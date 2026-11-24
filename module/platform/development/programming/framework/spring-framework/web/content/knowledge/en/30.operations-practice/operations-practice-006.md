# Resource Limits, Timeouts, Disconnects, and Graceful Shutdown in Spring Web

## 1. Goal: keep the system behaving properly under overload and severed connections

An HTTP endpoint does not just need to return JSON during normal traffic. In operations, the system also has to handle cases where:

- There are more concurrent requests than threads, connections, or sessions the server can handle.
- A client sends an oversized request, uploads large files, or holds a connection slowly.
- An HTTP call to another service stalls or drops; a seemingly small request holds a worker too long.
- A browser closes a tab, a mobile client loses network, or a reverse proxy hits its idle timeout while the server is still working.
- A pod/process receives a stop signal to deploy a new version while requests are still in flight.
- A long-lived SSE or WebSocket stream needs to terminate and release resources when the client disappears.

Four areas must work together: **resource limits**, **timeouts**, **disconnect/cancellation**, and **graceful shutdown**. The safe fix is not simply raising thread counts, timeouts, or allowing unlimited uploads: those changes can shift bottlenecks from the HTTP layer into the database, memory, thread pools, or downstream services.

This lesson primarily uses **Spring Boot 3.5.x, Spring Framework 6.2.x, Java 17+**. It distinguishes **Spring MVC on Servlet/Tomcat** from **Spring WebFlux on Reactor Netty** where properties or lifecycles differ. Configuration numbers are illustrative for learning; measure under load and tune for your real infrastructure.

### Request path model

~~~text
Client/browser/mobile
       |
  Load balancer / ingress / reverse proxy
       |     (max request, keep-alive, idle timeout)
       v
  HTTP listener (Tomcat / Reactor Netty)
       |     (connections, backlog, event loop / worker threads)
       v
  DispatcherServlet (MVC) or DispatcherHandler (WebFlux)
       |     (request body, codec, memory, validation)
       v
  Controller + business work
       |     (concurrency, queues, CPU, cancellation)
       +----> DB connection pool
       |
       +----> RestClient / WebClient -> remote API
       |           (connect, read, response, total timeout)
       v
  HTTP response / stream
       |
       v
  Client still connected or disconnected
~~~

Even a single unbounded layer can overload the system while all other layers are sensibly configured.

## 2. Resource limits: which resources need bounds?

| Resource | Risk | Common control points |
| --- | --- | --- |
| HTTP connections | Too many sockets, file descriptors, idle connections held open | Tomcat/Netty, ingress, OS |
| In-flight requests | Threads or CPU held until exhausted | Worker pool, semaphore, bulkhead |
| Waiting queues | Unbounded latency, out-of-memory | Executor queue, connection accept backlog, admission control |
| HTTP headers | Oversized headers consume memory or invite abuse | server.max-http-request-header-size, proxy |
| Request body / upload | Disk/memory exhaustion from storing huge payloads | Multipart limits, codec limits, proxy, file storage |
| JSON body | Decoder buffers large payloads in RAM | WebFlux codec maxInMemorySize, streaming design |
| WebSocket/SSE sessions | Sockets and outbound buffers held long-term | Session limits, timeout/heartbeat, subscriber policy |
| DB connections | Threads queuing for DB, cascading failures | Connection pool max size and query timeout |
| Outbound HTTP client | Too many downstream connections, retry storms | HTTP pool, pending-acquire, concurrency limit |
| File/temp buffers | Temp disk exhaustion, resource leaks | Temp directory quota, multipart cleanup, lifecycle |

**Defense in depth across layers**: even if ingress blocks huge uploads, the application should still enforce its own limits. If the application caps concurrent business operations at 20, the HTTP server still needs connection/thread caps and outbound HTTP clients need bounded pools.

### 2.1 Tomcat with Spring MVC

An illustrative configuration in **src/main/resources/application.properties**:

~~~properties
# Spring MVC uses embedded Tomcat in starter-web.
server.tomcat.threads.max=80
server.tomcat.max-connections=400
server.tomcat.accept-count=100

# HTTP request headers and multipart upload.
server.max-http-request-header-size=16KB
spring.servlet.multipart.max-file-size=5MB
spring.servlet.multipart.max-request-size=6MB

# Time to keep idle connections open or wait for the client to send the request line.
server.tomcat.keep-alive-timeout=20s
server.tomcat.connection-timeout=10s
~~~

Specific meanings:
- **threads.max** caps traditional Tomcat worker threads. This is not an exact cap on total app requests when async requests, virtual threads, background jobs, or side effects are involved.
- **max-connections** caps connections handled concurrently by the server; HTTP keep-alive can keep a connection open even when no request is executing.
- **accept-count** bounds the OS/accept backlog when request-accepting resources are saturated; it is not a transactional business queue.
- **max-http-request-header-size** protects request headers, not whole file uploads; accounting differs between Tomcat and Netty.
- **max-file-size/max-request-size** govern Servlet multipart parsing; they do not directly apply to WebFlux multipart or generic application/json.
- **connection-timeout** and **keep-alive-timeout** belong to connection/HTTP parsing stages; they do not set a deadline on slow business methods.
- When using Java 21+ **virtual threads** with supporting config, Tomcat's threads.max may not behave like a classic thread pool. This exercise uses Java 17 and regular worker threads.

Settings that are too low can reject valid requests; settings that are too high can push excess load onto the DB/CPU and stretch tail latency. Raising multiple settings at once without measuring makes bottlenecks harder to pinpoint.

### 2.2 WebFlux and codec limits

In Spring WebFlux, many HTTP connections can be served by a few event-loop threads; **never block the event loop** with Thread.sleep, synchronous JDBC, or long CPU work. Reactive Streams provide backpressure, yet do not automatically cap total JSON size, concurrent subscriptions, or total lifetime of every stream.

Example customizing decode buffer limits in a WebFlux server:

~~~java
@Configuration
public class WebFluxCodecConfig implements WebFluxConfigurer {
    @Override
    public void configureHttpMessageCodecs(ServerCodecConfigurer configurer) {
        configurer.defaultCodecs().maxInMemorySize(256 * 1024);
    }
}
~~~

Imports needed in the fragment:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.http.codec.ServerCodecConfigurer;
import org.springframework.web.reactive.config.WebFluxConfigurer;
~~~

**maxInMemorySize** bounds the data a decoder buffers for a single object/chunk depending on the codec. For an NDJSON stream, the limit can apply per decoded record; it is **not a total byte limit across every response**. Exceeding a codec limit can throw **DataBufferLimitException**. Do not raise it to hundreds of MB just to accommodate an inappropriate decoding model.

For WebFlux multipart, **non-file part** limits, disk-spill thresholds for file parts, max disk usage, and max part counts are distinct concepts. Example Spring Boot 3.5 properties:

~~~properties
spring.webflux.multipart.max-in-memory-size=256KB
spring.webflux.multipart.max-disk-usage-per-part=20MB
spring.webflux.multipart.max-parts=20
~~~

Verify against your exact Boot version and multipart reader. If your app uses Servlet multipart instead of WebFlux, configure **spring.servlet.multipart.***. Ensure temp directories are bounded and cleaned up; codec limits do not replace antivirus scanning, file-type validation, account quotas, or storage policies.

### 2.3 Shedding load at the business layer with a semaphore/bulkhead

HTTP connection counts do not reflect business resource cost: one request hitting the DB 5 times can cost more than hundreds of static requests. Place a concurrency limit around the protected work and fail fast when no slots remain:

~~~java
private final Semaphore permits = new Semaphore(8, true);

@GetMapping("/process")
public ResponseEntity<?> process() {
    if (!permits.tryAcquire()) {
        return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
            .header(HttpHeaders.RETRY_AFTER, "1")
            .build();
    }

    try {
        return ResponseEntity.ok(service.performWork());
    } finally {
        permits.release();
    }
}
~~~

The fragment belongs in a controller with an injected **service** and matching Spring/Java imports. **tryAcquire()** does not wait, enabling fast rejection instead of queuing requests indefinitely. **finally** guarantees the permit is released even if the business method throws. Use **503 Service Unavailable** appropriately for system-wide overload; **429 Too Many Requests** usually fits caller/rate policies. Choose status and Retry-After per contract.

**Scope warning:** an in-JVM semaphore limits only that single instance. Across multiple pods, cluster-wide limits require coordination via a load balancer/quota or distributed limiter. Never assume 8 permits per pod means 8 operations cluster-wide.

## 3. Timeouts are a family of mechanisms, not a single knob

| Timeout/deadline | Measured from | When expired | Where configured |
| --- | --- | --- | --- |
| TCP connect timeout | Connection establishment start | Fails to connect | HTTP client connector |
| Connection-pool acquire timeout | Waiting to borrow a pool connection | No slot obtained | HTTP client pool |
| Read/response timeout | Waiting for response/data per connector | Closes/cancels outbound request, error signal | RestClient/WebClient connector |
| Total business deadline | Operation start to deadline | Cancels or times out the whole chain | Business layer, Reactor timeout, request context |
| Servlet async timeout | Async request starts | Spring/Servlet dispatches timeout error | spring.mvc.async.request-timeout, DeferredResult |
| Idle/keep-alive timeout | Connection idle with no requests/bytes | Connection may close | Tomcat/Netty, proxy |
| Proxy upstream timeout | Gateway waiting on backend | Gateway may return 504 or close | Reverse proxy/ingress |
| Graceful shutdown timeout | Application starts shutting down | Waiting phase for completion ends | spring.lifecycle.timeout-per-shutdown-phase |

**Never conflate timeouts**: **server.tomcat.connection-timeout=10s** does not mean an API is allowed at most 10s to run. **spring.mvc.async.request-timeout=10s** does not automatically bound all synchronous controller methods. **WebClient responseTimeout(2s)** is an HTTP client policy, distinct from the total deadline across 5 business steps.

If a browser has a 3-second deadline while an API calls three services sequentially with 10-second read timeouts each, responses arrive far too late. Budget time from the outside in:

~~~text
Client deadline (e.g. 5s)
        |
Gateway deadline (e.g. 4.5s)
        |
API business budget (e.g. 4s)
        |
DB + downstream calls + serialization
        |
Margin for writing response/cleanup
~~~

The numbers illustrate the relationship only; account for network latency and queuing time. Propagating a **total deadline** down to child calls is better than giving every call an independent timeout with no regard for remaining budget.

## 4. Timeouts for synchronous RestClient

With **RestClient** using JDK HttpClient (Java 17), configure connect timeout on HttpClient and read timeout on **JdkClientHttpRequestFactory**:

~~~java
import java.net.http.HttpClient;
import java.time.Duration;

import org.springframework.http.client.JdkClientHttpRequestFactory;
import org.springframework.web.client.RestClient;

HttpClient jdkClient = HttpClient.newBuilder()
    .connectTimeout(Duration.ofSeconds(2))
    .build();

JdkClientHttpRequestFactory factory =
    new JdkClientHttpRequestFactory(jdkClient);
factory.setReadTimeout(Duration.ofSeconds(4));

RestClient client = RestClient.builder()
    .baseUrl("https://catalog.example.org")
    .requestFactory(factory)
    .build();
~~~

This is a **configuration fragment**, requiring a real remote server when invoked. **connectTimeout** governs TCP establishment; **setReadTimeout** on this factory sets the HTTP request timeout for requests it creates (fitting Spring 6.2). Other HTTP clients such as Apache HttpComponents or Jetty have their own APIs for pool lease, connect, and response timeouts: do not copy properties blindly between them.

On synchronous servlet threads, a hanging RestClient call holds a Tomcat worker. Thus **every significant outbound call should have a finite, observable timeout** aligned with SLA. Handle failures via exception mapping; never auto-retry POSTs with side effects blindly.

### Multi-step business timeout

Suppose a workflow queries both profile and inventory. With a 3-second total budget, do not give each sequential call 3 seconds. One design pattern passes an **Instant deadline** or **Duration remainingBudget** down to client methods and clamps the timeout for the next step. For blocking calls, cancelling execution requires cooperative interrupt/cancel support from client and service; **Future.cancel(true)** is a cooperative interrupt request, not a guarantee that all I/O stops instantaneously.

**Avoid** spawning a new Thread or unbounded ExecutorService per request just to "force a timeout." That merely moves still-running work off the request thread, complicating shutdown and leaks.

## 5. Timeouts for WebClient using Reactor Netty

With WebClient, you can configure the HTTP client connector:

~~~java
import java.time.Duration;

import io.netty.channel.ChannelOption;
import reactor.netty.http.client.HttpClient;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;

HttpClient httpClient = HttpClient.create()
    .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 2000)
    .responseTimeout(Duration.ofSeconds(4));

WebClient webClient = WebClient.builder()
    .baseUrl("https://catalog.example.org")
    .clientConnector(new ReactorClientHttpConnector(httpClient))
    .build();
~~~

**CONNECT_TIMEOUT_MILLIS** bounds connection establishment. Reactor Netty's **responseTimeout** applies to receiving the response and does not guarantee all pre/post-network logic and DB operations finish within one total deadline.

When a timeout is needed across the **entire reactive pipeline**:

~~~java
Mono<Book> result = webClient.get()
    .uri("/api/books/{id}", 7)
    .retrieve()
    .bodyToMono(Book.class)
    .timeout(Duration.ofSeconds(5));
~~~

**Book** is an app-defined DTO. Reactor's **timeout** emits an error if the source fails to signal in time per operator semantics; subscription cancellation can propagate down to the HTTP connector and stop I/O. However, blocking tasks spun outside the reactive pipeline may not stop automatically. For multi-element **Flux**, the timeout operator typically watches intervals between signals rather than acting as an absolute start-to-finish deadline; if you need a fixed total deadline, design an explicit deadline.

### Pools and connection saturation

Default WebClient can share Reactor Netty resources (event loops, connection pools). Under high load, monitor **active/idle/pending connections**, acquire latency, and timeouts. When creating a custom **ConnectionProvider** with **maxConnections**, **pendingAcquireMaxCount**, and **pendingAcquireTimeout**, use a sensible singleton/shared provider and dispose of it with the application lifecycle. Never allocate a new connection pool per request.

An outbound failure from pool acquire timeout differs from a DNS/connect timeout and from a response timeout. That distinction tells you whether to resize the pool, shed traffic, speed up downstream, or add capacity.

## 6. Spring MVC: timeouts in asynchronous requests

Spring MVC offers Servlet async processing via **Callable<T>**, **DeferredResult<T>**, **WebAsyncTask<T>**, **SseEmitter**, and **ResponseBodyEmitter**. It frees the servlet thread while waiting for results, though work may still run on an executor and streaming writes remain blocking I/O.

Default async request timeout configuration:

~~~properties
spring.mvc.async.request-timeout=10s
~~~

This property applies to **Servlet MVC asynchronous request processing**, not regular synchronous controllers or WebFlux. If unset, the default timeout depends on the Servlet container/implementation.

Example operation with **DeferredResult** and a timeout callback:

~~~java
@GetMapping("/async")
public DeferredResult<ResponseEntity<String>> async() {
    DeferredResult<ResponseEntity<String>> result =
        new DeferredResult<>(3_000L);

    result.onTimeout(() -> result.setErrorResult(
        new ResponseStatusException(
            HttpStatus.GATEWAY_TIMEOUT, "Upstream too slow")));

    service.startAsyncWork(result);
    return result;
}
~~~

The snippet above is an **illustrative fragment** with an app-defined **service**. **startAsyncWork** must complete via **setResult(...)** or **setErrorResult(...)**; do not block waiting synchronously inside the controller. On DeferredResult timeout, setting an error result triggers a Spring async dispatch to handle the error. The **onCompletion** callback is well suited for releasing related data/registrations, though it does not automatically cancel background tasks instantly.

With **Callable**, you can use **WebAsyncTask<T>** to set a per-request timeout; also supply a proper **AsyncTaskExecutor**. Spring MVC documentation warns that the default async executor is unsuitable for production under load; configure a bounded pool with clear backpressure if async methods are used heavily.

### Does a timeout actually cancel the work?

Not by default. An expired DeferredResult only finishes the HTTP-facing lifecycle; if you started a blocking DB call or an unlinked future, it can keep running. Design cancellation tokens, query timeouts, and task interruption across layers, and ensure resource cleanup in finally/onCompletion. Never leave thousands of "orphaned" jobs running after clients have left.

## 7. Detecting client disconnects in Spring MVC

**The Servlet API does not provide an instant, reliable signal for every client disconnect scenario.** Especially with response streams/SSE, the server often discovers a disconnect only when attempting to write bytes to the socket and failing. A browser closing a tab does not guarantee an in-progress synchronous controller immediately receives an exception.

With **SseEmitter**, you can register callbacks:

~~~java
SseEmitter emitter = new SseEmitter(30_000L);

emitter.onCompletion(() -> {
    // Drop subscription, release stream resources.
});

emitter.onTimeout(() -> {
    // Mark stream as timed out, clean up related data.
});

emitter.onError(error -> {
    // Record appropriate metrics; avoid infinitely repeated stack traces.
});
~~~

The code above is a **fragment** of **org.springframework.web.servlet.mvc.method.annotation.SseEmitter**. When emitting over time, send periodic SSE heartbeat comments to detect departed clients and avoid idle timeouts:

~~~java
emitter.send(SseEmitter.event().comment("heartbeat"));
~~~

Send calls must run inside streaming logic with a clear lifecycle, handling **IOException** properly. According to the Spring MVC reference, if **ResponseBodyEmitter/SseEmitter.send(...)** throws IOException because the client left, the servlet container triggers error notification and Spring handles completion; the application does not need to call **complete()** or **completeWithError()** inside catch IOException. Never keep emitters in a collection without removal to avoid memory leaks.

A subscription management pattern:

~~~text
Open SSE: create emitter + register onCompletion/onTimeout/onError
        |
Subscribe to event source
        |
Emit data or periodic heartbeat
        |
Write error / timeout / disconnect / server shutdown
        |
Stop subscription, remove emitter from registry, clean up tasks
~~~

**Heartbeats** are not a guarantee of detecting disconnects in every network state; they enable detection via I/O. With many SSE users, balance heartbeat frequency between fast detection and overhead.

## 8. WebFlux: cancellation, DataBuffer, and reactive resources

In WebFlux, the publisher returned to the framework represents the response lifecycle:

~~~java
@GetMapping(value = "/events",
            produces = MediaType.TEXT_EVENT_STREAM_VALUE)
public Flux<ServerSentEvent<String>> events() {
    return eventSource.stream()
        .map(item -> ServerSentEvent.<String>builder()
            .data(item)
            .build())
        .doFinally(signal -> {
            // signal can be CANCEL, ON_COMPLETE, or ON_ERROR.
            metrics.recordTermination(signal.name());
        });
}
~~~

The example is a **fragment**: it needs defined/injected **eventSource** and **metrics**, and imports **Flux**, **ServerSentEvent**, **MediaType**, **@GetMapping**. If the client disconnects, cancelling the subscription can produce **SignalType.CANCEL** in the publisher chain. **doFinally** fits metrics and cleanup; do not treat **CANCEL** as a business error or try to write another HTTP response after the socket is gone.

Key considerations:
- **Publisher cancellation** must propagate to the upstream/resource owner. If you called **subscribe()** manually inside the controller, the framework cannot manage that subscription; return the Flux/Mono instead.
- When handling **DataBuffer** directly, follow its lifecycle: consume, forward, or release buffers via the proper APIs, especially with pooled Netty buffers. Avoid retaining DataBuffers beyond the request.
- Unbounded **collectList()**, **cache()**, and **buffer()** on long-lived streams cause RAM growth; use per-item processing and bounded operators.
- **Thread.sleep**, synchronous JDBC, and long blocking operations on the Netty event loop impact every connection on that loop. If integrating a blocking API is unavoidable, offload carefully via **Schedulers.boundedElastic()** with concurrency limits; do not treat offloading as a permanent substitute for proper async APIs.
- A closed client connection does not automatically cancel background work submitted to an executor; manage task lifecycles and deadlines in the layer owning that work.

### Large response bodies

If an endpoint returns millions of records, do not return **Mono<List<BigRecord>>** holding everything while cranking maxInMemorySize up without bound. Where the contract permits, design NDJSON/SSE streaming or pagination, bounding each item's size. If a single huge JSON array is mandatory, analyze buffering, time-to-first-byte, and memory bounds across codecs, server, and clients.

## 9. Graceful shutdown: how does stopping cleanly differ from killing the process?

**Graceful shutdown** grants in-flight requests a window to complete while the server stops accepting new requests. In Spring Boot **3.5**, graceful shutdown is **enabled by default** for embedded Tomcat, Jetty, Reactor Netty, and Undertow; it can be declared explicitly for clarity:

~~~properties
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=20s
~~~

Spring performs shutdown when **ApplicationContext closes**, in an early phase of stopping **SmartLifecycle** beans. The configured duration is the **grace period per lifecycle phase**, not a blanket "request timeout = 20s." Once the wait window expires, the framework proceeds with shutdown, so longer-running work may not finish.

### Pod deployment timeline

~~~text
T0: orchestrator asks instance to stop (SIGTERM)
      |
      +--> Load balancer/ingress must stop routing new traffic
      |
      +--> Spring ApplicationContext begins closing
              |
              +--> web server graceful shutdown:
              |       stops accepting new requests per server behavior
              |       waits for in-flight requests within grace window
              |
              +--> SmartLifecycle beans and other resources stop
              |
              +--> close data sources / HTTP client pools / executors
      |
T_deadline: shutdown grace expires or external system forces termination
      |
      v
Container/process terminates
~~~

How new requests are rejected depends on the server: Tomcat, Jetty, and Reactor Netty typically stop accepting at the network layer; Undertow can return **503** during shutdown. Do not write tests expecting **every server to return HTTP 503** during graceful shutdown.

**SIGKILL**, process crashes, power loss, forced JVM kills, or container termination-grace expiration give the app no chance to finish cleanup. In an IDE, the Stop button may terminate immediately depending on how it sends signals. Thus graceful shutdown is **best effort with a deadline**, not a guarantee that every workflow completes or an exactly-once promise.

### Coordinating with the orchestrator

In Kubernetes or similar orchestrators:
- Set readiness to false and stop routing new traffic to the draining instance.
- Account for propagation delays in endpoint updates/proxies; requests may still be in transit.
- Set **terminationGracePeriodSeconds** larger than or sufficient to cover Spring's graceful shutdown window, resource cleanup, container stop, and safety margin.
- Align request timeouts, downstream budgets, and the shutdown window. If legitimate requests can run 2 minutes while grace is 20 seconds, those requests risk being cut off.
- For long-lived SSE/WebSocket streams, implement policies to request reconnects or close cleanly; waiting forever on infinite streams prevents graceful windows from completing cleanly.
- If work must survive restarts, persist to a durable job queue/database so another instance can resume; never keep critical state solely in memory.

A pod "closing its port" does not mean background jobs finished or transactions committed. Store work state in durable storage and design proper idempotency/transaction boundaries.

## 10. Shutting down app-managed executors and resources

Spring manages lifecycles for many beans and the embedded server, yet if the app creates its own ExecutorService, scheduled tasks, client connectors, file handles, or message consumers, an owner must clean them up.

Example **ThreadPoolTaskExecutor** with bounded threads/queue:

~~~java
@Configuration
public class WorkerPoolConfig {
    @Bean("workExecutor")
    public ThreadPoolTaskExecutor workExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(20);
        executor.setThreadNamePrefix("work-");
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(15);
        return executor;
    }
}
~~~

Imports: **org.springframework.context.annotation.Bean**, **Configuration**, **org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor**.

- **core/max pool size** bounds workers; **queueCapacity** bounds pending tasks.
- When pool/queue saturate, the executor can reject tasks; callers must handle **TaskRejectedException** or matching policy rather than silently accepting work.
- **waitForTasksToCompleteOnShutdown(true)** tells the executor to wait for active/queued tasks on close, though it does not by itself guarantee enough time across the whole shutdown and other beans.
- **awaitTerminationSeconds(15)** caps how long the executor waits during shutdown; balance it with Spring's lifecycle shutdown budget and the orchestrator deadline.
- If work runs indefinitely or ignores interruption, shutdown can still drag out or expire. Design tasks with deadlines, cancellation, and checkpoints; use durable queues when losing tasks is unacceptable.

This snippet is a **configuration fragment** that can be placed into a Spring Boot app. Do not add an executor like this unless the app genuinely needs async processing. In a pure non-blocking WebFlux controller, do not wrap every call in a thread pool without justification.

### Cancelling subscriptions and consumers

A background WebSocket/SSE subscription or message consumer needs logic to **stop requesting more work**, cancel subscriptions, close file/network resources, and drain in-flight messages before shutting down completely. With Reactive Streams, hold the **Disposable** or manage publisher lifecycles in a component with clear ownership; call **dispose()** on stop and ensure close/rollback on cancel. Never store subscriptions in static fields without cleanup.

## 11. Runnable demo: limiting concurrent work and graceful shutdown (Spring MVC)

This Java 17 demo uses Spring Boot 3.5.0, embedded Tomcat, and a **Semaphore** allowing at most **two business operations executing concurrently** within the JVM. If another request arrives while both permits are held, the server returns **503 + Retry-After: 1**. Requests with excessive simulated duration are rejected with 400 before acquiring a permit. Shutdown is handled by Spring Boot via **server.shutdown=graceful**.

Directory structure:

~~~text
resource-limits-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/
    │   │   ├── ResourceLimitsApplication.java
    │   │   └── WorkController.java
    │   └── resources/application.properties
    └── test/java/demo/WorkControllerTest.java
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
  <artifactId>resource-limits-demo</artifactId>
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
      <artifactId>spring-boot-starter-test</artifactId>
      <scope>test</scope>
    </dependency>
  </dependencies>
</project>
~~~

**src/main/java/demo/ResourceLimitsApplication.java**:

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ResourceLimitsApplication {
    public static void main(String[] args) {
        SpringApplication.run(ResourceLimitsApplication.class, args);
    }
}
~~~

**src/main/java/demo/WorkController.java**:

~~~java
package demo;

import java.util.concurrent.Semaphore;

import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
public class WorkController {

    // Limits business work within this instance only.
    private final Semaphore slots = new Semaphore(2, true);

    public record WorkResult(String status, long durationMs) {}

    @GetMapping("/work")
    public ResponseEntity<WorkResult> work(
            @RequestParam(name = "ms", defaultValue = "100") long ms) {

        if (ms < 0 || ms > 2_000) {
            return ResponseEntity.badRequest().build();
        }

        if (!slots.tryAcquire()) {
            return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
                .header(HttpHeaders.RETRY_AFTER, "1")
                .build();
        }

        try {
            // Simulates blocking work solely to observe behavior under load.
            Thread.sleep(ms);
            return ResponseEntity.ok(new WorkResult("completed", ms));

        } catch (InterruptedException interrupted) {
            Thread.currentThread().interrupt();
            return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
                .build();

        } finally {
            slots.release();
        }
    }
}
~~~

**Thread.sleep** is intentional solely for learning how servlet workers are held. In production, replace with real business logic, timeouts/transactions/cancellation, and separate DB/downstream limits. The Semaphore (fairness=true) is per-JVM and wraps only this work method; it does not limit all HTTP endpoints or the whole cluster. In a real app, consider service-layer bulkheads rather than duplicating semaphores across controllers.

**src/main/resources/application.properties**:

~~~properties
server.port=8080

# HTTP/Servlet resource boundaries for the demo.
server.tomcat.threads.max=20
server.tomcat.max-connections=100
server.max-http-request-header-size=16KB
spring.servlet.multipart.max-file-size=5MB
spring.servlet.multipart.max-request-size=6MB

# Applies only to MVC async requests, if used by the app.
spring.mvc.async.request-timeout=10s

# Wait for in-flight requests within a shutdown phase.
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=10s
~~~

The graceful timeout here is **10s** because the demo runs work for at most 2s; real apps with longer valid requests must adjust to match SLA and orchestrator limits. **server.tomcat.threads.max=20** does not cap business work at two: the business limit is enforced by the semaphore.

**src/test/java/demo/WorkControllerTest.java**:

~~~java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@WebMvcTest(WorkController.class)
class WorkControllerTest {
    @Autowired
    private MockMvc mvc;

    @Test
    void successfulWorkReturnsKnownJson() throws Exception {
        mvc.perform(get("/api/work").param("ms", "0"))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(
                org.springframework.http.MediaType.APPLICATION_JSON))
            .andExpect(jsonPath("$.status").value("completed"))
            .andExpect(jsonPath("$.durationMs").value(0));
    }

    @Test
    void invalidDurationRejectedBeforeWork() throws Exception {
        mvc.perform(get("/api/work").param("ms", "2001"))
            .andExpect(status().isBadRequest());
    }
}
~~~

These two tests verify the **200/JSON success contract** and **400 input rejection**. They do not prove the system handles concurrent overload, network timeouts, or graceful shutdown: those require integration/load/lifecycle tests because MockMvc does not open real sockets.

Run from the root directory:

~~~bash
mvn test
mvn spring-boot:run
~~~

Once dependencies resolve, the two JUnit tests are expected to pass. In another terminal:

~~~bash
curl -i "http://localhost:8080/api/work?ms=0"
~~~

The body returned by the controller on success:

~~~json
{"status":"completed","durationMs":0}
~~~

Expected status is **HTTP 200**, header **Content-Type: application/json**. Command with invalid ms:

~~~bash
curl -i "http://localhost:8080/api/work?ms=2001"
~~~

Expected **HTTP 400 Bad Request**; the exact error body is defined by Spring Boot error handling and no specific JSON body is guaranteed here.

### Testing overload in a controlled way

Open two terminals sending requests that hold permits for ~2 seconds:

~~~bash
curl -i "http://localhost:8080/api/work?ms=2000"
~~~

While both requests are running, send a third request. When both permits are held, the third request receives **HTTP 503** and **Retry-After: 1**. If the first request already finished or had not yet acquired a permit when the third arrived, the third can succeed; exact ordering/counts depend on timing, so never assert a fixed number in manual terminal tests.

In automated tests, use a **barrier/latch** with a real server to deterministically verify when two permits are held. Avoid relying solely on **Thread.sleep(100)** hoping requests overlap; that flakes easily on CI.

### Testing graceful shutdown

Start the server with **mvn spring-boot:run**, send a **ms=2000** request, send SIGTERM to the Java process while the request is executing, and observe whether it finishes before the 10s window expires. In real deployments, test via the orchestrator, traffic routing, and pod readiness. **Using Ctrl+C or IDE Stop is not an equivalent test across all environments** because process termination semantics may differ from SIGTERM.

**Do not interpret a single curl run as an absolute guarantee**: if the process is force-killed, misses SIGTERM, the reverse proxy times out, or requests are still in transit, outcomes can differ. Graceful shutdown must be tested alongside real load balancers, thread pools, DB transactions, and background jobs.

## 12. Logging, metrics, tracing, and alerting

To see where the system is constrained, measure at least:

| Metric / signal | Explanation |
| --- | --- |
| HTTP active requests and p50/p95/p99 latency | Whether load and tail latency are rising |
| 4xx/5xx, 429, 503, 504 | Distinguish input/rate limits, overload, and gateway timeouts |
| Tomcat busy/active and max threads | Whether the server worker pool is saturated |
| Open/idle connections and accept backlog | Connection pressure and idle socket retention |
| JVM heap, GC pauses, direct memory | Buffers/JSON/DataBuffers causing memory pressure |
| Executor active threads, queue depth, rejected tasks | Background processing overloaded |
| DB pool active/idle/pending and query timeouts | Downstream DB bottleneck |
| Outbound HTTP pool active/pending, connect/response timeouts | Remote dependencies causing congestion |
| WebSocket/SSE active sessions, drops, termination reasons | Streaming leaks or disconnects |
| Shutdown duration and unfinished work | Whether graceful windows are exceeded |

Spring Boot Actuator/Micrometer can provide metrics per configured instrumentation and backend, though not every metric above appears automatically unless the corresponding instrumentation is enabled. Distinguish **request canceled by client** from **server 500** in logs/metrics; a broken pipe after a browser leaves does not mean the same thing as a business failure before sending a response.

### Logging principles for disconnects/timeouts

- Log **request/correlation ID**, endpoint, duration, status/result, and timeout category.
- Never log raw access tokens, full request bodies, file uploads, or personal data.
- Normal SSE/WebSocket disconnects do not need ERROR stack traces repeated thousands of times; aggregate via metrics.
- Never swallow **InterruptedException**; restore the interrupt flag when catching in blocking code and exit early.
- Do not treat a **timeout** as proof that downstream rolled back. A client POST may have executed successfully on the server before the response was lost; retries require idempotency keys.

## 13. Designing tests for failure modes

| Failure mode | How to simulate | What must be proven |
| --- | --- | --- |
| High concurrent requests | Load test with explicit concurrency, barrier/latch tests | Early rejection, bounded queues, post-overload recovery |
| Oversized request body | Payload exceeding multipart/codec limits | Appropriate rejection, disk/memory do not grow unbounded |
| Downstream unreachable | Unreachable mock server/DNS/socket setup | Finite connect timeout, proper error reporting |
| Downstream very slow | MockWebServer/WireMock with response delay | Response timeout, total deadline, and cleanup |
| Outbound pool exhausted | Small connection pool with many concurrent requests | Bounded pending acquire, no unbounded queuing |
| Client closes SSE/browser tab | HTTP client cancels/closes socket | Subscriptions/tasks released, metrics updated |
| Client expires before server | Proxy timeout shorter than API | Stop wasting resources where cancellation is possible |
| SIGTERM while requests are active | Integration/deployment test | Stop accepting new requests; in-flight within grace finish if timely |
| SIGKILL mid-transaction | Chaos/drill with test data | Durable state/idempotency enables recovery |
| WebSocket/SSE during rolling deploy | Open sessions then drain pod | Clients reconnect, re-subscribe, state stays consistent |

**Note on HTTP status upon cancellation:** sometimes the server cannot send any status because the socket is already closed. Proxy logs may show vendor-specific codes for client-closed requests, yet the application should not try to write a "disconnect status" onto a dead connection. In Reactor, **CANCEL** is a publisher signal, not an HTTP status.

A reliable graceful-shutdown test must distinguish exact points in time: the request was truly accepted by the server, SIGTERM arrived, the server stopped routing new work, old requests finished/timed out, and resources closed. Merely sending SIGTERM and checking the exit code does not validate graceful behavior.

## 14. Common mistakes to avoid

1. **Setting server.tomcat.connection-timeout and assuming the API has a business deadline.** That is a connection timeout, not a substitute for outbound read timeouts and total request budgets.
2. **Raising threads.max when the DB pool is too small.** Adding servlet workers can simply increase threads waiting on the DB and worsen p99.
3. **Leaving executor queues or pending acquire unbounded.** Small overloads turn into thousands of hanging requests instead of fast rejection.
4. **Enforcing upload limits only on the client.** Other callers can bypass the UI; enforce limits at server/proxy/storage.
5. **Raising WebFlux maxInMemorySize to "fix" large streams.** Switch to pagination or streaming where contracts allow, bounding per-record size.
6. **Using Thread.sleep/synchronous JDBC on the Netty event loop.** One blocking call degrades many unrelated connections.
7. **Calling subscribe() manually in reactive controllers.** Loses WebFlux cancellation/error propagation and can orphan background work.
8. **Assuming DeferredResult timeout cancels the background task.** You need explicit owners, cancellation/interruption, and query timeouts.
9. **Expecting an instant disconnect callback in Spring MVC.** Servlet does not reliably notify on every remote close; I/O writes/heartbeats detect it.
10. **Calling completeWithError() unconditionally in SseEmitter's catch IOException.** Spring/container already handle lifecycle error notifications.
11. **Letting all in-flight streams live forever during graceful shutdown.** Enforce drain/reconnect policies and bounded deadlines.
12. **Treating graceful shutdown as a substitute for durable queues.** Processes can still be killed; guard against lost/duplicate work.
13. **Retrying every timeout error.** Timeouts can happen after the server completed side effects; retries require idempotency.
14. **Skipping tests behind a proxy/load balancer.** An app may work on localhost yet fail due to gateway idle timeouts or mismatched termination grace.

## 15. Pre-deployment operational checklist

- [ ] Identify true resource bottlenecks: CPU, JVM memory, Tomcat threads, Reactor Netty pools, DB connections, or downstreams.
- [ ] Set limits for HTTP connections/headers, request/multipart/codec buffers, and business concurrency per real capacity.
- [ ] Eliminate unbounded queues or buffers on high-traffic paths.
- [ ] Configure finite connect/read/response timeouts and controlled retry policies on outbound HTTP.
- [ ] Align total business deadlines with gateway timeouts and SLAs; never let every downstream step consume the entire deadline.
- [ ] Ensure streaming/SSE/WebSocket paths have cleanup, suitable heartbeats, cancellation, and reconnect strategies.
- [ ] Give Spring MVC async bounded executors and timeouts; keep WebFlux free of event-loop blocking.
- [ ] Align graceful shutdown and orchestrator termination grace with bounded valid requests.
- [ ] Ensure background tasks, thread pools, DB pools, and network clients have lifecycle owners and close on ApplicationContext shutdown.
- [ ] Ensure metrics/logs distinguish overload, rate limits, timeouts, disconnects, shutdowns, and business errors.
- [ ] Test overload, remote timeouts, client aborts, and SIGTERM behind a proxy.

## Official documentation

- [Spring Boot 3.5 – Graceful Shutdown](https://docs.spring.io/spring-boot/3.5/reference/web/graceful-shutdown.html)
- [Spring Boot 3.5 – Common Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/)
- [Spring Framework 6.2 – Spring MVC Asynchronous Requests](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-ann-async.html)
- [Spring Framework – Reactive Core and codec buffer limits](https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html)
- [Spring Framework – WebClient Configuration, resources and timeouts](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-builder.html)
- [JdkClientHttpRequestFactory Javadoc (Spring 6.2)](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/http/client/JdkClientHttpRequestFactory.html)
- [Spring Framework – WebFlux](https://docs.spring.io/spring-framework/reference/6.2/web/webflux.html)
