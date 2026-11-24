# Choosing flatMap Concurrency Limits Based on Downstream Resources

**Module:** Spring Framework – reactive  
**Parent Topic:** Performance and Load  
**Objective:** Choose concurrency limits for Reactor inner Publishers based on database capacity, connection pools, partner APIs, CPU, and memory; distinguish concurrency from prefetch, rate limiting, and global bulkheads; verify limits with tests and metrics.

## 1. The Problem to Solve

An endpoint receives a list of 500 order IDs and calls a partner service for each ID. If written as:

```java
Flux<Result> results = ids.flatMap(partnerClient::fetch);
```

sub-requests may be subscribed to concurrently according to Reactor's default settings. If upstream emits quickly, the partner service may receive too many concurrent requests, saturating the connection pool, growing the pending queue, stretching latency, and causing requests to time out.

You can cap the number of sub-operations processed concurrently within a single pipeline:

```java
Flux<Result> results = ids.flatMap(
        partnerClient::fetch,
        8,
        1);
```

The 8 is concurrency: the maximum number of inner Publishers in-flight. The 1 is prefetch: the amount of demand requested upfront from each inner Publisher. The two parameters mean different things. Do not pick concurrency merely because a number looks small; you need to know which resource each inner holds, what the resource's limit is, and how many parent requests run concurrently.

**Rule of thumb:** set concurrency according to the actual downstream resource bottleneck, then verify with representative load and metrics. Do not tune mechanically from CPU core count or thread pool size.

## 2. What Does flatMap Concurrency Actually Limit?

`Flux.flatMap(mapper, concurrency, prefetch)` does three things:

1. Receives an item from upstream and calls the mapper to create an inner Publisher.
2. Eagerly subscribes to inner Publishers, allowing multiple inners to run concurrently.
3. Merges the results of inner Publishers into one downstream Flux; values may interleave and input order is not preserved.

| Parameter | Meaning | Impact |
|---|---|---|
| `concurrency` / `maxConcurrency` | Maximum number of inner Publishers subscribed and processed concurrently | Caps in-flight sub-operations within a single subscription |
| `prefetch` | Number of items requested upfront from each inner Publisher | Tunes demand and buffering per inner, affecting memory and throughput |

Concurrency also determines the initial demand `flatMap` signals upstream. When an inner completes, the operator can request the next source element to open a new slot. This is how the operator coordinates backpressure with the inner count limit.

Example:

```java
Flux.range(1, 100)
        .flatMap(this::callPartner, 6, 1);
```

Within a single subscription, `flatMap` keeps at most six active inner Publishers. When one inner finishes, that slot is reused for the next element. If the mapper returns a `Mono`, each inner typically represents one sub-request. If it returns a `Flux`, one inner can emit multiple items; in that case prefetch has clearer significance.

### 2.1. Concurrency Is Not Thread Count

`flatMap(..., 8, ...)` does not mean Reactor creates eight separate threads. Concurrency is the number of in-flight inner subscriptions. Publishers may use the event loop, I/O callbacks, schedulers, or their own drivers.

`flatMap` also does not automatically switch work onto another scheduler. With WebClient, I/O is non-blocking; concurrency caps running sub-requests, without creating eight threads to wait on sockets.

If the mapper calls a blocking function, it can block the thread emitting signals. Isolate blocking calls while still bounding the number of operations:

```java
Flux<Result> results = ids.flatMap(
        id -> Mono.fromCallable(() -> legacyBlockingLookup(id))
                .subscribeOn(Schedulers.boundedElastic()),
        8,
        1);
```

This isolates a legacy blocking API; it does not make that API non-blocking. `Schedulers.boundedElastic` has its own thread and queue limits, so both limits must be accounted for.

### 2.2. Concurrency Is Not a Rate Limit

Concurrency caps how many operations run at the same time. A rate limit caps how many operations start within a time window.

For example, eight concurrent requests averaging 200 ms each can complete around 40 requests/second in steady state. Yet if the partner enforces at most 10 requests/second, `flatMap(..., 8)` does not automatically honor that quota. You need a token bucket, rate limiter, or separate pacing mechanism.

### 2.3. Concurrency Is Not a Global Bulkhead

A limit of 8 applies only to one subscription of that operator. If 30 concurrent HTTP requests each build a pipeline with `flatMap(..., 8)`, total sub-operations can approach 240.

To protect shared pools or upstreams, add a global limit: a bulkhead, admission control, pool/queue bounds, or a shared coordination point. Do not use a blocking semaphore on the event-loop; choose a reactive bulkhead or non-blocking acquire mechanism.

## 3. Choosing an Operator by Ordering and Concurrency

| Operator | Concurrent Inners | Output Order | Characteristics |
|---|---:|---|---|
| `flatMap(mapper, C, P)` | Up to C | Source order not guaranteed | Merges as soon as an inner emits; fits independent work |
| `flatMapSequential(mapper, C, P)` | Up to C | Preserves source order | Subscribes inners eagerly but buffers later inner results if an earlier inner is slow |
| `concatMap(mapper, P)` | One inner at a time | Preserves source order | Sequential, easy to control resources and order-dependent side effects |

Suppose request A takes 500 ms and B takes 50 ms. `flatMap` may emit B's result before A's. `flatMapSequential` still subscribes to B while A is running, yet holds B's result in a queue until A finishes emitting. `concatMap` subscribes to B only after A completes.

```java
// Independent work, no ordering required.
Flux<Result> merged = ids.flatMap(this::fetch, 8, 1);

// Can run in parallel, but must emit in source order.
Flux<Result> ordered = ids.flatMapSequential(this::fetch, 8, 1);

// Must complete each operation before starting the next.
Flux<Result> serial = ids.concatMap(this::writeSequentially, 1);
```

Use `concatMap` when side effects must occur in order or when steps share a resource that does not support parallel operations. Use `flatMapSequential` when inners can run in parallel yet output must stay ordered; watch out for head-of-line blocking and queue memory.

## 4. Identifying Resource Bottlenecks

Before choosing C, list what each inner Publisher uses:

| Work in Mapper | Occupied Resource | Limits to Know |
|---|---|---|
| WebClient partner call | Connection, pending acquire slot, partner quota | Max connections, pool queue, API in-flight/rate quota |
| Independent R2DBC query | DB connection, transaction, server execution slot | Pool size, DB connection budget, query capacity |
| File write | File handle, disk bandwidth, buffers | Concurrent files, throughput, temporary space |
| CPU-heavy decode/transform | CPU time, heap, object allocation | CPU cores, CPU quota, allocation/GC |
| Multi-tier service call | Multiple pools and timeouts | Smallest bottleneck across the entire chain |
| Message publish | Producer buffer, broker quota | Pending sends, broker throughput, retry queue |

One inner Publisher can hold multiple resources throughout its lifecycle. For instance, if a transaction opens a connection and then waits on a slow HTTP request, the DB connection may remain held. Do not merely count HTTP calls; examine which resources are held and for how long.

Practical formula:

```text
C_local <= min(
    downstream_inflight_budget,
    connection_budget_per_pipeline,
    memory_budget,
    CPU_or_scheduler_budget,
    business_policy_limit
)
```

This sets an initial ceiling, not a throughput prediction formula. Afterward, account for concurrent pipelines/requests to calculate global capacity.

## 5. Connection Pool Sizing Example

Suppose an R2DBC pool has 40 connections:

- 6 connections are reserved as headroom for health checks, admin tasks, and load spikes.
- 10 connections are expected to be used by other business flows.
- The remaining budget for batch lookup is 24 connections.

If a single pipeline issues one independent query per inner and each inner holds one connection, the initial limit could be 24 or lower. If queries can run long, starting at 8–12 and measuring is safer.

However, if 20 HTTP requests arrive simultaneously, each with `flatMap(..., 12)`, theoretical demand could hit 240 queries. A local concurrency of 12 does not protect a global 40-connection pool. Add a global bulkhead or partition the budget by workload type.

```text
Pool capacity                    = 40
Operational reserve              = 6
Other workload budget            = 10
Maximum budget for this workload = 24

Per-request flatMap concurrency  = 4
Global bulkhead for this workload = 24
```

Here, local `flatMap` = 4 bounds per-request fan-out; global bulkhead = 24 caps total activity for that workload group.

### 5.1. Transaction-Bound Connections

Inside an R2DBC reactive transaction, multiple queries may share a connection bound in the Reactor Context. A single connection does not inherently support multiple independent concurrent queries. The driver/database may require sequential operations or restrict concurrency on the same connection.

When multiple steps must run within the same transaction and same connection, you typically use:

```java
return commands.concatMap(repository::applyChange);
```

Do not raise `flatMap` concurrency to 8 just to run eight queries simultaneously inside one transaction. If business logic permits independent transactions, they can run in parallel, but each transaction consumes its own pool resource and needs a global budget.

## 6. Estimating with Duration and Little's Law

Little's Law describes an average relationship:

```text
L = λ × W
```

Where L is the average number of in-flight operations, λ is average throughput (operations/second), and W is the average time an operation spends in the system (seconds).

For example, to handle 80 requests/second with 150 ms average latency:

```text
L = 80 × 0.150 = 12 concurrent requests (average)
```

This states that achieving that throughput in steady state involves roughly 12 in-flight requests on average. It does not mean setting concurrency to exactly 12 guarantees 80 requests/second. You must still account for tail latency, errors, pool waits, downstream capacity, and load variance.

Safe process:

1. Measure average and p95/p99 latency at representative load.
2. Estimate the in-flight operations needed for target throughput.
3. Compare against connection/API/CPU/memory budgets.
4. Start below resource thresholds and ramp up in load tests.
5. Stop increasing when throughput stops rising while latency, queues, timeouts, or GC grow.

Do not use concurrency to compensate for an already-overloaded downstream. When queues and latency climb, raising C can worsen the condition.

## 7. Choosing Concurrency for WebClient and Partner APIs

With WebClient, each inner is typically one HTTP call:

```java
Flux<Product> products = productIds.flatMap(
        id -> webClient.get()
                .uri("/products/{id}", id)
                .retrieve()
                .bodyToMono(Product.class),
        8,
        1);
```

Check these limits:

- Connection pool `maxConnections`.
- Pending acquire queue and `pendingAcquireTimeout`.
- Partner API in-flight limit.
- Rate quota per API key/tenant.
- Response size, codec aggregation, and memory.
- Connect/response timeouts and overall business deadline.
- Retry/backoff when the partner returns transient errors.

If the pool has 20 connections shared across other flows, do not allocate all 20 slots to this pipeline. If the partner allows only 5 concurrent requests, workload concurrency must not exceed a budget of 5 even if the client pool has 100 connections.

A connection pool is a transport-level guard, not a substitute for concurrency limits in business flows. If the pool queue is unbounded or too long, requests can pile up and retain significant state before acquiring a connection.

## 8. CPU-Bound and Blocking Work

If the mapper performs heavy CPU computation, concurrency higher than available cores usually will not make computation faster. It can increase context switching, allocations, and GC. Consider `Schedulers.parallel()`/`ParallelFlux` or `publishOn` with an appropriate scheduler, then benchmark against actual CPU quotas.

```java
Flux<Score> scores = ids.flatMap(
        id -> Mono.fromCallable(() -> expensiveScore(id))
                .subscribeOn(Schedulers.parallel()),
        4,
        1);
```

If calling blocking JDBC, blocking filesystem I/O, or a synchronous SDK, do not run directly on the Netty event loop. Isolate with `Schedulers.boundedElastic()`:

```java
Flux<Value> values = ids.flatMap(
        id -> Mono.fromCallable(() -> blockingSdk.lookup(id))
                .subscribeOn(Schedulers.boundedElastic()),
        6,
        1);
```

The limit of 6 bounds tasks from this pipeline; the scheduler still has shared thread/queue limits. If multiple endpoints share boundedElastic, consider global pressure. Do not raise concurrency to thousands and leave thousands of requests waiting in the scheduler queue.

## 9. Prefetch and Memory

`prefetch` is not a second concurrency setting. With `flatMap(mapper, C, P)`, Reactor can keep at most C inner Publishers in-flight; each inner can be requested upfront up to P elements per operator semantics. As inners emit data, the operator replenishes demand via internal mechanics.

Rough memory estimate for multi-item inner Publishers:

```text
Approximate queued payload memory
    ≈ concurrency × prefetch × average item size
```

Example: C=8, P=4, average decoded item size 256 KiB:

```text
8 × 4 × 256 KiB = 8 MiB
```

This estimates only payloads in the corresponding queues; it excludes object overhead, outer queues, operator queues, decoder buffers, connection buffers, response aggregation, and data retained by business logic.

How to choose:

- Inner is `Mono<T>` emitting one item: prefetch usually has less impact since the inner is not a long stream.
- Inner is a multi-item `Flux<T>`: lower prefetch if items are large or downstream is slow.
- Inner needs high throughput with small items: prefetch can be raised after measuring.
- Large/untrusted payloads: prefer streaming and byte budgets; do not rely solely on lowering prefetch.

In many Reactor inner operators, a common default prefetch is 32, though defaults can vary by operator/version. Specify it explicitly when the memory profile matters and check the Javadoc for your exact Reactor version.

## 10. Nested Concurrency Can Multiply Load

Two nested `flatMap` operators:

```java
Flux<Result> results = accounts.flatMap(
        account -> account.getOrders().flatMap(
                this::fetchDetails,
                5,
                1),
        8,
        1);
```

If each account has enough orders, the pipeline can open up to 8 × 5 = 40 inner detail calls for a single subscription. That is the theoretical limit of nested fan-out, not 8 or 5 in isolation.

If each HTTP request runs that pipeline and 10 HTTP requests run concurrently, total demand can climb to 400 detail calls. Account for all fan-out levels and active parent requests.

A simpler approach is flattening items into a single stream and capping at the shared resource call site, or applying a global bulkhead for downstream. When flattening is not possible, document each tier's budget and run combined load tests.

## 11. How Retry, Timeout, and Error Handling Affect Slots

### 11.1. Retries Hold Inner Slots During Backoff

```java
Flux<Result> results = ids.flatMap(
        id -> fetch(id)
                .retryWhen(Retry.backoff(
                        2,
                        Duration.ofMillis(100))),
        8,
        1);
```

An inner Publisher has not completed while waiting to retry, so its concurrency slot stays occupied. This is often helpful to avoid opening too much extra work while upstream is failing. However, retries can amplify load without backoff, jitter, attempt caps, and deadlines.

Retry only appropriate transient errors. For POST requests with side effects, require an idempotency key or deduplication mechanism; a timeout does not prove the partner did not process the request.

### 11.2. Timeouts and Errors

```java
Flux<Result> results = ids.flatMap(
        id -> fetch(id)
                .timeout(Duration.ofSeconds(2)),
        8,
        1);
```

When an inner times out, it emits an error and `flatMap` fails fast by default: the error can terminate the outer sequence and cancel remaining inners. To handle errors per item, place a fallback inside the mapper:

```java
Flux<Outcome> results = ids.flatMap(
        id -> fetch(id)
                .map(Outcome::success)
                .onErrorResume(error ->
                        Mono.just(Outcome.failure(id))),
        8,
        1);
```

A failed item then becomes `Outcome.failure` while other items continue. Do not swallow all errors blindly; classify timeouts, validation errors, 4xx, 5xx, and non-retryable failures.

`flatMapDelayError(mapper, C, P)` delays error emission until active inners/backlog are processed according to operator semantics. It helps collect multiple errors, yet work can keep consuming resources after the first failure. It is not an overload protection mechanism.

## 12. Backpressure and Mapper Laziness

`flatMap` uses demand to avoid opening infinite inner Publishers simultaneously. However, the source may be a hot publisher, self-emitting callback, or an SDK that ignores Reactive Streams. When the source cannot slow down, apply bounded buffer/drop/error policies and quotas.

The mapper should create work lazily:

```java
Flux<Result> results = ids.flatMap(
        id -> Mono.defer(() -> partnerClient.fetch(id)),
        8,
        1);
```

If `partnerClient.fetch(id)` sends the request immediately when called rather than upon subscription, it can trigger side effects before the operator manages the subscription. Check the API/SDK contract; wrapping with `defer` will not fix an SDK that already executes side effects before returning a Publisher.

`limitRate` shapes batched upstream requests; it does not replace limiting active inners. For fan-out, set `flatMap` concurrency right where child operations are created.

## 13. Externalizing Limits into Configuration

Do not hard-code concurrency numbers across services. Move values into per-workload configuration:

```properties
app.partner.max-concurrency=8
app.partner.prefetch=1
app.database.batch-concurrency=4
app.database.batch-prefetch=1
```

A configuration class can validate them:

```java
@ConfigurationProperties(prefix = "app.partner")
@Validated
public record PartnerProperties(
        @Min(1) @Max(32) int maxConcurrency,
        @Min(1) @Max(16) int prefetch) {
}
```

This is a Spring Boot snippet requiring configuration properties scanning or registration via `@EnableConfigurationProperties`. Choose max values based on measured capacity rather than assuming `@Max(32)` means 32 is safe.

When changing configuration in production, roll out in a controlled manner and watch connection pools/latency. Do not change concurrency under heavy load without knowing whether previously constructed pipelines retain the old values.

## 14. Runnable Java 17+ Example: Measuring Active Inner Publisher Limits

A standalone example using Reactor Core. Each ID creates an inner `Flux` emitting three result parts with a short delay. The service tracks active inners and the maximum observed count. Tests verify all data is processed without ever exceeding configured concurrency.

**Project structure:**

```text
flatmap-concurrency-demo/
├── pom.xml
└── src/
    ├── main/java/demo/PartnerBatchService.java
    └── test/java/demo/PartnerBatchServiceTest.java
```

### 14.1. pom.xml

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

    <groupId>demo</groupId>
    <artifactId>flatmap-concurrency-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-core</artifactId>
        </dependency>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
```

The Spring Boot parent manages compatible Reactor versions. The project uses Java 17; no HTTP server is needed because the goal is testing `flatMap` semantics directly.

### 14.2. PartnerBatchService.java

```java
package demo;

import java.time.Duration;
import java.util.concurrent.atomic.AtomicInteger;

import reactor.core.publisher.Flux;

public final class PartnerBatchService {

    private final int maxConcurrency;
    private final int prefetch;

    private final AtomicInteger active = new AtomicInteger();
    private final AtomicInteger maxObserved = new AtomicInteger();

    public PartnerBatchService(
            int maxConcurrency,
            int prefetch) {

        if (maxConcurrency < 1) {
            throw new IllegalArgumentException(
                    "maxConcurrency must be positive");
        }
        if (prefetch < 1) {
            throw new IllegalArgumentException(
                    "prefetch must be positive");
        }

        this.maxConcurrency = maxConcurrency;
        this.prefetch = prefetch;
    }

    public Flux<Integer> fetchAll(int itemCount) {
        if (itemCount < 0) {
            throw new IllegalArgumentException(
                    "itemCount must not be negative");
        }

        return Flux.range(1, itemCount)
                .flatMap(
                        this::fetchThreeParts,
                        maxConcurrency,
                        prefetch);
    }

    private Flux<Integer> fetchThreeParts(int id) {
        return Flux.defer(() -> {
                    int now = active.incrementAndGet();
                    maxObserved.accumulateAndGet(
                            now, Math::max);

                    return Flux.range(1, 3)
                            .delayElements(
                                    Duration.ofMillis(10))
                            .map(part -> id * 10 + part);
                })
                .doFinally(signal ->
                        active.decrementAndGet());
    }

    public int activeCalls() {
        return active.get();
    }

    public int maxObservedConcurrency() {
        return maxObserved.get();
    }
}
```

Key points:

- `Flux.defer` increments the counter only when an inner is actually subscribed to.
- Each inner represents a downstream operation and emits three items.
- `flatMap` receives `maxConcurrency` and `prefetch` from the constructor.
- `doFinally` decrements the counter on complete, error, or cancel.
- `maxObserved` is the highest active count observed during the run, not a self-declared configuration value.

In a real application, replace `Flux.range(...).delayElements(...)` with publishers from WebClient, R2DBC, or a reactive SDK. Do not use `Thread.sleep` to simulate I/O on the event loop.

### 14.3. PartnerBatchServiceTest.java

```java
package demo;

import org.junit.jupiter.api.Test;

import reactor.test.StepVerifier;

import static org.assertj.core.api.Assertions.assertThat;

class PartnerBatchServiceTest {

    @Test
    void activeInnerPublishersNeverExceedConfiguredLimit() {
        int concurrencyLimit = 4;
        PartnerBatchService service =
                new PartnerBatchService(concurrencyLimit, 1);

        StepVerifier.create(service.fetchAll(20))
                .expectNextCount(60)
                .verifyComplete();

        assertThat(service.maxObservedConcurrency())
                .isGreaterThan(0)
                .isLessThanOrEqualTo(concurrencyLimit);

        assertThat(service.activeCalls()).isZero();
    }

    @Test
    void emptyInputDoesNotStartAnyInnerPublisher() {
        PartnerBatchService service =
                new PartnerBatchService(4, 1);

        StepVerifier.create(service.fetchAll(0))
                .verifyComplete();

        assertThat(service.maxObservedConcurrency())
                .isZero();

        assertThat(service.activeCalls()).isZero();
    }

    @Test
    void constructorRejectsInvalidLimits() {
        org.junit.jupiter.api.Assertions.assertThrows(
                IllegalArgumentException.class,
                () -> new PartnerBatchService(0, 1));

        org.junit.jupiter.api.Assertions.assertThrows(
                IllegalArgumentException.class,
                () -> new PartnerBatchService(4, 0));
    }
}
```

Run from the project directory with JDK 17+ and Maven:

```bash
mvn test
```

**Expected result:** three tests PASS; Maven exit code `0`.

- The first test receives 60 elements (20 inners × 3 items), confirming maximum active inners never exceed 4 and zero inners remain active after completion.
- The second test confirms empty input creates no inners.
- The third test confirms invalid concurrency/prefetch settings are rejected.

Do not assert that `maxObservedConcurrency()` always equals exactly 4; scheduling and timing can yield a lower reading. What matters is proving it stays within 1–4 when work exists.

## 15. Real-System Testing and Metrics

The test above proves a single publisher honors the operator cap in-process. It does not prove the database pool or partner API avoids overload when multiple requests run concurrently.

An integration/load test suite should measure:

1. Active inner count per workload.
2. Active connections and pending acquires in the pool.
3. Concurrent requests observed by downstream.
4. Latency p50/p95/p99, throughput, and error rate.
5. Timeouts, 429s, 5xx responses, retries, and cancellations.
6. Queue depth, heap, allocation rate, and GC pauses.
7. Behavior under multiple concurrent parent HTTP requests.
8. Behavior when downstream slows down or drops connections.
9. Behavior when one inner fails mid-batch.
10. Total resources after request completion/cancellation.

Use a mock test server with concurrency limits or a test database with an explicit pool size. To prove a global cap, run multiple concurrent parent requests and measure total active operations at the shared resource; testing a single subscription in isolation is not enough.

| Symptom | Likely Cause | Action |
|---|---|---|
| Pool pending acquires climb continuously | C exceeds connection budget or queries are too slow | Lower C, set queue/acquire timeouts, optimize queries |
| Upstream returns 429 | Quota or rate limit exceeded | Lower C if in-flight is high; add a rate limiter if time-window quota |
| Latency p95/p99 rises while throughput stalls | Downstream saturation/queueing | Lower C, shrink queues, locate the bottleneck |
| Heap/GC grows with C × P | Buffers/inner outputs accumulating | Lower prefetch, reduce payload size, use streaming |
| 100% CPU with flat throughput | CPU-bound work or serialization | Reduce contention, profile CPU |
| Scheduler queues grow | Blocking or too many tasks | Remove blocking, add admission limits, inspect scheduler |
| Timeouts and retries rise together | Overload amplified by retries | Lower C, add backoff+jitter, deadlines, and retry budget |
| One request hogs the pool | Local concurrency only, missing global bulkhead | Add a global cap and fair sharing |

Monitor both active and pending counts. Looking only at successful request counts can miss growing queues before errors appear.

## 16. Tuning Process and Common Pitfalls

Tuning process:

1. Identify resources: does each inner call DB, API, file, or CPU? How much resource does one inner hold and for how long?
2. Find capacity: pool size, downstream quota, scheduler limits, memory budget, and reserve for other workloads.
3. Separate local/global: choose per-request limits and a system-wide bulkhead; compute nested fan-out.
4. Pick a low initial C, such as 2 or 4.
5. Pick P: inner Mono usually needs no large prefetch; inner Flux with large payloads starts with low P.
6. Load test: gradually raise parent requests, batch sizes, and arrival rate; measure throughput alongside p95/p99.
7. Watch for saturation: if raising C stops increasing throughput while queues/latency/GC climb, step back down.
8. Add pool pending limits, acquire timeouts, rate limiters, bulkheads, deadlines, and cancellation cleanup.
9. Test downstream 429/500/timeouts, client cancellation, retries, and concurrent requests.
10. Configure per workload; do not reuse one C across all endpoints/backends.

Common pitfalls:

1. **Omitting concurrency in `flatMap`.** Defaults may not match downstream capacity; specify it explicitly when calling bounded resources.
2. **Confusing concurrency with thread count.** Concurrency caps inner subscriptions, not dedicated threads.
3. **Confusing concurrency with rate limit.** Capping in-flight calls does not cap starts per second.
4. **Assuming local concurrency is a global limit.** Each request creates its own subscription; total load multiplies by concurrent requests.
5. **Forgetting nested fan-out.** Outer 8 × inner 5 can generate 40 leaf operations.
6. **Setting C equal to the entire pool size.** Other workloads and operational overhead require reserved connections.
7. **Looking only at CPU.** I/O-bound services may be constrained by pools/APIs rather than cores.
8. **Raising C to fix latency.** If downstream is saturated, queues and tail latency worsen.
9. **Ignoring prefetch.** Inner Flux can buffer multiple items per inner.
10. **Treating prefetch as total memory.** Queues, decoders, object overhead, and buffers at other layers also consume memory.
11. **Using `flatMapSequential` without accounting for queues.** Later inners may finish yet remain buffered waiting on earlier ones.
12. **Using `flatMap` when side effects require ordering.** Output and execution order are not preserved like `concatMap`.
13. **Using `concatMap` for everything.** Serialization can sacrifice throughput when operations are independent.
14. **Running blocking JDBC on the event loop.** Low concurrency does not make blocking calls safe.
15. **Running parallel queries on a transaction-bound connection.** Drivers may not support it; run sequentially within the same transaction.
16. **Omitting `defer` for publishers needing lazy side effects.** Work may start before the operator manages the subscription.
17. **Unbounded retries.** Retry storms overload downstream further.
18. **Using `flatMapDelayError` as overload protection.** It defers errors, does not shed load, and may keep excess work running.
19. **Swallowing all errors with `onErrorResume`.** Can hide outages and fabricate success results.
20. **Neglecting cancellation.** Inners holding resources can leak if APIs do not clean up properly.
21. **Using blocking semaphores on the event loop.** Can stall the whole event loop; use reactive bulkheads.
22. **Omitting pool acquire timeouts.** Waiting queues can grow unbounded.
23. **Testing only one parent request.** Fails to catch global fan-out exceeding capacity.
24. **Asserting concurrency must always reach C.** Timing/schedulers can keep observed max lower; enforcing the ceiling is the key contract.
25. **Changing C without measuring p95/p99.** Slight throughput gains may come at the cost of terrible tail latency.
26. **Sharing one C across DB, HTTP, and CPU.** Each resource has different capacity and hold times.
27. **Not bounding input batch size.** Concurrency has a ceiling, yet the source backlog can still grow too large.
28. **Assuming the pool protects the whole system.** Pool queues may merely convert overload into wait time and timeouts.

## 17. Pre-Production Checklist

- Does the mapper build publishers lazily without calling `subscribe()` itself?
- Which resources does each inner use, and for how long?
- Is `concurrency` explicitly set based on capacity?
- Does `prefetch` fit the inner's item count and payload size?
- Should you use `flatMap`, `flatMapSequential`, or `concatMap` given ordering needs?
- Is concurrency distinguished from rate limiting?
- Are concurrent HTTP requests and nested fan-out accounted for?
- Is there a global bulkhead/admission control for shared pools/upstreams?
- Do pools have max connections, pending queue limits, and acquire timeouts?
- Are transaction-bound connections protected from improper parallel queries?
- Do CPU/blocking tasks have dedicated schedulers and quotas?
- Do retries have bounded attempts, backoff, jitter, deadlines, and idempotency?
- Do timeouts/errors/cancellations clean up connections, buffers, and file handles?
- Does the memory budget approximate C × P × payload size plus other queues?
- Are active, pending, pool usage, p95/p99 latency, 429, timeout, and GC metrics tracked?
- Do load tests include multiple concurrent parent requests and slow downstreams?
- Do tests prove the concurrency cap is never exceeded without requiring max to always equal C?
- Is there a plan to lower concurrency or shed load when downstream overloads?

**Key Takeaway:** `flatMap(mapper, C, P)` caps in-flight inner Publishers at C and tunes per-inner demand with P. C bounds **a single subscription**; protecting shared pools requires accounting for multi-request fan-out and adding a global bulkhead. Choose C from resource budgets and measured latency; use `concatMap` when sequential execution is needed, and `flatMapSequential` when ordered output is required and buffering is acceptable. Concurrency does not replace rate limits, timeouts, pool caps, or overload policies. Measure active/pending/latency/GC under real load before locking in configuration.

## References

- Project Reactor 3.7 — [Flux API: flatMap concurrency and prefetch](https://projectreactor.io/docs/core/3.7.17/api/reactor/core/publisher/Flux.html).
- Project Reactor — [Reference Guide: operators that change demand and prefetch](https://projectreactor.io/docs/core/3.8.1/reference/).
- Project Reactor — [ParallelFlux API and inner publisher concurrency](https://docs.spring.io/projectreactor/reactor-core/docs/current/api/reactor/core/publisher/ParallelFlux.html).
- Reactor Netty — [HTTP Client Connection Pool and pending acquire configuration](https://projectreactor.io/docs/netty/release/reference/http-client.html).
- Spring Framework — [WebClient: reactive HTTP client](https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html).
- Spring Boot 3.5 — [R2DBC connection configuration](https://docs.spring.io/spring-boot/3.5/reference/data/sql.html).
- Spring Framework — [Reactive transaction management and Reactor Context](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html).
- Project Reactor — [Testing with StepVerifier](https://projectreactor.io/docs/core/release/reference/testing.html).
