# Connect Timeout, Read Timeout, Query Timeout, and Statement Cancellation in Oracle JDBC

## 1. Why are multiple timeout types needed?

A Java application connecting to Oracle Database via JDBC waits across several distinct stages: acquiring a connection from the pool, opening the network connection, authenticating the session, sending SQL, waiting for database execution, receiving data, and reading the full `ResultSet`. Each stage has its own wait mode and failure causes.

If only a single generic timeout is set, the application may still hang in another stage. For example:
- The pool runs out of connections, and requests wait a long time before the JDBC driver is even called.
- TCP or the listener fails to respond while creating a physical connection.
- The database is executing a query while the client waits on socket read.
- A SQL statement runs too long and must be cancelled.
- A user cancels a request, yet the SQL keeps running on the database.
- Reading large data or a LOB stalls after the statement has already returned a cursor.

This lesson belongs to the **Database Engine Relational Oracle** module, **Oracle JDBC** chapter, focusing on **connect timeout, read timeout, query timeout, and statement cancellation**.

Layers to distinguish:

| Timeout type | What does it control? | Example mechanism |
|---|---|---|
| Pool acquisition timeout | Wait time to borrow a connection from the pool | Connection pool configuration |
| Connect timeout | Time to open a connection to database/listener | Oracle Net connect descriptor, JDBC connection properties |
| Read/socket timeout | Wait time for data from the socket | `oracle.jdbc.ReadTimeout` |
| Query timeout | Allowed execution time for a statement | `Statement.setQueryTimeout()` |
| Call timeout | Maximum time for a single database round trip | `OracleConnection.setCallTimeout()` |
| Network timeout | Time a JDBC request waits for a database response before marking the connection unusable | `Connection.setNetworkTimeout()` |
| Application deadline | Total time the caller waits for the entire request | API/service layer |

These timeouts do not replace one another. A sound configuration sets timeouts at each layer, ties them to the overall deadline, and defines how connections and transactions are handled after a timeout.

## 2. Lifecycle of a JDBC request

A request normally passes through this sequence:

```text
HTTP / application request
          |
          v
Wait for connection from pool
          |
          v
Open physical connection if needed by pool
          |
          v
Oracle Net / TCP / listener / service
          |
          v
Send SQL and bind parameters
          |
          v
Oracle parse / execute / fetch
          |
          v
Receive results over socket
          |
          v
Read ResultSet / LOB / batch results
          |
          v
Commit or roll back transaction
          |
          v
Return response to caller
```

Every step can block. Timing out at the HTTP layer does not mean the database stopped the SQL statement. A socket read timeout also does not mean the transaction rolled back.

Timeout design must answer:
1. How long is the entire request allowed to wait in total?
2. How long may borrowing or opening a connection wait?
3. How long may a SQL statement run?
4. If no response arrives, is the connection still usable?
5. Could the transaction have committed already?
6. Who is responsible for cancelling statements and releasing resources?

## 3. Pool acquisition timeout: waiting for a connection is not connect timeout

Applications commonly call:

```java
Connection connection = dataSource.getConnection();
```

When using a connection pool, this call may wait for an idle connection. This is **pool acquisition timeout**. While waiting for the pool to grant a connection, the JDBC driver may not have initiated any new network connection yet.

Common causes:
- All connections are currently checked out by other requests.
- Transactions hold connections too long.
- Some connections are hung or not yet detected as broken.
- Pool `maximumPoolSize` is smaller than actual concurrency.
- Requests hold connections while calling external APIs or sleeping during retries.
- Connection leaks from failing to close `Connection`, `Statement`, or `ResultSet`.

### 3.1. Pool configuration

Property names vary by library. For example, with HikariCP, `connectionTimeout` limits how long a caller waits to borrow a connection from the pool:

```java
HikariConfig config = new HikariConfig();
config.setJdbcUrl(jdbcUrl);
config.setUsername(username);
config.setPassword(passwordFromSecretProvider);

config.setMaximumPoolSize(20);
config.setConnectionTimeout(2_000);
config.setValidationTimeout(1_000);
```

Numbers are illustrative only. The pool's `connectionTimeout` is not the time to open a socket to Oracle. When the pool needs to open a new physical connection, the driver has its own connect timeout.

### 3.2. Do not enlarge pool size to hide timeouts

If the pool frequently runs out of connections, inspect:
- Concurrent request volume.
- Connection hold duration.
- Transaction duration.
- Slow SQL.
- Connection leaks.
- Database session/process limits.
- Requests waiting on external services while still holding connections.

Enlarging pool size can flood the database with sessions and worsen contention. Fix why connections are held long before raising limits.

### 3.3. Return connections on every code path

Use try-with-resources to guarantee JDBC resources are closed:

```java
try (Connection connection = dataSource.getConnection();
     PreparedStatement statement = connection.prepareStatement(
             "SELECT order_id FROM app.orders WHERE order_id = ?")) {

    statement.setLong(1, orderId);

    try (ResultSet resultSet = statement.executeQuery()) {
        while (resultSet.next()) {
            long id = resultSet.getLong(1);
        }
    }
}
```

With a pool, `Connection.close()` usually returns the logical connection to the pool rather than closing the physical socket. Broken connections must be flagged and evicted by the driver/pool mechanism.

## 4. Connect timeout: bounding time to open an Oracle connection

Connect timeout limits how long the client waits to establish a connection to Oracle. This phase can include multiple steps:
- Hostname/DNS resolution.
- TCP connection establishment.
- Connecting to the listener.
- Listener locating a matching service/handler.
- Database creating a session and authenticating the user.
- TLS/wallet steps if configured.

A timeout on a single step does not necessarily bound the entire `DataSource.getConnection()` duration if pooling, DNS, or retries have separate timings.

### 4.1. Oracle Net connect descriptor

Timeouts can be specified inside the connect descriptor:

```text
jdbc:oracle:thin:@(DESCRIPTION=
  (CONNECT_TIMEOUT=5)
  (TRANSPORT_CONNECT_TIMEOUT=3)
  (RETRY_COUNT=1)
  (ADDRESS=
    (PROTOCOL=TCP)
    (HOST=db.example.internal)
    (PORT=1521)
  )
  (CONNECT_DATA=
    (SERVICE_NAME=orders.example.internal)
  )
)
```

In this example:
- `TRANSPORT_CONNECT_TIMEOUT` bounds establishing the transport connection per Oracle Net semantics.
- `CONNECT_TIMEOUT` bounds the connection phase per Oracle Net descriptor rules.
- `RETRY_COUNT` controls address/connection retries per supported configuration.

Units, scope, and interactions among parameters must be verified against your Oracle Database/Oracle Net/Oracle JDBC release. When multiple addresses in `ADDRESS_LIST`, retries, or multiple services are configured, total elapsed time can exceed any single timeout value.

### 4.2. Oracle JDBC connection properties

The Oracle JDBC Thin Driver supports Oracle Net connection properties. Passing properties via `Properties`:

```java
Properties properties = new Properties();
properties.setProperty("user", username);
properties.setProperty("password", passwordFromSecretProvider);

// Illustrative value in milliseconds for the JDBC property.
properties.setProperty("oracle.net.CONNECT_TIMEOUT", "5000");

Connection connection =
        DriverManager.getConnection(jdbcUrl, properties);
```

Never place real passwords in source code, logs, or command lines. Retrieve credentials from a secret manager/wallet per deployment architecture.

Distinguish the JDBC property `oracle.net.CONNECT_TIMEOUT` from `CONNECT_TIMEOUT` in an Oracle Net connect descriptor; their representations and units are not necessarily identical. Check your deployed driver's documentation before configuring.

### 4.3. DriverManager login timeout

JDBC provides the API:

```java
DriverManager.setLoginTimeout(5);
```

The value is in seconds. This is a `DriverManager`-level login timeout; it is a global setting for connections managed by DriverManager and can affect other datasources in the same JVM.

For applications using multiple databases or pools, prefer configuring specific timeouts on the datasource/driver/pool rather than mutating a global setting without assessing impact.

### 4.4. DataSource login timeout

JDBC `DataSource` exposes `setLoginTimeout(int seconds)` in supporting implementations. This is a datasource-layer mechanism; the specific pool and datasource determine how it is applied.

Do not confuse it with pool acquisition wait time. Check the documentation for your pool and Oracle datasource.

### 4.5. Common connect errors

| Error | Investigation path |
|---|---|
| `ORA-12170` | Connect timeout; inspect network, listener, DNS, and timeouts |
| `ORA-12541` | No listener at host/port |
| `ORA-12514` | Listener does not recognize service name |
| `ORA-12154` | Could not resolve connect identifier |
| `ORA-01017` | Invalid credentials; do not retry the same credentials |
| `ORA-28000` | Account locked |
| Socket connect timeout | Inspect firewall, routing, host, and transport timeout |

Never retry service name or credential errors indefinitely. Distinguish configuration errors from transient network failures.

## 5. Read timeout and socket read timeout

After connecting successfully, JDBC sends a request to the database and waits for a response. **Read timeout** bounds how long the client waits to read data from the socket.

The Oracle JDBC Thin Driver provides the property:

```text
oracle.jdbc.ReadTimeout
```

This property is typically configured in milliseconds. Example:

```java
Properties properties = new Properties();
properties.setProperty("user", username);
properties.setProperty("password", passwordFromSecretProvider);
properties.setProperty("oracle.jdbc.ReadTimeout", "15000");

Connection connection =
        DriverManager.getConnection(jdbcUrl, properties);
```

It can be configured through OracleDataSource or corresponding datasource properties. How properties are passed depends on how the application creates connections.

### 5.1. Read timeout is not query timeout

Suppose the database runs a query taking 60 seconds. If the socket read timeout is 15 seconds, the client stops waiting for data after roughly that time and receives a socket/read timeout error.

This does not guarantee the database stopped the SQL statement at second 15. A socket-layer read timeout is not a server-side statement cancellation guarantee. The statement may continue executing until the server receives a cancel signal, the client closes the connection, or the operation finishes.

If you need to bound SQL execution duration, use an appropriate query timeout or call timeout rather than relying on socket read timeout alone.

### 5.2. Read timeout can occur during fetch

A SELECT statement may execute quickly yet return many rows. The application reads the `ResultSet` across multiple fetch batches. Any individual fetch may have to wait for the database to send the next batch.

Thus, a read timeout can occur:
- While waiting for execution results.
- While fetching subsequent batches of rows.
- While reading LOBs or large payloads across multiple round trips.
- When the database or network temporarily stalls.

`Statement.setQueryTimeout()` should not be treated as a guaranteed bound on total time spent consuming all rows of a `ResultSet`. Test the fetch phase separately and enforce an application-layer deadline.

### 5.3. Connection state after a read timeout

After a socket read timeout, the connection's state may no longer be reliable. With Oracle JDBC Thin, a socket read failure can render the connection unusable or mark it broken.

The application should:
1. Stop using the current connection.
2. Close/discard the connection per pool mechanics.
3. Never return a broken connection to the pool as healthy.
4. If the transaction included DML, determine transaction outcome before re-submitting business operations.
5. Acquire a fresh connection for subsequent work.

Never re-execute statements on a socket that timed out assuming the session remained synchronized.

## 6. Query timeout with Statement.setQueryTimeout()

JDBC provides:

```java
statement.setQueryTimeout(5);
```

The parameter unit is **seconds**. If execution exceeds the threshold, the driver attempts to cancel the statement and reports an error to the application, usually via `SQLTimeoutException` or `SQLException` depending on driver/operation.

Example:

```java
String sql = """
    SELECT order_id, customer_id, amount
    FROM app.orders
    WHERE status = ?
    """;

try (Connection connection = dataSource.getConnection();
     PreparedStatement statement = connection.prepareStatement(sql)) {

    statement.setQueryTimeout(5);
    statement.setString(1, "OPEN");

    try (ResultSet resultSet = statement.executeQuery()) {
        while (resultSet.next()) {
            long orderId = resultSet.getLong("order_id");
            BigDecimal amount = resultSet.getBigDecimal("amount");
        }
    }
}
```

### 6.1. Set timeout before execute

Call `setQueryTimeout()` before `executeQuery()`, `executeUpdate()`, or `execute()`. Setting timeout on a statement after execution cannot retroactively apply to an already-started run.

### 6.2. Unit is seconds

`setQueryTimeout(5)` means 5 seconds, not 5 milliseconds. A value of 0 means no query timeout limit per the JDBC API.

Never pass `5000` intending 5 seconds; that becomes 5,000 seconds.

### 6.3. What are the limits of query timeout?

Query timeout bounds statement execution per the JDBC driver. It does not automatically include:
- Connection pool wait time.
- Time spent establishing a physical connection before obtaining a statement.
- Total request processing time in the application.
- All processing time after the statement returns a cursor, such as the entire result-consumption loop.
- Time waiting on another HTTP service called within the same request.

Combine query timeout with pool/connect/read timeouts and an application deadline.

### 6.4. Query timeout is a cancel request, not a transaction rollback

On timeout, the driver attempts to cancel the statement. However, the transaction may already contain earlier successful statements. Cancelling the current statement does not automatically mean the entire transaction rolled back.

If the business operation must be atomic, the application must roll back the transaction once it confirms the connection/session is usable and the transaction has not committed. If the connection drops around COMMIT, handle the indeterminate outcome per transaction design.

## 7. Oracle JDBC call timeout

Oracle JDBC provides the `OracleConnection.setCallTimeout(int milliseconds)` extension in supporting drivers.

This API sets a limit for **a single database round trip**. A SQL statement or stored procedure can involve multiple round trips, so call timeout is not necessarily the total wall-clock time of the entire business operation.

Example:

```java
import oracle.jdbc.OracleConnection;

try (Connection connection = dataSource.getConnection()) {
    OracleConnection oracleConnection =
            connection.unwrap(OracleConnection.class);

    // Each database round trip is limited to 5 seconds.
    oracleConnection.setCallTimeout(5_000);

    try (PreparedStatement statement =
                 connection.prepareStatement(
                     "SELECT order_id FROM app.orders WHERE order_id = ?")) {

        statement.setLong(1, orderId);
        statement.setQueryTimeout(10);

        try (ResultSet resultSet = statement.executeQuery()) {
            while (resultSet.next()) {
                long id = resultSet.getLong(1);
            }
        }
    }
}
```

This is an illustrative example. Package imports, APIs, and exact behavior depend on the Oracle JDBC driver version.

### 7.1. Call timeout differs from query timeout

- Query timeout limits statement duration per JDBC.
- Call timeout limits a single round trip to the database.
- A single operation can incur multiple round trips, such as execute, fetching multiple batches, or multiple interactions inside a stored procedure/client call.

Therefore, do not substitute call timeout for query timeout without understanding round-trip counts and how the driver executes the operation.

### 7.2. Resetting timeouts when using connection pools

`setCallTimeout()` is connection-level state. When a connection returns to the pool, the next request may inherit the timeout setting if the pool does not reset it.

Best practices:
- Set timeouts per request/connection checkout.
- Restore defaults or standard policy before returning the connection.
- Never let one request with a short timeout break subsequent requests.
- Check connection labeling/reset callbacks if supported by the pool.

### 7.3. When is call timeout useful?

Call timeout can be useful to bound waiting on a single database response, especially for applications needing protection against prolonged socket reads. Even so, combine it with an application deadline and query timeout to govern the total request.

## 8. JDBC Connection.setNetworkTimeout()

JDBC 4.1 provides the API:

```java
connection.setNetworkTimeout(executor, milliseconds);
```

This API bounds how long a JDBC request waits for a database response over the connection. If exceeded, the driver can mark the connection invalid and use the executor to execute abort actions per the JDBC contract.

Example:

```java
ExecutorService networkTimeoutExecutor =
        Executors.newSingleThreadExecutor();

try (Connection connection = dataSource.getConnection()) {
    connection.setNetworkTimeout(
            networkTimeoutExecutor,
            15_000
    );

    // Perform JDBC operations with bounded network wait.
} finally {
    networkTimeoutExecutor.shutdown();
}
```

This is a minimal example. In real applications, do not create a new executor per request. Use an application-managed executor and shut it down on application shutdown.

### 8.1. Connection network timeout is not statement timeout

Network timeout bounds response waits at the connection level. Exceeding it can abort the connection. Query timeout has statement-level semantics and usually gives the driver a chance to send a statement cancel request.

Do not use an overly short network timeout as a substitute for query cancellation. If network timeout fires first, the connection may be destroyed before the server-side statement stops as intended.

### 8.2. Reset before returning the connection

With pools, timeouts must be restored per pool policy before returning the connection. JDBC `getNetworkTimeout()` can inspect the current value; resetting must follow supported APIs and driver behavior.

An aborted connection must never be reused. The pool must remove it from circulation.

## 9. Proactive statement cancellation with Statement.cancel()

Besides automatic timeouts, an application can proactively cancel a running statement:

```java
statement.cancel();
```

This is useful when:
- A user clicks Cancel.
- An HTTP request is aborted by the client.
- An application deadline expires.
- A background task is stopped.
- A circuit breaker or orchestrator decides results are no longer needed.

JDBC permits one thread to call `cancel()` to request cancellation of a statement currently executing on another thread.

### 9.1. Example cancelling from a control thread

```java
ExecutorService executor = Executors.newSingleThreadExecutor();

try (Connection connection = dataSource.getConnection();
     PreparedStatement statement =
             connection.prepareStatement(
                 "SELECT order_id FROM app.large_orders")) {

    Future<?> cancelTask = executor.submit(() -> {
        try {
            Thread.sleep(5_000);
            statement.cancel();
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        } catch (SQLException e) {
            // Log cancel failure without sensitive data.
        }
    });

    try (ResultSet resultSet = statement.executeQuery()) {
        while (resultSet.next()) {
            // Process results.
        }
    } finally {
        cancelTask.cancel(true);
    }
} finally {
    executor.shutdownNow();
}
```

This illustrates how another thread requests cancellation. Never use `Thread.sleep()` as a production timeout mechanism; use framework schedulers/deadlines/cancellation tokens. If `cancel()` fails or the connection breaks, handle the connection according to its actual state.

### 9.2. Cancel is best effort

`Statement.cancel()` sends a cancel request through the driver/database. Do not assume:
- The server stops at the exact instant the client calls cancel.
- Every operation type can be interrupted instantaneously.
- The connection always remains healthy after cancel.
- The transaction automatically rolls back completely.

Applications must catch cancel errors, wait within reasonable bounds for the statement to finish, and verify connection health before reuse.

### 9.3. ORA-01013

When an operation is cancelled, Oracle may return:

```text
ORA-01013: user requested cancel of current operation
```

This normally signals that an operation was requested to cancel. However, applications must distinguish:
- User-initiated cancellation.
- JDBC query timeout.
- A middleware layer issuing a cancel.
- An administrative operation cancelling SQL.

Do not treat `ORA-01013` as a database error to retry automatically. Respect the caller's cancellation.

## 10. Distinguishing cancel statement, rollback transaction, and close connection

These actions have different goals:

| Action | Goal | Effect |
|---|---|---|
| `Statement.cancel()` | Stop a running statement | Requests cancellation of the active operation |
| `Connection.rollback()` | Undo uncommitted changes in the current transaction | Rolls back the transaction per Oracle semantics |
| `Connection.close()` | Close logical connection/return to pool | Releases connection per datasource/pool |
| `Connection.abort(executor)` | Destroy physical connection per JDBC | Connection is no longer usable |

### 10.1. Cancel is not rollback

Example transaction:
1. UPDATE balance of account A.
2. INSERT ledger entry.
3. SELECT confirmation report.
4. SELECT times out.

Cancelling only the final SELECT leaves the previous two changes in the transaction. If business rules require all-or-nothing atomicity, the caller must roll back.

### 10.2. Rollback requires a working connection

If the connection is still healthy and the transaction has not committed, call `rollback()` to undo uncommitted changes. If the connection is already lost, do not rely on sending rollback over a broken socket to assume the server rolled back.

Oracle cleans up sessions/transactions when it detects a disconnected session per database mechanics. However, if failure occurred around COMMIT, the outcome may be unknown to the client. Use idempotency keys or Transaction Guard in supported environments to resolve the outcome before re-submitting business actions.

### 10.3. When should a connection be aborted?

If a statement refuses to stop, the socket is broken, or the connection cannot resynchronize, you may need to discard/abort the connection per pool APIs and policies. Abort is drastic: the connection cannot be reused.

Do not abort a connection just for a slow query if `Statement.cancel()` resolves it safely. Pick the action based on driver/session state.

## 11. Designing timeouts around an overall deadline

Timeouts at each layer must fit inside the request's overall budget. Suppose an API has a 10-second deadline:

| Stage | Illustrative budget |
|---|---:|
| Wait on pool | 1 second |
| Open new connection if needed | 2 seconds |
| Execute SQL | 5 seconds |
| Read results and finish | 1 second |
| Reserve/response | 1 second |
| Total | 10 seconds |

Not every request opens a new physical connection. The table illustrates a worst-case budget.

### 11.1. Mental formula

\[
T_{\text{pool}} + T_{\text{connect}} + T_{\text{execute}}
+ T_{\text{fetch}} + T_{\text{application}} \leq T_{\text{deadline}}
\]

When retrying:
\[
\sum T_{\text{attempt}} + \sum T_{\text{backoff}}
\leq T_{\text{request deadline}}
\]

Do not start a new attempt if remaining time is insufficient for a meaningful attempt.

### 11.2. Sensible timeout ordering

A common configuration guideline:
- Pool acquisition timeout fits within the application deadline.
- Connect timeout fits within the connection-creation budget.
- Query timeout is less than or equal to remaining time allocated for database work.
- Read/socket timeout is long enough for query cancellation to be processed and acknowledged.
- Application deadline is the final overall cap.

For example, a 5-second query timeout and 15-second read timeout may fit a given workload; these are not universal defaults. If read timeout is shorter than query timeout, the socket can close before the driver finishes the statement cancellation handshake.

### 11.3. Do not sum timeouts mechanically

A SQL statement can involve multiple round trips, fetch multiple batches, or make internal calls. Query timeout, call timeout, and read timeout are not always three strictly sequential intervals. They can monitor overlapping wait phases simultaneously.

Measure actual driver and workload behavior instead of inferring total time merely by adding configuration numbers.

## 12. Timeouts for execute, fetch, batch, and LOBs

### 12.1. Execute query

`executeQuery()` sends SQL and receives a cursor/result. Query timeout usually applies to statement execution per the driver. Yet if the query returns many rows, fetching can add substantial duration.

### 12.2. Fetch and ResultSet

JDBC fetches in batches. `setFetchSize()` influences how many rows the driver fetches per round trip:

```java
statement.setFetchSize(200);
```

A larger fetch size can reduce round trips while increasing memory. A smaller fetch size reduces memory while increasing network latency.

Read timeout/call timeout can affect fetch calls. Enforce an application deadline covering the entire ResultSet reading and processing loop, not just `executeQuery()`.

### 12.3. Batch DML

With:

```java
statement.executeBatch();
```

query timeout and driver behavior must be tested on real batches. If a batch times out, `BatchUpdateException` may contain update counts for completed items depending on driver/database. Never assume the entire batch rolled back automatically without explicit transaction boundaries.

In manual transactions:
- Catch errors.
- Roll back the entire transaction if business rules require atomicity.
- Never commit unverified partial results.
- If the connection dropped, resolve the outcome before retrying.

### 12.4. LOBs and streaming

Reading large CLOBs/BLOBs can involve many data exchanges after query execution. Socket read timeouts can fire while reading the stream. Close streams, ResultSets, and connections properly; never hold connections longer than necessary.

For LOB streaming, test with representative payload sizes and slow networks. A short query timeout does not necessarily bound the entire time spent reading the full LOB.

### 12.5. Stored procedures

Stored procedures can execute many SQL statements and run long on the server. Query timeout applies to the JDBC call, though you must test how the driver handles calls, nested SQL, and cancellation on your exact release.

Never design an unbounded procedure and rely on client socket timeouts as workload governance. Use Resource Manager, resource limits, or server-side deadline logic.

## 13. Multi-layer configuration in Oracle JDBC

The example below illustrates an intentional configuration set. Tune values for network latency, SLAs, connection pool, and driver version.

```java
Properties properties = new Properties();
properties.setProperty("user", username);
properties.setProperty("password", passwordFromSecretProvider);

// Oracle JDBC property: milliseconds.
properties.setProperty("oracle.net.CONNECT_TIMEOUT", "3000");

// Socket read timeout: milliseconds.
properties.setProperty("oracle.jdbc.ReadTimeout", "12000");

Connection connection =
        DriverManager.getConnection(jdbcUrl, properties);

try {
    try (PreparedStatement statement =
                 connection.prepareStatement(
                     "SELECT order_id FROM app.orders WHERE status = ?")) {

        // JDBC query timeout: seconds.
        statement.setQueryTimeout(5);
        statement.setString(1, "OPEN");

        try (ResultSet resultSet = statement.executeQuery()) {
            while (resultSet.next()) {
                long orderId = resultSet.getLong(1);
            }
        }
    }
} finally {
    connection.close();
}
```

Key points:
- Connect properties apply only when creating physical connections.
- When obtaining a connection from a pool, the pool may return an already-open connection; connect timeout does not bound pool wait time.
- `ReadTimeout` is a socket-level guard and does not replace query timeout.
- `setQueryTimeout(5)` uses seconds.
- All timeout values must fit inside the application deadline.
- Connections experiencing network errors must be validated/evicted from the pool.

## 14. Timeouts and Oracle RAC/service failover

In Oracle RAC, services can relocate across instances. Active connections can be impacted when a node or instance fails.

Related mechanisms:
- **FAN (Fast Application Notification):** notifies supporting clients/middleware of service/instance events.
- **FCF (Fast Connection Failover):** helps pools evict affected connections and create new ones on surviving service instances.
- **UCP:** Oracle Universal Connection Pool supports HA capabilities and manages connections per configuration/version.
- **Application Continuity/TAC:** can replay eligible requests after outages in supported configurations and drivers.

Timeouts remain essential:
- FAN/FCF helps detect events and manage the connection pool.
- Connect timeout limits time spent opening new connections.
- Query timeout limits statements.
- Read timeout limits socket waits.
- Application deadline caps the entire request.

Failover does not guarantee a transaction did not commit. If response is lost around COMMIT, determine the outcome via Transaction Guard or proper idempotency design before retrying business operations.

## 15. Managing timeouts and cancellation with connection pools

Timeouts are state that can exist at multiple levels. Because connection pools reuse connections, state resetting must be managed.

### 15.1. State that must be reset

If an application modifies on a connection:
- Call timeout.
- Network timeout.
- Read timeout if the driver allows runtime changes.
- Auto-commit.
- Transaction isolation.
- Read-only mode.
- Schema/catalog.
- Client identifier, module/action.
- Application context.
- NLS/session settings.

Use a pool reset callback or centralized wrapper instead of letting individual repositories mutate settings arbitrarily.

### 15.2. Broken connections must be evicted

When encountering fatal socket or connection errors:
- Mark the connection broken.
- Do not return it to the idle pool.
- Close/discard per pool APIs.
- Open a fresh connection on subsequent requests.
- Emit metrics for validation failures and connection evictions.

A query timeout error may not break the connection in every case; classify based on exception/driver state. Never flush the entire pool over a single statement timeout.

### 15.3. Never hold connections while waiting to retry

If retries are permitted:
1. Finish/roll back the transaction based on determined state.
2. Close statements/result sets.
3. Return healthy connections or discard broken ones.
4. Perform backoff outside any held connection.
5. Acquire a fresh connection for the next attempt.

Never hold a connection while sleeping or waiting on another service.

## 16. Classifying exceptions and taking appropriate action

| Scenario | Example signal | Action |
|---|---|---|
| Pool exhausted | Pool acquisition timeout | Inspect pool usage/leaks/slow SQL; do not hammer retries |
| Connect timeout | `ORA-12170`, socket connect timeout | Check network/listener; bounded retry if transient |
| Wrong service | `ORA-12514` | Fix service name/registration; do not retry infinitely |
| Wrong credentials | `ORA-01017` | Stop retrying, fix secrets/account |
| Read timeout | Socket read timed out | Discard connection if unreliable; check server/query |
| Query timeout | `SQLTimeoutException`, possibly `ORA-01013` | Stop operation, handle transaction |
| User cancel | `ORA-01013` or cancellation exception | Respect cancel request, do not auto-retry |
| Connection reset | `ORA-03113`, `ORA-03114`, `ORA-03135` | Discard connection; resolve transaction outcome |
| Deadlock | `ORA-00060` | Roll back full business transaction, then bounded retry if safe |
| Serialization conflict | `ORA-08177` | Roll back and retry whole transaction when business rules permit |

Never rely on error code alone. Inspect the exception chain, SQLState, vendor code, transaction phase, and driver version.

### 16.1. Distinguishing timeout from cancellation

A timeout is the reason the system decides to stop waiting or stop an operation. Cancellation is the action asking a statement to stop.

A socket-layer timeout may be unable to send a cancel request if the socket is already broken. A JDBC query timeout gives the driver an opportunity to send a cancel. Thus the two concepts are related, not synonymous.

### 16.2. Distinguishing retryable from non-retryable errors

Candidates for retry:
- Transient connect failures.
- Certain outage/failover errors.
- Deadlocks after rolling back the full transaction.
- Serialization conflicts after rolling back.

Do not retry in the same way:
- Invalid credentials.
- Invalid service names.
- SQL syntax errors.
- Insufficient privileges.
- Business constraint violations.
- User-initiated cancellations.
- Requests past their deadline.

## 17. Cancelling statements when users cancel HTTP requests

In web applications, users may leave a page or gateways may abort requests. Applications should propagate cancellation signals from the HTTP layer down to JDBC.

A general design:
1. Give each request a deadline and cancellation token.
2. Have JDBC operations register the running statement with the request context.
3. When the request is cancelled, the cancellation handler calls `Statement.cancel()`.
4. Close ResultSet/Statement.
5. Roll back if the business transaction was cancelled and the connection remains usable.
6. Return or discard the connection based on state.
7. Log cancellation reason and duration.

Never leave request-handling threads blocked indefinitely because a JDBC call lacks timeouts.

### 17.1. Avoid using Thread.interrupt instead of JDBC cancel

Interrupting a thread does not guarantee a database statement stops. Some frameworks/drivers react to interrupts, yet explicit supported cancellation APIs are required. Use `Statement.cancel()` or your framework/driver's cancellation mechanism and test against Oracle JDBC.

### 17.2. Never cancel shared operations

If a `Statement` or `Connection` were shared across multiple requests, calling cancel could disrupt another request by mistake. JDBC connections/statements must never be used concurrently by multiple business requests in unsupported ways.

Each request/transaction must own its connection and statements clearly.

## 18. Limiting queries on the database side

Client timeouts protect requests and connections, but the database also needs workload governance.

Consider:
- Oracle Database Resource Manager to cap CPU, parallelism, or execution time per consumer group.
- Dedicated services for reporting/batch workloads.
- User profiles/resource limits where appropriate.
- SQL plan management and tuning for slow queries.
- Concurrency caps at the application/pool layer.
- SQL Monitor/tracing subject to privileges and licensing.

Never rely on client timeouts as the sole defense against runaway queries. If the client stops waiting while the server keeps running, the database still burns CPU, I/O, PGA, and locks.

## 19. Measuring and monitoring timeouts

Logs should capture enough metadata for investigation:
- Request/correlation ID.
- Database service and application module/action.
- Pool name.
- Which timeout fired.
- Applied timeout configuration.
- Start/end timestamps.
- SQL_ID if obtainable.
- Oracle vendor error code and SQLState.
- Transaction phase: pool, connect, execute, fetch, commit.
- Whether the connection was retained, returned, or discarded.
- Whether cancel/rollback occurred.
- Retry attempt count and remaining deadline budget.

Never log passwords, tokens, full bind values, or sensitive business data.

### 19.1. Metrics to monitor

| Metric | Meaning |
|---|---|
| Pool acquisition latency | Wait time to borrow a connection |
| Physical connect latency | Time to open a new connection |
| Connect timeout count | Count of connection failures on timeout |
| Socket read timeout count | Count of socket read timeouts |
| Query timeout count | Count of statements exceeding limit |
| Cancel success/failure | Outcome of cancel requests |
| Connection eviction count | Count of discarded connections |
| Statement execution latency | SQL execution time distribution |
| ResultSet fetch latency | Data reading duration |
| Request deadline exceeded | Requests exhausting overall budget |
| Pool active/idle/pending | Connection pool pressure |

Track p50, p95, and p99, not averages alone. A small number of very slow queries can heavily skew tail latency.

### 19.2. Correlating client and database

When a timeout occurs:
- Record synchronized timestamps.
- Record service/module/action.
- Record SQL_ID if available.
- Check whether the database session is still running.
- Inspect alert logs, listener logs, and wait events.
- Check whether the session was cancelled or only lost client connectivity.
- Determine whether the transaction committed.

If privileges and licensing permit, use Oracle monitoring tools to investigate; never enable broad tracing or bind logging without evaluating sensitive data exposure.

## 20. Testing timeouts in a lab environment

Never test by hanging production or killing shared instances. Use a lab schema/database and SQL with controlled runtime.

### Step 1. Verify driver and datasource

Record:
- Oracle Database version.
- Oracle JDBC driver version.
- Thin/OCI driver.
- Pool implementation/version.
- Service name.
- Configured timeouts and units.

### Step 2. Test pool acquisition timeout

Limit the lab pool to one connection. Hold the first connection, then have a second request call `getConnection()`. Confirm the second request times out waiting on the pool as configured.

### Step 3. Test connect timeout

Use an unresponsive lab endpoint or a port blocked cleanly by a firewall. Confirm physical connection creation is bounded. Never use production hostnames/services for failure tests.

### Step 4. Test query timeout

Pick a lab query with known long runtime or a DBA-approved test procedure. Set:

```java
statement.setQueryTimeout(2);
```

Confirm the driver throws a timeout/cancel exception and observe whether the database session stops the operation.

### Step 5. Test read timeout

In an isolated environment, configure `oracle.jdbc.ReadTimeout` lower than a test operation's response delay. Confirm socket read timeout, connection state, and pool eviction behavior.

### Step 6. Test Statement.cancel()

Run a query on one thread, then have a control thread call `statement.cancel()`. Confirm the exception and measure how fast the server halts the operation.

### Step 7. Test fetching

Use a result set large enough to trigger multiple fetch round trips. Measure execute time separately from the `ResultSet.next()` loop time.

### Step 8. Test transactions

In the lab, execute DML and then cancel a subsequent statement. Confirm uncommitted changes remain in the transaction and verify rollback behavior. Never assume cancelling a statement rolled back earlier DML.

### Step 9. Test connection pool recovery

After each failure mode, verify whether the connection is retained or discarded. Confirm the next request receives a healthy connection.

### Step 10. Record results

Document actual timeout durations, server stop time, exceptions, connection states, transaction outcomes, and impact on subsequent requests.

## 21. Example timeout profiles by workload

The values below are illustrative starting points requiring benchmarking and tuning.

| Workload | Pool wait | Connect | Query | Read/socket | Notes |
|---|---:|---:|---:|---:|---|
| Short OLTP API | 1 s | 3 s | 3 s | 10 s | Tight request deadline, few rows |
| Small reporting API | 2 s | 3 s | 8 s | 15 s | Control fetch and row count |
| Batch ETL | 5 s | 5 s | 120 s | 180 s | Job deadline and checkpoints |
| Admin operation | Per change window | Per environment | Per operation | Per network | With approval and monitoring |

Do not copy this table as a universal default. A 60-second report may be valid; a payment API may need under 2 seconds. Timeouts must reflect SLAs and real behavior.

## 22. Common design mistakes

| Anti-pattern | Consequence | Fix |
|---|---|---|
| Setting only query timeout | Requests can still hang waiting on pool/connect | Set timeouts at every layer |
| Confusing pool timeout with connect timeout | Unbounded physical connection creation | Configure both pool and driver |
| Relying only on read timeout | Client stops reading while SQL keeps running | Use query/call timeout and cancellation |
| Setting read timeout shorter than query timeout | Socket can break before cancel completes | Coordinate timeouts and test |
| Using `setQueryTimeout(5000)` for 5 seconds | Actually sets 5,000 seconds | Remember the unit is seconds |
| Assuming timeout rolls back transactions | Earlier DML may stay in transaction | Roll back explicitly when possible |
| Reusing every connection after `cancel()` | Connection may be out of sync | Check and discard if needed |
| Immediately retrying after timeout around COMMIT | Risk of duplicate transactions | Resolve outcome/idempotency |
| Holding connections while waiting to retry | Exhausts pool | Release before backoff |
| Setting only HTTP timeout | Database query keeps running | Propagate cancellation to JDBC |
| Creating unclosed executors per request | Thread leak | Manage executors at application lifecycle |
| Changing global login timeout carelessly | Affects other datasources | Configure per datasource/driver |
| Enlarging pool to stop timeouts | Can overload database further | Investigate leaks, queries, and concurrency |
| Failing to reset call/network timeout | Next request inherits stale state | Reset connection before returning to pool |

## 23. Implementation checklist

### Connectivity
- Pool acquisition timeout configured.
- Connect timeout bounds physical connections.
- DNS/listener/service and TLS have reasonable wait limits.
- Connection retries are bounded.
- Broken connections are evicted from the pool.

### SQL execution
- Query timeout set before execute.
- Unit of seconds verified.
- Read timeout acts as an appropriate safety net.
- Call timeout considered for supporting Oracle drivers.
- Fetch/LOB/batch tested separately.
- Application deadline covers both execute and fetch.

### Cancellation and transactions
- Mechanism exists to receive cancellation signals.
- `Statement.cancel()` targets the right statement/request.
- Cancel failures handled cleanly.
- Transaction rolled back when business operations cancel and state permits.
- Indeterminate commit outcomes handled safely.
- Broken connections never reused.

### Pooling and operations
- Timeouts/session state reset.
- Executors used for network timeouts have clear lifecycles.
- Metrics and alerts cover each timeout layer.
- Runbooks cover local and remote database investigation.
- Fault-injection tests run in lab environments.

## 24. Self-check questions

**Question 1.** What does connect timeout control?

**Answer:** Time to establish a physical connection to the endpoint/listener/service per driver and Oracle Net mechanics.

**Question 2.** How does pool acquisition timeout differ from connect timeout?

**Answer:** Pool timeout is wait time for a free connection in the pool; connect timeout applies when opening a new physical connection.

**Question 3.** What is `oracle.jdbc.ReadTimeout` used for?

**Answer:** Bounds socket read wait time in milliseconds in supporting Oracle JDBC Thin Drivers.

**Question 4.** Does read timeout guarantee the server stops SQL?

**Answer:** No. It limits client socket waiting; the server-side statement may keep running if it has not received or processed a cancel request.

**Question 5.** What unit does `Statement.setQueryTimeout()` use?

**Answer:** Seconds. A value of 0 means no limit per the JDBC API.

**Question 6.** Does query timeout include pool wait time?

**Answer:** No. Pool acquisition happens before the statement is created/executed.

**Question 7.** What does `OracleConnection.setCallTimeout()` limit?

**Answer:** Duration of a single database round trip, not necessarily the total time of a multi-round-trip request.

**Question 8.** What does `Connection.setNetworkTimeout()` do?

**Answer:** Bounds how long a JDBC request waits for a database response at the connection level; exceeding it can abort the connection.

**Question 9.** Is `Statement.cancel()` a rollback?

**Answer:** No. It requests cancellation of the current statement; the transaction may still hold uncommitted changes from earlier statements.

**Question 10.** What does ORA-01013 usually mean?

**Answer:** An operation was requested to cancel, e.g., by user action, query timeout, or administrative action.

**Question 11.** Why should a connection not be reused after a socket read timeout?

**Answer:** The connection may be out of sync or invalid; the pool must discard it when marked broken.

**Question 12.** Why doesn't query timeout always bound the entire ResultSet reading duration?

**Answer:** Execution and fetching can be separate phases/round trips; read/call timeouts and application deadlines are needed for the fetch phase.

**Question 13.** What should be done when a user cancels an HTTP request?

**Answer:** Propagate the cancellation signal to JDBC, call statement cancel, close resources, and handle the transaction/connection based on state.

**Question 14.** What if a timeout happens around COMMIT?

**Answer:** The client may not know whether the transaction committed; resolve the outcome with an appropriate mechanism or idempotency.

**Question 15.** Why reset timeouts when using a connection pool?

**Answer:** Timeouts are connection state; subsequent requests may inherit the previous request's settings if not reset.

**Question 16.** Should client-side timeouts be the only protection for the database?

**Answer:** No. Resource Manager, workload governance, concurrency caps, and server-side tuning are also required.

## 25. Conclusion

Connect timeout, read timeout, query timeout, and cancellation govern distinct stages of an Oracle JDBC request lifecycle. Pool acquisition timeout bounds waiting for a free connection; connect timeout bounds creating physical connections; read/socket timeout bounds waiting on network reads; query timeout bounds statements under JDBC; call timeout bounds a single database round trip in Oracle JDBC; application deadlines govern the entire request.

`Statement.cancel()` requests cancellation of a running operation, whereas `rollback()` undoes uncommitted transaction changes and `Connection.abort()` destroys the connection. Never treat these three actions as equivalent. A read timeout can stop the client from waiting without proving the server halted SQL. Query timeout also does not automatically roll back earlier changes in the transaction. If response is lost around COMMIT, the outcome can be ambiguous and must be resolved before retrying business logic.

A reliable setup coordinates timeouts across the pool, Oracle Net, JDBC driver, statements, and application deadline; tests execute, fetch, batch, and LOBs; evicts broken connections from the pool; resets connection state upon reuse; and propagates cancellation from requests to JDBC. Monitor latency and timeout counts separately per layer to distinguish pool exhaustion, network issues, slow SQL, and server failures. Only after testing on your exact Oracle JDBC driver and representative workloads do timeouts become protective guardrails rather than hard-to-diagnose failure sources.
