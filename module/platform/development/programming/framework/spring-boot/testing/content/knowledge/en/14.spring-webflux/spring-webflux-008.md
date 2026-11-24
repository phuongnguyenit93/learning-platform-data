# Spring WebFlux: Testing Streaming, SSE, and Timeouts

## 1. Goal and Scope

A Spring WebFlux application can return data **incrementally over time** instead of a single complete JSON response. Examples include live trading prices, processing progress, real-time notifications, or long-running computation results. Testing such a stream requires observing **Reactive Streams signals**, partial payloads, emission timing, and how the stream closes — not just checking HTTP 200.

This lesson focuses on:

- `Flux<T>`, `Mono<T>`, and the `onNext`, `onComplete`, `onError`, and `cancel` signals.
- `text/event-stream` / **Server-Sent Events (SSE)**, the `id`, `event`, `data`, and `retry` fields, and long-lived connection semantics.
- Streaming JSON via `application/x-ndjson` (one JSON object per line).
- `WebTestClient` to assert status, `Content-Type`, stream bodies, and received items.
- `StepVerifier` to verify event ordering, completion, errors, cancellation, real time, and **virtual time**.
- Reactor's `timeout(Duration)` (inter-signal timeout), fallbacks, HTTP 504, client-side response timeouts, and infrastructure deadlines.
- Backpressure, subscription cancellation, cleanup, and error handling **after HTTP headers have already been sent**.
- CI test stability: not draining infinite streams, avoiding long `Thread.sleep` calls, and never letting `verify()` wait unboundedly.

The complete examples use **Java 17, Spring Boot 3.5.0, Spring Framework 6.2, Reactor 3.7**, Maven, JUnit Jupiter, and `reactor-test`. Spring Boot 4 introduces focused test starters and different test annotation packages; see the compatibility note at the end.

### Outcomes to Prove

| What We Want to Know | Appropriate Check | Evidence |
| --- | --- | --- |
| Publisher produces right items | Pure Reactor + `StepVerifier` | `onNext` values and ordering |
| Event arrives after specified delay | `StepVerifier` virtual time | No early signal; signal arrives after advancing clock |
| Client can stop an infinite stream | `StepVerifier` `thenCancel()` | No hang; upstream receives cancellation in Reactor test |
| Endpoint returns proper SSE | `WebTestClient` | HTTP 200, `text/event-stream`, `data/id/event` |
| NDJSON is separate objects | `WebTestClient` streaming body | Decodes 3 objects; stream completes |
| Upstream too slow | Reactor timeout/fallback test | `TimeoutException` or fallback/504 per contract |
| Real server flushes data | `@SpringBootTest(RANDOM_PORT)` + `WebTestClient` | Client receives items over a real socket |
| Backpressure not misunderstood | `StepVerifier` small initial demand | Proves emission obeys demand on eligible publishers |

**Principle:** a stream may never emit `onComplete`. Tests must have their own **termination condition** using `take(n)` for eligible publishers or `thenCancel()` when reading an HTTP stream. Never use `collectList()` or `blockLast()` unconditionally on an infinite source.

## 2. Reactive Streams Mechanics in WebFlux

A Reactive Streams `Publisher` emits these signals:

```text
subscribe
   |
   v
onSubscribe(Subscription)
   |
request(n)  ---> onNext(item1), onNext(item2), ...
   |
   +----> onComplete()           [normal termination]
   |
   +----> onError(Throwable)     [error termination]
   |
   +----> cancel()               [subscriber cancels, does not wait for terminal]
```

A stream has **at most one terminal signal**: `onComplete` or `onError`. `cancel()` is a downstream action to stop receiving further data, **not** a normal terminal signal emitted to the subscriber. After cancellation, spec-compliant sources should stop sending further items to that subscriber.

A few easily confused points:

1. `Flux.just(1,2,3)` is **finite** and completes; `Flux.interval(Duration)` can be **infinite** without `take` or a stop condition.
2. `Flux.interval` emits on a scheduler; in virtual-time tests you must **construct the publisher after the virtual scheduler is active**.
3. `Flux.never()` emits nothing, never completes, and never errors. Great for testing timeouts; using it with `expectComplete()` without a verifier timeout will hang the test.
4. `Flux.empty()` completes immediately without emitting data. Completely different from `Flux.never()`.
5. `Flux.error(ex)` errors immediately. You can assert the exception type and timing.
6. `Flux.take(n)` takes `n` items, cancels upstream when needed, and emits completion downstream; that is not equivalent to upstream terminating naturally.
7. `doFinally(SignalType.CANCEL)` is suited for checking cancellation cleanup at the **Reactor level**; do not assume HTTP client cancellation synchronously triggers server cleanup callbacks before a test asserts.

## 3. How Does SSE Differ from Regular JSON Responses and NDJSON?

SSE is a **unidirectional HTTP** server-push mechanism. The client sends a GET, and the server keeps the response open while emitting text records in `text/event-stream` format. Example wire format (illustrative only; newline sequences are significant):

```text
id: 1
event: tick
retry: 2000
data: {"number":1,"text":"tick-1"}

id: 2
event: tick
retry: 2000
data: {"number":2,"text":"tick-2"}

```

A blank line terminates each SSE event. Spring may append a charset, and JSON encoders may choose different spacing/escaping. **Do not test raw bytes with full-string equality when what you need to verify is typed data**. Use a decoder to read `ServerSentEvent<T>` or payload type `T`; only test raw formatting when the contract requires wire-level compatibility.

Fields:

| SSE Field | Role | What to Test |
| --- | --- | --- |
| `data` | Payload; may be a JSON object | Schema, field values, order if meaningful |
| `id` | Event identifier; browsers track as last event ID | Consistency/uniqueness, especially on reconnect |
| `event` | Event name (e.g., `tick`, `progress`) | Exact name frontend subscribes to |
| `retry` | Suggested browser `EventSource` reconnect delay (milliseconds on wire) | Matches policy if API publishes one |
| Comment `: ...` | Can serve as heartbeat/keep-alive, not a business event | Connection survives idle proxy without incrementing business event count |
| `Last-Event-ID` | Header sent by client on reconnect | Resume/replay **only works if the server explicitly implements it** |

**Never assume replay exists by default.** A server emitting `id` does not guarantee the endpoint accepts `Last-Event-ID`, retrieves past events, deduplicates, or provides exactly-once delivery. If reconnect is required, add dedicated tests for lost events, duplicates, cursor/offset handling, and history retention policy.

### Comparing Three Response Styles

| Style | Media Type | Method/Controller | Characteristics |
| --- | --- | --- | --- |
| Full JSON result | `application/json` | `Mono<List<T>>` or `Flux<T>` serialized as an array | Client typically waits for the complete body |
| SSE | `text/event-stream` | `Flux<ServerSentEvent<T>>` or `Flux<T>` producing SSE | Each event emitted/flushed incrementally; includes SSE metadata |
| NDJSON | `application/x-ndjson` | `Flux<T>` | Each item becomes a JSON object on one line; no SSE `id/event/retry` |

A `Flux<T>` with `produces = application/json` does not automatically mean the client observes each item as soon as it is produced; codec/flushing strategies vary by content type. When explicit streaming is desired, choose `text/event-stream` or `application/x-ndjson` and verify behavior through a client.

## 4. WebTestClient: Reading a Stream Without Waiting for Completion

Per official Spring Framework documentation, the typical streaming test sequence is:

```java
FluxExchangeResult<MyEvent> response = client.get()
        .uri("/events")
        .accept(MediaType.TEXT_EVENT_STREAM)
        .exchange()
        .expectStatus().isOk()
        .expectHeader()
            .contentTypeCompatibleWith(MediaType.TEXT_EVENT_STREAM)
        .returnResult(MyEvent.class);

StepVerifier.create(response.getResponseBody())
        .expectNext(expectedFirst)
        .expectNext(expectedSecond)
        .thenCancel()
        .verify(Duration.ofSeconds(5));
```

This is an **excerpt**: `MyEvent`, `client`, and expected objects must be defined beforehand. The complete runnable project code is in Sections 8–10.

Key points:

- `exchange()` sends the request/receives the response; `expectStatus` and `expectHeader` verify the protocol.
- `returnResult(MyEvent.class)` returns `FluxExchangeResult<MyEvent>` so the test can **subscribe/consume** events as they arrive.
- `getResponseBody()` is `Flux<MyEvent>`; `StepVerifier` verifies `onNext` signals.
- `thenCancel()` closes the subscription after the desired number of events; ideal for **infinite streams**.
- `verify(Duration.ofSeconds(5))` places a real-time bound on the entire scenario. Never rely on unbounded `verify()`.
- For generic SSE including metadata, use `returnResult(new ParameterizedTypeReference<ServerSentEvent<MyEvent>>() {})` when decoders/codecs are configured accordingly.
- For **finite** NDJSON, you can finish with `expectComplete().verify(Duration)`.

### Do Not Use expectBodyList for an Infinite Stream

```java
// Avoid on infinite endpoints: may wait forever for completion.
client.get().uri("/events").exchange()
    .expectBodyList(MyEvent.class);

// Right approach: take a few events, then cancel.
FluxExchangeResult<MyEvent> response = client.get()
    .uri("/events")
    .exchange()
    .returnResult(MyEvent.class);
StepVerifier.create(response.getResponseBody())
    .expectNextCount(3)
    .thenCancel()
    .verify(Duration.ofSeconds(5));
```

Both snippets are illustrative only. With a stream capped by `take(3)` on the server, `expectComplete` is reasonable, whereas on a server that never completes, tests can hang or run out of memory trying to collect the body.

### Controller-Bound Tests and Real Servers Are Not Equivalent

`WebTestClient` can:

- `bindToController(new Controller(...))`: test a WebFlux controller directly with mock exchanges, without a Spring Boot context.
- `bindToApplicationContext(context)`: test the WebFlux stack in a Spring test context, without opening a TCP server.
- `bindToRouterFunction(routes)`: test functional WebFlux endpoints.
- `bindToServer().baseUrl(...).build()`: send real HTTP to a running server.
- `@WebFluxTest`: Spring Boot slice creating a narrow WebFlux context and auto-configuring `WebTestClient`.
- `@SpringBootTest(webEnvironment=RANDOM_PORT)`: starts a real embedded server and can inject a client bound to the dynamic port.

Mock-bound tests verify routing, encoding, filters, and responses in a mock exchange; they **do not prove** socket behavior, reverse proxies, TCP disconnects, or buffering on production infrastructure. To verify real streaming flushes and HTTP connection termination, include at least one integration test against a real server.

## 5. StepVerifier: Signals, Timing, and Cancellation

`reactor-test` provides `StepVerifier` to express expectations on a `Publisher`.

### Values and Completion

```java
StepVerifier.create(Flux.just("A", "B", "C"))
        .expectNext("A", "B", "C")
        .expectComplete()
        .verify(Duration.ofSeconds(2));
```

Expects exactly three `onNext` signals followed by `onComplete`. If the `Flux` emits more items, errors, or fails to complete, the test FAILS.

### Error

```java
StepVerifier.create(
        Flux.concat(Flux.just("A"),
                    Flux.error(new IllegalStateException("stopped"))))
    .expectNext("A")
    .expectErrorMatches(ex -> ex instanceof IllegalStateException
            && "stopped".equals(ex.getMessage()))
    .verify(Duration.ofSeconds(2));
```

A stream can emit several items **and then error**; do not assume errors always occur before the first item. In HTTP streaming, an error occurring after response headers have committed can no longer change the status to 500/504; handling depends on the contract and client.

### Cancellation

```java
StepVerifier.create(Flux.interval(Duration.ofMillis(10)))
        .expectNext(0L, 1L)
        .thenCancel()
        .verify(Duration.ofSeconds(3));
```

In this example `Flux.interval` emits `0` first (after one interval) and `1` second. `thenCancel` does not wait for completion. **Reactive Streams-level** tests can use `doFinally` to assert upstream cleanup; real HTTP tests usually only prove the client stopped consuming, not immediately that every server resource was released.

### Verification Time Limits

Distinguish two types of "timeout":

- **Business timeout:** `Mono/Flux.timeout(Duration)`, causing the Publisher to emit `TimeoutException` if no subsequent signal arrives before the deadline.
- **Test harness timeout:** `StepVerifier.verify(Duration)`, causing the test to FAIL if expectations are not met within the real-time limit.

Specify both explicitly in time-sensitive tests. The harness timeout is typically **longer** than the business deadline to leave room for CI scheduling.

## 6. Virtual Time for Testing Timeouts Without Real Sleeping

Reactor lets `StepVerifier.withVirtualTime(() -> publisher)` replace the default scheduler with a virtual scheduler and drive time via `thenAwait`/`expectNoEvent`.

```java
StepVerifier.withVirtualTime(() ->
        Mono.delay(Duration.ofHours(1))
            .map(n -> "ready"))
    .expectSubscription()
    .expectNoEvent(Duration.ofMinutes(59))
    .thenAwait(Duration.ofMinutes(1))
    .expectNext("ready")
    .expectComplete()
    .verify(Duration.ofSeconds(2));
```

The test does not actually wait one hour. There are three rules:

1. **Create time-based publishers inside the `withVirtualTime` lambda**. If you create `Flux.interval` beforehand and the lambda merely returns the existing instance, the timer may already be bound to a real scheduler.
2. `expectNoEvent(Duration)` treats **subscription** as an event. Therefore write `expectSubscription()` before `expectNoEvent(...)`.
3. `thenAwait(Duration)` only advances the virtual clock; `expectNoEvent(Duration)` advances the clock **and** asserts no signals occurred during that span. Do not swap them if you need to prove "not emitted early".

Virtual time cannot replace network timeouts, blocking I/O, JDBC queries, or arbitrary custom schedulers. Tests using `Thread.sleep` or real HTTP clients **do not speed up** just by using virtual time. With multiple `publishOn`s, `flatMap`s, custom schedulers, insufficient demand, or infinite simultaneous emissions, poorly designed virtual-time tests can deadlock/starve.

### "No Signal Received Within 3 Seconds" Timeout

```java
StepVerifier.withVirtualTime(() ->
        Mono.<String>never().timeout(Duration.ofSeconds(3)))
    .expectSubscription()
    .expectNoEvent(Duration.ofSeconds(2))
    .thenAwait(Duration.ofSeconds(1))
    .expectError(TimeoutException.class)
    .verify(Duration.ofSeconds(2));
```

Here the timeout is a business error after **3 virtual seconds**. The `verify(2 seconds)` limit remains **real wall-clock time**, failing rather than hanging if the test is misdesigned. To compile the snippet, import `Mono`, `StepVerifier`, `Duration`, and `TimeoutException`.

## 7. Distinguishing Timeout Layers in a WebFlux Application

| Layer | Mechanism | Impact | How to Test |
| --- | --- | --- | --- |
| **Publisher first/next-signal timeout** | `Mono/Flux.timeout(Duration)` | No signal in time → `TimeoutException`, or fallback if supplied | Pure Reactor + virtual time |
| **Pre-commit response deadline** | Server maps `TimeoutException` → HTTP 504 | Client gets 504, if headers have not committed | `WebTestClient`/HTTP integration |
| **Stream idle timeout** | `Flux.timeout(Duration)` after each `onNext` | Too long a silence causes stream error; 200 may already be sent | `StepVerifier` for sequences with gaps |
| **Client response timeout** | `WebTestClient.Builder.responseTimeout(Duration)` | Bounds how long the test client waits for response operations | `WebTestClient`, separate limit |
| **Connection/TCP timeout** | Reactor Netty/`WebClient` options | Transport connect/read/write/idle behavior | Real-server/stub/proxy integration |
| **Infrastructure idle timeout** | Gateway/LB/reverse proxy/network | Closes SSE connection when no bytes flow | Staging/contract test through real infrastructure |
| **Test verifier timeout** | `verify(Duration)` | Protects CI from hanging if publisher never meets expectations | Every long-streaming test |

HTTP 504 is an **API contract choice** (Gateway Timeout). Spring Reactor `timeout` itself emits `TimeoutException`; if unhandled, the HTTP server may return 500 or close the connection depending on timing. To get 504, **explicitly map it** at the API layer while status can still be set.

### Flux Timeout Resets After Each Item

```java
Flux<String> source = Flux.concat(
        Flux.just("first"),
        Mono.delay(Duration.ofSeconds(10)).map(n -> "second"));

Flux<String> guarded = source.timeout(Duration.ofSeconds(3));
```

The source emits `first` immediately, then goes silent for 10 seconds. `timeout(3s)` emits `TimeoutException` roughly 3 seconds after `first`, **not** waiting 10 seconds for the whole stream. This is an **idle-gap timeout**, not "the entire request must finish within 3 seconds".

If business logic requires a fixed deadline for the **entire operation**, use a timer source or apply a separate overall time budget; do not assume `Flux.timeout(Duration)` expresses a request-wide deadline since the timer resets on every new item.

### Fallback and Exception Mapping

```java
Mono<String> fallback = upstream
        .timeout(Duration.ofMillis(100), Mono.just("cached"));

Mono<String> error = upstream
        .timeout(Duration.ofMillis(100))
        .onErrorMap(TimeoutException.class,
                ex -> new ResponseStatusException(
                        HttpStatus.GATEWAY_TIMEOUT,
                        "upstream deadline exceeded", ex));
```

These are excerpts where `upstream` is a `Mono<String>` passed from a service, requiring imports. Fallback returns 200 when the controller chooses `"cached"` as the response; critical APIs should mark stale data when required by the contract. `onErrorMap` translates the exception to HTTP 504 **if the response has not yet committed**.

### HTTP Status Cannot Be Changed After Streaming Data

Once the server has sent `200 OK` and some SSE events, an upstream error cannot "retract" HTTP 200 and turn it into 504. Handling must be specified clearly:

- Close the stream so the client reconnects; supply `id` and cursor/resume if needed.
- Emit an **error-type SSE event** (e.g., `event: error` with a safe payload) and complete; HTTP status remains the committed 200.
- Use heartbeats and server/client timeout policies for idle connections.
- For finite streams needing atomic response/error status, consider buffering the whole stream before writing, accepting memory/latency costs.

Do not test "HTTP 504 after the third event" once the response has committed, unless you are verifying a custom protocol embedding status inside payloads.

## 8. Runnable Java 17 Project: SSE, NDJSON, Deadline, and Fallback

The example below requires no DB, Docker, or external API. The design has three layers:

- `StreamService` generates `Tick`s and simulates slow work.
- `StreamController` defines streaming/timeout endpoints.
- Three test groups: **pure Reactor**, **`@WebFluxTest`**, and **`@SpringBootTest(RANDOM_PORT)`**.

### 8.1. Directory Tree

```text
webflux-stream-demo/
├── pom.xml
└── src/
    ├── main/java/example/sse/
    │   ├── SseApplication.java
    │   ├── Tick.java
    │   ├── StreamService.java
    │   └── StreamController.java
    └── test/java/example/sse/
        ├── StreamServiceTest.java
        ├── StreamControllerTest.java
        └── StreamHttpIntegrationTest.java
```

### 8.2. pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>webflux-stream-demo</artifactId>
    <version>1.0-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
```

`reactor-test` is declared explicitly so `StepVerifier` tests do not depend on whether a specific test starter pulls it onto the classpath. The Spring Boot parent manages Reactor Test/JUnit versions, so do not declare separate versions. Use only `spring-boot-starter-webflux` for the demo's WebFlux server, avoiding pulling `spring-boot-starter-web` into the same app: if both Spring MVC and WebFlux are on the classpath, Spring Boot usually prefers MVC unless the application type is configured as reactive.

### 8.3. SseApplication.java

```java
package example.sse;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SseApplication {
    public static void main(String[] args) {
        SpringApplication.run(SseApplication.class, args);
    }
}
```

### 8.4. Tick.java

```java
package example.sse;

public record Tick(long number, String text) {
}
```

The record provides constructor, equality, and `number()`/`text()` accessors. Spring Boot 3.5's Jackson supports record serialization/deserialization. Tests can compare `new Tick(1, "tick-1")` with decoded objects without writing `equals` manually.

### 8.5. StreamService.java

```java
package example.sse;

import java.time.Duration;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Service
public class StreamService {
    public Flux<Tick> ticks(Duration period) {
        return Flux.interval(period)
                .map(n -> new Tick(n + 1, "tick-" + (n + 1)));
    }

    public Mono<String> delayed(Duration delay) {
        return Mono.delay(delay).map(n -> "ready");
    }
}
```

`Flux.interval(period)` emits `0` after one period, then `1`, `2`, ...; the service transforms the first one into `Tick(number=1, ...)`. The `ticks` stream is **infinite** unless cancelled or limited with `take`. `delayed` emits a `"ready"` string after a wait, useful for simulating slow upstreams without real network calls.

**Practical note:** `Flux.interval` relies on a scheduler and can error with overflow if downstream demand is insufficient. In production, hot sources, buffers/drop/latest/replay, rate limiting, and backpressure must be designed for the data characteristics. Do not treat this infinite tick generator as a guaranteed-delivery message broker.

### 8.6. StreamController.java

```java
package example.sse;

import java.time.Duration;
import java.util.concurrent.TimeoutException;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api")
public class StreamController {
    private final StreamService service;

    public StreamController(StreamService service) {
        this.service = service;
    }

    @GetMapping(
            path = "/sse",
            produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public Flux<ServerSentEvent<Tick>> sse() {
        return service.ticks(Duration.ofMillis(50))
                .map(tick -> ServerSentEvent.<Tick>builder(tick)
                        .id(Long.toString(tick.number()))
                        .event("tick")
                        .retry(Duration.ofSeconds(2))
                        .build());
    }

    @GetMapping(
            path = "/ndjson",
            produces = MediaType.APPLICATION_NDJSON_VALUE)
    public Flux<Tick> ndjson() {
        return service.ticks(Duration.ofMillis(20)).take(3);
    }

    // 250 ms upstream vs 50 ms deadline: times out before any body is written.
    @GetMapping(
            path = "/deadline",
            produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> deadline() {
        return service.delayed(Duration.ofMillis(250))
                .timeout(Duration.ofMillis(50))
                .onErrorMap(TimeoutException.class,
                        ex -> new ResponseStatusException(
                                HttpStatus.GATEWAY_TIMEOUT,
                                "upstream deadline exceeded", ex));
    }

    // Contract allows fallback instead of returning an error.
    @GetMapping(
            path = "/fallback",
            produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> fallback() {
        return service.delayed(Duration.ofMillis(250))
                .timeout(Duration.ofMillis(50),
                        Mono.just("fallback"));
    }
}
```

The four endpoints serve distinct goals:

| Endpoint | Behavior | Expected |
| --- | --- | --- |
| `GET /api/sse` | Infinite SSE, each event has data/id/event/retry | 200, `text/event-stream`, client receives 1/2/... and cancels |
| `GET /api/ndjson` | Three `Tick`s then complete | 200, `application/x-ndjson`, exact three objects |
| `GET /api/deadline` | Upstream needs 250 ms, deadline is 50 ms | 504 before sending body |
| `GET /api/fallback` | Same slow upstream, with fallback | 200, body `fallback` |

These short durations are for learning; real systems need timeout budgets grounded in service-level objectives, network hops, and real load. Do not copy 50/250 ms as production defaults without metrics.

## 9. Pure Reactor Tests: Virtual Time, Timeout, Subscription Cancellation

Create `src/test/java/example/sse/StreamServiceTest.java`:

```java
package example.sse;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.time.Duration;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.core.publisher.SignalType;
import reactor.test.StepVerifier;

class StreamServiceTest {
    private final StreamService service = new StreamService();

    @Test
    void ticksFollowVirtualTimeCadence() {
        StepVerifier.withVirtualTime(() ->
                service.ticks(Duration.ofSeconds(10)).take(3))
            .expectSubscription()
            .expectNoEvent(Duration.ofSeconds(9))
            .thenAwait(Duration.ofSeconds(1))
            .expectNext(new Tick(1, "tick-1"))
            .expectNoEvent(Duration.ofSeconds(9))
            .thenAwait(Duration.ofSeconds(1))
            .expectNext(new Tick(2, "tick-2"))
            .expectNoEvent(Duration.ofSeconds(9))
            .thenAwait(Duration.ofSeconds(1))
            .expectNext(new Tick(3, "tick-3"))
            .expectComplete()
            .verify(Duration.ofSeconds(2));
    }

    @Test
    void timeoutTriggersWhenThereIsNoSignal() {
        StepVerifier.withVirtualTime(() ->
                Mono.<String>never()
                    .timeout(Duration.ofSeconds(3)))
            .expectSubscription()
            .expectNoEvent(Duration.ofSeconds(2))
            .thenAwait(Duration.ofSeconds(1))
            .expectError(TimeoutException.class)
            .verify(Duration.ofSeconds(2));
    }

    @Test
    void slowWorkFallsBackAtVirtualDeadline() {
        StepVerifier.withVirtualTime(() ->
                service.delayed(Duration.ofSeconds(8))
                    .timeout(Duration.ofSeconds(3),
                            Mono.just("fallback")))
            .expectSubscription()
            .expectNoEvent(Duration.ofSeconds(2))
            .thenAwait(Duration.ofSeconds(1))
            .expectNext("fallback")
            .expectComplete()
            .verify(Duration.ofSeconds(2));
    }

    @Test
    void fastWorkCompletesBeforeDeadline() {
        StepVerifier.withVirtualTime(() ->
                service.delayed(Duration.ofSeconds(3))
                    .timeout(Duration.ofSeconds(5)))
            .expectSubscription()
            .expectNoEvent(Duration.ofSeconds(2))
            .thenAwait(Duration.ofSeconds(1))
            .expectNext("ready")
            .expectComplete()
            .verify(Duration.ofSeconds(2));
    }

    @Test
    void cancellingStreamTriggersUpstreamCleanup() {
        AtomicReference<SignalType> termination =
                new AtomicReference<>();

        StepVerifier.withVirtualTime(() ->
                service.ticks(Duration.ofSeconds(2))
                    .doFinally(termination::set))
            .expectSubscription()
            .thenAwait(Duration.ofSeconds(2))
            .expectNext(new Tick(1, "tick-1"))
            .thenCancel()
            .verify(Duration.ofSeconds(2));

        assertEquals(SignalType.CANCEL, termination.get());
    }

    @Test
    void timeoutMeasuresGapBetweenEmissions() {
        StepVerifier.withVirtualTime(() ->
                Flux.concat(
                        Flux.just("first"),
                        Mono.delay(Duration.ofSeconds(10))
                            .map(n -> "second"))
                    .timeout(Duration.ofSeconds(3)))
            .expectSubscription()
            .expectNext("first")
            .expectNoEvent(Duration.ofSeconds(2))
            .thenAwait(Duration.ofSeconds(1))
            .expectError(TimeoutException.class)
            .verify(Duration.ofSeconds(2));
    }
}
```

**There are 6 test methods.** No Spring annotations: `new StreamService()` runs pure Reactor. All time checks advance using the virtual clock; tests use `verify(Duration)` so they never wait forever if an expected signal fails to arrive.

### Explanation of Each Case

- `ticksFollowVirtualTimeCadence`: `Tick`s arrive at 10/20/30 virtual seconds, with none before each threshold. `take(3)` completes downstream and cancels upstream.
- `timeoutTriggersWhenThereIsNoSignal`: `Mono.never()` emits nothing; 3 virtual seconds elapse and `timeout` emits `TimeoutException`.
- `slowWorkFallsBackAtVirtualDeadline`: source would emit `ready` at 8 seconds, yet fallback triggers at 3 seconds.
- `fastWorkCompletesBeforeDeadline`: source emits at 3 seconds, deadline is 5; stream returns `ready` and completes.
- `cancellingStreamTriggersUpstreamCleanup`: `doFinally` observes `CANCEL` in the publisher-level test; do not infer that network server callbacks run instantaneously when a client disconnects.
- `timeoutMeasuresGapBetweenEmissions`: receiving `first` can still trigger a timeout if the silent gap between items exceeds 3 seconds.

### Failure Clues When Using Virtual Time

If a test stalls at `expectNext` without `thenAwait`, the virtual timer may not have been advanced. If the publisher was constructed outside the lambda, the virtual scheduler may not control its timer. If `expectNoEvent` is placed right at the start without `expectSubscription`, it can FAIL because subscription counts as a signal. For real blocking sources, do not use virtual time assuming I/O is accelerated.

## 10. @WebFluxTest: Verifying SSE Metadata, NDJSON, and Timeouts at the HTTP Layer

Create `src/test/java/example/sse/StreamControllerTest.java`:

```java
package example.sse;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import java.time.Duration;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.WebFluxTest;
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.reactive.server.FluxExchangeResult;
import org.springframework.test.web.reactive.server.WebTestClient;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

@WebFluxTest(StreamController.class)
class StreamControllerTest {
    @Autowired
    WebTestClient client;

    @MockitoBean
    StreamService service;

    @Test
    void sseContainsIdNameAndTypedPayload() {
        when(service.ticks(any(Duration.class))).thenReturn(
                Flux.just(
                        new Tick(1, "tick-1"),
                        new Tick(2, "tick-2"))
                    .concatWith(Flux.never()));

        FluxExchangeResult<ServerSentEvent<Tick>> result =
                client.get().uri("/api/sse")
                    .accept(MediaType.TEXT_EVENT_STREAM)
                    .exchange()
                    .expectStatus().isOk()
                    .expectHeader().contentTypeCompatibleWith(
                            MediaType.TEXT_EVENT_STREAM)
                    .returnResult(
                            new ParameterizedTypeReference<
                                    ServerSentEvent<Tick>>() {});

        StepVerifier.create(result.getResponseBody())
                .assertNext(event -> {
                    assertEquals("1", event.id());
                    assertEquals("tick", event.event());
                    assertEquals(new Tick(1, "tick-1"),
                            event.data());
                })
                .assertNext(event -> {
                    assertEquals("2", event.id());
                    assertEquals("tick", event.event());
                    assertEquals(new Tick(2, "tick-2"),
                            event.data());
                })
                .thenCancel()
                .verify(Duration.ofSeconds(5));

        verify(service).ticks(any(Duration.class));
    }

    @Test
    void ndjsonHasThreeObjectsAndCompletes() {
        when(service.ticks(any(Duration.class))).thenReturn(
                Flux.just(
                        new Tick(1, "tick-1"),
                        new Tick(2, "tick-2"),
                        new Tick(3, "tick-3")));

        FluxExchangeResult<Tick> result =
                client.get().uri("/api/ndjson")
                    .accept(MediaType.APPLICATION_NDJSON)
                    .exchange()
                    .expectStatus().isOk()
                    .expectHeader().contentTypeCompatibleWith(
                            MediaType.APPLICATION_NDJSON)
                    .returnResult(Tick.class);

        StepVerifier.create(result.getResponseBody())
                .expectNext(
                        new Tick(1, "tick-1"),
                        new Tick(2, "tick-2"),
                        new Tick(3, "tick-3"))
                .expectComplete()
                .verify(Duration.ofSeconds(5));
    }

    @Test
    void deadlineMapsSlowUpstreamToHttp504() {
        when(service.delayed(any(Duration.class)))
                .thenReturn(Mono.never());

        client.get().uri("/api/deadline")
                .exchange()
                .expectStatus().isEqualTo(504);
    }

    @Test
    void fallbackReturns200AndExplicitValue() {
        when(service.delayed(any(Duration.class)))
                .thenReturn(Mono.never());

        client.get().uri("/api/fallback")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("fallback");
    }

    @Test
    void fastUpstreamDoesNotUseFallback() {
        when(service.delayed(any(Duration.class)))
                .thenReturn(Mono.just("ready"));

        client.get().uri("/api/fallback")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("ready");
    }
}
```

**There are 5 test methods.** `@WebFluxTest(StreamController.class)` loads only the WebFlux test slice; `StreamService` is mocked via `@MockitoBean`, so the test verifies controller mapping, content types, SSE serialization/decoding, and timeout mapping **without waiting on real service intervals**.

### Why Test SSE with a Generic Type?

`ServerSentEvent<Tick>` lets you assert `id`/`event` metadata along with the typed payload. `ParameterizedTypeReference` retains the generic `Tick` type when `WebTestClient` decodes SSE. If a test only needs payloads, you can use `returnResult(Tick.class)` and assert each item; however, when ensuring the frontend can subscribe by event name or use `Last-Event-ID`, verify metadata as well.

`Flux.just(...).concatWith(Flux.never())` emits two business events and keeps the connection open; `thenCancel()` terminates cleanly. Returning just `Flux.just(...)` would let the stream complete on its own and fail to test "client cancels an open SSE stream".

### Do Not Confuse the 504 Test with a Client Timeout

In `deadlineMapsSlowUpstreamToHttp504`, the mock service returns `Mono.never()` and the controller applies **Reactor `timeout(50ms)`**, then maps `TimeoutException` to `ResponseStatusException(504)`. That is an application deadline, **not** `WebTestClient` timing out on its own. If the client timed out first, the test would throw a client exception instead of observing a valid HTTP 504 status.

## 11. HTTP Integration: Verifying Real Streams from Reactor Netty

Create `src/test/java/example/sse/StreamHttpIntegrationTest.java`:

```java
package example.sse;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.time.Duration;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.FluxExchangeResult;
import org.springframework.test.web.reactive.server.WebTestClient;
import reactor.test.StepVerifier;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class StreamHttpIntegrationTest {
    @LocalServerPort
    int port;

    private WebTestClient liveClient() {
        return WebTestClient.bindToServer()
                .baseUrl("http://127.0.0.1:" + port)
                .responseTimeout(Duration.ofSeconds(5))
                .build();
    }

    @Test
    void liveSseDeliversTwoEventsAndCanBeCancelled() {
        FluxExchangeResult<Tick> result = liveClient()
                .get().uri("/api/sse")
                .accept(MediaType.TEXT_EVENT_STREAM)
                .exchange()
                .expectStatus().isOk()
                .expectHeader().contentTypeCompatibleWith(
                        MediaType.TEXT_EVENT_STREAM)
                .returnResult(Tick.class);

        StepVerifier.create(result.getResponseBody())
                .expectNext(new Tick(1, "tick-1"))
                .expectNext(new Tick(2, "tick-2"))
                .thenCancel()
                .verify(Duration.ofSeconds(5));
    }

    @Test
    void liveNdjsonDeliversThreeAndCompletes() {
        FluxExchangeResult<Tick> result = liveClient()
                .get().uri("/api/ndjson")
                .accept(MediaType.APPLICATION_NDJSON)
                .exchange()
                .expectStatus().isOk()
                .returnResult(Tick.class);

        StepVerifier.create(result.getResponseBody())
                .expectNext(
                        new Tick(1, "tick-1"),
                        new Tick(2, "tick-2"),
                        new Tick(3, "tick-3"))
                .expectComplete()
                .verify(Duration.ofSeconds(5));
    }

    @Test
    void liveDeadlineReturnsHttp504() {
        liveClient().get().uri("/api/deadline")
                .exchange()
                .expectStatus().isEqualTo(504);
    }
}
```

**There are 3 test methods.** `@SpringBootTest(RANDOM_PORT)` starts a real embedded server (Reactor Netty when only the WebFlux starter is present); `@LocalServerPort` receives the OS-assigned port. `WebTestClient.bindToServer()` sends real HTTP over loopback.

Evidence from the test:

1. SSE is flushed incrementally so the client receives at least two events even though the stream never completes.
2. The client can cancel after two events instead of waiting on an infinite connection.
3. NDJSON streams three objects and terminates properly.
4. The deadline is reflected by the server as HTTP 504 before committing a success body.

**Limitation:** the test runs over loopback, not checking production proxies/CDNs/gateways or browser `EventSource`. It also does not prove that HTTP client cancellation released every server resource at the exact instant before the test finished. That requires observing server resource lifecycle via metrics/logging/dedicated integration tests.

### What Role Do the 5-Second Limits Play?

`responseTimeout(5s)` protects the client against a server that fails to return response headers in time. `StepVerifier.verify(5s)` bounds how long the test observes/consumes the body after receiving the response. They **do not replace** the controller's `timeout(50ms)`, which is the business rule. Having both safety limits prevents tests from hanging on stream bugs.

Do not assume `RANDOM_PORT` forces tests to be slow: the demo emits events every 50 ms with a 50 ms deadline; Spring context startup takes most of the time. Under heavy CI load, tune test harness limits from measurements rather than relaxing all business deadlines just to make tests pass.

## 12. Running Maven and Expectations

From the directory containing `pom.xml`, JDK 17+ and Maven able to download dependencies are required:

```bash
mvn test
```

Run each group separately:

```bash
mvn test -Dtest=StreamServiceTest
mvn test -Dtest=StreamControllerTest
mvn test -Dtest=StreamHttpIntegrationTest
```

`@Test` method counts in the sample project:

| Class | Tests | Scope |
| --- | --- | --- |
| `StreamServiceTest` | 6 | Publisher values, virtual intervals, timeout, fallback, cancellation, idle gap |
| `StreamControllerTest` | 5 | Mock-bound SSE metadata, NDJSON, HTTP 504, fallback/fast |
| `StreamHttpIntegrationTest` | 3 | Real HTTP SSE, NDJSON, deadline |
| **Total** | **14** | No DB/Docker |

Expected **14 PASS, 0 FAIL, 0 SKIPPED** in a compatible environment. This is the expected outcome of the example code; actually run it on a machine with dependencies to confirm. The source uses no `System.out.println`, so there is no fixed application stdout. Maven/JUnit logs vary; inspect `target/surefire-reports` and verify how many tests actually ran, not just `BUILD SUCCESS`.

With the code above, virtual-time Reactor tests advance tens of virtual seconds without sleeping real seconds. Real HTTP tests use short intervals and 5-second client limits. None wait for completion of the infinite `/api/sse` endpoint.

## 13. SSE Reconnect, Last-Event-ID, and Idempotency

Frontends using `EventSource` typically reconnect automatically after a dropped connection and may send `Last-Event-ID` to the server. However, WebFlux `ServerSentEvent.builder().id(...)` **only populates metadata**; the server must implement resume/history itself to replay missed data.

A replay-capable design might include:

- An event store recording business events with monotonically increasing sequences and a retention policy.
- Client sending `Last-Event-ID` (if available).
- Server verifying access permissions, resolving the cursor, replaying events after that ID, and switching seamlessly to the live feed.
- Duplicate/out-of-order handling where the event store and live stream overlap.
- Resume strategy when an ID is too old, past retention, or missing.

### Reconnect Test Matrix

| Scenario | Given | Then |
| --- | --- | --- |
| Initial connect | No `Last-Event-ID` | Receives current events / initial snapshot per contract |
| Disconnect after ID 10 | Client reconnects with `Last-Event-ID: 10` | If contract supports replay, receives from 11 (or specified snapshot state) |
| Non-existent ID | Malformed or expired ID | Explicit response/status/event policy, no crash |
| Duplicate replay | Backend replays an event | Client/idempotency logic does not double-process side effects |
| Unauthorized client | Subscribing to another tenant's stream | Returns 401/403 or closes connection per security policy |
| Proxy drops connection | Long idle period | Heartbeat or reconnect strategy verified |

**Never assume exactly-once delivery.** SSE runs over HTTP and reconnects can produce duplicate or missing spans without event persistence and replay. Delivery guarantees must be defined at the product level and cannot be inferred from the mere presence of an `id` field.

### Heartbeats Are Transport Signals, Not Business Events

Some systems send SSE comments like `: heartbeat` to keep connections alive through proxies with idle timeouts. `EventSource` clients normally do not dispatch comments to business event handlers. Raw wire/transport tests or metrics should confirm heartbeats fire on schedule; business event tests must not count a heartbeat as a `Tick`.

## 14. Backpressure, Buffering, and Slow Consumers

Reactive Streams has a **demand** mechanism: subscribers call `request(n)` to specify how many elements they want. With cooperative sources, this keeps producers from flooding slow consumers unboundedly.

A demand test example without HTTP:

```java
AtomicLong requested = new AtomicLong();

StepVerifier.create(
        Flux.range(1, 3).doOnRequest(requested::addAndGet),
        0)
    .expectSubscription()
    .thenRequest(1)
    .expectNext(1)
    .thenRequest(2)
    .expectNext(2, 3)
    .expectComplete()
    .verify(Duration.ofSeconds(2));

assertEquals(3L, requested.get());
```

This is an **excerpt** with imports `AtomicLong`, `Flux`, `StepVerifier`, and `assertEquals`. The `0` argument in `StepVerifier.create(publisher, 0)` starts with **zero demand**. The test then requests one item followed by two items; `doOnRequest` observes demand flowing upstream.

**Do not infer pipeline-wide backpressure from HTTP headers/status.** HTTP transport, Netty buffering, codecs, operators such as `publishOn`/`flatMap`, prefetching, and downstream demand can alter request/byte counts. An HTTP test consuming 2 events and cancelling does not guarantee upstream was only requested for exactly 2 items.

Time-based sources like `Flux.interval` can signal overflow if requested slower than their tick rate rather than buffering forever. In real systems:

- Choose bounded queues/buffers with an explicit overflow policy.
- `onBackpressureLatest` can drop intermediate states for progress dashboards, **unsuitable** for payment/critical events that must not be lost.
- `onBackpressureDrop` fits only droppable data and should record metrics for dropped events.
- For mandatory business events, use a durable broker/persistence or proper delivery/acknowledgment semantics.
- Avoid `collectList()`, unbounded `cache()`, or unbounded in-memory replay on multi-user feeds.
- Test disconnects to ensure subscriptions cancel and resources clean up, rather than leaking DB cursors/files/sockets after clients close.

## 15. Testing Mid-Stream Errors: Choosing the Right Expectations

For a stream:

```java
Flux<String> stream = Flux.concat(
        Flux.just("first", "second"),
        Flux.error(new IllegalStateException("backend failed")));

StepVerifier.create(stream)
        .expectNext("first", "second")
        .expectError(IllegalStateException.class)
        .verify(Duration.ofSeconds(2));
```

A Reactor test observes two items followed by the error. However, if a controller serializes this stream to SSE and the server already sent at least one event, the client may already have received HTTP 200. You cannot assert "the response status changes to 500" once headers are committed.

You can design an in-stream error event in SSE:

```java
Flux<ServerSentEvent<String>> sse = source
        .map(data -> ServerSentEvent.<String>builder(data)
                .event("data").build())
        .onErrorResume(ex -> Flux.just(
                ServerSentEvent.<String>builder("temporarily unavailable")
                        .event("error")
                        .build()));
```

This is an **excerpt** where `source` must be a `Flux<String>` with imports. After the failure, the server emits an event named `error` and completes with an **HTTP status that may still be 200**, since headers committed earlier. The API must specify the schema and security of error events; never leak stack traces or raw exceptions with sensitive data.

To get status 504 on timeout **before data flows**, use `Mono` timeout/mapError as in the sample project's `/api/deadline`. Never write a test expectation that is impossible under the HTTP protocol.

## 16. Common Pitfalls in Testing WebFlux Streaming

| Error / Symptom | Common Cause | How to Handle |
| --- | --- | --- |
| SSE test hangs forever | Waiting for `onComplete` on infinite `Flux.interval` | `returnResult` + `StepVerifier.thenCancel()` |
| `expectBodyList` waits a long time | Trying to collect an infinite response | Decode stream item-by-item with `FluxExchangeResult` |
| `StepVerifier` emits nothing in virtual time | Publisher/scheduler created outside lambda or clock not advanced | `withVirtualTime(() -> ...)`, `thenAwait` |
| `expectNoEvent` fails immediately upon subscribe | Subscription counts as an event | Place `expectSubscription()` beforehand |
| Virtual timeout test "passes" yet real I/O is slow | Virtual clock does not control network/DB | Dedicated real-server/adapter tests |
| Test still hangs despite business timeout | Verifier has no time limit or publisher is not on tested path | Use `verify(Duration)`, inspect operator chain |
| SSE status 200 yet no data arrives | Response committed or events buffered | Assert individual events and timing, verify flushing |
| Wrong `Content-Type` | Controller lacks SSE/NDJSON `produces` | Set `produces` and check `contentTypeCompatibleWith` |
| JSON decode failure | Schema/codec/generic type mismatch | Use right DTO/record and `ParameterizedTypeReference` when needed |
| Thinking `take(2)` proves upstream completed itself | `take` cancels upstream after 2 items | Distinguish downstream completion from upstream cancellation |
| Client cancels yet server keeps working | Async cancellation/cleanup, hot/shared source | Instrument `doFinally`/metrics and test resource lifecycle |
| Expecting HTTP 504 after SSE events already sent | Status/headers already committed | Emit SSE error event or close connection per contract |
| `Flux.timeout` does not cut continuous stream | Timeout resets after each `onNext` | Add a separate overall deadline if required |
| Tests flake under high CI CPU | Real-time deadlines/assertions too tight | Virtual time for logic, generous harness timeouts |
| `@WebFluxTest` lacks service | Slice does not scan normal `@Service`s | Targeted `@MockitoBean` or `@Import` |
| Using `@WebMvcTest` to test WebFlux | Wrong web stack | Use `@WebFluxTest` and `WebTestClient` |
| App boots MVC despite expecting WebFlux | Both web and webflux starters on classpath | Keep only WebFlux or set `spring.main.web-application-type=reactive` |
| Browser reconnects yet misses events | No server-side resume | Test `Last-Event-ID` and event store |
| Memory leak on slow consumer | Unbounded buffer/replay or missing cancel cleanup | Bounded buffering, backpressure policy, and metrics |

## 17. When Are Real Servers, Real Proxies, and Security Needed?

### Mock-Bound Controller Tests

Use `@WebFluxTest` when verifying routing/codecs/SSE metadata, timeout mapping with a mock service, and response contracts; no real server port needs to open.

### Real HTTP Integration

Use `@SpringBootTest(RANDOM_PORT)` when verifying items actually reach the HTTP client, server cancellation/flushing, status, and headers over a socket. For real DB/Redis/brokers, add Testcontainers and test data ownership; not every integration test requires external networks/DBs.

### Proxy/LB/Staging

A loopback HTTP test does not verify idle timeouts in nginx, Envoy, ingress, or CDNs. If SSE must survive 60 seconds with no events through a proxy, add staging tests with the real infrastructure or matching config tests. Heartbeat intervals should be shorter than the idle cutoff with an operationally grounded margin rather than guessing.

### Security and Sensitive Data

Long-lived SSE connections can outlast permission/account-status changes after the initial HTTP request was authenticated. Enforce authorization at subscription time, terminate streams on revocation if required, enforce tenant isolation and rate limiting, and test against cross-user event leaks. Use WebFlux-compatible Spring Security test support (`SecurityWebFilterChain`, `WebTestClient.mutateWith(mockUser())` from `spring-security-test` when present) rather than disabling security filters just to keep streams running.

## 18. Safe Timeout Testing Strategy in CI

1. **Pure publisher logic:** use virtual time to test `T−ε, T, T+ε` boundaries, timeout/fallback, and idle gaps. Never sleep for real.
2. **HTTP contract:** use `WebTestClient` with bounded response timeouts; verify status/headers and a bounded number of events. Never require an intentionally infinite stream to complete.
3. **Real server:** keep a focused set of integration tests for flushing/cancellation and pre-commit errors. Use random ports.
4. **External dependencies:** use stub servers/containers and test timeouts at the right client layer; keep network calls inside controlled environments.
5. **Staging proxy:** verify long connections/heartbeats/reconnects through real infrastructure; do not extrapolate from loopback.
6. **Observability:** record metrics for active SSE connections, lifetimes, disconnects/cancellations, overflows, and first-event latency; never log sensitive payloads.
7. **Never mask flakes:** avoid blindly auto-retrying until green; when flaky, investigate schedulers, CI load, timeout budgets, shared state, and cleanup.

### Minimum Acceptance Matrix

| ID | Layer | Scenario | Then |
| --- | --- | --- | --- |
| ST01 | Reactor | Virtual intervals at 10/20/30s | Three `Tick`s on schedule; completes via `take(3)` |
| ST02 | Reactor | Never emits, 3s timeout | `TimeoutException` at deadline |
| ST03 | Reactor | Slow upstream + fallback | `fallback` then completes |
| ST04 | Reactor | Fast upstream | `ready` before deadline |
| ST05 | Reactor | Cancel after one event | `SignalType.CANCEL` upstream |
| ST06 | Reactor | Silence gap after first event | Gap timeout error |
| ST07 | WebFlux slice | SSE with 2 events, stream open | HTTP 200, metadata matches, client cancels |
| ST08 | WebFlux slice | NDJSON 3 items | Exact three JSON objects, completes |
| ST09 | WebFlux slice | `Mono.never` + deadline | HTTP 504 |
| ST10 | WebFlux slice | `Mono.never` + fallback | HTTP 200, body `fallback` |
| ST11 | WebFlux slice | `Mono.just` fast | HTTP 200, body `ready` |
| ST12 | Real HTTP | SSE over socket | Receives 2 items then cancels |
| ST13 | Real HTTP | NDJSON over socket | 3 items then completes |
| ST14 | Real HTTP | Deadline over socket | 504 |

## 19. Extension Exercises

1. **SSE heartbeat:** add `ServerSentEvent.builder().comment("heartbeat")` and test that business-event consumers do not count heartbeats as `Tick`s.
2. **Last-Event-ID:** store 20 events in an in-memory bounded store, support replay from a client-supplied ID, and test reconnect with old/new cursors.
3. **First-item timeout different from inter-item timeout:** use the `Flux.timeout(firstTimeout, nextTimeout)` overload or matching timeout publisher to model distinct deadlines.
4. **Rate-limited consumers:** create a downstream that only calls `request(1)` at a time and test the overflow/drop policy against the business contract.
5. **Server disconnect cleanup:** attach `doFinally`/metrics to a server flux, close the client, and use bounded polling to verify resources are released.
6. **Remote streaming:** use WireMock/MockWebServer as an upstream to test network timeouts, retries, and cancellation via `WebClient`.
7. **Post-commit error event:** emit two SSE events followed by an upstream error; verify the client handles closure/error events properly without expecting the HTTP status to change.
8. **Backpressure policies:** compare `onBackpressureBuffer(max)`, `onBackpressureDrop`, and `onBackpressureLatest` against lossless vs lossy product requirements.
9. **SSE security:** test unauthenticated/unauthorized/tenant isolation using `spring-security-test` for the reactive stack.
10. **Staging proxy:** measure idle cutoffs through a gateway and prove heartbeats keep connections alive within required bounds.

When adding these exercises, pick mock/slice/real server according to the layer needing proof; do not dump everything into one giant `@SpringBootTest`.

## 20. Checklist Before Concluding Streaming Tests Pass

- [ ] Determined whether the endpoint is finite or infinite?
- [ ] SSE/NDJSON `Content-Type` matches the contract?
- [ ] Status and headers checked **before** consuming the stream?
- [ ] Infinite streams have `thenCancel` and `verify(Duration)`?
- [ ] Finite streams assert item counts, ordering, and `onComplete`?
- [ ] SSE `id`, `event`, `data`, and `retry` tested if clients rely on them?
- [ ] Never used `collectList`/`expectBodyList` unboundedly?
- [ ] Virtual-time tests construct publishers inside the `withVirtualTime` lambda?
- [ ] Placed `expectSubscription` before `expectNoEvent`?
- [ ] Business timeouts distinguished from client response timeouts and verifier timeouts?
- [ ] For `Flux.timeout`, understood the deadline resets after each signal?
- [ ] HTTP 504 only expected before the response commits?
- [ ] Tested fallback/success/error and upstream cancellation cleanup?
- [ ] Tested slow consumer/backpressure policy matching business rules?
- [ ] Real-server tests use random ports, time limits, and do not leak resources?
- [ ] If replay is needed, server actually supports `Last-Event-ID`?
- [ ] Tests do not demand exactly-once when protocol/system does not guarantee it?
- [ ] CI reports actual executed test counts with no unintended hangs or skips?
- [ ] Spring Boot, Reactor, JUnit versions, and test annotations are consistent?

## 21. Official References

1. [Spring Framework 6.2 — WebTestClient](https://docs.spring.io/spring-framework/reference/6.2/testing/webtestclient.html): `FluxExchangeResult`, `returnResult`, and testing streaming responses.
2. [Spring Framework — WebFlux Annotated Controllers](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/return-types.html): `Flux<ServerSentEvent>` and streaming return values.
3. [Spring Framework — Reactive HTTP Message Codecs](https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html): Reactor/WebFlux runtime model and non-blocking semantics.
4. [Project Reactor — Testing with StepVerifier](https://projectreactor.io/docs/core/release/reference/testing.html): signals, virtual time, `expectNoEvent`, `thenCancel`, `verify(Duration)`.
5. [Project Reactor — StepVerifier API](https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifier.html): API and timing guarantees.
6. [Project Reactor — Flux API](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html): `interval`, `take`, `timeout`, and backpressure.
7. [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): `@WebFluxTest`, `@MockitoBean`, `@SpringBootTest`.
8. [Spring Boot Reference — Testing](https://docs.spring.io/spring-boot/reference/testing/): updated focused test modules when using Spring Boot 4.
9. [WHATWG — Server-Sent Events Specification](https://html.spec.whatwg.org/multipage/server-sent-events.html): event stream syntax, `EventSource`, reconnect, and `Last-Event-ID`.

### Spring Boot 4 Note

The runnable snippets in Sections 8–11 target **Boot 3.5.0**. Spring Boot 4 organizes test support by technology, introducing `spring-boot-starter-webflux-test`; the package of `@WebFluxTest` changes relative to Boot 3.5's `org.springframework.boot.test.autoconfigure.web.reactive.WebFluxTest`. When upgrading, inspect the documentation and dependency tree rather than changing only the version number in the POM.

**Conclusion:** with streaming, a trustworthy test does not merely say "HTTP 200" — it verifies **incremental data, SSE metadata, emission timing, completion/error/cancellation, and timeouts at the right layers**. Virtual time proves timing logic fast and deterministically; `WebTestClient` verifies the WebFlux contract; real-server tests verify HTTP streaming over a socket. Combining all three prevents infinite hangs, flakiness, and green tests that fail to verify real behavior.