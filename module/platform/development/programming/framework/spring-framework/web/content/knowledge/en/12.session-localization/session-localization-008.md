# Spring MVC — Context Propagation When Switching to Asynchronous Processing

## 1. Objectives and Real-World Problem

An HTTP request entering Spring MVC can carry the **user's language**, request details, authenticated identity, correlation ID (request ID), trace/span ID, and transaction state. When a controller runs synchronously on a Servlet thread, Spring normally binds some of this data to the current thread. If work moves to another thread via `@Async`, `CompletableFuture`, or an executor, that data **does not automatically appear in full** on the new thread.

For example:

~~~java
Locale locale = LocaleContextHolder.getLocale();
String requestId = MDC.get("requestId");
~~~

Inside the request-handling thread, `locale` may be `vi_VN` and `requestId` may be a UUID. However, if you run those exact two lines inside `CompletableFuture.supplyAsync(...)` on the common pool, the result may become the server's default locale and `requestId == null`. That causes wrong languages, lost log correlation, or worse, incorrect security context usage.

After this lesson, you will be able to:

- Distinguish **business data** passed via explicit parameters from thread-bound **execution context**.
- Understand `LocaleContextHolder`, `RequestContextHolder`, SLF4J `MDC`, `SecurityContextHolder`, Micrometer tracing/context propagation, and the proper scope of each.
- Explain the Servlet async lifecycles of `Callable`, `DeferredResult`, `CompletionStage`, and `@Async` — they are not synonymous.
- Design a `TaskDecorator` that **captures on submit**, **restores during execution**, and **cleans up in `finally`**, preventing context leaks across thread pools.
- Know when to use `ContextPropagatingTaskDecorator`/Micrometer Context Propagation versus Spring Security's `DelegatingSecurityContextAsyncTaskExecutor`.
- Build a Java 17+ / Spring Boot 3.5.0 example with `@Async`, locale, request ID, HTTP responses, and MockMvc async dispatch.
- Recognize boundaries regarding request/session lifecycles, `SecurityContext`, transactions, tracing, timeouts, thread pools, data privacy, and cross-service propagation.

**Scope:** Spring MVC (Servlet stack) of Spring Framework 6.2.x. Do not equate these solutions with Spring WebFlux / Reactor Context; reactive-stack environments require a different design.

## 2. What Is Context? Why Does Switching Threads Lose Context?

**Context** is execution metadata needed by multiple components that is not always passed directly through method parameters: locale, trace ID, request metadata, authentication, etc.

In Java, `ThreadLocal<T>` stores a value bound to **one thread**. Another thread has its own `ThreadLocal` slot:

~~~java
private static final ThreadLocal<String> CURRENT_REQUEST =
        new ThreadLocal<>();
~~~

In a thread pool, worker threads are reused across many tasks from many users. Without cleaning up `ThreadLocal` after execution, an old request's context can bleed into a new task.

### 2.1. Standalone Java 17 Program: Observing Context Loss Across Threads

Save to `ThreadLocalDemo.java`:

~~~java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class ThreadLocalDemo {
    private static final ThreadLocal<String> REQUEST = new ThreadLocal<>();

    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();

        try {
            REQUEST.set("req-A");

            Future<String> without = pool.submit(REQUEST::get);
            System.out.println(without.get() == null);

            String captured = REQUEST.get(); // Capture on caller thread.

            Future<String> with = pool.submit(() -> {
                String previous = REQUEST.get();
                try {
                    REQUEST.set(captured); // Install on worker.
                    return REQUEST.get();
                } finally {
                    if (previous == null) {
                        REQUEST.remove();
                    } else {
                        REQUEST.set(previous);
                    }
                }
            });
            System.out.println(with.get());
        } finally {
            REQUEST.remove();
            pool.shutdown();
        }
    }
}
~~~

Run:

~~~bash
javac ThreadLocalDemo.java
java ThreadLocalDemo
~~~

Stdout:

~~~text
true
req-A
~~~

**Meaning:** request context does not transfer to workers automatically. It must be captured while the context exists, installed on the worker thread, and restored/cleared afterward. `finally` is critical if the task throws an exception. Never try to work around this by setting context once when creating the thread pool, because the pool serves many requests.

### 2.2. Common Contexts in Spring

| Mechanism | What data does it hold? | Default scope and key notes |
| --- | --- | --- |
| `LocaleContextHolder` | `LocaleContext`, optionally with time zone | Spring `ThreadLocal`; used for localization/formatting |
| `RequestContextHolder` | `RequestAttributes`, typically `ServletRequestAttributes` | Bound to request/thread; request objects have a finite lifetime |
| `SecurityContextHolder` | `SecurityContext` with `Authentication` | Typically thread-local; propagation requires proper security mechanisms |
| SLF4J `MDC` | String map for structured logging and correlation IDs | Typically thread-local in logging backends; needs copy/restore |
| Micrometer Observation/Tracing | Observation, trace/span context | Dedicated mechanism managed by instrumentation and context propagation |
| `TransactionSynchronizationManager` | Resource/transaction synchronization state | Bound to thread/transaction; never copy arbitrarily to workers |
| HTTP session | User session state, stored server-side | Not a `ThreadLocal`; do not treat session as implicit task context |
| `@SessionAttributes` | Model attributes retained across MVC requests | Model/session lifecycle, **distinct** from async thread context |

In particular, the **language resolved from an HTTP request** does not automatically become a property of a background task. You must decide: does a task need the user's locale at submit time, or a newer locale selected later? Usually it is best to capture immutable values (such as `Locale` and an authorized user ID) when scheduling.

## 3. `LocaleContextHolder` and `RequestContextHolder` in MVC

Spring MVC typically determines locale from `LocaleResolver`/`LocaleContextResolver`. For example, default configuration can use `Accept-Language: vi-VN`. Inside a request handler, Spring binds the locale context to the request-serving thread:

~~~java
@GetMapping("/welcome")
@ResponseBody
String welcome() {
    Locale locale = LocaleContextHolder.getLocale();
    return locale.toLanguageTag();
}
~~~

In a request context with `Accept-Language: vi-VN`, the output is `vi-VN`. This is a handler fragment; a controller class and imports are required in an application.

**Distinguish:**

- `LocaleContextHolder.getLocale()` returns the current context's `Locale` or a fallback locale. A successful call **does not prove** the request's locale was propagated.
- `LocaleContextHolder.getLocaleContext()` retrieves the `LocaleContext` object; if it carries a time zone, that can be preserved when propagating the context properly.
- `LocaleContextHolder.setLocaleContext(context)` sets the context on the running thread; `resetLocaleContext()` clears it from the thread.
- `RequestContextHolder.currentRequestAttributes()` can throw `IllegalStateException` if no request attributes are bound to the thread. `getRequestAttributes()` returns null when absent.

### 3.1. Why Not Blindly Copy `ServletRequestAttributes`?

A request lives only for the HTTP lifecycle controlled by the Servlet container. When `@Async` starts a **background job that continues running after the response completes**, holding references to `HttpServletRequest`, `HttpSession`, or `ServletRequestAttributes` can cause:

1. Accessing a request that is no longer valid after request completion.
2. Retaining references to large objects, sessions, or sensitive data longer than intended.
3. Assuming session/security state remains unchanged even if the user logs out or permissions change.
4. Race conditions when multiple threads access mutable request/response objects simultaneously.

**Prefer:** extract needed data on the request thread and pass it explicitly to the task:

~~~java
record JobContext(
        String requestId,
        Locale locale,
        String authorizedUserId) {
}

// Read on the request thread after checking permissions.
JobContext context = new JobContext(requestId, resolvedLocale, userId);
executor.execute(() -> service.perform(jobId, context));
~~~

This is an architectural fragment requiring `requestId`, `resolvedLocale`, `userId`, `jobId`, and an appropriate service. Never put passwords, bearer tokens, or an entire session into an immutable context. **A user ID alone does not grant permissions**: background jobs may need to re-check authorization or service identity depending on timing and policy.

### 3.2. Mind Time Zones

A locale like `vi-VN` does not define a time zone by itself. If you need to render the user's local time, the context may need an independent `ZoneId`:

~~~java
record DisplayContext(Locale locale, ZoneId zoneId) {
}
~~~

Import `java.util.Locale` and `java.time.ZoneId`. When sending tasks to a queue or another process, send immutable values with an explicit contract instead of relying on the JVM default time zone.

## 4. Different Asynchronous Models Are Not Identical

### 4.1. Spring MVC `Callable`

~~~java
@GetMapping("/report")
@ResponseBody
public Callable<String> report() {
    return () -> reportService.generate();
}
~~~

Spring MVC switches the Servlet request into async mode, submits the `Callable` to the configured `AsyncTaskExecutor`, and once a result is ready performs an **ASYNC dispatch** to complete the HTTP response.

Do not confuse Spring's dedicated MVC `Callable` lifecycle with arbitrary `ThreadLocal` values automatically following to other threads. The framework and interceptors may handle certain context bindings; for MDC or custom `ThreadLocal`s, deliberate configuration and testing are still required.

### 4.2. `DeferredResult`

~~~java
@GetMapping("/jobs/{id}/wait")
@ResponseBody
public DeferredResult<String> waitForJob(@PathVariable String id) {
    DeferredResult<String> result = new DeferredResult<>(10_000L);
    registry.register(id, result);
    return result;
}
~~~

When another thread has the result:

~~~java
result.setResult("done");
// Or result.setErrorResult(exception);
~~~

These two fragments illustrate the concept; `registry` and `result` must be managed in a real application. `DeferredResult` does not spawn a worker task by itself: **the application actively completes it** from another thread or callback. When the result arrives, MVC dispatches again to send the response. Handle `onTimeout`, `onCompletion`, registry cleanup, and avoid completing twice.

Do not hold onto the Servlet request or locale holder across the lifetime of a `DeferredResult`. Capture needed context explicitly at registration time; the callback's thread context is not automatically the original request context.

### 4.3. `CompletionStage`/`CompletableFuture`

~~~java
@GetMapping("/summary")
@ResponseBody
public CompletableFuture<String> summary() {
    return CompletableFuture.supplyAsync(() -> "ready", executor);
}
~~~

Spring MVC can adapt a `CompletionStage`/`CompletableFuture` into an async HTTP response. However, **the task you submit yourself** to another executor runs on that executor's thread. If you write:

~~~java
CompletableFuture.supplyAsync(() -> work());
~~~

without specifying an executor, Java typically uses `ForkJoinPool.commonPool()`. Never assume MDC, locale, `SecurityContext`, or transactions follow into the common pool.

Similarly, chained stages like `thenApplyAsync`, `thenComposeAsync`, or callbacks invoked by external libraries may run on different threads. Propagating only the **first stage** leaves later stages on other executors without context. Design propagation at **every thread boundary**.

### 4.4. `@Async`

~~~java
@Service
class ReportService {
    @Async("contextExecutor")
    public CompletableFuture<String> generate() {
        return CompletableFuture.completedFuture("done");
    }
}
~~~

`@Async` in Spring typically uses a proxy/interceptor to submit method invocations to an executor. You must enable `@EnableAsync` and invoke the method through a Spring-managed bean/proxy (e.g., a controller injecting the service). **Self-invocation** from one method on the same instance calling another `@Async` method normally bypasses the proxy and runs synchronously.

`@Async` is a **way to execute a method on a worker**, not a mechanism that automatically propagates all context types. `ContextPropagatingTaskDecorator` or an equivalent mechanism must be attached to the executor.

### 4.5. Comparison Table

| Tool | Who picks/schedules the worker? | HTTP response still waiting? | Context considerations |
| --- | --- | --- | --- |
| MVC `Callable<T>` | MVC `AsyncTaskExecutor` | Yes, Servlet async | MVC lifecycle, custom MDC/tracing, executor |
| MVC `DeferredResult<T>` | Application/event source produces result | Yes, until result/timeout | Callback thread and cleanup |
| Controller returning `CompletableFuture<T>` | You or library creates future | Yes, until future completes/times out | Executors across all stages |
| `@Async` service method | Spring AOP async executor | Controller does not automatically wait; depends on return type | Proxy, `TaskDecorator`, `SecurityContext` |
| Scheduled/background job | Scheduler/queue | Typically no HTTP request remains | Pass immutable context / re-auth per policy |
| Reactor/WebFlux | Reactive scheduling/context | Per reactive pipeline | Reactor Context, do not rely on `ThreadLocal` |

When a Servlet request goes async, the original container thread returns to the pool while the HTTP response stays open. Completing async processing typically involves an `ASYNC` dispatch; filter mappings and `async-supported` must be configured properly so middleware behaves as expected.

## 5. The Capture → Install → Execute → Restore Pattern

A safe way to carry context across a thread boundary:

~~~text
HTTP request thread                         Pool worker thread
LocaleContextHolder = vi_VN
MDC.requestId = abc-123
       |
       | submit(task)
       | -- CAPTURE snapshot --> locale=vi_VN, mdc={requestId:abc-123}
       |                         |
       |                         | INSTALL into worker
       |                         | EXECUTE work
       |                         | finally RESTORE old worker state
       |                         |
HTTP handler is released                    Worker safely reused
~~~

Important rules:

- **Capture at submission time**, while the caller thread still holds valid context. Capturing when the worker begins running may be too late.
- Propagate only fields **actually needed**, rather than copying whole request objects or opaque `ThreadLocal`s.
- **Restore the previous state**, rather than blindly setting null; a worker might already be inside a nested context.
- Use `try/finally` even if the task throws an exception or is cancelled.
- Choose the right context lifetime: once the HTTP request finishes, background tasks have no business relying on a live `ServletRequest`.
- Security: never retain a mutable `Authentication` object from a request for too long or leak it into another user's task.

### 5.1. `TaskDecorator` in Spring Framework

Spring provides `org.springframework.core.task.TaskDecorator`. With `ThreadPoolTaskExecutor`:

~~~java
ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
executor.setCorePoolSize(2);
executor.setMaxPoolSize(4);
executor.setQueueCapacity(50);
executor.setThreadNamePrefix("ctx-");
executor.setTaskDecorator(new LocaleAndMdcTaskDecorator());
executor.initialize();
~~~

This fragment is from the complete configuration class in Section 9. `TaskDecorator` wraps the runnable before execution. It may wrap an internal wrapper `Runnable` rather than literally the user's `Runnable`, so do not rely on `TaskDecorator` to catch or observe every exception inside `Future`s. Its purpose is **context propagation**, not general error handling.

### 5.2. Cleaning Up Context Is Just as Important as Propagating It

Wrong:

~~~java
return () -> {
    MDC.put("requestId", capturedId);
    task.run();  // If task throws an exception, MDC lingers on the pooled thread.
};
~~~

Right in principle:

~~~java
return () -> {
    String previous = MDC.get("requestId");
    try {
        MDC.put("requestId", capturedId);
        task.run();
    } finally {
        if (previous == null) MDC.remove("requestId");
        else MDC.put("requestId", previous);
    }
};
~~~

This is a simplified version for **one key**. To propagate full MDC maps, use `MDC.getCopyOfContextMap()` and `MDC.setContextMap(...)` with clear/restore (see the project below). Even then, only privacy-reviewed keys should enter MDC; context propagation does not replace redaction.

## 6. `SecurityContext`: Controlled Propagation

Spring Security normally manages `SecurityContext` via `SecurityContextHolder`, typically thread-local. A new worker does not automatically inherit the request's identity.

Spring Security provides:

- `DelegatingSecurityContextRunnable` / `DelegatingSecurityContextCallable`.
- `DelegatingSecurityContextExecutor`, `DelegatingSecurityContextTaskExecutor`, and `DelegatingSecurityContextAsyncTaskExecutor`.
- Integrations with certain Spring MVC async types, such as `Callable`; do not assume every custom executor or background job is protected identically.

Illustrative executor wrapper example:

~~~java
AsyncTaskExecutor delegate = configuredExecutor;
AsyncTaskExecutor secured =
        new DelegatingSecurityContextAsyncTaskExecutor(delegate);
~~~

Requires imports `org.springframework.core.task.AsyncTaskExecutor` and `org.springframework.security.task.DelegatingSecurityContextAsyncTaskExecutor`, plus the Spring Security dependency. Using the constructor that takes only a delegate captures the security context at task submission per the class contract, executes under that context, and cleans up afterward.

**Never set `SecurityContextHolder.MODE_INHERITABLETHREADLOCAL` as a "quick fix" for pooled workers.** Pool threads are created and reused at arbitrary times, so inherited values can be stale or belong to the wrong request. Nor should you copy a mutable `Authentication` across untrusted tasks.

More importantly, long-running background jobs should receive **user ID, tenant ID, and required business facts**, then perform appropriate authorization checks at execution time; copying context at enqueue time does not mean permissions remain valid hours later. Follow least privilege and never leak tokens.

## 7. Micrometer Context Propagation and Tracing

Spring Framework 6.2 integrates with the **Micrometer Context Propagation** library. It provides a mechanism to capture registered `ThreadLocalAccessor`s and restore values across thread boundaries.

Example using `ContextSnapshot` (illustrative, requires appropriate dependencies and registry):

~~~java
ContextSnapshot snapshot = ContextSnapshot.captureAll();

executor.execute(() -> {
    try (ContextSnapshot.Scope scope = snapshot.setThreadLocals()) {
        process();
    }
});
~~~

Import:

~~~java
import io.micrometer.context.ContextSnapshot;
~~~

**Do not assume `captureAll()` captures every `ThreadLocal`.** Only context types with a registered `ThreadLocalAccessor` are captured and restored. Spring provides `LocaleContextThreadLocalAccessor` and `RequestAttributesThreadLocalAccessor`, yet in Spring MVC 6.2 documentation these accessors **are not registered automatically**; register them with `ContextRegistry` if you intend to use them. Carefully review request-attributes lifetimes before registering.

Spring 6.1+ includes `ContextPropagatingTaskDecorator`:

~~~java
executor.setTaskDecorator(new ContextPropagatingTaskDecorator());
~~~

Import `org.springframework.core.task.support.ContextPropagatingTaskDecorator`; requires Micrometer Context Propagation on the classpath. This decorator assists with logging/observation context when the proper accessors exist; it adds overhead for tiny tasks and does not replace executor capacity management, timeouts, security authorization, or request lifecycle design.

### 7.1. Cross-Thread Tracing and Cross-Service Tracing Are Different Things

Within one process, a task decorator or context snapshot can restore tracing/observation context on workers. When Service A calls Service B over HTTP, you must **inject/extract tracing headers** following standards like W3C `traceparent` via HTTP client instrumentation. Having `MDC.requestId` on A does not automatically make B receive that ID.

If your application already uses Micrometer Tracing / OpenTelemetry, prefer its built-in context propagation and instrumentation rather than inventing fake span/trace systems. A single trace can contain many spans, and a custom `requestId` does not have to equal `traceId`.

### 7.2. Avoid Double Propagation and Stale Context

When combining multiple task decorators, security wrappers, tracing interceptors, or custom MDC propagation on one executor, define ordering and key ownership clearly. If two mechanisms write the same MDC or `LocaleContextHolder` key, the final value can be unexpected. Test under concurrent requests and ensure proper scope restoration before a worker takes its next task.

## 8. Production Guidance: Choosing the Right Model for the Need

| Purpose | Recommended approach |
| --- | --- |
| Locale-based formatting/messages in short tasks | Pass `Locale`/`ZoneId` explicitly, or use a tested decorator |
| Request ID for `@Async` logs | Capture/copy MDC at submission; restore/clear in worker |
| Spring Security auth in short tasks | Security delegating executor or supported integration |
| Background tasks outliving the HTTP response | Pass immutable business context; do not hold `ServletRequest` |
| Cross-thread / cross-service tracing | Micrometer/OpenTelemetry context propagation and HTTP instrumentation |
| Async HTTP responses | MVC `Callable`/`DeferredResult`/`CompletionStage` + timeouts/interceptors/ASYNC dispatch |
| Waiting for external events | `DeferredResult` or async messaging with lifecycle cleanup |
| Many very small tasks | Measure snapshot/decorator overhead, batching, and pool sizing |
| Jobs via queue/message broker | Serialize permitted explicit metadata; never send Java `ThreadLocal`/`SecurityContext` objects |

Important boundaries:

- **Transactions:** `@Transactional` transaction-bound resources do not follow pooled workers automatically. Never copy `TransactionSynchronizationManager` to another thread to "share" a database transaction. Start a new transaction in the worker/service or redesign the boundary.
- **Persistence:** JPA entity lazy proxies may fail outside the original transaction; prepare DTOs/projections with required data before launching background jobs.
- **Timeouts/cancellation:** if an HTTP async request times out before the task completes, the worker may keep running depending on configuration; handle cancellation, shutdown, idempotency, and avoid writing to already-committed responses.
- **Thread pools:** unbounded queues can accumulate tasks and retain captured context/PII for too long. Choose bounded pools/queues and monitored rejection policies.
- **Error handling:** exceptions in `CompletableFuture` must be handled with `exceptionally`, `handle`, or an appropriate MVC async error path; never swallow failed futures.
- **MDC memory/privacy:** never capture the entire MDC if tokens/PII can reside there. Filter for approved keys like `requestId`/`traceId`.
- **ASYNC dispatches:** Servlet filters may need `DispatcherType.ASYNC` mapping and `asyncSupported=true` if logic must run on the subsequent dispatch. `OncePerRequestFilter` has `shouldNotFilterAsyncDispatch()`; verify default behavior and real configuration with tests.
- **`CompletableFuture` chains:** each `thenApplyAsync` on another executor is a new thread boundary; propagation does not magically "attach to the future object."

## 9. Runnable Spring Boot Project: Propagating Locale + MDC Through `@Async`

The demo sends `GET /api/greeting?name=Lan` with `Accept-Language: vi-VN`. The controller invokes **another Spring bean** having an `@Async("contextExecutor")` method. The executor's decorator captures **`LocaleContext`** and **MDC** at submit time, installs them on the worker, and restores the thread's previous state afterward.

The HTTP response returns `greeting` in the request's language, `locale`, `requestId`, and the worker thread name for observation.

### 9.1. Structure

~~~text
async-context-demo/
├── pom.xml
└── src/
    ├── main/java/demo/
    │   ├── AsyncContextApplication.java
    │   ├── RequestIdFilter.java
    │   ├── AsyncExecutionConfig.java
    │   ├── GreetingService.java
    │   └── GreetingController.java
    └── test/java/demo/AsyncGreetingTest.java
~~~

### 9.2. `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>async-context-demo</artifactId>
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

Micrometer Context Propagation is not needed for this demo because the custom `TaskDecorator` copies the two specific context types directly. To switch to `ContextPropagatingTaskDecorator`, add the dependency and register accessors matching your framework version.

### 9.3. `AsyncContextApplication.java`

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.scheduling.annotation.EnableAsync;

@SpringBootApplication
@EnableAsync
public class AsyncContextApplication {
    public static void main(String[] args) {
        SpringApplication.run(AsyncContextApplication.class, args);
    }
}
~~~

`@EnableAsync` activates Spring async proxies. For the proxy to intercept, the controller must invoke the `@Async` method on an injected service bean, without self-invocation.

### 9.4. `RequestIdFilter.java`

~~~java
package demo;

import java.io.IOException;
import java.util.UUID;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.slf4j.MDC;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

@Component
@Order(Ordered.HIGHEST_PRECEDENCE)
public class RequestIdFilter extends OncePerRequestFilter {

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain) throws ServletException, IOException {

        // Generate a new ID; do not trust an arbitrary X-Request-ID header from the client.
        String id = UUID.randomUUID().toString();
        String oldId = MDC.get("requestId");

        request.setAttribute("requestId", id);
        response.setHeader("X-Request-ID", id);
        MDC.put("requestId", id);

        try {
            chain.doFilter(request, response);
        } finally {
            if (oldId == null) {
                MDC.remove("requestId");
            } else {
                MDC.put("requestId", oldId);
            }
        }
    }
}
~~~

The filter sets `requestId` on the servlet thread before the controller calls the service. `finally` prevents stale data from lingering when the servlet thread is reused. This demonstrates the synchronous request phase before the `ASYNC` dispatch; the response header persists across the lifecycle of the same HTTP response. In real-world setups with multiple dispatches (`ERROR`/`ASYNC`), test and adjust filter registration instead of blindly generating a new ID on every dispatch.

### 9.5. `AsyncExecutionConfig.java`

~~~java
package demo;

import java.util.Map;

import org.slf4j.MDC;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.i18n.LocaleContext;
import org.springframework.context.i18n.LocaleContextHolder;
import org.springframework.core.task.TaskDecorator;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
public class AsyncExecutionConfig {

    @Bean("contextExecutor")
    public ThreadPoolTaskExecutor contextExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(50);
        executor.setThreadNamePrefix("ctx-");
        executor.setTaskDecorator(new LocaleAndMdcTaskDecorator());
        executor.initialize();
        return executor;
    }

    static final class LocaleAndMdcTaskDecorator implements TaskDecorator {
        @Override
        public Runnable decorate(Runnable delegate) {
            // Capture on the caller thread (at submit time).
            LocaleContext capturedLocale =
                    LocaleContextHolder.getLocaleContext();
            Map<String, String> capturedMdc =
                    MDC.getCopyOfContextMap();

            return () -> {
                // Worker may have run another task previously: save old state.
                LocaleContext previousLocale =
                        LocaleContextHolder.getLocaleContext();
                Map<String, String> previousMdc =
                        MDC.getCopyOfContextMap();

                try {
                    if (capturedLocale == null) {
                        LocaleContextHolder.resetLocaleContext();
                    } else {
                        LocaleContextHolder.setLocaleContext(capturedLocale);
                    }

                    if (capturedMdc == null) {
                        MDC.clear();
                    } else {
                        MDC.setContextMap(capturedMdc);
                    }

                    delegate.run();
                } finally {
                    // Restore previous state even if the task throws.
                    if (previousLocale == null) {
                        LocaleContextHolder.resetLocaleContext();
                    } else {
                        LocaleContextHolder.setLocaleContext(previousLocale);
                    }

                    if (previousMdc == null) {
                        MDC.clear();
                    } else {
                        MDC.setContextMap(previousMdc);
                    }
                }
            };
        }
    }
}
~~~

This decorator intentionally does only two things: propagate `LocaleContext` and the MDC map. It does **not** propagate `SecurityContext`, `ServletRequestAttributes`, or transactions. Copying the full MDC map suits illustration; applications with sensitive keys should filter with an allowlist before capturing. With thread pools, cleanup is a security requirement, not merely log aesthetics.

If task volume is very high with tiny tasks, capturing and copying maps on each task adds overhead; benchmark performance and adopt a unified propagation library if your architecture calls for it.

### 9.6. `GreetingService.java`

~~~java
package demo;

import java.util.Locale;
import java.util.concurrent.CompletableFuture;

import org.slf4j.MDC;
import org.springframework.context.i18n.LocaleContextHolder;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

record GreetingResponse(
        String greeting,
        String locale,
        String requestId,
        String workerThread) {
}

@Service
public class GreetingService {

    @Async("contextExecutor")
    public CompletableFuture<GreetingResponse> greet(String name) {
        Locale locale = LocaleContextHolder.getLocale();

        String greeting = "vi".equals(locale.getLanguage())
                ? "Xin chào, " + name
                : "Hello, " + name;

        GreetingResponse response = new GreetingResponse(
                greeting,
                locale.toLanguageTag(),
                MDC.get("requestId"),
                Thread.currentThread().getName());

        return CompletableFuture.completedFuture(response);
    }
}
~~~

The goal here is to observe `Locale` and MDC inside the worker thread. Real localization should use `MessageSource`/resource bundles rather than a ternary operator when there are many messages.

When the `@Async` interceptor dispatches the call, the service method runs on `contextExecutor`. `CompletableFuture.completedFuture(...)` is created **inside the worker**, and the Spring async proxy hands the future to the controller to return once the task completes.

### 9.7. `GreetingController.java`

~~~java
package demo;

import java.util.concurrent.CompletableFuture;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class GreetingController {
    private final GreetingService service;

    public GreetingController(GreetingService service) {
        this.service = service;
    }

    @GetMapping(path = "/api/greeting",
                produces = MediaType.APPLICATION_JSON_VALUE)
    public CompletableFuture<GreetingResponse> greeting(
            @RequestParam(defaultValue = "Lan") String name) {
        return service.greet(name);
    }
}
~~~

The controller receives the request on the Servlet thread, calls the Spring-managed service, receives the future, and returns it to MVC. MVC completes the async response once the future resolves. Do not call `future.join()` in the controller: joining blocks the Servlet thread and defeats most benefits of an async return type.

### 9.8. Running and HTTP Output

In the directory containing `pom.xml`:

~~~bash
mvn spring-boot:run
~~~

Send a Vietnamese request:

~~~bash
curl -i -G 'http://localhost:8080/api/greeting' \
  -H 'Accept-Language: vi-VN' \
  --data-urlencode 'name=Lan'
~~~

Body equivalent to the JSON below (request ID and thread name are dynamic):

~~~json
{
  "greeting": "Xin chào, Lan",
  "locale": "vi-VN",
  "requestId": "f64a2c8b-5e8c-4b02-9053-090122b843c4",
  "workerThread": "ctx-1"
}
~~~

The HTTP response includes an `X-Request-ID` header with the **exact same value** as `body.requestId` for that request. The sample UUID illustrates format only, not a fixed value. When called with `Accept-Language: en-US`, `greeting` is `Hello, Lan` and `locale` is `en-US` under the demo's default locale resolver configuration.

### 9.9. Testing with MockMvc Async Dispatch

Create `src/test/java/demo/AsyncGreetingTest.java`:

~~~java
package demo;

import java.util.UUID;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.asyncDispatch;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.request;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class AsyncGreetingTest {
    @Autowired MockMvc mvc;
    @Autowired ObjectMapper mapper;

    @Test
    void propagatesVietnameseLocaleAndRequestId() throws Exception {
        MvcResult initial = mvc.perform(get("/api/greeting")
                .param("name", "Lan")
                .header("Accept-Language", "vi-VN"))
            .andExpect(request().asyncStarted())
            .andReturn();

        String id = initial.getResponse().getHeader("X-Request-ID");
        assertNotNull(id);
        UUID.fromString(id);

        MvcResult finalResponse = mvc.perform(asyncDispatch(initial))
            .andExpect(status().isOk())
            .andReturn();

        JsonNode body = mapper.readTree(
                finalResponse.getResponse().getContentAsString());

        assertEquals("Xin chào, Lan", body.path("greeting").asText());
        assertEquals("vi-VN", body.path("locale").asText());
        assertEquals(id, body.path("requestId").asText());
        assertTrue(body.path("workerThread").asText().startsWith("ctx-"));
    }

    @Test
    void usesEnglishLocaleForAnotherRequest() throws Exception {
        MvcResult initial = mvc.perform(get("/api/greeting")
                .param("name", "Lan")
                .header("Accept-Language", "en-US"))
            .andExpect(request().asyncStarted())
            .andReturn();

        MvcResult finalResponse = mvc.perform(asyncDispatch(initial))
            .andExpect(status().isOk())
            .andReturn();

        JsonNode body = mapper.readTree(
                finalResponse.getResponse().getContentAsString());
        assertEquals("Hello, Lan", body.path("greeting").asText());
        assertEquals("en-US", body.path("locale").asText());
        assertEquals(
                initial.getResponse().getHeader("X-Request-ID"),
                body.path("requestId").asText());
    }
}
~~~

Run:

~~~bash
mvn test
~~~

The two tests confirm the HTTP MVC async lifecycle (`asyncStarted` and `asyncDispatch`), per-request locale, request ID propagation from header to worker, and worker thread naming. Running two tests sequentially is not enough to prove zero data leakage in all scenarios; production requires concurrent stress tests across multiple locales/users and testing error paths.

**Demo limitations:** Spring Security is not enabled, sessions/`ServletRequest`/transactions are not propagated across workers, no database is connected, and there is no distributed tracing or message queue. When integrating those components, choose appropriate propagation mechanisms for them; the manual `TaskDecorator` handles only `LocaleContext` and MDC.

## 10. Dangerous Examples and Fixes

### 10.1. Wrong: Reading `ThreadLocal` Directly Inside a Worker

~~~java
CompletableFuture.supplyAsync(() -> {
    // Worker may not have the HTTP request's Locale/RequestAttributes.
    return LocaleContextHolder.getLocale().toLanguageTag();
});
~~~

Better when only language is needed:

~~~java
Locale locale = LocaleContextHolder.getLocale();
return CompletableFuture.supplyAsync(
        () -> renderMessage(locale),
        boundedExecutor);
~~~

This is a fragment: `renderMessage` and `boundedExecutor` are supplied by the app. Passing `Locale` is simple and reduces `ThreadLocal` coupling. Decorators/snapshots become genuinely convenient mainly when many internal library layers rely on `LocaleContextHolder`.

### 10.2. Wrong: Always Setting MDC Without Clearing

~~~java
executor.execute(() -> {
    MDC.put("requestId", id);
    service.run();
});
~~~

If `service` throws, `requestId` can linger on the pooled thread and bleed into another request. Use `finally` to restore MDC or a tested executor `TaskDecorator`.

### 10.3. Wrong: Spawning a Manual Thread Per Request

~~~java
new Thread(() -> expensiveWork()).start();
~~~

This bypasses pool management, shutdown, queueing, context, error visibility, and rate limits. Use a managed executor with backpressure and explicit timeouts; for long/durable work, use a queue/job system.

### 10.4. Wrong: Retaining `HttpServletRequest` in Long Background Jobs

~~~java
executor.execute(() ->
        saveAuditRecord(request.getHeader("Authorization")));
~~~

This both holds a request reference past its required lifetime and pushes bearer tokens into jobs/logs. If auditing needs a verified identity, prepare an `AuditActorId` or approved context on the request thread and pass it to the task.

### 10.5. Wrong: Copying Transactions via `ThreadLocal`

A transaction is bound to a specific connection and resources. Copying `TransactionSynchronizationManager` to another thread is not a safe way to share a transaction. Open a transaction on the worker/service with `@Transactional` at the proper proxy boundary when business logic requires it, or redesign to keep a single transaction boundary.

### 10.6. Wrong: Treating `CompletableFuture` as Always Non-Blocking I/O

`CompletableFuture.supplyAsync(() -> jdbcRepository.findAll(), executor)` frees the Servlet thread while the worker waits on JDBC, yet that JDBC I/O **still blocks the worker thread**. Under high load, the worker pool can still exhaust. Choose proper pool sizing, query timeouts, and architecture rather than merely adding `@Async`.

## 11. Debugging Checklist When Context Disappears

1. **Identify the thread boundary:** controller → `@Async` service? common pool? `thenApplyAsync`? scheduled callback? HTTP client?
2. **Check where capture happens:** did the caller thread hold the right locale, MDC, and `SecurityContext` at submit time?
3. **Check the actual executor:** did `@Async` use the `contextExecutor` bean? Did self-invocation bypass the proxy?
4. **Check decorators/wrappers:** are they attached to the executor actually running the task? Are accessors registered if using Micrometer?
5. **Check cleanup:** does `finally` restore prior state on errors, timeouts, or cancellation?
6. **Check duration:** does the task outlive the HTTP request/session? Is `ServletRequestAttributes` held too long?
7. **Check security:** is an inappropriate `Authentication` being passed? Should the job re-authorize when it runs?
8. **Check locale:** does the locale resolver accept `Accept-Language`? Is a default locale masking propagation bugs?
9. **Check tracing:** is a tracing library already propagating automatically? Are multiple wrappers overwriting context?
10. **Check production readiness:** bounded thread pool, queue capacity, rejection policy, error handlers, timeouts, data retention, and multi-node behavior.
11. **Check tests:** one `vi-VN` request, one `en-US` request, run concurrently, assert MDC `requestId` never mixes; test error paths.
12. **Check MVC dispatch:** do filters/interceptors run on `ASYNC` dispatches as needed? Avoid generating a brand-new request ID on the second dispatch.

A common testing mistake is **seeing the expected default locale and assuming propagation works**. Test two distinct languages, configure the locale resolver explicitly, and verify the worker thread truly differs from the initial thread.

## 12. Extended Scenarios

### 12.1. Sending Email Asynchronously After Returning `202 Accepted`

An API accepts a request, returns 202, and an email job continues in a queue. Never hold `LocaleContextHolder` or an HTTP session for an email job that may run much later. Instead construct a job payload:

~~~java
record EmailJob(
        String templateId,
        String recipientId,
        String languageTag,
        String businessCorrelationId) {}
~~~

The worker reconstructs `Locale.forLanguageTag(languageTag)` and verifies needed business context before sending. If the user's language changes between enqueuing and execution, policy must define whether to use the enqueued snapshot or the newer preference.

### 12.2. Workers Using Region-Specific Time

Both `ZoneId` and locale are needed, for example for a user in Vietnam:

~~~java
Locale locale = Locale.forLanguageTag("vi-VN");
ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");
ZonedDateTime time = instant.atZone(zone);
~~~

Requires imports from `java.util` and `java.time`; `instant` must be a defined `Instant`. `Locale` governs language/formatting while `ZoneId` governs time-zone rules; passing one by mistake does not substitute for the other.

### 12.3. Chained Dependent Tasks

In `CompletableFuture`, a non-`Async` `thenApply` callback may run on whichever thread completed the previous stage, not necessarily the request thread. A `thenApplyAsync` callback may run on the common pool if no executor is given. Every stage using context needs an explicit contract; never rely on a "lucky thread" already holding the right value.

### 12.4. Logging Inside an Async Callback

If you only need the request ID for log correlation, passing it as a value:

~~~java
String id = MDC.get("requestId");
executor.execute(() -> {
    try (MDC.MDCCloseable ignored =
            MDC.putCloseable("requestId", id)) {
        service.run();
    }
});
~~~

is a simple option when you control one specific callback. Note that `MDC.putCloseable` removes the key when the scope ends and does not automatically restore a prior value if the worker already held that key; for nested contexts, use full snapshot-and-restore like the `TaskDecorator` in Section 9. Never put secrets into key IDs.

## 13. Self-Assessment Exercises

**Exercise 1 — Basic `ThreadLocal`:** Re-read the program in Section 2 and explain why the first stdout line is `true`. Remove `finally` in the wrapped task and describe the risk when the worker is reused.

**Exercise 2 — Localization:** A request with `Accept-Language: vi-VN` calls `CompletableFuture.supplyAsync()` and the service prints English. Identify where locale was lost and fix it by passing `Locale` into the lambda instead of reading `ThreadLocal` on the worker.

**Exercise 3 — MDC:** Write a `TaskDecorator` that captures `requestId` on submit and restores the previous value afterward. Send 100 concurrent requests with two different locales; verify IDs never mix across responses.

**Exercise 4 — Security:** Compare copying `SecurityContext` into a short task versus a background job running 10 hours later. Why should long-running jobs store user/tenant IDs and authorize under a separate policy?

**Exercise 5 — Spring MVC:** Distinguish `Callable<T>`, `DeferredResult<T>`, a controller returning `CompletableFuture<T>`, and an `@Async` service. Who creates the worker, who keeps the HTTP response waiting, and where does async dispatch occur?

**Exercise 6 — Time Zone:** A locale `en-US` is not enough to determine time zone. Design `DisplayContext(Locale, ZoneId)` to format an `Instant` on a worker.

**Exercise 7 — Micrometer:** State the condition for `ContextSnapshot.captureAll()` to know how to capture `LocaleContextHolder`, and why you should not propagate `ServletRequestAttributes` of a finished request.

**Exercise 8 — `CompletableFuture`:** Given `supplyAsync(..., executorA).thenApplyAsync(..., executorB)`, why might context be right in A yet lost in B? Propose decorators for both or passing explicit context.

**Exercise 9 — Testing:** Write a MockMvc test for two requests with different `Accept-Language` headers, use `asyncDispatch`, and assert the request ID from the header matches the JSON field returned by the worker.

**Exercise 10 — Operations:** Propose metrics/alerting when the pool queue fills up, tasks time out, rejections occur, and 5xx error rates spike. Why should you not infinitely retry non-idempotent POSTs?

## 14. Key Takeaways

- Context **bound to `ThreadLocal`** does not automatically follow to new threads. Propagation must be deliberate at every boundary.
- `LocaleContextHolder` handles language; `RequestContextHolder` binds the request; `MDC` is for logging; `SecurityContextHolder` is for security. They are not interchangeable.
- Prefer **passing explicit immutable business context** to background jobs, especially work outliving the HTTP request.
- With `@Async` and `ThreadPoolTaskExecutor`, use a `TaskDecorator` that **captures on submit, installs on worker, and restores in `finally`**.
- Micrometer Context Propagation and Spring Security executors support conditional propagation; choose the right dependencies, accessors, executors, and lifetimes.
- MVC async return types still go through Servlet async / `ASYNC` dispatches. Never assume `@Async` implies non-blocking I/O or guarantees all context is propagated.
- Test multiple locales/requests concurrently along with error paths to prevent stale context, data leaks, and security bugs.

## 15. Official Documentation

- [Spring Framework 6.2 — Asynchronous Requests](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-ann-async.html): `Callable`, `DeferredResult`, `CompletionStage`, async processing, context propagation, executor configuration.
- [Spring Framework 6.2 — `TaskDecorator`](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/core/task/TaskDecorator.html): interface for task context wrapping.
- [Spring Framework 6.2 — `ContextPropagatingTaskDecorator`](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/core/task/support/ContextPropagatingTaskDecorator.html): Micrometer context propagation in executors.
- [Spring Framework 6.2 — `LocaleContextHolder`](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/context/i18n/LocaleContextHolder.html): thread-bound locale context.
- [Spring Framework 6.2 — `RequestContextHolder`](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/context/request/RequestContextHolder.html): thread-bound request attributes.
- [Spring Security 6.5 — Concurrency Support](https://docs.spring.io/spring-security/reference/6.5/features/integrations/concurrency.html): `DelegatingSecurityContextRunnable`/Executor and Spring task executors.
- [Micrometer — Context Propagation](https://docs.micrometer.io/context-propagation/reference/): `ThreadLocalAccessor`, `ContextRegistry`, and `ContextSnapshot`.
- [W3C Trace Context](https://www.w3.org/TR/trace-context/): `traceparent`/`tracestate` when propagating distributed traces over HTTP.
