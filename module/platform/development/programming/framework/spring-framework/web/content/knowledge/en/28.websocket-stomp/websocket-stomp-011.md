# Exception Handling, Connection Events, Monitoring, and Testing WebSocket in Spring

## 1. Objectives and Scope

A WebSocket endpoint must do more than just receive and send messages. To operate reliably, an application must identify **which stage an error occurred in**, know **when a connection/STOMP session actually exists**, **clean up state when connections close**, expose observable metrics, and have tests covering the full transport path.

In Spring Framework 6.x with Java 17+, this lesson distinguishes two models:

1. **Raw WebSocket on the Servlet stack**: `WebSocketHandler`, `TextWebSocketHandler`, `WebSocketSession`, and callbacks such as `handleTransportError` and `afterConnectionClosed`.
2. **STOMP over WebSocket**: `@EnableWebSocketMessageBroker`, `@MessageMapping`, `@MessageExceptionHandler`, events `SessionConnectEvent`, `SessionConnectedEvent`, `SessionDisconnectEvent`, and `BrokerAvailabilityEvent`, along with `WebSocketMessageBrokerStats` and STOMP testing.

By the end of this lesson, you will be able to distinguish handshake errors, transport errors, message-handling errors, and broker errors; write lifecycle-aware handlers and event listeners; measure active connections, errors, and traffic; test raw WebSocket against a real WebSocket client; and design a STOMP testing strategy with explicit timeouts.

The main examples use **Spring Boot 3.3.x + Java 17** on the **Servlet / Spring MVC stack**. Reactive WebFlux WebSocket APIs live in a different package with different callbacks; do not copy Servlet `WebSocketHandler` examples directly into WebFlux.

## 2. Four Error Categories Commonly Confused

A connection can fail before or after protocol upgrade. Choosing the right handling layer matters more than wrapping everything in one broad `try/catch`.

| Stage | Examples | Where handled/observed | Signal to client |
| --- | --- | --- | --- |
| HTTP handshake, pre-upgrade | Wrong URL, missing auth, blocked origin | Servlet filters, Spring Security, `HandshakeInterceptor`, `HandshakeHandler` | HTTP 400/401/403/404 or handshake failure |
| WebSocket transport, post-upgrade | Socket drop, read/write error, client closes tab | `handleTransportError`, `afterConnectionClosed` | Close frame if still writable, or connection drop |
| Raw message / business logic | Invalid command, oversized payload, service failure | `handleTextMessage`, validation, service logic | App-defined error message or close code |
| STOMP message / broker | Invalid payload, forbidden destination, broker disconnect | `@MessageExceptionHandler`, `ChannelInterceptor`, broker events/error handler | STOMP message to user, STOMP `ERROR` frame, or disconnect depending on error |

**Key milestone:** HTTP status codes are returned **before upgrading**. After HTTP `101 Switching Protocols`, there is no individual HTTP response per WebSocket frame. Therefore, do not "return HTTP 400" from `handleTextMessage` or `@MessageMapping`. If a business error is recoverable, standardize an application-level error message; if a protocol/policy violation is severe, close the session with the appropriate close semantics.

### 2.1. WebSocket close codes

| Code | Practical meaning |
| --- | --- |
| 1000 | Normal closure |
| 1001 | Peer going away / shutdown |
| 1002 | Protocol error |
| 1003 | Unsupported data type |
| 1008 | Policy violation |
| 1009 | Message too big |
| 1011 | Unexpected server error |

Code **1006 represents abnormal closure observed locally** and is never sent inside a WebSocket close frame. Likewise, reserved codes must not be repurposed as custom application codes. A transport error may prevent sending any close frame, so the client only observes a dropped connection rather than receiving 1011.

## 3. Raw WebSocket: Error Handling and Lifecycle Callbacks

Spring Servlet defines `org.springframework.web.socket.WebSocketHandler`:

```java
void afterConnectionEstablished(WebSocketSession session) throws Exception;
void handleMessage(WebSocketSession session, WebSocketMessage<?> message)
        throws Exception;
void handleTransportError(WebSocketSession session, Throwable exception)
        throws Exception;
void afterConnectionClosed(WebSocketSession session, CloseStatus status)
        throws Exception;
boolean supportsPartialMessages();
```

These are **explanatory API signatures**, not a runnable Java class. When handling text, extend `org.springframework.web.socket.handler.TextWebSocketHandler` and override `handleTextMessage(...)`. The base class provides default lifecycle callbacks.

### 3.1. Callbacks to understand accurately

- `afterConnectionEstablished`: invoked by Spring when the handshake succeeds and the session is ready. Use it to register the session, increment active connection gauges, and send a greeting if needed.
- `handleTextMessage`: processes a text payload for **one specific session**. Validate input, call services, and reply according to schema. Do not let expected exceptions (like bad input) bubble up as unhandled server errors.
- `handleTransportError`: receives transport-layer errors; you can log the error class, increment counters, and attempt to close the session if still open. It **is not** a universal catch-all guaranteed to catch every business exception or every network failure.
- `afterConnectionClosed`: removes the session from registries and frees associated resources. Do not attempt to send new messages here.
- `supportsPartialMessages`: indicates whether the handler accepts partial WebSocket message fragments; this is not synonymous with STOMP message fragmentation.

Multi-client applications can share **a single singleton handler bean**. Never store `private WebSocketSession currentUserSession;` on a singleton to represent all clients. Close/error callbacks may arrive in overlapping scenarios; cleanup operations must be **idempotent**, for example using `Set.remove(sessionId)` and decrementing counters only if the element actually existed.

### 3.2. Expected vs. unexpected errors

Example pattern inside a subclass:

```java
@Override
protected void handleTextMessage(WebSocketSession session,
                                 TextMessage message) throws Exception {
    String text = message.getPayload();

    if (text.length() > 1024) {
        session.close(CloseStatus.TOO_BIG_TO_PROCESS);
        return;
    }

    if (!"PING".equals(text)) {
        session.sendMessage(new TextMessage("ERROR:BAD_COMMAND"));
        return;
    }

    session.sendMessage(new TextMessage("PONG"));
}
```

Here `ERROR:BAD_COMMAND` is an **application convention**, not a standard WebSocket ERROR frame. Oversized payloads follow another policy, closing with 1009. If the backend speaks JSON, design a stable error schema (such as `{"type":"error","code":"INVALID_COMMAND"}`) and never send stack traces to clients.

If an unhandled exception escapes the handler, Spring wraps it with infrastructure such as `ExceptionWebSocketHandlerDecorator` to close the session on failure. Do not rely on default exception-closing behavior to communicate business errors to clients; define controlled error responses and capture server-side logs/metrics explicitly.

### 3.3. Never send concurrently from multiple threads arbitrarily

With Servlet WebSocket built on Jakarta WebSocket, sending on a single session generally requires serialization; multiple producers calling `session.sendMessage(...)` concurrently can collide. `ConcurrentWebSocketSessionDecorator` provides send-time and buffer bounds:

```java
WebSocketSession safe =
        new ConcurrentWebSocketSessionDecorator(
                session, 10_000, 64 * 1024);
```

Snippet note: import `org.springframework.web.socket.handler.ConcurrentWebSocketSessionDecorator`. In a broadcast system, create and store **one consistent wrapper per session** and send through that wrapper. Do not wrap a fresh decorator per message, as that fails to share synchronization across producers.

## 4. STOMP: @MessageMapping Errors and Protocol Errors Are Different

STOMP is a messaging protocol layered on WebSocket. Typical routing is:

```text
Client WebSocket handshake /stomp (HTTP 101)
  -> STOMP CONNECT -> CONNECTED
  -> STOMP SUBSCRIBE /topic/...
  -> STOMP SEND /app/...
  -> clientInboundChannel
  -> @MessageMapping controller
  -> /topic/... or /user/queue/...
  -> brokerChannel -> clientOutboundChannel
  -> STOMP MESSAGE to subscribers
```

### 4.1. @MessageExceptionHandler

When a `@MessageMapping` method throws a business exception, Spring Messaging supports `@MessageExceptionHandler`—analogous to `@ExceptionHandler` on HTTP controllers, but operating in **message handling** rather than producing HTTP responses:

```java
@Controller
class PingController {
    record PingRequest(String text) {}
    record ErrorReply(String code) {}

    @MessageMapping("/ping")
    @SendTo("/topic/pongs")
    String ping(PingRequest body) {
        if (body == null || body.text() == null ||
                body.text().isBlank()) {
            throw new IllegalArgumentException("text required");
        }
        return "PONG:" + body.text();
    }

    @MessageExceptionHandler(IllegalArgumentException.class)
    @SendToUser(value = "/queue/errors", broadcast = false)
    ErrorReply badInput(IllegalArgumentException exception) {
        return new ErrorReply("INVALID_TEXT");
    }
}
```

This snippet belongs **inside a controller with the appropriate imports**. The client SENDs to `/app/ping`. Subscribers to `/topic/pongs` receive valid replies. On invalid input, the originating client subscribes to `/user/queue/errors` to receive the error code. `broadcast=false` prevents broadcasting the error to other sessions of a multi-session user; for anonymous sessions, it likewise targets the originating session.

`@MessageExceptionHandler` can be declared inside the same controller or in a `@ControllerAdvice` class for broader scope. Never send raw exception messages or stack traces to browsers, as they can expose service internals or sensitive data. Handling an exception does not automatically require closing the WebSocket.

### 4.2. STOMP ERROR frames and StompSubProtocolErrorHandler

STOMP frame parsing errors, protocol violations, channel-layer failures, or infrastructure errors can take a separate **STOMP ERROR** path without passing through a controller's `@MessageExceptionHandler`. Spring provides `StompSubProtocolErrorHandler` to customize subprotocol-level error responses. It can be registered via `StompEndpointRegistry.setErrorHandler(...)` in the broker config using an implementation designed not to leak internal details.

A STOMP `ERROR` frame may cause the connection to close. Clients should distinguish:

- **Business error message** on `/user/queue/errors`: the app can keep the connection open and handle subsequent requests.
- **STOMP ERROR frame**: a subprotocol/broker error, possibly accompanied by disconnect; check connection state and reconnect policy.
- **WebSocket transport close/error**: may occur with no STOMP ERROR frame at all.

### 4.3. BrokerAvailabilityEvent and proactive publishing

When using a broker relay (an external broker), `BrokerAvailabilityEvent` signals whether the broker is available or unavailable for sending messages. The built-in simple broker is normally available right after startup; a broker relay can lose and regain connectivity.

Components calling `SimpMessagingTemplate.convertAndSend(...)` can track availability state where appropriate, yet must still handle `MessageDeliveryException`/send failures: an availability event is a point-in-time observation and does not guarantee subsequent sends will succeed.

## 5. STOMP Connection Events: When Is a Client Considered Online?

Spring's ApplicationContext publishes the following events when using STOMP over WebSocket:

| Event | Timing | Notes |
| --- | --- | --- |
| `SessionConnectEvent` | Server receives STOMP `CONNECT` | This is **not yet** confirmation that the STOMP session completed |
| `SessionConnectedEvent` | Broker replies with STOMP `CONNECTED` | Can count the STOMP session as connected |
| `SessionSubscribeEvent` | Client sends `SUBSCRIBE` | Does not imply every subscription step has been confirmed |
| `SessionUnsubscribeEvent` | Client sends `UNSUBSCRIBE` | Use to update subscription tracking if needed |
| `SessionDisconnectEvent` | STOMP session ends | May fire **more than once** for the same session; must be idempotent |
| `BrokerAvailabilityEvent` | Broker transitions available/unavailable | Useful with a broker relay or proactive publishing |

**Two connection layers:** a successful WebSocket HTTP handshake only means the WebSocket connection is open. The client must still send STOMP `CONNECT` and receive `CONNECTED` before a STOMP session is ready. When the broker has issues, an open socket may exist while STOMP messaging is unusable.

### 5.1. Listening with @EventListener

```java
@Component
class StompSessions {
    private final Set<String> online = ConcurrentHashMap.newKeySet();

    @EventListener
    public void connected(SessionConnectedEvent event) {
        String id = SimpMessageHeaderAccessor
                .wrap(event.getMessage())
                .getSessionId();
        if (id != null) {
            online.add(id);
        }
    }

    @EventListener
    public void disconnected(SessionDisconnectEvent event) {
        online.remove(event.getSessionId());
    }
}
```

This is a **snippet** requiring imports from `java.util.Set`, `java.util.concurrent.ConcurrentHashMap`, `org.springframework.context.event.EventListener`, `org.springframework.stereotype.Component`, `org.springframework.messaging.simp.SimpMessageHeaderAccessor`, `org.springframework.web.socket.messaging.SessionConnectedEvent`, and `SessionDisconnectEvent`.

Maintaining a set of session IDs allows handling duplicate disconnects safely. To maintain a `disconnect_total` counter of "sessions that went online and then closed", increment only when `online.remove(id)` returns `true`. Sessions that fail before STOMP CONNECTED were never added to the set; measure handshake/connect failures separately.

**Never infer access permissions from connection events:** an active session does not mean the user is allowed to read every destination. Spring Security, interceptors, and business checks must be enforced separately.

### 5.2. Guarantees and multi-instance deployments

An in-RAM `online` list only reflects sessions on the **current running instance**. In multi-node deployments, global connection counts and presence require distributed state or metric aggregation across instances. `SessionDisconnectEvent` can fire multiple times; event listeners are also not an absolute source of truth for live presence if a network drop has not been detected by timeouts yet.

Spring's simple broker is great for getting started, but lacks external broker features and is not suited for multi-node relay clustering. For cross-node routing, use a full broker relay with clear reconnection and authorization designs.

## 6. Monitoring WebSocket: What to Measure and at Which Layer?

No single metric proves a WebSocket service is healthy. Track at least:

| Signal | What it answers | How to interpret |
| --- | --- | --- |
| Open raw WebSocket sessions | How many transport connections exist now? | Gauge incremented/decremented across lifecycle |
| Connected STOMP sessions | How many STOMP sessions reached CONNECTED? | Can differ from open socket count |
| Abnormal closes/connects over time | Are networks/proxies/brokers unstable? | Counters/rates broken down by close status |
| Transport vs. application errors | Infrastructure fault or bad data? | Separate transport, validation, and server errors |
| Inbound/outbound messages | Messages per second and by type | Counters; never put payloads into metric labels |
| Message size, send buffer, and send time | Slow clients or overload? | Inspect distributions against configured limits |
| STOMP CONNECT/CONNECTED/DISCONNECT and subscriptions | How are clients behaving at the STOMP layer? | DISCONNECT count may be lower due to hard drops |
| Broker relay availability and pending tasks | Is the broker or executor backed up? | Observe alongside queue/executor stats |

### 6.1. WebSocketMessageBrokerStats for STOMP

When `@EnableWebSocketMessageBroker` is active, Spring registers a `org.springframework.web.socket.config.WebSocketMessageBrokerStats` bean. By default, it aggregates and **logs statistics at INFO level roughly every 30 minutes**: client WebSocket/SockJS sessions, STOMP frames, broker relay stats if configured, inbound/outbound executors, and connection limits/errors.

These stats cover **STOMP message broker infrastructure** and do not automatically replace custom metrics on a raw `WebSocketHandler`. You can inspect it like this:

```java
@Component
class BrokerStatsReader {
    private final WebSocketMessageBrokerStats stats;

    BrokerStatsReader(WebSocketMessageBrokerStats stats) {
        this.stats = stats;
    }

    void inspect() {
        String summary = stats.toString();
        // Forward summary to internal logs or an appropriate monitoring system.
    }
}
```

This snippet shows how to inject the bean; `inspect()` is not invoked automatically without a scheduler or caller. In Spring 6.2, structured getters replace deprecated string-based stats APIs; check the Javadoc for your exact version when building automated dashboards. `BrokerStats` is not cluster-aware: across multiple application instances, each instance reports its own local metrics.

### 6.2. Spring Boot Actuator and Micrometer

Adding `spring-boot-starter-actuator` lets you register counters and gauges for application logic and inspect them via the metrics endpoint or configured collectors. Example metric design:

```text
demo.ws.raw.active              gauge  - currently open raw sessions
demo.ws.raw.messages            counter - received text messages
demo.ws.raw.transport.errors    counter - observed transport errors
demo.ws.stomp.active            gauge  - STOMP CONNECTED not yet disconnected
demo.ws.stomp.connected         counter - CONNECTED session count
demo.ws.stomp.disconnected      counter - closed CONNECTED session count
demo.ws.stomp.subscriptions     counter - received SUBSCRIBE frames
```

**Cardinality rule:** never put `sessionId`, `userId`, unbounded room IDs, tokens, message text, or dynamic paths into metric tags. Unbounded values explode time-series counts, consume memory, and risk leaking data. Use bounded tags such as `protocol=raw|stomp`, `result=success|error`, `reason=normal|transport|timeout`.

**Distinction:** counter metrics keep increasing across user reconnects, whereas gauges reflect point-in-time state. When an application restarts, instance counters reset to 0, so dashboards must apply proper rate/aggregation functions.

### 6.3. Structured logging and correlation

Useful logs typically include **timestamp, event type, internal session correlation ID, close code category, exception class, processing duration, and broker status**. Never log cookies, STOMP authorization headers, personal data, or full private chat contents.

Different threads may process messages belonging to the same WebSocket session. Never assume `ThreadLocal` or HTTP handshake MDC automatically propagates across every callback or executor. When correlation is required, pass context explicitly via message headers/attributes or use an interceptor that clears MDC cleanly to avoid leaking into unrelated tasks.

## 7. Runnable Example: Raw + STOMP + Events + Micrometer Metrics

This demo exposes two endpoints in one Servlet application:

- `ws://localhost:8080/ws/raw`: raw text WebSocket; replies `PONG` to `PING` and `ERROR:BAD_COMMAND` to anything else.
- `ws://localhost:8080/stomp`: STOMP endpoint. Clients subscribe to `/topic/pongs`, send JSON `{"text":"hello"}` to `/app/ping`, and receive a JSON reply. When text is missing, `@MessageExceptionHandler` sends an error to `/user/queue/errors`.

Everything uses Java 17 and Spring Boot 3.3.x. The demo is **open locally for learning** without authentication/authorization, so never expose it directly to the public Internet.

### 7.1. Structure

```text
websocket-observation-demo/
├── build.gradle
└── src/
    ├── main/
    │   ├── java/demo/ws/
    │   │   ├── DemoApplication.java
    │   │   ├── RawHandler.java
    │   │   ├── RawConfig.java
    │   │   ├── StompConfig.java
    │   │   ├── PingController.java
    │   │   └── StompMonitor.java
    │   └── resources/
    │       ├── application.properties
    │       └── static/index.html
    └── test/
        └── java/demo/ws/RawWebSocketIntegrationTest.java
```

### 7.2. build.gradle

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.6'
    id 'io.spring.dependency-management' version '1.1.6'
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
    implementation 'org.springframework.boot:spring-boot-starter-websocket'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`spring-boot-starter-websocket` provides Spring MVC WebSocket/STOMP and the embedded Servlet container. `spring-boot-starter-actuator` provides Micrometer and metrics endpoints; `spring-boot-starter-test` provides JUnit 5 and Spring Boot test utilities. Spring Boot manages all dependency versions to prevent mixing Spring 5/6 or `javax.websocket` with `jakarta.websocket`.

### 7.3. DemoApplication.java

```java
package demo.ws;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

All other classes reside in package `demo.ws` so component scanning picks them up.

### 7.4. RawHandler.java: separating business errors from transport errors

```java
package demo.ws;

import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.stereotype.Component;
import org.springframework.web.socket.CloseStatus;
import org.springframework.web.socket.TextMessage;
import org.springframework.web.socket.WebSocketSession;
import org.springframework.web.socket.handler.TextWebSocketHandler;

@Component
public class RawHandler extends TextWebSocketHandler {
    private final Set<String> live = ConcurrentHashMap.newKeySet();
    private final Counter messages;
    private final Counter transportErrors;

    public RawHandler(MeterRegistry metrics) {
        Gauge.builder("demo.ws.raw.active", live, Set::size)
                .register(metrics);
        this.messages = Counter.builder("demo.ws.raw.messages")
                .register(metrics);
        this.transportErrors =
                Counter.builder("demo.ws.raw.transport.errors")
                        .register(metrics);
    }

    @Override
    public void afterConnectionEstablished(WebSocketSession session) {
        live.add(session.getId());
    }

    @Override
    protected void handleTextMessage(WebSocketSession session,
                                     TextMessage message) throws Exception {
        messages.increment();
        String text = message.getPayload();

        if (text.length() > 1024) {
            session.close(CloseStatus.TOO_BIG_TO_PROCESS);
            return;
        }

        if (!"PING".equals(text)) {
            session.sendMessage(new TextMessage("ERROR:BAD_COMMAND"));
            return;
        }

        session.sendMessage(new TextMessage("PONG"));
    }

    @Override
    public void handleTransportError(WebSocketSession session,
                                     Throwable cause) throws Exception {
        transportErrors.increment();
        if (session.isOpen()) {
            session.close(CloseStatus.SERVER_ERROR);
        }
    }

    @Override
    public void afterConnectionClosed(WebSocketSession session,
                                      CloseStatus status) {
        live.remove(session.getId());
    }
}
```

The handler does not store a single user's session in a shared field; `live` is a set of open session IDs. `remove` is idempotent if a close callback arrives after an error. This raw demo only sends from inside the callback; when turning it into a multithreaded broadcast system, add concurrent send protection and buffer bounds.

The `text.length() > 1024` check uses UTF-16 code units for illustration. Real systems need container-level limits on **bytes, frames, and buffers**, payload size validation before processing, and resource caps as needed. The server may reject oversized messages before this callback is ever invoked.

### 7.5. RawConfig.java: registering raw WebSocket

```java
package demo.ws;

import org.springframework.context.annotation.Configuration;
import org.springframework.web.socket.config.annotation.EnableWebSocket;
import org.springframework.web.socket.config.annotation.WebSocketConfigurer;
import org.springframework.web.socket.config.annotation.WebSocketHandlerRegistry;

@Configuration
@EnableWebSocket
public class RawConfig implements WebSocketConfigurer {
    private final RawHandler handler;

    public RawConfig(RawHandler handler) {
        this.handler = handler;
    }

    @Override
    public void registerWebSocketHandlers(WebSocketHandlerRegistry registry) {
        registry.addHandler(handler, "/ws/raw");
    }
}
```

`@EnableWebSocket` + `WebSocketConfigurer` applies to raw Servlet WebSocket. It does not enable `@MessageMapping` and does not emit STOMP-layer `SessionConnectedEvent`s.

### 7.6. StompConfig.java: STOMP endpoint and transport limits

```java
package demo.ws;

import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.simp.config.MessageBrokerRegistry;
import org.springframework.web.socket.config.annotation.EnableWebSocketMessageBroker;
import org.springframework.web.socket.config.annotation.StompEndpointRegistry;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;
import org.springframework.web.socket.config.annotation.WebSocketTransportRegistration;

@Configuration
@EnableWebSocketMessageBroker
public class StompConfig implements WebSocketMessageBrokerConfigurer {

    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/stomp");
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry config) {
        config.setApplicationDestinationPrefixes("/app");
        config.enableSimpleBroker("/topic", "/queue");
    }

    @Override
    public void configureWebSocketTransport(
            WebSocketTransportRegistration registration) {
        registration.setMessageSizeLimit(64 * 1024);
        registration.setSendBufferSizeLimit(512 * 1024);
        registration.setSendTimeLimit(15_000);
    }
}
```

`setMessageSizeLimit` bounds inbound **STOMP subprotocol messages** after reassembly. `setSendBufferSizeLimit`/`setSendTimeLimit` limit impact from slow-reading clients. These settings belong to STOMP transport registration and do not automatically apply to raw `RawHandler`.

`enableSimpleBroker` suffices for a single-instance example; it does not provide full receipt/ACK semantics or clustered broker support. Use an external broker relay when those features and scale are required.

### 7.7. PingController.java: success path and business errors

```java
package demo.ws;

import org.springframework.messaging.handler.annotation.MessageExceptionHandler;
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.SendTo;
import org.springframework.messaging.simp.annotation.SendToUser;
import org.springframework.stereotype.Controller;

@Controller
public class PingController {
    public record PingRequest(String text) {}
    public record PingReply(String text) {}
    public record ErrorReply(String code) {}

    @MessageMapping("/ping")
    @SendTo("/topic/pongs")
    public PingReply onPing(PingRequest request) {
        String text = request == null ? null : request.text();
        if (text == null || text.isBlank()) {
            throw new IllegalArgumentException("Text is required");
        }
        return new PingReply("PONG:" + text);
    }

    @MessageExceptionHandler(IllegalArgumentException.class)
    @SendToUser(value = "/queue/errors", broadcast = false)
    public ErrorReply onValidationError(IllegalArgumentException error) {
        return new ErrorReply("INVALID_TEXT");
    }
}
```

With `@MessageMapping("/ping")` and prefix `/app`, clients SEND to `/app/ping`. Valid requests produce `PingReply` on `/topic/pongs`. Blank requests throw an exception that `@MessageExceptionHandler` converts into a stable error schema sent to the originating session via `/user/queue/errors`. This is a **business error** and does not automatically close the WebSocket.

Spring uses a suitable message converter (Jackson by default when on the classpath) to deserialize JSON payloads into `PingRequest` records and serialize response records. Decoding errors prior to method invocation may trigger different exception types/layers: test explicitly with malformed JSON.

### 7.8. StompMonitor.java: counting connections at the right milestone and safe on duplicate disconnects

```java
package demo.ws;

import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.context.event.EventListener;
import org.springframework.messaging.simp.SimpMessageHeaderAccessor;
import org.springframework.stereotype.Component;
import org.springframework.web.socket.messaging.SessionConnectEvent;
import org.springframework.web.socket.messaging.SessionConnectedEvent;
import org.springframework.web.socket.messaging.SessionDisconnectEvent;
import org.springframework.web.socket.messaging.SessionSubscribeEvent;

@Component
public class StompMonitor {
    private final Set<String> connected = ConcurrentHashMap.newKeySet();
    private final Counter connectedTotal;
    private final Counter disconnectedTotal;
    private final Counter subscribeTotal;
    private final Counter connectAttempts;

    public StompMonitor(MeterRegistry metrics) {
        Gauge.builder("demo.ws.stomp.active", connected, Set::size)
                .register(metrics);
        this.connectedTotal = Counter.builder("demo.ws.stomp.connected")
                .register(metrics);
        this.disconnectedTotal =
                Counter.builder("demo.ws.stomp.disconnected")
                        .register(metrics);
        this.subscribeTotal =
                Counter.builder("demo.ws.stomp.subscriptions")
                        .register(metrics);
        this.connectAttempts =
                Counter.builder("demo.ws.stomp.connect.attempts")
                        .register(metrics);
    }

    @EventListener
    public void onConnect(SessionConnectEvent event) {
        connectAttempts.increment();
    }

    @EventListener
    public void onConnected(SessionConnectedEvent event) {
        String sessionId = SimpMessageHeaderAccessor
                .wrap(event.getMessage()).getSessionId();
        if (sessionId != null && connected.add(sessionId)) {
            connectedTotal.increment();
        }
    }

    @EventListener
    public void onSubscribe(SessionSubscribeEvent event) {
        subscribeTotal.increment();
    }

    @EventListener
    public void onDisconnect(SessionDisconnectEvent event) {
        if (connected.remove(event.getSessionId())) {
            disconnectedTotal.increment();
        }
    }
}
```

Increment `connectedTotal` only when a new session ID is added, and increment `disconnectedTotal` only when an ID is actually removed. That ensures duplicate `SessionDisconnectEvent`s for the same session never make counts negative or double-count closures.

To measure handshake failures or STOMP CONNECT failures, add metrics at those corresponding layers; `connectedTotal - disconnectedTotal` is not an exact count of all sockets, especially for sessions that never reached CONNECTED or across app restarts.

### 7.9. application.properties

```properties
server.port=8080
management.endpoints.web.exposure.include=health,info,metrics
management.endpoint.health.show-details=never
```

The demo exposes `/actuator/metrics` for viewing metrics; production must restrict network access, require authentication/authorization, or bind actuator to a separate management port with strict endpoint controls. Never expose all actuator endpoints publicly merely for debugging convenience.

### 7.10. static/index.html: testing both raw and STOMP from the browser

This page uses the browser WebSocket API for **raw** and illustrates **basic STOMP frames** without CDN dependencies. The manual STOMP part is for local learning only; production clients should use a STOMP library with proper framing, heartbeats, and reconnection.

```html
<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8">
  <title>WebSocket Observability Demo</title>
</head>
<body>
  <h1>Raw WebSocket + STOMP</h1>
  <button id="rawConnect">Connect raw</button>
  <button id="rawPing">Send raw PING</button>
  <button id="stompConnect">Connect STOMP</button>
  <button id="stompPing">Send STOMP ping</button>
  <button id="stompBad">Send invalid STOMP ping</button>
  <pre id="log"></pre>

  <script>
    const logBox = document.querySelector("#log");
    const protocol = location.protocol === "https:" ? "wss:" : "ws:";
    const base = protocol + "//" + location.host;
    const log = value => { logBox.textContent += value + "\n"; };
    let raw = null;
    let stomp = null;
    let stompReady = false;

    document.querySelector("#rawConnect").onclick = () => {
      raw = new WebSocket(base + "/ws/raw");
      raw.onopen = () => log("RAW OPEN");
      raw.onmessage = event => log("RAW " + event.data);
      raw.onerror = () => log("RAW ERROR");
      raw.onclose = event => log("RAW CLOSE " + event.code);
    };

    document.querySelector("#rawPing").onclick = () => {
      if (raw && raw.readyState === WebSocket.OPEN) {
        raw.send("PING");
      }
    };

    function frame(command, headers, body = "") {
      const lines = [command];
      for (const [key, value] of Object.entries(headers)) {
        lines.push(key + ":" + value);
      }
      return lines.join("\n") + "\n\n" + body + "\0";
    }

    document.querySelector("#stompConnect").onclick = () => {
      stompReady = false;
      stomp = new WebSocket(base + "/stomp", ["v12.stomp", "v11.stomp"]);
      stomp.onopen = () => {
        stomp.send(frame("CONNECT",
          {"accept-version": "1.2,1.1", host: location.hostname}));
      };
      stomp.onmessage = event => {
        const text = String(event.data);
        log("STOMP " + text.replaceAll("\0", "\\0"));
        if (text.startsWith("CONNECTED\n")) {
          stomp.send(frame("SUBSCRIBE",
            {id: "pongs", destination: "/topic/pongs"}));
          stomp.send(frame("SUBSCRIBE",
            {id: "errors", destination: "/user/queue/errors"}));
          stompReady = true;
          log("STOMP SUBSCRIBE sent");
        }
      };
      stomp.onerror = () => log("STOMP ERROR");
      stomp.onclose = event => {
        stompReady = false;
        log("STOMP CLOSE " + event.code);
      };
    };

    function sendPing(text) {
      if (!stompReady || stomp.readyState !== WebSocket.OPEN) {
        log("STOMP not CONNECTED yet");
        return;
      }
      stomp.send(frame("SEND",
        {destination: "/app/ping", "content-type": "application/json"},
        JSON.stringify({text})));
    }

    document.querySelector("#stompPing").onclick =
      () => sendPing("hello");
    document.querySelector("#stompBad").onclick =
      () => sendPing("");
  </script>
</body>
</html>
```

Note: this manual script assumes each `onmessage` delivers a single simple frame for demo purposes. Real STOMP requires a parser handling fragmentation, coalesced frames, escaping, and heartbeats. The simple broker does not fully support receipts, so `SUBSCRIBE sent` **does not confirm the subscriber is ready yet**; during manual testing, click send after subscriptions have been processed. For reliable automated tests, use a dedicated STOMP client or an application-level subscription confirmation step.

### 7.11. Running and observing results

From the directory containing `build.gradle`, with JDK 17+ and a compatible Gradle:

```bash
gradle bootRun
```

If the project has the Gradle Wrapper, use `./gradlew bootRun` (Unix/macOS) or `gradlew.bat bootRun` (Windows).

Open `http://localhost:8080/`:

1. Click **Connect raw**, then **Send raw PING**. The log shows `RAW OPEN` and `RAW PONG`.
2. Click **Connect STOMP**; after the `CONNECTED` frame and subscriptions, click **Send STOMP ping**. In the STOMP MESSAGE on `/topic/pongs`, the expected JSON body is `{"text":"PONG:hello"}`.
3. Click **Send invalid STOMP ping**; once the user-destination subscription is active, the expected error body `{"code":"INVALID_TEXT"}` arrives on `/user/queue/errors`.
4. Check `/actuator/metrics/demo.ws.raw.active`, `/actuator/metrics/demo.ws.raw.messages`, `/actuator/metrics/demo.ws.stomp.active`, and `/actuator/metrics/demo.ws.stomp.subscriptions` via browser or curl.

These are expected messages/metrics after performing the actions, **not a fixed stdout string**: event timing, metrics formatting, live session counts, and Spring Boot bootstrap logs vary with connection/close ordering. Never assume every run produces identical numbers.

## 8. Automated Testing: Unit, Integration, and End-to-End

Because WebSocket is a long-lived protocol, a solid test suite verifies **opening, sending/receiving, and closing**, not just direct Java method calls.

| Test layer | What is verified | What is NOT yet proven |
| --- | --- | --- |
| Handler/service unit tests | Validation, error mapping, state transitions | Does not verify HTTP Upgrade, WebSocket framing, or container |
| Spring context / messaging integration | `@MessageMapping`, channels, converters, handlers, event wiring | Does not verify network/proxy connectivity |
| End-to-end raw WebSocket | Real server, handshake, send/receive, close | Does not verify STOMP destination routing |
| End-to-end STOMP | CONNECTED, SUBSCRIBE, SEND, MESSAGE, ERROR, and broker | Does not verify load/proxy/TLS/multi-node |
| Load/soak/chaos | High connection counts, reconnects, slow clients, broker outages, timeouts | Meaningful only in production-like environments |

### 8.1. RawWebSocketIntegrationTest.java: testing against a real server

This test uses JUnit 5 and `@SpringBootTest(webEnvironment = RANDOM_PORT)` to start the embedded Servlet server on a random port. `StandardWebSocketClient` performs a real HTTP Upgrade rather than invoking the handler directly.

```java
package demo.ws;

import java.util.concurrent.BlockingQueue;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.web.socket.TextMessage;
import org.springframework.web.socket.WebSocketSession;
import org.springframework.web.socket.client.standard.StandardWebSocketClient;
import org.springframework.web.socket.handler.TextWebSocketHandler;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class RawWebSocketIntegrationTest {

    @LocalServerPort
    int port;

    @Test
    void shouldEchoPingAndReportBadCommand() throws Exception {
        BlockingQueue<String> replies = new LinkedBlockingQueue<>();

        TextWebSocketHandler clientHandler = new TextWebSocketHandler() {
            @Override
            protected void handleTextMessage(WebSocketSession session,
                                             TextMessage message) {
                replies.offer(message.getPayload());
            }
        };

        WebSocketSession session = new StandardWebSocketClient()
                .execute(clientHandler,
                        "ws://127.0.0.1:" + port + "/ws/raw")
                .get(5, TimeUnit.SECONDS);

        try {
            session.sendMessage(new TextMessage("PING"));
            assertEquals("PONG",
                    replies.poll(5, TimeUnit.SECONDS));

            session.sendMessage(new TextMessage("BAD"));
            assertEquals("ERROR:BAD_COMMAND",
                    replies.poll(5, TimeUnit.SECONDS));
        } finally {
            session.close();
        }
    }
}
```

How to run:

```bash
gradle test
```

The test uses bounded timeouts to prevent CI hangs. If no message arrives within 5 seconds, `poll` returns null and the assertion fails cleanly. `finally` closes the session. Never use arbitrary sleeps to fake synchronization. `Awaitility` can be used if you need to wait reliably for an active gauge to return to 0, since metrics often update asynchronously and should not be asserted immediately after calling `close()`.

### 8.2. Testing STOMP with WebSocketStompClient

Spring provides `WebSocketStompClient` (package `org.springframework.web.socket.messaging`), working with `StandardWebSocketClient` and `StompSessionHandler`/`StompFrameHandler`. A clean e2e flow:

1. Start Spring Boot on a random port.
2. Create `WebSocketStompClient`, configuring `MappingJackson2MessageConverter` when exchanging JSON DTOs.
3. Call `connectAsync(...)` and await CONNECTED via future/handler.
4. Subscribe to `/topic/pongs` and `/user/queue/errors` with a `StompFrameHandler` returning the expected Java payload type.
5. SEND valid data to `/app/ping`, wait for the message, and assert the returned DTO.
6. SEND invalid data and assert the error DTO arrives only for the originating user/session.
7. Disconnect and stop the client in `finally`.

Client snippet (**illustrative, not a complete test class**):

```java
WebSocketStompClient stompClient =
        new WebSocketStompClient(new StandardWebSocketClient());
stompClient.setMessageConverter(
        new MappingJackson2MessageConverter());

StompSession session = stompClient
        .connectAsync("ws://127.0.0.1:" + port + "/stomp",
                new StompSessionHandlerAdapter() {})
        .get(5, TimeUnit.SECONDS);
```

Additional imports: `org.springframework.web.socket.messaging.WebSocketStompClient` (as used in the code above); `org.springframework.messaging.converter.MappingJackson2MessageConverter`; `org.springframework.messaging.simp.stomp.StompSession`; `org.springframework.messaging.simp.stomp.StompSessionHandlerAdapter`; `org.springframework.web.socket.client.standard.StandardWebSocketClient`; `java.util.concurrent.TimeUnit`.

**Crucial note to prevent flaky tests:** With the simple broker, sending immediately after `SUBSCRIBE` does not guarantee the subscription has been registered yet because messaging channels process asynchronously; the simple broker also lacks full STOMP receipt support. If a test needs a reliable confirmation signal, design an application-level subscription confirmation step or use a broker supporting STOMP receipts and wait for the receipt. Never rely on `Thread.sleep(500)` as "proof" a subscriber is ready.

### 8.3. Testing connection and duplicate disconnect events

Verify two cases:

- Two disconnect notifications for the same `sessionId` decrement the active gauge only once.
- A CONNECT event does not mean the session is CONNECTED; only when the connected event arrives should it count as active.

For event listeners, unit tests can construct the event with a mock `Message<?>`/session ID and invoke the listener directly. That tests idempotency logic; to verify Spring actually fires the event during a live session, an integration test is required. If a session never finished connecting, disconnect cleanup must not drive the active count negative.

### 8.4. Testing failed handshakes and abnormal closures

Additional scenarios:

- Wrong path: connecting to `/ws/not-found` → handshake fails, typically HTTP 404.
- Blocked origin: with allowed-origins configured → browser handshake from disallowed origin is rejected.
- Missing token or session: verify the security layer returns 401/403 **before** upgrade.
- Oversized message: test both raw handler policy and container limits. When exceeding container buffers, the handler may never see the message.
- Transport error: simulate network loss or proxy socket closure; observe actual callbacks, counters, and close statuses.
- Multiple concurrent clients: active gauge rises, then returns to 0 as each client closes (allow eventual consistency).
- STOMP broker relay disconnect: observe `BrokerAvailabilityEvent`, detect delivery failures, and verify client reconnection.

Do not assert a single hardcoded HTTP status or close code when the value depends on proxy/container behavior in an unpinned environment; tests should specify the expected failure category and how to observe it.

## 9. Production Monitoring and Incident Troubleshooting Scenarios

### 9.1. Connections increase, yet no STOMP messages flow

Verify that the HTTP Upgrade succeeded, the client received `CONNECTED`, `/app/...` and `/topic/...` destinations match, and the broker is available. If socket counts rise while STOMP connected counts stay flat, inspect STOMP CONNECT, auth/interceptors, and broker routing first rather than immediately increasing pool sizes.

### 9.2. Sudden spike in abnormal closes

Correlate timestamps with reverse proxy idle timeouts, network drops, restarts, and send limits. Check whether STOMP heartbeats are configured and agreed upon by both client and server; heartbeats do not completely replace TCP/WebSocket transport checks. Monitor client reconnect counts and mitigate reconnect storms with exponential backoff and jitter.

### 9.3. Latency spikes and send buffers hit limits

Inspect `clientInboundChannel`/`clientOutboundChannel` executor stats, payload sizes, slow clients, subscriber counts, and broadcast rates. With STOMP, `setSendTimeLimit` and `setSendBufferSizeLimit` cap data queued for slow clients. If business logic blocks inside message handlers, offload blocking work appropriately rather than enlarging executors indefinitely.

### 9.4. Session counts fail to drop after disconnects

Audit cleanup idempotency; half-open network states or timeouts can delay callbacks. Ensure no `WebSocketSession` references linger in uncleaned maps. Check whether other subscribers or event listeners hold unbounded state. Never blindly decrement counters on arbitrary errors without knowing whether the session was previously registered.

### 9.5. STOMP errors do not reach the right client

Verify the client subscribed to `/user/queue/errors`, `@SendToUser(broadcast=false)` is used in the right context, authenticated principals/user destinations are configured properly, and whether the error came from `@MessageMapping` or the protocol layer. `@MessageExceptionHandler` does not replace `StompSubProtocolErrorHandler` for frame-formatting errors.

## 10. Security and Operational Limits

A long-lived connection does not mean client permissions never change. In production applications:

- Authenticate at the HTTP handshake or STOMP CONNECT per your auth architecture; authorize access per destination, room, and user.
- Enforce origin checks for browsers to reduce Cross-Site WebSocket Hijacking risk. Origin **is not an authentication mechanism** for non-browser clients.
- Never put access tokens, cookies, Authorization headers, or sensitive payloads into logs or metric labels.
- Enforce limits on message sizes, message rates, connections per user/IP, send buffers, idle timeouts, and heartbeats.
- Use `wss://` over HTTPS; ensure reverse proxies allow Upgrade/Connection headers and appropriate timeouts.
- Define clear policies for recoverable errors (business error messages), severe access violations (close/block connection), and system faults (internal logs + clean close).
- Never assume a CONNECTED STOMP session remains authorized after a token/session is revoked; design revalidation and proactive disconnection policies where possible.

## 11. Self-Check Exercises

**Exercise 1 — Error classification:** A browser connects to `ws://localhost:8080/ws/raw` and gets HTTP 403; another browser connects successfully and then receives close 1009 after sending a large message. Which layer handles each case? Why is there no HTTP 403 in the second case?

**Exercise 2 — Lifecycle:** A client sends STOMP CONNECT but has not received CONNECTED yet; should the server already increment `demo.ws.stomp.active`? Explain using `SessionConnectEvent` and `SessionConnectedEvent`.

**Exercise 3 — Duplicate disconnects:** Invoke the `onDisconnect` listener twice for the same previously connected ID. How do the gauge and counter change? Why must you check that `Set.remove` returns `true`?

**Exercise 4 — Error routing:** Send JSON `{"text":""}` to `/app/ping`. In the demo, which destination does the error from `@MessageExceptionHandler` go to? Does it automatically become a STOMP ERROR frame?

**Exercise 5 — Monitoring:** You observe 50 raw WebSocket sessions but 45 STOMP sessions, 10 transport errors in one minute, and growing outbound send buffers. List three hypotheses to investigate and additional metrics/logs needed to isolate the cause rather than jumping to conclusions from a single gauge.

**Exercise 6 — E2E test:** Add a test connecting two raw clients simultaneously, sending PING from one client, and proving the other client does not receive the message because the endpoint replies only to the calling session. Close both clients and use a bounded wait to assert the active gauge returns to 0.

**Exercise 7 — Reliability:** If the app migrates from the simple broker to a broker relay, what behavior should be added when `BrokerAvailabilityEvent` reports false and clients lose CONNECTED? Why are backoff reconnects and delivery-failure handling still required even right after the event reports true?

## 12. Key Rules to Remember

1. **Handshake errors, transport errors, raw message errors, and STOMP errors are four distinct situations.** Choose the handler at the right layer.
2. `handleTransportError` is not a catch-all net for every exception; `afterConnectionClosed` is where raw WebSocket lifecycle cleanup belongs.
3. `@MessageExceptionHandler` handles `@MessageMapping` method exceptions; `StompSubProtocolErrorHandler` handles subprotocol-level STOMP errors.
4. `SessionConnectEvent` differs from `SessionConnectedEvent`; track STOMP online state at the CONNECTED milestone.
5. `SessionDisconnectEvent` can fire multiple times; cleanup must be idempotent.
6. `WebSocketMessageBrokerStats` reflects STOMP infrastructure, while raw handlers should expose their own dedicated metrics.
7. A test invoking a Java handler method directly **does not prove** WebSocket handshakes/frames work; combine unit, integration, and end-to-end tests.
8. Never use arbitrary sleeps to assume STOMP SUBSCRIBE is ready on the simple broker; synchronize at the proper layer.
9. Monitor active sessions, errors, closures, message rates, send buffers, broker health, and client reconnects; avoid unbounded IDs in metric labels.
10. Production systems require authorization policies, payload limits, timeouts, backpressure/reconnection strategies, and safe logging before public launch.

## Official Reference Documentation

- Spring WebSocket Servlet API: https://docs.spring.io/spring-framework/reference/6.2/web/websocket/server.html
- Spring STOMP application context events: https://docs.spring.io/spring-framework/reference/6.2/web/websocket/stomp/application-context-events.html
- Spring STOMP annotated controllers and MessageExceptionHandler: https://docs.spring.io/spring-framework/reference/6.2/web/websocket/stomp/handle-annotations.html
- Spring STOMP interception: https://docs.spring.io/spring-framework/reference/6.2/web/websocket/stomp/interceptors.html
- Spring STOMP monitoring: https://docs.spring.io/spring-framework/reference/6.2/web/websocket/stomp/stats.html
- Spring STOMP performance: https://docs.spring.io/spring-framework/reference/6.2/web/websocket/stomp/configuration-performance.html
- Spring STOMP testing: https://docs.spring.io/spring-framework/reference/6.2/web/websocket/stomp/testing.html
- Spring WebSocketClient JavaDoc (6.2): https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/web/socket/client/WebSocketClient.html
