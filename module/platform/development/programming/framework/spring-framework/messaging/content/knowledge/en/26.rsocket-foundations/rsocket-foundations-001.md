# RSocket and Reactive Data Exchange Protocol

## Learning Objectives

After this lesson, you will be able to:

- Explain why RSocket is a bidirectional messaging protocol and how it operates over a single connection.
- Distinguish the four interaction models: request-response, fire-and-forget, request-stream, and request-channel.
- Understand the roles of data, metadata, route, transport, and the connection setup process.
- Use Spring Framework with `RSocketRequester` on the requester side and `@MessageMapping` on the responder side.
- Combine `Mono`, `Flux`, and Reactive Streams to process asynchronous data with backpressure.
- Handle errors, stream cancellation, serialization, and security in RSocket applications.

## 1. What Is RSocket?

RSocket is an application protocol for exchanging messages between two endpoints of a connection. It is designed for asynchronous, bidirectional communication and supports reactive data streams. A single RSocket connection can carry many independent streams concurrently, allowing both sides to send requests and responses without opening a separate connection for each operation.

In Spring Framework, RSocket integrates with the Reactive Streams ecosystem. The sender uses `RSocketRequester` to issue requests; the receiver uses `@MessageMapping` methods to handle routes and return `Mono` or `Flux`.

RSocket is not merely a way to send messages over WebSocket. It defines the protocol, frames, interaction models, metadata, flow control, and stream management. TCP and WebSocket are common transports that can carry RSocket frames.

Key characteristics:

- **Bidirectional:** both client and server can initiate requests when the application allows it.
- **Multiplexing:** multiple streams can run concurrently over a single connection.
- **Reactive Streams:** supports demand, backpressure, and cancellation for data streams.
- **Metadata:** routes and auxiliary information can be sent separately from the data payload.
- **Multiple interaction models:** from a single request/response to bidirectional data streams.
- **Transport-agnostic:** the protocol can run over TCP or WebSocket, along with other implemented transports.

RSocket is useful when a system requires streaming, bidirectional communication, backpressure, or a unified API for multiple interaction styles. For simple CRUD operations, HTTP/REST can still be a suitable and easier choice to deploy.

## 2. RSocket in Spring Messaging

Spring Framework provides abstractions to connect applications with RSocket:

| Component | Role |
|---|---|
| `RSocketRequester` | Requester-side API to build route, data, and receive reactive results |
| `@MessageMapping` | Maps a route to a handler method on the responder side |
| `@ConnectMapping` | Handles connection setup frames, typically used to receive metadata or payload at connect time |
| `RSocketMessageHandler` | Resolves annotations and dispatches messages to the matching method |
| `RSocketStrategies` | Configures encoders, decoders, and data/metadata conversion components |
| `Mono<T>` | Represents at most one asynchronous result |
| `Flux<T>` | Represents an asynchronous sequence of results, which may be empty or unbounded |

`RSocketRequester` is not an HTTP client. It creates RSocket requests according to interaction models and processes responses via Reactive Streams.

On the responder side, a Spring controller can be declared with `@MessageMapping`. The route in the annotation is used to select the handler method. For example, the route `quotes.current` can map to a method that retrieves the current quote.

Spring supports DTOs, `Publisher`, `Mono`, and `Flux`. Encoders/decoders convert payloads between Java objects and their wire representation.

## 3. The Four RSocket Interaction Models

RSocket has four primary interaction models. Choosing the right model makes the API clearly express the number of requests, the number of responses, and the direction of data flow.

### 3.1. Request-response

One request produces at most one response.

```text
Requester  ---- request ---->  Responder
Requester  <--- response ----  Responder
```

Characteristics:

- The request is a single payload.
- The response is a single payload.
- Suitable for queries or commands that need a single result.
- The requester side typically uses `retrieveMono(Response.class)`.
- The responder side can return an object or `Mono<T>`.

### 3.2. Fire-and-forget

The requester sends a payload and does not wait for an application response.

```text
Requester  ---- request ---->  Responder
                (no response)
```

Characteristics:

- Suitable for one-way events or tasks that do not need an immediate return result.
- The requester side typically uses `send()`.
- The responder side can handle it with a method returning nothing or returning `Mono<Void>`.
- There is no response payload to confirm that business processing completed.

Do not use fire-and-forget if the caller needs to know whether a command was processed successfully, needs a result ID, or needs to retry based on a response. Completion of sending on the client-side publisher does not mean server-side business processing has completed and been durably persisted.

### 3.3. Request-stream

A single request initiates a stream consisting of multiple responses.

```text
Requester  ---- request ---->  Responder
Requester  <--- response 1 --  Responder
Requester  <--- response 2 --  Responder
Requester  <--- response 3 --  Responder
                    ...
```

Characteristics:

- The initial request is a single payload.
- The response is a sequence of elements.
- Suitable for continuously updated data, market quotes, task statuses, or streamed search results.
- The requester side typically uses `retrieveFlux(Response.class)`.
- The responder side typically returns `Flux<T>`.

### 3.4. Request-channel

Both request and response are streams. The requester sends multiple elements and the responder can return multiple corresponding elements or process them independently.

```text
Requester  ---- request 1 ---> Responder
Requester  ---- request 2 ---> Responder
Requester  ---- request 3 ---> Responder
Requester  <--- response 1 -- Responder
Requester  <--- response 2 -- Responder
Requester  <--- response 3 -- Responder
```

Characteristics:

- The requester provides a publisher.
- The responder receives a publisher and returns another publisher.
- Suitable for bidirectional stream processing.
- The requester side passes a `Flux` or `Publisher` to `data(...)` and then calls `retrieveFlux(...)`.
- The responder side receives `Publisher<T>` or `Flux<T>` and returns `Flux<R>`.

### Comparison Table

| Model | Request | Response | Spring requester |
|---|---|---|---|
| Request-response | One payload | At most one payload | `retrieveMono(T.class)` |
| Fire-and-forget | One payload | No response payload | `send()` |
| Request-stream | One payload | Multiple payloads | `retrieveFlux(T.class)` |
| Request-channel | One stream | One stream | `data(Publisher).retrieveFlux(T.class)` |

Beyond the four interaction models, the protocol also has control frames such as SETUP, KEEPALIVE, LEASE, RESUME, and METADATA_PUSH. They support establishing, maintaining, or managing the connection; they should not be confused with the four business request types above.

## 4. Data, Metadata, and Route

An RSocket payload can contain two independent parts:

- **Data:** the primary content, usually a DTO or binary data.
- **Metadata:** information that describes or controls how data is processed.

Metadata can carry the route, authentication information, tracing, or other auxiliary data. Metadata does not replace the business payload.

In Spring, the requester selects a route using `route(...)`:

```java
Mono<Quote> result = requester
        .route("quotes.current")
        .data(new QuoteRequest("ACME"))
        .retrieveMono(Quote.class);
```

Here:

- `quotes.current` is routing metadata used by the responder to select a handler.
- `QuoteRequest` is the data payload.
- `retrieveMono(Quote.class)` requests a single response decoded into `Quote`.

A route is neither an HTTP URL path nor a STOMP destination. A route is routing metadata in RSocket. The route name must match the mapping on the responder side.

Responder example:

```java
@Controller
public class QuoteController {

    @MessageMapping("quotes.current")
    public Mono<Quote> current(QuoteRequest request) {
        return quoteService.findCurrent(request.symbol());
    }
}
```

If the route does not match any mapping, the request may be rejected or return an error depending on configuration and how the application handles errors.

### Custom Metadata

The requester can attach metadata in addition to the route:

```java
Mono<Quote> result = requester
        .route("quotes.current")
        .metadata("trace-42", MimeType.valueOf("text/plain"))
        .data(new QuoteRequest("ACME"))
        .retrieveMono(Quote.class);
```

The responder side can read metadata through Spring's supported mechanisms. The metadata MIME type indicates how to interpret the value. If multiple metadata types are needed in the same payload, RSocket supports composite metadata; each metadata entry must have a corresponding MIME type and encoding.

Do not put sensitive information into metadata just because it is not in data. Metadata is still transmitted over the network and must be protected with transport security, authentication, and appropriate logging policies.

## 5. Building a Responder with @MessageMapping

A single controller can expose multiple routes corresponding to different interaction models.

Quote model example:

```java
import java.math.BigDecimal;

import org.reactivestreams.Publisher;
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.stereotype.Controller;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Controller
public class QuoteController {

    private final QuoteService quoteService;

    public QuoteController(QuoteService quoteService) {
        this.quoteService = quoteService;
    }

    // Request-response: one request, one result.
    @MessageMapping("quotes.current")
    public Mono<Quote> current(QuoteRequest request) {
        return quoteService.findCurrent(request.symbol());
    }

    // Request-stream: one request, multiple results.
    @MessageMapping("quotes.watch")
    public Flux<Quote> watch(QuoteRequest request) {
        return quoteService.watch(request.symbol());
    }

    // Fire-and-forget: does not return a response payload.
    @MessageMapping("quotes.audit")
    public Mono<Void> audit(AuditEvent event) {
        return quoteService.recordAudit(event);
    }

    // Request-channel: receives a stream and returns a stream.
    @MessageMapping("quotes.exchange")
    public Flux<QuoteAck> exchange(
            Publisher<QuoteUpdate> updates) {

        return Flux.from(updates)
                .concatMap(quoteService::applyUpdate);
    }
}

record QuoteRequest(String symbol) {}

record Quote(String symbol, BigDecimal price) {}

record AuditEvent(String action, String reference) {}

record QuoteUpdate(String symbol, BigDecimal price) {}

record QuoteAck(String symbol, boolean accepted) {}
```

How to read the example:

1. `quotes.current` returns `Mono<Quote>`, fitting request-response.
2. `quotes.watch` returns `Flux<Quote>`, fitting request-stream.
3. `quotes.audit` returns `Mono<Void>`, emitting no response payload to the requester.
4. `quotes.exchange` receives a publisher of updates and returns a publisher of acknowledgments, fitting request-channel.
5. `concatMap` processes each update in order and waits for the previous update's publisher to complete before moving to the next update.

The methods above illustrate signatures and route mapping. To run in practice, the application needs to configure the RSocket server transport, `RSocketMessageHandler`, `RSocketStrategies`, and the corresponding services. These configurations depend on whether the application initializes the server itself or uses Spring Boot.

## 6. Sending Requests with RSocketRequester

Requester provides a fluent API to select a route, send data, and declare the expected response type.

### Request-response

```java
Mono<Quote> current = requester
        .route("quotes.current")
        .data(new QuoteRequest("ACME"))
        .retrieveMono(Quote.class);
```

`retrieveMono` returns `Mono<Quote>`. Upon subscription, the request is executed and the response is decoded into the declared type.

### Request-stream

```java
Flux<Quote> updates = requester
        .route("quotes.watch")
        .data(new QuoteRequest("ACME"))
        .retrieveFlux(Quote.class);
```

`retrieveFlux` returns a stream. Consumers can process each element instead of waiting for all data to be collected into a single collection.

### Fire-and-forget

```java
Mono<Void> sent = requester
        .route("quotes.audit")
        .data(new AuditEvent("VIEW", "ACME"))
        .send();
```

`send()` returns no business payload. It is the choice for one-way commands when the caller does not need a response. If confirmation of recording or processing is required, use request-response and return an explicit acknowledgment.

### Request-channel

```java
Flux<QuoteUpdate> updates = Flux.just(
        new QuoteUpdate("ACME", new BigDecimal("101.25")),
        new QuoteUpdate("ACME", new BigDecimal("101.50")),
        new QuoteUpdate("ACME", new BigDecimal("101.75"))
);

Flux<QuoteAck> acknowledgements = requester
        .route("quotes.exchange")
        .data(updates)
        .retrieveFlux(QuoteAck.class);
```

The requester passes a publisher as the request stream and receives a response stream. The consumer must subscribe to `acknowledgements` to start consuming results.

Reactive chains are lazy: creating a `Mono` or `Flux` usually does not perform I/O until there is a subscription. Connect the chain to a reactive runtime, such as a WebFlux handler or subscriber. Do not call `block()` arbitrarily on an event loop or reactive processing thread.

## 7. Connection Setup and Transport

The RSocket protocol is transport-independent. Common transports:

- **TCP:** suitable for service-to-service communication in internal networks or environments requiring direct connections.
- **WebSocket:** suitable when connecting via RSocket from browsers or traversing infrastructure that already supports WebSocket.

Example creating a TCP requester:

```java
import org.springframework.messaging.rsocket.RSocketRequester;
import reactor.core.publisher.Mono;

Mono<RSocketRequester> requesterMono = RSocketRequester.builder()
        .connectTcp("localhost", 7000);
```

`connectTcp` returns `Mono<RSocketRequester>` because connection establishment is asynchronous. It can be composed with subsequent operations via `flatMap` or managed as a requester within the application lifecycle.

Example using the requester after connecting:

```java
Mono<Quote> quote = requesterMono.flatMap(requester ->
        requester.route("quotes.current")
                .data(new QuoteRequest("ACME"))
                .retrieveMono(Quote.class)
);
```

In a long-lived application, manage a requester/connection aligned with the lifecycle rather than creating a new connection for every message. When the application shuts down, dispose of connection resources using the mechanism provided by the managing client.

### SETUP and Connection Lifecycle

When a connection is created, both sides exchange a SETUP frame to establish the RSocket session and negotiate necessary details, including MIME types for data and metadata. Afterward, the connection can carry many independent request streams.

Other control frames have distinct roles:

- **KEEPALIVE:** checks and maintains the connection.
- **LEASE:** limits or grants permission to initiate requests under a lease mechanism if enabled.
- **RESUME:** supports resuming a session under compatible conditions and configuration.
- **METADATA_PUSH:** sends connection-level metadata.
- **ERROR:** signals an error at stream or connection scope depending on the error type.

Not every application needs to enable lease or resume. Choose features according to load management, resilience requirements, and deployment infrastructure.

## 8. Reactive Streams, Backpressure, and Cancellation

Backpressure is the consumer's ability to control how much data a producer is allowed to emit. This is crucial when a server provides large streams or continuously updated data.

In Reactive Streams, a subscriber signals demand via `request(n)`. With RSocket request-stream and request-channel, demand is propagated through the protocol's flow-control mechanism. A producer should not emit unbounded data faster than the client can consume it.

Example of a consumer limiting the number of elements:

```java
Flux<Quote> firstTen = requester
        .route("quotes.watch")
        .data(new QuoteRequest("ACME"))
        .retrieveFlux(Quote.class)
        .take(10);
```

`take(10)` completes after receiving ten elements and cancels the upstream subscription. This stops consuming the stream when data is no longer needed.

### Backpressure Is Not Business Rate Limiting

Backpressure regulates subscriber demand and emission rate within a stream. It does not replace:

- Per-user or per-tenant rate limits.
- Payload size limits.
- Limits on concurrent connections or concurrent streams.
- API quotas or anti-abuse policies.
- Resource controls for databases and downstream services.

A single client can consume slowly while still opening too many streams. Applications must manage both flow control and system-level resource limits.

### Cancellation and Resources

When a consumer cancels a subscription, RSocket can send CANCEL for the corresponding stream. The responder should release associated resources, stop queries, or cancel cancellable work.

However, cancellation does not automatically roll back side effects that have already completed. If a request-channel has already written part of the data to a database before the client cancels, the application must have its own transaction or business rules to ensure consistency.

### Handling Finite and Infinite Streams

- For finite streams, emit completion when the data ends.
- For infinite streams, establish appropriate cancellation, timeout, heartbeat, or time-limit strategies.
- Use operators like `take`, `timeout`, `onErrorResume`, and `limitRate` as needed.
- Avoid collecting an entire infinite stream into memory with `collectList`.

## 9. Errors and Timeouts

RSocket can report errors at stream or connection scope. In Spring, errors from responder methods can be translated into RSocket stream error signals and arrive at the requester as reactive errors.

Example of requester-side error handling:

```java
Mono<Quote> quote = requester
        .route("quotes.current")
        .data(new QuoteRequest("UNKNOWN"))
        .retrieveMono(Quote.class)
        .timeout(Duration.ofSeconds(3))
        .onErrorResume(error -> {
            // Log in a controlled manner or convert to a fallback.
            return Mono.empty();
        });
```

This example illustrates timeout and fallback. In real applications, do not turn every error into an empty result if callers need to distinguish not found, unauthorized, timeout, and system errors.

Some principles:

- Use timeouts for requests with business time limits.
- Distinguish validation errors, access-control errors, transient errors, and non-retryable errors.
- Only retry when the operation is safe to repeat or carries an idempotency key.
- Do not retry infinitely; configure retry count and backoff.
- Log necessary stream/route and correlation ID details, avoiding sensitive payloads.
- Handle cancellation separately from errors; a client cancelling a stream is not necessarily a system failure.
- If confirmation of a write command is required, design a response with explicit status instead of using fire-and-forget.

## 10. Serialization and RSocketStrategies

RSocket transmits payloads as data and metadata. Java objects must be converted to wire format by an encoder; the receiving side uses a decoder to reconstruct the object.

`RSocketStrategies` is where components are configured, such as:

- Encoders for outbound payloads.
- Decoders for inbound payloads.
- Default or supported MIME types.
- Metadata extractors and appropriate metadata-handling components.

Applications often use JSON for DTOs, but can choose CBOR or another binary format if both sides agree. Formats and MIME types must be compatible between requester and responder.

When configuring codecs, keep in mind:

- DTOs must have a structure understood by the encoder/decoder.
- Do not assume every class is automatically serializable just because a dependency was added.
- Data MIME type and metadata MIME type are two separate concepts.
- With composite metadata, each metadata entry must be encoded and identified by MIME type.
- Large payloads require size limits and appropriate streaming strategies.

Do not confuse successful serialization with successful validation. After the decoder constructs an object, the application must still validate data and business permissions.

## 11. @ConnectMapping and Connection-Setup Handling

`@ConnectMapping` lets a responder handle information sent during RSocket connection setup. It is useful when the server needs to receive initial metadata such as client details, protocol version, or session initialization data.

Unlike `@MessageMapping`, which handles requests by route, `@ConnectMapping` is tied to the connection lifecycle. It can be used to:

- Register new clients/sessions.
- Validate initialization data at the application layer.
- Attach metadata for tracing or session management.
- Reject the connection if required information is invalid per application policy.

Do not put unprotected secrets or authentication data into setup metadata. If setup metadata carries identity information, it must be verified using a trustworthy authentication mechanism and appropriate transport security.

For payload authentication and authorization, Spring Security provides dedicated support for RSocket. This configuration differs from STOMP/WebSocket message channel security. Do not mechanically apply STOMP matchers like `/app/**` or `/topic/**` to RSocket routes.

## 12. RSocket Security

A long-lived RSocket connection can carry many request streams, so security must be considered at both connection setup and per-request levels.

Principles:

- **Protect transport:** use TLS when data traverses untrusted networks; WebSocket also requires corresponding security configuration.
- **Authenticate identity:** do not trust a username or role merely because the client sent them in payload/metadata.
- **Authorize by route:** restrict which routes each user/role is permitted to call.
- **Check business permissions:** verify ownership, tenant, and per-resource permissions in services.
- **Limit payloads:** cap data and metadata sizes, stream counts, and request rates.
- **Manage connections:** handle timeouts, disconnects, and resource cleanup.
- **Protect logs:** do not log tokens, credentials, or sensitive payloads.

Spring Security integrates RSocket security with configurations such as `@EnableRSocketSecurity`, authentication metadata, and payload authorization. Exact mechanisms depend on the Spring Security version and how the application transmits credentials in setup or per-request metadata.

An obscure route name is not an authorization mechanism. The server must verify authentication and authorities before processing requests.

## 13. Comparing RSocket with STOMP and HTTP

| Criterion | RSocket | STOMP over WebSocket | HTTP/REST |
|---|---|---|---|
| Primary model | Request-response, FNF, stream, channel | SEND/SUBSCRIBE via destinations | Request/response |
| Streaming | Has request-stream and request-channel | Can receive multiple messages via subscription | Can stream depending on version/transport |
| Backpressure | Flow control integrated with Reactive Streams | Lacks RSocket's request-N flow-control model | Depends on API/transport |
| Routing | Route metadata | Destinations and broker prefixes | URL, method, query |
| Multiplexing | Multiple streams over one connection | One WebSocket session with multiple subscriptions | Usually independent requests; HTTP/2 has multiplexing |
| Bidirectional | Supports two-way communication | Client/server exchange through broker | Request/response model |
| Best suited for | Reactive service-to-service, streaming, two-way communication | Real-time pub/sub and message broker integration | Web APIs, CRUD, general integrations |

Both RSocket and STOMP can run over WebSocket, yet they are different protocols. A STOMP endpoint does not automatically become an RSocket endpoint just because both use WebSocket as a transport.

Choose RSocket when you need diverse interaction models, streams, and backpressure. Choose STOMP when the application needs a familiar destination/subscription model and message broker. Choose HTTP/REST for standard request-response APIs that integrate easily with the web ecosystem.

## 14. Common Pitfalls

| Symptom | Cause | Resolution |
|---|---|---|
| Route finds no handler | Route in requester does not match `@MessageMapping` | Check route metadata and mappings |
| Requester waits forever for response | Wrong interaction model used or responder does not emit completion | Check `retrieveMono`/`retrieveFlux` and return types |
| Using `send()` while expecting a result | Fire-and-forget has no response payload | Use request-response with an acknowledgment |
| Stream consumes too much memory | Collecting an unbounded stream or lacking backpressure | Process element-by-element, limit demand, and avoid unbounded collection |
| JSON fails to deserialize to DTO | Missing codec or incompatible MIME type | Check `RSocketStrategies`, encoders/decoders, and content type |
| Request-channel receives only part of data | Publisher completed/errored or was cancelled | Check lifecycle, demand, timeout, and cancellation |
| Too many connections created | Opening a connection per request | Reuse requester/connection according to lifecycle |
| Using STOMP destinations in RSocket | Confusing route metadata with broker destinations | Use RSocket routes and configure the responder accordingly |
| User calls unauthorized route | Only checking route existence without authorization | Add authentication, payload authorization, and business checks |

## 15. Self-Check Exercise

A stock quote service has these requirements:

1. Fetch the current price of a symbol and receive one result.
2. Watch prices continuously until the client cancels.
3. Send an audit event without needing a response.
4. Send multiple price updates to the server and receive an acknowledgment for each update.
5. Prevent unauthenticated clients from calling the update route.

Select the appropriate interaction model and API:

| Requirement | Interaction model | Spring requester API |
|---|---|---|
| Fetch current price | Request-response | `retrieveMono(Quote.class)` |
| Watch prices | Request-stream | `retrieveFlux(Quote.class)` |
| Send one-way audit | Fire-and-forget | `send()` |
| Send and receive update streams | Request-channel | `data(updates).retrieveFlux(QuoteAck.class)` |
| Block unauthenticated clients | Authentication/authorization | Spring Security RSocket |

Additional questions:

1. Why is `Mono` suited for request-response?
2. Why is `Flux` suited for request-stream?
3. When a client calls `take(10)` on a stream, what happens after the tenth element?
4. Why does completing `send()` not prove the server finished business processing?
5. Can route metadata replace authentication?

Answers:

1. `Mono` represents at most one result or no result.
2. `Flux` represents multiple elements over time.
3. The consumer completes and cancels the upstream subscription, allowing the responder to stop related work if possible.
4. Fire-and-forget has no response payload confirming business processing.
5. No. Routes only route requests; identity and permissions must be authenticated separately.

## 16. Key Takeaways

- RSocket is a bidirectional, reactive messaging protocol supporting multiplexing.
- The four interaction models are request-response, fire-and-forget, request-stream, and request-channel.
- Data holds the payload; metadata holds the route and auxiliary information.
- `RSocketRequester` creates requests; `@MessageMapping` handles routes on the responder.
- `Mono` represents at most one result; `Flux` represents a stream of multiple elements.
- Backpressure regulates demand; cancellation frees streams when no longer needed.
- TCP and WebSocket are transports; they are not interaction models.
- Fire-and-forget provides no response confirming business completion.
- Codec, MIME type, authentication, and authorization configurations must match on both sides.

## References

- Spring Framework Reference — [RSocket](https://docs.spring.io/spring/reference/rsocket.html)
- Spring Framework Reference — [RSocket Messaging](https://docs.spring.io/spring/reference/rsocket.html#rsocket-messaging)
- Spring Framework Javadoc — [RSocketRequester](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/rsocket/RSocketRequester.html)
- Spring Framework Javadoc — [RSocketMessageHandler](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/rsocket/RSocketMessageHandler.html)
- RSocket Protocol — [Protocol Specification](https://rsocket.io/about/protocol/)
- Reactive Streams — [Specification](https://www.reactive-streams.org/)
