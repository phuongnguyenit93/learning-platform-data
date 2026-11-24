# Comparing Polling, Server-Sent Events (SSE), and WebSocket: Choosing an Update Mechanism in Spring

## 1. The Problem to Solve

A web page often needs to know when **data on the server has just changed**: an order changes status, a dashboard has new metrics, the system emits notifications, a job reports progress, or new chat messages arrive. There are three common mechanisms:

- **Polling:** the client proactively sends repeated HTTP requests to ask whether new information is available.
- **Server-Sent Events (SSE):** the client opens a long-lived HTTP connection; the server continuously pushes text events from server to client when changes occur.
- **WebSocket:** the client and server maintain a bidirectional connection; either side can send messages at any time. In Spring, **STOMP over WebSocket** is commonly used to add concepts such as destinations, subscriptions, and message routing.

No single mechanism is optimal for every scenario. The right decision depends on **data direction, acceptable latency, connection count, request load, network/proxy characteristics, security, resilience, and scaling requirements**.

For example, an application displaying task processing status every 10 seconds does not necessarily need WebSocket. Conversely, a chat room with heavy bidirectional message traffic should not default to 1-second polling just because it is easy to implement.

## 2. How Do the Three Mechanisms Work?

### 2.1. Polling (short polling)

The client performs an HTTP GET periodically, for example every 5 seconds:

~~~text
Browser                         Server
   | --- GET /api/status ------> |
   | <------ 200 current -------- |
   |       (wait 5 seconds)      |
   | --- GET /api/status ------> |
   | <------ 200 current -------- |
   |       (wait 5 seconds)      |
   | --- GET /api/status ------> |
   | <------ 200 changed -------- |
~~~

Pros: compatible with traditional HTTP, passes cleanly through familiar auth/proxy/load balancer systems, easy to cache and monitor, and does not require holding a connection per client for the duration of a session. Cons: requests may return unchanged data; higher frequency increases HTTP traffic, while lower frequency means users see stale updates.

If the polling interval is `T` seconds, the delay from when the server updates data until the client sees it can approach `T` seconds; assuming change timestamps are uniformly distributed relative to the polling schedule, the average is roughly `T/2`, **excluding network/server latency**. With `N` clients all polling every `T` seconds, the request rate is roughly `N/T` requests/second. For instance, 10,000 clients polling every 10 seconds ≈ 1,000 requests/second, even when the data has not changed.

**Long polling** is a variant: the server holds the request open until a change occurs or a timeout expires; the client then calls again. It reduces empty responses when events are infrequent, but is more complex than short polling in terms of timeouts, cancellation, holding pending requests, and handling bursts. Long polling **is not SSE**: once a response is sent, the HTTP request ends; SSE can push multiple events over a single open response.

When using polling, you can optimize with `ETag` + `If-None-Match`, `Last-Modified` + `If-Modified-Since`, or by returning a version/timestamp; if unchanged, return `304 Not Modified` to save response body bandwidth. A `304` still consumes an HTTP request round-trip and request handling.

### 2.2. SSE (Server-Sent Events)

The browser uses `EventSource` to open an HTTP GET with `Accept: text/event-stream`. The server keeps the response open and sends properly formatted SSE text lines, separating events with blank lines:

~~~text
Browser                         Server
   | --- GET /api/events -----> |
   | <---- HTTP 200 ------------ |
   |      Content-Type: text/event-stream
   | <---- id: 41 -------------- |
   |       event: update        |
   |       data: {"count":41}   |
   |                            |
   | <---- id: 42 -------------- |
   |       event: update        |
   |       data: {"count":42}   |
   |     (same HTTP response)   |
~~~

Valid SSE format example:

~~~text
id: 42
event: update
data: {"count":42}

: heartbeat

retry: 3000

~~~

Here `data:` holds the payload (which may span multiple lines), `event:` is the event name, `id:` is the ID remembered by the browser, `retry:` suggests the reconnection delay in milliseconds, and lines starting with `:` are comments (often used as heartbeats). An event is terminated by a **blank line**.

Browser-standard SSE is **server → client**; when the client wants to send a command, it still uses a separate HTTP POST/fetch request. `EventSource` automatically reconnects after a connection drop. If the server previously sent `id:`, the browser can send `Last-Event-ID` upon reconnecting, **but the server must maintain its own event log/cursor and replay logic to recover missed events**. Simply adding `id` to the response does not guarantee replay.

SSE uses plain HTTP and is simple to integrate into existing web applications. However, long-lived responses require handling timeouts, proxy buffering, heartbeats, connection/stream limits, and cleanup when clients leave. Over HTTP/1.1, browsers typically limit concurrent connections per origin (commonly around 6); HTTP/2 has different stream limits and requires practical configuration.

### 2.3. WebSocket and STOMP

WebSocket opens a full-duplex communication session. After an appropriate HTTP handshake, the same connection allows sending messages **bidirectionally** without requiring each message to be a separate HTTP request/response.

~~~text
Browser                      WebSocket server
   | --- HTTP handshake -------> |
   | <--- switched protocols --- |
   | ------ "join room" -------> |
   | <----- "member joined" ---- |
   | <----- "new message" ------ |
   | ------ "send text" -------> |
   | <----- "new message" ------ |
   |   (long-lived connection)   |
~~~

**Raw WebSocket** is a frame transport protocol; it **does not natively provide** a topic/subscription model, persistence, queues, replay, or per-message-type authorization. `STOMP` is an application-level messaging protocol with frames such as `CONNECT`, `SUBSCRIBE`, `SEND`, `MESSAGE`, `DISCONNECT`; it can run **over WebSocket** and is supported in Spring via `@EnableWebSocketMessageBroker`, `@MessageMapping`, and `SimpMessagingTemplate`.

An example STOMP path in Spring:

~~~text
Client connects ws://host/ws
  --> CONNECT (STOMP)
  --> SUBSCRIBE destination:/topic/orders
Client sends SEND destination:/app/command
  --> Spring @MessageMapping("/command")
  --> server sends to /topic/orders
  --> broker forwards MESSAGE to subscribers
~~~

**Note:** `new WebSocket("/ws")` connecting via raw WebSocket does not automatically create or process STOMP frames. To talk to a STOMP endpoint, the browser must use a STOMP client (such as `@stomp/stompjs`) or implement the STOMP protocol itself. Conversely, a raw `TextWebSocketHandler` endpoint does not understand STOMP out of the box.

WebSocket does not automatically reconnect or replay at the browser WebSocket standard level; you need a client library or custom code to handle reconnection, heartbeats, state resumption, and duplicate/missing events.

## 3. Practical Comparison Table

| Criterion | Polling | SSE | WebSocket / STOMP |
| --- | --- | --- | --- |
| Update direction | Client asks, server answers | Server → client over one HTTP response; client sends commands via separate HTTP | Bidirectional full-duplex |
| Connection | Repeated HTTP requests | Long-lived HTTP streaming | Long-lived WebSocket connection |
| Latency on new data | Depends on polling interval | Usually sent immediately when an event occurs | Usually sent immediately when a message arrives |
| Traffic when data rarely changes | Many empty requests | Small if heartbeat is well-tuned | Small if heartbeat is well-tuned |
| Browser integration | `fetch`, HTTP libraries | `EventSource` | `WebSocket`; STOMP requires an extra client |
| Browser-to-server sending | Normal HTTP GET/POST | Separate HTTP request | Directly over WebSocket or STOMP `SEND` |
| Automatic reconnect | Polling schedule managed by application | `EventSource` reconnects automatically | Must be managed by application/library |
| Replaying missed updates | GET current snapshot or version again | Uses `id`/`Last-Event-ID` **if backend supports replay** | Requires a custom replay mechanism |
| Proxy/load balancer | Usually simplest | Needs streaming support, no buffering, suitable timeouts | Needs WebSocket upgrade/tunnel support and idle timeouts |
| Binary data | Supported by HTTP | SSE is UTF-8 text | WebSocket has text and binary frames; STOMP typically uses messaging payloads |
| Scaling | Stateless HTTP scales more easily, but costs requests | Scales long-lived streams and fan-out | Scales connections, subscriptions, brokers, and fan-out |
| Best suited for | Infrequently changing data, delay acceptable | One-way notifications/live feeds | Chat, bidirectional interaction, real-time collaboration |

This table describes baseline characteristics only. **Do not claim that WebSocket is always faster than SSE**: when both maintain an established connection and only the server pushes updates, the latency difference may be smaller than the design, operational, and recovery overhead. Actual performance must be measured with the real payload, user count, network, and server.

## 4. Scenario-Based Decision Rules

1. **Reports, job statuses, dashboards updating every 10–60 seconds:** start with polling. If changes are very sparse, increase the interval, use version/ETag, and pause when the tab is hidden if appropriate.
2. **Live stats, news feeds, progress logs, server-to-browser notifications:** consider SSE first; the browser receives one-way events and still uses HTTP POST to submit actions.
3. **Chat, multiplayer, collaborative editing, continuous low-latency bidirectional interaction:** consider WebSocket. For publish/subscribe channels and routing, STOMP helps structure messages by destination.
4. **Multiple server instances requiring system-wide broadcast:** both SSE and WebSocket need a shared pub/sub architecture or event bus; the STOMP simple broker lives only in each instance's memory and **is not sufficient for clustering**. Choose a broker relay or an appropriate fan-out architecture.
5. **Strict guarantees against message loss, ordering, and resumability:** define dedicated delivery semantics (event IDs, durable log, cursor, ACK, deduplication). No transport mechanism by itself replaces a durable queue or database.
6. **Clients may stay offline for long periods:** on return, synchronize snapshot and delta from a durable source; keeping a WebSocket open does not replace push notifications when the browser/app is inactive.

### A Decision Diagram

~~~text
Need data updates in the browser?
          |
          v
Does the client need continuous, low-latency two-way messages?
       /                              \
     Yes                              No
     |                                 |
  WebSocket                  Acceptable delay of seconds/minutes?
     |                              /              \
  Need topics/rooms?              Yes              No
   /       \                      |                |
  Yes       No                 Polling             SSE
   |        |               (ETag/version)   (+replay if needed)
 STOMP   Raw WebSocket
~~~

Do not choose based on the buzzword "real-time". Lock down concrete SLOs such as `p95 update latency < 2s`, concurrent client count, event rate per client, payload per event, loss tolerance, retry behavior, and infrastructure cost before running benchmarks.

## 5. Spring Framework: Which API to Use?

### Polling in Spring MVC

A REST endpoint returning the current snapshot:

~~~java
@RestController
@RequestMapping("/api")
class StatusController {
    @GetMapping("/status")
    Status status() {
        return statusService.current();
    }
}
~~~

`Status` and `statusService` are application components you need to provide; the snippet above illustrates the endpoint design. The client calls `GET /api/status` periodically. The controller does not need to maintain long-lived connections or subscriptions between calls.

### SSE in Spring MVC and WebFlux

In **Spring MVC**, use `SseEmitter`:

~~~java
@GetMapping(path = "/events",
            produces = MediaType.TEXT_EVENT_STREAM_VALUE)
public SseEmitter events() {
    SseEmitter emitter = new SseEmitter(60_000L);
    registerAndSendUpdates(emitter);
    return emitter;
}
~~~

`registerAndSendUpdates` is custom logic; on client disconnect/error/timeout you must remove the emitter from the registry and release resources. Spring MVC uses Servlet async to keep the response open; writing SSE responses in the Servlet stack **can still use blocking threads**. Do not push messages directly from a reactive event loop into a blocking API without an appropriate handling strategy.

In **Spring WebFlux**, you can return `Flux<ServerSentEvent<T>>`:

~~~java
@GetMapping(path = "/events",
            produces = MediaType.TEXT_EVENT_STREAM_VALUE)
public Flux<ServerSentEvent<Update>> events() {
    return updatesFlux.map(update ->
            ServerSentEvent.<Update>builder()
                    .id(Long.toString(update.sequence()))
                    .event("update")
                    .data(update)
                    .build());
}
~~~

The WebFlux snippet above is illustrative; `updatesFlux` must be a real publisher managed by the system. You need to design multi-subscriber event emission, backpressure, and slow-subscriber handling. Do not take a single-subscriber `Flux` and assume it automatically broadcasts.

### WebSocket STOMP in Spring

Create a message broker configuration:

~~~java
@Configuration
@EnableWebSocketMessageBroker
class SocketConfig implements WebSocketMessageBrokerConfigurer {
    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/ws");
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.setApplicationDestinationPrefixes("/app");
        registry.enableSimpleBroker("/topic");
    }
}
~~~

`/ws` is the **WebSocket handshake path**, `/app` is the prefix for routing client messages to Spring `@MessageMapping` methods, and `/topic` is the prefix handled by the broker to forward messages to subscribers. The name `/topic` is a convention in the simple broker, not a durability guarantee.

Messages sent to `/app/command` can be handled with:

~~~java
@Controller
class CommandHandler {
    private final SimpMessagingTemplate template;

    CommandHandler(SimpMessagingTemplate template) {
        this.template = template;
    }

    @MessageMapping("/command")
    void command(Command cmd) {
        template.convertAndSend("/topic/updates", cmd);
    }
}
~~~

This is an illustrative snippet; a `Command` model is required. For production, **authenticate/authorize by user, destination, and action** before forwarding any client content to a topic. Do not rely on an unguessable topic name as a security boundary.

## 6. Complete Java 17+ Demo: One Server for All Three Models

The example below uses **Spring Boot 3.x running on Spring MVC**. A scheduled task changes state every 5 seconds. Clients can:

- Poll `GET /api/status` to retrieve the latest snapshot.
- Subscribe to SSE `GET /api/events` to receive events automatically.
- Use STOMP over WebSocket `/ws`, subscribe to `/topic/updates`, and send commands to `/app/command`.

The examples share a single in-memory state and are intended for **single-instance learning**, without persistence, authorization, backplane, replay, or load balancing implemented yet.

### 6.1. `pom.xml`

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
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
    <artifactId>realtime-demo</artifactId>
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

The WebSocket STOMP starter integrates with MVC; this example **does not require** `spring-boot-starter-webflux`. `SseEmitter` belongs to Spring MVC. Place the source file at `src/main/java/demo/RealtimeDemoApplication.java`.

### 6.2. `src/main/java/demo/RealtimeDemoApplication.java`

~~~java
package demo;

import java.io.IOException;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.atomic.AtomicLong;
import java.util.concurrent.atomic.AtomicReference;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.MediaType;
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.simp.SimpMessagingTemplate;
import org.springframework.scheduling.annotation.EnableScheduling;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;
import org.springframework.web.socket.config.annotation.EnableWebSocketMessageBroker;
import org.springframework.web.socket.config.annotation.StompEndpointRegistry;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;
import org.springframework.messaging.simp.config.MessageBrokerRegistry;

@SpringBootApplication
@EnableScheduling
public class RealtimeDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(RealtimeDemoApplication.class, args);
    }
}

record Update(long sequence, String state) {}
record Command(String text) {}

@Component
class UpdatePublisher {
    private final AtomicLong counter = new AtomicLong();
    private final AtomicReference<Update> current =
            new AtomicReference<>(new Update(0, "READY"));
    private final CopyOnWriteArrayList<SseEmitter> emitters =
            new CopyOnWriteArrayList<>();
    private final SimpMessagingTemplate broker;

    UpdatePublisher(SimpMessagingTemplate broker) {
        this.broker = broker;
    }

    Update current() {
        return current.get();
    }

    SseEmitter openStream() {
        // SSE connection times out after 60 seconds;
        // Browser EventSource can reopen it.
        SseEmitter emitter = new SseEmitter(60_000L);
        emitters.add(emitter);
        emitter.onCompletion(() -> emitters.remove(emitter));
        emitter.onTimeout(() -> emitters.remove(emitter));
        emitter.onError(error -> emitters.remove(emitter));

        send(emitter, current());
        return emitter;
    }

    @Scheduled(initialDelay = 5_000, fixedRate = 5_000)
    public void tick() {
        publish("tick");
    }

    void publish(String state) {
        Update update = new Update(counter.incrementAndGet(), state);
        current.set(update);

        for (SseEmitter emitter : emitters) {
            send(emitter, update);
        }

        // Broadcast to STOMP clients subscribed to /topic/updates.
        broker.convertAndSend("/topic/updates", update);
    }

    private void send(SseEmitter emitter, Update update) {
        try {
            emitter.send(SseEmitter.event()
                    .id(Long.toString(update.sequence()))
                    .name("update")
                    .data(update, MediaType.APPLICATION_JSON));
        } catch (IOException | IllegalStateException failure) {
            emitters.remove(emitter);
            emitter.completeWithError(failure);
        }
    }
}

@RestController
class UpdatesController {
    private final UpdatePublisher publisher;

    UpdatesController(UpdatePublisher publisher) {
        this.publisher = publisher;
    }

    @GetMapping("/api/status")
    Update status() {
        return publisher.current();
    }

    @GetMapping(path = "/api/events",
            produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    SseEmitter stream() {
        return publisher.openStream();
    }

    @MessageMapping("/command")
    void command(Command command) {
        publisher.publish("client:" + command.text());
    }
}

@Configuration
@EnableWebSocketMessageBroker
class WebSocketConfig implements WebSocketMessageBrokerConfigurer {
    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/ws");
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.setApplicationDestinationPrefixes("/app");
        registry.enableSimpleBroker("/topic");
    }
}
~~~

Key points explained:

- `AtomicReference<Update>` stores the latest snapshot for polling; `AtomicLong` generates sequence IDs within a single process.
- `CopyOnWriteArrayList` is only sensible for demos or a small number of listeners. With many connections, array copying on add/remove, sequential broadcasting, and blocking writes can bottleneck; consider a dedicated fan-out system and slow-client controls.
- `@Scheduled` emits an update every 5 seconds. The SSE browser client reconnects after timeout and receives the current snapshot.
- Both SSE and STOMP receive records from `publish(...)`; regular HTTP requests read the snapshot from `current()`.
- `SseEmitter.send(...)` can fail when a client disconnects; completion/error/timeout callbacks remove the emitter. In real systems, avoid concurrent writes and configure write timeouts, heartbeats, and backpressure policies.
- `sequence` increments to make gaps easy to detect. The demo **does not store history**, so it cannot use `Last-Event-ID` to replay missed sequences yet.
- `@MessageMapping("/command")` illustrates a **client → server** path available only on the STOMP channel. In production, validate payload size/content and check command permissions.

### 6.3. Running and Testing Polling

Using JDK 17+ and Maven in the project directory:

~~~bash
mvn spring-boot:run
~~~

In another terminal:

~~~bash
curl -s http://localhost:8080/api/status
~~~

Right after the server starts, **before the first tick**, the expected response is:

~~~json
{"sequence":0,"state":"READY"}
~~~

After several ticks, `sequence` and `state` change; a single fixed output cannot be assumed once the server has been running. To poll continuously from browser JavaScript:

~~~javascript
let active = true;

async function poll() {
    if (!active) return;
    try {
        const response = await fetch("/api/status");
        if (!response.ok) throw new Error("HTTP " + response.status);
        const update = await response.json();
        console.log("poll", update);
    } catch (error) {
        console.warn("poll failed", error);
    } finally {
        // setTimeout after the request finishes prevents overlapping requests
        // if the server responds slower than the polling interval.
        if (active) setTimeout(poll, 5000);
    }
}
poll();
// When leaving the page/no longer needed: active = false;
~~~

For browser pages served from the **same origin** as the application, the relative URL `/api/status` works directly. If JavaScript runs on a different origin, use an absolute URL and configure CORS/auth accordingly; do not open CORS permissively in real systems.

### 6.4. Testing SSE

From the command line:

~~~bash
curl -N http://localhost:8080/api/events
~~~

`-N`/`--no-buffer` lets you observe streaming output immediately. An initial snapshot and subsequent updates look like:

~~~text
id:0
event:update
data:{"sequence":0,"state":"READY"}

id:1
event:update
data:{"sequence":1,"state":"tick"}

~~~

Whitespace and serialization formatting by the framework may differ slightly; the important fields are `id`, `event`, `data`, and the blank line terminating each event. If you connect after a tick, the first event may not be sequence 0.

Browser usage:

~~~javascript
const stream = new EventSource("/api/events");
stream.addEventListener("update", event => {
    const update = JSON.parse(event.data);
    console.log("SSE", update.sequence, update.state);
});
stream.onerror = () => console.warn("SSE disconnected; browser may retry");

// When updates are no longer needed:
// stream.close();
~~~

The browser automatically reconnects when the stream errors or closes in a reconnectable way. Do not assume SSE `onerror` always means permanent disconnection; inspect `readyState`. To guarantee zero lost events, store an event log and handle the `Last-Event-ID` header when the client reconnects. The demo only sends the **latest snapshot** and does not use that header.

### 6.5. Testing STOMP over WebSocket

Install the frontend library `@stomp/stompjs` (for example `npm install @stomp/stompjs` in a bundled JavaScript app), then use:

~~~javascript
import { Client } from "@stomp/stompjs";

const scheme = location.protocol === "https:" ? "wss" : "ws";
const client = new Client({
    brokerURL: scheme + "://" + location.host + "/ws",
    reconnectDelay: 3000,
    onConnect: () => {
        client.subscribe("/topic/updates", message => {
            const update = JSON.parse(message.body);
            console.log("STOMP", update.sequence, update.state);
        });

        client.publish({
            destination: "/app/command",
            body: JSON.stringify({ text: "refresh" })
        });
    },
    onStompError: frame => {
        console.error("Broker error", frame.headers["message"]);
    }
});
client.activate();

// When leaving the screen: await client.deactivate();
~~~

Once connected and subscribed, the client begins receiving `tick` updates. Sending `SEND` to `/app/command` causes the server to broadcast an update with `state="client:refresh"` to both the SSE stream and the STOMP topic. If a client sends `SEND` before subscribing, it may miss the first message; the example subscribes first and then publishes.

**Do not send STOMP SEND over `new WebSocket(...)` by writing plain JSON only:** STOMP requires protocol-compliant frames. If you need raw WebSocket for JSON payloads, create a separate raw handler using the Spring WebSocket API; that is a different design.

## 7. Reconnection, Data Consistency, and Missed Events

A real update system must define what happens when the browser sleeps, the network drops, or the server restarts.

### Polling: version-based synchronization

Polling typically fetches the **current snapshot**. When a new GET succeeds, the client knows the current state but not every intermediate transition. If history is needed, the endpoint should support `?since=<cursor>` or provide a separate event history call. The same data may be received multiple times; the client can compare version/ETag to avoid redundant rendering.

### SSE: `Last-Event-ID` and replay

The browser records `id` and typically sends `Last-Event-ID` on automatic reconnection. The server needs to:

1. Persist events with consistent IDs/offsets to appropriate storage or an event log.
2. On reconnect, read the cursor sent by the client and replay events after that cursor.
3. Deduplicate on the client (idempotent updates) because disconnect/ack boundaries can cause redelivery.
4. Detect cursors that have expired due to retention limits, and instruct the client to reload a full snapshot.
5. Preserve ordering between **replay** and **live** events so nothing is lost during the transition.

In Spring MVC, you can read `@RequestHeader(value = "Last-Event-ID", required = false) String lastId` when opening the emitter; the demo lacks an event store and therefore does not claim "exactly once" delivery semantics.

### WebSocket/STOMP: reconnect does not equal replay

Native WebSocket does not reconnect automatically; `@stomp/stompjs` supports `reconnectDelay` and resubscribing inside `onConnect`. However, messages sent while offline do not magically appear after reconnecting without a durable broker queue/replay or a delta API. Do not attribute the persistence, acknowledgement, and transaction capabilities of a **full STOMP broker** to the built-in simple broker.

For a reliable experience, you can use a common pattern: after reconnecting, the client calls HTTP to fetch the current snapshot and version, then subscribes to the stream or applies deltas; the server emits sequence numbers to detect gaps. The subscribe/snapshot ordering must handle races rather than naively doing "GET then subscribe", since events can occur between the two steps.

## 8. Scaling, Resources, and Proxies

### Polling

The bottleneck is **request rate**, not necessarily open sockets. Calculate `N / interval`, add jitter so tens of thousands of browsers do not wake up on the exact same second, and use backoff on server errors. Optimize caching, ETags, and poll only when the tab is visible if business rules allow. Polling every 1 second for hundreds of thousands of clients can be more expensive than long-lived streams.

### SSE

Each stream holds connection resources and registration state; reverse proxies may buffer responses unless configured for streaming. You need timeouts, heartbeat comments, bounded event sizes, and disconnect cleanup. Spring MVC `SseEmitter` can use blocking write threads; large broadcasts or very slow clients require an isolated fan-out mechanism. When scaling across multiple instances, events must be routed to the exact instance holding each emitter (typically via a shared event bus) or through a dedicated stream gateway layer.

### WebSocket/STOMP

Each connection holds a long-lived session with idle timeouts, heartbeats, message limits, and subscriber limits. Metrics to monitor include active sessions, outbound channel queues, slow consumers, memory per connection, broker health, and reconnection times. Spring's **simple broker** is in-memory, supports a subset of STOMP, and is unsuitable for clustering. When multiple nodes serve traffic, use a STOMP broker relay to an external broker (such as RabbitMQ or ActiveMQ with STOMP support), or another pub/sub architecture designed for the job.

### Proxies, load balancers, and TLS

- Use HTTPS/WSS on the Internet and configure certificates, origins, load balancers, and idle timeouts properly.
- For SSE, disable or tune proxy buffering on streaming routes; send heartbeats to detect dropped connections.
- For WebSocket, proxies must permit the appropriate handshake/tunnel and sufficiently long timeouts; session affinity or a shared broker may be needed depending on the design.
- For polling, keep the API stateless where possible; add rate limiting and conditional requests.
- For all three, **TLS, authentication, authorization, and data protection** are separate requirements that are not satisfied automatically by choosing a transport.

## 9. Security and Input Handling

- **Polling/REST:** protect endpoints with Spring Security like standard HTTP APIs; enforce user/tenant/resource authorization, rate limits, and cache headers to prevent data leaks.
- **SSE:** HTTP requests use same-origin cookies/sessions under browser policy; standard `EventSource` does not allow setting arbitrary custom Authorization headers like `fetch`. When using cookies, enforce CSRF protection for state-changing operations (separate POST commands), SameSite, CORS/credentials, and never embed sensitive tokens in query strings or logs.
- **WebSocket:** validate Origin and authenticate at handshake/messaging as appropriate; origin checks **do not replace** authentication/authorization. With STOMP, enforce controls on CONNECT, SUBSCRIBE, SEND, and permissions per destination and user/tenant. Spring Security provides message authorization; CONNECT/CSRF policies must be configured properly for browser apps.
- **Payloads:** enforce size limits, validate JSON/commands, and use `textContent` rather than inserting untrusted data directly via `innerHTML`. Do not assume every subscriber on a topic is authorized to read sensitive data.
- **Replay:** cursors and event history must be filtered by user permissions; prevent clients from setting a cursor to read another tenant's events.

Especially in multi-tenant systems, a global topic like `/topic/orders` can accidentally leak events to the wrong audience if the application lacks message authorization or user-scoped routing. Read permissions must be checked at the **emission source, destination, and history-read path**.

## 10. Common Misconceptions and Implementation Pitfalls

1. **"To be real-time, you must use WebSocket."** If only the server notifies the browser, SSE is simpler and has built-in reconnection; if updates are rare and delay is acceptable, polling is even easier.
2. **"SSE with `id` never loses messages."** Only true if the backend implements durable replay and handles races/cursors.
3. **"WebSocket manages topics and replay by itself."** Raw WebSocket provides no broker; the STOMP simple broker does not provide durable messaging or clustering either.
4. **"If it works on one server, multiple replicas will broadcast fine too."** SSE listeners and the simple STOMP broker hold local state; multiple instances require a backplane or external broker.
5. **"The faster the polling, the better."** Small intervals inflate request rates and peak load; choose according to business latency needs and add jitter/backoff.
6. **"SSE does not need heartbeats."** Silent connections can be closed by proxies or networks; appropriate keepalives help detect drops.
7. **"If the socket is open, the client is healthy."** A client can be slow and outbound buffers can grow; set limits and collect metrics.
8. **"Need duplex? Just use two SSE connections."** SSE is one-way; you can send upstream via POST, but for continuous two-way interaction, WebSocket/STOMP is usually more natural.
9. **"Adding `withSockJS()` makes WebSocket faster."** SockJS is a fallback transport/compatibility layer, not STOMP and not a default speed optimization. Use it when client/proxy environments require fallback.
10. **"Returning `Flux` from an MVC controller is completely non-blocking."** Servlet MVC still has its own HTTP write mechanics and executor; understand the threading model of your stack.

## 11. Implementation and Testing Checklist

Before releasing, clearly specify:

- **Update flow:** server → client or bidirectional? One-to-one, group, or system-wide?
- **Latency:** p95/p99 targets and peak update rate per client multiplier?
- **Data semantics:** is the latest snapshot enough, or must every event be replayed? Are ordering, deduplication, and idempotency required?
- **Transport:** HTTP polling, SSE stream, or WebSocket/STOMP; how specifically do proxies/load balancers support it?
- **Recovery:** reconnect, backoff, heartbeat, resubscribe, snapshot/delta, retention limits?
- **Capacity:** requests/s; active SSE/WebSocket connections; memory, threads, executors, pending queues, and slow consumers?
- **Security:** auth, origin/CORS/CSRF, topic subscription permissions, tenant isolation, input validation?
- **Observability:** p95 update lag, server→client fan-out lag, reconnect count, disconnect errors, dropped/duplicated events, broker queue size?
- **Load testing:** simulate real clients, slow networks, proxies, restarts, multiple instances, and connection drops; do not benchmark only localhost with one client.

**Pragmatic selection:** start with polling when delay is acceptable and frequency is low; choose SSE when the server mainly pushes notifications; use WebSocket/STOMP when bidirectional communication or complex subscription models are truly needed. Separate the **transport** problem from **reliable replay, security, and scaling**.

## 12. References

- Spring Framework — Asynchronous Requests, SSE/`SseEmitter` (MVC): https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-async.html
- Spring Framework — Enable STOMP: https://docs.spring.io/spring-framework/reference/web/websocket/stomp/enable.html
- Spring Framework — Message Flow: https://docs.spring.io/spring-framework/reference/web/websocket/stomp/message-flow.html
- Spring Framework — Simple Broker: https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-simple-broker.html
- Spring Framework — External Broker: https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-broker-relay.html
- Spring Framework — WebSocket transport configuration: https://docs.spring.io/spring-framework/reference/web/websocket/stomp/server-config.html
- MDN — Using server-sent events: https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events/Using_server-sent_events
- MDN — WebSocket API: https://developer.mozilla.org/en-US/docs/Web/API/WebSocket
