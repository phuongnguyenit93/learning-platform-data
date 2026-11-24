# Closing SSE, WebSocket, and Long-Lived Response Streams During Spring Boot Graceful Shutdown

> **Module:** Spring Boot - web-runtime · **Group:** Graceful Shutdown. This lesson guides properly closing the lifecycles of **Server-Sent Events (SSE)**, **WebSocket (raw and STOMP)**, **StreamingResponseBody**, `ResponseBodyEmitter`/`DeferredResult`, and **WebFlux/reactive** streams during deployments, rolling restarts, autoscaling, pod termination, or service shutdown. The goal is not merely for the JVM to exit: you must block new connections, tell clients how to redirect or reconnect, release subscriptions/tasks/buffers, avoid letting the process wait forever, and avoid losing unrecoverable business events. Examples use **Java 17+**, **Spring Boot 4.1.2**, Spring MVC/Tomcat, Actuator readiness, `SseEmitter`, raw WebSocket, along with tests using cURL, browsers, SIGTERM, and Kubernetes.

## 1. Learning objectives

After this lesson, you can:

1. Distinguish **embedded HTTP server graceful shutdown**, **application-driven session draining**, **protocol close handshakes**, and **process termination**; understand why they do not automatically replace one another.
2. Describe shutdown states: **RUNNING → DRAINING → CLOSING → TERMINATED**, the sequence of updating readiness, blocking new streams, notifying clients, stopping producers, waiting for valid work, and closing transports.
3. Use `spring.lifecycle.timeout-per-shutdown-phase`, `server.shutdown`, `ReadinessState.REFUSING_TRAFFIC`, readiness probes, and Kubernetes `preStop`/`terminationGracePeriodSeconds`.
4. Manage the `SseEmitter` lifecycle: `onCompletion`/`onTimeout`/`onError`, sending a `server-draining` event when possible, calling `complete()` in the right cases, heartbeats to detect disconnected clients, and idempotent registry cleanup.
5. Close raw WebSockets via `WebSocketSession.close(CloseStatus.GOING_AWAY)` (**close code 1001**) and release session state; distinguish close frames, network errors, and the meaning of `SessionDisconnectEvent` in STOMP.
6. Stop `StreamingResponseBody`/chunked responses via cancellation tokens, bounded executors, and completion/cleanup; understand limitations after HTTP responses are committed.
7. In WebFlux, bind `Flux`/`Mono` lifecycles to cancellation, `doFinally`/`takeUntilOther`/`WebSocketSession.close(...)`, and ensure no hot publishers/connection queues keep the process alive.
8. Build and run a Spring Boot MVC project demonstrating: SSE, WebSocket, streaming responses, internal drain endpoint, readiness, and context-close callbacks.
9. Design client reconnect with backoff+jitter and ID/cursor/Last-Event-ID/replay, avoiding reconnect storms and never promising guaranteed delivery merely from writing a terminal event.
10. Verify real behavior under SIGTERM, slow clients, proxies/LBs, timeouts/force kills, and measure active streams, dropped events, close reasons, and drain duration.

## 2. Why do long-lived connections make graceful shutdown harder than standard REST?

A short REST request can finish in tens of milliseconds. Meanwhile:

- **SSE** keeps a `text/event-stream` response open for minutes or hours for continuous delivery.
- **WebSocket** upgrades HTTP into a long-lived bidirectional channel; normally there is no HTTP response ending per message.
- **STOMP over WebSocket** also involves brokers, subscriptions, queues, heartbeats, and session lifecycles.
- **StreamingResponseBody**, NDJSON, file exports, gRPC streaming, or reactive `Flux` can write bytes over a very long interval.
- Streaming output may experience **backpressure** from a slow client or proxy, so it cannot be considered complete when the controller returns.

~~~text
Load balancer / Kubernetes Service
             |
        Spring Boot pod A
             |
       +-----+-----+--------------------+
       |           |                    |
     REST         SSE                 WebSocket
     40 ms     2 hrs open             1 hr open
       |           |                    |
       v           v                    v
  usually     needs active           needs close frame
  finishes    notice/complete        + session cleanup
  before grace
             |
    Deployment SIGTERM / drain
             |
             v
  If you only "wait for all requests to finish":
    SSE and streaming may NOT finish before grace expires
~~~

Crucially: **graceful shutdown does not mean “keep every WebSocket/SSE alive until they close on their own”**. A long-lived connection can last indefinitely; server, container, and orchestrator allowances are always finite. When time runs out, the process can be forced to stop before finishing the final message.

### 2.1. Four layers of closing connections

| Layer | Example | What can it guarantee? |
| --- | --- | --- |
| Application admission control | `draining=true`, reject new streams | No new long-lived work created on the old instance |
| Protocol signaling | SSE terminal event, WebSocket close 1001, app control frame | **Attempts** to tell clients to switch to another connection |
| Transport/server lifecycle | Embedded Tomcat/Jetty/Netty graceful stop | Prevents new requests and gives in-flight work time to finish |
| Process/orchestrator | SIGTERM, grace period, SIGKILL | Sets final deadline; does not guarantee the client saw the message |

To shut down properly, **all layers** must coordinate. A `preStop` hook that only closes WebSockets without lowering readiness can let the LB keep sending new clients to the old pod. Conversely, lowering readiness without terminating already-established SSE/WS sessions lets those connections consume resources until the deadline expires.

### 2.2. Closing an HTTP response vs closing a WebSocket

- **Normal HTTP response:** commit headers/status, write body, end body/connection per HTTP semantics.
- **SSE:** a streaming HTTP response; `SseEmitter.complete()` finishes the stream normally via async completion, yet that is not an application-level ACK that the browser processed the final event.
- **WebSocket:** after HTTP 101 upgrade, both sides exchange WebSocket frames; `session.close(status)` sends a close handshake as transport permits. There is no new HTTP 200/503 for an already-upgraded WebSocket session.
- **STOMP:** a subprotocol running **inside** WebSocket; clients can send STOMP `DISCONNECT`, while WebSocket closure or network loss can also trigger Spring's `SessionDisconnectEvent`.
- **NDJSON/file streaming:** clients may receive a partial body and get disconnected; checksums, cursors, Range, or job status are the application protocol's responsibility.

## 3. What does Spring Boot 4.1.2 graceful shutdown actually do?

Per Spring Boot 4.1 documentation, graceful shutdown is **enabled by default** for embedded **Tomcat, Jetty, and Reactor Netty**, for both Servlet and reactive. It runs while closing the application context, at an early stage of stopping `SmartLifecycle` beans. During the grace window, the server tries not to accept **new requests** and lets current requests finish.

Explicitly declare the policy so readers see the timeout:

~~~properties
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=20s
~~~

- `server.shutdown=graceful` here is an explicit declaration; in Boot 4.1 it is already the default.
- `spring.lifecycle.timeout-per-shutdown-phase=20s` is the timeout for **each shutdown phase**, **not** a guarantee that “the entire process always exits in exactly 20 seconds” or “every long-lived connection closes automatically after 20 seconds”.
- `server.shutdown=immediate` can disable graceful shutdown when truly needed, though it should not be used to “fix” a stream that refuses to end.
- Embedded servers may reject new requests at the network layer or behave differently depending on connector and keep-alive; **do not hardcode that every new request must get HTTP 503**.
- Stopping via an IDE **Stop** button may kill the process without proper SIGTERM/graceful behavior; verify with process signals in a production-like environment.

**Limitation:** embedded web server graceful shutdown docs **do not promise that every SSE/WebSocket with custom app producers will stop with the right business semantics**. The server can stop accepting new connections, yet producers, broker subscriptions, raw WebSocket sessions, async tasks, and custom queues still need explicit application lifecycles.

### 3.1. Do not confuse `timeout-per-shutdown-phase` with async request timeout

Different timeouts:

| Timeout | Applies to | Common confusion |
| --- | --- | --- |
| `spring.lifecycle.timeout-per-shutdown-phase` | Stopping lifecycle beans on context close | Not a request idle timeout |
| `spring.mvc.async.request-timeout` | Servlet MVC async request handling | Not the total Kubernetes grace period |
| `new SseEmitter(timeoutMs)` | One specific SSE response | Does not automatically trigger server drain |
| WebSocket idle timeout | Inactive connections | Does not automatically close all sessions on deploy |
| STOMP heartbeat | Detecting an unresponsive peer | Not a delivery ACK or drain |
| Reverse proxy/LB idle timeout | Edge connections | May sever before the app |
| Kubernetes `terminationGracePeriodSeconds` | Total time a pod gets to finish before force kill | Includes the preStop hook |

Ordering and values must be **compatible**. If the app expects a 30-second drain while Kubernetes allows only 10 seconds total, the pod can still be SIGKILLed early. Conversely, setting every timeout to infinity prevents termination from completing.

## 4. Drain-first workflow suited for rolling deployments

Recommended scenario:

~~~text
RUNNING
   |
   | 1. Receive drain request (deploy/preStop/admin)
   v
DRAINING
   |
   +-- readiness = REFUSING_TRAFFIC
   +-- block new SSE/WebSocket/long streams (including admission races)
   +-- stop creating new jobs / publishing into old sessions
   +-- attempt to send terminal control event to SSE/STOMP clients
   +-- WebSocket close 1001 (going away)
   +-- SSE complete(), stream cancellation tokens -> cleanup
   +-- wait for finite in-flight critical work or handoff
   v
CLOSING
   |
   +-- SIGTERM / application context close
   +-- Boot graceful shutdown / lifecycle timeout
   +-- stop background workers / close broker clients/resources
   v
TERMINATED
   |
   +-- remaining work must rely on durable state/replay
~~~

**Exact ordering may differ by platform and version**, yet invariants to maintain include:

1. From the instant `DRAINING` begins, new requests create no new long-lived sessions.
2. Draining can be invoked repeatedly without emitting duplicate terminal events, double-removing, or throwing merely because a session already closed.
3. Every registered session has cleanup callbacks on close/timeout/error.
4. There is a total deadline: if a client reads slowly, do not wait forever on it.
5. After disconnection, clients have a way to recover missed state from durable storage or snapshots.

### 4.1. Readiness vs liveness

- **Readiness:** should the instance receive **new traffic**? When draining, switch to `ReadinessState.REFUSING_TRAFFIC`.
- **Liveness:** is the process working properly or in need of a restart? Do not flip liveness to BROKEN just because it is draining.
- **Startup:** not being ready for traffic yet is normal during boot, not a liveness failure.

Spring Boot provides `AvailabilityChangeEvent.publish(context, ReadinessState.REFUSING_TRAFFIC)`. Kubernetes readiness probes can read `/actuator/health/readiness` when probes are enabled and the endpoint is reachable. However, readiness propagation through Service/LB/Ingress **is not instantaneous**; existing connections typically do not move automatically to another pod when readiness drops.

### 4.2. Race between opening a new stream and draining

A single check:

~~~java
if (!draining) {
    registerLongLivedSession();
}
~~~

still has a race: after this thread reads `draining=false`, another thread flips draining on and snapshots sessions to close, and then the first request registers after the snapshot and can be **missed**.

You need an **admission check both before and after registration**, or a lock/gate mechanism ensuring atomicity. The lab uses `AtomicBoolean`, concurrent sets/maps, and a second check after adding. Production can use a state machine/locks and controlled session ownership.

### 4.3. Drain endpoint must not be a public backdoor

In the lab, `POST /internal/drain` may be called from localhost. Production must secure it via management plane, auth/RBAC, network policies, mTLS, or local sidecar IPC with auditing. If public clients can invoke the drain endpoint, they can continuously disconnect all users (denial of service).

Never use a public GET URL to trigger shutdown side effects. Lowering readiness does not stop the process; a subsequent deploy/orchestrator step is still needed to send SIGTERM properly.

## 5. SSE: proper `SseEmitter` semantics

In Spring MVC, `SseEmitter` extends `ResponseBodyEmitter`. A controller can return the emitter and send events from another thread; the response enters Servlet async mode and stays open.

~~~java
// Fragment in a Spring MVC @RestController.
@GetMapping(path = "/events", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
public SseEmitter events() {
    SseEmitter emitter = new SseEmitter(180_000L);
    // Register in registry, set callbacks, and send from another thread.
    return emitter;
}
~~~

**Callbacks to know:**

- `emitter.onCompletion(Runnable)`: invoked when the async request completes, including certain error/timeout paths; use it to remove the session from the registry.
- `emitter.onTimeout(Runnable)`: handles timeout; do not keep the emitter in the registry.
- `emitter.onError(Consumer<Throwable>)`: handles container/async errors; cleanup and telemetry.
- `emitter.complete()`: application requests normal response completion; Spring finishes async handling/dispatch, **not** a delivery ACK.
- `emitter.completeWithError(Throwable)`: application reports an error to async handling; **do not** call indiscriminately when I/O already reported remote disconnect.

### 5.1. Sending a terminal event before complete

An SSE control event can look like:

~~~text
event: server-draining
data: reconnect
retry: 3000

~~~

This is **valid SSE format** so browsers receive `server-draining` and a retry hint. However:

- If the browser lost connectivity or a proxy buffers, it **might not see the final event**.
- `send(...)` returning **does not mean JS processed it**; TCP/HTTP buffers still sit in between.
- Once HTTP headers/body are committed, the server cannot change the status to HTTP 503 to signal drain.
- To preserve accurate data across disconnects, you need business-event `id:` values, retention, and replay.

Spring MVC sending code:

~~~java
// Fragment, requires an active emitter.
emitter.send(SseEmitter.event()
        .name("server-draining")
        .data("reconnect")
        .reconnectTime(3000L));
emitter.complete();
~~~

### 5.2. Errors when the client disconnects

Spring MVC docs note that the Servlet API **has no reliable immediate callback when a peer disappears**. Usually it is detected only when the **next write** fails with an I/O error. Periodic heartbeat/comment events and cleanup callbacks are therefore needed.

When `SseEmitter.send(...)` throws `IOException` because the remote disconnected, do **not** mechanically call `complete()` or `completeWithError(...)` inside the catch block: the Spring/Servlet container handles `AsyncListener` error notification and completes the error flow. The app should remove the registry entry, log concisely, and avoid double-completion.

~~~java
// Fragment inside the SSE emitting task.
try {
    emitter.send(SseEmitter.event().comment("heartbeat"));
}
catch (IOException disconnected) {
    activeEmitters.remove(emitter);
    // Do not call completeWithError in IOException branch: container handles the error.
}
~~~

Heartbeats help detect disconnects and prevent idle timeouts at some proxies, **do not guarantee the client parsed/business-ACKed events**, and may not suffice if networks/proxies stall. Pick intervals matching proxy policies.

### 5.3. EventSource auto-reconnects unless controlled

Browser `EventSource` automatically reconnects when a stream ends unexpectedly. If a pod is draining and keeps rejecting new connections, clients can cause a **reconnect storm**. Upon receiving `server-draining`, the client can call `EventSource.close()`, wait backoff+jitter, and reconnect via hostname/load balancer to a healthy instance.

If the client **misses** the terminal event, it must handle `onerror`, network status, and staggered retries. Certain HTTP responses such as 204 or error statuses have specific EventSource semantics; do not assume browsers always retry after every HTTP status. Verify browser and EventSource spec behavior.

### 5.4. Last-Event-ID and replay

Example server output:

~~~text
id: 101
event: order-updated
data: {"orderId":"o-1","state":"processing"}

id: 102
event: order-updated
data: {"orderId":"o-1","state":"completed"}

~~~

If the connection drops after event 101, the client can reconnect and send the `Last-Event-ID: 101` header. However, **Spring does not store events automatically** in `SseEmitter`; the server must maintain a durable event log/cursor and handle ordered replay, tenants, authorization, retention, and deduplication.

Do not use millisecond timestamps across multiple pods as contiguous sequences without an ordering contract. If the app only streams the latest state, clients can fetch a REST snapshot after reconnect instead of replaying every transition.

## 6. WebSocket: closing with a frame and cleaning up state

After the HTTP 101 handshake, a WebSocket is an independent connection at the application layer. When the server shuts down, it can call:

~~~java
// Fragment in a raw WebSocket session manager.
if (session.isOpen()) {
    session.close(CloseStatus.GOING_AWAY);
}
~~~

In Spring WebSocket, `CloseStatus.GOING_AWAY` is **1001**, suitable when a server is “going away” for restart/redirect. Code **1000** is normal closure when a task finishes; **1006** is reserved and must never be sent as a close frame. Do not confuse code 1012 from other registries with existing Spring constants without checking your version.

### 6.1. Close handshake is not a delivery guarantee

A normal path:

~~~text
Server wants to stop
   |
   +-- (optional) send app control message "server-draining"
   |
   +-- WebSocket close frame code=1001
   |
   <--- client close frame (if received/responded)
   |
   +-- underlying TCP close / resource cleanup
~~~

The network can break before the client receives the frame. A socket hit by SIGKILL can make the browser report abnormal closure, code **1006** (observed locally), rather than the server explicitly sending 1006.

Do not use a `session.close(...)` call as proof that preceding messages were processed by the browser. For payments/orders, use separate ACKs/replay.

### 6.2. Registry and cleanup

A raw `TextWebSocketHandler` has callbacks:

- `afterConnectionEstablished(WebSocketSession)`: register session, reject by closing if draining.
- `afterConnectionClosed(WebSocketSession, CloseStatus)`: remove session from registry and clean up resources.
- `handleTransportError(WebSocketSession, Throwable)`: log/observe error, clean up.
- `handleTextMessage(...)`: process app messages; do not enqueue new work if draining.

Use a concurrent registry keyed by session ID with **idempotent** removal because error/close/drain can run concurrently. If a session owns background subscriptions, timers, broker consumers, or dedicated queues, cancel those resources; deleting from a Map does not automatically stop an upstream producer.

### 6.3. Do not conflate WebSocket and STOMP DISCONNECT

In STOMP over WebSocket:

- Clients normally send STOMP `DISCONNECT`, optionally using `receipt` if the broker supports it.
- When a WebSocket closes without STOMP DISCONNECT, Spring can still publish `SessionDisconnectEvent`.
- Per documentation, **SessionDisconnectEvent can be published more than once for the same session**; cleanup listeners must be idempotent.
- Spring's simple STOMP broker stores subscriptions in memory; after disconnect they have no automatic durable replay.
- With a broker relay, closing a client WebSocket does not necessarily close external broker/system connections immediately; broker listener lifecycle/ack policies are separate.

To ask STOMP clients to switch pods proactively, you can publish **an app-level message** on a dedicated topic signaling drain, wait briefly, and let the framework close the WebSocket. However, brokers/send buffers can lag; delivery of the drain message to every subscriber before close is not guaranteed.

### 6.4. WebSocket client reconnect

Browser clients typically handle:

~~~javascript
socket.onclose = event => {
  if (event.code === 1001) {
    console.log("Server going away; reconnect with backoff");
  }
  // Every close/error path needs bounded retries and state reconciliation.
};
~~~

Use exponential backoff + jitter, retry limits, auth token refresh if needed, and **re-subscribe** once the new connection opens. Do not hardcode immediate continuous reconnects when 10,000 clients drop sockets together. For STOMP subscriptions, clients must subscribe again after reconnecting per application structure.

## 7. StreamingResponseBody, NDJSON, and long HTTP responses

Spring MVC `StreamingResponseBody` returns a callback writing to `OutputStream` on an async thread; even after the controller returns, the request is not done yet.

~~~java
// Fragment in MVC controller; pass a cancellation token with a clear lifecycle.
@GetMapping("/slow")
public StreamingResponseBody slow() {
    return out -> {
        for (int i = 0; i < 60 && !draining.get(); i++) {
            out.write(("part-" + i + "\n").getBytes(StandardCharsets.UTF_8));
            out.flush();
            try {
                Thread.sleep(1000);
            }
            catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                break;
            }
        }
    };
}
~~~

This is a **fragment**, with no `draining` field declared; a runnable example appears in section 11. What matters is checking the cancellation flag between chunks, keeping chunk counts and time bounded, handling interrupts, and ensuring cleanup in `finally`.

### 7.1. After the response is committed

A 200 streaming response may have already sent headers and 100 chunks. When the server stops before chunk 101, it **cannot go back and change the status to 503** or “roll back” bytes already sent. Clients must have:

- Checksums/lengths/trailers or an explicit application-level end marker.
- Sequences/cursors to resume downloading.
- HTTP Range/206 for resumable files, along with ETag/version.
- For export jobs, separate **job completion** from the download connection; store durable artifacts and let clients poll/re-download.

Do not assume “server closed socket” always means the response succeeded. Chunked HTTP/1.1 has an end marker; abnormal truncation can trigger an I/O error on the client, yet application-level data integrity still needs an explicit contract.

### 7.2. Executors and stopping producers

Spring MVC streaming can perform blocking I/O on `AsyncTaskExecutor`. With 1,000 streams and an 8-thread pool, the remainder will queue or reject per config. Do not use unbounded queues or blindly grow threads to hold streams forever. When draining:

1. Accept no new streams.
2. Emit cancellation signals to producers.
3. Let already-written chunks finish within a deadline.
4. Close/cancel upstream work and save state for resumability.
5. Wait until active stream count reaches 0 or the allowed timeout expires.
6. Do not keep the request executor alive forever just for a non-reading client.

With Spring MVC `DeferredResult`, during shutdown you can call `setResult`/`setErrorResult` if the request hasn't completed yet, alongside `onCompletion`/`onTimeout`; do not try to finish an already-set result. With `ResponseBodyEmitter`, use `complete()` or the proper error path just like SSE.

### 7.3. Never write endlessly during drain

If a thread is blocked on a socket write, checking `draining.get()` at the top of the loop **never runs** until the write returns. You need network I/O timeouts/proxy/connector policies, bounded producer queues, and shutdown deadlines. Do not assume a Java flag immediately interrupts a blocking kernel write.

## 8. Runnable example: Spring Boot 4.1.2 MVC with SSE, WebSocket, and drain

Demo endpoints:

| Endpoint | Purpose |
| --- | --- |
| `GET /events` | Keeps SSE open and sends heartbeats; at end of session can send `server-draining` |
| `GET /ws` | Raw WebSocket handshake, server tracks session; drain sends Close 1001 |
| `GET /slow-stream` | Long plain-text HTTP response up to 120 chunks, one chunk per second |
| `POST /internal/drain` | Switches readiness, blocks new streams, tries sending terminal SSE and closing sockets |
| `GET /internal/status` | Returns JSON counts of sessions/streams and draining state |
| `GET /actuator/health/readiness` | Spring Boot readiness probe when probes are enabled |
| `GET /demo.html` | Browser client to observe SSE and raw WebSocket |

**Scope:** localhost demo, no authentication, no durable event log. Do not deploy publicly; drain endpoints must be restricted to management/control planes in production. The demo proves **lifecycle**, not guaranteed event delivery.

### 8.1. Project structure

~~~text
long-lived-shutdown-lab/
  pom.xml
  src/main/java/com/example/longshutdown/
    LongShutdownApplication.java
    StreamRegistry.java
    LiveController.java
    RawSocketHandler.java
    WebSocketConfig.java
    AsyncMvcConfig.java
  src/main/resources/
    application.properties
    static/demo.html
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
        <version>4.1.2</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>long-lived-shutdown-lab</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-websocket</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
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

Boot 4.1.2's `spring-boot-starter-websocket` provides Spring MVC WebSocket support, including Servlet MVC needed for controllers and raw WebSocket handlers. Actuator supplies the readiness endpoint; no WebFlux starter is needed for a blocking MVC demo. When using WebFlux/Netty, use a suitably configured project rather than mixing Servlet APIs into a reactive server.

### 8.3. application.properties

~~~properties
# Lab listens only on localhost; DO NOT expose to the Internet.
server.address=127.0.0.1
server.port=8080

# Boot 4 enables graceful by default; declared explicitly for learning.
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=20s

# Async Servlet writes have their own deadline.
spring.mvc.async.request-timeout=180s

# Health/readiness, expose only what is needed for the demo.
management.endpoint.health.probes.enabled=true
management.endpoints.web.exposure.include=health,info

# Do not log raw messages/headers.
logging.level.com.example.longshutdown=INFO
~~~

**Important:** When deploying to Kubernetes, you cannot keep `server.address=127.0.0.1` and expect readiness traffic from outside the pod to work like a standard deployment. The lab binds loopback intentionally; production configures listeners and management networks per cluster, combined with auth/network policies.

### 8.4. LongShutdownApplication.java

~~~java
package com.example.longshutdown;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.scheduling.annotation.EnableScheduling;

@SpringBootApplication
@EnableScheduling
public class LongShutdownApplication {

    public static void main(String[] args) {
        SpringApplication.run(LongShutdownApplication.class, args);
    }
}
~~~

`@EnableScheduling` enables periodic SSE comment heartbeats in `StreamRegistry`. In production, a single-threaded scheduler blocked by one slow client can stall all other clients; see section 13 to design dedicated writers/queues.

### 8.5. StreamRegistry.java

~~~java
package com.example.longshutdown;

import java.io.IOException;
import java.util.List;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.context.ApplicationContext;
import org.springframework.context.event.ContextClosedEvent;
import org.springframework.context.event.EventListener;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;
import org.springframework.web.socket.CloseStatus;
import org.springframework.web.socket.WebSocketSession;

@Component
public class StreamRegistry {

    private final AtomicBoolean draining = new AtomicBoolean(false);
    private final Set<SseEmitter> emitters = ConcurrentHashMap.newKeySet();
    private final ConcurrentMap<String, WebSocketSession> sockets =
            new ConcurrentHashMap<>();
    private final AtomicInteger activeHttpStreams = new AtomicInteger();
    private final ApplicationContext applicationContext;

    public StreamRegistry(ApplicationContext applicationContext) {
        this.applicationContext = applicationContext;
    }

    public boolean isDraining() {
        return draining.get();
    }

    public int sseCount() {
        return emitters.size();
    }

    public int websocketCount() {
        return sockets.size();
    }

    public int longStreamCount() {
        return activeHttpStreams.get();
    }

    public void streamStarted() {
        activeHttpStreams.incrementAndGet();
    }

    public void streamFinished() {
        activeHttpStreams.decrementAndGet();
    }

    public SseEmitter registerSse() {
        if (draining.get()) {
            return null;
        }

        SseEmitter emitter = new SseEmitter(180_000L);
        emitter.onCompletion(() -> emitters.remove(emitter));
        emitter.onTimeout(() -> emitters.remove(emitter));
        emitter.onError(error -> emitters.remove(emitter));
        emitters.add(emitter);

        // Re-check so sessions opened concurrently with drain are not missed.
        if (draining.get()) {
            emitters.remove(emitter);
            emitter.complete();
            return null;
        }
        return emitter;
    }

    public void registerWebSocket(WebSocketSession session)
            throws IOException {
        if (draining.get()) {
            session.close(CloseStatus.GOING_AWAY);
            return;
        }

        sockets.put(session.getId(), session);

        // If drain occurred right after the put operation.
        if (draining.get() &&
                sockets.remove(session.getId(), session)) {
            session.close(CloseStatus.GOING_AWAY);
        }
    }

    public void unregisterWebSocket(WebSocketSession session) {
        sockets.remove(session.getId(), session);
    }

    @Scheduled(fixedDelay = 5_000)
    public void heartbeat() {
        if (draining.get()) {
            return;
        }
        for (SseEmitter emitter : emitters) {
            if (draining.get()) {
                return;
            }
            try {
                // SSE comment: client ignores content, proxy sees data.
                emitter.send(SseEmitter.event().comment("heartbeat"));
            }
            catch (IOException disconnected) {
                // Servlet container handles the async error path.
                emitters.remove(emitter);
            }
        }
    }

    public boolean drain() {
        if (!draining.compareAndSet(false, true)) {
            return false;
        }

        AvailabilityChangeEvent.publish(
                applicationContext, ReadinessState.REFUSING_TRAFFIC);

        for (SseEmitter emitter : List.copyOf(emitters)) {
            try {
                emitter.send(SseEmitter.event()
                        .name("server-draining")
                        .data("reconnect")
                        .reconnectTime(3000L));
                emitter.complete();
            }
            catch (IOException | IllegalStateException cannotSend) {
                // Peer may have left. Do not call completeWithError after
                // IOException on Servlet write: container handles it.
            }
            finally {
                emitters.remove(emitter);
            }
        }

        for (WebSocketSession session : List.copyOf(sockets.values())) {
            try {
                if (session.isOpen()) {
                    session.close(CloseStatus.GOING_AWAY);
                }
            }
            catch (IOException cannotClose) {
                // Peer may have lost network. Record bounded metric/log
                // if this were a production app.
            }
            finally {
                sockets.remove(session.getId(), session);
            }
        }
        return true;
    }

    @EventListener(ContextClosedEvent.class)
    public void onContextClosed() {
        // Fallback if the environment sends SIGTERM without calling /internal/drain.
        // Terminal event delivery is best-effort only, not an ACK.
        drain();
    }
}
~~~

**Detailed concurrency analysis:**

- `AtomicBoolean.compareAndSet(false,true)` makes drain **idempotent**; only the first drain call performs closing.
- `ConcurrentHashMap.newKeySet()` and concurrent maps let callbacks remove sessions concurrently with drain.
- Checking `draining` **after** registering prevents a session from slipping into the registry after drain's snapshot.
- `onCompletion`/`onTimeout`/`onError` all remove; removal is idempotent.
- `List.copyOf(emitters)` takes a snapshot to iterate safely while callbacks remove concurrently.
- If SSE send throws IOException, **do not** call `completeWithError`/`complete` in catch; Spring MVC receives the async error from the container. If send succeeds, call `complete()` so the request can finish cleanly.
- WebSocket calls `close(CloseStatus.GOING_AWAY)` and removes in `finally`, even if the client already closed. The `afterConnectionClosed` callback can safely remove again.
- `@EventListener(ContextClosedEvent.class)` is a **fallback**: context close does not guarantee every event reaches the peer or every appender/broker is still ready; production should proactively drain **before** SIGTERM when the platform supports it.
- Heartbeats here send sequentially on one scheduler, suited for **a lab with few clients**. Production must not let one slow client block and delay heartbeats for all clients.
- `activeHttpStreams` counts `StreamingResponseBody` callbacks that have started running, not total HTTP requests/response bytes; real production telemetry should distinguish accepted streams not yet scheduled by the thread pool.

### 8.6. RawSocketHandler.java

~~~java
package com.example.longshutdown;

import org.springframework.stereotype.Component;
import org.springframework.web.socket.CloseStatus;
import org.springframework.web.socket.WebSocketSession;
import org.springframework.web.socket.handler.TextWebSocketHandler;

@Component
public class RawSocketHandler extends TextWebSocketHandler {

    private final StreamRegistry registry;

    public RawSocketHandler(StreamRegistry registry) {
        this.registry = registry;
    }

    @Override
    public void afterConnectionEstablished(WebSocketSession session)
            throws Exception {
        registry.registerWebSocket(session);
    }

    @Override
    public void afterConnectionClosed(
            WebSocketSession session, CloseStatus status) {
        registry.unregisterWebSocket(session);
    }

    @Override
    public void handleTransportError(
            WebSocketSession session, Throwable exception) {
        registry.unregisterWebSocket(session);
    }
}
~~~

The handler does not echo messages because the exercise focuses on **closing sessions**. If you add background producers or reply to messages, ensure they do not send concurrently to the same raw WebSocket session, enforce bounded queues/send time limits, and stop producers before closing during drain. `ConcurrentWebSocketSessionDecorator` can be used if multiple threads send to the same session; **keep a single decorator per session**.

### 8.7. WebSocketConfig.java

~~~java
package com.example.longshutdown;

import org.springframework.context.annotation.Configuration;
import org.springframework.web.socket.config.annotation.EnableWebSocket;
import org.springframework.web.socket.config.annotation.WebSocketConfigurer;
import org.springframework.web.socket.config.annotation.WebSocketHandlerRegistry;

@Configuration(proxyBeanMethods = false)
@EnableWebSocket
public class WebSocketConfig implements WebSocketConfigurer {

    private final RawSocketHandler handler;

    public WebSocketConfig(RawSocketHandler handler) {
        this.handler = handler;
    }

    @Override
    public void registerWebSocketHandlers(
            WebSocketHandlerRegistry registry) {
        registry.addHandler(handler, "/ws")
                .setAllowedOrigins("http://localhost:8080");
    }
}
~~~

Only the demo browser's origin is allowed. **Origin is not authentication**, since non-browser clients can omit or spoof Origin. Production requires authentication/authorization at handshake, session expiry, tenant quotas, and TLS/WSS.

### 8.8. AsyncMvcConfig.java

~~~java
package com.example.longshutdown;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.web.servlet.config.annotation.AsyncSupportConfigurer;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration(proxyBeanMethods = false)
public class AsyncMvcConfig {

    @Bean
    ThreadPoolTaskExecutor streamTaskExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(32);
        executor.setThreadNamePrefix("mvc-stream-");
        return executor;
    }

    @Bean
    WebMvcConfigurer asyncWebMvcConfigurer(
            ThreadPoolTaskExecutor streamTaskExecutor) {
        return new WebMvcConfigurer() {
            @Override
            public void configureAsyncSupport(
                    AsyncSupportConfigurer configurer) {
                configurer.setTaskExecutor(streamTaskExecutor);
                configurer.setDefaultTimeout(180_000L);
            }
        };
    }
}
~~~

The numbers 4/8/32 are **for the lab only**, not production sizing. The executor uses a bounded queue so tasks do not accumulate infinitely under many long streams; requests may be rejected if capacity is exceeded, requiring a handling contract/metrics. Growing long-lived blocking writes ties up threads for a long time; WebFlux uses non-blocking I/O yet still must manage memory/buffers/cancellation.

### 8.9. LiveController.java

~~~java
package com.example.longshutdown;

import java.nio.charset.StandardCharsets;
import java.util.Map;

import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;
import org.springframework.web.servlet.mvc.method.annotation.StreamingResponseBody;

@RestController
public class LiveController {

    private final StreamRegistry registry;

    public LiveController(StreamRegistry registry) {
        this.registry = registry;
    }

    @GetMapping("/events")
    public ResponseEntity<?> events() {
        SseEmitter emitter = registry.registerSse();
        if (emitter == null) {
            return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
                    .contentType(MediaType.TEXT_PLAIN)
                    .body("server draining");
        }
        return ResponseEntity.ok()
                .contentType(MediaType.TEXT_EVENT_STREAM)
                .body(emitter);
    }

    @GetMapping("/slow-stream")
    public ResponseEntity<?> stream() {
        if (registry.isDraining()) {
            return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
                    .contentType(MediaType.TEXT_PLAIN)
                    .body("server draining");
        }

        StreamingResponseBody body = out -> {
            registry.streamStarted();
            try {
                for (int i = 1;
                     i <= 120 && !registry.isDraining();
                     i++) {

                    out.write(("part-" + i + "\n")
                            .getBytes(StandardCharsets.UTF_8));
                    out.flush();

                    try {
                        Thread.sleep(1000L);
                    }
                    catch (InterruptedException interrupted) {
                        Thread.currentThread().interrupt();
                        break;
                    }
                }
            }
            finally {
                registry.streamFinished();
            }
        };

        return ResponseEntity.ok()
                .contentType(MediaType.TEXT_PLAIN)
                .body(body);
    }

    @GetMapping("/internal/status")
    public Map<String, Object> status() {
        return Map.of(
                "draining", registry.isDraining(),
                "sseSessions", registry.sseCount(),
                "websocketSessions", registry.websocketCount(),
                "activeStreamingCallbacks", registry.longStreamCount());
    }

    @PostMapping("/internal/drain")
    public ResponseEntity<String> drain() {
        boolean first = registry.drain();
        return ResponseEntity.ok(
                first ? "drain started" : "already draining");
    }
}
~~~

**Important distinction:** `/slow-stream` has already returned HTTP 200; when draining, the callback stops at the next chunk and cannot switch the status to 503 after commit. For download/export integrity, add artifact IDs/cursors/checksums and a resume mechanism. The sample loop caps at 120 seconds so it does not become an infinite stream. If the thread is blocked in `out.write()`, the flag is only checked once the call returns; transport timeouts and deadlines are also needed.

For `/events`, pre- and post-registration drain checks happen in the registry. When already draining, it returns HTTP 503 so no new stream opens. For `/internal/drain`, invoking it directly can take time if there are many slow clients: production should use a **bounded control-plane worker/deadline** instead of sending sequentially on the request thread as in the lab.

### 8.10. static/demo.html

Minimal HTML needing no external JavaScript libraries; opens one SSE stream and one raw WebSocket to observe closing:

~~~html
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>SSE & WebSocket shutdown lab</title>
  <style>
    body { font-family: system-ui, sans-serif; margin: 2rem; }
    button { padding: .5rem; margin-right: .5rem; }
    pre { border: 1px solid #aaa; height: 280px; overflow: auto; }
  </style>
</head>
<body>
  <h1>Long-lived connections lab</h1>
  <button id="connect">Open SSE + WebSocket</button>
  <button id="drain">Drain this server</button>
  <button id="close">Close clients</button>
  <pre id="log"></pre>
  <script>
    let sse = null;
    let ws = null;
    const log = line => {
      const p = document.getElementById("log");
      p.textContent += line + "\n";
      p.scrollTop = p.scrollHeight;
    };

    document.getElementById("connect").onclick = () => {
      if (sse) sse.close();
      if (ws && ws.readyState === WebSocket.OPEN) ws.close();

      sse = new EventSource("/events");
      sse.onopen = () => log("SSE open");
      sse.onerror = () => log("SSE error/end; may reconnect");
      sse.addEventListener("server-draining", event => {
        log("SSE terminal: " + event.data);
        sse.close(); // Avoid continuous auto-reconnect to the draining pod.
        sse = null;
      });

      const protocol = location.protocol === "https:" ? "wss://" : "ws://";
      ws = new WebSocket(protocol + location.host + "/ws");
      ws.onopen = () => log("WebSocket open");
      ws.onerror = () => log("WebSocket error");
      ws.onclose = event => log(
        "WebSocket close code=" + event.code
        + " reason=" + event.reason);
    };

    document.getElementById("drain").onclick = async () => {
      const response = await fetch("/internal/drain", { method: "POST" });
      log("Drain API: " + response.status + " " + await response.text());
    };

    document.getElementById("close").onclick = () => {
      if (sse) sse.close();
      sse = null;
      if (ws && ws.readyState === WebSocket.OPEN) ws.close();
    };
  </script>
</body>
</html>
~~~

This is a **lab client**. It **does not implement reconnect/backoff or durable replay**: learners just need to observe close events; production apps should reconnect through the Service/LB with backoff+jitter, token refresh, and snapshot/cursor fetching. The Drain button is intentionally left open on localhost for testing—never expose it on a public endpoint.

## 9. Running and verifying results

### 9.1. Startup

From the `long-lived-shutdown-lab` directory:

~~~bash
mvn spring-boot:run
~~~

Open:

~~~text
http://localhost:8080/demo.html
~~~

Click **Open SSE + WebSocket**. If no connection error occurs, the on-page console may display:

~~~text
SSE open
WebSocket open
~~~

Exact order and timing depend on browser/network, not fixed stdout. Sending periodic `:heartbeat` SSE comments does not trigger default `onmessage`; it primarily keeps the stream alive and detects disconnects on write.

Inspect the registry from a terminal:

~~~bash
curl -s http://127.0.0.1:8080/internal/status
~~~

With exactly one tab connected successfully, the JSON response includes fields:

~~~json
{
  "draining": false,
  "sseSessions": 1,
  "websocketSessions": 1,
  "activeStreamingCallbacks": 0
}
~~~

Session counts change with tabs, refreshes, scheduling, and timeouts. Do not assert the response is always 1 right after clicking or if a proxy/Origin blocked the connection.

### 9.2. Testing SSE with cURL

In another terminal:

~~~bash
curl -N -i -H "Accept: text/event-stream" \
  http://127.0.0.1:8080/events
~~~

`-N`/`--no-buffer` disables cURL output buffering so you see the stream sooner. The response typically shows `Content-Type: text/event-stream` and heartbeat lines like:

~~~text
:heartbeat

~~~

Not every proxy flushes comments immediately. To evaluate live SSE in production, test through your actual ingress/LB path, not just localhost.

### 9.3. Testing long HTTP responses

Run:

~~~bash
curl -N -i http://127.0.0.1:8080/slow-stream
~~~

You will see lines:

~~~text
part-1
part-2
part-3
~~~

Data continues until reaching 120 chunks, timeout, client close, or drain; in practice `curl -i` shows initial headers and timing depends on async execution. If the server drains mid-stream, the committed response may finish with **some subset of chunks**, rather than switching to HTTP 503.

### 9.4. Executing drain

While browser and curl are still connected:

~~~bash
curl -i -X POST http://127.0.0.1:8080/internal/drain
~~~

First time, the controller returns body:

~~~text
drain started
~~~

Next time:

~~~text
already draining
~~~

This is the **body** produced by the demo; headers/status line vary by HTTP client. Logically:

- Drain state is flipped via CAS.
- Readiness publishes `REFUSING_TRAFFIC`.
- SSE emitters in the snapshot receive a `server-draining` event if delivered in time, then complete.
- Raw WebSockets in the snapshot receive close code **1001** if the close handshake traverses the network.
- `/slow-stream` terminates when the callback checks the `draining` flag on the next iteration.
- Requests attempting new streams are rejected or not routed depending on readiness/layer; the controller returns 503 if reached.

After drain, verify:

~~~bash
curl -s http://127.0.0.1:8080/internal/status
curl -i http://127.0.0.1:8080/events
curl -i http://127.0.0.1:8080/slow-stream
~~~

Status shows `"draining":true`, and SSE/WebSocket session counts usually drop to 0 after cleanup. Both stream-opening endpoints return HTTP **503** if requests reach the controller. **Note:** calling internal endpoints after the server already received SIGTERM may be refused at the network layer so cURL might not receive an HTTP response.

### 9.5. Readiness probe in the lab

With probes enabled:

~~~bash
curl -i http://127.0.0.1:8080/actuator/health/readiness
~~~

Before drain, readiness is normally `UP` when the app is ready. After `AvailabilityChangeEvent.publish(...REFUSING_TRAFFIC)`, readiness corresponds to `OUT_OF_SERVICE` and health HTTP status is typically 503 per default status mapping. **Do not set liveness = BROKEN** just for graceful shutdown.

If the probe endpoint is missing, check the Actuator dependency, `management.endpoint.health.probes.enabled=true`, management port/path mapping, and exposure/access policies; do not disable security across all of Actuator to fix it.

### 9.6. Proper SIGTERM test

Package:

~~~bash
mvn package
~~~

Run the JAR with Java in a POSIX shell (Linux/macOS/WSL) from project root:

~~~bash
java -jar target/long-lived-shutdown-lab-0.0.1-SNAPSHOT.jar &
APP_PID=$!
echo "java pid=$APP_PID"
~~~

Open browser/SSE in another terminal, then send:

~~~bash
kill -TERM "$APP_PID"
wait "$APP_PID"
~~~

When the Spring Boot process receives a normal SIGTERM, the application context starts closing. The `@EventListener(ContextClosedEvent.class)` callback in the demo invokes `drain()` as a fallback to close SSE/WebSockets before or during lifecycle close. The embedded server also performs graceful shutdown per config. **Do not promise** the terminal event definitely reaches every browser or that the process stops in exactly 20 seconds; ordering, timeouts, connectors, and other shutdown hooks can affect it.

Do not use `kill -9` to test graceful shutdown: SIGKILL **does not run** Java shutdown hooks, `@EventListener`, or `@PreDestroy`. On Windows, process signal delivery differs, and an IDE Stop button may perform an immediate kill.

## 10. Kubernetes: preStop, readiness, and SIGTERM deadlines

A typical rolling deployment should coordinate:

1. Transition the pod to **not ready** before stopping service so the LB/Service stops routing new traffic.
2. Block new sessions/streams inside the application immediately.
3. Send terminal control events, close WebSockets and SSE, and let clients reconnect to another pod.
4. Allow time for propagation and finite in-flight work.
5. Send SIGTERM and let Spring Boot graceful shutdown execute.
6. Exit within the grace period or get force-killed if the deadline expires.

### 10.1. Pod manifest fragment

~~~yaml
apiVersion: v1
kind: Pod
metadata:
  name: long-shutdown-demo
spec:
  terminationGracePeriodSeconds: 45
  containers:
    - name: app
      image: example/long-shutdown-demo:1.0
      ports:
        - containerPort: 8080
      readinessProbe:
        httpGet:
          path: /actuator/health/readiness
          port: 8080
        periodSeconds: 2
        failureThreshold: 1
      lifecycle:
        preStop:
          exec:
            command:
              - /bin/sh
              - -c
              - "curl -fsS -X POST http://127.0.0.1:8080/internal/drain; sleep 5"
~~~

**This is an illustrative deployment fragment, not a complete production manifest**: no real image is built, and securityContext/resources/Service/replicas/ingress are omitted. Minimal images may **lack curl or /bin/sh**; in that case use a sidecar, a lifecycle endpoint via the control plane, or another supported hook. On Kubernetes, **remove** the lab's `server.address=127.0.0.1` so probes and Services can reach the app on the pod IP; still restrict management routes to trusted traffic.

### 10.2. Calculating deadlines

Example:

~~~text
Kubernetes grace total:   45 s
  preStop drain + sleep:   5 s (can be longer if slow clients)
  app SIGTERM/grace:      20 s / lifecycle phase (illustrative config)
  margin for runtime/hooks: not strictly fixed
~~~

`preStop` time **is counted inside** Kubernetes `terminationGracePeriodSeconds`; it is not a bonus after the deadline. The hook can be killed if it exceeds the limit, while external LB/readiness propagation also incurs lag. Never design “40s preStop + 40s Spring grace” when pod grace is only 45s.

### 10.3. Readiness propagation is not instant

A `NotReady` pod can take time to be removed from Service/LB/Ingress endpoints. Therefore, in-app admission control must reject **new** streams while draining, even if a request arrives during the propagation window. Existing WebSocket/SSE connections are pinned to pod A; Kubernetes **does not automatically migrate TCP/WebSocket connections** to pod B.

Clients must reconnect via the stable Service URL, re-authenticate/re-subscribe, and fetch snapshots/replay. If connections pass through a proxy, proxy idle/termination policies may also close them ahead of the application.

### 10.4. Never call /internal/drain when no replacement pod exists

Rolling deployments must verify **new pod readiness** and enough replica capacity before the old pod exits. If all instances drain simultaneously, clients try to reconnect to a Service with zero healthy backends, causing errors/retry queues. Configure `maxUnavailable`/`maxSurge`, PodDisruptionBudgets, and autoscaler policies properly.

## 11. STOMP over WebSocket: subscriptions, brokers, and session events

If the app uses `@EnableWebSocketMessageBroker` instead of raw WebSockets, management differs:

~~~text
Client WebSocket + STOMP CONNECT
   |
   +-- SUBSCRIBE /topic/orders
   |
   v
Spring simple broker or broker relay
   |
   +-- server sends STOMP MESSAGE frames
   |
   v
drain
   |
   +-- stop publishing new events to old session
   +-- (optional) app notice "server-draining"
   +-- close WebSocket / stop transport
   +-- SessionDisconnectEvent / cleanup
   +-- client reconnect + new CONNECT + SUBSCRIBE
~~~

### 11.1. SessionDisconnectEvent can fire multiple times

Listener illustrating idempotency:

~~~java
// Fragment inside a Spring-managed @Component.
@EventListener
public void onSessionDisconnect(SessionDisconnectEvent event) {
    String sessionId = event.getSessionId();
    if (activeSessionIds.remove(sessionId)) {
        // Cancel subscription/job/resource strictly once.
    }
}
~~~

`activeSessionIds` is an application-managed registry; the snippet above **is not a standalone Java file**. The event can fire on client STOMP DISCONNECT or when the WebSocket closes, and may be published **multiple times**. Never double-decrement counters or double-charge/refund on repeated events.

### 11.2. Broker relays do not replace a durable replay contract

When using an external broker (RabbitMQ/ActiveMQ), acknowledgments/queues/retention may exist depending on STOMP destination and broker config. Yet a client WebSocket disconnecting **does not prove** all business events were processed. Distinguish:

- Event created by the app.
- Event accepted/committed by the broker.
- Event sitting in a queue/subscription.
- Event written to the outbound WebSocket.
- Browser receiving and processing the event.
- Application-level ACK/transaction completing.

Without a durable store and business ACKs, an event emitted right before drain can be lost to the client. For payments/audits, never treat “sent STOMP MESSAGE” as a committed business transaction.

### 11.3. Broker shutdown order

If you stop the broker connection/producer too early, clients miss the app notice; if you wait too long on the broker, the pod hits its deadline. Stage it by phase:

1. Gate new sends/subscriptions while draining.
2. Attempt to send control notices or persist required state.
3. Close sessions.
4. Cancel application-level consumers/actors.
5. Stop the broker relay/client connection per lifecycle.
6. Shut down the context and HTTP server.

In production, lifecycle hooks should coordinate with `SmartLifecycle`/ApplicationContext closure and deadlines; do not assume arbitrary `@PreDestroy` bean order suffices.

## 12. WebFlux: canceling Publishers and WebSockets with the right lifecycle

Spring WebFlux uses non-blocking pipelines rather than Servlet `SseEmitter`. HTTP SSE typically returns:

~~~java
// Fragment in a WebFlux @RestController.
@GetMapping(value = "/events", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
public Flux<ServerSentEvent<String>> events() {
    return eventSource
            .takeUntilOther(drainingSignal)
            .doFinally(signal -> subscriptions.releaseCurrent());
}
~~~

The snippet only **illustrates the logic**: `eventSource`, `drainingSignal`, and `subscriptions` are hypothetical app variables; the code cannot run standalone. Note that `takeUntilOther(Publisher)` stops the stream when another publisher **emits a signal**, not automatically when a boolean flag flips. `doFinally` runs on complete/error/cancel and should perform idempotent cleanup.

### 12.1. SSE with Flux does not guarantee the browser receives the final event

When `takeUntilOther(shutdownSignal)` completes the `Flux`, the HTTP connection may complete, yet whether a terminal control event goes out beforehand is not automatic. To emit a final event, build a state machine/publisher that is **serialized** in exact order:

~~~text
business events -> server-draining control event -> onComplete
~~~

If multiple publishers emit concurrently, use proper synchronization/sinks; never arbitrarily call `sink.tryEmitNext` after `tryEmitComplete` expecting the event to be received.

### 12.2. WebFlux WebSocket

Per Spring WebFlux documentation:

- `WebSocketSession.receive()` returns `Flux<WebSocketMessage>` and completes when the connection closes.
- `WebSocketSession.send(Publisher<WebSocketMessage>)` returns `Mono<Void>` when the source completes and finishes sending per connector contract.
- `WebSocketHandler.handle(session)` must return a `Mono<Void>` reflecting the lifecycle of inbound/outbound streams.
- `session.close(CloseStatus.GOING_AWAY)` can be used per the WebFlux `CloseStatus` API, but the Mono must be composed into the pipeline so it is **actually subscribed**; calling a reactive method and ignoring the Mono has no effect.

Conceptual example:

~~~java
// Fragment inside a WebFlux WebSocketHandler; not standalone.
// shutdownSignal must be a Publisher emitting a signal on drain.
Mono<Void> outbound = session.send(
        outboundMessages.takeUntilOther(shutdownSignal)
                .map(session::textMessage));

Mono<Void> inbound = session.receive()
        .doOnNext(message -> {
            // validate/route; do not block the event loop
        })
        .then();

return Mono.whenDelayError(inbound, outbound)
        .doFinally(signal -> cleanupSession(session.getId()));
~~~

This is a **mechanics** example: `outboundMessages`, `shutdownSignal`, and `cleanupSession` are undefined. If the outbound source completes on drain while inbound has not finished, `whenDelayError` may **keep waiting on inbound**. To close immediately, design the lifecycle with racing/cancellation or actively invoke `session.close(...)` and compose it into the publisher. Do not copy this fragment and claim WebSockets definitely close on deadline.

### 12.3. Hot streams and cancellation

A hot source can keep emitting after a subscriber cancels if the producer ignores demand/cancellation or lacks cleanup. With Reactor:

- `doFinally`/`usingWhen` to clean up resources on complete/error/cancel.
- `takeUntilOther` to tie streams to a drain signal.
- `onBackpressureBuffer(maxSize, ...)` must be bounded if used.
- `Sinks.Many.tryEmitNext` must handle `EmitResult` when subscribers are slow/closed.
- Do not call `block()` on the Netty event loop just to wait for drain.
- On shutdown, cancel subscriptions, timers, database change streams, message broker consumers, and HTTP clients per ownership.

Reactor Netty graceful server shutdown has its own connection lifecycle behavior; test through a real Netty server and gateway rather than projecting Servlet worker thread rules directly.

## 13. Slow clients, backpressure, and total deadline

A long-lived connection can fail to close quickly because:

- Client reads TCP slowly and kernel send buffers fill up.
- TLS writes or proxy forwarding stall.
- A heartbeat/terminal SSE scheduler is blocked on one session.
- A WebSocket outbound queue has many messages ahead of the control event.
- A STOMP client hasn't acked and the broker is waiting.
- A long-running database/export task has not received cancellation.

Do not write a single drain loop **sending sequentially** to 100,000 SSE clients on a request thread without a deadline. Use a bounded control-plane worker pool, per-session write queues with limits, deadlines, and metrics.

### 13.1. Ordered termination priorities

1. Stop upstream producers from generating new events into old sessions.
2. Set readiness `REFUSING_TRAFFIC` and the admission gate.
3. Send prioritized control events or enqueue into a serialized writer queue.
4. Give a brief policy-defined window for clients to receive the close notice, then close anyway.
5. Close WebSocket/SSE/streams with cleanup.
6. Cancel tasks/queues/outstanding subscriptions.
7. Hand off durable state or let clients replay from a durable source.
8. When the deadline hits, let shutdown proceed; never block liveness indefinitely.

A successful **buffered SSE write** only means the server wrote to its output layer, not that the client rendered it. Likewise, WebSocket close 1001 may never reach the browser if the network died. Therefore backend state must stay independent of ephemeral notices.

### 13.2. Policies by data type

| Data | During drain | Recovery |
| --- | --- | --- |
| Dashboard latest state | Close/reconnect relatively quickly | GET latest snapshot |
| Chat messages | Stop publishing to old session, close socket | Fetch messages after cursor |
| Order/payment events | Persist/outbox before sending | Idempotent replay/business ACK |
| Audit events | Flush durable log per SLA | Durable log consumer resume |
| Video/large download | Allow finite time or cut cleanly | Resume via Range/ETag if supported |
| SSE price ticker | Terminal notice, complete | Reconnect + latest snapshot |
| WebSocket game actions | Stop accepting new actions, save state | Resume session/game state per policy |

“Disconnected socket” must not wipe out uncommitted business work. Separate **stream connection lifecycle** from **durable business transaction lifecycle**.

## 14. Proxies, Ingress, HTTP/2, and edge cases

### 14.1. Load balancers do not migrate existing connections

Removing a pod from Service endpoints only affects routing of **new connections/requests**. Existing TCP/WebSocket connections typically remain pinned to the old pod until closed or LB drain policy kicks in. HTTP keep-alive may still carry requests over an old connection; how new requests get rejected depends on the embedded server connector.

### 14.2. SSE buffered by proxies

Proxy buffering can hold a terminal SSE event until enough bytes accumulate or the connection closes. The client might never see `server-draining` before the response ends. Check appropriate proxy options for streaming endpoints (e.g., disabling buffering on specific routes), idle timeouts, HTTP/2 behavior, compression, and flush semantics.

### 14.3. HTTP/2 GOAWAY is not a WebSocket close frame

HTTP/2 uses `GOAWAY` to signal stopping new streams on a connection. WebSocket close code 1001 is a frame of the **WebSocket protocol**. SSE is HTTP response streaming. Do not mistake one frame type for another; a proxy/LB may terminate HTTP/2/TLS at the edge and open fresh HTTP/1.1 connections to Spring Boot.

### 14.4. Ingress/LB timing out before the application

Even if Spring MVC `SseEmitter` timeout is 30 minutes, a 60-second LB idle timeout can cut the connection after 60 seconds with no bytes flowing. Heartbeats help, yet are not guaranteed if proxies buffer, networks fail, or the app is blocked. Test the **real path**, not just localhost. Never set a 5-minute client heartbeat interval when the ingress idle timeout is 1 minute.

### 14.5. TLS termination and reconnect

If a browser connects to `wss://service.example` through an Ingress to pod A, when pod A stops the browser must reconnect to the **same public hostname**, not a Pod IP or old internal raw socket URL. The app must enforce proper auth token/session policies; if a token expires during drain, refresh it validly before re-subscribing.

## 15. State, replay, and avoiding reconnect storms

### 15.1. Event IDs and business cursors

Suppose an event log has monotonically increasing IDs:

~~~text
101 -> created
102 -> paid
103 -> shipped
104 -> delivered
~~~

A client processed up to 102 and lost its socket. It can call `GET /events?after=102` or send `Last-Event-ID: 102` when SSE reconnects. The backend must **validate tenant ownership**, query the durable log, enforce retention, handle duplicates, and finish replay before switching to the live stream to avoid gaps.

A new WebSocket does not automatically inherit the old socket's subscriptions or state; it must re-authenticate and send the last processed cursor. Never use the **server send attempt** as the last ACKed cursor.

### 15.2. Exponential backoff + jitter

Illustrative reconnect sequence:

~~~text
attempt 1 -> random 0.5–1.5 s
attempt 2 -> random 1–3 s
attempt 3 -> random 2–6 s
attempt 4 -> random 4–12 s
max retry delay -> 30 s, with jitter
~~~

These numbers are **examples**, not a mandatory standard. The goal: when thousands of clients receive close code 1001 simultaneously, avoid triggering 10,000 WebSocket handshakes in one second. The server should also rate-limit handshakes, auth, subscriptions, and replay APIs; clients should handle offline state, retry limits, token renewal, and loading UX.

### 15.3. What should a client do after receiving 1001?

1. Close resources of the old WebSocket; stop sending to the old socket.
2. Do not treat closure as confirmation that all outbound business commands were received/committed.
3. Reconnect after backoff through the Service URL to a healthy instance.
4. Re-authenticate and re-subscribe.
5. Fetch a snapshot or replay from the cursor/offset of **already-processed events**.
6. Deduplicate using event IDs/idempotency keys.
7. Show a “reconnecting” UI indicator while data is stale.
8. Cap retries and show a degraded state if no healthy backend is reachable.

## 16. Observability when shutting down long-lived connections

### 16.1. Metrics to track

| Suggested metric | Meaning |
| --- | --- |
| `active_sse_connections` | Number of managed SSE emitters |
| `active_websocket_sessions` | Number of open raw/STOMP sessions |
| `active_streaming_callbacks` | Async streaming tasks currently executing |
| `draining_state` | 0/1 or instance status |
| `drain_duration_seconds` | Time from drain start until 0 sessions or deadline |
| `stream_terminations_total{reason=...}` | normal, timeout, error, drain, force-close |
| `websocket_close_total{code=...}` | Close codes from a bounded set of values |
| `sse_emit_error_total` | I/O errors and terminal send failures |
| `reconnect_rate` | Reconnects/sec after deploy |
| `replay_lag_seconds` | Recovery lag from durable log |
| `discarded_events_total` | Data dropped due to queue/overflow |
| `shutdown_timeouts_total` | Grace expired before completion |
| `readiness_state` | Whether instance accepts new traffic |

Not all metrics exist automatically in Boot Actuator; custom Micrometer gauges/counters, tracing, and platform metrics are required. Avoid attaching session IDs, user IDs, or raw URLs to metric labels (cardinality and privacy).

### 16.2. When is a drain considered “successful”?

**Not just** “process exit code 0”. A good set of criteria includes:

- After draining state is turned on, no **new long-lived sessions** are accepted on that instance.
- Readiness drops and routing shifts smoothly to healthy pods.
- Active SSE/WS sessions drop to 0 or below an accounted exception threshold.
- No queues/broker subscriptions/timers/resources leak after close.
- Critical streams complete or have **durable resume/cursors**.
- HTTP/WS client reconnect rates stay within budget.
- No 5xx/timeout spike exceeding SLO during rollout.
- Time-to-termination stays within the orchestrator's total grace period.
- Events with delivery contracts are not lost due to shutdown races.

### 16.3. Concise and safe logs

A shutdown log needs:

~~~text
drain_started instance=pod-a active_sse=12 active_ws=30
drain_finished instance=pod-a remaining_sse=0 remaining_ws=0
~~~

This is an illustrative log format, **not fixed lab stdout**. Never log raw SSE data, WebSocket payloads, Authorization headers, session cookies, or user PII. Trace/correlation IDs may be added while avoiding high-cardinality labels.

## 17. Test plan and chaos testing

### 17.1. Suggested test matrix

| Test | How to trigger | Expected outcome |
| --- | --- | --- |
| No connections | Call drain with empty registry | No errors; state transitions properly |
| SSE normal | Open EventSource, drain | Receives terminal if sent in time, emitter completes/cleans up |
| SSE already disconnected | Client disconnects before drain | Cleanup does not throw or double-complete |
| WS normal | Open WebSocket, drain | Client can observe code 1001; registry cleaned up |
| WS abnormal | Kill browser/network before drain | Server does not leak session forever |
| Many clients | Open N sessions, drain concurrently | Time/memory do not grow unbounded |
| Drain called twice | POST twice | Close runs once; second call is idempotent |
| New requests during drain | Race opening SSE/WS with POST drain | No new session survives after drain |
| Slow HTTP stream | Client reads slowly | Deadline/timeout applies; shutdown does not hang forever |
| SIGTERM | `kill -TERM` on Java process | Callbacks/lifecycle triggered if runtime supports it |
| SIGKILL | `kill -9` | No graceful hooks; client/replay still recovers |
| K8s preStop | Rolling deploy | Readiness and streams transition cleanly; pod exits within grace |
| Proxy idle timeout | Through real ingress | Heartbeat/reconnect behaves appropriately |
| Duplicate STOMP SessionDisconnectEvent | Deliver duplicate events | Cleanup executes once |
| Durable replay | Disconnect between events 102/103 | Client recovers exact data without duplicate effects |

### 17.2. Stress testing properly

- Confine tests to an isolated environment; never run against shared production.
- Use load-generator clients supporting WebSocket/SSE and network shaping; browser JS delays **do not reliably** make TCP readers slow.
- Test under queue/buffer pressure, large payloads, and low bandwidth.
- Keep one group of fast clients to check fairness while another group is slow.
- Measure pending bytes, active write threads, scheduling latency, and heap/GC.
- Run canary rolling deploys under load; do not only test shutting down an idle process.
- Verify the traffic generator/broker/client CPU does not saturate before the server.

### 17.3. Race conditions to test intentionally

1. Client finishes connecting right as drain snapshots the registry.
2. Browser receives terminal SSE event while WebSocket close has not been sent yet.
3. `SseEmitter` onTimeout fires concurrently with drain calling complete.
4. WebSocket `afterConnectionClosed` runs concurrently with drain removing the map entry.
5. Connection write is slow/blocked when the shutdown deadline arrives.
6. Broker publishes a new message after `draining=true`.
7. SIGTERM arrives before preStop finishes.
8. New pod is not ready yet while old pod is already not ready.
9. Client reconnects to old pod while LB endpoints haven't updated yet.
10. Replay returns duplicate/out-of-order events after reconnect.

Each case needs assertions on **state and resource cleanup**, not just HTTP status codes.

## 18. Common mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Only enabling `server.shutdown=graceful` | SSE/WS can stay open until deadline expires | App-level drain and close |
| Only lowering readiness | Existing sockets do not migrate on their own | SSE terminal, WebSocket close, client reconnect |
| Only closing sockets without lowering readiness | LB keeps routing new streams to old pod | Drain state + readiness + admission gate |
| Not re-checking race after register | New session can slip in after snapshot | Atomic gate / check-after-add |
| Calling `completeWithError` right after SSE write IOException | Double async error handling | Let container handle I/O error, clean up registry |
| Thinking `SseEmitter.complete()` means client ACKed | Final event can be lost | Durable log/snapshot/replay |
| Sending close code 1006 | 1006 is reserved and must not go on the wire | Use `CloseStatus.GOING_AWAY`/1001 appropriately |
| Treating WebSocket close and STOMP DISCONNECT identically | Wrong cleanup/ACK semantics | Separate subprotocol and transport |
| Non-idempotent STOMP disconnect event handling | Double cleanup/counters/billing | Remove-if-present, idempotency |
| Using SIGKILL to test graceful | Hooks do not run | Test SIGTERM, and separately test force-kill recovery |
| preStop longer than K8s grace | Pod gets killed mid-cleanup | Budget grace and deadlines together |
| Unbounded sequential terminal sends | One slow client blocks shutdown control thread | Bounded workers/deadlines per session |
| Not stopping producers | Queues keep filling while closing | Gate publishing/cancel subscriptions |
| Returning HTTP 200 streamed halfway | Client thinks download is complete | Checksum/cursor/Range/job state |
| Not canceling timers/queues | Memory/session leaks across restarts/drains | Cleanup in onComplete/onClose/doFinally |
| Immediate reconnect without jitter | Reconnect storm after rollout | Exponential backoff+jitter |
| WebFlux canceling Mono without subscribing | Reactive close never executes | Compose/subscribe through lifecycle flow |
| Using `Thread.sleep` on Netty event loop | Blocks multiple connections | Non-blocking scheduling, bounded tasks |
| Measuring active connections without backlog | Misses slow-consumer overload | Pending bytes/queue/latency metrics |
| Public `/internal/drain` endpoint | Anyone can disconnect the service | Management-plane auth/RBAC/network policy |
| Connecting WebSocket by Pod IP | Reconnect fails after pod replacement | Stable Service DNS/Ingress |
| No replay/ACK | Events lost in shutdown races | Durable event log, cursor, idempotency |
| Calling app drain too late from `@PreDestroy` | Broker/HTTP server may have already stopped | Proactive preStop/early lifecycle hook |
| Ignoring proxy buffering of SSE | Terminal event never seen in browser | Test through ingress and configure streaming |

## 19. Pre-deployment production checklist

### Lifecycle management

- [ ] Inventoried all long-lived connections: SSE, raw WS, STOMP, file streaming, NDJSON, reactive Flux?
- [ ] Idempotent draining state blocking new sessions and checking post-registration races?
- [ ] Readiness `REFUSING_TRAFFIC` published before shutting down listeners?
- [ ] Secure preStop/control-plane path, fallback on context close, and real deadlines?
- [ ] preStop + app grace fit inside Kubernetes `terminationGracePeriodSeconds`?
- [ ] Avoided using SIGKILL as a routine shutdown method?
- [ ] Embedded server graceful settings match the Boot version and tested behavior?

### SSE/streaming

- [ ] `SseEmitter` has `onCompletion`/`onTimeout`/`onError` cleanup?
- [ ] Heartbeats suffice to detect disconnected peers and prevent proxy idle timeouts?
- [ ] Terminal control event sent on drain, without confusing it with a client ACK?
- [ ] `IOException` on send left to the container to handle, avoiding double-completion?
- [ ] HTTP streaming has a cancellation flag, interrupt handling, and `finally` cleanup?
- [ ] Committed responses have checksums/cursors/restart policies?
- [ ] `AsyncTaskExecutor` bounded, never held indefinitely by slow client writes?

### WebSocket/STOMP

- [ ] WS registry has idempotent `afterConnectionClosed`/transport-error cleanup?
- [ ] Server closes with `GOING_AWAY`/1001 instead of sending reserved codes?
- [ ] Client handles `onclose`/`onerror`/reconnect backoff+jitter?
- [ ] STOMP subscriptions/`SessionDisconnectEvent` cleanup is idempotent?
- [ ] Broker producers/queues stopped/canceled according to lifecycle?
- [ ] Sequence/replay/snapshot exists for data that must not be lost?
- [ ] Per-user quotas, auth, rate limits, session expiry, and client reconnect budgets?

### Infrastructure and observability

- [ ] Proxy/LB/Ingress tested for SSE buffering/idle timeout and WS keepalive?
- [ ] Enough healthy pods exist before draining old pods?
- [ ] Metrics for active sessions, drain duration, close reasons, dropped events, replay lag, and timeouts?
- [ ] Canary deploy/chaos tests for SIGTERM and force kills separately?
- [ ] No PII/session IDs in metric tags or raw payloads in logs?
- [ ] Drain endpoint and Actuator secured via network/auth/RBAC?
- [ ] Runbook exists for when grace expires while a worker/socket remains blocked?

## 20. Self-check questions with answers

**Question 1.** Spring Boot 4.1 enables graceful shutdown by default with Tomcat/Netty—does that mean SSE and WebSocket automatically close according to business protocol?

**Answer:** No. The graceful server manages admission and in-flight requests up to a timeout; the app still needs registry draining, producer stopping, terminal events, close frames, cleanup, and deadlines.

**Question 2.** Once readiness switches to `REFUSING_TRAFFIC`, do existing WebSockets automatically move to a new pod?

**Answer:** No. Existing connections typically stay attached to the old pod; the server must close them and clients must reconnect through the Service URL and restore subscriptions/state.

**Question 3.** Does sending SSE `server-draining` and calling `complete()` prove the browser received/ACKed the final message?

**Answer:** No. Server send/complete does not guarantee end-to-end delivery. Event IDs/cursors/replay are needed for critical data.

**Question 4.** Why should you not call `completeWithError` immediately when `SseEmitter.send` throws `IOException` due to client disconnect?

**Answer:** The Spring MVC Servlet async error path is handled by the container on write failure; the app should clean up the registry and avoid double-completion.

**Question 5.** What code is `CloseStatus.GOING_AWAY`? Is sending 1006 allowed?

**Answer:** `GOING_AWAY` is **1001**; **1006** is a reserved code describing abnormal closure and must never be sent in a close frame.

**Question 6.** When using STOMP, does `SessionDisconnectEvent` fire strictly once per client?

**Answer:** No. Spring docs state the event can repeat; cleanup must be idempotent.

**Question 7.** If a `StreamingResponseBody` stream returns HTTP 200 and writes 50/100 chunks, can the server change the HTTP status to 503 during drain?

**Answer:** No once headers are committed. You need an application-level integrity/resume/cursor/checksum or job-state contract.

**Question 8.** Why is checking `draining=false` before adding to a concurrent Set insufficient?

**Answer:** Drain can turn on and take its snapshot between the check and the add; you must re-check after adding or synchronize admission with drain.

**Question 9.** In Kubernetes, should you set preStop sleep to 30 seconds when `terminationGracePeriodSeconds` is only 20 seconds?

**Answer:** No. preStop runs **inside the total grace budget**; the pod may be killed before the app receives SIGTERM or finishes cleanup.

**Question 10.** If WebFlux `takeUntilOther(shutdownSignal)` completed the output, does the WebSocket definitely close?

**Answer:** Not necessarily; inbound publishers/lifecycle composition remain. Close/cancel must be composed into the returned Mono or `session.close` properly subscribed.

**Question 11.** If a client reports WebSocket close code 1006, does that mean the server sent close code 1006?

**Answer:** No. 1006 is reserved; the client reports it when the connection closes abnormally without a valid close frame.

**Question 12.** Why can immediate client reconnect upon receiving close 1001 break a deployment?

**Answer:** Thousands of clients reconnecting/re-authing/re-subscribing/replaying simultaneously create a storm. Use backoff+jitter, quotas, and sufficient pod scale.

**Question 13.** If an app emits events from Kafka/RabbitMQ, is closing the WebSocket enough to guarantee payment events aren't lost?

**Answer:** No. You need durable logs, business ACKs/idempotency, consumer offsets, and tenant-scoped replay; WebSocket send is not a business commit.

**Question 14.** When drain is called twice, should it emit terminal events and close all sessions a second time?

**Answer:** No; it should be idempotent. A CAS flag and remove-if-present prevent double effects, while cleanup callbacks may safely execute more than once.

## 21. Official documentation and references

- [Spring Boot 4.1 — Graceful Shutdown](https://docs.spring.io/spring-boot/reference/web/graceful-shutdown.html) — default grace on Tomcat/Jetty/Netty, `timeout-per-shutdown-phase`, and how new requests are rejected.
- [Spring Boot — Actuator Endpoints: Kubernetes Probes and Readiness](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html) — lifecycle, readiness/liveness, shutdown, preStop.
- [Spring Boot 4.1 API — AvailabilityChangeEvent](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/availability/AvailabilityChangeEvent.html) — `publish(ApplicationContext, ReadinessState)`.
- [Spring Boot — Application Properties](https://docs.spring.io/spring-boot/appendix/application-properties/) — server.shutdown, lifecycle timeout, async MVC timeout, Actuator probes.
- [Spring Framework — Asynchronous Requests on Spring MVC](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-async.html) — SseEmitter, ResponseBodyEmitter, StreamingResponseBody, disconnect errors, and Servlet async lifecycle.
- [Spring Framework Javadoc — SseEmitter](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/servlet/mvc/method/annotation/SseEmitter.html).
- [Spring Framework Javadoc — SseEmitter.SseEventBuilder](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/servlet/mvc/method/annotation/SseEmitter.SseEventBuilder.html).
- [Spring Framework — WebSocket on Servlet Stack](https://docs.spring.io/spring-framework/reference/web/websocket/server.html).
- [Spring Framework Javadoc — WebSocketSession](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/socket/WebSocketSession.html).
- [Spring Framework Javadoc — CloseStatus](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/socket/CloseStatus.html).
- [Spring Framework — STOMP WebSocket Events](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/application-context-events.html) — SessionDisconnectEvent and broker state.
- [Spring Framework — WebFlux WebSockets](https://docs.spring.io/spring-framework/reference/web/webflux-websocket.html).
- [Spring Framework — WebFlux Server-Sent Events](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/return-types.html).
- [Spring Boot — Managed Dependencies](https://docs.spring.io/spring-boot/appendix/dependency-versions/coordinates.html) — Boot 4.1.2 WebSocket starter.
- [RFC 6455 — WebSocket Close Control Frame](https://www.rfc-editor.org/rfc/rfc6455).
- [WHATWG HTML — Server-Sent Events / EventSource](https://html.spec.whatwg.org/multipage/server-sent-events.html).
- [Kubernetes — Container Lifecycle Hooks](https://kubernetes.io/docs/concepts/containers/container-lifecycle-hooks/).
- [Kubernetes — Pod Termination](https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/#pod-termination).
- [Reactor — Reactive Streams Cancellation](https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html).
- [OWASP — WebSocket Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/WebSocket_Security_Cheat_Sheet.html).

**Conclusion:** With Spring Boot 4.1, the graceful embedded server **blocks new requests and grants a window for in-flight requests**, yet SSE, WebSocket, and streaming responses may not finish in time on their own. You need **drain-first**: transition readiness, block admission, stop producers, try notifying clients (SSE `server-draining`, WS close `GOING_AWAY/1001`), complete/cancel streams, clean up registries and subscriptions, and only then finalize shutdown within the deadline. Delivery of the final event is always best-effort; correctness must rest on **cursors/replay/ACK/idempotency and durable state**, not just on the TCP/WebSocket closing.
