# HikariCP, Pool Sizing, and Server-Side max_connections Limits

Spring Boot typically uses HikariCP to manage JDBC connections to MySQL. A pool enables the application to reuse connections, avoiding creating and authenticating a new connection for every statement. However, a pool does not add processing capacity to MySQL. If each application instance opens too many connections, the total number of connections across all instances can exceed max_connections, causing MySQL to reject new connections or waste resources on idle sessions.

Pool sizing requires considering application workload, the number of running instances, the number of datasources, other services sharing MySQL, and the connection budget reserved for administration. The goal is to maintain enough connections for useful concurrent queries while preventing database overload from excessive sessions.

## 1. How Does a Connection Pool Work?

When a component needs database access, HikariCP provides an available connection from the pool. After finishing its work, the application closes the connection with Connection.close(). For a pooled connection, this operation normally returns the connection to the pool for reuse rather than immediately closing the physical socket.

~~~mermaid
flowchart TD
    A["Spring service / repository"] --> B["DataSource.getConnection()"]
    B --> C{"Is an idle connection available?"}
    C -->|Yes| D["Grant connection to request"]
    C -->|No, pool has room| E["Create physical connection"]
    C -->|Reached maximumPoolSize| F["Wait up to connectionTimeout"]
    E --> D
    D --> G["Execute SQL / transaction"]
    G --> H["Connection.close()"]
    H --> I["Return connection to pool"]
    F -->|Connection returned| D
    F -->|Timed out| J["SQLException: timeout acquiring connection"]
~~~

The pool tracks connections currently borrowed by the application and connections waiting in reserve. A connection running a query or inside a transaction is typically considered active. An unborrowed connection can remain idle and ready for the next request.

Key concepts to distinguish:

- **Active connection:** a connection currently held by the application to perform work.
- **Idle connection:** a connection sitting in the pool and not currently borrowed by the application.
- **Pending thread:** a thread waiting to acquire a connection because the pool cannot supply one yet.
- **Physical connection:** an actual network/session connection to MySQL.
- **Pool capacity:** the maximum number of connections a single pool can maintain as configured.

maximumPoolSize limits the total number of active plus idle connections in one HikariCP pool. It is a per-pool limit within each application process, not a system-wide total limit.

## 2. HikariCP in Spring Boot

Spring Boot usually auto-configures HikariCP when a JDBC starter and HikariCP are on the classpath. Basic settings reside under spring.datasource.hikari.

~~~yaml
spring:
  datasource:
    url: jdbc:mysql://mysql.internal.example:3306/shop
    username: shop_app
    password: DB_PASSWORD_FROM_SECRET_MANAGER
    hikari:
      pool-name: shop-main-pool
      maximum-pool-size: 12
      minimum-idle: 4
      connection-timeout: 30000
      validation-timeout: 5000
      idle-timeout: 600000
      max-lifetime: 1500000
~~~

The values above are illustrative examples only. Replace them with values measured under real workloads and verify the bounds of the HikariCP version in use. Secrets should be supplied through a secret manager or your environment's secure configuration mechanism.

If no other pool implementation is specified, Spring Boot usually chooses HikariCP when the dependency is present. Inspect the dependency tree to confirm the actual packaged HikariCP version rather than relying solely on configuration files.

In an application with multiple datasources, each datasource can have its own pool. For instance, a read datasource and a write datasource have two separate maximumPoolSize values; potential total connections must sum both.

## 3. Key HikariCP Settings

| Property | Meaning | How to Choose |
|---|---|---|
| maximumPoolSize | Maximum connections in one pool, including active and idle | Size according to server budget and measured load |
| minimumIdle | Minimum idle connections the pool tries to maintain | Set lower than maximumPoolSize to allow the pool to shrink; if unset, HikariCP defaults to maximumPoolSize |
| connectionTimeout | Maximum wait time to borrow a connection from the pool | Choose according to application latency/SLO; too long causes requests to hang |
| validationTimeout | Maximum time for connection validation | Must be smaller than connectionTimeout |
| idleTimeout | Idle duration before excess connections may be evicted | Only triggers shrinking when minimumIdle is less than maximumPoolSize |
| maxLifetime | Maximum lifetime of a physical connection in the pool | Set lower than the connection lifetime limit of DB/proxy/network |
| keepaliveTime | Periodically checks/keeps idle connections from being dropped by infrastructure | Enable only when needed; must be smaller than maxLifetime |
| leakDetectionThreshold | Warns when a connection is held longer than the threshold | Use to aid investigation; warnings alone do not prove a leak |
| initializationFailTimeout | How the pool behaves if it cannot connect at initialization | Choose according to startup policy and service fault tolerance |

### 3.1. maximumPoolSize and minimumIdle

maximumPoolSize is the pool's ceiling. When all connections are in use and the pool has reached this ceiling, subsequent requests must wait. If no connection is returned before connectionTimeout, HikariCP throws a timeout exception.

minimumIdle controls the number of idle connections the pool tries to maintain. If unconfigured, HikariCP generally uses maximumPoolSize as minimumIdle, creating a fixed-size pool. Setting minimumIdle lower than maximum can let the pool reduce connections during low load, though opening additional connections when load rises may take extra time.

Do not increase maximumPoolSize merely because you see pending threads. Pending threads can signal slow queries, transactions holding connections too long, an overloaded database, or an application failing to return connections properly. Find the root cause before growing the pool.

### 3.2. Timeouts and Connection Lifetime

connectionTimeout is the wait time to acquire a connection, not the maximum execution time for a SQL statement. Query timeouts must be managed separately at the JDBC statement, transaction, framework, or server level.

maxLifetime should be shorter than the connection lifetime limits of MySQL, proxies, load balancers, or firewalls. Upon reaching its lifetime, HikariCP retires the connection when it is not in use; a borrowed connection is not closed mid-operation just because it hits maxLifetime.

keepaliveTime only affects idle connections. Do not set keepalive greater than or equal to maxLifetime. If the infrastructure does not have an idle timeout causing issues, enabling keepalive is not strictly necessary.

leakDetectionThreshold helps pinpoint code paths that may be holding connections too long. A valid but long-running transaction can also trigger a warning. Use stack traces and execution durations to investigate; do not lower the threshold so far that it creates constant alert noise.

## 4. MySQL max_connections Is a Server-Wide Limit

max_connections is the maximum number of concurrent client connections allowed by the MySQL server. This limit applies to the entire instance, not a single application or pool. Once reached, new connections may be rejected with an error such as Too many connections.

Inspect the limit and current usage:

~~~sql
SHOW VARIABLES LIKE 'max_connections';

SHOW GLOBAL STATUS
WHERE Variable_name IN (
  'Threads_connected',
  'Threads_running',
  'Max_used_connections',
  'Connection_errors_max_connections'
);
~~~

Meaning:

- max_connections: the server's configured limit.
- Threads_connected: the number of currently open client connections.
- Threads_running: the number of threads actively executing work, not total connections.
- Max_used_connections: the peak number of simultaneous connections since server startup or status reset.
- Connection_errors_max_connections: the number of connection attempts refused due to hitting the max connections limit.

A high Threads_connected value does not mean every connection is running a query. Pools may hold many idle connections. Conversely, a sustained high Threads_running value indicates the database is under heavy execution load.

You can inspect connection details with:

~~~sql
SHOW FULL PROCESSLIST;
~~~

Or query Performance Schema/sys schema if enabled and permitted. During investigation, categorize connections by user, host, database, state, and execution time. Do not share process list output if it contains sensitive information.

## 5. Budgeting Connections Across the Entire System

You cannot set maximumPoolSize equal to max_connections because MySQL serves many other processes as well. You must sum potential connections from all pools and reserve headroom for operations.

One budgeting approach:

\[
C_{app} = \sum_{i=1}^{n} R_i \times P_i
\]

Where:

- R_i is the number of replicas/instances running application process type i.
- P_i is the maximumPoolSize of a pool belonging to that process.

Then:

\[
C_{planned} = C_{app} + C_{jobs} + C_{ops} + C_{other} + C_{reserve}
\]

C_jobs represents connections from workers/batches, C_ops represents administrative tools, C_other covers monitoring, migrations, or other services, and C_reserve is headroom for deployments, failover, and incident investigation.

Example system:

| Source | Process Count | Max Pool per Process | Max Connections |
|---|---:|---:|---:|
| API service | 4 | 12 | 48 |
| Worker service | 3 | 5 | 15 |
| Reporting service | 2 | 4 | 8 |
| Total from application pools | | | 71 |
| Batch and operational tools | | | 12 |
| Monitoring, migrations, and other services | | | 7 |
| Deploy/failover reserve | | | 20 |
| Total planned budget | | | 110 |

If MySQL has max_connections = 150, an example budget of 110 leaves headroom for traffic spikes and unlisted processes. This is only an arithmetic illustration; reserve margins must reflect your actual deployment model and SLOs.

When an application has two datasources, sum the maximums of both. During rolling deployments, old and new replicas can coexist temporarily; account for connections from both groups. During failover to another MySQL instance, each server has its own budget, though applications may temporarily hold old connections while creating new ones during the transition.

## 6. Sizing the Pool by Workload

Pool size should not simply equal HTTP threads, CPU cores, or online users. A request might not touch the DB, might run multiple sequential queries on one connection, or might hold a connection while calling an external service. Measure how long connections are actually held and what level of concurrency benefits MySQL.

### 6.1. Start with Real Load

Collect:

- Request throughput and transactions per second.
- Percentage of requests accessing MySQL.
- Average and p95/p99 connection hold time.
- Concurrent running queries and execution duration.
- MySQL CPU, I/O, lock waits, buffer pool metrics, and Threads_running.
- HikariCP active, idle, pending, timeouts, and acquisition latency.

Little's Law can help estimate average concurrent work:

\[
L = \lambda \times W
\]

Where L is the average number of items in progress, lambda is the arrival rate (requests or transactions per second), and W is the average time each item holds the resource (seconds). For example, 80 DB transactions per second, each holding a connection for an average of 0.05 seconds, corresponds to roughly 4 active connections on average. This is a starting point for load testing, not the final optimal pool size.

### 6.2. Increment Gradually and Observe Saturation

Test small pool sizes and increase gradually in a production-like environment. At each step, measure throughput, latency, CPU, I/O, lock waits, active connections, and pending threads.

When growing the pool stops increasing throughput while latency, CPU, or lock waits climb, the database may have reached saturation. Adding even more connections can degrade performance due to context switching, lock contention, and per-session memory overhead.

A practical rule is to start with a modest pool, then benchmark to find the point where the database achieves strong throughput with stable latency. Size API, worker, and reporting pools independently if their workloads differ.

### 6.3. Pool-Locking and Nested Connections

The HikariCP documentation provides a reference formula to avoid deadlocks when multiple threads can simultaneously hold multiple connections:

\[
Pool_{min} = T_n \times (C_m - 1) + 1
\]

Where T_n is the number of concurrent threads that can hold connections and C_m is the maximum number of connections a single thread can hold simultaneously. This formula gives the minimum threshold for pool-locking caused by nested acquisition; it is not an optimal throughput sizing formula.

For example, if 8 threads can each hold up to 2 connections at once, the formula yields 8 x (2 - 1) + 1 = 9. However, a better design is usually to avoid nested connection acquisition or holding one connection while waiting on another task. Do not inflate the pool using this formula if the application practically needs only one connection per transaction.

## 7. Managing Connection Lifecycle in Spring and JPA

A connection should be returned to the pool as soon as database work completes. With plain JDBC, use try-with-resources:

~~~java
try (Connection connection = dataSource.getConnection();
     PreparedStatement statement =
         connection.prepareStatement(
             "SELECT status FROM orders WHERE order_id = ?")) {

    statement.setLong(1, orderId);

    try (ResultSet resultSet = statement.executeQuery()) {
        if (resultSet.next()) {
            String status = resultSet.getString("status");
        }
    }
}
~~~

With Spring Data JPA, transactions are typically managed via @Transactional:

~~~java
@Service
public class OrderService {

    private final OrderRepository repository;

    public OrderService(OrderRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true)
    public Order findOrder(long orderId) {
        return repository.findById(orderId)
            .orElseThrow();
    }
}
~~~

Do not keep a transaction open while calling HTTP services, waiting on users, processing large files, or performing long non-database work. A long-running transaction holds a connection and may hold locks, rapidly exhausting the pool under load.

Check Open Session in View (OSIV). If the persistence context stays open until the end of the HTTP request, lazy-loading queries during response serialization can continue hitting the database after the service method finishes. For API applications, consider disabling OSIV and loading required data within the transaction/service layer before mapping to DTOs.

Avoid:

- Storing Connection, EntityManager, or JDBC resources in static fields or singletons.
- Manually calling close() on a connection managed by the Spring transaction manager outside its proper lifecycle.
- Holding connections while executing external non-DB work.
- Opening unnecessary nested transactions or using propagation modes that hold multiple connections.
- Running N+1 queries that keep connections busy longer and generate excessive round trips.

## 8. Observing HikariCP and Detecting Pool Exhaustion

HikariCP can emit metrics through Micrometer when a Spring Boot application integrates Actuator/Micrometer. Useful metrics commonly include:

| Metric | Meaning |
|---|---|
| Active connections | Connections currently borrowed |
| Idle connections | Connections currently idle in the pool |
| Pending threads | Number of threads waiting for a connection |
| Total connections | Total connections currently in the pool |
| Connection acquisition time | Time spent waiting to acquire a connection |
| Usage duration | Duration a connection is held |
| Timeout count | Number of failed acquisitions due to timeout |

Exact metric names depend on the HikariCP version, Micrometer version, and pool naming. Assign a distinct pool-name per datasource to distinguish them on dashboards.

Signs of pool exhaustion:

- Active connections consistently hit maximumPoolSize.
- Pending threads rise and remain elevated.
- Acquisition latency increases.
- Requests begin timing out while acquiring connections.
- MySQL CPU may not be overloaded, yet connections are held long by transactions or application code paths.

To investigate:

1. Identify which pool is exhausted via pool-name.
2. Inspect active, idle, pending, acquisition time, and usage duration.
3. Look for long transactions, slow queries, lock waits, and connection leaks.
4. Compare Threads_connected, Threads_running, and the process list on MySQL.
5. Check application instance counts and pool capacity after deploys or autoscaling.
6. Fix queries or connection lifecycles before considering growing the pool.

leakDetectionThreshold can help capture stack traces where connections are borrowed for too long. A warning might point to a legitimate slow transaction; correlate with usage duration and transaction logs before concluding there is a leak.

## 9. Adjusting max_connections on MySQL

Once you have a connection budget and evidence that the server limit is too low, a DBA may consider raising max_connections. Before doing so, evaluate RAM, CPU, per-connection buffer settings, thread counts, and OS resource limits.

Check the current value:

~~~sql
SHOW VARIABLES LIKE 'max_connections';
~~~

On versions supporting dynamic changes and with an appropriately privileged account, you can adjust the runtime value:

~~~sql
SET GLOBAL max_connections = 180;
~~~

Runtime changes may not persist across restarts. To make them durable, configure them in the MySQL configuration file or use a persistence mechanism supported by your version and operational workflow. After changing, re-check the variable and monitor memory, connection count, and latency.

Do not pick a very large value simply to silence Too many connections errors. Every connection consumes memory and resources; certain buffers are allocated per session or per query. An excessively high limit can cause the server to run out of RAM when many sessions become active simultaneously.

Beyond max_connections, there may be per-account limits such as max_user_connections, proxy limits, or cloud service limits. When an application is refused connections, check all of these layers.

## 10. Example Budget with Autoscaling

Suppose an API service scales up to 6 replicas under autoscaling, each replica running a HikariCP pool of max 10 connections. Workers scale up to 4 replicas with max 4 connections each. Reporting runs 2 replicas with max 3 connections each.

\[
C_{app} = 6 \times 10 + 4 \times 4 + 2 \times 3 = 82
\]

If backup, monitoring, migration, and admin tools need 15 connections, plus 20 reserved for headroom, the total budget is:

\[
C_{planned} = 82 + 15 + 20 = 117
\]

With max_connections at 140, roughly 23 connections remain outside the planned budget. Confirm that this margin suffices for ad-hoc tasks and actual service limits.

If autoscaling can scale the API up to 10 replicas, the application budget changes:

\[
C_{app} = 10 \times 10 + 4 \times 4 + 2 \times 3 = 122
\]

Adding 35 connections for operations and reserve yields 157, exceeding max_connections = 140. Therefore, resize pools based on real workload, set appropriate autoscaling limits, or adjust MySQL capacity after evaluating resources. Never budget solely on normal replica counts; always calculate for maximum autoscaling and rolling deployment overlap.

## 11. Sizing and Operations Checklist

### Before Deployment

- [ ] List every application, worker, datasource, and pool connecting to MySQL.
- [ ] Calculate maximum replica counts, including autoscaling and rolling deployments.
- [ ] Sum maximumPoolSize across all pools.
- [ ] Reserve budget for backups, monitoring, migrations, DBAs, and other services.
- [ ] Cross-check total budget against max_connections and per-user/proxy limits.
- [ ] Check RAM and per-connection overhead on MySQL.
- [ ] Measure real load and benchmark multiple pool sizes.
- [ ] Configure timeouts and connection lifetimes compatible with infrastructure.

### During Operations

- [ ] Monitor active, idle, pending, total, acquisition latency, and timeouts.
- [ ] Monitor Threads_connected, Threads_running, and Max_used_connections.
- [ ] Alert when connection usage remains close to limits for sustained periods.
- [ ] Investigate long transactions, slow queries, lock waits, and leaks before increasing pool size.
- [ ] Recalculate the budget when adding replicas, adding datasources, or deploying new services.
- [ ] Test failover/restarts to confirm pools recreate connections properly.

## 12. Practice Scenario

A Spring Boot application runs 5 replicas. Each replica has HikariCP with maximumPoolSize = 30. MySQL sets max_connections = 160. Beyond the application, workers and admin tools need roughly 25 connections; the operations team wants to keep 20 connections in reserve.

Calculate:

1. Maximum total connections from the API pools.
2. Total budget when adding workers, tools, and reserve.
3. Surplus or deficit compared to max_connections.
4. Changes to consider if autoscaling can scale the API to 7 replicas.

The API can open up to 5 x 30 = 150 connections. Adding 25 and 20 yields a budget of 195, exceeding the 160 limit. If the API scales to 7 replicas, the API alone could request 210 connections before counting other sources. Re-size pools based on real workload, set appropriate autoscaling caps, or scale server capacity after evaluating resources. Simply raising max_connections will not solve the root issue if MySQL lacks the capacity to handle that many concurrent sessions.

## 13. Self-Check Questions

1. Which connections does maximumPoolSize limit inside a HikariCP pool?
2. Why must total connections be calculated across application replica counts and datasource counts?
3. How does Threads_connected differ from Threads_running?
4. When active connections hit maximumPoolSize and pending threads rise, what should be checked before increasing the pool?
5. Why is connectionTimeout not a query timeout?
6. Which MySQL or infrastructure timeouts should maxLifetime be compared against?
7. Why does minimumIdle defaulting to maximumPoolSize create a fixed-size pool?
8. Why can setting max_connections too high starve MySQL of resources?
9. What scenario does the pool-locking formula address, and why is it not an optimal throughput formula?
10. After autoscaling increases replica counts, how should the connection budget be recalculated?

Sizing HikariCP is a coordination problem between the application and the database. Calculate potential total connections across all processes, reserve operational headroom, benchmark to find the right pool size, and monitor both HikariCP metrics and MySQL state. When connections are returned promptly and pools stay within database capacity, applications remain far more resilient under both normal traffic and load spikes.
