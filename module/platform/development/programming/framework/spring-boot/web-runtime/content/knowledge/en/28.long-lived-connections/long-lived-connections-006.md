# WebSocketHandler and WebSocketSession in WebFlux

## 1. WebSocket in a Spring Boot web-runtime Application

HTTP request–response fits when a client calls an API, waits for a response, and finishes the interaction. For chat, continuously updating price tickers, collaborative notifications, device telemetry, or games, a long-lived bidirectional connection avoids repeating HTTP requests. **WebSocket** (RFC 6455) provides a **full-duplex** channel: both ends can send messages over a connection upgraded from HTTP.

In **Spring WebFlux**, you can handle this protocol at a low level with:

- `org.springframework.web.reactive.socket.WebSocketHandler`: interface taking a WebSocket session and returning `Mono<Void>` representing the lifetime of session handling.
- `org.springframework.web.reactive.socket.WebSocketSession`: abstraction for the connection and its two message streams: `receive()` and `send(...)`.
- `WebSocketMessage`: holds the message type (`TEXT`, `BINARY`, `PING`, `PONG`) and `DataBuffer` payload.
- `SimpleUrlHandlerMapping`: maps a `WebSocketHandler` to a URL such as `/ws/echo`.
- `WebSocketHandlerAdapter`: integrates the handler into WebFlux `DispatcherHandler` via a handshake service/upgrade strategy.

**Objective:** understand the handshake, create an endpoint, compose inbound–outbound streams, handle completion/cancellation/errors, protect long-lived connection resources, build a runnable Java 17+ example, test with a real WebSocket client, and grasp security/operational limits for production.

**Version context:** examples use **Spring Boot 3.3.13, Spring Framework 6.1.x, Java 17+** and `spring-boot-starter-webflux` to avoid confusion with Servlet WebSocket APIs. For production, pick a supported Boot/Framework line receiving security patches. Newer versions may introduce updated APIs/configurations, so never mix packages merely because class names look identical.

## 2. How Does WebSocket Differ from HTTP, SSE, and Polling?

| Feature | HTTP API | SSE | WebSocket |
|---|---|---|---|
| Transport pattern | Request → Response | One HTTP response stream from server → client | Bidirectional over the same connection |
| Initiation | Regular HTTP request | HTTP GET with `text/event-stream` | HTTP handshake and upgrade (commonly HTTP/1.1) |
| Data model | HTTP/JSON body | SSE text events | Protocol text/binary messages/frames |
| Client sending data | Separate HTTP requests | Usually separate HTTP requests | `send(...)` over the open socket |
| Infrastructure | Standard proxies/caches | Requires response streaming support | Proxy must support WebSocket upgrade and long-lived connections |
| Best suited for | CRUD and most app APIs | Feeds, server→browser notifications | Chat, collaboration, bidirectional real-time |
| Lifecycle scope | Per request | Per stream | Per long-lived connection/session |

A WebSocket can run over `ws://` or `wss://` (TLS). Browsers loading pages via HTTPS generally must connect using `wss://` to avoid mixed-content restrictions; production should always enforce TLS with proper certificate validation.

**Do not confuse low-level WebSocket with STOMP/SockJS.** The handler in this lesson operates on raw WebSocket protocol frames: your app defines what text/binary messages mean. With a STOMP broker, destinations and `@MessageMapping` belong to a different abstraction and do not appear automatically when creating a reactive `WebSocketHandler`.

**Do not confuse reactive with infinite scalability.** Even with Publisher-based I/O, every connection consumes a socket, memory, TLS state, metrics, heartbeats, and often session state. If each client opens multiple connections, memory/FD limits and outbound queues still require governance.

## 3. Handshake: Where Does HTTP Become WebSocket?

In the common HTTP/1.1 model, the client sends a request with headers:

```http
GET /ws/echo HTTP/1.1
Host: localhost:8080
Upgrade: websocket
Connection: Upgrade
Sec-WebSocket-Version: 13
Sec-WebSocket-Key: <base64-random-key>
Origin: http://localhost:8080
```

This is an **illustrative request**; `Sec-WebSocket-Key` must be a valid client-generated base64 value, not a literal placeholder. If accepted, the response looks like:

```http
HTTP/1.1 101 Switching Protocols
Upgrade: websocket
Connection: Upgrade
Sec-WebSocket-Accept: <derived-value>
```

Afterward, client and server exchange **WebSocket frames** over the connection rather than creating a new HTTP response per message. `101 Switching Protocols` belongs to the **handshake**, not a status returned each time the app calls `session.send(...)`.

Server-side flow in WebFlux:

```text
Browser/WebSocket client
           │
           │ GET /ws/echo + Upgrade
           ▼
HTTP server (Reactor Netty in Boot WebFlux default)
           │
           ▼
WebFilter (authentication, policies if configured)
           │
           ▼
DispatcherHandler
           │
           ▼
SimpleUrlHandlerMapping: "/ws/echo" → EchoWebSocketHandler
           │
           ▼
WebSocketHandlerAdapter
           │
           ▼
HandshakeWebSocketService
           │
           ▼
RequestUpgradeStrategy (per HTTP server)
           │
           ▼
HTTP 101 → WebSocketSession created
           │
           ▼
EchoWebSocketHandler.handle(session): Mono<Void>
           │
     ┌─────┴─────┐
     ▼           ▼
 receive()     send(...)
     │           ▲
     └─ process ─┘
```

`WebSocketHandlerAdapter` uses `WebSocketService` (defaulting to `HandshakeWebSocketService`) to validate the handshake and instruct the server adapter to upgrade. Never build a `101` response manually inside an HTTP controller: the framework handles negotiation and upgrade. A plain GET lacking upgrade headers is not treated as a WebSocket session.

**HTTP/2 note:** WebSocket has an HTTP/2 extension via RFC 8441 extended CONNECT on supporting stacks, but do not assume merely setting `server.http2.enabled=true` enables WebSocket over HTTP/2 automatically. This lesson uses the standard HTTP/1.1 handshake. Behind a CDN/ingress, verify actual protocol support and upgrade behavior at every hop.

## 4. Distinguishing WebFlux WebSocket APIs from Servlet WebSocket APIs

The names `WebSocketHandler`/`WebSocketSession` exist in **two separate package trees** that are easy to mis-import:

| WebFlux Reactive | Servlet/Spring WebSocket |
|---|---|
| `org.springframework.web.reactive.socket.WebSocketHandler` | `org.springframework.web.socket.WebSocketHandler` |
| `org.springframework.web.reactive.socket.WebSocketSession` | `org.springframework.web.socket.WebSocketSession` |
| `handle(WebSocketSession): Mono<Void>` | `handleTextMessage(...)`, `afterConnectionEstablished(...)`, and callbacks |
| `session.send(Publisher<WebSocketMessage>)` | Synchronous/callback-style `session.sendMessage(...)` |
| `Flux<WebSocketMessage> receive()` | Callback-based message delivery, no reactive `receive()` |
| `org.springframework.web.reactive.socket.server.support.WebSocketHandlerAdapter` | Servlet `WebSocketConfigurer`/registry configuration |

Never pass a Servlet-stack handler implementation into a reactive `SimpleUrlHandlerMapping` expecting Spring to convert it. In WebFlux, the core pattern is **composing Publishers** rather than pushing individual messages from arbitrary threads.

WebFlux's `WebSocketSession` is also **different from `WebSession`** (reactive HTTP session state). A `WebSocketSession` is **one network connection**. An HTTP `WebSession` can span many HTTP requests and be referenced during the handshake per policy; there is no mandatory one-to-one relationship between the two. Nor is it equivalent to a Servlet `HttpSession`.

## 5. WebSocketHandler and WebSocketSession Contracts

### 5.1. The Most Important Signature

```java
import org.springframework.web.reactive.socket.WebSocketHandler;
import org.springframework.web.reactive.socket.WebSocketSession;
import reactor.core.publisher.Mono;

class ExampleHandler implements WebSocketHandler {
    @Override
    public Mono<Void> handle(WebSocketSession session) {
        return session.receive().then();
    }
}
```

This is an **illustrative Java class compilable in a WebFlux project**, though not yet mapped to a URL and producing no output. `Mono<Void>` tells the framework **when all handling for the session completes**; it is not an HTTP body.

**Crucial contract:** never call `subscribe()` inside `handle` and immediately return `Mono.empty()`. Doing so tells the framework the session is done while your manual work continues outside the lifecycle, causing premature socket closure or lost error/cancellation propagation.

### 5.2. Commonly Used Methods

| API | Type | Meaning |
|---|---|---|
| `session.receive()` | `Flux<WebSocketMessage>` | Stream of incoming messages; typically completes when connection closes |
| `session.send(messages)` | `Mono<Void>` | Writes an outbound `Publisher`; completes once source finishes and writes finish per contract |
| `session.textMessage(text)` | `WebSocketMessage` | Creates an outgoing TEXT message from a string |
| `session.binaryMessage(factory -> buffer)` | `WebSocketMessage` | Creates an outgoing BINARY message from a `DataBuffer` |
| `session.pingMessage(...)`, `pongMessage(...)` | `WebSocketMessage` | Creates protocol ping/pong messages |
| `session.getId()` | `String` | Connection session ID for internal logging/correlation |
| `session.getHandshakeInfo()` | `HandshakeInfo` | HTTP handshake metadata (URI, headers, principal, subprotocol...) |
| `session.getAttributes()` | `Map<String,Object>` | Attributes attached to the WebSocket session per server/handshake config |
| `session.isOpen()` | `boolean` | Snapshot of whether the connection is open at read time |
| `session.close()` | `Mono<Void>` | Requests normal closure |
| `session.close(CloseStatus)` | `Mono<Void>` | Closes with a specific close code |
| `session.closeStatus()` | `Mono<CloseStatus>` | Observes close status when connection ends per contract |

**Caution:** `isOpen()` is only a point-in-time snapshot; the connection can close right after the check. Never use `isOpen()` as a lock guaranteeing `send` will succeed.

`HandshakeInfo` carries values from the request. **Do not trust** raw client headers or query params as authenticated identity. If inspecting client IP behind a reverse proxy, enforce a dedicated trusted-forwarded-header boundary. `WebSocketSession.getId()` is an internal connection identifier, not a login token.

### 5.3. WebSocketMessage Types

```java
// Code fragment inside WebSocketHandler processing a WebSocketMessage:
WebSocketMessage.Type type = message.getType();
if (type == WebSocketMessage.Type.TEXT) {
    String text = message.getPayloadAsText();
    // Validate text and process right inside the reactive pipeline.
}
```

Common types:
- `TEXT`: UTF-8 string, often carrying JSON or a custom application protocol.
- `BINARY`: byte payload; requires a clear format/protobuf/file-chunk contract.
- `PING`/`PONG`: protocol control frames for liveness (partially handled automatically by the stack).
- `CLOSE` is a protocol **WebSocket control frame**; depending on the adapter, it is typically surfaced via lifecycle/`closeStatus()` rather than as a regular payload message like TEXT/BINARY.

`getPayloadAsText()` assumes UTF-8 decoding makes sense, which suits TEXT; never call it unconditionally on arbitrary binary bytes assuming JSON text. For JSON TEXT messages, bound the size first and then deserialize/validate against a schema rather than parsing with `String.split(...)`.

## 6. Inbound–Outbound Flow: A Lifecycle-Correct Echo Pipeline

The simplest pattern linking receive and send:

```java
@Override
public Mono<Void> handle(WebSocketSession session) {
    Flux<WebSocketMessage> responses = session.receive()
            .map(in -> session.textMessage(
                    "echo: " + in.getPayloadAsText()));

    return session.send(responses);
}
```

This matches the Spring Framework reference example and explains **TEXT echo** when clients send only text. If binary or ping/pong frames arrive, do not decode everything as text; the runnable version in section 7 filters for TEXT and releases discarded messages.

**Why avoid `session.receive().subscribe(...)`?** `session.send(...)` takes an output Publisher. Chaining `receive().map(...)` straight into `send(...)` lets the framework keep the connection alive while receiving/producing responses, manage cancellation/errors, and know when the handler `Mono` completes.

A WebSocket connection has two independent directions. For echo, outbound **depends on inbound**, making a single flow convenient. For chat rooms or server-pushed alerts, outbound may come from an independent event source; both inbound and outbound lifecycles and cleanup must be coordinated.

## 7. Complete Project: Spring Boot WebFlux WebSocket Echo

This project uses **Java 17+, Gradle, Spring Boot 3.3.13**, without `spring-boot-starter-web`. Boot starts the reactive server (typically Reactor Netty). The server exposes `ws://localhost:8080/ws/echo`, replies only to TEXT messages, logs connection lifecycle events, and enforces a simple Origin policy for local browsers.

### 7.1. File Layout

```text
webflux-websocket-demo/
├── build.gradle
└── src/
    ├── main/
    │   ├── java/com/example/websocket/WebSocketDemoApplication.java
    │   └── resources/application.properties
    └── test/
        └── java/com/example/websocket/WebSocketEchoIntegrationTest.java
```

**`build.gradle`:**

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

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

**`src/main/resources/application.properties`:**

```properties
server.port=8080
spring.application.name=webflux-websocket-demo
logging.level.com.example.websocket=INFO
```

### 7.2. Application, Mapping, Adapter, and Handler

**`src/main/java/com/example/websocket/WebSocketDemoApplication.java`:**

```java
package com.example.websocket;

import java.util.List;
import java.util.Map;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.stereotype.Component;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.reactive.CorsConfigurationSource;
import org.springframework.web.reactive.HandlerMapping;
import org.springframework.web.reactive.handler.SimpleUrlHandlerMapping;
import org.springframework.web.reactive.socket.WebSocketHandler;
import org.springframework.web.reactive.socket.WebSocketMessage;
import org.springframework.web.reactive.socket.WebSocketSession;
import org.springframework.web.reactive.socket.server.support.WebSocketHandlerAdapter;
import org.springframework.web.server.ServerWebExchange;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@SpringBootApplication
public class WebSocketDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(WebSocketDemoApplication.class, args);
    }
}

@Configuration(proxyBeanMethods = false)
class SocketMappingConfig {

    @Bean
    HandlerMapping webSocketMapping(EchoWebSocketHandler handler) {
        SimpleUrlHandlerMapping mapping = new SimpleUrlHandlerMapping();
        mapping.setUrlMap(Map.of("/ws/echo", handler));
        mapping.setOrder(-1); // Prioritize WebSocket mapping before controllers.
        return mapping;
    }

    @Bean
    WebSocketHandlerAdapter webSocketHandlerAdapter() {
        return new WebSocketHandlerAdapter();
    }
}

@Component
class EchoWebSocketHandler
        implements WebSocketHandler, CorsConfigurationSource {

    private static final Logger log =
            LoggerFactory.getLogger(EchoWebSocketHandler.class);

    @Override
    public Mono<Void> handle(WebSocketSession session) {
        String id = session.getId();
        log.info("WebSocket opened: {}", id);

        Flux<WebSocketMessage> outgoing = session.receive()
                .filter(message ->
                        message.getType() == WebSocketMessage.Type.TEXT)
                .map(message -> {
                    // Decode immediately; do not retain DataBuffer across async boundaries.
                    String text = message.getPayloadAsText();
                    if (text.length() > 2048) {
                        // Demo returns a simple app error; production must
                        // limit frame/message sizes before decoding.
                        return session.textMessage("error: too-long");
                    }
                    return session.textMessage("echo: " + text);
                })
                .doOnDiscard(WebSocketMessage.class,
                        WebSocketMessage::release);

        // Do not call subscribe() manually. The framework owns the lifecycle.
        return session.send(outgoing)
                .doFinally(signal ->
                        log.info("WebSocket {} finished: {}", id, signal));
    }

    @Override
    public CorsConfiguration getCorsConfiguration(
            ServerWebExchange exchange) {
        CorsConfiguration cors = new CorsConfiguration();
        // Allow only the browser page at the demo origin.
        cors.setAllowedOrigins(List.of("http://localhost:8080"));
        cors.setAllowedMethods(List.of("GET"));
        return cors;
    }
}
```

**Why is this code structurally valid?**

- The Java file has one top-level `public class`, `WebSocketDemoApplication`; `SocketMappingConfig` and `EchoWebSocketHandler` are valid package-private classes in the same package.
- `@Component` registers the handler so the config can inject and map it.
- `SimpleUrlHandlerMapping` binds `/ws/echo` to the bean with order `-1` so it takes precedence on matching URLs.
- `WebSocketHandlerAdapter` lets `DispatcherHandler` perform the handshake and invoke the handler.
- `handle(WebSocketSession)` returns `Mono<Void>` directly from `session.send(outgoing)`, chaining upstream `session.receive()`.
- `WebSocketMessage.Type.TEXT` prevents treating binary or control frames as JSON/text. `doOnDiscard` releases messages discarded by discard-aware Reactor operators.
- `getPayloadAsText()` runs synchronously before any downstream async work; no pooled inbound payload is retained past the operator.
- `CorsConfigurationSource` configures the Origin policy during the handshake. This is a **local lab** allowlist; production must enforce real public origins, HTTPS/WSS, and authentication. **Origin is not an authentication mechanism.**

**Limitation of `text.length()`:** it counts already-decoded UTF-16 code units and is solely an application-level check. It **does not cap memory consumed while receiving the WebSocket frame** and does not replace server/proxy frame-size, rate, or connection limits. Production must configure server-specific message/frame limits so giant payloads never reach the handler.

### 7.3. Starting the Server

Requires JDK 17+ and a Gradle version compatible with Boot 3.3:

```bash
gradle bootRun
```

If the project has the Gradle Wrapper: run `./gradlew bootRun` (Linux/macOS) or `.\gradlew.bat bootRun` (Windows PowerShell). When the default WebFlux server starts, logs show the HTTP server listening on port 8080.

Test from the browser console on the same origin `http://localhost:8080`:

```javascript
const socket = new WebSocket("ws://localhost:8080/ws/echo");

socket.onopen = () => {
  console.log("connected");
  socket.send("Hello WebFlux");
};

socket.onmessage = event => {
  console.log("received:", event.data);
  socket.close(1000, "demo done");
};

socket.onerror = event => {
  console.error("WebSocket error", event);
};

socket.onclose = event => {
  console.log("closed:", event.code);
};
```

**Expected output** in DevTools console when the handshake succeeds:

```text
connected
received: echo: Hello WebFlux
closed: 1000
```

Log lines/sequence and close codes may vary if the network or proxy closes unexpectedly. If DevTools is opened from `http://localhost:3000`, `Origin` is `http://localhost:3000`, which the demo's `http://localhost:8080`-only policy **rejects**; update the allowlist for legitimate origins. Never use `*` when cookies/sessions are involved or without understanding the threat model.

**Note:** typing `ws://localhost:8080/ws/echo` directly into the browser address bar does not initiate a WebSocket handshake; use the browser WebSocket API, a WebSocket client tool, or an integration test.

## 8. Integration Testing with ReactorNettyWebSocketClient

Testing controllers with `WebTestClient.get()` does not prove WebSocket handshakes or frames work. Use Spring Framework's `ReactorNettyWebSocketClient` to open a real WebSocket to the server running on a random port.

**`src/test/java/com/example/websocket/WebSocketEchoIntegrationTest.java`:**

```java
package com.example.websocket;

import java.net.URI;
import java.time.Duration;
import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.Test;

import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.web.reactive.socket.client.ReactorNettyWebSocketClient;

import reactor.core.publisher.Mono;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class WebSocketEchoIntegrationTest {

    @LocalServerPort
    int port;

    @Test
    void echoTextIsReceivedOverRealWebSocket() {
        AtomicReference<String> received = new AtomicReference<>();
        ReactorNettyWebSocketClient client =
                new ReactorNettyWebSocketClient();

        URI uri = URI.create(
                "ws://localhost:" + port + "/ws/echo");

        Mono<Void> exchange = client.execute(uri, session -> {
            Mono<Void> send = session.send(
                    Mono.just(session.textMessage("hello")));

            Mono<Void> receive = session.receive()
                    .next()
                    .doOnNext(message ->
                            received.set(message.getPayloadAsText()))
                    .then();

            // Keep both directions alive until send and receive finish.
            return Mono.when(send, receive);
        });

        // Block only on the JUnit thread, NEVER on a Netty event-loop thread.
        exchange.block(Duration.ofSeconds(10));

        assertEquals("echo: hello", received.get());
    }
}
```

Run:

```bash
gradle test
```

**Expected outcome:** the test passes when the environment and code are correct. This is **an expected contract outcome, not a report of a Gradle run executed here**. The test opens a real WebSocket connection rather than just issuing an HTTP GET; `@LocalServerPort` captures the actual bound server port.

`Mono.when(send, receive)` keeps both branches active in the client handler until sending finishes and one text response arrives. `receive().next()` takes one message and cancels the inbound subscription; when the handler completes, the WebSocket client closes the connection. That is a valid short lifecycle for a test. Use a timeout in JUnit so the test does not hang indefinitely if handshake, send, or receive fails.

Some adapters handle control frames internally, so the test asserts only the TEXT payload. To test blocked Origins, pass `Origin` in handshake headers from a configurable client; never conclude browser policy is secure just because a non-browser client succeeds.

## 9. How `Mono<Void>` Represents the Session Lifecycle

`handle(session)` returns a publisher **subscribed to by the framework**. That `Mono` must complete when session processing finishes, or signal an error if handling fails per policy. Thus:

**Correct pattern when outbound depends on inbound:**

```java
@Override
public Mono<Void> handle(WebSocketSession session) {
    return session.send(
            session.receive()
                    .map(msg ->
                            session.textMessage(
                                    "echo: " + msg.getPayloadAsText())));
}
```

This works for text-only echo to illustrate the concept; production must classify messages, validate, cap sizes, and manage buffer ownership as covered in sections 7 and 12.

**Anti-pattern to avoid:**

```java
@Override
public Mono<Void> handle(WebSocketSession session) {
    session.receive().subscribe(message -> {
        // Not wired into the publisher returned by handle().
    });
    return Mono.empty();
}
```

In the broken pattern, `Mono.empty()` signals immediate completion while a separate subscription continues running. The framework can close the session or lose proper error/cancellation handling. Never call `subscribe()` manually inside a business handler unless deliberately building a separate lifecycle and understanding the consequences.

**Pattern combining independent inbound and outbound streams:**

```java
// Code fragment inside handle(session):
Mono<Void> inbound = session.receive()
        .doOnNext(message -> {
            // Convert content into application data
            // and never retain pooled DataBuffers indefinitely.
        })
        .then();

Flux<String> notifications = someFiniteOrHotSource;
Mono<Void> outbound = session.send(
        notifications.map(session::textMessage));

return Mono.when(inbound, outbound);
```

This snippet is **not standalone/runnable** because `someFiniteOrHotSource` and publisher management must be defined. It illustrates two independent data flows. **Key point:** if `notifications` is a Flux that **never completes**, `Mono.when(inbound, outbound)` keeps waiting for outbound even after inbound completes, unless upstream sees cancellation/disconnect that halts sending. Design an explicit completion policy: stop when inbound closes, stop when outbound closes, or keep open until the app actively closes.

The Spring Framework reference shows examples using `input.and(output)` and combining the two streams; what matters is understanding exact Reactor operator semantics rather than guessing completion conditions from method names. With infinite/hot sources, you typically need an explicit stop signal and `takeUntilOther(...)`/lifecycle cleanup.

## 10. How Clients Send Multiple Messages and How the Server Processes Them

One WebSocket connection can carry many messages. `session.receive()` is a `Flux`; each `onNext` is an API-level message, not a new HTTP request. Example transforming text:

```java
Flux<WebSocketMessage> replies = session.receive()
        .filter(msg -> msg.getType() == WebSocketMessage.Type.TEXT)
        .map(msg -> msg.getPayloadAsText())
        .map(String::trim)
        .filter(s -> !s.isEmpty())
        .map(s -> session.textMessage("ACK:" + s));

return session.send(replies);
```

This is **a fragment inside `handle(session)`**, not a standalone class; any filtered/discarded buffers must be released via adapter/operator hooks as shown in this lesson. To process messages asynchronously (DB/API) while **preserving order**:

```java
Flux<WebSocketMessage> replies = session.receive()
        .filter(msg -> msg.getType() == WebSocketMessage.Type.TEXT)
        .map(WebSocketMessage::getPayloadAsText)
        .concatMap(text -> service.process(text))
        .map(session::textMessage);

return session.send(replies);
```

This is also an **illustrative fragment** requiring a non-blocking `service.process(String): Mono<String>` and an error policy. `concatMap` processes sequentially in order, which can reduce throughput if one message is slow. `flatMap` provides concurrency while requiring careful control over response order, concurrency limits, and buffering. If `service.process` runs blocking JDBC directly on the event loop, WebFlux does not magically make I/O non-blocking; use a reactive driver or offload blocking work per policy.

**Never let incoming messages dictate raw URLs, SQL, or function names without validation.** WebSocket frames are still untrusted input requiring schema validation and per-command authorization.

## 11. Message Types: TEXT, BINARY, PING, PONG

### 11.1. TEXT

`session.textMessage("hello")` creates a WebSocket TEXT message, and inbound text is decoded via `message.getPayloadAsText()` (UTF-8). JSON text can be sent, for example:

```json
{"type":"chat.send","room":"dev","text":"Hello"}
```

This is **an application payload**. The WebSocket protocol does not parse JSON, authorize room sends, or apply Bean Validation automatically like a `@RequestBody` controller. The application must define schemas, versions, maximum sizes, and validate every command.

### 11.2. BINARY

`session.binaryMessage` takes a function producing a `DataBuffer` from `DataBufferFactory`:

```java
// Code fragment inside handle(session), requires StandardCharsets import:
byte[] payload = "hello".getBytes(StandardCharsets.UTF_8);
WebSocketMessage binary = session.binaryMessage(factory ->
        factory.wrap(payload));
```

Create outgoing buffers/messages **inside a publisher that is actually being sent**, avoiding pre-allocating many messages that end up unsent if the connection cancels. When streaming large binary/file payloads, avoid loading entire contents into RAM and manage memory pressure.

### 11.3. PING and PONG

WebSocket PING/PONG are **control frames**, not custom JSON like `{"type":"ping"}`. Example creating a ping:

```java
// Code fragment inside handler; DataBufferFactory is provided by session:
WebSocketMessage ping = session.pingMessage(
        factory -> factory.wrap(new byte[] {1}));
```

Do not assume every adapter exposes incoming PING/PONG frames on `receive()` identically; many network stacks reply to pings automatically. **Never run two conflicting heartbeat policies** across proxy, transport, and application. When an application-level heartbeat is needed to detect dead clients, clearly define the interval, timeout, retry limit, and whether proxies enforce their own idle timeouts.

### 11.4. CLOSE

Close frames carry close codes/reasons per RFC 6455 (e.g., 1000 normal closure, 1008 policy violation, 1009 message too big). `session.close(CloseStatus)` returns a `Mono<Void>` that must be **returned or composed**, not merely called and discarded.

Fragment example:

```java
// When policy determines the session must close, return this Publisher:
return session.close(CloseStatus.POLICY_VIOLATION);
```

This is a branch inside `handle(session)`, requiring `org.springframework.web.reactive.socket.CloseStatus`. Do not assume an application-layer exception always maps to a specific close code: error-to-close-status mapping depends on implementation, timing, and whether the response already committed. On abrupt network loss, browsers often report close code 1006 (abnormal closure) locally rather than receiving a wire close frame from the server.

## 12. DataBuffer Lifecycle: Avoiding Pooled Memory Leaks

In WebFlux, inbound `WebSocketMessage.getPayload()` returns a `DataBuffer`. On Reactor Netty, buffers may be pooled and reference-counted. A common pitfall is retaining a buffer to read **after** the original consumer/operator has finished:

```text
receive() → WebSocketMessage holding a pooled DataBuffer
                  │
                  ├── Read text immediately inside map() → application String
                  │        └── Never retain raw buffer for async work
                  │
                  └── Push WebSocketMessage onto an async queue
                           ├── After adapter releases → use-after-release
                           └── If retained and never released → memory leak
```

**Common safe approach:** convert the message into immutable application data (a String or validated DTO) **immediately inside the synchronous operator** before calling an async service. Never store whole `WebSocketMessage` instances in an external queue.

When you genuinely must pass a raw buffer across an async boundary:

```java
// Pseudocode fragment for an async branch taking ownership of the message:
// Retain only if the adapter/contract requires keeping the message beyond
// the initial receive callback lifecycle.
message.retain();
return asyncUse(message.getPayload())
        .doFinally(signal -> message.release());
```

This snippet is **not standalone**: `message` and `asyncUse(DataBuffer)` must be supplied in the handler, and you must understand adapter ownership to avoid double-releasing. `retain()`/`release()` is reference-count management, not a "safe byte copy". Release on success, error, **and cancel**. If you allocate, queue, or filter out buffers yourself, call `DataBufferUtils.release(...)` / `WebSocketMessage.release()` according to ownership.

`doOnDiscard(WebSocketMessage.class, WebSocketMessage::release)` in the example cleans up messages dropped by discard-aware operators (such as `filter`), yet it is **not a catch-all for every leak path**. Likewise, unbounded `Flux.buffer`, unbounded `onBackpressureBuffer`, or retaining unconsumed messages causes memory pressure despite `doOnDiscard`.

Never blindly call `message.release()` once a codec or transport has taken ownership and will release it, as double-release also triggers errors. Follow API contracts and run leak detection tests on the real runtime.

## 13. Backpressure, Slow Consumers, and Outbound Queues

Reactor `Flux` supports backpressure, yet **the WebSocket protocol and TCP do not provide an unbounded, self-managing message queue**. When the producer outpaces the connection's send rate:

- Bandwidth-constrained connections accumulate outbound events.
- Reactor operator buffers grow RAM when left unbounded.
- A slow client holds resources longer, lowering total concurrent capacity.
- Sending an infinite publisher can keep `handle()` from ever completing without lifecycle shutdown logic.
- Retries/duplicate delivery are not handled as "exactly once" by low-level WebSocket.

Policies depend on the product:

| Need | Recommended Policy |
|---|---|
| Latest state only (e.g., cursor position) | Coalesce / keep latest only, accepting loss of intermediate updates |
| Chat messages that must be delivered | Persist source of truth in DB/message broker; add sequence/ack/replay on reconnect |
| High-speed market ticker | Rate limit, sample/drop/compact deliberately, document semantics clearly |
| Per-user notifications | Cap queues and connections per user, apply backpressure and timeouts |
| File/binary chunks | Bound bytes in flight, validate chunk sizes, apply application-layer flow control |
| Fan-out to thousands of clients | Message broker/pubsub + bounded per-session queues; measure memory and latency |

Using `Flux.interval(...)` to push a counter every second looks deceptively simple:

```java
Flux<WebSocketMessage> ticks = Flux.interval(Duration.ofSeconds(1))
        .map(i -> session.textMessage("tick:" + i));
return session.send(ticks);
```

This is an **illustrative fragment** inside `handle(session)`, needing `Duration` and `Flux` imports. Because this `Flux` is infinite, the producer stops only if the subscription cancels / connection closes or you add a termination condition. Never use this pattern in production without cleanup, idle timeouts, and backpressure policies.

When fanning out with `Sinks.Many`, you must also handle **failed `tryEmitNext` calls**. `FAIL_OVERFLOW`, `FAIL_ZERO_SUBSCRIBER`, or slow subscribers must not be ignored as if sends succeeded. Moreover, a sink is strictly in-process; across multiple instances behind a load balancer, you need pub/sub or a broker to broadcast across nodes.

## 14. Errors, Cancellation, and Connection Termination

Key Reactor signals:

| Signal | When | Action |
|---|---|---|
| `onComplete` | Inbound/outbound finishes per Publisher | Complete/close session per contract |
| `onError` | Parsing, business service, or transport send/receive fails | Log safely, record metrics, clean up; close if needed |
| `cancel` | Subscription canceled via peer disconnect, lifecycle timeout, or downstream operator | Release resources, stop tasks where possible |
| WebSocket CLOSE | Peer requests normal close or sends specific code | Respect close lifecycle; observe `closeStatus()` |
| TCP reset/idle timeout | Unclean connection drop | Clean up and guide client reconnect |

In the handler, you can observe termination:

```java
return session.send(outbound)
        .doOnError(ex ->
                log.warn("WS {} failed: {}",
                        session.getId(), ex.toString()))
        .doFinally(signal ->
                log.info("WS {} ended with {}",
                        session.getId(), signal));
```

This is a **code fragment inside a class with `log` and `outbound`**, not standalone runnable code. `doFinally` observes `ON_COMPLETE`, `ON_ERROR`, or `CANCEL` for the subscription at that operator's position—it **does not prove external DB/file writes were rolled back**. If you launch a task outside the reactive chain, WebSocket cancellation does not automatically stop that task.

**Do not treat every disconnect as a server error.** Closing a browser tab, switching networks, client reconnects, and proxy idle timeouts are normal operational events. Track close codes and error categories in aggregate rather than spamming stack traces whenever a client leaves.

**Do not try sending new messages after a session closes** based on an earlier `isOpen()` check; sends can still race and fail. Build a lifecycle-bound publisher and handle errors/cancellations cleanly.

## 15. Using Session Attributes and Handshake Metadata Properly

`WebSocketSession.getHandshakeInfo()` exposes metadata from the handshake: URI, HTTP headers, principal, subprotocol, and addresses per adapter. You can use it for request correlation logging or building session context.

However:
- `getHandshakeInfo().getHeaders()` may contain cookies or `Authorization`; never log them verbatim.
- Query params like `?token=...` appear in URIs and proxy logs; **putting long-lived bearer tokens in WebSocket URLs is discouraged**.
- Reverse proxies can make local/remote addresses reflect the proxy; inspect `Forwarded`/`X-Forwarded-For` only when sanitized at a trusted edge proxy.
- Session attributes hold **per-connection** state, not a global cache across users; never keep connection objects in a static map without cleanup.
- The handshake Principal is not blanket permission for every command. Authorize per user, room, tenant, action, and timestamp (tokens can expire or permissions be revoked after handshake).

When carrying selected attributes from HTTP `WebSession` to `WebSocketSession`, Spring Framework provides `HandshakeWebSocketService.setSessionAttributePredicate(...)` to whitelist valid attributes. Never copy entire HTTP session state if it holds secrets or unwieldy objects; copy only minimal required fields and review privacy implications.

To authenticate at handshake, configure WebFlux's `SecurityWebFilterChain` to protect the WebSocket path and validate cookies/sessions/tokens per your threat model. Never trust a client-sent `X-User-Id` header as verified identity. In a raw WebSocket handler, you must build application-level authorization for message commands yourself; `@MessageMapping`/STOMP security does not automatically apply to raw TEXT frames.

## 16. Origin Policy: WebSocket Is Not Standard CORS Preflight

When opening a WebSocket, browsers normally send `Origin`. The server must restrict origins to prevent **Cross-Site WebSocket Hijacking** (especially when authentication relies on cookies sent automatically by the browser). Spring WebFlux docs describe two options:
- The handler can implement `org.springframework.web.cors.reactive.CorsConfigurationSource` and return a `CorsConfiguration` restricting origins.
- Or configure CORS directly on `SimpleUrlHandlerMapping` by URL pattern.
- When both are present, Spring merges the configurations per contract.

The example in section 7 permits only `http://localhost:8080`. For a production frontend at `https://app.example.test`, allow that exact origin—never a local dev origin.

**Important distinctions:**
- Browser WebSocket handshakes **do not perform CORS preflight OPTIONS requests like fetch/XHR**. WebSocket Origin validation runs inside handshake/handler-mapping policy.
- Non-browser clients can send or spoof `Origin`, so Origin **is neither authentication** nor authorization.
- When using cookies, address `SameSite`/`Secure`/`HttpOnly`, CSRF/cross-site WebSocket hijacking, session fixation, and identity expiration.
- Behind a gateway reverse proxy, ensure origin/host headers pass accurately into the policy and cannot be bypassed via another public backend route.
- In multi-tenant apps, allowing one tenant's origin never removes the need for object-level authorization.

**Never fix Origin errors in production by opening everything to everyone.** Specify exact browser origins, schemes/ports, proxies, and auth policies.

## 17. Proxies, HTTPS/WSS, and Long-Lived Connection Configuration

When WebSocket traffic passes through NGINX or an ingress, the proxy must support HTTP upgrade. Illustrative NGINX snippet **inside a location block of an already configured server**:

```nginx
location /ws/ {
    proxy_pass http://127.0.0.1:8080;
    proxy_http_version 1.1;

    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";

    proxy_set_header Host $host;
    proxy_read_timeout 75s;
}
```

This **is not a standalone NGINX file or complete production configuration**. Production requires HTTPS certificates, virtual host allowlists, upstream network policies, concurrent connection caps, and trusted proxy forwarded headers. `proxy_read_timeout` tracks intervals **without reading bytes from upstream**, not an absolute connection TTL; align heartbeat/ping policies with proxy/network idle timeouts.

**Never use trust-all TLS** to make `wss://` work. Browsers require trusted certificates with matching host SANs; Java WebSocket clients likewise need proper TLS/SSL context configuration.

**When deploying multiple instances:**
- Each WebSocket connection stays pinned to one backend instance for the lifetime of that socket.
- When a pod dies, the connection drops; the browser/app must reconnect, re-authenticate, and restore state.
- To broadcast among users spread across nodes, use Redis Pub/Sub, Kafka, or a suitable broker; a static `Sinks.Many` in one JVM never crosses to another instance.
- Messages in flight on a broken socket are not automatically preserved or replayed after reconnect; if needed, design sequence IDs, ACKs, replay windows, and idempotency at the application layer.
- Autoscalers and connection draining must avoid brutally severing thousands of sessions simultaneously; implement graceful shutdown, rate limiting, and retry jitter.

## 18. Distinguishing Raw WebSocketHandler, STOMP, and RSocket

**WebFlux Raw WebSocketHandler**:
- Works directly with RFC 6455 TEXT/BINARY/PING/PONG frames.
- App defines JSON schemas, command names, message IDs, ACKs, authorization, and retries.
- Fits when you need a minimal, tightly controlled protocol or integration with a specialized application protocol.

**STOMP over WebSocket**:
- Provides destinations, broker relay/simple broker, subscribe/send—commonly used in messaging apps.
- Spring messaging APIs like `@MessageMapping` belong to another abstraction; do not stick controller annotations directly onto a raw `WebSocketHandler` expecting routing to work.
- Can be deployed in Spring Servlet/message-broker architectures depending on library/stack.

**RSocket**:
- A distinct protocol supporting request-response, fire-and-forget, request-stream, and channel interactions with its own semantics.
- Can run over WebSocket or TCP transport; a `WebSocketHandler` is not an RSocket endpoint.
- If your problem requires a broker or rich application-level backpressure/stream semantics, pick an appropriate messaging stack rather than inventing a hard-to-maintain custom protocol.

**SSE** can be simpler if you only need server→client notifications and the browser does not send messages over the same connection. Choose WebSocket based on genuine full-duplex needs and interaction frequency, not just the buzzword "real-time".

## 19. Testing More Scenarios Than Just Happy-Path Echo

A valuable integration suite should verify:

| Scenario | Expectation to Verify |
|---|---|
| One TEXT message `hello` | Receives exact `echo: hello` |
| Multiple TEXT messages | All received in order when handler uses a sequential pipeline |
| Binary message sent to text-only handler | Not decoded as JSON/TEXT; clear reject/ignore policy |
| Payload larger than limit | Handled/rejected/closed per policy without OOMing server |
| Invalid browser Origin | Handshake rejected per allowlist |
| Missing or invalid auth on handshake | Never upgraded to an authenticated session |
| User lacks room permission | Command rejected even though socket is open |
| Client sends normal CLOSE | Server cleans up resources and records close event appropriately |
| Abrupt client disconnect | No lingering tasks, background buffer leaks, or dangling sessions |
| Slow reader + bursty events | Outbound queue / bytes in flight stay bounded |
| 1,000+ clients (within system capacity) | FDs/memory/CPU/pools/latency remain within bounds |
| Through real NGINX/ingress | Upgrade headers, timeouts, TLS/WSS, and Origin behave properly |
| Pod deploy/restart | Reconnect, re-auth, and replay behave as specified |

`WebTestClient` works well for testing WebFlux HTTP routes, yet **does not replace** a real WebSocket client for testing handshakes and frames. `ReactorNettyWebSocketClient` or compatible WebSocket test clients fill that role. For timeout assertions, never demand millisecond-exact timer precision in CI.

When testing binary payloads and buffers, enable Netty leak detection at an appropriate level in test/staging and measure direct memory. Resource leaks rarely show up in a single echo test.

## 20. Troubleshooting Common Issues

| Symptom | Possible Cause | How to Check and Fix |
|---|---|---|
| `GET /ws/echo` returns HTTP error | Missing WebSocket Upgrade handshake | Use a WebSocket client, not a plain HTTP URL visit |
| HTTP 404 on connect | Wrong mapped path or bean not registered | Check `SimpleUrlHandlerMapping`, URL, and path rewrites |
| Handler never invoked | Missing `WebSocketHandlerAdapter` in custom config or mapping conflict | Check handler mapping and adapter ordering |
| Compile error on `handleTextMessage` or `sendMessage` | Imported Servlet WebSocket API instead of WebFlux | Use `org.springframework.web.reactive.socket.*` |
| App boots as MVC/Tomcat instead | `spring-boot-starter-web` present alongside WebFlux | Exclude MVC starter to run the reactive server |
| Connection opens then closes immediately | `handle()` returned `Mono.empty()` or send source completed early | Return/compose a Publisher covering the session lifetime |
| Server receives yet sends no reply | Outgoing Publisher never passed to `session.send` | Chain `session.receive()` into `send(...)`, do not call `subscribe()` |
| Test times out | Client didn't subscribe, wrong mapping, origin blocked, or no response | Test with `ReactorNettyWebSocketClient`, inspect handshake logs |
| Client console shows code 1006 | Unclean disconnect, proxy timeout/TCP reset | Check proxy/TLS logs, close policy, and network |
| `WebSocketMessage.getPayloadAsText` fails | Message is not TEXT or `DataBuffer` already released | Filter by type, decode before async boundaries, manage retain/release |
| Direct memory grows | Pooled `DataBuffer` retained and never released | Audit retention, discarded-buffer cleanup, Netty leak detector |
| Slow client increases RAM | Unbounded outbound queue, overly fast broadcast | Apply quotas, backpressure/drop/replay policies |
| Browser rejected on Origin | Page origin outside allowlist | Set exact public origin, never open wildcard unconditionally |
| Fails to connect behind reverse proxy | Missing Upgrade/Connection headers or idle timeout | Verify NGINX/ingress WS support, WSS, and TLS |
| Sent JSON yet handler doesn't parse DTO | Raw WebSocket has no automatic `@RequestBody` | Decode/validate JSON explicitly and handle errors |
| Client receives duplicates on reconnect | No message ID/idempotency/replay contract | Design ACK/sequence/dedup at the application layer |
| Messages reach only same-pod clients | Fan-out uses in-memory Sink without broker | Add pub/sub/broker to scale across instances |
| User's permissions revoked yet socket stays open | Authenticated only at handshake with no recheck | Design re-auth/expiry/per-command authz or close session |

## 21. Safe Deployment Checklist

- [ ] Use WebFlux `WebSocketHandler`/`WebSocketSession` and only `spring-boot-starter-webflux` for a reactive server.
- [ ] Map `/ws/...` with `SimpleUrlHandlerMapping` and the corresponding adapter.
- [ ] `handle()` returns a **Publisher spanning the full lifetime**, never fire-and-forget `subscribe()`.
- [ ] Use `receive()` for input, `send(Publisher)` for output, and classify TEXT/BINARY/control frames.
- [ ] Validate schemas, versions, and authorization for every application command.
- [ ] Never retain raw `DataBuffer` across async boundaries without proper `retain`; release strictly per ownership.
- [ ] Enforce message/frame size limits, rate limits, and connection caps per tenant/user.
- [ ] Control outbound queues, slow consumers, and hot/infinite producers.
- [ ] Handle close/error/cancel and clean up resources on every path, including server shutdown.
- [ ] Enforce Origin allowlists at handshake; keep authentication and authorization as separate layers.
- [ ] Use WSS/TLS, protect cookies/tokens, and never log credentials in URLs or logs.
- [ ] Configure proxy WS upgrades, idle timeouts, host allowlists, and trusted forwarded headers.
- [ ] Implement reconnect, backoff/jitter, and replay/dedup if required by business semantics.
- [ ] Monitor active sessions, handshake rejections, close codes, message sizes, errors, and memory.
- [ ] Test with a real WebSocket client covering both success and failure scenarios.
- [ ] Run patched, supported framework/runtime versions and review changes across major upgrades.

## 22. Self-Check Questions

**Question 1: Why does `WebSocketHandler.handle` return `Mono<Void>`?**  
To represent the asynchronous session lifecycle; the framework manages subscribe/complete/error/cancel and closes the session once handling finishes per contract.

**Question 2: How does `WebSocketSession` differ from `WebSession`?**  
`WebSocketSession` represents the full-duplex connection; `WebSession` stores reactive HTTP session state that may span multiple HTTP requests or be consulted during the handshake per policy.

**Question 3: Why shouldn't you call `session.send(...).subscribe()` and return `Mono.empty()`?**  
Because sending becomes detached from the framework-managed lifecycle; the handler can complete and close the socket before sending finishes, breaking cancellation and error propagation.

**Question 4: After a successful handshake, does each WebSocket TEXT message create a new HTTP request?**  
No. Frames/messages travel over the same WebSocket connection, with no per-message HTTP response status.

**Question 5: Is `getPayloadAsText()` appropriate for BINARY messages?**  
Never unconditionally; classify message types and decode binary payloads according to an agreed format contract.

**Question 6: With pooled buffers, when is retain/release needed?**  
When keeping data past the current callback/operator or taking buffer ownership, retain per contract and release exactly once on every termination path. For text, usually decode straight into a String so no raw buffer is retained.

**Question 7: If a browser sends a valid Origin, is the user authenticated?**  
No. An Origin allowlist mitigates cross-site hijacking, yet never replaces login/session/token authentication and per-command authorization.

**Question 8: Does WebFlux automatically broadcast WebSocket messages across multiple pods?**  
No. In-memory sinks/state live inside each JVM; cross-node broadcasts require a broker/pubsub along with reconnect/consistency handling.

**Question 9: Why doesn't enabling HTTP/2 prove WebSocket runs over HTTP/2?**  
HTTP/2 WebSocket handshakes use a separate mechanism and depend on adapter/proxy support. This example relies on HTTP/1.1 Upgrade.

**Question 10: If outbound is an infinite Flux and inbound closes, how does the Mono finish?**  
It depends on composition, cancellation/close signals, and operators. Do not assume `Mono.when(...)` with an infinite source completes by itself; design explicit lifecycle signals and cleanup.

## 23. Official References

1. Spring Framework — **WebFlux WebSockets**, `WebSocketHandler`, mapping, send/receive, handshake, CORS, client: https://docs.spring.io/spring-framework/reference/web/webflux-websocket.html
2. Spring Framework 6.1 — **WebSocketHandler** JavaDoc: https://docs.spring.io/spring-framework/docs/6.1.3/javadoc-api/org/springframework/web/reactive/socket/WebSocketHandler.html
3. Spring Framework 6.1 — **WebSocketSession** JavaDoc: https://docs.spring.io/spring-framework/docs/6.1.3/javadoc-api/org/springframework/web/reactive/socket/WebSocketSession.html
4. Spring Framework 6.1 — **WebSocketMessage** JavaDoc, pooled buffer `retain/release`: https://docs.spring.io/spring-framework/docs/6.1.3/javadoc-api/org/springframework/web/reactive/socket/WebSocketMessage.html
5. Spring Framework 6.1 — **WebSocketHandlerAdapter**: https://docs.spring.io/spring-framework/docs/6.1.3/javadoc-api/org/springframework/web/reactive/socket/server/support/WebSocketHandlerAdapter.html
6. Spring Framework — **Data Buffers and Codecs**: https://docs.spring.io/spring-framework/reference/core/databuffer-codec.html
7. Spring Framework — **WebFlux Security** and security filter chain: https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html
8. IETF RFC 6455 — **The WebSocket Protocol**: https://www.rfc-editor.org/rfc/rfc6455
9. IETF RFC 8441 — **Bootstrapping WebSockets with HTTP/2**, only when supported by deployment: https://www.rfc-editor.org/rfc/rfc8441

**Conclusion:** In WebFlux, `WebSocketHandler.handle(WebSocketSession)` is the entry point for a **long-lived connection**, `receive()` is the inbound `Flux`, and `send(Publisher)` is the outbound `Mono<Void>`. Return and compose publishers so the framework owns the session lifecycle, classify and validate messages, bound queues and sizes, release buffers on cancel/error, enforce Origin alongside authentication, and test with a real WebSocket client before rolling out proxies, WSS, and scale-out.
