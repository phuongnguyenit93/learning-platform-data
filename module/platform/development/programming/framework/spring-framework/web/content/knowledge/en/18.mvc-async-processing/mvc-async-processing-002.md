# Callable, DeferredResult, WebAsyncTask, and Choosing a Completion Model in Spring MVC

## 1. Goal: returning an HTTP response after work completes

In synchronous Spring MVC, a Servlet container thread receives the request, runs the controller, waits for a DB query/external service, produces a result, and writes the response. If computing the result takes a long time to wait, the request-processing thread can be held for the entire wait.

Spring MVC supports **asynchronous Servlet request processing**. A controller can return a **value representing a result that will appear in the future**. Spring enters async mode, releases the initial Servlet request thread, and leaves the response open. When the result is ready, MVC performs an **ASYNC dispatch** to continue processing the result, apply handler return-value processing (JSON/view/error), and complete the response.

Three very common choices:

- `Callable<T>` — the controller hands over **a task that computes the result** for Spring MVC to execute using `AsyncTaskExecutor`.
- `DeferredResult<T>` — the controller hands over **a handle to receive the result**; the application or an external event/callback calls `setResult(...)` or `setErrorResult(...)`.
- `WebAsyncTask<T>` — wraps `Callable<T>` and allows configuring **timeout, executor, and onTimeout/onError/onCompletion** per request.

This lesson is about **choosing the completion model**, not just three allowed Java return types. You need to understand who owns the task, who finishes the response, how timeouts are measured, how waiting resources are managed, and when to choose reactive/streaming instead of these single-result types.

### Learning outcomes

After this lesson, you can:

1. Draw the exact flow `REQUEST → startAsync → release container thread → ASYNC redispatch → response`.
2. Distinguish `Callable`, `DeferredResult`, and `WebAsyncTask` by **producer, thread, completion trigger, timeout, and cleanup**.
3. Configure the MVC executor via `WebMvcConfigurer#configureAsyncSupport`; understand why the default executor should not be used blindly under high load.
4. Handle `setErrorResult`, exceptions, `@ExceptionHandler`, timeouts, network/client disconnect errors, and concurrent completion races.
5. Design endpoints that do not leak DeferredResult in maps, do not hold request threads with `Future#get()`, and do not rely blindly on thread-locals.
6. Run a Spring Boot 3 + Java 17 example and verify `request().asyncStarted()` and `asyncDispatch(...)` with MockMvc.

**Scope:** Spring Framework 6.x/Spring Boot 3.x, Jakarta Servlet API, and Spring MVC (Servlet stack). Spring WebFlux has its own reactive model. Returning `Callable`/`DeferredResult` does not automatically turn all of Spring MVC, JDBC, or HttpServletResponse into non-blocking I/O.

## 2. Servlet async: releasing the request thread without finishing the response yet

Synchronous request:

```text
Servlet thread T1
┌────────────────────────────────────────────────────┐
│ GET /report                                        │
│   → filters → DispatcherServlet → controller       │
│   → read DB/wait remote service → build body       │
│   → Jackson/View render → HTTP 200 → thread idle   │
└────────────────────────────────────────────────────┘
         holds Servlet thread for the entire wait time
```

Spring MVC async:

```text
T1: Servlet container thread                  T2: worker/event thread
──────────────────────────                    ─────────────────────────
GET /report
  → filters → DispatcherServlet
  → controller returns Callable or DeferredResult
  → ServletRequest.startAsync()
  → T1 exits filter/Servlet chain
      response STILL open                     Callable runs / event waits...
                                            └── produces result
                                                or calls setResult(...)
                           │
                           ▼
T3: Servlet container ASYNC redispatch
  → DispatcherServlet resumes with available result
  → ResponseEntity/JSON/View/error handler
  → HTTP 200/4xx/5xx
  → completes async request
```

Important facts:

- When the initial thread leaves request processing, **the HTTP response has not necessarily been sent yet**. The browser is still waiting.
- During the `ASYNC` redispatch, MVC may match the same URL, but **it does not invoke the original controller method again as a new request**; it resumes processing the stored async value.
- An `ASYNC` dispatch differs from `forward:`, differs from `redirect:`, and differs from the user opening a new HTTP connection.
- Switching to async **does not mean CPU/DB work disappears**. `Callable` only moves blocking work from the container thread to an executor thread.
- DeferredResult can be effective with a genuinely callback/event-based producer: the Servlet thread is freed **and** no extra thread sits waiting for the result. However, if you do `new Thread(...).sleep(...)` per DeferredResult, you only move the problem elsewhere.
- The final response still goes through Spring MVC processing, so exceptions and message conversion continue to work according to the Framework's rules.

### 2.1. Servlet prerequisites

Servlet async must be enabled on `DispatcherServlet` and relevant Servlet filters with `asyncSupported=true`; any filter that needs to participate in the ASYNC redispatch must be mapped for `DispatcherType.ASYNC`. In a typical Spring Boot Servlet MVC setup, Boot manages much of this. With `web.xml`, custom filter registrations, or custom WAR deployments, verify with real container testing.

Example mapping for a custom filter:

```java
registration.setAsyncSupported(true);
registration.setDispatcherTypes(
    DispatcherType.REQUEST, DispatcherType.ASYNC);
```

*This is an illustrative snippet of FilterRegistrationBean/Servlet registration, not a standalone Java file.*

`OncePerRequestFilter` has its own redispatch participation policy via `shouldNotFilterAsyncDispatch()`. Having the `asyncSupported` flag alone on a Filter does not guarantee it is called on an ASYNC dispatch; mapping, filter behavior, and the container all matter.

## 3. Quick decision table: who completes the result?

| Criterion | `Callable<T>` | `DeferredResult<T>` | `WebAsyncTask<T>` |
| --- | --- | --- | --- |
| Who executes? | Spring MVC submits callable to AsyncTaskExecutor | Application-managed producer: message/event/webhook/callback | Like Callable, but executor can be customized |
| Completion trigger | Callable returns/throws | Application calls `setResult` / `setErrorResult` | Callable returns/throws or timeout/error callback |
| Need to keep pending handle? | No, MVC manages the Callable | Usually yes, if an external callback needs to locate the right handle | No, MVC manages the callable |
| Per-request timeout | Not directly on Java Callable | `new DeferredResult<>(timeoutMillis)` | `new WebAsyncTask<>(timeoutMillis, callable)` |
| Timeout hook | Via MVC global CallableProcessingInterceptor | `onTimeout(Runnable)` | `onTimeout(Callable<T>)` |
| Error hook | Via MVC global interceptor / MVC exception handling | `onError(Consumer<Throwable>)`, `setErrorResult` | `onError(Callable<T>)` |
| Completion hook | Via MVC global interceptor | `onCompletion(Runnable)` | `onCompletion(Runnable)` |
| Per-request executor | Global MVC config or manage tasks externally | Does not require an executor to complete | Can specify an AsyncTaskExecutor or bean name |
| Typical use case | Blocking service that must run off the Servlet thread | Waiting for an unexpected/external event from an event bus | Blocking task with a different SLA/executor than default |
| Main risk | Executor pool/queue fills up, blocking still exists | Pending map leaks, timeout/callback races | Same as Callable + misusing callbacks/cancellation |

**The best model-selection question:** "How will the result **arrive**?" If you already have a callable to execute, choose Callable/WebAsyncTask. If an independent event will decide when the result is available, choose DeferredResult.

## 4. Callable<T>: handing a task over for Spring to execute

A controller can return:

```java
@GetMapping("/api/report")
public Callable<ResponseEntity<String>> report() {
    return () -> {
        String result = slowBlockingService.buildReport();
        return ResponseEntity.ok(result);
    };
}
```

*This is an illustrative snippet inside a `@RestController` with `slowBlockingService` injected; a standalone runnable example is in section 10.*

Flow:

```text
Controller thread T1:
  creates Callable → returns → Spring startAsync → T1 idle

MVC AsyncTaskExecutor thread T2:
  call() runs
    ├── success → result is stored
    └── exception → exception is stored

Container thread T3:
  ASYNC dispatch → Spring handles ResponseEntity, View, or exception
```

### 4.1. Callable does not mean non-blocking service

If `slowBlockingService.buildReport()` still uses blocking JDBC, thread T2 is still held while the DB processes. The benefit is **not holding a Servlet container thread** for the task, keeping container threads ready to accept new requests. However, total threads and DB resources must still be sufficient; if the executor queue grows unboundedly, latency and memory can be worse than synchronous requests.

Do not do this in a controller:

```java
@GetMapping("/wrong")
public String wrong() throws Exception {
    Future<String> future = executor.submit(this::slowCall);
    return future.get(); // Servlet thread T1 still waits!
}
```

The code above illustrates an **anti-pattern** and will not compile standalone without fields/helpers. Calling `get()` directly **defeats** Servlet async. Return a Callable or a future representation supported by MVC.

### 4.2. When to choose Callable?

- The task has a clear start and end, rather than waiting on an external message/event.
- You want MVC to submit the task and manage the return value/exception automatically.
- Per-endpoint timeout or custom executor is unnecessary; global configuration suffices.
- The service is already blocking, you have sufficient thread/connection pools, and you want to return the Servlet thread early.

Do not choose it just because "the controller should be fast": measure throughput, queues, DB connections, and tail latency before and after.

## 5. WebAsyncTask<T>: Callable with its own SLA and executor

`WebAsyncTask<T>` holds a `Callable<T>` like the model above, while also carrying optional timeout and executor settings along with lifecycle callbacks.

```java
@GetMapping("/api/report-with-deadline")
public WebAsyncTask<ResponseEntity<String>> report() {
    WebAsyncTask<ResponseEntity<String>> task =
        new WebAsyncTask<>(5_000L,
            () -> ResponseEntity.ok("report-ready"));

    task.onTimeout(() ->
        ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
                      .body("report-timeout"));

    task.onError(() ->
        ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR)
                      .body("report-error"));

    task.onCompletion(() ->
        logger.debug("HTTP async processing finished"));

    return task;
}
```

*Illustrative controller snippet with logger; the runnable project uses different endpoint names and full imports.*

### 5.1. Do the callbacks have the same signature?

No:

- `onTimeout(Callable<T>)` takes a callback **returning a value of type T** (or throwing an exception) as a fallback result when Servlet async times out.
- `onError(Callable<T>)` takes a callback that can produce a fallback result when an async container error occurs.
- `onCompletion(Runnable)` is for **resource cleanup/observability** when the async request finishes, including timeouts/errors.

Timeout/error callbacks run on a container thread, so **they must return quickly without blocking**. Do not call a slow remote HTTP service or wait on `Future#get()` inside a callback just to build a fallback.

### 5.2. Timeout does not mean cancelling the business task

When the client waits past the timeout:

- Spring/the container can produce a timeout/error result and finish the response.
- The submitted Callable may **still be running**; timing out the response **does not automatically guarantee** downstream JDBC/HTTP work stops immediately.
- You need deadlines in the DB/HTTP clients themselves, cancellation design, interruption handling, idempotency, and proper tracing.
- Do not confuse "returned 503/504 to the browser" with "all backend work has stopped".

The timeout in `WebAsyncTask<>(5_000L, callable)` is measured against the Servlet/container async request lifecycle, not a separate CPU quota for the callable.

### 5.3. Per-request executor

You can pick a different executor via `WebAsyncTask` constructors, such as overloads taking an `AsyncTaskExecutor` or an executor bean name. When a reporting endpoint needs a dedicated pool while short tasks use the default pool, separation helps with bulkheading, but explicit bounds must be set. Never create `new ThreadPoolTaskExecutor()` **inside individual requests**.

If the whole application shares a relatively uniform policy, configuring `WebMvcConfigurer#configureAsyncSupport` is simpler; use a per-endpoint executor only when workloads/priorities genuinely differ.

## 6. DeferredResult<T>: waiting for an external producer without handing over a Callable

`DeferredResult<T>` is a **future response completion point**. The controller creates it, returns immediately, and keeps a reference so elsewhere (event bus, JMS consumer, callback, another request) can complete it.

```java
@GetMapping("/api/jobs/{id}/wait")
public DeferredResult<ResponseEntity<String>> waitForJob(
        @PathVariable String id) {

    DeferredResult<ResponseEntity<String>> result =
        new DeferredResult<>(10_000L);

    pending.put(id, result);

    result.onTimeout(() ->
        result.setResult(ResponseEntity.status(504)
                                       .body("job-timeout")));

    result.onCompletion(() -> pending.remove(id, result));

    return result;
}
```

*This is an illustrative snippet in a controller with a concurrent pending map; the full project below handles duplicate IDs and cleanup.*

Another producer:

```java
DeferredResult<ResponseEntity<String>> result = pending.get(jobId);
if (result != null) {
    boolean accepted =
        result.setResult(ResponseEntity.ok("job-completed"));
    // false: already has a result, timed out, or no longer usable
}
```

Advantages:

- The controller **does not need to wait on the Servlet thread**.
- The producer does not have to be the MVC executor: it can be a message broker listener, an async client callback, or an event from a domain service.
- The model fits **single-result long polling** very well.

However, you must manage ownership, correlation IDs, timeouts, cancellation/disconnects, queue size, cleanup, and concurrency yourself.

### 6.1. setResult/setErrorResult is an ordered race

`DeferredResult#setResult(value)` returns a boolean:

- `true` if the new result was set successfully.
- `false` if a result was already set or the request/result is no longer valid.

A response can only be decided once: there can be a race between an **arriving event**, **timeout**, **async error**, and **request completion**. Do not assume the callback will beat the timeout.

`setErrorResult(exception)` passes the error into the MVC exception handling pipeline, which can be handled by `@ExceptionHandler` or `@ControllerAdvice`. If passing a response object rather than a Throwable via the error-result API, understand how the Framework interprets that return value; if you want HTTP 504 on timeout, calling `setResult(ResponseEntity.status(504).body(...))` is simpler.

### 6.2. Timely cleanup

For a pending map, protect against the following:

- On timeout or connection close: remove the reference from the map.
- On completion: remove the reference when the request actually completes.
- When two waiters share the same ID: do not silently overwrite the first waiter.
- When an event arrives after timeout: do not use a stale object; reflect the failed `setResult`.
- When a producer never sends anything: enforce timeout/TTL, bound pending count, and apply backpressure.
- When the application shuts down: close/wake pending requests with a clear policy.

`onCompletion(...)` is called whenever the Servlet async request finishes for any reason, making it valuable for cleanup. `onTimeout(...)` and `onError(...)` are fallback/result hooks, not replacements for full cleanup.

### 6.3. Do not use DeferredResult just to park a waiting thread

Wrong:

```java
@GetMapping("/wrong-deferred")
public DeferredResult<String> wrong() {
    DeferredResult<String> dr = new DeferredResult<>();
    executor.execute(() -> {
        try {
            Thread.sleep(10_000); // holds a thread just to wait
            dr.setResult("done");
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            dr.setErrorResult(e);
        }
    });
    return dr;
}
```

This snippet illustrates an anti-pattern. If the work is already a blocking `Callable`, letting MVC manage it via `Callable/WebAsyncTask` is usually easier. `DeferredResult` shows its real benefit when the API is already callback-based and needs no sleeping waiting thread.

## 7. Who owns completion? Architecture decision matrix

| Source of result | Default choice | Why |
| --- | --- | --- |
| Blocking service computes and returns one value | `Callable<T>` | MVC submits the task and manages the result |
| Blocking service with custom timeout/SLA | `WebAsyncTask<T>` | Callable + custom timeout, callbacks, and executor |
| JMS/Kafka/message consumer receives completion event | `DeferredResult<T>` | Event arrives on its own, no waiting thread needed |
| External webhook marks a job done | `DeferredResult<T>` | Callback completes the pending handle |
| Already have `CompletableFuture<T>`/`CompletionStage<T>` | Return an MVC-supported async type or adapt appropriately | Avoids creating a waiting thread/blocking `get` |
| Long polling one response after one event | `DeferredResult<T>` | Single result, clear timeout and cleanup |
| SSE stream of multiple events | `SseEmitter` or reactive stream adaptation | Single-value type does not fit |
| Streaming raw bytes for video/files | `StreamingResponseBody` | Needs streaming/chunking and writing-thread control |
| End-to-end non-blocking flow and backpressure | Consider WebFlux/reactive clients | MVC async does not make JDBC/Servlet writes non-blocking |

**Do not decide based on class name alone.** What matters is the actual producer, number of responses, blocking potential, data ownership, concurrent request count, deadlines, and expected client behavior.

## 8. Timeout, error, and completion mechanics

### 8.1. Where do timeouts come from?

Sources can include:

1. Servlet container async timeout (defaults vary by container).
2. MVC global async timeout from `AsyncSupportConfigurer#setDefaultTimeout(...)`.
3. Per-request timeout on `DeferredResult<>(milliseconds)` or `WebAsyncTask<>(milliseconds, callable)`.
4. DB client, HTTP client, and messaging layer timeouts.
5. Reverse proxy/API gateway/client timeouts — which can close the connection **before** the server.
6. Thread pool saturation causing a Callable not to run before the request expires.

Therefore, "setting 5 seconds on WebAsyncTask" is insufficient if a downstream HTTP client has a 60-second read timeout. Maintain a **deadline budget** across layers: service/read timeouts smaller than the request budget, with proper fallbacks and cleanup.

### 8.2. Default behavior on timeout

If you do not handle a timeout and the response is uncommitted, standard Spring MVC async timeout interceptors can lead to `AsyncRequestTimeoutException` and HTTP **503 Service Unavailable**. However, exact response/status depends on framework version, exception handling, container, and custom interceptors; do not rely on defaults in place of an explicit policy.

In the demo we configure:

- WebAsyncTask timeout → `503` body `webtask-timeout`.
- DeferredResult timeout → `504` body `deferred-timeout`.

That is a **contract deliberately chosen by the example**; 503/504 are not the only definitions for these two async types.

### 8.3. Exceptions flow through @ExceptionHandler

If a Callable throws, Spring MVC stores the concurrent result as an exception and redispatches. `@ExceptionHandler` or `@RestControllerAdvice` can handle it just like a synchronous controller error.

With DeferredResult:

```java
result.setErrorResult(
    new IllegalStateException("remote event failed"));
```

The Framework can route this through normal exception resolution. Do not return sensitive technical error strings to clients; API error schemas should be stable and avoid exposing infrastructure exception details.

### 8.4. Completion ends the HTTP exchange, not necessarily the work

`onCompletion` is for releasing pending references, clearing context, and recording metrics. Do not assume every database operation stops when the HTTP connection drops or a timeout occurs. If business side effects continue after a timeout, design idempotency keys, job states, retry semantics, and duplicate suppression.

### 8.5. Callbacks must be short

Timeout/error callbacks usually run on a Servlet container thread. Performing slow operations inside a callback can congest the container pool, defeating the goal of async. Callbacks should generally only **set a fallback result, record lightweight metrics, mark cancellation, and release references**, then return.

## 9. Executors, backpressure, and context propagation

### 9.1. Configuring MVC AsyncTaskExecutor

Spring Framework MVC allows:

```java
@Configuration
class MvcAsyncConfig implements WebMvcConfigurer {
    private final AsyncTaskExecutor executor;

    MvcAsyncConfig(
            @Qualifier("mvcExecutor") AsyncTaskExecutor executor) {
        this.executor = executor;
    }

    @Override
    public void configureAsyncSupport(AsyncSupportConfigurer configurer) {
        configurer.setTaskExecutor(executor);
        configurer.setDefaultTimeout(10_000L);
    }
}
```

*Illustrative configuration class snippet; the project in section 10 has the full file and imports.*

The default executor works for dev, but Spring documentation warns it is **not suitable for production under high load without configuration**. Configure core/max pool size, queue capacity, and rejection behavior, and attach metrics for queue length and active threads.

### 9.2. An executor pool does not make resources infinite

If a pool has 4 worker threads and each Callable blocks for 10 seconds, at most roughly 4 blocking tasks run concurrently in that pool. Other requests queue up and may time out before getting a worker.

So design with:

- Bounded queues and concurrent requests; never leave pending maps unbounded.
- Clear timeouts/deadlines in both the app and downstream dependencies.
- Saturation policies: queue, reject, circuit breaker, backoff retries.
- Properly sized DB connection pools and HTTP client pools.
- Bulkheads so slow tasks do not starve all workers.
- Load testing for p95/p99, rather than pointing at `asyncStarted=true` to claim throughput improved.

### 9.3. ThreadLocal, MDC, and Spring Security

`LocaleContextHolder`, `RequestContextHolder`, logging MDC, transaction context, and some SecurityContext storage rely on thread-locals. When MVC switches from the initial thread to an executor thread, **do not assume every context moves automatically**.

- Passing needed IDs/locale/user data **explicitly** into the callable/event callback is the easiest to control.
- For logging MDC, use a task decorator/context propagation on the executor.
- For Spring Security, use proper integrations/context propagation (such as security context delegation) instead of copying mutable SecurityContexts onto shared threads and forgetting cleanup.
- A Servlet thread's transaction does not automatically extend into a Callable thread; place transaction boundaries on the service executed by the worker.
- For DeferredResult producers running on message listeners, request thread context usually **does not exist**, so explicit correlation context is essential.

Do not hold onto `HttpServletRequest` or `HttpServletResponse` after the HTTP async request finishes; doing so causes stale references and leaks.

### 9.4. AsyncHandlerInterceptor differs from traditional HandlerInterceptor

In MVC async, `preHandle` can run in the initial dispatch and again on the redispatch. When the request enters concurrent handling, MVC can invoke `AsyncHandlerInterceptor#afterConcurrentHandlingStarted` instead of immediately invoking `postHandle`/`afterCompletion` on the first pass. When the ASYNC dispatch processes the result value, the interceptor chain participates again per Framework rules.

If counting "one HTTP request" metrics in an interceptor, do not increment the request count on every `preHandle`; use a request attribute/correlation ID and appropriate completion semantics.

## 10. Runnable example: Spring Boot 3 + Java 17

The application has a concrete set of endpoints:

- `GET /work/callable` → `Callable<ResponseEntity<String>>`, executed by Spring via the MVC executor.
- `GET /work/callable/fail` → Callable throws an exception, `@RestControllerAdvice` converts it to 500 JSON with a stable code.
- `GET /work/webtask` → `WebAsyncTask<ResponseEntity<String>>` with deadline and fallback callbacks.
- `GET /work/deferred/{id}` → waits for a **POST from another request** to receive a result.
- `POST /work/deferred/{id}/complete` → illustrative producer calling `setResult`.
- `DeferredResult` timeout is completed by the server with HTTP 504; `onCompletion` cleans up the pending map.

The example uses an in-memory map for ease of learning; **do not expose a public complete endpoint in production** without authentication/authorization and pending request limits.

### 10.1. Directory tree

```text
spring-mvc-async-models/
├── pom.xml
└── src/
    ├── main/
    │   └── java/example/
    │       ├── AsyncModelsApplication.java
    │       ├── MvcAsyncConfig.java
    │       └── WorkController.java
    └── test/
        └── java/example/WorkControllerTest.java
```

### 10.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>spring-mvc-async-models</artifactId>
    <version>1.0.0</version>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
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
```

### 10.3. AsyncModelsApplication.java

```java
package example;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class AsyncModelsApplication {
    public static void main(String[] args) {
        SpringApplication.run(AsyncModelsApplication.class, args);
    }
}
```

### 10.4. MvcAsyncConfig.java

```java
package example;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.AsyncTaskExecutor;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.web.servlet.config.annotation.AsyncSupportConfigurer;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class MvcAsyncConfig implements WebMvcConfigurer {

    private final AsyncTaskExecutor mvcExecutor;

    public MvcAsyncConfig(
            @Qualifier("mvcExecutor") AsyncTaskExecutor mvcExecutor) {
        this.mvcExecutor = mvcExecutor;
    }

    @Bean(name = "mvcExecutor")
    public static ThreadPoolTaskExecutor mvcExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(32);
        executor.setThreadNamePrefix("mvc-worker-");
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.initialize();
        return executor;
    }

    @Override
    public void configureAsyncSupport(AsyncSupportConfigurer configurer) {
        configurer.setTaskExecutor(mvcExecutor);
        configurer.setDefaultTimeout(10_000L);
    }
}
```

The thread pool is created **once** as a Spring bean. These are sample sizes for the demo, not a production sizing rule. If a real application has long tasks, it needs connection pools, bounded capacity, queue metrics, rejection policies, and shutdown timeouts.

### 10.5. WorkController.java

```java
package example;

import java.util.Map;
import java.util.concurrent.Callable;
import java.util.concurrent.ConcurrentHashMap;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.context.request.async.DeferredResult;
import org.springframework.web.context.request.async.WebAsyncTask;
import org.springframework.web.server.ResponseStatusException;

@RestController
public class WorkController {

    private final Map<String, DeferredResult<ResponseEntity<String>>> pending =
            new ConcurrentHashMap<>();

    @GetMapping("/work/callable")
    public Callable<ResponseEntity<String>> callable() {
        return () -> ResponseEntity.ok("callable-ok");
    }

    @GetMapping("/work/callable/fail")
    public Callable<ResponseEntity<String>> failedCallable() {
        return () -> {
            throw new IllegalStateException("simulated failure");
        };
    }

    @GetMapping("/work/webtask")
    public WebAsyncTask<ResponseEntity<String>> webTask() {
        WebAsyncTask<ResponseEntity<String>> task =
                new WebAsyncTask<>(5_000L,
                    () -> ResponseEntity.ok("webtask-ok"));

        task.onTimeout(() ->
            ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
                          .body("webtask-timeout"));

        task.onError(() ->
            ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR)
                          .body("webtask-error"));

        task.onCompletion(() -> {
            // Only record lightweight metrics / cleanup; do not await blocking work.
        });

        return task;
    }

    @GetMapping("/work/deferred/{id}")
    public DeferredResult<ResponseEntity<String>> waitForWork(
            @PathVariable String id) {

        DeferredResult<ResponseEntity<String>> result =
                new DeferredResult<>(5_000L);

        DeferredResult<ResponseEntity<String>> existing =
                pending.putIfAbsent(id, result);

        if (existing != null) {
            throw new ResponseStatusException(
                    HttpStatus.CONFLICT, "A waiter already exists");
        }

        result.onTimeout(() ->
            result.setResult(
                ResponseEntity.status(HttpStatus.GATEWAY_TIMEOUT)
                              .body("deferred-timeout")));

        result.onError(result::setErrorResult);

        result.onCompletion(() -> pending.remove(id, result));

        return result;
    }

    @PostMapping("/work/deferred/{id}/complete")
    public ResponseEntity<String> complete(
            @PathVariable String id) {

        DeferredResult<ResponseEntity<String>> result = pending.get(id);
        if (result == null) {
            return ResponseEntity.notFound().build();
        }

        boolean completed =
                result.setResult(ResponseEntity.ok("deferred-ok-" + id));

        return completed
                ? ResponseEntity.accepted().body("event-accepted")
                : ResponseEntity.status(HttpStatus.CONFLICT)
                                .body("already-completed");
    }
}

@RestControllerAdvice
class WorkErrors {
    @ExceptionHandler(IllegalStateException.class)
    ResponseEntity<Map<String, String>> onIllegalState(
            IllegalStateException exception) {
        return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR)
                .body(Map.of("code", "WORK_FAILED"));
    }
}
```

**Key points about the code above:**

- `Callable` and `WebAsyncTask` are submitted to `AsyncTaskExecutor` by MVC; the controller just builds the task and returns immediately.
- `DeferredResult` does not submit any task by itself. It waits for **POST /complete** as an external event. In a real system, the producer is typically a message consumer or service callback.
- `pending.putIfAbsent` avoids silently replacing a waiter with the same ID. There is no authentication/rate limit in this demo: that **must** be added in production.
- Timeout sets HTTP 504 per the sample policy. `setResult` can fail if the producer already won or the request expired.
- `onCompletion` removes the exact `id/result` pair so it does not accidentally delete a newer waiter with the same ID.
- `result.onError(result::setErrorResult)` forwards the exception to MVC. The callback runs quickly without blocking the container thread.
- `@RestControllerAdvice` handles exceptions thrown from a Callable. For network/client disconnect errors, not every exception can send a response after the connection breaks.

### 10.6. Running with Maven

In the directory containing `pom.xml`:

```bash
mvn test
mvn spring-boot:run
```

GET Callable:

```bash
curl -i http://localhost:8080/work/callable
```

Expected body on HTTP 200:

```text
callable-ok
```

GET WebAsyncTask:

```bash
curl -i http://localhost:8080/work/webtask
```

Expected 200 body:

```text
webtask-ok
```

GET failed Callable:

```bash
curl -i http://localhost:8080/work/callable/fail
```

Expected status 500, JSON body:

```json
{"code":"WORK_FAILED"}
```

Server-side async handling does not mean the client receives the response "immediately"; the client still waits for the work to finish before getting the body.

### 10.7. Simulating an external event for DeferredResult

Open terminal A first:

```bash
curl -i http://localhost:8080/work/deferred/job-42
```

Within the 5-second timeout, open terminal B:

```bash
curl -i -X POST \
  http://localhost:8080/work/deferred/job-42/complete
```

Terminal B receives body:

```text
event-accepted
```

Terminal A receives body:

```text
deferred-ok-job-42
```

If no producer sends POST, after the timeout the application policy returns 504 and:

```text
deferred-timeout
```

On Windows PowerShell you can use `curl.exe` and put the command on one line. Response header order can differ, so do not write tests asserting byte-for-byte full cURL output. This is a single-response long-polling demo; production needs authentication, ownership checks, concurrent waiter limits, and a job-state store when running multiple instances.

## 11. Testing MVC async properly: two stages

`MockMvc` does not simulate a browser waiting over the network on its own. An async MVC test has two passes:

1. Send the request with `mvc.perform(...)` and assert `request().asyncStarted()`.
2. Use `asyncDispatch(mvcResult)` so MVC processes the concurrent result into a response, then assert status/body.

The goal is not just verifying that the controller returns a wrapper, but verifying the **final value and exception handling**.

### 11.1. WorkControllerTest.java

File `src/test/java/example/WorkControllerTest.java`:

```java
package example;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.asyncDispatch;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.request;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class WorkControllerTest {

    @Autowired
    MockMvc mvc;

    @Test
    void callableUsesAsyncProcessing() throws Exception {
        MvcResult pending = mvc.perform(get("/work/callable"))
            .andExpect(request().asyncStarted())
            .andReturn();

        mvc.perform(asyncDispatch(pending))
            .andExpect(status().isOk())
            .andExpect(content().string("callable-ok"));
    }

    @Test
    void webAsyncTaskUsesAsyncProcessing() throws Exception {
        MvcResult pending = mvc.perform(get("/work/webtask"))
            .andExpect(request().asyncStarted())
            .andReturn();

        mvc.perform(asyncDispatch(pending))
            .andExpect(status().isOk())
            .andExpect(content().string("webtask-ok"));
    }

    @Test
    void callableExceptionIsHandledOnRedispatch() throws Exception {
        MvcResult pending = mvc.perform(get("/work/callable/fail"))
            .andExpect(request().asyncStarted())
            .andReturn();

        mvc.perform(asyncDispatch(pending))
            .andExpect(status().isInternalServerError())
            .andExpect(jsonPath("$.code").value("WORK_FAILED"));
    }

    @Test
    void deferredResultIsCompletedByAnotherRequest()
            throws Exception {
        MvcResult waiting = mvc.perform(
                get("/work/deferred/job-test-1"))
            .andExpect(request().asyncStarted())
            .andReturn();

        mvc.perform(post("/work/deferred/job-test-1/complete"))
            .andExpect(status().isAccepted())
            .andExpect(content().string("event-accepted"));

        mvc.perform(asyncDispatch(waiting))
            .andExpect(status().isOk())
            .andExpect(content().string("deferred-ok-job-test-1"));
    }

    @Test
    void unknownJobCannotBeCompleted() throws Exception {
        mvc.perform(post("/work/deferred/not-present/complete"))
            .andExpect(status().isNotFound());
    }

    @Test
    void duplicateWaiterIsRejectedWithoutReplacingOriginal()
            throws Exception {
        MvcResult waiting = mvc.perform(
                get("/work/deferred/job-test-2"))
            .andExpect(request().asyncStarted())
            .andReturn();

        mvc.perform(get("/work/deferred/job-test-2"))
            .andExpect(status().isConflict());

        mvc.perform(post("/work/deferred/job-test-2/complete"))
            .andExpect(status().isAccepted());

        mvc.perform(asyncDispatch(waiting))
            .andExpect(status().isOk())
            .andExpect(content().string("deferred-ok-job-test-2"));
    }

    @Test
    void newWaiterWithAnotherIdIsIndependent()
            throws Exception {
        MvcResult a = mvc.perform(
                get("/work/deferred/job-test-3"))
            .andExpect(request().asyncStarted())
            .andReturn();

        MvcResult b = mvc.perform(
                get("/work/deferred/job-test-4"))
            .andExpect(request().asyncStarted())
            .andReturn();

        mvc.perform(post("/work/deferred/job-test-4/complete"))
            .andExpect(status().isAccepted());
        mvc.perform(post("/work/deferred/job-test-3/complete"))
            .andExpect(status().isAccepted());

        mvc.perform(asyncDispatch(a))
            .andExpect(status().isOk())
            .andExpect(content().string("deferred-ok-job-test-3"));
        mvc.perform(asyncDispatch(b))
            .andExpect(status().isOk())
            .andExpect(content().string("deferred-ok-job-test-4"));
    }
}
```

Tests use distinct IDs so they do not collide when the Spring test context shares the controller instance. In practice, also ensure post-test cleanup and avoid unbounded global state.

### 11.2. Why not assert timeouts by sleeping for 5 seconds?

Spring MVC timeouts involve interaction between the Servlet container, async request manager, and test scheduling. Running `Thread.sleep(5_001)` and hoping HTTP status is always exact can create flaky tests. To test timeouts reliably:

- For unit tests, extract timeout fallback logic into a function tested independently, or test interceptors/callbacks with appropriate mock infrastructure.
- For integration tests, run an embedded server on a random port with a short test-specific timeout and verify real responses with clear timing.
- In production, monitor timeout rates, cancellations, and results completed after client disconnects.

The seven tests above intentionally verify **the completion model and redispatch**, without pretending to verify every container timeout/error scenario. Add separate tests for client disconnects and proxy timeouts on real deployment environments when needed.

## 12. Spring MVC async vs. @Async, CompletableFuture, and WebFlux

### 12.1. @Async does not have the same role

`@Async` belongs to Spring task execution, causing a **method call** to execute asynchronously via a proxy/executor when properly applied. `Callable/DeferredResult/WebAsyncTask` belong to Spring MVC's **HTTP response processing contract**.

An `@Async` service can be called from a controller, but if the controller calls `future.get()` before returning, the Servlet thread is still blocked. The right approach is returning an async type supported by Spring MVC or adapting the result into `DeferredResult` without blocking.

Remember `@Async` usually uses a Spring proxy: self-invocation within the same object may not trigger async advice. Do not automatically conclude "every call to an @Async-annotated method runs on another thread".

### 12.2. CompletableFuture / CompletionStage

Spring MVC supports multiple async return types through async adapters, including `CompletionStage`/`CompletableFuture` per Framework documentation. If you already have a true future from an async API, use it instead of creating an extra blocking worker.

Do not write:

```java
return () -> future.get();
```

if the goal is not to hold a thread waiting on a future. This still blocks the worker executor; for already callback-based producers, `DeferredResult` or MVC async adapters for `CompletionStage` fit better.

### 12.3. MVC async does not mean WebFlux

Spring MVC async:

- Servlet processing starts/redispatches on the container.
- Blocking JDBC/HTTP calls still block the worker when run inside a Callable.
- When the response body is written on the Servlet stack, writing can still be blocking.
- MVC can support streaming/reactive return types via dedicated integrations, but does not turn the entire HTTP layer into WebFlux.

Spring WebFlux:

- Built on reactive contracts and handles non-blocking I/O when the stack and dependencies are compatible.
- Usually requires rethinking repositories/clients, backpressure, and how CPU-blocking work is handled.
- Not "every MVC app moved to WebFlux becomes faster"; measure workloads and library compatibility.

## 13. Common design mistakes

| Misconception | Consequence | How to address |
| --- | --- | --- |
| "Returning Callable makes DB queries non-blocking" | DB call still blocks a worker | Understand threads and backend clients |
| "Async response returns immediately to the browser" | Client still waits, timeout UX unchanged | Distinguish releasing the Servlet thread from completing the response |
| "DeferredResult runs tasks automatically" | Result never completes, times out | Have a clear producer/callback |
| "WebAsyncTask is completely different from Callable" | Over-engineered layers | WebAsyncTask just adds timeout/executor/callbacks |
| Calling `Future#get()` in a controller | Servlet thread stays blocked | Return async type instead of blocking |
| Using `Thread.sleep()` per DeferredResult | Thread pool held pointlessly | Wait for real events or use Callable appropriately |
| Pending map never cleaned | Memory leak, stale correlation IDs | `onCompletion` + timeout policy |
| Using `put` to overwrite waiter | Old request loses its response | `putIfAbsent`, duplicate policy |
| Ignoring boolean return of `setResult` | Late event after timeout treated as success | Check atomic success/failure |
| Slow work inside timeout callback | Container thread gets held | Set fallback very quickly |
| Thinking timeout auto-cancels JDBC/HTTP | Background task keeps causing side effects | Downstream timeouts/cancellation/idempotency |
| Not configuring AsyncTaskExecutor | Uncontrolled saturation/queueing | Bounded executor and metrics |
| Creating a new executor per request | Thread leaks and overhead | Managed Spring bean |
| Using servlet thread-locals inside Callable | Missing/wrong context | Explicit propagation/task decorator |
| Thinking HTTP thread transaction follows worker | Transaction does not exist as expected | Place boundary on service worker |
| Forgetting asyncSupported on custom Servlet Filter | Async can fail | Register compatible Servlets/filters |
| Forgetting to map `DispatcherType.ASYNC` | Filter does not run on redispatch | Check filter mapping/flags |
| Counting metrics on every interceptor preHandle | One HTTP request counted multiple times | Async-aware lifecycle/marker |
| Blindly retrying POST completion multiple times | Duplicate side effects | Idempotency keys, first-result-wins |
| Letting a public endpoint complete any job | Strangers can complete another user's job | Authentication, authorization, ownership |
| Keeping request references after timeout | Memory/resource leak | Completion cleanup, TTL, cancellation |
| Using MockMvc without `asyncDispatch` | Only tests stage 1, misses final response | Call asyncDispatch and assert status/body |
| Testing timeouts with arbitrary sleep | Flaky across CI/containers | Controlled integration testing |
| Treating Servlet MVC async = reactive non-blocking | Wrong capacity plan | Choose stack based on actual blocking I/O |

## 14. Production model-selection checklist

When receiving a requirement "this endpoint must be asynchronous", answer:

1. **Who produces the result?** A function that needs to run, or an event from another producer?
2. **Is there blocking work?** JDBC, external HTTP client, encryption/compression, file I/O?
3. **Who owns the executor?** MVC executor, workload-specific pool, messaging consumer, or HTTP client event loop?
4. **What are the concurrency limits?** Pool, queue, pending request count, per-user quota, backpressure?
5. **Do total timeouts** align across gateway, browser, HTTP client, and downstream?
6. **Is the response type** a single value, or continuous events needing SSE/WebSocket?
7. **How are errors** routed to `@ExceptionHandler`/fallbacks?
8. **Does timeout** cancel the task, or does the task continue? Are side effects idempotent?
9. **How are client disconnects** observed and cleaned up?
10. **How is context** such as locale, MDC, user/tenant propagated across threads?
11. **Where are pending results** stored with multiple replicas? Is an in-memory map enough or is a broker/state store needed?
12. **Do tests** assert `asyncStarted`, `asyncDispatch`, duplicate completion, and errors?
13. **Do metrics** include active waiters, executor active/queue/rejections, timeout rate, and p95/p99 client latency?
14. **Does security** prevent user A from completing/waiting on user B's job?
15. Should you return **202 Accepted + job ID** for independent client polling instead of holding a long-poll HTTP request?

### 14.1. When to return 202 Accepted instead of holding the request?

If work takes many minutes or hours, proxy/client timeouts are short, the application has multiple instances, or work must survive restarts, an endpoint is usually better off as:

```text
POST /jobs           → 202 Accepted, Location: /jobs/123
GET  /jobs/123       → status pending/running/done
GET  /jobs/123/data  → result when complete
```

This is a durable **job lifecycle** model; it does not require keeping a DeferredResult alive in memory for minutes. `DeferredResult` fits moderate long polling better; it is not a queue/job store replacing durable messaging.

## 15. Self-check exercises

**1.** Who submits `Callable<T>` to the executor?  
**Answer:** Spring MVC submits it via the configured `AsyncTaskExecutor`.

**2.** Who completes `DeferredResult<T>`?  
**Answer:** The application/producer calls `setResult` or `setErrorResult`.

**3.** What does `WebAsyncTask<T>` add compared to Callable?  
**Answer:** Timeout, selectable executor, and lifecycle callbacks.

**4.** Does Spring MVC async make the browser receive the response before work completes?  
**Answer:** No; it only releases the initial Servlet request thread.

**5.** After `Callable` returns, how does MVC process the final result?  
**Answer:** An ASYNC redispatch through the Servlet container, then handling the return value like normal MVC.

**6.** Should you use DeferredResult and spawn a thread to sleep waiting for a callback?  
**Answer:** No; it loses the event-driven benefit and wastes a worker.

**7.** What happens when two producers call `setResult` on the same DeferredResult?  
**Answer:** Only one wins; check the boolean return value and handle the loser.

**8.** If a timeout returns HTTP 504, is the Callable guaranteed to stop immediately?  
**Answer:** No; cancellation and downstream deadlines must be designed separately.

**9.** What type does the timeout callback of WebAsyncTask return?  
**Answer:** `Callable<T>` producing a fallback value of type T.

**10.** What is `WebMvcConfigurer#configureAsyncSupport` used to configure?  
**Answer:** The executor, default timeout, and async processing interceptors.

**11.** When MockMvc performs a Callable request, is asserting 200 on the first pass correct?  
**Answer:** No; you need `asyncStarted()` then `asyncDispatch(...)`.

**12.** If a message broker sends an event after timeout, should you keep writing the response?  
**Answer:** No; `setResult` fails if the result has expired, so clean up/ignore.

**13.** Is `ThreadLocal` MDC guaranteed to appear inside a Callable worker?  
**Answer:** Not by default; propagation is required.

**14.** Does Spring MVC Callable automatically make JDBC non-blocking?  
**Answer:** No.

**15.** Does an ASYNC redispatch cause the controller to run from scratch again?  
**Answer:** MVC normally resumes processing the concurrent result, rather than calling the original controller method again as a new request.

**16.** Can exceptions thrown inside a Callable be handled by `@ExceptionHandler`?  
**Answer:** Yes, via async result exception handling.

**17.** When must a DeferredResult pending map be cleaned up?  
**Answer:** When the request finishes via success, timeout, or error; use `onCompletion` appropriately.

**18.** Should DeferredResult be used to stream multiple events?  
**Answer:** Not suitable; use `SseEmitter`, streaming, or reactive types depending on requirements.

**19.** When does the WebAsyncTask timeout clock start?  
**Answer:** According to the Servlet/container async request lifecycle and MVC configuration, not just "CPU execution time of the Callable".

**20.** What should be used for multi-minute work that must survive restarts?  
**Answer:** Usually a durable job system + 202 Accepted/job status instead of keeping HTTP pending indefinitely.

## 16. Official references

- [Spring Framework 6.2 — Asynchronous Requests](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-ann-async.html): `Callable`, `DeferredResult`, `WebAsyncTask`, ASYNC redispatch, exceptions, interceptors, executor, and context propagation.
- [Spring Framework 6.2 — DeferredResult Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/context/request/async/DeferredResult.html): `setResult`, `setErrorResult`, callbacks, hasResult, and lifecycle.
- [Spring Framework 6.2 — WebAsyncTask Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/context/request/async/WebAsyncTask.html): timeout, executor constructors, `onTimeout`, `onError`, `onCompletion`.
- [Spring Framework 6.2 — MockMvc Async Testing](https://docs.spring.io/spring-framework/reference/6.2/testing/mockmvc/hamcrest/async-requests.html): two-step `asyncStarted` and `asyncDispatch`.
- [Spring Framework — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/6.2/integration/scheduling.html): executor, `@Async`, and task execution configuration.
- [Spring Framework 6.2 — Java WebMvcConfigurer](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/servlet/config/annotation/WebMvcConfigurer.html): `configureAsyncSupport`.
- [Jakarta Servlet Specification](https://jakarta.ee/specifications/servlet/6.0/): `AsyncContext`, `asyncSupported`, and Servlet dispatcher types.

**Rule of thumb:** if **Spring must run a Callable to compute the result**, return `Callable`; if you want **custom timeout/executor/callbacks** for a Callable, use `WebAsyncTask`; if **an event outside the request brings the result**, use `DeferredResult`. All three release the initial Servlet thread, yet still require proper processing resources, concurrency limits, timeouts, cleanup, and security.
