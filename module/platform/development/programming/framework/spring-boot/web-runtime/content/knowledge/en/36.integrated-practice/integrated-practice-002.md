# Building a Streaming Spring WebFlux API with Controlled Blocking Code

## 1. Objectives of This Integrated Practice

Spring WebFlux is a web stack supporting **non-blocking I/O** and a programming model built on Reactive Streams. However, a controller returning `Flux<T>` does not automatically make all underlying work non-blocking: `Thread.sleep`, synchronous JDBC, `RestTemplate`, `Future.get`, `Files.readAllBytes`, `Mono.block()`, or a synchronous client library can still occupy the thread handling the request. If that code executes on a **Reactor Netty event-loop**, one slow request can stall many other connections sharing that event loop.

This lesson belongs to **Integrated Practice** in the **Spring Boot - web-runtime** module. We build an API featuring **two streaming response formats** and one endpoint bridging to a legacy synchronous library with **bounded resources**:

1. `GET /api/readings/sse` streams sensor events via **Server-Sent Events** (`text/event-stream`).
2. `GET /api/readings/ndjson` streams one JSON object per line via **NDJSON** (`application/x-ndjson`).
3. `GET /api/legacy/{sku}` simulates reading inventory from a synchronous API, wrapped with `Mono.fromCallable(...)` and `subscribeOn(...)` on a **custom boundedElastic Scheduler**—never sleeping or blocking on the Netty event loop.
4. `GET /api/readings/stats` observes **active/cancelled subscriptions** in the demo.
5. A suite of **unit tests with StepVerifier**, **slice tests with @WebFluxTest**, and **HTTP integration tests with @SpringBootTest(RANDOM_PORT)** verifying streaming, validation, cancellation, and offloading.

The sample project uses **Java 17+, Spring Boot 3.5.16, Reactor Netty, reactor-test, JUnit Jupiter, and Mockito**. Version 3.5.16 is pinned to keep imports and APIs aligned with Boot 3.5, though it is the **final OSS release of the 3.5.x line** per Spring's announcement (25/06/2026). For new production projects, choose a supported Boot line and current patch release; when upgrading to Boot 4.x, check for test module/package changes.

After completing this lesson, you should be able to answer:

- Is data sent to the client **incrementally**, or buffered completely with `collectList()` before returning?
- Is the source **cold** (each subscriber gets its own stream) or **hot** (shared producer)?
- What happens when a client disconnects or a subscriber calls `cancel()`?
- Which thread actually runs a blocking call? How does `subscribeOn` differ from `publishOn`?
- Why can a bounded scheduler still fill its queue, and when a timeout fires, is the underlying blocking I/O guaranteed to stop?
- When should you use SSE, NDJSON, WebSocket, a single-value `Mono`, or MVC instead of WebFlux?
- Does a passing mock-exchange test prove Netty actually flushes chunks and releases resources?

**Key rule:** returning `Flux` is only the **API shape**. True reactive/non-blocking behavior depends on every operation executed inside the pipeline—across the request handler, persistence, HTTP client, codec, scheduler, and downstream services.

## 2. Architecture of the Practice Project

```text
HTTP Client / curl -N / WebTestClient
                  |
                  v
          Reactor Netty server
            WebFlux WebHandler
                  |
          StreamingController
         /        |         \
        /         |          \
GET SSE       GET NDJSON      GET /legacy/{sku}
text/event-   x-ndjson              |
stream            |                LegacyBridge
        \         /                  |
        ReadingStreamService         Mono.fromCallable
        Flux.interval + take         .subscribeOn(custom boundedElastic)
        map -> SensorReading          |
        defer + doFinally            LegacyInventoryClient
         |         |                  (Thread.sleep demo ONLY)
    active gauge  cancel counter
```

WebFlux can multiplex many I/O-bound requests across a small number of event-loop threads. However, an application cannot create more CPU cores or database capacity merely by adopting `Mono`/`Flux`.

### 2.1. SSE vs NDJSON vs JSON Array

| Format | Media Type | How Data Arrives at Client | Best Fit |
| --- | --- | --- | --- |
| JSON array | `application/json` | Typically encoded as one complete JSON document; body readers may wait until completion | Small, finite lists |
| SSE | `text/event-stream` | Multiple `id`/`event`/`data` frames over a unidirectional server→client HTTP stream | Progress, notifications, logs, live dashboards |
| NDJSON | `application/x-ndjson` | Each line is an **independent JSON value**; consecutive lines over the stream | Streaming records/analytics/events to machine clients |
| WebSocket | WebSocket protocol | Full-duplex bidirectional messages | Chat, interactive bidirectional updates |

SSE is commonly consumed via browser `EventSource`, which provides reconnect semantics and `Last-Event-ID` in the protocol; **this demo only numbers IDs** and does not store or replay history after reconnects. If business requirements demand exact resume, the server needs a durable event log and `Last-Event-ID` handling—simply adding `.id(...)` is not enough.

NDJSON is not a JSON array: the body looks like this, with each object terminated by a newline:

```text
{"sequence":1,"celsius":20.0,"source":"sensor-demo"}
{"sequence":2,"celsius":20.5,"source":"sensor-demo"}
{"sequence":3,"celsius":21.0,"source":"sensor-demo"}
```

If a client runs `JSON.parse` across the entire body as **one** JSON document, it will fail. NDJSON clients must read line-by-line or use a streaming decoder. Likewise, an SSE body cannot be parsed as a regular JSON array.

### 2.2. Streaming Does Not Mean "Every Line Appears on Screen Instantly"

When a client sees each event is also affected by TCP buffers, kernel scheduling, codecs, compression, reverse proxy buffering, HTTP/2 flow control, mobile networks, and client library behavior. `curl -N` reduces curl-side buffering, **not buffering in intermediate proxies**. Therefore, test real HTTP streaming rather than only asserting that the publisher emits multiple values.

## 3. Enough Reactive Streams Fundamentals to Write Correct Code

Basic signals of a `Flux<T>`:

```text
subscribe
  |
  +-- request(n) from downstream (backpressure demand)
  |
  +-- onNext(value) 0..N times
  |
  +-- onComplete() OR onError(error)
  |
  +-- cancel() from subscriber (not onComplete)
```

A `Mono<T>` emits at most one value, completes empty, or signals an error. `Flux<T>` emits multiple values. A publisher can be **cold** (each subscription creates its own stream) or **hot** (multiple subscribers share a live source).

A controller returning `Flux<SensorReading>` **should never call `subscribe()` itself**. WebFlux subscribes according to the HTTP response lifecycle. Calling `subscribe()` manually to "kick off processing" and returning `Mono.empty()` disconnects asynchronous errors from the HTTP response, detaches cancellation, and can trigger duplicate side effects.

Key operators:

- `map`: transforms values in the pipeline; never use for blocking I/O.
- `flatMap`: coordinates asynchronous publishers; use `flatMap(mapper, concurrency)` to bound concurrency **within the pipeline** across multiple remote calls.
- `concatMap`: preserves order when publishers must execute sequentially.
- `take(n)`: bounds a finite stream; downstream cancels upstream once `n` items are received.
- `onErrorResume`: **conditional** fallback—do not swallow all errors; preserve error semantics for critical business failures.
- `timeout`: caps waiting time on the reactive pipeline, but **does not guarantee** that a blocking client or native I/O stops when timeout occurs.
- `doFinally`: runs on complete, error, or cancel; use for cleanup/metrics, **not** for consistency-critical business side effects.
- `retryWhen`: retry with backoff/jitter for idempotent operations; never blindly retry side-effecting POSTs.

### 3.1. Why `Flux.interval` Is Used in the Demo

`Flux.interval(initialDelay, period)` emits ticks via a Scheduler without calling `Thread.sleep` in the controller. In the demo, each subscription starts its own timer stream (a cold publisher). This simulates new time-based data, **not a real hardware sensor feed**. In production, replace it with `WebClient`, R2DBC, or a reliable message feed with explicit buffering and backpressure handling.

`Flux.interval` is not a durable queue; if a subscriber cannot keep up with demand, it can error on overflow and does not retain events for reconnecting clients. Holding open infinite streams across thousands of subscribers consumes timers, network connections, and memory; you need quotas, cancellation, heartbeats, and monitoring.

## 4. Blocking on the Event Loop: What Goes Wrong?

### 4.1. **Wrong** Examples — Only to Identify the Anti-Pattern

**Do not add the following snippet to the runnable project**:

```java
@GetMapping("/wrong")
public Mono<String> wrong() {
    // WRONG: synchronous code blocking the controller's calling thread.
    Thread.sleep(1000);  // Java will require handling InterruptedException.
    return Mono.just("done");
}
```

This is intentionally **non-compiling pseudocode** illustrating the design flaw; `Thread.sleep` also requires handling checked exceptions. In practice, if fixed to compile and executed directly inside a WebFlux handler, it can hold a Netty event-loop thread for 1 second, stalling many unrelated requests. Never copy this into production.

Another **also wrong** variant:

```java
@GetMapping("/wrong-again")
public Mono<String> wrongAgain() {
    String value = blockingClient.fetch(); // executes blocking call immediately
    return Mono.just(value);               // wraps AFTER already blocking
}
```

This is a conceptual snippet; `blockingClient` is not in the sample project. `Mono.just` does not make an already-executed synchronous call non-blocking; it merely wraps a precomputed value.

### 4.2. Correct Pattern for a Legacy Blocking Call

Reactor guidance:

```java
Mono<InventorySnapshot> result =
    Mono.fromCallable(() -> legacyClient.fetch(sku))
        .subscribeOn(Schedulers.boundedElastic());
```

`Mono.fromCallable` **defers** execution until subscription time; `subscribeOn` determines which scheduler runs the subscription and source call. `Schedulers.boundedElastic()` offloads blocking I/O off the event loop and enforces **bounds on threads and queued tasks**. It does not speed up an already saturated database; timeouts and concurrency controls are still required.

**Why not fix it by placing `publishOn(Schedulers.boundedElastic())` at the end?**

```java
Mono.fromCallable(() -> blockingClient.fetch(sku))
    .publishOn(Schedulers.boundedElastic());
```

Conceptual snippet. `publishOn` switches the execution context for **operators downstream** of the `publishOn` call; it does not offload the source callable upstream of it. For a blocking source, place `subscribeOn` right next to `Mono.fromCallable`.

**Never call `Mono.block()` inside a WebFlux handler.** Reactor warns that blocking APIs like `block()/blockFirst()/blockLast()` on non-blocking schedulers may throw `IllegalStateException`, in addition to hurting throughput.

### 4.3. A Bounded Scheduler Is a Container, Not Magic

In the project, we use a dedicated scheduler:

```java
Schedulers.newBoundedElastic(
    4,               // thread cap of the scheduler
    16,              // queue bound per backing thread per Reactor API
    "legacy-bridge"  // identifiable name in thread dumps
);
```

This is a **demo limit**, not a production sizing recommendation. Reactor can reject scheduling when queue capacity fills, signaling `RejectedExecutionException`. The queue bound is **not** a database connection quota and does not replace global admission control or per-user bulkheads.

Remaining limitations:

- All concurrent HTTP requests can enter the reactive pipeline; they wait or fail only at the scheduler queue.
- Reactor timeouts cancel the subscription, yet an underlying blocking call may ignore thread interrupts and keep running.
- Without native connect/read/query timeouts in the synchronous library, a worker thread can remain tied up indefinitely.
- A local scheduler does not control global load across **multiple JVM replicas**.
- Long-running blocking calls build memory and queue pressure; rejected requests and p95/p99 latency need dedicated metrics and alerts.
- `boundedElastic` is useful as a **temporary bridge**; long-term, prefer reactive/non-blocking clients where available and sensible.

## 5. Complete Runnable Java 17+ Practice Project

### 5.1. Directory Tree

```text
webflux-streaming-lab/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/streamlab/
    │   │   ├── StreamLabApplication.java
    │   │   ├── SensorReading.java
    │   │   ├── InventorySnapshot.java
    │   │   ├── ReadingStreamService.java
    │   │   ├── LegacyInventoryClient.java
    │   │   ├── LegacyBridge.java
    │   │   └── StreamingController.java
    │   └── resources/
    │       └── application.properties
    └── test/
        └── java/com/example/streamlab/
            ├── StreamingApiIntegrationTest.java
            ├── StreamingControllerSliceTest.java
            ├── ReadingStreamServiceTest.java
            └── LegacyBridgeTest.java
```

Each `public` top-level Java class or record lives in a file of the same name. No database, Kafka, or external HTTP service is needed for the demo; data comes from `Flux.interval` and a fake synchronous client with a short sleep. This lets learners run everything with Maven/JDK without external network dependencies.

### 5.2. `pom.xml` — Valid Maven Configuration

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>webflux-streaming-lab</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-test</artifactId>
            <scope>test</scope>
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
```

**Why these dependencies?**

- `spring-boot-starter-webflux`: Spring WebFlux, Reactor, default Reactor Netty server, and Jackson codecs.
- `spring-boot-starter-actuator`: `health/metrics` when exposed; for local lab observation only, not public production exposure.
- `spring-boot-starter-test`: JUnit Jupiter, Mockito, Spring Test.
- `reactor-test`: `StepVerifier` for testing signals, cancellation, and virtual time.
- **Do not** add `spring-boot-starter-web`, because when both MVC and WebFlux are on the classpath, Spring Boot normally selects MVC, invalidating the Netty event-loop runtime assumptions of this lesson.

### 5.3. Application Properties

**`src/main/resources/application.properties`**

```properties
spring.application.name=webflux-streaming-lab
server.port=8080

# Local demo only; in real container deployments,
# configure listen address/network per deployment topology.
server.address=127.0.0.1
spring.main.web-application-type=reactive

# Expose only health and metrics in local environment.
management.endpoints.web.exposure.include=health,metrics

# Limit buffer size when decoding a payload into memory
# (not a limit on total SSE clients or outbound bytes).
spring.codec.max-in-memory-size=256KB
```

`spring.codec.max-in-memory-size` caps codec buffering and raises `DataBufferLimitException` when a payload is too large; it **does not** cap total bytes sent across a streaming response. In production, add body-size rules, connection quotas, upstream timeouts, authentication/authorization, and cgroup resource monitoring.

### 5.4. Main Class

**`src/main/java/com/example/streamlab/StreamLabApplication.java`**

```java
package com.example.streamlab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class StreamLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(StreamLabApplication.class, args);
    }
}
```

### 5.5. DTOs for Streaming and Inventory

**`src/main/java/com/example/streamlab/SensorReading.java`**

```java
package com.example.streamlab;

public record SensorReading(
        long sequence,
        double celsius,
        String source
) {}
```

**`src/main/java/com/example/streamlab/InventorySnapshot.java`**

```java
package com.example.streamlab;

public record InventorySnapshot(
        String sku,
        int available
) {}
```

Java 17 records serve well as immutable DTOs and are encoded into JSON objects by Jackson. The examples use deterministic values so tests do not assert on random data. Never put internal thread names, exception stack traces, or tokens into production DTOs.

### 5.6. Stream Service: Cold Flux, Bounded Events, and Cleanup

**`src/main/java/com/example/streamlab/ReadingStreamService.java`**

```java
package com.example.streamlab;

import java.time.Duration;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.stereotype.Service;

import reactor.core.publisher.Flux;
import reactor.core.publisher.SignalType;

@Service
public class ReadingStreamService {

    private final AtomicInteger active = new AtomicInteger();
    private final AtomicInteger cancelled = new AtomicInteger();

    public Flux<SensorReading> readings(
            int count,
            long periodMs) {

        // Each subscription gets its own timer and lifecycle.
        return Flux.defer(() -> {
            active.incrementAndGet();

            return Flux.interval(
                    Duration.ZERO,
                    Duration.ofMillis(periodMs))
                .take(count)
                .map(tick -> new SensorReading(
                    tick + 1,
                    20.0 + (tick % 5) * 0.5,
                    "sensor-demo"
                ))
                .doFinally(signal -> {
                    if (signal == SignalType.CANCEL) {
                        cancelled.incrementAndGet();
                    }
                    active.decrementAndGet();
                });
        });
    }

    public int active() {
        return active.get();
    }

    public int cancelled() {
        return cancelled.get();
    }
}
```

Design notes:

1. `Flux.defer` creates the stream **at subscription time**, rather than incrementing `active` when the controller builds the `Flux`. If two subscribers call the endpoint concurrently, each gets its own timer and sequence.
2. `Flux.interval(Duration.ZERO, Duration.ofMillis(periodMs))` emits `0,1,2,...` on schedule, producing `SensorReading(sequence = tick+1,...)`.
3. `take(count)` bounds the event count and completes the pipeline, avoiding infinite streams in the HTTP demo.
4. `doFinally` handles **complete, error, and cancel**, decrementing `active` in one place. `SignalType.CANCEL` increments the counter to observe subscriber cancellation behavior.
5. `AtomicInteger` does not turn counters into a database; these are **per-JVM** metrics. Across multiple replicas, cluster totals require a monitoring backend.
6. Counters may already drop back to `0` before/when a client reads `/stats`; sampling stats **does not** prove every event reached the browser.
7. With `Flux.interval`, if downstream cannot keep up with demand, it can signal an overflow error; the demo does not guarantee at-least-once delivery or replay.
8. `doFinally` is appropriate for releasing resources and updating local gauges; do not use it for financial commits or exactly-once side effects.

**Limitation:** because `periodMs` is validated in the controller, calling the service directly with `periodMs <= 0` can fail timer creation. When reusing the service elsewhere, add domain validation and tests at the service boundary if an independent contract is needed.

### 5.7. Simulating a Legacy Synchronous Library

**`src/main/java/com/example/streamlab/LegacyInventoryClient.java`**

```java
package com.example.streamlab;

import org.springframework.stereotype.Component;

@Component
public class LegacyInventoryClient {

    public InventorySnapshot fetch(String sku) {
        // Only to simulate a legacy synchronous JDBC/HTTP API.
        // DO NOT use sleep to handle requests in production.
        try {
            Thread.sleep(60);
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException(
                "Legacy lookup interrupted", ex
            );
        }

        return new InventorySnapshot(sku, 17);
    }
}
```

`Thread.sleep(60)` **blocks the thread**. This is an intentional simulation to verify offloading, not how real I/O should be performed. When replacing it with a real synchronous JDBC/HTTP client, configure **timeouts in that library itself** (connect/read/query) and pool limits. Never allow a blocking task to run unboundedly.

### 5.8. Bridge with Dedicated Scheduler and Timeout

**`src/main/java/com/example/streamlab/LegacyBridge.java`**

```java
package com.example.streamlab;

import java.time.Duration;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.TimeoutException;

import jakarta.annotation.PreDestroy;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

import reactor.core.publisher.Mono;
import reactor.core.scheduler.Scheduler;
import reactor.core.scheduler.Schedulers;

@Service
public class LegacyBridge {

    private final LegacyInventoryClient client;

    // Demo limits: 4 backing threads, queue bound 16/thread.
    // Production sizing must be based on workload and downstream capacity.
    private final Scheduler scheduler =
        Schedulers.newBoundedElastic(4, 16, "legacy-bridge");

    public LegacyBridge(LegacyInventoryClient client) {
        this.client = client;
    }

    public Mono<InventorySnapshot> lookup(String sku) {
        return Mono.fromCallable(() -> client.fetch(sku))
            .subscribeOn(scheduler)
            .timeout(Duration.ofSeconds(2))
            .onErrorMap(
                TimeoutException.class,
                ex -> new ResponseStatusException(
                    HttpStatus.GATEWAY_TIMEOUT,
                    "Legacy lookup timed out",
                    ex
                ))
            .onErrorMap(
                RejectedExecutionException.class,
                ex -> new ResponseStatusException(
                    HttpStatus.SERVICE_UNAVAILABLE,
                    "Legacy executor saturated",
                    ex
                ));
    }

    @PreDestroy
    public void dispose() {
        scheduler.dispose();
    }
}
```

Key points:

- `Mono.fromCallable` wraps the **entire** blocking call and defers invocation until subscription.
- `subscribeOn(scheduler)` shifts the source callable off the event loop onto a bounded pool dedicated to legacy work.
- `newBoundedElastic(4,16,...)` prevents unbounded thread creation; when the queue fills, it can reject tasks, mapped to 503 at the demo's HTTP layer. The `16` is the queue bound **per backing thread** in Reactor's API, not 16 requests cluster-wide.
- `timeout(2s)` translates excessive waits into a timeout error mapped to 504. A pipeline timeout **does not guarantee** the underlying blocking JDBC/socket call has stopped; native driver timeouts and resource cleanup are still required.
- `@PreDestroy` disposes the scheduler when the bean/context closes. One scheduler is created **per singleton bean**, not per HTTP request. Creating a scheduler per request causes thread/resource leaks.
- `RejectedExecutionException` could also originate from another internal executor as logic grows; this mapping fits the demo, while production should distinguish error sources before returning 503.
- Returning HTTP 503/504 does not replace metrics and alerting. Add throughput, queue depth, rejected count, and error rate telemetry in real systems.

**Do not use `Schedulers.parallel()` to run blocking I/O.** It is meant for CPU/non-blocking work, not sleep/JDBC. Nor does `boundedElastic` speed up a CPU-bound loop; CPU-intensive tasks require separate design sized by cores, quotas, and concurrency.

### 5.9. Controller: SSE, NDJSON, Stats, and Bridge

**`src/main/java/com/example/streamlab/StreamingController.java`**

```java
package com.example.streamlab;

import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api")
public class StreamingController {

    private final ReadingStreamService readings;
    private final LegacyBridge legacy;

    public StreamingController(
            ReadingStreamService readings,
            LegacyBridge legacy) {
        this.readings = readings;
        this.legacy = legacy;
    }

    @GetMapping(
        path = "/readings/sse",
        produces = MediaType.TEXT_EVENT_STREAM_VALUE
    )
    public Flux<ServerSentEvent<SensorReading>> sse(
            @RequestParam(defaultValue = "3") int count,
            @RequestParam(defaultValue = "50") long periodMs) {

        validateStreamParameters(count, periodMs);

        return readings.readings(count, periodMs)
            .map(item ->
                ServerSentEvent.<SensorReading>builder()
                    .id(Long.toString(item.sequence()))
                    .event("reading")
                    .data(item)
                    .build());
    }

    @GetMapping(
        path = "/readings/ndjson",
        produces = MediaType.APPLICATION_NDJSON_VALUE
    )
    public Flux<SensorReading> ndjson(
            @RequestParam(defaultValue = "3") int count,
            @RequestParam(defaultValue = "50") long periodMs) {

        validateStreamParameters(count, periodMs);
        return readings.readings(count, periodMs);
    }

    @GetMapping("/readings/stats")
    public Map<String, Integer> stats() {
        return Map.of(
            "active", readings.active(),
            "cancelled", readings.cancelled()
        );
    }

    @GetMapping("/legacy/{sku}")
    public Mono<InventorySnapshot> legacy(
            @PathVariable String sku) {

        if (!sku.matches("[A-Za-z0-9_-]{1,32}")) {
            throw new ResponseStatusException(
                HttpStatus.BAD_REQUEST, "Invalid SKU"
            );
        }

        return legacy.lookup(sku);
    }

    private static void validateStreamParameters(
            int count,
            long periodMs) {
        if (count < 1 || count > 20 ||
                periodMs < 25 || periodMs > 1000) {
            throw new ResponseStatusException(
                HttpStatus.BAD_REQUEST,
                "count must be 1..20 and periodMs 25..1000"
            );
        }
    }
}
```

**Why validate before returning the Flux?**

If you do not validate upfront and an error occurs after SSE/NDJSON has started writing bytes, HTTP headers may already be committed. At that point, the server generally **cannot** change the status from 200 to 400/500 cleanly. Validate `count`/`periodMs`/`sku` at the request boundary to return a clean 400.

**Why cap count at 20 and periodMs at 25..1000?** These are demo guardrails preventing a single client from requesting an overly long stream or rapid timer. **They are not sufficient rate limiting for production**: an attacker can still open many concurrent connections. Production needs authentication, per-tenant connection limits, admission control, idle timeouts, and monitoring.

## 6. Testing the API in the Terminal

With JDK 17+ and Maven, inside `webflux-streaming-lab`:

```bash
java -version
mvn spring-boot:run
```

If a Maven Wrapper has been generated, use `./mvnw spring-boot:run` or `mvnw.cmd spring-boot:run` on Windows. Do not assume the project already contains a wrapper if none was created.

### 6.1. SSE — Watching Event-by-Event

```bash
curl -N -i \
  -H "Accept: text/event-stream" \
  "http://127.0.0.1:8080/api/readings/sse?count=3&periodMs=300"
```

Body shape (JSON field order may vary):

```text
id:1
event:reading
data:{"sequence":1,"celsius":20.0,"source":"sensor-demo"}

id:2
event:reading
data:{"sequence":2,"celsius":20.5,"source":"sensor-demo"}

id:3
event:reading
data:{"sequence":3,"celsius":21.0,"source":"sensor-demo"}

```

Events are separated by blank lines; this is an illustrative SSE encoder representation, not a guarantee that TCP packets map 1:1 to events. `id` lets the client identify each event, though the demo has no durable replay/resume.

### 6.2. NDJSON — One Object per Line

```bash
curl -N -i \
  -H "Accept: application/x-ndjson" \
  "http://127.0.0.1:8080/api/readings/ndjson?count=3&periodMs=300"
```

Illustrative body:

```text
{"sequence":1,"celsius":20.0,"source":"sensor-demo"}
{"sequence":2,"celsius":20.5,"source":"sensor-demo"}
{"sequence":3,"celsius":21.0,"source":"sensor-demo"}
```

There are no surrounding `[`/`]` brackets like a JSON array. A client using an array JSON decoder or `JSON.parse` over the full body will fail; clients need a line parser or NDJSON streaming decoder.

### 6.3. Offloaded Legacy Blocking Endpoint

```bash
curl -i "http://127.0.0.1:8080/api/legacy/SKU-123"
```

Expected:

```json
{"sku":"SKU-123","available":17}
```

The endpoint still spends ~60ms sleeping on the **legacy scheduler thread**, yet the Netty event loop is not blocked by that call. Clients may observe latency above 60ms due to queueing, network, and JVM scheduling. Never claim response time is always exactly 60ms or extrapolate maximum server throughput from one request.

### 6.4. Invalid Input and Stats

```bash
curl -i "http://127.0.0.1:8080/api/readings/sse?count=0&periodMs=50"
curl -i "http://127.0.0.1:8080/api/readings/ndjson?count=3&periodMs=1"
curl -i "http://127.0.0.1:8080/api/legacy/bad%20sku"
curl -sS "http://127.0.0.1:8080/api/readings/stats"
```

The three invalid requests above expect 400, though a proxy or path decoder may reject encoded URIs before reaching the handler depending on deployment; the status for an encoded space URL should not be the sole evidence of validation. To test SKU validation reliably, use a unit/controller test passing `"bad sku"` directly or an invalid path param accepted by the container such as `bad!sku`. `stats` returns JSON with `active`/`cancelled`; values vary with live streams and cancellations.

PowerShell aliases `curl` in some environments; use `curl.exe` to pass flags like `-N`.

## 7. Testing with Spring WebTestClient and Reactor StepVerifier

Distinguish three levels:

1. **Unit tests** for `ReadingStreamService`/`LegacyBridge` directly: no HTTP server needed, uses `StepVerifier`, proves emission/cancel and thread offloading of the blocking callable.
2. **`@WebFluxTest` slice**: loads the controller and WebFlux codecs/validation, uses `@MockitoBean` for service/bridge; verifies HTTP mapping/status/body, not Netty TCP or real business logic.
3. **`@SpringBootTest(RANDOM_PORT)`**: starts a **real Reactor Netty HTTP server**, `WebTestClient` sends HTTP to a random port and consumes SSE/NDJSON. Does not by itself prove production proxy/CDN/TLS or behavior under load.

### 7.1. Unit Test Service: Values, Completion, and Cancellation

**`src/test/java/com/example/streamlab/ReadingStreamServiceTest.java`**

```java
package com.example.streamlab;

import java.time.Duration;

import org.junit.jupiter.api.Test;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;

class ReadingStreamServiceTest {

    @Test
    void finiteStreamEmitsValuesInOrder() {
        ReadingStreamService service = new ReadingStreamService();

        StepVerifier.create(service.readings(3, 25))
            .assertNext(r -> {
                assertEquals(1L, r.sequence());
                assertEquals(20.0, r.celsius());
            })
            .assertNext(r -> assertEquals(2L, r.sequence()))
            .assertNext(r -> assertEquals(3L, r.sequence()))
            .expectComplete()
            .verify(Duration.ofSeconds(5));

        assertEquals(0, service.active());
        assertEquals(0, service.cancelled());
    }

    @Test
    void cancellationTriggersCleanup() {
        ReadingStreamService service = new ReadingStreamService();

        StepVerifier.create(service.readings(20, 1000))
            .assertNext(r -> assertEquals(1L, r.sequence()))
            .thenCancel()
            .verify(Duration.ofSeconds(5));

        assertEquals(0, service.active());
        assertEquals(1, service.cancelled());
    }
}
```

`StepVerifier` subscribes and requests signals; with `Flux.interval`, actual emissions run on a scheduler so timing can vary—avoid asserting exact millisecond intervals. `verify(Duration)` protects CI from hanging indefinitely. `thenCancel()` triggers a **subscriber cancellation**. `doFinally(CANCEL)` updates the counter when upstream actually receives cancellation.

This test verifies the stream implementation within one JVM. It does not test Netty, JSON encoders, or client TCP disconnects. For SSE behind a proxy, end-to-end cancellation requires integration tests and real resource observation.

### 7.2. Unit Test Bridge: Callable Does Not Run on Test Thread

**`src/test/java/com/example/streamlab/LegacyBridgeTest.java`**

```java
package com.example.streamlab;

import java.time.Duration;
import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.Test;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

class LegacyBridgeTest {

    @Test
    void blockingCallableRunsOnDedicatedScheduler() {
        AtomicReference<String> observedThread =
            new AtomicReference<>();

        LegacyInventoryClient fake = new LegacyInventoryClient() {
            @Override
            public InventorySnapshot fetch(String sku) {
                observedThread.set(
                    Thread.currentThread().getName());
                return new InventorySnapshot(sku, 7);
            }
        };

        LegacyBridge bridge = new LegacyBridge(fake);
        try {
            StepVerifier.create(bridge.lookup("SKU-1"))
                .expectNext(new InventorySnapshot("SKU-1", 7))
                .expectComplete()
                .verify(Duration.ofSeconds(5));

            assertNotNull(observedThread.get());
            assertNotEquals(
                Thread.currentThread().getName(),
                observedThread.get()
            );
        } finally {
            bridge.dispose();
        }
    }
}
```

This test does not prove the entire HTTP handler is non-blocking, but verifies **the blocking callable runs off the JUnit calling thread**, per the bridge's `subscribeOn`. Proving the **Netty event-loop** is never blocked in production requires tracing, profiling, BlockHound, or integration tests with compatible instrumentation.

### 7.3. Web Slice Test: Media Type, Body, and 400

**`src/test/java/com/example/streamlab/StreamingControllerSliceTest.java`**

```java
package com.example.streamlab;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.WebFluxTest;
import org.springframework.http.MediaType;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.reactive.server.WebTestClient;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

import static org.mockito.BDDMockito.given;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.ArgumentMatchers.anyInt;
import static org.mockito.ArgumentMatchers.anyLong;

@WebFluxTest(controllers = StreamingController.class)
class StreamingControllerSliceTest {

    @Autowired
    WebTestClient client;

    @MockitoBean
    ReadingStreamService readings;

    @MockitoBean
    LegacyBridge legacy;

    @Test
    void ndjsonUsesExpectedMediaTypeAndBody() {
        given(readings.readings(2, 25)).willReturn(Flux.just(
            new SensorReading(1, 20.0, "sensor-demo"),
            new SensorReading(2, 20.5, "sensor-demo")
        ));

        client.get()
            .uri("/api/readings/ndjson?count=2&periodMs=25")
            .accept(MediaType.APPLICATION_NDJSON)
            .exchange()
            .expectStatus().isOk()
            .expectHeader().contentTypeCompatibleWith(
                MediaType.APPLICATION_NDJSON)
            .expectBodyList(SensorReading.class)
            .hasSize(2)
            .contains(
                new SensorReading(1, 20.0, "sensor-demo"),
                new SensorReading(2, 20.5, "sensor-demo")
            );
    }

    @Test
    void invalidStreamSettingsReturn400BeforeService() {
        client.get()
            .uri("/api/readings/sse?count=0&periodMs=20")
            .exchange()
            .expectStatus().isBadRequest();

        verify(readings, never()).readings(
            anyInt(), anyLong());
    }

    @Test
    void legacyRouteReturnsJson() {
        given(legacy.lookup("SKU1")).willReturn(
            Mono.just(new InventorySnapshot("SKU1", 17))
        );

        client.get().uri("/api/legacy/SKU1")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.sku").isEqualTo("SKU1")
            .jsonPath("$.available").isEqualTo(17);
    }
}
```

`@WebFluxTest` auto-configures `WebTestClient` without an HTTP port; regular `@Service` beans are excluded from the slice, so `@MockitoBean` is used. `Mockito.verify(..., never())` confirms invalid input is rejected **before invoking** the stream service. The test does not exercise the real scheduler because `LegacyBridge` is mocked here.

### 7.4. HTTP Integration: Real Netty Server, NDJSON, and SSE

**`src/test/java/com/example/streamlab/StreamingApiIntegrationTest.java`**

```java
package com.example.streamlab;

import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.test.web.reactive.server.FluxExchangeResult;
import org.springframework.test.web.reactive.server.WebTestClient;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
@AutoConfigureWebTestClient
class StreamingApiIntegrationTest {

    @Autowired
    WebTestClient client;

    @Test
    void ndjsonStreamsThreeObjectsOverHttp() {
        FluxExchangeResult<SensorReading> result =
            client.get()
                .uri("/api/readings/ndjson?count=3&periodMs=25")
                .accept(MediaType.APPLICATION_NDJSON)
                .exchange()
                .expectStatus().isOk()
                .expectHeader().contentTypeCompatibleWith(
                    MediaType.APPLICATION_NDJSON)
                .returnResult(SensorReading.class);

        StepVerifier.create(result.getResponseBody())
            .assertNext(r -> assertEquals(1L, r.sequence()))
            .assertNext(r -> assertEquals(2L, r.sequence()))
            .assertNext(r -> assertEquals(3L, r.sequence()))
            .expectComplete()
            .verify(Duration.ofSeconds(5));
    }

    @Test
    void sseStreamsThreeEventsOverHttp() {
        FluxExchangeResult<ServerSentEvent<SensorReading>> result =
            client.get()
                .uri("/api/readings/sse?count=3&periodMs=25")
                .accept(MediaType.TEXT_EVENT_STREAM)
                .exchange()
                .expectStatus().isOk()
                .expectHeader().contentTypeCompatibleWith(
                    MediaType.TEXT_EVENT_STREAM)
                .returnResult(
                    new ParameterizedTypeReference<
                        ServerSentEvent<SensorReading>>() {}
                );

        StepVerifier.create(result.getResponseBody())
            .assertNext(e -> {
                assertEquals("reading", e.event());
                assertEquals("1", e.id());
                assertNotNull(e.data());
                assertEquals(1L, e.data().sequence());
            })
            .assertNext(e -> assertEquals("2", e.id()))
            .assertNext(e -> assertEquals("3", e.id()))
            .expectComplete()
            .verify(Duration.ofSeconds(5));
    }

    @Test
    void badCountIsRejectedWith400() {
        client.get()
            .uri("/api/readings/ndjson?count=21&periodMs=25")
            .exchange()
            .expectStatus().isBadRequest();
    }

    @Test
    void legacyLookupReturnsExpectedDtoOverHttp() {
        client.get().uri("/api/legacy/SKU-1")
            .exchange()
            .expectStatus().isOk()
            .expectBody(InventorySnapshot.class)
            .isEqualTo(new InventorySnapshot("SKU-1", 17));
    }

    @Test
    void clientCanCancelLongSseSubscription() {
        FluxExchangeResult<ServerSentEvent<SensorReading>> result =
            client.get()
                .uri("/api/readings/sse?count=20&periodMs=1000")
                .accept(MediaType.TEXT_EVENT_STREAM)
                .exchange()
                .expectStatus().isOk()
                .returnResult(
                    new ParameterizedTypeReference<
                        ServerSentEvent<SensorReading>>() {}
                );

        StepVerifier.create(result.getResponseBody())
            .assertNext(e -> assertEquals("1", e.id()))
            .thenCancel()
            .verify(Duration.ofSeconds(5));
    }
}
```

**What is actually verified:**

- `@SpringBootTest(RANDOM_PORT)` boots the full application context and embedded Reactor Netty HTTP server. `WebTestClient` sends requests over loopback networking and decodes the streaming body.
- `FluxExchangeResult` lets you consume the body **event-by-event or object-by-object**; avoid waiting on the whole stream with `expectBodyList` for long streams.
- `thenCancel()` cancels the test client's subscription. It proves the client can cancel an HTTP stream, though proving **server-side listener cleanup** over TCP in all cases requires instrumentation or async observation. Do not immediately assert `stats.active==0` without eventual waiting, because network cancellation has propagation delay.
- All tests use relative URLs against the Spring Boot random port; they do not depend on another process running on 8080.
- The 200 JSON test for `LegacyBridge` runs the real scheduler, yet a single request **does not** prove good latency under overload.

### 7.5. Running the Test Suite and Expectations

```bash
mvn test
```

Or if a Maven Wrapper is present:

```bash
./mvnw test
```

You can also run individually:

```bash
mvn -Dtest=ReadingStreamServiceTest test
mvn -Dtest=LegacyBridgeTest test
mvn -Dtest=StreamingControllerSliceTest test
mvn -Dtest=StreamingApiIntegrationTest test
```

The sample project contains **2 + 1 + 3 + 5 = 11 test methods**. They are **designed** to pass with compatible JDK/Maven/dependencies; this guide does not claim Maven was executed on the reader's machine. `Flux.interval` timing depends on the scheduler/CI; tests use `verify(Duration)` rather than asserting exact millisecond intervals per event.

## 8. Controlling Blocking in a Real Project

### 8.1. Auditing Every Call

Trace from controller down to service and repository:

| Work Type | Examples | Action |
| --- | --- | --- |
| Non-blocking reactive source | `WebClient`, R2DBC, reactive Redis driver | Keep the pipeline reactive; bound connection/request timeouts |
| Synchronous HTTP client | `RestTemplate`, Apache sync client, `java.net.http.HttpClient.send` | Prefer WebClient or offload via `fromCallable` + `boundedElastic` |
| JDBC/JPA | `JdbcTemplate`, `JpaRepository` | Synchronous; offload if migration isn't feasible yet; never call on event loop |
| Sync file I/O | `Files.readAllBytes`, `FileInputStream` | Use async-capable APIs where available or bounded offloading/streaming |
| Waiting | `Thread.sleep`, `Future.get`, `CountDownLatch.await` | Never execute on event loop; replace with async composition or offload |
| Reactive blocking bridge | `Mono.block()`, `Flux.blockFirst()` | Never call from handler/event loop; compose with `map`/`flatMap` |
| CPU-intensive task | Large loops, image/video encoding | Use a dedicated executor/scheduler/worker sized by CPU cores |
| Logging | Sync appenders or logging large bodies | Watch I/O/logging overhead and sensitive data |
| Database pool | Waiting to acquire a connection | Measure pool wait/busy/rejections, optimize downstream |

**Never conclude that `@Async` automatically turns a synchronous dependency into non-blocking I/O.** It moves execution to an executor, which has its own thread/queue bounds and failure modes. Adding `@Async` while ignoring timeouts and bulkheads can still cause overload.

### 8.2. Non-Blocking WebClient Instead of Synchronous HTTP

Example **snippet**, not one of the compiled classes in the sample project:

```java
private final WebClient webClient;

public Mono<RemoteStatus> getStatus(String id) {
    return webClient.get()
        .uri(uriBuilder ->
            uriBuilder.path("/status/{id}").build(id))
        .retrieve()
        .bodyToMono(RemoteStatus.class)
        .timeout(Duration.ofSeconds(2));
}
```

This snippet assumes `WebClient` is injected, `RemoteStatus` exists, and the upstream endpoint is permitted. Never append `.block()`. Note that `WebClient` still has connection pools, codec buffers, DNS/TLS, and upstream quotas; configure connect/response/read timeouts on the underlying Reactor Netty client rather than relying solely on reactive `timeout`.

When calling multiple sources:

```java
Flux.fromIterable(ids)
    .flatMap(id -> webClient.get()
        .uri("/items/{id}", id)
        .retrieve()
        .bodyToMono(ItemDto.class),
        4);
```

This snippet assumes `ids`, `webClient`, and `ItemDto` are defined. `flatMap(...,4)` caps **four concurrent inner subscriptions within this pipeline**, not global concurrency across all requests or replicas. For operations requiring ordering, use `concatMap` or reorder explicitly.

### 8.3. BoundedElastic: Shared vs Dedicated

`Schedulers.boundedElastic()` is a shared global scheduler with defaults and policies determined by the Reactor version/runtime. It suits short-term isolated blocking calls, though it is shared with other callers using the same scheduler. `Schedulers.newBoundedElastic(...)` creates a dedicated scheduler as in the demo, isolating workloads and allowing clean lifecycle disposal.

Avoid two mistakes:

1. Creating `newBoundedElastic` **inside every HTTP request** without disposing → thread/resource leak.
2. Sharing one dedicated scheduler across unrelated blocking libraries without separate admission quotas → one slow dependency stalls all other tasks.

Tune concurrency, queue limits, native timeouts, and fallbacks alongside connection pools and downstream SLAs, balancing throughput and resource budgets. When the queue is full, return 429/503 intentionally with metrics rather than swallowing errors or retrying infinitely.

### 8.4. Backpressure Is Not Producer Speed or Retries

Reactive Streams `request(n)` lets downstream ask for data, but overload protection **depends on the source**:

- `Flux.range` can emit exactly to demand.
- `Flux.interval` is time-driven; when a consumer is slow, it does not indefinitely buffer ticks for later.
- Hot external sensor/Kafka/WebSocket callbacks can outpace demand; you need a backpressure strategy, bounded buffers, drop/latest policies, or source-level flow control.
- Unbounded `onBackpressureBuffer` can cause OOM; bounded buffers are safer if that policy fits the domain.
- `retryWhen` can amplify traffic during downstream overload; use backoff + jitter, max attempts, and deadlines.

A slow HTTP client applies network backpressure to the response stream, yet **does not guarantee** an upstream provider slows down on the same signal, especially for hot sources. Build queue lengths, discarded counts, slow-consumer metrics, and cancellation cleanup into the design.

### 8.5. Cancellation and Resources

When a subscriber cancels:

- Reactor propagates cancel upstream, though the source may not support cancelling an OS/driver operation.
- `doFinally(SignalType.CANCEL)` runs when this pipeline's subscription terminates via cancellation.
- For SSE/NDJSON, client disconnects generally trigger cleanup, though detection timing depends on network/heartbeats.
- Long-lived connections may detect disconnects only when the server next attempts a write; framework docs recommend periodic heartbeats (SSE comment-only or no-op events) to detect disconnects sooner.
- If working directly with pooled Netty `DataBuffer` instances, release buffers per ownership contract. With DTO→Jackson codecs in the demo, the framework manages buffers; never call `DataBufferUtils.release` on objects you do not own.

**Do not treat cancellation as a transactional rollback.** If a blocking call already wrote to the database before the request was cancelled, the side effect can persist. Business idempotency and transactions must be designed separately.

## 9. Avoiding Misconceptions Around BlockHound and Profiling

### 9.1. BlockHound Detects Known Blocking Calls

**BlockHound** is an optional Reactor instrumentation agent that can detect known blocking operations called on threads marked non-blocking—especially event loops. It is not automatically included when you add `spring-boot-starter-webflux` or `reactor-test`.

If a team adopts BlockHound:

- Add the dependency/version **compatible with your JDK/Reactor/agent** and install it in tests/test JVMs, not arbitrarily in production.
- On JDK 13+, some BlockHound versions require JVM instrumentation flags (such as `-XX:+AllowRedefinitionToAddDeleteMethods`); verify against current docs/versions instead of copying old blog flags.
- Exercise **real reactive execution paths**, not trivial `Mono.just(...)` mocks; watch test framework and instrumentation agent interactions.
- Avoid allowlisting whole packages or relaxing rules broadly and assuming no blocking remains.
- Do not treat the absence of BlockHound reports as proof that **every JDBC/native call is non-blocking**. It detects only what its instrumentation intercepts.

### 9.2. Thread Dumps, Micrometer, and Event-Loop Latency

Signs of a blocked event loop:

- Netty event-loop threads showing `Thread.sleep`, synchronous JDBC, socket reads, or `Future.get` in stack traces.
- p95/p99 latency rising as request concurrency climbs, even when CPU is not saturated.
- Health endpoints responding slowly if sharing the blocked event loop.
- Queues, outbound pools, timeouts, and rejections rising when downstream slows down.

Micrometer/Actuator provides `http.server.requests` and JVM thread/memory/GC/process metrics depending on the registry. `/actuator/metrics` is a diagnostic endpoint, **not** a full multi-pod time-series DB for p99. With Prometheus/OpenTelemetry, track HTTP latency histograms, errors, Reactor Netty connection metrics, `boundedElastic` queue utilization, and downstream latency.

Never attach request paths containing user IDs, session IDs, access tokens, or raw queries to metric labels; use low-cardinality route templates like `/api/legacy/{sku}`. Protect Actuator `metrics/env/threaddump/heapdump`—never expose them publicly.

## 10. Timeouts, HTTP Errors, and Committed Streams

There are three distinct stages:

1. Request not yet processed / headers not yet sent.
2. Server starts emitting SSE/NDJSON data; **headers are committed**.
3. Client has received some events, then the `Flux` errors or downstream disconnects.

At stage 1, exception handlers can return 400/503/504. At stages 2/3, the server cannot reliably change status 200 to 500 because the HTTP response is already committed. Streaming clients must distinguish unexpected stream termination, heartbeat timeouts, explicit application-level error events, and network failures.

In the demo:

- `GET /api/readings/sse?count=0` → 400 from pre-Flux validation.
- `GET /api/legacy/sku` timeout → 504 if response is not yet committed.
- Scheduler rejection → 503.
- A `Flux` that emits 2 events and then `onError` → can terminate with a network/protocol error; **no guarantee** the status changes from 200.
- Client cancel → `doFinally(CANCEL)` updates the counter, though there is no guarantee an underlying legacy blocking task stopped immediately.

**Do not apply `onErrorResume(ex -> Flux.empty())` indiscriminately.** Doing so masks partial failures and tricks clients into thinking the stream completed normally. When business fallback is needed, restrict exception classes, record metrics, and emit a signal/format the client understands.

## 11. Designing Production Streaming APIs

### 11.1. Authentication, Authorization, and Sensitive Data

- SSE often keeps HTTP connections open long-term; authenticate at connection establishment and evaluate token expiration/re-auth policies for long-lived streams.
- Browser `EventSource` does not allow custom `Authorization` headers the same way `fetch` does; pick an appropriate architecture (same-origin cookie/CORS with CSRF/threat model, or `fetch` streaming with bearer tokens)—never put tokens in URL query parameters.
- Enforce object/tenant authorization per stream subscription. Never assume visiting the homepage authorizes streaming.
- Never put emails, user IDs, or session IDs into SSE `id` fields or metric labels. Client-supplied `Last-Event-ID` is untrusted input and must be validated/bounded when implementing replay.
- Configure CORS and cache headers according to origin and data sensitivity; never use `Access-Control-Allow-Origin: *` carelessly for private data.
- Avoid logging raw bodies or PII on every event, as it increases I/O and exposure risk.

### 11.2. Resource Limits and Overload

- Limit **active streams per user/tenant**, total connections, maximum stream duration, and idle timeouts.
- For hot sources, define buffer/drop/replay policies and slow-consumer metrics.
- Demo limits on `count`/`periodMs` **are not enough** against DDoS or multi-connection overload.
- For blocking bridges, combine a bounded scheduler with native DB/HTTP timeouts, connection pool limits, request deadlines, and global admission control.
- Under overload, returning 429/503 with clear retry guidance beats accepting unbounded work and pushing p99 to multiple seconds.
- Never run load tests against production or third-party endpoints without authorization; use staging with synthetic data and clear guardrails.

### 11.3. How Gateways and Proxies Affect Streaming

Check:

- Whether Nginx/Ingress response buffering or caching batches SSE into one chunk instead of delivering events incrementally.
- Whether gateway idle timeouts are shorter than your heartbeat interval.
- HTTP/1.1 vs HTTP/2 keep-alive, compression, and proxy limits.
- Whether `spring.webflux.base-path`, route annotations, and reverse proxy rewrites align.
- Whether DNS/load-balancer reconnects land the subscriber on a different replica; in-memory `Flux.interval` has no cross-replica replay.
- Whether clients implement exponential backoff on reconnect and handle duplicate/gap events when required by the domain.

**Note:** `X-Accel-Buffering: no` is a specific hint for Nginx setups that support it; it does not disable all proxy buffering everywhere. Do not set one header and assume every CDN or ingress will flush chunks on schedule.

### 11.4. API Streaming vs Infinite Storage

Streaming with `Flux` reduces the need to materialize large lists in memory, yet does not guarantee bounded memory across every pipeline. Operators like `collectList()`, unbounded `buffer()`, `cache()`, and `replay()` can still accumulate many items. Pooled `DataBuffer` instances or JSON object allocations also consume heap/direct memory.

When clients need replay or historical data, use a durable message log or database cursor, pagination, and checkpoints. SSE/NDJSON is only the transport representation, not a persistent event store.

## 12. Common Errors Matrix

| Symptom | Likely Cause | Diagnosis / Fix |
| --- | --- | --- |
| Controller returns Flux but other requests stall | Blocking code running on Netty event-loop | Thread dumps, audit sleep/JDBC/`block()`; offload source |
| `Mono.just(blockingCall())` still blocks | Blocking call ran before Mono creation | `Mono.fromCallable(...).subscribeOn(boundedElastic)` |
| `publishOn` at the end does not help | Does not change scheduler of upstream source | Put `subscribeOn` on the blocking source |
| Scheduler threads keep growing | Creating a new scheduler per request | Use singleton scheduler, dispose on bean lifecycle |
| Legacy latency rises even without blocking Netty | `boundedElastic` queue or upstream saturation | Queue/timeout metrics, native client timeouts, load shedding |
| `RejectedExecutionException` under heavy load | Scheduler queue/task cap reached | Return controlled 503, shed load, or scale with evidence |
| Client receives 504 while DB keeps working | Pipeline timeout does not abort blocking call | Driver timeouts, cancellation support, idempotency |
| SSE receives all events at once | Client/proxy buffering, compression, or burst emission | `curl -N`, inspect proxy buffering, check emit timing |
| NDJSON parse failure | Client treats multiple lines as one JSON object/array | Parse line-by-line or use streaming decoder |
| SSE endpoint returns 406 | `Accept`/`produces` mismatch | Send `text/event-stream` |
| NDJSON endpoint returns 406 | Client only accepts `application/json` | Send `application/x-ndjson` |
| Service returns `Mono.empty` and HTTP returns 200 empty | HTTP contract didn't map empty→404 | Explicit domain handler/advice |
| `DataBufferLimitException` | Codec buffering payload over limit | Cap inputs, stream instead of collecting, tune carefully |
| Heap/direct memory grows | Unbounded buffer/`cache`, unreleased DataBuffers | Profile and release per ownership |
| Active SSE count doesn't drop to 0 immediately on tab close | Disconnect detection / async network | Heartbeats, logs, eventual cleanup tests |
| Cancel counter differs from request count | Multiple subscriptions, disconnect timing, finalize | Define metric boundaries, add tracing |
| `StepVerifier` passes but network fails | Unit test doesn't exercise Netty/proxy | `RANDOM_PORT` or deployment-level tests |
| `@WebFluxTest` missing service bean | Slice does not scan `@Service` | `@MockitoBean` / explicit import |
| App boots Spring MVC instead of WebFlux | Both MVC and WebFlux starters on classpath | Check dependencies and `web-application-type` |
| 200 already sent, then source errors | Headers committed | Test stream termination/error protocol |
| BlockHound reports nothing | Not installed, incompatible agent/runtime, or wrong test path | Configure instrumentation properly and hit real event loop |
| `Thread.sleep` on `boundedElastic` treated as "non-blocking" | Still blocks a worker thread, only offloaded | Bound workers/queues; prefer non-blocking libraries |

## 13. Self-Assessment Checklist

- [ ] App genuinely runs **Spring WebFlux + Reactor Netty**, not accidentally Servlet MVC.
- [ ] SSE returns `text/event-stream` with `ServerSentEvent<T>`; NDJSON returns `application/x-ndjson`.
- [ ] Each event/object streams through `Flux` and the codec without `collectList()` buffering the whole stream.
- [ ] `Flux.defer` scopes metrics/subscription lifecycle accurately; `doFinally` handles complete/error/cancel.
- [ ] No `Thread.sleep`, synchronous JDBC, `RestTemplate`, `Future.get`, or `Mono.block()` directly on the event loop.
- [ ] Legacy blocking calls use `Mono.fromCallable(...).subscribeOn(boundedElastic)`, driver timeouts, and resource bounds.
- [ ] Dedicated schedulers are created once and disposed on lifecycle shutdown—never per request.
- [ ] Event counts, intervals, connections, and admission control are bounded in real deployments.
- [ ] Cold streams are distinguished from hot external feeds, with clear buffer/drop/replay policies.
- [ ] Pre-commit HTTP errors and post-stream errors are designed separately.
- [ ] Real HTTP SSE/NDJSON tested with `WebTestClient`, not only mock publishers.
- [ ] `StepVerifier` tests cover `onNext`/`onComplete`/cancel and thread offloading.
- [ ] Never use `expectBodyList` on infinite streams; use `returnResult` and `thenCancel()`.
- [ ] SLOs and metrics cover latency, error rate, upstream pool queues, memory/direct buffers, event-loop utilization, and active streams.
- [ ] CORS, auth, tenant isolation, and data sensitivity checked for SSE; no tokens/PII in URLs or logs.
- [ ] Proxy buffering, heartbeats, reconnects, and `Last-Event-ID` replay verified when required by business logic.
- [ ] Load tests run only in authorized environments; the 11 functional tests are not treated as production capacity proof.

## 14. Self-Check Questions

**1. Does returning `Flux<T>` guarantee WebFlux will never block?**  
No. Code inside the stream can still call synchronous JDBC/HTTP, `Thread.sleep`, or `block()`.

**2. Why is `Mono.just(legacy.fetch())` incorrect?**  
Because `legacy.fetch()` executes and may block **before** the `Mono` is even created. Use `Mono.fromCallable`.

**3. How do `subscribeOn` and `publishOn` differ for a blocking source?**  
`subscribeOn` sets the scheduler for subscription and source execution; `publishOn` switches downstream operators and cannot rescue a blocking call that already ran upstream.

**4. Why use `newBoundedElastic` instead of `parallel`?**  
`boundedElastic` isolates blocking calls with thread/queue caps; `parallel` is not intended for blocking I/O.

**5. Does a 504 timeout guarantee the synchronous JDBC task has stopped?**  
No. The driver may ignore cancellation/interrupts; native timeouts and resource controls are needed.

**6. How do SSE and NDJSON differ from a JSON array?**  
SSE uses `id/event/data` frames; NDJSON puts one JSON object per line; both suit incremental delivery.

**7. Does `Flux.interval` automatically store events for reconnecting clients?**  
No. The demo is a cold publisher generating fresh data per subscription with no event log or replay.

**8. Why not use `expectBodyList` for an infinite SSE stream?**  
It waits forever for stream completion; use `returnResult`/`StepVerifier` and cancel after asserting the desired events.

**9. Does `doFinally(CANCEL)` prove the browser received every event?**  
No. It reflects subscription lifecycle at the measured boundary, not end-to-end delivery.

**10. Once SSE returns 200 and the pipeline errors, will the HTTP status change to 500?**  
Not reliably. Headers may already be committed; clients must handle stream termination.

**11. Does `@WebFluxTest` start a real Netty TCP server?**  
No. Use `@SpringBootTest(RANDOM_PORT)` to test the real HTTP connector.

**12. Why is a minimum `periodMs` of 25 insufficient protection for production?**  
Because a client can still open many connections; quotas, rate limiting, auth, and monitoring are required.

**13. Does `WebClient` make the downstream API faster?**  
No. It avoids blocking the event loop during I/O, yet still remains subject to network/upstream latency, pool limits, and server quotas.

**14. If streaming clients are slow, is default `onBackpressureBuffer()` always safe?**  
No. Unbounded buffers can trigger OOM; use a bounded strategy and an overflow policy.

**15. Is BlockHound a default WebFlux dependency?**  
No. It is optional instrumentation with JDK/Reactor compatibility requirements and test setup.

## 15. Official Documentation

- Spring Boot 3.5 — **Reactive Web Applications**, WebFlux/Netty and application setup: https://docs.spring.io/spring-boot/3.5/reference/web/reactive.html
- Spring Framework 6.2 — **WebFlux Reactive Core**, SSE/NDJSON streaming and DataBuffer: https://docs.spring.io/spring-framework/reference/6.2/web/webflux/reactive-spring.html
- Spring Framework — **Annotated WebFlux Controllers**, response streaming: https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/responsebody.html
- Project Reactor — **FAQ: How Do I Wrap a Synchronous, Blocking Call?**: https://projectreactor.io/docs/core/release/reference/faq.html#faq.wrap-blocking
- Project Reactor — **Schedulers and Threading**: https://projectreactor.io/docs/core/release/reference/coreFeatures/schedulers.html
- Project Reactor — **Testing with StepVerifier**: https://projectreactor.io/docs/core/release/reference/testing.html
- Spring Framework — **WebTestClient (streaming returnResult)**: https://docs.spring.io/spring-framework/reference/testing/webtestclient.html
- Spring Boot 3.5 — **Testing Spring Boot Applications**: https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html
- Spring Boot 3.5 — **Actuator Metrics**: https://docs.spring.io/spring-boot/3.5/reference/actuator/metrics.html
- Spring Boot 3.5.16 — **Release and last OSS release notice (25/06/2026)**: https://spring.io/blog/2026/06/25/spring-boot-3-5-16-available-now/
- Reactor BlockHound repository/docs (optional instrumentation): https://github.com/reactor/BlockHound

**Conclusion:** Spring WebFlux streaming requires **both an appropriate transport (SSE/NDJSON)** and a **pipeline that truly does not block the event loop**. Emit items through `Flux` with explicit lifecycle and cancellation handling without unbounded memory accumulation; offload legacy synchronous operations cleanly with `Mono.fromCallable.subscribeOn(boundedElastic)` on a bounded scheduler; monitor queues and timeouts; and test both publisher signals and real HTTP streaming. Never equate "returning a Flux" with "the system is non-blocking end to end."