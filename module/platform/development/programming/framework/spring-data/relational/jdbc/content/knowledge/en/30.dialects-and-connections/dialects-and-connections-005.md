# Pool Configuration: Size, Timeouts, and Connection Lifecycle

In **Spring Data Relational JDBC**, repositories and JdbcTemplate access the database through a DataSource. In real-world applications, the DataSource is typically wrapped by a **connection pool**: the pool creates and keeps a set of JDBC connections ready, hands out a connection to operations needing the database, and reclaims it when the operation finishes.

A connection pool avoids creating a new physical connection for every SQL statement, controls concurrent connection counts, and detects connection exhaustion. However, the pool must be tuned to database capacity and actual workload. A pool that is too small makes requests wait; a pool that is too large can overload the database, increase lock contention, and reduce throughput.

This lesson uses **HikariCP** as the example because Spring Boot typically selects HikariCP when it is present on the classpath. Properties under spring.datasource.hikari.* apply only to HikariCP; other pools have their own property names and semantics.

## 1. Where does the connection pool sit in Spring Data JDBC?

A Spring Data JDBC repository does not hold a JDBC connection throughout the bean's lifecycle. The repository uses the DataSource infrastructure to acquire a connection when performing database operations. The pool manages physical connections and reuses them.

```text
Application service
       │
       ▼
Spring Data JDBC repository / JdbcTemplate
       │
       ▼
DataSource (HikariCP pool)
       │
       ├── Connection A ───┐
       ├── Connection B ───┼── Database
       ├── Connection C ───┤
       └── ...             ┘
```

When an operation needs a connection, the pool lends an idle connection. When the JDBC connection is closed per contract, HikariCP typically returns the connection to the pool rather than immediately closing the physical connection.

Key benefits:

- Reduces the cost of repeatedly creating TCP/database sessions.
- Bounds the number of connections an application instance opens to the database.
- Allows configuring wait timeouts for acquiring a connection.
- Reuses connections after a transaction or JDBC operation completes.
- Exposes metrics to observe active, idle, and pending connection requests.

A pool does not automatically make SQL queries run faster. Slow queries, lock contention, long transactions, or an under-resourced database will still cause slowdowns even with a well-configured pool.

## 2. Spring Boot selecting and configuring HikariCP

When using Spring Boot with the JDBC starter and HikariCP on the classpath, auto-configuration typically creates a DataSource backed by HikariCP. Spring Data JDBC uses this DataSource through the JDBC infrastructure.

Example configuration:

```yaml
spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/shop
    username: shop_app
    password: configure-through-secret-store
    hikari:
      pool-name: ShopJdbcPool
      maximum-pool-size: 12
      minimum-idle: 3
      connection-timeout: 2000
      validation-timeout: 1000
      idle-timeout: 600000
      max-lifetime: 1740000
      keepalive-time: 120000
      leak-detection-threshold: 0
```

These values are illustrative settings, not an optimal parameter set for every application. For example, maximum-pool-size 12 is merely a starting point to validate under real load; it does not mean the database should always receive 12 connections from every instance.

Commonly tuned Hikari properties:

| Property | Effect |
| --- | --- |
| pool-name | Pool name in logs/metrics |
| maximum-pool-size | Maximum number of connections, including both active and idle connections |
| minimum-idle | Minimum number of idle connections the pool tries to maintain |
| connection-timeout | Maximum time to wait for a connection from the pool |
| validation-timeout | Maximum time to wait when validating a connection |
| idle-timeout | How long an idle connection may remain before removal when the pool exceeds minimum idle |
| max-lifetime | Maximum lifetime of a connection in the pool |
| keepalive-time | Interval to test/keep alive idle connections |
| leak-detection-threshold | Threshold for warning when a connection is borrowed for too long |

If not using HikariCP, check the actual pool selected by Spring Boot and that pool's configuration documentation. Do not copy Hikari properties verbatim to Tomcat JDBC Pool, Apache DBCP2, or a custom pool.

## 3. Choosing maximumPoolSize

maximumPoolSize limits the total number of connections a HikariCP pool can allocate concurrently. It includes connections currently borrowed by the application and idle connections sitting in the pool.

When all connections are borrowed, the next request must wait for one to be returned. If the wait exceeds connectionTimeout, HikariCP throws a connection acquisition error.

### 3.1. Do not size the pool solely by thread count

An application with 200 HTTP worker threads does not need 200 database connections. Most requests may be doing CPU work, calling other services, or not accessing the database simultaneously. Conversely, even a few long-running transactions can hold connections and exhaust the pool.

The right connection count depends on:

- Database concurrency capacity.
- Database CPU count and I/O resources.
- How long an operation holds a connection.
- Concurrent queries/transactions running at peak.
- Number of application instances and other services sharing the database.
- Read/write workload, lock contention, and query complexity.

Increasing pool size can increase the number of queries competing for CPU, I/O, and locks. If the database is already saturated, adding connections usually does not improve throughput.

### 3.2. Calculate total connections across the entire system

Do not look only at maximum-pool-size on a single instance. For example, with 4 application instances each configured with a max pool of 12:

```text
4 application instances × 12 connections = 48 connections
```

The database may also receive connections from workers/background jobs, migration tools, admin consoles, monitoring tools, other services, and separate pools for other datasources.

Maximum total connections must stay within the database's allowed limit while reserving headroom for administration, failover, and operational tasks. With multiple datasources, calculate each pool separately and sum totals per target database. During rolling deployments or autoscaling, account for overlapping instances during the transition window.

### 3.3. How to find the right size

A practical process:

1. Determine the database connection limit and required reserve capacity.
2. Calculate the maximum concurrent instance count, including autoscaling and rolling deployments.
3. Choose a conservative initial pool size.
4. Run production-representative load, including peak hours and heavy queries.
5. Observe active/idle/pending connections, connection wait time, query latency, and database CPU/I/O.
6. Adjust pool size and rerun the same workload to compare.

If active connections stay consistently below the limit with no pending requests, increasing the pool likely adds no benefit. If the pool frequently hits its ceiling, investigate why connections are held for long before merely raising the number.

## 4. minimumIdle and fixed-size pools

minimumIdle is the minimum number of idle connections HikariCP attempts to maintain. If minimumIdle is smaller than maximumPoolSize, the pool can grow under load and retire idle connections above the minimum after idleTimeout.

By default, HikariCP sets minimumIdle equal to maximumPoolSize if not configured separately, behaving closely to a fixed-size pool. HikariCP documentation generally recommends keeping this default for many workloads for predictable responsiveness; dynamic sizing can still be useful when maintaining idle connections carries significant cost.

Example:

```yaml
spring:
  datasource:
    hikari:
      maximum-pool-size: 12
      minimum-idle: 3
      idle-timeout: 600000
```

The pool can keep at least 3 idle connections and grow under load. Setting minimum-idle to 12 keeps all 12 connections idle when none are borrowed.

Do not set minimum-idle higher than needed solely to avoid creating connections under load. Every idle connection is still a database session consuming resources.

## 5. Distinguishing timeout types

The word timeout can refer to several distinct stages. Proper configuration depends on which stage you intend to bound:

| Timeout | What does it limit? | Where is it usually configured? |
| --- | --- | --- |
| Pool acquisition timeout | Waiting to borrow a connection from the pool | Hikari connection-timeout |
| Connection validation timeout | Waiting to validate a connection | Hikari validation-timeout |
| Driver connect timeout | Opening a physical connection to the database | JDBC driver URL/properties |
| Query/statement timeout | SQL statement execution time | JDBC statement, Spring JDBC, or database |
| Socket/read timeout | Waiting for socket data after sending a query | JDBC driver/network/database |
| Transaction timeout | Time allowed for a transaction to complete | Transaction manager/framework |

HikariCP's connection-timeout is **not a query timeout**. If an SQL statement runs for 60 seconds, setting connection-timeout to 2 seconds does not cancel the SQL after 2 seconds. It only caps how long a caller waits to obtain a connection from the pool.

## 6. connectionTimeout: time spent waiting to borrow a connection

Example:

```yaml
spring:
  datasource:
    hikari:
      connection-timeout: 2000
```

The value is in milliseconds. If no idle connection is available and the pool has reached maximumPoolSize, the caller waits up to this duration. When expired, HikariCP reports a connection acquisition timeout error.

Choose the timeout based on the application's target latency:

- Too short: requests may fail during brief traffic spikes.
- Too long: application threads stay blocked waiting for connections, growing queues and risking cascading failures.
- Must coordinate with HTTP request timeouts, transaction timeouts, and retry policies.

Do not retry indefinitely when the pool runs out of connections. Aggressive retries can amplify waiting requests and make recovery harder for both the pool and the database.

## 7. validationTimeout and driver connect timeout

validation-timeout limits how long HikariCP waits when testing whether a connection is still valid. This value must be smaller than connection-timeout.

Example:

```yaml
spring:
  datasource:
    hikari:
      connection-timeout: 2000
      validation-timeout: 1000
```

Driver connect timeout applies when establishing a new physical connection, not when borrowing an existing pooled connection. Configuration depends on the JDBC driver. For PostgreSQL JDBC, the URL can include connectTimeout:

```yaml
spring:
  datasource:
    url: jdbc:postgresql://db-host:5432/shop?connectTimeout=5
```

Values and units must match your driver's documentation. Do not apply PostgreSQL URL properties to MySQL, SQL Server, or Oracle.

If the database starts slowly or the network is unstable, driver connect timeouts and application startup/fail-fast behavior must be designed separately. connection-timeout does not replace them.

## 8. idleTimeout: retiring idle connections

idle-timeout specifies how long an idle connection may sit before the pool considers retiring it. HikariCP only shrinks the pool below maximumPoolSize when idle connections exceed minimumIdle.

Example:

```yaml
spring:
  datasource:
    hikari:
      maximum-pool-size: 12
      minimum-idle: 3
      idle-timeout: 600000
```

When load drops, the pool can close idle connections above 3 after the idle period. It never closes connections actively used by a transaction.

If minimumIdle equals maximumPoolSize, idle-timeout will not shrink the pool below that fixed size. Therefore, do not expect changing idle-timeout alone to reduce all idle connections.

## 9. maxLifetime: maximum connection lifecycle

max-lifetime sets the maximum lifetime the pool allows a connection to live. HikariCP does not forcibly close a connection currently in use; an expired connection is marked for retirement once returned.

Set maxLifetime lower than any connection lifetime limit enforced by the database, proxy, firewall, or network infrastructure. For example, if infrastructure drops connections after 30 minutes, the pool can be set around 29 minutes to proactively retire them before that cutoff:

```yaml
spring:
  datasource:
    hikari:
      max-lifetime: 1740000
```

This is only an example assuming infrastructure actually has a 30-minute limit. Determine the actual timeout of your database/proxy/network. If maxLifetime exceeds external limits, the application may borrow a connection already closed by infrastructure and fail mid-operation.

Do not set maxLifetime unnecessarily short; the pool will churn connections frequently, increasing handshake overhead and load on the database.

## 10. keepaliveTime: keeping idle connections from being dropped by infrastructure

keepalive-time allows HikariCP to periodically probe idle connections to prevent network devices or database services from closing them due to idleness. Keepalive applies only to idle connections, never to connections currently borrowed by the application.

For example, if infrastructure drops idle connections after 5 minutes, you can configure keepalive shorter than that window:

```yaml
spring:
  datasource:
    hikari:
      keepalive-time: 120000
      max-lifetime: 1740000
```

keepalive-time must be smaller than max-lifetime. Do not enable keepalive just because it exists; first verify whether the database or proxy enforces an idle timeout. Keepalive generates extra health-check activity, so factor that in when running many pools and connections.

## 11. leakDetectionThreshold: detecting long-held connections

leak-detection-threshold causes HikariCP to log a warning if a connection stays borrowed longer than the configured threshold without being returned.

Example enabled temporarily in a test environment:

```yaml
spring:
  datasource:
    hikari:
      leak-detection-threshold: 30000
```

If a connection is held past 30 seconds, HikariCP can log the stack trace from where the connection was borrowed. This is a **warning**, not an automatic connection reclamation mechanism. The connection may still be returned afterward; a warning log alone does not prove an actual leak.

Common causes:

- Acquiring a connection directly and forgetting to close it.
- Not closing ResultSet or Statement when managing JDBC manually.
- Keeping transactions open too long.
- Making HTTP/external service calls while holding a transaction.
- Waiting on locks or slow SQL queries.
- Error paths bypassing finally/try-with-resources.

JdbcTemplate and Spring Data repositories manage standard JDBC resource lifecycles. If using JDBC directly, use try-with-resources or appropriate transaction-aware APIs. Never store a connection in a singleton service field.

## 12. Connection lifecycle within a transaction

In Spring JDBC, the transaction manager can bind a connection to the current transaction. Repository/JDBC operations within the same transaction typically reuse that managed connection. When the transaction finishes, the connection is returned to the pool.

```text
@Transactional service method
          │
          ▼
Transaction manager starts transaction
          │
          ▼
Borrow connection from DataSource pool
          │
          ▼
Repository call A ───┐
                     ├── uses the transaction's connection
Repository call B ───┘
          │
          ▼
Commit or rollback
          │
          ▼
Return connection to pool
```

Example:

```java
@Service
public class OrderService {

    private final PurchaseOrderRepository orders;
    private final CustomerRepository customers;

    public OrderService(
            PurchaseOrderRepository orders,
            CustomerRepository customers) {
        this.orders = orders;
        this.customers = customers;
    }

    @Transactional
    public void confirmOrder(Long orderId, Long customerId) {
        PurchaseOrder order = orders.findById(orderId)
                .orElseThrow();
        Customer customer = customers.findById(customerId)
                .orElseThrow();

        order.confirmFor(customer);
        orders.save(order);
    }
}
```

Repository calls within the same transaction can share the connection bound to that transaction. The connection is not held for the lifetime of OrderService; it is borrowed and returned per transaction/operation.

For operations outside an explicit transaction, Spring Data/JDBC still borrows a connection to execute the statement and returns it afterward. Transaction boundaries should sit at the service/use-case level so multiple atomic operations share a single transaction.

### 12.1. Do not hold transactions longer than necessary

Anti-pattern example:

```java
@Transactional
public OrderResult process(Long id) {
    PurchaseOrder order = repository.findById(id).orElseThrow();

    // Call external service while transaction/connection is open.
    paymentClient.authorize(order);

    order.confirm();
    repository.save(order);
    return OrderResult.from(order);
}
```

If paymentClient takes 10 seconds, the connection can remain held for the entire wait even though the database is idle. Many concurrent requests like this can exhaust the pool.

Design shorter transactions covering only the database work that must be atomic. When coordinating with external systems, consider multi-step workflows, outbox, or sagas based on business requirements rather than holding a connection across network calls.

### 12.2. Acquiring a connection manually

If direct JDBC usage is needed:

```java
try (Connection connection = dataSource.getConnection();
     PreparedStatement statement =
             connection.prepareStatement("SELECT 1")) {
    try (ResultSet resultSet = statement.executeQuery()) {
        if (resultSet.next()) {
            // Process the result.
        }
    }
}
```

For connections borrowed directly from the pool outside a transaction, close() returns the connection to the pool. Inside a Spring-managed transaction, use JdbcTemplate, DataSourceUtils, or an appropriate TransactionAwareDataSourceProxy to participate properly in the transaction. Never manually close a physical connection managed by the Spring transaction manager.

## 13. Environment-specific configuration

Pool sizes and timeouts typically differ across local, test, staging, and production environments. Profiles can be used:

```yaml
spring:
  config:
    activate:
      on-profile: local
  datasource:
    hikari:
      maximum-pool-size: 4
      minimum-idle: 1
      connection-timeout: 3000
```

Production can be configured via deployment platform environment variables or a secret store. Never commit real usernames/passwords into the repository.

When using multiple datasources, each datasource can have its own pool. Give each pool a distinct name and calculate total connections per target database. Do not duplicate pools for the same database without a clear architectural reason.

## 14. Monitoring pools with metrics

HikariCP exposes metrics showing how the pool is performing. When integrated with Micrometer/Actuator, metrics typically use the prefix hikaricp.connections:

| Metric | Meaning |
| --- | --- |
| hikaricp.connections.active | Number of connections currently borrowed |
| hikaricp.connections.idle | Number of idle connections in the pool |
| hikaricp.connections.pending | Number of callers waiting for a connection |
| hikaricp.connections.max | Maximum connection limit |
| hikaricp.connections.min | Minimum idle target |
| hikaricp.connections.acquire | Connection acquisition time |
| hikaricp.connections.usage | Connection usage duration |

Exact metric names may differ by Micrometer, HikariCP, and registry versions. Use the Actuator endpoint or configured metrics system to verify actual metric names.

Key indicators:

- active consistently equals max and pending increases: the pool is saturated.
- pending increases while database CPU is low: transactions may be holding connections too long, waiting on locks, or connections may be leaking.
- active is high alongside high query latency and high database CPU/I/O: the database may be the bottleneck; enlarging the pool may worsen contention.
- idle is continuously high: the pool may be oversized for demand, though peak load and scaling capacity must be considered.
- acquire increases: requests are spending time waiting to obtain a connection.

Do not treat a single snapshot as conclusive. Observe trends across peak traffic, deployments, autoscaling, and batch jobs.

## 15. Diagnosing pool exhaustion

When logs show errors like "Connection is not available, request timed out", inspect in order:

1. Which pool threw the error and what is its current maximumPoolSize?
2. What were active, idle, and pending at the time of the error?
3. Which queries are slow or waiting on locks?
4. Which transactions are holding connections for a long time?
5. Are there direct JDBC paths failing to close resources?
6. Are HTTP calls, file I/O, or heavy CPU work happening inside transactions?
7. Does the sum of pool sizes across all replicas exceed the database budget?
8. Is the database hitting connection, CPU, I/O, or memory limits?

If connections are held long due to slow queries, optimize queries/indexes or resolve locking before increasing pool size. If the workload genuinely needs more connections and the database has headroom, raise the pool gradually and re-measure.

Do not set an arbitrarily huge maximum-pool-size just to eliminate timeouts. That shifts the queue from the application to the database, slowing down all queries and spreading failures.

## 16. Pool lifecycle at application startup and shutdown

In a Spring Boot application, the DataSource is a container-managed bean. When the application context starts, the pool initializes according to configuration; depending on initialization settings, the app may open connections eagerly or on demand.

During graceful shutdown, Spring closes the DataSource bean and HikariCP drains the pool, releasing physical connections. Never create a new pool per request and never manually call close() on a shared DataSource bean inside a service.

During rolling deployments:

- Old instances need time to finish in-flight requests/transactions.
- Readiness/liveness probes and graceful shutdown must coordinate with request draining times.
- New instances may open pools before old instances shut down; include that overlap period in the database connection budget.
- Do not let shutdown cut off critical transactions if the platform allows configuring an appropriate termination grace period.

If the database restarts or the network drops briefly, the pool can discard broken connections and recreate them according to driver/pool capabilities. The application still needs bounded retries at the appropriate layer and transaction error handling; a pool cannot turn an already failed transaction into a success.

## 17. Combined configuration example

An illustrative configuration for a Spring Data JDBC application using PostgreSQL:

```yaml
spring:
  datasource:
    url: jdbc:postgresql://db-host:5432/shop
    username: shop_app
    password: set-through-secret-store
    hikari:
      pool-name: ShopJdbcPool
      maximum-pool-size: 12
      minimum-idle: 3
      connection-timeout: 2000
      validation-timeout: 1000
      idle-timeout: 600000
      max-lifetime: 1740000
      keepalive-time: 120000
      leak-detection-threshold: 0
```

Meaning of this example:

- At most 12 connections per application instance.
- Attempts to maintain at least 3 idle connections.
- Waits at most 2 seconds to borrow a connection.
- Connection validation timeout is 1 second, smaller than acquisition timeout.
- Idle connections above the minimum can be retired.
- Connection lifetime is 29 minutes, assuming infrastructure imposes a 30-minute limit.
- Keepalive probes idle connections every 2 minutes, if needed by driver/pool and infrastructure.
- Leak detection is disabled in normal operation; enable temporarily when investigating long-held connections.

Before adopting these numbers, verify database/proxy limits, maximum replica count, workload, and metrics. Configuration values are starting points for load testing, not formulas replacing measurement.

## 18. Common pitfalls

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Connection acquisition timeout | Pool exhausted or connections held too long | Inspect active/pending, transaction duration, queries, and leaks |
| Increasing pool size does not improve throughput | Database already saturated or lock contention | Measure database CPU/I/O, query latency, and lock waits |
| Pool has many idle connections | minimumIdle too high or pool oversized | Evaluate baseline minimum and peak load before shrinking |
| Connection closed while in use | maxLifetime exceeds infrastructure limit or network drops connection | Set lifetime lower than external limit and inspect driver |
| Idle connections closed by firewall/proxy | No keepalive or incompatible idle timeout | Identify infrastructure timeout and configure appropriate keepalive |
| Short connection-timeout yet SQL runs long | Confusing acquisition timeout with query timeout | Configure statement/database/driver timeouts separately |
| Leak detection warns without an actual leak | Valid transaction or query runs longer than threshold | Inspect stack trace and usage time; adjust threshold |
| Database hits connection limit during deploy | Sum of pools across replicas and overlapping instances too high | Calculate system-wide connection budget |
| Tests pass but production fails on connections | Pool/test DB differs from production or test load too light | Use target database and representative load |
| Connections not returned | Manually managed JDBC resources left unclosed | Use try-with-resources or Spring JDBC abstractions |

## 19. Pool configuration checklist

Before promoting pool configuration to production, verify:

1. Is the actual pool HikariCP or another implementation?
2. Does the sum of maximum connections across all replicas/datasources fit inside the database budget?
3. Was maximumPoolSize chosen from measured load rather than thread count?
4. Does minimumIdle match baseline load and idle connection cost?
5. Does connectionTimeout align with request/transaction deadlines?
6. Is validationTimeout smaller than connectionTimeout?
7. Is maxLifetime lower than database/proxy/network connection limits?
8. Is keepaliveTime enabled only when needed and smaller than maxLifetime?
9. Are driver connect timeouts and query timeouts configured separately if required?
10. Are transactions short, without holding connections while awaiting external services?
11. Are active/idle/pending/acquire/usage metrics and appropriate alerts in place?
12. Is there a graceful shutdown plan accounting for connection overlap during deploys?

## 20. Hands-on exercises

**Exercise 1 — Observe the pool.** Run a Spring Data JDBC application with HikariCP. Record pool name, maximum size, minimum idle, and active/idle counts while idle.

**Exercise 2 — Pool exhaustion.** Create a test endpoint that holds a transaction open in a controlled manner. Send concurrent requests and observe active, pending, and acquisition timeout errors. Stop the test as soon as the metrics are captured.

**Exercise 3 — Compare pool sizes.** Run the same workload across different maximum pool size levels. Record throughput, p95/p99 latency, database CPU, and lock waits; do not compare successful request counts alone.

**Exercise 4 — Different timeouts.** Trigger a connection wait and a slow query. Observe that connection-timeout only affects borrowing a connection, then test query/statement timeout separately.

**Exercise 5 — maxLifetime and keepalive.** Check database or proxy idle/lifetime settings. Set max lifetime below the limit and keepalive below idle timeout when needed; observe connections being recycled.

**Exercise 6 — Leak detection.** Enable leak-detection-threshold in a test environment, intentionally hold a connection long, then return it. Read the stack trace and distinguish long-usage warnings from genuine leaks.

**Exercise 7 — Transaction boundaries.** Compare a service holding a transaction across an HTTP call against a version moving the HTTP call outside the transaction. Observe connection usage and pending requests.

**Exercise 8 — Graceful shutdown.** Run a transaction with a known duration, send a shutdown signal to the application, and observe request draining, DataSource closing, and pool release.

### References

- [Spring Boot — SQL Databases / DataSource Configuration](https://docs.spring.io/spring-boot/reference/data/sql.html): DataSource and connection pool auto-configuration.
- [HikariCP — Configuration](https://github.com/brettwooldridge/HikariCP#configuration-knobs-baby): meaning of pool, timeout, lifetime, keepalive, and leak detection properties.
- [Spring Framework — Data Access and JDBC](https://docs.spring.io/spring-framework/reference/data-access/jdbc.html): JdbcTemplate, JDBC resource management, and transaction integration.
- [Spring Framework — DataSourceTransactionManager](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/datasource/DataSourceTransactionManager.html): managing connections bound to JDBC transactions.
