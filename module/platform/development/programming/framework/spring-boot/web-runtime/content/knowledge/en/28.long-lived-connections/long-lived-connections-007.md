# Distinguishing Raw WebSocket from STOMP and Support Scope per Stack

## 1. Learning Objectives and Core Ideas

In Spring Boot applications requiring real-time data updates, two terms frequently appear together: **WebSocket** and **STOMP**. They are not synonyms.

- **WebSocket** is a bidirectional (full-duplex) transport protocol over a long-lived connection. It defines the handshake, text/binary frames, ping/pong, and connection closure—**it does not itself define** what the string `"chat"` or a JSON payload means.
- **STOMP** (Simple Text Oriented Messaging Protocol) is a **higher-layer messaging protocol** with `CONNECT`, `SUBSCRIBE`, `SEND`, `MESSAGE`, `ACK` commands, destinations, subscriptions, headers, and heartbeats. It can run **over WebSocket or directly over TCP**, and is not a "different version" of WebSocket.
- **Spring MVC/Servlet** supports both raw WebSocket handlers **and** STOMP-over-WebSocket via Spring Framework's message broker infrastructure.
- **Spring WebFlux** supports reactive WebSocket via `WebSocketHandler` and `Mono/Flux`. The **Servlet MVC-style STOMP message broker integration** (`@EnableWebSocketMessageBroker`, `@MessageMapping` with MVC's broker channels) **is not automatically available in WebFlux** merely by adding the WebFlux starter. If you want STOMP in a reactive architecture, build/adopt a suitable parser/broker adapter/library or run a dedicated messaging service.

This lesson belongs to the **Long-lived connections** group in the **Spring Boot - web-runtime** module. After completing it, you will be able to:

1. Explain the WebSocket handshake, `ws://`/`wss://`, and how it differs from standard HTTP request–response.
2. Read a STOMP frame and distinguish WebSocket messages from STOMP `destination` and subscriptions.
3. Choose raw WebSocket for small custom protocols and STOMP when routing, pub/sub, and broker semantics are needed.
4. Run a **Java 17 / Spring Boot 3.3.5** example with both a raw echo endpoint and a STOMP endpoint in **Spring MVC**.
5. Understand how to use reactive `WebSocketHandler` in **WebFlux** in a separate project.
6. Distinguish the in-memory simple broker from a RabbitMQ/ActiveMQ broker relay, including scale, persistence, acknowledgment, and clustering limits.
7. Test connections and secure handshakes/Origins, user identity, message authorization, proxy upgrades, heartbeats, buffers, timeouts, and common errors.

**Quick rule of thumb:** WebSocket solves **the transport channel**; STOMP solves **structure, destinations, and message routing** running over that channel.

## 2. What Is Raw WebSocket?

In raw WebSocket mode, a browser or client opens a connection:

~~~javascript
const socket = new WebSocket("ws://localhost:8080/ws/raw");

socket.onopen = () => socket.send("hello");
socket.onmessage = event => console.log(event.data);
socket.onclose = event => console.log(event.code, event.reason);
socket.onerror = () => console.log("WebSocket transport error");
~~~

This snippet is **browser code**; it works only when the server has registered `/ws/raw`. There is no built-in rule that `hello` must be echoed, saved to a DB, or broadcast to other users. Server and client must agree on their own "application protocol": plain text strings, JSON envelopes, or a binary format.

### 2.1. Handshake and HTTP Upgrade

A WebSocket over HTTP/1.1 typically starts with an upgrade request:

~~~http
GET /ws/raw HTTP/1.1
Host: localhost:8080
Upgrade: websocket
Connection: Upgrade
Sec-WebSocket-Key: <random-base64>
Sec-WebSocket-Version: 13
Origin: http://localhost:8080
~~~

If the server accepts, the typical response is:

~~~http
HTTP/1.1 101 Switching Protocols
Upgrade: websocket
Connection: Upgrade
Sec-WebSocket-Accept: <computed-value>
~~~

After the handshake, both sides exchange **WebSocket frames** over that connection. Bracketed values are illustrative, not literal bytes to send. `Sec-WebSocket-Accept` is computed per RFC 6455 rules, not chosen arbitrarily.

- `ws://` is WebSocket without TLS, suitable for localhost labs.
- `wss://` is WebSocket over TLS, normally required when the frontend is served over HTTPS.
- The initial HTTP request is for the handshake; afterward, each application message is **not** a separate HTTP request returning status 200.
- WebSocket is full-duplex: either side can initiate sending messages while the connection stays open.
- WebSocket has text, binary, and control (ping/pong/close) frames; the base protocol knows nothing about `/topic` or `@MessageMapping`.

**Caution with HTTP/2:** WebSocket over HTTP/2 has a separate extended CONNECT specification (RFC 8441), yet do not assume every proxy, client, container, or Spring Boot setup enables it automatically. The lab uses HTTP/1.1 upgrade for straightforward inspection. A site serving static assets over HTTP/2 can still perform HTTP/1.1 WebSocket upgrades via a proxy.

### 2.2. WebSocket Is Transport, Not Application Messaging

If you send JSON:

~~~json
{"type":"chat","room":"general","body":"Hello"}
~~~

Spring's raw WebSocket handler receives a **text message containing JSON**, yet by default **does not route** it to subscribers of room `general`, does not interpret `type=chat`, and provides no built-in broker. To support chat, subscribe, replay, or acks, the team must design and implement those rules themselves.

If sending binary bytes, client and server must also agree on serialization, versioning, size limits, and malformed-payload handling. Raw WebSocket offers flexibility at the cost of owning the protocol yourself.

## 3. What Is STOMP and At Which Layer Does It Run?

STOMP is a frame-based messaging protocol. In STOMP-over-WebSocket:

~~~text
Browser / STOMP client
        |
        | HTTP handshake upgrading to WebSocket
        v
WebSocket connection
        |
        | WebSocket text/binary message
        | carrying a STOMP frame payload
        v
STOMP decoder + message routing
        |
        +--> /app/...   -> @MessageMapping handlers
        '--> /topic/... -> broker/subscribers
~~~

STOMP defines commands and headers. A STOMP frame looks like:

~~~text
COMMAND
header-name:header-value
other-header:other-value

body<NULL>
~~~

A blank line separates headers from the body; a **NUL byte (0x00)** acts as the frame terminator per the STOMP specification. Documentation often writes `^@` or `\0` as notation. This is **not** a JSON line and not a raw WebSocket frame header; STOMP lives inside the payload of WebSocket messages.

Basic commands:

| Command | Meaning |
| --- | --- |
| `CONNECT` / `STOMP` | Client initiates a STOMP session, declaring version, heartbeat, host |
| `CONNECTED` | Server accepts the STOMP session |
| `SUBSCRIBE` | Client subscribes to receive messages at a destination |
| `UNSUBSCRIBE` | Removes a subscription |
| `SEND` | Client sends a message to a destination |
| `MESSAGE` | Server/broker delivers a message to a subscriber |
| `ACK` / `NACK` | Acknowledges or negatively acknowledges delivery when broker/mode supports it |
| `DISCONNECT` | Cleanly ends the STOMP session |
| `ERROR` | Broker/server reports a protocol or processing error |
| `BEGIN`/`COMMIT`/`ABORT` | STOMP transactions when supported by the broker |

STOMP 1.2 also defines **heart-beating**, subscription IDs, `receipt`, and `content-length`. Not every broker or implementation supports every command; verify capabilities against your actual server.

### 3.1. Illustrative Frames

Client starts STOMP after WebSocket opens:

~~~text
CONNECT
accept-version:1.2
host:localhost
heart-beat:0,0

^@
~~~

Server may reply:

~~~text
CONNECTED
version:1.2
heart-beat:0,0

^@
~~~

Client subscribes for updates:

~~~text
SUBSCRIBE
id:sub-0
destination:/topic/echo
ack:auto

^@
~~~

Client sends a message to application logic:

~~~text
SEND
destination:/app/echo
content-type:application/json

{"text":"Hello"}^@
~~~

Server via broker delivers to the subscription:

~~~text
MESSAGE
subscription:sub-0
destination:/topic/echo
message-id:<broker-generated>

{"text":"stomp: Hello"}^@
~~~

These snippets use `^@` to represent the NUL byte; in real code, send `\0`/`\u0000`, **never the two characters `^` and `@`**. Header names and IDs vary by broker and version. An actual `MESSAGE` frame may also include `content-type`, `content-length`, or additional headers.

**STOMP can run directly over TCP**. WebSocket is not mandatory for STOMP under the protocol spec. Spring MVC commonly uses STOMP over WebSocket so browsers can connect easily; Spring's broker relay can speak STOMP over TCP to an external broker.

## 4. Comparing Raw WebSocket and STOMP-over-WebSocket

| Aspect | Raw WebSocket | STOMP over WebSocket |
| --- | --- | --- |
| Protocol layer | WebSocket transport | STOMP messaging layered atop WebSocket |
| Message structure | Application-defined | Frames with command/headers/destination |
| Destination routing | Custom implementation | Built-in routing semantics |
| Subscribe / publish | Custom design | `SUBSCRIBE` / `SEND`, broker emits `MESSAGE` |
| Typical MVC controller API | `TextWebSocketHandler` or `WebSocketHandler` | `@MessageMapping`, `@SendTo`, `SimpMessagingTemplate` |
| Typical MVC config | `@EnableWebSocket` + `WebSocketConfigurer` | `@EnableWebSocketMessageBroker` + `WebSocketMessageBrokerConfigurer` |
| Broker | None built in | In-memory simple broker or external broker relay |
| Binary payload | Yes (WebSocket binary frames) | STOMP payloads can be text/binary depending on converter/client/broker |
| Heartbeat | WebSocket ping/pong or app heartbeat | STOMP heartbeat; can combine with transport keepalive |
| ACK / receipt | Custom-defined | Defined by STOMP, though Spring's simple broker supports only a subset |
| JavaScript client | Native `WebSocket` suffices for custom protocols | Usually `@stomp/stompjs` or a STOMP client library |
| Overhead | Low with a minimal protocol | Adds frame headers, parsing, and broker routing |
| Best suited for | Echo, custom games/interactions, binary, small protocols | Chat rooms, notifications, pub/sub, topic/user destinations |
| Scaling across instances | You design the message bus | Simple broker does not cluster either; external broker relay fits better |

**Do not assume STOMP is inherently more reliable.** STOMP defines how to express subscribe and ACK semantics, whereas **durability, replay, delivery guarantees, and offline queues** depend on the broker, configuration, topology, and client logic. Spring's simple broker is not automatically a Kafka/RabbitMQ durable queue.

## 5. Support Matrix by Spring Boot Web Stack

Spring Framework has two primary web stacks: **Servlet/MVC** and **reactive/WebFlux**. Both support WebSocket; framework-integrated STOMP message brokering in the Spring MVC style belongs specifically to the Servlet stack.

| Capability | Spring MVC / Servlet | Spring WebFlux / Reactive |
| --- | --- | --- |
| HTTP endpoints | `@RestController`, MVC `HandlerMapping` | Reactive controllers, `RouterFunction` |
| Raw WebSocket server | `org.springframework.web.socket.WebSocketHandler`; `TextWebSocketHandler` | `org.springframework.web.reactive.socket.WebSocketHandler`; `Mono<Void>` |
| WebSocket session | `org.springframework.web.socket.WebSocketSession` | `org.springframework.web.reactive.socket.WebSocketSession` |
| Receiving messages | Callbacks like `handleTextMessage` | `session.receive(): Flux<WebSocketMessage>` |
| Sending messages | `session.sendMessage(...)` | `session.send(Publisher<WebSocketMessage>)` |
| Mapping raw WebSocket URL | `@EnableWebSocket` / `WebSocketConfigurer` | `SimpleUrlHandlerMapping` and `WebSocketHandlerAdapter` |
| Built-in STOMP message broker | **Yes**: `@EnableWebSocketMessageBroker` | **No automatic equivalent in WebFlux** |
| `@MessageMapping` STOMP with broker | **Yes** via Spring messaging infrastructure | Not automatically enabled via WebFlux handlers |
| Built-in simple broker / STOMP relay | **Yes**, in MVC STOMP configuration | Not a built-in reactive broker module like MVC |
| SockJS fallback in Spring STOMP | Yes when `.withSockJS()` is configured | No equivalent automatic messaging-broker config |
| Event loop / backpressure | Mostly Servlet threads + WebSocket session send semantics | Reactor `Flux/Mono`, buffer/backpressure management |
| Illustrative dependency | `spring-boot-starter-web` + `spring-boot-starter-websocket` | `spring-boot-starter-webflux` and server-appropriate WebSocket APIs |

**Important boundary:** "WebFlux lacks MVC's built-in STOMP broker" **does not mean STOMP is forbidden in WebFlux**. You can still parse STOMP frames inside a custom `WebSocketHandler`, integrate another STOMP library, run a separate STOMP/messaging service, or use a bridge/broker. What you cannot do is drop `@EnableWebSocketMessageBroker` into a WebFlux project expecting the framework to spin up MVC's message broker.

**Choose your stack based on running code, not accidental libraries.** When Spring Boot 3.3 sees both `spring-boot-starter-web` and `spring-boot-starter-webflux` on the classpath, Boot normally picks **Servlet MVC** by default. Using reactive `WebClient` inside MVC does not switch the app to WebFlux.

## 6. How WebSocket, STOMP, SockJS, SSE, and RSocket Differ

| Technology | Primary Model | When to Consider |
| --- | --- | --- |
| WebSocket | Full-duplex, long-lived connection | Custom chat, interactive UI, real-time binary |
| STOMP over WebSocket | Message commands + pub/sub + destinations over WebSocket | Need broker routing, subscriptions, Spring MVC STOMP |
| SockJS | Transport fallback when native WebSocket is unavailable or blocked | Compatibility with restrictive environments/browsers/proxies |
| Server-Sent Events (SSE) | **One-way server-to-client** HTTP streaming | Notifications/streams strictly server→browser with rare upstream actions |
| Long polling | Repeated HTTP requests to fetch events | Fallback or clients restricted from WebSocket |
| RSocket | Interactive request/stream protocol with backpressure and multiple interaction modes | Systems wanting a dedicated reactive messaging protocol |

**STOMP is not SockJS.** SockJS emulates a WebSocket-like transport using HTTP streaming/polling fallbacks. STOMP defines messaging. You can run STOMP over native WebSocket, or pair STOMP + SockJS when the server declares `.withSockJS()` and the client uses a matching SockJS library. Installing SockJS in the browser when the server registers only native WebSocket does not create a fallback endpoint.

**SSE is not a stripped-down one-way WebSocket.** SSE is a distinct HTTP mechanism with its own reconnection/event-ID semantics; do not pick raw WebSocket just to push one-way updates to a chart.

## 7. When to Choose Raw WebSocket vs. STOMP

Choose **raw WebSocket** when:

1. The app protocol is small—such as echo, device control, game state, or binary telemetry—and your team controls both client and server.
2. You do not need complex subscription routing; messages flow on one connection using a custom JSON schema.
3. You want minimal protocol overhead and full control over framing/app semantics.
4. You already have an external fan-out/queue design and do not want STOMP on clients.

Choose **STOMP-over-WebSocket in Spring MVC** when:

1. You want `/app/...` for controller messages, `/topic/...` for multi-subscriber fan-out, or `/user/...` for user-targeted messages.
2. You want `@MessageMapping`, `@SendTo`, and Spring messaging converters.
3. You want the simple broker for demos/small apps, or broker relay when an external STOMP broker exists.
4. Clients support STOMP and accept its protocol overhead.

Never choose based on "WebSocket is faster than STOMP so always use raw" or "STOMP has a broker so messages are never lost." Evaluate connection counts, message rates, payload sizes, guarantees, security, broker infrastructure, operational cost, and scalability.

## 8. Lab A — Spring MVC Serving Both Raw WebSocket and STOMP Simultaneously

This lab uses **Java 17+, Spring Boot 3.3.5**, embedded Tomcat. One application exposes two **distinct** WebSocket endpoints:

- `ws://localhost:8080/ws/raw`: server accepts text and returns `raw: ...` to **that connection only**, without STOMP.
- `ws://localhost:8080/ws/stomp`: server parses STOMP frames, allowing clients to subscribe to `/topic/echo` and `SEND` to `/app/echo` to receive broker-dispatched messages.

Placing both endpoints in one app makes direct comparison easy. In real projects, security and broker configuration require greater care; never expose this demo code as a public internet chat server.

### 8.1. Directory Structure

~~~text
mvc-websocket-lab/
├── pom.xml
└── src/main/
    ├── java/com/example/ws/
    │   ├── WebsocketApplication.java
    │   ├── RawEchoHandler.java
    │   ├── RawWebSocketConfig.java
    │   ├── StompWebSocketConfig.java
    │   ├── ChatMessage.java
    │   └── ChatController.java
    └── resources/
        ├── application.properties
        └── static/index.html
~~~

### 8.2. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
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
    <artifactId>mvc-websocket-lab</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-websocket</artifactId>
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

`spring-boot-starter-websocket` brings Spring WebSocket/messaging integration for Servlet/MVC apps. `spring-boot-starter-web` provides MVC controllers, static resources, and embedded Tomcat; overlapping transitive dependencies are resolved by Maven. The lab **omits** `spring-boot-starter-webflux` to avoid silently changing the runtime model.

### 8.3. application.properties

~~~properties
server.port=8080

# Demo: no authentication or external broker.
# Enforce Origin limits, message size limits, and TLS in production.
~~~

When running the browser on the same `http://localhost:8080`, both WebSocket endpoints share the HTML page's origin; there is no need to open `*` in `allowedOrigins`.

### 8.4. Application Entry Point

**File `src/main/java/com/example/ws/WebsocketApplication.java`:**

~~~java
package com.example.ws;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class WebsocketApplication {
    public static void main(String[] args) {
        SpringApplication.run(WebsocketApplication.class, args);
    }
}
~~~

### 8.5. Raw WebSocket Handler

**File `src/main/java/com/example/ws/RawEchoHandler.java`:**

~~~java
package com.example.ws;

import java.io.IOException;

import org.springframework.stereotype.Component;
import org.springframework.web.socket.TextMessage;
import org.springframework.web.socket.WebSocketSession;
import org.springframework.web.socket.handler.TextWebSocketHandler;

@Component
public class RawEchoHandler extends TextWebSocketHandler {

    @Override
    protected void handleTextMessage(
            WebSocketSession session, TextMessage message)
            throws IOException {
        String text = message.getPayload();
        session.sendMessage(new TextMessage("raw: " + text));
    }
}
~~~

**File `src/main/java/com/example/ws/RawWebSocketConfig.java`:**

~~~java
package com.example.ws;

import org.springframework.context.annotation.Configuration;
import org.springframework.web.socket.config.annotation.EnableWebSocket;
import org.springframework.web.socket.config.annotation.WebSocketConfigurer;
import org.springframework.web.socket.config.annotation.WebSocketHandlerRegistry;

@Configuration
@EnableWebSocket
public class RawWebSocketConfig implements WebSocketConfigurer {

    private final RawEchoHandler echoHandler;

    public RawWebSocketConfig(RawEchoHandler echoHandler) {
        this.echoHandler = echoHandler;
    }

    @Override
    public void registerWebSocketHandlers(WebSocketHandlerRegistry registry) {
        registry.addHandler(echoHandler, "/ws/raw");
    }
}
~~~

**Explanation:**

- `@EnableWebSocket` + `WebSocketConfigurer` registers the handshake URL for the **raw** socket.
- `TextWebSocketHandler` handles WebSocket **text messages**. When the browser sends `hello`, the server sends back text `raw: hello` on **that same WebSocket session**.
- There is no `SUBSCRIBE`, `/topic`, `brokerChannel`, `@MessageMapping`, or STOMP decoding in this handler.
- `WebSocketSession.sendMessage(...)` belongs to the Servlet WebSocket API. When multiple threads send to the same session, serialize sends or wrap with `ConcurrentWebSocketSessionDecorator`; **never invoke send concurrently** from multiple threads arbitrarily.
- The lab implements no binary message handler; do not assume binary payloads are supported just because the WebSocket transport allows binary frames.

### 8.6. STOMP Broker Configuration

**File `src/main/java/com/example/ws/StompWebSocketConfig.java`:**

~~~java
package com.example.ws;

import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.simp.config.MessageBrokerRegistry;
import org.springframework.web.socket.config.annotation.EnableWebSocketMessageBroker;
import org.springframework.web.socket.config.annotation.StompEndpointRegistry;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;

@Configuration
@EnableWebSocketMessageBroker
public class StompWebSocketConfig
        implements WebSocketMessageBrokerConfigurer {

    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/ws/stomp");
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.setApplicationDestinationPrefixes("/app");
        registry.enableSimpleBroker("/topic");
    }
}
~~~

This is the **STOMP part for Spring MVC**. Each path plays a different role:

- `/ws/stomp` is the **HTTP handshake endpoint** for upgrading to WebSocket. It is **not the destination** clients use when calling `SEND` for business messages.
- `/app/echo` is an application **STOMP destination**. Spring strips the `/app` prefix and routes the remainder to `@MessageMapping("/echo")`.
- `/topic/echo` is the broker **STOMP destination** used to deliver messages to active subscribers. It is not an HTTP GET URL.
- `enableSimpleBroker("/topic")` turns on a simple **in-memory** broker. It does not persist messages durably or connect across multiple replicas.

### 8.7. DTO and @MessageMapping Controller

**File `src/main/java/com/example/ws/ChatMessage.java`:**

~~~java
package com.example.ws;

public record ChatMessage(String text) {
}
~~~

**File `src/main/java/com/example/ws/ChatController.java`:**

~~~java
package com.example.ws;

import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.SendTo;
import org.springframework.stereotype.Controller;

@Controller
public class ChatController {

    @MessageMapping("/echo")
    @SendTo("/topic/echo")
    public ChatMessage echo(ChatMessage incoming) {
        String input = incoming.text() == null
                ? "" : incoming.text();

        return new ChatMessage("stomp: " + input);
    }
}
~~~

**Differences from the raw handler:**

1. There is no `@GetMapping` or `@RequestBody`; `@MessageMapping` handles **STOMP SEND frames** targeting the declared destination.
2. Spring's messaging converter decodes JSON in the STOMP payload into `ChatMessage` when headers/content type match.
3. `@SendTo("/topic/echo")` publishes the return payload to the broker; the broker emits `MESSAGE` frames to **all subscribers** on the topic, not merely the sender.
4. `@Controller` here handles **messages**, not regular Servlet HTTP requests.
5. You do not manually inspect each `WebSocketSession` to track subscribers, because the simple broker manages subscriptions within this instance.

**Demo limitations:** no payload length/content checks, no user authentication, no rate limits, and no history storage. Clients can send arbitrary messages; never deploy this as-is to production.

## 9. Browser Client: Testing Raw and STOMP Without External Libraries

To make the protocol-layer difference visible, the lab uses **native browser WebSocket** for both, having JavaScript build minimal raw STOMP frames. In production, use a maintained STOMP client library (such as `@stomp/stompjs`) for proper reconnection, heartbeats, frame parsing, fragmentation, and ACKs.

**File `src/main/resources/static/index.html`:**

~~~html
<!doctype html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Raw WebSocket and STOMP</title>
</head>
<body>
  <h1>Spring Boot WebSocket vs STOMP</h1>
  <button id="rawConnect">Connect raw + send hello</button>
  <button id="stompConnect">Connect STOMP + subscribe</button>
  <button id="stompSend">SEND STOMP /app/echo</button>
  <pre id="output"></pre>

  <script>
    const output = document.querySelector("#output");
    const scheme = location.protocol === "https:" ? "wss:" : "ws:";
    const base = scheme + "//" + location.host;

    const log = message => {
      output.textContent += message + "\n";
    };

    let rawSocket;
    let stompSocket;
    let stompConnected = false;

    document.querySelector("#rawConnect").onclick = () => {
      rawSocket = new WebSocket(base + "/ws/raw");
      rawSocket.onopen = () => {
        log("RAW OPEN");
        rawSocket.send("hello");
      };
      rawSocket.onmessage = event => log("RAW RECV: " + event.data);
      rawSocket.onclose = event => log("RAW CLOSE: " + event.code);
      rawSocket.onerror = () => log("RAW ERROR");
    };

    document.querySelector("#stompConnect").onclick = () => {
      // Propose STOMP subprotocols during the WebSocket handshake.
      stompSocket = new WebSocket(
        base + "/ws/stomp", ["v12.stomp", "v11.stomp", "v10.stomp"]);
      stompConnected = false;

      stompSocket.onopen = () => {
        log("WS STOMP TRANSPORT OPEN");
        stompSocket.send(
          "CONNECT\n" +
          "accept-version:1.2\n" +
          "host:localhost\n" +
          "heart-beat:0,0\n" +
          "\n\0");
      };

      stompSocket.onmessage = event => {
        // Demo prints raw STOMP text; production parsers handle more cases.
        const text = String(event.data);
        log("STOMP RECV: " + text.replaceAll("\0", "<NUL>"));

        if (text.startsWith("CONNECTED\n")) {
          stompConnected = true;
          stompSocket.send(
            "SUBSCRIBE\n" +
            "id:sub-0\n" +
            "destination:/topic/echo\n" +
            "ack:auto\n" +
            "\n\0");
          log("STOMP SUBSCRIBE sent: /topic/echo");
        }
      };

      stompSocket.onclose = event => {
        stompConnected = false;
        log("STOMP CLOSE: " + event.code);
      };
      stompSocket.onerror = () => log("STOMP ERROR");
    };

    document.querySelector("#stompSend").onclick = () => {
      if (!stompSocket ||
          stompSocket.readyState !== WebSocket.OPEN ||
          !stompConnected) {
        log("Connect STOMP and wait for CONNECTED before SEND.");
        return;
      }

      const body = JSON.stringify({text: "hello"});
      stompSocket.send(
        "SEND\n" +
        "destination:/app/echo\n" +
        "content-type:application/json\n" +
        "\n" + body + "\0");

      log("STOMP SEND: /app/echo");
    };
  </script>
</body>
</html>
~~~

### 9.1. How to Operate

1. Run the application (section 10) and open `http://localhost:8080/` in a browser.
2. Click **Connect raw + send hello**. You will see `RAW OPEN` and `RAW RECV: raw: hello`.
3. Click **Connect STOMP + subscribe**. Wait for `WS STOMP TRANSPORT OPEN`, a `CONNECTED` frame, and `STOMP SUBSCRIBE sent: /topic/echo`.
4. Click **SEND STOMP /app/echo** after subscribing. You will see a `MESSAGE` frame with destination `/topic/echo` and a JSON body containing `"stomp: hello"`.
5. Open the page in **two tabs** and subscribe both to `/topic/echo`. When tab A sends a STOMP SEND, both tabs receive the MESSAGE because the simple broker broadcasts to all subscribers; by contrast, a raw echo from tab A returns only to tab A's raw connection.

**Contractual expectation**, not byte-for-byte stdout: STOMP frames may include additional headers or generated IDs. The demo client parses only via `startsWith` and lacks multi-frame coalescing, frame splitting, heartbeats, header escaping, version negotiation, and reconnection. That is **intentional** so you see the protocol layer STOMP adds. In real products, pick a maintained STOMP client matching your version instead of hand-rolling a parser.

### 9.2. Why Not Send Plain JSON Directly to /ws/stomp?

A client doing:

~~~javascript
const w = new WebSocket("ws://localhost:8080/ws/stomp");
w.onopen = () => w.send('{"text":"hello"}');
~~~

will **not automatically map** to `@MessageMapping("/echo")`, because the STOMP endpoint expects **STOMP CONNECT/SEND frames** with destinations and proper frame terminators. Browser `WebSocket` only handles the transport; STOMP semantics live a layer above.

Conversely, sending a STOMP `SEND\n...` frame to `/ws/raw` causes the raw handler to treat it as **a literal text message** and echo it back with no broker parsing.

**This is the clearest test for distinguishing the two protocol layers.**

## 10. Running the MVC Lab and Verifying Results

Create the exact files from sections 8–9 using JDK 17+ and Maven 3.x. Inside `mvc-websocket-lab`:

~~~bash
mvn spring-boot:run
~~~

Open:

~~~text
http://localhost:8080/
~~~

Check that the HTTP server is running:

~~~bash
curl -i http://localhost:8080/
~~~

Expect the HTML page; however, plain `curl -i` **is not a full WebSocket/STOMP client**. Issuing a plain GET to `http://localhost:8080/ws/stomp` without upgrade handshake headers will not verify socket functionality.

### 10.1. Accurate Observations

| Action | What It Verifies |
| --- | --- |
| Browser opens WebSocket `/ws/raw` | Handshake succeeded; raw handler is registered |
| Send text `hello` | Raw server replies `raw: hello`, no broker needed |
| Browser opens WebSocket `/ws/stomp` with matching subprotocols | Only the transport opened; STOMP CONNECT still required |
| Receive STOMP `CONNECTED` | Messaging-layer STOMP session handshake accepted |
| Send `SUBSCRIBE destination:/topic/echo` | Broker registered subscription to receive messages |
| Send `SEND destination:/app/echo` JSON | `@MessageMapping("/echo")` processed it and published to topic |
| Two tabs both subscribed | Both receive broker `MESSAGE` while connected/subscribed |
| Send `SEND` without subscribing | Client does not automatically receive topic messages |
| Send STOMP frame to raw URL | Raw echo only, no `destination` routing |

### 10.2. Two Independent Handshakes

- **WebSocket handshake**: HTTP Upgrade → 101 Switching Protocols → transport open.
- **STOMP CONNECT/CONNECTED**: STOMP frame exchange **after** the WebSocket opens.

A socket showing `OPEN` in the browser does not mean the STOMP session is `CONNECTED`. If the server closes immediately after `CONNECT`, inspect the frame, version, subprotocol, auth/CSRF, and server logs.

### 10.3. Why You Cannot Look Only at Status 101

Both raw and STOMP WebSocket endpoints **return 101**. That status alone does not reveal whether the server treats payloads as raw text or STOMP frames. To distinguish them, inspect the `Sec-WebSocket-Protocol` request/response negotiated subprotocol, server config, and **post-handshake message contents**.

If proxy logs show `101` while the client reports "STOMP not connected", the WebSocket transport succeeded while the STOMP `CONNECT` failed or was rejected by a security channel interceptor.

## 11. WebFlux Raw WebSocket — A Separate Project

Spring WebFlux uses reactive APIs different from Servlet MVC. The next example is an **independent project**—do not copy it into `mvc-websocket-lab`. It implements **raw WebSocket echo only** and **does not** enable a STOMP broker.

### 11.1. Directory Layout

~~~text
webflux-websocket-lab/
├── pom.xml
└── src/main/
    ├── java/com/example/reactivews/
    │   ├── ReactiveWsApplication.java
    │   ├── ReactiveEchoHandler.java
    │   └── ReactiveWsConfig.java
    └── resources/
        ├── application.properties
        └── static/index.html
~~~

### 11.2. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
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
    <artifactId>webflux-websocket-lab</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
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

With the default Reactor Netty runtime, `spring-boot-starter-webflux` provides all WebFlux reactive APIs and the server needed for this lab. **If deploying WebFlux onto a Servlet container** such as Tomcat/Jetty or as a WAR, verify Jakarta WebSocket API/container requirements and Spring Boot WebSocket auto-configuration for your version. Do not assume Reactor Netty needs Tomcat WebSocket dependencies.

### 11.3. Application and Configuration

**File `src/main/resources/application.properties`:**

~~~properties
server.port=8082
~~~

**File `src/main/java/com/example/reactivews/ReactiveWsApplication.java`:**

~~~java
package com.example.reactivews;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReactiveWsApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReactiveWsApplication.class, args);
    }
}
~~~

**File `src/main/java/com/example/reactivews/ReactiveEchoHandler.java`:**

~~~java
package com.example.reactivews;

import org.springframework.stereotype.Component;
import org.springframework.web.reactive.socket.WebSocketHandler;
import org.springframework.web.reactive.socket.WebSocketMessage;
import org.springframework.web.reactive.socket.WebSocketSession;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Component
public class ReactiveEchoHandler implements WebSocketHandler {

    @Override
    public Mono<Void> handle(WebSocketSession session) {
        Flux<WebSocketMessage> output = session.receive()
                .map(incoming ->
                        session.textMessage(
                                "reactive: " + incoming.getPayloadAsText()));

        return session.send(output);
    }
}
~~~

**File `src/main/java/com/example/reactivews/ReactiveWsConfig.java`:**

~~~java
package com.example.reactivews;

import java.util.Map;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.HandlerMapping;
import org.springframework.web.reactive.handler.SimpleUrlHandlerMapping;

@Configuration
public class ReactiveWsConfig {

    @Bean
    public HandlerMapping reactiveWebSocketMapping(
            ReactiveEchoHandler handler) {
        return new SimpleUrlHandlerMapping(
                Map.of("/ws/echo", handler), -1);
    }
}
~~~

Explanation:

- `org.springframework.web.reactive.socket.WebSocketHandler` is a **different interface** from `org.springframework.web.socket.WebSocketHandler` in MVC.
- `session.receive()` produces `Flux<WebSocketMessage>`, while `session.send(Publisher<WebSocketMessage>)` returns `Mono<Void>` representing outbound writes.
- `getPayloadAsText()` is read immediately inside the pipeline upon receiving a message. Never retain or reuse Netty buffers past the lifecycle without proper `retain`/`release`.
- `SimpleUrlHandlerMapping` maps the **WebSocket handshake URL** `/ws/echo` to the reactive handler with order `-1` to take precedence over HTTP handlers.
- Spring WebFlux Java configuration / Boot auto-configuration supplies `WebSocketHandlerAdapter` for WebSocket handlers. In manual WebFlux setups without standard WebFlux config, declare the adapter explicitly per Spring Framework docs.
- `Mono<Void>` completes when the pipeline finishes (e.g., when the session closes); never call `subscribe()` manually and return an immediate empty completion.

**This is still raw WebSocket.** The string `reactive: hello` is sent by application code, not a STOMP `MESSAGE` frame; `SimpleUrlHandlerMapping` provides neither `@MessageMapping` nor a broker.

### 11.4. Browser Client for WebFlux

**File `src/main/resources/static/index.html`:**

~~~html
<!doctype html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>WebFlux raw WebSocket</title>
</head>
<body>
  <h1>Reactive WebSocket Echo</h1>
  <button id="send">Send hello</button>
  <pre id="log"></pre>
  <script>
    const log = document.querySelector("#log");
    const scheme = location.protocol === "https:" ? "wss:" : "ws:";
    const socket = new WebSocket(
      scheme + "//" + location.host + "/ws/echo");

    socket.onopen = () => log.textContent += "OPEN\n";
    socket.onmessage = event =>
      log.textContent += "RECV: " + event.data + "\n";
    socket.onclose = event =>
      log.textContent += "CLOSE: " + event.code + "\n";

    document.querySelector("#send").onclick = () => {
      if (socket.readyState === WebSocket.OPEN) {
        socket.send("hello");
      }
    };
  </script>
</body>
</html>
~~~

Run inside the separate WebFlux project:

~~~bash
mvn spring-boot:run
~~~

Open `http://localhost:8082/`, wait for `OPEN`, and click **Send hello**. Expected output:

~~~text
RECV: reactive: hello
~~~

That is a **raw WebSocket exchange** processed by the Reactor pipeline, not Spring MVC STOMP.

## 12. Why WebFlux Does Not Automatically Enable a STOMP Broker

Seeing `spring-messaging` on the classpath or a class named `Message` in a reactive project **does not prove** there is a full STOMP-over-WebSocket broker for WebFlux. `@EnableWebSocketMessageBroker` belongs to the Servlet/MVC WebSocket messaging stack and relies on its handler/channel/broker components.

Common mistake:

~~~java
// DO NOT treat this as an equivalent configuration for WebFlux:
// @EnableWebSocketMessageBroker
// class MyReactiveApp { ... }
~~~

This snippet is purely a boundary reminder, **not a runnable source file**. With WebFlux raw WebSocket, you read/write messages directly or use a specialized framework/adapter. If you need STOMP destinations in a reactive architecture, consider:

1. **Isolating an MVC WebSocket messaging gateway** with STOMP integration as its own service, connected to reactive services via a broker/API.
2. **Using or building a STOMP adapter** that handles frames and routing on top of a WebFlux raw `WebSocketHandler`, carefully managing protocol parsing, ACKs, subscriptions, heartbeats, security, and backpressure.
3. **Choosing another fitting protocol** such as RSocket, SSE for one-way streams, or raw WebSocket with an application-defined JSON envelope.
4. When durable delivery is needed, use a message broker with matching semantics; never treat the in-memory simple broker as a persistence layer.

**Do not mix both web stacks expecting "the best of both" for free.** If the classpath contains both `starter-web` and `starter-webflux`, Boot 3.3 normally chooses Servlet MVC. You can use reactive `WebClient` inside an MVC app, yet the **inbound socket stack** remains MVC/Servlet.

## 13. Spring STOMP Brokers: Simple vs. External Relay

### 13.1. Simple Broker

Configured in the lab as:

~~~java
registry.setApplicationDestinationPrefixes("/app");
registry.enableSimpleBroker("/topic");
~~~

The simple broker:

- Holds client subscriptions **in memory inside one application instance**.
- Receives messages sent to broker destinations and broadcasts to matching subscribers.
- Suits demos, prototypes, and modest single-instance apps with simple requirements.
- **Does not** provide persistent messaging, offline delivery, or routing across multiple Spring Boot replicas.
- Supports **only a subset of STOMP commands**; lacks full ACK/receipt and enterprise broker features.
- Can be configured with a task scheduler for STOMP heartbeats.

With two replicas A and B, if a user on A subscribes to `/topic/news` while app code on B publishes to B's simple broker, **the user on A will not receive it automatically**. Sticky sessions only keep a connection pinned to an instance; they do not synchronize broker memory between A and B.

### 13.2. External Broker Relay

Replace the simple broker with a STOMP broker relay when you want an external message broker such as RabbitMQ or ActiveMQ with STOMP enabled. **Illustrative** configuration:

~~~java
@Override
public void configureMessageBroker(MessageBrokerRegistry registry) {
    registry.setApplicationDestinationPrefixes("/app");

    registry.enableStompBrokerRelay("/topic", "/queue")
            .setRelayHost("127.0.0.1")
            .setRelayPort(61613);
}
~~~

This method **replaces** `configureMessageBroker` in the lab's `StompWebSocketConfig` once an external broker is running; **do not** enable both the simple broker and broker relay for the same destination prefixes simultaneously. Ensure a STOMP endpoint is listening on `127.0.0.1:61613` with valid credentials/TLS and network access before running; pasting this snippet into the lab without a broker breaks messaging.

Flow:

~~~text
Browser STOMP over WebSocket
       |
       v
Spring MVC WebSocket/STOMP endpoint
       |
       v
Spring STOMP broker relay (TCP client)
       |
       v
External STOMP broker
       |
       +--> subscriptions across app instances
       '--> routes / queues per broker capabilities
~~~

**Relay limitations:**

- Spring does not become a durable broker itself; it **relays** STOMP frames and depends on the external broker.
- The broker must speak STOMP natively, not merely AMQP or Kafka ports. RabbitMQ, for instance, requires enabling its STOMP plugin/config.
- Session authentication, destination ACLs, subscriber limits, and broker permissions must be enforced at the proper layers; using a relay does not remove Spring Security responsibilities.
- Multi-instance subscriptions can share the broker, yet delivery guarantees, durability, ACKs, and redelivery depend on the broker and destination semantics.

### 13.3. `/topic` and `/queue` Are Naming Conventions

In the **simple broker**, `/topic` and `/queue` do not automatically enforce different publish-subscribe vs. competing-consumer algorithms by name. They are primarily **prefix conventions** for routing messages. With an external broker, destination names and semantics follow that specific broker's rules.

Do not assume `/queue/orders` on the simple broker behaves like a durable single-consumer work queue. When reliable order processing is required, choose a message broker with durable queue semantics and transactional/outbox patterns.

## 14. @MessageMapping, @SendTo, and Proactive Sending

### 14.1. @MessageMapping Receives STOMP SEND

~~~java
@MessageMapping("/echo")
@SendTo("/topic/echo")
public ChatMessage echo(ChatMessage input) {
    return new ChatMessage("stomp: " + input.text());
}
~~~

This method belongs to **an MVC STOMP controller**, not an HTTP controller. The client sends:

~~~text
SEND
destination:/app/echo
content-type:application/json

{"text":"hi"}^@
~~~

Spring routes it to `/echo` and forwards the return value to `/topic/echo`. Never mistake `@SendTo` for an HTTP redirect or a browser URL.

### 14.2. SimpMessagingTemplate Sends from Services or HTTP Controllers

To push events produced by background jobs or HTTP requests, inject `SimpMessagingTemplate` in an MVC STOMP app:

~~~java
package com.example.ws;

import org.springframework.messaging.simp.SimpMessagingTemplate;
import org.springframework.stereotype.Service;

@Service
public class NotificationPublisher {

    private final SimpMessagingTemplate messaging;

    public NotificationPublisher(SimpMessagingTemplate messaging) {
        this.messaging = messaging;
    }

    public void publish(String text) {
        messaging.convertAndSend(
                "/topic/echo",
                new ChatMessage(text));
    }
}
~~~

This class is **runnable if placed inside the MVC STOMP lab project**; it **does not generate or schedule events itself**, merely providing `publish` for other services to invoke.

Do not confuse `convertAndSend` with writing directly to a raw `WebSocketSession`. It travels through Spring's messaging infrastructure/broker and broadcasts to all matching subscribers.

### 14.3. User-Targeted Messages

STOMP in Spring MVC supports user destinations, commonly via `/user/queue/...` and `convertAndSendToUser(...)`. This abstraction **requires accurate user identity, session mapping, and authorization**.

Never assume `/user/queue/private` in an unauthenticated lab protects personal data: without authentication, identity mapping, and security rules, private queues can be subscribed to improperly. User destinations do not replace authorization checks.

## 15. Distinguishing Handshake, Subscribe, Broadcast, and Disconnect

### 15.1. High-Level State Machine for Raw WebSocket

~~~text
CLOSED
  |
  | HTTP Upgrade
  v
OPEN <----> TEXT / BINARY frames
  |
  | ping/pong/timeout/network failure
  v
CLOSING -> CLOSED
~~~

Raw handlers must manage session lifecycles, resource cleanup, client message validation, slow-consumer controls, and close codes.

### 15.2. High-Level State Machine for STOMP-over-WebSocket

~~~text
WebSocket OPEN
    |
    | STOMP CONNECT
    v
STOMP CONNECTED
    |
    +--> SUBSCRIBE destination:/topic/echo
    |         |
    |         '--> MESSAGE events from broker
    |
    +--> SEND destination:/app/echo
    |         |
    |         '--> @MessageMapping + broker routing
    |
    +--> UNSUBSCRIBE / ACK / NACK (if supported)
    |
    '--> DISCONNECT / ERROR / broken network
                |
                v
          WebSocket closed
~~~

A WebSocket that is `OPEN` yet not `STOMP CONNECTED` is a normal intermediate stage. The browser must handle reconnects and **re-subscribe** after disconnects to continue receiving updates. The simple broker does not store messages sent while a client was offline.

## 16. WebSocket Ping/Pong, STOMP Heartbeats, and Idle Timeouts

Three mechanisms are frequently confused:

1. **WebSocket ping/pong:** WebSocket-layer control frames. Browser JavaScript does not expose a direct ping API like native HTTP/socket clients; servers/runtimes may send pings.
2. **STOMP heartbeats:** typically newlines between frames negotiated via `heart-beat:cx,cy` and managed by STOMP peers/brokers.
3. **Proxy/server idle timeouts:** connections can close if proxies see no traffic within their configured window.

Systems usually need to coordinate pings/heartbeats **with** proxy idle timeouts. In Spring's simple broker, STOMP heartbeats may require configuring a task scheduler. Enabling heartbeats on the STOMP client alone does not make the simple broker emit heartbeats unless configured on the server side.

**When using SockJS**, SockJS adds its own heartbeat policy. Once STOMP client and server negotiate STOMP heartbeats, SockJS heartbeats can be disabled to avoid duplication. Do not treat "SockJS's 25-second heartbeat" as a universal rule across all WebSocket setups.

In practice:

- Choose a heartbeat interval comfortably shorter than proxy idle timeouts to absorb jitter.
- Measure disconnects and reconnect success rates.
- Avoid overly aggressive heartbeats that spike CPU/network across tens of thousands of sockets.
- On disconnect, handle user state, subscriptions, and missed messages according to business contracts.

## 17. WebSocket and STOMP Security

### 17.1. Origin in the WebSocket Handshake

Browser WebSocket sends `Origin`, yet **fetch's same-origin policy/CORS does not govern WebSocket handshakes identically to AJAX**. Servers and proxies must actively validate allowed origins. Spring MVC WebSocket/SockJS normally **allows only same-origin by default**, configurable via the registry.

~~~java
// Illustrative config for a genuinely trusted frontend:
registry.addHandler(echoHandler, "/ws/raw")
        .setAllowedOrigins("https://app.example.com");
~~~

This snippet **replaces** the `addHandler` line in the lab; never paste a literal production domain into a localhost demo expecting local access to keep working. For STOMP endpoints, configure allowed origins on `StompEndpointRegistry`. Allowlist only origins you control; never use `*` for apps using private cookies.

**Origin is not authentication.** Non-browser WebSocket clients can spoof `Origin`; authenticate requests and enforce authorization independently.

### 17.2. Cookies, Handshake, and Sessions

WebSocket starts with an HTTP handshake. If the browser holds a session cookie matching host/path/SameSite/Secure rules, it sends that cookie during the handshake. Spring Security can authenticate the principal on the HTTP handshake and propagate that identity into the WebSocket/STOMP session.

Never let browser JS send raw user cookies or tokens to untrusted origins to "fix CORS". The browser WebSocket API also **cannot set arbitrary custom `Authorization` headers** like `fetch`. If passing tokens in STOMP `CONNECT` headers, configure a channel interceptor to validate the token; merely writing `Authorization: Bearer ...` inside a STOMP frame **does not** cause Spring Security HTTP filters to read it.

### 17.3. CSRF / Cross-Site WebSocket Hijacking

If the handshake relies on session cookies and the endpoint allows all origins, a malicious site can attempt to open a socket in the victim's authenticated context. Enforce:

- Strict allowed-origin validation matching your trust boundary.
- Authentication and authorization on both handshake and messages.
- Spring Security CSRF protection on STOMP `CONNECT` when using messaging security—never strip it out just because "it's only WebSocket".
- Appropriate `SameSite`/`Secure`/`HttpOnly` cookie policies and `wss://` TLS in production.
- Validation of protocol, destinations, message headers, and payloads against user permissions.

STOMP destinations like `/topic/public` and `/user/queue/private` have different privilege levels. Securing only the handshake is insufficient if any authenticated user can `SEND` to any destination or subscribe to another user's private updates.

### 17.4. Message-Layer Authorization

With Spring Security WebSocket message security in Servlet STOMP, use an authorization manager or channel interceptor to specify who can `SEND` to `/app/...` and `SUBSCRIBE` to `/topic/...` or `/user/...`. An `@MessageMapping` method does not automatically block unauthorized users.

Key risks:

- **Sender spoofing**: never trust a `username`/`userId` inside the message body; read the server-verified principal.
- **Subscription leaks**: block subscriptions to destinations carrying other users' data without authorization.
- **Flooding**: cap connections, subscriptions, messages/sec, and bytes/sec.
- **Slow consumers**: bound send buffers and send durations, closing overly slow sessions.
- **Payload injection/XSS**: render text on clients using `textContent` or proper escaping rather than injecting untrusted messages into HTML.
- **Secrets in logs**: never log raw cookies, tokens, or sensitive STOMP headers—especially in `CONNECT`.
- **TLS**: use `wss://` from HTTPS frontends and secure proxy→app hops as policy demands.

## 18. Reverse Proxies, Load Balancers, and Multiple Replicas

### 18.1. Proxies Must Support WebSocket Upgrade

An NGINX HTTP/1.1 reverse proxy typically needs WebSocket forwarding headers:

~~~nginx
map $http_upgrade $connection_upgrade {
    default upgrade;
    ''      close;
}

server {
    listen 443 ssl;
    server_name app.example.com;

    # Valid SSL certificate/key required here in real deployments.

    location /ws/ {
        proxy_pass http://127.0.0.1:8080;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection $connection_upgrade;
        proxy_set_header Host $host;
        proxy_read_timeout 300s;
    }
}
~~~

This snippet **is not a complete runnable NGINX file**: it omits `ssl_certificate`, `ssl_certificate_key`, security policies, and the outer `http` context. The point is that WebSocket handshakes require proxies to forward `Upgrade`/`Connection` over HTTP/1.1 with appropriately long timeouts.

If a proxy does not support upgrades or blocks the handshake, browsers typically report WebSocket connection failure, 400/404/426/502, or no 101 appears. That does not mean STOMP logic is broken: verify the **transport** first.

### 18.2. Sticky Sessions Do Not Mean a Clustered Broker

~~~text
Users A -> App replica 1 -> simple broker 1 (memory)
Users B -> App replica 2 -> simple broker 2 (memory)
~~~

If two Spring Boot instances each run the in-memory simple broker, subscriptions are not shared. A load balancer with sticky routing keeps a user's WebSocket on the same replica, yet **events published on replica 2 never reach subscribers on replica 1**.

To broadcast across replicas, consider:

- External STOMP broker relay (backed by an HA-deployed broker).
- A dedicated pub/sub bus so each instance fans out to its local sockets when using raw WebSocket.
- Redis pub/sub for ephemeral non-durable broadcasts, or Redis Streams/Kafka/RabbitMQ when stronger guarantees are required.
- Application-level event routing scoped by user/tenant and permissions.

**Message durability is separate from WebSocket session lifetime.** Dropped connections need reconnect/resubscribe; durable queues and offline inboxes must be built separately per business needs.

## 19. Performance: Connections, Threads, Buffers, and Backpressure

WebSocket keeps connections open long-term, unlike short HTTP requests where sockets are released right after a response.

In Spring MVC raw WebSocket:

- WebSocket callbacks run on threads managed by the Servlet/WebSocket runtime.
- When calling `WebSocketSession.sendMessage` from multiple threads, serialize writes or use `ConcurrentWebSocketSessionDecorator` to avoid unsafe concurrent sends on one session.
- Set appropriate max session idle timeouts, max message sizes, and send time/buffer limits; avoid unbounded message history in RAM.
- STOMP uses `clientInboundChannel`, `brokerChannel`, and `clientOutboundChannel` whose executors/queues can build backlogs; measure rather than blindly enlarging thread pools.

In WebFlux raw WebSocket:

- `Flux<WebSocketMessage>` and `Mono<Void>` form a reactive pipeline; avoid `block()` or blocking JDBC/filesystem I/O on the event loop.
- When handling Netty payload buffers, respect `DataBuffer` ownership—never retain/reuse after release, and handle errors/cancellations.
- Reactive APIs express backpressure and avoid holding threads idle during I/O, **without automatically preventing OOM** when consumers are slow.
- `session.receive().collectList()` on a long-lived socket retains unbounded data in memory; never use it on long streams.

### 19.1. STOMP Has Overhead

Every STOMP SEND frame carries command, headers, and terminator bytes alongside its payload. When sending tiny telemetry updates tens of thousands of times per second, overhead can be noticeable. Conversely, broker routing saves custom code and operational effort. Never declare one faster without measuring:

- concurrent sockets;
- message rates and payload sizes;
- network bandwidth and parsing CPU;
- broker queues/backlogs;
- p95/p99 end-to-end delivery latency;
- dropped messages and reconnects;
- memory/send buffers per session.

**Do not infer from "WebFlux is reactive" that MVC's STOMP broker also runs reactively.** Each stack has its own execution model.

## 20. Common Errors and How to Diagnose Them

| Symptom | Likely Cause | Resolution |
| --- | --- | --- |
| WebSocket handshake returns 404 | Wrong URL/path or unregistered handler | Compare `/ws/raw`, `/ws/stomp` against config |
| Browser never sees status 101 | Proxy not upgrading, TLS/origin failure, bad route, or error | Inspect Network WS handshake and proxy logs |
| Raw echo works yet STOMP never connects | Sent JSON/plain text instead of STOMP frame, missing NUL, wrong subprotocol | Use a STOMP client, verify CONNECT/CONNECTED |
| STOMP CONNECTED yet no messages arrive | Didn't SUBSCRIBE, wrong destination, or sent too early | Check `/app/echo` vs `/topic/echo`; subscribe first |
| `@MessageMapping` not invoked | Sent SEND to `/topic` instead of `/app`, wrong prefix | Inspect destination routing |
| `/ws/stomp` returns 101 yet send fails | Malformed STOMP frame, auth/CSRF, converter failure | Inspect STOMP ERROR frame and backend logs |
| `/topic` fails to broadcast across 2 replicas | In-memory simple brokers are instance-local | Use a broker relay or distributed fan-out bus |
| `/queue` is not durable | Prefix is only a naming convention in simple broker | Use an external broker with durable queue semantics |
| Added `@EnableWebSocketMessageBroker` to WebFlux without routing | Confused Servlet STOMP support with reactive raw WS | Pick MVC STOMP or a custom reactive adapter |
| Both `starter-web` and `starter-webflux` present; wrong stack booted | Boot prioritizes MVC | Check `WebApplicationType` and dependency tree |
| Client receives ERROR on CONNECT | Version mismatch, auth failure, security policy, frame headers | Inspect client frames and channel interceptors |
| Sent raw text to STOMP endpoint | Server expects STOMP protocol frames | Use valid CONNECT/SEND frames |
| Sent STOMP frame to raw endpoint | Raw handler treats it as plain text without routing | Match endpoint and protocol |
| Client disconnects after 60s idle | Proxy/LB timeout or missing heartbeat | Configure heartbeats/pings and `proxy_read_timeout` |
| WebSocket works on localhost, fails on HTTPS site | Using `ws://` from HTTPS, cert/proxy, or origin issue | Switch to `wss://`, check TLS and allowed origins |
| Cannot read JWT from custom browser WS headers | Browser WebSocket API disallows arbitrary headers | Use cookie handshake or controlled STOMP CONNECT token strategy |
| User can view another user's topic | Missing per-destination authorization | Enforce Spring Security message authorization |
| Server memory grows as users send messages | Unbounded queues/buffers, slow consumers | Add size/rate limits, backpressure, discard/cleanup |
| Raw session throws concurrent-write errors | Multiple threads calling `send` on one Servlet session | Serialize sends or use decorator |
| Missed messages while offline | WebSocket and simple broker are non-durable | Add dedicated replay/outbox/offline inbox |

### 20.1. Layer-by-Layer Debug Workflow

1. **Transport:** can the client open `ws://`/`wss://`? Does HTTP Upgrade return 101 or an error? Does the proxy support upgrades?
2. **Protocol:** is the endpoint raw or STOMP? Did `CONNECT`/`CONNECTED` succeed, and which subprotocol was negotiated?
3. **Routing:** for STOMP, did the client `SEND` to `/app/...` and `SUBSCRIBE` to the right broker destination?
4. **Converter:** do `content-type`, JSON field names, DTO record fields, and message converters align?
5. **Authorization:** handshake Origin, principal, STOMP CONNECT CSRF, and ACLs on SEND/SUBSCRIBE?
6. **Distribution:** local simple broker or external relay? Do replicas share an event bus?
7. **Resources:** any idle timeouts, slow clients, send buffer overflows, heartbeat mismatches, or thread/backpressure issues?

**Isolate the layer before fixing.** A successful WebSocket connection does not prove STOMP routing works; an invoked `@MessageMapping` does not prove users are authorized to subscribe and receive messages.

## 21. Key Misconceptions

1. **"STOMP is WebSocket."** False: STOMP is a messaging protocol that can run over WebSocket or TCP.
2. **"WebSocket includes subscribe/topic automatically."** False: raw WebSocket defines no pub/sub; apps must build it themselves.
3. **"Having a broker means all messages are saved."** False: Spring's simple broker holds subscriptions in memory without durable message storage.
4. **"WebFlux does not support WebSocket."** False: WebFlux has a reactive WebSocket API.
5. **"WebFlux has `@EnableWebSocketMessageBroker` just like MVC."** There is no built-in equivalent in WebFlux; STOMP requires another adapter/library/architecture.
6. **"With `@MessageMapping`, `/app/echo` can be opened via HTTP GET."** False: that is a STOMP destination, not an HTTP endpoint.
7. **"SockJS is STOMP."** False: SockJS is a transport fallback; STOMP is the messaging layer.
8. **"`/queue` in the simple broker is automatically a durable queue."** False: prefixes do not create durability.
9. **"A 101 handshake means STOMP is already CONNECTED."** False: STOMP still requires `CONNECT`/`CONNECTED` after the WebSocket handshake.
10. **"You don't need to worry about CORS/origins for WebSocket."** False: WebSocket handshakes require dedicated Origin/trust/security policies rather than relying on fetch CORS behavior.
11. **"Using `wss://` at the edge means every backend hop is encrypted."** Not automatically: proxies often terminate TLS and forward cleartext HTTP internally.
12. **"WebSocket is always superior to SSE or HTTP polling."** False: choose based on data direction, browser needs, infrastructure, and operational cost.

## 22. Self-Check Exercises

**Question 1.** A client runs `new WebSocket("ws://...")` and sends `{"text":"hi"}`. Does that automatically enable STOMP messaging?

**Question 2.** The WebSocket handshake returns `101`, yet the browser receives no messages from `@MessageMapping`. Why should you check STOMP CONNECT and destinations next?

**Question 3.** Distinguish `/ws/stomp`, `/app/echo`, and `/topic/echo` in the MVC example.

**Question 4.** When a client executes `SUBSCRIBE /topic/echo` and then `SEND /app/echo`, which components does the message traverse?

**Question 5.** A project has only `spring-boot-starter-webflux`. Which APIs are needed for a raw echo handler? Can you reuse Servlet's `TextWebSocketHandler` directly?

**Question 6.** Why can't `@EnableWebSocketMessageBroker` be assumed as an automatic feature in every WebFlux project?

**Question 7.** Two MVC replicas use the simple broker; one user is on A and another on B. Will an event on A automatically reach the user on B?

**Question 8.** STOMP defines `ACK`, yet the simple broker lacks full durable broker semantics. How does that affect delivery guarantees?

**Question 9.** An HTTPS browser page opens `ws://` to a production API and fails. What URL/TLS issues must be checked?

**Question 10.** Why isn't STOMP `/user/queue/private` secure automatically without authentication and authorization configured?

**Question 11.** When a client loses network connectivity and reconnects, are all missed messages guaranteed to replay automatically?

**Question 12.** When sending raw WebSocket messages from two threads into the same Servlet `WebSocketSession`, what must you watch out for?

**Suggested answers:**

1. No. The WebSocket payload is plain text; STOMP requires valid frames, CONNECT, destinations, and a STOMP endpoint.
2. Because WebSocket OPEN differs from STOMP CONNECTED; `@MessageMapping` routes only STOMP SEND messages matching configured destinations.
3. `/ws/stomp` is the handshake URL; `/app/echo` is the application message destination; `/topic/echo` is the broker destination.
4. The STOMP inbound channel routes `/app/echo` to `@MessageMapping`, `@SendTo` forwards the output to the broker, and the broker delivers `MESSAGE` frames to subscribers.
5. Use `org.springframework.web.reactive.socket.WebSocketHandler`, `WebSocketSession`, `Flux/Mono`, and `SimpleUrlHandlerMapping`; do not copy Servlet handlers verbatim.
6. Because Spring's STOMP broker and message channels belong to Servlet messaging integration; WebFlux ships only the raw reactive WebSocket API out of the box.
7. Not by default; each instance's simple broker keeps separate in-memory subscriptions, requiring a relay or distributed bus.
8. You cannot promise durable delivery/ack/replay merely because STOMP defines an ACK frame; you must use a broker with matching semantics.
9. Use `wss://` with valid certificates, proxy forwarding, and allowed origins; HTTPS pages normally block insecure `ws://`.
10. The destination is just a routing convention; you still need verified user identity and ACLs on SEND/SUBSCRIBE.
11. Not with raw WebSocket or the simple broker; add explicit replay/offline storage when required by business rules.
12. Serialize sends or use `ConcurrentWebSocketSessionDecorator` with bounded buffers and send time limits.

## 23. Implementation Checklist

- [ ] Clearly decide between raw WebSocket and STOMP messaging; never mix endpoints and payload formats.
- [ ] Verify whether the app actually runs **MVC/Servlet** or **WebFlux**.
- [ ] For MVC STOMP, include `spring-boot-starter-websocket`, `@EnableWebSocketMessageBroker`, and proper broker prefixes.
- [ ] For WebFlux, use reactive `WebSocketHandler`; never assume an MVC STOMP broker exists.
- [ ] Ensure clients verify both WebSocket OPEN **and** STOMP CONNECTED where applicable.
- [ ] Distinguish handshake URLs, application destinations, and broker destinations.
- [ ] Restrict the simple broker to in-memory/single-instance scopes; plan an external relay for scaling.
- [ ] Specify exact subscription, user-destination, delivery/ACK/replay requirements.
- [ ] Configure TLS `wss://`, proxy Upgrades, timeouts, and heartbeats matching your topology.
- [ ] Enforce Origin allowlists, authentication, session/CSRF, and per-message authorization.
- [ ] Cap connections, subscriptions, message sizes, rates, and slow-consumer buffers.
- [ ] Implement session cleanup, reconnect/backoff, resubscribe, and server-restart recovery.
- [ ] Never log tokens/cookies and never render message text as unsanitized HTML.
- [ ] Track metrics for open sockets, STOMP CONNECT/ERROR, inbound/outbound queues, sends, latency, and disconnects.
- [ ] Test two tabs, two replicas, offline clients, malformed frames, 404/101, and broker downtime.

## 24. References

- Spring Framework — WebSocket (Servlet), `WebSocketHandler`, and handshake: https://docs.spring.io/spring-framework/reference/web/websocket/server.html
- Spring Framework — STOMP over WebSocket overview and protocol: https://docs.spring.io/spring-framework/reference/web/websocket/stomp/overview.html
- Spring Framework — Enable STOMP/message broker in MVC: https://docs.spring.io/spring-framework/reference/web/websocket/stomp/enable.html
- Spring Framework — STOMP message flow: https://docs.spring.io/spring-framework/reference/web/websocket/stomp/message-flow.html
- Spring Framework — Simple Broker: https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-simple-broker.html
- Spring Framework — External Broker Relay: https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-broker-relay.html
- Spring Framework — STOMP annotated controllers and user destinations: https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-annotations.html
- Spring Framework — Reactive WebFlux WebSocket API: https://docs.spring.io/spring-framework/reference/web/webflux-websocket.html
- Spring Framework — WebFlux config and `WebSocketHandlerAdapter`: https://docs.spring.io/spring-framework/reference/web/webflux/config.html
- Spring Boot 3.3 — WebSocket server auto-configuration: https://docs.spring.io/spring-boot/3.3/reference/messaging/websockets.html
- Spring Security — WebSocket/STOMP authorization: https://docs.spring.io/spring-security/reference/servlet/integrations/websocket.html
- Spring Security — WebSocket CSRF and same-origin policy: https://docs.spring.io/spring-security/reference/servlet/integrations/websocket.html
- RFC 6455 — The WebSocket Protocol: https://www.rfc-editor.org/rfc/rfc6455
- RFC 8441 — Bootstrapping WebSockets with HTTP/2: https://www.rfc-editor.org/rfc/rfc8441
- STOMP Protocol Specification 1.2: https://stomp.github.io/stomp-specification-1.2.html
