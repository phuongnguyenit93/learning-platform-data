# Testing Flux, SSE, and Unbounded Streams with StepVerifier in Spring WebFlux

## 1. Lesson objectives

Spring WebFlux can return responses containing multiple elements over time, such as `Flux<OrderEvent>`, `Flux<ServerSentEvent<Alert>>`, JSON Lines/NDJSON streams, or streams read from a broker. Unlike finite JSON responses, these streams **may never emit onComplete**. Testing a streaming endpoint therefore cannot simply call `expectBodyList(...)` and wait for the whole response to finish.

This lesson focuses on combining:

- `reactor-test`'s `StepVerifier` to verify `Flux` signals.
- Spring's `WebTestClient` to make HTTP requests to a WebFlux controller and read streaming responses.
- `FluxExchangeResult<T>.getResponseBody()` to obtain the client-side Flux after verifying HTTP status and headers.
- `thenCancel()` to finish a time-bounded test against a **business stream that has no completion point**.
- `withVirtualTime(...)` to test timers, delays, and timeouts using a virtual clock at the Reactor layer without real waiting.
- `TestPublisher` and `PublisherProbe` to simulate upstream/errors/cancellation deterministically.
- Distinguishing HTTP status, media type, SSE framing, and decoded application data.

After this lesson, learners should know how to test a finite Flux, an infinite Flux, HTTP SSE, NDJSON streaming, a mid-stream error source, and subscription cancellation propagation—while avoiding hanging, flaky, or wrong-contract tests.

## 2. Distinguishing three testing layers

~~~text
                        WebTestClient
                             |
                             | HTTP GET /api/streams/sse
                             v
                      WebFlux Controller
                             |
                             | Flux<ServerSentEvent<Notice>>
                             v
                HttpMessageWriter / SSE Encoder
                             |
                             | HTTP response
                             | Content-Type: text/event-stream
                             v
                  FluxExchangeResult<T>
                             |
                             | getResponseBody()
                             v
                         StepVerifier
                  value, order, timing, error,
                  completion, cancellation
~~~

There are three distinct questions:

1. **HTTP contract:** is the status 200, and is the response header `text/event-stream` or `application/x-ndjson`?
2. **Stream contract:** which objects does the client receive, are they in order, and are there errors?
3. **Lifecycle contract:** is the source finite or infinite, when does downstream cancel, and does upstream clean up resources?

`WebTestClient` checks the HTTP part, while `StepVerifier` expresses expectations on the publisher. Together, they test more layers than a test calling the controller method directly.

Do not use a "response body equals fixed string" assertion to test every event stream. SSE responses have framing and may include heartbeat comments, retry, id, and line breaks; normally you should assert decoded data and the metadata that actually matters.

## 3. Finite Flux and non-terminating Flux

A `Flux<T>` can complete normally, terminate with an error, or never terminate on its own.

| Source | Typical signals | Suitable test |
| --- | --- | --- |
| `Flux.just("A", "B")` | onNext A, B then onComplete | expectNext + verifyComplete |
| `Flux.empty()` | onComplete, no onNext | verifyComplete |
| `Flux.error(ex)` | onError | expectError/expectErrorMatches |
| `Flux.interval(Duration)` | emits over time, does not complete by default | expectNextCount + thenCancel |
| `Flux.never()` | no onNext, no terminal signal | expectSubscription + thenCancel |
| Hot broker/feed | Can emit indefinitely and stop on cancel | TestPublisher/Sinks + thenCancel |
| `Flux.interval(...).take(3)` | emits 3 elements then completes | expectNext + verifyComplete |

### 3.1. Testing finite streams

~~~java
Flux<Integer> numbers = Flux.just(1, 2, 3);

StepVerifier.create(numbers)
    .expectNext(1, 2, 3)
    .verifyComplete();
~~~

`verifyComplete()` succeeds only when downstream emits the exact three elements and `onComplete`. If the Flux emits a fourth value, the test fails.

### 3.2. Testing streams without onComplete

~~~java
Flux<Long> ticks = Flux.interval(Duration.ofMillis(100));

StepVerifier.create(ticks)
    .expectNext(0L, 1L, 2L)
    .thenCancel()
    .verify(Duration.ofSeconds(3));
~~~

This is a **time-bounded test**, even though the source is infinite. `thenCancel()` cancels the subscription after three elements. It **does not** verify that the source completes on its own.

If you replace `thenCancel()` with `verifyComplete()`, the test will wait for a signal that never arrives. With a timeout, the test fails; without a timeout, the test risks hanging indefinitely.

### 3.3. Testing a completely silent source

~~~java
Flux<String> silent = Flux.never();

StepVerifier.create(silent)
    .expectSubscription()
    .thenCancel()
    .verify(Duration.ofSeconds(2));
~~~

`Flux.never()` emits neither items nor terminal signals. If you want to prove no items arrive for a duration, use `expectNoEvent(Duration)` after `expectSubscription()`. That has temporal meaning, unlike canceling immediately.

## 4. StepVerifier is a scripted subscriber

Key methods:

| API | Meaning |
| --- | --- |
| `StepVerifier.create(publisher)` | Builds verification script and subscribes on verify |
| `expectSubscription()` | Expects subscription |
| `expectNext(value)` | Expects a specific value |
| `expectNextMatches(predicate)` | Expects a value matching a condition |
| `assertNext(consumer)` | Runs assertions on the object |
| `expectNextCount(n)` | Expects n arbitrary elements |
| `expectNoEvent(duration)` | Must have no events during the duration |
| `thenAwait(duration)` | Advances time without asserting "no event" |
| `then(Runnable)` | Drives the source/side effects during the test |
| `thenRequest(n)` | Grants additional Reactive Streams demand |
| `thenCancel()` | Actively cancels downstream |
| `expectComplete()` | Requires completion |
| `expectError(...)` | Requires error |
| `verify(Duration)` | Executes the test with a time limit |
| `verifyComplete()` | Shortcut verifying completion |

**Mind the order:** creating the builder with `StepVerifier.create(...)` does not subscribe yet. Steps execute only when `verify(...)` is called. If using a hot source like TestPublisher, emit data via `then(...)` after the subscription step.

Example checking an object:

~~~java
StepVerifier.create(service.findAll())
    .assertNext(item -> {
        assertEquals("Keyboard", item.name());
        assertTrue(item.price().signum() > 0);
    })
    .expectNextCount(2)
    .verifyComplete();
~~~

In another test, if the service is a non-terminating feed, replace the terminal expectation with `thenCancel()`.

## 5. What is SSE and when is it used?

**Server-Sent Events (SSE)** is a one-way HTTP streaming mechanism from server to client. The client sends a normal request (usually GET), and the server responds with `Content-Type: text/event-stream` and keeps the response open to push events continuously.

SSE differs from WebSocket:

| Characteristic | SSE | WebSocket |
| --- | --- | --- |
| Primary direction | Server → client | Bidirectional |
| Transport | Long-lived HTTP response | WebSocket handshake/frames |
| Media type | text/event-stream | Not a typical MIME response stream |
| Browser API | EventSource | WebSocket |
| Reconnect | EventSource has built-in reconnect | Application manages reconnect |
| Event ID | id/Last-Event-ID | Custom-defined if needed |
| Testing | WebTestClient + StepVerifier | WebSocketClient + reactive test |

SSE can be emitted from a Spring WebFlux controller with:

~~~java
@GetMapping(
    path = "/events",
    produces = MediaType.TEXT_EVENT_STREAM_VALUE
)
public Flux<ServerSentEvent<String>> events() {
    return Flux.interval(Duration.ofSeconds(1))
        .map(i -> ServerSentEvent.<String>builder()
            .id(Long.toString(i))
            .event("tick")
            .data("tick-" + i)
            .build());
}
~~~

`ServerSentEvent<T>` belongs to package `org.springframework.http.codec`. This wrapper lets you set `id`, `event`, `retry`, `comment`, and `data` metadata. If only the payload is needed, WebFlux can write a `Flux<T>` as SSE when mapping/content negotiation selects `text/event-stream`, though using the wrapper is clearer when metadata is needed.

## 6. SSE structure on the wire

An SSE event typically contains lines:

~~~text
id:0
event:notice
retry:3000
data:{"sequence":0,"message":"notice-0"}

~~~

A blank line terminates an event. A stream can contain many consecutive events in the same HTTP response without a wrapping JSON array.

Meanings:

- `id`: event ID, allowing clients to send `Last-Event-ID` on reconnect.
- `event`: event type received by the browser's `EventSource.addEventListener("notice", ...)`.
- `retry`: suggested reconnect time, in **milliseconds** when written to SSE wire format.
- `data`: payload, typically text or JSON.
- Lines starting with a colon `:`: comments, usable as keepalives.
- Blank line: boundary between events.

Do not compare all SSE newlines/field order verbatim when the test goal is domain data. Prefer decoding to `ServerSentEvent<Notice>` and asserting `id()`, `event()`, `data()`, and `retry()`.

**Important limitation:** Having an SSE id is not enough to guarantee resume. The server must actually read `Last-Event-ID`, store or query event history, and define replay semantics. A demo using only `Flux.interval` per connection has no durable event log.

## 7. WebTestClient testing HTTP streaming properly

Spring Framework officially recommends for streaming responses such as `text/event-stream` or `application/x-ndjson`:

1. Send the HTTP request with an appropriate Accept header.
2. Call `exchange()`.
3. Verify status and headers.
4. Use `returnResult(Type)` to receive `FluxExchangeResult<T>`.
5. Call `result.getResponseBody()` to get `Flux<T>`.
6. Use StepVerifier to check a few items and **thenCancel** if the stream does not terminate.

~~~java
FluxExchangeResult<MyEvent> result =
    webTestClient.get()
        .uri("/api/events")
        .accept(MediaType.TEXT_EVENT_STREAM)
        .exchange()
        .expectStatus().isOk()
        .expectHeader()
            .contentTypeCompatibleWith(
                MediaType.TEXT_EVENT_STREAM)
        .returnResult(MyEvent.class);

StepVerifier.create(result.getResponseBody())
    .assertNext(event -> assertEquals("A", event.message()))
    .expectNextCount(2)
    .thenCancel()
    .verify(Duration.ofSeconds(8));
~~~

This is an API-illustrating **snippet**; the MyEvent class and matching endpoint belong to a hypothetical application. The complete demo at the end of the article uses `Notice` and runs standalone.

### 7.1. Why is returnResult necessary?

With a finite JSON response, you can write:

~~~java
webTestClient.get()
    .uri("/api/products")
    .exchange()
    .expectStatus().isOk()
    .expectBodyList(Product.class)
    .hasSize(3);
~~~

Body list assertions need to receive the full response and decode it into a collection. But if the endpoint is infinite SSE, the body never finishes, so the body-list assertion has no natural stopping point.

`returnResult(...)` hands control of the decoded Flux back to the test. It lets you request items one by one, verify order, cancel after N items, and avoid waiting for an infinite response.

### 7.2. Choosing how to decode

- SSE containing only plain strings: `returnResult(String.class)` can be used to receive data decoded per client config.
- SSE with metadata: use `returnResult(new ParameterizedTypeReference<ServerSentEvent<Notice>>() {})` to preserve the generic type.
- NDJSON: `returnResult(Notice.class)` to receive individual JSON objects.
- SSE needing exact wire byte framing checks: use a specialized decoder/raw response; do not conflate with domain object tests.

Do not rely on erased Java generics like `ServerSentEvent.class` and directly cast `data()` to Notice. For complex DTOs, use `ParameterizedTypeReference` to preserve generic types for the codec.

## 8. Testing SSE metadata with generic types

Example endpoint returning `Flux<ServerSentEvent<Notice>>`. In the test:

~~~java
FluxExchangeResult<ServerSentEvent<Notice>> response =
    webTestClient.get()
        .uri("/api/streams/sse")
        .accept(MediaType.TEXT_EVENT_STREAM)
        .exchange()
        .expectStatus().isOk()
        .expectHeader()
            .contentTypeCompatibleWith(
                MediaType.TEXT_EVENT_STREAM)
        .returnResult(
            new ParameterizedTypeReference<
                ServerSentEvent<Notice>>() {}
        );

StepVerifier.create(response.getResponseBody())
    .assertNext(event -> {
        assertEquals("0", event.id());
        assertEquals("notice", event.event());
        assertEquals(Duration.ofSeconds(3), event.retry());
        assertEquals(
            new Notice(0L, "notice-0"), event.data()
        );
    })
    .assertNext(event ->
        assertEquals(
            new Notice(1L, "notice-1"), event.data()
        )
    )
    .thenCancel()
    .verify(Duration.ofSeconds(8));
~~~

This is a **streaming contract** test: it does not wait for completion, yet checks the first two events, id, event name, and retry metadata. Because the stream is hot/timer-driven per request, event order is 0 then 1; do not attach expectations that responses must arrive after exactly 100.000 milliseconds over a real network.

## 9. NDJSON: one JSON object per line

`application/x-ndjson` is a streaming format consisting of multiple JSON values separated by newlines:

~~~text
{"sequence":0,"message":"notice-0"}
{"sequence":1,"message":"notice-1"}
{"sequence":2,"message":"notice-2"}
~~~

Unlike `application/json` containing one complete array:

~~~json
[
  {"sequence":0,"message":"notice-0"},
  {"sequence":1,"message":"notice-1"},
  {"sequence":2,"message":"notice-2"}
]
~~~

With NDJSON, clients can decode each object before the HTTP response finishes. In WebFlux:

~~~java
@GetMapping(
    path = "/ndjson",
    produces = MediaType.APPLICATION_NDJSON_VALUE
)
public Flux<Notice> ndjson() {
    return service.live();
}
~~~

Test:

~~~java
FluxExchangeResult<Notice> result = webTestClient.get()
    .uri("/api/streams/ndjson")
    .accept(MediaType.APPLICATION_NDJSON)
    .exchange()
    .expectStatus().isOk()
    .expectHeader()
    .contentTypeCompatibleWith(MediaType.APPLICATION_NDJSON)
    .returnResult(Notice.class);

StepVerifier.create(result.getResponseBody())
    .assertNext(n -> assertEquals(0L, n.sequence()))
    .assertNext(n -> assertEquals(1L, n.sequence()))
    .thenCancel()
    .verify(Duration.ofSeconds(8));
~~~

Do not assume NDJSON and SSE share the same wire format. NDJSON lacks SSE's `event`, `id`, and `retry` fields; for clients needing only JSON rows, NDJSON is often simpler. Browser EventSource does not automatically read NDJSON like SSE.

## 10. verifyComplete, thenCancel, and take(n) mean different things

These three are often mixed up:

| Approach | Downstream observes | Upstream |
| --- | --- | --- |
| `expectComplete().verify()` | Requires onComplete | Source finished normally |
| `thenCancel().verify()` | Test actively cancels | Source typically receives cancel |
| `take(3).verifyComplete()` | Flux after take emits 3 elements then completes | take usually cancels upstream before upstream completes on its own |

Example:

~~~java
Flux<Long> infinite = Flux.interval(
    Duration.ofMillis(20)
);

StepVerifier.create(infinite.take(3))
    .expectNext(0L, 1L, 2L)
    .verifyComplete();
~~~

This is a valid test, yet **it proves completion of the pipeline with take(3)**, not that the `Flux.interval` source terminates on its own. If the goal is testing an infinite source and cleanup when downstream cancels, test the source directly:

~~~java
StepVerifier.create(infinite)
    .expectNext(0L, 1L, 2L)
    .thenCancel()
    .verify(Duration.ofSeconds(5));
~~~

When using `take(n)` on the client response, receiving N elements can trigger cancellation on HTTP receive. However, server-side cleanup happens asynchronously over the network; do not assert that a server flag is set **immediately** right after the client verifier returns unless you have proper synchronization/waiting.

## 11. Virtual time: without waiting for real timers

In service unit tests using `Flux.interval` or `delayElements`, use `StepVerifier.withVirtualTime(...)` when the goal is timing logic rather than HTTP/networking.

~~~java
StepVerifier.withVirtualTime(() ->
        Flux.interval(Duration.ofHours(1)).take(2)
    )
    .expectSubscription()
    .expectNoEvent(Duration.ofMinutes(59))
    .thenAwait(Duration.ofMinutes(1))
    .expectNext(0L)
    .thenAwait(Duration.ofHours(1))
    .expectNext(1L)
    .verifyComplete();
~~~

The example does not wait two real hours. The virtual scheduler is installed before `Flux.interval` is created because the publisher is constructed **inside the supplier**.

### 11.1. expectNoEvent versus thenAwait

- `expectNoEvent(duration)` advances time while asserting no onNext/onError/onComplete occurred during that interval.
- `thenAwait(duration)` advances time without asserting that no signals occurred.
- Subscription counts as an event. If you want to assert no onNext for an interval after subscribing, use `expectSubscription().expectNoEvent(...)`.

Example:

~~~java
StepVerifier.withVirtualTime(() ->
        Mono.delay(Duration.ofSeconds(5))
    )
    .expectSubscription()
    .expectNoEvent(Duration.ofSeconds(4))
    .thenAwait(Duration.ofSeconds(1))
    .expectNext(0L)
    .verifyComplete();
~~~

### 11.2. Do not mechanically apply virtual time to HTTP integration tests

`WebTestClient.bindToServer()` connects over a real network. Kernel sockets, network I/O, Netty event loops, and flushing are not fully controlled by Reactor's virtual scheduler. Therefore:

- Service/timer unit tests: use `withVirtualTime`.
- Streaming HTTP integration tests: use real-time `verify(Duration)` with reasonable timeouts, short intervals, and assertions that do not depend on exact milliseconds.
- If handshake/headers/server-side cancellation need testing, use WebTestClient or WebClient integration tests instead of calling only the service.

## 12. TestPublisher: controlling upstream and error timing

A real stream may receive data from a message broker, database change feed, or sensor. TestPublisher emits planned signals without needing real infrastructure.

~~~java
TestPublisher<Long> upstream = TestPublisher.create();

Flux<Notice> output =
    service.transform(upstream.flux());

StepVerifier.create(output)
    .then(() -> upstream.next(7L))
    .expectNext(new Notice(7L, "notice-7"))
    .then(() -> upstream.error(
        new IllegalStateException("broker down")
    ))
    .expectErrorMessage("broker down")
    .verify(Duration.ofSeconds(3));
~~~

`then(...)` matters because `TestPublisher.create()` is a hot source: emitting before StepVerifier subscribes can lose items.

To test cancellation:

~~~java
TestPublisher<Long> upstream = TestPublisher.create();

StepVerifier.create(
        service.transform(upstream.flux()).take(2)
    )
    .then(() -> upstream.next(10L, 11L))
    .expectNext(
        new Notice(10L, "notice-10"),
        new Notice(11L, "notice-11")
    )
    .verifyComplete();

upstream.assertCancelled();
~~~

This behavior proves `take(2)` emits completion downstream and then cancels the TestPublisher source.

**Do not use TestPublisher in production** as a message bus: it belongs to reactor-test and is built for testing. For production imperative-to-reactive bridges, look at Reactor `Sinks` or appropriate adapters.

## 13. Testing errors on streaming responses

An error occurring **before** the HTTP response is committed can cause WebFlux to choose an HTTP error status, depending on exception handling. However, if the endpoint has already sent several SSE events and flushed the response, the server cannot go back and change the status to HTTP 500 for an already-started response.

Example **service-layer** test:

~~~java
Flux<Notice> feed = Flux.concat(
    Flux.just(new Notice(0L, "notice-0")),
    Flux.error(new IllegalStateException("feed failed"))
);

StepVerifier.create(feed)
    .expectNext(new Notice(0L, "notice-0"))
    .expectErrorMatches(error ->
        error instanceof IllegalStateException
            && "feed failed".equals(error.getMessage())
    )
    .verify(Duration.ofSeconds(2));
~~~

This test ensures the service emits the first event and then errors. It **does not** assert that an HTTP SSE client will see an HTTP 500 after the first event. When a network response fails mid-stream, the client may observe a closed connection, decoder error, or reconnect depending on the client/proxy.

If the application wants to send a controlled "business error" as SSE, you can convert certain business errors into a `ServerSentEvent<...>` with `event("error")` and a safe body, then decide whether to complete or continue the stream. Never send stack traces or tokens in SSE data.

### 13.1. Testing fallback in a service

~~~java
Flux<Notice> recovered = feed
    .onErrorResume(error ->
        Flux.just(new Notice(-1L, "temporarily-unavailable"))
    );

StepVerifier.create(recovered)
    .expectNext(
        new Notice(0L, "notice-0"),
        new Notice(-1L, "temporarily-unavailable")
    )
    .verifyComplete();
~~~

This is a specific business policy; do not use `onErrorResume` to turn all production errors into fake successes. Unexpected errors must have logs, metrics, and clear contracts.

## 14. Cancellation and resource release

With infinite streams, **cancellation is a normal test outcome**, not a test failure.

Service example:

~~~java
AtomicBoolean cancelled = new AtomicBoolean();

Flux<Long> source = Flux.interval(
    Duration.ofMillis(50)
).doOnCancel(() -> cancelled.set(true));

StepVerifier.create(source)
    .expectNext(0L, 1L)
    .thenCancel()
    .verify(Duration.ofSeconds(2));

assertTrue(cancelled.get());
~~~

This is a unit test on an in-memory pipeline. It verifies that `cancel` reaches upstream.

### 14.1. Cleanup when using external sources

If a stream holds a broker subscription, database cursor, or async resource, tie the resource to the publisher's lifecycle:

~~~java
Flux<String> events = Flux.usingWhen(
    broker.openSubscription(channel),
    subscription -> subscription.messages(),
    subscription -> subscription.close(),
    (subscription, error) -> subscription.close(),
    subscription -> subscription.close()
);
~~~

`usingWhen` has separate cleanup handlers for complete, error, and cancel. Ensure the actual operation is returned as a reactive publisher and not subscribed to independently outside.

In HTTP integration tests, the client's `thenCancel()` requests cancellation of body consumption. To verify actual server-side cleanup, instrument the resource (counter/metrics, latch, or fake test broker with a signal) and wait for that signal instead of using `Thread.sleep` and immediately reading a boolean.

### 14.2. Response streams from brokers must be bounded

Do not create an unbounded `Flux` from a multi-tenant source without topic authorization, subscription limits, queue bounds, and lifetimes. Slow clients can hold connections open for a long time; proper cancellation returns resources to the pool.

## 15. Backpressure: request(n) and HTTP streaming

Reactive Streams has `request(n)`, yet HTTP/TCP and codecs introduce different buffering layers. If StepVerifier starts with demand 1, do not conclude TCP reads only one packet or the server produces only one element. Buffering, prefetch, and network flushing can make request counts differ across layers.

Unit test example:

~~~java
StepVerifier.create(Flux.range(1, 3), 0)
    .expectSubscription()
    .thenRequest(1)
    .expectNext(1)
    .thenRequest(2)
    .expectNext(2, 3)
    .verifyComplete();
~~~

When testing WebFlux SSE integration:

- Verify the semantics the client actually receives: order, data, cancellation.
- Do not assert exact upstream `request(n)` from an HTTP client unless that is a contract being verified with proper instrumentation.
- When using `Flux.interval`, remember it can emit `OverflowException` when downstream has no demand; do not write a demand=0 unit test with a real interval without designing expectations accordingly.
- Queue limits, max in-memory size, event size, and connection counts are operational requirements distinct from StepVerifier assertions.

## 16. Heartbeat and keepalive for SSE

Spring Framework recommends streaming responses like SSE/NDJSON send periodic data to detect disconnects sooner. When a business feed can stay silent for long stretches, an SSE comment-only heartbeat can be emitted:

~~~java
Flux<ServerSentEvent<String>> heartbeat =
    Flux.interval(Duration.ofSeconds(15))
        .map(i -> ServerSentEvent.<String>builder()
            .comment("keepalive")
            .build());
~~~

An SSE comment starts with a colon on the wire, not as a normal business event. Clients can use heartbeats to keep connections alive and avoid reverse-proxy idle timeouts.

Do not design a test stating "every received event must be a Notice" when the real stream has heartbeats or multiple event types exposed by the decoder. Separate business data tests from keepalive tests, or filter/inspect appropriately.

When a proxy/load balancer is involved:

- Verify idle/read timeouts exceed the heartbeat period.
- Evaluate proxy buffering; if the proxy buffers the response, clients will not receive events immediately.
- Monitor client disconnects/cancellations.
- Enforce TLS, authorization, and connection quotas.
- For browser EventSource, consider reconnect/backoff and `Last-Event-ID`.

## 17. Testing SSE for browser EventSource

On the browser side:

~~~javascript
const stream = new EventSource("/api/streams/sse");

stream.addEventListener("notice", event => {
    const notice = JSON.parse(event.data);
    console.log(notice.sequence, notice.message);
});

stream.onerror = error => {
    console.error("SSE connection problem", error);
};

// When the UI no longer needs the stream:
stream.close();
~~~

EventSource has built-in reconnection when the connection drops. This differs from StepVerifier: StepVerifier checks a single subscription in the test and does not simulate browser retry policies.

If resume needs testing:

1. Server stores event IDs and history long enough.
2. Client reconnects with `Last-Event-ID`.
3. Server returns the exact subsequent slice of events.
4. Tests must verify no missed/duplicate events beyond published semantics.

A server that merely maps `Flux.interval` to IDs `"0", "1", ...` per connection **does not automatically support replay**. Do not write tests requiring resume if the server has not implemented it.

## 18. Complete demo: Spring Boot WebFlux, Java 17+, JUnit 5

The project below exposes three endpoints:

- `GET /api/streams/finite` returns two Notices as a JSON array and completes.
- `GET /api/streams/sse` returns an infinite `ServerSentEvent<Notice>` stream emitting every 100 ms.
- `GET /api/streams/ndjson` returns an infinite NDJSON stream with the same notice data.

The unit tests use StepVerifier, virtual time, TestPublisher, and cancellation. The HTTP integration tests use WebTestClient + `FluxExchangeResult` + StepVerifier.

### 18.1. Project structure

~~~text
webflux-stream-test/
  settings.gradle
  build.gradle
  src/
    main/java/demo/streams/
      StreamTestApplication.java
      Notice.java
      NoticeStreamService.java
      NoticeStreamController.java
    test/java/demo/streams/
      NoticeStreamServiceTest.java
      NoticeStreamHttpTest.java
~~~

### 18.2. settings.gradle

~~~groovy
rootProject.name = 'webflux-stream-test'
~~~

### 18.3. build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.6'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
version = '1.0.0'

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
~~~

Spring Boot 3.5.6 manages compatible versions of Spring Framework, Reactor Core, and reactor-test. For this WebFlux application, do not add `spring-boot-starter-web` because when both Spring MVC and WebFlux starters are present, Boot usually favors MVC auto-configuration.

### 18.4. StreamTestApplication.java

~~~java
package demo.streams;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class StreamTestApplication {
    public static void main(String[] args) {
        SpringApplication.run(StreamTestApplication.class, args);
    }
}
~~~

### 18.5. Notice.java

~~~java
package demo.streams;

public record Notice(long sequence, String message) {
}
~~~

An immutable record has value equality. Therefore StepVerifier can compare `new Notice(0, "notice-0")` using `expectNext(...)`.

### 18.6. NoticeStreamService.java

~~~java
package demo.streams;

import java.time.Duration;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Flux;

@Service
public class NoticeStreamService {

    public Flux<Notice> finite() {
        return Flux.just(
            new Notice(1L, "ready"),
            new Notice(2L, "done")
        );
    }

    public Flux<Notice> live() {
        return Flux.interval(Duration.ofMillis(100))
            .map(sequence ->
                new Notice(sequence, "notice-" + sequence)
            );
    }

    public Flux<Notice> transform(Flux<Long> source) {
        return source.map(sequence ->
            new Notice(sequence, "notice-" + sequence)
        );
    }
}
~~~

`finite()` is a finite source. `live()` is a cold publisher per subscription: each subscriber starts its own timer, emitting sequence 0, 1, 2... and never completing unless canceled. `transform(...)` enables testing with a fake source driven by TestPublisher without real timers.

### 18.7. NoticeStreamController.java

~~~java
package demo.streams;

import java.time.Duration;
import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Flux;

@RestController
@RequestMapping("/api/streams")
public class NoticeStreamController {

    private final NoticeStreamService service;

    public NoticeStreamController(NoticeStreamService service) {
        this.service = service;
    }

    @GetMapping(
        path = "/finite",
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    public Flux<Notice> finite() {
        return service.finite();
    }

    @GetMapping(
        path = "/sse",
        produces = MediaType.TEXT_EVENT_STREAM_VALUE
    )
    public Flux<ServerSentEvent<Notice>> sse() {
        return service.live()
            .map(notice -> ServerSentEvent.<Notice>builder()
                .id(Long.toString(notice.sequence()))
                .event("notice")
                .retry(Duration.ofSeconds(3))
                .data(notice)
                .build());
    }

    @GetMapping(
        path = "/ndjson",
        produces = MediaType.APPLICATION_NDJSON_VALUE
    )
    public Flux<Notice> ndjson() {
        return service.live();
    }
}
~~~

`@RestController` uses HttpMessageWriter to write the response; it is not server-side view rendering. `produces` helps select the codec and format. The SSE endpoint includes id/event/retry/data fields. The NDJSON endpoint writes each Notice as one JSON object per line.

### 18.8. NoticeStreamServiceTest.java

~~~java
package demo.streams;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.time.Duration;
import java.util.concurrent.atomic.AtomicBoolean;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;
import reactor.test.publisher.TestPublisher;

class NoticeStreamServiceTest {

    private final NoticeStreamService service =
        new NoticeStreamService();

    @Test
    void finiteStreamCompletes() {
        StepVerifier.create(service.finite())
            .expectNext(
                new Notice(1L, "ready"),
                new Notice(2L, "done")
            )
            .verifyComplete();
    }

    @Test
    void liveStreamProducesValuesUnderVirtualTime() {
        StepVerifier.withVirtualTime(service::live)
            .expectSubscription()
            .expectNoEvent(Duration.ofMillis(99))
            .thenAwait(Duration.ofMillis(1))
            .expectNext(new Notice(0L, "notice-0"))
            .thenAwait(Duration.ofMillis(100))
            .expectNext(new Notice(1L, "notice-1"))
            .thenCancel()
            .verify(Duration.ofSeconds(2));
    }

    @Test
    void cancellationReachesUpstream() {
        AtomicBoolean cancelled = new AtomicBoolean();

        StepVerifier.withVirtualTime(() ->
                service.live()
                    .doOnCancel(() ->
                        cancelled.set(true))
            )
            .expectSubscription()
            .thenAwait(Duration.ofMillis(100))
            .expectNext(new Notice(0L, "notice-0"))
            .thenCancel()
            .verify(Duration.ofSeconds(2));

        assertTrue(cancelled.get());
    }

    @Test
    void takeThreeCompletesButCancelsItsSource() {
        TestPublisher<Long> source = TestPublisher.create();

        StepVerifier.create(
                service.transform(source.flux()).take(3)
            )
            .then(() -> source.next(10L, 11L, 12L))
            .expectNext(
                new Notice(10L, "notice-10"),
                new Notice(11L, "notice-11"),
                new Notice(12L, "notice-12")
            )
            .verifyComplete();

        source.assertCancelled();
    }

    @Test
    void controlledSourceErrorIsPropagated() {
        TestPublisher<Long> source = TestPublisher.create();

        StepVerifier.create(
                service.transform(source.flux())
            )
            .then(() -> source.next(7L))
            .expectNext(new Notice(7L, "notice-7"))
            .then(() -> source.error(
                new IllegalStateException("feed failed")
            ))
            .expectErrorMessage("feed failed")
            .verify(Duration.ofSeconds(2));
    }

    @Test
    void boundedDemandDoesNotRequireInfiniteCompletion() {
        StepVerifier.create(
                Flux.range(1, 3), 0
            )
            .expectSubscription()
            .thenRequest(1)
            .expectNext(1)
            .thenRequest(2)
            .expectNext(2, 3)
            .verifyComplete();
    }

    @Test
    void neverSourceCanBeCancelledExplicitly() {
        StepVerifier.create(Flux.<Notice>never())
            .expectSubscription()
            .thenCancel()
            .verify(Duration.ofSeconds(2));
    }
}
~~~

Each test has a distinct meaning:

- `finiteStreamCompletes` verifies real onComplete.
- `liveStreamProducesValuesUnderVirtualTime` verifies two ticks without waiting 200 real ms.
- `cancellationReachesUpstream` verifies doOnCancel in the same pipeline.
- `takeThreeCompletesButCancelsItsSource` distinguishes downstream completion from upstream cancellation.
- `controlledSourceErrorIsPropagated` verifies one event before an error.
- `boundedDemandDoesNotRequireInfiniteCompletion` tests initial request 0 and partial demand requests.
- `neverSourceCanBeCancelledExplicitly` shows a completely silent source can still be tested without waiting for completion.

### 18.9. NoticeStreamHttpTest.java

~~~java
package demo.streams;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

import java.time.Duration;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.test.web.reactive.server.FluxExchangeResult;
import org.springframework.test.web.reactive.server.WebTestClient;
import reactor.test.StepVerifier;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
@AutoConfigureWebTestClient
class NoticeStreamHttpTest {

    @Autowired
    WebTestClient client;

    @Test
    void finiteResponseCanBeAssertedAsJsonArray() {
        client.get()
            .uri("/api/streams/finite")
            .accept(MediaType.APPLICATION_JSON)
            .exchange()
            .expectStatus().isOk()
            .expectHeader()
            .contentTypeCompatibleWith(
                MediaType.APPLICATION_JSON)
            .expectBodyList(Notice.class)
            .hasSize(2)
            .contains(
                new Notice(1L, "ready"),
                new Notice(2L, "done")
            );
    }

    @Test
    void sseEventsAreDecodedAndCancelled() {
        FluxExchangeResult<ServerSentEvent<Notice>> response =
            client.get()
                .uri("/api/streams/sse")
                .accept(MediaType.TEXT_EVENT_STREAM)
                .exchange()
                .expectStatus().isOk()
                .expectHeader()
                .contentTypeCompatibleWith(
                    MediaType.TEXT_EVENT_STREAM)
                .returnResult(
                    new ParameterizedTypeReference<
                        ServerSentEvent<Notice>>() {}
                );

        StepVerifier.create(response.getResponseBody())
            .assertNext(event -> {
                assertEquals("0", event.id());
                assertEquals("notice", event.event());
                assertEquals(Duration.ofSeconds(3), event.retry());
                assertNotNull(event.data());
                assertEquals(
                    new Notice(0L, "notice-0"),
                    event.data()
                );
            })
            .assertNext(event -> {
                assertEquals("1", event.id());
                assertEquals(
                    new Notice(1L, "notice-1"),
                    event.data()
                );
            })
            .thenCancel()
            .verify(Duration.ofSeconds(8));
    }

    @Test
    void ndjsonResponseCanBeReadIncrementally() {
        FluxExchangeResult<Notice> result =
            client.get()
                .uri("/api/streams/ndjson")
                .accept(MediaType.APPLICATION_NDJSON)
                .exchange()
                .expectStatus().isOk()
                .expectHeader()
                .contentTypeCompatibleWith(
                    MediaType.APPLICATION_NDJSON)
                .returnResult(Notice.class);

        StepVerifier.create(result.getResponseBody())
            .expectNext(
                new Notice(0L, "notice-0"),
                new Notice(1L, "notice-1")
            )
            .thenCancel()
            .verify(Duration.ofSeconds(8));
    }
}
~~~

These are integration tests with a real HTTP server running on a random port. Unlike the virtual-time unit tests, these use real 100 ms timers. Tests are bounded at 8 seconds to avoid hanging if the server emits no events. `thenCancel()` ends body consumption and allows network resources to be released.

**There is no assertion that the source must complete**, because these two endpoints are designed to be infinite. `expectBodyList(...)` is used only for `/finite`.

### 18.10. Running and manual testing

Requires Java 17 and Gradle. In the project directory:

~~~bash
gradle test
~~~

Run the application:

~~~bash
gradle bootRun
~~~

Fetch finite JSON:

~~~bash
curl -i http://localhost:8080/api/streams/finite
~~~

Expected response body:

~~~json
[
  {"sequence":1,"message":"ready"},
  {"sequence":2,"message":"done"}
]
~~~

Fetch SSE with unbuffered streaming output in curl:

~~~bash
curl -N -H "Accept: text/event-stream" \
  http://localhost:8080/api/streams/sse
~~~

The beginning of the SSE stream looks like:

~~~text
id:0
event:notice
retry:3000
data:{"sequence":0,"message":"notice-0"}

id:1
event:notice
retry:3000
data:{"sequence":1,"message":"notice-1"}

~~~

Field formatting and whitespace on the wire depend on the encoder/codec, yet the semantics of `id`, `event`, `retry`, and `data` must be preserved. Use Ctrl+C to cancel the client stream; do not wait for the server to complete on its own.

Fetch NDJSON:

~~~bash
curl -N -H "Accept: application/x-ndjson" \
  http://localhost:8080/api/streams/ndjson
~~~

First lines:

~~~text
{"sequence":0,"message":"notice-0"}
{"sequence":1,"message":"notice-1"}
{"sequence":2,"message":"notice-2"}
~~~

There is no fixed Gradle stdout, as version, cache, and runtimes vary by environment. For tests, the important result is that the test task PASSES and the assertions in the test classes hold.

## 19. Testing approach when upstream is a repository or broker

A production application may stream notifications from Redis pub/sub, Kafka, or a database change feed. Unit tests do not need a real broker when the goal is transform/filter/order/error handling.

Example interface:

~~~java
interface LiveFeed {
    Flux<Notice> subscribe(String userId);
}
~~~

Service:

~~~java
final class FilteredFeed {
    private final LiveFeed feed;

    FilteredFeed(LiveFeed feed) {
        this.feed = feed;
    }

    Flux<Notice> forUser(String userId) {
        return feed.subscribe(userId)
            .filter(n -> n.sequence() >= 10);
    }
}
~~~

Test:

~~~java
TestPublisher<Notice> source = TestPublisher.create();
LiveFeed fake = userId -> source.flux();

FilteredFeed filtered = new FilteredFeed(fake);

StepVerifier.create(filtered.forUser("u-1"))
    .then(() -> source.next(
        new Notice(5L, "skip"),
        new Notice(10L, "keep"),
        new Notice(11L, "keep-2")
    ))
    .expectNext(
        new Notice(10L, "keep"),
        new Notice(11L, "keep-2")
    )
    .thenCancel()
    .verify(Duration.ofSeconds(2));

source.assertCancelled();
~~~

This snippet tests service logic; there is no HTTP. When codecs/headers/reconnect/authorization need verification, add integration tests.

Do not fake complex Kafka/Redis behavior with a TestPublisher and conclude the whole production system will behave identically. Backpressure, reconnect, partitions, consumer groups, and broker acknowledgements require dedicated integration-layer tests.

## 20. Common mistakes causing SSE/Flux tests to hang or flake

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Using verifyComplete on an infinite stream | Waits for non-existent completion | thenCancel after enough data |
| Using expectBodyList for infinite SSE | Waits for entire body | returnResult + StepVerifier |
| Omitting verify timeout | Suite may hang | verify(Duration) |
| Expecting timer to emit immediately at t=0 | Standard Flux.interval starts after first period | Expect at the right time or use virtual time |
| Comparing timestamps to the millisecond over a network | Flaky on slow CI | Assert order/content with sufficient timeout |
| Creating interval before withVirtualTime | Virtual scheduler may not control it | Create publisher inside the supplier |
| Using expectNoEvent as the first step | Subscription counts as an event | expectSubscription first |
| Emitting on hot TestPublisher before verify | Data is lost | Emit via then(...) |
| Confusing take(3) completion with upstream completion | Tests wrong lifecycle | Assert source cancellation |
| Asserting server cleanup flag right after client cancel | Race due to async networking | Use signal/latch/await condition |
| Expecting mid-stream SSE error to change HTTP status | Response already committed | Test service error and transport/client separately |
| Reading SSE via expectBody(String.class) | Infinite body never finishes | returnResult and take a few events |
| Confusing NDJSON with a JSON array | Different decoders/framing | Choose matching produces/Accept and decoder |
| Ignoring media type | Unsure which codec is used | Assert appropriate Content-Type |
| Using ServerSentEvent.class then casting data | Loses generic type, data may become Map | ParameterizedTypeReference |
| Expecting Last-Event-ID to provide replay automatically | ID exists but server lacks history store | Design explicit store/replay |
| Using blocking Thread.sleep in tests | Slow and non-deterministic tests | Virtual time or controlled signals |
| Using overly tight intervals | Causes overflow/buffer issues | Reasonable interval, limits/backpressure |
| Not canceling WebTestClient result | Connections/resources may stay open | Intentional thenCancel or take(n) |
| Streams without authorization | Leaks other users' events | Authorize per subscription |
| Logging sensitive payloads | Leaks user data | Log metadata in a controlled manner |
| Proxy buffering SSE | Clients do not receive incrementally | Check proxy/content-type/flush config |

## 21. QA checklist for streaming endpoints

Before marking tests complete, check:

1. Does the endpoint use the right `produces` and Content-Type?
2. For SSE, do events have id/event/data/retry per contract?
3. For NDJSON, does each item decode into an independent object?
4. Are finite and infinite streams distinguished in terminal expectations?
5. Do HTTP tests use WebTestClient.returnResult to verify streaming?
6. Is thenCancel used when the source is not expected to complete on its own?
7. Is there a verify timeout so tests never hang?
8. For intervals, do unit tests use virtual time and integration tests use real time appropriately?
9. Is cancellation propagated to upstream cleanup verified using fakes/signals?
10. Are mid-stream errors tested at the service layer?
11. Are fallbacks/empty cases tested where business rules require?
12. Are generic codec types handled for ServerSentEvent?
13. Are exact millisecond assertions over real networks avoided?
14. Are event counts and connections bounded in production?
15. Are reconnect, heartbeat, and replay tested if clients depend on them?

## 22. Review questions with answers

**Question 1. Why is using verifyComplete for an infinite Flux.interval wrong?**

Because the publisher never emits onComplete on its own; the test will wait forever or fail by timeout. Use thenCancel after checking enough elements.

**Question 2. Does StepVerifier.thenCancel mean upstream completed?**

No. Downstream actively cancels the subscription; this is not an onComplete signal.

**Question 3. How does take(3) differ from direct thenCancel?**

take(3) builds a pipeline that completes downstream after three elements and usually cancels upstream; thenCancel is an active action by the test subscriber.

**Question 4. Why is WebTestClient.expectBodyList unsuitable for infinite SSE?**

Because it tries to decode the entire response into a collection, whereas the body has no endpoint.

**Question 5. Which WebTestClient API retrieves a streaming Flux?**

`returnResult(...)` creates a `FluxExchangeResult<T>` and `getResponseBody()` returns `Flux<T>`.

**Question 6. How does SSE differ from NDJSON?**

SSE is an event-stream format with id/event/retry/data fields and event delimiters; NDJSON is newline-separated JSON objects.

**Question 7. Why use ParameterizedTypeReference<ServerSentEvent<Notice>>?**

To preserve generic type information so the decoder creates ServerSentEvent and Notice rather than leaving data as an untyped Map/Object.

**Question 8. When is withVirtualTime used?**

When testing logic driven by Reactor schedulers such as interval/delay/timeout without waiting in real time.

**Question 9. Why must Flux.interval be created inside withVirtualTime's supplier?**

Because the virtual scheduler must be installed before time-based operators are constructed; creating it beforehand may bind to a real scheduler.

**Question 10. Does expectNoEvent treat subscription as an event?**

Yes. That is why we usually write expectSubscription() followed by expectNoEvent(duration).

**Question 11. Why shouldn't an HTTP cancellation test assert a server flag immediately after verify?**

Cancellation travels over the network and the server processes it asynchronously; an explicit waiting/signal mechanism is needed to assert server cleanup.

**Question 12. Can HTTP 500 be returned after an SSE response has already sent an event?**

The status of an already-committed response cannot be changed. Service errors and client transport/contracts must be tested separately.

**Question 13. Does browser EventSource automatically replay events thanks to id?**

It can send Last-Event-ID on reconnect, yet the server must implement history storage/replay; generating IDs alone does not prevent missed events.

**Question 14. What should a complete WebFlux streaming test verify?**

HTTP status/content-type, decoded events and order, termination/cancellation, plus resource cleanup or reconnect if part of the contract.

## 23. Summary

- A `Flux` can be finite, empty, errored, or infinite; the StepVerifier terminal expectation must match the exact contract.
- SSE is one-way HTTP `text/event-stream`, optionally carrying id/event/retry/data metadata.
- NDJSON is line-delimited JSON objects, also used for HTTP streaming.
- For WebTestClient streaming, assert status/headers first, call returnResult, then pass getResponseBody() into StepVerifier.
- Infinite streams: check several items then thenCancel; do not wait for verifyComplete.
- Virtual time is for time-based operators in unit tests; HTTP integration still involves real network timing.
- TestPublisher controls upstream; StepVerifier verifies downstream.
- Cancellation can clean up resources, though integration tests must account for network latency.
- Do not confuse Flux.take(n) completing with upstream completing on its own.
- SSE event IDs do not automatically become durable replay.
- Set timeouts for tests and bound memory/connections/producers in production.

## 24. Official documentation

1. [Spring Framework Reference — WebTestClient, Streaming Responses](https://docs.spring.io/spring-framework/reference/6.2/testing/webtestclient.html): status/header/returnResult/getResponseBody/StepVerifier thenCancel flow.
2. [Project Reactor — Testing Reference](https://projectreactor.io/docs/core/release/reference/testing.html): StepVerifier, virtual time, TestPublisher, and PublisherProbe.
3. [Reactor StepVerifier Javadoc](https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifier.html): verify, thenCancel, withVirtualTime, and method contracts.
4. [Spring Framework — ServerSentEvent Javadoc](https://docs.spring.io/spring-framework/docs/6.2.5/javadoc-api/org/springframework/http/codec/ServerSentEvent.html): data, id, event, retry, comment, and builder.
5. [Spring Framework — Reactive Core, Streaming](https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html): SSE/NDJSON streaming, periodic data, heartbeats, and memory limits.
6. [Spring Framework — @ResponseBody](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/responsebody.html): reactive return types serialized into HTTP bodies.
7. [Spring Framework — Return Values](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/return-types.html): Flux<ServerSentEvent> and reactive return types.
8. [WHATWG HTML Living Standard — Server-Sent Events](https://html.spec.whatwg.org/multipage/server-sent-events.html): EventSource, event stream format, ID, reconnection, and retry.
9. [Project Reactor — TestPublisher Javadoc](https://projectreactor.io/docs/test/release/api/reactor/test/publisher/TestPublisher.html): controlled sources and assertions.
10. [Spring Boot — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): SpringBootTest, WebTestClient, and test web environments.
