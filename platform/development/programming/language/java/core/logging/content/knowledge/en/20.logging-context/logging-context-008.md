# Context Across Executors in Java Logging: Propagating MDC Properly and Avoiding Leaks

In a Java application, logs for a single request often need `requestId`, `traceId`, `spanId`, or an operation name so multiple events can be correlated into one processing flow. Within the same thread, the logging backend can read these fields from the **Mapped Diagnostic Context (MDC)**. However, when work is handed off to an `ExecutorService`, `ThreadPoolExecutor`, `CompletableFuture`, or a framework task executor, the work runs on a different thread. **Context bound to the caller thread does not automatically follow in all cases**.

**Context across executors** is the mechanism of **capturing context upon submission → installing it on the worker while the task runs → restoring the worker's previous context in `finally`**. The two pitfalls to avoid are **lost correlation IDs** (the worker does not see `requestId`) and **leaked/mixed correlation IDs** (the worker serves a new request while still holding the MDC of an old request).

Example:

```text
INFO [thread=request-thread] requestId=req-A - event=request_received
INFO [thread=context-worker-1] requestId=none - event=without_propagation
INFO [thread=context-worker-1] requestId=req-A - event=wrapped_runnable
INFO [thread=context-worker-1] requestId=none - event=after_restore
INFO [thread=context-worker-1] requestId=req-A - event=wrapped_callable
INFO [thread=context-worker-1] requestId=req-B - event=next_request
```

This is the output of the Java 17 + Logback example in this article: the same worker is reused, yet the proper context **exists only within the scope of the corresponding task**. `none` in the pattern is a placeholder indicating no request ID is present, not a real ID.

## 1. What does logging context include?

A structured log might look like:

```json
{
  "timestamp": "2026-11-09T03:15:30.123Z",
  "level": "INFO",
  "service": "checkout-service",
  "thread": "payment-worker-2",
  "requestId": "req-A",
  "traceId": "trace-42",
  "spanId": "span-7",
  "event": "payment_authorized"
}
```

This is illustrative JSON, not Java's default output. Different fields answer different questions:

| Field | Role | Notes |
| --- | --- | --- |
| `thread` | Thread emitting the event | Thread pools can reuse the same thread across many requests |
| `requestId` | Application request | Can span multiple threads and services |
| `traceId` / `spanId` | Trace/span in distributed tracing | Must match tracing semantics, not just arbitrary strings |
| `operation` / `event` | Processing step | Prefer stable names, avoid high cardinality |
| `tenantId` | Relevant tenant if policy permits logging | Do not use an MDC key as a substitute for authorization |
| `service` / `instance` | Log emitter | May come from deployment configuration rather than the thread |

**SLF4J MDC** is an API providing a string-based key-value map that a compatible backend uses when formatting logs. On the same thread:

```java
// Fragment: LOG is an initialized org.slf4j.Logger.
org.slf4j.MDC.put("requestId", "req-A");
try {
    LOG.info("event=request_started");
} finally {
    org.slf4j.MDC.remove("requestId");
}
```

In this snippet, `MDC.remove` cleans up a single key that was set. When a prior MDC context exists or multiple keys are managed by a framework, you should **restore the pre-scope snapshot** rather than clearing the entire map indiscriminately.

**MDC is not all of execution context**: tracing `Context`, `SecurityContext`, locale, transaction, deadline, cancellation, or custom `ThreadLocal`s are separate components. Copying SLF4J MDC **does not implicitly** propagate those contexts. Conversely, propagating tracing context properly does not guarantee an encoder will automatically print every MDC field without the appropriate integration.

## 2. Why does `ExecutorService` lose context?

When processing sequentially:

```text
request-thread:
  MDC.put(requestId=req-A)
    -> service.call()
    -> LOG.info(...) sees req-A
  MDC.remove(requestId)
```

When handing off work to a pool:

```text
request-thread                        context-worker-1
  MDC: {requestId=req-A}              MDC: {} or another scope
           |
           +-- executor.submit(task) ----> task.run()
                                           LOG.info(...)
```

MDC in Logback classic is bound to the thread. A worker may have been created long before the request, or it may be reused. `executor.submit(task)` **has no general contract** to automatically carry the caller's SLF4J MDC over to the worker.

Consequences:

1. **Lost context:** worker logs have an empty `requestId`, making it impossible to correlate with the request.
2. **Leaked context:** a worker that previously handled `req-A` does not clean up MDC; later, a task for `req-B` can mistakenly log `req-A`.
3. **Accidental context clearing:** a task sets MDC and then calls `clear()`, causing an outer framework or scope to lose the map it already had.

Do not solve this by renaming the thread per request. `context-worker-1` can serve many requests; conversely, one request can pass through many workers. **Thread names help investigate concurrency; request IDs help correlate business flows.**

### `InheritableThreadLocal` is not the default solution

`InheritableThreadLocal` can pass values via inheritance when a thread is created, but **thread pools reuse workers**, and thread creation time is not the same as task submission time. Inherited data can be stale, incomplete, or outlive the request lifecycle. With executors, context must be managed **per task execution**, not based on where the thread was created.

## 3. The safe pattern: capture → install → run → restore

```text
CALLER THREAD                            WORKER THREAD
-------------                            -------------
MDC = {requestId=req-A}
     |
     +-- snapshot map on caller
     |
     +-- submit(wrappedTask) ----------------> previous = snapshot worker MDC
                                             install(req-A)
                                             try {
                                                 task.run()
                                             } finally {
                                                 restore(previous)
                                             }
```

Four steps:

1. **Capture on the caller thread:** call `MDC.getCopyOfContextMap()` **before submitting**, while the caller still holds a valid context. The API returns a copy of the map or `null`.
2. **Keep the snapshot isolated:** do not fetch the caller's MDC again after the task is queued; the caller may have already cleared it or started handling a new request.
3. **Install on the worker:** if the snapshot has data, call `MDC.setContextMap(snapshot)`; if `null`, call `MDC.clear()`.
4. **Restore in `finally`:** capture the worker's map before running the task and restore it afterward, even if the task throws an exception.

Why is **restore** better than just `clear`?

```text
Before task: {jobId=batch-3}
During task: {requestId=req-A}
After task:  {jobId=batch-3}    <- restore previous scope
```

If you only call `MDC.clear()` at the end, you lose the `jobId` that was already there. If you don't clean up at all, `req-A` sticks to the worker. `MDC.setContextMap` replaces the map with a copy, so you don't need to merge keys manually for the problem of **running a task under a complete snapshot**.

In SLF4J 2.x, `MDC.setContextMap(null)` is accepted; using an explicit `clear()` branch for `null` remains clear and avoids depending on how older adapters handle `null`.

## 4. Complete example: Java 17 + Maven + SLF4J + Logback

This example uses **Java 17**, **SLF4J API 2.0.17**, and **Logback classic 1.5.18**. Logback acts as the backend/provider with MDC support. The code uses an `ExecutorService` with an explicitly named thread to demonstrate propagation and worker reuse.

These versions are specific choices for this exercise and **should not be assumed to be the latest versions**. For production, follow your project's dependency management and security update policies.

Structure:

```text
executor-context-demo/
├── pom.xml
└── src/main/
    ├── java/com/example/logging/ExecutorContextDemo.java
    └── resources/logback.xml
```

### 4.1. `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>executor-context-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.slf4j</groupId>
            <artifactId>slf4j-api</artifactId>
            <version>2.0.17</version>
        </dependency>
        <dependency>
            <groupId>ch.qos.logback</groupId>
            <artifactId>logback-classic</artifactId>
            <version>1.5.18</version>
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
                <version>3.5.0</version>
                <configuration>
                    <mainClass>com.example.logging.ExecutorContextDemo</mainClass>
                    <classpathScope>runtime</classpathScope>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

`slf4j-api` only defines the facade and MDC API; `logback-classic` processes events and writes logs. **Do not add a second SLF4J provider** such as `slf4j-simple` or `slf4j-nop` to the same runtime when you want Logback behavior.

### 4.2. `logback.xml`

Placed at `src/main/resources/logback.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<configuration>
    <appender name="STDERR"
              class="ch.qos.logback.core.ConsoleAppender">
        <target>System.err</target>
        <encoder>
            <pattern>%level [thread=%thread] requestId=%X{requestId:-none} - %msg%n</pattern>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="STDERR"/>
    </root>
</configuration>
```

`%level` prints the event level, `%thread` is the thread name, `%X{requestId:-none}` reads MDC or prints the fallback value `none` if the key is absent, and `%msg` is the message. The appender sends output to **stderr**.

The pattern intentionally omits timestamps so the example produces deterministic output. In production, you need an explicit timestamp/offset, logger name, service, trace ID, exceptions, and a format suited to your collector.

### 4.3. `ExecutorContextDemo.java`

```java
package com.example.logging;

import java.util.Map;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;

public final class ExecutorContextDemo {
    private static final Logger LOG =
            LoggerFactory.getLogger(ExecutorContextDemo.class);

    private ExecutorContextDemo() {
    }

    private static void install(Map<String, String> context) {
        if (context == null) {
            MDC.clear();
        } else {
            MDC.setContextMap(context);
        }
    }

    private static Runnable withMdc(Runnable task) {
        // Capture on the caller thread before submitting.
        Map<String, String> submitted = MDC.getCopyOfContextMap();

        return () -> {
            // Preserve the worker's previous context.
            Map<String, String> previous = MDC.getCopyOfContextMap();
            try {
                install(submitted);
                task.run();
            } finally {
                install(previous);
            }
        };
    }

    private static <T> Callable<T> withMdc(Callable<T> task) {
        Map<String, String> submitted = MDC.getCopyOfContextMap();

        return () -> {
            Map<String, String> previous = MDC.getCopyOfContextMap();
            try {
                install(submitted);
                return task.call();
            } finally {
                install(previous);
            }
        };
    }

    public static void main(String[] args) throws Exception {
        Thread producer = Thread.currentThread();
        String originalName = producer.getName();
        producer.setName("request-thread");

        ExecutorService pool = Executors.newSingleThreadExecutor(
                task -> new Thread(task, "context-worker-1"));

        try {
            // Initialize the worker and ensure the initial context is empty.
            pool.submit(() -> MDC.clear()).get();

            MDC.put("requestId", "req-A");
            try {
                LOG.info("event=request_received");

                // Unwrapped: worker does not have req-A.
                pool.submit(() ->
                        LOG.info("event=without_propagation")).get();

                // Wrapped Runnable: worker sees req-A during the task.
                pool.submit(withMdc(() ->
                        LOG.info("event=wrapped_runnable"))).get();

                // After restore, worker no longer has requestId.
                pool.submit(() ->
                        LOG.info("event=after_restore")).get();

                // Wrapped Callable to receive a return value from the worker.
                String result = pool.submit(
                        withMdc((Callable<String>) () -> {
                            LOG.info("event=wrapped_callable");
                            return MDC.get("requestId");
                        })).get();

                System.out.println("callableRequestId=" + result);
            } finally {
                MDC.clear();
            }

            // Another request reuses the exact same worker.
            MDC.put("requestId", "req-B");
            try {
                pool.submit(withMdc(() ->
                        LOG.info("event=next_request"))).get();
            } finally {
                MDC.clear();
            }
        } finally {
            pool.shutdown();
            producer.setName(originalName);
        }

        System.out.println("finished=true");
    }
}
```

### 4.4. Running and verifying

In the `executor-context-demo/` directory:

```bash
mvn -q compile exec:java
```

**Six application log events on stderr, in exact order:**

```text
INFO [thread=request-thread] requestId=req-A - event=request_received
INFO [thread=context-worker-1] requestId=none - event=without_propagation
INFO [thread=context-worker-1] requestId=req-A - event=wrapped_runnable
INFO [thread=context-worker-1] requestId=none - event=after_restore
INFO [thread=context-worker-1] requestId=req-A - event=wrapped_callable
INFO [thread=context-worker-1] requestId=req-B - event=next_request
```

**Stdout printed by the program itself:**

```text
callableRequestId=req-A
finished=true
```

Maven or the terminal may emit additional build tool output. If stdout and stderr are merged, the **interleaving order between the two streams** is not strictly guaranteed; however, the log events in this synchronous example are submitted in order thanks to `Future.get()`.

Explanation of results:

1. `request_received` on the producer has `req-A`.
2. `without_propagation` runs on the worker without copying MDC, so it shows `none`.
3. `wrapped_runnable` was created while the producer had `req-A`; the worker installs the snapshot before `LOG.info`.
4. `after_restore` runs on the same worker after the wrapper finishes; because the pre-wrapper map was empty, the output is `none`, with no `req-A` leak.
5. `wrapped_callable` still has `req-A` and returns that value to the caller via `Future<String>`.
6. `next_request` shows the worker is reused without retaining the previous ID; the new task receives `req-B` in its proper scope.

**Java 17 note:** The example uses `shutdown()` and `Future.get()` calls that wait for all tasks; it does not use `try-with-resources` for `ExecutorService` because you should not assume this interface implements `AutoCloseable` in JDK 17. In real systems, you need an appropriate `shutdown`/`awaitTermination`/timeout strategy and interrupt handling.

### 4.5. Testing the negative cases of the wrapper

If you change the two `withMdc(() -> LOG.info(...))` calls to plain tasks, worker logs will not automatically receive the producer's context. If you omit `install(previous)` in `finally`, a subsequent task can inherit the **old requestId**. If you take the snapshot **inside the worker** instead of on the caller, you only copy the worker's context and fail to solve propagation.

The main exercise is designed to prove both **proper propagation** and **proper restoration**, because a test that only checks "task A sees ID A" cannot detect a leak into task B.

## 5. MDC APIs to understand

| API | Effect | Points to note |
| --- | --- | --- |
| `MDC.put(k, v)` | Adds/updates a key on the current thread | Do not use to pass directly to another thread |
| `MDC.get(k)` | Reads a key on the current thread | May return `null` |
| `MDC.remove(k)` | Removes a key | Does not automatically restore an old value if the key was overwritten |
| `MDC.clear()` | Clears the entire MDC map of the current thread | Can wipe keys managed by a framework |
| `MDC.getCopyOfContextMap()` | Returns a copy of the current map | May return `null` |
| `MDC.setContextMap(map)` | Replaces the current map with a copy | Used with the restore mechanism to create a scope |
| `MDC.putCloseable(k, v)` | Returns a closeable scope to remove one key | Does not replace full-map snapshot/restore in all scenarios |

**`MDC.getCopyOfContextMap()` returns a snapshot**, not a live reference that updates automatically when the caller changes context. This is essential: a task submitted for `req-A` must retain `req-A` semantics even if the producer moves on to `req-B` before the worker picks up the task from the queue.

### Why does the wrapper have `finally`?

```java
// Fragment illustrating the principle: previous, submitted, and task are already defined.
try {
    install(submitted);
    task.run();
} finally {
    install(previous);
}
```

Even if `task.run()` throws an exception, `finally` still restores the map. Do not use a `catch (Exception ignored)` to swallow errors. With `ExecutorService.submit`, task errors are stored in the `Future` and surface when calling `get()` as an `ExecutionException`. If your code never observes the `Future`, error logging and incident handling require a dedicated policy.

## 6. `execute`, `submit`, and `Callable<T>`

At task submission boundaries, use the wrapper matching the callback type:

```java
// Fragment: executor, withMdc, and business methods are already defined.
executor.execute(withMdc(() -> sendMessage()));

executor.submit(withMdc(() -> writeAuditSummary()));

java.util.concurrent.Future<String> result = executor.submit(
        withMdc((java.util.concurrent.Callable<String>) () ->
                calculateResult()));
```

This is a fragment, not a standalone program; methods like `sendMessage()` must be provided by the application.

- `execute(Runnable)` does not return a `Future`; error handling depends on the executor/uncaught exception handling.
- `submit(Runnable)` or `submit(Callable<T>)` returns a `Future`; `get()` lets you wait and observe exceptions.
- **Capture before submission** is the rule for both.
- If a framework already provides context propagation on the executor, determine whether a caller-side wrapper is still needed to avoid creating scopes with competing context sources.
- When a task is rejected (`RejectedExecutionException`), the wrapper never ran, so worker context restoration should not depend on a task that never executed.
- When a task is cancelled or interrupted while running, `finally` must still restore; do not arbitrarily hide or swallow interrupts.

### Task is queued and the caller changes context

```text
t0 caller MDC = req-A
t1 create wrapper and capture req-A
t2 call submit(...)
t3 caller finishes req-A, clears MDC
t4 caller receives req-B, calls put(req-B)
t5 worker runs req-A's task -> must see req-A
t6 worker restores previous context
```

That is why you **must not read the caller's MDC too late**. A per-task snapshot reflects the task's relationship to where it was created, independent of which thread the executor selects.

## 7. `CompletableFuture`: each async stage can switch threads

A chain can consist of multiple callbacks:

```text
supplyAsync(...)       -> worker A
thenApply(...)         -> may run on the thread that completed the previous stage
thenApplyAsync(...)    -> may be scheduled on a different executor
whenCompleteAsync(...) -> may schedule another callback
```

**Do not automatically assume** that wrapping `supplyAsync` guarantees context for the entire chain. For async stages, propagation is needed at the right boundaries. Non-`Async` stages such as `thenApply` are not guaranteed to run on the caller thread either.

Example of a `Supplier` wrapper:

```java
// Fragment: utility method with Map, Supplier, and MDC imported.
static <T> java.util.function.Supplier<T> withMdcSupplier(
        java.util.function.Supplier<T> action) {

    Map<String, String> submitted = MDC.getCopyOfContextMap();

    return () -> {
        Map<String, String> previous = MDC.getCopyOfContextMap();
        try {
            if (submitted == null) MDC.clear();
            else MDC.setContextMap(submitted);

            return action.get();
        } finally {
            if (previous == null) MDC.clear();
            else MDC.setContextMap(previous);
        }
    };
}
```

Applied in a class that has the `withMdcSupplier` method:

```java
// Fragment: executor and callDownstream() are already available.
java.util.concurrent.CompletableFuture<String> future =
        java.util.concurrent.CompletableFuture.supplyAsync(
                withMdcSupplier(() -> callDownstream()),
                executor);
```

This is a **fragment**, not a standalone runnable program. Callbacks such as `Function`, `Consumer`, and `BiFunction` may need corresponding wrappers or a **context-aware executor** configured at the infrastructure layer.

**Avoid arbitrary double wrapping:** if the application already has an executor decorator that propagates context, wrapping every stage again can create unintended snapshot ordering or extra overhead. Pick one consistent strategy and test it across success, failure, cancellation, and continuation paths.

## 8. Scheduled tasks: do not keep a request snapshot indefinitely

With `ScheduledExecutorService`:

```java
// Fragment: scheduler and job are already declared.
scheduler.scheduleAtFixedRate(
        withMdc(job), 0, 1,
        java.util.concurrent.TimeUnit.MINUTES);
```

If `withMdc(job)` is created while `requestId=req-A` and the job runs every minute for hours, every run may keep carrying the **old req-A**. In code terms the wrapper restores properly, but the context semantics are wrong.

For scheduled/background jobs:

- Generate an appropriate `jobId` or `runId` **per execution**.
- Only keep `originRequestId` if you genuinely need to link back to the request that created the work and policy allows it.
- Do not turn a short-lived request ID into the permanent identity of a recurring job.
- Clean up the MDC scope at the end of each execution, especially when the scheduler reuses threads.
- If a task is persisted and runs after a restart, store valid business metadata in the job record rather than expecting `ThreadLocal` to survive.

## 9. Spring: `TaskDecorator` and built-in context propagation

Spring Framework supports `TaskDecorator` to wrap tasks when a `TaskExecutor` dispatches work. This is a good place to **centralize propagation logic**, avoiding the need for every developer to remember `withMdc`.

A `ThreadPoolTaskExecutor` configuration fragment:

```java
// Fragment in Spring configuration; executor is already a ThreadPoolTaskExecutor.
executor.setTaskDecorator(task -> {
    java.util.Map<String, String> submitted =
            org.slf4j.MDC.getCopyOfContextMap();

    return () -> {
        java.util.Map<String, String> previous =
                org.slf4j.MDC.getCopyOfContextMap();

        try {
            if (submitted == null) org.slf4j.MDC.clear();
            else org.slf4j.MDC.setContextMap(submitted);

            task.run();
        } finally {
            if (previous == null) org.slf4j.MDC.clear();
            else org.slf4j.MDC.setContextMap(previous);
        }
    };
});
```

This is a fragment requiring Spring and a properly initialized executor; it is not a standalone class. Register the decorator **before tasks are submitted**, and verify that the executor actually used by `@Async` or your code is the one equipped with the decorator.

Spring Framework 6.1+ also provides `ContextPropagatingTaskDecorator` using Micrometer Context Propagation:

```java
// Fragment with appropriate Spring Framework/Micrometer integration.
executor.setTaskDecorator(
        new org.springframework.core.task.support
                .ContextPropagatingTaskDecorator());
```

This snippet has corresponding dependency, version, and integration requirements. **Do not assume** it copies every custom `ThreadLocal` and MDC in every project; check which context accessors are registered, which trace observation context is active, and test end-to-end. Decorators add overhead for very small tasks.

If `@Async` does not switch threads due to self-invocation/proxying or misconfiguration, that is an **async activation** bug that must be fixed before concluding MDC propagation does not work.

## 10. Log4j 2 `ThreadContext` follows the same principles

Log4j 2 uses `ThreadContext` for map and stack (NDC) context. A fragment example with the `ThreadContext` **map**:

```java
// Fragment: org.apache.logging.log4j.ThreadContext and Map are already imported.
Map<String, String> submitted = ThreadContext.getImmutableContext();

Runnable wrapped = () -> {
    Map<String, String> previous = ThreadContext.getImmutableContext();
    try {
        ThreadContext.clearMap();
        ThreadContext.putAll(submitted);
        task.run();
    } finally {
        ThreadContext.clearMap();
        ThreadContext.putAll(previous);
    }
};
```

This fragment assumes `task` is already declared and the wrapper is created **on the caller**. `getImmutableContext()` provides a map snapshot; `clearMap`/`putAll` install and restore the map. If the application uses the **ThreadContext stack/NDC**, copying the map does not automatically propagate the stack — a separate mechanism is needed.

For applications using SLF4J with a Log4j 2 backend, verify the exact SLF4J provider, bridges, and MDC compatibility. Do not place bidirectional SLF4J ↔ Log4j 2 bridges in the same runtime, as that can create a loop.

## 11. OpenTelemetry tracing context differs from SLF4J MDC

OpenTelemetry has `Context`/`Scope` to propagate the current span and defined context data. Its Java API provides ways to wrap `Runnable`/`Callable`/executors:

```java
// Fragment: pool is an existing Executor, and the application has OTel Context.
java.util.concurrent.Executor propagated =
        io.opentelemetry.context.Context.taskWrapping(pool);

propagated.execute(() -> performOperation());
```

This is a fragment, not a pure-JDK program; `performOperation()` is supplied by the application. `Context.taskWrapping` is designed to carry **OpenTelemetry Context** across executors. It does not automatically prove that all custom MDC keys are propagated or printed by an encoder. Integration between tracing and logging is required so `traceId`/`spanId` appear properly in log events.

Comparison:

| Context | Example API | Scope |
| --- | --- | --- |
| SLF4J MDC | `MDC.put`/`MDC.getCopyOfContextMap` | Log metadata, typically thread-bound |
| Log4j 2 map/stack | `ThreadContext` | Log4j event metadata |
| OpenTelemetry | `Context.current()`, `Scope`, `Context.taskWrapping` | Tracing/context propagation |
| Spring Security | `SecurityContext` and corresponding executor wrappers | Principal/authorization info; must use proper security mechanisms |
| Reactor | Reactor `Context`/context propagation | Context across reactive operators/schedulers |

**Do not use logging MDC as a trusted principal store for authorization.** Security mechanisms must have their own propagation and validation policies; MDC is primarily for investigation and observability.

### Reactive and virtual threads

- In **Reactor**, a pipeline can switch threads across schedulers; plain `ThreadLocal` is insufficient for all asynchronous boundaries. You need Reactor Context or an appropriate context-propagation integration.
- **Virtual threads** are officially supported in Java 21+; they have `ThreadLocal`s, but their execution structure differs from traditional pools. Do not assume all MDC from a caller is automatically copied across virtual thread creation or all reactive callbacks.
- The main example in this article uses **Java 17 platform threads**, so it does not depend on Java 21 APIs.

## 12. Async business tasks vs. async log appenders

There are two easily confused forms of "async":

1. **Async business execution:** `ExecutorService` offloads business code to another worker. **You must handle context propagation across tasks.**
2. **Async logging backend:** business code emits a log, and the backend captures the log event and queues it to a file/console writer thread. **The backend/encoder must preserve the event's metadata** across the queue.

Enabling Logback's `AsyncAppender` **does not make** `ExecutorService.submit` automatically propagate SLF4J MDC. Conversely, a proper task wrapper does not guarantee the logging backend's queue won't drop events or that the collector has received the records.

If you write a custom asynchronous formatter, do not call `Thread.currentThread().getName()` on the log-writing worker and treat it as the event's thread; use the metadata captured by the backend at log emission time.

## 13. Common issues and how to investigate

| Symptom | Cause | Fix |
| --- | --- | --- |
| Worker missing request ID | Not captured/propagated | Snapshot on caller, install when worker runs |
| Request B logs carry A's ID | Previous context not restored, worker reused | Restore in `finally`; test two requests on the same worker |
| Snapshot is null | Caller has no MDC yet or incompatible provider | Check where context is set and check SLF4J backend |
| Worker has ID but encoder doesn't print it | Pattern/JSON encoder missing MDC key | Check `%X{requestId}` and field mapping |
| First `CompletableFuture` stage right, later stage wrong | New async boundary not propagated | Wrap each stage or use a context-aware executor |
| `Callable` runs but exception not visible | `submit` stores error in `Future` | Inspect `get()` / error callbacks |
| `InheritableThreadLocal` works intermittently | Worker creation/reuse is decoupled from submit | Propagate per task, not only at thread creation |
| Scheduled job logs old ID | Snapshot taken once at scheduling time | Create context per execution |
| Spring `@Async` misses decorator | Different executor or proxy not active | Check executor configuration and async activation |
| Framework context lost on worker | Only called `clear()` at end without restoring | Save previous and restore it |
| MDC present but trace ID wrong | OTel context differs from SLF4J MDC | Propagate tracing context properly and integrate logging |
| Log4j 2 NDC stack lost | Only copied ThreadContext map | Use stack propagation if needed |
| Tiny tasks become slow | Copying too much MDC / double wrapping | Limit keys, measure overhead, use an appropriate decorator |
| Task fails and context lingers | Missing `finally` or error handler swallows error | Scope with `finally`; do not hide exceptions |
| Cross-tenant leakage | Request context not cleaned or holds invalid data | Test isolation, clean up context, security review |
| Tests use SLF4J NOP/Simple | Provider lacks MDC support like Logback | Check runtime/test classpath |
| Thread name right but request ID wrong | Thread name is not a correlation ID | Track MDC and request lifecycle separately |

**Investigation sequence:**

```text
Does the caller have requestId when submitting?
    |
    v
Was the snapshot taken before clearing?
    |
    v
Was the right wrapper/executor executed?
    |
    v
Was it installed on the worker before LOG.info?
    |
    v
Does the appender/encoder read MDC?
    |
    v
Does finally restore previous?
    |
    v
Does the next task on the same worker still have the old context?
```

If every step is right yet the dashboard still lacks the ID, inspect the collector/structured field mapping next. **Reading MDC correctly in Java does not by itself prove the pipeline stored that field.**

## 14. Testing: proving propagation and no leaks

A practical test suite should cover:

1. **Caller has context:** `requestId=req-A` before submitting the task.
2. **Unwrapped task:** in the Logback demo environment, the worker does not see `req-A` on its own.
3. **Wrapped Runnable:** the worker sees `req-A`.
4. **Post-restore task:** immediately after the wrapper, the same worker no longer has `req-A`.
5. **Wrapped Callable:** `Future.get()` receives the expected value.
6. **Request B:** the same worker must see `req-B`, not mixed with A.
7. **Exception path:** the task throws an error, yet `finally` still restores.
8. **Nested scopes:** the worker already had framework context, and it remains intact after the child task.
9. **Multiple keys:** request ID, trace ID, and operation are handled consistently.
10. **Async chain:** `CompletableFuture` stages requiring propagation all have the right IDs.
11. **Cancel/reject:** an unrun or cancelled task does not corrupt the producer's or worker's context.
12. **Scheduled execution:** the job generates an appropriate run ID per execution.
13. **Backend/collector:** actual text or JSON logs contain the fields and are queryable.
14. **Security:** do not copy tokens, secrets, raw request bodies, or unauthorized tenant info.

A check you can add to the exercise code:

```java
// Fragment: pool and withMdc(Runnable) are already declared in the demo class.
var failed = pool.submit(withMdc(() -> {
    LOG.info("event=before_failure");
    throw new IllegalStateException("simulated failure");
}));

try {
    failed.get();
} catch (java.util.concurrent.ExecutionException expected) {
    // In the test, confirm the failure cause; the worker already restored in finally.
}

pool.submit(() -> LOG.info("event=after_failure")).get();
```

This is a **fragment**, not standalone runnable code. In production, do not leave a `catch` block empty or ignore exception causes; the goal of this exercise is to verify that the failing task's context is cleaned up before the next task runs.

## 15. Security, limits, and operational strategy

- **Put only minimal metadata into MDC:** request ID/trace ID/operation when useful. Avoid passwords, tokens, session cookies, payment data, or raw HTTP bodies.
- **Validate input used as a request ID:** limit length, characters, and ID origin; do not trust a self-asserted client header as a valid ID without rules.
- **Limit key count and value length:** oversized maps increase snapshot/restore overhead and the memory footprint of queued tasks.
- **Do not hold large request objects in `ThreadLocal`:** it is easy to retain references beyond their scope, causing memory leaks.
- **Do not propagate security privileges solely via MDC:** use the proper security context mechanism and re-authorize at required boundaries.
- **Do not propagate MDC from a request that lives a few seconds into a job that lives for hours** if all you need is an independent job ID.
- **Use one consistent strategy:** manual wrappers, executor decorators, or framework instrumentation. If combining them, define precedence/scope order and test thoroughly.
- **Observe overhead:** with millions of tiny tasks, context capture/restore can be significant; measure latency, queue depth, and throughput.
- **Distinguish propagation from reliability:** valid context does not guarantee logs won't be filtered by level, dropped in an async queue, or truncated by a collector.
- **When sending work across processes/networks:** in-JVM MDC does not automatically follow HTTP/gRPC/Kafka. You need a contract to carry correlation/tracing metadata, enforce trust boundaries, and sanitize on the consumer side.

**Conclusion:** Logging context across executors is not just adding `MDC.put` inside a worker. It is a **task-scoped lifecycle**: snapshot at submission, install at execution, and restore the previous context in `finally`. Proper scoping gives logs from the same request a correlation ID across threads while preventing new requests from picking up stale IDs when thread pools reuse workers.

## Official documentation

- SLF4J — MDC API: https://www.slf4j.org/apidocs/org/slf4j/MDC.html
- Logback — MDC and managed threads: https://logback.qos.ch/manual/mdc.html
- Logback — PatternLayout and `%X{key:-default}`: https://logback.qos.ch/manual/layouts.html
- Oracle Java 17 — ExecutorService: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html
- Oracle Java 17 — CompletableFuture: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html
- Spring Framework — ContextPropagatingTaskDecorator: https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/core/task/support/ContextPropagatingTaskDecorator.html
- OpenTelemetry Java — Context propagation: https://opentelemetry.io/docs/languages/java/api/
