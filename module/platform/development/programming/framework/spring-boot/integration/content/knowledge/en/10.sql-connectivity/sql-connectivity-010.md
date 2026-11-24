# Sizing Connection Pools Across Total Application Replicas

## 1. Why Can a Pool That Looks Fine on One Pod Still Overload the Database?

In the **Spring Boot Integration** module, Spring Boot typically accesses PostgreSQL, MySQL, or another RDBMS through JDBC, JPA/Hibernate, `JdbcTemplate`, jOOQ, Spring Batch, and Spring Integration adapters. Most of those components acquire connections from a **pooled DataSource**, usually **HikariCP**. Pooling reduces the overhead of opening new connections, yet each physical connection still consumes resources on the database server.

A common mistake is setting `maximumPoolSize=30` because a single pod runs fine, and then scaling out to **8 replicas** without accounting for the database limit. That application alone can open up to **8 × 30 = 240 connections**, breaching capacity if PostgreSQL only allows around 200 connections and other applications share it.

In practice, total demand can grow even higher because:

- Old and new pods **run concurrently during rolling updates**.
- Horizontal Pod Autoscaler (HPA) scales replica counts during peak hours.
- Schedulers, Spring Batch workers, and Kafka/RabbitMQ consumers use **separate pools**.
- An application has **multiple DataSources**, multiple persistence units, or read/write splits.
- Migration jobs, operational tools, monitoring, and other services share the database.
- A call holds one connection in a transaction and opens a second connection for `REQUIRES_NEW` or another DataSource.

**Lesson objective:** Calculate pool limits across **all replicas and all consumers sharing the same database capacity**, configure HikariCP appropriately, recognize pool saturation, throttle concurrency, and test before scaling out or upgrading.

~~~mermaid
flowchart TB
    subgraph APP["Order Service - multiple replicas"]
      A["Pod A: Hikari max 12"]
      B["Pod B: Hikari max 12"]
      C["Pod C: Hikari max 12"]
      D["... Pod H: Hikari max 12"]
    end
    subgraph OTHER["Additional load sources"]
      X["Spring Batch: 3 workers x max 8"]
      Y["Other services, migrations, operations"]
    end
    A --> DB[("PostgreSQL: shared connection limit")]
    B --> DB
    C --> DB
    D --> DB
    X --> DB
    Y --> DB
~~~

Key takeaway: `maximumPoolSize` only caps **one pool inside one JVM**. It does not enforce a cluster-wide quota and does not coordinate across pools on other pods.

## 2. Understanding Connection Pools and What to Measure

| Concept | Meaning | Common misconception |
| --- | --- | --- |
| **Connection pool** | A set of reusable physical connections for JDBC work. | Not a durable request queue that survives restarts. |
| `maximumPoolSize` | Maximum physical connections **one Hikari pool** can manage. | Not the connection limit for the entire app or cluster. |
| `minimumIdle` | Target idle connections Hikari tries to maintain. | Does not change the `maximumPoolSize` ceiling; connections can still grow under load. |
| **Active connection** | Connection checked out by the app and currently held by a caller. | Might not be executing SQL; it may just be held by an open transaction. |
| **Idle connection** | Connection sitting in the pool ready for checkout. | Still a physical connection occupying a server slot. |
| **Pending acquisition** | Thread waiting for the pool to grant a connection. | Signals insufficient capacity or connections held too long. |
| `connectionTimeout` | Maximum wait time to **borrow a connection from Hikari**. | Not the SQL timeout or overall request deadline. |
| **Database connection limit** | Maximum backend sessions or connections allowed by the DB. | Shared across multiple apps, admin sessions, and replication depending on the engine. |

In Spring Boot, calls through `JdbcTemplate`, JPA `EntityManager`, jOOQ, or `DataSource` directly can **share one pool** if configured with the same DataSource bean. Conversely, two distinct `HikariDataSource` beans normally maintain **two independent pools**, even if both point to **the exact same PostgreSQL server**.

**Active ≠ running queries:** A connection can be held by a transaction waiting on an HTTP API call or Java processing while the database executes zero SQL. That causes pool exhaustion even when DB CPU stays low.

## 3. Formula for Cluster-Wide Connection Budgeting

Before choosing a pool size, list every source **drawing from the same connection budget**. For a database server/endpoint with a total connection limit, estimate the application budget as:

\[
C_{\text{app-budget}} =
C_{\text{db-limit}}
- C_{\text{reserved}}
- C_{\text{other-apps}}
- C_{\text{operations}}
- C_{\text{safety}}
\]

Where:

- `C_db-limit`: connection limit on the database instance/endpoint in use, per managed service settings and policy.
- `C_reserved`: slots that should not or cannot be given to ordinary apps, such as admin connections and engine-reserved capacity.
- `C_other-apps`: total budget allocated to other clients sharing the database.
- `C_operations`: headroom for migrations, backups/monitoring, reconciliation scripts, and intermittent tasks.
- `C_safety`: extra safety margin to avoid running right up against the ceiling.

Across multiple application groups:

\[
\sum_{g=1}^{G}
\left(N_{g,\text{peak}} \times P_{g,\max}\right)
\le C_{\text{app-budget}}
\]

`N_g,peak` is the **peak number of replicas that can exist concurrently** for group `g`, and `P_g,max` is the pool cap **per replica**. If a pod has multiple DataSources connecting to the same database, sum each pool. If batch jobs run in their own pool or pods, count the batch group separately.

This represents the **worst-case ceiling when every pool opens all connections**, not average connection usage. Use this ceiling to prevent configurations that can breach quotas at peak load; then use real load metrics to decide whether pools actually need to be that large.

### 3.1. Calculation Example with 8 Pods and Batch Workers

Suppose a PostgreSQL instance has a total connection limit of **200**. Operations allocates budgets based on internal data and policy:

| Consumer | Reserved / planned connections |
| --- | ---: |
| PostgreSQL limit | **200** |
| Admin and non-application connections | 25 |
| Other applications sharing the DB | 20 |
| Migrations, monitoring, operational tasks | 15 |
| **Remaining budget for Order + Batch** | **140** |

During rollouts or peak HPA scaling, up to **8 Order pods** can run simultaneously. In addition, **3 Spring Batch workers** share the database.

If configured as:

- Order pool: **12 connections/pod** ⇒ `8 × 12 = 96`.
- Batch pool: **8 connections/worker** ⇒ `3 × 8 = 24`.
- Combined peak across both groups: **120 connections**.
- Remaining buffer in the model: **140 − 120 = 20 connections**.

Both groups still require monitoring; "20 remaining" is a **model margin**, not a guarantee that 20 slots are always free if baseline assumptions shift. The 25/20/15 and 12/8 figures are **illustrative values**, not universal defaults for every PostgreSQL cluster.

~~~mermaid
flowchart LR
    A["200: DB limit"] --> B["-25: admin reserve"]
    B --> C["-20: other apps"]
    C --> D["-15: operations"]
    D --> E["140: Order + Batch budget"]
    E --> F["96: Order (8 x 12)"]
    E --> G["24: Batch (3 x 8)"]
    E --> H["20: remaining margin"]
~~~

If the Order pool grows from 12 to 20, the combined maximum becomes `8 × 20 + 3 × 8 = 184`, **exceeding 140**. Yet a single pod tested locally with `maximumPoolSize=20` would show no errors at all.

### 3.2. Include Rolling Updates and HPA

Do not use the **current replica count** as `N_peak` during sizing. Account for:

1. Maximum replicas HPA can scale out to.
2. Extra pods allowed by `Deployment.spec.strategy.rollingUpdate.maxSurge` during rollouts.
3. Scheduled jobs, canaries, blue-green deployments, or new pods starting before old pods **release their connections**.
4. Multiple namespaces, clusters, or regions sharing the same database.
5. Whether pools open connections eagerly on startup or lazily under load, and whether the DB can survive a **connection storm** when many pods start at once.

For instance, if HPA maxes at 6 replicas and rolling updates allow +2 surge pods → **8 pods** is a sound sizing ceiling, **provided** that is the actual concurrent maximum enforced by the platform. With blue-green running two full deployments side by side, count both groups, which can be much larger.

## 4. Pool Size Should Not Equal Thread Count or HTTP Request Count

An HTTP request may execute several JDBC queries, yet it **does not necessarily hold a connection for its entire response duration**. Pool sizing should reflect:

- Actual request rate, including scheduled jobs, event consumers, and retries.
- Queries or transactions per request.
- Average and p95/p99 connection **checkout hold time**.
- Database CPU/I/O, locks, disk, and backend worker limits.
- Number of concurrent pools and the system-wide quota.

By **Little's Law** in steady state:

\[
L = \lambda W
\]

If the application handles **180 requests/second**, each request checks out a connection an average of **2 times**, and holds it for about **25 ms** per checkout, average concurrent checkouts across the cluster are roughly:

\[
L \approx 180 \times 2 \times 0.025 = 9
\]

The figure **9** is only an **average estimate**—never conclude a total pool of 9 is safe. It ignores bursts, uneven pod distribution, long transactions, deadlocks, p99 spikes, and batch jobs. Use real telemetry and load tests to find the minimum pool meeting latency SLOs, then check the upper bound against the **cluster-wide budget formula** in section 3.

**Increasing pool size does not automatically raise database throughput.** Once the DB is saturated on CPU, I/O, locks, or WAL, adding concurrent connections usually increases contention and queueing, worsening latency. Reducing pool size and capping application concurrency often restores stability.

## 5. Configuring HikariCP in Spring Boot Within Budget

Example using **Java 17+, Spring Boot 3.x, Spring Data JDBC/JPA, and PostgreSQL**. With a single Boot auto-configured DataSource:

~~~yaml
# application.yml — illustrative pool per Order pod
spring:
  datasource:
    url: jdbc:postgresql://db.internal:5432/orders
    username: ${ORDERS_DB_USERNAME}
    password: ${ORDERS_DB_PASSWORD}
    hikari:
      pool-name: orders-pool
      maximum-pool-size: 12
      minimum-idle: 3
      connection-timeout: 1500
      validation-timeout: 1000
      idle-timeout: 600000
      max-lifetime: 1500000
      keepalive-time: 300000
      data-source-properties:
        ApplicationName: orders-service
~~~

In this example, Hikari timeouts/lifetimes are in **milliseconds**. Passwords must come from a secret manager or authorized environment variables; never commit passwords to the repository. `db.internal` is a placeholder requiring proper network and TLS configuration in deployment.

| Property | Role | Important note |
| --- | --- | --- |
| `maximum-pool-size: 12` | Caps the physical pool per JVM. | Total cluster ceiling depends on JVM/pool count sharing the DB. |
| `minimum-idle: 3` | Aims to keep at least 3 idle connections when possible. | Pool can still grow up to 12; not capped at 3. |
| `connection-timeout: 1500` | Waits at most 1.5 seconds to acquire a connection from the pool. | Not a 1.5-second limit for the entire SQL or HTTP request. |
| `validation-timeout: 1000` | Limits connection liveness check time. | Must be smaller than `connectionTimeout` and obey Hikari bounds. |
| `idle-timeout: 600000` | Allows retiring idle connections above `minimumIdle`. | Has little effect in a fixed pool where `minimumIdle=maximumPoolSize`. |
| `max-lifetime: 1500000` | Retires connections after a maximum age. | Should be shorter than DB/proxy lifetime limits; active connections retire only upon return. |
| `keepalive-time: 300000` | Periodically probes idle connections to prevent silent closure. | Must be shorter than `maxLifetime`; does not replace health queries or timeouts. |
| `pool-name` | Identifies the pool in logs and metrics. | Name by source; avoid personal data or high-cardinality instance IDs in tags. |

**`minimumIdle` policy:** HikariCP generally recommends operating as a fixed-size pool for predictable latency under load—leaving `minimumIdle` unset so it defaults to `maximumPoolSize`. This example sets `minimum-idle: 3` to illustrate an elastic pool, but you must measure connection creation latency and connection storms during autoscaling. Whether fixed or elastic, **upper-bound budgeting must use `maximumPoolSize`**, not `minimumIdle`.

### 5.1. Using Environment Variables to Adjust Budgets per Deployment

Placeholders allow tuning per deployment:

~~~yaml
spring:
  datasource:
    hikari:
      maximum-pool-size: ${ORDERS_DB_POOL_MAX:12}
~~~

The deployment platform sets `ORDERS_DB_POOL_MAX` (or uses Spring Boot's mapped environment variable `SPRING_DATASOURCE_HIKARI_MAXIMUM_POOL_SIZE`). When replica counts change, update this budget according to the capacity model; never scale pools independently by pod CPU while ignoring total database limits.

If the app defines multiple custom `DataSource` beans, `spring.datasource.hikari.*` **does not automatically apply to all beans**. Each DataSource must bind its own prefix and pool limit—such as `app.datasource.orders.hikari.maximum-pool-size` and `app.datasource.reporting.hikari.maximum-pool-size` via `@ConfigurationProperties`.

### 5.2. Don't Overlook Other Timeouts

Hikari's `connectionTimeout` controls only **waiting for checkout**. Distinguish it from:

- **JDBC driver connect/socket timeout:** time to establish the DB connection and wait for network I/O, driver-dependent.
- **Query/statement timeout:** bounds runaway SQL statements via JDBC statement timeout or DB-side settings.
- **Transaction timeout:** bounds transactional work per framework/execution semantics; does not automatically abort every blocking driver call.
- **Network proxy/load balancer idle timeout:** may drop idle connections; coordinate with `maxLifetime` and `keepaliveTime`.
- **Request deadline:** overall HTTP/gRPC/batch time budget. If a request times out while SQL continues running, proper cancellation and cleanup policies are needed.

Never simply bump `connection-timeout` from 1.5 seconds to 30 seconds when the pool saturates. That causes more HTTP threads to pile up and masks root causes like slow queries, locks, or leaks.

## 6. Aggregating Multiple DataSources and Multiple Worker Types

A single application pod might contain:

~~~text
Order Service pod
  ├── ordersDataSource      (PostgreSQL A, max 12)
  ├── auditDataSource       (PostgreSQL A, max 4)
  └── reportingDataSource   (PostgreSQL B, max 6)
~~~

Here the ceiling against **PostgreSQL A** per pod is **12 + 4 = 16**, while PostgreSQL B receives at most **6**. Across 8 pods, A alone can receive **128 connections** from these two pools. Do not count Reporting's 6 connections toward A if it genuinely connects to a **separate database instance with its own connection quota**.

However, never split budgets by **schema name** or logical database and assume separate quotas. Two schemas or logical databases can live on the same PostgreSQL server sharing `max_connections`. Group budgets by the **actual connection enforcement point** (instance, cluster/proxy, or managed DB service) and sum every pool targeting it.

| Connection source | Usually creates its own pool? | Include in budget? |
| --- | --- | --- |
| JPA/Hibernate via one DataSource | Not separately; uses the DataSource's configured pool. | Yes, **count the pool once**. |
| Spring JDBC + jOOQ sharing one DataSource | Can share the same pool. | Do not double-count if genuinely the same DataSource bean. |
| Two persistence units with two DataSources | Usually two independent pools. | Sum both if targeting the same DB. |
| Spring Batch metadata and writer | May share one or use two distinct DataSources. | Verify actual beans; include separate pools and active workers. |
| Quartz JDBC JobStore | May have a dedicated DataSource/pool for scheduler metadata. | Include in budget if on the same database. |
| Spring Integration JDBC poller | Usually uses the injected DataSource. | Count load/concurrency; add a pool only if it uses a separate DataSource. |
| Flyway/Liquibase/migration tool | May open short-lived separate connections. | Reserve operational headroom during deployments. |

For **read replicas**, budget each target separately. Replicas have their own connection limits and resources, though an upstream proxy may impose a different cap; inspect actual settings rather than treating "read-only" as free.

## 7. Limiting Concurrency Before Work Holds Connections

The pool is a last line of defense, **not an admission controller for all incoming traffic**. If thousands of requests enter and each waits 1.5 seconds for checkout before timing out, the app can still exhaust threads and memory. Cap concurrency at the processing layer according to real capacity:

~~~mermaid
flowchart LR
    A["HTTP / Kafka / RabbitMQ / Batch"] --> B{"Admission / backpressure"}
    B -->|"Within capacity"| C["Short service transaction"]
    B -->|"Overloaded"| X["Reject / defer / durable queue"]
    C --> D["Hikari pool"]
    D --> E[("Database")]
    E --> F["Return connection to pool"]
~~~

How to apply this:

1. **HTTP:** apply concurrency limits, rate limits, and timeouts, returning controlled errors when unable to accept more work rather than spawning unbounded threads waiting on the pool.
2. **Broker consumers:** tune listener concurrency, prefetch/poll batch sizes, worker pools, and ack timing to actual DB throughput; never pull more work than the DB can sustain.
3. **Spring Batch:** limit concurrent `JobExecution`/partitions/threads. A step with 20 workers does not automatically need a pool of 20, yet if each worker holds a connection for long periods, budget actual concurrency.
4. **Spring Integration:** `ExecutorChannel` or pollers can multiply concurrent handlers. Choose bounded executors with bounded queues; in-memory `QueueChannel` instances do not survive restarts.
5. **Scheduled jobs:** prevent duplicate cron execution across replicas or overlapping runs; use `JobRepository`, clustered Quartz, or distributed locks as appropriate.

When the DB is overloaded, **reducing concurrent execution** often improves throughput and latency more than raising `maximumPoolSize`. Apply backpressure before committing to side effects so promised work is not dropped; if queuing, use durable storage and explicit timeout/retry/DLQ policies.

### 7.1. Avoid Holding Transactions While Calling External Systems

~~~java
// Anti-pattern: DB transaction may be held while waiting for HTTP.
@Transactional
public void confirmOrder(UUID orderId) {
    OrderEntity order = repository.findById(orderId).orElseThrow();
    paymentClient.authorize(orderId); // HTTP call may take several seconds
    order.confirm();
}
~~~

Depending on the JPA provider and connection acquisition timing, a connection may be held for most of the transaction. With 12 connections/pod, just 12 slow calls exhaust the pool despite minimal SQL work. Moreover, DB rollback **cannot** undo a payment already authorized over HTTP.

A better design for long-running external work uses a short transaction to store `PENDING` state plus a **transactional outbox**, followed by a worker calling the partner and updating state in a separate transaction. Even for synchronous requirements, enforce deadlines, concurrency limits, and tight transaction boundaries so slow HTTP calls do not hold connections unnecessarily.

### 7.2. Be Careful with Nested Transactions and `REQUIRES_NEW`

When a transaction already holds a connection and invokes a method with `@Transactional(propagation = REQUIRES_NEW)`, the inner transaction may require a **second connection** while the outer connection remains held. Many concurrent threads doing this can deadlock waiting on the pool even though each thread "normally uses one connection."

Prefer redesigning transaction boundaries to avoid nested transactions holding multiple connections simultaneously. If independent nested transactions are truly needed, factor concurrent connections per worker into sizing and test under saturation. Do not size the pool solely by request thread count expecting it to suffice.

## 8. Connection Pools and Transactions Do Not Create "Free" Connections

Practical FAQs:

**Does sharing a pool across multiple beans multiply connections?** No. If `JdbcTemplate`, JPA repositories, and jOOQ all inject the same properly managed `DataSource`, they share that pool's `maximumPoolSize` cap. You must still account for **competing demand** across components.

**Can one logical DataSource accidentally spawn multiple pools?** Yes, if the application context unintentionally creates multiple Hikari beans with the same JDBC URL, or a library constructs its own DataSource. Inspect actual beans and metrics; do not assume identical DB names mean a single pool.

**Do idle connections count toward the DB limit?** Yes. An idle connection typically remains an open backend session occupying a database server slot until closed.

**Does an instance with `maximumPoolSize=12` always keep 12 connections open?** Not necessarily. Hikari may start smaller and grow under demand, depending on `minimumIdle`, initialization timing, and pool state. Still, **12 remains the ceiling you must budget for**.

**Does increasing the pool fix slow queries?** Usually not if the bottleneck is locks, missing indexes, disk, or DB CPU. When acquisition wait is high alongside high active connections, investigate **why connections are held so long** before enlarging the pool.

## 9. Observing PostgreSQL and HikariCP to Pinpoint the Bottleneck

### 9.1. Inspecting PostgreSQL Limits

Use **read-only** SQL to inspect instance connection limits:

~~~sql
SHOW max_connections;
SHOW superuser_reserved_connections;

-- Inspect reservation parameters present on the running version:
SELECT name, setting
FROM pg_settings
WHERE name IN (
    'max_connections',
    'superuser_reserved_connections',
    'reserved_connections'
)
ORDER BY name;
~~~

Some PostgreSQL versions include `reserved_connections`, while others do not; querying `pg_settings` checks which parameters exist. On managed PostgreSQL, also account for service limits, proxies, role-specific limits, and operational connections.

Count backends by application and state:

~~~sql
SELECT
    COALESCE(application_name, '') AS application_name,
    COALESCE(state, 'unknown') AS state,
    COUNT(*) AS connections
FROM pg_stat_activity
WHERE backend_type = 'client backend'
GROUP BY 1, 2
ORDER BY connections DESC, application_name;
~~~

In the PostgreSQL JDBC driver, `ApplicationName` can be set via DataSource properties. A stable name like `orders-service` groups sessions cleanly; to distinguish pods, use logs/telemetry or controlled naming rather than creating unbounded metric tag cardinality.

Find sessions holding open transactions too long:

~~~sql
SELECT
    pid,
    application_name,
    state,
    now() - xact_start AS transaction_age,
    now() - query_start AS query_age,
    wait_event_type,
    wait_event
FROM pg_stat_activity
WHERE xact_start IS NOT NULL
ORDER BY xact_start ASC
LIMIT 30;
~~~

This query requires appropriate monitoring privileges. `idle in transaction` deserves special attention: a session may hold locks and snapshots while executing no queries. Never bulk-terminate backends from this output; check ownership and transaction impact before running administrative actions.

### 9.2. Hikari Metrics to Watch Together

With `spring-boot-starter-actuator` and Micrometer configured, you can track Hikari metrics such as:

- `hikaricp.connections.active`: checked-out connections.
- `hikaricp.connections.idle`: idle connections in the pool.
- `hikaricp.connections.pending`: threads waiting for a connection.
- `hikaricp.connections.max` and `hikaricp.connections.min`: configured bounds.
- `hikaricp.connections.timeout`: timed-out checkout attempts, depending on metric export.
- Connection acquire/usage/creation timers if provided by your exporter/ecosystem.

Metric names and types can vary by Micrometer/registry version; verify actual Actuator/Prometheus endpoints. Tag by **pool name, service, and environment**, avoiding per-SQL, user ID, or request ID tags.

| Signal | Possible interpretation | First action |
| --- | --- | --- |
| Active ≈ max, pending rising | Pool out of capacity. | Inspect checkout duration, transactions, slow queries, locks, and worker concurrency. |
| High active, low DB CPU | Connections held waiting on HTTP, locks, or non-SQL code. | Check stack traces, `idle in transaction`, long transactions. |
| DB `too many clients already` while pods aren't full | Combined pods/pools/apps exceed server sessions. | Sum cluster-wide budgets and inspect rollout surges. |
| Acquisition timeouts spike after scaling | New connections fail/slow or DB contention rises. | Check `max_connections`, network/TLS, bootstrap, and `maxSurge`. |
| Too many idle connections across replicas | Pools hold excessive standby slots. | Evaluate `minimumIdle`, pool count, replica count, and off-peak load. |
| Connections held very long | Long transactions, leaks, or oversized jobs. | Trace checkouts, query timeouts, transaction scope, and bounded leak detection. |

## 10. Common Connection Errors and Diagnosis

### 10.1. `Connection is not available, request timed out after ...`

This is typically a **Hikari pool checkout timeout**, not necessarily a dead database. Investigation order:

1. Check `active`/`idle`/`pending`/`max` for the exact pool and pod at the error timestamp.
2. If `active ≈ max`: look for long transactions, lock waits, or code paths failing to return connections.
3. If new connections cannot be created: inspect DB logs, auth/TLS/network, session limits, and sudden pool surges.
4. Correlate timing with Spring Batch schedules, Kafka consumer rebalances, large cache-miss spikes, or rollouts.
5. Adjust pool size only after checking total cluster budget and DB capacity.

### 10.2. PostgreSQL Reports `too many clients already`

This error indicates the database has no room for a new connection under the caller's privileges. If combined pool caps across apps exceed available `max_connections`, raising Hikari's `connectionTimeout` only makes callers wait longer; it does not increase PostgreSQL's connection slots.

Reduce total pool caps, concurrent pods, or connection hold times, or route part of the traffic appropriately; if raising `max_connections`, evaluate RAM, CPU, OS limits, and real DB capacity. On managed databases, this parameter often ties to instance size and may require a restart or maintenance window.

### 10.3. Connection Leaks and Long-Held Connections

In plain JDBC, omitting `try-with-resources` can leak connections. With Spring, resource-managed APIs normally return connections via templates and transaction infrastructure, but code calling `dataSource.getConnection()` directly must close properly:

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import javax.sql.DataSource;

public long countOrders(DataSource dataSource) throws Exception {
    try (Connection connection = dataSource.getConnection();
         PreparedStatement statement =
                 connection.prepareStatement("SELECT COUNT(*) FROM orders");
         ResultSet rows = statement.executeQuery()) {
        rows.next();
        return rows.getLong(1);
    }
}
~~~

When participating in Spring-managed transactions, prefer `JdbcTemplate`/JPA or transaction-aware connection helpers rather than manually managing connections and breaking Spring's boundaries. Hikari's `leakDetectionThreshold` logs warnings when a connection is checked out longer than the threshold; this is a **diagnostic signal**, not proof of a real leak, and it does not close the connection. Choose a threshold high enough to avoid false positives on legitimate long jobs, and avoid unbounded sensitive logging.

## 11. PgBouncer / RDS Proxy and Layered Connection Limits

When replica counts are high or applications hold many idle connections, consider a **database-side connection pooler/proxy** such as PgBouncer or a managed cloud proxy. You must then manage **two budgets**:

1. Client connections from the application to the pooler/proxy.
2. Actual server connections from the pooler/proxy to the database.

For example: 20 pods with Hikari max 10 each ⇒ up to **200 client-side connections to the pooler**, while the pooler may maintain only **50 shared server connections** depending on configuration and load. This lowers concurrent backend sessions on the database, yet **does not create infinite throughput**: transactions waiting for a pooler slot still time out.

| Mode / aspect | Points to check |
| --- | --- |
| **Session pooling** | Server connection stays tied to a client longer; lower multiplexing efficiency, better for session-scoped state. |
| **Transaction pooling** | Server connections can be reassigned across clients after each transaction. | Cannot assume session state persists across transactions. |
| **Prepared statements** | Compatibility depends on JDBC driver, PgBouncer version, and prepared statement support config. | Test against the real setup; do not assume all setups work or fail identically. |
| **Temporary tables, session variables, advisory locks** | Session-bound features may misbehave when server connections swap between transactions. | Review usage, scope, or use session pooling. |
| **Long transactions** | Pin a pooler server connection for the entire transaction. | Proxies do not fix applications holding transactions during external I/O. |

JPA/Hibernate, Spring Batch, and JDBC drivers can rely on prepared statements or transaction semantics in subtle ways. Before adopting transaction pooling, test transactions, batch writers, migrations, locks, and session-state features. Never shrink app pools blindly just because a proxy exists without checking pooler saturation and DB SLAs.

## 12. Tuning Pools Across Deployments and Autoscaling

### 12.1. Controlled Configuration Change Workflow

1. **Measure baseline** at peak load: pod count, active pools, active/pending, checkout times, DB sessions, CPU, I/O, lock waits, and app latency.
2. **Build a budget sheet** per database instance/proxy, covering other services, Batch, Quartz, migrations, and rolling surges.
3. **Pick conservative caps**, test with bounded concurrency; avoid changing multiple variables at once so root causes stay clear.
4. **Load test** from low to high replica counts, explicitly testing rolling updates and autoscaling under heavy load.
5. **Monitor post-deploy**, especially connection counts during the first few minutes when pods start, startup probes run, and batches trigger.
6. **Keep a load-shedding/rollback plan** if the DB or pooler cannot keep up, rather than relying on emergency `max_connections` increases.

### 12.2. Deployment-Level Budget Example

~~~yaml
# Kubernetes configuration snippet, not a complete manifest.
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders-api
spec:
  replicas: 6
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 2
      maxUnavailable: 0
  template:
    spec:
      containers:
        - name: orders-api
          image: example/orders-api:1.0.0
          env:
            - name: ORDERS_DB_POOL_MAX
              value: "12"
~~~

Here, `replicas: 6` and `maxSurge: 2` require budgeting for **8 pods** during rollouts. Real sizing must also include HPA, canaries, blue-green deployments, and other workloads. **These fields do not enforce a global connection cap**: if operators raise HPA limits or deploy another worker group, the pool budget must be updated accordingly.

**Avoid startup connection storms:** If 50 pods open many connections at once to initialize JPA metadata or pass health checks, the database can stall before request traffic even rises. Use paced rollouts, proper readiness probes, sensible pool warm-up, and a coordinated migration job instead of having every pod run migrations concurrently.

## 13. Testing Connection Limits Under Failure Conditions

A load test should measure **actual connections reaching the database**, not just successful HTTP responses.

| Scenario | Expected behavior |
| --- | --- |
| Single pod under normal load | Active/idle/pending stay healthy; no need for huge pools just for many HTTP threads. |
| Scaling up to HPA maximum | Total connections across all pools stay within the modeled target budget. |
| Rolling update under high load | Old + new pods do not exhaust DB connections; readiness remains stable. |
| Concurrent Spring Batch and Quartz | Additional pools are accounted for; API is not starved when jobs start. |
| Two persistence units against one PostgreSQL | Sum both pools; do not undercount by schema name. |
| DB queries 10× slower | Rising pending is observed; admission/backpressure triggers before thread exhaustion. |
| Checkout timeouts across many requests | App fails gracefully without infinite immediate DB retries. |
| Slow downstream HTTP inside a transaction | Long connection hold times are caught; refactoring shrinks transaction duration. |
| Manual JDBC connection leak | Metrics and leak detection fire; tests fail if connections are unclosed. |
| DB failover or network partition | Pool evicts dead connections cleanly without an infinite reconnect storm. |
| Changing `minimumIdle` off-peak | Verified idle counts and connection-creation impact on the next burst. |
| PgBouncer transaction pooling | Verified prepared statements, session state, JPA transactions, and batch writers. |

With Spring Boot, you can combine `@SpringBootTest`, PostgreSQL Testcontainers, Micrometer/Actuator, and HTTP or broker load generators. For **multi-pod** scenarios, single-JVM tests are insufficient; test in a topology-matched environment to verify total database sessions/connections.

Never disable `max_connections` limits in test environments and assume the configuration is safe. Scale test limits proportionally to production and run load tests only on authorized databases or sandboxes.

## 14. Incident Runbook: Pool Exhaustion After Scaling Replicas

Suppose after a rollout, the API returns widespread 503s and Hikari logs `Connection is not available, request timed out`:

1. **Isolate:** identify failing APIs, which deployment scaled up, which pool is exhausted, and which DB is near its ceiling.
2. **Stop amplification:** cap admission/concurrency, pause low-priority jobs, prevent retry storms; avoid scaling out more pods just because app CPU rises if the DB is already overloaded.
3. **Verify quota:** check `max_connections` and sessions by `application_name`, summing caps across all pods/pools including batch and rollout surge.
4. **Inspect hold time:** check active/max, pending, slow queries, lock waits, `idle in transaction`, and code paths making HTTP calls inside transactions.
5. **Mitigate safely:** reduce worker/consumer counts, trim oversized pools, defer non-urgent work to durable queues, or roll back the rollout; raise DB capacity only via planned operational changes.
6. **Reconcile side effects:** if requests timed out after DB commit or external calls ran, reconcile via operation IDs/idempotency rather than blindly retrying writes.
7. **Recover and re-verify:** ramp traffic gradually, watch total sessions, pending counts, and p95/p99 latency; codify the pool budget as a deployment rule.

If the incident stems from slow queries or locks, shrinking the pool may ease contention temporarily, but does not replace SQL/index optimization and fixing transaction boundaries. If total replicas breached the quota, enlarging per-pod pools almost certainly worsens the outage.

## 15. Checklist Before Changing Pool Sizes or Scaling Replicas

- [ ] Know the **actual** database/proxy connection limit and slots reserved for admin, other systems, and safety headroom.
- [ ] Inventory every pool hitting each database: JDBC, JPA, jOOQ, Batch, Quartz, adapters, migrations, and auxiliary workers.
- [ ] Accounted for **peak concurrent pods**, including HPA, rolling updates, canary/blue-green, and multiple clusters.
- [ ] Total `N_peak × maximumPoolSize` across all pools targeting the same DB fits within the agreed budget.
- [ ] Pool sizes validated using QPS, checkout duration, DB CPU/I/O/locks, and p95/p99—not thread counts alone.
- [ ] `minimumIdle`, `connectionTimeout`, `maxLifetime`, and JDBC/SQL/deadline timeouts match real environment constraints.
- [ ] No connections/transactions held while waiting on HTTP or external tasks; `REQUIRES_NEW` paths reviewed.
- [ ] Concurrency limits/backpressure enforced for HTTP, consumers, schedulers, and Spring Batch.
- [ ] Hikari metrics, `pg_stat_activity`, dashboards, and alerts configured for pending/timeouts/session saturation.
- [ ] Multi-replica load tests, peak-hour rollout tests, DB failover drills, and load-shedding/rollback plans in place.

**Conclusion:** The optimal connection pool is not the largest pool each pod can open, but one **small enough that the entire cluster stays within database capacity while remaining large enough for measured workloads**. In Spring Boot Integration, HikariCP limits must be evaluated alongside replica counts, multiple DataSources, Batch/Quartz, broker flows, transactions, and downstream latencies. Only by managing connection budgets, hold times, backpressure, and failure recovery together can a system scale without causing cascading overload on the SQL database.
