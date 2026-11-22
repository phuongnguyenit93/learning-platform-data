# Logger Reception in Java Logging Architecture

## 1. Logger as the Event Entry Point

In a logging architecture, a **Logger** is the object that application code calls when it wants to report an event: an operation starting, successful processing, a warning, an error, or diagnostic information. The Logger receives the log request, checks whether the event is allowed to proceed, creates or receives a log record, and forwards valid records to the output processing component.

An important distinction: **calling a logger does not mean the log has been successfully written to a file, console, or centralized system**. The Logger is the entry point of the pipeline; a **Handler** in `java.util.logging` (JUL), or an **Appender** in many other logging backends, is what is responsible for delivering data to the output destination. A Formatter/Encoder decides how it is represented. Asynchronous logging, buffering, I/O errors, and filter policies can prevent a record from appearing at the destination.

General model:

```text
Application code (business logic)
        |
        | logger.info(...), logger.log(...)
        v
      Logger
        |-- Check logger's effective level
        |-- Create/receive LogRecord or equivalent event
        |-- Check Logger Filter (if any)
        v
   Handler/Appender (possibly multiple destinations)
        |-- Check its own level/filter
        |-- Formatter/Encoder
        v
  console / file / queue / log collection system
```

In **JUL**, a `LogRecord` can also be forwarded to the handlers of parent loggers if using parent handlers is enabled. This is a **forwarding branch**, not a new logger call from the application. The exact order and mechanism vary across JUL, Logback, Log4j 2, and other backends; the diagram above shows the general responsibilities, while the Java examples below use JUL built into JDK 17.

**When do you need to understand Logger?** When logs do not appear even though `info()` was called, when an event is written twice, when you want to enable DEBUG/FINE for the right component, when logs from multiple requests get mixed together, or when you need to ensure the logger does not become a performance bottleneck.

## 2. Distinguishing Pipeline Components

| Component | Primary Responsibility | Question It Answers |
| --- | --- | --- |
| Caller code | Determines which events are worth logging, their level, and context data | “What just happened?” |
| Logger | Receives the call, applies eligibility conditions, creates/forwards the event | “Should this event enter the logging flow?” |
| LogRecord/event | Carries the message content, level, parameters, exception, and metadata | “What does a log event contain?” |
| Filter | Accepts or rejects a record based on rules | “Is this record allowed through?” |
| Handler/Appender | Receives the event and outputs it to one or more destinations | “Where will the log be sent?” |
| Formatter/Encoder | Converts the event into a text line, JSON, or another format | “How is the log represented?” |
| Log collector/storage | Ingests, stores, indexes, searches, and applies retention | “Where can logs be searched and how long are they kept?” |

**JUL and SLF4J do not play the same role.** `java.util.logging.Logger` is a logger belonging to the JUL API/implementation bundled with the JDK. `org.slf4j.Logger` belongs to **SLF4J**, a facade API; the application calls SLF4J and the configured backend (such as Logback or Log4j 2 via the appropriate binding/provider) executes the corresponding pipeline. Do not assume every backend uses `LogRecord`, `Handler`, or the same level inheritance rules as JUL.

A good separation of responsibilities is: business code chooses the **message and context**, while logging configuration chooses the **level, filters, format, and output destinations**. That way, changing a log file or JSON structure does not force changes across all business code.

## 3. How a Logger Processes a Call

Example of a successful processing call:

```java
logger.log(
        Level.INFO,
        "event=order.created orderId={0}",
        orderId
);
```

The snippet above is a **code fragment**, assuming `Logger logger` and `orderId` are already defined; a complete runnable program example is in section 7.

For a typical call in JUL, the sequence can be described step by step:

1. **The application creates a log request:** chooses the level, message or message supplier, parameters, and exception if any. Java expressions passed as arguments are already evaluated before the logger method is invoked, except for work deferred using a `Supplier`.
2. **The Logger checks the effective level:** if the level is disabled, the call ends without emitting an event. `isLoggable(Level)` lets you check whether logging is enabled at a given level, but it does not guarantee that downstream filters/handlers will accept the record.
3. **Create or receive `LogRecord`:** the record holds the level, message, logger name, and optionally parameters, throwable, source information, and timestamp. Across different overloads, the exact moment the record is created can vary; you should not rely on every overload always creating `LogRecord` at the exact same step.
4. **Logger Filter (if configured) decides whether to proceed or drop:** this is an additional filtering step beyond the level check.
5. **Dispatch to Handlers:** each handler checks its own level and filter, then outputs or drops the record; the logger may also forward the same record up to ancestor handlers when `useParentHandlers=true`.
6. **Formatter and output destination process the record:** the message pattern/parameters are formatted, errors may include a stack trace, and data is written or buffered according to the handler's mechanism. Success in steps 1–5 does not prove the storage destination has durably received it.

You can visualize the filtering branches as:

```text
logger.log(...)
    |
    v
Does Logger allow the level? -- no --> discard
    |
   yes
    v
Does Logger Filter accept? -- no --> discard
    |
   yes
    v
Handler A (level + filter) --> console
    |
    +--> Handler B (level + filter) --> file
    |
    +--> Parent logger Handlers (if enabled)
```

Each handler can have a different policy: INFO and above to the console, WARNING and above to an alert channel, or logs with a dedicated format for a centralized system. The Logger does not need to open files itself to achieve this.

## 4. Levels Determine Whether an Event Is Accepted

JUL defines the following common levels, from more severe to more detailed:

| Level | Common Meaning |
| --- | --- |
| `SEVERE` | Serious error with major impact |
| `WARNING` | Recoverable issue, risk, or abnormal behavior |
| `INFO` | Notable operational event |
| `CONFIG` | Configuration and initialization information |
| `FINE` | Details for debugging |
| `FINER` | More detailed than `FINE` |
| `FINEST` | Most detailed among the standard levels |

`OFF` disables logging at that logger threshold; `ALL` enables all levels at that threshold. JUL compares the numeric value of levels: the event's level must be greater than or equal to the effective threshold to pass the logger check. Handlers, in turn, have **independent thresholds**.

Example:

```java
logger.setLevel(Level.INFO);
handler.setLevel(Level.WARNING);

logger.info("request.completed");      // Passes logger; this handler drops it
logger.warning("dependency.timeout"); // Passes both logger and handler
logger.fine("cache.hit");             // Logger drops it before reaching handler
```

This snippet illustrates the mechanism; it is not a standalone Java program. A call to `logger.isLoggable(Level.INFO)` with the configuration above can return `true`, yet `INFO` still will not appear on the `WARNING` handler. In addition, logger filters and handler filters can also drop the record.

**Change levels in the right place:** when you want to see `FINE` logs for a class, check the logger level, handler/appender level, filters, parent loggers, and the forwarding path. Raising the level on only one side may not be enough. Avoid enabling the most detailed level across the entire application long-term because of event volume, CPU and I/O cost, and the risk of exposing sensitive data.

## 5. Naming, Hierarchy, and Scoping Loggers Properly

In Java, the standard way to identify a logger is by using the class name:

```java
private static final Logger LOG =
        Logger.getLogger(OrderService.class.getName());
```

This is an **illustrative snippet inside the `OrderService` class**, importing `java.util.logging.Logger`. The logger name will be the fully qualified class name, for example `com.example.orders.OrderService`. Stable names make it easy to filter logs by package, class, or component. Avoid naming loggers per `requestId`, per user, or with random IDs, as that makes configuration difficult and creates too many loggers.

JUL organizes **named loggers into a hierarchy**. For example:

```text
""                             root logger
  com
    com.example
      com.example.orders
        com.example.orders.OrderService
```

The actual hierarchy depends on the loggers that have been created and managed in `LogManager`; dot-separated names help JUL determine the closest matching ancestor relationship.

If a `Logger` does not set its own level (`setLevel(null)`), **the effective level threshold is inherited from the nearest parent logger that has a level set**, ultimately falling back to root. A standalone conceptual example:

```java
Logger parent = Logger.getLogger("demo.orders");
parent.setLevel(Level.WARNING);

Logger child = Logger.getLogger("demo.orders.PaymentService");
child.setLevel(null); // Inherits WARNING
child.info("payment.started"); // Dropped by effective level
```

**Level inheritance is different from forwarding to parent handlers.** In JUL:

- `setLevel(null)` affects the logger's effective level.
- `setUseParentHandlers(false)` stops dispatching records to handlers belonging to parent loggers; it **does not automatically break level inheritance**.
- Once a child logger has accepted a `LogRecord`, forwarding it to a parent logger's handlers does not mean the parent logger will re-run all of its own level/filter checks. A handler attached to the parent logger still applies **that handler's** own level and filter.
- A parent logger may carry the root's default handler. If the same type of output is configured on both the child logger and a parent logger, logs may be printed twice. Check the handler tree and `useParentHandlers` before assuming your code called log twice.

An application typically uses one logger per class/component and manages levels/outputs in centralized configuration. In framework-based projects, avoid creating custom handlers inside every class: doing so easily causes duplicate logs, extra file descriptors, and hard-to-manage configuration.

## 6. What Types of Information Does a Logger Accept?

### 6.1. Static Messages and Parameters

```java
logger.info("event=service.ready");
logger.log(Level.INFO, "event=task.finished taskId={0} durationMs={1}",
        new Object[] { taskId, elapsedMs });
```

In JUL, placeholders `{0}`, `{1}` use `java.text.MessageFormat` parameter formatting rules when formatted by an appropriate formatter. This **differs** from the `{}` syntax common in SLF4J. The exact output may depend on the locale/formatter; use structured data formats when machine readability and cross-locale stability are required.

Do not mix format placeholders with uncontrolled arbitrary data. When strong searchability is needed, prefer stable fields such as `event=task.finished`, `taskId`, `outcome`, `durationMs`, and `errorCode`.

### 6.2. Exceptions and Stack Traces

```java
try {
    callDependency();
} catch (IOException ex) {
    logger.log(Level.WARNING,
            "event=dependency.failed operation=loadConfig", ex);
}
```

This is a **code fragment inside a method**, with `IOException`, `callDependency()`, and `logger` declared in context; it is not a standalone runnable example. The overload accepting a `Throwable` stores the exception in the record so the handler/formatter can include the error type and stack trace in the log. Do not replace it with `logger.warning(ex.getMessage())` and lose the calling context; likewise, avoid printing the same stack trace at every layer if the error is already logged at the responsible boundary.

A `catch` block that only logs and swallows an exception can leave the application running in an invalid state. You must explicitly decide whether to handle, retry, transform, or rethrow the error based on the business contract.

### 6.3. Suppliers for Deferred Message Construction

```java
logger.fine(() -> "state=" + expensiveSnapshot());
```

When the `FINE` level **is not allowed by the logger**, JUL does not need to invoke the `Supplier<String>` to build the message. By contrast:

```java
logger.fine("state=" + expensiveSnapshot());
```

here `expensiveSnapshot()` is already called by Java before `logger.fine(...)` runs, even if the log is dropped by level. A `Supplier` only defers **message construction**; it does not defer computations already performed to build arguments beforehand. Also, do not assume the supplier is guaranteed never to run if a **downstream filter or handler** rejects the record: the supplier may be invoked after passing the level check but before that rejection step.

Log messages should avoid side effects; do not update business state, count transactions, or make API calls just because a log branch is enabled. If expensive metadata is needed, check `isLoggable()` or design the data to already be available, while understanding the costs at downstream stages as well.

### 6.4. Request/Job Correlation Context

A Logger receives both the event and contextual information together. For example, in a system handling multiple concurrent requests:

```text
INFO event=request.start requestId=req-18 operation=checkout
INFO event=request.start requestId=req-19 operation=search
INFO event=request.end   requestId=req-18 outcome=success durationMs=24
INFO event=request.end   requestId=req-19 outcome=failed errorCode=UPSTREAM_TIMEOUT
```

`requestId` helps correlate events even when logs interleave. For distributed systems, add `traceId` and `spanId` according to the tracing standard in use. JUL does not natively provide an MDC mechanism like the API commonly seen in SLF4J/Logback; context can be passed via parameters, wrappers, `LogRecord`, or an appropriate supporting library. If a framework uses MDC/ThreadLocal, **context must be propagated when switching to another thread/executor and cleared or restored at the end of the scope** to avoid attributing a request ID to a later task.

Data written to logs should be selective. Do not log passwords, tokens, payment card details, personal data, or full requests/responses by default. `requestId`, error codes, durations, and controlled business keys are usually far more useful than a large payload.

## 7. Java 17 Example: Observing a Logger Accepting and Dropping Events

The example below runs standalone with only the JDK, using `java.util.logging` to test four scenarios:

1. `INFO` is accepted when the logger is set to `INFO`.
2. `FINE` is dropped when the logger level does not allow it yet, and the message supplier is not invoked.
3. `INFO` is rejected by the logger filter matching the `event=noise` prefix.
4. `WARNING` is formatted with a parameter; after switching the logger to `FINE`, the `FINE` record is accepted.

To keep output predictable, the program attaches a `StreamHandler` writing to `System.out`, a formatter printing the level and message, calls `flush()` after each event, and disables forwarding to parent logger handlers. In a real application, centralized handler/formatter configuration is more appropriate.

Save the file as **`LoggerReceptionDemo.java`**:

```java
import java.util.concurrent.atomic.AtomicInteger;
import java.util.logging.Formatter;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;
import java.util.logging.StreamHandler;

public final class LoggerReceptionDemo {
    private static final Logger LOG =
            Logger.getLogger(LoggerReceptionDemo.class.getName());

    public static void main(String[] args) {
        Handler output = new StreamHandler(System.out, new Formatter() {
            @Override
            public String format(LogRecord record) {
                return record.getLevel().getName() + " "
                        + formatMessage(record)
                        + System.lineSeparator();
            }
        }) {
            @Override
            public synchronized void publish(LogRecord record) {
                super.publish(record);
                flush();
            }
        };

        output.setLevel(Level.ALL);
        LOG.setLevel(Level.INFO);
        LOG.setUseParentHandlers(false);
        LOG.setFilter(record ->
                !record.getMessage().startsWith("event=noise"));
        LOG.addHandler(output);

        AtomicInteger supplierCalls = new AtomicInteger();

        try {
            LOG.info("event=logger.ready");

            LOG.fine(() -> {
                supplierCalls.incrementAndGet();
                return "event=debug.suppressed";
            });

            LOG.info("event=noise.heartbeat");

            LOG.log(Level.WARNING, "event=retry attempt={0}", 2);
            LOG.info("event=supplier.counter count=" + supplierCalls.get());

            LOG.setLevel(Level.FINE);
            LOG.fine(() -> "event=debug.accepted count="
                    + supplierCalls.incrementAndGet());
            LOG.info("event=supplier.counter count=" + supplierCalls.get());
        } finally {
            output.flush();
            LOG.removeHandler(output);
            LOG.setFilter(null);
        }
    }
}
```

Compile and run from the directory containing the file:

```bash
javac LoggerReceptionDemo.java
java LoggerReceptionDemo
```

**Exact expected stdout for this program:**

```text
INFO event=logger.ready
WARNING event=retry attempt=2
INFO event=supplier.counter count=0
FINE event=debug.accepted count=1
INFO event=supplier.counter count=1
```

**Result analysis:**

- `event=logger.ready` passes the `INFO` threshold and the filter.
- The first `LOG.fine(...)` call does not pass the `INFO` level, so the supplier does not run and `supplierCalls` remains `0`.
- `event=noise.heartbeat` meets the `INFO` threshold but is blocked by the logger filter, so no corresponding line appears.
- `WARNING` is accepted and `Formatter.formatMessage` replaces `{0}` with `2`.
- When the level is changed to `FINE`, the `fine(Supplier)` call is accepted and the supplier increments the counter to `1`. The handler has level `ALL`, so it prints `FINE` as well.
- `setUseParentHandlers(false)` prevents parent console handlers from receiving the record again, keeping the example free of duplicate output.
- `output.flush()` flushes any remaining data in the handler; the example **does not call `output.close()`** because closing a `StreamHandler` that owns `System.out` can close stdout itself. Real applications should manage handler lifecycles according to the backend.

You can try changing `output.setLevel(Level.ALL)` to `output.setLevel(Level.WARNING)`: the output will then contain only `WARNING event=retry attempt=2`, because all `INFO` and `FINE` lines are dropped by the handler. This is a direct way to observe that Logger acceptance and Handler output are **two separate decisions**.

## 8. Logger, Performance, and Multithreading

### 8.1. Logging Costs Appear at Multiple Points

Even when no log is emitted, building arguments via string concatenation or serialization before the logger call still incurs cost. When accepted, an event can consume additional CPU to create a `LogRecord`, determine caller information, evaluate filters, format stack traces, generate JSON, perform synchronous I/O, or enqueue onto a queue. Avoid formatting large objects, issuing extra DB queries, making network calls, or reading entire payloads solely for logging.

Use appropriate levels, message suppliers where suitable, and concise context fields. If the system uses sampling or rate limiting, apply it by event type and severity; **never let log reduction hide critical errors or mandatory audit trails**.

### 8.2. Multiple Threads Sharing a Logger

Typically, **one logger per class/component is shared across multiple threads**; there is no need to create a new logger for every request. JUL is designed to support logging from multiple threads, but output completion order does not always reflect the full causal order of the program, especially when handlers are asynchronous or an event goes through multiple destinations.

Do not use the line order between two independent requests as proof of which request finished first when IDs, timestamps, or traces are missing. When writing custom Handlers/Formatters, account for concurrent access as well as flush, resource closing, and write-error policies. For asynchronous loggers, the method returning may only mean the event was accepted into a queue; a full queue, lost buffer, or crash can still cause logs to disappear.

### 8.3. Logger Does Not Replace Error Handling

A call to `logger.severe(...)` **does not automatically fix an error, retry, roll back, or turn a method's outcome into a failure**. Business code must decide the control flow independently of logging. Do not log a “success” event before the critical operation actually completes; if a transaction is involved, distinguish processing-step success from commit success.

Similarly, audit requirements may demand durable, immutable storage and dedicated access controls; do not assume an application logger satisfies all audit requirements.

## 9. Diagnosing Common Symptoms

| Symptom | Check in Logical Order |
| --- | --- |
| Called `logger.fine()` but nothing appears | Effective logger level → logger filter → each handler's level/filter → parent handlers → output destination |
| `isLoggable(INFO)` returns `true` but no line appears | Logger filter, Handler filter/level, formatter, output destination, flush, and collector configuration |
| Log appears twice | Handlers attached to both child and parent loggers, or the same handler/destination configured twice |
| Logs print to stderr instead of stdout | JUL's default ConsoleHandler typically writes to stderr; check the actually configured handler |
| Logger calls are too slow | String concatenation/serialization before the call, stack traces, formatter, synchronous file/console I/O, locks, and backpressure |
| Logs from two requests are mixed | Add requestId/traceId; propagate context across threads/executors; restore or clear context after work completes |
| Only error message appears, no stack trace | Check whether `Throwable` was passed to the appropriate overload; check whether formatter/backend outputs throwables |
| Events disappear on abrupt shutdown | Handler/queue/collector buffers, shutdown and flush; `SIGKILL`/crash does not guarantee everything is written |
| Too many logs after enabling FINE | Narrow logger name, level, and duration; apply appropriate sampling, control cost and secrets |

A practical investigation approach is to **walk the pipeline from left to right**: did the application make the call → did the logger accept the level/filter → did the handler receive it → did the formatter produce output → did the destination/collector store it. Each question tests a specific boundary rather than raising the level for the entire application and hoping logs show up.

## 10. Logger Design Quality Checklist

When reviewing a logging module, verify the following points:

- Loggers have stable names, typically by package/class; do not generate loggers with dynamic request/user names.
- Application code accurately specifies `event`, level, context, outcome, and cause; logging does not cause business side effects.
- Effective levels, logger filters, handler levels/filters, and parent propagation are configured as needed.
- Every important log has a deterministic path to its output destination; logger acceptance is not mistaken for durable storage.
- `requestId`/`traceId` are present when tracing is needed; context does not leak across asynchronous tasks.
- Exceptions are logged at the appropriate boundary, with stack traces when needed; avoid duplicate logging or logging and swallowing errors.
- Logs do not expose sensitive data; verbosity, sampling, retention, and cost are appropriate.
- Actual behavior is tested for: disabled levels, filter rejections, handler rejections, multiple parent handlers, output failures, shutdown, and multiple threads.

**Conclusion:** The Logger is the **entry point and frontline decision-maker** of a logging system. Understanding level acceptance, event filtering, record creation, and handler dispatch helps you configure logging accurately, reduce redundant records, avoid losing signals during incidents, and clearly distinguish between “the application called log” and “the log reached storage.”
