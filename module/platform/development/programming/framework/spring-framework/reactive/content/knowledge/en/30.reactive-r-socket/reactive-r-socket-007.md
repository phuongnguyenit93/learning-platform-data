# RSocket Connection Setup, Lifecycle, and Error Handling in Spring Framework Reactive

## 1. Lesson Objectives

RSocket is a bidirectional (duplex) communication protocol that supports multiple requests over a single connection and propagates Reactive Streams backpressure signals across the network. In Spring, `RSocketRequester` creates requests from the client or from the server; `@MessageMapping` and `@ConnectMapping` are the handler entry points on the responder side.

An RSocket call is not simply "open a socket and send JSON." The application must manage:

- Choosing TCP or WebSocket transport and specifying the endpoint.
- Negotiating the `SETUP` frame: version, MIME types, metadata, keepalive, and optional capabilities.
- Reusing connections and re-establishing them when lost.
- Individual request lifecycles: completion, cancellation, errors, timeouts.
- Requester lifecycle on application shutdown: stopping new requests and releasing the transport.
- Distinguishing TCP/TLS errors, setup rejections, protocol errors, and business errors.
- Controlled retry/backoff, avoiding resending non-idempotent operations.
- Safe logging/metrics/tracing, protecting credentials and resources.

This lesson uses Java 17+, Spring Boot 3.3.x, Spring Framework 6.1/6.2, and RSocket Java 1.1.x as the foundation. A complete Spring Boot 3.3.5 example is presented so it can be run with Maven.

**Expected outcome:** clearly understand the boundary between **connection** and **request stream**; configure `RSocketRequester`; know when the client automatically reconnects vs. when the application must decide to retry; and test request-response, request-stream, channel, and application errors.

## 2. Where does RSocket differ from HTTP request/response?

Traditional HTTP typically pairs one request with one response. RSocket supports four interaction models once a connection is established.

| Model | Data direction | Typical RSocketRequester call |
|---|---|---|
| Request-Response | 1 request → 0/1 response | `retrieveMono(T.class)` |
| Request-Stream | 1 request → many responses | `retrieveFlux(T.class)` |
| Request-Channel | Many request payloads ↔ many responses | `data(Publisher, Class)` + `retrieveFlux(T.class)` |
| Fire-and-Forget | Send one request, await no response payload | `send()` |

Correspondingly:

```text
Request-Response
  Requester -- REQUEST_RESPONSE --> Responder
  Requester <-- PAYLOAD ---------- Responder

Request-Stream
  Requester -- REQUEST_STREAM ----> Responder
  Requester <-- PAYLOAD(1..n) ---- Responder

Request-Channel
  Requester -- REQUEST_CHANNEL --> Responder
  Requester <-- PAYLOAD ---------- Responder
  Requester -- PAYLOAD ----------> Responder

Fire-and-Forget
  Requester -- REQUEST_FNF -------> Responder
```

This does not mean RSocket guarantees durable storage or exactly-once processing. Fire-and-Forget only means the requester receives no response payload per the protocol model; there is no business acknowledgment that data committed to a database.

Once the connection is open, both sides are nearly symmetric at the protocol level: either can proactively send requests. Hence Spring distinguishes *requester* and *responder* rather than fixing client/server per request.

### Lifecycle-related benefits

- One connection can simultaneously carry multiple logical streams.
- Each stream has its own identity and complete/error/cancel signals.
- Request-Stream/Channel propagate demand via `REQUEST_N`.
- Keepalive helps detect unresponsive peers.
- Advanced features such as leasing/resume require support and configuration on both sides.

Do not equate backpressure with data durability or automatic recovery of lost requests.

## 3. Steps to establish an RSocket connection

Timeline diagram:

```text
Client / Requester                      Server / Responder
        |                                        |
        |---- Resolve DNS, TCP connect -------->|
        |       (or WebSocket upgrade)           |
        |---- RSocket SETUP -------------------->|
        |      protocol version                  |
        |      data + metadata MIME types        |
        |      keepalive / max lifetime          |
        |      optional setup data/metadata      |
        |                                        |
        |<--- Accept or ERROR (setup) -----------|
        |                                        |
        |---- REQUEST_RESPONSE/STREAM/etc. ----->|
        |<--- PAYLOAD or ERROR ------------------|
        |                                        |
        |<---> KEEPALIVE (per policy) -----------|
        |                                        |
        |---- dispose/transport close ---------->|
```

### 3.1. Transport phase

RSocket runs over TCP, WebSocket, or compatible byte-stream transports. For TCP, a connection target might be:

```text
127.0.0.1:7000
```

For WebSocket, an endpoint has a URI, for example:

```text
ws://localhost:8080/rsocket
wss://gateway.example.com/rsocket
```

The transport must connect before RSocket frames can be exchanged. DNS, routing, firewall, TLS handshake, or WebSocket HTTP upgrade failures happen at this stage.

RSocket TCP and RSocket over WebSocket use the same request/response models at the protocol layer, though network paths, proxies, ports, TLS, and observability can differ.

### 3.2. `SETUP` frame

Once the transport is ready, the requester sends a `SETUP` frame with parameters. Key fields:

- Protocol version.
- `dataMimeType` and `metadataMimeType` used on the connection.
- Keepalive interval and max lifetime.
- Setup data and setup metadata (if any).
- Optional fields for lease/resume.

Metadata can carry routes or credentials to authenticate the connection. The server can accept or reject setup. If setup is rejected, opening the TCP socket does not imply every request will be valid.

### 3.3. After SETUP

Request streams are multiplexed over the connection. An error on one request stream may terminate only that stream, whereas a connection-level `ERROR` or transport disconnect can affect all active requests on the connection.

Therefore, when debugging, identify whether the failure is in **transport**, **connection SETUP**, **individual stream**, or **application handler**.

## 4. Creating a requester with `RSocketRequester.Builder`

Spring provides `org.springframework.messaging.rsocket.RSocketRequester`. When the RSocket starter is present, Spring Boot auto-configures `RSocketRequester.Builder` and codecs. The Builder is stateful and prototype-scoped so each injection point gets its own configuration.

### 4.1. TCP connection

```java
RSocketRequester requester = requesterBuilder
        .tcp("localhost", 7000);
```

This is the modern API in Spring Framework 5.3+ and 6.x. `tcp(...)` returns a requester; it **does not necessarily open a connection immediately**. When a request is actually subscribed, a shared connection is established on demand.

Example:

```java
Mono<String> greeting = requester.route("hello")
        .data("Mai")
        .retrieveMono(String.class);
```

An unsubscribed publisher offers no guarantee that the request was sent. In reactive services, `return greeting` or compose it into another pipeline; do not call `subscribe()` arbitrarily.

### 4.2. WebSocket connection

```java
URI endpoint = URI.create("ws://localhost:8080/rsocket");

RSocketRequester requester = requesterBuilder
        .websocket(endpoint);
```

The server must enable RSocket over WebSocket and configure a mapping path matching `/rsocket`. Do not confuse raw WebSocket with RSocket over WebSocket: both use the WebSocket transport, but the payloads here are RSocket frames, not plain JSON chat messages.

### 4.3. Avoid legacy API examples

Some Spring 5.2 guides use `connectTcp(...)` or `connectWebSocket(...)` returning `Mono<RSocketRequester>` and call `.block()`. With Spring Framework 6.1/6.2, prefer `tcp(...)` and `websocket(...)` as above. Do not mechanically copy old examples into Boot 3.x.

### 4.4. Reusing a requester

A requester created with `.tcp(...)` or `.websocket(...)` is designed to serve multiple concurrent requests over a shared connection. Instead of building a requester on every service call, keep one requester per endpoint and trust policy.

Example:

```java
@Service
public final class InventoryRequester {

    private final RSocketRequester requester;

    public InventoryRequester(RSocketRequester.Builder builder) {
        this.requester = builder.tcp("inventory.internal", 7000);
    }

    public Mono<String> status(String sku) {
        return requester.route("inventory.status")
                .data(sku)
                .retrieveMono(String.class);
    }

    @PreDestroy
    public void stop() {
        requester.dispose();
    }
}
```

The snippet illustrates a service with a known endpoint. `@PreDestroy` requires importing `jakarta.annotation.PreDestroy`. In production, move host/port into configuration rather than hardcoding.

## 5. Configuring MIME types, routes, and setup metadata

RSocket has two data regions:

1. **Data**: business payload, e.g. a JSON object.
2. **Metadata**: routing, authentication, or other context.

MIME types are negotiated in `SETUP` and affect codecs on both sides.

```java
RSocketRequester requester = builder
        .dataMimeType(MimeTypeUtils.APPLICATION_JSON)
        .tcp("localhost", 7000);
```

`MimeTypeUtils.APPLICATION_JSON` lives in `org.springframework.util`. If the client uses JSON, the server must have a matching codec. The Spring Boot starter provides Spring codec integration; when configuring manually outside Boot, you must set up `RSocketStrategies` yourself.

### 5.1. Per-request route

```java
Mono<Order> order = requester
        .route("orders.lookup")
        .data("order-42")
        .retrieveMono(Order.class);
```

The route is metadata used to locate `@MessageMapping` on the responder side. It is not an HTTP URL path, contains no scheme/host, and is not a TCP port.

### 5.2. Setup route

You can specify a setup route and setup data:

```java
RSocketRequester requester = builder
        .dataMimeType(MimeTypeUtils.APPLICATION_JSON)
        .setupRoute("client.connect")
        .setupData("client-app")
        .tcp("localhost", 7000);
```

The server can handle setup via `@ConnectMapping("client.connect")` and read the setup payload if the contract permits. If the server has no corresponding setup route, test how setup is handled; do not add setup routes arbitrarily.

### 5.3. Composite metadata

When multiple independent metadata entries are needed (route, JWT, or trace context), RSocket typically uses composite metadata. If configuring a custom metadata MIME type, ensure both sides agree on the format and Spring has matching encoders/decoders.

Do not log tokens or print setup metadata. If a token is attached at the connection level, define policies for token expiration and per-request authorization.

## 6. Configuring the server with Spring Boot

Spring Boot auto-configures the RSocket server when `spring-boot-starter-rsocket` and appropriate settings are present.

### 6.1. Standalone TCP

In `application.properties`:

```properties
spring.rsocket.server.port=7000
spring.rsocket.server.transport=tcp
```

The TCP server listens on a dedicated RSocket port. A WebFlux HTTP server is not needed just to run TCP RSocket.

### 6.2. WebSocket integrated into a WebFlux server

```properties
spring.rsocket.server.transport=websocket
spring.rsocket.server.mapping-path=/rsocket
server.port=8080
```

When the application is reactive WebFlux using Reactor Netty, RSocket over WebSocket can attach to the HTTP server. In this deployment style, you usually do **not** set a separate `spring.rsocket.server.port`, because the transport shares the HTTP server.

### 6.3. How do the two options differ?

| Criterion | TCP | WebSocket |
|---|---|---|
| Access method | `host:port` | `ws://` or `wss://` URI |
| Primary config | `spring.rsocket.server.port` | `transport=websocket`, `mapping-path` |
| HTTP reverse proxy integration | Needs TCP-capable proxy | Often straightforward via HTTP gateways supporting WebSocket upgrade |
| TLS | Per transport/TLS config | Can use WSS/TLS at server or ingress |
| Business handlers | `@MessageMapping` | `@MessageMapping` |

Do not choose WebSocket merely because another project has a WebSocket endpoint. RSocket over WebSocket is the RSocket protocol layered over WebSocket, not automatically compatible with clients sending arbitrary plain-text WebSocket messages.

## 7. Responders: `@MessageMapping` and `@ConnectMapping`

`RSocketMessageHandler` maps routes to annotated methods.

```java
@Controller
public class GreetingResponder {

    @MessageMapping("hello")
    public Mono<String> hello(String name) {
        return Mono.just("Xin chào, " + name);
    }
}
```

RSocket requester:

```java
requester.route("hello")
        .data("An")
        .retrieveMono(String.class);
```

### 7.1. Request-stream handler

```java
@MessageMapping("numbers")
public Flux<Integer> numbers(Integer count) {
    return Flux.range(1, count);
}
```

Client:

```java
Flux<Integer> numbers = requester.route("numbers")
        .data(3)
        .retrieveFlux(Integer.class);
```

For server streaming, subscriber demand is expressed via the protocol. However, a handler creating unbounded queues, calling `collectList()`, or using a producer without backpressure support can still accumulate large amounts of data in memory.

### 7.2. Request-channel handler

```java
@MessageMapping("upper")
public Flux<String> upper(Flux<String> words) {
    return words.map(word -> word.toUpperCase(Locale.ROOT));
}
```

Client sending a stream:

```java
Flux<String> result = requester.route("upper")
        .data(Flux.just("mot", "hai", "ba"), String.class)
        .retrieveFlux(String.class);
```

`java.util.Locale` is needed in this example. The channel producer must respect demand and complete its publisher when no more data remains.

### 7.3. `@ConnectMapping` handles only connection-level events

`@ConnectMapping` can handle the contents of a `SETUP` frame or `METADATA_PUSH`:

```java
@ConnectMapping("client.connect")
public Mono<Void> onConnect(String applicationName) {
    return validateClientApplication(applicationName);
}
```

`validateClientApplication` is an application service returning `Mono<Void>`; this code only illustrates the method contract, not a standalone class.

`@ConnectMapping` methods may only return `void` or an async type with cardinality 0 such as `Mono<Void>`. If setup handling emits an error, the connection may be rejected.

**Warning:** Do not block a `@ConnectMapping` handler by waiting for the connection being set up to send and complete a request back. Setup has not finished yet, which can create a dependency deadlock. If the requester needs to send requests right upon connection setup, decouple that asynchronously according to your architecture.

## 8. Connection lifecycle vs. request stream lifecycle

Distinguish the two timelines clearly.

### 8.1. Connection lifecycle

```text
NEW
  |
  v
TRANSPORT CONNECT
  |
  v
SETUP
  |
  v
ACTIVE
  |
  +---- multiple request streams
  |
  +---- KEEPALIVE
  |
  v
CLOSED / FAILED / DISPOSED
```

A connection can close due to:

- Client/server shutdown.
- Network disconnect.
- Keepalive timeout.
- Setup rejection.
- Protocol-level connection error.
- TLS/proxy transport failure.

### 8.2. Stream lifecycle

```text
REQUEST CREATED
     |
     v
SUBSCRIBED / SENT
     |
     +-- PAYLOAD(s) -> onNext
     |
     +-- onComplete
     |
     +-- onError
     |
     +-- CANCEL
```

A request-response stream returning a validation error does not necessarily close the entire connection. Conversely, losing the connection can cause multiple concurrent streams to error or cancel.

**Operational principle:** retrying a stream and reconnecting the transport are two distinct operations. A successful reconnect does not automatically restore every previously pending request.

## 9. Lazy shared connections and reconnection

With the modern `.tcp(...)` and `.websocket(...)` builder APIs, Spring constructs a requester backed by `RSocketClient`. When a request is created and subscribed, a shared connection is established on demand.

The Spring API specifies that the requester can share one connection for multiple concurrent requests, and when new requests are made, the connection can be re-established if the previous one is no longer active.

```java
RSocketRequester requester = builder.tcp("service", 7000);

Mono<String> call1 = requester.route("hello")
        .data("A")
        .retrieveMono(String.class);

Mono<String> call2 = requester.route("hello")
        .data("B")
        .retrieveMono(String.class);
```

Both publishers can share the same connection. They do not open a new connection for each request while the shared connection remains usable.

### 9.1. What happens when the server restarts?

Example:

1. The client sent request A over connection 1.
2. The server restarts before returning response A.
3. Request A may receive an error because the connection died.
4. When the client later sends request B, the requester can reopen a connection to handle B.
5. Request A is **not automatically replayed** just because B succeeded on a new connection.

To retry A, the application must decide based on request type and idempotency.

### 9.2. Do not confuse reconnect with resume

The RSocket protocol supports session resumption under specific conditions and implementations, but it must be configured appropriately on both sides. Do not assume an `RSocketRequester` using a shared connection has resume enabled, or that every in-flight stream survives a reconnect.

If a use case must guarantee receiving all data after a network drop, design cursors, checkpoints, event offsets, message IDs, or replay mechanisms at the application layer.

## 10. Keepalive and detecting dead connections

RSocket sends `KEEPALIVE` frames to detect an unresponsive peer. RSocket Java's `RSocketConnector.keepAlive(interval, maxLifeTime)` can be configured from Spring:

```java
RSocketRequester requester = builder
        .rsocketConnector(connector ->
                connector.keepAlive(
                        Duration.ofSeconds(20),
                        Duration.ofSeconds(90)))
        .tcp("localhost", 7000);
```

`interval` is the time between keepalive frames. `maxLifeTime` is the maximum duration without a valid signal from the remote peer before concluding the connection is dead per protocol rules.

In RSocket Java 1.1.5, the defaults are 20 seconds and 90 seconds. These are not fixed SLAs for every system; choose values according to network topology, load balancer idle timeouts, latency, and heartbeat overhead.

### 10.1. Do not set keepalive too aggressively

A 100 ms keepalive across hundreds of thousands of connections generates huge numbers of small frames and scheduling overhead. Conversely, too long a timeout delays detecting a lost peer.

Tuning considerations:

- Network RTT and jitter.
- Mobile clients, weak networks, NAT.
- Proxy/load balancer idle timeouts.
- Frame cost and connection count.
- Acceptable business wait timeout.

### 10.2. Keepalive is not a request timeout

A connection may be completely healthy while a single request waits 30 seconds on a database. Keepalive does not replace request timeouts. An individual request can time out due to SLA even while the connection stays healthy.

Example:

```java
Mono<String> reply = requester.route("hello")
        .data("An")
        .retrieveMono(String.class)
        .timeout(Duration.ofSeconds(2));
```

The timeout here applies to the request publisher; it does not configure connection-wide keepalive.

## 11. Managing lifecycle on application shutdown

`RSocketRequester` implements `Disposable`:

```java
requester.dispose();

boolean disposed = requester.isDisposed();
```

`dispose()` requests closing the underlying transport connection and notifies subscribers. When an application holds a long-lived requester, tie its lifecycle to a bean/container.

```java
@Configuration
public class RSocketClientConfig {

    @Bean(destroyMethod = "dispose")
    RSocketRequester pricingRequester(RSocketRequester.Builder builder) {
        return builder.tcp("pricing.internal", 7000);
    }
}
```

Spring invokes `dispose()` when the bean is destroyed. This shows bean lifecycle integration, not a requirement to create a new requester per call.

If managing a requester manually outside a Spring bean, use `@PreDestroy` or close it via a shutdown hook where the requester was created.

### 11.1. What happens after dispose?

After disposing, do not reuse the requester for new traffic. If you need to restart a client adapter, create a new requester with a new lifecycle; do not treat `dispose()` like a transient network blip that can be retried infinitely.

### 11.2. Canceling streams

In Reactor, a subscriber can cancel a request stream. Cancellation propagates through the publisher and, where the protocol allows, can emit a `CANCEL` frame. However, the responder may have already started side effects before receiving cancel; cancellation is not equivalent to a transaction rollback.

For services touching files or databases, review cancellation cleanup and transaction semantics separately.

## 12. Classifying RSocket errors by layer

Errors must be classified to choose the right response.

| Layer | Examples | Meaning |
|---|---|---|
| DNS/TCP/TLS/WebSocket | Unresolved host, refused, timeout, TLS handshake fail, WebSocket upgrade fail | Transport not ready |
| SETUP | `InvalidSetupException`, `RejectedSetupException`, `UnsupportedSetupException` | RSocket session / setup parameters rejected |
| Connection | `ConnectionErrorException`, `ConnectionCloseException` | Connection terminated |
| Request stream | `ApplicationErrorException`, `RejectedException`, `CanceledException`, `InvalidException` | A specific interaction failed |
| Payload codec | JSON/CBOR decode failure | Invalid body or codec MIME mismatch |
| Application | Domain rules, database, permissions, timeouts | Business or downstream infrastructure failure |
| Reactor | `TimeoutException`, cancellation, retry exhausted | Pipeline/client policy |

Some RSocket protocol exceptions reside in `io.rsocket.exceptions`; they represent corresponding wire error codes. Many transport errors can be wrapped by other exceptions; inspect the cause chain rather than matching only `getClass().getSimpleName()`.

### 12.1. `ApplicationErrorException`

The responder can send a stream-level RSocket `ERROR` frame when the handler emits `onError`. The requester receives a corresponding exception, typically `ApplicationErrorException`.

Do not assume native server Java exceptions are serialized verbatim to the client. The RSocket protocol carries an error code and error data/message; clients should rely on an explicit error contract if stable structure is needed.

### 12.2. `RejectedException` and `CanceledException`

Per RSocket semantics:

- `RejectedException`: the responder rejected a valid request and guarantees it has not processed that request.
- `CanceledException`: the responder canceled the request, though processing may have begun; no guarantee of zero side effects.

This distinction is crucial when deciding whether to retry operations with side effects.

### 12.3. Setup rejection is not an application 404

RSocket has no HTTP 404/500 statuses inside a TCP RSocket interaction. Missing routes or handler errors are expressed via RSocket protocol exceptions/errors; if the transport is WebSocket, HTTP status applies only during the HTTP upgrade phase, not as a response status for individual RSocket requests.

## 13. Client-side error handling: `onErrorMap`, `onErrorResume`, and logging

A reactive service can keep transport exceptions at the adapter boundary and map them to application exceptions.

```java
public Mono<String> getGreeting(String name) {
    return requester.route("hello")
            .data(name)
            .retrieveMono(String.class)
            .onErrorMap(
                    io.rsocket.exceptions.ApplicationErrorException.class,
                    error -> new RemoteBusinessException(
                            "Responder rejected greeting", error))
            .doOnError(error ->
                    logger.warn(
                            "RSocket greeting failed: type={}",
                            error.getClass().getSimpleName()));
}
```

`RemoteBusinessException` is a domain exception declared by the application. For retries/timeouts, preserving the original cause helps operations trace the root failure.

### 13.1. Fallback only when truly meaningful to business logic

```java
public Mono<String> optionalGreeting(String name) {
    return requester.route("hello")
            .data(name)
            .retrieveMono(String.class)
            .onErrorResume(
                    io.rsocket.exceptions.ApplicationErrorException.class,
                    error -> Mono.just("Temporarily unable to greet"));
}
```

A fallback is appropriate if the use case allows returning a substitute value. Never turn every connection error into "success" data if doing so causes callers to miss that an order was not processed.

### 13.2. Do not log raw metadata/payloads

RSocket setup/request metadata can contain tokens or session identifiers. Safe logs should include:

- Endpoint name, route.
- Sanitized connection/client ID.
- Error class and RSocket error code when available.
- Correlation/trace ID.
- Connect duration and request latency.
- Retry attempt count and reason.

Never log access tokens, full payloads, private keys, account details, or upstream stack traces into public responses.

## 14. Retry vs. reconnect

Reactor's `retryWhen(...)` works by re-subscribing to the source when the publisher emits `onError`. With RSocket, that can resend the *request*, not merely "recreate the socket."

```java
Mono<String> result = requester.route("hello")
        .data("An")
        .retrieveMono(String.class)
        .retryWhen(
                Retry.backoff(2, Duration.ofMillis(200))
                        .maxBackoff(Duration.ofSeconds(2)));
```

This example allows up to 2 retries after the initial attempt. It illustrates a retry-safe operation; do not apply it blindly to every route.

### 14.1. Why can retries cause duplicate side effects?

Consider the route:

```text
payments.charge
```

The client sends a payment request. The server records the transaction successfully, but the connection drops before the response arrives. The client sees a transport error and retries. The server could execute the payment a second time.

RSocket does not automatically guarantee exactly-once delivery or business-level deduplication. For non-idempotent operations, require:

- Client-generated idempotency keys.
- Server-side storage of processed results by key.
- Retries only when permitted by the contract.
- Bounded retry count with backoff and jitter.
- Overall deadline to prevent infinite retries.

### 14.2. Retry only selected transient errors

Intentional predicate example:

```java
Retry retryPolicy = Retry.backoff(3, Duration.ofMillis(200))
        .maxBackoff(Duration.ofSeconds(2))
        .filter(error ->
                error instanceof io.rsocket.exceptions.ConnectionErrorException
                || error instanceof java.net.ConnectException)
        .onRetryExhaustedThrow(
                (spec, signal) -> signal.failure());
```

This example filters specific errors. In practice, errors may be wrapped; write a utility to inspect the cause chain and test against your connector/version. Never retry `InvalidSetupException`, authentication failures, or application validation errors merely because they are also `RuntimeException` subclasses.

### 14.3. Retrying a stream can emit duplicate data

For Request-Stream:

```java
Flux<Event> events = requester.route("events")
        .data("room-1")
        .retrieveFlux(Event.class)
        .retryWhen(Retry.backoff(2, Duration.ofSeconds(1)));
```

If 100 events were received before the connection dropped, retrying typically restarts the stream from the beginning (depending on the route's contract), re-emitting those 100 events. Do not use bare stream retries if the application needs exactly-once ordering. You need server-side cursor/offset/checkpoint support and client-side event ID deduplication.

### 14.4. When not to retry?

- Setup rejected due to incompatible version/MIME.
- Invalid credentials or insufficient permissions.
- Domain validation errors.
- Route does not exist.
- Requests with side effects lacking idempotency.
- Overall deadline exceeded.
- Downstream is overloaded and retries would worsen the outage.

## 15. Timeouts, deadlines, and backpressure

### 15.1. `Mono.timeout` is a request-level deadline

```java
Mono<String> result = requester.route("hello")
        .data("An")
        .retrieveMono(String.class)
        .timeout(Duration.ofSeconds(3));
```

Timeout cancels the subscription when it does not finish within the requested duration. It does not prove the server has not executed side effects.

### 15.2. Total timeout with retries

```java
Mono<String> result = requester.route("hello")
        .data("An")
        .retrieveMono(String.class)
        .retryWhen(
                Retry.backoff(2, Duration.ofMillis(250)))
        .timeout(Duration.ofSeconds(5));
```

Place `timeout` after `retryWhen` to cap the entire retry chain. Placing `timeout` before retry has different semantics: each attempt can get its own timeout and then retry, extending total duration.

### 15.3. Backpressure across the network

In Request-Stream/Channel, RSocket carries demand signals via `REQUEST_N`. However:

- `Flux` helps only if the producer honors demand.
- Custom unbounded queues can still exhaust memory.
- Calling `collectList()` on a very long stream accumulates all data.
- Unbounded `flatMap` can inflate concurrent in-flight requests.
- Network-level backpressure does not replace payload and memory limits.

Example of a sequential consumer:

```java
Mono<Void> processing = requester.route("events")
        .data("room-1")
        .retrieveFlux(Event.class)
        .concatMap(eventService::process)
        .then();
```

For concurrent processing, use `flatMap(eventService::process, concurrency)` with a finite bound.

## 16. Responder-side error handling

A handler can return an error-emitting publisher:

```java
@MessageMapping("validate")
public Mono<String> validate(String input) {
    if (input == null || input.isBlank()) {
        return Mono.error(
                new IllegalArgumentException("value must not be blank"));
    }

    return Mono.just(input.toUpperCase(Locale.ROOT));
}
```

When a handler emits an error, RSocket can transmit an `ERROR` frame for that request stream. Other requests on the same connection are not necessarily affected.

### 16.1. Mapping errors with application meaning

Structured error results can be sent on the success path if client/server agree on the contract:

```java
public record OperationResult(
        boolean success,
        String code,
        String message) {
}
```

Do not return `Mono.just(OperationResult(false,...))` arbitrarily if the API contract treats it as a terminal error. Define clearly when to send an `ERROR` frame vs. when to return a domain result.

### 16.2. Connection-level errors

`@ConnectMapping` can reject `SETUP` by returning an error when validating connection identity or setup data fails. That differs from a `@MessageMapping` route returning a validation error on a request stream.

Never return stack traces, SQL, or private server details inside error payloads. If stable error codes are needed, define a versioned application error contract.

## 17. Session resumption, leasing, and fragmentation

The RSocket protocol includes advanced capabilities that should not be assumed enabled by default.

### 17.1. Resume

Session resumption supports resuming a session after disconnect when both sides negotiate it and retain appropriate state. Not every RSocket requester enables resume. Infrastructure needs memory/state and frame replay rules.

If an application needs data recovery after disconnects, consider designing application-layer checkpoints/replay even when using resume.

### 17.2. Lease

Leasing is a mechanism where the responder grants a request quota to the requester over time; the requester must respect the lease before sending more. Lease differs from per-stream Reactive Streams demand and from HTTP rate limits.

Enabling leasing without compatible server/client configuration can cause rejections or delayed requests. Enable it only with an explicit capacity management design.

### 17.3. Fragmentation

RSocket can fragment large payloads/frames for transport transmission. Fragmentation enables transporting large payloads, but does not mean the application can accept unbounded data without limits. Configure appropriate max inbound payload sizes, memory limits, concurrency, and codec limits.

`RSocketConnector.fragment(mtu)` is the connector-level API to configure fragmentation; the exact value must match server/transport capabilities.

## 18. Securing connections and metadata

RSocket connections can be long-lived; therefore authentication and authorization must be designed at both connection level and request level.

- Use TLS when connecting over untrusted networks.
- When running RSocket over WebSocket, use `wss://` and verify reverse proxies support WebSocket upgrades.
- With TCP transport, configure TLS at the transport or appropriate network layer.
- Setup metadata may carry connection credentials; never log secrets.
- Per-route permissions must still be checked.
- Tokens can expire while a connection remains open; define re-authentication or session termination policies.
- Limit connection counts, stream counts, payload sizes, and request rates.
- Never assume an open network-level connection authorizes every message.
- Never send passwords over unencrypted connections.

Spring Security supports RSocket authorization. In real deployments, test setup authentication, message authorization, and expired credentials.

## 19. Runnable Java 17+ project: RSocket over WebSocket

The example project combines Spring Boot 3.3.5, Spring WebFlux, RSocket starter, Jackson, and JUnit 5. Using the WebSocket transport lets tests start the server on a random port via `@SpringBootTest(webEnvironment = RANDOM_PORT)`, avoiding fixed TCP port conflicts.

**Routes demonstrated:**

- `hello`: Request-Response.
- `numbers`: Request-Stream.
- `upper`: Request-Channel.
- `reject`: Application error.
- `audit`: Fire-and-Forget.

### 19.1. Structure

```text
rsocket-connection-lifecycle/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/edu/demo/rsocket/
    │   │   ├── RSocketApplication.java
    │   │   └── DemoResponder.java
    │   └── resources/
    │       └── application.properties
    └── test/
        └── java/edu/demo/rsocket/
            └── RSocketLifecycleTests.java
```

### 19.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>edu.demo</groupId>
    <artifactId>rsocket-connection-lifecycle</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-rsocket</artifactId>
        </dependency>
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

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

`spring-boot-starter-rsocket` brings RSocket transport and Spring messaging support. `spring-boot-starter-webflux` creates the reactive HTTP server used to host RSocket over WebSocket.

### 19.3. `application.properties`

```properties
server.port=8080
spring.rsocket.server.transport=websocket
spring.rsocket.server.mapping-path=/rsocket
logging.level.io.rsocket=INFO
```

In production, do not enable DEBUG across all RSocket frames if metadata contains tokens or sensitive data. Here `INFO` is used to avoid logging payloads.

### 19.4. `RSocketApplication.java`

```java
package edu.demo.rsocket;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RSocketApplication {

    public static void main(String[] args) {
        SpringApplication.run(RSocketApplication.class, args);
    }
}
```

### 19.5. `DemoResponder.java`

```java
package edu.demo.rsocket;

import java.util.Locale;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.stereotype.Controller;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Controller
public class DemoResponder {

    private final AtomicInteger auditCount = new AtomicInteger();

    @MessageMapping("hello")
    public Mono<String> hello(String name) {
        return Mono.just("Xin chào, " + name);
    }

    @MessageMapping("numbers")
    public Flux<Integer> numbers(Integer count) {
        int safeCount = Math.max(0, Math.min(count, 10));
        return Flux.range(1, safeCount);
    }

    @MessageMapping("upper")
    public Flux<String> upper(Flux<String> words) {
        return words.map(word -> word.toUpperCase(Locale.ROOT));
    }

    @MessageMapping("reject")
    public Mono<String> reject(String input) {
        return Mono.error(
                new IllegalArgumentException("Rejected: " + input));
    }

    @MessageMapping("audit")
    public Mono<Void> audit(String event) {
        return Mono.fromRunnable(auditCount::incrementAndGet);
    }

    public int auditCount() {
        return auditCount.get();
    }
}
```

`auditCount` is for internal sample observation, not persistence. In real systems, Fire-and-Forget requires business-layer acknowledgment if data loss must be prevented.

### 19.6. `RSocketLifecycleTests.java`

```java
package edu.demo.rsocket;

import java.net.URI;
import java.time.Duration;

import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.TestInstance;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.messaging.rsocket.RSocketRequester;
import org.springframework.util.MimeTypeUtils;

import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@TestInstance(TestInstance.Lifecycle.PER_CLASS)
class RSocketLifecycleTests {

    @LocalServerPort
    int port;

    @Autowired
    RSocketRequester.Builder builder;

    private RSocketRequester requester;

    @BeforeAll
    void connect() {
        requester = builder
                .dataMimeType(MimeTypeUtils.APPLICATION_JSON)
                .rsocketConnector(connector ->
                        connector.keepAlive(
                                Duration.ofSeconds(20),
                                Duration.ofSeconds(90)))
                .websocket(URI.create(
                        "ws://localhost:" + port + "/rsocket"));
    }

    @AfterAll
    void close() {
        if (requester != null) {
            requester.dispose();
        }
    }

    @Test
    void requestResponseReturnsOneValue() {
        StepVerifier.create(
                        requester.route("hello")
                                .data("An")
                                .retrieveMono(String.class))
                .expectNext("Xin chào, An")
                .verifyComplete();
    }

    @Test
    void requestStreamRespectsDemandAndCompletes() {
        StepVerifier.create(
                        requester.route("numbers")
                                .data(3)
                                .retrieveFlux(Integer.class),
                        0)
                .thenRequest(1)
                .expectNext(1)
                .thenRequest(2)
                .expectNext(2, 3)
                .verifyComplete();
    }

    @Test
    void requestChannelTransformsSeveralMessages() {
        StepVerifier.create(
                        requester.route("upper")
                                .data(
                                        Flux.just("mot", "hai", "ba"),
                                        String.class)
                                .retrieveFlux(String.class))
                .expectNext("MOT", "HAI", "BA")
                .verifyComplete();
    }

    @Test
    void applicationErrorIsSignaledToRequester() {
        StepVerifier.create(
                        requester.route("reject")
                                .data("bad")
                                .retrieveMono(String.class))
                .expectError()
                .verify();
    }

    @Test
    void timeoutCancelsSlowPublisher() {
        StepVerifier.create(
                        Flux.never()
                                .timeout(Duration.ofMillis(100)))
                .expectError(java.util.concurrent.TimeoutException.class)
                .verify(Duration.ofSeconds(3));
    }
}
```

**Note on the last test:** testing `Flux.never().timeout(...)` checks Reactor's deadline semantics at the client layer; it does not claim the remote RSocket server was called. The first four tests are integration tests over real RSocket WebSocket.

The `@BeforeAll` hook builds the requester without forcing an immediate transport connection. When `StepVerifier` subscribes to the first request, the connection opens. Subsequent tests can share the connection; `@AfterAll` calls `dispose` to release resources.

### 19.7. Running Maven

From the directory containing `pom.xml`:

```bash
mvn test
```

Then you can run the server:

```bash
mvn spring-boot:run
```

RSocket over WebSocket endpoint:

```text
ws://localhost:8080/rsocket
```

To connect from another Java client:

```java
RSocketRequester requester = RSocketRequester.builder()
        .dataMimeType(MimeTypeUtils.APPLICATION_JSON)
        .websocket(URI.create("ws://localhost:8080/rsocket"));

requester.route("hello")
        .data("Mai")
        .retrieveMono(String.class)
        .doFinally(signal -> requester.dispose())
        .block(Duration.ofSeconds(5));
```

`block(Duration)` here is solely for a synchronous demo program or CLI/test boundary. In production WebFlux services, return the publisher and manage the requester via a Spring bean; never block the Netty event loop.

### 19.8. Expected results

Assertions verify:

1. Request-response returns `"Xin chào, An"`.
2. Request-stream emits `1, 2, 3` according to requested demand.
3. Request-channel uppercases three words.
4. `reject` emits a terminal error to the requester.
5. Reactor timeout emits `TimeoutException`.

A successful Maven run is expected to execute five tests with zero failures/errors/skips. This describes the expected result, not a claim that Maven was executed in the authoring environment.

### 19.9. Switching the sample to TCP

Change server configuration:

```properties
spring.rsocket.server.port=7000
spring.rsocket.server.transport=tcp
```

Update client:

```java
RSocketRequester requester = builder
        .dataMimeType(MimeTypeUtils.APPLICATION_JSON)
        .tcp("localhost", 7000);
```

When using a standalone TCP server, do not use the `/rsocket` URI. With WebSocket integrated into WebFlux, keep `mapping-path` and the matching WebSocket URI.

## 20. Observing connections and requests in production

A well-operated RSocket system needs metrics and logs at both connection and stream levels.

### 20.1. Useful measurements

| Metric | Meaning |
|---|---|
| Active connections | Number of currently open connections |
| Connection attempts/failures | DNS/TCP/TLS/setup failures |
| Setup rejection count | Connections rejected by server |
| Keepalive timeout | Peer may have lost connectivity |
| Request count by route/type | Workload volume |
| Request latency p50/p95/p99 | Latency per route |
| Application error rate | Handler failures |
| Stream cancellation | Canceled requests |
| Retry attempts/exhaustion | Retry pressure |
| In-flight streams | Concurrency level |
| Payload size/queue depth | Memory pressure |

### 20.2. Structured logging

Example logging a client error:

```java
requester.route("hello")
        .data("An")
        .retrieveMono(String.class)
        .doOnError(error ->
                logger.warn(
                        "rsocket route=hello failed type={}",
                        error.getClass().getSimpleName()));
```

In production, include correlation IDs and tracing, while avoiding sensitive tokens/metadata contents. For long-lived streams, attach an ID to the request stream and log complete/error/cancel lifecycle events.

### 20.3. Alert targets

- Sudden spike in setup failures.
- Frequent keepalive disconnects.
- Prolonged reconnect durations.
- Increasing retry exhaustion.
- Rising request latency and in-flight counts.
- Queue sizes exceeding thresholds.
- Application errors per route rising above baseline.

Do not monitor only TCP active connections. A healthy connection can still harbor thousands of slow streams or business errors.

## 21. Troubleshooting scenarios

### Scenario A: TCP refused

Symptom: client calls `.tcp("localhost", 7000)` and cannot connect.

Check:

1. Does the server have `spring.rsocket.server.port=7000`?
2. Is transport set to TCP?
3. Is the port listening?
4. Do the container/network namespace have the right host and port?
5. Is a firewall/NetworkPolicy blocking traffic?

Do not tweak retries to mask a static host/port misconfiguration.

### Scenario B: WebSocket upgrade failed

Symptom: connecting to `ws://.../rsocket` is rejected.

Check:

- Has the server enabled `transport=websocket` with the right mapping path?
- Is the WebFlux server running on Reactor Netty?
- Does the proxy forward WebSocket `Upgrade`/`Connection` headers?
- Is the URI properly `ws://` or `wss://`?
- Is any gateway route rewriting the path incorrectly?
- Are Origin/TLS/authentication on handshake valid?

### Scenario C: SETUP rejected

Symptom: transport connects, but the server rejects the RSocket session.

Check:

- Compatible protocol versions.
- Data/metadata MIME types.
- Setup route/metadata format.
- Setup credentials/authorization.
- Whether lease/resume options are supported by the server.

Retrying the exact same broken setup config rarely helps. Fix setup before reconnecting.

### Scenario D: Old request fails after restart

Symptom: call A before restart receives an error; call B after restart succeeds.

This can be normal behavior: the requester creates a new shared connection for request B, while in-flight request A is not automatically replayed. If A must complete, design application-level retries with idempotency and duplicate checks.

### Scenario E: Stream duplicates after retry

Symptom: the first 100 events appear again.

Retrying `retrieveFlux` may re-subscribe from the start of the source. Use event IDs, cursors/offsets, and deduplication rather than `.retryWhen(...)` alone.

### Scenario F: Frequent keepalive timeouts

Check:

- Network jitter and RTT.
- Proxy/load balancer idle timeouts.
- Blocked event loop.
- JVM GC pauses.
- Overly tight `interval` and `maxLifeTime` values.
- Connection counts exceeding server capacity.

Do not set an ultra-low interval to "fix" timeouts; measure the network and event loop first.

## 22. Common pitfalls

| Mistake | Consequence | Fix |
|---|---|---|
| Using Spring 5.2 `connectTcp().block()` in Spring 6 code | Compilation errors or unnecessary blocking | Use `tcp(...)`/`websocket(...)` |
| Creating a new requester per call | Opens many connections, hard to clean up | Reuse long-lived requester per endpoint |
| Forgetting to subscribe/return publisher | Request never executes | Return/compose `Mono`, `Flux` |
| Calling `.subscribe()` directly inside a service | Errors/cancels escape lifecycle | Keep reactive composition |
| Confusing SETUP with individual requests | Error handling at wrong layer | Separate connection-level and stream-level |
| Assuming reconnect replays in-flight requests | Lost requests/uncertain side effects | App-level idempotency/replay |
| Retrying every exception | Repeats config, auth, validation failures | Select transient errors |
| Retrying non-idempotent POST-like business operations | Duplicate side effects | Idempotency keys |
| Retrying streams without offsets | Duplicate data received | Cursors/checkpoints/dedup |
| Leaving request timeouts unbounded | Streams can hang waiting indefinitely | Explicit deadlines |
| Using keepalive alone to enforce SLAs | Slow requests go undetected properly | Per-request timeouts |
| Setting keepalive too frequently | High frame/scheduling overhead | Tune to topology |
| Forgetting `dispose()` | Connection leaks on shutdown | Bean `destroyMethod`/`@PreDestroy` |
| Reusing a disposed requester | New requests fail | Create a new lifecycle requester |
| Confusing RSocket WebSocket with raw WebSocket | Client cannot understand frames | Use an RSocket-aware client |
| Logging setup metadata containing tokens | Credential leaks | Mask secrets, log metadata safely |
| Leaving payloads/streams unbounded | Memory/resource pressure | Size, concurrency, lease/quota limits |
| Treating cancel as rollback | Side effects already started may still commit | Transactions/idempotency |
| Assuming resume is enabled by default | Misunderstands disconnect behavior | Configure properly or use app replay |
| Monitoring only active connections | Misses request failures/latency | Metrics per connection and route |

## 23. Checklist before taking RSocket to production

### Connection setup

- Has TCP or WebSocket transport been chosen properly?
- Do host, port, or WebSocket URI match the deployment?
- Are TLS, truststores, proxies, and ingress configured where needed?
- Do client and server agree on `SETUP` MIME types?
- Are required setup metadata/routes defined?
- Is connection-level authentication secure?

### Lifecycle

- Is the requester reused across multiple calls?
- Is there a shutdown lifecycle to dispose the requester?
- On connection loss, are new requests distinguished from in-flight requests?
- Does keepalive match network idle timeouts and RTT?
- Are connection failures and reconnect latencies monitored?
- Are manual `.subscribe()` calls avoided in adapters/services?

### Error handling

- Are transport, setup, connection, stream, codec, and domain errors distinguished?
- Are retries avoided for permanent errors?
- Do retries have max attempts, backoff, jitter, and deadlines?
- Do routes with side effects have idempotency keys?
- Do stream retries use checkpoints/offsets/dedup where needed?
- Do logs/traces omit payloads and credentials?
- Are fallbacks business-appropriate, or are failures propagated?

### Capacity and security

- Are connection counts and in-flight streams bounded?
- Are payload size limits enforced?
- Is route-level authorization enforced?
- Is there a token expiry/re-authentication policy for long-lived connections?
- Are backpressure and queue limits enforced?
- Have load, disconnects, restarts, timeouts, and slow consumers been tested?

### Testing

- Test all four interaction models as needed.
- Test setup failures and unsupported MIME types.
- Test handler application errors.
- Test timeouts and cancellation.
- Test lost connections + new requests.
- Test zero duplicate side effects on retry.
- Test shutdown resource cleanup.
- Test WebSocket upgrade through gateways when deployed behind proxies.

## 24. Self-check exercises

**Exercise 1.** Does `RSocketRequester.Builder.tcp(...)` always open a TCP connection immediately?

**Answer:** No. The modern API builds a requester that connects on demand when a request is subscribed. Requests can share the connection.

**Exercise 2.** What key information does RSocket `SETUP` contain?

**Answer:** Protocol version, data/metadata MIME types, keepalive settings, optional setup data/metadata, and lease/resume options.

**Exercise 3.** How does `@ConnectMapping` differ from `@MessageMapping`?

**Answer:** `@ConnectMapping` handles connection-level `SETUP`/`METADATA_PUSH` without returning response data; `@MessageMapping` handles individual request routes.

**Exercise 4.** The server restarts, request A fails, and subsequent request B succeeds. Is this contradictory?

**Answer:** No. The new request can establish a new shared connection, while the lost in-flight request is not automatically replayed.

**Exercise 5.** When is `RSocketRequester.dispose()` used?

**Answer:** When the client adapter/app shuts down or no longer needs the requester. Never reuse a disposed requester.

**Exercise 6.** Does `KEEPALIVE` replace `Mono.timeout` for requests?

**Answer:** No. Keepalive monitors the connection, whereas request timeout bounds the response time of an individual operation.

**Exercise 7.** What is the key difference between `RejectedException` and `CanceledException`?

**Answer:** `Rejected` guarantees the responder has not processed the request; `Canceled` may occur after side effects have started. Retries must respect these semantics.

**Exercise 8.** Why can retrying a Request-Stream cause duplicate events?

**Answer:** Retrying re-subscribes to the publisher and can restart the stream from the beginning per the route's contract. Cursors, event IDs, checkpoints/dedup are needed.

**Exercise 9.** Can `@MessageMapping` handle RSocket over WebSocket?

**Answer:** Yes. RSocket interaction models and handlers remain the same; only transport and endpoint configuration change.

**Exercise 10.** What must be done to ensure a payment is not processed twice if the connection drops right after commit?

**Answer:** Use an idempotency key stored and enforced by the server, paired with a retry policy aligned with the business contract. Reconnect/keepalive do not provide exactly-once guarantees.

## 25. Key takeaways

- RSocket supports Request-Response, Request-Stream, Channel, and Fire-and-Forget.
- Connections are established via transport + `SETUP`; request streams run over a shared connection.
- `RSocketRequester.Builder.tcp(...)` and `.websocket(...)` are the right APIs for Spring Framework 6.x, connecting on demand.
- `SETUP` carries MIME types, keepalive, and optional metadata. `@ConnectMapping` can inspect setup and reject connections.
- A stream-level `ERROR` does not mean the whole connection died.
- Connection loss can fail in-flight requests; new requests can open a new connection, while old requests do not replay automatically.
- `dispose()` manages requester lifecycle at shutdown.
- `KEEPALIVE` checks the peer; `Mono.timeout` enforces per-operation deadlines.
- Classify transport/setup/connection/stream/codec/application errors before deciding to retry.
- Retrying re-subscribes to the publisher, potentially resending requests and duplicating side effects or stream events.
- Idempotency, event cursors, and deduplication must be solved per the business contract.
- Resume, leasing, and fragmentation are advanced features requiring configuration and testing, not enabled by default.
- Long-lived connections need security, metrics, payload limits, concurrency limits, and graceful cleanup.

**Quick rule of thumb:** **Can the connection re-establish? Did the old request actually finish? Is retrying safe?** These are the three separate questions you must answer when designing a resilient RSocket application.

## Official documentation and further reading

- Spring Framework — RSocket Overview, `RSocketRequester`, Connection Setup and Annotated Responders: https://docs.spring.io/spring-framework/reference/rsocket.html
- Spring Framework 6.1 — `RSocketRequester.Builder` Javadoc: https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/messaging/rsocket/RSocketRequester.Builder.html
- Spring Framework 6.2 — `RSocketRequester` Javadoc and `dispose()` lifecycle: https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/messaging/rsocket/RSocketRequester.html
- Spring Boot 3.3 — RSocket messaging/auto-configuration: https://docs.spring.io/spring-boot/3.3/reference/messaging/rsocket.html
- RSocket Java 1.1.5 — `RSocketConnector`/keepalive API: https://javadoc.io/static/io.rsocket/rsocket-core/1.1.5/io/rsocket/core/RSocketConnector.html
- RSocket Java 1.1.5 — Protocol exception classes: https://javadoc.io/static/io.rsocket/rsocket-core/1.1.5/io/rsocket/exceptions/package-summary.html
- RSocket Protocol Specification: https://rsocket.io/about/protocol/
- Project Reactor — Error Handling and Retry: https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html