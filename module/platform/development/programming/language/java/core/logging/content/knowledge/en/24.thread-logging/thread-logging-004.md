# Logging in Virtual Threads (Java 21+)

## 1. Goal and Context

A **virtual thread** is a `java.lang.Thread` managed by the JVM, standardized since Java 21 (JEP 444). It is well-suited for tasks with heavy I/O waiting, such as handling HTTP requests, calling services, and querying databases. A virtual thread can pause (unmount) from its **carrier thread** (the platform thread executing it) and later resume on a different carrier. This increases concurrency for many waiting tasks, without making the CPU execute individual instructions any faster.

Logging in virtual threads still works with `java.util.logging` (JUL), SLF4J + Logback, Log4j 2, or compatible frameworks. The key considerations lie in **task identity**, **request context**, **log ordering**, and **logging overhead** when a very large number of virtual threads are running.

After this lesson, you will be able to:
- Log from virtual threads using Java 21+ and check `Thread.currentThread().isVirtual()`.
- Attach `requestId`/`traceId` to correlate logs belonging to the same business flow without relying on the carrier.
- Understand when MDC/`ThreadLocal` is preserved and when context must be propagated to a new virtual thread.
- Identify issues related to synchronous logging, sensitive data, task failures, and pinning depending on the JDK version.

## 2. Which Thread Actually Appears in the Log?

In code running on a virtual thread, `Thread.currentThread()` returns the **task's virtual thread**. When the JVM unmounts and remounts it onto another carrier, the `Thread` instance and the `ThreadLocal` data attached to that virtual thread still belong to the same task.

Distinguish three types of information:

| Information | Meaning | How to Use in Logs |
| --- | --- | --- |
| `Thread.currentThread().getName()` | Name of the thread running the code; virtual threads may have no name by default | Useful for diagnostics if explicitly named |
| `Thread.currentThread().isVirtual()` | `true` when code is running on a virtual thread | Used to verify the runtime environment during testing |
| `requestId`, `traceId`, `spanId` | Identifier of the request or business execution | Used to search and correlate related logs; preferred in production |

Do not use the **carrier thread** name/ID as a request identifier: one carrier can serve multiple virtual threads, and one virtual thread can resume on a different carrier. Similarly, a virtual thread ID does not replace `requestId` because a single request can spawn multiple subtasks.

`Executors.newVirtualThreadPerTaskExecutor()` creates a **new virtual thread for each task**; it is not a pool that reuses virtual threads. You can assign names when creating a custom factory with `Thread.ofVirtual().name("req-vt-", 0).factory()`. Thread names help with debugging, but you should keep `requestId`/`traceId` in every log record for business correlation.

## 3. Standalone Java 21+ Example: Logging from Two Virtual Threads

This example uses only the Java Development Kit, with no external dependencies. Each task receives an explicit `requestId`; JUL's `ConsoleHandler` is configured to print a simple message.

Create the file **`VirtualThreadLoggingDemo.java`**:

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.ThreadFactory;
import java.util.logging.ConsoleHandler;
import java.util.logging.Formatter;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class VirtualThreadLoggingDemo {
    private static final Logger LOG =
            Logger.getLogger(VirtualThreadLoggingDemo.class.getName());

    static {
        LOG.setUseParentHandlers(false); // Avoid duplicate output from the default handler.
        ConsoleHandler handler = new ConsoleHandler();
        handler.setFormatter(new Formatter() {
            @Override
            public String format(LogRecord record) {
                return record.getMessage() + System.lineSeparator();
            }
        });
        LOG.addHandler(handler);
    }

    public static void main(String[] args) throws Exception {
        ThreadFactory factory =
                Thread.ofVirtual().name("req-vt-", 0).factory();

        try (ExecutorService executor =
                     Executors.newThreadPerTaskExecutor(factory)) {
            Future<?> first = executor.submit(() -> handle("req-101"));
            Future<?> second = executor.submit(() -> handle("req-102"));

            // get() waits and wraps task failures as ExecutionException.
            first.get();
            second.get();
        }
    }

    private static void handle(String requestId) {
        Thread current = Thread.currentThread();
        LOG.info(() -> "requestId=" + requestId
                + " thread=" + current.getName()
                + " virtual=" + current.isVirtual()
                + " event=handled");
    }
}
```

Compile and run with JDK 21 or later:

```bash
javac VirtualThreadLoggingDemo.java
java VirtualThreadLoggingDemo
```

**One possible output** (the two lines may appear in swapped order because the two tasks run concurrently):

```text
requestId=req-101 thread=req-vt-0 virtual=true event=handled
requestId=req-102 thread=req-vt-1 virtual=true event=handled
```

Explanation:
1. The factory creates virtual threads named `req-vt-0`, `req-vt-1`.
2. `executor.submit` launches both tasks; completion order or log output order is not guaranteed.
3. `Future.get()` lets `main` wait for and receive exceptions thrown in the tasks. When exiting the `try` block, the executor is closed.
4. `LOG.info(Supplier<String>)` only builds the string when the corresponding log level is enabled. The example customizes the formatter for readability; real-world systems typically use a shared formatter/JSON layout with timestamp and level.

`ConsoleHandler` writes to standard error (stderr) by default; therefore, if you redirect stdout and stderr to two separate files, you will see the two lines in stderr. This example demonstrates how to attach context, not a benchmark.

## 4. Correlating Logs by Request: Passing Parameters or Using MDC?

### 4.1. Passing Context Explicitly

The simplest and most verifiable approach is to pass `requestId`, `traceId`, or an immutable context object as a parameter across methods:

```java
void processOrder(String requestId, String orderId) {
    log.info("requestId={} event=order_started orderId={}",
             requestId, orderId);
    // Invoke business steps, continuing to pass requestId if needed.
}
```

The snippet above illustrates **SLF4J**, which requires an `org.slf4j.Logger` and a corresponding backend; it is not a standalone program. The `{}` placeholder is SLF4J's parameterized logging mechanism, avoiding unnecessary eager string concatenation. In deeply layered systems, passing context via parameters is explicit, though it can lengthen parameter lists.

### 4.2. Thread-Scoped Data with MDC

**Mapped Diagnostic Context (MDC)** allows setting key-value pairs such as `requestId` and `traceId`, and having the log layout print them alongside the message. With SLF4J/Logback, commonly used APIs are `MDC.put`, `MDC.getCopyOfContextMap`, `MDC.setContextMap`, and `MDC.clear`. For example, a Logback configuration can use `%X{requestId}` in a pattern, while a JSON layout can emit a dedicated `requestId` field.

It is important to distinguish:
- **Same virtual thread:** `ThreadLocal`-based context stays attached to the virtual thread across unmount/remount; the JVM switching carriers does not cause MDC to be lost.
- **Creating a new virtual thread or submitting a task to an executor:** do not assume by default that the calling thread's MDC will appear on the new thread. Context propagation depends on the MDC adapter/framework and its configuration; you should explicitly capture and restore the context.
- **End of scope:** you must clear or restore MDC to avoid retaining stale data, leaking wrong context in reused code, and consuming unnecessary memory.

Example helper for propagating MDC across an executor boundary (using **SLF4J 2.x**, with `org.slf4j.MDC`; this is a method snippet meant to be integrated into an application already configured with SLF4J):

```java
import java.util.Map;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Future;
import org.slf4j.MDC;

static <T> Future<T> submitWithMdc(
        ExecutorService executor, Callable<T> task) {

    // Capture context on the calling thread before submitting.
    Map<String, String> captured = MDC.getCopyOfContextMap();

    return executor.submit(() -> {
        Map<String, String> previous = MDC.getCopyOfContextMap();
        try {
            if (captured == null) {
                MDC.clear();
            } else {
                MDC.setContextMap(captured);
            }
            return task.call();
        } finally {
            // Restore the executing thread's context, even if the task throws an exception.
            if (previous == null) {
                MDC.clear();
            } else {
                MDC.setContextMap(previous);
            }
        }
    });
}
```

A typical usage is: at the start of a request call `MDC.put("requestId", requestId)`; call `submitWithMdc(executor, task)`; after waiting on `Future.get()`, use `finally` to call `MDC.remove("requestId")` (or restore the previous context if inside a nested scope). This is **manual context propagation**. If you use a web framework, OpenTelemetry, or a context-propagation library, check their mechanism and version to avoid double propagation, missing async branches, or generating incorrect traces.

In systems with a very large number of virtual threads, keep only a few small, essential MDC keys. Avoid storing large objects, connection caches, entities, or request payloads in `ThreadLocal`: each virtual thread has its own storage, and the number of threads can be very high. If MDC is not needed, passing an immutable context as a parameter is often easier to manage in terms of memory and lifecycle.

## 5. Logging Correctly Under Errors and Concurrency

### Do Not Confuse Log Line Order with Business Order

Two tasks can execute in parallel; you cannot infer that `req-101` finished before `req-102` solely from the order of log lines. The time a log is recorded, the time an event occurs, and the time it is shipped to a central system can all differ, especially with async appenders.

To reconstruct the event flow:
- Log `timestamp`, `level`, `logger`, `service`, `event`, and `requestId`/`traceId` consistently.
- Include `durationMs` for steps that need measurement, `spanId` if tracing is used, and stable error codes.
- When comparing timestamps across multiple machines, use synchronized clocks; do not rely solely on the order of appearance in the console or log collector.

### Preserve Exceptions

Do not log only `e.getMessage()` or `e.toString()` when you need stack traces for diagnostics. With JUL, pass the exception as the throwable parameter:

```java
try {
    performWork();
} catch (Exception ex) {
    LOG.log(java.util.logging.Level.SEVERE,
            "requestId=req-101 event=work_failed", ex);
    throw ex;
}
```

`performWork()` is a placeholder business method, so this is an **illustrative snippet**, not a standalone program. With SLF4J, the equivalent is `log.error("requestId={} event=work_failed", requestId, ex)`. If using `executor.submit`, the exception is captured inside the `Future`; call `get()` or an equivalent result-handling mechanism so errors are not silently lost. With `Thread.ofVirtual().start(...)`, uncaught exceptions go through `UncaughtExceptionHandler` following standard thread rules.

### Data Safety

Do not log passwords, access tokens, session cookies, API keys, payment details, or full request bodies. When personal data is present, apply redaction according to your system's policy. Use identifiers sufficient to correlate logs and traces; avoid using sensitive data as virtual thread names.

## 6. Performance: Cheap Virtual Threads Do Not Mean Cheap Logging

Being able to create a vast number of virtual threads does **not** make string formatting, appender locking, file/console/network I/O, or log ingestion free. Bottlenecks usually lie in log volume and the log-receiving pipeline.

| Symptom | Common Cause | Mitigation |
| --- | --- | --- |
| Throughput drops when DEBUG is enabled | Formatting/allocating too many messages; increased I/O | Lower log level, use parameterized/lazy logging, re-measure |
| Many threads waiting to write to console/file | Appender or I/O target under contention/lock | Inspect backend, use appropriate batching/async appender, reduce hot-path logging |
| Heap grows when storing context | MDC/`ThreadLocal` holding large data across many virtual threads | Keep context small, clean up in `finally`, bound payload sizes |
| Logs dropped under higher load | Async queue full, drop/overwrite policy, or premature shutdown | Monitor queue/drop metrics, configure backpressure and flush on shutdown |
| Missing `requestId` in a subtask | Context not propagated across executor boundary | Pass parameters or snapshot/restore MDC |
| Log lines out of `submit` call order | Concurrent scheduler and appender | Correlate by ID/event/timestamp; do not rely on display order |

**Synchronous logging** is easy to reason about but can cause tasks to wait on locks or I/O. **Asynchronous logging** reduces wait time on business threads in some scenarios, but introduces queues, extra latency, and the risk of losing logs during overload or abrupt process termination. You need clear policies for full queues, mandatory log levels, and flush/shutdown behavior; benchmark with a realistic workload before choosing.

Do not create a small fixed pool of virtual threads just to throttle logging or request rate: each task should have its own virtual thread. If you need to bound concurrent access to a limited resource, use mechanisms such as `Semaphore` or limits at the resource itself, and monitor wait times.

### Pinning Depends on the JDK Version

On **JDK 21–23**, a virtual thread can become *pinned* to its carrier when blocking inside `synchronized` blocks or native/foreign code; if logging operations cause long waits inside such sections, scalability can degrade. **JDK 24** (JEP 491) changed synchronization to eliminate most pinning caused by `synchronized`; native/foreign cases still require evaluation. Do not attribute every logging delay to pinning, and do not mechanically apply JDK 21 diagnostics to newer JDKs.

You can use Java Flight Recorder (JFR), thread dumps, and appender latency/queue metrics to identify root causes. On JDK 21, the `jdk.VirtualThreadPinned` event helps detect pinning occurrences exceeding a configured threshold; on other JDKs, check which events that version supports. Also monitor log write latency, log generation rate, drop rate, and CPU/heap usage.

## 7. Common Pitfalls and Self-Check

1. **Blank thread column in logs:** virtual threads created by default may have an empty name. Set bounded names when debugging is genuinely needed; always include `requestId`/`traceId`.
2. **Assuming MDC automatically follows every subtask:** `ThreadLocal` belongs to an individual thread, not the entire request. Check `submit` sites, callbacks, and executors.
3. **Putting the entire request into `ThreadLocal` to avoid passing parameters:** easily retains large objects across tens of thousands of tasks. Keep only compact keys and clean up scopes.
4. **Using `System.out.println` instead of a logger in production:** lacks log levels, structure, and configuration, and can cause console contention.
5. **Logging by carrier ID:** the carrier is an execution detail, not a business identifier.
6. **Ignoring `Future.get()`:** a task may throw an exception while the calling thread never inspects the result.
7. **Enabling DEBUG system-wide and concluding virtual threads are slow:** measure log generation/writing overhead separately and compare against a baseline.

**Practice exercise:** run the example in Section 3 multiple times to observe the order of log lines; remove `.name("req-vt-", 0)` to see the default thread names; add a third task and pass a distinct `requestId`; finally, switch the configuration to structured JSON logging or Logback MDC and verify that every line contains the task's ID. When migrating from JUL to SLF4J, keep the business logic the same while updating the logger API and backend configuration appropriately.

## 8. Key Takeaways

- Virtual threads are real `Thread` instances to logging code; `Thread.currentThread()` still points to the right virtual thread after the JVM switches carriers.
- Prefer business identifiers (`requestId`, `traceId`) over thread names or IDs.
- MDC/`ThreadLocal` can survive a virtual thread park/unpark; when spawning another thread, you must handle context propagation explicitly.
- Many virtual threads can produce a massive volume of logs. Design log levels, formatting, queues, backpressure, and security as bounded resources.
- For pinning issues, check the **exact JDK version** and JFR/appender metrics before drawing conclusions.

### References

- Oracle, *Virtual Threads* (Java 21): https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html
- OpenJDK, *JEP 444: Virtual Threads*: https://openjdk.org/jeps/444
- OpenJDK, *JEP 491: Synchronize Virtual Threads without Pinning*: https://openjdk.org/jeps/491
- SLF4J, *MDC API*: https://www.slf4j.org/api/org/slf4j/MDC.html
- SLF4J, *User Manual*: https://www.slf4j.org/manual.html
