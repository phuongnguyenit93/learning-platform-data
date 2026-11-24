# Timeouts, Cancellation, and Resource Cleanup in Reactive Execution

## 1. Problem and Objectives

In Spring Boot applications using **Spring WebFlux**, an HTTP request may await `WebClient` responses, reactive database queries, data streams, or long-lived SSE connections. When work runs too long, a client disconnects, or downstream only needs part of the stream, the application must **bound wait times**, **cancel unneeded work**, and **clean up resources**.

Three distinct concepts:

- **Timeout:** bounds waiting according to specific semantics. Reactor's `timeout(Duration)` can emit `TimeoutException` when no signal arrives in time; that error can be replaced with a fallback.
- **Cancellation:** downstream invokes `Subscription.cancel()` to tell upstream it no longer wants data. This is a Reactive Streams control signal, **neither** `onError` **nor** `onComplete`.
- **Cleanup:** releases connections, streams, reactive transactions, producer subscriptions, pooled buffers, or other resources across every termination path: completion, error, and cancellation.

Common pipeline sequence: upstream runs too slowly → `timeout` cancels upstream → downstream receives `TimeoutException` → `onErrorResume` returns a fallback → outer publisher may complete successfully. Within the same request, **upstream observes cancel while downstream observes complete**. If cleanup sits only on the error branch, resources can leak.

Scope: **Reactor (`Mono`/`Flux`) and Spring WebFlux** with Java 17+, Spring Boot 3.3.x / Reactor 3.6.x. Behavior involving networks, databases, and external systems always depends on driver/transport cancellation support.

## 2. Reactive Streams Signals and Where Cancellation Fits

A declared pipeline does not execute merely because code writes `Mono.just(...)` or `webClient.get()...bodyToMono(...)`. Execution begins upon **subscription**. Spring WebFlux normally manages subscribing to the `Publisher` returned by a controller to produce the HTTP response.

```text
Subscriber                                      Publisher / upstream
    │
    ├── subscribe() ─────────────────────────────►
    ◄── onSubscribe(Subscription) ────────────────┤
    ├── request(n) ──────────────────────────────►
    ◄── onNext(value) [0..n values] ──────────────┤
    ◄── onComplete() OR onError(cause) ───────────┤  (terminal)
    │
    └── OR cancel() ─────────────────────────────►  (stop wanting further items)
```

A `Mono` publisher emits at most one value; a `Flux` can emit multiple values according to `request(n)` demand. The Reactive Streams contract defines two data-termination signals—`onComplete` and `onError`; `cancel` is a request from subscriber back to upstream, and does not emit a new error to the already-cancelled subscriber.

| Event at observation point | Meaning | `doFinally` `SignalType` |
|---|---|---|
| Publisher finishes | `onComplete` (Mono may be empty) | `ON_COMPLETE` |
| Publisher emits error | `onError(Throwable)` | `ON_ERROR` |
| Downstream cancels subscription | Stops wanting further data from upstream | `CANCEL` |
| Timeout with fallback | Original source is normally cancelled, fallback may complete | Upstream `CANCEL`; post-fallback `ON_COMPLETE` |

**Operator placement is crucial:** `doFinally` placed before `timeout` observes how the source ended; placed after `onErrorResume` it observes the final outcome after fallback handling. Both hooks can report different signal types without contradiction.

## 3. Bounding Time with `timeout`

### 3.1. Mono: Time Limit for a Value

```java
import java.time.Duration;
import java.util.concurrent.TimeoutException;
import reactor.core.publisher.Mono;

Mono<String> slow = Mono.delay(Duration.ofSeconds(3))
        .map(ignored -> "finished");

Mono<String> limited = slow.timeout(Duration.ofMillis(250));
```

This is a code fragment placed inside a Java method with the imports above, not a standalone class. Upon subscription, `Mono.delay` emits after roughly three seconds, yet `timeout` waits only 250 ms. Because no result arrives on time, `limited` emits `java.util.concurrent.TimeoutException` and sends cancel to the slow source.

**`timeout(Duration)` does not automatically produce HTTP 504.** It alters the reactive signal. HTTP status is decided at the WebFlux/controller/exception-handler layer or proxy.

You can handle it with `onErrorResume`:

```java
Mono<String> withFallback = limited.onErrorResume(
        TimeoutException.class,
        ex -> Mono.just("fallback")
);
```

Or supply a fallback directly:

```java
Mono<String> directly = slow.timeout(
        Duration.ofMillis(250),
        Mono.just("fallback")
);
```

In both cases, `fallback` comes from a new Publisher—it does not mean the slow original source keeps running subscribed in the background to finish later. The fallback itself can error, lag, or be cancelled next; size budgets accordingly.

### 3.2. Flux: Interval Between Elements

For `Flux`, `timeout(Duration)` governs the wait until **the first element** and **between consecutive elements**. It is **not** a total deadline for the entire stream.

```java
Flux<Long> regular = Flux.interval(Duration.ofMillis(100))
        .take(20)
        .timeout(Duration.ofMillis(500));
```

This snippet (requiring `Flux` and `Duration` imports) normally emits 20 elements over nearly two seconds without timing out, because the gap between consecutive items is only ~100 ms. Only if the stream stalls for over 500 ms between items does `Flux.timeout` signal an error (unless the source already completed).

If the goal is "the stream lives at most 2 seconds", `take(Duration.ofSeconds(2))` can terminate the stream after that duration, though it **completes normally** without a timeout error. If the goal is "the whole list must finish within 2 seconds", you can apply timeout to a `Mono` representing full collection/completion, e.g., `flux.collectList().timeout(...)` on a **finite** stream with a suitable memory budget. Never `collectList` an unbounded stream just to enforce a deadline, as memory will grow dangerously.

### 3.3. Timeout Placement in Multi-Stage Flows

Suppose a business flow calls service A then service B:

```java
Mono<FinalResult> answer = callA()
        .flatMap(a -> callB(a))
        .timeout(Duration.ofSeconds(3));
```

This is a syntax outline; in an app you must define `FinalResult`, `callA`, and `callB`. The outer timeout bounds total completion time across A→B, whereas per-call timeouts on `callA`/`callB` govern each hop. Two hops each allowing 2 seconds can total nearly 4 seconds without a shared outer budget.

When combining `retryWhen`, operator order defines the budget:

- `source.timeout(1s).retryWhen(...)`: each attempt resets the 1-second clock; total time spans multiple attempts plus backoff.
- `source.retryWhen(...).timeout(3s)`: adds an overall cap wrapping all retry attempts.

Retries must bound attempt counts, choose backoff, filter for retryable failures, and respect **idempotency**. Timeout/cancel cannot guarantee a remote write did not already execute.

### 3.4. Distinguishing Network-Level and Application-Level Timeouts

| Limit type | Scope | Does not guarantee |
|---|---|---|
| Reactor `Mono.timeout` | Time waiting for Mono signal/completion | Does not apply to work detached from the subscription |
| Reactor `Flux.timeout` | Gap between emitted elements | Not an overall stream deadline |
| Reactor Netty TCP connect timeout | Time to establish network connection | Does not bound full business processing |
| Reactor Netty response timeout | HTTP client response read condition | Does not replace multi-hop/retry deadlines |
| Proxy/gateway timeout | Network infrastructure policy | Does not necessarily emit `TimeoutException` inside your pipeline |
| Business/request deadline | Overall budget designed by the app | Does not undo side effects already sent out-of-process |

When Spring Boot WebFlux returns a streaming response whose status and headers have already been sent, a later timeout **cannot always rewrite the response to a fresh HTTP 504**; instead you may need to close the stream/connection or signal errors at the event protocol level.

## 4. Where Does Cancellation Come From?

Cancel originates downstream, for example:

1. `timeout` fails to receive signals within the allowed window.
2. A subscriber calls `dispose()` on the `Disposable` returned by `subscribe()`, or calls `Subscription.cancel()`.
3. Operators needing only part of the stream such as `take(1)`, `next()`, or `switchMap` switching to a new inner source.
4. The server/framework detects HTTP client disconnect and cancels the associated subscription (degree and timing depend on transport and pipeline).
5. One branch obtains enough results and cancels an unneeded publisher.

```text
Upstream source ──► operator A ──► operator B ──► HTTP subscriber
                    ▲               ▲               │
                    └── cancel ◄────┴── cancel ◄────┘
```

Cancel is a **request to stop delivering/continuing work**, not a forced "kill thread". Reactive timers (`Mono.delay`) or non-blocking drivers typically cancel promptly. Conversely, synchronous JDBC, `Thread.sleep`, native calls, or external APIs may keep running even after downstream stops waiting. Data may already be written to a database or published to a broker before cancel arrives.

Therefore, **timeout does not automatically roll back transactions or prevent side effects**. Write operations require proper transaction boundaries, idempotency keys, controlled retries, or business compensation.

**In WebFlux controllers, always return the Publisher.** The framework subscribes to write the HTTP response and can propagate cancellation. Never casually call `subscribe()` and return something else; manual subscriptions become detached work outside the request lifecycle.

## 5. Cleanup Across Complete, Error, and Cancel

| Reactor API | Timing / characteristics | When to use |
|---|---|---|
| `doOnCancel(Runnable)` | Runs on cancel at operator position; not called on normal complete/error | Cancel logs/metrics, lightweight cancel action |
| `doFinally(Consumer<SignalType>)` | Runs after complete, error, **or cancel**; provides signal type | Latency stats, metrics, short synchronous cleanup |
| `Mono.using` / `Flux.using` | Acquires resource **per subscription**, uses it in scope, cleans up on end/cancel | Synchronous closeable resources (`AutoCloseable`/handles) |
| `Mono.usingWhen` / `Flux.usingWhen` | Acquires and cleans up via Publishers, supporting async cleanup | Reactive connections, transactions, leases |
| `doOnDiscard(Class, Consumer)` | Discard-aware operators pass dropped/queued elements here | Releasing pooled buffers/resources in queues/prefetch |
| `FluxSink.onCancel`, `onDispose` | Producer callbacks for `Flux.create` adapters | Unregistering callbacks/sockets/producers |

Key distinctions:

- `doOnTerminate` or `doAfterTerminate` react only to complete/error—**they do not replace `doFinally` for cancellation**.
- `doFinally(signal -> closeAsync())` only creates a `Mono<Void>` if `closeAsync()` returns a Publisher; it **does not subscribe to or await async cleanup**. Use `usingWhen` or framework lifecycle hooks when cleanup is asynchronous.
- `doOnCancel` does not run on complete/error, so it must never be the sole resource-closing mechanism.
- `doOnDiscard` works only with operators that support discard and must sit in the right chain position; cleanup should be idempotent/safe per resource contract.
- Never double-release a `DataBuffer` or close resources still owned by the framework/driver.

## 6. Runnable Spring Boot WebFlux Example (Java 17+)

This example uses a Reactor timer to simulate a slow source **without blocking the event loop**, plus a mock lease to observe resource closure. It needs no external database or HTTP service.

Project layout:

```text
reactive-timeout-demo/
├── build.gradle
└── src/
    ├── main/
    │   ├── java/com/example/reactivecleanup/ReactiveTimeoutApplication.java
    │   └── resources/application.properties
    └── test/
        └── java/com/example/reactivecleanup/CancellationTest.java
```

**`build.gradle`**:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

**`src/main/resources/application.properties`**:

```properties
server.port=8080
```

**`src/main/java/com/example/reactivecleanup/ReactiveTimeoutApplication.java`**:

```java
package com.example.reactivecleanup;

import java.time.Duration;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicBoolean;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;
import reactor.core.publisher.SignalType;

@SpringBootApplication
public class ReactiveTimeoutApplication {

    public static void main(String[] args) {
        SpringApplication.run(ReactiveTimeoutApplication.class, args);
    }
}

@RestController
@RequestMapping("/demo")
class DeadlineController {

    private static final Duration BUDGET = Duration.ofMillis(250);

    @GetMapping("/wait")
    Mono<ResponseEntity<Reply>> waitForValue(
            @RequestParam(defaultValue = "800") long waitMs) {

        if (waitMs < 0) {
            return Mono.just(ResponseEntity.badRequest()
                    .body(new Reply("invalid", "waitMs must be non-negative")));
        }

        Mono<ResponseEntity<Reply>> upstream =
                Mono.delay(Duration.ofMillis(waitMs))
                    .map(tick -> ResponseEntity.ok(
                            new Reply("success", "done")))
                    .doOnCancel(() ->
                            System.out.println("WAIT_UPSTREAM_CANCEL"))
                    .doFinally(this::logUpstreamEnd);

        return upstream
                .timeout(BUDGET)
                .onErrorResume(TimeoutException.class, ignored ->
                        Mono.just(ResponseEntity.status(HttpStatus.GATEWAY_TIMEOUT)
                                .body(new Reply("timeout", "wait exceeded 250 ms"))))
                .doFinally(signal ->
                        System.out.println("WAIT_RESULT_FINALLY=" + signal));
    }

    @GetMapping("/resource")
    Mono<ResponseEntity<Reply>> withResource(
            @RequestParam(defaultValue = "800") long waitMs) {

        if (waitMs < 0) {
            return Mono.just(ResponseEntity.badRequest()
                    .body(new Reply("invalid", "waitMs must be non-negative")));
        }

        Mono<ResponseEntity<Reply>> scoped =
                Mono.using(
                        DemoLease::new,
                        lease -> Mono.delay(Duration.ofMillis(waitMs))
                                .map(tick -> ResponseEntity.ok(
                                        new Reply("success", lease.read()))),
                        DemoLease::close
                );

        return scoped
                .timeout(BUDGET)
                .onErrorResume(TimeoutException.class, ignored ->
                        Mono.just(ResponseEntity.status(HttpStatus.GATEWAY_TIMEOUT)
                                .body(new Reply("timeout", "lease wait exceeded 250 ms"))));
    }

    private void logUpstreamEnd(SignalType signal) {
        System.out.println("WAIT_UPSTREAM_FINALLY=" + signal);
    }
}

record Reply(String outcome, String detail) {}

final class DemoLease implements AutoCloseable {

    private final AtomicBoolean closed = new AtomicBoolean();

    DemoLease() {
        System.out.println("LEASE_OPENED");
    }

    String read() {
        return "lease result";
    }

    @Override
    public void close() {
        if (closed.compareAndSet(false, true)) {
            System.out.println("LEASE_CLOSED");
        }
    }
}
```

This is a **complete single Java file**: only `ReactiveTimeoutApplication` is a top-level `public class`; controller, record, and lease in the same file are package-private. `spring-boot-starter-webflux` selects the reactive stack (typically embedded Reactor Netty), and Spring manages subscribing to the publisher returned by the controller.

From `reactive-timeout-demo`, run:

```bash
gradle bootRun
```

If your project includes the Gradle Wrapper, substitute `./gradlew bootRun` on Linux/macOS or `.\gradlew.bat bootRun` on Windows PowerShell. Requires JDK 17+ and a Gradle version compatible with Boot 3.3.x.

### 6.1. Completing Successfully

```bash
curl -i "http://localhost:8080/demo/wait?waitMs=20"
```

Expected result: **HTTP 200 OK** and JSON body:

```json
{"outcome":"success","detail":"done"}
```

The source emits after ~20 ms, well under 250 ms. Both `doFinally` hooks before and after timeout normally record `ON_COMPLETE`. There is no reason for upstream cancellation on the success path.

### 6.2. Source Too Slow: Upstream Cancels, Downstream Returns Fallback

```bash
curl -i "http://localhost:8080/demo/wait?waitMs=800"
```

Expected result: **HTTP 504 Gateway Timeout** because **the controller explicitly chooses status 504**, JSON body:

```json
{"outcome":"timeout","detail":"wait exceeded 250 ms"}
```

Because `Mono.delay(800 ms)` has not emitted by 250 ms, `timeout` cancels upstream and emits `TimeoutException`. `onErrorResume` maps this error into a 504 ResponseEntity. The pre-timeout logger receives cancel; the post-fallback chain completes normally.

Log lines can represent the events as:

```text
WAIT_UPSTREAM_CANCEL
WAIT_UPSTREAM_FINALLY=cancel
WAIT_RESULT_FINALLY=onComplete
```

This **illustrates the signals**, without guaranteeing exact log ordering or `SignalType.toString()` formatting. Reactor's corresponding enum constants are `CANCEL` and `ON_COMPLETE`. A pipeline completing normally downstream **does not contradict** upstream having been cancelled.

### 6.3. Resource Closes Even on Cancellation

```bash
curl -i "http://localhost:8080/demo/resource?waitMs=800"
```

Expected result: HTTP 504, body:

```json
{"outcome":"timeout","detail":"lease wait exceeded 250 ms"}
```

For each subscription, `Mono.using` invokes `DemoLease::new`, provides the resource to the inner source, and invokes `DemoLease::close` upon completion, error, or cancellation. On the timeout path, logs include `LEASE_OPENED` and `LEASE_CLOSED` (once per lease in this example). On the success path `waitMs=20`, the resource must likewise close: that is why cleanup belongs inside `using`, not only in an error branch.

`Mono.using` suits **lightweight, synchronous** cleanup. Never let `close()` execute long blocking I/O on the Netty event loop; when an async cleanup API is needed, use `usingWhen`.

## 7. Testing with `StepVerifier.withVirtualTime`

Testing cancellation/cleanup with **virtual time** avoids real timer waits and flaky tests. Crucial detail: declare timer publishers **inside the `Supplier` passed to `withVirtualTime`** so they use the virtual scheduler. Ensure `reactor-test` is included as in `build.gradle`.

**`src/test/java/com/example/reactivecleanup/CancellationTest.java`**:

```java
package com.example.reactivecleanup;

import java.time.Duration;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;

import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;

class CancellationTest {

    @Test
    void timeoutCancelsSlowSource() {
        AtomicInteger cancellations = new AtomicInteger();

        StepVerifier.withVirtualTime(() ->
                Mono.delay(Duration.ofSeconds(10))
                    .doOnCancel(cancellations::incrementAndGet)
                    .timeout(Duration.ofSeconds(1))
        )
        .expectSubscription()
        .thenAwait(Duration.ofSeconds(1))
        .expectError(TimeoutException.class)
        .verify();

        assertEquals(1, cancellations.get());
    }

    @Test
    void usingCleansResourceOnCancellation() {
        AtomicInteger closes = new AtomicInteger();

        StepVerifier.withVirtualTime(() ->
                Mono.using(
                        Object::new,
                        resource -> Mono.delay(Duration.ofSeconds(10)),
                        resource -> closes.incrementAndGet()
                )
                .timeout(Duration.ofSeconds(1))
        )
        .expectSubscription()
        .thenAwait(Duration.ofSeconds(1))
        .expectError(TimeoutException.class)
        .verify();

        assertEquals(1, closes.get());
    }
}
```

Run:

```bash
gradle test
```

Expected: **2 tests pass**; both cancellation and close counters equal 1. This tests actual behavior, not just fallback values. To verify HTTP 200/504 and JSON serialization, add a `WebTestClient` integration test as needed.

In real applications, add tests for **complete**, **onError**, **explicit cancel**, boundary-timing signals, retries, and cleanup failures. Never assert log ordering when callbacks can run on different schedulers.

## 8. When Async Cleanup Is Required: `Mono.usingWhen` / `Flux.usingWhen`

When a resource exposes a reactive API such as `closeAsync(): Mono<Void>`, writing:

```java
source.doFinally(signal -> resource.closeAsync());
```

is insufficient: the lambda merely builds a Publisher **with no subscription to run cleanup**. Calling `subscribe()` inside `doFinally` detaches cleanup errors/lifecycle from the source. Use the resource-scoped `usingWhen` operator, or your driver/framework's equivalent facility.

Below is an **illustrative API skeleton**, requiring an actual resource implementation and placement in an appropriate class:

```java
interface AsyncLease {
    Mono<String> fetch();
    Mono<Void> closeAsync();
}

Mono<String> queryWithLease(Mono<AsyncLease> acquireLease) {
    return Mono.usingWhen(
            acquireLease,
            AsyncLease::fetch,
            AsyncLease::closeAsync,
            (lease, failure) -> lease.closeAsync(),
            AsyncLease::closeAsync
    );
}
```

The arguments to `usingWhen` are:

1. Publisher to **acquire** the resource per subscription.
2. Function using the resource and returning the business Publisher.
3. Cleanup Publisher on **complete**.
4. Cleanup Publisher on **error**.
5. Cleanup Publisher on **cancel**.

In transactional applications, complete cleanup may commit while error/cancel cleanup rolls back. Never assume "close" automatically means rollback; use your driver and transaction manager's official transaction APIs.

Timeout placement changes which cleanup branch `usingWhen` invokes:

```java
// Outer timeout: upon expiration, usingWhen is cancelled by downstream;
// the asyncCancel branch may trigger.
queryWithLease(acquireLease).timeout(Duration.ofSeconds(2));

// Timeout inside the resource closure: TimeoutException is an onError
// inside the resource-usage scope;
// the asyncError branch of usingWhen may trigger.
Mono.usingWhen(
        acquireLease,
        lease -> lease.fetch().timeout(Duration.ofSeconds(2)),
        AsyncLease::closeAsync,
        (lease, error) -> lease.closeAsync(),
        AsyncLease::closeAsync
);
```

These snippets **are not standalone programs**, requiring definitions for `acquireLease` and `AsyncLease`. `Mono.usingWhen` can **delay downstream completion signals until the async cleanup publisher finishes**; cleanup errors can alter the final outcome. Once downstream has cancelled, cleanup errors cannot reliably be reported back to the disconnected subscriber, so add dedicated logging/metrics for cleanup.

Never close a connection twice: if a driver/framework already manages release/transactions, use its official mechanism instead of writing a parallel `closeAsync`.

## 9. HTTP Client Disconnects and Calling `WebClient`

### 9.1. Client Disconnect

```text
HTTP client ──► Spring WebFlux handler ──► Mono/Flux
                                              │
                                              ├── WebClient / R2DBC
                                              └── HTTP response writer

Client disconnect ──► transport detects ──► subscription cancelled
                                                  └── upstream / cleanup
```

The web server can propagate cancellation into the reactive chain when a client closes the connection and the transport detects it. **Detection speed and actual cancellability depend on Netty, drivers, and sources.** An already-dispatched transaction or HTTP call may still complete even though the client no longer awaits the response.

When streaming SSE/bodies, response status and headers may **already be committed**. If a late error occurs, the app cannot rewrite status to 504 and send fresh JSON; depending on protocol, close the stream, emit a protocol-defined error event, or let the client reconnect.

### 9.2. `WebClient`: Connect, Response I/O, and Operator Timeouts

```java
import java.time.Duration;

import io.netty.channel.ChannelOption;
import reactor.netty.http.client.HttpClient;

import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;

// Place inside a @Bean configuration or appropriate method.
HttpClient httpClient = HttpClient.create()
        .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 3000)
        .responseTimeout(Duration.ofSeconds(2));

WebClient client = WebClient.builder()
        .clientConnector(new ReactorClientHttpConnector(httpClient))
        .build();

Mono<String> response = client.get()
        .uri("https://example.org/api/ping")
        .retrieve()
        .bodyToMono(String.class)
        .timeout(Duration.ofSeconds(4));
```

This is an **illustrative snippet inside a method**, not a standalone file. `CONNECT_TIMEOUT_MILLIS` sets TCP connect timeout, `responseTimeout` bounds response waiting at the Reactor Netty layer, and `Mono.timeout` bounds signals from the subscribed publisher. Do not confuse these three semantics. The URL is illustrative only, without implying the endpoint exists.

`retrieve().bodyToMono(...)` relies on codecs/WebClient to manage body consumption along the standard path. When branching on HTTP status, `exchangeToMono`/`exchangeToFlux` permits conditional decoding, and once the handler publisher finishes, unconsumed body parts are checked and released. When directly handling `ClientResponse`, pooled `DataBuffer`s, or low-level HTTP streams, follow the matching ownership and cleanup contract.

### 9.3. Avoid Detached `subscribe()` Outside the Request

**Pattern to avoid inside controllers:**

```java
// Anti-pattern: spawns independent work outside the HTTP subscription.
webClient.get().uri("/slow")
        .retrieve().bodyToMono(String.class)
        .subscribe();

return Mono.just("accepted");
```

This is an illustrative snippet, not a full method. The HTTP response may return "accepted" before the WebClient call ends, and cancelling the request does not cancel the separate subscription created via `subscribe()`.

**Lifecycle-linked pattern:**

```java
// Inside a method returning Mono<String> with a configured webClient.
return webClient.get().uri("/slow")
        .retrieve()
        .bodyToMono(String.class)
        .timeout(Duration.ofSeconds(2));
```

The framework subscribes to that chain to complete the response. If you genuinely need background jobs, use a dedicated task/lifecycle, retry, and error-management mechanism.

## 10. Pooled `DataBuffer`s, Producer Callbacks, and Infinite Streams

### 10.1. Buffers Discarded on Cancel

Some operators maintain queues/prefetch buffers. When a subscriber cancels, elements **not yet emitted downstream** may be dropped. If those elements are releasable resources (such as pooled `DataBuffer`s owned by application code), releasing in `doOnNext` is insufficient.

`doOnDiscard(DataBuffer.class, DataBufferUtils::release)` is a tool when placed right after discard-supporting operators. Only use it **after confirming buffer ownership and avoiding double release**. Reactor does not promise every operator supports discard. If codecs, the framework, or drivers already manage buffers, never call `release` a second time.

For streams/files/connections opened per subscription, `using`/`usingWhen` clarify ownership. For infinite streams, always enforce stop/cancel/reconnect policies, bounded queues, and backpressure; never leave producers holding listeners or sockets after subscribers disappear.

### 10.2. Adapters Built with `Flux.create`

When wrapping legacy callback APIs, unregister callbacks when the sink completes or cancels. Illustrative skeleton:

```java
Flux<String> events = Flux.create(sink -> {
    // registerWithSource is an application-defined adapter API.
    Disposable registration = registerWithSource(
            value -> sink.next(value),
            error -> sink.error(error)
    );

    sink.onDispose(registration::dispose);
});
```

**This is not a standalone compilable file**, because `registerWithSource` is hypothetical; import `Flux`/`Disposable` and the concrete callback API. `sink.onDispose` runs on complete, error, and cancel; `onCancel` runs only on cancellation (and runs before `onDispose` when both are registered). Watch for races: producers may still fire callbacks while a sink is terminating.

### 10.3. Avoid Blocking on the Event Loop

Never invoke `Thread.sleep`, blocking JDBC, `block()`, or long blocking SDK calls directly on reactor-netty event-loop threads. Doing so stalls many requests, and **cancel does not reliably interrupt blocking calls**. If blocking APIs are unavoidable, isolate them on a scheduler like `Schedulers.boundedElastic()` with explicit concurrency/cancellation limits; prefer genuine reactive drivers whenever possible.

## 11. Observability and Error Handling

Log trace/request IDs, per-stage durations, and completion counts by `ON_COMPLETE`, `ON_ERROR`, and `CANCEL`. Put `doFinally` **near the upstream being measured** to learn the true cancellation cause, and at the end of the pipeline to see overall outcome. Never treat HTTP 504 or a fallback as proof that upstream stopped external side effects.

| Symptom | Common cause | How to inspect |
|---|---|---|
| Timeout triggers yet CPU/DB keeps running | Blocking source or third party lacks cancel support | Check drivers and task submission; measure when source actually finishes |
| Long-running Flux never triggers `timeout` | Elements arrive steadily faster than the per-item gap | Design an overall deadline or separate stream time limit |
| Upstream reports `CANCEL`, HTTP still returns 504/200 fallback | Timeout cancelled upstream, `onErrorResume` completed downstream | Inspect `doFinally` positions and response mapping |
| Resources keep opening without closing | Cleanup covers success/error only, missing cancel | Switch to `using`/`usingWhen` and test cancel paths |
| Async cleanup never executes | Only built `Mono<Void>` inside `doFinally` without subscribing | Use `usingWhen` or a proper transaction manager |
| Pool/heap grows under frequent cancellations | Pooled buffers/response bodies unreleased, producer leaks listeners | Audit ownership, discard hooks, Netty metrics, and connection pools |
| Client disconnects yet request keeps running | Transport hasn't detected disconnect or operation isn't cancellable | Trace cancellation signals and external request lifecycles |
| Streaming error returns no JSON 504 | Status/headers already committed before error | Design streaming error protocol, reconnect/heartbeats |
| Retries amplify load | Per-attempt timeout with many retries/backoff | Cap retries, total budget, idempotency, and rate limits |

In tests, avoid sleeping to wait for logs. Use `StepVerifier.withVirtualTime` for timers, assert close/cancel counters, and use `WebTestClient` integration tests when HTTP behavior needs verification.

## 12. Checklist for Designing Safe Pipelines

1. Clarify **which timeout**: connect, response I/O, Mono, Flux inter-element gap, or overall deadline.
2. Bind every upstream needing cancellation to the **same subscription**, avoiding accidental `subscribe()`.
3. Know that client/proxy/server can close connections independently; never assume error responses can always be sent after headers commit.
4. Establish who **owns each resource** and clean up on **complete, error, cancel**; use `usingWhen` for async release.
5. Never equate cancel with rollback or thread killing; side-effecting work needs idempotency/transactions.
6. Place logs/metrics at the right operator positions, distinguishing upstream state from post-fallback downstream outcome.
7. Test timeout, success, source error, cancellation, and cleanup without relying on stdout or real wall-clock timing.

## 13. Official Documentation

- Reactor Core 3.6.17 — `Mono.timeout`, `doFinally`, `doOnCancel`, `using`, and `usingWhen`: https://projectreactor.io/docs/core/3.6.17/api/reactor/core/publisher/Mono.html
- Reactor Core 3.6.11 — `Flux.timeout` between element emissions: https://projectreactor.io/docs/core/3.6.11/api/reactor/core/publisher/Flux.html
- Reactor Core 3.6 — guide on resources and discard: https://projectreactor.io/docs/core/3.6.7/reference/reactor-core-reference-guide-3.6.7.pdf
- Spring Framework — WebClient and Reactor Netty connection/response timeouts: https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-builder.html
- Spring Framework — `exchangeToMono`, body consumption, and release: https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-exchange.html

**Remember:** timeout is a *wait limit*; cancellation is a *subscription termination signal*; cleanup is *the duty to release resources across all three paths: complete, error, and cancel*. All three must be designed together for a reliable reactive pipeline.