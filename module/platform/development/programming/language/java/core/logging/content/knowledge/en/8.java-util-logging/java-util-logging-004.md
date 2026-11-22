# JUL Handlers — Log Destinations and Processing in Java Util Logging

## 1. What is a Handler?

In **Java Util Logging (JUL)**, `java.util.logging.Handler` is the component that **receives a `LogRecord` from a `Logger`, decides whether to publish that record, formats it when needed, and forwards it to an output destination** such as the console, a file, or a network connection. JUL is the logging system bundled with the JDK, requiring no additional libraries to use its core classes.

A call such as:

```java
import java.util.logging.Logger;

Logger logger = Logger.getLogger("com.example.orders");
logger.info("Order accepted");
```

creates a log record using the JUL mechanism. However, **Logger and Handler have two distinct responsibilities**:

- **Logger** is where the application emits events: logger name, level threshold, logger filter, parent/child logger hierarchy, and the list of handlers attached to it.
- **Handler** is the output processing point: its *own* level threshold and filter, formatter, encoding, flush, close, and record destination.

An application can attach **multiple handlers to the same logger**. A `WARNING` might be sent to both the console and a file, while `INFO` is only sent to the file. This is an event distribution feature, not Java automatically "promoting" INFO to WARNING.

**Important distinction:** A JUL Handler is not an HTTP controller handler, a Spring exception handler, or a thread handler. In other logging frameworks, the equivalent component is often called an *appender* (Logback, Log4j 2), though the APIs and configuration rules are not identical.

## 2. How a LogRecord Flows Through Logger and Handler

A simplified model:

```text
Java code
   |
   | logger.info(...) / logger.warning(...)
   v
Logger (Logger level + filter)
   |
   +-- Rejected ---------> Record not emitted
   |
   +-- Accepted ---------> LogRecord
                              |
                  +-----------+-----------+
                  |                       |
              Handler A               Handler B
            (level, filter)         (level, filter)
                  |                       |
              Formatter               Formatter
                  |                       |
             Console/file              Network
                  |
             Flush / close
                  |
          Collector / storage (if any)
```

Steps to understand:

1. **The application creates an event:** Java code invokes a logging method. A `LogRecord` typically contains the level, message, logger name, timestamp, parameters, and a `Throwable` if passed.
2. **The Logger checks the level:** for example, a logger configured with `Level.INFO` will not accept a `FINE` record, but can accept `INFO`, `WARNING`, and `SEVERE`.
3. **The Logger applies its own filter** if one is set. Events dropped here do not reach any handlers.
4. **The Logger forwards the record** to its attached handlers. If `useParentHandlers` is enabled, the record may continue up to the parent logger's handlers.
5. **Each Handler independently evaluates** its own level and filter. Handler A may output a record while Handler B discards it.
6. **The Handler outputs the record** using the appropriate formatter and encoding; the destination may be stdout/stderr, a file, or a socket. Sending a record to a sink does not guarantee it has reached a central log store.

**A subtle JUL detail:** when a record is propagated to a parent logger's handlers, **the parent logger's level threshold and filter are not re-applied to a record already accepted by the child logger**; the filter on the parent's handler itself still applies. Therefore, you cannot use the root logger's level as proof that all handlers attached to root will only receive records at or above that level. Always check the emitting logger's level, the target handler's settings, and propagation together.

With `Logger.setLevel(null)`, a logger can **inherit its level** from an ancestor logger according to JUL rules; `Handler.setLevel(...)` is a separate threshold on the handler itself. These are two different configuration points.

## 3. Built-in Handlers in the JDK

JUL provides several built-in handler types. Common classes include:

| Handler | Purpose | Suitable Use Cases and Limitations |
| --- | --- | --- |
| `ConsoleHandler` | Outputs records to `System.err` by default. | Suitable for console logging; formatting and threshold are affected by JUL configuration. Does not turn logs into durable storage on its own. |
| `FileHandler` | Writes logs to files; supports filename patterns, size limits, and rotation via configuration. | Requires managing file paths, write permissions, disk capacity, rotation/retention, and file collection. |
| `StreamHandler` | Writes through a provided `OutputStream` and `Formatter`. | Suitable when you want control over the output stream; requires careful handling of flush and stream lifecycle. |
| `SocketHandler` | Sends records over a socket connection to a remote destination. | Network-dependent; does not guarantee retries, exactly-once delivery, or durable storage by default. |
| `MemoryHandler` | Buffers a number of records in memory and pushes them to a target handler when a push condition is met. | Helps preserve context leading up to a critical event; **not** a multi-threaded async queue or durable log store. |

### ConsoleHandler

`ConsoleHandler` is useful when an application runs under a supervisor or container that captures stderr. It writes to stderr by default, so when a tutorial requires **exact stdout**, you should use `StreamHandler(System.out, formatter)`, as shown in section 7, or explicitly note which output stream is being observed.

Do not assume that "having `ConsoleHandler` means logs are saved to a file." Capturing stdout/stderr is the responsibility of the runtime or an external collector system.

### FileHandler

Example of configuring a dedicated file handler in an application (illustrative snippet, not a standalone program):

```java
import java.io.IOException;
import java.util.logging.FileHandler;
import java.util.logging.Level;
import java.util.logging.Logger;
import java.util.logging.SimpleFormatter;

Logger logger = Logger.getLogger("com.example.batch");

// The "logs" directory must exist and the running account must have write permission.
FileHandler file = new FileHandler("logs/service-%g.log",
        1_000_000, 3, true);
file.setLevel(Level.INFO);
file.setFormatter(new SimpleFormatter());
logger.addHandler(file);

// When the owner ends the logging lifecycle:
// logger.removeHandler(file);
// file.flush();
// file.close();
```

In the constructor above:

- `"logs/service-%g.log"` is the path pattern; `%g` represents the generation number during file rotation.
- `1_000_000` is the byte size limit for a single file before rotation kicks in.
- `3` is the number of files used for generations; it is not a day-based retention policy.
- `true` requests append mode when possible. Production configurations should verify behavior when files already exist and when multiple processes write concurrently.
- `SimpleFormatter` is a plain-text formatter; it does not produce structured JSON on its own.

A file handler must be **closed by its owning component** when no longer needed, releasing file handles and locks. In applications using a centrally configured logging framework, avoid creating a new `FileHandler` per request.

### MemoryHandler

`MemoryHandler` buffers records in memory and has a *target Handler* that receives them on push. It can help capture trace records leading up to a severe error, but **events sitting in the buffer can be lost if the process exits before a push occurs**. It also does not automatically turn log output into background I/O. If auditing or high durability is required, a dedicated storage and acknowledgment mechanism is needed.

## 4. Key Handler Methods and Properties

`Handler` is an abstract class. When implementing one yourself, the three foundational methods are:

```java
// Illustrative skeleton to understand the Handler contract;
// these methods must be implemented in a real subclass.
@Override
public void publish(LogRecord record) {
    // Select the record and send it to the destination.
}

@Override
public void flush() {
    // Flush buffered data if the sink supports it.
}

@Override
public void close() {
    // Release resources owned by the handler.
}
```

| API | Purpose |
| --- | --- |
| `publish(LogRecord)` | Publishes a record. A custom Handler should check `isLoggable(record)` before processing. |
| `isLoggable(LogRecord)` | Checks whether the record satisfies the handler's `Level` and `Filter`. |
| `setLevel(Level)` / `getLevel()` | Sets/gets the handler's severity threshold. |
| `setFilter(Filter)` / `getFilter()` | Applies a handler-specific filtering policy. |
| `setFormatter(Formatter)` / `getFormatter()` | Chooses how a record is converted to text; not every handler requires text formatting. |
| `setEncoding(String)` / `getEncoding()` | Configures character encoding when supported by the handler; not all sinks use text encoding. |
| `setErrorManager(ErrorManager)` | Specifies the handler's internal error reporting mechanism. |
| `flush()` | Flushes buffers managed by the handler to the underlying layer; **does not guarantee fsync or durable persistence by default**. |
| `close()` | Releases resources owned by the handler; after closing, it should not continue to be used as before. |

Basic pattern for a custom handler:

```java
// Illustration inside a subclass of java.util.logging.Handler.
@Override
public void publish(LogRecord record) {
    if (!isLoggable(record)) {
        return;
    }
    // Safely serialize and send to the sink according to the application's contract.
}
```

**Do not treat `isLoggable` as a data security mechanism.** It filters by level and filter, not by redacting tokens or masking personal data. Formatting and writing must preserve record structure, escape control characters, and enforce data policies before transmission.

### Filter and Formatter Are Two Separate Concerns

- `Filter` decides **whether a record is allowed to proceed**; its primary signature is `boolean isLoggable(LogRecord record)`.
- `Formatter` decides **how the record is represented**; typically implemented via `String format(LogRecord record)`.
- `Formatter.formatMessage(record)` can process parameterized messages and resource bundles according to JUL rules. Do not confuse JUL's `{0}` template style with SLF4J's `{}` placeholders.

For example, one handler might accept all WARNINGs but use a filter to drop common duplicate warning messages, while a second handler can still receive that record if its filter differs. In production, dropping warnings should be decided based on risk and operational value.

## 5. How Logger and Handler Levels Work Together

Suppose:

- A logger named `com.example.orders` has `Level.INFO`.
- Handler A accepts `Level.INFO` and above.
- Handler B only accepts `Level.WARNING` and above.

Then, **with no additional filters**:

| LogRecord emitted by logger | Logger INFO | Handler A INFO | Handler B WARNING |
| --- | --- | --- | --- |
| `FINE` | Blocked | Not received | Not received |
| `INFO` | Accepted | Output | Blocked |
| `WARNING` | Accepted | Output | Output |
| `SEVERE` | Accepted | Output | Output |

This demonstrates that **a logger accepting a record does not mean every handler will output it**. If a handler is attached to a logger with a higher threshold (e.g., a SEVERE logger), setting the handler to ALL cannot "recover" INFO records that the logger already discarded at the source.

JUL has standard levels such as `SEVERE`, `WARNING`, `INFO`, `CONFIG`, `FINE`, `FINER`, `FINEST`, along with `ALL`/`OFF`. Handlers and loggers both use `java.util.logging.Level`, yet their acceptance/rejection configurations are **independent**. Mapping from other frameworks' ERROR/WARN/DEBUG names must be done explicitly—never pass `Level.ERROR` or `Level.WARN` directly to JUL, as those constants do not exist.

### Parent Handlers and Duplicate Logging

JUL loggers form a hierarchy based on their names. A record can be processed by handlers attached directly to a child logger **and** handlers on parent loggers if `useParentHandlers` is enabled. This is sometimes intentional (a shared console plus a module-specific file), but easily causes duplicate output if both point to the console.

```java
// Illustration in application configuration.
Logger appLogger = Logger.getLogger("com.example.orders");
appLogger.setUseParentHandlers(false);
```

Calling `setUseParentHandlers(false)` is only appropriate when you are certain the logger has an alternative handler; otherwise, logs may fail to reach their intended destination. Do not apply it indiscriminately to every logger just to mask duplicate-log symptoms without inspecting the root and handler configuration.

## 6. Configuring Handlers with logging.properties

JUL can read configuration from `logging.properties` via `LogManager`. An illustrative configuration example:

```properties
handlers = java.util.logging.ConsoleHandler
.level = INFO
java.util.logging.ConsoleHandler.level = WARNING
java.util.logging.ConsoleHandler.formatter = java.util.logging.SimpleFormatter
com.example.orders.level = FINE
```

Meaning:

1. `handlers` at the root level specifies the handler classes to configure.
2. `.level = INFO` sets the default level for the root logger.
3. `java.util.logging.ConsoleHandler.level = WARNING` causes the console handler to only output WARNING/SEVERE (unless filtered otherwise).
4. `com.example.orders.level = FINE` allows the application logger to emit FINE records, but FINE **will not necessarily appear on the console** because the handler's threshold is WARNING.
5. `SimpleFormatter` produces plain text in JUL's standard format; it does not default to JSON.

Specify the configuration file when starting the JVM:

```bash
java -Djava.util.logging.config.file=/path/to/logging.properties com.example.Main
```

The path and main class name above are usage examples, **not a command to run the demo in section 7**. In practice, provide your actual config file and application main class; the configuration must be loaded before `LogManager` is initialized for the first time. If your project uses a container/Spring or another logging bridge, determine whether JUL is handled directly or bridged to another backend.

**Do not mix** JUL's `logging.properties` configuration with Logback/Log4j 2 XML. Class names, APIs, and formatter controls are different.

## 7. Standalone Java 17 Example: Two Handlers, Two Policies

The following example demonstrates:

- A Logger allowing only INFO and above.
- One `Handler` accepting INFO and above, writing the prefix `MAIN`.
- A second Handler accepting WARNING and above, with its own `Filter` dropping messages starting with `RETRY`, writing the prefix `ALERT`.
- Both use `StreamHandler` targeting `System.out`, calling `flush()` after each write so output is visible immediately.
- Parent handlers disabled so extra lines from the host machine's JUL configuration are not printed.

Create the file **`JulHandlersDemo.java`**:

```java
import java.util.logging.Formatter;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;
import java.util.logging.StreamHandler;

public class JulHandlersDemo {

    public static void main(String[] args) {
        Logger logger = Logger.getLogger("demo.jul.handlers");
        logger.setUseParentHandlers(false);

        // The demo manages handlers itself for consistent output.
        for (Handler old : logger.getHandlers()) {
            logger.removeHandler(old);
        }

        logger.setLevel(Level.INFO);
        logger.setFilter(record ->
                !String.valueOf(record.getMessage())
                        .startsWith("NOISY"));

        Handler main = stdoutHandler("MAIN", Level.INFO);
        Handler alert = stdoutHandler("ALERT", Level.WARNING);

        // The filter on ALERT does not affect MAIN.
        alert.setFilter(record ->
                !String.valueOf(record.getMessage())
                        .startsWith("RETRY"));

        logger.addHandler(main);
        logger.addHandler(alert);

        logger.fine("Internal detail");
        logger.info("Order O-17 accepted");
        logger.warning("RETRY scheduled");
        logger.warning("Queue capacity nearing limit");
        logger.warning("NOISY repeated signal");
        logger.severe("Payment failed");

        main.flush();
        alert.flush();

        // Do not close these StreamHandlers because they wrap System.out.
        // In a real application, handler lifecycle is owned by the system.
    }

    private static Handler stdoutHandler(String name, Level minimum) {
        Formatter formatter = new Formatter() {
            @Override
            public String format(LogRecord record) {
                return name + " | "
                        + record.getLevel().getName() + " | "
                        + formatMessage(record) + "\n";
            }
        };

        StreamHandler handler =
                new StreamHandler(System.out, formatter) {
                    @Override
                    public synchronized void publish(LogRecord record) {
                        super.publish(record);
                        flush();
                    }
                };

        handler.setLevel(minimum);
        return handler;
    }
}
```

Compile and run with **JDK 17 or later** in the directory containing the file:

```bash
javac -encoding UTF-8 JulHandlersDemo.java
java JulHandlersDemo
```

**Exact stdout** for the program above:

```text
MAIN | INFO | Order O-17 accepted
MAIN | WARNING | RETRY scheduled
MAIN | WARNING | Queue capacity nearing limit
ALERT | WARNING | Queue capacity nearing limit
MAIN | SEVERE | Payment failed
ALERT | SEVERE | Payment failed
```

### Step-by-Step Output Walkthrough

1. `logger.fine("Internal detail")` is rejected at the logger because `FINE` is lower than `INFO`, so no line is printed.
2. `logger.info("Order O-17 accepted")` is accepted by the logger; the `MAIN` handler (level INFO) writes one line; the `ALERT` handler (level WARNING) drops the record.
3. `logger.warning("RETRY scheduled")` meets the level for both handlers; `ALERT`'s filter drops it, so only `MAIN` writes it.
4. `logger.warning("Queue capacity nearing limit")` passes the logger, both handler levels, and filters, producing **two lines**: one for MAIN and one for ALERT. These represent two distinct logical destinations in the demo, not unintended duplication.
5. `logger.warning("NOISY repeated signal")` is dropped immediately by the logger's filter and reaches neither handler.
6. `logger.severe("Payment failed")` passes all policies, producing one line per handler.

`Formatter.format` intentionally **omits timestamps, threads, and code locations** to keep stdout deterministic. In production systems, you should include an offset/UTC timestamp, service name, logger name, correlation/trace ID, and relevant event fields. `Formatter.formatMessage(record)` handles message formatting using JUL rules; producing structured JSON requires a proper serializer/encoder to guarantee valid single-line JSON escaping.

**Why not use `ConsoleHandler`?** `ConsoleHandler` normally writes to stderr and has a default formatter that depends on external configuration, making it harder to guarantee identical stdout across all machines. Here, `StreamHandler(System.out, ...)` lets us label the destination and keep output easy to verify. Both handlers share stdout to demonstrate routing; in real production environments, destinations may be separate consoles, files, or centralized systems.

**Limitations:** This example does not create files, demonstrate durability, perform background logging, or provide retries. Calls run on a single thread so output order is clear. When multiple threads or processes share a sink, you must verify how the backend synchronizes writes and preserves individual record boundaries.

## 8. Writing a Custom Handler: When You Need One and What to Avoid

You should only subclass `Handler` when built-in handlers cannot meet your requirements: a specialized sink, a custom filtering/routing mechanism, or an adapter for an observability system. For standard file, console, or socket logging, prefer configuring existing handlers or the logging backend already used by your project.

A custom handler must address:

- **Input data:** which `LogRecord` fields are used, how `null` is handled, and where `isLoggable(record)` is called.
- **Format/encoding:** which `Formatter` is used, and how newlines, quotes, and sensitive information are escaped.
- **I/O and errors:** if the sink fails, is the log dropped, buffered, retried, alerted, or handled under another contract? Never break business logic because of an unhandled logging exception.
- **Concurrency:** can multiple threads call `publish`? Could writers interleave? If async with a queue, how is a full queue handled?
- **Lifecycle:** who creates, attaches, detaches, flushes, and closes the handler? On shutdown, how long does draining take, and where might data be lost?
- **Access control:** could the sink hold sensitive data, requiring TLS, retention policies, access permissions, and separate auditing?

Minimal design template:

```java
// Illustrates how to structure a custom Handler;
// lacks a concrete class and sink, so it is not a standalone runnable example.
@Override
public void publish(LogRecord record) {
    if (!isLoggable(record)) {
        return;
    }
    try {
        // Format and safely write the record to the chosen sink.
    } catch (RuntimeException ex) {
        // Report errors via ErrorManager per the handler contract;
        // avoid letting logging errors trigger an infinite logging loop.
        reportError("Failed to write log", ex,
                java.util.logging.ErrorManager.WRITE_FAILURE);
    }
}
```

In real code, catch the specific exception types defined by your sink's API, define clear delivery guarantees, and avoid unbounded memory growth. Never have a handler log its own errors through **the same logger it serves**, as that easily causes recursion until resources are exhausted.

### Flush Is Not a Guarantee of Durable Persistence

`flush()` can push data sitting in the handler's buffer to the underlying stream, but **it does not automatically mean fsync, server acknowledgment, indexing, or backup**. If audit-grade evidence is required, you need dedicated acknowledgment, durable write, and loss/duplication detection mechanisms—do not rely solely on calling `flush()`.

### Close Must Belong to the Owner

Closing a `StreamHandler` attached to `System.out` risks closing the shared stdout stream. That is why the demo does not call `close()`. For handlers owning dedicated files or sockets, the owner must call `flush()`/`close()` at the appropriate time and remove the handler from the logger when no longer used. When configuration is managed by `LogManager` or a framework, avoid arbitrarily closing handlers owned by another component.

## 9. Handlers, Asynchronous Processing, and Performance

Standard JUL handlers do not automatically create a background queue for every record. With a slow sink, the `Logger → Handler.publish → I/O` path can force business threads to wait.

```text
Request thread
  |
  +-> Logger -> Synchronous handler -> slow file/network
                                          |
                                      Increased latency

Or in an architecture with a dedicated async queue:

Request thread -> enqueue LogRecord/snapshot -> worker -> handler/sink
                     |
                 Queue full?
                 block / drop / fail / spool per policy
```

To design async logging properly:

1. Decide which work still runs on the request thread: event creation, context capture, serialization, or only enqueuing?
2. Choose a bounded queue to prevent unbounded memory growth.
3. Define behavior when the queue is full: block, drop with a counter, fall back to synchronous logging, or spool durably.
4. Capture important context at **event time**, especially when mutable objects or thread-locals may change.
5. Manage shutdown/drain, retries, duplicates, ordering, and sink failures.
6. Monitor queue depth, dropped record counts, write duration, I/O errors, and ingestion latency.

**MemoryHandler is not a substitute for an async queue:** it is an in-memory buffer with a push condition to another handler, and does not guarantee non-blocking publication or crash recovery.

If a handler writes directly to the network, verify timeouts and exception policies, because a slow sink can degrade application throughput. In containerized environments, a simpler approach is often to write structured logs to the console and let a dedicated collector handle transport and retention; choose the architecture that fits your actual requirements.

## 10. Security and Record Quality Through Handlers

Risks do not disappear just by splitting a logger across multiple handlers:

- **Secret leakage:** passwords, cookies, access tokens, refresh tokens, private keys, and PII can appear in multiple sinks if messages or exceptions are constructed without controls. Apply allowlisting/redaction at the source or before any unauthorized sink.
- **Log injection:** messages containing newlines or control characters can forge additional log lines. Plain-text patterns do not handle every case automatically; JSON Lines requires a properly escaping encoder.
- **Duplicate logging:** the same event routed through both a child logger and a parent logger, or through two handlers pointing to the same destination. Understand routing before randomly removing handlers.
- **Log loss:** logger/handler levels, filters, queues, sink failures, collectors, or retention policies can prevent events from reaching the search store.
- **Missing context:** logging only a message without service name, correlation ID, or event code makes cross-service correlation difficult.
- **Access control:** two handlers writing to different stores may require different read permissions, retention periods, and integrity guarantees.
- **Inconsistent formatting:** sinks using different timezones, charsets, or field names make event correlation harder.

A `Handler Filter` that blocks a message prefix is not a complete data-protection mechanism. If sensitive data has already entered the record, another handler or a parent logger may still emit it. Security should be designed around what data is permitted into an event in the first place.

## 11. Testing Handlers and Troubleshooting

When setting up JUL, include the following checks:

| Test Case | What to Verify |
| --- | --- |
| Logger INFO, handler INFO | INFO, WARNING, SEVERE pass through the handler when accepted by filters. |
| Logger INFO, handler WARNING | INFO is dropped at the handler; WARNING/SEVERE can be output. |
| Logger WARNING, handler ALL | FINE/INFO already dropped by the logger cannot be recovered by the handler. |
| Filter on the logger | Rejected events do not reach any downstream handler. |
| Filter on a single handler | Only that handler drops the event; other handlers can still receive it. |
| Two handlers and parent propagation | Record count matches design, with no unexpected duplication. |
| Formatter with timestamp/parameters/exception | Valid text/JSON with full context; stack traces are not lost. |
| Message with newlines, quotes, and Unicode | Proper encoding/escaping; no forged records or parse errors. |
| File rotation, missing write permission, full disk | Errors are signaled rather than silently dropping critical data. |
| Remote sink failure and recovery | Timeout/retry/drop behavior matches policy without stalling requests indefinitely. |
| Shutdown | Application-owned handlers are flushed/closed; log loss boundaries are understood. |

**Checklist for investigating missing logs:**

1. Confirm the code actually invokes the logger under investigation.
2. Confirm the logger name and effective level (including inherited levels).
3. Check the filter on the logger.
4. Inspect directly attached handlers, `useParentHandlers`, and handlers on parent loggers.
5. Check the level and filter of each handler.
6. Verify the formatter/encoding, output destination (stdout vs. stderr, file path, socket), write permissions, and I/O errors.
7. If a collector is used, check transport, ingest/indexing, query permissions, and retention.

**Why are there two identical lines?** This can happen when two handlers share the same destination, or when handlers exist on both a child logger and root with `useParentHandlers=true`. Audit handler routing before making changes.

**Why do only WARNINGs appear and not INFO?** The logger may accept INFO while the handler is configured at WARNING. Setting a logger to INFO does not force its handlers to output INFO.

**Why does a logger with no attached handlers still produce logs?** It may be propagating `LogRecord`s up to a parent logger's handlers; this is normal JUL behavior when parent handlers are enabled.

## 12. Checklist for Applying Handlers in a Java Project

1. **Choose the API:** is the project using JUL directly, or is JUL bridged to SLF4J/Logback/Log4j 2?
2. **Define routing:** which loggers emit records, which handlers receive them, and is parent propagation enabled?
3. **Configure levels/filters per layer:** have INFO, WARNING, SEVERE, and rejected records been tested?
4. **Choose destinations:** stderr/stdout, file, remote, or collector; who retains and queries logs after they are written?
5. **Formatting:** timestamp and offset, service, correlation ID, level, event name, message, exception, and encoding.
6. **Control risks:** redaction, log injection, access permissions, duplicate logs, and dropped critical events.
7. **Performance:** could synchronous sinks hurt latency; is a queue/spool needed with clear full-queue and shutdown policies?
8. **Lifecycle:** which component owns each handler, who flushes/closes them, and is closing shared stdout avoided?
9. **End-to-end verification:** does a test event flow through the logger, handler, and collector to the query destination as expected?

**Remember:** in JUL, `Logger` determines where events are emitted and performs logger-level filtering; `Handler` determines **how and where each LogRecord is output**. Controlling logging requires understanding levels, filters, formatters, handler sets, the logger hierarchy, and resource lifecycles together. Calling `logger.warning(...)` is only the starting point, not a guarantee that a record has been saved at its final destination.