# Testing Reactive Streams with Virtual Time and WebTestClient

## 1. Goal and real-world problem

Spring Boot WebFlux applications return `Mono<T>` or `Flux<T>` rather than synchronous values. A stream may emit immediately, wait seconds, fetch from another source, retry, time out, or stream indefinitely like Server-Sent Events (SSE). Testing with `Thread.sleep`, `block()`, and real waits makes test suites slow, flaky, and poor at expressing event contracts.

A common mistake:

~~~java
Flux<Long> ticks = Flux.interval(Duration.ofHours(1));
StepVerifier.create(ticks)
    .expectNext(0L)
    .verifyComplete();
~~~

This example both **fails to wait one hour** and expects an unbounded `Flux.interval` to complete on its own. Even raising the test timeout to several hours leaves the test poorly designed. Separate two questions:

1. **Stream logic under a virtual clock**: “When virtual time advances by one hour, what does the publisher emit, error with, or complete with?” → `StepVerifier.withVirtualTime`, `VirtualTimeScheduler`.
2. **WebFlux HTTP protocol**: “Does the endpoint return the right status/content-type, decode JSON/SSE properly, and complete or cancel the response stream cleanly?” → `WebTestClient` + `StepVerifier.create(responseBody)`.

This lesson belongs to **Integration Practice** in the **Spring Boot - testing** module, focusing on **Testing Reactive Streams with Virtual Time and WebTestClient**.

### Learning outcomes

After this lesson, you will be able to:

1. Distinguish assembly, subscription, demand/request, next, error, completion, and cancellation in Reactive Streams.
2. Understand `Mono`, `Flux`, `Schedulers.parallel()`, injected `Scheduler`s, and time operators `delay`, `interval`, `timeout`, and `retryWhen`.
3. Use `StepVerifier.create`, `StepVerifier.withVirtualTime`, `VirtualTimeScheduler`, `expectSubscription`, `expectNoEvent`, `thenAwait`, `thenCancel`, and `verify(Duration)` accurately.
4. Avoid the trap of **creating the publisher before the virtual scheduler is activated**.
5. Distinguish Reactor virtual clocks from real clocks in HTTP servers, external DBs/brokers, Netty, and non-Reactor libraries.
6. Test finite `Flux` streams with `verifyComplete` and long/infinite SSE streams with `thenCancel`.
7. Use `WebTestClient` at three levels: `bindToController`, `@WebFluxTest`, and `@SpringBootTest(webEnvironment = RANDOM_PORT)`.
8. Verify JSON responses, HTTP 404, `text/event-stream`, `FluxExchangeResult`, backpressure, and error propagation.
9. Distinguish `@MockBean` in a WebFlux slice from real services in full-context integration tests.
10. Separate virtual-time logic tests from HTTP streaming contracts to stay deterministic without testing the wrong boundary.
11. Build a complete **Java 17 + Spring Boot 3.3.5 + Gradle 8.8 + Reactor Test + JUnit Jupiter** project.
12. Diagnose hanging tests, fake timeouts, scheduler leaks, test races, and CI flakiness, supported by checklists and extension exercises.

**Golden rule:** Virtual time is a scheduler simulating time progression for Reactor operators using that scheduler. It **does not** speed up physical wall-clock time for networks, JDBC, REST servers in other JVMs, or plain `Thread.sleep`.

## 2. Mastering Reactive Streams signals

A `Publisher` is assembled before any subscriber arrives. Once a test subscribes, signals flow:

~~~text
Publisher assembly
       |
       v
Subscriber subscribes
       |
       v
onSubscribe(Subscription)   <-- request(n) / cancel()
       |
       +-- onNext(A)
       +-- onNext(B)
       +-- onNext(C)
       |
       +-- onComplete()  or  onError(Throwable)
~~~

`onComplete` and `onError` are **terminal signals**: a stream can never emit both. Cancellation is requested by the subscriber to stop receiving items, not an `onComplete` message sent by the server.

### 2.1. `Mono` and `Flux`

| Construct | How many values? | How does it terminate? |
| --- | --- | --- |
| `Mono.just(x)` | One | `onNext(x)`, `onComplete` |
| `Mono.empty()` | Zero | `onComplete` |
| `Mono.error(e)` | Zero | `onError(e)` |
| `Flux.just(a,b,c)` | Three | `onNext(a,b,c)`, `onComplete` |
| `Flux.interval(period)` | Potentially infinite | Never completes by itself |
| `Flux.interval(...).take(3)` | Three | Completes after the third item |
| `Flux.never()` | Zero | Emits no terminal signal |
| `Flux.concat(a, Flux.never())` | Values from `a`, then waits | Usually requires cancellation |

### 2.2. Why does execution begin only at subscribe time?

Many Reactor publishers are **cold**: assembly builds a pipeline blueprint. When subscribed to, it starts loading data or scheduling timers. `Mono.delay` and `Flux.interval` schedule onto a scheduler appropriately, yet **a scheduler reference can be captured right at assembly time**. Thus code creating a publisher **before** `StepVerifier.withVirtualTime` may capture the real scheduler.

### 2.3. Backpressure

Subscribers control how many items they want via `request(n)`. `StepVerifier.create(publisher, initialRequest)` lets you test demand. However, HTTP streaming also involves network buffers and codecs: a `StepVerifier` test on `Flux.range` does not prove backpressure traverses a reverse proxy or HTTP connection. Integration tests must measure behavior at the real boundary.

### 2.4. Shared state and thread safety

Reactive pipelines can switch threads via `publishOn`/`subscribeOn`. Never rely on scheduler execution order or unsynchronized mutable lists. In tests, `StepVerifier` serializes signal observation cleanly; when an app merges concurrent sources, define ordering semantics explicitly.

## 3. `StepVerifier` fundamentals

Required Gradle dependency:

~~~groovy
testImplementation 'io.projectreactor:reactor-test'
~~~

The Spring Boot BOM pins a Reactor version compatible with Spring WebFlux. Avoid overriding Reactor Core independently of the BOM just to grab a newer test API without verifying Spring Framework/Netty compatibility.

Example:

~~~java
StepVerifier.create(
        Flux.just("A", "B", "C"))
    .expectNext("A", "B", "C")
    .verifyComplete();
~~~

`verifyComplete()` asserts all expected items **and terminal completion**. If the publisher emits an extra unexpected item, the verifier fails.

Testing errors:

~~~java
StepVerifier.create(
        Mono.error(
            new IllegalArgumentException("invalid")))
    .expectErrorMatches(error ->
        error instanceof IllegalArgumentException
        && "invalid".equals(error.getMessage()))
    .verify();
~~~

Never use `verifyComplete()` on a publisher designed to emit `onError`.

### 3.1. `StepVerifier` can hang indefinitely

If you write:

~~~java
StepVerifier.create(Flux.never())
    .expectNext("never")
    .verify();
~~~

the test hangs because the item never arrives. Use a real-time verification timeout with `verify(Duration.ofSeconds(5))` where appropriate. For infinite streams, terminate explicitly with `thenCancel()`. For virtual-time tests, **advance the virtual clock** rather than raising the real timeout.

### 3.2. Never expect completion on an infinite SSE stream

~~~java
StepVerifier.create(
        Flux.concat(Flux.just("A", "B"), Flux.never()))
    .expectNext("A", "B")
    .thenCancel()
    .verify(Duration.ofSeconds(5));
~~~

This test intentionally cancels after two messages. Changing it to `verifyComplete` makes it fail or hang because the stream never completes.

## 4. How does virtual time work?

`StepVerifier.withVirtualTime` replaces Reactor's standard scheduler factories for the scope of verification, causing timed operators to run on **`VirtualTimeScheduler`** instead of waiting wall-clock time. The publisher must be built **lazily** after the virtual scheduler is active.

Correct example:

~~~java
StepVerifier.withVirtualTime(
        () -> Mono.delay(Duration.ofDays(1)))
    .expectSubscription()
    .expectNoEvent(Duration.ofDays(1))
    .expectNext(0L)
    .verifyComplete();
~~~

`Mono.delay` emits `0L` after one **virtual** day; the test finishes without waiting a real day. Because `expectNoEvent` treats the subscription signal itself as an event, place `expectSubscription()` beforehand.

### 4.1. Wrong: assembly before `VirtualTimeScheduler`

~~~java
Mono<Long> createdTooEarly =
    Mono.delay(Duration.ofDays(1));

// Avoid: the publisher may already have captured the real scheduler.
StepVerifier.withVirtualTime(() -> createdTooEarly)
    .expectSubscription()
    .thenAwait(Duration.ofDays(1))
    .expectNext(0L)
    .verifyComplete();
~~~

This is an **illustrative anti-pattern**, not part of the runnable tests. The lambda merely returns a pre-built publisher, bypassing virtual time. Fix it by moving the entire assembly inside the supplier or injecting an explicit `VirtualTimeScheduler` into the service.

### 4.2. `thenAwait` vs `expectNoEvent`

| Step | Meaning | Can `onNext` arrive while waiting? |
| --- | --- | --- |
| `thenAwait(Duration)` | Advance virtual clock or wait real time | Yes |
| `expectNoEvent(Duration)` | Advance/wait and fail on any signal | **No** |
| `expectNext(value)` | Expect exact item | Must match |
| `expectNextCount(n)` | Expect `n` items regardless of value | Yes |
| `expectSubscription()` | Expect subscription signal | Yes |
| `thenCancel()` | Cancel subscription | Not `onComplete` |
| `verifyComplete()` | Assert `onComplete` | Terminal |
| `expectError(...)` | Expect `onError` | Terminal |

To prove **nothing arrives before a deadline**, use `expectNoEvent`. To simply move timers forward, use `thenAwait`. Exact boundary timestamps can trigger emissions; structure test timelines cleanly without assuming how unmanaged schedulers order events.

### 4.3. Virtual time does not solve everything

Exceptions:

- `Thread.sleep` uses wall-clock time, untouched by the virtual scheduler.
- An HTTP server in **another JVM** has its own scheduler and clock.
- A custom `ScheduledExecutorService` is not replaced automatically.
- A scheduler captured before virtual-time setup continues running on real time.
- Blocking JDBC, Redis/Kafka brokers, and network I/O cannot be “fast-forwarded” by `StepVerifier`.
- `Instant.now()`/`System.currentTimeMillis()` do not read Reactor's virtual clock.
- Synchronous/blocking work inside an operator on the same scheduler can stall virtual-time advancement.
- Long/infinite immediate loops can hog the virtual scheduler thread.

When business logic reads wall-clock time, inject `java.time.Clock` to test timestamps; when it uses Reactor timers, inject `Scheduler` to test delays. `Clock` and `Scheduler` solve two different problems.

## 5. Choosing a virtual-time strategy

### Strategy A — `withVirtualTime` constructing the publisher inside the lambda

~~~java
StepVerifier.withVirtualTime(
        () -> Flux.interval(Duration.ofHours(1))
                .take(2))
    .expectSubscription()
    .thenAwait(Duration.ofHours(1))
    .expectNext(0L)
    .thenAwait(Duration.ofHours(1))
    .expectNext(1L)
    .verifyComplete();
~~~

Pros: minimal boilerplate, works naturally with Reactor operators defaulting to `Schedulers.parallel()`. Cons: swapping scheduler factories is JVM-global during the call; be careful with parallel tests or early-initialized schedulers.

### Strategy B — inject `VirtualTimeScheduler` directly

~~~java
VirtualTimeScheduler clock =
    VirtualTimeScheduler.create();

try {
    Flux<Long> values =
        Flux.interval(
            Duration.ofHours(1),
            Duration.ofHours(1),
            clock)
            .take(2);

    StepVerifier.create(values)
        .expectSubscription()
        .then(() ->
            clock.advanceTimeBy(Duration.ofHours(1)))
        .expectNext(0L)
        .then(() ->
            clock.advanceTimeBy(Duration.ofHours(1)))
        .expectNext(1L)
        .verifyComplete();
}
finally {
    clock.dispose();
}
~~~

Pros: isolated scheduler instance per test, easy lifecycle control, minimal interference with other tests. Cons: production code must accept an injected `Scheduler` for timed operations—which is usually good design anyway.

### Comparing the two strategies

| Criterion | `withVirtualTime` | Inject `VirtualTimeScheduler` |
| --- | --- | --- |
| Publisher creation | Must be lazy inside supplier | Can inject when building service |
| Scheduler ownership | Virtual factory scope | Per-test instance |
| Ease with default operators | Very easy | Requires passing scheduler to operators |
| Avoiding global scheduler interference | Must watch test parallelism | Safer |
| Testing very long durations | Yes | Yes |
| Cross-JVM HTTP servers | Does not apply automatically | Does not apply automatically |
| Cleanup | `StepVerifier` restores factory scope | Test disposes manually |
| Best used when | Pure timer operators | Service accepts `Scheduler` dependency |

Never call `VirtualTimeScheduler.getOrSet()` in `@BeforeAll` across classes and forget to reset: global state leaks easily into other tests. If you must touch factory hooks manually, document setup/teardown strictly.

## 6. `WebTestClient`: three ways to test WebFlux

`WebTestClient` is the client API for testing Reactive HTTP. With Spring WebFlux, three levels are common:

### 6.1. `bindToController`

No Spring Boot context needed:

~~~java
FeedController controller =
    new FeedController(fakeFeedService);

WebTestClient client =
    WebTestClient.bindToController(controller).build();
~~~

This is an **illustrative snippet**: `fakeFeedService` must be created matching the project's interface/constructor. It tests the controller and codecs over simulated WebFlux infrastructure without opening a TCP port.

### 6.2. `@WebFluxTest`

~~~java
@WebFluxTest(FeedController.class)
class FeedWebSliceTest {

    @Autowired
    WebTestClient client;

    @MockBean
    FeedService service;
}
~~~

Spring Boot auto-configures the WebFlux slice, controller, and `WebTestClient`. Ordinary `@Service` beans are not scanned in the slice; `@MockBean` (Boot 3.3) supplies the collaborator. Great for route, status, JSON, and SSE contracts. Note that for functional `RouterFunction` endpoints, `@WebFluxTest` does not auto-discover functional routes; import the router bean/config explicitly or use full context.

### 6.3. `@SpringBootTest(RANDOM_PORT)`

~~~java
@SpringBootTest(
    webEnvironment =
        SpringBootTest.WebEnvironment.RANDOM_PORT)
class FeedLiveHttpTest {
    @Autowired
    WebTestClient client;
}
~~~

For a **reactive WebFlux app**, Spring Boot auto-configures `WebTestClient` bound to the random port, providing real HTTP integration against a live Netty server. Because it uses real server/Netty clocks, keep delays short or provide dedicated control hooks. Never assume `StepVerifier.withVirtualTime` on the test client controls timers inside the entire server — especially across threads or JVMs.

### 6.4. `bindToServer`

~~~java
WebTestClient client =
    WebTestClient.bindToServer()
        .baseUrl("http://localhost:8080")
        .build();
~~~

Snippet for an already-running server. `bindToServer` hits the real network; port 8080 is not guaranteed to hold the right server or version, so CI tests must not hardcode this URL unless the pipeline manages that server. Under `RANDOM_PORT`, inject Boot's auto-configured `WebTestClient` to avoid port collisions.

## 7. Streaming SSE: `WebTestClient` + `FluxExchangeResult`

SSE typically uses content type `text/event-stream`; responses emit multiple events over time and may never terminate.

Standard pattern:

~~~java
FluxExchangeResult<FeedEvent> result =
    client.get()
        .uri("/api/feeds/news/events")
        .accept(MediaType.TEXT_EVENT_STREAM)
        .exchange()
        .expectStatus().isOk()
        .expectHeader().contentTypeCompatibleWith(
            MediaType.TEXT_EVENT_STREAM)
        .returnResult(FeedEvent.class);

StepVerifier.create(result.getResponseBody())
    .expectNext(event1, event2, event3)
    .verifyComplete();
~~~

For long or infinite streams:

~~~java
StepVerifier.create(result.getResponseBody())
    .expectNext(event1, event2)
    .thenCancel()
    .verify(Duration.ofSeconds(5));
~~~

**Both snippets above assume `client`, `event1`, `event2`, `event3`, and imports inside a test class**; the runnable project below shows complete classes.

Never call `expectBodyList` on an infinite SSE stream: it waits for stream completion and hangs forever. Use `returnResult(...).getResponseBody()` to verify streams incrementally.

### Status/headers and body happen in two phases

`exchange().expectStatus()...` checks response metadata. `StepVerifier` checks the streamed payload. If a stream errors **after HTTP response headers have already committed**, the HTTP status may still be 200 and the connection aborts mid-stream. Never assume mid-stream `onError` signals turn into HTTP 500; design protocol-level error events when needed.

## 8. Runnable project: Java 17 + Spring Boot 3.3.5 + Gradle 8.8

This small project serves a finite three-event SSE feed. In the live service, events arrive every 25 ms so HTTP tests stay fast. In virtual-time tests, the exact same business logic runs with intervals of **one virtual day or two virtual hours** without real waiting. Scheduler configuration is injected, avoiding forcing tests to hijack global `Schedulers` factories.

### 8.1. Directory tree

~~~text
reactive-virtual-time-lab/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
├── gradle/wrapper/
│   ├── gradle-wrapper.jar
│   └── gradle-wrapper.properties
└── src/
    ├── main/java/com/example/reactivelab/
    │   ├── ReactiveLabApplication.java
    │   ├── FeedSchedulersConfiguration.java
    │   ├── FeedEvent.java
    │   ├── FeedService.java
    │   └── FeedController.java
    └── test/java/com/example/reactivelab/
        ├── FeedVirtualTimeTest.java
        ├── FeedServiceContractTest.java
        ├── FeedWebSliceTest.java
        └── FeedLiveHttpTest.java
~~~

Gradle Wrapper scripts and `gradle-wrapper.jar` are generated by Gradle or provided by the repository. This Markdown article does not embed binary jars.

### 8.2. `settings.gradle`

~~~groovy
rootProject.name = 'reactive-virtual-time-lab'
~~~

### 8.3. `build.gradle`

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
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
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()

    testLogging {
        events 'passed', 'failed', 'skipped'
    }
}
~~~

`spring-boot-starter-webflux` brings Spring WebFlux, Reactor, and Netty; `reactor-test` provides `StepVerifier` and `VirtualTimeScheduler`. Boot's BOM aligns Reactor Core/Test versions. Never add `spring-boot-starter-web` merely for `WebTestClient`: having both MVC and WebFlux switches the default web application type to Servlet and alters test behavior.

### 8.4. `ReactiveLabApplication.java`

~~~java
package com.example.reactivelab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReactiveLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(
            ReactiveLabApplication.class, args);
    }
}
~~~

### 8.5. `FeedEvent.java`

~~~java
package com.example.reactivelab;

public record FeedEvent(
        String channel,
        long sequence,
        String kind) {
}
~~~

Example JSON:

~~~json
{
  "channel": "news",
  "sequence": 1,
  "kind": "tick"
}
~~~

Java `record` generates value-based `equals`/`hashCode`, so `StepVerifier.expectNext(new FeedEvent(...))` compares values reliably rather than object identity.

### 8.6. `FeedSchedulersConfiguration.java`

~~~java
package com.example.reactivelab;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import reactor.core.scheduler.Scheduler;
import reactor.core.scheduler.Schedulers;

@Configuration(proxyBeanMethods = false)
public class FeedSchedulersConfiguration {

    @Bean(name = "feedScheduler",
          destroyMethod = "dispose")
    Scheduler feedScheduler() {
        return Schedulers.newSingle("feed-clock");
    }
}
~~~

`Schedulers.newSingle` creates a scheduler **owned by the context**; when the context closes, Spring calls `dispose`. Avoid registering the shared `Schedulers.parallel()` directly as a disposable bean and accidentally disposing the shared scheduler for other components. `@WebFluxTest` with a mocked service does not need this scheduler.

### 8.7. `FeedService.java`

~~~java
package com.example.reactivelab;

import java.time.Duration;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Scheduler;

@Service
public class FeedService {

    private final Scheduler scheduler;

    public FeedService(
            @Qualifier("feedScheduler")
            Scheduler scheduler) {
        this.scheduler = scheduler;
    }

    public Flux<FeedEvent> events(
            String channel,
            Duration interval,
            int count) {

        if (channel == null || channel.isBlank()) {
            return Flux.error(
                new IllegalArgumentException(
                    "channel must not be blank"));
        }

        if (interval == null
                || interval.isZero()
                || interval.isNegative()) {
            return Flux.error(
                new IllegalArgumentException(
                    "interval must be positive"));
        }

        if (count <= 0) {
            return Flux.error(
                new IllegalArgumentException(
                    "count must be positive"));
        }

        return Flux.interval(
                interval,
                interval,
                scheduler)
            .map(index -> new FeedEvent(
                channel, index + 1, "tick"))
            .take(count);
    }

    public Mono<FeedEvent> snapshot(String channel) {
        return Mono.defer(() -> {
            if (channel == null
                    || channel.isBlank()) {
                return Mono.error(
                    new IllegalArgumentException(
                        "channel must not be blank"));
            }

            return Mono.just(
                new FeedEvent(
                    channel, 0L, "snapshot"));
        });
    }
}
~~~

**Design notes:**

- Never uses blocking `sleep` to wait for events.
- `Flux.interval(firstDelay, period, scheduler)` runs timers on the injected scheduler.
- `take(count)` turns the interval stream into a finite stream emitting `onComplete`.
- `Flux.error` emits errors inside Reactive Streams rather than throwing synchronously before a subscriber arrives.
- `Mono.defer` defers validation/data creation until subscription.
- Same source uses a real scheduler in the full app and a virtual scheduler in unit tests.
- `channel`, `interval`, and `count` are validated so invalid counts never create infinite streams.

### 8.8. `FeedController.java`

~~~java
package com.example.reactivelab;

import java.time.Duration;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/feeds")
public class FeedController {

    public static final Duration HTTP_INTERVAL =
        Duration.ofMillis(25);

    private final FeedService service;

    public FeedController(FeedService service) {
        this.service = service;
    }

    @GetMapping(
        path = "/{channel}/snapshot",
        produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<FeedEvent> snapshot(
            @PathVariable("channel") String channel) {

        return service.snapshot(channel);
    }

    @GetMapping(
        path = "/{channel}/events",
        produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public Flux<FeedEvent> events(
            @PathVariable("channel") String channel) {

        return service.events(
            channel, HTTP_INTERVAL, 3);
    }
}
~~~

Two routes:

| Method/path | Content type | Contract |
| --- | --- | --- |
| `GET /api/feeds/{channel}/snapshot` | `application/json` | `Mono<FeedEvent>` with sequence 0, kind `snapshot` |
| `GET /api/feeds/{channel}/events` | `text/event-stream` | `Flux<FeedEvent>` emitting 1, 2, 3 then completing |

The SSE endpoint uses 25 ms so live HTTP tests finish quickly; service virtual-time tests use long intervals to verify exact semantics. Never treat 25 ms as a production SLA — in real systems intervals come from config or event sources.

## 9. `FeedVirtualTimeTest`: six JUnit tests

**src/test/java/com/example/reactivelab/FeedVirtualTimeTest.java**

~~~java
package com.example.reactivelab;

import java.time.Duration;
import java.util.concurrent.TimeoutException;

import org.junit.jupiter.api.Test;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;
import reactor.test.StepVerifier;
import reactor.test.scheduler.VirtualTimeScheduler;

import static org.junit.jupiter.api.Assertions.*;

class FeedVirtualTimeTest {

    @Test
    void oneDayDelayFinishesWithoutWaitingOneDay() {
        StepVerifier.withVirtualTime(
                () -> Mono.delay(Duration.ofDays(1)))
            .expectSubscription()
            .expectNoEvent(Duration.ofDays(1))
            .expectNext(0L)
            .verifyComplete();
    }

    @Test
    void serviceBuiltInsideSupplierUsesVirtualFactory() {
        StepVerifier.withVirtualTime(() -> {
            FeedService service =
                new FeedService(
                    Schedulers.parallel());

            return service.events(
                "news", Duration.ofHours(2), 2);
        })
        .expectSubscription()
        .thenAwait(Duration.ofHours(2))
        .expectNext(
            new FeedEvent("news", 1L, "tick"))
        .thenAwait(Duration.ofHours(2))
        .expectNext(
            new FeedEvent("news", 2L, "tick"))
        .verifyComplete();
    }

    @Test
    void explicitVirtualSchedulerControlsService()
            throws Exception {

        VirtualTimeScheduler clock =
            VirtualTimeScheduler.create();

        try {
            FeedService service =
                new FeedService(clock);

            StepVerifier.create(
                service.events(
                    "orders",
                    Duration.ofDays(1),
                    3))
                .expectSubscription()
                .then(() ->
                    clock.advanceTimeBy(
                        Duration.ofDays(1)))
                .expectNext(
                    new FeedEvent(
                        "orders", 1L, "tick"))
                .then(() ->
                    clock.advanceTimeBy(
                        Duration.ofDays(1)))
                .expectNext(
                    new FeedEvent(
                        "orders", 2L, "tick"))
                .then(() ->
                    clock.advanceTimeBy(
                        Duration.ofDays(1)))
                .expectNext(
                    new FeedEvent(
                        "orders", 3L, "tick"))
                .verifyComplete();
        }
        finally {
            clock.dispose();
        }
    }

    @Test
    void timeoutErrorAppearsAtVirtualDeadline() {
        StepVerifier.withVirtualTime(
                () -> Mono.never()
                    .timeout(Duration.ofHours(5)))
            .expectSubscription()
            .expectNoEvent(Duration.ofHours(5))
            .expectError(TimeoutException.class)
            .verify();
    }

    @Test
    void infiniteTicksCanBeCanceled() {
        StepVerifier.withVirtualTime(
                () -> Flux.interval(
                    Duration.ofDays(1)))
            .expectSubscription()
            .thenAwait(Duration.ofDays(2))
            .expectNext(0L, 1L)
            .thenCancel()
            .verify(Duration.ofSeconds(5));
    }

    @Test
    void backpressureRequiresExplicitDemand() {
        StepVerifier.create(
                Flux.range(1, 5),
                0)
            .expectSubscription()
            .thenRequest(2)
            .expectNext(1, 2)
            .thenRequest(3)
            .expectNext(3, 4, 5)
            .verifyComplete();
    }
}
~~~

### 9.1. One virtual day tests time logic, not wall-clock benchmarks

The first method verifies `Mono.delay` fires after one virtual day. Never assert “test completed in 0 ms” as a guarantee; CPU scheduling and build overhead vary.

### 9.2. The supplier must assemble the pipeline lazily

In `serviceBuiltInsideSupplierUsesVirtualFactory`, even constructing `FeedService(Schedulers.parallel())` sits **inside the lambda**. If the service were built before `withVirtualTime` and held onto a real scheduler, timed operators would not follow virtual time.

### 9.3. Injecting an explicit scheduler isolates global state

`explicitVirtualSchedulerControlsService` creates a dedicated scheduler, advances time via callbacks, and disposes it in `finally`. Other tests remain unaffected by global scheduler factory swaps. Under parallel execution, explicit scheduler injection is usually safer and easier to reason about.

### 9.4. Timeout tests must emit the right error

`Mono.never().timeout(...)` emits `TimeoutException` at the deadline. That tests the operator timeout, **not network timeouts or reverse-proxy timeouts**. In HTTP streaming, different timeout layers need separate tests.

### 9.5. `thenCancel` is not `verifyComplete`

An infinite `Flux.interval` must be canceled once enough items arrive. Calling `verifyComplete` contradicts the contract. Add dedicated resource-disposal tests if downstream cancellation cleanup is a business requirement.

### 9.6. Backpressure tests verify `request(n)`

`StepVerifier` starts with initial demand 0, then requests 2 and 3 items. `Flux.range` honors demand and completes after 5 items, without `Thread.sleep` or network timing dependencies.

### 9.7. Real limits of the test classes

`withVirtualTime` swaps the process-wide Reactor scheduler factory during the test; never run multiple tests mutating the global scheduler concurrently without isolation. In this project, Gradle's `Test` task runs one test JVM and JUnit parallel mode is off. If parallelizing later, prefer explicit scheduler injection or test isolation.

## 10. `FeedServiceContractTest`: reactive errors and snapshot

**src/test/java/com/example/reactivelab/FeedServiceContractTest.java**

~~~java
package com.example.reactivelab;

import java.time.Duration;

import org.junit.jupiter.api.Test;

import reactor.core.scheduler.Schedulers;
import reactor.test.StepVerifier;

class FeedServiceContractTest {

    private final FeedService service =
        new FeedService(Schedulers.immediate());

    @Test
    void snapshotEmitsOneRecordAndCompletes() {
        StepVerifier.create(
                service.snapshot("news"))
            .expectNext(
                new FeedEvent(
                    "news", 0L, "snapshot"))
            .verifyComplete();
    }

    @Test
    void blankChannelReturnsReactiveError() {
        StepVerifier.create(
                service.snapshot(" "))
            .expectErrorMatches(error ->
                error instanceof IllegalArgumentException
                && error.getMessage()
                    .contains("channel"))
            .verify();
    }

    @Test
    void zeroIntervalIsRejectedBeforeScheduling() {
        StepVerifier.create(
                service.events(
                    "news", Duration.ZERO, 2))
            .expectError(
                IllegalArgumentException.class)
            .verify();
    }

    @Test
    void nonPositiveCountIsRejected() {
        StepVerifier.create(
                service.events(
                    "news",
                    Duration.ofSeconds(1),
                    0))
            .expectError(
                IllegalArgumentException.class)
            .verify();
    }
}
~~~

`Schedulers.immediate()` executes no real timers here because these cases only call `snapshot` or return `Flux.error` before `Flux.interval`. Never use the immediate scheduler for positive timed interval tests: timed scheduling may not behave as expected. For positive timed behavior, use `VirtualTimeScheduler` or a properly scoped real scheduler.

### Testing validation without blocking

`StepVerifier.expectError` observes `onError`, unlike `assertThrows(() -> service.events(...))`, because the method intentionally returns `Flux.error` instead of throwing synchronously at call time. Distinguishing **assembly-time** from **subscription-time** errors keeps tests faithful to the Reactive Streams contract.

## 11. `FeedWebSliceTest`: `WebTestClient` HTTP + SSE

**src/test/java/com/example/reactivelab/FeedWebSliceTest.java**

~~~java
package com.example.reactivelab;

import java.time.Duration;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.WebFluxTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.FluxExchangeResult;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.web.server.ResponseStatusException;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

@WebFluxTest(FeedController.class)
class FeedWebSliceTest {

    @Autowired
    WebTestClient client;

    @MockBean
    FeedService service;

    private static FeedEvent event(
            long sequence) {
        return new FeedEvent(
            "news", sequence, "tick");
    }

    @Test
    void snapshotHasJsonAndExpectedFields() {
        when(service.snapshot("news"))
            .thenReturn(Mono.just(
                new FeedEvent(
                    "news", 0L, "snapshot")));

        client.get()
            .uri("/api/feeds/news/snapshot")
            .accept(MediaType.APPLICATION_JSON)
            .exchange()
            .expectStatus().isOk()
            .expectHeader()
                .contentTypeCompatibleWith(
                    MediaType.APPLICATION_JSON)
            .expectBody()
            .jsonPath("$.channel")
                .isEqualTo("news")
            .jsonPath("$.sequence")
                .isEqualTo(0)
            .jsonPath("$.kind")
                .isEqualTo("snapshot");

        verify(service).snapshot("news");
    }

    @Test
    void finiteSseCanBeDecodedAsFlux() {
        when(service.events(
                "news",
                FeedController.HTTP_INTERVAL,
                3))
            .thenReturn(Flux.just(
                event(1), event(2), event(3)));

        FluxExchangeResult<FeedEvent> result =
            client.get()
                .uri("/api/feeds/news/events")
                .accept(MediaType.TEXT_EVENT_STREAM)
                .exchange()
                .expectStatus().isOk()
                .expectHeader()
                    .contentTypeCompatibleWith(
                        MediaType.TEXT_EVENT_STREAM)
                .returnResult(FeedEvent.class);

        StepVerifier.create(
                result.getResponseBody())
            .expectNext(
                event(1), event(2), event(3))
            .verifyComplete();

        verify(service).events(
            "news", FeedController.HTTP_INTERVAL, 3);
    }

    @Test
    void longLivedSseIsCanceledByConsumer() {
        when(service.events(
                "news",
                FeedController.HTTP_INTERVAL,
                3))
            .thenReturn(
                Flux.concat(
                    Flux.just(event(1), event(2)),
                    Flux.never()));

        FluxExchangeResult<FeedEvent> result =
            client.get()
                .uri("/api/feeds/news/events")
                .accept(MediaType.TEXT_EVENT_STREAM)
                .exchange()
                .expectStatus().isOk()
                .returnResult(FeedEvent.class);

        StepVerifier.create(
                result.getResponseBody())
            .expectNext(event(1), event(2))
            .thenCancel()
            .verify(Duration.ofSeconds(5));
    }

    @Test
    void snapshotErrorMapsToHttp404() {
        when(service.snapshot("missing"))
            .thenReturn(Mono.error(
                new ResponseStatusException(
                    HttpStatus.NOT_FOUND,
                    "channel not found")));

        client.get()
            .uri("/api/feeds/missing/snapshot")
            .exchange()
            .expectStatus().isNotFound();
    }
}
~~~

### 11.1. Why mock the service in the WebFlux slice?

`@WebFluxTest(FeedController.class)` builds only the WebFlux slice components without scanning regular `@Service` beans. `@MockBean` registers a valid mock in the Spring context under Spring Boot 3.3. There is no need to import `FeedSchedulersConfiguration` or start a real scheduler thread just to verify controller contracts.

### 11.2. Distinguishing JSON snapshot from SSE

`snapshot` is a finite `Mono<FeedEvent>`, tested with `expectBody().jsonPath(...)`. `events` is a `Flux<FeedEvent>`, tested via `returnResult(FeedEvent.class)` to decode each SSE data event. Never use `expectBodyList` on long-lived streams.

### 11.3. Testing SSE needs no virtual time when the service is mocked

The mock returns `Flux.just(...)` immediately. That **does not test interval timing** — interval timing was already verified in `FeedVirtualTimeTest`. This is proper separation of concerns: controller tests verify routing/codecs/media types, while service tests verify timing.

### 11.4. Cancellation is a consumer signal

`longLivedSseIsCanceledByConsumer` cancels the response stream after two events. It **does not** prove upstream sockets/server resources cleaned up instantaneously; if cancellation cleanup is an SLO, add `doFinally` hooks or metrics and assert with async propagation in mind.

### 11.5. 404 before response commit

`snapshotErrorMapsToHttp404` tests an error raised **before any item emits** in the response. Once a streaming response commits after its first item, HTTP status usually cannot change; handle mid-stream errors via protocol-level error events or another strategy.

## 12. `FeedLiveHttpTest`: full context and random port

**src/test/java/com/example/reactivelab/FeedLiveHttpTest.java**

~~~java
package com.example.reactivelab;

import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.FluxExchangeResult;
import org.springframework.test.web.reactive.server.WebTestClient;

import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest(
    classes = ReactiveLabApplication.class,
    webEnvironment =
        SpringBootTest.WebEnvironment.RANDOM_PORT)
class FeedLiveHttpTest {

    @Autowired
    WebTestClient client;

    @Test
    void realServerServesSnapshotJson() {
        client.get()
            .uri("/api/feeds/news/snapshot")
            .accept(MediaType.APPLICATION_JSON)
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.channel")
                .isEqualTo("news")
            .jsonPath("$.sequence")
                .isEqualTo(0)
            .jsonPath("$.kind")
                .isEqualTo("snapshot");
    }

    @Test
    void realServerCompletesThreeSseEvents() {
        FluxExchangeResult<FeedEvent> result =
            client.get()
                .uri("/api/feeds/news/events")
                .accept(MediaType.TEXT_EVENT_STREAM)
                .exchange()
                .expectStatus().isOk()
                .expectHeader()
                    .contentTypeCompatibleWith(
                        MediaType.TEXT_EVENT_STREAM)
                .returnResult(FeedEvent.class);

        StepVerifier.create(
                result.getResponseBody())
            .expectNext(
                new FeedEvent("news", 1L, "tick"),
                new FeedEvent("news", 2L, "tick"),
                new FeedEvent("news", 3L, "tick"))
            .verifyComplete();
    }

    @Test
    void realServerResponseCanBeCanceled() {
        FluxExchangeResult<FeedEvent> result =
            client.get()
                .uri("/api/feeds/news/events")
                .accept(MediaType.TEXT_EVENT_STREAM)
                .exchange()
                .expectStatus().isOk()
                .returnResult(FeedEvent.class);

        StepVerifier.create(
                result.getResponseBody())
            .expectNext(
                new FeedEvent("news", 1L, "tick"))
            .thenCancel()
            .verify(Duration.ofSeconds(5));
    }
}
~~~

### 12.1. Why not use virtual time in this HTTP test?

Spring Boot starts a real WebFlux server on a random port. Netty and WebFlux request processing use their own schedulers, threads, and connection lifecycles; wrapping HTTP responses in `StepVerifier.withVirtualTime` mutates Reactor global factories in the test JVM while **failing to safely control the entire server path**. The lesson uses a 25 ms interval for real HTTP and reserves virtual time for testing timed domain `Publisher`s.

### 12.2. What value does the real HTTP test still add?

It proves app startup, server binding, real routing, codecs, SSE serialization, finite completion, and client cancellation across a genuine network boundary. It does not replace Testcontainers database/broker integration if real streams depend on Redis or Kafka.

### 12.3. Random port and `WebTestClient` addressing

Spring Boot reactive `RANDOM_PORT` tests auto-configure `WebTestClient` pointing to the real server port. Never hardcode `localhost:8080`. Never take `@WebFluxTest`'s client and claim you tested TCP transport: mocked WebFlux opens no port.

## 13. Total test count in the project

| Test class | `@Test` count | Focus |
| --- | ---: | --- |
| `FeedVirtualTimeTest` | 6 | `Mono.delay`, virtual factory, explicit scheduler, timeout, cancel, demand |
| `FeedServiceContractTest` | 4 | snapshot, blank channel, interval/count validation |
| `FeedWebSliceTest` | 4 | JSON, finite SSE, SSE cancellation, 404 in mocked WebFlux |
| `FeedLiveHttpTest` | 3 | real HTTP snapshot, real SSE completion, HTTP cancellation |
| **Total** | **17** | Timed `Publisher` + HTTP streaming contract |

**Transparency note:** These are **17 designed `@Test` methods** in Markdown. They were not executed in the authoring environment. Never treat “expected to pass” as real JUnit/CI output; after creating the project, run Gradle and inspect JUnit reports.

### Run commands

Linux/macOS:

~~~bash
./gradlew test
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat test
~~~

If the wrapper is not present yet and a compatible Gradle is installed:

~~~bash
gradle wrapper --gradle-version 8.8 --distribution-type bin
~~~

Run individual classes:

~~~bash
./gradlew test --tests 'com.example.reactivelab.FeedVirtualTimeTest'
./gradlew test --tests 'com.example.reactivelab.FeedServiceContractTest'
./gradlew test --tests 'com.example.reactivelab.FeedWebSliceTest'
./gradlew test --tests 'com.example.reactivelab.FeedLiveHttpTest'
~~~

Force re-execution if the Gradle task is `UP-TO-DATE`:

~~~bash
./gradlew test --rerun-tasks --stacktrace
~~~

JUnit HTML/XML outputs:

~~~text
build/reports/tests/test/index.html
build/test-results/test/TEST-com.example.reactivelab.FeedVirtualTimeTest.xml
build/test-results/test/TEST-com.example.reactivelab.FeedServiceContractTest.xml
build/test-results/test/TEST-com.example.reactivelab.FeedWebSliceTest.xml
build/test-results/test/TEST-com.example.reactivelab.FeedLiveHttpTest.xml
~~~

Response body outputs follow deterministically from source; Gradle duration, PID/port, startup logs, and test order **vary per run**, so never fabricate stdout.

## 14. Differences between virtual clocks and real clocks

A sound testing workflow must know **who owns each clock**.

| Component | Supports virtual time? | Notes |
| --- | --- | --- |
| Default `Mono.delay` | Yes, if operator built after setup | `withVirtualTime` |
| `Flux.interval` with explicit scheduler | Yes | Inject `VirtualTimeScheduler` |
| `Mono.timeout` using Reactor scheduler | Yes | Still requires lazy publisher creation |
| `Retry.fixedDelay` with configured scheduler | Yes | Tests retry count and timeline |
| `Thread.sleep` | No | Blocking wall-clock wait |
| `Instant.now()` | Does not change automatically | Inject `java.time.Clock` |
| Non-Reactor `ScheduledExecutorService` | Does not change automatically | Abstract behind interface |
| Netty HTTP server | Not controlled by test-client clock | Use short real delays or controlled server scheduler |
| Out-of-process Kafka broker | No | Broker has its own clock/lifecycle |
| PostgreSQL transaction timeout | No | Database has its own clock |
| Redis TTL | No | Redis server has its own clock |
| Remote SSE service | No | Real network boundary |
| `Flux.just` | Not needed | No time dependency |

Inside the same JVM, a virtual factory swap can affect Reactor schedulers used by both test and server, yet **that is not a stable isolation architecture** for HTTP tests. Never rely on race-sensitive global state to make network tests run “fast”.

## 15. Timed operator patterns worth testing separately

### 15.1. Delay

~~~java
Mono<String> message =
    Mono.just("READY")
        .delayElement(Duration.ofMinutes(30));

StepVerifier.withVirtualTime(
        () -> Mono.just("READY")
            .delayElement(Duration.ofMinutes(30)))
    .expectSubscription()
    .expectNoEvent(Duration.ofMinutes(30))
    .expectNext("READY")
    .verifyComplete();
~~~

The pre-created `message` variable illustrates **the hazard of eager assembly**, whereas the lambda expression shows the proper way. With `delayElement`, do not confuse it with `delaySubscription`: they delay different phases.

### 15.2. Timeout and fallback

~~~java
StepVerifier.withVirtualTime(
        () -> Mono.<String>never()
            .timeout(
                Duration.ofHours(4),
                Mono.just("PENDING")))
    .expectSubscription()
    .thenAwait(Duration.ofHours(4))
    .expectNext("PENDING")
    .verifyComplete();
~~~

This is a standalone snippet given imports for `Mono`, `Duration`, and `StepVerifier`. Fallbacks must make business sense; if a timeout must be an error, assert `TimeoutException` rather than blindly falling back to `PENDING`.

### 15.3. Retry with backoff

Reactor's `Retry.fixedDelay` and `Retry.backoff` have distinct policies: fixed vs exponential, optional jitter, error filters, and custom schedulers. For deterministic tests:

- Wrap sources in `Flux.defer`/`Mono.defer` so each attempt re-executes the source.
- Count subscriptions/attempts with `AtomicInteger`.
- For `Retry.backoff`, disable jitter or assert within designed tolerances.
- Run on `VirtualTimeScheduler` or construct the whole publisher inside `withVirtualTime`.
- Remember “3 retries” means **4 total subscriptions** (initial + 3).
- Never retry every exception blindly, especially validation or authorization errors.
- If retries call real HTTP or brokers, virtual time tests only scheduler policy, not skipping remote calls.

### 15.4. `debounce`/`throttle`/`bufferTimeout`

`debounce` emits only after a quiet period with no newer items. `sample`/`throttleFirst` select per time window. `bufferTimeout` flushes by count or deadline. Use `TestPublisher` to emit exact source signals and `VirtualTimeScheduler` to advance the clock; test emissions right at **boundaries**, upstream completion/error, and downstream cancellation.

### 15.5. Setting real-time timeouts on verifiers

~~~java
StepVerifier.create(
        Flux.just("A", "B"))
    .expectNext("A", "B")
    .verifyComplete();
~~~

Whenever a publisher risks hanging, use `thenCancel().verify(Duration.ofSeconds(5))` or a verification terminal method with an explicit timeout. A global `StepVerifier` default timeout helps guard the suite, though it never replaces virtual-time advancement.

## 16. `TestPublisher` and simulating event sources

`reactor-test` also provides `TestPublisher<T>`, useful for manually pushing `onNext`, `complete`, and `error` from an upstream source without relying on real timers.

Example sketch:

~~~java
TestPublisher<String> source =
    TestPublisher.create();

Flux<String> flux = source.flux();

StepVerifier.create(flux)
    .then(() -> source.next("A", "B"))
    .expectNext("A", "B")
    .then(source::complete)
    .verifyComplete();
~~~

This snippet belongs inside a method with proper imports (`reactor.test.publisher.TestPublisher`) to test upstream signals. For backpressure scenarios, consider `TestPublisher.createCold()`/`TestPublisher.createNoncompliant(...)` per Reactor API docs and verify contract compliance rather than accidentally violating Reactive Streams rules.

### Separating dimensions of testing

- **`TestPublisher`** tests how a pipeline reacts to upstream values and errors.
- **`VirtualTimeScheduler`** tests how a pipeline handles time progression.
- **`WebTestClient`** tests HTTP wire behavior of the pipeline's output.
- **`StepVerifier`** is the assertion DSL tying all three together.

Do not cram all three into one test; design each scenario with a clear failure cause.

## 17. Infinite SSE and cancellation

A production SSE endpoint may never close on its own:

~~~java
@GetMapping(
    path="/updates",
    produces=MediaType.TEXT_EVENT_STREAM_VALUE)
Flux<FeedEvent> updates() {
    return eventService.liveEvents();
}
~~~

Illustrative snippet; `eventService` needs a real implementation. HTTP tests should:

1. Send GET with `Accept: text/event-stream`.
2. Assert status and content type.
3. Obtain `FluxExchangeResult<FeedEvent>`.
4. Wrap with `StepVerifier.create(result.getResponseBody())`.
5. Assert a few specific events/sequences/order.
6. Call `thenCancel` before timeout.
7. If cancellation cleanup matters, verify resource disposal at the service layer via metrics/hooks.

### When should you use `verifyComplete`?

Only when the contract states the stream is finite and completes. The demo's `events(...).take(3)` completes after three events, so finite SSE tests use `verifyComplete`. For live feeds, expecting completion is wrong.

### HTTP disconnects can arrive with a delay

Client-side cancellation does not guarantee the server producer's cleanup callback runs **on the exact same thread or microsecond**. Asserting an atomic counter immediately after `thenCancel` against a live HTTP server can flake because disconnects propagate asynchronously. Assert with eventual checks/metrics and bounded real timeouts; never use `Thread.sleep(500)` assuming fixed network latency.

## 18. Comparing reactive error scenarios

| Scenario | Reactive signal | Possible HTTP behavior |
| --- | --- | --- |
| Valid source emits 3 then completes | `onNext`×3, `onComplete` | 200 + SSE closes cleanly |
| Source errors right on subscribe | `onError` before body | 4xx/5xx depending on exception mapping |
| Error after 2 SSE events | `onNext`×2, `onError` | HTTP status already committed; stream drops or emits custom error frame |
| Client cancels after first event | downstream cancel | Server stops producer upon seeing cancel |
| Timeout on `Mono` before response | `onError(TimeoutException)` | May map to 5xx/custom status |
| Infinite stream never canceled | No terminal signal | Client test hangs |
| `Flux` has zero demand | Stops emitting as expected | Backpressure/consumer stall |
| Event stuck in buffer/codec | Publisher emitted `onNext`, client hasn't decoded | Streaming flush/framing issue |
| Java exception in mapper | `onError` | Depends on phase; response error |
| External broker disconnected | retry/error/resource issue | Cannot be solved with vTime alone |

To test an **HTTP error response contract**, explicitly define `@RestControllerAdvice`, `@ExceptionHandler`, or `ResponseStatusException`, then assert status/body. Never assume `onError` automatically becomes HTTP 503.

## 19. Streaming media types

| Content type | Used when | How to test |
| --- | --- | --- |
| `application/json` | One finite JSON object/list | `expectBody`/`jsonPath` |
| `text/event-stream` | SSE events | `returnResult(type)` + `StepVerifier` |
| `application/x-ndjson` | Newline-delimited JSON streaming | `returnResult(type)`, codec framing |
| `application/json` for finite `Flux` | May serialize as JSON array | `expectBodyList`/JSON assertions if finite |
| `application/octet-stream` | Binary streaming | Check byte buffers/framing, memory |
| `text/plain` | Text flux | `returnResult(String.class)`, encoding |

Never take a `Flux<T>` return type and assume the response is always SSE. HTTP media type and content negotiation determine encoding. Tests must send `Accept` and assert `Content-Type`. Streaming behavior also depends on HTTP server flushing, buffers, and proxies.

## 20. Functional routes and `WebTestClient`

A Spring WebFlux app may use `RouterFunction<ServerResponse>` instead of `@RestController`:

~~~java
@Bean
RouterFunction<ServerResponse> feedRoutes(
        FeedService service) {

    return RouterFunctions.route(
        RequestPredicates.GET("/functional/feeds"),
        request -> ServerResponse.ok()
            .contentType(MediaType.TEXT_EVENT_STREAM)
            .body(
                service.events(
                    "news", Duration.ofMillis(25), 3),
                FeedEvent.class));
}
~~~

Illustrative snippet inside a `@Configuration` importing WebFlux functional routing APIs. `@WebFluxTest` does not automatically detect all functional route beans; import the router configuration/function explicitly or use `@SpringBootTest`.

Never use `@WebMvcTest` to test WebFlux functional endpoints: that is the Spring MVC slice with different infrastructure. `WebTestClient` can work against MVC in mock/live setups supported by Spring, yet with `@WebFluxTest` this lesson focuses strictly on the reactive stack.

## 21. Schedulers, context cache, and concurrency

### 21.1. `Schedulers.parallel` vs `newSingle`

`Schedulers.parallel()` is a shared factory-managed scheduler. `Schedulers.newSingle(name)` creates a dedicated scheduler instance. When injecting a scheduler as a bean, clarify **ownership**: who creates it, who disposes it, and whether it is process-wide shared. The demo uses `newSingle` with `destroyMethod=dispose` so Spring owns its lifecycle.

### 21.2. Test context caching

Spring's TestContext cache retains `ApplicationContext` instances across tests sharing the same configuration key within one JVM. `@WebFluxTest` uses a smaller context distinct from `@SpringBootTest`. Overusing `@DirtiesContext` drives up startup costs. Never use `@DirtiesContext` to reset a Reactor publisher subscription; each subscription already has its own lifecycle.

### 21.3. Global effect of `VirtualTimeScheduler`

`StepVerifier.withVirtualTime` temporarily swaps Reactor's global `Schedulers` factory, so avoid running multiple tests mutating the global factory concurrently in the same JVM. Injecting `VirtualTimeScheduler.create()` gives stronger isolation. Ensure virtual schedulers are disposed/restored cleanly rather than stored in shared static fields across tests.

### 21.4. Mocks and backpressure under parallel execution

`@MockBean` in a WebFlux slice is a Spring context bean mock; two test methods running concurrently that stub/reset the same mock will race. JUnit Jupiter keeps method-level parallelism off by default; if CI enables it, ensure mocks/fixtures/thread safety or isolate them.

### 21.5. Never call `block()` on an event loop

In reactive apps, calling `block()` on Reactor non-blocking threads throws errors or stalls the event loop. In plain test methods, `block()` occasionally reads a finite `Mono`, yet `StepVerifier` gives far better assertions for `onError`/`onComplete`/cancel/demand/time. Avoid building suites out of `block()` and `Thread.sleep` when proving Reactive Streams semantics.

## 22. Reasons virtual-time tests hang

**Case 1 — publisher created too early.** `Flux.interval` captured the real `Scheduler` before `withVirtualTime` activated. Fix: build the publisher inside the supplier.

**Case 2 — expecting `onNext` before advancing time.** The test puts `expectNext` right after subscription before the interval elapses. Fix: call `thenAwait` or explicit `clock.advanceTimeBy`.

**Case 3 — expecting completion on an infinite stream.** `Flux.interval` never completes. Fix: add `take(n)` if finite by contract, or use `thenCancel`.

**Case 4 — `expectNoEvent` before `expectSubscription`.** Subscription counts as an event in `StepVerifier`. Fix: `expectSubscription().expectNoEvent(...)`.

**Case 5 — non-Reactor time source involved.** `Thread.sleep`, external Redis TTLs, or custom Java executors ignore virtual time. Fix: inject proper time abstractions or test real delays with bounded timeouts.

**Case 6 — custom `Scheduler` captured before setup.** A Spring singleton service already captured a real scheduler before `withVirtualTime`. Fix: inject `VirtualTimeScheduler` into the service test, or instantiate the service after setup.

**Case 7 — too many immediate synchronous events.** Infinite recursion or zero-interval scheduling hogs the thread. Fix: avoid zero-delay unbounded loops; use `take` and bounded demand.

**Case 8 — verifier lacks a real-time timeout.** When a publisher fails to emit, the suite hangs forever. Fix: use `verify(Duration)` and CI timeouts, without treating timeouts as a substitute for valid expectations.

**Case 9 — advancing the wrong `VirtualTimeScheduler` instance.** Code creates two `VirtualTimeScheduler` instances; operators use A while the test advances B. Fix: pass the **exact same instance** with clear ownership.

**Case 10 — concurrent tests collide.** One test swaps the global `Schedulers` factory while another runs real Reactor timers. Fix: serialize global-virtual-factory tests or inject per-test schedulers.

## 23. Reasons `WebTestClient` SSE tests fail

| Symptom | Possible cause | Fix |
| --- | --- | --- |
| 404 before reading stream | Wrong `@RequestMapping`/path | Check route mapping |
| 406 Not Acceptable | Incompatible `Accept`/media type | Send `TEXT_EVENT_STREAM` |
| 415 Unsupported Media Type | Wrong request `Content-Type` | Align `consumes`/codecs |
| 500 at context startup | Missing service mock in slice | Add `@MockBean` of right type |
| SSE body fails DTO decode | Codec/Jackson type mismatch | Check DTO/serializer/`returnResult` |
| Test hangs waiting for completion | Stream never completes | Use `thenCancel`, never `expectBodyList` |
| Flux events arrive slowly | Scheduler/network/CI load | Separate service vTime tests, shorten real test intervals |
| Slice passes, live HTTP fails | Netty/server/config/proxy differences | Check `RANDOM_PORT`/response headers |
| 200 yet stream breaks mid-way | HTTP headers already committed | Check `onError` and protocol framing |
| Client cancels yet server doesn't clean up | Async propagation | Assert `doFinally`/metrics eventually |
| `StepVerifier.withVirtualTime` hangs HTTP | Does not control full live server clock | Use `StepVerifier.create(responseBody)` |
| App boots MVC instead of WebFlux | Both web starters present, wrong app type | Confirm reactive stack |
| Response buffering holds events | Codec/flush/proxy buffering | Check streaming media type |
| Mock service returns null | Unstubbed Mockito `Mono`/`Flux` | Return valid `Mono`/`Flux` |
| Stream keeps running after test | Subscription never canceled/disposed | Call `thenCancel`, clean up lifecycle |
| Tests fail only under parallel suite | Shared mocks/global scheduler/ports | Isolate, serialize, or refactor |

## 24. `TestScheduler` vs `VirtualTimeScheduler` vs `Clock`

`VirtualTimeScheduler` is `reactor-test`'s scheduler implementation for controlling timed Reactor operators. It is not equivalent to `java.time.Clock.fixed`:

- `Clock.fixed(Instant, ZoneId)` tests *business timestamps*.
- `VirtualTimeScheduler` controls *when reactive timers/operators fire*.
- `TestPublisher` controls *upstream signal sequences*.
- `WebTestClient` tests *HTTP wire/codec behavior*.

An application using both timestamps and intervals can inject both `Clock` and `Scheduler`. Tests can advance the scheduler while `Instant.now()` still reflects real wall time if code bypasses the injected `Clock`; that is not a Reactor bug.

## 25. Retries, timeouts, and cancellation by scope

A retry policy can be modeled as:

~~~text
Attempt 1 -> onError(transient) -> wait 1s
Attempt 2 -> onError(transient) -> wait 2s
Attempt 3 -> onNext(success) -> onComplete
~~~

With virtual time, assertions check total attempt counts, next-attempt timing, and terminal success/error. Still, remote HTTP/DB calls require mocks/fakes or local test servers; testing the `Scheduler` alone does not replace network testing.

When a client cancels a request:

~~~text
Client WebTestClient.cancel()
           |
           v
HTTP connection/response subscriber canceled
           |
           v
Server Flux subscription cancellation propagated
           |
           v
doFinally(CANCEL) / resource cleanup
~~~

Propagation can be asynchronous. Never rely on fixed sleeps or unsynchronized synchronous assertions on server-side counters. In service-layer tests you can attach `doFinally(signalType -> ...)` and assert via `StepVerifier`; in end-to-end HTTP tests use bounded waits/metrics when cleanup is required.

## 26. CI: keeping tests fast and trustworthy

Split into three groups:

1. **Pure reactive unit:** `FeedVirtualTimeTest`, `FeedServiceContractTest`, zero Spring context; fast and deterministic.
2. **WebFlux slice:** `FeedWebSliceTest`, `WebTestClient` mock server + mocked service; fast HTTP contract checks without TCP.
3. **Full-context HTTP:** `FeedLiveHttpTest`, Netty on random port; uses wall-clock/IO so keep to critical scenarios.

Gradle uses `useJUnitPlatform()`. When splitting PR vs integration jobs, use JUnit tags or an `integrationTest` task, **never running the same tests twice while double-counting reports**. CI release gates must confirm JUnit XML reports all 17 tests rather than treating `UP-TO-DATE` as a fresh test run.

### GitHub Actions snippet

~~~yaml
name: reactive-tests

on:
  pull_request:
  workflow_dispatch:

permissions:
  contents: read

jobs:
  test:
    runs-on: ubuntu-24.04
    timeout-minutes: 20
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'
      - uses: gradle/actions/setup-gradle@v4
      - name: Run all reactive tests
        run: ./gradlew test --rerun-tasks
      - name: Save JUnit reports
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: reactive-test-results
          path: |
            build/reports/tests/test/
            build/test-results/test/
          if-no-files-found: ignore
~~~

This is an example workflow; in production pin action commits per supply-chain policy and track supported action versions. If random-port tests fail only on shared CI runners, collect logs, JUnit XML, test durations, and Netty bind exceptions before blindly raising timeouts.

## 27. Extension exercises

**A.** Change the virtual-time interval from 2 hours to 7 days; verify results return without waiting seven wall-clock days.

**B.** Construct `Flux.interval` outside the `withVirtualTime` supplier; explain why the test keeps the real scheduler and fix it.

**C.** Remove `expectSubscription` before `expectNoEvent` and observe which signal the verifier catches.

**D.** Replace `thenAwait` with `expectNoEvent` during silent periods and test the boundary.

**E.** Remove `take(count)` while keeping `verifyComplete`; explain why the test fails legitimately and switch to cancellation.

**F.** Use an explicit `VirtualTimeScheduler.create` passing the same instance to service and test, disposing it afterward.

**G.** Change the service interval to zero/negative and verify `Flux.error` with `StepVerifier`.

**H.** Replace the `Flux.just` mock service with `Flux.never` in the WebFlux slice; cancel cleanly with `thenCancel`.

**I.** Add an `application/x-ndjson` endpoint returning a finite `Flux`; write a `WebTestClient.returnResult` test checking frame decoding.

**J.** Write a `@WebFluxTest` with a `@MockBean` service returning HTTP 404 and assert `ResponseStatusException` mapping.

**K.** Write a full `RANDOM_PORT` SSE test and contrast it with the mocked WebFlux slice.

**L.** Compare startup times of slice vs full-context tests, avoiding conclusions from a single sample on a shared CI host.

**M.** Add a `TestPublisher` pushing events into the service; assert output sequence, errors, and cancellation.

**N.** Implement a retry policy with a 1-virtual-day `fixedDelay` and assert attempt counts and elapsed virtual time.

**O.** Simulate timeout fallback via `Mono.never().timeout(Duration, fallback)` and assert the fallback value.

**P.** Use `StepVerifier.create(Flux.range(1, 5), 0)` to test `request(2)`, `request(3)`, and completion.

**Q.** Instrument a producer with `doOnCancel`/`doFinally` and verify subscriber cancellation in a service unit test.

**R.** Add a `@RestControllerAdvice` mapping validation errors and `ResponseStatusException` into an explicit JSON contract.

**S.** Run JUnit methods in parallel in a sandbox branch; observe the hazard when two tests swap the global virtual scheduler factory, then switch to explicit scheduler injection.

**T.** Add `Clock.fixed` for timestamps and `VirtualTimeScheduler` for intervals, proving the two clocks are independent dependencies.

**U.** Switch the SSE media type to `application/json` and compare JSON array serialization vs streaming semantics.

**V.** Put a real proxy/test gateway in front of the client if production uses SSE, testing buffering and disconnect propagation.

**W.** Write an integration test with Testcontainers Kafka/Redis, separating virtual retry timing from broker/wall-clock time.

**X.** Check logs for `onErrorDropped` or post-cancel network disconnect errors; never ignore dropped errors.

## 28. Pre-merge checklist for reactive tests

- [ ] Do tests verify assembly, subscription, `onNext`, terminal signals, and cancellation?
- [ ] Do `Mono`/`Flux` terminal behaviors match the assertions?
- [ ] With virtual time, is the publisher created lazily inside the supplier?
- [ ] When injecting a scheduler, does the test advance the exact same instance?
- [ ] Is `expectSubscription` placed before `expectNoEvent`?
- [ ] Are `thenAwait` and `expectNoEvent` used accurately?
- [ ] Are `Thread.sleep` calls avoided for simulating reactive time?
- [ ] Are `Clock.fixed` and `VirtualTimeScheduler` kept distinct?
- [ ] Do tests avoid assuming a virtual scheduler controls Netty or external HTTP servers?
- [ ] Is `verifyComplete` avoided on infinite SSE streams?
- [ ] Is `thenCancel` used when the client stops a stream early?
- [ ] Are verification timeouts set to prevent test hangs?
- [ ] Are tests independent of global `Scheduler` state across methods?
- [ ] Are test-created schedulers cleaned up/disposed?
- [ ] Is `Schedulers.immediate` avoided on positive timed tests?
- [ ] Is backpressure demand tested when part of the contract?
- [ ] Does `@WebFluxTest` provide mocks for ordinary services?
- [ ] Does `WebTestClient` check route, status, media type, and response body?
- [ ] Does SSE use `returnResult().getResponseBody()` instead of unbounded `expectBodyList`?
- [ ] Are both finite streams and long-lived cancellation cases covered?
- [ ] Are error-before-headers and error-after-commit strategies clear?
- [ ] Do live-server HTTP tests use `RANDOM_PORT` rather than hardcoded ports?
- [ ] Is the Spring WebFlux stack used properly without mixing in MVC?
- [ ] Is media-type content negotiation verified?
- [ ] Do JSON codecs/serializers match the DTOs?
- [ ] Are stream test payloads free of secrets and PII?
- [ ] Do tests avoid calling `block()` on Reactor event loops?
- [ ] Are retry/backoff/timeout policy tests decoupled from external networks?
- [ ] Were JUnit test counts and outcomes verified after an actual run?
- [ ] Does CI avoid masking failed tests via `UP-TO-DATE`/cached outputs?
- [ ] Are JUnit reports saved on failure alongside bounded CI job timeouts?
- [ ] Do you avoid raising timeouts indefinitely to mask races or wrong schedulers?

## 29. Official references

- [Project Reactor — Testing Reactor Core](https://projectreactor.io/docs/core/release/reference/testing.html): `StepVerifier`, virtual time, `TestPublisher`, post-execution assertions.
- [Project Reactor — Reactor 3 Reference Guide](https://docs.spring.io/projectreactor/reactor-core/docs/current/reference/html/): lazy suppliers, `expectNoEvent`/`thenAwait`, and virtual time limits.
- [Reactor Test — StepVerifier API](https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifier.html): initial request, `withVirtualTime`, `verify`/timeouts.
- [Reactor Test — VirtualTimeScheduler API](https://projectreactor.io/docs/test/release/api/reactor/test/scheduler/VirtualTimeScheduler.html): `advanceTimeBy` and `dispose`.
- [Spring Framework — WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html): `bindToController`, `bindToServer`, streaming `FluxExchangeResult`.
- [Spring Framework — WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux.html): Reactive HTTP dispatch and streaming.
- [Spring Boot 3.3 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html): `@WebFluxTest`, `@MockBean`, `WebTestClient`, and random-port tests.
- [Reactive Streams specification](https://www.reactive-streams.org/): `Subscription`, `request(n)`, `cancel`, terminal signals.
- [JUnit Jupiter User Guide](https://docs.junit.org/5.10.2/user-guide/): lifecycle, test isolation, and parallel execution.
- [Gradle Java Testing](https://docs.gradle.org/current/userguide/java_testing.html): JUnit Platform, filtering, and test reports.

**Summary:** Use `StepVerifier.withVirtualTime` or an explicit `VirtualTimeScheduler` to test delay/interval/timeout logic **without wall-clock waits**, and use `WebTestClient` to test real WebFlux JSON/SSE HTTP behavior at the right boundary. For finite `Flux`, verify completion; for long-lived SSE, assert a few events then cancel. Never try to drive external servers with a virtual clock, never assemble publishers prematurely, never let concurrent tests mutate global `Scheduler` state, and always distinguish designed JUnit tests from actually executed test results.
