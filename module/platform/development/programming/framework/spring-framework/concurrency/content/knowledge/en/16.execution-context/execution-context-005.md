# Propagating Request Correlation IDs and Logging Context in Spring Framework

When an HTTP request passes through a controller and is handed off to `@Async`, `ThreadPoolTaskExecutor`, or `CompletableFuture`, the request *correlation ID* is frequently lost from log lines on the worker thread. The cause is not Spring "dropping" a normal parameter, but rather that many logging libraries store the **Mapped Diagnostic Context (MDC)** per **thread**. The HTTP-handling thread and the thread pulling a task from a pool are not necessarily the same. Moreover, thread pools **reuse workers**, so without proper context cleanup, a request can be mistakenly tagged with the previous request's ID.

The goal of this lesson in the **Execution Context** group of the **Spring Framework – concurrency** module is to establish how to propagate correlation IDs and logging context across asynchronous boundaries **at the right time, with the right scope, and with cleanup**, while distinguishing them from distributed tracing and security context. These rules help trace a request through controllers, executors, workers, and downstream services without mixing logs from multiple clients.

> Core principle: **a correlation ID is data identifying a processing flow; MDC is merely a vehicle for attaching that data to the current thread's logs.** If a value must cross into another task or another system, there must be a dedicated propagation mechanism; you cannot rely on sharing the same JVM or the same request.

## 1. What Problem Does a Correlation ID Solve?

A report-generation request may go through multiple steps:

```text
                         X-Correlation-ID: req-8f2
                                      |
                                      v
Client ----HTTP----> Spring MVC Filter ----> Controller / Service
                           |                       |
                           | MDC[corrId=req-8f2]   | submit
                           v                       v
                     Log request thread     ThreadPoolTaskExecutor
                                                    |
                                       [queue] -> pooled worker
                                                    |
                                         MDC must be propagated
                                                    |
                                            Database / API
                                                    |
                                          outbound HTTP header
                                                    |
                                                    v
                                              Downstream service
```

If log lines carry the same `req-8f2` ID, the observability system can find all events belonging to the same request, even when steps execute across multiple threads or multiple services.

Illustrative log example:

```text
INFO  [http-nio-8080-exec-2] [corr=req-8f2] Received report request
INFO  [report-1]            [corr=req-8f2] Started report generation
INFO  [report-1]            [corr=req-8f2] Stored report result
```

The thread names in the example are purely illustrative; actual threads, timestamps, and log ordering depend on the executor/scheduler.

**Without a correlation ID**, searching log lines solely by timestamp, endpoint, or worker name is error-prone when the application handles thousands of tasks in parallel. **Having a correlation ID but propagating it wrongly** is even more dangerous because logs from two requests can merge, misleading incident root-cause investigation.

### 1.1. Three Requirements of a Good Correlation ID

1. **Stable across the logical scope being traced.** Steps handling the same request/job should know the same ID or a clear parent-child relationship.
2. **Propagatable across boundaries.** HTTP headers, queue message metadata, job payloads, and task wrappers each have concrete mechanisms.
3. **Free of secrets or PII.** Avoid emails, tokens, card numbers, phone numbers, or sensitive business payloads as correlation IDs. The ID must have low collision risk and validation/length limits if accepted from clients.

A correlation ID is **not** proof of authentication/authorization; any user can send a forged HTTP header if a public system allows it. Use the ID to find logs, **never use it as a condition for granting permissions**.

## 2. Distinguishing Correlation ID, Request ID, Job ID, Trace ID, and Span ID

Systems use similar terms with different scopes. Do not force one variable into every role.

| Identifier | Typical Scope | What Is It Used For? |
| --- | --- | --- |
| **Request ID** | One HTTP request at one service/edge | Finding logs or errors tied to a specific request |
| **Correlation ID** | One business flow potentially spanning multiple steps | Grouping logs of related steps, potentially across async/brokers |
| **Job ID** | One tracked background task | Querying QUEUED/RUNNING/SUCCEEDED/FAILED status |
| **Trace ID** | One distributed trace | Linking spans according to tracing standards |
| **Span ID** | One step/operation within a trace | Identifying child operations, measuring latency/parent-child |
| **Idempotency key** | One logical request that may be retried | Preventing executing a business side effect twice |

For example, a client POSTs to generate a report with `X-Correlation-ID=req-8f2`. The server may create `jobId=job-92` and return HTTP 202. If the worker runs after the HTTP response has ended, the worker's logs can record both `correlationId=req-8f2` and `jobId=job-92`. Another client calling `GET /jobs/job-92` creates a **new request ID**, yet can still be linked to the same job.

**Distributed tracing** typically uses W3C Trace Context standards such as `traceparent` and `tracestate`; `traceId`/`spanId` have specific formats and semantics. A custom `X-Correlation-ID` header **does not replace** tracing instrumentation. If using Micrometer Tracing/OpenTelemetry, prioritize the tracing framework's propagation rules; you may additionally record correlation IDs when business needs require them.

## 3. What Is MDC? Why Is It Easily Lost When Switching Threads?

`org.slf4j.MDC` provides an API to set/read key-value pairs used in logging context:

```java
MDC.put("correlationId", "req-8f2");
String id = MDC.get("correlationId");
MDC.remove("correlationId");
MDC.clear();
```

This is a **fragment**, requiring the SLF4J API and a backend supporting MDC such as Logback in the project. MDC is not an API for persisting request state in a database; it holds context attached by the logging adapter to the current thread.

In the common SLF4J/Logback model, MDC uses thread-local context:

```text
Thread HTTP-A     MDC = { correlationId: req-A }
Thread HTTP-B     MDC = { correlationId: req-B }
Thread worker-1   MDC = { }          // Has not automatically received req-A
Thread worker-2   MDC = { }          // Has not automatically received req-B
```

From this come two opposite bugs:

- **Not propagating:** worker logs lack `correlationId`, even though the caller has it.
- **Not cleaning up:** worker retains MDC from the previous task; next time it can mistakenly tag `req-B` task logs with `req-A`.

Distinguish clearly:

- **ThreadLocal:** mechanism storing data per thread; does not automatically attach data to `Runnable`/`Callable` submitted through an executor.
- **MDC:** a logging abstraction API backed by a concrete provider. With Logback, MDC is typically thread-local bound, hence requiring copying/restoration across thread switches.
- **InheritableThreadLocal:** can pass a snapshot when *creating a child thread* in certain scenarios, but **is unsuitable as a default solution for reusable thread pools**. Workers are often created before requests arrive, and data can leak across requests.
- **Reactor Context:** context following a reactive subscription flow; not identical to `ThreadLocal`. WebFlux can switch threads, so a dedicated context propagation integration is required.

**No implicit guarantee:** a `CompletableFuture` object does not automatically carry the caller thread's entire MDC to all dependent callbacks.

## 4. Why Does ThreadPoolTaskExecutor Need Intentional Propagation?

Spring's `ThreadPoolTaskExecutor` manages a worker pool and queue. When a controller calls:

```java
executor.execute(() -> generateReport(reportId));
```

`execute` hands off a `Runnable` to the executor. A worker will run the task at a different time, likely on an existing thread. The controller's MDC sits on the request thread, **not automatically inside the worker**.

One solution is to **capture context at submit time** and **install that context when the worker starts running**. Finally, **restore the worker's prior context**, even if the task throws an exception:

```text
Request thread:  MDC[corr=req-8f2]
       |
       | submit
       v
TaskDecorator captures snapshot {corr=req-8f2}
       |
       | executor queue
       v
Worker thread:
    previous = snapshot worker's existing MDC
    try:
        install {corr=req-8f2}
        run business task
    finally:
        restore previous
```

With `ThreadPoolTaskExecutor`, Spring provides `TaskDecorator` to wrap the `Runnable` received by the executor. This is the right place to implement a centralized context capture/restore policy for tasks passing through that executor bean.

### 4.1. Why Capture at Submit Time, Not at Run Time?

If you only call `MDC.get("correlationId")` inside the worker, you are reading the **worker's context**, which either lacks the request ID or holds old data. The snapshot must be taken from where the right context still resides: **the thread submitting the task**.

Wrong example:

```java
executor.execute(() -> {
    String id = MDC.get("correlationId"); // May be null or stale
    log.info("job {}", id);
});
```

Conceptually right example:

```java
String capturedId = MDC.get("correlationId");
executor.execute(() -> {
    String previous = MDC.get("correlationId");
    try {
        if (capturedId == null) MDC.remove("correlationId");
        else MDC.put("correlationId", capturedId);
        doWork();
    } finally {
        if (previous == null) MDC.remove("correlationId");
        else MDC.put("correlationId", previous);
    }
});
```

Both snippets are **fragments**, requiring an executor/logger/`doWork` and appropriate imports. In a project with many tasks, you should **not manually copy** this wrapper snippet into every call site; a clearly tested `TaskDecorator` is far easier to maintain.

### 4.2. Why Restore Instead of Just Clearing?

If before the task began, the worker already held a valid context set by an outer wrapper, calling `MDC.clear()` after the task can wipe out the outer scope's context. **Restoring previous** handles both cases:

- Before the task there was no MDC → clears back to empty.
- Before the task there was MDC → restores that exact context.

This is especially helpful when there are **nested decorators**, instrumentation, or another executor wrapper. A task must never write context data and forget cleanup on exception.

## 5. Runnable Java 17: Proving ThreadLocal Does Not Auto-Propagate and Requires Cleanup

This pure JDK example has no Spring/SLF4J dependencies. It uses `ThreadLocal<String>` to simulate a `correlationId` field in Logback's MDC. A single-thread executor shows that the caller's value **does not automatically appear** on the worker. Then a **capture → install → restore** wrapper passes the exact ID and cleans up after the task finishes.

Save the program in **ContextBoundaryDemo.java**:

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class ContextBoundaryDemo {
    private static final ThreadLocal<String> REQUEST_ID =
            new ThreadLocal<>();

    private static String current() {
        String id = REQUEST_ID.get();
        return id == null ? "absent" : id;
    }

    private static void assign(String value) {
        if (value == null) {
            REQUEST_ID.remove();
        } else {
            REQUEST_ID.set(value);
        }
    }

    private static Runnable capture(Runnable action) {
        // This line runs on the SUBMIT thread, before any worker.
        String captured = REQUEST_ID.get();

        return () -> {
            String previous = REQUEST_ID.get();
            try {
                assign(captured);
                action.run();
            } finally {
                assign(previous);
            }
        };
    }

    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor(
                r -> new Thread(r, "pooled-worker"));

        try {
            REQUEST_ID.set("req-123");

            // No propagation: worker does not see caller's ThreadLocal.
            pool.submit(() ->
                    System.out.println("without: " + current())).get();

            // Wrapper captures req-123 on submit, then sets it on worker.
            pool.submit(capture(() ->
                    System.out.println("with: " + current()))).get();

            // Worker does not leak req-123 to the next task.
            pool.submit(() ->
                    System.out.println("after: " + current())).get();

            System.out.println("caller: " + current());
        } finally {
            REQUEST_ID.remove();
            pool.shutdownNow();
        }
    }
}
```

Compile and run with **JDK 17+**:

```bash
javac ContextBoundaryDemo.java
java ContextBoundaryDemo
```

**Deterministic program stdout:**

```text
without: absent
with: req-123
after: absent
caller: req-123
```

Analysis:

1. `REQUEST_ID.set("req-123")` only sets the value on the main thread. Standard `ThreadLocal` does not inherit values to workers, so the first line is `without: absent`.
2. `capture(...)` runs **on the main thread when creating the wrapper**, holding the `req-123` snapshot before handing off to the pool.
3. The wrapper sets the ID on the worker, runs the action, and `finally` **restores `previous`**. Because the worker had no prior value, restoring performs `remove()`.
4. The next task reuses the single-thread pool and sees `after: absent`, proving the wrapper left no context behind.
5. The main thread still sees `caller: req-123` until `finally` cleans up main's value.
6. Each `Future.get()` waits for the previous task to complete, so output line order does not depend on scheduling luck. No `Thread.sleep` is needed to guess when a worker finishes.

**Limitation:** the demo illustrates `ThreadLocal`, **not the SLF4J MDC implementation**. In Spring/Logback, instead of a single `String`, you typically capture the full `Map<String,String>` via `MDC.getCopyOfContextMap()`. You must handle a `null` snapshot (no map) differently from a populated map and properly restore the worker's context.

## 6. Spring TaskDecorator to Copy and Restore MDC

A `TaskDecorator` implements the snapshot mechanism centrally:

```java
import java.util.Map;

import org.slf4j.MDC;
import org.springframework.core.task.TaskDecorator;

public final class MdcTaskDecorator implements TaskDecorator {
    @Override
    public Runnable decorate(Runnable task) {
        // Capture on submit thread, not inside worker.
        Map<String, String> captured = MDC.getCopyOfContextMap();

        return () -> {
            // There may be a valid outer scope context.
            Map<String, String> previous = MDC.getCopyOfContextMap();

            try {
                if (captured == null) {
                    MDC.clear();
                } else {
                    MDC.setContextMap(captured);
                }

                task.run();
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
```

The class above compiles in a project with **Spring Core and an SLF4J MDC backend**. It is also used in the complete application later on (the Spring Boot section uses a class with the same idea).

### Why Do These Details Matter?

- `MDC.getCopyOfContextMap()` takes a **snapshot**, avoiding passing a shared map where two threads mutate the same object.
- `decorate(...)` is called when the executor receives the `Runnable` to build the wrapper; in this case it captures MDC on the submitting thread. Capture timing must occur **before** the request filter clears the context.
- When the worker runs, the code captures `previous` before overwriting. After the task, `finally` restores the exact prior state. If the task throws an error, `finally` still runs.
- `captured == null` means no map exists; on the worker we must **clear** to avoid logging with an old ID.
- `MDC.setContextMap(...)` takes a map of string keys/values; do not put mutable business objects or secrets into MDC.

For ultra-short tasks at very high frequency, context capture/restore has overhead. Measure in special cases, yet **never skip cleanup to "optimize"**. You can propagate only the necessary keys instead of the entire map when security and performance requirements are strict.

### 6.1. Do Not Capture Once When Creating the Executor Bean

A subtle bug:

```java
Map<String, String> startupMdc = MDC.getCopyOfContextMap();

executor.setTaskDecorator(task -> () -> {
    MDC.setContextMap(startupMdc);
    task.run();
});
```

This is a **counter-example, do not use in production**; `setContextMap` does not even accept `null` safely across all backends. `startupMdc` is captured **once at startup**, usually empty, rather than on each task submission. It also lacks restoration in `finally`.

**Correct:** place `MDC.getCopyOfContextMap()` **inside `TaskDecorator.decorate(...)`**, and restore previous inside the wrapper. Never store a request's ID in a singleton field of an executor or service.

### 6.2. TaskDecorator Only Covers Tasks Going Through That Exact Executor

If a method uses `@Async("workExecutor")`, `workExecutor`'s decorator can apply. However, if code calls:

```java
CompletableFuture.supplyAsync(() -> compute());
```

**without passing an executor**, the JDK typically uses `ForkJoinPool.commonPool()` (with its own fallback rules). That pool **does not automatically go through Spring `workExecutor`'s `TaskDecorator`**.

If a continuation needs to run through a propagating executor:

```java
CompletableFuture.supplyAsync(() -> compute(), workExecutor);
```

This is a fragment, requiring `compute` and `workExecutor` to be declared. Meanwhile, `whenComplete`/`thenApply` **without the Async suffix** may run on the completing thread or the registration thread depending on timing. Do not rely on "having once passed through an executor" to assume all later callbacks will have MDC. When explicit guarantees are needed, pass the correlation ID as data, or use a context-aware executor at **every critical scheduling point**.

## 7. Runnable Spring Boot 3.x: Filter + Executor + @Async + MDC

The following example demonstrates end-to-end in **Spring Boot 3.x / Spring Framework 6.x / Java 17+**, with the `spring-boot-starter-web` dependency (including Spring MVC and standard logging). It has four components:

1. `OncePerRequestFilter` extracts or generates `X-Correlation-ID`, validates it, and sets it in MDC on the request thread.
2. `ThreadPoolTaskExecutor` with a `TaskDecorator` captures/restores MDC for the worker.
3. `WorkService` runs an `@Async("workExecutor")` method; logs on the worker and returns the ID actually observed.
4. `WorkController` calls the separate service bean through a proxy, using the correlation ID from the request to verify the result.

Put **all the code below** into **src/main/java/com/example/demo/CorrelationApplication.java**:

```java
package com.example.demo;

import java.io.IOException;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ThreadPoolExecutor;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.core.task.TaskDecorator;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.stereotype.Component;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.filter.OncePerRequestFilter;

@SpringBootApplication
@EnableAsync
public class CorrelationApplication {
    public static void main(String[] args) {
        SpringApplication.run(CorrelationApplication.class, args);
    }

    @Bean("workExecutor")
    ThreadPoolTaskExecutor workExecutor() {
        ThreadPoolTaskExecutor pool = new ThreadPoolTaskExecutor();
        pool.setCorePoolSize(2);
        pool.setMaxPoolSize(4);
        pool.setQueueCapacity(20);
        pool.setThreadNamePrefix("work-");
        pool.setRejectedExecutionHandler(
                new ThreadPoolExecutor.AbortPolicy());
        pool.setTaskDecorator(new MdcTaskDecorator());
        return pool; // Spring manages bean initialization and shutdown
    }
}

final class MdcTaskDecorator implements TaskDecorator {
    @Override
    public Runnable decorate(Runnable runnable) {
        Map<String, String> captured = MDC.getCopyOfContextMap();

        return () -> {
            Map<String, String> previous = MDC.getCopyOfContextMap();
            try {
                if (captured == null) MDC.clear();
                else MDC.setContextMap(captured);
                runnable.run();
            } finally {
                if (previous == null) MDC.clear();
                else MDC.setContextMap(previous);
            }
        };
    }
}

@Component
class CorrelationFilter extends OncePerRequestFilter {
    private static final String HEADER = "X-Correlation-ID";
    private static final String KEY = "correlationId";

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain) throws ServletException, IOException {
        String incoming = request.getHeader(HEADER);

        // Accept only short IDs without control/CRLF characters.
        String correlationId =
                incoming != null
                && incoming.matches("[A-Za-z0-9][A-Za-z0-9._-]{0,63}")
                ? incoming
                : UUID.randomUUID().toString();

        String previous = MDC.get(KEY);
        try {
            MDC.put(KEY, correlationId);
            response.setHeader(HEADER, correlationId);
            chain.doFilter(request, response);
        } finally {
            if (previous == null) MDC.remove(KEY);
            else MDC.put(KEY, previous);
        }
    }
}

record WorkResult(
        String jobId,
        String requestCorrelationId,
        String workerCorrelationId) {}

@Service
class WorkService {
    private static final Logger log =
            LoggerFactory.getLogger(WorkService.class);

    @Async("workExecutor")
    public CompletableFuture<WorkResult> process(
            String jobId, String requestCorrelationId) {
        String workerCorrelationId = MDC.get("correlationId");
        log.info("Processing job {}", jobId);

        WorkResult result = new WorkResult(
                jobId, requestCorrelationId, workerCorrelationId);
        return CompletableFuture.completedFuture(result);
    }
}

@RestController
class WorkController {
    private static final Logger log =
            LoggerFactory.getLogger(WorkController.class);
    private final WorkService service;

    WorkController(WorkService service) {
        this.service = service;
    }

    @GetMapping("/work/{id}")
    public CompletableFuture<WorkResult> process(
            @PathVariable String id) {
        String correlationId = MDC.get("correlationId");
        log.info("Accepted work {}", id);
        return service.process(id, correlationId);
    }
}
```

**Structural note:** placing all package-private classes in one file alongside the public `CorrelationApplication` class is valid in Java. The project needs Spring Boot 3.x, the default logging backend or equivalent, and the Jakarta Servlet HTTP stack. You cannot run `javac CorrelationApplication.java` without Spring dependencies.

Example run in a project with Gradle wrapper:

```bash
./gradlew bootRun
curl -i -H "X-Correlation-ID: req-demo-01" \
  http://localhost:8080/work/J7
```

On Windows PowerShell you can run `gradlew.bat bootRun` and then run `curl.exe` separately; the `\` line continuation in the shell example above is bash syntax, not PowerShell line-continuation syntax.

When the request is received and the worker completes, the **JSON response body** has values equivalent to:

```json
{
  "jobId": "J7",
  "requestCorrelationId": "req-demo-01",
  "workerCorrelationId": "req-demo-01"
}
```

**Why can we observe that?**

1. The filter accepts a valid ID and puts `MDC["correlationId"]` on the servlet thread.
2. The controller reads the ID from MDC and passes it **explicitly** as the `requestCorrelationId` parameter to the service.
3. The controller calls the separate `WorkService` bean; the `@Async` call is intercepted by the Spring proxy and dispatched to `workExecutor`.
4. `TaskDecorator.decorate(...)` captures the MDC snapshot **at the time the task is submitted**.
5. The worker runs the wrapper and sets MDC before invoking the actual method, so `MDC.get("correlationId")` inside `WorkService` is `req-demo-01`.
6. After the task finishes, the wrapper restores the worker's prior MDC, preventing leaks into the next task.
7. The filter restores the servlet thread's old value upon leaving the request processing scope.

Even though `WorkService.process` returns `CompletableFuture.completedFuture(...)` on the worker, **Spring MVC responds when the `CompletableFuture` returned from the controller completes**. This is a demo endpoint response, not a `202 Accepted` job protocol. The JSON is built from the **explicitly passed value and the worker-observed value**; it does not depend on which thread runs Spring MVC's serialization callback.

### 7.1. Showing Correlation ID in Logs With Logback

MDC is only useful when the log layout **reads the corresponding key**. In Spring Boot with Logback, you can configure a console log pattern, for example in `src/main/resources/application.properties`:

```properties
logging.pattern.console=%d{HH:mm:ss.SSS} %-5level [%thread] [corr=%X{correlationId}] %logger{36} - %msg%n
```

This is an illustrative configuration using the Logback pattern `%X{correlationId}`. Actual logs have varying timestamps/thread names, yet when the filter and decorator work properly, both request and worker can contain:

```text
[corr=req-demo-01] ... Accepted work J7
[corr=req-demo-01] ... Processing job J7
```

Do not predict exact thread names or absolute ordering of all logs in asynchronous processing. If using JSON structured logging, add a `correlationId` field from MDC via encoder configuration; **do not manually concatenate the ID in every log statement** if the backend already supports fields.

### 7.2. What If the Client Sends No Header?

The filter uses `UUID.randomUUID().toString()` to generate a new ID, puts it in MDC, and returns it in the `X-Correlation-ID` response header. The client can save that ID to provide when reporting errors. The specific value changes on every request and **cannot be treated as fixed stdout**.

If the client sends a value containing newlines, excessive length, or characters outside the regex, the filter replaces it with a server-generated UUID. This is a simple measure to prevent log injection and header abuse; in production you may also want to enforce gateway policies and organization ID standards.

### 7.3. Understand Servlet Async Dispatch Limitations

`OncePerRequestFilter` by default selects which dispatcher types to filter; Spring MVC's process of returning a `CompletableFuture` may involve an **async dispatch** after the initial filter scope has ended. The demo only needs the filter to set MDC **initially when the controller submits the task**, so `TaskDecorator` captures it in time.

Do not assume MDC will automatically be present at **every filter invocation, error dispatch, post-response framework log, or async dispatch thread**. If you need correlation IDs across all servlet async phases, design propagation/filtering for the appropriate dispatcher types/lifecycles, or use supported observability/context propagation integrations.

## 8. Executor Initialization and Selection in Spring

In the pattern above:

```java
@Bean("workExecutor")
ThreadPoolTaskExecutor workExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setTaskDecorator(new MdcTaskDecorator());
    return executor;
}
```

This is a **shortened fragment**; the full example also includes sizing and a rejection policy. `ThreadPoolTaskExecutor` is a Spring bean, so the container manages initialization and shutdown per lifecycle. `@Async("workExecutor")` selects the exact executor with that decorator.

Cases where MDC is not propagated:

- An `@Async` method selects a **different** executor bean without a decorator.
- Code calls `CompletableFuture.supplyAsync(fn)` without passing an executor and runs on the default JDK facility.
- Code calls `this.asyncMethod()` inside the same bean in proxy mode, thus **bypassing the Spring async proxy**.
- An external library spawns its own thread without using a propagation-equipped executor.
- A non-async `thenApply(...)` callback runs inline on a thread lacking MDC at completion time.
- A scheduler/message listener starts a task without having created a correlation ID for the root job/message.

You must understand the **actual call path** and **actual executor**. Do not blame `TaskDecorator` if the task never went through that executor.

### 8.1. When Does Rejection Happen?

`ThreadPoolTaskExecutor` has pool and queue limits. If using `AbortPolicy` and the executor is overloaded or shut down, submission may throw `TaskRejectedException`. A rejected task **does not run the worker wrapper**, yet the submitting request thread still has MDC, so logging in the catch block can include the correlation ID:

```java
try {
    workExecutor.execute(task);
} catch (TaskRejectedException ex) {
    log.warn("Executor rejected a task", ex);
    // Respond 503/429 or persist durable job per contract.
}
```

This is a fragment, assuming `log`, `task`, and `workExecutor` exist. Never use a silent discard handler and then promise that every task ran. Tracing rejections is crucial because worker logs will **not exist** for a task that was never accepted.

### 8.2. TaskDecorator and Future Exceptions

Spring notes that `TaskDecorator` may receive a wrapper `Runnable` rather than the original user-supplied task; for `submit` calls, the wrapper may be a `FutureTask` that hides exceptions. Therefore, do not treat `TaskDecorator` as a reliable place to **catch all business exceptions** via `catch (Throwable)` and log them. To observe errors, use Future/CompletableFuture callbacks, an appropriate `@Async` exception handler, or a job-level error handler.

**The decorator's responsibility is setting up/restoring context**, not becoming a handler for every business outcome.

## 9. Propagating Correlation ID Through a CompletableFuture Chain

Example:

```java
CompletableFuture<String> stage =
        CompletableFuture.supplyAsync(() -> fetchData(), workExecutor)
                .thenApply(this::transform);
```

`supplyAsync(..., workExecutor)` is scheduled on an executor with a decorator, yet `thenApply` **without the Async suffix** may run on the completing thread or the registering thread depending on timing. When a callback needs logging context, understand where it runs:

- If upstream has not completed yet, a non-async callback may run before upstream's worker wrapper restores MDC, thus observing the worker's context.
- If upstream already completed before the callback is registered, it may run inline on the caller thread; context depends on that caller.
- If the stage completes from another thread or after context restoration, the callback may not see the expected MDC.
- Use `thenApplyAsync(fn, workExecutor)` when you truly need dispatch through a context-propagating executor. **However, capture happens on the thread submitting the continuation**, so that thread must hold the context to propagate.

### Do Not Assume Upstream Propagation "Spreads" Automatically Forever

```java
CompletableFuture<String> next =
        upstream.thenApplyAsync(this::work, workExecutor);
```

This is a fragment. If `upstream` has not finished, scheduling the continuation may occur on the thread completing `upstream`. `TaskDecorator` captures **whatever MDC is on that scheduling thread**, not necessarily the original HTTP request's MDC. If `upstream` completes from a foreign executor carrying no context, merely passing `workExecutor` will not magically "revive" the ID.

When consistent correlation across many stages is required, there are clear choices:

1. Pass **correlation ID as data**: a `record Context(jobId, correlationId)` traveling with the payload, independent of threads.
2. Wrap the callback with a context snapshot **at a moment when the right ID is still known**, and restore when running.
3. Use a context-aware executor or officially supported context propagation mechanism, auditing every asynchronous boundary.
4. Avoid relying on callback timing/thread identity since `CompletableFuture` does not promise non-async stages run on a fixed thread.

### 9.1. Passing as Data When a Job Outlives the HTTP Request

An approach less dependent on MDC is defining:

```java
record JobContext(
        String jobId,
        String correlationId,
        String traceId) {}

record WorkItem(JobContext context, String payload) {}
```

This is a **Java 17 record fragment**. The worker receives `WorkItem`, puts `context.correlationId()` into MDC for **the job's processing scope**, and then cleans up. If the job is persisted in a database/broker, metadata can be stored/published with the job and recovered after restarts.

The advantage is that a job lasting several minutes need not hold onto an HTTP request object or servlet thread. **Do not store the entire security context, access token, or session inside a job just to have a correlation ID.**

## 10. Outside the JVM: Propagating Correlation Headers Across Other Services

`MDC.put(...)` only alters the current thread's logging context. It **does not automatically add headers** to outgoing HTTP requests and **does not automatically enter Kafka/RabbitMQ messages**.

Java 17 standard `HttpClient` example:

```java
String correlationId = MDC.get("correlationId");

HttpRequest request = HttpRequest.newBuilder()
        .uri(URI.create("https://service.example.test/data"))
        .header("X-Correlation-ID",
                correlationId == null ? "unknown" : correlationId)
        .GET()
        .build();
```

This is a **fragment**, requiring `java.net.URI`, `java.net.http.HttpRequest`, and SLF4J MDC. Using `"unknown"` is only for explanation; real systems should **generate a valid ID at ingress or job boundaries** instead of using a shared placeholder that merges logs across requests.

Better yet, integrate an outbound interceptor suited to your client, such as Spring `RestClient`/`WebClient`/`RestTemplate` or a library-provided HTTP client, and use a properly scoped **CorrelationContext** per request/job. For message brokers, put the correlation ID in **message headers/metadata** on publish and read it on consume.

```text
Service A:
  MDC[corr=req-8f2]  --> outgoing HTTP header / message header
                                       |
                                       v
Service B:
  ingress filter / listener reads corr=req-8f2
  validates value and chooses trust policy
  sets MDC for local scope
  runs work, propagates onward if needed
  finally restores/clears MDC
```

**Important:** service B should not treat a correlation ID as an authenticated identity; headers can be forged by any client. Trace/span context has its own propagation rules when using OpenTelemetry/Micrometer Tracing. Correlation IDs link logs; they do not replace a standard trace with parent/child spans.

### 10.1. With Kafka/RabbitMQ and Scheduled Jobs

- **Producer:** take the ID from request/job context and write it into message headers; do not assume MDC is serialized automatically.
- **Consumer:** validate/normalize the ID from the message, set it in MDC for the scope of processing one message, and **restore/clear in finally** so it does not leak to the next message.
- **Scheduled job:** has no HTTP header; generate a correlation ID per trigger/logical job and record it in metadata before submitting. If a scheduled run dispatches hundreds of tasks, decide whether they share a parent correlation ID or add child/job IDs.
- **Retry/redelivery:** keep the correlation ID stable for the same logical job if the goal is tracing the same workflow, while recording an `attempt` field to distinguish retries. Do not use a correlation ID as the sole idempotency key.
- **Distributed trace:** if broker/client instrumentation supports trace context, use standard propagation instead of generating random trace/span IDs yourself and assuming you have distributed tracing.

## 11. Micrometer Context Propagation, Tracing, and Reactor Context

In the modern Spring ecosystem, a system may use:

- **Micrometer Observation/Tracing** to create spans and traces, correlating logs with `traceId`/`spanId`.
- **Micrometer Context Propagation** to capture/restore certain contexts across thread/reactive boundaries via registered accessors.
- Spring's **`ContextPropagatingTaskDecorator`** to leverage context snapshots when dependencies and configuration are in place.
- **Reactor Context** to store data along a reactive chain rather than relying on an event-loop worker's `ThreadLocal`.

The key is not picking a magic class name, but understanding **which contexts are managed** and **where capture/restore points apply**. Do not assume enabling Micrometer tracing copies every custom MDC key you invented or the entire security context across every `CompletableFuture`/raw thread.

### 11.1. When Do You Need a Context Propagation Framework?

A simple `MdcTaskDecorator` may suffice for a Spring MVC app with a few explicit executors. When flows cross multiple boundary types — servlets, async tasks, reactor operators, broker listeners, tracing spans — a framework solution with standard accessors/observations is easier to maintain, provided the application tests propagation behavior in its actual library versions.

**Do not mix these up:**

- `traceId` and `spanId` are managed by the tracing system; do not arbitrarily overwrite them with `correlationId`.
- `MDC` is a logging display context, not a context propagation protocol.
- `SecurityContextHolder` has different policies; do not copy authentication into MDC.
- Reactor operators can switch threads per scheduler; `MDC.get(...)` does not automatically reflect Reactor Context in every callback.
- Logging itself may run on another thread when using an async appender; check your logging backend's MDC capture mechanism and test end-to-end.

Read documentation for your **actual Spring Framework/Spring Boot version** before combining propagation solutions to avoid double wrapping, lost context, or unnecessary overhead.

## 12. Security and Data Controls in Logging Context

A correlation ID looks harmless, yet it is still potentially client-controlled data. Several safety rules:

### 12.1. Validate Headers; Do Not Trust Arbitrary Strings

A header containing `\r`/`\n`, control characters, or a megabyte-long string can cause log injection, inflate log storage costs, or break JSON structure. Enforce limits on:

- Length (for example, max 64 characters).
- Allowed character set (for example, letters, digits, `-`, `_`, dots).
- Repeated header count.
- Policy when invalid: generate a fresh ID or reject the request per API contract.

Never use a request body, access token, or username as a correlation ID.

### 12.2. MDC Must Only Contain Data Needed for Tracing

Do not put passwords, authorization bearer tokens, cookies, payment card data, email contents, or sensitive personal data into MDC just to make debugging easier. Context is copied to workers/structured loggers and may be shipped to centralized log storage.

Include only values with clear scope and retention: `correlationId`, `jobId`, `component`, or a normalized request path if valid. If principal info is needed for authorization, use proper security mechanisms and evaluate propagation separately.

### 12.3. Cross-Tenant and ID Collisions

If accepting IDs directly from the internet, two users can both send `X-Correlation-ID=abc` to intentionally mix logs. You can:

- Generate a trusted ID **at the gateway** and prevent clients from arbitrarily overwriting it.
- Keep a server-generated ID alongside the external client-provided ID in **separate fields**, labeled by trust source.
- Never query sensitive data using only a correlation ID.
- Enforce formal tenant/authorization policies in status APIs; a correlation ID must not grant access to another user's logs or jobs.

If a system needs distributed tracing, follow sampling/trust/propagation policies at ingress rather than blindly trusting any external trace context.

## 13. Cleanup, Nested Scopes, and Context Leakage Risks

### 13.1. Worker Threads Are Reused Resources

Suppose a pool has one worker:

```text
Task A: MDC.put("correlationId", "req-A")
        run...
        // Forgot remove

Task B: does not set MDC
        log.info("Processing")
        => B's log may carry corr=req-A (WRONG)
```

A bug that only appears under real load can be hard to reproduce, because small tests creating new threads do not show reuse. Always use `finally`, even when a task times out, cooperatively cancels, or throws an exception.

### 13.2. Restore the Entire Map When Nested Contexts Exist

Suppose a worker already has context `{traceId=abc, component=outer}` from an outer wrapper. A decorator that only runs `MDC.remove("correlationId")` may leave behind new keys added by the task itself; a decorator that only runs `MDC.clear()` can wipe out the outer scope's `traceId`.

Full-snapshot approach:

```java
Map<String, String> previous = MDC.getCopyOfContextMap();
try {
    MDC.setContextMap(captured);
    runnable.run();
} finally {
    if (previous == null) MDC.clear();
    else MDC.setContextMap(previous);
}
```

This is a **fragment**, assuming `captured` is non-null. If null, `MDC.clear()` is needed at the start like the complete `MdcTaskDecorator` class. Restoring the map handles keys introduced during the task centrally.

### 13.3. Filter Cleanup When a Controller Returns CompletableFuture

A Spring MVC controller returning `CompletableFuture` may complete the HTTP response after the initial servlet thread has exited the filter. The filter's `finally` must still restore MDC on its thread. Never leave MDC around "so MVC can still log"; doing so leaks the ID to the next request running on that servlet thread.

For logs emitted during subsequent MVC async/error dispatches, use an appropriate context propagation mechanism for the new dispatch or framework observability. **MDC is not durable request state across all dispatches.**

## 14. Handling Errors, Cancellation, and Shutdown Without Losing the Trail

A request may submit a task to an executor and finish before the worker runs. If the client times out, **the task may still keep running**. The correlation ID should be kept in the job payload or context snapshot for accepted tasks; do not depend on the HTTP thread still existing.

Scenarios to test:

| Scenario | What Must Hold |
| --- | --- |
| Task throws exception | Worker logs have the right ID; `finally` restores MDC |
| Task rejected before running | Submitter logs have the right ID; do not mark status as "ran" |
| Task waits long in queue | Context was captured at submit, not when worker picked up task |
| Client request times out | Job may continue; correlation/job ID stored separately if tracking is needed |
| CompletableFuture callback outside executor | Does not automatically have the request's MDC |
| Worker reused | Must not retain the previous task's correlation ID |
| App shutdown / task interrupt | MDC cleaned up even on early exit in error branch |
| Retry same job | Preserve logical correlation ID, add separate attempt ID |
| Cross-service HTTP | Put correlation ID in explicit header; receiver re-validates |
| Broker consumer | Read message headers, set MDC in message scope, restore afterward |

**Logs from a late-finishing worker** may appear after HTTP 202/timeout; this is not a bug if the system has clear job IDs/correlation IDs and a state machine. Do not interpret "the client stopped waiting" as "the worker definitely stopped running".

### 14.1. @Async void and CompletableFuture Exceptions

`@Async void` does not return a Future to the caller; exceptions must be observed via `AsyncUncaughtExceptionHandler`/logging, and that handler may run under its own execution lifecycle. For methods returning `CompletableFuture<T>`, the caller should attach `whenComplete` or `handle` to record outcomes.

`whenComplete` **without the Async suffix** can run on the thread completing the future or the registering thread, depending on timing. If the logging callback needs a guaranteed ID, **capture the correlation ID into the closure as an immutable variable** or route the callback through a context-aware executor; do not trust `MDC.get` at callback time to always match the HTTP request.

An explicit solution:

```java
String requestCorrelationId = MDC.get("correlationId");

future.whenComplete((result, error) -> {
    // Use requestCorrelationId as trace data;
    // do not assume the callback thread's MDC always holds the ID.
    if (error != null) {
        log.warn("Job failed, correlationId={}",
                requestCorrelationId, error);
    }
});
```

This is a fragment; `future` and `log` are required. To make the callback log according to an MDC layout, you still need to set/restore MDC inside the callback or use context-aware scheduling; writing the ID explicitly into the message here simply avoids wrong assumptions about the thread.

## 15. Testing Propagation Properly

Seeing two log lines with the same ID in a single run **is not enough**. You must test multiple requests, failures, and thread reuse.

### 15.1. JDK Unit Test Ideas

With `ContextBoundaryDemo.java`, verify three invariants:

1. Without wrapper: worker does not see caller's request ID.
2. With wrapper: worker sees the exact snapshot from caller.
3. After wrapper: worker does not retain the previous request's snapshot.

Extend the test by intentionally throwing a `RuntimeException` inside the decorated action, catching via `Future.get()`, and submitting a follow-up task to confirm MDC was restored via `finally`.

### 15.2. Spring Integration Tests

With `CorrelationApplication`:

- Send a request with `X-Correlation-ID: req-A`, check response body `requestCorrelationId=workerCorrelationId=req-A`.
- Send a request with `X-Correlation-ID: req-B` right after, verifying the worker does not carry `req-A`.
- Send a request without the header, checking that the response header contains a server-generated ID and the body uses that same ID.
- Send an overly long header or invalid characters, verifying the filter does not copy it raw into MDC/response.
- Intentionally make `WorkService` throw an exception; verify the next task still gets the right MDC and does not leak.
- Test `@Async` called **from another bean** on the right `workExecutor`; self-invocation must not be used to test propagation.
- Use a pool with core=1 in tests to force reuse of the same worker and reduce scheduling variance.
- Test a `CompletableFuture.thenApply` callback after upstream completes to see that the registration thread can participate, avoiding assuming MDC on all callbacks.

For real logging, use a capturing appender or test instrumentation to inspect MDC when the log event is created, rather than only comparing formatted output strings affected by async appenders.

### 15.3. Production Monitoring

Monitor propagation quality as well:

- Rate of logs/jobs missing `correlationId` where expected.
- Jobs/HTTP requests with abnormal, overly long, or duplicate correlation IDs.
- Tasks on workers whose ID differs from metadata in their payload.
- Execution time, queue wait, rejection counts, and exceptions per executor.
- Number of requests/jobs that ended while workers still continue — potentially valid, yet requiring log linkage.
- Alignment between `correlationId`, `jobId`, and `traceId`/`spanId` in structured logs.

Never export the entire MDC map or user payloads into metric labels: cardinality explodes and data leaks. **Correlation IDs typically have high cardinality**, making them suited for logs and trace lookups rather than primary labels on metric time series.

## 16. Common Mistakes

**Mistake 1 — Assuming MDC automatically follows @Async.** ThreadPoolTaskExecutor uses separate workers; MDC is usually thread-local and requires propagation.

**Mistake 2 — Reading MDC inside the worker and thinking it is the submitting request's ID.** The worker may have no context or hold an old ID. Capture from the submitter.

**Mistake 3 — Capturing MDC once when initializing a singleton executor.** A startup snapshot is not a per-task snapshot.

**Mistake 4 — Setting MDC on the worker without finally.** Exceptions or cooperative cancellation can leak context to another request.

**Mistake 5 — Only calling clear without restoring previous.** This can break scopes of outer instrumentation/decorators.

**Mistake 6 — Using InheritableThreadLocal instead of TaskDecorator in a reusable pool.** Values only relate to thread creation time, unsuitable for each submission.

**Mistake 7 — Unconditionally propagating the entire MDC.** May copy PII/tokens and too many unnecessary keys; pick the minimal scope.

**Mistake 8 — Believing CompletableFuture.supplyAsync(...) without an executor uses the Spring pool.** The default JDK async facility is typically commonPool, bypassing Spring's TaskDecorator.

**Mistake 9 — Believing non-Async callbacks always run on a context-carrying worker.** Callbacks may run inline on the registration thread when the stage is already complete or under another completion policy.

**Mistake 10 — Assuming @Async("workExecutor") applies to this.method() in the same bean.** Self-invocation in proxy mode bypasses the interceptor.

**Mistake 11 — Only setting MDC without configuring the log pattern/structured encoder.** The correlation ID will not appear in log output if the layout does not read the field.

**Mistake 12 — Using a correlation ID as authentication or a standalone idempotency key.** Client-provided IDs can be forged and do not prove permissions or uniqueness of business side effects.

**Mistake 13 — Failing to propagate outgoing HTTP/message headers.** Service A's MDC does not automatically appear in Service B.

**Mistake 14 — Treating a custom correlation ID as standard trace context.** W3C trace/span has specific semantics; use proper tracing tooling when distributed traces are needed.

**Mistake 15 — Wrapping tasks yet using a different executor directly on error or retry branches.** Not every task passes through the same decorator; inventory all execution boundaries.

**Mistake 16 — Using correlation ID as a metric label for every task.** Cardinality explodes; log/trace by ID and measure aggregate metrics.

**Mistake 17 — Holding ServletRequest or SecurityContext as mutable objects in long-running jobs.** Requests end and threads change; pass only verified, necessary data.

**Mistake 18 — Believing TaskDecorator catches all Callable/Future exceptions.** With `FutureTask`, exceptions may be stored inside the Future; observe the proper error path instead of just `catch` around `Runnable.run()`.

## 17. Implementation Checklist for a Spring System

- [ ] Standardize **ID names and scopes**: how correlation ID, request ID, job ID, and trace ID differ.
- [ ] Identify ingress points creating/validating IDs: gateway, servlet filter, message listener, or scheduler.
- [ ] Use a consistent header like `X-Correlation-ID` if part of a contract; never treat client-sent headers as trusted identity.
- [ ] Set MDC in a short request/task scope and **restore in finally**.
- [ ] Register `TaskDecorator` on the exact `ThreadPoolTaskExecutor` used by `@Async` or services.
- [ ] Capture MDC **on the submitting thread for every task**, never as a singleton snapshot at startup.
- [ ] When a task has no snapshot, **clear worker MDC** to prevent stale data.
- [ ] With `CompletableFuture`, audit non-async/Async callbacks and explicit executors at every stage needing propagation.
- [ ] With jobs/brokers, pass correlation ID in **job payload/headers** and define retry attempts.
- [ ] With HTTP clients, add outbound propagation and validation at downstream ingress.
- [ ] When using Micrometer Tracing, do not invent custom trace/span IDs replacing standards; verify context propagation integrations.
- [ ] Never place secrets/PII in MDC; enforce header length/character controls and log retention.
- [ ] Configure Logback/structured logging to read the `correlationId` key.
- [ ] Test A/B requests on the **same reused worker**, exceptions, shutdown, and callbacks running on different threads.
- [ ] Log/meter executor rejections with the caller's correlation ID; do not wait for a worker to log an unaccepted task.
- [ ] Monitor rates of logs missing or carrying wrong correlation IDs and the integrity of job/request/trace linkage.

## 18. Self-Check Questions

**Question 1.** The controller calls `MDC.put("correlationId","req-1")` and then invokes `@Async`. Is the worker guaranteed to read `req-1`?

**Answer:** No. MDC is usually thread-local; you need a TaskDecorator or suitable context propagation, or to pass the ID as data.

**Question 2.** Why must `MDC.getCopyOfContextMap()` be captured in `decorate` rather than inside the wrapper's `run`?

**Answer:** `decorate` is invoked at the submit point, where the caller still holds the request context. `run` executes on the worker, which normally lacks the caller's MDC.

**Question 3.** Why is `finally` needed even when tasks usually return normally?

**Answer:** Pools reuse workers; tasks can throw exceptions or exit early. `finally` guarantees restoring/clearing context, avoiding leaking IDs to subsequent tasks.

**Question 4.** Is `MDC.clear()` after a task always better than restoring previous?

**Answer:** No. If an outer wrapper or instrumentation already set a valid context on the worker, clear wipes that scope's data. Snapshotting/restoring previous is safer for nested scopes.

**Question 5.** Does `CompletableFuture.supplyAsync(fn)` automatically use a Spring `ThreadPoolTaskExecutor` bean configured with a TaskDecorator?

**Answer:** No. Without passing an executor, it uses the JDK's default async facility. You must control the executor or pass the ID as data.

**Question 6.** Does `@Async("workExecutor")` guarantee every downstream `thenApply` always has the right MDC?

**Answer:** No. Non-async continuations may run on the completion thread or registration thread depending on timing; snapshots and boundaries must be managed explicitly.

**Question 7.** A consumer receives a Kafka message carrying a correlation ID without any HTTP request. What should it do?

**Answer:** Read metadata, validate the ID, set it in MDC for the message processing scope, propagate on further publishing, and restore/clear afterward. No fake ServletRequest is needed.

**Question 8.** Should customer emails or bearer tokens be placed into a correlation ID?

**Answer:** No. Use IDs free of PII/secrets; tokens must not be written into MDC or centralized logs.

**Question 9.** Does a correlation ID replace W3C `traceparent` and OpenTelemetry spans?

**Answer:** No. Correlation IDs group application events; distributed tracing uses trace/span context and standard propagation mechanisms. Both can be used together with clear purposes.

**Question 10.** Worker logs show `correlationId=req-A` while processing req-B's task. What should you inspect first?

**Answer:** Check which task set MDC without restoring/clearing, whether req-B's task went through the right executor's TaskDecorator, and whether snapshots are captured from the submitter rather than mistakenly from the worker.

**Question 11.** The filter restored MDC after the HTTP request; does a background job need to hold onto the ServletRequest to keep the ID?

**Answer:** No. The job should receive the correlation ID as immutable metadata or a snapshot at submit time; holding a ServletRequest across long lifecycles risks errors/data leaks.

## Summary

In Spring Framework, **MDC is thread-bound context**, whereas a logical request/job can span **multiple threads and multiple services**. Therefore:

1. **Create/validate correlation IDs at ingress**; distinguish request/job/trace/span/idempotency IDs.
2. **Propagate at asynchronous boundaries** using a TaskDecorator that captures at submit, installs before the worker runs, and restores previous in `finally`; or pass the ID as data/job metadata.
3. **Never assume `@Async`, `CompletableFuture`, raw threads, Reactor, or HTTP clients carry MDC automatically.** Every boundary needs an appropriate propagation mechanism.
4. **Return the right ID in response headers and include it in log patterns/structured logging.** When crossing to other services, propagate via headers or message metadata with validation/trust policies.
5. **Security and observability:** never copy secrets/PII, never use IDs for authorization, never make high-cardinality IDs metric labels; test worker reuse and exception cleanup.

A properly propagated correlation ID does not just make "finding logs faster"—it ensures **request A's logs are never attributed to request B** in real concurrent systems.

## References

1. SLF4J API — `MDC`: https://www.slf4j.org/apidocs/org/slf4j/MDC.html
2. Logback Manual — Mapped Diagnostic Context: https://logback.qos.ch/manual/mdc.html
3. Spring Framework Javadoc — `TaskDecorator`: https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/core/task/TaskDecorator.html
4. Spring Framework Javadoc — `ThreadPoolTaskExecutor`: https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html
5. Spring Framework Reference — Task Execution and Scheduling (`@Async`): https://docs.spring.io/spring-framework/reference/integration/scheduling.html
6. Spring Framework Javadoc — `ContextPropagatingTaskDecorator`: https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/core/task/support/ContextPropagatingTaskDecorator.html
7. Spring Framework Reference — MVC asynchronous requests: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-async.html
8. Java SE 17 — `ThreadLocal`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ThreadLocal.html
9. W3C Trace Context — `traceparent` and `tracestate`: https://www.w3.org/TR/trace-context/
