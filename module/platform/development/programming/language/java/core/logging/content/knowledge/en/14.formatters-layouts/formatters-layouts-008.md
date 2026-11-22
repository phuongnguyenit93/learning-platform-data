# Exception Formatting in Java Logging: Message, Stack Trace, Cause, and Layout

## 1. What Is Exception Formatting?

**Exception formatting** is the process of turning the information inside a `Throwable` object into readable, storable, and searchable content when an application writes logs. A good exception log entry does not just say "an error occurred"; it also tells you **which operation failed, what type of exception it is, what related cause was involved, which call path produced the error, and which request or job the event belongs to**.

For Java Core Logging, it helps to distinguish between two activities:

1. **The application creates or receives an exception**: Java provides the exception type, message, stack trace, cause chain, and list of suppressed exceptions.
2. **The logging framework represents the exception**: the logger passes the `Throwable` object to the backend; the formatter/layout decides which parts of that information are printed, whether they are rendered as multiline text or as a field in JSON, and whether to include a timestamp, level, logger name, or trace/request ID.

Example of **illustrative log content**, not a fixed transcript of a specific program:

~~~text
2026-11-09 10:15:20.123 ERROR [http-worker-2] CheckoutService
requestId=req-42 operation=checkout outcome=failed
java.lang.IllegalStateException: Cannot complete checkout
    at example.CheckoutService.checkout(CheckoutService.java:48)
Caused by: java.io.IOException: Connection reset
    at example.StoreClient.read(StoreClient.java:71)
    ... 3 more
~~~

Here there are two layers of information: a **business-context message** carrying `requestId` and a **formatted exception** containing the type, stack trace, and cause. The line numbers, timestamp, and thread name in this example are only for illustration; in practice, they depend on the program, version, and layout.

**Note:** "Exception formatting" does not mean merely calling `e.getMessage()`; nor does it mean writing the entire stack trace to every destination. The goal is to **preserve the appropriate diagnostic information in the right place and in a format that the pipeline can process**.

## 2. Components Inside a Throwable

`java.lang.Throwable` is the base class of `Exception` and `Error`. When logging an exception, there are five main groups of information:

| Component | API | Meaning |
| --- | --- | --- |
| Exception type | `e.getClass().getName()` | Distinguishes `IOException`, `IllegalStateException`, etc. |
| Message | `e.getMessage()` | Short description provided by the throwing code; may be `null` |
| Stack trace | `e.getStackTrace()` | Stack frames related to where the exception was created/recorded |
| Cause | `e.getCause()` | The exception attached as the cause of the current exception |
| Suppressed | `e.getSuppressed()` | Additional errors retained, commonly encountered when closing resources in `try-with-resources` |

An exception can carry both a cause and suppressed exceptions:

~~~text
IllegalStateException: Cannot load order
  Caused by: IOException: read failed
    Suppressed: IOException: close failed
~~~

The diagram above illustrates the relationship; the actual indentation and printing of `Suppressed`/`Caused by` in `printStackTrace()` follow their own rules and do not necessarily match the diagram verbatim.

### 2.1. getMessage() Is Only a Very Small Part

`e.getMessage()` might return `"Read timed out"` without indicating the operation, the Java class, or the execution path that reached the timeout. It can be `null`. Some libraries put file paths, data, or SQL statements inside the message, so you should not assume it is always safe to include in public logs.

`e.toString()` typically represents the exception class name plus the message (if present), but it is **not equivalent to a full stack trace**. The statement:

~~~java
// Illustration inside a catch block:
LOG.severe(e.toString());
~~~

only passes a string into `LogRecord`. The formatter will not have a `Throwable` object to display frames, causes, and suppressed exceptions unless another source provides it.

### 2.2. A Stack Trace Is Not a Message

A stack frame typically includes a class name, method name, file name, and line number, for example:

~~~text
at example.StoreClient.read(StoreClient.java:71)
at example.OrderService.load(OrderService.java:33)
~~~

This is a trace of the call path; whether line numbers exist and how accurate they are depend on debug information in the bytecode, the environment, and how the exception was constructed. Using a stack trace helps identify **where** it happened, but does not always prove the **business root cause** on its own. It should be read alongside operational data, safely filtered inputs, and the cause chain.

### 2.3. Cause Chain

When translating errors across layers, preserve the `cause`:

~~~java
// Illustration inside a method catching IOException.
catch (java.io.IOException e) {
    throw new IllegalStateException("Cannot load order", e);
}
~~~

The `IllegalStateException(String, Throwable)` constructor retains the original error object. A compatible formatter can print the `Caused by: java.io.IOException...` section after the outermost exception.

Conversely:

~~~java
// Wrong if you want to preserve the cause.
catch (java.io.IOException e) {
    throw new IllegalStateException(e.getMessage());
}
~~~

loses the link to `IOException` because the new exception has no `cause`. A formatter cannot recover a `Throwable` that the application code has discarded.

### 2.4. Suppressed Exceptions

With `try-with-resources`, if the body of the block throws error A and `close()` throws error B, Java typically keeps A as the primary error and attaches B to `A.getSuppressed()`. If only `close()` fails, then B may be the exception thrown directly.

Suppressed information is distinct from `cause`. An exception can have multiple suppressed exceptions, and each suppressed exception can have its own stack trace or cause. A formatter that only prints `e.getMessage()` ignores this entire relationship; standard `Throwable.printStackTrace()` has a built-in mechanism to render them.

## 3. Three Ways to Present Exceptions and Their Level of Detail

| Presentation | Example | Information retained in the log record |
| --- | --- | --- |
| Message only | `"Read timed out"` | Very little; may lose both type and location |
| Type + message | `"IOException: Read timed out"` | Includes the type, but no stack/cause/suppressed |
| Full Throwable | `Throwable` retained by the logger and stack trace rendered by the formatter | Can preserve type, frames, cause, and suppressed, depending on the formatter and configuration |

The best way to log is not always "print everything on every line." A timeout that was retried and handled completely may only need a brief DEBUG/WARN log or a metric. By contrast, a failure at an HTTP/job boundary that requires investigation should usually have **one record containing the full Throwable** along with appropriate context fields.

**Rule of thumb:** when you need a stack trace, **pass the exception object to the logging API**; do not build a string with `e.getMessage()` and expect the layout to infer the call path and cause.

## 4. JUL: Formatter, LogRecord, and getThrown()

In `java.util.logging` (JUL), loggers create `LogRecord` instances. A `LogRecord` can carry:

- `record.getMessage()`: the message/template.
- `record.getParameters()`: the parameters, if passed using an appropriate overload.
- `record.getThrown()`: the `Throwable`, if the logger call passed an exception.
- `record.getLevel()`, `record.getLoggerName()`, timestamp, thread information, and other fields.

`java.util.logging.Formatter` defines `format(LogRecord)` and provides `formatMessage(LogRecord)` to process the message (including `MessageFormat`-style `{0}` parameters where applicable).

### 4.1. Passing the Throwable via the Right Overload

Recommended when this is the point responsible for logging the error:

~~~java
// Illustration: LOG is java.util.logging.Logger, e is IOException.
LOG.log(java.util.logging.Level.SEVERE,
        "operation=readOrder outcome=failed",
        e);
~~~

The `Logger.log(Level, String, Throwable)` overload places `e` into `LogRecord.getThrown()`. If the backend uses `SimpleFormatter`, the `Throwable` is typically printed as a stack trace including cause/suppressed exceptions.

Prone to missing information:

~~~java
// Does not attach the Throwable to the LogRecord.
LOG.severe("readOrder failed: " + e.getMessage());
~~~

The second statement can still be useful when you only want a brief marker and the error has already been logged in full elsewhere; however, it is not a replacement for a diagnostic exception record.

### 4.2. Parameterized Message and Exception in the Same Record

JUL uses `{0}`, `{1}` placeholders instead of SLF4J's `{}`. When you need to **both** parameterize a message and attach a `Throwable`, you can construct a `LogRecord`:

~~~java
// Illustrative snippet inside a catch block; orderId, e, and LOG already exist.
java.util.logging.LogRecord record =
        new java.util.logging.LogRecord(
                java.util.logging.Level.SEVERE,
                "operation=loadOrder orderId={0} failed");

record.setParameters(new Object[] {orderId});
record.setThrown(e);
LOG.log(record);
~~~

A formatter that calls `formatMessage(record)` can replace `{0}` with `orderId`; a formatter that prints `record.getThrown()` also preserves the stack trace. This is an illustrative snippet assuming those variables are in scope, not a standalone Java application.

Do not confuse the `log(Level, String, Object[])` overload with `log(Level, String, Throwable)`: they pass **different kinds of data** into the record. If you only call `LOG.log(Level.SEVERE, "failed {0}", new Object[]{e})`, the object `e` is treated as a message parameter and does not automatically become `getThrown()`.

### 4.3. SimpleFormatter and the Format String

`java.util.logging.SimpleFormatter` is a common JUL formatter. It allows configuring a format string using `String.format` conventions; in this string, notable placeholders include **`%4$s` (level), `%5$s` (formatted message), and `%6$s` (Throwable/stack trace when present)**.

Conceptual format example:

~~~text
%4$s %5$s%6$s%n
~~~

This is a **pattern for SimpleFormatter's format property**, not a message template for `Logger.log(...)`. The placeholder set in formatter configuration differs from `{0}` in JUL messages and `{}` in SLF4J. `%6$s` can be empty when the record has no `Throwable` and usually includes a newline/stack trace when one is present.

Be careful when editing the format string: if you print only `%5$s` and omit `%6$s`, the record may still hold the `Throwable` object, but **the text output will not display the stack trace**. Do not conclude that "the cause was lost in the program" just because a console pattern does not print throwables.

## 5. Standalone Java 17 Example: A Formatter That Sees Cause and Suppressed

The example below uses **JDK 17, with no Maven and no external libraries outside the JDK**. It simulates a processing error and a resource-closing error, wraps the exception to preserve the cause, and passes the `Throwable` into a JUL `LogRecord`.

To make stdout **completely predictable**, the formatter in this example prints only a fixed summary of the exception. The next section explains how to replace this formatter with full stack trace output in a real application.

Create **ExceptionFormatterDemo.java**:

~~~java
import java.io.IOException;
import java.util.logging.Formatter;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;
import java.util.logging.StreamHandler;

public final class ExceptionFormatterDemo {
    private static final Logger LOG =
            Logger.getLogger(ExceptionFormatterDemo.class.getName());

    private static final class FailingResource implements AutoCloseable {
        @Override
        public void close() throws IOException {
            throw new IOException("close failed");
        }
    }

    private static void runOperation() throws IOException {
        try (FailingResource ignored = new FailingResource()) {
            throw new IOException("operation failed");
        }
    }

    private static final class SummaryFormatter extends Formatter {
        @Override
        public String format(LogRecord record) {
            StringBuilder out = new StringBuilder();
            out.append(record.getLevel().getName())
               .append(" ")
               .append(formatMessage(record))
               .append("\n");

            Throwable error = record.getThrown();
            if (error != null) {
                out.append("type=")
                   .append(error.getClass().getSimpleName())
                   .append("\n");
                out.append("message=")
                   .append(error.getMessage())
                   .append("\n");

                Throwable cause = error.getCause();
                if (cause != null) {
                    out.append("causeType=")
                       .append(cause.getClass().getSimpleName())
                       .append("\n");
                    out.append("causeMessage=")
                       .append(cause.getMessage())
                       .append("\n");
                    out.append("causeSuppressed=")
                       .append(cause.getSuppressed().length)
                       .append("\n");

                    for (Throwable suppressed : cause.getSuppressed()) {
                        out.append("suppressedMessage=")
                           .append(suppressed.getMessage())
                           .append("\n");
                    }
                }
            }
            return out.toString();
        }
    }

    private static void configureLogging() {
        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.ALL);

        Handler console = new StreamHandler(System.out,
                                            new SummaryFormatter()) {
            @Override
            public synchronized void publish(LogRecord record) {
                super.publish(record);
                flush();
            }
        };
        console.setLevel(Level.ALL);
        LOG.addHandler(console);
    }

    public static void main(String[] args) {
        configureLogging();

        try {
            runOperation();
        } catch (IOException original) {
            IllegalStateException wrapped =
                    new IllegalStateException("checkout failed", original);

            LOG.log(Level.SEVERE,
                    "operation=checkout requestId=req-17 outcome=failed",
                    wrapped);
        }
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 ExceptionFormatterDemo.java
java ExceptionFormatterDemo
~~~

**Program stdout produced by the defined formatter:**

~~~text
SEVERE operation=checkout requestId=req-17 outcome=failed
type=IllegalStateException
message=checkout failed
causeType=IOException
causeMessage=operation failed
causeSuppressed=1
suppressedMessage=close failed
~~~

Why does this output occur?

1. `runOperation()` throws `IOException("operation failed")` inside the `try-with-resources` block.
2. `FailingResource.close()` also throws `IOException("close failed")`. Java keeps the processing error as the **primary** exception and attaches the close error as a **suppressed** exception on the primary one.
3. `IllegalStateException("checkout failed", original)` retains the primary exception as its cause. `LOG.log(..., wrapped)` attaches the outermost exception to `LogRecord.getThrown()`.
4. The formatter prints the type name, message, cause, and `cause.getSuppressed()`. The suppressed count is `1`, and the suppressed message is `close failed`.
5. The handler uses `StreamHandler(System.out, ...)` and calls `flush()` after each publish; the logger disables parent handlers, so no extra default JUL lines appear on stderr.

**Important scope boundary of this demo:** `SummaryFormatter` intentionally **does not print stack frames**, and only inspects suppressed exceptions on the direct cause. It is a learning tool for reading the `Throwable` structure, **not a recommendation to replace full stack traces with such a summary in production logs**. If an exception has multiple levels of causes or suppressed exceptions, a complete formatter must traverse/format all necessary levels.

### 5.1. Printing the Full Stack Trace in a Custom Formatter

If you are writing a specialized JUL formatter, you can obtain the full standard representation of a `Throwable` using `printStackTrace(PrintWriter)`:

~~~java
// Illustrative snippet placed inside Formatter.format(LogRecord record).
Throwable error = record.getThrown();
if (error != null) {
    java.io.StringWriter buffer = new java.io.StringWriter();
    java.io.PrintWriter writer = new java.io.PrintWriter(buffer);
    error.printStackTrace(writer);
    writer.flush();
    // Use buffer.toString() to append to the formatter output.
}
~~~

`Throwable.printStackTrace` prints the outermost exception, frames, causes, and suppressed exceptions according to standard Java rules, including abbreviated common frames like `... N more`. **Line numbers and frame order depend on the code and compiler**, so no single "exact" transcript is shown for the full-stack printing example.

The snippet above is a **method-level snippet**, not a standalone runnable program. If you only call `getStackTrace()` and concatenate `StackTraceElement` items yourself, you have to handle traversing causes/suppressed exceptions and avoiding loops or missing branches; using `printStackTrace` or a battle-tested formatter is usually safer.

### 5.2. Why Not Call e.printStackTrace() Directly in catch?

~~~java
// Approach to avoid as the primary logging pipeline in server applications:
catch (IOException e) {
    e.printStackTrace();
}
~~~

`printStackTrace()` with no arguments prints to **System.err** by default, bypassing logger levels, appenders, correlation IDs, retention settings, or the application's encoder. It can be handy in tiny experiments, but in operational applications you should pass the `Throwable` through the logger so the formatter/layout handles it consistently:

~~~java
// Illustration using JUL.
catch (IOException e) {
    LOG.log(Level.SEVERE, "operation=load outcome=failed", e);
}
~~~

Note: the example above is also a code snippet inside a method that has `LOG`, not a standalone Java file.

## 6. SLF4J + Logback: Exceptions via ThrowableProxy and PatternLayout

In systems using the **SLF4J API with Logback Classic**, application code typically uses `org.slf4j.Logger`:

~~~java
// Illustration in a class that already has SLF4J Logger LOG and requestId.
try {
    loadOrder();
} catch (java.io.IOException e) {
    LOG.error("operation=loadOrder requestId={} outcome=failed",
              requestId, e);
    throw e;
}
~~~

SLF4J normally recognizes a **`Throwable` in the last argument position** of a parameterized message call as the event's exception. The Logback backend can build a `ThrowableProxy` to represent the stack trace/cause/suppressed exceptions and render it via a layout converter. If you only pass `e.getMessage()` as an ordinary argument, the `Throwable` is not attached.

The code snippet above requires `loadOrder`, `requestId`, `LOG`, and a method signature with `throws IOException`. It will not compile standalone without the corresponding declarations.

### 6.1. PatternLayout: Using %ex or %throwable

Example `logback.xml` configuration for logging exceptions to the console:

~~~xml
<configuration>
    <appender name="CONSOLE"
              class="ch.qos.logback.core.ConsoleAppender">
        <target>System.out</target>
        <encoder>
            <pattern>%d{yyyy-MM-dd HH:mm:ss.SSS} %-5level [%thread] %logger{36} requestId=%X{requestId} - %msg%n%ex{full}</pattern>
            <charset>UTF-8</charset>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
    </root>
</configuration>
~~~

Key conversion words:

| Token | Role |
| --- | --- |
| `%d{...}` | Timestamp according to the chosen pattern |
| `%-5level` | Log level, padded/aligned |
| `%thread` | Thread that generated the event |
| `%logger{36}` | Abbreviated logger name |
| `%X{requestId}` | Value of `requestId` in MDC, if present |
| `%msg` | Message content after placeholder substitution |
| `%n` | Line separator |
| `%ex{full}` | Full Throwable stack trace via Logback's converter |

The `%ex`/`%throwable` token (the corresponding converter name) is a key part of **exception formatting**. It allows Logback to render the exception as a stack trace rather than printing only a single message line.

**Caution:** some versions/configurations of Logback Classic **automatically append throwable information** to `PatternLayout` when you do not declare a throwable converter. Do not assume "omitting `%ex` always makes the stack trace disappear"; check the actual output and backend policy. Conversely, if a configuration explicitly uses `%nopex` or a custom encoder drops the throwable, the stack trace may not appear even when `Logger.error(..., e)` passes it properly.

With `%ex{short}`, the stack trace output is shortened (depending on the converter and version); use `%ex{full}` when investigations need all causes and suppressed exceptions. Do not place `%ex` twice in the pattern, as it can print the same exception twice.

### 6.2. A Layout Cannot Fix a Discarded Cause

If application code does:

~~~java
// Does not retain the cause in the new exception.
throw new IllegalStateException("Cannot read data");
~~~

then even if the pattern has `%ex{full}`, the layout only prints the stack trace of that `IllegalStateException`; it **cannot recover the original IOException** if the code did not pass it into the constructor. When wrapping:

~~~java
throw new IllegalStateException("Cannot read data", e);
~~~

the cause chain is preserved for the converter to display.

### 6.3. Avoid Duplicate Logging at Every Layer

If the repository throws `IOException`, the service wraps it in `OrderLoadException` with the cause, and the API boundary logs ERROR and returns a response, you typically only need **one full throwable log record at the boundary**. Logging the same error at all three layers and rethrowing can cause dashboards to count a single failure multiple times and make logs noisy.

This is different from intentionally logging WARN on a successful retry or another distinct, meaningful event. Choose log levels according to the impact and responsibility of that layer.

## 7. Apache Log4j 2: %throwable, %ex, and PatternLayout

In **Log4j 2**, application code can use the Log4j API directly:

~~~java
// Illustration in a project that already has log4j-api and log4j-core.
import org.apache.logging.log4j.LogManager;
import org.apache.logging.log4j.Logger;

private static final Logger LOG =
        LogManager.getLogger(MyService.class);
~~~

and pass the `Throwable` when logging:

~~~java
// Illustrative snippet inside catch, with valid requestId and LOG.
LOG.error("operation=process requestId={} outcome=failed",
          requestId, e);
~~~

The message uses `{}` placeholders according to Log4j 2's parameterized message syntax; the `Throwable` is attached to the event via the compatible overload/invocation. The backend/appender/layout determines how the error is printed.

### 7.1. Configuring log4j2.xml with Stack Traces

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<Configuration status="WARN">
    <Appenders>
        <Console name="CONSOLE" target="SYSTEM_OUT">
            <PatternLayout pattern="%d{yyyy-MM-dd HH:mm:ss.SSS} %-5p [%t] %c{1.} requestId=%X{requestId} - %m%n%throwable{full}"/>
        </Console>
    </Appenders>

    <Loggers>
        <Root level="INFO">
            <AppenderRef ref="CONSOLE"/>
        </Root>
    </Loggers>
</Configuration>
~~~

Place the configuration file at `src/main/resources/log4j2.xml` if the project is packaged with Maven/Gradle using the standard directory structure.

Relevant tokens:

- `%m` or `%msg`: the event message.
- `%n`: newline.
- `%throwable{full}` or `%ex{full}`: renders the Throwable's stack trace/cause/suppressed exceptions via Log4j 2's converter.
- `%X{requestId}`: value from the `ThreadContext` map, if set and propagated properly across the execution context.
- `%d`, `%p`, `%t`, `%c`: timestamp, level, thread, and logger name.

Log4j 2's `PatternLayout` has options related to **automatically appending exceptions when the pattern does not include a Throwable converter** (such as `alwaysWriteExceptions` in supported versions). Therefore, you should not claim that omitting `%throwable` guarantees no stack trace will be printed. For explicit requirements, declare the appropriate converter and test the output.

### 7.2. Full, Short, and Extended Exception Information

Log4j 2 converters provide options to shorten or expand stack trace information, with exact syntax and features depending on the version. For example, `%throwable{short}` is an option to shorten exception output in `PatternLayout`.

**Choosing full or short based on purpose**:

- For boundary error logs where a single record supports investigation, a full trace is usually valuable.
- With multiple retries, if the final point already logs the full trace, intermediate attempts can log just the error code, attempt number, and context; printing a full trace on every attempt is not always necessary.
- Logs intended for field-based/JSON analysis should consider encoding the throwable as a properly escaped multiline string or structured fields, rather than sending separate stack trace lines into a collector.

Do not confuse **extended stack traces** with automatically getting extra business data. Metadata about class/JAR locations may be included, but request IDs, safe inputs, and business state still have to be provided by the application.

## 8. Multiline Text Formatting and Structured Logging

### 8.1. One Event Can Span Multiple Physical Lines

Typically, a full exception stack trace produces a message containing newlines:

~~~text
ERROR operation=checkout requestId=r-7 failed
java.lang.IllegalStateException: checkout failed
    at example.CheckoutService.checkout(CheckoutService.java:42)
Caused by: java.io.IOException: store unavailable
    at example.StoreClient.read(StoreClient.java:23)
~~~

This is an **illustrative** example, not a claim about the exact stack frames of the earlier programs. If a collector splits events solely on every newline, it may treat each `at ...` line as a new log event or lose the ERROR level and request ID context.

Two operational approaches:

1. **Multiline-aware ingestion:** configure the log shipper/collector to merge related lines into a single event before indexing, based on the output structure.
2. **Structured logging:** use an encoder/layout designed for JSON or structured event formats, so that the stack trace is a string value properly escaped according to JSON rules (for example, newlines represented as `\n` inside the string value).

Do not assume "JSON = no newlines": valid JSON can contain string values with escaped newlines, whereas an NDJSON-style file requires **each event to be a single JSON object on one physical line**. Confirm that the encoder and collector agree on the same protocol.

### 8.2. Example JSON Event Model

~~~json
{
  "timestamp": "2026-11-09T10:15:20Z",
  "level": "ERROR",
  "logger": "example.CheckoutService",
  "requestId": "req-17",
  "message": "operation=checkout outcome=failed",
  "error": {
    "type": "java.lang.IllegalStateException",
    "message": "checkout failed",
    "stack_trace": "java.lang.IllegalStateException: checkout failed\n\tat example.CheckoutService.checkout(CheckoutService.java:42)\nCaused by: java.io.IOException: operation failed"
  }
}
~~~

This is an **illustrative schema designed by an application or encoder**, not a default output automatically produced by JUL, Logback, or Log4j 2. Field names like `error.type` and `error.stack_trace`, how causes are stored, and timestamp formats depend on the encoder, version, and pipeline configuration.

Some stack-trace schemas split an exception into `type`, `message`, `frames[]`, `cause`, or `suppressed[]` instead of a single string. That aids querying but increases complexity and volume; there is no single mandatory schema across all frameworks.

**Library dependencies:** getting JSON logs in Logback may require an encoder outside the default library; in Log4j 2, advanced structured layouts such as JSON Template Layout have separate modules/dependencies. Do not copy a JSON configuration from another backend and expect it to work without the right module.

### 8.3. Choosing Fields for Searchability

Recommended fields where appropriate:

| Field | Meaning |
| --- | --- |
| `timestamp` | Event time, with an explicit timezone |
| `level` | Log level |
| `logger` | Class/component emitting the event |
| `thread` | Thread emitting the event, when useful |
| `service` / `environment` | Service and processing environment |
| `requestId` / `traceId` / `spanId` | Correlation IDs linking events, if implemented |
| `operation` | Operation being processed |
| `error.type` | Exception type |
| `error.message` | Message vetted against safety policy |
| `error.stack_trace` | Stack trace when needed for investigation |

Correlation IDs and error types can be more useful for searching than running regexes over multiline stack traces. However, do not overuse high-cardinality fields as metric labels or unnecessary index keys; design an appropriate observability policy.

## 9. MDC/ThreadContext and Exceptions: Attaching Context Properly

A stack trace shows the call path, but when thousands of requests run concurrently, responders still need to tie an exception to a specific request.

In projects using **SLF4J + Logback**, you can set `MDC`:

~~~java
// Illustrative code in a request handler that has requestId and LOG.
org.slf4j.MDC.put("requestId", requestId);
try {
    processRequest();
} finally {
    org.slf4j.MDC.remove("requestId");
}
~~~

In Logback's `PatternLayout`, `%X{requestId}` prints that ID. When using the Log4j 2 API directly, `ThreadContext.put(...)` / `CloseableThreadContext` is a common way to attach context; `%X{requestId}` can output the corresponding field.

**Keep in mind:** MDC and ThreadContext are usually bound to a thread or a framework-managed context, and are not automatically propagated across every `CompletableFuture` or worker thread. When handling asynchronous work, propagate context via the proper mechanism, clean up upon completion, and verify that IDs do not "leak" into subsequent requests on a thread pool.

MDC/ThreadContext values are not a substitute for preserving `Throwable`. A log entry with a `requestId` but without a cause or stack trace may still be insufficient to diagnose tricky failures.

## 10. Choosing Where to Log Exceptions and Avoiding Duplicates

A common architecture:

~~~text
Storage layer -> throws IOException
Service layer -> wraps ServiceException("load failed", IOException)
HTTP boundary -> logs ServiceException with Throwable + requestId
             -> returns safe error response
~~~

The service layer can add context using a constructor that accepts a cause:

~~~java
throw new IllegalStateException("Cannot load orderId=" + safeOrderId, e);
~~~

That way, a single complete record at the HTTP boundary can reveal both the failed operation and the original `IOException`. If every layer logs ERROR and rethrows, the same failure can turn into multiple duplicate records. Beyond wasting storage, it makes it hard to distinguish **one error happening three times** from **one error logged at three layers**.

When an exception has already been handled by a fallback or successful retry, you can log DEBUG/WARN or record a metric depending on impact. Not every exception needs an ERROR with a full stack trace, especially expected exceptions in control flow.

### 10.1. Do Not Hide the Cause When Wrapping

Common ways traces get lost:

~~~java
// Creating a new exception while forgetting the cause:
throw new IllegalStateException("Cannot load data");

// Taking only the message, leaving no original stack trace in the record:
LOG.error("Cannot load data: {}", e.getMessage());

// Catching and leaving it empty, leaving no sign of failure:
catch (IOException ignored) {
}
~~~

These are **illustrative snippets of design mistakes** in different contexts, not a standalone runnable Java block. The fix is to preserve the `Throwable` across layers and log in full only at the point responsible for reporting the error.

### 10.2. Protecting Information in External Responses

An API might return:

~~~json
{
  "errorCode": "ORDER_READ_FAILED",
  "message": "The request could not be completed",
  "requestId": "req-17"
}
~~~

This is an illustrative response, not a mandatory Java requirement. End users do not need to see internal stack traces, SQL queries, endpoints, filesystem paths, or tokens. Internal logging systems can retain the `Throwable` with restricted access and retention, while also scrubbing secrets if exception messages contain them.

**Keeping the cause internally and hiding stack traces from HTTP responses are two completely compatible decisions.**

## 11. Safety When Formatting and Storing Exceptions

Exception messages may contain user-controlled data or driver/framework details. For example, filenames, connection URLs, query parameters, malformed JSON payloads, or internal paths can appear in messages; stack traces can reveal classes, modules, and versions.

Core principles:

1. **Do not log secrets in the first place.** Do not put passwords, API keys, access tokens, session cookies, OTP codes, or sensitive payloads into exception messages or log context. Do not rely solely on a post-hoc regex step after full text has already been constructed.
2. **Choose appropriate levels and destinations.** Full exception traces can be long; for critical errors, store them in a diagnostic system with access control. Do not print full traces into user-facing responses.
3. **Prevent log forging.** Untrusted data may contain newlines or control characters that fabricate fake log lines. Encoders should escape/normalize according to the target format; a compliant JSON encoder can escape newlines inside strings.
4. **Bound length and volume.** A deep cause chain or large message can bloat logs, causing I/O/GC pressure and higher ingestion costs. Apply intentional limits; if a stack trace is truncated, make it clear that the information was abbreviated.
5. **Protect files and collectors.** Set access permissions, retention, encryption where needed, and account for copies/backups.
6. **Do not put sensitive data into MDC.** MDC can travel with events to more appenders and destinations than you expect.
7. **Assess output when a formatter/encoder fails.** An exception should not cause the logging pipeline to throw errors endlessly; use a proven backend/layout and monitor appender health.

The goal of a formatter is to preserve **the information needed for investigation** without creating unnecessary **leakage or overload risks**.

## 12. Cost and Performance of Stack Traces

Printing a full exception is not as cheap as logging a simple numeric value:

- Creating an exception typically captures the stack trace at `Throwable` construction time (cost depends on type and configuration); some `Throwable` types can disable or limit stack trace capture.
- Formatters/layouts must traverse frames, causes, and suppressed exceptions and may allocate many intermediate strings.
- Encoding and writing multi-byte text/JSON increases I/O, file size, and collector/indexing costs.
- If exceptions are created and logged thousands of times per second on a hot path, CPU usage, allocations, and p95/p99 latency can rise noticeably.
- With async logging, encoding/writing costs may move to a worker thread, but the queue still consumes memory and risks blocking or dropping events when full; it does not guarantee zero event loss.

**Do not prematurely optimize by deleting all stack traces.** Categorize errors, choose appropriate logging points, limit duplicate logs, and measure performance. If an error repeats heavily, consider aggregating counts with metrics/rate limits where appropriate, while keeping sufficient traces for important errors.

Metrics worth watching: log events/s, bytes/s, CPU, allocations/GC, queue depth, dropped events, p95/p99 latency, and storage volume. Compare workloads before and after changing a layout, rather than measuring only a single `LOG.error(...)` call.

## 13. How to Verify Exception Formatting in Practice

To test a project after changing `logback.xml`, `log4j2.xml`, or a JUL handler, create a test exception with:

- An easily recognizable outermost message, such as `"checkout failed"`.
- A distinct root cause type, such as `IOException("operation failed")`.
- A suppressed exception, such as a `close()` error in `try-with-resources`.
- A safe request ID, such as `req-17`.
- Both normal events (without a `Throwable`) and error events (with a `Throwable`).

Then verify in sequence:

1. **Correct backend:** which of JUL/Logback/Log4j 2 actually receives the event? Does the logger have the right provider/implementation?
2. **Event accepted:** do the logger level, filters, and appender-ref/handler levels allow ERROR?
3. **Throwable present on the event:** for JUL, check `LogRecord.getThrown()`; for SLF4J/Log4j 2, use the overload taking `Throwable`, not just `getMessage()`.
4. **Formatter/layout prints the stack trace:** does the JUL formatter use `Throwable`/`%6$s`? Does Logback have `%ex` or the corresponding display mechanism? Does Log4j 2 have `%throwable` and a suitable encoder?
5. **Cause/suppressed visible:** look for `Caused by:` and `Suppressed:` sections in the full trace; if missing, check both the exception data and any abbreviated-format policy.
6. **Context accurate:** is `requestId`/`traceId` attached to the right request and cleared after the thread finishes processing?
7. **Collector merges multilines:** is a single exception split into multiple events? Does JSON output escape newlines properly?
8. **Security:** do logs contain secrets, URLs with credentials, unnecessary internal paths, or untrusted input payloads?
9. **Performance:** test both normal load and repeated errors; measure throughput, bytes/s, CPU, GC, and queue behavior.
10. **No duplicate logging:** is the same exception logged across multiple layers/appenders?

When testing output, you do not have to assert the entire stack trace text with fixed line numbers: line numbers shift with refactoring and compilers. It is better to assert stable properties such as **exception type, message, cause type, suppressed count, requestId**, and whether the encoder includes the `Throwable` field, then use integration tests to confirm the actual format.

## 14. Common Mistakes and How to Fix Them

| Mistake | Result | How to fix |
| --- | --- | --- |
| `LOG.error("failed: {}", e.getMessage())` | Log contains only text, no `Throwable` | Pass `e` to the appropriate logging overload |
| `System.err.println(e)` | Only `toString()`, bypasses the logging pipeline | Log through the logger with the `Throwable` |
| `e.printStackTrace()` directly in a server | Prints stack trace, but lacks unified logger level, appender/context/retention | Use a logger and formatter/layout |
| Wrapping in an exception without a cause | Loses the link to the original error | Use the `(message, cause)` constructor |
| Rendering only `getStackTrace()` | May omit causes and suppressed exceptions | Use `printStackTrace` or a standard converter |
| JUL pattern with only `%5$s` | May not show the `Throwable` | Check `%6$s` or a formatter that reads `getThrown()` |
| Logback accidentally using `%nopex` | May suppress stack trace printing | Choose the appropriate throwable converter |
| Log4j 2 printing only `%m` with auto-exceptions disabled | Stack trace does not appear | Add `%throwable{full}` or enable the appropriate policy |
| Two Throwable converters in one pattern | May print the exception twice | Include only one converter for your goal |
| Multiline stack trace split by collector | Frames lose level/`requestId` and become hard to search | Multiline parsing or structured logging |
| Assuming JSON automatically includes exception fields | Encoder may store only the message | Choose an encoder/layout with Throwable support and test it |
| Logging the same ERROR failure at every layer | Duplicate data, inflated alerts | Log in full at the responsible boundary |
| Printing full stack traces in API responses | Exposes classes/files/paths/internal details | Return a safe code/message; log internally with access control |
| Logging only "failed" without `requestId` | Hard to correlate with other events in the system | Add a safe correlation ID |
| Ignoring suppressed exceptions | Resource-closing errors go unseen | Use a formatter that displays suppressed exceptions and inspect causes |

## 15. Self-Check Exercises

1. **Concepts:** Compare `e.getMessage()`, `e.toString()`, `e.getStackTrace()`, and `e.printStackTrace(PrintWriter)`. Which one can include cause/suppressed exceptions in standard Java format?
2. **JDK 17:** Create `ExceptionFormatterDemo.java`, run it with `javac`/`java`, and explain why `causeSuppressed=1` and `suppressedMessage=close failed` appear. If `close()` no longer throws an exception, what output changes?
3. **JUL:** Design a `LogRecord` using the template `"orderId={0}"`, add parameters, and call `setThrown(e)`. Explain why passing an exception merely as an argument to `log(Level, String, Object[])` does not have the same effect.
4. **Logback:** Update a pattern to print timestamp, level, `requestId`, message, and `%ex{full}`. For an error with a cause, which part should you inspect to verify the cause was preserved?
5. **Log4j 2:** Compare `%m%n` with `%m%n%throwable{full}`. Why must you check both `alwaysWriteExceptions` and the actual backend before concluding that a pattern does not print exceptions?
6. **Structured:** Design JSON fields for an exception, ensuring `stack_trace` is a valid string when it contains newlines. Explain how a collector can distinguish a JSON event from multiple lines of plain text.
7. **Cost:** A service sees 1,000 errors/second, with each full trace around 5 KB. Calculate the raw daily data volume and propose ways to reduce repetitive logs while retaining enough diagnostic information.
8. **Safety:** An exception message accidentally contains a token in a URL. Why is changing the layout alone not always enough? Design a safe internal logging approach and a user response that does not leak data.
9. **Async:** If a request ID is placed in MDC but exception handling happens on another thread, why might that field be empty? Describe how to verify context propagation.
10. **Boundaries:** Repository, service, and controller all receive the same exception. Choose where to log the full trace and how to preserve the cause across layers without producing three duplicate ERROR logs.

## 16. Summary

**Exception formatting** is the bridge between Java's `Throwable` structure and the log records that humans or processing systems need to read. To make logs useful, **pass the real Throwable**, preserve **causes and suppressed exceptions**, choose a **formatter/layout that displays sufficient detail**, and attach safe context such as a request ID. In JUL, pay attention to `LogRecord.getThrown()` and `Formatter`; in Logback, pay attention to `PatternLayout` and the `%ex` converter; in Log4j 2, pay attention to `%throwable` and how the encoder emits events. Finally, verify multiline/JSON handling, performance, retention, and security so that exception logs genuinely help pinpoint root causes rather than adding noise.