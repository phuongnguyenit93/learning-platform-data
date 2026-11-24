# Testing Flux, SSE, Cancellation, and Timeouts in Spring WebFlux

## 1. Goal: testing a stream differs from testing a single JSON response

In Spring WebFlux, an HTTP response can carry **a single object** (`Mono<T>`), **a finite sequence** (`Flux<T>`), or **a long-lived/unbounded stream** (Server-Sent Events — SSE, NDJSON streaming, etc.). Testing must observe Reactive Streams signals, not just the HTTP status.

Three key `Publisher` signals:

- `onNext(value)`: a new item arrives.
- `onComplete()`: the stream finished successfully; **not required** to happen for a continuously live SSE stream.
- `onError(error)`: the stream terminated with an error; no further `onNext` items can follow.

Besides the three downstream signals, `cancel()` is an action sent **upstream from the subscriber** to terminate a subscription. Cancellation is neither an error nor an upstream `onComplete`.

```text
                   HTTP status + headers
WebTestClient.exchange() ────────┐
                                 ▼
                       FluxExchangeResult<T>
                                 │ getResponseBody()
                                 ▼
                          decoded Flux<T>
                                 │
                         StepVerifier
                   ┌─────────────┼──────────────┐
                   ▼             ▼              ▼
              expectNext     expectError     thenCancel
                   │             │              │
             verifyComplete    verify       verify
             (finite stream) (error end)  (infinite stream)
```

**Two complementary layers of testing:**

1. **Testing the HTTP contract/streaming** with `WebTestClient`: status, `Content-Type`, SSE/NDJSON encoding, output items, and behavior when the client cancels.
2. **Testing Reactor publishers directly** with `StepVerifier`: item ordering, completion/error, backpressure, cancellation, and time operators with virtual time.

This lesson uses **Spring Framework 6.1.x, Spring Boot 3.3.x, Java 17+, and Reactor Test/JUnit 5**. Standalone Java examples and run commands are in section 7.

## 2. Finite Flux: asserting elements, order, completion, and errors

When an endpoint returns a finite sequence, check **the right content type**, ordering, element count, and terminal signal.

Pure Reactor source example:

```java
Flux<Integer> values = Flux.just(2, 4, 6);

StepVerifier.create(values)
    .expectNext(2, 4, 6)
    .verifyComplete();
```

`StepVerifier.create(...)` registers a test subscriber. `expectNext(...)` compares elements **in order**. `verifyComplete()` both expects `onComplete` and runs verification. If the source emits extra elements, emits an error, or never completes, the test fails or can hang if no verification timeout is set.

For complex data:

```java
StepVerifier.create(service.findProducts())
    .assertNext(p -> assertEquals("Notebook", p.name()))
    .expectNextMatches(p -> p.price() > 0)
    .verifyComplete();
```

This is **illustrative code**, depending on `service`, `Product.price()`, and an `assertEquals` import defined in the app. `assertNext` runs JUnit assertions inside; `expectNextMatches` uses a predicate. Use `expectNextCount(n)` when only the count of n elements matters, though for important data verify content as well.

Testing an error-terminating source:

```java
Flux<String> broken = Flux.concat(
    Flux.just("first"),
    Flux.error(new IllegalStateException("upstream failed"))
);

StepVerifier.create(broken)
    .expectNext("first")
    .expectErrorMatches(error ->
        error instanceof IllegalStateException
        && "upstream failed".equals(error.getMessage()))
    .verify();
```

These snippets require imports for `reactor.core.publisher.Flux`, `reactor.test.StepVerifier`, and JUnit assertions where needed. Note `expectErrorMatches(...).verify()` for a terminal error; never use `verifyComplete()` if the stream's contract is to emit an error.

**For HTTP endpoints returning `Flux<T>`:** `expectBodyList(T.class)` works when the response is **finite and collected completely**. For unbounded streams, use `returnResult(T.class)` to consume items as a stream without collecting the entire body.

## 3. SSE: understanding the format to write accurate assertions

**Server-Sent Events (SSE)** is a unidirectional server → client HTTP mechanism, typically responding with `Content-Type: text/event-stream`. Each event may include fields:

```text
id: 17
event: price-updated
data: {"sku":"P1","price":120}

```

A blank line marks the event boundary. There may be `retry: 5000`, multiple `data:` lines, comment lines `: heartbeat`, or data-only events. Field ordering and presence depend on the server; do not require every event to carry `id`, `event`, or `retry` unless mandated by the contract.

Spring supports `ServerSentEvent<T>`:

```java
@GetMapping(value = "/events", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
public Flux<ServerSentEvent<String>> events() {
    return Flux.interval(Duration.ofSeconds(1))
        .map(index -> ServerSentEvent.<String>builder()
            .id(String.valueOf(index))
            .event("tick")
            .data("value-" + index)
            .build());
}
```

This is an **illustrative controller snippet**; it needs imports for `GetMapping`, `MediaType`, `Flux`, `ServerSentEvent`, and `Duration`. `Flux.interval` emits 0, 1, 2... over time. Without `take(...)`, it **never completes on its own**.

Testing SSE via `WebTestClient`:

```java
FluxExchangeResult<ServerSentEvent<String>> result = client.get()
    .uri("/events")
    .accept(MediaType.TEXT_EVENT_STREAM)
    .exchange()
    .expectStatus().isOk()
    .expectHeader().contentTypeCompatibleWith(MediaType.TEXT_EVENT_STREAM)
    .returnResult(new ParameterizedTypeReference<ServerSentEvent<String>>() {});

StepVerifier.create(result.getResponseBody())
    .assertNext(e -> {
        assertEquals("tick", e.event());
        assertEquals("0", e.id());
        assertEquals("value-0", e.data());
    })
    .assertNext(e -> assertEquals("value-1", e.data()))
    .thenCancel()
    .verify(Duration.ofSeconds(5));
```

Requires imports `FluxExchangeResult`, `ParameterizedTypeReference`, `StepVerifier`, `MediaType`, `ServerSentEvent`, `Duration`, and JUnit assertions. This is **illustrative code**; `client` must be initialized properly; section 7 has the complete example. `returnResult(new ParameterizedTypeReference<...>() {})` preserves generic type info so the decoder selects `ServerSentEvent<String>`. If you only want `data`, you can decode directly into `String` per the media type and codec, but when checking `id/event/retry` decode as `ServerSentEvent<T>`.

**Do not assert raw bytes rigidly** when the goal is semantics: encoders can format newlines or metadata slightly differently across codecs/versions. Check status, `Content-Type`, data, and event metadata per the contract. Check raw SSE frames separately only when the contract mandates exact wire formatting.

### SSE vs. WebSocket and NDJSON

- **SSE:** unidirectional server → client over HTTP, media type `text/event-stream`, event framing with `data/id/event/retry`.
- **NDJSON:** multiple JSON objects line by line, media type typically `application/x-ndjson`; decodable as `Flux<Dto>`, with no SSE metadata.
- **WebSocket:** bidirectional connection with different protocol framing; do not use `WebTestClient` SSE assertions to test a WebSocket session. For WebSocket use `WebSocketClient`/`WebSocketHandler` or an appropriate testing tool.

`Content-Type` only tells how the body is interpreted; it does not automatically guarantee a real server emits chunks without proxy buffering, so run real HTTP tests when verifying network streaming.

## 4. Never wait for onComplete on an infinite stream

This is an **anti-pattern**:

```java
// Wrong if endpoint /events never emits onComplete:
client.get().uri("/events")
    .exchange()
    .expectBodyList(String.class)
    .hasSize(10);
```

`expectBodyList` generally tries to read the entire response to collect all items; a continuous stream may never finish and consume unbounded time/memory. Similarly, `collectList().block()` or `blockLast()` on an infinite `Flux.interval` is inappropriate.

The right approach: verify a meaningful number of events and then **explicitly cancel** the subscription:

```java
StepVerifier.create(result.getResponseBody())
    .expectNextCount(3)
    .thenCancel()
    .verify(Duration.ofSeconds(5));
```

`thenCancel()` expresses the expectation clearly: **the test stops after three events, without requiring the server to send `onComplete`**. The `verify(Duration.ofSeconds(5))` bound ensures the test fails within a time limit if events never arrive.

`take(n)` can create a **downstream finite Flux**, for example:

```java
StepVerifier.create(source.take(3))
    .expectNextCount(3)
    .verifyComplete();
```

`take(3)` consumes three items, then **cancels the upstream subscription** and emits `onComplete` downstream. “Downstream completed” and “upstream was cancelled” are two distinct yet compatible observations. If producer-side cleanup must be proven, observe the cancel signal or `doFinally` at the source.

## 5. Cancellation: verifying the right SignalType and cleanup

**Cancellation** happens when the consumer no longer wants more data. Examples: a browser tab closes, an SSE client disconnects, `StepVerifier.thenCancel()`, downstream `take(2)`, or a timeout cancels the source. Reactive Streams sends `cancel()` back upstream; the rest of the pipeline can run `doOnCancel` and `doFinally(SignalType.CANCEL)`.

Simple example:

```java
AtomicInteger cancelCalls = new AtomicInteger();

Flux<Long> source = Flux.interval(Duration.ofMillis(20))
    .doOnCancel(cancelCalls::incrementAndGet);

StepVerifier.create(source)
    .expectNext(0L, 1L)
    .thenCancel()
    .verify(Duration.ofSeconds(3));

assertEquals(1, cancelCalls.get());
```

This is an illustrative snippet; it requires imports `AtomicInteger`, `Duration`, `Flux`, `StepVerifier`, and `assertEquals`. Writing this with `Flux.interval` and real wall-clock time can be affected by scheduling; section 7 shows a more deterministic **virtual time** test.

Distinguishing callbacks:

```java
source
    .doOnCancel(() -> cleanupSubscription())
    .doFinally(signal -> recordFinalSignal(signal));
```

- `doOnCancel` runs when the source receives cancel.
- `doFinally` runs after complete, error, or cancel; distinguish them via `SignalType.ON_COMPLETE`, `ON_ERROR`, `CANCEL`.
- `doOnTerminate` only reflects onComplete/onError at that operator point and **does not replace** `doFinally` when resources must also be cleaned up on cancellation.
- When registering resources such as listeners, timers, file handles, or broker subscriptions, use `Flux.using`/`usingWhen` or equivalent cleanup; make cleanup idempotent because multiple error/timeout paths can interact.
- `StepVerifier.thenCancel` verifies the client stream stops per the scenario, **and does not by itself prove the kernel socket closed or the server container released the connection**. Run real network/lifecycle tests when that is a requirement.

**Testing cancellation is not the same as testing backpressure**: backpressure is `request(n)` regulating demand; cancel terminates the subscription. To check requested counts, use `StepVerifier.create(source, initialRequest)` followed by `thenRequest(n)` with `TestPublisher` or a demand-respecting source. Never infer demand from the number of events observed.

## 6. Three different kinds of time limits

| Mechanism | What is bounded | Behavior when exceeded |
| --- | --- | --- |
| `WebTestClient.Builder.responseTimeout(Duration)` | How long WebTestClient waits for a **response** during exchange; Spring 6.1 default is 5 seconds | Exchange/test can fail for waiting too long for the response |
| `StepVerifier.verify(Duration)` | Maximum real time allowed for **StepVerifier's assertion script** | Test fails if terminal/cancel expectation isn't reached in time; not an HTTP response |
| Reactor `Publisher.timeout(Duration)` | Wait interval for the publisher's next signal (or per-item timeout depending on overload) | Emits `TimeoutException` downstream and cancels upstream |
| Reactor `take(Duration)` | Duration during which items are allowed to be emitted | Completes downstream when time elapses, usually cancelling upstream |
| Underlying HTTP client connect/read/response timeout | DNS/TCP connect, waiting for response bytes, transport | Corresponding request/transport error, distinct from Reactor timeouts |
| Business deadline across retries | Total time covering request, retries, and processing | Depends on pipeline design and operator placement |

### Timeout for WebTestClient

`WebTestClient` bound directly to a mock controller/router (no server needed):

```java
WebTestClient client = WebTestClient
    .bindToController(new EventController())
    .configureClient()
    .responseTimeout(Duration.ofSeconds(5))
    .build();
```

This is illustrative configuration; section 7 has a real class. WebTestClient's `responseTimeout` protects waiting for the response; for an **already started** SSE stream, use `StepVerifier.verify(Duration)` to bound event observation time. Never treat `responseTimeout(5s)` as a contract saying “every SSE connection must close after 5s.”

### Timeout inside a Reactor pipeline

`timeout` emits an error if no signal arrives before the deadline:

```java
Mono<String> expensive = Mono.delay(Duration.ofSeconds(10))
    .map(value -> "ready")
    .timeout(Duration.ofSeconds(3));
```

This publisher is expected to emit `TimeoutException` (from `java.util.concurrent`) rather than `"ready"`. Note that `timeout` **is not just a test assertion**: it is a production operator that cancels the upstream subscription. For a `Flux` with continuous events, `timeout(Duration.ofSeconds(3))` monitors the gap **between events**; a stream steadily receiving events can live much longer than 3s. To enforce a **total** deadline across an interaction, design a separate time budget (e.g., wrap the overall `Mono` result or use `take(Duration)` for a stream).

`take(Duration)` has a different meaning:

```java
Flux<Long> finite = Flux.interval(Duration.ofSeconds(1))
    .take(Duration.ofSeconds(3));
```

When the window expires, downstream can receive `onComplete` instead of a timeout error. Ordering, exact boundary item counts, and scheduler choice can affect results; when tests need exact counts, use virtual time and control the clock.

## 7. Complete Java 17+ example with JUnit 5, Spring WebFlux, and Reactor Test

This project **does not need to start a real HTTP server**. `WebTestClient.bindToController(...)` uses mock server binding to test WebFlux endpoints and SSE/NDJSON decoders, while `StepVerifier.withVirtualTime(...)` tests publisher cancellation and timeouts without waiting real-world seconds.

Structure:

```text
flux-sse-test/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/demo/
    │   └── StreamController.java
    └── test/java/demo/
        ├── StreamControllerTest.java
        └── PublisherTimingTest.java
```

**`settings.gradle`**

```groovy
rootProject.name = 'flux-sse-test'
```

**`build.gradle`** — requires JDK 17+, Gradle 8.x:

```groovy
plugins {
    id 'java'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation platform('org.springframework.boot:spring-boot-dependencies:3.3.13')
    testImplementation platform('org.springframework.boot:spring-boot-dependencies:3.3.13')

    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.test {
    useJUnitPlatform()
}
```

The Spring Boot BOM manages compatible dependency versions, including Reactor. `reactor-test` contains `StepVerifier` and is not production code to put in `implementation`. No Boot plugin is required because the example only runs unit/web-layer tests.

**`src/main/java/demo/StreamController.java`**

```java
package demo;

import java.time.Duration;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Flux;

@RestController
public class StreamController {
    private final AtomicInteger canceled = new AtomicInteger();

    public int cancellationCount() {
        return canceled.get();
    }

    @GetMapping(value = "/items", produces = MediaType.APPLICATION_NDJSON_VALUE)
    public Flux<Item> items() {
        return Flux.just(
            new Item(1, "Notebook"),
            new Item(2, "Pen")
        );
    }

    @GetMapping(value = "/events", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public Flux<ServerSentEvent<String>> events() {
        return Flux.interval(Duration.ofMillis(25))
            .map(index -> ServerSentEvent.<String>builder()
                .id(Long.toString(index))
                .event("tick")
                .data("value-" + index)
                .build())
            .doOnCancel(canceled::incrementAndGet);
    }

    public record Item(int id, String name) {}
}
```

`/items` is **finite NDJSON**; `/events` is **unbounded SSE** until downstream cancels or the connection closes. `AtomicInteger` tracks how many times the source was cancelled when needed; HTTP tests avoid relying on it directly to prevent races between mock exchange and cleanup.

**`src/test/java/demo/StreamControllerTest.java`**

```java
package demo;

import java.time.Duration;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.test.web.reactive.server.FluxExchangeResult;
import org.springframework.test.web.reactive.server.WebTestClient;

import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;

class StreamControllerTest {
    private WebTestClient client;

    @BeforeEach
    void setUp() {
        client = WebTestClient.bindToController(new StreamController())
            .configureClient()
            .responseTimeout(Duration.ofSeconds(5))
            .build();
    }

    @Test
    void finiteNdjsonFluxHasTwoItemsAndCompletes() {
        FluxExchangeResult<StreamController.Item> result = client.get()
            .uri("/items")
            .accept(MediaType.APPLICATION_NDJSON)
            .exchange()
            .expectStatus().isOk()
            .expectHeader()
            .contentTypeCompatibleWith(MediaType.APPLICATION_NDJSON)
            .returnResult(StreamController.Item.class);

        StepVerifier.create(result.getResponseBody())
            .expectNext(
                new StreamController.Item(1, "Notebook"),
                new StreamController.Item(2, "Pen"))
            .verifyComplete();
    }

    @Test
    void sseHasMetadataAndCanBeCanceledAfterTwoEvents() {
        FluxExchangeResult<ServerSentEvent<String>> result = client.get()
            .uri("/events")
            .accept(MediaType.TEXT_EVENT_STREAM)
            .exchange()
            .expectStatus().isOk()
            .expectHeader()
            .contentTypeCompatibleWith(MediaType.TEXT_EVENT_STREAM)
            .returnResult(
                new ParameterizedTypeReference<ServerSentEvent<String>>() {});

        StepVerifier.create(result.getResponseBody())
            .assertNext(event -> {
                assertEquals("0", event.id());
                assertEquals("tick", event.event());
                assertEquals("value-0", event.data());
            })
            .assertNext(event -> {
                assertEquals("1", event.id());
                assertEquals("value-1", event.data());
            })
            .thenCancel()
            .verify(Duration.ofSeconds(5));
    }
}
```

**Points to observe:** test 1 finishes with `verifyComplete()` because two items are the entire response. Test 2 finishes with `thenCancel()` because the stream has no natural `onComplete`. `ParameterizedTypeReference` preserves `ServerSentEvent<String>` so `id`, `event`, and `data` can all be verified after client decoding.

**`src/test/java/demo/PublisherTimingTest.java`**

```java
package demo;

import java.time.Duration;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;

class PublisherTimingTest {

    @Test
    void cancelNotifiesUpstream() {
        AtomicInteger cancelCalls = new AtomicInteger();

        StepVerifier.withVirtualTime(() ->
                Flux.interval(Duration.ofSeconds(1))
                    .doOnCancel(cancelCalls::incrementAndGet))
            .expectSubscription()
            .thenAwait(Duration.ofSeconds(2))
            .expectNext(0L, 1L)
            .thenCancel()
            .verify(Duration.ofSeconds(2));

        assertEquals(1, cancelCalls.get());
    }

    @Test
    void timeoutEmitsErrorAndCancelsUpstream() {
        AtomicInteger cancelCalls = new AtomicInteger();

        StepVerifier.withVirtualTime(() ->
                Mono.delay(Duration.ofSeconds(10))
                    .doOnCancel(cancelCalls::incrementAndGet)
                    .timeout(Duration.ofSeconds(3)))
            .expectSubscription()
            .expectNoEvent(Duration.ofSeconds(2))
            .thenAwait(Duration.ofSeconds(1))
            .expectError(TimeoutException.class)
            .verify(Duration.ofSeconds(2));

        assertEquals(1, cancelCalls.get());
    }
}
```

Explanation of the two timing tests:

- `withVirtualTime(Supplier<Publisher>)` replaces Reactor's time scheduler to test operators like `interval`/`delay`/`timeout` without waiting 10 real seconds. **The Publisher must be created lazily inside the lambda**; declaring `Mono.delay(...)` outside and passing it in can leave the test using the real scheduler.
- `expectSubscription()` consumes the subscription signal before calling `expectNoEvent(...)`. Calling `expectNoEvent` right at the start without consuming the subscription signal can fail.
- `thenAwait(...)` advances the virtual clock. A `timeout(3s)` is verified via 2s with no events, advancing 1 more second, and expecting the error.
- `verify(Duration.ofSeconds(2))` is the **test's real-time timeout**, preventing the test from hanging if the virtual time script is misconfigured. It does not turn into a production `timeout` operator.
- `doOnCancel` on the source measures upstream cancellation. Both explicit `thenCancel()` and an expired `timeout(...)` can send cancel to the source.
- SSE events through `WebTestClient` still use the real scheduling/codecs of mock WebFlux execution; do not apply virtual time indiscriminately to whole HTTP tests unless you completely control all schedulers and lifecycles.

Run in the project directory:

```bash
gradle test
```

When all four tests pass, Gradle finishes with:

```text
BUILD SUCCESSFUL
```

Exact log lines and total duration vary by machine; Gradle generates the default report at `build/reports/tests/test/index.html`. This is the **expected result when run**, not a captured transcript. You can use the Gradle Wrapper if available (`./gradlew test` or `gradlew.bat test`).

## 8. Separating timing logic tests from HTTP I/O and network behavior

`WebTestClient.bindToController(...)` uses WebFlux mock requests/responses and exercises controllers/codecs without crossing a TCP socket. It is a fast option for checking status, media types, and event decoding. To test **true end-to-end streaming**, you can use:

```java
WebTestClient client = WebTestClient.bindToServer()
    .baseUrl("http://127.0.0.1:8080")
    .responseTimeout(Duration.ofSeconds(5))
    .build();
```

This is an **illustrative snippet**; a server must be running on that port. With Spring Boot, run `@SpringBootTest(webEnvironment = RANDOM_PORT)`, inject `@LocalServerPort` for a dynamic base URL, or use `@AutoConfigureWebTestClient` where appropriate. Network-level tests are useful for chunk flushing, HTTP proxies, load balancers, TCP disconnects, TLS, and connector behavior.

**Prefer virtual time for business Reactor publishers** using `delay`, `interval`, `timeout`, and default schedulers. It does not speed up real wall time for:
- HTTP networking, DNS/TLS/connection pools.
- Schedulers instantiated separately and captured outside the lambda.
- Blocking I/O, `Thread.sleep`, or external services.
- Requests processed on schedulers outside the virtualized system.

Live stream tests in CI need finite bounds and comfortable event intervals to avoid flakiness from CPU scheduling. Whenever possible, separate “HTTP decodes two events” tests from publisher-level virtual-time tests.

## 9. Testing realistic cancellation and advanced backpressure

Demand counts (`request(n)`) can be tested with `StepVerifier` when the source supports backpressure:

```java
Flux<Integer> demandAware = Flux.range(1, 10);

StepVerifier.create(demandAware, 0)
    .expectSubscription()
    .thenRequest(2)
    .expectNext(1, 2)
    .thenRequest(1)
    .expectNext(3)
    .thenCancel()
    .verify(Duration.ofSeconds(2));
```

Explanation: `create(source, 0)` starts with zero initial demand, `thenRequest(2)` requests two items, then one more. `thenCancel` stops the stream even though the source could emit up to 10 values. This tests whether the publisher **honors demand**, not the exact count of TCP chunks or HTTP packets sent.

For real resources, combine `doFinally` or `usingWhen` with assertions at the **right upstream point**:

```java
AtomicReference<SignalType> finalSignal = new AtomicReference<>();

Flux<Long> source = Flux.interval(Duration.ofSeconds(1))
    .doFinally(finalSignal::set);

StepVerifier.withVirtualTime(() -> source)
    .expectSubscription()
    .thenAwait(Duration.ofSeconds(1))
    .expectNext(0L)
    .thenCancel()
    .verify(Duration.ofSeconds(2));
```

**This snippet only illustrates the idea**; when writing serious virtual-time tests, **construct `Flux.interval` inside the lambda itself**, rather than referencing a `source` created outside as in this sketch. Correct version:

```java
AtomicReference<SignalType> finalSignal = new AtomicReference<>();

StepVerifier.withVirtualTime(() ->
        Flux.interval(Duration.ofSeconds(1))
            .doFinally(finalSignal::set))
    .expectSubscription()
    .thenAwait(Duration.ofSeconds(1))
    .expectNext(0L)
    .thenCancel()
    .verify(Duration.ofSeconds(2));

assertEquals(SignalType.CANCEL, finalSignal.get());
```

Requires imports `AtomicReference` and `reactor.core.publisher.SignalType`. `doFinally` runs on terminal/cancel signals, making it well suited for verifying cleanup signals. In concurrent production tests, never read an asynchronous cleanup variable immediately without synchronization; use `CountDownLatch`/`Awaitility` or a signal sink with bounded waiting.

## 10. Common mistakes

1. **`expectBodyList` / `collectList` on an infinite SSE stream.** The test waits forever or buffers unboundedly. Use `returnResult` and `thenCancel` after a few events.
2. **Calling `verifyComplete()` after a few events on an infinite stream.** No `onComplete` is expected; end with `thenCancel().verify(Duration)`.
3. **Omitting a test timeout.** A broken scenario can hang the pipeline or wait indefinitely; pass `verify(Duration)` for streams.
4. **Confusing `verify(Duration)` with `Publisher.timeout(Duration)`.** The first bounds the test runner; the second changes the live pipeline and emits `TimeoutException`.
5. **Using `withVirtualTime` while creating `Flux.interval` before the supplier.** The scheduler was already captured; the test will not speed up as expected.
6. **Calling `expectNoEvent` before consuming the subscription.** Subscription itself is an event; call `expectSubscription()` first.
7. **Asserting only HTTP 200 for SSE.** The response may have zero events or wrong schema; verify `Content-Type`, payloads, and event id/type as needed.
8. **Decoding SSE as String and assuming metadata was tested.** When verifying `id/event/retry`, decode as `ServerSentEvent<T>`.
9. **Assuming downstream cancellation always proves the socket closed.** `thenCancel` checks the reactive subscription; use network integration tests for connection closure.
10. **Forgetting that cancel is neither onComplete nor onError.** Cleanup in `doOnTerminate` misses cancellation; use `doFinally`/`doOnCancel` where appropriate.
11. **Confusing stream inactivity timeout with total deadline.** `Flux.timeout(3s)` will not fail if events arrive every 2s; total deadlines require a different policy.
12. **Asserting exact real-time event timestamps in CI.** CPU scheduling and OS jitter cause flakiness; test timing logic with virtual time.
13. **Using virtual time for real HTTP networking** and expecting minutes of network transfer to run instantly; virtual clocks do not replace network I/O.
14. **Ignoring production client disconnects/reconnects.** SSE clients need retry/backoff and `Last-Event-ID` if using cursors/replay; servers need cleanup on cancel and slow-consumer handling.

## 11. Self-check questions

1. **An SSE stream never completes: should you use `verifyComplete` or `thenCancel`?** → `thenCancel` after asserting enough events, paired with `verify(Duration)` to bound the wait.
2. **When `Flux.take(2)` completes downstream, what does upstream receive?** → Normally upstream receives `cancel()` after delivering two items.
3. **When do you need `returnResult(new ParameterizedTypeReference<ServerSentEvent<T>>() {})`?** → When decoding SSE with generic data and checking `id/event/retry` metadata.
4. **Why avoid `expectBodyList` on an infinite stream?** → It waits for the body to finish and can accumulate unbounded data.
5. **If SSE emits every 2 seconds with `timeout(3s)`, is a 5-minute stream an error?** → Not necessarily; timeout measures gaps between events, not total deadline.
6. **Does `verify(Duration.ofSeconds(2))` inject a timeout into the application pipeline?** → No; it only limits how long the test waits for verification.
7. **Does virtual time accelerate a real HTTPS request?** → No; it only drives controlled Reactor operators/schedulers.
8. **When a subscriber cancels, where should listeners be cleaned up?** → In resource lifecycle hooks such as `doFinally(CANCEL)`, `doOnCancel`, or `usingWhen`, accompanied by side-effect tests.
9. **How does testing `request(n)` differ from testing cancel?** → `request(n)` signals demand; `cancel()` ends the subscription. Use StepVerifier `initialRequest` + `thenRequest`.
10. **Does mock WebFlux SSE testing guarantee production proxies will not buffer?** → No; end-to-end streaming tests through real proxies/HTTP connectors are required.

## 12. References

- Spring Framework — WebTestClient, streaming response assertions: https://docs.spring.io/spring-framework/reference/testing/webtestclient.html
- Spring Framework — WebFlux annotated SSE controllers: https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/return-types.html
- Spring Framework 6.1 Javadoc — WebTestClient.Builder responseTimeout: https://docs.spring.io/spring-framework/docs/6.1.13/javadoc-api/org/springframework/test/web/reactive/server/WebTestClient.Builder.html
- Spring Framework — ServerSentEvent Javadoc: https://docs.spring.io/spring-framework/docs/6.1.13/javadoc-api/org/springframework/http/codec/ServerSentEvent.html
- Reactor Core — Testing with StepVerifier and virtual time: https://projectreactor.io/docs/core/release/reference/testing.html
- Reactor Test API — StepVerifier: https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifier.html
- Reactive Streams Specification — Subscriber demand and cancellation: https://www.reactive-streams.org/
