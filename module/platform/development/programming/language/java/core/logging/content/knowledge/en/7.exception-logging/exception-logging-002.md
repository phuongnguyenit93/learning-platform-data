# Passing Exceptions Properly in Java Logging

When Java encounters an error, a message like `"Save failed"` is rarely enough for investigation. Operators need to know which operation failed, which entity was affected, and **where the original exception came from**. Therefore, a key principle of *exception logging* is **passing the `Throwable` object to the logging API properly**, rather than merely copying `getMessage()` or `toString()` into the log message.

This lesson distinguishes between *logging an exception*, *throwing/propagating an exception*, and *wrapping an exception while preserving its cause*; it also explains how to call Java Util Logging (JUL), SLF4J, and common API pitfalls. Standalone runnable examples use Java 17 and the built-in JDK JUL; SLF4J examples are marked as illustrative snippets that require a dependency.

## 1. What Information Does an Exception Carry?

In Java, `Exception` is a subclass of `Throwable`. A `Throwable` can contain:

| Component | How to retrieve | Meaning |
| --- | --- | --- |
| **Exception type** | `error.getClass()` | Error classification, e.g. `IOException`, `IllegalStateException`, `SQLException`. |
| **Message** | `error.getMessage()` | Description created by application code or a library; may be `null`, and is not the complete diagnostic picture. |
| **Stack trace** | `error.getStackTrace()`, `error.printStackTrace(...)` | Sequence of frames showing where the exception was created/thrown and the recorded execution path. |
| **Cause** | `error.getCause()` | Underlying exception that triggered the current error, e.g. an I/O failure causing an order save failure. |
| **Suppressed exceptions** | `error.getSuppressed()` | Secondary errors recorded in certain situations, typically when closing resources in `try-with-resources`. |
| **Business context** | Application-generated message/fields, outside `Throwable` if needed | Examples include `orderId`, `jobId`, `requestId`, `operation`, `errorCode`. |

**Cause** and **suppressed** are not synonymous: a cause represents the declared causal chain; suppressed exceptions record secondary errors accompanying a primary error. Standard formatters can usually print both the cause chain and suppressed exceptions when given the `Throwable` object.

### Passing an exception vs. logging only the message

Suppose an `IOException` has the message `"Disk unavailable"`:

```java
// Illustrative example in a catch block; assuming LOG is java.util.logging.Logger.
catch (java.io.IOException ex) {
    LOG.severe("Could not save file: " + ex.getMessage());
}
```

The call above logs **a single string** and does not pass the `Throwable` to JUL. The log record may lose the stack trace and cause relationship, making it hard to pinpoint which file or method threw the error. Switch to the overload that accepts a `Throwable` parameter:

```java
// Illustrative example in a catch block; LOG is java.util.logging.Logger.
catch (java.io.IOException ex) {
    LOG.log(
        java.util.logging.Level.SEVERE,
        "event=file.save_failed pathId=report-42",
        ex
    );
}
```

`Logger.log(Level, String, Throwable)` stores `ex` in the `LogRecord.thrown` field. A suitable handler/formatter can print the stack trace and cause, while the separate message string describes the business context. Passing the right object does not guarantee that every formatter or log collector will output the full stack trace: output configuration must still be verified.

## 2. Three Distinct Operations to Understand Accurately

| Operation | Example | Result |
| --- | --- | --- |
| **Log exception** | `logger.log(Level.SEVERE, "Saving failed", ex)` | Creates a log record carrying the message and `Throwable`. Does not throw the exception or recover from the error. |
| **Rethrow** | `throw ex;` | Propagates the same exception object up to the caller; does not create a log record on its own. |
| **Wrap with cause** | `throw new IllegalStateException("Cannot save order", ex);` | Creates an application-level exception with new context while preserving the original exception in `getCause()`. |
| **Handle/recover** | Switch to a fallback source or return a valid rejection result | May not require a high-severity error log if the final outcome satisfies the contract. |

Do not call `logger.error(...)` (or `logger.log(...)` in JUL) and assume the exception has been thrown to the caller. Logging only records information. Likewise, `throw ex` does not automatically emit a log event.

### Wrapping an exception: preserve the cause

A service that wants to translate low-level I/O error details into a business-appropriate exception can write:

```java
// Illustrative snippet; saveToDisk() may throw IOException.
try {
    saveToDisk();
} catch (java.io.IOException ex) {
    throw new IllegalStateException("Cannot persist order", ex);
}
```

Here, `IllegalStateException` keeps the `IOException` in `getCause()`. If an outer layer logs the `IllegalStateException` as a `Throwable`, the cause's stack trace can be displayed alongside the outer exception.

**Common mistake:**

```java
// Avoid: loses the original cause and stack trace.
throw new IllegalStateException(ex.getMessage());
```

Creating a new exception from the message alone breaks the causal relationship. If you need to change the exception type, use a constructor that accepts a cause (if the API provides one) or `initCause` when designed appropriately. Do not call `fillInStackTrace()` just to "clean up" an error, as that can discard essential diagnostic traces.

## 3. Passing a Throwable to Java Util Logging (JUL)

JUL is built into Java and can be used without extra libraries:

```java
import java.util.logging.Level;
import java.util.logging.Logger;

Logger logger = Logger.getLogger("demo.orders");

// Assuming error is a caught Throwable.
logger.log(Level.SEVERE, "event=order.persist_failed", error);
```

The snippet above is **illustrative**, not a standalone runnable class; the `error` variable must exist in the catch context. When calling the `log(Level, String, Throwable)` overload properly:

1. `Level.SEVERE` indicates the severity of the final error in the example.
2. The message carries the event type and context useful to readers.
3. `error` is preserved as a `Throwable` in `LogRecord.getThrown()`.
4. The formatter decides whether to display the stack trace, cause, and suppressed exceptions.

### Watch out for parameter overloads vs. Throwable overloads

JUL has these notable overloads:

| Call | Meaning |
| --- | --- |
| `logger.log(level, message)` | Logs the message without a throwable. |
| `logger.log(level, message, (Throwable) error)` | Logs the message and sets `error` in the thrown field. |
| `logger.log(level, "Order {0} failed", (Object) orderId)` | One parameter used by the formatter to replace `{0}` (if supported by the formatter). |
| `logger.log(level, "Order {0}, retry {1}", new Object[]{orderId, attempt})` | Multiple formatting parameters. |
| `logger.log(LogRecord record)` | Logs a prepared record that can hold *both parameters and thrown*. |

**Java overload resolution trap:** If `ex` has type `Throwable` or a subtype and you write:

```java
// Do not use this when the intent is to replace {0} with the exception:
logger.log(Level.SEVERE, "Failure caused by {0}", ex);
```

Java selects the overload accepting `Throwable` (more specific than `Object`). As a result, `ex` becomes the attached throwable, **not the `{0}` format argument**, and `{0}` may remain unformatted in the message. To log with an exception, write a clear event-descriptive message and pass `ex` as the final `Throwable` argument:

```java
logger.log(
    Level.SEVERE,
    "event=job.failed jobId=job-9",
    ex
);
```

The two snippets above are also **illustrative** in a context where `logger` and `ex` already exist. Do not concatenate the full exception string into the message and also pass the same exception if that creates unnecessary duplication.

### When you need both placeholders and a Throwable in JUL

JUL does not have a `log(Level, String, Object[], Throwable)` overload. You can construct a `LogRecord` explicitly:

```java
// Illustrative example; assuming logger, orderId, and ex already exist.
java.util.logging.LogRecord record = new java.util.logging.LogRecord(
        java.util.logging.Level.SEVERE,
        "event=order.failed orderId={0} outcome={1}"
);
record.setParameters(new Object[]{orderId, "failed"});
record.setThrown(ex);
record.setLoggerName(logger.getName());
logger.log(record);
```

A formatter calling `formatMessage(record)` will substitute `{0}` and `{1}` as supported by JUL while still having access to `record.getThrown()`. In applications with structured logging, prefer the framework's field/attribute API to store `orderId` structurally while keeping `Throwable` separate.

## 4. Passing Exceptions with SLF4J

SLF4J is a **logging facade** commonly used with Logback or another provider. The Java code below is an **illustrative snippet requiring the SLF4J dependency** and will not compile with the plain JDK alone:

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

class OrderService {
    private static final Logger LOG =
            LoggerFactory.getLogger(OrderService.class);

    void save(String orderId) {
        try {
            persist(orderId);
        } catch (RuntimeException ex) {
            LOG.error(
                    "event=order.persist_failed orderId={}",
                    orderId,
                    ex
            );
            throw ex;
        }
    }

    void persist(String orderId) {
        throw new IllegalStateException("Storage unavailable");
    }
}
```

The `{}` syntax is SLF4J's parameter placeholder convention, **unlike `{0}` in JUL**. In the call above, `orderId` fills the placeholder, while `ex` is the `Throwable` in the trailing position, recognized by SLF4J as the exception (across standard overloads and implementations).

You can also use the explicit form without formatting parameters:

```java
LOG.error("event=order.persist_failed", ex);
```

This is the `error(String, Throwable)` overload. When using placeholders, pass all data arguments **before** the trailing exception; avoid passing an exception as a "string substitution argument" if you want the stack trace.

Cases to watch out for:

- `LOG.error("Failed orderId={}", orderId, ex)`: business parameter `orderId` followed by throwable `ex` at the end; clear intent.
- `LOG.error("Failed", ex)`: valid, but lacks the order ID; add context if needed.
- `LOG.error("Failed: " + ex.getMessage())`: passes only a string; does not attach the exception to the event.
- `LOG.error("Failed: {}", ex)`: easily misunderstood due to the `Throwable` overload vs. placeholder; if you want to log the error, use a fixed message and pass the throwable in the proper position.
- `LOG.error("Failed orderId={} error={}", orderId, ex)`: risks leaving an unmatched placeholder or misinterpreting arguments because the trailing throwable is handled specially; it is best to use placeholders only for regular data and pass the throwable last.

SLF4J 2.x provides a fluent API (`atError()`, `setCause(...)`, `addKeyValue(...)`) that supports expressing causes and fields explicitly when backed by a compatible provider. Which API to use depends on your version and configured backend; do not mix SLF4J syntax with JUL.

## 5. Standalone Java 17 Example: Preserving Cause and Passing the Exception to the Logger

The following program simulates an order persistence failure: the low-level layer throws `IOException`, the business layer **wraps the exception and preserves the cause**, and the boundary layer catches `IllegalStateException` and logs it once with the `Throwable`. The program intentionally uses a single-line formatter showing only the exception type and cause so that stdout stays predictable. **In real systems, formatters usually need to print the full stack trace**, not just a summary like this example.

Save as **`ExceptionPassingDemo.java`**:

```java
import java.io.IOException;
import java.util.logging.Formatter;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;
import java.util.logging.StreamHandler;

public class ExceptionPassingDemo {
    private static final Logger LOG =
            Logger.getLogger(ExceptionPassingDemo.class.getName());

    public static void main(String[] args) {
        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.INFO);

        Handler output = new StreamHandler(System.out, new Formatter() {
            @Override
            public String format(LogRecord record) {
                StringBuilder line = new StringBuilder()
                        .append(record.getLevel().getName())
                        .append(' ')
                        .append(formatMessage(record));

                Throwable thrown = record.getThrown();
                if (thrown != null) {
                    line.append(" | thrown=")
                        .append(thrown.getClass().getSimpleName())
                        .append(": ")
                        .append(thrown.getMessage());

                    Throwable cause = thrown.getCause();
                    if (cause != null) {
                        line.append(" | cause=")
                            .append(cause.getClass().getSimpleName())
                            .append(": ")
                            .append(cause.getMessage());
                    }
                }
                return line.append(System.lineSeparator()).toString();
            }
        });
        output.setLevel(Level.ALL);
        LOG.addHandler(output);

        try {
            processOrder("ord-42");
        } catch (IllegalStateException failure) {
            // Log once at the boundary where the final outcome is known.
            LOG.log(
                    Level.SEVERE,
                    "event=order.persist_failed orderId=ord-42 outcome=failed",
                    failure
            );
        } finally {
            output.flush();
            LOG.removeHandler(output);
        }
    }

    private static void processOrder(String orderId) {
        try {
            persist(orderId);
        } catch (IOException cause) {
            // Translate across abstraction layers, while preserving the cause.
            throw new IllegalStateException(
                    "Cannot persist " + orderId,
                    cause
            );
        }
    }

    private static void persist(String orderId) throws IOException {
        throw new IOException("Storage unavailable");
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac ExceptionPassingDemo.java
java ExceptionPassingDemo
```

**Exact standard output** (one line; excluding the shell prompt):

```text
SEVERE event=order.persist_failed orderId=ord-42 outcome=failed | thrown=IllegalStateException: Cannot persist ord-42 | cause=IOException: Storage unavailable
```

Step-by-step explanation:

1. `persist` throws `IOException("Storage unavailable")`, representing a storage-layer failure.
2. `processOrder` catches the I/O error and creates `IllegalStateException("Cannot persist ord-42", cause)`. Because `cause` is passed, the root error remains traceable.
3. `main` is the boundary that knows the operation did not complete, so it logs at `SEVERE` exactly once. The third argument of `LOG.log(Level.SEVERE, message, failure)` is a `Throwable`, not a string or placeholder parameter.
4. `record.getThrown()` in the formatter receives `IllegalStateException`; `getCause()` leads back to `IOException`. This proves the exception was **attached to the record**, not merely interpolated as text into the message.
5. The custom formatter intentionally omits stack frames to keep output deterministic; replace it with a stack-trace-printing formatter in production when investigation is needed. With the default `java.util.logging.SimpleFormatter`, the output also includes timestamp, source, and stack trace, so it will not match the single-line output above.
6. `output.flush()` flushes `StreamHandler` data to `System.out`; `setUseParentHandlers(false)` prevents duplicate printing from parent handlers. In real applications, handlers are normally configured at startup rather than created per request.

The example handles the error at the `main` boundary and exits after logging; real server applications must return an error response matching their contract or let an exception handler process it further. Never treat a `log` call as data recovery.

## 6. When to Log vs. When to Propagate the Exception Upward

An exception may pass through multiple layers:

```text
Repository
   |  throws IOException
   v
Service
   |  wraps IllegalStateException(cause)
   v
Controller / job runner
   |  knows final outcome
   v
Logs one failure event (with Throwable)
```

Each layer knows part of the context, but not every layer should print a stack trace. A common policy is **log once at the boundary responsible for the final outcome**:

- **Repository:** throws errors with technical context and does not need to log on its own if the service or caller will handle it. If wrapping with a cause, preserve the causal chain.
- **Service:** may translate an infrastructure exception into a business-appropriate error using a cause-accepting constructor; add an error code or context if needed.
- **Controller / job runner / message consumer:** knows whether the request/job ultimately succeeded, failed, or recovered. Log an event with the appropriate level, a clear message, and the `Throwable` when needed.
- **Global exception handler:** if this handler already logs request errors, avoid having the controller or service also log the full stack trace and then rethrow the same exception.

**Not every exception warrants `ERROR/SEVERE`.** An invalid input rejected per contract can be a normal outcome; a timeout that is retried and eventually succeeds may only need `DEBUG` or conditional `WARN` information. The level reflects the *actual operational impact*, not merely the presence of an exception.

### Log and throw: when does it make sense?

The pattern:

```java
catch (RuntimeException ex) {
    logger.log(Level.SEVERE, "event=job.failed", ex);
    throw ex;
}
```

makes sense **only if that layer is the official recording boundary** and upper layers simply propagate the error without logging it again. If every layer does this, one failure produces multiple duplicate `SEVERE` logs, complicating investigation and causing alert noise. When rethrowing the same exception with `throw ex;`, the original object and stack trace are preserved; do not wrap it unless changing abstraction levels or adding useful context.

In some systems, "log first then rethrow" can even record `failed` in the logs while an outer layer executes a successful fallback. Choose the log level and logging location based on the scope where you actually know the final outcome.

## 7. Cause Chains, Suppressed Exceptions, and Asynchronous Errors

### Cause chains

An error is often wrapped across multiple layers:

```text
OrderProcessingException
   caused by -> IllegalStateException
                 caused by -> IOException
```

When passing the outermost exception to a logging framework with an appropriate stack trace formatter, causes appear as `Caused by: ...` sections. If you only log `getMessage()` of the outer exception, the trail to `IOException` can vanish.

Avoid forcing every error down to its "root cause" and passing only that root cause, as doing so can lose the business layer's message and stack trace showing which operation failed. Usually you should keep and log **the exception representing the final failure together with its entire cause chain**.

### Suppressed exceptions

`try-with-resources` can record an error thrown while closing a resource as a suppressed exception on the primary error. Example in an appropriate context:

```java
// Illustrative snippet showing how to inspect Throwable details.
for (Throwable suppressed : error.getSuppressed()) {
    System.out.println(suppressed.getClass().getName());
}
```

You do not need to manually print suppressed exceptions in application code when standard formatters already output the full stack trace; this example simply highlights that `getSuppressed()` exists alongside `getCause()`. Passing the `Throwable` properly gives the framework the chance to surface this information; whether it actually renders depends on the formatter/collector.

### Asynchronous code

With `Future.get()`, an exception inside the task may be wrapped in `ExecutionException`. With `CompletableFuture.join()`, you may encounter `CompletionException`. When investigating, inspect `getCause()` to find the task's underlying cause. Do not concatenate the wrapper's `getMessage()` and discard the `Throwable` object.

For retries, an internal failure is not necessarily the final outcome. Log with `attempt`, `maxAttempts`, and `outcome` if needed, but avoid logging `ERROR` on every attempt when retries are expected; evaluate when the overall operation finishes.

With `InterruptedException`, follow the cancellation contract: typically rethrow it or restore the interrupt flag via `Thread.currentThread().interrupt()` when rethrowing is not possible. Merely logging and swallowing an interrupt can break cancellation handling.

## 8. Passing Exceptions with Context Without Exposing Sensitive Data

Exception details often contain data produced by libraries or external systems. `getMessage()`, stack traces, and causes can carry URLs, queries, file paths, connection details, personal identifiers, or payloads. **Passing a `Throwable` through the right API does not mean it is safe to expose its full contents everywhere**.

When designing exception logging:

1. Record the operation name and outcome type clearly: `event=order.persist_failed`, `outcome=failed`, `errorCode=STORAGE_UNAVAILABLE`.
2. Include only approved IDs: `orderId` or `requestId` where appropriate; never use passwords, tokens, or cookies as correlation IDs.
3. Use stable error codes instead of relying solely on exception text that can change across versions.
4. Consider masking/redaction at the source and ingestion pipeline, along with access control, retention, and stack trace collection policies.
5. Avoid concatenating raw request bodies, SQL with sensitive values, `Authorization` headers, or `ex.toString()` into messages if there is any risk of data exposure.
6. If an exception originates from untrusted input, watch out for newlines and control characters that can make text logs unreadable or forged; use a proper formatter/encoder rather than hand-building JSON strings.

In particular, writing `Throwable` to centralized logs can expose internal details via stack traces. This is operational data that requires access control, not information to return to end users by default. HTTP responses should use controlled error codes/messages and never return raw stack traces to clients.

## 9. Performance and Exception Formatting

Creating exceptions with stack traces, formatting traces, and writing them to a sink all carry a cost. When errors occur thousands of times per second, logging full stack traces on every iteration can spike CPU, I/O, and storage usage.

Considerations:

- Emit logs only at meaningful boundaries, avoiding duplicate logging of the same exception across multiple layers.
- Set levels based on impact; keep detailed diagnostics at an appropriate level enabled only when needed.
- Do not build stack trace strings manually with `StringWriter` on every code path if the logger/backend already formats `Throwable` and filters by level.
- Do not strip stack traces from important final failures just to save space. Policy-based rate limiting or sampling can be used, while preserving sufficient evidence.
- In asynchronous logging systems, understand flush policies, queues, and potential log loss if the process terminates abruptly; attaching a `Throwable` to an event does not guarantee durable persistence.
- When using structured logging, keep the exception in the standard error field supported by your backend; verify that your pipeline preserves multiline stack traces or structured exception fields.

Note: the time a log is written differs from the time the error was created; thread/trace context for an asynchronous task may need to be propagated separately. A `Throwable` by itself does not carry full correlation IDs or transaction context.

## 10. Common Exception-Passing Mistakes and Fixes

| Error-prone practice | Problem | Better approach |
| --- | --- | --- |
| `logger.severe(ex.getMessage())` in JUL | Text only; no stack trace or cause attached to the record. | `logger.log(Level.SEVERE, "event=operation.failed", ex)`. |
| `logger.log(Level.SEVERE, "Failure {0}", ex)` in JUL | May select the `Throwable` overload, leaving `{0}` unreplaced. | Use a message without placeholders + `Throwable`, or build a `LogRecord` with both `parameters` and `thrown`. |
| `LOG.error("Failure: " + ex)` with SLF4J | String concatenation only; usually loses the stack trace. | `LOG.error("event=operation.failed", ex)`. |
| `LOG.error("Failed id={}", ex)` with SLF4J | Confuses the `Throwable` overload with placeholders and misses business data. | `LOG.error("Failed id={}", id, ex)`. |
| `throw new RuntimeException(ex.getMessage())` | Loses the cause, making the root error hard to trace. | `throw new RuntimeException("Operation failed", ex)`. |
| `logger.log(Level.SEVERE, "...", ex.getCause())` | May drop the wrapper's stack trace and business context. | Usually log the outermost `ex` to preserve the full cause chain. |
| `ex.printStackTrace()` in business code | Prints to stderr outside the configured logging pipeline, levels, and context. | Use the logging API with `Throwable` and context. |
| Logging an ERROR stack trace in every catch then rethrowing | Multiple duplicate logs for one incident, obscuring impact. | Pick the responsible boundary and log once when the outcome is known. |
| Catching an exception, logging only, then returning success | Corrupts application outcome and hides failure signals from the caller. | Actually recover or throw/return an error per contract. |
| Returning full exceptions to clients | Leaks stack traces and internal details. | Log internally with access control; return a safe error code/message. |

**Do not treat every exception as a `SEVERE` incident.** For example, invalid input parsing where the application returns `400 Bad Request` per contract may not need an ERROR stack trace; conversely, a transaction persistence failure causing lost results must be recorded appropriately. `Throwable` helps investigate the root cause; **the level reflects operational significance**.

## 11. Exception Logging Review Checklist

Before finalizing a logger call in a `catch` block or global exception handler, check:

- Is the exception actually passed as a `Throwable`, or was it converted into a string?
- Does the call use the right **JUL/SLF4J overload** and the library's placeholder syntax?
- When wrapping an exception, does the constructor accept `cause` to preserve the causal chain?
- Is the logged object the outermost exception carrying useful context, without accidentally dropping cause or suppressed exceptions?
- Does the message state the **event, operation, relevant entity, outcome, and error code** without leaking secrets?
- Is the same error being logged repeatedly across layers, or logged as an error while a retry/fallback could still succeed?
- Does the level reflect the final impact, and do the logger/handler/appender actually allow recording this event?
- Do the formatter and centralized logging system display/collect stack traces, causes, and context fields as expected?
- In recovery cases, does the code genuinely handle the error? In failure cases, is the exception or error state propagated to the responsible boundary?
- Do exception contents and stack traces go through access control, sensitive-data filtering, and retention per policy?

**Core principle:** Pass `Throwable` to the logger using the right API to preserve technical traces; propagate or wrap exceptions in code with `throw` and `cause` to carry failures across layers; and log failure events only where you have full visibility into the outcome. The message describes *what failed*, while the exception helps find *why it failed*.