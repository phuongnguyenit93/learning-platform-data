# Client Disconnects, Unsubscribing, and Resource Cleanup in Spring Boot Long-Lived Connections

## 1. Problem: The Client Has Left, Yet Server Work Continues

A Spring Boot endpoint that receives an HTTP request, runs for a few milliseconds, and returns JSON has a short lifecycle. By contrast, **Server-Sent Events (SSE), WebSocket, streaming downloads, long polling**, and subscriptions to message brokers can live for tens of seconds, minutes, or longer. During that time, the server may hold timers, tasks, connections, registry entries, callbacks, threads, buffers, subscriptions, and connections to downstream systems.

Suppose a browser opens a dashboard page running `new EventSource("/events")`. The backend registers a listener against a data source to push new values. The user closes the tab after 20 seconds, yet the backend listener is never canceled. After 1,000 such visits, 1,000 listeners and queues may still remain unreleased. Subsequent symptoms include rising RAM, growing timer/task counts, heap retaining `SseEmitter`/`WebSocketSession` instances, lingering downstream connections, or repeated `Broken pipe` errors.

**Lesson topic:** when a client disconnects, how to detect the end of the connection, **unsubscribe/cancel** from the data source, and **clean up resources** thoroughly, effectively once, and safely when callbacks fire multiple times.

Core principles:

1. **A client TCP/HTTP disconnect does not mean the server knows immediately.** Not every framework receives an instant signal when the remote socket closes or the network drops.
2. **Stopping data sends does not automatically stop the data source.** An application-registered listener, timer, or manually created subscription can stay alive even after the response closes.
3. **Cleanup must run on every termination path:** normal completion, timeout, I/O error, client cancellation, server shutdown, and pipeline errors.
4. **Cleanup must be idempotent:** you may receive `onError` followed by `onCompletion`, or a timeout callback and a send task may touch the same session concurrently.
5. **Clear ownership:** close resources owned by **that single session/request**; never shut down a shared `WebClient` or connection pool just because one client disconnected.

Scope is **Spring Boot 3.3.x, Spring Framework 6.1.x, Java 17+**. The Spring MVC and WebFlux sample apps use Java 21. Certain disconnect-detection details depend on the server, HTTP protocol, container, proxy, and real network behavior, and must not be assumed to fire instantaneously.

## 2. Different Long-Lived Connection Types Have Different Lifecycles

| Communication Type | Data Direction | How Does the Server Know the Client Left? | Cleanup Points |
| --- | --- | --- | --- |
| SSE with Spring MVC `SseEmitter` | Primarily server → browser | Failure on write, servlet container async completion/error/timeout | `onCompletion`, `onTimeout`, `onError`, cancel timer/listener |
| WebFlux SSE `Flux<ServerSentEvent<?>>` | Server → browser | Transport detects disconnect and cancels subscription; or pipeline ends | `doFinally`, `using`, `usingWhen`, upstream cleanup |
| WebSocket | Bidirectional | Close frame, transport error/close, idle/heartbeat policy | Session callbacks or reactive termination |
| HTTP streaming/raw response | Server → client | `write`/flush error, reactive cancellation | `try/finally`, `try-with-resources`, `doFinally` |
| Long polling | Client waits for one response then completes | Request timeout/complete/cancel | Remove waiter from registry, stop timeout task |
| Broker/DB change stream subscription | Server ↔ upstream service | Auto-closes only if subscription/cancellation API is wired properly | `unsubscribe`, `Disposable.dispose`, `AutoCloseable.close` |

**Do not confuse SSE with WebSocket:** `EventSource` manages browser-side reconnection; WebSocket has a close protocol and bidirectional send/receive streams. **Do not confuse long polling with SSE:** long polling completes one response and the client typically issues a new request, whereas SSE keeps an HTTP response open to emit multiple events.

What actually needs cleanup depends on architecture. With `Flux.interval`, canceling upstream normally stops the scheduled subscription. With a Kafka listener, Redis Pub/Sub, JDBC polling, external socket, or app-managed session map, explicit cleanup is often required.

## 3. Lifecycle of a Session from Registration to Release

```text
Browser opens EventSource / WebSocket / streaming fetch
          |
          v
Server creates sessionId + registers active stream
          |
          +--> registers listener on broker/event source
          +--> creates heartbeat timer or scheduling task
          +--> holds a bounded queue/buffer if needed
          +--> response / WebSocket stays open
          |
          +----------- termination paths -------------
          | Client closes / tab unloads (may not arrive immediately)
          | I/O error during send
          | Server async timeout
          | User loses permission / token expires per policy
          | Event source completes or errors
          | Server shutdown/deployment
          v
CLOSE_ONCE / CANCEL_ONCE
          |
          +--> remove session from registry
          +--> unsubscribe data source / dispose subscription
          +--> cancel heartbeat/timer
          +--> release session-specific buffers / files / listeners
          +--> update active gauge + audit reason
          v
No resources belonging to that connection remain
```

A good design separates **the trigger event** from **the actual cleanup action**. Multiple callbacks may race to trigger cleanup, yet a session/object only needs its release side effects executed once. Using `AtomicBoolean.compareAndSet(false, true)` or atomic registry removal is a standard pattern.

**Do not assume you always receive an exact `CLIENT_DISCONNECTED` event.** In Servlet, you may only see an error on the next heartbeat write; in WebFlux, `SignalType.CANCEL` shows the downstream subscription was canceled, which does not by itself prove the browser closed the tab (it could also be a timeout operator, route cancellation, or application code).

## 4. Why Disconnects Are Not Always Detected Immediately

A connection from a browser to Spring Boot may pass through:

```text
Browser
  |
  v
CDN / reverse proxy / load balancer
  |
  v
Embedded Tomcat / Reactor Netty
  |
  v
Application and data sources
```

When a browser closes a tab, the client TCP socket may send FIN/RST; if network connectivity drops or NAT silently drops traffic, the server may receive no immediate notification. A reverse proxy sometimes keeps **a separate upstream connection** open even after the client closes. A TCP half-open connection can linger until a write, read, heartbeat, timeout, or network layer detects the failure.

Spring Framework documentation on **Spring MVC asynchronous requests** highlights a key point: **the Servlet API provides no direct notification when a remote client goes away**; for streaming, periodic writes are needed to detect write errors after disconnect. In SSE, that write can be a comment-only heartbeat that the client ignores. This is why a **completely silent** stream can hold resources far longer than expected.

In WebFlux/Reactive Streams, the server cancels the subscription once it detects transport closure; however, that timing still depends on **when the transport/proxy actually detects the disconnect**, not a deterministic timer in business logic.

Thus there are two parallel lines of defense:

- **Detection:** heartbeats, I/O errors, WebSocket close/ping-pong, async timeouts, socket idle/keepalive, and proxy timeouts.
- **Cleanup:** cleanup callbacks, cancellation propagation, resource ownership, registry eviction, shutdown hooks, and leak testing.

Merely raising timeouts or adding an `onCompletion` callback is not enough if nothing happens on the wire to let the container discover the dead connection.

## 5. SSE: `EventSource.close()` Only Closes the Browser Side

A simple JavaScript client:

```javascript
const source = new EventSource("/events");

source.addEventListener("tick", event => {
  console.log("tick", event.data);
});

source.onerror = () => {
  console.warn("SSE interrupted; browser may reconnect");
};

// Example when component unmounts or user explicitly leaves the view:
function stopWatching() {
  source.close();
}
```

`EventSource.close()` tells the browser to close the SSE connection and stops reconnection for **that EventSource instance**. It **does not directly invoke a Java `unsubscribe()` method on the server**. The backend only cleans up after HTTP transport/framework detects the response ended or failed.

In React/Vue/Angular components, call `close()` inside component/subscription cleanup rather than creating a new `EventSource` on every render. React example:

```jsx
import { useEffect } from "react";

export default function LivePanel() {
  useEffect(() => {
    const source = new EventSource("/events");
    const onTick = event => console.log(event.data);

    source.addEventListener("tick", onTick);

    return () => {
      source.removeEventListener("tick", onTick);
      source.close();
    };
  }, []);

  return <div>Live events</div>;
}
```

This is a **browser component snippet** requiring a React project; it is not Spring Boot Java code. When authenticating via cookies or tokens, implement appropriate auth/CORS/CSRF policies; never place secret tokens in the URL where they get logged or cached.

**Do not use `onerror` as proof the stream ended permanently.** Native `EventSource` reconnects automatically on network errors. The client must decide when reconnect is allowed and when to call `close()` per business logic.

## 6. Spring MVC and `SseEmitter`: Three Lifecycle Callbacks

Spring MVC supports returning `SseEmitter` to stream `text/event-stream`. Key callbacks:

| Callback/API | When Is It Invoked? | Recommended Action |
| --- | --- | --- |
| `onCompletion(Runnable)` | Async request completed; could be normal completion, timeout, or network error | Idempotently clean up resources/registry |
| `onTimeout(Runnable)` | Servlet async timeout occurred | Cancel work and clean up; do not assume status can still be changed |
| `onError(Consumer<Throwable>)` | Container reported an async request error | Clean up, log/record metric appropriately, do not return a new JSON error body |
| `send(...)` | Writes an event to the HTTP response | Catch `IOException` and stop this session's producer |
| `complete()` | Application intentionally completes stream normally | Call when business stream reaches intended end |
| `completeWithError(error)` | Application actively forwards an error to the framework | Do not call carelessly after `send` throws `IOException` |
| `SseEmitter(Long timeout)` | Timeout in **milliseconds** for the async stream | Pick per requirements; do not treat this timeout as client heartbeat |

**Special detail after I/O errors:** Spring Framework advises that when `SseEmitter.send(...)` throws `IOException` because the client left, the application **is not responsible for calling** `emitter.complete()` or `emitter.completeWithError()` in that error branch; the Servlet container fires an async error notification and Spring MVC completes the request. The application must still **stop its own work and unregister its listeners**. That is the distinction between **container cleanup** and **business resource cleanup**.

`onCompletion` is a solid hook for releasing resources, yet you should not rely on it alone without handling `IOException`, timeouts, and server shutdown. The callback may fire **later** than when the browser closed.

## 7. Complete Spring Boot MVC Example: SSE with Heartbeat and Idempotent Cleanup

This example uses **Spring Boot 3.3.13, Java 21, embedded Tomcat**, Gradle Wrapper, listening over HTTP on loopback for testing. Each SSE session gets a scheduled task, stopped on completion, timeout, error, or shutdown. This design **makes lifecycle behavior easy to observe**, though it is not optimal for tens of thousands of clients; large systems should use fan-out and bounded backpressure rather than one scheduled job per client.

**Source structure:**

```text
src/main/java/com/example/longconn/
  LongConnectionApplication.java
  StreamSchedulerConfig.java
  ManagedSseController.java
src/main/resources/
  application.properties
build.gradle
```

### 7.1. `build.gradle`

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
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
```

### 7.2. `src/main/java/com/example/longconn/LongConnectionApplication.java`

```java
package com.example.longconn;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class LongConnectionApplication {
    public static void main(String[] args) {
        SpringApplication.run(LongConnectionApplication.class, args);
    }
}
```

### 7.3. `src/main/java/com/example/longconn/StreamSchedulerConfig.java`

```java
package com.example.longconn;

import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class StreamSchedulerConfig {

    @Bean(destroyMethod = "shutdown")
    ScheduledExecutorService sseScheduler() {
        return Executors.newScheduledThreadPool(2);
    }
}
```

This is a **shared executor whose lifecycle is managed by Spring**; we cancel only a **single connection's** `ScheduledFuture` when the client closes, never calling `shutdown()` on the whole executor per disconnect. Spring shuts down the executor when the application context stops.

### 7.4. `src/main/java/com/example/longconn/ManagedSseController.java`

```java
package com.example.longconn;

import java.io.IOException;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;
import java.util.concurrent.atomic.AtomicReference;

import jakarta.annotation.PreDestroy;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

@RestController
public class ManagedSseController {

    private final ScheduledExecutorService scheduler;
    private final ConcurrentMap<UUID, StreamSession> sessions =
            new ConcurrentHashMap<>();
    private final AtomicInteger active = new AtomicInteger();

    public ManagedSseController(ScheduledExecutorService scheduler) {
        this.scheduler = scheduler;
    }

    @GetMapping(path = "/events", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public SseEmitter events() {
        UUID id = UUID.randomUUID();
        SseEmitter emitter = new SseEmitter(90_000L);
        StreamSession session = new StreamSession(id, emitter);
        sessions.put(id, session);
        active.incrementAndGet();

        // Multiple callbacks may fire; cleanup must be idempotent.
        emitter.onCompletion(session::close);
        emitter.onTimeout(session::close);
        emitter.onError(error -> session.close());

        ScheduledFuture<?> task = scheduler.scheduleAtFixedRate(
                () -> pushTick(session),
                0,
                10,
                TimeUnit.SECONDS);

        // Guard against race: close callback may run before assigning task.
        session.setTask(task);
        return emitter;
    }

    private void pushTick(StreamSession session) {
        if (session.closed.get()) {
            return;
        }
        try {
            long tick = session.sequence.incrementAndGet();
            session.emitter.send(SseEmitter.event()
                    .name("tick")
                    .id(session.id + ":" + tick)
                    .data("beat-" + tick));
        } catch (IOException disconnected) {
            // Spring MVC/container completes async I/O error.
            // Only stop the producer and clean up application resources.
            session.close();
        } catch (IllegalStateException alreadyClosed) {
            session.close();
        }
    }

    @GetMapping("/active-streams")
    public int activeStreams() {
        return active.get();
    }

    @PreDestroy
    public void shutdownStreams() {
        for (StreamSession session : sessions.values()) {
            session.close();
            session.emitter.complete();
        }
    }

    private final class StreamSession {
        final UUID id;
        final SseEmitter emitter;
        final AtomicLong sequence = new AtomicLong();
        final AtomicBoolean closed = new AtomicBoolean();
        final AtomicReference<ScheduledFuture<?>> task =
                new AtomicReference<>();

        StreamSession(UUID id, SseEmitter emitter) {
            this.id = id;
            this.emitter = emitter;
        }

        void setTask(ScheduledFuture<?> scheduled) {
            task.set(scheduled);
            if (closed.get()) {
                scheduled.cancel(false);
            }
        }

        void close() {
            if (closed.compareAndSet(false, true)) {
                ScheduledFuture<?> scheduled = task.get();
                if (scheduled != null) {
                    scheduled.cancel(false);
                }
                sessions.remove(id, this);
                active.decrementAndGet();
            }
        }
    }
}
```

**Explanation of key points:**

- `SseEmitter(90_000L)` sets a 90-second async timeout (in **ms**). This is a finite-session management example; if business requirements demand longer SSE lifetimes, configure appropriate timeouts and reconnection. Timeout is not the heartbeat interval.
- Each stream has a unique `UUID`; `sessions` enables tracking and shutdown cleanup. The registry retains no closed sessions as long as callbacks/heartbeats function properly.
- `onCompletion`, `onTimeout`, and `onError` all call the **same** `close()`, guarded by `AtomicBoolean.compareAndSet`. `active.decrementAndGet()` executes only once.
- The scheduled task sends `tick` every 10 seconds. If the client closes, the next write may throw `IOException`; the code cancels the producer immediately. **Do not call `completeWithError` in the `IOException` branch**, per Spring MVC guidance.
- `cancel(false)` does not forcibly interrupt an in-flight `send`; it prevents subsequent runs. Tasks and callbacks can race, so check `closed` and keep cleanup idempotent.
- `setTask()` checks `closed` right after storing `ScheduledFuture`, avoiding a rare race where a callback runs `close()` before `scheduleAtFixedRate` returns.
- The executor is a shared bean; the session only owns its future. The shutdown hook cancels remaining sessions when the application context stops.
- `/active-streams` is purely an observation endpoint for the demo—**do not expose session counts or user details publicly in production** without protection. Production should use restricted metrics gauges.

**Limitations:** To keep the example easy to learn, it schedules one task per client without authentication, quotas, or slow-client queues. In production, separate broker subscriptions, connection limit policies, per-user cleanup, and backpressure controls. If a single `send` blocks too long, `ScheduledExecutorService` threads can be tied up; do not use this demo for high-load benchmarking.

### 7.5. `src/main/resources/application.properties`

```properties
server.address=127.0.0.1
server.port=8080

# Default async limit for other endpoints; SSE explicitly sets 90s.
spring.mvc.async.request-timeout=90s
```

`server.address=127.0.0.1` restricts the demo to loopback only; this does not replace authentication/authorization in public deployments. `spring.mvc.async.request-timeout` applies to Servlet MVC async request processing, not browser or load balancer socket timeouts.

## 8. Running the SSE Demo and Intentionally Cutting the Connection

In the sample project with `gradlew` and Java 21:

```bash
./gradlew bootRun
```

In another terminal, open SSE using `curl`:

```bash
curl -N -i http://127.0.0.1:8080/events
```

Example streamed SSE lines (actual UUID/tick IDs will vary):

```text
id: 9e5c0...:1
event: tick
data: beat-1

id: 9e5c0...:2
event: tick
data: beat-2
```

This is an **illustrative format**, not byte-exact stdout, because UUIDs, tick timing, and HTTP headers vary. `curl -N` disables curl-side output buffering so you see events as they flush.

In a third terminal:

```bash
curl -s http://127.0.0.1:8080/active-streams
```

With one open client and no others, the expected body is:

```text
1
```

Press `Ctrl+C` to stop `curl -N`. The server **might not notice immediately**; after the next heartbeat/tick write or once the container detects network closure, `onError`/`onCompletion` and `session.close()` clean up the task. Once detected and cleaned up, `/active-streams` drops back to `0`.

**Do not promise it will drop to 0 in exactly 10 seconds** on every infrastructure: proxy buffering, half-open sockets, container behavior, scheduler jitter, and timeouts affect detection latency. Test through your system's actual ingress/proxy rather than localhost alone.

If the stream times out after 90 seconds, the session is also cleaned up. With native `EventSource`, the browser may reconnect automatically and create a new session. Thus total `active-streams` need not stay at 0 if the client keeps reconnecting—distinguish **old session removed** from **new session created**.

## 9. Why Cleanup Must Be Idempotent and Not Depend on One Callback

A single disconnect can trigger:

```text
send -> IOException
       |
       +--> application calls session.close()
       |
       +--> Servlet container raises async error
                  |
                  +--> onError -> close()
                  +--> onCompletion -> close()
```

Or:

```text
async timeout -> onTimeout -> close()
              -> onCompletion -> close()
```

If cleanup code does not guard state, each callback could decrement `active--` multiple times, attempt to unsubscribe the same listener twice, close connections out of order, or mistakenly remove a newer session sharing the same user key.

With `AtomicBoolean`, multiple callbacks can **all invoke** `close()`, yet only the winner of `compareAndSet(false,true)` runs the side effects. `ConcurrentMap.remove(id, this)` is likewise safer than `remove(id)` when the registry might be updated by a newer session.

**Note:** idempotence does not guarantee cleanup never throws. If `unsubscribe()` or `close()` throws an exception, define error handling, metrics, and occasional retry/reconciliation. When closing multiple resources, try to release **all** of them even if one step fails—for example using `try/finally` blocks or `closeQuietly` with controlled logging. Avoid holding locks long or performing blocking network I/O on container callback threads.

Standalone Java 17 example demonstrating close-once semantics:

**`CloseOnceDemo.java`**

```java
import java.util.concurrent.atomic.AtomicBoolean;

public class CloseOnceDemo {
    static class Subscription implements AutoCloseable {
        private final AtomicBoolean closed = new AtomicBoolean();

        @Override
        public void close() {
            if (closed.compareAndSet(false, true)) {
                System.out.println("released");
            }
        }
    }

    public static void main(String[] args) {
        try (Subscription subscription = new Subscription()) {
            System.out.println("active");
            subscription.close();
            subscription.close();
        }
    }
}
```

Compile and run:

```bash
javac CloseOnceDemo.java
java CloseOnceDemo
```

**Exact stdout:**

```text
active
released
```

In `try-with-resources`, `close()` is called again when exiting the block, yet the `released` side effect prints **only once**. This is the simplified model of unsubscribing when a session ends.

## 10. `onCompletion`/`onTimeout` Is Not an Exact "User Closed Tab" Signal

While `onCompletion` is useful, it can fire due to:

- Server actively calling `emitter.complete()`.
- Async request timeout.
- Exceptions during response handling or network I/O.
- Container/application shutdown.
- Client disconnect detected by transport.
- Business logic deciding the stream finished.

Therefore, do not always log `"user closed browser"` whenever `onCompletion` runs. Log the exact reason when **known** (`SERVER_COMPLETE`, `TIMEOUT`, `IO_FAILURE`); otherwise use `ASYNC_COMPLETE` or `UNKNOWN`. An `IOException` from `send` can be a disconnect, reset, proxy closure, or another network error; it does not prove user intent.

Similarly, `onTimeout` is the server's **async request/session** timeout, not a reliable indicator the client left. In production, metrics and logs should distinguish timeouts, cancellations, network write errors, and normal completions to avoid miscounting errors.

Once HTTP headers/body have been committed for streaming, the server usually **cannot turn an open response into a JSON 500 with another status code**. With SSE, you can send an application error event if the connection is still alive and policy allows, then complete. Once the socket has failed, do not keep trying to write error messages over the broken socket.

## 11. `ResponseBodyEmitter`, `StreamingResponseBody`, and `DeferredResult`

Three Spring MVC APIs have distinct cleanup models:

**`ResponseBodyEmitter` / `SseEmitter`:** pushes multiple chunks from another thread; requires callbacks to clean up event producers/listeners. SSE adds `text/event-stream` formatting.

**`StreamingResponseBody`:** writes directly to `OutputStream`, suited for streaming files/large byte payloads. Use **try-with-resources** for `InputStream`/file channels:

```java
@GetMapping("/download")
public StreamingResponseBody download() {
    return output -> {
        try (InputStream input = Files.newInputStream(
                Path.of("/srv/data/public/sample.bin"))) {

            byte[] buffer = new byte[64 * 1024];
            int n;
            while ((n = input.read(buffer)) != -1) {
                output.write(buffer, 0, n);
            }
            output.flush();
        }
    };
}
```

This is an **integration method snippet**, not standalone source: it needs imports for `InputStream`, `Files`, `Path`, `GetMapping`, `StreamingResponseBody`, an actual file, and proper security. When `output.write` throws `IOException` due to client disconnect, try-with-resources still closes the file. Do not catch the error and keep writing to a broken output stream. On Servlet stacks, write/flush can block; configure an appropriate `AsyncTaskExecutor` when using `StreamingResponseBody` under load.

**`DeferredResult<T>`:** waits for **one** asynchronous result, not a multi-event SSE stream. On timeout/completion, remove the waiter from the map/queue, cancel any scheduled timeout, and interrupt cancelable upstream work. Never leave a timed-out `DeferredResult` in a registry and call `setResult` on it later.

Cleanup logic example:

```java
DeferredResult<String> pending = new DeferredResult<>(30_000L);
pending.onCompletion(() -> waiters.remove(requestId));
pending.onTimeout(() -> waiters.remove(requestId));
```

This is an **integration snippet** requiring an actual `waiters` registry and `requestId`; reuse the same close-once helper if other timers/listeners exist. `setResult(...)` returns `false` if the request no longer accepts results under its contract; do not ignore the return value when the application needs to know if the result was accepted.

## 12. WebFlux: Client Disconnect Becomes Cancellation in Reactive Streams

With Spring WebFlux and Reactor Netty, a controller can return `Flux<ServerSentEvent<String>>`. The server subscribes to the `Flux` to emit the HTTP stream. When the response ends or the connection closes and the transport detects it, the downstream subscription sends a **cancel** signal upstream to the publisher.

```text
Browser HTTP SSE
     |
     v
Reactor Netty response writer [subscriber]
     |
     +--> cancel (when transport/user stops under actual runtime conditions)
     |
     v
Flux<ServerSentEvent<?>>
     |
     +--> doFinally(CANCEL)
     +--> upstream subscription dispose / resource cleanup
     |
     v
Source (interval / listener / broker / file I/O)
```

Reactor provides signals:

| `SignalType` | Meaning |
| --- | --- |
| `ON_COMPLETE` | Publisher completed normally |
| `ON_ERROR` | Publisher terminated with an error |
| `CANCEL` | Subscriber/upstream chain canceled because downstream no longer requests data |
| Other signals | Subscribe/request/next...; `doFinally` handles terminal paths |

`doFinally(signalType -> ...)` runs whenever a **subscription** terminates via complete, error, or cancel. It is well suited for metrics and cleanup side effects—**unlike** `doOnComplete` (skipped on cancel) and `doOnError` (skipped on complete/cancel).

`Flux.defer(...)` creates resources and increments counters **per subscription**, avoiding opening resources at the moment the controller constructs the `Flux` before anyone subscribes.

Do not rely solely on `doOnCancel` to clean up every resource if `ON_COMPLETE`/`ON_ERROR` paths also exist; use `doFinally` or dedicated resource-ownership operators.

## 13. Complete Spring Boot WebFlux Example: Self-Cleaning SSE Cancellation

This is **a separate project**, not mixed directly into the Spring MVC demo from section 7. Spring Boot can select the Servlet web application type if both `spring-boot-starter-web` and `spring-boot-starter-webflux` are present; to demonstrate WebFlux/Reactor Netty, use **only the WebFlux starter**.

### 13.1. `build.gradle`

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
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
```

### 13.2. `src/main/java/com/example/reactivestream/ReactiveStreamApplication.java`

```java
package com.example.reactivestream;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReactiveStreamApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReactiveStreamApplication.class, args);
    }
}
```

### 13.3. `src/main/java/com/example/reactivestream/ReactiveSseController.java`

```java
package com.example.reactivestream;

import java.time.Duration;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;

import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Flux;
import reactor.core.publisher.SignalType;

@RestController
public class ReactiveSseController {

    private final AtomicInteger active = new AtomicInteger();
    private final AtomicLong cancelled = new AtomicLong();

    @GetMapping(path = "/events", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public Flux<ServerSentEvent<String>> events() {
        return Flux.defer(() -> {
            String streamId = UUID.randomUUID().toString();
            active.incrementAndGet();

            return Flux.interval(Duration.ZERO, Duration.ofSeconds(5))
                    .map(n -> ServerSentEvent.<String>builder()
                            .event("tick")
                            .id(streamId + ":" + n)
                            .data("beat-" + n)
                            .build())
                    .doFinally(signal -> {
                        active.decrementAndGet();
                        if (signal == SignalType.CANCEL) {
                            cancelled.incrementAndGet();
                        }
                    });
        });
    }

    @GetMapping("/stream-metrics-demo")
    public Map<String, Long> metrics() {
        return Map.of(
                "active", (long) active.get(),
                "cancelled", cancelled.get());
    }
}
```

**Why does this example clean up cleanly?**

- `Flux.defer` executes each time a request **is subscribed to**; each request gets its own `streamId` and `active` increment per subscription.
- `Flux.interval` creates a periodic publisher. When downstream cancels, the upstream subscription is canceled and **that subscription's** periodic task is disposed; no separate `ScheduledFuture` management is needed in the controller.
- `doFinally` decrements `active` on complete/error/cancel. `cancelled` increments only on `SignalType.CANCEL`, avoiding labeling every termination as a browser disconnect.
- `ServerSentEvent` is serialized by Spring WebFlux into `text/event-stream`, with clear `id` and `event` names.
- Never call `subscribe()` manually inside the controller. **The framework is the HTTP response subscriber**, so cancellation propagates naturally upstream.

**Note:** The example has no external broker listener or DB connection. Those resources require `using`/`usingWhen` or explicit cleanup. `Flux.interval` here uses the shared Reactor scheduler; canceling one subscription's task **must not shut down the shared scheduler**.

### 13.4. `src/main/resources/application.properties`

```properties
server.address=127.0.0.1
server.port=8080
```

Run:

```bash
./gradlew bootRun
curl -N http://127.0.0.1:8080/events
```

In another terminal:

```bash
curl -s http://127.0.0.1:8080/stream-metrics-demo
```

While one stream is active, the JSON response **might** look like:

```json
{"active":1,"cancelled":0}
```

When you stop `curl` and the transport/server processes cancellation, `active` drops and `cancelled` typically increments. Exact timing and counts depend on connection state and concurrent requests. **Never claim clicking close in a browser triggers `CANCEL` synchronously on the exact millisecond.**

## 14. Testing Unsubscription with Reactor `StepVerifier`

Testing at the publisher layer verifies **cleanup on downstream cancel** without depending on TCP or proxies. Using the WebFlux project from section 13 with `reactor-test`:

**`src/test/java/com/example/reactivestream/ReactiveSseControllerTest.java`**

```java
package com.example.reactivestream;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.http.codec.ServerSentEvent;

import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

class ReactiveSseControllerTest {

    @Test
    void cancellationStopsStreamAndUpdatesCounters() {
        ReactiveSseController controller = new ReactiveSseController();

        Flux<ServerSentEvent<String>> flux = controller.events();

        StepVerifier.create(flux)
                .expectNextMatches(
                        item -> "beat-0".equals(item.data()))
                .thenCancel()
                .verify(Duration.ofSeconds(3));

        assertThat(controller.metrics().get("active")).isZero();
        assertThat(controller.metrics().get("cancelled")).isEqualTo(1L);
    }
}
```

Run:

```bash
./gradlew test
```

This is a **Reactor chain unit test**, not an integration test measuring how fast Servlet/Netty detects a TCP disconnect. `StepVerifier` explicitly emits **cancel** on the subscription and verifies `doFinally` ran and `active` returned to 0. For more complex asynchronous pipelines, use a latch/`Awaitility` to wait for cleanup instead of assuming callbacks finish at a deterministic instant.

To test end-to-end, use `@SpringBootTest(webEnvironment=RANDOM_PORT)` and a real `WebTestClient`/HTTP client subscribing to SSE, then cancel/dispose the client and **wait with a timeout** for server metrics to return to baseline. Never write assertions demanding "server must detect disconnect within 10 ms", as that depends on transport and scheduling.

## 15. Canceling One Subscription Does Not Cancel a Manual `subscribe()`

A dangerous anti-pattern in reactive code:

```java
// Wrong pattern: application manually subscribes to an infinite upstream.
Disposable upstream = brokerEvents.subscribe(event -> queue.offer(event));

// Controller returns a stream from queue; when client leaves, upstream keeps running
// unless something ties upstream's lifecycle to the HTTP subscription.
return queueFlux;
```

This is an **illustrative snippet**; `brokerEvents`, `queue`, and `queueFlux` would be defined separately. The flaw is that **the application-owned subscription** has a lifecycle decoupled from the HTTP response subscription. When the browser disconnects, Spring cancels `queueFlux` yet has no idea it needs to call `upstream.dispose()`.

A better design is to **chain the reactive stream directly** into the response:

```java
return brokerEvents
        .filter(this::isAuthorizedEvent)
        .map(this::toSse)
        .doFinally(signal -> recordTermination(signal));
```

This is an **integration snippet** with business-defined helpers. If `brokerEvents` obeys Reactive Streams and propagates cancellation upstream, `cancel` releases the broker subscriber. If the broker SDK requires an explicit `unsubscribe`, build an adapter that releases the resource on termination.

Whenever you must create a `Disposable` via manual `subscribe()`, **tie its `dispose()` call to the exact HTTP session's cleanup** and handle completion/errors too. Prefer building cold publishers or managed per-subscriber resources rather than starting a global hot subscription per request and forgetting its handle.

## 16. `using` and `usingWhen`: Owning Resources Across a Subscription

`doFinally` suits side effects (decrementing counters, metrics, logging). When a resource must be opened on subscribe and closed reliably on termination, Reactor provides:

- `Flux.using(resourceSupplier, resourceToPublisher, resourceCleanup)` for **synchronous** cleanup.
- `Flux.usingWhen(resourcePublisher, resourceClosure, asyncComplete, asyncError, asyncCancel)` for **asynchronous** cleanup.

**Integration pseudocode** against a hypothetical broker API:

```java
Flux<Event> liveEvents = Flux.using(
        () -> broker.openSubscription(topic),
        handle -> handle.events(),
        handle -> handle.close());
```

Here `broker`, `Event`, `handle.events()`, and `close()` are **application-defined interfaces**, not built-in Spring APIs. The design contract is that each subscriber opens exactly one handle and `Flux.using` invokes cleanup on complete, error, or cancel.

If closing the subscription requires an async network call:

```java
Flux<Event> liveEvents = Flux.usingWhen(
        broker.openSubscriptionAsync(topic),
        handle -> handle.events(),
        handle -> handle.closeAsync(),
        (handle, error) -> handle.closeAsync(),
        handle -> handle.closeAsync());
```

This is also pseudocode; `closeAsync()` must return a `Publisher` that completes after releasing the resource. The three-branch form lets you define cleanup for normal completion, error, and cancel. **Never return an empty `Mono<Void>` cleanup and assume the resource was closed.**

Key guidelines:

1. Clean up **per subscription**; never share a mutable resource across all clients and close it whenever any single client cancels.
2. Cleanup must be idempotent or guaranteed by the operator within its scope; the app still needs to handle races across other callbacks/lifecycles.
3. For blocking cleanup (JDBC close, filesystem sync, non-reactive SDKs), do not block the Reactor event loop. Offload to a suitable scheduler or migrate to a non-blocking client.
4. When cleanup can fail, define error reporting/metrics/retry policies; never assume swallowed cleanup errors are harmless.
5. `doFinally` placed on a shared hot publisher or after `share()` may reflect **only one layer's subscription**; inspect actual stream sharing and reference counts before closing upstream globally.

## 17. WebSocket: Close Frames, Transport Errors, and Registry Cleanup

Unlike SSE, WebSocket has a bidirectional protocol, a close handshake, and transport-level ping/pong. In the Spring Servlet WebSocket stack, `WebSocketHandler` exposes lifecycle methods:

| Method | Meaning |
| --- | --- |
| `afterConnectionEstablished(session)` | Handshake succeeded; WebSocket session established |
| `handleMessage(session, message)` | Message received |
| `handleTransportError(session, exception)` | Transport/session error occurred |
| `afterConnectionClosed(session, closeStatus)` | Connection closed; clean up registry/listeners |
| `session.close(status)` | Server initiates protocol close on session |

An MVC WebSocket skeleton illustrating **registry management**:

```java
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;

import org.springframework.web.socket.CloseStatus;
import org.springframework.web.socket.WebSocketSession;
import org.springframework.web.socket.handler.TextWebSocketHandler;

public class TrackingWebSocketHandler extends TextWebSocketHandler {
    private final ConcurrentMap<String, WebSocketSession> sessions =
            new ConcurrentHashMap<>();

    @Override
    public void afterConnectionEstablished(WebSocketSession session) {
        sessions.put(session.getId(), session);
    }

    @Override
    public void handleTransportError(
            WebSocketSession session, Throwable exception) {
        cleanup(session);
    }

    @Override
    public void afterConnectionClosed(
            WebSocketSession session, CloseStatus status) {
        cleanup(session);
    }

    private void cleanup(WebSocketSession session) {
        sessions.remove(session.getId(), session);
        // Unsubscribe / cancel per-session producer here if present.
    }
}
```

This is an **illustrative class snippet** needing WebSocket configuration/handler mapping and dependencies to become a working endpoint. `sessions.remove(key, session)` prevents removing a newer entry under concurrent updates. If a session errors while still open, product code needs a policy to close the session and free its producer—never merely remove from the map while the socket retains resources.

For WebSocket broadcasts, never send concurrently from multiple threads into a single `WebSocketSession` without ensuring session thread safety. Spring provides `ConcurrentWebSocketSessionDecorator` to serialize concurrent sends and enforce send/buffer limits on the Servlet stack; slow clients must be bounded or closed per policy.

Ping/pong and idle timeouts must align with proxies and load balancers, not only browser `onclose`. A silently dropped network link may only be caught after heartbeat/timeout expiration.

## 18. WebFlux WebSocket: Unifying Inbound and Outbound Lifecycles

In reactive WebFlux, a handler typically looks like:

```java
public Mono<Void> handle(WebSocketSession session) {
    Flux<WebSocketMessage> outgoing =
            Flux.interval(Duration.ofSeconds(1))
                    .map(n -> session.textMessage("tick-" + n));

    Mono<Void> sending = session.send(outgoing);
    Mono<Void> receiving = session.receive().then();

    return Mono.firstWithSignal(sending, receiving)
            .doFinally(signal -> recordSessionEnd(signal));
}
```

This is an **integration snippet** requiring `WebSocketHandler`, `WebSocketSession`, Reactor `Flux`/`Mono`, a `recordSessionEnd(...)` method, and a real `HandlerMapping`. `session.receive()` completes when the inbound stream closes; `session.send(outgoing)` is the outbound stream. With an infinite outbound stream in this example, `Mono.firstWithSignal(...)` finishes as soon as either side completes/errors and **cancels** the other side, preventing the sender from emitting forever after the inbound socket closes.

If you only write:

```java
return session.send(outgoing);
```

with an infinite outbound source, the handler may fail to observe **inbound termination** according to business intent; transport may still cancel when the real socket closes, yet composing the lifecycle explicitly clarifies "which branch closes the session".

Spring Framework WebFlux documentation describes `WebSocketSession.send(...)` and `receive()` as two streams that must be **composed into one unified lifecycle**. If an upstream broker subscription lives inside `outgoing`, ensure canceling the `Mono` cancels the broker source, or use `usingWhen` when the SDK requires async cleanup.

Never close the **shared Reactor Netty event loop** or application-wide scheduler when a single WebSocket session ends. Clean up only resources owned by that session.

## 19. Client-Side `WebClient`: Cancellation Must Also Release the Connection

Beyond server-side SSE, a Spring Boot application can **act as an HTTP client** subscribing to a stream from another service:

```java
Disposable subscription = webClient.get()
        .uri("/events")
        .retrieve()
        .bodyToFlux(String.class)
        .subscribe(this::consumeEvent);
```

This is an **integration snippet**: `webClient` and `consumeEvent` are app-defined. Calling `subscribe()` directly means you own managing the lifecycle. When the user stops watching or the service shuts down, you must call:

```java
subscription.dispose();
```

However, **do not** treat `dispose()` as a guarantee that the socket closes/returns to the pool in that exact millisecond, or that the upstream broker on the remote server canceled instantly. Reactor Netty handles cancellation once propagated down to transport; the remote server must also detect the drop and run its own cleanup.

Better yet, in many endpoints you can **return the Publisher directly** to the framework instead of calling `subscribe()` yourself:

```java
@GetMapping(path = "/proxy-events",
            produces = MediaType.TEXT_EVENT_STREAM_VALUE)
public Flux<String> relay() {
    return webClient.get()
            .uri("/events")
            .retrieve()
            .bodyToFlux(String.class);
}
```

This is a Spring WebFlux integration example requiring an injected `WebClient` with a configured base URL. When the upstream client chain is composed straight into the HTTP response, cancellation **propagates** from downstream to the `WebClient` exchange. If intermediate operators such as `cache`, `share`, `publish`, `replay`, or a separate hot subscription are introduced, semantics change; clearly identify who owns the upstream subscription.

**Never shut down the shared `WebClient` connection pool** after an individual request. Disposing a per-request subscription is completely different from shutting down shared Reactor Netty `ConnectionProvider`/HTTP resources.

## 20. `AbortController` with Streaming `fetch`: Client-Side Cancellation Responsibility

When the frontend uses streaming `fetch` instead of native `EventSource`:

```javascript
const controller = new AbortController();

async function watchStream() {
  const response = await fetch("/stream", {
    signal: controller.signal
  });

  if (!response.ok || !response.body) {
    throw new Error("Stream unavailable");
  }

  const reader = response.body.getReader();
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) {
        break;
      }
      console.log("received bytes", value.length);
    }
  } finally {
    reader.releaseLock();
  }
}

function stopWatching() {
  controller.abort();
}
```

This is browser JavaScript; a real frontend must invoke `watchStream()` and handle promise rejections. `AbortController.abort()` asks the client to cancel the HTTP request/stream. `reader.releaseLock()` releases the stream reader lock and **does not substitute** for `abort()` when actively terminating the network request.

Abandoning the read loop without aborting or canceling can leave the connection open. Once you know you will stop reading, call `reader.cancel()` per the Streams API and handle errors/cancellation cleanly. UI frameworks should tie cancellation to component unmount, navigation, and user session lifecycle.

As with SSE, the server may only detect closure once transport delivers the signal; aborting in the browser is not guaranteed to fire server callbacks instantaneously.

## 21. Client Cancellation vs. Timeout vs. Server-Initiated Close

| Trigger | What Client/Server Does | Cleanup Required? |
| --- | --- | --- |
| Client calls `EventSource.close()` | Browser closes SSE and stops reconnecting | Yes, once server learns stream ended |
| Client calls `AbortController.abort()` | Cancels HTTP fetch/stream | Yes |
| Client WebSocket `close(code, reason)` | Initiates WebSocket close handshake | Yes |
| Proxy idle timeout | Proxy closes or resets connection | Yes, once backend detects it |
| Spring MVC async timeout | Container invokes timeout lifecycle | Yes |
| Reactor `.timeout(Duration)` | Publisher emits timeout error and cancels upstream | Yes |
| Data source completes | Server proactively completes response | Yes |
| Authentication revoked | Application actively closes/cancels per policy | Yes |
| Server shutdown/redeploy | Stops accepting new sessions and drains/closes old ones | Yes |

Timeouts are **liveness** policies; user cancellation is a **change in data demand**; server shutdown is a **system lifecycle transition**. All of them must release resources, though reason codes and response/close behaviors differ.

Do not add `setTimeout(0)` or "infinite" timeouts merely to avoid disconnects when an environment gateway has a lower idle cutoff. Instead, align handshakes, heartbeats, lifetimes, and reconnects across client, proxy, and backend.

When the server intentionally ends an SSE stream, it can emit a **business `done` event** and complete the stream. Clients should not rely on receiving that final message if the network drops; build reconnect/idempotency logic per use case.

## 22. Heartbeats and Proxy Buffering: Misconfiguration Delays Cleanup

SSE can send a comment heartbeat formatted as:

```text
: heartbeat

```

The EventSource client ignores comment lines as application events, while the transport still sends bytes to verify liveness. With `SseEmitter`, create a comment event:

```java
emitter.send(SseEmitter.event().comment("heartbeat"));
```

Behind NGINX or another reverse proxy, inspect response buffering and timeouts. If the proxy holds bytes in a buffer rather than flushing downstream, heartbeats may not reach the browser on time; moreover, backend and proxy maintain separate connections.

**Conceptual** NGINX example for a specific SSE route:

```nginx
location /events {
    proxy_pass http://127.0.0.1:8080;
    proxy_buffering off;
    proxy_read_timeout 120s;
}
```

This is not a complete production configuration: routing, TLS, auth, upstreams, idle timeouts, header sanitization, and NGINX version checks are still needed. `proxy_read_timeout` typically measures **idle gaps between reads from upstream**, not total SSE lifetime. Set heartbeats **shorter than the smallest idle timeout** along the connection path, without making them so frequent they overload the server.

Some deployments emit the response header `X-Accel-Buffering: no` for NGINX, yet this is vendor-specific, does not replace proxy configuration, and is not honored by all CDNs.

**Heartbeats are not security keepalives**: enforce connection limits, authentication, per-user session quotas, and abuse protection. Never send heartbeats every few milliseconds for tens of thousands of users.

## 23. Slow Consumers and Backpressure: Clean Up Before Memory Grows Unbounded

Suppose a broker emits 10,000 events/second, while one browser can only read 100 events/second. If the application allocates an unbounded queue per client, memory climbs even while the socket remains "connected". Long before disconnecting, the server can run out of RAM or retain too many `DataBuffer` instances.

Options depending on business semantics:

| Strategy | Best For | Risks/Trade-offs |
| --- | --- | --- |
| Bounded queue per client | Absorbing small bursts with capped memory | Must define overflow behavior when full |
| Drop/latest/coalesce | Status dashboards needing only latest value | Intermediate events may be lost |
| Disconnect slow consumer | Protecting server from overly slow clients | Client must reconnect and resume |
| Batch/throttle | High-frequency updates that can be grouped | Increases latency and changes granularity |
| Replay from durable log + cursor | Meaningful events requiring reliability | Requires storage, offsets, and ordering |
| Upstream backpressure | Reactive sources honoring demand | Not all SDKs or brokers obey demand |

Reactor `onBackpressureLatest()` is an **intentional data-loss policy**, unsuitable for transactions/orders where every event must be delivered. For critical events, use a durable event log, per-client offsets, reconnect + resume, and rate limits rather than holding all events in RAM indefinitely.

When forced to disconnect an overly slow client, close its session cleanly and release upstream listeners/queues immediately. **Never let a listener keep pushing into a queue nobody reads.**

Browser SSE over HTTP/1.1 is also subject to per-origin connection limits in many clients/browsers. WebSocket/HTTP2 have different concurrency semantics. Do not equate TCP pool connection counts directly with active logical subscribers.

## 24. Buffer Ownership in WebFlux/Netty: Cancellation Can Leak Off-Heap Memory

In Spring WebFlux, `DataBuffer` can wrap a **reference-counted** Netty `ByteBuf`. When an application retains, transforms, or discards a buffer, it must respect ownership: `retain` only when genuinely extending lifetime, and `release` when done.

Example when a pipeline drops a `DataBuffer` inside an operator:

```java
Flux<DataBuffer> processed = source
        .filter(this::isWanted)
        .doOnDiscard(DataBuffer.class, DataBufferUtils::release);
```

This is an **integration snippet**; `source` and `isWanted` must be defined, and you must know which operator owns each buffer. `doOnDiscard` releases **buffers discarded** by operators that support discard hooks. Never `release` a buffer right after handing it to the response writer if the writer still needs to read bytes—doing so causes a use-after-release error.

Certain Spring APIs such as `DataBufferUtils.join` have contracts managing release on cancellation/error; never release a buffer **twice**. Read each API's documentation for ownership rules, especially with `DataBufferUtils.read(...)`, `response.writeWith(...)`, or custom codecs.

**Off-heap memory leaks** can occur even when Java heap usage barely grows. When investigating, check Netty leak detection, direct memory usage, pooled buffer metrics, and transformation/discard code per production needs rather than inspecting heap dumps alone.

## 25. Resource Cleanup by Ownership: Close Session Resources, Keep Shared Ones

| Resource | Typical Scope | Proper Cleanup |
| --- | --- | --- |
| `sessionId → emitter/session` entry | One connection | Atomic/idempotent entry removal |
| Broker listener registered for a browser | One connection | `unsubscribe()`/`close()` when session ends |
| `Disposable` from manual `subscribe()` | One subscription | `dispose()` |
| Heartbeat `ScheduledFuture` | One connection | `cancel(false)` or per interrupt policy |
| Shared `ScheduledExecutorService` bean | Whole application | Shut down on context stop, **not** per client |
| Shared `WebClient`/Reactor Netty resources | Whole application | Managed by application lifecycle |
| WebSocket session | One socket | Close frame / lifecycle callback then remove |
| File `InputStream` in streaming response | One request | `try-with-resources` |
| Opened JDBC connection/transaction | One operation | Release/rollback per transaction boundary |
| App-retained Netty `DataBuffer` | One buffer | Release per ownership contract |
| Per-client queue | One connection | Clear/close, bounded capacity |
| Metrics counters/gauges | Whole application | Update on session lifecycle, avoid raw user ID tags |

**Do not close a shared broker connection** when one client unsubscribes if the broker multiplexes many subscribers over that connection. Usually you call `subscription.unsubscribe()` for the single topic/subscriber while the shared client connection lives until service shutdown. Distinguish subscription handles from transport/client objects.

Conversely, **do not use `userId` as a unique map key** if a single user has multiple tabs/devices. If tab A closes and code deletes all listeners for `userId`, tab B loses data. Use a sufficiently unique `sessionId`/`subscriptionId` and map to the owner via a structured registry.

On user logout or permission revocation, policy may require closing all sessions for that user; that is an **intentional business action**, not to be confused with cleanup when one tab leaves.

## 26. SSE Auto-Reconnect: Unsubscribing the Old and Restoring New State

Native `EventSource` frequently reconnects after network failures, producing a sequence:

```text
session A is open
   -> client loses network
   -> server detects and cleans up A (possibly delayed)
   -> browser reconnects creating session B
   -> server registers B
```

There is a window where **A is not yet cleaned up while B has already been created**. If the registry is only `Map<userId, SseEmitter>` and overwrites A with B, A's delayed cleanup callback could call `remove(userId)` and **mistakenly delete B**. Use unique `sessionId` keys or `map.remove(userId, expectedSession)` where appropriate, and support multiple sessions per user.

SSE has an `id:` field and browsers can send `Last-Event-ID` on reconnect. These help resume **if** the server has a durable event source and replay policy. Still, `Last-Event-ID` **does not turn the system into exactly-once delivery**; handle duplicates, ordering, and idempotent consumers.

Cap sessions per user/tenant, use connection expiry and half-open cleanup, and prevent reconnect storms after restarts. Add jitter/backoff where controllable so thousands of browsers do not reconnect simultaneously when a gateway recovers.

If security requires disconnecting when a token expires mid-session, do not authenticate only at handshake and leave streams open forever. Define reconnect/re-auth/forced-close policies, and avoid logging tokens in SSE event IDs or URLs.

## 27. Long Polling: Removing Waiters from the Queue on Timeout/Cancel

With long polling, the client sends:

```http
GET /notifications/wait
```

The backend holds the request for up to, say, 25 seconds, then returns an event or an empty response. Events may come from a broker and the server often holds `Map<userId, List<DeferredResult<...>>>`.

If a request times out or the client leaves while the waiter remains in the map:

- The next event may try writing to an invalid `DeferredResult`.
- The registry grows over time.
- Reconnecting users accumulate stale waiters.
- Scheduled timeout tasks keep firing after the waiter already finished.

Management pattern:

```java
DeferredResult<ResponseEntity<?>> waiter =
        new DeferredResult<>(25_000L);

Runnable cleanup = () -> pendingWaiters.remove(waiterId, waiter);
waiter.onCompletion(cleanup);
waiter.onTimeout(cleanup);
waiter.onError(error -> cleanup.run());
```

This is **illustrative integration code**, needing imports, the `pendingWaiters` registry, `waiterId`, and actual result-setting logic. When an event arrives, check whether `setResult(...)` succeeded; remove the waiter upon completion. If a separate timer exists, cleanup must also cancel the timer and remove the broker listener.

`DeferredResult` returns a single result, rather than streaming multiple events in one HTTP response. When a client waits and aborts mid-poll, callback/container behavior also depends on the Servlet async lifecycle; do not expect immediate cleanup on the exact browser abort instant.

## 28. WebSocket Ping/Pong and Idle Timeouts

WebSocket supports `Ping`/`Pong` control frames and close handshakes. They verify liveness and free hung connections, yet only work effectively when properly configured across **the server implementation** and the actual network path. In browsers, the JavaScript WebSocket API **does not allow sending raw ping frames directly**; browsers answer protocol-level pings internally per implementation. Applications can send custom heartbeat messages if an application-layer signal is needed.

JavaScript client example:

```javascript
const socket = new WebSocket("wss://example.test/live");

socket.onmessage = event => console.log(event.data);
socket.onclose = event => console.log("closed", event.code);
socket.onerror = () => console.log("transport error");

function leavePage() {
  if (socket.readyState === WebSocket.OPEN) {
    socket.close(1000, "client leaving");
  }
}
```

This is a browser-side example with an illustrative hostname. `onclose` fires on both normal closes and certain error cases. `onerror` does not provide reliable detailed diagnostics for security or auditing. The server still needs `afterConnectionClosed`/reactive session termination and idempotent cleanup, even when the browser drops offline without sending a close frame.

When a proxy closes WebSockets after an idle timeout, align the ping interval, proxy/read idle timeout, server idle timeout, and reconnect policy. Never crank server timeouts to infinity to mask a missing liveness check.

## 29. Testing Errors, Timeouts, and Disconnects Without Relying on Luck

A solid testing strategy uses **two tiers**:

**A. Unit testing cancellation and cleanup logic:** Reactor `StepVerifier.thenCancel`, `AtomicBoolean`, `CountDownLatch`, and `CloseOnceDemo` verify single-execution side effects. For MVC, extract cleanup logic into a `StreamSession`/service testable standalone without a real browser.

**B. Integration testing over real HTTP sockets:** Start the server on a random port or staging endpoint; open SSE with an HTTP client, read the first event, then explicitly close the response/connection; wait **with a bounded timeout** for active streams, registry size, scheduled futures, and upstream listener counts to return to baseline.

Essential test cases:

| Scenario | What to Verify |
| --- | --- |
| Client reads 1 event then closes SSE | Old session's subscription/producer cancels once detected by server |
| Client closes right as server sends | No double cleanup, no negative counters |
| Async timeout | Timer/listener canceled; session leaves registry |
| Broker emits error | Server catches it and cleans up without leaking listeners |
| Multiple tabs for one user | Closing tab A does not drop session B |
| Very fast browser reconnect | Delayed cleanup for A does not delete entry B |
| WebSocket normal close | Registry and per-session queues cleaned up |
| WebSocket transport reset | Cleanup and metrics run on error path |
| Slow client | Queue bounds enforced, RAM does not grow unbounded |
| Normal stream completion | Active gauge returns to baseline |
| Redeploy/shutdown | Server stops accepting new connections and releases old subscriptions |
| Proxy buffering/idle timeout | Heartbeats and disconnect detection work via public route |
| Shared resource ownership | Closing one session does not shut down global executor/client pool |

**Never test by calling `Thread.sleep(10)` and asserting the server must already detect the disconnect.** Use latches/events, eventual assertions, and generous timeouts; measure liveness over real network paths.

During manual testing, you can run `curl -N` and press `Ctrl+C` to simulate a disconnect, while automation should use an HTTP client whose connection disposal the test controls. For end-to-end tests through a gateway, inspect both upstream and downstream connections; disconnecting the browser does not always close the proxy's upstream connection immediately.

## 30. Metrics and Logs: Distinguishing Normal Completion, Errors, and Cancellation

A helpful dashboard includes these metric groups:

```text
stream_active_connections{protocol="sse|websocket"}
stream_opened_total{protocol="sse|websocket"}
stream_ended_total{reason="complete|timeout|io_error|cancel|shutdown"}
stream_upstream_subscriptions{source="broker"}
stream_scheduler_tasks_active
stream_per_client_queue_bytes
stream_write_errors_total
stream_duration_seconds
```

These are **suggested metric names**, not claims that Micrometer/Actuator exports these exact names out of the box. In implementation, avoid high-cardinality tags like `sessionId`, `userId`, or dynamic URLs. Use trace/span IDs in controlled tracing/logs; keep metric tags to protocol, route, outcome, and stable business categories.

Session logs might look like:

```text
stream_opened streamId=... protocol=sse
stream_cleanup streamId=... reason=io_error
stream_closed streamId=... activeAfter=...
```

In production, log only what is necessary without leaking tokens, cookies, sensitive message payloads, or PII. Emit **a single cleanup event** after `closeOnce` succeeds instead of logging an error on every redundant callback.

Leak warning signals: `stream_opened_total` climbs while `stream_ended_total` lags after load stops; active connections fail to return to baseline; broker listener counts/queue sizes remain elevated after all clients exit; `ScheduledFuture` counts never drop; off-heap memory grows during byte streaming.

Monitor **legitimate active session counts** and typical real session durations to avoid false alarms when users intentionally leave streams open all day.

## 31. Security and Operations: Long Streams Need Explicit Boundaries

Long-lived connections retain resources for extended periods and affect authorization:

- **Authentication on open:** authenticate via appropriate cookies/tokens/TLS; never trust a query-supplied `userId` to pick data.
- **Continuous authorization:** when privileges are revoked, accounts locked, or tokens expire, policy may require closing streams or re-authenticating. Never treat a valid handshake as permanent permission.
- **Quotas/rate limits:** cap concurrent connections per verified user/tenant/IP to guard against reconnect storms and abuse.
- **Browser policies:** SSE with credentials/CORS requires careful configuration; WebSocket does not use CORS preflight like `fetch`, so enforce `Origin` validation and handshake authentication properly.
- **CSRF/session:** if WebSocket messages trigger side effects, enforce auth, authorization, anti-CSRF, or origin policies instead of trusting an open socket blindly.
- **TLS/proxy:** public traffic should use HTTPS/WSS; enforce proper termination and forwarded-header trust boundaries without exposing backend sockets directly.
- **Data privacy:** once a client disconnects, do not keep personal data sitting in per-client queues/caches beyond necessary retention.
- **Backpressure:** disconnected or slow clients must never consume unbounded memory or stall data sources for healthy clients.

In multi-replica clusters, session state is normally **instance-local**; when a node goes down, clients reconnect to another instance. Never design a local registry as durable storage; use a broker/durable log for events requiring replay.

## 32. Handling Server Shutdown and Graceful Termination

During redeploys, the server should stop accepting new connections and allow existing requests time to finish or close cleanly. **Long-lived streams may not finish naturally inside the grace period**, so define an explicit policy:

1. Mark the service as draining and reject new subscriptions or send business reconnect signals.
2. Proactively complete/close remaining open streams when the grace window ends.
3. Dispose broker listeners, future tasks, and per-session buffers.
4. Only afterward shut down shared executors and HTTP/broker clients.
5. Ensure ingress/load balancers stop routing new requests to the terminating instance.

Spring Boot has embedded server graceful shutdown, yet you must not assume it will **wait forever** for every WebSocket/SSE stream or clean up manually registered listeners on its own. Test startup/shutdown lifecycles for every server and connection type.

In the MVC sample from section 7, `@PreDestroy` calls `session.close()` and `emitter.complete()` for remaining sessions. The shared scheduler is stopped by bean lifecycle; production designs with multiple sources should enforce a clear shutdown order so unsubscribe calls do not run after a global broker client is destroyed.

When a pod is forcefully killed (`SIGKILL`) or a node crashes, no Java shutdown hook is guaranteed to run. External broker subscriptions and leases require **server-side timeouts/TTLs** or independent expiry mechanisms rather than relying solely on JVM cleanup.

## 33. Common Bugs and Diagnosing at the Right Layer

| Symptom | Primary Suspect | Resolution |
| --- | --- | --- |
| Browser closes tab yet active sessions stay high | Transport hasn't detected disconnect; no heartbeat | Write periodically; check proxy, timeouts, and container callbacks |
| `Broken pipe` appears while sending SSE | Client/proxy closed the HTTP connection | Stop producer and clean up; do not attempt to write a JSON error |
| `onCompletion` fires alongside other paths | Error/timeout/complete all reach cleanup | `closeOnce`, atomic removal |
| Emitter map grows continuously | Sessions not removed on completion | Clean up registry on every terminal path |
| WebFlux `doOnComplete` skipped after client cancel | Cancel differs from normal complete | Use `doFinally`/`doOnCancel`, handle `ON_ERROR` |
| Broker `Disposable` keeps running | Called `subscribe()` manually without lifecycle binding | `dispose` or `using`/compose Publisher |
| WebSocket closes yet sender keeps running | Handler failed to compose receive/send or leaked a timer | Bind outbound cancellation to session termination |
| Closing one tab disconnects other tabs | Registry keyed only by `userId`, deleting wrong entry | Key by `sessionId`/compare-and-remove |
| RAM grows with slow clients | Unbounded queue/buffer | Bound queues; apply backpressure/drop/replay policy |
| Netty direct memory grows | `DataBuffer` retained without release | Audit buffer ownership; enable leak detector |
| SSE drops consistently after 60 seconds | Proxy/read idle timeout or async timeout | Compare heartbeats and per-hop timeouts |
| Spring returns HTTP 500 after client leaves | Write error on already-committed response | Track cause/metrics; do not rewrite committed status |
| Browser reconnect creates duplicate sessions | Delayed cleanup on old session or missing max-session policy | Close old sessions, track ownership and TTL |
| Server shutdown hangs | Infinite streams never ending, shared resources waiting | Draining policy, close active sessions |
| Flaky tests | Assertions expecting instantaneous network disconnects | Eventual assertions, latches, controlled clients |
| `EventSource.close` called yet browser reconnects | App creates a new EventSource or buggy component lifecycle | Inspect frontend mount/reconnect logic |
| Long streams exhaust downstream pools | Streams hold downstream connections/resources too long | Isolate pools, enforce limits, close consumers |

A concise investigation workflow:

1. Trace **one `sessionId`** from open to cleanup.
2. Observe which callbacks/signals fire: I/O error, timeout, complete, reactive cancel, or WebSocket close.
3. Compare active session registries, heartbeat tasks, broker subscriptions, and pending queues **before and after** disconnect.
4. Inspect proxy buffering, idle timeouts, client reconnection, and browser/network behavior.
5. Check whether any upstream subscription was created via manual `subscribe()` without disposal.
6. Test races between disconnect, timeout, shutdown, and reconnect.

Never treat symptoms by merely increasing heap, expanding executor pools, or disabling timeouts: leaks will return as load grows.

## 34. Review Questions and Hands-On Exercises

1. Why does `EventSource.close()` not guarantee the server invokes `onCompletion()` immediately?
2. When Spring MVC `SseEmitter.send()` throws `IOException` due to client disconnect, how should the app clean up data sources, and why shouldn't it call `completeWithError()` in that branch?
3. Compare `onTimeout`, `onError`, and `onCompletion`: can they ever trigger cleanup for the **same** session?
4. Why is `AtomicBoolean.compareAndSet(false, true)` useful when multiple callbacks arrive?
5. How does `cancel(false)` on a `ScheduledFuture` differ from `shutdown()` on the whole shared executor?
6. How does reactive `doFinally(SignalType.CANCEL)` differ from `doOnComplete`?
7. If `Flux.interval` is returned directly to WebFlux, what happens to the scheduled task when downstream cancels?
8. If code calls `broker.subscribe(...).subscribe()` without keeping the `Disposable`, why doesn't an HTTP disconnect clean up upstream?
9. When do you need `Flux.using` versus `Flux.usingWhen`?
10. Why must reactive WebSocket unify `session.receive()` and `session.send()` under one termination policy?
11. How do you prevent session A's delayed callback from mistakenly deleting session B after a reconnect?
12. What does a comment-only SSE heartbeat help detect, and why can proxy buffering delay that signal?
13. When is dropping events with `onBackpressureLatest` unacceptable?
14. Why must a retained `DataBuffer` be released, and why can releasing immediately after handing it to the response writer be wrong?
15. Write a test using `StepVerifier.thenCancel` proving active subscriptions return to 0; how does it differ from an end-to-end TCP disconnect test?
16. If a node receives `SIGKILL`, which Java cleanup code may not run, and where are TTL/lease mechanisms needed?
17. Open two tabs for one user and close one tab; how do you prove the remaining tab still receives data?
18. Which metrics reveal that listeners, tasks, or queues are leaking even with zero connected browsers?

**Exercise 1:** Run the Spring MVC app, open two `curl -N` sessions, and query `/active-streams`; stop one session and observe the count drop to 1 once the server detects it, then stop the second. Test timeouts and restarts to verify no stale tasks remain.

**Exercise 2:** Run the WebFlux app and the Reactor test in section 14. Replace `doFinally` with `doOnComplete` and observe why cancellation no longer updates the counter as intended; then restore `doFinally`.

**Exercise 3:** Simulate a data source with an `AutoCloseable` handle and use `Flux.using` to tie handle ownership to each subscription. Cancel the subscription and verify `close()` runs only once. Add an error case to verify cleanup still executes.

**Exercise 4:** Place a buffering/idle-timeout proxy in front of SSE; vary the heartbeat interval in a test environment and measure how long it takes the server to detect disconnects. **Never** test connection exhaustion or DoS against production.

## 35. Conclusion: Closing the HTTP Response Is Not Enough if Auxiliary Resources Remain

**Chain of responsibility to remember:**

```text
Client no longer needs the stream
     -> transport/framework detects termination (possibly delayed)
     -> cancel/timeout/error/close signal
     -> idempotent session cleanup
     -> cancel broker listener / timer / upstream subscription
     -> remove registry/buffers, update metrics
     -> no impact on other sessions or shared resources
```

With **Spring MVC `SseEmitter`**, clean up via `onCompletion`, `onTimeout`, `onError`, and the `IOException` catch block of `send`, paired with heartbeats to detect departed clients; **do not call `completeWithError` after an I/O send failure**. With **WebFlux**, let cancellation propagate down the reactive chain, using `doFinally`, `Flux.using`, or `usingWhen` to release sources. With **WebSocket**, unify inbound/outbound lifecycles and perform close/error/idempotent registry removal.

A well-behaved stream does more than emit accurate events. It **stops consuming resources once receivers leave**, withstands slow clients, reconnects, network errors, timeouts, and redeploys, and never accidentally disrupts healthy connections.

### References

- Spring Framework 6.1 — Asynchronous Requests, HTTP Streaming, SSE, Disconnects, and Exception Handling: https://docs.spring.io/spring-framework/reference/6.1/web/webmvc/mvc-ann-async.html
- Spring Framework 6.1 — `SseEmitter` JavaDoc: https://docs.spring.io/spring-framework/docs/6.1.18/javadoc-api/org/springframework/web/servlet/mvc/method/annotation/SseEmitter.html
- Spring Framework 6.1 — `ResponseBodyEmitter` JavaDoc: https://docs.spring.io/spring-framework/docs/6.1.18/javadoc-api/org/springframework/web/servlet/mvc/method/annotation/ResponseBodyEmitter.html
- Spring Framework — WebFlux reactive core: https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html
- Spring Framework — WebFlux WebSocket handling: https://docs.spring.io/spring-framework/reference/web/webflux-websocket.html
- Project Reactor — Reference Guide, `doFinally`, `using`, and cancellation: https://projectreactor.io/docs/core/3.6.17/reference/
- Project Reactor — `Flux` API: https://projectreactor.io/docs/core/3.6.17/api/reactor/core/publisher/Flux.html
- Spring Framework — Data Buffers and Codecs: https://docs.spring.io/spring-framework/reference/core/databuffer-codec.html
- Spring Boot 3.3 — Servlet Web Applications and reactive web applications: https://docs.spring.io/spring-boot/3.3/reference/web/index.html
- MDN — EventSource `close()`: https://developer.mozilla.org/en-US/docs/Web/API/EventSource/close
- MDN — AbortController `abort()`: https://developer.mozilla.org/en-US/docs/Web/API/AbortController/abort
