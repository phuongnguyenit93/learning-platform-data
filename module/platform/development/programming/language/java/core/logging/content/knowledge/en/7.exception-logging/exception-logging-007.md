# Preserving the Root Cause in Java Exception Logging

## 1. Goal: Preserving the Evidence Leading to Failure

When a Java operation fails, an exception usually carries far more information than the error message shown to the user. **“Not masking the cause”** means that while catching, translating, logging, or rethrowing exceptions, we preserve the evidence needed to trace back to the actual incident: **the error type, where it occurred, the preceding cause, processing context, and any secondary errors**.

For example, an order-loading operation fails at the application layer, while the initial cause is a timeout at the storage layer:

~~~text
IllegalStateException: Cannot load orderId=O-42
    Caused by: IOException: connection timed out
~~~

If the application layer only throws `new IllegalStateException("Cannot load order")` and discards the `IOException` object, an investigator can see which operation failed, but can no longer see **why** loading the order failed. Conversely, if the application layer adds context and passes the original exception as the cause, the log can tell the whole failure story.

Preserving the cause **does not mean printing a stack trace at every layer**. A preserved exception can be logged once at the boundary responsible for recording the failure. The responsibility of intermediate layers is to preserve and enrich context without losing the trail.

This lesson explains:

- What a `Throwable` contains and how to read a `Caused by` chain.
- Practices that commonly mask the cause: swallowing exceptions, throwing a new exception without a cause, logging only the message, throwing another error from `finally`, or clearing the interrupt status.
- When to rethrow, when to wrap, and how to log properly with JUL/SLF4J.
- How to read **suppressed exceptions** from `try-with-resources`, distinguishing the primary error from errors raised while closing resources.
- How to preserve diagnostic information internally while limiting information exposure externally.

## 2. Understanding the Throwable Structure Before Handling It

In Java, both `Exception` and `Error` extend `Throwable`. A `Throwable` instance can contain:

| Component | How to Access | Investigation Value |
| --- | --- | --- |
| Exception type | `e.getClass()` | Identifies I/O errors, business errors, state violations, etc. |
| Message | `e.getMessage()` | Short description of the error at the layer that created the exception |
| Stack trace | `e.getStackTrace()`, `e.printStackTrace()` | Call path to where the exception was created/captured, depending on how the object was constructed |
| Cause | `e.getCause()` | The underlying exception explaining why the current exception occurred |
| Suppressed | `e.getSuppressed()` | Secondary exceptions retained while handling the primary exception, commonly during resource closing |

**A message does not replace a stack trace.** `getMessage()` might only say “connection timed out”, whereas the stack trace points to the method that initiated the connection and the call path leading there. **Cause** links a higher-level error to a lower-level error. **Suppressed** stores additional errors that should not overwrite the primary error.

Suppose you have this chain:

~~~text
IllegalStateException: Cannot finish checkout orderId=O-42
  caused by: RepositoryException: Cannot read inventory
    caused by: SocketTimeoutException: Read timed out
~~~

The outermost exception describes **the failed operation in the terminology of the current layer**. The inner causes describe **the technical mechanism that led to the failure**. Investigators typically start from the outermost error, follow `Caused by` down the chain, and correlate with stack traces and execution context. The deepest exception is not automatically the “ultimate business root cause”; it is the deepest recorded cause in **the existing chain**.

### Exception Translation Does Not Mean Losing the Cause

Translating a checked exception into an unchecked one, or translating an I/O error into a domain error, is reasonable when layer boundaries have different contracts. What to avoid is copying only the message:

~~~java
// Wrong: the original IOException is no longer attached to the new exception.
catch (IOException e) {
    throw new IllegalStateException("Cannot read configuration");
}
~~~

A better approach:

~~~java
// Right: preserve the original exception so the stack trace includes the "Caused by" section.
catch (IOException e) {
    throw new IllegalStateException("Cannot read configuration", e);
}
~~~

The two snippets above are **illustrative code inside a method that can catch IOException**, not a standalone program. The `IllegalStateException(String, Throwable)` constructor stores `e` as the cause; each exception object still retains its own stack trace. The `Caused by` chain lets whoever handles the error trace back to the originating layer.

## 3. Four Fundamental Exception-Handling Patterns

### 3.1. Rethrow: Leave the Error Meaning Unchanged

If the current layer cannot handle the error and the method contract allows propagating the original exception:

~~~java
// Illustrative method declaring throws IOException.
try {
    readConfiguration();
} catch (IOException e) {
    // Non-failing cleanup or appropriate metrics can be added here.
    throw e;
}
~~~

`throw e` propagates the same exception instance along with its existing cause and stack trace; there is no need to wrap it in a new exception. Do not call `e.fillInStackTrace()` just to rethrow: that method overwrites the exception's stack trace and can make it harder to find the original failure site.

If no extra handling is needed, you usually **do not need to write catch-and-rethrow at all**; simply let the exception propagate according to the `throws` declaration.

### 3.2. Wrap: Add Context, Preserve the Cause

The service layer may know an ID, operation name, or business boundary that the I/O layer does not. In that case, wrapping is appropriate:

~~~java
// Illustrated inside a service method.
try {
    repository.fetch(orderId);
} catch (IOException e) {
    throw new IllegalStateException(
            "Cannot load orderId=" + safeOrderId, e);
}
~~~

The service-layer message answers **which operation failed**; the cause answers **the underlying failure mechanism**. `safeOrderId` is an ID evaluated against the application's data policy. Do not include tokens, credentials, or queries containing sensitive data in the message.

Wrapping should not be unbounded. If every layer adds another wrapper with no new information, the cause chain becomes long and hard to read. Each wrapper should add **useful context or perform a valid API contract translation**.

### 3.3. Handle: Process an Anticipated Error

Not every exception needs to propagate outward. For example, an optional configuration file does not exist and the application has a documented default. In that case, you can catch the specific exception, apply the fallback, and log a record at an appropriate level if needed.

~~~java
// Illustrative fallback branch permitted by application requirements.
try {
    return loadOptionalConfig();
} catch (NoSuchFileException e) {
    LOG.log(Level.INFO, "Optional config missing; using defaults", e);
    return defaultConfig();
}
~~~

This snippet is illustrative inside a method that has `LOG`, `loadOptionalConfig`, and `defaultConfig` accordingly. Distinguish **optional file not found** (which may be expected) from errors such as permission denied or read failures (where fallback is not permitted by default). Catching the specific type prevents accidentally masking an infrastructure incident with a default value.

In some cases, fallback is normal operation and only needs a metric or a brief log, without printing a stack trace at ERROR level. The decision should be driven by operational requirements, not a rigid rule to “log every exception”.

### 3.4. Log at the Responsible Boundary, Not Everywhere

A typical, clean flow looks like this:

~~~text
Repository   : throw IOException
Service      : wrap IllegalStateException(..., cause)
API boundary : log Throwable with requestId, return safe response
~~~

If the repository, service, and controller all log the same error at ERROR level and keep throwing it upward, a single failure can produce three error logs. That creates noise and skews metrics. Choose one place **responsible for logging the failure outcome**, while intermediate layers only add context when they genuinely have new information.

**Not masking the cause** and **not duplicating logs** are compatible goals: preserve the cause all the way through, and log it in full at the right boundary.

## 4. Coding Patterns That Make the Cause Disappear

### Mistake 1: Catch and Ignore

~~~java
try {
    updateRemoteState();
} catch (Exception ignored) {
    // No reaction, no cause preserved.
}
~~~

This can give the false impression that the operation succeeded even though a failure occurred. If ignoring a specific exception is genuinely permitted, there must be a clear reason and verifiable subsequent behavior. Catching a broad `Exception` to ignore all errors often masks scenarios that were never anticipated.

### Mistake 2: Keep Only getMessage()

~~~java
catch (IOException e) {
    throw new RuntimeException(e.getMessage());
}
~~~

The new exception contains the text of `IOException` but **does not contain the original error object**. The original type and stack trace are no longer linked via `getCause()`. Use this instead:

~~~java
catch (IOException e) {
    throw new RuntimeException("Read operation failed", e);
}
~~~

### Mistake 3: Log a String Instead of the Throwable

~~~java
catch (IOException e) {
    LOG.severe("Failed: " + e.getMessage());
    throw e;
}
~~~

This log line does not attach the `Throwable` object; looking only at that log record, you have no stack trace. Rethrowing still keeps the exception in the execution flow, but the logger record is insufficient for investigation if nothing logs the Throwable later.

With JUL, when this is the place responsible for reporting the error, use an overload that accepts a Throwable:

~~~java
catch (IOException e) {
    LOG.log(Level.SEVERE, "operation=readConfig outcome=failed", e);
    throw e;
}
~~~

`Logger.log(Level, String, Throwable)` attaches the `Throwable` to the `LogRecord`. An appropriate formatter/handler will display the stack trace and cause. If another boundary is already responsible for logging the exception, consider letting that boundary log it once.

### Mistake 4: Throw a New Exception from finally

~~~java
// Illustrative example: an exception in finally can mask the preceding exception.
try {
    throw new IOException("read failed");
} finally {
    throw new IllegalStateException("cleanup failed");
}
~~~

The exception that escapes is `IllegalStateException("cleanup failed")`; the exception from the `try` block has been replaced. Avoid placing cleanup operations that can throw unchecked/unhandled errors inside `finally`. Use `try-with-resources` for eligible resources so Java preserves close errors as suppressed exceptions when a primary error exists.

Do not place `return` inside `finally` either: it can also cause an active thrown exception to vanish from control flow.

### Mistake 5: Catch Broadly and Return a Fake “Valid” Value

~~~java
// Avoid: callers may interpret 0 as a real result.
try {
    return calculateTotal();
} catch (Exception e) {
    return 0;
}
~~~

If `0` is a valid business value, the error is turned into data and can propagate into downstream operations. Only fall back when it is an explicit business requirement, with a specific exception type and a result that distinguishes the fallback state if needed.

### Mistake 6: Recreate an Exception from Another Exception's Message

Sometimes developers write `new IOException(e.toString())`, `new IllegalArgumentException(e.getMessage())`, or copy only an error code. These actions may keep a few words, but they lose the **cause** and the link to the original stack trace. Choose a constructor that accepts `Throwable`, or design domain exceptions to support a cause.

## 5. Standalone Java 17 Example: Cause, Logging, and Suppressed Exceptions

The following example simulates an I/O error at the storage layer; the service layer translates it into `IllegalStateException` with a business ID and preserves `IOException` as the cause. The JUL logger receives the Throwable. A small handler prints only verifiable details so stdout stays deterministic; it **does not replace a production formatter** (which normally prints the full stack trace).

Create **PreserveCauseDemo.java**:

~~~java
import java.io.IOException;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class PreserveCauseDemo {
    private static final Logger LOG =
            Logger.getLogger(PreserveCauseDemo.class.getName());

    static String readFromStore(String recordId) throws IOException {
        throw new IOException("connection timed out");
    }

    static String loadRecord(String recordId) {
        try {
            return readFromStore(recordId);
        } catch (IOException e) {
            throw new IllegalStateException(
                    "Cannot load recordId=" + recordId, e);
        }
    }

    static final class FailingResource implements AutoCloseable {
        @Override
        public void close() throws IOException {
            throw new IOException("close failed");
        }
    }

    static void showSuppressed() {
        try (FailingResource resource = new FailingResource()) {
            throw new IOException("read failed");
        } catch (IOException e) {
            System.out.println("primary=" + e.getMessage());
            System.out.println("suppressedCount=" + e.getSuppressed().length);
            System.out.println("suppressed[0]="
                    + e.getSuppressed()[0].getMessage());
        }
    }

    static void configureDemoLogger() {
        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.ALL);

        Handler handler = new Handler() {
            @Override
            public void publish(LogRecord record) {
                if (!isLoggable(record)) {
                    return;
                }
                System.out.println(record.getLevel().getName()
                        + " " + record.getMessage());

                Throwable thrown = record.getThrown();
                if (thrown != null) {
                    System.out.println("loggedThrowable="
                            + thrown.getClass().getSimpleName());
                    if (thrown.getCause() != null) {
                        System.out.println("loggedCause="
                                + thrown.getCause()
                                        .getClass().getSimpleName());
                    }
                }
            }

            @Override
            public void flush() {}

            @Override
            public void close() {}
        };

        handler.setLevel(Level.ALL);
        LOG.addHandler(handler);
    }

    public static void main(String[] args) {
        configureDemoLogger();

        try {
            loadRecord("R-42");
        } catch (IllegalStateException e) {
            LOG.log(Level.SEVERE,
                    "operation=loadRecord recordId=R-42 outcome=failed", e);

            System.out.println("outer=" + e.getClass().getSimpleName()
                    + ": " + e.getMessage());
            System.out.println("cause="
                    + e.getCause().getClass().getSimpleName()
                    + ": " + e.getCause().getMessage());
        }

        showSuppressed();
    }
}
~~~

Compile and run in the directory containing the file:

~~~bash
javac -encoding UTF-8 PreserveCauseDemo.java
java PreserveCauseDemo
~~~

**Exact stdout** of the program:

~~~text
SEVERE operation=loadRecord recordId=R-42 outcome=failed
loggedThrowable=IllegalStateException
loggedCause=IOException
outer=IllegalStateException: Cannot load recordId=R-42
cause=IOException: connection timed out
primary=read failed
suppressedCount=1
suppressed[0]=close failed
~~~

Analysis:

1. `readFromStore` throws `IOException("connection timed out")`.
2. `loadRecord` catches it and creates `IllegalStateException("Cannot load recordId=R-42", e)`. Because `e` is passed, `getCause()` on the new exception still returns the original `IOException`.
3. At the boundary in `main`, `LOG.log(Level.SEVERE, message, e)` passes **the exception object itself** to the logger. The demo handler shows that `record.getThrown()` is `IllegalStateException` and its cause is `IOException`. The handler intentionally prints only class names so the example does not print a full stack trace; a standard JUL formatter can print the stack trace and the `Caused by` chain.
4. In `showSuppressed`, the `try` block throws `IOException("read failed")` and `close()` also throws `IOException("close failed")`. Java keeps the read exception as **primary** and attaches the close exception to the `getSuppressed()` array. Thus the suppressed count is 1, and the read error is not masked.

The `getCause()` and `getSuppressed()` values are inspected here in a scenario where the program already knows the exception structure. In general code, **do not** access `getCause().getMessage()` or `getSuppressed()[0]` without first checking that the cause is non-null and the suppressed array is non-empty.

## 6. Logging Exceptions Properly in JUL and SLF4J

### 6.1. java.util.logging (JUL)

In JUL, use an overload designed for a Throwable:

~~~java
// Illustrated inside a catch block with LOG, recordId, and IOException e.
LOG.log(Level.SEVERE, "operation=loadRecord outcome=failed", e);
~~~

`LogRecord.getThrown()` will hold the passed exception. With `SimpleFormatter` or a Throwable-aware formatter, the log displays the stack trace along with its cause; readers can inspect the `Caused by` section to find the underlying exception.

Be careful with overloads that **do not accept a Throwable**:

~~~java
LOG.severe("Load failed: " + e.getMessage());
~~~

This line produces only a text message. If this log is the only remaining evidence, the cause is lost at the observability layer, even though the `e` object may still exist in the thread.

### 6.2. SLF4J

In a project that already has SLF4J and a provider/backend:

~~~java
// Illustrated inside a catch block; LOG is org.slf4j.Logger.
LOG.error("operation=loadRecord recordId={} outcome=failed",
        recordId, e);
~~~

In standard SLF4J parameterized logging, **the trailing Throwable** is recognized as the event's exception and passed to the backend to print the stack trace. Do not create a `{}` placeholder for the Throwable. When logging only a message and an exception, there is also the `error(String, Throwable)` overload:

~~~java
LOG.error("Load record failed", e);
~~~

Do not replace it with:

~~~java
LOG.error("Load record failed: {}", e.getMessage());
~~~

The latter passes only the exception's message string. It does not attach the Throwable and does not preserve the stack trace on that log record.

**Actual output depends on the logger and backend.** Logger levels, appenders/filters, and formatters/encoders can drop an event or render only part of it. When investigating, check both event-filtering configuration and whether the encoder includes the throwable/cause/suppressed exceptions in the output.

### 6.3. Log Once and Propagate the Cause Across Layers

If the repository throws, the service wraps, and the HTTP boundary logs the full Throwable and turns the error into a safe response, the service usually does not need to log another `ERROR` for the same exception. This optimization does not lose the cause, because `throw new DomainException(message, e)` preserves the cause until the logging boundary.

If an exception is **handled completely locally** (for example, a successful retry or a valid fallback), the handling site can log at an appropriate level or record a metric. There is no rigid rule that an exception may only be logged once in every system; the goal is to **avoid duplicate records that add no new information**.

## 7. How Do the Cause Chain and Suppressed Exceptions Differ?

Suppose a request goes through:

~~~text
ServiceException
  Caused by: RepositoryException
    Caused by: SQLException
~~~

`getCause()` describes the layers of errors **that were wrapped and propagated**. To find a deeper cause, you can walk step by step through `e.getCause()` until `null`. Still, keep the outermost exception when reporting, because it tells you which operation failed.

Here is an **illustrative** helper to traverse the cause chain without dropping information:

~~~java
static void printCauseChain(Throwable failure) {
    int depth = 0;
    for (Throwable current = failure;
         current != null;
         current = current.getCause()) {
        System.out.println("depth=" + depth
                + " type=" + current.getClass().getName()
                + " message=" + current.getMessage());
        depth++;
    }
}
~~~

The snippet above assumes the cause chain has no cycles; Java normally prevents attaching an exception as its own cause, though unusual `Throwable` structures created by custom code or reflection may require cycle detection. For complete diagnostics, use a standard formatter or error-management tool rather than reconstructing a stack trace as a single message string.

**Suppressed exceptions** are a separate branch, **not** a link in `getCause()`. They commonly appear when an error in the `try` block and an error while closing a resource happen together. For example:

~~~java
try (InputStream input = openStream()) {
    parse(input);               // May throw the primary error.
}                               // close() may also fail.
~~~

If `parse(input)` throws one exception and `close()` throws another, `try-with-resources` keeps the parse error as primary and attaches the close error to `primary.getSuppressed()`. If the body throws no error and only `close()` fails, the close exception becomes the primary error. Therefore, **do not assume a suppressed exception is always present, or that it is always the root cause**.

When diagnosing, inspect all of:

- The `getCause()` chain: why the higher-level error was created.
- The `getSuppressed()` list on each `Throwable` if needed: what additional errors occurred during processing or resource closing.
- Stack traces and messages at each layer: the specific operation, location, and conditions.

## 8. Try-with-Resources Helps Preserve the Primary Error

Before Java 7, cleanup in `finally` could easily throw a new exception and mask the exception from the main work. For objects implementing `AutoCloseable`, `try-with-resources` provides automatic resource closing and suppressed-exception handling:

~~~java
// Illustrative: resource implements AutoCloseable.
try (MyResource resource = acquire()) {
    resource.process();
}
~~~

If `process()` fails and `close()` fails, Java applies the primary/suppressed rule described in Section 7. This prevents losing the business error simply because closing the resource failed.

However, still verify whether your log formatter prints suppressed exceptions. If a system only logs `getMessage()` of the outermost exception, the resource-close error may exist on the object yet **never appear in the logs**.

Avoid turning a close error into the primary error like this:

~~~java
// May cause the error from businessOperation() to be masked.
try {
    businessOperation();
} finally {
    closeThatMayThrow();
}
~~~

Use `try-with-resources` or design cleanup to preserve the primary exception; do not automatically catch and discard all close errors, because those errors can also be important.

## 9. Do Not Mask Thread Interruption Signals or Async Errors

### 9.1. InterruptedException

`InterruptedException` is a cancellation/interruption signal, not an ordinary error that can always be ignored. Many blocking Java methods **clear the interrupt flag when throwing InterruptedException**. When code cannot propagate `InterruptedException` directly due to its contract, it usually needs to restore the flag and wrap the cause:

~~~java
// Illustrated inside a method that does not declare throws InterruptedException.
try {
    Thread.sleep(1_000);
} catch (InterruptedException e) {
    Thread.currentThread().interrupt(); // Restore the interrupt signal.
    throw new IllegalStateException("Worker interrupted while waiting", e);
}
~~~

In a method that can declare `throws InterruptedException`, you can propagate it directly with `throw e` and let the caller decide how to cancel or interrupt. Do not catch it and silently continue an infinite loop: doing so can lose both the stop reason and the interrupt status.

### 9.2. CompletionException and ExecutionException

Asynchronous operations such as `CompletableFuture.join()` can throw `CompletionException`; `Future.get()` can throw `ExecutionException`. They typically hold the underlying task error in `getCause()`. If you only log:

~~~java
// Avoid logging only the wrapper's message.
LOG.warning("Async task failed: " + e.getMessage());
~~~

you may miss the exception from the actual task execution. Log the Throwable or inspect the cause when classifying the error:

~~~java
// Illustrated inside catch (ExecutionException e) with JUL Logger LOG.
LOG.log(Level.SEVERE, "Background operation failed", e);
~~~

Usually there is no need to “unwrap” every wrapper by rethrowing the raw cause if the current layer's contract does not allow it: the wrapper provides information about the async boundary. You can create a new domain exception with context and preserve the wrapper or cause as appropriate for the API.

Avoid treating `CancellationException` as a critical system error in every situation: a canceled task may be expected behavior. The key is distinguishing cancellation, interruption, and genuine failure while keeping the information needed by the handling layer.

## 10. Preserving the Cause Does Not Mean Leaking Data

Stack traces, driver/database messages, and resource path details can sometimes contain sensitive data: internal endpoints, filesystem paths, parameterized queries, usernames, or operational details. **Keeping the cause internally** can still go hand-in-hand with **a restricted external response**.

A suitable pattern:

~~~text
Internal logger:
  operation=loadOrder requestId=req-8 outcome=failed
  Throwable: IllegalStateException ... Caused by: SQLException ...

Public API response:
  status=500
  errorCode=ORDER_LOAD_FAILED
  message=Cannot complete the request
  requestId=req-8
~~~

The lines above are **structural illustrations**, not a mandatory HTTP standard. The end user receives a safe message and a support ID; the internal logging system preserves the cause and stack trace in a location with proper access control.

Safe practices include:

- Write exception messages that are **clear about the operation**, without including passwords, tokens, cookies, or full request payloads.
- Prefer `requestId`, error codes, operation names, and controlled identifiers over unnecessary personal data.
- Use encoders/formatters that guard against newlines and control characters from untrusted input (preventing log forging).
- Log the full Throwable only where it is needed and authorized; restrict retention, access permissions, and forwarding to third-party systems.
- Do not unconditionally strip causes to be “safe”; instead, control **log destinations and exposed data** according to purpose.

## 11. When to Wrap vs. When to Rethrow?

| Scenario | Recommended Approach | Why |
| --- | --- | --- |
| Method simply propagates an error under the same contract | Rethrow or do not catch | Preserves exact type and stack trace, avoids redundant code |
| Crossing from storage layer to business layer | Wrap in an exception with a cause-accepting constructor | Adds useful context while preserving the original error |
| Optional config error with an allowed fallback | Catch the specific type, apply fallback, log/metric as required | Expected handling branch; must be distinguished from infrastructure errors |
| HTTP boundary or job runner | Log Throwable with correlation ID, convert to safe result | Centralizes error reporting, avoids duplicate logs |
| Try-with-resources with a close error | Inspect primary and suppressed | Avoids confusing resource-close errors with task errors |
| Task interrupted | Rethrow or restore interrupt and propagate appropriately | Does not swallow thread coordination signals |
| Future/async failure | Inspect outer exception and cause | Preserves async context and task error |
| Error caught in a retryable component | Retry only allowed error types; keep final error and needed history | Does not mask the cause with a generic “retry failed” message |

When defining a custom exception class, provide a constructor that accepts a cause:

~~~java
// Standalone example of defining a custom exception class.
public class OrderLoadException extends RuntimeException {
    public OrderLoadException(String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

At the catch site:

~~~java
throw new OrderLoadException(
        "Cannot load orderId=" + safeOrderId, e);
~~~

The second throwing snippet requires `safeOrderId` and `e` to be in scope. Having the constructor call `super(message, cause)` is the key to not losing the cause. Avoid creating domain exceptions that only accept `String message` if they are commonly used to wrap lower-level exceptions.

## 12. Investigation Workflow When Logs Appear to Lack a Cause

1. **Identify the records for a single failure:** use `requestId`, `operation`, timestamp, and application version to correlate the right event, rather than searching for the keyword “error” across all threads.
2. **Locate the actual stack trace:** does the record have a `Throwable`/`Caused by` or only `e.getMessage()`? If only a string is present, look for another boundary that logged the full record.
3. **Read the outermost exception and cause chain:** note the error type, message, and stack trace location at each layer. Check whether the service layer wrapped an error and forgot to pass the cause.
4. **Check suppressed exceptions:** if the error involves resources or cleanup, look for `Suppressed: ...` and `getSuppressed()`. Distinguish task errors from resource-closing errors.
5. **Check where errors are turned into fake results:** empty catches, broad `Exception` catches, `null`/`0`/empty-list fallbacks, or handlers returning success even though the real operation failed.
6. **Check async/interruption handling:** was `ExecutionException`, `CompletionException`, or `InterruptedException` filtered out or ignored?
7. **Fix at the right boundary and add a regression test:** verify both correct business behavior and preservation of `getCause()`, suppressed exceptions when applicable, and log records with sufficient context and no leaked secrets.

When testing a cause chain, you do not need to match every stack trace line verbatim because line numbers shift with refactoring. Instead, assert **the cause type, an appropriate message or error code, and the wrapper-to-cause relationship**. For `try-with-resources` tests, assert that the suppressed array contains the expected close exception.

## 13. Common Mistakes and How to Avoid Them

| Mistake | What Is Lost or Wrong | How to Fix |
| --- | --- | --- |
| `catch (Exception ignored) {}` | No trail remains and behavior may falsely appear successful | Catch specific types and handle intentionally |
| `new RuntimeException(e.getMessage())` | Loses the link to the cause object | `new RuntimeException("context", e)` |
| `LOG.severe(e.getMessage())` as the only error log | Log lacks Throwable/stack trace | Use `LOG.log(Level.SEVERE, message, e)` |
| `throw new X("failed")` at every layer | Impossible to tell where the error originated | Wrap only when needed, preserving cause and context |
| Log ERROR then rethrow at every layer | Duplicate logs, skewed alert counts | Choose an appropriate logging boundary |
| `finally` throws an exception or returns | Masks the error from the `try` block | Use `try-with-resources`/cleanup that preserves the primary error |
| Inspect only `getCause()` | Misses suppressed errors during resource closing | Inspect `getSuppressed()` as well |
| Treat the outermost exception as the deepest cause | Ignores `Caused by` and underlying stack traces | Follow the cause chain and read full context |
| Catch `InterruptedException` and continue | Can clear the interrupt signal | Propagate or restore the interrupt |
| Return full stack trace in HTTP response | Exposes unnecessary internal details | Log internally with access control, return a safe response |
| Include Throwable in a formatted message string | Stack trace may be lost in the log | Pass the Throwable object using the proper API overload |

## 14. Self-Check Exercises

1. **Predict the cause:** given `throw new IllegalStateException("Cannot load", new IOException("timeout"))`, state the type and message of the outermost exception and the cause. Compare with `new IllegalStateException("Cannot load")`.
2. **Run the example:** compile `PreserveCauseDemo.java` with JDK 17, and explain why `loggedCause=IOException`, `cause=IOException: connection timed out`, and `suppressedCount=1`. If you change the constructor to `new IllegalStateException("Cannot load recordId=" + recordId)`, what happens when accessing `e.getCause().getClass()`?
3. **Fix the snippet:** replace `catch (IOException e) { LOG.severe(e.getMessage()); throw new RuntimeException("failed"); }` so that the cause is preserved and logging happens only at the designated error-reporting boundary.
4. **Try-with-resources:** make the processing block succeed while `close()` throws an error, and compare the escaping exception with the case where both `process()` and `close()` throw errors.
5. **Asynchronous code:** given a `CompletableFuture` that completes exceptionally with `IOException`, analyze the exception thrown by `join()` and how to read `getCause()`; do not treat the wrapper's text message as the complete information.
6. **API design:** propose an internal log that preserves the Throwable and a safe JSON response for an order-loading failure; explain why the two have different levels of detail.
7. **Regression test:** describe the two most important assertions for a domain exception created by wrapping `SQLException`, and how to verify that a log contains the Throwable rather than only a message.

**Remember:** when an error crosses multiple layers, keep the original exception as the **cause**, preserve secondary errors as **suppressed**, log the **Throwable** using the right overload, and add context at the right place. Do not let empty catches, cause-less wrappers, `finally`, or message-only logs prevent investigators from finding the true root cause.