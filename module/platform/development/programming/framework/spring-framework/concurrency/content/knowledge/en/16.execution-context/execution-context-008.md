# Do Not Retain the Entire Request Object After the Request Has Ended

> **Module:** Spring Framework – concurrency  
> **Knowledge group:** Execution Context  
> **Principle:** When dispatching work to `ThreadPoolTaskExecutor`, `@Async`, `CompletableFuture`, or a queue, **do not keep references to the entire `HttpServletRequest`/`ServletRequestAttributes` or objects tied to the request lifecycle** if work can continue after the request ends. **Extract the exact needed data at the request boundary**, validate it, and turn it into a **minimal, immutable snapshot** containing no request/response/session/container objects.

This lesson focuses on Java 17, Spring MVC/Servlet, and asynchronous execution. You must distinguish **controller method returning** from **Servlet async request actually completing**: Spring MVC can keep the response open during a valid async flow. What is prohibited by design here is *storing/re-reading the entire request outside its valid lifecycle*, not denying standard-supported Servlet async.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish the lifetimes of `HttpServletRequest`, `HttpServletResponse`, request-scoped beans, references to `ServletRequestAttributes`, and context stored in `ThreadLocal`.
2. Spot **direct or indirect** reference retention paths via lambdas, anonymous classes, `CompletableFuture` callbacks, `@Async` arguments, queues, scheduled tasks, caches, static maps, and `TaskDecorator`.
3. Explain the risks: reading expired data, races/cross-request contamination, retaining object graphs/payloads too long, data leaks, and errors when context is no longer active.
4. Design compact immutable records/DTOs with only genuinely needed fields: `actorId`, `tenantId`, `correlationId`, `jobId`, and validated business parameters.
5. Use `@Async`/`ThreadPoolTaskExecutor`/`CompletableFuture` in Spring so tasks **receive only snapshots**, never accessing raw requests again when workers run.
6. Distinguish propagating a few logging/tracing values from **passing entire request attributes**, security context, or sessions across threads.
7. Handle file uploads, body streams, cancellation, timeouts, retries, shutdown, and work running long after the response closes.
8. Write Java 17 and Spring Context examples with deterministic output; test with latches and reproducible assertions without relying on the garbage collector.

## 2. Who Owns the Request and How Long Does It Live?

In the Servlet stack, the container creates or manages an `HttpServletRequest` representing HTTP processing. This object is not a DTO freely owned by the application; it can carry or lead to:

- HTTP headers, parameters, cookies, session-related data.
- Attributes added by filters/interceptors/Servlets/Spring.
- Streams/bodies, multipart metadata, and related wrappers.
- References to `ServletContext`, container wrappers, or temporary resources.
- Authentication/locale information via request-related subsystems.
- Async dispatch and corresponding response state.

**Not every attribute is guaranteed to exist across every implementation.** What matters is remembering that **a reference to `HttpServletRequest` can retain many objects unintentionally**. It is also bound by a *usage lifetime contract*, not just RAM concerns.

### 2.1. Synchronous Servlet Request

For a standard request, the Servlet specification scopes the request object's validity to `service()` or filter `doFilter()`. Once processing finishes and the container reclaims control, you must not assume the request remains usable. Containers may reuse/recycle objects to cut allocation costs. Thus, a background lambda calling `request.getHeader(...)` seconds later is **broken by design**, even if locally it occasionally returns a value.

~~~text
Container receives HTTP request
       |
       v
Filter -> DispatcherServlet -> Controller
       |
       +-- Read/validate request (within valid lifecycle)
       |
       +-- Build immutable WorkInput with a few scalar fields
       |
       +-- Enqueue work(WorkInput)
       |
       v
HTTP request ends
       |
       +-- Container may clean up/recycle request
       |
       v
Worker runs later
       |
       +-- Uses only WorkInput (does not retain HttpServletRequest)
~~~

**Do not:** pass `HttpServletRequest` itself into a worker hoping it survives until the worker needs it.

### 2.2. Important Exception: Valid Servlet Async Request

The Servlet API has an asynchronous model: `request.startAsync()` returns an `AsyncContext`. Once async processing has genuinely started, the request/response has a **valid async lifecycle**: the request object remains valid during async processing until `AsyncContext.complete()` (and container-contract dispatches/timeouts).

In Spring MVC, return types like `Callable`, `DeferredResult`, `CompletionStage`, or `CompletableFuture` integrate with Servlet async processing. The controller may **return early**, releasing the Servlet thread, while the logical HTTP request/response **has not completed yet**.

~~~text
Controller method returns CompletableFuture
              |
              v
Spring MVC starts Servlet async processing
              |
              +-- Request/response belong to active async lifecycle
              +-- Initial container thread may exit filter chain
              |
              +-- Future completes -> Async dispatch -> write response
              |
              v
Async request completes / times out / errors
              |
              v
Do not reuse request/response from completed lifecycle
~~~

Therefore, **do not equate** "controller method returns" with "request completes". However, Servlet async keeping validity alive **does not mean** every API on `HttpServletRequest` is thread-safe, or that any worker can access it arbitrarily. Simply submitting a `Runnable` to an executor **does not automatically** extend the Servlet request's lifecycle if the framework has not established a proper async lifecycle.

**Design rule still holds:** business workers use minimal snapshots. Let the framework/container control request/response; do not turn `AsyncContext`'s existence into an excuse to store raw requests out of scope.

### 2.3. What Is the "Request Has Ended" Event?

For normal requests: after Servlet/filter processing actually ends per lifecycle. For async requests: after async handling completes, times out, errors, or finishes via the framework/container mechanism. **Do not predict it by a single controller `return` statement.**

Signals such as the client closing the connection, Spring MVC completing the response, or an internal asynchronous task finishing are all distinct; a fire-and-forget task can outlive the entire request. Client cancellation also does not guarantee any Java task is automatically cancelled.

## 3. The Core Issue: Retaining an Object Graph, Not Just One Variable

Suppose a lambda captures the `request` variable:

~~~java
executor.execute(() -> {
    String tenantId = request.getHeader("X-Tenant-Id");
    generateReport(tenantId);
});
~~~

This is a **non-standalone snippet**: `executor`, `request`, and `generateReport` belong to the application.

There are two problems:

1. **Access timing:** the lambda may run after the response finishes, placing `request.getHeader` outside the valid lifecycle.
2. **Strong reference:** the lambda/task must hold `request` so it can run later. If the queue is long or a future is kept in a map, `request` can remain **reachable** long after the HTTP request ends, along with wrappers, attributes, and reachable objects.

Reference retention diagram:

~~~text
Singleton / ThreadPoolExecutor
     |
     +-- workQueue
             |
             +-- Runnable / Callable / FutureTask
                       |
                       +-- lambda captured request
                                 |
                                 +-- HttpServletRequest
                                 +-- attributes / wrappers
                                 +-- session-related references
                                 +-- potentially large payload and buffers
~~~

GC cannot reclaim an object graph while a strong reference path from roots remains. Not every captured request creates a **permanent memory leak**: if the task completes quickly and the reference is released, retention may only be temporary. Yet long queues, schedulers, static caches, unresolved futures, or stuck workers can turn **temporary retention into a severe problem**.

### 3.1. Why Does Queue Capacity Matter Directly?

Suppose one task accidentally retains roughly **1 MiB** of data from a request's object graph, and the queue holds 5,000 such tasks. That data alone can hold roughly **5,000 MiB (around 4.88 GiB)**, excluding overhead of objects, futures, and thread pools. This is only an **illustrative calculation**; actual object graph size must be measured with a heap profiler.

Hence, besides keeping only snapshots, you must bound `queueCapacity`, pending task counts, deadlines, and rejection policies. Creating a DTO holding an entire 10 MiB body does not solve memory issues merely by renaming the object.

## 4. Direct and Indirect Capture Forms

### 4.1. Lambda Capturing the Request Variable

~~~java
CompletableFuture.runAsync(() -> {
    audit(request.getRequestURI());
}, executor);
~~~

Wrong when the task can outlive the lifecycle; `CompletableFuture` does not keep the request valid on its own. **Fix:** read the needed value before scheduling:

~~~java
String path = request.getRequestURI(); // Within request lifecycle.
CompletableFuture.runAsync(
        () -> audit(path),
        executor);
~~~

This is a **snippet**; `audit` and `executor` are application dependencies. Sanitize/bound path data before logging; URLs can contain sensitive info.

### 4.2. Capturing `this` of the Controller/Handler

~~~java
executor.execute(() -> this.processLater());
~~~

Not every `this` capture is wrong: if `this` is a stateless singleton service, referencing the service does not pull in the raw request. Yet if the controller/handler has a **field storing the current request** or a request-scoped object, the lambda can indirectly retain the entire request. In particular, **never store a request in a mutable field of a singleton controller**, as concurrent requests will overwrite one another.

Keep controllers stateless and pass snapshot arguments to services.

### 4.3. Anonymous Classes and Inner Classes

An anonymous/inner class can hold a reference to the outer instance even when not obvious in code. If the outer instance holds a request, session, file stream, or mutable holder, the task can drag the entire chain of objects along. A static nested class or small record with explicit dependencies is easier to audit.

### 4.4. CompletableFuture Callbacks

~~~java
future.whenComplete((result, error) -> {
    request.setAttribute("result", result);
});
~~~

The callback may run on another thread or after the HTTP request has ended; `request.setAttribute` is not a valid channel for returning data from background jobs. The Future/callback can also retain a reference to `request` until the pipeline finishes.

The same applies to `thenApply`, `thenCompose`, `handle`, `exceptionally`, and `thenCombine`: inspect all captured closures, not just the first lambda.

### 4.5. Tasks/Schedulers/Caches Holding Requests Too Long

Do not store these objects in `@Scheduled` jobs, `DelayQueue`, message payloads, global `ConcurrentHashMap`s, async application events, or singleton state. If a task must survive restarts, persist **validated business data** in durable storage rather than serializing container requests.

### 4.6. Capturing via `ServletRequestAttributes`

~~~java
RequestAttributes attrs =
        RequestContextHolder.currentRequestAttributes();

executor.execute(() ->
        useAttributesLater(attrs));
~~~

This is a **snippet with Spring web imports**. For standard Servlet requests, `ServletRequestAttributes` typically holds references to request/response; capturing it can therefore **indirectly** retain the entire request. Aside from retention risk, accessing those attributes past lifecycle can fail. Do not "wrap" a request inside a holder and call it a snapshot.

## 5. Do Not Confuse ThreadLocal Context With Durable Data for Background Work

In Spring MVC, `RequestContextHolder` typically publishes `RequestAttributes` via a `ThreadLocal` bound to the current processing thread. Spring Security and logging frameworks also have thread-stored contexts. A worker from `ThreadPoolTaskExecutor` is a different thread, **reused** across many tasks.

When leaving the request thread:

- `RequestContextHolder.getRequestAttributes()` on the worker may be `null`; `currentRequestAttributes()` can throw an error when no active context exists.
- `@RequestScope` beans are tied to an HTTP request, not beans usable arbitrarily once request scope ends. Scoped proxies do not automatically extend request lifecycle.
- MDC/locale/SecurityContext do not automatically propagate reliably across every executor type; if needed, use explicit propagation mechanisms.
- If you copy entire `RequestAttributes` to a worker, you can retain the raw request longer or access objects past lifecycle.
- If you fail to clean up `ThreadLocal` on a pooled thread, the next task can see the previous task's correlation/user/tenant. That is a security and correctness bug, not just a memory leak.

### 5.1. Why Is InheritableThreadLocal Not a Solution for Thread Pools?

`RequestContextFilter.setThreadContextInheritable(true)` or similar inheritance mechanisms fit only a very narrow condition: child threads spawned exclusively for the request and **never reused**. Spring Javadoc explicitly warns against enabling inheritance for thread pools that may create new workers on demand. A pooled worker can inherit context from a random request when the thread happened to be created and then keep reusing that context for other requests.

**Do not enable inheriting the entire request context just so `@Async` can "see" HttpServletRequest.**

### 5.2. Propagation ≠ Snapshot for Long-Lived Jobs

Context propagation carries certain state across threads for an **execution scope**. It is useful for tracing/logging along a chain with a defined lifecycle. However, it must not be taken as permission to retain `ServletRequestAttributes` inside a task that may live minutes or hours after the response.

Spring provides `ContextPropagatingTaskDecorator` based on Micrometer Context Propagation for certain context types; if a registry has an accessor for request attributes, propagating it must be carefully evaluated against lifecycle. This is **not** a mechanism to turn a raw request into safe post-completion data.

## 6. The Right Way: Extract a Minimal, Immutable Snapshot

Define the values the worker **genuinely needs**, instead of bringing along the whole "context just in case".

Java 17 example:

~~~java
public record JobInput(
        String jobId,
        String actorId,
        String tenantId,
        String correlationId,
        String documentId) {

    public JobInput {
        java.util.Objects.requireNonNull(jobId);
        java.util.Objects.requireNonNull(actorId);
        java.util.Objects.requireNonNull(tenantId);
        java.util.Objects.requireNonNull(correlationId);
        java.util.Objects.requireNonNull(documentId);
    }
}
~~~

This is a **Java 17 file/record** usable in an application; when declared as a top-level `public record JobInput`, it must be saved in **`JobInput.java`**. It has no `main` method so it is not a standalone runnable demo.

All fields are immutable `String`s, so this record is an **immutable snapshot of the data contained within**. Records only guarantee reference fields are `final`; if a field holds `List<MutableItem>`, `byte[]`, or a mutable entity, the record **does not deep-copy automatically**.

### 6.1. Choosing the Right Fields

| Worker Need | Prefer Passing | Avoid Passing |
| --- | --- | --- |
| Identifying user/actor | Stable, verified `actorId` | Raw `Principal`/`Authentication` object, entire security session if unnecessary |
| Distinguishing tenant | Validated/authorized `tenantId` | Unverified `X-Tenant-Id` header verbatim |
| Log/tracing correlation | Normalized, length-bounded `correlationId` | `HttpServletRequest`, all headers/cookies |
| Processing order/form | `orderId`, `documentId`, validated DTO | Entire mutable `@RequestBody` or raw input stream |
| Uploading large files | Internal storage object key/URI with ACL | `MultipartFile`/`ServletInputStream` still tied to request |
| Controlling deadlines | Simple deadline/timeout with clear contract | Container request/response for the worker to "query time" |
| Authorization | Actor ID and minimal policy-compliant evidence | Tokens, passwords, bearer Authorization header |

Passing an actor ID alone does not automatically grant job permissions. If a task runs long, actual authorization may need **re-checking at execution time** because user privileges may have changed. For special workloads needing identity delegation, use formal security contracts instead of caching raw tokens indefinitely.

### 6.2. Snapshots Must Be Created at the Right Time

~~~text
HTTP request thread
    |
    +-- Authenticate/authorize user
    +-- Validate payload, headers, tenant
    +-- Extract stable IDs + small fields
    +-- Construct immutable JobInput
    +-- Send JobInput to bounded executor/queue
    |
    v
Request completes

Worker:
    |
    +-- Only JobInput + injected services
    +-- Perform business work with own transaction
    +-- Report success/failure using jobId
~~~

Do not create a snapshot **inside the worker** by waiting and re-reading `HttpServletRequest`; that action is already too late. If the body is needed, read/validate **within the valid lifecycle** and consider persisting needed payloads to durable storage if large or long-running.

### 6.3. Immutable Collections and Arrays

~~~java
record BatchInput(String tenantId, java.util.List<String> ids) {
    BatchInput {
        ids = java.util.List.copyOf(ids);
    }
}
~~~

This is a **record snippet**: `List.copyOf` creates an unmodifiable collection for immutable `String` elements. If elements are mutable objects, you still must deep-copy contents when the worker needs consistent state. For `byte[]`, clone on entry/exit to prevent the caller from mutating the array after submit. For an arbitrary `Map<String, Object>`, it **cannot** be considered an immutable snapshot if values contain mutable entities/request objects.

## 7. Standalone Runnable Java 17: Simulating Lifecycle and Fixing the Bug

The following example **does not implement Jakarta Servlet**; it accurately simulates the issue of *using request data after the request has been closed* via a test object. A `CountDownLatch` ensures both the bad and good tasks run only **after** the simulated request has expired, so stdout does not depend on scheduler luck or `Thread.sleep`.

Create file **`RequestLifetimeDemo.java`**:

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public class RequestLifetimeDemo {

    static final class SimulatedRequest {
        private final String requestId;
        private final String tenantId;
        private boolean active = true;

        SimulatedRequest(String requestId, String tenantId) {
            this.requestId = requestId;
            this.tenantId = tenantId;
        }

        synchronized String read(String key) {
            if (!active) {
                throw new IllegalStateException("request already ended");
            }
            return switch (key) {
                case "requestId" -> requestId;
                case "tenantId" -> tenantId;
                default -> throw new IllegalArgumentException(key);
            };
        }

        synchronized void end() {
            active = false;
        }
    }

    record Snapshot(String requestId, String tenantId) { }

    static void await(CountDownLatch gate) {
        try {
            if (!gate.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("gate timeout");
            }
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("interrupted", e);
        }
    }

    public static void main(String[] args) throws Exception {
        ExecutorService worker = Executors.newSingleThreadExecutor();
        CountDownLatch gate = new CountDownLatch(1);
        SimulatedRequest request =
                new SimulatedRequest("req-17", "tenant-A");

        // Snapshot is created while the request is still active.
        Snapshot input = new Snapshot(
                request.read("requestId"),
                request.read("tenantId"));

        try {
            // WRONG: lambda retains the request itself; will read too late.
            CompletableFuture<String> bad =
                    CompletableFuture.supplyAsync(() -> {
                        await(gate);
                        return request.read("requestId");
                    }, worker);

            // RIGHT: lambda retains only two strings in the snapshot.
            CompletableFuture<String> good =
                    CompletableFuture.supplyAsync(() -> {
                        await(gate);
                        return input.requestId()
                                + "/" + input.tenantId();
                    }, worker);

            request.end();   // Simulate HTTP request completion.
            gate.countDown();

            try {
                bad.get(5, TimeUnit.SECONDS);
            } catch (ExecutionException e) {
                Throwable root = e.getCause();
                System.out.println("bad = "
                        + root.getClass().getSimpleName()
                        + ": " + root.getMessage());
            }

            System.out.println("good = "
                    + good.get(5, TimeUnit.SECONDS));
        } finally {
            gate.countDown();
            worker.shutdown();
            if (!worker.awaitTermination(5, TimeUnit.SECONDS)) {
                worker.shutdownNow();
            }
        }
    }
}
~~~

Compile and run with JDK 17+:

~~~bash
javac RequestLifetimeDemo.java
java RequestLifetimeDemo
~~~

**Exact stdout on successful run:**

~~~text
bad = IllegalStateException: request already ended
good = req-17/tenant-A
~~~

### Why Does the Example Produce Deterministic Output?

1. `request.read(...)` is called to build `Snapshot` before `request.end()`, obtaining two stable scalar fields.
2. The "bad" task is enqueued first yet waits on `gate`; `main` calls `request.end()` **before** `gate.countDown()`.
3. Therefore, when the bad task reads the request, the simulated object is always already in the ended state; `CompletableFuture` stores `IllegalStateException`, and `get(...)` throws `ExecutionException` with the root cause.
4. The "good" task does not access `request`, reading only the immutable record; it returns `req-17/tenant-A` once the gate opens.
5. `get(timeout)` and `awaitTermination` make wait points explicit; the program uses neither `Thread.sleep` nor waiting for GC.

**Simulation limitation:** real Servlet containers have many states and `AsyncContext`; whether a container object throws `IllegalStateException` when read past lifecycle **is not guaranteed to behave like this fake**. The demo aims to prove a **safe dependency/lifecycle pattern**, not emulate byte-for-byte how a real container recycles requests.

## 8. Direct Comparison: From Bug-Prone Code to Safe Code

### 8.1. Bad: Passing HttpServletRequest Into an Async Service

~~~java
@Service
class BadReportService {
    @Async("reportExecutor")
    public void generate(HttpServletRequest request) {
        // Request may have already ended its lifecycle by the time the worker runs.
        String tenant = request.getHeader("X-Tenant-Id");
        createReport(tenant);
    }
}
~~~

This is a **bug-illustrating snippet**, requiring Spring `@Service`, `@Async`, `HttpServletRequest`, and `createReport` imports. Both passing the request through the proxy and retaining closures afterward can drag the request into an invalid lifecycle.

### 8.2. Good: Creating the Snapshot in the Controller

~~~java
public record ReportInput(
        String reportId,
        String actorId,
        String tenantId,
        String correlationId) { }

@RestController
class ReportController {
    private final ReportService reports;

    ReportController(ReportService reports) {
        this.reports = reports;
    }

    @PostMapping("/reports/{reportId}")
    public CompletableFuture<String> start(
            @PathVariable String reportId,
            @RequestHeader("X-Correlation-Id") String correlationId,
            Principal principal) {

        // Example: tenantId comes from the verified identity,
        // DO NOT trust arbitrary client tenant headers.
        String actorId = principal.getName();
        String tenantId = lookupAuthorizedTenant(actorId);
        String traceId = validateCorrelationId(correlationId);

        ReportInput input =
                new ReportInput(reportId, actorId, tenantId, traceId);
        return reports.generate(input);
    }
}
~~~

This is an **integrated Spring MVC example (not standalone)**. It requires importing `CompletableFuture`, `Principal`, MVC annotations, and implementing `lookupAuthorizedTenant`/`validateCorrelationId` per security/business contracts. `ReportInput` must be declared in its own file if left as a top-level `public record`. `reports.generate(input)` returns a future to Spring MVC, letting the framework manage the async response. The worker needs no request, principal, or session.

A matching service:

~~~java
@Service
class ReportService {
    @Async("reportExecutor")
    public CompletableFuture<String> generate(ReportInput input) {
        // May start after the controller has already returned.
        // Uses validated input and required beans.
        String result = "report-" + input.reportId()
                + "-tenant-" + input.tenantId();
        return CompletableFuture.completedFuture(result);
    }
}
~~~

This is also a **Spring snippet**, requiring `@EnableAsync`/executor bean and invocation through the Spring proxy. Do not return `HttpServletResponse` from a worker or try to mutate request attributes to return results. Exceptions from an `@Async CompletableFuture` method must be observed/mapped to an appropriate HTTP error response.

### 8.3. Header Data Is Not Automatically Trustworthy

`X-Tenant-Id`, `X-User-Id`, `X-Forwarded-For`, and `X-Correlation-Id` can be sent by clients. **Do not** turn them into "verified identity" merely by copying them from the request into a DTO. Validate/normalize at the trust boundary: verified security principal/claims, tenant policies, allowlisted proxy headers, and length/character restrictions for correlation IDs.

When using `principal.getName()` as the actor ID, verify the actual identity mapping; a display username is not necessarily a durable key. For long-lived jobs, consider using an immutable internal account ID that does not change when an account is renamed.

## 9. Spring @Async: Data Boundary and Proxy

### 9.1. @Async Does Not Keep a Request Valid

`@Async` dispatches a method call through a Spring proxy to an executor. It **does not** extend the lifetime of an `HttpServletRequest` passed as an argument, and does not mean the worker thread is the original servlet-handling thread.

~~~text
HTTP thread:
    validate -> build ReportInput -> asyncBean.generate(input) -> return

Spring proxy:
    submit invocation to executor

Worker thread:
    call generate(ReportInput) -> result / failure
~~~

If the method returns `void` and the request already returned an HTTP response before the worker finishes, you need dedicated job ownership/logging/retry/durability. If the method returns `CompletableFuture` to MVC, the framework can keep the logical async response open until the future completes. In neither case does the worker need to retain the raw request.

### 9.2. @Async Self-Invocation

In default proxy mode, calling `this.generate(input)` from the same instance can bypass `@Async`: the work runs directly instead of going through the proxy. Invoke through the bean proxy from another layer. Even if it "looks synchronous" in tests, **do not** pass a raw request into an async API simply because the current call path happens not to run asynchronously; a later refactor can expose the bug.

### 9.3. Executor Beans Should Be Container-Managed

~~~java
@Configuration(proxyBeanMethods = false)
@EnableAsync
class ExecutorConfig {

    @Bean("reportExecutor")
    ThreadPoolTaskExecutor reportExecutor() {
        ThreadPoolTaskExecutor pool = new ThreadPoolTaskExecutor();
        pool.setCorePoolSize(2);
        pool.setMaxPoolSize(4);
        pool.setQueueCapacity(64);
        pool.setThreadNamePrefix("report-");
        return pool;
    }
}
~~~

This is a **Spring configuration snippet**, requiring imports from `org.springframework.context.annotation`, `org.springframework.scheduling.annotation`, and `org.springframework.scheduling.concurrent`. The Spring context manages bean initialization and shutdown. The queue must have an appropriate bound; parameters are illustrative only, not "64 is optimal".

`ThreadPoolTaskExecutor` is **where tasks can sit waiting**. If tasks capture requests, the pool queue extends reference lifetimes. Using immutable snapshots solves the ownership class of problems; queue capacity, timeouts, rejection, and memory profiling address resource limits.

## 10. Runnable Spring Context Java 17: Passing Only a Snapshot to @Async

The next demo **requires no servlet container**, so it does not pretend `@Async` is managing a Servlet request. It uses Spring `AnnotationConfigApplicationContext`, `@EnableAsync`, and `ThreadPoolTaskExecutor` to demonstrate passing simple input separated from request objects.

### 10.1. Maven Structure

~~~text
spring-request-snapshot/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── SnapshotSpringDemo.java
~~~

`pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-request-snapshot</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.16</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`src/main/java/demo/SnapshotSpringDemo.java`:

~~~java
package demo;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

public class SnapshotSpringDemo {

    public record JobInput(String actorId, String correlationId) { }

    @Configuration(proxyBeanMethods = false)
    @EnableAsync
    public static class Config {
        @Bean("jobExecutor")
        ThreadPoolTaskExecutor jobExecutor() {
            ThreadPoolTaskExecutor e = new ThreadPoolTaskExecutor();
            e.setCorePoolSize(1);
            e.setMaxPoolSize(1);
            e.setQueueCapacity(8);
            e.setThreadNamePrefix("job-");
            return e;
        }

        @Bean
        Worker worker() {
            return new Worker();
        }
    }

    public static class Worker {
        @Async("jobExecutor")
        public CompletableFuture<String> process(JobInput input) {
            return CompletableFuture.completedFuture(
                    input.actorId() + "/" + input.correlationId());
        }
    }

    public static void main(String[] args) throws Exception {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(Config.class)) {

            Worker worker = context.getBean(Worker.class);
            JobInput snapshot = new JobInput("actor-7", "corr-9");
            String result = worker.process(snapshot)
                                  .get(5, TimeUnit.SECONDS);

            System.out.println("job = " + result);
        }
    }
}
~~~

Run in the directory containing `pom.xml`:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.SnapshotSpringDemo
~~~

**Stdout from the demo class on successful run:**

~~~text
job = actor-7/corr-9
~~~

The code includes `main`, bean configuration, the Spring async interceptor, and context closure. No `HttpServletRequest` is needed to execute the worker; the input is a record of two immutable `String`s. In real HTTP applications, the snapshot must be created after authentication/validation at the request boundary.

**Demo limitation:** it does not prove Servlet lifecycle because there is no web server. `RequestLifetimeDemo.java` above simulates the lifetime mismatch; the controller section in section 8 illustrates real Servlet/Spring MVC integration.

## 11. MDC and Correlation ID: Pass Small, Clean Up Properly

A worker may need a correlation ID for logging. A safer approach is passing **a validated string** into the task, then setting MDC for the scope of the task; clean up in `finally` because pooled threads are reused for subsequent requests/jobs.

Example with SLF4J `MDC` (logging framework dependency, **non-standalone snippet**):

~~~java
static Runnable withCorrelation(
        String correlationId, Runnable task) {

    return () -> {
        String previous = MDC.get("correlationId");
        try {
            if (correlationId == null) {
                MDC.remove("correlationId");
            } else {
                MDC.put("correlationId", correlationId);
            }
            task.run();
        } finally {
            if (previous == null) {
                MDC.remove("correlationId");
            } else {
                MDC.put("correlationId", previous);
            }
        }
    };
}
~~~

At submission:

~~~java
String correlationId = validateCorrelationId(
        request.getHeader("X-Correlation-Id"));

executor.execute(withCorrelation(
        correlationId,
        () -> processWithId(correlationId)));
~~~

This is a snippet assuming `validateCorrelationId`, `processWithId`, and `executor` already exist. The snapshot is taken before scheduling; the wrapper **does not need** to capture `request`. Additionally, MDC may hold multiple distinct keys; the example manages only one key for illustration. If the application propagates multiple keys, snapshot only small/permitted keys and restore each key responsibly.

### TaskDecorator Also Must Capture at the Right Time

~~~java
executor.setTaskDecorator(delegate -> {
    String correlationId = MDC.get("correlationId");

    return () -> {
        String before = MDC.get("correlationId");
        try {
            if (correlationId == null) {
                MDC.remove("correlationId");
            } else {
                MDC.put("correlationId", correlationId);
            }
            delegate.run();
        } finally {
            if (before == null) {
                MDC.remove("correlationId");
            } else {
                MDC.put("correlationId", before);
            }
        }
    };
});
~~~

This is an **integration snippet**, assuming `executor` and `MDC` dependencies exist. `TaskDecorator` is applied to the execution callback, yet a task submitted via `submit` may be wrapped in a `FutureTask`; a decorator's error handling **is not** where all `submit` exceptions are guaranteed to be observed. The goal here is solely to carry **one correlation ID** across threads and restore cleanly, without accessing the request inside the worker.

**Never** store `RequestContextHolder.currentRequestAttributes()` in a decorator and attach it to every task to "easily grab headers". Doing so can keep request object graphs past lifecycle.

## 12. Spring Security: Actor ID Differs From SecurityContext

Spring Security typically uses `SecurityContextHolder` with thread-bound context. A spawned worker **does not** automatically see the servlet thread's authentication.

If a job only needs an actor identifier for auditing and accessing policy-controlled resources, extract the **verified actor ID** at the request boundary and let the worker check permissions per business rules. Never put arbitrary bearer tokens or principal objects into long-lived queues.

If executing within a specific security context is truly needed, Spring Security provides wrappers such as `DelegatingSecurityContextRunnable`, `DelegatingSecurityContextExecutor`, and `DelegatingSecurityContextAsyncTaskExecutor`. They set/clear security context for the callback scope per contract, yet:

- They do not keep `HttpServletRequest` valid after completion.
- They do not exempt tasks from token expiry/revocation and privilege changes over time.
- You should not snapshot/share a mutable `SecurityContext` across multiple tasks and mutate it from multiple threads.
- You should not use context propagation as "copy the entire request" for long-running background jobs.
- For jobs surviving restarts, handle security with an internal service identity and appropriate authorization policies rather than relying on an old HTTP request's in-memory thread context.

Security wrappers are tools for **task-scoped execution context**, not a license to ignore request lifecycles.

## 13. File Uploads, Request Bodies, and Streams: Highly Error-Prone Cases

### 13.1. Do Not Pass ServletInputStream Outside the Request

~~~java
InputStream stream = request.getInputStream();

executor.execute(() -> parseDocument(stream));
~~~

**Unsafe snippet** if the stream still depends on the Servlet request or is closed by container/request processing before the worker reads it. The stream is also not guaranteed to be thread-safe, and a failing worker may fail to close resources promptly.

### 13.2. MultipartFile Is Not Automatically Durable Data Either

In Spring MVC, `MultipartFile` can reference temporary data managed by multipart processing. Do not enqueue `MultipartFile` or `getInputStream()` to read minutes after the response, as temporary data may be cleaned up with the request lifecycle.

For large files needing background processing, an example sound design:

~~~text
HTTP multipart request
      |
      +-- Authenticate/validate content type, size, quota
      +-- Save stream to durable object storage or staging area
      +-- Commit metadata: fileId, ownerId, size, checksum
      +-- Enqueue fileId + jobId (atomic/outbox if needed)
      |
      v
Response 202 Accepted (+ jobId)

Background worker:
      |
      +-- Load data by fileId from storage
      +-- Verify permissions/quota and integrity
      +-- Process, update status
      +-- Clean up staging data per retention policy
~~~

There is no need to copy the entire file into a `byte[]` in RAM and call it a snapshot. For uploads needing durability, passing a **reference to a persisted file with a retention contract** is safer and more efficient.

### 13.3. Spring MVC Example: Stage Then Dispatch Job

~~~java
@PostMapping(path = "/imports", consumes = "multipart/form-data")
public ResponseEntity<JobAccepted> upload(
        @RequestParam("file") MultipartFile file,
        Principal principal) throws IOException {

    String ownerId = principal.getName();
    String objectKey = storage.saveValidated(file.getInputStream(),
                                             file.getSize(), ownerId);
    String jobId = jobs.enqueueImport(ownerId, objectKey);

    return ResponseEntity.accepted()
            .body(new JobAccepted(jobId));
}
~~~

This is a **Spring MVC snippet**: `storage` and `jobs` are application beans to implement; `JobAccepted` is a DTO; imports are needed for `MultipartFile`, `Principal`, `IOException`, `ResponseEntity`. In production, enforce size limits, validate MIME/format independently of the client, clean up streams, and handle atomicity between save and enqueue. **Ensure `saveValidated` has actually flushed data to stable storage before accepting the job.** If the operation fails, do not return a false 202.

If object storage and the DB queue do not share a transaction, use job state/idempotency/outbox or compensation/cleanup to avoid jobs pointing to nonexistent files or orphaned files.

## 14. Timeouts, Cancellation, and Work Continuing After the HTTP Response

A task may keep running when:

- The client closes the connection.
- Spring MVC async request times out.
- The controller returned 202 and already ended the response.
- Downstream is slower than the HTTP deadline.
- The worker is already in the queue at context shutdown.
- A frontend retry creates a second logical request.

In every case, **the request object must not become durable background data**. Design the **job** lifecycle separately from the **HTTP request** lifecycle.

### When Returning CompletableFuture to Spring MVC

~~~java
@GetMapping("/reports/{id}")
public CompletableFuture<String> report(@PathVariable String id) {
    String reportId = validateId(id);
    return reportService.generateAsync(reportId);
}
~~~

This is a **Spring MVC snippet**; a service and validator are needed. The framework can hold the async HTTP request open until the future completes/times out/is handled per contract. The worker still uses only `reportId`, never `HttpServletRequest`.

### When Returning 202 and Running a Background Job

If the system has a durable job queue:

~~~text
POST /exports
    |
    +-- validate payload, identity
    +-- persist job(input snapshot)
    +-- return 202 + jobId
                 |
                 v
            background worker
                 |
                 +-- status=RUNNING/SUCCEEDED/FAILED
                 +-- GET /jobs/{jobId} to track
~~~

Here 202 usually only means **the request was accepted for processing**, not that the work succeeded. If you only call `@Async void` and return 202 without persisting job state/queue, an application crash can lose the work.

### On Cancellation

Cancelling a `CompletableFuture` does not mean the underlying network/DB action stops immediately or rolls back side effects. For tasks in an executor, actively tie cancellation/deadlines to the job and active resources via appropriate APIs. Cleanup runs in the task's `finally` or appropriate lifecycle callback, never trying to "amend the response" using an old `HttpServletResponse`.

## 15. Request-Scoped Beans: An Easily Overlooked Angle

~~~java
@Component
@RequestScope
public class RequestMetadata {
    private final String requestId;
    // ...
}
~~~

This is an **illustrative snippet**, not standalone. A `@RequestScope` bean has a lifecycle bound to a single HTTP request in a web-aware `ApplicationContext`. When worker code tries to access a request-scoped proxy outside the active scope, it can fail with no active request scope, such as a `ScopeNotActiveException` or an underlying root exception depending on configuration.

You also should not pass an entire request-scoped bean as an argument to a job running after the response. That bean may hold the request, body, or temporary resources in its fields.

**Do:** read `requestMetadata.getRequestId()` while the request scope is still valid, copy the `String` result into a DTO, and pass the DTO to the worker. If the bean holds mutable objects, establish deep-copy and validation boundaries.

## 16. Distinguishing Data, Context, and Access Rights

Three things often mixed together:

1. **Business data:** document ID, order ID, amount, validated options. Needed for the worker to do its job. Belongs in an immutable DTO or durable job payload.
2. **Observability info:** trace ID, correlation ID, locale code, operation ID. A small permitted subset can travel across threads or task decorators; clean up after each task.
3. **Permissions/security context:** authentication tokens, sessions, security principals, tenant policies, request-specific authorities. Do not blindly copy into long-lived jobs; separate security contracts, expiry/current permissions, and auditing are needed.

"Snapshot all headers just to be safe" is an anti-pattern: it copies cookies, bearer tokens, unverified proxy headers, and unnecessary metadata. A small record is only safe if **the values inside it have been validated and remain valid for the job's lifetime**.

## 17. Retries and Closed Requests

A task detached from a request may be retried minutes later. If it carries the old request:

~~~java
scheduler.schedule(
        () -> callPartner(request.getHeader("Authorization")),
        5, TimeUnit.MINUTES);
~~~

This is a **counter-example snippet**. After 5 minutes, the request's lifecycle has ended; the token may have expired; holding the Authorization header in the callback retains secrets. Do not fix this by wrapping the request in `Supplier<HttpServletRequest>` — the supplier can still retain the reference or return invalid context.

**Better design**:

- Define a **logical operation ID** and permitted scalar parameters.
- Persist the job payload durably if work must survive restarts.
- At execution/retry time, use an appropriate service credential/authorization or refresh tokens via a secure mechanism, rather than pulling tokens from an old request.
- Use the same idempotency key across attempts of a logical operation if downstream has side effects.
- Once a job exceeds TTL/permissions, stop and mark a clear status.

### When You Need Retrospective HTTP Metadata

If you need to audit request paths, client IDs, or idempotency keys, normalize and log/emit events **inside the request boundary**, rather than retaining raw `HttpServletRequest` "to inspect later". Auditing needs retention/access controls, not container objects living in RAM.

## 18. Reducing Memory Retention Risk

Even a bounded queue can hold large memory if inputs are heavy. Combined measures:

1. **Small DTO:** only required IDs/scalars, never bodies/sessions/requests.
2. **Bounded executor:** cap workers/queues and set clear overload policies.
3. **Timeouts/deadlines:** never allow futures/tasks to pend forever.
4. **Job ownership:** do not let static registries keep completed Futures indefinitely without cleanup.
5. **Explicit cleanup:** streams, temp files, storage leases, context restoration.
6. **Metrics:** queue depth, wait time, task age, payload size, heap old-generation, retained objects.
7. **Heap analysis:** use heap dumps/profilers in safe environments to trace GC root paths to `HttpServletRequest`/`ServletRequestAttributes` when suspected.
8. **Data minimization:** keep bearer tokens/cookies/bodies out of background queues; apply retention/access controls to job payloads.

You do not need to prove a request was GC'd to confirm code is right; more important is **having no structurally wrong reference paths**. `System.gc()` and `WeakReference.get()==null` are unreliable assertions in unit tests because GC has no mandatory schedule.

## 19. Testing and QA in Projects

### 19.1. Test That the Snapshot Does Not Depend on the Request Object

JUnit 5 snippet:

~~~java
JobInput input = new JobInput(
        "job-1", "actor-2", "tenant-3", "corr-4", "doc-5");

assertEquals("tenant-3", input.tenantId());
assertEquals("doc-5", input.documentId());
~~~

This is a **snippet**, requiring the `JobInput` record from section 6 and JUnit 5 imports. The goal is verifying typed, immutable data and explicit property copying. Add tests for validation rejecting empty, overly long, or malformed values per policy; the sample record only checks null and does not replace validators.

### 19.2. Test Zero Request Access After Lifecycle Completion

`RequestLifetimeDemo` in section 7 uses a fake request with an active flag and `CountDownLatch`. In service unit tests, use a fake/spy request that throws if called after the handler method finishes; assert the service receives only a DTO. Never use `Thread.sleep(1000)` and assume the worker definitely ran after the response.

### 19.3. Test Real Spring MVC Async

Use Spring MVC tests or container integration tests to verify:

- The controller builds the snapshot **before** returning.
- `@Async` is triggered through the proxy (no self-invocation).
- Controllers returning `CompletableFuture`/`DeferredResult` are managed by the framework; errors/timeouts map accurately.
- No worker code calls `RequestContextHolder.currentRequestAttributes()` or `@RequestScope` beans after the response completes.
- Once the async request finishes, no references remain in custom schedulers/registries.
- For file uploads, the worker receives a storage key; multipart temp files are used only within the valid request lifecycle.
- When tasks are rejected or context shuts down, job status is not lost and no false "success" is returned.

### 19.4. Test Against Cross-Task Context Leaks

Use **one pooled worker** sequentially running two tasks with different correlation IDs. The first task sets `traceId="A"` and cleans up; the second task must not see A if given no context. Check `finally` in decorators/MDC wrappers even when tasks throw exceptions and when cancelled. Never use thread inheritance to "patch" leaks.

### 19.5. Test Footprint/Retained References

You can profile under load with a bounded queue, measuring heap retained size and class histograms before/after a burst of requests. Do not use `WeakReference` + forced GC as pass/fail criteria; instead enforce code review/type boundaries ("job payloads contain no ServletRequest/ServletResponse/RequestAttributes/MultipartFile/InputStream/Session") alongside functional tests.

### 19.6. Test Authorization and Data Security

- A client spoofing `X-Tenant-Id` must not be able to select another tenant in the snapshot.
- Inputs containing bearer tokens/cookies must not be copied into job payloads/logs/traces.
- Long-running or retried jobs must apply authorization policies appropriate at execution time.
- Users must not be able to read another user's job results merely by guessing job IDs.
- Storage keys must not expose data if accessed directly; use internal ACLs or short-lived signed URLs per contract.

## 20. Common Misconceptions

**1. "Controller return means the Servlet request always ends immediately."** False under managed Servlet async; it can stay open until future/async completion.

**2. "If `@Async` is called, the container automatically keeps `HttpServletRequest` alive until the task finishes."** False. `@Async` and Servlet async requests are two separate mechanisms.

**3. "Keeping the request only costs one pointer."** False regarding retained object graphs: one pointer can retain many attributes, wrappers, or data.

**4. "Having a reference means the request is still API-valid."** False. GC reachability and lifecycle validity are two different properties.

**5. "Seeing no exception when reading the request on a worker means the code is safe."** False. It may be a race or the container simply hadn't recycled it during that test run.

**6. "Copying `ServletRequestAttributes` to a thread counts as a snapshot."** False. It typically holds request/response and lifecycle-bound attributes.

**7. "Records are always deeply immutable."** False. A record with a List of mutable elements or `byte[]` still has mutable data.

**8. "Passing raw `Principal` or `Authentication` is always safe for a 1-hour job."** No. You must account for credentials, changing permissions, token expiry, sensitivity, and security contracts.

**9. "`RequestContextHolder` automatically works on every `@Async` worker."** False. ThreadLocals usually do not move across executor threads on their own.

**10. "Enabling `setThreadContextInheritable(true)` is a good solution for pools."** False. Spring warns that inheriting context into newly created pooled threads can leak context across other work.

**11. "`TaskDecorator` copying all contexts will not cause retention."** False if contexts contain `RequestAttributes` or heavy tokens/objects.

**12. "Keeping `MultipartFile` to process after the response is safe."** Not by default. Multipart storage and streams may be cleaned up with the request.

**13. "Just copying the body to `byte[]` is enough."** Insufficient. If bodies are large, a queue holding thousands of copies can OOM; use staging/object storage.

**14. "Snapshotting correlation ID means the user is authenticated."** False. Correlation IDs only serve observability; auth/tenant must come from trusted sources.

**15. "Thread pools only hold running tasks, not queued ones."** False. Pending Runnables/Callables still hold their closures and attached data.

**16. "Request-scoped proxies work on any worker after HTTP completion."** False. Proxies do not extend request scope.

**17. "Returning 202 guarantees the job already ran successfully."** False. 202 only states the request was accepted for processing per contract; durable job status is needed if business requires it.

**18. "Cancelling `CompletableFuture` cancels the underlying I/O or rolls back side effects."** False. Cancelling a future does not replace cancellation of underlying resources and business logic.

**19. "A `WeakReference` test is enough to prove zero leaks."** False: GC is nondeterministic; checking ownership and structural retained references is far more reliable.

**20. "Clean up MDC only when the task succeeds."** False. `finally` is mandatory to prevent contamination when workers are reused.

## 21. Self-Check Questions

**Question 1:** Is `@Async public void export(HttpServletRequest request)` safe because Spring made it async?

**Answer:** No. `@Async` only dispatches the method. The request may have ended its lifecycle when the worker reads it. Extract an immutable `ExportInput` in the controller and pass that object.

**Question 2:** A Spring MVC controller returns `CompletableFuture`. Does the request definitely expire the instant the method returns?

**Answer:** No. Spring MVC has Servlet async support, so the logical request may remain open until async completion. Yet that is still no reason to pass raw requests to workers outside framework control.

**Question 3:** A task finished, yet a static map still holds a `FutureTask` referencing the request. Can the heap still retain the request?

**Answer:** Possibly, if the FutureTask/callback still has a strong reference path to related objects. Depending on implementation and cleanup timing, the retention graph must be checked; the fix is not capturing requests and cleaning up registries.

**Question 4:** Is `record Input(byte[] raw)` completely immutable?

**Answer:** No. The record only fixes the `raw` reference, while array elements can be mutated. Defensive copying is needed if the raw bytes are truly required along with size limits; better yet, use a storage key for large payloads.

**Question 5:** Should you pass entire `ServletRequestAttributes` to another thread to call `RequestContextHolder`?

**Answer:** Not as a general solution for jobs running after the response. Attributes can hold raw requests and are valid only during the request lifecycle; choose small snapshots or context propagation managed under clear lifetimes.

**Question 6:** A 200 MiB multipart file is processed 10 minutes after the response. Is enqueuing `MultipartFile` appropriate?

**Answer:** No. Persist the data safely to durable storage within the request boundary, and enqueue only the storage key and job ID.

**Question 7:** Why is a GC test unnecessary to prove input safety?

**Answer:** The issue is dependency/lifetime ownership: DTOs do not retain requests, workers do not access context post-completion, and queues are bounded. GC timing is nondeterministic, so `System.gc`/`WeakReference` cannot provide reliable pass guarantees.

**Question 8:** Should a worker use the client's old bearer token to call downstream an hour later?

**Answer:** Not by default. You must design credentials/delegation with expiry/revocation/authorization and secure storage; better to use a service identity alongside a contract-audited business actor ID.

**Question 9:** An executor uses `InheritableThreadLocal` to pass tenant from request threads to pooled threads; what is the risk?

**Answer:** A pooled thread spawned during one request can retain the old tenant/context and serve other tasks afterward; Spring warns against this exact case. Use per-task propagation and strict cleanup, not copying the entire request.

**Question 10:** Returning 202 right after `@Async void` accepts a task, then the process crashes before the task runs. Why can the user not know the status?

**Answer:** The work existed only in non-durable RAM/queues without a job store. If delivery guarantees are needed, persist job intent/status durably before returning accepted.

## 22. Code Review / Implementation Checklist

- [ ] Do not pass `HttpServletRequest`, `HttpServletResponse`, `ServletRequestAttributes`, `HttpSession`, or request-scoped proxies into background jobs.
- [ ] Do not capture requests via lambdas/anonymous classes/`this`/callbacks, schedulers, static caches, or queues.
- [ ] Snapshots contain only necessary, validated/authorized fields, free of raw headers/cookies/bearer tokens.
- [ ] For records/DTOs with collections/mutable values, copy or choose appropriate immutable representations.
- [ ] Do not retain `MultipartFile`/`ServletInputStream` past lifecycle; large files use storage object keys with proper retention/ACLs.
- [ ] Understand the difference between controller return, Servlet async completion, and fire-and-forget `@Async`.
- [ ] Spring `@EnableAsync` and proxies are properly configured; avoid self-invocation pitfalls.
- [ ] `ThreadPoolTaskExecutor` has queue/worker caps, timeouts, rejection handling, and shutdown.
- [ ] Context/trace propagation carries only needed data, cleaning up `ThreadLocal/MDC` in `finally`.
- [ ] Do not enable `setThreadContextInheritable(true)` for reusable pools.
- [ ] Actor/tenant permissions are verified without trusting unverified headers; long-lived jobs have dedicated security policies.
- [ ] Deadlines/cancellation are present; old response/request objects are never used to complete detached jobs.
- [ ] For long-lived jobs or crash-retryable work, persist payloads/intent/status durably with idempotency.
- [ ] Metrics cover queue depth, task age, retained heap, async errors, and job statuses.
- [ ] Tests cover fake/latch lifecycles, async MVC integration, cross-task MDC, file staging, and tenant spoofing.
- [ ] Do not use `System.gc()`/`WeakReference` as mandatory pass criteria for code correctness.

## 23. Conclusion

**Not retaining the entire request object after the request completes** is a principle of **lifecycle ownership, concurrency correctness, security, and memory retention**.

At the request boundary, authenticate, validate inputs, extract a **minimal immutable snapshot**, and pass that snapshot to the executor or persistent job queue. Workers must use the snapshot and dependencies independent of the Servlet request; never re-read request attributes, raw headers, sessions, streams, or responses past lifecycle.

Spring MVC supports valid Servlet async processing, so **controller return does not always mean the request has ended**. Even so, `@Async` or `CompletableFuture` alone does not permit retaining requests indefinitely. For context propagation, transfer only necessary values and clean up per task. For long-running jobs, pass **job IDs/storage keys** and manage durable state instead of holding container objects in RAM.

## References

- Jakarta Servlet specification — **Lifetime of the Request Object** and asynchronous processing: https://jakarta.ee/specifications/servlet/6.1/jakarta-servlet-spec-6.1
- Spring MVC Reference — Asynchronous Requests: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-async.html
- Spring MVC Reference — Controller Return Values (CompletionStage/CompletableFuture): https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/return-types.html
- Spring Framework Reference — Bean Scopes (`request` scope): https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html
- Spring Framework — `RequestContextHolder` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/web/context/request/RequestContextHolder.html
- Spring Framework — `RequestContextFilter` Javadoc (InheritableThreadLocal warning): https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/web/filter/RequestContextFilter.html
- Spring Framework — `ContextPropagatingTaskDecorator` (Spring 6.1+): https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/core/task/support/ContextPropagatingTaskDecorator.html
- Spring Framework Reference — Task Execution / @Async: https://docs.spring.io/spring-framework/reference/integration/scheduling.html
- Spring Security Reference — Concurrency Support: https://docs.spring.io/spring-security/reference/servlet/integrations/concurrency.html
- Java SE 17 — `CompletableFuture`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html
- Spring Framework Reference — Multipart Form Data: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/multipart-forms.html
