# Limiting Threads, Queues, and Pressure on Target Resources in Spring WebFlux

## 1. Problem: Many Concurrent Tasks Do Not Mean Infinite Resources

A Spring WebFlux API may receive hundreds of requests, call multiple services via `WebClient`, or integrate a legacy JDBC/SDK library performing blocking I/O. When scaling up by spawning more tasks, you encounter completely different limits:

- **Threads available to execute work**: event-loop threads, CPU workers, blocking-I/O workers, or virtual threads.
- **In-flight tasks**: concurrent subscriptions/inner publishers started at once, e.g., from `flatMap(..., concurrency)`.
- **Task queues**: work already accepted that does not yet have a worker or connection to begin.
- **Target resources**: JDBC/R2DBC/HTTP connection pools, concurrent requests upstream can tolerate, API quotas, CPU, memory, and external service response speeds.

If a target API only handles 20 concurrent requests steadily, creating 1,000 worker threads or 1,000 `Mono` instances does not raise the target API's capacity to 1,000. Instead, work piles up in scheduler queues, connection-pool pending queues, queues on the target server, or gets rejected. The usual result is **rising latency, timeouts, 429/503 errors, GC pressure, and growing memory consumption**.

The goal of this lesson is to design **intentional limits** for each layer, understand the relationship between throughput, concurrency, and queues, handle overload explicitly, keep it measurable, and keep the system stable. This belongs to the **Execution Threading** knowledge area: focusing on where work runs and how to prevent slow sources from taking down the application.

## 2. Diagram of the Path from Request to Target Resource

Consider a WebFlux endpoint receiving multiple IDs and calling an external API:

```text
                         Client requests
                                |
                                v
                       Reactor Netty event loop
                                |
                                v
                       WebFlux controller
                                |
                         Flux<ID> + flatMap
                       (maxConcurrency = 8)
                                |
                                v
                       WebClient / HTTP client
                                |
                  +-------------+-------------+
                  |                           |
           Connection active             Pending acquire
           (pool limit = 16)            (queue limit = 32)
                  |                           |
                  +---------------------------+
                                |
                                v
                   Remote API / database
                   (quota, threads, CPU, DB)
```

If the service also calls a **blocking** SDK, an extra branch usually appears:

```text
Reactive pipeline
       |
       v
Mono.fromCallable(blockingCall)
       |
       v
subscribeOn(dedicated boundedElastic)
       |
       +-- running worker threads (threadCap)
       |
       +-- pending tasks (queuedTaskCap)
       |
       +-- rejected when saturated
       |
       v
Legacy SDK -> downstream resource
```

Each box in the diagram can be an independent limit. Furthermore, multiple concurrent HTTP requests create multiple separate **subscriptions**, each spawning a new `flatMap`. Therefore, `concurrency=8` inside one request **is not an application-wide limit of 8**.

Another crucial point: **non-blocking I/O does not create free target resources**. An event loop can manage many waiting connections without holding one worker thread per connection, yet upstream still must process the actual requests; bandwidth, connection counts, quotas, and memory remain finite.

## 3. Distinguishing Threads, Subscriptions, Connections, and Tasks

| Concept | Limited unit | Example | Equivalent to the other concepts? |
|---|---|---|---|
| Thread | Java execution thread | `Schedulers.parallel()` or `newBoundedElastic` | No; one event-loop thread serves many I/O operations |
| Active inner publisher | Unfinished/uncanceled inner subscription | `flatMap(mapper, 8)` | No; one inner may emit many elements or perform multiple operations |
| Scheduled task | Runnable accepted by a scheduler | `publishOn`, `subscribeOn`, scheduled timers | No; many tasks can queue up for one worker |
| HTTP connection | TCP/TLS connection or pool-managed connection | `ConnectionProvider.maxConnections(16)` | No; HTTP/2 can multiplex many requests over one connection |
| DB connection | Database session inside a pool | `maximumPoolSize` of HikariCP | No; many workers can wait to acquire a connection |
| Pending acquire | Connection request waiting on the pool | `pendingAcquireMaxCount(32)` | No; distinct from scheduler task queues |
| Backpressure demand | Number of elements subscriber is ready to receive | `Subscription.request(n)` | No; not measured in requests/second or threads |
| Rate limit | Operations allowed per time window | 100 HTTP requests/second | No; concurrency only measures what is in-flight at once |

**Do not use a single knob in place of all limits.** In a real application, you might simultaneously have 8 inner publishers, 4 blocking threads, 16 HTTP connections, 32 pending connection acquires, and an upstream allowing only 10 requests/second. The bottleneck lies at whichever layer has the lowest effective capacity for the current load.

## 4. Which Threads Does Reactor Use to Process Work?

### 4.1. The WebFlux Event Loop

Spring WebFlux with Reactor Netty typically receives and processes network events on a small group of **event-loop threads**. These threads are valuable because they can keep handling events from other connections while one non-blocking I/O operation is still waiting for data.

Practical prohibition: **never place prolonged blocking operations on the event loop**, for example:

```java
@GetMapping("/bad")
public Mono<String> badEndpoint() {
    return Mono.fromCallable(() -> {
        Thread.sleep(500); // Unsafe if executed on the event loop
        return "done";
    });
}
```

This is a snippet inside a WebFlux `@RestController`; `Mono.fromCallable` **does not select a separate scheduler on its own**. If WebFlux subscribes on the event loop, `Thread.sleep` can block that thread. `Mono` has no magic to make blocking code non-blocking.

With genuinely reactive APIs (`WebClient`, compatible reactive drivers), use the publisher from the client itself and **return the publisher** to WebFlux:

```java
@GetMapping("/good")
public Mono<String> goodEndpoint() {
    return webClient.get()
            .uri("/status")
            .retrieve()
            .bodyToMono(String.class);
}
```

This is also a snippet: `webClient` must be injected/configured and the target endpoint must exist. `WebClient` is non-blocking on the HTTP client side, yet the target service still has its own processing limits.

### 4.2. Common Schedulers

| Scheduler | Intended usage | What to avoid |
|---|---|---|
| `Schedulers.immediate()` | Runs on the calling thread | Does not isolate blocking code off the event loop |
| `Schedulers.single()` | One shared worker for sequential work | Long blocking stalls everything sharing the worker |
| `Schedulers.parallel()` | Fixed thread group, usually near available CPUs; fits short CPU math | Never put long blocking I/O onto the CPU group |
| `Schedulers.boundedElastic()` | Shared bounded scheduler for legacy blocking work | Do not treat its large default queue as a complete overload defense |
| `Schedulers.newBoundedElastic(threadCap, queuedTaskCap, name)` | Creates a dedicated bounded scheduler for a blocking class | Must manage lifecycle and handle full queues |
| Scheduler from `ExecutorService` | Integrates an executor with custom queue/rejection policy | Do not guess limits without reading the executor config |

`parallel()` is not the tool for every task just because its name contains "parallel." It uses a finite worker group suited for computation. Calling `.publishOn(Schedulers.parallel())` moves the processing chain **after the operator** to this scheduler; it **does not automatically parallelize elements** or boost database capacity.

### 4.3. `subscribeOn` and `publishOn`

For legacy blocking libraries, Reactor recommends wrapping them in `Mono.fromCallable(...)` and placing `subscribeOn(Schedulers.boundedElastic())`:

```java
Mono<Account> account = Mono.fromCallable(
        () -> legacyAccountDao.load(accountId)
).subscribeOn(Schedulers.boundedElastic());
```

This snippet requires the application's DAO and `Account` type. `fromCallable` defers invocation until subscribe; `subscribeOn` arranges related subscription/execution on the designated scheduler. A boundedElastic thread is still **held while `load` waits**, because this remains blocking I/O.

With `publishOn`:

```java
Flux<Integer> calculated = Flux.range(1, 5)
        .publishOn(Schedulers.parallel())
        .map(value -> value * value);
```

`publishOn` creates a scheduler-switching boundary for downstream steps like `map`. It does not turn an upstream blocking call into non-blocking. When combining multiple `publishOn` calls, understand the signal flow direction and thread-switch points.

In Java 21+, Reactor supports a `boundedElastic` variant using virtual threads when JDK and version configuration requirements are met. **Virtual threads reduce thread overhead in many blocking scenarios, but do not remove target-resource, queue, or connection-pool limits.** This lesson uses Java 17 and does not rely on virtual threads.

## 5. Limiting Thread Counts: boundedElastic and the Blocking I/O Layer

In Reactor Core 3.6.6, `Schedulers.boundedElastic()` has a default thread limit based on **10 × available processors** (changeable via system properties) and a default queued-task limit of **100,000 tasks per backing thread**. This is the **shared scheduler** configuration and should not be interpreted as 100,000 tasks across the entire application. Large numbers can allow very high queue wait latency before errors appear.

To isolate a specific blocking dependency, you can create a dedicated scheduler:

```java
Scheduler legacyScheduler =
        Schedulers.newBoundedElastic(
                4,          // max 4 backing threads
                20,         // max 20 queued scheduled tasks / backing thread
                "legacy-io"
        );
```

`newBoundedElastic` returns a `Scheduler` with its own lifecycle. Requires importing `reactor.core.scheduler.Scheduler` and `reactor.core.scheduler.Schedulers`. With this configuration:

- The scheduler does not spawn unbounded platform threads for its tasks.
- When enough workers exist, up to 4 background threads run blocking tasks simultaneously per the scheduler limit.
- Once the scheduler reaches its thread limit, new tasks can be queued per `queuedTaskCap` associated with backing threads. Exact worker-to-backing-thread and queue mapping depends on the implementation.
- When no queue space remains, scheduling is rejected with `RejectedExecutionException`; do not let users wait forever behind an unbounded queue.

**Do not infer total capacity as `4 × 20 = 80` HTTP requests**. This is the limit on scheduled tasks in the scheduler, while one request may spawn multiple tasks or use other connection pools. When multiple `Scheduler.Worker` instances share backing threads, rejection behavior also depends on how workers are assigned to threads.

### Isolating Dependencies to Prevent App-Wide Contention

If integrating two independent blocking SDKs with different load profiles, you can use two separate bounded schedulers:

```java
Scheduler reportScheduler =
        Schedulers.newBoundedElastic(3, 12, "report-legacy");

Scheduler paymentScheduler =
        Schedulers.newBoundedElastic(2, 8, "payment-legacy");
```

These settings are illustrative only, not production defaults. When the reporting service hangs, workers and queues reserved for payments are not automatically consumed by tasks running on the report scheduler.

Every self-created scheduler must be **disposed when the application shuts down**, e.g., exposed as a Spring bean with an appropriate destroy method. Avoid creating a new scheduler **per request**, as that explodes pools/threads and complicates resource cleanup.

## 6. Where Do Queues Appear, and Why Must They Be Bounded?

A task may pass through multiple queues:

```text
Client -> HTTP server ingress
       -> operator/prefetch buffer
       -> scheduler task queue (if switched to a worker)
       -> HTTP connection pending-acquire queue
       -> upstream HTTP server queue
       -> upstream database connection queue
       -> database execution/lock wait
```

**Queues absorb short bursts, but create no sustainable extra throughput.** When arrival rate persistently exceeds processing rate, queued work grows. Larger queues can delay failures until requests have already missed their deadlines, raising heap usage and client wait times.

Four strategies to distinguish:

1. **Bound in-flight work**: concurrency caps so upstream does not receive too many concurrent new requests.
2. **Bound waiting work**: bounded queues; when full, fail fast or return an appropriate overload response.
3. **Bound waiting time**: timeouts/deadlines for acquire, request, and business work, avoiding requests spending seconds in a queue only to execute anyway.
4. **Throttle input**: backpressure where protocols support it, rate limiting at ingress, or admission control.

If you use an unbounded queue and only set a client-side timeout, a task may still consume resources after the caller gives up unless downstream cancels properly. Observe cancellation and configure timeouts at the right layers.

### Failure Modes Under High Load

| Saturated layer | Symptoms | Reasonable action |
|---|---|---|
| Blocked event loop | Latency rises across multiple endpoints; event-loop threads sit waiting | Remove blocking from event loop; move legacy I/O to an appropriate scheduler |
| boundedElastic out of threads + queue | Pending tasks grow, then `RejectedExecutionException` | Reduce accepted load, shorten blocking duration, use bounded queues and signal overload |
| HTTP connection pool full | Pending acquires grow; timeouts/cancellations waiting for connections | Lower `flatMap` concurrency; check `maxConnections`, timeouts, and upstream |
| DB pool full | Threads/tasks wait to borrow connections; checkout wait climbs | Reduce DB concurrency, optimize queries/transactions, size pool to DB |
| Remote API overloaded | 429, 503, p99 spikes, connection resets | Respect quotas, use global limits, retry carefully with backoff/jitter |
| Slow downstream consumer | Operator/response buffers grow; RAM/GC climb | Lower prefetch/concurrency, propagate backpressure, bound buffers |

Do not solve every failure by adding threads. If the bottleneck is a DB with 10 connections and slow SQL, increasing workers from 20 to 200 just creates far more waiters on the DB.

## 7. Pressure on Target Resources and Simple Capacity Math

### 7.1. Little's Law for Average Concurrency

In a stable system, Little's Law states:

\[
L = \lambda \times W
\]

Where:

- `L`: average number of tasks inside the measured scope (can include active and waiting).
- `λ`: average throughput, e.g., requests/second.
- `W`: average time a task spends inside that scope, in seconds.

For example, a system steadily handling **80 requests/second** where each request takes an average of **0.25 seconds** in the downstream call segment: `L ≈ 80 × 0.25 = 20` in-flight requests in that segment. This is an **average estimate**, not p95 or an exact thread/pool configuration. To leave headroom for bursts, monitor distributions and real limits.

If downstream has only 8 connections handling **one request per connection in 0.25 seconds**, ideal capacity is near `8 / 0.25 = 32 requests/second` before overhead. If input persistently arrives at 40/second, queues will tend to grow because demand exceeds processing capacity. Increasing queue size only delays visible overload.

This example does not apply directly to multiplexed HTTP/2 or protocols permitting multiple requests per connection. You must identify **the true limiting unit of work at the target resource**.

### 7.2. Sizing Is Not Just Looking at CPU

20% CPU does not prove ample capacity remains: requests may be waiting on remote APIs, database locks, connections, or quotas. Evaluate at minimum:

- Downstream service time (average and p95/p99).
- Total in-flight requests, pending acquires, and connection checkout wait time.
- CPU, heap, GC, thread counts, and scheduler task run/wait times.
- Actual requests hitting the target API (including retries), plus 429/503/timeout errors.
- Time spent in each queue and cancellation rate when clients stop waiting.

A CPU bottleneck requires a different fix from a network or database bottleneck. When latency rises, use traces/metrics to pinpoint **which layer is waiting** before tuning concurrency.

## 8. Concurrency Limits in Pipelines: Effectiveness and Limits of `flatMap`

```java
Flux<Order> orders = orderIds.flatMap(
        id -> orderClient.fetch(id),
        8 // max 8 active inner publishers in this subscription
);
```

This is a snippet: `orderIds`, `orderClient`, and `Order` must be defined in the application. If `fetch(id)` returns a `Mono<Order>` that initiates an HTTP call on subscribe:

- `flatMap` can subscribe to up to **8** inner publishers at once; as one finishes, it can subscribe to another ID.
- Results from inner publishers can interleave and **do not guarantee** input ID order.
- `8` is a limit **per subscription**. If 50 concurrent HTTP requests arrive and each creates a similar pipeline, the application can send many concurrent calls upstream.
- If each inner triggers two sub-requests, real HTTP request concurrency can exceed the inner count.
- `flatMap` does not directly cap runtime threads or `WebClient` connections.

If ID order must be kept, `flatMapSequential` subscribes eagerly while keeping output aligned by source order, at the cost of **buffering** when earlier inners are slow. If business logic demands the next step run only after the previous finishes, `concatMap` subscribes to inners one by one. Each operator bounds pressure under a different contract.

For instance, `flatMap(mapper, 8, 16)` adds `prefetch=16`, mainly tuning initial demand on **each inner Flux**; it does not mean 16 HTTP requests/second. With inner `Mono`s, large prefetch usually has little effect since each Mono emits at most one value.

## 9. Runnable Java 17+ Program: Inner Limit and Full-Queue Rejection

The example below uses standalone **Project Reactor Core 3.6.6**, without Spring Boot. It has two parts:

1. Create 9 inner `Mono.delay` instances, yet `flatMap(..., 3)` allows at most 3 active inners simultaneously.
2. Create a scheduler with **only 1 backing thread and 1 queued task**. Deliberately hold the first task with `CountDownLatch`, queue a second task, then try scheduling a third task to observe `RejectedExecutionException`.

`CountDownLatch` creates a **controlled** full-queue scenario without hoping the machine is busy or depending on random timing. All waits in the example run in a console app, **never on a WebFlux event loop**.

### 9.1. Project Structure

```text
reactor-resource-limits/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── edu/
                └── demo/
                    └── ResourceLimitsDemo.java
```

Create `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>edu.demo</groupId>
    <artifactId>reactor-resource-limits</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-core</artifactId>
            <version>3.6.6</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.3.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

Create `src/main/java/edu/demo/ResourceLimitsDemo.java`:

```java
package edu.demo;

import java.time.Duration;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Scheduler;
import reactor.core.scheduler.Schedulers;

public final class ResourceLimitsDemo {

    public static void main(String[] args) throws Exception {
        demonstrateInnerConcurrency();
        demonstrateBoundedTaskQueue();
    }

    private static void demonstrateInnerConcurrency() {
        AtomicInteger active = new AtomicInteger();
        AtomicInteger peak = new AtomicInteger();

        List<Integer> results = Flux.range(1, 9)
                .flatMap(id -> Mono.defer(() -> {
                    int running = active.incrementAndGet();
                    peak.accumulateAndGet(running, Math::max);

                    return Mono.delay(Duration.ofMillis(40))
                            .map(tick -> id)
                            .doOnTerminate(
                                    () -> active.decrementAndGet());
                }), 3)
                .collectList()
                .block(Duration.ofSeconds(5));

        if (results == null || results.size() != 9
                || peak.get() != 3 || active.get() != 0) {
            throw new IllegalStateException(
                    "Unexpected concurrency behavior");
        }

        System.out.println("received=" + results.size());
        System.out.println("peakInner=" + peak.get());
    }

    private static void demonstrateBoundedTaskQueue()
            throws InterruptedException {
        Scheduler scheduler =
                Schedulers.newBoundedElastic(1, 1, "legacy-lab");
        Scheduler.Worker worker = scheduler.createWorker();

        CountDownLatch firstStarted = new CountDownLatch(1);
        CountDownLatch releaseFirst = new CountDownLatch(1);
        CountDownLatch queuedCompleted = new CountDownLatch(1);
        AtomicBoolean queuedRan = new AtomicBoolean();

        try {
            worker.schedule(() -> {
                firstStarted.countDown();
                try {
                    releaseFirst.await();
                } catch (InterruptedException error) {
                    Thread.currentThread().interrupt();
                }
            });

            if (!firstStarted.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("First task not started");
            }

            // Thread is occupied: this task enters its bounded queue.
            worker.schedule(() -> {
                queuedRan.set(true);
                queuedCompleted.countDown();
            });

            boolean thirdRejected = false;
            try {
                worker.schedule(() -> {});
            } catch (RejectedExecutionException expected) {
                thirdRejected = true;
            }

            releaseFirst.countDown();

            if (!queuedCompleted.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Queued task not run");
            }
            System.out.println("thirdRejected=" + thirdRejected);
            System.out.println("queuedTaskRan=" + queuedRan.get());
        } finally {
            releaseFirst.countDown();
            worker.dispose();
            scheduler.dispose();
        }
    }
}
```

### 9.2. Running and Reading Results

In the directory containing `pom.xml`:

```bash
mvn -q compile exec:java -Dexec.mainClass=edu.demo.ResourceLimitsDemo
```

Standard output of the example with Reactor Core 3.6.6:

```text
received=9
peakInner=3
thirdRejected=true
queuedTaskRan=true
```

Explanation:

- `received=9`: all nine inners had a chance to run and finish.
- `peakInner=3`: the `flatMap(..., 3)` cap prevented more than three active inners in the example. `Mono.delay` uses Reactor's scheduler, **not a dedicated thread per Mono**.
- `thirdRejected=true`: one thread was occupied by the first task; another task waited in the single-slot bounded queue; the third task was rejected. This is a **scheduled-task limit**, unrelated to the HTTP connection pool.
- `queuedTaskRan=true`: after releasing the first task, the second task had room to run.
- `scheduler.dispose()`: reclaims the custom scheduler. Cleanup steps must not be omitted in long-running applications.

The assertions in the program match a controlled test setup that forces a full queue. On an under-resourced machine, the program might fail on the 5-second test timeout—do not interpret that as Reactor's baseline throughput. Do not treat this example as a performance benchmark.

### 9.3. Variants to Avoid in WebFlux

Never place a task like this directly on the event loop:

```java
@GetMapping("/blocking")
Mono<String> blocking() {
    return Mono.fromCallable(() -> {
        Thread.sleep(500);
        return "blocked";
    });
}
```

`Mono.fromCallable` is a lazy source, **but has not switched schedulers**. If you must use a blocking library, place the entire call in `fromCallable` and use an appropriate scheduler:

```java
@GetMapping("/legacy")
Mono<String> legacy() {
    return Mono.fromCallable(() -> {
        Thread.sleep(500); // Only simulates a blocking SDK
        return "finished";
    }).subscribeOn(legacyScheduler);
}
```

Both snippets above are **snippets** inside a WebFlux controller with `Mono` and `GetMapping` imported, plus a `legacyScheduler` bean. Do not use `Thread.sleep` in production; replace with the real blocking API if integration is mandatory and load-test capacity. `.subscribeOn()` does not make that call non-blocking: the worker is still held for 500 ms. The scheduler has limits and can reject when full.

## 10. Limits Specific to the HTTP Client: Connection Pool and Pending Acquire

A reactive `WebClient` still needs network connections. When concurrent calls exceed available connections, requests must **wait to acquire a connection**. Reactor Netty lets you configure the pool:

```java
ConnectionProvider provider =
        ConnectionProvider.builder("reports-api")
                .maxConnections(16)
                .pendingAcquireMaxCount(32)
                .pendingAcquireTimeout(Duration.ofSeconds(2))
                .build();

HttpClient httpClient = HttpClient.create(provider)
        .responseTimeout(Duration.ofSeconds(3));

WebClient client = WebClient.builder()
        .baseUrl("https://reports.example")
        .clientConnector(
                new ReactorClientHttpConnector(httpClient))
        .build();
```

This is a **Spring WebFlux configuration snippet**, requiring Spring WebFlux/Reactor Netty dependencies and these imports:

```java
import java.time.Duration;
import reactor.netty.http.client.HttpClient;
import reactor.netty.resources.ConnectionProvider;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;
```

The URI `https://reports.example` is only an example, not a live server for testing. Create the provider once for the application lifecycle and close it on shutdown.

Parameter meanings:

- `maxConnections(16)`: caps connections in the pool per client/provider pool scope; not 16 Java threads. With HTTP/2, one connection can serve multiple streams, so understand protocol behavior when sizing.
- `pendingAcquireMaxCount(32)`: number of connection acquire requests held in the pending queue when none is immediately available; exceeding the cap may trigger rejection.
- `pendingAcquireTimeout(Duration.ofSeconds(2))`: maximum time a single connection acquire may wait.
- `responseTimeout(Duration.ofSeconds(3))`: cap on **response read time per HTTP client behavior**, not an end-to-end deadline covering all queue, DNS, connect, and business processing time. When a whole-request deadline is needed, enforce it at the appropriate layer too.

With Reactor Netty, pool limits typically apply **per pool key/destination** of the connection provider; do not treat 16 as a global cap across all upstream hosts in the whole application. A `WebClient` can also share a provider/HTTP resources with other clients, so configuration and sharing scope must be defined clearly.

### Combining with Operator Limits

Example service calling an API for each ID:

```java
public Flux<Report> getReports(Flux<String> ids) {
    return ids.flatMap(id ->
                    reportClient.get()
                            .uri("/reports/{id}", id)
                            .retrieve()
                            .bodyToMono(Report.class)
                            .timeout(Duration.ofSeconds(4)),
            8);
}
```

This is an **integration snippet**, not standalone runnable: it requires a configured `reportClient`, `Report` class, and `Flux`, `Duration` imports. Each subscription allows up to eight active inners, while the HTTP provider may let requests from **other subscriptions** compete for the same pool. If the client retries, a single inner can issue additional HTTP request attempts over time; measure actual attempts.

Do not conclude `flatMap(...,8)` plus `maxConnections(16)` equals "at most 24 requests"; the limits sit on **different** layers and do not add up that way.

## 11. Limits on Databases, Transactions, and Upstream Services

### 11.1. Database Pool

An application accessing JDBC/JPA usually has a connection pool (such as HikariCP). If the pool has 10 connections, creating 100 concurrent JDBC tasks does not give the database 100 connections. Excess tasks may **wait to borrow a connection**, adding latency and risking timeouts.

Example HikariCP configuration in a Spring Boot app using JDBC/JPA:

```yaml
spring:
  datasource:
    hikari:
      maximum-pool-size: 10
      connection-timeout: 2000
```

This is a **configuration snippet**, not a full application. Property names apply when using HikariCP; `connection-timeout` is the maximum wait to borrow a connection from the pool, not how long SQL is allowed to run. The value `2000` is in milliseconds; pool size is only one parameter in total database capacity.

With WebFlux, JDBC is a blocking API. If forced to use it, isolate it from the event loop as in section 5 while still **capping work sent down to JDBC**; blindly increasing boundedElastic threads only creates more pool wait time. If the pipeline needs end-to-end non-blocking, consider R2DBC with reactive drivers and reactive transactions, and size its connection pool accordingly.

### 11.2. Quota-Limited Remote Services

Suppose a partner enforces 100 requests/second. Even if our service keeps only 8 concurrent requests, if each finishes in 20 ms, request emission rate can be very high. **A concurrency cap is not a time-based rate limit.**

Distinguish:

- Concurrency: how many requests are active at the same moment?
- Rate: how many attempts are sent within one second?
- Retry: does one business request generate extra attempts?
- Queue depth: how much work is waiting?
- Deadline: how long does the caller still care about the result?

At an upstream boundary, you may need **concurrency limits, rate limiters, and timeouts together**. On HTTP 429, honor `Retry-After` if present and business logic permits; retry only idempotent operations or ones with proper idempotency keys. Aggressive retries while upstream is overloaded can trigger a **retry storm**.

### 11.3. Per-Dependency Bulkheads

A service calling both a lookup system and a payment system should isolate limits so a slow lookup upstream cannot exhaust resources needed for payments. You can separate client pools, schedulers for blocking SDKs, and admission limits per dependency.

The common architectural term is **bulkhead**: separate bounded work compartments so saturation in one area does not saturate the entire system. It does not always mean building new thread pools for everything; with non-blocking WebClient, bulkheads based on **in-flight request counts**, separate client pools, or limiters may fit better.

## 12. Queues, Deadlines, and Rejection Policies

### 12.1. Why Are Bounded Queues Better Than Infinite Waiting?

If a target resource processes at most 40 tasks/second and incoming work arrives steadily at 60/second, backlog grows by roughly **20 tasks/second** (ignoring overhead). After 10 seconds, backlog can grow by around 200 tasks. Keeping an infinite queue accepts more and more requests that are already stale. When a queue fills up, a **controlled** overload response can be better than accepting more work that cannot finish in time.

Depending on context, overload strategies include:

- **Fail fast**: reject immediately once slots/queues are full; map the error to a sensible HTTP status (typically 503, possibly with an appropriate `Retry-After`).
- **Wait at most a short bounded duration**: pending acquire timeout or bounded wait.
- **Shed load**: throttle accepted work at ingress, or offload processing to a durable queue if business rules allow async results.
- **Slow down the source**: leverage backpressure if upstream can genuinely respond to demand.
- **Drop expired work**: check cancellation/deadlines so work that is no longer needed does not run.

These limits must reflect **SLOs and business goals**, not just machine heap size.

### 12.2. `onBackpressureBuffer` Is Not a Universal Queue

```java
Flux<Event> buffered = events.onBackpressureBuffer(256);
```

This is a snippet requiring a source `Flux<Event>`. This expression inserts a bounded 256-element buffer at a backpressure boundary; when full, error/overflow behavior depends on the overload chosen. It does **not** automatically reduce already-started HTTP calls, limit running SQL, or replace connection pools. For hot sources emitting nonstop, explicit overflow policies and monitoring are needed. Do not blindly use parameterless `onBackpressureBuffer()` on high-load paths due to unbounded memory growth risk.

### 12.3. Timeouts Do Not Replace Real Resource Cancellation

In Reactor:

```java
Mono<String> answer = remoteCall
        .timeout(Duration.ofSeconds(2));
```

This is a snippet with an existing `remoteCall`. If no matching signal arrives before the timeout, `timeout` emits an error and cancels the upstream subscription as supported by the operator. However, **a blocking SDK that ignores interruption/cancellation can keep working** even after the caller gave up. Therefore, configure timeouts inside the HTTP/DB/SDK client itself and enforce thread/queue bounds.

With multi-element `Flux`, `.timeout(Duration)` by default measures the **gap between `onNext` signals** (and from subscribe to the first signal); it is not automatically a deadline for the entire stream. Distinguish idle timeout, connect timeout, acquire timeout, and overall deadline.

## 13. Observing Health Under Load Instead of Only Counting Threads

When a system slows down, the first question is: **where is time being spent?** Metrics groups to collect:

| Layer | Metrics worth observing | Meaning |
|---|---|---|
| HTTP ingress | Requests/s, in-flight, p50/p95/p99, 4xx/5xx | Incoming load and response quality |
| Reactor Netty event loop | Event-loop blocked time, CPU/thread diagnostics | Detect blocking on network threads |
| Custom schedulers | Active/running tasks, pending queue, rejected tasks | Know whether thread or queue caps are hit |
| WebClient connection pool | Active/idle connections, pending connections, acquire timeouts | Pinpoint connection-wait pressure |
| Database pool | Active/idle/pending connections, checkout wait | Identify DB pool bottlenecks |
| Upstream API | 429, 503, latency, retry attempts, timeouts | Identify target capacity |
| Memory | Heap, GC pauses, queue sizes, retained objects | Detect uncontrolled buffer/queue growth |

Micrometer and Spring Boot Actuator can help measure many metric types depending on libraries, versions, and metric configuration. **Verify actual metric names in your application**, rather than assuming every scheduler and pool automatically exports metrics.

Add tracing across layers to break down intervals:

```text
Request total latency
    = ingress queue/wait (if any)
    + waiting for worker/scheduler (if any)
    + waiting for connection
    + I/O/service time at upstream
    + response processing
    + other overhead
```

This is a diagnostic breakdown diagram, not an exact additive formula for concurrent stages. With fan-out across multiple inners, branches can overlap.

### Using Scheduler Hooks Properly

`doOnSubscribe`, `doOnRequest`, `doOnCancel`, and `doFinally` help observe the reactive lifecycle:

```java
Mono<String> traced = remoteCall
        .doOnSubscribe(s -> logger.debug("remote subscribed"))
        .doFinally(signal -> logger.debug("remote finished: {}", signal));
```

This is a snippet: `remoteCall` and `logger` must exist. `doFinally` can receive `ON_COMPLETE`, `ON_ERROR`, or `CANCEL`; cancellation does not mean upstream halted physical work instantly. In production programs, prefer controlled metrics/tracing rather than per-element logging that adds overload.

## 14. Process for Determining Safe Limits

A process to apply when tuning production:

1. **Identify the bottleneck source**: CPU, thread blocking, DB connections, HTTP pool, quota, or upstream latency.
2. **Define scope**: limit per inner, per subscription, per HTTP client, per service instance, or system-wide?
3. **Cap work before generating load**: use `flatMap` concurrency, pool limits, or admission control at the right layer. Do not wait for downstream queues to fill before noticing overload.
4. **Set queue bounds and timeouts**: every major waiting point needs item and time limits paired with a rejection policy.
5. **Isolate bad dependencies**: dedicated schedulers for blocking SDKs or separate pools/limiters for quota-bound upstreams; never allocate unbounded threads.
6. **Ensure cancellation and cleanup**: aborted requests must release subscriptions and connections/resources as supported by the libraries.
7. **Load-test with bursts and failures**: include slow upstreams, timeouts, full connection pools, large responses, client cancels, and retry storms.
8. **Measure before/after**: throughput, tail latency, pending queues, rejections/timeouts, heap, and actual load on upstream.
9. **Tune one layer at a time**: e.g., concurrency 4→8 while holding pools/queues steady; do not raise every limit at once or you cannot tell what helped or hurt.
10. **Keep headroom and protect upstream**: a good configuration stays stable under expected load and handles overload transparently, rather than merely showing low p50 on a single request.

### Practical Selection Table

| Situation | Preferred approach |
|---|---|
| CPU-bound transform on in-memory data | Bound by core count; consider CPU scheduler and work partitioning |
| Non-blocking WebClient calling multiple independent APIs | Moderate `flatMap` concurrency + HTTP pool + timeouts/quotas |
| Mandatory JDBC/blocking SDK integration | `fromCallable` + dedicated boundedElastic + task/DB pool caps |
| Hot source producing faster than consumption | Backpressure or overflow policy, bounded buffers |
| Must preserve source group ordering | `concatMap` or `flatMapSequential`, monitor buffering |
| Upstream returns 429 as load rises | Throttle request rate, lower concurrency, conditional retry with backoff |
| Timed-out requests remain in queues | Shrink queues, set deadlines/cancellation and admission control |
| Heap grows during load tests | Inspect multi-layer queues, prefetch, payload sizes, retained objects |

## 15. Common Misconceptions

| Misconception | Accurate understanding |
|---|---|
| "WebFlux needs no threads" | Event loops and workers still exist; optimization comes from not holding threads waiting on non-blocking I/O. |
| "`Mono.fromCallable` automatically moves blocking code to another thread" | You must choose a scheduler with `subscribeOn`/an appropriate execution mechanism. |
| "`boundedElastic` is unbounded" | Reactor Core caps threads and queues; when full, tasks can be rejected. |
| "Adding threads speeds up every API" | If the target is limited by connections/quotas/CPU, more threads only increase waiting and pressure. |
| "`flatMap(..., 8)` limits the whole server to 8 HTTP calls" | It limits active inners **per subscription**, while many subscribers/other inners can coexist. |
| "`maxConnections(16)` equals 16 requests or 16 threads" | It is a pool connection limit; HTTP/2 can multiplex; it is not thread count. |
| "Prefetch 32 means 32 requests/second" | Prefetch is element demand at an operator boundary, not a rate limit. |
| "Bigger queues mean fewer errors" | They can increase queueing latency, memory, and timeouts; stale work piles up. |
| "Response timeout covers all waiting steps of a request" | Acquire/connect/response/overall deadlines are distinct limits. |
| "Timeout guarantees every task stopped" | Cancellation depends on the client/SDK; blocking code may keep running. |
| "Low CPU means the server is not overloaded" | It may be waiting on DB, connections, remote APIs, or locks. |
| "Virtual threads make the DB pool bigger" | Virtual threads cut thread cost in many cases; the DB pool stays finite. |
| "Retries fix overload automatically" | Misconfigured retries amplify attempts and crash downstream faster. |
| "`publishOn(parallel())` runs each item on its own core" | It switches scheduler boundaries; it does not add per-inner concurrency. |
| "Flux backpressure alone protects every external service" | Protocols/drivers/call sites may not respond to demand; explicit caps and queues are still needed. |

## 16. Self-Assessment Questions and Exercises

**Exercise 1.** An endpoint uses `flatMap(..., 5)` and 30 HTTP requests arrive simultaneously, each creating a separate subscription. Is the service guaranteed to call the target API at most 5 times concurrently?

**Answer:** No. `5` limits active inners **within each subscription**. Multiple subscriptions create cumulative load; client/pool limits or service-wide mechanisms are also needed.

**Exercise 2.** A blocking SDK takes 500 ms and runs on boundedElastic capped at 4 threads. What is the ideal completion rate in calls/second in a zero-overhead environment without expanding the pool?

**Answer:** If each call occupies one thread for the full 0.5 seconds, the limit is roughly `4 / 0.5 = 8 calls/second`. A large queue cannot raise this sustainable ceiling. With SDK contention or a slow target DB, throughput can be lower.

**Exercise 3.** Does `Schedulers.newBoundedElastic(2, 10, "x")` guarantee creating 20 HTTP connections?

**Answer:** No. It caps 2 backing threads and queued waiting tasks per backing thread; the HTTP connection pool is a separate mechanism.

**Exercise 4.** An API has a 10-connection pool, DB latency spikes, and many threads are waiting for connections. Should you immediately raise boundedElastic threads to 100?

**Answer:** Do not do so blindly. Measure wait times, SQL latency, DB limits, transaction handling, and concurrency sent to the DB; shedding input or optimizing queries is often more effective than adding more pool waiters.

**Exercise 5.** Why does `.timeout(Duration.ofSeconds(3))` on a streaming `Flux` not guarantee the stream closes after three total seconds?

**Answer:** Because this overload monitors the **silence gap between signals**, which can continue indefinitely if upstream keeps emitting items in time. An overall deadline is a separate concern.

**Exercise 6.** A service sees HTTP 429s, and raising concurrency from 10 to 50 increases the error rate. Should you raise concurrency further?

**Answer:** No. 429 usually signals upstream rate limits. Inspect quotas/rate limits, reduce load, use cautious retries with backoff/jitter, and track actual attempts.

**Exercise 7.** Do scheduler queues and HTTP pending-acquire queues mean the same thing?

**Answer:** No. Scheduler queues hold tasks not yet picked up by a worker; pending acquire holds connection borrow requests not yet granted. A request can traverse both and needs deadlines at the right layers.

**Exercise 8.** When should you create a dedicated `newBoundedElastic` instead of routing all blocking calls through global `boundedElastic()`?

**Answer:** When a blocking dependency has distinct slowness, quotas, or overload risks and needs **isolated worker/queue counts** so it cannot starve other blocking tasks. Reuse the instance and dispose it on shutdown.

## 17. Conclusion

For execution threading in Spring WebFlux, resource control is a chain of consecutive limits:

1. **Thread/scheduler caps** determine how many blocking/CPU tasks can run on worker groups.
2. **Concurrency caps** determine how many inner jobs can start concurrently within a pipeline.
3. **Queue caps and timeouts** determine how much work may wait and how long callers accept waiting.
4. **Connection pools, quotas, and downstream capacity** determine how much real work can execute at the target resource.

Measure the **actual bottleneck** and apply limits at the right scope. WebFlux saves threads while waiting on non-blocking I/O, yet it does not eliminate physical limits at target services. A stable system knows **when to slow down, wait briefly, fail fast, or cancel**, rather than only increasing concurrency.

## Official Documentation

- Project Reactor, **Schedulers API (3.6.6)**, including `boundedElastic`, `newBoundedElastic`, and queue/thread limits: https://docs.spring.io/projectreactor/reactor-core/docs/3.6.6/api/reactor/core/scheduler/Schedulers.html
- Project Reactor, **Threading and Schedulers**: https://projectreactor.io/docs/core/3.6.6/reference/coreFeatures/schedulers.html
- Project Reactor, **Backpressure and Ways to Reshape Requests**: https://projectreactor.io/docs/core/3.6.6/reference/
- Reactor Netty, **HTTP Client – Connection Pool**: https://projectreactor.io/docs/netty/release/reference/http-client.html
- Spring Framework, **WebFlux**: https://docs.spring.io/spring-framework/reference/web/webflux.html
- Spring Framework, **WebClient**: https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html
- Reactive Streams, **JVM Specification**: https://www.reactive-streams.org/