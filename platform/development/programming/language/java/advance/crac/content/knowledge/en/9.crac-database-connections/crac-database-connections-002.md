# Closing Connections Before Checkpoint and Re-validating After Restore

A database connection is a live resource outside the Java process. A JDBC `Connection` is not just an object in the heap: it typically represents a session on the database server, a network socket, driver protocol state, and potentially an open transaction. When the process is checkpointed and then restored at a different time, that connection session may have already been closed by the server, the network may have changed, or the transaction may no longer be valid.

Therefore, a CRaC application should proactively bring the data access layer to a safe state before checkpoint: stop accepting new work, wait for in-flight operations to complete, commit or roll back transactions, close connections, and close the connection pool according to the library's guidelines. After restore, the application needs to retrieve valid credentials again, create a new pool, verify the actual connection to the database, and only then allow repositories, workers, and requests to use it.

The key point is that a checkpoint image only saves process state within the scope supported by the mechanism. It does not freeze the database server, does not preserve remote transactions, and does not guarantee that JDBC sockets remain usable after restore. The application must design an explicit connection lifecycle on both the checkpoint and restore sides.

## 1. Why should JDBC connections not be kept across a checkpoint?

A JDBC connection typically includes multiple layers of state:

- The `Connection` object and driver state residing in the JVM heap.
- TCP sockets or operating system resources used to exchange data with the database.
- The session managed by the database server.
- Transaction state, locks, cursors, prepared statements, and result sets.
- Connection lifetime, timeouts, keepalive, TLS sessions, and authentication credentials.

Checkpoint can save the state of Java objects and part of the process state, but the database server continues operating independently. While the image is stored, the server may time out the session, restart, fail over, change the primary node, or terminate the transaction. The network may also change addresses, routes, or socket states.

After restore, the old `Connection` object may still exist in the heap but no longer represent a usable database session. A subsequent SQL command may encounter errors such as:

- Connection is already closed.
- Socket reset or broken pipe.
- Read timeout or connection timeout.
- Session no longer exists on the database.
- Transaction has been rolled back or timed out.
- TLS or authentication credentials are no longer valid.

Therefore, you should not rely on the `Connection` object still being non-`null` to conclude that the connection is still active. Connections must be closed before checkpoint and new connections created after restore.

## 2. Preparing the database layer before checkpoint

Before closing the pool, the application needs to prevent components from continuing to use the database. If you only call `close()` on the connection pool while workers are still processing requests, in-flight operations may fail mid-way.

A preparation procedure can include:

1. Stop accepting new requests or messages in components that require the database.
2. Pause schedulers, consumers, and workers that may issue queries.
3. Wait for in-flight requests and tasks to complete within a bounded timeout.
4. Confirm that transactions have committed or rolled back.
5. Close any remaining open `ResultSet`, `Statement`, `EntityManager`, or session according to proper ownership.
6. Close the connection pool to release connections and sockets.
7. Proceed with checkpoint only when the database state in the process is safe.

### 2.1. Stopping new work and draining in-flight work

A Spring Boot application may have multiple sources generating queries: HTTP controllers, message listeners, schedulers, batch jobs, and background executors. All of these sources need to be put into a paused state before closing the pool.

For example, an order-processing worker might be executing three steps:

1. Reading the order from the database.
2. Calling the payment service.
3. Updating the order status.

If a checkpoint occurs between step 2 and step 3, the process may be restored with an in-memory state that does not accurately reflect the external payment result. Therefore, it is necessary to wait for the task to complete or bring it to a safe business boundary before checkpoint.

The drain time should be bounded. If the deadline expires while requests or transactions are still active, the appropriate policy is usually to abort the checkpoint and resume serving after restoring the active state. You should not close a pool that is still in use just to force creating an image.

### 2.2. Completing transactions explicitly

Open transactions should not be left active at the time of checkpoint. Complete or roll them back according to business policy before closing the connection.

With manual JDBC:

```java
try (Connection connection = dataSource.getConnection()) {
    connection.setAutoCommit(false);
    try {
        updateOrder(connection, orderId);
        insertAuditRecord(connection, orderId);
        connection.commit();
    } catch (Exception failure) {
        connection.rollback();
        throw failure;
    }
}
```

`try-with-resources` ensures the connection is closed after the processing block finishes. In the example, the transaction is committed when both operations succeed and rolled back on error. A real-world application also needs to handle rollback errors, close errors, and driver exceptions according to its policy.

With Spring transaction management, let the transaction boundary finish before the checkpoint callback closes the pool. Do not manually close a connection managed by the transaction manager from an independent callback, as doing so can corrupt the running transaction.

Closing a connection is not a substitute for determining whether a transaction committed or rolled back. If a request has already sent a side effect to an external service and then fails when updating the database, the application still needs an idempotency key, outbox, or an appropriate reconciliation mechanism.

## 3. Connection pools must be managed as a resource

In a server application, you do not normally create a new JDBC connection for each component and keep it forever. Instead, the application uses a connection pool such as HikariCP to reuse connections and limit the number of concurrent connections.

A pool manages more than just a `DataSource` variable:

- A set of JDBC connections.
- Sockets currently connected to the database.
- Background threads to check or manage connections.
- Timeouts, keepalive, and validation.
- Connection wait queues and shutdown state.

Therefore, before checkpoint, the pool must be closed using the library's API. After restore, it is usually necessary to create a new pool from the current configuration. You should not assume that a pool that has been `close()`d can be reopened by calling `getConnection()`.

For example, with HikariCP, `HikariDataSource.close()` closes the pool. When it needs to operate again, create a new `HikariDataSource` instance instead of trying to reuse the closed instance.

## 4. Verifying connections after restore

After restore, recreating the pool object does not prove that the database is reachable. The application must verify actual connectivity and necessary conditions before accepting traffic.

A verification procedure should include:

1. Re-fetching the endpoint and authentication credentials according to the current configuration.
2. Creating a new connection pool.
3. Attempting to obtain a connection from the pool.
4. Checking that the connection is active using the JDBC API or an appropriate validation query.
5. Confirming that the required database/schema is accessible and the necessary permissions are valid.
6. Allowing repositories, workers, and requests to resume operation only after the checks succeed.

### 4.1. Using JDBC `Connection.isValid`

JDBC provides `Connection.isValid(int timeout)` to check whether a connection is still valid. For example:

```java
try (Connection connection = dataSource.getConnection()) {
    if (!connection.isValid(5)) {
        throw new SQLException("Database connection is not valid");
    }
}
```

The parameter `5` is the timeout in seconds according to the JDBC contract. The driver must support this method; if the driver has limitations or its own validation mechanism, read the driver documentation.

Some systems choose to run a lightweight query such as `SELECT 1`. This approach can additionally confirm that the database can execute a statement, but the syntax and execution permissions must match the database type. Do not use a query with side effects as a health check.

### 4.2. Checking the pool is not equivalent to checking the entire application

A pool may connect successfully while another dependency is still not ready: schema migration has not finished, credentials only have connect permission but not query permission, the database is in read-only state, or message consumers have not re-registered.

Application readiness should reflect the dependencies actually required for traffic. You can separate:

- **Liveness:** the JVM process is still running and not severely stuck.
- **Readiness:** the database and required dependencies are ready to handle requests.
- **Startup/restore status:** the application is in the post-restore recovery phase.

Do not report readiness as successful just because the `afterRestore` callback has started or the pool object has been created.

## 5. Integrating with CRaC Resource

CRaC provides `org.crac.Resource` for the application to handle resources at two points:

- `beforeCheckpoint(...)`: stop operations using the database, complete in-flight work, and close the pool before creating the image.
- `afterRestore(...)`: create a new pool, verify the connection, and reopen dependent components.

The example below illustrates how to manage a HikariCP pool through a holder. Repositories obtain connections through the holder each time they perform work, so they can use the new pool instance after restore.

```java
import com.zaxxer.hikari.HikariDataSource;

import java.sql.Connection;
import java.sql.SQLException;
import java.util.concurrent.atomic.AtomicReference;

public final class DatabasePoolHolder {

    private final AtomicReference<HikariDataSource> current =
            new AtomicReference<>();

    public Connection getConnection() throws SQLException {
        HikariDataSource pool = current.get();
        if (pool == null) {
            throw new SQLException("Database pool is not ready");
        }
        return pool.getConnection();
    }

    public void install(HikariDataSource pool) {
        if (!current.compareAndSet(null, pool)) {
            throw new IllegalStateException("Database pool is already installed");
        }
    }

    public void closeCurrent() {
        HikariDataSource previous = current.getAndSet(null);
        if (previous != null) {
            previous.close();
        }
    }
}
```

Resource coordinating the traffic gate, pool holder, and factory:

```java
import com.zaxxer.hikari.HikariDataSource;
import org.crac.Context;
import org.crac.Resource;

import java.sql.Connection;
import java.sql.SQLException;
import java.time.Duration;

public final class DatabaseCracResource implements Resource {

    private final TrafficGate trafficGate;
    private final DatabasePoolHolder poolHolder;
    private final DatabasePoolFactory poolFactory;

    public DatabaseCracResource(
            TrafficGate trafficGate,
            DatabasePoolHolder poolHolder,
            DatabasePoolFactory poolFactory) {
        this.trafficGate = trafficGate;
        this.poolHolder = poolHolder;
        this.poolFactory = poolFactory;
    }

    @Override
    public void beforeCheckpoint(Context<? extends Resource> context)
            throws Exception {
        // Stop new work and wait for running transactions/requests to finish.
        trafficGate.pauseAndDrain(Duration.ofSeconds(30));

        // Only close the pool after no components are using it.
        poolHolder.closeCurrent();
    }

    @Override
    public void afterRestore(Context<? extends Resource> context)
            throws Exception {
        // Factory retrieves current configuration and credentials, then creates a new pool.
        HikariDataSource restoredPool = poolFactory.create();

        boolean installed = false;
        try {
            try (Connection connection = restoredPool.getConnection()) {
                if (!connection.isValid(5)) {
                    throw new SQLException(
                            "Database connection validation failed");
                }
            }

            poolHolder.install(restoredPool);
            installed = true;
            trafficGate.resume();
        } catch (Exception failure) {
            try {
                if (installed) {
                    poolHolder.closeCurrent();
                } else {
                    restoredPool.close();
                }
            } catch (Exception cleanupFailure) {
                failure.addSuppressed(cleanupFailure);
            }
            throw failure;
        }
    }
}
```

The dependent interfaces in the example can be defined according to the application:

```java
import com.zaxxer.hikari.HikariDataSource;
import java.time.Duration;

public interface TrafficGate {
    void pauseAndDrain(Duration timeout) throws Exception;
    void resume() throws Exception;
}

public interface DatabasePoolFactory {
    HikariDataSource create() throws Exception;
}
```

`DatabasePoolFactory.create()` should retrieve the current endpoint and credentials from an appropriate configuration/secret source, rather than simply reusing short-lived credentials that were already in the heap before checkpoint. In a real-world application, `TrafficGate` needs to coordinate HTTP requests, message consumers, schedulers, and executors that may use the database.

The example is an illustrative skeleton, not a complete Spring Boot configuration. You need to register `DatabaseCracResource` once in the appropriate CRaC context, ensure repositories use `DatabasePoolHolder`, and define how to recover if `pauseAndDrain` or closing the pool fails. If the checkpoint fails after traffic has been paused, the application needs a policy to bring traffic back or transition the instance into a controlled error state.

## 6. Managing transactions and connections across frameworks

### 6.1. Plain JDBC

With plain JDBC, each operation should have clear ownership. Use `try-with-resources` for `Connection`, `PreparedStatement`, and `ResultSet`. Do not store connections in static fields or long-lived singletons unless there is a dedicated lifecycle management layer.

Example:

```java
String sql = "SELECT status FROM orders WHERE id = ?";

try (Connection connection = poolHolder.getConnection();
     PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setLong(1, orderId);

    try (ResultSet resultSet = statement.executeQuery()) {
        if (resultSet.next()) {
            return resultSet.getString("status");
        }
    }
}
```

The connection is returned to the pool when closed, and the statement and result set are also closed. When the pool is replaced after restore, the next call through the holder will receive a connection from the new pool.

### 6.2. Spring transaction management

In Spring, `DataSourceTransactionManager`, `JpaTransactionManager`, or the corresponding transaction manager manages connections/sessions according to transaction boundaries. A checkpoint callback should not arbitrarily take a connection held by the transaction manager and close it from another thread.

Ensure that:

- No transactions are still running before closing the pool.
- `@Transactional` methods have finished on their executing threads.
- Message listeners and schedulers have stopped accepting new work.
- `EntityManager`/Session and persistence contexts are not retained across restore if they depend on old connections.
- The `DataSource` is replaced or reinitialized according to the lifecycle used by Spring beans.

If `DataSource` is injected directly into multiple beans, changing a field elsewhere does not automatically update the references held by those beans. You can use a delegating/routing `DataSource` whose target can be swapped, or a holder/proxy designed so that every repository always accesses the current pool. Ensure the old target is closed and the new target is verified before traffic is reopened.

### 6.3. JPA/Hibernate

Do not keep an `EntityManager`, Hibernate `Session`, JDBC `Statement`, or `ResultSet` across a checkpoint as an active unit of work. These objects may hold transactions, cursors, connections, or persistence context state tied to the old session.

Finish transactions before checkpoint, close manually scoped sessions, and let the framework create a new persistence context for work after restore. Once the new pool is ready, test an actual repository operation through the path the application will use.

## 7. Credentials, DNS, and changing conditions upon restore

New connections after restore may require different information than when the image was created. For example:

- The database password was rotated.
- The database access token or secret lease expired.
- DNS points to a new address after failover.
- The database endpoint switched primary or changed proxy.
- TLS certificates were updated.
- Network routes or firewall policies changed.
- The database just restarted and needs time to accept connections.

Therefore, the pool factory should read configurable values that may change at restore time. You should not store passwords, short-lived tokens, or resolved IP addresses in an object that existed before checkpoint and assume they are still valid.

When multiple instances restore simultaneously, avoid having all pools create too many connections at the same time. Calculate the database's total connection budget, limit `maximumPoolSize`, and consider staggered startup or retry with backoff to avoid creating a sudden burst of connections.

## 8. Retry and handling when the database is not ready

The database may not accept connections immediately after the application restores. This can be due to failover, restart, DNS propagation, or connection limits. The application needs to distinguish between transient errors and configuration errors.

A reasonable policy can include:

1. Attempt to connect with a finite timeout.
2. For recoverable errors, retry a limited number of times with exponential backoff and jitter.
3. Bound the total restore wait time so the instance is not kept in an indefinite hanging state.
4. For invalid credential or configuration errors, log clearly and keep readiness failing instead of retrying continuously.
5. Resume traffic only after the pool and required verification operations succeed.

Do not retry every exception with the same short interval. Doing so can put heavier load on a database experiencing issues. Classify errors by SQLState, vendor code, or driver exception and set appropriate limits.

## 9. Testing the database lifecycle across checkpoint–restore

A good test must prove that old connections are closed, a new pool is created, and the application can actually query the database after restore.

You can test in the following sequence:

1. Start the application and confirm the initial pool works.
2. Execute a verification query and record the connection/pool state.
3. Generate light load to confirm the traffic gate can drain requests.
4. Request a checkpoint; confirm workers have stopped and the old pool is closed.
5. Restore the image on a compatible environment.
6. Confirm `afterRestore` creates a new pool.
7. Check `Connection.isValid` or a lightweight query.
8. Call an actual repository and confirm the correct result.
9. Confirm traffic is only resumed after database readiness succeeds.
10. Test when the database is unavailable, credentials are expired, or pool creation fails; confirm the instance does not accept traffic.

The following metrics should be collected:

| Metric | Meaning |
|---|---|
| Connections before checkpoint | Confirms the pool has managed connections |
| Open transactions | Detects work that has not reached a safe boundary |
| Drain duration | Measures time waiting for requests/workers to finish |
| Pool close duration | Measures cost of releasing connections |
| Pool creation duration after restore | Measures cost of re-establishing database access |
| Validation/query result | Confirms the connection is actually usable |
| Restore to readiness | Measures time until the instance can serve traffic |
| Retry count and error types | Diagnoses database or network unavailability |

Do not just check the “pool created” log. A pool object may be created without being able to open a connection yet. Perform actual validation or a real query before transitioning readiness.

## 10. Common pitfalls

**Keeping JDBC connections across checkpoint.** A Java object still existing does not mean the database session and socket are still valid. Close connections before checkpoint and create new connections after restore.

**Closing the pool while requests are still running.** Requests may fail mid-transaction or while using a statement. Stop accepting new work and drain work before closing the pool.

**Only calling `Connection.close()` without closing the pool.** The connection pool still has threads, sockets, and other connections. Call the pool's shutdown API according to the library's guidelines.

**Trying to reuse a closed pool.** Some pools such as HikariCP are not designed to be reopened after `close()`. Create a new pool instance and switch repositories to the new target.

**Checkpointing while a transaction is open.** The transaction may time out or be rolled back while the image is stored. Commit or roll back before checkpoint.

**Reusing old credentials after restore.** Tokens or passwords may have expired or been rotated. Fetch current credentials when creating the new pool.

**Marking readiness as soon as the pool object is created.** Only report ready after obtaining a connection and verifying the database succeeds.

**Retrying without limits.** Continuous retries can overload the database. Use timeouts, backoff, jitter, and error classification.

**Letting multiple restored instances create too many concurrent connections.** Calculate the connection budget, limit pool size, and throttle startup to avoid exceeding database limits.

**Using FD policies instead of database lifecycle management.** `jdk.crac.resource-policies` can assist with certain FDs within the runtime's scope, but it does not handle transactions, database sessions, or connection pool state. Manage the database via callbacks and the pool's API.

## 11. Self-check questions

1. **Why should JDBC connections not be kept across a checkpoint?** Because sessions and sockets belong to external systems and may become invalid while the process is stored; a `Connection` object remaining in the heap does not guarantee the connection is still usable.
2. **What needs to be done before closing the connection pool?** Stop accepting new work, drain requests/workers, complete or roll back transactions, and close statements/sessions under your ownership.
3. **Should a closed pool be reused after restore?** Usually, a new pool must be created according to the library's API, such as creating a new `HikariDataSource` instance.
4. **What does `Connection.isValid(5)` verify?** It asks the JDBC driver to check whether the connection is still valid within the specified maximum timeout; you still need to verify permissions and business operations that the application depends on.
5. **When should readiness transition to successful?** After the new pool is created, a connection is obtained, required validation/queries succeed, and dependent components have recovered.
6. **Why does the pool factory need to fetch current credentials?** Because secrets, tokens, or endpoints may change or expire while the checkpoint image is stored.
7. **Why must the pool not be closed while transactions are still running?** Because requests may fail mid-way, hold locks, or create inconsistent business state.

## Conclusion

Database connections are resources tied to both the process and external systems. Before checkpoint, stop new work, drain in-flight requests, complete transactions, and close the connection pool. After restore, fetch current configuration and credentials, create a new pool, verify actual connectivity, and only then allow repositories, workers, and traffic to resume operation.

In a CRaC application, place the database lifecycle into a `Resource` or an appropriate coordinator, ensuring dependent components are stopped before the pool and only reopened after the pool is ready. Test both success cases and database/credential unavailability so that readiness always accurately reflects the instance's ability to serve.
