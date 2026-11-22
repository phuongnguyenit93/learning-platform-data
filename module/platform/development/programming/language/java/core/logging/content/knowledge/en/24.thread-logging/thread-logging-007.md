# Thread-Safe Loggers in Java Core Logging

## 1. What is a thread-safe logger?

In a Java application, multiple threads can concurrently process HTTP requests, background tasks, queue messages, or thread-pool jobs. Those threads typically log through **the same Logger instance**, such as a shared `static final` field on a class.

A **thread-safe logger** allows multiple threads to call logging methods concurrently without corrupting the logger's internal state. For example, if thread A logs "Order received" while thread B logs "Payment processed", calling the logger API from both threads is valid when the logger and logging backend are designed for concurrent access.

However, it is important to distinguish between different layers of guarantees:

- **Logger/API:** whether multiple threads concurrently calling `info`, `warn`, `error`, and so on are safely supported.
- **Handler/Appender:** the component that receives and writes each log event to the console, a file, the network, or a queue. A custom handler can break thread safety even when the shared logger itself is used properly.
- **Log messages and passed-in data:** the logger does not automatically synchronize mutable application objects being passed into log calls.
- **Ordering and durability:** thread-safe does not mean logs from different threads appear in business order, are persisted immediately, or can never be lost.

With the standard library **`java.util.logging.Logger` (JUL)**, the same logger can be used from multiple threads. In applications using **SLF4J** with common backends such as Logback or Log4j 2, sharing one logger across threads is also the standard pattern. If you write a custom backend, appender, formatter, or handler, you must separately evaluate that component's ability to handle concurrent access.

## 2. Share a logger; do not create one logger per thread

A common way to declare a class logger is:

~~~java
import java.util.logging.Logger;

public final class OrderService {
    private static final Logger LOGGER =
            Logger.getLogger(OrderService.class.getName());

    public void process(String orderId) {
        LOGGER.info("Processing order " + orderId);
    }
}
~~~

`static final` means the logger reference field is created/selected once when the class is initialized, and all `OrderService` instances share that reference. This choice is lightweight, easy to configure, and keeps logs under the same source name. `static final` by itself **does not make any object thread-safe**; safety comes from how `Logger` and its handlers/appenders are implemented.

You do not need to create a new logger per call, per request, or per thread to avoid contention. Creating separate loggers per thread also makes managing logger names, log levels, and correlation harder. Conversely, having a thread-safe logger **does not make the entire `process` method thread-safe**: if `process` mutates a shared list, counter, or cache, that data still needs appropriate synchronization.

**Distinguish two questions:**

1. "Can multiple threads call `LOGGER.info(...)` concurrently?" — Yes, with a logger and logging backend that support concurrency.
2. "Is the business data recorded in the log consistent?" — Not necessarily. For example, two threads incrementing an unsynchronized `int` variable can still produce wrong values, even though the log lines themselves are written safely.

## 3. Standalone Java 17 example: 4 threads writing to one logger

This example uses `java.util.logging` built into the JDK, so **no external libraries are required**. Four workers share one `Logger`, and each worker produces 25 distinct messages. A custom `Handler` collects messages into a `ConcurrentLinkedQueue` for verification after all workers finish.

Create the file **`ThreadSafeLoggerDemo.java`**:

~~~java
import java.util.HashSet;
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class ThreadSafeLoggerDemo {
    private static final Logger LOGGER =
            Logger.getLogger(ThreadSafeLoggerDemo.class.getName());

    public static void main(String[] args) throws InterruptedException {
        ConcurrentLinkedQueue<String> messages = new ConcurrentLinkedQueue<>();

        Handler collectingHandler = new Handler() {
            @Override
            public void publish(LogRecord record) {
                if (isLoggable(record)) {
                    messages.add(record.getMessage());
                }
            }

            @Override
            public void flush() {
            }

            @Override
            public void close() {
            }
        };

        collectingHandler.setLevel(Level.INFO);
        LOGGER.setLevel(Level.INFO);
        LOGGER.setUseParentHandlers(false); // Suppress default console logging.
        LOGGER.addHandler(collectingHandler);

        ExecutorService pool = Executors.newFixedThreadPool(4);
        CountDownLatch start = new CountDownLatch(1);

        try {
            for (int worker = 0; worker < 4; worker++) {
                final int workerId = worker;
                pool.execute(() -> {
                    try {
                        start.await();
                        for (int event = 0; event < 25; event++) {
                            LOGGER.info("worker=" + workerId + " event=" + event);
                        }
                    } catch (InterruptedException e) {
                        Thread.currentThread().interrupt();
                    }
                });
            }

            start.countDown(); // Allow workers to start.
            pool.shutdown();

            if (!pool.awaitTermination(30, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Workers did not finish");
            }

            System.out.println("records=" + messages.size());
            System.out.println("unique=" + new HashSet<>(messages).size());
        } finally {
            pool.shutdownNow();
            LOGGER.removeHandler(collectingHandler);
            collectingHandler.close();
        }
    }
}
~~~

Compile and run with JDK 17 or later:

~~~bash
javac ThreadSafeLoggerDemo.java
java ThreadSafeLoggerDemo
~~~

Output when the workers complete within the 30-second timeout:

~~~text
records=100
unique=100
~~~

**Result explanation:**

- There are **4 × 25 = 100** `LOGGER.info` calls; all of them use the same `LOGGER` field.
- Each message contains a `(workerId, event)` pair, so **all 100 messages are distinct**.
- `ConcurrentLinkedQueue` is safe when multiple threads call `add` concurrently. This is a key point: a handler must protect **its own shared memory**.
- `CountDownLatch` gives the workers a chance to start concurrently. `awaitTermination` ensures the counts are checked after all workers have finished, rather than reading the queue while threads are still writing.
- The example **makes no guarantee about the order** of the 100 messages. If each message were printed directly, `worker=3` could easily appear before `worker=0`.

This example demonstrates one safe usage pattern; **it is not a proof that every handler or logging backend is thread-safe**. Adding a shared `ArrayList` to a handler and calling `add` from multiple threads without synchronization is a different design and can cause race conditions.

## 4. Thread-safe does not mean ordered logs

Consider two threads processing two independent requests:

~~~text
Thread-A: start A   ─────── process A ───────── complete A
Thread-B: ─── start B   ── process B ─── complete B
Log:      [A start] [B start] [B done] [A done]
~~~

The order above can be completely valid. **Thread-safe** only means concurrent logging operations are handled according to the logger/appender contract; it does not promise that all logs for a single request will always stay contiguous. Thread scheduling, I/O, buffering, and asynchronous logging all affect the observed order.

Common misconceptions:

- **Single-event integrity:** a backend may handle each log event as an atomic unit, but custom formatters/appenders or writing directly to a shared stream can produce interleaved output.
- **Creation time vs. output time:** with async logging, an event can be created on a worker thread and written to a file or network later. Do not equate log output order with business operation completion order.
- **Cross-thread ordering:** timestamps can be identical, and a system may use multiple clocks or services. Never use log line order as a synchronization mechanism.
- **Within-thread ordering:** log calls in code follow program execution order, but an asynchronous backend or log aggregation from multiple sources can cause the displayed order to differ from naive assumptions.

If you need to verify causality, include a request/trace ID, task ID, or a sequence number **assigned with proper synchronization**. Do not make thread coordination or business ordering the logger's responsibility.

## 5. SLF4J and parameterized logging in real-world applications

In Java applications using SLF4J, you typically declare a class-level logger and call it from any thread:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public final class PaymentService {
    private static final Logger LOGGER =
            LoggerFactory.getLogger(PaymentService.class);

    public void charge(String requestId, long amount) {
        LOGGER.info("Charging requestId={} amount={}", requestId, amount);
    }
}
~~~

This snippet **requires SLF4J and a logging backend dependency** to compile and run; it is an integration example, not part of the standalone JDK program in section 3. With a common backend designed for concurrent use, a class-level logger is the standard pattern.

Using `{}` placeholders separates the message template from its arguments and avoids eager string concatenation when the log level may be disabled. Even so:

- Do not pass an object that is being mutated by another thread and assume its `toString()` representation will be safe.
- Do not build messages with a **shared static** `StringBuilder` unless properly synchronized. A local `StringBuilder` created per call does not have this sharing issue.
- Do not call methods with side effects just to compute log arguments. Even if the event is filtered out, Java evaluates argument expressions before invoking the logger.
- Do not log passwords, access tokens, sensitive personal data, or full request bodies just to identify a thread.

If you use an asynchronous logger, check the configuration for **queue size, full-queue policy, flush/shutdown behavior, and potential event discarding**. The API accepting a call does not guarantee the log has been durably written to disk or a collection system.

## 6. Thread name, MDC, and trace context: three different things

**Thread name** (for example, `pool-1-thread-2`) tells you which thread executed the call. It is useful for debugging, **but it is not a request ID**: a thread in a pool can handle many requests sequentially, and a single request can also span multiple threads.

**MDC (Mapped Diagnostic Context)** lets you attach fields such as `requestId` to log events so logs can be grouped by request. Common MDC implementations store context per thread, so you must set and clean up context carefully:

~~~java
import org.slf4j.MDC;

// Code inside a scope where LOGGER and requestId are already available.
MDC.put("requestId", requestId);
try {
    LOGGER.info("Start processing");
    // Process the request on the current thread.
} finally {
    MDC.remove("requestId");
}
~~~

This is an **SLF4J integration snippet**, not a standalone program. `try/finally` prevents the next request on the same pooled thread from accidentally inheriting the previous `requestId`. If a framework provides a managed MDC scope, use that scope properly. When code runs inside a method that already has multiple MDC keys, consider saving and restoring the previous context rather than blindly clearing keys owned by the caller.

**Trace context** includes `traceId`, `spanId`, and parent-span relationships to link work across threads and services. Tracing instrumentation can help populate IDs into MDC/logs, **but a thread-safe logger does not propagate trace context automatically**. When crossing into an `ExecutorService`, `CompletableFuture`, reactive pipeline, or another thread, you need the framework or tracing library's propagation mechanism. You cannot assume request context is still present merely because the same `Logger` is used.

For example, two logs on the same thread can have different `requestId` values; conversely, two different threads can process parts of the same trace. Use **request/trace identifiers** to investigate an execution flow, and use the thread name to identify where execution occurred.

## 7. Common pitfalls when multiple threads log

| Symptom | Cause to check | How to handle |
| --- | --- | --- |
| Logs from two requests interleave | Threads execute concurrently; interleaving is normal | Log `requestId` or `traceId` and filter by ID |
| Logs carry the wrong request ID | MDC/context was not cleaned up or not propagated properly | Use scoped context/`finally` and proper propagation mechanisms |
| Logs are lost or delayed | Async queue full, filtering/sampling config, exporter errors, missing flush on shutdown | Check backend policies and the telemetry pipeline |
| Log content shows inconsistent data | Shared mutable object modified concurrently during formatting | Snapshot the data or protect business state |
| Missing events or corrupted strings in a custom handler | Custom collection/formatter/appender is not thread-safe | Use concurrent collections, synchronization, or an appropriate queue |
| Logs are out of business order | Scheduling, buffering, or multiple services | Use correlation IDs and timestamp/causality metadata |
| Multiple processes writing to one file cause corruption | Thread-safety guarantees apply only across threads within each process | Configure multi-process logging or aggregate logs through an intermediary |

**Do not try to "fix" every issue by wrapping all `LOGGER.info(...)` calls in `synchronized`**. Doing so can bottleneck throughput while failing to solve business-data races, lost MDC, or multiple processes writing to the same file. Synchronize only where shared state genuinely needs protection.

When writing a custom `Handler`/`Appender`, clearly identify all mutable data that multiple threads can touch: buffers, formatters, counters, writers, sockets, queues, and runtime configuration. That component must have appropriate thread-safety mechanisms and proper lifecycle flush/close handling.

## 8. Implementation and self-check checklist

Before deploying logging in a concurrent Java service, verify:

1. Loggers are declared at the class/component level and shared in a way supported by the backend; no logger is created per message.
2. Handlers/appenders, especially custom ones, can handle concurrent calls; no unprotected mutable collections are used.
3. Log events include useful correlation data; thread name is only supporting metadata.
4. MDC and trace context are set, propagated across async boundaries when needed, and cleaned up or restored after the task.
5. Async queue settings, log levels, filters, flush, and shutdown behavior are configured to match data-loss and performance requirements.
6. A single observed log order is never treated as proof that threads ran sequentially.

**Self-check:** If 10 requests call the same `static final Logger`, do you need 10 `Logger` instances? **No**, as long as the logger/backend supports concurrency. If all 10 requests append to a shared `static StringBuilder` and then log it, will the logger call fix the bug? **No**: `StringBuilder` is shared state outside the logger's thread-safety contract. If logs from two requests interleave while each event remains intact, is that necessarily a bug? **No**: it can be a normal outcome of parallel execution.

**Key takeaway:** A thread-safe logger lets multiple threads log through one shared logger safely according to the library's contract. For logs to be reliable during troubleshooting, you also need thread-safe handlers/appenders, consistent input data, accurate correlation context, and a clear understanding of ordering and persistence limits.