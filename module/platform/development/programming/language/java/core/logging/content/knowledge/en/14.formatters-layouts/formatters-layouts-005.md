# Thread Formatting in Java Logging: Thread Name, Thread ID, and Layout

In concurrent Java applications, multiple threads can emit logs at the same time. **Thread formatting** is the practice of including information about the thread that emitted an event—most commonly the **thread name**, and sometimes the **thread ID**—in the formatter/layout output so investigators know which thread a log came from.

For example:

```text
2026-11-09T08:15:12.038Z INFO  [http-nio-8080-exec-7] OrderController - request accepted
2026-11-09T08:15:12.041Z DEBUG [order-worker-2] InventoryService - reserve completed
```

The two lines above are **illustrative data** only; timestamps, thread names, and classes depend on the application. Thread metadata is especially useful when inspecting thread pools, background tasks, concurrent request handling, and race conditions. However, **a thread is not a request**: a single thread can handle multiple requests sequentially, and a single request can hop across multiple threads. Therefore, thread names should be combined with `requestId`/`traceId` when you need to trace business operations.

This lesson belongs to the **Formatters and Layouts** group. The goal is to know how to include thread names/IDs in JUL, Logback, and Log4j 2; understand when the metadata values are captured; choose useful thread names; verify output in multithreaded and asynchronous scenarios; and avoid confusing thread metadata with MDC or logger names.

## 1. Where does thread metadata sit in a log event?

A logging event can carry the following information:

| Field | Meaning | Example |
| --- | --- | --- |
| Timestamp | Time when the event was emitted | `2026-11-09T08:15:12.038Z` |
| Level | Log level | `INFO`, `DEBUG`, `WARN` |
| Logger name | Category/class emitting the log | `com.example.order.OrderService` |
| **Thread name** | Name of the thread associated with the event | `order-worker-2` |
| **Thread ID** | Thread identifier within the JVM | `37` |
| Message | Event content | `stage=reserved` |
| Throwable | Exception and stack trace, if any | `IllegalStateException` |
| Context | Correlation ID, trace ID, or structured data | `requestId=req-17` |

You need to separate three kinds of names:

- **Logger name** answers: *which class/category emitted the event?* A single class can be called from multiple threads.
- **Thread name/ID** answers: *which thread executed the code that emitted the log?* A thread pool can reuse the same thread for many requests.
- **Request ID/trace ID** answers: *which request or trace does this event belong to?* A single request can span multiple threads and multiple services.

A good formatter/layout displays these fields separately. Do not name loggers dynamically after threads, do not use thread IDs as correlation IDs, and do not infer the cause of a race condition solely from two lines having different thread names.

## 2. How do thread name and thread ID differ?

### Thread name

Java lets you read the current thread's name:

```java
// Fragment inside a Java method.
String name = Thread.currentThread().getName();
```

This is a string that helps humans identify the thread's function. For example, a thread pool might use `payment-worker-1` and `payment-worker-2`, while the main thread is usually named `main`. The name can be assigned by the application, framework, or `ThreadFactory`, and **can be changed** with `setName(...)`. Do not assume thread names are strictly unique, immutable, or controlled by the JVM in every application.

### Thread ID

On Java 17, you can read the ID with:

```java
// Fragment on Java 17; id is a long.
long id = Thread.currentThread().getId();
```

`Thread.getId()` returns the thread's ID within the JVM. It is not the process PID, not the OS thread ID in a sense guaranteed across all operating systems, and **not a key for correlating logs across services or JVM restarts**. Newer Java versions have the `threadId()` API; if your project is pinned to Java 17, use the API supported by Java 17.

**For `java.util.logging.LogRecord`:** JDK 17 provides `getLongThreadID()`, which retrieves the ID of the thread that emitted the event. The `int`-returning `getThreadID()` API was deprecated in Java 16 because the ID can be a synthesized value; on Java 17, prefer `getLongThreadID()`.

```java
// Fragment inside Formatter.format(LogRecord record) in Java 17.
long originThreadId = record.getLongThreadID();
```

The ID in `LogRecord` is tied to the event's origin, which does not mean it matches the native OS thread ID. With Logback and Log4j 2, thread information is captured according to the backend's log event model; use the proper conversion word so the formatter reads the **event's metadata** rather than reading whichever thread happens to run the formatter during asynchronous processing.

## 3. Formatting threads with Logback PatternLayout

In Logback classic, **`%thread`** and its short form **`%t`** are the conversion words for printing the **name of the thread that emitted the event**. Example pattern:

```text
%d{HH:mm:ss.SSS} %-5level [thread=%thread] %logger{36} - %msg%n
```

Explanation:

| Token | Effect |
| --- | --- |
| `%d{HH:mm:ss.SSS}` | Timestamp matching the pattern; a simple example without date/timezone |
| `%-5level` | Level left-aligned with a minimum width of 5 |
| `%thread` or `%t` | Thread name of the log event |
| `%logger{36}` | Logger name abbreviated when necessary to fit the display length |
| `%msg` | Formatted message |
| `%n` | Platform-specific line separator |

### Complete Logback file

In a project that already uses **Logback classic** as its backend, create `src/main/resources/logback.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<configuration>
    <appender name="CONSOLE"
              class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%d{HH:mm:ss.SSS} %-5level [thread=%thread] %logger{36} - %msg%n</pattern>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
    </root>
</configuration>
```

This is a **complete Logback configuration file**, not a Log4j 2 or JUL configuration. Business code can continue declaring SLF4J loggers:

```java
// Fragment in a class that already has the SLF4J dependency.
private static final org.slf4j.Logger LOG =
        org.slf4j.LoggerFactory.getLogger(OrderService.class);
```

`OrderService` is an illustrative class. When `LOG.info(...)` is emitted, Logback writes the thread name at the `%thread` position according to the configuration. **`LoggerFactory.getLogger` does not create a thread**; the thread is whichever thread is executing the logging code.

Example output:

```text
08:15:12.038 INFO  [thread=main] com.example.OrderService - application started
08:15:12.041 INFO  [thread=order-worker-1] com.example.OrderService - processing order
```

The timestamps are illustrative only. This pattern has no timezone; in production, use a full timestamp with timezone or structured logging suited to your collector. **Do not assume Logback supports Log4j 2's `%T` thread ID conversion word**: Logback's `%thread` prints the *name*, whereas if you need the *ID*, you should use an encoder/converter mechanism or structured logging supported by that version/backend.

### Adding request ID to a Logback pattern

```xml
<!-- Fragment inside Logback's <encoder> -->
<pattern>%d{HH:mm:ss.SSS} %-5level [%thread] requestId=%X{requestId} %logger{36} - %msg%n</pattern>
```

`%X{requestId}` reads **MDC**, not the thread ID. If the application has not put `requestId` into MDC, the field may be empty. Do not use the thread name as a substitute for MDC just because the request ID does not appear.

## 4. Formatting threads with Log4j 2 PatternLayout

Log4j 2 also has PatternLayout, but **do not assume all conversion words are identical to Logback**.

Common tokens:

- **`%t`** or `%thread`: the event's **thread name**.
- **`%T`**, `%tid`, or `%threadId`: the event's **thread ID**.
- **`%X{requestId}`**: the `requestId` value in the Thread Context Map, if present.
- **`%c`**, `%logger`: logger/category name.
- **`%p`**, `%level`: log level.
- **`%m`**, `%msg`: message.
- **`%n`**: newline.

Example of a **complete `log4j2.xml` file**, when the project uses Log4j 2 Core:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<Configuration status="WARN">
    <Appenders>
        <Console name="Console" target="SYSTEM_ERR">
            <PatternLayout pattern="%d{HH:mm:ss.SSS} %-5p [thread=%t tid=%T] requestId=%X{requestId} %c{1} - %m%n"/>
        </Console>
    </Appenders>

    <Loggers>
        <Root level="info">
            <AppenderRef ref="Console"/>
        </Root>
    </Loggers>
</Configuration>
```

Here, `%t` and `%T` read the thread name and ID from the Log4j 2 event. `%X{requestId}` only contains data if MDC/ThreadContext is managed properly.

Illustrative example:

```text
08:15:12.038 INFO  [thread=order-worker-1 tid=37] requestId=req-17 OrderService - order created
```

The `tid=37` value and timestamp are illustrative data only; actual IDs vary by JVM and thread. Do not write unit tests comparing against **a hardcoded thread ID number** unless the test itself initializes a mock model to control the value.

### Quick comparison across backends

| Requirement | Logback classic | Log4j 2 |
| --- | --- | --- |
| Print thread name | `%thread`, `%t` | `%t`, `%thread` |
| Print thread ID | Check encoder/converter support for your version; do not blindly apply Log4j's `%T` | `%T`, `%tid`, `%threadId` |
| Print request ID from context | `%X{requestId}` (MDC) | `%X{requestId}` (ThreadContext Map) |
| Format message | `%msg` | `%m` or `%msg` |
| Logger name | `%logger` | `%c` or `%logger` |
| Common XML config | `logback.xml`, `logback-spring.xml` when using Boot | `log4j2.xml`, `log4j2-spring.xml` with Boot integration |

Do not copy `<PatternLayout>` verbatim from Log4j 2 into Logback's XML, or Logback's `<encoder>` into Log4j. They are two different configuration schemas even though some conversion words share the same names.

## 5. Java Util Logging (JUL): understanding `LogRecord` and Formatter

In **JUL** (`java.util.logging`), `SimpleFormatter` supports formatting via the `java.util.logging.SimpleFormatter.format` system property, but its default format argument list **does not have a thread name field** like Logback's `%thread`. To display the thread in a custom format, you can write a `java.util.logging.Formatter` and attach it to a `Handler`.

**Java 17's `LogRecord` provides `getLongThreadID()` but has no standard getter for the thread name.** This is especially important when logging asynchronously:

- The ID can be read from `record.getLongThreadID()` even if the formatter runs on a different thread.
- `Thread.currentThread().getName()` inside `Formatter.format` is only the name of **the thread calling the formatter**, **not always the thread that emitted the event**.
- With a synchronous `ConsoleHandler` in the example below, the formatter executes on the same call path as the log call, so reading the current thread name works for demonstration.
- If you push events onto a queue, defer formatting, or use an asynchronous handler, you should **capture the thread name at event emission time** into the record's metadata or use a backend that has an event thread-name field; do not substitute the queue consumer worker's name.

### Runnable example with JDK 17

Save the file **`ThreadFormatDemo.java`** (no libraries outside the JDK):

```java
import java.util.logging.ConsoleHandler;
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class ThreadFormatDemo {
    private static final Logger LOG =
            Logger.getLogger(ThreadFormatDemo.class.getName());

    public static void main(String[] args) throws InterruptedException {
        String oldName = Thread.currentThread().getName();
        Thread.currentThread().setName("demo-main");

        ConsoleHandler console = new ConsoleHandler();
        console.setLevel(Level.INFO);
        console.setFormatter(new Formatter() {
            @Override
            public String format(LogRecord record) {
                return record.getLevel().getName()
                        + " [thread="
                        + Thread.currentThread().getName()
                        + "] "
                        + formatMessage(record)
                        + System.lineSeparator();
            }
        });

        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.INFO);
        LOG.addHandler(console);

        try {
            LOG.info("stage=start");

            Thread worker = new Thread(
                    () -> LOG.info("stage=worker-done"),
                    "order-worker-1");

            worker.start();
            worker.join();

            LOG.info("stage=end");
        } finally {
            LOG.removeHandler(console);
            console.close();
            Thread.currentThread().setName(oldName);
        }

        System.out.println("completed=true");
    }
}
```

Run with **JDK 17 or later**:

```bash
javac -encoding UTF-8 ThreadFormatDemo.java
java ThreadFormatDemo
```

**Exact stderr from the program's three JUL calls:**

```text
INFO [thread=demo-main] stage=start
INFO [thread=order-worker-1] stage=worker-done
INFO [thread=demo-main] stage=end
```

**Exact stdout:**

```text
completed=true
```

Calling `Thread.currentThread().setName("demo-main")` makes the main thread name **deterministic in the example**; this is not a recommendation to arbitrarily rename the main thread in production applications. The second thread is created with an explicit name; `join()` ensures it finishes before the `stage=end` call, so the order of the three logs in the example is intentional.

**Why use `LOG.setUseParentHandlers(false)`?** To prevent parent handlers from printing extra lines and breaking the sample output. In a real application, propagation to the root handler may be the standard way to route logs into a centralized system; do not disable it by default without knowing the logging architecture.

**Major limitation of the example:** The formatter calls `Thread.currentThread()`, which is fine here because `ConsoleHandler` writes synchronously on the thread emitting the log. If you switch to asynchronous processing, the formatter may log the name of the log-processing thread instead of the origin thread. In that case, you need to snapshot metadata or use a backend with its own thread-event capture mechanism.

### When you only need the origin thread ID in JUL

Java 17 has an API to read the ID from `LogRecord`:

```java
// Fragment inside Formatter.format(LogRecord record).
long sourceThreadId = record.getLongThreadID();
String idField = "tid=" + sourceThreadId;
```

This is a fragment, not a standalone program. You can append `idField` to the formatter string to log the ID of the thread that emitted the event. Note that the thread ID **is not the OS TID** and cannot replace a correlation ID.

### Why not use `SimpleFormatter.format` to get the thread name?

`java.util.logging.SimpleFormatter.format` uses predefined argument positions for the timestamp, source, logger name, level, message, and throwable. It **does not** use the same PatternLayout syntax as Logback/Log4j 2; writing `%thread` into JUL's system property will not make the thread name appear as intended. When you need thread metadata in a custom format, use a custom Formatter, an integrated encoder, or switch to a logging system designed with that field.

## 6. Naming threads usefully for reading logs

A log with `[thread=pool-1-thread-7]` is still better than nothing, but `[thread=invoice-export-2]` helps operators identify the function much faster.

A `ThreadFactory` can assign names when creating worker threads:

```java
// Fragment in a method with java.util.concurrent and AtomicInteger.
java.util.concurrent.atomic.AtomicInteger next =
        new java.util.concurrent.atomic.AtomicInteger();

java.util.concurrent.ThreadFactory factory = task ->
        new Thread(task, "invoice-worker-" + next.incrementAndGet());

java.util.concurrent.ExecutorService pool =
        java.util.concurrent.Executors.newFixedThreadPool(2, factory);
try {
    // Submit tasks via pool.submit(...) or pool.execute(...).
} finally {
    pool.shutdown();
}
```

This is an illustrative snippet, not a standalone runnable program, and no actual tasks are submitted. `shutdown()` only tells the executor not to accept new tasks; the application needs to manage waiting for completion or cancellation policies if tasks are still running. For a production system, you can add an uncaught-exception handler and daemon rules according to operational requirements.

**Naming conventions to follow:**

- Use a prefix that reflects the function: `http-worker-`, `invoice-worker-`, `message-consumer-`.
- Use a worker index suffix for readability: `invoice-worker-1`, `invoice-worker-2`.
- Keep names short and stable, without passwords, tokens, email addresses, user IDs, or private data.
- Do not rename threads per request if threads are reused by a pool; instead, put the request ID into MDC/log events.
- Do not assume a thread name is unique across multiple JVMs, containers, deployments, or nodes.

**Do not arbitrarily rename framework-managed threads** if the framework uses the name for metrics, diagnostics, or conventions. You can configure the thread factory/executor at the pool creation site instead of renaming mid-request.

## 7. Thread pools: one thread can serve multiple requests

Suppose an HTTP server reuses `http-worker-7`:

```text
INFO [http-worker-7] requestId=req-101 event=accepted
INFO [http-worker-7] requestId=req-101 event=completed
INFO [http-worker-7] requestId=req-102 event=accepted
INFO [http-worker-7] requestId=req-102 event=failed
```

These lines are illustrative. All four events can come from **the same thread** yet belong to **two different requests**. If you filter only by thread name, you will mix together information from `req-101` and `req-102`.

Conversely, a single request can be processed asynchronously:

```text
INFO [http-worker-7]   requestId=req-103 event=request-started
INFO [db-worker-2]     requestId=req-103 event=sql-completed
INFO [http-worker-12]  requestId=req-103 event=response-sent
```

In this case, filtering by thread name will **drop events belonging to the same request**. Choose `requestId` to correlate the business flow, and use thread names to see work distribution and thread handoffs.

Some concurrency issues such as deadlocks, queue backlogs, or starvation may leave clues in thread names and stack traces, but a thread name alone **does not prove** that two operations executed concurrently or in a particular happens-before order. You need to inspect timestamps, event sequences, lock/wait states, metrics, and thread dumps during deep investigation.

## 8. MDC/ThreadContext is different from thread name

In an application using **SLF4J and a backend that supports MDC**, you can attach a temporary correlation ID for the duration of processing:

```java
// Fragment: requestId is generated or validated from the request.
org.slf4j.MDC.put("requestId", requestId);
try {
    handleRequest();
} finally {
    org.slf4j.MDC.remove("requestId");
}
```

The snippet above assumes `handleRequest()` and `requestId` already exist, and that the application has the SLF4J API and a compatible backend/provider.

Points to remember:

- `%thread` reads the **thread name**; `%X{requestId}` reads the **MDC** value.
- MDC is not printed automatically unless the pattern/encoder references it.
- MDC is usually bound to the **thread context**; because thread pools reuse threads, you must clean it up in `finally` so an old request ID is not attached to a new task.
- Tasks handed off to an `ExecutorService`, `CompletableFuture`, reactive stream, or async callback **do not always propagate MDC automatically**. You need a context propagation mechanism compatible with your framework.
- In Log4j 2, the corresponding concept is `ThreadContext`; patterns can read the context map using `%X{requestId}`.

**Common mistake:** Reading `[thread=payment-worker-1]` and treating it as the `requestId`. A single worker executes many transactions sequentially; a thread name does not replace a request identifier.

### Caution with virtual threads

Starting in **Java 21**, Java officially supports virtual threads. Code running on virtual threads may have different naming behavior, and default configurations may leave thread names uninformative. If your application uses virtual threads, do not rely on individual virtual thread names to represent requests or transactions; the number of threads can be very large. Prefer structured logging and explicit context/tracing, along with an encoder/backend tested on your Java runtime.

The main examples in this lesson use Java 17 **platform threads** and do not use virtual-thread APIs unavailable in JDK 17.

## 9. When logging asynchronously: preserve the emitting thread

An async logging pipeline typically looks like this:

```text
order-worker-1
   |
   | logger.info(...)
   v
Log event (contains metadata at emission time)
   |
   v
Queue
   |
   v
async-logging-consumer
   |
   v
Layout/encoder -> file/console
```

An important question: **does the pattern display the thread of the event emitter or the worker writing the log?** With Logback/Log4j 2, a log event's thread fields are designed to describe the emitter when the backend captures the event properly, even when the layout is applied later. Still, you should check the implementation, event snapshot, deferred processing, and async appender in use.

If you write a custom formatter like:

```java
// Do not use this to infer the origin thread in an asynchronous formatter.
String name = Thread.currentThread().getName();
```

then `name` could be `async-logging-consumer`, **not** `order-worker-1`. In JUL, if you only need the origin ID, `LogRecord.getLongThreadID()` provides the event's metadata. If you need the **origin name**, you must capture it when emitting the log and store it with the record/structured event, or use a backend that already provides this field.

Beyond thread metadata, async logging also requires attention to queue capacity, ordering, batching, flush/shutdown, full-queue behavior, and drop/backpressure policies. A pattern with the right thread name does not guarantee logs will not be lost during process shutdown.

### How are thread names and stack traces related?

A stack trace in an exception describes the frames where the exception was created/thrown or captured, whereas the event's thread name indicates the thread that **emitted the log**. If an exception is caught on one thread and passed to another thread for handling, these two pieces of information may not share the same execution context. When analyzing, look at the cause chain, log site, request ID, and task relationships—do not rely on the thread name to infer that the stack trace was generated on the same thread.

## 10. Formatting threads in structured JSON logging

For centralized logging, JSON is often more suitable than a text pattern that is hard to parse. Illustrative example of an event:

```json
{
  "timestamp": "2026-11-09T08:15:12.038Z",
  "level": "INFO",
  "logger": "com.example.order.OrderService",
  "thread": {
    "name": "order-worker-1",
    "id": 37
  },
  "requestId": "req-17",
  "event": "order_reserved",
  "message": "Inventory reservation completed"
}
```

This is **illustrative JSON**, not output from `ThreadFormatDemo`. The actual thread ID value will differ; the field schema depends on the encoder and your project's logging standard. Backends/encoders may use `thread_name`, `thread.name`, `threadId`, or other keys. **Do not assume every backend produces the same JSON schema** just because PatternLayout has `%thread`.

Advantages of structured logging:

1. Separates thread name/ID into dedicated fields for querying.
2. Avoids relying on regex to extract `[thread=...]` from a string.
3. Allows filtering simultaneously by `service`, `logger`, `thread.name`, and `requestId`.
4. A standard encoder handles necessary escaping for string values.

If a collector processes line by line, many systems choose **one JSON object per line per event**. Multi-line pretty-printed JSON may require multiline collector configuration; do not assume one log event equals one physical line when the formatter inserts newlines in messages or stack traces.

Even when using JSON, do not put sensitive data such as tokens, passwords, or session cookies into thread names or MDC. Thread metadata does not need to contain user identities.

## 11. Common pitfalls when formatting threads

| Symptom | Common cause | How to resolve |
| --- | --- | --- |
| Thread name missing | Pattern does not use `%thread` or another backend is active | Check config file, provider/backend, and actual layout |
| Logback prints `%T` or parser error | Using Log4j 2's thread ID token in Logback | Use `%thread` for name; choose a suitable ID encoder/converter |
| Log4j 2 does not display ID | Pattern uses `%t` for name rather than `%T` | Check `%T`/`%threadId` and backend version |
| JUL prints literal `%thread` | JUL SimpleFormatter does not use Logback-style PatternLayout | Write a Formatter or choose another backend |
| Log shows `async-consumer` instead of origin name | Custom formatter reads `Thread.currentThread()` on writer thread | Capture thread at event emission time |
| Multiple requests share the same thread name | Thread pool reuses workers | Use `requestId`/trace ID to correlate business flow |
| Same request has multiple thread names | Task hopped across executors/async boundaries | Propagate correlation context across threads |
| MDC retains ID from an old request | `ThreadLocal`/MDC not cleaned up after handling | Clean up in `finally`, verify worker reuse |
| Log missing request ID despite having `%thread` | Thread field and MDC are two separate data sources | Populate MDC and reference `%X{requestId}` |
| Thread ID does not match OS tool number | JVM ID is not necessarily the native TID | Do not cross-reference directly without a mapping |
| Thread name changes between two records | Thread was renamed or multiple JVMs use the same name | Check timestamp, thread ID, and service/instance |
| Log file duplicated after adding pattern | Two appenders or additivity/propagation | Check logger → appender routing configuration |
| Logging works but is too slow | Expensive formatting, I/O, stack traces, or excessive flushing | Reduce unnecessary events, choose suitable async/encoder, and measure |

**Most common conceptual mistake:** Thinking that a thread name always identifies a request. It is an investigative tool for **execution paths**, not a unique correlation key for business operations.

## 12. Testing formatters/layouts in a real system

When configuring a thread pattern, verify at least these cases:

1. **Main thread:** an event emitted on the main thread; the name appears in the pattern.
2. **Explicitly named thread:** an event from `new Thread(task, "order-worker-1")`; the pattern logs the right origin.
3. **Thread pool reuse:** two different tasks run on the same worker; `requestId` differs even though the thread name is the same.
4. **Thread handoff:** a single request passes through two executors; the correlation ID is not lost.
5. **Exception:** stack trace is preserved, and thread metadata is attached to the right event.
6. **Async appender:** the thread field reflects the emitter rather than the consumer thread.
7. **Structured encoder:** thread name/ID is written to the expected key with proper escaping.
8. **Security:** no secret data in thread names or context.
9. **Actual backend:** Logback or Log4j 2 is selected as configured; not just SLF4J API missing a provider.
10. **Collection destination:** stdout/stderr, files, and collectors receive the right fields without truncating messages or merging records incorrectly.

Example of verifying by inspecting logs:

```text
INFO [thread=order-worker-1] requestId=req-17 event=started
INFO [thread=order-worker-1] requestId=req-18 event=started
INFO [thread=order-worker-2] requestId=req-17 event=completed
```

This is illustrative data. If a query wants to track the progress of request `req-17`, selecting `requestId=req-17` finds events on both worker-1 and worker-2; filtering by `order-worker-1` would miss the final event and mistakenly include part of `req-18`.

## 13. Checklist for bringing thread formatting to production

- **Clear purpose:** thread names serve concurrency, thread pool, and thread dump diagnostics; request IDs serve business correlation.
- **Backend-accurate pattern:** Logback uses `%thread`/`%t`; Log4j 2 uses `%t` for name and `%T` for ID; JUL needs a different mechanism.
- **Capture at the right time:** if async, do not read `Thread.currentThread()` in the consumer formatter and treat it as the origin thread.
- **Useful thread names:** use a ThreadFactory/executor creation point, avoiding dynamic names per user or transaction.
- **Keep other metadata:** full timestamp with timezone, level, logger, exception, and correlation ID when needed.
- **Collector-friendly format:** backend/encoder and collector agree on encoding, escaping, and line splitting.
- **Consider virtual threads:** when upgrading the JVM and threading model, re-evaluate the usefulness of thread names.
- **Security and performance:** do not put secrets/PII into thread names or MDC; measure layout overhead and event volume.
- **Real verification:** test at least main thread, named worker, executor reuse, cross-thread, and async logger in staging.

**Conclusion:** “Thread formatting” is the inclusion of **emitting-thread metadata** in a formatter/layout. The thread name helps reveal the execution thread; the thread ID can assist internal correlation within a JVM; but neither **replaces a request ID or trace ID**. Choosing the right conversion word for Logback/Log4j 2 or handling JUL explicitly, while preserving thread metadata before logs enter a queue, produces reliable records when investigating concurrent Java applications.

## Official reference documentation

- Oracle Java 17, `LogRecord`: https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/LogRecord.html
- Oracle Java 17, `Thread`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html
- Logback, `PatternLayout`: https://logback.qos.ch/manual/layouts.html
- Apache Log4j 2, `PatternLayout`: https://logging.apache.org/log4j/2.x/manual/pattern-layout.html
