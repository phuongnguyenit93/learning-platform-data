# Thread ID in Java Logging

## 1. What Is a Thread ID?

**Thread ID** is the numeric identifier of a `java.lang.Thread` object in the JVM. When multiple threads write logs concurrently, the `threadId` field helps identify **which Java thread executed the logging statement**. This is critical diagnostic information when tracing event ordering, concurrency bugs, resource contention, and thread pools.

Key properties to remember:

- The ID is a positive `long` value, assigned by the JVM when a `Thread` is created, and remains unchanged for the lifetime of that thread.
- Live threads have distinct IDs within the same JVM. Do not use the ID as a global identifier across multiple JVMs, containers, or application restarts; do not rely on the assumption that an ID is never reused permanently.
- `threadId` and `threadName` are two different fields. Names can be duplicated, changed, and carry descriptive meaning; the ID is a number used to distinguish threads.
- A Java Thread ID is **not guaranteed to match** the operating system thread ID (OS TID). Do not correlate IDs in Java logs directly with `top -H`/`ps -L` or OS tools without first determining how they map.
- The ID only answers the question "which thread ran this code?". A single HTTP request, message, or transaction may span multiple threads; a single thread in a pool may process many requests over time.

Example of a useful log structure:

~~~text
2026-11-10T09:40:00Z level=INFO service=checkout instance=checkout-2 threadId=37 threadName=worker-2 traceId=8f2a... event=payment_start
~~~

In this example, `threadId=37` is an illustrative ID, not a fixed value. `traceId` links events belonging to the same business operation; `threadId` describes the execution context of **each** individual event.

## 2. Getting the ID of the Current Thread

| Java Version | Recommended API | Notes |
| --- | --- | --- |
| Java 17–18 | `Thread.currentThread().getId()` | Returns `long`; works with Java 17 programs. |
| Java 19+ | `Thread.currentThread().threadId()` | `final` API added in Java 19; preferred for new code. |
| Java 19+ with legacy code | `getId()` still exists | `Thread.getId()` was marked deprecated in Java 19 because subclasses can override it; avoid in new code now that `threadId()` is available. |

Example snippet inside a method running on Java 17:

~~~java
Thread current = Thread.currentThread();
long id = current.getId();
String name = current.getName();
System.out.printf("threadId=%d threadName=%s%n", id, name);
~~~

On Java 19+, replace the ID retrieval line with:

~~~java
long id = Thread.currentThread().threadId();
~~~

**You must capture the ID at the point where the event occurs.** If on the `main` thread you call `worker.getId()`, you get the ID of the `worker` object, not the ID of the `main` thread doing the logging. Use `Thread.currentThread()` to attach the ID of the thread actually executing the statement.

Do not assume IDs start at 1, are sequential, or that ID order reflects the order in which work was processed. Do not cast `long` to `int`; `int` may not be large enough to hold the ID value.

## 3. Logging Thread ID with java.util.logging (Java 17, No External Libraries)

In JUL (Java Util Logging), each `LogRecord` records the ID of the thread that emitted the event. Starting in Java 16, use `LogRecord.getLongThreadID()` to obtain the proper `long` value when building a formatter. The `LogRecord.getThreadID()` API returning `int` was deprecated in Java 16 and may return a synthetic value that differs from the actual Java Thread ID.

Create the file **ThreadIdLoggingDemo.java**:

~~~java
import java.util.logging.ConsoleHandler;
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class ThreadIdLoggingDemo {
    private static final Logger LOG =
            Logger.getLogger(ThreadIdLoggingDemo.class.getName());

    public static void main(String[] args) throws InterruptedException {
        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.INFO);

        ConsoleHandler handler = new ConsoleHandler();
        handler.setLevel(Level.INFO);
        handler.setFormatter(new Formatter() {
            @Override
            public String format(LogRecord record) {
                return "threadId=" + record.getLongThreadID()
                        + " level=" + record.getLevel().getName()
                        + " " + formatMessage(record)
                        + System.lineSeparator();
            }
        });
        LOG.addHandler(handler);

        Thread worker = new Thread(() -> {
            String name = Thread.currentThread().getName();
            LOG.info(() -> "event=start threadName=" + name);
            LOG.info(() -> "event=end threadName=" + name);
        }, "logging-worker");

        worker.start();
        worker.join();
        handler.flush();
    }
}
~~~

Compile and run with JDK 17+:

~~~bash
javac ThreadIdLoggingDemo.java
java ThreadIdLoggingDemo
~~~

Output format (the actual ID value is determined by the JVM; do **not** print the angle-bracketed placeholder literally):

~~~text
threadId=<positive ID> level=INFO event=start threadName=logging-worker
threadId=<same ID> level=INFO event=end threadName=logging-worker
~~~

Both records share the same ID because they were emitted in **the same thread**. `ConsoleHandler` writes to standard error by default; appearing in the same terminal as standard output does not change the meaning of the Thread ID.

**How it works:**

1. `new Thread(..., "logging-worker")` creates a thread with a human-readable name.
2. `worker.start()` executes the `Runnable` on the new thread; inside `Runnable`, `Thread.currentThread()` refers to that thread.
3. `LOG.info(...)` creates a record with the originating thread's information; the formatter reads `record.getLongThreadID()`.
4. `worker.join()` makes `main` wait for the thread to finish so the example does not exit prematurely.
5. `LOG.setUseParentHandlers(false)` prevents the parent logger from printing the same event a second time using the default formatter.

Writing `Thread.currentThread().getId()` directly into the message content is also valid on Java 17:

~~~java
Thread t = Thread.currentThread();
LOG.info(() -> "event=validate threadId=" + t.getId()
        + " threadName=" + t.getName());
~~~

Using a formatter is a good choice when you want a consistent `threadId` field on **every record**, even if a developer forgets to include the ID in individual log statements. Using the message directly is simpler when only a few log points are needed. In production systems, standardize the field in the layout/encoder or shared logging configuration to avoid duplicating the ID in both metadata and the message.

## 4. Thread ID in Thread Pools: One Thread Can Handle Many Tasks

`ExecutorService` typically reuses threads. Therefore, two tasks with different `taskId` values **can have the same** `threadId`. This is expected behavior, not a duplicate ID bug.

Create the file **PoolThreadIdDemo.java**:

~~~java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public final class PoolThreadIdDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();
        try {
            for (int i = 1; i <= 3; i++) {
                final int taskId = i;
                pool.submit(() -> {
                    long threadId = Thread.currentThread().getId();
                    System.out.printf(
                            "taskId=%d threadId=%d%n", taskId, threadId);
                }).get();
            }
        } finally {
            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                pool.shutdownNow();
            }
        }
    }
}
~~~

~~~bash
javac PoolThreadIdDemo.java
java PoolThreadIdDemo
~~~

Output format:

~~~text
taskId=1 threadId=<N>
taskId=2 threadId=<N>
taskId=3 threadId=<N>
~~~

`<N>` across all three lines represents the same positive ID value during a normal run: the single-thread executor processes tasks sequentially, and `Future.get()` waits for each task to complete. Do not assume this result holds for a multi-threaded pool or a pool where a thread is replaced after an error.

With a multi-threaded pool, logs can interleave. To trace a single request, log an application-generated `requestId` or `traceId`; do not rely on `threadId` to stitch together the entire lifecycle of a request.

## 5. SLF4J/Logback: Adding the ID to the Message or MDC

Different logging frameworks have their own patterns. With Logback, `%thread` usually displays the thread **name**, not the numeric Java Thread ID. To include a numeric field, you can log it directly in the message or put the ID into MDC (Mapped Diagnostic Context).

**Approach 1 — directly in the log (illustrative, requires SLF4J and a `log` variable):**

~~~java
long threadId = Thread.currentThread().getId(); // Java 17
log.info("event=order_validate threadId={} orderId={}", threadId, orderId);
~~~

This snippet is intended for an application already configured with SLF4J; it is not a standalone Java SE program. On Java 19+, you can replace `getId()` with `threadId()`.

**Approach 2 — storing in MDC for logs emitted within the same scope:**

~~~java
import org.slf4j.MDC;

// In the handler method, assuming an SLF4J logger and orderId variable are already available.
String id = Long.toString(Thread.currentThread().getId());
MDC.put("threadId", id);
try {
    log.info("event=order_validate orderId={}", orderId);
    // Other logs on the same thread within this block can also read from MDC.
} finally {
    MDC.remove("threadId");
}
~~~

An illustrative Logback pattern configuration:

~~~text
%d{ISO8601} %-5level threadId=%X{threadId} threadName=%thread %logger - %msg%n
~~~

`%X{threadId}` reads **the value the application explicitly puts into MDC**; it does not automatically call `Thread.threadId()`. You must set the MDC value before logging and remove it in a `finally` block so the context does not leak into the next task on the same thread pool. If multiple layers use the `threadId` key, save the previous value and restore it within the appropriate scope instead of removing it unconditionally.

MDC is typically bound to the current thread; when executing asynchronously or switching to another thread, **do not assume the context will propagate automatically**. You need a context propagation mechanism suited to your framework. `requestId`/`traceId` must be propagated across async boundaries if you want to trace the same transaction; copying the previous thread's `threadId` will misrepresent execution details.

## 6. Virtual Threads (Java 21+)

A virtual thread is still a `java.lang.Thread` and still has its own Java Thread ID. Calling `Thread.currentThread().threadId()` on a virtual thread returns the ID of the **current virtual thread**, not the ID of the platform thread acting as its carrier. Over its lifetime, a virtual thread may be mounted onto and unmounted from different carrier threads; do not use the carrier thread to infer request identity.

Create the file **VirtualThreadIdDemo.java** (requires JDK 21+):

~~~java
public final class VirtualThreadIdDemo {
    public static void main(String[] args) throws InterruptedException {
        Thread worker = Thread.ofVirtual()
                .name("request-virtual")
                .start(() -> {
                    Thread t = Thread.currentThread();
                    System.out.printf(
                            "isVirtual=%s threadId=%d threadName=%s%n",
                            t.isVirtual(), t.threadId(), t.getName());
                });
        worker.join();
    }
}
~~~

~~~bash
javac VirtualThreadIdDemo.java
java VirtualThreadIdDemo
~~~

Output format:

~~~text
isVirtual=true threadId=<positive ID> threadName=request-virtual
~~~

Operational notes:

- Thousands of virtual threads can exist at once. The ID is useful for per-thread diagnostics, but it produces high-cardinality values; do not use `threadId` as a label for low-cardinality metrics such as total requests per endpoint.
- A virtual thread's name may be empty if not set; including both the ID and business context in logs improves readability.
- Request tracing still requires `traceId`/`requestId`, even when a request typically runs within a single virtual thread.

## 7. Analyzing Logs Effectively

When investigating a concurrency issue, examine **thread ID, timestamp, instance, and business ID** together:

1. Identify which application/JVM emitted the log: service, instance/container, time range, and startup/run.
2. Filter events by `threadId` to see the sequence of actions for a single thread within the relevant time window.
3. Cross-reference `requestId`, `traceId`, and `taskId` to determine which request an event belongs to. With thread pools, the same ID does not mean the same request.
4. Compare events across different threads using timestamps and correlation IDs. Do not infer absolute ordering solely from log line order or Thread ID numbers.
5. If you need to diagnose hangs or lock contention, combine thread dumps, Java Flight Recorder (JFR), `ThreadMXBean`, and the IDs in logs. Correlate by Java thread ID within the same JVM session; avoid confusing Java IDs with OS TIDs.

If storing logs as JSON, keys should have clear names and consistent types, for example:

~~~json
{
  "timestamp": "2026-11-10T09:40:00Z",
  "level": "WARN",
  "service": "checkout",
  "instance": "checkout-2",
  "threadId": 37,
  "threadName": "pool-1-thread-2",
  "requestId": "req-123",
  "event": "lock_wait"
}
~~~

In this JSON, `threadId` is a number and `requestId` is a string. These values only illustrate the representation format and do not depict an actual runtime scenario.

## 8. Common Mistakes and How to Avoid Them

| Symptom / Mistake | Cause | Solution |
| --- | --- | --- |
| Logging only the thread name and treating it as an ID | Names are set by users/frameworks and can be duplicated or changed | Log `threadId` as a `long` and optionally `threadName`. |
| Using `LogRecord.getThreadID()` in Java 17 | Deprecated `int` API that may return a synthetic ID | Use `LogRecord.getLongThreadID()`. |
| Casting ID to `int` or assuming IDs increment sequentially | Loses precision or relies on an unguaranteed pattern | Use `long`; correlate by timestamp and specific JVM. |
| Calling `otherThread.getId()` while logging | Retrieves another thread object's ID, not the running thread's | Capture `Thread.currentThread()` at the logging call site. |
| Assuming all logs with the same Thread ID belong to one request | Pool workers reuse threads | Log a separate `requestId`/`traceId`. |
| Carrying over an old `threadId` to a new thread via MDC | Misattributes the thread emitting the log | Recompute Thread ID on the executing thread and propagate correlation context separately. |
| Failing to clear MDC after a task | Values from a previous task can appear in logs of subsequent tasks | Use `try/finally` to remove or restore context. |
| Comparing Java Thread IDs directly with OS TIDs | The two identifier spaces are not guaranteed to match | Use tools with explicit mapping; in JFR, distinguish between Java and OS thread IDs. |
| Filtering logs by ID while ignoring JVM/instance | Two different JVMs can have the same numeric ID | Combine with `service`, `instance`, and time range. |
| Using Thread ID as a user/request identity key | Thread ID only represents a thread | Use business/correlation IDs and separate access controls. |

## 9. Self-Check Questions

1. A single-thread executor runs 100 tasks sequentially. Why might you see only one `threadId` but 100 different `taskId` values?
2. Do two threads with different names always have different Thread IDs? Must two threads with the same name have the same ID? Answer within **the scope of the same JVM while both threads are alive simultaneously**.
3. Why might you see the same `requestId` but a different `threadId` after `CompletableFuture.supplyAsync(...)`?
4. What is the difference between `Thread.getId()` on Java 17 and `Thread.threadId()` on Java 19+?
5. When using `java.util.logging.LogRecord`, why should you call `getLongThreadID()` instead of `getThreadID()`?
6. With Logback, where do `%thread` and `%X{threadId}` get their data from? What happens if `MDC.put("threadId", ...)` has not been called?
7. For a virtual thread, does the ID in the log represent the virtual thread or the carrier thread?

**Answer hints:** (1) the pool reuses the thread; (2) live threads have unique IDs, whereas names can be duplicated; (3) asynchronous tasks may switch threads; (4) `threadId()` was added in Java 19 and is `final`, while `getId()` was deprecated in Java 19; (5) using `long` avoids synthetic `int` IDs; (6) `%thread` is the thread name, `%X{threadId}` is from MDC and may be empty if unset; (7) the current virtual thread.

## 10. References

- [Java SE 21 — Thread API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Thread.html): `threadId()`, `getId()`, and `isVirtual()`.
- [Java SE 17 — LogRecord API](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/LogRecord.html): `getLongThreadID()` and `getThreadID()`.
- [Java SE 21 — Virtual Threads](https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html): virtual threads and carrier threads.
