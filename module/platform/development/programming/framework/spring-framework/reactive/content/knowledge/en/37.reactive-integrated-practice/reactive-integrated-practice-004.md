# Concurrency Limits, Timeouts, and Retry Budgets

**Module:** Spring Framework – reactive  
**Parent topic:** Integrated Practice  
**Goal:** Design reactive flows with bounded concurrency, clear deadlines, and finite retries; coordinate per-request limits with connection pools and system-wide quotas; avoid retry storms, duplicate side effects, and holding resources for too long.

## 1. Why Must All Three Policies Be Designed Together?

A service receives 200 order IDs, calls a partner API for each ID, and aggregates the results. Three decisions directly affect load and reliability:

- **Concurrency:** at any moment, how many child requests may run simultaneously?
- **Timeout/deadline:** how long may one call wait, and by when must the entire workflow finish?
- **Retry:** which errors are retried, at most how many times, and how long to wait between attempts?

Setting only one of the three policies is not enough. High concurrency without a timeout lets inner Publishers hang and hold slots. A short timeout with unbounded retries can create a continuous request loop. Retries with backoff but without a concurrency cap can still create thousands of concurrent attempts. Low local concurrency across many concurrent parent requests can multiply total load. Retrying a non-idempotent POST can create duplicate transactions when a response is lost after upstream already processed it successfully.

A stable pipeline needs a predefined **resource budget**, **time budget**, and **retry budget**.

## 2. Overall Processing Model

```text
Incoming request
      |
      v
Validate batch size and caller quota
      |
      v
flatMap(mapper, concurrency, prefetch)
      |
      +---- Item A
      |       +-- attempt timeout
      |       +-- retry filter / backoff / jitter
      |       +-- per-item deadline
      |
      +---- Item B
      |       +-- attempt timeout
      |       +-- retry filter / backoff / jitter
      |       +-- per-item deadline
      |
      +---- Item C ...
      |
      v
Aggregate / map partial results
      |
      v
Batch deadline and response
```

`flatMap` bounds the number of in-flight inner Publishers within one subscription. Each inner has its own timeout and retry policy. If the whole batch also has a deadline, add a limit for the entire workflow's duration. These limits serve different purposes.

## 3. Limiting Concurrency at Resource Call Sites

`Flux.flatMap(mapper, concurrency, prefetch)` has two key parameters:

| Parameter | Meaning | Tuning |
|---|---|---|
| `concurrency` | Maximum number of inner Publishers subscribed concurrently in one subscription | Number of in-flight child operations |
| `prefetch` | Initial demand requested from each inner Publisher | Buffering/demand when inner emits multiple elements |

Example:

```java
Flux<Result> results = orderIds.flatMap(
        id -> partnerClient.fetch(id),
        8,
        1);
```

At most eight inner Publishers are processed concurrently in this subscription. This does not mean eight separate threads. With WebClient, inners are typically non-blocking network I/O; with R2DBC, they can hold connections or transaction resources.

`prefetch` is not a limit on running requests. It matters more when the inner is a `Flux` emitting multiple items; if each inner is a `Mono` emitting at most one result, prefetch usually has less impact. Many inner operators have a common default prefetch of 32, but always check the Javadoc for your exact Reactor version.

### 3.1. Local Concurrency vs. System-Wide Limits

A limit of 8 applies only to a single subscription. If 25 HTTP requests run simultaneously and each creates `flatMap(..., 8)`, the total number of child operations can approach 200.

Distinguish:

- **Local concurrency:** maximum inners in one pipeline.
- **Global bulkhead:** maximum operations for a workload across the entire process or cluster.
- **Connection pool cap:** number of provisioned transport connections.
- **Rate limit:** number of operation starts per unit of time.

A 40-connection pool does not mean one request may occupy all 40. Allocate budget for health checks, other workloads, administrative tasks, and headroom. Bound the pending queue so overload is detected early rather than building an unbounded queue.

### 3.2. Choosing C Based on the Backend Resource

For example, a pool with 40 connections: 6 connections reserved for headroom, 10 connections for other workloads, leaving 24 connections as the maximum budget for batch lookups.

You can start with local concurrency 4 and a global bulkhead of 24, then load test. If 20 parent requests arrive at once, a local cap of 4 can still produce 80 child operations; only a global cap protects total load.

Do not pick C based solely on CPU core count. WebClient can be I/O-bound; databases can be constrained by connections or query execution; CPU transforms have different limits.

### 3.3. Calculating Nested Fan-Out

If an outer `flatMap` has concurrency 8 and an inner `flatMap` has concurrency 5, one subscription can generate up to roughly 40 leaf operations when all branches have enough work.

If 10 parent requests run concurrently, the theoretical number can reach 400. Calculate fan-out across all layers and apply bulkheads at shared resources.

### 3.4. Choosing Operators by Ordering

- `flatMap`: allows inners to run concurrently; output can interleave.
- `flatMapSequential`: subscribes to inners in parallel while preserving output order; may buffer results of early-completing inners.
- `concatMap`: runs only one inner at a time, preserving order.

If updates depend on order or share a single transaction-bound connection that does not support concurrent queries, consider `concatMap`. If work is independent, `flatMap` generally utilizes resources better.

## 4. Timeouts: Bounding a Single Attempt and the Whole Workflow

An outbound HTTP call can spend time in DNS resolution, connection pool acquire, TCP connect, TLS handshake or proxy tunnel, sending the request, reading the response, decoding the body, and processing the result. No single timeout describes every stage.

| Stage | API/Config | Meaning |
|---|---|---|
| Waiting for connection pool | `pendingAcquireTimeout` | Maximum time waiting for a connection |
| TCP connect | `CONNECT_TIMEOUT_MILLIS` | Time to establish TCP |
| TLS | `handshakeTimeout` | Time to complete the TLS handshake |
| DNS | Resolver query timeout | Limit for hostname lookup |
| Response | `HttpClient.responseTimeout` | Limit for waiting/reading response per transport semantics |
| Whole publisher | Reactor `timeout(Duration)` | Deadline of the wrapped publisher |

Reactor Netty configuration example:

```java
ConnectionProvider pool =
        ConnectionProvider.builder("partner")
                .maxConnections(24)
                .pendingAcquireMaxCount(48)
                .pendingAcquireTimeout(Duration.ofSeconds(1))
                .build();

HttpClient httpClient = HttpClient.create(pool)
        .option(
                ChannelOption.CONNECT_TIMEOUT_MILLIS,
                1_000)
        .responseTimeout(Duration.ofSeconds(2));

WebClient partnerClient = WebClient.builder()
        .clientConnector(
                new ReactorClientHttpConnector(httpClient))
        .baseUrl("https://partner.example.org")
        .build();
```

This is a configuration snippet requiring Reactor Netty, Netty, and Spring WebFlux imports. A custom `ConnectionProvider` has its own lifecycle; production applications must dispose of it according to Spring bean lifecycle. Never create a new pool per request.

### 4.1. Per-Attempt Timeout

Each attempt should have a finite timeout:

```java
Mono<Result> oneAttempt =
        partnerClient.get()
                .uri("/orders/{id}", id)
                .retrieve()
                .bodyToMono(Result.class)
                .timeout(Duration.ofSeconds(2));
```

Timeouts free the subscription when upstream does not respond within budget. However, a timeout does not prove upstream did not process the request. The server may have already committed while the response was lost.

### 4.2. Per-Item Deadline, Including Retries

Suppose each attempt takes at most 800 ms, retries happen at most twice, and backoffs are 100 ms then 200 ms. Theoretical maximum duration:

```text
3 × 800 ms + 100 ms + 200 ms = 2,700 ms
```

Add scheduling and overhead. You can set an overall 3-second deadline for the item:

```java
Mono<Result> callOne(String id) {
    return Mono.defer(() -> callPartner(id))
            .timeout(Duration.ofMillis(800))
            .retryWhen(retryPolicy)
            .timeout(Duration.ofSeconds(3));
}
```

The first timeout is **inside retry**, so each attempt gets an 800 ms budget. The final timeout is **outside retry**, so the entire chain of attempts and backoffs must finish within 3 seconds.

If you only place a timeout after retry, 3 seconds becomes a shared budget; a single attempt could consume most of the time and leave no room for subsequent retries:

```java
return Mono.defer(() -> callPartner(id))
        .retryWhen(retryPolicy)
        .timeout(Duration.ofSeconds(3));
```

### 4.3. Batch-Wide Deadline

If the batch is finite and can be aggregated within a bounded size, you can set a deadline on the aggregated `Mono`:

```java
Mono<List<Result>> batch =
        ids.flatMap(this::callOne, 8, 1)
                .collectList()
                .timeout(Duration.ofSeconds(8));
```

`collectList()` holds all results in memory, so only use it when the batch size is bounded. For large batches or long streams, process in chunks or emit results incrementally; never collect an unbounded stream.

Note: `Flux.timeout(Duration)` generally limits the **silence interval between signals**, not the total lifetime of a multi-element stream. For a single-result `Mono`, timeout expresses that call's deadline. For long SSE/streams, use an idle timeout/heartbeat separately and an absolute deadline if business rules require one.

### 4.4. Transport Timeouts Do Not Replace Business Deadlines

`responseTimeout` protects Reactor Netty's response-reading phase; it does not replace an end-to-end deadline. Conversely, an overall `Mono.timeout` can cancel the operation without telling you whether time was spent waiting on the pool, connect, or response.

Configure layered timeouts so failures remain diagnosable. Ensure a downstream deadline does not exceed the parent request's remaining deadline; if the parent request only has 500 ms left, do not start a new attempt with a 2-second timeout.

## 5. Retries: Only Retry Recoverable Errors

Retries are appropriate when an error is transient and re-calling is likely to succeed. They are not a catch-all for every exception.

| Error group | Common policy |
|---|---|
| Connection reset, transient network errors | Can be retried with bounds |
| HTTP 502/503/504 | Can be retried per policy and deadline |
| HTTP 429 | Honor `Retry-After` or quota; do not hammer retries |
| Timeout | Retry only when the operation is safe/idempotent and deadline remains |
| HTTP 400/401/403 | Usually do not retry |
| Validation/domain error | Do not retry |
| DB constraint violation | Do not retry blindly |
| Programming bug, serialization failure | Do not retry to hide bugs |

Classify exceptions specifically. A `WebClientResponseException` can represent 404, 429, or 503; do not retry every status just because they share the same class.

### 5.1. Retry Count Differs from Total Attempts

In Reactor:

```java
Retry.backoff(2, Duration.ofMillis(100))
```

The number 2 is the number of **retries after the initial call**, so the maximum total attempts is 3.

| Attempt | Action |
|---:|---|
| 1 | Initial call |
| 2 | Retry 1 after backoff |
| 3 | Retry 2 after backoff |
| Afterwards | Emit the final error if still failing |

Name variables clearly like `maxRetries`; avoid naming a variable `maxAttempts=2` and passing it straight into `Retry.backoff` while misunderstanding the total call count.

### 5.2. Exponential Backoff and Jitter

Do not retry immediately in a tight loop. When many clients fail together, immediate retries can cause a **thundering herd**: everyone calls again at the same instant and keeps overloading upstream.

Exponential backoff increases the wait interval on each retry. Jitter adds randomness to spread out retry timing.

```java
Retry retryPolicy = Retry.backoff(
                2,
                Duration.ofMillis(100))
        .maxBackoff(Duration.ofMillis(500))
        .jitter(0.5)
        .filter(this::isTransientFailure)
        .onRetryExhaustedThrow(
                (spec, signal) -> signal.failure());
```

`Retry.backoff` takes maximum retries and minimum backoff. `maxBackoff` caps how high the wait grows; `jitter` prevents synchronized retries. `filter` permits only transient errors. When retries are exhausted, the example above re-emits the original failure for the caller to handle.

In tests needing deterministic timing, you can set `.jitter(0d)` and use virtual time. In production, jitter helps when multiple instances may retry concurrently.

### 5.3. Filtering Errors Before Retrying

Sample classification skeleton:

```java
boolean isTransientFailure(Throwable error) {
    if (error instanceof TimeoutException) {
        return true;
    }

    if (error instanceof WebClientResponseException response) {
        int status = response.getStatusCode().value();
        return status == 502
                || status == 503
                || status == 504;
    }

    return error instanceof IOException;
}
```

This snippet requires imports and specific domain policy. Do not automatically treat 429 like 503; read `Retry-After`, enforce quotas, and bound wait times. Also do not retry 401/403 without an explicit credential refresh mechanism.

## 6. Placing Retry at the Right Boundary of flatMap

This is a critical decision to avoid unintentionally re-running the entire batch.

**Per-item retry:**

```java
Flux<Result> results = ids.flatMap(
        id -> Mono.defer(() -> callPartner(id))
                .timeout(Duration.ofSeconds(2))
                .retryWhen(retryPolicy),
        8,
        1);
```

Each item has its own retry policy. One failing item does not necessarily cause other items to re-run; however, by default a final error from one inner can terminate `flatMap` with an error and cancel the remaining inners.

**Whole-batch retry:**

```java
Flux<Result> results = ids.flatMap(
        this::callPartner,
        8,
        1)
        .retryWhen(retryPolicy);
```

If one item emits an error, an outer `retryWhen` can re-subscribe to the entire source Flux. Items that already succeeded may be called again, especially if the source is a cold Publisher. For write side effects, this can create duplicate data.

Only retry the whole batch when the source and all side effects are designed for safe re-execution, or when proper checkpointing/deduplication exists. In many batch APIs, per-item retry is the clearer boundary.

### 6.1. Retries Hold Concurrency Slots During Backoff

When retry is inside the mapper, the inner Publisher has not completed while waiting through backoff. Therefore, the `flatMap` slot remains occupied. C still bounds how many items are in progress, including items waiting to retry.

Pros: avoids opening unbounded new items while a group of items is failing. Cons: if many inners back off at once, batch throughput drops because slots stay held.

Do not try to free slots by pushing retries onto an unbounded queue. If you need to decouple retry scheduling from the request flow, you must have a bounded queue, a global retry budget, and separate admission control.

### 6.2. Avoid Unintentional Multi-Layer Retries

If the gateway retries 3 times, the service retries 3 times, and the SDK retries 3 times, attempts hitting upstream can multiply up to 27 (3 × 3 × 3) if each layer defines 3 as total attempts.

Choose one layer to own primary retries, or explicitly budget each layer. Calculate total attempts and total deadlines across the entire chain.

## 7. Retries and Idempotency

Timeouts often leave an uncertain outcome: the client did not receive a response, yet upstream may have already processed it successfully. If the client resends an order creation or payment command, the side effect can happen a second time.

Mitigations:

- Use a unique idempotency key per business operation.
- Store results by key on the server and return the previous result on duplicate requests.
- Have unique constraints or deduplication records in the database.
- Only retry POST/commands when the contract supports idempotency.
- Distinguish errors before sending the request from errors after upstream may have received it.
- Do not change the idempotency key across retries of the same business operation.

Retries do not automatically make a non-idempotent operation safe. For event/message delivery, design idempotent consumers and accept at-least-once if those are the actual semantics.

## 8. Deadlines Must Be Shared Across the Workflow

A parent request has a 5-second deadline. If service A spends 4 seconds and then calls service B with a default 5-second timeout, the whole workflow can stretch to 9 seconds or longer.

Deadline design:

1. Create or receive the deadline at a trusted boundary.
2. Compute remaining time before each downstream call.
3. Use an attempt timeout that does not exceed the remaining budget.
4. Do not start a new retry if the backoff plus next attempt no longer fit in the remaining time.
5. Propagate the deadline/remaining budget via metadata or context per internal contract.
6. Record timeout stages to identify where budget is exhausted.

Estimation formula for one item:

```text
T_item_max ≈
    attempts × attempt_timeout
    + sum(backoff_delays)
    + local_queue_and_scheduling_overhead
```

If pool acquire, connect, and response timeouts all sit inside an attempt, do not add them again when computing the total. Clearly identify which timeouts nest inside which to avoid double-counting budget.

For a batch, completion time depends on item count, concurrency, latency distribution, and retries. Do not use `itemCount × timeout` as a default deadline; load tests and SLAs should determine it.

## 9. Error Handling After Retries Are Exhausted

**Fail fast:** let the final error terminate the batch when every result is required.

```java
return ids.flatMap(this::callWithRetry, 8, 1);
```

**Per-item result:** convert errors into an explicit domain result type so other items continue.

```java
return ids.flatMap(
        id -> callWithRetry(id)
                .map(value -> ItemResult.success(id, value))
                .onErrorResume(error ->
                        Mono.just(ItemResult.failure(
                                id, classify(error)))),
        8,
        1);
```

`flatMapDelayError` can delay emitting errors until other inners are processed per the operator's semantics. It is not overload protection and can continue holding resources after the first error.

Do not use `onErrorResume(error -> Mono.empty())` for all exceptions. Doing so can turn data-loss errors into a "successful" batch missing items. Partial results must carry status/error codes so callers know which items failed.

## 10. Cancellation and Cleanup

Timeouts or client disconnects can propagate cancellation down the pipeline. Reactor can cancel inner Publishers and pending timers, but cannot guarantee an already-sent HTTP side effect will be rolled back by upstream.

Each inner must clean up properly by lifecycle:

- Release connections/buffers/file handles on complete, error, or cancel.
- Do not call `subscribe()` manually to detach work from the request.
- Use `using`/`usingWhen` for lifecycle-bound resources.
- Do not retry cancellation; cancellation is not an `onError` signal.
- For side-effecting operations, check idempotency and business state before retrying.
- Do not hold transactions or DB connections during long backoffs if boundaries can be redesigned.

`doFinally` is useful for observing complete/error/cancel, but resource cleanup must use proper ownership APIs; a logging callback does not replace closing resources.

## 11. Metrics for Tuning Concurrency, Timeouts, and Retries

| Metric | What to detect |
|---|---|
| Active inner calls | Actual concurrency level |
| Pending pool acquire | Connection wait queue |
| Connection active/idle/max | Whether the pool is saturated |
| Attempt count by error type | Whether retries are amplifying load |
| Retry exhausted | Number of items failing after retries |
| Attempt latency and total item latency | Whether timeouts hit single attempts or whole items |
| Timeout by stage | Pool, connect, TLS, response, or deadline |
| HTTP 429/5xx | Quota and upstream health |
| Cancellation count | Clients abandoning requests or timing out |
| p50/p95/p99 | Tail latency as C increases |
| Queue depth, heap, GC | Whether buffers and backlogs are growing |

Do not put order IDs, emails, tokens, or raw URLs in metric labels. Use route/workload/status/error category with bounded cardinality.

If increasing C does not increase throughput while pending queues, p99, and retries climb, reduce concurrency and find the bottleneck. Retries should not be evaluated solely by final request success rate; also examine attempt counts and generated load.

## 12. Runnable Java 17+ Example: Bounded Concurrency + Retry + Timeout

The example uses Reactor Core, Java 17, and Maven. A service accepts a `Function<String, Mono<String>>` representing a downstream client. Each item has a per-attempt timeout, finite retries with backoff, and an overall per-item deadline. `flatMap` limits how many items are processed at once.

**Project structure:**

```text
reactive-reliability-demo/
├── pom.xml
└── src/
    ├── main/java/demo/ResilientBatchService.java
    └── test/java/demo/ResilientBatchServiceTest.java
```

### 12.1. pom.xml

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
    <artifactId>reactive-reliability-demo</artifactId>
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

Spring Boot parent manages Reactor versions compatible with the Boot 3.5 line. The project does not need an HTTP server because the focus is publisher policies; in a real application, `remoteCall` would invoke WebClient/R2DBC or a reactive SDK.

### 12.2. ResilientBatchService.java

```java
package demo;

import java.time.Duration;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Function;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.util.retry.Retry;

public final class ResilientBatchService {

    private final Function<String, Mono<String>> remoteCall;
    private final int concurrency;
    private final int prefetch;
    private final Duration attemptTimeout;
    private final Duration itemDeadline;
    private final Retry retryPolicy;

    private final AtomicInteger activeAttempts =
            new AtomicInteger();

    private final AtomicInteger maxObservedAttempts =
            new AtomicInteger();

    public ResilientBatchService(
            Function<String, Mono<String>> remoteCall,
            int concurrency,
            int prefetch,
            Duration attemptTimeout,
            Duration itemDeadline,
            Retry retryPolicy) {

        if (concurrency < 1 || prefetch < 1) {
            throw new IllegalArgumentException(
                    "concurrency and prefetch must be positive");
        }
        if (attemptTimeout.isZero() || attemptTimeout.isNegative()
                || itemDeadline.isZero() || itemDeadline.isNegative()) {
            throw new IllegalArgumentException(
                    "timeouts must be positive");
        }

        this.remoteCall = remoteCall;
        this.concurrency = concurrency;
        this.prefetch = prefetch;
        this.attemptTimeout = attemptTimeout;
        this.itemDeadline = itemDeadline;
        this.retryPolicy = retryPolicy;
    }

    public Mono<String> fetchOne(String id) {
        return Mono.defer(() -> remoteCall.apply(id))
                .doOnSubscribe(subscription -> {
                    int current = activeAttempts.incrementAndGet();
                    maxObservedAttempts.accumulateAndGet(
                            current, Math::max);
                })
                .doFinally(signal ->
                        activeAttempts.decrementAndGet())
                .timeout(attemptTimeout)
                .retryWhen(retryPolicy)
                .timeout(itemDeadline);
    }

    public Flux<String> fetchAll(List<String> ids) {
        return Flux.fromIterable(ids)
                .flatMap(this::fetchOne, concurrency, prefetch);
    }

    public int activeAttempts() {
        return activeAttempts.get();
    }

    public int maxObservedAttempts() {
        return maxObservedAttempts.get();
    }
}
```

Important boundaries:

- `Mono.defer` invokes `remoteCall` again on every subscription/attempt; the source must be lazy so requests are not sent before subscription.
- `doOnSubscribe` increments the counter for each attempt, while `doFinally` decrements on complete/error/cancel.
- `timeout(attemptTimeout)` sits before `retryWhen`, giving each attempt its own deadline.
- `retryWhen(retryPolicy)` retries only errors permitted by the policy.
- `timeout(itemDeadline)` sits after retry, encompassing all attempts and backoffs.
- `flatMap(..., concurrency, prefetch)` limits the number of inner items in one subscription.

The counter measures attempts actively executing downstream; during backoff intervals, the previous attempt has ended and the counter decrements, yet the inner item has not completed so the `flatMap` slot remains held.

### 12.3. ResilientBatchServiceTest.java

```java
package demo;

import java.time.Duration;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;

import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;
import reactor.util.retry.Retry;

import static org.assertj.core.api.Assertions.assertThat;

class ResilientBatchServiceTest {

    private Retry retryPolicy() {
        return Retry.backoff(2, Duration.ofMillis(100))
                .maxBackoff(Duration.ofMillis(200))
                .jitter(0d)
                .filter(error ->
                        error instanceof TransientRemoteException)
                .onRetryExhaustedThrow(
                        (spec, signal) -> signal.failure());
    }

    @Test
    void batchNeverExceedsConfiguredActiveConcurrency() {
        ResilientBatchService service =
                new ResilientBatchService(
                        id -> Mono.delay(Duration.ofMillis(20))
                                .thenReturn("ok-" + id),
                        3,
                        1,
                        Duration.ofSeconds(1),
                        Duration.ofSeconds(3),
                        retryPolicy());

        java.util.List<String> ids =
                java.util.stream.IntStream.rangeClosed(1, 20)
                        .mapToObj(Integer::toString)
                        .toList();

        StepVerifier.create(service.fetchAll(ids))
                .expectNextCount(20)
                .verifyComplete();

        assertThat(service.maxObservedAttempts())
                .isGreaterThan(0)
                .isLessThanOrEqualTo(3);

        assertThat(service.activeAttempts()).isZero();
    }

    @Test
    void transientFailureRetriesAndThenSucceeds() {
        AtomicInteger attempts = new AtomicInteger();

        StepVerifier.withVirtualTime(() -> {
                    ResilientBatchService service =
                            new ResilientBatchService(
                                    id -> Mono.defer(() -> {
                                        int attempt =
                                                attempts.incrementAndGet();
                                        if (attempt < 3) {
                                            return Mono.error(
                                                    new TransientRemoteException());
                                        }
                                        return Mono.just("success");
                                    }),
                                    2,
                                    1,
                                    Duration.ofSeconds(2),
                                    Duration.ofSeconds(5),
                                    retryPolicy());

                    return service.fetchOne("order-A");
                })
                .thenAwait(Duration.ofSeconds(1))
                .expectNext("success")
                .verifyComplete();

        assertThat(attempts).hasValue(3);
    }

    @Test
    void nonRetryableFailureIsAttemptedOnlyOnce() {
        AtomicInteger attempts = new AtomicInteger();

        ResilientBatchService service =
                new ResilientBatchService(
                        id -> Mono.defer(() -> {
                            attempts.incrementAndGet();
                            return Mono.error(
                                    new IllegalArgumentException("invalid order"));
                        }),
                        2,
                        1,
                        Duration.ofSeconds(1),
                        Duration.ofSeconds(3),
                        retryPolicy());

        StepVerifier.create(service.fetchOne("bad-order"))
                .expectError(IllegalArgumentException.class)
                .verify();

        assertThat(attempts).hasValue(1);
    }

    @Test
    void totalItemDeadlineIncludesTheAttempt() {
        StepVerifier.withVirtualTime(() -> {
                    ResilientBatchService service =
                            new ResilientBatchService(
                                    id -> Mono.delay(Duration.ofSeconds(10))
                                            .thenReturn("too-late"),
                                    1,
                                    1,
                                    Duration.ofSeconds(8),
                                    Duration.ofSeconds(2),
                                    retryPolicy());

                    return service.fetchOne("slow-order");
                })
                .thenAwait(Duration.ofSeconds(2))
                .expectError(TimeoutException.class)
                .verify();
    }

    @Test
    void cancellationReleasesActiveAttemptCounter() {
        ResilientBatchService service =
                new ResilientBatchService(
                        id -> Mono.never(),
                        1,
                        1,
                        Duration.ofSeconds(10),
                        Duration.ofSeconds(15),
                        retryPolicy());

        StepVerifier.create(service.fetchOne("cancel-me"))
                .thenCancel()
                .verify();

        assertThat(service.activeAttempts()).isZero();
    }
}

final class TransientRemoteException extends RuntimeException {
}
```

Run from the project directory with JDK 17+ and Maven:

```bash
mvn test
```

**Expected logical result:** five tests PASS and Maven exit code 0.

| Test | What it proves |
|---|---|
| `batchNeverExceedsConfiguredActiveConcurrency` | 20 items complete, active attempts do not exceed C=3 |
| `transientFailureRetriesAndThenSucceeds` | First two transient errors are retried, third attempt succeeds |
| `nonRetryableFailureIsAttemptedOnlyOnce` | Validation errors are not retried |
| `totalItemDeadlineIncludesTheAttempt` | Overall deadline terminates slow item with `TimeoutException` |
| `cancellationReleasesActiveAttemptCounter` | Cancellation frees the attempt counter |

`Retry.backoff(2, ...)` allows at most two retries after the first call, so the transient test expects three total calls. Virtual-time tests create the service inside the supplier so the retry scheduler is set up in the virtual-time context. No fixed build duration or log order is asserted.

## 13. Reactor Netty Configuration Example in Spring WebClient

A production configuration needs a bounded pool, bounded pending queue, and clear transport timeouts:

```java
@Configuration(proxyBeanMethods = false)
class PartnerClientConfiguration {

    @Bean(destroyMethod = "dispose")
    ConnectionProvider partnerPool() {
        return ConnectionProvider.builder("partner")
                .maxConnections(24)
                .pendingAcquireMaxCount(48)
                .pendingAcquireTimeout(Duration.ofSeconds(1))
                .build();
    }

    @Bean
    WebClient partnerWebClient(
            ConnectionProvider partnerPool,
            WebClient.Builder builder) {

        HttpClient httpClient =
                HttpClient.create(partnerPool)
                        .option(
                                ChannelOption.CONNECT_TIMEOUT_MILLIS,
                                1_000)
                        .responseTimeout(Duration.ofSeconds(2));

        return builder
                .baseUrl("https://partner.example.org")
                .clientConnector(
                        new ReactorClientHttpConnector(httpClient))
                .build();
    }
}
```

This is a Spring snippet requiring the corresponding imports. `destroyMethod="dispose"` releases the custom pool when the bean context closes. Verify the lifecycle API against the Reactor Netty version managed by Boot.

Pool size 24 is only an example. If `flatMap` local concurrency is 8 and 10 parent requests run at once, the pool can receive up to 80 demands; the pool creates at most 24 connections while the rest wait in queue or time out. A pool cap does not replace a global bulkhead because it can merely convert overload into a pending queue.

## 14. Common Mistakes

1. **Setting only concurrency without timeouts.** Hanging inners hold slots and resources for too long.
2. **Setting only timeouts without a retry budget.** Callers can retry continuously and trigger retry storms.
3. **Unbounded retries.** Increases load right when upstream is already failing.
4. **Confusing maxRetries with total attempts.** `Retry.backoff(2, ...)` is two retries plus the initial call.
5. **Retrying all exceptions.** Validation, 401/403, and bugs do not self-recover.
6. **Retrying HTTP 429 immediately.** Can violate quotas; honor `Retry-After`.
7. **Not using jitter.** Multiple instances retry simultaneously after the exact same backoff.
8. **Placing a timeout outside retry while thinking it is per-attempt.** That timeout is a shared budget across the whole chain.
9. **Placing a timeout inside retry without an overall deadline.** Multiple attempts and backoffs can stretch beyond the SLA.
10. **Placing retry outside the entire batch.** One failing item can re-run the entire cold source, repeating already-succeeded side effects.
11. **Retrying POST without idempotency.** Can create duplicate orders or payments.
12. **Excluding backoff from deadlines.** Each attempt still fits individually, yet the overall item runs out of budget.
13. **Retrying at multiple layers.** Gateway, service, and SDK multiply call counts.
14. **Increasing C to fix timeouts.** Saturating the downstream can make things worse.
15. **Using local concurrency as a global cap.** Multiple parent requests multiply total fan-out.
16. **Setting C equal to the entire connection pool.** Leaves no headroom for other workloads.
17. **Unbounded pending acquire queues.** Overload turns into long backlogs and rising memory.
18. **Using `Flux.timeout(Duration)` as an absolute deadline.** For multi-item Fluxes, it is usually an idle timeout between signals.
19. **Using `collectList()` for unbounded batches.** Accumulates the entire result set on the heap.
20. **Not releasing resources on cancel.** Timeouts/client disconnects can leak connections/files/buffers.
21. **Treating cancel as upstream rollback.** Side effects may have already committed.
22. **Not distinguishing timeout stages.** Pool, DNS, TCP, TLS, and response have different root causes.
23. **Retrying while holding transactions/connections unnecessarily.** Resources can stay occupied during backoff.
24. **Not measuring attempt counts.** Final success rate can mask massive retry load.
25. **Not testing multiple concurrent parent requests.** Local caps pass while global resources still overload.

## 15. Parameter Tuning Process

1. Identify the downstream: DB, HTTP partner, broker, or CPU.
2. Calculate connection, quota, memory, and CPU budgets; reserve headroom for other workloads.
3. Start with a low local concurrency and an appropriate global bulkhead.
4. Choose prefetch based on inner type and payload size.
5. Set separate timeouts for pool acquire, connect, TLS, and response.
6. Set per-attempt timeouts and an overall per-item deadline.
7. Choose a small, finite retry count; filter transient errors.
8. Choose exponential backoff, max backoff, and jitter.
9. Verify idempotency before retrying side-effecting operations.
10. Load test with multiple concurrent parent requests, slow downstreams, 429/5xx, timeouts, and cancellation.
11. Observe active/pending counts, attempt counts, p95/p99 latency, pool, heap, and GC.
12. Tune one parameter at a time and record results.

A good configuration does not necessarily maximize throughput in a short benchmark. It must keep latency and resource headroom stable when downstreams slow down or fail.

## 16. Pre-Production Checklist

- Does `flatMap` have explicit concurrency where bounded resources are called?
- Are local cap, global bulkhead, pool cap, and rate limit clearly separated?
- Are nested fan-out and concurrent parent requests accounted for?
- Does the pool have max connections, a bounded pending queue, and an acquire timeout?
- Does every attempt have a finite timeout?
- Does the whole item have a deadline including retries/backoff?
- Do downstream deadlines respect the parent request's remaining time?
- Does `Retry.backoff` have finite max retries, max backoff, and jitter?
- Are only clearly classified transient errors retried?
- Are 429/503 responses handled with appropriate quota/`Retry-After` logic?
- Is retry placed intentionally per item or for the whole batch?
- Do side effects have idempotency keys/deduplication?
- Are nested retries across gateway/service/SDK avoided?
- Do cancellation/error/timeout release resources according to lifecycle?
- Are Mono deadlines distinguished from Flux inter-signal timeouts?
- Are concurrency caps, transient retries, non-retryable errors, deadlines, and cancellation tested?
- Are multiple concurrent parent requests and slow downstreams load tested?
- Are metrics present for active/pending, attempts, retry exhaustion, timeout stage, and p95/p99?
- Are alerts configured when retry rates or pool pending counts spike?

**Remember:** `flatMap` bounds the number of running inners in a single subscription; a global bulkhead is what protects shared resources across multiple requests. A per-attempt timeout sits inside retry, while the item deadline sits outside retry to account for backoff. `Retry.backoff(N, ...)` allows N retries after the initial attempt; retry only transient errors, with jitter, deadlines, and proper idempotency. Timeouts do not prove a side effect has not happened, cancellation does not automatically roll back upstream, and retrying outside an entire batch can re-run already-succeeded items. Pick parameters from resource budgets and load tests, then monitor active/pending/attempt/latency in production.

## References

- Project Reactor 3.8 — [Flux API: flatMap, concurrency and prefetch](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html).
- Project Reactor 3.8 — [Retry API: Retry.backoff and retry limits](https://projectreactor.io/docs/core/release/api/reactor/util/retry/Retry.html).
- Project Reactor — [Reference Guide: Backpressure, prefetch and demand](https://projectreactor.io/docs/core/release/reference/subscribe-backpressure.html).
- Project Reactor — [Reference Guide: Threading and Schedulers](https://projectreactor.io/docs/core/release/reference/coreFeatures/schedulers.html).
- Reactor Netty 1.3 — [HTTP Client: Connection Pool, timeouts and metrics](https://projectreactor.io/docs/netty/release/reference/http-client.html).
- Spring Framework — [WebClient reactive HTTP client](https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html).
- Spring Framework — [Reactive transaction management and Reactor Context](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html).
- Project Reactor — [Testing with StepVerifier](https://projectreactor.io/docs/core/release/reference/testing.html).
