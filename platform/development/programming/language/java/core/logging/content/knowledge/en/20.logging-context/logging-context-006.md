# Context and Threads in Java Logging

## 1. What is logging context and why do threads matter?

**Logging context** is supplementary information attached to a log event so readers know **which request, task, transaction, trace, or execution flow the event belongs to**. In concurrent applications, a single line like `INFO request.completed` is not enough to distinguish two interleaved requests.

Example without context:

```text
INFO  event=order.received
INFO  event=order.received
WARN  event=payment.retry
INFO  event=order.completed
```

Example with context:

```text
INFO  [http-1] requestId=req-A event=order.received
INFO  [http-2] requestId=req-B event=order.received
WARN  [pool-1] requestId=req-A event=payment.retry
INFO  [http-2] requestId=req-B event=order.completed
```

The lines above are **illustrative**. With `requestId`, you can correlate lines from the same request even when they are interleaved and potentially executed on **different threads**. The thread name indicates **where the log was emitted at that moment**, not the persistent identity of the request.

In Java, a straightforward way to hold per-thread context is `ThreadLocal`. Logging frameworks such as **Logback** support **MDC (Mapped Diagnostic Context)** through the `org.slf4j.MDC` API; Log4j 2 provides `ThreadContext`; JUL (`java.util.logging`) does not have an equivalent standard MDC, though you can use explicit context passing or an application-managed `ThreadLocal`.

Core takeaway of this lesson:

> **Storing context per thread does not automatically mean context follows a unit of work.** When a task moves to an `ExecutorService`, `CompletableFuture`, callback, message listener, or asynchronous pipeline, you must understand and control the **capture → install → execute → restore** lifecycle.

### Objectives

After this lesson, you will be able to:

1. Distinguish **thread name/thread ID** from **requestId, traceId, spanId, and jobId**.
2. Understand `ThreadLocal`, MDC, and the limits of per-thread context storage.
3. Explain why thread pools can cause **lost context** or **context leakage across tasks**.
4. Safely propagate, restore, and clear context with `Runnable`, `ExecutorService`, and `CompletableFuture`.
5. Understand the difference between the context of the **event-producing thread** and the thread **processing log output asynchronously**.
6. Apply these practices in SLF4J/Logback and recognize when distributed tracing or framework-level context propagation is needed.
7. Run a **JDK-only Java 17** program to demonstrate both the problem and the fix.

## 2. Do not equate a thread with a request

An HTTP or event-driven system might execute as follows:

```text
Request req-A
  |
  +--> http-worker-1: validate input
  |
  +--> executor-worker-2: call payment provider
  |
  +--> http-worker-1: return response

Request req-B
  |
  +--> http-worker-1: receive request after req-A finishes
  |
  +--> executor-worker-3: process asynchronously
```

Here:

- **One request can run across multiple threads**: `req-A` appears on both `http-worker-1` and `executor-worker-2`.
- **One thread can serve multiple requests over time**: `http-worker-1` is reused for `req-B`.
- Thread pools typically **reuse threads** instead of creating a new thread per task.
- A thread name may be `main`, `worker-1`, `ForkJoinPool.commonPool-worker-*`, or a framework-assigned name. It is not a system-wide correlation ID.
- `requestId` and `traceId` usually must be generated or extracted at the request boundary, attached to the context, and **propagated alongside the work** when execution moves elsewhere.

Therefore, merely adding `%thread` to your log layout still **does not** solve finding all logs belonging to a request. Thread name is only one useful diagnostic dimension.

| Information | What is it for? | Is it stable across threads? |
| --- | --- | --- |
| Thread name | Identifies the thread that emitted the log | No; it can change at another step |
| Thread ID | Identifies a thread within a runtime scope | Not a request ID; do not use as a distributed key |
| `requestId` | Groups logs for one HTTP request or processing cycle | Yes, if propagated properly |
| `jobId` | Groups logs for a background job | Yes, if attached and propagated properly |
| `traceId` | Links operations within a distributed trace | Yes, if tracing is propagated properly |
| `spanId` | Identifies a unit of work within a trace | May change across steps/spans |
| `userId` | Business context that can be useful but sensitive | Should not be logged without appropriate need and authorization |

**Do not put the request ID into the Logger name.** Logger names should stay fixed by package/class, such as `com.example.order.OrderService`. Creating per-request names like `com.example.order.req-A` causes an explosion of Logger instances and makes level configuration difficult. Keep IDs in MDC or event fields.

## 3. How does ThreadLocal work?

`ThreadLocal<T>` allows the same `ThreadLocal` variable to be accessed from multiple threads, while **each thread has its own independent value**. Calling `set(...)` on one thread does not make another thread calling `get()` see that value.

**Java snippet** example:

```java
private static final ThreadLocal<String> REQUEST_ID =
        new ThreadLocal<>();

REQUEST_ID.set("req-42");
try {
    logger.info("event=request.received");
} finally {
    REQUEST_ID.remove();
}
```

This is an **illustrative snippet inside a method**, assuming `logger` already exists. `set(...)` binds the value to the current thread; `get()` reads it on that same thread; `remove()` cleans up the value after the processing scope ends.

### 3.1. Why must context be cleaned up?

Threads in a pool can live for the entire lifetime of the application. If request A sets `requestId=req-A` and forgets to clear it, that thread may later handle request B and **still read req-A**, mixing logs from two different users or transactions.

This is both an observability bug and a potential **cross-request information leak**. Cleaning up context in a `finally` block is an essential rule, even when a task throws an exception.

### 3.2. `remove()` is not equivalent to `set(null)` in all cases

With a standard `ThreadLocal`, `remove()` deletes the current thread's entry, whereas `set(null)` still stores a `null` value for the thread. If `ThreadLocal.withInitial(...)` is used, after `remove()`, the next `get()` may invoke the initial value supplier again. You must understand these semantics when designing context management.

For scoped contexts, you can **restore the previous value** rather than always clearing it. This is especially important when scopes are **nested** (request → operation → subtask), or when a wrapper runs on a thread that already holds its own valid context.

### 3.3. ThreadLocal does not replace explicit data passing

A `ThreadLocal` reduces the need to pass the same ID string through every method signature just for logging. However, critical business logic (authorization, tenant resolution, transactions, deadlines) **should not silently depend on a logging-specific MDC/ThreadLocal**. When data is needed for business decisions, pass it explicitly via parameters, an immutable `Context` object, or a well-defined framework context mechanism.

## 4. MDC in SLF4J and Logback

**MDC — Mapped Diagnostic Context** — is a widely used API for storing `String key → String value` pairs attached to the current thread's diagnostic context.

Example:

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;

Logger log = LoggerFactory.getLogger("com.example.checkout");

MDC.put("requestId", "req-42");
MDC.put("operation", "placeOrder");
try {
    log.info("event=order.received orderId={}", "ord-17");
} finally {
    MDC.remove("operation");
    MDC.remove("requestId");
}
```

This is a **method-level code snippet**, not a standalone Java class. It requires `slf4j-api` and a configured logging provider that supports MDC.

With Logback, a pattern such as:

```xml
<pattern>%-5level [%thread] requestId=%X{requestId} operation=%X{operation} %logger{36} - %msg%n</pattern>
```

is placed inside an Appender's `<encoder>`. `%X{requestId}` reads the value from the logging event's MDC; `%thread` displays the name of the thread that emitted the log, not a value from MDC.

An illustrative output line:

```text
INFO  [http-1] requestId=req-42 operation=placeOrder c.e.checkout.OrderService - event=order.received orderId=ord-17
```

**Note:** SLF4J is a facade/API; actual MDC storage and output behavior depend on the MDC adapter and backend. With a provider that does not meaningfully support MDC, calling the MDC API does not guarantee all fields will appear in output. Always verify the active backend and confirm that the encoder/layout actually outputs the context.

### 4.1. MDC is not a global map shared across all threads

`MDC.put` writes to the **current thread's** context. Do not treat `MDC.get("requestId")` as a JVM-wide global setting.

If two threads write:

```text
thread-A: MDC.put("requestId", "req-A")
thread-B: MDC.put("requestId", "req-B")
```

each thread sees its own context under a compliant MDC implementation. One thread does not automatically see another thread's context just because both use the `requestId` key.

### 4.2. `getCopyOfContextMap` and `setContextMap`

SLF4J MDC provides several key APIs:

- `MDC.getCopyOfContextMap()`: returns a **copy** of the calling thread's context map, or `null` if no context is set.
- `MDC.setContextMap(map)`: replaces the current thread's context map by **copying** the provided map.
- `MDC.clear()`: removes all entries for the current thread.
- `MDC.remove(key)`: removes a single key.
- `MDC.putCloseable(key, value)`: creates a convenient scope that removes the key on close; **do not assume it automatically restores a previously overwritten value for the same key**.

Do not pass a shared mutable `Map` and continue modifying it after submitting a task. Capture a snapshot before handing off the task; if you need an immutable snapshot, create a copy such as `Map.copyOf(...)` for non-`null` keys and values.

**Version note:** Starting in SLF4J 2.0, `setContextMap(null)` is accepted by the API; in snippets aiming for broader version compatibility, you can call `MDC.clear()` when the snapshot is `null`.

## 5. Why is context lost when using ExecutorService?

**Illustrative snippet**:

```java
MDC.put("requestId", "req-42");

ExecutorService executor = Executors.newFixedThreadPool(2);
executor.submit(() -> {
    // The worker thread may not have the calling thread's requestId.
    logger.info("event=async.work");
});
```

In this snippet, `MDC.put` runs on the calling thread, while `logger.info` runs on a pool-managed thread. Without an explicit propagation mechanism, you **cannot assume** the worker has the same MDC. This snippet also omits shutdown/cleanup; it is meant to pinpoint where context is lost, **not as a complete standalone program**.

A visual representation:

```text
Thread HTTP-1                        Thread pool-1
MDC: {requestId=req-42}              MDC: {}
    |                                     ^
    +---- submit(Runnable) ---------------+
                                          |
                                    logger.info(...)
                                    requestId is empty
```

`submit` transfers **work**, not the source thread's `ThreadLocal` values. In an executor that reuses threads, the situation can be even more dangerous: if a previous task forgot to clean up, the worker may hold **stale context** rather than simply an empty one.

### 5.1. Does `InheritableThreadLocal` solve this?

`InheritableThreadLocal` can pass a value from a parent thread to a **newly created child thread** via inheritance at thread creation time. It is **not a general solution for thread pools**:

- Pools create or retain threads before a request arrives.
- A single worker processes many different tasks; values inherited at thread creation do not automatically update per submission.
- If a pool happens to create a thread while a request is active, that worker may carry that request's context into subsequent tasks.
- Inheriting a mutable reference can lead to unintended shared state without proper snapshotting.

Therefore, using `InheritableThreadLocal` to "fix" MDC in a thread pool is usually insufficient or unsafe. Propagating context at **task boundaries** or using proper instrumentation/framework support is much clearer and safer.

## 6. Standard workflow: capture → install → execute → restore

A safe model for per-thread context:

```text
Calling thread:
  1. Capture a snapshot of the current context
  2. Submit the work along with the snapshot

Worker thread:
  3. Save the worker's previous context
  4. Install the task's snapshot
  5. Execute the work and emit logs
  6. In finally: restore the previous context or clear
```

Why **restore** instead of simply calling `clear`? If a wrapped task runs inside a scope that already had a valid context (or nested wrappers), blindly clearing can wipe out the outer scope's context. Restoring the prior context preserves proper scoping semantics. In systems that explicitly require workers to be empty after each task, a clear policy can also work, provided it is clearly defined.

### 6.1. SLF4J MDC wrapper example using `Runnable`

```java
import java.util.Map;
import org.slf4j.MDC;

// Called from the thread holding the MDC, at submission time.
Map<String, String> captured = MDC.getCopyOfContextMap();

executor.submit(() -> {
    Map<String, String> previous = MDC.getCopyOfContextMap();
    try {
        if (captured == null) {
            MDC.clear();
        } else {
            MDC.setContextMap(captured);
        }

        logger.info("event=async.work");
        doWork();
    } finally {
        if (previous == null) {
            MDC.clear();
        } else {
            MDC.setContextMap(previous);
        }
    }
});
```

This is a **code snippet** assuming `executor`, `logger`, and `doWork()` are already defined, not a complete Java program. The snapshot is captured **outside the lambda, on the submitting thread**; if you call `MDC.getCopyOfContextMap()` for the first time **inside the worker**, you are reading the wrong thread's context.

Key points:

- `getCopyOfContextMap` creates a copy, so the task is isolated from subsequent MDC changes on the calling thread after submission.
- The wrapper **installs the snapshot before invoking** business logic.
- `finally` runs even if `doWork()` throws an exception, preventing context leaks.
- If the worker previously had a valid outer-scope context, the wrapper restores it.
- Treat the MDC snapshot purely as **diagnostic context**, not as a complete carrier for security, tracing, or transaction state.
- `MDC.setContextMap` replaces the entire map, so do not arbitrarily restore only a single key after installing the whole map.

### 6.2. When a task is cancelled or rejected

If a task **never runs**, the lambda never enters the worker's `finally` block, though it also never installs context onto any worker. However, a snapshot attached to the task object can retain data in memory until the queue releases it; therefore, do not capture sensitive data or oversized objects.

If a task starts running and is interrupted or throws an exception, `finally` remains the core cleanup mechanism. Note that `finally` cannot be guaranteed to run if the JVM crashes abruptly or the process is killed.

### 6.3. Nested MDC scopes and `putCloseable`

If you are inside `requestId=req-A`, and an operation temporarily sets `requestId=req-B` before finishing, you likely want to **restore req-A**. `MDC.putCloseable("requestId", "req-B")` removes the key on close, so it should not be treated as a full restoration stack for a previous value of the same key.

A pattern for a **single key**:

```java
String previous = MDC.get("requestId");
try {
    MDC.put("requestId", "req-B");
    logger.info("event=nested.operation");
} finally {
    if (previous == null) {
        MDC.remove("requestId");
    } else {
        MDC.put("requestId", previous);
    }
}
```

This is an illustrative snippet. For multiple keys or task wrappers, saving and restoring the **entire context map** is usually less error-prone than manipulating individual keys in bulk.

## 7. Standalone Java 17 example with no external dependencies

The following program uses only **JDK 17**, `java.util.logging`, and `ThreadLocal<Map<String,String>>`. It is an example to verify **the thread-bound nature of context**, not a demonstration that JUL has a standard MDC.

The program is designed to show:

1. The `main` thread has `requestId=req-42`.
2. The first task on the thread pool runs **without propagation**, so it prints `requestId=-`.
3. The second task is wrapped with a snapshot, so it prints `requestId=req-42`.
4. After the wrapper finishes and cleans up, the next task on the **same worker** does not see the old `requestId`.
5. The `main` thread retains its own context until its `finally` block cleans it up.

To keep stdout deterministic, the program uses a **synchronous** JUL `Handler` that prints directly to `System.out` and reads the context on the thread calling `Logger.info(...)`. That choice is for demo clarity; do not read `ThreadLocal` inside an asynchronous Handler's output-writing thread, because by then the context may belong to the **writer thread**, not the log-emitting thread.

### 7.1. File `ContextThreadDemo.java`

```java
import java.util.Map;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class ContextThreadDemo {
    private static final ThreadLocal<Map<String, String>> CONTEXT =
            new ThreadLocal<>();
    private static final Logger LOG =
            Logger.getLogger("demo.logging.ContextThreadDemo");

    public static void main(String[] args) throws Exception {
        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.INFO);

        Handler handler = new Handler() {
            @Override
            public synchronized void publish(LogRecord record) {
                if (!isLoggable(record)) {
                    return;
                }
                Map<String, String> context = CONTEXT.get();
                String requestId = context == null
                        ? "-" : context.getOrDefault("requestId", "-");
                System.out.println(Thread.currentThread().getName()
                        + " requestId=" + requestId
                        + " " + record.getLevel().getName()
                        + " " + record.getMessage());
            }

            @Override
            public void flush() {
                System.out.flush();
            }

            @Override
            public void close() {
                flush();
            }
        };
        handler.setLevel(Level.ALL);
        LOG.addHandler(handler);

        ExecutorService executor = Executors.newSingleThreadExecutor(
                task -> new Thread(task, "worker-1"));
        try {
            CONTEXT.set(Map.of(
                    "requestId", "req-42", "operation", "submitOrder"));
            LOG.info("event=main.begin");

            executor.submit(() ->
                    LOG.info("event=worker.no_context")).get();

            Map<String, String> captured = snapshot();
            executor.submit(withContext(captured, () ->
                    LOG.info("event=worker.with_context"))).get();

            executor.submit(() ->
                    LOG.info("event=worker.after_cleanup")).get();
            LOG.info("event=main.end");
        } finally {
            CONTEXT.remove();
            executor.shutdown();
            if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
                executor.shutdownNow();
            }
            LOG.removeHandler(handler);
            handler.close();
        }
    }

    private static Map<String, String> snapshot() {
        Map<String, String> current = CONTEXT.get();
        return current == null ? null : Map.copyOf(current);
    }

    private static Runnable withContext(
            Map<String, String> captured, Runnable work) {
        return () -> {
            Map<String, String> previous = CONTEXT.get();
            try {
                if (captured == null) {
                    CONTEXT.remove();
                } else {
                    CONTEXT.set(captured);
                }
                work.run();
            } finally {
                if (previous == null) {
                    CONTEXT.remove();
                } else {
                    CONTEXT.set(previous);
                }
            }
        };
    }
}
```

### 7.2. Compile and run

In the directory containing `ContextThreadDemo.java`:

```bash
javac ContextThreadDemo.java
java ContextThreadDemo
```

**Exact stdout with JDK 17 under standard execution:**

```text
main requestId=req-42 INFO event=main.begin
worker-1 requestId=- INFO event=worker.no_context
worker-1 requestId=req-42 INFO event=worker.with_context
worker-1 requestId=- INFO event=worker.after_cleanup
main requestId=req-42 INFO event=main.end
```

This program has been **verified to compile with `javac --release 17` and run**, producing the exact output above. No Maven/Gradle or external logging backend is required.

### 7.3. Step-by-step analysis

- `CONTEXT` is a `ThreadLocal` holding a context map per thread.
- `Map.of(...)` and `Map.copyOf(...)` create immutable context maps, preventing the worker from accidentally mutating the calling thread's snapshot. All keys and values in the demo are non-`null`; `Map.copyOf` does not allow null keys or values.
- `newSingleThreadExecutor` ensures tasks run sequentially on the same worker unless an error forces worker replacement; the `ThreadFactory` names the worker `worker-1`.
- `Future.get()` waits for each task to finish before submitting or observing the next one, making the log line order deterministic.
- The first task does not install context on the worker, so `CONTEXT.get()` on the worker returns `null` and prints `-`.
- `snapshot()` is called on the **main thread**, where `req-42` is present.
- `withContext` saves the worker's previous value, installs the snapshot, runs the task, and restores the previous value in `finally`.
- The final worker task does not see `req-42`, verifying **no context leakage between tasks**.
- Finally, `main` still has `req-42` for `event=main.end`; only the `finally` block in `main` clears `main`'s context.

### 7.4. Limitations of the Handler in the demo

The custom Handler reads `Thread.currentThread().getName()` and `CONTEXT.get()` directly inside `publish(LogRecord)`. With a synchronous JUL Handler and the `LOG.info` calls in this example, `publish` executes on the event-emitting thread, so both values are accurate.

**Do not move this Handler as-is into an async logging system** expecting it to record the right context. If a handler queues events and another worker formats them later, `ThreadLocal` on the output thread **may no longer hold the producer's context**. In production, you must **capture context information at the moment the logging event is created**, store it in the event or structured fields, or use a backend/appender that properly supports deferred processing.

Additionally, the Handler uses `record.getMessage()` directly, and the demo does not use JUL message parameters. If you use parameterized messages like `"orderId={0}"`, a full-featured Formatter should call `formatMessage(record)` to substitute parameters. This example is intentionally minimal to demonstrate **context and threads**, not to replace a production Formatter/Encoder.

## 8. Applying this to Spring, Servlet Filters, background jobs, and messaging

### 8.1. HTTP request boundary

A Filter or Interceptor at the request boundary typically:

1. Generates or validates a `requestId`.
2. Stores it in MDC before entering the controller/service.
3. Executes business logic and emits logs.
4. In `finally`, restores or clears MDC after the response completes.

Important caveat: if request processing **continues asynchronously**, the context lifecycle does not always match the synchronous Filter invocation scope. The framework may switch threads or re-dispatch the request. Use the framework's async dispatch and context propagation support so correlation IDs do not disappear or get misattributed.

### 8.2. Scheduled/background jobs

Not every task originates from an HTTP request. A scheduler can generate a `jobId`, `runId`, or `operation` for **each execution**, install the context at the start of the job, and clear/restore it at the end. Do not leave the most recent HTTP `requestId` as a default context for background tasks.

If a job submits subtasks to an executor, you still need to snapshot and propagate context across task boundaries.

### 8.3. Message consumers

Kafka, RabbitMQ, or other queue consumers typically use thread pools and reuse threads. When consuming a message:

- Extract valid correlation/trace IDs from message metadata/headers according to your policy.
- Install context **per message** or per processing unit.
- Log events with `messageId`, `consumerGroup`, and `partition`/`offset` where permitted.
- In `finally`, restore/clear context before processing the next message.
- When sending a task or message to another stage, propagate context through the transport mechanism rather than relying on the source JVM's `ThreadLocal`.

### 8.4. CompletableFuture

`CompletableFuture.supplyAsync(...)` or `runAsync(...)` may execute on a different executor than the calling thread. If no executor is provided, it typically uses `ForkJoinPool.commonPool()` depending on runtime conditions. **Do not assume the calling thread's MDC/ThreadLocal is automatically propagated**.

**Code snippet** example:

```java
Map<String, String> captured = MDC.getCopyOfContextMap();

CompletableFuture<Void> future =
        CompletableFuture.runAsync(() -> {
            Map<String, String> previous = MDC.getCopyOfContextMap();
            try {
                if (captured == null) MDC.clear();
                else MDC.setContextMap(captured);

                logger.info("event=async.completed");
            } finally {
                if (previous == null) MDC.clear();
                else MDC.setContextMap(previous);
            }
        }, executor);

future.join();
```

Assume `logger` and `executor` exist, along with imports for `CompletableFuture`, `Map`, and `MDC`. In real projects with many stages, wrapping every lambda can become hard to maintain; prefer an executor decorator, instrumentation, or framework-supported context propagation.

### 8.5. Reactive pipelines

Reactive execution engines such as Reactor can switch threads multiple times; standard MDC relies on `ThreadLocal`, making it unreliable without explicit integration. Reactive frameworks typically provide their own **subscriber/signal-bound context** or context propagation via instrumentation.

Do not force an entire pipeline onto a single thread just to preserve MDC. Use the official context propagation mechanism of your reactive/tracing stack, and export context when constructing logging events.

## 9. InheritableThreadLocal, thread pools, and anti-patterns

| Technique | Suitable scenario | Risks / Caveats |
| --- | --- | --- |
| `ThreadLocal` | Data scoped to a single thread | Does not automatically transfer to new workers; must be cleaned up |
| `InheritableThreadLocal` | Specific models creating true child threads | Inherited at thread creation, not per pooled task |
| SLF4J MDC | Attaching diagnostic key-value pairs to events | Depends on adapter/backend; must be propagated across thread hops |
| `Map.copyOf` snapshot | Immutable context copy before submission | Rejects null keys/values; avoid secrets or large objects |
| Passing `LogContext` as a parameter | Business logic or tracing needing explicit, testable context | Must be passed through layers or carried by the framework |
| Executor decorator | Many tasks needing uniform propagation | Must wrap `Runnable`, `Callable`, and callbacks consistently |
| Tracing instrumentation | Propagating trace/span across threads/processes/networks | Requires proper framework setup, propagation headers, and sampling |
| Reading ThreadLocal in an async encoder | Not recommended | May read the output thread's context instead of the producer's |

### 9.1. Context should not be a global mutable map

Wrong approach:

```java
static final Map<String, String> CURRENT_REQUEST =
        new HashMap<>();
```

This is an **anti-pattern snippet**. If all requests mutate a single global `HashMap`, threads will contend and overwrite each other's values. Switching to `ConcurrentHashMap` **does not** isolate data per request; it only changes the concurrency characteristics of the shared map.

Instead, use a **dedicated context instance per request/task** or an appropriate framework context carrier, and define clear install/restore boundaries.

### 9.2. Do not mutate a map after submitting a task

Error-prone approach:

```java
Map<String, String> captured = mutableContext;
executor.submit(() -> logWith(captured));
captured.put("requestId", "req-other");
```

This is a **buggy illustrative snippet**. `captured` and `mutableContext` may point to the same object; which value the worker reads depends on timing, and a data race can occur if the map is not thread-safe.

Use an independent snapshot at submission time, such as `Map.copyOf(mutableContext)` if the map contains valid entries and is not being concurrently modified during copying. An even better design is to create an **immutable context from the start** instead of using a shared mutable map.

## 10. Relationship between producer context and AsyncAppender

There are two distinct meanings of "async":

1. **Async business task:** business work moves from thread A to thread B. You must propagate context **before the task emits logs**.
2. **Async logging output:** the event is created on thread B, but the Appender/encoder offloads writing to thread C. The backend must retain a **snapshot of the event's fields** so thread C encodes it accurately without reading thread C's current MDC.

Diagram:

```text
Request thread A
  MDC {requestId=req-42}
        |
        | submit with captured context
        v
Business worker B
  install MDC {requestId=req-42}
  logger.info(...)
        |
        | logging event carries context snapshot
        v
Async logging worker C
  encoder outputs requestId=req-42
        |
        v
stdout/file/collector
```

**If step A→B is missing**, the event will be created with an empty context. Even a properly functioning `AsyncAppender` **cannot reconstruct a `requestId`** that was already lost beforehand.

**If a custom logging handler reads ThreadLocal on C**, it may pick up C's context instead of B's. Standard backends therefore prepare the event before deferred processing—for example, Logback's `AsyncAppender` prepares the necessary data for deferred output. For custom appenders or encoders, verify where data is captured and ensure arguments/structured fields are immutable.

### 10.1. Task context and logging event snapshot are two different layers

- **Task context snapshot:** passed from caller to worker **so the worker knows which request it is processing**.
- **Logging event snapshot:** packages the context at the moment of `logger.info` so the formatter/appender **outputs the exact event that occurred**.

Do not work around a missing snapshot in one layer by blindly disabling async logging. Identify the exact boundary where context is lost and fix propagation or capture there.

### 10.2. The logger's thread name cannot replace trace context

An `AsyncAppender` may have its own output worker thread. If a formatter reads the thread name directly from `Thread.currentThread()` on the output worker, it will observe the output thread. A proper backend should use the **thread name recorded by the logging event at creation time** if it wants to show the originating thread. Likewise, MDC/trace IDs must be captured from the event, never queried from the output worker's `ThreadLocal`.

## 11. Context and distributed tracing

**MDC helps print context**, but **MDC does not automatically propagate traces over HTTP, gRPC, or message brokers**. When service A calls service B, trace context must be transmitted via **headers/metadata** understood by both sides, typically through instrumentation and standards like W3C Trace Context.

Distinguish between:

- `requestId`: ID of a single request/operation per application policy.
- `traceId`: ID of the entire distributed trace.
- `spanId`: ID of a single span, which changes across units of work.
- **MDC:** a convenient place to expose those IDs in logging events.
- **Tracing context carrier:** holds the active span and propagation metadata across executors and network boundaries.

A good tracing setup can automatically populate `traceId`/`spanId` into logs via integration. If you set MDC manually, avoid conflicting with the real tracing context, do not reuse invalid IDs, and do not assume an arbitrary self-generated string is a trace recognized by your collector.

### 11.1. Client-provided correlation IDs must be validated

If you accept `X-Request-ID` or similar metadata from a client:

1. Restrict length and allowed character sets.
2. Never use the raw value to determine file paths, tenant identity, or access permissions.
3. Generate a new internal ID if the input is invalid or untrusted.
4. Never place headers containing tokens or cookies into MDC.
5. Clearly document the relationship between external request IDs and internal trace IDs if both are used.

For authorization decisions, always rely on an authenticated security context—never trust an MDC key simply because it is populated.

## 12. Choosing fields and formatting logs with context

A log schema should standardize essential fields:

| Field | Common type | Purpose |
| --- | --- | --- |
| `timestamp` | ISO 8601 UTC or epoch milliseconds | When the event occurred |
| `level` | String | INFO/WARN/ERROR |
| `logger` | String | Source package/class |
| `thread` | String | Thread that emitted the event |
| `service` | String | Application emitting the event |
| `requestId` | String | Per-request correlation |
| `jobId` | String | Per-background-job correlation |
| `traceId` | String | Distributed trace |
| `spanId` | String | Current span |
| `event` | String | Stable event type |
| `errorCode` | String | Categorized error code |
| `durationMs` | Number | Processing latency |

Traditional MDC stores **String values**. If you want `durationMs` to be an actual number in JSON, use a structured key-value API/encoder that supports typed fields; do not put everything into MDC as Strings and assume the collector will coerce types automatically.

A JSON log example might look like:

```json
{
  "timestamp": "2026-01-12T10:15:00Z",
  "level": "INFO",
  "logger": "com.example.checkout.OrderService",
  "thread": "worker-1",
  "service": "checkout",
  "requestId": "req-42",
  "traceId": "0123456789abcdef0123456789abcdef",
  "spanId": "0123456789abcdef",
  "event": "order.completed",
  "durationMs": 120
}
```

This is **illustrative JSON**, not the default format of every Logback encoder. Choose an encoder capable of emitting fields matching your schema and types. When using `%X{requestId}` in a text `PatternLayout`, it only produces a character string, not a JSON field.

### 12.1. Minimal context is better than oversized context

Do not copy entire request bodies, header maps, `User` objects, Hibernate entities, or security tokens into MDC. Cloning large contexts across thousands of tasks increases memory usage, CPU overhead, event size, and data-exposure risk. Keys like `requestId`, `traceId`, `operation`, and `errorCode` usually offer far higher diagnostic value than uncontrolled payloads.

`requestId` and `traceId` have high cardinality—ideal for looking up specific logs or traces, but you should never create per-ID metric labels or dynamic logger names from them.

## 13. Common issues and how to diagnose them

| Symptom | Possible cause | How to check |
| --- | --- | --- |
| `requestId` present in controller but lost in async task | Context not propagated to worker | Capture before submit, install on worker, restore in `finally` |
| Request B has Request A's `requestId` | Thread pool reused a thread with stale MDC | Verify cleanup on all execution and exception paths |
| One thread mixes multiple `requestId`s | Mutable/global context or overwritten scope | Use isolated snapshots and restore outer scopes |
| `MDC.get` is empty even though thread name is right | Thread name is not MDC; different adapter/provider | Confirm MDC is populated and supported by the backend |
| Context exists in event but missing from layout | Pattern lacks `%X{...}` or JSON encoder omits MDC | Check encoder/layout configuration and field names |
| `CompletableFuture` loses context | Stage runs on a different executor than caller | Wrap each async boundary or use framework propagation |
| `InheritableThreadLocal` gives erratic results | Pool thread was created at an earlier time | Do not rely on inheritance for per-task context |
| MDC used on async writer thread has wrong ID | Reading ThreadLocal on consumer instead of event snapshot | Capture context on producer when emitting the log |
| `MDC.clear()` in wrapper wipes outer context | Previous context not saved before install | Restore previous map in `finally` |
| `putCloseable` does not restore overwritten value | Only removes key on close | Explicitly save/restore previous value or map for nested scopes |
| Trace ID only appears in one service | Headers/metadata not propagated across processes | Check tracing instrumentation and carriers |
| JSON has wrong type/field name for `requestId` | Encoder schema differs from expectations | Inspect raw JSON output and MDC field mapping |
| Task logs missing due to NOP provider | No SLF4J backend binding at runtime | Check SLF4J binding/provider and output target |
| Test logs appear in unpredictable order | Tasks run concurrently without ordering guarantees | Use `Future`/latches in tests; do not assume global ordering |
| Memory grows in long-lived thread pools | `ThreadLocal` not removed or holding large objects | Clean up properly, keep context small/immutable, review lifecycle |
| Logs leak personal data | Too many headers/bodies copied into context | Use a context allowlist and restrict log read access |

### 13.1. Boundary-by-boundary verification workflow

1. **Pick a unique test `requestId`** and identify where it is created/attached.
2. Emit a log **before submission** on the caller thread.
3. Emit a log **at the very start of the worker**, before business logic runs.
4. Verify that the context was captured **on the caller**, not read for the first time inside the worker.
5. Emit a log after installing the snapshot, before calling the service.
6. In `finally`, log or assert that the context is properly restored/cleared and does not leak to the next task.
7. Check the distinction between business executors, listeners, callbacks, and logging `AsyncAppender`s.
8. Inspect the actual output through the real encoder/collector to confirm `requestId` is emitted from the event correctly.
9. If context is still lost across network calls, inspect tracing headers/broker metadata, not just local MDC.

A test with only a single sequential request often misses context leaks; write tests with **interleaved A/B requests on the same pool** and tasks that throw exceptions.

## 14. Anti-patterns to avoid

### 14.1. Calling `MDC.put` only once at server startup

Per-request context is not application-wide configuration. If `requestId` is set on the `main` thread at startup, server worker threads will not automatically receive valid request IDs. Context must be installed at **each request/task boundary**, not once for the entire process.

### 14.2. Clearing context before the task executes

Code can capture **too late**:

```java
MDC.put("requestId", "req-42");
executor.submit(() -> {
    Map<String, String> capturedTooLate =
            MDC.getCopyOfContextMap();
});
MDC.clear();
```

This is a **buggy illustrative snippet**. The worker is reading the worker's own MDC, not the caller's request copy before `clear()`. The right way: capture the snapshot **before `submit`**, then pass that snapshot into the lambda to install.

### 14.3. Omitting `finally` because you assume the task always succeeds

Tasks can throw `RuntimeException`, time out, get interrupted, or return error results. Without `finally`, context can linger on the worker and corrupt subsequent tasks. Context cleanup should be independent of business outcomes.

### 14.4. Using ThreadLocal as a global security context

Do not trust `MDC.get("tenantId")` as proof that a user is authorized to access a tenant. MDC is diagnostic metadata that can be overwritten by application code and has no authentication mechanism. Authorization must rely on an authenticated security context with its own lifecycle and propagation.

### 14.5. Dumping all request fields into MDC

Logging all headers, query strings, cookies, or request bodies increases the risk of token/PII leaks, log injection, bloated log volume, and retention compliance issues. Keep context minimal, validate inputs, and use a field allowlist.

### 14.6. Relying on "every task runs on pool-1-thread-1"

A single worker can still process many tasks, and a single task can hop across threads. Matching thread names do not prove tasks belong to the same request; different thread names do not prove tasks belong to different requests. Use properly propagated correlation IDs.

## 15. Project adoption checklist

- [ ] Standardized `requestId`, `traceId`, `spanId`, `jobId`, and other clear context keys.
- [ ] Logger names remain fixed by class/package; request IDs are never placed in Logger names.
- [ ] Context is attached at **each request/task boundary**, not at startup.
- [ ] `ThreadLocal`/MDC is cleared/restored in `finally` on all success and failure paths.
- [ ] For tasks running on executors, snapshots are captured on the **submitting thread**.
- [ ] Wrappers save the worker's previous context, install the task's context, and restore properly.
- [ ] `InheritableThreadLocal` is not relied upon to solve thread-pool propagation.
- [ ] Solutions are in place for `CompletableFuture`, listeners, and callbacks that actually run on other threads.
- [ ] Reactive pipelines use the framework's official context propagation.
- [ ] Asynchronous log events capture **producer** context and thread name rather than reading `ThreadLocal` on output workers.
- [ ] Verified that the SLF4J provider/backend and layout/encoder actually output required MDC keys.
- [ ] MDC/Context contains only allowlisted keys; no tokens, cookies, bodies, or large objects.
- [ ] Trace context propagates across processes/networks via carriers/instrumentation, not by expecting MDC to cross process boundaries.
- [ ] Tested interleaved A/B requests on the same pool, exception-throwing tasks, and nested scopes.
- [ ] Inspected actual logs in stdout/file/collector to confirm accurate IDs, correct requests, and zero leakage.
- [ ] Evaluated impact on CPU/memory, log size, and sensitive data exposure.

### Technical references

- [Java 17 — ThreadLocal](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ThreadLocal.html): per-thread value storage semantics and `remove()`.
- [Java 17 — InheritableThreadLocal](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/InheritableThreadLocal.html): value inheritance when creating child threads.
- [Java 17 — ExecutorService](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html): task management and execution mechanisms.
- [SLF4J MDC Javadoc](https://www.slf4j.org/api/org/slf4j/MDC.html): `getCopyOfContextMap`, `setContextMap`, `clear`, `remove`, `putCloseable`.
- [Logback Manual — Mapped Diagnostic Context](https://logback.qos.ch/manual/mdc.html): MDC and context behavior with Executor-managed threads.
- [Logback Manual — Appenders](https://logback.qos.ch/manual/appenders.html): logging output and `AsyncAppender`.
- [W3C Trace Context](https://www.w3.org/TR/trace-context/): propagating trace context across distributed systems.

**Conclusion:** **Context and threads** are closely related, but they are not the same thing. `ThreadLocal`/MDC lets a thread attach `requestId` and metadata to logs; when work crosses into thread pools, `CompletableFuture`, or reactive pipelines, context can be **lost or leaked to other tasks** if not propagated and cleaned up properly. The key rule to remember is **capture on the source thread → install in the worker → execute → restore in `finally`**, while encoders/`AsyncAppender`s must use the context captured inside the logging event. When investigating across services, use tracing propagation to connect steps rather than relying on thread names or MDC alone.
