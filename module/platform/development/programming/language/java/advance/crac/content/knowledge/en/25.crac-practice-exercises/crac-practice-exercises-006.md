# Restoring a JDBC Application When the Old Connection Pool Has Become Invalid

When a Java application is restored from a CRaC checkpoint, Java objects in the heap may still exist, but the JDBC connections they represent may have become invalid. While the JVM is stopped, the database may close sessions due to idle timeouts, a firewall may drop TCP connections, credentials may be rotated, a proxy may switch backends, or the database may restart. A `Connection` object remaining in memory does not prove that the server-side socket and session are still usable.

The safe approach is to treat JDBC connections and the connection pool as resources bound to the running environment. Before checkpoint, the application stops accepting new work, completes in-flight transactions, and closes the old connections. After restore, the application creates a new connection pool from current configuration and credentials, validates connectivity to the database, and only then opens readiness and resumes JDBC-dependent workers.

This practice exercise builds that workflow with JDBC and HikariCP, explains how to integrate it into the Spring lifecycle or a CRaC Resource, and covers handling stale connections, open transactions, credential rotation, reconnect retries, and testing when the database changes during checkpoint.

## 1. Why Are Old Connections No Longer Reliable?

CRaC restores process state, including Java objects and the heap. The database is an independent system and continues operating during the time the JVM is not running. TCP sockets, database sessions, transactions, and server-side resources are not automatically re-established just because the JVM has been restored.

A typical cycle:

~~~text
JVM is running
    │
    ▼
Application borrows Connection from pool
    │
    ▼
beforeCheckpoint
    ├── Stop accepting new JDBC work
    ├── Drain in-flight transactions
    └── Close connection pool
    │
    ▼
CRaC creates checkpoint
    │
    │  JVM is paused; database and network remain active
    │
    ├── Database restart or failover
    ├── Firewall/proxy expires TCP session
    ├── Credentials are rotated
    └── Server closes idle connections
    │
    ▼
CRaC restores JVM
    │
    ▼
afterRestore
    ├── Read current config/credentials
    ├── Create new pool
    ├── Open new connections
    ├── Validate connection
    └── Reopen admission/readiness
    │
    ▼
Application accepts JDBC requests
~~~

If a checkpoint is created while the pool still holds connections, the pool object and `Connection` wrappers may be restored along with the heap. However, the file descriptors/sockets and server-side sessions may no longer match the state inside the JVM. Reusing old connections can cause `SQLException`, I/O errors, socket resets, transaction errors, or driver-dependent behavior.

CRaC requires the application to coordinate the lifecycle of resources that cannot be carried over intact across a checkpoint, such as sockets and database connections. Close them before checkpoint and recreate them after restore. See [CRaC: Integrating CRaC in your Application](https://docs.azul.com/crac/usage/integrating-crac) and [CRaC: Implementing the CRaC API](https://crac.org/use/implement-crac/).

### 1.1. JDBC Components That Can Be Affected

| Component | Why it can become stale | How to handle |
|---|---|---|
| `Connection` | TCP socket or server session has been closed | Close and acquire a new connection |
| `PreparedStatement` | Bound to the old connection/session | Recreate after acquiring a new connection |
| `ResultSet` | Cursor depends on session and transaction | Close before checkpoint; re-query after restore |
| Transaction | Locks, snapshots, and server transactions cannot continue safely | Commit or rollback before checkpoint |
| Connection pool | May contain connection wrappers pointing to old sockets | Drain and close pool; create a new pool |
| Database metadata/cache | May reflect an old schema or endpoint | Refresh if the environment can change |
| JDBC driver state | May hold native/socket resources or background threads | Follow driver guidance; reinitialize if needed |
| XA/JTA resource | Transaction coordinator and resource manager have their own state | Do not checkpoint mid-transaction; use the transaction manager's recovery protocol |

Do not attempt to keep transactions open across a checkpoint. A checkpoint is not a database transaction serialization mechanism.

### 1.2. `isClosed()` Does Not Verify That a Connection Is Alive

JDBC has two methods that are often confused:

- `Connection.isClosed()` indicates whether the connection object has been closed according to JDBC state.
- `Connection.isValid(timeout)` asks the driver to verify that the connection is still valid, using a query or an equivalent mechanism.

A connection can return `false` from `isClosed()` even though the socket has been closed by the peer or the network path has been lost. The Java API explicitly states that `isClosed()` should not be used to determine whether a connection is still valid. Use `isValid(timeout)` or the validation mechanism provided by the pool/driver. [Java JDBC `Connection` API](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/Connection.html).

## 2. Practice Exercise Goals

After completing this exercise, the application must satisfy the following conditions:

1. No new request or worker starts a transaction once checkpoint preparation has begun.
2. In-flight transactions are completed within a finite deadline.
3. No borrowed connections remain in use before the pool is closed.
4. The old pool is closed and is not reused after restore.
5. The new pool obtains configuration and credentials according to current policy.
6. New connections are validated before the application accepts traffic.
7. If the database is temporarily unavailable, the application keeps readiness in a state that refuses traffic and retries with bounded limits.
8. Workers and schedulers only resume after the datasource is ready.
9. If checkpoint preparation fails, the application has a recovery path to continue running or report errors clearly.
10. No two components jointly own the lifecycle of the same connection pool.

The code below is an illustrative sample for an application using HikariCP. Adjust it to your actual HikariCP, JDBC driver, Spring Framework, and CRaC JDK versions.

## 3. Preparing JDBC and HikariCP

The example uses:

- Java with a JDK that supports CRaC.
- A JDBC driver matching the database.
- HikariCP as the connection pool.
- Spring JDBC or plain JDBC for data access.
- CRaC API `org.crac` if the application registers resources itself.

Illustrative Maven dependencies:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.crac</groupId>
        <artifactId>crac</artifactId>
        <version>1.5.0</version>
    </dependency>

    <dependency>
        <groupId>com.zaxxer</groupId>
        <artifactId>HikariCP</artifactId>
        <version>6.3.0</version>
    </dependency>

    <dependency>
        <groupId>org.springframework</groupId>
        <artifactId>spring-jdbc</artifactId>
        <version>6.2.0</version>
    </dependency>
</dependencies>
~~~

These are example versions to illustrate declaration. Choose versions compatible with the JDK, Spring Boot BOM, JDBC driver, and runtime in your project. With Spring Boot, prefer dependency management provided by Spring Boot instead of pinning individual library versions manually.

### 3.1. Pool Configuration

A HikariCP configuration can start as follows:

~~~java
HikariConfig config = new HikariConfig();

config.setJdbcUrl(jdbcUrl);
config.setUsername(username);
config.setPassword(password);

config.setPoolName("orders-db-pool");
config.setMaximumPoolSize(20);
config.setMinimumIdle(2);

config.setConnectionTimeout(5_000);
config.setValidationTimeout(3_000);

config.setMaxLifetime(25 * 60_000L);
config.setKeepaliveTime(2 * 60_000L);
~~~

The properties have different meanings:

- `maximumPoolSize`: limits the total number of connections in the pool.
- `minimumIdle`: the number of idle connections the pool tries to maintain.
- `connectionTimeout`: maximum time to wait to borrow a connection.
- `validationTimeout`: maximum time for validation.
- `maxLifetime`: maximum lifetime of a connection in the pool.
- `keepaliveTime`: keepalive interval for idle connections.

`maxLifetime` should be shorter than any connection age limit imposed by the database or infrastructure. `keepaliveTime` helps check/keep idle connections alive while the JVM is running. These two properties do not replace closing and recreating the pool after a long checkpoint period. While the JVM is stopped, the pool's scheduler cannot guarantee executing keepalives on time.

## 4. Designing a Pool-Swappable DataSource

`HikariDataSource` after `close()` is considered shut down. You should not close a pool and then try calling `getConnection()` on that same old object. A new Hikari instance must be created after restore.

One way to organize this is to place a `DataSource` wrapper in front of the real pool. Repositories and `JdbcTemplate` only see the wrapper; the lifecycle manager can detach the old pool and install the new pool without replacing the entire dependency injection graph.

### 4.1. ReloadableDataSource

The following example implements the main `DataSource` methods and forwards calls to the current delegate:

~~~java
package com.example.jdbc;

import javax.sql.DataSource;
import java.io.PrintWriter;
import java.sql.Connection;
import java.sql.SQLException;
import java.sql.SQLFeatureNotSupportedException;
import java.util.concurrent.atomic.AtomicReference;
import java.util.logging.Logger;

public final class ReloadableDataSource implements DataSource {

    private final AtomicReference<DataSource> delegate =
            new AtomicReference<>();

    public void install(DataSource replacement) {
        if (replacement == null) {
            throw new IllegalArgumentException(
                    "replacement must not be null");
        }

        if (!delegate.compareAndSet(null, replacement)) {
            throw new IllegalStateException(
                    "A JDBC pool is already installed");
        }
    }

    public DataSource detach() {
        return delegate.getAndSet(null);
    }

    public boolean isInstalled() {
        return delegate.get() != null;
    }

    private DataSource current() throws SQLException {
        DataSource current = delegate.get();

        if (current == null) {
            throw new SQLException(
                    "JDBC DataSource is unavailable during lifecycle transition");
        }

        return current;
    }

    @Override
    public Connection getConnection() throws SQLException {
        return current().getConnection();
    }

    @Override
    public Connection getConnection(
            String username,
            String password) throws SQLException {

        return current().getConnection(username, password);
    }

    @Override
    public PrintWriter getLogWriter() throws SQLException {
        return current().getLogWriter();
    }

    @Override
    public void setLogWriter(PrintWriter out) throws SQLException {
        current().setLogWriter(out);
    }

    @Override
    public void setLoginTimeout(int seconds) throws SQLException {
        current().setLoginTimeout(seconds);
    }

    @Override
    public int getLoginTimeout() throws SQLException {
        return current().getLoginTimeout();
    }

    @Override
    public Logger getParentLogger()
            throws SQLFeatureNotSupportedException {

        DataSource current = delegate.get();

        if (current == null) {
            throw new SQLFeatureNotSupportedException(
                    "JDBC DataSource is unavailable");
        }

        return current.getParentLogger();
    }

    @Override
    public <T> T unwrap(Class<T> iface) throws SQLException {
        if (iface.isInstance(this)) {
            return iface.cast(this);
        }

        return current().unwrap(iface);
    }

    @Override
    public boolean isWrapperFor(Class<?> iface) throws SQLException {
        return iface.isInstance(this) || current().isWrapperFor(iface);
    }
}
~~~

This wrapper provides a stable access point for repositories. When `delegate` is `null`, every request for a new connection fails clearly instead of accidentally using the old pool.

Note: `AtomicReference` only makes swapping the delegate reference thread-safe. It does not automatically drain connections currently being borrowed. Before calling `detach()`, the application must still stop admission and wait for all transactions/connection borrowers to finish. Do not swap the pool while requests are still using old connections.

### 4.2. Configuring Repositories to Use the Wrapper

In Spring, you can inject the wrapper as the primary datasource:

~~~java
@Configuration
public class JdbcConfiguration {

    @Bean
    public ReloadableDataSource reloadableDataSource() {
        return new ReloadableDataSource();
    }

    @Bean
    public JdbcTemplate jdbcTemplate(
            ReloadableDataSource dataSource) {

        return new JdbcTemplate(dataSource);
    }
}
~~~

Repositories use the `JdbcTemplate` or `DataSource` injected by Spring. They do not hold a direct reference to `HikariDataSource`.

If using `DataSourceTransactionManager` or `JdbcTransactionManager`, configure it with the same `ReloadableDataSource`. The transaction manager needs to see a stable datasource; swapping the pool only occurs when no active transactions remain.

## 5. Stopping New Transactions and Draining Active Connections

Before closing the pool, new requests and new workers must be prevented from starting JDBC work. Simply calling `HikariDataSource.close()` while a transaction is running can cause the application to lose its connection in the middle of a business operation.

A simple admission gate can count active JDBC operations:

~~~java
package com.example.jdbc;

import java.time.Duration;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.locks.Condition;
import java.util.concurrent.locks.ReentrantLock;

public final class JdbcAdmissionGate {

    private final ReentrantLock lock = new ReentrantLock();
    private final Condition drained = lock.newCondition();

    private boolean accepting = true;
    private int activeOperations;

    public boolean enter() {
        lock.lock();
        try {
            if (!accepting) {
                return false;
            }

            activeOperations++;
            return true;
        } finally {
            lock.unlock();
        }
    }

    public void exit() {
        lock.lock();
        try {
            if (activeOperations <= 0) {
                throw new IllegalStateException(
                        "No active JDBC operation to exit");
            }

            activeOperations--;

            if (activeOperations == 0) {
                drained.signalAll();
            }
        } finally {
            lock.unlock();
        }
    }

    public void pauseAndDrain(Duration timeout)
            throws InterruptedException, TimeoutException {

        long budget = timeout.toNanos();
        if (budget <= 0) {
            throw new IllegalArgumentException(
                    "timeout must be positive");
        }

        long started = System.nanoTime();

        lock.lockInterruptibly();
        try {
            accepting = false;

            while (activeOperations > 0) {
                long remaining =
                        budget - (System.nanoTime() - started);

                if (remaining <= 0) {
                    accepting = true;
                    drained.signalAll();

                    throw new TimeoutException(
                            "JDBC operations did not drain in time");
                }

                drained.awaitNanos(remaining);
            }
        } catch (InterruptedException interrupted) {
            accepting = true;
            drained.signalAll();
            Thread.currentThread().interrupt();
            throw interrupted;
        } finally {
            lock.unlock();
        }
    }

    public void resume() {
        lock.lock();
        try {
            accepting = true;
            drained.signalAll();
        } finally {
            lock.unlock();
        }
    }

    public int activeOperations() {
        lock.lock();
        try {
            return activeOperations;
        } finally {
            lock.unlock();
        }
    }
}
~~~

Every JDBC processing path needs to go through the gate and must call `exit()` in a `finally` block:

~~~java
public Order loadOrder(long id) {
    if (!jdbcGate.enter()) {
        throw new ServiceUnavailableException(
                "JDBC operations are paused");
    }

    try {
        return orderRepository.findById(id)
                .orElseThrow(OrderNotFoundException::new);
    } finally {
        jdbcGate.exit();
    }
}
~~~

This example assumes the gate covers the entire unit of work holding the transaction/connection. If a request calls multiple repositories within the same transaction, place the gate at the transaction or service operation boundary so the counter increments/decrements once for the entire unit of work.

Do not gate only HTTP requests. Message listeners, schedulers, `@Async` tasks, and worker threads must also stop admission. Readiness false does not automatically stop background work.

### 5.1. Why Drain Before Closing the Pool?

When the checkpoint is created, the application should no longer have:

- Uncommitted/unrolled-back transactions.
- Borrowed connections.
- Open prepared statements or ResultSets.
- Active database-side cursors.
- Batch updates in progress.
- Message acknowledgements dependent on a JDBC transaction.
- Workers holding business locks or database locks.

If draining does not complete within the deadline, reject the checkpoint. Do not close the pool to force transactions to end unless the application already has clear recovery semantics.

## 6. Managing the Pool with a CRaC Resource

Once the wrapper and admission gate are in place, create a resource responsible for closing the old pool before checkpoint and creating a new pool after restore.

Example:

~~~java
package com.example.jdbc;

import com.zaxxer.hikari.HikariConfig;
import com.zaxxer.hikari.HikariDataSource;
import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;
import org.springframework.stereotype.Component;

import javax.sql.DataSource;
import java.sql.Connection;
import java.sql.SQLException;
import java.time.Duration;
import java.util.function.Supplier;

@Component
public final class JdbcPoolCracResource implements Resource {

    private final ReloadableDataSource dataSource;
    private final JdbcAdmissionGate gate;
    private final Supplier<HikariConfig> configSupplier;

    public JdbcPoolCracResource(
            ReloadableDataSource dataSource,
            JdbcAdmissionGate gate,
            Supplier<HikariConfig> configSupplier) {

        this.dataSource = dataSource;
        this.gate = gate;
        this.configSupplier = configSupplier;

        Core.getGlobalContext().register(this);
    }

    @Override
    public void beforeCheckpoint(
            Context<? extends Resource> context) throws Exception {

        gate.pauseAndDrain(Duration.ofSeconds(20));

        DataSource old = dataSource.detach();

        if (old instanceof HikariDataSource hikari) {
            hikari.close();
        }
    }

    @Override
    public void afterRestore(
            Context<? extends Resource> context) throws Exception {

        HikariDataSource replacement = null;

        try {
            HikariConfig config = configSupplier.get();
            replacement = new HikariDataSource(config);

            validate(replacement);

            dataSource.install(replacement);
            replacement = null;

            gate.resume();

        } catch (Exception failure) {
            if (replacement != null) {
                replacement.close();
            }

            // Keep datasource unavailable and gate closed.
            throw failure;
        }
    }

    private void validate(HikariDataSource candidate)
            throws SQLException {

        try (Connection connection = candidate.getConnection()) {
            if (!connection.isValid(5)) {
                throw new SQLException(
                        "Database connection validation failed");
            }
        }
    }
}
~~~

In the example, `javax.sql.DataSource` needs to be imported for the `old` variable. The Hikari config creation must obtain the JDBC URL, username, password, and other properties from the application's configuration provider.

Key points:

1. `beforeCheckpoint` closes admission and waits for running operations to finish.
2. The old pool is detached from the wrapper.
3. The old pool is closed; the wrapper no longer hands out new connections.
4. `afterRestore` creates a new `HikariDataSource` instance.
5. The candidate pool is verified with a real connection.
6. Only after validation is the pool installed into the wrapper.
7. The admission gate only resumes after the pool is ready.
8. If reconnecting fails, the candidate pool is closed, the wrapper remains unavailable, and the callback reports an error.

This is a skeleton showing the lifecycle order. In real code, also handle the case where the checkpoint is rejected after the pool has been detached: the application may need to recreate the pool and resume the gate according to its recovery policy. Do not assume a failed `beforeCheckpoint` will automatically invoke `afterRestore`.

### 6.1. Do Not Register Duplicate Lifecycle Owners

If Spring Framework already manages a `Lifecycle` bean to stop and restart the datasource, do not simultaneously register another `org.crac.Resource` that also closes/opens the same pool. Choose a single owner for the pool lifecycle.

Spring Framework supports checkpoint/restore by stopping running beans according to `Lifecycle` before checkpoint and starting them again after restore. Libraries without Spring integration can be managed with a custom `org.crac.Resource`. See [Spring Framework: JVM Checkpoint Restore](https://docs.spring.io/spring-framework/reference/integration/checkpoint-restore.html).

### 6.2. Creating a New Pool from Current Configuration

Do not store passwords or tokens directly in `HikariConfig` and assume the values in the checkpoint will always remain valid. After restore, the configuration supplier should read secrets/config according to current policy.

Example:

~~~java
@Bean
Supplier<HikariConfig> hikariConfigSupplier(
        JdbcProperties properties,
        SecretProvider secretProvider) {

    return () -> {
        HikariConfig config = new HikariConfig();

        config.setJdbcUrl(properties.jdbcUrl());
        config.setUsername(secretProvider.username());
        config.setPassword(secretProvider.password());

        config.setMaximumPoolSize(properties.maximumPoolSize());
        config.setConnectionTimeout(5_000);
        config.setValidationTimeout(3_000);

        return config;
    };
}
~~~

If the secret provider is unreachable, do not create the pool with old credentials as an implicit fallback. Keep readiness false and apply bounded retries or report a configuration error.

## 7. Validating Connections After Restore

After creating a new pool, you need to verify that the database actually accepts connections.

### 7.1. Using `Connection.isValid(timeout)`

~~~java
try (Connection connection = dataSource.getConnection()) {
    if (!connection.isValid(5)) {
        throw new SQLException("Connection is not valid");
    }
}
~~~

The timeout parameter of `isValid` is in seconds. The driver must send a query or use an active mechanism to verify the connection. If the driver does not support it or has specific behavior, check the driver documentation.

### 7.2. Validation Query

Some drivers or pool configurations can use a test query:

~~~sql
SELECT 1
~~~

The specific query depends on the database. Choose a lightweight statement that does not modify data and does not require permissions beyond the application's permissions.

HikariCP prefers JDBC4 `Connection.isValid()` when the driver supports it. Only configure `connectionTestQuery` when the driver requires that validation method. Do not run heavy queries or access business tables just for health checks.

### 7.3. Do Not Rely on `isClosed()`

The following example is insufficient:

~~~java
if (!connection.isClosed()) {
    // Cannot conclude that the database session is still alive.
}
~~~

`isClosed()` primarily reflects the closed state of the object according to JDBC. It is not required to check the socket/peer. Use `isValid(timeout)` or let the pool validate connections according to policy.

### 7.4. Validation When Borrowing Connections

After restore, the pool can create connections on demand instead of opening the entire `maximumPoolSize` immediately. This avoids creating a connection burst to the database. However, the first request should only be accepted after at least one connection test succeeds and the readiness policy has been satisfied.

If warming up multiple connections is needed, limit concurrency and use timeouts. Do not open the entire pool simultaneously across all replicas if the database has a low connection limit.

## 8. HikariCP Settings and Keepalive Limitations

Several HikariCP properties help handle connections closed while the application is running:

| Property | Purpose | Limitation |
|---|---|---|
| `maxLifetime` | Retires overly old connections from the pool | Does not bring old connections back to life after checkpoint |
| `keepaliveTime` | Checks/keeps idle connections active | Only runs while the JVM/pool is running |
| `connectionTimeout` | Limits time spent waiting to borrow a connection | Does not fix credential or endpoint errors |
| `validationTimeout` | Limits time spent on validation | Must be lower than connection timeout per Hikari requirements |
| `idleTimeout` | Removes excess idle connections | Does not replace checkpoint lifecycle |
| `leakDetectionThreshold` | Detects connections held too long | Leak diagnostics, not a recovery mechanism |

HikariCP uses `maxLifetime` to retire connections by age; connections currently borrowed are not evicted mid-use just for reaching maximum age. `keepaliveTime` applies to idle connections. Because the JVM is not running during checkpoint, periodic tasks in the pool cannot replace CRaC callbacks. See [HikariCP configuration](https://github.com/brettwooldridge/HikariCP#frequently-used).

An example configuration:

~~~yaml
app:
  jdbc:
    maximum-pool-size: 20
    minimum-idle: 2
    connection-timeout: 5s
    validation-timeout: 3s
    max-lifetime: 25m
    keepalive-time: 2m
~~~

Values are for illustration only. `maxLifetime` should be shorter than the limit imposed by the database/proxy; `keepaliveTime` must be smaller than `maxLifetime` if both are enabled. Measure actual load and check HikariCP configuration for your exact version.

## 9. Integrating with Spring Framework and Spring Boot

If the application uses Spring, determine the checkpoint mode before choosing a lifecycle hook.

### 9.1. On-Demand Checkpoint/Restore

With on-demand checkpoint/restore, Spring Framework stops running beans according to `Lifecycle` before checkpoint. After restore, Spring starts those beans again. Resources can be managed via `Lifecycle.stop()` and `Lifecycle.start()`.

You can implement `SmartLifecycle` for the JDBC management component:

~~~java
@Component
public final class JdbcPoolLifecycle implements SmartLifecycle {

    private final ReloadableDataSource dataSource;
    private final JdbcAdmissionGate gate;
    private final Supplier<HikariConfig> configSupplier;

    private volatile boolean running;

    public JdbcPoolLifecycle(
            ReloadableDataSource dataSource,
            JdbcAdmissionGate gate,
            Supplier<HikariConfig> configSupplier) {

        this.dataSource = dataSource;
        this.gate = gate;
        this.configSupplier = configSupplier;
    }

    @Override
    public void start() {
        if (running) {
            return;
        }

        HikariDataSource replacement =
                new HikariDataSource(configSupplier.get());

        try {
            validate(replacement);
            dataSource.install(replacement);
            running = true;
            gate.resume();
        } catch (Exception failure) {
            replacement.close();
            throw new IllegalStateException(
                    "Could not restore JDBC pool", failure);
        }
    }

    @Override
    public void stop() {
        if (!running) {
            return;
        }

        try {
            gate.pauseAndDrain(Duration.ofSeconds(20));

            DataSource old = dataSource.detach();
            if (old instanceof HikariDataSource hikari) {
                hikari.close();
            }

            running = false;
        } catch (Exception failure) {
            throw new IllegalStateException(
                    "Could not prepare JDBC pool for checkpoint",
                    failure);
        }
    }

    @Override
    public boolean isRunning() {
        return running;
    }

    @Override
    public boolean isAutoStartup() {
        return true;
    }

    @Override
    public int getPhase() {
        return 0;
    }

    private void validate(HikariDataSource candidate)
            throws SQLException {

        try (Connection connection = candidate.getConnection()) {
            if (!connection.isValid(5)) {
                throw new SQLException(
                        "Database connection validation failed");
            }
        }
    }
}
~~~

The example needs to be placed in the right lifecycle order relative to workers and schedulers. Workers must stop before the JDBC pool closes; on restore, the pool must be ready before workers resume. You can adjust `getPhase()` to express that relationship after checking the lifecycle order in the application.

`SmartLifecycle.stop()` does not declare checked exceptions. If stop fails, clearly define the framework and application policy. For resources that need to report errors directly through CRaC callbacks, a custom `org.crac.Resource` can be used instead of a lifecycle bean.

### 9.2. Automatic Checkpoint at Startup

Spring Framework distinguishes automatic checkpoint during the refresh phase from on-demand checkpoint of an already running application. Automatic checkpoint occurs before lifecycle beans start running. Therefore, you cannot assume a pool has already been started and will be stopped/started in the same way as an on-demand checkpoint.

If using automatic checkpoint, design the datasource so it does not open database connections prematurely when not yet needed, or determine the proper resource initialization phase. After restore, the pool must be created when the lifecycle starts and before requests requiring JDBC are accepted.

Spring Framework clearly describes these two modes in [JVM Checkpoint Restore](https://docs.spring.io/spring-framework/reference/integration/checkpoint-restore.html).

### 9.3. Do Not Use Both SmartLifecycle and Resource for the Same Pool

A common mistake is:

- `SmartLifecycle.stop()` closes the Hikari pool.
- `org.crac.Resource.beforeCheckpoint()` also closes the Hikari pool.
- After restore, both `Lifecycle.start()` and `Resource.afterRestore()` create a new pool.

The result can be the pool being closed twice, the delegate being overwritten, the old pool remaining running, or two pools coexisting. Choose a single lifecycle owner. Another coordinator can manage readiness/admission, but should not co-own the pool close/install operations.

## 10. Transaction Manager and Thread-Bound Connections

Spring JDBC transactions typically bind a connection to the thread for the duration of the transaction. The connection can be acquired when the transaction starts and returned to the pool when the transaction ends.

Before checkpoint, ensure:

- No transactions are active.
- No thread holds a connection in `TransactionSynchronizationManager`.
- No `@Transactional` method is running.
- No async task holds an invalid transaction context.
- No batch/cursor operation is open.
- The transaction manager has finished committing or rolling back.

Do not try to serialize `TransactionStatus`, JDBC connections, or server transactions to resume after restore. If a transaction has not completed, let the operation finish before checkpoint. If it cannot finish within the allowed time, reject the checkpoint and handle business logic according to transaction policy.

For distributed transactions/JTA/XA, recovery depends on the transaction manager and resource manager. Do not assume a CRaC checkpoint can replace transaction logs or XA recovery. Use the transaction manager's official recovery mechanism and do not checkpoint while a transaction is in an in-doubt state.

## 11. Credential Rotation and Database Configuration Changes

One benefit of creating a new pool after restore is being able to read current credentials. This is important when secrets are rotated while the JVM is stopped.

Information that should be re-read or verified:

- JDBC URL and hostname.
- Username/password.
- IAM/database authentication token.
- TLS certificate and truststore.
- Client certificate/private key path.
- Proxy endpoint.
- Database name/schema.
- Connection properties.
- Pool size and timeout policy.

Do not log or emit secret values into logs or metrics. Only log non-sensitive secret version/revision or configuration source names.

### 11.1. Short-Lived Tokens

If the database uses short-lived tokens, do not create the pool using a token saved in the checkpoint. `configSupplier` should request a new token during `afterRestore` or when creating connections.

Example:

~~~java
String token = tokenProvider.createDatabaseToken();

HikariConfig config = new HikariConfig();
config.setJdbcUrl(jdbcUrl);
config.setUsername(databaseUser);
config.setPassword(token);
~~~

A token may expire shortly after the pool is created. If the driver supports per-connection token refresh, configure it according to the driver's mechanism. Otherwise, a strategy is needed to recreate the pool before the token expires. Do not assume changing the password on an already initialized `HikariConfig` will automatically update credentials for all existing connections.

### 11.2. TLS Certificates and Truststores

If certificates are rotated during checkpoint, recreating the client/pool may require reloading the SSL context or driver configuration. Merely updating certificate files on disk does not necessarily change an SSL context already initialized in the heap.

Check how the JDBC driver creates its TLS context. If the driver holds the SSL context or socket factory in a singleton, you need to recreate the corresponding object or restart the component according to lifecycle.

## 12. Retrying When the Database Is Not Yet Ready

The database may not be ready immediately when the application finishes restoring. For example, the database may be failing over or the service endpoint may not yet be stable.

A good reconnect policy needs:

- Timeout for each connection attempt.
- Retry count or total deadline.
- Exponential backoff.
- Jitter to avoid multiple replicas retrying at the exact same time.
- Readiness kept false while a required dependency is not working.
- Standardized reason logging.
- Not repeatedly creating new pools without closing the previous candidate pool.

Backoff example:

~~~java
import java.util.concurrent.ThreadLocalRandom;

public void reconnectWithRetry(
        int maxAttempts,
        Duration initialDelay,
        Duration maxDelay) throws Exception {

    long delayMillis = initialDelay.toMillis();

    for (int attempt = 1; attempt <= maxAttempts; attempt++) {
        try {
            installValidatedPool();
            return;
        } catch (Exception failure) {
            if (attempt == maxAttempts) {
                throw failure;
            }

            long jitter = ThreadLocalRandom.current()
                    .nextLong(Math.max(1, delayMillis / 4));

            Thread.sleep(delayMillis + jitter);

            delayMillis = Math.min(
                    delayMillis * 2,
                    maxDelay.toMillis());
        }
    }
}
~~~

This is a simplified example. In production, use a retry library or controlled scheduler, limit total duration, and respect interrupts. `Thread.sleep()` inside a CRaC callback will prolong restore and may keep the JVM not Ready; if retries may take a long time, consider having the callback initialize a reconnecting state and run a separate recovery worker while readiness remains false.

### 12.1. Distinguishing Transient Errors from Configuration Errors

| Error | Retryable | Handling |
|---|---|---|
| Database failover in progress | Yes | Retry with backoff |
| Temporary DNS resolution failure | Yes | Retry and monitor resolver |
| Connection refused | Yes, if service is restarting | Retry within deadline |
| Wrong or expired credentials | Do not retry with same credentials | Fetch new secret/token |
| Database user revoked | Do not retry indefinitely | Report configuration/permission error |
| Wrong JDBC URL | Do not retry indefinitely | Stop readiness and report configuration |
| Untrusted TLS certificate | Do not retry with same trust config | Fix certificate/truststore |
| Connection limit reached | Bounded | Backoff, reduce concurrency, and check pool size |

Do not retry indefinitely in `afterRestore` if doing so causes the callback to never finish. Define a restore deadline and a clear operational policy for unavailable dependencies.

## 13. Readiness and Background Workers After the Pool Is Restored

A newly created pool succeeding does not necessarily mean the application is ready. Readiness should only succeed after:

1. JDBC configuration is loaded.
2. Current credentials/tokens are retrieved.
3. The new pool is created.
4. Connection validation succeeds.
5. The transaction manager and repositories can use the datasource.
6. Workers needing JDBC are ready to resume.

With Spring Boot, use `ReadinessState.REFUSING_TRAFFIC` during recovery and only transition to `ACCEPTING_TRAFFIC` after the datasource and required dependencies are working.

Example:

~~~java
publisher.publishEvent(
        new AvailabilityChangeEvent<>(
                this,
                ReadinessState.REFUSING_TRAFFIC));

// Create a new pool, validate, and restore required workers.

publisher.publishEvent(
        new AvailabilityChangeEvent<>(
                this,
                ReadinessState.ACCEPTING_TRAFFIC));
~~~

HTTP server readiness does not automatically stop schedulers or message consumers. A separate gate is needed for background workers. If a worker uses JDBC, only resume it after the new pool is installed and validation succeeds.

## 14. Handling `SQLException` After Restore

Some common exceptions when an application accidentally uses an old connection:

| Exception/SQLState | Possible cause | How to handle |
|---|---|---|
| `SQLNonTransientConnectionException` | Connection can no longer be used | Discard connection and create a new one |
| `SQLRecoverableException` | Driver requires reconnecting | Close old connection, acquire a new one |
| `SQLTransientConnectionException` | Temporary connection error | Retry according to policy and deadline |
| `Communications link failure` | Socket/network/server no longer connected | Check endpoint, network, and pool |
| `Connection reset` | Peer or proxy closed TCP session | Discard connection and reconnect |
| `Connection is closed` | Pool/driver has closed the connection | Do not use old reference |
| Authentication failure | Credentials expired or rotated | Retrieve new credentials |
| `Too many connections` | Multiple pools/replicas creating connections simultaneously | Check pool size, rollout, and connection limit |

SQLState and exception classes depend on the JDBC driver. Do not classify every `SQLException` as a retryable error. Syntax errors, constraint violations, or permission denied errors usually require different handling than network interruptions.

### 14.1. Do Not Blindly Retry a Transaction with Side Effects

If the connection drops between sending a command and receiving the result, the application may not know whether the database committed or not. Retrying the entire transaction could execute the side effect twice.

For operations with side effects:

- Use an idempotency key or unique business key.
- Design the transaction so commit status can be determined.
- Do not automatically retry write commands when commit outcome is unknown.
- Use outbox/inbox or deduplication mechanisms where appropriate.
- Distinguish errors occurring before sending the command, during execution, and after commit.

CRaC restore does not change transaction semantics or database/message broker exactly-once guarantees.

## 15. Verifying the Old Pool Has Truly Been Removed

After restore, ensure no object graph accidentally holds a reference to the old pool.

Places to check:

- Whether singleton repositories/services hold the old `HikariDataSource` directly.
- Whether `JdbcTemplate` or the transaction manager points to the wrapper or a specific pool.
- Whether `ThreadLocal` holds connections.
- Whether async tasks hold connections/statements.
- Whether caches store `Connection`, `PreparedStatement`, or `ResultSet`.
- Whether driver-specific objects hold old sockets/sessions.
- Whether health indicators use a different datasource than the production datasource.

All JDBC access should go through a single datasource entry point that can swap delegates. Do not store connections in singleton fields or reuse connections across multiple requests.

### 15.1. Checking Connection Counts

HikariCP can provide metrics or JMX for:

- Active connection count.
- Idle connection count.
- Total connection count.
- Threads awaiting connection.

After restore, confirm the new pool has a new name/identity or new generation in the logs, an appropriate connection count, and no remaining borrowers from the old pool. Do not rely solely on a connection count of 0; the pool may lazy-create connections on the first request.

## 16. Testing Scenarios Where the Database Changes During Checkpoint

A restore test should simulate the database changing while the JVM is not running.

### 16.1. Basic Test

1. Start the application with the JDBC pool.
2. Send a few requests to create connections.
3. Confirm transactions complete and the pool has idle connections.
4. Transition readiness to refusing traffic.
5. Stop background workers and drain JDBC operations.
6. Create a checkpoint with a real CRIU engine.
7. Restart from the checkpoint.
8. Confirm the new pool is created.
9. Confirm connection validation succeeds.
10. Confirm readiness transitions to accepting traffic.
11. Send JDBC requests and verify data.

### 16.2. Database Restart During Checkpoint

1. Create a checkpoint after the application has drained and closed the pool.
2. Restart the database or database container.
3. Restore the application from the checkpoint.
4. Confirm the application creates new sessions.
5. Verify JDBC requests succeed.
6. Confirm there are no logs using old connections.

This test proves the application does not depend on the database session at checkpoint time.

### 16.3. Credential Rotation

1. Create a checkpoint.
2. Rotate the database user's password or token.
3. Restore the application.
4. Confirm `configSupplier` reads the new credentials.
5. Confirm the new pool connects successfully.
6. Confirm secrets are not logged.
7. Verify readiness only succeeds after validation.

If the application uses IAM tokens, simulate the old token expiring and confirm the new pool requests a new token.

### 16.4. Database Unavailable After Restore

1. Create a valid checkpoint.
2. Upon restore, block connections to the database.
3. Confirm pool creation/validation fails according to timeout.
4. Confirm the wrapper does not hand out the old pool.
5. Confirm readiness stays false.
6. Restore the database.
7. Confirm retries create a new pool and readiness transitions to success.

If retries do not succeed within the deadline, verify the recovery policy instead of letting the callback wait indefinitely.

### 16.5. Connection Leak or Non-Draining Transaction

1. Keep a connection/transaction active in staging.
2. Initiate checkpoint.
3. Confirm the admission gate stops new tasks.
4. Confirm drain waits for the running transaction.
5. If past the deadline, confirm the checkpoint is rejected.
6. Confirm the application rolls back the pause state and readiness/gate return to the proper policy.
7. Fix the leak and retry.

Do not try to create a checkpoint while a transaction still holds a connection just to make the test "pass".

## 17. Diagnostics When JDBC Restore Fails

Collect the following information:

- Checkpoint ID and restore operation ID.
- JDK vendor/version and JDBC driver version.
- Database engine/version and endpoint.
- Hikari pool name/generation.
- Pool active/idle/pending count.
- SQLState and exception class.
- Reconnect start timestamp and validation duration.
- Non-sensitive secret/config revision.
- CRaC callback logs.
- Pod readiness and container restart events.
- Network/DNS/TLS diagnostics.

Useful Kubernetes commands:

~~~bash
kubectl logs <POD_NAME> -c app
kubectl logs <POD_NAME> -c app --previous
kubectl describe pod <POD_NAME>
kubectl get endpointslices \
  -l kubernetes.io/service-name=<SERVICE_NAME>
~~~

If the `afterRestore` callback does not run, the error may lie in the checkpoint engine or JVM resume before JDBC code runs. If the callback runs but `getConnection()` times out, check the database endpoint, credentials, pool config, and network. If pool validation succeeds but business requests still fail, check the transaction manager and code still holding references to the old datasource/connection.

## 18. Common Implementation Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Keeping the old pool in the checkpoint | Connections point to invalid sockets/sessions | Close pool before checkpoint and create a new instance |
| Only checking `isClosed()` | Stale connections can still be considered open | Use `isValid(timeout)` or pool validation |
| Closing the pool while transactions are active | Requests fail mid-business-operation | Gate admission and drain before closing |
| `DataSource` bean holds the old Hikari instance directly | Repositories continue calling the closed pool | Inject a wrapper that can swap delegates |
| Creating a new pool without validating | Pod Ready when the database is unreachable | Test connection before install/readiness |
| Reusing password from checkpoint | Credentials rotated or token expired | Read new secret/token after restore |
| Relying only on keepalive | Does not handle the period when the JVM is stopped | Close/recreate pool according to CRaC lifecycle |
| Retrying indefinitely in callback | Restore never completes | Deadline, backoff, and recovery policy |
| Workers resume before the pool | Mass task failures or retry storms | Resume in dependency order |
| Two lifecycle owners both close the pool | Double close or new pool overwritten | Choose a single owner |
| Health check only checks that DataSource object exists | Readiness reports false healthy | Validate a real connection |
| Retrying non-idempotent write transactions | Duplicate side effects | Design idempotency/reconciliation |

## 19. Recommended Operational Workflow

The lifecycle can be organized according to the diagram:

~~~text
BEFORE CHECKPOINT
  1. Readiness = REFUSING_TRAFFIC
  2. Stop HTTP/background admission
  3. Pause scheduler/message consumer
  4. Drain active JDBC operations
  5. Commit/rollback transaction
  6. Detach and close old pool
  7. CRaC checkpoint
          │
          ▼
TIME JVM IS STOPPED
  - Database may restart/failover
  - Network sessions may expire
  - Credential may rotate
          │
          ▼
AFTER RESTORE
  1. Keep JDBC admission closed
  2. Load current config and credentials
  3. Create a new HikariDataSource
  4. Validate a fresh JDBC connection
  5. Install the new pool
  6. Resume required workers
  7. Readiness = ACCEPTING_TRAFFIC
          │
          ▼
NORMAL OPERATION
  - Monitor pool and query metrics
  - Retire stale connections
  - Keep transaction and retry policies explicit
~~~

If the database is not yet ready, stop at the reconnect/validation phase, keep readiness false, and retry according to the deadline. Do not advertise Ready when the pool object has just been created but cannot yet connect.

## 20. Pre-Production Deployment Checklist

- [ ] Every JDBC request/worker goes through an admission gate or equivalent quiesce mechanism.
- [ ] In-flight transactions are drained before checkpoint.
- [ ] No open connections, statements, result sets, or cursors exist when creating the checkpoint.
- [ ] The old pool is detached and closed before checkpoint.
- [ ] `DataSource` is injected via a wrapper that can swap delegates.
- [ ] The new pool is created from current configuration and credentials.
- [ ] New connections are validated by the JDBC driver/pool.
- [ ] Readiness remains false during reconnect.
- [ ] Background workers only resume after the datasource is ready.
- [ ] Retries have timeouts, backoff, and a total time limit.
- [ ] Credential/config errors do not retry indefinitely with old values.
- [ ] The transaction manager uses the same datasource wrapper.
- [ ] There are no two lifecycle owners for the same pool.
- [ ] Checkpoint failures have a rollback/resume policy.
- [ ] Database restart, failover, and credential rotation have been tested.
- [ ] Connection leaks or non-draining transactions have been tested.
- [ ] Logs/metrics have been verified to contain no secrets.
- [ ] Integration tests have been run using a real CRaC runtime/engine.

## 21. Practice Conclusion

A JDBC connection is a resource dependent on the database session, socket, and network environment at the time it was created. When the JVM is restored, old `Connection` objects or pools may still sit in the heap but no longer represent a usable connection. `isClosed()` is not sufficient to determine that.

Design the lifecycle around closing the old pool and creating a new pool. Before checkpoint, stop admission, drain transactions and workers, then close the pool. After restore, retrieve current config/credentials, create a new Hikari pool, validate the connection, and only open readiness when the datasource is truly ready. With Spring, leverage `Lifecycle` integration where appropriate; for resources not managed by Spring, register an `org.crac.Resource`. Do not let two mechanisms manage the same pool.

Test database restarts, failovers, network interruptions, and credential rotation during checkpoint. When the new pool cannot yet connect, keep the application in a NotReady state and apply bounded retries. This approach protects transactions, avoids reusing stale connections, and helps the application recover in a controlled manner.

## 22. References

- [CRaC: Integrating CRaC in your Application](https://docs.azul.com/crac/usage/integrating-crac): closing and reopening database connections in callbacks.
- [CRaC: Implementing the CRaC API](https://crac.org/use/implement-crac/): registering resources and implementing `beforeCheckpoint`/`afterRestore`.
- [Spring Framework: JVM Checkpoint Restore](https://docs.spring.io/spring-framework/reference/integration/checkpoint-restore.html): lifecycle stop/start during checkpoint/restore.
- [Spring Boot: Checkpoint and Restore With the JVM](https://docs.spring.io/spring-boot/reference/packaging/checkpoint-restore.html): CRaC support in Spring Boot.
- [Java JDBC `Connection` API](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/Connection.html): `close`, `isClosed`, and `isValid`.
- [HikariCP](https://github.com/brettwooldridge/HikariCP): pool lifecycle, validation, `maxLifetime`, `keepaliveTime`, and timeout configuration.
- [Spring JDBC](https://docs.spring.io/spring-framework/reference/data-access/jdbc.html): `JdbcTemplate`, datasource, and transaction integration.

