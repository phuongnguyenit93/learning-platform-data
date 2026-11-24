# WebSocket Handshake, Subprotocol, and Connection Lifecycle in Spring Framework

## 1. Learning Objectives and Scope

WebSocket creates a **long-lived, bidirectional (full-duplex)** communication channel between client and server. Unlike a regular HTTP request that ends after returning a response, a WebSocket connection starts with an **HTTP handshake**, then transitions to exchanging **WebSocket frames** over the same connection. If both sides use an application protocol such as **STOMP**, they also negotiate a **subprotocol** during the handshake and exchange STOMP frames over WebSocket.

After this lesson, you will be able to:

- Explain step by step the HTTP/1.1 Upgrade handshake and the meaning of the headers `Upgrade`, `Connection`, `Sec-WebSocket-Key`, `Sec-WebSocket-Accept`, `Sec-WebSocket-Version`, `Origin`, and `Sec-WebSocket-Protocol`.
- Distinguish between **HTTP handshake**, **WebSocket connection**, **WebSocket subprotocol**, **STOMP CONNECT**, **STOMP subscription**, and **SockJS fallback**.
- Configure endpoints using `@EnableWebSocket` / `WebSocketConfigurer` or `@EnableWebSocketMessageBroker` / `WebSocketMessageBrokerConfigurer`, inspect handshakes with `HandshakeInterceptor`, and negotiate subprotocols through `SubProtocolCapable`/`HandshakeHandler`.
- Track the `CONNECTING → OPEN → CLOSING → CLOSED` lifecycle, Spring callbacks, close statuses, transport errors, heartbeats, and resource cleanup.
- Run a Java 17+ example using Spring Boot, a raw WebSocket server, and the Java JDK WebSocket client; inspect the handshake, selected subprotocol, message send/receive, and close flow.

**Reference versions:** Java 17+, Spring Framework 6.1/Spring Boot 3.3. The example syntax applies to the **Servlet stack (Spring MVC)** with `spring-websocket`. Spring WebFlux has a different reactive API, covered separately in section 10. WebSocket follows RFC 6455; HTTP/1.1 upgrade is the common path illustrated here. HTTP/2 uses an extended CONNECT mechanism per RFC 8441 and does not use the exact HTTP/1.1 header sequence shown in the examples below.

## 2. Why Is a Handshake Needed Before Sending Data?

A WebSocket client cannot immediately send arbitrary text messages to a `ws://...` URL. It must establish a network/TLS connection if needed, send a protocol-compliant connection request, be accepted by the server, and only then exchange WebSocket frames.

Example HTTP/1.1 request to open a connection (sample key value):

```http
GET /ws/echo HTTP/1.1
Host: localhost:8080
Upgrade: websocket
Connection: Upgrade
Sec-WebSocket-Version: 13
Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==
Sec-WebSocket-Protocol: demo.v1, chat.v2
Origin: http://localhost:3000
```

If accepted, the server may respond:

```http
HTTP/1.1 101 Switching Protocols
Upgrade: websocket
Connection: Upgrade
Sec-WebSocket-Accept: s3pPLMBiTxaQ9kYGzzhZRbK+xOo=
Sec-WebSocket-Protocol: demo.v1
```

This is a **handshake example using the sample key from RFC 6455**; real keys must be generated randomly for every handshake. Do not hardcode the sample key when building a production client. The `Origin` header is added by browsers when applicable; native Java clients and other non-browser clients might not send it.

Overall flow:

```text
Browser/JDK/JS client                 Spring + HTTP server
       |                                        |
       |  TCP connect / TLS if using wss        |
       |--------------------------------------->|
       |  GET /ws/echo + Upgrade: websocket     |
       |  Sec-WebSocket-Key + protocol offers   |
       |--------------------------------------->|
       |                         validate method,
       |                         version, key, Origin,
       |                         security/interceptor
       |                         select subprotocol
       |  101 + Sec-WebSocket-Accept + protocol |
       |<---------------------------------------|
       | ======= WebSocket OPEN ============== |
       |  TEXT / BINARY / PING / PONG frames    |
       |<======================================>|
       |  CLOSE frame (code + reason)           |
       |<-------------------------------------->|
       |  TCP/TLS connection closed             |
       |---------------------------------------X
```

### Meaning of each header

| Header/status | Sent by | Practical meaning |
| --- | --- | --- |
| `GET ... HTTP/1.1` | Client | Opens the handshake on an HTTP endpoint that supports WebSocket. |
| `Upgrade: websocket` | Client and server | Requests/confirms switching to WebSocket. |
| `Connection: Upgrade` | Client and server | Indicates the `Upgrade` token is an option for the current HTTP hop. |
| `Sec-WebSocket-Version: 13` | Client | Standard RFC 6455 wire protocol version. |
| `Sec-WebSocket-Key` | Client | Random Base64-encoded nonce; **not a password or login token**. |
| `Sec-WebSocket-Accept` | Server | Proves the response matches the request key, computed per RFC 6455. |
| `Origin` | Usually browser | Helps the server enforce origin policy; **does not replace authentication**. |
| `Sec-WebSocket-Protocol` | Client proposes; server selects | Selects **one** application subprotocol supported by both sides. |
| `Sec-WebSocket-Extensions` | Negotiated by both sides | Wire-protocol extensions, such as `permessage-deflate` compression; not a subprotocol. |
| `101 Switching Protocols` | Server | Upgrade handshake succeeded; subsequent traffic is WebSocket frames, no longer per-message HTTP request/response pairs. |

With the sample key `dGhlIHNhbXBsZSBub25jZQ==`, the server computes:

```text
Sec-WebSocket-Accept =
  Base64(SHA-1(
    Sec-WebSocket-Key
    + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"))
```

The result is `s3pPLMBiTxaQ9kYGzzhZRbK+xOo=`. The GUID is an RFC constant; SHA-1 here is used **to verify the handshake**, not as cryptography to authenticate identity or protect payloads. Transport security comes from `wss://` (TLS), authentication, and application authorization.

### When does the handshake fail?

Several error categories should be kept distinct:

1. **Before HTTP:** DNS, TCP connect, TLS certificate/handshake, proxy/firewall. No HTTP 101 response is received.
2. **HTTP handshake rejected:** endpoint does not exist (404), user is unauthenticated (401/403 per security), invalid Origin (403), wrong method/header/version, or server/proxy does not support Upgrade.
3. **101 returned but headers are invalid:** an RFC-compliant client must verify `Sec-WebSocket-Accept` and the selected subprotocol. If invalid, the client aborts the connection.
4. **Handshake succeeded but WebSocket/application failed:** these are post-OPEN errors; observe them via WebSocket close/error, as you cannot "return HTTP 500" for an individual message like a normal HTTP request.

Do not treat every "WebSocket connection failed" error as a message handler bug; in many cases the request never even reached `afterConnectionEstablished`.

## 3. Subprotocol: The Contract Layer on Top of WebSocket

RFC 6455 defines **TEXT/BINARY frames and control frames**, while the business meaning of text/binary is up to the application. A **subprotocol** is a concrete convention for encoding and interpreting messages, such as `chat.v1`, `graphql-transport-ws`, or STOMP versions (`v10.stomp`, `v11.stomp`, `v12.stomp`).

A client may send:

```http
Sec-WebSocket-Protocol: chat.v2, chat.v1
```

The server may only select **one value proposed by the client**, for example:

```http
Sec-WebSocket-Protocol: chat.v1
```

If there is no common protocol, the server **must not return a subprotocol name that was not proposed**. The server may omit selecting a subprotocol and still allow WebSocket if the application accepts subprotocol-less mode; if business rules **require** STOMP or a specific chat version, enforce a rejection condition or close the connection at the appropriate layer. Do not assume that a mismatched offer list is always rejected automatically.

**Subprotocol ≠ WebSocket URL:** `/ws/chat` is the endpoint; `chat.v1` defines the syntax and semantics of messages running over that connection. The same endpoint can support multiple protocol versions if the handler defines them clearly.

**Subprotocol ≠ HTTP Content-Type:** After `101`, payloads travel inside WebSocket frames, not HTTP bodies of individual GET/POST calls. The subprotocol selects the application format; it may combine text JSON or binary protobuf by mutual agreement.

**Subprotocol ≠ extension:** `permessage-deflate` controls frame compression, not message structure or routing.

### Is STOMP a subprotocol?

Yes. Spring supports **STOMP over WebSocket**: WebSocket handles transport; STOMP defines commands `CONNECT`, `CONNECTED`, `SEND`, `SUBSCRIBE`, `MESSAGE`, `DISCONNECT` and headers `destination`, `subscription`, `receipt`, `heart-beat`. Browsers select STOMP in `Sec-WebSocket-Protocol` if the client sends a matching list and the server supports it.

There are **two distinct steps**:

1. **HTTP/WebSocket handshake** completes: server returns 101; WebSocket is OPEN.
2. **Application-level STOMP handshake**: client sends a `CONNECT` or `STOMP` frame; server/broker replies with `CONNECTED` before processing subscriptions/messages.

Example after WebSocket is OPEN:

```text
CONNECT
accept-version:1.2
heart-beat:10000,10000

^@
```

`^@` represents the NUL byte (0x00) terminating a STOMP frame, not two literal caret/at characters. The server responds with a `CONNECTED` frame if STOMP CONNECT is accepted. **HTTP 101 does not mean STOMP CONNECT has succeeded**, nor are there any active `SUBSCRIBE`s yet.

A raw WebSocket handler selecting the `demo.v1` subprotocol is a simple way to learn negotiation. Spring's STOMP handler is more complex because it also involves channels, controllers, a broker, and STOMP frame handling.

## 4. Spring MVC: Configuring Raw WebSocket Endpoints and Handshake

In the Servlet stack, use `spring-websocket`, `@EnableWebSocket`, and `WebSocketConfigurer`. You register:

- **URL endpoint:** for example `/ws/echo`.
- **`WebSocketHandler`:** callbacks when connections open/close, messages arrive, or transport errors occur.
- **`HandshakeInterceptor`:** pre/post-handshake logic; can reject before 101 or store attributes.
- **`HandshakeHandler`:** validates protocol/Origin/extensions and delegates upgrade to the server container; by default Spring uses `DefaultHandshakeHandler` when appropriate.
- **Origin policy:** `setAllowedOrigins(...)`/`setAllowedOriginPatterns(...)`, especially for cross-origin browsers.

Minimal configuration pattern:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.web.socket.config.annotation.EnableWebSocket;
import org.springframework.web.socket.config.annotation.WebSocketConfigurer;
import org.springframework.web.socket.config.annotation.WebSocketHandlerRegistry;

@Configuration
@EnableWebSocket
class RawWebSocketConfiguration implements WebSocketConfigurer {
    @Override
    public void registerWebSocketHandlers(WebSocketHandlerRegistry registry) {
        registry.addHandler(new EchoHandler(), "/ws/echo")
                .addInterceptors(new ConnectionMetadataInterceptor())
                .setAllowedOriginPatterns("http://localhost:*");
    }
}
```

This is a **fragment**; `EchoHandler` and `ConnectionMetadataInterceptor` are classes you need to define. A complete runnable example is in section 8. In production, configure allowed origins per environment and combine with Spring Security appropriately; `*` is only glob matching for local dev examples and does not grant login authorization.

### HandshakeInterceptor: acting before Upgrade

The `HandshakeInterceptor` interface defines:

```java
boolean beforeHandshake(
    ServerHttpRequest request,
    ServerHttpResponse response,
    WebSocketHandler wsHandler,
    Map<String, Object> attributes);

void afterHandshake(
    ServerHttpRequest request,
    ServerHttpResponse response,
    WebSocketHandler wsHandler,
    Exception exception);
```

These are simplified API signatures. `beforeHandshake` can read method, URI, headers, user principal, and HTTP session; if unauthorized, set an appropriate HTTP status and return `false`. Entries placed into `attributes` are copied to the `WebSocketSession` attributes upon successful handshake, such as a correlation ID or safe user ID. Do not store raw passwords or access tokens in `attributes` or logs.

**Do not confuse:** `afterHandshake` is a callback after handshake processing completes; it is not proof that STOMP is CONNECTED, nor does it replace `afterConnectionEstablished`. To observe an actually open session, use the `WebSocketHandler` lifecycle callback or appropriate STOMP events.

### HandshakeHandler and subprotocol negotiation

`DefaultHandshakeHandler` checks WebSocket requirements, origin, and subprotocols, then delegates the upgrade to the container. For a raw `WebSocketHandler`, Spring can obtain supported subprotocols from the handler if it implements `SubProtocolCapable`:

```java
import java.util.List;
import org.springframework.web.socket.SubProtocolCapable;
import org.springframework.web.socket.handler.TextWebSocketHandler;

class EchoHandler extends TextWebSocketHandler
        implements SubProtocolCapable {

    @Override
    public List<String> getSubProtocols() {
        return List.of("demo.v1");
    }
}
```

If the client proposes `demo.v1` and the server selects it, Spring's `WebSocketSession.getAcceptedProtocol()` returns the negotiated name (once the session is open). If a handler only supports raw messages without a subprotocol, implementing `SubProtocolCapable` is not required; both sides must agree on a shared message format through other application conventions.

**When to customize `DefaultHandshakeHandler`?** When you need custom subprotocol selection rules or handshake control that default hooks do not cover; ensure any customization respects the RFC and security policies. Simple business checks belong in an interceptor rather than rewriting the upgrade mechanism.

## 5. WebSocket Lifecycle: From TCP Connect to Cleanup

### 5.1 States

```text
             TCP/TLS connect + HTTP handshake
    ┌─────────────────────────────────────────┐
    │                                         ▼
CONNECTING -------------------------------> OPEN
    │       handshake failed                   │
    ▼                                          │ send/receive TEXT/BINARY
  CLOSED                                       │ PING/PONG
                                               ▼
                                            CLOSING
                                         close frame exchange
                                               ▼
                                             CLOSED

Exception: sudden network loss may lead to CLOSED/abnormal
without full standard close frames.
```

`CONNECTING`, `OPEN`, `CLOSING`, `CLOSED` are common state descriptions in browser/client WebSocket APIs. Spring servers represent the lifecycle through callbacks and `WebSocketSession.isOpen()`; it is not necessarily the same public enum across all server APIs.

While **OPEN**, both sides can exchange frames per the WebSocket protocol. There are two data frame types: TEXT and BINARY; messages can be fragmented into multiple frames, and handlers may support partial messages depending on configuration/server. Ping/Pong and Close are separate **control frames**, not regular text messages.

### 5.2 Callbacks in Spring's WebSocketHandler

| Timing | Callback API | Typical work |
| --- | --- | --- |
| After handshake succeeds, WebSocket ready | `afterConnectionEstablished(WebSocketSession)` | Record OPEN metrics, initialize per-session state, check protocol/attributes |
| When a message arrives | `handleMessage(...)`; usually override `handleTextMessage(...)` in `TextWebSocketHandler` | Parse and process payload per contract; respond in a controlled manner |
| On transport error | `handleTransportError(WebSocketSession, Throwable)` | Log error safely, clean up, close if session is still open |
| After connection closes | `afterConnectionClosed(WebSocketSession, CloseStatus)` | Remove state/registries, decrement metrics, stop sending messages |
| When Pong arrives | `handlePongMessage(...)` (if supported by handler) | Track transport heartbeat/round-trip if needed |

Example normal event sequence:

```text
HTTP handshake accepted
afterConnectionEstablished(session)
handleTextMessage(session, "hello")
sendTextMessage(session, "echo:hello")
close frame exchanged / underlying transport closed
afterConnectionClosed(session, CloseStatus.NORMAL)
```

**Callback ordering is not guaranteed across all network failures.** For example, a sudden connection drop may invoke `handleTransportError` and `afterConnectionClosed` with differing details; cleanup logic must be **idempotent** (removing multiple times must not corrupt state). If the handshake has not succeeded, no valid `WebSocketSession` exists as OPEN; do not wait for `afterConnectionClosed` to clean up resources allocated in an interceptor before Upgrade.

### 5.3 Close handshake and status codes

A standard WebSocket close **sends a CLOSE control frame**, the peer typically replies with CLOSE (if not already sent), and the transport closes. In Spring:

```java
session.close(CloseStatus.NORMAL);     // code 1000
```

Important status codes:

| Code | Meaning | When observed |
| --- | --- | --- |
| `1000` | Normal closure | Client/user finished session, or server ended normally |
| `1001` | Going away | Server shutting down, endpoint navigating away/closing app |
| `1002` | Protocol error | WebSocket framing/handshake protocol violation |
| `1003` | Unsupported data | Data type received is unsupported by the handler |
| `1006` | Abnormal closure (**never sent on the wire**) | API reports connection died without receiving a standard close frame |
| `1008` | Policy violation | Application policy violated |
| `1009` | Message too big | Message exceeded size limit |
| `1011` | Internal server error | Server error while processing a message |
| `1012` / `1013` | Service restart / Try again later | Corresponding operational conditions if endpoint supports them |

**1005 and 1006 are status-representation values and must not be placed into a Close frame on the wire.** Never force sending `1006` via `session.close(...)`; use a valid code such as 1000/1008/1011, and log the cause when a connection drops abnormally. Reason strings should not contain sensitive information and must obey the UTF-8 byte limit of close control frames. A TCP reset does not mean the peer received the application's close frame.

### 5.4 Ping/Pong and heartbeats

- **WebSocket Ping/Pong:** RFC 6455 control frames; help detect transport liveness per runtime policy. Endpoints receiving Ping must respond with Pong per the RFC; the browser JavaScript WebSocket API does not expose raw ping/pong functions to application code.
- **STOMP heart-beat:** STOMP-layer heartbeat negotiated in `CONNECT`/`CONNECTED` via the `heart-beat` header; **not** WebSocket Ping/Pong. It can detect an inactive client or broker even when the underlying TCP connection appears alive.
- **TCP keepalive:** OS/socket-level network option; does not replace application timeouts. Proxies/firewalls/load balancers have their own idle timeouts.
- **SockJS heartbeat:** when using fallback transports, keepalive behavior may differ from raw WebSocket and is affected by STOMP heartbeat configuration.

Choose heartbeat intervals carefully: too short creates unnecessary traffic, too long delays detecting network loss. For each transport, measure timeouts across proxies, engines, brokers, and the application. Never write a blocking/sleeping ping loop on an I/O thread.

## 6. STOMP over WebSocket: Endpoints and Separate Lifecycle Milestones

To use STOMP messaging instead of manually parsing raw text, you can configure Spring MVC with:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.simp.config.MessageBrokerRegistry;
import org.springframework.web.socket.config.annotation.EnableWebSocketMessageBroker;
import org.springframework.web.socket.config.annotation.StompEndpointRegistry;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;

@Configuration
@EnableWebSocketMessageBroker
class StompConfiguration implements WebSocketMessageBrokerConfigurer {

    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/ws/stomp")
                .setAllowedOriginPatterns("https://app.example.org");
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.setApplicationDestinationPrefixes("/app");
        registry.enableSimpleBroker("/topic", "/queue");
    }
}
```

This is an **illustrative configuration snippet**, independent of the raw WebSocket demo in section 8. `/ws/stomp` is the HTTP endpoint that opens the WebSocket; `/app/...` and `/topic/...` are **STOMP destination prefixes**, not HTTP handshake URLs. `/app` typically routes `SEND` frames to `@MessageMapping` controller methods, while `/topic`/`/queue` are handled by the simple broker per the configuration above. With the simple broker, these two prefixes are only routing conventions and do not automatically guarantee message persistence or enterprise queue semantics.

Example flow:

```text
Client                             Spring STOMP messaging
  GET /ws/stomp + WebSocket Upgrade   → HTTP 101
  STOMP CONNECT                       → STOMP CONNECTED
  STOMP SUBSCRIBE /topic/updates      → broker stores subscription
  STOMP SEND /app/notify              → @MessageMapping handles
                                      → broker sends MESSAGE /topic/updates
  STOMP DISCONNECT                    → cleanup STOMP session
  WebSocket CLOSE                     → close transport
```

Why distinguish these? A WebSocket can be **OPEN** while STOMP is not yet `CONNECTED` (client has not sent the CONNECT frame, was rejected, or is waiting on the broker). Checking application state solely via WebSocket callbacks and assuming the user has already "subscribed" is inaccurate.

### STOMP-side lifecycle events

Spring publishes useful `ApplicationEvent`s:

- `SessionConnectEvent`: server received STOMP CONNECT from the client; the broker may not have confirmed the connection yet.
- `SessionConnectedEvent`: the STOMP session is reported as connected after CONNECT processing succeeds.
- `SessionSubscribeEvent` / `SessionUnsubscribeEvent`: STOMP subscription registered/canceled.
- `SessionDisconnectEvent`: signals STOMP session termination; may fire multiple times for the same session in some flows, so cleanup must be idempotent.

Example observer listener:

```java
import org.springframework.context.event.EventListener;
import org.springframework.messaging.simp.stomp.StompHeaderAccessor;
import org.springframework.stereotype.Component;
import org.springframework.web.socket.messaging.SessionConnectedEvent;
import org.springframework.web.socket.messaging.SessionDisconnectEvent;

@Component
class StompSessionEvents {
    @EventListener
    void onConnected(SessionConnectedEvent event) {
        StompHeaderAccessor accessor =
                StompHeaderAccessor.wrap(event.getMessage());
        System.out.println("STOMP CONNECTED: " + accessor.getSessionId());
    }

    @EventListener
    void onDisconnected(SessionDisconnectEvent event) {
        System.out.println("STOMP DISCONNECTED: " + event.getSessionId());
        // Clean up state map by sessionId using an idempotent operation.
    }
}
```

This is a **Spring bean fragment**, not a standalone Java file. Depending on the event type, native/STOMP headers can vary; avoid relying on event listeners to extract credentials that are not guaranteed to exist. When a broker relay is enabled, CONNECT phases may also depend on the external broker connection. The **simple broker** is suited for learning/small apps and lacks full-featured broker capabilities (full ACK/receipts, clustering, persistence, etc.).

### STOMP authentication vs. HTTP handshake authentication

Spring normally associates the HTTP handshake `Principal` with the WebSocket/STOMP session. With cookie-based authentication, browsers send cookies on the handshake when policy permits; Spring Security can authenticate before the upgrade. STOMP `login`/`passcode` by default **does not automatically replace** HTTP authentication in Spring WebSocket; if an application passes tokens in STOMP `CONNECT`, you must implement an inbound channel interceptor, explicitly authenticate and bind the `Principal`, and enforce destination authorization policies.

A connection whose handshake succeeded **is not automatically authorized to send to every `/app/...` or subscribe to every `/topic/...`**. Authorization must check both connection and message destinations. With browsers and cookies, remember to consider origin policy and CSRF/security on STOMP CONNECT for your stack.

## 7. SockJS: Why Can the Handshake Flow Differ?

`SockJS` provides fallback transports when the environment does not support standard WebSocket or proxies block Upgrade. It can be enabled with:

```java
registry.addEndpoint("/ws/stomp")
        .setAllowedOriginPatterns("https://app.example.org")
        .withSockJS();
```

A SockJS client exchanges additional HTTP requests (such as `/info` and transport-specific paths), then selects WebSocket or XHR streaming/polling depending on capability. **You cannot take a SockJS fallback request and assume it follows the `101 Switching Protocols` handshake of raw WebSocket**. STOMP frames can run over fallback transports, so the STOMP session lifecycle and transport lifecycle must be observed separately.

Do not point browser-native `new WebSocket("ws://host/ws/stomp")` at a SockJS URL variant and expect it to understand SockJS paths/frames. If the server exposes native WebSocket on the STOMP endpoint, use a STOMP library with the appropriate `brokerURL`; if you want SockJS fallback, use the SockJS client + StompJS configured with `webSocketFactory`. Keep client and server choices consistent.

## 8. Runnable Example: Raw WebSocket Handshake, Subprotocol, and Close

This example intentionally uses **raw WebSocket** to observe the handshake and lifecycle clearly. You can later extend to STOMP via the separate configuration in section 6. Runtime: Java 17+, Gradle, Spring Boot 3.3.x. The JDK includes `java.net.http.WebSocket`, so the client needs neither npm nor a browser.

### 8.1 Create the project

Structure:

```text
websocket-lifecycle-demo/
├── build.gradle
└── src/main/java/demo/
    ├── WsLifecycleApplication.java
    └── WsClientApp.java
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
version = '1.0.0'

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-websocket'
}

springBoot {
    mainClass = 'demo.WsLifecycleApplication'
}

tasks.register('runClient', JavaExec) {
    group = 'application'
    description = 'Connect the JDK WebSocket client to the local server'
    classpath = sourceSets.main.runtimeClasspath
    mainClass = 'demo.WsClientApp'
}
```

`spring-boot-starter-websocket` brings in the required WebSocket dependencies along with Spring Boot's default Servlet server. The Boot plugin manages dependency versions, avoiding manual mismatches between Spring Framework and Tomcat.

### 8.2 Server: WsLifecycleApplication.java

```java
package demo;

import java.io.IOException;
import java.util.List;
import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpStatus;
import org.springframework.http.server.ServerHttpRequest;
import org.springframework.http.server.ServerHttpResponse;
import org.springframework.web.socket.CloseStatus;
import org.springframework.web.socket.SubProtocolCapable;
import org.springframework.web.socket.TextMessage;
import org.springframework.web.socket.WebSocketHandler;
import org.springframework.web.socket.WebSocketSession;
import org.springframework.web.socket.config.annotation.EnableWebSocket;
import org.springframework.web.socket.config.annotation.WebSocketConfigurer;
import org.springframework.web.socket.config.annotation.WebSocketHandlerRegistry;
import org.springframework.web.socket.handler.TextWebSocketHandler;
import org.springframework.web.socket.server.HandshakeInterceptor;

@SpringBootApplication
public class WsLifecycleApplication {
    public static void main(String[] args) {
        SpringApplication.run(WsLifecycleApplication.class, args);
    }
}

@Configuration
@EnableWebSocket
class WebSocketConfiguration implements WebSocketConfigurer {

    @Override
    public void registerWebSocketHandlers(WebSocketHandlerRegistry registry) {
        registry.addHandler(new EchoHandler(), "/ws/echo")
                .addInterceptors(new DemoHandshakeInterceptor())
                .setAllowedOriginPatterns("http://localhost:*");
    }
}

class DemoHandshakeInterceptor implements HandshakeInterceptor {

    @Override
    public boolean beforeHandshake(
            ServerHttpRequest request,
            ServerHttpResponse response,
            WebSocketHandler handler,
            Map<String, Object> attributes) {

        // Condition is for demo only; do not use query parameters as credentials.
        if (!"client=cli".equals(request.getURI().getRawQuery())) {
            response.setStatusCode(HttpStatus.FORBIDDEN);
            return false;
        }

        attributes.put("client", "cli");
        return true;
    }

    @Override
    public void afterHandshake(
            ServerHttpRequest request,
            ServerHttpResponse response,
            WebSocketHandler handler,
            Exception exception) {
        // Non-sensitive metrics/traces can be recorded after handshake.
    }
}

class EchoHandler extends TextWebSocketHandler implements SubProtocolCapable {

    @Override
    public List<String> getSubProtocols() {
        return List.of("demo.v1");
    }

    @Override
    public void afterConnectionEstablished(WebSocketSession session) {
        System.out.println("OPEN protocol=" + session.getAcceptedProtocol()
                + " client=" + session.getAttributes().get("client"));
    }

    @Override
    protected void handleTextMessage(
            WebSocketSession session,
            TextMessage message) throws IOException {
        session.sendMessage(new TextMessage("echo:" + message.getPayload()));
    }

    @Override
    public void handleTransportError(
            WebSocketSession session,
            Throwable exception) throws Exception {
        System.err.println("Transport error: "
                + exception.getClass().getSimpleName());
        if (session.isOpen()) {
            session.close(CloseStatus.SERVER_ERROR);
        }
    }

    @Override
    public void afterConnectionClosed(
            WebSocketSession session,
            CloseStatus status) {
        System.out.println("CLOSED code=" + status.getCode());
    }
}
```

What to observe:

- `@EnableWebSocket` enables the infrastructure to register handlers at `/ws/echo`.
- `beforeHandshake` checks the `?client=cli` query parameter and puts a validated attribute into the session. Returning `false` when missing yields `403` **before** WebSocket OPEN. This is only an **exercise to distinguish lifecycle phases**, not a production authentication mechanism.
- `EchoHandler.getSubProtocols()` offers `demo.v1` for negotiation; `session.getAcceptedProtocol()` returns the selected protocol.
- `afterConnectionEstablished` runs after a successful handshake, and `handleTextMessage` sends the reply.
- `afterConnectionClosed` logs the status. `handleTransportError` handles transport errors by closing the session if it is still open.

In multi-client applications, never store unsynchronized mutable state on a singleton handler; keep state keyed by `session.getId()` in a concurrent map, bound resources, and make cleanup idempotent. Sending concurrently from multiple threads to a single session requires synchronization or `ConcurrentWebSocketSessionDecorator` with appropriate send time/buffer limits; a `WebSocketSession` is not an unbounded queue.

### 8.3 Client: WsClientApp.java (Java 17)

```java
package demo;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.WebSocket;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionStage;
import java.util.concurrent.TimeUnit;

public class WsClientApp {

    public static void main(String[] args) throws Exception {
        CompletableFuture<String> reply = new CompletableFuture<>();
        StringBuilder partial = new StringBuilder();

        WebSocket.Listener listener = new WebSocket.Listener() {
            @Override
            public void onOpen(WebSocket socket) {
                socket.request(1);
            }

            @Override
            public CompletionStage<?> onText(
                    WebSocket socket, CharSequence data, boolean last) {
                partial.append(data);
                if (last) {
                    reply.complete(partial.toString());
                }
                socket.request(1);
                return CompletableFuture.completedFuture(null);
            }

            @Override
            public void onError(WebSocket socket, Throwable error) {
                reply.completeExceptionally(error);
            }
        };

        HttpClient client = HttpClient.newHttpClient();
        WebSocket socket = client.newWebSocketBuilder()
                .subprotocols("demo.v1")
                .buildAsync(
                        URI.create("ws://localhost:8080/ws/echo?client=cli"),
                        listener)
                .get(5, TimeUnit.SECONDS);

        System.out.println("selected=" + socket.getSubprotocol());

        socket.sendText("hello", true).join();
        System.out.println("received=" + reply.get(5, TimeUnit.SECONDS));

        socket.sendClose(WebSocket.NORMAL_CLOSURE, "done").join();
    }
}
```

The client proposes `Sec-WebSocket-Protocol: demo.v1` and connects to the endpoint via the WebSocket handshake performed by `HttpClient`. The listener requests further deliveries with `request(1)` to satisfy the Java WebSocket client's demand mechanism, accumulates text chunks until `last=true`, and delivers the result to the main thread. `sendClose(...)` initiates a normal close handshake.

### 8.4 Running, Results, and Experiments

In the project directory, start the server in the first terminal:

```bash
gradle bootRun
```

Once Spring Boot reports the server is listening on port 8080, run in a second terminal:

```bash
gradle runClient
```

If you have the Gradle Wrapper: `./gradlew bootRun` and `./gradlew runClient` on macOS/Linux, or `.\gradlew.bat bootRun` and `.\gradlew.bat runClient` on Windows PowerShell. **`gradlew` is not present by default** in a newly created project; generate the Gradle Wrapper or use an installed Gradle binary. These commands are meant for two separate terminals: the server must keep running while the client connects.

**Two lines printed by the client**, assuming the server runs on port 8080 and the handshake succeeds:

```text
selected=demo.v1
received=echo:hello
```

Gradle and HTTP/Tomcat/Spring may print additional logs that are not part of those two `System.out.println` lines. The server will also print lines like `OPEN protocol=demo.v1 client=cli` and `CLOSED code=1000` when the session ends normally; log ordering between the two terminals is not fixed. If port 8080 is already used by another app, configure `server.port` and update the client URL to match.

**Experiment A – pre-handshake rejection:** change the client URL to `ws://localhost:8080/ws/echo` (remove `?client=cli`). `beforeHandshake` returns 403; `buildAsync(...)` fails, and `afterConnectionEstablished` never runs. This differs from opening a connection and later receiving close code 1008.

**Experiment B – different subprotocol:** change `.subprotocols("demo.v1")` to `.subprotocols("unknown.v1")`. The sample server only supports `demo.v1`, so it cannot select `unknown.v1`. Depending on the container/client, the upgrade may proceed **with no subprotocol selected**, or the client may reject based on application requirements; inspect `getSubprotocol()` and the actual handshake. If your app *requires* a specific protocol, add explicit validation/enforcement rules.

**Experiment C – normal vs. abnormal close:** run the client normally to observe 1000. Then abruptly kill the network/process mid-session to see how transport errors or abnormal termination can occur without a normal close frame. Do not conclude a business error occurred solely from code 1006.

### 8.5 How can the HTTP handshake be observed?

Browser DevTools → **Network** → **WS** (or WebSocket) → select `/ws/echo`; inspect request/response handshake headers, negotiated protocol, and Frames/Messages. Display layouts differ between Chrome and Firefox; inspect the `Sec-WebSocket-Protocol` header and response status 101 when using HTTP/1.1 Upgrade.

On the JDK client, `WebSocket.getSubprotocol()` reflects the server's choice (empty string if no subprotocol was selected). To observe the transport-level handshake, enable debug logging on client/server or use packet capture **only in authorized test environments**, avoiding logging cookies/tokens. A standard WebSocket client does not automatically expose every handshake response header after the connection is established.

## 9. Authentication, Origin, Proxies, Resources, and Operations

### 9.1 WebSocket does not bypass Spring Security

- The HTTP handshake is an endpoint request and can pass through the security filter chain; decide which users are allowed to open `/ws/...`.
- Cookie/session vs. bearer token authentication must fit the environment. The browser WebSocket API does not allow setting arbitrary HTTP headers like `fetch()`; many applications rely on cookies or authenticate during STOMP CONNECT via a channel interceptor. Never move secret tokens into URL query parameters just for "easier debugging".
- `Origin` differs from CORS: WebSocket does not use regular CORS preflight like `fetch`, but Spring has dedicated origin checks. Non-browser clients can spoof Origin headers; **Origin is only an additional defense against cross-site WebSocket hijacking**, not identity authentication.
- For STOMP, session authentication and per-destination `SEND`/`SUBSCRIBE` authorization must also be checked even after a valid HTTP 101.
- Limit connections per user/IP, message sizes, idle time, fan-out, and send rates; never allow unbounded buffers.

### 9.2 Reverse proxies and load balancers

When using nginx or another reverse proxy, you must forward HTTP Upgrade and Connection headers, allow longer timeouts than typical HTTP requests, and configure TLS for `wss://`. A basic nginx example might look like:

```nginx
location /ws/ {
    proxy_pass http://127.0.0.1:8080;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_set_header Host $host;
    proxy_read_timeout 3600s;
}
```

This is an implementation fragment, not a complete reverse proxy configuration. Flexible `Connection` setups commonly use a `map` to avoid setting Upgrade when the request lacks the header; in production, configure TLS/security headers/health checks per infrastructure standards. `proxy_read_timeout` and load balancer timeouts must align with heartbeats and resource policies.

Multi-instance deployments must note: a WebSocket connection **is pinned to one node** for its lifetime; a load balancer does not split an open connection across multiple servers. To deliver messages to users connected to other nodes, you need a shared broker/pub-sub, STOMP broker relay, or suitable distribution infrastructure; sticky sessions alone do not create a distributed message bus.

### 9.3 Reliable lifecycle management

| Event | Do | Avoid |
| --- | --- | --- |
| Before handshake | Validate Origin/auth/path/limits; put minimal metadata into attributes | Treating `Sec-WebSocket-Key` nonce as authentication |
| Just OPEN | Record session ID/Principal, selected subprotocol, start time | Assuming STOMP is also CONNECTED |
| Receiving TEXT/BINARY | Parse, bound payload, check authorization, catch errors properly | Running long blocking I/O on I/O threads |
| Sending message | Check session open, buffer/send time limits, backpressure | Concurrent unsynchronized sends from multiple threads |
| Transport error | Log cause safely, close when possible, idempotent cleanup | Assuming a close frame and code 1000 always arrive |
| Normal close | Send valid close code, remove from session map, decrement metric once | Sending reserved code `1006` |
| Redeploy/shutdown | Drain/close sessions gracefully, let clients reconnect with jitter | Letting all clients reconnect immediately and causing a thundering herd |

### 9.4 Stage-by-stage debugging checklist

1. **No request reaches the server:** check `ws://`/`wss://` URL, DNS, TLS, port, proxy, and path.
2. **Request arrives but no 101:** check 400/401/403/404 response statuses, HTTP Upgrade headers, Origin, security filters, `HandshakeInterceptor`, and WebSocket version.
3. **101 returned then client rejects:** check `Sec-WebSocket-Accept`, selected subprotocol, extensions, and client library.
4. **WebSocket OPEN but no application messages:** check client subscribe/demand, handler binding, TEXT/BINARY message format, STOMP CONNECTED, and correct destination.
5. **Connection drops after idle period:** check heartbeats, proxy/load balancer/container idle timeouts, shutdowns, and network errors; do not guess the cause from 1006 alone.
6. **Memory/CPU grows with many clients:** monitor active connections, sessions, send buffers, event-loop/thread pools, subscription counts, message rates, and broker health.
7. **Clients reconnect continuously:** add backoff + jitter, check expired auth, protocol mismatches, rolling deployments, duplicate subscriptions, and state cleanup.

## 10. How Does WebFlux Differ from Spring MVC WebSocket?

This lesson uses the Servlet stack with `org.springframework.web.socket.WebSocketHandler` and `WebSocketSession`. WebFlux has an interface in a different namespace: `org.springframework.web.reactive.socket.WebSocketHandler` with method `Mono<Void> handle(WebSocketSession session)` and publishers `session.receive()`, `session.send(...)`. Handshakes in WebFlux are coordinated by `HandshakeWebSocketService`/`WebSocketHandlerAdapter`, not registered through MVC's `@EnableWebSocket` + `WebSocketConfigurer`.

Example **WebFlux fragment**:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.web.reactive.HandlerMapping;
import org.springframework.web.reactive.handler.SimpleUrlHandlerMapping;
import org.springframework.web.reactive.socket.WebSocketHandler;
import org.springframework.web.reactive.socket.server.support.WebSocketHandlerAdapter;
import reactor.core.publisher.Mono;

import java.util.Map;

@Bean
HandlerMapping webSocketMapping() {
    WebSocketHandler echo = session ->
            session.send(session.receive()
                    .map(message -> session.textMessage(
                            "echo:" + message.getPayloadAsText())));

    SimpleUrlHandlerMapping mapping = new SimpleUrlHandlerMapping();
    mapping.setOrder(-1);
    mapping.setUrlMap(Map.of("/ws/reactive", echo));
    return mapping;
}

@Bean
WebSocketHandlerAdapter webSocketHandlerAdapter() {
    return new WebSocketHandlerAdapter();
}
```

This snippet belongs inside a `@Configuration` class; it is not a standalone file. WebFlux does not have the same `afterConnectionEstablished`/`afterConnectionClosed` callbacks as MVC; the lifecycle is modeled through reactive stream termination/completion and session methods. However, the RFC 6455 rules for handshake, subprotocol, close, and transport remain the same underlying protocol. Do not mix imports between MVC and WebFlux `WebSocketHandler` or `WebSocketSession`.

## 11. Review Questions and Hands-On Scenarios

**Question 1.** Is seeing HTTP response `101 Switching Protocols` enough to conclude that a STOMP client has subscribed successfully?

**Answer:** No. 101 only confirms the WebSocket Upgrade; the client must still send STOMP CONNECT, receive CONNECTED, and send the corresponding SUBSCRIBE.

**Question 2.** A server only supports `chat.v1` but returns `Sec-WebSocket-Protocol: chat.v2` when the client only proposed `chat.v1`. Is that RFC-compliant?

**Answer:** No. The server may only select a subprotocol from the list proposed by the client; in this case `chat.v2` was not proposed.

**Question 3.** Why should `Sec-WebSocket-Key` not be used as proof that a client is logged in?

**Answer:** The key is a nonce used for handshake verification, not a credential; it does not bind a user identity or access rights.

**Question 4.** When should cookies/tokens/Origin be checked if you want to reject before 101?

**Answer:** In the HTTP security chain and/or `HandshakeInterceptor.beforeHandshake` / handshake handler, before the upgrade. Message authorization still needs to be checked after OPEN.

**Question 5.** Does seeing close code 1006 in client logs mean the server sent `Close(1006)`?

**Answer:** No. 1006 is an abnormal closure status reported by the API and is never sent inside a WebSocket close frame.

**Question 6.** Is a STOMP heartbeat the same as WebSocket Ping/Pong?

**Answer:** No. STOMP heartbeats belong to STOMP framing, whereas WebSocket Ping/Pong are RFC 6455 control frames. Both can assist with failure detection, but they do not directly replace each other.

**Question 7.** Does `HandshakeInterceptor.afterHandshake` replace `afterConnectionEstablished` in a raw Spring WebSocket handler?

**Answer:** No. The interceptor observes the handshake process; the handler callback only runs once the WebSocket connection has been established.

**Extended lab:** Starting from the example in section 8, try storing a non-sensitive correlation ID in session attributes, adding idle detection timeouts, rejecting clients with unsupported subprotocols, and tracking OPEN/CLOSED active sessions using a `ConcurrentHashMap` with idempotent cleanup. Demonstrate via logs and real requests that pre-101 rejection differs from opening a connection and then receiving a Close frame.

## Official References

- [RFC 6455 — The WebSocket Protocol](https://www.rfc-editor.org/rfc/rfc6455)
- [RFC 8441 — Bootstrapping WebSockets with HTTP/2](https://www.rfc-editor.org/rfc/rfc8441)
- [Spring Framework — WebSocket Overview](https://docs.spring.io/spring-framework/reference/web/websocket.html)
- [Spring Framework — WebSocket Server API and Handshake](https://docs.spring.io/spring-framework/reference/web/websocket/server.html)
- [Spring Framework — STOMP over WebSocket](https://docs.spring.io/spring-framework/reference/web/websocket/stomp.html)
- [Spring Framework — Enable STOMP](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/enable.html)
- [Spring Framework — WebFlux WebSocket](https://docs.spring.io/spring-framework/reference/web/webflux-websocket.html)
- [Spring Framework 6.1 — SubProtocolCapable Javadoc](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/web/socket/SubProtocolCapable.html)
