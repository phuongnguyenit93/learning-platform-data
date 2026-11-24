# Servlet Async vs. Non-Blocking Code

In Spring Boot using Spring MVC, a synchronous HTTP request typically holds a servlet container thread until the controller finishes. **Servlet async** allows a request to temporarily leave the initial thread while keeping the HTTP response waiting for a result. When the result becomes available, the container performs further processing or an async dispatch to send the response. **This does not turn JDBC, `Thread.sleep`, or a synchronous HTTP client into non-blocking I/O**: if offloaded to an executor, the work can still block another worker.

This article belongs to the **Servlet Concurrency** section and applies to **Java 17+, Spring Boot 3.3.x, Spring MVC on Jakarta Servlet**. We will distinguish request lifecycles, async execution, and non-blocking I/O; use `AsyncContext`, `Callable`, `DeferredResult`, and `WriteListener`; explain threads, timeouts, executors, and context security; and then build and test a runnable application.

## 1. Concepts that are not synonymous

| Concept | Purpose | Can it still be blocking? |
|---|---|---|
| Synchronous Servlet | Complete the request within the initial dispatch | Yes, directly on the container thread |
| Servlet async lifecycle | Keep the response open while the initial container thread is returned to the pool | Yes, if a worker performs blocking I/O |
| Asynchronous execution | Offload work to a worker/executor or wait for an event | Yes, the worker can `sleep`/run JDBC |
| Non-blocking I/O | Avoid holding a thread waiting for socket/file readiness; use readiness/callbacks | The corresponding I/O does not block a thread; other logic can still block |
| Reactive programming | Compose Publishers/signals; can support demand/backpressure | Can still block if blocking libraries/operations are used |

Simplified request diagram:

~~~text
HTTP Client
   |
Servlet container thread A
   |
Spring MVC Controller
   |
return Callable / DeferredResult
   |
startAsync -> return thread A to pool
   |
   +-- Callable: worker thread B executes, may BLOCK
   |
   +-- DeferredResult: wait for event/future; NO worker may be waiting
   |
Result / Error / Timeout
   |
ASYNC dispatch on container thread C
   |
Serialize body, HTTP response completes
~~~

Threads A, B, and C can be different. Processing a request asynchronously does not make the HTTP response appear immediately; the client still waits, and connections along with other resources may remain active.

## 2. How does a synchronous request hold a container thread?

An illustrative controller:

~~~java
@RestController
class SlowController {

    @GetMapping("/slow")
    String slow() throws InterruptedException {
        Thread.sleep(200); // request thread is blocked
        return "ok";
    }
}
~~~

This is a Spring MVC snippet requiring imports and a Boot project. When a request hits `GET /slow`, the Servlet thread executes the method and waits 200 ms before returning. Under high concurrent load, many threads may wait on JDBC, the filesystem, or an HTTP client; the finite pool of servlet threads can be exhausted.

Very short tasks do not need async at all costs: adding an async lifecycle, executor, and timeout carries overhead. Evaluate actual concurrency needs and long event/I/O waits before choosing an approach.

## 3. Jakarta Servlet AsyncContext

The Servlet API allows starting asynchronous processing when the corresponding servlet/filter supports async. Key methods:

- `ServletRequest.startAsync()` starts the async lifecycle and returns an `AsyncContext`.
- `ServletRequest.isAsyncStarted()` checks whether the request has entered async mode.
- `AsyncContext.start(Runnable)` asks the container to run the Runnable on an appropriate thread; **the Runnable may contain blocking code**.
- `AsyncContext.dispatch()` dispatches the request to the next dispatch on a container thread.
- `AsyncContext.complete()` completes the async operation per the Servlet contract.
- `AsyncContext.setTimeout(long)` sets the timeout in **milliseconds**.
- `AsyncListener` receives `onTimeout`, `onError`, `onComplete`, `onStartAsync`.

A typical flow:

~~~text
REQUEST dispatch
  |
Servlet calls startAsync()
  |
Initial Servlet method + filter chain finishes
  |
Container thread returns to pool
  |
Request/response remain in ASYNC state
  |
  +-- Result available -> dispatch() or complete()
  +-- Error -> error callback/dispatch or application error handling
  +-- Timeout -> onTimeout and timeout/error handling
  |
Response finishes
~~~

Once `startAsync` is called, an HTTP response is not yet finished even though the servlet method has returned. In production, ensure completion paths exist for success, error, timeout, and client disconnect, while avoiding multiple threads writing to the response simultaneously.

### 3.1. Native Servlet example (illustrating the mechanism)

~~~java
import jakarta.servlet.AsyncContext;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServlet;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;

public class NativeAsyncServlet extends HttpServlet {

    @Override
    protected void doGet(
            HttpServletRequest request,
            HttpServletResponse response)
            throws ServletException, IOException {

        AsyncContext async = request.startAsync();
        async.setTimeout(3_000L); // milliseconds

        async.start(() -> {
            try {
                Thread.sleep(100); // blocking on worker!
                HttpServletResponse target =
                    (HttpServletResponse) async.getResponse();
                target.setContentType("text/plain;charset=UTF-8");
                target.getWriter().write("native async done");
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                // Real applications need controlled logging and error handling.
            } catch (IOException ex) {
                // Client may have disconnected; handle per policy.
            } finally {
                async.complete();
            }
        });
    }
}
~~~

This is **not a standalone Boot application**; it requires Servlet registration with `asyncSupported=true` and compatible filters. The demo emphasizes that the initial thread leaves while the worker is still blocked by `Thread.sleep`. In production, a timeout can race with the worker; do not hold onto the response reference and write after completion. You must handle late results, errors, cleanup, and terminal states properly before real-world use.

Registration example:

~~~java
@Bean
ServletRegistrationBean<NativeAsyncServlet> nativeAsyncServlet() {
    ServletRegistrationBean<NativeAsyncServlet> bean =
        new ServletRegistrationBean<>(
            new NativeAsyncServlet(), "/native-async");
    bean.setAsyncSupported(true);
    return bean;
}
~~~

This snippet requires importing `@Bean` and `ServletRegistrationBean` inside a `@Configuration`. Custom filters on the path must also meet async requirements; a single async-supported servlet does not fix an incompatible filter.

## 4. Spring MVC integration with Servlet async

Spring MVC provides built-in abstractions for asynchronous request processing:

| Return type | Result source | Thread usage |
|---|---|---|
| `Callable<T>` | Lambda returns data; Spring MVC submits it to `AsyncTaskExecutor` | Worker executes lambda, may block |
| `WebAsyncTask<T>` | Wraps Callable with optional timeout/executor/callbacks | Worker from the selected executor |
| `DeferredResult<T>` | Value provided when another callback/event calls `setResult`/`setErrorResult` | May hold no worker while waiting for the event |
| `ResponseBodyEmitter` | Sends response parts over time | Some writes remain blocking via executor |
| `SseEmitter` | Server-Sent Events | Long-lived connection; needs timeout/heartbeat/cleanup |
| `StreamingResponseBody` | Writes directly to response OutputStream | Callback typically runs via async executor; writes may block |
| Reactive types in MVC | Result from Publisher adapted by MVC | Does not mean running Spring WebFlux |

Spring MVC manages `startAsync`, receiving the result, and the async dispatch. Controllers using `Callable` or `DeferredResult` typically **do not need to call `HttpServletRequest.startAsync()` directly**.

### 4.1. Callable: work runs on a worker

~~~java
@GetMapping("/api/async/callable")
Callable<Map<String, String>> callable() {
    return () -> {
        Thread.sleep(120);  // worker BLOCKING
        return Map.of("mode", "callable", "value", "ok");
    };
}
~~~

When the handler returns a `Callable`, MVC starts the async lifecycle, submits the Callable via `AsyncTaskExecutor`, and returns the initial servlet thread. The worker sleeps for 120 ms. Once the Callable produces a result, the container continues with an async dispatch and writes JSON.

This is an **asynchronous request**, not a **non-blocking computation**. It keeps the container thread from waiting the entire 120 ms; the executor still needs a worker.

### 4.2. DeferredResult: waiting for callbacks or events

~~~java
@GetMapping("/api/async/deferred")
DeferredResult<String> deferred() {
    DeferredResult<String> pending = new DeferredResult<>(3_000L);
    // Register pending with the service receiving events/callbacks.
    return pending;
}

// When an external event arrives, in the appropriate context:
pending.setResult("done");
~~~

This snippet separates two contexts and is not a complete class. With `DeferredResult`, the result can come from a JMS callback, an external event, an async HTTP client, or a future completed later. While waiting for the event, **no worker may be waiting**.

However, if you replace the event with:

~~~java
executor.execute(() -> {
    Thread.sleep(120); // worker BLOCKING
    pending.setResult("done");
});
~~~

you have only changed which thread is blocked. Do not conclude that `DeferredResult` always performs non-blocking I/O; how the result is produced determines that.

### 4.3. WebAsyncTask and per-request timeouts

`WebAsyncTask` wraps a `Callable` to customize timeout/executor/callbacks for a specific request:

~~~java
@GetMapping("/api/async/task")
WebAsyncTask<String> task() {
    return new WebAsyncTask<>(2_000L, () -> "ok");
}
~~~

This is a controller snippet requiring an import for `WebAsyncTask`. It is convenient when an endpoint needs a different wait time from the default. An HTTP async request timeout does not automatically abort an in-progress JDBC query; the I/O library needs its own timeout/cancellation.

## 5. Async execution does not mean non-blocking I/O

You can create a future in Java:

~~~java
CompletableFuture<String> value =
    CompletableFuture.supplyAsync(
        () -> legacyClient.load(),
        executor);
~~~

`legacyClient` and `executor` are application dependencies. If `load()` uses a blocking HTTP client, the executor thread still waits for the response. In Spring, `@Async` likewise only shifts method invocation to an executor when AOP/proxying is properly configured; it does not make JDBC reactive and does not automatically keep an HTTP response open.

In particular, a controller calling `@Async void` and immediately returning HTTP 200 can report success to the client before side effects complete, and background failures are no longer tied to the request. If the response depends on the work, compose the result using the appropriate MVC abstraction.

### 5.1. Plain Java 17: async yet still blocking

Create `AsyncNotNonBlocking.java`:

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class AsyncNotNonBlocking {
    public static void main(String[] args) {
        ExecutorService pool = Executors.newSingleThreadExecutor();
        try {
            CompletableFuture<String> job =
                CompletableFuture.supplyAsync(() -> {
                    try {
                        Thread.sleep(50);  // BLOCKS worker
                    } catch (InterruptedException ex) {
                        Thread.currentThread().interrupt();
                        throw new IllegalStateException(ex);
                    }
                    return "done";
                }, pool);

            System.out.println("submitted");
            System.out.println(job.join());
        } finally {
            pool.shutdown();
        }
    }
}
~~~

Compile and run:

~~~bash
javac AsyncNotNonBlocking.java
java AsyncNotNonBlocking
~~~

Exact stdout:

~~~text
submitted
done
~~~

`supplyAsync` submits the task; the main thread continues to `println("submitted")`, and then `join()` blocks main waiting for the result. The worker also blocks for 50 ms in `sleep`. The only thing guaranteed is that the task runs via an executor—not that I/O became non-blocking.

## 6. Servlet 3.1 non-blocking I/O: readiness and callbacks

Servlet 3.1 added read/write interfaces based on I/O readiness:
- `ServletInputStream.isReady()` and `setReadListener(ReadListener)`.
- `ServletOutputStream.isReady()` and `setWriteListener(WriteListener)`.
- `ReadListener.onDataAvailable()`, `onAllDataRead()`, and `WriteListener.onWritePossible()`.

In non-blocking output, the application writes only when the stream is ready instead of blocking on the socket:

~~~text
Register WriteListener
       |
onWritePossible()
       |
while isReady() && chunk available
       |-- write(chunk)
       |
isReady() == false
       |
Return from callback, no busy-wait/Thread.sleep
       |
Container signals writable -> next onWritePossible()
       |
All data written -> asyncContext.complete()
~~~

Illustrative API example:

~~~java
ServletOutputStream stream = response.getOutputStream();

stream.setWriteListener(new WriteListener() {
    @Override
    public void onWritePossible() throws IOException {
        while (stream.isReady() && hasNextChunk()) {
            stream.write(nextChunk());
        }
        if (allChunksWritten()) {
            asyncContext.complete();
        }
    }

    @Override
    public void onError(Throwable cause) {
        reportWriteError(cause);
        asyncContext.complete();
    }
});
~~~

This is **pseudocode**, not a standalone runnable class: `hasNextChunk`, `nextChunk`, `allChunksWritten`, and `reportWriteError` must be defined by the application; `asyncContext` must be in async mode, and callbacks and state must be thread-safe. Do not copy verbatim into production. When `isReady()` returns false, the callback must return so the container notifies it later instead of waiting on its own.

**The difference:** `AsyncContext.start(() -> blockingJDBC())` still needs a worker blocking on JDBC; `WriteListener` only handles socket output readiness without blocking a thread waiting for the connection to become writable. Calling JDBC or heavy CPU work **inside** `onWritePossible()` still stalls the callback.

Spring MVC async/streaming **does not by default** rely completely on Servlet-level non-blocking I/O: response writes may run as blocking writes on an executor. WebFlux uses a reactive/non-blocking model on an appropriate runtime; returning a `Flux` from MVC does not turn the app into WebFlux.

## 7. Executors in Spring Boot 3.3

Spring Boot 3.3 auto-configures an `AsyncTaskExecutor` when conditions match. On Java 17 without virtual threads enabled, Boot typically provides a `ThreadPoolTaskExecutor`. In Spring MVC, an `AsyncTaskExecutor` bean is commonly named `applicationTaskExecutor` for async request processing.

You can configure it via:

~~~yaml
spring:
  task:
    execution:
      thread-name-prefix: "demo-async-"
      pool:
        core-size: 4
        max-size: 8
        queue-capacity: 50
        keep-alive: 30s
  mvc:
    async:
      request-timeout: 5s
~~~

Full property names:
- `spring.task.execution.pool.core-size`.
- `spring.task.execution.pool.max-size`.
- `spring.task.execution.pool.queue-capacity`.
- `spring.task.execution.pool.keep-alive`.
- `spring.mvc.async.request-timeout`.

**Queue capacity and max-size are tightly coupled.** If the queue is unbounded, tasks can keep queueing and the pool will not grow up to `max-size` as expected. Consider queue bounds, overload/rejection policies, memory, and maximum wait time.

Do not confuse this executor with **Servlet container threads** (such as `server.tomcat.threads.max` when using Tomcat). Async helps keep container threads from being tied up, but moving work to an executor does not make total workload vanish. With JDBC, the connection pool limit or the database itself can be an even larger bottleneck than worker count.

If the application declares another custom `Executor`, verify whether the `applicationTaskExecutor` bean still exists and has type `AsyncTaskExecutor` for Spring MVC to use. Do not assume an arbitrary bean named `taskExecutor` is always picked up by MVC.

## 8. Timeouts and cancellation do not automatically propagate across layers

| Configuration/mechanism | What is it limiting? |
|---|---|
| `spring.mvc.async.request-timeout` | How long an MVC async request waits before timing out |
| `AsyncContext.setTimeout(ms)` | Timeout of the Servlet async operation |
| `DeferredResult<>(timeoutMs)` | Per-request timeout for a `DeferredResult` |
| `WebAsyncTask` | Per-request timeout for a `Callable` wrapper |
| HTTP client connect/read timeout | Downstream connect/read wait |
| JDBC/query timeout | Database query limit |
| Reverse proxy/ingress timeout | How long the proxy waits for upstream |
| Client timeout/disconnect | How long the client waits for a response |

An async request timeout **does not guarantee** that an in-flight JDBC task is interrupted, a transaction is rolled back, or an outbound HTTP request is automatically canceled. A worker can continue running after the client has given up. Therefore production requires:
- Dedicated downstream timeouts.
- Timeout/error/completion callbacks and resource cleanup.
- Cancellation propagation where supported by clients/libraries.
- A late-result policy (do not write to an already-completed response).
- Not returning HTTP 200 before critical work is actually done.

`DeferredResult.setResult` or `setErrorResult` returns a status indicating whether setting the result was accepted; that does not replace cancelling side effects.

## 9. Runnable Spring Boot example: Sync, Callable, and DeferredResult

A Java 17+ / Spring Boot 3.3.x project has dependencies:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

This is the dependencies block; the project still needs the Spring Boot plugin, toolchain, and Gradle wrapper.

Create `src/main/java/com/example/demo/ServletAsyncApplication.java`:

~~~java
package com.example.demo;

import java.util.Map;
import java.util.concurrent.Callable;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.core.task.AsyncTaskExecutor;
import org.springframework.core.task.TaskRejectedException;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.context.request.async.DeferredResult;
import org.springframework.web.server.ResponseStatusException;

@SpringBootApplication
public class ServletAsyncApplication {
    public static void main(String[] args) {
        SpringApplication.run(ServletAsyncApplication.class, args);
    }
}

@RestController
@RequestMapping("/api/async")
class AsyncDemoController {

    private final AsyncTaskExecutor tasks;

    AsyncDemoController(
            @Qualifier("applicationTaskExecutor")
            AsyncTaskExecutor tasks) {
        this.tasks = tasks;
    }

    @GetMapping("/sync")
    Map<String, String> sync() throws InterruptedException {
        Thread.sleep(120);
        return Map.of("mode", "sync", "value", "ok");
    }

    @GetMapping("/callable")
    Callable<Map<String, String>> callable() {
        return () -> {
            Thread.sleep(120); // worker is still blocking
            return Map.of("mode", "callable", "value", "ok");
        };
    }

    @GetMapping("/deferred")
    DeferredResult<Map<String, String>> deferred() {
        DeferredResult<Map<String, String>> result =
            new DeferredResult<>(3_000L);

        result.onTimeout(() ->
            result.setErrorResult(new ResponseStatusException(
                HttpStatus.GATEWAY_TIMEOUT,
                "Async request timed out")));

        try {
            tasks.execute(() -> {
                try {
                    Thread.sleep(120); // worker is still blocking
                    result.setResult(Map.of(
                        "mode", "deferred", "value", "ok"));
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                    result.setErrorResult(new ResponseStatusException(
                        HttpStatus.SERVICE_UNAVAILABLE,
                        "Worker interrupted", ex));
                }
            });
        } catch (TaskRejectedException ex) {
            result.setErrorResult(new ResponseStatusException(
                HttpStatus.SERVICE_UNAVAILABLE,
                "Server busy", ex));
        }
        return result;
    }
}
~~~

All classes are in the same package, with only `ServletAsyncApplication` public and matching the file name. Spring Boot 3.3 provides `applicationTaskExecutor` when auto-configuration applies; if a project overrides the executor, make sure a bean with the right name/type remains available.

Behavior explanation:
1. `/sync` blocks the **servlet request thread** while sleeping.
2. `/callable` returns a `Callable`; Spring MVC runs it in the async executor and returns the initial servlet thread to the pool.
3. `/deferred` returns a holder; `tasks.execute` runs the task and calls `setResult` afterward. The worker still blocks while sleeping.
4. When the result is ready, MVC resumes via an async dispatch to serialize the JSON response.
5. `DeferredResult<>(3_000L)` sets a per-endpoint timeout, whereas the global property may be 5 seconds.
6. The demo includes basic rejection handling; production needs full overload policies and cancellation/late-result handling.
7. You do not need to add `@EnableAsync` to use MVC `Callable`/`DeferredResult`.

Create `src/main/resources/application.yml`:

~~~yaml
server:
  port: 8080

spring:
  mvc:
    async:
      request-timeout: 5s
  task:
    execution:
      thread-name-prefix: "demo-async-"
      pool:
        core-size: 4
        max-size: 8
        queue-capacity: 50
~~~

Run via the Gradle wrapper:

~~~bash
./gradlew bootRun
~~~

On Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

Call the three endpoints:

~~~bash
curl -i http://localhost:8080/api/async/sync
curl -i http://localhost:8080/api/async/callable
curl -i http://localhost:8080/api/async/deferred
~~~

JSON bodies (key order is not a contract):

~~~json
{"mode":"sync","value":"ok"}
~~~

~~~json
{"mode":"callable","value":"ok"}
~~~

~~~json
{"mode":"deferred","value":"ok"}
~~~

All three endpoints share a 120 ms sleep for illustration. Do not infer exact response latency or thread names from the JSON alone. What to observe is the **threading mechanism and lifecycle**, not a promise that async is always faster than sync.

## 10. Testing Servlet async with MockMvc

For a handler returning `Callable` or `DeferredResult`, MockMvc needs two phases: first assert that async mode started, then call `asyncDispatch(mvcResult)` to inspect the final response.

Create `src/test/java/com/example/demo/ServletAsyncApplicationTest.java`:

~~~java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.asyncDispatch;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.request;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ServletAsyncApplicationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void callableStartsAsync() throws Exception {
        MvcResult first = mvc.perform(get("/api/async/callable"))
            .andExpect(request().asyncStarted())
            .andReturn();

        mvc.perform(asyncDispatch(first))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.mode").value("callable"));
    }

    @Test
    void deferredStartsAsync() throws Exception {
        MvcResult first = mvc.perform(get("/api/async/deferred"))
            .andExpect(request().asyncStarted())
            .andReturn();

        mvc.perform(asyncDispatch(first))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.mode").value("deferred"));
    }

    @Test
    void syncDoesNotStartAsync() throws Exception {
        mvc.perform(get("/api/async/sync"))
            .andExpect(request().asyncNotStarted())
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.mode").value("sync"));
    }
}
~~~

Run:

~~~bash
./gradlew test
~~~

`asyncDispatch` is crucial: the initial MockMvc request does not automatically complete a full container dispatch like a real HTTP request. The test proves MVC uses an async lifecycle, yet **does not prove the internals use non-blocking I/O** (the demo intentionally uses `Thread.sleep`).

To test real servlet container timeouts, client disconnects, socket readiness, and filter dispatches, add `@SpringBootTest(webEnvironment = RANDOM_PORT)` integration tests with an actual HTTP client. MockMvc is not a full model of a socket/servlet container.

## 11. Filters and DispatcherType.ASYNC

A Servlet that legitimately calls `startAsync` must have `asyncSupported=true`; filters in the call chain must also be compatible. If a filter needs to run during the async redispatch, configure the appropriate dispatcher types.

`web.xml` excerpt example:

~~~xml
<filter-mapping>
  <filter-name>traceFilter</filter-name>
  <url-pattern>/*</url-pattern>
  <dispatcher>REQUEST</dispatcher>
  <dispatcher>ASYNC</dispatcher>
</filter-mapping>
~~~

Or via Spring Boot `FilterRegistrationBean`:

~~~java
FilterRegistrationBean<TraceFilter> bean =
    new FilterRegistrationBean<>(new TraceFilter());

bean.setAsyncSupported(true);
bean.setDispatcherTypes(
    DispatcherType.REQUEST, DispatcherType.ASYNC);
~~~

These are illustrative snippets; `TraceFilter` and the registration bean must be properly defined. Do not enable `ASYNC` for all filters if they do not support re-invocation. A filter running on both REQUEST and ASYNC may log twice or wrap the response twice; a filter running only on REQUEST may not observe completion. Verify `DispatcherType.ASYNC` and actual callback lifecycles.

## 12. Context across threads

An async request can switch threads within a single HTTP lifecycle. Things bound to `ThreadLocal` are not automatically consistent across all threads:
- MDC/correlation IDs used for logs.
- `SecurityContextHolder`.
- `RequestContextHolder`.
- Transaction context.
- Certain request-scoped or tracing contexts.

When needed, use a `TaskDecorator`, security-aware executor, context propagation library, or pass data explicitly via function arguments. Do not copy passwords/tokens or let request state outlive the HTTP lifecycle.

A transaction opened on the servlet thread does not automatically run on a worker thread. With JDBC transactions, establish the service/transaction boundary on the thread actually doing the work instead of assuming context moves automatically.

## 13. Throughput, resources, and backpressure

Servlet async avoids holding a servlet thread for the **entire response wait**, yet resources remain bounded:

| Resource | What can bottleneck | How to observe |
|---|---|---|
| Container threads | Sync requests, dispatch/serialization | Active threads, thread pool saturation |
| Async executor threads | Blocking JDBC, REST clients, sleep | Pool active count, max, rejections |
| Executor queue | Tasks waiting for a worker | Queue size, task wait time |
| DB connections | Slow queries or high concurrent requests | Pool active/idle/wait |
| HTTP downstream pool | Connect/read timeouts | Connection usage, latency |
| Memory/buffers | Pending requests and streaming | Heap, response buffers, GC |
| Proxy/client timeouts | Long-lived responses | 499/502/504, disconnects, timeouts |

For example, suppose 1,000 requests simultaneously run a blocking query taking 1 second. Servlet async can release the initial container threads, but if the executor has 20 workers, only a limited number of blocking queries execute concurrently. The rest queue or get rejected. Async **does not make the database faster**.

Reactive Streams backpressure (`request(n)`) is a different mechanism and is not synonymous with `ThreadPoolTaskExecutor` queue capacity. For streaming, consider producer speed, buffering, client read speed, and cancellation.

## 14. Comparing MVC async, WebFlux, and virtual threads

| Option | Best suited when | Watch out for |
|---|---|---|
| Synchronous Spring MVC | Simple CRUD, fast I/O, legacy code | Request threads get blocked |
| MVC `Callable` | You want to offload blocking work from the container thread | Workers/queue remain bounded |
| MVC `DeferredResult` | Results arrive from events/callbacks rather than a waiting worker | Timeouts, cleanup, and late completion |
| Servlet ReadListener/WriteListener | Low-level Servlet non-blocking I/O is needed | Complex callbacks/state machines |
| Spring WebFlux | End-to-end reactive I/O, long-lived streams, non-blocking codecs | Blocking on the event loop causes stalls |
| Java 21+ virtual threads with MVC | You want linear code with lower thread overhead | Does not turn blocking I/O into non-blocking; downstream limits remain |

Spring Boot 3.3 supports virtual threads with Java 21+ and `spring.threads.virtual.enabled=true`, though this article's example uses Java 17. With virtual threads, the blocking programming model can still be a reasonable choice; watch out for pinning, connection pools, and operations.

Do not decide to migrate an MVC app to WebFlux just because request volume is high. First measure the root cause of latency: servlet threads, async queues, database/HTTP pools, CPU, serialization, or the reverse proxy.

## 15. Common mistakes

1. **Calling Servlet async “non-blocking.”** The async lifecycle only decouples waiting for the response from the initial request thread.
2. **Moving `Thread.sleep`/JDBC into a `Callable` and thinking no thread is blocked.** The worker still blocks.
3. **Forgetting `complete()`/dispatch in a native servlet.** The request stays pending until timeout.
4. **Forgetting downstream timeouts/cancellation.** Workers keep running after the request failed.
5. **Allowing pools/queues to grow without bounds.** Memory and tail latency suffer.
6. **Using `@Async void` and returning 200 right away.** Clients may receive false success.
7. **Losing MDC/security/transaction context across thread switches.** Intentional propagation is required.
8. **Misconfigured `asyncSupported` or filter dispatcher mappings.** Can cause `IllegalStateException`, missing traces, or double logging.
9. **Using `SseEmitter`/`StreamingResponseBody` and assuming all I/O is non-blocking.** Spring MVC can perform blocking writes via an executor.
10. **Attempting to write to the response after timeout/disconnect.** Can race and throw `IOException`.
11. **Running a single MockMvc call and forgetting `asyncDispatch`.** The final response has not been verified.
12. **Returning `Mono`/`Flux` from MVC and thinking the app is WebFlux.** The runtime determines the stack.
13. **Assuming virtual threads eliminate database connection limits.** Downstream bottlenecks remain.

## 16. Checklist and references

- [ ] Distinguished async request lifecycle from non-blocking I/O.
- [ ] Identified which threads run blocking code.
- [ ] Chose `Callable` for executor tasks; `DeferredResult` for event/callback completion.
- [ ] Have bounded executors, queues, rejection policies, and metrics.
- [ ] Configured appropriate MVC, client, proxy, and downstream timeouts.
- [ ] Handled completion/error/timeout/client disconnect and avoided late writes.
- [ ] Custom servlets/filters have appropriate `asyncSupported` and dispatch types.
- [ ] Addressed MDC, `SecurityContext`, and transaction context across thread hops.
- [ ] Wrote MockMvc tests with `request().asyncStarted()` and `asyncDispatch`.
- [ ] Added HTTP integration tests for timeouts and socket behavior where needed.
- [ ] Measured p95/p99 latency, pool saturation, and database connections before/after changes.

Official documentation:
- [Spring Framework — Asynchronous Requests](https://docs.spring.io/spring-framework/reference/6.1/web/webmvc/mvc-ann-async.html): `Callable`, `DeferredResult`, `WebAsyncTask`, and Servlet async lifecycle.
- [Spring Framework — MockMvc Async Tests](https://docs.spring.io/spring-framework/reference/testing/mockmvc/hamcrest/async-requests.html): testing async requests/dispatches.
- [Spring Boot 3.3 — Task Execution and Scheduling](https://docs.spring.io/spring-boot/3.3/reference/features/task-execution-and-scheduling.html): `applicationTaskExecutor`, pools, and queues.
- [Spring Boot 3.3 — Application Properties](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/): MVC async timeouts and executors.
- [Jakarta Servlet — AsyncContext API](https://jakarta.ee/specifications/servlet/6.0/apidocs/jakarta.servlet/jakarta/servlet/asynccontext): `startAsync`, `complete`, `dispatch`, timeout.
- [Jakarta Servlet — ServletOutputStream API](https://jakarta.ee/specifications/servlet/6.0/apidocs/jakarta.servlet/jakarta/servlet/servletoutputstream): `isReady`, `WriteListener`.

**Conclusion:** **Servlet async** coordinates the HTTP request lifecycle and frees the container thread while the response waits. **Non-blocking** is a property of how I/O is performed, requiring suitable sources and APIs; moving a blocking call to another thread is only asynchronous execution. With Spring MVC, measure executors, downstream dependencies, timeouts, and test results before concluding that async improves system load handling.
