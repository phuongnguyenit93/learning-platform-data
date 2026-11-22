# Logging the Full Exception Object Instead of Just `getMessage()` in Java

When a Java operation fails, a statement like `logger.error("Error: {}", exception.getMessage())` may produce a log line that looks informative enough. However, when you need to know which line of code triggered the error, which call led to it, or whether there is an underlying exception, a single message is usually not enough. **Passing the `Throwable` object to the logger** allows the system to record the exception type, stack trace, cause chain (`cause`), and any attached suppressed exceptions (`suppressed exception`) supported by the formatter.

This topic belongs to error diagnostics and logging skills. The goal is to distinguish the data returned by `getMessage()` from the data of the entire exception, use Java logging APIs properly, preserve the cause when wrapping or rethrowing errors, and avoid noisy logs or information leaks.

## 1. What Does a `Throwable` Actually Contain?

In Java, both `Exception` and `Error` extend `Throwable`. A `Throwable` object can carry several pieces of data:

| Component | How to Access | Meaning |
| --- | --- | --- |
| Exception type | `exception.getClass()` | Identifies the error category: `IOException`, `IllegalStateException`, `NumberFormatException`... |
| Message | `exception.getMessage()` | Short description provided where the exception was created; **can be `null`** |
| Description line | `exception.toString()` | Typically the exception class name followed by the message if present |
| Call stack | `exception.getStackTrace()` | Stack frames relevant to when the exception's stack trace was created/populated |
| Cause | `exception.getCause()` | The underlying exception that led to the current exception, if linked |
| Suppressed exceptions | `exception.getSuppressed()` | Additional exceptions, commonly occurring when closing resources with `try-with-resources` |

`getMessage()` **only retrieves a single string**. It cannot carry the stack trace, exception class name, cause chain, or suppressed exceptions on its own. Even if the message says "Cannot load invoice", we still need to know where the operation failed and whether the root cause was a lost connection, access permission, or invalid data.

Example:

```java
java.io.IOException root = new java.io.IOException("disk unavailable");
IllegalStateException error =
        new IllegalStateException("cannot load invoice 42", root);

System.out.println(error.getMessage());
System.out.println(error.getCause().getClass().getSimpleName());
```

Output:

```text
cannot load invoice 42
IOException
```

This is an **illustrative snippet placed inside a method**, not a standalone Java program. The two output lines show that the outer error's message **does not automatically include** the `IOException` cause; someone diagnosing the issue must follow `getCause()` or use a formatter that accepts the full `Throwable`.

## 2. Comparison: Logging Only the Message vs. Logging the Full Exception

In an application using the SLF4J library (for example, SLF4J backed by Logback), compare:

```java
try {
    loadInvoice(invoiceId);
} catch (Exception exception) {
    logger.error("Cannot load invoice {}: {}",
            invoiceId, exception.getMessage()); // Missing Throwable.
}
```

with:

```java
try {
    loadInvoice(invoiceId);
} catch (Exception exception) {
    logger.error("Cannot load invoice {}", invoiceId, exception);
}
```

Both blocks above are **illustrative snippets inside an application** that already has `logger`, `invoiceId`, and `loadInvoice(...)`; they cannot run standalone without those declarations and the SLF4J library. The `{}` syntax is SLF4J's message parameterization mechanism, **not** `java.util.logging` syntax.

In the first snippet, the logger only receives a string from `exception.getMessage()`: the exception type name, stack frames, and underlying cause are usually lost. In the second snippet, the logger receives the `Throwable` as an exception argument; with a logging backend configured to record errors, the log entry can include the stack trace and cause chain.

If there are no business parameters, the clearest form is usually:

```java
logger.error("Cannot load invoice", exception);
```

Here, the second parameter is `Throwable`, directly expressing the intent to log the exception. When using `{}`, follow the library's contract; in standard SLF4J, a `Throwable` in the final position of a parameterized call is recognized as the exception argument. Do not force the formatter to guess the error from an already-converted string.

## 3. Standalone Java 17+ Example: Logger Receiving the Full `Throwable`

Standard Java already includes `java.util.logging` (JUL), requiring no extra libraries. The following example creates a small handler to print the received fields in a **fixed** format, making it easy to verify without depending on environment timestamps or formatter patterns. In a real application, use your configured logging handler/backend; the test handler here is only for observation.

Create the file **`ExceptionLoggingDemo.java`**:

```java
import java.io.IOException;
import java.io.PrintWriter;
import java.io.StringWriter;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class ExceptionLoggingDemo {
    static void readInvoice() throws IOException {
        throw new IOException("disk unavailable");
    }

    static void processInvoice() {
        try {
            readInvoice();
        } catch (IOException cause) {
            throw new IllegalStateException("cannot load invoice 42", cause);
        }
    }

    public static void main(String[] args) {
        Logger logger = Logger.getLogger("demo.exception.logging");
        logger.setUseParentHandlers(false);
        logger.setLevel(Level.ALL);

        Handler demoHandler = new Handler() {
            @Override
            public void publish(LogRecord record) {
                Throwable error = record.getThrown();
                StringWriter buffer = new StringWriter();

                if (error != null) {
                    error.printStackTrace(new PrintWriter(buffer));
                }

                String trace = buffer.toString();
                System.out.println("level=" + record.getLevel());
                System.out.println("logMessage=" + record.getMessage());
                System.out.println("throwableAttached=" + (error != null));
                System.out.println("originInTrace="
                        + trace.contains("at ExceptionLoggingDemo.readInvoice("));
                System.out.println("causeInTrace=" + trace.contains(
                        "Caused by: java.io.IOException: disk unavailable"));
            }

            @Override
            public void flush() {}

            @Override
            public void close() {}
        };

        demoHandler.setLevel(Level.ALL);
        logger.addHandler(demoHandler);

        try {
            processInvoice();
        } catch (IllegalStateException exception) {
            System.out.println("onlyMessage=" + exception.getMessage());
            logger.log(Level.SEVERE, "Invoice processing failed", exception);
        } finally {
            logger.removeHandler(demoHandler);
            demoHandler.close();
        }
    }
}
```

Compile and run:

```bash
javac --release 17 ExceptionLoggingDemo.java
java ExceptionLoggingDemo
```

Output:

```text
onlyMessage=cannot load invoice 42
level=SEVERE
logMessage=Invoice processing failed
throwableAttached=true
originInTrace=true
causeInTrace=true
```

Explanation:

1. `readInvoice()` throws `IOException("disk unavailable")`. `processInvoice()` wraps the error into `IllegalStateException` with business context, **while preserving the cause** via the constructor accepting a `cause` argument.
2. `exception.getMessage()` only reports `cannot load invoice 42`. If the application only logs that value, the log has no accompanying stack trace or cause.
3. `logger.log(Level.SEVERE, "Invoice processing failed", exception)` uses the overload accepting `Throwable`. `LogRecord.getThrown()` in the handler returns the exact exception object attached to the record.
4. `Throwable.printStackTrace(...)` lets the handler inspect the full representation containing the `readInvoice()` call frame and the `Caused by: java.io.IOException: disk unavailable` line. The two `true` values prove this without depending on line numbers or timestamps.

With JUL, the typical call can be as simple as:

```java
logger.log(Level.SEVERE, "Failed to process invoice", exception);
```

This is an illustrative line in a scope that already has `java.util.logging.Logger logger` and an `exception` variable. When using `java.util.logging`, parameterized messages follow `MessageFormat` placeholders `{0}`, `{1}`, unlike `{}` in SLF4J. For example:

```java
logger.log(Level.SEVERE, "Invoice {0} failed", new Object[] {invoiceId});
```

The last line only illustrates **message parameterization** in JUL; this call **does not attach an exception**. If you need both business data and a `Throwable`, you can construct a safe message and call the three-argument overload `(Level, String, Throwable)`, or use the logging platform's contextual record mechanism.

## 4. Why Is `getMessage()` Often Insufficient for Diagnostics?

### 4.1. The Message Can Be Empty or Lack Context

Not every exception constructor is passed a message:

```java
RuntimeException failure = new RuntimeException();
System.out.println(failure.getMessage() == null);
System.out.println(failure.getClass().getSimpleName());
```

Output:

```text
true
RuntimeException
```

This is an illustrative snippet inside a method. A log that only records `failure.getMessage()` may print `null`, whereas the class name and stack trace still help identify the error. Some APIs also use generic messages like "request failed"; only the stack trace and cause help trace the actual execution path.

### 4.2. The Message Does Not Reveal Where the Error Originated

Two operations that both throw `IllegalArgumentException("invalid id")` can originate in two different processing branches. Their `getMessage()` values are identical, whereas the stack trace pinpoints the methods and lines of code involved in each creation/throw site.

Note: the stack trace is typically captured when the exception is created or when `fillInStackTrace()` is called; do not assume the logger invents the call history at logging time. A reused exception or one created with stack trace recording disabled may not contain the expected frames. Stack traces can also be missing or truncated due to JVM optimizations or library configuration.

### 4.3. The Message Does Not Contain the Cause Chain

A business error can span multiple layers:

```text
IllegalStateException: cannot load invoice 42
    caused by IOException: disk unavailable
        caused by FileNotFoundException: /data/invoices/42.json
```

This example is a **conceptual cause chain**, not stdout from the program above. If you only log the outermost exception's message, you may miss the most critical part at the I/O layer. When logging the full `Throwable`, a standard formatter typically renders the `Caused by:` blocks and their associated stack frames.

You should not always strip all wrappers just to log only the deepest cause. The outermost exception can carry **meaningful context**, such as the operation name or the business rule that failed. Logging the full chain preserves both the business context and the technical root cause.

### 4.4. Resource-Closing Errors May Reside in `getSuppressed()`

In `try-with-resources`, if the `try` body throws an exception and `close()` also throws, Java keeps the exception from the `try` body as the primary error and adds the resource-closing error to the suppressed exceptions list. The primary error's `getMessage()` does not show that additional event.

## 5. Second Example: Full Logging Preserves Suppressed Exceptions

Create the file **`SuppressedExceptionDemo.java`**:

```java
import java.io.IOException;
import java.io.PrintWriter;
import java.io.StringWriter;

public class SuppressedExceptionDemo {
    static class BrokenResource implements AutoCloseable {
        @Override
        public void close() throws IOException {
            throw new IOException("close failed");
        }
    }

    static void useResource() throws IOException {
        try (BrokenResource resource = new BrokenResource()) {
            throw new IOException("read failed");
        }
    }

    public static void main(String[] args) {
        try {
            useResource();
        } catch (IOException exception) {
            System.out.println("onlyMessage=" + exception.getMessage());
            System.out.println("suppressedCount="
                    + exception.getSuppressed().length);

            StringWriter buffer = new StringWriter();
            exception.printStackTrace(new PrintWriter(buffer));
            String trace = buffer.toString();
            System.out.println("primaryInTrace="
                    + trace.contains("java.io.IOException: read failed"));
            System.out.println("suppressedInTrace=" + trace.contains(
                    "Suppressed: java.io.IOException: close failed"));
        }
    }
}
```

Run:

```bash
javac --release 17 SuppressedExceptionDemo.java
java SuppressedExceptionDemo
```

Output:

```text
onlyMessage=read failed
suppressedCount=1
primaryInTrace=true
suppressedInTrace=true
```

The `read failed` error is the primary exception. While exiting `try-with-resources`, `close()` also throws `close failed`; Java attaches this error to the primary exception via `addSuppressed` under the `try-with-resources` mechanism. If you only log `getMessage()`, the `close failed` information disappears from the log. Logging the full `Throwable` with a backend that supports stack traces makes both visible.

`getSuppressed()` can also be empty, and some exceptions have suppression disabled. Do not assume every resource-closing error is always in suppressed: the behavior depends on the `try` structure, the resources, and which exception is thrown first.

## 6. Placing `Throwable` in the Right Position Across Logging APIs

### 6.1. Java Util Logging (`java.util.logging`)

```java
logger.log(Level.SEVERE, "Cannot load customer", exception);
```

This is the clear choice when using JUL: the third argument is `Throwable`, stored in the `LogRecord`. If you want to change the order or formatting of fields, that is the formatter/handler's responsibility.

Contrast this with:

```java
logger.severe("Cannot load customer: " + exception.getMessage());
```

The second snippet only sends a string to JUL. There is no `Throwable` reference in the record, so the formatter cannot infer the stack trace or cause.

### 6.2. SLF4J and Backends Like Logback

```java
logger.error("Cannot load customer {}", customerId, exception);
```

This is an **illustrative snippet** in an application with SLF4J, `logger`, and a `customerId` variable. In standard SLF4J usage, the trailing `Throwable` argument is attached to the logging event, while `{}` receives `customerId`. You can use the direct overload `logger.error("Cannot load customer", exception)` when parameterization is not needed.

Conversely:

```java
logger.error("Cannot load customer {}: {}",
        customerId, exception.getMessage());
```

Only logs the error message as a string; no stack trace accompanies the record.

Watch out for specific APIs: many libraries have different overloads for `String`, `Object`, varargs, and `Throwable`. If your project's logging wrapper does not recognize a trailing `Throwable` like SLF4J does, use the overload or `cause` field specified by that wrapper's contract. Do not rely on how a custom function converts arguments to strings.

### 6.3. `System.Logger` in Java

Besides JUL, Java also has `System.Logger`. You can write:

```java
System.Logger log = System.getLogger("billing");
log.log(System.Logger.Level.ERROR, "Cannot load customer", exception);
```

This is an illustrative snippet that can be placed inside a Java method or program. The overload accepting `Throwable` sends the exception information to the platform's logger. The exact presentation depends on the logging/provider configuration.

In all three approaches, the principle is the same: **pass the exception object itself to a logging API that supports `Throwable`**; calling `.getMessage()` before logging discards the unconverted information fields.

## 7. Preserving the Cause When Catching and Rethrowing Exceptions

Logging the full stack trace cannot rescue the cause chain if the code discarded it earlier.

Example of what **not to do**:

```java
try {
    repository.load(id);
} catch (java.io.IOException exception) {
    throw new IllegalStateException(exception.getMessage());
}
```

This is an illustrative snippet requiring `repository` and `id`. The new exception is not linked to the old `IOException`. A logger that receives the `IllegalStateException` later cannot reconstruct the discarded cause.

Replace with:

```java
try {
    repository.load(id);
} catch (java.io.IOException exception) {
    throw new IllegalStateException(
            "Cannot load record " + id, exception);
}
```

The constructor accepting `cause` preserves the original exception while adding operational context. In cases where you only need to propagate the error without adding meaning, `throw exception;` may be preferable to creating a new wrapper.

**Avoid creating pointless wrappers at every layer.** Wrapping is only valuable when crossing an abstraction boundary or adding necessary context. A chain of a dozen `RuntimeException("failed", previous)` instances makes logs hard to read and hard to group, even though it technically preserves the cause.

## 8. At Which Boundary Should You Log to Avoid Duplicates While Keeping Visibility?

An exception may travel through repository -> service -> controller -> global error handler. If every layer logs `ERROR` with a stack trace and then rethrows, the system can produce multiple log entries for a single incident. This makes it harder to find the real root cause and generates high log volume.

A common strategy:

1. **Lower layers:** add context and rethrow if the error cannot be handled; only log here if there is a recovery action, a business decision, or diagnostic information that cannot be added at a higher layer.
2. **The error-handling layer that owns the final decision:** log the `Throwable` **once** with enough request ID/operation name to correlate it, and translate it into an appropriate response or failure status.
3. **A layer that recovered from the error:** may log `WARN` with the fallback reason if monitoring is needed; it does not necessarily need to print a full stack trace for an expected, frequent condition.
4. **Severe or unexpected errors:** forward full cause details to the monitoring system, prioritizing stack trace searchability and safe context.

There is no single `ERROR` logging location that fits every architecture; what matters is that **logging ownership is clear**. Consider logging once at a boundary that has sufficient context, rather than logging and rethrowing indefinitely.

## 9. Exceptions in `CompletableFuture`, `ExecutorService`, and Callbacks

With asynchronous tasks, the calling thread may receive a **wrapped** exception instead of the original one:

- `Future.get()` typically throws `ExecutionException`, where `getCause()` holds the task's failure.
- `CompletableFuture.join()` typically throws `CompletionException`, where `getCause()` holds the source failure.
- A `whenComplete((value, error) -> ...)` callback receives a `Throwable` when the stage fails; `error` may be the original exception or a technical wrapper depending on the pipeline.

Example illustrating a logging boundary:

```java
try {
    future.join();
} catch (java.util.concurrent.CompletionException exception) {
    logger.error("Async invoice computation failed", exception);
    throw exception;
}
```

This snippet requires a `CompletableFuture<?> future` and an application `logger`; it uses the SLF4J `logger.error` API. When the logger is passed **the full `CompletionException`**, the formatter can print the `Caused by:` chain. If the handling layer wants to classify the root error, it can unwrap `CompletionException`/`ExecutionException` to choose a policy, while keeping the original chain in the log to show the path through the future.

A program that calls `submit()` but discards the `Future`, or creates a `CompletableFuture` with nothing observing its failure, can miss logging altogether. A failed task does not mean the system automatically calls a logger. The design must specify **who observes the result and is responsible for handling errors**.

In a `whenComplete` callback, if you only want to observe, avoid letting the log statement itself throw a new exception. A failing callback can alter the state of the returned stage. With standard loggers this risk is rare, but custom code making network/I/O calls inside a callback still needs careful control.

## 10. Reading Full Logs to Trace Errors

A log entry with a stack trace looks like:

```text
java.lang.IllegalStateException: cannot load invoice 42
    at ExceptionLoggingDemo.processInvoice(ExceptionLoggingDemo.java:...)
Caused by: java.io.IOException: disk unavailable
    at ExceptionLoggingDemo.readInvoice(ExceptionLoggingDemo.java:...)
```

This is an **illustrative format**; `...` indicates line numbers that depend on the source file rather than guaranteed stdout. When analyzing:

- The first line describes the **reported exception** at the logging boundary.
- The `at ...` lines show the call frames associated with the stack trace. Check the first frame belonging to application code, as well as the call path leading into it.
- `Caused by:` indicates the underlying error preserved via `getCause()`.
- `Suppressed:`, if present, usually indicates secondary errors such as resource-closing failures.
- The `... N more` section in a stack trace is Java's way of eliding frames shared between the cause and the wrapper; it does not mean cause data was lost.

Do not look only at the top-level line and conclude the bug is in the controller, endpoint, or `join()`. Those locations may simply be where the error **was observed**, while the initial cause was created in a repository/worker in another part of the chain.

`exception.toString()` is more useful than `getMessage()` when you need both the class name and the message, but it **still does not replace** a log record with an attached `Throwable`.

## 11. Security, Performance, and Log Quality Principles

Full logging is a diagnostic tool; it must be used responsibly:

- **Do not put secrets into error messages or log context.** Passwords, access tokens, cookies, sensitive identifiers, or arbitrary request payloads can be logged if the application embeds them in an exception message. Passing the full `Throwable` does not automatically redact that data.
- **Minimize personal data.** Use request correlation IDs, non-sensitive business IDs, and approved error statuses. If centralized logging has filters/masking, check both the message field and the stack trace.
- **Do not assume the logger will always print the stack trace.** Output depends on the backend, formatter, log level configuration, sampling, and log sink. Verify the actual configuration to confirm the throwable field is recorded.
- **Prefer parameterized logging.** With SLF4J, the pattern `logger.error("Failed order {}", orderId, exception)` keeps parameter structure and avoids manual message string concatenation. Pay attention to the library's specific API and `Throwable` extraction mechanism.
- **Limit repetitive logging.** An error occurring thousands of times in a loop should not unconditionally generate thousands of large stack traces. Consider batched alerts, metric counters, sampling, or lowering the log level once the incident is identified.
- **Use appropriate log levels.** `INFO`, `WARN`, and `ERROR`/`SEVERE` should reflect impact and required action, not logging at the highest level just because an `Exception` occurred.
- **Do not rely on `printStackTrace()` directly in production.** It is useful for learning or testing, but writing to stderr does not provide the routing, log levels, correlation IDs, and data policies of a logging platform.
- **Do not swallow errors after logging.** If a method cannot recover, propagate the error or return an appropriate failure result; logging and then returning a "success" value without explanation makes discrepancies hard to detect.

## 12. Diagnostic Checklist and Self-Check Questions

When encountering an unexplained "Failed to process" line, check:

1. In the `catch` branch, does the system **pass the `Throwable` to the logger**, or does it only convert it to `getMessage()`/`toString()`?
2. When wrapping an error, does the constructor **accept `cause`**?
3. Does the log include the exception type name, stack trace, `Caused by:`, and (if applicable) `Suppressed:`?
4. Is the error logged at the boundary that owns handling, or is it logged repeatedly across multiple layers?
5. For asynchronous work, does the code **retain and check the `Future`/`CompletableFuture`**, or are errors ignored?
6. Does the logged content contain sensitive data or generate excessive duplicate records?

**Q1.** Can `exception.getMessage()` be `null`?  
**A:** Yes. It is only an optional description, not the entire exception.

**Q2.** Does `logger.error("Failed: {}", exception.getMessage())` guarantee saving the stack trace?  
**A:** No. Under standard SLF4J usage, the logger only receives a string from `getMessage()` in this case.

**Q3.** How do you log with JUL to pass the entire exception?  
**A:** `logger.log(Level.SEVERE, "Operation failed", exception)`; this overload places the `Throwable` into the `LogRecord`.

**Q4.** Does `throw new IllegalStateException(exception.getMessage())` preserve the cause?  
**A:** No. Use `new IllegalStateException("context", exception)` when you need to preserve the cause.

**Q5.** Why is `getSuppressed()` important?  
**A:** It can hold errors that occurred while closing resources, while the primary error remains the exception thrown from the `try` body.

**Q6.** Should you log the full stack trace at every layer?  
**A:** Not necessarily. Choose a boundary with sufficient context and handling responsibility, avoiding pointless duplicate logs of the same incident.

**Q7.** Can `toString()` replace logging the full `Throwable`?  
**A:** No. `toString()` typically contains the class name and message, but it does not carry the full stack trace/cause/suppressed exceptions as a complete error record.

Practical takeaway: **pass the exception object to a logging API that supports `Throwable`**, preserve the cause when wrapping errors, and log safe operational context. `getMessage()` is useful for displaying a short message, but it is not enough as diagnostic evidence when an error needs to be investigated.