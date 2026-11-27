# Sizing Connection Pool Limits Based on Resources and Application Replicas

In a Spring Data Relational R2DBC application, the connection pool limits the number of database connections a single application instance can use concurrently. The `maxSize` value is not just a performance tuning parameter: when an application runs multiple replicas, the total number of connections that can be opened equals the sum of pools across all instances, workers, and services accessing the database. If each pod configures an overly large pool, autoscaling or rolling deployments can push the database past its connection limit even though each individual pod looks reasonable on its own.

Pool design requires balancing three factors: **database capacity**, **maximum replica count across all clients**, and **workload concurrency and connection hold time**. A pool that is too small creates acquire queues and increases latency; a pool that is too large increases sessions, memory, scheduling, and contention on the database. The goal is to choose a limit sufficient for expected load, with headroom for spikes, while staying within the system-wide connection budget.

## 1. What problem does a connection pool solve?

Opening a database connection has overhead: TCP/TLS setup, authentication, session initialization, and driver/database handshakes. If every operation opened and closed a new connection, latency and infrastructure load would surge.

An R2DBC connection pool keeps a set of connections for reuse:

```text
HTTP request / background job
             |
             v
       R2DBC Connection Pool
        /       |        \
       v        v         v
   Connection Connection Connection
       |        |         |
       +--------+---------+
                |
                v
             Database
```

When an operation needs the database, the application requests a connection from the pool. If an idle connection is available, the pool grants it immediately. Otherwise, the request waits in the acquire queue until a connection is returned or the wait timeout expires. When the operation finishes and lifecycle cleanup runs, the connection is returned to the pool or discarded if no longer valid.

The pool enables connection reuse and caps concurrency toward the database. It does not make the database process more queries than its CPU, I/O, locks, or memory can handle. Increasing the connection count can increase throughput up to a point, after which it only increases contention.

## 2. Distinguishing pool size, active connections, and request concurrency

These concepts are not the same:

| Concept | Meaning |
|---|---|
| `maxSize` | Maximum number of connections a single pool is allowed to manage |
| `initialSize` | Number of connections the pool attempts to create initially, depending on implementation and initialization timing |
| Allocated/total | Number of connections currently created by the pool |
| Acquired/active | Number of connections currently leased to consumers |
| Idle | Number of free connections available to be leased |
| Pending acquire | Number of requests waiting for a connection |
| Application concurrency | Number of tasks/requests that can run concurrently in the application |
| Database max connections | Session/connection limit on the database or proxy |

An application handling 500 concurrent HTTP requests does not necessarily need 500 database connections. Many requests may not touch the database, may wait on other I/O, or database operations may occupy only a fraction of request duration. Conversely, a single request may run multiple sequential queries or multiple parallel database tasks.

Therefore, do not set `maxSize` equal to the thread count, CPU count, or maximum HTTP requests. Measure the number of concurrent database operations and how long each operation holds a connection.

## 3. Connection budgeting starts at the database

A database typically has a connection/session limit. That limit must serve all clients, not just one Spring Boot application.

Examples of groups sharing the database:

- Replicas of the primary API.
- Workers/consumers and scheduled jobs.
- Other services sharing the database.
- Migration jobs, schema tools, and deployment tasks.
- Dashboards, BI, reporting, or batch integrations.
- DBAs, monitoring, backups, replication, and administrative connections.
- Reserved connections for failover or incident response.

Never allocate the entire `max_connections` to application pools. Keep headroom reserved for administration and other workloads, and account for actual database limits on RAM, CPU, file descriptors, and per-session overhead.

A simple budget formula:

\[
\text{Connection budget for service}
= \text{DB connection limit}
- \text{reserved capacity}
- \text{other clients}
\]

This is the total budget for the service across all replicas and all pools belonging to that service, not the budget per pod.

### 3.1. Budget allocation example

Suppose a PostgreSQL instance has a limit of 300 connections. The operations team reserves 50 connections for administration, monitoring, failover, and headroom; other services have a maximum budget of 70; migrations/reporting and internal tools require another 20.

| Component | Planned connections |
|---|---:|
| DB connection limit | 300 |
| Reserved/administration | 50 |
| Other services | 70 |
| Migration/reporting/tools | 20 |
| Remaining for the service being designed | 160 |

160 is the total ceiling for this service in this hypothetical scenario. If the service has multiple pools (e.g., primary and read replica), the sum of `maxSize` across all pools and all replicas must stay within its assigned budget.

These numbers are examples only. `max_connections` does not mean the database can efficiently execute that many queries simultaneously; true capacity must be determined via load testing and server metrics.

## 4. Replica counts multiply total pool size

Each instance typically creates its own pool. If an application has `R` replicas and each replica has at most `P` connections:

\[
\text{Total maximum connections} = R \times P
\]

If there are multiple pools per instance:

\[
\text{Total maximum connections}
= R \times \sum_{i=1}^{n} P_i
\]

Where `P_i` is the max size of the `i`-th pool on an instance. Expand this formula if you have multiple replica types or workers with different configurations.

For example, a service with 8 replicas and a per-pod pool `maxSize = 30`:

\[
8 \times 30 = 240\text{ connections}
\]

If autoscaling increases replicas to 12, the total ceiling becomes 360 connections. The database can exceed its budget even though the configuration inside each pod did not change.

### 4.1. Always use the maximum replica count, not the average

Pools must be sized for the maximum permitted scale, including:

- `maxReplicas` of the Horizontal Pod Autoscaler.
- Fixed replicas outside the HPA.
- Worker deployments that scale independently.
- Concurrent CronJobs or batch jobs.
- Old instances still alive during rolling deployments.
- Temporary replicas during rollouts, canaries, or blue-green deployments.

Calculating from typical off-peak pod counts can cause the system to breach database limits right when autoscaling scales out to handle high load.

### 4.2. Rolling deployments and surge capacity

During a rolling update, Kubernetes or the deployment platform may spin up new pods before stopping old ones. `maxSurge` temporarily pushes replica counts above desired `replicas`.

For example, a deployment with 8 replicas allowing a surge of 2 extra pods can have 10 pods alive during a rollout. With a max pool of 16 per pod:

\[
10 \times 16 = 160\text{ connections}
\]

Calculating for 8 pods yields 128 connections and underestimates the rollout peak by 32 connections. Always include surge, canary, and blue-green overlap in your budget.

### 4.3. Scale-down can also create fluctuations

When a pod terminates, its pool must close connections and in-flight requests need time to finish or be cancelled per shutdown policy. If the termination grace period is too short, requests may fail; if old pods have not exited yet while new pods are already up, connection counts can temporarily spike.

Pool sizing and graceful shutdown must be considered together. Monitor connection counts per instance and verify actual rollout behavior.

## 5. Formula for maxSize based on replica count

Once you have the total budget for the service, divide by the maximum number of instances that can coexist simultaneously:

\[
P_{\max}
\leq
\left\lfloor
\frac{B_{service}}{R_{peak}}
\right\rfloor
\]

Where:

- `B_service`: total connection budget of the service.
- `R_peak`: maximum number of replicas/workers that can coexist in the worst-case scenario.
- `P_max`: max size per instance if all instances share the same configuration.

With the example budget of 160 connections and a peak of 10 pods:

\[
P_{\max} \leq \lfloor 160/10 \rfloor = 16
\]

Thus, `maxSize = 16` is the mathematical ceiling under the hypothetical budget. You may choose a lower value to leave headroom or because the database cannot efficiently execute 160 concurrent queries.

### 5.1. Multiple pools on one instance

If each pod has a primary write pool of max 10 and a read replica pool of max 8, the per-pod total is 18. With 10 pods:

\[
10 \times (10 + 8) = 180
\]

Do not size each pool in isolation and forget the sum. Every pool connecting to the same database endpoint must count toward that endpoint's budget. If the read pool connects to a separate database server, maintain a separate budget for that server.

### 5.2. Different pool configurations by workload type

APIs, workers, and reporting jobs do not necessarily need the same `maxSize`. You can partition the budget by role:

- Interactive API: small pool, low target latency, bounded concurrency.
- Worker: pool sized for job throughput and concurrency.
- Report/export: dedicated pool or small quota so long-running workloads do not starve API connections.
- Migration: separate connections, active only during deployment windows and accounted for in the budget.

However, separate pools do not create extra database capacity. The sum of all pools must still fit within server limits and be measured as one system.

## 6. Estimating demand from concurrency and connection hold time

The database budget gives the upper bound. The next step is estimating how many connections the workload actually needs.

One estimation method uses Little's Law:

\[
L = \lambda \times W
\]

Where:

- `L`: average number of operations in the system.
- `λ`: arrival rate of operations, e.g., database operations/second.
- `W`: average duration an operation occupies a resource, in seconds.

If a service generates an average of 120 database operations per second and each operation holds a connection for an average of 80 ms:

\[
L = 120 \times 0.08 = 9.6
\]

The estimated average busy connections is about 10 if each operation holds one connection for that duration without special sharing. Peak concurrency will exceed the average during traffic bursts or when hold times have a long tail.

Do not use this result directly as the final `maxSize`. Use it as a baseline to compare against measured active connections, queueing, and latency.

### 6.1. Connection hold time matters more than HTTP request duration

An HTTP request might last 2 seconds while using the database for only 50 ms. Conversely, a streaming response can keep a result and connection open for several seconds.

Measure:

- Time spent acquiring a connection.
- Time spent executing the statement and consuming results.
- Time a transaction holds a connection.
- Time spent in downstream processing while the connection remains held.

If a transaction wraps an external HTTP call or long CPU work, `W` increases and average busy connections rise accordingly.

### 6.2. Calculating peak concurrency per operation

A service has multiple operation types:

| Operation | Assumed rate | Average hold time | Estimated average busy connections |
|---|---:|---:|---:|
| Lookup customer | 80/s | 20 ms | 1.6 |
| Create order | 25/s | 100 ms | 2.5 |
| Update inventory | 30/s | 60 ms | 1.8 |
| Report page | 5/s | 400 ms | 2.0 |
| Total | 140/s | — | 7.9 |

The total is a Little's Law estimate assuming groups use connections independently for the measured hold times. It does not yet include bursts, tail latency, retries, long transactions, or prefetching. Report pages have a low rate but a long hold time, so they still consume meaningful capacity.

### 6.3. Use percentiles and peaks rather than averages alone

Connection occupancy is heavily influenced by rare but very long operations. Track p50/p95/p99 hold durations alongside active/pending connections during peak hours. A low average can hide a few streams holding connections for minutes.

If traffic is bursty, load-test with realistic traffic profiles and measure peak concurrent acquisitions. Never choose a pool size from a daily average rate alone.

## 7. Pool size does not equal thread count

R2DBC is a non-blocking API, so the number of event-loop threads does not directly dictate how many database connections are needed.

For example:

- One event-loop thread can multiplex many requests.
- A request might not use the database.
- A query can wait on network I/O without occupying a thread while still holding a connection.
- A transaction can hold a connection across multiple reactive operations.
- `flatMap` can launch many concurrent database operations within a single request.

Do not use formulas like "CPU cores × 2" or "Netty worker thread count" to set pool size without measurement. Base sizing on database concurrency, hold time, and database limits.

### 7.1. Reactor concurrency can exceed pool capacity

Example:

```java
return Flux.fromIterable(orderIds)
    .flatMap(orderId -> orderRepository.findById(orderId), 100);
```

This code can spawn up to that many active inner publishers. If the pool only has 16 connections, many operations must wait to acquire one. If multiple requests run this pipeline simultaneously, total demand can far exceed the pool.

Set concurrency according to budget:

```java
return Flux.fromIterable(orderIds)
    .flatMap(orderId -> orderRepository.findById(orderId), 8);
```

The number 8 is just an example. Account for concurrency from other requests and workers; never dedicate the entire pool to a single pipeline.

### 7.2. Concurrency limits do not replace pool limits

Limiting `flatMap` in one service does not cover other repository calls, schedulers, workers, or parallel requests. Pool `maxSize` remains the final guardrail per instance. Bulkheads and concurrency limits help distribute capacity across workloads so one operation cannot monopolize the pool.

## 8. How transactions affect connection demand

In reactive transactions, a connection is typically bound to the transaction context and held until the transaction completes, errors, or is cancelled and cleaned up. If a transaction spans multiple operations or waits on an external service, the connection cannot be leased to other requests during that time.

Example to consider:

```java
@Transactional
public Mono<Order> createOrder(CreateOrder command) {
    return orderRepository.save(toOrder(command))
        .flatMap(order -> inventoryClient.reserve(order)
            .thenReturn(order));
}
```

If `inventoryClient.reserve` is a slow HTTP call and the transaction stays open while waiting, the database connection can be held longer than necessary. Consider shortening the transaction, splitting the workflow, or using an outbox/saga pattern depending on consistency requirements.

### 8.1. Long transactions keep the pool busy even when SQL has finished

A transaction can hold a connection between two statements while the application runs business logic. Therefore, short individual query durations do not guarantee short connection hold times.

Track transaction duration separately when possible. Bound the work performed inside a transaction and avoid waiting on users, networks, or long timers while holding a connection.

### 8.2. Streaming results can hold connections at the consumer's pace

Returning a large `Flux` directly to a slow WebFlux client can keep the result and connection open until the stream completes or is cancelled. If an export endpoint runs long, consider keyset pagination or a background export job to release the connection between pages.

Pool sizing must account for long-running stream workloads, not just short CRUD queries.

## 9. Choosing maxSize below the mathematical budget when needed

Dividing the budget gives the maximum value that stays within server limits. However, the database may achieve optimal throughput at a lower connection count.

Reasons include:

- Each connection incurs session/process or memory overhead.
- Too many concurrent queries contend for CPU and I/O.
- Lock contention rises when many transactions update the same data.
- Database buffers/caches become fragmented across too many concurrent activities.
- Context switching and scheduling overhead increase.
- Having more connections wait on the same lock does not make the transaction finish faster.

Therefore, load-test across multiple pool sizes. Compare throughput, p95/p99 latency, database CPU/I/O, lock waits, pending acquisitions, and error rates. Choose the best balance rather than the largest allowable value.

## 10. Calculating a budget in a complete example

Suppose the system has the following assumptions:

| Parameter | Assumed value |
|---|---:|
| PostgreSQL connection limit | 400 |
| Reserved for admin/monitoring/failover | 60 |
| Other services | 100 |
| External workers/reports/migrations | 40 |
| Remaining budget for API service | 200 |
| Desired API replicas | 10 |
| Maximum rolling surge | 2 |
| Peak replicas during rollout | 12 |

Per-pod budget based on server limit:

\[
P_{max} = \left\lfloor \frac{200}{12} \right\rfloor = 16
\]

If you choose `maxSize = 16`, total pool size during rollout is:

\[
12 \times 16 = 192
\]

The service retains 8 connections of headroom in the hypothetical budget. However, verify whether the database can efficiently handle 192 additional connections. If load testing shows optimal throughput at 10 connections/pod, choosing 10 may be better:

\[
12 \times 10 = 120
\]

That leaves 80 connections in the service budget for traffic spikes, jobs, or another pool. You do not have to consume the entire budget.

### 10.1. When there are two pools

Suppose each pod has:

- Primary write pool: `maxSize = 8`.
- Read replica pool: `maxSize = 6`.

With 12 pods, ceiling demand is:

\[
12 \times (8 + 6) = 168
\]

If the primary and read replica are two separate database servers, allocate 96 connections for the primary and 72 for the replica and check each server's own budget. Do not lump them into one combined budget if they have separate limits; equally, do not omit any pool because each server still has its own limit.

## 11. Autoscaling must align with database capacity

HPA can scale replicas up based on CPU, memory, or custom metrics. Yet every new replica creates a new pool and increases total connections.

If HPA scales from 5 to 20 pods, a pool max of 20 raises the connection ceiling from 100 to 400. If the database only has capacity for 150 connections from that service, autoscaling can turn application overload into database overload.

### 11.1. Setting maxReplicas based on the connection budget

A simple bound:

\[
R_{max} \leq
\left\lfloor
\frac{B_{service}}{P_{per\ instance}}
\right\rfloor
\]

If the service budget is 200 and max pool per instance is 10, the theoretical limit is 20 instances before factoring in surge and other pools. If rollouts require 2 extra surge pods, reduce `maxReplicas` or reduce pool size per instance so peak total remains within budget.

### 11.2. Scaling the application does not scale the database

When requests increase, adding replicas helps handle HTTP, CPU, and non-database I/O. But if every request hits the same database and the database is already saturated, adding pods just adds connection waiters and query contention.

Identify the bottleneck:

- If application CPU is high while the database still has capacity, scaling the app can help.
- If pool pending rises because each pod's pool is too small while the database has capacity, adjusting pool/concurrency can help.
- If database CPU/I/O/locks are saturated, scaling the app usually makes things worse; optimize queries, shed load, or scale the database.

### 11.3. Be cautious with HPA based on pending acquire

If using pending acquisitions as a scaling signal, avoid a feedback loop: pool pending increases → HPA adds pods → each pod opens another pool → the database receives more connections → the database becomes more overloaded. Custom autoscaling must enforce a total connection cap and understand database capacity.

You can scale workers or APIs by queue depth/CPU while keeping total pool budget fixed by lowering pool size per instance as replicas grow, or by enforcing a centralized concurrency limit. Implementation depends on your platform and architecture.

## 12. Configuring the pool in Spring Boot

Spring Boot supports R2DBC pool configuration when the appropriate dependency and version are present. Common properties use the `spring.r2dbc.pool` prefix:

```yaml
spring:
  r2dbc:
    url: r2dbc:postgresql://db.internal:5432/app
    username: ${DB_USERNAME}
    password: ${DB_PASSWORD}
    pool:
      enabled: true
      initial-size: 2
      max-size: 10
      max-acquire-time: 2s
      max-create-connection-time: 3s
      max-idle-time: 10m
      max-life-time: 30m
```

This is an illustrative example, not a default suitable for every environment. Property availability and exact names depend on your Spring Boot version, `r2dbc-pool`, and how `ConnectionFactory` is created. Check the configuration metadata/documentation for your project's exact version.

### 12.1. Meaning of key properties

| Property | Meaning | Notes |
|---|---|---|
| `enabled` | Enable/disable pooling if auto-configuration supports it | Verify dependency and auto-config |
| `initial-size` | Number of connections created initially | Increases startup connection burst if many pods start together |
| `max-size` | Connection limit of one pool within one instance | Must be multiplied by replicas and number of pools |
| `max-acquire-time` | Maximum time to wait for a connection | Choose based on request budget |
| `max-create-connection-time` | Maximum time to create a new connection | Related to network/authentication |
| `max-idle-time` | Time a connection can sit idle before eviction per policy | Coordinate with database/proxy idle timeouts |
| `max-life-time` | Maximum lifetime of a connection before replacement | Can help rotate old connections |

Some versions also support validation timeout/query or background eviction intervals. Never copy properties that do not exist in the version you are running.

### 12.2. Do not blindly set initial-size equal to max-size

If 20 pods start simultaneously and each has `initial-size = 20`, the system can open 400 connections during rollout. That creates a connection storm, spikes authentication load, and drives the database toward its connection limit before workload even demands it.

Choose a small initial size so startup happens gently; the pool expands on demand up to max size. If controlled warm-up is required, coordinate rollout pacing and connection ramp-up.

### 12.3. Acquire timeout does not replace maxSize

`maxSize` caps connection count. `maxAcquireTime` caps how long a caller waits for a free connection. When a pool is saturated, increasing acquire timeout only makes requests wait longer and piles up pending requests; it adds zero capacity.

Choose an acquire timeout smaller than the request's remaining latency budget. If the HTTP deadline is 3 seconds, do not let acquire wait 10 seconds before failing.

## 13. Configuring via R2dbcPoolConfiguration

If creating the pool manually, you can configure it with `ConnectionPoolConfiguration` from `r2dbc-pool`:

```java
ConnectionPoolConfiguration configuration =
    ConnectionPoolConfiguration.builder(connectionFactory)
        .initialSize(2)
        .maxSize(10)
        .maxAcquireTime(Duration.ofSeconds(2))
        .maxCreateConnectionTime(Duration.ofSeconds(3))
        .maxIdleTime(Duration.ofMinutes(10))
        .maxLifeTime(Duration.ofMinutes(30))
        .build();

ConnectionPool pool = new ConnectionPool(configuration);
```

This example uses the R2DBC Pool API; package, builder methods, and defaults must match your version. If Spring Boot already auto-configures a pool, avoid accidentally creating a second pool. Every additional `ConnectionFactory`/pool must be counted in the connection budget and closed properly according to lifecycle.

## 14. Pool size, min/initial size, and idle policy

A pool does not necessarily keep every connection open at all times.

- `initialSize` controls how many connections are created initially.
- `maxSize` caps maximum connections.
- `maxIdleTime` and eviction policies remove connections that stay idle too long.
- `maxLifeTime` rotates aging connections.

Not every pool has a separate `minSize` property. Some configurations use `initialSize` without guaranteeing a minimum open connection count after eviction. Check the actual semantics of your implementation.

### 14.1. maxIdleTime and database/proxy idle timeouts

If the database or proxy closes idle connections after 5 minutes while the pool retains them longer, the pool may hand out a server-closed connection. Align idle policies so the pool detects/evicts connections earlier or handles validation/reconnection properly.

Do not set `maxIdleTime` too short under steady traffic, as the pool will constantly close and reopen connections. Conversely, do not keep idle connections open too long when many pods scale out against a tight database budget.

### 14.2. maxLifeTime and connection rotation

`maxLifeTime` helps replace aging connections, supporting credential rotation, DNS changes, or avoiding long-lived sessions. When many pods share the same lifetime and start at the same time, they may evict connections simultaneously. If the implementation supports jitter or appropriate eviction scheduling, consider using it to avoid synchronized reconnect storms.

Do not set lifetimes shorter than necessary; recreating connections has overhead and can cause spikes when many connections turn over together.

## 15. Connection pools and PgBouncer/proxies

Some architectures place PgBouncer or a database proxy between the application and PostgreSQL. In that case, distinguish between:

- Client connections from the R2DBC pool to the proxy.
- Server connections from the proxy to PostgreSQL.
- The proxy's pooling mode: session, transaction, or statement, depending on product/configuration.

R2DBC `maxSize` caps each application instance's client connections to the proxy. It does not necessarily equal the number of PostgreSQL backend connections held by the proxy.

With PgBouncer transaction pooling, a backend connection may be assigned for the duration of a transaction and returned on commit/rollback. This affects session-level state, prepared statements, temporary tables, and features relying on session persistence. Verify driver and application compatibility with the pooling mode in use.

### 15.1. A proxy does not eliminate client limits

Even when a proxy reduces backend sessions, the proxy still has client connection limits, memory, file descriptors, and queues. Application pools must fit inside the proxy's client connection budget; the proxy's backend pool must fit inside PostgreSQL's budget.

### 15.2. Budget at both layers

```text
Application replicas
  10 pods x 10 R2DBC connections = 100 client connections
                    |
                    v
              PgBouncer
      client limit / queue / pool mode
                    |
                    v
          PostgreSQL backend pool
       backend connections <= DB budget
```

Track client connections and server connections separately. Do not compare `R2DBC maxSize` directly against `max_connections` while ignoring the proxy layer in between.

## 16. Multiple databases and read/write pools

An application may connect to multiple databases or split read/write traffic:

- Primary database for INSERT/UPDATE/transactions.
- Read replica for read queries.
- Dedicated database for audit/reporting.
- Different tenant databases or shards.

Each `ConnectionFactory` can have its own pool. Build a budget table per endpoint/database:

| Database endpoint | Pool per pod | Peak pods | Total max pool | Endpoint budget |
|---|---:|---:|---:|---:|
| Primary | 8 | 12 | 96 | 120 |
| Read replica | 6 | 12 | 72 | 100 |
| Reporting DB | 2 | 4 | 8 | 20 |

Numbers are examples. The table highlights total connections per server and remaining headroom. If a database is shared by multiple services, include all services.

### 16.1. Do not send all read queries to replicas by default

Read replicas have their own capacity, replication lag, and consistency semantics differing from the primary. Enlarging the read pool will not fix slow queries if replica CPU/I/O is already saturated. Budget each replica individually and route workloads deliberately.

### 16.2. Tenant/shard fan-out

If one pod creates pools to multiple shards, total connections on one pod equal the sum of max sizes across all created pools. Lazy pool creation delays opening connections but does not eliminate the aggregate ceiling if every shard is active.

With hundreds of tenant databases, do not create a large fixed pool per tenant without bounding and eviction mechanisms. Consider a bounded pool registry, idle eviction, and an aggregate budget.

## 17. Separating pools for heavy workloads

Some reporting/export queries hold connections much longer than transactional lookups. Sharing a single pool lets long workloads occupy all connections and force critical requests to wait.

Consider:

- A dedicated pool for reporting/read replicas.
- Low concurrency limits for exports.
- Queues for batch jobs.
- Query timeout and page size limits.
- Prioritizing capacity for interactive transactions.

A separate pool only helps when it targets separately managed capacity or enforces clear quotas. If two pools point to the same PostgreSQL server, total connections still add up and can overload the server further.

## 18. How do retries increase connection demand?

Even bounded retries multiply the database operation rate when errors occur. If 100 requests each retry three times, the database can receive far more attempts than original requests.

Track:

- Attempt count by operation/error category.
- Backoff duration.
- Retry success ratio.
- Number of operations waiting in backoff.
- Connection acquire rate and query rate during retries.

Use exponential backoff and jitter for transient errors. Do not retry validation/constraint errors or non-transient failures. For writes, ensure idempotency so retries do not create duplicate side effects.

Pool sizing should not assume retries never happen. At the same time, do not enlarge the pool to absorb a retry storm; cap retries and protect the database.

## 19. Pool size and database workload capacity

`max_connections` is only a session limit, not optimal concurrent processing throughput. A database often reaches peak throughput at a connection count well below its configured limit.

Load tests should vary pool size across several levels and measure:

- Throughput (operations/second).
- p50/p95/p99 latency.
- Active/pending connections and acquire duration.
- Database CPU, memory, I/O, and storage latency.
- Lock waits, deadlocks, and transaction duration.
- Error rates, timeouts, and retry rates.
- Connection creation/close rates.

If increasing the pool from 10 to 20 does not improve throughput while p99 latency and database CPU climb, a larger pool is counterproductive. You likely need query/index optimization or lower concurrency.

### 19.1. Load-test realistic scenarios

Include:

- Normal and peak traffic.
- Short bursts and sustained load.
- Realistic read/write ratios.
- Short and long transactions.
- Multi-row/streaming queries.
- Concurrent workers and reporting jobs.
- Rolling deployments/autoscaling.
- Simulated transient errors triggering retries.

Benchmarking a single simple SELECT rarely reflects real workload connection hold time and contention.

## 20. Monitoring metrics to tune the pool

Metrics to monitor:

| Metric | What to inspect on abnormal increases |
|---|---|
| Acquired/active | Connection hold time, concurrency, long transactions |
| Idle | Whether the pool is provisioning too many connections relative to demand |
| Pending acquire | Pool saturation, slow queries, bursts, `maxSize` too small |
| Acquire latency | Queueing and timeout budget |
| Acquire timeout | Users/jobs failing to obtain connections |
| Connection creation rate | Pool churn, `maxIdleTime`/`maxLifeTime`, startup storms |
| Connection creation failure | Network, credentials, DB capacity, proxy |
| Hold duration | Result streams, transactions, slow cleanup |

Exact meter names depend on R2DBC Pool/Micrometer/Spring Boot versions. Verify which metrics are actually exported before building dashboards or alerts.

### 20.1. Combining pool metrics with query and HTTP metrics

Diagnostic examples:

| Observation | Likely area to investigate |
|---|---|
| High active, high pending, high query duration | Slow queries or database contention |
| High active, low query execution, high HTTP stream duration | Slow downstream or slow result consumption |
| Pending spikes right when scaling pods | Total connection demand/rollout surge exceeding capacity |
| Acquire timeouts rising, DB connections at limit | System-wide budget or oversized pools |
| High idle, persistently high creation rate | Pool churn, lifetime/idle policy, or traffic bursts |
| Low active pool, yet acquire timeouts occur | Connection creation/network/validation issue or misconfigured metrics |

Never draw conclusions from a single metric. Correlate across time, instances, pools, and operations.

## 21. Alerting on pool capacity

Alert signals can include:

- Acquired staying near max for a sustained window.
- Pending acquire staying greater than 0.
- Acquire latency p95/p99 exceeding budget.
- Increasing acquire timeouts.
- Total database connections approaching server limits.
- Rising connection creation failures.

Illustrative rule:

```text
IF acquired_connections / max_connections > 0.90
AND pending_acquire > 0
FOR 5 minutes
THEN alert = R2DBC_POOL_SATURATED
```

Thresholds like 90% and 5 minutes are not universal defaults. Tune them based on baseline behavior, SLAs, burst patterns, and impact. High utilization alone may simply mean the pool is being used efficiently; pending counts, acquire latency, and timeouts indicate saturation much more clearly.

### 21.1. Alert on total database connections

Monitor total sessions across all applications and services, not just one pool's metrics. When database connection usage approaches the server limit, alerts should identify the database endpoint and connection sources whenever possible.

Do not use dynamic usernames or application instance IDs as high-cardinality metric labels. Use service name, logical pool, and environment.

## 22. Startup storms and warm-up during scale-out

When many pods start at the same time, each pod may create `initialSize` connections and rapidly grow under traffic. Rolling out 20 pods with an initial size of 10 can create 200 connections almost simultaneously.

Mitigations:

- Set `initialSize` lower than max size if workload permits.
- Limit rollout surge and rollout speed.
- Use proper startup/readiness logic so traffic is not accepted before the pool is ready.
- Avoid having all pods reconnect at once without backoff after a database outage.
- Monitor connection creation rates and authentication load.
- Consider jitter/eviction scheduling if supported by the pool.

Do not warm up by pre-opening `maxSize` connections on every pod unless accounted for in the budget. Warm-up must be a controlled operation.

## 23. Graceful shutdown and connection lifecycle during scale-down

When pods stop, pools must close connections and in-flight publishers must complete or cancel per shutdown policy. Configure termination grace periods and server shutdown timeouts to accommodate maximum request duration.

Checks to verify:

- Does the pod stop accepting new requests before shutting down?
- Do in-flight requests have enough time to finish per SLA?
- Do workers stop picking up new jobs and checkpoint their work?
- Are transactions committed/rolled back properly on cancellation/shutdown?
- Is the pool disposed and are connections closed properly according to lifecycle?
- Do new pods spin up too early, causing total connections to exceed budget?

Do not rely on process termination alone for the database to clean up immediately. Sessions may linger until the server detects a closed socket or hits a timeout.

## 24. Common pitfalls

| Pitfall | Consequence | Fix |
|---|---|---|
| Choosing maxSize for a single pod | Total pools exceed DB limit when scaling | Multiply by peak replicas and all pools |
| Using normal replicas instead of maxReplicas | Autoscaling exhausts connections | Calculate from HPA max, surge, and workers |
| Ignoring rolling deployment surge | Connections spike temporarily during rollouts | Account for peak overlap of old/new pods |
| Summing service budgets without reserving admin/other clients | DBAs/migrations run out of connections | Reserve headroom and include all clients |
| Sizing pools by thread/CPU count | Does not reflect actual DB concurrency | Measure operation rate and connection hold time |
| Increasing pool when DB is already saturated | Increases contention and session overhead | Load-test, optimize queries, and cap concurrency |
| Counting only one pool in the app | Read/report/tenant pools are missed | Sum `maxSize` across every `ConnectionFactory` |
| Setting initialSize equal to maxSize across many pods | Startup connection storm | Initialize small and ramp up controllably |
| Acquire timeout too long | Many waiting requests and cascading latency | Set per request deadline and handle overload |
| Acquire timeout too short | Fails fast even on short resolvable bursts | Tune to SLA and wait-time distribution |
| Long transactions or slow streams | Connections are held too long | Shorten transactions, paginate, use export jobs |
| Excessive flatMap concurrency | Connection demand exceeds pool | Limit concurrency/use bulkheads |
| Unbounded retries | Retry storms and pool saturation | Use backoff, jitter, filters, and deadlines |
| Monitoring utilization alone | Misses queueing or causes false positives | Combine pending, acquire latency, and timeouts |
| Using PgBouncer while counting only backend connections | Proxy client limit gets exceeded | Budget both client and server pools |
| Not closing pools on shutdown/tests | Connections/resources leak unexpectedly | Dispose pools properly in lifecycle |

## 25. Process for calculating and configuring a pool

When deploying a new service or changing replica counts, follow this sequence:

1. **Identify database limits:** obtain server/proxy limits and true capacity via load testing.
2. **Inventory all clients:** APIs, workers, scheduled jobs, reports, migrations, and other services.
3. **Reserve headroom:** admin, monitoring, failover, maintenance, and unexpected workloads.
4. **Compute the service budget:** remaining connections allocated to the service.
5. **Compute peak replicas:** HPA max, rolling surge, canary, blue-green, and worker overlap.
6. **Sum all pools:** primary/read/report/tenant/shard pools per instance.
7. **Compute per-pool ceilings:** divide the budget by peak instances and allocate by role.
8. **Estimate workload demand:** operation rates, concurrency, connection hold times, transactions, and streaming.
9. **Load-test multiple configurations:** measure throughput, p95/p99, DB CPU/I/O, locks, and pending acquisitions.
10. **Set complementary bounds:** `maxAcquireTime`, create timeout, idle/lifetime, page size, and Reactor concurrency.
11. **Test scaling/rollouts:** verify total connections stay within budget as pods scale or replace.
12. **Monitor and adjust:** review metrics whenever traffic or replica counts change.

## 26. Illustrative sizing checklist

A capacity spreadsheet should include at least these fields:

| Field | Value to fill in |
|---|---|
| Database endpoint | Logical database/proxy name |
| Server connection limit | Limit from DB/proxy |
| Reserved headroom | Admin, failover, monitoring, migrations |
| Other client budget | Other services |
| Service budget | Remaining allocation for this service |
| Deployment desired replicas | Normal replicas |
| HPA max replicas | Maximum replicas under autoscaling |
| Rollout surge/canary | Additional overlapping instances |
| Worker/job replicas | Instances outside web deployment |
| Number of pools per instance | Pools targeting this endpoint |
| Max size per pool | Planned configuration |
| Total peak connections | Total across all instances/pools |
| Measured hold time | p50/p95/p99 if available |
| Peak DB operation concurrency | Measured during load tests |
| Acquire timeout/latency | Baseline and target |
| Database CPU/I/O/locks | Actual capacity |

Total peak connections must be less than the service budget after accounting for all pools and instances. In addition, pool size must be validated against database performance; staying under the connection limit math does not guarantee the workload runs well.

## 27. Key takeaways

- `maxSize` caps a single pool in a single instance; total connections grow with replicas and pools.
- Start budgeting from the database connection limit, reserving headroom for administration, failover, monitoring, and other clients.
- Use maximum replica counts, HPA max, rolling surge, canary, blue-green, and worker overlap.
- For a uniform pool, `maxSize per instance <= service budget / peak instance count`.
- Sum all primary/read/report/tenant/shard pools per target database endpoint.
- Do not choose pool sizes based on thread count, CPU count, or HTTP request concurrency.
- Estimate demand from operation rate and connection hold time; use `L = λ × W` as a baseline, then validate with load tests.
- Monitor p95/p99 hold duration, transaction duration, pending acquisitions, and acquire latency.
- Long transactions, slow result streams, high `flatMap` concurrency, and retry storms all increase connection occupancy.
- Larger pools do not always yield higher throughput; too many sessions can increase database contention.
- Set `initialSize` conservatively to prevent startup/rollout connection storms.
- `maxAcquireTime` caps wait time rather than adding capacity; choose it based on request deadlines.
- Align idle/lifetime policies with database/proxy timeouts and connection rotation.
- When using PgBouncer/proxies, budget client connections and backend connections separately.
- Cap concurrency, page sizes, and export workloads so one request group cannot exhaust the pool.
- Monitor metrics on both the application pool and the database server; pair utilization with saturation and errors.
- Test scale-out, rolling deployments, shutdowns, and realistic load before raising max replicas or pool sizes.

Sizing pool limits correctly is a system-wide capacity problem. Start from the connection budget the database can dedicate to the service, divide by the maximum number of coexisting instances and total pools, and compare against measured concurrency and connection hold time. Final settings should be validated via load testing while tracking pending acquisitions, latency, database CPU/I/O, and connection usage. When pool size, autoscaling, rollout surge, and concurrency are designed under a shared budget, R2DBC applications can scale without inadvertently multiplying connections beyond database capacity.
