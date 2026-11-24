# Callable, DeferredResult, and WebAsyncTask in Spring MVC

## 1. Why does Spring MVC support asynchronous HTTP processing?

Spring MVC runs on the Servlet stack: a request is received by a Servlet container thread, passes through the Filter chain and `DispatcherServlet`, and reaches the controller. With a synchronous endpoint, the request-handling thread typically remains occupied until the controller returns a result and the response is complete. If the controller must wait on long-running work—such as calling an external service, generating a report, or waiting for an event—that thread can remain held for the duration of the wait.

Servlet 3.0+ provides **asynchronous request processing**. Spring MVC integrates with that mechanism through return types such as `Callable`, `DeferredResult`, and `WebAsyncTask`. When a controller returns one of these types, Spring MVC can place the Servlet request into async mode so the initial request-handling thread exits the Filter/Servlet chain while the **HTTP response remains open**. Once the result is ready, the framework performs an **ASYNC dispatch** to complete the response.

~~~text
Client
  |
  v
Servlet container thread #1
  |
  v
Filters -> DispatcherServlet -> Controller
                                   |
                                   +-- returns Callable / DeferredResult / WebAsyncTask
  |
  v
request.startAsync() managed by Spring MVC infrastructure
  |
  +--> container thread #1 returns to pool, response stays open
  |
  +--> Work runs on a worker thread or completes via an external event
  |
  v
Result available -> ASYNC dispatch
  |
  v
Servlet container thread #2 (may be a different thread)
  |
  v
DispatcherServlet processes result, serializes body, writes HTTP response
~~~

Threads #1 and #2 in the diagram do not necessarily have to be different threads; the Servlet container assigns them. The important point is that **a thread does not have to stay waiting for the result throughout the entire execution of the work**.

**Do not confuse:** asynchronous handling at the request layer does not automatically turn JDBC, `RestTemplate`, `Thread.sleep`, or blocking SDKs into non-blocking I/O. With `Callable`, the work can still occupy an executor thread. Releasing a Servlet thread does not mean all other resources are freed.

This article uses **Spring Boot 3.5.x, Spring Framework 6.2.x, and Java 17+** as the baseline. The examples belong to **Spring MVC/Servlet**, not WebFlux. In Spring Boot 3.x, the Servlet API uses the `jakarta.servlet` package.

## 2. Quick comparison of the three return types

| Criterion | Callable<T> | DeferredResult<T> | WebAsyncTask<T> |
|---|---|---|---|
| Who computes the result? | Spring MVC submits the Callable to `AsyncTaskExecutor` | The application or an external event calls `setResult` / `setErrorResult` | Spring MVC runs the Callable wrapped by `WebAsyncTask` |
| Return form | A zero-argument function returning `T` | A holder object whose result state will be populated later | Holder for a Callable, plus optional timeout and executor |
| When to use | You already have a task expressible as a Callable | The result comes from an event, message, callback, or source not actively run by the controller | You want Callable behavior but need a per-request timeout or custom executor |
| Processing thread | Worker executor | Depends on event source: message listener, scheduler, worker, callback | Default or dedicated worker executor |
| Completion | `return T` or throw exception in Callable | `setResult(T)` or `setErrorResult(Object)` | `return T`, exception, or timeout/error callback |
| Per-request timeout | Use `WebAsyncTask` to configure conveniently | Constructor timeout and `onTimeout` | Constructor timeout and `onTimeout` |
| Lifecycle callbacks | Can use `CallableProcessingInterceptor` | `onTimeout`, `onError`, `onCompletion` | `onTimeout`, `onError`, `onCompletion` |
| Can serve regular HTTP responses? | Yes | Yes | Yes |

All three are suited for **a single final result**. If you want to continuously push multiple values or server-sent events (SSE), Spring MVC also provides `ResponseBodyEmitter` and `SseEmitter`; that is a different streaming problem.

These types are **controller return types**. Do not treat them as a replacement for every `TaskExecutor`, queue, transaction, retry, or business-data management mechanism.

## 3. Async lifecycle in Servlet and Spring MVC

With `Callable` or `DeferredResult`, the typical steps are:

1. The Servlet container passes the request to Filters and `DispatcherServlet`.
2. `DispatcherServlet` selects the controller; the controller returns an object representing a future result rather than writing the complete body immediately.
3. Spring MVC invokes Servlet `request.startAsync()` via its infrastructure and registers asynchronous handling.
4. The initial dispatch thread exits the Filter/Servlet chain; the client continues waiting for an HTTP response.
5. For `Callable`/`WebAsyncTask`, the framework submits the task to `AsyncTaskExecutor`. For `DeferredResult`, the application waits for an external source to complete it.
6. When the result or exception is available, Spring MVC asks the Servlet container for an ASYNC dispatch.
7. `DispatcherServlet` runs again in a new dispatch and processes the **already-produced result** without re-invoking the controller method to start a new task.
8. MVC proceeds with return-value handling, message converters, exception resolvers, and sending the response.

Spring Framework describes this mechanism under [Asynchronous Requests](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-ann-async.html).

### What you should not infer

- The HTTP connection **may still stay open** while waiting for the result; async does not turn the request into fire-and-forget.
- The request still consumes resources such as the connection, timeout state, certain contexts, and potentially memory holding payloads.
- The async dispatch uses a Servlet thread to finalize the response.
- If the work blocks a worker thread, you still have to size the worker pool and downstream connection pools.
- An HTTP request timeout does not necessarily abort a hanging JDBC call or I/O operation.
- Async processing does not alter the default contract of transactions or data stored in `ThreadLocal`.

## 4. Callable<T>: Spring MVC executes the work for you

`java.util.concurrent.Callable<T>` is a functional interface with a `call()` method returning `T` or throwing `Exception`. When a Spring MVC controller returns a `Callable`, the framework executes the `Callable` on the `AsyncTaskExecutor` configured for MVC async support.

Minimal controller example:

~~~java
@GetMapping("/callable")
public Callable<String> callable() {
    return () -> "result from worker";
}
~~~

When the controller returns the lambda, the string is not immediately written to HTTP. Spring MVC switches the request into async mode, submits the lambda to the executor, and waits for the result. Once the `Callable` completes, Spring MVC dispatches again to process the returned value.

You can return `Callable<ResponseEntity<MyDto>>`, `Callable<String>`, `Callable<ModelAndView>`, or any return value supported by Spring MVC. If the `Callable` throws an exception, Spring MVC redispatches and routes the exception through the appropriate `HandlerExceptionResolver`/`@ExceptionHandler` mechanism.

### Benefits and limits

`Callable` is suitable when the controller **knows the exact work to perform**, and that work can be wrapped in a single function—for example, computing a small report or invoking a blocking dependency through a bounded executor.

However, if the task takes 10 seconds due to blocking, one worker thread remains busy for 10 seconds. If the pool has 8 workers, at most 8 such tasks execute concurrently, barring other concurrency mechanisms. If the queue is long, requests may wait for a long time and time out before execution even begins.

Do not call `callable.call()` directly inside the controller and wrap the result to return: doing so still executes synchronously on the initial Servlet thread and defeats the purpose of an async return type.

## 5. DeferredResult<T>: result completed from elsewhere

`DeferredResult<T>` does not require the controller to supply a `Callable`. The controller creates an object representing the future result, registers any necessary callbacks, and returns the `DeferredResult` to Spring MVC. Another component completes the result via:

~~~java
deferred.setResult(value);
~~~

Or passes an exception for Spring MVC to handle:

~~~java
deferred.setErrorResult(exception);
~~~

Conceptual example:

~~~java
@GetMapping("/wait-for-event")
public DeferredResult<String> waitForEvent() {
    DeferredResult<String> deferred = new DeferredResult<>(5000L);

    eventRegistry.register(deferred);
    deferred.onCompletion(() -> eventRegistry.remove(deferred));

    return deferred;
}

// In a message listener or callback of another task:
deferred.setResult("event received");
~~~

The snippet above is **illustrative pseudocode**, requiring `eventRegistry` and an application-defined event reception mechanism. A complete example without `eventRegistry` appears in section 9.

### When is DeferredResult a better fit than Callable?

- A RabbitMQ/Kafka message or webhook signals task completion, and the controller does not own the thread computing the result.
- Another process sends a callback matched by correlation ID.
- The server needs **long polling** to return a single result when an event arrives, within a timeout window.
- A library already exposes a callback API and you want to bridge that callback into an HTTP response.

If the controller simply wants to run a function on an executor and return its result, `Callable` or `WebAsyncTask` is usually simpler. Do not use `DeferredResult` and spawn a new `Thread` per request without a bounded executor.

### setResult() and setErrorResult(): only one winner

`DeferredResult` allows setting the result successfully at most once. `setResult`/`setErrorResult` return a `boolean` indicating whether the result was accepted. If a timeout or completion has already occurred, a late callback may no longer take effect.

~~~java
boolean accepted = deferred.setResult(response);
if (!accepted) {
    // The request already has a result or its lifecycle has ended.
}
~~~

Never attempt to send two HTTP responses for the same request. If using a registry to hold pending `DeferredResult` instances, remove them on completion, timeout, or error to prevent memory leaks.

## 6. WebAsyncTask<T>: Callable with custom timeout and executor

`WebAsyncTask<V>` in package `org.springframework.web.context.request.async` is a holder for a `Callable<V>`, a timeout, and an optional executor.

Example:

~~~java
@GetMapping("/task")
public WebAsyncTask<String> task() {
    WebAsyncTask<String> result =
            new WebAsyncTask<>(3000L,
                    () -> "result from callable");

    result.onTimeout(() -> "fallback after timeout");
    result.onError(() -> "fallback after async error");
    result.onCompletion(() -> {
        // Clean up state, record metrics, or log completion.
    });

    return result;
}
~~~

`WebAsyncTask` can select a dedicated executor per request:

~~~java
new WebAsyncTask<>(3000L, chosenExecutor, callable);
~~~

Here `chosenExecutor` must be a suitable `AsyncTaskExecutor` and `callable` is a `Callable<V>`. This example only illustrates the constructor without declaring those two variables.

The callbacks:

- `onTimeout(Callable<V>)`: receives a timeout event before the `Callable` produces a result. It can return a fallback value or exception. The callback runs on a container thread and must **return quickly without blocking**.
- `onError(Callable<V>)`: handles errors during async processing at the container layer before the `Callable` finishes; **do not assume it replaces all `@ExceptionHandler` methods** for exceptions thrown by the `Callable`.
- `onCompletion(Runnable)`: invoked when the async request finishes, including via timeout or network error; suitable for cleaning up registrations/metrics. Avoid writing to the response again here.

`WebAsyncTask` does not turn a task into fire-and-forget. It remains an HTTP request with a corresponding timeout and lifecycle.

## 7. Request timeout vs. task timeout

Spring MVC involves multiple timeout layers:

| Layer | Example | Meaning |
|---|---|---|
| Servlet async timeout | `spring.mvc.async.request-timeout` or `AsyncSupportConfigurer.setDefaultTimeout` | How long the async request is allowed to wait under the Servlet lifecycle |
| Per-request timeout | `DeferredResult<>(5000L)`, `WebAsyncTask<>(3000L, ...)` | Specific limit for the created request |
| Outbound HTTP client | connect/read/response timeouts of `WebClient`, `RestClient`, or corresponding library | How long the client waits on downstream |
| Database/query timeout | Driver/query/transaction-specific | Limit on query, lock, or transaction |
| Reverse proxy timeout | Nginx/Ingress/Gateway timeouts | How long the proxy waits for an upstream HTTP response |
| Client timeout | Browser, mobile client, curl | How long the caller waits |
| Executor saturation | Worker/queue capacity | Ability to accept and execute work; not an HTTP timeout |

In Spring Boot 3.5, you can configure:

~~~yaml
spring:
  mvc:
    async:
      request-timeout: 10s
~~~

This value is the **default async request timeout** of MVC when Boot applies that configuration. If unset, the default may depend on the Servlet container. Do not claim that every Boot/Tomcat/Jetty version defaults to 10s or 30s.

You can configure it via Java:

~~~java
@Override
public void configureAsyncSupport(AsyncSupportConfigurer configurer) {
    configurer.setDefaultTimeout(10_000L);
}
~~~

This is an alternative to properties configuration when you only need one timeout. The sample project below uses **Java config** to demonstrate both the executor and timeout, so we do not add a separate YAML with conflicting values.

**Important:** `setDefaultTimeout` is in milliseconds. According to the Spring Framework Javadoc, the Servlet async timer generally starts after the main request thread exits and ends when the request is redispatched. It does not measure the entire journey across DNS, TLS, gateway, and client.

A request timeout **does not automatically cancel running work**. If a worker is calling an external service without its own timeout, the task can continue running after the client has timed out or closed the connection. Production designs must enforce timeouts/cancellation at the task or downstream level and clean up resources.

### Status codes on timeout

Spring MVC can handle `AsyncRequestTimeoutException` with a 503 response if no custom callback is present and the response has not been written. However, if the controller uses `WebAsyncTask.onTimeout` or `DeferredResult.onTimeout` to return a fallback, the status/body depends on what you return. A proxy may return 504 on its own when timing out waiting for upstream; that is not proof that Spring MVC chose HTTP 504.

Do not rely on a single status code to deduce where the timeout occurred. Inspect logs, request IDs, executor metrics, gateway metrics, and which callbacks executed.

## 8. Configuring AsyncTaskExecutor for Spring MVC in production

Spring MVC uses `AsyncTaskExecutor` to run `Callable` and `WebAsyncTask` when no custom executor is specified. Spring Framework documentation recommends configuring a suitable executor for production under load.

Spring Boot 3.5 provides **task execution auto-configuration**: when no custom `Executor` bean alters the conditions, Boot can create an `AsyncTaskExecutor`. On Java 21+ with virtual threads enabled, the executor type may differ from Java 17 and traditional thread pools. Boot also follows rules regarding the `applicationTaskExecutor` bean name for MVC integration.

**Do not just see an `Executor` bean and conclude MVC is definitely using it.** To make the choice explicit, override `WebMvcConfigurer.configureAsyncSupport` and call `setTaskExecutor` with the designated bean. The next example project does exactly that.

### Resource limits

A `ThreadPoolTaskExecutor` can tune:

- `corePoolSize`: baseline number of workers.
- `maxPoolSize`: maximum workers when needed and permitted by the queue.
- `queueCapacity`: how many tasks can wait.
- `threadNamePrefix`: helps distinguish threads during debugging.
- `rejection policy`: behavior when both pool and queue are full.
- `shutdown policy`: how to stop and await tasks during deployment.

**Common pitfall:** with standard `ThreadPoolExecutor` behavior, if the queue is unbounded, the pool may rarely grow beyond `corePoolSize`; `maxPoolSize` is not a guarantee of extra workers. Size capacity for arrival rate, processing time, timeouts, and downstream limits.

`CallerRunsPolicy` when the executor is full may run the work directly on the submitting request thread, defeating the goal of freeing the Servlet thread. `AbortPolicy` or controlled rejection makes applying backpressure easier, provided task rejection is mapped to an appropriate response (such as 503) when overloaded.

In MVC async, memory and the count of pending HTTP requests also grow as each request waits for a result. Async does not give a server unlimited concurrency.

## 9. Complete example with Spring Boot 3.5.x and Java 17+

The example creates three endpoints returning the same JSON structure, making the differences in mechanism easy to test.

### 9.1. Dependencies and project structure

Create a Maven project using Spring Boot 3.5.x and Java 17+, with a Spring Boot parent or BOM. Dependencies:

~~~xml
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
~~~

Structure:

~~~text
src/main/java/example/asyncmvc/
  AsyncMvcApplication.java
  AsyncMvcConfig.java
  AsyncDemoController.java
src/test/java/example/asyncmvc/
  AsyncDemoControllerTest.java
~~~

Spring Boot `starter-web` typically brings embedded Tomcat and Spring MVC onto the classpath; the example does not need `spring-boot-starter-webflux`.

### 9.2. Main application

File `src/main/java/example/asyncmvc/AsyncMvcApplication.java`:

~~~java
package example.asyncmvc;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class AsyncMvcApplication {

    public static void main(String[] args) {
        SpringApplication.run(AsyncMvcApplication.class, args);
    }
}
~~~

The main class sits in the same package or parent package of configurations/controllers so component scanning discovers the beans properly.

### 9.3. Configuring a bounded executor and MVC async support

File `src/main/java/example/asyncmvc/AsyncMvcConfig.java`:

~~~java
package example.asyncmvc;

import java.util.concurrent.ThreadPoolExecutor;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.AsyncTaskExecutor;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.web.servlet.config.annotation.AsyncSupportConfigurer;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration(proxyBeanMethods = false)
public class AsyncMvcConfig implements WebMvcConfigurer {

    private final AsyncTaskExecutor mvcExecutor;

    public AsyncMvcConfig(
            @Qualifier("mvcAsyncExecutor") AsyncTaskExecutor mvcExecutor) {
        this.mvcExecutor = mvcExecutor;
    }

    @Bean("mvcAsyncExecutor")
    public static ThreadPoolTaskExecutor mvcAsyncExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(64);
        executor.setThreadNamePrefix("mvc-async-");
        executor.setRejectedExecutionHandler(
                new ThreadPoolExecutor.AbortPolicy());
        return executor;
    }

    @Override
    public void configureAsyncSupport(AsyncSupportConfigurer configurer) {
        configurer.setTaskExecutor(mvcExecutor);
        configurer.setDefaultTimeout(10_000L);
    }
}
~~~

Key points:

- The `mvcAsyncExecutor` bean is a `ThreadPoolTaskExecutor`. Spring manages bean initialization and destruction, avoiding manual thread creation per request.
- The bean factory method is `static` to avoid circular dependencies when the configuration class itself injects the executor it declares.
- `configureAsyncSupport` uses that exact executor to run `Callable` tasks managed by Spring MVC; the default timeout is 10,000 ms.
- Finite `queueCapacity` prevents holding unbounded work under heavy load.
- The code illustrates intentional configuration; in real systems, benchmark and choose pool sizes matching CPU, I/O, and downstream capacity.

If the project has multiple `Executor` beans, injecting with `@Qualifier` and explicitly calling `setTaskExecutor` as shown avoids picking the wrong bean. Do not add `@EnableWebMvc` solely to configure async; `WebMvcConfigurer` suffices to add customization while preserving Boot MVC auto-configuration.

### 9.4. Controller with Callable, DeferredResult, and WebAsyncTask

File `src/main/java/example/asyncmvc/AsyncDemoController.java`:

~~~java
package example.asyncmvc;

import java.util.concurrent.Callable;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.core.task.AsyncTaskExecutor;
import org.springframework.core.task.TaskRejectedException;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.context.request.async.DeferredResult;
import org.springframework.web.context.request.async.WebAsyncTask;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/api/async")
public class AsyncDemoController {

    private static final Logger log =
            LoggerFactory.getLogger(AsyncDemoController.class);

    private final AsyncTaskExecutor executor;

    public AsyncDemoController(
            @Qualifier("mvcAsyncExecutor") AsyncTaskExecutor executor) {
        this.executor = executor;
    }

    public record Reply(String source, String status) {}

    @GetMapping("/callable")
    public Callable<ResponseEntity<Reply>> callable() {
        return () -> ResponseEntity.ok(
                new Reply("callable", "ok"));
    }

    @GetMapping("/deferred")
    public DeferredResult<ResponseEntity<Reply>> deferred() {
        DeferredResult<ResponseEntity<Reply>> result =
                new DeferredResult<>(5_000L);

        result.onTimeout(() -> result.setErrorResult(
                new ResponseStatusException(
                        HttpStatus.SERVICE_UNAVAILABLE,
                        "Result was not ready")));

        result.onError(error -> {
            log.warn("Async request error", error);
        });

        result.onCompletion(() ->
                log.debug("Deferred request completed"));

        try {
            executor.execute(() -> {
                try {
                    boolean accepted = result.setResult(
                            ResponseEntity.ok(
                                    new Reply("deferred", "ok")));
                    if (!accepted) {
                        log.debug("Deferred result arrived too late");
                    }
                } catch (RuntimeException ex) {
                    result.setErrorResult(ex);
                }
            });
        } catch (TaskRejectedException ex) {
            result.setErrorResult(
                    new ResponseStatusException(
                            HttpStatus.SERVICE_UNAVAILABLE,
                            "Async worker is busy", ex));
        }

        return result;
    }

    @GetMapping("/web-task")
    public WebAsyncTask<ResponseEntity<Reply>> webTask() {
        Callable<ResponseEntity<Reply>> work = () ->
                ResponseEntity.ok(
                        new Reply("webAsyncTask", "ok"));

        WebAsyncTask<ResponseEntity<Reply>> task =
                new WebAsyncTask<>(3_000L, executor, work);

        task.onTimeout(() ->
                ResponseEntity.status(
                        HttpStatus.SERVICE_UNAVAILABLE)
                        .body(new Reply("webAsyncTask", "timeout")));

        task.onError(() ->
                ResponseEntity.status(
                        HttpStatus.INTERNAL_SERVER_ERROR)
                        .body(new Reply("webAsyncTask", "error")));

        task.onCompletion(() ->
                log.debug("WebAsyncTask request completed"));

        return task;
    }
}
~~~

Notable points:

- `/callable`: Spring MVC automatically submits the `Callable` to the registered executor.
- `/deferred`: the application submits a task via the executor; the worker calls `setResult`. This pattern deliberately shows that **the application** decides when `DeferredResult` completes. If you only need to run a `Callable`, `/callable` is simpler.
- `/deferred` has a dedicated 5-second timeout using `onTimeout` to return a `ResponseStatusException` with HTTP 503. `setResult` returns `false` if the result arrives too late or has already been set.
- `/web-task`: `WebAsyncTask` wraps the `Callable`, uses the specified executor, sets a 3-second timeout, and attaches timeout/error/completion callbacks.
- No `Thread.sleep` appears in the runtime code: the examples return quickly, are easy to test, and avoid brittle deadline simulations.
- `Reply` responses are serialized to JSON by Jackson via `starter-web`.
- `TaskRejectedException` represents an overloaded pool; `DeferredResult` explicitly maps it to 503. With `Callable`/`WebAsyncTask`, you still need rejection-handling policies at the framework/API level if required.

**Important:** `WebAsyncTask.onError` must not be treated as a catch-all replacing `@ExceptionHandler`. Exceptions thrown directly by the `Callable` generally flow through MVC exception handling when the async result is dispatched. In real systems, log exceptions, classify domain errors, and return secure responses.

### 9.5. Running the application

In a Maven project with Maven Wrapper:

~~~bash
./mvnw spring-boot:run
~~~

Windows PowerShell:

~~~powershell
.\mvnw.cmd spring-boot:run
~~~

Unless configured otherwise, the embedded servlet server listens on HTTP port 8080. Call:

~~~bash
curl -i http://localhost:8080/api/async/callable
curl -i http://localhost:8080/api/async/deferred
curl -i http://localhost:8080/api/async/web-task
~~~

Without timeout or executor saturation, expected results are HTTP 200, `Content-Type` `application/json`, and bodies **equivalent** to:

~~~json
{"source":"callable","status":"ok"}
~~~

~~~json
{"source":"deferred","status":"ok"}
~~~

~~~json
{"source":"webAsyncTask","status":"ok"}
~~~

These are the **expected JSON bodies**, not the application's full stdout. Headers, logs, property ordering, and thread names vary by environment. There is no guarantee that each request uses a predetermined thread name; inspect logs/traces to observe threads.

## 10. MockMvc: properly testing both phases of an async request

`MockMvc` typically simulates MVC requests without opening a real HTTP socket. With async controllers, **`asyncDispatch` is required** to finish processing in tests.

File `src/test/java/example/asyncmvc/AsyncDemoControllerTest.java`:

~~~java
package example.asyncmvc;

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
class AsyncDemoControllerTest {

    @Autowired
    MockMvc mvc;

    private void assertAsyncResult(
            String path, String expectedSource) throws Exception {

        MvcResult pending = mvc.perform(get(path))
                .andExpect(request().asyncStarted())
                .andReturn();

        mvc.perform(asyncDispatch(pending))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.source").value(expectedSource))
                .andExpect(jsonPath("$.status").value("ok"));
    }

    @Test
    void callableCompletes() throws Exception {
        assertAsyncResult("/api/async/callable", "callable");
    }

    @Test
    void deferredCompletes() throws Exception {
        assertAsyncResult("/api/async/deferred", "deferred");
    }

    @Test
    void webAsyncTaskCompletes() throws Exception {
        assertAsyncResult("/api/async/web-task", "webAsyncTask");
    }
}
~~~

Since all three endpoints return async results:

1. `mvc.perform(get(path))` starts the request and verifies `request().asyncStarted()`.
2. `MvcResult` holds the initial async request state.
3. `asyncDispatch(pending)` waits for the async result and executes a dispatch inside MockMvc.
4. Only after the dispatch are the HTTP status and final JSON body asserted.

Run:

~~~bash
./mvnw test
~~~

On Windows:

~~~powershell
.\mvnw.cmd test
~~~

If you only call `perform(get(...)).andExpect(content().string(...))` on the first pass, the test may observe an incomplete response instead of the final JSON. This testing pattern follows [Spring Framework MockMvc Async Requests](https://docs.spring.io/spring-framework/reference/6.2/testing/mockmvc/hamcrest/async-requests.html).

### Testing timeouts without flaky sleeps

Do not simply add `Thread.sleep(5000)` to a unit test with a 3000 ms timeout and hope every machine/CI yields the same outcome. MockMvc is not a real Servlet container, and timeout simulation can differ from an actual server. To test timeouts, exceptions, client disconnects, and reverse proxies, use integration tests on `RANDOM_PORT` with real embedded Tomcat/Jetty and controlled synchronization (`CountDownLatch`, `CompletableFuture`, or a fake external service with explicit signaling).

Write dedicated tests for:

- Exceptions thrown from a `Callable` and `@ControllerAdvice` handling them.
- `DeferredResult.setErrorResult` and final status.
- `WebAsyncTask.onTimeout` fallback.
- Full worker pool, task rejection, and load bursts.
- Client disconnect and cleaning up pending registries.
- Executor/DB shutdown during deployment.

Never infer production timeout behavior from tests that call controller methods like plain Java functions bypassing `DispatcherServlet`.

## 11. DeferredResult completed by external events: real-world pattern

`DeferredResult` is most useful when results arrive from an external source instead of merely running a `Runnable` directly. A common design:

~~~text
HTTP GET /jobs/{id}/wait
          |
          v
Controller creates DeferredResult, sets timeout
          |
          v
Registry.put(jobId, deferred)
          |
          v
Controller returns DeferredResult, Servlet thread is released
          |
          v
Message listener receives JobCompleted(jobId, result)
          |
          v
Registry.remove(jobId) -> deferred.setResult(result)
          |
          v
Spring MVC ASYNC dispatch -> HTTP response
~~~

Registry API sketch:

~~~java
// Conceptual snippet, not a standalone Java class:
ConcurrentMap<String, DeferredResult<ResponseEntity<JobReply>>>
        pending = new ConcurrentHashMap<>();

DeferredResult<ResponseEntity<JobReply>> result =
        new DeferredResult<>(15_000L);

DeferredResult<ResponseEntity<JobReply>> previous =
        pending.putIfAbsent(jobId, result);

if (previous != null) {
    // Choose a clear policy: reject, allow multiple waiters, or cancel the older session.
}

result.onCompletion(() -> pending.remove(jobId, result));
~~~

With one client waiting per `jobId`, the pending map must handle concurrency and clean up properly. If multiple clients can wait on the same job, a `jobId` -> single `DeferredResult` map is insufficient; use a thread-safe collection/registration and per-request cleanup.

When the completion message arrives:

~~~java
DeferredResult<ResponseEntity<JobReply>> waiting =
        pending.remove(jobId);
if (waiting != null) {
    waiting.setResult(ResponseEntity.ok(jobReply));
}
~~~

These snippets explain the architecture; `JobReply`, `jobId`, `jobReply`, queue/message listener, and synchronization mechanisms must be defined by your system. They do not replace the complete runnable example in section 9.

**Races to handle:**

- Event arrives before the HTTP request registers the `DeferredResult`: maintain durable job state so the client can query again rather than relying solely on the in-memory pending map.
- Timeout occurs right as the event arrives: `setResult` may return `false`. Job data should live in independent storage.
- Client disconnects: `onCompletion` must clean up the pending registry.
- Application restarts: in-memory pending maps are lost; if durability is needed, persist job state in a DB/cache/queue.
- Same `jobId` from two users: never leak a result to the wrong user; enforce authentication/authorization and job ownership checks.

This is why `DeferredResult` usually pairs with correlation IDs, idempotency policies, and durable state storage.

## 12. AsyncHandlerInterceptor and Filter lifecycle differ from synchronous requests

A regular `HandlerInterceptor` has:

- `preHandle` before the controller.
- `postHandle` after the handler runs and before rendering where applicable.
- `afterCompletion` when dispatch processing completes.

With an async controller, the **initial dispatch** may skip `postHandle` and `afterCompletion` along the normal synchronous path. If an interceptor implements `AsyncHandlerInterceptor`, it can receive `afterConcurrentHandlingStarted` when the request transitions to async. The subsequent ASYNC dispatch may re-run the appropriate interceptor steps before finalizing the response.

Skeleton example:

~~~java
public final class TimingInterceptor implements AsyncHandlerInterceptor {

    @Override
    public boolean preHandle(
            HttpServletRequest request,
            HttpServletResponse response,
            Object handler) {
        return true;
    }

    @Override
    public void afterConcurrentHandlingStarted(
            HttpServletRequest request,
            HttpServletResponse response,
            Object handler) {
        // The first dispatch switched to async;
        // do not conclude that the HTTP request has finished.
    }

    @Override
    public void afterCompletion(
            HttpServletRequest request,
            HttpServletResponse response,
            Object handler,
            Exception exception) {
        // Can clean up request resources when the dispatch completes.
    }
}
~~~

This skeleton requires imports for `jakarta.servlet.http.HttpServletRequest`/`Response` and `org.springframework.web.servlet.AsyncHandlerInterceptor`; it is not a standalone Java file.

If an interceptor records a start time in a request attribute, do not assume `preHandle` runs only once for the entire HTTP exchange. Check `REQUEST`/`ASYNC` dispatch types to avoid overwriting the start time and corrupting metrics.

### Filter asyncSupported and DispatcherType.ASYNC

Servlet async requires all involved Servlets and Filters to declare `asyncSupported=true`. For custom Filter registrations, check `DispatcherType.REQUEST` and `DispatcherType.ASYNC` configuration when the filter needs to participate in async dispatches.

However, **participating in async dispatches** and **supporting async requests** are not the same thing:

- `asyncSupported=true` indicates the Filter can sit in the chain of a request that uses asynchronous processing.
- Registration dispatcher types control whether the Filter is invoked during the ASYNC dispatch.
- `OncePerRequestFilter` has default logic to avoid re-running on async dispatches, depending on `shouldNotFilterAsyncDispatch()` and registration settings.

Avoid accidentally running authentication logic, request logging, or body reading twice simply due to async dispatch. With Spring Security, inspect filter chains across dispatch types and how security contexts are restored.

## 13. ThreadLocal, MDC, SecurityContext, and transactions do not propagate everywhere automatically

When code moves from a Servlet thread to an executor worker thread, `ThreadLocal` is an easy place to make mistakes. Values such as MDC logging context, correlation IDs, `LocaleContextHolder`, `RequestContextHolder`, or custom `ThreadLocal`s do not automatically appear on all other threads.

Some Spring integrations provide specific context propagation. For example, Spring Security integrates with `Callable` through MVC async support and `WebAsyncManagerIntegrationFilter`. Even so, **do not treat that as a guarantee that all `ThreadLocal`/security data propagates into every `Runnable` your application submits itself**.

For a `DeferredResult` completed inside a message listener or scheduler, the original request context may no longer exist on that thread. When user/correlation data is needed:

1. Extract authorized request metadata into immutable data.
2. Pass that data explicitly to the job/event.
3. For observability/trace context, use a `TaskDecorator` or appropriate context propagation mechanism.
4. Clear MDC and custom `ThreadLocal` values when the worker finishes, including on exceptions.

### Transactions and persistence

Do not assume `@Transactional` on a controller wraps the entire `Callable` body running later on an executor. Transactions are typically bound to the thread invoking the service and transaction interceptor. If async work needs a transaction:

~~~java
@Service
public class BookingService {

    @Transactional
    public Receipt createBooking(CreateBookingCommand command) {
        // Place business logic and database work at the service boundary.
    }
}
~~~

This skeleton needs `Receipt`, `CreateBookingCommand`, and imports; in a real application, ensure the service bean is called through a Spring proxy with an appropriate transaction manager.

Invoke the transactional service from the thread actually performing the work, and test rollback/commit behavior. Never rely on an `EntityManager`, database session, or transactional `ThreadLocal` automatically migrating from the Servlet thread to a worker.

## 14. Exceptions from Callable, DeferredResult, and WebAsyncTask

### Callable throws an exception

~~~java
@GetMapping("/failure")
public Callable<String> failure() {
    return () -> {
        throw new IllegalStateException("simulated failure");
    };
}
~~~

Spring MVC treats the exception as the async processing result, redispatches, and passes it through standard exception handling. If a `@RestControllerAdvice` catches a matching exception, the handler can produce a `ProblemDetail`/`ResponseEntity`. Do not leak sensitive raw exception messages or stack traces to clients.

### DeferredResult sends an error result

~~~java
DeferredResult<ResponseEntity<String>> result =
        new DeferredResult<>(5000L);

result.setErrorResult(
        new ResponseStatusException(
                HttpStatus.SERVICE_UNAVAILABLE,
                "external service unavailable"));
~~~

This snippet requires imports; when the framework processes the error result during async dispatch, `ResponseStatusException` can be rendered into the corresponding response.

### WebAsyncTask timeout fallback

~~~java
WebAsyncTask<String> task =
        new WebAsyncTask<>(2000L, () -> "slow result");

task.onTimeout(() -> "fallback");
~~~

If a timeout happens before the task finishes, the callback can supply a fallback result. Do not assume the timeout callback cancels the thread, rolls back a transaction, or prevents side effects. Already-running work can continue until it finishes or is explicitly canceled by a designed mechanism.

With `WebAsyncTask.onError`, you can return an alternative value for errors occurring in async processing before the `Callable` completes. It is not a catch-all for every exception inside business methods; verify exception-handler routing along the actual execution path.

### Double completion

`DeferredResult.setResult` and `setErrorResult` return a `boolean`. If the timeout callback already completed the response and a message listener calls `setResult` afterward, the return value may be `false`. Do not log a late callback as an HTTP success.

If the client already disconnected, trying to write the response can trigger an `IOException`; with streaming, disconnects may only be noticed when writing. Completion and cleanup callbacks should not depend on the client still reading the response.

## 15. Measurement and load limits

Suppose an application receives 200 HTTP requests per second, and each blocking task takes 2 seconds on average. Without optimization, the in-flight task count is roughly 400 by Little's Law (assuming steady state and representative latency). Switching to `Callable` frees Servlet threads to accept more requests, yet **the executor still has to process that workload**.

With an 8-worker pool and 2-second blocking tasks, sequential worker throughput is roughly 4 requests/second (ignoring overhead)—far below the 200/s arrival rate. The queue will grow or requests will be rejected, so async is not a cure for overload when downstream lacks capacity.

Metrics to monitor:

- Executor active threads, queue depth, completed tasks, rejection counts.
- HTTP active requests, Servlet async timeouts, p50/p95/p99 latency.
- Outbound HTTP/database latency and connection pool saturation.
- Client disconnect rate, proxy timeouts, late `DeferredResult` completions.
- 503/504 rates, exception counts, CPU, memory, and GC.
- Pending requests waiting on external events when using a `DeferredResult` registry.

**Four limits must work together:** concurrency limit, queue capacity, task/dependency timeout, and HTTP async timeout. Raising only the timeout can pile up thousands of waiting requests.

If you need streaming or high-scale end-to-end non-blocking I/O, evaluate Spring WebFlux, reactive clients, and system capabilities rather than merely changing the return type to `Callable`.

## 16. Comparing Servlet async, @Async, and WebFlux

| Mechanism | Scope | Can return an HTTP response from an open request? | Key takeaway |
|---|---|---|---|
| Spring MVC `Callable` | Servlet HTTP controller | Yes | MVC manages the executor and ASYNC dispatch |
| Spring MVC `DeferredResult` | Servlet HTTP controller | Yes | Application decides when to complete the result |
| Spring MVC `WebAsyncTask` | Servlet HTTP controller | Yes | `Callable` + per-request timeout/executor/callbacks |
| Spring `@Async` | Spring bean method | Not automatically just from adding the annotation | Executes method via task executor/proxy; does not alter Servlet async contract |
| `CompletableFuture` | Java async abstraction | Can be adapted by MVC in controllers depending on return-type support | Does not guarantee non-blocking I/O |
| Spring WebFlux `Mono`/`Flux` | Reactive HTTP pipeline | Yes | Request/response contract and I/O differ from Servlet MVC |

**`@Async` is not equivalent to a `Callable` return type.** `@Async` on a service causes the method to run via an executor when enabled and called through a Spring proxy; it does not put `HttpServletRequest` into Servlet async mode. Conversely, a controller returning `Callable` works without `@EnableAsync`.

**MVC async is not WebFlux.** Spring MVC still uses `DispatcherServlet`, Filters, and the Servlet async lifecycle. WebFlux uses `DispatcherHandler`, reactive request/response abstractions, and typically Reactor Netty. Spring MVC can support certain reactive return types when the right dependencies are present, but that does not turn all Servlet I/O into non-blocking I/O.

## 17. Troubleshooting common issues

| Symptom | Possible cause | How to check or fix |
|---|---|---|
| Controller returns `Callable` yet thread pool still stalls | Blocking work occupies workers too long | Measure executor queue/active, add downstream timeouts, tune pool |
| Async request receives 503 when waiting long | Servlet async timeout or custom fallback | Identify timeout layer; check callbacks and proxy |
| Proxy reports 504 before server | Proxy timeout shorter than server/task timeout | Align timeouts and response policies |
| `DeferredResult` never returns a response | Nobody calls `setResult`/`setErrorResult` | Inspect registry/callbacks/timeouts; always have a fallback |
| Registry memory grows continuously | Pending results not removed on timeout/disconnect | Clean up in `onCompletion` and error paths |
| `setResult` returns `false` | Timeout/completion already happened or result already set | Check for races; do not emit a second response |
| `WebAsyncTask` callbacks are slow | `onTimeout`/`onError` perform blocking I/O on container thread | Make callbacks return fast; move heavy work elsewhere |
| `TaskRejectedException` | Executor/queue is full | Tune pool/capacity, return 503 deliberately, measure saturation |
| MVC still executes synchronously despite `Callable` variable | Controller calls `call()` directly before returning | Return the `Callable` object to MVC without executing it yourself |
| `@Transactional` does not carry onto worker | Transaction/thread context does not propagate automatically | Place `@Transactional` at the service boundary running on the worker |
| MDC or `SecurityContext` disappears | `ThreadLocal` does not transfer across all threads | Use proper propagation or pass metadata explicitly |
| Filter does not run on ASYNC dispatch | `DispatcherType` or `OncePerRequestFilter` settings | Check `asyncSupported`, registration, and callbacks |
| Filter fails async requests at startup | Filter/Servlet does not support async | Enable `asyncSupported` across the whole chain when needed |
| `HandlerInterceptor` measures twice | `REQUEST` and `ASYNC` dispatches have different lifecycles | Use `AsyncHandlerInterceptor` and request attributes carefully |
| MockMvc test sees an empty response | Forgot `asyncDispatch` | Assert `asyncStarted`, then call `asyncDispatch` before checking body |
| `Callable` fails but response is unexpected | Exception resolver/advice not handling async error | Test exceptions through the full MVC lifecycle |
| Client disconnects yet task keeps running | Async completion does not equal task cancellation | Add cancellation/timeouts at the work source and clean up |
| Throughput does not increase | Downstream bottleneck or small pool | Optimize dependencies, caching, queues, and capacity first |

**Never use `Thread.sleep` to work around races or build business synchronization.** In tests, use `CountDownLatch`, `CompletableFuture`, or a fake message listener with explicit signals. In production, use message correlation, transactions, and managed shared state.

## 18. Checklist for taking MVC async to production

1. The application truly runs Spring MVC/Servlet; do not confuse it with WebFlux-only.
2. Servlets and involved Filters support async requests.
3. `AsyncTaskExecutor` has bounded workers/queue and a deliberate rejection policy.
4. `Callable` fits request-initiated work; `DeferredResult` fits external completion; `WebAsyncTask` is used when per-request timeout/executor is needed.
5. Clear HTTP async timeouts, dependency timeouts, and proxy timeouts are configured.
6. Workers/jobs support cancellation or cleanup on timeout/client disconnect where the work allows it.
7. Any `DeferredResult` registry is leak-free and handles events arriving early or late.
8. Never assume `ThreadLocal`, transactions, MDC, or `SecurityContext` propagate automatically across every executor.
9. Never run blocking code on the container thread inside `WebAsyncTask` timeout callbacks.
10. Write MockMvc tests with `asyncDispatch` and integration tests on a real Servlet container.
11. Test exceptions, timeouts, task rejection, client disconnects, and overload.
12. Monitor executor saturation, active requests, p95/p99 latency, and HTTP 5xx rates.
13. Enforce authentication/authorization for long polling and correlation IDs.
14. Never return raw stack traces or internal messages from worker exceptions.
15. When sending multiple events, consider `SseEmitter`/`ResponseBodyEmitter` instead of chaining endless `DeferredResult` calls.

## 19. Official documentation

- [Spring Framework 6.2 – Asynchronous Requests](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-ann-async.html): `Callable`, `DeferredResult`, `WebAsyncTask`, ASYNC dispatch, error handling, and Servlet async configuration.
- [Spring Framework 6.2 – AsyncSupportConfigurer](https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/web/servlet/config/annotation/AsyncSupportConfigurer.html): `setTaskExecutor`, `setDefaultTimeout`, `CallableProcessingInterceptor`/`DeferredResultProcessingInterceptor`.
- [Spring Framework 6.2 – WebAsyncTask Javadoc](https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/web/context/request/async/WebAsyncTask.html): constructors and lifecycle callbacks.
- [Spring Framework 6.2 – DeferredResult Javadoc](https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/web/context/request/async/DeferredResult.html): `setResult`, `setErrorResult`, `onTimeout`/`onError`/`onCompletion`.
- [Spring Framework 6.2 – MockMvc Async Requests](https://docs.spring.io/spring-framework/reference/6.2/testing/mockmvc/hamcrest/async-requests.html): `request().asyncStarted()` and `asyncDispatch()`.
- [Spring Boot 3.5 – Task Execution and Scheduling](https://docs.spring.io/spring-boot/3.5/reference/features/task-execution-and-scheduling.html): auto-configured `AsyncTaskExecutor`, `applicationTaskExecutor`, and virtual threads on Java 21+.
- [Spring Boot 3.5 – Common Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html): `spring.mvc.async.request-timeout`.

## 20. Conclusion

**`Callable`** lets Spring MVC actively execute work on an executor; **`DeferredResult`** lets a source outside the controller decide when the HTTP response is ready; **`WebAsyncTask`** wraps a `Callable` with intentional timeout, executor, and callbacks. All three leverage Servlet async to release the initial request-receiving thread and finalize the response via an ASYNC dispatch.

For a system to perform well, choosing a return type is only the start—you must configure executors, multi-layer timeouts, error and late-completion handling, context/transaction boundaries, pending-request management, and proper lifecycle tests. MVC async reduces holding Servlet threads while waiting, but it does not replace capacity planning and does not turn blocking work into non-blocking I/O.