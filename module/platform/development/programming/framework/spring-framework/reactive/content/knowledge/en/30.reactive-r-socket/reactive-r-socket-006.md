# @MessageMapping and Handlers Returning Mono and Flux in Spring RSocket

## 1. Lesson Objectives

RSocket is a binary, reactive-oriented messaging protocol supporting bidirectional exchange over TCP, WebSocket, and other byte-stream transports. Spring Framework provides an **annotated responder** model: instead of manually manipulating individual RSocket frames, you write a `@Controller` with `@MessageMapping` and return `Mono<T>`, `Flux<T>`, or `Mono<Void>`.

After this lesson, you can:

- Accurately identify the meaning of `@MessageMapping`, route metadata, and payloads.
- Distinguish the four interaction types: request-response, request-stream, fire-and-forget, and request-channel.
- Understand why Spring inspects **the cardinality of both input and output**, not just the return type.
- Write methods taking `@Payload T`, `Mono<T>`, `Flux<T>` and returning `Mono<R>`, `Flux<R>`, `Mono<Void>`.
- Call responders via `RSocketRequester.route(...).data(...).retrieveMono(...)`, `retrieveFlux(...)`, or `send()`.
- Handle backpressure, completion, errors, and cancellation.
- Run a Spring Boot RSocket TCP server and a Java 17 client to exercise all four interactions.

RSocket is **different from** an HTTP REST controller or a raw `WebSocketHandler`. RSocket `@MessageMapping` does not automatically create REST endpoints; routes live in the metadata of an RSocket request. Each RSocket connection can multiplex multiple request streams.

## 2. RSocket Protocol Overview

The four RSocket interactions:

| Interaction | Data from requester | Data from responder | Example |
| --- | --- | --- | --- |
| **Request-Response** | At most one initial payload | One response payload | Look up one product's details |
| **Request-Stream** | At most one initial payload | Multiple response payloads | Stream processing progress |
| **Fire-and-Forget** | At most one initial payload | No response data | Send best-effort events |
| **Request-Channel** | Stream of payloads from requester | Zero, one, or many response payloads | Chat, bidirectional sensor stream processing |

Illustration:

~~~text
REQUEST_RESPONSE
Requester   -- request --> Responder
Requester   <-- response -- Responder

REQUEST_STREAM
Requester   -- request --> Responder
Requester   <-- data 1 --- Responder
Requester   <-- data 2 --- Responder
Requester   <-- ... ------ Responder
Requester   <-- complete - Responder

FIRE_AND_FORGET
Requester   -- event ----> Responder
             (no response payload)

REQUEST_CHANNEL
Requester   -- data 1 ---> Responder
Requester   <-- reply A -- Responder
Requester   -- data 2 ---> Responder
Requester   <-- reply B -- Responder
Requester   -- complete -> Responder
Requester   <-- complete - Responder
~~~

Do not equate **fire-and-forget** with "the server processed it successfully." The `Mono` returned by the send operation on the requester only indicates the send was performed per the contract, not a business acknowledgment from the responder.

### 2.1. Setup, route, and MIME types

An RSocket connection starts with a `SETUP` frame. Both sides negotiate data MIME type and metadata MIME type. On each request, messages typically carry:

- **Data**: business payload, e.g. String, JSON, CBOR, or Protobuf.
- **Metadata**: information for routing, authentication, or other context.
- **Route**: logical destination, e.g. `products.find`, usually placed inside routing metadata.

`@MessageMapping("products.find")` is selected by Spring when the request's routing metadata contains the matching route. A route is not an HTTP path and does not use HTTP methods GET/POST.

If requester and responder use incompatible codecs or MIME types, the route may match yet the payload will still fail to decode.

### 2.2. Backpressure across network boundaries

When a requester receives a request-stream or channel, it sends demand to the responder. RSocket transmits demand via frames such as `REQUEST_N`. This keeps the responder from emitting infinitely when the requester only wants a certain number of items.

In Java, `Flux` and `Mono` implement Reactive Streams semantics, so cancellation, demand, and errors in the pipeline can propagate down to the RSocket layer.

Even so, backpressure does not replace memory limits or protect against a hot source emitting data without respecting demand.

## 3. What is @MessageMapping?

`@MessageMapping` marks a method that handles RSocket messages by route. Basic form:

~~~java
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.stereotype.Controller;
import reactor.core.publisher.Mono;

@Controller
public class ProductResponder {

    @MessageMapping("products.find")
    public Mono<String> findProduct(String productId) {
        return Mono.just("Product " + productId);
    }
}
~~~

Once Spring Messaging RSocket infrastructure is configured, `RSocketMessageHandler` scans `@Controller` classes and annotated methods to select handlers.

This code illustrates handler shape. To explicitly bind simple payload types like `String`, the standalone runnable example later uses `@Payload`:

~~~java
@MessageMapping("products.find")
public Mono<String> findProduct(@Payload String productId) {
    return Mono.just("Product " + productId);
}
~~~

### 3.1. @MessageMapping is not @GetMapping

| API | Protocol | Routing mechanism |
| --- | --- | --- |
| `@GetMapping("/products/{id}")` | HTTP | URL path and GET method |
| `@PostMapping("/products")` | HTTP | URL path and POST method |
| `@MessageMapping("products.find")` | RSocket | Route metadata in RSocket message |
| `@ConnectMapping` | RSocket | Connection-level SETUP or METADATA_PUSH |

The same annotation name `@MessageMapping` also appears in Spring messaging for STOMP/WebSocket. This lesson covers only **Spring RSocket annotated responders**, not STOMP broker destinations or `@SendTo` in WebSocket messaging.

### 3.2. Methods can reside in @Controller

In Spring Boot:

~~~java
@Controller
class CatalogController {

    @MessageMapping("catalog.greet")
    Mono<String> greet(@Payload String name) {
        return Mono.just("Hello " + name);
    }
}
~~~

Use `@Controller`; `@RestController` is unnecessary. Spring Boot with the RSocket starter can auto-configure `RSocketMessageHandler` and `RSocketStrategies`. You do not need to manually instantiate `RSocketMessageHandler` in a Boot sample project when auto-configuration is active.

## 4. Rules determining the interaction type

This is the most critical aspect of `@MessageMapping`: Spring inspects **the potential cardinality of both the input payload and output**.

### 4.1. Input/output cardinality

| Cardinality | Common types | Meaning |
| --- | --- | --- |
| 0 (input) | No payload parameter | No request data needed |
| 1 (input) | `T`, `Mono<T>` | One input payload |
| Many (input) | `Flux<T>` | Stream of input payloads |
| 0 (output) | `void`, `Mono<Void>` | Emits no response value |
| 1 (output) | `T`, `Mono<T>` | One response value |
| Many (output) | `Flux<T>` | Stream of response values |

### 4.2. Standard mapping table

| Input | Output | RSocket interaction |
| --- | --- | --- |
| 0 or 1 | 0 | Fire-and-Forget **or** Request-Response with no response data |
| 0 or 1 | 1 | Request-Response |
| 0 or 1 | Many | Request-Stream |
| Many | 0, 1, or Many | Request-Channel |

Examples:

~~~java
@MessageMapping("hello")
Mono<String> hello(@Payload String name) { ... }
// Input 1 -> Output 1 => Request-Response.

@MessageMapping("numbers")
Flux<String> numbers(@Payload String count) { ... }
// Input 1 -> Output Many => Request-Stream.

@MessageMapping("record")
Mono<Void> record(@Payload String event) { ... }
// Input 1 -> Output 0 => typically used for Fire-and-Forget.

@MessageMapping("transform")
Flux<String> transform(@Payload Flux<String> values) { ... }
// Input Many -> Output Many => Request-Channel.
~~~

**Do not assume "returning Flux means request-channel."** A handler receiving a single payload and returning `Flux` is **request-stream**. A handler receiving a `Flux` payload is **request-channel**, regardless of whether the final output is 0, 1, or many elements.

### 4.3. Why does Many input determine a channel?

In RSocket, ordinary requests such as request-response or request-stream have only one initial request payload. For the requester to keep sending multiple payloads within the same interaction, the protocol requires request-channel.

Thus, when a handler declares:

~~~java
Mono<String> summarize(@Payload Flux<String> lines) { ... }
~~~

it is a Many-input, 1-output channel; **not** request-response merely because the output is `Mono<String>`.

## 5. Handlers returning Mono<T>: Request-Response

Use `Mono<T>` when one request requires a single response.

~~~java
@MessageMapping("user.greet")
public Mono<String> greet(@Payload String name) {
    return Mono.just("Hello, " + name);
}
~~~

Client:

~~~java
Mono<String> reply = requester.route("user.greet")
        .data("Mai")
        .retrieveMono(String.class);
~~~

Explanation:

1. `route("user.greet")` places routing metadata into the request.
2. `data("Mai")` sets a single input payload.
3. `retrieveMono(String.class)` requests one response value.
4. Subscribing triggers the exchange; the client receives `onNext(reply)` then `onComplete()`, or `onError()`.

`Mono.just(...)` suits an already available value. If the work involves asynchronous I/O, return the `Mono` produced by the service:

~~~java
@MessageMapping("products.find")
public Mono<Product> find(@Payload String id) {
    return productService.findById(id);
}
~~~

Never call `block()` inside an RSocket handler. Return the `Mono` so the framework manages subscriptions and network lifecycles.

### 5.1. Mono<T> input

You can declare a reactive payload input:

~~~java
@MessageMapping("products.normalize")
public Mono<String> normalize(@Payload Mono<String> input) {
    return input
            .map(String::trim)
            .map(String::toUpperCase);
}
~~~

This lets you process the payload inside the chain, including decode errors and cancellation. However, a `Mono<T>` input still has cardinality 1; it does not turn the interaction into request-channel.

### 5.2. Mono.empty() in request-response

`Mono.empty()` completes without emitting a value. This is not an empty String and not HTTP 204. For a requester expecting a value, the result can be an empty `Mono` or behave according to the RSocket interaction contract. Define "not found" semantics explicitly:

- You can use a response DTO with an explicit status.
- You can emit an appropriate application error.
- Only use `Mono.empty` when clients are designed to handle empty completion.

## 6. Handlers returning Flux<T>: Request-Stream

Use `Flux<T>` when a single input request should receive a sequence of responses.

~~~java
@MessageMapping("numbers.generate")
public Flux<Integer> generate(@Payload Integer count) {
    if (count < 0 || count > 100) {
        return Flux.error(
                new IllegalArgumentException("count out of range"));
    }

    return Flux.range(1, count);
}
~~~

Client:

~~~java
Flux<Integer> numbers = requester.route("numbers.generate")
        .data(5)
        .retrieveFlux(Integer.class);
~~~

When the subscriber requests 5 items, the responder can emit 1, 2, 3, 4, 5 in order and complete. Request-stream supports backpressure across the network.

Example using `Flux.interval`:

~~~java
@MessageMapping("ticks")
public Flux<Long> ticks(@Payload String topic) {
    return Flux.interval(Duration.ofSeconds(1))
            .take(5);
}
~~~

This is a finite stream. If you omit `take(5)`, the stream can run indefinitely until the client cancels or the connection closes. Enforce resource limits or idle/timeout policies per contract.

### 6.1. Client canceling mid-stream

~~~java
requester.route("ticks")
        .data("system")
        .retrieveFlux(Long.class)
        .take(3)
        .doFinally(signal ->
                log.info("ticks ended: {}", signal))
        .subscribe();
~~~

`take(3)` completes after three items and cancels upstream if the stream has not ended. RSocket propagates cancellation accordingly. This is an illustrative snippet; inside controllers/services, avoid creating detached subscriptions when a caller already owns the lifecycle.

### 6.2. Do not call collectList() on an infinite stream

Do not do this:

~~~java
// Wrong for infinite streams: there is no completion for collectList to return a result.
requester.route("events")
        .retrieveFlux(Event.class)
        .collectList();
~~~

`collectList()` buffers every item in memory and emits the `List` only when the stream completes. For continuous streams, use `subscribe` at application boundaries or compose per-event pipelines, limit concurrency, and protect memory.

## 7. Handlers returning Mono<Void>: Fire-and-Forget

For an event needing no response data:

~~~java
@MessageMapping("audit.record")
public Mono<Void> record(@Payload AuditEvent event) {
    return auditService.save(event);
}
~~~

`auditService.save(...)` must return `Mono<Void>` (or another `Mono` adapted via `then()`). Spring subscribes to the result within the handler lifecycle.

Client call:

~~~java
Mono<Void> sent = requester.route("audit.record")
        .data(event)
        .send();
~~~

**Distinguish very clearly:**

- `send()` on the requester performs fire-and-forget. Its `Mono<Void>` **does not confirm that business logic on the server finished saving the event**.
- `Mono<Void>` on the responder describes work handled by the application, letting the framework track completion/errors.
- If the business case needs confirmation, e.g. "whether saving the audit succeeded or failed," use request-response with an acknowledgment DTO.

### 7.1. Do not subscribe inside a handler

Avoid this:

~~~java
@MessageMapping("audit.record")
public Mono<Void> record(@Payload AuditEvent event) {
    auditService.save(event).subscribe(); // Anti-pattern.
    return Mono.empty();
}
~~~

Reason: the side effect is detached from error/cancellation propagation and the request lifecycle. Return `auditService.save(event)` directly or compose with `then()`.

### 7.2. Output 0 does not always mean fire-and-forget

According to the official cardinality table, input 0/1 and output 0 can correspond to **fire-and-forget or request-response without response data**. The actual interaction is selected by the requester via APIs like `send()` or `retrieveMono(...)` and must be compatible with the handler.

Do not conclude solely from a method signature that every request-response must return a payload.

## 8. Handlers receiving Flux<T>: Request-Channel

Request-channel is a bidirectional streaming channel within a single RSocket interaction.

~~~java
@MessageMapping("texts.upper")
public Flux<String> upper(@Payload Flux<String> inputs) {
    return inputs
            .map(String::trim)
            .map(String::toUpperCase);
}
~~~

Client:

~~~java
Flux<String> requests = Flux.just(
        "alpha", "beta", "gamma");

Flux<String> replies = requester.route("texts.upper")
        .data(requests, String.class)
        .retrieveFlux(String.class);
~~~

RSocket handles both streams:

- The requester sends elements from `requests`.
- The responder receives them as `Flux<String>`.
- The responder emits transformed elements.
- The requester receives `replies` as `Flux<String>`.

Both directions can operate simultaneously. There is no need to finish sending all requests before starting to receive responses.

### 8.1. Flux<T> input, Mono<R> output

A channel does not have to return `Flux`.

~~~java
@MessageMapping("readings.sum")
public Mono<Long> sum(@Payload Flux<Long> readings) {
    return readings
            .reduce(0L, Long::sum);
}
~~~

Many input, 1 output is still request-channel. Yet this requires a finite stream: `reduce` emits its result only when the inbound stream completes. With an infinite stream, the result will never arrive without limits or windowing.

### 8.2. Flux<T> input, Mono<Void> output

~~~java
@MessageMapping("readings.store")
public Mono<Void> store(@Payload Flux<Reading> readings) {
    return readings
            .concatMap(readingService::save)
            .then();
}
~~~

Many input, 0 output is still request-channel. The client must choose a compatible interaction and understand that channel completion can be a protocol event, not a business acknowledgment message.

### 8.3. When to use concatMap, flatMap, limitRate?

| Operator | Effect | When to use |
| --- | --- | --- |
| `map` | Synchronously transforms each element | Lightweight CPU logic |
| `concatMap` | Runs inner publishers sequentially in order | Need to preserve order, avoid overwriting state |
| `flatMap` | Runs inner publishers concurrently | Independent messages |
| `flatMapSequential` | Processes concurrently yet emits results in order | Need both throughput and ordering |
| `limitRate` | Shapes upstream demand request pattern | Need controlled demand distribution |

Example handling I/O inside a channel with bounded concurrency:

~~~java
@MessageMapping("items.enrich")
public Flux<EnrichedItem> enrich(@Payload Flux<Item> items) {
    return items.flatMap(
            enrichmentService::enrich,
            8);
}
~~~

Choose concurrency based on downstream capacity. Do not use unbounded `flatMap` with a hot source when each message triggers heavy side effects.

## 9. Parameters supported by @MessageMapping

For Spring RSocket annotated responders, methods can accept:

| Parameter | Meaning |
| --- | --- |
| `@Payload T` | Payload decoded into a Java type |
| `@Payload Mono<T>` | Single payload wrapped in a Mono |
| `@Payload Flux<T>` | Stream of payloads; channel interaction |
| `RSocketRequester` | Requester pointing to the current peer, enabling server-to-client calls |
| `@DestinationVariable` | Variable extracted from the route pattern |
| `@Header` | Metadata registered for extraction |
| `@Headers Map<String,Object>` | Metadata values registered by the extractor |

### 9.1. @Payload

`@Payload` marks the parameter holding request data:

~~~java
@MessageMapping("orders.accept")
Mono<OrderResult> accept(@Payload OrderCommand command) {
    return orderService.accept(command);
}
~~~

The annotation may be omitted for some non-simple payload object parameters; using it explicitly avoids confusion with route variables or metadata, especially for `String` and numeric types.

### 9.2. @DestinationVariable

Routes can contain variables:

~~~java
@MessageMapping("orders.{orderId}.status")
public Mono<String> status(
        @DestinationVariable("orderId") String orderId,
        @Payload String request) {

    return Mono.just(orderId + ":" + request);
}
~~~

Client sends a route with a concrete variable:

~~~java
requester.route("orders.{orderId}.status", "ORD-42")
        .data("read")
        .retrieveMono(String.class);
~~~

Route variables do not replace payloads. Here `ORD-42` sits in routing metadata, while `read` is the data payload. Always verify access rights to `orderId` against the authenticated user; route variables come from the peer and are not proof of permission to read the resource.

### 9.3. @Header and @Headers

RSocket does not use HTTP headers per message. `@Header` in RSocket reads metadata registered with Spring's `MetadataExtractor`.

Structural example:

~~~java
@MessageMapping("orders.submit")
Mono<String> submit(
        @Header("traceId") String traceId,
        @Payload OrderCommand command) {

    return orderService.submit(command, traceId);
}
~~~

For this to work with a custom metadata MIME type, a matching metadata extractor and encoder/decoder must be configured. Do not assume any arbitrary metadata entry automatically becomes an `@Header`.

### 9.4. Receiving RSocketRequester

~~~java
@MessageMapping("peer.ask")
Mono<String> handle(
        @Payload String question,
        RSocketRequester peer) {

    return peer.route("client.answer")
            .data(question)
            .retrieveMono(String.class);
}
~~~

This is a bidirectional requester/responder example, which only works if the client also registers a responder for the `client.answer` route. An RSocket connection is symmetric on both sides: the server can initiate requests to the client, not merely reply.

Manage connection lifecycles, permissions, and deadlines when calling back to clients.

## 10. How does @ConnectMapping differ from @MessageMapping?

`@ConnectMapping` handles connection-level events:

- `SETUP` frame when establishing a connection.
- `METADATA_PUSH` frame during the connection.

Example:

~~~java
@Controller
class SetupController {

    @ConnectMapping
    public Mono<Void> connected(RSocketRequester requester) {
        return Mono.fromRunnable(() ->
                System.out.println("RSocket SETUP accepted"));
    }
}
~~~

Key differences:

- `@ConnectMapping` can only return `void` or `Mono<Void>`; it returns no payload data.
- If SETUP handling emits an error, the new connection can be rejected.
- When using `RSocketRequester` for the server to proactively call the client during SETUP, do not make a synchronous request and wait inside the SETUP handler itself because the connection setup has not completed yet; decouple that task asynchronously according to your architecture.
- `@MessageMapping` is for routed request interactions sent after connection setup.

If authentication is needed at SETUP, use official Spring Security RSocket authentication/authorization mechanisms instead of blindly trusting a token simply because it appears in metadata.

## 11. Client-side RSocketRequester

`RSocketRequester` is the Spring-level facade for building requests, encoding data/metadata, and decoding responses.

### 11.1. Creating a TCP requester

~~~java
RSocketRequester requester = RSocketRequester.builder()
        .tcp("127.0.0.1", 7000);
~~~

Connections are established on demand when a request actually runs; the builder creates a requester bound to the endpoint and allows sharing the connection across multiple streams.

In Spring Boot, inject Boot's auto-configured `RSocketRequester.Builder` to obtain the right `RSocketStrategies` and codecs:

~~~java
@Service
public class PartnerRSocketClient {

    private final RSocketRequester requester;

    public PartnerRSocketClient(RSocketRequester.Builder builder) {
        this.requester = builder.tcp("partner.internal", 7000);
    }

    public Mono<String> greet(String name) {
        return requester.route("greet")
                .data(name)
                .retrieveMono(String.class);
    }
}
~~~

Boot provides a prototype-scoped builder because the builder is stateful. Do not share one mutable builder to configure multiple requesters with different setups.

### 11.2. Creating a requester over WebSocket transport

~~~java
URI address = URI.create("ws://localhost:8080/rsocket");

RSocketRequester requester = RSocketRequester.builder()
        .webSocket(address);
~~~

The server must actually configure RSocket over WebSocket. This is still **the RSocket protocol running over WebSocket transport**, distinct from a plain WebFlux `WebSocketHandler`.

### 11.3. Corresponding call APIs

| Requirement | Requester API | Common handler |
| --- | --- | --- |
| One request, one response | `route(...).data(x).retrieveMono(T.class)` | `Mono<T> handler(T)` |
| One request, many responses | `route(...).data(x).retrieveFlux(T.class)` | `Flux<T> handler(T)` |
| Send without response data | `route(...).data(x).send()` | `Mono<Void> handler(T)` |
| Stream input and output | `route(...).data(flux, T.class).retrieveFlux(R.class)` | `Flux<R> handler(Flux<T>)` |

Specify the input element type for a `Publisher` using the `data(Publisher, Class)` overload (or corresponding `ParameterizedTypeReference` variant) so Spring can select the encoder.

### 11.4. Using metadata

~~~java
requester.route("secure.profile")
        .metadata(token, tokenMimeType)
        .data(userId)
        .retrieveMono(Profile.class);
~~~

`metadata(value, mimeType)` attaches metadata by MIME type. When using composite metadata, each entry has its own MIME type. Client and server must agree on the metadata MIME type during SETUP.

Never log tokens. In production, use TLS and proper security middleware.

## 12. Spring Boot RSocket auto-configuration

Main dependency:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-rsocket</artifactId>
</dependency>
~~~

This starter provides the RSocket implementation and necessary encoding/decoding components. Spring Boot can:

- Auto-configure `RSocketStrategies`.
- Auto-configure `RSocketMessageHandler` to discover annotated responders.
- Create a standalone RSocket server when a port is configured.
- Provide `RSocketRequester.Builder` for clients.
- Register CBOR or JSON codecs based on dependencies and configuration.

### 12.1. Standalone TCP server

~~~properties
spring.application.name=rsocket-demo
spring.rsocket.server.port=7000
spring.rsocket.server.transport=tcp
~~~

Even without configuring an HTTP server, RSocket can run standalone with its own TCP server. HTTP `server.port` is not the RSocket TCP port.

### 12.2. RSocket over WebSocket in a WebFlux server

For WebFlux and Reactor Netty applications:

~~~yaml
spring:
  rsocket:
    server:
      transport: websocket
      mapping-path: /rsocket
~~~

The web layer must be configured as a reactive WebFlux application. RSocket will run through the WebSocket endpoint under the configured path. Clients then use `RSocketRequester.Builder.webSocket(URI)`.

Not every WebSocket client speaks RSocket. A raw browser `new WebSocket(...)` does not generate an RSocket `SETUP` frame and cannot directly call `@MessageMapping`; an RSocket-over-WebSocket client is required.

### 12.3. MIME and codecs

A requester has `dataMimeType(MimeType)` and `metadataMimeType(MimeType)`. Server and client must agree. The runnable Java project below uses `text/plain` with `String` to keep codecs simple.

For DTOs, use JSON/CBOR/Protobuf via `RSocketStrategies`. Simply adding a Java DTO is not enough if the connection negotiates a MIME type without a matching decoder.

## 13. Runnable Spring Boot Java 17+ example: all four interactions

The project consists of an RSocket TCP server with `@MessageMapping` and a Java command-line client. The entire example uses only `String` to avoid differing JSON configuration dependencies across environments.

**Requirements:** JDK 17+, Maven 3.6.3+, and Spring Boot **4.1.2**. This is the stable Spring Boot release published on 23/10/2026; compatible dependencies are managed by the Spring Boot BOM.

### 13.1. Directory structure

~~~text
rsocket-message-mapping-demo/
  pom.xml
  src/main/resources/application.properties
  src/main/java/example/rsocket/RSocketDemoApplication.java
  src/main/java/example/rsocket/RSocketLessonController.java
  src/main/java/example/rsocket/RSocketClientDemo.java
~~~

### 13.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>example</groupId>
    <artifactId>rsocket-message-mapping-demo</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.2</version>
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
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.3.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 13.3. TCP server configuration

**src/main/resources/application.properties**

~~~properties
spring.application.name=rsocket-message-mapping-demo
spring.rsocket.server.port=7000
spring.rsocket.server.transport=tcp
~~~

### 13.4. Entry point

**src/main/java/example/rsocket/RSocketDemoApplication.java**

~~~java
package example.rsocket;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RSocketDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(
                RSocketDemoApplication.class, args);
    }
}
~~~

### 13.5. Annotated controller

**src/main/java/example/rsocket/RSocketLessonController.java**

~~~java
package example.rsocket;

import java.util.Locale;

import org.springframework.messaging.handler.annotation.DestinationVariable;
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.stereotype.Controller;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Controller
public class RSocketLessonController {

    // Request-Response: one String in, one String out.
    @MessageMapping("greet")
    public Mono<String> greet(@Payload String name) {
        return Mono.just("Hello, " + name);
    }

    // Request-Stream: one String in, multiple Strings out.
    @MessageMapping("count")
    public Flux<String> count(@Payload String rawCount) {
        int count;
        try {
            count = Integer.parseInt(rawCount);
        }
        catch (NumberFormatException error) {
            return Flux.error(
                    new IllegalArgumentException(
                            "count must be an integer", error));
        }

        if (count < 0 || count > 100) {
            return Flux.error(new IllegalArgumentException(
                    "count must be between 0 and 100"));
        }

        return Flux.range(1, count)
                .map(index -> "n=" + index);
    }

    // Request-Channel: Flux in, Flux out.
    @MessageMapping("upper")
    public Flux<String> upper(@Payload Flux<String> input) {
        return input.map(text ->
                "UPPER:" + text.toUpperCase(Locale.ROOT));
    }

    // Fire-and-Forget: one event in, no response data returned.
    @MessageMapping("audit")
    public Mono<Void> audit(@Payload String event) {
        return Mono.fromRunnable(() ->
                System.out.println("AUDIT:" + event));
    }

    // Request-Response with route variable.
    @MessageMapping("greet.{lang}")
    public Mono<String> greetWithLanguage(
            @DestinationVariable("lang") String lang,
            @Payload String name) {

        String prefix = "vi".equals(lang)
                ? "Xin chao, "
                : "Hello, ";

        return Mono.just(prefix + name);
    }
}
~~~

Explanation:

- `greet` takes one String and emits one String: **request-response**.
- `count` takes a count String and emits multiple Strings: **request-stream**.
- `upper` takes `Flux<String>` and returns `Flux<String>`: **request-channel**.
- `audit` returns `Mono<Void>`: used as **fire-and-forget** from the client.
- `greetWithLanguage` demonstrates reading the `lang` variable from route metadata.

The example caps `count` at 100 to prevent an invalid request from emitting excessive data. Production logic requires authorization, rate limits, and business quotas.

### 13.6. Java client calling the routes

**src/main/java/example/rsocket/RSocketClientDemo.java**

~~~java
package example.rsocket;

import java.time.Duration;
import java.util.List;

import org.springframework.messaging.rsocket.RSocketRequester;
import org.springframework.util.MimeTypeUtils;

import reactor.core.publisher.Flux;

public class RSocketClientDemo {

    public static void main(String[] args) {
        RSocketRequester requester = RSocketRequester.builder()
                .dataMimeType(MimeTypeUtils.TEXT_PLAIN)
                .tcp("127.0.0.1", 7000);

        try {
            // 1. Request-Response
            String greeting = requester.route("greet")
                    .data("RSocket")
                    .retrieveMono(String.class)
                    .block(Duration.ofSeconds(5));

            System.out.println("response=" + greeting);

            // 2. Request-Stream
            List<String> stream = requester.route("count")
                    .data("3")
                    .retrieveFlux(String.class)
                    .collectList()
                    .block(Duration.ofSeconds(5));

            System.out.println("stream=" + stream);

            // 3. Request-Channel
            List<String> channel = requester.route("upper")
                    .data(
                            Flux.just("one", "two", "three"),
                            String.class)
                    .retrieveFlux(String.class)
                    .collectList()
                    .block(Duration.ofSeconds(5));

            System.out.println("channel=" + channel);

            // 4. Route variable
            String localized = requester
                    .route("greet.{lang}", "vi")
                    .data("Ban")
                    .retrieveMono(String.class)
                    .block(Duration.ofSeconds(5));

            System.out.println("route-variable=" + localized);

            // 5. Fire-and-Forget
            requester.route("audit")
                    .data("opened")
                    .send()
                    .block(Duration.ofSeconds(5));

            System.out.println("fnf=sent");
        }
        finally {
            requester.dispose();
        }
    }
}
~~~

**Note:** `block(Duration)` is used only at the command-line demo entry point to wait for results; never call block inside Spring reactive services/handlers. `dispose()` closes the requester at the end of the program.

### 13.7. Running the server and client

Open the first terminal in the project directory:

~~~bash
mvn clean package
mvn spring-boot:run
~~~

Once the server is listening on TCP port 7000, open a second terminal:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=example.rsocket.RSocketClientDemo
~~~

**Expected business stdout lines from the client:**

~~~text
response=Hello, RSocket
stream=[n=1, n=2, n=3]
channel=[UPPER:ONE, UPPER:TWO, UPPER:THREE]
route-variable=Xin chao, Ban
fnf=sent
~~~

Maven may print additional logs depending on configuration. The order of the client's business lines is as shown above because the client waits for each request to complete before issuing the next.

**The server may print:**

~~~text
AUDIT:opened
~~~

The `AUDIT:opened` line on the server is a side effect of fire-and-forget; when it appears relative to `fnf=sent` on the client is not guaranteed. `fnf=sent` only confirms the send operation per the client API, not that the event was durably processed.

### 13.8. When should you replace String with DTOs?

For real-world APIs, use Java records and JSON/CBOR codecs:

~~~java
public record FindProductRequest(String productId) {
}

public record ProductReply(String id, String name) {
}

@MessageMapping("products.find")
public Mono<ProductReply> find(
        @Payload FindProductRequest request) {

    return productService.findById(request.productId());
}
~~~

This is an extension snippet requiring an application-defined service and matching codecs. The Spring Boot RSocket starter helps configure codecs, though both sides must agree on the MIME type at SETUP. Do not assume the server will understand any DTO while the client sends `text/plain`.

## 14. Reactive error handling in @MessageMapping

### 14.1. Error is a terminal signal

~~~java
@MessageMapping("orders.find")
public Mono<Order> find(@Payload String id) {
    return orderRepository.findById(id)
            .switchIfEmpty(Mono.error(
                    new OrderNotFoundException(id)));
}
~~~

If the publisher emits an error, the framework translates it into the interaction's RSocket error semantics. The client receives the error signal in `retrieveMono` or `retrieveFlux`.

Do not return an error Object as if it were a success response unless the contract has a distinguishing field. Standardize error codes, deserialization, and retry policies.

### 14.2. Validation in reactive flows

~~~java
@MessageMapping("count.safe")
public Flux<Integer> safeCount(@Payload String raw) {
    return Mono.fromCallable(() -> Integer.parseInt(raw))
            .flatMapMany(count -> {
                if (count < 1 || count > 1000) {
                    return Flux.error(new IllegalArgumentException(
                            "count must be between 1 and 1000"));
                }
                return Flux.range(1, count);
            });
}
~~~

`Mono.fromCallable` defers parsing until subscription and turns exceptions into error signals. No separate thread is needed for a small parsing operation like this.

For DTO validation with Bean Validation, appropriate dependencies and argument validation configuration are required. Do not assume `@Payload` alone validates input.

### 14.3. Recoverable error handling inside a channel

~~~java
@MessageMapping("texts.safeUpper")
public Flux<String> safeUpper(@Payload Flux<String> input) {
    return input.concatMap(text -> {
        if (text.length() > 256) {
            return Mono.just("ERROR:too-long");
        }
        return Mono.just(text.toUpperCase(Locale.ROOT));
    });
}
~~~

If an error belongs to a single message and the protocol allows returning an error value and continuing, handle it inside the inner publisher so the entire channel does not emit a terminal error.

Conversely, authentication errors or dangerous protocol violations should be propagated as terminal errors to terminate the stream.

### 14.4. Do not swallow every exception

Avoid this:

~~~java
return service.call(input)
        .onErrorResume(error -> Mono.empty());
~~~

This makes clients lose the distinction between "no data" and "broken service." Only fall back on specific exceptions when business rules specify it, while keeping sufficient metrics/logs for investigation.

## 15. Demand, timeouts, cancellation, and backpressure

### 15.1. Limiting elements on the requester

~~~java
Flux<String> firstThree = requester.route("events")
        .data("topic-a")
        .retrieveFlux(String.class)
        .take(3);
~~~

The requester needs only three elements; `take` then cancels the unfinished upstream stream. RSocket has the `CANCEL` mechanism to notify the responder.

### 15.2. Time limits

~~~java
Mono<ProductReply> result = requester.route("products.find")
        .data(request)
        .retrieveMono(ProductReply.class)
        .timeout(Duration.ofSeconds(3));
~~~

A timeout on a Reactor Publisher can cancel the client-side request; the server may still have executed side effects before cancellation arrived. For write actions, design appropriate idempotency keys and retry policies.

With `Flux.timeout(Duration)`, the timer tracks intervals between items; it is not a total deadline for an infinite stream. Do not confuse it with connect/SETUP timeouts or connector keepalive.

### 15.3. Infinite streams and hot sources

RSocket request-stream/channel supports demand across the network, yet an upstream hot source can emit faster than demand is processed. Use bounded queues or appropriate drop/coalesce policies:

- State data may need only the latest snapshot.
- Events that must never be lost require persistence/replay.
- Commands with side effects need concurrency limits and explicit rejection when overloaded.
- Never use unbounded `onBackpressureBuffer()` for thousands of clients.

### 15.4. Preserving order

`concatMap` preserves request order when each element requires I/O processing. `flatMap` may reorder results. Choose the operator based on the contract, not throughput alone.

For bidirectional channels, do not assume a response corresponds positionally to an input if the responder processes concurrently. If request-response correlation within a channel is required, include a `requestId` in the payload and echo it in the response DTO.

## 16. Connections, resource management, and security

### 16.1. One connection, many requests

After SETUP, one TCP/WebSocket connection can carry many request streams. Do not create a new connection per business request without a valid reason. Reuse the requester and manage lifecycles properly:

- Create the requester during service configuration.
- Reuse it across calls.
- Dispose of the requester on component/application shutdown, not after every call if it is a shared bean.
- Design reconnect/backoff, keepalive, resume, and leasing according to operational requirements.

### 16.2. @ConnectMapping and server calling client

The server can accept an `RSocketRequester` parameter in annotated handlers to call back to the client. However, the client must have a matching responder route. Never invoke and wait on a synchronous round-trip inside the SETUP handler before SETUP finishes.

If the server needs to push proactively, clearly define routes, access permissions, and connected requester lifecycles; when a connection closes, clean up registries and cancel streams.

### 16.3. Authentication and authorization

- Use TLS when transmitting credentials or sensitive data.
- Set up proper authentication with Spring Security RSocket and metadata authentication.
- Authorize every route and resource, not just based on route name.
- Never treat `@DestinationVariable` or payload IDs as proof of access permission.
- Control what information enters logs/traces.
- Bound frame sizes, payload sizes, stream counts, and throughput.
- Do not expose RSocket TCP ports publicly unless needed.

A route like `orders.{id}.find` must check whether the user is allowed to access that order. CORS is a browser policy for HTTP/WebSocket and cannot replace RSocket authentication/authorization at the appropriate transport layer.

### 16.4. Codecs and buffers

When using low-level `io.rsocket.Payload` or Netty buffers, you must manage reference counting. Spring annotated responders with standard DTOs and codecs avoid manual buffer handling. If passing pooled buffers across async boundaries, follow API ownership and retain/release rules.

## 17. Testing @MessageMapping

A meaningful test suite should cover:

| Scenario | What to verify |
| --- | --- |
| Valid Request-Response | `Mono` emits one typed value and completes |
| Finite Request-Stream | `Flux` emits items in expected order and count |
| Fire-and-Forget | Requester `send` completes; verify business side effect separately |
| Request-Channel | Input `Flux` received by responder, output `Flux` matches contract |
| Route variable | Value extracted properly from route metadata |
| Non-existent route | Requester receives appropriate route/handler error |
| Wrong MIME payload | Decoder reports error without misprocessing data |
| Invalid input | Emits clear application error |
| Client cancels stream | Responder stops emitting and cleans up resources |
| Slow requester | Demand does not trigger unbounded buffering |
| Connection drop/keepalive | Reconnects or errors per policy |
| Authentication/authorization | Unauthorized routes are rejected |
| Side effects on retry | Idempotency protects data from duplication |

You can use `StepVerifier` to test service publishers, for example:

~~~java
StepVerifier.create(
        Flux.range(1, 3).map(value -> "n=" + value))
        .expectNext("n=1", "n=2", "n=3")
        .verifyComplete();
~~~

This is a unit-test snippet; `reactor-test` is required in test scope. Real RSocket tests should call via `RSocketRequester` over TCP/WebSocket to verify routing metadata, SETUP, codecs, and interactions over the network.

### 17.1. Why not test Java methods directly only?

Calling `controller.greet("Mai")` like a normal method only verifies Java logic. It does not verify:

- Whether route metadata matches `@MessageMapping`.
- Whether the client selects the right interaction type.
- Whether codecs decode the payload.
- Whether setup MIME types are compatible.
- Whether RSocket request-stream/channel propagates demand and cancellation.

Therefore, use both unit tests for domain logic and integration tests through a requester.

## 18. Common mistakes when using @MessageMapping, Mono, and Flux

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Treating `@MessageMapping` as a REST endpoint | No matching HTTP GET/POST route | Call via `RSocketRequester` with route metadata |
| Checking only `Flux` return to conclude channel | Confusing request-stream with request-channel | Check both input and output cardinality |
| Taking `Flux` input while client calls request-response | Wrong interaction model | Use request-channel with `data(Publisher, Class)` |
| Returning `Mono<Void>` and assuming requester got an ACK | FNF does not confirm business success | Use request-response with an ACK DTO |
| Calling `subscribe()` inside a handler | Detaches work from lifecycle and errors | Return `Mono`/`Flux` directly |
| Calling `block()` inside a handler | Blocks the reactive event loop | Compose publishers |
| Using `collectList` on infinite streams | Accumulates memory and never completes | Process element by element |
| Using `flatMap` for order-dependent commands | Side effects may reorder | Use `concatMap` |
| Allowing `Flux.range` with unbounded `count` | Can cause excessive load | Validate and enforce limits |
| Forgetting `dataMimeType` or codecs | Cannot encode/decode DTOs | Align MIME types and `RSocketStrategies` |
| Putting route String in payload | Responder cannot find route | Use `route(...)` metadata |
| Reading `@Header` like an HTTP header | Missing metadata extractor/MIME | Configure metadata extractor |
| Calling requester inside `@ConnectMapping` and blocking | Can deadlock/block SETUP | Decouple asynchronously post-setup |
| Sharing one mutable requester builder for multiple configs | Mixed codecs/setup/routes | Use Boot prototype builder |
| Retrying non-idempotent POST-like actions after timeout | Can create duplicate side effects | Use idempotency keys |
| Trusting route variable as access permission | Exposes another user's data | Authorize every resource |
| Buffering infinite event streams | Memory pressure/leaks | Bounded queues/backpressure policy |
| Forgetting to dispose requester in CLI | Leaks connections/resources | Dispose at shutdown boundary |
| Only unit-testing annotated methods | Misses route/codec/interaction bugs | Integration test via `RSocketRequester` |

## 19. Production checklist

- [ ] Define consistent RSocket routes organized by namespace.
- [ ] Document the interaction type for every route in the API contract.
- [ ] Check input and output cardinality before choosing `Mono`/`Flux`.
- [ ] Use `@Payload`, `@DestinationVariable`, and metadata according to their responsibilities.
- [ ] Do not treat `@MessageMapping` as an HTTP route.
- [ ] Specify RSocket server port/transport explicitly in configuration.
- [ ] Align `dataMimeType`/`metadataMimeType` and codecs.
- [ ] Reuse `RSocketRequester` and dispose with application lifecycle.
- [ ] Never block or subscribe manually inside annotated handlers.
- [ ] Bound counts, payload sizes, concurrency, and stream durations per SLA.
- [ ] Choose `concatMap` when order matters.
- [ ] Never aggregate infinite streams.
- [ ] Enforce backpressure and bounded queues for hot sources.
- [ ] Propagate and handle errors/cancellations properly.
- [ ] Never mistake fire-and-forget for business acknowledgment.
- [ ] Configure timeouts, retry/backoff, and idempotency appropriately.
- [ ] Enforce authentication, authorization, TLS, and quotas.
- [ ] Never log tokens or sensitive payloads.
- [ ] Test all four interaction types with a client over a real transport.
- [ ] Monitor connection count, request count, latency, errors, cancellations, and queue depth.

## 20. Self-check

**Question 1.** How does `@MessageMapping` in RSocket route requests?

By the RSocket request's routing metadata, not by HTTP URL/method.

**Question 2.** A handler taking `String` and returning `Mono<String>` belongs to which interaction?

Request-response, because input has one payload and output has one response value.

**Question 3.** A handler taking `String` and returning `Flux<String>` belongs to which interaction?

Request-stream, because input is one payload and output is multiple items.

**Question 4.** A handler taking `Flux<String>` and returning `Flux<String>` belongs to which interaction?

Request-channel, because the input is a stream.

**Question 5.** Is a handler taking `Flux<String>` and returning `Mono<Long>` request-response?

No. Input is Many so it is request-channel, even though output is a single item.

**Question 6.** Which requester method is used for fire-and-forget?

`send()`, returning a `Mono<Void>` representing sending, not confirming business processing.

**Question 7.** Which API does the client use to receive multiple responses?

`retrieveFlux(ResponseType.class)`.

**Question 8.** Why is `@Payload` useful with `String`?

It explicitly marks the parameter as the data payload, avoiding confusion with route variables or metadata.

**Question 9.** Where does `@DestinationVariable` read data from?

From variables in the matched route pattern inside routing metadata.

**Question 10.** Does `@Header` read HTTP headers?

No. In RSocket it reads metadata registered by `MetadataExtractor`.

**Question 11.** Which events does `@ConnectMapping` handle?

`SETUP` and `METADATA_PUSH`; handlers only return `void` or `Mono<Void>`.

**Question 12.** Why must you not call `block` inside an RSocket handler?

Because blocking stalls reactive threads and breaks asynchronous processing.

**Question 13.** How does backpressure work in RSocket request-stream?

The requester signals demand; the responder emits according to demand and RSocket transmits that information via control frames such as `REQUEST_N`.

**Question 14.** When a client uses `take(3)` on a stream, what can happen?

After three items, the client cancels the upstream stream; cancellation is propagated to the responder.

**Question 15.** What does a server returning `Mono.empty` mean?

Completion without emitting response data—not an empty string or an HTTP status.

**Question 16.** Why must you write integration tests via `RSocketRequester`?

To verify route metadata, `SETUP`, MIME/codecs, interaction models, demand, and transport—not just Java method logic.

## 21. Official References

- [Spring Framework — RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html): protocol overview, `RSocketRequester`, annotated responders, `@MessageMapping`, `@ConnectMapping`, and cardinality table.
- [Spring Framework — RSocketRequester JavaDoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/rsocket/RSocketRequester.html): route, data, `retrieveMono`, `retrieveFlux`, `send`, `dispose`.
- [Spring Framework — RSocketMessageHandler JavaDoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/rsocket/annotation/support/RSocketMessageHandler.html): controller discovery and handling annotated RSocket messages.
- [Spring Framework — MessageMapping JavaDoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/handler/annotation/MessageMapping.html): message route mapping and method-level contract.
- [Spring Framework — ConnectMapping JavaDoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/handler/annotation/ConnectMapping.html): handling RSocket `SETUP`/`METADATA_PUSH`.
- [Spring Boot — RSocket](https://docs.spring.io/spring-boot/4.1/reference/messaging/rsocket.html): starter, auto-configuration, TCP/WebSocket server, `RSocketRequester.Builder`, and codecs.
- [Spring Boot 4.1.2 Release Announcement](https://spring.io/blog/2026/10/23/spring-boot-4-1-2-available-now/): stable release on 23/10/2026.
- [RSocket Protocol — Interaction Models](https://rsocket.io/about/protocol/): request-response, request-stream, request-channel, fire-and-forget, and `REQUEST_N`/`CANCEL`.
- [Reactor Core — Flux](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html): streams, backpressure, `concatMap`, `flatMap`, cancellation.
- [Reactor Core — Mono](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html): single-value publisher, error, and completion.

**Key takeaway:** `@MessageMapping` routes RSocket requests by metadata. A `Mono<T>` handler with single input is typically request-response; a `Flux<T>` handler with single input is request-stream; `Mono<Void>` is typically used for fire-and-forget; and **any handler receiving a `Flux<T>` payload belongs to request-channel**. Identify input/output cardinality, use the right `RSocketRequester` API, let the framework manage subscriptions, and protect streams with validation, backpressure, timeouts, cancellation, and authorization.