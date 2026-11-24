# RSocketRequester, RSocketStrategies, and Codecs in Spring Framework Reactive

RSocket is a bidirectional communication protocol over TCP, WebSocket, or another suitable transport, providing four interaction models: request-response, request-stream, fire-and-forget, and request-channel. Spring Framework adds abstractions so applications exchange objects and reactive streams without directly manipulating byte buffers or RSocket frames.

Three core concepts of this lesson:

- **RSocketRequester**: a fluent API for selecting a route, sending data/metadata, and receiving `Mono`/`Flux` results.
- **RSocketStrategies**: shared configuration for encoders, decoders, route matcher, metadata extractor, buffer factory, and reactive adapters.
- **Codec**: encoder/decoder converting between Java objects and payload bytes based on data type and MIME type.

Understanding them prevents common errors: a client having only a String codec while sending a DTO; SETUP declaring `application/json` while the server only understands CBOR; a route missing from the proper metadata; or fire-and-forget being mistaken for business confirmation.

This lesson belongs to the RSocket group of the Spring Framework - reactive module, using Java 17+ and Spring Boot 3.3.5 as practical examples.

## 1. Learning Objectives

After this lesson, you will be able to:

- Distinguish RSocket from HTTP and regular WebSocket transports.
- Understand the four interaction models and corresponding `RSocketRequester` APIs.
- Create a requester for TCP or WebSocket, and manage lifecycle and shared connections.
- Understand the `SETUP` frame, data MIME type, and metadata MIME type.
- Send routes, setup metadata, and per-request metadata.
- Distinguish `retrieveMono()`, `retrieveFlux()`, `send()`, and `sendMetadata()`.
- Understand the role of encoders/decoders inside `RSocketStrategies`.
- Use JSON or CBOR codecs consistently across both sides.
- Customize strategies using the builder or `RSocketStrategiesCustomizer`.
- Handle route matching, composite metadata, and custom metadata extraction.
- Choose type hints for `Publisher` and `ParameterizedTypeReference` for generic types.
- Bound timeouts, retries, and backpressure according to the interaction model.
- Write a runnable `@MessageMapping` responder and `RSocketRequester` client.
- Test all four interaction types over real TCP RSocket.

## 2. RSocket Mechanism and the Four Interaction Models

An RSocket connection begins with a `SETUP` frame. Afterward, either side can initiate interactions across multiple concurrent logical streams.

~~~text
Requester                                 Responder
    |                                         |
    |---------- TCP/WebSocket ---------------|
    |--------------- SETUP ------------------>|
    |                                         |
    |----------- REQUEST_RESPONSE ---------->|
    |<-------------- PAYLOAD ----------------|
    |                                         |
    |----------- REQUEST_STREAM ------------>|
    |<-------------- PAYLOAD ----------------|
    |<-------------- PAYLOAD ----------------|
    |---------------- REQUEST_N ------------>|
    |<-------------- PAYLOAD ----------------|
    |                                         |
    |----------- REQUEST_CHANNEL ----------->|
    |---------------- PAYLOAD --------------->|
    |<-------------- PAYLOAD ----------------|
    |                                         |
    |------------ REQUEST_FNF --------------->|
    |                                         |
~~~

RSocket propagates demand via `REQUEST_N` for streams requiring backpressure. This is protocol-layer semantics, not merely logic inside one Java process.

| Interaction | Request data | Response data | RSocketRequester |
| --- | --- | --- | --- |
| Request-Response | One message | One message | retrieveMono(Class) |
| Request-Stream | One message | Many messages | retrieveFlux(Class) |
| Fire-and-Forget | One message | No business response | send() |
| Request-Channel | Many messages | Many messages | data(Flux, Class).retrieveFlux(Class) |

RSocket does not replace every HTTP API. It is useful for real-time feeds, long-lived streams, bidirectional interactions, and connections carrying multiple logical streams. HTTP remains well suited for REST, caching, standard request-response, and broad web infrastructure.

## 3. What abstraction is RSocketRequester?

`RSocketRequester` sits on top of RSocket Java's `io.rsocket.RSocket`. The low-level API works with `Payload` and buffers. `RSocketRequester` accepts Java objects, encodes them using codecs, attaches routes/metadata, and returns `Mono` or `Flux`.

~~~java
Mono<GreetingReply> reply = requester.route("greet")
    .data(new GreetingRequest("Lan"))
    .retrieveMono(GreetingReply.class);
~~~

Here:

1. `route("greet")` builds routing metadata.
2. `data(...)` declares the object to encode into a payload.
3. `retrieveMono(...)` selects request-response and the target Java type to decode.
4. Sending the request actually occurs when the publisher is subscribed.
5. The result emits `onNext` then `onComplete`, or terminates with `onError`.

Key methods:

| API | Role |
| --- | --- |
| RSocketRequester.builder() | Creates a client requester builder |
| Builder.tcp(host, port) | Creates a requester using TCP |
| Builder.websocket(uri) | Creates a requester using WebSocket transport |
| Builder.transport(transport) | Uses an existing ClientTransport |
| route(route, vars...) | Sets logical route in metadata |
| data(object) | Sends application data |
| data(publisher, elementClass) | Sends multiple data elements with a type hint |
| metadata(value, mimeType) | Attaches per-request metadata |
| retrieveMono(type) | Receives one response object |
| retrieveFlux(type) | Receives a stream of response objects |
| send() | Sends fire-and-forget |
| dispose() | Releases the requester |
| isDisposed() | Checks whether the requester has been disposed |

Version note: in Spring Framework 6.1, `Builder.tcp()` and `Builder.websocket()` return **`RSocketRequester`**, using a shared connection on demand. The older `connectTcp()` and `connectWebSocket()` APIs returning `Mono<RSocketRequester>` are deprecated. New code should use `tcp()`/`websocket()` so the return type is not confused.

## 4. Creating a requester with TCP and WebSocket

### TCP

~~~java
RSocketRequester requester = RSocketRequester.builder()
    .tcp("localhost", 7000);
~~~

`tcp()` creates a requester without forcing the socket to open immediately. Once a request is subscribed, the connection is established and can be reused for subsequent requests.

### RSocket over WebSocket

~~~java
URI endpoint = URI.create("ws://localhost:8080/rsocket");

RSocketRequester requester = RSocketRequester.builder()
    .websocket(endpoint);
~~~

RSocket-over-WebSocket still transmits **RSocket frames** inside the WebSocket transport. A `WebSocketHandler` sending arbitrary text strings is not an RSocket responder; both sides must speak the RSocket protocol.

### Protocol is transport-independent

The `greet` route and `GreetingRequest` record do not need changes when switching from TCP to WebSocket, as long as server and client declare matching transports. WebSocket URLs typically use `ws://` locally and `wss://` in production with TLS.

### Reuse instead of creating per message

Build one requester per upstream/connection policy and inject it into services. Do not create a new builder and TCP connection inside every service call method. When the application shuts down, release the requester with `dispose()` or manage it via Spring bean lifecycle.

## 5. SETUP frame and connection-level MIME types

When establishing a connection, the requester sends a `SETUP` frame containing MIME types, keepalive/lifetime, and optional setup data.

Builder APIs:

| Method | Meaning |
| --- | --- |
| dataMimeType(MimeType) | MIME of application data on the connection |
| metadataMimeType(MimeType) | MIME of metadata on the connection |
| setupData(Object) | Data payload in SETUP |
| setupRoute(String, Object...) | Route handling setup |
| setupMetadata(Object, MimeType) | Adds setup metadata |
| rsocketStrategies(RSocketStrategies) | Selects strategies |
| rsocketConnector(configurer) | Configures lower-level RSocketConnector |

Illustrative SETUP example:

~~~java
RSocketRequester requester = RSocketRequester.builder()
    .dataMimeType(MimeTypeUtils.APPLICATION_JSON)
    .metadataMimeType(MimeTypeUtils.parseMimeType(
        "message/x.rsocket.composite-metadata.v0"))
    .setupRoute("client.setup")
    .setupData(new ClientHello("reporting-service"))
    .tcp("localhost", 7000);
~~~

This is an **illustrative fragment**: the responder must have a matching setup contract, such as `@ConnectMapping`, otherwise SETUP may be rejected. Minimal applications do not need `setupRoute` and `setupData`.

The default data MIME type is chosen based on configured Decoders. With multiple codecs like JSON and CBOR, declare `dataMimeType` explicitly to avoid accidentally using an unexpected format.

The default metadata MIME type is usually composite metadata, allowing multiple metadata entries each with its own MIME type. Both MIME settings live in SETUP and apply for the connection, rather than being re-chosen arbitrarily per message.

## 6. Route, data, and metadata in a request

Data carries business content; metadata carries routing, tracing, authentication, or other metadata extensions.

~~~java
Mono<OrderView> result = requester.route("orders.get")
    .data(new OrderQuery("O-101"))
    .retrieveMono(OrderView.class);
~~~

The route `orders.get` is a logical destination, not an HTTP URL. Spring Messaging reads routing metadata to locate the matching `@MessageMapping`.

### Route templates

~~~java
Mono<OrderView> result = requester
    .route("orders.{id}", "O-101")
    .retrieveMono(OrderView.class);
~~~

The responder needs a matching mapping and can use `@DestinationVariable` according to the route pattern convention.

### Additional metadata

~~~java
MimeType traceMime =
    MimeTypeUtils.parseMimeType("text/plain");

Mono<OrderView> result = requester
    .route("orders.get")
    .metadata("trace-123", traceMime)
    .data(new OrderQuery("O-101"))
    .retrieveMono(OrderView.class);
~~~

This fragment sends a `text/plain` metadata entry. The server must have metadata extraction configured if it wants to read the trace ID via `@Header`. Adding a metadata entry alone does not automatically enable full tracing.

Metadata can contain secrets or tokens. Never write them to logs, and never send tokens inside application data if the API expects authentication metadata. Use RSocket security mechanisms when implementing authentication.

## 7. Composite metadata and routing

Composite metadata has the MIME type:

~~~text
message/x.rsocket.composite-metadata.v0
~~~

Routing entries in metadata typically use:

~~~text
message/x.rsocket.routing.v0
~~~

A single request can contain multiple independent entries:

~~~text
Metadata entry 1:
    MIME: message/x.rsocket.routing.v0
    Value: orders.get

Metadata entry 2:
    MIME: text/plain
    Value: trace-123

Application data:
    MIME per SETUP: application/json
    JSON: {"id":"O-101"}
~~~

`RSocketRequester.route()` builds appropriate routing metadata when using the default composite format. If you change the metadata MIME type to an incompatible format, the route may fail to be extracted by the responder and `@MessageMapping` will not match.

Do not confuse `dataMimeType` with `metadataMimeType`. They describe different byte regions of an RSocket payload.

## 8. Four ways to send and receive with RSocketRequester

### Request-Response

~~~java
Mono<GreetingReply> one = requester.route("greet")
    .data(new GreetingRequest("An"))
    .retrieveMono(GreetingReply.class);
~~~

Returns one object. If the server emits an error, the `Mono` terminates with `onError`.

### Request-Stream

~~~java
Flux<NumberEvent> numbers = requester.route("count")
    .data(new CountRequest(3))
    .retrieveFlux(NumberEvent.class);
~~~

Returns multiple messages. Downstream can request incrementally, cancel, apply timeouts, or process element by element.

### Fire-and-Forget

~~~java
Mono<Void> sent = requester.route("audit.record")
    .data(new AuditRecord("login", "user-42"))
    .send();
~~~

`Mono<Void>` here reflects only the send behavior for a model with no business response. It does **not** guarantee the audit record has been committed to the database. If processing confirmation is required, switch to request-response returning an Ack.

### Request-Channel

~~~java
Flux<UppercaseRequest> input = Flux.just(
    new UppercaseRequest("hello"),
    new UppercaseRequest("rsocket"));

Flux<UppercaseReply> output = requester.route("uppercase")
    .data(input, UppercaseRequest.class)
    .retrieveFlux(UppercaseReply.class);
~~~

Channel sends multiple request messages and receives multiple response messages. Pass `UppercaseRequest.class` as a type hint so the encoder does not have to infer it per element. Both directions can operate concurrently depending on the channel contract.

### Metadata Push

RSocket has a connection-level `metadata-push` interaction. In Spring, the dedicated metadata-push API has different semantics from regular request-routes: it expects no business response and the receiving side needs a corresponding handler/metadata extractor. Do not use metadata push as a substitute for audit commands that require an Ack.

## 9. RSocketStrategies: roles and components

`RSocketStrategies` groups the strategies that requester and responder need for serialization and routing.

| Component | Role |
| --- | --- |
| Encoder | Converts Java objects to payload bytes |
| Decoder | Converts bytes into Java objects |
| RouteMatcher | Matches route patterns against responders |
| MetadataExtractor | Extracts route and custom metadata |
| DataBufferFactory | Allocates buffers for encode/decode |
| ReactiveAdapterRegistry | Recognizes Mono, Flux, and supported reactive producers |

`RSocketStrategies` is not a network connection, not an HTTP client, and does not send requests itself. `RSocketRequester` consults strategies when encoding outbound data, decoding inbound data, and processing metadata.

### Builder with JSON codec

~~~java
RSocketStrategies strategies = RSocketStrategies.builder()
    .encoder(new Jackson2JsonEncoder())
    .decoder(new Jackson2JsonDecoder())
    .build();

RSocketRequester requester = RSocketRequester.builder()
    .rsocketStrategies(strategies)
    .dataMimeType(MimeTypeUtils.APPLICATION_JSON)
    .tcp("localhost", 7000);
~~~

The classes `Jackson2JsonEncoder` and `Jackson2JsonDecoder` belong to `org.springframework.http.codec.json`. This fragment works when Spring Web/Jackson dependencies are present. It does not configure the responder; the server must also have JSON decoders/encoders.

Strategies can be supplemented directly via a callback:

~~~java
RSocketRequester requester = RSocketRequester.builder()
    .rsocketStrategies(builder ->
        builder.encoder(new Jackson2JsonEncoder())
               .decoder(new Jackson2JsonDecoder()))
    .dataMimeType(MimeTypeUtils.APPLICATION_JSON)
    .tcp("localhost", 7000);
~~~

With the Spring Boot RSocket starter, manual configuration is usually unnecessary because Boot auto-configures `RSocketStrategies`.

## 10. Codecs, MIME types, and data types

Codecs are selected by both MIME type and Java type. Encoders turn objects into bytes; Decoders read bytes into the requested type.

~~~text
GreetingRequest
      |
      | Encoder + application/json
      v
   JSON bytes
      |
      v
 RSocket transport
      |
      v
  Decoder + target type
      |
      v
 GreetingRequest at responder
~~~

If the client sends JSON while the responder only knows CBOR, requests can fail immediately during decoding. Likewise, if response bytes are JSON `GreetingReply` but the client calls `retrieveMono(OtherType.class)`, the decoder may fail or produce the wrong object.

### JSON and CBOR

| Property | JSON | CBOR |
| --- | --- | --- |
| MIME | application/json | application/cbor |
| Data format | UTF-8 text | Binary |
| Human-readable debugging | Easy | Requires decoder |
| Size | Typically larger | Typically more compact |
| Requirement | Both sides register Jackson JSON | Both sides register Jackson CBOR |

The Boot RSocket starter provides dependencies and auto-configuration supporting Jackson. Depending on the classpath, the CBOR codec may take precedence over JSON as default; therefore the example below explicitly sets the JSON MIME type.

Do not switch from JSON to CBOR merely assuming CBOR is always faster. Measure throughput, payload size, and CPU on real data, and manage schema versioning.

### Basic codecs

`RSocketStrategies.Builder` includes basic codecs for `String`, `byte[]`, `ByteBuffer`, and `DataBuffer`. Sending Java records/DTOs requires codecs such as Jackson JSON/CBOR.

### Generic types

~~~java
Mono<List<GreetingReply>> all = requester.route("greetings.all")
    .retrieveMono(new ParameterizedTypeReference<
        List<GreetingReply>>() {});
~~~

Use `ParameterizedTypeReference` to preserve the generic element type in the `List`. Using plain `List.class` may decode elements into generic `Map` or `Object` instances rather than the desired DTO.

## 11. RSocketStrategiesCustomizer in Spring Boot

Spring Boot creates an `RSocketStrategies` bean and provides a prototype `RSocketRequester.Builder` pre-configured with auto-configured codecs and connector settings.

To add codecs at the application level, use `RSocketStrategiesCustomizer` from `org.springframework.boot.rsocket.messaging`:

~~~java
@Configuration
public class RSocketCodecConfiguration {

    @Bean
    public RSocketStrategiesCustomizer extraJsonCodec() {
        return builder -> {
            builder.encoder(new Jackson2JsonEncoder());
            builder.decoder(new Jackson2JsonDecoder());
        };
    }
}
~~~

Illustrative imports:

~~~java
import org.springframework.boot.rsocket.messaging.RSocketStrategiesCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.codec.json.Jackson2JsonDecoder;
import org.springframework.http.codec.json.Jackson2JsonEncoder;
~~~

This is a syntax example for a customizer; do not copy it verbatim into an app that already has default Jackson JSON codecs. Duplicate codecs do not improve the system; customize only when you have a dedicated `ObjectMapper`, a new data format, or defined interop requirements.

If multiple customizers add codecs, `@Order` ordering can matter. Verify encoder/decoder order and test round-trips. Do not alter the system-wide serializer without evaluating impact on other responders.

### Safe custom codecs

When creating a codec for a custom binary format:

1. Specify the exact MIME type.
2. Clearly specify the Java types supported by the encoder/decoder.
3. Ensure both client and server register matching codecs.
4. Limit message sizes and memory usage.
5. Manage `DataBuffer` lifecycles properly.
6. Test encode/decode at both unit level and over real connections.
7. Verify compatibility when multiple versions are deployed.

Never label non-JSON bytes with `application/json` MIME just to force the framework to invoke a particular decoder.

## 12. RouteMatcher and MetadataExtractor

`RSocketStrategies` also handles routing.

### RouteMatcher

~~~java
RSocketStrategies strategies = RSocketStrategies.builder()
    .routeMatcher(new PathPatternRouteMatcher())
    .build();
~~~

`RouteMatcher` resolves matching routes against `@MessageMapping`. `PathPatternRouteMatcher` is helpful when Spring Web pattern matching is desired. Changing `RouteMatcher` requires re-testing route names and patterns.

### MetadataExtractor

`MetadataExtractor` extracts routing metadata and additional metadata entries. Example registering extraction for `text/plain` metadata:

~~~java
RSocketStrategies strategies = RSocketStrategies.builder()
    .metadataExtractorRegistry(registry ->
        registry.metadataToExtract(
            MimeTypeUtils.TEXT_PLAIN,
            String.class,
            "traceId"))
    .build();
~~~

This fragment illustrates promoting decoded metadata into a header named `traceId`. The responder can read the header with `@Header("traceId")` once Spring has the extractor and matching metadata encoding configured.

In production, use a dedicated MIME type to avoid turning every `text/plain` metadata entry into `traceId`; both sides must agree on format, decoder, and security.

### ReactiveAdapterRegistry and DataBufferFactory

`ReactiveAdapterRegistry` lets Spring recognize reactive publisher types beyond `Mono`/`Flux` when supported. `DataBufferFactory` governs buffer allocation; with Reactor Netty, pooled buffers may be used. Do not customize `DataBufferFactory` or hold raw `DataBuffer` instances across long operations without understanding retain/release, zero-copy, and frame decoders.

## 13. Customizing connectors, timeouts, and lifecycle

`RSocketRequester.Builder` allows configuring the low-level `RSocketConnector`:

~~~java
RSocketRequester requester = RSocketRequester.builder()
    .dataMimeType(MimeTypeUtils.APPLICATION_JSON)
    .rsocketConnector(connector ->
        connector.keepAlive(
            Duration.ofSeconds(20),
            Duration.ofSeconds(90)))
    .tcp("localhost", 7000);
~~~

This fragment configures keepalive and lifetime; values must align with the server, proxies, and network characteristics. It does not set a deadline for an individual business request.

To bound a single interaction, use Reactor's `timeout`:

~~~java
Mono<GreetingReply> reply = requester.route("greet")
    .data(new GreetingRequest("An"))
    .retrieveMono(GreetingReply.class)
    .timeout(Duration.ofSeconds(3));
~~~

When the requester is no longer needed, call `dispose()`:

~~~java
requester.dispose();
~~~

Spring can manage it as a bean:

~~~java
@Bean(destroyMethod = "dispose")
RSocketRequester catalogRequester(RSocketRequester.Builder builder) {
    return builder
        .dataMimeType(MimeTypeUtils.APPLICATION_JSON)
        .tcp("catalog.internal", 7000);
}
~~~

Do not create a new requester inside every request handler. Never call `block()` on a WebFlux event-loop thread; only block in CLI tools or synchronous tests when justified and with an appropriate timeout.

## 14. Error handling, retry, and backpressure

Interaction failures surface as `onError` in `Mono`/`Flux`. Distinguish between:

- Inability to connect over TCP/WebSocket.
- Rejected SETUP or unsupported MIME types.
- Route not found.
- Failure to decode payload.
- Application error on responder.
- Stream timeout.
- Client cancellation.
- Transport drop mid-stream.

Controlled logging:

~~~java
Mono<GreetingReply> response = requester.route("greet")
    .data(new GreetingRequest("An"))
    .retrieveMono(GreetingReply.class)
    .doOnError(error ->
        log.warn("RSocket interaction failed", error));
~~~

`doOnError` only observes; it does not recover. `onErrorResume` can fall back if the domain allows, but should not return a fake success result when a business process failed.

### Retry is not exactly-once

A request reaching the responder may already have been processed before the connection dropped. Retrying fire-and-forget or request-channel operations with side effects can cause duplicates. Use idempotency keys, deduplication, and `retryWhen` with backoff/limits when appropriate.

### REQUEST_N and cancellation

RSocket propagates demand via `REQUEST_N` for request-stream and channel. If downstream uses `take(3)`, the source can receive cancellation and stop emitting data:

~~~java
Flux<NumberEvent> firstThree = requester.route("count")
    .data(new CountRequest(100))
    .retrieveFlux(NumberEvent.class)
    .take(3);
~~~

Do not create unbounded queues just because the transport supports backpressure. Hot push sources may still require overflow policies; bound concurrency, payload sizes, and processing times.

## 15. @MessageMapping responders

On the server side, Spring Messaging receives routes via `RSocketMessageHandler` and maps them to controller methods annotated with `@MessageMapping`.

Request-response:

~~~java
@Controller
public class GreetingResponder {

    @MessageMapping("greet")
    public Mono<GreetingReply> greet(
            @Payload GreetingRequest request) {

        return Mono.just(new GreetingReply(
            "Xin chào, " + request.name()));
    }
}
~~~

Request-stream:

~~~java
@MessageMapping("count")
public Flux<NumberEvent> count(@Payload CountRequest request) {
    int safeCount = Math.max(0, Math.min(request.count(), 10));

    return Flux.range(1, safeCount)
        .map(i -> new NumberEvent(i, "event-" + i));
}
~~~

Request-channel:

~~~java
@MessageMapping("uppercase")
public Flux<UppercaseReply> uppercase(
        @Payload Flux<UppercaseRequest> requests) {

    return requests.map(r ->
        new UppercaseReply(r.value().toUpperCase(Locale.ROOT)));
}
~~~

These snippets illustrate individual methods, not three standalone Java classes. The complete project below provides a responder, records, and imports to build.

In a responder, do not manually subscribe and return `Mono.empty()` when work still needs management. Return the publisher so the framework controls errors/cancellation and backpressure.

## 16. Runnable Java 17+ example: four interaction models

The Spring Boot 3.3.5 project below has a TCP RSocket server on port 7000 and four routes:

- `greet`: request-response.
- `count`: request-stream.
- `audit.record`: fire-and-forget.
- `uppercase`: request-channel.

A standalone CLI client explicitly constructs JSON `RSocketStrategies` because it runs outside a Spring context, sends four requests, and prints the results. An integration test uses Boot-configured `RSocketRequester.Builder` and a random port.

### Project structure

~~~text
rsocket-codec-demo/
├── pom.xml
└── src
    ├── main
    │   ├── java/com/example/rsocket
    │   │   ├── RSocketCodecDemoApplication.java
    │   │   ├── Messages.java
    │   │   ├── DemoResponder.java
    │   │   └── ClientRunner.java
    │   └── resources/application.properties
    └── test
        └── java/com/example/rsocket
            └── RSocketCodecIntegrationTests.java
~~~

### pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>

  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.3.5</version>
    <relativePath/>
  </parent>

  <groupId>com.example</groupId>
  <artifactId>rsocket-codec-demo</artifactId>
  <version>1.0.0</version>

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
~~~

### application.properties

~~~properties
spring.rsocket.server.port=7000
spring.rsocket.server.transport=tcp
spring.main.web-application-type=none
~~~

The application runs a standalone TCP RSocket server without requiring an HTTP web server. If `transport=websocket` is desired, configure a server mapping path with appropriate WebFlux/Reactor Netty infrastructure.

### Messages.java

~~~java
package com.example.rsocket;

record GreetingRequest(String name) {
}

record GreetingReply(String message) {
}

record CountRequest(int count) {
}

record NumberEvent(int number, String label) {
}

record AuditRecord(String kind, String actor) {
}

record UppercaseRequest(String value) {
}

record UppercaseReply(String value) {
}
~~~

Package-private records shared inside package `com.example.rsocket`. Jackson can serialize/deserialize Java records on Java 17 when matching Boot dependencies are present.

### DemoResponder.java

~~~java
package com.example.rsocket;

import java.util.Locale;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.stereotype.Controller;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Controller
public class DemoResponder {

    private static final Logger log =
        LoggerFactory.getLogger(DemoResponder.class);

    @MessageMapping("greet")
    public Mono<GreetingReply> greet(
            @Payload GreetingRequest request) {

        return Mono.just(
            new GreetingReply("Xin chào, " + request.name()));
    }

    @MessageMapping("count")
    public Flux<NumberEvent> count(
            @Payload CountRequest request) {

        int count = Math.max(0, Math.min(request.count(), 10));

        return Flux.range(1, count)
            .map(i -> new NumberEvent(i, "event-" + i));
    }

    @MessageMapping("audit.record")
    public Mono<Void> audit(
            @Payload AuditRecord record) {

        return Mono.fromRunnable(() ->
            log.info("audit kind={}, actor={}",
                record.kind(), record.actor()));
    }

    @MessageMapping("uppercase")
    public Flux<UppercaseReply> uppercase(
            @Payload Flux<UppercaseRequest> requests) {

        return requests.map(item ->
            new UppercaseReply(
                item.value().toUpperCase(Locale.ROOT)));
    }
}
~~~

The `count` responder caps the item count to prevent a single request from asking for an overly large stream. Fire-and-forget only logs; if auditing must be durable, use a message queue or a dedicated request-response Ack.

### RSocketCodecDemoApplication.java

~~~java
package com.example.rsocket;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RSocketCodecDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(RSocketCodecDemoApplication.class, args);
    }
}
~~~

### ClientRunner.java

~~~java
package com.example.rsocket;

import java.util.List;

import org.springframework.http.codec.json.Jackson2JsonDecoder;
import org.springframework.http.codec.json.Jackson2JsonEncoder;
import org.springframework.messaging.rsocket.RSocketRequester;
import org.springframework.messaging.rsocket.RSocketStrategies;
import org.springframework.util.MimeTypeUtils;

import reactor.core.publisher.Flux;

public class ClientRunner {

    public static void main(String[] args) {
        // Running outside Spring context: supply JSON codecs explicitly.
        RSocketStrategies strategies = RSocketStrategies.builder()
            .encoder(new Jackson2JsonEncoder())
            .decoder(new Jackson2JsonDecoder())
            .build();

        RSocketRequester requester = RSocketRequester.builder()
            .rsocketStrategies(strategies)
            .dataMimeType(MimeTypeUtils.APPLICATION_JSON)
            .tcp("localhost", 7000);

        try {
            GreetingReply greeting = requester.route("greet")
                .data(new GreetingRequest("An"))
                .retrieveMono(GreetingReply.class)
                .block();

            System.out.println(greeting.message());

            List<NumberEvent> numbers = requester.route("count")
                .data(new CountRequest(3))
                .retrieveFlux(NumberEvent.class)
                .collectList()
                .block();

            numbers.forEach(n ->
                System.out.println(n.number() + ": " + n.label()));

            requester.route("audit.record")
                .data(new AuditRecord("login", "user-42"))
                .send()
                .block();

            System.out.println("Audit fire-and-forget sent");

            List<UppercaseReply> replies = requester
                .route("uppercase")
                .data(
                    Flux.just(
                        new UppercaseRequest("hello"),
                        new UppercaseRequest("rsocket")),
                    UppercaseRequest.class)
                .retrieveFlux(UppercaseReply.class)
                .collectList()
                .block();

            replies.forEach(r ->
                System.out.println(r.value()));
        } finally {
            requester.dispose();
        }
    }
}
~~~

`ClientRunner` runs on the CLI main thread, so `block()` is acceptable for printing output in order. In WebFlux handlers, return `Mono`/`Flux` instead of blocking the event loop.

Important point: if you call `RSocketRequester.builder()` directly outside a Spring context without setting `rsocketStrategies(strategies)`, the builder only has basic codecs by default, which is insufficient to encode/decode Java records. Configuring JSON explicitly in `ClientRunner` solves this. In the integration test below, the builder is injected by Spring Boot and already receives auto-configured codecs.

### Build and run commands

From the directory containing `pom.xml`:

~~~bash
mvn -q clean package
mvn spring-boot:run
~~~

Keep the terminal running the server on port 7000. In a second terminal, run the client:

~~~bash
mvn org.codehaus.mojo:exec-maven-plugin:3.5.0:java -Dexec.mainClass=com.example.rsocket.ClientRunner
~~~

When server and client run successfully, expected business output lines:

~~~text
Xin chào, An
1: event-1
2: event-2
3: event-3
Audit fire-and-forget sent
HELLO
RSOCKET
~~~

Maven and logging frameworks may print additional log lines. The line `Audit fire-and-forget sent` does not prove the server persisted the event to durable storage.

## 17. JSON codec integration test over TCP

The test starts the RSocket server on port 0; Boot assigns a random port and injects it with `@LocalRSocketServerPort`. Four tests correspond to the four interaction models.

### RSocketCodecIntegrationTests.java

~~~java
package com.example.rsocket;

import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.TestInstance;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.rsocket.server.LocalRSocketServerPort;
import org.springframework.messaging.rsocket.RSocketRequester;
import org.springframework.util.MimeTypeUtils;

import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

@SpringBootTest(properties = {
    "spring.rsocket.server.port=0",
    "spring.rsocket.server.transport=tcp"
})
@TestInstance(TestInstance.Lifecycle.PER_CLASS)
class RSocketCodecIntegrationTests {

    @LocalRSocketServerPort
    private int port;

    @Autowired
    private RSocketRequester.Builder builder;

    private RSocketRequester requester;

    @BeforeAll
    void setUp() {
        requester = builder
            .dataMimeType(MimeTypeUtils.APPLICATION_JSON)
            .tcp("127.0.0.1", port);
    }

    @AfterAll
    void tearDown() {
        if (requester != null) {
            requester.dispose();
        }
    }

    @Test
    void requestResponseUsesJsonCodec() {
        StepVerifier.create(
                requester.route("greet")
                    .data(new GreetingRequest("An"))
                    .retrieveMono(GreetingReply.class))
            .expectNext(new GreetingReply("Xin chào, An"))
            .verifyComplete();
    }

    @Test
    void requestStreamDecodesMultipleDtos() {
        StepVerifier.create(
                requester.route("count")
                    .data(new CountRequest(3))
                    .retrieveFlux(NumberEvent.class))
            .expectNext(
                new NumberEvent(1, "event-1"),
                new NumberEvent(2, "event-2"),
                new NumberEvent(3, "event-3"))
            .verifyComplete();
    }

    @Test
    void fireAndForgetHasNoResponseBody() {
        StepVerifier.create(
                requester.route("audit.record")
                    .data(new AuditRecord("login", "user-42"))
                    .send())
            .verifyComplete();
    }

    @Test
    void channelEncodesAndDecodesFluxValues() {
        Flux<UppercaseRequest> input = Flux.just(
            new UppercaseRequest("hello"),
            new UppercaseRequest("rsocket"));

        StepVerifier.create(
                requester.route("uppercase")
                    .data(input, UppercaseRequest.class)
                    .retrieveFlux(UppercaseReply.class))
            .expectNext(
                new UppercaseReply("HELLO"),
                new UppercaseReply("RSOCKET"))
            .verifyComplete();
    }
}
~~~

Run:

~~~bash
mvn -q test
~~~

The test uses a real TCP RSocket transport with JSON encoding/decoding through Spring Messaging. It verifies routes, data MIME types, codecs, annotated responders, and response types end-to-end, rather than only unit-testing a serializer function.

Checklist when tests fail:

- Does `application.properties` specify a fixed port while the test overrides it with a random port?
- Did Spring Boot start the RSocket server?
- Did the requester read the right port from `@LocalRSocketServerPort`?
- Are `dataMimeType` `application/json` and Jackson codecs present on both sides?
- Do handler routes and DTOs match?
- Is another application occupying the port?

## 18. Deployment scenario: multiple codec and client versions

When requester and responder are deployed independently, a clear wire contract is required:

- Stable route names, versioned if semantics change.
- Data MIME type chosen before connecting.
- Metadata MIME type supporting routes and required extensions.
- DTO schemas compatible across versions.
- Agreed enum/date/time and null policies.
- Custom MIME types with encoders/decoders on both sides.
- Appropriate message size limits.
- No raw tokens or sensitive payloads written to logs.
- Integration tests covering actual versions running concurrently in production.

For instance, migrating data format from JSON to CBOR requires updating requester, responder, and intermediate services. Changing codecs is more than replacing `"application/json"` with `"application/cbor"`; it requires dependencies, schema testing, and performance verification.

If backward compatibility is required, run two endpoints/connection policies in parallel during migration rather than forcing older clients to connect with an unsupported format.

## 19. Observability and diagnostics

In production, capture metrics/logs for:

- Connection setup successes/failures.
- Requests by route and interaction model.
- Latency, message counts, and bytes.
- Errors by route, transport, and codec.
- Stream cancellations and timeouts.
- Reconnects and live connection counts.
- Backpressure and queue behavior under heavy load.
- Memory/buffer usage for large payloads.

Log routes and correlation IDs, while avoiding access tokens, secrets, and raw user payloads. For infinite streams or long-lived channels, latency to the first event and message rate are more informative than total interaction duration.

### Symptom-based troubleshooting

| Symptom | Causes to inspect |
| --- | --- |
| Cannot connect | Host, port, TCP/WebSocket transport, server startup |
| SETUP rejected | MIME types, authentication/setup metadata, protocol config |
| Route not found | `route()`, `@MessageMapping`, routing metadata, `RouteMatcher` |
| Cannot encode DTO | Encoder matching Java type and data MIME type |
| Response decode error | Decoder/target type/schema |
| Only String works, records fail | Requester built outside Boot missing JSON codec |
| Stream stops mid-way | `onError`, cancel, timeout, or transport disconnection |
| FNF succeeds but no data saved | FNF has no business acknowledgment |
| Memory grows on long channels | Unbounded buffers/queues or missing cleanup |
| Duplicate events after reconnect | Retries lacking idempotency/deduplication |

## 20. Common mistakes

1. **Confusing RSocket and raw WebSocket.** WebSocket is a transport; RSocket has its own protocol and interaction semantics.
2. **Using `connectTcp()` instead of `tcp()`.** In Spring 6.1, the older method is deprecated; use `tcp()`.
3. **Assuming `tcp()` always connects immediately.** The requester uses a shared connection, typically connecting when a request is subscribed.
4. **Creating a new requester per message.** Causes churn and cleanup issues; reuse long-lived requesters.
5. **Forgetting `dispose()`.** Connections can retain resources after shutdown/tests.
6. **Building a requester outside Boot without JSON codecs.** DTOs fail to encode even if the server supports JSON.
7. **Adding an encoder without a decoder.** Requests can be sent, but responses cannot be read.
8. **Omitting data MIME type when multiple format codecs exist.** Negotiation may pick an unexpected format.
9. **Confusing data MIME and metadata MIME.** Route metadata is encoded differently from application data.
10. **Changing metadata MIME without understanding composite metadata.** `@MessageMapping` may fail to locate routes.
11. **Sending custom metadata without declaring an extractor.** The server does not automatically populate headers to read.
12. **Using `retrieveMono()` for multi-element streams.** Choose `retrieveFlux` to match the interaction.
13. **Treating `send()` as a business Ack.** Fire-and-forget does not prove durable processing.
14. **Omitting element type for complex `Flux` inputs.** Codec lookup can be ambiguous or slow; use `data(flux, Type.class)`.
15. **Decoding generics with `List.class`.** Element type information is lost; use `ParameterizedTypeReference`.
16. **Subscribing manually inside a responder.** Breaks lifecycle/error linkage; return the publisher.
17. **Calling `block()` on the WebFlux event loop.** Causes blocking; use reactive composition.
18. **Retrying FNF without idempotency.** Causes duplicate side effects.
19. **Leaving payloads and concurrent streams unbounded.** Easily spikes memory/CPU under load.
20. **Customizing `DataBufferFactory` without understanding pooled buffers.** Can cause memory leaks or frame decoder conflicts.
21. **Equating reconnect with replay.** A new connection does not guarantee old requests are re-sent exactly once.
22. **Skipping tests over real transport.** Codec unit tests miss setup/route/metadata errors.

## 21. Implementation checklist

Before releasing an RSocket client/responder:

- **Interaction model:** choose Mono, Flux, FNF, or channel?
- **Transport:** do both sides agree on TCP, WebSocket, or another transport?
- **Lifecycle:** is the requester reused and properly disposed?
- **SETUP:** are `dataMimeType` and `metadataMimeType` compatible?
- **Routing:** do route strings match `@MessageMapping`?
- **Encoder/Decoder:** do both sides have codecs for the DTOs and MIME types?
- **Strategies:** are Boot-managed beans/builders used when running inside Spring?
- **Custom codecs:** are round-trips and version compatibility tested?
- **Metadata:** does the responder have extractors for custom metadata?
- **Generics:** are type hints and `ParameterizedTypeReference` used where needed?
- **Backpressure:** do streams honor demand, cancellation, and overflow policies?
- **Timeouts:** do clients enforce appropriate deadlines?
- **Retries:** are operations idempotent or protected by deduplication?
- **Security:** are setup/request metadata and transports protected?
- **Monitoring:** are routes, errors, latency, and reconnects observed?
- **Tests:** have all four interaction models been tested over real RSocket?

## 22. Self-check exercises

**Question 1.** How does `RSocketRequester` help compared to low-level `io.rsocket.RSocket`?  
**Answer:** Sends requests using Java objects with routes/metadata and codecs, instead of manually handling `Payload`.

**Question 2.** What type does `Builder.tcp()` return in Spring Framework 6.1?  
**Answer:** `RSocketRequester`, using a lazy/shared connection.

**Question 3.** What are the two key MIME types in SETUP?  
**Answer:** Data MIME type and metadata MIME type.

**Question 4.** What are the main parts of `RSocketStrategies`?  
**Answer:** `Encoder`, `Decoder`, `RouteMatcher`, `MetadataExtractor`, `DataBufferFactory`, and `ReactiveAdapterRegistry`.

**Question 5.** What metadata MIME type does RSocket routing typically use?  
**Answer:** `message/x.rsocket.routing.v0` inside composite metadata.

**Question 6.** When do you use `retrieveFlux()`?  
**Answer:** When the interaction expects multiple response messages.

**Question 7.** Why is `send()` not a business Ack?  
**Answer:** Fire-and-forget has no business response confirming processing.

**Question 8.** What is the benefit of `data(flux, Type.class)`?  
**Answer:** Provides a clear element type hint for selecting the encoder across multiple items.

**Question 9.** Which callback does Boot provide to customize codecs?  
**Answer:** `RSocketStrategiesCustomizer`.

**Question 10.** What must a requester created outside a Spring context watch out for regarding DTOs?  
**Answer:** It must configure Jackson JSON/CBOR codecs and matching MIME types when using DTOs.

**Question 11.** What does `MetadataExtractor` do?  
**Answer:** Extracts metadata such as routing or custom fields for Spring Messaging to use during handling.

**Question 12.** Why does request-channel need backpressure?  
**Answer:** Because many bidirectional messages can accumulate if a producer outpaces a consumer.

**Question 13.** Should FNF be retried unconditionally on network failure?  
**Answer:** No; the server may have already processed the message, causing duplicate side effects.

**Question 14.** Why test against a real TCP server?  
**Answer:** It tests SETUP, routing, codecs, and annotated responders end-to-end, not just serializers.

## 23. Key takeaways

`RSocketRequester` provides a fluent API to send RSocket requests by route, data, and metadata, receiving results via `retrieveMono()`, `retrieveFlux()`, or sending FNF via `send()`. `Builder.tcp()` and `websocket()` return a requester with an on-demand shared connection; reuse it and dispose it properly with its lifecycle.

`RSocketStrategies` governs object encoding/decoding, route/metadata handling, and buffers. Codecs must match both Java types and the data MIME type declared in SETUP. Composite metadata lets routes and other metadata entries have their own MIME types. Spring Boot starters pre-configure `RSocketStrategies` and `RSocketRequester.Builder`; code outside a Spring context must supply codecs for DTOs.

RSocket provides backpressure via `REQUEST_N` for streams/channels, yet applications must still bound concurrency, buffers, timeouts, and retries. Fire-and-forget is not a business acknowledgment. When changing DTOs or codecs, test cross-version compatibility and run integration tests over a real transport.

### References

- Spring Framework, [RSocket overview, requester and strategies](https://docs.spring.io/spring-framework/reference/rsocket.html).
- Spring Framework 6.1, [RSocketRequester.Builder](https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/messaging/rsocket/RSocketRequester.Builder.html).
- Spring Framework 6.1, [RSocketStrategies.Builder](https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/messaging/rsocket/RSocketStrategies.Builder.html).
- Spring Framework 6.1, [RSocketRequester.RequestSpec](https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/messaging/rsocket/RSocketRequester.RequestSpec.html).
- Spring Boot 3.3, [RSocket auto-configuration](https://docs.spring.io/spring-boot/docs/3.3.5/reference/html/messaging.html#messaging.rsocket).
- Spring Boot Javadoc, [RSocketStrategiesCustomizer](https://docs.spring.io/spring-boot/docs/3.3.5/api/org/springframework/boot/rsocket/messaging/RSocketStrategiesCustomizer.html).
- Project Reactor, [Handling Errors](https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html).
- RSocket, [Protocol](https://rsocket.io/about/protocol/).
