# Limiting by Database Connections or Target Service Capacity

## 1. Why Limit Concurrent Work by Target Resource Capacity?

In a Spring application, increasing request threads, using `@Async`, expanding `ThreadPoolTaskExecutor`, or enabling virtual threads allows more tasks to make progress at the same time. Yet each task may still require **JDBC connections**, **HTTP connections**, **partner API throughput**, **long transactions**, memory, or CPU. An executor's capacity to accept tasks does not equal the serving capacity of the underlying resource.

For example: a Spring instance has 40 workers processing reports, while the datasource allows only 10 JDBC connections. When all 40 workers query the database simultaneously, at most 10 connections from that pool can be granted concurrently; the remaining workers may block while waiting to borrow a connection, and then time out. Raising workers to 80 does not create extra connections. If the database is already saturated, raising the pool to 80 can even make things worse as the DB handles more concurrent transactions.

This lesson explains how to **establish a resource budget**, **bound concurrent operations at the call site**, **configure connection pools and executors**, **handle saturation**, **observe the system**, and **verify under load**. The focus is the relationship between Spring concurrency and the connection/intake capacity of the database or target service.

### Four Distinct Limits

| Limit | What Does It Count? | Example | What It Does Not Guarantee |
| --- | --- | --- | --- |
| Executor concurrency | Running tasks on one executor | 8 `@Async` workers | At most 8 SQL queries across the whole app |
| JDBC connection pool | Physical connections managed by the pool, idle and active | HikariCP `maximumPoolSize=12` | Enough DB CPU or that every transaction is fast |
| HTTP connection pool | Network connections managed by the client, usually per remote host | Reactor Netty `maxConnections=16` | Exactly 16 in-flight requests, especially with HTTP/2 |
| Target bulkhead/admission limit | Concurrent business calls allowed to one dependency | 6 concurrent operations calling payment service | Rate limit of 60 requests/second or cluster-wide quota |

**Connections**, **threads**, **tasks**, **HTTP requests**, **transactions**, and **requests/second** are different units. To protect a target service, you must pick the limit matching the exact unit under which that service actually overloads.

## 2. Understanding the Bottleneck Path: From Executor to Database and External APIs

A synchronous processing path typically looks like this:

```text
HTTP request / scheduled job / message
           |
           v
    Spring controller/service
           |
           v
        executor              <-- can have its own workers/queue
           |
      +----+------+
      |           |
      v           v
 HikariCP      HTTP client    <-- two different types of connection pools
      |           |
      v           v
 Database      Remote API     <-- target servers also have their own limits
```

Suppose the processing flow runs as follows:

1. A request enters Spring; a task is accepted into an executor, occupying one worker.
2. The task calls `JdbcTemplate`/JPA; the connection pool lends a connection if one is available.
3. When the pool has no free connections, the task may **wait at the connection acquisition step**. Meanwhile, the worker stays occupied under a blocking model.
4. If the wait times out, HikariCP throws a connection acquisition error; if acquired, SQL still has to wait for locks, CPU, I/O, or DB resources.
5. The task returns the connection to the pool when its usage scope/transaction ends, and may then call another HTTP service, again subject to connection pool rules, timeouts, and server-side quotas.

**Why does latency spike abruptly under overload?** When work arrives faster than completion capacity, callers start waiting in multiple queues: executor queue, JDBC connection acquisition, DB locks, HTTP pool pending acquisitions, or downstream queues. Every layer can extend total response time.

**Why doesn't adding threads solve it?** A thread waiting for a connection does not help the DB process more work; it still consumes memory, occupies a slot in the executor pool, and can lengthen other requests' wait past timeouts. Active request counts rise without a matching rise in throughput.

## 3. Limiting by DB Connections: HikariCP in Spring Boot

### 3.1. `maximumPoolSize` and `connectionTimeout`

For a datasource using **HikariCP**, two fundamental settings are:

- **`maximumPoolSize`:** the maximum number of connections managed by the pool, counting both borrowed and idle connections. This is a **per-pool, per-instance** limit, not a limit across the entire DB cluster.
- **`connectionTimeout`:** the maximum time a caller waits to borrow a connection from the pool when none is ready. On expiration, HikariCP throws an error; it is **not** a timeout for SQL execution after a connection has been borrowed.

Example configuration in **`application.yml`** of a Spring Boot 3.x application using HikariCP:

```yaml
spring:
  datasource:
    hikari:
      pool-name: application-db
      maximum-pool-size: 12
      connection-timeout: 2000
```

This is an **integration snippet**: datasource URL/credentials and JDBC driver must be configured appropriately. `connection-timeout: 2000` is in **milliseconds** (2 seconds). When all 12 connections are in use and none is idle, a new acquisition request waits up to that deadline, then fails if no connection becomes available.

Spring Boot usually selects HikariCP when HikariCP is on the classpath; common JDBC/JPA starters typically pull in HikariCP. If an application intentionally uses another datasource or connection pool, `spring.datasource.hikari.*` properties **do not necessarily apply**. Verify the actual `DataSource` bean and configured pools, especially in multi-datasource apps.

Do not confuse:

- `maximumPoolSize=12` does not mean "12 SQL queries per second."
- One connection can execute many SQL statements **sequentially** within a transaction.
- One request may borrow a connection multiple times or hold multiple connections depending on design/transactions.
- A borrowed connection waiting on a DB lock still occupies one slot in the pool.
- Increasing `maximumPoolSize` does not automatically increase database CPU/IOPS capacity.

### 3.2. Why Do Long Transactions Bottleneck the Pool?

In standard JDBC processing, an active transaction can hold a connection until commit or rollback. If code opens a transaction and then makes an external HTTP call with 3-second latency, the connection may stay held even though the DB does no work during that interval. Rising load will rapidly exhaust the pool.

Example of a **pattern to reconsider**:

```java
@Transactional
public void updateAndNotify(Order order) {
    repository.save(order);
    remoteClient.sendNotification(order.getId()); // May wait a long time on network.
}
```

This is an illustrative snippet, not a standalone class. It also carries consistency risks: the DB might roll back while the remote notification was already sent, or the remote call fails after external side effects occurred. A sounder design usually shrinks the transaction scope, moves non-DB work after commit, or uses a **transactional outbox** when reliable event publishing is needed. Do not arbitrarily split transactions if business logic requires DB atomicity; analyze consistency requirements first.

Signs to inspect: transaction duration, active connections, pending connection requests, slow queries, lock waits, N+1 queries, connection leaks, and timeouts during high DB load.

### 3.3. Connection Leaks and Closing Resources Properly

With raw JDBC, always return connections, statements, and result sets via proper lifecycle management, typically `try-with-resources`:

```java
try (Connection connection = dataSource.getConnection();
     PreparedStatement statement =
             connection.prepareStatement("SELECT COUNT(*) FROM orders");
     ResultSet rows = statement.executeQuery()) {
    if (rows.next()) {
        return rows.getLong(1);
    }
    return 0L;
}
```

This is a method-body snippet assuming `dataSource` is injected; class/signature/exceptions must be added during integration. Do not manually close a connection inside a Spring-managed transaction in a way that breaks transaction lifecycle. With `JdbcTemplate`, JPA, and Spring transaction management, prefer letting the framework manage connections along proper boundaries.

**An exhausted pool** can result from legitimate load, transactions holding connections too long, leaks, deadlocks, or a slow backend. Never assume "small pool" automatically means you must increase its size.

## 4. Connection Budgeting by Instance Count and Workload

### 4.1. Global DB Limit and Per-Pod Limit

Suppose the database allows at most **100 connections**, and we reserve **20** for operations/admin sessions/maintenance and **20** for other systems. That leaves a budget of **60 connections** for the Spring service. If the service runs **4 instances** with one datasource per instance, a preliminary cap is:

```text
Service budget = 100 - 20 - 20 = 60 connections
Preliminary cap per instance = floor(60 / 4) = 15 connections
```

The number 15 is a **connection budget ceiling**, not a recommendation to set the pool to exactly 15. The database may hit CPU, I/O, or lock contention limits at much lower active connection counts. Load test and monitor throughput, p95/p99 latency, query waits, and DB saturation to pick a suitable value.

If autoscaling expands from 4 to 8 instances while keeping `maximumPoolSize=15`, this group alone can hold up to **120 connections** (idle plus active depending on pool lifecycle), exceeding the budget of 60. Calculate limits using **maximum instance count**, not just currently running pods at configuration time.

General calculation for similar pools:

```text
Total connection cap from the application
  = instance count × pools per instance × maximumPoolSize of each pool
  (if all pools are the same size; otherwise sum each pool's cap)

Available budget
  = DB limit - share for other systems - operational reserve
```

Include read/write datasources, batch workers, migrations, admin clients, background jobs, and other apps sharing the database. The fact that an app is not using all connections at a quiet moment is **no** excuse to ignore combined surges at peak.

### 4.2. Do Not Mechanically Equate Task Count with Connection Count

If each task always borrows at most **one** connection and no other threads access the database, an executor capped at 6 tasks can help control demand. In real systems, direct HTTP threads, schedulers, listeners, and other executors also share the pool; they are not bounded by that single executor pool.

Furthermore, a single task might run two queries concurrently across two different transactions, or hold a connection inside a transaction while waiting on something else. Hence a generic rule like `maxThreads = maximumPoolSize` cannot be applied universally.

**Principle:** treat the connection pool as the last physical barrier, and put concurrency limits/bulkheads **right where load originates** as the front-line control. Reserve capacity for critical paths; do not let batch/background work exhaust the pool and starve interactive requests of connections.

## 5. Bounding Spring Background Work to Reserve DB Capacity for Primary Requests

Suppose the JDBC pool has at most 12 connections. We allow the background report-export group to use **at most 4 concurrent workers**, leaving interactive requests a chance to acquire connections. This bounds **one task group**, rather than hard-guaranteeing exactly 8 free connections at all times since other threads can still occupy the pool.

**Spring Framework/Spring Boot configuration in an async-enabled app:**

```java
import java.util.concurrent.ThreadPoolExecutor;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration(proxyBeanMethods = false)
@EnableAsync
public class AsyncResourceConfiguration {
    @Bean("reportDbExecutor")
    public ThreadPoolTaskExecutor reportDbExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(16);
        executor.setThreadNamePrefix("report-db-");
        executor.setRejectedExecutionHandler(
                new ThreadPoolExecutor.AbortPolicy());
        return executor; // Spring manages initialize/shutdown per lifecycle.
    }
}
```

**Usage in a Spring-managed service:**

```java
import java.util.concurrent.CompletableFuture;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class ReportCountService {
    private final JdbcTemplate jdbc;

    public ReportCountService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Async("reportDbExecutor")
    public CompletableFuture<Long> countOrders() {
        Long count = jdbc.queryForObject(
                "SELECT COUNT(*) FROM orders", Long.class);
        return CompletableFuture.completedFuture(count);
    }
}
```

These are two classes integrated into **a Spring Boot/Spring Framework project that already has a datasource, `orders` table, and JDBC dependencies**, not a standalone `javac` program. With this executor, at most four tasks are **running in the report group** at once; up to 16 more tasks can wait in the queue. When both workers and queue are full, `AbortPolicy` rejects submissions. Handle rejection errors at the call boundary, e.g., returning an overload response or persisting the job to an appropriate job store.

**Important boundaries:**

- `@Async("reportDbExecutor")` uses this executor only when the method is invoked **through the Spring proxy**. Internal `this.countOrders()` calls inside the same bean typically bypass the proxy.
- Four running tasks do not mean exactly four connections are borrowed at every instant: tasks may be computing, waiting for a connection, or not touching the DB.
- Regular API requests using the DB directly do not automatically pass through `reportDbExecutor`.
- Business data needing a transaction must open the transaction on the **actual working thread**. Calling `@Async` does not automatically carry the caller's imperative transaction to another worker.
- `queueCapacity=16` is the number of waiting slots in the executor; it does **not** add connections. Large queues lengthen wait times; measure queue delay before setting bounds.
- To prioritize interactive requests under congestion, limiting background workers alone may not suffice: you still need to evaluate total DB capacity, query cost, and admission control on other paths.

### When Using `SimpleAsyncTaskExecutor` or Virtual Threads

`SimpleAsyncTaskExecutor` does not reuse threads, and `setConcurrencyLimit(n)` caps the number of tasks executing through it; by default callers can block when slots run out. With Java 21+ and Spring virtual thread support, creating many virtual threads is cheaper than platform threads, yet **does not** increase the number of connections HikariCP or a downstream can provide. Dependency-level concurrency limits remain essential.

## 6. Limiting Target Services: Connection Pools Are Not Enough

For external HTTP services, at least three things must be managed:

1. **Network connections** the client can open to the target.
2. **Concurrent in-flight requests/operations** being processed at the target service.
3. **Request rate over time** (requests/second or requests/minute) permitted by the partner.

These three units are often unequal. With HTTP/1.1, an active request usually holds one connection for its duration, subject to keep-alive, pooling, and proxy details. With **HTTP/2**, multiple streams/requests can share **one TCP connection**; thus a 10-connection cap does not mean only 10 concurrent requests. Multiplexing and concurrent stream limits depend on protocol/implementation.

**If a partner contract states "maximum 20 in-flight requests"**, you need an admission/bulkhead mechanism limiting **operations**, not merely an HTTP connection pool. If the contract specifies **100 requests/second**, add a rate limiter. If the partner returns 429 or `Retry-After`, apply a proper retry/backoff strategy without bursting simultaneously.

### Why Limit Per Dependency?

Suppose service A concurrently calls:

- Inventory API: at most 10 in-flight calls.
- Payment API: at most 4 in-flight calls.
- Shipping API: at most 20 in-flight calls.

Using one shared 40-worker executor **does not guarantee** each API stays below its own threshold; requests could all target Payment and exceed 4. Good designs usually establish **separate bulkheads for Payment, Inventory, and Shipping** or dedicated client-layer pools/throttles.

A **bulkhead** isolates active work per dependency so one slow service cannot consume all resources needed by other services. It does not replace timeouts, circuit breakers, rate limiters, or retry budgets.

## 7. Standalone Java 17 Example: Limiting Two Calls with a Semaphore

`java.util.concurrent.Semaphore` is useful for understanding **permit** acquisition: every call entering the protected section must acquire one permit, and must release it in `finally`. The following example simulates a dependency that tolerates only **two** concurrent operations and makes the outcome deterministic using `CountDownLatch`.

Create **`DependencyPermitDemo.java`**:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.Semaphore;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public final class DependencyPermitDemo {
    public static void main(String[] args) throws Exception {
        Semaphore permits = new Semaphore(2);
        CountDownLatch started = new CountDownLatch(2);
        CountDownLatch releaseWorkers = new CountDownLatch(1);
        AtomicInteger inFlight = new AtomicInteger();
        AtomicInteger maxInFlight = new AtomicInteger();

        Runnable remoteCall = () -> {
            if (!permits.tryAcquire()) {
                throw new IllegalStateException("No capacity for worker");
            }

            try {
                int current = inFlight.incrementAndGet();
                maxInFlight.accumulateAndGet(current, Math::max);
                started.countDown();

                try {
                    // Hold both permits to test the full-capacity case.
                    releaseWorkers.await();
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                }
            } finally {
                inFlight.decrementAndGet();
                permits.release();
            }
        };

        ExecutorService pool = Executors.newFixedThreadPool(2);
        try {
            Future<?> first = pool.submit(remoteCall);
            Future<?> second = pool.submit(remoteCall);

            try {
                if (!started.await(5, TimeUnit.SECONDS)) {
                    throw new IllegalStateException("Workers did not start");
                }

                System.out.println("maxInFlight=" + maxInFlight.get());

                boolean thirdAccepted = permits.tryAcquire();
                if (thirdAccepted) {
                    permits.release();
                }
                System.out.println("thirdAccepted=" + thirdAccepted);
            } finally {
                releaseWorkers.countDown();
            }

            // Future.get() verifies both tasks complete or report an error.
            first.get();
            second.get();

            System.out.println("availableAfter=" + permits.availablePermits());
        } finally {
            releaseWorkers.countDown();
            pool.shutdownNow();
        }
    }
}
```

Run with JDK 17 or later:

```bash
javac DependencyPermitDemo.java
java DependencyPermitDemo
```

**Expected standard output of the program:**

```text
maxInFlight=2
thirdAccepted=false
availableAfter=2
```

**Explanation:**

- Two tasks acquired the two permits, incremented the active operation count, and waited together on the latch. The third call from main saw `tryAcquire() == false` because no permit remained.
- Main released the latch in `finally`; both tasks finished and returned their permits even if interrupted or failing inside the guarded region.
- After `Future.get()` on both, `availablePermits() == 2`. Thus no permit was leaked along the normal path of the example.
- The outcome uses latches and therefore does not depend on OS worker scheduling order. This is a simulation of **bounding operations within one JVM**, not a program actually calling a database/HTTP service.

### Applying This Principle in an Application

Method-body snippet for a **blocking HTTP client**, where every call path to the same dependency passes through a gateway sharing one semaphore:

```java
private final Semaphore targetSlots = new Semaphore(6);

public TargetResult callTarget(Request request) {
    if (!targetSlots.tryAcquire()) {
        throw new TargetBusyException("Target concurrency limit reached");
    }
    try {
        return blockingHttpClient.call(request);
    } finally {
        targetSlots.release();
    }
}
```

The snippet above **illustrates logic only**; `TargetResult`, `Request`, `TargetBusyException`, and `blockingHttpClient` are business types/variables you must define upon integration. Calls must have I/O timeouts and client exception handling. Using `tryAcquire()` is **fail-fast**; if bounded waiting is desired, you can use `tryAcquire(timeout, unit)` on an appropriate blocking thread while factoring that wait into the end-to-end deadline.

**Boundary:** if calling a reactive API returning `Mono`/`Flux`, **never** write `try { return webClient...bodyToMono(...); } finally { slots.release(); }`; `finally` runs immediately when returning the publisher, before the actual async request finishes. Hold the permit until the terminal/cancel signal (e.g., reactive `doFinally` operator), use a compatible reactive bulkhead, and handle subscription/cancellation properly. Never block an event loop with a blocking semaphore wait.

In Spring environments, libraries like **Resilience4j Bulkhead** provide semaphore bulkheads with `maxConcurrentCalls` and `maxWaitDuration`, suitable for per-downstream limits. With reactive code, choose an integrated operator so the permit covers **execution time**, not just publisher assembly time.

## 8. HTTP Connection Pools with WebClient/Reactor Netty

When using `WebClient` with Reactor Netty, you can configure a connection pool for a dedicated HTTP client. Example in a Spring WebFlux/WebClient app with Reactor Netty:

```java
import java.time.Duration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.netty.http.client.HttpClient;
import reactor.netty.resources.ConnectionProvider;

@Configuration(proxyBeanMethods = false)
public class TargetClientConfiguration {
    @Bean(destroyMethod = "dispose")
    public ConnectionProvider targetConnectionProvider() {
        return ConnectionProvider.builder("target-api-pool")
                .maxConnections(16)
                .pendingAcquireMaxCount(24)
                .pendingAcquireTimeout(Duration.ofMillis(700))
                .build();
    }

    @Bean
    public WebClient targetWebClient(ConnectionProvider targetConnectionProvider) {
        HttpClient httpClient = HttpClient.create(targetConnectionProvider)
                .responseTimeout(Duration.ofSeconds(3));

        return WebClient.builder()
                .baseUrl("https://api.example.com")
                .clientConnector(new ReactorClientHttpConnector(httpClient))
                .build();
    }
}
```

This is an **integration** example; it will not run standalone without `spring-webflux` and `reactor-netty-http` dependencies and a real endpoint. Purpose of each setting:

- `maxConnections(16)`: connection cap per provider pool (typically separated by remote host/port), **not** a cap on HTTP operations or requests/second.
- `pendingAcquireMaxCount(24)`: limits how many connection acquisition requests can **wait** when the pool is full. Pending queues should not be unbounded.
- `pendingAcquireTimeout(700 ms)`: wait timeout to acquire a connection. Expiration is an acquire error, **not necessarily** a downstream response timeout.
- `responseTimeout(3 s)`: response time limit per Reactor Netty's mechanism; does not replace connect timeout, DNS deadline, or end-to-end API deadlines across all failure paths.
- `@Bean(destroyMethod = "dispose")`: ensures the provider is released when the application context closes.

**Remember with HTTP/2:** multiple streams can share one connection, and pool/stream handling varies by Reactor Netty version. If the goal is "no more than N concurrent operations to the inventory API," adding a per-request semaphore/bulkhead at the API call layer is usually clearer.

Other clients like Apache HttpClient, JDK `HttpClient`, Feign, or gRPC clients have their own connection management mechanisms. Do not copy Reactor Netty settings onto those clients. Verify the actual implementation used by Spring Boot or your project and apply its corresponding properties.

## 9. Concurrency, Rate, and Timeouts: Three Policies That Must Align

### 9.1. Concurrency Limit Differs from Rate Limit

- **Concurrency limit:** at most **N operations actively processing at the same time**. A 100 ms operation and a 10-second operation hold permits for different durations.
- **Rate limit:** at most **R requests per time window**, e.g., 60 requests/second; does not automatically bound total requests waiting for responses if each request is very slow.
- **Connection limit:** client/server connection count; with HTTP/2, this does not equal request count.

By Little's Law, in a stable system with consistent units, the average number of tasks in the system is approximately `L = λ × W` (completion rate × residence time in the system). For example, receiving 50 requests/second with a 0.4-second service time produces roughly 20 executing requests on average, **not a p99 or peak guarantee**. If latency climbs to 2 seconds at the same arrival rate, in-flight demand can surge, causing queues to build up.

Therefore treat limits as a **resource budget** tied to traffic, service time, timeouts, instance count, and latency distribution. Never raise concurrency automatically when a queue grows: if the target is already saturated, increasing concurrent calls usually just increases errors and timeouts.

### 9.2. Avoid Stacking Wait Times

A single request can spend time across many layers:

```text
Executor queue
    + Hikari connectionTimeout wait
    + DB execution / lock wait
    + HTTP connection pending acquire
    + HTTP connect / response wait
    + retry backoff
    = end-to-end latency (may exceed client deadline)
```

Setting every timeout to 10 seconds while the HTTP client only gives users 5 seconds makes no sense if layers execute sequentially. Prefer defining a **total deadline**, budgeting time per step, cancelling/rejecting upon expiration, and never holding DB transactions/connections while waiting on external services longer than necessary.

**Hikari `connectionTimeout`** only bounds connection acquisition time; it does not abort running SQL. Set driver/database query timeouts and transaction timeouts appropriately; for HTTP clients configure connect timeout, response timeout, and total request deadline; distinguish each type to read metrics accurately.

### 9.3. Retries Can Worsen Target Load

When a DB or target service is already full, immediate retries from hundreds of concurrent requests can trigger a **retry storm**: slower responses cause more retries, and more retries further exhaust connections. Retries must be conditional (only on appropriate errors), bounded in attempts, use backoff with jitter, honor a total deadline, and preserve idempotency.

If an external API enforces rate limits or returns `429 Too Many Requests` with `Retry-After`, honor that contract instead of merely raising connection counts. For operations with side effects like payments, tie retries to idempotency keys/transaction design to prevent duplicate execution.

## 10. Local Limits vs. System-Wide Limits

Suppose there are 5 pods, each using a 6-permit semaphore for Payment. **The whole system can send 30 concurrent Payment calls** if every pod uses all 6 slots. If the partner only allows 10 in-flight calls across the entire tenant, a per-JVM local semaphore is not enough.

Approaches:

| Need | Typical Mechanism | What Must Be Verified |
| --- | --- | --- |
| Limit threads/tasks in one JVM | Explicitly configured executor pool | Do all load sources go through that executor? |
| Limit DB connections per instance | HikariCP `maximumPoolSize` | Sum across all datasources, pods, and other workloads |
| Limit operations to one downstream in one JVM | Semaphore/Resilience4j bulkhead | Do all call paths share the same permit pool? |
| Limit aggregate rate across multiple pods | Gateway/distributed rate limiter | Clocks, quotas, retries, failure modes |
| Limit cluster-wide concurrency | Coordinated admission control/queue with ownership or service gateway | Leases, fairness, crash handling, and permit reclamation |
| Durable work and retries across restarts | Message broker/job queue + bounded consumers | Idempotency, dead-lettering, backlog, ordering |

A distributed semaphore/lock solution must account for pod crashes while holding a slot: TTL/leases, fencing, or knowing when permits can be reclaimed. For databases, using **transactions + constraints + atomic updates** matching business rules is often safer and simpler than custom distributed locks.

**Do not use connection limits as a substitute for data consistency control.** A database with 10 connections can still suffer lost updates, overselling, or duplicate inserts if transactions/constraints are wrong.

## 11. Observing and Testing Before Optimizing

### 11.1. Metrics to Monitor

**For HikariCP** (when the app has Micrometer/Actuator and metrics enabled):

- `hikaricp.connections.active`: connections currently borrowed.
- `hikaricp.connections.idle`: idle connections.
- `hikaricp.connections.pending`: callers waiting to borrow a connection.
- `hikaricp.connections.max`: pool connection limit.
- Connection acquisition timeouts, query latency, slow queries, DB CPU/IOPS, lock waits, and transaction duration.

**For executors:** active threads, pool size, queue size, task rejection count, task execution time, and time spent in queue. Note that `maxPoolSize` does not guarantee an executor will rapidly scale workers to max while queue space remains.

**For HTTP/target APIs:** active/idle/pending connections, pending acquire duration, in-flight requests, p50/p95/p99 latency, timeouts, 429/503/5xx responses, retry counts, and remaining quota. Reactor Netty exposes `reactor.netty.connection.provider.*` metrics when configured appropriately.

Inspect **multiple charts together**: Hikari active=12/12 + high pending signals a full pool, yet if DB CPU is very low and transactions are long due to waiting on HTTP, the fix may be shortening connection hold times rather than enlarging the pool.

### 11.2. Targeted Load Tests

1. **Run low load** to capture baseline throughput, latency, DB active/idle, and downstream response time.
2. **Increase concurrency gradually**, keeping pod count and workload fixed, to find where throughput stops rising while p95/p99 or pending climbs.
3. **Slow down a dependency in a controlled way** (test environment): make DB queries take longer or add mock API delay; observe waiting tasks and timeouts at each layer.
4. **Push past configured limits**: confirm requests reject/wait as expected, queues do not grow unbounded, and other business paths remain able to serve.
5. **Test autoscaling/multi-instance**: observe total DB connections, total downstream in-flight calls, and quotas as pod count rises.
6. **Test retries and failures**: timeouts, 429, 503, connection resets, request cancellation, shutdown; verify permits/connections are returned without leaks.
7. **Adjust one parameter at a time**, then re-measure; avoid simultaneously increasing pool, queue, threads, and retries so you can tell which change had effect.

Avoid a common flawed test: launching 100 tasks without waiting for results, immediately reading metrics, and concluding the system is not overloaded. Ensure all tasks are submitted/counted, enforce test timeouts, and inspect max concurrent tasks, rejected tasks, backlog, and completed tasks.

## 12. Common Design Mistakes

### 12.1. "If the executor has 50 threads, Hikari also needs 50 connections"

Not necessarily. Some tasks may not touch the DB; conversely, other HTTP threads also use the DB. Connection counts must be based on **actual resource usage** and DB capacity. With weak CPU/IOPS, a larger pool often increases contention rather than throughput.

### 12.2. "A 10-connection pool means at most 10 requests per second"

False: a connection can serve many requests sequentially; throughput also depends on query time, transaction length, and connection utilization. Do not confuse **in-flight** with **throughput**.

### 12.3. "We capped HTTP connections so we cannot exceed the API quota"

False with HTTP/2 multiplexing, multiple requests per connection, or multiple clients/pods. If the quota is in-flight operations or requests/second, use proper bulkheads/rate limiters and calculate system-wide totals.

### 12.4. "Increasing `connectionTimeout` will fix pool exhaustion"

It only lets callers **wait longer** before failing; if serving capacity does not grow, queues and latency can worsen. Prioritize finding long transactions, connection leaks, DB locks, slow queries, and overload beyond capacity.

### 12.5. "Having `@Async` means request threads are never held"

A request thread can be freed on properly structured async paths, yet another executor can still stall waiting for connections; submissions can also block or reject when pools/queues fill. Never infer a system is non-blocking solely from `@Async`.

### 12.6. "Wrapping `Mono` creation with `Semaphore.tryAcquire()` is enough"

False: in a reactive pipeline, building a `Mono` only describes work; the actual network call typically happens upon subscription and finishes later. Permits must span the entire execution lifetime, including error/cancel. Use reactive operators/bulkheads that support publisher lifecycle.

### 12.7. "A cap of 20 per pod guarantees total load stays at or below 20"

False when running multiple pods. Sum by maximum instance count or use a shared coordination point for the global limit.

### 12.8. "Fast retries help recover from overload errors"

False when the same dependency is congested: synchronized retry waves prolong congestion and hurt healthy requests. Use backoff, jitter, total retry budgets, circuit breakers, and idempotency.

### 12.9. "Keeping a transaction open during remote API calls doesn't affect the pool"

Across many JDBC transaction paths, the connection stays held until the transaction ends; slow remote calls prolong connection hold time and increase pending acquisitions. Redesign transaction boundaries and use outbox if consistency between DB and external events is needed.

### 12.10. "A nice configuration number is enough, no metrics needed"

Capacity cannot be chosen solely from CPU counts or generic rules of thumb. Measure under real load and failure modes, checking saturation, p95/p99, and total connections across all instances.

## 13. Configuration Selection Process and References

A practical workflow for sizing concurrency around a DB or target service:

1. **Identify the bottleneck:** DB connections, query CPU/locks, HTTP sockets, downstream in-flight quota, or rate quota? Each demands a different mechanism.
2. **Define the scope:** per task, per executor, per datasource, per remote host, per pod, or cluster-wide. Count all load sources and maximum instance count.
3. **Establish a budget:** reserve headroom for priority requests and other systems; set initial concurrency and queues according to capacity, not running against physical ceilings.
4. **Enforce limits where load originates:** Hikari pool for connections; executors for background tasks; semaphores/bulkheads for operations; rate limiters for requests/second; connector pools for sockets.
5. **Define behavior when full:** how long to wait, how to reject, what API response to return, how to retry, and whether durable job storage is needed.
6. **Control resource lifecycle:** close connections/permits properly, enforce timeouts, cancellation, transaction scope, shutdown, and crash/retry handling.
7. **Test under load and faults:** both single-instance and multi-instance, comparing throughput/latency/queue/saturation before changing settings.

### References

- [Spring Boot 3.5 – SQL Databases](https://docs.spring.io/spring-boot/3.5/reference/data/sql.html): datasource auto-configuration and connection pool types.
- [HikariCP – README and Pool Configuration](https://github.com/brettwooldridge/HikariCP): meaning of `maximumPoolSize` and `connectionTimeout`.
- [Spring Framework – Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html): `TaskExecutor`, `@Async`, thread pools, and queue/rejection behavior.
- [Reactor Netty – HTTP Client Reference](https://projectreactor.io/docs/netty/release/reference/http-client.html): connection providers, max connections, pending acquire, and metrics.
- [Resilience4j – Bulkhead](https://github.com/resilience4j/resilience4j#73-bulkhead): isolating concurrent calls per dependency.
- [Java SE 17 – Semaphore](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Semaphore.html): permits, `tryAcquire`, and `release`.

**Key takeaway:** thread count only reflects task-dispatching capacity; **connection counts and DB/remote service capacity limit how much work can execute concurrently**. Proper configuration must protect each resource at its appropriate scope, explicitly define waiting/rejection when full, and be verified with metrics and load testing.
