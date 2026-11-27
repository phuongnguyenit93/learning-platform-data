# The Role of r2dbc-pool and When to Use It

In a Spring Data Relational R2DBC application, each database access operation requires a connection provided by the R2DBC driver. Creating a physical connection can be time-consuming and resource-intensive: the application has to open a network connection, authenticate, establish a session, and consume part of the connection limit allowed by the database.

`r2dbc-pool` is a pooling library for R2DBC. It manages a set of reusable connections, allowing multiple operations to borrow a connection for a short duration and return it to the pool after completion. The pool helps limit the number of concurrent connections and reduces the overhead of repeatedly creating connections.

A pool is not a mandatory requirement for using Spring Data R2DBC. An application should only add it when the workload pattern, connection cost, or database resource limits show that reusing connections is beneficial. This lesson explains the role, connection lifecycle, prerequisites, configuration, and operational aspects to monitor.

## 1. ConnectionFactory and Connections in R2DBC

The R2DBC SPI defines `ConnectionFactory` as the component that creates connections to the database. Each database vendor's driver provides a way to create a `ConnectionFactory` corresponding to that database's protocol and connection configuration.

For example, an application connecting to PostgreSQL can use the `r2dbc-postgresql` driver; when `create()` is called on the connection factory, the driver creates a connection to work with the database. If the application frequently creates and closes connections, each occurrence can incur physical connection overhead.

Simplified lifecycle of a connection without pooling:

~~~text
Application
   |
   | ConnectionFactory.create()
   v
R2DBC driver
   |
   | open physical connection
   v
Database
   |
   | execute SQL statement
   v
Application closes connection
   |
   v
Physical connection is released
~~~

`ConnectionFactory` is the common entry point that Spring R2DBC, `DatabaseClient`, `R2dbcEntityTemplate`, repositories, and the transaction manager can use. These components do not need to know the network protocol details of each database.

## 2. What Does r2dbc-pool Do?

`r2dbc-pool` provides a `ConnectionPool` that acts as a `ConnectionFactory`. The pool wraps a driver-provided connection factory, manages physical connections, and issues a logical connection for each application request.

When the application calls `create()` on the pool:

1. The pool looks for an idle and valid connection.
2. If a suitable connection is available, the pool issues that connection to the caller.
3. If no idle connection is available and the pool has not reached its limit, the pool can create a new physical connection.
4. If the pool has reached its limit, the request must wait for a connection to be returned or fail when the wait time expires.
5. When the caller closes the logical connection, the pool reclaims the lease and returns the physical connection to a reusable state, provided the connection is still valid.

High-level diagram:

~~~text
                 +-------------------------+
                 |  Spring Data R2DBC      |
                 |  DatabaseClient         |
                 |  Repository / Service   |
                 +------------+------------+
                              |
                              v
                    +------------------+
                    | ConnectionPool   |
                    | max-size = 20    |
                    +---+----------+---+
                        |          |
                    idle         in-use
                  connection   connection
                        |          |
                        v          v
                  +--------------------+
                  |   R2DBC driver     |
                  +---------+----------+
                            |
                            v
                         Database
~~~

The pool manages borrowing and returning connections. It does not replace the driver, execute SQL on behalf of repositories, or decide transaction isolation on its own.

### 2.1. Reusing Physical Connections

A physical connection can be used for multiple operations at different times. After an operation completes and the connection is returned to the pool, the next request can borrow that connection again.

Reusing connections reduces the number of new sessions opened, lowers connection setup latency, and avoids creating too many concurrent connections. The benefit is clearer when an application handles many short requests that continuously access the same database.

A connection borrowed from the pool is a lease. When the operation finishes, the application must close the lease so the pool knows the connection can be reused. In Spring Data R2DBC, Spring abstractions manage the connection lifecycle during standard repository and transaction operations. When working directly with the R2DBC SPI, developers must ensure the connection is closed on every termination path, including when the publisher errors or is cancelled.

### 2.2. Limiting Concurrent Connections

The pool has a `max-size` limit. When the limit is reached, the pool does not continue opening an unbounded number of physical connections. New requests must wait for a connection to be returned or receive a timeout error if they wait too long.

This protects the database from an application creating an uncontrolled number of sessions. However, a `max-size` that is too low can cause requests to queue up; a `max-size` that is too high can exhaust database connections or increase resource contention.

### 2.3. Managing Unusable Connections

Connections can become invalid because of a database restart, network interruption, server-closed session, or exceeding maximum age. The pool provides mechanisms to limit lifetime, idle time, and validate connections according to configuration.

When a connection is no longer suitable for reuse, the pool can discard it and create a new connection as needed. Validation can add a check to the connection acquisition path, so it is important to choose a strategy suited to the driver and environment.

## 3. When Should You Use r2dbc-pool?

Adding a pool should be driven by the application's operational characteristics, not merely because the project uses R2DBC.

### 3.1. Applications Serving Many Concurrent Requests

An API server often has many requests accessing the database concurrently. If every operation creates a new physical connection, connection overhead can grow quickly and concurrent sessions become difficult to control.

A pool is suitable when:

- The application receives many short, repeated requests accessing the same database.
- Multiple reactive tasks need connections during overlapping time intervals.
- Connection creation cost is significant compared to query execution time.
- The database has a connection limit that must be shared across multiple application instances.
- You want a clear upper bound on the number of operations holding connections.

### 3.2. Database or Infrastructure Connection Limits

Databases typically have a session/connection limit. Even an application with multiple instances can generate a large total number of connections if each instance opens only a moderate number.

The pool helps enforce a per-instance limit. When sizing, you must calculate the total number of connections that can be opened across all instances, rather than looking only at the `max-size` of a single process.

### 3.3. High Connection Creation Cost

If the database is accessed over a network, involves authentication steps, or uses TLS setup, continually creating new connections can introduce unnecessary latency and load. Reusing connections can improve response times and reduce work on the database.

Actual benefits depend on the driver, database, network, request lifespan, and how the application uses connections. Measure before and after enabling the pool to verify that the change helps.

### 3.4. Limiting Database Load from the Application

A pool acts as a throttle on the number of connections used by the application. When the database has reached an appropriate load level, pool limits can cause requests to wait on the application side instead of opening more sessions and overloading the database.

This is not a complete automatic load-control mechanism. If connection hold times are too long or the number of waiting requests keeps growing, you must address the root cause in queries, transactions, backpressure, or request rate limiting.

## 4. When Is a Pool Not Yet Necessary?

A pool adds a dependency, configuration, and state that must be monitored. There are cases where it is not needed:

- One-off applications performing a small task with few database connections.
- Command-line tools or short batch jobs with very few database operations.
- Simple test environments that do not need to simulate concurrent load or a production pool.
- Applications with very low request volume where connection creation is not a bottleneck.
- Environments where infrastructure already provides connection pooling at another layer and the application does not need a second pool.
- Special requirements needing a dedicated connection per operation where pooling has been verified to provide no benefit.

Not using a pool does not mean the application cannot use Spring Data R2DBC. The driver can create connections directly via the connection factory. Simply choose the connection strategy suited to your workload and operational model.

If an application uses JDBC with HikariCP, do not assume HikariCP also manages R2DBC connections. HikariCP manages JDBC `DataSource`; `r2dbc-pool` manages R2DBC `ConnectionFactory`. These are two different APIs and two different types of connections.

## 5. Prerequisites for Using r2dbc-pool

For the pool to work, the application must meet the following prerequisites:

1. Have the R2DBC SPI and the driver corresponding to the database management system.
2. Add the `io.r2dbc:r2dbc-pool` library to the runtime classpath.
3. Create a pool wrapping the driver's connection factory, or enable pool auto-configuration if supported by the framework.
4. Configure pool limits and timeouts suitable for the database and the number of application instances.
5. Have Spring components share the connection factory wrapped by the pool.
6. Ensure connections are returned to the pool after operations complete.
7. Have a way to monitor pool health, connection acquisition errors, and wait times.

`r2dbc-pool` does not provide a database driver on its own. Adding only the pool without the corresponding driver still leaves the application unable to connect to the specific database.

You should also avoid creating one pool for repositories, another for the transaction manager, and another for `DatabaseClient` if operations need to share the same transaction. Use the same pool-wrapped connection factory for components belonging to the same data access configuration.

## 6. Declaring Dependencies

`r2dbc-pool` is a separate dependency that can be declared using Gradle or Maven. When the application uses Spring Boot, let the Spring Boot BOM manage the compatible version if the BOM manages that artifact.

### 6.1. Gradle Groovy DSL

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-r2dbc'
    runtimeOnly 'org.postgresql:r2dbc-postgresql'
    runtimeOnly 'io.r2dbc:r2dbc-pool'
}
~~~

In this example:

- The starter provides Spring Data R2DBC integration.
- The PostgreSQL driver creates connections to PostgreSQL.
- `r2dbc-pool` provides the pool management classes.

If source code directly references `ConnectionPool` or `ConnectionPoolConfiguration`, declare `r2dbc-pool` with `implementation` so those classes are present on the compile classpath.

### 6.2. Gradle Kotlin DSL

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-r2dbc")
    runtimeOnly("org.postgresql:r2dbc-postgresql")
    runtimeOnly("io.r2dbc:r2dbc-pool")
}
~~~

There is no need to specify an explicit version if the project's plugin or BOM already manages dependency versions. If the project does not use a BOM, select an `r2dbc-pool` version compatible with the R2DBC SPI and driver in use.

### 6.3. Maven

When using the Spring Boot parent or importing the corresponding BOM:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-r2dbc</artifactId>
    </dependency>

    <dependency>
        <groupId>org.postgresql</groupId>
        <artifactId>r2dbc-postgresql</artifactId>
        <scope>runtime</scope>
    </dependency>

    <dependency>
        <groupId>io.r2dbc</groupId>
        <artifactId>r2dbc-pool</artifactId>
        <scope>runtime</scope>
    </dependency>
</dependencies>
~~~

If Java code directly uses `r2dbc-pool` classes, omit the `runtime` scope or use the default `compile` scope so the source code can compile.

### 6.4. Do Not Pin Arbitrary Versions When Using a BOM

The pool, R2DBC SPI, and driver must be compatible. When a project uses the Spring Boot BOM, prefer the versions managed by the BOM. Only override a version when there is a specific reason, compatibility has been verified, and integration tests have passed.

When dependency resolution issues occur, inspect the dependency tree to see which versions of `r2dbc-spi`, `r2dbc-pool`, and the driver are actually selected. A version may be pulled in transitively from another dependency.

## 7. Enabling the Pool in Spring Boot

With Spring Boot supporting R2DBC pool auto-configuration, an application can add the `r2dbc-pool` dependency and declare properties under `spring.r2dbc.pool`.

PostgreSQL example:

~~~yaml
spring:
  r2dbc:
    url: r2dbc:postgresql://localhost:5432/appdb
    username: app_user
    password: ${DB_PASSWORD}
    pool:
      enabled: true
      initial-size: 5
      max-size: 20
      max-idle-time: 30m
      max-life-time: 2h
      max-acquire-time: 5s
      max-create-connection-time: 5s
~~~

Meaning of the main properties:

| Property | Role |
|---|---|
| `enabled` | Enables pool configuration if the Spring Boot version in use supports this property |
| `initial-size` | Number of connections the pool attempts to initialize initially |
| `max-size` | Maximum number of connections managed by the pool |
| `max-idle-time` | Duration a connection is allowed to remain idle before it becomes eligible for eviction |
| `max-life-time` | Maximum lifetime of a connection in the pool |
| `max-acquire-time` | Maximum time a request waits to borrow a connection |
| `max-create-connection-time` | Maximum time allocated for creating a new connection |

Property names and support depend on the Spring Boot version. Check the configuration metadata and documentation for the exact project version; do not copy a property from a newer version to an older version without verifying.

If `r2dbc-pool` is not on the runtime classpath or pooling is not enabled according to the Boot version's mechanism, the application may still connect using an unpooled driver connection factory. Therefore, verify the actual effective configuration and runtime dependencies rather than just looking at the YAML file.

### 7.1. Using Environment-Specific Profiles

Pool parameters can differ between development, testing, and production environments. You can use profiles or environment variables to adjust limits without changing source code.

Example:

~~~yaml
spring:
  config:
    activate:
      on-profile: production
  r2dbc:
    pool:
      enabled: true
      initial-size: 5
      max-size: 30
      max-acquire-time: 5s
~~~

The numbers above are illustrative only. Production `max-size` must be calculated from the database connection limit, number of application instances, number of services sharing the database, and connections reserved for administrative tasks.

Do not place credentials directly in profile files committed to the repository. Use environment variables or a secret manager.

## 8. Configuring the Pool in Java Without Auto-Configuration

In Spring Framework applications not using Spring Boot, or when needing to create a pool manually with custom rules, you can use the `r2dbc-pool` API.

High-level example:

~~~java
ConnectionFactory driverConnectionFactory =
        ConnectionFactories.get(connectionFactoryOptions);

ConnectionPoolConfiguration poolConfiguration =
        ConnectionPoolConfiguration.builder(driverConnectionFactory)
                .initialSize(5)
                .maxSize(20)
                .maxIdleTime(Duration.ofMinutes(30))
                .maxLifeTime(Duration.ofHours(2))
                .maxAcquireTime(Duration.ofSeconds(5))
                .build();

ConnectionPool connectionPool =
        new ConnectionPool(poolConfiguration);
~~~

`driverConnectionFactory` is the connection factory provided by the driver. `ConnectionPoolConfiguration` describes connection limits and lifecycle. `ConnectionPool` wraps the original factory and becomes the connection factory used by the application.

Imports and how `ConnectionFactoryOptions` is created depend on the driver, so the example focuses on pool configuration. When registering a pool as a Spring bean, manage its lifecycle so the pool is disposed when the application stops:

~~~java
@Bean(destroyMethod = "dispose")
ConnectionPool connectionPool(ConnectionFactory driverConnectionFactory) {
    ConnectionPoolConfiguration configuration =
            ConnectionPoolConfiguration.builder(driverConnectionFactory)
                    .initialSize(5)
                    .maxSize(20)
                    .maxIdleTime(Duration.ofMinutes(30))
                    .maxLifeTime(Duration.ofHours(2))
                    .maxAcquireTime(Duration.ofSeconds(5))
                    .build();

    return new ConnectionPool(configuration);
}
~~~

In a Boot application where the pool is already auto-configured, do not create a second pool bean just to repeat configuration. Creating a manual bean can cause the application to have two layers of pooling or cause components to use different connection factories. Only use manual configuration when intentionally replacing or taking over auto-configuration.

When using a manual pool, the transaction manager must receive the pool-wrapped connection factory. Repositories and `DatabaseClient` must also use that same factory so operations within a transaction can share the connection managed by the transaction manager.

## 9. Choosing Pool Size

`max-size` is one of the parameters with the greatest impact on application behavior. There is no single right value for every system.

### 9.1. Calculating the System-Wide Connection Budget

Suppose an application runs 4 instances and each instance has `max-size` of 20. That application alone can open at most:

\[
4 \times 20 = 80 \text{ connections}
\]

If the database has a limit of 150 connections, room must still be reserved for other services, migration tasks, monitoring, administration, and external connections.

You can use a simple budgeting formula:

\[
C_{\text{app}} = N_{\text{instances}} \times P_{\text{max}}
\]

Where:

- \(N_{\text{instances}}\) is the number of application instances that can run concurrently, including during autoscaling.
- \(P_{\text{max}}\) is `max-size` per instance.
- \(C_{\text{app}}\) is the maximum number of connections the application can occupy.

The total budget must satisfy:

\[
C_{\text{app}} + C_{\text{other}} + C_{\text{reserve}}
\leq C_{\text{database}}
\]

`C_other` represents connections from other services and jobs; `C_reserve` is the reserve for administration and load fluctuations; `C_database` is the safe usable connection limit.

### 9.2. Balancing Wait Time and Database Load

A pool that is too small can force requests to queue for connections even when the database has spare capacity. A pool that is too large can overwhelm the database with too many concurrent queries, increasing lock contention, context switching, and response times.

Start with a conservative limit, then measure:

- Number of currently borrowed connections.
- Number of idle connections.
- Acquire wait time.
- Acquire timeout rate.
- Query and transaction durations.
- Database CPU, memory, and connection limit usage.

Increasing pool size does not fix slow queries, transactions holding connections too long, or a saturated database. In those cases, optimize SQL, indexes, transaction boundaries, or reduce concurrent work.

### 9.3. Distinguishing Request Concurrency from Database Concurrency

A server may receive hundreds of concurrent requests, yet not every request holds a database connection at the same time. Some requests may be authenticating, reading cache, calling other services, or waiting for data.

Conversely, one request may execute multiple sequential queries and hold a connection for the entire transaction. Therefore, do not mechanically set `max-size` equal to thread count or maximum request count.

Measure the actual number of overlapping database operations and connection hold durations. In reactive applications, a small thread count does not mean a small number of connections is needed.

## 10. Wait Timeouts, Idle Time, and Connection Lifetime

### 10.1. Acquire Timeout

`max-acquire-time` limits how long a request waits to borrow a connection. If the pool has no available connections and none are returned within that duration, the operation can fail.

A timeout that is too short causes requests to fail during brief load spikes. A timeout that is too long leaves requests waiting, consuming upstream resources and potentially building large queues. Align the acquire timeout with overall request timeouts and response time targets.

Acquire timeouts are also an operational signal. If they spike, check for pool saturation, slow queries, connection leaks, database overload, and long-running transactions.

### 10.2. Idle Timeout

`max-idle-time` limits how long a connection can remain unused. The pool can evict connections that have been idle too long to reduce resources held on the database.

This value must be chosen alongside the idle timeout policies of the database, firewall, proxy, and load balancer. If infrastructure closes a connection sooner than the pool expects, the pool may retain a dead connection and hit errors when borrowing it again.

### 10.3. Maximum Lifetime

`max-life-time` limits the lifespan of a connection. Periodically replacing connections helps avoid keeping a single session open too long when infrastructure enforces lifetime limits or rotates endpoints.

Do not set lifetime too short, or the pool will constantly close and open new connections. Do not set it too long if the database or proxy enforces connection closure by age.

### 10.4. Connection Creation Time

`max-create-connection-time` limits how long creating a new connection can take. If the database is unresponsive, DNS fails, or the network is slow, a connection creation attempt should not wait indefinitely.

Creation timeout differs from acquire timeout: acquire timeout bounds total wait time to obtain a connection; create timeout specifically bounds the process of opening a new connection. Read the documentation for your pool version to understand how both limits are applied.

## 11. Validation and Invalid Connections

A connection may have been closed by the database or infrastructure while idle. The pool needs to know which connections are still usable before handing them out again.

Depending on the `r2dbc-pool` version and driver, you can configure validation depth or a validation query. Validation can inspect the connection at the protocol level or execute a verification query. Property names and support levels depend on the API, driver, and Spring Boot version.

If using a validation query, pick a lightweight statement that is valid for the database and causes no data modifications. For example, `SELECT 1` works on many databases, though you should verify with your specific driver and database.

Validating too frequently can add extra queries and increase acquire latency. Do not enable a heavy check on every borrow if the driver and infrastructure already provide a more suitable mechanism.

The pool cannot guarantee every connection is alive at all times. The network can drop immediately after validation succeeds. The application still needs to handle connection errors and apply bounded retries for operations that are safe to retry.

## 12. Pooling and Reactive Transactions in Spring Data R2DBC

Spring uses `ConnectionFactory` to obtain connections for repositories, `DatabaseClient`, and the transaction manager. When pooling is enabled, the connection factory used by these components is the pool-wrapped factory.

In a reactive transaction, the transaction manager obtains a connection and attaches the resource to the Reactor Context. Operations within the same transaction use that managed connection. When the transaction ends, the connection is closed according to the R2DBC API and the pool reclaims the lease for reuse.

This leads to several rules:

- Use the same pool-wrapped connection factory for repositories, `DatabaseClient`, and `R2dbcTransactionManager` in the same configuration.
- Do not create an independent subscription via `subscribe()` to run queries that need to participate in a transaction.
- Do not store a connection in a service field or share a connection across requests.
- Do not manually close a connection while the transaction manager is still using it.
- Do not run operations concurrently on the same connection if the driver does not support it.
- Keep transactions short so connections are returned to the pool promptly.

The pool only manages connection resources. It does not automatically combine two statements into a transaction, does not replace `@Transactional` or `TransactionalOperator`, and does not prevent lost updates or isolation anomalies.

## 13. Connection Leaks and How to Prevent Them

A connection leak occurs when an application borrows a connection and never returns it to the pool. Over time, the count of borrowed connections rises even though operations have finished or are no longer progressing. The pool can run out of connections and new requests begin timing out.

Common causes:

- Calling `ConnectionFactory.create()` directly and forgetting to close the connection.
- Error handling or subscription cancellation paths failing to release the connection properly.
- Keeping transactions open for too long.
- Calling external services while holding a connection or lock.
- Creating a publisher without consuming or terminating it.
- Storing a connection to reuse across multiple requests.

When using the R2DBC SPI directly, ensure the connection is closed in all outcomes. For reactive resources, use abstractions that manage lifecycle or the `usingWhen` operator when managing asynchronous resources manually. Do not write a manual chain that only closes the connection on the success path.

With Spring Data R2DBC, prefer repositories, `DatabaseClient`, `R2dbcEntityTemplate`, and the transaction manager so Spring manages borrowing and returning connections.

## 14. Pooling Does Not Replace Backpressure or Request Limits

The pool limits the number of concurrently issued connections, but requests waiting for a connection can still accumulate. If the system receives requests faster than the database can process them, the acquire queue can grow and response times lengthen.

Combine pooling with:

- Limiting concurrent requests at the API or service layer.
- Using backpressure in reactive pipelines when supported by the data source.
- Setting timeouts for acquire and requests.
- Cancelling no-longer-needed work to release resources.
- Reducing slow queries and transaction hold durations.
- Using bulkheads or concurrency limits for high-load database tasks.

A pool is a resource limit at the connection layer, not a limit on total application requests.

## 15. Monitoring and Diagnosing the Pool

When enabling a pool in production, observe at least the following:

| Metric | Meaning |
|---|---|
| Acquired / allocated connections | Number of connections currently in use and total connections managed by the pool |
| Idle connections | Number of connections ready to be borrowed |
| Pending acquire | Number of requests waiting for a connection |
| Acquire latency | Time spent waiting to obtain a connection |
| Acquire timeout | Number of requests that failed to get a connection within the timeout |
| Connection creation | Rate and errors when creating new connections |
| Connection lifetime | Age and idle duration of connections |
| Query/transaction duration | How long connections are held during processing |

If pending acquire and acquire latency increase while the database still has spare resources, the pool may be too small or connections are being held too long. If the pool frequently hits max-size while the database is already saturated, enlarging the pool can worsen the situation; optimize queries and reduce concurrency instead.

If acquired connections stay high even during low request volume, investigate connection leaks, non-terminating publishers, or unclosed transactions. If connection creation rises steadily, check lifetime/idle policies, network errors, server-side session closures, and validation configuration.

Pool metrics can be integrated with a monitoring system if supported by the library version and metrics configuration. Specific metric names depend on the library version and registry used; verify the actual emitted metrics rather than assuming fixed names.

## 16. Common Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Adding `r2dbc-pool` without a driver | Pool cannot create connections to the database | Add the corresponding R2DBC driver |
| Assuming a pool is mandatory for every app | Unnecessary configuration and operational overhead | Use only when connection reuse and limits are needed |
| Using HikariCP to pool R2DBC | HikariCP manages JDBC `DataSource`, not R2DBC `ConnectionFactory` | Use `r2dbc-pool` for R2DBC |
| Not enabling the pool in Boot config | Application may continue using the driver factory directly | Check dependencies, properties, and Boot version auto-configuration |
| Setting `max-size` too large | Database exhausts connections or suffers excessive concurrent queries | Budget across all instances and services |
| Setting `max-size` too small | Requests queue up and hit acquire timeouts | Measure database concurrency and tune carefully |
| Setting acquire timeout too long | Requests wait too long, queues build up | Align timeouts with request SLAs and handle saturation |
| Failing to close connections | Pool exhausts connections due to leaks | Manage lifecycle via Spring or proper resource APIs |
| Unintentionally creating multiple pools for one database | Total connections exceed budget and transactions fail to share a factory | Use one intentional factory/pool per access configuration |
| Holding transactions during HTTP calls | Connections and locks are held too long | Move non-database work outside the transaction |
| Assuming pooling prevents concurrency anomalies | Data can still suffer lost updates or invariant violations | Use transactions, isolation, atomic SQL, versioning, or locking |
| Ignoring metrics | Slowdowns and timeouts become hard to diagnose | Monitor pending acquire, latency, pool size, and errors |

## 17. Decision and Rollout Process

When considering adding `r2dbc-pool`, you can follow this sequence:

1. Measure connection creation frequency, concurrent connections, connection latency, and database load.
2. Identify the database connection limit and the total number of application instances that can run.
3. Calculate the connection budget for the application, other services, and reserves.
4. If connection reuse is beneficial, add `io.r2dbc:r2dbc-pool` along with the corresponding R2DBC driver.
5. Enable the pool using the appropriate Spring Boot mechanism or configure `ConnectionPool` manually.
6. Set `max-size`, initial size, acquire timeout, idle timeout, and lifetime based on workload and infrastructure policies.
7. Ensure repositories, `DatabaseClient`, and the transaction manager share the pool-wrapped connection factory.
8. Run load and connection-failure tests while observing pending acquire, latency, connection creation, and timeouts.
9. Tune parameters using production metrics; never enlarge the pool merely to mask slow queries or long transactions.

## 18. Key Takeaways

- `r2dbc-pool` is an optional library for reusing and limiting R2DBC connections.
- The pool wraps a driver-provided connection factory; it does not replace the driver or Spring Data R2DBC.
- Pooling fits applications with many repeated database operations, costly physical connections, or a need to cap concurrent sessions.
- Small apps, short tasks, or environments with external connection management may not need a pool yet.
- Add the `io.r2dbc:r2dbc-pool` dependency and enable pool configuration according to your framework version.
- `max-size` must be calculated across all instances and services sharing the database.
- Acquire timeout, idle timeout, and maximum lifetime should align with SLAs and database/infrastructure policies.
- Spring's transaction manager and repositories must use the same pool-wrapped connection factory.
- Connections must be returned to the pool after use; long transactions and connection leaks exhaust the pool.
- A pool bounds connection resources; it does not replace backpressure, transactions, isolation, or concurrency data protection mechanisms.
