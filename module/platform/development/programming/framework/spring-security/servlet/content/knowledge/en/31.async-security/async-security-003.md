# DeferredResult, CompletableFuture, and Application-Coordinated Async Work

## 1. The Big Picture in Spring Security Servlet

In a Spring MVC application running on the **Servlet stack**, each normal HTTP request flows through the Servlet filter chain, Spring Security, `DispatcherServlet`, and the controller, returning a response on one request-processing thread. When an external operation takes time (calling another service, computing a report, waiting for an event), holding a servlet thread for the entire duration reduces the capacity to serve other requests.

**Servlet asynchronous processing** allows returning the request-receiving thread to the pool while the result is still being prepared, then completing the response via an **async dispatch**. Spring MVC supports several return types, including `DeferredResult<T>` and `CompletableFuture<T>`.

Important distinctions to make:

1. **Asynchronous request**: the HTTP connection is still waiting for a result; the initial servlet thread is released, yet the request is not finished.
2. **Application-coordinated work**: the application chooses the executor, creates/runs the task, handles timeouts, errors, cancellation, resource monitoring, and load limits.
3. **True non-blocking I/O**: not synonymous with `DeferredResult` or `CompletableFuture`. If the task uses JDBC or `Thread.sleep`, the application's worker thread is **still blocked**.
4. **Async security**: `SecurityContextHolder` is normally thread-bound. Moving to a worker thread does not guarantee `Authentication`/MDC/request attributes automatically follow.

This lesson focuses on coordinating Spring MVC async and Spring Security in a **Servlet** application, without switching to WebFlux or Reactor.

## 2. HTTP Request Lifecycle When Using Async

A synchronous flow:

```text
Client
  -> Tomcat servlet thread
      -> SecurityFilterChain
      -> DispatcherServlet
      -> Controller makes slow I/O call and waits
      -> Controller returns result
      -> write HTTP response
  -> thread returns to pool
```

An asynchronous flow using `DeferredResult`:

```text
Client -> Tomcat servlet thread #1
            -> SecurityFilterChain
            -> DispatcherServlet / Controller
            -> create DeferredResult, register callbacks
            -> submit work to application executor
            -> return DeferredResult
            -> Servlet async starts; thread #1 is released
                                      |
                                      v
                           Separate worker thread
                           -> execute work
                           -> deferred.setResult(...)
                                      |
                                      v
                     Servlet container async dispatch
                           -> MVC processes result
                           -> HTTP response
                           -> complete async request
```

The thread in the worker branch is **not** the original servlet request thread. `DeferredResult#setResult` only publishes the result to Spring MVC; never manually use `HttpServletResponse#getWriter()` from a worker to race against Spring MVC's response-handling mechanism.

After the controller returns, the client usually keeps the HTTP connection open. Therefore, request-bound async is not a durable background job queue system; connections, async contexts, timeouts, and server memory still require management.

## 3. `DeferredResult<T>`: The Application Decides When to Complete

`DeferredResult<T>` is a **promise-like** object for Spring MVC. The controller creates and returns it immediately; another thread or event later calls:

```java
DeferredResult<String> result = new DeferredResult<>(2_000L);

result.onTimeout(() ->
        result.setErrorResult("Operation exceeded its deadline"));

result.onError(error ->
        result.setErrorResult("Operation could not be completed"));

// Once a worker or callback has the data:
result.setResult("ready");
```

This is an **illustrative snippet**, not a complete HTTP method; the constructor timeout is in **milliseconds**. Real APIs should return an HTTP status/body with a clear contract, not just an error string.

Key methods:

| API | Meaning | Notes |
| --- | --- | --- |
| `new DeferredResult<>(timeoutMs)` | Creates a pending result with an optional timeout | Does not mean the worker will be cancelled automatically upon expiration |
| `setResult(value)` | Publishes a normal result | Returns `boolean`; may be `false` if already completed |
| `setErrorResult(valueOrError)` | Publishes an error/error value | If an exception is passed, MVC goes through exception handling |
| `onTimeout(Runnable)` | Callback when the async request exceeds its deadline | Can set an appropriate error result |
| `onError(Consumer<Throwable>)` | Callback when the async request encounters an error | Distinguish transport errors from worker logic errors |
| `onCompletion(Runnable)` | Callback when async processing has finished | Useful for cleanup/metrics; not a signal that the task was cancelled |

**Only the first result wins**: if the worker and the timeout callback both call `setResult`/`setErrorResult`, only one branch claims completion. Always design for this race, avoiding writing the response or updating business state twice when a late result arrives.

Examples of result sources suited to `DeferredResult`: replies from a message broker, callbacks from external systems, a long-lived event (*long polling*), or a task running on an executor. Do not spawn a new thread per request.

## 4. `CompletableFuture<T>`: Coordinating Computations and Pipelines

Java 8+ provides `CompletableFuture` to represent a computation completing in the future. With Spring MVC Servlet, returning `CompletableFuture<ResponseEntity<...>>` from a controller is adapted by Spring MVC into the async response mechanism.

```java
CompletableFuture<String> future =
        CompletableFuture.supplyAsync(
                () -> "ready",
                reportExecutor);
```

**Notes:**

- Passing an explicit executor is important. Without passing an executor to `supplyAsync`, Java usually uses **`ForkJoinPool.commonPool()`**. The common pool is a shared resource, unsuitable as a default for slow I/O or security-sensitive/multi-tenant work.
- `supplyAsync` merely runs the supplier on an executor; it **does not make a blocking function non-blocking**.
- Stages such as `thenApply`, `thenCompose`, `handle`, and `exceptionally` have different execution rules. Variants without the `Async` suffix may run on the thread that completed the previous stage; `Async` variants usually use the specified executor or the default executor if omitted.
- Exceptions are commonly wrapped in `CompletionException` when reading/composing futures. Never expose internal exceptions, stack traces, or secrets to clients.
- `orTimeout(...)` completes the future in an error state upon deadline; it **is not guaranteed to stop** already-running I/O work. `cancel(true)` on a `CompletableFuture` likewise does not guarantee every task submitted to an executor will be interrupted.

Result-processing example:

```java
CompletableFuture<String> normalized =
        CompletableFuture.supplyAsync(() -> "report-ready", reportExecutor)
                .thenApply(String::toUpperCase)
                .exceptionally(error -> "UNAVAILABLE");
```

This is an **illustrative snippet** assuming `reportExecutor` is already defined; there is no HTTP server. `thenApply` does not automatically switch back to the servlet thread.

## 5. When to Choose `DeferredResult`, `CompletableFuture`, or `Callable`?

| Return Type / Mechanism | Who Controls Completion? | When Appropriate |
| --- | --- | --- |
| `DeferredResult<T>` | Application/callback actively calls `setResult` | Long polling, callbacks, event-driven completion, needing clear separation between receiver and completer |
| `CompletableFuture<T>` | A Java future pipeline completes | Running computations or combining results from other services, handling exceptions per stage |
| `Callable<T>` | Spring MVC submits the callable to MVC's configured AsyncTaskExecutor | Tasks with a single return value that do not need manual DeferredResult management |
| `@Async` on a service | Spring proxy executes the method on an executor | Separating a service task from the caller; **does not automatically set an HTTP response timeout/async contract** |
| Job queue + `202 Accepted` | Worker/queue independent of the HTTP request | Long tasks needing durable retries, client polling by job ID |

`Callable` is usually simpler when only one computation is needed. `DeferredResult` fits when **the completion timing comes from an external event** or is defined by the application. `CompletableFuture` fits pipelines with dependencies and per-stage error handling. Regardless of choice, executor/timeout/backpressure must be deliberate.

Do not use `DeferredResult` to hold millions of long-waiting requests without bounds; each request still consumes HTTP server resources.

## 6. Runnable Spring Boot 3.3.x / Java 17+ Application

The practical example provides two equivalent endpoints:

- `GET /api/reports/deferred/{id}` returning `DeferredResult<ResponseEntity<...>>`.
- `GET /api/reports/future/{id}` returning `CompletableFuture<ResponseEntity<...>>`.

Both require **HTTP Basic solely for local demo purposes**. The example uses the authenticated username **captured on the request thread** before dispatching the task to the executor. Workers do not read `SecurityContextHolder` on their own, avoiding reliance on implicit context propagation.

### 6.1. Directory Structure

```text
servlet-async-demo/
├── build.gradle
└── src/
    ├── main/
    │   ├── java/demo/async/
    │   │   ├── AsyncDemoApplication.java
    │   │   ├── SecurityConfig.java
    │   │   ├── WorkerConfig.java
    │   │   └── ReportController.java
    │   └── resources/application.yml
    └── test/java/demo/async/ReportAsyncTest.java
```

Create `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
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
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`spring-boot-starter-web` uses **Spring MVC Servlet**, not WebFlux. `spring-security-test` supports authenticated testing.

Create `src/main/resources/application.yml`:

```yaml
server:
  address: 127.0.0.1
  port: 8080

spring:
  mvc:
    async:
      request-timeout: 5s
```

The application binds only to loopback for the demo. `spring.mvc.async.request-timeout` sets a global limit for MVC async processing where applicable; a specific limit on `DeferredResult` or `CompletableFuture#orTimeout` may trigger sooner. Do not treat HTTP timeout as a mechanism that automatically terminates workers.

Create `src/main/java/demo/async/AsyncDemoApplication.java`:

```java
package demo.async;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class AsyncDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(AsyncDemoApplication.class, args);
    }
}
```

### 6.2. Spring Security Configuration for the API

Create `src/main/java/demo/async/SecurityConfig.java`:

```java
package demo.async;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    UserDetailsService users() {
        return new InMemoryUserDetailsManager(
                User.withUsername("alice")
                        .password("{noop}demo-only")
                        .roles("READER")
                        .build());
    }

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
                .sessionManagement(session -> session
                        .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/api/reports/**").hasRole("READER")
                        .anyRequest().denyAll())
                .httpBasic(Customizer.withDefaults())
                .build();
    }
}
```

**Never use `{noop}` or hardcoded passwords in source in production.** These are merely test credentials for loopback, not a guide for real login deployment. Production APIs typically accept bearer tokens/OIDC, use TLS, and verify scopes/business permissions. Because the demo endpoints only perform GET, this config does not arbitrarily disable CSRF.

`hasRole("READER")` requires the `ROLE_READER` authority; only requests with valid Basic credentials and the matching role enter the controller. Spring Security performs authorization at the request boundary **before** the controller starts worker tasks.

### 6.3. Explicitly Bounded Application Executor

Create `src/main/java/demo/async/WorkerConfig.java`:

```java
package demo.async;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
public class WorkerConfig {

    @Bean("reportExecutor")
    ThreadPoolTaskExecutor reportExecutor() {
        ThreadPoolTaskExecutor pool = new ThreadPoolTaskExecutor();
        pool.setCorePoolSize(2);
        pool.setMaxPoolSize(4);
        pool.setQueueCapacity(8);
        pool.setThreadNamePrefix("report-worker-");
        return pool;
    }
}
```

Spring manages the lifecycle/initialization of the `ThreadPoolTaskExecutor` bean. The queue is not unbounded: once the two core threads and queue are occupied, the pool can grow up to four threads; if all are busy and the queue is full, submissions may be rejected. This is **backpressure**; do not change to an unbounded queue to hide overload.

The core/max/queue values are illustrative only. Size according to CPU, I/O blocking levels, downstream connection pools, SLOs, memory, and measured load. Never pick `maxPoolSize=1000` thinking more threads automatically mean higher throughput.

### 6.4. Controller for Both Async Styles

Create `src/main/java/demo/async/ReportController.java`:

```java
package demo.async;

import java.security.Principal;
import java.util.Map;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.Executor;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.TimeUnit;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.context.request.async.DeferredResult;

@RestController
public class ReportController {

    private final Executor executor;

    public ReportController(@Qualifier("reportExecutor") Executor executor) {
        this.executor = executor;
    }

    @GetMapping("/api/reports/deferred/{id}")
    public DeferredResult<ResponseEntity<Map<String, String>>> deferred(
            @PathVariable String id, Principal principal) {

        // Capture minimal info while the request is still on the security thread.
        String requestedBy = principal.getName();
        DeferredResult<ResponseEntity<Map<String, String>>> result =
                new DeferredResult<>(1_500L);

        result.onTimeout(() -> result.setErrorResult(unavailable()));
        result.onError(error -> result.setErrorResult(unavailable()));

        try {
            executor.execute(() -> {
                try {
                    result.setResult(buildReport(id, requestedBy));
                } catch (RuntimeException error) {
                    result.setErrorResult(unavailable());
                }
            });
        } catch (RejectedExecutionException rejected) {
            result.setErrorResult(unavailable());
        }

        return result;
    }

    @GetMapping("/api/reports/future/{id}")
    public CompletableFuture<ResponseEntity<Map<String, String>>> future(
            @PathVariable String id, Principal principal) {

        String requestedBy = principal.getName();
        try {
            return CompletableFuture
                    .<ResponseEntity<Map<String, String>>>supplyAsync(
                            () -> buildReport(id, requestedBy), executor)
                    .orTimeout(1_500L, TimeUnit.MILLISECONDS)
                    .exceptionally(error -> unavailable());
        } catch (RejectedExecutionException rejected) {
            return CompletableFuture.completedFuture(unavailable());
        }
    }

    private static ResponseEntity<Map<String, String>> buildReport(
            String id, String requestedBy) {
        // Simulate a short blocking piece of work.
        try {
            TimeUnit.MILLISECONDS.sleep(120);
        } catch (InterruptedException interrupted) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("Report computation interrupted",
                    interrupted);
        }

        return ResponseEntity.ok(Map.of(
                "id", id,
                "requestedBy", requestedBy,
                "status", "ready"));
    }

    private static ResponseEntity<Map<String, String>> unavailable() {
        return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
                .body(Map.of("error", "report unavailable"));
    }
}
```

Key points in the code:

- `principal.getName()` is read **on the servlet request thread** after Spring Security authenticates. The worker receives only the `requestedBy` string; it does not implicitly rely on `SecurityContextHolder`.
- Each request creates its own `DeferredResult`; a worker completes it with `setResult`.
- `CompletableFuture.supplyAsync(..., executor)` uses the **bounded executor**, not occupying the default common pool.
- `orTimeout(1_500L, ...)` affects the future's state; it **does not automatically stop `sleep` or external HTTP requests**.
- `onTimeout`, `onError`, `exceptionally`, and the rejection branch return a consistent error body with status `503` in the demo. Production needs proper error mapping (`429`/`503`/`504` depending on source and contract), retry policies, and correlation IDs.
- `TimeUnit.MILLISECONDS.sleep(120)` simulates **blocking** work. It is not proof that the entire pipeline is non-blocking.
- If timeout and task completion race, only the first result takes effect; a late `setResult` may return `false` and will not alter the HTTP response.
- The app does not leak stack traces in responses. Log errors safely with limited sensitive info, and monitor saturation and timeouts.

This example is intentionally **request-bound**. For operations lasting minutes/hours or needing retries across restarts, do not keep an HTTP request open returning only `DeferredResult`.

## 7. Running and Observing the HTTP Response

Start using the project's Gradle wrapper:

```bash
./gradlew bootRun
```

On Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

Without credentials:

```bash
curl -i http://127.0.0.1:8080/api/reports/deferred/R1
```

Spring Security will reject before the controller runs; with the HTTP Basic demo, the status is typically **401 Unauthorized**.

With local credentials for learning purposes:

```bash
curl -i -u alice:demo-only \
  http://127.0.0.1:8080/api/reports/deferred/R1
```

When the request succeeds, the JSON body looks like:

```json
{
  "id": "R1",
  "requestedBy": "alice",
  "status": "ready"
}
```

Try the future endpoint:

```bash
curl -i -u alice:demo-only \
  http://127.0.0.1:8080/api/reports/future/R2
```

Equivalent JSON body:

```json
{
  "id": "R2",
  "requestedBy": "alice",
  "status": "ready"
}
```

JSON property ordering is not guaranteed because Java `Map.of(...)` has no ordering contract. The request ID value comes from what you pass in the URL. Never print Basic passwords or bearer tokens to production logs; the two `curl -u` commands over **HTTP loopback are for demo only**. Real network access requires HTTPS and appropriate credential mechanisms.

You cannot conclude from the client response alone that the servlet thread was released: check metrics/thread traces, async request lifecycle, and executor configuration.

## 8. Testing Spring Security + MockMvc Async Dispatch

With Spring MVC async, tests should not stop at the controller returning `DeferredResult`: verify the **async dispatch phase** once the worker result is ready.

Create `src/test/java/demo/async/ReportAsyncTest.java`:

```java
package demo.async;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.asyncDispatch;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.request;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ReportAsyncTest {

    @Autowired
    MockMvc mvc;

    @Test
    void unauthenticatedRequestIsRejectedBeforeAsyncWork()
            throws Exception {
        mvc.perform(get("/api/reports/deferred/R1"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void deferredResultCompletesWithCapturedPrincipal()
            throws Exception {
        MvcResult pending = mvc.perform(
                        get("/api/reports/deferred/R1")
                                .with(httpBasic("alice", "demo-only")))
                .andExpect(request().asyncStarted())
                .andReturn();

        mvc.perform(asyncDispatch(pending))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value("R1"))
                .andExpect(jsonPath("$.requestedBy").value("alice"));
    }

    @Test
    void completableFutureCompletesWithCapturedPrincipal()
            throws Exception {
        MvcResult pending = mvc.perform(
                        get("/api/reports/future/R2")
                                .with(httpBasic("alice", "demo-only")))
                .andExpect(request().asyncStarted())
                .andReturn();

        mvc.perform(asyncDispatch(pending))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value("R2"))
                .andExpect(jsonPath("$.status").value("ready"));
    }
}
```

Run:

```bash
./gradlew test
```

This test verifies three things:

1. Requests without Basic credentials cannot cross the authorization boundary.
2. MVC started asynchronous processing (`asyncStarted`).
3. The result completed in the `asyncDispatch` step, with the captured principal intact.

MockMvc does not replace real stress tests against Tomcat and downstream I/O; it does not prove the app properly handles client disconnects, network speeds, queue saturation, or timeout races. Add tests using a stub executor that deliberately completes slowly or rejects to verify `503`, and run bounded concurrency tests in staging.

## 9. The Spring Security Issue: `SecurityContextHolder` Is Thread-Bound

Under the default configuration, `SecurityContextHolder` typically uses `ThreadLocal` to store `SecurityContext`. That means:

```java
// On the servlet thread:
String user = SecurityContextHolder.getContext()
        .getAuthentication().getName();
```

is not guaranteed to behave the same as:

```java
// On a thread submitted manually by the application:
executor.execute(() -> {
    Authentication a =
            SecurityContextHolder.getContext().getAuthentication();
    // a may be null; do not assume the request's user is still present.
});
```

Both snippets merely illustrate the API and need corresponding imports; a worker lambda is not a request handler that automatically carries context. Returning `DeferredResult` or `CompletableFuture` **does not automatically propagate `SecurityContext`** into arbitrary application-managed threads.

If a worker uses a security context leaked from a previous task, the risk is even worse: user B's request might execute with user A's privileges. Never set a request's `SecurityContext` on a worker thread without guaranteeing restore/clear in `finally`.

### Recommended Approach When the Worker Only Needs a User ID

Read identity and minimal immutable facts **while the request is still under Spring Security's control**:

```java
@GetMapping("/api/example")
public DeferredResult<String> example(Principal principal) {
    String requestedBy = principal.getName();
    DeferredResult<String> output = new DeferredResult<>(2_000L);
    executor.execute(() -> output.setResult("requester=" + requestedBy));
    return output;
}
```

This snippet is illustrative only: place it in a controller with a configured `executor` and handle timeouts/rejections in production. Never pass raw `HttpServletRequest`, `HttpSession`, or the entire mutable authentication object to a task unless genuinely needed.

Captured data can **become stale** if permissions are revoked while a very long job runs. For sensitive operations like funds transfers or multi-tenant data exports, the service should re-verify permissions/ownership when executing the change, rather than relying solely on privileges captured when the HTTP request arrived.

## 10. When the Worker Genuinely Needs `SecurityContext`

Spring Security provides executor wrappers such as:

- `DelegatingSecurityContextExecutor`
- `DelegatingSecurityContextAsyncTaskExecutor`
- Similar wrappers for `ExecutorService`, `Runnable`, and `Callable`.

With `AsyncTaskExecutor` in a Spring Boot application:

```java
@Bean("securityAwareReportExecutor")
AsyncTaskExecutor securityAwareReportExecutor(
        @Qualifier("reportExecutor")
        ThreadPoolTaskExecutor delegate) {
    return new DelegatingSecurityContextAsyncTaskExecutor(delegate);
}
```

This is a **method snippet inside `@Configuration`**, requiring additional imports:

```java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.core.task.AsyncTaskExecutor;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.security.task.DelegatingSecurityContextAsyncTaskExecutor;
```

The decorator can capture the caller's `SecurityContext` when the task is submitted, set it while the worker runs, and restore/clear it afterward. Use the wrapper properly; **never** invent a global `ThreadLocal` to hold the user. Also never pin a single admin `SecurityContext` for all tasks when permissions should be per-request.

Note that this is **not** an independent authorization mechanism. When intending to use `SecurityContextHolder` inside a worker:

1. The controller must be protected by `SecurityFilterChain` before submission.
2. Tasks must be submitted within the proper execution context when the wrapper captures authentication.
3. Permissions can change after the task starts; business services must still check permissions at the right moment.
4. Executors and context propagation must be clearly scoped, never allowing credentials/tokens to be logged or passed to untrusted work.
5. If a task must run very long or survive process restarts, **do not** carry the request's `SecurityContext` as a long-term source of authority.

Spring Security has dedicated integration for Spring MVC async **`Callable`** (for example, `WebAsyncManagerIntegrationFilter` assists context when processing Callables on MVC's executor), yet that mechanism **does not mean** every `DeferredResult` completion callback, arbitrary worker thread, or `CompletableFuture.supplyAsync` receives automatic context propagation.

## 11. Request Timeout and Task Timeout Are Two Different Things

There are multiple kinds of deadlines:

| Deadline | Managed By | What Happens on Expiration |
| --- | --- | --- |
| Servlet/MVC async request timeout | Container/Spring MVC or `DeferredResult(timeout)` | HTTP request may complete in an error/timeout state |
| `CompletableFuture.orTimeout(...)` | Future state | Future completes exceptionally, **underlying task may keep running** |
| HTTP client read/connect timeout | Downstream HTTP client | A specific I/O call may stop/error |
| Database statement/query timeout | DB driver or database | A query may be cancelled/errored per driver mechanism |
| Business deadline | Business workflow | Decides whether late task completion is allowed or must roll back/cancel |

In the example code, the HTTP/deferred timeout is 1.5 seconds and the MVC default is 5 seconds. The request may return an error due to the 1.5-second deadline, yet a worker stuck on I/O can still occupy an executor slot.

For real blocking work, **configure downstream client timeouts**, bound queues, consider feasible cancellation, and make business operations idempotent. Never treat `setErrorResult(503)` as proof the backend stopped all side effects.

Late-result check example:

```java
boolean accepted = deferredResult.setResult(value);
if (!accepted) {
    // Request already completed via another branch: do not try to write the response again.
}
```

This snippet assumes `deferredResult` and `value` are in scope. If the job updates data, the response timing out **does not automatically reverse a commit** that already occurred in the database.

## 12. Errors, Saturation, and Backpressure

A common production mistake is creating an executor with an unbounded queue. When downstream slows down and HTTP requests keep arriving, the queue grows rapidly and consumes RAM even though the initial servlet thread was released.

The demo executor has `core=2`, `max=4`, `queueCapacity=8`. When the queue is full and all four workers are busy, new tasks can fail with `RejectedExecutionException`/`TaskRejectedException`; the controller should return **503 or a designed backpressure status** rather than spawning unlimited threads.

Monitor real metrics:

- active task count, queue depth, and queue age;
- rejections per minute, request timeouts, and downstream timeouts;
- p50/p95/p99 latency at endpoints and per dependency;
- open async requests, Tomcat worker utilization, and DB connection pool;
- tasks completing **after the HTTP response already timed out**.

A `CompletableFuture` pipeline with multiple `thenApplyAsync` stages that omit an executor can shift work onto the common pool even if the first stage used a custom pool. Pass the executor at every async stage when consistent resource policy is needed.

**Never use request/user input as a parameter to create new thread pools.** Use managed, metered, and bounded executors at the service level. If a job can take minutes, move to a job queue architecture rather than holding thousands of async contexts.

## 13. `@Async`, `@Transactional`, and Thread-Bound State

`@Async` is a Spring mechanism to execute a method through a configured proxy/executor. It is not `DeferredResult`; a controller can combine them yet must still adhere to the HTTP contract.

For applications using `@Transactional`:

```java
@Transactional
public Report loadReport(String id) {
    return reportRepository.findById(id).orElseThrow();
}
```

This is an **illustrative method**, assuming `Report`, `reportRepository`, and transaction management exist. Transactions are normally thread-bound; when a request thread submits a task, the current transaction **does not automatically propagate to the worker**. Workers invoke properly proxied `@Transactional` services to open a new transaction when needed.

Do not hold a managed JPA entity from the request thread and access lazy relationships on a worker after the transaction has closed. This can trigger `LazyInitializationException` or data races. Pass immutable IDs/data, open a transaction inside the worker's service, and build a materialized DTO.

With `@Async`, watch out for **self-invocation**: calling an `@Async` method from another method in the **same instance** typically bypasses the Spring proxy, causing synchronous execution. When explicit task orchestration is needed, configure an executor and call through the proper bean/proxy.

Long-running background tasks should also avoid keeping a transaction open across a slow HTTP call; wrap transactions only around the necessary read/write units.

## 14. MDC, Tracing, and Request-Scoped Data

Beyond `SecurityContext`, many applications use MDC (`traceId`, `correlationId`), locale, tenant context, or request attributes via `ThreadLocal`. They **do not automatically propagate safely** to a thread pool just because a controller returns `CompletableFuture`.

A simple approach is passing minimal normalized values in an immutable context object, for example:

```java
public record WorkContext(
        String principalId,
        String tenantId,
        String correlationId) {}
```

This is a **standalone Java record** that can be saved in `WorkContext.java` in the application's package. Include only necessary data—never raw access tokens, cookies, or full HTTP headers.

If automatic MDC/tracing is needed, use a task decorator or context propagation solution compatible with your Spring/observability stack; always clear `ThreadLocal` in `finally`. For tracing, rely on supported context propagation libraries and avoid duplicating trace baggage containing sensitive data.

Never access `RequestContextHolder.currentRequestAttributes()` inside a worker assuming request attributes still exist. The Servlet request may already have timed out/completed, and reading streams/bodies/sessions on a worker after completion is unsafe.

## 15. Async Dispatch and the Servlet Filter Chain

Once MVC starts async, a subsequent dispatch usually finishes response processing. Servlet filters have **dispatcher types** configuration and can run on `REQUEST`, `ASYNC`, and `ERROR` differently.

A few notes:

- `OncePerRequestFilter` and Spring Security filters have specific logic for async dispatch. **Do not assume** a filter runs exactly once or exactly twice across every container/configuration.
- A security rule protecting a controller is not bypassed just because the return type is `DeferredResult`.
- Async redispatch does not mean another request's `Authentication` may be reused.
- Never call `SecurityContextHolder.clearContext()` on the servlet request thread to "clean up" the worker's context; Spring Security and executor wrappers have separate lifecycles. If you manually set context on a worker, **the worker itself must restore/clear in `finally`**.
- Test `401` for unauthenticated requests up front, then test `asyncDispatch` for authorized requests. With multiple filter chains/dispatcher mappings, test against real Tomcat when modifying filter registrations.

Older Servlet libraries lacking async support or filter registrations missing `asyncSupported` can trigger `Async support must be enabled`. Spring Boot auto-configures many required pieces, yet custom Servlet filters must still declare async support properly when participating in this path.

## 16. Using `DeferredResult` to Wait for External Events

Another scenario beyond `supplyAsync` is waiting for an event from a message broker or notification:

```java
// Architectural example, not a complete controller:
DeferredResult<String> waiting = new DeferredResult<>(5_000L);
pendingRequests.put(correlationId, waiting);
waiting.onCompletion(() -> pendingRequests.remove(correlationId));
return waiting;
```

When the consumer receives an event with a valid `correlationId`:

```java
DeferredResult<String> waiting =
        pendingRequests.remove(event.correlationId());

if (waiting != null) {
    waiting.setResult(event.payload());
}
```

These snippets are illustrative: they assume `pendingRequests`, `correlationId`, and `event` with matching APIs. In production, **never use an unguessable correlation ID as the sole authorization mechanism**. Ensure events belong to the right principal/tenant, cap pending request counts, clean up on timeout/error to prevent memory leaks, and account for events arriving before/repeatedly/after the request closes.

If the application runs multiple replicas, an in-memory map on node A is not automatically visible to a consumer on node B. When long polling truly needs to scale, design appropriate routing, an event store/broker, or shared coordination. Consider cursor-based DB queries if suitable instead of holding masses of pending futures.

## 17. When to Return `202 Accepted` Instead of Holding the HTTP Connection?

Even though async Servlet releases the request thread, **the connection is still waiting**. Long operations can be cut off by timeouts at the browser, load balancer, ingress, or API gateway before the application produces a result.

For jobs running several minutes, needing easy retries, or requiring durability across instance restarts:

```text
POST /api/report-jobs
    |
    v
Check Authentication + Authorization
    |
    v
Persist job record and enqueue durable message
    |
    v
202 Accepted
Location: /api/report-jobs/{jobId}
    |
    v
Independent worker runs job, updates status
    |
    v
GET /api/report-jobs/{jobId}
    -> QUEUED / RUNNING / SUCCEEDED / FAILED
```

In this model, the user/caller must be authenticated and authorized to **create the job**, and then authorized to **view that job's result**. Never let user A guess user B's job ID and download a cross-tenant report. Use idempotency keys and transactions/outbox when consistency between DB and queue is required.

`DeferredResult` fits short-waiting requests with clear deadlines and bounded resources. Job queues fit tasks needing durability, independent coordination, and recovery after failure.

## 18. Common Issues and How to Verify

| Symptom | Common Cause | Fix |
| --- | --- | --- |
| Servlet thread still stays busy for long | Controller blocks before returning `DeferredResult` | Move slow work to an executor or callback; only create the object on the request thread |
| Many requests lead to OOM | Unbounded queue/pending DeferredResults | Bounded executor, limit concurrent requests, and clean up |
| `SecurityContextHolder` inside worker is `null` | Context is bound to request thread | Capture minimal data or use a security-context-aware executor |
| User B sees user A | Leaked ThreadLocal/SecurityContext/tenant cache | Restore/clear context, scope per request, and test concurrency |
| HTTP response times out yet work keeps running | Timeout only closes request/future, does not cancel downstream I/O | Design cancellation, downstream deadlines, and idempotency |
| `CompletableFuture` unexpectedly runs on common pool | Missing executor on `supplyAsync`/`Async` stages | Pass explicit executor |
| 503 under high load | Pool/queue saturated | Measure queue/active/rejections, optimize throughput and backpressure |
| `MockMvc` only checks initial status | `asyncDispatch` not called | Use `request().asyncStarted()` then `asyncDispatch(result)` |
| `@Async` method actually runs on same thread | Self-invocation bypasses Spring proxy | Move method to another bean/call through proxy |
| `LazyInitializationException` in worker | JPA context/transaction does not cross threads | Pass ID/DTO; open dedicated transaction in worker service |
| Correlation ID lost when switching threads | MDC/trace context not propagated | Task decorator, context propagation library, cleanup |
| User lost permission yet job still modifies data | Authorization checked only when request arrived | Re-check permissions/tenant at commit time when appropriate |
| `setResult` after timeout does not change response | Request already completed on another branch | Check boolean completion and clean up safely |
| `asyncSupported` exception | Custom Servlet filter incompatible with async | Check filter registration/dispatcher types |

### Short Investigation Procedure

1. Confirm whether the request passed through Spring Security and was authorized.
2. Verify whether the controller returned the async return type before slow work ran.
3. Inspect which executor actually runs the task; verify active threads and queue are bounded.
4. Check which deadline fires first: MVC, proxy, HTTP client, DB, or future.
5. Check whether request timeouts leave background tasks/side effects running.
6. Inspect how `Authentication`, tenant, and trace context are created/propagated/cleared.
7. Re-test end-to-end with unauthenticated requests, authenticated-but-unauthorized requests, timeouts, rejections, client disconnects, and concurrent users.

## 19. Safe Deployment Checklist

- Choose `DeferredResult` when **an application event signals completion**, `CompletableFuture` when composing stages; do not confuse Servlet async with non-blocking I/O.
- Never perform blocking I/O on the servlet thread before returning the async result.
- Use a bounded executor with thread naming, metrics, shutdown, and proper backpressure.
- Configure HTTP timeouts, downstream timeouts, timeout/completion race handling, and cancellation policies.
- Catch/sanitize worker errors; never return internal exceptions or tokens/PII to clients.
- Spring Security authenticates and authorizes requests before starting tasks.
- Pass principal/tenant safely; do not assume `SecurityContextHolder` is automatically present on workers.
- If using security context propagation, use standard wrappers and guarantee restore/clear.
- Pass only immutable DTOs/IDs across threads; transactions, JPA persistence contexts, and request scope do not propagate automatically.
- Test `asyncDispatch`, 401/403, 503/rejection, timeouts, session/context leaks, and concurrent users.
- Bound pending futures, queues, and event listeners; clean up on request timeout/completion.
- For long jobs or work requiring durability across restarts, use a job queue + `202 Accepted` instead of keeping HTTP requests open.

## Key Takeaways

`DeferredResult` tells Spring MVC that **the application will decide when the response is ready**. `CompletableFuture` describes **a computation/async-task pipeline** that MVC can use to complete a response asynchronously. Both allow releasing the initial servlet thread, yet **they do not provide free worker threads, do not automatically cancel tasks after timeout, do not guarantee non-blocking I/O, and do not automatically propagate `SecurityContext` to application-managed threads**. Proper design requires bounded executors, timeouts and error handling, safe identity passing, async dispatch testing, and choosing a job queue whenever work outlives the HTTP request lifecycle.