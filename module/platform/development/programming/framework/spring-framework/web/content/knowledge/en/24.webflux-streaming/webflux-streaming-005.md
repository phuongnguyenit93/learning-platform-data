# Isolating Blocking Tasks with the Right Scheduler and Concurrency Limits in Streaming WebFlux

## 1. Problem: A Single Blocking Call Can Stall Many HTTP Streams

Spring WebFlux uses a non-blocking HTTP processing model over a relatively small number of **event-loop threads**. Reactor Netty receives requests, decodes payloads, and writes responses on these I/O threads. Consequently, if a handler executes synchronous JDBC, `Thread.sleep`, `InputStream.read` on a slow source, or a blocking-only SDK directly on the event loop, every other request sharing that thread can be delayed.

```text
             HTTP requests / SSE / NDJSON
                       |
                       v
           Reactor Netty event loops
             |       |       |
             |  +----+-------+-----+
             |  |  Blocking SDK   |   <- WRONG: holds the event loop
             |  |  waits 2 sec    |
             |  +-----------------+
             |
         other HTTP requests must wait

Better approach:
 event loop -> Mono.fromCallable(...) -> boundedElastic worker
      |                                      |
      | request thread is not held           | Blocking SDK/read/write
      |                                      |
      +<-------- asynchronous result --------+
                       |
             encode/write HTTP response
```

Moving blocking tasks off the event loop only solves **thread isolation**. If 10,000 concurrent users call a legacy service that can only handle 20 requests, the scheduler can accumulate thousands of queued tasks, latency climbs, connection pools exhaust, and overload cascades to other systems. You still need **concurrency limits, bounded queues, timeouts, error control, cancellation, and metrics**.

This lesson belongs to **Streaming WebFlux** because the pressure becomes even more acute on endpoints returning NDJSON/SSE/file streams: each connection can remain open a long time, producers and consumers run at different speeds, and emitting data at an uncontrolled rate adds queue and direct-memory pressure.

**Baseline:** Java 17+, Spring Boot 3.5.x, Spring Framework 6.2.x, Project Reactor 3.7.x, Reactor Netty. With Java 21+, there is also a virtual-threads option for Reactor's boundedElastic covered later.

## 2. Knowledge Objectives and Completion Criteria

After this lesson, you will be able to:

1. Identify **blocking** operations across controllers, services, codecs, publishers, and callbacks.
2. Understand how `Schedulers.parallel()`, `single()`, `boundedElastic()`, and `newBoundedElastic(...)` differ.
3. Know why Reactor's recommended recipe is **`Mono.fromCallable(blockingCall).subscribeOn(Schedulers.boundedElastic())`**.
4. Distinguish `subscribeOn` from `publishOn` and where thread switching happens.
5. Use a **dedicated, bounded** scheduler so one legacy dependency cannot monopolize the global pool.
6. Tune `flatMap(mapper, concurrency)` or `flatMapSequential` to limit tasks **within a single stream**.
7. Distinguish per-stream concurrency from **global concurrency** across all HTTP requests/nodes.
8. Use non-blocking admission such as `Semaphore.tryAcquire` or a bulkhead when needed, without calling `acquire` on the event loop.
9. Recognize that timeouts/cancellation do not automatically stop blocking I/O immediately or roll back side effects.
10. Write a Java 17 WebFlux.fn demo and WebTestClient/StepVerifier tests without blocking the Netty event loop.

No scheduler eliminates the blocking nature of JDBC, file I/O, or synchronous HTTP clients. It only chooses where the blocking work executes; the long-term goal may be a true reactive driver/client or moving the work to a background job.

## 3. What Is Blocking? Classification by Source

| Task | Can Block? | Approach |
| --- | --- | --- |
| `Thread.sleep` | Yes | Never call on the event loop; used in demos only to simulate |
| JDBC `ResultSet.next` / `Connection.execute` | Yes | Reactive driver like R2DBC if suitable; otherwise offload to boundedElastic |
| `RestTemplate` / blocking HTTP SDK | Yes | Prefer WebClient; when forced to use, isolate and bound |
| `Files.readAllBytes` | Yes, and uses heavy RAM | Stream files properly; if using blocking API, isolate executor and cap bytes |
| `InputStream.read` / `OutputStream.write` | Yes | Isolate if synchronous API; watch slow clients and resource cleanup |
| Long-waiting `synchronized`/locks | Possible | Remove contention, not merely switch schedulers |
| `Mono.block()` / `Flux.blockLast()` | Yes | Never use in reactive request pipelines |
| CPU-heavy JSON transformation | Not I/O, but occupies CPU | `parallel` or dedicated compute pool, bound work |
| Regular Jackson HTTP codec | May use noticeable CPU/allocations | Cap payload sizes; codecs should not perform blocking I/O |
| Non-blocking WebClient | Normally does not block caller thread | Use reactive composition, connection pool/timeouts/limits |
| Reactive database driver | Designed non-blocking | Still requires pool/concurrency/backpressure |
| `Mono.just(expensiveCall())` | **Yes**, runs expensiveCall eagerly | Use `fromCallable` to defer side effects |
| `Mono.fromCallable(...)` | Lazy itself, does not switch threads | Add `subscribeOn(boundedElastic)` when the callable blocks |

If a library is marketed as "async" yet actually performs sync I/O and holds threads, measure and inspect it anyway. Merely wrapping a method to return `Mono<...>` while calling blocking code inside on the event loop still stalls the system.

### 3.1. Event-Loop Capacity Is Not Infinite

Netty event loops suit short, non-blocking callbacks. Suppose an event loop handles 100 connections; a single handler holding the thread for 500 ms can delay many other connections even while CPU sits mostly idle. When streaming, this manifests as bursty SSE events, sluggish NDJSON responses, or latency spikes on health endpoints.

Do not "fix" this by blindly increasing Netty event-loop thread counts. If threads block for 2 seconds, adding a few threads neither fixes the root bottleneck nor increases downstream capacity.

## 4. Key Schedulers in Reactor

| Scheduler | Characteristics | Suitable For | Unsuitable For |
| --- | --- | --- | --- |
| `Schedulers.immediate()` | Runs tasks on the current thread | Lightweight processing | Does not isolate blocking |
| `Schedulers.single()` | Shares one dedicated thread | Lightweight sequential work | One blocking task stalls every shared task |
| `Schedulers.parallel()` | Fixed pool sized to CPU count | Short CPU-bound calculations | Blocking JDBC, blocking sockets, waiting file I/O |
| `Schedulers.boundedElastic()` | Shared pool for blocking work with **thread and pending-task caps** | Legacy blocking I/O, migrations | Does not protect the whole system from request floods alone |
| `Schedulers.newBoundedElastic(...)` | Dedicated pool with configurable caps/queues | Isolating one dependency per SLA/quotas | Does not replace app-wide admission control |
| `Schedulers.fromExecutorService(...)` | Wraps a Java ExecutorService | Integrating an existing lifecycle-managed pool | Avoid unbounded common executors by default |

Key notes:

- Legacy `Schedulers.elastic()` is discouraged for isolating heavy blocking work because it can spawn excessive threads and mask backpressure issues.
- `Schedulers.parallel()` and `single()` mark their threads as **non-blocking**; calling `block()` on them may throw `IllegalStateException`.
- `boundedElastic` is a suitable place to wait on a blocking library, yet it **does not** magically give external libraries HTTP/TCP backpressure.
- A Scheduler is not a Reactive Streams Subscriber. `request(n)` is a demand signal; a scheduler determines where tasks run. The two complement rather than replace each other.

### 4.1. Default Limits of boundedElastic in Reactor 3.7

Per Reactor 3.7 Javadoc:

- Shared `boundedElastic()` defaults to **a maximum of 10 × CPU processors** at runtime for backing platform threads.
- The default queue cap is **100,000 pending tasks per backing thread**, not a single 100,000 queue for the entire system.
- Once the corresponding queue/capacity fills, scheduling can throw **`RejectedExecutionException`**.
- Idle pools may be reclaimed after a period (default ~60 seconds for the platform-thread implementation).
- Defaults can be tuned via system properties `reactor.schedulers.defaultBoundedElasticSize` and `reactor.schedulers.defaultBoundedElasticQueueSize` **before the global scheduler initializes**.

These defaults are **not capacity recommendations for every server**. For instance, 8 CPUs allow ~80 backing threads and huge queued task counts; a downstream DB pool with only 10 connections can still overload or suffer severe latency. 100,000 queued tasks **per backing thread** is a technical upper bound, not a healthy short queue for interactive HTTP APIs.

Do not throw every legacy endpoint, huge export, and blocking log into the same shared scheduler without boundaries when workloads have different SLAs and load profiles.

## 5. The Right Core Pattern: fromCallable + subscribeOn

### 5.1. Wrong: Calling Blocking Code Before Creating the Mono

```java
// Anti-pattern: legacyClient.fetch(id) runs immediately on
// the current thread, which may be the Netty event loop.
return Mono.just(legacyClient.fetch(id));
```

`Mono.just(...)` only wraps an **already-computed value**. Java evaluates `fetch(id)` before `Mono.just` is invoked. Even if `.subscribeOn(boundedElastic())` is appended afterward, `fetch` already ran **before** scheduling.

### 5.2. Right: Defer and Shift Subscription

```java
Mono<Customer> find(String id) {
    return Mono.fromCallable(() -> legacyClient.fetch(id))
            .subscribeOn(Schedulers.boundedElastic());
}
```

This is a **fragment**, assuming `legacyClient.fetch` has a blocking contract and returns a `Customer`. This `Mono` is lazy; the callable runs when subscribed on a `boundedElastic` worker. Reactor recommends placing `subscribeOn` close to the blocking source.

`Mono.fromCallable` completes empty if the callable returns null; if null is a business error, add `switchIfEmpty(Mono.error(...))` to yield 404/502 appropriately.

### 5.3. For Blocking Operations Returning No Result

```java
Mono<Void> writeAudit(AuditLine input) {
    return Mono.fromRunnable(() -> blockingAuditSink.write(input))
            .subscribeOn(Schedulers.boundedElastic())
            .then();
}
```

This is a fragment. `Mono.fromRunnable` fits side-effect-only tasks with no return value. Never call `subscribe()` in a service to "fire-and-forget" without owner/lifecycle/error tracking; once the HTTP request finishes, audit errors can be silently lost. If auditing must be durable, consider an outbox/message broker/job with transaction boundaries.

### 5.4. Checking Threads via Logs

```java
Mono.fromCallable(() -> {
    String name = Thread.currentThread().getName();
    return "read-on=" + name;
}).subscribeOn(Schedulers.boundedElastic());
```

This is a fragment; observing output requires subscribing through a test or HTTP pipeline. **Never assert exact thread names in production**: implementations vary by Reactor version, custom schedulers, or Java 21 virtual-thread mode.

### 5.5. Never Call block() to "Finish" a Pipeline

```java
// Wrong inside a WebFlux handler:
Customer c = find(id).block();
return ServerResponse.ok().bodyValue(c);
```

Replace with:

```java
return find(id)
        .flatMap(customer ->
                ServerResponse.ok().bodyValue(customer));
```

Functional WebFlux handlers return `Mono<ServerResponse>` and the framework subscribes. Calling `block()` on the event loop can throw errors or stall other HTTP requests.

## 6. How Does subscribeOn Differ from publishOn?

### 6.1. subscribeOn: Affects Upstream Subscription/Source

```java
Mono<String> pipeline =
        Mono.fromCallable(() -> blockingGateway.read())
            .subscribeOn(Schedulers.boundedElastic())
            .map(String::trim);
```

`subscribeOn` affects where the source/subscription executes. For blocking sources, placing it close to the source clarifies why scheduling is there.

### 6.2. publishOn: Switches Downstream Execution Context

```java
Flux<Result> pipeline =
        incoming
            .publishOn(Schedulers.parallel())
            .map(this::expensiveCpuTransform);
```

`publishOn` creates a scheduler boundary for downstream operators until another boundary appears; it has its own **prefetch/queue**. Suitable for isolating bounded CPU-heavy transforms; never use `parallel` for blocking JDBC or `Thread.sleep`.

Another way to isolate a blocking stage:

```java
return source
        .flatMap(item ->
            Mono.fromCallable(() -> blockingGateway.fetch(item))
                .subscribeOn(Schedulers.boundedElastic()),
            4);
```

This fragment creates **one lazy Mono per item**, executing blocking calls on `boundedElastic` with at most four active inner publishers in that subscription.

### 6.3. Order and Structure Are What Matter

Appending `publishOn(boundedElastic)` at the end of a chain **does not travel back in time** to move an earlier blocking call. The example below still risks blocking the event loop:

```java
return source
        .map(id -> blockingGateway.fetch(id))  // runs beforehand
        .publishOn(Schedulers.boundedElastic());
```

If you truly need that `map` stage moved onto a pool, `publishOn` must sit **before** `map`—though `flatMap(id -> Mono.fromCallable(...).subscribeOn(...), n)` usually makes both the blocking boundary and concurrency explicit.

## 7. Creating a Dedicated Scheduler for Legacy Systems

Use `newBoundedElastic` to partition separately:

```java
@Configuration
class LegacySchedulerConfig {
    @Bean(destroyMethod = "dispose")
    Scheduler legacyIoScheduler() {
        return Schedulers.newBoundedElastic(
                4,              // max 4 backing threads
                32,             // queue cap per backing thread
                "legacy-io");   // thread name prefix
    }
}
```

This is a **class fragment** requiring imports for `@Configuration`, `@Bean`, `reactor.core.scheduler.Scheduler`/`Schedulers`. Calling `dispose()` when the Spring context closes frees the dedicated scheduler. With Spring Boot 3.5, `Scheduler` beans can be injected by qualifier.

**4 threads, 32 pending tasks/thread** are **learning** numbers, not production specs. The second parameter of `Schedulers.newBoundedElastic(threadCap, queuedTaskCap, name)` is **queue capacity PER BACKING THREAD**, not 32 tasks for the whole pool; never treat it as a global request quota.

Benefits of a dedicated scheduler:

- One slow dependency cannot exhaust the shared `boundedElastic` pool.
- Metrics are easy to collect per scheduler name.
- Custom timeouts/rejection policies can be applied per dependency.
- Thread caps reflect an initial bound on downstream concurrency.
- Clear lifecycle; never create a new scheduler **per HTTP request**.

Avoid:

```java
// Anti-pattern: creating a new pool per request easily leaks resources:
Mono.fromCallable(this::blockingWork)
        .subscribeOn(
            Schedulers.newBoundedElastic(4, 32, "per-request"));
```

Creating an undisposed scheduler per request causes resource leaks and management overhead. Use a singleton Spring bean or shared scheduler when appropriate.

## 8. Limiting Concurrency with flatMap and flatMapSequential

A `Flux<ID>` may carry hundreds of IDs. Writing:

```java
return ids.flatMap(id -> legacyService.find(id));
```

`flatMap` has default concurrency/prefetch settings that can spawn many inner subscriptions and queues. With blocking downstreams, **specify concurrency explicitly**:

```java
Flux<Result> responses = ids
        .flatMap(
            id -> legacyService.find(id),
            4);
```

Within **one subscription** of this pipeline, `flatMap(..., 4)` bounds concurrently subscribed inner publishers so at most four calls run concurrently in that stream.

Notes:

- `flatMap` can emit results **out of input ID order** because tasks finish at different speeds.
- `flatMapSequential(mapper, 4)` runs inner tasks concurrently while **preserving output order**; preserving order may buffer early-completing results.
- `concatMap` runs inner publishers **sequentially** (effectively concurrency 1) and preserves order.
- `flatMap(mapper, concurrency, prefetch)` adds a prefetch parameter affecting demand/queues; it is not a hard byte memory cap.
- If one item is a 10 MB object, concurrency 4 can still retain tens of MB plus codec overhead.
- With hot sources, concurrency control does not throttle a broker or sensor pushing regardless of demand.

### 8.1. Difference Between Per-Stream and Global Concurrency

Suppose each HTTP request runs:

```java
Flux.range(1, 100)
    .flatMap(this::blockingFetch, 4);
```

With **200 concurrent HTTP requests**, total inner subscriptions can theoretically reach `200 × 4 = 800` (before scheduler/downstream limits). Thus **`flatMap(...,4)` is not an application-wide limit of 4 calls**.

Beyond per-stream caps, account for:

1. Global concurrency/bulkheads per dependency.
2. Scheduler thread caps and queue caps.
3. HTTP client connection pools / JDBC pools.
4. Gateway limits, tenant quotas, and fairness.
5. Timeouts and circuit breakers.
6. Memory consumed by buffered outputs and in-flight items.

If three instances are deployed, a cap of 4 per instance still allows 12 cluster-wide calls. Global/cross-node quotas require a coordinator/broker/gateway or service-side policy, not just an in-JVM `Semaphore`.

## 9. Non-Blocking Bulkhead with Semaphore.tryAcquire

A `Semaphore` can cap **currently executing** blocking operations, yet must be used carefully to avoid blocking the event loop.

**Wrong:**

```java
// Anti-pattern if executed on a reactive event-loop thread:
semaphore.acquire(); // BLOCKS until a permit is available!
try {
    blockingGateway.fetch();
} finally {
    semaphore.release();
}
```

**Better:** if a cap is needed, use non-blocking `tryAcquire()` inside the scheduled callable:

```java
Mono<Result> fetchBounded(String id) {
    return Mono.fromCallable(() -> {
        if (!slots.tryAcquire()) {
            throw new LegacyBusyException();
        }
        try {
            return blockingGateway.fetch(id);
        } finally {
            slots.release();
        }
    }).subscribeOn(legacyScheduler);
}
```

This is a **fragment**, assuming a singleton `Semaphore slots`, dedicated `Scheduler legacyScheduler`, and real exceptions/types. When permits run out, the worker task fails fast instead of waiting for a permit. However, tasks may still **wait in the scheduler queue before reaching tryAcquire**. Therefore:

- Scheduler queues still need bounds and monitoring.
- If you must reject *immediately upon HTTP endpoint entry*, use request-boundary/gateway admission control or non-blocking acquisition **before** scheduling with cancellation-safe ownership.
- Never call `tryAcquire(timeout, unit)` on the event loop; even with a timeout, it **blocks**.
- Permits must be released in `finally` right when the blocking call actually finishes, not merely when downstream cancels.
- If you release a permit in `doFinally` while the blocking thread keeps running after cancel/timeout, you undercount active calls and allow excessive real work. Tie permit lifetime to the **actual blocking task** or use a bulkhead library with clear cancellation contracts.
- If a queued task is cancelled **before starting**, acquiring inside the callable leaks no permit.

For advanced capabilities (fairness, metrics, global distribution, slow queues, circuit breakers), use a maintained bulkhead/rate-limiter library or ingress admission controls; the `Semaphore` demo only illustrates the principle.

## 10. RejectedExecutionException, Overload, and HTTP Statuses

When `newBoundedElastic` runs out of backing threads and queue space for tasks, scheduling can throw `RejectedExecutionException`. When a dependency is overloaded and a custom bulkhead's `tryAcquire` returns false, you can return **503 Service Unavailable** with a controlled `Retry-After`.

```java
return legacyService.find(id)
        .flatMap(result ->
            ServerResponse.ok().bodyValue(result))
        .onErrorResume(
            RejectedExecutionException.class,
            ex -> ServerResponse.status(503)
                    .header("Retry-After", "1")
                    .bodyValue(Map.of(
                        "code", "LEGACY_CAPACITY_EXCEEDED")));
```

This is a **fragment**. Never treat `503 Retry-After: 1` as a universal recipe. Choose retry hints based on service semantics, SLOs, load, and jitter/backoff. On a request that has already streamed part of its response, you **cannot change** status 200 to 503; see the streaming section below.

### 10.1. Distinguishing 429 and 503

- **429 Too Many Requests:** the client/tenant exceeded policy request rates/quotas.
- **503 Service Unavailable:** a dependency/instance temporarily lacks capacity.
- **504 Gateway Timeout:** a gateway did not receive a timely upstream response in that role.
- **500 Internal Server Error:** unclassified internal failure or bug.
- **408 Request Timeout:** the client failed to send the request on time per HTTP semantics.

Do not map every `TimeoutException` to 429 or every `RejectedExecutionException` to 400. Keep error codes, metrics, and retry policies consistent.

## 11. Timeouts and Cancellation Are Not Magic

One way to bound duration:

```java
return legacyService.find(id)
        .timeout(Duration.ofMillis(500));
```

`timeout` emits `TimeoutException` downstream when exceeded and normally cancels the upstream subscription. However:

- Threads currently inside blocking JDBC/SDK calls may **not stop immediately** or may not support interruption.
- Queued tasks may not have started yet; cancellation may prevent them from running where the scheduler supports it.
- `Thread.interrupt` does not guarantee underlying network sockets/DB operations abort cleanly.
- Already-committed side effects (such as payments or emails) do not roll back merely because downstream timed out.
- If the client retries after a timeout while the server is still processing, the request may execute **twice**.
- `doOnCancel` and `doFinally(CANCEL)` signal publisher lifecycle events; they do not guarantee completion of external work cleanup.

### 11.1. Multi-Layer Deadlines and Timeouts

A legacy call should have:

1. HTTP client/request deadline.
2. Connection acquisition timeout.
3. Socket/connect/read timeouts on the actual **SDK or database driver**.
4. Bulkhead/queue-wait deadline.
5. Reactor `timeout` for the end-to-end promise.
6. Gateway/ingress timeouts and retry policies.
7. Idempotency keys/transaction semantics for operations with side effects.

If Reactor's timeout is 200 ms while the JDBC driver timeout is 30 s, the client receives an early error while DB threads/connections remain tied up far longer. Always configure **timeouts at the blocking source** and cap in-flight operations.

### 11.2. Never Retry Infinitely Under Overload

```java
// Avoid:
return legacyService.find(id).retry();
```

Against an exhausted dependency, infinite retries cause a **retry storm**, keeping scheduler queues and connection pools full. Use bounded retries with exponential backoff/jitter, only for retryable errors, and only when operations are idempotent or have deduplication keys. Partially streamed requests usually cannot retry cleanly without framing/checkpoints.

## 12. Streaming WebFlux: Slow Producers, Slow Consumers, and Buffering

### 12.1. Using NDJSON

NDJSON-style HTTP response:

```http
HTTP/1.1 200 OK
Content-Type: application/x-ndjson

{"id":"A","value":"value-A"}
{"id":"B","value":"value-B"}
{"id":"C","value":"value-C"}
```

A `Flux<Record>` returned via `ServerResponse.body(flux, Record.class)` can be encoded record-by-record when the content type is `application/x-ndjson`. However:

- Default `flatMap` may reorder items; use `flatMapSequential` or `concatMap` if input order must be preserved.
- Codecs may buffer per record, and networks have outbound queues.
- Proxies/CDNs may coalesce events and flush only at the end.
- `subscribeOn(boundedElastic)` isolates blocking sources; it does not directly control TCP flushing.
- If the client disconnects, downstream may cancel the stream while an already-started blocking task keeps running.
- If record 20 fails after HTTP 200 has committed, the response may contain only 19 records without a complete JSON error body.

**Every record still requires validation and total stream quotas.** In the demo, input is capped at eight IDs to bound task counts; production needs ID validation, authorization, and tenant boundaries.

### 12.2. With SSE

A live dashboard might emit:

```text
id: 7
event: progress
data: {"percent":70}

id: 8
event: complete
data: {"percent":100}

```

SSE `ServerSentEvent<T>` is encoded by WebFlux as `text/event-stream`. If data comes from a blocking SDK, wrap each call on a bounded scheduler—or better, use an asynchronous source. **Never dedicate a blocking thread per SSE subscriber running `while(true) Thread.sleep(...)`**: it ties up workers for long durations and exhausts pools.

Considerations:

- Use scheduler timers/reactive `Flux.interval` for heartbeats instead of sleeping workers.
- Shared pub/sub data sources and per-client bounded queues/drop/latest strategies (when dropping updates is allowed).
- When every event must arrive intact, use a durable broker + IDs + replay.
- Connection limits/heartbeats/reconnect/backoff.
- Never treat Reactor demand as a wire-level HTTP `request(n)` command from browser EventSource.

### 12.3. Slow Consumers and Response Encoding

When clients read slowly, Reactor Netty can throttle demand based on write readiness, yet operator queues, JSON encoding, and proxy buffers still exist. If each response item holds several MBs, even concurrency 2 can consume substantial heap/direct memory.

Never use unbounded `onBackpressureBuffer()` to "fix" slow networks; it can trigger OOM. If sampling is acceptable, choose `onBackpressureLatest`/`onBackpressureDrop` by policy; if data is critical, propagate backpressure to the source or use a broker/replay.

## 13. Runnable Application: Spring Boot 3.5 + WebFlux.fn + Bounded Legacy Calls

The demo includes two endpoints:

- `GET /api/legacy/{id}`: calls a **simulated blocking** service running on a dedicated `boundedElastic` scheduler, returning JSON on success.
- `GET /api/legacy/stream?ids=A,B,C`: returns an **NDJSON stream** preserving input order via `flatMapSequential(..., 2)`; maximum eight IDs per request.
- Each blocking call uses `Semaphore.tryAcquire` inside the **worker** to limit **three concurrent executions per JVM**.
- The dedicated scheduler has at most four backing platform threads and a queue cap of 32 per backing thread. When capacity runs out, custom exceptions or scheduler rejections map to 503 for the single endpoint; for an already-started stream, observe committed HTTP response constraints.
- Tests use real `WebTestClient` over HTTP and `StepVerifier`/metrics to confirm outputs and concurrency bounds.

**Scope:** the demo only has a read-only simulated service. `Thread.sleep(70)` illustrates a blocking SDK; this is **not** behavior to ship in production. Auth/tenant quotas, real DB/HTTP clients, distributed concurrency limiters, and guaranteed flow control across proxies are omitted.

### 13.1. Creating the Gradle Project

Select Java 17, Spring Boot 3.5.x, Gradle, and **Spring Reactive Web** in Initializr. In a project with Boot plugin, dependency management, Maven Central, and toolchain configured, dependencies are:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

This is a **`build.gradle` fragment**, not a standalone Gradle file. Do not add `spring-boot-starter-web` to the demo if you want WebFlux/Netty: Boot 3.x typically selects Servlet MVC when both MVC and WebFlux starters are present.

### 13.2. Java Source: One Complete File

Create **`src/main/java/demo/isolation/IsolationApplication.java`**:

```java
package demo.isolation;

import java.util.Arrays;
import java.util.List;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.Semaphore;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.server.RouterFunction;
import org.springframework.web.reactive.function.server.RouterFunctions;
import org.springframework.web.reactive.function.server.ServerRequest;
import org.springframework.web.reactive.function.server.ServerResponse;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Scheduler;
import reactor.core.scheduler.Schedulers;

@SpringBootApplication
public class IsolationApplication {
    public static void main(String[] args) {
        SpringApplication.run(IsolationApplication.class, args);
    }
}

record LegacyRecord(String id, String value) {}

record ApiError(String code) {}

class LegacyBusyException extends RuntimeException {}

@Configuration
class IsolationConfig {

    @Bean(destroyMethod = "dispose")
    Scheduler legacyIoScheduler() {
        // Demo: 4 threads, 32 queued tasks per backing thread.
        return Schedulers.newBoundedElastic(
                4, 32, "legacy-io");
    }

    @Bean
    RouterFunction<ServerResponse> legacyRoutes(
            LegacyHandler handler) {
        return RouterFunctions.route()
                // Static route before variable route.
                .GET("/api/legacy/stream", handler::stream)
                .GET("/api/legacy/{id}", handler::single)
                .build();
    }
}

@Component
class LegacyBlockingGateway {
    private final Semaphore slots = new Semaphore(3);
    private final AtomicInteger active = new AtomicInteger();
    private final AtomicInteger peak = new AtomicInteger();

    LegacyRecord fetch(String id) throws InterruptedException {
        // Runs only inside scheduled callable.
        if (!slots.tryAcquire()) {
            throw new LegacyBusyException();
        }

        int inFlight = active.incrementAndGet();
        peak.accumulateAndGet(inFlight, Math::max);

        try {
            // Simulate synchronous/legacy SDK API.
            Thread.sleep(70L);
            return new LegacyRecord(id, "value-" + id);
        } finally {
            active.decrementAndGet();
            slots.release();
        }
    }

    int peakActive() {
        return peak.get();
    }

    int activeNow() {
        return active.get();
    }
}

@Service
class LegacyService {
    private final LegacyBlockingGateway gateway;
    private final Scheduler legacyScheduler;

    LegacyService(
            LegacyBlockingGateway gateway,
            @Qualifier("legacyIoScheduler")
            Scheduler legacyScheduler) {
        this.gateway = gateway;
        this.legacyScheduler = legacyScheduler;
    }

    Mono<LegacyRecord> fetch(String id) {
        return Mono.fromCallable(() -> gateway.fetch(id))
                .subscribeOn(legacyScheduler);
    }
}

@Component
class LegacyHandler {
    private final LegacyService service;

    LegacyHandler(LegacyService service) {
        this.service = service;
    }

    private Mono<ServerResponse> invalidIds() {
        return ServerResponse.badRequest()
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(new ApiError("INVALID_IDS"));
    }

    private Mono<ServerResponse> overloaded() {
        return ServerResponse
                .status(HttpStatus.SERVICE_UNAVAILABLE)
                .header(HttpHeaders.RETRY_AFTER, "1")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(new ApiError("LEGACY_OVERLOADED"));
    }

    Mono<ServerResponse> single(ServerRequest request) {
        String id = request.pathVariable("id");
        if (!id.matches("[A-Za-z0-9-]{1,16}")) {
            return invalidIds();
        }

        return service.fetch(id)
                .flatMap(record ->
                    ServerResponse.ok()
                        .contentType(MediaType.APPLICATION_JSON)
                        .bodyValue(record))
                .onErrorResume(
                    LegacyBusyException.class,
                    error -> overloaded())
                .onErrorResume(
                    RejectedExecutionException.class,
                    error -> overloaded());
    }

    Mono<ServerResponse> stream(ServerRequest request) {
        String raw = request.queryParam("ids")
                .orElse("");

        List<String> ids = Arrays.stream(
                raw.split(",", -1))
                .map(String::trim)
                .toList();

        if (ids.isEmpty() || ids.size() > 8
                || ids.stream().anyMatch(id ->
                    !id.matches("[A-Za-z0-9-]{1,16}"))) {
            return invalidIds();
        }

        Flux<LegacyRecord> records =
                Flux.fromIterable(ids)
                    // Concurrency per HTTP response = 2.
                    // Preserves order even if blocking calls finish out of order.
                    .flatMapSequential(service::fetch, 2);

        return ServerResponse.ok()
                .contentType(MediaType.APPLICATION_NDJSON)
                .body(records, LegacyRecord.class);
    }
}
```

**Java structure:** `IsolationApplication` is the sole public class in a single Java 17 file; the package-private records/classes in the same package allow Spring component scanning to detect `IsolationConfig`, `LegacyBlockingGateway`, `LegacyService`, and `LegacyHandler`.

**Safety/semantics notes:**

- `LegacyService.fetch` builds a **lazy** Mono whose callable runs on the custom scheduler upon subscription; the Netty event loop never executes `Thread.sleep(70L)`.
- `LegacyBlockingGateway.fetch` calls `Semaphore.tryAcquire` inside scheduled work so it **never blocks waiting for a permit**. `finally` releases the permit as soon as the actual fetch ends, including on exceptions/interrupts. If a task cancels before starting, no permit was acquired.
- `peakActive`/`activeNow` are local JVM metrics **for tests/illustration**, not cluster-wide. Do not expose them on public production APIs unnecessarily.
- `flatMapSequential(...,2)` bounds concurrency **per HTTP stream** only; other requests share the same scheduler/bulkhead.
- `ids.size() ≤ 8` is a per-request demo quota. The ID regex restricts syntax/length, but does not replace authorization or full request-flood defenses.
- `ServerResponse.body(flux, LegacyRecord.class)` is the WebFlux.fn body writer; `application/x-ndjson` lets the writer emit each record per line.
- `onErrorResume(Rejection...)` handles **single** before `ServerResponse` is constructed. For `stream`, the response may already commit while writing initial records; returning 503 JSON if the Nth task rejects is not guaranteed.
- ``32 queued tasks per backing thread`` is not a 32-task cap for the entire endpoint; with 200 concurrent requests, many may queue before the gateway runs `tryAcquire`.
- If an external SDK ignores interruption, Reactor cancellation cannot force early permit release: the permit tracks the true lifetime of `fetch`.
- If you want a bulkhead that **rejects immediately at HTTP admission** rather than when a worker starts, design cancellation-safe acquisition at the request boundary and independent bounded queues.

### 13.3. Running and Testing via HTTP

Start the app:

```bash
./gradlew bootRun
```

**Fetch a single ID:**

```bash
curl -i \
  'http://localhost:8080/api/legacy/A'
```

When not overloaded, expected body:

```json
{"id":"A","value":"value-A"}
```

**NDJSON stream of multiple IDs:**

```bash
curl -N -i \
  -H 'Accept: application/x-ndjson' \
  'http://localhost:8080/api/legacy/stream?ids=A,B,C'
```

Expected body in input order thanks to `flatMapSequential`:

```text
{"id":"A","value":"value-A"}
{"id":"B","value":"value-B"}
{"id":"C","value":"value-C"}
```

**Invalid ID or too many IDs:**

```bash
curl -i \
  'http://localhost:8080/api/legacy/stream?ids=A,B,not%20allowed'
```

Expected 400 response:

```json
{"code":"INVALID_IDS"}
```

**To truly test overload**, run a load test generating many simultaneous HTTP clients and monitor `activeNow`/`peakActive`, scheduler queues, and rejection counts. A single `curl` command does not prove a bulkhead operates under overload.

The illustrative outputs here are **expected by design**, **not results of actual Gradle or load-test runs**.

## 14. Testing with WebTestClient and StepVerifier

### 14.1. Why Are Both Test Types Needed?

- **`WebTestClient` with RANDOM_PORT:** tests HTTP codecs, routing, statuses, NDJSON framing, and response contents against embedded Reactor Netty.
- **`StepVerifier` with `Mono/Flux`:** tests publisher signals, errors, cancellation, and terminal states without HTTP.
- **Slow-consumer load tests:** measure actual in-flight work, queue depth, latency, CPU, direct memory, and behavior with many concurrent clients.
- **Thread assertions:** supportive only—avoid hardcoding exact thread names; Java 21 virtual threads/scheduler implementations may change naming.

### 14.2. Tests for the Java 17 Demo

Create **`src/test/java/demo/isolation/IsolationApplicationTests.java`**:

```java
package demo.isolation;

import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class IsolationApplicationTests {

    @Autowired
    WebTestClient client;

    @Autowired
    LegacyService service;

    @Autowired
    LegacyBlockingGateway gateway;

    @Test
    void singleReadRespondsWithJson() {
        client.get()
                .uri("/api/legacy/A")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.id").isEqualTo("A")
                .jsonPath("$.value").isEqualTo("value-A");
    }

    @Test
    void invalidIdIsRejectedBeforeSchedulingWork() {
        client.get()
                .uri("/api/legacy/invalid_id")
                .exchange()
                .expectStatus().isBadRequest()
                .expectBody()
                .jsonPath("$.code")
                    .isEqualTo("INVALID_IDS");
    }

    @Test
    void streamingEndpointPreservesRecordOrder() {
        Flux<LegacyRecord> body = client.get()
                .uri("/api/legacy/stream?ids=A,B,C,D")
                .accept(MediaType.APPLICATION_NDJSON)
                .exchange()
                .expectStatus().isOk()
                .expectHeader().contentTypeCompatibleWith(
                        MediaType.APPLICATION_NDJSON)
                .returnResult(LegacyRecord.class)
                .getResponseBody();

        StepVerifier.create(body)
                .expectNext(new LegacyRecord("A", "value-A"))
                .expectNext(new LegacyRecord("B", "value-B"))
                .expectNext(new LegacyRecord("C", "value-C"))
                .expectNext(new LegacyRecord("D", "value-D"))
                .verifyComplete();
    }

    @Test
    void streamRejectsTooManyIds() {
        client.get()
                .uri("/api/legacy/stream?ids=A,B,C,D,E,F,G,H,I")
                .exchange()
                .expectStatus().isBadRequest()
                .expectBody()
                .jsonPath("$.code")
                    .isEqualTo("INVALID_IDS");
    }

    @Test
    void serviceIsLazyUntilSubscriberConsumes() {
        // Constructor creates a Mono; it does not execute Gateway.
        var publisher = service.fetch("LAZY");
        StepVerifier.create(publisher)
                .expectNext(new LegacyRecord(
                        "LAZY", "value-LAZY"))
                .verifyComplete();
    }

    @Test
    void perStreamConcurrencyIsAtMostTwo() {
        StepVerifier.create(
                Flux.fromIterable(List.of(
                    "1", "2", "3", "4", "5", "6"))
                    .flatMapSequential(service::fetch, 2))
                .expectNextCount(6)
                .verifyComplete();

        // Without concurrent unrelated tests, peak is bounded by 2.
        assertTrue(gateway.peakActive() <= 2);
        assertTrue(gateway.activeNow() == 0);
    }
}
```

Run command:

```bash
./gradlew test
```

**Six tests are designed to pass** when run on the right baseline with JUnit's default sequential execution. This is **only expected behavior from API/code review**, with **no claim of Gradle execution**. The `peakActive() <= 2` test relies on shared bean state and assumes no other test runs concurrent background blocking calls; if CI runs tests in parallel or against external traffic, isolate the test context/gateway or use dedicated test instrumentation.

**Weakness to avoid:** `serviceIsLazyUntilSubscriberConsumes` above **only checks output after subscription** and does not directly prove "no side effects before subscription" because it asserts no counter beforehand. A stricter test should inject a fake gateway or spy, call `service.fetch(id)`, assert invocation count = 0, then subscribe and assert count = 1. The current snippet targets successful publisher integration.

### 14.3. Deterministic Concurrency Testing with StepVerifier

To verify concurrency caps without relying on `Thread.sleep` timing or CPU load, build a test source with `AtomicInteger` and async fake tasks using `Mono.defer`/`Sinks.One` to control manually when each inner task completes. Then verify max active subscriptions under `flatMap(...,2)`. Avoid wall-clock assertions like "must finish under 140 ms" since CI load fluctuates.

A simple error-propagation test:

```java
StepVerifier.create(
        Mono.<String>error(
                new LegacyBusyException()))
        .expectError(LegacyBusyException.class)
        .verify();
```

This is a unit-test **fragment**; it only verifies Reactor propagates typed errors. Testing HTTP 503 requires creating a controlled full-bulkhead state and asserting error mapping at the handler or via `WebTestClient`.

## 15. Why Don't Virtual Threads Replace Concurrency Limits?

Starting in Reactor 3.6, `boundedElastic` can execute on virtual threads when running **Java 21+** with the system property enabled:

```properties
reactor.schedulers.defaultBoundedElasticOnVirtualThreads=true
```

This is a **Reactor system property** that must be set early enough (before the shared scheduler initializes); do not assume it is a default Spring Boot `application.properties` binding. In a Java process, it is typically passed as:

```bash
java -Dreactor.schedulers.defaultBoundedElasticOnVirtualThreads=true \
  -jar app.jar
```

On the Java 17 baseline demo, **this option does not enable virtual threads**. On Java 21+, shared `Schedulers.boundedElastic()` can use the virtual-thread-per-task implementation per Reactor config; custom `Schedulers.newBoundedElastic(4,32,...)` has different overloads/semantics, so never assume every custom pool switches to virtual threads automatically.

Virtual threads reduce the cost of parked threads across many blocking calls, yet:

- Database connection counts remain limited.
- Remote services still sustain only finite QPS/concurrency.
- CPU, heap, network, and thread pinning can still bottleneck.
- Queued tasks still need capacity caps and timeouts.
- Blocking native library calls may have different pinning/interruption semantics.
- Never remove bulkheads, admission controls, or observability.

**One million virtual threads do not turn a 10-connection database into a one-million-connection database**. Choose virtual threads based on profiling and JDK/Reactor versions, and prefer reducing root blocking wherever possible.

## 16. Scheduler Lifecycle, Metrics, and Sizing Decisions

### 16.1. Metrics to Measure

| Metric | Meaning |
| --- | --- |
| Active running legacy tasks | Actual in-flight blocking operations |
| Peak in-flight / permitted slots | Whether bulkheads are nearing capacity |
| Scheduler backing thread count | Whether thread caps are hit frequently |
| Scheduler pending queue depth | Whether long blocking calls cause backlogs |
| Oldest queued wait time | Are clients waiting too long despite idle CPU? |
| Scheduled task rejections | Scheduler or queue-cap overload |
| HTTP 503 / 429 / timeout rates | Signs protective policies are triggering |
| Dependency connection pool active/pending | True DB/HTTP client bottlenecks |
| Latency P50/P95/P99 per route | User experience and SLO compliance |
| SSE time-to-first-event/event lag | Whether streaming clients lag due to producer or proxy |
| JVM heap + Netty direct memory | Backpressure/buffer pressure |
| Cancellation vs. task completion | Do tasks keep running after HTTP timeouts? |
| Retry count and downstream QPS | Detecting retry storms |

Reactor supports Micrometer scheduler metrics when integrating `reactor-core-micrometer` and wrapping schedulers with `Micrometer.timedScheduler(...)` per your version's API. If the project does not use the Micrometer module, measure via runtime/JVM and service metrics. Never enable logging of every item/payload under high traffic or with sensitive data.

### 16.2. Pool Sizing Guidelines (No Single Universal Number)

When a legacy downstream handles at most `C` concurrent requests, size scheduler thread caps and per-instance bulkheads considering:

- Total traffic across all instances/clients.
- Actual DB/HTTP connection counts.
- Dependency request latency and timeouts.
- Memory per task/response item.
- Other workloads sharing the scheduler.
- Acceptable queuing delay vs. HTTP deadlines.
- Fairness across tenants/request classes.
- Cold starts/peak bursts, autoscaling, and headroom.

Illustrative thought process:

```text
DB pool = 10 connections
Web app = 2 instances
Need to reserve 4 connections for jobs/admin/migrations

You cannot give each app 10 blocking calls
and assume a peak total of 20 is safe.
Allocate quotas against the service budget + all consumers.
```

These numbers illustrate capacity-planning principles, not a universal optimal formula.

### 16.3. Backpressure Alone Does Not Solve Scheduler Queues

Reactive Streams `request(n)` regulates element counts in the pipeline, yet a scheduled blocking callable can hold a thread for a long time. If downstream requests 1,000 items from `flatMap` with high concurrency, many tasks can flood the scheduler queue. Combine:

- Explicit `flatMap` concurrency.
- Bounded scheduling queues.
- Bulkheads/admission control.
- Demand-aware sources/record limits.
- Response-writer backpressure without unbounded buffers.
- Retry/timeout policies with worker cleanup.

## 17. Security, Resource Ownership, and Production Requirements

1. **Never run blocking crypto/file scanning/server-side requests (SSRF) on the Netty event loop**. If the SDK blocks, isolate it while still enforcing destination URL allowlists.
2. **Never let users choose arbitrary paths/files/DB keys** when exporting via blocking file APIs; validate/authorize before the operation.
3. Enforce **max request body, upload bytes, response record size, ID counts, and concurrency** per tenant and endpoint.
4. Never return raw `RejectedExecutionException`, JDBC errors, or stack traces in API responses.
5. Never log passwords, Authorization headers, Cookies, signed URLs, or PII in scheduler task MDC.
6. `ThreadLocal`/MDC **do not propagate automatically across scheduling boundaries**. Use Reactor Context and version-appropriate context-propagation/tracing integration, or pass explicit immutable context to legacy libraries when needed.
7. Cancellation must release DB connections, streams, and buffers cleanly per lifecycle, without assuming interrupts always work.
8. When multiple tenants share a pool, one tenant can starve the queue; enforce per-tenant fairness/admission.
9. Bulkhead rejections do not replace rate limiting/authorization; an HTTP client can still spam tiny requests to fill queues.
10. For side effects (payments, emails, jobs), enforce idempotency/reconciliation even with bounded schedulers.
11. Trigger circuit breakers on dependency failures/latency—not on 400 client input errors.
12. Use meaningful health checks and alerts so infinite auto-retries do not mask overload.

## 18. Troubleshooting: Symptoms and Root Causes

| Symptom | Likely Cause | Action |
| --- | --- | --- |
| Low WebFlux throughput despite idle CPU | JDBC/SDK/`Thread.sleep` on event loop | Profile thread dumps, isolate blocking source |
| `Mono.just(blockingCall())` still blocks | Computation happened before Mono | `Mono.fromCallable(...).subscribeOn(...)` |
| `subscribeOn` after `Mono.just` does not help | Blocking call already executed | Move blocking work inside callable |
| `publishOn` at end of chain does not help | Blocking `map` ran before boundary | Move boundary before `map` or wrap inner Mono |
| `block()` throws `IllegalStateException` | Reactor non-blocking thread | Remove `block()`, use reactive composition |
| CPU-bound code on `boundedElastic` causes queuing | Wrong pool for compute | Move short compute to `parallel`/dedicated compute pool |
| Pool has many pending tasks | Slow downstream, overly loose cap/queue | Bulkhead, timeouts, fail-fast, metrics |
| Global pool starves during exports | Workloads sharing `boundedElastic` | Dedicated scheduler / job queue |
| `flatMap(...,4)` still results in 100 calls | Many independent HTTP requests | Global semaphore/admission + pool limits |
| NDJSON stream results arrive out of order | Using `flatMap` to merge results | `flatMapSequential`/`concatMap` |
| NDJSON appears only after many seconds | Proxy/codec/client buffering | `curl -N`, inspect proxy, measure first-event timings |
| HTTP times out but DB query keeps running | Driver ignores cancel/interrupt | Configure driver timeouts and DB statement cancellation |
| `doFinally` releases permit yet overload exceeds cap | Task keeps running after client cancels | Release permit inside the actual blocking task |
| 503s spike with many clients | Scheduler/bulkhead rejections | Check queue/dependency latency/QPS |
| Retry storm | Clients retry immediately forever | Backoff, jitter, `Retry-After`, idempotency |
| CPU/heap grows from `collectList()` | Buffering full stream | Stream responses / bounded batches |
| Client closes tab, task keeps running | Non-instant cancellation or SDK ignores interrupt | Track task lifecycle, use SDK cancel APIs |
| Mid-stream failure still returns status 200 | Response already committed | Error protocol, partial-stream contract |
| Large queued task count but unpredictable memory | Varying item/task metadata and buffers | Monitor queue bytes/memory and heap profiles |
| DB still bottlenecks with virtual threads enabled | DB/HTTP connection cap unchanged | Size bulkheads/pools to match dependency |

### Diagnostic Workflow

1. Use metrics/thread dumps to find **which thread blocks and in which method**.
2. Confirm runtime uses WebFlux/Netty, not accidentally MVC.
3. Search handlers/operators for `block()`, `Thread.sleep`, JDBC, and synchronous HTTP SDKs.
4. Verify blocking code sits **inside a lazy `fromCallable`**.
5. Check which stages come before vs. after `subscribeOn`/`publishOn`.
6. Check `flatMap` concurrency per stream and simultaneous HTTP request counts.
7. Inspect scheduler caps/queues, DB/HTTP client pools, and bulkhead permits.
8. Verify real client/driver timeouts and cancellation propagation.
9. If streaming is slow, separate producer, codec, proxy, and browser behavior.
10. Load test many concurrent clients and check heap/direct memory, QPS, p99, rejections, and resource cleanup.

## 19. Comparing Architectural Choices

| Need | Option to Consider | What to Guard |
| --- | --- | --- |
| One short blocking legacy SDK call | `Mono.fromCallable` + `boundedElastic` | Timeouts, pool caps |
| Legacy SDK shared across multiple routes | Dedicated `newBoundedElastic` bean | Queue/rejections, cross-route fairness |
| Batch of IDs from a request | `flatMap(mapper,n)` | Per-stream cap, total count/bytes |
| Results must keep order | `flatMapSequential` or `concatMap` | Out-of-order buffering |
| JVM-wide global concurrency | Non-blocking bulkhead/semaphore | Permit lifetime, cancellation |
| Across multiple nodes | Gateway/distributed quotas, downstream pool policies | Never rely on local semaphores |
| Blocking DB needing a reactive API | Temporary `boundedElastic` isolation | Migrate to R2DBC when suitable |
| Workloads lasting minutes | Background job/queue + 202/GET status | Durable state, retries, DLQ |
| Streaming live updates without losing events | Broker + SSE/WebSocket | Replay, ordered IDs, slow consumers |
| Streaming needing only latest state | `onBackpressureLatest`/coalescing | Tolerates losing intermediate updates |
| Native async client exists | WebClient / reactive DB driver | Connection pooling, cancellation |

An API that does not need real-time delivery and takes minutes to generate a report is often better served by `POST /exports` returning `202 Accepted` + a job ID, followed by downloading the finished file; holding thousands of HTTP streaming requests on blocking workers is rarely optimal.

## 20. Important Version Differences

| Version | Notes |
| --- | --- |
| Reactor 3.3+ | `boundedElastic` introduced to replace unbounded-thread `elastic` |
| Reactor 3.6/3.7 | `boundedElastic` adds optional virtual-thread execution on Java 21+ via system property |
| Spring Framework 6.2 / Boot 3.5 | Java 17 baseline; WebFlux.fn returns `Mono<ServerResponse>` and supports NDJSON/SSE |
| Java 17 | Lacks production Java virtual threads as in Java 21 |
| Java 21+ | Can use Reactor `boundedElastic` virtual threads per configuration/conditions |
| Spring Framework 7 / Boot 4 | Check dependency/API/test-module/config migrations; core concepts remain applicable |

Do not assume Boot's `spring.threads.virtual.enabled=true` automatically switches shared Reactor `boundedElastic()` to virtual threads in every version. Read the exact Reactor Javadoc/system property and test actual thread/capacity behavior.

## 21. Production Checklist

- [ ] No blocking JDBC/HTTP/file operations directly on the Netty event loop.
- [ ] Blocking sources wrapped in lazy `Mono.fromCallable`/`fromRunnable` with appropriate `subscribeOn`.
- [ ] No `block()`/`blockLast()` calls inside WebFlux handlers.
- [ ] No new scheduler created per request; proper bean lifecycle and `dispose`.
- [ ] Dedicated schedulers per downstream where workload isolation is needed.
- [ ] Pool thread/queue caps sized to service capacity, not treating defaults as SLOs.
- [ ] Explicit `flatMap` concurrency declared for batches/streams.
- [ ] Global HTTP/dependency concurrency protected by dedicated bulkheads/admission control.
- [ ] No `Semaphore.acquire` on the event loop; permits released on actual task completion.
- [ ] Driver/socket/connection timeouts paired with sensible deadlines and `Retry-After`.
- [ ] Cancellations/timeouts never cause duplicate side effects or leaked resources.
- [ ] Proper NDJSON/SSE framing; never assume late error status changes after commit.
- [ ] Streaming producers and consumers have bounded queues and backpressure policies.
- [ ] Rate limits/tenant quotas and authn/authz do not rely on the scheduler.
- [ ] Logs/metrics never expose credentials, PII, or raw rejected payloads.
- [ ] Metrics cover scheduler pending, active, rejections, p95/p99, and dependency pool usage.
- [ ] Unit `StepVerifier` and `WebTestClient` integration tests plus concurrent-client load tests.
- [ ] Tested through real proxies for slow clients, reconnects, timeouts, and disconnects.
- [ ] Migration plan toward non-blocking drivers or durable background jobs as load grows.

## 22. Self-Assessment Exercises

1. Why does `Mono.just(legacy.read())` still block the event loop even with `subscribeOn(boundedElastic())` after it?
2. Rewrite that code using `Mono.fromCallable` and explain when the callable executes.
3. How does `Schedulers.parallel()` differ from `boundedElastic()` in purpose? What is dangerous about running JDBC on `parallel`?
4. Compare the effects of `subscribeOn` vs. `publishOn` on a `map` operator containing a blocking call.
5. With `flatMap(...,4)` on an endpoint and 100 concurrent clients, what is the maximum number of inner subscriptions without a global limit?
6. Does `Schedulers.newBoundedElastic(4,32,"io")` mean the whole app queues at most 32 tasks? Check the Javadoc.
7. Why should you never create `newBoundedElastic` per HTTP request?
8. If `Semaphore.tryAcquire` runs **inside the scheduled callable**, are previously queued tasks rejected immediately at HTTP admission?
9. Why is `Semaphore.acquire` on the Netty event loop an anti-pattern?
10. If HTTP times out and `doFinally` releases the permit while the blocking query is still running, what goes wrong?
11. How do `flatMapSequential` and `concatMap` differ in concurrency, ordering, latency, and buffering?
12. An NDJSON stream returns 100 items, and item 40 fails after 39 items were written. Can the HTTP status be changed to 500/503?
13. When an EventSource client closes its tab, does a blocking SDK stop immediately? Explain cancellation limitations.
14. An app has 4 instances, each with a bulkhead of 3. How many total DB calls can occur? What is needed for a global limit of 6?
15. If a DB pool has only 10 connections, is leaving `boundedElastic` at its high default thread count necessarily safe?
16. When should `Retry-After` be returned? Distinguish 429 (quota) from 503 (capacity).
17. How do you combine timeouts, circuit breakers, and retries without triggering a retry storm?
18. On Java 21, which property enables virtual threads for Reactor `boundedElastic`? Does it solve DB connection limits?
19. If a single response record is 5 MB, what memory aspect does concurrency 2 protect and what does it leave unprotected?
20. Add a test firing 20 concurrent requests verifying `activeNow() ≤ 3` and appropriate overload responses without relying on wall-clock timing.
21. Design a streaming endpoint behind a buffering NGINX proxy; why doesn't `curl -N` against the origin necessarily reflect real browser UX?
22. Choose among reactive WebClient, `boundedElastic`-wrapped RestTemplate, R2DBC, and background jobs for three workloads: fast lookups, long reports, and multi-GB imports.
23. If downstream takes 5 seconds while WebFlux times out at 500 ms, how long might workers/DB connections stay occupied?
24. If logs have a `ThreadLocal` traceId in the handler that disappears on a `boundedElastic` worker, how do Reactor Context/tracing integrations solve it?
25. How do you expose custom dedicated scheduler metrics without leaking user IDs into metric tags?
26. Why doesn't unbounded `onBackpressureBuffer()` solve blocking pool saturation?

## 23. Official Documentation and Reading Guide

- [Project Reactor 3.7 — Threading and Schedulers](https://docs.spring.io/projectreactor/reactor-core/docs/3.7.x/reference/html/coreFeatures/schedulers.html): scheduler differences, `publishOn`/`subscribeOn`, `boundedElastic` threads/queues, and virtual threads.
- [Project Reactor 3.7 — FAQ: Wrap a synchronous blocking call](https://docs.spring.io/projectreactor/reactor-core/docs/3.7.x/reference/html/faq.html): `Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())`.
- [Project Reactor 3.7 — Schedulers Javadoc](https://projectreactor.io/docs/core/3.7.8/api/reactor/core/scheduler/Schedulers.html): `newBoundedElastic`, thread/queue caps, global defaults, virtual threads property.
- [Project Reactor 3.7 — Flux Javadoc](https://projectreactor.io/docs/core/3.7.8/api/reactor/core/publisher/Flux.html): `flatMap`, `flatMapSequential`, `concatMap`, concurrency/prefetch.
- [Project Reactor 3.7 — Mono Javadoc](https://projectreactor.io/docs/core/3.7.8/api/reactor/core/publisher/Mono.html): `fromCallable`, `fromRunnable`, `subscribeOn`, `timeout`, and cancellation.
- [Spring Framework 6.2 — WebFlux Reactive Core](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/reactive-spring.html): non-blocking I/O, event loops, backpressure, reactive streams.
- [Spring Framework 6.2 — WebFlux Functional Endpoints](https://docs.spring.io/spring-framework/reference/6.2/web/webflux-functional.html): RouterFunction, HandlerFunction, `ServerResponse.body`/NDJSON.
- [Spring Framework 6.2 — WebFlux HTTP Streaming](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-methods/responsebody.html): reactive streaming media types, codecs, and flushing.
- [Spring Framework — WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html): HTTP tests for streaming and reactive response bodies.
- [Spring Boot 3.5 — Reactive Web Applications](https://docs.spring.io/spring-boot/3.5/reference/web/reactive.html): WebFlux/embedded Netty setup.
- [Reactive Streams JVM Specification](https://www.reactive-streams.org/): `request(n)`, cancellation, and publisher/subscriber contracts.
