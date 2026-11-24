# RSocket: Route, Metadata, and Data Formats

**RSocket** is a binary protocol for bidirectional, asynchronous message exchange with backpressure support. Unlike REST over HTTP, RSocket does not use a URL path and HTTP method for each business call. The client connects over TCP or WebSocket, sends a `SETUP` frame to agree on connection parameters, and then sends multiple requests over that connection. Each request can carry **data** (business content) and **metadata** (control information such as route, authentication, tracing).

In Spring, `RSocketRequester` builds requests; `RSocketMessageHandler` looks up handlers by the route in metadata and invokes `@MessageMapping` methods. `RSocketStrategies` together with encoders/decoders decide how Java objects and bytes are converted.

Concepts to distinguish:

- **Route:** a logical name used to select a handler, e.g. `orders.get.42` or `orders.list`; typically placed in routing metadata, not an HTTP URL.
- **Data:** the business content of a request/response, which may be JSON, CBOR, text, or binary.
- **Metadata:** supplementary information, such as route, client tag, token, tenant, trace ID.
- **Data MIME type:** the data format used on the connection, e.g. `application/json`.
- **Metadata MIME type:** the format of the metadata section, typically `message/x.rsocket.composite-metadata.v0`.
- **Transport:** TCP/WebSocket used to carry frames. A WebSocket transport path and a business route are two independent concepts.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain data and metadata inside an RSocket payload.
2. Understand data MIME and metadata MIME in the `SETUP` frame.
3. Build requests with `route()`, `metadata()`, and `data()`.
4. Map routes with `@MessageMapping` and variables with `@DestinationVariable`.
5. Distinguish the four interactions: Request-Response, Request-Stream, Fire-and-Forget, Request-Channel.
6. Use `@Header` to read metadata registered for extraction.
7. Customize `RSocketStrategiesCustomizer` and `metadataExtractorRegistry`.
8. Understand the role of `@ConnectMapping` and metadata push.
9. Choose JSON/CBOR codecs and avoid MIME mismatches.
10. Distinguish an RSocket TCP port, WebSocket mapping path, and route.
11. Design secure metadata, schema versioning, and resource limits.
12. Write and test a Spring Boot RSocket application with Java 17.

## 2. Message Format: data and metadata

An RSocket payload consists of two sections:

~~~text
RSocket Payload
+----------------------------------------+
| Metadata (optional)                    |
| - routing: orders.get.42               |
| - clientTag: web                        |
| - authentication/tracing...            |
+----------------------------------------+
| Data (optional)                        |
| - JSON / CBOR / plain text / binary    |
| - request or response payload          |
+----------------------------------------+
~~~

Metadata is used for routing and carrying control information; data carries business information. Example of fetching order 42:

| Component | Value |
| --- | --- |
| Transport | TCP localhost:7000 |
| Route | `orders.get.42` |
| Extra metadata | clientTag = web |
| Request data | Empty |
| Response data | `OrderView("42", "accepted", "web")` |
| Data MIME | application/json |
| Metadata MIME | composite metadata |

You could design a fixed route `orders.get` and send the ID in data. Both options are valid. Agree on one contract and avoid sending two differing ID copies in route and payload.

### 2.1. Metadata is not an HTTP header

Over TCP, RSocket has no HTTP header set per request. Spring provides `@Header` to read a metadata value that has been extracted into a message header. This is not HTTP `@RequestHeader`.

With RSocket over WebSocket, HTTP headers appear only during the WebSocket upgrade handshake; subsequent RSocket interactions still carry routes and metadata inside RSocket frames, not HTTP headers.

### 2.2. Per-request vs. per-connection metadata

The route typically appears in the interaction-initiating frame, such as `REQUEST_RESPONSE`, `REQUEST_STREAM`, `REQUEST_CHANNEL`, or `REQUEST_FNF`. Subsequent `REQUEST_N` frames transmit demand signals rather than repeating the route on every item.

Metadata push is a different mechanism: `METADATA_PUSH` sends connection-level metadata that does not belong to a specific request. Do not confuse metadata push with request-response.

## 3. SETUP frame, data MIME, and metadata MIME

When an RSocket connection is created, the requester sends `SETUP`. This frame carries two MIME types:

- `dataMimeType`: how data payloads on the connection are encoded/decoded.
- `metadataMimeType`: how metadata on the connection is serialized.

Example:

~~~java
RSocketRequester requester = builder
    .dataMimeType(
        MimeTypeUtils.parseMimeType("application/json")
    )
    .tcp("localhost", 7000);
~~~

Spring uses JSON for data with this configuration. Metadata MIME can remain Spring's default, typically composite metadata.

### 3.1. Not HTTP Content-Type/Accept

RSocket MIME types are declared in SETUP, not per-route `Content-Type`/`Accept` HTTP headers. A connection that chose JSON does not dynamically negotiate CBOR per request like HTTP content negotiation.

If a system needs multiple formats, design per-connection format selection or an explicit envelope contract, and ensure client/server have the appropriate codecs.

### 3.2. Composite Metadata

Common MIME type:

~~~text
message/x.rsocket.composite-metadata.v0
~~~

Composite metadata allows multiple metadata entries, each with its own MIME type:

~~~text
SETUP:
  data MIME     = application/json
  metadata MIME = message/x.rsocket.composite-metadata.v0

REQUEST:
  metadata entry 1:
    MIME  = message/x.rsocket.routing.v0
    value = orders.get.42

  metadata entry 2:
    MIME  = text/plain
    value = web

  data:
    (empty)
~~~

The route entry uses MIME `message/x.rsocket.routing.v0` per the routing extension. Another entry uses `text/plain` for a simple client tag. Both entries coexist in the same metadata region.

If a client does not use composite metadata yet wants to send multiple entries of different MIME types, inspect the peer's protocol and configure an appropriate metadata extractor. Do not just change a MIME string and assume Spring will automatically understand it.

### 3.3. MIME is not a codec

A MIME type is a format contract; a codec performs byte-to-object conversion. Selecting `application/cbor` does not automatically add a Jackson CBOR decoder. Spring Boot starters provide auto-configuration for common codecs, whereas custom formats require registering encoders/decoders explicitly.

## 4. Routes in Spring RSocket

A Spring responder can declare:

~~~java
@Controller
class OrderController {

    @MessageMapping("orders.get")
    Mono<OrderView> get(OrderQuery query) {
        return orderService.find(query.id());
    }
}
~~~

The snippet above is illustrative, assuming `orderService` exists. Requester calls:

~~~java
Mono<OrderView> result = requester
    .route("orders.get")
    .data(new OrderQuery("42"))
    .retrieveMono(OrderView.class);
~~~

Internal flow:

~~~text
RSocketRequester.route("orders.get")
              |
              v
Routing metadata entry
              |
              v
MetadataExtractor => "route"
              |
              v
RSocketMessageHandler
              |
              v
@MessageMapping("orders.get")
              |
              v
Decode data -> handler -> encode response
~~~

### 4.1. A route is not an HTTP URL

Over TCP, `orders.get` corresponds to no URL. With WebSocket transport, `/rsocket` is the transport path used to open a WebSocket connection; the `orders.get` route is still sent inside RSocket metadata.

Do not use HTTP `@GetMapping` to receive pure TCP RSocket routes. Use `@MessageMapping` on a controller or an appropriate responder implementation.

### 4.2. Hierarchical conventions

Examples:

~~~text
catalog.products.get
catalog.products.search
orders.get
orders.list
orders.status.{id}
audit.log
text.upper
~~~

Spring RSocket's default route matcher uses dots as separators, not HTTP URL path decoding rules. When designing hierarchies, prefix by domain and action to avoid route collisions across modules.

### 4.3. @DestinationVariable

Responder:

~~~java
@MessageMapping("orders.status.{id}")
Mono<String> status(
        @DestinationVariable("id") String id) {

    return Mono.just("status:" + id);
}
~~~

Requester:

~~~java
Mono<String> result = requester
    .route("orders.status.{id}", "42")
    .retrieveMono(String.class);
~~~

`route(String, Object...)` passes a route template and variables, while `@DestinationVariable` extracts the value in the handler. Do not build routes by concatenating unvalidated client input strings. After extraction, still validate the ID and check authorization.

### 4.4. Route versioning

For breaking changes, you can use `orders.v1.get` and `orders.v2.get`, or version the schema inside data. There is no need to version a route merely for adding a backward-compatible optional JSON field. Publish schemas, track usage of old routes, and plan migrations.

## 5. The four RSocket interactions

RSocket supports four primary exchange models:

| Interaction | Input | Output | Requester API |
| --- | --- | --- | --- |
| Request-Response | 0 or 1 | 1 | `retrieveMono(T.class)` |
| Fire-and-Forget | 0 or 1 | 0 data | `send()` |
| Request-Stream | 0 or 1 | Many | `retrieveFlux(T.class)` |
| Request-Channel | Many | 0, 1, or many | `data(Flux)` + appropriate response method |

Examples:

~~~java
// Request-Response
Mono<OrderView> one = requester.route("orders.get")
    .data(new OrderQuery("42"))
    .retrieveMono(OrderView.class);

// Fire-and-Forget
Mono<Void> sent = requester.route("audit.log")
    .data("order-42 opened")
    .send();

// Request-Stream
Flux<OrderView> many = requester.route("orders.list")
    .data(new ListQuery(3))
    .retrieveFlux(OrderView.class);

// Request-Channel
Flux<String> upper = requester.route("text.upper")
    .data(Flux.just("alpha", "beta"))
    .retrieveFlux(String.class);
~~~

Spring determines the interaction based on input and output cardinality in the annotated responder. Single-item data can be a concrete object or `Mono`; multi-item is `Flux`; no response data is usually represented by `void` or `Mono<Void>`.

### 5.1. Fire-and-Forget has no business ACK

`send()` completing means the message was sent according to the requester's contract. It does **not** guarantee the remote business handler committed data. If processing confirmation is required, use Request-Response with an explicit status receipt.

### 5.2. Backpressure

RSocket supports stream demand via frames such as `REQUEST_N`. For Request-Stream/Channel, the responder must respect demand rather than producing infinitely into an unbounded buffer. When the requester cancels, downstream data sources/resources must stop and clean up.

## 6. Sending extra metadata with RSocketRequester

When using composite metadata, the requester adds custom metadata:

~~~java
Mono<OrderView> result = requester
    .route("orders.get.{id}", "42")
    .metadata("web", MimeTypeUtils.TEXT_PLAIN)
    .retrieveMono(OrderView.class);
~~~

`route()` adds routing metadata. `metadata("web", TEXT_PLAIN)` adds another entry with MIME `text/plain`.

**Point to remember:** Adding metadata on the requester does not automatically make `@Header("clientTag")` available on the responder. The responder must register a matching extractor.

### 6.1. MetadataExtractor

`MetadataExtractor` converts metadata bytes into a map of named values. `DefaultMetadataExtractor` already supports routing metadata and stores it under the key `route`.

For other metadata, register the MIME type, decoded value type, and header name:

~~~java
strategies.metadataExtractorRegistry(registry ->
    registry.metadataToExtract(
        MimeTypeUtils.TEXT_PLAIN,
        String.class,
        "clientTag"
    )
);
~~~

This snippet is a callback inside `RSocketStrategies.Builder`. A decoder supporting `String`/`text/plain` is required. Once registered, the responder can receive:

~~~java
@MessageMapping("orders.get.{id}")
Mono<OrderView> get(
        @DestinationVariable("id") String id,
        @Header("clientTag") String clientTag) {

    return Mono.just(
        new OrderView(id, "accepted", clientTag)
    );
}
~~~

`@Header` here refers to extracted RSocket metadata, not an HTTP header.

### 6.2. @Headers Map

Spring also allows receiving a map of extracted metadata:

~~~java
@Headers Map<String, Object> headers
~~~

The map contains only items the extractor knows how to read. It is not raw metadata bytes and does not automatically contain arbitrary unknown entries.

### 6.3. Metadata with DTOs

For complex metadata, use a vendor MIME type, for example:

~~~text
application/vnd.example.tenant+json
~~~

On the server side:

~~~java
MimeType tenantMime = MimeTypeUtils.parseMimeType(
    "application/vnd.example.tenant+json"
);

strategies.metadataExtractorRegistry(registry ->
    registry.metadataToExtract(
        tenantMime,
        TenantMetadata.class,
        "tenant"
    )
);
~~~

This is an illustrative configuration pattern: `TenantMetadata` is an application DTO; an encoder/decoder supporting the chosen vendor MIME is required. Calling `metadataToExtract` alone does not install a new codec.

### 6.4. Common metadata MIME types

| Data | MIME | Notes |
| --- | --- | --- |
| Routing | `message/x.rsocket.routing.v0` | Extracted by default as `route` |
| Text tag | `text/plain` | Must register extractor to read via `@Header` |
| Tenant object | `application/vnd.example.tenant+json` | Requires codec supporting the vendor MIME |
| Bearer authentication | `message/x.rsocket.authentication.bearer.v0` | Follows authentication extension; requires security configuration |
| Tracing | System-specific MIME | Do not log secrets or sensitive data |

Metadata can appear in logs or traces. Do not put tokens in routes or write raw authentication metadata to logs.

## 7. Spring Boot RSocket auto-configuration

The `spring-boot-starter-rsocket` dependency provides Spring Messaging RSocket infrastructure and common codecs. Spring Boot automatically creates `RSocketStrategies`, `RSocketMessageHandler`, and requester builders when dependencies and auto-configuration conditions are met.

### 7.1. TCP transport

~~~properties
spring.rsocket.server.port=7000
spring.rsocket.server.transport=tcp
~~~

The RSocket TCP server is independent of the HTTP server; `spring.rsocket.server.port` is not `server.port`. Business routes are neither ports nor TCP URL paths.

### 7.2. WebSocket transport

In a WebFlux application wanting RSocket over WebSocket integrated into the Reactor Netty HTTP server:

~~~properties
spring.rsocket.server.transport=websocket
spring.rsocket.server.mapping-path=/rsocket
~~~

When embedded in the WebFlux server, do not configure a separate `spring.rsocket.server.port`. Client:

~~~java
RSocketRequester requester = builder.webSocket(
    URI.create("ws://localhost:8080/rsocket")
);
~~~

The `/rsocket` path only opens the transport connection. After connecting, the client still calls `route("orders.get")` or `route("orders.list")` via metadata, not via URL paths.

### 7.3. Plain Spring Framework

Without Spring Boot, you can configure `RSocketMessageHandler`:

~~~java
RSocketMessageHandler handler = new RSocketMessageHandler();
handler.setRSocketStrategies(strategies);
handler.routeMatcher(new PathPatternRouteMatcher());
~~~

This is a configuration snippet, not a standalone runnable app: you must supply `strategies`, register annotated responders, create an `RSocketServer`, and bind `handler.responder()` to a TCP/WebSocket transport. With Boot, avoid manually creating a handler that duplicates the auto-configured bean.

## 8. JSON, CBOR, String, and data formats

### 8.1. Data MIME and encoders/decoders

The same Java DTO can be encoded differently:

~~~text
Java OrderView
      |
      +--> Jackson JSON Encoder --> JSON UTF-8 bytes
      |
      +--> Jackson CBOR Encoder --> CBOR binary bytes
~~~

The Spring Boot RSocket starter provides Jackson CBOR and JSON support. When client/server use different technologies, explicitly specify the agreed MIME type. Example:

~~~java
RSocketRequester requester = builder
    .dataMimeType(
        MimeTypeUtils.parseMimeType("application/json")
    )
    .tcp("localhost", 7000);
~~~

For CBOR, use `application/cbor` and ensure both ends have supporting codecs. Do not fix a codec mismatch by renaming routes.

### 8.2. Text/plain

For text data, you can use:

~~~java
builder.dataMimeType(MimeTypeUtils.TEXT_PLAIN);
~~~

The `text/plain` decoder fits `String`; it does not automatically convert strings into complex Java records. If sending a JSON object over `text/plain` data MIME, use an explicit application encoder/decoder rather than relying on coincidence.

### 8.3. MIME is set at SETUP

Do not treat each interaction like an HTTP request that can switch `Content-Type` arbitrarily. Choose the format per connection or use a dedicated envelope contract, and configure matching codecs. A client can create multiple requesters for different targets or formats.

### 8.4. Schema compatibility

JSON example:

~~~json
{"id":"42","status":"accepted","clientTag":"web"}
~~~

When adding fields, verify how older clients handle unknown fields. For breaking changes, use route/schema versioning; for compatible changes, you may keep the route. Add validation for missing data, wrong types, oversized payloads, and unauthorized data.

### 8.5. Custom codecs

To support a new format:

1. Define an official MIME type.
2. Implement the encoder and decoder.
3. Register them with `RSocketStrategies` or `RSocketStrategiesCustomizer`.
4. Agree on the data MIME in SETUP.
5. Test valid payloads, invalid schemas, and size limits.

`metadataExtractorRegistry` only controls how **metadata** is extracted. It does not decode new data payloads by itself.

## 9. @ConnectMapping and connection-level metadata

`@MessageMapping` handles regular interactions. `@ConnectMapping` handles the `SETUP` frame and connection-level metadata pushes.

Illustrative example:

~~~java
@Controller
class SetupController {

    @ConnectMapping("client.init")
    Mono<Void> connected(String clientName) {
        if (clientName == null || clientName.isBlank()) {
            return Mono.error(
                new IllegalArgumentException("Client name required")
            );
        }
        return Mono.empty();
    }
}
~~~

Requester:

~~~java
RSocketRequester requester = builder
    .setupRoute("client.init")
    .setupData("web-app")
    .tcp("localhost", 7000);
~~~

If the SETUP handler emits an error, the connection is rejected. `@ConnectMapping` sends no response data: the method returns `void` or `Mono<Void>`.

Do not wait for an outbound request on the same connection inside the SETUP handler; the connection has not finished setting up for the peer to serve requests. Decouple proactive interactions until after the connection is ready.

### 9.1. Metadata push

`sendMetadata()` sends `METADATA_PUSH`, delivering connection-level metadata notifications. It is not a Request-Response route, nor does it carry business return values like `retrieveMono`.

### 9.2. Setup authentication

Some systems validate authentication metadata during SETUP to authenticate the peer. Yet per-route/per-resource authorization must still be enforced afterward, especially when a client can access multiple tenants or objects with different permissions.

## 10. Securing routes, metadata, and transport

Metadata is not inherently trustworthy. Clients can spoof `clientTag`, tenant, route variables, or even supply invalid tokens. Distinguish:

- **Authentication:** proving who the peer is (mTLS/TLS, setup or request authentication).
- **Authorization:** determining whether the peer has permission to invoke a specific route/resource.
- **Transport encryption:** TCP is unencrypted unless TLS is enabled; WebSocket without TLS uses `ws`.
- **Validation:** route IDs, DTOs, and metadata are all untrusted input.
- **Observability:** logs must not contain raw tokens or sensitive information.

### 10.1. Authentication metadata

RSocket has a bearer authentication extension, e.g. MIME:

~~~text
message/x.rsocket.authentication.bearer.v0
~~~

A requester can send a metadata entry of this type. However, simply calling `metadata(token, mimeType)` does not authenticate the token; the server must have Spring Security RSocket or an interceptor to verify signature, expiry, and scopes, then check route permissions.

Never read a string via `@Header("token")` and treat it as an authenticated principal. Metadata extraction and authentication are two separate layers.

### 10.2. Routes are not secrets

Do not embed passwords/tokens inside routes:

~~~text
orders.get.42.token=secret
~~~

Routes can appear in logs and metrics. When credentials must be transmitted, use TLS-protected authentication metadata combined with log masking and authorization checks.

### 10.3. Tenants and authorization

If a route has `tenant.{tenantId}.orders.{orderId}`, the responder must verify `tenantId` against the authenticated principal. Never rely on client-sent route variables or metadata to query another tenant's data.

## 11. Runnable Java 17 example: RSocket routes + metadata + JSON

This example uses Java 17, Spring Boot **3.4.13**, and a TCP server. Endpoints:

| Route | Interaction | Contract |
| --- | --- | --- |
| orders.get.{id} | Request-Response | Route ID + clientTag metadata -> OrderView |
| orders.list | Request-Stream | ListQuery -> Flux<OrderView> |
| audit.log | Fire-and-Forget | One String, no response data |
| text.upper | Request-Channel | Flux<String> -> Flux<String> |

### 11.1. Project structure

~~~text
rsocket-routing-demo/
├── build.gradle
└── src/
    ├── main/
    │   ├── java/demo/RsocketApplication.java
    │   ├── java/demo/OrderController.java
    │   ├── java/demo/OrderView.java
    │   ├── java/demo/ListQuery.java
    │   ├── java/demo/MetadataConfiguration.java
    │   └── resources/application.properties
    └── test/java/demo/RsocketIntegrationTest.java
~~~

### 11.2. build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.4.13'
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
    implementation 'org.springframework.boot:spring-boot-starter-rsocket'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Spring Boot manages Jackson, Reactor, and RSocket versions. The starter provides JSON/CBOR codecs to serialize Java records.

### 11.3. application.properties

~~~properties
spring.application.name=rsocket-routing-demo
spring.rsocket.server.port=7000
spring.rsocket.server.transport=tcp
spring.rsocket.server.address=127.0.0.1
~~~

The server binds loopback for local testing. For remote access across machines, configure networking, firewalls, TLS, and authentication; never expose an unprotected raw TCP service to the Internet.

### 11.4. RsocketApplication.java

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RsocketApplication {

    public static void main(String[] args) {
        SpringApplication.run(RsocketApplication.class, args);
    }
}
~~~

### 11.5. OrderView.java

~~~java
package demo;

public record OrderView(
    String id,
    String status,
    String clientTag
) {}
~~~

### 11.6. ListQuery.java

~~~java
package demo;

public record ListQuery(int limit) {}
~~~

### 11.7. MetadataConfiguration.java

Register extraction of custom metadata from a `text/plain` entry and name the extracted header `clientTag`:

~~~java
package demo;

import org.springframework.boot.rsocket.messaging.RSocketStrategiesCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.util.MimeTypeUtils;

@Configuration
public class MetadataConfiguration {

    @Bean
    RSocketStrategiesCustomizer clientTagMetadata() {
        return strategies ->
            strategies.metadataExtractorRegistry(registry ->
                registry.metadataToExtract(
                    MimeTypeUtils.TEXT_PLAIN,
                    String.class,
                    "clientTag"
                )
            );
    }
}
~~~

`metadataToExtract` registers the MIME type, Java type, and header name. The client only needs a `String`/`text/plain` encoder to send metadata. The responder must have a matching decoder.

### 11.8. OrderController.java

~~~java
package demo;

import java.util.Locale;

import org.springframework.messaging.handler.annotation.DestinationVariable;
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.stereotype.Controller;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Controller
public class OrderController {

    @MessageMapping("orders.get.{id}")
    public Mono<OrderView> get(
            @DestinationVariable("id") String id,
            @Header("clientTag") String clientTag) {

        return Mono.just(new OrderView(
            id, "accepted", clientTag
        ));
    }

    @MessageMapping("orders.list")
    public Flux<OrderView> list(ListQuery query) {
        int count = Math.max(0, Math.min(query.limit(), 5));

        return Flux.range(1, count)
            .map(i -> new OrderView(
                "O-" + i, "queued", "server"
            ));
    }

    @MessageMapping("audit.log")
    public Mono<Void> audit(String message) {
        return Mono.fromRunnable(() ->
            System.out.println("audit: " + message)
        );
    }

    @MessageMapping("text.upper")
    public Flux<String> uppercase(Flux<String> messages) {
        return messages.map(text ->
            text.toUpperCase(Locale.ROOT)
        );
    }
}
~~~

The `get` route returns one `OrderView`; `list` returns multiple items; `audit` has no response data; `uppercase` receives and returns a stream. The cap of 5 in `list` is a demo rule to avoid arbitrary requests producing too many results.

### 11.9. RsocketIntegrationTest.java

The test starts a real TCP server on a random port. `@LocalRSocketServerPort` supplies the actual RSocket port, not an HTTP port.

~~~java
package demo;

import java.time.Duration;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.rsocket.server.LocalRSocketServerPort;
import org.springframework.messaging.rsocket.RSocketRequester;
import org.springframework.util.MimeTypeUtils;

import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest(properties = "spring.rsocket.server.port=0")
class RsocketIntegrationTest {

    @LocalRSocketServerPort
    int port;

    @Autowired
    RSocketRequester.Builder builder;

    private RSocketRequester requester;

    @BeforeEach
    void connect() {
        requester = builder
            .dataMimeType(
                MimeTypeUtils.parseMimeType("application/json")
            )
            .tcp("127.0.0.1", port);
    }

    @AfterEach
    void dispose() {
        if (requester != null) {
            requester.rsocket().dispose();
        }
    }

    @Test
    void routeVariableAndTextMetadata() {
        StepVerifier.create(
            requester.route("orders.get.{id}", "42")
                .metadata("web", MimeTypeUtils.TEXT_PLAIN)
                .retrieveMono(OrderView.class)
        )
        .assertNext(value -> {
            assertEquals("42", value.id());
            assertEquals("accepted", value.status());
            assertEquals("web", value.clientTag());
        })
        .verifyComplete();
    }

    @Test
    void requestStreamUsesJsonData() {
        StepVerifier.create(
            requester.route("orders.list")
                .data(new ListQuery(3))
                .retrieveFlux(OrderView.class)
        )
        .expectNextMatches(v -> v.id().equals("O-1"))
        .expectNextMatches(v -> v.id().equals("O-2"))
        .expectNextMatches(v -> v.id().equals("O-3"))
        .verifyComplete();
    }

    @Test
    void channelStreamsBothDirections() {
        StepVerifier.create(
            requester.route("text.upper")
                .data(Flux.just("alpha", "beta"))
                .retrieveFlux(String.class)
        )
        .expectNext("ALPHA", "BETA")
        .verifyComplete();
    }

    @Test
    void fireAndForgetCompletesWithoutDataResponse() {
        StepVerifier.create(
            requester.route("audit.log")
                .data("order-42 opened")
                .send()
        )
        .verifyComplete();
    }

    @Test
    void unknownRouteEmitsError() {
        StepVerifier.create(
            requester.route("unknown.route")
                .retrieveMono(OrderView.class)
        )
        .expectError()
        .verify(Duration.ofSeconds(5));
    }
}
~~~

The tests cover route variables, `text/plain` metadata, JSON DTOs in Request-Stream, channels, fire-and-forget, and unknown-route errors. Completion of `send()` does not prove the audit side effect was committed, so the test does not assert that.

### 11.10. Running the demo

Run tests:

~~~bash
./gradlew test
~~~

On Windows:

~~~powershell
.\gradlew.bat test
~~~

Run server:

~~~bash
./gradlew bootRun
~~~

On Windows:

~~~powershell
.\gradlew.bat bootRun
~~~

The application listens on TCP port 7000 when running `bootRun`, whereas in the integration test port 0 lets the OS pick a free port. Clients should inject Boot's pre-configured `RSocketRequester.Builder`; if calling `RSocketRequester.builder()` directly, configure compatible JSON/CBOR codecs before sending Java records.

## 12. Testing metadata, MIME, and errors

### 12.1. Missing required metadata

If a handler uses `@Header("clientTag")` while a request omits the corresponding entry, argument resolution can fail. For required metadata, fail explicitly. For optional metadata, set sensible defaults and document them in the contract.

Never treat a self-declared `clientTag` as an authenticated principal.

### 12.2. Data MIME mismatch

If a requester selects `text/plain` yet tries to send a complex DTO unsupported by the encoder, failure can happen immediately on the client. If the server lacks a decoder for the declared data MIME, the request fails at the codec layer. Do not try to fix it by changing routes.

### 12.3. Metadata MIME mismatch

If a client uses a metadata format incompatible with the route extractor, the server may fail to locate the route. Check:
- Metadata MIME declared in SETUP.
- Is composite metadata used when multiple entries are needed?
- Does the routing entry use the routing extension MIME?
- Is custom metadata MIME registered in `MetadataExtractor`?
- Does the codec decode the metadata value properly?

### 12.4. Unknown route

When a route has no handler, the requester typically receives an error at the RSocket messaging layer. Do not call it HTTP 404: TCP RSocket does not return HTTP status codes for interactions.

### 12.5. Testing demand with StepVerifier

~~~java
StepVerifier.create(
    requester.route("orders.list")
        .data(new ListQuery(3))
        .retrieveFlux(OrderView.class),
    0
)
.thenRequest(1)
.expectNextCount(1)
.thenRequest(2)
.expectNextCount(2)
.verifyComplete();
~~~

This tests requester demand. To evaluate real memory behavior, add load tests with concurrent connections/streams, buffer bounds, timeouts, and cancellations.

### 12.6. Useful error categorization

| Error | Where does it usually occur? |
| --- | --- |
| Unsupported codec | Encoding/decoding data or metadata |
| Route mismatch | Metadata extraction/routing |
| Missing header | Resolving extracted metadata |
| Validation error | Handler/business service |
| Authorization failure | Security/interceptor/handler |
| Timeout/cancel | Connection or stream lifecycle |

Categorization helps fix the right layer instead of randomly tweaking MIME types or routes.

## 13. Designing routes and metadata for production

### 13.1. A contract should document everything

| Route | Interaction | Data MIME | Input | Metadata | Output |
| --- | --- | --- | --- | --- | --- |
| orders.get.{id} | Request-Response | JSON | None | clientTag (demo) | OrderView |
| orders.list | Request-Stream | JSON | ListQuery | None | Flux<OrderView> |
| audit.log | FNF | JSON | String | Auth in production | No data |
| text.upper | Channel | JSON | Flux<String> | None | Flux<String> |

Authorized routes must specify required scopes/roles and the subject to check. In production, do not use `text/plain` `clientTag` for authentication.

### 13.2. Keep metadata small

Metadata is meant for routes, traces, tokens, and small control fields. Do not put large files or entire business DTOs inside metadata. Set limits for frames/messages, concurrent requests, and metadata size.

### 13.3. Backpressure and cancellation

Request-Stream and Channel interactions can be long-lived. Use `Flux` rather than collecting all items into a list; do not manually `subscribe()` inside controllers; bound prefetch/concurrency when using `flatMap`; clean up resources on cancel/disconnect. Backpressure support in the protocol does not guarantee bounded memory if the application creates unbounded queues itself.

### 13.4. Versioning and migration

When making breaking schema changes:
1. Publish the new contract.
2. Run v1/v2 routes side by side if needed.
3. Add tests for both old and new clients.
4. Monitor traffic on the old route.
5. Retire the old route on an announced schedule.

### 13.5. Observability

Log routes (without tokens), interaction types, outcomes, latencies, message sizes, corresponding connection IDs, error types, and cancellation states. Mask sensitive tokens/metadata; never place personal data into metric tags with unbounded cardinality.

## 14. Common mistakes and fixes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Thinking route is an HTTP URL | Calling wrong path or confusing transport | Routes live in RSocket metadata |
| Sending route as data | Handler not found | Use `requester.route(...)` |
| Forgetting composite metadata | Cannot send route and extra metadata properly together | Use compatible metadata MIME |
| Thinking `@Header` reads all entries automatically | `clientTag` not received | Register `metadataExtractorRegistry` |
| Registering `metadataToExtract` without a decoder | Cannot decode metadata | Provide decoder for the MIME type |
| Confusing `dataMimeType` and `metadataMimeType` | Codec/routing errors | Distinguish the two SETUP MIME types |
| Using HTTP Accept/Content-Type for TCP routes | Wrong model | Choose MIME on the RSocket connection |
| Creating requester builder without Jackson | DTO encode/decode fails | Use Boot-managed builder or register strategies |
| Using `@GetMapping` for RSocket | Handler not invoked | Use `@MessageMapping` |
| Concatenating routes with variables containing dots | Wrong separator/matching | Use route templates and `@DestinationVariable` |
| Thinking `send()` confirms business commit | Wrong status assumption | Use Request-Response with a receipt |
| `@ConnectMapping` returning object data | Invalid SETUP contract | Return `void` or `Mono<Void>` |
| Awaiting requests on the connection during SETUP | Can deadlock handshake | Decouple outbound requests until after connect |
| Calling `block` inside handlers | Can block the event loop | Return `Mono`/`Flux` |
| Skipping route authorization checks | Privilege escalation | Verify principal and resource |
| Trusting client-sent tenant/tag | Metadata spoofing | Authenticate and authorize independently |
| Using unbounded queues on streams | Memory grows when client is slow | Bound queues/buffers, respect demand |
| Not testing MIME mismatches | Bugs surface only at integration | Test codecs, routes, metadata, and errors |

## 15. Implementation checklist

1. **Route:** stable names, namespaced, no collisions?
2. **Matcher:** route variables and dots tested?
3. **Interaction:** `Mono`/`Flux` matching Request-Response/FNF/Stream/Channel?
4. **SETUP:** data MIME and metadata MIME agreed upon?
5. **Composite:** multiple metadata entries represented properly?
6. **Routing:** `message/x.rsocket.routing.v0` MIME and matching extractor configured?
7. **Custom metadata:** MIME, decoder, and header name registered?
8. **Codecs:** JSON/CBOR/text supported with same contract on client and server?
9. **Transport:** TCP port or WebSocket mapping path correct?
10. **Security:** peer authenticated, routes/resources authorized?
11. **Limits:** frame size, concurrency, and buffers bounded?
12. **Backpressure:** request stream/channel honor demand?
13. **Schema:** versioning and migration plan defined?
14. **Tests:** route variables, `@Header` metadata, MIME, request stream, channel, unknown route tested?
15. **Operations:** logs/metrics do not leak tokens or sensitive data?

**Takeaway:** An RSocket route is logical metadata, not an HTTP URL. `RSocketRequester.route()` creates routing metadata; `@MessageMapping` and `RSocketMessageHandler` dispatch to handler methods. Data MIME and metadata MIME are declared at SETUP, and composite metadata allows carrying routing alongside extra metadata. To use `@Header` with new metadata, register a metadata extractor/decoder in `RSocketStrategies`. Choose data formats explicitly, test codecs and routing end-to-end, and enforce authorization at both connection and interaction levels.

## References

- Spring Framework — RSocket, RSocketRequester, Annotated Responders, MetadataExtractor: https://docs.spring.io/spring-framework/reference/rsocket.html
- Spring Boot 3.4 — RSocket Auto-configuration, TCP and WebSocket: https://docs.spring.io/spring-boot/3.4/reference/messaging/rsocket.html
- Spring Framework — RSocketRequester Java API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/rsocket/RSocketRequester.html
- Spring Framework — RSocketStrategies Java API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/rsocket/RSocketStrategies.html
- Spring Framework — MetadataExtractor API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/rsocket/MetadataExtractor.html
- Spring Boot — RSocket Properties: https://docs.spring.io/spring-boot/3.4/appendix/application-properties/index.html
- RSocket — Routing Metadata Extension: https://github.com/rsocket/rsocket/blob/master/Extensions/Routing.md
- RSocket — Composite Metadata Extension: https://github.com/rsocket/rsocket/blob/master/Extensions/CompositeMetadata.md
