# Simple Broker, Broker Relay, and Choices When Scaling Out

## 1. The Problem a STOMP Broker Solves

WebSocket opens a long-lived, bidirectional communication channel between the browser/client and the Spring server. STOMP adds a messaging protocol on top of that channel: clients send `CONNECT`, `SUBSCRIBE`, `SEND`, `DISCONNECT`; the server or broker emits `MESSAGE` frames to subscribed sessions. When a client subscribes to `/topic/news`, the system must know **who is subscribed, where messages should go, and when they are delivered**.

Spring Framework supports two broker deployment models:

- **Simple broker**: a lightweight subscription handler running **inside the Spring JVM**, storing subscriptions in RAM and delivering messages to matching WebSocket sessions on that instance. Enabled with `enableSimpleBroker(...)`.
- **STOMP broker relay**: Spring forwards STOMP traffic to an **external message broker supporting STOMP/TCP** such as RabbitMQ (with the STOMP plugin enabled) or ActiveMQ. Enabled with `enableStompBrokerRelay(...)`. The external broker handles subscriptions, routing, and its own messaging features.

This choice becomes critical when an application scales from one Spring process to multiple instances/pods. **Adding pods with the simple broker does not automatically create a shared message distribution network.** A relay lets multiple Spring nodes share one broker, though it does not by itself provide durable delivery, exactly-once semantics, or per-user authorization.

This lesson progresses from Spring messaging flow diagrams, Java configuration, routing/ACK semantics, scaling models, user destinations, connections/heartbeats, fault recovery, and security to a runnable **Java 17+ + Spring Boot 3.3.x/Spring Framework 6.1.x** example. Code fragments are clearly distinguished from complete runnable programs.

## 2. Flow Diagram: Endpoint, Application Destination, and Broker Destination

First, distinguish the **WebSocket connection URL** from **STOMP destinations**:

| Value | Role | Who handles it? |
| --- | --- | --- |
| `/ws` | HTTP handshake / WebSocket endpoint | Servlet container and Spring WebSocket |
| `/app/chat` | Client sends STOMP `SEND` for business logic | `@MessageMapping("/chat")` after Spring strips `/app` |
| `/topic/chat` | Destination used for subscribe/broadcast | Broker (simple or external) |
| `/queue/notices` | Destination prefixed with `/queue` | Simple broker treats it as a routing string; external broker depends on policy |
| `/user/queue/notices` | Logical destination for user/session | Spring `UserDestinationMessageHandler` translates to a concrete destination |

Typical flow:

```text
Client A                        Spring                            Client B
   │                               │                                  │
   ├─ SEND /app/chat ─────────────►│ clientInboundChannel             │
   │                               │ @MessageMapping("/chat")         │
   │                               │ @SendTo("/topic/chat")           │
   │                               ▼                                  │
   │                         brokerChannel                            │
   │                               │                                  │
   │                ┌──────────────┴──────────────┐                   │
   │                ▼                             ▼                   │
   │          SimpleBroker                STOMP Broker Relay          │
   │          (local RAM)                 → External Broker           │
   │                └──────────────┬──────────────┘                   │
   │                               │                                  │
   │                         clientOutboundChannel                    │
   │                               │                                  │
   │◄──── MESSAGE /topic/chat ─────┼───── MESSAGE /topic/chat ───────►│
```

The diagram shows **two mutually exclusive broker options**. A Spring configuration for the same broker destinations normally enables **only one** broker handler. `clientInboundChannel` receives messages from WebSocket; `brokerChannel` receives messages published by application code via `SimpMessagingTemplate` or controller return values; `clientOutboundChannel` delivers broker messages to WebSocket sessions.

**Do not confuse:** `SimpMessagingTemplate.convertAndSend("/topic/chat", value)` publishes to a destination. That call **does not mean** the client has received or processed it, nor is it an HTTP endpoint call. Likewise, HTTP status 101 only confirms the WebSocket Upgrade; the client still needs STOMP CONNECT and SUBSCRIBE to establish a subscription.

## 3. Simple Broker: How It Works, Limitations, and Heartbeats

### 3.1 Single-instance mechanics

With `registry.enableSimpleBroker("/topic", "/queue")`, Spring creates an in-memory subscription store for STOMP sessions. When A and B subscribe to `/topic/news` and the server publishes a message to that destination, the simple broker pushes it to both sessions. Unsubscribed client C does not receive it. When a client is offline, the simple broker's memory **does not store a backlog** for later delivery.

```text
Spring instance A
 ├─ WebSocket session user1 → SUB /topic/news
 ├─ WebSocket session user2 → SUB /topic/news
 ├─ WebSocket session user3 → SUB /topic/alerts
 └─ SimpleBroker (in-RAM subscription registry)
       │
       ├─ publish /topic/news   → user1, user2
       └─ publish /topic/alerts → user3
```

Core characteristics:

1. **Fast to set up**: ideal for learning, demos, single-instance apps, and real-time notifications that can be refreshed/resynced.
2. **No persistent message store**: JVM restarts lose WebSocket sessions and subscriptions; clients must reconnect and re-subscribe.
3. **Not a full message broker**: supports a subset of STOMP and does not provide full ACK/RECEIPT semantics or advanced features of a full broker. Do not rely on `ack:client-individual` with the simple broker to guarantee redelivery.
4. **Subscriptions match only within the current instance**: the subscription registry is not shared automatically with other Spring instances.
5. **Prefixes are conventions only**: `/topic` and `/queue` do not enforce durable topics or competing-consumer queues. If two clients subscribe to `/queue/jobs` on the simple broker, do not assume only one client receives each job.
6. **Heartbeats are configurable** with a `TaskScheduler`. STOMP heartbeats differ from WebSocket Ping/Pong and TCP keepalives.

Baseline configuration snippet:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.simp.config.MessageBrokerRegistry;
import org.springframework.web.socket.config.annotation.EnableWebSocketMessageBroker;
import org.springframework.web.socket.config.annotation.StompEndpointRegistry;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;

@Configuration
@EnableWebSocketMessageBroker
class SocketConfig implements WebSocketMessageBrokerConfigurer {

    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/ws")
                .setAllowedOriginPatterns("http://localhost:*");
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.setApplicationDestinationPrefixes("/app");
        registry.setUserDestinationPrefix("/user");
        registry.enableSimpleBroker("/topic", "/queue");
    }
}
```

This is a **Spring configuration fragment**, not a standalone runnable Java program. `/ws` is the handshake URL, while `/app` and `/topic` are destination prefixes. Localhost origins are only for local examples; production needs HTTPS/WSS, explicit origin allowlists, and proper authorization.

### 3.2 Configuring heartbeats on the simple broker

The simple broker requires a scheduler when STOMP heartbeats are enabled. Inside a `WebSocketMessageBrokerConfigurer` you can add:

```java
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.Lazy;
import org.springframework.scheduling.TaskScheduler;

// Members inside the configuration class (fragment):
private TaskScheduler messageBrokerTaskScheduler;

@Autowired
void setMessageBrokerTaskScheduler(@Lazy TaskScheduler scheduler) {
    this.messageBrokerTaskScheduler = scheduler;
}

@Override
public void configureMessageBroker(MessageBrokerRegistry registry) {
    registry.setApplicationDestinationPrefixes("/app");
    registry.enableSimpleBroker("/topic", "/queue")
            .setTaskScheduler(messageBrokerTaskScheduler)
            .setHeartbeatValue(new long[] {10_000, 10_000});
}
```

You must **replace** the earlier `configureMessageBroker` method rather than pasting a duplicate override. Spring WebSocket configuration can supply a suitable scheduler; `@Lazy` prevents dependency cycles when the configurer injects the scheduler. The heartbeat array is in milliseconds; client and broker still negotiate `heart-beat` headers during STOMP CONNECT/CONNECTED. Heartbeats only detect connection liveness; they do not add clustering or persistence.

## 4. What Happens When Scaling the Simple Broker Across Multiple Pods?

Suppose two Spring instances A and B sit behind a load balancer:

```text
                     Load balancer
                    /             \
Client X ──WebSocket─► Spring A   Spring B ◄─WebSocket── Client Y
                         │           │
                   SimpleBroker A  SimpleBroker B
                   SUB /topic/live SUB /topic/live
                         │           │
REST request → Spring A  │           │
         publish /topic/live          │
                         ▼           (not received)
                      Client X
```

The two simple brokers **do not share RAM**. A REST call hitting A can publish to sessions subscribed on A; Y connected to B will not receive that message. A WebSocket connection stays pinned to one instance for its lifetime; **sticky sessions do not turn two simple brokers into a clustered broker**.

Operational consequences:

- Scaling from one to multiple replicas can cause incomplete notifications if the business requires cross-node fan-out.
- A single user on two devices may be load-balanced to two different nodes; sending to that user from one node requires cross-node user-destination resolution.
- Rolling restarts close WebSocket connections on the retiring node; clients must reconnect and re-subscribe even when using an external broker.
- If you build a custom event bus to sync nodes, you must handle duplicates, ordering, retries, security, and loop suppression. That is a custom architecture, not default simple-broker behavior.

**When is the simple broker still reasonable?** When running a single Spring node or intentionally partitioned nodes that never need cross-node delivery, when the business tolerates best-effort notifications, and when clients can reload authoritative state via REST/database.

## 5. STOMP Broker Relay: Connections and the External Broker's Role

`registry.enableStompBrokerRelay("/topic", "/queue")` configures Spring to forward messages to an external STOMP/TCP broker. Browsers/clients still connect to Spring's WebSocket endpoint; Spring continues to handle handshakes, security, STOMP frame decoding, and `@MessageMapping`. The external broker handles distributing messages among publishers and subscribers.

```text
WebSocket client 1 ─► Spring A ── STOMP/TCP relay client connection ─┐
                                                                   │
WebSocket client 2 ─► Spring B ── STOMP/TCP relay client connection ─┤
                                                                   ▼
                                                       External STOMP Broker
                                               RabbitMQ STOMP / ActiveMQ / ...
                                                                   ▲
REST publisher ───────► Spring A ── STOMP/TCP system connection ────┘
                                                                   │
             Broker sends MESSAGE back to matching relay TCP session ┘
                        → Spring A / Spring B → WebSocket clients
```

### 5.1 Two types of TCP connections

| Connection | Typical count | Purpose |
| --- | --- | --- |
| **Client relay connection** | One TCP connection **per** WebSocket/STOMP client session | Forwards `CONNECT`, `SUBSCRIBE`, `SEND` and receives broker responses for that session |
| **System connection** | One shared connection **per Spring relay instance** | Application sends messages not tied to a specific client, e.g., from REST/cron/service code |

Per Spring documentation, the **system connection is only for sending application-originated messages**, not a channel for receiving broadcasts for all users. Consequently, 10,000 WebSocket sessions can open a large number of TCP connections to the broker. You must evaluate connection limits, file descriptors, memory, heartbeats, and network capacity on the broker.

### 5.2 Relay configuration, credentials, and virtual hosts

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.simp.config.MessageBrokerRegistry;
import org.springframework.web.socket.config.annotation.EnableWebSocketMessageBroker;
import org.springframework.web.socket.config.annotation.StompEndpointRegistry;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;

@Configuration
@EnableWebSocketMessageBroker
class RelayConfig implements WebSocketMessageBrokerConfigurer {

    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/ws")
                .setAllowedOrigins("https://app.example.org");
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.setApplicationDestinationPrefixes("/app");
        registry.setUserDestinationPrefix("/user");

        registry.enableStompBrokerRelay("/topic", "/queue")
                .setRelayHost("broker.internal")
                .setRelayPort(61613)
                .setVirtualHost("realtime")
                .setSystemLogin("spring-system")
                .setSystemPasscode("set-through-secret-manager")
                .setClientLogin("spring-clients")
                .setClientPasscode("set-through-secret-manager");
    }
}
```

This is a **reference configuration fragment**—never hardcode literal credentials in production. Credentials must come from a secret manager or environment config and belong to least-privilege accounts. The broker must expose the proper **STOMP TCP listener**; for example, `61613` is a common STOMP port, not universal across every broker. RabbitMQ's AMQP port `5672` is not the STOMP port.

If the broker requires TLS, configure TLS transport from **Spring to the broker**; `wss://` only encrypts **browser ↔ Spring** and does not automatically encrypt relay TCP traffic.

**Credentials differ across the two layers:**

- End users are authenticated in Spring during the WebSocket handshake or STOMP CONNECT and authorized on `SEND`/`SUBSCRIBE`.
- The STOMP relay replaces `login`/`passcode` sent to the broker with `clientLogin`/`clientPasscode`, or `systemLogin`/`systemPasscode` for the system connection. Broker usernames **do not automatically reflect the real user principal**.
- The broker authenticates service accounts and enforces broker resource policies. Spring must still enforce authorization per STOMP destination.

Configuration APIs may vary across Spring versions; consult the Javadoc matching your BOM. When migrating from simple to relay, **replace** `enableSimpleBroker` with `enableStompBrokerRelay` for the same destination prefixes rather than running two broker handlers over overlapping routes.

### 5.3 Broker connection drops

The relay monitors the system connection and attempts reconnection. Spring publishes `BrokerAvailabilityEvent` when the broker becomes available or unavailable to receive messages from the system perspective:

```java
import org.springframework.context.event.EventListener;
import org.springframework.messaging.simp.broker.BrokerAvailabilityEvent;
import org.springframework.stereotype.Component;

@Component
class BrokerStatusListener {
    @EventListener
    void onBrokerChanged(BrokerAvailabilityEvent event) {
        System.out.println("broker available=" + event.isBrokerAvailable());
    }
}
```

This is a **Spring bean fragment**, not a CLI program. This event is useful for monitoring and letting producers defer sends when the broker is down. It **does not confirm** that individual client TCP sessions are healthy or that users received messages.

When the broker restarts or the network drops, relay client connections can break; clients must **reconnect WebSocket/STOMP, CONNECT, and re-SUBSCRIBE**. Never assume system-connection recovery restores client subscriptions automatically. If the app must never lose a business event, use durable storage/outbox/queues and proper delivery confirmations rather than calling `convertAndSend(...)` alone.

## 6. What Does an External Broker Guarantee vs. Not Promise?

A full STOMP broker can support ACK/NACK, receipts, topics/queues, persistence, failover, durable subscriptions, TTL, dead-lettering, and clustering. Actual capabilities depend on the **broker, STOMP plugin, topology config, destination mappings, and client headers**.

| Property | Simple broker | Broker relay + external broker |
| --- | --- | --- |
| Subscription location | RAM inside Spring instance | External broker routing/state |
| Cross-node broadcast | Not automatic | Possible when all nodes share the broker topology |
| Messages while client offline | Not retained | Only if durable queues/topics/replay are properly designed |
| STOMP ACK/RECEIPT | Not fully supported | Depends on broker, mode, and STOMP plugin |
| Competing queue delivery | `/queue` prefix gives no guarantee | Depends on broker destination semantics |
| Broker clustering | No | Possible if the broker supports and is configured for it |
| Operations | Minimal dependencies | Must operate broker, credentials, network, and HA |
| TCP connection cost | Mainly WebSocket client ↔ Spring | Plus relay TCP connections to the broker |
| Spring restart | Loses WebSocket sessions/subscriptions | WebSocket sessions still must reconnect |
| Exactly-once delivery | No | Not automatic; requires protocol and idempotent consumers |

**Dangerous migration example:** a legacy app used `/queue/jobs` on the simple broker as a broadcast channel name. After migrating to RabbitMQ/ActiveMQ, the external broker may route `/queue/jobs` as a competing-consumer queue. That is a major semantic shift. Verify routing, bindings, and ACK policies through real integration tests.

**A publish call is not a delivery receipt.** `SimpMessagingTemplate.convertAndSend(...)` passes a message to Spring's broker channel. The broker might not have persisted it yet, the client may have just disconnected, or the device may not have ACKed it. When delivery guarantees are required, define what "successfully delivered" means at which layer and build broker confirmations, ACKs, idempotency keys, outboxes, and retries into the design.

## 7. User Destinations Across Multiple Spring Nodes

Spring allows clients to subscribe to `/user/queue/notifications`; `UserDestinationMessageHandler` translates the logical destination into a session-specific destination. The server can send messages with:

```java
// Fragment inside a service with SimpMessagingTemplate messagingTemplate injected.
messagingTemplate.convertAndSendToUser(
        "alice", "/queue/notifications", "You've got mail");
```

If user `alice` has a session on node B while the event is processed on node A, node A cannot resolve the user destination using only its local registry. Spring provides settings to coordinate across multiple nodes:

- `setUserDestinationBroadcast(...)`: broadcasts unresolved user destinations so other nodes can look up matching sessions.
- `setUserRegistryBroadcast(...)`: shares user session registry info across app instances via a broker destination.

Example **only when a relay/external broker and matching topology are configured**:

```java
@Override
public void configureMessageBroker(MessageBrokerRegistry registry) {
    registry.setApplicationDestinationPrefixes("/app");
    registry.setUserDestinationPrefix("/user");

    registry.enableStompBrokerRelay("/topic", "/queue")
            .setRelayHost("broker.internal")
            .setRelayPort(61613);

    registry.setUserDestinationBroadcast("/topic/unresolved-user");
    registry.setUserRegistryBroadcast("/topic/user-registry");
}
```

This is a **configuration fragment**: host, credentials, and SSL are not shown in full. Destinations used for metadata/registry broadcasts are **internal coordination channels**—never allow arbitrary clients to `SEND` to or `SUBSCRIBE` from them; enforce authorization.

When user destinations resolve to per-session queues on an external broker, manage inactive queue cleanup, TTL, or auto-delete per your broker product. Some brokers create temporary queues per WebSocket session; mass reconnects must not accumulate millions of stale queues.

## 8. Decision Making and Scaling Roadmap

### 8.1 Decision table

| Requirement | Recommended option | Why? |
| --- | --- | --- |
| Learning Spring STOMP, single JVM | Simple broker | Lightweight, no broker operations |
| Single-node dashboard, best-effort notifications | Simple broker + REST snapshot/resync | Durable fan-out is unnecessary |
| Multiple Spring pods broadcasting to one topic | External STOMP broker/relay or shared message bus | Avoids node-isolated subscriptions |
| Delivering notifications to offline users | Database/outbox and replay; optionally external broker | WebSocket subscriptions are not durable inboxes |
| Needing ACKs, redelivery, dead-letter, retries | Full-featured messaging broker + ACK design | Simple broker is not a reliable work queue |
| Tens of thousands of connections and heavy fan-out | Benchmark WebSocket gateway + relay + broker resources | Relay adds TCP connections and broker load |
| Per-user authorization and privacy | Spring Security on handshake and STOMP destinations | Broker choice does not replace authorization |
| Global ordering | Design partitioning/sequences/deduplication | Spring outbound order flag is per-session only |

Do not choose a broker based solely on node count. Quantify **concurrent WebSocket sessions**, messages/sec, fan-out, payload sizes, acceptable latency, uptime, RPO/RTO, offline reliability, ordering, operational cost, and security boundaries.

### 8.2 Steps to migrate from simple to relay

1. Inventory all broker prefixes, topics, queues, publishers/subscribers, and user destinations; verify current semantics.
2. Select a broker with a STOMP listener and matching routing semantics; configure accounts/permissions, TLS/HA, and metrics.
3. Preserve the WebSocket endpoint and `/app` application prefix where possible. Switch **one** broker handler from simple to relay; avoid overlapping prefixes.
4. Test with at least **two Spring nodes** and WebSocket clients connected to different nodes; publish from each node and verify recipients.
5. Test user destinations across multiple sessions/nodes, registry broadcasts, and queue cleanup.
6. Inject faults: broker restart, DNS/TLS failure, node loss, client reconnects, duplicate/out-of-order messages, and slow consumers.
7. Monitor backlogs, message latency, broker TCP connections, authorization failures, and Spring outbound buffers, and prepare a rollback plan.

The Spring app still handles business logic in `@MessageMapping`, and you should keep HTTP/WebSocket entrypoints unchanged aside from approved semantic shifts. An external broker **does not replace** your business database, REST queries, or durable outbox.

## 9. Runnable Java 17+ Example with the Simple Broker

This example includes a Spring Boot server broadcasting notifications to `/topic/events` and a Java JDK WebSocket client sending STOMP CONNECT/SUBSCRIBE directly. No Internet is needed when **running internal HTTP requests**; the first build may fetch Maven dependencies. This is a single-node subscription demo to understand before introducing a relay.

### 9.1 Structure and Gradle

```text
broker-demo/
├── build.gradle
└── src/main/java/demo/
    ├── BrokerDemoApplication.java
    └── StompDemoClient.java
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
version = '1.0'

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
    mainClass = 'demo.BrokerDemoApplication'
}

tasks.register('runStompClient', JavaExec) {
    group = 'application'
    classpath = sourceSets.main.runtimeClasspath
    mainClass = 'demo.StompDemoClient'
}
```

Use an installed Gradle or a Spring Boot-compatible Gradle Wrapper. The first source file contains the server, configuration, and REST publisher; the second contains the client. You can rely on the Spring Boot Gradle plugin BOM rather than hardcoding versions when integrating into an existing project.

### 9.2 Spring Boot server

`src/main/java/demo/BrokerDemoApplication.java`:

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.MediaType;
import org.springframework.messaging.simp.SimpMessagingTemplate;
import org.springframework.messaging.simp.config.MessageBrokerRegistry;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.socket.config.annotation.EnableWebSocketMessageBroker;
import org.springframework.web.socket.config.annotation.StompEndpointRegistry;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;

@SpringBootApplication
public class BrokerDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(BrokerDemoApplication.class, args);
    }
}

@Configuration
@EnableWebSocketMessageBroker
class BrokerConfig implements WebSocketMessageBrokerConfigurer {
    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/ws")
                .setAllowedOriginPatterns("http://localhost:*");
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.setApplicationDestinationPrefixes("/app");
        registry.enableSimpleBroker("/topic", "/queue");
    }
}

@RestController
class EventPublisher {
    private final SimpMessagingTemplate messagingTemplate;

    EventPublisher(SimpMessagingTemplate messagingTemplate) {
        this.messagingTemplate = messagingTemplate;
    }

    @PostMapping(
            path = "/api/events",
            consumes = MediaType.TEXT_PLAIN_VALUE,
            produces = MediaType.TEXT_PLAIN_VALUE)
    String publish(@RequestBody String body) {
        messagingTemplate.convertAndSend("/topic/events", body);
        return "sent: " + body;
    }
}
```

`@EnableWebSocketMessageBroker` creates the messaging infrastructure. The REST controller does not hold the list of WebSocket sessions directly; it uses `SimpMessagingTemplate`. The response `sent: hello` means the HTTP method reached its return statement—**it does not guarantee** every subscriber has received it. This API has no authentication and is only suitable for local demos.

### 9.3 JDK WebSocket client sending STOMP frames

`src/main/java/demo/StompDemoClient.java`:

```java
package demo;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.WebSocket;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionStage;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.TimeUnit;

public final class StompDemoClient {
    private static final class Receiver implements WebSocket.Listener {
        final BlockingQueue<String> frames = new LinkedBlockingQueue<>();
        private final StringBuilder pending = new StringBuilder();

        @Override
        public void onOpen(WebSocket socket) {
            socket.request(1);
        }

        @Override
        public CompletionStage<?> onText(
                WebSocket socket, CharSequence chunk, boolean last) {
            synchronized (pending) {
                pending.append(chunk);
                int end;
                while ((end = pending.indexOf("\u0000")) >= 0) {
                    String frame = pending.substring(0, end);
                    pending.delete(0, end + 1);
                    frame = frame.replaceFirst("^[\\r\\n]+", "");
                    if (!frame.isEmpty()) {
                        frames.offer(frame);
                    }
                }
            }
            socket.request(1);
            return CompletableFuture.completedFuture(null);
        }

        @Override
        public void onError(WebSocket socket, Throwable error) {
            frames.offer("ERROR\n\n" + error.getMessage());
        }
    }

    public static void main(String[] args) throws Exception {
        Receiver receiver = new Receiver();
        WebSocket socket = HttpClient.newHttpClient()
                .newWebSocketBuilder()
                .subprotocols("v12.stomp")
                .buildAsync(URI.create("ws://localhost:8080/ws"), receiver)
                .get(10, TimeUnit.SECONDS);

        try {
            socket.sendText(
                    "CONNECT\naccept-version:1.2\nhost:localhost"
                    + "\nheart-beat:0,0\n\n\u0000", true).join();

            String connected = receiver.frames.poll(10, TimeUnit.SECONDS);
            if (connected == null || !connected.startsWith("CONNECTED")) {
                throw new IllegalStateException(
                        "Expected CONNECTED: " + connected);
            }
            System.out.println("CONNECTED");

            socket.sendText(
                    "SUBSCRIBE\nid:subscription-1"
                    + "\ndestination:/topic/events"
                    + "\nack:auto\n\n\u0000", true).join();

            System.out.println("SUBSCRIBED /topic/events");
            System.out.println("WAITING FOR MESSAGE");

            String message = receiver.frames.poll(60, TimeUnit.SECONDS);
            if (message == null || !message.startsWith("MESSAGE")) {
                throw new IllegalStateException(
                        "Expected MESSAGE: " + message);
            }

            int separator = message.indexOf("\n\n");
            if (separator < 0) {
                throw new IllegalStateException("Missing frame separator");
            }
            System.out.println("MESSAGE: " + message.substring(separator + 2));

            socket.sendText("DISCONNECT\n\n\u0000", true).join();
            socket.sendClose(WebSocket.NORMAL_CLOSURE, "done").join();
        } finally {
            socket.abort();
        }
    }
}
```

Here JDK `WebSocket` implements WebSocket frames only, **with no STOMP client library**; we manually send STOMP CONNECT/SUBSCRIBE and scan for NUL bytes to split frames. Fragment reassembly uses `StringBuilder` in case a STOMP frame is split across WebSocket transport chunks. The demo disables STOMP heartbeats, reads a single message, and omits full STOMP features like `content-length` with embedded NUL bytes; production code should use a proper STOMP client library.

**Note:** `.subprotocols("v12.stomp")` in the HTTP/WebSocket handshake is completely separate from the STOMP `CONNECT` frame sent after the socket opens. The Spring server handles negotiation automatically if STOMP 1.2 is supported.

### 9.4 Running with three terminals

Terminal 1 — start the server and wait until port 8080 is ready:

```bash
gradle bootRun
```

Terminal 2 — connect and subscribe the client:

```bash
gradle runStompClient
```

Output printed by the client program **before the message arrives**:

```text
CONNECTED
SUBSCRIBED /topic/events
WAITING FOR MESSAGE
```

Terminal 3 — once the client prints `WAITING FOR MESSAGE`, send an HTTP POST:

```bash
curl -X POST http://localhost:8080/api/events -H "Content-Type: text/plain" --data-binary "hello"
```

If using Windows PowerShell:

```powershell
Invoke-RestMethod -Method Post -Uri 'http://localhost:8080/api/events' -ContentType 'text/plain' -Body 'hello'
```

REST response body:

```text
sent: hello
```

Client in Terminal 2 then prints:

```text
MESSAGE: hello
```

Spring, Gradle, and Tomcat may emit additional logs; the lines above are **exactly what the demo app itself prints** when run in sequence without timeouts on port 8080. If the port changes, update the URI in the Java client. The demo omits `@MessageMapping` to focus on the **application publisher → broker → subscriber** path. You can start two clients before sending the POST to observe fan-out on a single Spring instance.

### 9.5 Trying a broker swap while keeping the endpoint

Once an external broker with an enabled STOMP/TCP listener is running, replace in `BrokerConfig.configureMessageBroker`:

```java
registry.enableSimpleBroker("/topic", "/queue");
```

with the corresponding configuration:

```java
registry.enableStompBrokerRelay("/topic", "/queue")
        .setRelayHost("127.0.0.1")
        .setRelayPort(61613)
        .setSystemLogin("configured-system-user")
        .setSystemPasscode("configured-secret")
        .setClientLogin("configured-client-user")
        .setClientPasscode("configured-secret");
```

This is an **illustrative configuration** and will not run without a broker and valid credentials; production setups read secrets from environment/secret managers and configure TLS. Once the external broker handles `/topic/events` and the Spring relay is active, clients still subscribe through the same `/ws` endpoint. To **verify scaling**, launch **two Spring instances** on different ports, connect two clients to separate instances, and publish from just one node; messages must reach clients according to your configured broker topology. A single-node demo does not prove cross-node fan-out.

## 10. Ordering, Backpressure, and Operations

### 10.1 Ordering is not automatically guaranteed system-wide

Spring's inbound/outbound channels use executors. With multiple threads, messages can be processed or flushed out of arrival order on **the same session** unless configured. Spring offers these options:

```java
// Fragments placed inside a WebSocketMessageBrokerConfigurer:
@Override
public void registerStompEndpoints(StompEndpointRegistry registry) {
    registry.addEndpoint("/ws");
    registry.setPreserveReceiveOrder(true);
}

@Override
public void configureMessageBroker(MessageBrokerRegistry registry) {
    registry.setApplicationDestinationPrefixes("/app");
    registry.enableSimpleBroker("/topic");
    registry.setPreservePublishOrder(true);
}
```

`setPreserveReceiveOrder(true)` processes inbound messages per session in receive order. `setPreservePublishOrder(true)` preserves outbound channel publish order per session. Both add overhead and **do not guarantee global ordering** across nodes, topics, broker queues, or reconnects. When strict ordering is mandatory, use sequence numbers, entity versions, stable partitioning/ordering keys, and client-side duplicate/out-of-order handling.

### 10.2 Slow consumers, send buffers, and message size

Slow-reading clients cause WebSocket outbound buffers to grow, pushing the server toward memory/latency limits. A suitable configuration might look like:

```java
import org.springframework.web.socket.config.annotation.WebSocketTransportRegistration;

// Fragment method of WebSocketMessageBrokerConfigurer:
@Override
public void configureWebSocketTransport(
        WebSocketTransportRegistration registration) {
    registration.setMessageSizeLimit(128 * 1024);
    registration.setSendBufferSizeLimit(512 * 1024);
    registration.setSendTimeLimit(15_000);
}
```

Message/buffer limits are in bytes and send time is in milliseconds. These limits govern **the transport between Spring and clients**, not the external broker's capacity. When large payloads must be supported, consider REST/object storage for bulk data and small WebSocket notifications.

### 10.3 Metrics and potential failures

| Symptom | Likely cause | How to inspect |
| --- | --- | --- |
| Some clients on another node miss messages | Simple brokers isolated per pod | Add node/session ID logs, inspect broker topology |
| STOMP connected but subscribe receives no messages | Wrong prefix/destination or sent before subscribe | Inspect frames, routing, authorization |
| Relay reports broker unavailable | STOMP listener, DNS/TLS/firewall, or auth error | `BrokerAvailabilityEvent`, TCP/broker logs |
| Broker overloaded with many clients | Per-session relay TCP connections, broker limits | Active connections, memory, FDs, CPU |
| User not found on current node | Distributed user registry/resolution | Configure broadcasts, run multi-node tests |
| Client receives slowly / drops | Send buffer, proxy timeout, heartbeats | Outbound queue, close codes, network |
| Duplicate/lost messages after retry/reconnect | Missing end-to-end idempotency | Event IDs, outbox/replay, ACK policies |
| Out-of-order UI updates | Concurrent channels, broker/order semantics | Sequence numbers, per-session order options |

**Minimum monitoring:** active WebSocket sessions, subscriptions, inbound/outbound executor queues, message latency, errors/close codes, outbound send buffers, broker TCP connections, broker memory/disk/backlogs, reconnect rates, missed heartbeats, and publish/delivery metrics per SLA. Monitoring `SimpUserRegistry` alone does not prove clients processed events.

### 10.4 Durable pattern for business events

For notifications whose purpose is simply telling the UI "new data is available", a common pattern is:

```text
Business transaction
     │
     ├─ persist DB + event/outbox (durable)
     │
     ▼
Reliable delivery/event processing
     │
     ▼
Realtime notification via WebSocket/STOMP
     │
     ▼
Client calls REST/query to load the latest snapshot
```

When a client drops off the network, it reconnects/re-subscribes and fetches a snapshot or cursor-based events; never expect WebSocket to hold offline messages. This is especially critical for financial state, orders, and long-impact operations.

## 11. Security and Common Migration Mistakes

- **Never treat broker credentials as user authentication:** the relay uses configured service credentials to connect to the broker. Authenticate users at HTTP/WebSocket or STOMP CONNECT and authorize SEND/SUBSCRIBE per destination.
- **Never expose internal user-registry topics publicly:** destinations used by `setUserDestinationBroadcast`/`setUserRegistryBroadcast` must be protected.
- **Never believe sticky sessions solve cross-node fan-out:** subscriptions still stay inside separate simple-broker RAM.
- **Never assume `/queue` keeps identical meaning:** full brokers typically enforce different queue semantics than the simple broker; verify destination mappings.
- **Never send secrets in STOMP headers and log full frames:** protect tokens, cookies, and user details; use TLS for both client→Spring and Spring→broker.
- **Never use the simple broker for ACK/durable workflows:** retries, ACKs, and transactions require a properly designed broker and contract.
- **Never assume a single `convertAndSend` is exactly-once:** loss/duplication can occur on retries, reconnects, or offline clients; build message IDs/idempotency into the protocol.
- **Never forget reconnect/resubscribe on node/broker restarts:** WebSocket OPEN after reconnect does not mean subscriptions were restored.
- **Never equate STOMP heartbeats with TCP keepalives/WebSocket Ping/Pong:** these operate at different layers, and timeouts must fit proxies.
- **Never leave send buffers or broker connections unbounded:** size for load, set limits, enforce slow-consumer policies, and monitor brokers/nodes.
- **Never mix relay and simple broker on the same destination prefixes:** it makes handler selection unpredictable or causes duplicate deliveries.
- **Never deploy an external broker before verifying its STOMP listener:** RabbitMQ plugins/resources, broker accounts, destination permissions, and network/TLS must all be ready.

## 12. Comprehension Check Questions

**1. Two Spring pods both enable the `/topic/news` simple broker. A POST publishes on pod A. Will a user on pod B receive it automatically?**

No. Pod A's simple broker only knows about subscribers currently connected to pod A. If the business requires system-wide delivery, a shared broker or message bus is required.

**2. Does `/queue/jobs` on the simple broker guarantee only one of two subscribers receives each job?**

No. With the simple broker, `/queue` is just a string prefix; competing-consumer queue semantics are not guaranteed.

**3. Does a relay connected to RabbitMQ automatically make every message durable?**

No. Durability depends on queue/exchange/destination mappings, broker settings, headers, publisher/consumer confirmations, and application idempotency.

**4. Does the relay use one TCP connection for all WebSocket clients?**

False. It opens a separate client relay TCP connection per STOMP client session plus a system connection for application-originated messages.

**5. Does `BrokerAvailabilityEvent` guarantee every client received the latest message?**

No. It reflects broker system availability; there is no automatic end-to-end client receipt.

**6. Does enabling `setPreservePublishOrder(true)` provide global exactly-once delivery?**

No. It handles outbound publish order within a single client session at some overhead; sequences/deduplication and broker contracts are still required.

**7. One user is connected to two different Spring instances; why does `/user/queue/notifications` need extra design?**

User destinations must resolve to the right session. Configure user-registry/destination broadcasts via the broker and test multi-node when events can arrive on a different node than the one holding the session.

**8. When a client is offline for 10 minutes, how do you recover critical notifications?**

Persist business data durably, reconnect/re-subscribe, and fetch a snapshot or cursor-based replay. The simple broker does not store durable offline messages.

## Official References

- [Spring Framework — STOMP Enable](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/enable.html)
- [Spring Framework — Simple Broker](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-simple-broker.html)
- [Spring Framework — External Broker](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-broker-relay.html)
- [Spring Framework — Connecting to Broker](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-broker-relay-configure.html)
- [Spring Framework — Message Flow](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/message-flow.html)
- [Spring Framework — User Destinations](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/user-destination.html)
- [Spring Framework — Message Order](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/ordered-messages.html)
- [Spring Framework — Monitoring](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/stats.html)
