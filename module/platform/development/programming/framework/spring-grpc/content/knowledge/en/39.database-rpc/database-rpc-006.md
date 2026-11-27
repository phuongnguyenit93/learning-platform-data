# Connection Pools Under RPC Load

## 1. The role of connection pools in Spring gRPC

In **SPRING_GRPC**, a server can receive hundreds or thousands of concurrent RPCs, while a database can only serve a finite number of connections. Opening a connection for every active RPC does not make the database faster; it can exhaust connection limits, increase context switching, worsen lock contention, and cause latency to spike sharply.

Spring Boot typically uses HikariCP to reuse JDBC connections. When a transaction needs the database, the application borrows a connection from the pool; when the transaction finishes, the connection is returned to the pool. The pool is a bounded resource queue between RPC concurrency and database capacity.

Design needs to balance three factors:

- **RPC concurrency:** the number of requests executing simultaneously.
- **Pool capacity:** the number of connections one instance is allowed to hold.
- **Database capacity:** the number of queries/transactions the database can process efficiently at once.

Increasing pool size only helps when the database still has spare capacity and connections are genuinely the bottleneck. If the database is already saturated on CPU, I/O, or locks, enlarging the pool usually makes queuing and contention worse.

## 2. Does an RPC hold a connection for its entire processing time?

An RPC does not necessarily hold a connection from the moment gRPC receives the request until the response is sent. With JDBC/JPA, a connection is typically acquired when the transaction begins database work and returned when the transaction ends, depending on the transaction manager and connection handling configuration.

Unary command example:

1. The gRPC adapter receives the request and validates its structure.
2. The adapter calls the application service.
3. Spring opens a transaction; the transaction manager acquires a connection when needed.
4. Repositories read/write data.
5. The transaction commits or rolls back.
6. The connection is returned to the pool.
7. The adapter emits the response.

If a transaction opens too early and then calls a remote service, waits long on locks, or performs heavy computation before commit, the connection may be held even when no SQL is executing. For streaming RPCs, holding a transaction across message waits or backpressure is even more dangerous.

**Keep transactions and connections tight around the database work; never hold them while waiting on the network or callbacks.**

## 3. Relationship between RPC concurrency and pool size

Suppose a server has 300 active RPCs, but each RPC only uses the database for 20 ms. That does not mean you need 300 JDBC connections. RPCs can take turns borrowing from a small set of connections over short intervals.

An initial estimate uses Little's Law:

```text
Average connections needed ≈ database work throughput × average connection hold time
```

For example, a system handles 500 RPCs/second, each using a connection for a total of 30 ms:

```text
500 × 0.030 = 15 average connections
```

This is only an average. Real sizing needs headroom for bursts, p95/p99 transaction durations, multi-query RPCs, and background tasks. Do not take concurrent RPC count directly as the pool size.

If each RPC opens multiple sequential transactions, connection hold times add up; if multiple transactions run in parallel within the same request, demand can be higher. Measure actual connection borrow times rather than inferring them solely from RPC latency.

## 4. Calculating the system-wide connection budget

HikariCP maximumPoolSize applies per pool in each process. When running multiple replicas, total connections can far exceed the number configured on a single instance.

| Component | Instances | Max Pool per Instance | Total Max |
| --- | ---: | ---: | ---: |
| gRPC service A | 4 | 20 | 80 |
| gRPC service B | 3 | 10 | 30 |
| Background worker | 2 | 8 | 16 |
| Application total |  |  | 126 |

If the database allows 160 connections, you cannot allocate all 160 to this application. You must reserve capacity for migrations, monitoring, DBAs, consoles, backup tooling, failovers, and other services.

The budget must be calculated at maximum scale:

```text
Maximum total connections
= Σ (maximum replicas × pool maximum of each instance)
```

If autoscaling adds replicas while each replica keeps the old pool maximum, total connections can suddenly exceed the DB limit. Autoscaling, replica ceilings, and pool maximums must be coordinated.

## 5. Configuring HikariCP in Spring Boot

Spring Boot supports configuring HikariCP via datasource properties. Example:

```yaml
spring:
  datasource:
    url: jdbc:postgresql://db.internal:5432/orders
    username: orders_app
    password: injected-secret
    hikari:
      pool-name: orders-db-pool
      maximum-pool-size: 20
      minimum-idle: 5
      connection-timeout: 1500
      validation-timeout: 1000
      idle-timeout: 600000
      max-lifetime: 1800000
      leak-detection-threshold: 0
```

The username/password values are illustrative only; production should inject credentials from a secret/configuration provider and never commit secrets to the repository.

| Property | Meaning | Considerations |
| --- | --- | --- |
| maximum-pool-size | Maximum connections in the pool | Bounded by DB budget and measured throughput |
| minimum-idle | Target idle connections | Balance readiness against continuously held connections |
| connection-timeout | Wait time to borrow a connection | Must fit within the RPC deadline budget |
| validation-timeout | Time to validate a connection | Smaller than connection-timeout |
| idle-timeout | Time before an idle connection may be retired | Meaningful when minimum-idle is less than maximum-pool-size |
| max-lifetime | Maximum age of a connection before replacement | Lower than infrastructure lifetime limits |
| leak-detection-threshold | Threshold for logging suspected long-held connections | For diagnostics; does not fix leaks automatically |

Do not copy example numbers directly into production. Measure the database, workload, and infrastructure limits before choosing values.

## 6. Choosing maximumPoolSize without overloading the database

Pool size must be large enough for independent transactions to make progress, but not so large that the database must execute too many queries simultaneously.

Sizing process:

1. Determine DB max connections and subtract allocations for administration, monitoring, migrations, and other services.
2. Determine the maximum replica count for each application.
3. Divide the connection budget across pools by priority and actual load.
4. Start with a moderate pool size.
5. Measure pool pending/acquisition wait, transaction duration, and database CPU/I/O/lock waits.
6. Adjust the pool based on load test results.
7. Repeat at maximum replica count and under failover/autoscaling scenarios.

A constantly full pool does not automatically mean the pool must be enlarged. If active connections are all running slow queries, the bottleneck may be query plans, indexes, locks, or database capacity. Enlarging the pool only pushes more queries onto an already busy database.

## 7. Connection acquisition timeout and deadline budgets

When the pool runs out of connections, threads needing the database wait for a connection to be returned. If the wait exceeds connectionTimeout, HikariCP throws a connection acquisition timeout error.

RPCs also have deadlines. The two budgets must align:

```text
RPC deadline
  ├─ validation / application work
  ├─ wait for pool connection
  ├─ database query + commit
  └─ response serialization / network
```

If an RPC only has 200 ms remaining while connectionTimeout is 2 seconds, the request may continue waiting for resources after the client has already timed out. Choose connection timeouts, query timeouts, and transaction timeouts consistent with the remaining deadline.

Not every JDBC driver automatically cancels a query as soon as the gRPC client cancels. Configure statement/query timeouts and cancellation behavior according to the driver/database; do not assume a gRPC deadline automatically translates into a JDBC timeout.

When a pool acquisition timeout occurs, classify the error according to service policy. UNAVAILABLE may fit recoverable transient overload; RESOURCE_EXHAUSTED fits if the contract expresses resource/quota exhaustion. Do not return ABORTED unless it is genuinely a transaction conflict. Client retries need backoff/jitter and an overall deadline; aggressive retries can worsen pool overload.

## 8. Connection leaks and transactions holding connections too long

A connection leak occurs when code borrows a connection and never returns it, usually due to improper resource management or hung transactions. With Spring/JPA, connections are typically managed by the transaction manager; however, overly long transactions can still make a pool appear leaked.

Common causes:

- A transaction wrapping HTTP/gRPC calls to another service.
- A transaction held open while waiting for the next stream message.
- Async callbacks misusing transaction/thread lifecycles.
- Manual JDBC code failing to close Statement/ResultSet/Connection properly.
- Queries blocked by locks or running too long.
- Exception paths skipping resource cleanup in manually managed code.

Use try-with-resources for manual JDBC. With Spring transactions, keep application services short and avoid network calls inside transactions. Leak detection only logs stack traces for connections held past the threshold; it does not safely close connections on behalf of the application.

## 9. Pool exhaustion vs. database saturation

| Symptom | Possible Cause | Investigation Direction |
| --- | --- | --- |
| Pool active at max, pending rising, DB CPU low | Queries waiting on locks, transactions holding connections too long, pool too small | Check lock waits, transaction duration, pool sizing |
| Pool active at max, DB CPU/I/O high | Database is saturated | Query plans, indexes, reduce concurrency, optimize workload |
| Pool active low but RPC slow | Slowness in network, application, or another dependency | Trace individual spans; do not increase pool size blindly |
| Connection timeouts after scale-out deploy | Sum of pools across replicas exceeds DB budget | Recalculate replicas × pool maximum |
| Continuous leak detection warnings | Long-held connections or genuine leak | Inspect stack traces, transaction boundaries, cleanup |

Correlate application metrics with database metrics. Looking at Hikari active counts alone is not enough to identify the root cause.

## 10. Splitting pools by workload when necessary

Some applications have very different workloads:

- Interactive RPCs requiring low latency.
- Batch imports running long queries and touching many rows.
- Reporting/exports reading large volumes of data.
- Background outbox workers.

If everything shares one pool, batch/reporting jobs can occupy connections and force interactive RPCs to wait. You can consider separate datasources/pools for distinct workloads, though each pool consumes part of the connection budget and increases transaction complexity.

Splitting pools only helps when there is a clear isolation goal. Verify transaction managers, routing datasources, consistency, and the total maximum connections across all pools. Do not create a separate pool per RPC method arbitrarily.

## 11. Metrics to monitor

HikariCP can export metrics through Micrometer/Spring Boot Actuator when properly configured and instrumented.

| Metric | Meaning |
| --- | --- |
| active connections | Connections currently borrowed |
| idle connections | Connections ready in the pool |
| pending threads | Threads waiting for a connection |
| max connections | Pool limit |
| connection acquisition time | Time spent waiting to acquire a connection |
| connection usage time | Time a connection is held |
| timeout count | Number of times a connection could not be acquired in time |
| transaction duration | Time a transaction stays open |
| query duration | Time spent executing database queries |

Combine these with gRPC metrics such as RPC rate, p95/p99 latency, status codes, concurrent calls, and cancellations. Also combine with database metrics such as CPU, I/O, active sessions, lock waits, deadlocks, slow queries, and replication lag.

Base alerts on trends and impact, such as sustained pending threads accompanied by rising acquisition latency and increasing RPC UNAVAILABLE responses. A brief spike at active=max during peak traffic is not enough to conclude the pool is misconfigured.

## 12. Methodical load testing and tuning

Load tests should simulate realistic RPC distributions rather than just calling a single simple method:

1. Create a workload with query/command/streaming ratios matching production.
2. Simulate realistic payload sizes and transaction durations.
3. Step up concurrency incrementally, holding each level long enough to stabilize.
4. Record throughput, RPC latency p50/p95/p99, and status distribution.
5. Record Hikari active/idle/pending, acquisition/usage times, and timeout counts.
6. Record database CPU/I/O, lock waits, slow queries, and connection counts.
7. Repeat at maximum replica count and when a replica/database node fails.
8. Change one variable at a time to understand its impact.

Find the point where throughput stops increasing while latency, pending threads, or DB contention rises rapidly. That usually indicates you have crossed the effective load region. The goal is not the largest possible pool, but achieving the required throughput with stable latency and error rates.

## 13. Operations checklist

- Pool maximum is calculated against the system-wide DB connection budget.
- Accounts for maximum replicas, autoscaling, and other pools/workers.
- Transactions are short, never holding connections across network calls or stream waits.
- Query/statement/transaction timeouts align with RPC deadlines.
- Pool acquisition timeout does not exceed a reasonable RPC wait budget.
- Hikari active/idle/pending/acquisition/usage/timeout metrics are collected.
- Database CPU, I/O, lock waits, and slow queries are observed in parallel.
- Leak detection is used only for diagnostics; not treated as an auto-remediation mechanism.
- Batch/reporting workloads do not starve interactive RPC pools.
- Load tests cover realistic concurrency, payloads, and transaction durations.
- Retries on pool exhaustion use backoff/jitter, attempt limits, and an overall deadline.
- Runbooks exist to distinguish pool exhaustion from database saturation.

In **SPRING_GRPC**, the connection pool is a shared resource boundary across RPCs needing the database. Size it according to database capacity and total replica count, keep transactions short, align timeouts with deadlines, and use pool metrics alongside database metrics to pinpoint bottlenecks. When the pool fills up, determine whether connections are being held too long, queries are slow, or the database is saturated before deciding to increase the pool.
