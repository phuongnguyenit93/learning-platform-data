# Offloading Blocking Tasks to a Bounded Scheduler in Spring WebFlux

## 1. Objective: Keeping the Event Loop Responsive When Using Blocking APIs

In Spring WebFlux, the server typically accepts requests on a small number of **event-loop threads** (such as Reactor Netty's `reactor-http-nio-*` threads). These threads are designed for short tasks, coordinating asynchronous I/O, and handling reactive signals. If a request calls `Thread.sleep(...)`, synchronous JDBC/JPA, a blocking HTTP client, blocking file I/O, or `Future.get()` directly on the event loop, that thread must **wait idle**. Many other requests sharing the event loop can slow down together.

When **a blocking API cannot yet be replaced**, the solution is to isolate the synchronous section into a cold publisher, then offload **execution of the blocking work** to a bounded `Scheduler`. Project Reactor's standard pattern is:

```java
Mono<Result> result = Mono.fromCallable(() -> legacyService.load())
        .subscribeOn(Schedulers.boundedElastic());
```

This is an **illustrative pattern**, not a standalone program: `Result` and `legacyService` are provided by your application. Essentially:

1. `Mono.fromCallable(...)` **defers** calling `legacyService.load()` until a subscriber subscribes.
2. `subscribeOn(...)` shifts subscribing and executing the `Callable` source onto a `boundedElastic()` worker.
3. While the blocking call runs, the scheduler thread is **still occupied**, yet the event loop does not wait on it.
4. Once a result or error occurs, Reactor emits `onNext`/`onComplete` or `onError` to the pipeline.

**Technique limitations:** it does not turn JDBC, JPA, or blocking libraries into non-blocking I/O, does not speed up external calls, and does not create infinite capacity. It only **isolates where blocking occurs** and caps execution resources to protect other reactive threads.

## 2. What Are Blocking, Non-Blocking, and a Scheduler?

### 2.1. Blocking Call

A blocking call holds a thread waiting until a result, timeout, or error arrives, for example:

```java
String readLegacy() throws InterruptedException {
    Thread.sleep(200); // Simulates synchronous I/O; never use sleep for production I/O.
    return "done";
}
```

If `readLegacy()` is called inside `map(...)` running on `reactor-http-nio-*`, that HTTP thread is blocked for 200 ms. With real operations like `jdbcTemplate.query(...)`, blocking duration depends on DB connections, locks, timeouts, and downstream load.

### 2.2. Non-Blocking Reactive Publisher

`Mono<T>` describes a sequence emitting **0 or 1** value; `Flux<T>` describes **0 to many** values. A Publisher does not automatically guarantee non-blocking behavior: if code inside calls a synchronous library, blocking still occurs.

`Mono.just(value)` merely holds an already computed value. Because Java evaluates argument expressions beforehand, `Mono.just(readLegacy())` runs blocking code **at Mono creation time**, potentially before `subscribeOn`.

`Mono.fromCallable(...)` creates a cold publisher: each subscription triggers one invocation of the `Callable`, unless caching/sharing is applied. This deferral is mandatory for moving a blocking call onto the right thread.

### 2.3. What Is a Scheduler?

Reactor's `Scheduler` provides execution scheduling for operators such as `subscribeOn` and `publishOn`. It manages `Worker`s, task queues, and backing threads/executors; it is **not an HTTP server** and not a database connection pool.

| Scheduler | Common purpose | Suitable for blocking I/O? |
| --- | --- | --- |
| `Schedulers.immediate()` | Runs immediately on the current thread | Does not solve blocking |
| `Schedulers.single()` | One shared thread for quick, sequential work | No; one block affects all other tasks |
| `Schedulers.parallel()` | Short, CPU-bound, non-blocking work | **No**; may fail when calling `block()` on non-blocking threads, and blocking code stalls CPU workers |
| `Schedulers.boundedElastic()` | Longer blocking tasks; threads/queues are bounded | **Yes**; recommended transitional option |
| `Schedulers.newBoundedElastic(...)` | Dedicated pool with application-chosen bounds | **Yes**; suitable for isolating a specific blocking integration |

Never use `Schedulers.parallel()` for JDBC or `Thread.sleep` just because of the name "parallel". It serves non-blocking computation, not an unbounded pool of I/O threads.

## 3. Mechanics and Limits of `boundedElastic()`

`Schedulers.boundedElastic()` returns Reactor's **shared scheduler**, suited for offloading blocking calls. Under default settings in many Reactor 3.6–3.8 versions running on platform threads:

- Has a cap on backing threads, defaulting to **10 × available processors** (at scheduler initialization time).
- When no free thread is available, tasks may be **queued**. The default limit is roughly **100,000 pending tasks per backing thread**, not 100,000 for the entire application.
- Once the queue limit is exceeded, the scheduler **rejects scheduling** with an error, typically involving `RejectedExecutionException`.
- Threads can be reused and idle threads reclaimed after an idle period; the shared scheduler typically lives for the lifetime of the application.

These values are **Reactor version defaults** that can be configured and may vary across versions; do not treat them as an SLA. Related JVM system properties include:

```properties
reactor.schedulers.defaultBoundedElasticSize=40
reactor.schedulers.defaultBoundedElasticQueueSize=1000
```

These are **JVM system properties**, not automatically equivalent to putting two lines into Spring Boot's `application.properties`. If needed, pass them via `-D...` before Reactor initializes the shared scheduler, or configure your JVM/container accordingly:

```bash
java -Dreactor.schedulers.defaultBoundedElasticSize=40 \
     -Dreactor.schedulers.defaultBoundedElasticQueueSize=1000 \
     -jar app.jar
```

The command example above targets shells supporting line continuation with `\` (Linux/macOS). Only tune limits after load testing and checking downstream connection pool/CPU/memory constraints. Making queues huge does not make the database faster; it can retain requests longer, increasing memory usage and latency.

### Why Must Requests Still Be Bounded Even with a Queue?

Suppose a pool runs 4 blocking tasks concurrently, each taking 2 seconds. If 500 requests arrive at once, only a few run immediately; the rest wait. The longer the queue, the worse tail response times become. Therefore:

- Limit **concurrent tasks** per operation/channel;
- Set **real timeouts** inside the blocking HTTP/DB/SDK library;
- Enforce a **rejection or load-shedding policy** when queues fill;
- Monitor the scheduler, the blocking resource, and pending requests.

Setting `threadCap=4` on a custom scheduler **does not mean the endpoint accepts at most 4 requests**; excess requests can enter the queue if space remains. Distinguish running tasks from queued tasks.

### Java 21+ and Virtual Threads

Starting with Reactor 3.6, `boundedElastic()` can use a thread-per-task style backed by **virtual threads** when running on Java 21+ with the system property enabled:

```text
-Dreactor.schedulers.defaultBoundedElasticOnVirtualThreads=true
```

This mode differs from the platform-thread pool: each task may use a virtual thread, yet the scheduler still enforces concurrency/queue limits. Virtual threads **do not remove database connection limits, connection pool sizes, rate limits, or memory bounds**; native-code blocking or pinning must still be evaluated. The Java 17 examples below use platform threads for straightforward reproducibility.

## 4. Standard Pattern: Wrap Blocking Calls and Use `subscribeOn`

```java
public Mono<User> findUser(long userId) {
    return Mono.fromCallable(() -> legacyUserDao.findById(userId))
            .subscribeOn(Schedulers.boundedElastic());
}
```

This is a **service illustration**, with `User`/`legacyUserDao` declared in a real project. Explanation:

1. The lambda passed to `fromCallable` holds **the entire synchronous section** requiring isolation.
2. Placing `subscribeOn` right after the source makes the thread boundary clear.
3. When WebFlux subscribes to serve HTTP, the callable executes on `boundedElastic`.
4. Exceptions thrown by `Callable` become `onError` signals; no need to manually `try/catch` and hide failures.
5. If the callable returns `null`, `Mono.fromCallable` **completes empty** (no `onNext`), which might produce unexpected HTTP behavior; verify "not found" semantics and handle explicitly.

For blocking operations with side effects only and no return value:

```java
Mono<Void> update = Mono.fromRunnable(() -> legacyAudit.write("saved"))
        .subscribeOn(Schedulers.boundedElastic())
        .then();
```

This is an illustrative snippet, with `legacyAudit` supplied by the app. `Mono.fromRunnable` emits completion/error; `then()` clearly expresses that only completion matters.

## 5. `subscribeOn` vs. `publishOn`: The Difference That Decides Offloading

Both switch execution contexts, but at different positions and directions:

- **`subscribeOn(scheduler)`**: schedules the subscription process toward the **source** (upstream); with `Mono.fromCallable`, this puts the blocking callable itself onto the scheduler. Placing it right after the source is usually clearest.
- **`publishOn(scheduler)`**: switches **signals coming from upstream** onto the scheduler so that **subsequent** operators run there. It cannot travel back in time to relocate a blocking call that already executed.

Diagram:

```text
RIGHT:       fromCallable(() -> BLOCKING)
                  |
             subscribeOn(boundedElastic)
                  |
                map(...)

WRONG:        just(BLOCKING())  --> publishOn(boundedElastic)
                    ^
                 already ran before Mono was assembled

WRONG:       fromCallable(() -> BLOCKING)
                  |
             publishOn(boundedElastic)
                  ^
              source already ran on upstream thread upon subscribe
```

If you **must** run a blocking transformation inside `map`, you can place `publishOn` **before** that transformation:

```java
Mono<String> migrated = input
        .publishOn(Schedulers.boundedElastic())
        .map(value -> legacyFormatter.format(value));
```

This snippet is illustrative only, assuming `input` is an existing `Mono` and `legacyFormatter` is a blocking API. `publishOn` before `map` runs the `format` callback on the scheduler. Even so, **wrapping the blocking call itself in `Mono.fromCallable(...).subscribeOn(...)` is usually clearer**, especially when pipelines have multiple asynchronous steps or distinct blocking APIs to manage.

### Snippets That Look Right but Are Actually Wrong

**Wrong 1 — eager evaluation before offloading:**

```java
// blockingCall() already ran on the thread assembling the pipeline.
return Mono.just(blockingCall())
        .subscribeOn(Schedulers.boundedElastic());
```

**Right:**

```java
return Mono.fromCallable(() -> blockingCall())
        .subscribeOn(Schedulers.boundedElastic());
```

**Wrong 2 — calling a blocking API directly in `map` on the event loop:**

```java
return requestMono.map(value -> blockingClient.lookup(value));
```

**Right — isolate each value:**

```java
return requestMono.flatMap(value ->
        Mono.fromCallable(() -> blockingClient.lookup(value))
                .subscribeOn(Schedulers.boundedElastic()));
```

**Wrong 3 — calling `.block()` inside a handler and thinking it's reactive:**

```java
@GetMapping("/item")
public String item() {
    return reactiveClient.getItem().block();
}
```

When running on an event-loop/non-blocking thread, `block()` can throw `IllegalStateException` because Reactor forbids blocking on threads marked `NonBlocking`. Elsewhere, it still occupies a waiting thread and defeats reactive benefits. WebFlux handlers should **return `Mono`/`Flux`** and let the runtime subscribe.

**Wrong 4 — calling `.subscribe()` manually inside a controller:**

```java
@GetMapping("/item")
public Mono<String> item() {
    fetch().subscribe(System.out::println);
    return Mono.just("ok");
}
```

Manual `subscribe()` detaches the task from the HTTP lifecycle, loses error/cancellation propagation, and may return "ok" before the core work finishes. **Return the pipeline** to the framework rather than subscribing to "kick off background work".

## 6. Runnable Spring Boot WebFlux Example with Java 17+

This example simulates a legacy integration using blocking `Thread.sleep`, offloaded onto a dedicated scheduler with a **4-thread cap and queue cap of 20 tasks per backing thread**. It uses released **Spring Boot 3.5.16** with compatible Reactor APIs. Production projects should pick a supported Boot version suited to their environment.

Create structure:

```text
offload-demo/
├── pom.xml
└── src/main/java/com/example/offload/OffloadDemoApplication.java
```

### 6.1. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>offload-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

This is a complete Maven POM; there is no need to declare Reactor versions manually because the Spring Boot BOM manages compatible dependencies. **Do not add `spring-boot-starter-web` to the example**, because when both MVC and WebFlux are on the classpath Boot typically chooses the Servlet web application type.

### 6.2. `OffloadDemoApplication.java`

```java
package com.example.offload;

import java.util.List;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Scheduler;
import reactor.core.scheduler.Schedulers;

@SpringBootApplication
public class OffloadDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(OffloadDemoApplication.class, args);
    }

    // Dedicated scheduler for legacy API; on context close, Spring calls dispose().
    @Bean(name = "legacyIoScheduler", destroyMethod = "dispose")
    Scheduler legacyIoScheduler() {
        return Schedulers.newBoundedElastic(4, 20, "legacy-io");
    }
}

@RestController
class LegacyController {

    private final Scheduler legacyIoScheduler;

    LegacyController(@Qualifier("legacyIoScheduler") Scheduler legacyIoScheduler) {
        this.legacyIoScheduler = legacyIoScheduler;
    }

    @GetMapping("/legacy/{id}")
    Mono<String> one(@PathVariable long id) {
        return lookup(id);
    }

    @GetMapping("/batch")
    Mono<List<String>> batch() {
        // Each /batch request allows at most 2 concurrently subscribed lookups.
        return Flux.range(1, 6)
                .flatMap(i -> lookup(i), 2)
                .collectList();
    }

    private Mono<String> lookup(long id) {
        return Mono.fromCallable(() -> blockingLookup(id))
                .subscribeOn(legacyIoScheduler);
    }

    private String blockingLookup(long id) throws InterruptedException {
        Thread.sleep(200);  // Simulates a blocking API only.
        return "legacy-" + id;
    }
}
```

All source above sits in **a single Java file**. Only `OffloadDemoApplication` is `public`; `LegacyController` is package-private and still detected by Spring component scanning. `@Bean(destroyMethod = "dispose")` manages shutdown of the dedicated pool, preventing threads from outliving the application lifecycle.

**Why does this code offload properly?** Spring WebFlux subscribes to the `Mono` returned by the controller. `lookup(id)` does not call `blockingLookup` until subscription. Because the source has `subscribeOn(legacyIoScheduler)`, `Thread.sleep` runs on a worker from the `legacy-io` pool rather than directly on the event loop.

### 6.3. Run and Verify

Requires **JDK 17+**, Maven 3.6.3+, and port 8080 available. From inside `offload-demo`:

```bash
mvn spring-boot:run
```

Open another terminal:

```bash
curl -s http://localhost:8080/legacy/7
```

**Exact** HTTP response body:

```text
legacy-7
```

Test the batch endpoint:

```bash
curl -s http://localhost:8080/batch
```

The body is a JSON array containing 6 strings `legacy-1` through `legacy-6`. **Order is not guaranteed** because `flatMap` may complete inner sources out of order; do not assert exact element ordering as a pass/fail check.

In PowerShell, `curl` may alias another command on some OS versions; use `curl.exe` when needed. You can change the port with `--server.port=8081` via standard Spring Boot arguments if 8080 is busy. When stopping the app, Spring calls `dispose()` on the dedicated scheduler.

### 6.4. Verifying Which Thread Actually Runs

To observe, temporarily add to `blockingLookup` before `Thread.sleep`:

```java
System.out.println("blockingLookup thread=" + Thread.currentThread().getName());
```

After sending requests, thread names usually carry the `legacy-io-` prefix; thread numbers and log line ordering **are not fixed**. Replace with a proper logger in production. Never treat thread names as a rigid API, though do use thread dumps/profilers to verify no `reactor-http-nio-*` thread is stuck inside legacy calls.

## 7. Scheduler Limits, `flatMap`, and Downstream Resources Are Three Separate Things

A resilient design needs **multi-layer controls**, because a scheduler only decides where code runs.

### 7.1. Dedicated Scheduler Limits

`Schedulers.newBoundedElastic(4, 20, "legacy-io")` means:

- **`threadCap=4`**: at most 4 backing threads managed by this scheduler.
- **`queuedTaskCap=20`**: pending task limit per backing thread queue; not "at most 20 requests for the whole app".
- **`name="legacy-io"`**: thread name prefix, useful for debugging.

Tasks can be rejected once queues fill. Queues may distribute unevenly across workers; never compute an exact "4 + 4×20 requests" SLA purely from those two numbers without measuring.

Use a dedicated scheduler when you need to shield the rest of the app from an unstable blocking integration. Shared `Schedulers.boundedElastic()` is simpler and suits occasional/minor blocking tasks. **Never call `dispose()` on shared `Schedulers.boundedElastic()` inside request-handling code**; only dispose schedulers you created and own.

### 7.2. `flatMap(..., concurrency)`

`flatMap(id -> lookup(id), 2)` in the example keeps at most **2 concurrent inner subscriptions** at that operator, preventing all 6 tasks from hitting the pool simultaneously. However, one server can handle **many parallel `/batch` requests**: each request has its own limit, so the aggregate can exceed 2.

For a **global cap** on a legacy backend, apply application-wide admission control/bulkheads/semaphores or rate limiters integrated with publishers and permit release on success, error, or cancellation. Avoid holding blocking semaphore `acquire()` calls on the event loop. Combine timeouts with explicit overload conditions to prevent unbounded queuing.

### 7.3. Real Limits of DB/HTTP/SDK

Suppose a scheduler has 40 threads while the DB pool has only 10 connections. At least part of those tasks will **block waiting for a connection**, raising latency and memory usage. Tune these together:

- allowed incoming request rate;
- concurrent blocking tasks;
- connection pool / HTTP client pool sizes;
- connect, query, read, and overall deadlines;
- maximum throughput of the dependent service.

More workers do not guarantee better performance. A smaller limit carefully benchmarked and monitored is usually far healthier than raising the default `threadCap`.

## 8. Timeouts, Cancellation, Errors, and Retries

### 8.1. Reactive Timeout Cannot Always Interrupt Blocking I/O

```java
return Mono.fromCallable(() -> legacyClient.fetch())
        .subscribeOn(legacyIoScheduler)
        .timeout(Duration.ofSeconds(2));
```

This is an **illustration inside a method**, requiring `import java.time.Duration`; `legacyClient` and `legacyIoScheduler` are provided by the app. `timeout` emits an error when the pipeline fails to receive signals on time and can cancel the upstream subscription. Still, an active blocking call may **not stop immediately** if the blocking library ignores interruption or is stuck in a syscall/SDK without timeouts.

Therefore, configure **connect timeout/read timeout/query timeout** on the *actual blocking library*, aligned with the outer HTTP deadline. If the blocking source cannot be stopped, request cancellation does not immediately free the thread; the thread remains held until the API finishes on its own.

### 8.2. Do Not Retry Unconditionally

`Mono.fromCallable` normally **re-runs the callable on every subscription**. `retryWhen` creates a new subscription on error, potentially repeating the blocking operation:

- For idempotent GET/reads, bounded retries with backoff and jitter may be reasonable for transient failures.
- For writes, payments, emails, or side effects, enforce idempotency keys/transaction semantics before retrying.
- Retries amplify load on the scheduler and downstream; never mass-retry when pools are already saturated.

### 8.3. Handling Full Queues and Business Errors

When a scheduler stops accepting tasks, `RejectedExecutionException` can occur. Define the desired response explicitly:

- return an appropriate error (e.g., HTTP 503 when a dependency is overloaded) with logging/metrics;
- shed new requests to allow recovery;
- never hide errors with `onErrorResume(e -> Mono.empty())` if that tricks clients into thinking the request succeeded;
- never grow queues unboundedly or instantiate a new scheduler per request to "bypass" limits.

Business errors (not found, validation, downstream HTTP statuses) and infrastructure failures (timeouts, rejections, connect failures) should be mapped distinctly at the API layer.

## 9. Proper Design When a Request Combines Multiple Kinds of Work

Suppose an endpoint needs data from `legacyDao` (blocking) combined with `WebClient` (non-blocking). Offload **only the blocking part**:

```java
Mono<LegacyUser> user = Mono.fromCallable(() -> legacyDao.find(userId))
        .subscribeOn(legacyIoScheduler);

return user.flatMap(u ->
        webClient.get()
                .uri("/profiles/{id}", u.id())
                .retrieve()
                .bodyToMono(Profile.class)
                .map(profile -> combine(u, profile)));
```

This is a **condensed illustration**, not a standalone program: `LegacyUser`, `Profile`, `webClient`, and `combine` come from your app. `WebClient` does not need to be "wrapped" in `boundedElastic` just because it follows a blocking source: WebClient natively uses reactive I/O. Never call `.block()` to unwrap WebClient results inside a WebFlux handler.

For hundreds of elements, avoid fetching all data synchronously in one huge blocking query and thinking `Flux.fromIterable(...)` makes it non-blocking streaming. If upstream still blocks to compute the entire set, the scheduler only isolates **that blocking call**. Use pagination, true streaming APIs, or reactive drivers when cross-layer backpressure is needed.

### JDBC/JPA and Transactions

`JdbcTemplate` and `EntityManager`/JPA are typically **blocking**. Running them on a bounded scheduler avoids blocking the event loop, yet **does not make persistence reactive**. Spring Data JPA transactions usually rely on `ThreadLocal`; placing `@Transactional` on a method that merely **returns a cold `Mono`** whose queries later run on another thread after the method returns can mislead imperative transaction management. Do not assume an imperative transaction wraps the deferred callable.

The safe structure is keeping a **blocking service with clear imperative transaction boundaries** (e.g., `@Transactional` on a public method of a Spring-proxied service), then calling that method **inside `fromCallable`** on the bounded scheduler. For end-to-end reactive persistence, evaluate R2DBC and reactive transaction management.

### ThreadLocal, MDC, and Security Context

Switching threads can drop values stored in manually managed `ThreadLocal` variables (correlation IDs/MDC). Reactor provides `Context` and the context propagation ecosystem; use mechanisms compatible with your Spring/Reactor version rather than assuming "every callback runs on the same request thread". Avoid manually copying or leaking sensitive context into static fields.

## 10. Observing and Testing in Practice

A good test demonstrates **thread isolation**, **load bounds**, and **system latency**:

1. **Verify the runtime:** confirm the app runs WebFlux; log/request threads are not occupied by legacy operations; inspect stack traces or profilers.
2. **Generate controlled load:** test 1, 10, and 100 concurrent requests; inspect p50/p95/p99 latency, throughput, error/rejected counts, and queue wait times.
3. **Monitor the scheduler:** thread count, pending tasks, queue wait duration, rejected tasks. Depending on version, instrument schedulers via Micrometer/Reactor Micrometer or profiling tools.
4. **Monitor downstream:** active/pending connection pools, query duration, timeouts, and retries.
5. **Measure under slow downstream:** e.g., raise stub delay from 50 ms to 2 seconds. The scheduler must not spawn unbounded threads; under overload, timeouts and rejection policies should engage.
6. **Test request cancellation:** close a client connection mid-flight and see whether the blocking library responds to interruption or keeps running.
7. **Test correctness:** verify exceptions map cleanly to HTTP semantics; verify transactions and idempotency.

Using BlockHound in compatible dev/test environments can catch certain illegal blocking calls on non-blocking threads. However, BlockHound is **no absolute guarantee** of detecting every blocking API and does not replace benchmarks or thread dumps.

Never judge solely by "faster single-request speed": offloading adds thread-switching overhead; the primary goal is **keeping the event loop unblocked, preserving responsiveness across concurrent blocking I/O, and capping resources**. For pure blocking JDBC/JPA apps, Spring MVC can be simpler and better suited than WebFlux + offloading everywhere.

## 11. Common Mistakes and Fixes

| Symptom / mistake | Cause | Fix |
| --- | --- | --- |
| `Mono.just(dao.query())` with `subscribeOn` | `query()` already ran before the Mono was constructed | Change to `Mono.fromCallable(() -> dao.query())` |
| `publishOn` placed **after** blocking `map` | Thread switch happens too late | Use `fromCallable + subscribeOn` or put `publishOn` before the blocking callback |
| Using `Schedulers.parallel()` for JDBC | Pool is meant for non-blocking/CPU work | Use `boundedElastic` or a dedicated blocking scheduler |
| Calling `.block()` in a WebFlux handler | Blocks reactive threads, may be rejected by Reactor | Return `Mono`/`Flux` to the framework |
| Calling `.subscribe()` in a controller | Detaches work from the HTTP lifecycle | Return the composed publisher using `flatMap`/`then` |
| Creating `newBoundedElastic` **per request** | Leaks threads/queues, defeats shared limits | Define one singleton bean, dispose on shutdown |
| Assuming `boundedElastic` is infinite | Pool/queue are capped and will reject | Add overload policies, metrics, and timeouts |
| HTTP timeout fires, assuming DB query stopped | Cancellation is not guaranteed to interrupt blocking APIs | Configure timeouts on JDBC/SDK/sockets; verify interruption |
| `flatMap(..., 2)` yet app still floods downstream | Limit applies only per individual subscription | Add global admission/bulkhead controls |
| Missing `ThreadLocal`/transactions after thread switch | Imperative context does not automatically hop threads | Keep service transactions inside the callable, use context propagation |
| Offloading every pipeline step to elastic | Unnecessary thread hops; non-blocking steps crowd the blocking pool | Offload only blocking parts; keep WebClient/R2DBC reactive |
| Single-request test looks fast | Fails to reveal contention/queuing | Benchmark concurrency and measure p95/p99, resources, and rejections |

## 12. Self-Assessment Exercises

1. **Which snippet runs the blocking call on the right thread?**

   `Mono.just(legacyCall()).subscribeOn(Schedulers.boundedElastic())` or `Mono.fromCallable(() -> legacyCall()).subscribeOn(Schedulers.boundedElastic())`?

   **Answer:** the second snippet, because the call is deferred until subscription and the subscription is scheduled on the scheduler.

2. **Does `Schedulers.boundedElastic()` turn `JdbcTemplate` into non-blocking I/O?**

   **No.** JDBC still blocks a thread on the bounded scheduler; only the event loop is shielded.

3. **If `threadCap=4` is set, are at most 4 requests accepted?**

   **No.** Excess tasks can queue; distinguish running, queued, and rejected tasks, and add admission control if total requests must be capped.

4. **Does `flatMap(..., 3)` inside one request cap blocking tasks to 3 system-wide?**

   **No.** It bounds concurrency for that operator/subscription; multiple concurrent requests create separate batches.

5. **Why might `timeout(Duration.ofSeconds(2))` fail to free a worker after 2 seconds?**

   **Because** a blocking library may not respond immediately to cancellation/interruption; configure timeouts in the underlying library itself.

6. **When should JDBC be replaced with R2DBC instead of offloading?**

   When the architecture requires end-to-end non-blocking I/O, drivers/DBs are suitable, and real load tests confirm the benefit. If most of the system remains imperative blocking, consider MVC to reduce complexity.

## 13. Application Checklist

- [ ] Identify exactly which APIs block threads and which threads currently execute them.
- [ ] Wrap calls with `Mono.fromCallable` or `Mono.fromRunnable` to defer execution.
- [ ] Place `subscribeOn(Schedulers.boundedElastic())` close to the source, or use a Spring-managed dedicated scheduler.
- [ ] Keep HTTP handlers returning `Mono`/`Flux`, with no `.block()` and no manual `.subscribe()`.
- [ ] Bound concurrency both per stream and globally where required.
- [ ] Configure timeouts in underlying blocking APIs; evaluate cancellation, error/retry/idempotency.
- [ ] Ensure `dispose()` lifecycle on custom schedulers; never create schedulers per request.
- [ ] Verify transactions, ThreadLocal/context, metrics, thread dumps, and overload behavior.
- [ ] Consider Spring MVC when the majority of code is blocking I/O.

## 14. Official Documentation

- Project Reactor — [Threading and Schedulers](https://projectreactor.io/docs/core/release/reference/coreFeatures/schedulers.html)
- Project Reactor — [FAQ: How Do I Wrap a Synchronous, Blocking Call?](https://projectreactor.io/docs/core/release/reference/faq.html)
- Reactor API — [Schedulers: boundedElastic, newBoundedElastic and limits](https://projectreactor.io/docs/core/release/api/reactor/core/scheduler/Schedulers.html)
- Spring Framework — [Spring WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux.html)
- Spring Framework — [Reactive Core, concurrency model](https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html)
- Spring Boot — [Reactive Web Applications](https://docs.spring.io/spring-boot/reference/web/reactive.html)

**Remember:** the core formula to master is **`Mono.fromCallable(blockingCall) + subscribeOn(boundedElastic)`**; production apps additionally require **scheduler bounds, request/concurrency limits, downstream timeouts, and overload observability**. Offloading is a boundary protecting the event loop, not a magic switch turning blocking I/O into reactive I/O.