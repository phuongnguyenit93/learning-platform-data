# StreamingResponseBody, ResponseBodyEmitter, and SseEmitter in Spring MVC

## Learning objectives

This article belongs to the **Servlet Concurrency** group in the **Spring Boot - web-runtime** module. After reading it, you will be able to:

1. Understand why Spring MVC uses **Servlet asynchronous request processing** to return multiple pieces of HTTP data over time rather than waiting for the entire content before responding.
2. Distinguish **StreamingResponseBody** (writing raw bytes directly), **ResponseBodyEmitter** (emitting objects through `HttpMessageConverter`), and **SseEmitter** (emitting standard Server-Sent Events).
3. Describe the request lifecycle: initial Servlet thread, async context, background producer, blocking response writes, completion, timeout, and error dispatch.
4. Distinguish Servlet async from **end-to-end non-blocking I/O** in Spring WebFlux; understand why a bounded `TaskExecutor` is still required in Spring MVC.
5. Design responses with proper **Content-Type**, data framing, encoding, and flushing; recognize the bug of concatenating JSON objects into an invalid single JSON body.
6. Build a runnable **Spring Boot 3.3.x / Spring Framework 6.1.x / Java 17+** application containing all three streaming endpoints, an explicitly configured thread pool, and lifecycle callbacks.
7. Test using **curl -N**, browser `EventSource`, and real HTTP integration tests; distinguish verifying content from verifying when chunks are received.
8. Configure appropriate timeouts, client-disconnect cleanup, heartbeats, and SSE reconnection behavior.
9. Analyze risks around memory, thread/connection exhaustion, slow consumers, proxy buffering, caching, CORS, authentication, and sensitive data.
10. Choose the right API for large reports, incremental data, live notifications, streaming JSON/NDJSON, and bidirectional updates.

**Versions:** Spring Boot 3.3.x on Java 17+, Spring Framework 6.1.x, Spring MVC, and a Servlet container such as Tomcat. These three classes live in **org.springframework.web.servlet.mvc.method.annotation** and are not the default classes of Spring WebFlux.

## 1. Why do we need streaming in the Servlet web runtime?

Normally a controller builds a complete response and Spring writes it:

~~~java
@GetMapping("/api/report")
List<ReportRow> report() {
    return service.findAll();
}
~~~

This snippet illustrates the idea and is not a standalone runnable file. With hundreds of thousands of rows, this approach can force the application to materialize a huge `List`, serialize it to JSON, and make the client wait a long time before seeing useful content.

Several use cases fit streaming well:

- Exporting **large CSVs/logs/reports** incrementally as bytes without holding the entire file on the heap.
- Emitting **multiple messages or objects** as progress unfolds when each message can be serialized independently.
- Sending **one-way server-to-browser notifications** such as job status, sensor readings, task progress, or data changes.
- Forwarding output from a downstream producer read in chunks.
- Keeping an HTTP connection open for a period to deliver new events.

With HTTP streaming, the client can receive response headers first and the body in multiple chunks, but **the exact timing of when the client application sees each chunk is not strictly guaranteed**: Servlet output buffering, TCP, compression, gateways, CDNs, browsers, or HTTP clients may batch data.

### Do not confuse streaming with automatic multithreading

Returning `StreamingResponseBody` or `SseEmitter` **does not automatically make a blocking database query non-blocking**. It enables asynchronous Servlet response handling; blocking I/O and producer logic still require appropriate resources.

## 2. How does Servlet async request processing work?

When a Spring MVC controller returns an async-capable return value, Spring integrates with Servlet asynchronous processing:

~~~text
Client opens HTTP connection
        |
        v
Tomcat worker thread
        |
        v
Servlet filters -> DispatcherServlet -> Controller
        |
        +--> Controller returns StreamingResponseBody / emitter
        |
        v
Servlet request enters asynchronous mode
        |
        +--> Initial request-handling thread is released
        |
        +--> HTTP response stays open
                   |
                   v
            Background producer /
            AsyncTaskExecutor
                   |
                   v
            Write data incrementally
                   |
                   +--> write/flush / emitter.send
                   +--> complete / timeout / error
                   |
                   v
             Async completion
             and/or dispatch
                   |
                   v
           HTTP response finishes
~~~

The framework uses Servlet async support, which fundamentally works like `request.startAsync()` and `AsyncContext` in the Servlet API. Normal applications **do not need** to call `startAsync()` themselves when returning the proper MVC return type.

Things to remember:

1. **The initial request thread is released** after shifting processing into async mode.
2. **The HTTP connection stays open** for the duration of the stream.
3. One or more producer tasks must be managed via an appropriate executor/scheduler.
4. **Writes to the Servlet response can block the thread** when the client reads slowly; using Servlet async does not turn every write into non-blocking I/O.
5. On complete/timeout/error, the container and Spring coordinate finishing the request; errors can trigger a final async dispatch and exception resolvers.

### Why is this a “Servlet Concurrency” topic?

An application handles many concurrent requests. With long-lived streaming requests, thread-pool structure, async timeouts, and open connection counts directly affect throughput and system stability.

A common mistake: spawning a new unbounded `Thread` per SSE request. With thousands of clients, threads or pending tasks can grow out of control. Capacity, backpressure, and connection lifetimes must be designed upfront.

## 3. Comparing all three APIs in one table

| Criterion | StreamingResponseBody | ResponseBodyEmitter | SseEmitter |
|---|---|---|---|
| Primary purpose | Write raw bytes directly | Emit multiple objects/parts over time | Emit standard SSE events |
| Interface/class | Functional interface | Class | Class extending `ResponseBodyEmitter` |
| Body API | `OutputStream` | `send(Object)`, `send(Object, MediaType)` | `send(event builder)` or `send(Object)` |
| Object conversion | You write bytes manually | Via `HttpMessageConverter` | Uses converter for event data |
| Content-Type | e.g. `text/plain`, `application/octet-stream`, `text/csv` | Contract-dependent: `text/plain`, custom framed format | `text/event-stream` |
| Emission unit | Any chunk of bytes | A serialized item | An SSE event/frame |
| Who performs writes? | Spring invokes `writeTo(...)` on an executor | Application-provided producer calls `send(...)` | Producer calls `send(...)` |
| Completion | `writeTo` finishes / throws | `complete()`, `completeWithError(...)` | `complete()`, `completeWithError(...)` |
| Good for downloads | Very suitable | Possible, though not the first choice | Not suitable |
| Good for browser `EventSource` | Not directly | No automatic SSE framing | Very suitable |
| Byte-level control | High | Per converter | Per SSE serializer |
| Spawns a producer thread itself? | Framework runs `writeTo` via async executor | No | No |
| Blocking I/O? | Possible | Possible | Possible |

**Short summary:**
- Need to write bytes from a file/report: **StreamingResponseBody**.
- Need to emit values in multiple batches that are not SSE: **ResponseBodyEmitter**.
- Need one-way browser notifications following the `EventSource` standard: **SseEmitter**.

## 4. StreamingResponseBody: writing directly to OutputStream

Spring MVC defines:

~~~java
org.springframework.web.servlet.mvc.method.annotation.StreamingResponseBody
~~~

It is a functional interface with one method:

~~~java
void writeTo(OutputStream outputStream) throws IOException;
~~~

You receive the HTTP response's `OutputStream` and write bytes yourself. Example:

~~~java
@GetMapping(
    path = "/api/export",
    produces = MediaType.TEXT_PLAIN_VALUE
)
StreamingResponseBody export() {
    return output -> {
        output.write("row-1\n".getBytes(StandardCharsets.UTF_8));
        output.flush();
        output.write("row-2\n".getBytes(StandardCharsets.UTF_8));
        output.flush();
    };
}
~~~

This is an **illustrative method inside a Spring MVC controller**, requiring imports and a matching app.

### What happens when the controller returns

1. The controller merely creates the `StreamingResponseBody` callback and returns.
2. Spring starts async handling.
3. The framework runs the `writeTo` callback on the appropriate async executor.
4. The callback writes to `OutputStream`; `flush` may request pushing buffers down to lower layers.
5. When the callback returns normally, Spring completes the response.
6. When the callback throws an exception, the framework/container handles the error via the async lifecycle.

With this type, you **do not** call `complete()`. Do not close the container-managed `OutputStream` yourself; let the framework manage response resources.

### What data fits StreamingResponseBody well?

- CSV generated record by record.
- Files read via `InputStream` and copied to `OutputStream` in chunks.
- Newly generated text log data.
- Compressed files or binary protocols produced incrementally.
- Output of a report generator processing batch by batch.

For existing files on disk, Spring also offers `Resource`, resource handlers, and HTTP Range support depending on the mechanism; do not use `StreamingResponseBody` for every file when `Resource` works better.

## 5. StreamingResponseBody and large files: avoid holding all data

Anti-example:

~~~java
@GetMapping("/download")
byte[] all() {
    return Files.readAllBytes(Path.of("large-report.bin"));
}
~~~

This illustrative snippet lacks error handling and is unsuitable for very large files because `readAllBytes` loads the entire file onto the heap.

Instead, stream with a buffer:

~~~java
@GetMapping(
    path = "/download",
    produces = MediaType.APPLICATION_OCTET_STREAM_VALUE
)
ResponseEntity<StreamingResponseBody> download() {
    Path path = Path.of("/var/app/reports/report.bin");
    StreamingResponseBody body = output -> {
        try (InputStream input = Files.newInputStream(path)) {
            input.transferTo(output);
            output.flush();
        }
    };

    return ResponseEntity.ok()
        .contentType(MediaType.APPLICATION_OCTET_STREAM)
        .body(body);
}
~~~

This is a **controller snippet** needing imports; the file must exist and be readable. Java's `InputStream.transferTo` copies using an internal buffer without holding the entire file in a single `byte[]`.

Additional design concerns:
- Download authentication/authorization.
- Application-controlled file paths—never concatenate unvalidated filenames from the client.
- Check file existence and handle errors **before the response commits** whenever possible.
- `Content-Disposition`, MIME type, and `Content-Length` when known and appropriate.
- Timeouts and protection against slow-reading clients.
- Stop writing if the client has closed the connection.

When HTTP Range, caching, or conditional GET is needed, `Resource`/`ResourceRegion`/resource handlers may be a better fit than a custom streaming callback.

## 6. ResponseBodyEmitter: multiple objects over one response

Class:

~~~java
org.springframework.web.servlet.mvc.method.annotation.ResponseBodyEmitter
~~~

It lets a request send multiple response parts **after the controller has already returned**.

Example:

~~~java
@GetMapping(
    path = "/api/progress",
    produces = MediaType.TEXT_PLAIN_VALUE
)
ResponseBodyEmitter progress() {
    ResponseBodyEmitter emitter = new ResponseBodyEmitter(15_000L);

    executor.execute(() -> {
        try {
            emitter.send("start\n", MediaType.TEXT_PLAIN);
            emitter.send("processing\n", MediaType.TEXT_PLAIN);
            emitter.send("done\n", MediaType.TEXT_PLAIN);
            emitter.complete();
        } catch (IOException ex) {
            // Spring/Servlet handles the I/O connection error notification.
        } catch (RuntimeException ex) {
            emitter.completeWithError(ex);
        }
    });

    return emitter;
}
~~~

This **snippet** assumes `executor` is already configured. In the complete hands-on example, `executor` is declared using `ThreadPoolTaskExecutor`.

### Why is an executor needed?

`ResponseBodyEmitter` **does not automatically run producer code on another thread**. It is only a channel for sending multiple parts. The application can receive events from a service, listener, or background task; in the demo, we use a bounded executor.

### What does send(Object, MediaType) do?

Spring MVC picks an appropriate `HttpMessageConverter` to serialize the object based on Java type and media type—for instance, sending a `String` as `text/plain`, or a DTO as `application/json` if a converter is present.

**Watch your formatting:** If you call `emitter.send(productDto, application/json)` three times, the HTTP body may contain consecutive JSON objects **without a valid delimiter for a single JSON document**. Do not assume it forms a JSON array.

Invalid example when a client expects one JSON document:

~~~text
{"id":1}{"id":2}{"id":3}
~~~

This is not a valid JSON array. If you want multiple JSON documents line by line, design proper NDJSON formatting:

~~~text
{"id":1}
{"id":2}
{"id":3}
~~~

For browser `EventSource`, use `SseEmitter` to get proper SSE framing. With a generic `ResponseBodyEmitter`, **the framing/record-separator rules are the API's responsibility**; the converter only turns each item into bytes.

### ResponseEntity<ResponseBodyEmitter>

You can return `ResponseBodyEmitter` as the body of a `ResponseEntity` to control status and headers:

~~~java
ResponseBodyEmitter emitter = new ResponseBodyEmitter();
return ResponseEntity.ok()
        .contentType(MediaType.TEXT_PLAIN)
        .body(emitter);
~~~

This is a snippet. Set a `Content-Type` matching the content. If the response is a text stream, avoid declaring `application/json` for a body containing arbitrary lines of text.

## 7. SseEmitter: emitting standardized HTTP events

Class:

~~~java
org.springframework.web.servlet.mvc.method.annotation.SseEmitter
~~~

`SseEmitter` **extends `ResponseBodyEmitter`**, adding helpers to build properly formatted SSE events. Server-Sent Events is a one-way HTTP protocol: **the server pushes events to the client**; browsers can use JavaScript `EventSource` to consume them and automatically reconnect if dropped.

An endpoint typically looks like:

~~~java
@GetMapping(
    path = "/api/events",
    produces = MediaType.TEXT_EVENT_STREAM_VALUE
)
SseEmitter events() {
    return new SseEmitter(30_000L);
}
~~~

This is only a snippet; without a producer calling `send(...)` and `complete`/timeout, the client receives no events. Returning an emitter **does not generate data by itself**.

### What does an SSE frame look like?

Example body:

~~~text
id:1
event:tick
data:{"id":1,"message":"hello"}

id:2
event:tick
data:{"id":2,"message":"world"}

~~~

Each event ends with a **blank line**. SSE supports fields such as `id`, `event`, `data`, `retry`, and comments; a single event can span multiple `data` lines. Spacing after colons and field ordering depend on the serializer, so avoid brittle raw-byte assertions when unnecessary.

`SseEmitter` supports a builder:

~~~java
emitter.send(
    SseEmitter.event()
        .id("42")
        .name("tick")
        .reconnectTime(3000L)
        .data(new Tick(42, "hello"), MediaType.APPLICATION_JSON)
);
~~~

This snippet assumes a `Tick` record and an existing `emitter`. The Jackson converter encodes the object to JSON and the SSE writer formats the frame.

### JSON inside SSE does not make the whole body application/json

With SSE, the **top-level `Content-Type` is `text/event-stream`**, even when each `data` field holds JSON.

The client must parse event framing first, and then it can run `JSON.parse(event.data)` in JavaScript. If you label the entire SSE stream as `application/json`, standard JSON parsers will fail on the `id`/`event`/`data` lines.

### How SSE differs from WebSocket

SSE:
- Primarily **one-way server -> client** over HTTP.
- Browser `EventSource` supports automatic reconnection.
- Content uses `text/event-stream` with UTF-8 framing.
- Well suited for notifications, job progress, and feed updates.
- When clients need to send messages back, they typically use separate HTTP requests.

WebSocket:
- Full-duplex connection; both client and server can actively push frames.
- Well suited for chat, collaboration, bidirectional real-time interaction, or custom protocols.
- Carries its own concerns around heartbeats, auth, state, load balancing, and capacity.

Do not use SSE for every real-time system if high-frequency bidirectional exchange is required.

## 8. Lifecycle comparison: StreamingResponseBody vs. emitters

### StreamingResponseBody

~~~text
Controller returns StreamingResponseBody
          |
Spring invokes writeTo(outputStream)
          |
Code writes bytes / flushes / continues
          |
Callback finishes
          |
Framework completes response
~~~

You do not call `complete` manually; the callback returning is the completion signal.

### ResponseBodyEmitter or SseEmitter

~~~text
Controller creates emitter and returns
          |
Producer on appropriate thread/scheduler
          |
emitter.send(item/event) multiple times
          |
emitter.complete() or completeWithError(...)
          |
Framework/container finishes async request
~~~

With emitters, **forgetting to call `complete` on a finite stream** can leave the request hanging until timeout. For infinite streams, design explicit cancellation/lifecycle rules and timeouts/heartbeats; holding connections open forever is not a safe default strategy.

### Timeout constructor

~~~java
ResponseBodyEmitter emitter = new ResponseBodyEmitter(15_000L);
SseEmitter sse = new SseEmitter(30_000L);
~~~

These values are in **milliseconds**. They set a per-emitter timeout—not the interval between events and not the client's reconnect delay. Actual timeouts are also governed by the Servlet container, reverse proxy, load balancer, and network.

## 9. AsyncTaskExecutor: do not leave it at defaults in production

Spring Framework recommends explicitly configuring an executor for blocking writes/`Callable` and related MVC async work. The default task executor for certain MVC async cases is **not suitable for production load**.

A bounded executor provides:
- A cap on worker threads.
- An explicit queue size.
- An overload/rejection strategy.
- Observability for active threads, queue depth, and rejected tasks.
- Separation between initial request threads and background producers.

### Configuration example

~~~java
@Bean
ThreadPoolTaskExecutor streamExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(4);
    executor.setMaxPoolSize(8);
    executor.setQueueCapacity(100);
    executor.setThreadNamePrefix("mvc-stream-");
    executor.initialize();
    return executor;
}
~~~

This is an illustrative `@Bean` method; the full example includes imports/class. A thread pool is **not an infinite solution**: once 8 threads are busy and 100 tasks are queued, the next task may be rejected. The API needs load-shedding policies and appropriate HTTP statuses rather than unbounded threads.

### Configuring Spring MVC async

~~~java
@Override
public void configureAsyncSupport(
        AsyncSupportConfigurer configurer) {
    configurer.setTaskExecutor(streamExecutor);
    configurer.setDefaultTimeout(30_000L);
}
~~~

This is a `WebMvcConfigurer` callback. If the project registers custom Servlet filters manually, `asyncSupported` and `ASYNC` dispatcher handling must be configured properly per the Servlet API. Default Spring Boot `starter-web` MVC auto-configuration usually configures the core parts.

**Note:** The executor used by the framework to invoke `StreamingResponseBody.writeTo` may differ from the executor you use yourself to call `emitter.send()`. In the example we inject the same bean into both MVC async config and the controller to manage total capacity clearly. Under heavy production load, you can separate producer executors from blocking-write executors as needed.

## 10. Timeouts and connection lifecycles

Spring Boot 3.3 provides the property:

~~~yaml
spring:
  mvc:
    async:
      request-timeout: 30s
~~~

It sets the MVC async request timeout. If unconfigured, the default depends on the Servlet container. For each `ResponseBodyEmitter`/`SseEmitter`, you can pass a per-instance timeout in milliseconds.

Do not conflate these distinct timeouts:
- **MVC async request timeout**.
- **Servlet container async timeout**.
- **Emitter timeout**.
- **Reverse proxy idle/read timeout**.
- **Load balancer/CDN timeout**.
- **Client/browser/network timeout**.
- **`EventSource` reconnection delay** determined by the `retry` field or the browser.

A 30-second SSE emitter timeout neither means the client receives an event every 30 seconds nor guarantees proxies keep the connection alive for 30 seconds.

### Emitter lifecycle callbacks

~~~java
emitter.onCompletion(() -> {
    // Stop producer, remove registry entry, close dedicated subscription.
});
emitter.onTimeout(() -> {
    // Mark timed out, cancel work if needed.
});
emitter.onError(error -> {
    // Log in a controlled manner, cancel producer if needed.
});
~~~

This snippet sits in a controller/service that holds an `emitter`.

**Callbacks do not replace application resource management.** They may be invoked from container threads as the Servlet async lifecycle transitions. Do not rely on callbacks running on the original request thread or in one fixed order in every scenario.

## 11. IOException when a client disconnects: avoid mishandling

When a client closes a tab, loses network, or a proxy closes the connection, writing to the Servlet response can throw an `IOException`.

For `ResponseBodyEmitter` or `SseEmitter`, Spring Framework specifies: when **`emitter.send` throws `IOException` because the remote client can no longer receive**, the application **must not call `emitter.complete()` or `completeWithError(IOException)`**. The Servlet container triggers the `AsyncListener` error notification and Spring MVC handles the final async dispatch/exception resolution.

Pattern showing the distinction:

~~~java
try {
    emitter.send("hello", MediaType.TEXT_PLAIN);
} catch (IOException disconnected) {
    // Stop the producer and clean up application state.
    // Do not call completeWithError solely because send threw IOException.
} catch (RuntimeException other) {
    emitter.completeWithError(other);
}
~~~

This is a snippet requiring `MediaType`/imports. An `IOException` is not the only proof of client disconnect, but when an I/O send fails, avoid triggering a duplicate final dispatch by reflexively calling `completeWithError`.

With **StreamingResponseBody**, `writeTo` can throw `IOException` and Spring handles it through the async mechanism. Do not swallow `IOException` and keep writing indefinitely; stop the work, close any input resources opened by the application, and let the framework finish the lifecycle.

### You cannot always change the HTTP status after the response commits

Once the server has sent `200` + headers + some bytes, a subsequent failure cannot reliably switch the response to a `500` JSON body or Whitelabel HTML page. The client may receive a truncated stream. Define protocol-level error events if your application needs the client to recognize mid-stream failures.

## 12. Heartbeats, proxy buffering, and slow clients

SSE often traverses:

~~~text
Browser EventSource
       |
       v
CDN / reverse proxy / ingress / load balancer
       |
       v
Tomcat + Spring MVC SseEmitter
~~~

Some proxies:
- Buffer multiple chunks before forwarding.
- Close idle connections sooner than the application wants.
- Enforce maximum connection lifetimes.
- Apply HTTP compression that delays event flushing unexpectedly.
- Enforce separate connection or rate limits.

**`flush()` or `emitter.send()` is only an attempt to write to the next layer**; it does not guarantee the client immediately receives each event at the exact same moment.

### SSE heartbeat

An SSE comment-only frame:

~~~text
:keepalive

~~~

can keep the connection from appearing idle to layers that inspect traffic. With `SseEmitter` you can send a comment via the builder:

~~~java
emitter.send(SseEmitter.event().comment("keepalive"));
~~~

This is a snippet; you need an appropriate periodic heartbeat policy and must stop when the client disconnects. Do not send heartbeats too frequently and waste bandwidth/CPU.

Proxies such as Nginx may have their own buffering policies; depending on your architecture, consider no-buffer settings or proxy-specific headers per proxy policy. Never claim an arbitrary header disables buffering across every CDN.

### Slow consumers and memory

When a client reads slowly:
- A blocking write can hold a worker thread for a long time.
- A producer may generate data faster than the network drains it.
- Per-client event queues can grow memory usage.
- Many simultaneous idle connections consume file descriptors, session/state objects, and container resources.

Systems need **bounded queues**, timeouts, producer cancellation, and rules to drop or coalesce events when appropriate. Spring MVC async does not automatically solve all application backpressure.

## 13. SSE id, Last-Event-ID, and reconnect

Browser `EventSource` supports automatic reconnection when a connection closes and can send **`Last-Event-ID`** if it previously received an event with an `id`.

Stream example:

~~~text
id:101
event:order-change
data:{"orderId":7,"status":"SHIPPED"}

id:102
event:order-change
data:{"orderId":8,"status":"PAID"}

~~~

After an interruption, the browser can open a new connection including:

~~~http
Last-Event-ID: 102
~~~

**`SseEmitter` does not automatically store event history or replay missed events.** If you need lossless notifications, the application must implement storage/sequence IDs and resume logic. You can:

1. Assign monotonically increasing IDs from a reliable source.
2. Persist a window of events (database, log, or message broker).
3. Read `Last-Event-ID` on the new request.
4. Replay events with IDs greater than that value, subject to ordering/retention rules.
5. Have the client deduplicate events since reconnect/retry may deliver duplicates.

### EventSource in the browser

~~~javascript
const stream = new EventSource("/api/sse/ticks");

stream.addEventListener("tick", event => {
  const payload = JSON.parse(event.data);
  console.log(payload.id, payload.message, event.lastEventId);
});

stream.onerror = () => {
  console.log("SSE connection interrupted or unavailable");
};

// When events are no longer needed:
// stream.close();
~~~

This snippet targets browser JavaScript on the same origin as the endpoint. Cross-origin usage requires proper CORS and credential policies. The standard browser `EventSource` API **does not let you pass arbitrary `Authorization` headers** in its constructor; design authentication using same-origin cookies, a gateway, or another transport—avoid putting sensitive tokens in URLs whenever possible.

### Reconnect does not equal exactly-once delivery

Browser reconnection can cause duplicate or missed events if the server does not keep history. If an API needs transactional semantics, do not rely on SSE framing alone; define explicit offsets, replay, and idempotency.

## 14. Hands-on example: one Spring Boot MVC app with all three APIs

This project uses **Spring Boot 3.3.x, Java 17+, and `spring-boot-starter-web`**, without `starter-webflux`.

### 14.1. Dependencies

In a Gradle Spring Boot project that already has plugins, repositories, and a Java toolchain:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

This is only the **`dependencies` block**, not a full `build.gradle`. Use the Gradle wrapper provided by the project. Spring Boot 3.3.x requires Java 17 or newer.

### 14.2. Complete Java file

Create **src/main/java/com/example/streammvc/ServletStreamingApplication.java**:

~~~java
package com.example.streammvc;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.atomic.AtomicBoolean;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.CacheControl;
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
public class ServletStreamingApplication {

    public static void main(String[] args) {
        SpringApplication.run(ServletStreamingApplication.class, args);
    }

    @Bean
    ThreadPoolTaskExecutor streamExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("mvc-stream-");
        executor.initialize();
        return executor;
    }

    @Configuration(proxyBeanMethods = false)
    public static class MvcAsyncConfig implements WebMvcConfigurer {

        private final ThreadPoolTaskExecutor executor;

        public MvcAsyncConfig(ThreadPoolTaskExecutor executor) {
            this.executor = executor;
        }

        @Override
        public void configureAsyncSupport(
                AsyncSupportConfigurer configurer) {
            configurer.setTaskExecutor(executor);
            configurer.setDefaultTimeout(30_000L);
        }
    }

    public record Tick(int id, String message) {}

    @RestController
    public static class StreamingController {

        private final ThreadPoolTaskExecutor executor;

        public StreamingController(ThreadPoolTaskExecutor executor) {
            this.executor = executor;
        }

        // For lab demo: create an observable gap between parts.
        private static boolean pause() {
            try {
                Thread.sleep(150L);
                return true;
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                return false;
            }
        }

        @GetMapping(
            path = "/api/stream/lines",
            produces = MediaType.TEXT_PLAIN_VALUE
        )
        public ResponseEntity<StreamingResponseBody> streamLines() {
            StreamingResponseBody body = output -> {
                for (int i = 1; i <= 3; i++) {
                    byte[] bytes = ("line-" + i + "\n")
                            .getBytes(StandardCharsets.UTF_8);
                    output.write(bytes);
                    output.flush();

                    if (!pause()) {
                        break;
                    }
                }
            };

            return ResponseEntity.ok()
                    .contentType(MediaType.TEXT_PLAIN)
                    .cacheControl(CacheControl.noCache())
                    .body(body);
        }

        @GetMapping(
            path = "/api/emit/lines",
            produces = MediaType.TEXT_PLAIN_VALUE
        )
        public ResponseEntity<ResponseBodyEmitter> emitLines() {
            ResponseBodyEmitter emitter =
                    new ResponseBodyEmitter(15_000L);
            AtomicBoolean active = new AtomicBoolean(true);

            emitter.onCompletion(() -> active.set(false));
            emitter.onTimeout(() -> active.set(false));
            emitter.onError(error -> active.set(false));

            executor.execute(() -> {
                try {
                    for (int i = 1; i <= 3 && active.get(); i++) {
                        emitter.send(
                                "part-" + i + "\n",
                                MediaType.TEXT_PLAIN
                        );
                        if (!pause()) {
                            break;
                        }
                    }
                    if (active.get()) {
                        emitter.complete();
                    }
                } catch (IOException disconnected) {
                    // Servlet/Spring handles the async I/O failure.
                    // Producer must stop; do not call completeWithError
                    // solely because emitter.send threw IOException.
                    active.set(false);
                } catch (RuntimeException ex) {
                    active.set(false);
                    emitter.completeWithError(ex);
                }
            });

            return ResponseEntity.ok()
                    .contentType(MediaType.TEXT_PLAIN)
                    .cacheControl(CacheControl.noCache())
                    .body(emitter);
        }

        @GetMapping(
            path = "/api/sse/ticks",
            produces = MediaType.TEXT_EVENT_STREAM_VALUE
        )
        public ResponseEntity<SseEmitter> ticks() {
            SseEmitter emitter = new SseEmitter(15_000L);
            AtomicBoolean active = new AtomicBoolean(true);

            emitter.onCompletion(() -> active.set(false));
            emitter.onTimeout(() -> active.set(false));
            emitter.onError(error -> active.set(false));

            executor.execute(() -> {
                try {
                    for (int i = 1; i <= 3 && active.get(); i++) {
                        emitter.send(
                            SseEmitter.event()
                                .id(Integer.toString(i))
                                .name("tick")
                                .reconnectTime(2000L)
                                .data(
                                    new Tick(i, "tick-" + i),
                                    MediaType.APPLICATION_JSON
                                )
                        );
                        if (!pause()) {
                            break;
                        }
                    }
                    if (active.get()) {
                        emitter.complete();
                    }
                } catch (IOException disconnected) {
                    active.set(false);
                    // Do not call completeWithError when send causes an I/O error.
                } catch (RuntimeException ex) {
                    active.set(false);
                    emitter.completeWithError(ex);
                }
            });

            return ResponseEntity.ok()
                    .contentType(MediaType.TEXT_EVENT_STREAM)
                    .cacheControl(CacheControl.noCache())
                    .body(emitter);
        }
    }
}
~~~

**This is a complete Java source file inside a Spring Boot project that already has dependencies**; it cannot be compiled/run with bare `javac` without specifying the Spring/Jackson/Servlet classpath.

### Code explanation

- **streamExecutor():** creates a `ThreadPoolTaskExecutor` with `core=4`, `max=8`, `queue=100`. These are illustrative values to bound resources, not general production sizing recommendations.
- **MvcAsyncConfig.configureAsyncSupport:** supplies the executor to Spring MVC async and sets a 30-second timeout.
- **streamLines():** returns `StreamingResponseBody`; the framework runs `writeTo` on the async executor. The code writes three UTF-8 lines, flushing after each line.
- **emitLines():** returns `ResponseBodyEmitter`; the producer on the executor calls `send(String, text/plain)` and then `complete`. `Content-Type` `text/plain` is set explicitly and each part ends with a newline.
- **ticks():** `SseEmitter` sends three events with `id`, event `name`, `retry`, and JSON-serialized `Tick` data; the top-level response is `text/event-stream`.
- **AtomicBoolean active:** callbacks mark the stream inactive; the producer checks it to avoid continuing sends after completion/timeout/error. This is minimal cleanup for a short demo, not a full registry or cancellation framework for long-lived streams.
- **IOException from `emitter.send`:** the producer stops, letting Spring/Servlet handle the async I/O error; the code does not call `completeWithError` for `IOException` thrown by `send`.
- **RuntimeException:** `completeWithError` reports the error to the framework when still possible; it cannot guarantee changing the status if the response has already committed.
- **pause():** illustrative `Thread.sleep` so the three batches are visible; it runs on a bounded worker pool, not as a non-blocking technique. **Never use `Thread.sleep` on request threads or WebFlux event loops** in real applications.

### Risk of executor overload

When many streaming requests arrive concurrently, `executor.execute` may reject tasks because workers/queue are full. In this example, the rejection can propagate through the controller and produce an error response if uncommitted. Production needs overload policies: limits on concurrent streams, controlled rejection (such as 503 where appropriate), metrics/retry hints, and cleanup so the application stays stable.

### Scope of the demo

These are three **finite** streams (three batches each), not an infinite event-broadcasting system. In a large real-time service, use an event bus/pub-sub with bounded subscriptions, heartbeats, and cancellation instead of keeping a thread/task waiting indefinitely for every user.

## 15. Configuring application.yml and starting up

Create **src/main/resources/application.yml**:

~~~yaml
server:
  port: 8080

spring:
  mvc:
    async:
      request-timeout: 30s
~~~

The `spring.mvc.async.request-timeout` property in Boot 3.3 sets the MVC async timeout; the example also calls `configurer.setDefaultTimeout(30000L)`, aligning both at 30 seconds. Both emitters use a per-emitter timeout of 15 seconds.

On Linux/macOS:

~~~bash
./gradlew bootRun
~~~

On Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

Wait for embedded Tomcat to report it is running on port 8080. If the port is occupied, change `server.port` and use the new port in `curl`.

You do not need `@EnableAsync` just because controllers return `StreamingResponseBody`/`ResponseBodyEmitter`/`SseEmitter`; this is **Servlet MVC async return-value support**. `@EnableAsync` serves a different purpose: `@Async` method invocations.

## 16. Testing StreamingResponseBody with curl

Run:

~~~bash
curl -i -N \
  -H 'Accept: text/plain' \
  http://localhost:8080/api/stream/lines
~~~

A valid body:

~~~text
line-1
line-2
line-3
~~~

- **-i** displays status and headers.
- **-N** or `--no-buffer` reduces client-side buffering in curl so batches are visible.
- The body uses `text/plain`, not JSON.
- Flushing happens after every line in server code, though proxies/TCP/clients may still buffer.

### Checking integrity when saving to a file

~~~bash
curl -sS -N \
  http://localhost:8080/api/stream/lines \
  -o lines.txt
~~~

`lines.txt` contains the three lines above, each terminated by a newline character. Do not treat newline characters as TCP chunk boundaries; HTTP framing and application payloads are two separate layers.

### Binary downloads

When streaming real files, use `application/octet-stream` or a specific media type and an appropriate `Content-Disposition`. For binary data, never print raw bytes to a terminal or convert bytes to `String` just to inspect them: use checksums, a hex viewer, or byte size.

## 17. Testing ResponseBodyEmitter with curl

~~~bash
curl -i -N \
  -H 'Accept: text/plain' \
  http://localhost:8080/api/emit/lines
~~~

A valid body:

~~~text
part-1
part-2
part-3
~~~

In the example, the application itself appends a newline to each `String` before sending; **`ResponseBodyEmitter` does not automatically insert newlines between objects**.

If you replace the `String` values with DTOs under `application/json`, you must define a specific framing contract. Three concatenated JSON DTOs do not form a valid JSON array. To stream multiple JSON objects, consider proper NDJSON or use SSE if items represent events.

## 18. Testing SseEmitter with curl

~~~bash
curl -i -N \
  -H 'Accept: text/event-stream' \
  http://localhost:8080/api/sse/ticks
~~~

The response typically has `Content-Type` `text/event-stream`. The body looks equivalent to:

~~~text
id:1
event:tick
retry:2000
data:{"id":1,"message":"tick-1"}

id:2
event:tick
retry:2000
data:{"id":2,"message":"tick-2"}

id:3
event:tick
retry:2000
data:{"id":3,"message":"tick-3"}

~~~

The order of metadata lines inside an event, whitespace after colons, JSON field order, and flush timing may vary. Tests should assert **three valid events, `id`, `name`, `data`, and status/media type**, rather than comparing raw text against a rigid transcript.

### Parsing in the browser

~~~javascript
const events = new EventSource("/api/sse/ticks");

events.addEventListener("tick", event => {
  const item = JSON.parse(event.data);
  console.log(item.id, item.message);
});

events.onerror = () => {
  console.log("Connection interrupted, closed or retrying");
};

// Call events.close() when no longer needed.
~~~

With the demo endpoint, the server explicitly completes after three events. Browser `EventSource` **may reconnect after the server closes the stream normally**, because the EventSource protocol sees the stream end and applies retry logic. To stop the client completely after three events, browser code must invoke its own `close()` condition.

### PowerShell

On Windows, use `curl.exe` instead of the PowerShell alias:

~~~powershell
curl.exe -i -N -H "Accept: text/plain" "http://localhost:8080/api/stream/lines"
curl.exe -i -N -H "Accept: text/plain" "http://localhost:8080/api/emit/lines"
curl.exe -i -N -H "Accept: text/event-stream" "http://localhost:8080/api/sse/ticks"
~~~

## 19. Testing over real HTTP with TestRestTemplate

Testing the **final content** of finite streams can use an HTTP client that buffers the full response. To prove chunk delivery timing, add a streaming client test that records read timestamps/flush observations; you cannot prove incremental delivery from a single `String` captured after completion.

Create **src/test/java/com/example/streammvc/ServletStreamingApplicationTests.java**:

~~~java
package com.example.streammvc;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
class ServletStreamingApplicationTests {

    @Autowired
    TestRestTemplate http;

    private ResponseEntity<String> get(
            String path, MediaType accept) {

        HttpHeaders headers = new HttpHeaders();
        headers.setAccept(List.of(accept));

        return http.exchange(
                path,
                HttpMethod.GET,
                new HttpEntity<>(headers),
                String.class
        );
    }

    @Test
    void rawStreamingWritesThreeLines() {
        ResponseEntity<String> result =
                get("/api/stream/lines", MediaType.TEXT_PLAIN);

        assertEquals(200, result.getStatusCode().value());
        assertNotNull(result.getHeaders().getContentType());
        assertTrue(result.getHeaders().getContentType()
                .isCompatibleWith(MediaType.TEXT_PLAIN));
        assertEquals("line-1\nline-2\nline-3\n",
                result.getBody());
    }

    @Test
    void emitterSendsThreePlainTextParts() {
        ResponseEntity<String> result =
                get("/api/emit/lines", MediaType.TEXT_PLAIN);

        assertEquals(200, result.getStatusCode().value());
        assertEquals("part-1\npart-2\npart-3\n",
                result.getBody());
    }

    @Test
    void sseProducesEventStreamWithThreeEvents() {
        ResponseEntity<String> result =
                get("/api/sse/ticks", MediaType.TEXT_EVENT_STREAM);

        assertEquals(200, result.getStatusCode().value());
        assertNotNull(result.getHeaders().getContentType());
        assertTrue(result.getHeaders().getContentType()
                .isCompatibleWith(MediaType.TEXT_EVENT_STREAM));

        String body = result.getBody();
        assertNotNull(body);
        assertTrue(body.contains("event:tick"));
        assertTrue(body.contains("tick-1"));
        assertTrue(body.contains("tick-2"));
        assertTrue(body.contains("tick-3"));
    }
}
~~~

Run:

~~~bash
./gradlew test
~~~

On Windows:

~~~powershell
.\gradlew.bat test
~~~

These tests send requests through an embedded HTTP server on a random port and **wait for the finite streams to finish**. They verify HTTP status, `Content-Type`, and payload, but do not prove a line arrived at exactly 150 ms because buffering can occur.

### Why not rely solely on MockMvc?

MockMvc supports MVC async testing via `asyncStarted` and `asyncDispatch`, which is suited for verifying controller return values in the Spring MVC pipeline. However, MockMvc does not open real TCP connections and does not model transport/proxy behavior, flushing, or client disconnects. When learning HTTP streaming, complement it with real embedded-server integration tests like the ones above.

## 20. Distinguishing “correct body” tests from “incremental delivery” tests

A test reading the response body as a `String` after the server completes only proves the **final content**. To measure streaming delivery, use a client that reads input over time:

~~~text
T0: client sends GET /api/stream/lines
T1: client reads "line-1"
T2: client reads "line-2"
T3: client reads "line-3"
T4: EOF
~~~

A good test records timestamps as each line is read, includes timeouts, and avoids assuming exact OS/network scheduler timing.

Java 17 HTTP client example in a separate test/demo program:

~~~java
HttpClient client = HttpClient.newHttpClient();

HttpRequest request = HttpRequest.newBuilder(
        URI.create("http://localhost:8080/api/stream/lines"))
    .header("Accept", "text/plain")
    .GET()
    .build();

HttpResponse<Stream<String>> response = client.send(
        request, HttpResponse.BodyHandlers.ofLines());

try (Stream<String> body = response.body()) {
    body.forEach(System.out::println);
}
~~~

This is a **snippet** requiring `java.net.http.*`, `java.net.URI`, and `java.util.stream.Stream` imports, with the server running. It is not a standalone Java file because it lacks a `main` class. For the three-line endpoint, the output content is:

~~~text
line-1
line-2
line-3
~~~

Exact 150 ms intervals between lines are not guaranteed because the JVM, OS, TCP, Servlet/container, and proxies each have their own scheduling.

## 21. Filters, asyncSupported, and DispatcherType

Spring MVC async builds on the Servlet container. In custom deployments, Servlets and Filters must permit async processing:

- Servlet/Filter declarations have **`asyncSupported=true`** where required.
- Filter mappings may need **`DispatcherType.ASYNC`** depending on what they inspect.
- Some filters are invoked again on `ASYNC` dispatch; do not assume they run only once for the whole lifecycle.
- Request/response wrappers must be compatible with the async lifecycle; otherwise exceptions or write errors can occur.

With default Spring Boot `starter-web` auto-configuration, the core settings are usually handled. When creating `FilterRegistrationBean` or registering Servlets manually, verify `asyncSupported` and dispatcher types.

### Does OncePerRequestFilter really run once across every thread?

The class name indicates avoiding duplicate execution per dispatcher according to configuration and policy, yet an async dispatch can constitute another pass. Methods like `shouldNotFilterAsyncDispatch()` and dispatcher types govern whether the filter executes during `ASYNC` dispatch.

Do not use `ThreadLocal` to assume a request stays on the same thread forever: a request can move from a Servlet thread to an executor and return to an async dispatch on a different thread.

### Logging and MDC

If you use MDC/trace IDs with `ThreadLocal`, apply proper context propagation to async tasks or capture small immutable values beforehand. Never store an entire `HttpServletRequest` in a singleton for later reading, as request lifecycles and concurrency create serious risks.

## 22. Authentication, CORS, and browser EventSource

`SseEmitter` does not authenticate users on its own. Ensure routes are protected with Spring Security as needed and that every event contains only data the client is authorized to receive.

For browser `EventSource`:
- The standard constructor does not allow setting arbitrary custom HTTP headers.
- Same-origin cookie/session authentication can work when CSRF, `SameSite` cookies, and session policies are properly designed.
- Cross-origin requests require a CORS policy, potentially with credentials configuration if using cookies.
- Avoid putting sensitive access tokens in query strings whenever possible, as URLs appear in logs, browser history, and monitoring.
- Re-check authorization over the connection's lifetime if permissions can change.
- An already-open SSE stream can continue emitting after a user is revoked unless the producer checks permissions and cancels as required.

### SSE is just a representation

`EventSource` is a convenient client for SSE; the backend remains a standard HTTP endpoint testable with `curl` or custom clients. Never set `Content-Type: application/json` for the entire stream merely because the `data` field is JSON-serialized.

## 23. Caching, headers, and file downloads

For personalized/real-time responses, consider:

~~~http
Cache-Control: no-cache
Content-Type: text/event-stream
~~~

`no-cache` instructs caches to revalidate before reusing, **not** to forbid all storage. For sensitive data, you may need **`Cache-Control: no-store`** and matching policies. The sample app uses `CacheControl.noCache()` for illustration, not as a complete production security policy.

For downloads:

~~~http
Content-Type: application/octet-stream
Content-Disposition: attachment; filename="report.csv"
~~~

When the file is actually CSV, `text/csv` with an appropriate charset may be used instead of `octet-stream`, depending on how you want clients to handle it. `Content-Disposition` only suggests a download filename; it does not enforce access control or guarantee well-formed bytes.

### Should you set Content-Length?

If the total stream size is unknown ahead of time, you normally should not buffer the entire body just to measure `Content-Length`. HTTP/1.1 can use chunked transfer encoding, and HTTP/2 has its own framing; that belongs to the container/transport layer, not a 1:1 mapping where each `flush` equals one HTTP chunk.

## 24. Observability and system capacity limits

Streaming endpoints require different observability than short-lived REST endpoints:

| Metric | Reason |
|---|---|
| Open connections/streams count | Risk of exhausting sockets or resources |
| Async request duration | Detect hung streams or timeouts |
| TaskExecutor active threads | Assess blocking writes |
| Executor queue size / rejected tasks | Detect overload |
| Bytes sent / event rate | Measure throughput |
| Client disconnects / `IOException` | Distinguish dropped clients from server errors |
| Timeout count | Track idle/proxy/application timeouts |
| Producer backlog / retained events | Detect memory growth |
| 4xx/5xx / request latency | Monitor general HTTP errors |
| Event ID lag / replay rate | Track SSE reconnections |

Design **bounded resources** at every layer: active streams, producer subscriptions, per-client queues, max payload sizes, max execution times, connection quotas, and proxy limits.

### When should you avoid SseEmitter?

If an application needs tens of thousands of very long-lived connections where each connection ties up a blocking thread continuously, MVC emitters can incur heavy resource overhead. Evaluate **WebFlux non-blocking I/O**, messaging infrastructure, or WebSocket based on requirements—do not decide purely by connection count without benchmarking.

## 25. Common misconceptions

| Misconception | Reality |
|---|---|
| `StreamingResponseBody` means non-blocking response writes | `ServletOutputStream` writes can block |
| Returning `ResponseBodyEmitter` runs a producer automatically | The application must provide a producer/background thread or event source |
| `emitter.send` automatically appends a newline | No; the application must design framing |
| Three consecutive JSON `send` calls form a JSON array | Not guaranteed; they may become concatenated invalid JSON |
| `SseEmitter` is WebSocket | No; SSE is server-to-client `text/event-stream` |
| `EventSource` never reconnects after `complete` | Browsers may reconnect; the client must call `close` when done |
| SSE `id` automatically replays missed events | No; the app must store history and handle `Last-Event-ID` |
| Call `completeWithError` for every `IOException` from `send` | Spring docs advise letting Servlet/Spring handle I/O disconnects |
| Emitter timeout is the interval between events | No; it is the async lifecycle timeout |
| `flush` guarantees every line appears immediately in the browser | No; proxies, networks, and clients may buffer |
| MVC async needs no executor capacity planning | False; blocking writes and producers consume resources |
| Spawn a new thread indefinitely for each SSE client | Quickly exhausts threads/memory |
| No cleanup is needed once the client disconnects | Must cancel producers/subscriptions and remove registry entries |
| `@EnableAsync` is required for MVC streaming | No; this is a Servlet async return-value mechanism |
| `MockMvc` tests prove TCP streaming works | No; real HTTP tests are required |
| Use `Content-Type: application/json` for JSON inside SSE `data` | Wrong; top-level SSE is `text/event-stream` |
| An already-committed response can still be switched to a 500 JSON error | Not guaranteed |

## 26. Exercises

**Exercise 1 — Change the interval:** change `pause` from 150 ms to 500 ms and observe with `curl -N`. Measure per-line arrival times on the client and distinguish timeout from interval.

**Exercise 2 — NDJSON:** change `/api/emit/lines` into an endpoint emitting each line as a properly encoded JSON object terminated by a newline. Set media type `application/x-ndjson` and validate each line with an NDJSON parser. Do not emit raw concatenated JSON objects.

**Exercise 3 — Large file:** generate valid test data on disk and stream it with `StreamingResponseBody` + `InputStream.transferTo`; compare heap usage against `Files.readAllBytes` on the same file. Enforce request concurrency limits.

**Exercise 4 — SSE client:** run browser `EventSource`, listen for `"tick"` events, parse JSON, and call `close()` after `id=3` to avoid reconnection on the finite demo stream.

**Exercise 5 — SSE heartbeat:** design a long-lived event source with comment heartbeats. Test proxy idle timeouts and producer cleanup when the client closes.

**Exercise 6 — Last-Event-ID:** build a bounded in-memory or database event log, emit increasing event IDs, and on reconnect read `Last-Event-ID` and replay events still inside the retention window. Handle duplicate IDs.

**Exercise 7 — Overload:** run a safely bounded load test against executor `core=4, max=8, queue=100`; measure wait time and rejected tasks. Propose a controlled rejection policy instead of raising `maxThreads` without limit.

**Exercise 8 — HTTP tests:** write one test asserting only the full body after completion and another reading line by line with timestamps. Explain why the two tests verify different properties.

## 27. Self-check questions

**Question 1.** When should you choose `StreamingResponseBody` over `ResponseBodyEmitter`?

**Answer:** When the application wants direct control over raw bytes, such as exporting/downloading files or generating large reports chunk by chunk.

**Question 2.** Does `ResponseBodyEmitter` automatically add newlines or JSON array framing?

**Answer:** No. It writes each object through an `HttpMessageConverter`; the application must design the appropriate record separator/format.

**Question 3.** Which class does `SseEmitter` extend?

**Answer:** `ResponseBodyEmitter`.

**Question 4.** What is the top-level media type of SSE when event data contains JSON?

**Answer:** `text/event-stream`, not `application/json`.

**Question 5.** Does returning `StreamingResponseBody` release the initial Servlet request thread?

**Answer:** It can transition the request into Servlet async mode to release the initial thread; response writing can still block and run via an async executor.

**Question 6.** Why must `TaskExecutor` be configured rather than left at defaults?

**Answer:** To manage blocking writes and worker capacity, bound threads/queues, and prevent uncontrolled overload.

**Question 7.** What must a finite emitter do after sending three items?

**Answer:** Call `complete()`, otherwise the response may wait until timeout. `StreamingResponseBody` finishes when the `writeTo` callback exits.

**Question 8.** When `emitter.send` throws `IOException` because the remote client disconnected, should you always call `completeWithError`?

**Answer:** No. Spring Framework instructs letting the Servlet container/Spring async error listener handle the I/O failure; the application stops the producer and cleans up.

**Question 9.** Does an SSE `id` automatically guarantee exactly-once delivery and replay after reconnect?

**Answer:** No. The app must persist history/offsets, inspect `Last-Event-ID`, and handle duplicates or retention gaps.

**Question 10.** Does `flush()` guarantee the browser sees data immediately?

**Answer:** No. Proxies, TCP, compression, and clients may buffer.

**Question 11.** Does `MockMvc` prove HTTP network chunking?

**Answer:** No. It verifies MVC async request processing; testing real delivery requires an embedded HTTP server and streaming client.

**Question 12.** When the response has already committed and the producer throws an error, will the status definitely change to 500?

**Answer:** No. The stream may simply abort and the server logs the error.

## 28. Implementation checklist

- [ ] Confirmed the app runs **Spring MVC Servlet**, not confused with WebFlux.
- [ ] Chose `StreamingResponseBody` for bytes, `ResponseBodyEmitter` for multiple serialized parts, and `SseEmitter` for standard SSE.
- [ ] `Content-Type` matches framing: `text/plain`, `text/csv`, `application/octet-stream`, or `text/event-stream`.
- [ ] Avoided concatenating JSON objects into an invalid single JSON body.
- [ ] Configured bounded executors/schedulers and an overload policy.
- [ ] Configured `asyncSupported` when manually registering Servlets/Filters.
- [ ] Avoided relying on `ThreadLocal` request context across async threads without proper propagation.
- [ ] Configured MVC/emitter, reverse proxy, and client timeouts to match real requirements.
- [ ] Finite producers call `complete()`; long-lived producers implement cancellation/cleanup.
- [ ] `IOException` from `emitter.send` is handled per Servlet/Spring recommendations.
- [ ] Avoided promising that `flush` equals instant browser delivery.
- [ ] SSE includes heartbeats, event IDs/replay/reconnection when reliability is needed.
- [ ] Configured proper authentication/authorization and CORS; avoided putting tokens in URLs where possible.
- [ ] Added metrics: active streams, executor pool/queue, timeouts, disconnects, event rate.
- [ ] Tested responses through an embedded server and through a realistic proxy/gateway.
- [ ] For large files, avoided loading entire contents into `byte[]` or holding unbounded data in memory.
- [ ] Avoided assuming the response status can be changed after bytes have already committed.

## Official documentation

- [Spring Framework 6.1 — MVC Asynchronous Requests: HTTP Streaming, SSE, Raw Data, Disconnects, Configuration](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-async.html)
- [Spring Framework 6.1 — StreamingResponseBody Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/servlet/mvc/method/annotation/StreamingResponseBody.html)
- [Spring Framework 6.1 — ResponseBodyEmitter Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/servlet/mvc/method/annotation/ResponseBodyEmitter.html)
- [Spring Framework 6.1 — SseEmitter Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/servlet/mvc/method/annotation/SseEmitter.html)
- [Spring Boot 3.3 — Servlet Web Applications](https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html)
- [Spring Boot 3.3 — Common Application Properties, spring.mvc.async.request-timeout](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/)
- [MDN — Using Server-Sent Events](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events/Using_server-sent_events)