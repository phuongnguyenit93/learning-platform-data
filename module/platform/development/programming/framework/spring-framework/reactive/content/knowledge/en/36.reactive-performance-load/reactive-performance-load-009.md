# Closing Active Connections and Graceful Application Shutdown in Spring WebFlux

## 1. Goal

A Spring WebFlux application may be processing HTTP requests, SSE streams, WebSockets, message consumers, background tasks, and WebClient calls when the process receives a shutdown signal. If the JVM exits immediately, in-flight requests may be cut off, unacknowledged messages may be reprocessed, WebSocket clients drop unexpectedly, and connection pools are not released in proper order.

**Graceful shutdown** is the process of stopping new work intake, giving in-flight work time to finish, closing long-lived connections per protocol, stopping workers, and releasing resources before the process exits.

This lesson covers:

1. Default graceful shutdown in Spring Boot 3.5 with WebFlux/Reactor Netty.
2. Readiness, in-flight HTTP requests, and shutdown timeouts.
3. Completing SSE streams and closing WebSocket sessions.
4. Stopping background workers, message consumers, Schedulers, and connection pools.
5. Coordinating order with SmartLifecycle and asynchronous callbacks.
6. Sizing termination budgets for Kubernetes/containers.
7. Testing cancellation, cleanup, and SIGTERM.

## 2. Three Lifecycle Levels

| Level | Target | What to Do |
| --- | --- | --- |
| Request | HTTP request/reactive operation | Let running operations complete or time out cleanly |
| Connection | SSE, WebSocket, client/database connections | Send completion signals, close per protocol, release resources |
| Application | ApplicationContext, workers, schedulers, pools, server | Stop new intake, shut down in order, and await callbacks |

An HTTP response finishing does not mean the application has shut down. Conversely, closing a TCP socket does not prove a business transaction committed or a message was acknowledged.

A Flux that does not terminate naturally cannot be awaited forever. It needs an explicit policy: a final SSE event, a WebSocket Close frame, canceling broker subscriptions, or forced closure when the deadline expires.

## 3. Spring Boot 3.5 Graceful Shutdown

Spring Boot supports graceful shutdown out of the box with embedded Reactor Netty, Tomcat, Jetty, and Undertow for both reactive and servlet applications. When ApplicationContext closes, the server stops accepting new requests and grants active requests a grace period to finish.

Explicit configuration:

~~~properties
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=20s
~~~

In Boot 3.5, graceful shutdown is enabled by default for embedded web servers; declaring it explicitly makes intent clear to readers. `spring.lifecycle.timeout-per-shutdown-phase` sets the timeout **per Spring Lifecycle phase**, not the total duration of the entire process.

With Reactor Netty, the server stops accepting new requests at the network layer. Already-accepted requests can continue processing during the grace window. How rejected requests fail can vary by web server and persistent connection state; do not assume every case always returns the exact same HTTP status.

### 3.1. Shutdown Flow

~~~text
Orchestrator sends SIGTERM
          |
          v
Spring ApplicationContext starts closing
          |
          v
Readiness -> REFUSING_TRAFFIC
          |
          v
Application drain
  - reject new work
  - complete SSE
  - close WebSockets
  - stop workers/consumers
          |
          v
Embedded server stops accepting new requests
          |
          v
Wait for in-flight HTTP within grace period
          |
          v
Release custom pools / schedulers / resources
          |
          v
Destroy beans, close context, process exits
~~~

This is the target sequence. Actual order is governed by SmartLifecycle phases and Spring Boot configuration.

### 3.2. SIGTERM and SIGKILL

- SIGTERM asks the process to stop; Spring gets a chance to close ApplicationContext and execute lifecycle callbacks.
- SIGKILL terminates the process immediately without letting Java run cleanup callbacks.
- IDEs or process managers may not always send SIGTERM cleanly.
- Shutdown hooks are not guaranteed to finish if a container hits its termination deadline or power is cut abruptly.

Test the shutdown flow using the exact mechanism used in production.

## 4. Readiness: Stop Receiving Traffic Before Closing Resources

Readiness answers whether an instance is ready to accept traffic. When shutdown starts, Spring Boot transitions state to `REFUSING_TRAFFIC` so infrastructure stops routing new requests to that instance.

Two states:

| ReadinessState | Meaning |
| --- | --- |
| `ACCEPTING_TRAFFIC` | Instance is ready to receive traffic |
| `REFUSING_TRAFFIC` | Instance does not want new traffic |

Spring Boot publishes an AvailabilityChangeEvent when state changes. Readiness can also be updated proactively:

~~~java
AvailabilityChangeEvent.publish(
    eventPublisher,
    this,
    ReadinessState.REFUSING_TRAFFIC
);
~~~

In Kubernetes, readiness lets Services/EndpointSlices remove the terminating Pod from traffic. Endpoint/load-balancer updates take time to propagate; if needed, design a preStop hook or appropriate orchestration mechanism.

Do not use liveness to signal that an instance is draining. Liveness answers whether the process needs restarting because it is unhealthy; readiness answers whether the instance should receive new traffic.

### 4.1. Health Probes

~~~properties
management.endpoint.health.probes.enabled=true
management.endpoints.web.exposure.include=health,info
~~~

Commonly used endpoints:

~~~text
/actuator/health/liveness
/actuator/health/readiness
~~~

During shutdown, readiness may switch to REFUSING_TRAFFIC while the connector is also stopping request acceptance. Do not rely on polling probes continuously after the HTTP connector has closed to determine if the process has exited. The orchestrator should observe container/process state.

Protect Actuator endpoints with network policies and security; expose only required endpoints.

## 5. In-Flight HTTP Requests and the Grace Period

For finite requests, Spring Boot allows already-accepted requests to finish within the grace period. Example:

~~~java
@GetMapping("/work")
public Mono<String> work() {
    return Mono.delay(Duration.ofSeconds(5))
        .map(ignored -> "completed");
}
~~~

If the request started before the server stopped accepting traffic and the operation finishes within the grace period, the client receives the response normally.

If the request takes longer than the grace period, the server/process may exit before the response completes. No setting guarantees infinite requests stay alive forever.

Guidelines:

- Keep request processing finite and bounded by timeouts.
- Set downstream timeouts smaller than the request/shutdown budget.
- Never hold database transactions open inside infinite streams.
- Work that must continue after an HTTP client leaves should become a durable job/message workflow.
- Use idempotency keys when clients retry without knowing if a request committed.
- Never return 200 before the business operation reaches the state promised by the API.

## 6. SSE: Proactively Completing Open Streams

SSE returns `text/event-stream` and keeps the HTTP response open. A publisher like `Flux.interval(Duration.ofSeconds(1))` does not complete on its own. Merely enabling graceful shutdown can force the server to wait until the entire grace period expires.

A clear strategy is emitting a final `shutdown` event and completing. Clients receiving this event can close the EventSource or reconnect to another instance per application policy.

Illustrative wire format:

~~~text
event:shutdown
data:server-restarting

~~~

### 6.1. SseFeed Using Sinks.One

~~~java
@Component
public class SseFeed {
    private final Sinks.One<Boolean> shutdownSignal = Sinks.one();

    public Flux<ServerSentEvent<String>> events() {
        Flux<ServerSentEvent<String>> ticks =
            Flux.interval(Duration.ofSeconds(1))
                .map(sequence ->
                    ServerSentEvent.<String>builder("tick-" + sequence)
                        .id(Long.toString(sequence))
                        .event("tick")
                        .build()
                );

        Mono<ServerSentEvent<String>> shutdownEvent =
            shutdownSignal.asMono()
                .map(ignored ->
                    ServerSentEvent.<String>builder("server-restarting")
                        .event("shutdown")
                        .build()
                );

        return Flux.merge(ticks, shutdownEvent)
            .takeUntil(event -> "shutdown".equals(event.event()));
    }

    public void beginShutdown() {
        shutdownSignal.tryEmitValue(Boolean.TRUE);
    }
}
~~~

`Sinks.One` retains a single shutdown signal for current and late subscribers. Once emitted, the merged Flux receives the shutdown event; `takeUntil` emits the final event, completes the stream, and cancels the interval.

Clients can close EventSource:

~~~javascript
const source = new EventSource("/api/stream");

source.addEventListener("tick", event => {
    console.log("tick:", event.data);
});

source.addEventListener("shutdown", event => {
    console.log("server restarting:", event.data);
    source.close();
});
~~~

If clients should auto-reconnect, omit `source.close()` and design backoff and resume semantics. Avoid letting all clients reconnect simultaneously when multiple Pods restart.

### 6.2. Controller with Drain Gate

~~~java
@RestController
@RequestMapping("/api")
public class StreamController {
    private final SseFeed feed;
    private final DrainCoordinator drain;

    public StreamController(SseFeed feed, DrainCoordinator drain) {
        this.feed = feed;
        this.drain = drain;
    }

    @GetMapping(path = "/stream",
                produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public Flux<ServerSentEvent<String>> stream() {
        if (drain.isDraining()) {
            return Flux.error(new ResponseStatusException(
                HttpStatus.SERVICE_UNAVAILABLE,
                "instance is draining"
            ));
        }
        return feed.events();
    }
}
~~~

The drain gate rejects new SSE requests in the window between when the application starts draining and when the server stops accepting requests at the network layer. In real apps, a WebFilter can enforce this across business routes while letting required readiness/management endpoints keep returning status as long as the connector remains active.

## 7. WebSocket: Managing Active Sessions

WebSockets are long-lived bidirectional connections. The server should maintain a session registry to:

1. Reject new sessions once drain begins.
2. Send a Close frame with an appropriate status.
3. Wait for the close handshake within a bounded timeout.
4. Cancel outbound publishers and release subscriptions/resources.
5. Let clients reconnect with backoff.

Spring WebFlux uses WebSocketHandler and WebSocketSession. `session.receive()` is the inbound Flux; `session.send(...)` writes the outbound publisher. The handler must compose both flows into one unified lifecycle and return a Mono<Void> reflecting when session handling ends.

### 7.1. Close Statuses

| CloseStatus | Code | Meaning |
| --- | ---: | --- |
| `NORMAL` | 1000 | Normal closure |
| `GOING_AWAY` | 1001 | Endpoint is going away, e.g., server shutdown |
| `PROTOCOL_ERROR` | 1002 | Protocol error |
| `POLICY_VIOLATION` | 1008 | Policy violation |
| `SERVER_ERROR` | 1011 | Unexpected server error |
| `SERVICE_RESTARTED` | 1012 | Server is restarting |
| `SERVICE_OVERLOAD` | 1013 | Service overloaded |

The example uses `GOING_AWAY` (1001). If clients understand `SERVICE_RESTARTED`, 1012 can be used with jittered reconnect delays. Never send reserved codes such as 1005 or 1006 in a Close frame.

### 7.2. Thread-Safe Registry

~~~java
@Component
public class WebSocketSessionRegistry {
    private static final Logger log =
        LoggerFactory.getLogger(WebSocketSessionRegistry.class);

    private final ConcurrentMap<String, WebSocketSession> sessions =
        new ConcurrentHashMap<>();

    private final AtomicBoolean draining = new AtomicBoolean();

    public boolean register(WebSocketSession session) {
        if (draining.get()) {
            return false;
        }

        sessions.put(session.getId(), session);

        // Second check to handle race with drain start.
        if (draining.get()) {
            sessions.remove(session.getId(), session);
            return false;
        }
        return true;
    }

    public void remove(String id) {
        sessions.remove(id);
    }

    public int activeCount() {
        return sessions.size();
    }

    public Mono<Void> closeAll() {
        draining.set(true);

        return Flux.fromIterable(sessions.values())
            .flatMap(session ->
                session.close(CloseStatus.GOING_AWAY)
                    .doOnError(error ->
                        log.warn("Cannot close session {}",
                            session.getId(), error)
                    )
                    .onErrorResume(error -> Mono.empty()),
                32
            )
            .then();
    }

    public boolean isDraining() {
        return draining.get();
    }
}
~~~

ConcurrentHashMap supports concurrent access across threads/event loops. The draining flag is set before iterating over sessions. The double-check inside `register` handles handshakes arriving right as shutdown begins.

`closeAll()` closes up to 32 sessions concurrently in the example. Tune concurrency to session counts and server capacity; avoid creating unbounded tasks for hundreds of thousands of sessions.

### 7.3. WebSocketHandler

~~~java
@Component
public class ManagedWebSocketHandler implements WebSocketHandler {
    private static final Logger log =
        LoggerFactory.getLogger(ManagedWebSocketHandler.class);

    private final WebSocketSessionRegistry registry;

    public ManagedWebSocketHandler(WebSocketSessionRegistry registry) {
        this.registry = registry;
    }

    @Override
    public Mono<Void> handle(WebSocketSession session) {
        if (!registry.register(session)) {
            return session.close(CloseStatus.GOING_AWAY);
        }

        Mono<Void> inbound = session.receive()
            .doOnNext(message ->
                log.debug("Received message type={}", message.getType())
            )
            .then();

        Flux<WebSocketMessage> outgoing =
            Flux.interval(Duration.ofSeconds(5))
                .map(sequence ->
                    session.textMessage("heartbeat:" + sequence)
                );

        Mono<Void> outbound = session.send(outgoing);

        return Mono.firstWithSignal(inbound, outbound)
            .doFinally(signal -> registry.remove(session.getId()));
    }
}
~~~

`Mono.firstWithSignal` completes when either inbound or outbound finishes and cancels the other stream. When a client closes the connection, inbound completes and the outbound heartbeat is canceled. When the registry closes the session, the connection closes, inbound terminates, and the handler removes the session from the registry.

This is a lifecycle demo; real apps must authenticate Principals, cap sessions per user, validate messages, serialize outbound sends, and manage broker subscriptions.

### 7.4. Registering the Endpoint

~~~java
@Configuration
public class WebSocketConfiguration {
    @Bean
    HandlerMapping webSocketMapping(ManagedWebSocketHandler handler) {
        SimpleUrlHandlerMapping mapping = new SimpleUrlHandlerMapping();
        mapping.setUrlMap(Map.of("/ws/live", handler));
        mapping.setOrder(-1);
        return mapping;
    }
}
~~~

The endpoint is `/ws/live`. The handler rejects new sessions once the registry is draining.

## 8. SmartLifecycle to Coordinate Draining

`@PreDestroy` suits short synchronous cleanup. When asynchronous cleanup is needed and a Mono must finish, `SmartLifecycle.stop(Runnable callback)` fits better.

Crucial contract: invoke the callback after the bean finishes stopping. Spring's LifecycleProcessor awaits the callback within the phase timeout.

Spring Boot 3.x reserves phases for graceful shutdown: web server stop at `SmartLifecycle.DEFAULT_PHASE - 1024` and graceful wait at `DEFAULT_PHASE - 2048`. Spring stops higher-phase values first. Thus the example places the drain coordinator at `DEFAULT_PHASE - 512` to emit readiness/drain signals and close WebSockets before the server stops.

### 8.1. DrainCoordinator

~~~java
@Component
public class DrainCoordinator implements SmartLifecycle {
    private static final Logger log =
        LoggerFactory.getLogger(DrainCoordinator.class);

    private final ApplicationEventPublisher events;
    private final SseFeed sseFeed;
    private final WebSocketSessionRegistry sessions;

    private final AtomicBoolean running = new AtomicBoolean();
    private final AtomicBoolean draining = new AtomicBoolean();

    public DrainCoordinator(
            ApplicationEventPublisher events,
            SseFeed sseFeed,
            WebSocketSessionRegistry sessions) {
        this.events = events;
        this.sseFeed = sseFeed;
        this.sessions = sessions;
    }

    @Override
    public void start() {
        running.set(true);
    }

    @Override
    public void stop(Runnable callback) {
        if (!running.getAndSet(false)) {
            callback.run();
            return;
        }

        if (!draining.compareAndSet(false, true)) {
            callback.run();
            return;
        }

        AvailabilityChangeEvent.publish(
            events, this, ReadinessState.REFUSING_TRAFFIC
        );

        sseFeed.beginShutdown();

        sessions.closeAll()
            .timeout(Duration.ofSeconds(8))
            .doOnError(error ->
                log.warn("WebSocket drain timed out", error)
            )
            .onErrorResume(error -> Mono.empty())
            .doFinally(signal -> callback.run())
            .subscribe();
    }

    @Override
    public void stop() {
        stop(() -> {});
    }

    @Override
    public boolean isRunning() {
        return running.get();
    }

    @Override
    public boolean isAutoStartup() {
        return true;
    }

    @Override
    public int getPhase() {
        return DEFAULT_PHASE - 512;
    }

    public boolean isDraining() {
        return draining.get();
    }
}
~~~

`stop(Runnable)` runs reactive cleanup and invokes the callback only after `closeAll` completes or times out. Per-session errors are logged; one failing session does not block closing other sessions.

`getPhase()` in the example relies on Spring Boot 3.x's phase arrangement. If the app includes Spring Cloud Stream, custom workers, or other lifecycle beans, coordinate phases by dependency and test ordering when upgrading Boot.

### 8.2. Why Not Block Inside the Stop Callback?

Do not write:

~~~java
sessions.closeAll().block();
~~~

on the event-loop or lifecycle thread without evaluating its impact. The SmartLifecycle contract supplies a callback to signal asynchronous completion. Subscribe to the publisher, handle errors, and invoke the callback exactly once.

Never invoke the callback immediately after `subscribe()`; doing so early lets Spring destroy dependencies while sessions are still closing.

## 9. Background Workers and Message Consumers

Workers have two categories of tasks:

- In-flight work: finish, commit/checkpoint, or return safely for retry.
- New work: stop accepting once draining begins.

The workflow should be:

1. Flip a flag to stop accepting new messages/jobs.
2. Pause the consumer or cancel the upstream subscription.
3. Wait for in-flight count to reach 0.
4. Commit offsets/acks after successful processing.
5. On timeout, let unacknowledged messages be redelivered by the broker or save checkpoints.
6. Invoke the SmartLifecycle callback when the worker stops.

Example contract:

~~~java
public interface DrainableWorker {
    Mono<Void> stopAccepting();
    Mono<Void> awaitInFlight();
}
~~~

A lifecycle bean can compose:

~~~java
worker.stopAccepting()
    .then(worker.awaitInFlight())
    .timeout(Duration.ofSeconds(10))
    .doOnError(error -> log.warn("Worker drain timed out", error))
    .onErrorResume(error -> Mono.empty())
    .doFinally(signal -> callback.run())
    .subscribe();
~~~

This snippet assumes an implemented worker. Never ack messages merely because shutdown started. Ack/commit must obey business semantics. If work does not finish within the grace period, let the broker redeliver and ensure consumers are idempotent.

Never open an infinite Flux inside a database transaction waiting for worker drain. Transactions should stay short and finite.

## 10. Stopping Schedulers and Reactive Resources

Custom Schedulers should be declared as Spring beans and disposed on shutdown:

~~~java
@Bean(destroyMethod = "dispose")
Scheduler workerScheduler() {
    return Schedulers.newBoundedElastic(
        8, 200, "worker-io"
    );
}
~~~

This works for Schedulers with synchronous cleanup. If a Scheduler backs workers that must stop accepting tasks and await running tasks, manage it via SmartLifecycle with a callback and timeout.

Do not call `Schedulers.shutdownNow()` on global Schedulers if the app or other libraries still use them. Dispose only application-owned resources.

For infinite publishers:

- Tie cancellation to lifecycle.
- Use `doFinally` to release subscriptions.
- Never call standalone `subscribe()` without keeping a handle to cancel.
- Ensure canceling a feed cancels the underlying broker subscription.
- Never maintain unbounded queues when consumers stop.

## 11. Closing WebClient Connection Pools

WebClients auto-configured by Spring Boot and built from `WebClient.Builder` can share Reactor Netty resources with the server. This is the recommended mode; Spring manages resource lifecycles.

If you create a custom `ConnectionProvider`, the application owns that resource and must dispose of it at the right time.

~~~java
ConnectionProvider provider =
    ConnectionProvider.builder("downstream")
        .maxConnections(32)
        .pendingAcquireMaxCount(64)
        .pendingAcquireTimeout(Duration.ofSeconds(3))
        .disposeTimeout(Duration.ofSeconds(5))
        .build();

HttpClient httpClient = HttpClient.create(provider);

WebClient client = WebClient.builder()
    .clientConnector(
        new ReactorClientHttpConnector(httpClient)
    )
    .build();
~~~

`ConnectionProvider.dispose()` is fire-and-forget. When you need to observe completion, use `disposeLater()`:

~~~java
provider.disposeLater()
    .doFinally(signal -> callback.run())
    .subscribe();
~~~

Call dispose after in-flight HTTP requests complete. Once a pool begins disposing, new acquires are rejected; pending acquires receive a grace period governed by `disposeTimeout`. Never close the pool while the service still needs it to finish active requests.

Do not manually call `HttpResources.disposeLoopsAndConnections()` if using global Reactor Netty resources shared between server and clients. Disposing global resources can affect all clients using them.

## 12. R2DBC/JDBC and Database Connections

With R2DBC, Spring Boot manages the ConnectionFactory/pool as lifecycle beans. Do not close connections manually per request; transactions/repositories must terminate their publishers so connections return to the pool.

Sequence:

1. Stop accepting new requests/jobs.
2. Wait for active transactions to finish within the grace period.
3. Roll back/cancel remaining live transactions when the deadline expires.
4. Let the pool/ConnectionFactory dispose when bean lifecycle ends.

If you build a custom R2DBC pool, own and dispose that bean. With JDBC DataSource/Hikari, close the DataSource after requests using connections have finished. Never close the database pool in a phase earlier than the phase awaiting in-flight requests.

An uncommitted transaction cannot be treated as successful merely because the client sent a request. If shutdown cuts off the response after DB commit, the client may not know the outcome; APIs with side effects should support idempotency keys or status lookup endpoints.

## 13. Shutdown Order and SmartLifecycle Phases

Spring starts lifecycle beans in ascending phase order and stops them in descending phase order. Higher-phase beans stop earlier.

In Spring Boot 3.x, the graceful shutdown phase arrangement leaves room for applications to participate:

| Relative Phase | Example | Stop Timing |
| --- | --- | --- |
| `DEFAULT_PHASE - 512` | DrainCoordinator | Before web server stop |
| `DEFAULT_PHASE - 1024` | Web server stop | Stop accepting new requests |
| `DEFAULT_PHASE - 2048` | Graceful wait | Wait for active requests |
| `DEFAULT_PHASE - 3072` | Custom outbound pool cleanup | After grace period |

These phases illustrate Boot 3.x integration; check phases of other lifecycle beans. Spring Cloud Stream or consumer lifecycles may need custom phases to stop in proper order.

If a worker must keep serving active requests, do not arbitrarily stop it at a higher phase than the web server. If a worker only consumes background messages and must halt intake before the HTTP server closes, assign explicit phases and test the ordering.

`spring.lifecycle.timeout-per-shutdown-phase` applies per phase. Multiple asynchronous phases can consume more than one timeout interval. Sum your total budget across actual phases that await callbacks.

## 14. Kubernetes and terminationGracePeriodSeconds

Kubernetes enforces a termination window for Pods. When a Pod terminates:

- The preStop hook runs before the TERM signal.
- After preStop, the container runtime sends SIGTERM.
- Spring Boot starts closing ApplicationContext and running graceful shutdown.
- Once `terminationGracePeriodSeconds` expires, kubelet can send SIGKILL.

Example budget configuration:

~~~yaml
spec:
  terminationGracePeriodSeconds: 60
  containers:
    - name: reactive-api
      image: example/reactive-api:1.0
      lifecycle:
        preStop:
          exec:
            command: ["/bin/sh", "-c", "sleep 5"]
~~~

This is an example only. `sleep 5` consumes 5 seconds of the termination budget; use it only when time is needed for endpoints/load balancers to update. In production, a preStop hook can call a protected drain endpoint or coordinate with a service mesh/load balancer.

Budget calculation:

~~~text
terminationGracePeriodSeconds
    >= preStop duration
     + app drain phase
     + web server graceful wait
     + custom resource cleanup
     + safety margin
~~~

For example, 5s preStop, 8s drain, 20s HTTP grace, 5s pool cleanup, and 10s margin require around 48s. Configuring 60s leaves headroom. This is an illustration; measure your service's real shutdown behavior.

With rolling updates, account for readiness propagation, PodDisruptionBudgets, maxUnavailable/maxSurge, and new Pod startup times.

## 15. Client Reconnection

When the server closes WebSockets or SSE during a restart, clients must recognize this as an intentional closure and reconnect with backoff.

### 15.1. WebSocket

Clients should:

- Distinguish close codes 1001/1012 from protocol or authentication errors.
- Reconnect using exponential backoff and jitter.
- Restore subscriptions after the new connection succeeds.
- Send a cursor/last-seen event ID if supported by the protocol.
- Use idempotency keys for commands with side effects.
- Cap reconnect attempts and display offline state.

Do not let every client reconnect instantaneously after the same close frame; that causes a connection storm against surviving instances.

### 15.2. SSE

EventSource has built-in reconnect and can send `Last-Event-ID`. However, the server can replay missed events only if an event log/store exists to query. A `Flux.interval` generating IDs 0, 1, 2 per subscription does not create durable replay on its own.

If a shutdown event announces server restarting, clients can wait with jitter before reopening the stream. If a resume contract exists, the server must inspect `Last-Event-ID` and emit subsequent events per defined semantics.

## 16. Timeouts, Deadlines, and Forced Shutdown

Graceful shutdown is best-effort within a time bound. Completing every operation cannot be guaranteed when dependencies hang, clients stop reading responses, or networks partition.

| Work Type | Policy |
| --- | --- |
| HTTP request | Wait within server grace period |
| SSE | Send shutdown event then complete |
| WebSocket | Close frame, wait bounded handshake |
| Background job | Stop intake, finish or checkpoint |
| Message consumer | Pause, process/ack or leave for redelivery |
| Custom WebClient pool | Dispose after in-flight requests finish |
| Scheduler | Stop task intake, await tasks, dispose |
| DB pool | Dispose after request/transaction drain |

Every cleanup step needs a timeout. If cleanup fails, log the cause, increment metrics, and proceed with shutdown per policy. Never wait forever inside a SmartLifecycle callback.

Distinguish:

- Graceful close: both sides exchange protocol close frames and clean up.
- Timeout close: grace period expires, framework/server forces termination.
- Process kill: JVM gets no chance to run cleanup.

## 17. Logging and Metrics

A solid shutdown process must be observable:

| Metric/Log | Meaning |
| --- | --- |
| `app.shutdown.started` | Timestamp when draining began |
| `app.shutdown.duration` | Total shutdown duration |
| `app.shutdown.phase.duration` | Duration per phase |
| `app.shutdown.timeout` | Count of phases hitting timeout |
| `app.shutdown.inflight.requests` | Requests still running |
| `app.websocket.active` | Open WebSocket sessions |
| `app.websocket.closed.shutdown` | Sessions closed due to shutdown |
| `app.sse.active` | Active SSE subscriptions |
| `app.worker.inflight` | Background tasks running |
| `app.worker.unacked` | Unacked/uncheckpointed messages |
| `app.resource.dispose.errors` | Resource disposal errors |

Logs should include instance ID, deployment version, shutdown reason, phase, elapsed time, remaining request/session counts, and error classes. Never log tokens, cookies, or sensitive message payloads.

Illustrative logs:

~~~text
INFO shutdown.started instance=api-7 reason=SIGTERM
INFO shutdown.readiness state=REFUSING_TRAFFIC
INFO shutdown.websocket closing=12
INFO shutdown.sse event=shutdown active=8
INFO shutdown.http waiting_inflight=3
INFO shutdown.complete durationMs=6420
~~~

These lines are illustrative output, not default Spring Boot logs. Emit such logs/metrics from your application.

## 18. Complete Demo: Spring Boot 3.5.6, Java 17+, WebFlux

The demo includes:

- Finite HTTP requests running during the grace period.
- An SSE stream emitting a shutdown event and completing.
- A WebSocket handler registering active sessions.
- DrainCoordinator updating readiness, closing WebSockets, and stopping SSE.
- Spring Boot stopping the server and waiting for active requests.
- Unit tests for SSE and the WebSocket registry.

### 18.1. Project Structure

~~~text
webflux-graceful-shutdown/
  settings.gradle
  build.gradle
  src/main/java/demo/shutdown/
    ShutdownApplication.java
    SseFeed.java
    StreamController.java
    WebSocketSessionRegistry.java
    ManagedWebSocketHandler.java
    WebSocketConfiguration.java
    DrainCoordinator.java
    LongTaskController.java
  src/main/resources/
    application.properties
  src/test/java/demo/shutdown/
    SseFeedTest.java
    WebSocketSessionRegistryTest.java
~~~

### 18.2. settings.gradle

~~~groovy
rootProject.name = 'webflux-graceful-shutdown'
~~~

### 18.3. build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.6'
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
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Spring Boot dependency management manages versions of Spring Framework, Reactor, and Reactor Netty. Do not manually override Reactor modules to incompatible versions.

### 18.4. application.properties

~~~properties
spring.application.name=webflux-graceful-shutdown
server.port=8080

server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=20s

management.endpoint.health.probes.enabled=true
management.endpoints.web.exposure.include=health,info
~~~

The 20-second grace period is an example. The container's termination grace period must exceed the sum of all phases and preStop.

### 18.5. ShutdownApplication.java

~~~java
package demo.shutdown;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ShutdownApplication {
    public static void main(String[] args) {
        SpringApplication.run(
            ShutdownApplication.class,
            args
        );
    }
}
~~~

### 18.6. SseFeed.java

~~~java
package demo.shutdown;

import java.time.Duration;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.core.publisher.Sinks;

@Component
public class SseFeed {
    private final Sinks.One<Boolean> shutdownSignal = Sinks.one();

    public Flux<ServerSentEvent<String>> events() {
        Flux<ServerSentEvent<String>> ticks =
            Flux.interval(Duration.ofSeconds(1))
                .map(sequence ->
                    ServerSentEvent.<String>builder("tick-" + sequence)
                        .id(Long.toString(sequence))
                        .event("tick")
                        .build()
                );

        Mono<ServerSentEvent<String>> stopping =
            shutdownSignal.asMono()
                .map(ignored ->
                    ServerSentEvent.<String>builder("server-restarting")
                        .event("shutdown")
                        .build()
                );

        return Flux.merge(ticks, stopping)
            .takeUntil(event -> "shutdown".equals(event.event()));
    }

    public void beginShutdown() {
        shutdownSignal.tryEmitValue(Boolean.TRUE);
    }
}
~~~

### 18.7. WebSocketSessionRegistry.java

~~~java
package demo.shutdown;

import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicBoolean;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.socket.CloseStatus;
import org.springframework.web.reactive.socket.WebSocketSession;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Component
public class WebSocketSessionRegistry {
    private static final Logger log =
        LoggerFactory.getLogger(WebSocketSessionRegistry.class);

    private final ConcurrentMap<String, WebSocketSession> sessions =
        new ConcurrentHashMap<>();

    private final AtomicBoolean draining = new AtomicBoolean();

    public boolean register(WebSocketSession session) {
        if (draining.get()) {
            return false;
        }

        sessions.put(session.getId(), session);

        if (draining.get()) {
            sessions.remove(session.getId(), session);
            return false;
        }
        return true;
    }

    public void remove(String id) {
        sessions.remove(id);
    }

    public int activeCount() {
        return sessions.size();
    }

    public Mono<Void> closeAll() {
        draining.set(true);

        return Flux.fromIterable(sessions.values())
            .flatMap(session ->
                session.close(CloseStatus.GOING_AWAY)
                    .doOnError(error ->
                        log.warn("Could not close session {}",
                            session.getId(), error)
                    )
                    .onErrorResume(error -> Mono.empty()),
                32
            )
            .then();
    }

    public boolean isDraining() {
        return draining.get();
    }
}
~~~

### 18.8. ManagedWebSocketHandler.java

~~~java
package demo.shutdown;

import java.time.Duration;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.socket.CloseStatus;
import org.springframework.web.reactive.socket.WebSocketHandler;
import org.springframework.web.reactive.socket.WebSocketMessage;
import org.springframework.web.reactive.socket.WebSocketSession;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Component
public class ManagedWebSocketHandler implements WebSocketHandler {
    private static final Logger log =
        LoggerFactory.getLogger(ManagedWebSocketHandler.class);

    private final WebSocketSessionRegistry registry;

    public ManagedWebSocketHandler(
            WebSocketSessionRegistry registry) {
        this.registry = registry;
    }

    @Override
    public Mono<Void> handle(WebSocketSession session) {
        if (!registry.register(session)) {
            return session.close(CloseStatus.GOING_AWAY);
        }

        Mono<Void> inbound = session.receive()
            .doOnNext(message ->
                log.debug("Received message type={}", message.getType())
            )
            .then();

        Flux<WebSocketMessage> outgoing =
            Flux.interval(Duration.ofSeconds(5))
                .map(sequence ->
                    session.textMessage("heartbeat:" + sequence)
                );

        Mono<Void> outbound = session.send(outgoing);

        return Mono.firstWithSignal(inbound, outbound)
            .doFinally(signal -> registry.remove(session.getId()));
    }
}
~~~

### 18.9. WebSocketConfiguration.java

~~~java
package demo.shutdown;

import java.util.Map;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.HandlerMapping;
import org.springframework.web.reactive.handler.SimpleUrlHandlerMapping;
import org.springframework.web.reactive.socket.WebSocketHandler;

@Configuration
public class WebSocketConfiguration {
    @Bean
    HandlerMapping webSocketMapping(ManagedWebSocketHandler handler) {
        SimpleUrlHandlerMapping mapping = new SimpleUrlHandlerMapping();
        mapping.setUrlMap(Map.<String, WebSocketHandler>of(
            "/ws/live", handler
        ));
        mapping.setOrder(-1);
        return mapping;
    }
}
~~~

### 18.10. DrainCoordinator.java

~~~java
package demo.shutdown;

import java.time.Duration;
import java.util.concurrent.atomic.AtomicBoolean;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.SmartLifecycle;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Mono;

@Component
public class DrainCoordinator implements SmartLifecycle {
    private static final Logger log =
        LoggerFactory.getLogger(DrainCoordinator.class);

    private final ApplicationEventPublisher events;
    private final SseFeed sseFeed;
    private final WebSocketSessionRegistry sessions;

    private final AtomicBoolean running = new AtomicBoolean();
    private final AtomicBoolean draining = new AtomicBoolean();

    public DrainCoordinator(
            ApplicationEventPublisher events,
            SseFeed sseFeed,
            WebSocketSessionRegistry sessions) {
        this.events = events;
        this.sseFeed = sseFeed;
        this.sessions = sessions;
    }

    @Override
    public void start() {
        running.set(true);
    }

    @Override
    public void stop(Runnable callback) {
        if (!running.getAndSet(false)) {
            callback.run();
            return;
        }

        if (!draining.compareAndSet(false, true)) {
            callback.run();
            return;
        }

        AvailabilityChangeEvent.publish(
            events, this, ReadinessState.REFUSING_TRAFFIC
        );

        sseFeed.beginShutdown();

        sessions.closeAll()
            .timeout(Duration.ofSeconds(8))
            .doOnError(error ->
                log.warn("WebSocket drain timed out", error)
            )
            .onErrorResume(error -> Mono.empty())
            .doFinally(signal -> callback.run())
            .subscribe();
    }

    @Override
    public void stop() {
        stop(() -> {});
    }

    @Override
    public boolean isRunning() {
        return running.get();
    }

    @Override
    public boolean isAutoStartup() {
        return true;
    }

    @Override
    public int getPhase() {
        return DEFAULT_PHASE - 512;
    }

    public boolean isDraining() {
        return draining.get();
    }
}
~~~

### 18.11. StreamController.java

~~~java
package demo.shutdown;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;
import reactor.core.publisher.Flux;

@RestController
@RequestMapping("/api")
public class StreamController {
    private final SseFeed feed;
    private final DrainCoordinator drain;

    public StreamController(SseFeed feed, DrainCoordinator drain) {
        this.feed = feed;
        this.drain = drain;
    }

    @GetMapping(path = "/stream",
                produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public Flux<ServerSentEvent<String>> stream() {
        if (drain.isDraining()) {
            return Flux.error(new ResponseStatusException(
                HttpStatus.SERVICE_UNAVAILABLE,
                "instance is draining"
            ));
        }
        return feed.events();
    }
}
~~~

### 18.12. LongTaskController.java

~~~java
package demo.shutdown;

import java.time.Duration;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api")
public class LongTaskController {
    @GetMapping("/work")
    public Mono<String> work(
            @RequestParam(defaultValue = "5") long seconds) {
        if (seconds < 1 || seconds > 15) {
            return Mono.error(
                new IllegalArgumentException(
                    "seconds must be between 1 and 15"
                )
            );
        }

        return Mono.delay(Duration.ofSeconds(seconds))
            .map(ignored -> "completed");
    }
}
~~~

## 19. Unit Tests for SSE and WebSocket Registry

### 19.1. SseFeedTest.java

~~~java
package demo.shutdown;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.time.Duration;
import org.junit.jupiter.api.Test;
import reactor.test.StepVerifier;

class SseFeedTest {
    @Test
    void shutdownEventCompletesAnInfiniteSseFeed() {
        SseFeed feed = new SseFeed();

        StepVerifier.withVirtualTime(feed::events)
            .expectSubscription()
            .thenAwait(Duration.ofSeconds(1))
            .assertNext(event ->
                assertEquals("tick", event.event())
            )
            .then(feed::beginShutdown)
            .assertNext(event -> {
                assertEquals("shutdown", event.event());
                assertEquals("server-restarting", event.data());
            })
            .verifyComplete();
    }

    @Test
    void lateSubscriberReceivesShutdownSignal() {
        SseFeed feed = new SseFeed();
        feed.beginShutdown();

        StepVerifier.create(feed.events())
            .assertNext(event ->
                assertEquals("shutdown", event.event())
            )
            .verifyComplete();
    }
}
~~~

The first test uses virtual time to avoid waiting on real timers. The second test verifies that a subscriber arriving after drain begins still receives the shutdown event from `Sinks.One`.

### 19.2. WebSocketSessionRegistryTest.java

~~~java
package demo.shutdown;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import org.junit.jupiter.api.Test;
import org.springframework.web.reactive.socket.CloseStatus;
import org.springframework.web.reactive.socket.WebSocketSession;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class WebSocketSessionRegistryTest {
    @Test
    void closesActiveSessionsAndRejectsNewOnes() {
        WebSocketSessionRegistry registry =
            new WebSocketSessionRegistry();

        WebSocketSession active = mock(WebSocketSession.class);
        when(active.getId()).thenReturn("session-1");
        when(active.close(CloseStatus.GOING_AWAY))
            .thenReturn(Mono.empty());

        assertTrue(registry.register(active));
        assertTrue(registry.activeCount() == 1);

        StepVerifier.create(registry.closeAll())
            .verifyComplete();

        verify(active).close(CloseStatus.GOING_AWAY);

        WebSocketSession late = mock(WebSocketSession.class);
        when(late.getId()).thenReturn("session-2");

        assertFalse(registry.register(late));
    }
}
~~~

The test verifies that existing sessions are closed with status 1001 and new sessions are rejected after the registry starts draining. This is a registry unit test and does not open real network sockets.

## 20. Running the Demo and Manual Testing

Requires Java 17 and Gradle:

~~~bash
gradle test
gradle bootRun
~~~

### 20.1. In-Flight HTTP Request

Terminal 1:

~~~bash
curl -i "http://localhost:8080/api/work?seconds=10"
~~~

While the request waits, send SIGTERM to the application process on Linux/container. If the grace period is long enough, the response completes normally:

~~~text
HTTP/1.1 200 OK
Content-Type: text/plain;charset=UTF-8

completed
~~~

This is the expected result when the request completes before the grace period expires.

### 20.2. SSE

Another terminal:

~~~bash
curl -N -H "Accept: text/event-stream" \
  http://localhost:8080/api/stream
~~~

Normal events:

~~~text
id:0
event:tick
data:tick-0

id:1
event:tick
data:tick-1

~~~

When the app drains, the stream emits the final event:

~~~text
event:shutdown
data:server-restarting

~~~

After the shutdown event, the response completes and curl exits.

### 20.3. WebSocket

Connect a client to:

~~~text
ws://localhost:8080/ws/live
~~~

The client receives a heartbeat every 5 seconds. When the server stops, the registry sends a Close frame with status 1001 GOING_AWAY.

Browser console:

~~~javascript
const socket = new WebSocket("ws://localhost:8080/ws/live");

socket.onmessage = event => console.log(event.data);

socket.onclose = event => {
    console.log("close code:", event.code);
    if (event.code === 1001) {
        console.log("server is going away; reconnect with backoff");
    }
};
~~~

### 20.4. Readiness

~~~bash
curl -i http://localhost:8080/actuator/health/readiness
~~~

When shutdown starts, readiness flips to unready. Once the server stops accepting requests, the endpoint may no longer be reachable via the HTTP connector.

## 21. Runbook When Shutdown Fails to Complete

| Symptom | Possible Cause | What to Check |
| --- | --- | --- |
| Process killed before callback | Termination grace period too short | preStop + lifecycle phases + margin |
| HTTP requests cut off | Requests exceed grace period | Request/downstream timeouts and p99 |
| SSE holds process open | Flux never completes | Shutdown event/cancellation |
| WebSockets stay open | No session registry management | CloseStatus and registry |
| Workers keep receiving messages | Consumer not paused | Stop intake, in-flight, ack/checkpoint |
| WebClient errors during shutdown | Pool disposed too early | Pool cleanup after request drain |
| Scheduler tasks abandoned | Disposed before tasks finish | Stop intake and await tasks |
| Callback never runs | Error in cleanup chain or forgotten callback | `doFinally` and invoke callback once |
| Shutdown hangs | Cleanup Mono never terminates | Per-resource timeouts |
| Clients reconnect simultaneously | Missing backoff/jitter | Exponential backoff and jitter |
| Unclear DB operation outcome | Response lost after commit | Idempotency keys and status lookup endpoint |
| Kubernetes kills after SIGTERM | Insufficient `terminationGracePeriodSeconds` | Increase budget or shorten cleanup |

Investigation sequence:

1. Confirm whether the process received SIGTERM or SIGKILL.
2. Read shutdown logs and readiness state.
3. Identify which phase failed to invoke its callback.
4. Check in-flight HTTP request count.
5. Check active SSE/WebSocket sessions.
6. Check workers/message consumers and unacked messages.
7. Check connection pools and Schedulers.
8. Compare actual timings against each phase timeout.
9. Adjust policies on the right resource.
10. Retest with slow requests, client disconnects, and slow dependencies.

Do not raise every timeout to huge values without knowing which resource is holding the process. A stream that never completes will still hold the app until the deadline expires.

## 22. Common Anti-Patterns

| Anti-Pattern | Consequence | How to Fix |
| --- | --- | --- |
| Calling `System.exit(0)` directly | Skips lifecycle cleanup | Close ApplicationContext via standard mechanisms |
| Using only `@PreDestroy` for async cleanup | No callback to await publishers | `SmartLifecycle.stop(Runnable)` |
| Blocking indefinitely inside `stop()` | Lifecycle thread stalls | Reactive cleanup with timeouts |
| Invoking callback right after `subscribe` | Destroys dependencies prematurely | Invoke callback when cleanup terminates |
| Closing pools before HTTP drain | In-flight requests lose connections | Place resource phase after grace period |
| Not updating readiness | Load balancer keeps sending traffic | `REFUSING_TRAFFIC` |
| Waiting for `Flux.interval` to complete | Stream never completes | Shutdown signal/cancellation |
| Not tracking WebSocket sessions | Sockets cut abruptly | Registry and Close frames |
| Closing WebSockets with TCP reset | Client lacks closure reason | Appropriate `CloseStatus` |
| Not canceling broker subscriptions | Resources stay alive | `doFinally`/`usingWhen` |
| Acking messages before processing completes | Lost work on kill | Ack after commit, idempotent retry |
| Unbounded queues when consumers stop | Memory grows | Bounded queues and draining |
| One timeout for all resources | One hung dependency eats the whole budget | Per-resource timeouts |
| Disposing global Reactor Netty resources | Affects multiple clients | Dispose only custom providers |
| Reconnecting instantaneously | Connection storm | Backoff + jitter |
| Using readiness as liveness | Orchestrator restarts unnecessarily | Separate readiness and liveness |
| Never testing SIGTERM | Bugs appear only during deploy | Manual/integration shutdown tests |

## 23. Production Checklist

1. Does the embedded server have graceful shutdown enabled?
2. Does `timeout-per-shutdown-phase` match SLAs and container budgets?
3. Does readiness transition to `REFUSING_TRAFFIC` before stopping traffic intake?
4. Do load balancers/service meshes have time to propagate endpoint updates?
5. Do in-flight HTTP requests have finite timeouts?
6. Does SSE emit a shutdown event and complete?
7. Do WebSockets have a registry, close status, and reconnect policy?
8. Do client reconnects use exponential backoff and jitter?
9. Do workers stop intake, drain, and checkpoint?
10. Are messages acked only after successful processing?
11. Do custom Schedulers have explicit lifecycles/disposal?
12. Do custom WebClient `ConnectionProvider`s call `disposeLater` after request drain?
13. Do R2DBC/JDBC pools close only after transactions/requests finish?
14. Does async `SmartLifecycle` stop invoke its callback exactly once?
15. Does cleanup enforce timeouts and log errors?
16. Are metrics exposed for active requests, sessions, workers, and shutdown duration?
17. Is Kubernetes `terminationGracePeriodSeconds` larger than preStop plus all phases?
18. Has SIGTERM been tested in a production-like environment?
19. Have hung dependencies, client disconnects, and exhausted pools been tested?
20. Are idempotency/recovery paths in place for interrupted business operations?

## 24. Review Questions and Answers

**Question 1. What does Spring Boot graceful shutdown do?**

Stops accepting new requests and grants in-flight requests a grace period to finish before stopping the server.

**Question 2. Is `server.shutdown=graceful` the default in Boot 3.5?**

Yes for embedded web servers; declaring it explicitly still makes configuration clear.

**Question 3. Is `timeout-per-shutdown-phase` the total shutdown duration?**

No. It applies per lifecycle phase; total duration can be longer.

**Question 4. Why must readiness switch to `REFUSING_TRAFFIC`?**

So orchestrators/load balancers stop routing new requests to the draining instance.

**Question 5. Why does SSE need its own policy?**

SSE streams may not complete naturally. The server should emit a shutdown event and complete or cancel the publisher.

**Question 6. What code does `CloseStatus.GOING_AWAY` have?**

1001, used when an endpoint is going away, such as during server shutdown.

**Question 7. What should a WebSocketHandler do when a session closes?**

Inbound completes and outbound is canceled; the handler composes both streams and releases registry/subscriptions in `doFinally`.

**Question 8. What does `SmartLifecycle.stop(Runnable)` use the callback for?**

To notify Spring that asynchronous stop processing has finished and it may advance to the next phase.

**Question 9. Why not invoke the callback immediately after `subscribe`?**

Cleanup has not finished yet; Spring may destroy dependencies while sessions/workers are still active.

**Question 10. When should `ConnectionProvider.disposeLater()` be used?**

When the application owns a custom Reactor Netty pool and needs a Mono to observe/await disposal.

**Question 11. Should you dispose global `HttpResources` when shutting down a custom WebClient?**

No. Global resources may be shared across multiple clients/servers; dispose only application-owned resources.

**Question 12. When should a message consumer ack?**

After the business operation processes and commits per broker semantics; if unfinished, leave it for safe retry/redelivery.

**Question 13. Why are exponential backoff and jitter needed?**

To prevent many clients from reconnecting simultaneously and causing a connection storm.

**Question 14. What must `terminationGracePeriodSeconds` account for?**

preStop duration, app drain, web server grace period, custom resource cleanup, and a safety margin.

**Question 15. Does SIGKILL run `@PreDestroy`?**

No. SIGKILL terminates the process immediately without letting the JVM run shutdown hooks or lifecycle callbacks.

## 25. Summary and Official Documentation

- Spring Boot graceful shutdown stops accepting new requests and awaits in-flight HTTP requests within the grace period.
- Readiness should switch to `REFUSING_TRAFFIC` so infrastructure stops routing new traffic.
- SSE needs a shutdown event/completion; WebSockets need a close handshake and session registry.
- `SmartLifecycle.stop(Runnable)` supports asynchronous cleanup and awaiting a callback.
- Background workers must stop intake, drain in-flight tasks, and ack/checkpoint according to business semantics.
- Custom WebClient `ConnectionProvider` instances should be disposed after request drain; do not dispose global Reactor Netty resources.
- Every cleanup step needs a timeout; container deadlines must exceed total shutdown budgets.
- Clients need reconnect backoff/jitter and idempotency for commands with side effects.
- Test with real SIGTERM, not just unit tests on lifecycle methods.

References:

1. [Spring Boot 3.5 — Graceful Shutdown](https://docs.spring.io/spring-boot/3.5/reference/web/graceful-shutdown.html): embedded servers, grace period, and timeout per phase.
2. [Spring Boot 3.5 — Actuator Endpoints, Application Lifecycle and Probe States](https://docs.spring.io/spring-boot/3.5/reference/actuator/endpoints.html): readiness/liveness during shutdown.
3. [Spring Boot 3.5 — Application Events and Availability](https://docs.spring.io/spring-boot/3.5/reference/features/spring-application.html): AvailabilityChangeEvent and readiness state.
4. [Spring Framework 6.2 — SmartLifecycle and Bean Lifecycle](https://docs.spring.io/spring-framework/reference/6.2/core/beans/factory-nature.html): phase ordering, stop callbacks, and timeouts.
5. [Spring Framework 6.2 — WebFlux WebSockets](https://docs.spring.io/spring-framework/reference/6.2/web/webflux-websocket.html): WebSocketHandler, receive/send, and session lifecycle.
6. [Spring Framework 6.2 — WebFlux CloseStatus Javadoc](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/web/reactive/socket/CloseStatus.html): close codes 1000, 1001, 1012, and other statuses.
7. [Reactor Netty — HTTP Client Connection Pool](https://projectreactor.io/docs/netty/release/reference/http-client.html): dispose, disposeLater, disposeTimeout, and custom ConnectionProvider.
8. [Spring Boot 3 Migration Guide — Updated Graceful Shutdown Phases](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.0-Migration-Guide#updated-phases-for-graceful-shutdown): graceful shutdown phase ordering and web server.
9. [Spring Boot 3.5 — Reactive Web Applications](https://docs.spring.io/spring-boot/3.5/reference/web/reactive.html): WebFlux and Reactor Netty resources.
10. [Kubernetes — Container Lifecycle Hooks](https://kubernetes.io/docs/concepts/containers/container-lifecycle-hooks/): preStop, SIGTERM, and termination grace period.
