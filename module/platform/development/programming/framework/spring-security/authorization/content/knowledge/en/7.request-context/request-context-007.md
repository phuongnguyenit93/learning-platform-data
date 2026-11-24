# AsyncContext, Executors, and the Limits of Context Propagation in Spring Security

## 1. Goal: Request Context Does Not Automatically Follow Every Async Job

A request arrives at a Spring Boot API authenticated as **Alice**. The controller can read:

```java
Authentication authentication =
        SecurityContextHolder.getContext().getAuthentication();
```

However, after the controller hands work off to another thread, is `Authentication` still available there? The answer depends not only on the task being "asynchronous", but also on **who creates the task, who submits it to an executor, which Spring Security integration ran, and when the context was captured**.

Three situations must be separated:

1. **Servlet `AsyncContext.start(Runnable)`**: Spring Security integrates to propagate `SecurityContext` to a `Runnable` launched via the request/async context wrapper inside the proper filter chain.
2. **Spring MVC returning `Callable<T>`**: Spring Security integrates with `WebAsyncManager` and automatically sets `SecurityContext` on the thread executing the `Callable` via MVC async mechanics.
3. **`DeferredResult<T>`, `Executor`, `@Async`, `CompletableFuture`, or manually created threads**: do not assume they share the same `SecurityContext`; usually an explicit context-propagation mechanism is required, such as `DelegatingSecurityContextExecutor` or `DelegatingSecurityContextAsyncTaskExecutor`.

**Lesson goal:** understand the path `SecurityContextHolder → task → worker thread → cleanup`, choose the right API, prevent identity leaks between tasks of different users, distinguish security context from request context/transactions, and recognize the security limits of "copying identity".

Content targets **Spring Security Servlet/Spring MVC on Java 17+**, not a separate guide for Spring WebFlux Reactor Context. Examples marked as "fragments" must be placed inside a Spring Boot project with suitable dependencies/config; the standalone Java 17 example later includes compile commands and stdout.

## 2. Objects to Understand Accurately

| Component | Role | Propagates automatically across arbitrary threads? |
| --- | --- | --- |
| `SecurityContextHolder` | Access point for the current security context | **No**, ThreadLocal-based by default |
| `SecurityContext` | Object holding `Authentication` | Can be propagated via wrappers, but does not follow every API automatically |
| `Authentication` | Identity, authentication status, `GrantedAuthority` | Data inside `SecurityContext`, does not replace policy |
| `HttpServletRequest` | HTTP context of the request | Does not automatically stay a valid request for a background job |
| `AsyncContext` | Controls async lifecycle of Servlet request/response | Has propagation integration when using `AsyncContext.start` properly |
| `WebAsyncManager` | Manages Spring MVC Servlet async processing | Has integration for MVC `Callable` |
| `Executor`/`ExecutorService` | Infrastructure running tasks on other threads | **Does not** propagate SecurityContext automatically |
| `DelegatingSecurityContextRunnable` | Wraps a `Runnable` with the context to use | Yes: installs on worker then cleans up |
| `DelegatingSecurityContextExecutor` | Wraps tasks submitted to an `Executor` | Yes: captures context per constructor/config style |
| `DelegatingSecurityContextAsyncTaskExecutor` | Wraps `Runnable`/`Callable` for Spring `AsyncTaskExecutor` | Yes: supports async tasks when using the right executor |

**Key perspective:** `SecurityContext` is not the "request", not the "session", does not revive transactions, and does not guarantee the principal still holds permissions when the task actually executes. Propagation solves *putting information onto the right thread*, while business authorization must still be checked by trustworthy policies.

### 2.1. Context Created on a Request Thread

Example request `GET /api/reports/r7` after authentication:

```text
Servlet thread: http-nio-8080-exec-2

SecurityContextHolder
  └─ SecurityContext
       └─ Authentication
           ├─ principal: alice
           ├─ authenticated: true
           └─ authorities: [ROLE_USER, report:read]
```

When code hands execution off to a pooled worker:

```text
Worker thread: report-pool-1

SecurityContextHolder
  └─ No Authentication for Alice
     (without a propagation mechanism)
```

If the worker tries to use `@PreAuthorize("hasAuthority('report:read')")`, it may be denied because there is no valid identity. More dangerously, if legacy code manually called `setContext` without cleaning up, the worker can accidentally retain the previous request's context while serving a new request.

### 2.2. SecurityContextHolder Normally Uses ThreadLocal

Spring Security defaults to `SecurityContextHolder.MODE_THREADLOCAL`. Within the same thread, code can access `SecurityContextHolder.getContext()` without passing parameters through every function.

This is convenient yet has **thread boundaries**:

- Creating a task on thread A does not automatically attach A's context to thread B.
- A thread pool can reuse B for many different users.
- After a request, Spring Security clears context in the filter chain to prevent leaks on servlet threads.
- Workers created outside the filter chain must take responsibility for setting and **clearing/restoring** context safely.

**Do not infer that an authenticated request means every task spawned from that request is authenticated.**

## 3. Matrix: Which Asynchronous Flows Are Automatically Supported?

| Processing style | Execution mechanism | SecurityContext propagated automatically? | Appropriate action |
| --- | --- | --- | --- |
| Synchronous code inside controller/service | Same request thread | Usually yes | Check permissions in web/service |
| Servlet `AsyncContext.start(Runnable)` | Runnable via Spring Security-wrapped Servlet async context | **Yes in properly integrated configs** | Ensure async support, lifecycle, and tests |
| MVC controller returns `Callable<T>` | Spring WebAsyncManager + Spring Security integration | **Yes** for the thread executing Callable | Use MVC async API properly |
| MVC controller returns `DeferredResult<T>` | Task completed manually by the app | **Not automatic for user tasks** | Wrap executor or task |
| `CompletableFuture.supplyAsync(...)` without executor | ForkJoin common pool | **Not by default** | Pass an appropriate context-aware executor |
| `new Thread(...)` | Manually created thread | **Not by default** | Avoid ad-hoc threads; wrap if forced to use |
| `ExecutorService.submit(...)` | Pooled worker | **Not by default** | Wrap `ExecutorService`/task |
| `@Async` | Spring `TaskExecutor` | **Only when executor is configured to propagate context** | Use `DelegatingSecurityContextAsyncTaskExecutor`/equivalent |
| `@Scheduled` | Request-independent scheduler | No natural user request | Use service identity + explicit policy |
| Message consumer/queue job | Process/request-independent worker | Not propagated via HTTP ThreadLocal | Pass minimal trusted actor info and re-authenticate/authorize |

**Version note:** modern Spring Security Servlet docs explicitly describe integration with `AsyncContext.start` and Spring MVC `Callable`, while stating there is **no auto integration for `DeferredResult`** because the application controls execution itself. This is an API/lifecycle distinction, not a bug where you need to "flip an extra flag" for every task type.

## 4. Servlet AsyncContext: Different from Calling new Thread Yourself

### 4.1. AsyncContext Keeps Request/Response Open

Servlet asynchronous processing allows a controller/filter to leave the initial thread without finishing the response yet. Calling:

```java
AsyncContext async = request.startAsync();
```

marks the request as switching to async mode. Afterward you can use:

- `async.start(Runnable)`: ask the container to run a task bound to the async request.
- `async.dispatch(...)`: request dispatching back to Servlet processing when appropriate.
- `async.complete()`: finish the async response.
- `async.setTimeout(...)` and `AsyncListener`: manage timeout/lifecycle.

**Do not confuse `async.start(...)` with `executor.execute(...)`:** although both run code on another thread, Spring Security has dedicated propagation integration for `AsyncContext.start(Runnable)` along a Servlet request path processed by security wrappers. A self-created `Executor` does not automatically receive that integration.

### 4.2. Why Can Spring Security Propagate in AsyncContext.start?

Per Spring Security docs, the framework wraps `AsyncContext` so when you call `async.start(Runnable)`, the `Runnable` runs with the appropriate `SecurityContext` present at handoff time. Under the hood is a wrapper mechanism akin to `DelegatingSecurityContextRunnable`.

Model:

```text
REQUEST thread (alice)
    │
    ├─ request.startAsync()
    │
    └─ async.start(runnable)
          │
          └─ Spring Security/Servlet integration
               ├─ capture context
               ├─ worker thread: set context Alice
               ├─ runnable.run()
               └─ cleanup SecurityContextHolder
    │
    └─ original request thread can return to pool
```

This does **not** mean every `Runnable` launched via `new Thread` after `request.startAsync()` gets propagated. Wrapping applies only when going through the proper integration API.

### 4.3. Servlet Fragment Example

The following goes inside a Spring-managed controller with an appropriate GET mapping using the Jakarta Servlet API. This is an **integration fragment**, omitting imports, the enclosing class, security config, and exception handlers:

```java
@GetMapping("/api/me/async")
public void readCurrentUser(HttpServletRequest request) {
    AsyncContext async = request.startAsync();
    async.setTimeout(10_000L);

    async.start(() -> {
        HttpServletResponse response =
                (HttpServletResponse) async.getResponse();
        try {
            Authentication authentication =
                    SecurityContextHolder.getContext().getAuthentication();

            if (authentication == null || !authentication.isAuthenticated()) {
                response.setStatus(HttpServletResponse.SC_UNAUTHORIZED);
            } else {
                response.setStatus(HttpServletResponse.SC_OK);
                response.setContentType("text/plain;charset=UTF-8");
                response.getWriter().write(authentication.getName());
            }
        } catch (IOException ex) {
            // Integrate with project logging/error policy;
            // do not log secrets or tokens.
            throw new UncheckedIOException(ex);
        } finally {
            async.complete();
        }
    });
}
```

Types to import per project include `jakarta.servlet.AsyncContext`, `jakarta.servlet.http.HttpServletRequest`, `HttpServletResponse`, `IOException`, `UncheckedIOException`, and Spring Security types. The response/writer can fail due to client disconnects; the example ensures `async.complete()` is called in `finally`, yet does **not** replace production error handling or timeout listeners. If code has multiple timeout/cancellation paths, avoid uncontrolled duplicate `complete()` calls.

The **security rule** for that route must still require authentication:

```java
.requestMatchers(HttpMethod.GET, "/api/me/async").authenticated()
.anyRequest().denyAll()
```

A worker thread being able to read `Authentication` does not ensure the route is protected if HTTP config accidentally places an overly broad `permitAll` ahead of it.

### 4.4. Servlet Async Support Conditions

With Servlet 3.x+/corresponding Spring Boot setups, involved servlets/filters must support async. With manually managed `web.xml`, `async-supported=true` and appropriate dispatcher mappings (such as REQUEST and ASYNC) for `springSecurityFilterChain` are needed if required by runtime. In modern Boot Java config, standard Spring Security usually supports it already, yet **custom filters or container configs** can cause `request.startAsync()` to fail due to unsupported async.

Check:

- `request.isAsyncSupported()` when diagnosing.
- Actual Filter/Servlet registrations and applied `DispatcherType`s.
- Timeouts, cancellations, and response I/O errors.
- Security filters handling async redispatches per configuration.
- Never accessing request/response after lifecycle completion.

### 4.5. AsyncContext Is Not a Long-Running Work Queue

An async HTTP request remains bounded by **request lifetime**, timeouts, client connections, and container resources. Never hold `AsyncContext` open for minutes or hours just to send emails, extract video, or run long batch jobs.

If work must survive client disconnection, use a dedicated queue/job, return `202 Accepted` with a job ID, and enforce authorization when creating the job and when querying results. **Never place the raw `SecurityContext` and `HttpServletRequest` into a queue.**

## 5. Spring MVC Callable: Has Automatic Integration Support

### 5.1. Callable Is an MVC-Managed Async Result

Spring MVC lets controllers return `Callable<T>`. The framework offloads `Callable.call()` to MVC's executor and completes the response afterward. Spring Security integrates with `WebAsyncManager` to supply `SecurityContext` to the thread executing `Callable`.

Example:

```java
@GetMapping("/api/me/callable")
public Callable<ResponseEntity<String>> currentUser() {
    return () -> {
        Authentication authentication =
                SecurityContextHolder.getContext().getAuthentication();

        if (authentication == null || !authentication.isAuthenticated()) {
            return ResponseEntity.status(401).body("Unauthenticated");
        }
        return ResponseEntity.ok(authentication.getName());
    };
}
```

This is a fragment inside a Spring MVC controller, not a standalone runnable Java program. `ResponseEntity` comes from Spring Web and `Callable` from `java.util.concurrent`. With default integration, `Callable` runs on an MVC-managed thread yet has the current `SecurityContext`.

**Exact capture point:** documentation notes the `SecurityContext` bound to `Callable` is the context in `SecurityContextHolder` when `WebAsyncManager.startCallableProcessing` is invoked, not an arbitrary context at some later instant.

### 5.2. What Does WebAsyncManagerIntegrationFilter Do?

Spring Security includes `WebAsyncManagerIntegrationFilter`, which integrates with Spring MVC's `WebAsyncManager` via `SecurityContextCallableProcessingInterceptor`. Its role is supporting context during `Callable` processing.

Learners do not need to manually add a `new WebAsyncManagerIntegrationFilter()` in default configurations where Spring Security already registers the required component. When customizing security filter chains or altering many framework defaults, run integration tests before manually adjusting filter ordering.

### 5.3. Do Not Assume Every Callback Inside Callable Has Context

If inside `Callable.call()` you also do:

```java
return () -> {
    CompletableFuture<String> nested =
            CompletableFuture.supplyAsync(() ->
                    SecurityContextHolder.getContext()
                            .getAuthentication().getName());
    return ResponseEntity.ok(nested.join());
};
```

A context-integrated `Callable` **does not mean** a new task started by `supplyAsync` on the common pool also has context. You may hit `NullPointerException` or an empty principal. If nested tasks are needed, use a context-aware executor properly, or pass minimal identity data to the service with validation.

### 5.4. Authorization Inside Callable Still Needs the Right Enforcement Point

A controller protected by `hasAuthority("report:read")` may return a `Callable` to read a report. Yet if the service inside `Callable` must verify owner/tenant, that policy must run in the **executing service**, rather than relying solely on the controller having been entered earlier.

When using `@PreAuthorize` on a Spring-managed service bean, ensure the call goes through the Spring proxy and security context has been propagated. If a controller/bean calls an internal `@PreAuthorize` method via self-invocation, the interceptor can be bypassed; not directly tied to async, yet a risk worth testing.

## 6. DeferredResult: Application Completes It Manually, So No Auto Propagation

### 6.1. DeferredResult Differs from Callable in Task Ownership

Spring MVC `DeferredResult<T>` allows a controller to immediately return a **handle awaiting a result**. The application chooses whichever callback, thread, executor, message listener, or event will call `setResult(...)`/`setErrorResult(...)`.

Because Spring does not control that arbitrary execution, Spring Security **does not automatically propagate `SecurityContext` for work completing DeferredResult**. This is explicitly stated in Spring Security MVC documentation.

```text
MVC Callable:
  MVC owns Callable execution
  → Spring Security has an integration hook

MVC DeferredResult:
  Application owns result completion
  → application must decide propagation
```

### 6.2. Wrong Example: Raw Executor in DeferredResult

```java
@GetMapping("/api/reports/{id}/deferred")
public DeferredResult<ResponseEntity<String>> read(@PathVariable String id) {
    DeferredResult<ResponseEntity<String>> result =
            new DeferredResult<>(5_000L);

    plainExecutor.execute(() -> {
        Authentication a =
                SecurityContextHolder.getContext().getAuthentication();
        // a may be null or not carry the request's principal.
        result.setResult(ResponseEntity.ok(a.getName()));
    });
    return result;
}
```

This is an **illustrative anti-pattern**, not production code: `plainExecutor` is an ordinary executor; `a.getName()` can throw. Even though the controller was authorized, the task on that executor does not automatically get SecurityContext.

### 6.3. Using a Context-Aware Executor When Completing DeferredResult

Suppose an `Executor` named `securityContextExecutor` is injected, created with `DelegatingSecurityContextExecutor` (see section 7):

```java
@GetMapping("/api/reports/{id}/deferred")
public DeferredResult<ResponseEntity<String>> read(@PathVariable String id) {
    DeferredResult<ResponseEntity<String>> result =
            new DeferredResult<>(5_000L);

    securityContextExecutor.execute(() -> {
        try {
            // This must be a Spring-managed service with real policy:
            String data = reportService.loadVisibleReport(id);
            result.setResult(ResponseEntity.ok(data));
        } catch (Exception ex) {
            result.setErrorResult(ex);
        }
    });

    return result;
}
```

This is a controller fragment with `securityContextExecutor` and `reportService` dependency-injected. Method name `loadVisibleReport` merely illustrates business intent; the project must implement and enforce permissions on the report. The wrapped executor captures context upon submission and installs it on the worker before calling the service.

**Boundary:** `setResult` completes the response and does not create new permissions. If the user's permission was revoked while the task waited, a policy must re-check against current permission data when business logic executes. Use timeout callbacks and check `result.isSetOrExpired()`/version-appropriate lifecycle checks so late work does not cause unwanted side effects.

### 6.4. DeferredResult Is Not a Durable Background Job

When an HTTP client disconnects or a request times out, setting a result may no longer matter. For long-running tasks, return `202` with a job ID and track outcomes via a separate endpoint. When accessing results, **verify owner/tenant/job scope**, rather than relying solely on the token once present on the initiating request.

## 7. DelegatingSecurityContextRunnable and Callable

### 7.1. Spring Security's Standard Wrapper Mechanism

`DelegatingSecurityContextRunnable` is a helper class in package `org.springframework.security.concurrent`. Conceptually, it does:

```java
public void run() {
    try {
        SecurityContextHolder.setContext(contextForTask);
        actualRunnable.run();
    } finally {
        SecurityContextHolder.clearContext();
    }
}
```

The code above is **simplified pseudocode of the mechanism**, not full source or a promise about every internal detail across all versions. The crucial aspect is **try/finally cleanup**: even if the task throws an exception, the worker must never accidentally retain the old context for the next task.

### 7.2. Wrapping a Runnable Explicitly

```java
SecurityContext captured = SecurityContextHolder.getContext();

Runnable actualTask = () -> reportService.generateAllowedReport();

Runnable securedTask =
        new DelegatingSecurityContextRunnable(actualTask, captured);

executor.execute(securedTask);
```

This is an integration fragment; `executor` and `reportService` must exist. When submitting the task, the caller's context is specified explicitly. If the service uses `@PreAuthorize`, ensure the bean is invoked via its proxy.

There is a shortcut constructor:

```java
Runnable securedTask =
        new DelegatingSecurityContextRunnable(actualTask);
```

This form uses the context from `SecurityContextHolder` when the wrapper is constructed per class contract. **Never construct a wrapper once at application startup and reuse it across requests of different users**, because then the context may not belong to the current request's user.

### 7.3. Callable Has a Matching Wrapper

`DelegatingSecurityContextCallable<V>` wraps `Callable<V>`. When work returns a result or throws an exception, Spring Security handles setting/cleaning up context on the worker per wrapper contract.

```java
Callable<String> actual = () -> reportService.getCurrentUserReport();

Callable<String> secured =
        new DelegatingSecurityContextCallable<>(actual);

Future<String> future = executorService.submit(secured);
```

This snippet is an integration fragment, appropriate only when `executorService` is a managed JDK `ExecutorService`. Avoid unbounded `future.get()` on request threads if the goal is asynchrony; use timeouts/cancellation or MVC async APIs so servlet threads are not blocked.

### 7.4. Wrappers Do Not Do Business Work for You

They do not:

- Re-verify access tokens at the moment the worker starts.
- Automatically check `report:read` or tenant/owner.
- Automatically renew expired JWTs.
- Automatically supply transactions, request scope, MDC, locale, or tracing context.
- Automatically record exceptions into audit logs.
- Guarantee the caller still holds permissions after logout or role revocation.

**Context propagation is an authentication-data transport mechanism, not an authorization policy.**

## 8. DelegatingSecurityContextExecutor and ExecutorService

### 8.1. A Raw Executor Does Not Automatically Pick Up the Submitting User's Identity

An `Executor` simply accepts a `Runnable` and decides which thread runs it:

```java
Executor pool = Executors.newFixedThreadPool(4);
pool.execute(() -> {
    Authentication a =
            SecurityContextHolder.getContext().getAuthentication();
    // No guarantee that a is the caller of the submitting request.
});
```

Moreover, the snippet above creates a pool without shutting it down, so it **must not be used as complete production code**. Manage lifecycle, pool size, queues, saturation, and shutdown.

### 8.2. Wrapping an Executor to Capture Context per Submission

```java
Executor rawExecutor = ...; // Application-managed Executor.

Executor securedExecutor =
        new DelegatingSecurityContextExecutor(rawExecutor);

// Called from request thread after authentication:
securedExecutor.execute(() -> reportService.generateAllowedReport());
```

When instantiating `DelegatingSecurityContextExecutor` **without passing a fixed `SecurityContext`**, the wrapper uses the current context at the time `execute` is called to wrap the task. Per Spring Security docs, this is how tasks run under the identity of **the caller submitting the task at submission time**.

Contrast with a worker reading context later:

```text
Submit:
  request thread: Alice
      └─ securedExecutor.execute(task)
            └─ capture Alice

Execute:
  worker thread:
      ├─ install captured SecurityContext
      ├─ run(task)
      └─ cleanup
```

**Note on capture timing:** if a task is submitted from a thread **that already lost context** (e.g., another callback, scheduler, or main application thread), the wrapper cannot conjure up the old user. Naming a bean `secured` does not make identity appear out of thin air.

### 8.3. Constructor Taking a Fixed SecurityContext: Different Tool, Different Risk

```java
SecurityContext fixed = SecurityContextHolder.createEmptyContext();
// Needs a validly created/verified Authentication per app model.

Executor privilegedExecutor =
        new DelegatingSecurityContextExecutor(rawExecutor, fixed);
```

The constructor accepting a fixed context means **every task on that executor uses the specified context**, not the submitting request's principal. This is useful for operational tasks with a controlled **service identity**, yet risky if accidentally configured with an ADMIN user's context from one request while letting any user submit work to that pool.

Never use an admin user's context to "fix missing permission errors" for all tasks. If a service principal is genuinely required, explicitly define permissions, lifetime, auditing, trust source, and object-level checks.

### 8.4. ExecutorService and ScheduledExecutorService

If using JDK `ExecutorService`, Spring Security provides `DelegatingSecurityContextExecutorService`; for schedulers, there are `DelegatingSecurityContextScheduledExecutorService` and Spring Task classes.

```java
ExecutorService raw = Executors.newFixedThreadPool(4);
ExecutorService secured =
        new DelegatingSecurityContextExecutorService(raw);

// On request thread:
Future<String> result = secured.submit(
        () -> reportService.getCurrentUserReport());
```

This is a fragment requiring lifecycle management of `raw`/`secured` and `Future` handling. Wrapping the service helps tasks run under the caller's context; it does not make outcomes permanently authorized. Periodic scheduled jobs **have no natural request user** and should not permanently inherit a previously submitting principal without policy design.

## 9. @Async and Spring TaskExecutor: Where to Place the Wrapper?

### 9.1. @Async Runs via a Task Executor, Not Automatically Preserving Context

Spring's `@Async` routes method calls to a `TaskExecutor` when invocation goes through the Spring proxy/async infrastructure. However, `@Async` does not mean `SecurityContextHolder` automatically appears on workers for every executor. Identify which executor actually runs the task.

Bean config example:

```java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.AsyncTaskExecutor;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.security.task.DelegatingSecurityContextAsyncTaskExecutor;

@Configuration
public class AsyncExecutorConfig {

    @Bean("rawAsyncExecutor")
    ThreadPoolTaskExecutor rawAsyncExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("secure-work-");
        return executor;
    }

    @Bean("securedAsyncExecutor")
    AsyncTaskExecutor securedAsyncExecutor(
            ThreadPoolTaskExecutor rawAsyncExecutor) {
        return new DelegatingSecurityContextAsyncTaskExecutor(
                rawAsyncExecutor);
    }
}
```

**This is a configuration class for use inside a Spring Boot project**, requiring Spring Security dependencies and `@EnableAsync` placed appropriately to enable `@Async`. `ThreadPoolTaskExecutor` is a Spring-lifecycle-managed bean. If the app has multiple beans of the same type, add `@Qualifier("rawAsyncExecutor")` on the injection parameter to avoid ambiguity.

### 9.2. Specifying the Bean Name in @Async

```java
@Service
public class ExportService {

    @Async("securedAsyncExecutor")
    public CompletableFuture<String> exportForCurrentUser(String reportId) {
        Authentication authentication =
                SecurityContextHolder.getContext().getAuthentication();

        // Protect object/tenant in the real service.
        String result = "requested by " + authentication.getName();
        return CompletableFuture.completedFuture(result);
    }
}
```

This is a fragment of a Spring-managed service, omitting `@EnableAsync`/`SecurityFilterChain`/real resource policies. When invoked from **another bean through the proxy**, `@Async` routes execution to the secured executor; the wrapper can propagate the submitting thread's context.

**Self-invocation risk:** `this.exportForCurrentUser(...)` called from another method of the same bean can bypass the proxy and **not run asynchronously**. Furthermore, AOP/authorization interceptor ordering when combining `@PreAuthorize` and `@Async` depends on configuration; test at the real service boundary rather than assuming annotations run on the right thread without verification.

### 9.3. Do Not Use the Default Pool Without Knowing What It Is

If you write:

```java
@Async
public void doWork() { ... }
```

without specifying an executor, Spring selects a default executor per configuration/beans. Outcomes can vary across projects. For features requiring user identity, **explicitly specify and test the actual executor**, rather than assuming every `@Async` in the system is already wrapped.

### 9.4. Exceptions and Results

- `@Async` methods returning `CompletableFuture`/`Future`: callers must observe failures, timeouts, and cancellation.
- Methods returning `void`: exceptions may go to `AsyncUncaughtExceptionHandler` rather than appearing automatically on the request thread.
- Propagating `SecurityContext` does not keep request data alive forever; never hold references to `HttpServletRequest` after the request finishes.
- Thread pools have queue/pool limits; if requests spawn too many tasks, resources can exhaust even with accurate propagation.

## 10. CompletableFuture, Nested Async, and Limits of Propagation

### 10.1. ForkJoin Common Pool Does Not Receive Request Context

```java
CompletableFuture<String> future =
        CompletableFuture.supplyAsync(() ->
            SecurityContextHolder.getContext()
                    .getAuthentication().getName());
```

**Illustrative anti-pattern:** the overload taking no `Executor` can run on `ForkJoinPool.commonPool()` or JDK-chosen execution; user ThreadLocals are not propagated automatically. This can cause `NullPointerException` or insufficient permissions in services.

### 10.2. Passing a Context-Aware Executor to Each Required Stage

```java
Executor securedExecutor = ...; // DelegatingSecurityContextExecutor

CompletableFuture<String> future =
        CompletableFuture.supplyAsync(
                () -> reportService.buildAuthorizedReport(), securedExecutor)
            .thenApplyAsync(
                result -> reportService.decorateAuthorizedResult(result),
                securedExecutor);
```

This is an integration fragment; both `buildAuthorizedReport` and `decorateAuthorizedResult` need reliable policies. Specifying the executor explicitly runs each stage where propagation operates.

**Advanced warning on capture timing:** `DelegatingSecurityContextExecutor` without a fixed context captures from **the thread calling `execute`**. A subsequent stage might be scheduled by another thread, after context was cleared, or before/after request completion; thus do not assume every arbitrary stage always carries the right user merely by passing the same wrapper. For complex pipelines, define context explicitly at handoff points, use a fixed context **strictly for that task** when genuinely appropriate, or pass actor IDs/permissions under controlled policies rather than a long-lived mutable SecurityContext.

### 10.3. thenApply Differs from thenApplyAsync

`thenApply` can run on the thread completing the prior stage or on the calling thread if the stage is already complete, depending on timing. `thenApplyAsync` typically schedules the stage on the default or specified executor. The absence of "Async" does not guarantee running on the context-bearing HTTP request thread.

Whenever callback code needs security identity, always verify the **executing thread** and how wrappers install context; never rely on intuition that a callback "is part of the same future".

### 10.4. parallelStream, Virtual Threads, and Reactive Pipelines

`parallelStream()` normally uses ForkJoin workers, which do not automatically inherit request context in the Spring Security `ThreadLocal` sense. With Java virtual threads, thread models and lifecycles differ from traditional pools, yet **you cannot assume a task running on a new thread will have the right SecurityContext**. Spring Security Servlet still requires explicit mechanisms to propagate identity across execution boundaries. WebFlux uses Reactor Context and different APIs: never carry Servlet `ThreadLocal` tutorials verbatim into reactive pipelines.

### 10.5. Do Not Freeze Permissions Inside Long-Lived CompletableFutures

If a user had permission when creating a future yet had their role revoked before a write stage executes, **the captured context can hold stale authorities**. For sensitive operations, verify current resource permissions and membership right before commit or per an appropriate transactional model; design explicit revocation/caching policies.

## 11. MODE_INHERITABLETHREADLOCAL Is Not the Default Solution for Thread Pools

### 11.1. Three Commonly Mentioned Strategies

Spring Security offers `SecurityContextHolder` modes:

| Strategy | Core meaning | Suitable as default solution for pooled workers? |
| --- | --- | --- |
| `MODE_THREADLOCAL` | Context per current thread | Default suitable for most Servlet apps |
| `MODE_INHERITABLETHREADLOCAL` | New child threads may inherit context upon thread creation | **Should not be treated as a thread-pool solution** |
| `MODE_GLOBAL` | Shares one context across the entire JVM | Dangerous in multi-user applications |

### 11.2. Why Can Inheritable Context Cause User Mix-Ups?

A pool typically creates workers **once**, then reuses them across thousands of tasks from different requests. `InheritableThreadLocal` copies values when **child threads are created**, not each time a `Runnable` is submitted.

Suppose:

```text
10:00 Pool creates worker-1 while Alice has context.
10:01 Alice submits task A; worker-1 runs.
10:02 Bob submits task B; worker-1 is reused.
```

Relying wrongly on inheritable context can leave the worker with Alice's old identity or indeterminate values over thread lifetimes; Bob may be processed with wrong permissions. Enabling `MODE_INHERITABLETHREADLOCAL` globally fails to establish per-task propagation and expands leak risks wherever threads are spawned.

**Recommendation:** keep `MODE_THREADLOCAL`, use wrappers per **specific task/executor**, clear context in `finally`, and verify isolation with tests across two different users.

### 11.3. Never Change Strategy While Serving Requests

`SecurityContextHolder.setStrategyName(...)` changes the global strategy; switching repeatedly or while threads are running can cause races/affect live threads. Never call it inside controllers/requests to "turn on context propagation"; if a special strategy must be configured, do so at startup with thorough testing.

## 12. Propagation Does Not Replace Re-Authorization

### 12.1. Permissions at Submit Time Differ from Permissions at Execute Time

Example:

```text
T0: Alice has report:export; submits export task for file r7.
T1: Alice's SecurityContext is captured and queued.
T2: Admin revokes Alice's report:export.
T3: Worker begins running export.
```

If the worker reads only authorities from the `Authentication` object captured at T0, it may still see old permissions. Context propagation does not reload roles from the database/JWT or detect revocation automatically.

Solutions depend on business requirements:

- Low-sensitivity tasks: record actor/requester ID, enforce policy at submit time, keep audits.
- Sensitive or money-moving tasks: verify permissions/membership/state at execution time and before commit, considering approval expiration.
- Long-running jobs: enforce a policy when permissions change, cancelling or requiring re-authorization before sensitive actions.
- Queue commands: use trusted identity and policy/tenant scope, never trusting client-declared JSON like `isAdmin=true`.

### 12.2. Copying Context Differs from Capturing an Immutable Snapshot

`SecurityContext` is normally a **mutable object** holding a reference to `Authentication`. Handing the raw object to a worker gives no guarantee it is a deep immutable snapshot of all permission details. Concurrent updates, context clearing/replacement, or `Authentication` holding non-thread-safe details can occur.

When separating context objects between task and caller is mandatory, create a new context:

```java
SecurityContext source = SecurityContextHolder.getContext();

SecurityContext copy = SecurityContextHolder.createEmptyContext();
copy.setAuthentication(source.getAuthentication());
```

**Warning:** this example creates only a **new SecurityContext container**; `Authentication` remains the **same reference**, not an immutable deep copy/snapshot. Do not treat this as a fix for revocation or concurrency if Authentication/details are also mutable. For long-lived workflows, prefer actor ID + trustworthy data sources and business-level re-checks.

### 12.3. Object-Level Authorization Remains Mandatory

A `GET /api/files/f9` request holding `file:read` is not automatically permitted to read every file. Even when the worker has an accurate `SecurityContext`, the service still requires:

```text
ALLOW =
    authenticated
    AND hasAuthority("file:read")
    AND sameTenant(actor, file)
    AND canReadOwnerOrShare(actor, file)
    AND file.status permits read
```

These functions are **domain pseudo-policies**, not built-in Spring Security methods. With Spring MVC `Callable` or `DeferredResult`, file-level rules belong in testable service and repository/query layers, not only in controllers.

### 12.4. Transactions, Request Scope, and MDC Do Not Follow Automatically

`SecurityContext` propagation does not automatically carry:

- Transactions and EntityManagers bound to the request thread.
- Request-scoped beans or `RequestContextHolder`.
- MDC/logging correlation IDs or distributed tracing baggage.
- User locale/time zone.
- Thread-bound resource locks.
- Servlet response lifecycle, timeouts, and connection state.

Each context type has **its own propagation mechanism**. Never assume `DelegatingSecurityContextExecutor` makes every `ThreadLocal` in the app propagate automatically.

## 13. Standalone Java 17 Example: Propagating Context and Cleaning Up Workers

The following program uses no Spring libraries and simulates:

- a `ThreadLocal<Caller>` holding the thread's identity;
- an `ExecutorService` creating **one reusable worker thread**;
- an `Executor` wrapping tasks and **capturing caller at submit time**;
- a `finally` block restoring the worker's prior context to prevent leaks;
- two users Alice/Bob submitted sequentially through the same pool;
- a failing task still getting cleaned up.

This is a **conceptual** demo matching propagation wrappers, **not an implementation of `SecurityContextHolder` or a real authorization framework**. Keep it as a simplified learning aid; never ship it verbatim in production instead of `DelegatingSecurityContextExecutor`.

Create file `ContextHandoffDemo.java`:

```java
import java.util.Set;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.Executor;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.FutureTask;
import java.util.concurrent.TimeUnit;

public class ContextHandoffDemo {

    record Caller(String username, Set<String> authorities) {}

    private static final ThreadLocal<Caller> CURRENT =
            new ThreadLocal<>();

    private static String describe() {
        Caller caller = CURRENT.get();
        if (caller == null) {
            return "NO_CONTEXT";
        }
        boolean canRead = caller.authorities().contains("report:read");
        return caller.username() + "/read=" + canRead;
    }

    private static Executor contextual(Executor delegate) {
        return command -> {
            // Capture on the thread SUBMITTING the task.
            Caller captured = CURRENT.get();

            delegate.execute(() -> {
                Caller previous = CURRENT.get();
                try {
                    if (captured == null) {
                        CURRENT.remove();
                    } else {
                        CURRENT.set(captured);
                    }
                    command.run();
                } finally {
                    // Restore pre-task state, avoiding pool leakage.
                    if (previous == null) {
                        CURRENT.remove();
                    } else {
                        CURRENT.set(previous);
                    }
                }
            });
        };
    }

    private static <T> T call(
            Executor executor, Callable<T> work) throws Exception {
        FutureTask<T> future = new FutureTask<>(work);
        executor.execute(future);
        return future.get();
    }

    public static void main(String[] args) throws Exception {
        ExecutorService rawPool = Executors.newSingleThreadExecutor();
        Executor secured = contextual(rawPool);

        try {
            Caller alice = new Caller(
                    "alice", Set.of("ROLE_USER", "report:read"));
            Caller bob = new Caller(
                    "bob", Set.of("ROLE_USER"));

            CURRENT.set(alice);
            System.out.println("main-alice=" + describe());
            System.out.println("raw-alice="
                    + call(rawPool, ContextHandoffDemo::describe));
            System.out.println("wrapped-alice="
                    + call(secured, ContextHandoffDemo::describe));

            CURRENT.set(bob);
            System.out.println("wrapped-bob="
                    + call(secured, ContextHandoffDemo::describe));
            System.out.println("raw-after-bob="
                    + call(rawPool, ContextHandoffDemo::describe));

            // Intentionally failing task to verify finally still cleans context.
            FutureTask<String> failing = new FutureTask<>(
                    () -> { throw new IllegalStateException("demo"); });
            secured.execute(failing);
            try {
                failing.get();
            } catch (ExecutionException expected) {
                System.out.println("failure-caught="
                        + expected.getCause().getClass().getSimpleName());
            }

            System.out.println("raw-after-failure="
                    + call(rawPool, ContextHandoffDemo::describe));
            System.out.println("main-bob=" + describe());

            CURRENT.remove();
            System.out.println("wrapped-without-caller="
                    + call(secured, ContextHandoffDemo::describe));
        } finally {
            CURRENT.remove();
            rawPool.shutdown();
            if (!rawPool.awaitTermination(5, TimeUnit.SECONDS)) {
                rawPool.shutdownNow();
            }
        }
    }
}
```

Run with **JDK 17+**:

```bash
javac ContextHandoffDemo.java
java ContextHandoffDemo
```

Deterministic stdout per sequential `FutureTask.get()` logic:

```text
main-alice=alice/read=true
raw-alice=NO_CONTEXT
wrapped-alice=alice/read=true
wrapped-bob=bob/read=false
raw-after-bob=NO_CONTEXT
failure-caught=IllegalStateException
raw-after-failure=NO_CONTEXT
main-bob=bob/read=false
wrapped-without-caller=NO_CONTEXT
```

### 13.1. Interpreting the Output

1. `main-alice`: caller thread has Alice's identity and read permission.
2. `raw-alice=NO_CONTEXT`: worker pool does not automatically receive the request thread's `ThreadLocal`.
3. `wrapped-alice`: wrapper captures Alice **at submit time**, then installs Alice on the worker.
4. `wrapped-bob`: the same worker is reused, yet proper wrapping surfaces Bob instead of Alice.
5. `raw-after-bob=NO_CONTEXT`: at the end of Bob's task, the worker is clean; no identity leak.
6. Task threw `IllegalStateException` yet `FutureTask` captured the exception and the wrapper `finally` still ran.
7. `raw-after-failure=NO_CONTEXT` proves cleanup even on errors.
8. `main-bob` shows the caller thread's context is independent of the worker.
9. `wrapped-without-caller=NO_CONTEXT`: the wrapper does not fabricate an identity when submitted from a callerless thread.

### 13.2. Differences from Real Spring Security

- Demo uses `ThreadLocal<Caller>` instead of `SecurityContextHolder`.
- Demo does not implement `SecurityContextHolderStrategy`, authentication managers, JWTs, or method security.
- Demo restores the worker's `previous`; Spring Security wrappers follow version-specific context set/clear contracts.
- Demo lacks request/HTTP boundaries, timeouts, cancellation, CSRF, or asynchronous servlet dispatches.
- Demo does not check tenant/resource permissions; it only illustrates installing and cleaning up identity.

**Educational value:** before using Spring Security APIs, clearly grasp where context is captured, which thread uses it, and when it is cleared/restored.

## 14. Testing: Verifying Propagation, Isolation, and Authorization

### 14.1. Minimum Matrix

| Situation | Expected outcome |
| --- | --- |
| Synchronous HTTP request authenticated as Alice | Controller/service sees Alice |
| Alice's MVC `Callable` | Thread executing Callable sees Alice when integration works |
| Servlet `AsyncContext.start` via wrapped request | Runnable sees Alice's Authentication |
| Alice's raw `ExecutorService` | Does not have Alice by default; secured service must fail closed |
| `DeferredResult` completed via raw executor | No auto propagation |
| `DeferredResult` completed via secured executor | Task sees properly captured context |
| `@Async` with unwrapped executor | Do not assume right principal |
| `@Async` with Delegating wrapper | Context propagated when submitted at right point |
| Alice and Bob submit to same pool | Each task sees the right person, no cross-contamination |
| Task throws exception | Worker no longer holds previous task's principal |
| Task submitted without context | Must not inherit previous user's context |
| Permission revoked before worker executes | Policy re-checks as required; do not trust stale snapshot |
| Request lacks permission | Denied even when propagation succeeds |
| Async timeout/cancel | No context leak, no double complete/side effects |
| Multiple filter chains and ASYNC dispatch | Right chain, authz not bypassed |

### 14.2. MockMvc Testing Spring MVC Callable

This is a **test fragment** requiring `MockMvc`, Spring Security Test, the `GET /api/me/callable` controller from section 5, a security filter chain, and imports:

```java
@Test
@WithMockUser(username = "alice", authorities = "report:read")
void callableGetsRequestPrincipal() throws Exception {
    MvcResult result = mockMvc.perform(get("/api/me/callable"))
            .andExpect(request().asyncStarted())
            .andReturn();

    mockMvc.perform(asyncDispatch(result))
            .andExpect(status().isOk())
            .andExpect(content().string("alice"));
}
```

The snippet needs static imports from `MockMvcRequestBuilders`, `MockMvcResultMatchers`, and `SecurityMockMvcRequestPostProcessors` when used. When the controller returns `ResponseEntity<String>`, the response body in the example is `alice`. `@WithMockUser` creates a test Authentication and does not test a production JWT converter.

**Do not test only that `Callable` ran.** Test the user-visible output or service security decision, then test missing permission/anonymous on the same route.

### 14.3. Testing DeferredResult with Two Users

With a single-worker pool to expose leak bugs clearly:

1. Alice submits a task via the secured executor → task sees Alice.
2. Bob submits a task via the same executor → task sees Bob.
3. Submit a raw unwrapped task → sees neither Alice nor Bob left over.
4. Make Alice's task intentionally throw an exception → next task still does not see Alice.
5. Submit a task after the request thread logs out/clears context → must not inherit the old user.
6. Use countdown latches to control submit/execute timing when testing concurrency and revocation precisely; do not rely on `Thread.sleep` to manufacture random races.

### 14.4. Testing @Async and @PreAuthorize

Calling `@Async` through a proxy differs from self-invocation. Test from another bean/controller and verify:

- the executor chosen by `@Async` is the wrapped bean;
- context captured at submit time carries the right test Authentication;
- the service method with `@PreAuthorize` is invoked through the Spring proxy;
- a user with only `report:read` cannot invoke a use case needing `report:export`;
- for cross-tenant objects, the method is still denied despite having the right role;
- task exceptions surface through `Future`/`CompletableFuture` or configured handlers.

Specifically, never assume `@PreAuthorize` on an `@Async` method always evaluates on the caller thread or worker thread across all AOP orderings; test on your exact version/config and enforce critical policies at reliable service boundaries.

### 14.5. Testing Servlet AsyncContext with an Embedded Container When Needed

`MockMvc` supports some Servlet async flows, yet if tests depend on `AsyncContext.start`, dispatcher registrations, timeouts, request wrappers, or container behavior, write integration tests with a **real embedded server**. Check status, response, thread cleanup, dispatch type, and absence of exceptions on client cancellation.

### 14.6. Testing Fail-Closed When Context Is Absent

When `Authentication` is null or anonymous, code should never do:

```java
// Anti-pattern: never auto-allow when worker lacks auth.
if (SecurityContextHolder.getContext().getAuthentication() == null) {
    return exportEverything();
}
```

Instead, deny or apply a policy genuinely matching a system actor, auditing the reason. If anonymous is valid for a public read job, document the public route/policy explicitly; never accidentally open paths containing user data.

## 15. Complex Scenarios and How to Decide

### 15.1. Scheduled Jobs with No Request User

A `@Scheduled` nightly report-aggregation job **has no request** and must not demand some random user's `SecurityContextHolder`. You can:

- Design a **service account/principal** with least privilege for the job.
- Execute via domain APIs with dedicated system-action mechanisms and auditing.
- Restrict tenants, data, and scope the job is permitted to process.
- Never grant global `ROLE_ADMIN` to a job just to bypass all permissions.

For multi-tenant batches, run under a scope-restricted service identity rather than piggybacking on the last request's principal on a thread.

### 15.2. Queue/Event Consumers

You cannot send a Java `SecurityContext` object over Kafka/RabbitMQ as if it were still a request session. A job payload may store actor ID, tenant ID, action ID, and correlation ID, yet **that is producer-supplied data**. Consumers must verify message origin, integrity, idempotency policy, and authorization at their own security boundary.

If a consumer trusts a `role=ADMIN` claim from a client-supplied payload without verification, that is an **authorization bypass**. When genuinely acting on a user's behalf, apply controlled delegation/impersonation with TTL, audit, and revocation support.

### 15.3. Async Work After the HTTP Response Was Sent

If a controller returns 202 and a worker runs long:

- `SecurityContext` on the worker may have been captured when creating the task.
- Session/JWT may expire after the response.
- The user may change roles, be locked, or leave the tenant.
- Resource state may have changed.

Therefore, for critical tasks, use job IDs and explicit workflow authorization: **submit allowed?**, **execute still allowed?**, **view/download result allowed?**. Never keep request/response objects as "insurance" for permissions.

### 15.4. AsyncContext, Callable, or DeferredResult for Which Work?

| Need | Usually suitable choice | Warning |
| --- | --- | --- |
| Low-level Servlet needing direct async response control | `AsyncContext` | App is responsible for lifecycle/timeout/filters/response |
| MVC controller wanting a result from a simple async task | `Callable<T>` | Auto-integrated context, yet nested tasks are not auto-propagated |
| Result produced later by an event/callback | `DeferredResult<T>` | App owns completion task; needs context wrapper |
| Async service method with Spring AOP | `@Async` + configured executor | Proxy, @EnableAsync, context-aware executor, error handling |
| Multi-stage pipeline | `CompletableFuture` with explicit executor strategy | Capture timing and nested stages |
| Long-running/durable work | Queue/job store | Do not pass raw context; re-authorization, audit |

### 15.5. When Is Propagating SecurityContext Unnecessary?

Not every task should borrow the caller's identity. For instance, formatting public images or emitting system metrics needs no security context and can run on workers without a principal. The less context propagated, the lower the risk of leakage and coupling.

If business APIs need to know **who initiated a task** for auditing, pass `actorId` as a verified **data value** instead of passing an `Authentication` carrying credentials/authorities. For risky actions, consumers/services must still check permissions from a trusted source. **Never treat a client-controlled actorId in a message as authentication proof.**

## 16. Common Errors and How to Diagnose Them

| Symptom | Common cause | Where to check |
| --- | --- | --- |
| `SecurityContextHolder.getContext().getAuthentication() == null` in executor | ThreadLocal not propagated automatically | Wrap Executor/Callable, verify submit thread |
| MVC Callable sees user yet nested CompletableFuture does not | Nested task runs on another pool | Pass appropriate executor to stage |
| DeferredResult has no principal | No auto integration for user task | Use context-aware executor/explicit actor |
| `AsyncContext.start` fails to run properly | Servlet/filter lacks async support or broken lifecycle | Check asyncSupported, dispatcher, timeout |
| `new Thread` sees null Authentication | Does not go through Spring integration | Use wrapper, avoid manual thread creation |
| Bob sees Alice's authorities | Worker retained stale ThreadLocal, missing cleanup, or wrong inheritable mode | Use standard wrapper, test 2-user pool reuse |
| `@Async` runs on caller thread | Self-invocation/proxy not enabled | Check `@EnableAsync` and cross-bean calls |
| `@Async` runs yet has no user | Executor unwrapped or wrong bean selected | Check @Async qualifier and executor instance |
| `Future` fails yet controller returns 200 | Exception/awaited result not observed properly | Record completion/errors explicitly |
| Authorization passes at submit yet fails at execute | Context changed or live-data policy differs | Review capture timing, re-checks |
| Authorization passes after role revocation | Stale authorities snapshot used too long | Check revocation, TTL, execution-time policy |
| Job gets admin even when caller is regular user | Executor uses high-privilege fixed context | Never use privileged fixed context casually |
| Async task breaks DB transaction | Thread-bound transaction not propagated | Design separate transaction inside worker |
| MDC/tracing lost on worker | SecurityContext wrapper handles security only | Add separate propagation for other contexts |
| Request already completed yet worker writes response | Broken AsyncContext lifecycle | Fix timeout/cancel/complete properly |
| MockMvc test passes, production server fails | Different container/filters/async redispatches | Integration test on matching servlet stack |

### Five Questions When Debugging

1. **Which thread does the task actually run on?** Log thread names safely.
2. **Who submits the task and when?** Is there a SecurityContext on the submitting thread?
3. **Which executor/mechanism executes it?** `AsyncContext.start`, MVC Callable, raw pool, @Async, or callback?
4. **Is context cleaned up?** Submit Alice → Bob → raw task to the same pool to check for leaks.
5. **Did policy run again where side effects happen?** Right permission, object, tenant, validity window?

Never fix errors by switching everything to `MODE_GLOBAL` or assigning default `ROLE_ADMIN` to userless tasks.

## 17. Workflow for Applying in Real Projects

**Step 1 — Classify asynchronous boundaries.** Find places using `request.startAsync`/`AsyncContext.start`, controller `Callable`/`DeferredResult`, `ExecutorService`, `@Async`, `CompletableFuture`, schedulers, and message consumers. Pinpoint **where execution truly switches threads**.

**Step 2 — Map capture and execution points.** Document where the user's SecurityContext resides, which thread submits the task, how long the worker can be delayed, and which authorities the task uses.

**Step 3 — Pick the right propagation mechanism.** Use Servlet `AsyncContext.start`/MVC `Callable` integrations where available; for `DeferredResult`, raw pools, or @Async, use the matching Spring Security wrapper. Avoid unnecessary nested wrappers and never create app-wide fixed contexts unintentionally.

**Step 4 — Protect the thread pool.** Manage pool size, queues, timeouts, shutdown, saturation, and exceptions. Ensure workers clean up context on every branch. Avoid raw `SecurityContextHolder.setContext` without `finally`.

**Step 5 — Keep authorization boundaries.** HTTP routes/Method security check functions; services check object/tenant/state; delayed jobs enforce re-authorization/revocation policies.

**Step 6 — Do not mix ThreadLocals.** Transactions, request scope, MDC, locale, tracing, and SecurityContext have separate mechanisms; configure each when genuinely needed, avoiding sending credentials where unnecessary.

**Step 7 — Test two principals and exceptions.** Alice/Bob on the same pool, wrapper with/without context, throwing tasks, timeouts/cancellations, revoked user permissions, different tenants.

**Step 8 — Test the right runtime.** For MVC Callable use MockMvc asyncDispatch; for Servlet AsyncContext and dispatcher configs use an embedded server; for @Async test Spring proxies and executor beans.

**Step 9 — Review tasks outliving requests.** Move long-running work to jobs/queues, store verified minimal actor ID metadata, with TTL/audit and authorization at execute and result-download steps.

**Step 10 — Verify against your version.** Wrapper APIs and Spring MVC integrations exist in Spring Security 6.x/7.x, yet exact configurations can change. Rely on your resolved dependencies/BOM/Javadoc, not just "current" snippets or assumptions that Servlet and WebFlux behave identically.

## 18. Self-Check Questions

**Question 1.** Why can `SecurityContextHolder` inside a raw `ExecutorService` lack a user even though the request caller logged in?

**Answer:** `SecurityContextHolder` is `ThreadLocal`-based by default. Pool workers are different threads and do not automatically inherit the HTTP thread's context. Use a proper propagation mechanism at submission time.

**Question 2.** Are `AsyncContext.start(Runnable)` and `new Thread(runnable).start()` equivalent for Spring Security context?

**Answer:** No. Spring Security integrates with `AsyncContext.start` via Servlet request/async wrappers. `new Thread` does not pass through that integration.

**Question 3.** A Spring MVC controller returns `Callable<String>`. Must you wrap the Callable manually by default?

**Answer:** Usually no in standard integrated Spring Security/MVC configs. `WebAsyncManager` propagates context to the thread executing `Callable`. However, nested tasks manually spawned inside still need their own mechanism.

**Question 4.** A Spring MVC controller returns `DeferredResult<String>` and uses a raw thread pool to call `setResult`. Is there auto propagation?

**Answer:** Not for user-executed tasks. Use a context-aware executor/explicit propagation or design suitable trusted actor data.

**Question 5.** Where does `DelegatingSecurityContextExecutor(raw)` without a fixed context get the user's context?

**Answer:** At the moment `execute` receives the task, from the submitting thread's `SecurityContextHolder`. If the submitting thread has no user, the wrapper cannot recover a prior user.

**Question 6.** What is the difference between `DelegatingSecurityContextExecutor(raw)` and `DelegatingSecurityContextExecutor(raw, fixedContext)`?

**Answer:** The first captures context per submission; the second applies a fixed context to tasks. The fixed form requires special privilege review so one user/ADMIN is not applied to all callers.

**Question 7.** Should `MODE_INHERITABLETHREADLOCAL` be enabled app-wide to fix propagation errors in pooled workers?

**Answer:** No. Inheritable context is copied when **creating child threads**, not each time a pool accepts a task; it risks user mix-ups/leaks.

**Question 8.** A wrapper makes `getAuthentication()` return Alice; is Alice guaranteed to still have `report:export` when the task runs?

**Answer:** No. Captured context can hold stale permissions. For sensitive tasks, re-check policy/membership/tenant at execution time.

**Question 9.** `@Async("securedAsyncExecutor")` fails to run asynchronously when called from its own bean. What likely happened?

**Answer:** Self-invocation bypassed the Spring AOP proxy. Call from another bean via proxy, enable `@EnableAsync`, and test the selected executor.

**Question 10.** If a worker has `SecurityContext`, are transactions and MDC propagated automatically too?

**Answer:** No. Transactions, request context, MDC, locale, and tracing are separate context types; design separate propagation when needed.

**Question 11.** Why is `finally` cleanup needed for context?

**Answer:** Thread pools reuse workers. If a task fails without clearing context, subsequent tasks can see the previous user, creating data/authorization vulnerabilities.

**Question 12.** A job created from an HTTP request must continue running hours after logout. Should you keep the user's `HttpServletRequest` and `SecurityContext`?

**Answer:** No. Move to a durable job storing minimal verified requester metadata, with authorization/revocation/auditing at execution and result retrieval.

**Summary:** `AsyncContext.start` and MVC `Callable` support `SecurityContext` propagation in Spring Security Servlet when integration is active; `DeferredResult`, raw executors, `@Async`, and nested futures require controlling handoff points. Propagating the right principal **does not** replace action/object authorization and never permits retaining stale permissions forever. With pooled workers, always think **capture → set → execute → cleanup → re-check when needed**.

## Official References

- Spring Security — Servlet API integration, `AsyncContext.start(Runnable)` and async dispatch: https://docs.spring.io/spring-security/reference/servlet/integrations/servlet-api.html
- Spring Security — Spring MVC Async Integration, `Callable`, `DeferredResult` limits: https://docs.spring.io/spring-security/reference/servlet/integrations/mvc.html
- Spring Security — Concurrency Support and DelegatingSecurityContext* list: https://docs.spring.io/spring-security/reference/servlet/integrations/concurrency.html
- Spring Security — Servlet Authentication Architecture and `SecurityContextHolder`: https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html
- Spring Security 7.0 — `WebAsyncManagerIntegrationFilter` Javadoc: https://docs.spring.io/spring-security/reference/7.0/api/java/org/springframework/security/web/context/request/async/WebAsyncManagerIntegrationFilter.html
- Spring Security 7.0 — `DelegatingSecurityContextAsyncTaskExecutor` API: https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/task/DelegatingSecurityContextAsyncTaskExecutor.html
- Spring Security — Method Security and method interceptors: https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
- Spring Framework — Spring MVC Asynchronous Requests: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-async.html
- Spring Framework — Task Execution, @Async and scheduling: https://docs.spring.io/spring-framework/reference/integration/scheduling.html
- Spring Security — HTTP authorization and dispatcher types: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
