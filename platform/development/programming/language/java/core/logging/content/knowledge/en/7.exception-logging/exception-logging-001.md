# Logging Stack Traces for Exceptions in Java

## 1. What is a stack trace and why log it?

When a Java program encounters an error, a message like `"Payment failed"` or `"Invalid configuration"` only describes the symptom. To investigate the cause in the source code, developers usually need a **stack trace**: a list of stack frames showing the chain of method calls associated with where a `Throwable` object was created or where its stack trace was updated.

A typical stack trace contains the exception name, message, and frames:

```text
java.lang.IllegalArgumentException: Invalid port: abc
    at Example.parsePort(Example.java:27)
    at Example.main(Example.java:12)
Caused by: java.lang.NumberFormatException: For input string: "abc"
    at java.base/java.lang.NumberFormatException.forInputString(...)
    ...
```

**This is an illustrative example**, not the verbatim output of the program in this lesson: line numbers, JDK frames, and stack truncation depend on the compiled code, Java version, and formatting tool. The `...` notation represents frames omitted for illustration.

An exception object stores important information:

- **Exception type**: `IllegalArgumentException`, `IOException`, `NullPointerException`…
- **Message**: error description, which may be absent.
- **Stack trace**: `StackTraceElement` entries (class, method, file, and line number if available).
- **Cause**: the underlying cause stored via `Throwable.getCause()`; this can form a multi-level chain.
- **Suppressed exceptions**: secondary errors attached to the primary exception, commonly appearing when closing resources with `try-with-resources`.

**Logging a stack trace** in logging usually means passing the **entire `Throwable` object** to the logging framework so the formatter/backend displays the message, frames, cause, and suppressed exceptions according to the configured policy.

> **Distinction:** an exception's stack trace describes the call stack at the time the stack trace was recorded; it is **not** a distributed trace linking requests across multiple services, nor is it the log level named `TRACE` in some frameworks.

## 2. Using printStackTrace: direct but limited

Every `Throwable` object has the following methods:

```java
exception.printStackTrace();               // Defaults to writing to System.err.
exception.printStackTrace(printStream);    // Writes to the provided PrintStream.
exception.printStackTrace(printWriter);    // Writes to the provided PrintWriter.
```

This is a **syntax illustration**, assuming `exception`, `printStream`, and `printWriter` variables already exist.

A simple Java example:

```java
public class PrintStackTraceDemo {
    public static void main(String[] args) {
        try {
            Integer.parseInt("not-a-number");
        } catch (NumberFormatException exception) {
            exception.printStackTrace();
        }
    }
}
```

Compile/run:

```bash
javac PrintStackTraceDemo.java
java PrintStackTraceDemo
```

When run, `printStackTrace()` writes to **`System.err`**, including the `NumberFormatException` name, message, and frames. The JDK-internal portion may vary across Java versions. You should not expect identical line numbers or full output in every environment.

### Limitations of printStackTrace

`printStackTrace()` is useful for learning, small experiments, or viewing errors in a terminal. However, in applications that need managed logging, calling it directly has limitations:

- It does not automatically provide a logger-system level, such as `WARNING` or `SEVERE`.
- It does not automatically include the logger name, request ID, trace ID, or timestamp according to the active logging formatter.
- It writes directly to the specified stream or writer; it may bypass the centralized log pipeline, filters, or application log destination configuration.
- It can cause stack traces to appear on the terminal even when application logging is disabled or directed elsewhere.
- It can produce duplicate logs when both calling `printStackTrace()` and passing the same exception to a logger.

For real-world Java applications, **prefer using a logging API that supports a `Throwable` parameter**, rather than scattering `printStackTrace()` calls throughout business code.

## 3. The right way in Java Util Logging (JUL)

The JDK standard library provides `java.util.logging.Logger`. An important overload is:

```java
logger.log(Level.SEVERE, "Unable to read configuration", exception);
```

This is an illustrative snippet requiring appropriate `logger` and `exception` variables. `Logger.log(Level, String, Throwable)` creates a `LogRecord` with the error object stored in the `thrown` field. When the logger and handler allow the record through, the **formatter** determines how the stack trace is displayed.

An equivalent example when catching `IOException`:

```java
try {
    loadConfiguration();
} catch (java.io.IOException exception) {
    logger.log(
            java.util.logging.Level.SEVERE,
            "Configuration loading failed",
            exception
    );
}
```

This is an **illustrative snippet**, assuming `loadConfiguration()` is an existing method that may throw `IOException`. The third parameter is crucial: if you only log `exception.getMessage()` or `exception.toString()`, the log record **does not contain a reference to the Throwable**, so the formatter typically has no stack trace to display.

Comparison:

| Logging approach | Information the logger receives |
| --- | --- |
| `logger.severe(exception.getMessage())` | Only the message string, no `Throwable` |
| `logger.severe(exception.toString())` | A string with type and message, no stack frames |
| `logger.log(Level.SEVERE, "Operation failed", exception)` | Contextual message **and** the full `Throwable` |
| `exception.printStackTrace()` | Stack trace written directly to stderr/writer, bypassing the logger pipeline |

Not every error is `SEVERE`. When an operation has a reasonable handling/fallback mechanism, `WARNING` or a lower level may be appropriate. Choose the level based on **actual impact**, not the exception class name.

## 4. Runnable Java 17 example: logging a full stack trace with a logger

Create `StackTraceLoggingDemo.java`:

```java
import java.util.logging.ConsoleHandler;
import java.util.logging.Level;
import java.util.logging.Logger;
import java.util.logging.SimpleFormatter;

public class StackTraceLoggingDemo {
    private static final Logger LOG =
            Logger.getLogger(StackTraceLoggingDemo.class.getName());

    private static int parsePort(String input) {
        try {
            return Integer.parseInt(input);
        } catch (NumberFormatException cause) {
            // Preserve the cause to diagnose the root error.
            throw new IllegalArgumentException(
                    "Invalid port configuration: " + input, cause);
        }
    }

    public static void main(String[] args) {
        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.ALL);

        ConsoleHandler console = new ConsoleHandler();
        console.setLevel(Level.ALL);
        console.setFormatter(new SimpleFormatter());
        LOG.addHandler(console);

        try {
            try {
                int port = parsePort("abc");
                LOG.info("Configured port: " + port);
            } catch (IllegalArgumentException exception) {
                // Pass the entire Throwable into the LogRecord.
                LOG.log(Level.SEVERE, "Server startup configuration failed",
                        exception);
            }
        } finally {
            LOG.removeHandler(console);
            console.close();
        }
    }
}
```

Run with JDK 17 or later:

```bash
javac StackTraceLoggingDemo.java
java StackTraceLoggingDemo
```

**Expected output on stderr** (format and line numbers may vary):

- A `SEVERE` record with the message `Server startup configuration failed`.
- The class name `java.lang.IllegalArgumentException` and message `Invalid port configuration: abc`.
- Frames for `StackTraceLoggingDemo.parsePort` and `StackTraceLoggingDemo.main`.
- A `Caused by: java.lang.NumberFormatException` section with the root cause's stack (common frames may be abbreviated).

Abbreviated illustrative format:

```text
<timestamp> StackTraceLoggingDemo main
SEVERE: Server startup configuration failed
java.lang.IllegalArgumentException: Invalid port configuration: abc
    at StackTraceLoggingDemo.parsePort(StackTraceLoggingDemo.java:<line>)
    at StackTraceLoggingDemo.main(StackTraceLoggingDemo.java:<line>)
Caused by: java.lang.NumberFormatException: For input string: "abc"
    ...
```

The `<timestamp>` and `<line>` placeholders are only for the output diagram; in an actual run, `SimpleFormatter` prints the real timestamp and line numbers. The JDK may also print additional `NumberFormatException` frames.

### How it works

1. `parsePort("abc")` calls `Integer.parseInt(...)`, which throws `NumberFormatException`.
2. `parsePort` wraps the error in a new `IllegalArgumentException` while **passing the original error as the cause** to the constructor, preserving the causal link.
3. `LOG.log(Level.SEVERE, "...", exception)` passes the entire object into the log record. There is no need to call `exception.printStackTrace()` again.
4. JUL's `SimpleFormatter` recognizes `LogRecord.getThrown()` and prints the stack trace chain. If you use a custom formatter that only outputs the message, the stack trace may be omitted.
5. `LOG.setUseParentHandlers(false)` prevents forwarding the same record to parent logger handlers, avoiding duplicate logs in this standalone example.
6. `ConsoleHandler` writes to `System.err`. Calling `close()` in `finally` releases the handler created by the demo.

**Calling `Logger.log(...)` does not guarantee you will see a stack trace:** the logger level, handler level, filters, active handlers, and formatter still determine whether the record is emitted and which parts are printed.

## 5. Preserving the cause when wrapping exceptions

A low-level error often needs to be translated into an error type meaningful to the business domain or architectural layer. For example, an `IOException` when reading a configuration file is wrapped into an `IllegalStateException` at the startup layer:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

public static String readSettings(Path path) {
    try {
        return Files.readString(path);
    } catch (IOException cause) {
        throw new IllegalStateException(
                "Cannot load application settings from " + path, cause);
    }
}
```

This is an **illustrative method**; it must be placed inside a class with the appropriate imports. The constructor taking `cause` stores the underlying error. Then, at the handling boundary responsible for reporting errors, log `IllegalStateException` once:

```java
try {
    String settings = readSettings(Path.of("config.txt"));
} catch (IllegalStateException exception) {
    logger.log(Level.SEVERE, "Application initialization failed",
            exception);
}
```

This snippet is also illustrative, assuming `logger` is declared and necessary imports are present. When the formatter supports `Throwable`, the output can include both the wrapper exception and `Caused by: java.io.IOException`.

**Common mistake:**

```java
throw new IllegalStateException("Cannot load settings: " + cause.getMessage());
```

This only copies the message into the new exception **without preserving the cause**; the original error type and `cause` stack trace are detached from the causal chain. Prefer constructors that accept `Throwable cause` when wrapping errors.

Another rule of thumb: if you just want to rethrow the exact caught exception and the declared method signature allows it, `throw exception;` preserves the stack trace attached to that object. Avoid unnecessarily creating a new exception just to record the same content.

## 6. Suppressed exceptions and try-with-resources

In addition to `cause`, `Throwable` also holds **suppressed exceptions** retrieved via `getSuppressed()`. The classic case is `try-with-resources`: the try block body throws an error, and automatically closing the resource throws another error. Java keeps the primary exception and attaches the closing error as a suppressed exception.

Standalone Java 17 example — create `SuppressedTraceDemo.java`:

```java
public class SuppressedTraceDemo {
    static final class BrokenResource implements AutoCloseable {
        @Override
        public void close() {
            throw new IllegalStateException("close failed");
        }
    }

    public static void main(String[] args) {
        try (BrokenResource ignored = new BrokenResource()) {
            throw new IllegalArgumentException("work failed");
        } catch (Exception exception) {
            System.out.println("primary=" + exception.getMessage());
            System.out.println("suppressed="
                    + exception.getSuppressed().length);
        }
    }
}
```

Run:

```bash
javac SuppressedTraceDemo.java
java SuppressedTraceDemo
```

**Exact stdout output:**

```text
primary=work failed
suppressed=1
```

If you call `exception.printStackTrace()` inside `catch` or pass the full `Throwable` to a formatter that supports stack traces, the output will also include `Suppressed: java.lang.IllegalStateException: close failed`. This helps surface resource-closing failures that logging only `exception.getMessage()` would miss.

Distinction:

- **Cause**: an exception that caused or was wrapped beneath another exception.
- **Suppressed**: a secondary exception attached when a primary error already occurred, not necessarily the cause of the primary error.
- **Stack frame**: a single method call location in a `Throwable`'s stack trace.

## 7. Writing stack traces to a log file

The mechanism of **passing the exception to the logger does not change** when the log destination is a file. With JUL, you only need a `FileHandler` and an appropriate formatter:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.logging.FileHandler;
import java.util.logging.Level;
import java.util.logging.Logger;
import java.util.logging.SimpleFormatter;

public static void configureFileLog(Logger logger) throws IOException {
    Files.createDirectories(Path.of("logs"));

    FileHandler file = new FileHandler(
            "logs/errors.%g.log", 1_048_576, 3, true);
    file.setLevel(Level.WARNING);
    file.setFormatter(new SimpleFormatter());

    logger.addHandler(file);
    // Keep a reference to file to close it when the application shuts down.
}
```

This is an **illustrative method** inside a class, not a standalone program. `FileHandler` uses a filename pattern, size limit, file generation count, and append mode. When logging an exception:

```java
logger.log(Level.SEVERE, "Cannot open customer data", exception);
```

`SimpleFormatter` prints the stack trace to the file if the record reaches the handler. If you replace `SimpleFormatter` with a custom formatter that only prints `record.getMessage()`, the file may no longer contain stack traces even though the logger received the exception properly.

Note that `FileHandler` may default to `XMLFormatter` if no formatter is configured. In that case, the file has an XML structure rather than familiar plain-text lines. Choose a formatter suited to your actual log-processing tools, and configure rotation/retention so long stack traces do not fill up the disk.

**Handler lifecycle:** Create the file handler once during initialization and close it at shutdown by the owning component. Never create a new `FileHandler` inside each `catch` block, as doing so causes overhead, file-lock contention, and potentially scatters logs across multiple files.

## 8. Custom formatters can drop stack traces

A minimal formatter often looks like this:

```java
import java.util.logging.Formatter;
import java.util.logging.LogRecord;

Formatter messageOnly = new Formatter() {
    @Override
    public String format(LogRecord record) {
        return record.getLevel() + ": "
                + formatMessage(record) + System.lineSeparator();
    }
};
```

This illustrative snippet only prints the level and message. It **does not use `record.getThrown()`**, so the error's stack trace is omitted from the output even when the application properly calls `logger.log(Level.SEVERE, "error", exception)`.

A custom formatter that wants to display the exception as well can do:

```java
import java.io.PrintWriter;
import java.io.StringWriter;
import java.util.logging.Formatter;
import java.util.logging.LogRecord;

Formatter withThrowable = new Formatter() {
    @Override
    public String format(LogRecord record) {
        StringBuilder result = new StringBuilder();
        result.append(record.getLevel())
              .append(": ")
              .append(formatMessage(record))
              .append(System.lineSeparator());

        Throwable error = record.getThrown();
        if (error != null) {
            StringWriter buffer = new StringWriter();
            error.printStackTrace(new PrintWriter(buffer));
            result.append(buffer);
        }
        return result.toString();
    }
};
```

This snippet is an **illustrative code fragment for use inside a method/class**, with imports placed at the top of the file. `StringWriter` holds text in memory, while `PrintWriter` receives the stack trace from `Throwable.printStackTrace(PrintWriter)`. `StringBuilder.append(buffer)` calls `StringWriter.toString()` to append the content.

Trade-off: this approach allocates a large string containing the stack trace for every record with an exception. Under high-frequency error logging, that can increase memory, CPU, and log volume. Real-world formatters also need timestamps, logger names, correlation info, and consistent formatting; do not replace `SimpleFormatter` with a minimal formatter without thoroughly testing `Throwable` output.

## 9. Logging stack traces with SLF4J / Logback: choosing the right overload

In Java applications using SLF4J with Logback or a compatible backend, multiple log-level methods accept a `Throwable` parameter so the backend can render the stack trace.

Illustrative example **requiring SLF4J and backend dependencies**:

```java
try {
    paymentService.charge(orderId);
} catch (PaymentException exception) {
    log.error("Payment failed for orderId={}", orderId, exception);
}
```

Here `log` is assumed to be `org.slf4j.Logger` and the classes/services exist. When using the appropriate overload/varargs, SLF4J treats the trailing `Throwable` as the event's throwable, while `{}` is the placeholder for `orderId`. Exact API behavior depends on the SLF4J version; verify the backend output when designing formatters or structured logging.

A pattern that easily loses information:

```java
log.error("Payment failed: {}", exception.getMessage());
```

This call only passes the exception's **message string** into the placeholder and normally does not attach a `Throwable`, so no stack frames are included automatically. Likewise, do not build a string from `exception.toString()` assuming the backend still receives the exception object.

In Spring Boot, the SLF4J API is commonly used in application code, while stack trace formatting is controlled by the backend/encoder and logging configuration. `java.util.logging.Logger.log(Level, String, Throwable)` and `org.slf4j.Logger.error(...)` are two different APIs; do not mix their syntax.

## 10. Log once at an appropriate handling boundary

Exceptions often travel through multiple layers: repository → service → controller → HTTP error handler. If every layer catches and logs the entire stack trace, a single root error can appear multiple times.

Example of an undesirable flow:

```text
Repository: SEVERE + stack trace
    ↓ rethrow
Service: SEVERE + same stack trace
    ↓ rethrow
HTTP handler: SEVERE + same stack trace
```

This results in duplicate log lines, makes it harder to tell where the error was actually handled, increases log volume, and can trigger duplicate alerts.

How to choose:

- If a lower layer **cannot handle the error** and only propagates it, it can **throw/wrap while preserving the cause** so the responsible layer decides the log level and response.
- At the **final handling boundary** (such as a job runner, controller advice, message consumer, or entrypoint), log the exception with sufficient context once if the error needs to be reported.
- If a lower layer has special context that cannot be recovered higher up, add that context when wrapping or write a single purposeful log entry, avoiding repeatedly printing the same full stack trace.
- An expected and normally handled exception may only need a lower log level or no stack trace at all; unhandled errors or availability-impacting failures usually need a stack trace for diagnosis.

**There is no rigid rule to "only ever log once"**: in some systems, logging at multiple boundaries serves different purposes. The principle is to avoid duplicating **the exact same information** without adding diagnostic value.

## 11. When should you not log a full stack trace?

Stack traces are helpful, but not every situation needs one:

| Situation | Recommendation |
| --- | --- |
| Unexpected programming exception, failed task | Log the full `Throwable` at an appropriate boundary |
| I/O error, timeout, database connection failure of unknown cause | Log the full stack trace with safe context |
| Frequent validation failures, expected bad user input | Log briefly or use metrics to avoid log noise |
| Request/task cancellation due to an expected signal | Stack trace may be unnecessary; record status and reason |
| An error retried multiple times | Avoid printing the full stack on every retry if it floods logs; log a summary per attempt and full details on final failure |
| Exception converted into a recoverable business error | Choose a level and details suited to the handling context |

Log level does not have to map one-to-one to exception type. For example, an `IllegalArgumentException` caused by handled user input may not warrant `SEVERE`; the exact same exception type caused by an unexpected startup configuration error can be a critical incident.

## 12. Security, privacy, and log data

Stack traces can expose:

- Package, class, and method names, file names, and source code locations.
- Exception message strings containing file paths, connection strings, SQL statements, query details, or user identifiers.
- Information added by the application into messages when wrapping exceptions.

**Never include full technical stack traces directly in HTTP responses sent to end users.** Instead, return an error code and a safe message; keep details in a protected logging system. When logging, avoid recording passwords, tokens, API keys, auth cookies, card numbers, request bodies, and sensitive personal data. Do not assume that "just a stack trace" contains no sensitive data: `Throwable.getMessage()` and cause messages may already contain input data.

To correlate multiple events, log a safe `request_id` or `trace_id` in context (for example via MDC when supported by the backend), rather than logging raw tokens or PII as IDs. Enforce access controls, retention policies, file rotation, and volume monitoring. Long stack traces can be truncated by log collection platforms, event size limits, or encoders; test end-to-end with your actual backend.

## 13. Tricky cases and how to diagnose them

### 13.1. Logger receives the exception but prints no stack trace

Check:

1. Does the call pass the full `Throwable` to a supporting overload?
2. Do both the logger level and handler level accept the record?
3. Does the formatter/encoder render the `thrown`/throwable field?
4. Is there a `Filter` or configuration dropping the record?
5. Is the console, file, or log collector truncating long content?
6. Does the exception actually have a stack trace, or was it created with stack trace generation disabled for performance reasons?

In JUL, `LogRecord.getThrown()` gives the formatter access to the error object; `SimpleFormatter` already supports printing stack traces. If replaced with a formatter that only reads `getMessage()`, the stack trace disappears from the output.

### 13.2. The same error appears twice

Check both **where the logger is called** and **the handler configuration**. Two layers might be logging the same `Throwable`, or both a child logger and the root logger might have handlers attached with parent propagation enabled. Use `setUseParentHandlers(false)` only when the child logger already has an appropriate handler; otherwise, you could accidentally drop logs.

### 13.3. The stack trace does not point to where the user saw the error

A `Throwable`'s stack trace primarily reflects the call stack when it was created or when `fillInStackTrace()` was called. If the error was **caught and transferred to another thread**, or a `CompletableFuture` wrapped it in a `CompletionException`, the stack trace may show call frames from the origin and wrappers from the observation point. Inspect the **cause chain** and async task context to connect the stages.

### 13.4. The stack trace lacks enough contextual data

A stack trace shows the call path, but does not by itself tell you which order, configuration, or request led to the failure. You need a message with safe context, correlation IDs, and possibly distributed tracing to follow a request across services. Logging a long string from `exception.toString()` cannot replace proper contextual data.

### 13.5. Original error details are lost when wrapping an exception

If a new exception is created with only a message string, check whether a constructor accepting a cause is available. When you need to preserve the original error, pass `cause` and log the exception at the responsible layer. If frames are missing from a stack trace, distinguish between application catch-and-wrap code, library behavior, and formatter/collector policies.

## 14. Checklist before taking exception logging to production

1. **Choose the boundary:** which layer is truly responsible for reporting the error and deciding the log level?
2. **Pass the Throwable:** use an overload that accepts the exception; avoid logging only `getMessage()`.
3. **Preserve the cause:** wrap exceptions using a constructor with a `Throwable cause` parameter when crossing layers.
4. **Verify the formatter:** are stack traces, causes, and suppressed exceptions fully rendered in the console, file, and backend?
5. **Check filtering levels:** do the logger, handler, encoder, and filters all accept the record?
6. **Avoid duplicates:** check logging across multiple layers and parent logger handlers.
7. **Keep context safe:** include operation names and correlation IDs; avoid secrets in messages.
8. **Control volume:** configure storage policies, rotation, oversized-log limits, and retention.
9. **Test with real errors:** trigger errors with causes or suppressed exceptions and verify the final output in your collection system.
10. **Separate log output from responses:** keep technical logs in internal systems; return minimal, safe information in external responses.

## 15. Self-check questions

**Question 1:** Why does `logger.severe(exception.getMessage())` usually not include a stack trace?  
Because the call only passes the message string; it does not attach a `Throwable` to the `LogRecord`.

**Question 2:** What is the way to log an exception with a stack trace in JUL?  
Use `logger.log(Level.SEVERE, "Action failed", exception)` or an appropriate level, and configure a formatter/handler that supports `Throwable`.

**Question 3:** Where does `printStackTrace()` write by default?  
To `System.err`; it does not go through the application's logger, levels, filters, or handlers.

**Question 4:** How do you preserve the original error's stack trace when converting `IOException` to `IllegalStateException`?  
Use a constructor that accepts a cause, for example `new IllegalStateException("Cannot load config", cause)`.

**Question 5:** In `try-with-resources`, where can an error thrown while closing a resource be found?  
In the primary exception's `exception.getSuppressed()` list; a formatter that prints the full `Throwable` can display a `Suppressed:` section.

**Question 6:** If you passed the `Throwable` properly to JUL and still see no frames, what should you check first?  
Check whether the formatter reads `LogRecord.getThrown()`, followed by levels, filters, handlers, log destinations, and collector limits.

**Question 7:** Are a stack trace and a distributed trace the same thing?  
No. A stack trace is the frame sequence of a single `Throwable`; a distributed trace consists of spans showing the path and duration of execution across operations or services.

**Takeaway:** To log stack traces properly in Java, **pass the entire `Throwable` object to the logging API**, preserve the cause when wrapping errors, and use a formatter that supports exceptions. Include enough context to diagnose root causes while avoiding duplicate logs, data leaks, and runaway log volume.