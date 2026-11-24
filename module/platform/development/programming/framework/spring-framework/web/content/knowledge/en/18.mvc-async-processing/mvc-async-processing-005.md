# ResponseBodyEmitter, SseEmitter, and StreamingResponseBody in Spring MVC

## 1. When should an HTTP response be sent over a timeline?

A typical Spring MVC response is usually completed in one shot:

```text
Client                Spring MVC
  | GET /api/report        |
  |----------------------->|
  |                        | Compute the entire result
  |<-----------------------| HTTP 200 + complete JSON
  |        finish          |
```

However, some requirements need to **stream the result in multiple parts** as data becomes ready:

- A long-running job emitting progress steps (queued, running, completed).
- A browser receiving one-way notifications from the server via **Server-Sent Events (SSE)**.
- An API generating a large CSV report or large binary content without holding the entire output in RAM.
- A query returning many records sequentially as **NDJSON** (each line is a JSON value).
- A system needing lower **time to first byte** and avoiding building a huge array/list before returning a response.

Spring MVC Servlet provides three representative return types:

| API | Unit written | Format | Suitable scenario |
| --- | --- | --- | --- |
| **`ResponseBodyEmitter`** | Multiple objects; each passes through `HttpMessageConverter` | Decided by application, e.g. text/NDJSON | Multi-fragment progress, object streaming |
| **`SseEmitter`** | Multiple SSE events, a subclass of `ResponseBodyEmitter` | `text/event-stream`, with `event/id/data/retry` | Browser EventSource, one-way notifications |
| **`StreamingResponseBody`** | Raw bytes directly to `OutputStream` | CSV, binary, or text per your code | Downloads/stream writing without per-object message conversion |

All three belong to **asynchronous** Spring MVC, yet **they do not turn Servlet output I/O into non-blocking I/O**. When writing the response, a thread can still be blocked by the network or a slow downstream client. This is an important difference compared to Spring WebFlux.

**Scope:** Spring Framework 6.2.x / Spring Boot 3.5.x, Java 17+, **Servlet MVC** (e.g., embedded Tomcat). Do not mistakenly import WebFlux reactive APIs when using these three types.

## 2. Servlet async foundation: request thread exits while response remains open

In synchronous processing, a container thread runs through filters, `DispatcherServlet`, and the controller, writes the response, and exits. With MVC async, Spring invokes the Servlet API's `request.startAsync()` mechanism (through the framework), allowing the **request thread to return to the container** while the HTTP response is not yet complete.

```text
HTTP GET /demo/events
       |
       v
Servlet container REQUEST dispatch (Thread A)
       |
Filters -> DispatcherServlet -> Controller
       |
Controller returns SseEmitter/ResponseBodyEmitter
       |
Spring MVC activates Servlet async
       |
Thread A returns to pool (response stays open)
       |
Producer thread / message source (Thread B)
       |
  emitter.send(...) multiple times
       |
  emitter.complete() or timeout/error/disconnect
       |
Servlet ASYNC dispatch to finish lifecycle
       |
Response ends, cleanup callbacks
```

For `StreamingResponseBody`, the `writeTo(OutputStream)` callback is executed asynchronously by the MVC task executor instead of forcing the container request thread to wait for the entire download. Therefore, you need to configure a **bounded `AsyncTaskExecutor` sized for real load**.

### "Async" does not mean "uses no threads"

- The Servlet request thread can be released when the controller returns an emitter or streaming callback.
- The producer still needs a thread/worker or an event source with a suitable mechanism.
- Writing to `OutputStream` in Spring MVC remains a **blocking** operation under the traditional Servlet output model.
- If a client downloads extremely slowly, the thread calling `send` or `writeTo` can be blocked.
- Returning `Flux` in Spring MVC can support reactive backpressure at the publisher interface, but the final HTTP writes can still happen on a thread and block.
- For systems with huge numbers of long-lived connections and end-to-end non-blocking I/O goals, consider **Spring WebFlux, WebSocket, or other event-streaming infrastructure** depending on application characteristics.

## 3. Direct comparison of the three APIs and other async types

| Characteristic | `ResponseBodyEmitter` | `SseEmitter` | `StreamingResponseBody` |
| --- | --- | --- | --- |
| Returns multiple values | Yes | Yes | Yes, as multiple byte writes |
| Object conversion | Via `HttpMessageConverter` | Via converter for the data portion | **No** for directly written bytes |
| Built-in SSE event formatting | No | **Yes** | No |
| Read from JavaScript `EventSource` | Only if you build the exact wire format yourself | **Best fit** | Can manually write SSE bytes, though less convenient |
| Intended for large files/CSV | Possible, though less direct | Not the primary goal | **Best fit** |
| Controlling response status/headers | Return inside `ResponseEntity<ResponseBodyEmitter>` | `ResponseEntity<SseEmitter>` | `ResponseEntity<StreamingResponseBody>` |
| Built-in emitter timeout callback | `onTimeout` | Inherits `onTimeout` | No emitter callback; handled via MVC/Servlet async infrastructure |
| Normal completion | `complete()` | `complete()` | `writeTo` callback returns |
| Application-level error | `completeWithError(ex)` when appropriate | Inherits `completeWithError` | `writeTo` throws IOException/exception |
| On client disconnect | Subsequent writes can throw IOException | Heartbeat/event writes can detect disconnect | `writeTo` can throw IOException |
| Client-side display unit | Depends on content framing you choose | Standard SSE event | Bytes defined by your code |

`DeferredResult<T>` and `Callable<T>` solve **a single asynchronous result**; they do not emit multiple messages in one HTTP response. `WebAsyncTask` is a configuration wrapper for `Callable`. If a job returns one JSON object after completion, `DeferredResult` may be more appropriate. If multiple messages on one response are required, pick from the three APIs above.

### HTTP chunked transfer is not the API's own wire protocol

When Content-Length is unknown, an HTTP/1.1 server may use `Transfer-Encoding: chunked`; HTTP/2 has its own frames. **Never write or parse chunk markers** in application code. You write logical data/fragments; the container and HTTP stack decide the transport representation.

Even when calling `flush()`, proxies, CDNs, compression, browser buffering, or TCP can still deliver data in different groupings. Do not rely on "each `send` creates exactly one network chunk".

## 4. `ResponseBodyEmitter`: sending multiple objects sequentially

Class:

```java
import org.springframework.web.servlet.mvc.method.annotation.ResponseBodyEmitter;
```

A controller can return an emitter immediately:

```java
@GetMapping("/progress")
ResponseBodyEmitter progress() {
    ResponseBodyEmitter emitter = new ResponseBodyEmitter(30_000L);
    // Producer in another component/thread will call send and complete.
    return emitter;
}
```

**This is a method fragment**, not a complete flow; without a producer or a call to complete, the connection can hang until timeout.

### 4.1. Essential API

- `new ResponseBodyEmitter()`: timeout comes from MVC/server configuration if not specified separately.
- `new ResponseBodyEmitter(Long timeout)`: timeout for the emitter; unit is **milliseconds**.
- `send(Object object)`: passes the object through a compatible `HttpMessageConverter`.
- `send(Object object, MediaType hint)`: provides a media type hint for converter selection.
- `complete()`: signals that the producer finished normally.
- `completeWithError(Throwable)`: completes with an appropriate application-level error, triggering an async dispatch.
- `onTimeout(Runnable)`: callback when the async request times out.
- `onError(Consumer<Throwable>)`: callback when async processing encounters an error.
- `onCompletion(Runnable)`: callback when the async request finishes, including success, timeout, and network error.

Spring 6.2 allows registering multiple callbacks for the lifecycle events above. Callbacks can run on **container threads**, not necessarily the producer thread. Therefore, all shared state must be thread-safe.

### 4.2. An emitter does not produce valid NDJSON automatically

If you want multiple records as NDJSON:

```text
{"seq":1,"state":"queued"}
{"seq":2,"state":"running"}
{"seq":3,"state":"done"}
```

Each line must be a valid JSON value with a **newline** delimiter. Calling `emitter.send(object, MediaType.APPLICATION_JSON)` consecutively does not automatically separate objects onto individual lines: concatenating JSON objects directly produces `{}{}`, which is neither a valid JSON document nor valid NDJSON.

A producer can send **a JSON object followed by a newline character** to match the contract:

```java
emitter.send(new Progress(1, "queued"), MediaType.APPLICATION_JSON);
emitter.send("\n", MediaType.TEXT_PLAIN);

emitter.send(new Progress(2, "done"), MediaType.APPLICATION_JSON);
emitter.send("\n", MediaType.TEXT_PLAIN);

emitter.complete();
```

This is a **fragment**, assuming the `Progress` record and emitter are declared. In the runnable example in section 9, the server uses `application/x-ndjson` on the response, the JSON converter for each record, and text/plain for the delimiter.

If you need specific framing/flushing guarantees at very high throughput, `StreamingResponseBody` may fit better, or a specialized publisher/batching framework.

### 4.3. Error lifecycle: special rules for IOException

Per Spring MVC guidance:

- If `emitter.send(...)` throws **`IOException`** because the client disconnected or a network write failed, **do not call `complete()` or `completeWithError()`** from that branch. The Servlet container notifies of the async error; Spring completes the request via corresponding handling.
- For **application-originated errors** in the producer (business failures, serialization bugs before response commit), `completeWithError(ex)` may be used if the emitter has not already finished.
- Once the response has committed (bytes/headers written), error handlers **cannot reliably change the HTTP status to 500 or replace the body with JSON error details**. The client may receive partial initial data and then see the stream terminate abruptly.
- `onCompletion` is the right place to remove the emitter reference from registries and release resources; do not assume it only runs on the happy path.

## 5. `SseEmitter`: standard Server-Sent Events for browsers

Class:

```java
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;
```

`SseEmitter` extends `ResponseBodyEmitter` and adds builders for **SSE events**:

```java
SseEmitter emitter = new SseEmitter(30_000L);

emitter.send(SseEmitter.event()
        .id("event-42")
        .name("progress")
        .reconnectTime(2_000L)
        .data("Completed 42%"));
```

This is a **fragment**, without a controller/executor or exception handling. `SseEmitter.event()` returns an `SseEventBuilder` to set fields; `send(builder)` writes the event in `text/event-stream` format.

### 5.1. SSE wire format

An SSE stream is **UTF-8 text** with events separated by **blank lines**:

```text
id: 42
event: progress
retry: 2000
data: {"percent":42}

id: 43
event: finished
data: {"percent":100}

```

Important fields:

| Field | Meaning |
| --- | --- |
| `data:` | Payload. Multiple consecutive `data:` lines are joined by newlines on the client |
| `event:` | Event type for JavaScript `addEventListener("progress",...)` |
| `id:` | Event ID, used for `lastEventId` and reconnection |
| `retry:` | Reconnection hint in milliseconds for the client; must be an integer |
| Line starting with `:` | Comment/heartbeat, ignored as an application event by the client |
| Blank line | Ends one event frame |

**Field names are not HTTP headers.** `id:` here is inside the `text/event-stream` response body, not `ETag` or HTTP `Last-Modified`. Each event needs proper frame delimiters; `SseEmitter` reduces mistakes from manual string concatenation.

### 5.2. JavaScript `EventSource`

Browsers provide the EventSource API:

```javascript
const source = new EventSource("/demo/sse");

source.addEventListener("progress", event => {
  console.log("Progress:", event.lastEventId, event.data);
});

source.addEventListener("finished", event => {
  console.log("Finished:", event.data);
  source.close(); // Finite demo stream, avoid auto-reconnect.
});

source.onerror = event => {
  console.warn("SSE interrupted", event);
};
```

Notes:

- `EventSource` uses **HTTP GET** to subscribe to the stream.
- A closed connection can **auto-reconnect** per browser policy; for streams intentionally ending after a few events, the client should call `source.close()` or follow a stop protocol.
- `EventSource` supports **server → client** messages; when the client needs to send commands, normally use POST/PUT via `fetch`, or WebSocket if bidirectional is needed.
- Browser EventSource has no standard API for attaching arbitrary custom request headers; for auth, use appropriate cookies or a dedicated gateway/token design. Never put raw access tokens in URL query parameters.
- Cross-origin EventSource requires accurate CORS configuration. If using credentials/cookies, use `withCredentials: true` and a CORS policy allowing specific origins; never use a wildcard origin when credentials are enabled.
- SSE is supported across modern browsers; proxy/CDN buffering and HTTP/1.1 connection limits can cause issues when opening many tabs.

### 5.3. `Last-Event-ID` and reconnect

If the server sends `id: 42`, the browser can send **`Last-Event-ID: 42`** upon reconnecting. This **does not automatically create a replay log in Spring**. If an app only keeps emitters in RAM, reconnecting to another node or after a restart leaves it with no idea which event to resume from.

A production SSE system needing delivery continuity must:

1. Assign stable, ordered IDs per stream/resource.
2. Persist events in a broker/database/log according to a retention policy.
3. When a client sends Last-Event-ID, authorize that ID against the user/tenant/stream, then replay appropriate events.
4. Handle duplicate events with **at-least-once** semantics if needed; clients need idempotency.
5. Handle gaps if old events have aged past retention.
6. When scaling across multiple nodes, use a shared event source or pub/sub, not just a local map of emitters.

**Do not promise exactly-once** merely because SSE has `id`.

### 5.4. Heartbeats and disconnect detection

The Servlet API does not notify of client disconnects immediately in every scenario. For long-lived streams, **send data periodically** to keep the connection alive and detect write failures. SSE can use a comment event:

```java
emitter.send(SseEmitter.event().comment("heartbeat"));
```

This is a fragment. The `:heartbeat` comment does not fire an application event in the browser. The interval should be smaller than the proxy/container idle timeout per your architecture, with jitter/backoff if appropriate. Heartbeats do not replace authorization, connection limits, or subscriber cleanup.

Do not design **an infinite `Thread.sleep` per client**; use a bounded scheduler/producer event loop, measure subscriber counts, optimize broadcasters, and handle slow clients.

## 6. `StreamingResponseBody`: writing directly to OutputStream

The class is a functional interface:

```java
import org.springframework.web.servlet.mvc.method.annotation.StreamingResponseBody;
```

Core method:

```java
void writeTo(OutputStream outputStream) throws IOException;
```

Spring MVC executes the `writeTo` callback asynchronously, letting the application **write bytes directly**. There is no per-object message conversion like `ResponseBodyEmitter`.

Example CSV response:

```java
@GetMapping(path = "/export.csv", produces = "text/csv")
ResponseEntity<StreamingResponseBody> export() {
    StreamingResponseBody body = output -> {
        output.write("id,name\n".getBytes(StandardCharsets.UTF_8));
        output.write("1,Ada\n".getBytes(StandardCharsets.UTF_8));
        output.flush();
    };

    return ResponseEntity.ok()
            .contentType(MediaType.parseMediaType(
                    "text/csv;charset=UTF-8"))
            .header(HttpHeaders.CONTENT_DISPOSITION,
                    "attachment; filename=\"export.csv\"")
            .body(body);
}
```

This is a **controller method fragment**; imports `StandardCharsets`, `ResponseEntity`, `HttpHeaders`, `MediaType` are needed. Production needs proper CSV escaping and output bounds.

### 6.1. Avoid holding the entire file in RAM

Anti-pattern for large files:

```java
byte[] all = Files.readAllBytes(path);
return ResponseEntity.ok(all);
```

When many clients download large files, memory can grow with the sum of file sizes. Use `StreamingResponseBody` with buffered streaming:

```java
StreamingResponseBody body = output -> {
    try (InputStream source = Files.newInputStream(path)) {
        source.transferTo(output);
        output.flush();
    }
};
```

This is a **fragment**; verify server-owned `path` and access permissions beforehand. `InputStream#transferTo` streams via an internal buffer instead of materializing the whole file, though network writes are still blocking and download speed depends on downstream.

For very large static files already on disk, Spring MVC `Resource` / `ResourceRegion` may be better suited when needing HTTP Range, conditional GET, Content-Length, or sendfile. `StreamingResponseBody` **does not automatically provide** resumable downloads/`206 Partial Content`.

### 6.2. CSV/NDJSON require manual framing control

- For CSV, escape commas, quotes, and newlines properly. When exporting user input for spreadsheets, consider **CSV formula injection** (values starting with `=`, `+`, `-`, `@` can be interpreted as formulas by spreadsheet software).
- For NDJSON, each line is **one complete JSON value** with a newline delimiter; manually concatenating field strings can produce invalid JSON.
- For binary, never use a `Writer` mixing uncontrolled charsets into `OutputStream`.
- Write in reasonable batches; do not flush byte-by-byte with high overhead.
- Do not set Content-Length unless you know the exact bytes sent and can guarantee that length.
- Do not access request-scoped beans or `HttpServletRequest` from an async callback without explicit context propagation; pass immutable metadata, paths/IDs after validation.

## 7. Lifecycle, timeouts, errors, and connection cleanup

### 7.1. Useful states for an emitter

```text
CREATED
   |
   v
ACTIVE --send()--> ACTIVE --send()--> ACTIVE
   |                  |                 |
   | complete()       | timeout         | IOException/disconnect
   v                  v                 v
COMPLETED           TIMED_OUT          ERROR
   \                  |                 /
    \_________________|________________/
                       |
                onCompletion()
                release registry
```

This is a **conceptual diagram**, not a public state enum on `ResponseBodyEmitter`. Lifecycle events can occur close together on different threads; use `AtomicBoolean` or proper synchronization to protect cleanup operations from races.

### 7.2. onTimeout differs from completeWithError

`emitter.onTimeout(...)` only registers a callback; it does not automatically cancel producers in an external message broker. The application must cancel tasks/unsubscribe and release resources per policy.

`onCompletion` runs when the async request finishes due to success/error/timeout; it is usually the best place to remove the emitter from registries. For disconnects, do not expect a callback at an exact instant unless a write/heartbeat detects the failure.

### 7.3. Pitfall with IOException

If `send` throws `IOException` due to a container write failure, the application **must not call `completeWithError` or `complete` for that container event**. The container delivers the error notification and Spring handles async completion. This advice comes from the Spring MVC async streaming reference.

If a business error occurs before/after sending some events, `completeWithError(ex)` can let Spring run exception resolvers on async dispatch. However, if **headers/response have already committed**, status/body can no longer be safely replaced; the server should emit a protocol-level error event before completing (if the connection is still usable), or let the client handle disconnect/retry.

### 7.4. Three-tier timeouts

1. **Emitter timeout**: `new SseEmitter(30_000L)` or `new ResponseBodyEmitter(30_000L)`.
2. **MVC default async timeout**: `AsyncSupportConfigurer#setDefaultTimeout`; applies when no override is set.
3. **Servlet container/proxy/load balancer timeout**: connections can be closed independently of the two values above.

Do not equate "30 s emitter timeout" with "every proxy is guaranteed to keep the connection open at least 30 s". Reverse proxies have their own idle/read timeouts, and browsers have their own reconnect policies.

## 8. Configuring TaskExecutor and Servlet async

### 8.1. Spring Boot 3.5 auto-configures an executor — but sizing still matters

Spring Boot 3.5 auto-configures an `AsyncTaskExecutor` when conditions match. In this version, the auto-configured bean is named **`applicationTaskExecutor`**; Spring MVC looks for a bean with that name and type `AsyncTaskExecutor` when using Boot auto-configuration.

Spring Framework documentation recommends configuring an executor sized for your load rather than relying on the default fallback when streaming needs blocking writes. Boot normally creates a `ThreadPoolTaskExecutor` unless Java 21+ virtual threads are enabled. Defining a custom `Executor` bean can cause Boot auto-configuration to back off, so verify the active executor.

An explicit manual configuration in the section 9 demo:

```java
@Configuration
class StreamingAsyncConfig implements WebMvcConfigurer {

    @Bean(name = "applicationTaskExecutor")
    ThreadPoolTaskExecutor applicationTaskExecutor() {
        ThreadPoolTaskExecutor pool = new ThreadPoolTaskExecutor();
        pool.setCorePoolSize(4);
        pool.setMaxPoolSize(8);
        pool.setQueueCapacity(100);
        pool.setThreadNamePrefix("mvc-stream-");
        pool.initialize();
        return pool;
    }

    @Override
    public void configureAsyncSupport(AsyncSupportConfigurer configurer) {
        configurer.setTaskExecutor(applicationTaskExecutor());
        configurer.setDefaultTimeout(30_000L);
    }
}
```

This is a **class fragment** requiring Spring Config/AsyncTaskExecutor imports; see the full runnable file in section 9.

- The pool has at most 8 workers and a queue of 100 requests/tasks in the example. These are **learning numbers**, not production sizing for every system.
- If tasks block due to slow clients, the pool can exhaust workers; when the queue is full, you need fail-fast/rejection/backpressure policies.
- `StreamingResponseBody` and producer tasks in the demo share one pool for simplicity; in production, **separate executors** if load profiles differ so streaming writes do not starve producers.
- You can use Boot properties `spring.task.execution.pool.*` if letting Boot auto-configure the executor; avoid creating a custom executor while expecting all Boot properties to modify it automatically.
- With Java 21+ virtual threads, lighter-weight threads do not turn network I/O into automatic backpressure. You still need client limits and bounds on in-flight data.

### 8.2. Servlet/Filter registrations must support async

With Servlet 3+ and standard Spring Boot Java configuration, `DispatcherServlet` is normally registered with async support. However, a custom filter lacking `asyncSupported=true` can prevent requests from entering async mode.

With a custom `FilterRegistrationBean`:

```java
registration.setAsyncSupported(true);
registration.setDispatcherTypes(
        DispatcherType.REQUEST, DispatcherType.ASYNC);
```

This is a **fragment**, requiring a valid filter registration and `jakarta.servlet.DispatcherType` imports. `ASYNC` dispatcher mapping is used when the filter must participate on redispatch; it does not by itself force logic to re-run if the `OncePerRequestFilter` base class skips async/error by default.

If declaring `web.xml`/external WAR, configure `<async-supported>true</async-supported>` on the servlet and relevant filters. Test in the embedded container or target deployment rather than only controller unit tests.

## 9. Runnable Spring Boot 3.5 + Java 17 application

Three endpoints:

1. `GET /demo/objects` — `ResponseBodyEmitter` emits **two NDJSON records** using Jackson converter and newlines.
2. `GET /demo/sse` — `SseEmitter` emits one `progress` event and one `finished` event, each with an ID.
3. `GET /demo/report.csv` — `StreamingResponseBody` emits a CSV file without materializing the entire response upfront.

To keep tests finite and avoid hanging clients, each stream intentionally **completes normally**. They do not simulate endless live feeds, shared pub/sub, or cross-node state storage. Full source is in a single Java file.

### 9.1. Gradle dependencies

In a Spring Boot 3.5 project with the Boot plugin, repositories, dependency management, and Java 17 toolchain:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

This is a **`build.gradle` configuration snippet**, not a standalone Gradle file. Starter web provides Servlet MVC/Jackson for JSON object conversions. No WebFlux dependency is needed to run these three streaming types.

### 9.2. Complete Java source

Create **`src/main/java/demo/streaming/StreamingDemoApplication.java`**:

```java
package demo.streaming;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.atomic.AtomicBoolean;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.AsyncTaskExecutor;
import org.springframework.http.CacheControl;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.config.annotation.AsyncSupportConfigurer;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;
import org.springframework.web.servlet.mvc.method.annotation.ResponseBodyEmitter;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;
import org.springframework.web.servlet.mvc.method.annotation.StreamingResponseBody;

@SpringBootApplication
public class StreamingDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(StreamingDemoApplication.class, args);
    }
}

@Configuration
class StreamingAsyncConfig implements WebMvcConfigurer {

    @Bean(name = "applicationTaskExecutor")
    ThreadPoolTaskExecutor applicationTaskExecutor() {
        ThreadPoolTaskExecutor pool = new ThreadPoolTaskExecutor();
        pool.setCorePoolSize(4);
        pool.setMaxPoolSize(8);
        pool.setQueueCapacity(100);
        pool.setThreadNamePrefix("mvc-stream-");
        pool.initialize();
        return pool;
    }

    @Override
    public void configureAsyncSupport(AsyncSupportConfigurer configurer) {
        configurer.setTaskExecutor(applicationTaskExecutor());
        configurer.setDefaultTimeout(30_000L);
    }
}

record Progress(int seq, String state) {}

@RestController
class StreamingController {

    private static final MediaType NDJSON =
            MediaType.parseMediaType("application/x-ndjson");

    private final AsyncTaskExecutor executor;

    StreamingController(
            @Qualifier("applicationTaskExecutor")
            AsyncTaskExecutor executor) {
        this.executor = executor;
    }

    @GetMapping(path = "/demo/objects",
            produces = "application/x-ndjson")
    ResponseEntity<ResponseBodyEmitter> objects() {
        ResponseBodyEmitter emitter = new ResponseBodyEmitter(15_000L);
        AtomicBoolean stopped = registerLifecycle(emitter);

        executor.execute(() -> {
            try {
                if (stopped.get()) {
                    return;
                }

                emitter.send(new Progress(1, "queued"),
                        MediaType.APPLICATION_JSON);
                emitter.send("\n", MediaType.TEXT_PLAIN);

                emitter.send(new Progress(2, "done"),
                        MediaType.APPLICATION_JSON);
                emitter.send("\n", MediaType.TEXT_PLAIN);

                if (!stopped.get()) {
                    emitter.complete();
                }
            } catch (IOException disconnected) {
                // Servlet container handles IOException/async error.
                stopped.set(true);
            } catch (RuntimeException failure) {
                if (!stopped.get()) {
                    emitter.completeWithError(failure);
                }
            }
        });

        return ResponseEntity.ok()
                .contentType(NDJSON)
                .cacheControl(CacheControl.noStore())
                .body(emitter);
    }

    @GetMapping(path = "/demo/sse",
            produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    ResponseEntity<SseEmitter> sse() {
        SseEmitter emitter = new SseEmitter(15_000L);
        AtomicBoolean stopped = registerLifecycle(emitter);

        executor.execute(() -> {
            try {
                if (stopped.get()) {
                    return;
                }

                emitter.send(SseEmitter.event()
                        .id("1")
                        .name("progress")
                        .reconnectTime(2_000L)
                        .data("queued"));

                emitter.send(SseEmitter.event()
                        .id("2")
                        .name("finished")
                        .data("done"));

                if (!stopped.get()) {
                    emitter.complete();
                }
            } catch (IOException disconnected) {
                // Do NOT call completeWithError after an I/O failure.
                stopped.set(true);
            } catch (RuntimeException failure) {
                if (!stopped.get()) {
                    emitter.completeWithError(failure);
                }
            }
        });

        return ResponseEntity.ok()
                .contentType(MediaType.TEXT_EVENT_STREAM)
                .cacheControl(CacheControl.noCache())
                .header("X-Accel-Buffering", "no")
                .body(emitter);
    }

    @GetMapping(path = "/demo/report.csv",
            produces = "text/csv")
    ResponseEntity<StreamingResponseBody> csv() {

        StreamingResponseBody body = output -> {
            // Deterministic demo, no user-provided spreadsheet cells.
            output.write("id,name\n".getBytes(StandardCharsets.UTF_8));
            output.write("1,Ada\n".getBytes(StandardCharsets.UTF_8));
            output.write("2,Lin\n".getBytes(StandardCharsets.UTF_8));
            output.flush();
        };

        return ResponseEntity.ok()
                .contentType(MediaType.parseMediaType(
                        "text/csv;charset=UTF-8"))
                .header(HttpHeaders.CONTENT_DISPOSITION,
                        "attachment; filename=\"report.csv\"")
                .cacheControl(CacheControl.noStore())
                .body(body);
    }

    private static AtomicBoolean registerLifecycle(
            ResponseBodyEmitter emitter) {
        AtomicBoolean stopped = new AtomicBoolean(false);
        emitter.onTimeout(() -> stopped.set(true));
        emitter.onError(error -> stopped.set(true));
        emitter.onCompletion(() -> stopped.set(true));
        return stopped;
    }
}
```

**This is a valid Java 17 file in Spring Boot 3.5:** only `StreamingDemoApplication` is public; `StreamingAsyncConfig`, `StreamingController`, and record `Progress` are in the same package so Spring component scanning picks them up. `ThreadPoolTaskExecutor` is a Spring `AsyncTaskExecutor`, used for both producers and MVC async in the demo.

Notes:

- `objects()` sends JSON objects and `"\n"` separately to form **NDJSON**. Requires message converters from `spring-boot-starter-web`. A single producer guarantees message ordering by `seq`.
- `sse()` formats proper SSE frames with `id` and `event`; it is not JSON. The `X-Accel-Buffering: no` header is **NGINX-specific configuration** honored by reverse proxies that support it, not a mandatory standard HTTP header.
- `csv()` lets Spring MVC schedule the callback on the async executor without manually creating threads. Static CSV text example with no user-input escaping needed.
- The 15-second timeout is set **per emitter**, while the 30-second MVC default timeout acts as fallback for async requests without overrides.
- `onTimeout`, `onError`, and `onCompletion` only set a flag here; in real systems, stop producers/subscriptions, cancel scheduled tasks, and remove emitters from registries.
- If the executor is overloaded, `execute` can throw a rejection exception right inside the handler; production needs admission control and fallback status/metrics, not infinite retries.
- Sending before Spring finishes initializing the emitter can be queued by the framework to flush once the handler attaches; do not rely on thread ordering to assume bytes are definitely sent before the controller returns.
- Never design an endless `while(true)` per HTTP request, especially with a fixed thread pool.
- Response media types matter: clients need `application/x-ndjson`, `text/event-stream`, or `text/csv` to match functionality.

## 10. Calling with curl and reading expected output

Run the application:

```bash
./gradlew bootRun
```

### 10.1. Object streaming/NDJSON

```bash
curl -N -i 'http://localhost:8080/demo/objects'
```

`-N` (no-buffer) prevents curl from buffering output locally; it does not force every proxy to flush immediately.

Expected body (two lines, each a JSON object):

```json
{"seq":1,"state":"queued"}
{"seq":2,"state":"done"}
```

Key order inside a JSON object depends on Jackson; this example uses a record with two fields in declaration order. NDJSON clients should parse **line by line** instead of parsing the whole body as one JSON array.

### 10.2. SSE

```bash
curl -N -i \
  -H 'Accept: text/event-stream' \
  'http://localhost:8080/demo/sse'
```

Body format:

```text
id:1
event:progress
retry:2000
data:queued

id:2
event:finished
data:done

```

Formatting may include a space after colons or slightly different field order depending on the serializer; the **important contract** is the fields and event delimiters. `curl` only displays raw bytes and does not parse SSE like browser `EventSource`.

### 10.3. Downloading CSV

```bash
curl -i 'http://localhost:8080/demo/report.csv'
```

Expected status `200 OK`; headers include `Content-Type: text/csv;charset=UTF-8` and `Content-Disposition: attachment; filename="report.csv"`. Body:

```csv
id,name
1,Ada
2,Lin
```

Download the file to disk with `curl -o report.csv 'http://localhost:8080/demo/report.csv'`; omit `-i` when saving a real CSV so HTTP headers are not written into the file.

## 11. MockMvc testing for async and finite streaming

`MockMvc` does not run a real HTTP socket like Tomcat, so it is suited for verifying **MVC contracts, media types, and the body after the producer completes**. It cannot measure wire flush latency, proxy buffering, TCP disconnects, or real browser EventSource behavior.

Create **`src/test/java/demo/streaming/StreamingDemoApplicationTests.java`**:

```java
package demo.streaming;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.asyncDispatch;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.request;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class StreamingDemoApplicationTests {

    @Autowired
    MockMvc mvc;

    @Test
    void emitsTwoNdjsonRecordsAndCompletes() throws Exception {
        MvcResult result = mvc.perform(get("/demo/objects"))
                .andExpect(request().asyncStarted())
                .andReturn();

        result.getAsyncResult(5_000L); // Wait for completion signal, do not sleep.

        mvc.perform(asyncDispatch(result))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(
                        "application/x-ndjson"))
                .andExpect(content().string(
                        containsString("\"state\":\"queued\"")))
                .andExpect(content().string(
                        containsString("\"state\":\"done\"")));
    }

    @Test
    void writesSseFieldsAndCompletes() throws Exception {
        MvcResult result = mvc.perform(get("/demo/sse")
                        .accept("text/event-stream"))
                .andExpect(request().asyncStarted())
                .andReturn();

        result.getAsyncResult(5_000L);

        mvc.perform(asyncDispatch(result))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(
                        "text/event-stream"))
                .andExpect(content().string(
                        containsString("event:progress")))
                .andExpect(content().string(
                        containsString("data:queued")))
                .andExpect(content().string(
                        containsString("event:finished")));
    }

    @Test
    void writesCsvBytesInAsyncCallback() throws Exception {
        MvcResult result = mvc.perform(get("/demo/report.csv"))
                .andExpect(request().asyncStarted())
                .andReturn();

        result.getAsyncResult(5_000L);

        mvc.perform(asyncDispatch(result))
                .andExpect(status().isOk())
                .andExpect(header().string(
                        "Content-Disposition",
                        "attachment; filename=\"report.csv\""))
                .andExpect(content().string(
                        "id,name\n1,Ada\n2,Lin\n"));
    }
}
```

Run:

```bash
./gradlew test
```

The three tests are **designed to pass** with the Spring Boot 3.5 project and full source above; this is a **reviewed expectation**, **not an executed Gradle result**. Tests use `asyncDispatch` once the async result signal is present, following Spring's documented way to test MVC async.

**MockMvc limitation:** if a test needs to prove *partial streaming before completion*, do not just assert the body after `asyncDispatch`. Boot `@SpringBootTest(webEnvironment=RANDOM_PORT)` and use a client that reads the response **incrementally**, such as Java `HttpClient` with `BodyHandlers.ofInputStream()` or an appropriate HTTP/SSE client.

## 12. Testing directly on an embedded server and avoiding false positives

With Servlet streaming, a test that only reads the full body after completion **does not prove** data was flushed early. To measure genuinely:

1. Start Boot on a real port (RANDOM_PORT).
2. Have a producer emit events at controlled intervals.
3. Have an HTTP client read `InputStream`/SSE frames while the response is still open.
4. Measure the arrival timestamp of the first frame without waiting for the entire stream.
5. Check status/Content-Type; close the client mid-stream.
6. Verify the producer/registry cleans up the connection and memory does not keep growing.
7. Repeat through staging reverse proxy/ingress/CDN.
8. Test slow networks, timeouts, and retry behavior.

Sample Java 17 client to read the response (fragment inside a real HTTP test):

```java
HttpClient client = HttpClient.newHttpClient();
HttpRequest request = HttpRequest.newBuilder()
        .uri(URI.create(
                "http://localhost:" + port + "/demo/sse"))
        .header("Accept", "text/event-stream")
        .GET()
        .build();

HttpResponse<InputStream> response =
        client.send(request, HttpResponse.BodyHandlers.ofInputStream());

try (BufferedReader reader = new BufferedReader(
        new InputStreamReader(
                response.body(), StandardCharsets.UTF_8))) {
    String line;
    while ((line = reader.readLine()) != null) {
        System.out.println(line);
    }
}
```

This is a **fragment**, requiring imports `java.net.http.*`, `java.net.URI`, `java.io.*`, `StandardCharsets`, and the `port` variable from `@LocalServerPort` in tests. The example stream is finite so the loop exits; infinite production streams require read deadlines/cancellation.

In real tests, use timeouts/Awaitility or bounded logic instead of infinite `Thread.sleep` or overly tight network timing assertions that make CI flaky.

## 13. Reverse proxies, browsers, and HTTP buffering

A stream that works properly in the controller can still be coalesced by a proxy:

```text
Producer send event 1 -----+
Producer send event 2 -----+--> Servlet output
Producer send event 3 -----+
                                |
                        NGINX / CDN buffer
                                |
                   Client receives all 3 at the end
```

Possible causes:

- Proxy `proxy_buffering`/compression prevents flushing per event.
- CDN caching/transformation, gateway timeouts, or WAF policies unsuitable for long-lived connections.
- Response compressed/buffered into one block before sending.
- Browser/devtools/curl output buffering.
- TCP segmentation/HTTP/2 framing not matching `send()` boundaries.
- Producer actually sending only after finishing all work.
- Undersized executor causing tasks to sit queued too long.

Checks to run:

- For SSE, send `Content-Type: text/event-stream` and an appropriate cache policy like `no-cache`.
- Check NGINX buffering. `X-Accel-Buffering: no` only takes effect if that proxy honors it.
- Use `curl -N` or an incremental HTTP client.
- Track timestamps at the producer, Servlet write, and client event receiver to isolate where the delay occurs.
- Do not disable buffering/caching globally unconditionally; configure per streaming route.
- Align proxy idle timeouts with an appropriate heartbeat interval.

**Never promise each `flush()` corresponds to one network packet**. Define SLAs based on when events appear at the client, and test through the actual production topology.

## 14. Backpressure, slow consumers, and resource limits

### 14.1. `ResponseBodyEmitter`/`SseEmitter` is not a message broker

If a producer generates 10,000 events/s while a client only reads 100 events/s, the application can:

- Block workers on socket writes.
- Accumulate queues inside emitter registries/broadcasters.
- Exhaust executor threads/heap.
- Time out or disconnect other clients.

Production solutions:

- Limit subscribers per user/tenant, total connections, and event rates.
- Use **bounded-capacity** queues instead of unbounded lists; apply explicit **drop/coalesce/disconnect policies**.
- Track metrics: active connections, queue depth, dropped events, average write latency, reconnect counts.
- For frequent progress updates, **coalesce** into the latest state instead of keeping every intermediate event.
- For events requiring durability, use a DB/event log/message broker; SSE is just the delivery layer to clients.
- Authorize subscription per stream and re-check access on reconnect.
- Avoid creating a new dedicated thread/scheduler **per client** without limits.
- Remove emitters from registries in `onCompletion`, `onTimeout`, and `onError`; stop corresponding heartbeats.

### 14.2. `StreamingResponseBody` is governed by client read speed

If exporting from a database or object storage, each download can hold a worker for the entire stream duration. Do not keep a `ResultSet`/DB transaction open for a long time just to feed a slow HTTP connection; consider:

- Generating a controlled temporary file and serving it via object storage/CDN.
- Asynchronous export jobs: `POST /exports` returns `202 Accepted` and `GET /exports/{id}` returns status.
- Streaming queries/cursors with designed timeouts/batch sizes and transaction boundaries.
- Bounded connection pools/CPU/memory/IO quotas.
- Range/206 support if users need resumable file downloads.

## 15. Security for SSE and streaming

### 15.1. Authentication/authorization

SSE connections can stay open for a long time. Do not check permissions only at subscribe time and assume the user retains access forever:

- Authenticate the initial request with Spring Security per your architecture.
- Authorize per resource/tenant for the event stream.
- If permissions are revoked mid-connection, consider disconnecting or bounding TTL and forcing reconnect/re-auth.
- Never broadcast tenant A's events to tenant B's subscribers.
- Never put access tokens in `?token=...` because URL queries can leak into browser history, logs, and proxies/APM.
- If cross-origin uses cookie sessions, use an exact CORS allowlist, CSRF for **other state-changing requests**, and review credentials policies.
- Avoid public response caching on streams containing private data.

### 15.2. Event data and frontend injection

`EventSource` exposes `event.data` as a string. If content is user-controlled, never assign it directly to `innerHTML`:

```javascript
source.addEventListener("progress", event => {
  const node = document.getElementById("progress");
  node.textContent = event.data; // Text, do not parse HTML.
});
```

This is a fragment assuming the DOM has an element with id `progress`. If using JSON, parse with `JSON.parse` and validate required schema/fields. SSE framing does not make embedded data HTML-safe.

### 15.3. File download headers

With `StreamingResponseBody`:

- Set `Content-Type` matching the data: `text/csv;charset=UTF-8`, `application/pdf`, `application/octet-stream`, etc.
- Use `Content-Disposition: attachment` when forcing downloads, and encode filenames using appropriate APIs instead of concatenating raw client filenames into headers.
- `X-Content-Type-Options: nosniff` helps when files might be MIME-sniffed by browsers.
- For private documents, use `Cache-Control: private` or `no-store`.
- Authorization must happen **before opening the stream**; do not rely solely on hard-to-guess file IDs.
- When exporting CSV from untrusted data, guard against **formula injection** in spreadsheet software.
- Never log downloaded bytes, access tokens, or signed URLs.

## 16. When to choose WebSocket or WebFlux over SSE/MVC streaming

| Need | Solution to consider |
| --- | --- |
| Browser only receives server → client updates, text events | **SseEmitter** |
| Server sends multiple object fragments/NDJSON over HTTP response | **ResponseBodyEmitter** |
| Direct file/CSV/binary delivery with low memory | **StreamingResponseBody** |
| Single async result, no streaming needed | `DeferredResult`/`Callable` |
| Continuous bidirectional communication, client streams events too | WebSocket / STOMP depending on use case |
| Huge connection/stream count needing non-blocking reactive I/O | Spring WebFlux or a reactive-capable gateway |
| Durable events/replay independent of the app | Event broker/log + SSE/WebSocket frontend API |
| Batch exports lasting minutes/hours | Background job + object storage + download |
| Client uses SSE but needs to send commands | EventSource GET + separate HTTP POST/PUT |

SSE suits many dashboard/notification use cases thanks to simplicity and built-in browser reconnection. However, HTTP GET streaming does not satisfy every bidirectional interaction and does not eliminate the need for brokers, event retention, auth, or rate limits.

## 17. Common errors and troubleshooting

| Symptom | Possible cause | How to investigate |
| --- | --- | --- |
| Controller returns emitter but browser sees nothing | Producer never called `send`, proxy buffering, wrong media type | Debug producer, `curl -N`, response headers |
| Request times out after a few seconds | Differing emitter/MVC/Servlet/proxy timeouts | Log callbacks and check proxy idle timeout |
| Browser SSE reconnects repeatedly after 2 events | Finite stream completed but EventSource auto-retries | Client calls `source.close()` on `finished` event |
| SSE delivers events yet `onmessage` never fires | Has `event: progress`, so `addEventListener("progress")` is required | Inspect wire frames |
| Client gets JSON parse error | Concatenated `{}{}` without newline/array delimiters | Use explicit NDJSON framing |
| `send` throws IOException when closing tab | Client disconnected during server write | Let container handle async error, clean up registry |
| App calls `completeWithError` after IOException | Incorrect lifecycle per Spring docs | Never call complete/error in write IOException branch |
| Error after sending bytes still returns HTTP 200 | Response committed, status cannot change | Design protocol error events/abort handling |
| Download uses excessive RAM | `readAllBytes`/materialized output | Stream buffered through `OutputStream` |
| CSV has garbled encoding | Charset mismatch or writer without explicit charset | Use UTF-8 consistently |
| CSV opened in Excel executes strange formulas | Formula injection from user fields | Escape/sanitize exports per policy |
| Thread pool exhausts with many SSE clients | Blocking writes/producer loops, unbounded connections | Executor metrics, connection caps, queue policy |
| Registry retains stale emitters forever | Missing cleanup onCompletion/error/timeout | Remove emitter, cancel heartbeat |
| MVC async fails to start | Servlet/filter `asyncSupported=false` | Check registrations |
| URL via gateway only appears when finished | Proxy buffering/compression or missing flush | Incremental HTTP test behind proxy |
| `Last-Event-ID` sent yet events are missing | No server-side replay store | Shared event log and resume policy |
| CORS fails on cross-origin EventSource | Mismatched origins/credentials | Configure CORS for the SSE endpoint |
| Authorization checked only on connect | User permissions changed mid-stream | TTL/re-auth/disconnect policy |
| MockMvc test fails because async not complete | Test did not wait for async result/dispatch | `getAsyncResult(...)` then `asyncDispatch(...)` |
| Streaming on WebFlux not using MVC classes | Mixing Servlet and reactive stacks | Use WebFlux `Flux`/ServerSentEvent APIs |

## 18. Differences across Spring Boot/Spring Framework versions

| Version | Notes |
| --- | --- |
| Spring Framework 5.x + Boot 2.x | `ResponseBodyEmitter`, `SseEmitter`, and `StreamingResponseBody` already exist; Servlet API mostly uses `javax.servlet.*` |
| Spring Framework 6.x + Boot 3.x | Java 17+, Servlet API `jakarta.servlet.*`; demo code targets this generation |
| Spring Framework 7.x + Boot 4.x | MVC streaming concepts continue, though starters/modules/test APIs and executor auto-configuration may change; check version-specific docs/BOM |

Specifically, **Spring Boot 3.5** changed the auto-configured TaskExecutor bean name: the bean is named `applicationTaskExecutor`, no longer defaulting to the `taskExecutor` alias as in earlier versions. Custom executor examples must verify the bean name and MVC's requirement for type `AsyncTaskExecutor`.

Spring Framework 6.2 added the ability to register multiple callbacks in the emitter lifecycle. Still, callback registration does not replace cleaning up producer tasks when streams time out or disconnect.

Do not mix WebFlux Java imports (`org.springframework.web.reactive.*`) with Servlet MVC (`org.springframework.web.servlet.mvc.method.annotation.*`). Similarly named APIs can have different execution contracts.

## 19. Production implementation checklist

- [ ] Choose the right representation: NDJSON, SSE, or raw bytes.
- [ ] `Content-Type` and client parsers match the wire format.
- [ ] Producers do not run unbounded loops on unmanaged request/worker threads.
- [ ] Executor has bounds/metrics/rejection strategy; streaming writes do not starve other workloads.
- [ ] Servlet and filters have `asyncSupported=true`; ASYNC mapping when needed.
- [ ] Emitter/MVC/container/proxy timeouts align with heartbeats/reconnects.
- [ ] `onCompletion`/`onError`/`onTimeout` clean up subscribers, queues, and scheduled tasks.
- [ ] After an IOException on emitter send, do not call `complete`/`completeWithError`.
- [ ] When response is committed, error handling follows the streaming protocol without assuming a new status code.
- [ ] SSE events have a clear `id/event/data` contract, with Last-Event-ID/replay if required by business rules.
- [ ] EventSource clients close streams intentionally; CORS/credentials are configured accurately.
- [ ] Private streams authorize per user/tenant and have a revocation strategy.
- [ ] Rate limits/connection caps/backpressure/slow-client policies are enforced.
- [ ] Downloads have appropriate Content-Disposition/MIME/cache/authorization headers.
- [ ] Never log raw tokens, query secrets, or sensitive stream payloads.
- [ ] Test MockMvc async semantics and test incremental streaming on a real container.
- [ ] Test through the final proxy/CDN, not just localhost.
- [ ] Multi-node scaling uses a shared event source when replay/ordering is required.
- [ ] Monitor active streams, disconnects, errors, timeout rates, queue depth, and memory.

## 20. Practice exercises

1. Replace `ResponseBodyEmitter` with `DeferredResult<List<Progress>>`. What is the difference in when the client receives each record and in memory usage?
2. Remove the `"\n"` sends in the NDJSON endpoint. Is the received body still valid NDJSON?
3. Replace `SseEmitter.event().name("progress")` by omitting `name`. Does the browser trigger `onmessage` or `addEventListener("progress")`?
4. Explain the difference between `id:42` and `Last-Event-ID:42`. Does Spring SseEmitter automatically store replay events?
5. Write an EventSource client that closes the stream when receiving the `finished` event, then test reopening the stream.
6. If a container proxy has a 60-second idle timeout while the server only emits events every 5 minutes, what heartbeat is needed?
7. When `emitter.send` throws IOException, should you call `completeWithError`? State the container-managed error handling sequence.
8. Why can a server with 500 SSE connections exhaust threads if producers or writes block? Propose limits and metrics.
9. Use `StreamingResponseBody` instead of `Files.readAllBytes` to serve a 2 GB file. How should Content-Length/Range/download cancellation be handled?
10. Modify the CSV export to include a user-supplied value starting with `=`. What risk arises when opened in a spreadsheet? What escaping policy is needed?
11. Add MockMvc tests for all three endpoints using `asyncDispatch`; why is asserting status before async completion insufficient?
12. Create a real HTTP test with `HttpClient.BodyHandlers.ofInputStream` measuring when the first SSE frame arrives versus when the producer completes.
13. With Spring Security cookie authentication enabled, what CORS/credentials setup does cross-origin EventSource require?
14. During a rolling deployment, a client reconnects with Last-Event-ID to a different node; where must state be stored?
15. Compare SSE, WebSocket, and WebFlux for a dashboard updating once per second versus a game needing 60 bidirectional updates per second.
16. If an `@Async` method tries to read `RequestContextHolder` or MDC, why are they not automatically present? Show how to pass immutable context safely.
17. When an application returns `ResponseEntity<SseEmitter>`, which headers should be configured before the first send and why do header changes fail once committed?
18. Write a fail-fast test when the executor runs out of queue capacity, and pick an appropriate HTTP status/retry policy for clients.

## 21. Official references

- [Spring Framework 6.2 — Asynchronous Requests and HTTP Streaming](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-ann-async.html): Servlet async lifecycle, ResponseBodyEmitter, SseEmitter, StreamingResponseBody, disconnects, and configuration.
- [Spring Framework 6.2 — ResponseBodyEmitter Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/servlet/mvc/method/annotation/ResponseBodyEmitter.html): send, timeout, complete, error, lifecycle callbacks.
- [Spring Framework 6.2 — SseEmitter Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/servlet/mvc/method/annotation/SseEmitter.html): SSE event builder, id/event/data/retry.
- [Spring Framework 6.2 — StreamingResponseBody Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/servlet/mvc/method/annotation/StreamingResponseBody.html): writeTo(OutputStream) and async execution.
- [Spring Framework 6.2 — AsyncSupportConfigurer Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/servlet/config/annotation/AsyncSupportConfigurer.html): MVC executor and default timeout.
- [Spring Boot 3.5 — Task Execution and Scheduling](https://docs.spring.io/spring-boot/3.5/reference/features/task-execution-and-scheduling.html): applicationTaskExecutor, ThreadPoolTaskExecutor, Boot defaults.
- [Spring Framework — MockMvc Async Requests](https://docs.spring.io/spring-framework/reference/testing/mockmvc/hamcrest/async-requests.html): asyncResult, asyncDispatch.
- [MDN — Using Server-Sent Events](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events/Using_server-sent_events): EventSource, SSE format, retry, Last-Event-ID, and comments.
- [Spring MVC — Controller Return Values](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/return-types.html): async return value types.
