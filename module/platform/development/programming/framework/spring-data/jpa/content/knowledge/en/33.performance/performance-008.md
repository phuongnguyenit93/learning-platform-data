# Configuring Connection Pools Based on Load and Connection Hold Time

A connection pool manages a set of JDBC connections so the application can borrow and return connections instead of opening a new physical connection for every database operation. In Spring Boot, HikariCP is typically the connection pool used when present on the classpath. Pool configuration directly affects wait times to acquire a connection, concurrent sessions on the database, and application load resilience.

Good configuration balances three factors: concurrent workload, how long each transaction holds a connection, and how many connections the database can safely serve. Increasing pool size does not automatically make an application faster; an oversized pool can subject the database to extra contention, context switching, and memory pressure.

## 1. How Does a Connection Pool Work?

When code needs database access, JDBC borrows a connection from the pool. The connection is held while the operation or transaction requires it, then returned to the pool for another request to reuse.

General flow:

1. The application requests a connection.
2. If the pool has an idle connection, it lends that connection immediately.
3. If all connections are in use and the pool is below its limit, the pool may create a new connection.
4. If the pool has reached its limit, the request waits for a connection to be returned or times out.
5. When work completes, the connection is returned to the pool instead of closing the physical connection.

In HikariCP, `maximumPoolSize` is the maximum total connections the pool is allowed to maintain, including both idle and active connections. When the pool is exhausted, `getConnection()` waits up to `connectionTimeout`; if time expires with no available connection, the application receives a connection acquisition error.

An HTTP request does not necessarily hold a connection for its entire execution duration. A connection is typically acquired when the persistence context needs database access and held according to the connection management policy of the JPA provider, transaction manager, and driver. When capacity planning, measure how long connections are actually occupied, especially inside transactions.

## 2. Sizing the Pool Based on Load

Do not pick `maximumPoolSize` solely from web server thread count or CPU core count. Consider:

- Peak transaction rate.
- Average duration a transaction holds a connection.
- Fraction of transactions that actually touch the database.
- Query duration and lock wait time.
- Database concurrency capacity.
- Number of application instances connecting to the same database.
- Connections reserved for other services, background jobs, migrations, and admin tools.

You can use Little's Law as an initial estimate:

```text
Average concurrent connections
    ≈ Transaction rate (transactions/second)
      × Average connection hold time (seconds)
```

For example, if an application processes an average of 80 transactions per second and each transaction holds a connection for about 0.12 seconds:

```text
80 × 0.12 = 9.6 connections
```

Average demand is roughly 10 busy connections. This is not the final configuration value: peak hours, hold-time distribution, burst traffic, and acceptable wait margins can make real demand differ substantially. Use production metrics or load testing to size the pool and monitor queuing as load increases.

### Calculating Total Connections Across Multiple Instances

`maximumPoolSize` applies per pool in each instance. If an application runs multiple pods or VMs, total connections can far exceed the per-instance setting.

Suppose the database budgets at most 60 connections for this application after subtracting capacity for other clients. With 3 instances and each instance set to a max pool of 12:

```text
3 instances × 12 connections = 36 max connections
```

This leaves 24 connections within that budget for traffic spikes or related components. When using autoscaling, account for the maximum possible replica count, not just the typical replica count.

A database having a connection limit does not mean it operates efficiently when all connections are active. If the pool is too large, many queries compete for CPU, I/O, buffers, row locks, and internal resources. Throughput can drop and p95/p99 latency can climb. Increase pool size incrementally while comparing throughput, latency, lock waits, and database resource utilization.

## 3. Configuring HikariCP in Spring Boot

Spring Boot configures HikariCP using properties under the `spring.datasource.hikari` prefix. The YAML example below illustrates a configuration with a maximum pool of 12 connections:

```yaml
spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/shop
    username: app
    password: change-me
    hikari:
      maximum-pool-size: 12
      minimum-idle: 4
      connection-timeout: 3000
      validation-timeout: 1000
      idle-timeout: 300000
      max-lifetime: 1500000
      keepalive-time: 120000
      leak-detection-threshold: 20000
```

These numbers are examples illustrating millisecond units and relationships between parameters, not defaults suitable for every system. Adjust them based on your database, network infrastructure, replica count, and load test results.

Property meanings:

| Property | Effect |
|---|---|
| `maximum-pool-size` | Caps total connections in a pool |
| `minimum-idle` | Minimum idle connections the pool tries to maintain |
| `connection-timeout` | Maximum wait time to acquire a connection from the pool |
| `validation-timeout` | Maximum time to validate that a connection is still alive |
| `idle-timeout` | How long an idle connection above `minimum-idle` can sit before eviction |
| `max-lifetime` | Maximum lifetime of a connection in the pool |
| `keepalive-time` | Interval for testing/keeping alive idle connections |
| `leak-detection-threshold` | Threshold for logging when a connection is held too long |

With a single datasource, these properties can go in `application.yml` or `application.properties`. With multiple datasources, each `DataSource` bean must be wired to its own pool and corresponding property group; do not assume one property set applies uniformly to all datasources.

## 4. Understanding the Timeout and Lifecycle Parameters

Time-related parameters solve distinct problems. Distinguish connection wait time, connection lifetime, and idle time.

### connectionTimeout

This is the maximum time a thread waits for a connection when the pool has no idle connections and has reached `maximumPoolSize`. It is not a query timeout and does not cap SQL execution time.

Setting it too long causes requests to queue up, tying up application threads before eventually failing. Setting it too short causes transient errors during brief traffic spikes even when the database still has capacity to catch up. Choose it based on request deadlines and acceptable wait tolerances.

### maxLifetime

This is the maximum lifetime of a connection in the pool. HikariCP proactively retires connections reaching this age; a connection currently in use is not cut mid-flight simply for hitting the mark, but is retired once returned to the pool.

Set `maxLifetime` shorter than any connection lifetime limit enforced by the database, proxy, or network infrastructure by a reasonable buffer. If infrastructure closes connections after a certain age while the pool retains them longer, the application may borrow connections already closed by the other side.

### idleTimeout and minimumIdle

`idleTimeout` governs eviction of idle connections exceeding `minimumIdle` when the pool holds more than the minimum. It only shrinks the pool when `minimumIdle < maximumPoolSize`.

If `minimumIdle` is omitted, HikariCP defaults it to `maximumPoolSize`, creating a fixed-size pool. When you want the pool to scale with load, set `minimumIdle` below `maximumPoolSize` and configure an appropriate `idleTimeout`. Pool shrinking does not happen on the exact millisecond; HikariCP checks on an internal schedule.

### keepaliveTime

`keepaliveTime` checks and keeps idle connections alive to reduce the chance of firewalls, proxies, or databases dropping connections due to inactivity. HikariCP only runs keepalive on idle connections; it cannot rescue a connection stuck in a hanging query or severed mid-use.

This value must be smaller than `maxLifetime`. If infrastructure enforces an idle timeout, pick an interval shorter than that threshold with a safe buffer. Do not run keepalive too aggressively, since each check generates database and network activity.

### validationTimeout

This limits how long connection validity checks may take. It must be smaller than `connectionTimeout`. For JDBC drivers supporting JDBC4, HikariCP typically uses `Connection.isValid()`; avoid configuring a custom `connectionTestQuery` when the driver supports the standard check.

## 5. Distinguishing Pool Timeout from Query Timeout and Transaction Timeout

A common mistake is seeing slow requests and only increasing `connectionTimeout`. Pool timeout and query timeout are separate issues:

- **Connection acquisition timeout:** waiting to borrow a connection from the pool.
- **Query timeout:** limiting how long a single SQL statement may run.
- **Transaction timeout:** limiting how long a transaction may exist per the transaction manager.
- **Network/socket timeout:** limiting how long to wait for data over a network socket, depending on driver and configuration.

For example, the pool might hand out a connection immediately, yet a query runs for 40 seconds due to a missing index or lock wait. Raising `connectionTimeout` does not fix a slow query. Conversely, the database might be healthy while every connection is pinned by long transactions; in that case, a single-query timeout will not cure pool exhaustion either.

Design timeouts in alignment with your system's deadline hierarchy. Connection acquisition wait should be short enough for requests to fail cleanly before exceeding the overall deadline. Queries and transactions need dedicated timeouts matched to their workload type.

## 6. Keeping Transactions Short to Return Connections Early

How long a transaction holds a connection strongly dictates how many connections are required. A transaction does not consist only of SQL execution time; if a connection is held for the entire transaction, any Java work between queries can also keep the connection occupied.

Example of what to avoid:

```java
@Transactional
public void checkout(Long orderId) {
    PurchaseOrder order = repository.findById(orderId)
            .orElseThrow();

    paymentGateway.charge(order); // External network call
    shippingClient.createShipment(order); // External network call

    order.markPaid();
}
```

Two network calls can take seconds or time out, keeping the transaction and database connection pinned for a long time. When business logic allows, separate external service calls from database transactions, using state machines, sagas, or the outbox pattern to coordinate steps. Each transaction should wrap a clearly scoped data change and finish promptly.

Also pay attention to:

- Never wait for user input inside a transaction.
- Never sleep, perform long retries, or call external APIs while holding a connection.
- Avoid N+1 queries that prolong transactions.
- With streaming queries or cursors, close streams properly since resources may stay held until the stream closes.
- Never hold connections manually across multiple requests.

## 7. Monitoring the Pool with Metrics

You cannot pick the right pool size by guessing. Observe the pool under real traffic or load tests.

Key HikariCP metrics to monitor:

| Metric | Meaning |
|---|---|
| Active connections | Number of connections currently borrowed |
| Idle connections | Number of idle connections |
| Pending threads | Number of threads waiting for a connection |
| Maximum connections | Current pool cap |
| Connection acquisition time | Time spent waiting to obtain a connection |
| Connection usage time | Time a connection is held before returning |
| Connection timeout count | Number of failed acquisitions due to timeout |

With Spring Boot Actuator and Micrometer, datasource/pool metrics can be exported to your monitoring system depending on configuration. Exact metric names and tags vary by version and registry; inspect your application's actual metrics endpoint or dashboard.

Signals worth investigating:

- Active consistently equals maximum and pending climbs: the pool is frequently exhausted.
- Acquisition latency rises while database CPU is low: check if transactions hold connections too long, check for connection leaks, or verify pool sizing.
- Active is high and database CPU/lock waits are also high: the database may be the bottleneck; enlarging the pool can worsen contention.
- Idle is high and active is low: the pool may be larger than current demand, though check peak loads before shrinking.
- Usage time climbs: inspect slow queries, locks, long transactions, and external calls inside transactions.

Correlate pool metrics with database CPU, I/O, active sessions, lock waits, p95/p99 query latency, and throughput. Pool metrics alone do not pinpoint the root cause.

## 8. Detecting Connection Leaks

A connection leak occurs when the application borrows a connection and fails to return it promptly. The pool gradually drains and other threads block waiting.

When using Spring Data JPA and standard transaction managers, borrowing/returning connections is handled by the framework. However, leaks can still occur via manual JDBC code, unclosed streams, overly long transactions, or mismanaged resources.

For raw JDBC, use try-with-resources:

```java
try (Connection connection = dataSource.getConnection();
     PreparedStatement statement =
             connection.prepareStatement(
                     "select id from customer where id = ?")) {

    statement.setLong(1, customerId);

    try (ResultSet resultSet = statement.executeQuery()) {
        if (resultSet.next()) {
            long id = resultSet.getLong("id");
            // Process result
        }
    }
}
```

When using `DataSourceUtils` or Spring JDBC, follow Spring's resource management rules; do not manually close a connection managed by the current transaction. Do not manually close a Spring-injected `EntityManager`.

You can enable `leak-detection-threshold` in HikariCP to log warnings when a connection is held longer than the threshold. This is a diagnostic tool: it does not reclaim connections automatically, and legitimate long-running transactions will also trigger warnings. Use the stack trace in the log to find where the connection was borrowed, then inspect transaction boundaries and resource cleanup paths.

## 9. A Controlled Tuning Process

A practical tuning workflow can follow these steps:

1. **Measure baseline load:** collect transactions/second, replica count, connection hold time, query latency, and database connection limits.
2. **Estimate demand:** multiply throughput by connection hold time to estimate average busy connections; add headroom for bursts and variance.
3. **Set a system-wide budget:** multiply per-instance pool size by max replicas; subtract connections reserved for other apps and tasks.
4. **Choose timeouts:** set connection acquisition timeout according to request deadlines; set max lifetime and keepalive based on database, proxy, and network limits.
5. **Run load tests:** ramp load step-by-step while tracking pending, active, acquisition latency, throughput, query latency, and database resources.
6. **Tune one group at a time:** adjust a small set of parameters per iteration to isolate effects; avoid changing pool size alongside multiple other changes.
7. **Test failure modes:** simulate database restarts, network blips, traffic spikes, and long transactions to see how the application recovers.

There is no universal pool size for every application. The right value is one that meets throughput and latency targets within database resource limits, even when running at maximum expected replica count.

## 10. Takeaways

Connection pools reuse JDBC connections and cap concurrent connections from the application to the database. Configure `maximumPoolSize` based on throughput, connection hold time, and the total connection budget across all instances. Distinguish `connectionTimeout`, `maxLifetime`, `idleTimeout`, and `keepaliveTime` from query/transaction timeouts; keep transactions short, track active/idle/pending counts and usage time, and investigate leaks before enlarging the pool.