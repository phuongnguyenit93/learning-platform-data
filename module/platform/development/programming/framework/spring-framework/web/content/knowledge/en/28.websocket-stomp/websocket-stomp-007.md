# STOMP, Destinations, and Message Flow Through Spring Channels

## 1. Objectives and Big Picture

**WebSocket** provides a long-lived full-duplex connection between client and server, but it only defines how bytes/frames are transported; it does not prescribe whom a message is sent to, how clients subscribe, or what structure the content has. **STOMP (Simple Text Oriented Messaging Protocol)** adds a *frame*-based messaging protocol consisting of a command, headers, and a body. Spring Framework supports **STOMP over WebSocket** by mapping frames into **Spring Messages**, routing them through **MessageChannels**, invoking **@MessageMapping** methods, and forwarding results to the broker and subscribed clients.

In this lesson, distinguish **three kinds of addresses** often lumped together as "endpoints":

1. **WebSocket handshake endpoint**, e.g. **/ws**: the URL browsers use to open a WebSocket connection.
2. **Application destination**, e.g. **/app/chat.send**: a STOMP destination routed by Spring to **@MessageMapping("/chat.send")**.
3. **Broker destination**, e.g. **/topic/chat**: the address clients **SUBSCRIBE** to so the broker delivers messages to subscribers.

All three are configured by the application. They serve three different stages; **/ws is not where clients SEND STOMP messages**, and **/topic/chat does not invoke controllers** once prefixes are cleanly separated.

### Questions you should be able to answer afterward

- Why can **SEND** and **SUBSCRIBE** frames travel over the same WebSocket yet be handled by different components?
- What do **/app**, **/topic**, **/queue**, and **/user** mean, and which parts are determined by Spring configuration?
- Which channel does a message from the browser to **@MessageMapping** traverse, and which channel carries replies back to subscribers?
- What are the responsibilities of **clientInboundChannel**, **brokerChannel**, and **clientOutboundChannel**? Why should channel names not be confused with STOMP destinations?
- What is the difference between the **simple broker** and a **STOMP broker relay**, and how do you trace flow, ordering, and errors?

## 2. STOMP Frames: Protocol-Level Messages

A STOMP frame has the form:

~~~text
COMMAND
header-1:value
header-2:value

BODY<NUL>
~~~

**<NUL>** in the diagram denotes the frame-terminating byte **0x00**, not the literal characters `NUL`. The actual layout consists of the command line, header lines, a blank line, an optional body, and the terminating NUL byte. The body may be text or binary; for JSON, include an appropriate content-type header.

### Example connection and messaging sequence

The client opens a WebSocket to **ws://localhost:8080/ws**, then sends STOMP **CONNECT**:

~~~text
CONNECT
accept-version:1.2
heart-beat:10000,10000

<NUL>
~~~

The server responds with **CONNECTED** if the STOMP session is accepted:

~~~text
CONNECTED
version:1.2
heart-beat:0,0

<NUL>
~~~

To receive chat messages, the client sends **SUBSCRIBE**:

~~~text
SUBSCRIBE
id:sub-chat-1
destination:/topic/chat

<NUL>
~~~

The same client, or another client, sends **SEND** to have the server process a message:

~~~text
SEND
destination:/app/chat.send
content-type:application/json

{"from":"An","text":"Hello everyone"}<NUL>
~~~

If the controller emits the result to **/topic/chat**, the broker sends STOMP **MESSAGE** to each matching subscription:

~~~text
MESSAGE
subscription:sub-chat-1
destination:/topic/chat
message-id:msg-1
content-type:application/json

{"from":"An","text":"Hello everyone"}<NUL>
~~~

Illustrative frames may vary in actual headers, message-id, and heartbeat values depending on the broker/library; for example **msg-1** is just for readability, not a fixed value Spring always generates. STOMP also defines **UNSUBSCRIBE**, **DISCONNECT**, **ACK**, **NACK**, **RECEIPT**, and **ERROR**; not every broker supports the full feature set.

| Command | Typical direction | Meaning |
| --- | --- | --- |
| CONNECT | Client → server | Starts a STOMP session over an open connection |
| CONNECTED | Server → client | Confirms the STOMP session is established |
| SUBSCRIBE | Client → server | Subscribes to a destination; requires an id header |
| SEND | Client → server | Sends a payload to a destination |
| MESSAGE | Server/broker → client | Delivers a message to a subscription |
| UNSUBSCRIBE | Client → server | Cancels a subscription by subscription id |
| DISCONNECT | Client → server | Ends the session gracefully per protocol |
| ACK/NACK | Client → broker | Acknowledges/rejects delivery if broker/mode supports it |
| ERROR | Server/broker → client | Reports a protocol-level error |
| RECEIPT | Server/broker → client | Confirms a receipt request when supported |

**Important:** A WebSocket message, a STOMP frame, and a Spring **Message<?>** are not the same thing. On the server, the WebSocket/STOMP layer decodes frames, normalizes headers/payload into a Spring `Message`, and dispatches it onto internal channels. A message converter can deserialize JSON bytes into a Java DTO when the handler executes.

## 3. Configuring STOMP in Spring

A minimal Spring Boot/Spring Framework configuration using **@EnableWebSocketMessageBroker**:

~~~java
package demo;

import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.simp.config.MessageBrokerRegistry;
import org.springframework.web.socket.config.annotation.EnableWebSocketMessageBroker;
import org.springframework.web.socket.config.annotation.StompEndpointRegistry;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;

@Configuration
@EnableWebSocketMessageBroker
public class WebSocketConfig implements WebSocketMessageBrokerConfigurer {

    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/ws");
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.setApplicationDestinationPrefixes("/app");
        registry.enableSimpleBroker("/topic", "/queue");
        registry.setUserDestinationPrefix("/user");
    }
}
~~~

Explanation of each setting:

- **registry.addEndpoint("/ws")** exposes the HTTP handshake path to upgrade to WebSocket; browsers connect via **ws://host/ws** or **wss://host/ws** with TLS. It says nothing about STOMP frame **destinations**.
- **setApplicationDestinationPrefixes("/app")** designates destinations routed to **SimpAnnotationMethodMessageHandler**, i.e. **@MessageMapping** or **@SubscribeMapping** methods. Spring normally strips the **/app** prefix before matching mappings.
- **enableSimpleBroker("/topic", "/queue")** enables Spring's in-memory broker to manage subscriptions and broadcast messages for destinations with these prefixes. The broker does not understand business logic: it does not invoke **@MessageMapping** for **/topic/chat**.
- **setUserDestinationPrefix("/user")** configures the prefix for **UserDestinationMessageHandler**, mapping logical destinations into per-session/per-user subscriptions. This is not a physical broker destination.
- **@EnableWebSocketMessageBroker** registers the required handlers, message channels, converters, and broker components.

The names **/app**, **/topic**, **/queue**, and **/user** are **common configuration-driven conventions**, not fixed names mandated by the STOMP protocol itself. You can pick different prefixes, provided client and server agree. Choose non-overlapping prefixes so a single frame is not handled unexpectedly by multiple handlers.

### Distinguishing HTTP endpoints and STOMP destinations

| Address | Where it lives | Who handles it | Client action |
| --- | --- | --- | --- |
| **/ws** | HTTP/WebSocket handshake URL | WebSocket handshake handler | `new WebSocket("ws://.../ws")` or STOMP client |
| **/app/chat.send** | `destination` header of a SEND frame | Spring annotated controller | STOMP publish/SEND |
| **/topic/chat** | `destination` header of SUBSCRIBE and MESSAGE | Broker | STOMP subscribe |
| **/queue/notifications** | Conventional broker destination | Broker | Usually subscribed for notification streams |
| **/user/queue/notifications** | Logical user destination | UserDestinationMessageHandler → session broker destination | User/session-specific subscribe |

By name, **/queue** often suggests point-to-point semantics in external brokers, but **Spring's simple broker does not natively provide durable queues or competing-consumer semantics**; it stores subscriptions in memory and delivers to matching subscriptions. Never infer persistence, ACKs, or single-consumer delivery solely from the name "/queue".

## 4. Spring's Three Main Message Channels

Spring Messaging provides these abstractions:

- **Message<T>**: a payload of type `T` with headers, such as destination, content-type, sessionId, and simpMessageType.
- **MessageHandler**: component that processes a message.
- **MessageChannel**: send target decoupling producers from consumers.
- **SubscribableChannel**: a message channel allowing handlers to subscribe.
- **ExecutorSubscribableChannel**: a channel that dispatches work to an executor/thread pool.

Spring's STOMP setup uses three central channels:

| Channel | Traffic passing through | Responsibility |
| --- | --- | --- |
| **clientInboundChannel** | From WebSocket clients into the server | Receives Spring Messages decoded from STOMP frames and routes them to controllers, the broker, or appropriate handlers |
| **brokerChannel** | From server-side application code to the broker | Carries messages created by controllers, `SimpMessagingTemplate`, or server components for broker distribution |
| **clientOutboundChannel** | From the broker/server handlers out to clients | Delivers messages to WebSocket sessions and encodes them into STOMP MESSAGE/frames for transmission |

Flow diagram with the simple broker:

~~~text
                 WebSocket clients
                 (STOMP frames)
                        │
            CONNECT / SUBSCRIBE / SEND
                        │
                        ▼
              WebSocket transport
              + STOMP frame decoder
                        │
                        ▼
               clientInboundChannel
                    /         \
                   /           \
       /app/chat.send        /topic/chat
             │               SUBSCRIBE
             ▼                  │
  SimpAnnotationMethod        Simple
     MessageHandler           Broker
             │                  ▲
     @MessageMapping            │
       @Controller              │
             │                  │
       @SendTo result ──► brokerChannel
                                │
                                ▼
                          Simple Broker
                                │
                                ▼
                       clientOutboundChannel
                                │
                       STOMP frame encoder
                                │
                                ▼
                     WebSocket subscribers
~~~

**How to read the diagram correctly:** the broker receives subscriptions directly from **clientInboundChannel**; **@SendTo** return messages from controllers travel through **brokerChannel**. Outbound, the broker sends messages to **clientOutboundChannel**. This is the logical flow model: actual threading and dispatch depend on Spring's executors and handlers. Not every inbound message passes through `brokerChannel`.

### Concrete timeline: a chat message

Suppose two browsers A and B have connected to **/ws**:

1. **A SUBSCRIBEs to /topic/chat** with subscription id **a1**. WebSocket transport decodes and sends a Spring Message onto **clientInboundChannel**; the simple broker receives and stores A's subscription.
2. **B SUBSCRIBEs to /topic/chat** with id **b1**. The broker stores B's subscription as well.
3. **A SENDs to /app/chat.send** with JSON **{"from":"An","text":"Hello"}**. The frame is decoded and sent onto **clientInboundChannel**.
4. **SimpAnnotationMethodMessageHandler** claims it because the **/app** prefix belongs to the application; it strips the prefix and finds **@MessageMapping("/chat.send")** on a controller.
5. Spring's **MessageConverter** converts the JSON payload into a Java DTO. The controller validates/transforms per business rules and returns an object.
6. **@SendTo("/topic/chat")** wraps the return value into an outbound message with destination **/topic/chat**, routing it through **brokerChannel** to the simple broker.
7. The broker matches the destination against active subscriptions and dispatches copies to both A and B via **clientOutboundChannel**.
8. WebSocket transport encodes each Spring Message into a STOMP **MESSAGE** frame with the matching subscription id/session and writes it over WebSocket.

**Note:** A also receives its own message if A is subscribed to `/topic/chat`. If there are no subscriptions, the broker does not automatically store messages for later delivery. If a client SENDs directly to **/topic/chat** instead of **/app/chat.send**, the simple broker may handle it directly; the **@MessageMapping("/chat.send")** controller will not run. This is a common reason users see messages broadcast while validation/business logic is bypassed.

## 5. @MessageMapping, @SendTo, and SimpMessagingTemplate

Controller handling **/app/chat.send**:

~~~java
package demo;

import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.SendTo;
import org.springframework.stereotype.Controller;

@Controller
public class ChatController {

    public record ChatInput(String from, String text) {}
    public record ChatEvent(String from, String text) {}

    @MessageMapping("/chat.send")
    @SendTo("/topic/chat")
    public ChatEvent send(ChatInput input) {
        return new ChatEvent(input.from(), input.text());
    }
}
~~~

Characteristics:
- **@Controller** is used with Spring Messaging annotation handlers; do not confuse with HTTP **@RestController** mappings.
- **@MessageMapping("/chat.send")** matches the destination after stripping the **/app** prefix. It does not need **@PostMapping**.
- **ChatInput** is converted from JSON by an appropriate message converter (Jackson when configured).
- **@SendTo("/topic/chat")** specifies where to publish **the return value**. Without **@SendTo**, Spring applies a default reply destination rule (based on broker prefix config); however, declaring it explicitly makes it clear to readers where clients must subscribe.
- When a method returns **void**, no outbound return message is sent automatically. To send messages, inject **SimpMessagingTemplate** or perform another side effect.
- **@DestinationVariable** binds path variables in destinations such as **@MessageMapping("/rooms/{roomId}")**; similarly **@Header**, **@Payload**, and **Principal** can be used as method parameters.

### Server-initiated publishing without waiting for STOMP SEND

An application can push messages from an HTTP endpoint, scheduled job, or message queue consumer using **SimpMessagingTemplate**:

~~~java
@RestController
public class AnnouncementController {

    public record Announcement(String text) {}

    private final SimpMessagingTemplate messaging;

    public AnnouncementController(SimpMessagingTemplate messaging) {
        this.messaging = messaging;
    }

    @PostMapping("/api/announcements")
    public ResponseEntity<Void> publish(@RequestParam("text") String text) {
        messaging.convertAndSend(
            "/topic/announcements", new Announcement(text));
        return ResponseEntity.accepted().build();
    }
}
~~~

Required imports are **org.springframework.messaging.simp.SimpMessagingTemplate**, **org.springframework.web.bind.annotation.RestController**, **PostMapping**, **RequestParam**, and **org.springframework.http.ResponseEntity**. This is an HTTP + WebSocket application fragment; full runnable code is shown in section 10.

**convertAndSend** converts the object into a Spring Message and sends it through **brokerChannel**; the broker delivers it to subscribers of **/topic/announcements**. No client needs to SEND to **/app** first. Returning HTTP **202 Accepted** in the example confirms the endpoint handled the publish request at the application layer; it does not guarantee every browser subscriber has already received and processed the announcement.

### @SubscribeMapping: a different branch from @MessageMapping

**@SubscribeMapping("/snapshot")** handles a **SUBSCRIBE /app/snapshot** in an annotated controller. By default, the return value goes **directly via clientOutboundChannel** back to the subscribing client, **skipping brokerChannel** rather than broadcasting or registering a long-lived subscription. This is useful for sending an initial snapshot when a page opens:

~~~java
@SubscribeMapping("/snapshot")
public Snapshot initialState() {
    return service.currentSnapshot();
}
~~~

If **@SendTo** or **@SendToUser** is applied, the return path can route through the broker instead of the default direct reply. Do not use SUBSCRIBE **/app/snapshot** as a substitute for a long-lived **/topic/updates** subscription when continuous change streams are needed.

## 6. User Destinations: How /user Differs from /queue

Sometimes the server needs to send a private notification to a specific user account or a single WebSocket session. Spring supports **UserDestinationMessageHandler**, which translates logical destinations prefixed with **/user** into session-specific destinations.

Client subscribes:

~~~text
SUBSCRIBE
id:me-1
destination:/user/queue/notifications

<NUL>
~~~

Application sends to an authenticated user:

~~~java
messaging.convertAndSendToUser(
    username,
    "/queue/notifications",
    new Notification("Processing complete"));
~~~

With **@MessageMapping**, you can return a result using **@SendToUser("/queue/notifications")**. The server resolves the destination to one or more sessions of that user according to its rules, such as a physical destination with a session suffix.

**Clear distinctions**:
- The client typically **SUBSCRIBEs to /user/queue/notifications** **without embedding a username** in the subscription destination.
- Server code calls **convertAndSendToUser(username, "/queue/notifications", payload)** or **@SendToUser**.
- **/user** is a logical prefix for Spring to resolve recipients, not an authorization guarantee.
- By default, when a user has multiple sessions, user-targeted messages may be delivered to multiple sessions; **@SendToUser(broadcast=false)** can restrict replies to the originating session when appropriate.
- For an unauthenticated WebSocket session, **@SendToUser** can still route to that session when `broadcast=false`; this behavior does not replace actual authentication requirements.
- In multi-instance deployments with an external broker, distributed user sessions must be configured and routed properly; do not assume a target user on another instance is always automatically resolved.

Using **/queue** in a user destination expresses the intent to receive personal notifications; it does not mean the simple broker writes durable messages to disk.

## 7. Simple Broker vs. Broker Relay: Similarities and Differences in Flow

### Built-in simple broker

Configuration:

~~~java
registry.setApplicationDestinationPrefixes("/app");
registry.enableSimpleBroker("/topic", "/queue");
~~~

The simple broker keeps subscription state in **the Spring application's memory** and broadcasts messages to connected sessions. It fits demos, small single-node apps, or systems without heavy broker requirements. It **is not a full-featured message broker**: it does not provide full STOMP features such as ACKs, receipts, persistence, clustering, or enterprise durable delivery.

The SEND `/app` → controller → `brokerChannel` → simple broker → `clientOutboundChannel` flow works as analyzed above. For `SUBSCRIBE /topic`, the broker captures subscriptions from `clientInboundChannel`. With multiple Spring instances behind a load balancer, a simple subscription on node A is not automatically known to node B.

### STOMP broker relay

When a real broker is needed (for example RabbitMQ/ActiveMQ with STOMP enabled), Spring can use a **relay**:

~~~java
@Override
public void configureMessageBroker(MessageBrokerRegistry registry) {
    registry.setApplicationDestinationPrefixes("/app");
    registry.enableStompBrokerRelay("/topic", "/queue")
        .setRelayHost("127.0.0.1")
        .setRelayPort(61613)
        .setClientLogin("guest")
        .setClientPasscode("guest")
        .setSystemLogin("guest")
        .setSystemPasscode("guest");
}
~~~

Host, port, and credentials in this snippet **are illustrative only**; load them from your deployed broker setup and protect secrets in environment configuration. **Spring does not automatically start RabbitMQ/ActiveMQ** when enabling the relay.

The flow changes as follows:

~~~text
Client SEND /app/action
       |
       v
clientInboundChannel
       |
 @MessageMapping
       |
 brokerChannel
       |
  STOMP broker relay ──TCP──> External broker
                                 |
                          subscribers matched
                                 |
                         TCP reply to relay
                                 |
                       clientOutboundChannel
                                 |
                            WebSocket clients
~~~

For `SUBSCRIBE /topic`, the relay forwards the subscription to the external broker over TCP. For `SEND` to a broker-managed destination, the relay also forwards it to the broker. **@MessageMapping** still runs inside Spring for application destinations like `/app`.

The relay maintains TCP connections to the broker, including a system connection and connections representing WebSocket clients per the relay model. If the broker disconnects, handle availability/reconnection and monitor **BrokerAvailabilityEvent**; do not treat the relay as an unbounded in-memory queue. External brokers can support ACKs, receipts, heartbeats, durable subscriptions, and advanced routing, **only when both the broker and configuration actually support them**.

## 8. Ordering, Executors, and Operational Concerns

Normally **clientInboundChannel** and **clientOutboundChannel** are backed by executors. This boosts throughput but has a consequence: messages from a single session may be processed or sent on different threads, so actual order may not match frame arrival order or publish order.

If ordering is a business requirement (such as sequential updates within a session), Spring provides options:

~~~java
@Override
public void registerStompEndpoints(StompEndpointRegistry registry) {
    registry.addEndpoint("/ws");
    registry.setPreserveReceiveOrder(true);
}

@Override
public void configureMessageBroker(MessageBrokerRegistry registry) {
    registry.setApplicationDestinationPrefixes("/app");
    registry.enableSimpleBroker("/topic", "/queue");
    registry.setPreservePublishOrder(true);
}
~~~

- **setPreserveReceiveOrder(true)** makes Spring process inbound messages within the same WebSocket session in arrival order on **clientInboundChannel**.
- **setPreservePublishOrder(true)** ensures outbound messages within the same session are published to **clientOutboundChannel** in order.
- Both options incur performance overhead and **do not promise global ordering across all sessions, instances, or external brokers**. Include sequence numbers in payloads if your application needs cross-node business ordering/comparison.

### Interceptors and observability

To observe or inspect inbound STOMP frames, register a **ChannelInterceptor** via **configureClientInboundChannel**:

~~~java
@Override
public void configureClientInboundChannel(ChannelRegistration registration) {
    registration.interceptors(new ChannelInterceptor() {
        @Override
        public Message<?> preSend(
                Message<?> message, MessageChannel channel) {
            StompHeaderAccessor stomp =
                MessageHeaderAccessor.getAccessor(
                    message, StompHeaderAccessor.class);
            if (stomp != null) {
                System.out.println("STOMP " + stomp.getCommand()
                    + " -> " + stomp.getDestination());
            }
            return message;
        }
    });
}
~~~

To compile the snippet above, import **ChannelRegistration**, **ChannelInterceptor**, **Message**, **MessageChannel**, **MessageHeaderAccessor**, and **StompHeaderAccessor**. This is a diagnostic example that **prints frame metadata**, not a complete security mechanism. Log only necessary commands/destinations, never payloads or authorization tokens. In production, use structured logging/metrics and monitor thread pools, sizes, queue saturation, disconnects, and processing latency.

### Authentication and authorization

A WebSocket connection begins with an HTTP handshake; the principal can be inherited from the HTTP session/authentication at handshake time. STOMP CONNECT, SUBSCRIBE, and SEND are messaging operations that require separate **authorization**. For example, a user permitted to read **/topic/public** does not necessarily have permission to SEND straight to the broker or subscribe to someone else's **/user/** destination.

In Spring Security, define message authorization rules **by STOMP message type and destination**, enforce CSRF/origin protections appropriate for browser apps, and verify identity before delivering to user destinations. Do not rely solely on the **/app** prefix or a client-supplied username field in JSON. A safe pattern restricts client SENDs to **/app/** so controllers validate business rules, disallowing clients from publishing directly to server-only destinations.

### Lifecycle and reliability

- **STOMP heartbeats** detect silent connections but do not replace post-reconnect state recovery.
- **Connection loss** drops the old session's subscriptions; STOMP clients generally must reconnect and re-subscribe.
- **WebSocket reconnect** does not automatically replay messages emitted while offline when using the simple broker.
- For business data that must not be lost, persist events/state to a DB or durable broker, use message IDs, acknowledgements, and post-reconnect sync. STOMP over WebSocket itself does not guarantee exactly-once delivery.
- **@MessageExceptionHandler** maps controller errors to response messages; choose error destinations carefully. Never leak stack traces or secrets to clients.
- When the outbound channel slows down, enforce buffer/send timeout limits, payload sizes, subscription counts, and emission rates. A single slow subscriber can exert resource pressure.

## 9. Another Flow: Notifications from a REST Endpoint to WebSocket

The chat flow in section 4 is **client SEND** → **@MessageMapping**. However, system events can also originate from an HTTP request or scheduled task:

~~~text
HTTP POST /api/announcements
        |
        v
@RestController / service
        |
SimpMessagingTemplate.convertAndSend(
    "/topic/announcements", object)
        |
        v
    brokerChannel
        |
     broker
        |
  clientOutboundChannel
        |
STOMP MESSAGE to all clients SUBSCRIBED to /topic/announcements
~~~

In this branch, **there is no client STOMP SEND**, so service-generated messages **do not pass through clientInboundChannel**. This is a crucial boundary when tracing flows: seeing a subscriber receive a MESSAGE does not tell you whether it originated from a STOMP controller, a REST API, a database change event, or a scheduler.

## 10. Runnable Demo: Chat + Announcements with Spring Boot 3, Java 17

This demo contains **one Spring Boot server** with WebSocket/STOMP endpoint **/ws**, a controller handling **/app/chat.send**, and browsers subscribing to two broker destinations: **/topic/chat** and **/topic/announcements**. An HTTP endpoint triggers publishing via **SimpMessagingTemplate**. With two browser tabs, you can observe subscriptions and broadcasts in a single JVM.

Requires **JDK 17+**, Maven, and Internet access to fetch dependencies and the STOMP browser client CDN. The demo uses Spring Boot **3.5.0** so APIs align with Spring Framework 6.2.x.

Project layout:

~~~text
stomp-channels-demo/
├── pom.xml
└── src/main/
    ├── java/demo/
    │   ├── MessagingDemoApplication.java
    │   ├── WebSocketConfig.java
    │   ├── ChatController.java
    │   └── AnnouncementController.java
    └── resources/static/index.html
~~~

**pom.xml**:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>stomp-channels-demo</artifactId>
    <version>1.0.0</version>
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

**src/main/java/demo/MessagingDemoApplication.java**:

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MessagingDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(MessagingDemoApplication.class, args);
    }
}
~~~

**src/main/java/demo/WebSocketConfig.java**:

~~~java
package demo;

import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.simp.config.MessageBrokerRegistry;
import org.springframework.web.socket.config.annotation.EnableWebSocketMessageBroker;
import org.springframework.web.socket.config.annotation.StompEndpointRegistry;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;

@Configuration
@EnableWebSocketMessageBroker
public class WebSocketConfig implements WebSocketMessageBrokerConfigurer {
    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/ws");
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.setApplicationDestinationPrefixes("/app");
        registry.enableSimpleBroker("/topic", "/queue");
    }
}
~~~

**src/main/java/demo/ChatController.java**:

~~~java
package demo;

import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.SendTo;
import org.springframework.stereotype.Controller;

@Controller
public class ChatController {
    public record ChatInput(String from, String text) {}
    public record ChatEvent(String from, String text) {}

    @MessageMapping("/chat.send")
    @SendTo("/topic/chat")
    public ChatEvent send(ChatInput input) {
        return new ChatEvent(input.from(), input.text());
    }
}
~~~

**src/main/java/demo/AnnouncementController.java**:

~~~java
package demo;

import org.springframework.http.ResponseEntity;
import org.springframework.messaging.simp.SimpMessagingTemplate;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class AnnouncementController {
    public record Announcement(String text) {}

    private final SimpMessagingTemplate messaging;

    public AnnouncementController(SimpMessagingTemplate messaging) {
        this.messaging = messaging;
    }

    @PostMapping("/api/announcements")
    public ResponseEntity<Void> publish(@RequestParam("text") String text) {
        messaging.convertAndSend(
            "/topic/announcements",
            new Announcement(text));
        return ResponseEntity.accepted().build();
    }
}
~~~

**src/main/resources/static/index.html** (same-origin avoids CORS errors caused by opening from `file://`):

~~~html
<!doctype html>
<html lang="vi">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>STOMP channels demo</title>
</head>
<body>
  <h1>STOMP channels demo</h1>
  <p id="status">Connecting...</p>
  <button id="send" disabled>Send chat message</button>
  <ol id="feed"></ol>

  <script src="https://cdn.jsdelivr.net/npm/@stomp/stompjs@7/bundles/stomp.umd.min.js"></script>
  <script>
    const status = document.querySelector("#status");
    const feed = document.querySelector("#feed");
    const send = document.querySelector("#send");

    const scheme = location.protocol === "https:" ? "wss" : "ws";
    const client = new StompJs.Client({
      brokerURL: scheme + "://" + location.host + "/ws",
      reconnectDelay: 5000,
      onConnect: () => {
        status.textContent = "STOMP CONNECTED";
        send.disabled = false;

        client.subscribe("/topic/chat", frame => {
          const chat = JSON.parse(frame.body);
          const li = document.createElement("li");
          li.textContent = "Chat " + chat.from + ": " + chat.text;
          feed.append(li);
        });

        client.subscribe("/topic/announcements", frame => {
          const event = JSON.parse(frame.body);
          const li = document.createElement("li");
          li.textContent = "Announcement: " + event.text;
          feed.append(li);
        });
      },
      onWebSocketClose: () => {
        status.textContent = "Disconnected, attempting to reconnect...";
        send.disabled = true;
      },
      onStompError: frame => {
        status.textContent = "STOMP ERROR: " + frame.headers.message;
      }
    });

    send.addEventListener("click", () => {
      client.publish({
        destination: "/app/chat.send",
        body: JSON.stringify({
          from: "An",
          text: "Hello via STOMP"
        }),
        headers: { "content-type": "application/json" }
      });
    });

    client.activate();
  </script>
</body>
</html>
~~~

Here the UMD bundle of **@stomp/stompjs** from a CDN exposes global **StompJs** to the browser. Production projects should install via npm and bundle their client, configuring authentication, origin policies, and CSP appropriately; the demo omits permission checks and chat content validation.

### Running and verifying

In **stomp-channels-demo**:

~~~bash
mvn spring-boot:run
~~~

Wait for the application to start and open **http://localhost:8080/** in **two tabs**. Both tabs should display **STOMP CONNECTED** once connected.

1. Click **Send chat message** in the first tab. Since both tabs are **SUBSCRIBED to /topic/chat**, each tab displays **Chat An: Hello via STOMP**.
2. Use a terminal to send an HTTP POST to the REST endpoint:

~~~bash
curl -i -X POST --data-urlencode "text=System ready" http://localhost:8080/api/announcements
~~~

The endpoint responds with **HTTP 202 Accepted** and an empty body. Both subscribed tabs will display **Announcement: System ready**.

These are **conditional results**: if the browser has not connected or subscribed yet, the server is not running, port 8080 is occupied, or the CDN cannot load the STOMP library, the outcome will differ. Spring Boot logs depend on the environment, so there is no fixed server stdout. To run multiple tabs reliably, wait for CONNECTED before sending.

### Tracing the exact path in the demo

When the browser sends a chat message:

~~~text
Browser A
  publish("/app/chat.send", JSON)
    -> WebSocket /ws
    -> clientInboundChannel
    -> @MessageMapping("/chat.send")
    -> @SendTo("/topic/chat")
    -> brokerChannel
    -> simple broker
    -> clientOutboundChannel
    -> Subscribed Browsers A and B
~~~

When calling the HTTP POST announcement endpoint:

~~~text
curl -> HTTP @PostMapping("/api/announcements")
     -> SimpMessagingTemplate.convertAndSend("/topic/announcements")
     -> brokerChannel
     -> simple broker
     -> clientOutboundChannel
     -> Subscribed Browsers A and B
~~~

Observe that the REST branch **bypasses clientInboundChannel** and **never invokes @MessageMapping**. This is the exact distinction to keep in mind when debugging events in apps combining HTTP and WebSocket.

## 11. Common Errors and How to Diagnose Them

| Symptom | Possible cause | How to inspect and fix |
| --- | --- | --- |
| WebSocket connects but controller does not run | Client SENDs straight to `/topic` instead of `/app`, or mapping mismatch | Check SEND destination, application prefix, and `@MessageMapping` |
| Client SUBSCRIBEs to `/app/chat.send` but sees no broadcast | `/app` is for handlers; broadcast subscriptions live on broker destinations | Subscribe to `/topic/chat` matching `@SendTo` |
| Client sends to `/ws` as a STOMP destination | Confusing WebSocket handshake endpoint with STOMP destination | Connect to `ws://host/ws`, then publish to `/app/...` |
| Message reaches controller but nobody receives it | Missing subscription, wrong `@SendTo` target, broker disconnected | Verify `SUBSCRIBE /topic/...` and broker prefixes |
| One user receives duplicate copies | Multiple open sessions, duplicate subscriptions, or multiple sends | Check session/subscription IDs, user destinations, and reconnect logic |
| Using `/queue` without single-consumer guarantees | Simple broker is not a durable queue | Use an external broker with proper ACKs and routing |
| Event ordering is inverted | Concurrent executor processing | Enable `preserveReceiveOrder`/`preservePublishOrder` only when needed; add sequences |
| Messages missing after reconnect | Simple broker does not persist offline messages | Sync from DB, use replay/IDs, or durable broker when required |
| WebSocket handshake returns 403 | Origin/CORS/CSRF/auth configuration | Check same-host origin, Spring Security policies, handshake config |
| CONNECT works but SUBSCRIBE/SEND is forbidden | Separate messaging authorization rules | Check rules by message type and destination |
| JSON fails to convert into DTO | Payload/schema mismatch, missing content-type, or converter issue | Send valid JSON with matching content-type |
| Broker relay reports disconnected | Broker TCP offline, bad credentials, or network issue | Check relay host/port, connectivity, and `BrokerAvailabilityEvent` |
| Browser shows nothing in the demo | CDN script failed, not CONNECTED yet, or not subscribed | Check browser Console/Network and STOMP client status |

### Debugging in logical order

1. **Handshake**: did WebSocket **/ws** open and did the browser reach CONNECTED?
2. **Frames**: which destination did the client actually send in STOMP **SUBSCRIBE** or **SEND**?
3. **Routing**: do the **/app** and **/topic** prefixes match server configuration?
4. **Inbound**: did the message enter **clientInboundChannel** and reach the annotated handler or broker?
5. **Business**: did the **@MessageMapping** method execute and did the converter decode the DTO properly?
6. **Broker**: did the message enter **brokerChannel** and does the broker hold matching subscriptions?
7. **Outbound**: did the message reach **clientOutboundChannel**, is the WebSocket still open, and did the subscriber callback parse JSON properly?
8. **Operations**: is there thread pool saturation, outbound buffer overflow, relay outage, timeout, reconnect loop, or authorization failure?

If you need to inspect channels with an interceptor, start with **clientInboundChannel** to view CONNECT/SUBSCRIBE/SEND frames. Then inspect `brokerChannel` or `clientOutboundChannel` along the identified branch. Never conclude from a browser `console.log` alone that the server controller ran.

## 12. Key Takeaways and Exercises

- **STOMP** provides commands and headers such as SEND, SUBSCRIBE, and destination on top of WebSocket.
- A **destination** is a logical address inside a STOMP frame; **/ws** is the HTTP/WebSocket handshake endpoint at a lower layer.
- **/app** usually routes to **@MessageMapping**; **/topic** and **/queue** usually go to the broker; **/user** resolves per-user/per-session destinations.
- **clientInboundChannel** carries messages from WebSocket clients; **brokerChannel** carries server-created messages to the broker; **clientOutboundChannel** delivers messages to WebSocket clients.
- **@SendTo** and **SimpMessagingTemplate** are two ways to send from application code to the broker. **@SubscribeMapping** defaults to replying directly to the client via the outbound channel.
- The simple broker manages subscriptions in memory; an external STOMP broker relay offloads broadcasting to a dedicated broker over TCP.
- Executors, ordering, authentication, authorization, reconnection, and delivery guarantees all affect the system beyond the happy path.

### Self-check exercises

1. Change **@MessageMapping("/chat.send")** to **@MessageMapping("/rooms/{roomId}")** using **@DestinationVariable String roomId**, and send the reply to **/topic/rooms/{roomId}**. Why might you need **SimpMessagingTemplate** instead of a static `@SendTo`?
2. Add **@SubscribeMapping("/snapshot")** returning current state, have the browser subscribe to **/app/snapshot**, and compare with **/topic/chat**: which message is broadcast?
3. Use **@SendToUser("/queue/errors")** to return validation errors to the originating session. Discuss why a client-supplied **username** inside JSON is insufficient to verify the recipient.
4. Have a client send directly to **/topic/chat** without going through **/app/chat.send**; what happens to the controller? In a real application, what authorization rule should prevent this?
5. Explain why messages published from REST **/api/announcements** skip `clientInboundChannel` yet still reach subscribers.
6. If multiple Spring instances serve users behind a load balancer, would you choose the simple broker or a broker relay? To guarantee messages across reconnects, what storage/sync layer must be added?

## References

- [Spring Framework – STOMP Overview](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/overview.html)
- [Spring Framework – Enable STOMP](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/enable.html)
- [Spring Framework – Flow of Messages](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/message-flow.html)
- [Spring Framework – Annotated Controllers](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-annotations.html)
- [Spring Framework – Sending Messages](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-send.html)
- [Spring Framework – Simple Broker](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-simple-broker.html)
- [Spring Framework – External Broker](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-broker-relay.html)
- [Spring Framework – User Destinations](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/user-destination.html)
- [Spring Framework – Order of Messages](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/ordered-messages.html)
- [Spring Framework – Interception](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/interceptors.html)
