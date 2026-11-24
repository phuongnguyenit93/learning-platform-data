# Receiving a Result Stream with `RSocketRequester.retrieveFlux()`

## Objectives

After this lesson, you can choose `retrieveFlux()` when an RSocket request needs to receive multiple results, match the route properly with the responder handler, consume `Flux<T>` reactively, and handle backpressure, stream cancellation, errors, and return data types.

## 1. What Is `retrieveFlux()` Used For?

`RSocketRequester` is Spring's fluent API for sending requests over RSocket using Java objects instead of manually manipulating byte-buffer payloads. `retrieveFlux(Class<T>)` declares the data type of each response element and returns `reactor.core.publisher.Flux<T>`.

RSocket has four common interaction models:

| Interaction | Data sent | Data received | Typical requester API |
| --- | --- | --- | --- |
| Request-Response | One message | One message | `retrieveMono()` |
| Request-Stream | One message | Multiple messages | `retrieveFlux()` |
| Request-Channel | A stream of messages | A stream of messages | `retrieveFlux()` |
| Fire-and-Forget | One message | No response awaited | `send()` |

For this lesson's primary case, the client sends a single object and the server returns multiple objects. Spring selects the **Request-Stream** interaction. Remember that `retrieveFlux()` is not always Request-Stream: if the input payload is passed as a multi-element `Publisher`, Spring selects **Request-Channel**. The interaction model is inferred from the input and output cardinality.

## 2. Sending a Request and Receiving a Stream

Example of a client requesting quotes for ticker `ACME`:

```java
Flux<Quote> quotes = requester
    .route("market.quotes")
    .data(new QuoteRequest("ACME"))
    .retrieveFlux(Quote.class);
```

Meaning of each step:

1. `route("market.quotes")` sets the route in the request metadata. The route must match the route registered by the responder.
2. `data(new QuoteRequest("ACME"))` sets the request payload. In this example there is only a single payload.
3. `retrieveFlux(Quote.class)` asks Spring to decode each response into a `Quote` object and return `Flux<Quote>`.

A requester can be created over TCP as follows:

```java
RSocketRequester requester = RSocketRequester.builder()
    .tcp("localhost", 7000);
```

Calling `tcp()` prepares the requester; the shared connection is established when a request actually executes and is reused thereafter. Applications can also use WebSocket or configure `RSocketStrategies` when custom codecs or metadata are needed.

## 3. Server-Side Handler

The route on the client must match `@MessageMapping` on the responder. A minimal handler can return `Flux<Quote>`:

```java
import java.time.Duration;
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.stereotype.Controller;
import reactor.core.publisher.Flux;

@Controller
class QuoteController {

    @MessageMapping("market.quotes")
    Flux<Quote> quotes(QuoteRequest request) {
        return Flux.interval(Duration.ofSeconds(1))
            .take(5)
            .map(sequence -> new Quote(request.symbol(), sequence));
    }
}

record QuoteRequest(String symbol) {}
record Quote(String symbol, long sequence) {}
```

The handler receives one `QuoteRequest` and emits up to five `Quote` instances. Because the input is a single payload and the output is multiple elements, this method handles Request-Stream. Each element of the `Flux` is encoded by Spring into a response payload sent back to the requester; when the stream ends, the client side receives a complete signal.

This snippet illustrates a handler in a Spring application already configured with an RSocket server and matching codecs. It is not a standalone Java program to run with only `javac`.

## 4. Consuming Results on the Client

In a command-line program or test example, you can wait until the stream completes using `blockLast()`:

```java
requester.route("market.quotes")
    .data(new QuoteRequest("ACME"))
    .retrieveFlux(Quote.class)
    .doOnNext(System.out::println)
    .blockLast();
```

With the handler above, the output has the following exact form:

```text
Quote[symbol=ACME, sequence=0]
Quote[symbol=ACME, sequence=1]
Quote[symbol=ACME, sequence=2]
Quote[symbol=ACME, sequence=3]
Quote[symbol=ACME, sequence=4]
```

In a reactive application such as WebFlux, return `Flux<Quote>` to the next caller so the framework manages the subscription. Avoid calling `block()`, `blockFirst()`, or `blockLast()` on the event loop because those operations block a thread serving many requests.

When you need to handle items directly with callbacks, `subscribe()` returns a `Disposable`:

```java
Disposable subscription = requester.route("market.quotes")
    .data(new QuoteRequest("ACME"))
    .retrieveFlux(Quote.class)
    .take(10)
    .subscribe(
        quote -> log.info("quote={}", quote),
        error -> log.error("Stream failed", error),
        () -> log.info("Stream completed")
    );

// When no more data is needed:
subscription.dispose();
```

`take(10)` finishes automatically after ten elements and cancels the upstream subscription. You can call `dispose()` when the lifecycle of a screen, connection, or task ends. In reactive services, it is usually better to return the publisher instead of calling `subscribe()` internally, leaving lifecycle and error control to the caller.

## 5. Backpressure and Stream Cancellation

`Flux` follows Reactive Streams. With Request-Stream and Request-Channel, demand signals are propagated across the network boundary: the requester reports how many elements it needs, and the responder must honor that demand. As a result, the client can regulate the rate at which it receives data and avoid having the server emit unboundedly into an uncontrolled buffer.

Example limiting request rate from the client side:

```java
Flux<Quote> quotes = requester.route("market.quotes")
    .data(new QuoteRequest("ACME"))
    .retrieveFlux(Quote.class)
    .limitRate(32);
```

`limitRate(32)` adjusts how downstream requests data from upstream in batches. It does not replace designing an emission source capable of respecting backpressure. If the source is a hot publisher or cannot slow down, choose an explicit policy such as bounded buffering, drop, or latest; avoid unbounded buffers because they can grow memory until the application fails.

Operators such as `take(n)`, `take(Duration)`, and disposing the subscription end the stream when it is no longer needed. Cancelling the subscription also sends a cancel signal over RSocket; the responder-side source can stop corresponding work if it supports cancellation.

Do not call `collectList()` on long or unbounded streams if the goal is to process each element as it arrives. `collectList()` must retain all elements in memory and only emits a single `Mono<List<T>>` when the stream completes.

## 6. Generic Response Types

When the response is a generic type such as `ApiEvent<Quote>`, `Class<T>` cannot preserve type parameters due to Java type erasure. Use the overload accepting `ParameterizedTypeReference<T>`:

```java
Flux<ApiEvent<Quote>> events = requester.route("market.quote-events")
    .data(new QuoteRequest("ACME"))
    .retrieveFlux(new ParameterizedTypeReference<ApiEvent<Quote>>() {});
```

Import `org.springframework.core.ParameterizedTypeReference`. This preserves the `ApiEvent<Quote>` information so codecs decode nested types accurately.

## 7. Completion, Errors, and Empty Data

- If the responder emits no elements and completes, the client receives an empty stream and an `onComplete` signal; there is no `null` element representing an empty result.
- If the responder, connection, or decoding encounters an error, the `Flux` emits `onError` and terminates. Handle errors using operators such as `doOnError`, `onErrorResume`, or `retryWhen` depending on application policy.
- Only retry when the operation can be safely repeated. A resent request may cause the server to repeat work or replay side effects.
- For long-lived streams, define clear termination conditions, idle timeouts where appropriate, and how subscriptions are released when callers leave.

Example using a fallback for a recoverable error:

```java
Flux<Quote> quotes = requester.route("market.quotes")
    .data(new QuoteRequest("ACME"))
    .retrieveFlux(Quote.class)
    .onErrorResume(RecoverableQuoteException.class, error -> fallbackQuotes());
```

`fallbackQuotes()` must return `Flux<Quote>`. In real applications, only handle identified error types; do not turn every error into an empty stream because that can hide connection failures or data errors.

## 8. Codecs and Data Types on Both Ends

The `Quote.class` or `ParameterizedTypeReference` parameter describes the expected type on the receiving side. It does not itself define how payloads are serialized. Requester and responder must have encoders/decoders compatible with the data format and connection MIME type.

In a basic Spring Framework configuration, default codecs mainly support `String`, `byte[]`, and `ByteBuffer`. To transmit DTOs such as `QuoteRequest` or `Quote`, register matching encoders/decoders, commonly Jackson JSON or CBOR via `RSocketStrategies`. Spring Boot can auto-configure codecs when the corresponding dependencies are present. If codecs are missing or both sides use incompatible formats, the request can fail during encode/decode.

## 9. Quick Comparison and Common Mistakes

| Scenario | How to handle |
| --- | --- |
| One request, one response | Use `retrieveMono()` |
| One request, multiple responses | Use `retrieveFlux()` with a single payload |
| Multiple request payloads and a response stream | Use `retrieveFlux()` with a `Publisher` input; Spring selects Request-Channel |
| Only send a message, no response needed | Use `send()` |

Mistakes to check for:

1. Using `retrieveMono()` when the server returns multiple elements; interaction model and cardinality do not match.
2. Route in `route()` does not match `@MessageMapping` or the route configured on the responder.
3. Creating a `Flux` without returning it to the caller or subscribing; without a subscriber, the pipeline is not consumed.
4. Calling `subscribe()` inside a service and discarding the `Disposable`, making lifecycle and error handling hard to control.
5. Assuming every `retrieveFlux()` call is Request-Stream; a multi-element input leads to Request-Channel.
6. Using `Class` for a generic response and expecting Java to retain type parameters; use `ParameterizedTypeReference`.
7. Collecting an infinite stream with `collectList()` or using unbounded buffers, increasing memory usage.
8. Configuring codecs only on the client or server and forgetting the other side, making payloads undecodable.

## 10. Summary

`retrieveFlux()` is the choice for receiving a sequence of responses decoded into `Flux<T>`. When sending a single payload, it creates Request-Stream: one request and multiple responses. When sending a multi-element input, it creates Request-Channel. Let subscriptions drive consumption, leverage backpressure, cancel streams when no longer needed, and configure compatible codecs on both ends.

## References

- [Spring Framework Reference — RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html)
- [Spring Framework Javadoc — RSocketRequester.RetrieveSpec](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/rsocket/RSocketRequester.RetrieveSpec.html)
