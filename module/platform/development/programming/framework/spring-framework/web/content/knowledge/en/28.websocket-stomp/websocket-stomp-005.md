# WebSocket and STOMP: Message Limits, Concurrent Sending, Timeouts, and Disconnection

## 1. Scoping Properly: Frames, STOMP Messages, and Sessions

In Spring Framework, WebSocket creates a long-lived bidirectional connection between client and server; STOMP is a frame-based messaging protocol running on top of that connection. A Spring application using `@EnableWebSocketMessageBroker` typically has these stages:

```text
Browser/STOMP application
    │ HTTP Upgrade (handshake) → WebSocket session
    │ STOMP CONNECT / SUBSCRIBE / SEND / DISCONNECT
    ▼
WebSocket engine (Tomcat/Jetty/...)
    │ handles WebSocket frames, frame/buffer limits, idle timeout
    ▼
STOMP sub-protocol handler
    │ reassembles/decodes STOMP messages, checks messageSizeLimit
    ▼
clientInboundChannel → @MessageMapping / broker
    │
    ▼
clientOutboundChannel → WebSocket session
    │    serializes sends; buffers pending data when client is slow
    ▼
Browser receives MESSAGE or socket closes
```

Distinguish three concepts:

- **WebSocket frame/message:** the unit of the WebSocket protocol, handled by the HTTP upgrade endpoint and underlying WebSocket library. Size limits depend on the container and engine configuration.
- **STOMP frame/message:** commands `CONNECT`, `SEND`, `SUBSCRIBE`, `MESSAGE`, `ERROR`, `DISCONNECT` with headers and body. A large STOMP message may arrive across multiple WebSocket messages/chunks and is reassembled by Spring's decoder before entering the application.
- **WebSocket/STOMP session:** a connection carrying subscription state, heartbeats, user identity, and an outbound buffer. Per-session limits differ from system-wide total session limits.

This lesson applies to **Spring Framework 6.1.x / Spring Boot 3.3.x with Java 17+** using Spring WebSocket + STOMP on the Servlet stack. Example limit values are **for learning**; real configurations must be load-tested and account for client, proxy, and external broker limits (if any).

## 2. Message Size Limits: Inbound STOMP vs. Container Buffers

In `WebSocketMessageBrokerConfigurer`, use:

```java
@Override
public void configureWebSocketTransport(WebSocketTransportRegistration registration) {
    registration.setMessageSizeLimit(64 * 1024); // bytes
}
```

`setMessageSizeLimit` bounds **inbound STOMP messages received from clients**, even when assembled from multiple WebSocket messages. Spring STOMP transport's default is **64 KiB** per the Spring 6.1 Javadoc. The number is in **bytes**, not Unicode characters. On the wire, STOMP headers and body also consume space; a JSON payload near the ceiling can still exceed the limit once overhead is included.

Flow for an oversized message:

```text
Client sends STOMP SEND (with large body)
 → WebSocket engine receives parts
 → STOMP decoder reassembles content
 → exceeds messageSizeLimit
 → protocol/transport-layer error, may emit ERROR/close session
 → @MessageMapping is not invoked successfully
```

Do not assume every container and error type returns the same **close code** or `ERROR` string. How it surfaces in the browser/logs depends on which component rejected it (WebSocket engine vs. STOMP decoder), versions, and connection state.

**Another limit at the WebSocket engine level** (for example Jakarta WebSocket/Tomcat configuration):

```java
@Bean
ServletServerContainerFactoryBean webSocketContainer() {
    ServletServerContainerFactoryBean factory =
        new ServletServerContainerFactoryBean();
    factory.setMaxTextMessageBufferSize(32 * 1024);
    factory.setMaxBinaryMessageBufferSize(32 * 1024);
    factory.setMaxSessionIdleTimeout(120_000L);
    return factory;
}
```

Requires imports `org.springframework.context.annotation.Bean` and `org.springframework.web.socket.server.standard.ServletServerContainerFactoryBean`. This is **illustrative configuration code**, not a mandatory choice for every app. It configures WebSocket text/binary receive capacity and idle timeout (ms) on the server container, whereas `setMessageSizeLimit` bounds the assembled STOMP message. For STOMP, Spring may adjust the underlying WebSocket buffer size enough to receive chunks sent by STOMP clients; do not treat both numbers as the same limit.

Small limits help protect resources, but you must account for legitimate cases: JSON with long Unicode fields, messages with large headers, initial snapshots, etc. For files or multi-MB objects, it is better to **upload via HTTP/object storage**, then emit a small event over STOMP carrying a controlled URL/ID. Do not raise `setMessageSizeLimit` indefinitely as a substitute for an upload workflow.

**Inbound differs from outbound:** `setMessageSizeLimit` is not a cap on `MESSAGE` frames pushed out by the server. To restrict outbound data, actively control payloads in business logic, the broker, and send buffer capacities.

## 3. Concurrent Sending: Each WebSocket Session Must Serialize Sends

A WebSocket session must not have multiple threads concurrently calling `sendMessage` on the same connection. In Spring's STOMP broker model, outbound deliveries pass through `clientOutboundChannel` (which may have multiple worker threads), while Spring guarantees that when writing to **a single WebSocket session**, only one thread sends at a time.

Real problems arise when a client reads slower than the server emits:

```text
Server emits MESSAGE #1, #2, #3, #4...
                   │
                   ▼
clientOutboundChannel (multithreaded)
                   │
                   ▼
Session A: send #1 is slow
           #2, #3, #4 must wait in buffer
                   │
                   ├─ buffer keeps growing
                   └─ check sendTimeLimit / sendBufferSizeLimit
                       if exceeded: session may be terminated
```

Spring uses a mechanism similar to `ConcurrentWebSocketSessionDecorator`: a wrapper serializes sends on a session; new sends arriving while another thread is writing are queued. Therefore, *thread-safe sending* **does not mean free RAM or guarantee the receiver keeps up**.

Configuring outbound limits:

```java
@Override
public void configureWebSocketTransport(WebSocketTransportRegistration registration) {
    registration
        .setMessageSizeLimit(64 * 1024)       // inbound STOMP, bytes
        .setSendBufferSizeLimit(512 * 1024)   // outbound buffer / session, bytes
        .setSendTimeLimit(15_000);            // send duration, milliseconds
}
```

Mechanics:

- `setSendBufferSizeLimit(512 * 1024)` sets the limit on **pending outbound data** per session when sends back up. This is neither an unbounded queue nor a shared buffer across all sessions.
- `setSendTimeLimit(15_000)` sets the duration threshold for a stalled send operation. It **is not** an end-to-end deadline from publish until the client application finishes processing.
- While one send holds the write lock and additional sends arrive, the wrapper checks elapsed send time and pending byte count; if exceeded, it may throw `SessionLimitExceededException` and close the session with an unreliable state.

**Important technical warning:** this send-time limit is not a hard timer that interrupts a blocking send to the millisecond. In the decorator implementation, limits are typically checked when another send occurs or on close; a single long-blocked send may not be detected immediately at the threshold. Combine container/network timeouts, monitoring, and appropriate backpressure policies. Do not treat raising `sendTimeLimit` as a fix for a browser that stopped reading.

### When writing a raw WebSocketHandler

If you do **not** use the STOMP broker config and instead send directly from multiple threads, wrap `WebSocketSession` with `ConcurrentWebSocketSessionDecorator` or implement an equivalent serializing queue:

```java
WebSocketSession safe = new ConcurrentWebSocketSessionDecorator(
    originalSession, 15_000, 512 * 1024
);

// Application threads only call safe.sendMessage(message);
// do not mix calls to originalSession.sendMessage(message).
```

This is an illustrative snippet requiring imports for `WebSocketSession` and `org.springframework.web.socket.handler.ConcurrentWebSocketSessionDecorator`. **Do not manually wrap again** sessions already managed by the Spring STOMP stack; stacking wrappers in the wrong place can disrupt lifecycle and metrics.

### Concurrent sending vs. receive ordering

Events may be published through `clientOutboundChannel` across multiple threads, so the order **seen by the client** can differ from the order the application published them. If per-session ordering is required, enable:

```java
@Override
public void configureMessageBroker(MessageBrokerRegistry registry) {
    registry.enableSimpleBroker("/topic", "/queue");
    registry.setApplicationDestinationPrefixes("/app");
    registry.setPreservePublishOrder(true);
}
```

Since Spring Framework 6.1, you can also preserve **inbound processing order within a client session**:

```java
@Override
public void registerStompEndpoints(StompEndpointRegistry registry) {
    registry.addEndpoint("/ws");
    registry.setPreserveReceiveOrder(true);
}
```

This guarantees **per-session** ordering, not global ordering across all clients, and incurs overhead. It does not turn STOMP into an exactly-once protocol or resolve ordering when external publishers write directly to a broker outside Spring.

## 4. Timeouts and Heartbeats: Multiple Independent Clocks

"WebSocket timeout" can refer to completely different things:

| Timeout/monitor | Purpose | Typical configuration location |
| --- | --- | --- |
| HTTP handshake/upgrade | Establishing HTTP → WebSocket connection | HTTP server/proxy/client; not `sendTimeLimit` |
| WebSocket idle timeout | Socket has no traffic for a period | WebSocket container, e.g., `setMaxSessionIdleTimeout` |
| STOMP heartbeats | Detecting when one side stops sending/receiving traffic as negotiated | STOMP `heart-beat`, TaskScheduler, broker |
| Outbound send time | A single send to client takes too long | `setSendTimeLimit` |
| Client reconnect delay | Wait time before attempting to reconnect | STOMP/browser client or reconnect library |
| Business acknowledgement/receipt | Has the peer processed/persisted business logic? | STOMP `receipt` or application-level ACK/event, per contract |

**STOMP heartbeats** use millisecond pairs `heart-beat:cx,cy` in `CONNECT` and `heart-beat:sx,sy` in `CONNECTED` to negotiate minimum intervals: each side states how often it can send and expects to receive. A STOMP heartbeat frame can be just a single newline byte; when other STOMP frames flow, that traffic also satisfies the liveness cadence. They do not guarantee the endpoint succeeded in processing a business message.

With the simple broker, heartbeats require a configured `TaskScheduler`:

```java
@Override
public void configureMessageBroker(MessageBrokerRegistry registry) {
    registry.enableSimpleBroker("/topic")
        .setTaskScheduler(heartbeatTaskScheduler)
        .setHeartbeatValue(new long[] {10_000, 10_000});
    registry.setApplicationDestinationPrefixes("/app");
}
```

`heartbeatTaskScheduler` is a `TaskScheduler` created/injected into the configuration (full example in section 7). The two numbers are suggested send/receive intervals in Spring's broker mechanism, **not an HTTP request timeout**. With multiple proxies/load balancers, intermediate idle timeouts must exceed the heartbeat interval with enough margin for jitter/network delays. If a proxy drops the socket despite heartbeats, check WebSocket Upgrade policy, TCP idle settings, and load balancing.

**SockJS:** if SockJS fallback is enabled, it also has its own heartbeat mechanism; once STOMP heartbeats are negotiated, SockJS heartbeats are typically disabled to avoid redundancy. SockJS HTTP streaming/polling transports have different timeout and resource characteristics from native WebSocket, so WebSocket assumptions cannot be copied verbatim.

**Broker relay:** when Spring uses an external broker (RabbitMQ/ActiveMQ, etc.), the broker relay connection heartbeat and the WebSocket client heartbeat are two separate streams. The relay can reconnect to the broker at the system level, **it does not automatically reconnect dropped WebSocket clients**.

## 5. Disconnection: Graceful, Abnormal, and Limit-Triggered Closures

A session can end because of:

1. **Client-initiated:** sends STOMP `DISCONNECT` and closes WebSocket (to be more graceful, it can wait for a STOMP `RECEIPT` if the broker supports it and the client requests one). Closing a tab may not leave time to send `DISCONNECT`.
2. **Network/proxy:** Wi-Fi drop, NAT/LB closing idle connections, client sleeping, power loss. The server does not necessarily notice immediately; heartbeats/timeouts detect it after an interval.
3. **Exceeded message size / buffer / send time:** Spring or the container rejects data or closes the session.
4. **Protocol/auth/server:** malformed STOMP frame, invalid subscription, rejected handshake, server error, or restart.
5. **External broker unavailable:** can affect publishing/subscriptions; depending on config, broker availability and reconnection must be handled separately.

Key Spring events to know:

- `SessionConnectEvent`: server received a STOMP CONNECT frame, **not sufficient to confirm CONNECTED**.
- `SessionConnectedEvent`: broker sent the CONNECTED frame; the STOMP session can be considered established.
- `SessionSubscribeEvent` / `SessionUnsubscribeEvent`: tracks subscription changes.
- `SessionDisconnectEvent`: the STOMP session ended, whether initiated by client or WebSocket transport. **One session may emit this event more than once**, so cleanup must be idempotent.

Safe cleanup is typically an idempotent operation:

```java
@EventListener
public void onDisconnect(SessionDisconnectEvent event) {
    String sessionId = event.getSessionId();
    SessionState removed = activeSessions.remove(sessionId);
    if (removed != null) {
        releaseResources(removed);
    }
}
```

This is **Java pseudocode**: `SessionState`, `activeSessions`, and `releaseResources` are components the application must define. `ConcurrentHashMap.remove` returns `null` on a second cleanup call, avoiding duplicate side effects. If cleanup touches a database or external system, use appropriate transactions/idempotency keys. Do not keep a `Set` of every disconnected session ID forever in the heap.

**Recovery after reconnect:** a new WebSocket/STOMP connection usually has a **new session ID**. The client must reconnect, send CONNECT, and SUBSCRIBE again; in-memory subscription state from the old session is not automatically restored. For critical chat/notifications, use offsets/event IDs to sync missed messages, or a persistent broker with ACK/transactions per design. STOMP heartbeats or a live WebSocket TCP connection only confirm liveness; they do not provide exactly-once delivery.

## 6. Choosing Limits by Load and Observing Symptoms

Suppose an average notification is 2 KiB and the per-session outbound buffer is 64 KiB. If a client stalls while messages keep arriving, a few dozen queued messages can approach the limit (exact count depends on framing, serialization, and overhead). With 10,000 concurrently slow clients, buffers alone at an assumed 64 KiB/session peak equal **roughly 625 MiB** of queued data—excluding session objects, broker state, network buffers, TLS, and heap overhead. Therefore, do not raise buffer limits to "stop disconnects" before diagnosing why clients are slow.

As load grows, consider:

- **Payload:** shrink message sizes, send only needed fields, and avoid repeatedly sending large snapshots.
- **Outbound:** size `clientOutboundChannel` resources alongside slow-client counts, reduce publish rates, and coalesce/throttle updates where only the latest value matters.
- **Inbound:** rate-limit messages per user/connection at the gateway or app, validate destination permissions, validate schemas, and keep `setMessageSizeLimit` tight to the contract.
- **Memory:** session count × per-session buffer + inbound decode + broker queues + objects/direct heap; monitor heap and direct memory.
- **Liveness:** align heartbeats and idle timeouts across browser, broker, and proxy; measure false disconnects on flaky networks.
- **Ordering:** if strict per-session order is required, enable preserve-order and benchmark performance; for messages from multiple producers, use domain sequence IDs/ordering.
- **Scaling:** Spring's simple broker holds subscriptions in a single instance's memory; when multiple instances need cross-node routing, consider a broker relay or an appropriate message broker architecture with proper load balancer/session routing.

Do not rely on one "standard value" for every application. Real SLOs include connection counts, peak fan-out, messages/s, p95/p99 send latency, mobile clients, reconnect rates, and network conditions.

## 7. Runnable Example: Spring Boot 3.3 + STOMP and WebSocket Browser Client

This example exposes WebSocket endpoint `/ws`, subscription `/topic/echo`, and send destination `/app/echo`. It configures **1 KiB inbound STOMP**, **64 KiB outbound buffer**, **5-second send limit**, and enables order preservation and heartbeats. The HTML page uses native `WebSocket` and **string-based STOMP frames** so the protocol is visible without installing a JavaScript STOMP library.

Structure:

```text
stomp-limit-demo/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/demo/StompLimitDemo.java
    └── resources/static/index.html
```

**`settings.gradle`**

```groovy
rootProject.name = 'stomp-limit-demo'
```

**`build.gradle`** — JDK 17+, Gradle 8.x:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
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
    implementation 'org.springframework.boot:spring-boot-starter-websocket'
}
```

**`src/main/java/demo/StompLimitDemo.java`**

```java
package demo;

import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Lazy;
import org.springframework.context.event.EventListener;
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.SendTo;
import org.springframework.messaging.simp.SimpMessageHeaderAccessor;
import org.springframework.messaging.simp.config.MessageBrokerRegistry;
import org.springframework.scheduling.TaskScheduler;
import org.springframework.scheduling.concurrent.ThreadPoolTaskScheduler;
import org.springframework.stereotype.Component;
import org.springframework.stereotype.Controller;
import org.springframework.web.socket.config.annotation.EnableWebSocketMessageBroker;
import org.springframework.web.socket.config.annotation.StompEndpointRegistry;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;
import org.springframework.web.socket.config.annotation.WebSocketTransportRegistration;
import org.springframework.web.socket.messaging.SessionConnectedEvent;
import org.springframework.web.socket.messaging.SessionDisconnectEvent;

@SpringBootApplication
public class StompLimitDemo {
    public static void main(String[] args) {
        SpringApplication.run(StompLimitDemo.class, args);
    }
}

@Configuration
@EnableWebSocketMessageBroker
class SocketConfig implements WebSocketMessageBrokerConfigurer {
    @Autowired
    @Lazy
    @Qualifier("stompHeartbeatScheduler")
    private TaskScheduler heartbeatScheduler;

    @Bean("stompHeartbeatScheduler")
    ThreadPoolTaskScheduler stompHeartbeatScheduler() {
        ThreadPoolTaskScheduler scheduler = new ThreadPoolTaskScheduler();
        scheduler.setPoolSize(1);
        scheduler.setThreadNamePrefix("stomp-heartbeat-");
        return scheduler;
    }

    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/ws");
        registry.setPreserveReceiveOrder(true);
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.setApplicationDestinationPrefixes("/app");
        registry.enableSimpleBroker("/topic")
            .setTaskScheduler(heartbeatScheduler)
            .setHeartbeatValue(new long[] {10_000, 10_000});
        registry.setPreservePublishOrder(true);
    }

    @Override
    public void configureWebSocketTransport(WebSocketTransportRegistration reg) {
        reg.setMessageSizeLimit(1024)           // 1 KiB inbound STOMP
            .setSendBufferSizeLimit(64 * 1024)  // outbound / session
            .setSendTimeLimit(5_000);           // ms
    }
}

record EchoPayload(String text) {}

@Controller
class EchoController {
    @MessageMapping("/echo")
    @SendTo("/topic/echo")
    public EchoPayload echo(EchoPayload payload) {
        return new EchoPayload("echo: " + payload.text());
    }
}

@Component
class SessionEvents {
    private final ConcurrentMap<String, Boolean> live =
        new ConcurrentHashMap<>();

    @EventListener
    public void onConnected(SessionConnectedEvent event) {
        String sessionId = SimpMessageHeaderAccessor
            .wrap(event.getMessage()).getSessionId();
        if (sessionId != null) {
            live.put(sessionId, Boolean.TRUE);
        }
    }

    @EventListener
    public void onDisconnect(SessionDisconnectEvent event) {
        if (live.remove(event.getSessionId()) != null) {
            System.out.println("Closed STOMP session: " + event.getSessionId());
        }
    }
}
```

**`src/main/resources/static/index.html`**

```html
<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>STOMP connection limits</title>
</head>
<body>
  <h1>STOMP over WebSocket</h1>
  <button id="connect">Connect</button>
  <button id="small">Send small message</button>
  <button id="large">Send oversized message</button>
  <button id="disconnect">Disconnect</button>
  <pre id="log"></pre>
  <script>
    let socket = null;
    let ready = false;

    const output = document.getElementById("log");
    function log(value) {
      output.textContent += value + "\n";
    }
    function sendFrame(command, headers, body = "") {
      if (!socket || socket.readyState !== WebSocket.OPEN) {
        log("Socket not open");
        return;
      }
      const lines = Object.entries(headers)
        .map(([name, value]) => name + ":" + value)
        .join("\n");
      socket.send(command + "\n" + lines + "\n\n" + body + "\0");
    }

    document.getElementById("connect").onclick = () => {
      ready = false;
      socket = new WebSocket(
        "ws://" + location.host + "/ws", "v12.stomp"
      );
      socket.onopen = () => {
        log("WebSocket OPEN");
        sendFrame("CONNECT", {
          "accept-version": "1.2",
          "host": location.hostname,
          "heart-beat": "0,0"
        });
      };
      socket.onmessage = (event) => {
        const frame = event.data;
        if (frame.startsWith("CONNECTED")) {
          ready = true;
          log("STOMP CONNECTED");
          sendFrame("SUBSCRIBE", {
            id: "sub-1", destination: "/topic/echo"
          });
        } else if (frame.startsWith("MESSAGE")) {
          log("MESSAGE: " + frame.split("\n\n")[1].replace(/\0$/, ""));
        } else if (frame.startsWith("ERROR")) {
          log("STOMP ERROR: " + frame);
        }
      };
      socket.onclose = (e) => {
        ready = false;
        log("WebSocket CLOSED: code=" + e.code + ", reason=" + e.reason);
      };
      socket.onerror = () => log("WebSocket transport error");
    };

    function sendText(text) {
      if (!ready) {
        log("Not STOMP CONNECTED");
        return;
      }
      sendFrame("SEND", {
        destination: "/app/echo",
        "content-type": "application/json"
      }, JSON.stringify({text}));
    }
    document.getElementById("small").onclick = () => sendText("Hello");
    document.getElementById("large").onclick = () => sendText("x".repeat(2048));
    document.getElementById("disconnect").onclick = () => {
      if (socket && socket.readyState === WebSocket.OPEN) {
        sendFrame("DISCONNECT", {});
        socket.close(1000, "done");
      }
    };
  </script>
</body>
</html>
```

In the project directory:

```bash
gradle bootRun
```

Once Spring Boot starts, open `http://localhost:8080/index.html` in a browser:

1. Click **Connect**: the log will show `WebSocket OPEN` and, when the broker confirms, `STOMP CONNECTED`. The client sends `SUBSCRIBE` to `/topic/echo`.
2. Click **Send small message**: once SUBSCRIBE has been processed by the broker, the browser receives a MESSAGE with body approximately `{"text":"echo: Hello"}` (in Jackson record JSON field order). If sent immediately after CONNECTED, wait briefly for the subscription to be processed first.
3. Click **Send oversized message**: the 2 KiB payload + STOMP headers exceed `setMessageSizeLimit(1024)`. The server must reject the message at the STOMP layer; the browser may see `ERROR`, socket closure, or a transport message depending on handler/container. **Do not assume a fixed CLOSE code or error string.**
4. Click **Disconnect** while open: sends `DISCONNECT` and closes the WebSocket; the server emits the disconnect event and cleans up. To verify duplicate events, try reconnecting or abruptly closing the tab; the listener succeeds only once per connected session.

**Most reliably observed results:** small requests produce Echo payloads; oversized requests are blocked; closing the connection frees the session. Logs include asynchronous IDs and ordering, so no fabricated fixed stdout transcript is shown.

The HTML example intentionally sets `heart-beat:0,0` to make manual frame inspection easier; thus this demo browser **does not perform client-side liveness checks**. In real applications, use a STOMP client library supporting heartbeats, reconnect/backoff, auth tokens, subscription restoration, and full receipt handling. If the page is deployed on HTTPS, WebSocket must use `wss://`, not `ws://` as on localhost.

## 8. Diagnosing Failures Layer by Layer

| Symptom | Likely cause | What to inspect |
| --- | --- | --- |
| Client sends large payload then socket closes | Exceeded STOMP `messageSizeLimit` or container limit | Byte size including headers, decoder/close reason logs, container text buffer |
| Slow client disconnected during heavy server broadcast | Outbound buffer grew or send took too long | `sendBufferSizeLimit`, `sendTimeLimit`, outbound channel queue, network/client throughput |
| Messages from same user arrive out of order | Processed on a multithreaded executor | `setPreservePublishOrder`, `setPreserveReceiveOrder`, publish ordering across producers |
| Disconnected after an idle period | STOMP heartbeat, container idle, or proxy/LB idle | Heartbeat negotiation, TaskScheduler, close code, proxy timeouts |
| Session still shows online after network drop | Disconnection not detected yet | Heartbeat/idle timeout, cleanup events, presence TTL |
| Duplicate cleanup/presence notifications | `SessionDisconnectEvent` can fire multiple times | Use remove-if-present, idempotency, deduplication |
| Session reconnects but subscriptions are gone | New connection gets a new session | Client must re-CONNECT + re-SUBSCRIBE and recover from last-event-id |
| Broker relay recovers but browser stays offline | System broker connection differs from client WebSocket connection | `BrokerAvailabilityEvent` and separate client reconnection |
| RAM grows during large fan-out | Many sessions × buffers, subscriptions, broker queues | Memory/GC, active/pending messages, payload size, slow consumers |

Essential metrics: active/closed WebSocket session counts, close codes by cause, STOMP CONNECTED/DISCONNECT counts, oversized message rate, `clientInboundChannel`/`clientOutboundChannel` queue sizes, send latency, slow client count, heartbeat scheduler health, memory usage, and reconnect count. Spring provides `WebSocketMessageBrokerStats` and STOMP/WebSocket stats; combine with infrastructure monitoring/metrics to observe proxies and external brokers as well. Do not log sensitive bodies or credentials while debugging.

## 9. Common Design Mistakes

1. **Confusing the STOMP message limit with a WebSocket frame limit.** A STOMP message can span multiple WebSocket chunks; limits differ at each layer.
2. **Treating `sendTimeLimit` as a hard request deadline.** It checks session send progress under contention/buffering, not whether the "client finished processing".
3. **Writing from multiple threads to a raw `WebSocketSession` without serializing.** For raw handlers, use a wrapper or queue; Spring's STOMP broker handles this internally.
4. **Increasing send buffers to prevent disconnects without addressing backpressure.** Many slow sessions can retain massive amounts of RAM.
5. **Equating heartbeats with business ACKs.** Pings/heartbeats only indicate liveness; message loss can still happen during disconnects or restarts.
6. **Relying on `SessionConnectEvent` to show a successful online state.** CONNECT was only received; `SessionConnectedEvent` indicates the STOMP handshake completed.
7. **Failing to make cleanup idempotent.** `SessionDisconnectEvent` can fire repeatedly, causing double-releases or duplicate notifications.
8. **Assuming the broker relay automatically reconnects browsers.** Clients must reconnect and re-subscribe themselves.
9. **Setting heartbeats longer than or close to proxy idle timeouts.** Likely to cause periodic disconnects even with healthy apps; measure jitter and intermediate timeouts.
10. **Using a single-node simple broker while expecting subscriptions to be shared across nodes.** To scale across multiple instances, design an external broker and proper routing.
11. **Neglecting user destinations and permissions.** Message limits protect resources; they do not replace authentication/authorization at handshake, inbound channel, and destination layers.
12. **Assuming identical close/ERROR codes across every browser.** Limits may be enforced by the container before Spring; log per layer and build fault-tolerant clients.

## 10. Self-Check Questions

1. **A STOMP SEND has a 100 KiB body split across multiple 8 KiB WebSocket messages, while `setMessageSizeLimit(64 KiB)` is set—what happens?** → Spring checks the size of the reassembled STOMP message; splitting frames does not bypass the limit.
2. **On the same session, thread A is sending slowly while thread B emits more messages—what happens?** → B should not write concurrently to the socket; messages are buffered/serialized and may cause the session to hit send buffer/time limits.
3. **Does `sendTimeLimit(5_000)` guarantee a blocking send is aborted after exactly 5 seconds?** → No; limit checks depend on subsequent send/close events and the transport. Use monitoring/timeouts at other layers if needed.
4. **Why doesn't a network drop always produce an immediate DISCONNECT?** → The client had no chance to send a frame; the server must rely on I/O errors, idle timeouts, or heartbeats to detect it.
5. **Why does `SessionDisconnectEvent` need idempotency?** → The event can be published more than once; cleanup must be safe if invoked repeatedly.
6. **Does enabling `setPreservePublishOrder(true)` guarantee global ordering?** → No; it applies primarily to publish ordering within a single client session.
7. **If a mobile client reconnects, do its old subscriptions automatically reappear?** → No; the client must re-subscribe on the new session and sync missed messages if business rules require it.
8. **Does a 1 KiB inbound limit ensure clients never receive a MESSAGE larger than 1 KiB?** → No; the inbound STOMP message limit is not an outbound maximum. Apply separate payload policies if needed.

## 11. Official Documentation

- Spring Framework — STOMP performance: https://docs.spring.io/spring-framework/reference/web/websocket/stomp/configuration-performance.html
- Spring Framework — Message ordering: https://docs.spring.io/spring-framework/reference/web/websocket/stomp/ordered-messages.html
- Spring Framework — STOMP Simple Broker and heartbeats: https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-simple-broker.html
- Spring Framework — STOMP application-context events: https://docs.spring.io/spring-framework/reference/web/websocket/stomp/application-context-events.html
- Spring Framework — STOMP monitoring/statistics: https://docs.spring.io/spring-framework/reference/web/websocket/stomp/stats.html
- Spring Framework — WebSocket server container config: https://docs.spring.io/spring-framework/reference/web/websocket/server.html
- Spring Framework 6.1 Javadoc — `WebSocketTransportRegistration`: https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/web/socket/config/annotation/WebSocketTransportRegistration.html
- Spring Framework 6.1 Javadoc — `ConcurrentWebSocketSessionDecorator`: https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/web/socket/handler/ConcurrentWebSocketSessionDecorator.html
