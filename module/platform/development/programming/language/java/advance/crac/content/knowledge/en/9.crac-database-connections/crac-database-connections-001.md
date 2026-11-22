# DataSource Lifecycle Management and JDBC Connection Pools

In a Java application, DataSource is the standard entry point for obtaining a JDBC connection. In real-world environments, DataSource is usually provided by a connection pool such as HikariCP, Apache Commons DBCP, or a pool managed by an application server. The pool holds physical connections to the database, manages timeouts, reuses connections, and runs background tasks to validate or evict connections.

When using CRaC (Coordinated Restore at Checkpoint), the lifecycle of the DataSource and connection pool needs to be coordinated with checkpoint/restore. An open Connection is typically tied to a socket, transaction state, driver, and native resources of the process. These connections may no longer be valid after the process is restored. A common approach is to stop accepting new work, complete transactions, return connections to the pool, close the pool before checkpoint, and then create a new pool after restore.

## 1. DataSource, Connection, and Connection Pool

JDBC defines DataSource in the javax.sql package. DataSource is a factory that provides Connection; it decouples application code from how connections are specifically created.

~~~java
DataSource dataSource = obtainDataSource();

try (Connection connection = dataSource.getConnection()) {
    // Execute JDBC query.
}
~~~

A connection pool implements DataSource and maintains a set of physical connections for reuse. When the application calls getConnection(), the pool typically lends an idle connection. When the application calls close() on the borrowed Connection, the connection is usually returned to the pool instead of closing the physical socket immediately.

Common components:

| Component | Role |
|---|---|
| DataSource | Standard API to obtain a Connection |
| Connection | JDBC session with the database |
| Connection pool | Manages and reuses physical connections |
| JDBC Driver | Communicates with the database via the corresponding protocol |
| PreparedStatement | Executes parameterized SQL statements |
| ResultSet | Reads query results |
| Transaction | Group of operations that need to be committed or rolled back consistently |

### DataSource does not mean pool

DataSource is a standard interface; it does not specify that every DataSource has a pool or a shutdown method. The DataSource interface does not define close().

A specific pool may have its own closing API. For example, HikariDataSource provides close(); Apache Commons DBCP BasicDataSource also has its own lifecycle methods. When managing the lifecycle, it is necessary to keep a reference to the specific pool object or use an abstraction with an explicit close method. Do not cast every DataSource to AutoCloseable without knowing the implementation.

### Connection.close() is different from pool.close()

These two calls have different meanings:

- Connection.close(): ends the use of the current connection; with a pool, usually returns the connection to the pool.
- Pool.close(): stops the pool, releasing physical connections and internal resources according to the implementation.

Do not call pool.close() after every request. The pool is created and closed according to the lifecycle of the application or a service component.

## 2. Normal Lifecycle of a JDBC Pool

An application can create the pool at startup, use the pool throughout its serving lifetime, and close the pool at shutdown.

~~~text
Application starts
        |
        v
Read JDBC configuration
        |
        v
Create DataSource / connection pool
        |
        v
Receive request and obtain Connection
        |
        v
Execute transaction
        |
        v
Connection.close() returns connection to pool
        |
        v
Application shuts down
        |
        v
Close connection pool
~~~

During a normal cycle, the pool can maintain idle connections, create new connections when load increases, and evict expired connections. Pools may also run housekeeper, validation, or eviction tasks on background threads.

In CRaC, a checkpoint is not the same as a normal shutdown. The application will resume from the checkpoint image at a different point in time. Therefore, the pool must be prepared so that sockets, background threads, and connection states are not reused under conditions that are no longer appropriate.

## 3. Why Close the Pool Before Checkpoint?

An open JDBC Connection is typically tied to:

- A TCP socket to the database or proxy.
- A session and transaction on the database side.
- Protocol state in the JDBC driver.
- Buffers and native resources.
- Background threads of the pool to validate or manage connections.
- Credentials, tokens, or authentication information used when opening the connection.

While the application is checkpointed, the database may time out the session, a proxy may close the socket, the network route may change, or credentials may be rotated. Upon restore, a Connection that still exists in the heap is not guaranteed to still be usable on the database side.

Therefore, a connection borrowed from the pool should not be treated as a resource that can continue to be used safely after restore. The application needs to complete transactions and release connections before checkpoint, then close the pool so that the runtime does not have to restore sockets or background threads tied to the old pool.

A common workflow:

~~~text
Stop accepting new requests
        |
        v
Wait for in-flight requests to complete
        |
        v
Commit / rollback transactions
        |
        v
Close borrowed Connections
        |
        v
Close DataSource / connection pool
        |
        v
Checkpoint
        |
        v
Restore
        |
        v
Create new connection pool
        |
        v
Verify database and reopen traffic
~~~

Closing the pool does not replace draining requests. If threads are still using Connections, closing the pool can cause requests to fail or interrupt transactions. The application must control in-flight work first.

## 4. Managing Connection and Transaction Before Checkpoint

### Always close Connection with try-with-resources

Each borrowed Connection needs a clear lifecycle:

~~~java
try (Connection connection = dataSource.getConnection();
     PreparedStatement statement =
         connection.prepareStatement(
             "select id, name from customer where id = ?")) {

    statement.setLong(1, customerId);

    try (ResultSet resultSet = statement.executeQuery()) {
        while (resultSet.next()) {
            // Process data.
        }
    }
}
~~~

When the try block ends, ResultSet, PreparedStatement, and Connection are closed in reverse order. With a pool, Connection.close() returns the connection to the pool.

Do not hold a Connection in a static field, singleton, or ThreadLocal across multiple requests. Do not let a Connection live longer than the transaction or work that needs it. A connection held across a checkpoint may represent an incomplete transaction and a socket that is no longer valid after restore.

### Complete transactions

With auto-commit disabled, the application must decide to commit or rollback before returning the connection:

~~~java
try (Connection connection = dataSource.getConnection()) {
    connection.setAutoCommit(false);

    try {
        updateAccount(connection);
        insertAuditRecord(connection);

        connection.commit();
    } catch (Exception failure) {
        try {
            connection.rollback();
        } catch (SQLException rollbackFailure) {
            failure.addSuppressed(rollbackFailure);
        }

        throw failure;
    }
}
~~~

Do not leave an open transaction when starting a checkpoint. The transaction may hold locks in the database, occupy a connection in the pool, and leave an ambiguous state if the socket is lost.

The application needs to define a policy for in-flight work:

- Wait for transactions to complete within a bounded time.
- If the deadline is exceeded, ask the business layer to cancel the work and rollback.
- If it cannot be determined whether the transaction committed due to a connection error, use a transaction ID, idempotency key, or reconciliation mechanism to avoid duplicate execution.

Do not infer that a transaction was rolled back just because the client connection was closed. The database may have committed before the client lost connection, while the response had not yet reached the application.

### Track borrowed connections

To drain accurately, the application can track the number of in-flight requests or the number of connections currently in use. Some pools provide metrics such as active, idle, total, and pending threads. API names depend on the implementation.

Only when requests have stopped and the active connection count reaches 0 (or meets a defined condition) should the application close the pool. Set a timeout for the drain step to avoid hanging the checkpoint indefinitely.

## 5. DataSource and Connection Pool in CRaC

CRaC provides the Resource interface in the org.crac package. A component implementing Resource can register with the global context to receive callbacks:

- beforeCheckpoint(): prepare the resource before creating the checkpoint image.
- afterRestore(): recreate the resource after the process is restored.

For JDBC, the resource is typically responsible for closing the old pool before checkpoint and creating a new pool after restore.

~~~java
import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

public final class JdbcPoolResource implements Resource {
    private final JdbcPoolFactory factory;
    private JdbcPoolHandle pool;

    public JdbcPoolResource(JdbcPoolFactory factory) throws Exception {
        this.factory = factory;
        this.pool = factory.create();
        Core.getGlobalContext().register(this);
    }

    public synchronized DataSource dataSource() {
        if (pool == null) {
            throw new IllegalStateException(
                "JDBC pool is not ready"
            );
        }
        return pool.dataSource();
    }

    @Override
    public synchronized void beforeCheckpoint(
            Context<? extends Resource> context) throws Exception {
        if (pool == null) {
            return;
        }

        if (!pool.awaitIdle()) {
            throw new IllegalStateException(
                "JDBC pool still has active connections"
            );
        }

        JdbcPoolHandle oldPool = pool;
        oldPool.close();
        pool = null;
    }

    @Override
    public synchronized void afterRestore(
            Context<? extends Resource> context) throws Exception {
        pool = factory.create();
    }

    public synchronized void reopenAfterAbortedCheckpoint()
            throws Exception {
        if (pool == null) {
            pool = factory.create();
        }
    }
}
~~~

JdbcPoolFactory and JdbcPoolHandle are application abstractions, not standard JDBC classes. The simplified example clarifies responsibilities:

~~~java
public interface JdbcPoolFactory {
    JdbcPoolHandle create() throws Exception;
}

public interface JdbcPoolHandle {
    DataSource dataSource();

    boolean awaitIdle() throws Exception;

    void close() throws Exception;
}
~~~

An implementation of JdbcPoolHandle can wrap HikariDataSource, BasicDataSource, or another pool. awaitIdle() should use the metrics API or drain mechanism of the specific pool. If the pool does not provide a method to wait for idle, the application can coordinate using a request/connection counter it manages.

In real code, it is necessary to handle the case where close() partially fails. Do not set pool to null and report success if the implementation has not actually closed; if the state cannot be determined, keep the application in a not-ready state and report an error.

### Keep DataSource injection stable

Many applications inject DataSource into repositories or DAOs at startup. If the old pool is closed and a new pool object is created, repositories may still hold a reference to the old closed pool.

There are two common design approaches:

1. Use a stable DataSource wrapper that forwards getConnection() to the current delegate. Upon restore, replace the delegate with the new pool.
2. Manage the pool as a bean with a lifecycle updated by the container, ensuring repositories obtain the new DataSource after restore.

If using a wrapper, all DataSource methods must be delegated consistently; do not only update a field in the resource while other components still hold the old pool.

Do not create a new pool in afterRestore() without updating where the DataSource is provided to the application. In that case, the new pool may be active while requests still call the old object.

## 6. Example with HikariCP

HikariCP is a popular connection pool. HikariDataSource has a close() method to stop the pool. Configuration should be created from application configuration, not by hard-coding passwords in source code.

~~~java
import com.zaxxer.hikari.HikariConfig;
import com.zaxxer.hikari.HikariDataSource;

public final class HikariPoolFactory {
    public HikariDataSource create() {
        HikariConfig config = new HikariConfig();

        config.setJdbcUrl(System.getenv("JDBC_URL"));
        config.setUsername(System.getenv("JDBC_USER"));
        config.setPassword(System.getenv("JDBC_PASSWORD"));

        config.setMaximumPoolSize(10);
        config.setMinimumIdle(2);
        config.setConnectionTimeout(10_000);
        config.setValidationTimeout(5_000);

        return new HikariDataSource(config);
    }
}
~~~

A wrapper can hold a reference to HikariDataSource and provide lifecycle management:

~~~java
public final class HikariPoolHandle implements JdbcPoolHandle {
    private final HikariDataSource dataSource;

    public HikariPoolHandle(HikariDataSource dataSource) {
        this.dataSource = dataSource;
    }

    @Override
    public DataSource dataSource() {
        return dataSource;
    }

    @Override
    public boolean awaitIdle() {
        // Use metrics or an application-managed active connection
        // counter to confirm drain.
        return dataSource.getHikariPoolMXBean() != null
            && dataSource.getHikariPoolMXBean()
                         .getActiveConnections() == 0;
    }

    @Override
    public void close() {
        dataSource.close();
    }
}
~~~

The example snippet only illustrates how to wrap the pool. In a real application, a single metrics read should not be used as the drain mechanism if new requests can still arrive. Accepting new work must be stopped first, in-flight requests must finish, and only then should active connections be checked. Cases where getHikariPoolMXBean() is not ready or the pool has already shut down must be handled.

Upon restore, the factory creates a new HikariDataSource from the current configuration. Physical connections will be created on demand or according to minimumIdle depending on the pool configuration.

For Apache Commons DBCP, Oracle UCP, or pools managed by an application server, use the corresponding lifecycle API. Do not assume all pools have the same close, eviction, validation, or CRaC integration behavior.

## 7. Coordinating Checkpoint to Close and Reopen the Pool

If the application proactively calls Core.checkpointRestore(), the coordinator can control stopping traffic, waiting for transactions to complete, and recovering the pool when a checkpoint is aborted.

~~~java
import org.crac.CheckpointException;
import org.crac.Core;
import org.crac.RestoreException;

public final class DatabaseCheckpointCoordinator {
    private final RequestGate requestGate;
    private final JdbcPoolResource jdbcPool;

    public DatabaseCheckpointCoordinator(
            RequestGate requestGate,
            JdbcPoolResource jdbcPool) {
        this.requestGate = requestGate;
        this.jdbcPool = jdbcPool;
    }

    public void checkpoint() throws Exception {
        requestGate.stopAcceptingNewRequests();

        boolean readyToResume = false;

        try {
            requestGate.awaitInFlightRequests();

            Core.checkpointRestore();

            // When execution continues after restore,
            // the afterRestore() callback has already created a new pool.
            readyToResume = true;

        } catch (CheckpointException checkpointFailure) {
            try {
                jdbcPool.reopenAfterAbortedCheckpoint();
                readyToResume = true;
            } catch (Exception reopenFailure) {
                checkpointFailure.addSuppressed(reopenFailure);
                markApplicationNotReady();
            }

            throw checkpointFailure;

        } catch (RestoreException restoreFailure) {
            // The instance restored, but a restore callback failed.
            // Do not open traffic while the pool is not ready.
            markApplicationNotReady();
            throw restoreFailure;

        } finally {
            if (readyToResume) {
                requestGate.resumeAcceptingRequests();
            }
        }
    }

    private void markApplicationNotReady() {
        // Update readiness/health state to not accept traffic.
    }
}
~~~

RequestGate is an application abstraction to stop new requests and wait for in-flight requests to finish. The example assumes the JDBC resource is already registered with CRaC and afterRestore() creates a new pool. If the afterRestore() callback fails, traffic must not be opened.

When a checkpoint fails, Core.checkpointRestore() throws CheckpointException in the original instance. The coordinator calls reopenAfterAbortedCheckpoint() to create a new pool. If reopening also fails, the recovery error is attached to the original exception and the application remains in the not-ready state.

If using jcmd directly from outside:

~~~bash
jcmd <pid> JDK.checkpoint
~~~

The application's business thread does not have a Core.checkpointRestore() call to catch CheckpointException. Therefore, one cannot rely on the catch block in the coordinator to handle cases where a checkpoint is aborted by the jcmd command. If automatic pool rollback is mandatory, the request should be sent through an administrative mechanism of the application so the coordinator calls the CRaC API. If jcmd is still used, callbacks and operational procedures must be designed with appropriate recovery capabilities.

## 8. Pool Configuration After Restore

Do not assume that the pre-checkpoint pool configuration is always still appropriate after restore. When creating a new pool, the application may need to reload configuration or authentication credentials according to deployment policy.

Information that typically needs to be checked:

- JDBC URL and database hostname.
- Username, password, or token.
- TLS certificate and truststore.
- Connection timeout and validation timeout.
- Maximum pool size and minimum idle.
- Default transaction isolation.
- Driver version and vendor-specific options.
- Proxy, failover, or read replica configuration.

If credentials are rotated while checkpointed, using a password stored in the heap may cause new connections to fail. Secrets can be reloaded from a secret manager or configuration source after restore, depending on the security model.

Do not log URLs containing tokens, passwords, or authentication data. Log the database/service name, connection duration, and error codes with sensitive information stripped.

### Verify database readiness

A successfully created pool does not guarantee the database is ready to accept queries. After restore, connections must be verified in a way appropriate to the pool and driver.

Example:

~~~java
try (Connection connection = dataSource.getConnection()) {
    if (!connection.isValid(5)) {
        throw new SQLException("Database connection is not valid");
    }
}
~~~

Connection.isValid() depends on the driver and database. Some pools have their own connection test query or validation mechanism. Use configuration supported by the driver and avoid running overly heavy validation queries.

If the database is not ready yet, retry with exponential backoff and a total time limit. Do not create infinite pools or infinite retry threads. Only mark the application ready when required dependencies are operational.

## 9. Pool Sizing and Database Connection Limits

Restoring multiple instances from the same checkpoint can cause the number of connection pools to grow rapidly. If each instance creates a pool with a maximumPoolSize of 20 and there are 10 instances, the total number of connections can reach 200, not counting other applications.

Calculate according to database limits:

~~~text
Maximum total connections
    = number of instances
      x maximumPoolSize per instance
      + administrative connections
      + connections from other applications
~~~

A large pool does not automatically make the application faster. Too many connections can increase lock contention, memory usage, and scheduling overhead on the database.

When scaling out from a checkpoint image:

- Choose maximumPoolSize according to the database's total connection budget.
- Do not let all instances simultaneously open overly large pools immediately upon restore.
- Consider using a low minimumIdle and creating connections on demand.
- Apply backoff when the database refuses connections.
- Monitor active, idle, pending, timeout, and connection creation failures.
- Use connection limits at the database or proxy layer if needed to protect the service.

## 10. Background Threads and Pool-Managed Resources

A connection pool typically has background threads to manage idle connections, check lifetimes, clean up expired connections, or handle internal tasks.

Before checkpoint, closing the pool helps terminate the lifecycle of threads and sockets owned by the pool. After restore, the new pool creates threads and connections according to the current configuration.

Do not:

- Hold a Connection in a ThreadLocal across a checkpoint.
- Keep the old pool's ScheduledExecutorService and create another new pool without closing the old executor.
- Create a new pool in afterRestore() while forgetting the old pool.
- Close the pool while requests are still using connections.
- Create new connections from a pre-checkpoint callback after transitioning the service to the drain state.
- Run health checks concurrently with closing the pool.

If the application creates its own executor to manage JDBC retries or health checks, the lifecycle of that executor must be managed separately. Database resources may depend on that executor; define a clear stop and restart order.

## 11. Callback Ordering and Database-Dependent Components

An application may have multiple Resources: request listeners, transaction managers, DataSources, caches, and workers. They have dependency relationships.

For example, a request handler uses a repository, and the repository uses a DataSource:

~~~text
RequestHandler
      |
      v
Repository / DAO
      |
      v
TransactionManager
      |
      v
DataSource / JDBC Pool
      |
      v
Database
~~~

Before checkpoint, requests and workers must be stopped first, transactions must be awaited to complete, and only then should the pool be closed. After restore, the pool must be created and the database verified before opening the request handler.

Do not rely implicitly on Resource registration order as a substitute for the drain process. Use a coordinator or lifecycle manager to ensure dependent steps are executed in the correct order. If using multiple Resource callbacks, check the ordering rules of the running CRaC version and design so that callbacks remain safe when a dependency is not yet ready.

## 12. Common Pitfalls

### Connection is closed, but repository still uses the old pool

The cause is usually that the repository holds a reference to the old DataSource after the resource creates a new pool.

How to handle: use a stable DataSource wrapper or update the bean/container so every repository receives the new delegate. Check the pool instance ID in logs to identify stale references.

### Pool shuts down while active connections remain

Requests may encounter SQLException or transactions may be interrupted.

How to handle: stop new requests, wait for in-flight requests, check active connections, and only close the pool when the drain condition is met.

### Database refuses connections after restore

This can be due to the database not being ready, DNS or network not yet stabilized, changed credentials, connection limits reached, or invalid TLS configuration.

How to handle: check driver errors, verify secrets/config, retry with bounds, and only open readiness after the pool is operational.

### Transaction processed with unknown outcome

The client may lose connection after the database has committed but before receiving the acknowledgement.

How to handle: use an idempotency key, transaction identifier, or reconcile state in the database. Do not automatically retry non-idempotent operations just because the client received a connection error.

### Checkpoint aborted after pool is closed

If the callback closing the pool succeeds but another callback or the checkpoint engine fails, the original instance may continue with a null or shut-down pool.

How to handle: when using Core.checkpointRestore(), catch CheckpointException and create a new pool. If using external jcmd, a separate recovery procedure or an administrative mechanism that invokes checkpoint from within the application is needed.

### Creating too many pools when restoring multiple instances

Each restored instance may create a new pool, exceeding database connection limits.

How to handle: calculate the total connection budget, limit pool size, reduce minimum idle, and throttle instance startup.

## 13. Observability and Operations

Monitor pool metrics before and after restore:

| Metric | Meaning |
|---|---|
| active_connections | Number of borrowed connections |
| idle_connections | Number of available connections |
| total_connections | Total connections in the pool |
| pending_threads | Number of threads waiting for a connection |
| connection_timeout_total | Number of times waiting for a connection timed out |
| connection_creation_failure_total | Number of connection creation failures |
| pool_lifecycle_state | Whether the pool is ACTIVE, PREPARING, CLOSED, or RESTORING |
| database_validation_failure_total | Number of database validation failures |

Logs should include a pool ID or generation ID to distinguish the pre-checkpoint pool from the post-restore pool. Record the drain start time, connection wait time, pool close time, pool creation time, and database validation results.

Do not log passwords, tokens, JDBC URLs containing credentials, or sensitive query data. For exceptions from the driver, inspect the content before sending it to a centralized logging system.

## 14. Recommended Workflow

### Before checkpoint

1. Transition the application to a state that does not accept new requests.
2. Wait for in-flight requests and background tasks using the database to complete.
3. Commit or rollback open transactions.
4. Close ResultSet, Statement, and Connection using try-with-resources.
5. Confirm that active connections have reached 0 or met the drain condition.
6. Close the DataSource/connection pool using the implementation's API.
7. Log that the pool has been closed and is ready for checkpoint.

### After restore

1. Reload database configuration and secrets if required by policy.
2. Create a new pool using the factory.
3. Update the DataSource delegate or bean used by repositories.
4. Verify the database connection.
5. Restart workers and background tasks that depend on the database.
6. Only open the request listener when the pool and dependencies are ready.

### When checkpoint is aborted

If the application calls Core.checkpointRestore():

1. Catch CheckpointException.
2. Check the pool state.
3. If the pool is closed, create a new pool.
4. Verify the database.
5. Only open the request listener when the pool is operational.
6. If recovery fails, keep readiness false and report an error.

If the checkpoint is sent directly via jcmd, there is no catch block in the application's API call flow. The lifecycle design and administrative procedures must reflect this limitation.

## 15. Principles to Remember

- DataSource is JDBC's standard factory; not every DataSource is a connection pool.
- The DataSource interface does not define close(); close the pool using the implementation's API.
- Connection.close() usually returns the connection to the pool; pool.close() closes the pool and releases resources.
- Use try-with-resources to close Connection, Statement, and ResultSet.
- Complete or rollback transactions before checkpoint.
- Stop accepting new work and drain active connections before closing the pool.
- Do not hold a Connection or transaction across a checkpoint.
- Create a new pool in afterRestore() and update where the DataSource is provided to repositories.
- Verify the database before marking the application ready.
- Catch CheckpointException to recover the pool when a checkpoint is aborted if the application proactively calls Core.checkpointRestore().
- With external jcmd, build a separate recovery procedure because business threads cannot catch that exception.
- Calculate the total connection budget when restoring multiple instances.
- Separately manage background threads, executors, retries, and health checks created by the pool or the application.

DataSource and connection pools are resources whose lifecycle is tied to the database, network, and process threads. When the application drains requests, completes transactions, closes the pool before checkpoint, and creates a new pool after restore, repositories can continue using JDBC with valid connections. Checking readiness and limiting connections after restore helps avoid putting an instance that cannot connect to the database into traffic service.
