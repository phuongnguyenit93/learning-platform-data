# Thread Context When Logging in Java

## 1. What Is Thread Context?

When multiple requests run concurrently, log lines from different threads are often interleaved. Seeing only messages like "Starting processing", "Calling database", or "Completed" makes it hard to tell which request each line belongs to. A **logging context** is the set of metadata attached to a unit of work (a request, task, or transaction) so that related log lines can be correlated.

Examples of common fields:

| Field | Purpose | Notes |
| --- | --- | --- |
| `requestId` | Identifies a specific HTTP request or unit of work | Generate or validate the value at the request-entry boundary |
| `traceId`, `spanId` | Links logs to a trace/span in a distributed observability system | Managed by a tracing library; requires a mechanism to propagate across the network |
| `operation`, `component` | Indicates the operation or component currently handling the work | Keep values short and meaningful |
| `thread` / thread name | Helps identify the thread emitting the log | A thread in a pool can process multiple requests sequentially |

Illustrative example:

```text
[http-worker-1] requestId=req-101 INFO Starting processing
[http-worker-2] requestId=req-102 INFO Starting processing
[http-worker-1] requestId=req-101 INFO Data saved
[http-worker-2] requestId=req-102 INFO Data saved
```

Although the two requests interleave, they remain distinguishable via `requestId`. **The thread name only tells you where the log statement executed at that moment; it is not the request identifier.** "Thread context" in this article refers to diagnostic data for logging, not `Thread.State`, the context class loader, or application-wide business state.

## 2. Underlying Mechanism: `ThreadLocal<T>`

`ThreadLocal<T>` gives each thread its own independent value for the same `ThreadLocal` variable: if thread A calls `set(x)`, thread B does not automatically see `x` when calling `get()`. Its primary API consists of `set(value)`, `get()`, and `remove()`. Because of this, `ThreadLocal` is commonly used to hold information that needs to appear across multiple methods called sequentially on **the same thread**, without passing extra parameters through every method signature.

Two lifecycles must be distinguished:

- **Thread lifecycle:** a thread in an `ExecutorService` can be long-lived and execute many tasks.
- **Context lifecycle:** a `requestId` is typically valid only for a single request or task, after which it must be cleaned up.

### Standalone Java 17+ Example

File `ThreadContextDemo.java`:

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class ThreadContextDemo {
    private static final ThreadLocal<String> REQUEST_ID = new ThreadLocal<>();

    private static void log(String step) {
        System.out.printf("[%s] requestId=%s | %s%n",
                Thread.currentThread().getName(), REQUEST_ID.get(), step);
    }

    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor(
                task -> new Thread(task, "worker-1"));

        try {
            REQUEST_ID.set("req-42");
            log("receive");

            pool.submit(() -> log("without-propagation")).get();

            String captured = REQUEST_ID.get();
            pool.submit(() -> {
                String previous = REQUEST_ID.get();
                try {
                    if (captured == null) {
                        REQUEST_ID.remove();
                    } else {
                        REQUEST_ID.set(captured);
                    }
                    log("with-propagation");
                } finally {
                    if (previous == null) {
                        REQUEST_ID.remove();
                    } else {
                        REQUEST_ID.set(previous);
                    }
                }
            }).get();

            pool.submit(() -> log("after-cleanup")).get();
        } finally {
            REQUEST_ID.remove();
            pool.shutdown();
        }
    }
}
```

Run with JDK 17 or later:

```bash
javac ThreadContextDemo.java
java ThreadContextDemo
```

Stdout output (tasks are awaited in order via `get()`; the pool thread has a fixed name):

```text
[main] requestId=req-42 | receive
[worker-1] requestId=null | without-propagation
[worker-1] requestId=req-42 | with-propagation
[worker-1] requestId=null | after-cleanup
```

Explanation:

1. The `main` thread holds `req-42` in its own `REQUEST_ID`.
2. The task submitted to `worker-1` **does not automatically inherit** `main`'s `ThreadLocal` value.
3. The program explicitly captures the value on the submitting thread, sets it on the receiving thread before logging, and restores the previous value in `finally`.
4. The subsequent task reusing `worker-1` sees `null`, proving that the previous request did not leak context into the next one.

This example intentionally uses plain Java `ThreadLocal` to illustrate the underlying principle. In an application with a logging framework, use the framework's MDC API to attach diagnostic fields to logs; do not build a full-featured logging mechanism solely from this example.

## 3. MDC: Putting Context into Log Lines

**MDC (Mapped Diagnostic Context)** is a mechanism for storing diagnostic key–value pairs associated with the current execution context. In the SLF4J ecosystem, the `org.slf4j.MDC` class provides the familiar operations:

| API | Meaning |
| --- | --- |
| `MDC.put("requestId", id)` | Sets or replaces a value in the current context |
| `MDC.get("requestId")` | Retrieves a single value |
| `MDC.remove("requestId")` | Removes a key |
| `MDC.clear()` | Clears the current context |
| `MDC.getCopyOfContextMap()` | Returns a snapshot copy of the fields; may be `null` |
| `MDC.setContextMap(map)` | Replaces the current context with a copied map |

SLF4J's `MDC` is a facade; actual storage and log output behavior depend on the underlying **logging backend** (for example, Logback). In typical usage with Logback, MDC is a thread-local context included in log records when the logger creates an event. Do not assume every backend shares the same inheritance rules or automatically propagates context across threads. The application must have both the SLF4J API and a properly configured backend; without a supporting backend, calling MDC does not guarantee that fields will appear in the output.

### Setting at the Start of a Request, Restoring at the End

Below is an illustrative class that can be placed in a Java application using SLF4J and Logback, where `process` is called from the request-entry point:

```java
import java.util.Map;
import java.util.Objects;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;

public final class PaymentLogger {
    private static final Logger LOG = LoggerFactory.getLogger(PaymentLogger.class);

    public void process(String requestId) {
        Objects.requireNonNull(requestId, "requestId");
        Map<String, String> previous = MDC.getCopyOfContextMap();
        try {
            MDC.put("requestId", requestId);
            MDC.put("component", "payment");

            LOG.info("Bắt đầu xử lý thanh toán");
            LOG.info("Hoàn tất xử lý thanh toán");
        } finally {
            restore(previous);
        }
    }

    private static void restore(Map<String, String> context) {
        if (context == null) {
            MDC.clear();
        } else {
            MDC.setContextMap(context);
        }
    }
}
```

`previous` holds the entire context that existed before the call. This restoration pattern is important when `process` is called nested inside another scope that already has `requestId` or other MDC keys. Unconditionally calling `clear()` could wipe out the caller's context. At the outermost boundary, if no context existed beforehand, `restore(null)` cleans up the newly set values. `finally` runs even if processing throws an exception.

### Configuring Logback to Print MDC

With Logback, an example `src/main/resources/logback.xml`:

```xml
<configuration>
    <appender name="STDOUT" class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%d{HH:mm:ss.SSS} [%thread] %-5level requestId=%X{requestId} component=%X{component} %logger{32} - %msg%n</pattern>
        </encoder>
    </appender>
    <root level="INFO">
        <appender-ref ref="STDOUT"/>
    </root>
</configuration>
```

`%thread` prints the thread name; `%X{requestId}` and `%X{component}` pull fields from the MDC; `%msg` is the message body. When `process("req-42")` is called, both log lines from the method carry `requestId=req-42` and `component=payment`; timestamp, log level, and logger name remain formatted by Logback. If a field has not been set, the MDC placeholder is typically empty. This pattern syntax is specific to **Logback**; when using Log4j2, refer to its corresponding configuration and `ThreadContext` API.

MDC is useful because every class calling `LOG.info(...)` does not have to accept `requestId` and concatenate it into every message string. However, MDC is strictly **diagnostic information**: do not use it as a source of business data, access-control decisions, or a substitute for required method parameters.

## 4. Across Thread Boundaries: Propagate Context Deliberately

A common scenario: an HTTP request-handling thread sets the MDC and then calls `executor.submit(...)`, `CompletableFuture.runAsync(...)`, or an asynchronous callback. The task may run on a different thread, which has its own MDC. Ignoring this boundary can cause async logs to miss `requestId` or, worse, carry stale context left behind in an uncleaned thread pool.

An explicit propagation approach has four steps: **capture a snapshot at submission time → save the previous context on the receiving thread → install the snapshot and run the task → restore in `finally`**. Never share a single mutable `Map` across multiple requests.

### Integration Example with SLF4J MDC and `CompletableFuture`

The `MdcPropagationExample.java` file below runs in a project that has the SLF4J dependency and a Logback backend configured as shown above:

```java
import java.util.Map;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;

public final class MdcPropagationExample {
    private static final Logger LOG =
            LoggerFactory.getLogger(MdcPropagationExample.class);

    private static void restore(Map<String, String> context) {
        if (context == null) {
            MDC.clear();
        } else {
            MDC.setContextMap(context);
        }
    }

    private static Runnable withCapturedMdc(Runnable task) {
        Map<String, String> captured = MDC.getCopyOfContextMap();

        return () -> {
            Map<String, String> previous = MDC.getCopyOfContextMap();
            try {
                restore(captured);
                task.run();
            } finally {
                restore(previous);
            }
        };
    }

    public static void main(String[] args) {
        ExecutorService executor = Executors.newSingleThreadExecutor(
                task -> new Thread(task, "log-worker"));
        Map<String, String> original = MDC.getCopyOfContextMap();

        try {
            MDC.put("requestId", "req-42");
            LOG.info("Nhận yêu cầu");

            CompletableFuture<Void> future = CompletableFuture.runAsync(
                    withCapturedMdc(() -> LOG.info("Xử lý async")),
                    executor);
            future.join();
        } finally {
            restore(original);
            executor.shutdown();
        }
    }
}
```

With the pattern above, both log lines will include `requestId=req-42`, one from `main` and one from `log-worker`. Timestamps and logger-name formatting vary by configuration; this is a **behavioral illustration**, not fixed stdout like the `ThreadContextDemo` example.

Key points to understand:

- `withCapturedMdc(...)` is called **on the submitting thread**, so the snapshot reflects the context at task creation time; placing the call inside the worker lambda would capture the worker's context by mistake.
- `restore(captured)` also handles an empty snapshot, preventing the task from accidentally inheriting stale context already present on the pool thread.
- `restore(previous)` in `finally` returns the receiving thread to its exact state before execution, even if the task throws an exception.
- `CompletableFuture` only manages completion and result values; it does not by itself promise to copy MDC. Subsequent stages—especially `*Async` stages—also need appropriate context propagation.
- The wrapper above illustrates `Runnable`. For `Callable<T>` or `Supplier<T>`, apply the same snapshot/restore principle or use integrations provided by your framework or tracing library so no execution path is missed.

If your application already has framework-provided context propagation (such as a task decorator or observability instrumentation), prefer configuring it consistently at executor boundaries rather than having each team write slightly different wrappers.

## 5. Request Context Does Not Equal Thread Context

Consider a processing flow:

```text
HTTP request req-42
    |
    v
Thread A: set MDC, log
    |
    +--> Executor / CompletableFuture --> Thread B: must transfer MDC
    |
    +--> HTTP call to another service --> must propagate trace/request headers
    |
    v
End of request: restore or clear MDC on Thread A
```

- **Switching threads within the same JVM:** `ThreadLocal`/MDC is bound to the current thread, so data must be transferred explicitly where tasks are handed off.
- **Crossing process/service boundaries over HTTP or message queues:** JVM MDC does not travel over the network automatically. You need a propagator for trace context or the corresponding headers; the receiving service reads, validates, and populates the required fields into its own logging context.
- **Distributed tracing:** `traceId`/`spanId` have their own semantics and lifecycle. OpenTelemetry or a tracing tool manages the trace context and can integrate with MDC to expose these IDs. Manually putting a `traceId` key into MDC does not create a span or propagate a trace to another service.
- **Reactive/asynchronous pipelines:** in Reactor or pipelines where a single unit of work may hop across multiple threads, use the framework's context mechanism and context-propagation integration; do not assume the entire pipeline stays on one thread.
- **`InheritableThreadLocal`:** only initializes a child thread's value at thread-creation time; it is not a mechanism for propagating context each time a task is submitted to an existing executor thread. It does not solve thread-pool reuse and requires checking specific inheritance semantics.
- **Virtual threads (Java 21+):** support `ThreadLocal`, but it remains thread-bound data, not implicitly the context of a distributed chain of tasks. Avoid holding large maps or objects per virtual thread, and still clean up within the proper scope.

When a request fans out into multiple parallel branches, taking a snapshot at the right moment gives all branches the same correlation ID without sharing a mutable map. If one branch needs an extra branch-specific field (such as `operation`), add it within that branch's scope and restore before exiting.

## 6. Common Pitfalls and How to Fix Them

| Symptom | Common Cause | How to Fix |
| --- | --- | --- |
| Async logs lose `requestId` | Task runs on a different thread | Capture/propagate context at the submission boundary and restore after the task |
| Request B shows Request A's ID | Thread pool reuses a thread with leftover MDC | Use `try/finally` with snapshot and restore/clear at every entrypoint |
| Nested method wipes out outer context | Calling `MDC.clear()` when the inner method finishes | Save the map before modifying and restore the previous map |
| Logs only show `pool-...`, hard to correlate requests | Worker name does not identify the unit of work | Use `requestId`/`traceId` consistently |
| `traceId` appears in logs but services cannot be linked | Only decorating logs, not propagating over the network | Use a real trace-context propagator and instrumentation |
| Logs expose tokens or customer data | Sensitive data placed into MDC | Store only approved fields; control sources and formatting |
| Context memory grows over time | Long-lived threads retain references via `ThreadLocal`, or context is too large | Clean up in `finally`; keep only a few short required strings in MDC |

A useful testing habit: run two requests sequentially on **the same single-worker thread pool** with different IDs, verify that each request's logs carry the right ID, and confirm that a subsequent context-free task no longer sees the old ID. Also test an exception-throwing path to ensure `finally` still restores the context. For async flows, check logs both before and after thread hops. For distributed systems, verify the actual trace/headers on the receiving service.

## 7. Project Rules to Apply

1. **Set context at ingress boundaries** (HTTP filters/interceptors, message consumers, job runners) after generating or validating a valid ID. Use tracing IDs that contain no sensitive data; avoid blindly trusting arbitrary client-sent headers.
2. **Log in a structured way with consistent keys** (such as `requestId`, `traceId`, `spanId`) across layers. Include the thread name in the pattern if needed, but never use it in place of a work-unit ID.
3. **Propagate context at every execution-environment boundary:** executors, `CompletableFuture`, scheduled jobs, message handlers, and network boundaries. Use library support when available to avoid boilerplate and missed paths.
4. **Bound the lifecycle with `try/finally`;** restore the previous context so nested calls remain safe. Never store a single fixed ID in a static field shared across requests.
5. **Never put passwords, tokens, cookies, personal data, or large objects into MDC.** MDC is for diagnostics; business data and authorization must be passed and checked through dedicated mechanisms.

**Remember:** a thread is where execution happens, while a request/task is the unit you need to track. MDC puts diagnostic data into the current thread's logs; to preserve correlation across async hops or services, the application must propagate context at the right boundaries and always clean up after use.
