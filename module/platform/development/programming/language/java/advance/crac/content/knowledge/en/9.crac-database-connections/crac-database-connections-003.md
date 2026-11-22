# HikariCP and CRaC Support Levels by Library Version

HikariCP is a popular JDBC connection pool in Java applications. The pool holds connections to the database so that the application can borrow and return a connection instead of creating a TCP connection and logging in to the database for each request. This approach reduces connection overhead, but creates a problem when using CRaC (Coordinated Restore at Checkpoint): a checkpoint can preserve the Java object state while the database, network, or firewall continues operating outside the process.

A connection sitting in the pool at checkpoint time may have already been closed by the database server, timed out, or lost its session state by the time the application is restored. Therefore, the pool needs to participate in the checkpoint/restore lifecycle: preparing and handling connections before checkpoint, then validating or recreating connections before the application receives traffic.

HikariCP added CRaC integration in the **5.1.0** line. When choosing a version, it is necessary to distinguish between the feature built into the library and the application managing the DataSource itself using a CRaC Resource. Using a newer version does not automatically prove that every part of the application is checkpoint-safe; the JDBC driver, in-flight transactions, callback ordering, and runtime configuration still need to be handled.

## 1. Why Do JDBC Connections Need to Be Handled at Checkpoint?

A JDBC connection is not just a Java object. Behind that object, there are usually:

- A TCP socket to the database server.
- Authentication and session state on the database.
- An open transaction or auto-commit state.
- Protocol state between the JDBC driver and the database.
- Timeouts, keepalives, and environment-dependent network state.

CRaC saves the process state to restore it later. During the time the process is checkpointed, the database server may continue running. The server may close the session due to an idle timeout, the network may change, or the connection may be dropped by a firewall.

Therefore, after restore, a Connection object still existing on the heap does not mean the connection on the database side is still valid.

### 1.1. What Does a Connection Pool Do?

When the application initializes HikariCP, the pool typically:

1. Reads the JDBC URL, username, credentials, and pool limits configuration.
2. Creates a number of initial connections or creates connections on demand.
3. Keeps idle connections so the next request can borrow one quickly.
4. Checks and removes connections that are no longer valid according to policy.
5. Closes connections when the pool shuts down.

Request flow:

~~~text
HTTP request
    │
    ▼
Service calls DataSource.getConnection()
    │
    ▼
HikariCP provides connection from pool
    │
    ▼
JDBC driver communicates with database
    │
    ▼
Service commits/rolls back and closes connection
    │
    ▼
Connection returns to pool for reuse
~~~

Normally, calling close() on a connection provided by HikariCP returns the connection to the pool instead of closing the physical socket immediately. The pool is the component that owns the physical connection lifecycle.

### 1.2. What Can Happen If a Checkpoint Keeps Old Connections?

~~~text
Before checkpoint
  HikariCP
    ├── Connection A ── Database session A
    ├── Connection B ── Database session B
    └── Connection C ── Database session C

Checkpoint
  JVM state is saved

During checkpoint
  Database continues running
  Sessions may time out or be closed
  Network may change

After restore
  Java objects Connection A/B/C still appear
  But database-side sessions may no longer be valid
~~~

If the application reuses old connections without proper handling, requests may encounter I/O errors, connection reset, communications link failure, or transaction errors. These errors often only appear after restore, even though the application worked normally before checkpoint.

## 2. CRaC Support Levels by HikariCP Version

The important milestone when choosing HikariCP is **5.1.0**, the version that introduced CRaC support into the library.

| Version line | CRaC support | Approach |
|---|---|---|
| Before 5.1.0, including 5.0.x | No built-in CRaC integration in HikariCP | The application must coordinate the pool lifecycle itself using Resource callbacks |
| 5.1.0 | Added CRaC integration | Use HikariCP's integration when running with a compatible CRaC runtime/API |
| Newer versions | Continue checking release notes and dependencies of the exact artifact | Prefer built-in integration, verify with the actual JDBC driver and JDK |

You should not just look at the Java target number or the major version of HikariCP to conclude that it supports CRaC. You need to check the exact artifact being resolved in the build, the CRaC API version present at runtime, and the guidance of the corresponding release.

### 2.1. Before HikariCP 5.1.0

Older versions do not automatically participate in the CRaC lifecycle. If the application checkpoints without handling the pool, old connections may be restored along with the process.

The application must manage on its own:

- Stopping accepting new requests and work.
- Waiting for in-flight transactions or JDBC operations to complete.
- Closing the pool before checkpoint.
- Recreating the pool after restore.
- Opening traffic only after the new pool can connect to the database.

Self-management requires a DataSource facade or a lifecycle coordinator so that services continue to use the same logical DataSource object while the underlying HikariDataSource delegate is replaced. If you only close a HikariDataSource and create a new object in the callback while other beans still hold references to the old object, the application may continue calling the closed pool.

### 2.2. HikariCP 5.1.0 and CRaC Integration

Starting from 5.1.0, HikariCP has integration to participate in the CRaC lifecycle. This integration is aimed at handling connection pool state in both the checkpoint and restore phases, reducing the need to write custom adapters for the pool's internal operations.

To use it properly:

- Use a HikariCP artifact that supports CRaC.
- Ensure the required CRaC API is present in the way that release requires.
- Run on a JDK distribution that supports CRaC.
- Do not register a second callback to close/open the same pool if the library already manages that pool.
- Still coordinate requests, transactions, and other application resources.

HikariCP's integration manages the pool lifecycle; it cannot automatically know whether all business transactions in the application have completed. The application must still bring the system to a safe state before checkpoint.

### 2.3. Newer Versions

When upgrading HikariCP, read the release notes of the exact version and check the dependency tree. Do not infer compatibility solely from the version being higher than 5.1.0.

Factors to confirm:

- Whether the HikariCP release retains CRaC integration and which API it uses.
- Whether the org.crac API version is compatible with the running CRaC JDK.
- Whether the JDBC driver supports recreating connections after restore.
- Whether the framework registers or manages other resource callbacks on its own.
- Whether pool configuration, timeouts, and validation are suitable for the database after the checkpoint duration.

A library upgrade can change Java requirements, dependencies, or internal behavior. Therefore, checkpoint/restore must be tested with the exact set of versions intended for deployment.

## 3. Identifying the HikariCP Version Used by the Application

Do not just look at the version declared in the build file. Maven or Gradle may select a different version due to dependency mediation or a version catalog.

### 3.1. Maven

If using Maven, inspect the dependency tree:

~~~bash
./mvnw -B dependency:tree -Dincludes=com.zaxxer:HikariCP
~~~

The result will show which dependency HikariCP is resolved from and what the final version is.

If the project uses dependency management or a BOM, check where versions are managed as well. Avoid declaring one version in one module and another version in another module unintentionally.

### 3.2. Gradle

With Gradle:

~~~bash
./gradlew dependencyInsight \
    --dependency HikariCP \
    --configuration runtimeClasspath
~~~

This command shows the selected version and why Gradle chose it. If the application runs in Spring Boot, check the dependency managed by Spring Boot's BOM before overriding the version.

### 3.3. Checking the CRaC API on the Classpath

If the HikariCP release uses the CRaC API as an optional dependency, the application needs to ensure the API is present at runtime. Check the dependency tree or runtime classpath to avoid a situation where compilation succeeds but the required class is missing when initializing the pool.

The CRaC JDK and the org.crac artifact are two related parts that should not be confused: the JDK distribution provides checkpoint/restore capability at runtime; the API dependency allows library and application code to reference Resource/Context types according to the mechanism used by that build. Follow the exact dependency requirements of the chosen HikariCP release, and do not add multiple different versions of org.crac to the classpath.

## 4. Declaring Dependencies

Maven example with HikariCP 5.1.0:

~~~xml
<dependencies>
    <dependency>
        <groupId>com.zaxxer</groupId>
        <artifactId>HikariCP</artifactId>
        <version>5.1.0</version>
    </dependency>

    <!-- Declare if the release/runtime requires the CRaC API on the application classpath. -->
    <dependency>
        <groupId>org.crac</groupId>
        <artifactId>crac</artifactId>
        <version>1.4.0</version>
    </dependency>

    <!-- Database JDBC driver, for example PostgreSQL. -->
    <dependency>
        <groupId>org.postgresql</groupId>
        <artifactId>postgresql</artifactId>
        <version>42.7.3</version>
        <scope>runtime</scope>
    </dependency>
</dependencies>
~~~

The versions in the example are illustrative versions so that dependencies are declared explicitly. When applying, choose versions compatible with the project's Java baseline, database server, JDBC driver, and CRaC JDK. If the framework's dependency management already manages the version, check the actual version before overriding.

Do not add the CRaC dependency blindly. First check the POM of the HikariCP version in use and determine which scope the org.crac API is declared with. If the library already brings the required API into runtime appropriately, do not create a conflicting API version. If it is optional/provided, the application needs to provide a compatible dependency according to the release documentation.

## 5. Configuring HikariCP in the Application

Example of creating a DataSource:

~~~java
import com.zaxxer.hikari.HikariConfig;
import com.zaxxer.hikari.HikariDataSource;

public final class DataSourceFactory {

    private DataSourceFactory() {
    }

    public static HikariDataSource create() {
        HikariConfig config = new HikariConfig();

        config.setJdbcUrl(
                System.getenv("DB_JDBC_URL"));
        config.setUsername(
                System.getenv("DB_USERNAME"));
        config.setPassword(
                System.getenv("DB_PASSWORD"));

        config.setPoolName("orders-pool");
        config.setMaximumPoolSize(10);
        config.setMinimumIdle(2);
        config.setConnectionTimeout(30_000);
        config.setValidationTimeout(5_000);
        config.setMaxLifetime(1_800_000);
        config.setKeepaliveTime(120_000);

        return new HikariDataSource(config);
    }
}
~~~

The values above only illustrate how to configure it. Choose pool size, timeout, and lifetime based on the database's connection limits, actual load, number of application instances, and network latency.

Some notable parameters:

| Parameter | Meaning |
|---|---|
| maximumPoolSize | Maximum number of connections in the pool |
| minimumIdle | Target number of idle connections the pool tries to maintain |
| connectionTimeout | Maximum time to wait to borrow a connection |
| validationTimeout | Maximum time for a connection validation operation |
| maxLifetime | Maximum lifetime of a connection in the pool |
| keepaliveTime | Interval for checking/keeping idle connections alive when configuration allows |

These parameters help manage the pool while the application is running normally. They do not replace CRaC callbacks and do not guarantee that old connections will be valid after restore.

## 6. Pool Lifecycle When Using CRaC

The desired lifecycle can be modeled as follows:

~~~text
Application starts
      │
      ▼
HikariDataSource creates pool
      │
      ▼
Application READY
      │
      │ checkpoint requested
      ▼
Stop accepting new requests
      │
      ▼
Wait for in-flight transactions/JDBC work
      │
      ▼
CRaC beforeCheckpoint
      │
      ▼
HikariCP prepares pool/connections
      │
      ▼
Process checkpoint
      │
      ▼
Process paused duration
      │
      ▼
Restore process
      │
      ▼
CRaC afterRestore
      │
      ▼
HikariCP restores pool/connections
      │
      ▼
Check database and dependencies
      │
      ▼
Application READY again
~~~

With HikariCP that has CRaC integration, the library participates in handling the pool lifecycle. With older versions, the application must implement the preparation and restoration steps itself. In both cases, draining requests and transactions is the application's responsibility.

### 6.1. Before Checkpoint

The application should:

1. Switch readiness to NOT_READY so the load balancer stops sending new requests.
2. Stop accepting new work from message consumers or schedulers.
3. Wait for requests currently using JDBC to finish within a bounded time.
4. Ensure transactions have been committed or rolled back.
5. Let HikariCP perform its pool handling according to the integration of the version in use.
6. Allow the checkpoint to proceed only when required resources have reached a safe state.

Do not close the pool while a request is still holding a connection. If an open transaction is snapshotted, the application may restore a connection object, but the transaction on the database side may have already timed out or been rolled back.

### 6.2. After Restore

After restore, the application needs to:

1. Let HikariCP's callback complete according to the registered resource order.
2. Confirm that the pool can provide a new connection.
3. Verify the database endpoint, credentials, and network.
4. Restore services that depend on the database.
5. Switch readiness to READY only after required dependencies are operational.

Do not manually invoke HikariCP's callbacks. The CRaC runtime invokes callbacks according to the lifecycle. If you need to check the pool, use a health check or borrow a test connection and close it to return it to the pool.

## 7. Do Not Manage the Same Pool Twice

When using a HikariCP version with CRaC integration, avoid creating another independent Resource callback just to close and reopen the same pool. Two lifecycle managers controlling the same HikariDataSource can lead to:

- One callback closes the pool first, while another callback tries to use the closed pool.
- The pool is initialized twice after restore.
- Connections are closed repeatedly or internal executors are stopped at the wrong time.
- Callback ordering between the pool and services becomes incorrect.
- The application marks itself READY before the pool is actually ready.

Divide ownership clearly:

| Component | Responsibility |
|---|---|
| HikariCP CRaC integration | Manages the internal lifecycle of the connection pool |
| Application/service | Stops accepting requests, drains transactions and work |
| Application's resource coordinator | Coordinates other resources and readiness |
| JDBC driver | Creates and executes connections according to the database protocol |
| Database server | Manages server-side sessions, transactions, and connections |

If using an older HikariCP without integration, only one adapter should own closing/opening the pool. The adapter must coordinate with dependency injection so that all services continue using the same DataSource facade, even though the HikariDataSource delegate is replaced after restore.

## 8. Self-Managing HikariCP in Versions Without CRaC Integration

For HikariCP prior to 5.1.0, you can create a CRaC Resource adapter. Architecture pattern:

~~~text
Service
   │
   ▼
RestartableDataSource (DataSource facade)
   │
   ▼
Current HikariDataSource
   │
   ▼
Database

beforeCheckpoint:
  1. Mark facade unavailable
  2. Drain application work
  3. Close current HikariDataSource
  4. Checkpoint

afterRestore:
  1. Create a new HikariDataSource
  2. Validate a connection
  3. Publish new delegate
  4. Mark facade available
~~~

The key point is that services depend on a stable facade, rather than directly holding the delegate that will be replaced.

Illustrative pseudocode:

~~~java
public final class RestartableDataSource
        implements javax.sql.DataSource, org.crac.Resource {

    private final HikariConfig config;
    private volatile HikariDataSource delegate;

    public RestartableDataSource(HikariConfig config) {
        this.config = new HikariConfig(config);
        this.delegate = new HikariDataSource(this.config);
        Core.getGlobalContext().register(this);
    }

    @Override
    public synchronized void beforeCheckpoint(
            Context<? extends Resource> context) {
        HikariDataSource current = delegate;
        delegate = null;

        if (current != null) {
            current.close();
        }
    }

    @Override
    public synchronized void afterRestore(
            Context<? extends Resource> context) throws Exception {
        HikariDataSource restored =
                new HikariDataSource(config);

        try (Connection connection = restored.getConnection()) {
            if (!connection.isValid(5)) {
                throw new SQLException(
                        "Database connection validation failed");
            }
        } catch (Exception failure) {
            restored.close();
            throw failure;
        }

        delegate = restored;
    }

    private HikariDataSource currentDataSource() throws SQLException {
        HikariDataSource current = delegate;

        if (current == null) {
            throw new SQLException(
                    "DataSource is not ready during checkpoint/restore");
        }

        return current;
    }

    @Override
    public Connection getConnection() throws SQLException {
        return currentDataSource().getConnection();
    }

    // Remaining DataSource methods must delegate to
    // currentDataSource(), including getConnection(username, password),
    // log writer, login timeout, unwrap, and isWrapperFor.
}
~~~

This is pseudocode describing ownership and sequence, not a complete DataSource implementation to copy verbatim. A real implementation must implement all DataSource methods, manage thread safety, and ensure no new request obtains the delegate while the callback is closing the pool.

In addition, HikariConfig contains credentials and connection configuration. Do not write passwords to logs or shared checkpoint artifacts. After restore, consider reading fresh credentials from a secret provider if credentials may change while the process is paused.

### 8.1. Why Not Just Call close and Create a New Pool in the Callback?

If the application injects a HikariDataSource directly into multiple services, creating a new object after restore does not automatically change the references that the services already hold. The services will still call the old closed object.

A DataSource facade solves this problem by keeping a stable reference in dependency injection and swapping the internal delegate. Another option is to let the application context manage bean replacement, but you must ensure every consumer receives the new reference and lifecycle hooks do not overlap with CRaC callbacks.

## 9. JDBC Transactions and In-Flight Requests

HikariCP's CRaC integration cannot replace business transaction management. Before checkpoint, the application needs to handle in-flight requests.

Example of a request:

~~~text
HTTP request starts
      │
      ▼
Borrow JDBC connection
      │
      ▼
BEGIN transaction
      │
      ▼
Update data
      │
      ▼
COMMIT
      │
      ▼
Return connection to pool
~~~

A checkpoint should be requested after the request completes, the connection has been returned to the pool, and there are no remaining transactions that need to be preserved.

If a checkpoint occurs during a transaction:

- The database may still hold the transaction while the client process is paused.
- The server may roll back the transaction when the session times out.
- Restore may not be able to recover the old session.
- The application may not know whether the business operation was committed if the connection is lost at that exact moment.
- Retrying the request may cause duplicate execution if the operation is not idempotent.

For data write operations, use clear transaction boundaries and idempotency keys or deduplication mechanisms on retry. CRaC does not provide a distributed transaction snapshot between the JVM and the database.

## 10. Pool Configuration and Database Connection Limits

CRaC can cause multiple instances to restore almost simultaneously. If all instances recreate their connection pools at the same time, the database may receive a connection burst.

For example, 10 instances, each with a maximumPoolSize of 20, can generate a maximum demand of 200 connections. If the database only allows 100 application connections, simultaneous restore may cause some pools to fail to initialize.

When designing:

- Calculate the maximum total connections across all replicas.
- Reserve headroom for admin, migrations, monitoring, and other applications.
- Choose a reasonable minimumIdle to avoid creating too many connections immediately after restore.
- Use bounded retry/backoff if the database is temporarily unavailable.
- Do not let all instances retry synchronously and continuously.
- Choose a readiness policy so an instance only receives traffic when the pool is operational.

Example:

| Replica count | Maximum pool size | Total maximum connections |
|---:|---:|---:|
| 2 | 10 | 20 |
| 5 | 10 | 50 |
| 10 | 20 | 200 |
| 20 | 10 | 200 |

This is a theoretical limit calculation; the pool may not open all connections immediately if minimumIdle is low. However, database capacity still needs to be sized according to maximumPoolSize multiplied by the number of instances that can run concurrently.

## 11. Verifying HikariCP Behavior with CRaC

Do not conclude CRaC support just because the application builds successfully or the JVM restores successfully. The pool and database must be tested after restore.

### 11.1. Basic Scenario

1. Confirm the HikariCP version using the dependency tree.
2. Confirm that the CRaC JDK and CRIU work in the test environment.
3. Start the database and the application.
4. Send a request that executes a query so the pool has a connection.
5. Check the health endpoint and pool logs.
6. Bring the application to a state with no remaining transactions or requests using a connection.
7. Create a checkpoint.
8. Restore the process.
9. Send a new query through the service.
10. Verify that the pool provides a new connection and the query succeeds.

### 11.2. Checking Logs and Pool State

You can observe the pool via HikariPoolMXBean if MBeans are enabled or by accessing it through the DataSource:

~~~java
HikariPoolMXBean pool =
        dataSource.getHikariPoolMXBean();

if (pool != null) {
    System.out.println(
            "active=" + pool.getActiveConnections());
    System.out.println(
            "idle=" + pool.getIdleConnections());
    System.out.println(
            "total=" + pool.getTotalConnections());
    System.out.println(
            "waiting=" + pool.getThreadsAwaitingConnection());
}
~~~

These metrics help understand how many active, idle, total connections the pool currently has and how many threads are waiting. Do not use a single metric snapshot to conclude that the pool is ready; combine it with a health check that executes an actual query.

### 11.3. Failure Scenarios to Test

| Scenario | Expected result to verify |
|---|---|
| Database temporarily unavailable at restore | Pool does not falsely report READY; errors are observable and retried according to policy |
| Expired credentials | Application refreshes credentials or fails restore in a controlled manner |
| Old connection closed by database | Post-restore requests use a new valid connection |
| In-flight request when preparing checkpoint | Application drains or rejects checkpoint according to policy |
| Multiple replicas restore simultaneously | Database does not exceed its connection limit |
| Older HikariCP self-managed with an adapter | No request calls a closed delegate |
| HikariCP with CRaC integration | No duplicate pool close/open callback is registered |

Test against a dedicated database or staging environment. Log the HikariCP version, JDBC driver, CRaC JDK, database server, and checkpoint/restore timestamps so that results are reproducible.

## 12. Common Errors

| Symptom | Possible cause | Resolution |
|---|---|---|
| Post-restore request encounters connection reset | Old connection is no longer valid | Confirm that HikariCP CRaC integration or adapter handled the pool |
| Missing org.crac class at initialization | API dependency is not on the runtime classpath | Check the POM, dependency tree, and scope |
| Pool is closed but service still calls old reference | DataSource delegate was replaced improperly | Use a stable facade or framework-managed bean lifecycle |
| Pool creates too many connections after restore | minimumIdle, replica count, or warm-up causes a burst | Adjust pool sizing, stagger restores, and use backoff |
| Checkpoint hangs | Requests/transactions or resources have not drained | Check thread dumps, timeouts, and callback ordering |
| Database refuses connection | Credentials, network, or connection limit | Check secrets, network, and database capacity |
| Pool is closed/opened twice | Both HikariCP integration and a custom Resource are present | Choose a single owner for the pool lifecycle |
| Application is READY before queries succeed | Readiness does not check the database | Mark READY only after an actual health check |

## 13. Choosing the Right Integration Approach

You can use the following selection rule:

~~~text
Identify HikariCP runtime version
             │
             ▼
        Version < 5.1.0?
          /       \
        Yes        No
        │            │
        ▼            ▼
Self-manage pool   Check that release has
via CRaC Resource  CRaC integration
        │            │
        ▼            ▼
Use stable         Ensure CRaC API/runtime
DataSource facade  meets requirements
        │            │
        └─────┬──────┘
              ▼
     Drain requests/transactions
              │
              ▼
      Checkpoint and restore
              │
              ▼
      Real query/health check
              │
              ▼
       Only then mark READY
~~~

If using HikariCP 5.1.0 or later, prefer the CRaC integration included in the release and verify the behavior of that exact version. If on an older version, build an adapter to manage the pool explicitly. In both cases, avoid having two components close/open the same pool.

## 14. Points to Record When Upgrading HikariCP

When upgrading from an older version to 5.1.0 or a newer version, record:

- Old and new versions of HikariCP.
- JDBC driver and database server versions.
- JDK vendor, version, build, and CRaC capability.
- org.crac API version if the application declares the dependency.
- How the pool participates in callbacks in the release being used.
- Whether any custom Resource callback was previously managing the pool.
- Registration order among the pool, services, consumers, and HTTP server.
- Query results before checkpoint and after restore.
- Active/idle/total connection counts and time until the pool is ready after restore.

If moving to a release with built-in integration, consider removing the old adapter after confirming that the new library actually manages the pool. Do not let a custom callback and an internal callback perform lifecycle operations simultaneously.

## 15. Operational Principles

HikariCP helps manage JDBC connections efficiently during the normal lifecycle of an application. When adding CRaC, the connection pool must be treated as a resource whose lifecycle is tied to the database server and network outside the process.

Identify the exact HikariCP runtime version. Starting from 5.1.0, the library has CRaC integration; older versions require the application to coordinate the pool lifecycle itself. Then, coordinate pool management with draining requests and transactions, restoring dependencies in order, and opening traffic only when an actual query succeeds.

The decisive point is the state of the database connection after restore. The continued existence of a Java object does not prove that the database-side session is still alive. A restore is only complete from the application perspective when HikariCP can provide valid connections and critical JDBC operations can run normally.
