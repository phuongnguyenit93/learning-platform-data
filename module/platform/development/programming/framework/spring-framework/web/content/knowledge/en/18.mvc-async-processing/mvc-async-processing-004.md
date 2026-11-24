# ASYNC Dispatch Flow and Result or Exception Handling in Spring MVC

## 1. Goal: properly understanding the two passes of an HTTP request

In a traditional Servlet application, an HTTP request usually occupies a servlet container thread until the controller returns a result and the response finishes. However, some work must wait for I/O, an event from another system, or longer-than-usual processing. Spring MVC has **Servlet asynchronous request processing**: return the servlet thread before a result exists, keep the HTTP response open, and resume processing when the result is ready.

Example endpoint using `Callable`:

~~~java
@GetMapping("/report")
public Callable<ResponseEntity<String>> report() {
    return () -> ResponseEntity.ok("ready");
}
~~~

When the controller **returns the `Callable` object**, the string `"ready"` is **not yet** the final HTTP response at that point. Spring MVC:
1. Puts the request into asynchronous mode via the Servlet async API.
2. Runs the `Callable` on an `AsyncTaskExecutor`.
3. Returns the servlet container thread serving the request back to the pool while waiting.
4. When the task finishes, **dispatches the request again with `DispatcherType.ASYNC`**.
5. `DispatcherServlet` processes the **stored result**, without calling the controller method again to re-run the task.
6. Resolves the return value or exception, writes the response, and ends the async request.

**Important:** a single HTTP request can have multiple internal phases/dispatches, yet the client still sees **one HTTP response**. `ASYNC` is a Servlet dispatch type; it does **not** mean the client sent an `ASYNC` HTTP method.

### After this lesson, you will be able to

- Draw the order `REQUEST` → `startAsync` → worker/event → `ASYNC` → response.
- Distinguish the Servlet container thread from the thread running `Callable` or calling `DeferredResult.setResult`.
- Use `Callable<T>`, `DeferredResult<T>`, and `WebAsyncTask<T>` properly for a single asynchronous result.
- Understand how successful results and errors pass through `HandlerMethodReturnValueHandler`, `HttpMessageConverter`, and `HandlerExceptionResolver` / `@ExceptionHandler`.
- Distinguish exceptions from workers vs. timeouts, client disconnects, and exceptions after the response has committed.
- Understand `AsyncHandlerInterceptor`, filter dispatcher types, Spring Security context, cleanup, and executor/timeout configuration.
- Write Java 17+ Spring Boot 3.3.5 examples and MockMvc tests with `request().asyncStarted()`, `asyncDispatch(...)`, and final HTTP assertions.
- Know the differences between MVC async, Java `@Async`, and Spring WebFlux/reactive processing.

The lesson focuses on the **Spring MVC Servlet stack**; do not interpret this mechanism as WebFlux. The illustrative API names match Spring Framework 6.1.x in Spring Boot 3.3.5.

## 2. Why returning `Callable` does not mean returning the response immediately

Look at two controllers:

~~~java
@GetMapping("/sync")
public String sync() {
    return slowService.load();
}

@GetMapping("/async")
public Callable<String> async() {
    return () -> slowService.load();
}
~~~

These are two illustrative fragments (without the enclosing class and `slowService` bean). `sync` waits for `load()` to finish on the servlet request thread. `async` delegates the work to an executor; the servlet thread can return to serve other requests while the task runs.

However, **I/O operations inside the Callable can still be blocking** and occupy a **worker thread**. MVC async does not automatically make blocking JDBC/HTTP calls non-blocking. The benefit is avoiding holding container threads while waiting; the cost is a thread pool, queue, context propagation, and an additional dispatch.

If you call `Thread.sleep` or a synchronous REST client for 10 seconds inside a Callable, you still occupy an executor thread for 10 seconds. You only moved where the waiting happens, without "eliminating" wait time. For performance, measure threads, queues, and latency before and after.

## 3. Servlet cycle: `REQUEST`, async mode, and `ASYNC`

### 3.1. Diagram by stage

~~~text
Client           Servlet container          Spring MVC             Async executor/event
  |                      |                       |                          |
  | GET /api/async/...   |                       |                          |
  |--------------------->|  DispatcherType.REQUEST                         |
  |                      |-- Filters ---------->|                          |
  |                      |                       | HandlerMapping            |
  |                      |                       | Controller returns        |
  |                      |                       | Callable/DeferredResult  |
  |                      |                       | startAsync()             |
  |                      |                       |------------------------->| Callable worker
  |                      |<-- Filter/Servlet exit|                          |
  |                      |  request thread free  |                          |
  |                      |  response remains open|                          |
  |                      |                       |                 compute result
  |                      |<-----------------------------------------------  |
  |                      |  async dispatch       |                          |
  |                      |  DispatcherType.ASYNC |                          |
  |                      |-- Filters* ---------->| DispatcherServlet again |
  |                      |                       | consume saved result     |
  |                      |                       | serialize OR resolve err |
  |<---------------------| response completes    |                          |
~~~

The `Filters*` marker reminds you that **only filters mapped for dispatcher type `ASYNC`** and matching dispatch rules participate in the second pass. A `OncePerRequestFilter` also has logic deciding whether to skip async dispatches. Do not assume every filter runs twice, or that no filter runs a second time.

### 3.2. Underlying Servlet API

At the Servlet level, `HttpServletRequest.startAsync()` returns an `AsyncContext` and puts the request into async mode (if the servlet/filter chain permits it). Key effects:
- The Servlet can exit the initial dispatch.
- The response stays open for a later result.
- The application/container can redispatch or complete.
- The async request can time out and receive `AsyncListener` notifications.

Spring MVC manages these operations via infrastructure such as `WebAsyncManager`, `AsyncWebRequest`, and argument/return-value processing. **Do not call `request.startAsync()` yourself inside a controller that already returns `Callable`/`DeferredResult`**: mixing two independent management paths easily causes double-dispatches, race conditions, or incomplete responses.

### 3.3. One request or two requests?

There is **one** HTTP request from the client. Inside the server, there are two Servlet dispatches:
- `REQUEST`: receives the request, selects the handler, controller returns an async handle.
- `ASYNC`: resumes once a result or error is available.

On the ASYNC dispatch, Spring MVC still resolves the corresponding handler mapping to continue the pipeline, but **does not invoke the controller method again**; the result was saved by `WebAsyncManager` for return-value/exception resolvers to process. Therefore, do not put business logic in an MVC interceptor `preHandle` assuming it runs strictly once per request: account for async redispatches.

### 3.4. Distinguishing Servlet dispatch from HTTP redirect/forward

| Mechanism | Does the client send a new request? | Meaning |
| --- | --- | --- |
| `DispatcherType.REQUEST` | Client sends the initial request | Normal HTTP request handling |
| `DispatcherType.ASYNC` | No | Container resumes the same logical HTTP request after async completion |
| `DispatcherType.FORWARD` | Not a new HTTP request | Internal Servlet forward |
| HTTP `302 Location` | Browser/client usually sends a new request following the redirect | Another HTTP round-trip |
| `DispatcherType.ERROR` | Not necessarily | Container error dispatch per configuration |

An `ASYNC` dispatch is not a redirect, not a server push, and not a message queue acknowledgement. If you want the client to come back and poll status, that is a different **202 Accepted + status endpoint** design, not an internal MVC async dispatch.

## 4. `Callable<T>`: Spring manages the worker and resumes the result

### 4.1. Main processing flow

When a handler returns `Callable<T>`, Spring:
1. Accepts the return value as an asynchronous computation.
2. Places the request into async mode.
3. Submits the `Callable` to the MVC-configured `AsyncTaskExecutor`.
4. Lets `DispatcherServlet` and initial-pass filters exit.
5. The worker runs `Callable.call()` and captures the result or `Throwable`.
6. Stores the result in the async manager and asks the container for an ASYNC dispatch.
7. For a result, processes the return value just as if the controller returned that object directly.
8. For an exception, routes through Spring MVC exception handling.

Example:

~~~java
@GetMapping("/callable")
public Callable<ResponseEntity<String>> callable() {
    return () -> ResponseEntity.ok("worker complete");
}
~~~

Spring MVC can serialize `"worker complete"` into the response after the dispatch. **The ResponseEntity is not written to completion immediately when the controller returns the Callable**.

### 4.2. Results do not depend on thread identity

Three different threads may be observed:
- `T1`: container thread handling REQUEST.
- `T2`: executor worker running Callable.
- `T3`: container thread handling ASYNC.

T1 ≠ T3 is not required in every runtime: a thread pool may reuse the same thread. The essence is **dispatch context split into phases**, not necessarily three distinct thread names. Do not treat thread names/order as an API contract or hard assertion.

### 4.3. Are exceptions thrown by Callable on another thread lost?

No, if the exception occurs **inside a Callable managed by Spring MVC**, Spring captures it as the async result and dispatches again. On the ASYNC pass, it passes through `HandlerExceptionResolver` and `@ExceptionHandler` just like an exception in a synchronous controller.

~~~java
@GetMapping("/callable/fail")
public Callable<String> fail() {
    return () -> {
        throw new IllegalStateException("simulated");
    };
}
~~~

This is an explanatory fragment only; production code should not expose internal `IllegalStateException` verbatim to clients. A `@RestControllerAdvice` maps known public exceptions to safe statuses/bodies; unexpected errors become 500 and are logged safely server-side.

### 4.4. Unlike spawning threads manually

Do not write:

~~~java
@GetMapping("/bad")
public String bad() {
    new Thread(() -> expensiveWork()).start();
    return "done";
}
~~~

The code above **returns the HTTP response before knowing whether the work succeeded or failed**, which is not an MVC async response. It also spawns uncontrolled threads and lets exceptions fall elsewhere. If the goal is genuinely long jobs, use a task queue/job table and an endpoint returning 202 + job ID, rather than holding HTTP connections open indefinitely.

## 5. `DeferredResult<T>`: a result arriving from an external source

With `Callable`, Spring MVC knows the computation to submit. With `DeferredResult`, the controller returns a **holder** for a result that will be set later by the application: a message listener, a service callback, workflow completion, a scheduler, or a worker you coordinate.

~~~java
@GetMapping("/deferred")
public DeferredResult<String> deferred() {
    DeferredResult<String> result = new DeferredResult<>(5_000L);

    // An external source or executor will invoke later:
    scheduleCallback(() -> result.setResult("event arrived"));

    return result;
}
~~~

`scheduleCallback` is an illustrative function name, not part of the Servlet/Spring API. A full example with a real executor is in section 10.

### 5.1. When calling `setResult(...)`

If you call:

~~~java
boolean accepted = result.setResult(ResponseEntity.ok(body));
~~~

Spring stores the value if the result has not yet been decided, then triggers an async dispatch to process it as a normal handler return value. The method returns a boolean indicating whether setting that result was accepted; **do not infer that the response has already been sent successfully to the browser**. The result can be rejected if the request already timed out/completed or another result won the race.

### 5.2. When calling `setErrorResult(...)`

~~~java
result.setErrorResult(new ResourceNotFoundException("record missing"));
~~~

If the object is an appropriate exception, the ASYNC pass handles it via exception resolvers. `setErrorResult` can also accept a non-exception Object as an alternate result per Spring's contract, though using explicit exceptions/domain results avoids confusion with success responses.

**An exception thrown in a separate `Runnable` without calling `setErrorResult` does not automatically become a request error.** For example:

~~~java
executor.execute(() -> {
    throw new RuntimeException("lost to request");
});
~~~

Once the handler has returned `DeferredResult`, an exception from this runnable is not automatically linked to the holder by MVC. Catch the exception in the callback and call `setErrorResult`:

~~~java
executor.execute(() -> {
    try {
        String data = externalService.load();
        result.setResult(data);
    } catch (Exception ex) {
        result.setErrorResult(ex);
    }
});
~~~

The lines above are a fragment assuming executor/service/result variables; the full demo uses this below. Missing this distinction is a **common reason DeferredResult requests hang until timeout while worker logs already report an error**.

### 5.3. Timeout and completion callbacks

`DeferredResult` provides:
- `onTimeout(Runnable)`: callback when the async request times out.
- `onError(Consumer<Throwable>)`: callback when an error occurs during request/async processing.
- `onCompletion(Runnable)`: callback when the async lifecycle ends, whether successful or failed.

A timeout callback can try `setErrorResult(...)` or pick an alternate result; however, callbacks race with the producer. After completion, clean up registries/pending entries, unregister listeners, and prevent memory leaks. **Do not use `onCompletion` as proof that a business transaction succeeded**.

## 6. `WebAsyncTask<T>`: Callable with custom timeout/executor

`WebAsyncTask<T>` wraps `Callable<T>` and allows custom timeout, executor, and timeout/error/completion handlers.

~~~java
@GetMapping("/web-task")
public WebAsyncTask<ResponseEntity<String>> webTask() {
    WebAsyncTask<ResponseEntity<String>> task =
            new WebAsyncTask<>(3_000L,
                    () -> ResponseEntity.ok("task done"));

    task.onTimeout(() -> ResponseEntity.status(503).body("timed out"));
    task.onCompletion(() -> {
        // Request-bound resources can be cleaned up here.
    });
    return task;
}
~~~

This is an illustrative fragment requiring Spring imports. `3_000L` in the constructor is in **milliseconds**. The timeout callback runs on a container thread and must finish very quickly—**do not sleep or wait on network I/O** inside the callback.

`WebAsyncTask.onError(Callable<T>)` can also provide an alternate result for errors in async request processing. Do not confuse this `onError` with every exception thrown **inside the worker Callable**: worker exceptions are normally routed straight through MVC exception handling by Spring; design handlers according to actual error types.

The timeout on `WebAsyncTask` is not a guarantee of actively stopping a JDBC query, HTTP request, or blocked thread. You need per-dependency timeouts, cancellation/cooperative interrupts, and bounded resources in real usage.

## 7. How does the `ASYNC` dispatch handle the result?

### 7.1. Success case

~~~text
T1: DispatcherServlet --> Controller returns Callable<Payload>
T1: Spring starts async; servlet/filter chain exits
T2: Callable returns Payload
T2: WebAsyncManager stores result; asks AsyncContext.dispatch()
T3: DispatcherServlet on ASYNC
T3: stored Payload --> return value handling --> HttpMessageConverter
T3: response status/headers/body; complete
~~~

If `Payload` is a Java record and the controller is `@RestController`, a JSON converter (typically Jackson) serializes it during result handling. With `ResponseEntity<Payload>`, the status and headers inside the object are used by MVC in the completion phase.

### 7.2. Exception case

~~~text
T1: Controller returns Callable
T2: Callable throws ResourceNotFoundException
T2: Spring saves exception as async result
T3: ASYNC dispatch
T3: HandlerExceptionResolver / @RestControllerAdvice
T3: HTTP 404 + safe ProblemDetail JSON
~~~

For `DeferredResult`:

~~~text
T1: Controller returns DeferredResult
E1: External callback calls setErrorResult(exception)
T3: ASYNC dispatch
T3: @ExceptionHandler can map the exception
~~~

The crux is that **the exception must enter the Spring MVC pipeline**. If you spawn an arbitrary thread and an exception goes uncaught, MVC cannot know which request should receive 404/500. Connect it via `setErrorResult` or a return type that Spring understands.

### 7.3. Participation of `@RestControllerAdvice`

`@ExceptionHandler` in a controller or `@RestControllerAdvice` still applies after an ASYNC dispatch. If a handler returns a default 500 for unknown exceptions, do not include stack traces, raw SQL messages, tokens, or server paths in the response. For known public business exceptions, include a machine-readable `code` and proper HTTP status.

Spring MVC 6.x also provides `ProblemDetail`/`ErrorResponse` and `ResponseEntityExceptionHandler`. When extending `ResponseEntityExceptionHandler`, override hooks for built-in exceptions rather than adding duplicate `@ExceptionHandler` methods for the same exception types as the superclass, avoiding ambiguous mappings.

### 7.4. After the response has committed

Once bytes have been streamed to the client, the server **can no longer freely change the HTTP status/body** as before. `ResponseBodyEmitter`/`SseEmitter` have their own complete/error mechanisms; I/O errors from client disconnects cannot always send a clean 500 body. This article focuses on **single-result async** via Callable/DeferredResult/WebAsyncTask and does not promise advice can handle every error occurring after the body was sent.

## 8. Timeouts, errors, client disconnects, and race conditions

### 8.1. Default timeout

Do not guess that timeout is "30 seconds by default" in every deployment. The default Servlet async timeout depends on the container/configuration and can be customized by Spring MVC. With `WebMvcConfigurer.configureAsyncSupport`:

~~~java
@Override
public void configureAsyncSupport(AsyncSupportConfigurer configurer) {
    configurer.setDefaultTimeout(10_000L);
}
~~~

The unit is milliseconds. `DeferredResult<>(5_000L)` or `WebAsyncTask<>(3_000L, callable)` can set per-request timeouts; some load balancers/gateways/clients have even shorter timeouts. An API's effective timeout depends on **multiple layers**, not just Spring.

### 8.2. Timeout without a custom handler

Spring has `AsyncRequestTimeoutException`, which by default typically results in **503 Service Unavailable** via MVC exception infrastructure in Spring 6.1. A custom timeout callback can decide on a different result/status, e.g. 504 for gateway-like use cases when semantically accurate. Do not claim every timeout is definitely 504.

Rely on `@RestControllerAdvice` and `onTimeout` to produce a stable error schema; test realistically and avoid returning 200 with an error description body when clients expect proper error statuses.

### 8.3. Does the producer win or does timeout win?

Suppose the executor finishes right as timeout happens:

~~~text
T2: result.setResult(payload)        ↘
                                      one result is accepted
T3: timeout callback setErrorResult ↗
~~~

`DeferredResult` coordinates a single terminal result, but an external callback might still be running or about to perform side effects. Check the boolean return value of `setResult`/`setErrorResult` when you need instrumentation or pending-work cleanup, and do not record a "sent successfully" business event based solely on that.

### 8.4. Client already closed the connection

Servlet async generally does not guarantee an immediate, exact "client closed tab" event in all situations. With streaming, writes can throw `IOException` on connection errors; for single results, the server sometimes only discovers this during final serialization/writing. Do not keep work alive indefinitely hoping the client is still connected.

Use bounded timeouts on services, HTTP clients/databases, and queues; cancel when possible; clean up in completion callbacks; and ensure idempotency for side effects. Do not log sensitive data on client disconnect errors.

### 8.5. Full executor

MVC async releases container threads, yet **does not make execution capacity free**. If a pool has 8 threads and continuously receives thousands of blocking tasks, queues grow, latency climbs, and requests time out. Task rejections can occur past thresholds.

Use bounded executors, overload policies, metrics, per-dependency timeouts, and backpressure/admission control at the app/gateway. Never use unbounded pools in production; never spawn a new thread per request.

## 9. `AsyncHandlerInterceptor` and MVC callbacks

A normal `HandlerInterceptor` has `preHandle`, `postHandle`, and `afterCompletion`. When a controller starts async:
- On the **initial REQUEST**, `preHandle` normally runs.
- When concurrent handling starts, an `AsyncHandlerInterceptor` receives `afterConcurrentHandlingStarted` **instead of** `postHandle` and `afterCompletion` on the first pass.
- On the **ASYNC dispatch**, the interceptor can go through the lifecycle again; `preHandle` may be called again and then `postHandle/afterCompletion` run on completion depending on the path.

Fragment example:

~~~java
public final class TraceAsyncInterceptor implements AsyncHandlerInterceptor {

    @Override
    public void afterConcurrentHandlingStarted(
            HttpServletRequest request, HttpServletResponse response,
            Object handler) {
        // Clear REQUEST-thread ThreadLocal if needed.
    }
}
~~~

This fragment requires imports for `AsyncHandlerInterceptor` and Servlet types; it is not registered in the runnable demo since the main example does not need request modification.

**Common bug:** starting a timer in `preHandle` and incrementing a pageview there, then incrementing it a second time after ASYNC redispatch. If a business side effect must run only once, mark it in request scope/check dispatcher type or place the side effect elsewhere, rather than assuming an interceptor is always called once.

### 9.1. Filters and `DispatcherType.ASYNC`

Servlet filters have dispatcher type mappings; in Boot, when registering a `FilterRegistrationBean`, you can specify:

~~~java
registration.setDispatcherTypes(
        DispatcherType.REQUEST, DispatcherType.ASYNC);
registration.setAsyncSupported(true);
~~~

This is a fragment requiring `registration` and importing `jakarta.servlet.DispatcherType`. If a servlet/filter does not support async, the runtime can throw `IllegalStateException` when starting asynchronous processing.

With `OncePerRequestFilter`, check `shouldNotFilterAsyncDispatch()` and `isAsyncDispatch(request)`; it has built-in behavior to avoid running multiple times depending on dispatcher type and overrides. Do not assume a custom filter runs on every ASYNC dispatch just because the class has "Once" in its name.

### 9.2. Filter chain and Spring Security

Spring Security integrates `WebAsyncManagerIntegrationFilter` to help handle `SecurityContext` when using Spring MVC `Callable`. Even so, **custom threads**, `DeferredResult` completed from a message listener, and many `CompletableFuture` callbacks **do not always automatically have the same `SecurityContextHolder`**, MDC, or transaction context as the container request thread.

If a worker needs principal/tenant details, capture **immutable, authenticated** data from the controller/service and pass it safely as parameters, or use `DelegatingSecurityContextExecutor`/context propagation per your framework/config. Do not keep the mutable `HttpServletRequest` in a worker to read user/session arbitrarily later. Do not assume `@Transactional` context follows across threads; transactions are normally thread-bound and need proper service boundaries called on the worker.

### 9.3. MDC, tracing, and correlation

`ThreadLocal`/SLF4J MDC usually does not propagate automatically across thread pools. If logging by trace/request ID, use tracing context propagation or a proper task decorator, ensuring context is cleared at the end of the task so one request's data does not remain on a thread reused for another request.

Never put raw cookies/Authorization headers/tokens into logs to "debug async". A benign trace ID and dedicated task ID correlate T1/T2/T3 far better than logging thread names.

## 10. Runnable example: Spring Boot 3.3.5, Callable, DeferredResult, WebAsyncTask

The demo illustrates an async outcome that can be **success**, **not found**, or **timeout**:
- `GET /api/async/callable/{id}`: `Callable<ResponseEntity<Payload>>` executed on the MVC executor.
- `GET /api/async/deferred/{id}`: `DeferredResult<ResponseEntity<Payload>>` completed by an executor callback; on error it calls `setErrorResult`.
- `GET /api/async/web-task/{id}`: `WebAsyncTask<ResponseEntity<Payload>>` with its own timeout.
- `@RestControllerAdvice`: maps `MissingItemException` to 404 and `WorkTimedOutException` to 503 using `ProblemDetail`.
- MockMvc: asserts `asyncStarted`, calls `asyncDispatch`, then checks the final response.

There is no database, Spring Security, or real network client; results are **deterministic fixtures**, not claiming workers do slow I/O. The goal is illustrating lifecycle and exception propagation. Tests do not try to trigger timeouts with `Thread.sleep` because that would make CI flaky.

~~~text
mvc-async-dispatch-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/com/example/mvcasync/
    │   ├── AsyncApplication.java
    │   ├── config/AsyncMvcConfig.java
    │   └── web/
    │       ├── AsyncController.java
    │       ├── AsyncErrorAdvice.java
    │       ├── MissingItemException.java
    │       └── WorkTimedOutException.java
    └── test/java/com/example/mvcasync/web/
        └── AsyncControllerTest.java
~~~

### 10.1. Gradle build

`settings.gradle`:

~~~groovy
rootProject.name = 'mvc-async-dispatch-demo'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

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

`spring-boot-starter-web` provides Spring MVC, the Servlet container (Tomcat by default with Boot starter Web), and Jackson JSON conversion. `spring-boot-starter-test` provides JUnit 5 and MockMvc. You do not need `spring-boot-starter-webflux` just to use MVC Callable/DeferredResult.

### 10.2. Main class

`src/main/java/com/example/mvcasync/AsyncApplication.java`:

~~~java
package com.example.mvcasync;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class AsyncApplication {
    public static void main(String[] args) {
        SpringApplication.run(AsyncApplication.class, args);
    }
}
~~~

### 10.3. Configuring a bounded executor and MVC timeout

`src/main/java/com/example/mvcasync/config/AsyncMvcConfig.java`:

~~~java
package com.example.mvcasync.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.web.servlet.config.annotation.AsyncSupportConfigurer;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class AsyncMvcConfig implements WebMvcConfigurer {

    @Bean("mvcAsyncExecutor")
    public ThreadPoolTaskExecutor mvcAsyncExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setThreadNamePrefix("mvc-worker-");
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(64);
        return executor;
    }

    @Override
    public void configureAsyncSupport(AsyncSupportConfigurer configurer) {
        // @Configuration uses the Spring-managed @Bean method.
        configurer.setTaskExecutor(mvcAsyncExecutor());
        configurer.setDefaultTimeout(10_000L);
    }
}
~~~

In standard `@Configuration` (where proxy bean methods are enabled by default), calling `mvcAsyncExecutor()` inside the class retrieves the managed singleton bean; Spring manages initialization/shutdown. `ThreadPoolTaskExecutor` is used both for MVC's `Callable` and injected into the controller for `DeferredResult` completion. `setDefaultTimeout` sets the default async timeout to **10,000 milliseconds**; in the code below `DeferredResult`/`WebAsyncTask` specify their own timeouts.

**Production:** 4/8/64 sizing is demo-only. Choose pool/queue sizes based on real traffic, blocking vs. CPU-bound workloads, thread memory, queue-wait timeouts, overload behavior, metrics, and shutdown. Time spent waiting in the queue also counts toward the request's wait time in practice; do not measure only `call()` duration.

### 10.4. Two public exceptions

`src/main/java/com/example/mvcasync/web/MissingItemException.java`:

~~~java
package com.example.mvcasync.web;

public class MissingItemException extends RuntimeException {

    public MissingItemException(long id) {
        super("Item " + id + " does not exist");
    }
}
~~~

`src/main/java/com/example/mvcasync/web/WorkTimedOutException.java`:

~~~java
package com.example.mvcasync.web;

public class WorkTimedOutException extends RuntimeException {

    public WorkTimedOutException() {
        super("Async operation timed out");
    }
}
~~~

In a real application, internal exception messages should not be echoed directly if they contain identifiers or sensitive data. Advice should return safe details instead of `ex.getMessage()`.

### 10.5. Controller covering all three result types

`src/main/java/com/example/mvcasync/web/AsyncController.java`:

~~~java
package com.example.mvcasync.web;

import java.util.concurrent.Callable;
import org.springframework.core.task.AsyncTaskExecutor;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.context.request.async.DeferredResult;
import org.springframework.web.context.request.async.WebAsyncTask;

@RestController
@RequestMapping("/api/async")
public class AsyncController {

    public record Payload(long id, String state) {}

    private final AsyncTaskExecutor executor;

    public AsyncController(AsyncTaskExecutor mvcAsyncExecutor) {
        this.executor = mvcAsyncExecutor;
    }

    private ResponseEntity<Payload> find(long id) {
        if (id <= 0) {
            throw new MissingItemException(id);
        }
        return ResponseEntity.ok(new Payload(id, "ready"));
    }

    @GetMapping("/callable/{id}")
    public Callable<ResponseEntity<Payload>> callable(
            @PathVariable("id") long id) {
        return () -> find(id);
    }

    @GetMapping("/deferred/{id}")
    public DeferredResult<ResponseEntity<Payload>> deferred(
            @PathVariable("id") long id) {

        DeferredResult<ResponseEntity<Payload>> result =
                new DeferredResult<>(5_000L);

        result.onTimeout(() ->
                result.setErrorResult(new WorkTimedOutException()));

        result.onCompletion(() -> {
            // Do not retain results in queues/registries after completion.
        });

        try {
            executor.execute(() -> {
                try {
                    result.setResult(find(id));
                } catch (Exception ex) {
                    result.setErrorResult(ex);
                }
            });
        } catch (RuntimeException rejected) {
            result.setErrorResult(rejected);
        }

        return result;
    }

    @GetMapping("/web-task/{id}")
    public WebAsyncTask<ResponseEntity<Payload>> webTask(
            @PathVariable("id") long id) {

        WebAsyncTask<ResponseEntity<Payload>> task =
                new WebAsyncTask<>(3_000L, () -> find(id));

        task.onTimeout(() -> {
            throw new WorkTimedOutException();
        });

        return task;
    }
}
~~~

**Explanation and key takeaways:**
- `find(id)` simply builds a fixture or throws when `id <= 0`; no DB/network I/O is done. All examples ultimately return the same `Payload`.
- `callable`: the controller method **runs on the REQUEST thread**, while the lambda `() -> find(id)` runs on the executor submitted by MVC. Exceptions inside the lambda are captured by Spring and routed through the ASYNC dispatch.
- `deferred`: MVC **does not submit work automatically** for `DeferredResult`; the controller dispatches the task via the injected executor. On success it calls `setResult`; on failure inside the task, **it must call `setErrorResult`**, otherwise MVC will never know about the exception on the custom thread.
- `deferred` times out after 5 seconds per the holder configuration, and the callback pushes `WorkTimedOutException` if no result is set yet.
- `webTask` has a 3-second timeout, with a callback returning/pushing an alternate error. Exceptions thrown from the timeout callback are handled by Spring's async interception contract; in real deployments verify the exact mapping/error branch, and never assume a callback can perform long I/O.
- The catch around `executor.execute` merely illustrates that task submission can be rejected; in real systems, map task rejection to a policy-driven 503 error safely without returning raw exceptions.

**One refinement before production use:** `WebAsyncTask`'s `onTimeout` can `return` an appropriate alternate `ResponseEntity` instead of throwing an exception; that reduces reliance on exception paths inside the callback. If you need ProblemDetail errors like the other branches, you can return a matching response object or write a thoroughly tested resolver. This demo only tests success/error paths from `Callable`/`DeferredResult`, without simulating real timers.

### 10.6. Advice converting exceptions to standard error responses

`src/main/java/com/example/mvcasync/web/AsyncErrorAdvice.java`:

~~~java
package com.example.mvcasync.web;

import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class AsyncErrorAdvice {

    @ExceptionHandler(MissingItemException.class)
    public ResponseEntity<ProblemDetail> missing(
            MissingItemException ex) {

        ProblemDetail problem =
                ProblemDetail.forStatus(HttpStatus.NOT_FOUND);
        problem.setTitle("Item not found");
        problem.setDetail("The requested item does not exist.");
        problem.setProperty("code", "ITEM_NOT_FOUND");
        return ResponseEntity.status(HttpStatus.NOT_FOUND).body(problem);
    }

    @ExceptionHandler(WorkTimedOutException.class)
    public ResponseEntity<ProblemDetail> timeout(
            WorkTimedOutException ex) {

        ProblemDetail problem =
                ProblemDetail.forStatus(HttpStatus.SERVICE_UNAVAILABLE);
        problem.setTitle("Operation timed out");
        problem.setDetail("The operation could not finish in time.");
        problem.setProperty("code", "ASYNC_TIMEOUT");
        return ResponseEntity.status(
                HttpStatus.SERVICE_UNAVAILABLE).body(problem);
    }
}
~~~

`ProblemDetail` is Spring 6's HTTP API based on RFC 9457. With Jackson support in Spring MVC, `setProperty("code", ...)` normally becomes a top-level `code` extension field in JSON.

HTTP 404/503 are just the demo's contract: do not use 503 for **every** failure. Network gateway timeout 504, upstream failure 502, or overload 503 have different semantics; choose based on error type and where it occurred. Do not expose raw exception messages in JSON.

## 11. MockMvc: requires two test phases, not just `asyncStarted`

`MockMvc` does not automatically execute a container async dispatch for you like a running server. With asynchronous handlers, the proper test sequence is:
1. Initial `mvc.perform(get(...))`.
2. Assert `request().asyncStarted()` and capture `MvcResult`.
3. `mvc.perform(asyncDispatch(first))` to finish processing the result in the test.
4. Assert **final HTTP status/body**.

### 11.1. Runnable test suite

`src/test/java/com/example/mvcasync/web/AsyncControllerTest.java`:

~~~java
package com.example.mvcasync.web;

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
class AsyncControllerTest {

    @Autowired
    MockMvc mvc;

    @Test
    void callableSuccessNeedsAsyncDispatch() throws Exception {
        MvcResult started = mvc.perform(
                        get("/api/async/callable/7"))
                .andExpect(request().asyncStarted())
                .andReturn();

        mvc.perform(asyncDispatch(started))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value(7))
                .andExpect(jsonPath("$.state").value("ready"));
    }

    @Test
    void callableExceptionIsHandledOnResume() throws Exception {
        MvcResult started = mvc.perform(
                        get("/api/async/callable/0"))
                .andExpect(request().asyncStarted())
                .andReturn();

        mvc.perform(asyncDispatch(started))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.code").value("ITEM_NOT_FOUND"))
                .andExpect(jsonPath("$.status").value(404));
    }

    @Test
    void deferredSuccessIsSerializedAfterResume() throws Exception {
        MvcResult started = mvc.perform(
                        get("/api/async/deferred/9"))
                .andExpect(request().asyncStarted())
                .andReturn();

        mvc.perform(asyncDispatch(started))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value(9))
                .andExpect(jsonPath("$.state").value("ready"));
    }

    @Test
    void deferredSetErrorResultGoesThroughAdvice() throws Exception {
        MvcResult started = mvc.perform(
                        get("/api/async/deferred/0"))
                .andExpect(request().asyncStarted())
                .andReturn();

        mvc.perform(asyncDispatch(started))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.code").value("ITEM_NOT_FOUND"))
                .andExpect(jsonPath("$.status").value(404));
    }

    @Test
    void webAsyncTaskSuccessNeedsDispatch() throws Exception {
        MvcResult started = mvc.perform(
                        get("/api/async/web-task/11"))
                .andExpect(request().asyncStarted())
                .andReturn();

        mvc.perform(asyncDispatch(started))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value(11));
    }
}
~~~

Run in the project directory containing the Gradle wrapper:

~~~bash
./gradlew test
~~~

Windows PowerShell/CMD:

~~~powershell
.\gradlew.bat test
~~~

**Interpreting test scope properly:** Spring MVC MockMvc support waits for the async result on dispatch, yet tests do not prove network disconnects, Servlet container timeouts, filter ASYNC registrations, or thread pool behavior under real load. Do not assert hardcoded thread names, and do not use `Thread.sleep` to prove dispatch. The current executor configuration ensures non-blocking execution of the servlet REQUEST thread when MVC hands work to a worker; the worker finishing quickly does not alter the lifecycle principle.

### 11.2. Typical broken test

~~~java
mvc.perform(get("/api/async/callable/7"))
        .andExpect(status().isOk());
~~~

That test may only inspect the **initial status** before JSON serialization finishes, failing to verify the final body or error handling. Even if `status().isOk()` passes before dispatch, it **does not prove the task succeeded**. Always assert `request().asyncStarted()` and call `asyncDispatch(...)` for asynchronous return value types.

### 11.3. When using WebTestClient instead of MockMvc

Spring MVC supports binding WebTestClient to MockMvc; higher-level test abstractions may handle async automatically, so do not mechanically copy MockMvc's two-phase pattern to every client. When hitting embedded Tomcat with a real HTTP client, the client normally only sees the final response—there is no client-side "asyncDispatch API call".

## 12. Observing HTTP on a real server

Run:

~~~bash
./gradlew bootRun
~~~

Success:

~~~bash
curl -i 'http://localhost:8080/api/async/callable/7'
curl -i 'http://localhost:8080/api/async/deferred/9'
curl -i 'http://localhost:8080/api/async/web-task/11'
~~~

Each response is expected to return HTTP **200** and JSON such as:

~~~json
{"id":7,"state":"ready"}
~~~

For deferred/9 `id=9`, and for web-task/11 `id=11`.

Try exceptions:

~~~bash
curl -i 'http://localhost:8080/api/async/callable/0'
curl -i 'http://localhost:8080/api/async/deferred/0'
~~~

Expect HTTP **404** with `ProblemDetail` and extension:

~~~json
{
  "type":"about:blank",
  "title":"Item not found",
  "status":404,
  "detail":"The requested item does not exist.",
  "code":"ITEM_NOT_FOUND"
}
~~~

`instance` may be added automatically from the request path depending on Spring/Jackson handling. The JSON snippet above lists the main fields only. **curl only sees one final HTTP response**; you cannot deduce the number of Servlet dispatches from `curl -i` alone. Use application tracing/debug logs or an instrumented interceptor if you need to observe internal phases.

## 13. Handle errors where they occur

| Where error occurs | Example | Does MVC receive it automatically? | How to handle |
| --- | --- | --- | --- |
| Controller before returning async handle | Parameter validation fails | Yes, like synchronous MVC | `@ExceptionHandler`, validation/error response |
| Inside `Callable.call()` | Remote service exception | Yes, Spring captures exception as async result | Advice/error resolver on ASYNC dispatch |
| Inside `WebAsyncTask` Callable | Worker throws | Yes, like Callable | Advice/error resolver |
| Custom `Runnable` for `DeferredResult` | Uncaught throw | **No**, MVC only sees an uncompleted holder | Catch and call `setErrorResult(exception)` |
| Callback `setErrorResult(exception)` | Event reports missing item | Yes, when accepted | ASYNC dispatch then advice |
| DeferredResult timeout callback | Holder has no result yet | Via callback/result/interceptor | Set error/alternate result, log, and clean up |
| Default Servlet async timeout | Request waited too long | Usually becomes `AsyncRequestTimeoutException` | Default 503 or custom policy |
| Streaming response already committed | Network disconnect/write IOException | Cannot guarantee changing body/status | Safe cleanup/logging, emitter/completion API |
| Executor rejects on submit | Pool/queue overloaded | Depends on throw point/config | Bounded overload policy, 503/metrics/tests |
| Background worker unrelated to request | Scheduled job throws exception | No | Independent job error handling/retry/dead-letter |

Using `@RestControllerAdvice` does not mean catching exceptions on every thread in the JVM. The condition is that the error flows through **MVC's result/exception handling mechanism**. Spring MVC async lets you do that with Callable/WebAsyncTask/DeferredResult when used properly.

## 14. Observability: do not double-count requests due to the second dispatch

Because the same HTTP request can pass through filters/interceptors twice across two dispatcher types, analytics should not count every `preHandle` or `doFilter` as a separate business request if they execute on both REQUEST and ASYNC.

Recommendations:
- Use HTTP server metrics instrumented by the framework across the true response lifecycle when available.
- When instrumenting manually, attach a request ID/attribute and mark logical request start/end once.
- Log dispatcher type, phase, trace ID, and duration; **never log sensitive tokens/cookies/bodies**.
- For workers, propagate tracing/MDC context in a controlled way and clear it when using pooled threads.
- Measure executor active count, pool/queue size, task rejections, timeout rate, p95/p99 latency, and downstream wait time.
- Separate proxy/client/service/container timeouts; do not look at a single "async timeout" metric and conclude the DB is at fault.

Suppose a worker starts after waiting 9 seconds in the queue and Spring MVC timeout is 10 seconds. Even if business computation takes only 2 seconds, the request can time out before the worker returns. Monitoring must distinguish queue time from execution time.

## 15. MVC async vs. Java `@Async`, CompletableFuture, and WebFlux

### 15.1. Spring's `@Async`

`@Async` is a Spring mechanism to run methods on an executor via an AOP proxy when enabled and called across a valid proxy boundary. It **does not automatically make HTTP responses use Servlet ASYNC dispatch** just because a service is annotated. If the controller waits on `future.get()`, the servlet request thread still blocks.

To do MVC async, the controller must return a return type MVC recognizes such as `Callable`, `DeferredResult`, an appropriate `CompletionStage/CompletableFuture`, or a reactive single-result adapter. Check versions/adapters when using them and handle cancellation/exceptions explicitly.

### 15.2. `CompletableFuture` and context propagation

`CompletableFuture.supplyAsync(...)` without specifying an executor can use the common ForkJoinPool. That easily causes unpredictable throughput, trace context, transaction/security context, and workload isolation. For request-scoped workloads, prefer a dedicated bounded executor or appropriate async HTTP client. MVC knows how to handle several async return types via adapters, yet **where** a future executes remains the application's responsibility.

### 15.3. Spring MVC async is not WebFlux

| Characteristic | Spring MVC async | Spring WebFlux |
| --- | --- | --- |
| HTTP server foundation | Servlet API | Reactive/non-blocking stack |
| Servlet `ASYNC` dispatch pass | Yes, when using async support | Does not share the Servlet MVC mechanism |
| Controller returns `Callable`/`DeferredResult` | Supported | Not the primary programming model |
| Blocking JDBC inside worker | Still occupies worker thread | Must also offload if calling blocking code |
| HTTP response stream writes | Can block via executor | Based on non-blocking reactive I/O |
| Usage context | Extending existing MVC | End-to-end reactive/streaming when appropriate |

Do not migrate to WebFlux just because you see the word "async"; evaluate the library chain, team familiarity, thread model, tracing, backpressure, and testing. If you only need to wait on some external calls in an MVC app, Servlet async is often enough.

## 16. Common implementation mistakes

| Symptom | Common cause | Solution |
| --- | --- | --- |
| Controller returns Callable yet threads stay high | Callable performs blocking I/O in worker | Measure pool/queue; consider async I/O or right-size capacity |
| `IllegalStateException` when starting async | Servlet/filter lacks `asyncSupported` | Configure Servlet/Filter and dispatcher types |
| Client hangs forever with DeferredResult | `setResult`/`setErrorResult` never called | Ensure every success/error/timeout branch completes |
| Worker logs error but client gets 503 timeout | Runnable threw without calling `setErrorResult` | Catch and pass exception into DeferredResult |
| `@ExceptionHandler` does not run | Error occurred outside MVC async flow or response committed | Route through holder, use appropriate error flow |
| MockMvc asserts 200 yet JSON is empty | Only checked initial perform | Call `asyncDispatch(MvcResult)` |
| Interceptor double-counts metrics | `preHandle` runs again on ASYNC | Distinguish phase/dispatcher type |
| MDC lost or wrong user shown | ThreadLocal did not propagate or leaked | Controlled context propagation and cleanup |
| `SecurityContextHolder` empty in custom worker | Callback bypassed Callable Security integration | Pass trusted principal/context via executor wrapper |
| `@Transactional` gone in worker | Transaction context is thread-bound | Open transaction in service on the right thread |
| Always times out at 30s despite MVC 120s | Shorter proxy/client/LB timeout | Configure end-to-end and verify network path |
| Async timeout after work actually finished | Race/queue backlog/late task result | Check `setResult` boolean, metrics, and cancellation |
| Thousands of worker threads under heavy load | Unbounded executor | Use bounded pool/queue and overload handling |
| 500 JSON leaks raw exception | Catch-all advice returns `ex.getMessage()` | Safe ProblemDetail + internal logs |
| Background task finishes after client disconnect | No cancel/cleanup | Check idempotency, timeouts, and lifecycle callbacks |
| Trying to change status to 404 after `ResponseBodyEmitter` committed | HTTP status/headers already sent | Handle streaming protocol/errors separately |
| Calling controller method twice thinking ASYNC is a new request | Misunderstanding mapping during redispatch | MVC uses stored result, does not re-invoke method |
| `Thread.sleep` inside timeout callback | Blocks container thread | Fast callback; schedule external cleanup if needed |

## 17. Production checklist

1. Confirm container, DispatcherServlet, and filter mappings support Servlet async.
2. Pick the right type: Callable for MVC-managed computation; DeferredResult for external event/completion; WebAsyncTask for per-request Callable settings.
3. Set MVC async timeouts and per-dependency timeouts; verify LB/client timeouts are not unintentionally shorter.
4. Use bounded executors with clear metrics/rejection policies; never spawn unbounded threads.
5. Ensure every DeferredResult callback path calls `setResult` or `setErrorResult`.
6. Use `@ExceptionHandler`/`ProblemDetail` for known errors, keeping statuses/bodies safe.
7. Account for timeout/result races, cancellation, cleanup, and pending-registration leaks.
8. Do not rely on ThreadLocal/MDC/SecurityContext/transaction context propagating automatically across threads.
9. Distinguish `REQUEST` and `ASYNC` so business side effects are not counted/executed twice.
10. Verify AsyncHandlerInterceptor and OncePerRequestFilter if logic must apply on redispatch.
11. Test MockMvc in two phases and add HTTP/container integration tests for timeout/disconnect/security.
12. If streaming, verify behavior after response commit; do not assume status can still be changed.
13. Move genuinely long jobs to a queue/job status endpoint instead of holding HTTP connections indefinitely.
14. Check sensitive data in logs, traces, exceptions, and security context propagation.
15. Measure thread pools, queues, response latency, and errors after every executor/config change.

### Self-check questions

**1.** With Callable, is the controller method called again on the ASYNC dispatch?

**Answer:** No. Spring MVC maps the handler to resume, but uses the **stored concurrent result**, without re-running the business code inside the controller method.

**2.** How many requests does the HTTP client send if the server processes REQUEST and ASYNC?

**Answer:** One HTTP request. REQUEST/ASYNC are two internal Servlet dispatches; the client sees a single completed response.

**3.** Can an exception thrown by a `Callable` on a worker reach `@RestControllerAdvice`?

**Answer:** Yes, when Spring MVC manages the Callable, the exception is captured as the result and processed during the ASYNC dispatch.

**4.** Why does an exception inside a DeferredResult's executor runnable not reach advice automatically?

**Answer:** An independent Runnable is not automatically linked to DeferredResult by Spring; the application must catch it and call `setErrorResult(exception)`.

**5.** Does `DeferredResult.setResult(...)` returning true mean the client already received the response?

**Answer:** Not yet. It only reflects that the holder accepted setting the result; async dispatch, conversion, and network write still follow.

**6.** Why does MockMvc need `asyncDispatch`?

**Answer:** MockMvc simulates Servlet processing but does not automatically finish async requests like an embedded container; you must dispatch again to test the final status/body.

**7.** Should `WebAsyncTask.onTimeout` call a 10-second HTTP client to retry?

**Answer:** No. Timeout callbacks run on a container thread and must be fast; handle retries/heavy background work externally with bounded resources.

**8.** Does Spring MVC async free all threads while JDBC is running?

**Answer:** No. The Servlet request thread returns to the pool, but blocking JDBC still occupies the executor worker.

**9.** After `ResponseBodyEmitter` has sent part of the body, can you change the status to 404?

**Answer:** Usually no, because the response may already be committed; streaming errors must be handled according to the corresponding protocol.

## 18. Official documentation

- [Spring Framework 6.2 — Asynchronous Requests](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-ann-async.html): Callable, DeferredResult, WebAsyncTask, processing, error handling, interceptors, streaming, and Servlet configuration.
- [Spring Framework 6.1 — WebAsyncManager Javadoc](https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/web/context/request/async/WebAsyncManager.html): start, concurrent result, dispatch lifecycle.
- [Spring Framework 6.1 — DeferredResult Javadoc](https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/web/context/request/async/DeferredResult.html): `setResult`, `setErrorResult`, timeout/error/completion callbacks.
- [Spring Framework 6.1 — WebAsyncTask Javadoc](https://docs.spring.io/spring-framework/docs/6.1.8/javadoc-api/org/springframework/web/context/request/async/WebAsyncTask.html): per-task timeout, executor, timeout/error/completion.
- [Spring Framework 6.1 — AsyncHandlerInterceptor Javadoc](https://docs.spring.io/spring-framework/docs/6.1.8/javadoc-api/org/springframework/web/servlet/AsyncHandlerInterceptor.html): `afterConcurrentHandlingStarted` and interceptor lifecycle.
- [Spring Framework — MockMvc Async Requests](https://docs.spring.io/spring-framework/reference/testing/mockmvc/hamcrest/async-requests.html): `request().asyncStarted()`, `request().asyncResult(...)`, and `asyncDispatch`.
- [Spring Framework — MVC Configuration](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/async-support.html): `configureAsyncSupport`, task executor, and timeout.
- [Jakarta Servlet 6.0 — AsyncContext](https://jakarta.ee/specifications/servlet/6.0/apidocs/jakarta.servlet/jakarta/servlet/asynccontext): `dispatch`/`complete`, timeout/listeners.
- [Spring Security — Servlet Integration](https://docs.spring.io/spring-security/reference/servlet/integrations/servlet-api.html): integration points and security context.
- [Spring Framework — Problem Details](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-rest-exceptions.html): error response API and exception handling.

**Key takeaway:** Spring MVC async neither returns the response immediately nor creates a "second request" in the browser. Controllers return **Callable/DeferredResult/WebAsyncTask**, the Servlet releases the request thread and then performs an **ASYNC dispatch** when a result/error arrives. Success passes through return-value processing; properly routed errors pass through exception resolvers; timeout/cleanup/context propagation must be configured and tested. In MockMvc, do not stop at `asyncStarted`: call `asyncDispatch` and assert the final HTTP response.
