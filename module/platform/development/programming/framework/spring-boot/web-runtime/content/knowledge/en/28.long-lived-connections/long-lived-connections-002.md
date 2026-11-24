# Emitting SSE with SseEmitter in Spring MVC and Flux in Spring WebFlux

## 1. Context: The Server Needs to Push Updates to the Browser

Suppose a Spring Boot system tracks order status, report export progress, or task notifications. After the browser sends an HTTP request to subscribe for updates, the server wants to **send multiple events over time** without the browser repeatedly polling `GET /status` every second. **Server-Sent Events (SSE)** is the standard HTTP solution for a **one-way stream: server → client**.

~~~text
Browser / EventSource                    Spring Boot
        |                                      |
        | GET /events, Accept: text/event-stream
        |------------------------------------->|
        |<-- HTTP 200, text/event-stream ------|
        |                                      |
        |<-- id: 1, event: progress, data:... -|
        |<-- id: 2, event: progress, data:... -|
        |<-- : keep-alive ---------------------|
        |<-- id: 3, event: done, data:... -----|
        |                                      |
        | (connection continues or is closed)  |
~~~

In Spring Boot, there are two common ways to implement this:

1. **Spring MVC/Servlet:** the controller returns `SseEmitter`, the application calls `emitter.send(...)` whenever an event occurs, and manages lifecycle/timeout/cleanup.
2. **Spring WebFlux:** the controller returns `Flux<T>` with `produces = text/event-stream`, often using `Flux<ServerSentEvent<T>>` when `id`, `event`, `retry`, and comments are needed; lifecycle is tied to the reactive subscription.

Both approaches share **the same SSE protocol on the wire** but differ in scheduling, unsubscription, and backpressure handling. This lesson uses **Java 17+, Spring Boot 3.x** and splits into two separate sample projects, without mixing Servlet MVC and WebFlux in one learning app.

SSE is well suited for notifications, job progress, timelines, and moderately frequent market/telemetry snapshots; it is not the default choice for bidirectional chat, binary file transfer, or protocols requiring browser acknowledgments/transactions. For bidirectional communication, consider WebSocket; for simple infrequent updates, polling may be enough.

## 2. How Does SSE Work Over HTTP?

The client typically opens an **HTTP GET**; the server returns HTTP 200 and keeps the response body **streaming**, with `Content-Type: text/event-stream`. The body consists of UTF-8 text records separated by **blank lines**.

Raw format example:

~~~http
HTTP/1.1 200 OK
Content-Type: text/event-stream;charset=UTF-8
Cache-Control: no-cache

id: 101
event: progress
retry: 3000
data: {"jobId":"job-42","percent":20}

id: 102
event: progress
data: {"jobId":"job-42","percent":50}

: keep-alive

id: 103
event: done
data: {"jobId":"job-42","percent":100}

~~~

Significant fields:

| SSE Line | Meaning |
| --- | --- |
| `data: ...` | Event text payload; multiple `data:` lines are joined by a newline character |
| `event: progress` | Event name; JS uses `addEventListener("progress", ...)` to listen |
| `id: 101` | Event ID remembered by EventSource, sent back upon reconnect |
| `retry: 3000` | Reconnect delay hint of **3000 milliseconds**; browsers may apply their own policies |
| `: keep-alive` | Comment, ignored by the browser; helps keep traffic flowing to detect disconnects or avoid idle timeouts |
| Blank line | Ends the record; the browser dispatches the event once the complete record is received |

**If `event: tick` is present, the `onmessage` handler does not receive it as a default event; you must use `addEventListener("tick", handler)`.** If `event:` is omitted, the browser dispatches a `message` event to `onmessage`/the `message` listener. This mistake causes situations where Network shows SSE traffic but the JS callback never runs.

SSE is a text stream, **not** a long JSON array like `[{"a":1},{"b":2}]`. The `data:` payload can hold serialized JSON, but **framing** uses SSE lines and blank lines. Do not print JSON objects back-to-back without `data:` and blank lines.

A multi-line record:

~~~text
event: multiline
data: first line
data: second line

~~~

The client receives one event whose `event.data` is a string containing a newline. Avoid concatenating untrusted input directly into SSE lines, which could let an attacker inject `event:`, `id:`, or new records. Use a framework builder/encoder or escape/serialize properly instead of raw string concatenation.

### SSE Is Not WebSocket

| Criterion | SSE | WebSocket | Polling |
| --- | --- | --- | --- |
| Communication direction | Primarily server → browser, one-way | Bidirectional | Client repeatedly sends requests |
| Transport | HTTP response streaming | HTTP upgrade / WebSocket protocol | Multiple HTTP requests |
| Browser API | `EventSource` | `WebSocket` | `fetch`, timers |
| Auto-reconnect in standard API | EventSource usually retries automatically | Custom logic required | Custom schedule required |
| Event ID/retry fields | Standard `id`, `retry` | Application-defined | Application-defined |
| Direct binary data | No, UTF-8 text; encode if needed | Supports binary frames | Standard support |
| Ease of use with HTTP proxies | Often works; must disable buffering and set timeouts properly | Requires Upgrade support | Usually easiest |
| Server can emit multiple times per request | Yes | Yes | One response/request, then a new request |

**SSE does not guarantee exactly-once delivery.** EventSource's reconnection alone is not enough to prevent lost events between a network drop and server emission. A cursor-backed event log + replay policy is required if business consistency demands it.

## 3. Browser EventSource: Receiver Example

In an HTML page served from the same origin as the backend, use:

~~~javascript
const source = new EventSource("/events/mvc");

source.addEventListener("open", () => {
  console.log("SSE connected");
});

source.addEventListener("tick", (event) => {
  const payload = JSON.parse(event.data);
  console.log("id =", event.lastEventId, "data =", payload);
});

source.addEventListener("done", () => {
  console.log("Server reported completion");
  source.close();
});

source.onerror = (event) => {
  console.warn("SSE failed or reconnecting", event);
};
~~~

Explanation:

- `EventSource(url)` initiates a GET connection and receives complete SSE records.
- `event.data` is **text**, so parse JSON when the backend sends JSON. Include try/catch for malformed payloads in real apps.
- `event.lastEventId` carries the most recent `id` in the event context.
- `source.close()` stops the browser stream; if the server closes the response without the client calling `close()`, EventSource may attempt to reconnect according to standard policy.
- `onerror` does not only mean a 500 backend error; it also fires when the connection drops and the browser prepares to reconnect.
- `EventSource` **does not allow scripts to set arbitrary request headers** such as `Authorization: Bearer ...` under the standard API. For cookie auth, EventSource can use credential mode; for bearer headers, use a streaming `fetch` client/custom polyfill or a secure BFF pattern.

The frontend examples for the two projects will differ in path:

- MVC: `http://localhost:8081/events/mvc`.
- WebFlux: `http://localhost:8082/events/reactive`.

If the HTML page and API are on different origins, **CORS** must be configured in addition to SSE. Security details follow later.

## 4. Spring MVC SseEmitter Architecture

Spring MVC runs on a Servlet stack (e.g., embedded Tomcat). `SseEmitter` extends `ResponseBodyEmitter`, allowing a controller to return the emitter **immediately** and send data from another thread/task over time.

~~~text
HTTP request /events/mvc
            |
            v
Spring MVC controller
            |
            +-- create SseEmitter(timeout)
            +-- register onCompletion/onTimeout/onError
            +-- register event source
            |
            +-- return SseEmitter / ResponseEntity<SseEmitter>
                  |
                  v
             Servlet async request
                  |
                  +---- background scheduler/task ----> emitter.send(...)
                  |                               |
                  |                               +--> event: tick, id, data
                  |
                  +---- disconnect / timeout / complete --> cleanup
~~~

This is **Servlet async request processing**, not a non-blocking I/O reactive API like WebFlux. Even though the controller thread returns quickly, that **does not mean every socket write is non-blocking**. `SseEmitter.send` uses message converters and writes the response through Servlet infrastructure; writes can block worker threads when downstream is slow. Do not create a permanent thread per client or leave an unbounded executor.

### Important SseEmitter APIs

| API | Role |
| --- | --- |
| `new SseEmitter(timeoutMillis)` | Creates an emitter with timeout in milliseconds; do not pass `Duration` directly to this constructor |
| `SseEmitter.event().id("1")` | Sets event ID |
| `.name("tick")` | Sets `event: tick` |
| `.data(object)` | Adds `data: ...`; a message converter can serialize a DTO into JSON |
| `.reconnectTime(3000L)` | Sets `retry: 3000` |
| `.comment("keep-alive")` | Sends an SSE comment, useful as a heartbeat |
| `emitter.send(builder)` | Writes one SSE event |
| `emitter.complete()` | Completes normally |
| `emitter.completeWithError(ex)` | Completes due to an application error other than a standard write-disconnect |
| `onCompletion(Runnable)` | Callback when the request has completed, used for cleanup |
| `onTimeout(Runnable)` | Callback on async timeout |
| `onError(Consumer<Throwable>)` | Callback when async processing encounters an error |

An important detail from the Spring Framework documentation: if `send` throws an **`IOException` because the client went away**, the app does not need to call `complete()` or `completeWithError()` to try to fix the write path; the servlet container raises an async error notification and Spring MVC handles it. The app should **stop the producer and clean up resources**, letting the framework lifecycle finish.

Not every error is an IOException: serialization or business computation errors may require `completeWithError` before the response commits. Once a response has streamed part of its body, an exception handler cannot change the HTTP status from 200 to 500 as usual; emit a structured error event and/or close the stream per policy.

## 5. Project A: Runnable Spring MVC + SseEmitter with Java 17+

This example emits five `tick` events, one per second, then sends `done` and closes the response. The EventSource client listens for `done` and calls `close()` so it does not reconnect indefinitely after the short stream ends.

This is a **dedicated Servlet MVC project**; **do not** add `spring-boot-starter-webflux`.

### 5.1. Structure

~~~text
mvc-sse-lab/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/demo/mvcsse/MvcSseApplication.java
    │   └── resources/application.properties
    └── test/
        └── java/demo/mvcsse/MvcSseTest.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'mvc-sse-lab'
~~~

`build.gradle`, e.g., Spring Boot 3.3.13 + Java 17:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.6'
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
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

`src/main/resources/application.properties`:

~~~properties
server.port=8081

# Servlet async timeout can be capped at multiple layers.
# The controller below uses SseEmitter(20000L) for the short sample stream.
spring.mvc.async.request-timeout=30s
~~~

Do not treat `spring.mvc.async.request-timeout` as the lifetime of every SSE connection: `SseEmitter` has its own timeout, and servlet containers and proxies have different timeouts. Production must calculate long-stream requirements, heartbeats, cancellation, and connection quotas rather than just setting every timeout to infinity.

### 5.2. Standalone Runnable Source Code

File `src/main/java/demo/mvcsse/MvcSseApplication.java`:

~~~java
package demo.mvcsse;

import java.io.IOException;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

@SpringBootApplication
public class MvcSseApplication {
    public static void main(String[] args) {
        SpringApplication.run(MvcSseApplication.class, args);
    }

    @Bean(destroyMethod = "shutdown")
    ScheduledExecutorService sseScheduler() {
        return Executors.newScheduledThreadPool(4);
    }
}

@RestController
class MvcSseController {
    private final ScheduledExecutorService scheduler;

    MvcSseController(ScheduledExecutorService scheduler) {
        this.scheduler = scheduler;
    }

    record Tick(int sequence, String message) { }

    @GetMapping(path = "/events/mvc",
                produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    ResponseEntity<SseEmitter> events() {
        SseEmitter emitter = new SseEmitter(20_000L);
        AtomicInteger counter = new AtomicInteger();
        AtomicReference<ScheduledFuture<?>> taskRef =
                new AtomicReference<>();

        Runnable cancelTask = () -> {
            ScheduledFuture<?> task = taskRef.get();
            if (task != null) {
                task.cancel(false);
            }
        };

        emitter.onCompletion(cancelTask);
        emitter.onTimeout(cancelTask);
        emitter.onError(error -> cancelTask.run());

        Runnable publish = () -> {
            int number = counter.incrementAndGet();

            try {
                emitter.send(SseEmitter.event()
                        .id("mvc-" + number)
                        .name("tick")
                        .reconnectTime(3000L)
                        .data(new Tick(number, "event-" + number)));

                if (number == 5) {
                    emitter.send(SseEmitter.event()
                            .name("done")
                            .data("finished"));
                    emitter.complete();
                    cancelTask.run();
                }
            } catch (IOException disconnected) {
                // Client may have disconnected. Container manages async error.
                cancelTask.run();
            } catch (RuntimeException unexpected) {
                cancelTask.run();
                emitter.completeWithError(unexpected);
            }
        };

        ScheduledFuture<?> task = scheduler.scheduleAtFixedRate(
                publish, 1, 1, TimeUnit.SECONDS);
        taskRef.set(task);

        return ResponseEntity.ok()
                .contentType(MediaType.TEXT_EVENT_STREAM)
                .header(HttpHeaders.CACHE_CONTROL, "no-cache, no-transform")
                .header("X-Accel-Buffering", "no")
                .body(emitter);
    }
}
~~~

### 5.3. Detailed Controller Explanation

- `@GetMapping(... produces = TEXT_EVENT_STREAM_VALUE)` declares an SSE response. `ResponseEntity<SseEmitter>` lets you add headers such as Cache-Control and `X-Accel-Buffering`.
- `new SseEmitter(20_000L)` times out after about 20 seconds under the servlet async lifecycle; the lab sends 5 events across 1–5 seconds, which is well under the timeout.
- `ScheduledExecutorService` is a **shared bean**, avoiding creating a new thread/executor per connection. `@Bean(destroyMethod = "shutdown")` tells Spring to shut down the scheduler when the application context closes.
- Each connection has its own `AtomicInteger`/`taskRef` and a scheduled task. `onCompletion`/`onTimeout`/`onError` cancel the task so emitters without clients are not retained.
- `SseEmitter.event().id().name().reconnectTime().data()` uses the builder API, avoiding manual string concatenation and ensuring proper event framing.
- The `Tick` DTO is a Java record with `sequence`/`message` fields; Jackson from Spring Web starter serializes it into a JSON object.
- On the fifth iteration, `done` is also sent. The browser must handle `done` by calling `EventSource.close()` so it does not reconnect after a finite stream.
- An `IOException` when writing after a disconnect is normally handled by the container/Spring via the async error lifecycle. The app cancels the producer and **does not** attempt to call `completeWithError` for a write-disconnect. Other runtime/serialization errors can call `completeWithError`; at that point the HTTP response may already be committed and its status can no longer be changed normally.
- `no-cache, no-transform` is a demo policy to limit intermediary caching/rewriting; `no-cache` **is not `no-store`**. For notifications containing personal data, switch to `Cache-Control: no-store, no-transform` and bypass CDN caching.
- `X-Accel-Buffering: no` is understood by the NGINX proxy module in compatible configurations; it does not guarantee every CDN/proxy disables buffering.

**Demo limitation:** There is one scheduled task per client, and `send` can occupy a thread when the network is slow. Do not use this 4-thread executor for tens of thousands of connections. Production needs connection limits, bounded scheduling/queues, monitoring, worker isolation, and evaluating WebFlux if most of the pipeline is non-blocking.

### 5.4. Running and Observing

If you have the Gradle wrapper:

~~~bash
./gradlew bootRun
~~~

On Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

If there is no wrapper yet, generate one with a compatible Gradle version or use an installed Gradle binary to run. The server listens on `localhost:8081`.

Using cURL, the `-N`/`--no-buffer` option disables **cURL output buffering**:

~~~bash
curl -N -i -H "Accept: text/event-stream" \
  http://localhost:8081/events/mvc
~~~

Expect HTTP 200 and `Content-Type: text/event-stream`, followed every second by a record like:

~~~text
id:mvc-1
event:tick
retry:3000
data:{"sequence":1,"message":"event-1"}

id:mvc-2
event:tick
retry:3000
data:{"sequence":2,"message":"event-2"}

...
event:done
data:finished

~~~

Spaces after colons, serialization order/style, or metadata headers can vary by message converter and Spring version. What to verify is **5 tick events, sequential IDs, and 1 done event**. `curl` exits when the server completes the response; `EventSource` does not inherently know this is the business end, so the client needs `close()` on `done`.

### 5.5. Browser Testing

Open DevTools on a frontend with the same origin or via an appropriate CORS/same-origin reverse proxy:

~~~javascript
const es = new EventSource("/events/mvc");

es.addEventListener("tick", event => {
  const tick = JSON.parse(event.data);
  console.log("MVC", event.lastEventId, tick.sequence, tick.message);
});

es.addEventListener("done", () => {
  console.log("MVC stream finished");
  es.close();
});

es.onerror = err => console.error("MVC SSE connection issue", err);
~~~

If the HTML is opened from `http://localhost:5173` and the API is on `http://localhost:8081`, they have **different origins**; CORS must be configured, otherwise the browser blocks the response. Alternatively, use a reverse proxy or frontend dev-server proxy so both share the same origin and CORS is unnecessary.

## 6. Spring MVC Async Timeout, Disconnect, and Resource Cleanup

### 6.1. Timeouts Have Multiple Layers

| Layer | Meaning |
| --- | --- |
| `SseEmitter(20000L)` | Timeout tied to the async lifecycle of the emitter/request |
| `spring.mvc.async.request-timeout` | Default MVC async request timeout if not overridden on the emitter |
| Servlet container | Async request support, connector/response settings |
| Load balancer/CDN/NGINX | Upstream/downstream idle/read timeout |
| Browser/network | TCP connection, tab sleep, network transitions, EventSource reconnect |
| Application | Business timeout milestone and stream count policy |

Setting `SseEmitter(0L)` or a huge timeout does not keep a stream alive forever: networks and proxies can still drop it due to idleness, quotas, or deployments. For long-lived SSE, use heartbeats with a period **shorter than the intermediary's idle timeout**; measure in the actual environment rather than guessing a fixed number.

### 6.2. Why Are Heartbeats Needed?

According to Spring MVC documentation, the Servlet API does not provide reliable immediate notification merely because a TCP peer went away. In streaming, periodic writes surface write failures once a client has disconnected. You can send a comment-only event:

~~~java
// Snippet on an active SseEmitter, called from a worker/scheduler:
emitter.send(SseEmitter.event().comment("keep-alive"));
~~~

A `: keep-alive` comment is ignored by EventSource and does not trigger `onmessage`. Separate heartbeats from business events to avoid incrementing sequence numbers or `Last-Event-ID` unnecessarily.

**Do not create a new scheduler per request** or send forever without cleanup. On timeout, error, completion, or user logout, cancel the publisher/task and remove references from registries to prevent memory leaks.

### 6.3. Multi-Subscriber Registry in MVC

If the business logic broadcasts events, the app typically maintains a registry of active `SseEmitter` instances per user/tenant/topic, e.g., a `ConcurrentHashMap<...>` or thread-safe set. Rules:

1. Add the emitter when the connection is authorized to subscribe.
2. Remove the emitter in `onCompletion`, `onTimeout`, `onError`, and when sending fails.
3. Sending must not hold a registry lock for long; avoid letting one slow socket block all other clients.
4. Never emit tenant A's data to tenant B's emitter; key by authenticated principal, never trusting a client-supplied userId.
5. Cap connections/subscribers per user and per node, with capacity limits and eviction policies.
6. A JVM registry **belongs to a single node**; when running multiple instances, wire broadcast sources through a broker/pubsub or design affinity—do not assume registries share themselves.

The lab example omits a global registry because each connection has its own stream. That is intentional to avoid turning an SSE lesson into a pub/sub infrastructure without capacity policies.

### 6.4. Blocking Writes and Schedulers

Servlet async frees the request thread once the controller returns the emitter, but calling `send` can still perform blocking I/O/serialization on a worker thread. For a few connections, the demo scheduled executor suffices; for many connections:

- Use bounded task queues, thread pool metrics, and a per-client write strategy.
- Bound event queues for slow clients; you may drop older snapshots if data represents "latest state", but **never drop financial events requiring audit**.
- Rate-limit connects/reconnects, cap active emitters, and detect stuck tasks.
- Align timeouts across the servlet, LB, CDN, client heartbeat, and business SLA.
- If the data source is already reactive/non-blocking and concurrent stream counts are high, evaluate WebFlux.

Do not conclude that merely changing a return type to `Flux` inside an MVC app turns the pipeline into reactive Netty. Spring MVC can adapt Reactor types for streaming, but underlying Servlet response writes remain blocking on the async executor; configure an appropriate executor.

## 7. Spring WebFlux: Flux Is the Reactive Stream, ServerSentEvent Is SSE Metadata

Spring WebFlux runs with a reactive server (typically Reactor Netty) and reactive HTTP codecs. A controller can return:

~~~java
@GetMapping(path = "/events", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
public Flux<String> events() {
    return Flux.just("one", "two");
}
~~~

With media type `text/event-stream`, each element is written as an SSE data event. However, if you need `id`, `event`, `retry`, and comments, return:

~~~java
Flux<ServerSentEvent<MyEvent>>
~~~

and build each element with `ServerSentEvent.builder(...)`.

**Flux** is a Publisher capable of emitting 0..N values over time and supports reactive demand/cancellation. **`ServerSentEvent<T>`** is a wrapper for **a single SSE record**, not a Kafka message, WebSocket frame, or standalone HTTP response.

~~~text
GET /events/reactive
       |
       v
WebFlux Handler
       |
       v
Flux<ServerSentEvent<Tick>>
       |    event 1
       |    event 2
       |    ...
       |
       v
SSE encoder -> Reactor Netty -> HTTP text/event-stream
       |
Client cancels/disconnects
       |
       v
Reactive subscription canceled; upstream can release resources
~~~

This reduces the need to hold a Servlet write thread per active stream, **provided downstream dependencies are also non-blocking**. Calling blocking JDBC or `Thread.sleep` on the WebFlux event loop defeats the benefit and stalls the entire server.

## 8. Project B: Runnable Spring WebFlux + Flux<ServerSentEvent<Tick>>

This project is **completely independent** from the MVC lab; it adds only `spring-boot-starter-webflux`, without `spring-boot-starter-web`. The example also emits 5 ticks and then done.

### 8.1. Structure

~~~text
webflux-sse-lab/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/demo/fluxsse/FluxSseApplication.java
    │   └── resources/application.properties
    └── test/
        └── java/demo/fluxsse/FluxSseTest.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'webflux-sse-lab'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.6'
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
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

`src/main/resources/application.properties`:

~~~properties
server.port=8082
~~~

### 8.2. Runnable Source Code

File `src/main/java/demo/fluxsse/FluxSseApplication.java`:

~~~java
package demo.fluxsse;

import java.time.Duration;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@SpringBootApplication
public class FluxSseApplication {
    public static void main(String[] args) {
        SpringApplication.run(FluxSseApplication.class, args);
    }
}

record Tick(int sequence, String message) { }

@RestController
class ReactiveSseController {
    @GetMapping(path = "/events/reactive",
                produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    ResponseEntity<Flux<ServerSentEvent<Tick>>> events() {
        Flux<ServerSentEvent<Tick>> ticks =
                Flux.interval(Duration.ofSeconds(1))
                        .take(5)
                        .map(index -> {
                            long number = index + 1;

                            return ServerSentEvent
                                    .<Tick>builder(
                                            new Tick((int) number,
                                                     "event-" + number))
                                    .id("flux-" + number)
                                    .event("tick")
                                    .retry(Duration.ofSeconds(3))
                                    .build();
                        });

        ServerSentEvent<Tick> done = ServerSentEvent
                .<Tick>builder(new Tick(0, "finished"))
                .event("done")
                .build();

        Flux<ServerSentEvent<Tick>> stream = ticks
                .concatWith(Mono.just(done))
                .doFinally(signal ->
                        System.out.println("SSE terminated: " + signal));

        return ResponseEntity.ok()
                .contentType(MediaType.TEXT_EVENT_STREAM)
                .header(HttpHeaders.CACHE_CONTROL, "no-cache, no-transform")
                .header("X-Accel-Buffering", "no")
                .body(stream);
    }
}
~~~

### 8.3. Operator and Lifecycle Analysis

- `Flux.interval(Duration.ofSeconds(1))` emits ascending `Long` values **0, 1, 2, ...**, starting after ~1 second. It does not call `Thread.sleep`.
- `take(5)` limits to five values, then completes upstream. Because the source is cold per subscription, each client gets its own sequence of five ticks in this example.
- `index + 1` creates sequences 1..5. `ServerSentEvent.<Tick>builder(...)` holds the DTO data; `.id(...)`, `.event("tick")`, `.retry(Duration.ofSeconds(3))` produce the SSE metadata.
- `concatWith(Mono.just(done))` emits the `done` event only **after** the five ticks finish. The client uses `done` to close EventSource proactively and avoid a reconnect loop.
- `doFinally(signal -> ...)` receives the termination signal (`onComplete`, `cancel`, or `onError`) and is the right place to record metrics or release resources. The example prints to stdout for observation; avoid logging raw user tokens or session IDs.
- `ResponseEntity<Flux<ServerSentEvent<Tick>>>` adds headers without turning the stream into a list or waiting for all values before returning.
- **Do not call `collectList()` or `block()` in the controller**: `collectList` turns the stream into a collection rather than emitting incrementally; `block` can stall the event loop or break the reactive runtime.
- When the browser disconnects, WebFlux can cancel the subscription; cooperative sources and operators will release resources. Do not assume every dependency (blocking APIs, custom hot sources, brokers) cancels cleanly on its own; implement explicit cleanup and tuning.

### 8.4. Running and Observing

In the WebFlux project:

~~~bash
./gradlew bootRun
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

Connect with cURL:

~~~bash
curl -N -i -H "Accept: text/event-stream" \
  http://localhost:8082/events/reactive
~~~

Expect 200 + `text/event-stream` and records:

~~~text
id:flux-1
event:tick
retry:3000
data:{"sequence":1,"message":"event-1"}

id:flux-2
event:tick
retry:3000
data:{"sequence":2,"message":"event-2"}

...
event:done
data:{"sequence":0,"message":"finished"}

~~~

Spacing, field ordering, and server headers may vary; verify logical content rather than comparing printed output byte-for-byte. When disconnecting cURL with Ctrl+C, `doFinally` may print `cancel` if cancellation propagates to the Publisher.

### 8.5. Frontend Listening to the Reactive Stream

~~~javascript
const es = new EventSource("/events/reactive");

es.addEventListener("tick", event => {
  const tick = JSON.parse(event.data);
  console.log("WebFlux", event.lastEventId, tick);
});

es.addEventListener("done", event => {
  console.log("Finished", JSON.parse(event.data));
  es.close();
});

es.onerror = error => {
  console.warn("Connection issue/reconnect", error);
};
~~~

If the page is hosted on a different origin, configure CORS or a reverse proxy, just as with MVC. EventSource does not automatically know the server sent `done` if JS does not listen for the right event name.

## 9. Comparing MVC SseEmitter and WebFlux Flux by Responsibility

| Aspect | Spring MVC + SseEmitter | Spring WebFlux + Flux |
| --- | --- | --- |
| Web stack | Servlet container, e.g., Tomcat | Reactive stack, typically Reactor Netty |
| Controller return | `SseEmitter` or `ResponseEntity<SseEmitter>` | `Flux<ServerSentEvent<T>>` or `ResponseEntity<Flux<...>>` |
| Data emission | Worker/task calls `emitter.send` | Publisher emits `onNext` per subscription/demand |
| Event metadata | `SseEmitter.event().id().name().data()` | `ServerSentEvent.builder().id().event().data()` |
| Completion | `emitter.complete()` | Publisher completes after the final element |
| Disconnect | Async callbacks + write errors; must clean up tasks/registry | Cancellation signal; requires cooperative upstream |
| Timeout | `SseEmitter(timeoutMillis)`, Servlet/proxy | Timeouts/reactive operators/proxy/server configs |
| Backpressure | No protocol-level demand from EventSource; writes can block | Reactor demand/cancellation in pipeline, but TCP and event sources still need capacity controls |
| Resources | Must balance blocking writes and worker threads | Advantageous for high connection counts if dependencies are non-blocking |
| Blocking data sources | MVC/JDBC usually easier to integrate | Must offload or move to non-blocking; never block event loop |
| Multi-node | Emitter registry is local to each JVM | Subscriptions/hot sources are local to each instance without a broker |
| Browser | EventSource, same SSE protocol | EventSource, same SSE protocol |

**Do not assume WebFlux is always faster.** With modest stream counts and an app largely built on blocking Spring MVC/JPA, `SseEmitter` can be simpler. With many long-lived connections and an end-to-end reactive stack, WebFlux can use resources more efficiently, provided memory, slow clients, hot publishers, and consistency are controlled.

Spring MVC can accept reactive return types such as `Flux` when Reactor is on the classpath. However, MVC adapts the stream to a Servlet async response with blocking writes via an executor; **that does not mean the app switched to Netty WebFlux**. If both `spring-boot-starter-web` and `spring-boot-starter-webflux` are present in Boot, Boot normally defaults to MVC/Servlet; always verify the active web application type.

## 10. Hard Problems: Backpressure, Slow Clients, and Memory

### 10.1. SSE Has No Per-Event ACK

EventSource does not send an ACK back to the server for each `id`. `Last-Event-ID` only appears during reconnection and does not prove the server durably persisted the event or the client processed it properly. Consequently, when a producer is faster than the client/network:

~~~text
Broker emits: 1000 events/s
                 |
                 v
SSE server ------ TCP/HTTP -----> Slow browser 10 events/s
       |
       +--> growing queue / blocked writes / memory pressure
~~~

If the producer pushes indefinitely into an unbounded queue, the app can OOM; if using a worker thread per slow client, the thread pool can be exhausted.

### 10.2. Strategies by Data Type

- **Current state snapshots:** coalesce or drop intermediate updates, e.g., emit only the latest state every 500 ms. Document clearly that intermediate values are not guaranteed.
- **Re-displayable notifications:** use a bounded replay window and cursor, letting the client resync on gaps.
- **Critical business events that must not be lost:** persist to a durable log/DB/broker first; SSE is merely the **delivery channel**, not the sole source of truth.
- **Slow clients:** bound queues and total connections, measure write latency, drop overly slow streams, or instruct the client to resync when thresholds are exceeded.
- **Hot Flux publishers:** use bounded `onBackpressureBuffer` with an overflow policy; `onBackpressureLatest` drops older events and should only be used when semantics allow it. `Sinks.Many` requires choosing multicast/replay/overflow strategies; do not assume Reactor provides a safe infinite queue.
- **MVC schedulers:** limit task/thread counts and avoid letting a single blocked `send` stall the entire pool.

In WebFlux, reactive backpressure coordinates producer/consumer demand inside the pipeline, but **it does not turn SSE into an exactly-once protocol** nor eliminate the need for capacity planning.

## 11. Reconnect, Last-Event-ID, and Replay: Must Be Designed Intentionally

EventSource usually reconnects automatically when a connection drops, and may send:

~~~http
GET /events HTTP/1.1
Last-Event-ID: 103
Accept: text/event-stream
~~~

`Last-Event-ID` comes from the `id:` values the client has seen; an empty event ID (`id:`) can reset the stored value. `retry: 3000` suggests the reconnect interval in milliseconds.

**Important:** simply setting `id` on `SseEmitter` or `ServerSentEvent` **does not create an event log or replay**. Both lab projects start the 1..5 sequence anew on every connection; if the browser reconnects, it receives the sequence from the beginning again. That is intentional for the demo, **not sufficient** for a system that must resume accurately after disconnect.

### Designing Replay in Production

1. Assign durable, ordered event IDs within **a clear stream scope** (per user/tenant/topic), rather than using a JVM-local counter as a system-wide ID.
2. Write events to a DB/durable log or a stream with clear retention.
3. When a client connects/reconnects, authenticate the principal and check stream read permissions **before** processing the cursor.
4. Read `Last-Event-ID`, validate format, scope, authorization, retention, and ordering; reject or force a resync if the ID belongs to another tenant, is too old, or does not exist.
5. Replay events **after the cursor** and seamlessly continue the live stream, ensuring the transition from replay to live creates no gaps via consistent offset/ordering design.
6. Clients can receive duplicates at the reconnect boundary; deduplicate by event ID and make state-updating handlers idempotent.
7. When the cursor falls outside retention, send a `resync-required` signal or tell the client to fetch a fresh snapshot and reopen the stream.
8. Never trust `Last-Event-ID` as proof of authorization: non-browser clients can forge that header freely.

Diagram:

~~~text
Business event producer -> Durable event store/broker
                                      |
                         +------------+------------+
                         |                         |
                    Spring node A             Spring node B
                         |                         |
                         +-----------+-------------+
                                     |
                         GET /events + Last-Event-ID
                                     |
                        auth + replay + live subscription
                                     |
                             Browser EventSource
~~~

### Distinguishing At-Most-Once, At-Least-Once, and Exactly-Once

An HTTP stream can break right as the server writes data before the browser processes it. Therefore, a system cannot rely solely on socket write behavior to know an event was processed exactly once. For events requiring accuracy, use durable event IDs, idempotency, and corresponding business transactions. SSE delivery typically has to tolerate **duplicates or gaps** and resolve them in the application protocol.

## 12. Authentication and Authorization for SSE

An SSE endpoint is a **real HTTP endpoint** that can stay open for a long time. Authenticate before subscribing, authorize per user/tenant/topic, and plan for revocation while the connection is open.

### 12.1. Cookie/Session

Browser EventSource can use same-origin cookies. For a cross-origin API, if cookies must be sent:

~~~javascript
const es = new EventSource("https://api.example.test/events", {
  withCredentials: true
});
~~~

The backend must configure CORS with a specific `Access-Control-Allow-Origin`, `Access-Control-Allow-Credentials: true`, and cookies must satisfy `Secure`, `SameSite`, Domain/Path, and browser third-party-cookie policies. `Access-Control-Allow-Origin: *` **is invalid with credentialed browser CORS**.

**Do not treat CORS as authentication.** CORS only controls whether JS on another website can read the response; non-browser servers/clients can still call the endpoint. `SecurityFilterChain`/`SecurityWebFilterChain` and domain authorization remain mandatory. Cookies sent automatically require evaluating the CSRF threat model for state-changing endpoints; SSE GET should be read-only and never perform business side effects on GET.

### 12.2. Bearer Token

Native `EventSource` does not support arbitrary request headers such as:

~~~http
Authorization: Bearer ...
~~~

If the API uses bearer access tokens in headers, common options are:

- Use streaming `fetch` with `Authorization` and a client-side SSE parser (handling framing/reconnect/Last-Event-ID yourself or via a vetted library).
- Use a same-origin BFF with secure HttpOnly cookies where the BFF holds the token server-side and opens the stream to the backend.
- Use a short-lived, single-use, identity-bound ticket mechanism if truly necessary, rather than carelessly placing long-lived access tokens in query strings where they leak into logs, history, and analytics.

Do not put tokens in `?token=...` as a production shortcut. Analyze XSS, CSRF, CORS, cookie policies, and token rotation according to your app architecture.

### 12.3. Permissions Can Change While the Stream Is Open

Checking permissions at connect time **is not enough** for streams lasting hours: roles may be revoked, tenant memberships may change, or accounts may be locked. The system may need:

- A maximum stream lifetime forcing periodic reconnect/re-authentication.
- Pushing a revoke signal / canceling subscriptions when a user logs out or is disabled.
- Re-evaluating permissions before emitting sensitive data per policy.
- Preventing tenant B's data from being broadcast to tenant A's emitters/subscribers.
- Monitoring which principal a connection belongs to without logging raw session IDs or tokens.

An authenticated user with `ROLE_USER` does not automatically have permission to subscribe to someone else's `/events/orders/{orderId}`. Query/stream routing must be scoped by owner/tenant, just like REST APIs.

## 13. Proxies, CDNs, and Timeouts Determine Whether Streaming Is "Real"

The most common failure when deploying SSE: Spring called `send` or Flux emitted, yet the client receives events **batched all at once after 30 seconds** or the connection is cut periodically. The usual culprits are proxy buffering, idle timeouts, compression buffering, CDNs not supporting streaming as expected, or HTTP topology.

### 13.1. NGINX Example for SSE

The following NGINX snippet **requires** a `spring_backend` upstream and environment server config; it is not a standalone `nginx.conf`:

~~~nginx
location /events/ {
    proxy_pass http://spring_backend;
    proxy_http_version 1.1;
    proxy_set_header Connection "";
    proxy_buffering off;
    proxy_cache off;
    proxy_read_timeout 3600s;
}
~~~

Explanation:

- `proxy_buffering off`: forwards data downstream as soon as it arrives instead of waiting for buffers to fill.
- `proxy_cache off`: disables shared caching of the stream response. For personal data, the origin should also emit `Cache-Control: no-store`.
- `proxy_read_timeout 3600s` is the limit for **receiving no bytes from upstream for a continuous period**, not necessarily total connection duration. Heartbeats must use an appropriate cadence, and cloud LBs/proxies have their own timeouts.
- `proxy_http_version 1.1` and `Connection ""` keep the upstream connection suitable for HTTP streaming in common configurations; test against your actual topology.
- `X-Accel-Buffering: no` from the origin can be honored by NGINX when configuration allows; it does not override buffering in an upstream CDN.

A CDN or WAF in front of NGINX can introduce its own buffering, caching, response duration limits, or compression. Test via **the public hostname across all hops** and compare with calling the Spring Boot port directly.

### 13.2. Heartbeat and Flush

An SSE heartbeat comment can prevent idle timeouts **if** intermediaries actually forward bytes rather than buffering them. Simply setting a high `proxy_read_timeout` without sending any bytes for minutes can still cause mobile networks or TCP paths to drop. Conversely, overly frequent heartbeats across tens of thousands of clients create unnecessary overhead.

Choose the heartbeat interval through measurement: e.g., 15–30 seconds when proxy/LB timeouts are noticeably higher, without applying one magic number to every system. Measure the real elapsed time between server emission and browser receipt, not just server logs.

### 13.3. HTTP/1.1 and HTTP/2

With HTTP/1.1, browsers enforce a limit on concurrent connections per origin, and each EventSource occupies a long-lived connection. Opening many tabs/streams can starve other `fetch` requests. HTTP/2 multiplexing shares connections, though stream counts remain bounded by negotiated limits between client, server, and proxy; they are not infinite.

Account for users opening multiple tabs, reconnect storms after deploys, mobile sleep/resume, and rolling restarts. Multiplex topics over a single stream using the `event:` field where appropriate instead of opening many independent EventSource instances.

## 14. The Multi-Instance Problem: Emitters and Subscribers Are Not Shared Automatically

Suppose:

~~~text
Client A -- LB --> Spring node 1 -- SseEmitter A
Client B -- LB --> Spring node 2 -- SseEmitter B

Business event processed on node 3
~~~

If node 3 only invokes its in-memory emitter registry, A and B receive nothing. Each JVM has its own registry/subscriptions. A shared bus is required:

~~~text
Business services
       |
       v
Redis Pub/Sub / Kafka / RabbitMQ / DB change stream
       |
       +--> Node 1 -> node 1 emitters/subscriptions
       +--> Node 2 -> node 2 emitters/subscriptions
       +--> Node 3 -> node 3 emitters/subscriptions
~~~

Do not treat all brokers as equivalent:

- Redis Pub/Sub is simple for live notifications, **not durable replay** if a subscriber is offline.
- Redis Streams/Kafka/event logs can support cursor/replay depending on policy and retention.
- MQ/DB transactions/outbox help align emitted events with business state; idempotency is still required.
- Topic/user routing must enforce authorization. Do not broadcast all PII to every node/client and rely on the frontend to filter it.
- Sticky load balancing is not an event delivery protocol; a node restart still closes the HTTP stream and the browser reconnects. Only a shared durable event log supports meaningful resume.

If you only need to display current state, you can resync via a REST snapshot after reconnect instead of building a full event log.

## 15. Testing MVC SSE: Verifying the Request Is Async

In the MVC project, add `src/test/java/demo/mvcsse/MvcSseTest.java`:

~~~java
package demo.mvcsse;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.request;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class MvcSseTest {
    @Autowired
    MockMvc mvc;

    @Test
    void sseUsesAsyncServletProcessing() throws Exception {
        mvc.perform(get("/events/mvc")
                .accept(MediaType.TEXT_EVENT_STREAM))
            .andExpect(status().isOk())
            .andExpect(request().asyncStarted())
            .andExpect(content().contentTypeCompatibleWith(
                    MediaType.TEXT_EVENT_STREAM));
    }
}
~~~

Run:

~~~bash
./gradlew test --tests demo.mvcsse.MvcSseTest
~~~

This test verifies that **an async request started**, along with the response status and media type. It **does not** test real network streaming, proxy buffering, or all 5 events. A `MockMvc` test using `asyncDispatch` can assert the content of a finite stream once the emitter completes, provided you pick a suitable timeout and avoid hanging on infinite streams.

To inspect individual events at runtime, use `curl -N` or an HTTP streaming integration test against a real port; compare sequential IDs, event names, and payloads at each interval. Test disconnects by aborting cURL / calling `EventSource.close()` and observing cleanup/metrics rather than checking HTTP status alone.

## 16. Testing WebFlux SSE: WebTestClient + StepVerifier

In the WebFlux project, create `src/test/java/demo/fluxsse/FluxSseTest.java`:

~~~java
package demo.fluxsse;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive
        .AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.test.web.reactive.server.WebTestClient;

import reactor.test.StepVerifier;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class FluxSseTest {
    @Autowired
    WebTestClient client;

    @Test
    void firstEventHasNameIdAndPayload() {
        var result = client.get()
                .uri("/events/reactive")
                .accept(MediaType.TEXT_EVENT_STREAM)
                .exchange()
                .expectStatus().isOk()
                .expectHeader().contentTypeCompatibleWith(
                        MediaType.TEXT_EVENT_STREAM)
                .returnResult(
                    new ParameterizedTypeReference<
                        ServerSentEvent<Tick>>() { });

        StepVerifier.create(result.getResponseBody().take(1))
                .expectNextMatches(event ->
                        "tick".equals(event.event())
                        && "flux-1".equals(event.id())
                        && event.data() != null
                        && event.data().sequence() == 1)
                .verifyComplete();
    }
}
~~~

Run:

~~~bash
./gradlew test --tests demo.fluxsse.FluxSseTest
~~~

`WebTestClient` checks the streaming response; `StepVerifier` subscribes, consumes one event, and `take(1)` cancels upstream without waiting the full 5 seconds. This demonstrates cancellation tied to consumption. To test all five ticks and `done`, consume six records, assert `event`/`id`/payload in order, and set an appropriate timeout.

**Note:** `RANDOM_PORT` + `@AutoConfigureWebTestClient` exercises the reactive HTTP runtime, yet still bypasses external CDNs/ingress. Only an HTTP streaming test through a public URL/staging environment reveals real buffering and idle timeouts.

## 17. Common Errors and How to Diagnose Them

| Symptom | Common Cause | Resolution |
| --- | --- | --- |
| Browser SSE call gets 404 | Wrong path/port, controller not scanned | Check mapping, app type, and URL |
| HTTP 406 Not Acceptable | Incompatible `produces`/Accept | Use `text/event-stream` properly |
| Network 200 but UI doesn't update | Event is named `tick`, JS only uses `onmessage` | `addEventListener("tick", ...)` |
| Events arrive all in one batch | NGINX/CDN/compression buffering | Disable buffering, test `curl -N` against origin and public URL |
| Connection drops after 30/60s | Servlet async timeout, proxy idle timeout, cloud LB | Align timeouts and heartbeats |
| MVC runs out of threads under many clients | Per-client threads, blocking writes, small/unbounded executor | Bounded pool, quotas, evaluate WebFlux |
| Emitter remains in map after disconnect | Missing cleanup handlers | Register `onCompletion`/`onError`/`onTimeout` and remove from registry |
| `send` throws IOException | Client disconnected, network failure | Stop producer, let container async error lifecycle handle it |
| WebFlux does not stream to browser | Using `collectList()`/blocking logic or wrong media type | Return `Flux` with `text/event-stream` |
| `block()` causes errors/lag on Netty | Blocking call on event loop | Use reactive I/O or offload blocking properly |
| Browser keeps reconnecting after done | Server only calls `complete()`, client never calls `close()` | Send named `done` event and close EventSource |
| Reconnect loses events | No durable log/replay | `Last-Event-ID` + event store/REST resync |
| Reconnect receives duplicates | Replay/live overlap and at-least-once delivery | Idempotent client and deduplication by event ID |
| OAuth2 bearer cannot go through EventSource | Native EventSource cannot set arbitrary headers | BFF cookie or streaming fetch/suitable client |
| Browser reports CORS though curl works | Origin/credentials/CORS policy mismatch | Check final CORS headers and SameSite |
| Stream lags behind LB but works locally | Proxy/CDN response buffering or caching | Test public route, inspect headers |
| Believing WebFlux guarantees infinite backpressure | Hot sources and queues are bounded | Bounded overflow policy, metrics, slow-client rules |
| SSE leaks another tenant's notifications | Broken subscription routing/authorization | Scope streams by principal, audit per event |
| SSE gets stored in shared CDN cache | Missing/wrong Cache-Control/rules | Bypass shared cache, `no-store` for PII |

**Practical investigation workflow:**

1. Use `curl -N -i` directly against Spring to inspect HTTP status, Content-Type, individual records, and arrival intervals.
2. Call **the same URL through the public proxy/CDN** and compare timestamps: if batching only happens on the public route, check buffering/timeouts.
3. In browser Network tab, inspect Request Headers, CORS, EventStream tab, named event listeners, and `EventSource.readyState`.
4. Measure active emitters/subscribers, task counts, thread pool usage, write latency, cancellations, and timeouts.
5. For missing/duplicate events, examine IDs, `Last-Event-ID`, retention, and replay logic rather than merely tweaking `retry` milliseconds.
6. For auth failures, inspect cookie/bearer mode, principal/tenant, and subscribe permissions without logging raw tokens.
7. Test killing connections, rolling deploys, flaky networks, and slow clients in staging—never against production streams carrying live user data.

## 18. SSE Observability and Operations

Design metrics with controlled cardinality:

- `sse.connections.active` by route/node (never use session ID or user ID as metric labels).
- `sse.connections.opened`, `completed`, `timed_out`, `errored`, `canceled`.
- `sse.events.sent` and `sse.bytes.sent` by event type/route group.
- `sse.send.latency` in MVC; elapsed time between publish and browser receipt if client telemetry exists.
- `sse.backlog.depth`, `dropped.events`, `replay.events` when using buffers/pubsub.
- `sse.reconnect.rate`, auth failure rate, quota exceeded count, node distribution.
- Per-route proxy read timeouts, 499/client disconnects or vendor-specific statuses, HTTP/2 streams, and container socket usage.

Long-lived streams increase open connections and file descriptors. Enforce: per-user quotas, request/auth rate limits, resource budgets, heartbeats, shutdown/draining, and global capacity. Do not log every heartbeat with PII at INFO level for thousands of subscribers, or logs will explode and expose sensitive data.

### Graceful Shutdown and Rolling Deployment

When a node is taken out of the load balancer, existing connections may continue until the grace period expires and then get closed. The browser reconnects to another node; **it needs resume/replay or REST resync** if events were missed. Sticky LBs do not preserve event stream sessions across node deaths.

If the app keeps an `SseEmitter` registry, clean it up and cancel tasks when the Spring context closes; if reactive subscriptions talk to a broker, dispose/cancel them. Align shutdown timeouts with load balancer draining and do not assume "node healthy" means streams will never be reset.

## 19. Payload Security and Cache Policies

A private stream may carry account balances, chat messages, order status, or user data. Key practices:

1. Authenticate and authorize **before allowing subscription**, and guard every topic/tenant as well as permission changes mid-stream.
2. Use **HTTPS**, Secure/HttpOnly/SameSite cookies or appropriate bearer transport; never use query strings with long-lived access tokens.
3. Allow CORS only for trusted origins; credentialed responses cannot use wildcard ACAO.
4. SSE GET must never perform business side effects; keep POST/PUT/DELETE APIs separate with CSRF protections matching the credential mode.
5. Set `Cache-Control: no-store, no-transform` or an equivalent private policy on private responses; **`no-cache` does not forbid storage**, and `no-transform` does not forbid caching.
6. Never allow a CDN to shared-cache personal SSE streams or serve user A's response to B.
7. Handle data serialization via the framework; if manually building SSE strings, guard against CR/LF injection from untrusted payloads.
8. Never place raw access tokens, Cookies, session IDs, or sensitive data into metrics, logs, or debug events.
9. When a client refreshes/reconnects, verify owner/tenant during replay queries; `Last-Event-ID` is not an authorization credential.
10. Enforce connection quotas so a single account cannot open thousands of streams to cause DoS.

**A stream opened before user logout** can continue receiving events unless the server implements revalidation or a revocation policy. Design connection lifetimes and cancel-on-revoke according to product requirements.

## 20. Evaluation: End-to-End Lab Practice

Build the two separate projects using the same logical contract:

- `tick` with incrementing `id` 1..5 and `data` as JSON containing `sequence` + `message`.
- `done` after the final tick, after which the frontend closes EventSource.
- MVC on port 8081; WebFlux on port 8082.
- Verify each path with cURL, browser, and automated tests.

**Check 1 — Format:** verify HTTP 200, `text/event-stream`, blank lines separating records, `event:tick` + `data:...`, and ordered IDs. The output must not be a JSON array.

**Check 2 — Timing:** record arrival times of each record via cURL/Browser. Do they arrive roughly every ~1 second or batched? If batching occurs only through NGINX, focus on proxy buffering.

**Check 3 — Disconnect:** open cURL and terminate with Ctrl+C after the second tick. In MVC, the task must cancel upon write error/callbacks; in WebFlux, the reactive source must receive cancellation. Do not expect upstream sources to stop instantaneously across all transports before the next write occurs.

**Check 4 — Client done:** keep the browser open after the fifth tick. With JS listening via `addEventListener("done")` and calling `close()`, the stream must not restart. Removing `close()` allows EventSource to reconnect.

**Check 5 — Auth:** test a stream requiring session cookie login over same-origin; unauthenticated users must be rejected. For cross-origin, verify CORS/credentials and SameSite.

**Check 6 — Reconnect:** force a disconnect and reconnect. The demo starts from the beginning; explain why `Last-Event-ID` alone does not replay, then design an event store if required.

**Check 7 — Slow client:** simulate a slow reader in staging and monitor memory, task/thread pools, and event backlogs. Do not rely on HTTP status alone to conclude the system handles load.

**Check 8 — Deploy:** connect behind two Spring instances, restart the node handling the request, and verify reconnect, authorization, and replay semantics.

## 21. Checklist for Choosing MVC vs. WebFlux in Real Projects

1. Is the app currently using blocking Spring MVC/JPA or reactive WebFlux/R2DBC/WebClient?
2. How many concurrent SSE connections and what event rates are expected?
3. Are there periodic small JSON payloads, or high-frequency event streams needing buffering/replay?
4. Do you need a multi-node broker, durable cursors, and exactly-once business effects?
5. Is there a risk of slow clients exhausting threads or growing memory queues?
6. Have app, proxy, LB, and browser timeouts been measured and matched with heartbeats?
7. Is authentication required with cross-origin browser cookies or bearer tokens?
8. How are user role/tenant changes or logouts handled while a stream is alive?
9. For MVC, are cleanup callbacks wired and schedulers/executors bounded?
10. For WebFlux, is the entire pipeline non-blocking, and have cancellation/backpressure been tested?
11. Have you tested browser EventSource, `curl -N`, origin vs. CDN, and shutdown/reconnect?
12. Are active streams, latency, reconnects, dropped/replayed events, and quotas monitored?

**Practical rule:** do not rewrite your entire stack just to emit a few SSE notifications. `SseEmitter` works well for many medium-scale MVC apps when the async lifecycle is managed properly. If you already run a reactive web stack with high stream counts, `Flux`/`ServerSentEvent` is a natural fit—though you still need proxy configuration, durable events, and resource policies.

## 22. Self-Check Questions

**1.** Is SSE bidirectional push like WebSocket?

**Answer:** No. SSE is a one-way server → client HTTP stream. The browser sends commands via separate HTTP requests or uses WebSocket when continuous two-way traffic is needed.

**2.** Does `SseEmitter.send(...)` terminate the response after one event?

**Answer:** No. It writes another SSE record. The request remains open until `complete()`, timeout, error, or disconnect, depending on the lifecycle.

**3.** Is `Flux.just("a","b")` automatically SSE?

**Answer:** Only when mapping/content negotiation selects `text/event-stream` and a compatible encoder. When named events, IDs, or retry delays are needed, use `Flux<ServerSentEvent<T>>`.

**4.** Why can MVC with `SseEmitter` still exhaust threads?

**Answer:** Servlet async frees the initial request thread, but `send` writes can still block worker threads; per-client threads, unbounded queues, and slow clients can still exhaust resources.

**5.** When `send` throws IOException due to client disconnect, should you immediately call `completeWithError`?

**Answer:** Per Spring MVC guidance, no; the container/Spring handles the async error notification. The app stops the producer and cleans up resources, avoiding double-completion.

**6.** The browser only uses `source.onmessage`, while the server sends `event: tick`—why is nothing received?

**Answer:** It is a named event. Use `source.addEventListener("tick", ...)`; `onmessage` only fires for unnamed default events.

**7.** Does EventSource automatically replay missed events on reconnect if the server sets `id`?

**Answer:** No. The browser may send `Last-Event-ID`, but the server must implement a durable store/cursor logic to replay. The client still needs deduplication/idempotency.

**8.** Is `retry: 3000` a server timeout or a cache TTL?

**Answer:** No. It is a client reconnect delay hint in milliseconds; it is neither a request timeout, `Access-Control-Max-Age`, nor `Cache-Control`.

**9.** Does WebFlux automatically make every JDBC query inside a stream non-blocking?

**Answer:** No. Blocking JDBC must be offloaded or replaced with a non-blocking solution; calling `block()` on the event loop breaks scalability.

**10.** Can an API requiring a bearer token in headers use native EventSource to attach `Authorization`?

**Answer:** Native EventSource does not support arbitrary request headers. Use streaming `fetch`/a parser, a BFF-cookie setup, or another auth mechanism with a clear threat model.

**11.** Why does local cURL see one event per second while the public CDN URL receives all 5 in one burst?

**Answer:** Check proxy buffering, compression, CDN streaming behavior, and cache policies—not just `SseEmitter`/`Flux` code.

**12.** Can any authenticated user subscribe to any `/events/orders/{id}`?

**Answer:** No. You must enforce owner/tenant/resource authorization and check permissions over long-lived streams, not just `authenticated()`.

## 23. Official References

- [Spring Framework — MVC Asynchronous Requests and SSE](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-async.html): `ResponseBodyEmitter`, `SseEmitter`, disconnects, Servlet async executor/timeout.
- [Spring Framework — SseEmitter Javadoc (6.2)](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/web/servlet/mvc/method/annotation/SseEmitter.html): `send`, `event`, timeouts, and lifecycle.
- [Spring Framework — WebFlux Controller Return Types](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/return-types.html): `Flux<ServerSentEvent>` and `text/event-stream`.
- [Spring Framework — WebFlux @ResponseBody](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/responsebody.html): encoding reactive Publishers into response streams.
- [Spring Framework — ServerSentEvent Javadoc](https://docs.spring.io/spring-framework/docs/6.2.5/javadoc-api/org/springframework/http/codec/ServerSentEvent.html): builder with `id`, `event`, `retry`, `comment`, and `data`.
- [MDN — Using Server-Sent Events](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events/Using_server-sent_events): EventSource, framing, event fields, reconnect, comments, and browser behavior.
- [MDN — EventSource](https://developer.mozilla.org/en-US/docs/Web/API/EventSource): `close`, `withCredentials`, and event listeners.
- [HTML Standard — Server-sent events](https://html.spec.whatwg.org/multipage/server-sent-events.html): event stream specification, reconnection, and `Last-Event-ID`.
- [Reactor Core — Flux API](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html): `interval`/`take`/`concatWith`/`doFinally`, backpressure/cancellation.
- [Spring Boot — Web applications](https://docs.spring.io/spring-boot/reference/web/index.html): choosing Servlet vs. Reactive stack, runtime configuration.

**Conclusion:** `SseEmitter` lets **MVC/Servlet** actively `send` individual SSE records from workers while cleaning up async tasks/emitters; `Flux<ServerSentEvent<T>>` lets **WebFlux** emit SSE from a Publisher with cancellation/backpressure semantics. Both must obey `text/event-stream`, handle proxy buffering/timeouts, secure streams per user/tenant, bound resources, and implement `Last-Event-ID` + replay if data continuity across reconnects is required.
