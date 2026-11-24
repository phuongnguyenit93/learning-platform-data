# Servlet Async and the Difference Between Releasing the Request Thread and Non-Blocking I/O in Spring MVC

## 1. Practical problem: does a long-waiting request really have to hold a Servlet thread?

Imagine `GET /api/reports/42` needs 3 seconds to wait for a result from another service. In traditional synchronous MVC, a Servlet container thread receives the request, enters the controller, calls the service, and **waits** before writing the HTTP response. If many requests wait on I/O at the same time, the number of busy request threads increases, even though the CPU is not actually doing much computation.

Spring MVC supports **Servlet asynchronous request processing** (Servlet 3.0+) to return the **initial thread** to the container while the HTTP response **remains open**. The result is provided later via `Callable`, `DeferredResult`, `WebAsyncTask`, or a compatible return value type. Spring then performs an **ASYNC dispatch** and completes the response.

However, there is a very common misconception:

> **Releasing the Servlet request thread does not mean that all I/O in the application is non-blocking.**

If a controller returns a `Callable` that still makes synchronous JDBC calls inside, the **executor** thread will be blocked for the duration of the query. If writing a file using `StreamingResponseBody` with `OutputStream.write(...)`, the work has left the initial container thread, but the write call can still be **blocking**. The non-blocking I/O mechanism in Servlet 3.1 is a different layer, based on `ServletInputStream.isReady()`/`ReadListener` and `ServletOutputStream.isReady()`/`WriteListener`.

**Article scope:** Spring **Web MVC on the Servlet stack**, Java 17, Spring Boot 3.3.5 / Spring Framework 6.1.x; distinguishing **Servlet async**, **worker executors**, **non-blocking Servlet I/O**, and **Spring WebFlux**. The article explains the request lifecycle, return value types, timeout/cancellation, thread pool configuration, MockMvc testing, and system load limits.

### Learning outcomes

After this article, you can:

1. Describe synchronous requests and Servlet async per thread/dispatch.
2. Distinguish between "waiting without holding a Servlet thread" and "an operation without holding any thread while waiting".
3. Explain `Callable`, `DeferredResult`, `WebAsyncTask`, and their relationship to `CompletableFuture`.
4. Know when `ResponseBodyEmitter`, `SseEmitter`, and `StreamingResponseBody` release the request thread yet still perform blocking writes.
5. Distinguish the Servlet 3.0 asynchronous request lifecycle from Servlet 3.1 non-blocking I/O callbacks.
6. Configure a bounded `AsyncTaskExecutor` and timeout in Spring MVC; handle overload and context propagation.
7. Write integration-style controller and MockMvc async tests, observing the difference between `REQUEST` and `ASYNC dispatch`.
8. Decide when to stay on Spring MVC and when to consider WebFlux or truly non-blocking drivers/clients.

## 2. Four concepts to separate

| Concept | What does it solve? | Does it turn blocking JDBC/HTTP clients into non-blocking? |
| --- | --- | --- |
| **Servlet request thread** | Container thread currently processing filter/servlet/controller for a dispatch | No |
| **Servlet async lifecycle** | Allows the initial request thread to exit while the response remains open, then dispatches again later | No |
| **Async executor / worker pool** | Executes work on another thread, which may include blocking calls | No |
| **Non-blocking I/O** | I/O readiness/callback/async client; threads do not have to wait for a socket to be ready by blocking | Only when the entire API/driver/pipeline genuinely supports it |

Synchronous example:

```text
Servlet thread (http-nio-8080-exec-1)
  receives request -> filter -> controller
  -> blocking HTTP call / JDBC (waits 3 seconds)
  -> serialize JSON -> write response -> finish
  [thread is occupied for the entire wait time]
```

`Callable` example:

```text
Servlet thread (http-nio-8080-exec-1)
  receives request -> controller returns Callable
  -> request.startAsync()
  -> exits filter/servlet chain, returns thread to pool

MVC worker thread (mvc-work-1)
  runs Callable -> blocking JDBC/HTTP call (waits 3 seconds)
  -> creates Java result -> reports result

Servlet container thread (may be a different thread)
  handles ASYNC dispatch
  -> MVC serializes result -> writes HTTP response -> finish
```

In the second example, the **initial container thread is released**, but **mvc-work-1** is still blocked. Therefore, the main benefit is **separating container thread resources from long-running work** and controlling a dedicated pool/policy, not creating magic that turns the application into non-blocking I/O.

Example of `DeferredResult` waiting for a genuinely non-blocking external event/callback:

```text
Servlet thread -> returns DeferredResult -> startAsync -> exits
                        |
                        | request is pending, no result yet
                        | does not require a worker thread sleeping to wait
                        v
External callback/event loop receives result later
  -> deferredResult.setResult(value)
                        |
                        v
Servlet ASYNC dispatch -> writes HTTP response -> complete
```

If you implement DeferredResult with `new Thread(() -> Thread.sleep(...))` per request, you still consume a thread, just a different thread. **DeferredResult by itself does not make the producer non-blocking.**

## 3. From Servlet 3.0: startAsync(), AsyncContext, and ASYNC dispatch

Servlet 3.0 added asynchronous request processing. At the Servlet API layer, the idea is:

```java
AsyncContext asyncContext = request.startAsync();
// Can register a listener, timeout, or trigger work outside this thread.
// When the result is ready: asyncContext.dispatch() or asyncContext.complete().
```

This is a **Servlet-level snippet**; `request` is an `HttpServletRequest` in an async-enabled Servlet, importing `jakarta.servlet.AsyncContext`. Do not place this directly inside an MVC method that already returns `Callable`/`DeferredResult` and try to control the lifecycle in parallel: **Spring MVC manages startAsync/dispatch/complete for you**.

### 3.1. Asynchronous request lifecycle in Spring MVC

Suppose an endpoint returns `DeferredResult`:

1. The container receives an HTTP request and assigns a Servlet thread.
2. DispatcherServlet runs handler mapping, binding, interceptors, and the controller.
3. The controller creates a `DeferredResult` and **returns early**, without a response body yet.
4. MVC invokes the Servlet `request.startAsync()` mechanism and exits the filter/servlet chain.
5. The initial request container thread returns to the pool; the response **has not been committed/closed**.
6. Another thread/callback completes `DeferredResult.setResult(value)` or `setErrorResult(...)`.
7. MVC requests an **ASYNC dispatch** to the Servlet container.
8. DispatcherServlet is invoked again in the new dispatch; it uses the already available **concurrent result**, **without calling the business controller method again from the start** to produce the result a second time.
9. MVC applies return-value handling/message converters and writes the response; async processing completes.
10. Timeouts, client disconnects, exceptions, and async listeners can intervene in this flow.

```text
HTTP Request
    |
    v
REQUEST dispatch (Servlet thread #1)
    |
    v
Spring MVC controller -> DeferredResult / Callable
    |
    v
Servlet startAsync(); request thread #1 released
    |
    +--------------------- waiting --------------------+
    |                                                  |
    |           producer event / worker result          |
    |                      arrives                     |
    +--------------------------+-----------------------+
                               |
                               v
                  DeferredResult.setResult(...)
                               |
                               v
ASYNC dispatch (Servlet thread #2, may equal #1)
                               |
                               v
           Spring MVC return-value handling + response
                               |
                               v
                       Request complete
```

**Do not assume the second dispatch uses the same thread**: the container is free to use a different thread. Similarly, `@RequestScope`, MDC, SecurityContext, transaction-bound state, and custom `ThreadLocal`s **do not automatically propagate** across every worker/dispatch; see section 12.

### 3.2. Where must Servlet async be enabled?

For the mechanism to work, the corresponding Servlet/filter chain must support asynchronous processing:

- The Servlet needs `asyncSupported=true`.
- Filters on the processing path must not block async and need appropriate dispatcher mappings (`jakarta.servlet.DispatcherType.ASYNC`) when they must execute on async redispatch.
- With Spring Boot's embedded Servlet container and common Spring MVC auto-configuration, many declarations are pre-configured appropriately.
- If registering filters/servlets manually, use `FilterRegistrationBean.setAsyncSupported(true)` or the corresponding Servlet 3.x registration according to your architecture.
- When a filter needs to run again on the `ASYNC` dispatch, ensure the mapping includes this dispatch type; however, do not simply run all filter logic twice without considering semantics.

A commonly seen error:

```text
java.lang.IllegalStateException:
Async support must be enabled on a servlet and for all filters involved...
```

The exact message depends on the container/framework. It is usually related to a filter or servlet not supporting async, not because the `Callable` return type is wrong.

### 3.3. Why does ASYNC dispatch matter?

Spring MVC does not simply take a value from an external thread and write it directly as if it were still on the initial request. Redispatching allows reusing the MVC pipeline to handle the body, status, converters, and error handling according to a unified lifecycle.

Lifecycle callbacks in `HandlerInterceptor` need to understand async: `afterConcurrentHandlingStarted(...)` of `AsyncHandlerInterceptor` runs when the request transitions to async; `postHandle`/`afterCompletion` in the initial dispatch do not always occur in the same order as a sync request. On the subsequent dispatch, MVC processing continues and completion is invoked according to the lifecycle. If using timing/trace interceptors, guard against duplicate logging and improper cleanup.

## 4. What async return value types does Spring MVC have?

### 4.1. Callable<T>: offloading work to the MVC async executor

```java
@GetMapping("/price")
public Callable<ResponseEntity<PriceDto>> price() {
    return () -> {
        PriceDto dto = blockingPriceService.loadPrice();
        return ResponseEntity.ok(dto);
    };
}
```

This is a **snippet** assuming `PriceDto` and `blockingPriceService` already exist; it is not a standalone runnable controller. When the controller returns Callable, MVC starts Servlet async, then submits the Callable to `AsyncTaskExecutor`. Inside the Callable, blocking operations still **occupy a worker thread**. When the Callable returns a result, Spring redispatches and completes.

**Suitable when:**
- You have long-running or blocking business logic that needs to be separated from Servlet threads.
- You want to use a dedicated executor with a configured queue/pool size.
- A single result is returned, not an infinite stream.

**Not suitable for claiming "no waiting threads"** if the Callable calls `Thread.sleep`, blocking JDBC, blocking file I/O, or a sync REST client.

### 4.2. DeferredResult<T>: completing from an external event

```java
@GetMapping("/status")
public DeferredResult<ResponseEntity<StatusDto>> status() {
    DeferredResult<ResponseEntity<StatusDto>> result =
            new DeferredResult<>(5000L);

    queue.registerListener(event -> {
        result.setResult(ResponseEntity.ok(new StatusDto(event.state())));
    });

    result.onTimeout(() ->
            result.setErrorResult(
                ResponseEntity.status(503).build()));

    result.onCompletion(() -> queue.unregisterListener(result));
    return result;
}
```

This is **snippet-style Java pseudocode** because `queue`, `StatusDto`, and the event API are undeclared, and `unregisterListener` in a real system must use the appropriate registration token/listener. The point is that the result can come from a message broker callback, a non-blocking HTTP client callback, or an event stream, **without creating a sleeping waiting thread per request**.

- `setResult(T)`: provides the result for MVC to redispatch.
- `setErrorResult(Object)`: provides an exception or error result for MVC to handle.
- `onTimeout(Runnable)`: handles when the container signals the async wait time has expired.
- `onError(Consumer<Throwable>)`: reacts to async errors.
- `onCompletion(Runnable)`: releases resources/registrations after the request ends.

**Lifecycle note:** `setResult` may fail/have no effect if a result has already been set by timeout/error; do not wait until the HTTP response closes and then keep sending. When using a queue/listener, clean up on completion/cancel/timeout to avoid memory leaks.

### 4.3. WebAsyncTask<T>: Callable with per-endpoint configuration

`WebAsyncTask` is a wrapper around Callable that allows specifying timeout, executor, and callbacks for an endpoint:

```java
@GetMapping("/report")
public WebAsyncTask<ResponseEntity<String>> report() {
    WebAsyncTask<ResponseEntity<String>> task =
        new WebAsyncTask<>(3000L,
            () -> ResponseEntity.ok("ready"));

    task.onTimeout(() ->
        ResponseEntity.status(503).body("timed out"));
    return task;
}
```

This snippet can be placed in a `@RestController` with imports `GetMapping`, `ResponseEntity`, `WebAsyncTask`. The timeout `3000L` is in milliseconds. `WebAsyncTask` **does not automatically turn a Callable into non-blocking I/O**; the work still runs on an executor.

### 4.4. CompletionStage/CompletableFuture

Spring MVC can accept single-value async return types such as `CompletionStage`/`CompletableFuture` via return-value adaptation:

```java
@GetMapping("/remote")
public CompletableFuture<ResponseEntity<String>> remote() {
    return service.fetchAsync()
            .thenApply(ResponseEntity::ok);
}
```

This is a snippet because `service.fetchAsync()` is undeclared. The benefit depends on the implementation of `fetchAsync()`:

- If it uses a genuinely async HTTP client, network wait time may not occupy a dedicated worker thread.
- If it uses `CompletableFuture.supplyAsync(() -> blockingService.call())`, a worker thread is blocked in `call()`.
- If `supplyAsync` is used without specifying an executor, by default it may use the common ForkJoinPool — **you should not assume that is a suitable thread pool for blocking production work**.

Do not judge non-blocking behavior based solely on a `CompletableFuture` signature.

### 4.5. StreamingResponseBody, ResponseBodyEmitter, and SseEmitter

| Type | What is it used for? | Does it guarantee non-blocking socket I/O? |
| --- | --- | --- |
| `StreamingResponseBody` | Writes raw bytes incrementally to `OutputStream`, e.g., large downloads | **No.** MVC uses a thread to execute the task; `write` can block |
| `ResponseBodyEmitter` | Sends multiple objects/response chunks over time via converters | **Not guaranteed.** Writing the Servlet response can block |
| `SseEmitter` | Server-Sent Events (`text/event-stream`) over a long-lived HTTP connection | Does not turn the transport/write pipeline into fully non-blocking |
| `Callable` | A single result produced in an executor | Worker can block |
| `DeferredResult` | A single result completed by a producer/event | Depends on the producer; may not need a waiting thread |

For SSE, you need heartbeats, timeouts, client disconnect handling, subscription cleanup, and a concurrent connection limit policy. An open connection still consumes socket descriptors, buffers, server state, and other resources even though the initial Servlet thread has been released.

## 5. Servlet 3.1: true non-blocking I/O is a different layer

Servlet **3.0 asynchronous request lifecycle** releases the request thread while waiting for a result. Servlet **3.1 non-blocking I/O** adds APIs to read/write when the stream is ready, instead of blocking a thread on socket I/O:

- `ServletInputStream.isReady()` / `isFinished()` / `setReadListener(ReadListener)`.
- `ServletOutputStream.isReady()` / `setWriteListener(WriteListener)`.
- `ReadListener.onDataAvailable()`, `onAllDataRead()`, `onError(...)`.
- `WriteListener.onWritePossible()` and `onError(...)`.

### 5.1. Blocking I/O

With a standard OutputStream:

```java
// Snippet in a Servlet/synchronous code path.
OutputStream out = response.getOutputStream();
out.write(bigChunk); // Can BLOCK until buffer/network capacity is sufficient.
```

When a client reads very slowly or the network buffer is full, `write` can block the calling thread. Moving this code into a `StreamingResponseBody` worker **does not change the blocking nature** of `write`.

### 5.2. Non-blocking output readiness

With the Servlet 3.1 API, the correct model is:

```text
request enters Servlet with async support
  -> startAsync()
  -> getOutputStream().setWriteListener(...)
  -> callback onWritePossible()
       while (output.isReady() && bytes remaining):
           write the portion that can be written
       if output is not ready: EXIT callback, do not busy-spin
  -> container invokes onWritePossible() again when ready
  -> when writing finishes: asyncContext.complete()
```

Snippet illustrating the calls:

```java
ServletOutputStream output = response.getOutputStream();

output.setWriteListener(new WriteListener() {
    @Override
    public void onWritePossible() throws IOException {
        while (output.isReady() && hasPendingBytes()) {
            writeNextChunk(output);
        }
        if (allBytesWritten()) {
            asyncContext.complete();
        }
    }

    @Override
    public void onError(Throwable error) {
        handleFailure(error);
        asyncContext.complete();
    }
});
```

This is **illustrative pseudocode**: `hasPendingBytes`, `writeNextChunk`, `allBytesWritten`, `handleFailure`, and `asyncContext` must be implemented and synchronized yourself; it is not a ready-to-run class. Avoid calling `complete()` multiple times, handle errors/partial writes, and avoid blocking inside callbacks. Input similarly uses `ReadListener` and a `while(input.isReady() && !input.isFinished())` loop.

**Important condition:** callbacks must respect readiness, not invoke I/O against the contract, and not try to spin when `isReady()==false`. Non-blocking I/O here solves threads being blocked by **network stream readiness**, but application callbacks can still block if you make blocking JDBC calls inside them.

### 5.3. Comparing the mechanisms in one sentence each

- `request.startAsync()`: "I am leaving the current Servlet thread, keeping the HTTP exchange alive, and will resume later."
- `ServletOutputStream.setWriteListener(...)`: "Call me when the output socket can accept writes; I do not need a thread waiting for buffer space."
- `Callable`: "Run this logic on a worker, often still synchronous/blocking inside."
- `DeferredResult`: "I will supply the result when an external producer signals completion; no dedicated waiting worker is needed if the producer is event-driven."
- `WebFlux + non-blocking client/driver`: "The whole pipeline can follow readiness/signals and backpressure instead of using a waiting thread per blocking operation", **provided blocking calls are not embedded onto the event loop**.

Do not equate an **asynchronous API** with a **non-blocking implementation**.

## 6. Comparing the models by thread consumption

Suppose there are 100 concurrent HTTP requests, each waiting 2 seconds for a remote service. This is a **thought experiment**, not a benchmark or throughput measurement.

| Approach | Initial request Servlet thread | While waiting for remote |
| --- | --- | --- |
| Sync controller + blocking client | Holds thread until completion | **Servlet thread** waits |
| Controller returns Callable + blocking client | Released early | **Executor worker thread** waits |
| DeferredResult + executor running blocking client | Released early | **App worker thread** waits |
| DeferredResult + event-driven non-blocking HTTP client | Released early | No per-request waiting worker needed; event-loop/runtime threads still exist |
| Servlet 3.1 WriteListener | Released when socket output is not ready | Container callbacks when writable, if code follows the contract |
| Spring WebFlux + end-to-end reactive I/O | Different model, typically event-driven | Fewer threads for many waiting connections, if dependencies do not block |

**Do not conclude** "100 async requests = 0 threads". Even when waiting has no dedicated thread, the server still needs threads to process callbacks, CPU work, serialization, dispatching, GC, and the network stack; it also needs memory for every pending request, sockets, and timeout state.

If a JDBC driver only provides a blocking API, using WebFlux or CompletableFuture does not automatically turn JDBC into non-blocking. You can offload the blocking call to a bounded scheduler/executor, but that is still **moving where the thread blocks**, not a non-blocking driver.

## 7. Complete demo: Java 17 + Spring Boot 3.3.5 + Spring MVC async

The demo has four endpoints:

- `GET /api/async/sync`: returns a synchronous result; the thread is a Servlet container thread.
- `GET /api/async/callable`: returns a `Callable` and records the `mvc-work-*` worker thread name.
- `GET /api/async/deferred`: returns a `DeferredResult`; the producer runs in the `producer-*` thread pool and completes via callback.
- `GET /api/async/web-task`: uses `WebAsyncTask` to attach a timeout to a Callable.

**Note:** The demo does not wait on a real remote service and does not intentionally call `Thread.sleep`. The goal is to verify **lifecycle/executor behavior**, not to prove latency or throughput under load. The demo's DeferredResult still has a producer worker to generate data; it is **not** an example of an end-to-end non-blocking producer.

### 7.1. Project structure

```text
servlet-async-demo/
├── pom.xml
└── src/
    ├── main/java/example/asyncmvc/
    │   ├── AsyncMvcApplication.java
    │   ├── AsyncMvcConfig.java
    │   └── AsyncDemoController.java
    └── test/java/example/asyncmvc/
        └── AsyncDemoControllerTest.java
```

**`pom.xml`:**

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
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>servlet-async-demo</artifactId>
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

The project only needs the web starter for MVC, Jackson, and the embedded Servlet container; plus starter-test to run MockMvc/JUnit. No WebFlux, no Reactor, and no reactive libraries are needed to use Servlet async.

**`src/main/java/example/asyncmvc/AsyncMvcApplication.java`:**

```java
package example.asyncmvc;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class AsyncMvcApplication {
    public static void main(String[] args) {
        SpringApplication.run(AsyncMvcApplication.class, args);
    }
}
```

### 7.2. Registering a bounded executor and timeout

For `Callable`, Spring MVC has an `AsyncTaskExecutor`. Without configuring an appropriate pool, MVC's default executor is not a production choice under load. Configuration:

**`src/main/java/example/asyncmvc/AsyncMvcConfig.java`:**

```java
package example.asyncmvc;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.web.servlet.config.annotation.AsyncSupportConfigurer;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class AsyncMvcConfig implements WebMvcConfigurer {

    @Bean("mvcAsyncExecutor")
    public ThreadPoolTaskExecutor mvcAsyncExecutor() {
        ThreadPoolTaskExecutor pool = new ThreadPoolTaskExecutor();
        pool.setCorePoolSize(4);
        pool.setMaxPoolSize(8);
        pool.setQueueCapacity(32);
        pool.setThreadNamePrefix("mvc-work-");
        pool.setWaitForTasksToCompleteOnShutdown(true);
        pool.setAwaitTerminationSeconds(5);
        return pool;
    }

    @Bean("producerExecutor")
    public ThreadPoolTaskExecutor producerExecutor() {
        ThreadPoolTaskExecutor pool = new ThreadPoolTaskExecutor();
        pool.setCorePoolSize(2);
        pool.setMaxPoolSize(4);
        pool.setQueueCapacity(16);
        pool.setThreadNamePrefix("producer-");
        pool.setWaitForTasksToCompleteOnShutdown(true);
        pool.setAwaitTerminationSeconds(5);
        return pool;
    }

    @Override
    public void configureAsyncSupport(AsyncSupportConfigurer configurer) {
        configurer.setTaskExecutor(mvcAsyncExecutor());
        configurer.setDefaultTimeout(5000L);
    }
}
```

Explanation:

- `mvcAsyncExecutor` runs `Callable`/`WebAsyncTask` and serves as the MVC async executor. `setDefaultTimeout(5000L)` applies by default when the return type does not override it.
- `producerExecutor` illustrates an **application-managed executor** used to complete `DeferredResult`. `DeferredResult` does not necessarily run on the `mvcAsyncExecutor` pool — where the producer lives is the application's decision.
- `corePoolSize`, `maxPoolSize`, and `queueCapacity` set meaningful bounds. When both pool and queue are full, tasks can be rejected. **Do not create an unbounded pool or infinite queue just because you want requests to be "async".**
- `threadNamePrefix` helps identify threads in logs and tests. Thread names are not an API contract for production clients, only an illustration tool.
- Spring manages the lifecycle of `ThreadPoolTaskExecutor` beans, including initialization and shutdown.
- Calling `mvcAsyncExecutor()` from a `@Configuration` class proxied by Spring with default `proxyBeanMethods=true` retrieves the same singleton bean; it does not create a new thread pool per request.

**Important note on capacity:** When a pool has a bounded queue, `maxPoolSize` is typically only used after the queue reaches its limit (depending on executor behavior). If jobs run for a long time, the queue can increase request latency; you need to measure **active threads, queued tasks, rejected tasks, request timeouts, and p95/p99 latency** instead of just increasing pool size.

### 7.3. Controller: sync, Callable, DeferredResult, WebAsyncTask

**`src/main/java/example/asyncmvc/AsyncDemoController.java`:**

```java
package example.asyncmvc;

import java.util.concurrent.Callable;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.context.request.async.DeferredResult;
import org.springframework.web.context.request.async.WebAsyncTask;

@RestController
@RequestMapping("/api/async")
public class AsyncDemoController {

    public record Reply(String mode, String thread) {}

    private final ThreadPoolTaskExecutor producerExecutor;

    public AsyncDemoController(
            @Qualifier("producerExecutor")
            ThreadPoolTaskExecutor producerExecutor) {
        this.producerExecutor = producerExecutor;
    }

    @GetMapping("/sync")
    public ResponseEntity<Reply> synchronous() {
        return ResponseEntity.ok(
                new Reply("sync", Thread.currentThread().getName()));
    }

    @GetMapping("/callable")
    public Callable<ResponseEntity<Reply>> callable() {
        return () -> ResponseEntity.ok(
                new Reply("callable", Thread.currentThread().getName()));
    }

    @GetMapping("/deferred")
    public DeferredResult<ResponseEntity<Reply>> deferred() {
        DeferredResult<ResponseEntity<Reply>> result =
                new DeferredResult<>(4000L);

        result.onTimeout(() -> result.setErrorResult(
                ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
                        .body(new Reply("timeout", "none"))));

        result.onError(error -> result.setErrorResult(
                ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR)
                        .body(new Reply("error", "none"))));

        try {
            producerExecutor.execute(() -> {
                Reply reply = new Reply(
                        "deferred", Thread.currentThread().getName());
                result.setResult(ResponseEntity.ok(reply));
            });
        } catch (RuntimeException rejected) {
            // Demo: when the pool rejects work, return a controlled error.
            result.setErrorResult(
                    ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
                            .body(new Reply("overloaded", "none")));
        }

        return result;
    }

    @GetMapping("/web-task")
    public WebAsyncTask<ResponseEntity<Reply>> webTask() {
        WebAsyncTask<ResponseEntity<Reply>> task =
                new WebAsyncTask<>(3000L, () ->
                        ResponseEntity.ok(new Reply(
                                "web-task",
                                Thread.currentThread().getName())));

        task.onTimeout(() ->
                ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
                        .body(new Reply("timeout", "none")));

        return task;
    }
}
```

**Why is this code well-suited for learning Servlet async?**

1. `synchronous()` executes on the Servlet request thread; it returns the body in the same dispatch.
2. `callable()` returns a closure; Spring starts async and executes the closure on the `mvc-work-*` pool; the response is completed in an ASYNC dispatch.
3. `deferred()` returns **an application-controlled promise**. Work is submitted to `producerExecutor`; upon completion it calls `setResult` so MVC redispatches. If this producer were replaced with a real non-blocking I/O callback, there would be no need for a waiting thread per HTTP call.
4. `webTask()` demonstrates a per-request 3s timeout with a Callable. `WebAsyncTask` is suitable when an endpoint needs a custom timeout callback.
5. `onTimeout` and `onError` return specific response statuses via `setErrorResult`. They cannot guarantee modifying the response if it has already been partially committed or if the client socket has closed.
6. `ThreadPoolTaskExecutor.execute(...)` can reject tasks on overload; the demo catches RuntimeException on submission to avoid pending forever. In a real system, catch the **specific rejection policy exception** and avoid masking other programming errors; this example is intentionally minimal.
7. The `producer-*` name in the JSON indicates the **producer thread**, not the Servlet thread that writes the final response.
8. There is no `Thread.sleep`, network request, or database call, so the example only verifies the lifecycle rather than proving performance.
9. A timed-out `DeferredResult` may reject late results; production code must check the return value of `setResult` if cleanup/metrics are needed.
10. `request.startAsync()` is not called directly: Spring MVC manages the lifecycle automatically when returning an async type.

**Note on timeouts:** `DeferredResult(4000L)` and `WebAsyncTask(3000L)` use timeouts in milliseconds; in Servlet async, the timeout starts after the initial request thread exits and the request enters the waiting state. Real runtimes may have shorter proxy/ingress timeouts; do not treat a server-side timeout as a millisecond-exact deadline across the entire network.

### 7.4. Running the demo

From the `servlet-async-demo` directory containing `pom.xml`:

```bash
mvn test
mvn spring-boot:run
```

These are **two sequential commands**. Install JDK 17+ and Maven. With Boot defaults, the application runs at `http://localhost:8080`.

Requests:

```bash
curl -i 'http://localhost:8080/api/async/sync'
curl -i 'http://localhost:8080/api/async/callable'
curl -i 'http://localhost:8080/api/async/deferred'
curl -i 'http://localhost:8080/api/async/web-task'
```

Example response bodies look like:

```json
{"mode":"sync","thread":"http-nio-8080-exec-1"}
```

```json
{"mode":"callable","thread":"mvc-work-1"}
```

```json
{"mode":"deferred","thread":"producer-1"}
```

```json
{"mode":"web-task","thread":"mvc-work-2"}
```

**These are illustrative outputs**, without guaranteeing exact thread names/suffix numbers. Thread numbers, creation order, and pool reuse depend on the runtime/concurrency. For normal successful requests, the expected status is `200 OK`. The `thread` field in the response body is only proof that work ran on a different pool type, not proof that all socket/network operations are non-blocking.

## 8. MockMvc: testing asyncStarted and asyncDispatch

If a test only calls `mvc.perform(get("/api/async/callable")).andExpect(status().isOk())` on the first dispatch, the result may not be ready yet because the request is async. MockMvc provides:

- `request().asyncStarted()`: confirms the controller transitioned to asynchronous handling.
- `MvcResult` from the initial request: holds the request/response to continue.
- `asyncDispatch(mvcResult)`: simulates the subsequent Servlet ASYNC dispatch once the result is ready.
- `jsonPath`/`status`: asserts the response **after** dispatch.

**`src/test/java/example/asyncmvc/AsyncDemoControllerTest.java`:**

```java
package example.asyncmvc;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.hamcrest.Matchers.startsWith;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.asyncDispatch;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.request;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class AsyncDemoControllerTest {

    @Autowired
    MockMvc mvc;

    @Test
    void synchronousResponseIsImmediate() throws Exception {
        mvc.perform(get("/api/async/sync"))
           .andExpect(status().isOk())
           .andExpect(jsonPath("$.mode").value("sync"));
    }

    @Test
    void callableStartsAsyncAndRunsOnMvcExecutor()
            throws Exception {
        MvcResult pending = mvc.perform(get("/api/async/callable"))
                .andExpect(request().asyncStarted())
                .andReturn();

        mvc.perform(asyncDispatch(pending))
           .andExpect(status().isOk())
           .andExpect(jsonPath("$.mode").value("callable"))
           .andExpect(jsonPath("$.thread").value(
                   startsWith("mvc-work-")));
    }

    @Test
    void deferredResultUsesProducerExecutor()
            throws Exception {
        MvcResult pending = mvc.perform(get("/api/async/deferred"))
                .andExpect(request().asyncStarted())
                .andReturn();

        mvc.perform(asyncDispatch(pending))
           .andExpect(status().isOk())
           .andExpect(jsonPath("$.mode").value("deferred"))
           .andExpect(jsonPath("$.thread").value(
                   startsWith("producer-")));
    }

    @Test
    void webAsyncTaskUsesMvcExecutor()
            throws Exception {
        MvcResult pending = mvc.perform(get("/api/async/web-task"))
                .andExpect(request().asyncStarted())
                .andReturn();

        mvc.perform(asyncDispatch(pending))
           .andExpect(status().isOk())
           .andExpect(jsonPath("$.mode").value("web-task"))
           .andExpect(jsonPath("$.thread").value(
                   startsWith("mvc-work-")));
    }
}
```

Run:

```bash
mvn test
```

The test suite has **4 test methods**. When passing, Maven exits with code `0` and typically prints the summary `Tests run: 4, Failures: 0, Errors: 0, Skipped: 0`. This example tests the return-value lifecycle with MockMvc; it is not a latency measurement or a real socket I/O readiness check. It is not claimed that Maven was executed while authoring this document.

### Why not assert first thread == thread after redispatch?

Spring/the container may use different threads for the initial request, task executor, and redispatch. Thread names in the demo response are recorded when the business reply is created, **not proving** which thread writes the HTTP response. Therefore, the tests only check prefixes matching the producer/Callable executor, without requiring thread IDs to be equal.

### How to test timeouts?

To test real timeout callbacks, MockMvc alone may not trigger identically to container network timeouts. You can use `MockAsyncContext` or integration tests via embedded Tomcat with a producer controlled by a `CountDownLatch`/fake service, rather than using `Thread.sleep(10000)` in unit tests and assuming timeouts will be reliable.

A reliable test should actively control when the producer completes versus times out, verifying status/error bodies according to application policy. You must check whether work continues running after an HTTP timeout and whether it gets cancelled. `DeferredResult.onTimeout` does not automatically call `Future.cancel(true)` on tasks you submit.

## 9. Timeouts, errors, and client disconnects

Async requests that leave responses pending should have a **timeout policy**, both in MVC and at proxies/networks. Otherwise, connections open too long can accumulate state and sockets.

### 9.1. Timeout does not mean cancellation

When a request times out:

1. The container may signal an async timeout.
2. Spring MVC/interceptors/`DeferredResult.onTimeout` get a chance to produce an error result.
3. MVC attempts to redispatch to write the error response, if the HTTP response has not committed and the client is still connected.
4. **A running blocking service/worker task is not necessarily stopped.** You must have deadline and cancellation policies at the producer/driver.

If a `Callable` calls a sync REST client with a 60-second timeout while MVC timeout is 3 seconds, the client request may receive 503 after 3 seconds while the worker keeps running/waiting up to the 60-second timeout. With enough tasks, the pool still drains even though container threads are idle.

**Practical rule:** request deadlines must propagate to downstream I/O: connection/read timeouts, database statement timeouts, client cancellation, messaging subscription cleanup, and queue cancellation. Do not just set `configureAsyncSupport.setDefaultTimeout(...)` and consider load management done.

### 9.2. Exception propagation

- With a `Callable` throwing an exception, Spring MVC can handle the error result via exception resolvers/`@ControllerAdvice` during redispatch.
- With `DeferredResult`, use `setErrorResult(exception)` or an appropriate error result; Spring MVC redispatches and handles it according to return type/exception.
- If the response has already been partially written (streaming) or the client disconnected, you cannot reliably change the HTTP status/body anymore. Logs/metrics must distinguish business errors from broken pipe/timeout/client abort.
- Do not expose stack traces, database errors, or credentials in error responses. Use stable error codes and a request correlation ID.

### 9.3. Error callbacks and cleanup

`DeferredResult` provides:
- `onTimeout(...)` to return a fallback/error.
- `onError(...)` to react to exceptions.
- `onCompletion(...)` to clean up subscriptions, pending listener registrations, slots in a long-polling map, and timer/correlation context.

Avoid races between producer completion and timeout. `setResult(...)` returns a boolean indicating whether the result was set; only the first successful callback is used. Use `AtomicBoolean`/a state machine when cleanup from multiple sources may run concurrently.

A `DeferredResult` stored in a `ConcurrentHashMap` waiting for an event must be removed on completion/timeout to avoid memory leaks if the client leaves or the producer never emits an event.

## 10. Why @Async does not mean HTTP Servlet async

Spring `@Async` typically marks a bean method to run on another task executor and returns `Future`/`CompletableFuture` or `void`. It is **method invocation async**, not the Servlet request lifecycle itself:

```java
@Async
public CompletableFuture<String> loadReport() {
    return CompletableFuture.completedFuture(
            blockingRepository.loadReport());
}
```

This is a snippet with a hypothetical `blockingRepository`; even though it returns CompletableFuture, calling `blockingRepository.loadReport()` still blocks the thread that the `@Async` method runs on. For a controller to release the initial request thread, the MVC return type must be handled as an async return value, or the controller chooses `DeferredResult`/`Callable`. A method calling itself on the same bean (**self-invocation**) can bypass the `@Async` proxy, so do not assume the annotation always switches threads.

**Do not** spawn a new raw thread per HTTP request:

```java
// ANTI-PATTERN: do not spawn unbounded threads per request.
new Thread(() -> doBlockingWork()).start();
```

Under heavy load, unbounded concurrency causes OOM, context switching, and shutdown difficulties. Use bounded executors, queue policies, service-level timeouts, and capacity planning.

## 11. StreamingResponseBody: streaming does not mean non-blocking

Example returning bytes via `StreamingResponseBody`:

```java
@GetMapping("/download")
public StreamingResponseBody download() {
    return outputStream -> {
        try (InputStream input = fileService.openInputStream()) {
            input.transferTo(outputStream);
        }
    };
}
```

This is a **snippet**: `fileService` is undeclared, controller/response headers are incomplete, and imports for `StreamingResponseBody` and `InputStream` are needed. It allows writing the response **from a task executor after the initial Servlet thread is returned**. However, `InputStream.transferTo(OutputStream)` uses a read/write loop that is typically **blocking**; if the client is slow, the worker can stall waiting on output. Spring MVC recommends configuring an appropriate async executor when using streaming.

### ResponseBodyEmitter and SSE

`ResponseBodyEmitter` can send multiple objects with `send(...)`/`complete()`. `SseEmitter` supports SSE events. Each request can live a long time without holding the initial Servlet thread, but:

- Each client still occupies a connection, memory/state, and can use a worker while sending.
- Blocking writes or queue buildup can occur if the client is slow.
- SSE is typically unidirectional server → client; if bidirectional is desired, consider WebSocket.
- Set timeouts, heartbeats, limits, cleanup, and a client reconnect policy.
- If subscribing to a broker, cancel the subscription when the emitter completes/errors/times out.

**Backpressure:** Servlet MVC emitters do not automatically create an end-to-end backpressure solution between broker, application queue, and browser. If the producer is faster than the consumer, you need buffer bounds, drop policies, producer pacing, or an appropriate protocol; do not send infinitely just because the initial thread left the request.

## 12. ThreadLocal, SecurityContext, MDC, and transactions in async

One of the hardest bugs to spot is assuming "it is still the same HTTP request" so all context from the initial thread still exists on the worker.

### 12.1. MDC/trace

Logging MDC typically uses `ThreadLocal`. A `Callable` running on `mvc-work-*` does not necessarily carry the `traceId`/`tenantId` that a Servlet filter attached to the initial container thread. Without context propagation, logs from the producer lose correlation or record leftover values from a previous task.

A `TaskDecorator` can capture/apply MDC when submitting a task, but must **restore/clear** it in a finally block. When integrating tracing/OpenTelemetry, use official integrations/context propagation instead of blindly copying arbitrary ThreadLocals.

### 12.2. SecurityContext

Spring Security provides integration mechanisms for Servlet async in certain `Callable` paths, but **you must not assume every executor/CompletableFuture/DeferredResult callback inherits the principal automatically**. For custom producer executors, consider `DelegatingSecurityContextAsyncTaskExecutor` or an explicit immutable user context; pass only the minimal required data.

Do not store the entire request or a mutable security context in a long-lived queue and process it after the session has expired without verifying policy. Authorization must be enforced at the appropriate endpoints and downstream services.

### 12.3. Transaction

`@Transactional` typically binds a transaction to the thread running the method. A transaction on the controller's initial thread **does not automatically continue** inside a callable worker, deferred producer, or asynchronous dispatch. If a DB transaction is needed for work, open the transaction **inside the service method** called on the worker. Do not try to hold a JDBC transaction open for several minutes while waiting for an event.

### 12.4. Locale and request-scoped data

`LocaleContextHolder`/`RequestContextHolder` have their own lifecycles; Spring has some integration for Callable but does not guarantee every application-specific callback receives the request context. When an async producer needs locale, timezone, or tenant, pass those values **explicitly** (as immutables) into the job/callback. Do not assume a request-scoped bean remains valid after the request completes.

## 13. Throughput, thread pools, and real performance

### 13.1. What can releasing the Servlet thread actually help with?

If 200 concurrent requests are waiting on remote events, `DeferredResult` allows initial Servlet threads to return to the pool early so the container can accept other requests. At the same time, there are still:

- 200 pending HTTP responses/connections.
- 200 async state objects.
- Timeout registrations, callbacks, and possible buffered data.
- Event producers/subscriptions or background tasks.
- A brief Servlet thread when the result is ready to redispatch and serialize the response.

If using `Callable` with blocking work, 200 requests can overflow a worker pool of 8 threads + queue 32; the remaining 160 requests may be rejected/delayed. That is **necessary backpressure/overload protection**, not a bug to "fix" by spawning 200 unbounded threads.

### 13.2. Little's Law and waiting limits

A performance intuition: the number of waiting requests is roughly `arrival rate × average time in system` when measured on a relatively stable system. If 100 requests/second take 2 seconds, there can be around 200 requests in flight; async does not eliminate the 200 pending connections, it only changes how threads are held.

When building a capacity plan, measure:
- Active/queued/rejected tasks on the executor.
- Current async requests, completions/timeouts/cancellations.
- Container threads busy and idle.
- HTTP client connection pool limits, DB pool saturation.
- CPU/GC, heap bytes for response buffers and upload/download state.
- p50/p95/p99 latency and error rates.
- Client disconnects and ingress/reverse proxy timeouts.

Do not say "async is always faster than sync". For very short CPU-bound tasks, executor handoff + redispatch adds overhead and can be slower. For blocking operations, releasing Servlet threads helps isolation/availability, but does not lower total wait time if downstream remains slow.

### 13.3. Request deadlines and circuit breakers

When calling a slow downstream service:
1. Set connection/read/request timeouts on the HTTP client/DB.
2. Bound concurrent calls and queues.
3. Use cancellation/deadline propagation where supported.
4. Apply fallbacks/circuit breakers/rate limits per business requirements.
5. Do not retry infinitely in workers; retry storms can further congest downstream.
6. Return proper HTTP statuses (`503` when temporarily overloaded, `504` at a gateway if appropriate) with a correlation ID and safe logging.

Setting a timeout only in Servlet MVC without setting client/DB timeouts is an **incomplete design**.

## 14. Spring MVC async vs. Spring WebFlux

| Aspect | Spring MVC Servlet async | Spring WebFlux |
| --- | --- | --- |
| Primary abstraction | MVC controllers, Servlet request/response | Reactive streams/publishers and reactive HTTP processing |
| Releases initial thread | Yes, with Callable/DeferredResult/etc. | Reactive event-driven request lifecycle |
| Return types | Callable, DeferredResult, WebAsyncTask, CompletionStage, emitters | Mono, Flux, and reactive types |
| Server I/O | Servlet container, has Servlet 3.1 non-blocking APIs though MVC response writes are often blocking | Designed for non-blocking streaming I/O via supported runtimes/adapters |
| Blocking JDBC/JPA | Still blocking if used | Still blocking if called from the event loop; must offload or switch drivers |
| Backpressure | Must be designed separately for emitters/producer queues | Reactive Streams support demand/signals, though each boundary must be checked |
| Testing | MockMvc + asyncDispatch | WebTestClient + reactive test utilities |
| Migration | Incremental async addition on existing MVC | Changes programming model/stack and potentially clients/drivers |
| Best suited for | Leveraging Spring MVC, blocking libraries, traffic needing Servlet thread isolation | End-to-end async pipelines, streaming/high concurrency with non-blocking dependencies |

There is no one-size-fits-all choice. For MVC apps already using blocking Hibernate ORM/JPA/JDBC, `Callable` or `DeferredResult` + a bounded worker can be an incremental solution. If the main bottleneck is concurrent connection count and the entire data path has non-blocking network/DB clients, WebFlux can reduce thread consumption. However, if you put `block()`/blocking JDBC on the event loop, the benefits vanish and throughput can suffer.

**WebFlux does not equal Netty in every deployment**; it can run on other runtime adapters. Distinguish the **programming model** (reactive), the **server runtime** (Servlet/Netty), and the **actual I/O libraries**.

## 15. Common pitfalls when applying Servlet async

| Symptom | Possible cause | How to fix |
| --- | --- | --- |
| `IllegalStateException` reporting async unsupported | Servlet/filter chain lacks `asyncSupported` or dispatcher mapping is missing | Check Servlet/filter registrations and ASYNC dispatch |
| Threads still exhausted when using Callable | Blocking work moved from container to worker pool | Bound executor, add downstream timeouts, measure worker utilization |
| DeferredResult times out even though producer finished | Race condition, queue too long, result set after timeout | Check `setResult` boolean, queue latency, and deadlines |
| HTTP response ends but task keeps running | MVC timeout does not auto-cancel downstream work | Propagate cancellation/deadlines, clean up producer/connections |
| Default `AsyncTaskExecutor` fails under load | No suitable pool/queue configured | `WebMvcConfigurer.configureAsyncSupport` with a bounded executor |
| Request is not async despite `@Async` method | `@Async` only changes where the method runs; controller return value is not async | Return an appropriate Callable/DeferredResult/CompletionStage |
| MDC/traceId disappears in worker | ThreadLocal does not propagate automatically | TaskDecorator/context propagation, clear in finally |
| SecurityContext missing in producer | Using custom executor outside security integration | Explicit context or delegating executor, verify ACLs |
| Lazy-loading/transaction exception | Transaction was only opened on the initial thread | Open service transaction inside worker, DTO boundaries |
| `StreamingResponseBody` slow with slow clients | `OutputStream.write` blocks in worker | Appropriate pool, flow control, native non-blocking APIs if needed |
| SSE causes steady memory growth | Emitter/subscription not cleaned up, slow clients | Bounds, callbacks, heartbeats, cancellation |
| MockMvc test fails because response is missing | `asyncDispatch` was not called | `request().asyncStarted()` then `asyncDispatch(result)` |
| Controller appears called "twice" in logs | Confusing ASYNC redispatch/filters/interceptors with controller return value | Log DispatcherType and lifecycle; do not duplicate business actions |
| Proxy times out before Spring MVC | Ingress idle timeout lower than MVC timeout | Align end-to-end timeouts, configure keepalive per policy |
| CPU spikes after switching to async | Executor dispatch overhead, oversubscription, retry storms | Benchmark with realistic load, tune bounded concurrency |
| Non-blocking WriteListener loops continuously | Not exiting when `isReady()==false` | Write only when ready; wait for the next callback |
| Synchronous file/DB reads attempted on event loop | Blocking I/O still blocks the reactive thread | Use non-blocking drivers or offload to a bounded scheduler |

Concrete debugging checklist:

1. Observe `DispatcherType.REQUEST` and `DispatcherType.ASYNC` with the same correlation ID.
2. Check the controller return type; is it returning Callable/DeferredResult or a sync DTO?
3. Inspect `asyncSupported`/ASYNC dispatcher mappings for the Servlet and filters.
4. Measure thread names of producers/workers and the container, not just total thread count.
5. Measure downstream wait time, MVC timeout, proxy timeout, and queue wait separately.
6. With `DeferredResult`, check whether completion happened via `setResult` or error/timeout, and clean up listeners.
7. With streaming, measure time spent inside `write` and consumer speed.
8. Verify MDC/SecurityContext/LocaleContext/transaction boundaries across each executor.
9. Use MockMvc `asyncDispatch`, then add live HTTP server tests when verifying disconnects/network/proxies.
10. If the goal is end-to-end non-blocking, inspect **every I/O API** (HTTP, DB, filesystem, response write), not just the return type.

## 16. Choosing the technique by workload type

| Scenario | Suitable direction |
| --- | --- |
| Controller calls slow blocking JDBC DB, wants to protect Servlet thread pool | Callable/WebAsyncTask + bounded executor, DB timeout |
| Must wait on event/message broker callback without a dedicated waiting thread | DeferredResult + event subscription/callback and cleanup |
| HTTP client returns CompletableFuture from genuinely async I/O | Controller returns CompletableFuture/CompletionStage or adapts via DeferredResult |
| 20 ms CPU-bound report generation | Usually sync or suitable worker based on benchmarks; async is not automatically faster |
| Multi-minute report generation | Job queue + `202 Accepted` + polling/webhook, do not hold HTTP connections indefinitely |
| Returning large files via StreamingResponseBody | MVC async executor and controlled blocking writes |
| Thousands of SSE clients receiving continuous updates | Consider WebFlux/non-blocking pipelines, bounds, and heartbeats |
| Need low-level non-blocking Servlet streams | Servlet 3.1 `ReadListener`/`WriteListener` adhering to readiness contract |
| End-to-end reactive network + data-store | WebFlux and non-blocking clients/drivers, avoid blocking on the event loop |
| Need support for existing Servlet filters, JSP, blocking Spring MVC ecosystem | Stay on MVC, apply async only where it genuinely helps |

An endpoint with an overly long wait time probably should **not** hold an HTTP connection open. For report tasks taking several minutes, an API where `POST /reports` returns `202 Accepted` with a job ID and the client polls `GET /reports/{id}/status` or receives a webhook is an option that handles retries, scaling, and timeouts much more reliably. Servlet async fits requests with moderate wait times and clear policies, not replacing message queues/job orchestration.

## 17. Self-check exercises

1. Why can `Callable` release a Servlet request thread yet still **block** a worker thread?
2. Does `DeferredResult` spawn its own thread and perform I/O by itself?
3. In the MVC async lifecycle, does the request complete on the initial `REQUEST` dispatch or is there an `ASYNC` redispatch?
4. How do `request.startAsync()` (Servlet 3.0) and `ServletOutputStream.setWriteListener()` (Servlet 3.1) differ in responsibility?
5. Does setting `MVC timeout=3s` automatically stop a 60s JDBC query?
6. Does `StreamingResponseBody` guarantee that socket writes will never block a thread?
7. Why does Spring MVC need a configured `AsyncTaskExecutor` instead of unbounded threads for Callable?
8. If the response to the user has already timed out, what can happen when `DeferredResult.setResult(value)` is called late?
9. What steps must a MockMvc test for Callable include?
10. Does the `@Async` annotation on a service automatically make an HTTP response non-blocking?
11. Why cannot `ThreadLocal` transaction/MDC/SecurityContext be assumed to persist across a worker executor by default?
12. If you switch to WebFlux but still call blocking JDBC directly on the event loop, do you achieve end-to-end non-blocking?
13. When should `DeferredResult` be used instead of Callable?
14. Does async eliminate the socket/buffer cost of each pending HTTP response?
15. With a slow SSE client, why are backpressure/buffer limits still required even though the request thread was released?

**Hints:** (1) Callable runs on an executor; blocking calls block the executor thread. (2) No; the producer/event thread is decided by the application. (3) MVC continues via an ASYNC dispatch. (4) Request release/resume lifecycle vs. I/O readiness. (5) No; cancellation/downstream timeouts are needed. (6) No; OutputStream.write can block. (7) Protect concurrency/queue/memory. (8) The result may be rejected because it is already complete. (9) Request asyncStarted → MvcResult → asyncDispatch → assert. (10) No; method execution and MVC return-type handling are two separate layers. (11) Thread-bound context. (12) No. (13) When the result arrives from a callback/event without needing a worker waiting. (14) No. (15) The producer can be faster than network/consumer speed.

## 18. Official references

- [Spring Framework — Asynchronous Requests in Spring MVC](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-async.html)
- [Spring Framework 6.1 — AsyncSupportConfigurer Javadoc](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/web/servlet/config/annotation/AsyncSupportConfigurer.html)
- [Spring Framework 6.1 — DeferredResult Javadoc](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/web/context/request/async/DeferredResult.html)
- [Spring Framework 6.1 — WebAsyncTask Javadoc](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/web/context/request/async/WebAsyncTask.html)
- [Spring Framework — MVC Streaming](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-async.html#webmvc-ann-async-http-streaming)
- [Spring Framework — MVC Compared to WebFlux](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-async.html#webmvc-ann-async-vs-webflux)
- [Spring Framework — ThreadPoolTaskExecutor](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html)
- [Jakarta Servlet 6.0 — AsyncContext](https://jakarta.ee/specifications/servlet/6.0/apidocs/jakarta.servlet/jakarta/servlet/asynccontext)
- [Jakarta Servlet 6.0 — ReadListener](https://jakarta.ee/specifications/servlet/6.0/apidocs/jakarta.servlet/jakarta/servlet/readlistener)
- [Jakarta Servlet 6.0 — WriteListener](https://jakarta.ee/specifications/servlet/6.0/apidocs/jakarta.servlet/jakarta/servlet/writelistener)
- [Spring MVC Testing — Asynchronous Requests](https://docs.spring.io/spring-framework/reference/testing/spring-mvc-test-framework/async-requests.html)

**Summary:** Servlet async releases the **initial Servlet request thread** while the HTTP response is still pending and uses an **ASYNC dispatch** to complete it later. `Callable` typically moves blocking work to an executor; `DeferredResult` can wait for an external callback without needing a dedicated waiting thread; `WebAsyncTask` adds timeout/callbacks. This is not proof of non-blocking I/O. **Servlet 3.1 ReadListener/WriteListener** addresses low-level socket readiness, while WebFlux provides a more reactive model when dependencies support end-to-end non-blocking. When implementing, measure threads/queues/downstream timeouts, ensure security/trace context propagation, cleanup, and load bounds — do not just change the return type and consider the application "non-blocking".
