# The Boundary Between Raw WebSocket and STOMP in Spring Framework

## 1. Lesson Objectives

After this lesson, you should be able to distinguish **WebSocket as a bidirectional transport** from **STOMP as an application-layer messaging protocol** that can run over that transport; know when to design a custom message protocol over WebSocket, when to use STOMP, and especially **never confuse WebFlux WebSocketHandler with Spring STOMP message-broker configuration**.

Specific capabilities:

1. Explain HTTP Upgrade, WebSocket text/binary frames, and the meaning of `Sec-WebSocket-Protocol`.
2. Recognize STOMP frames such as `CONNECT`, `CONNECTED`, `SUBSCRIBE`, `SEND`, `MESSAGE`, `ACK`, `NACK`, and `DISCONNECT`.
3. Distinguish WebSocket URLs from STOMP destinations, and transport close codes from STOMP `ERROR`/`RECEIPT`.
4. Understand `/app`, `/topic`, and `/queue` routing in Spring and the difference between the simple broker and an external broker relay.
5. Identify the technological boundary: WebFlux reactive WebSocket API versus Servlet-stack Spring WebSocket/STOMP messaging.
6. Build a WebFlux raw WebSocket echo server and a standalone Spring MVC + STOMP application on Java 17+.
7. Choose a solution based on latency, routing, subscriptions, reliability, security, operations, and scalability.

## 2. The Concept in One Sentence

**Raw WebSocket** is a full-duplex connection enabling both sides to exchange text/binary messages. RFC 6455 **does not define** what messages like `subscribe`, `order-created`, or `chat-room-42` mean. If an application wants those actions, both sides must agree on the format and semantics themselves.

**STOMP** (Simple Text Oriented Messaging Protocol) is a message-oriented protocol with commands, headers, a body, and a frame terminator. STOMP defines how to connect a messaging session, send to a destination, subscribe to receive messages, acknowledge delivery, and perform several control operations. STOMP can run over WebSocket or another bidirectional streaming transport such as TCP.

In short:

~~~text
Raw WebSocket:
  HTTP Upgrade -> WebSocket frames -> application-defined payload

STOMP over WebSocket:
  HTTP Upgrade -> WebSocket frames -> STOMP protocol frames
                                      |
                                      +-- destinations
                                      +-- subscriptions
                                      +-- SEND / MESSAGE
                                      +-- ACK / NACK
                                      +-- heartbeats
                                      +-- broker routing
~~~

**STOMP is not a version of WebSocket.** It is a higher-level protocol carried over WebSocket. And an open WebSocket connection **does not automatically** understand STOMP.

## 3. Comparison Table of the Two Models

| Criterion | Raw WebSocket | STOMP over WebSocket |
| --- | --- | --- |
| Primary layer | Transport | Messaging protocol running over transport |
| Unit of exchange | WebSocket text/binary message | STOMP frame inside a WebSocket payload |
| Application format | Self-chosen JSON, text, binary, Protobuf... | STOMP command/headers/body; body may be JSON/binary |
| Routing | Written by the application | Broker destinations and subscriptions |
| Subscribe/unsubscribe | Must define custom protocol if needed | `SUBSCRIBE` / `UNSUBSCRIBE` |
| Publish | Self-defined and implemented | `SEND` to destination |
| ACK/NACK | Self-defined | Present in STOMP; broker must support it |
| Heartbeat | WebSocket Ping/Pong or application-defined | Negotiated STOMP heartbeat, separate from Ping/Pong |
| Broadcast/fan-out | Written by app or integrated broker | Simple broker or external broker relay |
| Backpressure | Application's own API and design | Depends on library/broker; STOMP does not inherently carry Reactive Streams demand |
| Protocol complexity | Less overhead if business logic is simple | Overhead from commands/headers and subscription state |
| Best suited for | Games, sensor streams, binary feeds, custom protocols | Chat rooms, notification topics, multi-client pub/sub apps |
| Spring WebFlux | `WebSocketHandler`, `WebSocketSession`, `Flux`, `Mono` | Does not automatically provide a full STOMP broker via reactive WebSocketHandler alone |
| Built-in Spring STOMP support | Not required | `@EnableWebSocketMessageBroker`, `@MessageMapping`, `SimpMessagingTemplate` in Servlet WebSocket messaging support |

Neither option is inherently faster than the other in every situation. STOMP adds protocol overhead while reducing custom routing/subscription code. Raw WebSocket can reduce overhead in fixed-message systems, while shifting responsibility for protocol guarantees, authorization, and operations onto the application.

## 4. Two Handshakes: WebSocket Handshake and STOMP CONNECT

When using STOMP over WebSocket, there are **two session-establishment layers**:

~~~text
Browser / STOMP client                         Server
        |                                         |
        | -- HTTP GET Upgrade: websocket ------>  |
        | <-- HTTP 101 Switching Protocols -----  |
        |                                         |
        | ==== WebSocket transport is open ====== |
        |                                         |
        | -- WebSocket payload: CONNECT frame --> |
        | <-- WebSocket payload: CONNECTED -----  |
        |                                         |
        | ==== STOMP messaging session ready ==== |
        |                                         |
        | -- SUBSCRIBE destination:/topic/... --> |
        | -- SEND destination:/app/... ---------> |
        | <-- MESSAGE destination:/topic/... ---- |
~~~

HTTP status **101 Switching Protocols** confirms switching the transport protocol to WebSocket. It is not STOMP `CONNECTED`.

The `Sec-WebSocket-Protocol` header can be used by client and server to negotiate a WebSocket subprotocol, such as `v12.stomp`. If the application intends to use STOMP, this negotiation must align with server/client configuration. Completing a WebSocket handshake and then sending raw JSON to a STOMP endpoint usually violates the protocol; conversely, sending a STOMP `CONNECT` to a raw echo WebSocket will just be treated as a text payload unless the handler implements a STOMP parser.

In a JavaScript client:

~~~javascript
// Raw WebSocket: application-designed payload.
const rawSocket = new WebSocket("ws://localhost:8080/ws/raw");
rawSocket.onopen = () => rawSocket.send("ping");

// STOMP requires a STOMP client library and a STOMP CONNECT frame.
// new WebSocket(...) alone does not create a STOMP session.
~~~

## 5. How Do WebSocket Frames Differ from STOMP Frames?

WebSocket defines text/binary messages, Ping/Pong control frames, and Close frames. Frame fragmentation belongs to the transport. Text data can contain a JSON document:

~~~json
{
  "type": "subscribe",
  "channel": "orders",
  "orderId": 42
}
~~~

This is a **custom-designed JSON protocol**. The browser sends it and the server understands it only because both sides agreed on the fields `type`, `channel`, `orderId`, and their semantics. WebSocket has no concept of which field is a destination or subscription.

A STOMP frame has the structure:

~~~text
COMMAND
header-1:value-1
header-2:value-2

body<NULL>
~~~

`<NULL>` here represents **a single NUL byte (0x00)** terminating the frame, not the literal character string "<NULL>" sent over the wire. A frame consists of a command line, header lines, a blank line, and then the body. A STOMP protocol parser must split frames according to STOMP framing, never assuming one WebSocket callback always equals one complete STOMP frame.

Example sending JSON content over STOMP:

~~~text
SEND
destination:/app/orders
content-type:application/json

{"orderId":42,"action":"confirm"}<NULL>
~~~

STOMP adds a routing and control layer; the body itself can still be JSON. STOMP does not replace JSON, and JSON does not automatically turn a raw WebSocket into STOMP.

**Parser warning:** STOMP 1.2 supports `content-length`, header escaping, frame boundaries, multiple commands/headers, and newline-byte heartbeats. If implementing a STOMP parser yourself, follow the specification; never just `split("\n")` or assume "every WebSocket message contains exactly one STOMP frame."

## 6. Important STOMP Frames

| Frame | Typically Sent By | Role |
| --- | --- | --- |
| `CONNECT` or `STOMP` | Client | Requests opening a STOMP session, version, and heartbeats |
| `CONNECTED` | Server | Confirms the selected version |
| `SUBSCRIBE` | Client | Subscribes to a destination with a subscription ID |
| `UNSUBSCRIBE` | Client | Cancels a subscription by ID |
| `SEND` | Client | Sends a message to a destination |
| `MESSAGE` | Server | Delivers a message to a subscription |
| `ACK` | Client | Acknowledges a message per ack mode |
| `NACK` | Client | Reports failure to process a message |
| `BEGIN` / `COMMIT` / `ABORT` | Client | Controls transactions when supported by the broker |
| `RECEIPT` | Server | Confirms a frame requesting a receipt was processed |
| `ERROR` | Server | Reports a protocol or processing error |
| `DISCONNECT` | Client | Requests ending the STOMP session |

At minimum, a STOMP 1.2 client must provide `accept-version` and `host` in `CONNECT`:

~~~text
CONNECT
accept-version:1.2
host:localhost
heart-beat:10000,10000

<NULL>
~~~

If the server accepts:

~~~text
CONNECTED
version:1.2
heart-beat:10000,10000

<NULL>
~~~

Then the client can subscribe:

~~~text
SUBSCRIBE
id:sub-1
destination:/topic/greetings
ack:auto

<NULL>
~~~

And send a message:

~~~text
SEND
destination:/app/hello
content-type:application/json

{"name":"An"}<NULL>
~~~

A message pushed by the server to subscribers carries metadata:

~~~text
MESSAGE
subscription:sub-1
message-id:message-7
destination:/topic/greetings
content-type:application/json

{"content":"Xin chào, An!"}<NULL>
~~~

The IDs and bodies above are illustrative examples, not fixed values Spring always generates. Destination names, ACK/NACK capabilities, transactions, and delivery semantics are determined by the broker/server; the STOMP specification does not guarantee that a `/queue` prefix always corresponds to a durable queue.

## 7. A Destination Is Not a WebSocket URL

This is one of the most critical misconceptions.

- `ws://localhost:8081/ws-stomp` is the **URL to establish the WebSocket connection**.
- `/app/hello` is a **STOMP destination for commands from client to application handler** in the example Spring configuration.
- `/topic/greetings` is a **STOMP destination for clients to subscribe and receive broadcasts**.
- `/queue/...` is a conventional destination prefix; exact semantics depend on the message broker and configuration.

A single WebSocket connection can carry **multiple STOMP subscriptions**. Clients do not need to open a separate WebSocket for each destination.

In a common Spring STOMP configuration:

~~~java
registry.setApplicationDestinationPrefixes("/app");
registry.enableSimpleBroker("/topic", "/queue");
~~~

This means:

1. A STOMP `SEND` message to `/app/hello` is routed to `@MessageMapping("/hello")`.
2. `SUBSCRIBE` to `/topic/greetings` is managed by the broker.
3. The return value from `@MessageMapping` can be sent to `/topic/greetings` via `@SendTo` or `SimpMessagingTemplate`.
4. A prefix is not an HTTP controller route, not a WebFlux `@GetMapping`, and not a Spring Security authorization rule.

In Spring's simple broker, `/topic` and `/queue` do not inherently enforce distinct routing semantics; they are primarily configured conventions. External brokers may attach different semantics.

## 8. Spring: The Key Boundary Between WebFlux and Built-In STOMP Support

Within the Spring ecosystem, there are two related documentation and API branches:

**A. Reactive WebFlux WebSocket**

- Main module: `spring-webflux`.
- Server endpoints use `org.springframework.web.reactive.socket.WebSocketHandler`.
- `handle(WebSocketSession)` returns `Mono<Void>`.
- `receive()` is `Flux<WebSocketMessage>`, `send(...)` is `Mono<Void>`.
- Fits Reactor Netty/Reactive Streams and application-defined protocols.
- Raw WebSocket does not inherently include `@MessageMapping`, destination brokers, or a STOMP subscription manager.

**B. Spring STOMP-over-WebSocket Messaging**

- Configuration is documented by Spring Framework under **Servlet-stack WebSocket messaging**.
- Modules `spring-messaging` and `spring-websocket`.
- Uses `@EnableWebSocketMessageBroker`, `WebSocketMessageBrokerConfigurer`, `@MessageMapping`, `@SendTo`, `SimpMessagingTemplate`.
- Clients send/receive STOMP frames; Spring decodes and routes them through messaging channels/brokers.
- Spring Boot 3.5's `spring-boot-starter-websocket` brings dependencies for MVC web support, messaging, and websocket.

**Do not assume that adding `@EnableWebSocketMessageBroker` to an application containing only `spring-boot-starter-webflux` on Reactor Netty will automatically spin up a STOMP broker working like the Servlet sample.** These are two distinct programming models; Spring Boot also typically prioritizes MVC when both MVC and WebFlux starters are present. To use built-in STOMP messaging, choose the matching stack/configuration or an external STOMP library/server rather than confusing it with reactive WebSocketHandler.

Quick decision table:

| Need | Approach to Consider |
| --- | --- |
| Keep reactive WebFlux/Netty app, custom protocol | WebFlux WebSocketHandler |
| WebFlux/Netty but clients require STOMP | Choose a suitable STOMP-capable server/broker gateway; evaluate integration and architecture separately |
| Standard Spring `@MessageMapping`, simple broker | Spring Servlet WebSocket messaging |
| Thousands of subscriptions, broker clustering, ACK/receipt | STOMP broker relay to RabbitMQ/ActiveMQ or suitable broker |
| Only pushing a one-way feed | SSE/HTTP streaming is also worth considering |
| Clients need standardized pub/sub across many topics | STOMP can reduce application routing code |

**STOMP is not WebFlux's default**, and **WebFlux does not force applications to use STOMP**. Sharing the word "WebSocket" does not mean APIs/configurations can be swapped between the two stacks.

## 9. Processing Flow of Spring STOMP Messaging

In Spring Servlet STOMP messaging, the flow typically looks like:

~~~text
Browser STOMP client
        |
        v
WebSocket transport /ws-stomp
        |
        v
STOMP decoder
        |
        v
clientInboundChannel
        |
        +--> destination /app/hello
        |         |
        |         v
        |   @MessageMapping("/hello")
        |         |
        |         v
        |    @SendTo("/topic/greetings")
        |         |
        |         v
        |      brokerChannel
        |         |
        |         v
        +--> simple broker / external broker relay
                  |
                  v
           clientOutboundChannel
                  |
                  v
             MESSAGE frame
                  |
                  v
        Browser subscription callback
~~~

For `SUBSCRIBE /topic/greetings`, the broker stores the subscription. For `SEND /app/hello`, the application controller processes the payload and forwards the response through the broker. These messaging channels are distinct from HTTP controller invocation in WebFlux's DispatcherHandler.

Spring can replace the simple broker with a broker relay to forward STOMP to an external broker over TCP. The relay does not turn each browser WebSocket into a direct connection from the browser to RabbitMQ; Spring remains a gateway layer.

## 10. Simple Broker vs. External Broker Relay

Spring lets you enable the built-in simple broker:

~~~java
registry.enableSimpleBroker("/topic", "/queue");
~~~

The simple broker stores subscriptions in memory and forwards messages to matching clients. It is convenient for demos or simple pub/sub, but has notable limitations:

- Does not fully support STOMP acknowledgements, receipts, and many advanced features.
- Not designed for true broker clustering.
- Subscription state resides in the application process; do not treat it as a persistent queue.
- After a server restart, subscriptions must be re-established by clients.
- Delivery success must not be treated as business transaction success.

When queue semantics, ACK/NACK, receipts, durable messaging, multi-node scaling, or retry/redelivery are needed, consider an external broker:

~~~java
registry.enableStompBrokerRelay("/topic", "/queue");
registry.setApplicationDestinationPrefixes("/app");
~~~

The relay requires an active STOMP broker and proper connection/credential configuration. Specific capabilities depend on RabbitMQ, ActiveMQ, or another broker; do not assume every broker behaves identically.

**An evaluation trap:** STOMP has an `ACK` command in its specification, yet **Spring's simple broker does not automatically support all ACK/receipt semantics**. Never promise "exactly-once is guaranteed" simply because STOMP is used. Verify implementation, persistence, idempotency, and message-processing policies.

## 11. Heartbeat: WebSocket Ping/Pong Differs from STOMP Heartbeat

WebSocket has protocol-level Ping/Pong control frames. STOMP 1.1/1.2 has its own heartbeat negotiated via `heart-beat:cx,cy` and `heart-beat:sx,sy`.

- `cx`: minimum heartbeat send interval the client can guarantee.
- `cy`: interval at which the client wants to receive heartbeats from the server.
- `sx`: minimum heartbeat send interval the server can guarantee.
- `sy`: interval at which the server wants to receive heartbeats from the client.

When both corresponding values are non-zero, the expected interval in that direction is the larger of the two agreed values. For example, if the client sends `heart-beat:10000,10000` and the server replies `heart-beat:5000,5000`, both sides expect activity at least roughly every 10 seconds in each direction, with tolerance for scheduling/network jitter.

When neither side has an actual STOMP frame to send, a STOMP heartbeat is a single newline byte (EOL). That is **not** a WebSocket Ping frame and not JSON `{"type":"heartbeat"}`.

Raw WebSocket:

~~~text
WS Ping  --> WS Pong (control frame)
~~~

STOMP over WebSocket:

~~~text
STOMP CONNECT heart-beat:10000,10000
STOMP CONNECTED heart-beat:5000,5000
... EOL bytes on the WebSocket transport while idle
~~~

Do not configure overly frequent heartbeats across tens of thousands of connections without measuring cost. Proxy idle timeouts, broker heartbeat policies, and WebSocket transport timeouts can all affect liveness.

## 12. ACK/NACK and Reliability Levels

STOMP defines three acknowledgement modes in SUBSCRIBE:

| Mode | Meaning |
| --- | --- |
| `auto` | Broker considers the message delivered upon sending; no explicit ACK required |
| `client` | Client ACKs cumulatively for preceding messages in the subscription |
| `client-individual` | Individual ACK/NACK per message |

Example:

~~~text
SUBSCRIBE
id:orders-1
destination:/queue/orders
ack:client-individual

<NULL>
~~~

The server sends a MESSAGE and may include an `ack` header; the client ACKs using that header ID:

~~~text
ACK
id:ack-token-from-message

<NULL>
~~~

**ACK here does not automatically prove the application committed to a database successfully.** The application must define the "finish processing before ACK" boundary, use transactions/idempotency, and understand the broker's redelivery policy.

STOMP `RECEIPT` differs from `ACK`:

- `RECEIPT` confirms the broker/server processed a client frame carrying a receipt request.
- `ACK` confirms consumption of a MESSAGE per subscription mode.
- Neither creates end-to-end exactly-once semantics without additional application design.

Raw WebSocket has no application-layer ACK/NACK; achieving something similar requires implementing message IDs, pending tables, timeouts, retries, duplicate handling, and persistence yourself.

## 13. Authentication, Authorization, and Security

Both models require security, though the control points differ.

### 13.1. Handshake Authentication

WebSocket starts with an HTTP handshake. You can use cookies/sessions or supported authentication mechanisms before upgrading the connection. In browsers, the WebSocket API does not allow setting arbitrary HTTP Authorization headers like fetch; if tokens are needed, design an appropriate handshake/cookie/subprotocol/first-message strategy and avoid putting tokens in URLs or logs.

### 13.2. STOMP Authentication and Destination Authorization

STOMP messaging also has a CONNECT step and destinations such as `/app/*`, `/topic/*`, or user destinations. You must:

- Authenticate the session and attach a Principal.
- Validate/verify CONNECT and message headers from untrusted sources.
- Authorize `SEND`/`SUBSCRIBE` by user, role, and resource ID.
- Never trust client-declared `userId`, `accountId`, or arbitrary destinations.
- Limit subscription count, message size, and SEND rate.
- Enforce allowed origins/cross-origin usage when using cookie authentication.
- Account for CSRF and Spring Security's authorization model for inbound STOMP.

A raw WebSocket application must perform equivalent permission checks on its custom-defined messages. Using STOMP does not make a system automatically secure. Subscribing to `/topic/private/order-42` merely by knowing the name is not proof the user is allowed to read order 42.

### 13.3. WSS

In production, prefer `wss://` over TLS. STOMP over `ws://` is not encrypted simply because its framing has commands and headers. Never log STOMP `passcode`, tokens, or bodies containing PII.

## 14. Backpressure and Operational Responsibilities

In raw WebFlux, `Flux`/`Mono` APIs express demand and cancellation. Still, network buffers and slow clients need limits: unbounded queues, large messages, and infinite sources can all drive memory growth.

In Spring STOMP messaging, channels/brokers have their own executors and outbound buffers. A STOMP subscription is **not equivalent** to Reactive Streams `request(n)`. When handling large payloads, slow connections, or many subscribers, monitor:

- Active WebSocket sessions and STOMP subscriptions.
- Inbound/outbound message throughput.
- Queue depth, send times, send buffers.
- Session disconnects/abnormal closures.
- Broker relay availability and reconnects.
- Missed heartbeats.
- Publish-to-delivery latency.
- Consumer lag and ACK/NACK/redeliveries where supported by the broker.
- Broker memory and resources.

If STOMP connects browsers to an external broker, clearly delineate where the broker handles persistence, retries, and fan-out, and where the application gateway handles authentication, authorization, and validation.

## 15. Demo A — Raw WebFlux WebSocket (Java 17+)

The first demo proves raw WebSocket **without STOMP**. A WebSocket endpoint receives text messages and replies with text prefixed by `raw:`.

### 15.1. Project Structure

~~~text
raw-webflux-websocket/
  build.gradle
  src/main/java/demo/raw/
    RawApp.java
    RawEchoHandler.java
    RawWebSocketConfig.java
  src/test/java/demo/raw/
    RawWebSocketTest.java
~~~

### 15.2. build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.6'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo.raw'
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
~~~

Do not add `spring-boot-starter-websocket` to this raw demo: that starter typically pulls in Spring MVC/Servlet messaging, which is unnecessary for a WebFlux handler on Reactor Netty.

### 15.3. RawApp.java

~~~java
package demo.raw;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RawApp {
    public static void main(String[] args) {
        SpringApplication.run(RawApp.class, args);
    }
}
~~~

### 15.4. RawEchoHandler.java

~~~java
package demo.raw;

import org.springframework.stereotype.Component;
import org.springframework.web.reactive.socket.WebSocketHandler;
import org.springframework.web.reactive.socket.WebSocketMessage;
import org.springframework.web.reactive.socket.WebSocketSession;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Component
public class RawEchoHandler implements WebSocketHandler {

    @Override
    public Mono<Void> handle(WebSocketSession session) {
        Flux<WebSocketMessage> outgoing = session.receive()
            .map(WebSocketMessage::getPayloadAsText)
            .map(text -> session.textMessage("raw:" + text));

        return session.send(outgoing);
    }
}
~~~

Here there are only WebSocket messages. If the client sends `ping`, the server returns `raw:ping`. If the client sends JSON, the server simply prepends the prefix to the raw text without inspecting destinations or subscriptions.

### 15.5. RawWebSocketConfig.java

~~~java
package demo.raw;

import java.util.Map;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.HandlerMapping;
import org.springframework.web.reactive.handler.SimpleUrlHandlerMapping;
import org.springframework.web.reactive.socket.WebSocketHandler;

@Configuration
public class RawWebSocketConfig {

    @Bean
    HandlerMapping webSocketMapping(RawEchoHandler handler) {
        SimpleUrlHandlerMapping mapping =
            new SimpleUrlHandlerMapping();

        mapping.setUrlMap(Map.<String, WebSocketHandler>of(
            "/ws/raw", handler
        ));
        mapping.setOrder(-1);
        return mapping;
    }
}
~~~

Spring Boot WebFlux provides the corresponding WebSocket handling configuration. If building a WebFlux app purely via manual configuration without WebFlux config, you must additionally register `WebSocketHandlerAdapter` per Spring documentation.

### 15.6. RawWebSocketTest.java

~~~java
package demo.raw;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.net.URI;
import java.time.Duration;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.web.reactive.socket.CloseStatus;
import org.springframework.web.reactive.socket.client.ReactorNettyWebSocketClient;
import org.springframework.web.reactive.socket.client.WebSocketClient;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
class RawWebSocketTest {

    @LocalServerPort
    int port;

    @Test
    void rawWebSocketEchoesPlainText() {
        WebSocketClient client = new ReactorNettyWebSocketClient();
        AtomicReference<String> received = new AtomicReference<>();

        URI uri = URI.create("ws://localhost:" + port + "/ws/raw");

        Mono<Void> result = client.execute(uri, session ->
            Mono.when(
                session.send(
                    Mono.just(session.textMessage("ping"))
                ),
                session.receive()
                    .next()
                    .doOnNext(message ->
                        received.set(message.getPayloadAsText()))
                    .then()
            ).then(session.close(CloseStatus.NORMAL))
        );

        StepVerifier.create(result)
            .expectComplete()
            .verify(Duration.ofSeconds(10));

        assertEquals("raw:ping", received.get());
    }
}
~~~

The test demonstrates a real WebSocket client sending a single text message, receiving the reply, and closing the session. No STOMP frames or STOMP client library are needed.

### 15.7. Running and Testing via Browser

From the demo directory:

~~~bash
./gradlew bootRun
~~~

Or if Gradle is installed:

~~~bash
gradle bootRun
~~~

Browser console:

~~~javascript
const socket = new WebSocket("ws://localhost:8080/ws/raw");

socket.onopen = () => {
    socket.send("ping");
    socket.send('{"type":"subscribe","channel":"orders"}');
};

socket.onmessage = event => console.log(event.data);
socket.onclose = event => console.log("closed", event.code);
~~~

Data emitted by the server in this example:

~~~text
raw:ping
raw:{"type":"subscribe","channel":"orders"}
~~~

The JSON line does not create an actual subscription; the raw server has no router for the `type` field. This clearly demonstrates that WebSocket only transports payloads, and all semantics must be built by the application.

## 16. Demo B — Spring STOMP Messaging (Servlet Stack, Java 17+)

The second demo is **a separate Spring Boot project**, running independently on port 8081. It uses STOMP over WebSocket, the simple broker, `@MessageMapping`, and `@SendTo`. Do not merge this project's code into the WebFlux/raw demo or assume the two configurations are alike.

### 16.1. Project Structure

~~~text
stomp-mvc-messaging/
  build.gradle
  src/main/java/demo/stomp/
    StompApp.java
    StompConfig.java
    GreetingController.java
    HelloRequest.java
    Greeting.java
  src/main/resources/
    application.properties
    static/stomp-client.html
  src/test/java/demo/stomp/
    GreetingControllerTest.java
~~~

### 16.2. build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.6'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo.stomp'
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
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

`spring-boot-starter-websocket` brings in the dependencies needed for Spring MVC WebSocket messaging. Do not add `spring-boot-starter-webflux` to "enable STOMP"; those are two different technical branches.

### 16.3. application.properties

~~~properties
spring.application.name=stomp-mvc-messaging
server.port=8081
~~~

### 16.4. StompApp.java

~~~java
package demo.stomp;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class StompApp {
    public static void main(String[] args) {
        SpringApplication.run(StompApp.class, args);
    }
}
~~~

### 16.5. StompConfig.java

~~~java
package demo.stomp;

import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.simp.config.MessageBrokerRegistry;
import org.springframework.web.socket.config.annotation.EnableWebSocketMessageBroker;
import org.springframework.web.socket.config.annotation.StompEndpointRegistry;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;

@Configuration
@EnableWebSocketMessageBroker
public class StompConfig implements WebSocketMessageBrokerConfigurer {

    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/ws-stomp");
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.setApplicationDestinationPrefixes("/app");
        registry.enableSimpleBroker("/topic");
    }
}
~~~

`/ws-stomp` is the WebSocket handshake path. `/app` routes to application controllers. `/topic` routes to the simple broker. These are three distinct concepts.

### 16.6. HelloRequest.java

~~~java
package demo.stomp;

public record HelloRequest(String name) {
}
~~~

### 16.7. Greeting.java

~~~java
package demo.stomp;

public record Greeting(String content) {
}
~~~

### 16.8. GreetingController.java

~~~java
package demo.stomp;

import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.SendTo;
import org.springframework.stereotype.Controller;

@Controller
public class GreetingController {

    @MessageMapping("/hello")
    @SendTo("/topic/greetings")
    public Greeting greet(HelloRequest request) {
        String name = request.name() == null
            ? "khách"
            : request.name().strip();

        if (name.isEmpty()) {
            name = "khách";
        }

        return new Greeting("Xin chào, " + name + "!");
    }
}
~~~

The client sends `SEND destination:/app/hello` with JSON body `{"name":"An"}`. Spring converts the payload to HelloRequest, calls `greet`, converts Greeting into a MESSAGE, and the broker broadcasts it to subscribers of `/topic/greetings`.

This is a messaging controller, **not an HTTP `@PostMapping("/app/hello")`** endpoint. HTTP GET/POST to /app/hello will not invoke this method.

### 16.9. static/stomp-client.html

The following HTML page uses a JavaScript STOMP client via a UMD bundle for quick testing. In production, install the package via npm and bundle it yourself rather than relying on an unmanaged CDN.

~~~html
<!doctype html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <title>STOMP demo</title>
</head>
<body>
    <h1>STOMP messaging demo</h1>
    <input id="name" value="An">
    <button id="send" disabled>Send greeting</button>
    <ul id="messages"></ul>

    <script src="https://cdn.jsdelivr.net/npm/@stomp/stompjs@7/bundles/stomp.umd.min.js"></script>
    <script>
        const scheme = location.protocol === "https:" ? "wss:" : "ws:";
        const brokerURL = scheme + "//" + location.host + "/ws-stomp";

        const client = new StompJs.Client({
            brokerURL: brokerURL,
            reconnectDelay: 5000,
            heartbeatIncoming: 10000,
            heartbeatOutgoing: 10000
        });

        client.onConnect = () => {
            client.subscribe("/topic/greetings", message => {
                const greeting = JSON.parse(message.body);
                const item = document.createElement("li");
                item.textContent = greeting.content;
                document.getElementById("messages").appendChild(item);
            });

            document.getElementById("send").disabled = false;
        };

        client.onStompError = frame => {
            console.error("STOMP ERROR", frame.headers["message"]);
        };

        client.onWebSocketClose = event => {
            console.log("WebSocket closed:", event.code);
            document.getElementById("send").disabled = true;
        };

        document.getElementById("send").addEventListener("click", () => {
            const name = document.getElementById("name").value;

            client.publish({
                destination: "/app/hello",
                body: JSON.stringify({name: name}),
                headers: {"content-type": "application/json"}
            });
        });

        client.activate();

        window.addEventListener("beforeunload", () => {
            client.deactivate();
        });
    </script>
</body>
</html>
~~~

Visit `http://localhost:8081/stomp-client.html`. Once STOMP is CONNECTED, the Send greeting button is enabled. When clicked, the STOMP client publishes to `/app/hello`, and the subscription receives the Greeting JSON from `/topic/greetings`.

Using `textContent` prevents the browser from interpreting the greeting content as arbitrary HTML. In real applications, you must still validate inputs and authorize destinations.

### 16.10. GreetingControllerTest.java

~~~java
package demo.stomp;

import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.Test;

class GreetingControllerTest {

    private final GreetingController controller =
        new GreetingController();

    @Test
    void createsGreetingForName() {
        Greeting response =
            controller.greet(new HelloRequest("An"));

        assertEquals("Xin chào, An!", response.content());
    }

    @Test
    void usesGuestNameWhenBlank() {
        Greeting response =
            controller.greet(new HelloRequest("  "));

        assertEquals("Xin chào, khách!", response.content());
    }
}
~~~

These tests only verify the transformation inside `greet`; they **do not** verify broker wiring or the WebSocket handshake. To test end-to-end, use a real STOMP client connecting through `/ws-stomp`, subscribing to `/topic/greetings`, sending `SEND /app/hello`, and verifying the callback receives MESSAGE.

### 16.11. Running the Application

~~~bash
./gradlew bootRun
~~~

Or:

~~~bash
gradle bootRun
~~~

Open the page:

~~~text
http://localhost:8081/stomp-client.html
~~~

Click Send greeting with the name "An". The UI receives:

~~~text
Xin chào, An!
~~~

Run unit tests:

~~~bash
./gradlew test
~~~

This outcome differs from the raw demo: the STOMP client manages CONNECT/SUBSCRIBE/SEND, the controller receives messages by destination, and the broker fans out to subscribers. STOMP provides messaging semantics that raw WebSocket does not include out of the box.

## 17. Choosing a Solution for Real-World Scenarios

### Case A: Games or High-Speed Price Feeds with Binary Data

Raw WebSocket is often worth considering if:

- The message schema is tightly controlled between a specific group of clients and servers.
- A compact binary format such as Protobuf or custom bytes is needed.
- You already have a custom routing/connection manager.
- You need protocol-specific control over scheduling, queues, and backpressure.

However, you must design message types, versioning, authorization, subscriptions (if any), recovery, and monitoring yourself.

### Case B: Chat Rooms and Notification Subscriptions

STOMP is advantageous if:

- Clients need to subscribe/unsubscribe to multiple topics over one WebSocket.
- There are many producers and consumers.
- You want destination-to-`@MessageMapping` routing.
- You want broker-backed broadcasting.
- You may need an external broker later.

You must accept the overhead of framing, broker state, and monitoring message channels.

### Case C: Large WebFlux System Running on Reactor Netty

Do not simply swap `WebSocketHandler` for `@MessageMapping`. Make an explicit architectural choice:

1. Keep raw WebSocket with a compact custom protocol, while connecting to a broker using an appropriate reactive client if needed.
2. Separate a dedicated Servlet STOMP gateway responsible for WebSocket messaging, connecting to reactive backend services via APIs or a message broker.
3. Use a STOMP-capable gateway or broker and configure clients accordingly.
4. If only pushing one-way updates, evaluate SSE to reduce complexity.

This is an architectural decision, not merely changing an annotation.

### Case D: Delivery Guarantees Required

Do not choose STOMP solely because it has an ACK command. Ask:

- Which broker truly supports ACK/NACK?
- Is there persistence or durable subscriptions?
- When a client reconnects, which messages are replayed?
- Where are message IDs/idempotency keys managed?
- Does the client ACK after successful processing or immediately on receipt?
- Do multiple nodes share subscription/queue state?

If these answers are unclear, STOMP alone will not magically provide delivery guarantees.

## 18. Migrating from Raw WebSocket to STOMP

Changing protocols requires updates on both client and server. You cannot keep a raw browser WebSocket client sending plain JSON directly and expect Spring STOMP to understand it automatically.

### 18.1. Protocol

Before:

~~~json
{"type":"join","room":"general"}
~~~

After: the STOMP client sends `SUBSCRIBE` to a destination with an explicit contract:

~~~text
SUBSCRIBE
id:room-general
destination:/topic/chat/general

<NULL>
~~~

Before:

~~~json
{"type":"chat","room":"general","message":"hello"}
~~~

After:

~~~text
SEND
destination:/app/chat/general
content-type:application/json

{"message":"hello"}<NULL>
~~~

### 18.2. Server API

- Replace raw `WebSocketHandler.handle(session)` with a Spring STOMP message handler on a supported stack.
- Define application destination prefixes and broker destinations.
- Use `@MessageMapping` for messages sent to the application.
- Use `@SendTo` or `SimpMessagingTemplate` for broadcasts.
- Authorize SUBSCRIBE/SEND per destination and user.
- Design reconnects, heartbeats, ACKs, and error handling matching the broker.

### 18.3. Client API

- Choose a STOMP client library.
- Open the WebSocket transport, send CONNECT, and wait for CONNECTED.
- Subscribe after the STOMP connection succeeds.
- Publish to application destinations.
- Unsubscribe and deactivate/disconnect when leaving the page.
- On reconnect, re-register subscriptions per the library's lifecycle.
- Handle STOMP ERROR and WebSocket close events separately.

### 18.4. Migration Testing

| Test | What to Prove |
| --- | --- |
| WebSocket handshake | URL and subprotocol negotiate properly |
| STOMP CONNECT | CONNECTED is received before publishing |
| Subscribe | Broker registers the right destination |
| Send | @MessageMapping receives the right payload |
| Broadcast | Correct subscribers receive MESSAGE |
| Unauthorized subscribe | Client cannot read topics outside its permissions |
| Invalid payload | Errors are handled without leaking details |
| Heartbeat | Timeouts/reconnects follow configuration |
| Reconnect | Subscriptions recover per policy |
| Multi-node | External broker or sticky sessions are configured properly |
| Slow client | Queues/outbound limits and monitoring work |

## 19. Common Mistakes

| Misconception | Why It Is Wrong | Fix |
| --- | --- | --- |
| WebSocket natively understands SEND/SUBSCRIBE | RFC 6455 does not define STOMP | Use a STOMP client/server or define a custom protocol |
| STOMP is a newer version of WebSocket | STOMP runs on top of WebSocket | Distinguish transport from messaging protocol |
| Using `new WebSocket(url)` gives you STOMP | The browser only opens the transport | Use a STOMP library and CONNECT |
| `/topic/x` is an HTTP endpoint | It is a STOMP destination | Use SUBSCRIBE with that destination |
| `@MessageMapping` works automatically in raw WebFlux | WebFlux WebSocketHandler is not a STOMP broker | Choose a compatible Spring STOMP configuration/stack |
| Adding `spring-boot-starter-websocket` to "enable STOMP" in Netty WebFlux | Starter 3.5 pulls in the MVC Servlet web stack | Separate the models and check the effective application type |
| `/queue` is always durable | A prefix does not define delivery semantics | Check the broker, persistence, and policies |
| Simple broker supports full ACK/receipt | Simple broker supports only a subset | Use a broker supporting the needed features |
| ACK means exactly-once | ACK is only a messaging-layer acknowledgement | Use idempotency, transactions, and recovery |
| STOMP heartbeat is a WebSocket Ping | Two mechanisms at different layers | Configure and monitor independently |
| STOMP ERROR is the same as a WS Close code | Different protocol layers | Handle ERROR frames and close events separately |
| HTTP 101 means CONNECTED | Only confirms the WS upgrade | Wait for STOMP CONNECTED |
| Adding subscriptions needs no authorization | Topic names do not prove read permissions | Authorize SUBSCRIBE per resource/user |
| A wss connection guarantees valid payloads | TLS does not validate business data | Validate schemas, rate limits, and permissions |
| Using STOMP automatically scales multi-node | Simple broker holds state in memory | Use an external broker/relay and HA design |
| Using raw WebSocket for everything | Forces rebuilding pub/sub/retry from scratch | Compare cost against STOMP/SSE/brokers |

## 20. Design Checklist

Before deciding on a protocol, answer:

1. Does the application need full-duplex or only one-way server push?
2. Do clients have multiple subscriptions/destinations or a single simple stream?
3. Are payloads mainly text/JSON or high-speed binary?
4. Is broker-backed broadcasting needed, or does the server manage a single connection?
5. Is the current framework WebFlux reactive or Servlet MVC?
6. Are the right Spring starters/modules selected for that stack?
7. Are ACK, NACK, RECEIPT, persistence, and redelivery required?
8. Does the actual broker support the required features?
9. Are destination prefixes and access control defined?
10. On reconnect, do clients re-subscribe and recover state properly?
11. Are heartbeats and transport Ping/Pong understood separately?
12. Are message sizes, rates, subscriptions, and queues bounded?
13. Are there tests for handshake, CONNECTED, SEND, SUBSCRIBE, authorization, and close?
14. Are there metrics for active connections, broker subscriptions, dropped messages, and latency?
15. Is there a protocol version upgrade plan when schemas change?

## 21. Self-Check Questions with Answers

**Question 1.** Does WebSocket define a message named `SUBSCRIBE`?

**Answer:** No. WebSocket is a transport with text/binary/control frames. SUBSCRIBE is a command belonging to STOMP.

**Question 2.** Does STOMP require using WebSocket?

**Answer:** No. STOMP is a messaging protocol that can run over any reliable two-way streaming transport, such as TCP or WebSocket.

**Question 3.** How does HTTP 101 differ from STOMP CONNECTED?

**Answer:** HTTP 101 confirms upgrading the transport to WebSocket; CONNECTED confirms the STOMP session afterward.

**Question 4.** How does a WebSocket URL differ from a STOMP destination?

**Answer:** The URL selects the handshake endpoint; destinations are used in SEND/SUBSCRIBE to route messages inside the STOMP connection.

**Question 5.** Does using WebFlux WebSocketHandler automatically support @MessageMapping?

**Answer:** No. @MessageMapping is part of Spring STOMP messaging support configured in a compatible model, not a built-in feature of raw WebFlux WebSocketHandler.

**Question 6.** What roles do `/app/hello` and `/topic/greetings` play in the Spring example?

**Answer:** /app/hello routes to @MessageMapping("/hello"); /topic/greetings is the destination broadcast by the broker to subscribers.

**Question 7.** Is the simple broker a persistent cluster-aware broker?

**Answer:** No. It is a simple in-memory broker unsuitable for full ACK/receipt/clustering features.

**Question 8.** How do ACK and RECEIPT differ?

**Answer:** ACK confirms consumption of a MESSAGE under a subscription mode; RECEIPT confirms processing of a frame carrying a receipt request. Neither creates end-to-end exactly-once delivery on its own.

**Question 9.** Is a STOMP heartbeat a WS Ping frame?

**Answer:** No. A STOMP heartbeat is an EOL byte at the messaging layer; WebSocket Ping/Pong are transport control frames.

**Question 10.** In a browser, is using new WebSocket(url) to send JSON to a raw handler considered STOMP?

**Answer:** No. That is a custom application protocol; STOMP requires STOMP frames/clients and a STOMP-capable server.

**Question 11.** Why must subscribe destinations be authorized?

**Answer:** Because knowing a topic name does not prove a user has permission to view the data. Every subscription/resource requires authorization.

**Question 12.** When should SSE be used instead of WebSocket/STOMP?

**Answer:** When you primarily need one-way server-pushed updates and do not need the browser to publish over the same connection.

## 22. Summary and References

- **WebSocket = full-duplex transport**; **STOMP = messaging protocol** over the transport.
- **WebSocket messages** do not inherently carry destinations; STOMP frames have commands, headers, bodies, and NUL terminators.
- **WebSocket URLs** differ from **STOMP destinations**.
- `HTTP 101` differs from `STOMP CONNECTED`.
- `CONNECT`, `SUBSCRIBE`, `SEND`, `MESSAGE`, `ACK`, `NACK`, `RECEIPT`, and `DISCONNECT` are STOMP commands, not WebSocket control frames.
- Spring WebFlux uses reactive `WebSocketHandler`; Spring STOMP messaging uses `@EnableWebSocketMessageBroker`/`@MessageMapping` in Servlet-stack support.
- The simple broker fits basic pub/sub; it does not promise full ACK, receipt, clustering, or persistence.
- STOMP heartbeats differ from WebSocket Ping/Pong.
- Transport, broker, and application must all enforce security, quotas, lifecycle management, and observability.
- Choose raw or STOMP based on actual requirements; never swap the two models merely because both use WebSocket.

Official Documentation:

1. [Spring Framework — WebFlux WebSockets](https://docs.spring.io/spring-framework/reference/web/webflux-websocket.html): reactive WebSocketHandler API, receive/send, handshake, and lifecycle.
2. [Spring Framework — STOMP Overview](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/overview.html): STOMP over WebSocket, destinations, message flow, and brokers.
3. [Spring Framework — Enable STOMP](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/enable.html): configuring @EnableWebSocketMessageBroker and destination prefixes.
4. [Spring Framework — STOMP Message Flow](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/message-flow.html): clientInboundChannel, brokerChannel, and clientOutboundChannel.
5. [Spring Framework — Annotated Controllers](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-annotations.html): @MessageMapping, @SendTo, @SubscribeMapping.
6. [Spring Framework — Simple Broker](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-simple-broker.html): in-memory subscriptions, heartbeats, and limitations.
7. [Spring Framework — External Broker Relay](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-broker-relay.html): TCP relay to external STOMP brokers, simple broker limitations.
8. [STOMP Protocol Specification 1.2](https://stomp.github.io/stomp-specification-1.2.html): framing, commands, ACK modes, heartbeats, receipts, and transactions.
9. [Spring Boot 3.5 — WebSockets](https://docs.spring.io/spring-boot/3.5/reference/messaging/websockets.html): starters and distinguishing reactive/Servlet web applications.
10. [Spring Getting Started — Messaging with STOMP over WebSocket](https://spring.io/guides/gs/messaging-stomp-websocket): Spring's step-by-step build guide.
