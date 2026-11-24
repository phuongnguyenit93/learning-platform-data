# Setting Wait Bounds for Non-Terminating Streams

In WebFlux, an endpoint can return a `Flux` that continuously emits data without ever sending a completion signal. Endpoints such as Server-Sent Events (SSE), live notifications, log streams, or status feeds are often designed this way: the connection stays open so the server can send new items whenever data becomes available.

This characteristic creates an important difference when testing. With a regular response, a test can read the entire body, wait for the publisher to complete, and then compare results. With a non-terminating stream, waiting for the body to complete will never finish without a timeout or a cancellation action. Tests need to specify clearly whether they want to wait for the response to begin, wait for a specific event, assert that no events occur for a duration, or explicitly terminate the subscription.

`WebTestClient` combined with Reactor Test (`StepVerifier`) provides ways to control these wait boundaries. You can also configure a client timeout and a test-level timeout to prevent one failure from hanging the entire test suite.

## 1. Why do non-terminating streams need a separate testing approach?

A reactive publisher can emit elements and then complete:

```java
Flux<String> finite = Flux.just("first", "second", "third");
```

After the last element, the publisher sends `onComplete`. Body-collecting APIs such as `expectBodyList(...)` can read until completion and return the result.

By contrast, the following publisher does not send `onComplete` or `onError`:

```java
Flux<String> endless = Flux.interval(Duration.ofSeconds(1))
        .map(index -> "event-" + index);
```

Every second a new element arrives, yet the publisher never finishes on its own. Another source may emit no elements at all:

```java
Flux<String> silent = Flux.never();
```

`Flux.never()` emits no `onNext`, `onError`, or `onComplete`. This is a useful source for testing timeouts, yet if a test waits for it to complete, the test will wait forever.

For streaming responses, distinguish between stages:

```text
Request sent
      |
      v
Response status and headers arrive
      |
      v
Body publisher begins being read
      |
      +---- onNext: first item
      |
      +---- onNext: next item
      |
      +---- onNext: heartbeat / new data
      |
      +---- ... stream continues ...
      |
      +---- onComplete or onError (may never occur)
```

A test may need to verify the status and headers as soon as the response opens, then read only a few elements and cancel. It does not need to wait for the stream to finish to prove those behaviors.

## 2. Using `returnResult` to obtain the stream

For finite bodies, matchers such as `expectBody(...)` and `expectBodyList(...)` are convenient because they wait until the body finishes reading. For non-terminating streams, use `returnResult(...)` to obtain the response body `Flux` and control the subscription with Reactor Test.

Example controller emitting Server-Sent Events:

```java
import java.time.Duration;

import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Flux;

@RestController
class EventController {

    @GetMapping(value = "/events", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    Flux<ServerSentEvent<String>> events() {
        return Flux.interval(Duration.ofSeconds(1))
                .map(index -> ServerSentEvent.<String>builder()
                        .id(Long.toString(index))
                        .event("tick")
                        .data("event-" + index)
                        .build());
    }
}
```

The test reads only the first two events and then cancels the subscription:

```java
import static org.assertj.core.api.Assertions.assertThat;

import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.test.web.reactive.server.FluxExchangeResult;
import reactor.test.StepVerifier;

class EventControllerTest {

    @Test
    void readsSomeEventsAndCancelsTheInfiniteStream() {
        FluxExchangeResult<ServerSentEvent<String>> result = webTestClient.get()
                .uri("/events")
                .accept(MediaType.TEXT_EVENT_STREAM)
                .exchange()
                .expectStatus().isOk()
                .expectHeader().contentTypeCompatibleWith(MediaType.TEXT_EVENT_STREAM)
                .returnResult(new ParameterizedTypeReference<ServerSentEvent<String>>() {});

        StepVerifier.create(result.getResponseBody())
                .assertNext(event -> {
                    assertThat(event.event()).isEqualTo("tick");
                    assertThat(event.data()).isEqualTo("event-0");
                })
                .assertNext(event -> assertThat(event.data()).isEqualTo("event-1"))
                .thenCancel()
                .verify(Duration.ofSeconds(4));
    }
}
```

In the example, `webTestClient` is created from WebFlux configuration or injected by Spring Boot test. `returnResult(...)` returns a `FluxExchangeResult`, allowing the body to be retrieved as `Flux<ServerSentEvent<String>>`. `StepVerifier` subscribes to the stream, verifies two items, and calls `thenCancel()` to end the subscription.

`verify(Duration.ofSeconds(4))` bounds the total verification time. If an event does not arrive in time, verification fails instead of hanging forever. This duration must accommodate the emission schedule and CI environment latency; avoid setting it too close to the emission period.

## 3. Distinguishing timeout types

No single timeout fits every phase. A streaming test often has several independent bounds:

| Bound type | Scope | Purpose |
|---|---|---|
| Client response timeout | Waiting for the server response during exchange | Detects when the server fails to respond or responds too slowly. |
| `StepVerifier.verify(Duration)` | Entire publisher verification process | Limits how long the test waits for expected reactive signals. |
| `expectNoEvent(Duration)` | An interval during the subscription | Asserts the stream emits no further signals during that interval. |
| Reactor `timeout(...)` | Publisher inside the application | Defines actual business or stream timeout behavior. |
| JUnit `@Timeout` | Entire test method | Last line of defense if the test gets stuck at any step. |

These bounds do not replace one another. For instance, the server may send status and headers promptly, and then the stream stops emitting events. The client response timeout might not catch silence in the body; `StepVerifier` is what directly bounds waiting for events.

### Configuring timeout on WebTestClient

When building the client, you can configure a response timeout:

```java
WebTestClient client = WebTestClient.bindToApplicationContext(applicationContext)
        .configureClient()
        .responseTimeout(Duration.ofSeconds(5))
        .build();
```

For a client connecting to a real server, the same configuration can be applied after `bindToServer()`:

```java
WebTestClient client = WebTestClient.bindToServer()
        .baseUrl("http://localhost:8080")
        .responseTimeout(Duration.ofSeconds(5))
        .build();
```

Response timeout bounds the client-side wait for the response. With streaming responses, status and headers can arrive early while the body continues streaming long-term. Therefore, do not rely on response timeout as the sole way to bound reading a non-terminating stream; bound the body subscription with `StepVerifier`.

### Bounding total verification time

Reactor Test allows setting a timeout directly on the verify call:

```java
StepVerifier.create(responseBody)
        .expectNext("ready")
        .thenCancel()
        .verify(Duration.ofSeconds(3));
```

This is the overall timeout for verification. If the stream does not emit `ready`, the test fails when time expires. If `ready` arrives, the verifier cancels the subscription and finishes early.

Prefer per-test timeouts over setting `StepVerifier.setDefaultTimeout(...)` globally. Global default configuration can affect other tests, especially during parallel execution, and obscure why a test is slow.

## 4. Asserting a stream stays silent for an interval

Sometimes the requirement is not waiting for the next event, but proving the server emits no events during a period. For example, an endpoint only emits data upon changes and must not continuously send empty notifications.

`expectNoEvent(Duration)` checks that no signal arrives during the specified interval:

```java
StepVerifier.create(responseBody)
        .expectSubscription()
        .expectNoEvent(Duration.ofMillis(300))
        .thenCancel()
        .verify(Duration.ofSeconds(2));
```

You must call `expectSubscription()` before `expectNoEvent(...)`, because the initial subscription signal itself counts as an event during verification. Otherwise, the verifier can fail right at the first step.

You can combine checking an initial event with asserting a silent interval afterward:

```java
StepVerifier.create(responseBody)
        .expectSubscription()
        .expectNextMatches(event -> "connected".equals(event))
        .expectNoEvent(Duration.ofMillis(500))
        .thenCancel()
        .verify(Duration.ofSeconds(2));
```

This is a real-time measurement. The silent interval must be larger than normal latency yet short enough not to slow tests unnecessarily. Do not use a few-millisecond window to conclude that a stream emits no data if the scheduler or CI can experience delays.

## 5. Application timeouts with Reactor `timeout`

`StepVerifier.verify(Duration)` only limits how long the test waits. It does not alter publisher behavior in the application. If business requirements dictate that a stream must emit data within a certain window, or switch to a fallback when no data arrives, configure a timeout in the reactive pipeline.

For example, `Flux.timeout(Duration)` emits a `TimeoutException` if the source fails to emit an element within the allowed interval:

```java
Flux<String> guarded = source.timeout(Duration.ofSeconds(10));
```

With `Flux`, the timeout interval applies while waiting for the first element and resets after each emitted element. Hence it is an idle timeout between events, not a limit on the stream's total lifetime. A stream sending regular heartbeats can run indefinitely without timing out.

To switch to a fallback stream on timeout:

```java
Flux<String> guarded = source.timeout(
        Duration.ofSeconds(10),
        Flux.just("no-data-fallback"));
```

To handle timeout errors according to business logic:

```java
Flux<String> guarded = source
        .timeout(Duration.ofSeconds(10))
        .onErrorResume(TimeoutException.class,
                error -> Flux.just("stream-timeout"));
```

Tests must distinguish between the two outcomes: an application timeout alters the response stream; a `StepVerifier` timeout merely ends the test if expected signals do not arrive. Do not add `timeout(...)` to production code solely to keep tests from hanging.

### Limiting total stream duration

If the requirement is that a stream may exist for at most a given duration, use a total-duration operator such as `take(Duration)`:

```java
Flux<String> finiteWindow = source.take(Duration.ofMinutes(5));
```

Unlike `timeout(Duration)`, `take(Duration)` completes after the elapsed duration measured from subscription start, even when the source keeps emitting events continuously. Choose the operator matching the requirement: idle timeout to detect missing data, or lifetime limit to close the stream after a fixed duration.

## 6. Using virtual time for time-based publishers

For publishers using schedulers that support virtual time, Reactor Test can run virtual time to test timeouts or intervals without waiting in real time. This makes tests faster and more deterministic when logic depends only on Reactor time.

Example publisher emitting two values one second apart and then completing:

```java
StepVerifier.withVirtualTime(() -> Flux.interval(Duration.ofSeconds(1)).take(2))
        .expectSubscription()
        .thenAwait(Duration.ofSeconds(2))
        .expectNext(0L, 1L)
        .verifyComplete();
```

`withVirtualTime` accepts a `Supplier` so the publisher is created after the virtual scheduler is installed. If `Flux.interval(...)` is created beforehand and passed into the verifier, the publisher may already hold the real scheduler and will not be controlled by virtual time.

Virtual time fits unit tests for publishers or reactive services. Do not assume it automatically controls the clocks of Netty, sockets, HTTP clients, or every component in a `WebTestClient` exchange. For tests traversing real transport, use real timeouts with sufficiently generous bounds.

## 7. Verifying cancellation when the test ends

With long-lived streams, cancelling the subscription is a key part of the resource contract. When a client is no longer interested in data, cancellation should propagate back to the publisher to release listeners, timers, connections, or message broker subscriptions.

You can attach `doOnCancel` to the data source to observe cancellation in tests:

```java
AtomicBoolean cancelled = new AtomicBoolean(false);

Flux<String> events = Flux.<String>never()
        .doOnCancel(() -> cancelled.set(true));

StepVerifier.create(events)
        .thenCancel()
        .verify(Duration.ofSeconds(1));

assertThat(cancelled).isTrue();
```

This is a unit test for the publisher. With WebTestClient, you can apply the same idea to the source returned by the controller and check cancellation after the verifier cancels the body stream:

```java
StepVerifier.create(result.getResponseBody())
        .expectNextCount(1)
        .thenCancel()
        .verify(Duration.ofSeconds(2));

assertThat(sourceCancelled.get()).isTrue();
```

This integration example assumes the controller uses a publisher with `doOnCancel` updating `sourceCancelled`. Make sure you monitor the right upstream source; if operators buffer or prefetch, the observed timing of cancellation may differ slightly. Do not merely verify that the test finishes while ignoring whether upstream releases resources when that is an important requirement.

## 8. Protecting the entire test with a JUnit timeout

A `StepVerifier` timeout protects reading the publisher. However, a test can also get stuck before `FluxExchangeResult` is created, for instance if the server never sends response headers or test configuration is broken. You can add a timeout at the test method level:

```java
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;

class EventControllerTest {

    @Test
    @Timeout(value = 8, unit = TimeUnit.SECONDS)
    void verifiesStreamingResponseWithinBoundedTime() {
        // Execute the request, obtain the response stream, and use StepVerifier.
    }
}
```

A JUnit timeout is an overall safety net. It does not replace assertions on events, does not explain how long a stream stayed silent, and is not an application timeout policy. Put timeouts at the appropriate operational levels, then use JUnit to cap overall test duration.

## 9. Common mistakes when testing non-terminating streams

### Using `expectBodyList` for an infinite stream

`expectBodyList(...)` must read the body until completion. If the publisher never sends `onComplete`, the test keeps waiting. Use `returnResult(...)` and `StepVerifier` to inspect part of the stream and then cancel.

### Calling `verify()` without a time bound

`StepVerifier.verify()` can wait forever if expected signals never arrive. For tests that could hang, use `verify(Duration)` or a controlled timeout configuration. Do not rely on a global default timeout without understanding its scope of impact.

### Confusing response timeout with body idle timeout

A server can send status and headers immediately and then stop emitting the body. In that case the exchange already succeeded while the body subscription keeps waiting. Use `StepVerifier` to bound reading time or assert no-event intervals.

### Using `Thread.sleep` to wait for events

`Thread.sleep` only pauses the test thread; it does not prove events were emitted or received by the subscription. Use `StepVerifier` to synchronize on reactive signals. For time-based logic, consider virtual time.

### Cancelling the subscription too early

If `thenCancel()` is called right after subscription, the test may finish before the first event arrives. Place `expectNext`, `assertNext`, or `expectNextCount` before `thenCancel()` to specify the data to observe.

### Using virtual time for real transport

Reactor's virtual scheduler does not fast-forward time inside Netty or the operating system. Use virtual time for publishers with controllable schedulers; use real timeouts for HTTP integration tests.

### Setting timeouts too short

Timeouts of just a few milliseconds can fail randomly under high CI load or scheduler delays. Set bounds based on event emission intervals, startup time, and acceptable latency. Keep timeouts short enough to catch hangs yet wide enough for real environments.

### Failing to verify cancellation

A test can finish while the source still holds resources if cancellation does not propagate properly upstream. For long-open streams, verify `doOnCancel`, cleanup, or subscription release when the client cancels.

## 10. Choosing a timeout strategy by goal

| Testing goal | Approach |
|---|---|
| Server fails to return status/headers | Configure `WebTestClient.responseTimeout(...)` and an overall test timeout. |
| Stream emits a few events then continues forever | `returnResult(...)`, `StepVerifier.expectNext(...)`, `thenCancel()`, `verify(Duration)`. |
| Stream must stay silent for a defined interval | `expectSubscription()`, `expectNoEvent(Duration)`, then `thenCancel()`. |
| Publisher must emit events within a bound | `expectNext(...)` with `verify(Duration)` to cap verification time. |
| Application must switch to fallback when no data arrives | Reactor `timeout(Duration, fallback)` and assertions on the fallback. |
| Stream must close itself after a total duration | `take(Duration)` and verify completion. |
| Test timers/intervals without real waiting | `StepVerifier.withVirtualTime(...)` with publisher created inside the supplier. |
| Ensure resources are freed when client stops reading | `thenCancel()` and verify upstream cleanup/cancellation. |

## 11. Checklist for streaming tests

- [ ] Identify whether the endpoint returns a finite body or a potentially non-terminating stream.
- [ ] Verify status and headers before reading the body.
- [ ] Use `returnResult(...)` for streaming bodies instead of waiting for the entire body to complete.
- [ ] Use `StepVerifier` to check the exact number of events needed.
- [ ] Call `thenCancel()` when the test does not need to read the rest of the stream.
- [ ] Set `verify(Duration)` to bound how long the test waits for signals.
- [ ] Use `expectNoEvent(Duration)` only when you genuinely need to assert a silent interval.
- [ ] Configure response timeout for the exchange phase when needed.
- [ ] Use Reactor `timeout(...)` or `take(...)` only when that is the application behavior under test.
- [ ] Use virtual time only for schedulers/publishers controllable by the virtual scheduler.
- [ ] Set JUnit `@Timeout` as an overall cap for tests at risk of hanging.
- [ ] Verify cancellation and cleanup if the stream manages long-lived resources.

With non-terminating streams, the test's goal is usually to observe a slice of data within a bounded time and then explicitly cancel the subscription. `WebTestClient.returnResult(...)` provides the body publisher, `StepVerifier` verifies the required signals, and `verify(Duration)` prevents the test from waiting indefinitely. Timeouts on the client, publisher, and test runner should each be applied at their proper scope to both catch bugs and preserve the semantics of a long-lived streaming response.
