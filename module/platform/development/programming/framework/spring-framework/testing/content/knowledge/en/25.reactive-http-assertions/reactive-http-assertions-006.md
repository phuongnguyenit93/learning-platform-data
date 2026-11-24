# FluxExchangeResult and Streaming Data

In Spring WebFlux, a controller can return `Flux<T>` to emit multiple elements over time. With streaming responses, tests need to inspect each element as it is emitted, and may need to verify ordering, timing, item count, and stream completion or cancellation. `FluxExchangeResult<T>` combines HTTP response metadata with a `Flux<T>` containing the decoded body.

When using `WebTestClient`, you can obtain `FluxExchangeResult` from `ResponseSpec.returnResult(...)`, then use Reactor Test `StepVerifier` to assert the elements. This approach fits Server-Sent Events (SSE), NDJSON, and responses whose body is transmitted as a stream.

## 1. Why is FluxExchangeResult needed?

For regular responses, tests usually collect the entire body before verifying:

```java
client.get()
        .uri("/api/orders")
        .exchange()
        .expectStatus().isOk()
        .expectBodyList(OrderResponse.class)
        .hasSize(2);
```

This works for finite responses where the client can read the entire body before asserting. However, for long or infinite streams, waiting for the body to finish is unsuitable. An endpoint streaming stock quotes, logs, or notifications may keep emitting data until the client closes the connection.

`FluxExchangeResult<T>` lets tests access the body as a `Flux<T>` once response headers are ready. The test can request a number of items, inspect them, and then verify stream completion or explicitly cancel the subscription.

Basic flow:

```text
WebTestClient request
        |
        v
     exchange()
        |
        v
HTTP status + headers
        |
        v
returnResult(BodyType.class)
        |
        v
FluxExchangeResult<T>
        |
        +---- response metadata
        |
        +---- getResponseBody(): Flux<T>
                          |
                          v
                    StepVerifier
```

## 2. What does FluxExchangeResult contain?

`FluxExchangeResult<T>` resides in the `org.springframework.test.web.reactive.server` package. It is a specialization of `ExchangeResult` dedicated to reactive stream response bodies.

The most commonly used part is:

```java
Flux<T> responseBody = result.getResponseBody();
```

`getResponseBody()` returns a publisher containing elements decoded into type `T`. HTTP information such as status, headers, cookies, and request/response metadata can still be accessed from `ExchangeResult`, which `FluxExchangeResult` extends.

Example retrieving the result:

```java
FluxExchangeResult<StockUpdate> result = client.get()
        .uri("/stocks/stream")
        .accept(MediaType.TEXT_EVENT_STREAM)
        .exchange()
        .expectStatus().isOk()
        .expectHeader().contentTypeCompatibleWith(MediaType.TEXT_EVENT_STREAM)
        .returnResult(StockUpdate.class);
```

Status and header assertions run before retrieving the body stream. `returnResult(StockUpdate.class)` instructs WebTestClient to decode each response item into `StockUpdate`.

## 3. Declaring the dependency for StepVerifier

`StepVerifier` belongs to the `reactor-test` module, not `reactor-core`. If the project does not yet have this dependency on the test classpath, add the appropriate test dependency:

```groovy
dependencies {
    testImplementation("io.projectreactor:reactor-test")
}
```

With Maven:

```xml
<dependency>
    <groupId>io.projectreactor</groupId>
    <artifactId>reactor-test</artifactId>
    <scope>test</scope>
</dependency>
```

Keep the `reactor-test` version compatible with the Reactor Core used by Spring Framework or Spring Boot. When a project uses Spring Boot's BOM, let dependency management select the version rather than pinning a different version manually.

Common imports:

```java
import reactor.test.StepVerifier;
import org.springframework.test.web.reactive.server.FluxExchangeResult;
```

## 4. Testing a finite stream

Example controller returning two price updates:

```java
import reactor.core.publisher.Flux;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class StockController {

    @GetMapping(value = "/stocks/stream", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    Flux<StockUpdate> stream() {
        return Flux.just(
                new StockUpdate("ACME", 100),
                new StockUpdate("ACME", 105));
    }
}

record StockUpdate(String symbol, int price) {}
```

The test retrieves `FluxExchangeResult` and verifies the elements in order:

```java
import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.FluxExchangeResult;
import reactor.test.StepVerifier;

import static org.springframework.test.web.reactive.server.WebTestClient.bindToController;

class StockControllerTests {

    private final WebTestClient client = bindToController(
            new StockController()).build();

    @Test
    void streamsStockUpdatesInOrder() {
        FluxExchangeResult<StockUpdate> result = client.get()
                .uri("/stocks/stream")
                .accept(MediaType.TEXT_EVENT_STREAM)
                .exchange()
                .expectStatus().isOk()
                .expectHeader().contentTypeCompatibleWith(MediaType.TEXT_EVENT_STREAM)
                .returnResult(StockUpdate.class);

        StepVerifier.create(result.getResponseBody())
                .expectNext(new StockUpdate("ACME", 100))
                .expectNext(new StockUpdate("ACME", 105))
                .verifyComplete();
    }
}
```

`expectNext(...)` verifies the value and order of each element. `verifyComplete()` requires the stream to finish emitting items and send an `onComplete` signal. If the stream emits unexpected extra items or terminates with an error, verification fails.

Because `StockUpdate` is a record, `equals` comparison can be used directly in `expectNext`. For regular classes, implement appropriate equality or use `expectNextMatches(...)` to check properties.

## 5. Testing infinite or long-lived streams

A streaming endpoint may never send `onComplete` under normal conditions. For instance, a server emitting periodic metrics:

```java
@GetMapping(value = "/stocks/live", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
Flux<StockUpdate> liveUpdates() {
    return Flux.interval(Duration.ofSeconds(1))
            .map(sequence -> new StockUpdate("ACME", 100 + sequence.intValue()));
}
```

You cannot call `verifyComplete()` on this stream because it is not meant to finish. The test should verify the required number of items and then explicitly cancel the subscription:

```java
FluxExchangeResult<StockUpdate> result = client.get()
        .uri("/stocks/live")
        .accept(MediaType.TEXT_EVENT_STREAM)
        .exchange()
        .expectStatus().isOk()
        .returnResult(StockUpdate.class);

StepVerifier.create(result.getResponseBody())
        .expectNextMatches(update -> "ACME".equals(update.symbol()))
        .expectNextMatches(update -> update.price() == 101)
        .thenCancel()
        .verify(Duration.ofSeconds(5));
```

`thenCancel()` cancels the subscription after the preceding expectations are met. This matters because the test needs to release the stream and open connection. Use `verify(Duration)` to cap the wait time and prevent the test from hanging indefinitely if the server fails to emit data.

For publishers requiring backpressure verification, start with zero initial demand and request elements one at a time:

```java
StepVerifier.create(result.getResponseBody(), 0)
        .expectSubscription()
        .thenRequest(1)
        .expectNextMatches(update -> update.price() >= 100)
        .thenRequest(1)
        .expectNextMatches(update -> update.price() >= 100)
        .thenCancel()
        .verify(Duration.ofSeconds(5));
```

This example verifies that the publisher is only asked to emit data according to the demand requested by the test. This is useful when backpressure behavior is part of the contract under test.

## 6. Server-Sent Events and ServerSentEvent<T>

SSE is an HTTP streaming format commonly used by a server to push one-way events to clients. Responses typically have media type `text/event-stream`. Each event can contain `id`, `event`, `retry`, and `data`.

Spring represents SSE with `ServerSentEvent<T>`. A controller can return `Flux<ServerSentEvent<StockUpdate>>` to control metadata for each event:

```java
import org.springframework.http.codec.ServerSentEvent;

@GetMapping(value = "/stocks/events", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
Flux<ServerSentEvent<StockUpdate>> stockEvents() {
    return Flux.just(
            ServerSentEvent.<StockUpdate>builder()
                    .id("event-1")
                    .event("stock-update")
                    .data(new StockUpdate("ACME", 100))
                    .build(),
            ServerSentEvent.<StockUpdate>builder()
                    .id("event-2")
                    .event("stock-update")
                    .data(new StockUpdate("ACME", 105))
                    .build());
}
```

To check both SSE metadata and payload, use `ParameterizedTypeReference` to preserve the generic type:

```java
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.http.codec.ServerSentEvent;

ParameterizedTypeReference<ServerSentEvent<StockUpdate>> eventType =
        new ParameterizedTypeReference<>() {};

FluxExchangeResult<ServerSentEvent<StockUpdate>> result = client.get()
        .uri("/stocks/events")
        .accept(MediaType.TEXT_EVENT_STREAM)
        .exchange()
        .expectStatus().isOk()
        .returnResult(eventType);

StepVerifier.create(result.getResponseBody())
        .expectNextMatches(event ->
                "event-1".equals(event.id())
                && "stock-update".equals(event.event())
                && event.data() != null
                && event.data().price() == 100)
        .expectNextMatches(event ->
                "event-2".equals(event.id())
                && event.data() != null
                && event.data().price() == 105)
        .verifyComplete();
```

When only the payload matters and SSE metadata is not needed, you can call `returnResult(StockUpdate.class)` to receive each `StockUpdate`. When you need to verify event names or event IDs, keep `ServerSentEvent<StockUpdate>` to inspect those fields.

## 7. NDJSON and other streaming formats

NDJSON (Newline Delimited JSON) transmits each JSON object on its own line. This format fits when a server emits multiple independent JSON objects instead of wrapping them in one JSON array.

Example controller:

```java
private static final MediaType APPLICATION_NDJSON =
        MediaType.parseMediaType("application/x-ndjson");

@GetMapping(value = "/stocks/ndjson", produces = "application/x-ndjson")
Flux<StockUpdate> ndjsonUpdates() {
    return Flux.just(
            new StockUpdate("ACME", 100),
            new StockUpdate("ACME", 105));
}
```

Tests can decode each line into an object:

```java
MediaType ndjson = MediaType.parseMediaType("application/x-ndjson");

FluxExchangeResult<StockUpdate> result = client.get()
        .uri("/stocks/ndjson")
        .accept(ndjson)
        .exchange()
        .expectStatus().isOk()
        .expectHeader().contentTypeCompatibleWith(ndjson)
        .returnResult(StockUpdate.class);

StepVerifier.create(result.getResponseBody())
        .expectNext(new StockUpdate("ACME", 100))
        .expectNext(new StockUpdate("ACME", 105))
        .verifyComplete();
```

For regular `application/json`, a server-side `Flux<T>` is usually encoded as a single JSON array forming one complete document. If the goal is checking a finite JSON list, `expectBodyList(...)` is usually more suitable. To test individual elements over time, use a streaming-framed media type such as SSE or NDJSON and retrieve `FluxExchangeResult`.

## 8. How FluxExchangeResult differs from expectBodyList(...)

| API | Data received | Body reading behavior | Suitable for |
|---|---|---|---|
| `expectBody(Class<T>)` | Single object | Collects body into one value | JSON object or single response body |
| `expectBodyList(Class<T>)` | `List<T>` | Reads and collects complete list | Finite JSON array |
| `returnResult(Class<T>)` | `FluxExchangeResult<T>` | Exposes body as `Flux<T>` | SSE, NDJSON, and streaming responses |

Do not use `expectBodyList(...)` for infinite streams because the assertion must wait for the body to finish before producing the complete list. Conversely, `FluxExchangeResult` is unnecessary if the response is just a finite JSON object or array and the test does not need to verify streaming behavior.

## 9. Verifying errors and stream termination

`StepVerifier` lets you verify both completion and error signals:

```java
StepVerifier.create(result.getResponseBody())
        .expectNextCount(2)
        .verifyComplete();
```

To verify that a publisher terminates with a specific exception:

```java
StepVerifier.create(result.getResponseBody())
        .expectNextCount(1)
        .expectErrorMatches(error ->
                error instanceof IllegalStateException
                && "stream failed".equals(error.getMessage()))
        .verify(Duration.ofSeconds(5));
```

In HTTP streaming, an error can happen after response headers have already been sent. In that case, the status may already be 200 while the body stream terminates with an error. Status assertions alone will miss the problem; `StepVerifier` is required to detect error signals on the body publisher.

Distinguish HTTP errors before the body starts from errors occurring mid-stream:

- If the server returns 4xx or 5xx before a streaming body is established, check with `expectStatus()` and error body assertions per contract.
- If the server already began the response and then the publisher emits `onError`, assert the error on `getResponseBody()` using `expectError...`.
- If the client intentionally stops receiving data, use `thenCancel()` to cancel the subscription.

## 10. Notes on subscription, timeouts, and resources

The body in `FluxExchangeResult` is a reactive publisher bound to the active response being read. Normally, subscribe once per test and let `StepVerifier` manage the subscription. Do not call `block()` and then create a verifier on the same body, or try subscribing repeatedly to run multiple independent assertions.

Some practical guidelines:

- Use `verifyComplete()` for finite streams that emit a completion signal.
- Use `thenCancel()` for infinite streams or tests that only need to inspect the first few events.
- Set a timeout on `verify(...)` if the stream is time-dependent or might fail to emit data.
- Verify ordering using `expectNext(...)` or `expectNextMatches(...)`.
- Only use `expectNoEvent(Duration)` when you need to assert no signals arrive during an interval; avoid overly short timing assertions that become flaky on CI.
- Do not collect an entire infinite stream using `collectList()` or `expectBodyList(...)`.

## 11. Common mistakes

| Symptom | Common cause | How to fix |
|---|---|---|
| Test hangs when verifying stream | Calling `verifyComplete()` on a publisher that never finishes | Use `thenCancel()` after the required events and set a timeout |
| Individual JSON objects are not received | Server returns `application/json` as a single JSON array | Use SSE or NDJSON if the contract is streaming; use `expectBodyList(...)` for an array |
| `returnResult(...)` fails to decode body | Target type or codec does not match media type | Check `Accept`, response content type, and configured codecs |
| Checking status only misses mid-stream errors | Body publisher emits an error after headers were sent | Use StepVerifier to check `onError` or `onComplete` |
| Test receives only one event | Test cancels subscription too early or insufficient demand | Check `thenRequest(...)` steps and `thenCancel()` placement |
| SSE assertions miss event ID or event name | Decoding only the payload into a DTO | Use `ParameterizedTypeReference<ServerSentEvent<T>>` to preserve SSE metadata |
| Time-dependent test is flaky | Delay is too short or timing checks are unstable | Prefer checking order and counts; only assert timing when it is part of the contract |

## 12. Takeaways

`FluxExchangeResult<T>` lets you obtain a WebTestClient response body as `Flux<T>` via `returnResult(...)`. Combined with `StepVerifier`, tests can verify elements, ordering, completion signals, errors, backpressure, and stream cancellation. Use `verifyComplete()` for finite streams and `thenCancel()` for long or infinite streams. For SSE, keep `ServerSentEvent<T>` when metadata must be verified; for NDJSON, decode each line into a DTO. Choose the streaming API when the response contract actually streams data incrementally.

