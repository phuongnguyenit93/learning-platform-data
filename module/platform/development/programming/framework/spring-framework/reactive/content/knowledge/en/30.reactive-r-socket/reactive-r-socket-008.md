
# Choosing RSocket vs. WebClient, SSE, or WebSocket in Spring Reactive

## 1. Lesson Objectives

Not every reactive application needs RSocket. A typical CRUD API works well with HTTP and `WebClient`. A notification dashboard receiving updates from server to browser usually needs only Server-Sent Events (SSE). Real-time chat or games can use WebSocket. RSocket stands out when a system needs **multiple bidirectional interaction models, long-lived message streams, and protocol-level backpressure between processes**, while controlling client, server, and transport infrastructure.

This lesson answers:
- How do RSocket's four interaction models differ from HTTP request-response, SSE, and WebSocket?
- How does RSocket provide backpressure, multiplexing, keepalive, leasing, and resumption?
- How do you choose between WebClient, SSE, WebSocket, and RSocket based on data direction, clients, infrastructure, reliability, operations, and cost?
- When does RSocket add complexity with negligible benefit?
- How do you configure Spring Boot and Java 17+ to test an RSocket requester/responder with request-response, request-stream, request-channel, and fire-and-forget?
- How do you test, measure, and deploy a defensible architectural decision?

**Scope:** Spring Framework 6.2+/7.x, Spring Boot 3.5.x, and Reactor. The runnable exercise uses Spring Boot 3.5.x and Java 17+, separating standalone code from illustrative snippets.

## 2. Positioning the four concepts accurately

Before comparing, avoid a categorization mistake:

- **WebClient** is Spring WebFlux's HTTP client API. It sends HTTP/1.1 or HTTP/2 depending on the connector; it can fetch a JSON response, download files, or read a streaming HTTP response such as SSE.
- **SSE** is a way for servers to push a one-way event stream to clients over HTTP with media type `text/event-stream`; browsers usually use `EventSource`.
- **WebSocket** is a protocol maintaining a bidirectional connection with messages/frames; browsers have a native WebSocket API.
- **RSocket** is an application protocol with four interaction models, metadata routing, multiplexing, and Reactive Streams demand over the network; it runs **over TCP or WebSocket** rather than simply being a type of HTTP request.

Thus "RSocket or WebClient" is not comparing two APIs at the same layer. In reality, you choose **the protocol/interaction style** for a use case, then pick the matching client: WebClient for HTTP, RSocketRequester for RSocket, EventSource/WebClient for SSE, or WebSocketHandler/WebSocketClient for WebSocket.

### 2.1. Initial positioning table

| Criterion | HTTP with WebClient | SSE | WebSocket | RSocket |
| --- | --- | --- | --- | --- |
| Role | HTTP client with request-response semantics | Server → client stream over HTTP | Bidirectional message transport | Messaging protocol with four interaction models |
| Bidirectional sending on one connection by application message | Not in the traditional API model; each HTTP request has a request and response phase | No; clients send other requests via separate HTTP calls | Yes | Yes; both peers can act as requester and responder |
| One request → many continuous results | Can stream HTTP body/SSE | Designed specifically for this | Yes, with self-designed message protocol | Request-Stream |
| Many messages in ↔ many messages out | No standard request-channel abstraction like RSocket | No | Yes, if you build your own protocol | Request-Channel |
| Cross-network backpressure at application message level | No REQUEST_N like RSocket; HTTP/TCP have flow control mechanisms | No demand protocol from EventSource | No Reactive Streams demand in the WebSocket protocol | Has REQUEST_N for streaming interactions |
| Browser support | Native HTTP APIs, fetch | Native EventSource | Native WebSocket | Needs RSocket client/library, typically over WebSocket |
| HTTP gateway/CDN/cache | Integrates very well | Works at HTTP edge, though streams need proxy tuning | Needs WebSocket upgrade/keepalive support | TCP needs dedicated support; RSocket-over-WebSocket needs compatibility |
| Integration cost | Low if HTTP stack already exists | Low for one-way notifications | Medium: message contracts, reconnects | Higher: protocol, codecs, connection lifecycle, ops support |
| Typical fit | CRUD, REST, public APIs, service calls | Notifications/dashboards/live feeds | Chat, collaboration, browser interaction | Streaming RPC, telemetry, bidirectional service-to-service |

This table is an architectural guide, not a claim about which protocol is "fastest" in every situation.

## 3. Four RSocket interaction types and deriving use cases

RSocket has four standard interaction models. Each interaction is opened over an established connection; a connection can carry multiple logical streams concurrently.

| RSocket interaction | Outbound payload | Returned payload | Spring requester |
| --- | --- | --- | --- |
| Request-Response | One request | Zero or one response | `retrieveMono(T.class)` |
| Request-Stream | One request | Multiple streamed responses | `retrieveFlux(T.class)` |
| Fire-and-Forget | One message | No business response awaited | `send()` |
| Request-Channel | Outbound message stream | Inbound message stream | `data(Flux<T>, T.class).retrieveFlux(R.class)` |

### 3.1. Request-Response

One side sends a message and receives exactly one result (or error).

```text
Requester ------ request ------> Responder
Requester <----- response ------ Responder
```

Close to HTTP GET/POST in how developers think about it, yet without built-in HTTP statuses, cache validators, URL routing, CDN semantics, OpenAPI tooling, or the HTTP proxy ecosystem. If an application only has CRUD calls, **HTTP/WebClient is usually the simpler choice**.

### 3.2. Request-Stream

A single request asks for multiple response items over time:

```text
Requester --- subscribe sensor.temp ---> Responder
Requester <-------- temperature 1 ----- Responder
Requester <-------- temperature 2 ----- Responder
Requester <-------- temperature 3 ----- Responder
```

RSocket has demand signals: the requester asks for a number of items, and the responder must honor demand. Demand is carried in the initial request and subsequent `REQUEST_N` frames.

SSE also fits well when the receiver is a browser and the stream only goes server → browser. RSocket adds value when the same system also wants request-channel, multiplexed RPC streams, or cross-network backpressure control.

### 3.3. Fire-and-Forget

A message is sent without expecting an application response:

```text
Requester ------ event ------> Responder
           (no business response)
```

In Spring, `send()` returns `Mono<Void>`. This Mono indicates the send operation completed, **not that the receiving handler processed it successfully**, nor that data was written to storage. For payments, critical audits, or events needing durable delivery, design separate business acknowledgments or use a durable message broker.

### 3.4. Request-Channel

Both directions are streams; both sides can send multiple messages within the same interaction:

```text
Requester ---- reading A ------------> Responder
Requester <--- normalized A ---------- Responder
Requester ---- reading B ------------> Responder
Requester ---- reading C ------------> Responder
Requester <--- normalized B ---------- Responder
Requester <--- normalized C ---------- Responder
```

This is a strong reason to consider RSocket in service-to-service or telemetry systems: the protocol already provides a many-to-many pattern and companion demand mechanism, avoiding custom action IDs, acks, request correlation, and flow-control messages layered atop WebSocket.

Nevertheless, WebSocket can solve this too when the application defines its own protocol; it is not impossible with WebSocket.

### 3.5. Two symmetric peers

Once the connection is established, either side can act as requester or responder for different interactions. This is duplex messaging, not merely a client opening a connection while the server passively replies.

Applications must still enforce authentication/authorization for both client-side and server-side routes. Never assume an open connection authorizes calling every route.

## 4. How does RSocket backpressure differ from ordinary streaming?

RSocket embeds Reactive Streams semantics over the network. For request-stream and request-channel, a side can announce how many messages it is ready to receive.

Illustrative example:

```text
Client                        Server
  | ---- REQUEST_STREAM ------> |
  |       demand = 2            |
  | <------ PAYLOAD #1 -------- |
  | <------ PAYLOAD #2 -------- |
  | ---- REQUEST_N(3) --------> |
  | <------ PAYLOAD #3 -------- |
  | <------ PAYLOAD #4 -------- |
  | <------ PAYLOAD #5 -------- |
```

The difference is that demand has meaning at the **protocol message level**, not merely the TCP receive window or buffering in a client library.

Distinguish:

1. **Reactor backpressure** regulates publisher/subscriber inside the application.
2. **TCP or HTTP/2 flow control** regulates bytes on the network.
3. **RSocket REQUEST_N** transmits demand for the count of application payload messages between peers.

RSocket reduces the risk of a producer outpacing a consumer in streaming RPC, but does not guarantee infinite memory, replace concurrency/connection pool limits, or turn blocking database code into non-blocking code.

Spring WebFlux `WebSocketHandler` uses Reactor publishers and some connectors apply internal backpressure throttling. However, **the WebSocket protocol defines no RSocket-equivalent `REQUEST_N`**. If message-level credit-based flow control is needed over WebSocket, applications generally have to build it themselves.

SSE uses HTTP response streaming. Browser `EventSource` provides no API to send per-message demand to the server. If the server emits too fast, you need rate limiting, buffer/drop policies, network flow control, or publisher/transport backpressure.

## 5. What else does RSocket have beyond the four interaction models?

### 5.1. Multiplexing

A single TCP or WebSocket connection can carry many concurrent RSocket interactions. This avoids opening a socket per RPC stream and avoids manually demultiplexing messages across requests on one connection.

Multiplexing does not automatically mean lowest latency. Serialization overhead, batching, frame sizes, network hops, CPU, schedulers, and upstream services are what you actually measure.

### 5.2. Routing metadata and codecs

A request carries a route, data, and metadata. A route like `sensor.stream` is handled by Spring `@MessageMapping`; payloads can be encoded with JSON, CBOR, or other codecs via `RSocketStrategies`.

RSocket lacks built-in HTTP method/status/header semantics. Migrating APIs from HTTP to RSocket requires redesigning error representation, versioning, authentication metadata, tracing, and timeouts.

### 5.3. Keepalive

RSocket has keepalive frames to monitor connection health. That helps detect dead connections, but does not mean messages are automatically replayed or business transactions finish after a network drop.

### 5.4. Leasing (optional)

RSocket supports `LEASE` frames: a peer can cap how many new requests may be opened within a time window. This is **connection-level request throttling**, unlike `REQUEST_N` which regulates stream item counts.

Leasing is neither mandatory nor enabled by default across all deployments. Rely on leasing only after configuring and testing both peers.

### 5.5. Session resumption (optional)

RSocket has a resumption mechanism to continue a session after transient disconnects if the implementation, both peers, and infrastructure support it and retain sufficient state.

Do not conclude that RSocket:
- Safely retries every request automatically.
- Has durable message storage.
- Provides exactly-once business processing.
- Guarantees zero lost events across server restarts.
- Automatically replays historical streams if the app has no storage source.

Those guarantees require designing **idempotency, offsets/cursors, persistence, replay policies, reconnect logic, and failover tests** separately.

### 5.6. Transport choice: TCP or WebSocket

RSocket **is not WebSocket**, though it can run over WebSocket. For browser clients, you usually need an RSocket JavaScript library over WebSocket; browser native WebSocket APIs do not understand RSocket frames, routes, or `REQUEST_N`.

Direct service-to-service RSocket TCP can work well inside private networks, whereas HTTP ingresses, CDNs, API gateways, and firewalls may not support arbitrary TCP routes. RSocket-over-WebSocket helps when infrastructure only permits WebSocket, though proxy timeouts, max frame sizes, TLS, and subprotocol support still require checking.

## 6. When should you keep HTTP and WebClient?

**Choose WebClient/HTTP first** when communication has these traits:

- One request receiving one response is the dominant pattern.
- Public APIs for browsers, mobile apps, partners, or third parties.
- Reliance on REST semantics, status codes, HTTP auth, caching, ETag, Range Requests, and content negotiation.
- Existing ingress, WAF, API gateway, service mesh, CDN, OpenAPI, and HTTP observability.
- Easy testing with curl/Postman, straightforward debugging, and team onboarding.
- No need for native request-channel or cross-process demand signals.
- HTTP/2 available for multiplexing, or SSE for response streaming.

Spring WebClient example:

```java
WebClient client = WebClient.builder()
        .baseUrl("https://orders.example.test")
        .build();

Mono<OrderDto> order = client.get()
        .uri("/orders/{id}", 42)
        .retrieve()
        .bodyToMono(OrderDto.class);
```

This is an **illustrative snippet**: `OrderDto` is an application DTO and the endpoint is hypothetical. The HTTP request may use HTTP/1.1 or HTTP/2 depending on the connector; that is separate from using RSocket.

When response streaming over HTTP is needed, `WebClient` can also consume `Flux<ServerSentEvent<T>>`, `application/x-ndjson`, or suitable streaming payloads. You do not need to move the entire system to RSocket just because a return type is `Flux`.

### 6.1. HTTP/2 does not turn WebClient into RSocket

HTTP/2 allows multiple HTTP streams over one connection and has byte-level connection/stream flow control. Yet HTTP retains request-response semantics. It does not define a many-to-many request-channel with application-message `REQUEST_N` like RSocket.

### 6.2. REST APIs can coexist with RSocket

A balanced architecture often looks like:

```text
Browser / Partner / Public clients
         |
      HTTPS REST
         |
     API Gateway
         |
     WebFlux API
         |
   +-----+-----------------+
   |                       |
HTTP/WebClient       Internal RSocket
   |                       |
CRUD services           live telemetry
```

Migrate only streams that truly need RSocket's capabilities; keep the rest on HTTP to avoid full-scale migration and preserve compatibility.

## 7. When should you choose SSE instead of RSocket?

SSE fits when **the server continuously pushes notifications to the browser, while the browser does not need to send messages on the same stream**.

Scenarios:

- Dashboards updating metrics periodically.
- Job processing status notifications.
- Simple live feeds or progress updates.
- Exchange rates, stock prices, short logs, or display event broadcasts.
- UI receives events while user commands are sent via separate HTTP POST/PUT requests.

SSE uses `text/event-stream`. Browser `EventSource` supports automatic reconnection. If the server sends event IDs, the client can send `Last-Event-ID` upon reconnecting, though true replay requires server-side event history and lookup logic by that ID.

### 7.1. WebFlux SSE example

```java
@RestController
public class LiveController {

    @GetMapping(
            value = "/events",
            produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public Flux<ServerSentEvent<String>> events() {
        return Flux.interval(Duration.ofSeconds(1))
                .map(n -> ServerSentEvent.<String>builder()
                        .id(Long.toString(n))
                        .event("update")
                        .data("tick-" + n)
                        .build());
    }
}
```

Browser:

```javascript
const stream = new EventSource("/events");

stream.addEventListener("update", event => {
    console.log(event.lastEventId, event.data);
});

stream.onerror = error => {
    console.error("Stream connection problem", error);
};
```

This example generates IDs from scratch per subscription, **has no event store, and performs no replay**. It illustrates the API, not a reliable delivery solution.

### 7.2. Practical advantages of SSE

- Direct browser API without extra protocol libraries.
- Runs over HTTP, integrating smoothly with web authentication models and streaming-capable reverse proxies.
- Text format is easy to inspect with `curl -N`.
- `EventSource` includes built-in reconnection and event IDs.
- No need to build a bidirectional message-type system when the UI only receives updates.

Limitations:
- Server → client only on an SSE stream; client actions go through separate HTTP requests.
- `EventSource` provides no `request-N` protocol backpressure.
- Heartbeats/comments are needed to avoid proxy idle timeouts.
- Proxy buffering, timeouts, HTTP/1.1 browser connection limits, and per-client memory must be evaluated.
- Sensitive data needs auth, CORS, and token protection; never place credentials casually in URLs.

**Rule of thumb:** If it is simply "server push to browsers," try SSE before RSocket.

## 8. When should you choose WebSocket instead of RSocket?

WebSocket provides a bidirectional message channel native to browsers. It fits when real-time interaction from both sides is needed without requiring RSocket's specific RPC/backpressure standards.

Examples:
- Single-room or multi-room chat.
- Whiteboards/collaboration.
- Multiplayer games.
- Browser continuously sending actions while the server returns real-time messages.
- Existing ecosystems using STOMP/WebSocket, Socket.IO, or custom protocols.

A WebSocket connection can carry JSON/binary messages per an application contract:

```json
{"type":"chat.send","requestId":"abc-42","room":"dev","text":"hello"}
```

However, the WebSocket protocol does not standardize RPC routing, response correlation, stream cardinality, per-stream request-N, or durable event delivery. Applications can implement those features themselves, which increases development effort and protocol complexity.

### 8.1. WebFlux WebSocketHandler example

```java
public final class EchoWebSocketHandler implements WebSocketHandler {

    @Override
    public Mono<Void> handle(WebSocketSession session) {
        Flux<WebSocketMessage> output = session.receive()
                .map(WebSocketMessage::getPayloadAsText)
                .map(text -> session.textMessage("echo:" + text));

        return session.send(output);
    }
}
```

This is **illustrative handler code**, requiring a bean declaration and URL mapping in WebFlux config. The WebSocket connection is bidirectional; calling `session.send` takes a `Publisher` and ties the send lifecycle to the inbound stream. In real deployments, bound message sizes, handle session closure, enforce session auth, validate origins, and manage pressure at application/connector levels.

### 8.2. When is RSocket better than WebSocket?

RSocket is advantageous when you want:
- Multiple independent request-response, request-stream, and request-channel interactions on one connection.
- Cross-network `REQUEST_N` backpressure per interaction.
- Consistent routing and metadata semantics.
- Fewer custom message types and less hand-rolled correlation/ack/flow-control logic over WebSocket.
- Peers that are services/JVMs/backends already using Reactor where you control both ends of the connection.

WebSocket is usually better if:
- Clients are mainly browsers and WebSocket SDKs/infrastructure already exist.
- The message protocol is simple (chat, cursors, presence).
- Native Reactive Streams demand across the network is unnecessary.
- Fewer protocol dependencies/client libraries are preferred.
- The ecosystem already runs STOMP or a stable real-time WebSocket solution.

**Note:** RSocket-over-WebSocket still uses WebSocket as the transport, adding the RSocket protocol layer on top. A native browser WebSocket client cannot talk directly to an RSocket endpoint without implementing the RSocket protocol.

## 9. Decision table based on real-world conditions

| Decision question | If the answer is… | Prefer |
| --- | --- | --- |
| One HTTP request → one response? | Mostly CRUD/REST operations | WebClient/HTTP |
| External clients need an easy-to-publish API contract? | Public/mobile/partner, OpenAPI, CDN, WAF | WebClient/HTTP |
| Browser only receives one-way events? | Notifications, progress, dashboards | SSE |
| Browser continuously sends and receives messages? | Chat, whiteboards, games | WebSocket |
| Multiple RPC interactions on one connection? | Request-response + stream + channel | Consider RSocket |
| Fast producer, slow consumer needing remote demand? | Streaming telemetry with explicit pressure | Consider RSocket |
| Peers can proactively request each other? | Full-duplex service-to-service | RSocket or WebSocket per contract |
| Infrastructure supports only HTTP ingress? | No TCP routes, WebSocket blocked | WebClient/SSE |
| Need native browser support without extra SDKs? | Compatibility and onboarding prioritized | SSE/WebSocket |
| Need durable queues, multi-day replay, offline consumers? | Delivery/replay is a core requirement | Broker (Kafka/RabbitMQ/Pulsar), not RSocket alone |
| Broadcasting data to millions of clients? | Massive fanout, consumers at varying speeds | Pub/sub/broker + edge design, not one RSocket connection |
| Team cannot operate stateful connections? | New to Spring, stable HTTP infrastructure | Avoid RSocket initially |
| Truly many-to-many interaction needing REQUEST_N? | Owned services on both ends, long-lived streaming | RSocket |

These are **heuristics**, not latency measurements. Benchmark with realistic data before deciding on a migration.

## 10. Short decision tree

```text
Is real-time/streaming data exchange required?
  |
  +-- No --> HTTP + WebClient
  |
  +-- Yes
       |
       +-- Does the browser only receive updates?
       |       |
       |       +-- Yes --> SSE
       |       |
       |       +-- No
       |
       +-- Does the browser need to send and receive in real time?
       |       |
       |       +-- Yes --> WebSocket (or RSocket-over-WS when
       |       |           RSocket semantics are truly needed and an SDK exists)
       |       |
       |       +-- No
       |
       +-- Does service-to-service need multiple requests/streams and
       |   cross-process backpressure?
       |       |
       |       +-- Yes --> Evaluate RSocket via POC
       |       |
       |       +-- No --> HTTP/WebClient or SSE
       |
       +-- Are durable storage and offline replay needed?
               |
               +-- Yes --> Message broker/event log with an appropriate API
```

Do not pick RSocket just because the project uses `Flux`/`Mono`: Spring WebFlux and `WebClient` are already reactive even over HTTP.

## 11. Mandatory prerequisites before approving RSocket

### 11.1. Control over both sides

RSocket has libraries for Java, JavaScript, and other languages, though it is less ubiquitous than HTTP. Verify compatible client versions, codecs, transports, and security across **all actual platforms**. If third parties cannot adopt the protocol, keep an HTTP interface at the edge.

### 11.2. Prove the interaction model need

Document which use cases need request-stream or request-channel. Measure concurrent streams, payload sizes, request rates, consumer lag, and behavior when a consumer slows down.

If all use cases are short request-response calls, HTTP is often simpler and easier to observe.

### 11.3. Infrastructure supports the transport

- RSocket TCP needs TCP ports, firewalls, L4 ingress/load balancers, and a TLS plan.
- RSocket-over-WebSocket needs WS/WSS endpoints, proxies supporting Upgrade/long-lived connections, and appropriate timeouts.
- HTTP service meshes/gateways do not automatically understand RSocket routes.
- TLS, certificates, and network policies must be verified per transport.
- Test reconnects through proxies, idle timeouts, rolling deploys, and draining.

### 11.4. Authentication and authorization plan

HTTP OAuth2/sessions/cookies do not automatically apply to RSocket TCP. With Spring Security RSocket, you can use authentication metadata or suitable token mechanisms plus route-based authorization.

Specifically define:
- Who is the connecting peer?
- Who is permitted to call which route?
- How are expired/revoked tokens handled on long-lived connections?
- Is a tenant ID in metadata verified against the authenticated principal?
- Are bearer tokens and sensitive payloads kept out of logs?

SSE/WebSocket also need auth, CORS/origin controls, rate limits, and per-channel authorization; every protocol must address security.

### 11.5. Clear reliability contract

Define for each interaction:
- Is at-most-once sufficient?
- Is an application ACK or idempotency key required?
- Which events must be persisted to a store?
- What does reconnect do to in-flight requests?
- Are delayed, missing, duplicate, or out-of-order messages acceptable?
- Is replay from an offset/cursor needed?

RSocket does not replace Kafka, RabbitMQ, or a transactional outbox.

### 11.6. Operations and observability

Require metrics/tracing for:
- Active connections, close reasons, setup failures.
- Request counts by route/interaction model.
- p50/p95/p99 latency, stream duration.
- `REQUEST_N`/demand, consumer lag, buffers/drops.
- Errors, cancellations, resume/reconnect failures.
- Authentication failures, timeouts.
- Memory/CPU and encoder/decoder throughput.

HTTP tooling is usually more readily available; with RSocket, plan instrumentation and runbooks before production.

## 12. Java 17+ with Spring Boot example: four interaction models

The following example uses **one Spring Boot 3.5.x project running two processes with different profiles**: one TCP RSocket server process and one client process. The structure is minimal so learners can verify behavior directly without a browser or database.

### 12.1. Structure

```text
rsocket-choice-demo/
  build.gradle
  settings.gradle
  src/main/resources/application.yml
  src/main/java/demo/rsocket/
    ProtocolDemoApplication.java
    TelemetryResponder.java
    DemoClientRunner.java
  src/test/java/demo/rsocket/
    TelemetryResponderTest.java
```

### 12.2. build.gradle

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
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
```

File `settings.gradle`:

```groovy
rootProject.name = 'rsocket-choice-demo'
```

The Spring Boot RSocket starter includes RSocket Java, Spring Messaging, and codec support. Boot auto-configures `RSocketStrategies`, `RSocketMessageHandler`, and `RSocketRequester.Builder`. You do not need `spring-boot-starter-webflux` when running standalone RSocket TCP.

### 12.3. application.yml: open TCP server only under the server profile

```yaml
spring:
  application:
    name: rsocket-choice-demo

---
spring:
  config:
    activate:
      on-profile: server
  rsocket:
    server:
      port: 7000
      transport: tcp
```

The `client` profile does not set `spring.rsocket.server.port`, so the client application does not open an extra RSocket server. When running with the `server` profile, Boot creates an RSocket TCP server on port 7000.

### 12.4. Application class

```java
package demo.rsocket;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ProtocolDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ProtocolDemoApplication.class, args);
    }
}
```

### 12.5. Responder: @MessageMapping

```java
package demo.rsocket;

import java.time.Duration;

import org.springframework.context.annotation.Profile;
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.stereotype.Controller;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Controller
@Profile("server")
public class TelemetryResponder {

    @MessageMapping("greet")
    public Mono<String> greet(@Payload String name) {
        return Mono.just("Xin chào " + name);
    }

    @MessageMapping("sensor.stream")
    public Flux<String> readings(@Payload String sensorId) {
        return Flux.interval(Duration.ofMillis(120))
                .map(n -> sensorId + "#" + n)
                .take(4);
    }

    @MessageMapping("sensor.channel")
    public Flux<String> normalize(@Payload Flux<String> readings) {
        return readings.map(String::trim)
                .filter(value -> !value.isBlank())
                .map(String::toUpperCase);
    }

    @MessageMapping("audit")
    public Mono<Void> audit(@Payload String event) {
        return Mono.fromRunnable(() ->
                System.out.println("audit:" + event));
    }
}
```

Explanation:
- `greet` takes one `String` and returns `Mono<String>` → Request-Response.
- `sensor.stream` takes one `String` and returns `Flux<String>` → Request-Stream.
- `sensor.channel` takes `Flux<String>` and returns `Flux<String>` → Request-Channel.
- `audit` takes one `String` and returns `Mono<Void>` → Fire-and-Forget when the requester uses `send()`.

In this example, the stream stops after four values to avoid emitting infinitely. Never stream infinitely to learners without cancellation or timeouts.

### 12.6. Client runner: RSocketRequester

```java
package demo.rsocket;

import java.time.Duration;
import java.util.List;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Profile;
import org.springframework.messaging.rsocket.RSocketRequester;
import org.springframework.stereotype.Component;

import reactor.core.publisher.Flux;

@Component
@Profile("client")
public class DemoClientRunner implements ApplicationRunner {

    private final RSocketRequester.Builder requesterBuilder;

    public DemoClientRunner(RSocketRequester.Builder requesterBuilder) {
        this.requesterBuilder = requesterBuilder;
    }

    @Override
    public void run(ApplicationArguments arguments) {
        RSocketRequester requester =
                requesterBuilder.tcp("127.0.0.1", 7000);

        String greeting = requester.route("greet")
                .data("An")
                .retrieveMono(String.class)
                .block(Duration.ofSeconds(5));

        List<String> stream = requester.route("sensor.stream")
                .data("temp-1")
                .retrieveFlux(String.class)
                .collectList()
                .block(Duration.ofSeconds(5));

        List<String> channel = requester.route("sensor.channel")
                .data(Flux.just(" a ", "b"), String.class)
                .retrieveFlux(String.class)
                .collectList()
                .block(Duration.ofSeconds(5));

        requester.route("audit")
                .data("client-start")
                .send()
                .block(Duration.ofSeconds(5));

        System.out.println("greet=" + greeting);
        System.out.println("stream=" + stream);
        System.out.println("channel=" + channel);
        System.out.println("fnf sent");
    }
}
```

Using `block(Duration)` is solely to produce deterministic output in the **CLI demo's `ApplicationRunner`**, not how to write production WebFlux controllers or Netty event-loop code. In production, return `Mono`/`Flux` to callers, compose operators, and apply conditional timeouts/retries.

### 12.7. Running the demo

Open two terminals:

Terminal 1 (server):

```bash
./gradlew bootRun --args='--spring.profiles.active=server'
```

Terminal 2 (client):

```bash
./gradlew bootRun --args='--spring.profiles.active=client'
```

With the data in the code, key client output:

```text
greet=Xin chào An
stream=[temp-1#0, temp-1#1, temp-1#2, temp-1#3]
channel=[A, B]
fnf sent
```

The server may print `audit:client-start`, but when it appears relative to `fnf sent` is not guaranteed. `send()` is not an application-level ACK proving the event was durably processed.

If the client fails to connect, check the server profile, port 7000, firewall, startup timing, and that both sides use TCP transport. Use the same codec/`dataMimeType` configuration on both sides; the default starter supports compatible codecs.

### 12.8. Testing publisher logic with StepVerifier

File `src/test/java/demo/rsocket/TelemetryResponderTest.java`:

```java
package demo.rsocket;

import java.time.Duration;

import org.junit.jupiter.api.Test;

import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

class TelemetryResponderTest {

    private final TelemetryResponder responder =
            new TelemetryResponder();

    @Test
    void requestResponseReturnsOneValue() {
        StepVerifier.create(responder.greet("An"))
                .expectNext("Xin chào An")
                .verifyComplete();
    }

    @Test
    void requestChannelTransformsInputStream() {
        StepVerifier.create(responder.normalize(
                        Flux.just(" a ", "   ", "b")))
                .expectNext("A", "B")
                .verifyComplete();
    }

    @Test
    void requestStreamProducesFourReadings() {
        StepVerifier.withVirtualTime(
                        () -> responder.readings("temp-1"))
                .thenAwait(Duration.ofMillis(600))
                .expectNext(
                        "temp-1#0",
                        "temp-1#1",
                        "temp-1#2",
                        "temp-1#3")
                .verifyComplete();
    }
}
```

Run:

```bash
./gradlew test
```

These tests verify the responder's reactive logic. They **do not replace** integration tests over real RSocket TCP/WebSocket, because direct `StepVerifier` calls do not prove encoding, routing metadata, or `REQUEST_N` work over the network.

## 13. RSocket over WebSocket: when is it needed?

If the client is a browser yet the use case genuinely requires RSocket semantics, you can use RSocket over WebSocket with a compatible JavaScript client.

With Spring Boot WebFlux + Reactor Netty, configure RSocket under a URL mapping:

```properties
spring.rsocket.server.transport=websocket
spring.rsocket.server.mapping-path=/rsocket
```

Add the WebFlux starter for an HTTP web server. This attaches the RSocket WebSocket endpoint to the corresponding WebFlux server. This mode is supported by Spring Boot when the web server is Reactor Netty; do not switch to Tomcat/Jetty expecting the same auto-configuration to work.

Another option: open a standalone RSocket TCP server via `spring.rsocket.server.port` on a dedicated port. The demo in section 12 uses this option.

Raw SSE/WebSocket still retain the advantage of native browser APIs. Accept the extra RSocket JavaScript dependency, protocol framing, and operational overhead only if the project genuinely leverages multiple interaction models/backpressure.

## 14. Comparing reliability on connection loss

| Incident | HTTP/WebClient | SSE/EventSource | WebSocket | RSocket |
| --- | --- | --- | --- | --- |
| Socket disconnected | Request fails/times out; needs retry policy | EventSource usually reconnects | App needs reconnect logic | App/connector needs reconnect logic; resumption possible if enabled and supported |
| Replaying lost data | Self-designed by API/app | `Last-Event-ID` helps if server keeps history | Self-designed by app | Optional stateful resumption; does not equal durable replay |
| Guaranteeing exactly-once side effects | Not built-in | Not built-in | Not built-in | Not built-in |
| Storing events for offline consumers | Needs storage/broker | Needs event store/broker | Needs event store/broker | Needs event store/broker |
| Client sending per-event demand signals | No request-N messages | EventSource lacks it | Must add custom protocol | `REQUEST_N` in streaming |

**Conclusion:** Do not pick RSocket just because you want "zero lost messages." If reliable event processing is needed, design application-level ACKs, persistence/idempotency, and possibly combine with a message broker.

## 15. Benchmark POC before deciding

An RSocket architecture should be backed by measurements rather than a hunch that "reactive must be faster."

### 15.1. Use the same workload

Compare RSocket request-stream against SSE/WebClient streaming on identical:
- Producer rate in messages/s.
- Concurrent client/stream counts.
- Small/medium/large message sizes.
- RTT latency and packet loss.
- CPU/memory, socket count, connection duration.
- Slow consumer or paused reading scenarios.

### 15.2. Metrics to measure

- Throughput, p50/p95/p99 latency, end-to-end event lag.
- Peak memory/GC, buffered bytes, dropped messages.
- Connection establishment/reconnect time.
- Cancellation propagation.
- Backpressure response when downstream requests only N elements.
- Timeout rates, encoding errors, resets, leaks.
- Deployment complexity: ports, TLS, proxy rules, dashboards/tracing.
- Development and client support cost.

### 15.3. Failure scenarios to test

1. Slow-reading consumer.
2. Server emitting faster than capacity.
3. Proxy closing idle connections.
4. Client switching networks or sleeping/waking.
5. Server rolling restart.
6. Token expiring mid-session.
7. One interaction failing while other streams keep running.
8. Large messages requiring fragmentation.
9. Retries creating duplicate side effects.
10. Clients with incompatible codec/protocol versions.

If a POC shows no measurable gain or the team lacks operational readiness, prefer the simpler existing solution.

## 16. Illustrative scenarios and recommendations

### Scenario A: Product CRUD and payments

Requirements: GET/POST, HTTP statuses, idempotency, validation, auditing, and external partners.

**Choice:** REST/HTTP with `WebClient` on the client and WebFlux or Spring MVC on the server. RSocket does not improve REST semantics and makes integration harder.

### Scenario B: Dashboard displaying order statuses

The browser only monitors status over time; button clicks send separate HTTP POST calls.

**Choice:** SSE. An event ID can recover events if an event store exists. RSocket is unnecessary just to push notifications.

### Scenario C: Browser chat and collaborative editor

The browser continuously sends and receives messages. There are rooms, user presence, and small interactions.

**Choice:** WebSocket with a clear message protocol. If the system already runs STOMP or a well-functioning real-time solution, moving to RSocket needs strong justification.

### Scenario D: IoT devices streaming telemetry and receiving continuous commands

Both directions are streams; rate limits depend on peer processing capacity; each connection carries multiple logical streams; client and server are controlled by the same organization.

**Choice:** RSocket is a strong candidate. Check device SDKs, TLS transport, auth, reconnects, and memory behavior on unstable networks.

### Scenario E: Financial data requiring replay and auditing even when clients are offline

Requirements: durable history, offset-based replay, zero lost events on failure, and multiple consumer groups.

**Choice:** an event log/broker like Kafka/Pulsar or a suitable queue; WebClient/SSE/WebSocket/RSocket are only part of the data delivery path. RSocket itself does not create a durable queue.

### Scenario F: One backend service reading 1 record from another service

Requirements: short request-response through an API gateway with existing HTTP tracing.

**Choice:** `WebClient`, no need to expand to the RSocket stack.

## 17. Common architectural mistakes

| Mistake | Consequence | How to handle it |
| --- | --- | --- |
| Seeing `Flux`/`Mono` and picking RSocket | Unnecessary protocol added | Start from the use case, not return types |
| Thinking `WebClient` cannot stream | Expensive migration | `WebClient` can consume `Flux`/SSE/NDJSON over HTTP |
| Thinking WebSocket cannot handle two-way traffic | Choosing an over-featured protocol | WebSocket is natively duplex; RSocket adds semantics |
| Thinking SSE is bidirectional | Cannot send client messages on the same stream | Use HTTP POST or WebSocket |
| Thinking RSocket is a browser-native protocol | Clients fail to connect | Use RSocket JS over WebSocket or pick native WS/SSE |
| Equating `REQUEST_N` with the TCP window | Flawed pressure design | Distinguish application message demand from byte flow control |
| Using fire-and-forget for critical financial events | No business ACK/durable guarantee | Use idempotency, ACKs, outbox, or a broker |
| Thinking resumption is auto-enabled and lossless | Wrong reconnect expectations | Verify both ends' config, replay, and failover |
| Not checking proxies/LBs | Connections time out or get blocked | Test every hop/transport and idle timeout |
| Opening one connection with unbounded streams | Memory/CPU overload | Measure queues, cap concurrency, set buffering policies |
| Omitting route authorization | Cross-tenant data exposure | Spring Security RSocket + principal/route policies |
| Calling `subscribe()` manually inside handlers | Errors/cancels miss the caller | Compose `Mono`/`Flux` and return the publisher |
| Blocking on the Netty event loop | Stalls and loss of scalability | Stay non-blocking, isolate blocking workloads |
| Running unit tests and claiming network backpressure | Misses frame/codec/proxy bugs | Add integration + failure-injection tests |
| Using RSocket instead of Kafka | No replay/durable queue | Pair with a broker when needed |
| Assuming RSocket is always faster than HTTP/2 | Benchmarks do not back it up | POC with equal workload, compare p95/p99 and cost |

## 18. Final decision checklist

Before approving RSocket, answer and document:

1. Which routes need request-stream or request-channel? Provide sample payloads.
2. Is remote `REQUEST_N` truly needed instead of HTTP/SSE/WebSocket streaming?
3. Which peers use Java, JavaScript, mobile, or embedded devices? Are compatible SDKs available?
4. Are native browsers, external partners, or public OpenAPI required?
5. Does infrastructure support TCP/WSS and end-to-end TLS?
6. Do you have authority to modify all clients and servers?
7. What is the plan for authentication, per-route authorization, token expiry, and tenant isolation?
8. Where are demand, buffers, cancellation, timeouts, and rate limiting enforced?
9. Are replay, duplicates, ordering, offline consumers, and durable processing needed?
10. Have reconnect/resumption been configured and failover-tested for real?
11. Are tracing/metrics/logging and debugging tools sufficient?
12. Have benchmarks against WebClient/SSE/WebSocket proven the benefit?
13. Does the team have the operational capability to manage connection lifecycles and protocol errors?
14. If the conditions above are not met, would a simpler HTTP/SSE/WebSocket solution achieve the goal?

## 19. References

- [Spring Framework – RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html): four interaction models, REQUEST_N, leasing, resumption, requester, and `@MessageMapping`.
- [Spring Boot 3.5 – RSocket](https://docs.spring.io/spring-boot/3.5/reference/messaging/rsocket.html): starter, auto-configuration, TCP server, RSocket-over-WebSocket, `RSocketRequester.Builder`.
- [Spring Framework – WebClient](https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html): reactive HTTP client, response handling, and streaming.
- [Spring Framework – WebSockets](https://docs.spring.io/spring-framework/reference/web/webflux-websocket.html): `WebSocketHandler`, `WebSocketSession`, receive/send, and transports.
- [Spring Framework – Reactive Core Streaming](https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html): HTTP SSE/NDJSON streaming and heartbeats.
- [MDN – Using server-sent events](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events/Using_server-sent_events): `EventSource`, server→client, event/id/retry, and reconnect.
- [RSocket Protocol](https://rsocket.io/about/protocol/): wire-level interactions, frames, resumability, and protocol contract.

## 20. Key takeaways

**Do not choose RSocket solely because the system is written with Spring WebFlux.** Choose `WebClient`/HTTP for CRUD, public APIs, and standard HTTP integrations; choose SSE when browsers only receive updates; choose WebSocket when browsers need real-time send/receive with a simple message protocol; consider RSocket when services/peers have multiple bidirectional interactions, request-stream/request-channel, and genuinely need backpressure via `REQUEST_N` at the application-message level.

RSocket can run over TCP or WebSocket, with multiplexing, keepalive, and optional leasing/resumption. It **does not replace** HTTP gateways, native browser APIs, security policies, durable brokers, or business-level ACKs. The right decision comes from communication requirements, client/infrastructure capabilities, operations, benchmark evidence, and reliability needs — not technology trends.
