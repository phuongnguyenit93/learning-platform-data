# Spring MVC — Disconnect Detection, Resource Cleanup, and Post-Header Error Handling

## 1. Practical problem and goals

Spring MVC supports asynchronous processing via `Callable`, `DeferredResult`, `ResponseBodyEmitter`, `SseEmitter`, `StreamingResponseBody`, and certain reactive return types. A controller method can return long before the HTTP response closes. If a client closes the tab, loses network connectivity, cancels a download, or a reverse proxy proactively closes the connection, the server might still retain scheduled tasks, subscriptions, buffers, or streams serving that client.

Example SSE progress endpoint:

~~~http
GET /api/events HTTP/1.1
Accept: text/event-stream
~~~

Server emits:

~~~http
HTTP/1.1 200 OK
Content-Type: text/event-stream
Cache-Control: no-store

event: progress
data: {"job":"A123","percent":30}

: heartbeat

event: progress
data: {"job":"A123","percent":50}
~~~

A browser closing the tab after receiving 50% does not automatically invoke an instant "remote disconnected" callback on a Servlet thread at that exact moment. If the connection is dead yet no new writes occur, the backend may not know yet. Meanwhile, live objects can cause **memory leaks, task leaks, subscriber leaks, thread exhaustion, and wasted resources**.

After this lesson, you should be able to explain:

- **Disconnect detection**: Servlet API limitations, write/flush failures, SSE heartbeats, proxy idle timeouts, `IOException`, and `AsyncRequestNotUsableException`.
- **Lifecycle management**: `SseEmitter.onCompletion`, `onTimeout`, `onError`, `DeferredResult`, and container ASYNC dispatches.
- **Idempotent cleanup**: cleaning up client registries, ScheduledFutures, broker subscriptions, file/DB streams, queues, and MDC; guarding against racing callbacks.
- **Committed HTTP responses**: once status/headers are sent, you cannot arbitrarily flip status 200 to 500 or return a fresh JSON error body.
- **Streaming errors**: in-band SSE error events while the connection is still usable; stopping writes and cleaning up on I/O failures.
- **Testing**: Java 17 / Spring Boot 3.5, Maven, MockMvc async, and real socket disconnect tests.

This lesson covers **Spring MVC on the Servlet stack**. WebFlux and WebSocket have different lifecycles, APIs, and backpressure; do not copy assumptions from one stack to the other.

## 2. Servlet async processing lifecycle

### 2.1. Synchronous request

~~~text
Client -> Filter -> DispatcherServlet -> Controller
       -> View/Converter -> Response write -> Request complete
~~~

Controller return normally aligns closely with when the server finishes handling the response.

### 2.2. Callable and DeferredResult

~~~text
REQUEST dispatch
  |
  +-> Controller returns Callable/DeferredResult
  |
  +-> Servlet request enters async mode
  |
  +-> Initial servlet thread released
  |      HTTP response remains pending
  |
  +-> Worker or callback provides result
           |
           v
       ASYNC dispatch
           |
           v
       Serialize/complete response
~~~

- `Callable<T>`: Spring MVC submits the Callable to `AsyncTaskExecutor`; once it returns a value or throws an exception, the request is async-dispatched to complete.
- `DeferredResult<T>`: the application holds the handle and calls `setResult` or `setErrorResult` from another callback/thread; MVC processes the final outcome.
- `SseEmitter` and `ResponseBodyEmitter`: a single request can emit **multiple** chunks/events until completion, timeout, or error.
- `StreamingResponseBody`: the callback writes directly to OutputStream; Spring MVC uses an executor for writing, though Servlet I/O usually remains blocking.

**Controller return is not the end of an SSE resource's lifetime.** If you create a ScheduledFuture in the controller and cancel it in a `finally` block inside the controller method, the timer gets cancelled right before the stream even runs. Attach cleanup to **async lifecycle callbacks**.

### 2.3. Filters and interceptors change too

A `OncePerRequestFilter` can exit the initial REQUEST dispatch while an SSE stream stays open. Thus, duration measured by a `try/finally` around the initial `chain.doFilter` is **dispatch duration**, not the entire stream lifetime.

`AsyncHandlerInterceptor.afterConcurrentHandlingStarted(...)` is invoked when MVC enters concurrent processing, instead of immediate `postHandle` and `afterCompletion` on the first pass. When the result completes, an ASYNC redispatch may occur. Timeouts/disconnects need matching callbacks; never assume interceptor `afterCompletion` always runs at the moment the controller method returns.

Servlet configuration also requires `asyncSupported=true` on DispatcherServlet and relevant filters; filter mappings must consider `DispatcherType.ASYNC` if a filter must run on redispatch. Spring Boot normally configures baseline MVC integration, yet custom registrations still require verification.

## 3. When is a client disconnect detected?

**The Servlet API does not provide a reliable, immediate notification that a remote client just vanished.** This limitation is explicitly noted in Spring MVC documentation. With HTTP streaming, the common way to detect a client disconnect is **attempting a write**; when the TCP connection/proxy is no longer usable, write/flush can throw an exception.

### 3.1. A timeline

~~~text
12:00:00  Browser opens EventSource
12:00:01  Server sends event #1
12:00:05  Browser loses network / closes tab
12:00:06  No events to send -> server may not know yet
12:00:15  Heartbeat write/flush -> failure may be detected
12:00:15+ AsyncListener/container error notification
           Spring MVC completes async lifecycle
~~~

Timestamps are illustrative only. OS socket buffers, reverse proxy buffering, TCP timeouts, kernel/network stacks, and container flushing can prevent **the first write after disconnect from failing immediately**. Heartbeats shrink the silent window without guaranteeing detection in an exact number of seconds.

### 3.2. Signals to distinguish

| Event | Reasonable meaning | What NOT to infer |
| --- | --- | --- |
| `IOException: Broken pipe` | Writing to a closed or reset connection | Every IOException is a deliberate user cancel |
| `Connection reset by peer` | Peer/proxy TCP reset | HTTP status 500 was returned to the client |
| `AsyncRequestNotUsableException` | Async response is no longer usable due to write error, container error, or completed lifecycle | You can keep writing more JSON |
| `SseEmitter.onError(Throwable)` | Container reported an async error | Definitely caused by user closing tab |
| `SseEmitter.onTimeout()` | Servlet async timeout | User actively disconnected |
| `SseEmitter.onCompletion()` | Async request ended for any reason | Always an error |
| `emitter.send(...)` throws no exception | Current write API reported no error | Client rendered/received the full payload |

Specific class:

~~~java
import org.springframework.web.context.request.async.AsyncRequestNotUsableException;
~~~

`AsyncRequestNotUsableException` extends `IOException` and indicates the async response is no longer usable according to Spring/container mechanisms. You do not need to catch it individually on every endpoint; understand it when reading stack traces and designing cleanup.

### 3.3. Client-side close and server-side completion differ

Browser `EventSource.close()` stops opening/reconnecting on the browser side. The server may only find out after a write failure or container error/completion. Meanwhile, `emitter.complete()` is a **server-side** action marking the request finished; it does not mean "the remote browser actively disconnected".

Similarly, if a proxy idle timeout closes downstream while keeping upstream open briefly, detection timing can differ between gateway and application.

## 4. Heartbeats as part of SSE design

SSE supports comment-only events:

~~~text
: heartbeat

~~~

A line starting with `:` is a comment in SSE. Browsers normally ignore comments instead of firing business message events. Spring provides:

~~~java
emitter.send(SseEmitter.event().comment("heartbeat"));
~~~

Purpose:

- Triggers periodic write/flush attempts for a chance to detect closed connections.
- Reduces the risk of ingress/proxies considering the upstream response idle.
- Helps measure write failure rates and stream lifetimes.

However, a heartbeat does not prove every byte was processed by the browser; TCP/proxy buffers can let writes succeed temporarily even when downstream is gone.

### 4.1. Three timeouts to choose separately

| Timeout | Where | Notes |
| --- | --- | --- |
| Servlet async timeout | `new SseEmitter(timeoutMillis)` or MVC config | Limits async processing per container/Spring |
| Proxy read/idle timeout | Nginx, ingress, CDN | May close response if idle too long |
| Client idle/reconnect | Browser, HTTP client, mobile app | May auto-abort/reconnect per protocol |

For instance, `new SseEmitter(60_000L)` sets a 60-second async timeout. A heartbeat every 10 seconds **does not necessarily reset the async request deadline**. If streams must stay open longer, choose appropriate timeout/reconnection policies rather than just sending heartbeat comments.

### 4.2. Proxy buffering

Nginx may buffer data so the browser does not receive heartbeats in time even though Spring wrote them. In some configurations, the response can set:

~~~http
Content-Type: text/event-stream
Cache-Control: no-store
X-Accel-Buffering: no
~~~

`X-Accel-Buffering: no` is an Nginx-related hint, **not a browser SSE standard**, and can be ignored by upstream configs. Test through a real proxy and configure streaming/timeouts at every hop.

## 5. ResponseBodyEmitter, SseEmitter, and callbacks

### 5.1. Register lifecycle callbacks before publishing the emitter

~~~java
SseEmitter emitter = new SseEmitter(60_000L);
emitter.onTimeout(() -> cleanupOnce());
emitter.onError(error -> cleanupOnce());
emitter.onCompletion(() -> cleanupOnce());
return emitter;
~~~

This is a fragment; `cleanupOnce()` must belong to the actual connection state. Callbacks can fire on a **container thread**, not the controller thread. Multiple callbacks can fire for the same request.

Spring 6.2 Javadoc:

- `onTimeout(Runnable)`: container signaled an async timeout.
- `onError(Consumer<Throwable>)`: container signaled an async processing error.
- `onCompletion(Runnable)`: container completed the async request **for any reason**, including network errors and timeouts.

**onCompletion is terminal cleanup, not a dedicated disconnect detector.**

### 5.2. Crucial rule: IOException from emitter.send()

Spring MVC documentation states explicitly: when `ResponseBodyEmitter.send(...)` throws `IOException` (for example, the remote client left), **the application neither has to nor should call `emitter.complete()` or `emitter.completeWithError(exception)` solely for that write error**.

The Servlet container emits the async error notification itself; Spring MVC receives the error and handles it, potentially including an ASYNC dispatch to exception resolution. The application must **stop its producer and clean up resources it owns**.

Correct in principle:

~~~java
try {
    emitter.send(SseEmitter.event().name("update").data(payload));
} catch (IOException writeFailure) {
    cleanupMySubscription();
    // Do NOT call emitter.complete() / completeWithError(writeFailure).
}
~~~

This is a fragment using application-provided `payload` and `cleanupMySubscription`. It **differs** from self-detected business errors while the channel is still usable: in that case you can send an SSE error event or `completeWithError` depending on response state.

### 5.3. Do not attempt a second error write on a broken socket

Wrong:

~~~java
try {
    emitter.send(event);
} catch (IOException ex) {
    emitter.send(SseEmitter.event()
            .name("error")
            .data("Connection lost"));
}
~~~

The connection may no longer be usable; a second write usually just throws another exception. Do not try returning HTTP 500 JSON after SSE has started, because status/headers may already be committed.

## 6. What does HTTP response committed mean?

Servlet `HttpServletResponse` provides:

~~~java
boolean committed = response.isCommitted();
~~~

A response is **committed** once HTTP status and headers have been flushed out of the response buffer toward the output layer. After commit:

- You cannot retract an emitted 200 status and change it to 500/409/404 in the same response.
- You cannot send a brand-new response with different headers.
- `reset()` or `resetBuffer()` after commit can throw `IllegalStateException`.
- `sendError(...)` after commit cannot produce a valid replacement response; it can fail or cause secondary errors depending on the container.
- `@RestControllerAdvice`/`@ExceptionHandler` cannot turn already-sent SSE bytes into an `application/problem+json` body.

### 6.1. Timeline

~~~text
Controller returns SseEmitter
   |
Response headers prepared
   |
First event sent / flush occurs
   |
HTTP 200 + Content-Type are committed
   |
Later producer fails
   |
Cannot replace with HTTP 500 JSON on the same connection
~~~

Note that `setStatus(200)` does not necessarily commit immediately; buffering and flushing govern the exact moment. Never assume controller return equals response committed; when debugging you can inspect `isCommitted()`, while still adhering to the framework lifecycle.

### 6.2. Pre-commit errors

If the controller already knows the request is invalid/unauthorized/job missing, check **before creating or starting the stream**:

~~~java
@GetMapping(path = "/events/{jobId}",
            produces = MediaType.TEXT_EVENT_STREAM_VALUE)
SseEmitter events(@PathVariable String jobId) {
    jobService.verifyAccess(jobId);     // 401/403 if needed
    jobService.verifyExists(jobId);     // 404
    jobService.verifyStreamingState(jobId); // 409
    return streamService.subscribe(jobId);
}
~~~

This fragment requires implemented service methods. When an error occurs before commit, Spring `@ExceptionHandler` can return safe HTTP statuses and JSON/ProblemDetail. That is why validation, auth, and preconditions should be resolved early.

### 6.3. Post-commit error while still writable

A business producer encountering an error while the SSE channel remains usable can emit an **in-band error event**:

~~~text
event: app-error
data: {"code":"JOB_FAILED","message":"Cannot continue"}

~~~

In Java (fragment):

~~~java
emitter.send(SseEmitter.event()
        .name("app-error")
        .data(Map.of(
                "code", "JOB_FAILED",
                "message", "Cannot continue")));
emitter.complete();
~~~

The HTTP status remains the earlier 200; the frontend must distinguish **transport status** from **application-level event code**. Only do this when sending is possible; never use it to recover from a failed write or an unusable response.

### 6.4. Post-commit I/O error

If a write fails with `IOException`:

1. Cancel scheduled tasks, unsubscribe from brokers, and release business resources.
2. Do not attempt to emit JSON or an error SSE event.
3. Do not call `complete()/completeWithError()` solely because of an IOException from `ResponseBodyEmitter.send`.
4. Let the Servlet container/Spring complete the request error lifecycle.
5. Record appropriate metrics/logs, avoiding an ERROR stack trace for every normal browser tab close.

## 7. Idempotent cleanup and race conditions

A session can experience timeout, onError, write failure, manual cancel, shutdown, or completion within instants of each other. These callbacks can run on multiple threads.

Wrong:

~~~java
void cleanup() {
    registry.remove(id);
    future.cancel(false);
    subscription.close();
    activeCount.decrementAndGet();
}
~~~

If executed twice, activeCount is decremented twice; it can double-close or accidentally remove a different session sharing the same ID.

How to design it:

~~~java
final AtomicBoolean closed = new AtomicBoolean(false);

void cleanup() {
    if (!closed.compareAndSet(false, true)) {
        return;
    }
    registry.remove(id, thisSession);
    if (future != null) future.cancel(false);
    subscription.close();
    activeCount.decrementAndGet();
}
~~~

This is an illustrative fragment. Use a **unique connection ID**, `ConcurrentMap.remove(id, instance)`, and exactly-once cleanup. Also handle the race where `onCompletion` runs **before ScheduledFuture is assigned**: the setter stores the Future, checks `closed.get()`, and cancels if already closed.

### 7.1. Resources to clean up

| Resource | Action |
| --- | --- |
| Map holding SseEmitter/session | Remove exact object/value |
| Heartbeat ScheduledFuture | Cancel the connection's future |
| Broker subscription | Unsubscribe per SDK contract |
| Stream/file InputStream | Close via try-with-resources |
| DB cursor/transaction resources | Close at ownership boundary; do not hold open unnecessarily |
| Per-client queue/buffer | Clear references and enforce bounded capacity |
| Background job Future | Cancel/cooperative interrupt if client no longer needs it |
| MDC/ThreadLocal | Restore/clear on the corresponding worker thread |
| Active connections metric | Decrement once |
| Application scheduler | Shut down only when application lifecycle ends, never per client |

**Never take a shared executor and shut it down inside per-request `onCompletion`**, as doing so breaks all other clients.

### 7.2. Races to test

- Timeout callback fires right as the timer task is calling `send`.
- Write failure triggers container `onError` and eventually `onCompletion`.
- Future just scheduled when cleanup callback already ran.
- Client reconnects creating a new session for the same logical user; old session cleanup accidentally removes the new session.
- App shutdown occurs concurrently with client disconnect.
- Broker callback entered a queue before session close but executes after close.

Check `closed` before each send and keep state per connection; do not hold a global lock across network writes. Running operations may need separate cancellation/cooperative stopping.

## 8. SSE reconnect and Last-Event-ID

Browsers' `EventSource` typically auto-reconnects after certain connection errors. When SSE events include IDs:

~~~text
id: 102
event: update
data: {"percent":70}

~~~

the browser can send `Last-Event-ID: 102` upon reconnecting. The server **can only replay events** if it has real storage/sequence history; an in-memory emitter map provides no durability.

If zero lost events are required, you need:

- Monotonic/unique event IDs per stream contract.
- Durable event store or message broker retention.
- Reconnect with an authorized cursor.
- Replay from the next sequence, handling duplicates/idempotency.
- Retention window and defined behavior when a cursor is too old.

If only sending the latest progress value, you can choose a **latest-state snapshot on reconnect** instead of replaying everything.

The frontend should call `eventSource.close()` on unmount/when the stream is no longer needed to prevent endless reconnects. The server still needs cleanup on disconnect detection rather than relying solely on frontend compliance.

## 9. Runnable project: SSE + DeferredResult

The project uses Java 17, Spring Boot 3.5.0. It includes:

- `GET /api/stream`: opens SSE, sends a heartbeat every 10 seconds.
- `GET /api/once`: DeferredResult completed after 50 ms.
- `GET /api/stream-count`: counts active subscriptions for learning/easy testing.
- Lifecycle cleanup on `onCompletion`/`onTimeout`/`onError`, `AtomicBoolean` exactly-once.
- When `send()` throws IOException, only cleans up resources; does not call `emitter.complete`/`error`.
- A shared `ScheduledExecutorService` as a Spring bean, shut down on app stop.

### 9.1. Structure

~~~text
async-disconnect-demo/
├── pom.xml
└── src/
    ├── main/java/demo/AsyncDisconnectApplication.java
    └── test/java/demo/AsyncDisconnectTest.java
~~~

### 9.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>async-disconnect-demo</artifactId>
    <version>1.0.0</version>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
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

### 9.3. AsyncDisconnectApplication.java

Put all code into **one file** `src/main/java/demo/AsyncDisconnectApplication.java`. One top-level public class; remaining classes package-private. The demo has no database, no login/security, and no business broker.

~~~java
package demo;

import java.io.IOException;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

import jakarta.annotation.PreDestroy;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.CacheControl;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.context.request.async.DeferredResult;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

@SpringBootApplication
public class AsyncDisconnectApplication {
    public static void main(String[] args) {
        SpringApplication.run(AsyncDisconnectApplication.class, args);
    }
}

@Configuration
class SchedulerConfig {
    @Bean(destroyMethod = "shutdown")
    ScheduledExecutorService scheduler() {
        return Executors.newScheduledThreadPool(2);
    }
}

@Service
class StreamService {
    private static final Logger LOG =
            LoggerFactory.getLogger(StreamService.class);

    private final ScheduledExecutorService scheduler;
    private final ConcurrentMap<String, Connection> connections =
            new ConcurrentHashMap<>();

    StreamService(ScheduledExecutorService scheduler) {
        this.scheduler = scheduler;
    }

    SseEmitter subscribe() {
        String id = UUID.randomUUID().toString();
        SseEmitter emitter = new SseEmitter(60_000L);
        Connection connection = new Connection(id, emitter);
        connections.put(id, connection);

        emitter.onCompletion(() -> close(connection, "completion"));
        emitter.onTimeout(() -> close(connection, "timeout"));
        emitter.onError(ex -> {
            LOG.info("stream_error id={} kind={}",
                    id, ex.getClass().getSimpleName());
            close(connection, "container-error");
        });

        try {
            ScheduledFuture<?> future = scheduler.scheduleAtFixedRate(
                    () -> heartbeat(connection),
                    1, 10, TimeUnit.SECONDS);
            connection.setFuture(future);
        } catch (RuntimeException ex) {
            close(connection, "scheduler-failed");
            throw ex; // Emitter not returned yet; HTTP error handling still applies.
        }
        return emitter;
    }

    int activeCount() {
        return connections.size();
    }

    private void heartbeat(Connection connection) {
        if (connection.closed.get()) {
            return;
        }
        try {
            // SSE comment; browser does not dispatch a business message event.
            connection.emitter.send(
                    SseEmitter.event().comment("heartbeat"));
        } catch (IOException ioFailure) {
            // Do not call complete()/completeWithError() after a write IOException.
            LOG.info("stream_write_failed id={} kind={}",
                    connection.id,
                    ioFailure.getClass().getSimpleName());
            close(connection, "write-failure");
        } catch (IllegalStateException noLongerUsable) {
            close(connection, "not-usable");
        } catch (RuntimeException unexpected) {
            LOG.warn("stream_producer_failed id={} kind={}",
                    connection.id,
                    unexpected.getClass().getSimpleName());
            close(connection, "producer-failure");
        }
    }

    private void close(Connection connection, String reason) {
        if (!connection.closed.compareAndSet(false, true)) {
            return;
        }
        connections.remove(connection.id, connection);
        ScheduledFuture<?> f = connection.future;
        if (f != null) {
            f.cancel(false);
        }
        LOG.info("stream_closed id={} reason={}", connection.id, reason);
    }

    @PreDestroy
    void cleanupOnShutdown() {
        for (Connection connection : connections.values()) {
            close(connection, "shutdown");
        }
        // Spring destroys the scheduler bean; never shut down per client.
    }

    private static final class Connection {
        final String id;
        final SseEmitter emitter;
        final AtomicBoolean closed = new AtomicBoolean();
        volatile ScheduledFuture<?> future;

        Connection(String id, SseEmitter emitter) {
            this.id = id;
            this.emitter = emitter;
        }

        void setFuture(ScheduledFuture<?> scheduled) {
            this.future = scheduled;
            if (closed.get()) {
                scheduled.cancel(false);
            }
        }
    }
}

@RestController
class AsyncController {
    private final StreamService streams;
    private final ScheduledExecutorService scheduler;

    AsyncController(StreamService streams,
                    ScheduledExecutorService scheduler) {
        this.streams = streams;
        this.scheduler = scheduler;
    }

    @GetMapping(path = "/api/stream",
                produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    ResponseEntity<SseEmitter> stream() {
        return ResponseEntity.ok()
                .cacheControl(CacheControl.noStore())
                .header("X-Accel-Buffering", "no")
                .body(streams.subscribe());
    }

    @GetMapping(path = "/api/once",
                produces = MediaType.APPLICATION_JSON_VALUE)
    DeferredResult<ResponseEntity<Map<String, String>>> once() {
        DeferredResult<ResponseEntity<Map<String, String>>> result =
                new DeferredResult<>(2_000L);

        ScheduledFuture<?> future = scheduler.schedule(
                () -> result.setResult(
                        ResponseEntity.ok(Map.of("state", "done"))),
                50, TimeUnit.MILLISECONDS);

        result.onCompletion(() -> future.cancel(false));
        result.onError(error -> future.cancel(false));
        result.onTimeout(() -> {
            future.cancel(false);
            result.setErrorResult(
                    ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
                            .body(Map.of("code", "WAIT_TIMEOUT")));
        });
        return result;
    }

    @GetMapping("/api/stream-count")
    Map<String, Integer> count() {
        return Map.of("activeConnections", streams.activeCount());
    }
}
~~~

### 9.4. Why does this implementation handle races?

- `ConcurrentMap` uses a distinct ID per connection.
- `AtomicBoolean.compareAndSet(false,true)` guarantees cleanup runs **exactly once**.
- `connections.remove(id, connection)` avoids removing a different object sharing the key.
- `setFuture` re-checks `closed` because timeout could arrive before the Future is assigned.
- Callbacks cancel only the **owned scheduled task**, without shutting down the global scheduler.
- When `send` throws IOException, it does not proactively call `complete()` or `completeWithError()`; Spring/the container manages the async error.
- Timeout and error callbacks can execute on different threads; state/registries are designed to be thread-safe.
- `SseEmitter(60_000L)` has a 60-second timeout; heartbeats do not necessarily extend this timeout.

**Demo limitations:** One ScheduledFuture per connection incurs scheduling overhead with very large client counts; production can use shared heartbeat loops or other strategies. The in-memory registry is lost on restart and provides no replay. All demo endpoints are public; authentication/authorization and quotas are required for real data. `stream-count` should be a protected metric/admin endpoint.

### 9.5. Running and observing

From the Maven directory:

~~~bash
mvn spring-boot:run
~~~

Second terminal:

~~~bash
curl -N -i http://localhost:8080/api/stream
~~~

`-N` disables curl's output buffering, making it convenient to watch the stream. Response headers may include:

~~~http
HTTP/1.1 200
Content-Type: text/event-stream
Cache-Control: no-store
X-Accel-Buffering: no
~~~

After about one second and then every ten seconds:

~~~text
:heartbeat

:heartbeat

~~~

Open another terminal:

~~~bash
curl -s http://localhost:8080/api/stream-count
~~~

Example while one subscription is active:

~~~json
{"activeConnections":1}
~~~

Press Ctrl+C in the client. The server **may not know immediately**; after write/timeout callbacks, the registry cleans up and the count returns to 0:

~~~json
{"activeConnections":0}
~~~

These are illustrative results, not exact timing guarantees. In production observe proxy behavior, TCP buffering, heartbeat intervals, timeouts, and real active subscription counts.

### 9.6. Browser EventSource

~~~javascript
const source = new EventSource("/api/stream");

source.onopen = () => {
  console.log("SSE opened");
};
source.onerror = () => {
  console.log("Disconnected or reconnecting");
};

function stop() {
  source.close();
}
~~~

The demo only emits SSE **comments**, so the browser receives no business message events. If your application needs business events, send `event: update` and appropriate data, and register matching listeners. The client must call `close()` when the stream is no longer needed so it does not reconnect forever.

### 9.7. A single-result DeferredResult

~~~bash
curl -i http://localhost:8080/api/once
~~~

Equivalent output:

~~~json
{"state":"done"}
~~~

After roughly 50ms plus overhead, MVC redispatches the result. If the request times out before the task runs, the timeout callback cancels the Future and can set HTTP 503 per the demo policy; real races/Servlet container default handling must be tested. Calling `future.cancel(false)` after the Future already completed is harmless.

## 10. MockMvc tests

File `src/test/java/demo/AsyncDisconnectTest.java`:

~~~java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.hamcrest.Matchers.containsString;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.asyncDispatch;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.request;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class AsyncDisconnectTest {
    @Autowired MockMvc mvc;

    @Test
    void deferredResultCompletesViaAsyncDispatch() throws Exception {
        MvcResult initial = mvc.perform(get("/api/once"))
            .andExpect(request().asyncStarted())
            .andReturn();

        mvc.perform(asyncDispatch(initial))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.state").value("done"));
    }

    @Test
    void sseStartsAsyncWithStreamingHeaders() throws Exception {
        MvcResult result = mvc.perform(get("/api/stream"))
            .andExpect(status().isOk())
            .andExpect(request().asyncStarted())
            .andExpect(header().string(
                    HttpHeaders.CACHE_CONTROL, "no-store"))
            .andExpect(header().string(
                    "X-Accel-Buffering", "no"))
            .andExpect(header().string(
                    HttpHeaders.CONTENT_TYPE,
                    containsString("text/event-stream")))
            .andReturn();

        assertTrue(result.getRequest().isAsyncStarted());
    }

    @Test
    void countEndpointExposesNumericValue() throws Exception {
        mvc.perform(get("/api/stream-count"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.activeConnections").isNumber());
    }
}
~~~

Run:

~~~bash
mvn test
~~~

MockMvc checks MVC asyncStarted, asyncDispatch, and HTTP headers. It **does not fully simulate TCP disconnects**. With `SseEmitter`, a test reaching `andReturn()` when asyncStarted does not mean the stream completed; you must design timeout/lifecycle cleanup and, if needed, write integration tests against embedded Tomcat with real HTTP sockets.

## 11. StreamingResponseBody: handling mid-download errors

For large file downloads, Spring MVC offers `StreamingResponseBody`:

~~~java
@GetMapping("/download")
public StreamingResponseBody download() {
    return output -> {
        try (InputStream input = storage.open("report.csv")) {
            input.transferTo(output);
            output.flush();
        }
    };
}
~~~

This is a fragment requiring `InputStream`, `StreamingResponseBody` imports, and a real `storage` service. If writing to OutputStream fails due to a client disconnect:

- `try-with-resources` closes the InputStream.
- Do not attempt to write JSON `{"error":"..."}` onto the failed output.
- Record concise logs/metrics with proper classification.
- Stop producers and release resources/cursors tied to the download.

If the server already sent 5MB of a 10MB file before failing, HTTP headers/status may already be committed. The client receives an incomplete file rather than a fresh HTTP 500. If the protocol requires resume/integrity, provide accurate `Content-Length`, range requests, ETag/checksums, and explicit semantics.

**Blocking I/O:** StreamingResponseBody does not make JDBC/file/socket writes non-blocking. You need a bounded task executor, timeouts, quotas, and slow-client handling.

## 12. DeferredResult: timeouts and cancellation

`DeferredResult<T>` represents **a single** async result. Inside a callback:

~~~java
boolean accepted = result.setResult(value);
if (!accepted) {
    // Request already timed out/completed or result was already set.
    // Stop work that is no longer needed.
}
~~~

This is a fragment with `result`/`value` defined in the app. Do not emit results multiple times; do not assume the timeout callback always beats a task that is about to finish.

Lifecycle example:

~~~java
DeferredResult<String> response = new DeferredResult<>(5_000L);
response.onCompletion(() -> cancelJob());
response.onError(error -> cancelJob());
response.onTimeout(() -> {
    cancelJob();
    response.setErrorResult(new TimeoutException("Expired"));
});
~~~

This fragment requires `cancelJob()` and importing `TimeoutException`. `Future.cancel(true)` only sends an interrupt signal if the task supports it; it does not guarantee the thread stops. For jobs longer than HTTP timeouts, consider returning `202 Accepted + jobId` followed by client polling/SSE rather than keeping the connection open until the business job finishes.

## 13. Pre-commit and post-commit error design

| Timing | Example error | How to handle |
| --- | --- | --- |
| Before creating stream | Invalid input, 401/403, 404, business 409 | Return safe HTTP status + JSON/ProblemDetail |
| After stream starts while channel is usable | Job failed, business task stopped | Send SSE `app-error` event or finish per contract |
| After commit + write IOException | Broken pipe, connection reset | Stop writing, clean up producer, let container/Spring handle |
| After commit + internal producer failure | Serialization/business exception | In-band error if usable; otherwise log/cleanup/close |
| Uncommitted DeferredResult | Worker exception | `setErrorResult`, MVC exception resolver |
| Stream finishes normally | Business completed | `emitter.complete()` and onCompletion cleanup |
| Async timeout | Deadline exceeded | onTimeout cleanup, framework timeout behavior or result policy |
| Reverse proxy closes connection | Idle timeout/network | Often detected on next heartbeat/send |

Distinguish:

- **HTTP transport status** is finalized when the response commits.
- **Event-level status** can change inside the SSE payload since that is application data.
- **Business job state** can continue after the HTTP stream ends depending on business rules; cancelling SSE does not necessarily cancel a durable job.

Do not treat `@ExceptionHandler` as a "500 fixer for every situation", because it cannot undo bytes already sent.

## 14. Metrics and logging for streaming

Log on open and close:

~~~text
stream_open connectionId=<id> endpoint=/api/stream
stream_close connectionId=<id> reason=timeout lifetimeMs=60000
stream_write_failed connectionId=<id> kind=AsyncRequestNotUsableException
~~~

These are sample logs, not fixed output.

Useful metrics:

- Active SSE connections (gauge).
- Opened/closed totals by **bounded reason categories**.
- Stream lifetime histogram.
- IO write failures by endpoint/bounded reason.
- Timeout rate, reconnect rate, and heartbeat latency.
- Scheduler queue/executor saturation.
- Cleanup failures and broker subscription backlog.

Do not put userId/requestId/connectionId into Prometheus low-cardinality labels. Correlation IDs can appear in logs/traces subject to privacy review. Never log tokens, cookies, emails, or raw request bodies to debug disconnects.

Some gateways like Nginx log **499** for client-closed requests; that is a **nonstandard, proxy-specific** code, not an HTTP status Spring MVC needs to return to a disconnected client.

Normal "Broken pipe" errors from routine client disconnects usually do not warrant logging an ERROR stack trace every time; track them with counters and log at an appropriate level. If failures spike unexpectedly after a new deployment, investigate proxies/network/timeouts and code.

## 15. Slow clients, backpressure, and production capacity

SSE channels can hold thousands of connections. If the producer generates events faster than client networks read them, queues grow, RAM grows, and threads can block.

Recommendations:

1. Limit connections per instance/tenant/user according to trust and authentication policies.
2. Choose bounded buffers/queues, avoiding infinite per-client buildup.
3. For progress/latest state, prefer **coalescing**: keep the newest value instead of every stale event.
4. For data that must never be lost, use a durable log/replay cursor.
5. Choose schedulers/thread pools with metrics and clean shutdown.
6. Set heartbeats sensibly relative to proxy idle read timeouts.
7. Clean up broker subscriptions and Futures immediately when the lifecycle ends.
8. Do not hold database transactions, file handles, or ServletRequests open across a stream unnecessarily.
9. Run soak tests with many connections, slow readers, and disconnect storms.
10. Separate HTTP stream lifetime from business job lifetime; do not cancel durable jobs merely because a browser tab closed unless business rules require it.

### 15.1. Illustrative Nginx config

~~~nginx
location /api/stream {
    proxy_pass http://backend:8080;
    proxy_buffering off;
    proxy_read_timeout 120s;
}
~~~

This is a fragment requiring TLS, host validation, auth, and other routing config. `proxy_read_timeout` usually measures the idle gap between reads from upstream, not total stream lifetime. For SSE, test through the real public proxy, not just the backend.

If upstream already sent HTTP headers and later fails, the gateway likewise cannot emit a new HTTP 502 response inside the already-started stream; it usually has to close the connection. The client can reconnect per SSE semantics.

## 16. Practice questions

**Exercise 1:** A browser closes an SSE connection when the stream has no events for 2 minutes. Why does the Servlet API not guarantee immediate detection? How should heartbeats, timeouts, and proxies be designed?

**Exercise 2:** `SseEmitter.send()` throws `IOException: Broken pipe`. According to Spring, should you call `completeWithError` immediately inside the catch? Why clean up scheduled tasks while letting the container finish the lifecycle?

**Exercise 3:** `onError`, `onTimeout`, and `onCompletion` all invoke cleanup. Write code using `AtomicBoolean.compareAndSet` to avoid decrementing an active counter multiple times.

**Exercise 4:** An SSE response already sent status 200 and two events. A business exception occurs. Why can `@RestControllerAdvice` not turn it into HTTP 500? When should `event: app-error` be sent?

**Exercise 5:** A stream holds a broker subscription and a scheduled heartbeat. Draw the lifecycle of both resources on client disconnect, timeout, shutdown, and normal completion.

**Exercise 6:** A `DeferredResult` times out, yet the worker calls `setResult` afterward. Inspect the boolean return value and design appropriate cancellation.

**Exercise 7:** A 100MB file download aborts at the 1-millionth byte. How do you close the InputStream? Why can you not send JSON error details after file bytes have already been streamed?

**Exercise 8:** How does an SSE heartbeat comment differ from a business event? Does the browser fire a message event from a comment?

**Exercise 9:** Proxy buffering of SSE prevents the client from seeing data. Explain how to inspect `X-Accel-Buffering`, `proxy_buffering`, timeouts, and TCP socket behavior.

**Exercise 10:** Design metrics `stream.active`, `stream.closed.total{reason}`, and `stream.lifetime` while avoiding `connectionId` as a metric label.

**Exercise 11:** EventSource reconnects and the client must not lose messages. Design event IDs and replay history; if no durable history exists, what must the contract state?

**Exercise 12:** Write a MockMvc test for DeferredResult `asyncStarted`/`asyncDispatch` and propose a socket disconnect integration test that MockMvc cannot fully simulate.

## 17. Pre-deployment checklist

- [ ] Input, authentication, authorization, and business preconditions are checked before the stream commits.
- [ ] Async timeout, proxy idle timeout, and client reconnect policy are understood and defined.
- [ ] Periodic heartbeats exist without assuming instant disconnect detection.
- [ ] `onCompletion`/`onTimeout`/`onError` are registered when creating the emitter.
- [ ] Idempotent cleanup uses thread-safe state, cancels futures, unsubscribes from brokers, and removes from registries.
- [ ] IOException from `ResponseBodyEmitter.send` is not double-completed by the application.
- [ ] Post-commit exceptions do not attempt to change HTTP status or send a new JSON response.
- [ ] Event-level error protocol is clear if reporting errors while SSE remains usable.
- [ ] Per-user/per-instance limits, bounded buffers, and slow-client policies are in place.
- [ ] Shared executors are never shut down per request.
- [ ] Resource cleanup runs on application shutdown.
- [ ] Active/lifetime/disconnect/timeout metrics and leak alerts are configured.
- [ ] Tests cover streaming headers, MVC async lifecycle, concurrent callbacks, socket disconnects, and proxy behavior.
- [ ] Frontend EventSource closes when unneeded and handles reconnect/event replay intentionally.

## 18. Key takeaways

- **Servlets do not provide an immediate, reliable callback for remote disconnects.** Write failures or container async error notifications are typically how disconnects are detected.
- **SSE heartbeats** both keep the stream active and provide opportunities to detect broken connections.
- **onCompletion** fires for many reasons, so use it for terminal cleanup; **onTimeout/onError** provide extra signals rather than definitive proof of client cancellation.
- When **SseEmitter.send throws IOException**, stop the producer and clean up owned resources; **do not call complete or completeWithError** solely for that write error.
- Once the **HTTP response is committed**, you cannot change status/headers or return a new JSON error inside the same response.
- Business errors while SSE is still usable can be delivered via an **SSE app-error event**; transport errors stop writing.
- **Cleanup must be idempotent** because callbacks can race; every Future, subscription, and buffer must have a clear owner.
- `DeferredResult`, `StreamingResponseBody`, and MVC async filters/interceptors all need timeouts/cancellation at the right boundaries.
- MockMvc tests the MVC lifecycle, while **disconnects require integration tests with real sockets/proxies**.

## 19. Official documentation

- [Spring Framework 6.2 — Asynchronous Requests](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-ann-async.html): Callable, DeferredResult, ResponseBodyEmitter, SseEmitter, StreamingResponseBody, disconnects.
- [Spring Framework 6.2 — ResponseBodyEmitter](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/servlet/mvc/method/annotation/ResponseBodyEmitter.html): send, complete, completeWithError, and lifecycle callbacks.
- [Spring Framework 6.2 — SseEmitter](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/servlet/mvc/method/annotation/SseEmitter.html).
- [Spring Framework 6.2 — AsyncRequestNotUsableException](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/context/request/async/AsyncRequestNotUsableException.html).
- [Spring Framework 6.2 — DeferredResult](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/context/request/async/DeferredResult.html).
- [Jakarta Servlet 6.0 — ServletResponse](https://jakarta.ee/specifications/servlet/6.0/apidocs/jakarta.servlet/jakarta/servlet/servletresponse): isCommitted, reset, and resetBuffer.
- [HTML Living Standard — Server-sent events](https://html.spec.whatwg.org/multipage/server-sent-events.html): EventSource, SSE framing, reconnect.
