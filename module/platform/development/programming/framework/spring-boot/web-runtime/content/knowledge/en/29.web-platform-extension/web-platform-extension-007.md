# RSocket and How It Differs from the HTTP Request-Response Model

## 1. Why Learn About RSocket in Spring Boot web-runtime?

Most web APIs begin with an HTTP request: the client sends `GET /orders/42`, and the server processes it and returns a status, headers, and body. This **request–response** style fits CRUD, caching, browsers, public APIs, and existing proxy infrastructure well. However, certain requirements need more than a single result:

- A device continuously streams sensor data while also receiving control commands.
- A dashboard wants a sequence of results as soon as the server produces each item, rather than waiting for a full batch to finish.
- A client wants to emit a fire-and-forget event without needing a response body.
- Both peers want to send and receive multiple messages **over the same connection**, with built-in control over production and consumption rates.

**RSocket** is an application protocol for bidirectional, multiplexed, message-oriented communication over transports such as **TCP** and **WebSocket**. It supports four interaction models: **Request-Response**, **Fire-and-Forget**, **Request-Stream**, and **Request-Channel**. For streaming interactions, RSocket carries Reactive Streams demand at the protocol level so the sender can regulate how much data it emits.

In Spring Boot, RSocket is typically integrated via `spring-boot-starter-rsocket`, `@MessageMapping`, `RSocketMessageHandler`, and `RSocketRequester`. This lesson explains how they work, compares them fairly with HTTP, walks through a **Java 17+ / Spring Boot 3.3.13** example, and demonstrates practical testing.

**Keep in mind from the start:** RSocket **is not automatically faster than HTTP**, does not guarantee exactly-once delivery, does not provide authentication automatically, does not turn blocking data sources into non-blocking ones, and is not mandatory for every real-time API.

## 2. HTTP Request-Response: The Baseline for Comparison

A typical HTTP API call:

```http
GET /api/greet?name=Mai HTTP/1.1
Host: localhost:8080
Accept: text/plain
```

Response:

```http
HTTP/1.1 200 OK
Content-Type: text/plain

Hello, Mai!
```

The client sends a request; the server returns a response. Each HTTP interaction has its own **request message and response message** with a status code (`200`, `404`, `500`...), headers, and body. With HTTP/1.1 keep-alive, multiple requests can reuse a TCP connection; with HTTP/2, multiple streams can multiplex over the same connection. Therefore the claim "HTTP always opens a new TCP connection per request" is **false**.

HTTP also supports continuous delivery mechanisms:
- **Chunked/streaming HTTP responses**: the server flushes body chunks incrementally.
- **SSE (Server-Sent Events)**: text event streams from server to browser.
- **Long polling**: holding a request open until an event or timeout occurs, then re-issuing a new request.
- **WebSocket upgrade**: switching to a separate full-duplex protocol.
- **HTTP/2/HTTP/3**: multiplexing and flow control across layers.

Thus **the core difference is not "HTTP cannot stream"**, but rather **interaction models, protocol framing, demand/cancellation semantics, route/data/metadata separation, and operational topology**. For browsers and public REST APIs, HTTP usually holds major advantages in tooling, proxies, caching, authentication conventions, and interoperability.

### 2.1. Comparing an RSocket Request-Response

```text
HTTP:
  Client ── GET /api/greet?name=Mai ──► HTTP server
  Client ◄─ HTTP 200 + "Hello, Mai!" ── Server

RSocket:
  Requester ── route="demo.greet", data="Mai" ──► Responder
  Requester ◄─ payload="Hello, Mai!" ───────────── Responder
```

RSocket does not transmit HTTP method `GET` or HTTP status `200` inside each request frame. It uses **route metadata** to locate the handler and a data payload for the content. When errors occur, RSocket sends protocol error frames/signals instead of HTTP status codes over TCP.

**A single RSocket connection can carry many concurrent request streams**, distinguished by protocol stream IDs. Applications do not need to open a separate socket per route or message.

## 3. RSocket's Four Interaction Models

| Model | Requester Sends | Responder Returns | Typical Spring/Reactor API | Use Case |
|---|---|---|---|---|
| **Request-Response** | 0 or 1 request payload | One result (or completion/error) | `retrieveMono(T.class)` | Profile lookup, command confirmation |
| **Fire-and-Forget** | One unidirectional message | No business response payload | `send(): Mono<Void>` | Telemetry/signals where loss is acceptable per contract |
| **Request-Stream** | One request | Multiple responses emitted over time | `retrieveFlux(T.class)` | Progress feeds, periodic updates |
| **Request-Channel** | Stream of request messages | Stream of response messages | `data(Flux<T>,T.class).retrieveFlux(U.class)` | Bidirectional telemetry, interactive streams |

One important detail: `@MessageMapping` in Spring selects the **interaction type** from the **cardinality** of input and output, together with the requester API used. For multi-item input, the handler accepts `Flux<T>`. For multi-item output, the handler returns `Flux<T>`. Many-to-one combinations have specific constraints/mappings, so check the cardinality table in Spring Framework rather than assuming every `Mono`/`Flux` pairing maps to a valid protocol interaction.

### 3.1. Request-Response

```text
Requester                                      Responder
   │ REQUEST_RESPONSE(route, data)                 │
   ├──────────────────────────────────────────────►│
   │                                               │
   │                       process / validate      │
   │◄───────────────────────── PAYLOAD(response) ──┤
   │               or ERROR                        │
```

This model is closest to HTTP. It has one request and one response, yet still operates over the RSocket protocol, an established connection, custom metadata, and non-HTTP semantics.

### 3.2. Fire-and-Forget (FNF)

```text
Requester                                      Responder
   │ REQUEST_FNF(route, data)                      │
   ├──────────────────────────────────────────────►│
   │                                               │
   │    No business response in the protocol       │
```

**`send().then()/Mono<Void>` does not prove business processing finished.** Spring Framework states explicitly that `RSocketRequester.send()` only indicates the message was sent per contract, **not a confirmation from the responder that the business handler executed, wrote to the DB, or committed a transaction**. When you need proof of acceptance/persistence, use Request-Response returning an acknowledgement or a durable event pipeline with ACKs.

### 3.3. Request-Stream

```text
Requester                                      Responder
   │ REQUEST_STREAM(route, data, demand=N)         │
   ├──────────────────────────────────────────────►│
   │◄────────────────── PAYLOAD(item 1) ───────────┤
   │◄────────────────── PAYLOAD(item 2) ───────────┤
   │             REQUEST_N(more demand)            │
   ├──────────────────────────────────────────────►│
   │◄────────────────── PAYLOAD(item 3)... ────────┤
   │                COMPLETE / CANCEL / ERROR      │
```

The requester consumes messages at its own pace. Demand is not "send N messages per second," but rather the **count of elements** the consumer can accept on a stream under the Reactive Streams contract. Regulation must flow all the way through operators and drivers to the data source to genuinely reduce work.

### 3.4. Request-Channel

```text
Requester                                      Responder
   │ REQUEST_CHANNEL(route, first data)            │
   ├──────────────────────────────────────────────►│
   │◄────────────────────────── response item 1 ───┤
   ├────────────────────────── request item 2 ────►│
   ├────────────────────────── request item 3 ────►│
   │◄────────────────────────── response item 2 ───┤
   │◄────────────────────────── response item 3 ───┤
   │        Bidirectional with independent demand/cancel │
```

Channel is bidirectional stream communication. **There is no protocol rule requiring a 1-to-1 output for each input**: a handler can filter, aggregate, fan out, batch, or emit independent responses depending on the application contract. The `uppercase` demo below intentionally maps each input string to one output string for easy observation.

## 4. Which Layers Does RSocket Operate Across?

```text
Application logic
  @MessageMapping / RSocketRequester
            │
        Spring Messaging
  Encoders/Decoders + RSocketStrategies
            │
        RSocket protocol
  SETUP / REQUEST_* / PAYLOAD / REQUEST_N / CANCEL
  ERROR / KEEPALIVE / LEASE / RESUME (when configured)
            │
        Transport layer
           ├── TCP
           └── WebSocket (over HTTP handshake)
            │
        Network/TLS/firewall
```

**Distinctions:**
1. **TCP/WebSocket transport:** how byte frames traverse the network. TCP is not an HTTP API.
2. **RSocket protocol:** frame types, stream IDs, request models, setup, demand.
3. **Spring Messaging:** routes to `@MessageMapping`, decodes data/metadata into Java objects.
4. **Application:** message validation, authentication, authorization, transactions, retries, metrics.

RSocket over **WebSocket** does not mean sending custom plain-text WebSocket JSON frames: inside WebSocket lies the **binary RSocket protocol**. A browser merely calling `new WebSocket(url)` and sending plain JSON strings **cannot talk directly to an RSocket server**; it requires an RSocket client library implementing RSocket framing and protocol.

## 5. Connections, SETUP, Payloads, and Metadata

When opening an RSocket connection, both sides negotiate via `SETUP` parameters such as **data** and **metadata** MIME types, keepalive intervals, and protocol capabilities. On an established connection, a request can carry:

- **Route metadata:** e.g., `demo.greet` so Spring locates `@MessageMapping("demo.greet")`.
- **Data payload:** e.g., `"Mai"` or a JSON/CBOR DTO encoded per the data MIME type.
- **Authentication/trace metadata:** when implemented and registered, bearer tokens, trace context, or tenant keys — all of which must be verified at trust boundaries.

`@MessageMapping` defines a **route**, not an HTTP URL. For example, `@MessageMapping("orders.find")` does not create `GET /orders/find`. Routes can use hierarchical dot notation, with no HTTP method, URI query string, or HTTP status code attached.

**`RSocketRequester.Builder` in Spring Framework 6.1** supports `dataMimeType(...)`, `metadataMimeType(...)`, `setupData(...)`, `setupRoute(...)`, `setupMetadata(...)`, and custom `RSocketConnector`s. Sending `SETUP` happens when the connection is actually established, which can be deferred/lazy in newer clients. A requester can reuse a shared connection and reconnect when sending requests, yet that **does not automatically enable session resumption or exactly-once replay**.

**MIME/codecs must match:** a client sending a Jackson JSON DTO when the server expects CBOR (or a custom binary format) will fail before reaching the handler. In the demo we use `String`/`Integer` and codecs auto-configured by Spring Boot; when changing formats, verify both peers.

## 6. Backpressure: What Does RSocket Add Over HTTP Streaming?

In Reactor, `Flux<T>` implements Reactive Streams. A subscriber requests a number of items via `request(n)`, and the producer is expected to emit only up to that demand. RSocket transmits demand signals for Request-Stream/Channel across the network as frames like `REQUEST_N`. When a consumer processes slowly, the system has a **protocol-level signal** saying "send me only this many more messages."

```text
Requester (slow consumer)              Responder
         │ REQUEST_STREAM(count=5)         │
         ├─────────────────────────────────►│
         │◄──────── tick-1 ─────────────────┤
         │◄──────── tick-2 ─────────────────┤
         │                                  │
         ├──── REQUEST_N(2) ───────────────►│
         │◄──────── tick-3 ─────────────────┤
         │◄──────── tick-4 ─────────────────┤
         │                                  │
         ├──── REQUEST_N(1) ───────────────►│
         │◄──────── tick-5, COMPLETE ───────┤
```

The request counts in the diagram are illustrative, **not a literal trace of every Reactor operator**, because Reactor uses prefetching and batching and may request multiple items ahead. To verify real flow control, observe demand at the `Publisher` and transport/protocol metrics.

**Backpressure does not guarantee absolute memory safety:**
- A `Sinks.Many` or hot broker source can still pile up events unless an overflow strategy is designed.
- Blocking operations or SDK callbacks that ignore demand cannot be halted by RSocket alone.
- Unbounded `Flux.onBackpressureBuffer()` can still exhaust RAM.
- `CANCEL` tells upstream to stop emitting, yet does not roll back already-committed side effects.
- Concurrent connections still consume file descriptors, TLS state, CPU, and memory.
- Very large payloads require frame fragmentation, max size caps, and quotas.

HTTP/2 also has **stream/connection-level flow control**; it is inaccurate to claim HTTP lacks flow control completely. The difference here is **application-level Reactive Streams message demand** expressed directly in the RSocket protocol, whereas HTTP streaming relies on body buffering, socket flow control, and adapters.

## 7. When to Use HTTP vs. When to Consider RSocket?

| Question | HTTP REST / SSE / WebSocket | RSocket |
|---|---|---|
| Public CRUD API for browsers/mobile? | Usually prefer HTTP/JSON/OpenAPI | Use only if clients/infra fully support it |
| HTTP caching, CDNs, status codes, crawlers? | Strong standard ecosystem | No automatic equivalent mapping |
| One request → one response? | HTTP fits naturally | Request-Response works, but adds protocol/dependency overhead |
| Simple server → browser streaming? | SSE may suffice | Request-Stream requires an RSocket client |
| Bidirectional multi-message connection? | WebSocket is a common choice | Channel fits when RSocket semantics and backpressure are needed |
| Microservice streaming many streams/routes? | HTTP/2/gRPC may fit | RSocket offers interaction models and duplex demand |
| Infra only allows HTTP through proxies? | Easier to deploy | Raw RSocket TCP may be blocked; use RSocket-over-WebSocket if supported |
| Need durable broker/replay? | Requires Kafka/RabbitMQ/DB depending on model | RSocket **does not replace** a durable broker |
| Standard organizational firewall/observability? | HTTP tooling usually exists | Requires adding protocol/gateway/telemetry support |
| Team mainly uses Spring Reactive? | WebClient, SSE, WebSocket integrate easily | `RSocketRequester` + `@MessageMapping` can feel very natural |

**There is no conclusion that "RSocket beats HTTP."** RSocket fits **internal or controlled-client duplex streaming** when multiple interaction models and explicit network backpressure matter. HTTP remains dominant for public integrations, browsers, simple APIs, and standard infrastructure management.

## 8. Complete Project: HTTP Request-Response Alongside RSocket TCP

The example below builds **one Spring Boot app**:
- HTTP WebFlux server on **8080**, endpoint `GET /http/greet?name=Mai`.
- RSocket TCP server on **7000** with four routes:
  - `demo.greet`: Request-Response.
  - `demo.notice`: Fire-and-Forget.
  - `demo.ticks`: Request-Stream.
  - `demo.uppercase`: Request-Channel.

Includes an integration test that **starts the real server**, connects via TCP using `RSocketRequester.Builder.tcp(...)`, and exercises every model without needing external HTTP/CLI tools for RSocket tests.

### 8.1. Directory Structure

```text
rsocket-vs-http-demo/
├── build.gradle
└── src/
    ├── main/
    │   ├── java/com/example/rsocketdemo/RSocketVsHttpApplication.java
    │   └── resources/application.properties
    └── test/
        └── java/com/example/rsocketdemo/RSocketInteractionTest.java
```

### 8.2. Gradle Build — Java 17+ and Spring Boot 3.3.13

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
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
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-rsocket'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

**Dependency notes:**
- `spring-boot-starter-webflux` provides the reactive HTTP server, Reactor, and codecs.
- `spring-boot-starter-rsocket` provides the RSocket transport, Spring Messaging integration, and requester.
- `spring-boot-starter-test` + `reactor-test` provide JUnit and `StepVerifier` if testing Publishers directly.
- Omit `spring-boot-starter-web` so Spring Boot does not prioritize Servlet/MVC when both starters appear.

This runs **two servers in one process on separate ports** in the example. Adding the RSocket starter does not make HTTP GET routes into RSocket routes; they remain distinct entry points.

### 8.3. Application Properties

`src/main/resources/application.properties`:

```properties
spring.application.name=rsocket-vs-http-demo

# HTTP API (Spring WebFlux):
server.port=8080

# RSocket TCP listens on a separate port:
spring.rsocket.server.transport=tcp
spring.rsocket.server.address=127.0.0.1
spring.rsocket.server.port=7000
```

`spring.rsocket.server.address=127.0.0.1` binds loopback **for the local demo**. If an RSocket requester runs from another container/host, loopback will not be reachable; production requires explicit listening addresses, network policies, service mesh/firewall rules, TLS, and authentication. **Never expose an RSocket port to the public Internet by default.**

Spring Boot starts the RSocket server only when matching configuration and dependencies are present. With TCP, `spring.rsocket.server.port` sets the RSocket port; it is separate from HTTP `server.port`. `curl http://localhost:7000/...` cannot speak to RSocket TCP even though port 7000 is listening.

### 8.4. Java Application — All Four Models

`src/main/java/com/example/rsocketdemo/RSocketVsHttpApplication.java`:

```java
package com.example.rsocketdemo;

import java.util.Locale;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.MediaType;
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@SpringBootApplication
public class RSocketVsHttpApplication {

    public static void main(String[] args) {
        SpringApplication.run(RSocketVsHttpApplication.class, args);
    }
}

// HTTP request-response, for browsers/curl.
@RestController
class HttpGreetingController {

    @GetMapping(
            path = "/http/greet",
            produces = MediaType.TEXT_PLAIN_VALUE)
    Mono<String> greet(@RequestParam String name) {
        return Mono.just("Hello, " + name + "!");
    }
}

// RSocket: routes via metadata instead of HTTP method + URL.
@Controller
class RSocketDemoController {

    private static final Logger log =
            LoggerFactory.getLogger(RSocketDemoController.class);

    // 1 input -> 1 output: Request-Response.
    @MessageMapping("demo.greet")
    Mono<String> greet(@Payload String name) {
        return Mono.just("Hello, " + name + "!");
    }

    // 1 input -> no response payload: Fire-and-Forget.
    @MessageMapping("demo.notice")
    Mono<Void> notice(@Payload String message) {
        return Mono.fromRunnable(() ->
                log.info("Demo notice received (length={}): ",
                        message.length()));
    }

    // 1 input -> stream output: Request-Stream.
    @MessageMapping("demo.ticks")
    Flux<String> ticks(@Payload Integer count) {
        if (count == null || count < 1 || count > 5) {
            return Flux.error(new IllegalArgumentException(
                    "count must be between 1 and 5"));
        }
        return Flux.range(1, count)
                .map(i -> "tick-" + i);
    }

    // Stream input -> stream output: Request-Channel.
    @MessageMapping("demo.uppercase")
    Flux<String> uppercase(@Payload Flux<String> words) {
        return words.map(value ->
                value.toUpperCase(Locale.ROOT));
    }
}
```

**Why this code fits Java 17+:**
- Only one top-level `public class` (`RSocketVsHttpApplication`); the other two package-private controllers in the same package are still found by component scanning.
- `@RestController` handles the HTTP route. `@Controller` + `@MessageMapping` belong to the RSocket messaging handler, not Servlet `@GetMapping`.
- Return types match interaction models: `Mono<String>` for single response; `Mono<Void>` for FNF; `Flux<String>` for streams.
- Channel accepts `Flux<String>` without sharing a mutable global field/queue.
- `@Payload` clarifies the argument comes from the RSocket payload rather than an HTTP query param.
- `Locale.ROOT` keeps uppercasing independent of the host machine's locale.
- `demo.notice` **logs only character length**, avoiding logging arbitrary client-supplied payloads.
- `ticks` caps output at 5 items so the demo never creates an unbounded source.

**Fire-and-Forget note:** the `Mono.fromRunnable` callback runs when the framework subscribes to the `Publisher`. Completing `send()` on the requester **is not proof** the log line was already written on the responder. If business logic requires confirmation, use Request-Response returning an acknowledgement after commit.

**Practical note:** `ticks` in the demo uses synchronous `Flux.range`, so it does not simulate latency or network backpressure. That is enough to learn the interaction model. To observe timed streaming, you could insert `delayElements(Duration.ofMillis(200))` (importing `Duration`), though tests will run slower without changing RSocket semantics.

### 8.5. Running and Checking HTTP

In the project folder, with JDK 17+ and Gradle compatible with Boot 3.3.13:

```bash
gradle bootRun
```

If a Gradle Wrapper exists: `./gradlew bootRun` on macOS/Linux or `.\gradlew.bat bootRun` in PowerShell. You need either a Gradle wrapper or Gradle installed; this guide does not silently generate a wrapper.

Test HTTP with curl:

```bash
curl -i "http://localhost:8080/http/greet?name=Mai"
```

Expected body:

```text
Hello, Mai!
```

Expected HTTP status `200 OK`, `Content-Type` matching `text/plain`. This is an **HTTP** endpoint. There is no simple REST `curl` command equivalent to calling `demo.greet` over RSocket TCP; you need an RSocket client speaking the binary protocol or the integration test below.

## 9. Real RSocket Integration Tests over TCP

To avoid port collisions on CI, the test uses:
- `@SpringBootTest(webEnvironment=RANDOM_PORT)` so the HTTP server picks a random port.
- Test property `spring.rsocket.server.port=0` so the RSocket server also picks a random port.
- `@LocalRSocketServerPort` (Spring Boot 3.3) to inject the **actual RSocket port**.
- Boot auto-configured `RSocketRequester.Builder` using matching codecs/MIME types.

`src/test/java/com/example/rsocketdemo/RSocketInteractionTest.java`:

```java
package com.example.rsocketdemo;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.List;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.rsocket.server.LocalRSocketServerPort;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.messaging.rsocket.RSocketRequester;

import reactor.core.publisher.Flux;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
        properties = "spring.rsocket.server.port=0")
class RSocketInteractionTest {

    @LocalRSocketServerPort
    int rsocketPort;

    @LocalServerPort
    int httpPort;

    @Autowired
    RSocketRequester.Builder requesterBuilder;

    @Test
    void httpRequestResponseUsesStatusAndBody() throws Exception {
        HttpClient client = HttpClient.newHttpClient();

        HttpRequest request = HttpRequest.newBuilder(
                URI.create("http://127.0.0.1:" + httpPort
                        + "/http/greet?name=Mai"))
                .GET()
                .build();

        HttpResponse<String> response = client.send(
                request, HttpResponse.BodyHandlers.ofString());

        assertEquals(200, response.statusCode());
        assertEquals("Hello, Mai!", response.body());
    }

    @Test
    void requestResponseReturnsOneMessage() {
        RSocketRequester requester =
                requesterBuilder.tcp("127.0.0.1", rsocketPort);
        try {
            String reply = requester.route("demo.greet")
                    .data("Mai")
                    .retrieveMono(String.class)
                    .block(Duration.ofSeconds(5));

            assertEquals("Hello, Mai!", reply);
        } finally {
            requester.dispose();
        }
    }

    @Test
    void requestStreamReturnsSeveralMessages() {
        RSocketRequester requester =
                requesterBuilder.tcp("127.0.0.1", rsocketPort);
        try {
            List<String> replies = requester.route("demo.ticks")
                    .data(3)
                    .retrieveFlux(String.class)
                    .collectList()
                    .block(Duration.ofSeconds(5));

            assertEquals(
                    List.of("tick-1", "tick-2", "tick-3"),
                    replies);
        } finally {
            requester.dispose();
        }
    }

    @Test
    void requestChannelStreamsBothDirections() {
        RSocketRequester requester =
                requesterBuilder.tcp("127.0.0.1", rsocketPort);
        try {
            List<String> replies = requester.route("demo.uppercase")
                    .data(Flux.just("one", "two"), String.class)
                    .retrieveFlux(String.class)
                    .collectList()
                    .block(Duration.ofSeconds(5));

            assertEquals(
                    List.of("ONE", "TWO"),
                    replies);
        } finally {
            requester.dispose();
        }
    }

    @Test
    void fireAndForgetCanSendWithoutResponsePayload() {
        RSocketRequester requester =
                requesterBuilder.tcp("127.0.0.1", rsocketPort);
        try {
            requester.route("demo.notice")
                    .data("ping")
                    .send()
                    .block(Duration.ofSeconds(5));
            // Do not assert business state committed.
            // send() only confirms the message was sent per contract.
        } finally {
            requester.dispose();
        }
    }
}
```

Run:

```bash
gradle test
```

**Expected outcome** (by logic and API): all five tests pass given compatible dependencies and environment. **Gradle was not executed in this lesson**, so do not treat this as a verified runtime log.

**Takeaways from the tests:**
- HTTP `HttpClient` inspects `statusCode()` and body.
- `RSocketRequester` uses `route(...)`/`data(...)`/`retrieveMono` or `retrieveFlux`, without HTTP paths, methods, or statuses.
- `RSocketRequester.Builder.tcp(...)` in Spring Framework 6.1 returns an **immediately usable requester** that connects lazily/shares the client, unlike the deprecated `connectTcp(...): Mono<RSocketRequester>` API.
- `requester.dispose()` releases the client/connection after the test so sockets do not leak.
- `block(Duration)` is valid on the **JUnit test thread** to assert results. **Never** call `block()` on a Reactor Netty event-loop thread or inside a production RSocket handler.
- The Fire-and-Forget test only proves **it can be sent**, not that the server finished side effects — that is a semantic distinction, not a missing assertion.
- The RSocket server port can differ from the HTTP port; `@LocalServerPort` and `@LocalRSocketServerPort` are not interchangeable.

If a test times out, inspect TCP binding, route names, serializers, thread starvation, and shutdown cleanup rather than blindly raising the timeout.

## 10. Why Can't You Call RSocket TCP with a REST Client or curl?

RSocket over TCP speaks **RSocket frames**, not HTTP headers/bodies. Therefore:

```bash
# RIGHT: This is an HTTP endpoint.
curl -i "http://localhost:8080/http/greet?name=Mai"

# WRONG TOOL: Port 7000 is RSocket TCP,
# not an HTTP server.
curl -i "http://localhost:7000/demo.greet"
```

An RSocket client initializes a requester:

```java
// Snippet inside a test/service with injected RSocketRequester.Builder.
RSocketRequester requester = builder.tcp(
        "127.0.0.1", 7000);

Mono<String> reply = requester.route("demo.greet")
        .data("Mai")
        .retrieveMono(String.class);

// In a Spring WebFlux business service, return/compose the reply.
// Do not fire-and-forget subscribe() ignoring results and errors.
```

This snippet is **not a standalone class**: it requires imports for `RSocketRequester`, `Mono`, and an injected `builder`. In real applications, manage the requester as a shared client with proper shutdown/dispose rather than creating a new requester/connection per business request.

Dedicated RSocket CLI tools can send protocol-compliant frames and metadata, yet you should never equate an HTTP GET with an RSocket route just by changing the URL.

## 11. RSocket-over-WebSocket: When Raw TCP Cannot Traverse Infrastructure

When browsers or gateways only permit HTTP(S)/WebSocket, Spring Boot can serve RSocket **over WebSocket** instead of raw TCP. With a WebFlux server and Reactor Netty, RSocket can mount onto the existing HTTP server:

```properties
# Alternative profile/config to the TCP example (do not combine simultaneously).
server.port=8080
spring.rsocket.server.transport=websocket
spring.rsocket.server.mapping-path=/rsocket
# Do not set spring.rsocket.server.port when sharing
# the HTTP WebFlux server via Boot's integrated mode.
```

External Java client:

```java
// Snippet in service/test:
RSocketRequester requester = builder.websocket(
        URI.create("ws://localhost:8080/rsocket"));

Mono<String> reply = requester.route("demo.greet")
        .data("Mai")
        .retrieveMono(String.class);
```

Requires imports `URI`, `RSocketRequester`, `Mono`, and a configured builder. `ws://` is for local environments without TLS; production browsers/HTTPS must use `wss://` with valid certificates. You can also run a standalone RSocket-over-WebSocket server by setting a port/transport; **sharing `mapping-path` on the HTTP web server** depends on the server stack (Spring Boot docs specify Reactor Netty).

**Important:** a WebSocket connection carrying RSocket **is not** a raw WebSocket chat connection. Clients must implement **RSocket SETUP, framing, metadata, and interaction models** over that transport. The bare browser WebSocket API only moves raw bytes/messages and does not speak RSocket protocol.

Behind a reverse proxy/ingress, ensure WebSocket upgrades, TLS, idle timeouts, host/origin policies, connection limits, and buffering are configured properly. Do not assume an HTTP API gateway understands RSocket route metadata or applies HTTP per-request authorization to individual RSocket frames.

## 12. RSocket vs. Raw WebSocket and Server-Sent Events (SSE)

| Concern | Raw WebSocket | RSocket | SSE |
|---|---|---|---|
| Protocol/abstraction | Duplex frames; app defines custom JSON commands | Duplex + 4 interaction models, route/data/metadata | Server → client HTTP event stream |
| Application backpressure | Must be designed manually if needed | Network Reactive Streams demand for streams | Typically depends on HTTP/reader/network and client protocol |
| Multiplexing logical streams | App must add message IDs/routes | Protocol-level stream IDs | One HTTP response stream; multiple connections possible |
| Built-in request-response semantics | App must manage correlation IDs | Request-Response | Must use separate HTTP requests for client → server |
| Browser availability | Native WebSocket API | Requires RSocket client library over WebSocket | Native `EventSource` |
| Gateways/public Internet | Usually works where upgrades are supported | Raw TCP is harder; WS transport needs proxy/stack support | HTTP tooling/ingress is most familiar |
| Durable message broker | Not included | Not included | Not included |
| Per-event authorization | Built by app | Built by app via RSocket metadata/routes/security | Built by app via HTTP/session |

If you only need "server pushes new order counts to a dashboard," **SSE can be simpler**. If you need bidirectional browser chat without message-level backpressure or correlation complexity, raw WebSocket may suffice. With multiple bidirectional streams and internal/client support for Spring Reactive, RSocket is worth considering.

## 13. Frame-Level Backpressure, LEASE, KEEPALIVE, and RESUME

RSocket includes notable protocol capabilities, not all of which are enabled or used by default in Spring Boot:

### 13.1. REQUEST_N

For Request-Stream/Channel, the receiver requests additional messages. `REQUEST_N` signals demand; cancellation signals stopping a stream. **Inspect Reactor operators carefully** because prefetching can cause upstream to request more items than downstream processes at a given instant.

### 13.2. LEASE

LEASE lets a peer advertise how many requests the other peer may initiate within a time window. This is **request admission control**, distinct from `Flux.request(n)` within a single stream. It must be enabled/configured via RSocket connector/server APIs; adding `spring-boot-starter-rsocket` does not mean the app automatically sends `LEASE` frames.

### 13.3. KEEPALIVE

On long-lived connections, keepalive detects dead peers or broken network links. Interval/timeout settings must match proxies, load balancers, networks, and resource limits. HTTP keep-alive, TCP keepalive, and RSocket `KEEPALIVE` **are not the same thing**; they operate at different layers.

### 13.4. RESUME

The RSocket protocol defines session resumption across dropped connections when both peers retain required state. **This does not create exactly-once business transactions**, store messages indefinitely, or guarantee recovery across pod crashes/restarts. Enabling resume adds memory/storage/operational complexity; configure both sides for compatible transports/versions and test with real fault injection.

### 13.5. Fragmentation

RSocket can split large payloads/frames into fragments and reassemble them. Still, frame fragmentation **does not replace** max message size limits, codec memory caps, queue limits, or validation. Huge payloads can still trigger OOM if the app buffers whole DTOs/`byte[]` arrays in memory.

## 14. Cancellation, Timeouts, and Error Semantics

Over HTTP, a client can cancel a request or close the socket; depending on the stack, the server may detect I/O closure and cancel the reactive pipeline. In RSocket streaming, a requester can cancel **one stream** while the connection keeps serving all other streams.

```text
Shared RSocket connection
   │
   ├── Stream A: demo.ticks ── CANCEL ──► stops A when upstream cooperates
   │
   ├── Stream B: demo.greet ── PAYLOAD ─► continues to completion
   │
   └── Stream C: demo.uppercase ────────► stays active
```

**Do not confuse cancel with error or assume automatic rollback**:
- `onComplete`: `Publisher` finished normally.
- `onError`: encode/decode, handler, transport, or business failure.
- `cancel`: downstream no longer wants items; upstream is notified if the chain propagates cancellation.
- Reactor `timeout(Duration)` is a client-side deadline on the publisher; it does not guarantee a blocking DB query or call actually stopped on the server.
- If data was already committed to the DB before cancellation, cancelling the stream does not roll back the commit.
- Dropping the connection can fail multiple in-flight streams simultaneously; never blindly retry side-effecting commands.

Example where a client **takes only two ticks and cancels the rest**:

```java
// Snippet inside a service/test:
Flux<String> firstTwo = requester.route("demo.ticks")
        .data(5)
        .retrieveFlux(String.class)
        .take(2);

// Return or subscribe safely in the appropriate runtime.
```

`take(2)` cancels upstream after receiving two elements per contract. However, **it is no guarantee the server produced only two items**: due to prefetching, network buffering, and scheduling, extra items may have been generated or sent before cancellation arrived.

**Proper error handling:** never write unconditional `onErrorResume(e -> Mono.empty())` if doing so hides protocol, auth, or serialization failures. Map exceptions to observable error policies, use bounded retries, log correlation IDs, and emit metrics without printing raw tokens or sensitive payloads.

## 15. Security: Do Not Treat RSocket as HTTP with an Extra Port

A dangerous deployment mistake is securing `/api/**` with Spring Security WebFlux while leaving the RSocket TCP port publicly open **with no RSocket security**. They are **two separate entry points**.

Address all of the following:
1. **Transport security:** TLS on RSocket TCP (or WSS for RSocket-over-WebSocket), certificate validation, and mTLS if your threat model requires it.
2. **Connection-level authentication:** authenticate peers at `SETUP`/metadata using Spring Security RSocket or an equivalent policy.
3. **Per-route authorization:** an authenticated connection must not automatically grant access to every route or tenant action.
4. **Payload validation:** message sizes, DTO schemas/versions, allowed routes, ownership/tenant checks, rate limits.
5. **Network policy:** restrict RSocket TCP ports to authorized clients via proxies, mTLS, or ingress ACLs.
6. **Secrets:** never log payloads, setup tokens, cookies, or authorization metadata; support secret rotation and revocation.
7. **Backpressure/resource quotas:** cap concurrent streams, queues, frame/message sizes, and long-lived subscriptions.

Spring Security supports RSocket security, yet requires its own module/dependencies and configuration. Adding `spring-boot-starter-rsocket` **does not enable authentication** or apply HTTP `SecurityWebFilterChain` rules to RSocket TCP. Never trust raw metadata like `X-User-Id` as a verified identity.

For RSocket-over-WebSocket from browsers, `Origin`, cookies, TLS, reverse proxies, and CORS/WebSocket upgrade policies matter too. **`Origin` is not user authentication**; non-browser clients can spoof `Origin`. Commands must still enforce business authorization.

If data contains personal information, enforce encryption in transit and storage protections. RSocket over TCP **is not encrypted by default** in the demo configuration; binding loopback `127.0.0.1` only narrows local exposure in the lab and does not replace TLS over a network.

## 16. RSocketRequester: Managing Client Connections Properly

In Spring Boot 3.3, an auto-configured prototype `RSocketRequester.Builder` bean is provided with codecs and `RSocketConnectorConfigurer` customizations. The builder is stateful; do not mutate the same builder instance across incompatible configurations without isolating it.

You can create a shared requester at startup/configuration time:

```java
// Illustrative snippet inside @Configuration:
// Inject RSocketRequester.Builder builder.

@Bean(destroyMethod = "dispose")
RSocketRequester inventoryRequester(
        RSocketRequester.Builder builder) {
    return builder.tcp("inventory.internal.example", 7000);
}
```

This is a **configuration snippet** requiring `Bean` and `RSocketRequester` imports. `tcp(...)` returns a requester using a shared connection (which may connect lazily). `destroyMethod="dispose"` closes the client when the Spring context shuts down. In production, externalize host/port/SSL settings and enforce network policies.

**Do not create a new TCP requester on every incoming HTTP request.** Doing so multiplies sockets and handshakes, defeats multiplexing, and leaks resources. One requester per downstream service/trust domain is normally far cleaner.

**Never block inside a reactive runtime:** `retrieveMono(...)` returns a `Publisher`. Inside a WebFlux handler, return or compose the `Publisher` rather than calling `block()` on Reactor Netty's event loop. If calling a blocking external SDK, offload onto a bounded worker pool with concurrency limits, without mistaking that for true non-blocking I/O.

`data(Object)` and `data(Publisher, elementType)` are distinct overloads. For a `Flux<T>` Request-Channel, use the element-type overload like `data(Flux.just("a","b"), String.class)` so the framework knows the codec for each item.

## 17. HTTP Mappings and RSocket Routes Are Not Interchangeable

Side by side:

```java
// HTTP:
@GetMapping("/http/greet")
Mono<String> greet(@RequestParam String name) {
    return Mono.just("Hello, " + name + "!");
}

// RSocket:
@MessageMapping("demo.greet")
Mono<String> greetRSocket(@Payload String name) {
    return Mono.just("Hello, " + name + "!");
}
```

This is an **illustrative snippet**, requiring enclosing controller classes and imports; the complete project appeared in Section 8. HTTP passes `name` in the URL query string; RSocket passes `name` in the data payload with the route in metadata.

**Never infer an HTTP API path from an RSocket route.** To expose the same business operation over both protocols, place the core logic in a shared service:
- The HTTP controller adapts HTTP requests/responses to the service.
- The RSocket responder adapts RSocket payloads/metadata to the service.
- The service enforces authorization, validation, and business logic.
- Both transports maintain separate error handling, auth, timeouts, and lifecycles.

Sharing a service avoids duplicating business logic, yet verify **both transports enforce equivalent security policies and validation semantics**. A service protected only by an HTTP web filter is unprotected if an RSocket route invokes it directly without method-level authorization.

## 18. Streaming Real Data: When Not to Use Flux.interval

In the demo, `Flux.range` emits a finite sequence. In production, streams originate from DBs, Kafka, sensor callbacks, or multi-step pipelines. `Flux.interval` is merely an in-memory periodic timer, not a persistent message broker.

**Illustrative** bounded periodic stream example:

```java
@MessageMapping("demo.clock")
Flux<String> clock(@Payload Integer count) {
    int bounded = Math.max(1, Math.min(count, 10));
    return Flux.interval(Duration.ofSeconds(1))
            .take(bounded)
            .map(i -> "second-" + i);
}
```

This snippet is not part of Section 8's runnable app; adding it requires importing `Duration` and ensuring `count` is non-null before `Math.min`. It is a **demo snippet**, not advice to spawn thousands of timers for thousands of clients without memory and scheduler analysis.

**Production requires:**
- Backpressure-aware sources or bounded bridges from hot/non-reactive sources.
- Caps on streams per user, data rates, in-flight messages, and memory.
- Deadlines, heartbeats, cancellation cleanup, retries/backoff, and monitoring.
- Durable sources of truth when clients must receive every missed event after reconnecting.
- Never holding Java entities or database connections open for an unbounded stream without release.
- Node-failure recovery; session resumption only when both peers implement it with supporting state.

A broker like Kafka or RabbitMQ handles durable storage and routing; RSocket handles **direct peer-to-peer communication** and does not replace a message broker's durability or consumer-group features.

## 19. Deploying via Docker/Kubernetes, Proxies, and Scale-Out

Infrastructure considerations:

| Concern | HTTP | RSocket |
|---|---|---|
| Exposure | HTTP/HTTPS Ingress is standard | TCP needs L4 Services/routing or RSocket-over-WebSocket |
| Discovery | DNS/API gateways, HTTP service routes | DNS/port or RSocket load balancing; no default HTTP routes |
| Load balancing | Per HTTP request/connection depending on HTTP version | Connections are long-lived; understand per-connection distribution |
| Pod restarts | Failed HTTP requests may retry per policy | Many in-flight RSocket streams can fail together |
| TLS | HTTPS, proxy termination | TLS TCP or WSS; configured separately per transport |
| Metrics | Standard HTTP status/URI templates | Track per-route, stream, connection, and error metrics |
| Scale-out | Stateless HTTP endpoints scale easily | Connected clients stick to one backend; cross-node broadcast needs a broker |
| Browsers | Native HTTP | RSocket-over-WebSocket requires client library/protocol support |

Because one RSocket connection multiplexes many logical requests, L4 load balancers distribute **connections** rather than individual requests like an HTTP/1.1 gateway. Size capacity for **active connections, streams per connection, and per-node workload**, not just requests per second.

During pod draining, servers should stop accepting new connections, drain reasonable in-flight work, and signal clients to reconnect with jitter. Client retries do not eliminate duplicate side effects; use idempotency keys for DB or financial mutations.

When RSocket-over-WebSocket passes through NGINX/Ingress, verify upgrades, keepalive/idle timeouts, max frame sizes, and TLS hostnames/certificates — not merely whether the TCP port is open.

## 20. Observability, Timeouts, and Troubleshooting

### 20.1. Metrics to Track

- **Connection:** active RSocket connections, connect/setup failures, disconnect reasons, missed keepalives.
- **Per interaction:** route name, model type, stream duration, request rate, active streams, errors, cancellations.
- **Backpressure/resource:** requested vs. produced/delivered items, queued bytes, pooled direct memory, frame sizes.
- **Resilience:** retry counts, reconnect latency, timeouts, pod drain interruptions.
- **Security:** auth failures, rejected routes, invalid payloads, rate-limit rejections, TLS failures.
- **Business:** processed/committed events separated from "message sent" counters.

Tag metrics by **stable route template**, never raw payloads, user IDs, or tokens that cause unbounded cardinality. Metadata-based tracing requires instrumentation, context propagation, and privacy controls; RSocket does not automatically produce distributed traces just because frames exist.

### 20.2. Common Error Table

| Symptom | Possible Cause | Fix |
|---|---|---|
| `curl localhost:7000` fails HTTP | Port 7000 is RSocket TCP, not HTTP | Use `RSocketRequester` or an RSocket CLI, not a URL tweak |
| Connection refused | RSocket server not bound, wrong port/address | Check `spring.rsocket.server.port/address/transport` |
| `GET /demo.greet` 404 | `@MessageMapping` does not create HTTP endpoints | Use RSocket route metadata via a requester |
| Request reaches route yet fails decoding | Incompatible MIME/codec or JSON/CBOR DTO | Check `RSocketStrategies`, `dataMimeType`, encoded payload |
| `retrieveMono` emits nothing | Wrong route, interaction mismatch, empty payload response | Check handler signature, server logs, error frames |
| Fire-and-Forget lacks business ACK | Protocol has no response payload | Use Request-Response or explicit ACK workflow |
| Stream runs forever | Infinite `Flux`, no duration/element bound | `take`/timeout/cancel, limits, cleanup |
| Slow client spikes RAM | Hot source ignores demand, unbounded queue | Backpressure-aware bridges, bounds, drop/replay policies |
| Thread starvation | `block()`/sync JDBC on Reactor event loop | Non-blocking drivers or bounded offload |
| TLS handshake fails | Wrong CA/SAN/cert or TLS unconfigured | Configure proper trust material, never trust-all |
| RSocket TCP works locally yet fails via Ingress | Ingress routes HTTP only, not raw TCP | L4 routing or RSocket-over-WebSocket |
| Browser WebSocket connects yet server rejects protocol | Sending raw WS messages instead of RSocket frames | Use RSocket client library and proper `SETUP` |
| Session lost on pod restart | No durable state/resumption configured | Reconnect/re-auth/replay from broker or DB |
| FNF processed twice on retry | Delivery lacks business idempotency | Event IDs and consumer deduplication |
| HTTP and RSocket share service with inconsistent auth | HTTP filter chain does not protect RSocket TCP | Add RSocket Security and method-level policies |
| Client uses `wss://` while server runs TCP | Transport configuration mismatch | Match WebSocket transport and `mapping-path` |
| Independent streams fail together on disconnect | Shared connection dropped | Distinguish stream cancellation from connection loss |
| `@WebFluxTest` lacks RSocket server | Test slice does not load full RSocket infrastructure | Use `@SpringBootTest` with a real RSocket port |

**Never diagnose RSocket solely from HTTP status codes.** For TCP, inspect RSocket error frames, application logs, and Reactor signals. Over WebSocket, HTTP `101` reflects only the upgrade step, not individual RSocket business request outcomes.

## 21. Protocol Design and Operations Checklist

- [ ] Does the requirement genuinely need full-duplex/streaming, or do HTTP/SSE suffice?
- [ ] Is the interaction model matched to exact cardinality (0/1/many)?
- [ ] Are route metadata, data payloads, and HTTP URLs clearly separated?
- [ ] Are HTTP statuses and RSocket error semantics mapped independently?
- [ ] Have codecs/MIME types and DTO versions been verified across peers?
- [ ] Do RSocket TCP/WebSocket transport, port, `mapping-path`, and TLS align?
- [ ] Are connection authentication and per-route/command authorization enforced?
- [ ] Do reactive sources honor demand, and are queues/sinks bounded?
- [ ] Are timeouts, cancellations, and cleanup explicit per stream and connection?
- [ ] Can Fire-and-Forget tolerate no ACK, or is business confirmation required?
- [ ] Do retries use idempotency keys, attempt caps, and backoff?
- [ ] Are requesters reused and disposed properly across the lifecycle instead of leaked?
- [ ] Have all four models been tested with a real RSocket client alongside an HTTP baseline?
- [ ] Are active connections, streams, errors, cancellations, queue bytes, and memory monitored?
- [ ] Is there a reconnect/resume/replay plan for instance or network failures?
- [ ] Do browsers/gateways actually support the RSocket library/proxy setup?
- [ ] Are HTTP and RSocket security policies independent yet consistent with business rules?

## 22. Self-Check Questions

**1. How does RSocket Request-Response differ from HTTP?**  
Both model one request and one response, yet RSocket routes via metadata, exchanges payloads/errors as RSocket frames over a shared connection, and carries no HTTP method or status code per interaction.

**2. Does HTTP/2 multiplex?**  
Yes. Multiplexing cannot be claimed as exclusive to RSocket. RSocket differs in its four interaction models and protocol-level Reactive Streams demand.

**3. Does a successful Fire-and-Forget `send().block()` mean the message committed to the DB?**  
No. Per contract it confirms only that the message was sent; use a business-level ACK or durable model when confirmation is required.

**4. How does Request-Stream differ from Request-Channel?**  
Request-Stream: one request, multiple responses. Channel: both peers can send streams of messages within one interaction.

**5. Does `@MessageMapping("demo.greet")` handle HTTP `GET /demo.greet`?**  
No, that is an RSocket route, not an HTTP path/method.

**6. Why can't `curl http://localhost:7000` invoke RSocket TCP?**  
The RSocket TCP port speaks the binary RSocket protocol and does not parse HTTP request lines or headers.

**7. Does `RSocketRequester.Builder.tcp` require `block()` on creation?**  
In Spring Framework 6.1, `tcp(host,port)` returns an immediately usable `RSocketRequester` that connects lazily/shares connections. The older `connectTcp` returning `Mono` is deprecated.

**8. Can you enable `spring.rsocket.server.transport=websocket` and send raw JSON from a browser WebSocket?**  
No, WebSocket is only the transport; payloads inside must still conform to the RSocket protocol.

**9. Does RSocket replace Kafka or RabbitMQ for durable storage?**  
No. It is a peer-to-peer communication protocol; durable brokers, replay, and consumer groups require separate systems/designs.

**10. Does cancelling a stream roll back DB work?**  
Not automatically. Cancellation only signals upstream to stop if possible; committed side effects require dedicated transaction/idempotency handling.

**11. Why can't a normal HTTP proxy route RSocket TCP by path?**  
RSocket TCP has no HTTP URL or method. Use L4 forwarding or RSocket-over-WebSocket with protocol support.

**12. If Spring Security protects HTTP endpoints, is RSocket TCP already safe?**  
No. RSocket TCP has its own handshake/security boundary and needs transport security, authentication/authorization, validation, and network ACLs.

## 23. Official Documentation and Further Reading

1. Spring Framework — **RSocket protocol overview, RSocketRequester, Annotated Responders**, 4 interaction types, SETUP, and REQUEST_N: https://docs.spring.io/spring-framework/reference/rsocket.html
2. Spring Boot 3.3 — **RSocket integration** (TCP/WebSocket servers, messaging, requester): https://docs.spring.io/spring-boot/3.3/reference/messaging/rsocket.html
3. Spring Boot 3.3 — **Common Application Properties**, `spring.rsocket.server.*`: https://docs.spring.io/spring-boot/3.3/appendix/application-properties/
4. Spring Framework 6.1 — **RSocketRequester.Builder** Javadoc, `tcp`, `websocket`, and deprecated `connectTcp`: https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/messaging/rsocket/RSocketRequester.Builder.html
5. Spring Boot 3.3 — **LocalRSocketServerPort** for integration tests: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/rsocket/server/LocalRSocketServerPort.html
6. Spring Project blog — **Getting Started with RSocket: Spring Boot Server**: https://spring.io/blog/2020/03/02/getting-started-with-rsocket-spring-boot-server/
7. Spring Project blog — **Testing Spring Boot Responders**: https://spring.io/blog/2020/05/25/getting-started-with-rsocket-testing-spring-boot-responders/
8. RSocket Protocol website/specification: https://rsocket.io/
9. Reactive Streams Specification, `request(n)`/backpressure: https://www.reactive-streams.org/

**Conclusion:** HTTP request–response remains the right default for most public APIs. RSocket provides a message-oriented protocol supporting Request-Response, Fire-and-Forget, Request-Stream, and Request-Channel over multiplexed connections with application-level backpressure. In Spring Boot, use `spring-boot-starter-rsocket`, `@MessageMapping`, and `RSocketRequester` to implement the four models, while explicitly designing security, timeouts, durability, retries/idempotency, and transport operations for production.