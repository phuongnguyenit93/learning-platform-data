# Testing Timeouts, Pool Exhaustion, Broken Connections, and Ambiguous Commit Outcomes

Java applications connecting to MySQL via JDBC or a connection pool can encounter many errors that look similar: requests waiting too long, failing to acquire a connection, query timeouts, dropped sockets, or clients losing connectivity right at commit time. These situations have distinct causes and remedies. Lumping them all together into a generic "database timeout" and retrying immediately can create duplicate transactions, keep broken connections in the pool, or amplify load on MySQL.

An especially tricky case is an **ambiguous commit outcome**: the client sends `COMMIT`, MySQL may already have committed successfully, yet the response is lost on the network. The client receives an exception and does not know whether the transaction committed. Calling `rollback()` on a broken connection does not prove the transaction was not committed. To handle this properly, applications must classify timeouts by layer, manage transactions cleanly, and use idempotency keys to verify or safely retry operations.

This lesson focuses on testing Java/Spring Boot systems backed by MySQL and JDBC. Examples assume business tables use InnoDB, a connection pool such as HikariCP, and MySQL 8.0. Specific property names should be checked against your deployed driver, pool, and framework versions.

## Learning Objectives

After this lesson, you will be able to:

- Distinguish pool acquisition timeout, connect timeout, query timeout, lock wait timeout, and socket/network timeout.
- Identify pool exhaustion, connection leaks, and stale connections.
- Test connection failures before DML, during DML, and around `COMMIT`.
- Explain why losing a commit response produces an ambiguous outcome for the client.
- Design idempotency keys, checkpoints, and bounded retries.
- Verify data state after an error using a fresh connection to the authoritative data source.
- Collect metrics from HikariCP, JDBC, and MySQL to pinpoint root causes.
- Write reproducible fault-injection tests independent of random timing.

## 1. Distinguishing Timeout Layers

A request traverses multiple layers before receiving a response from MySQL. Each layer has its own timeout; expiring in one layer does not automatically stop the remaining layers.

```text
HTTP request / service deadline
             |
             v
       Connection pool
       wait to acquire connection
             |
             v
       TCP connect / TLS
             |
             v
       JDBC statement
       query timeout
             |
             v
       MySQL execution
       lock wait / execution
             |
             v
       Socket read/write
             |
             v
       COMMIT response
```

| Timeout | Layer | Example setting | What it bounds |
|---|---|---|---|
| Pool acquisition timeout | Connection pool | Hikari `connectionTimeout` | Time spent waiting for an idle connection from the pool |
| Connect timeout | JDBC/network | Connector/J `connectTimeout` | Time allowed to establish a TCP connection to the server |
| Query timeout | JDBC statement | `Statement.setQueryTimeout()` | Time the driver allows a statement to run before requesting cancellation |
| Transaction timeout | Framework/transaction manager | Spring `@Transactional(timeout=...)` | Transaction time limit per transaction manager capabilities |
| Lock wait timeout | InnoDB | `innodb_lock_wait_timeout` | Time InnoDB waits for a row lock |
| Socket/network timeout | JDBC socket | Connector/J `socketTimeout` | Time waiting for response data on the socket before the driver errors |
| Idle session timeout | MySQL server | `wait_timeout` | Time before an idle non-interactive session is closed by the server |
| Network packet timeout | MySQL server | `net_read_timeout`, `net_write_timeout` | Time the server waits to read/write a data packet over a connection |

Never set every timeout to the same number. For example, pool acquisition timeout is typically shorter than the request deadline; connect timeout must fit the network; socket timeout must allow legitimate queries while staying inside the request budget; transaction timeout must account for connection acquisition and application processing time.

### 1.1. Pool Connection Acquisition Timeout

If the pool has exhausted its connections and none are returned before `connectionTimeout`, `getConnection()` fails. In that case, no SQL was ever sent to MySQL.

Common causes:

- Some requests hold connections too long or forget to close them.
- Transactions span HTTP calls, file I/O, or waiting on external services.
- Slow queries, lock waits, or database overload prevent connections from returning.
- Pool size is too small for actual concurrency.
- Pool size is configured too large for MySQL's capacity, driving up concurrent query load.

Pool exhaustion is a symptom; it does not automatically prove `maximumPoolSize` should be increased. First inspect active, idle, and pending connections, connection hold times, and running queries.

### 1.2. Connect Timeout and Socket Timeout

In modern MySQL Connector/J releases, `connectTimeout` and `socketTimeout` are configured in milliseconds. Example:

```text
jdbc:mysql://db.example:3306/app?connectTimeout=3000&socketTimeout=15000
```

`connectTimeout` applies when establishing the connection. `socketTimeout` governs waiting for socket data once connected. If `socketTimeout` expires during a query or commit, the driver closes the connection because protocol exchange state is no longer known.

Do not set `socketTimeout` overly low to "protect" requests. A valid query may legitimately need longer; an overly tight timeout triggers false errors, reconnects, and retries that add load. Base settings on SLOs, observed latency distributions, and application-layer budgets.

### 1.3. Query Timeout Is Not Socket Timeout

JDBC supports:

```java
try (PreparedStatement ps = connection.prepareStatement(
        "SELECT id, status FROM orders WHERE customer_id = ?")) {
    ps.setLong(1, customerId);
    ps.setQueryTimeout(5); // seconds
    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            // Read results.
        }
    }
}
```

`setQueryTimeout(5)` asks the driver to cancel the statement if it exceeds the limit per the JDBC contract. Cancellation mechanics depend on driver and server; it neither guarantees the TCP socket closes nor automatically rolls back the entire transaction. After a query timeout, the application must determine transaction state and roll back if needed before reusing the connection.

In MySQL, `max_execution_time` caps execution time for certain read-only `SELECT` statements in milliseconds; it is not a general timeout for all `INSERT`, `UPDATE`, `DELETE`, or transactions. Example:

```sql
SET SESSION max_execution_time = 5000;
```

Do not use this variable in place of JDBC query timeout or transaction timeout. For lock contention, inspect `innodb_lock_wait_timeout`; for overall request duration, enforce deadlines at the service/API layer.

### 1.4. Idle Timeout and Stale Connections

MySQL can close idle sessions via `wait_timeout`. Firewalls, NATs, load balancers, or proxies can also drop idle connections before the pool realizes it. A connection sitting in the pool whose underlying socket is already dead is a stale connection.

HikariCP provides properties like `maxLifetime`, `keepaliveTime`, and `validationTimeout`. Generally:

- Set `maxLifetime` shorter than any proxy or network infrastructure connection age limit.
- Set `keepaliveTime` lower than `maxLifetime` if idle connections need periodic checks; Hikari only runs keepalive on idle connections.
- Rely on JDBC4 validation (`Connection.isValid`) when supported by the driver; avoid adding `connectionTestQuery` unnecessarily.
- Never hold connections longer than required in application code.

MySQL's `wait_timeout` and pool timeouts serve different purposes. The pool should retire connections before infrastructure drops them, or detect invalid connections before handing them to requests.

## 2. Configuring and Observing HikariCP

Example Spring Boot configuration:

```yaml
spring:
  datasource:
    url: jdbc:mysql://db.example:3306/app?connectTimeout=3000&socketTimeout=20000
    username: app_user
    hikari:
      maximum-pool-size: 20
      minimum-idle: 5
      connection-timeout: 3000
      validation-timeout: 1000
      max-lifetime: 1500000
      keepalive-time: 300000
      leak-detection-threshold: 30000
```

These numbers are illustrative only, not universal recommendations. `maxLifetime` and `keepaliveTime` must align with MySQL, proxy, and infrastructure limits. `leak-detection-threshold` only logs warnings for connections held too long; it does not forcibly reclaim connections or replace proper resource closing.

### 2.1. Metrics to Monitor

HikariCP exposes metrics including:

- `active`: connections currently borrowed by the application.
- `idle`: available idle connections.
- `pending`: threads waiting to acquire a connection.
- `total`: current total connections.
- Timeout counts and acquire/usage latency when metrics integration is enabled.

Interpreting common signals:

| Signal | Likely issue to investigate |
|---|---|
| `active` pinned at `maximumPoolSize`, `pending` rising | Pool exhausted due to slow queries, long transactions, leaks, or excessive concurrency |
| `idle=0`, `active` high yet MySQL shows few queries | Connections held in app code, waiting on non-DB locks, or doing external work |
| Timeouts after long idle periods | Stale connections from `wait_timeout` or network devices |
| `active` climbs steadily and never drops | Leak, unclosed resources, or unclosed transactions |
| High `active` alongside high `Threads_running` and latency | Database likely overloaded or experiencing lock contention |

Never raise pool size solely because `pending` is nonzero. Adding connections can push more concurrent queries onto MySQL, slowing every request further.

### 2.2. MySQL-Side Metrics

Check connections and load:

```sql
SHOW GLOBAL STATUS
WHERE Variable_name IN (
  'Threads_connected',
  'Threads_running',
  'Max_used_connections',
  'Connections',
  'Aborted_connects',
  'Aborted_clients'
);

SHOW GLOBAL VARIABLES
WHERE Variable_name IN (
  'max_connections',
  'wait_timeout',
  'net_read_timeout',
  'net_write_timeout',
  'innodb_lock_wait_timeout',
  'max_execution_time'
);
```

Check active transactions and sessions:

```sql
SELECT *
FROM information_schema.innodb_trx
ORDER BY trx_started;

SHOW FULL PROCESSLIST;
```

High `Threads_connected` does not automatically mean pool exhaustion; it can reflect multiple pools, services, or idle sessions. Correlate app pool metrics with `Threads_running`, transaction age, and query latency to locate bottlenecks.

## 3. Designing Timeout and Pool Exhaustion Tests

Tests must have clear targets and recovery cleanup. Never spin infinite connection loops against a shared database. Use a test MySQL instance/container and a small pool to create reproducible conditions.

### 3.1. Controlled Pool Exhaustion Testing

Example test config with a single-connection pool:

```yaml
spring:
  datasource:
    hikari:
      maximum-pool-size: 1
      minimum-idle: 1
      connection-timeout: 500
```

The test borrows and holds the first connection, then requests a second connection. The second request must time out near the configured threshold. Once the first connection is returned, a subsequent request must succeed.

Outcomes to verify:

1. The second acquire fails within the expected time window.
2. No SQL is sent by the request that failed to acquire a connection.
3. Once the first connection closes/returns to the pool, pending drops and new acquires succeed.
4. No connections remain leaked in the pool after the test finishes.

This tests pool acquisition, not MySQL query timeout. Never use long `Thread.sleep()` calls as primary synchronization; use latches/barriers to guarantee the first connection is held before triggering the second request.

### 3.2. Testing Connection Leaks

Create a code path in a test fixture or mock service that intentionally omits closing a connection, then observe leak warnings and pool metrics. Never introduce intentional leaks into production code. After the test, ensure resources are released and the pool shuts down cleanly.

In real code, prefer try-with-resources:

```java
try (Connection connection = dataSource.getConnection();
     PreparedStatement ps = connection.prepareStatement(
         "SELECT COUNT(*) FROM orders WHERE status = ?")) {
    ps.setString(1, "PENDING");
    try (ResultSet rs = ps.executeQuery()) {
        rs.next();
        return rs.getLong(1);
    }
}
```

With Spring Data JPA/`JdbcTemplate`, let the framework manage connections; never borrow a connection manually and hold it across HTTP calls, email sends, or file processing.

### 3.3. Testing Lock Wait Timeouts

Use two sessions against the same MySQL test instance:

```sql
-- Session A
START TRANSACTION;
UPDATE accounts SET balance = balance - 10 WHERE id = 1;
-- Keep transaction open to hold the row lock.
```

```sql
-- Session B
SET SESSION innodb_lock_wait_timeout = 2;
START TRANSACTION;
UPDATE accounts SET balance = balance + 10 WHERE id = 1;
```

Session B waits for the row lock; if Session A does not commit or roll back within the limit, Session B receives a lock wait timeout error. After the error, check Session B's transaction state and roll back the entire transaction per application logic before reusing the connection.

Release Session A:

```sql
-- Session A
COMMIT;
```

Tests must confirm no unintended partial updates occurred, transactions ended cleanly, and connections returned to the pool. Deadlocks differ from lock wait timeouts: the deadlock detector can pick a victim transaction and roll it back before `innodb_lock_wait_timeout` expires.

## 4. Testing Broken Connections

Connections can drop at various points. Outcomes depend on whether the request reached the server and how far MySQL progressed.

| Disconnect timing | What the client knows | What to do |
|---|---|---|
| Before TCP connect completes | Connection was never established | Bounded connect retry if error is transient |
| After connect, before sending statement | No statement was sent if confirmed cleanly | Discard broken connection; open a new one |
| While sending/executing DML | Server may not have received, may be running, or may have finished the statement; client lost response | Under InnoDB, statements are atomic, yet the transaction may still be uncommitted; verify via idempotency key |
| After DML, before `COMMIT` | Transaction may still be open on server or session closed | Server rolls back uncommitted transactions when session closes, though client should verify if connection state is unclear |
| While sending `COMMIT` or waiting for response | Commit may have succeeded with lost ACK, or commit did not complete | Treat as ambiguous outcome; query authoritative primary by idempotency key |
| After receiving commit ACK | Client received commit confirmation from server | Record success; handle any downstream failures separately |

When a connection drops, the server normally detects the closed socket and rolls back uncommitted InnoDB transactions. However, if commit completed before the server noticed the dropped socket, changes may already be committed. Thus, a socket error alone never answers "was the transaction persisted?"

### 4.1. Fault Injection

To reproduce network faults, place a test proxy such as Toxiproxy between the application and MySQL, or use isolated firewall rules. Build scenarios:

- Block new connections to test connect timeout.
- Sever idle connections to test stale connections and pool validation.
- Inject latency or bandwidth caps to test socket/query timeouts.
- Reset connections mid-query.
- Cut the link right after the server processes commit but before the client receives the response.

That final scenario is difficult to hit reliably with random socket drops. To test ambiguous commits deterministically, use an observable synchronization point—such as a test proxy that delays/drops the server response after forwarding the commit packet, or a server/proxy test hook confirming commit reached the server before blocking the response.

Never run fault injection against production or shared networks. Every test needs an overall timeout, proxy rule cleanup, and connection restoration in `finally` so subsequent tests stay clean.

## 5. Ambiguous Commit Outcomes

Suppose an application executes:

```java
connection.setAutoCommit(false);
insertPayment(connection, payment);
connection.commit();
```

MySQL may commit the transaction while the commit response is lost due to a network drop. JDBC throws an exception, yet the client cannot infer from the exception alone whether the server rolled back or committed. Calling `connection.rollback()` on an already broken socket generally cannot reach the server and cannot undo a completed commit.

That is why retrying a financial operation or order creation solely because "the client saw an error" risks creating duplicate records. Design operations with idempotent identifiers so retries can determine the outcome of the prior attempt.

### 5.1. Distinguishing Definite Failures from Ambiguous Outcomes

- If failure happened before sending the request to the server and the application has proof, the operation never ran and may be retried.
- If MySQL returned a clear SQL error for a statement while the connection remains intact, handle by error type and roll back or fix data.
- If connectivity dropped while sending or executing a statement or commit, treat the outcome as potentially ambiguous.
- If a commit confirmation was received, the server confirmed commit; downstream failures in HTTP or message brokers belong to downstream recovery.

Never classify every `SQLTransientConnectionException`, `SQLRecoverableException`, or SQLState class `08` as "uncommitted." Those exceptions signal connection problems, not server transaction state.

## 6. Idempotency Keys for Resolving Ambiguous Outcomes

A business request can carry a unique `request_id` generated by the client or caller service. The server persists the request ID alongside the business result in the **same transaction**. If the client loses the response and resends the same request ID, a unique key prevents executing the action twice.

Example request-tracking table:

```sql
CREATE TABLE payment_requests (
  request_id VARCHAR(64) NOT NULL,
  payload_hash BINARY(32) NOT NULL,
  payment_id BIGINT UNSIGNED NOT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (request_id),
  UNIQUE KEY uk_payment_requests_payment (payment_id)
) ENGINE = InnoDB;
```

The business `payments` table also needs appropriate unique keys for its domain rules. Example flow:

```text
Receive request_id and payload
          |
          v
START TRANSACTION
          |
          v
Insert payment and request record
in the same transaction
          |
          v
COMMIT
          |
     +----+----+
     |         |
   ACK recvd  ACK lost
     |         |
   Return    Client unsure
   result          |
                   v
           Resend same request_id
                   |
                   v
           Lookup payment_requests
                   |
            +------+------+
            |             |
          Found        Not found
            |             |
       Verify hash    Retry safely
       return result  under idempotency
```

Both inserts must execute in a single InnoDB transaction. If the payment commits without saving the request record in the same transaction, deduplication may miss that the transaction already succeeded. Conversely, if the request record commits without the payment, state becomes inconsistent.

### 6.1. Verifying Payload to Catch Improper Key Reuse

One request ID must represent only one business payload. When receiving the same key again:

- If `payload_hash` matches, return the stored result.
- If the hash differs, reject the request because the client reused a key for a different operation.
- If the initial request is still in flight, the unique constraint may make the competing transaction wait until the first commits or rolls back; set timeouts and handle duplicates properly.

Compute the hash over a canonicalized payload representation rather than arbitrary JSON field order or whitespace. Never use the hash in place of request authentication or authorization checks.

### 6.2. Example Duplicate Handling

JDBC pseudo-code:

```java
try (Connection connection = dataSource.getConnection()) {
    connection.setAutoCommit(false);
    try {
        long paymentId = insertPayment(connection, command);
        insertPaymentRequest(
            connection,
            command.requestId(),
            command.payloadHash(),
            paymentId
        );
        connection.commit();
        return loadPaymentResult(connection, paymentId);
    } catch (SQLException e) {
        try {
            connection.rollback();
        } catch (SQLException rollbackError) {
            e.addSuppressed(rollbackError);
        }
        throw e;
    }
}
```

This is the transaction skeleton for the first execution. Upon receiving a duplicate key or an ambiguous connection error around commit, handle it using a fresh connection to the authoritative primary: query `payment_requests` by `request_id`, compare `payload_hash`, and return the stored result if present. If no record is found, do not jump to the conclusion that the earlier transaction rolled back: the server might still be running or not yet have detected the dropped session. A synchronizing approach is attempting to insert the same idempotency key in a new transaction; the unique index forces the retry to wait until the prior transaction commits or rolls back. If the prior committed, the retry hits duplicate key; if the prior rolled back, the retry inserts the record and proceeds. Set lock wait timeouts and handle duplicates per business logic. Retry only after confirming you are talking to the authoritative primary.

In real implementations, distinguish a duplicate key on `payment_requests` from a duplicate key on `payments`, ensuring proper insert ordering and unique constraints. The pseudo-code above omits full duplicate/reconciliation branches.

### 6.3. Reading from the Authoritative Primary

After an ambiguous commit error, never query an asynchronous replica and conclude the request did not commit just because the row is missing. The replica may not have applied the transaction yet. Read state from the writable primary or use an appropriate read-after-write consistency mechanism.

If the primary failed over, verify whether the transaction reached the new primary. Under asynchronous replication, a transaction committed on the old primary before replicating can be lost on failover. Idempotency records only identify what exists on the current topology; they cannot resurrect a commit lost across all nodes.

## 7. Bounded, Properly Scoped Retries

Retries must depend on error classification and operation idempotency. A sound policy usually includes:

- A small, explicit maximum attempt count.
- Exponential backoff with jitter so clients do not retry in lockstep.
- An overall request deadline.
- Retrying only classified transient errors; never retry data, privilege, or syntax errors.
- Retrying the entire transaction after confirmed deadlock or rollback, never just re-running the final statement.
- Reusing the same idempotency key when commit state is ambiguous.
- Logging attempt number, request ID, `SQLSTATE`, vendor code, and wait time without logging secrets or sensitive data.

Illustrative backoff logic:

```text
delay = min(max_delay, base_delay * 2^attempt) + random_jitter
retry only if transient and request is idempotent
stop when attempts or request deadline is exhausted
```

Never retry indefinitely. When the database is overloaded, retries add connections and queries, exhausting pools faster. Use circuit breakers or load shedding when services must fail fast during database degradation.

### 7.1. Deadlocks and Lock Wait Timeouts

Deadlocks typically cause InnoDB to roll back one victim transaction. Applications can retry the entire transaction if the operation is idempotent and the error is properly classified. Default lock wait timeout usually rolls back only the waiting statement; the transaction may remain open. Explicitly roll back the entire transaction in the application before retrying to avoid keeping locks from earlier statements.

### 7.2. Socket Timeouts and Commit Errors

If a socket timeout occurs during `commit()`, do not treat it as an ordinary retryable error. Log the request ID, discard the connection, record the timestamp, and open a new connection to reconcile by idempotency key. Never reuse the broken connection and never submit a new business operation with a fresh request ID for the same user action.

## 8. Spring Transactions and Timeouts

Spring defines transaction boundaries at the service layer:

```java
@Transactional(timeout = 10)
public PaymentResult createPayment(CreatePaymentCommand command) {
    // Write payment and idempotency record in the same transaction.
    return paymentRepository.create(command);
}
```

`@Transactional(timeout=10)` specifies a transaction timeout in seconds for the transaction manager. How that timeout propagates to JDBC statements depends on the transaction manager, JDBC driver, and data access technology. It does not automatically replace `connectTimeout`, `socketTimeout`, pool `connectionTimeout`, or HTTP deadlines.

Never wrap slow non-database operations—such as HTTP calls, sending emails, or waiting on user input—inside a database transaction. Keeping transactions short reduces connection and lock hold times.

If events must be published after database writes, consider the transactional outbox pattern: write the business row and outbox row in the same transaction, then have a worker publish events and mark them processed. This prevents database commit succeeding while message publishing fails, or vice versa. Consumers still need idempotency because messages can be redelivered.

## 9. Testing Failure Scenarios

A thorough test suite covers pool, MySQL, network, and transaction states.

| Scenario | How to reproduce in test | Outcomes to verify |
|---|---|---|
| Pool exhaustion | Small pool; hold connection with latch then request another | Acquire times out at limit; no SQL sent; pool recovers when released |
| Connection leak | Intentionally hold connection in test fixture | Leak warnings/metrics fire; cleanup closes resources |
| Connect timeout | Block MySQL port or point to unresponsive endpoint | Fails within connect deadline; threads do not hang forever |
| Query timeout | Run slow test query with `setQueryTimeout` | Driver throws timeout; transaction handled cleanly; connection not reused in unknown state |
| Lock wait timeout | Session A holds row lock; Session B updates same row with short timeout | Session B hits lock wait error; app rolls back and releases locks |
| Idle stale connection | Close idle socket via proxy or set short test idle timeout | Pool evicts broken connection and issues a fresh one |
| Disconnect during DML | Reset connection while statement executes | App classifies ambiguous outcome and reconciles by request ID |
| Disconnect around commit | Forward `COMMIT` to server then drop response | Client creates no duplicate; querying idempotency record resolves outcome |
| Failover after commit | Simulate primary loss after commit before replica receives log | Verify RPO, GTID, and asynchronous replication limits |

### 9.1. Synchronized Testing of Ambiguous Commits

A proper test must establish two contrasting outcomes:

**Case A — server committed, response lost:**

1. Client begins transaction, inserts payment and request record.
2. Proxy forwards `COMMIT` to MySQL.
3. Test confirms the server processed commit, then blocks/drops the response back to client.
4. Client receives a connection error.
5. Client reconnects to primary and queries with the same request ID.
6. Test verifies only one payment exists and the stored result is returned from the request record.

**Case B — commit never reached server:**

1. Client begins transaction and writes uncommitted data.
2. Proxy blocks `COMMIT` before it reaches the server or severs the session before commit.
3. Client receives an error.
4. Test waits for server to close session and roll back the uncommitted transaction.
5. Client retries with the same request ID.
6. Test verifies only one payment exists after the successful retry.

Never run a random socket-kill test and claim you tested ambiguous commits. Without controlling the exact cut point, the test may only be exercising connect or query errors.

### 9.2. Post-Failure Assertions

After every scenario, verify:

- Number of business records per request ID.
- Number of idempotency records and matching payload hash.
- Before/after balances or totals in financial tests.
- No hanging transactions or leaked connections remain in the pool.
- `active`/`idle`/`pending` metrics return to baseline.
- Replica lag and GTID behave per test expectations.
- Retries caused no duplicate side effects in message brokers or external systems.

## 10. Diagnosing Incidents in Live Environments

When receiving timeout or connection reset errors, gather evidence in order:

1. **Request layer:** request ID, deadline, endpoint, start/end timestamps, and retry count.
2. **Pool:** active/idle/pending/total, acquire latency, timeout counts, leak warnings.
3. **JDBC:** exception class, `SQLSTATE`, vendor code, active operation (`getConnection`, `execute`, `commit`), and driver version.
4. **MySQL:** `Threads_connected`, `Threads_running`, process list, transaction age, lock waits, error log.
5. **Network:** resets, retransmissions, proxy idle timeouts, DNS, firewalls, and app-to-DB latency.
6. **Transaction:** whether the request carried an idempotency key, whether commit was confirmed, and whether data exists on the primary.
7. **Topology:** whether failover or replica lag occurred during the error window; whether the current endpoint points to the authoritative primary.

Never log passwords, full connection URLs containing secrets, tokens, or sensitive payloads. For ambiguous commit incidents, retain request IDs and timestamps sufficient to correlate application, proxy, and MySQL logs.

## 11. Practice Exercise

A Spring Boot service creates orders and processes payments using MySQL. HikariCP has `maximumPoolSize=10`. During peak load:

- The API occasionally returns timeouts.
- Hikari reports `Connection is not available, request timed out`.
- Some JDBC logs show `Communications link failure`.
- Clients retry requests and occasionally create two payments for the same order.
- MySQL shows elevated `Threads_running` and several transactions waiting on locks.

Design an investigation and testing plan:

1. Distinguish pool acquisition timeout, connect timeout, query timeout, lock wait timeout, and socket timeout in this scenario.
2. Which Hikari metrics must be collected to tell a pool leak apart from slow queries?
3. Write two SQL sessions to induce a controlled lock wait timeout and specify which transaction must roll back.
4. Design a pool exhaustion test using a small pool size and latches, without long sleeps for synchronization.
5. Use a proxy to inject faults before DML, during DML, and after forwarding `COMMIT` but before returning the response.
6. Design an idempotency table with a unique request ID and payload hash; ensure payment and request record commit in one transaction.
7. If connectivity drops during `commit()`, why cannot you rely on the exception or `rollback()` to determine the outcome?
8. Why must you look up the idempotency record on the primary instead of an async replica right after the error?
9. Design a bounded retry policy with exponential backoff, jitter, and an overall deadline.
10. List assertions proving retries do not create duplicate payments, leak connections, or keep exhausting the pool.
11. If the primary fails over before a transaction replicates, how should RPO and GTID be evaluated?

A complete plan must include a layered failure matrix, synchronizable fault-injection points, stable idempotency keys, and data verification criteria after each retry. Run the entire exercise on an isolated MySQL test instance.

## 12. Common Misconceptions

- **Calling every timeout a query timeout:** failures can stem from pool waits, connects, locks, sockets, or request deadlines.
- **Immediately raising pool size on exhaustion:** if MySQL is overloaded, more connections can make things worse.
- **Assuming query timeout rolls back the transaction:** verify transaction state and roll back on the connection explicitly.
- **Assuming socket timeout means MySQL never ran the statement:** the server may have received and executed the request.
- **Assuming `rollback()` after disconnect proves uncommitted state:** the rollback command may never reach the server; commit may already have finished.
- **Retrying with a fresh request ID:** defeats deduplication of the earlier attempt.
- **Querying a replica immediately to check commit:** async replicas may not yet have received or applied the transaction.
- **Treating leak detection as automatic reclamation:** warnings only detect long-held connections.
- **Testing only by killing MySQL:** fails to reproduce all network-cut states around commit.
- **Conflating database commit with external side effects:** use an outbox and idempotent consumers for integration flows.

## Conclusion

Timeouts and connection drops must be classified by layer: pool, connect, statement, lock, socket, and request. Pool exhaustion typically reflects connections held too long or a slow database; raising pool size does not always help. In particular, losing a response during `COMMIT` creates an ambiguous outcome on the client: the transaction may already have committed. Designing idempotency keys and persisting request records alongside business data in one transaction enables applications to look up outcomes and retry safely. Test using synchronized fault injection, monitor both application and MySQL metrics, and verify data after every scenario.
