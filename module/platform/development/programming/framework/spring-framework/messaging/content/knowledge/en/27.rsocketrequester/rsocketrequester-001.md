# Creating RSocketRequester.Builder and Configuring Connections

`RSocketRequester` is Spring's fluent API for sending RSocket requests using Java objects and receiving results as a `Mono` or `Flux`. On the client side, `RSocketRequester.builder()` creates a builder to configure the connection, `SETUP` frame, MIME types, codecs, and transport. After calling `tcp(...)` or `websocket(...)`, you receive an `RSocketRequester` that can be reused for multiple requests over the same connection.

This lesson focuses on creating a client requester with Spring Framework 6.x. RSocket is a bidirectional application protocol that supports multiple interaction models and can run over TCP or WebSocket.

## 1. RSocketRequester and Connection Lifecycle

RSocket is an application protocol for bidirectional (duplex), multiplexed communication over a single connection. Once the connection is established, either side can send requests; the concepts of client and server only describe the role in a specific request.

RSocket supports four main interaction models:

| Model | Meaning | Typical result |
|---|---|---|
| Request-Response | Send one message and receive one reply message | `Mono<T>` |
| Request-Stream | Send one request and receive a stream of messages | `Flux<T>` |
| Fire-and-Forget | Send a one-way message without waiting for a response | `Mono<Void>` signaling send completion |
| Request-Channel | Send a request stream and receive a response stream | Bidirectional `Flux<T>` |

For streams, RSocket uses Reactive Streams demand and backpressure so the requester can regulate the rate at which the responder emits data. This is one difference compared to simply sending multiple independent HTTP requests.

`RSocketRequester` hides most low-level operations with `io.rsocket.Payload`, `ByteBuf`, or `DataBuffer`. Applications work with Java objects, routes, and metadata through a higher-level API.

## 2. Creating a Requester with TCP or WebSocket

The simplest way is to call the static factory `RSocketRequester.builder()` and then choose a transport:

~~~java
import java.net.URI;
import org.springframework.messaging.rsocket.RSocketRequester;

RSocketRequester tcpRequester =
        RSocketRequester.builder().tcp("localhost", 7000);

RSocketRequester websocketRequester =
        RSocketRequester.builder().websocket(
                URI.create("ws://localhost:8080/rsocket"));
~~~

The two requester creation methods differ in transport:

- `tcp(host, port)` connects to an RSocket server listening on the corresponding TCP host and port.
- `websocket(uri)` connects to an RSocket endpoint exposed over WebSocket. The URI typically uses `ws://` or `wss://`.
- `transport(ClientTransport)` lets you pass an already initialized `ClientTransport` if a custom transport is needed.

The endpoint and transport must match how the server is configured. For example, a TCP server must listen on the exact port; a WebSocket server must expose the exact path `/rsocket`. A regular REST URL does not automatically become an RSocket endpoint just because it uses the HTTP port.

### When Is the Connection Created?

`tcp(...)` and `websocket(...)` return an `RSocketRequester`; they do not force the application to open a connection immediately when the object is created. The connection is established when the first request is subscribed to and needs to be sent. Subsequent requests can share the connection; the requester supports multiple concurrent requests and the connection can be re-established when a subsequent request runs after a previous connection is lost.

Example:

~~~java
RSocketRequester requester =
        RSocketRequester.builder().tcp("localhost", 7000);

// No request has been subscribed at this point.
Mono<Product> productMono = requester.route("catalog.find")
        .data("SKU-42")
        .retrieveMono(Product.class);

// The connection is used when the publisher is subscribed.
productMono.subscribe(
        product -> System.out.println(product.name()),
        error -> System.err.println("RSocket request failed: " + error.getMessage()));
~~~

Do not call `block()` on the WebFlux event loop or inside a reactive handler. If the application is using reactive end-to-end, return the `Mono`/`Flux` for the framework to subscribe to. `block(Duration)` is only suitable at imperative boundaries such as command-line programs or startup code that intentionally waits for a result.

### Current API Names

Use `tcp(host, port)` and `websocket(uri)` in Spring Framework 6.x. The older methods `connectTcp(...)` and `connectWebSocket(...)` have been deprecated since Spring Framework 5.3 in favor of the API that returns `RSocketRequester` directly.

## 3. Configuring RSocketRequester.Builder

The builder lets you configure the following before creating a requester:

| Method | Role |
|---|---|
| `dataMimeType(MimeType)` | MIME type for data on the connection, declared in `SETUP` |
| `metadataMimeType(MimeType)` | MIME type for metadata on the connection |
| `rsocketStrategies(...)` | Encoders, decoders, and strategies for handling routes/metadata |
| `setupData(Object)` | Optional data sent in `SETUP` |
| `setupRoute(String, Object...)` | Optional route attached to `SETUP` |
| `setupMetadata(Object, MimeType)` | Optional metadata attached to `SETUP` |
| `rsocketConnector(...)` | Directly customize the underlying `RSocketConnector` |

Example configuring JSON and a TCP connection:

~~~java
package com.example.rsocket;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.codec.json.Jackson2JsonDecoder;
import org.springframework.http.codec.json.Jackson2JsonEncoder;
import org.springframework.messaging.rsocket.RSocketRequester;
import org.springframework.messaging.rsocket.RSocketStrategies;
import org.springframework.util.MimeTypeUtils;

@Configuration
public class RSocketClientConfiguration {

    @Bean
    public RSocketStrategies rsocketStrategies() {
        return RSocketStrategies.builder()
                .encoders(encoders -> encoders.add(new Jackson2JsonEncoder()))
                .decoders(decoders -> decoders.add(new Jackson2JsonDecoder()))
                .build();
    }

    @Bean(destroyMethod = "dispose")
    public RSocketRequester catalogRequester(RSocketStrategies strategies) {
        return RSocketRequester.builder()
                .dataMimeType(MimeTypeUtils.APPLICATION_JSON)
                .rsocketStrategies(strategies)
                .tcp("localhost", 7000);
    }
}
~~~

The example assumes the application has compatible dependencies for Spring Messaging, Spring Web/codecs, Jackson, and RSocket TCP transport. The server side must support the same data MIME type and the routes called by the client.

`@Bean(destroyMethod = "dispose")` tells Spring to dispose of the requester when the application context stops. If a requester is created outside the Spring container, the application must manage its lifecycle itself and call `dispose()` when the connection is no longer in use.

## 4. RSocketStrategies and Data Conversion

`RSocketStrategies` groups the components Spring uses to encode and decode data/metadata. The builder receives strategies via `rsocketStrategies(...)`.

By default, basic codecs from `spring-core` support `String`, `byte[]`, and `ByteBuffer`. When you need to exchange DTOs, JSON, CBOR, or other formats, register the corresponding encoder/decoder. Spring's JSON/CBOR codecs reside in `spring-web`; the JSON format also requires Jackson on the classpath.

Example:

~~~java
RSocketStrategies strategies = RSocketStrategies.builder()
        .encoders(encoders -> encoders.add(new Jackson2JsonEncoder()))
        .decoders(decoders -> decoders.add(new Jackson2JsonDecoder()))
        .build();
~~~

An encoder converts outgoing objects into data bytes; a decoder converts received data into the target object. Both sides must agree on the MIME type and payload format. Adding a decoder only on the client does not automatically make the server understand that format.

`dataMimeType(...)` declares the connection-level data MIME type via `SETUP`. If not explicitly set, Spring infers it from the configured decoders, preferring the first non-default decoder. When an application exchanges JSON, it is good practice to declare `application/json` explicitly so the contract between both ends is easy to read and avoids depending on codec ordering.

`RSocketStrategies` can be reused between client and server in the same application, provided the set of codecs and route matcher fit both roles. There is no need to create a new strategies instance for each request.

## 5. Data MIME Type and Metadata MIME Type

Each RSocket message can contain data, metadata, or both. The two parts can use different formats:

- Data typically contains the business payload, such as a DTO, string, or byte array.
- Metadata typically contains the route, authentication tokens, tracing information, or control information.
- The MIME types for data and metadata are declared in `SETUP` and apply to the connection.

`dataMimeType(...)` determines how data is encoded/decoded. `metadataMimeType(...)` determines how metadata is interpreted.

By default, Spring uses the composite metadata MIME type `message/x.rsocket.composite-metadata.v0`. Composite metadata allows a single metadata payload to contain multiple independent entries, each with its own MIME type. This is the right choice when a request needs routing metadata alongside authentication or tracing metadata.

Normally there is no need to change `metadataMimeType(...)`. If you replace it with a single MIME type, the application and server must agree on the new format; any provided route is also encoded according to that MIME type. Do not change the metadata MIME type just because you want to change the JSON data MIME type: the two settings serve separate purposes.

## 6. Configuring the SETUP Frame

After the transport is opened, the client sends an RSocket `SETUP` frame to initialize the connection. The builder lets you add data, route, and metadata to this frame:

~~~java
RSocketRequester requester = RSocketRequester.builder()
        .dataMimeType(MimeTypeUtils.APPLICATION_JSON)
        .setupRoute("client.connect")
        .setupData(new ClientInfo("inventory-worker", "1.0"))
        .setupMetadata(
                "tenant-42",
                MimeType.valueOf("message/x.example.tenant.v1"))
        .rsocketStrategies(strategies)
        .tcp("localhost", 7000);
~~~

In the example:

- `setupRoute(...)` attaches a route to the connection establishment event.
- `setupData(...)` adds a data object to the `SETUP` payload.
- `setupMetadata(...)` adds metadata with its own MIME type.
- `dataMimeType(...)` determines how `setupData` is encoded.
- `metadataMimeType(...)` remains composite metadata by default, allowing the route and metadata entries to coexist.

Both data and metadata in `SETUP` are optional. The server can handle this content using `@ConnectMapping`. The route in `SETUP` is used to route the connection event handler; it does not replace the route of individual requests created with `requester.route(...)`.

If you call `setupMetadata(...)` multiple times or combine it with `setupRoute(...)`, composite metadata must be used. The server must also support the corresponding decoder/metadata extractor. Do not send a metadata type that the server has not registered to handle.

### SETUP Metadata vs. Request Metadata

`setupMetadata(...)` applies to connection establishment. If you need to send per-request metadata, use `metadata(value, mimeType)` on the request spec:

~~~java
MimeType tokenMimeType =
        MimeType.valueOf("message/x.rsocket.authentication.bearer.v0");

Mono<Account> accountMono = requester.route("accounts.current")
        .metadata(accessToken, tokenMimeType)
        .retrieveMono(Account.class);
~~~

The example above requires the server to have an authentication mechanism and decoder matching the bearer metadata. Do not put tokens in the route or business payload. In production environments, protect the transport with TLS (for example `wss://` or a TLS-enabled TCP transport) and enforce authentication/authorization on the server.

## 7. Customizing RSocketConnector and Transport

The builder provides `rsocketConnector(...)` to configure the underlying `io.rsocket.core.RSocketConnector`. This is the extension point for protocol-level settings such as keepalive, session resumption, interceptors, and client-side acceptors.

~~~java
RSocketRequester requester = RSocketRequester.builder()
        .rsocketConnector(connector -> {
            // Configure keepalive, resumption, or interceptors
            // according to the RSocket Java version used by the application.
        })
        .tcp("localhost", 7000);
~~~

Do not set keepalive parameters arbitrarily. They must align with network timeouts, proxies, server capabilities, and operational requirements. RSocket keepalive is a protocol-level mechanism; it is not a business message and does not replace per-request timeouts.

If the transport is not the default TCP or WebSocket, instantiate the corresponding `ClientTransport` and pass it to `transport(...)`. This is useful when you need to configure TLS, network addresses, event loops, or specialized transports. Ensure that client and server use compatible transports.

The builder also supports `transports(...)` with a list of load-balancing targets and a strategy. Only use this API when the application has multiple RSocket server targets and a defined target selection policy; for a single endpoint, `tcp(...)` or `websocket(...)` is simpler.

## 8. Using the Requester After Configuration

Once you have an `RSocketRequester`, each request starts with a route. A route is metadata used to locate a responder on the server; a route is not an HTTP URL path.

Request-response example:

~~~java
Mono<Product> productMono = requester.route("catalog.find")
        .data("SKU-42")
        .retrieveMono(Product.class);
~~~

Request-stream example:

~~~java
Flux<Product> products = requester.route("catalog.search")
        .data(new ProductSearch("keyboard"))
        .retrieveFlux(Product.class);
~~~

Fire-and-forget example:

~~~java
Mono<Void> sent = requester.route("audit.record")
        .data(new AuditEvent("user-17", "viewed-catalog"))
        .send();
~~~

`send()` only signals that sending the message has completed on the client side; it does not prove that the server has successfully processed the business logic. If you need a response or business acknowledgement, use request-response or a dedicated acknowledgement protocol.

For requests that do not need data, you can omit `.data(...)`:

~~~java
Mono<SystemStatus> status = requester.route("system.status")
        .retrieveMono(SystemStatus.class);
~~~

These methods return a Reactor `Mono`/`Flux`, so the request is only actually executed when the publisher is subscribed. Connect the publisher into a reactive pipeline, or subscribe at an imperative boundary with explicit error handling.

## 9. Connection Management, Errors, and Reuse

A requester created from `tcp(...)` or `websocket(...)` can be used for multiple concurrent requests over a shared connection. Do not create a new requester for every service call if the endpoint and connection configuration are the same.

Operational points to note:

- Create the requester once at application scope if the endpoint and configuration do not change.
- Use `dispose()` when the requester is no longer needed; for Spring beans, you can declare `destroyMethod = "dispose"`.
- Monitor errors in the reactive chain because DNS, connection refused, handshake, `SETUP`, timeout, or decoding errors can surface when the publisher is subscribed.
- Configure appropriate timeouts and keepalive at the transport/connector layer; do not assume a default timeout for all requests.
- If retrying requests, consider idempotency. Retrying after a network error can leave the application uncertain whether the server already processed the request before the connection dropped.
- Do not treat a successfully established connection as proof that every route exists or is authorized.

The requester can re-establish the connection when the next request needs it after a previous connection was lost. That does not mean an in-flight failing request will automatically be safely retried. Retry policies and business state recovery remain the application's responsibility.

## 10. Common Errors and How to Handle Them

| Symptom | Common cause | How to check or fix |
|---|---|---|
| Connection refused | Server is not listening on the right host/port or transport mismatch | Check the RSocket server, TCP port, and network configuration. |
| WebSocket handshake fails | Wrong scheme, host, port, or endpoint path | Check the ws/wss URI and the path exposed by the RSocket server. |
| Server cannot decode DTO | Missing encoder/decoder or mismatched data MIME type | Configure RSocketStrategies on both ends and check dataMimeType. |
| Route cannot find responder | Wrong route or server has not registered the corresponding handler | Compare requester.route(...) with the responder's route. |
| Server cannot read setup metadata | Incompatible MIME type or metadata extractor | Use composite metadata when multiple entries are needed and register a server-side decoder. |
| setupRoute confused with request route | The two routes have different lifecycles | setupRoute belongs to the SETUP frame; requester.route belongs to each request. |
| Calling block() stalls reactive thread | Blocking the event loop or a reactive processing thread | Return Mono/Flux or only block at a controlled imperative boundary. |
| Using requester after dispose | Connection was closed according to the application lifecycle | Manage the requester by application lifecycle and do not retain references after shutdown. |
| Retries cause duplicate processing | Unknown whether the previous request was processed by the server before the connection error | Use a request id/idempotency key and design safe idempotent processing. |
| Token metadata rejected | Server has not enabled or configured the corresponding metadata authentication mechanism | Check RSocket Security, MIME type, metadata extractor, and TLS. |

## 11. Connection Configuration Checklist

Before bringing an RSocket client into production, verify:

1. Dependencies include spring-messaging, the appropriate RSocket Java transport, and required codecs.
2. The server exposes TCP or WebSocket matching the transport chosen by the client.
3. Host, port, URI, and endpoint path are accurate.
4. dataMimeType and metadataMimeType are consistent with the server.
5. RSocketStrategies has encoders/decoders for every payload object exchanged.
6. setupData, setupRoute, and setupMetadata are only used when the server needs to handle SETUP.
7. Request routes match the routes registered by server responders.
8. Connections are reused and disposed according to the application lifecycle.
9. Timeouts, keepalive, TLS, authentication, and retries are configured according to system requirements.
10. Integration tests cover successful connection, valid routes, mismatched MIME types, transport errors, and closing the connection.

## References

- [Spring Framework Reference — RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html): protocol overview, transports, `RSocketRequester`, client requester, SETUP, strategies, and interaction types.
- [Spring Framework 6.1.21 Javadoc — RSocketRequester.Builder](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/messaging/rsocket/RSocketRequester.Builder.html): APIs for `tcp`, `websocket`, `transport`, `dataMimeType`, `metadataMimeType`, `setupData`, `setupRoute`, `setupMetadata`, and `rsocketStrategies`.
- [Spring Framework 6.1.21 Javadoc — RSocketRequester](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/messaging/rsocket/RSocketRequester.html): `builder()`, `route(...)`, `dispose()`, and requester API.
- [Spring Framework 6.1 — RSocket](https://docs.spring.io/spring-framework/reference/6.1/rsocket.html): 6.1 branch documentation on client connections and requester configuration.
- [RSocket Protocol](https://rsocket.io/about/protocol/): SETUP frames, request interactions, metadata, and transport-independent behavior.
