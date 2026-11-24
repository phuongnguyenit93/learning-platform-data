# Context Propagation, Thread Safety, and Avoiding Unbounded Executors in Asynchronous Spring MVC

## 1. Context and goals

Spring MVC supports **asynchronous request processing on the Servlet stack** via `Callable<T>`, `WebAsyncTask<T>`, `DeferredResult<T>`, `ResponseBodyEmitter`, `SseEmitter`, `StreamingResponseBody`, and certain reactive return types. When a handler returns an async value, the initial Servlet thread can leave the request early while the response stays open. Subsequent work continues on a thread from an executor, an event callback thread, or another I/O system.

Moving from one thread to multiple threads introduces three categories of risk:

1. **Lost context:** `MDC`/trace IDs, `SecurityContextHolder`, `LocaleContextHolder`, `RequestContextHolder`, transactions, or custom `ThreadLocal`s do not automatically synchronize across all threads.
2. **Data races and leaks:** singleton controllers/services sharing unsynchronized mutable state; thread pools reusing threads that retain a previous request's `ThreadLocal`; requests finishing while callbacks still hold stale request/session/stream references.
3. **Resource exhaustion:** executors spawning unbounded threads or using unbounded queues, long-running blocking tasks, and slow streaming clients causing CPU, heap, connections, disk, database pools, and timeouts to grow unchecked.

After completing this lesson, you will be able to accurately explain the `Callable` vs. `DeferredResult` flow, configure a **bounded `AsyncTaskExecutor`**, propagate MDC/tracing and security context through proper mechanisms, write thread-safe code, handle timeouts/rejections/cancellation, and test async requests using `MockMvc`.

**Scope:** **Java 17+, Spring Framework 6.x, Spring Boot 3.x, Spring MVC Servlet stack**. This is not a non-blocking WebFlux guide or a dedicated Java virtual threads tutorial. Being able to run on virtual threads does not replace concurrency limits, resource bounds, or data security.

## 2. How do the initial request thread and async thread differ?

With `Callable`:

~~~text
Client                         Servlet container             MVC executor
  | GET /api/async/work               |                          |
  |---------------------------------->|                          |
  |                          DispatcherServlet                    |
  |                          calls controller -> Callable        |
  |                          request.startAsync()                |
  |                          submit Callable ------------------->|
  |                          release Servlet thread              |
  |                                                             |
  |                                              Callable runs on worker
  |                                              creates DTO / throws error
  |                          <------ result/async dispatch ------|
  |                          DispatcherServlet resumes            |
  |<------------------------- HTTP response ----------------------|
~~~

Important sequence:

- The controller is invoked on the **initial request-serving thread**.
- The controller returns a `Callable<T>` object rather than running `call()` immediately.
- MVC uses `AsyncTaskExecutor` to run `Callable` on a worker thread.
- When the worker completes, the framework **async dispatches** the request back to the Servlet container to finalize the response or handle exceptions.
- Application code must not assume every `before/after` hook in MVC interceptors/filters runs strictly once on the same thread; with async there can be multiple dispatch phases.

For `DeferredResult<T>`, another system (event listener, message broker callback, scheduler, separate bounded executor) can call `setResult` or `setErrorResult`. **MVC does not automatically run producer work in its executor** merely because the handler returned `DeferredResult`. This is a crucial difference for context propagation.

### Common return types

| Return type | Who performs the next work? | What to watch out for |
| --- | --- | --- |
| `Callable<T>` | MVC `AsyncTaskExecutor` | Thread-local context; queue; timeout; result/error |
| `WebAsyncTask<T>` | Default executor or custom executor if configured | Per-task timeout and callbacks |
| `DeferredResult<T>` | Producer/callback managed by the application or library | Managing producer, completion, timeout, cleanup yourself |
| `CompletableFuture<T>` | Whichever executor the future was actually created/run on | `supplyAsync` without an executor usually uses the common pool |
| `ResponseBodyEmitter`, `SseEmitter` | App event source/producer, HTTP writing system | Slow clients; heartbeats; cleanup; buffer memory |
| `StreamingResponseBody` | MVC async executor runs the `OutputStream` write callback | Blocking writes; client disconnects; executor capacity |
| Reactive return types on Spring MVC | Bridged via MVC async mechanism | Servlet response writes remain blocking at corresponding points |

**Async Servlet does not mean CPU stops working.** It avoids holding the initial Servlet thread throughout the wait for a result, while downstream database queries, HTTP clients, file I/O, and response writes can still block elsewhere.

## 3. ThreadLocal: thread-bound context, not permanently request-bound

A `ThreadLocal<T>` stores values per **current thread**:

~~~java
private static final ThreadLocal<String> TRACE_ID = new ThreadLocal<>();

TRACE_ID.set("req-42");
String here = TRACE_ID.get(); // "req-42" on the thread that just set it
~~~

This example is an illustrative Java snippet inside a class/method, not a full program. If an executor runs a task on **another thread**, `TRACE_ID.get()` on the worker is normally `null`, or worse, **a leaked stale value** from an earlier task that failed to clean up.

Related holders in the Spring ecosystem:

| Context | Access point | Nature |
| --- | --- | --- |
| Correlation/log fields | SLF4J `MDC` | Typically thread-local per logging implementation |
| Security authentication | `SecurityContextHolder` | Default strategy is usually thread-local |
| Locale/time zone | `LocaleContextHolder` | Thread-bound context |
| Request attributes | `RequestContextHolder` | Normally bound to the request-processing thread |
| Transaction | `TransactionSynchronizationManager` | Thread-bound transaction/resource state |
| Tracing observation | Micrometer Observation/trace context | Has its own scope and context propagation mechanism |
| Custom tenant/user metadata | Custom `ThreadLocal` | Must define lifecycle, confidentiality, and cleanup yourself |

**You cannot pick one propagation mechanism and assume it carries all other contexts automatically.** For instance, MDC may hold a trace ID while the worker still lacks `SecurityContext` without the right integration; conversely, a `DelegatingSecurityContextAsyncTaskExecutor` does not automatically copy arbitrary MDC/LocaleContext values.

### Lifecycle rules

1. **Capture** the exact context at the **hand-off point** (submission), not when the class initializes.
2. **Restore** it on the worker right before the callback.
3. **Clean up/restore the previous value** in `finally`, even if the task throws.
4. Do not keep live references to `HttpServletRequest`, `HttpSession`, JPA `EntityManager`, or mutable security objects longer than needed.
5. For background tasks extending beyond the HTTP request, prefer passing **minimal immutable data** (ID, tenant, principal identifier, traceparent/correlation ID) instead of copying the entire request scope.

`InheritableThreadLocal` is not a safe default for thread pools: threads are created/reused at different times and can retain context from unrelated work. In particular, do not enable `RequestContextHolder.setRequestAttributes(..., true)` or `SecurityContextHolder.MODE_INHERITABLETHREADLOCAL` expecting it to handle every pooled worker properly.

## 4. Propagating MDC via `TaskDecorator` with cleanup

When a request carries `X-Request-Id`, you typically want logs in the handler, business service, and worker to share the same request ID.

A `TaskDecorator` can capture an MDC snapshot when the task is submitted to the executor, then set and restore it on the worker:

~~~java
package com.example.demo;

import java.util.Map;
import org.slf4j.MDC;
import org.springframework.core.task.TaskDecorator;

public final class MdcTaskDecorator implements TaskDecorator {

    @Override
    public Runnable decorate(Runnable runnable) {
        Map<String, String> captured = MDC.getCopyOfContextMap();

        return () -> {
            Map<String, String> previous = MDC.getCopyOfContextMap();
            try {
                if (captured == null) {
                    MDC.clear();
                } else {
                    MDC.setContextMap(captured);
                }
                runnable.run();
            } finally {
                if (previous == null) {
                    MDC.clear();
                } else {
                    MDC.setContextMap(previous);
                }
            }
        };
    }
}
~~~

This is a **complete Java file** usable in a Spring Boot project with SLF4J. Key points to note:

- `getCopyOfContextMap()` creates a **snapshot**, avoiding sharing a mutable `Map` across requests.
- `decorate` is invoked on the **submission side**, capturing context **before** the task runs on the worker.
- The task reads context only while executing; `finally` restores the previous context so request A's correlation ID never bleeds into request B.
- Even if the task throws an exception, `finally` still cleans up. Some executors wrap the user task before passing it to the decorator, so **do not rely on the decorator to catch business exceptions**; monitor futures/callbacks/error handlers and logs.
- Propagate only necessary logging fields. Never place passwords, cookies, bearer tokens, or sensitive PII into MDC.

### TaskDecorator does not replace controller filters/interceptors

For MDC to hold values when MVC submits a `Callable`, the request thread must populate the correlation ID **before the task is submitted**. A `OncePerRequestFilter` fits well in the example. If a controller calls `MDC.put` and then `MDC.remove` right in a handler `finally` block, MVC might submit the `Callable` **after the handler returns**, causing the decorator to capture an empty context. Therefore, do not confuse the **controller method** lifecycle with the **Servlet filter chain** lifecycle.

A filter must also handle dispatch types intentionally. `OncePerRequestFilter` has default rules for async/error dispatches; if MDC is needed during async redispatches as well, verify `shouldNotFilterAsyncDispatch`, filter registration, and how context is re-established on each dispatch. The demo focuses on MDC while **the worker runs Callable**, without promising trace context across every filter/async dispatch.

## 5. Spring Security: Callable context differs from arbitrary executor context

With Spring Security 6.x, `SecurityContextHolder` uses a thread-local strategy by default. Spring Security integrates with **Spring MVC `Callable`** via `WebAsyncManagerIntegrationFilter` and `SecurityContextCallableProcessingInterceptor`. When the Security filter chain is configured properly, this integration propagates the request's `SecurityContext` to the thread running the MVC Callable and cleans it up according to the lifecycle.

**However, this does not automatically cover every async type:**

- `DeferredResult` completed by a message listener on another thread: that worker/listener does not automatically have the original context just because MVC returned `DeferredResult`.
- `CompletableFuture.supplyAsync(...)` uses `ForkJoinPool.commonPool()` by default when no executor is supplied and does not automatically inherit request SecurityContext.
- `@Async` uses the executor selected by Spring's async infrastructure, which may be completely separate from the MVC executor.
- `StreamingResponseBody`, callbacks, and self-managed producers must be verified individually rather than inferred from `Callable` behavior.
- An async task running after user logout or permission revocation cannot treat an earlier captured SecurityContext as permanent authorization.

To run **application-submitted tasks** with Spring Security, you can use `DelegatingSecurityContextAsyncTaskExecutor`:

~~~java
@Bean("securityAwareExecutor")
public AsyncTaskExecutor securityAwareExecutor(
        @Qualifier("boundedWorkerExecutor")
        AsyncTaskExecutor delegate) {

    return new DelegatingSecurityContextAsyncTaskExecutor(delegate);
}
~~~

This is an **illustrative bean method**, requiring the Spring Security dependency and a configured `boundedWorkerExecutor` bean, plus imports for `@Bean`, `@Qualifier`, `AsyncTaskExecutor`, and `DelegatingSecurityContextAsyncTaskExecutor`. With the delegate-only constructor, the executor captures the submitter's `SecurityContext` at each task submission, runs the task under that context, and cleans up afterward. If a **fixed SecurityContext** is passed to the other constructor, all tasks run under that identity; that is a deliberate security decision and must not be used by mistake in multi-user web requests.

**Do not stack security context wrappers arbitrarily across multiple layers.** Understand how Spring Security integrates `Callable` natively versus which tasks use a custom executor; test with mock authentication rather than seeing a 200 response and assuming no privilege leakage.

### Authorization must happen at the right boundary

- **Check request permissions** before submitting work and before accessing sensitive resources.
- If a task resumes after a long wait, consider **re-checking authorization** when fetching sensitive data, especially in background jobs.
- Pass only the required principal ID/tenant ID into the task; avoid retaining references to mutable Authentication objects or entire sessions longer than the request.
- Never treat the presence of a `SecurityContext` on a worker as proof that the operation remains authorized forever, as permissions can change.

## 6. Locale, request attributes, tracing, and Micrometer

### 6.1. LocaleContextHolder

In an MVC request, `LocaleContextHolder.getLocale()` may rely on `LocaleResolver` or request locale configuration. A worker spawned via `new Thread(...)` does not automatically have the initial locale. When executing background work, capture **`Locale`** as a value object and pass it to the service instead of forcing the service to read thread-locals:

~~~java
Locale locale = LocaleContextHolder.getLocale();
Callable<String> task = () -> renderMessage(locale, "welcome");
~~~

This is an illustrative snippet in a method having `renderMessage(Locale,String)`. To pass timezone, also capture `ZoneId` or the needed domain type. Explicit parameter passing makes testing easier and avoids holding expired request attributes.

### 6.2. RequestContextHolder

`RequestContextHolder.currentRequestAttributes()` can throw `IllegalStateException` when no request is bound to the thread. Do not "patch" this by pushing raw `ServletRequestAttributes` onto a task that may run after the HTTP response completes. The request, input stream, output stream, and session have their own lifecycles.

Better:

~~~java
String tenantId = validatedTenantIdFromRequest;
String correlationId = validatedCorrelationId;
executor.execute(() -> work(tenantId, correlationId));
~~~

This is an illustrative snippet assuming `executor`, `work`, and validated inputs exist. Choose copyable data such as `String`, `UUID`, or immutable records so the servlet request object is not retained.

### 6.3. Micrometer Context Propagation

Spring Framework 6.1+ provides `ContextPropagatingTaskDecorator` in `org.springframework.core.task.support` for setups using Micrometer Context Propagation. It helps capture/restore logging/observation context across threads when configured properly:

~~~java
pool.setTaskDecorator(new ContextPropagatingTaskDecorator());
~~~

**This is a supplementary illustrative snippet**, requiring the Micrometer context propagation library, a compatible Spring version, and registered context accessors. Do not combine a custom MDC decorator and the Micrometer decorator uncoordinatedly; choose or compose them based on real needs and verify restoration order.

Per Spring MVC documentation, accessors such as `LocaleContextThreadLocalAccessor` and `RequestAttributesThreadLocalAccessor` **must be registered with `ContextRegistry` if you want to use them**—they do not appear automatically in every project. With `ContextSnapshot`:

~~~java
ContextSnapshot snapshot = ContextSnapshot.captureAll();
executor.execute(() -> {
    try (ContextSnapshot.Scope scope = snapshot.setThreadLocals()) {
        doWork();
    }
});
~~~

This is a conceptual snippet for an app with Micrometer configured and matching imports; `executor`/`doWork` are external dependencies. The snapshot is captured on the caller thread; the scope restores context on the worker and reverts state when closed.

**Be cautious:** copying request scope across long-running workers can retain objects and data beyond their lifetime. Context propagation is a policy to design carefully, not a "clone the entire web request" mechanism.

### 6.4. Transactions do not follow across threads automatically

Spring's `@Transactional` manages transaction resources per thread. A `Callable` running on a worker **does not automatically continue a transaction** started on the controller request thread. Isolate transactions inside a service running **on the worker**:

~~~java
return () -> reportService.loadReport(id);
~~~

Here `reportService.loadReport(id)` can be a public `@Transactional(readOnly = true)` method on a Spring-managed service proxy. If the controller method itself is annotated `@Transactional` and just returns a `Callable`, the controller's transaction may already have finished **before the callable even executes**.

Never share a thread-bound JPA `EntityManager` or `Session` across multiple async tasks. Watch out for lazy-loaded entities across async boundaries; load the needed DTOs inside the worker's transaction.

## 7. Thread safety: controllers and services are singletons by default

Spring `@RestController`, `@Service`, and `@Component` are typically **singleton beans**. Multiple concurrent requests invoke the same instance. If a controller has an unsynchronized mutable field:

~~~java
@RestController
public class UnsafeCounterController {
    private int count = 0;

    @GetMapping("/counter")
    public int counter() {
        return ++count;
    }
}
~~~

This class illustrates an anti-pattern and requires `@RestController`/`@GetMapping` imports. The `++` operator performs read–increment–write and is non-atomic. Two requests can lose an increment. When async tasks also access fields, race conditions become even more apparent.

If an in-memory counter is genuinely needed (for demos/simple metrics only), use:

~~~java
private final AtomicInteger count = new AtomicInteger();

int current = count.incrementAndGet();
~~~

`AtomicInteger` protects atomic updates within **one process**, though it does not synchronize across multiple application instances. For bank balances, business sequences, quotas, or inventory, use storage-level synchronization/transactions/constraints or a dedicated service, not just an AtomicInteger.

### Appropriate data types and mechanisms

| State type | How to handle | Mistake to avoid |
| --- | --- | --- |
| Request DTO | Immutable record/local variable | Mutating shared objects across requests |
| Request ID, tenant ID | Immutable snapshot / explicit parameter | Uncleaned `ThreadLocal` |
| Simple counter | `AtomicInteger`, metrics backend | `int++` on a singleton |
| In-process shared map | `ConcurrentHashMap` when contract fits | Unsynchronized concurrent `HashMap` |
| Multi-step compound update | Lock / atomic compute / DB transaction | Thinking ConcurrentHashMap makes multi-step sequences atomic |
| File/stream | Single owning thread or contractual synchronization | Multiple threads arbitrarily writing a shared `OutputStream` |
| Database entity manager | Valid transaction/thread scope | Sharing `EntityManager` across async tasks |
| Global configuration | Immutable `record`/`final` fields | Writing mutable config during request handling |

**Never pass a mutable `HashMap`, `ArrayList`, or shared `StringBuilder` into multiple callbacks** without synchronization. Each async request should own its own data, or enforce explicit concurrency control.

### Atomic does not mean business-safe

~~~java
int current = counter.get();
if (current < limit) {
    counter.incrementAndGet();
}
~~~

The snippet above still has a race: two threads both read `current < limit` and both increment past the quota. Use CAS/atomic update operations or transactional storage matching the business constraint. Do not conclude "using atomic variables makes everything thread-safe".

### `volatile` has limits

`volatile` provides visibility and certain ordering guarantees, yet `volatile int count` **does not make** `count++` atomic. Choose `synchronized`, `ReentrantLock`, atomic classes, or immutability according to the actual operation; avoid slapping `synchronized` across an entire controller and accidentally serializing all requests when high throughput is required.

## 8. Avoiding unbounded executors: three sources of risk

An example unsuitable for production load:

~~~java
ExecutorService executor = Executors.newCachedThreadPool();
~~~

A cached thread pool can keep spawning new threads whenever tasks are busy without a proper fixed cap; under heavy load, memory and scheduler pressure spike sharply. `newFixedThreadPool(8)` bounds worker threads yet uses an **unbounded queue** by default—which can still accumulate huge numbers of pending tasks and trigger out-of-memory errors or severe latency. So "an 8-thread pool" **does not** mean "total work is bounded".

Similarly:

~~~java
CompletableFuture.supplyAsync(() -> slowCall());
~~~

Without passing an executor, it can use the **ForkJoin common pool** instead of your configured MVC executor; thread context, observability, and capacity no longer follow MVC rules. The common pool suits certain controlled CPU-bound tasks, not as a general shortcut for blocking request I/O.

### Real capacity of ThreadPoolTaskExecutor

Key parameters:

- `corePoolSize`: minimum target worker count per pool policy.
- `maxPoolSize`: maximum workers when the queue is full and the pool needs to grow.
- `queueCapacity`: pending tasks allowed before rejecting or scaling up workers.
- `keepAliveSeconds`: idle time before non-core threads are reclaimed.
- `RejectedExecutionHandler`: reaction when capacity is exhausted; **AbortPolicy** is usually safer than silently dropping tasks.
- Timeout/cancellation: limits processing time, avoiding tasks hanging forever.
- Monitoring: active threads, pool size, queue depth, rejection count, latency, timeouts, disconnect rate.

Example `core=2, max=4, queue=16`: once two workers are busy, most new tasks enter the queue first; the pool normally grows from 2 to 4 **only after the queue is full**. Once 4 workers are busy and 16 tasks are queued, the next task can be rejected. This is standard `ThreadPoolExecutor` behavior used by `ThreadPoolTaskExecutor`; do not treat `maxPoolSize=4` as "always runs 4 threads in parallel immediately" while the queue has room.

### Setting a huge queue can be worse

If each task takes 5 seconds and only 4 workers run, a 10,000-request queue retains huge numbers of objects/request snapshots while clients wait pointlessly and time out. A bounded queue forces the system to **acknowledge overload** earlier; handle rejections at the HTTP boundary, plan capacity, and set overall concurrency limits.

Appropriate thresholds depend on downstream resources:
- A DB connection pool with 10 connections: 100 concurrent I/O workers will not necessarily run faster.
- An upstream API rate-limited at 20 QPS: needs rate limiting/circuit breakers/timeouts, not infinite threads.
- File streaming to slow clients: a single blocking callback can hold a worker for a long time.
- CPU-bound jobs: adding threads beyond CPU cores can increase context switching.

**Little's Law** is a useful intuition: concurrent work in progress/waiting roughly equals arrival rate × time in system at steady state. If requests arrive faster than sustainable completion over time, any finite queue will fill—the fix is shedding load or adding real capacity, not switching to an infinite queue.

## 9. Runnable example: bounded MVC executor + MDC propagation

The example below includes:

- A `ThreadPoolTaskExecutor` bounded to **core=2**, **max=4**, **queue=16**, thread prefix `mvc-worker-`, MVC timeout **5 seconds**.
- `MdcTaskDecorator` with snapshot/restore in `finally`.
- A `OncePerRequestFilter` generating/validating `X-Request-Id` and setting `MDC["requestId"]` within the filter scope.
- A controller returning `Callable<WorkResponse>`; the worker reads propagated MDC and returns an immutable record.
- A MockMvc test using `asyncDispatch`, verifying matching request/worker trace IDs and a worker thread distinct from request handling.
- Uses only Spring Boot 3.x web/test; **does not require Spring Security or Micrometer** in the runnable example.

Maven project using Java 17+, Spring Boot 3.x, dependencies `spring-boot-starter-web` and `spring-boot-starter-test`, package `com.example.demo`.

Structure:

~~~text
src/main/java/com/example/demo/DemoApplication.java
src/main/java/com/example/demo/MdcTaskDecorator.java
src/main/java/com/example/demo/AsyncMvcConfig.java
src/main/java/com/example/demo/RequestIdMdcFilter.java
src/main/java/com/example/demo/AsyncWorkController.java
src/test/java/com/example/demo/AsyncWorkControllerTest.java
~~~

### 9.1. Main application

**`DemoApplication.java`**

~~~java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

### 9.2. MdcTaskDecorator.java

Use the exact file contents introduced in section 4, under package `com.example.demo`. Place it in its **own matching file/class**; do not declare two `MdcTaskDecorator` classes with the same fully qualified name.

### 9.3. AsyncMvcConfig.java

~~~java
package com.example.demo;

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

    private final AsyncTaskExecutor executor;

    public AsyncMvcConfig(
            @Qualifier("mvcAsyncExecutor") AsyncTaskExecutor executor) {
        this.executor = executor;
    }

    // Static bean method avoids a circular reference with the configuration itself.
    @Bean("mvcAsyncExecutor")
    public static ThreadPoolTaskExecutor mvcAsyncExecutor() {
        ThreadPoolTaskExecutor pool = new ThreadPoolTaskExecutor();
        pool.setCorePoolSize(2);
        pool.setMaxPoolSize(4);
        pool.setQueueCapacity(16);
        pool.setKeepAliveSeconds(30);
        pool.setThreadNamePrefix("mvc-worker-");
        pool.setTaskDecorator(new MdcTaskDecorator());
        pool.setRejectedExecutionHandler(
                new ThreadPoolExecutor.AbortPolicy());
        return pool;
    }

    @Override
    public void configureAsyncSupport(AsyncSupportConfigurer configurer) {
        configurer.setTaskExecutor(executor);
        configurer.setDefaultTimeout(5_000L); // milliseconds
    }
}
~~~

Sizing parameters are **demo-only**. In production, design queues/rejection around SLOs, throughput, workload type, database pools, and pod/server counts. Spring Framework docs emphasize that the default MVC async executor is **not suitable for production under load**; explicit configuration is strongly recommended.

**There is no need** to add `@EnableAsync` just to use Spring MVC `Callable`. `@EnableAsync` serves the separate `@Async` infrastructure, which may use a different executor.

### 9.4. RequestIdMdcFilter.java

~~~java
package com.example.demo;

import java.io.IOException;
import java.util.UUID;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.slf4j.MDC;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

@Component
public class RequestIdMdcFilter extends OncePerRequestFilter {

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain) throws ServletException, IOException {

        String candidate = request.getHeader("X-Request-Id");
        String requestId = candidate != null &&
                candidate.matches("[A-Za-z0-9_-]{1,64}")
                ? candidate : UUID.randomUUID().toString();

        String previous = MDC.get("requestId");
        try {
            MDC.put("requestId", requestId);
            chain.doFilter(request, response);
        } finally {
            if (previous == null) {
                MDC.remove("requestId");
            } else {
                MDC.put("requestId", previous);
            }
        }
    }
}
~~~

**Why does this filter avoid simple memory leaks?**

- `requestId` is capped at 64 characters and restricted to an allowlist, reducing log-injection risks via headers.
- Context is set **before** `DispatcherServlet`, so when MVC submits the `Callable`, the decorator captures the active MDC.
- `finally` restores the initial thread's context, even on exceptions.
- The worker thread also restores its prior context via `MdcTaskDecorator`.
- The default filter has specific behavior on ASYNC dispatches; the demo **only proves propagation on the worker**. If you need MDC across redispatches/filters/controller advice as well, register and test an explicit strategy rather than assuming it persists everywhere.

In real systems, correlation IDs may be generated by ingress/gateways. Do not blindly trust `X-Request-Id` from arbitrary clients, especially when correlating logs across trust boundaries; apply renaming, validation, regeneration, or trace-ID mapping policies based on trust boundaries.

### 9.5. AsyncWorkController.java

~~~java
package com.example.demo;

import java.util.concurrent.Callable;

import org.slf4j.MDC;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/api/async")
public class AsyncWorkController {

    @GetMapping("/work")
    public Callable<WorkResponse> work(
            @RequestParam(defaultValue = "demo") String job) {

        if (job.length() > 40) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "job too long");
        }

        // Snapshot request data before leaving the Servlet thread.
        String requestTrace = MDC.get("requestId");

        return () -> {
            // Runs on the bounded MVC AsyncTaskExecutor.
            String workerTrace = MDC.get("requestId");
            String workerThread = Thread.currentThread().getName();

            return new WorkResponse(
                    job, requestTrace, workerTrace, workerThread);
        };
    }

    public record WorkResponse(
            String job,
            String requestTrace,
            String workerTrace,
            String workerThread) {}
}
~~~

**Here `Callable` does not contain `Thread.sleep`** because the goal is proving thread context and the bounded executor reliably in tests. Real work might call a service or read a file, requiring an executor sized for blocking levels, time bounds, and downstream capacity.

`WorkResponse` is an immutable Java record; do not store mutable shared fields on a singleton controller. Both `job` and `requestTrace` are request snapshots, requiring no access to `HttpServletRequest` on the worker.

### 9.6. MockMvc testing with asyncDispatch

**`src/test/java/com/example/demo/AsyncWorkControllerTest.java`**

~~~java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders
        .asyncDispatch;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders
        .get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers
        .jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers
        .request;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers
        .status;

@SpringBootTest
@AutoConfigureMockMvc
class AsyncWorkControllerTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void callableCarriesMdcAndUsesBoundedExecutor() throws Exception {
        MvcResult pending = mockMvc.perform(
                        get("/api/async/work")
                                .param("job", "report")
                                .header("X-Request-Id", "req-123"))
                .andExpect(request().asyncStarted())
                .andReturn();

        MvcResult completed = mockMvc.perform(asyncDispatch(pending))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.job").value("report"))
                .andExpect(jsonPath("$.requestTrace").value("req-123"))
                .andExpect(jsonPath("$.workerTrace").value("req-123"))
                .andReturn();

        String json = completed.getResponse().getContentAsString();
        assertTrue(json.contains("mvc-worker-"));
    }

    @Test
    void rejectsJobNameThatIsTooLong() throws Exception {
        mockMvc.perform(get("/api/async/work")
                        .param("job", "a".repeat(41)))
                .andExpect(status().isBadRequest());
    }
}
~~~

**Interpreting the test value properly:**
- `request().asyncStarted()` confirms the request entered async handling.
- `asyncDispatch(pending)` routes the completed result through Servlet/MVC dispatch to finish the response; only then should JSON be asserted.
- `requestTrace=workerTrace` proves MDC propagation on this demo `Callable` path.
- `workerThread` containing the `mvc-worker-` prefix proves the task ran on the named pool.
- The test **does not prove the pool withstands overload** from thousands of clients. Add load/integration tests to measure active threads, queue depth, rejections, timeouts, memory, DB pools, and 503s.
- The test does not include Spring Security; if the real app has Security filters, configure/mock authentication compatibly.

Run tests:

~~~bash
./mvnw test
~~~

On Windows use `mvnw.cmd test`; if the Maven wrapper is missing, use `mvn test` with Maven installed.

### 9.7. Calling curl

Start the application:

~~~bash
./mvnw spring-boot:run
~~~

Then:

~~~bash
curl -i   -H "X-Request-Id: req-123"   "http://localhost:8080/api/async/work?job=report"
~~~

HTTP 200 output contains JSON with the **same trace ID**:

~~~json
{
  "job": "report",
  "requestTrace": "req-123",
  "workerTrace": "req-123",
  "workerThread": "mvc-worker-1"
}
~~~

**Note:** the thread name `mvc-worker-1` is illustrative only; the actual worker may be `mvc-worker-2` or another name depending on scheduling order. Do not assert exact thread names/IDs. What to verify is the prefix and trace ID.

Line-continuation commands above use Linux/macOS/Git Bash `\` syntax. On Windows PowerShell, use `curl.exe` on one line or PowerShell line-continuation syntax.

## 10. DeferredResult: where does the producer run and how to clean up?

`DeferredResult` allows returning a response from an event/task completing later:

~~~java
@GetMapping("/wait-for-message")
public DeferredResult<String> waitForMessage() {
    DeferredResult<String> result =
            new DeferredResult<>(5_000L, "timeout");

    messageBroker.registerListener(payload -> {
        result.setResult(payload);
    });

    result.onCompletion(() ->
            messageBroker.unregisterListener(result));

    return result;
}
~~~

This is a **conceptual illustration**, not standalone runnable code since `messageBroker` and its register/unregister API are hypothetical. Producer callbacks may run on a broker thread. In implementations returning a listener handle, store the exact subscription/token to unsubscribe in `onCompletion`, `onTimeout`, and `onError` as appropriate.

Rules to apply:

- **Do not create a dedicated thread per request** just to wait for events; use existing event-loop/message-broker infrastructure or a dedicated bounded executor.
- Never keep `DeferredResult` in an unbounded map without capping subscribers or cleaning up on completion/timeout/disconnect.
- Treat `setResult`/`setErrorResult` as competitive (the request may time out concurrently); inspect the boolean return value where appropriate.
- Context from the initial request **does not appear automatically** on broker listeners. Capture needed immutable fields, or use the producer's snapshot/propagation mechanism.
- If a producer fails after the request has timed out, there is no guarantee an error body can be sent as on an uncommitted response.

### WebAsyncTask for a task with a custom timeout

~~~java
@GetMapping("/slow-task")
public WebAsyncTask<String> slowTask() {
    WebAsyncTask<String> task = new WebAsyncTask<>(
            2_000L, () -> slowService.call());

    task.onTimeout(() -> "timeout");
    task.onError(() -> "error");
    return task;
}
~~~

This is an illustrative handler requiring imports for `WebAsyncTask`, `@GetMapping`, and an injected `slowService`. `WebAsyncTask` attaches timeout/callbacks to an MVC `Callable` task. **An HTTP request timeout is not a guaranteed mechanism to stop work already running on a worker**; if a downstream call does not support cancellation/timeouts, it can keep consuming resources after the client already received a timeout response.

If choosing a `"timeout"` fallback, evaluate the HTTP status code and API contract; do not assume returning a fallback string with status 200 fits every endpoint.

## 11. Timeouts, cancellation, rejection, and backpressure

### 11.1. Multi-layer timeouts

| Layer | Example | Effect |
| --- | --- | --- |
| Spring MVC async timeout | `configurer.setDefaultTimeout(5_000)` | Limits how long to wait for the async result in Servlet lifecycle |
| HTTP client timeout | Connection/read/response timeout calling upstream | Limits how long the worker waits externally |
| DB query timeout | Transaction/query timeout | Limits work at the database |
| Queue wait timeout | Deadline before task execution starts | Prevents requests waiting pointlessly |
| Reverse proxy idle timeout | Nginx/ingress/CDN | May close connections before Spring finishes |
| Browser/client abort | User closes page, AbortController | Client no longer wants the result; server must clean up |
| Business deadline | Overall deadline with context/cancellation | Avoids continuing operations past useful lifetime |

**Do not just set `setDefaultTimeout` and think blocking tasks will be stopped.** Spring/Servlet can end the request and release the response, while tasks calling slow services still need timeouts/cancellation at the corresponding I/O layers. Java interruption cannot break every blocking API.

### 11.2. Rejection when the pool is full

With `AbortPolicy`, tasks are rejected once capacity is exhausted. In Spring Task execution, you may see `TaskRejectedException` or a wrapped/routed exception depending on API/version.

A proper architecture:
1. Never swallow rejections and leave clients hanging with no response.
2. Translate rejections caught at the HTTP boundary into **503 Service Unavailable** or a contractual status, optionally with `Retry-After` when a suitable retry strategy exists.
3. **Never auto-retry immediately inside the request in an unbounded loop**, as that worsens load.
4. Add queue/rejection metrics, alerts, rate limiting, and admission control.
5. Test realistically with controlled blocking tasks in an isolated environment to prove the pool hits bounds and responses are handled properly.

Example handler at a layer where the exception is known to reach MVC:

~~~java
@RestControllerAdvice
class CapacityErrorAdvice {

    @ExceptionHandler(TaskRejectedException.class)
    ResponseEntity<Map<String, String>> overloaded() {
        return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
                .body(Map.of("error", "SERVER_BUSY"));
    }
}
~~~

This is an **illustrative class**, not required for the runnable demo in section 9. It requires imports `@RestControllerAdvice`, `@ExceptionHandler`, `TaskRejectedException`, `ResponseEntity`, `HttpStatus`, and `Map`. **It is not guaranteed** that every executor exception reaches `@RestControllerAdvice`: errors can arise during async submission, filters, executor schedulers, or after response commit. Test end-to-end along real paths and add filter/container error handling where needed.

### 11.3. CallerRunsPolicy is not always good for MVC

`CallerRunsPolicy` executes the task on the caller thread when the pool is full. While it can create backpressure in certain worker pipelines, on an MVC request path the caller thread is normally the **Servlet request thread**; if the task blocks for a long time, you occupy the Servlet thread and lose the benefit of async. Do not pick CallerRuns just because "you do not want to lose tasks"; evaluate its impact on the entire server.

**DiscardPolicy** drops tasks without ensuring the response completes, which is especially dangerous for a waiting `Callable`; avoid it for request/response workloads unless the design has explicit completion/error handling.

### 11.4. Supplementary semaphore/admission control

A bounded queue caps total pending tasks in one instance, but does not strictly cap HTTP/SSE/file-stream connections or concurrent DB queries if other executors are active too. You can enforce a per-downstream semaphore or per-tenant quota before submitting work, returning 429/503 when slots are exhausted, and releasing in `finally`.

~~~java
if (!semaphore.tryAcquire()) {
    throw new ResponseStatusException(
            HttpStatus.TOO_MANY_REQUESTS, "too many concurrent jobs");
}
try {
    return compute();
} finally {
    semaphore.release();
}
~~~

This is an **illustrative snippet inside a service/work-running method**, where `semaphore`, `compute`, and imports already exist. Place `release` at the lifecycle point **when the work actually finishes**, not just when the controller returns `Callable`. An in-process semaphore does not automatically cap total load across all application replicas.

## 12. CompletableFuture, @Async, and separate executors

### `CompletableFuture`

~~~java
CompletableFuture<Report> future =
        CompletableFuture.supplyAsync(
                () -> reportService.generate(id),
                boundedExecutor);
~~~

This is a snippet assuming `reportService`, `id`, and `boundedExecutor` exist. Specify a **bounded executor** rather than letting `supplyAsync` fall back to the common pool by default. If callbacks need request context, capture immutable IDs and propagate via the executor. Never keep `HttpServletRequest`/JPA entities alive across async boundaries.

When chaining futures, account for stages:
- `thenApply` may run on whichever thread completed the previous stage.
- `thenApplyAsync` without an executor uses the default async facility, usually the common pool.
- `thenApplyAsync(..., boundedExecutor)` clarifies where the next stage runs, yet still needs timeouts and propagation.
- `exceptionally`, `handle`, and `whenComplete` must clean up resources and errors per contract.

### `@Async`

~~~java
@Service
class ReportService {

    @Async("reportExecutor")
    public CompletableFuture<String> generate() {
        return CompletableFuture.completedFuture("done");
    }
}
~~~

This is an **illustrative class**, requiring imports, a `reportExecutor` bean, and `@EnableAsync` in configuration. Spring `@Async` via AOP proxies normally intercepts only **calls going through the Spring proxy**; self-invocation like `this.generate()` inside the same bean will not switch threads.

MVC `configureAsyncSupport(...).setTaskExecutor(mvcExecutor)` and the executor used by `@Async` **are two separate configuration mechanisms**. If you want to share a pool, explicitly declare/register the same bean and evaluate whether long jobs can congest async requests. Many systems should **isolate pools by workload** (quick MVC callbacks, report jobs, streaming), each with its own quotas and shutdown policies.

## 13. ResponseBodyEmitter, SSE, and StreamingResponseBody: yet another threading challenge

### 13.1. StreamingResponseBody

~~~java
@GetMapping("/download")
public StreamingResponseBody download() {
    return outputStream -> {
        try (InputStream input = fileService.openAuthorizedFile()) {
            input.transferTo(outputStream);
        }
    };
}
~~~

This is an illustrative handler requiring `fileService` and imports for `StreamingResponseBody`, `InputStream`, and `@GetMapping`. Open the source stream only **inside the callback**, never in the controller where it could be closed before the async task runs. `transferTo` copies incrementally without loading the entire file onto the heap, yet writing the response can still **block** on slow clients.

If the same executor serves both JSON `Callable`s and long downloads, 4 slow file downloads can occupy every worker, causing normal requests to queue and time out. Consider separating workloads and setting rate/concurrency limits when streaming heavily.

### 13.2. SseEmitter

~~~java
@GetMapping(path = "/events",
        produces = MediaType.TEXT_EVENT_STREAM_VALUE)
public SseEmitter events() {
    SseEmitter emitter = new SseEmitter(30_000L);
    emitter.onCompletion(() -> subscriptions.remove(emitter));
    emitter.onTimeout(() -> subscriptions.remove(emitter));
    subscriptions.add(emitter);
    return emitter;
}
~~~

This illustrative snippet assumes `subscriptions` is a thread-safe collection (such as a concurrent set) managed by a service. The controller merely registering the emitter **does not send events**; an application producer must send events and call `complete`/`completeWithError` when appropriate.

Management responsibilities:

- Bound SSE client counts, connection durations, buffered outbound events, and memory per subscriber.
- Do not call `send` chaotically from multiple producer threads onto the same `SseEmitter` without coordinating concurrent writes.
- Use heartbeats/periodic events to detect client disconnects in Servlet environments; lost clients may only be noticed when a write occurs.
- Clean up on `onCompletion`/`onTimeout`/`onError`, including when errors happen while the producer is pushing.
- Never retain subscriber `SecurityContext`, `HttpServletRequest`, or `ThreadLocal`s across a long-lived SSE connection.

Similarly for `ResponseBodyEmitter`: data is sent asynchronously by producers, yet lifecycle callbacks, serialization/blocking writes, and resource ownership must be managed explicitly.

## 14. Testing properly: MockMvc, concurrency, and production observability

### 14.1. MockMvc for correctness

Core assertions for `Callable`:
- Initial request has `asyncStarted`.
- Async result is **dispatched**.
- JSON output is accurate and needed context propagated.
- Errors/timeouts are handled per contract.

Never use `Thread.sleep(...)` to guess when an async worker finished in tests. `MockMvc` provides async result handling and `asyncDispatch`; tests must wait through the proper lifecycle.

### 14.2. Testing load/rejection with real HTTP

To test real pool capacity, run the server on a real HTTP socket and send concurrent requests to an endpoint whose task blocks via controlled synchronization in a **test environment**. Measure:
- Active workers never exceed configured max.
- Queue never exceeds its bound.
- Subsequent requests are rejected/timed out per policy.
- `MDC` is never lost and context never leaks between different request IDs.
- Valid error responses appear when the pool has no capacity left.
- Recovery after overload: queue drains, thread counts stabilize, memory does not grow forever.

**Never run extreme load tests on production** just to "check for unbounded executors", as that can disrupt service. Pick a test environment, allocate a traffic budget, and observe metrics.

### 14.3. Spring Boot Actuator / Micrometer metrics

With Spring Boot Actuator and a corresponding metrics registry, you can monitor:
- Active thread/pool/queue metrics on properly bound executors.
- HTTP server request durations and 2xx/4xx/5xx statuses.
- JVM heap, threads, GC pauses, CPU.
- Database connection pool saturation.
- Rates of 503/429/rejections, async timeouts, and client disconnects.
- Trace/log correlation across workers and downstream calls.

Do not rely solely on total HTTP 200 counts. A system with a 10,000-job queue may still return many 200s while p99 latency and memory degrade badly.

### 14.4. Testing for cross-request leakage

Send request A with `X-Request-Id: req-A` and B with `X-Request-Id: req-B`. When worker threads are reused, A must never see `req-B` and vice versa. Sequential tests may miss races; run concurrent stress tests with many request IDs and check trace fields in outputs and logs.

MDC cleanup in `finally` is a key safeguard, yet if the app creates other custom `ThreadLocal`s, test and clean up those exact contexts too.

## 15. Common mistakes

| Mistake | Why it is wrong | Better practice |
| --- | --- | --- |
| Assuming `@Async` uses the MVC executor automatically | The two mechanisms can be separate | Declare executors explicitly per workload |
| Thinking MVC async turns blocking I/O into non-blocking | Workers still block on DB/network/streams | Bound concurrency, set timeouts, pick the right I/O stack |
| Using an unbounded cached pool | Threads/memory/scheduler explode under load | Bounded pools/queues, admission control |
| Using a fixed pool with default unbounded queue | Pending tasks can grow without limit | `ThreadPoolTaskExecutor` with explicit `queueCapacity` |
| Propagating MDC without propagating SecurityContext | Two separate holders/semantics | Proper Spring Security integration and wrappers |
| Using InheritableThreadLocal in a pool | Thread reuse preserves wrong-request context | Per-task capture/restore/cleanup |
| Clearing MDC in controller finally before submit | Async submission can happen after controller return | Set in request filter or capture explicit IDs |
| Holding `HttpServletRequest` in background jobs | Request may complete/become invalid | Immutable snapshots before submit |
| Sharing `EntityManager` across threads | Thread-bound transaction semantics | Open service transaction inside worker |
| `volatile int count++` | Increment is still non-atomic | Appropriate atomic/lock/transaction |
| Assuming `ConcurrentHashMap` makes all logic atomic | Read-check-write sequences still race | Atomic map methods/transactions |
| Swallowing rejections to let requests "wait" | Requests time out with no one completing them | Return 503/429 or bounded retries |
| Setting only MVC request timeouts | Downstream blocking tasks keep running | Deadlines and cancellation per I/O call |
| `CallerRunsPolicy` for MVC requests | Can block Servlet request threads | Evaluate overload semantics separately |
| Keeping thousands of SSE emitters without cleanup | Memory and connection resource leaks | Bound subscriber counts, timeouts/cleanup |
| Using `MockMvc` to prove overload immunity | MockMvc cannot replace HTTP load/production metrics | Integration/load tests matching workload |
| Logging session tokens in MDC | Credential leaks via logs | Propagate only necessary correlation metadata |

## 16. Review questions

**1. Why might `Callable<T>` need context propagation while a controller method does not?**

The controller runs on the Servlet request thread with initial context; `Callable.call()` runs later on a different worker thread. Thread-local values do not automatically exist on workers in all cases.

**2. What must `TaskDecorator` do besides `MDC.setContextMap`?**

Capture a snapshot on submission and **restore/clear in `finally`** after the worker runs, preventing data leakage across requests when threads are reused.

**3. If Spring Security 6.x already integrates with MVC Callable, do DeferredResult producers also get SecurityContext automatically?**

No. `WebAsyncManagerIntegrationFilter` integration applies to the Callable lifecycle; event/broker producers or custom executors require their own propagation mechanism.

**4. Does `newFixedThreadPool(8)` genuinely cap the number of pending tasks?**

No. It caps threads, while the factory's default queue is typically unbounded, so pending tasks and memory can still grow unboundedly.

**5. With `core=2,max=4,queue=16`, when does the pool grow to a third worker?**

In standard `ThreadPoolExecutor`, once core threads exist, new tasks are queued first. Only when the queue is full does the pool attempt to add workers up to max; beyond full capacity, it rejects.

**6. Does `setDefaultTimeout(5000)` automatically interrupt every blocking DB query?**

Not guaranteed. It governs MVC async timeout in the Servlet lifecycle; you need query/socket/call timeouts and cancellation appropriate to each downstream.

**7. Should a transaction `ThreadLocal` be copied to an async worker?**

Do not copy it raw. Open a fresh transaction in the service executed on the worker so thread-bound resources are managed properly.

**8. Why do Stream/SSE endpoints still need concurrency limits despite using async?**

Streams still hold connections, buffers, and can hold threads during blocking writes to slow clients. Async requests do not create infinite resources.

**9. Can `CompletableFuture.supplyAsync(...)` without an executor be used for many blocking HTTP calls?**

Do not do so by default, because the common pool and its context handling/capacity may not be suitable; specify a bounded executor tailored to the workload.

**10. If request A's logs appear inside request B, what should you check?**

Check MDC/ThreadLocal cleanup in `finally`, worker reuse, whether `TaskDecorator` captures context at submission time, async dispatches, other executors, and nested contexts.

## 17. Production implementation checklist

1. **Map out async boundaries**: Servlet request, MVC Callable/WebAsyncTask, DeferredResult producer, `@Async`, CompletableFuture, message brokers, streaming callbacks.
2. For each boundary, identify **who owns the executor**, threads, timeouts, exception handling, and cleanup.
3. Use bounded thread pools/queues and cap concurrent tasks; avoid unbounded executors/queues for blocking work.
4. Enforce admission control and overload behavior; return contractual 503/429 instead of silently dropping.
5. Capture **immutable request/tenant/correlation context** before submission; never retain the full servlet request or JPA session.
6. Propagate MDC/logging/tracing via TaskDecorator or Micrometer Context Propagation; clean up/restore in `finally`.
7. Handle SecurityContext via appropriate Spring Security integrations/wrappers, not `InheritableThreadLocal` as a blanket fix.
8. Open transactions inside worker services when needed; keep singleton controllers/services stateless or properly synchronize shared mutable state.
9. Set MVC timeouts, downstream I/O timeouts, deadlines/cancellation; measure client disconnects and async errors.
10. Do not mix long streams/downloads with quick-response Callable pools if resource sharing causes starvation.
11. Test `MockMvc asyncDispatch`, context propagation, and responses; run real HTTP load tests for queues/rejections/timeouts.
12. Monitor active threads, queue depth, p95/p99 latency, DB pools, rejections, memory, trace correlation, and leaks; tune capacity from measurements rather than setting huge max threads.

## Official documentation

- [Spring Framework 6.2 — Asynchronous Requests (MVC)](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-ann-async.html)
- [Spring Framework 6.2 — AsyncSupportConfigurer](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/servlet/config/annotation/AsyncSupportConfigurer.html)
- [Spring Framework 6.2 — ThreadPoolTaskExecutor](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html)
- [Spring Framework 6.2 — TaskDecorator](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/core/task/TaskDecorator.html)
- [Spring Framework 6.2 — ContextPropagatingTaskDecorator](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/core/task/support/ContextPropagatingTaskDecorator.html)
- [Spring Security 6.5 — Concurrency Support](https://docs.spring.io/spring-security/reference/6.5/features/integrations/concurrency.html)
- [Spring Security 6.5 — Servlet MVC Async Security](https://docs.spring.io/spring-security/reference/6.5/servlet/integrations/concurrency.html)
- [Micrometer — Context Propagation](https://docs.micrometer.io/context-propagation/reference/)
- [Java SE 17 — ThreadPoolExecutor](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html)
