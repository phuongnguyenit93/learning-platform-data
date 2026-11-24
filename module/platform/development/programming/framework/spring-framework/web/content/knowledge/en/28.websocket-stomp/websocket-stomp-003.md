# WebSocketHandler, TextWebSocketHandler, and Servlet Endpoint Registration in Spring Framework

## Learning Objectives and Scope

This lesson explains how to build a **low-level WebSocket endpoint (raw WebSocket)** on the **Spring MVC / Servlet stack** using the `WebSocketHandler` interface, the `TextWebSocketHandler` utility class, and `@EnableWebSocket` + `WebSocketConfigurer` configuration. After studying it, you will be able to:

- Understand the flow **HTTP Upgrade handshake → WebSocketSession → message handling → connection close**.
- Distinguish between `WebSocketHandler` (the callback contract) and `TextWebSocketHandler` (a base class specialized for text messages).
- Register the `/ws/echo` endpoint on the Servlet stack, understanding the roles of `WebSocketHandlerRegistry`, `ServletWebSocketHandlerRegistry`, and the Servlet container.
- Build a Spring Boot/Java 17+ application with an echo server and an HTML page using a browser to connect and send/receive messages.
- Know where to place authentication, origin validation, session management, message limits, and synchronized sending when multiple threads write to a single WebSocket session.

**The primary scope is raw WebSocket on the Servlet stack.** STOMP is a messaging protocol layered on top of WebSocket and typically uses `@EnableWebSocketMessageBroker`, a broker, and `@MessageMapping`. Those STOMP components serve a different role and are not required to build the raw WebSocket endpoint in this lesson.

## 1. WebSocket Is Not Like REST HTTP Request/Response

Standard HTTP REST follows a one-request, one-response model. WebSocket starts with **one HTTP handshake** requesting a protocol upgrade, then transitions to a long-lived bidirectional connection: both server and client can send **frames** without opening a new HTTP request for every message.

Example path:

```text
Browser or WebSocket client
        |
        | HTTP GET /ws/echo
        | Upgrade: websocket
        | Connection: Upgrade
        | Sec-WebSocket-Key: ...
        | Sec-WebSocket-Version: 13
        v
Spring MVC HandlerMapping / WebSocketHttpRequestHandler
        |
        | valid handshake
        v
Servlet container upgrades connection
        |
        | HTTP 101 Switching Protocols
        v
WebSocketSession established
        |
        +--- client -> text frame ---> handleTextMessage(...)
        |
        +--- server -> text frame ---> WebSocketSession.sendMessage(...)
        |
        +--- close / transport error -> close/error callbacks
```

Key steps:

1. **URL registration:** Spring knows which WebSocket handler handles `/ws/echo`.
2. **Handshake:** HTTP Upgrade is validated, origins/interceptors are checked, and subprotocols or extensions are negotiated if present.
3. **Session:** Once the upgrade succeeds, both sides speak the WebSocket protocol; Spring provides a `WebSocketSession` representing the active connection.
4. **Message:** Callbacks receive text/binary/pong frames; the handler defines payload semantics itself.
5. **Close:** Both sides exchange close frames when possible; the server receives a close or transport error callback and cleans up resources.

Each connection has its own session. **One handler instance can handle many sessions**, so do not store per-connection user state in regular instance fields when the handler is a shared singleton bean.

### 1.1. HTTP and WebSocket URLs

In the local example, the web page is `http://localhost:8080/` while the WebSocket endpoint is `ws://localhost:8080/ws/echo`. When running over HTTPS, clients should connect with `wss://`. Unlike HTTP polling, after a successful upgrade there is no new HTTP status code per WebSocket message.

**HTTP 101** signals that the upgrade succeeded; thereafter data travels in text/binary frames. If a message is malformed, the application can send an error message as a frame or close the session with an appropriate close code; it does not "return HTTP 400 for a subsequent frame".

## 2. The WebSocketHandler Interface

Spring Servlet uses `org.springframework.web.socket.WebSocketHandler`. It is the contract of callbacks managing lifecycle and messages:

| Callback | When Spring calls it | Typical work |
| --- | --- | --- |
| `afterConnectionEstablished(WebSocketSession)` | Connection is established | Initialize context, record session, send greeting |
| `handleMessage(WebSocketSession, WebSocketMessage<?>)` | A message arrives | Dispatch text/binary/pong or handle generically |
| `handleTransportError(WebSocketSession, Throwable)` | Transport error occurs | Safe logging, close connection if still open, clean up resources |
| `afterConnectionClosed(WebSocketSession, CloseStatus)` | Connection has closed | Remove session from memory, release subscriptions/resources |
| `supportsPartialMessages()` | Framework queries fragmented message support | Return whether partial messages are supported |

The main callback signatures can throw `Exception`. If you implement the interface directly, you must implement all required methods. When only text is needed, extending `TextWebSocketHandler` is usually cleaner and clearer.

**Do not confuse two classes from different packages:**

- Servlet: `org.springframework.web.socket.WebSocketHandler`, `WebSocketSession`, `TextMessage`.
- Reactive WebFlux: `org.springframework.web.reactive.socket.WebSocketHandler`, `WebSocketSession`, and `WebSocketMessage`; the API uses Reactor `Mono<Void> handle(WebSocketSession)`.

Both stacks solve WebSocket, but **their interfaces are not directly interchangeable**. This lesson uses the Servlet stack exclusively and imports from `org.springframework.web.socket.*`.

### 2.1. WebSocketMessage and WebSocketSession

In raw Servlet WebSocket:

- `TextMessage` carries a UTF-8/text string payload, retrieved with `getPayload()`.
- `BinaryMessage` carries binary data (with `ByteBuffer` depending on the API).
- `PongMessage` represents a pong control message. Ping/pong may be managed by the container at a low level; when heartbeats are needed, design according to the container and protocol.
- `WebSocketSession` provides `getId()`, `getPrincipal()`, `getAttributes()`, `getHandshakeHeaders()`, `isOpen()`, `sendMessage(...)`, and `close(...)`.

`session.getAttributes()` is a map scoped to the WebSocket session that can hold data passed from a handshake interceptor. It is not automatically a full Spring HTTP session. `getPrincipal()` depends on whether the HTTP handshake was authenticated and populated a principal in the system.

## 3. TextWebSocketHandler: The Natural Choice for Text Frames

`TextWebSocketHandler` belongs to package `org.springframework.web.socket.handler`, extends `AbstractWebSocketHandler`, and handles text messages via:

```java
@Override
protected void handleTextMessage(WebSocketSession session,
                                 TextMessage message) throws Exception {
    String text = message.getPayload();
    session.sendMessage(new TextMessage("ECHO:" + text));
}
```

This is a **snippet inside a subclass**, not a standalone runnable Java file. When a client sends `hello`, the server sends `ECHO:hello` back to **the same session**. Other clients do not receive this frame because there is no broadcast mechanism.

`TextWebSocketHandler` inherits default lifecycle callbacks from `AbstractWebSocketHandler`. If a binary message arrives, this base handler rejects it with `CloseStatus.NOT_ACCEPTABLE`; therefore, do not use `TextWebSocketHandler` when an endpoint needs to upload or broadcast binary content unless you explicitly override its handling. When binary support is needed, see `BinaryWebSocketHandler` or implement an appropriate handler.

### 3.1. Lifecycle and resource cleanup

A handler typically also overrides:

```java
@Override
public void afterConnectionEstablished(WebSocketSession session)
        throws Exception {
    // Session can start receiving/sending WebSocket messages.
}

@Override
public void afterConnectionClosed(WebSocketSession session,
                                  CloseStatus status)
        throws Exception {
    // Clean up state, subscriptions, or session registry.
}

@Override
public void handleTransportError(WebSocketSession session,
                                 Throwable exception)
        throws Exception {
    // Log sanitized error; consider closing session.
}
```

**CloseStatus** uses WebSocket protocol codes. For example: 1000 = normal closure, 1008 = policy violation, 1009 = message too big, 1011 = server error. Do not pass HTTP status codes into `session.close(...)`.

### 3.2. Do you need to store every WebSocketSession?

- **Single-user echo:** no session map needed. Callbacks already receive `WebSocketSession`; reply to that session directly.
- **Chat/broadcast:** you need to manage a registry of open sessions (for example `ConcurrentHashMap`), remove them in close/error callbacks, and check `isOpen()` and receive permissions.
- **Multiple server instances:** an in-RAM registry only sees sessions on the current instance. System-wide broadcast requires fan-out via a broker/pub-sub or equivalent architecture; a local `ConcurrentHashMap` cannot represent cluster-wide connections.

## 4. Registering Endpoints on the Servlet Stack

The standard Spring MVC approach uses this configuration:

```java
@Configuration
@EnableWebSocket
public class WebSocketConfig implements WebSocketConfigurer {
    private final EchoTextWebSocketHandler echoHandler;

    public WebSocketConfig(EchoTextWebSocketHandler echoHandler) {
        this.echoHandler = echoHandler;
    }

    @Override
    public void registerWebSocketHandlers(WebSocketHandlerRegistry registry) {
        registry.addHandler(echoHandler, "/ws/echo");
    }
}
```

Imports for this snippet:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.web.socket.config.annotation.EnableWebSocket;
import org.springframework.web.socket.config.annotation.WebSocketConfigurer;
import org.springframework.web.socket.config.annotation.WebSocketHandlerRegistry;
```

Meaning:

- `@Configuration` declares a Spring configuration class.
- `@EnableWebSocket` enables raw WebSocket configuration infrastructure on the Servlet stack.
- `WebSocketConfigurer` is the callback for configuring WebSocket handler mappings.
- `WebSocketHandlerRegistry.addHandler(handler, paths...)` binds a handler instance to handshake URLs.
- Spring MVC uses its Servlet registry mechanism to create handler mappings and handshake handlers; applications generally do not instantiate `ServletWebSocketHandlerRegistry` manually.

`ServletWebSocketHandlerRegistry` is the `WebSocketHandlerRegistry` implementation used in Servlet environments, where paths are registered into Spring MVC handler mappings. It is an internal infrastructure/configuration class, **not a business handler** and not a REST controller.

### 4.1. Distinguishing registration mechanisms

| Mechanism | Purpose | When to use |
| --- | --- | --- |
| `@EnableWebSocket` + `WebSocketConfigurer` + `addHandler` | Raw WebSocket via Spring Servlet | Need direct handling of text/binary frames |
| `@EnableWebSocketMessageBroker` + `registerStompEndpoints` | STOMP over WebSocket | Have destinations, subscriptions, broker, `@MessageMapping` |
| Jakarta WebSocket `@ServerEndpoint("/...")` | Standard Jakarta WebSocket API | App intentionally chooses the Jakarta endpoint model |
| Reactive `HandlerMapping` + `WebSocketHandlerAdapter` | Raw WebSocket in WebFlux | App runs on the reactive HTTP stack |

Do not write `@GetMapping("/ws/echo")` returning a string to "register a WebSocket". A normal GET controller produces an HTTP response and does not upgrade the protocol. `@ServerEndpoint` is a separate mechanism; with an embedded Servlet container in Spring Boot it has its own registration requirements and is unnecessary for the `@EnableWebSocket` path in this lesson.

### 4.2. Position in the request flow

In Spring MVC, the handshake request `GET /ws/echo` passes through the Servlet container and is routed to the WebSocket handler mapping; Spring then uses a handshake handler such as `WebSocketHttpRequestHandler` along with `HandshakeHandler`/`RequestUpgradeStrategy` to upgrade the protocol. The container performs WebSocket I/O after the upgrade.

Responsibility diagram:

```text
DispatcherServlet / HandlerMappings (HTTP Upgrade GET)
         |
         v
WebSocket registration ("/ws/echo")
         |
         v
WebSocketHttpRequestHandler -> HandshakeHandler
         |
         v
Servlet container adapter upgrades protocol
         |
         v
WebSocketSession + WebSocketHandler callbacks
```

`DefaultHandshakeHandler` can be customized when you need custom subprotocol negotiation, origin rules, or upgrade strategies. For typical Servlet applications, the default registry configuration is sufficient.

## 5. Complete Runnable Example: Spring Boot WebSocket Echo

This example uses **Spring Boot 3.3.6, Java 17, and embedded Tomcat**, without Redis, STOMP, or a broker. The HTML page is served by Spring Boot from the same origin as the endpoint, making it easy to observe the difference between the initial HTTP connection and subsequent WebSocket frames.

**Project structure:**

```text
servlet-websocket-demo/
├── build.gradle
└── src/
    └── main/
        ├── java/demo/websocket/
        │   ├── ServletWebSocketDemoApplication.java
        │   ├── EchoTextWebSocketHandler.java
        │   └── WebSocketConfig.java
        └── resources/static/index.html
```

### 5.1. build.gradle

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.6'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '0.0.1-SNAPSHOT'

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
}
```

This starter provides WebSocket support for Spring MVC applications and the corresponding Servlet container environment. Gradle/Spring Boot manages compatible versions of Spring Framework, Jakarta Servlet, Tomcat, and websocket modules. Do not manually mix legacy `javax.websocket.*` artifacts into a Spring Boot 3 project (which uses `jakarta.*`).

### 5.2. ServletWebSocketDemoApplication.java

```java
package demo.websocket;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ServletWebSocketDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(ServletWebSocketDemoApplication.class, args);
    }
}
```

The main class bootstraps Spring Boot and component scanning in package `demo.websocket`. The `@Component` handler and `@Configuration` class below will be discovered by Spring.

### 5.3. EchoTextWebSocketHandler.java

```java
package demo.websocket;

import java.io.IOException;

import org.springframework.stereotype.Component;
import org.springframework.web.socket.CloseStatus;
import org.springframework.web.socket.TextMessage;
import org.springframework.web.socket.WebSocketSession;
import org.springframework.web.socket.handler.TextWebSocketHandler;

@Component
public class EchoTextWebSocketHandler extends TextWebSocketHandler {

    @Override
    public void afterConnectionEstablished(WebSocketSession session)
            throws IOException {
        session.sendMessage(new TextMessage("READY"));
    }

    @Override
    protected void handleTextMessage(WebSocketSession session,
                                     TextMessage message)
            throws IOException {
        String payload = message.getPayload();

        // Demo limit by Java String length; production also
        // needs byte/frame and buffer limits in the WebSocket container.
        if (payload.length() > 1024) {
            session.close(CloseStatus.TOO_BIG_TO_PROCESS);
            return;
        }

        session.sendMessage(new TextMessage("ECHO:" + payload));
    }

    @Override
    public void afterConnectionClosed(WebSocketSession session,
                                      CloseStatus status) {
        System.out.println("CLOSED " + status.getCode());
    }

    @Override
    public void handleTransportError(WebSocketSession session,
                                     Throwable exception)
            throws IOException {
        if (session.isOpen()) {
            session.close(CloseStatus.SERVER_ERROR);
        }
    }
}
```

Explanation of each callback:

1. Connection succeeds → `afterConnectionEstablished` sends `READY`.
2. Client sends text payload → `handleTextMessage` reads `message.getPayload()`.
3. If the string exceeds 1,024 UTF-16 code units in the example → closes session with 1009. This **is not a complete network byte limit**, because Unicode characters have varying UTF-8 byte lengths; real protection requires configuring container limits.
4. If valid → sends `ECHO:` plus the payload back to **that same client**.
5. Connection closes → Spring calls `afterConnectionClosed`. Prints the close code for observation; in real apps, clean up registries/subscriptions here.
6. Transport error → attempts to close the still-open session with 1011. If background work exists, the handler must clean up related resources rather than only closing the socket.

**Why doesn't the handler hold the session in a field?** Because this example replies immediately to the session received in the callback. One handler bean can serve many connections; adding a field like `private WebSocketSession currentSession;` would cause clients to overwrite one another's sessions.

### 5.4. WebSocketConfig.java

```java
package demo.websocket;

import org.springframework.context.annotation.Configuration;
import org.springframework.web.socket.config.annotation.EnableWebSocket;
import org.springframework.web.socket.config.annotation.WebSocketConfigurer;
import org.springframework.web.socket.config.annotation.WebSocketHandlerRegistry;

@Configuration
@EnableWebSocket
public class WebSocketConfig implements WebSocketConfigurer {

    private final EchoTextWebSocketHandler echoHandler;

    public WebSocketConfig(EchoTextWebSocketHandler echoHandler) {
        this.echoHandler = echoHandler;
    }

    @Override
    public void registerWebSocketHandlers(WebSocketHandlerRegistry registry) {
        registry.addHandler(echoHandler, "/ws/echo");
        // Default same-origin policy fits this demo.
    }
}
```

This is the **Servlet endpoint registration** step: `/ws/echo` is mapped to the handler bean. Ensure the configuration is component-scanned by Spring; here the package matches `@SpringBootApplication`'s package.

### 5.5. src/main/resources/static/index.html

This static HTML page is served by Spring Boot at `http://localhost:8080/`. The user clicks "Connect", sends a text string, and watches the receive log. JS automatically picks `ws:` or `wss:` matching the page's protocol.

```html
<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8">
  <title>Spring Servlet WebSocket Echo</title>
  <style>
    body { font-family: system-ui, sans-serif; max-width: 760px;
           margin: 32px auto; padding: 0 16px; }
    button, input { padding: 8px; margin: 4px 0; }
    #events { white-space: pre-wrap; padding: 12px;
              background: #f3f4f6; min-height: 180px; }
  </style>
</head>
<body>
  <h1>Raw WebSocket Echo</h1>
  <button id="connect">Connect</button>
  <button id="close" disabled>Close</button>
  <p>
    <input id="message" value="hello" aria-label="Message">
    <button id="send" disabled>Send</button>
  </p>
  <pre id="events" aria-live="polite"></pre>

  <script>
    const connectButton = document.querySelector("#connect");
    const closeButton = document.querySelector("#close");
    const sendButton = document.querySelector("#send");
    const input = document.querySelector("#message");
    const output = document.querySelector("#events");

    let socket = null;

    function log(message) {
      output.textContent += message + "\n";
    }

    connectButton.addEventListener("click", () => {
      const scheme = location.protocol === "https:" ? "wss:" : "ws:";
      const url = scheme + "//" + location.host + "/ws/echo";
      socket = new WebSocket(url);

      connectButton.disabled = true;

      socket.onopen = () => {
        log("OPEN");
        sendButton.disabled = false;
        closeButton.disabled = false;
      };

      socket.onmessage = event => {
        log("RECV " + event.data);
      };

      socket.onerror = () => {
        log("ERROR");
      };

      socket.onclose = event => {
        log("CLOSE " + event.code);
        connectButton.disabled = false;
        sendButton.disabled = true;
        closeButton.disabled = true;
        socket = null;
      };
    });

    sendButton.addEventListener("click", () => {
      if (socket && socket.readyState === WebSocket.OPEN) {
        socket.send(input.value);
        log("SEND " + input.value);
      }
    });

    closeButton.addEventListener("click", () => {
      if (socket && socket.readyState === WebSocket.OPEN) {
        socket.close(1000, "done");
      }
    });
  </script>
</body>
</html>
```

Using `textContent` to display responses ensures payloads like `<script>` are not interpreted as HTML. When displaying messages from other users, never concatenate them into `innerHTML` without safe sanitization.

### 5.6. How to Run and Observe

From the directory containing `build.gradle`, with JDK 17+ and a suitable Gradle installed, run:

```bash
gradle bootRun
```

If you generated the Gradle Wrapper, use `./gradlew bootRun` (Unix/macOS) or `gradlew.bat bootRun` (Windows).

1. Open `http://localhost:8080/` in your browser.
2. Click **Connect**, and observe `OPEN` and the `READY` message sent by the server.
3. Keep the input `hello` and click **Send**.
4. Observe the browser showing `SEND hello` and `RECV ECHO:hello`.
5. Click **Close**, and observe `CLOSE 1000` in the browser and `CLOSED 1000` in the server application's stdout when the close callback runs.

**Expected lines produced by the app in the UI, in the sequence of actions above** (startup logs, network timing, and close events may produce additional entries):

```text
OPEN
RECV READY
SEND hello
RECV ECHO:hello
CLOSE 1000
```

Not all of the lines above are Java stdout; they are the output from the demo page's `<pre id="events">` element. Java only prints `CLOSED 1000` on normal close. If the handshake fails or uses a different origin, you may see `ERROR`/`CLOSE 1006` in the browser; 1006 is the status reported by the browser for connection loss, not a close frame sent by the server.

### 5.7. Which Components Does a Real Request Traverse?

When clicking **Connect**:

```text
new WebSocket("ws://localhost:8080/ws/echo")
  -> browser sends HTTP Upgrade
  -> Tomcat accepts connection
  -> DispatcherServlet resolves mapping /ws/echo
  -> Spring handshake + Servlet WebSocket upgrade
  -> HTTP 101
  -> EchoTextWebSocketHandler.afterConnectionEstablished
  -> session.sendMessage("READY")
  -> browser.onmessage receives READY
```

When clicking **Send**:

```text
browser.socket.send("hello")
  -> WebSocket text frame on existing connection
  -> EchoTextWebSocketHandler.handleTextMessage
  -> message.getPayload() == "hello"
  -> session.sendMessage(TextMessage("ECHO:hello"))
  -> browser.onmessage receives "ECHO:hello"
```

After the upgrade, **there are no additional Servlet HTTP GETs per frame**. Normal REST controllers or HTTP filters are not re-invoked whenever a WebSocket message is sent. If per-command authorization is needed in raw WebSocket, place those checks in the message-handling logic or corresponding service layer.

## 6. HandshakeInterceptor, Origin, and Authentication

The handshake begins as an HTTP request, so it can carry headers, cookies, authentication info, query parameters, and origin. Spring provides `HandshakeInterceptor` with two callbacks: `beforeHandshake(...)` and `afterHandshake(...)`.

Extended configuration example (this is an **illustrative variant**; replace the registration method in `WebSocketConfig.java` above if applying it):

```java
@Override
public void registerWebSocketHandlers(WebSocketHandlerRegistry registry) {
    registry.addHandler(echoHandler, "/ws/echo")
            .addInterceptors(new HttpSessionHandshakeInterceptor())
            .setAllowedOrigins("https://app.example.com");
}
```

Also import `org.springframework.web.socket.server.support.HttpSessionHandshakeInterceptor`.

- `HttpSessionHandshakeInterceptor` can copy HTTP session attributes into the WebSocket session's attributes map. It **does not replace authentication**.
- `setAllowedOrigins(...)` permits only declared browser origins; in production, set exact origins for authorized frontends.
- `setAllowedOriginPatterns(...)` supports flexible patterns, but domains must still be strictly bounded.
- If the application serves both HTML pages and WebSocket on the same host/port, the default same-origin policy is appropriate.
- Do not treat `Origin` as an authentication mechanism: non-browser clients can set this header arbitrarily. You must still authenticate callers and check permissions.

**Watch out with the example:** if you replace the config with `setAllowedOrigins("https://app.example.com")` while still opening the demo from `http://localhost:8080/`, the browser's handshake will be rejected because the origin is not in the allowlist. To run the local demo, keep the original config or explicitly add the matching local origin.

### 6.1. When a custom HandshakeInterceptor is needed

You can create an interceptor to inspect state before accepting the upgrade:

```java
public final class AttributeHandshakeInterceptor
        implements HandshakeInterceptor {

    @Override
    public boolean beforeHandshake(
            ServerHttpRequest request,
            ServerHttpResponse response,
            WebSocketHandler wsHandler,
            Map<String, Object> attributes) {

        attributes.put("connectedAt", java.time.Instant.now());
        return true;
    }

    @Override
    public void afterHandshake(
            ServerHttpRequest request,
            ServerHttpResponse response,
            WebSocketHandler wsHandler,
            Exception exception) {
        // Release resources or record metrics if needed.
    }
}
```

This is an **illustrative snippet to place in a file in the same package with imports**:
`org.springframework.web.socket.server.HandshakeInterceptor`,
`org.springframework.http.server.ServerHttpRequest`,
`org.springframework.http.server.ServerHttpResponse`,
`org.springframework.web.socket.WebSocketHandler`,
`java.util.Map`.

Register it via `.addInterceptors(new AttributeHandshakeInterceptor())`. After handshake, read `session.getAttributes().get("connectedAt")` in the handler. If `beforeHandshake` returns `false`, Spring halts the upgrade; the response should be configured appropriately when rejecting.

**Security:** If session cookies are used to authenticate WebSocket connections from browsers automatically, validate Origin and user/room/resource authorization to prevent Cross-Site WebSocket Hijacking. Behind a reverse proxy, forward Upgrade/Connection headers and WSS accurately, and ensure proper session/routing handling.

## 7. Concurrent Sending and Proper Session Management

Typically a session belongs to one TCP/WebSocket connection. Multiple threads calling `session.sendMessage(...)` concurrently can cause races or errors in Jakarta WebSocket-compliant containers. Spring recommends **synchronizing sends** when multiple producers emit messages.

One approach is wrapping the session with `ConcurrentWebSocketSessionDecorator`:

```java
WebSocketSession safeSession =
        new ConcurrentWebSocketSessionDecorator(
                rawSession,
                10_000,       // send time limit, ms
                64 * 1024);   // send buffer limit, bytes
```

Import `org.springframework.web.socket.handler.ConcurrentWebSocketSessionDecorator`. This is a **snippet** assuming `rawSession` is available in a callback; do not paste it into the demo file without designing an appropriate registry lifecycle.

The decorator ensures only one thread performs a direct send at a time; subsequent sends are buffered. Exceeding the time or buffer limit triggers overflow behavior / session closure as configured. It **is not a message broker** and does not synchronize sessions across server nodes.

### 7.1. Broadcast registry

If building a chat room, you need a structure like:

```java
private final Map<String, WebSocketSession> sessions =
        new ConcurrentHashMap<>();
```

Add the session in `afterConnectionEstablished`, remove it in `afterConnectionClosed` and error paths; when broadcasting, check that each session is still open, verify subscription permissions, and send sequentially or via the decorator. When using the decorator, **store the wrapped session in the registry once** and use that exact instance for sending; do not wrap a new decorator per frame and assume sends are synchronized.

**This is an additional design**, not needed for the runnable echo program above. Avoid broadcasting to every session without checking rooms, users, and authorization, as that can leak data across users.

### 7.2. Backpressure and resource limits

The raw Servlet WebSocket API is callback-based and does not natively provide Reactor `Flux`-style reactive backpressure. To protect the server, design:

- Limits on inbound text/binary message sizes and total connections.
- Limits on outbound queues, send times, broadcast fan-out, and per-user message rates.
- Closing slow/invalid sessions and cleaning up the session registry.
- Idle timeouts/heartbeats aligned with the container and load balancer.
- Avoiding logging sensitive payloads, validating message schemas, and checking authorization on **every critical command**.

The `payload.length() > 1024` check in the demo only illustrates application-level validation; oversized messages may be rejected by the container **before reaching the callback**. For Servlet containers using Jakarta WebSocket, Spring provides `ServletServerContainerFactoryBean` to configure buffers and timeouts:

```java
@Bean
ServletServerContainerFactoryBean webSocketContainer() {
    ServletServerContainerFactoryBean container =
            new ServletServerContainerFactoryBean();
    container.setMaxTextMessageBufferSize(8192);
    container.setMaxBinaryMessageBufferSize(8192);
    return container;
}
```

Import `org.springframework.context.annotation.Bean` and `org.springframework.web.socket.server.standard.ServletServerContainerFactoryBean`. This is optional configuration placed inside a `@Configuration` class; buffer sizes and timeouts should match real payloads and the Servlet container in use.

## 8. Raw WebSocket vs. STOMP over WebSocket

This lesson handles `TextMessage` directly. When a client sends `hello`, the handler interprets it by application convention and replies `ECHO:hello`. Spring **does not automatically add destinations, subscriptions, or a broker** when registering `registry.addHandler(echoHandler, "/ws/echo")`.

STOMP is an application-level protocol with commands like `CONNECT`, `SUBSCRIBE`, `SEND`, and destinations. When building STOMP over WebSocket with Spring, you typically configure `@EnableWebSocketMessageBroker`, `StompEndpointRegistry`, and a message broker. STOMP clients send frames with STOMP headers/bodies rather than arbitrary raw text.

| Feature | Raw WebSocketHandler | STOMP over WebSocket |
| --- | --- | --- |
| Endpoint registration | `WebSocketConfigurer.registerWebSocketHandlers` | `WebSocketMessageBrokerConfigurer.registerStompEndpoints` |
| Receiving data | `handleTextMessage` or `handleMessage` callback | Broker/messaging routing and `@MessageMapping` |
| Message format | Defined by the application | STOMP frames with commands and headers |
| Broadcast | Manual session/room/queue management | Built-in broker destination mechanism |
| Best suited for | Echo, custom protocols, bespoke data streams | Chat/pub-sub with destinations and subscriptions |

**Do not mismatch them:** A STOMP-configured client will not communicate properly with a raw echo handler if the server lacks STOMP frame parsing. Conversely, a raw browser WebSocket sending the string `hello` is not a valid STOMP `SEND` command.

## 9. Real-World Errors and How to Diagnose Them

### 9.1. Handshake fails, never reaches handleTextMessage

Check step by step:

1. Is the URL `/ws/echo` exact, with no port, context-path, or reverse proxy mismatch?
2. Is the client using `ws://` for HTTP and `wss://` for HTTPS?
3. Are `@EnableWebSocket` and `WebSocketConfigurer` included in component scanning?
4. On the Servlet stack, are container WebSocket support and dependencies present?
5. Is the browser `Origin` permitted by policy?
6. Are HTTP auth/filters/proxies blocking the GET Upgrade or stripping `Connection`/`Upgrade` headers?
7. Is another controller route, servlet mapping, or endpoint occupying the same path?

In DevTools → Network → WS, a successful handshake normally displays **101 Switching Protocols**. If you get 400/401/403/404/500, clearly distinguish **pre-upgrade failures** from **post-upgrade close codes**.

### 9.2. Connection succeeds but no data arrives

- The client only created `new WebSocket(...)` without calling `send(...)`.
- The handler did not properly override `handleTextMessage(WebSocketSession, TextMessage)`.
- The server sent the response to the wrong session or an already-closed session.
- The client emitted or missed a message before attaching `onmessage` (attach callbacks immediately after creating the socket).
- The message is binary while the handler only expects text.
- Concurrent sends from multiple threads collided. Serialize sends.
- The client closed the tab or a proxy dropped the connection due to idle timeout.

### 9.3. Misunderstanding scope and lifecycle

Never store a single `WebSocketSession` in a shared mutable field like `currentSession` on a singleton handler to represent all users. Reconnecting users receive new sessions, and old sessions can close at any time. For broadcast registries, always clean up in lifecycle callbacks so dead sessions are not retained indefinitely.

### 9.4. Confusing HTTP errors with WebSocket errors

- HTTP 101 = handshake upgraded.
- WebSocket close 1000 = normal closure.
- Close 1009 = message too big.
- Close 1011 = server error.
- Browsers may report 1006 on abnormal connection loss; 1006 is not a close frame code sent over the wire.

Do not return JSON HTTP 404 from `handleTextMessage` after upgrading; to represent business errors, use an application message schema with error codes or close the WebSocket per contract.

### 9.5. Forgetting security or treating Origin as authentication

Allowed origins are a defense for browser handshakes, not a substitute for authentication. WebSocket connections can outlive user permission changes, so consider validating sessions, token expiration, room permissions, rate limits, and connection revocation. Avoid putting tokens in query parameters whenever possible because URLs are frequently logged; design an appropriate authentication scheme for browsers (cookies/sessions over HTTPS with CSRF/origin protections, or carefully designed token mechanisms).

## 10. Practice Exercises

**Exercise 1 — Track lifecycle:** Run the demo and connect from two browser tabs. Each tab receives `READY`. Send `hello A` in tab A. Explain why tab B does not receive `ECHO:hello A`. Close tab A and observe the close callback.

**Exercise 2 — Add a command:** In `handleTextMessage`, if the payload is exactly `PING`, reply `PONG` as an application-level message; for other strings, continue replying `ECHO:...`. Note that this is an **application text message**, not a WebSocket protocol-level Ping/Pong control frame.

**Exercise 3 — Test limits:** Send a text longer than 1,024 Java characters but below the container frame limit. Predict which close code the browser receives. Change the container buffer configuration and analyze why failures can happen before the callback runs.

**Exercise 4 — Origin and handshake:** Add `setAllowedOrigins("https://app.example.com")` and retry the `http://localhost:8080/` page. Predict why the handshake is rejected. Restore the same-origin configuration for the demo before continuing.

**Exercise 5 — Design broadcast:** Without writing the full code, describe where sessions are added/removed in lifecycle callbacks, where message receive permissions are checked, and why `sendMessage` must be synchronized when multiple producers emit messages.

## Key Takeaways

- `WebSocketHandler` is the contract for lifecycle and message callbacks.
- `TextWebSocketHandler` is the appropriate base class for handling raw WebSocket **text frames** on the Servlet stack.
- `@EnableWebSocket` + `WebSocketConfigurer` + `WebSocketHandlerRegistry.addHandler(...)` registers handshake URLs; Servlet infrastructure and Spring handle upgrading the connection.
- After HTTP 101, data is processed as WebSocket frames without going through REST controllers for each message.
- A `WebSocketSession` belongs to a single connection, while a handler bean can serve many users.
- When broadcast, authentication, resource limits, multithreading, or multiple server instances are needed, you must add lifecycle management, access control, and synchronized sends.
- Raw WebSocket and STOMP use different configuration and handler classes; they are not interchangeable without an agreed-upon protocol.

## References

- Spring Framework — WebSocket API (Servlet): https://docs.spring.io/spring-framework/reference/web/websocket/server.html
- Spring Framework — WebSockets on Servlet Stack: https://docs.spring.io/spring-framework/reference/web/websocket.html
- Spring Framework — `WebSocketHandler` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/web/socket/WebSocketHandler.html
- Spring Framework — `TextWebSocketHandler` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/web/socket/handler/TextWebSocketHandler.html
- Spring Framework — `ConcurrentWebSocketSessionDecorator`: https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/web/socket/handler/ConcurrentWebSocketSessionDecorator.html
- Spring Boot — WebSockets: https://docs.spring.io/spring-boot/3.3/reference/messaging/websockets.html
