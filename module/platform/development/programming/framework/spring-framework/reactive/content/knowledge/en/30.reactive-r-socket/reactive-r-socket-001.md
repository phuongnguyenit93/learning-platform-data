# RSocket and the Need for Bidirectional Reactive Communication

## 1. Why is bidirectional reactive communication needed?

In many distributed applications, the classic HTTP request-response model remains very effective: the client sends a request, the server returns a response, and the interaction ends. However, some problems require exchanging data continuously or alternately in both directions over the same connection:

- A dashboard continuously receiving updated prices, telemetry, or device status.
- A chat/dispatching application needing to both send messages and receive notifications.
- A gateway exchanging events with multiple backend services.
- An IoT device sending sensor data and receiving control commands.
- A service needing to stream results while the client continues supplying input.
- A system needing to protect the producer when the consumer is slow (backpressure).

This can be partially solved with HTTP polling, Server-Sent Events (SSE), WebSocket, or a message broker. However, for reactive services that need streaming, multiplexing, and flow control at the protocol level, `RSocket` is worth exploring.

`RSocket` is a binary application-level protocol that runs over TCP, WebSocket, or other byte-stream transports. It provides symmetric interaction models, full-duplex communication, backpressure support for streaming flows, and multiplexes multiple logical streams over a single physical connection.

**Bidirectional does not mean both sides send at the same time on every request.** RSocket supports multiple patterns: one request and one response, one-way, streaming results, and request-channel allowing two data streams to occur simultaneously.

Lesson goal: understand the real-world problem RSocket solves, grasp the four interaction models, the requester/responder architecture, demand/cancellation, differences from HTTP/SSE/WebSocket, and implement a Java 17 + Spring Boot example using `@MessageMapping` and `RSocketRequester`.

## 2. What is RSocket and how does it work?

### 2.1. Requester and responder instead of fixed client/server

When opening a TCP/WebSocket connection, one side initiates the connection and the other listens. Once the RSocket connection is established, **either side can act as a requester or responder** for independent interactions.

- **Requester** initiates an interaction.
- **Responder** handles the interaction and sends appropriate signals.
- Each logical interaction has its own stream identifier so messages do not get mixed up.
- One physical connection can simultaneously carry multiple interactions.

~~~text
                      One TCP / WebSocket connection
+------------------------+  <==================>  +------------------------+
| Service A              |                        | Service B              |
| requester + responder  | -- request  stream 1 ->| responder              |
|                        |<- response stream 1 ---|                        |
| responder              |<- request  stream 3 ---| requester              |
|                        |-- response stream 3 -->|                        |
| requester              |<== channel stream 5 ==>| responder              |
+------------------------+                        +------------------------+
~~~

If Service A initiates the connection, that does **not** mean Service B can only reply. Once Service B has the connection's `RSocketRequester` and Service A has registered a responder, Service B can also proactively invoke routes on A.

### 2.2. An interaction is not a TCP connection

RSocket multiplexes multiple logical streams over a single connection. For example, a client can send a catalog lookup request, receive a price stream, and conduct a request-channel chat without creating a new TCP connection for each task.

Multiplexing reduces connection overhead and creates a unified model, though it does not eliminate physical limits: multiple streams still share network bandwidth, CPU, buffers, and connection congestion.

### 2.3. Establishing a connection

The client sends a `SETUP` frame with settings such as data MIME type and metadata MIME type. The server can accept or reject the SETUP. Once the connection is established, both sides begin sending request frames.

~~~text
Initiator                            Acceptor
    | --- TCP/WebSocket connect -----> |
    | -------- RSocket SETUP --------> |
    | <------ setup accepted ----------|
    | -- REQUEST_RESPONSE (stream 1)-> |
    | <--------- PAYLOAD --------------|
    | -- REQUEST_STREAM (stream 3) --> |
    | <---- PAYLOAD, PAYLOAD,... ------|
    | --------- CANCEL --------------> |
~~~

Details about when the server is allowed to send requests during SETUP must follow the lifecycle. In Spring, `@ConnectMapping` handles SETUP; you must not wait for a server-initiated request to complete inside the SETUP callback itself, because the connection needs to be accepted first.

### 2.4. Data, metadata, and route

An RSocket payload consists of **data** (business content) and **metadata** (control information, routing, security, tracing, etc.). MIME types for data and metadata are negotiated during SETUP.

Spring commonly uses composite metadata to hold multiple independent metadata entries, where routing metadata helps select a `@MessageMapping` such as `orders.created` or `telemetry.readings`. A route is a logical destination, **not an HTTP URL**.

Example:

~~~java
Flux<String> updates = requester
    .route("telemetry.readings")
    .data("sensor-A")
    .retrieveFlux(String.class);
~~~

There is no HTTP method, status 200, or Authorization header like a typical REST endpoint. With RSocket, metadata/routes and error signals have their own semantics.

## 3. The four interaction models of RSocket

RSocket has four core patterns. This is the most important difference from a protocol that only provides byte streams or messages without application-level cardinality.

| Model | Requester input sent | Responder output returned | Common Spring API | Use case |
| --- | --- | --- | --- | --- |
| **Request-Response** | 0–1 item | 1 item | `retrieveMono(T.class)` | Information lookup |
| **Fire-and-Forget** | 0–1 item | No response payload | `send()` | Best-effort event sending |
| **Request-Stream** | 0–1 item | Multiple items | `retrieveFlux(T.class)` | Telemetry/price monitoring |
| **Request-Channel** | Stream of multiple items | Stream of multiple items | `data(Flux, type).retrieveFlux(T.class)` | Chat, control, real-time processing |

In Spring Messaging, the interaction type is largely inferred from the number of inputs and outputs. If the input is a multi-element Publisher, it is Request-Channel; the output can be empty, one, or many items depending on the handler. With 0–1 input and multiple output items, it is Request-Stream. Avoid assuming "many inputs, one output" is equivalent to request-response: that is still a channel.

### 3.1. Request-Response

Send one request and receive one response. It is similar in shape to HTTP request-response but uses RSocket frames and metadata instead of HTTP.

~~~text
Requester                      Responder
   | ----- REQUEST_RESPONSE ----->|
   |<----------- PAYLOAD ----------|
   |        COMPLETE/error         |
~~~

Spring client:

~~~java
Mono<String> greeting = requester
    .route("demo.hello")
    .data("Linh")
    .retrieveMono(String.class);
~~~

Server:

~~~java
@MessageMapping("demo.hello")
public Mono<String> hello(@Payload String name) {
    return Mono.just("Xin chào, " + name);
}
~~~

Suitable for a single-result lookup. Only use `retrieveMono` if the contract truly returns at most one value.

### 3.2. Fire-and-Forget

The requester sends a message **without waiting for a business response**:

~~~java
Mono<Void> sent = requester
    .route("demo.notify")
    .data("Order created")
    .send();
~~~

`send()` returns `Mono<Void>` indicating that the message has been sent according to the RSocket contract; **it does not guarantee the receiving side has processed it, saved to the database, or committed a transaction**.

~~~text
Requester                     Responder
   | ------ REQUEST_FNF --------->|
   |  no application response     |
~~~

Do not use Fire-and-Forget for payments or commands requiring business acknowledgment, unless you already have separate protocol acknowledgment/idempotency and delivery guarantees. If you need to know the server succeeded, use Request-Response or emit an acknowledgment via another interaction.

### 3.3. Request-Stream

Send one request to receive multiple results from the server. For example, receiving 3 ticks:

~~~java
Flux<String> ticks = requester
    .route("demo.ticks")
    .data("3")
    .retrieveFlux(String.class);
~~~

~~~text
Requester                        Responder
   | ------ REQUEST_STREAM -------->|
   |<--------- PAYLOAD 1 -----------|
   |<--------- PAYLOAD 2 -----------|
   |<--------- PAYLOAD 3 -----------|
   |<---------- COMPLETE -----------|
~~~

The consumer can adjust demand, and when data is no longer needed, can cancel the stream. This model fits price feeds, telemetry, live progress, and queries returning multiple results incrementally.

### 3.4. Request-Channel: two independent data streams

This is the pattern that clearly demonstrates bidirectional communication: the requester sends a stream and the responder returns a stream. Both directions can have different speeds and lifecycles; the responder does not necessarily wait for the requester to finish sending all items before responding.

~~~java
Flux<String> outbound = Flux.just("a", "b", "c")
    .delayElements(Duration.ofMillis(100));

Flux<String> inbound = requester
    .route("demo.uppercase")
    .data(outbound, String.class)
    .retrieveFlux(String.class);
~~~

~~~text
Requester                       Responder
   | ------- REQUEST_CHANNEL ----->|
   | -------- DATA "a" ----------->|
   |<------- DATA "ECHO:A" --------|
   | -------- DATA "b" ----------->|
   |<------- DATA "ECHO:B" --------|
   | -------- DATA "c" ----------->|
   |<------- DATA "ECHO:C" --------|
   | ------- COMPLETE -----------> |
   |<-------- COMPLETE ----------- |
~~~

This model suits interactive processing, conversation streams, devices sending sensor readings while receiving responses, and sessions with continuous state exchange.

Note the distinction: Request-Channel enables two sides to exchange data within one interaction. **A server initiating a new request to the client** is an additional duplex capability, requiring the client to register a responder and the server to have an `RSocketRequester` for the connection.

### 3.5. Metadata-Push is not a fifth business request pattern

The RSocket protocol has a `METADATA_PUSH` frame to send connection-level metadata without attaching it to a specific request. In a Spring requester, `sendMetadata()` is used for this mechanism. This is a protocol capability, not a replacement for the four core interaction models above.

## 4. Backpressure, multiplexing, and stream lifecycle

### 4.1. Backpressure across the network

In Reactive Streams, downstream expresses consumption demand through demand signals. RSocket extends this mechanism across the network boundary in Request-Stream and Request-Channel.

The protocol uses `REQUEST_N` to transmit the number of items the receiving side is ready to process. When the consumer requests fewer items, the responder should not send beyond the demand granted for that stream direction.

~~~text
Consumer                                    Producer
   | -------- request(2) / REQUEST_N --------> |
   | <---------------- item 1 ---------------- |
   | <---------------- item 2 ---------------- |
   | -------- request(1) / REQUEST_N --------> |
   | <---------------- item 3 ---------------- |
   | ---------------- CANCEL ----------------> |
~~~

Spring + Reactor allow `request(n)` or operators like `take(n)` and `limitRate(n)` to participate in flow control. RSocket's backpressure is an advantage over raw WebSocket, where applications often have to design credits or queuing mechanisms themselves.

However, backpressure **does not automatically guarantee memory will never overflow**. A hot source, an unbounded queue, too many logical streams, or a handler holding too much state can still cause memory pressure. Always bound buffers, concurrency, subscriber counts, and publish rates.

### 4.2. Cancellation, complete, and error

An interaction has lifecycle signals:

- `PAYLOAD` carries data/metadata.
- `COMPLETE` signals the sender has no more items.
- `ERROR` signals an error for the stream/interaction.
- `CANCEL` signals the receiver no longer needs data.
- `REQUEST_N` replenishes demand.

For example, a client needing only three items from a stream can use:

~~~java
Flux<String> firstThree = requester
    .route("prices.stream")
    .data("ABC")
    .retrieveFlux(String.class)
    .take(3);
~~~

After three items, `take(3)` completes and cancels upstream as needed. The sender must honor cancellation, releasing connection-specific resources, timers, and subscriptions. Do not treat cancellation as a business error.

### 4.3. Multiplexing does not mean unlimited concurrency

RSocket distinguishes logical streams by stream identifier on a single connection. It enables many interactions to run concurrently without needing one TCP connection per request.

However, all of them still share the network link. When designing, limit:

- The number of active channels and long-lived streams.
- The number of pending requests and wait timeouts.
- Payload size, fragmentation, and buffers.
- Reconnect and retry frequency.
- Message size per route and concurrent client count.

### 4.4. Keepalive, lease, resume, and fragmentation

The RSocket protocol supports advanced features:

- **Keepalive:** checks connection liveness.
- **Leasing:** grants permission to send a certain number of requests within a time window via `LEASE`.
- **Resumption:** resumes a session after disconnection if the implementation enables it and retains sufficient state.
- **Fragmentation/reassembly:** splits large messages into multiple frames when needed.

These capabilities **do not turn RSocket into durable messaging by default**. Session resumption must be configured and has state limits; it does not guarantee preserving messages across every restart or power loss. Critical transactions still require persistence, acknowledgments, conditional retries, and idempotency at the application layer.

## 5. Comparing RSocket, REST, SSE, and WebSocket

| Criterion | HTTP REST | SSE | Raw WebSocket | RSocket |
| --- | --- | --- | --- | --- |
| Communication style | Request–response | Server → client stream | Full duplex message | 4 reactive interaction models |
| Client sends data continuously in 1 interaction | Not a typical pattern | No | Yes | Yes, Request-Channel |
| Server push | Polling/long response/HTTP streaming | Yes | Yes | Yes, Request-Stream/channel and server-initiated requests |
| Application-level backpressure over protocol | Depends on stack/additional mechanism | No REQUEST_N equivalent | Self-designed | Built-in for streams via REQUEST_N |
| Multiplex logical requests/streams on one connection | HTTP/2 has transport multiplexing | Depends on HTTP transport | Self-designed ID/protocol | Built-in stream identifiers |
| Metadata routing | URL/method/header | HTTP header | Self-designed | Composite metadata, route |
| Browser calls directly | Yes | Yes | Yes | Needs RSocket JavaScript client over WebSocket |
| Best suited for | CRUD, public APIs | One-way notifications | Realtime custom protocols | Reactive service-to-service, full duplex streams |

**RSocket does not replace all HTTP APIs.** HTTP has a vast ecosystem for browsers, CDNs, caches, gateways, HTTP semantics, observability, and public clients. RSocket is beneficial when its interaction patterns, bidirectional streaming, and network backpressure genuinely bring value.

**WebSocket is also full-duplex**, but it only provides message transport; the application must define its own routes, request IDs, completion, demand, error, and retry semantics. RSocket comes with request/stream models and flow control built in.

**SSE is simpler** for server → browser notifications, especially when the client does not need to stream back. Choose SSE if you only need one-way server push over HTTP instead of deploying the entire RSocket stack.

### 5.1. When should you choose RSocket?

Situations worth considering:

- Multiple microservices use Reactor and need to exchange bidirectional streams.
- Both client and server may proactively initiate requests.
- Source/consumer speeds differ and application-level backpressure is needed.
- Multiple logical interactions share a long-lived connection.
- Typed routing, metadata, and unified error/completion semantics via the RSocket protocol are needed.

When **not** to use it:

- Public APIs that are mainly CRUD request-response.
- Simple browsers that only need SSE.
- Systems needing durable queuing and replay after many days: a message broker is usually more suitable.
- Teams lacking the capability to operate and monitor long-lived connections.
- Existing middleware/gateways do not support RSocket.

## 6. How does Spring Framework support RSocket?

### 6.1. RSocketRequester

`RSocketRequester` is the fluent API from `spring-messaging` for sending requests with data and metadata at the Java object level. It hides most of the buffer/frame-level logic.

~~~java
Mono<String> result = requester
    .route("catalog.lookup")
    .data("SKU-001")
    .retrieveMono(String.class);
~~~

Key APIs to remember:

- `route("...")` puts the logical destination into routing metadata.
- `data(value)` sends a single payload, or `data(Flux, Class)` sends a payload stream.
- `retrieveMono(Target.class)` receives at most one result.
- `retrieveFlux(Target.class)` receives a stream of results.
- `send()` is used for Fire-and-Forget, returning `Mono<Void>`.
- `metadata(value, mimeType)` adds metadata to a request when using composite metadata.
- `sendMetadata()` sends connection-level metadata-push.

Usually a requester is created from `RSocketRequester.Builder`:

~~~java
RSocketRequester requester =
    RSocketRequester.builder().tcp("localhost", 7000);
~~~

Creating a requester does not mean the network is immediately connected. The connection is established when a request actually occurs; the requester reuses the connection according to its lifecycle.

### 6.2. @MessageMapping and @Payload

Spring supports annotated responders with `@Controller` and `@MessageMapping`:

~~~java
@Controller
public class CatalogRSocketController {

    @MessageMapping("catalog.lookup")
    public Mono<String> lookup(@Payload String sku) {
        return Mono.just("Product:" + sku);
    }
}
~~~

`@Payload` marks the parameter receiving request data. You can use `@DestinationVariable` for route parameters, `@Header` for metadata with registered extraction, or `RSocketRequester` to call the opposite side.

The route `catalog.lookup` is not an HTTP URL; do not use `@GetMapping` to handle RSocket frames.

### 6.3. @ConnectMapping and SETUP

`@ConnectMapping` handles SETUP (and related metadata pushes by route). The handler can return `void` or `Mono<Void>`; it does not return a business payload.

~~~java
@ConnectMapping
public void onConnect() {
    log.info("RSocket connection setup received");
}
~~~

If authentication is needed at SETUP, design the metadata format and security policy clearly. Do not block inside `@ConnectMapping` and do not wait for a server-initiated request to complete right inside SETUP.

### 6.4. RSocketStrategies and codecs

`RSocketStrategies` holds encoders/decoders, the route matcher, and serialization configurations. Spring Boot with `spring-boot-starter-rsocket` auto-configures `RSocketStrategies`. By default, Boot prefers CBOR via Jackson when applicable, followed by JSON depending on dependencies.

When manually creating a requester outside Boot, ensure data MIME types and decoders/encoders match the server. Do not expect complex DTOs to serialize properly without the appropriate Jackson codecs or strategies.

### 6.5. Route and composite metadata

By default, Spring uses routing metadata to match `@MessageMapping`. Additional metadata such as trace id, authentication, or protocol version can be included.

~~~java
MimeType authType =
    MimeType.valueOf("message/x.rsocket.authentication.bearer.v0");

Flux<String> data = requester
    .route("telemetry.watch")
    .metadata(accessToken, authType)
    .data("sensor-A")
    .retrieveFlux(String.class);
~~~

This only illustrates metadata placement. In production, use Spring Security RSocket and codecs for standard authentication metadata formats; do not send raw tokens with wrong encoding or assume metadata is automatically protected. When secrecy is required, configure TLS, restrict routes, and enforce authorization on both requester and responder sides.

### 6.6. @RSocketExchange

Spring Framework also offers RSocket service interfaces via `@RSocketExchange` and `RSocketServiceProxyFactory`. This is an option for declaring typed contracts for the requester. `@MessageMapping` is convenient for responders with many route patterns.

You can share the same service contract between client and server if the methods are designed appropriately for the capabilities of the interface proxy.

## 7. Spring Boot RSocket auto-configuration and transport

### 7.1. Starter and standalone TCP server

Spring Boot 3.5 provides `spring-boot-starter-rsocket` for RSocket server/client, Jackson CBOR/JSON strategies, and messaging infrastructure.

Standalone TCP server configuration:

~~~properties
spring.rsocket.server.port=7000
spring.rsocket.server.transport=tcp
spring.rsocket.server.address=127.0.0.1
~~~

RSocket port 7000 is **not an HTTP port**. Running `curl http://localhost:7000/...` will not speak the RSocket protocol.

Boot auto-configures `RSocketMessageHandler` to discover `@Controller` beans with `@MessageMapping`, and `RSocketRequester.Builder` for clients. The Builder in Boot is a prototype bean because it holds mutable configuration state; do not share a single mutable builder instance to create multiple requesters with different SETUP settings.

### 7.2. RSocket over WebSocket

If the WebFlux application uses Reactor Netty, RSocket WebSocket can be integrated with the web server:

~~~properties
spring.rsocket.server.transport=websocket
spring.rsocket.server.mapping-path=/rsocket
server.port=8080
~~~

Then the RSocket client can use the WebSocket transport at the appropriate URI, for example:

~~~java
RSocketRequester requester = builder
    .webSocket(URI.create("ws://localhost:8080/rsocket"));
~~~

Notes:

- `spring.rsocket.server.mapping-path` applies only to the WebSocket transport.
- Do not confuse a standalone TCP port with an HTTP server port.
- RSocket over WebSocket still carries RSocket binary frames, not plain JSON messages.
- Browsers need an RSocket client implementation supporting WebSocket; do not just call `new WebSocket(...)` and send arbitrary JSON.
- If using HTTPS, use WebSocket TLS `wss://` and an appropriate authentication policy.

### 7.3. Customizing RSocketStrategies

Boot lets you declare `RSocketStrategiesCustomizer` beans to add codecs or change route matching. `@Order` on customizers affects codec registration order.

Avoid changing the serialization strategy on one side without changing the other; SETUP MIME types and payload codecs must be compatible.

### 7.4. RSocketConnectorConfigurer

Boot provides `RSocketConnectorConfigurer` to tune the connector, such as keepalive, interceptors, or session resumption via low-level RSocket Java APIs.

This is an advanced extension point. Only enable lease/resume when genuinely required and after testing failure modes such as reconnects, duplicate processing, and message ordering.

## 8. Java 17 + Spring Boot 3.5.7 project: four real patterns

The project below runs an RSocket TCP server and a client integration test using RSocketRequester. It demonstrates all four patterns, where request-channel streams items client → server and receives streamed responses server → client.

### 8.1. Directory structure

~~~text
rsocket-duplex-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/example/rsocket/
    │   │   ├── RSocketDemoApplication.java
    │   │   └── DemoRSocketController.java
    │   └── resources/
    │       └── application.properties
    └── test/
        └── java/example/rsocket/
            └── RSocketPatternsTest.java
~~~

### 8.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>rsocket-duplex-demo</artifactId>
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

Use the RSocket starter instead of only adding `spring-boot-starter-webflux`. A standalone RSocket server does not need HTTP controllers.

### 8.3. application.properties

~~~properties
spring.main.web-application-type=none
spring.rsocket.server.port=7000
spring.rsocket.server.transport=tcp
spring.rsocket.server.address=127.0.0.1
logging.level.example.rsocket=INFO
~~~

The server listens for RSocket on loopback TCP 7000. When running in containers, adjust the address/network policy depending on your architecture. The test below overrides the port to 0 so the OS picks a free port.

### 8.4. RSocketDemoApplication.java

~~~java
package example.rsocket;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RSocketDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(RSocketDemoApplication.class, args);
    }
}
~~~

### 8.5. DemoRSocketController.java

~~~java
package example.rsocket;

import java.time.Duration;
import java.util.Locale;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.stereotype.Controller;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Controller
public class DemoRSocketController {

    private static final Logger log =
        LoggerFactory.getLogger(DemoRSocketController.class);

    // Request-Response: one input, one output.
    @MessageMapping("demo.hello")
    public Mono<String> hello(@Payload String name) {
        return Mono.just("Xin chào, " + name);
    }

    // Fire-and-Forget: no business response.
    @MessageMapping("demo.notify")
    public void notifyEvent(@Payload String event) {
        log.info("Received notification: {}", event);
    }

    // Request-Stream: one input, multiple outputs.
    @MessageMapping("demo.ticks")
    public Flux<String> ticks(@Payload String rawCount) {
        int count = Integer.parseInt(rawCount);
        if (count < 0 || count > 100) {
            return Flux.error(
                new IllegalArgumentException("count must be 0..100")
            );
        }

        return Flux.range(1, count)
            .delayElements(Duration.ofMillis(20))
            .map(index -> "tick-" + index);
    }

    // Request-Channel: streaming input and streaming output.
    @MessageMapping("demo.uppercase")
    public Flux<String> uppercase(@Payload Flux<String> incoming) {
        return incoming.map(value ->
            "echo:" + value.toUpperCase(Locale.ROOT));
    }
}
~~~

Explanation:

- The `hello` method returns `Mono<String>`, making it suitable for Request-Response.
- `notifyEvent` returns `void`; the client sends via `send()`. Logging illustrates handling, though send completion is not a business acknowledgment.
- `ticks` accepts one payload and returns `Flux<String>`, suitable for Request-Stream; the count limit prevents clients from requesting overly large streams.
- `uppercase` takes `Flux<String>` and returns `Flux<String>`, suitable for Request-Channel. Each input item can produce a response as it arrives without waiting for the entire input to complete.

### 8.6. RSocketPatternsTest.java

~~~java
package example.rsocket;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.time.Duration;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.messaging.rsocket.RSocketRequester;

import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

@SpringBootTest(properties = "spring.rsocket.server.port=0")
class RSocketPatternsTest {

    @Autowired
    RSocketRequester.Builder builder;

    @Value("${local.rsocket.server.port}")
    int port;

    private RSocketRequester requester;

    @BeforeEach
    void connectRequester() {
        requester = builder.tcp("127.0.0.1", port);
    }

    @AfterEach
    void disposeRequester() {
        if (requester != null) {
            requester.dispose();
        }
    }

    @Test
    void requestResponse() {
        StepVerifier.create(
                requester.route("demo.hello")
                    .data("Linh")
                    .retrieveMono(String.class))
            .expectNext("Xin chào, Linh")
            .verifyComplete();
    }

    @Test
    void fireAndForget() {
        // Completion of send() does not prove business handling.
        StepVerifier.create(
                requester.route("demo.notify")
                    .data("created:42")
                    .send())
            .verifyComplete();
    }

    @Test
    void requestStream() {
        StepVerifier.create(
                requester.route("demo.ticks")
                    .data("3")
                    .retrieveFlux(String.class))
            .expectNext("tick-1", "tick-2", "tick-3")
            .verifyComplete();
    }

    @Test
    void requestChannelDuplex() {
        Flux<String> input = Flux.just("a", "b", "c")
            .delayElements(Duration.ofMillis(15));

        StepVerifier.create(
                requester.route("demo.uppercase")
                    .data(input, String.class)
                    .retrieveFlux(String.class))
            .expectNext("echo:A", "echo:B", "echo:C")
            .verifyComplete();
    }

    @Test
    void requestStreamRespectsBoundedDemand() {
        Flux<String> stream = requester.route("demo.ticks")
            .data("3")
            .retrieveFlux(String.class);

        StepVerifier.create(stream, 0)
            .thenRequest(1)
            .expectNext("tick-1")
            .thenRequest(2)
            .expectNext("tick-2", "tick-3")
            .verifyComplete();
    }
}
~~~

In the test, `spring.rsocket.server.port=0` tells Boot to start the server on a random port. `local.rsocket.server.port` holds the actual port. Boot provides an `RSocketRequester.Builder` with server-compatible strategies.

`StepVerifier` verifies Publisher signals in order without blocking the production event loop. Since this test runs on the test thread, having `verifyComplete()` wait for results is normal.

### 8.7. Running the project

Requirements: Java 17+, Maven, and TCP port 7000 available if running the server in normal mode.

~~~bash
mvn test
~~~

When tests succeed, Maven reports that the RSocket request-response, fire-and-forget, stream, channel, and demand tests all pass. The tests open real connections to the RSocket TCP server started by Spring Boot on a random port.

Run the standalone server:

~~~bash
mvn spring-boot:run
~~~

At this point the server listens on RSocket TCP port 7000, with **no HTTP routes** to test via curl. To call the server outside JUnit tests, use Java `RSocketRequester`, RSocket CLI (`rsc`) with appropriate routing/MIME support, or an RSocket client in another language.

Do not place `subscribe()` or `block()` inside handlers just to perform these checks. In application code, return `Mono/Flux` so the framework manages subscriptions.

## 9. Server proactively calling the client: true duplex

Request-Channel already transfers data bidirectionally within the same logical interaction. However, RSocket also allows the server to open a **new request** to the client over the existing connection.

### 9.1. Registering a client responder

The client must have a handler for the route the server wants to call:

~~~java
public class ClientCallbackHandler {

    @MessageMapping("client.ping")
    public Mono<String> ping(@Payload String message) {
        return Mono.just("client-ack:" + message);
    }
}
~~~

The snippet above is an additional class, not part of the demo project in section 8. When registering a responder manually, configure RSocket strategies, route matcher, and SocketAcceptor:

~~~java
RSocketStrategies strategies = RSocketStrategies.builder()
    .routeMatcher(new PathPatternRouteMatcher())
    .build();

SocketAcceptor responder =
    RSocketMessageHandler.responder(
        strategies, new ClientCallbackHandler());

RSocketRequester requester = RSocketRequester.builder()
    .rsocketStrategies(strategies)
    .rsocketConnector(connector -> connector.acceptor(responder))
    .tcp("127.0.0.1", 7000);
~~~

This advanced example assumes the APIs are imported and the `spring-web` module is present for `PathPatternRouteMatcher`. For complex data types, register additional codecs compatible with the server.

### 9.2. Server receiving the client's requester

A `@MessageMapping` or `@ConnectMapping` on the server can receive the `RSocketRequester` for the current connection:

~~~java
@MessageMapping("server.ask-client")
public Mono<String> askClient(
    @Payload String question,
    RSocketRequester clientRequester
) {
    return clientRequester.route("client.ping")
        .data(question)
        .retrieveMono(String.class);
}
~~~

The server now becomes the requester for the `client.ping` route provided by the client.

**Do not confuse this:** The server cannot call a client route automatically if the client has not registered a suitable responder. Establishing a TCP/WebSocket connection does not automatically provide a list of client callbacks.

### 9.3. Be careful with the SETUP lifecycle

`@ConnectMapping` handles SETUP before the connection is ready to serve subsequent requests. If you want the server to ask the client for status right after connecting, decouple that call from the Mono/void handling SETUP; do not create a mutual wait deadlock.

In production, maintain the connection/requester map by session identity carefully; remove entries when connections close; limit session count; avoid keeping disposed requesters; and define authentication/authorization for both client→server and server→client directions.

## 10. Errors, timeouts, reconnects, and data safety

### 10.1. Error signals and timeouts

RSocket does not return HTTP 404 or 500 statuses the way REST does. Handlers can emit errors in the Publisher:

~~~java
@MessageMapping("demo.invalid")
public Mono<String> invalid(@Payload String data) {
    return Mono.error(
        new IllegalArgumentException("Invalid payload"));
}
~~~

The requester side receives the corresponding error signal. Do not assume every server-side exception preserves its exact Java type or message across the network; error mapping depends on RSocket/Spring and serialization.

Timeouts should be applied at the use-case layer:

~~~java
Mono<String> result = requester.route("demo.hello")
    .data("Linh")
    .retrieveMono(String.class)
    .timeout(Duration.ofSeconds(3));
~~~

A timeout causes the consumer to cancel the subscription when the deadline expires. You must handle the possibility that the server already executed side effects before the requester timed out. If a write operation might repeat, use an idempotency key or deduplication.

### 10.2. Retry, reconnect, and resumption

Do not retry every request when a connection resets. For read-only lookup Request-Response calls, conditional retries are usually safer. For payments, order creation, and Fire-and-Forget, retries can cause duplicate side effects.

A safe retry policy needs to:

- Retry only exceptions classified as transient.
- Cap the retry count and total deadline.
- Use exponential backoff with jitter.
- Consider idempotency and replayability of the input Publisher.
- Prevent reconnect storms when downstream services fail.
- Include circuit breakers/rate limits appropriate for the system.

RSocket resumption does not replace a database, persistent log, or durable queue. You must test restarts, prolonged network outages, and duplicate deliveries.

### 10.3. Security

RSocket traffic is not automatically encrypted or authenticated. You need to design:

1. TLS over TCP or secure WebSocket.
2. Identity and authentication in SETUP or request metadata using standard mechanisms.
3. Route-level and direction-level authorization.
4. Protection of tokens/credentials from logs and error messages.
5. Limits on payload size, concurrent streams, and requests per connection.
6. Validation of all client-sent routes and metadata without blind trust.
7. Authentication and authorization for server-initiated callbacks as well.

Spring Security supports RSocket Security for authentication/authorization. Do not invent an incompatible token format or skip TLS simply because connections are long-lived.

### 10.4. Observability

Record:

- Connection count, reconnects, and setup failures.
- Active streams by route.
- Stream duration, throughput, REQUEST_N/demand, and cancellations.
- Errors by route and error type.
- Payload sizes, buffer memory, and queue depth.
- Request-response latency and end-to-end channel processing latency.

Do not log raw payloads or metadata tokens by default. Use route names as low-cardinality tags; avoid putting user IDs or random session IDs into metric labels.

## 11. Common pitfalls when starting with RSocket

**Pitfall 1 — Calling RSocket with HTTP curl.** RSocket TCP ports use binary frames, not HTTP endpoints. Use `RSocketRequester` or another RSocket client.

**Pitfall 2 — Treating WebSocket and RSocket as the same protocol.** WebSocket is a message transport, whereas RSocket defines requester/responder roles, interaction models, metadata, demand, and error semantics.

**Pitfall 3 — Thinking RSocket request-channel is request-response.** A channel carries streams in both directions. Use `Flux` input and `retrieveFlux` when many-to-many is needed.

**Pitfall 4 — Sending a Flux but using retrieveMono and expecting multiple items.** Check input/output and handler cardinality; Spring infers the model from them.

**Pitfall 5 — Treating Fire-and-Forget as business-processed.** `send()` only signals the message was sent; it does not prove the DB committed.

**Pitfall 6 — Not managing subscriptions of long-lived streams.** Sources may keep running when the caller no longer needs them. Use cancel, dispose, and cleanup.

**Pitfall 7 — Ignoring backpressure with hot sources.** REQUEST_N only governs producers that respect demand. Unbounded queues can still overflow.

**Pitfall 8 — Passing DTOs without a Jackson codec.** Check `RSocketStrategies` and data MIME types on both sides.

**Pitfall 9 — Confusing route metadata with URLs.** `@MessageMapping` matches logical routes; do not use HTTP `@GetMapping` for RSocket.

**Pitfall 10 — Enabling WebSocket mapping-path and connecting to the wrong TCP port.** The WebSocket transport uses a URI and the WebFlux Reactor Netty server, unlike the standalone TCP server.

**Pitfall 11 — Reusing a mutable RSocketRequester.Builder across heterogeneous setups.** Boot's builder is prototype-scoped; build purpose-specific requesters without mutating a shared builder.

**Pitfall 12 — Using block() inside reactive controllers.** This can block the event loop. Keep `Mono/Flux` and process asynchronously.

**Pitfall 13 — Retrying non-idempotent requests blindly.** This easily causes duplicate side effects and retry storms. Define idempotency, backoff, and deadlines.

**Pitfall 14 — Believing resume guarantees durable delivery.** Resume requires state and configuration; it does not replace a durable message broker.

**Pitfall 15 — Having the server call the client when the client has no registered responder.** A `SocketAcceptor` and appropriate route handlers must be attached.

**Pitfall 16 — Waiting for a server→client request inside @ConnectMapping.** Incomplete setup can cause a deadlock. Decouple callbacks from the setup lifecycle.

**Pitfall 17 — Leaving TCP and metadata unsecured.** RSocket does not provide TLS, auth, or authorization policies by default.

**Pitfall 18 — Using RSocket for every CRUD endpoint.** Implementation/observability/gateway overhead is not worthwhile if you only need HTTP request-response.

## 12. Pre-production design checklist

1. Does the workload need request-response, Fire-and-Forget, request-stream, or request-channel?
2. Are duplex or server-initiated requests truly required?
3. Does the consumer need to control the producer with backpressure across the network?
4. Can the source emit data beyond demand or create unbounded queues?
5. Are payload sizes and active streams per connection bounded?
6. Should the transport be TCP or WebSocket? Does the browser have an RSocket JS client?
7. Are MIME types, codecs, and routing metadata compatible on both sides?
8. Are the SETUP lifecycle and `@ConnectMapping` non-blocking?
9. Is a client responder registered if the server needs to make reverse requests?
10. Are TLS, authentication, authorization, and metadata handling properly configured?
11. Have timeouts, cancellations, and cleanup on client disconnect been tested?
12. Do retries account for idempotency and replayable Publishers?
13. Is leasing/resumption sufficient, or is a durable message broker actually required?
14. Are there metrics for connections, demand, errors, and stream lifecycles?
15. Are there integration tests covering all four interaction models?

## 13. Self-check exercises

1. What is RSocket? **A binary application protocol providing multiplexed duplex reactive interactions over byte-stream transports.**
2. How does a "requester" differ from a "responder"? **The requester initiates an interaction; the responder handles it and returns signals.**
3. After SETUP, is the side that opened the TCP connection always the requester? **No; either side can initiate interactions.**
4. What are the four core patterns? **Request-Response, Fire-and-Forget, Request-Stream, Request-Channel.**
5. Which pattern has bidirectional streams within the same interaction? **Request-Channel.**
6. Which pattern sends one request and receives multiple items? **Request-Stream.**
7. Does `send()` prove the server processed the business logic successfully? **No, it only indicates the message was sent according to the protocol.**
8. What is the role of `REQUEST_N`? **It propagates consumer demand to the producer in a stream.**
9. What is the role of `CANCEL`? **It signals the stream is no longer needed, allowing the sender to stop and release resources.**
10. Can a single TCP connection carry multiple logical interactions? **Yes, through stream identifiers and multiplexing.**
11. Is an RSocket route an HTTP URL? **No; it is a logical destination in metadata.**
12. Which annotation creates a responder in Spring? **`@MessageMapping` on a `@Controller`.**
13. Which Spring Boot starter supports RSocket server/client? **`spring-boot-starter-rsocket`.**
14. Which Spring Boot property opens the TCP port? **`spring.rsocket.server.port`.**
15. Does RSocket over WebSocket in Boot use the mapping-path property? **Yes; combined with `transport=websocket`.**
16. Which component does DTO serialization depend on? **`RSocketStrategies` along with encoders/decoders and MIME types.**
17. Why doesn't request-channel automatically allow the server to call client callbacks? **A new server-initiated request requires the client to have a responder and the server to have the connection's requester.**
18. Can `@ConnectMapping` be used to wait for a server→client callback response? **No; SETUP must complete first.**
19. Why doesn't resumption replace a message broker? **It relies on in-memory state/limits and does not guarantee durable storage across all failures.**
20. When are HTTP/SSE more reasonable than RSocket? **When the application is mainly CRUD or only needs one-way server push to browsers.**

## 14. Key takeaways and references

- RSocket is a binary application protocol, not HTTP or raw WebSocket.
- Bidirectional communication has two levels: `Request-Channel` streams data in both directions, and **server-initiated requests** when the client also has a responder.
- Requester/responder are per-interaction roles, not immutable server/client roles.
- Four models: Request-Response, Fire-and-Forget, Request-Stream, and Request-Channel.
- `REQUEST_N` propagates demand across the network; `CANCEL` and `COMPLETE` manage stream lifecycles.
- Multiplexing lets multiple logical streams share a connection, yet concurrency/buffers must still be bounded.
- Spring uses `RSocketRequester` to call, `@MessageMapping` to handle, `@ConnectMapping` for setup, and `RSocketStrategies` for codecs.
- Spring Boot 3.5 provides `spring-boot-starter-rsocket`, TCP server properties, and WebSocket mapping paths.
- `send()` is not a business acknowledgment; TLS/security, timeouts, reconnects, idempotency, and observability are designed by the application.
- RSocket complements HTTP/SSE/WebSocket; choose based on interaction shape and operational requirements.

**Official documentation**

1. [Spring Framework — RSocket reference](https://docs.spring.io/spring-framework/reference/rsocket.html): overview, protocol, request patterns, RSocketRequester, annotated responders, and metadata.
2. [Spring Boot 3.5 — RSocket](https://docs.spring.io/spring-boot/3.5/reference/messaging/rsocket.html): starter, RSocketStrategies, TCP/WebSocket server, requester builder auto-configuration.
3. [RSocket Protocol Specification](https://rsocket.io/about/protocol/): SETUP, REQUEST_N, CANCEL, REQUEST_CHANNEL, REQUEST_FNF, leasing, resumption.
4. [Spring Framework — RSocketRequester Javadoc](https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/messaging/rsocket/RSocketRequester.html): fluent API, send, retrieveMono, retrieveFlux.
5. [Spring Boot 3.5 — RSocket properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html): TCP port, transport, mapping path, SSL, fragmentation.
6. [Project Reactor Reference](https://projectreactor.io/docs/core/release/reference/): Mono, Flux, subscribeOn, backpressure, retry, cancellation, and StepVerifier.
