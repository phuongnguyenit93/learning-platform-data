# Throwing a New Exception While Losing the `cause` in Java

When handling errors, developers often want to convert a technical exception into an exception that is more meaningful to the calling layer. For example, `IOException("configuration file missing")` can be converted into `IllegalStateException("Cannot start application")`. This is a valid **exception translation / exception wrapping** technique. The mistake occurs when creating a new exception **only from the message** without attaching the original exception as the `cause`:

```java
catch (IOException error) {
    throw new IllegalStateException("Startup failed: " + error.getMessage());
}
```

The snippet above is illustrative code inside a method that can throw `IOException`. It creates an `IllegalStateException` with its own stack trace, but `getCause()` returns `null`. Investigators can see that startup failed, but they lose the cause chain, the original `IOException` type, the stack trace where the error originated, and any suppressed exceptions attached to that error.

A usually more appropriate way to wrap it is:

```java
catch (IOException error) {
    throw new IllegalStateException("Startup failed", error);
}
```

The constructor taking `Throwable cause` keeps a **reference to the original exception**. The wrapper's stack trace describes where the error was translated, while `Caused by:` lets you trace back to where the underlying exception occurred. This article explains the consequences of losing `cause`, when to wrap or propagate exceptions, and how to preserve the error chain across APIs, loggers, resources, and asynchronous tasks.

## 1. Distinguishing Message, Cause, and Stack Trace

A `Throwable` object typically carries the following key pieces of information:

| Information | API | Purpose |
| --- | --- | --- |
| Exception type | `error.getClass()` | Indicates whether it is `IOException`, `SQLException`, `IllegalArgumentException`... |
| Message | `error.getMessage()` | Short string describing the error; may be `null` |
| Stack trace | `error.getStackTrace()` | Call-site information where the stack was captured |
| Cause | `error.getCause()` | Underlying exception linked at creation or via cause initialization |
| Suppressed errors | `error.getSuppressed()` | Additional exceptions, such as a `close()` failure in `try-with-resources` |

`getMessage()` is **a string**, not a copy of the entire `Throwable`. Creating `new IllegalStateException(error.getMessage())` does not preserve `getCause()`, `error`'s stack trace, or its suppressed exceptions.

A proper cause chain may look like:

```text
IllegalStateException: Cannot start application
  Caused by: IOException: configuration file missing
      at ConfigRepository.read(...)
      at StartupService.initialize(...)
```

This is an illustrative format, not guaranteed stdout for line numbers or method names in every application. The wrapper carries business context, while the cause preserves the technical trail.

When the cause is omitted:

```text
IllegalStateException: Cannot start application: configuration file missing
  at StartupService.initialize(...)
```

The message still mentions the missing file, but the `IOException` type, exact origin, and deeper causes may have vanished from the new exception object. A higher-level logger **cannot infer back** data that was never passed along.

## 2. Comparison Table of Rethrowing Approaches

Suppose we are inside `catch (IOException error)`:

| Code | Thrown Object | Preserves Original Cause? | Meaning |
| --- | --- | --- | --- |
| `throw error;` | The caught `IOException` itself | No wrapper created; preserves the object and existing cause chain | Propagates the error as-is when the contract allows |
| `throw new IllegalStateException("Cannot load");` | New wrapper | **No** | Changes the error type and loses the cause |
| `throw new IllegalStateException(error.getMessage());` | New wrapper | **No** | Copies the message but loses the original exception info |
| `throw new IllegalStateException("Cannot load", error);` | New wrapper | **Yes** | Adds context and preserves `IOException` |
| `throw new RuntimeException(error);` | New wrapper | **Yes** | Preserves cause; default message is typically derived from `error.toString()` |
| `throw new IllegalStateException("Cannot load", error.getCause());` | New wrapper | Does not preserve **the `error` object** | May accidentally drop a useful error layer |
| `throw new IllegalStateException(error.toString());` | New wrapper | **No** | Copies only the string representation, does not preserve the exception |

The snippets in the table are illustrative statements, not complete programs. Using `throw error;` depends on the `throws` signature and checked exception checking. Java does not allow freely throwing `IOException` out of a method that is not permitted to declare or propagate it.

**Rule:** if you must create a wrapper to cross an abstraction boundary, prefer a constructor that takes both a **contextual message** and **`Throwable cause`**.

## 3. Java 17+ Example: Seeing Lost Data Directly

Create the file **`LostCauseDemo.java`**:

```java
import java.io.IOException;
import java.io.PrintWriter;
import java.io.StringWriter;

public class LostCauseDemo {
    static void readConfiguration() throws IOException {
        throw new IOException("configuration file missing");
    }

    static void startWrong() {
        try {
            readConfiguration();
        } catch (IOException original) {
            throw new IllegalStateException(
                    "startup failed: " + original.getMessage());
        }
    }

    static void startCorrect() {
        try {
            readConfiguration();
        } catch (IOException original) {
            throw new IllegalStateException("startup failed", original);
        }
    }

    static void inspect(String label, Runnable action) {
        try {
            action.run();
        } catch (IllegalStateException error) {
            StringWriter buffer = new StringWriter();
            error.printStackTrace(new PrintWriter(buffer));
            boolean hasOriginalTrace = buffer.toString().contains(
                    "Caused by: java.io.IOException: configuration file missing");
            String causeType = error.getCause() == null
                    ? "null"
                    : error.getCause().getClass().getSimpleName();

            System.out.println(label + ".type="
                    + error.getClass().getSimpleName());
            System.out.println(label + ".cause=" + causeType);
            System.out.println(label + ".originalTrace="
                    + hasOriginalTrace);
        }
    }

    public static void main(String[] args) {
        inspect("wrong", LostCauseDemo::startWrong);
        inspect("correct", LostCauseDemo::startCorrect);
    }
}
```

Compile and run with Java 17 or later:

```bash
javac --release 17 LostCauseDemo.java
java LostCauseDemo
```

Output:

```text
wrong.type=IllegalStateException
wrong.cause=null
wrong.originalTrace=false
correct.type=IllegalStateException
correct.cause=IOException
correct.originalTrace=true
```

**Step-by-step explanation:**

1. `readConfiguration()` creates and throws `IOException("configuration file missing")`.
2. `startWrong()` catches the error but only passes the message text into a new string. Its `IllegalStateException` does not retain the `IOException` object, so `getCause() == null`.
3. `startCorrect()` creates `IllegalStateException` with the second argument being the **original exception**. Thus `getCause()` is `IOException`.
4. `printStackTrace(...)` on the proper wrapper additionally outputs the `Caused by: ...` block, revealing the underlying error. The program checks using a stable substring instead of printing the full stack, whose line numbers vary by environment.

The example only demonstrates **losing the cause due to how the wrapper is constructed**; it does not benchmark performance, does not prove that every logger automatically prints stack traces, and does not require applications to use `IllegalStateException` for all error types. In a real project, choose the exception type according to the API contract.

## 4. Why Losing the Cause Is a Serious Diagnostic Mistake

### 4.1. Losing the True Error Origin

A wrapper is instantiated inside `catch`, so the new stack trace typically starts at `new IllegalStateException(...)`. If `cause` is lost, the stack portion associated with the initial `IOException` is no longer referenced to be logged with the incident.

Looking only at the wrapper can mislead operators into fixing the wrong service layer, while the actual fault lies in file reading, SQL execution, or an HTTP call.

### 4.2. Losing the Exception Type for Classification and Recovery

`IOException`, `SQLException`, `TimeoutException`, or an SDK-provided exception may require different handling. If only the message remains in the wrapper, higher-level logic cannot inspect `getCause()` to identify the exact type—for instance, distinguishing a transient error that can be retried from an invalid-data error that should not be retried.

However, **do not rely solely on the exception class name to decide retries**. You must check the cause, state, idempotency, and system policy. The cause is supporting information for classification, not an automatic business decision.

### 4.3. Losing Underlying Causes and Suppressed Errors

An `IOException` can have its own cause, such as a filesystem error. It can also carry `getSuppressed()` from `try-with-resources`. When the entire `IOException` object is kept as the cause, those relationships remain traceable; when only the message is copied, they are dropped from the new wrapper's exception chain.

### 4.4. Depriving Logs and Monitoring Systems of Evidence

Loggers such as JUL and SLF4J/Logback typically have mechanisms to accept a `Throwable` object and format the stack, cause, and suppressed exceptions. However, they can only display data that the current exception still holds. If the cause was stripped by an intermediate layer, logs in the controller or global error handler cannot recover it.

### 4.5. Making Testing and Error Contract Maintenance Harder

Tests can assert both the wrapper type **and the original cause**. If tests only check the message, a refactor could accidentally drop the cause chain while tests still pass. The contract "a data-layer error is translated into a business-layer error while preserving the cause" should be a verifiable condition.

## 5. Propagate As-Is or Wrap in a New Exception?

You should not always create a wrapper. There are two main strategies:

**Propagate:** when the method can declare `throws IOException` and the caller is already responsible for handling it.

```java
void load() throws java.io.IOException {
    repository.read();
}
```

The illustrative snippet requires `repository` to be declared with an appropriate `read()` method. No new exception is created here. If this layer adds no new context and does not need to change the exception type, catching and rethrowing only makes the code more verbose.

**Translate the exception:** when you want to describe the failure in terms of the current abstraction layer, or because the method contract does not allow checked exceptions to escape.

```java
void initialize() {
    try {
        repository.read();
    } catch (java.io.IOException cause) {
        throw new IllegalStateException(
                "Cannot initialize configuration", cause);
    }
}
```

This is an illustrative snippet requiring `repository`. The wrapper provides an error type and message suited to the initialization layer, while the `IOException` cause is preserved.

Use a wrapper when it **adds meaning**, rather than wrapping in `RuntimeException("failed", previous)` at every layer you pass through. Unnecessary wrapping layers increase stack-creation overhead and make traces harder to read.

Do not rely on technical error messages to build messages shown to end users. HTTP/UI messages should be safe and stable, and may differ from messages in logs or exceptions.

## 6. Constructors That Preserve the Cause

In Java, exception classes typically provide several constructors, for example `IllegalStateException`:

```java
new IllegalStateException("operation failed", cause);
new IllegalStateException(cause);
```

These are illustrative expressions with a `cause` variable of type `Throwable`. The two-argument constructor is usually clearest because it provides both business context and preserves the cause.

A custom exception class should consider providing a constructor that accepts a cause:

```java
public final class ConfigurationLoadException extends RuntimeException {
    public ConfigurationLoadException(String message, Throwable cause) {
        super(message, cause);
    }
}
```

This is a **complete class declaration at the snippet level**, though when placed in a standalone Java file the public class name must match the file name (`ConfigurationLoadException.java`). You can omit `public` when embedding it inside another class. To use it:

```java
try {
    configRepository.read();
} catch (java.io.IOException cause) {
    throw new ConfigurationLoadException("Cannot load application config", cause);
}
```

The usage snippet requires the corresponding `configRepository` object and `ConfigurationLoadException` class.

If you use a message-only constructor such as `new ConfigurationLoadException(cause.getMessage())`, the class must have that constructor to compile; more importantly, that approach still **does not automatically attach the cause**.

Some libraries have their own exception hierarchies (error codes, HTTP status, retryability). Use the constructor or builder with the cause field according to the API, rather than assuming that setting a `message` field is equivalent.

## 7. `initCause()` Is Neither the Preferred Solution Nor a Setter

`Throwable.initCause(Throwable)` can attach a cause after creating a throwable whose cause **has not yet been initialized**. This is useful for legacy classes lacking a constructor that accepts `Throwable`, but it has important limitations:

- The cause can only be initialized **once**. Calling `initCause` again throws `IllegalStateException`.
- `initCause(this)` is invalid: a throwable cannot be its own direct cause.
- If the constructor already initialized the cause—even to `null`—a subsequent `initCause(...)` call may be rejected.
- Do not call `initCause` on an exception shared across requests or multiple threads to try to alter its cause.

Example of a **standalone method-level snippet**:

```java
Exception error = new Exception("load failed");
error.initCause(new java.io.IOException("file missing"));

System.out.println(error.getCause().getClass().getSimpleName());
```

Output:

```text
IOException
```

Prefer a constructor that takes `cause` at creation time if the class supports it. That makes the error relationship explicit and avoids a window where the object exists without a cause.

## 8. Cause Is Not Equivalent to Suppressed Exception

There are two distinct kinds of exception relationships:

- **Cause:** error A led to creating and reporting error B. For example, an `IOException` while reading data is the cause of `IllegalStateException("startup failed")`.
- **Suppressed:** a secondary error occurred during handling/closing a resource while a primary error was already active. For example, `close()` failing after reading a file had already thrown an error.

Do not replace a causal relationship with `addSuppressed(error)` just to "store it somewhere." `getCause()` and `getSuppressed()` have different semantics; processing systems and log readers interpret them differently.

### Java 17+ Example: Cause Preserves Suppressed Exceptions

Create the file **`CauseAndSuppressedDemo.java`**:

```java
import java.io.IOException;
import java.io.PrintWriter;
import java.io.StringWriter;

public class CauseAndSuppressedDemo {
    static final class BrokenResource implements AutoCloseable {
        @Override
        public void close() throws IOException {
            throw new IOException("close failed");
        }
    }

    static void readData() throws IOException {
        try (BrokenResource resource = new BrokenResource()) {
            throw new IOException("read failed");
        }
    }

    static void process() {
        try {
            readData();
        } catch (IOException original) {
            throw new IllegalStateException("import failed", original);
        }
    }

    public static void main(String[] args) {
        try {
            process();
        } catch (IllegalStateException wrapper) {
            Throwable cause = wrapper.getCause();

            System.out.println("wrapper=" + wrapper.getMessage());
            System.out.println("cause=" + cause.getMessage());
            System.out.println("suppressedCount="
                    + cause.getSuppressed().length);
            System.out.println("suppressedMessage="
                    + cause.getSuppressed()[0].getMessage());

            StringWriter buffer = new StringWriter();
            wrapper.printStackTrace(new PrintWriter(buffer));
            String trace = buffer.toString();

            System.out.println("causeInTrace="
                    + trace.contains("Caused by: java.io.IOException: read failed"));
            System.out.println("suppressedInTrace="
                    + trace.contains(
                            "Suppressed: java.io.IOException: close failed"));
        }
    }
}
```

Compile and run:

```bash
javac --release 17 CauseAndSuppressedDemo.java
java CauseAndSuppressedDemo
```

Output:

```text
wrapper=import failed
cause=read failed
suppressedCount=1
suppressedMessage=close failed
causeInTrace=true
suppressedInTrace=true
```

Because `readData()` threw `IOException("read failed")` while the `try` body was executing, and `close()` threw `IOException("close failed")`, Java kept the read error as the primary exception and attached the close error as suppressed. `process()` created a wrapper **while keeping the read exception itself as the cause**, so both failures remain reachable from the wrapper.

If you replace the line in `process()` with `throw new IllegalStateException(original.getMessage());`, the wrapper loses access to both `IOException("read failed")` and its `getSuppressed()`. This is why the "copy message only" mistake is especially harmful when an error spans multiple layers.

## 9. Walking the Cause Chain Without Losing Context

When investigating an error, start from the outermost exception and follow `getCause()`:

```java
Throwable cursor = failure;
while (cursor != null) {
    System.out.println(cursor.getClass().getName()
            + ": " + cursor.getMessage());
    cursor = cursor.getCause();
}
```

This is an illustrative snippet inside a method that has `Throwable failure`. For a normal, valid cause chain, this traversal lets you inspect each layer. However, if you write a utility for error data from arbitrary sources, guard against abnormal chains (for example, by tracking visited objects and limiting depth) rather than assuming every cause link has a reasonable depth.

**The deepest cause is not always the only important information.** An upper-layer exception such as `PaymentValidationException` may identify the failed business rule, while the deepest cause is simply `SQLException`. When choosing a response or retry policy, preserve information from each layer; when logging, prefer passing the entire `Throwable` so the backend can render the full chain.

If code uses an "unwrap" helper to strip `CompletionException` or `ExecutionException`, distinguish **technical wrappers** from **exceptions with business semantics**. Stripping all wrappers unconditionally can lose information about which operation failed.

## 10. Impact in `CompletableFuture` and `ExecutorService`

In asynchronous tasks, errors may be further wrapped by the result-observing API:

- `Future.get()` and `CompletableFuture.get()` typically throw `ExecutionException` when a task fails; `getCause()` links to the exception from the task.
- `CompletableFuture.join()` typically throws `CompletionException` when a future completes exceptionally; the cause holds the pipeline's error.
- In `CompletableFuture.supplyAsync`, if the supplier wants to convert a checked `IOException` into an unchecked exception to signal failure, it can throw `new CompletionException("loading failed", original)`. This **preserves the cause**.
- If the supplier instead throws `new RuntimeException(original.getMessage())`, the cause is lost **right inside the worker**. No matter how many layers `join()`/`get()` wraps around it, the discarded `IOException` cannot be recovered.

Illustrative code inside a `CompletableFuture` lambda:

```java
CompletableFuture<String> loaded = CompletableFuture.supplyAsync(() -> {
    try {
        return readText();
    } catch (java.io.IOException original) {
        throw new java.util.concurrent.CompletionException(
                "Cannot read text asynchronously", original);
    }
});
```

This snippet **cannot run standalone**: it requires importing `CompletableFuture` and declaring `readText()` with return type `String` that can throw `IOException`.

When catching `CompletionException` at the `join()` call boundary:

```java
try {
    loaded.join();
} catch (java.util.concurrent.CompletionException error) {
    Throwable underlying = error.getCause();
    // Classify the error if needed, while preserving the throwable chain when logging.
    throw error;
}
```

The illustrative snippet requires `loaded` to be declared as above. Depending on the pipeline, `getCause()` may be a business exception or another wrapper. Inspecting each layer is more reliable than guessing the cause depth.

Cancellation (`CancellationException`) or thread interruption (`InterruptedException`) have specific semantics; do not wrap all cancellation/interruption errors into a generic `RuntimeException` just to avoid checked exceptions. If you catch `InterruptedException` without being able to propagate it and intentionally terminate the current work, consider restoring the interrupt status with `Thread.currentThread().interrupt()` and exiting the task according to contract.

## 11. Logging: Pass the Whole `Throwable`, Not Just the Message

Even when a wrapper properly preserves the cause, you can still lose information at the **logging layer** if you only log strings.

With SLF4J (illustrative snippet; requires `logger`, `orderId`, `error`):

```java
logger.error("Order {} failed: {}", orderId, error.getMessage());
```

The approach above does not pass the exception object to the logger. Replace it with:

```java
logger.error("Order {} failed", orderId, error);
```

In standard SLF4J usage, the trailing `Throwable` argument is recognized as the event's exception, allowing the backend to print the stack trace, cause, and suppressed exceptions. If no formatting arguments are needed, you can use `logger.error("Order failed", error)`.

With `java.util.logging` (JUL):

```java
logger.log(java.util.logging.Level.SEVERE, "Order failed", error);
```

This is a call on a `java.util.logging.Logger logger`; the overload taking `Throwable` stores the exception reference in the `LogRecord`. Conversely, `logger.severe(error.getMessage())` only logs a string and attaches no exception.

Do not confuse **preserving the cause in the object** with **the backend being guaranteed to display the entire cause**. Actual formatting also depends on the formatter, log level, configuration, sampling, and destination. Verify the runtime environment's configuration.

For an error crossing multiple layers, avoid logging the full stack in the repository, logging again in the service, and logging once more in the controller without good reason. Usually it is best to log once at the handling boundary that has full context, while intermediate layers simply propagate or add causes properly.

## 12. How to Choose the Message When Wrapping an Error

A good wrapper message should answer **which operation could not be performed**, rather than merely repeating the technical message:

```java
throw new IllegalStateException(
        "Cannot initialize tax rules for region " + safeRegionCode,
        original);
```

This is an illustrative snippet with variables `safeRegionCode` and `original`. The wrapper adds context ("initializing tax rules for which region") while the cause preserves the storage/network-layer error. Avoid constructing messages with passwords, tokens, sensitive identifiers, or entire user requests.

You do not necessarily need to append `original.getMessage()` to the wrapper message. If the logging system prints the cause chain, the original error's message is already present in the `Caused by:` section. Repeating the message can cause verbosity, make searching harder, and increase data-leak risk.

**Messages for end users** should be constructed separately according to the error contract: for example, a non-sensitive error code and actionable guidance. Do not return stack traces, technical causes, or internal exception structures directly from public APIs.

## 13. Notable Exceptions and Counterexamples

### 13.1. Constructors That Do Not Support `cause`

Some legacy or library exception classes may only support a message. If you need to preserve the cause, check whether another constructor, builder, or `initCause` is available. Do not arbitrarily use reflection to mutate the cause field; if needed, create a new wrapper with a constructor taking `Throwable` in accordance with the application's contract.

### 13.2. Do Not Use `initCause` on Finalized or Shared Exceptions

A `Throwable` may already have a cause, or may be shared across multiple threads. Attempting to assign a cause after it has been published can fail or mix contexts. Creating a new wrapper for the **current incident** is usually easier to reason about.

### 13.3. Catching Every `Exception` and Turning It Into the Same Error

```java
try {
    performOperation();
} catch (Exception error) {
    throw new IllegalStateException("operation failed", error);
}
```

This snippet preserves the cause, but **does not automatically guarantee good design**: catching too broadly can mask error classification, alter the exception contract, or swallow interrupt signals that require special handling. Catch only at boundaries where you genuinely have a translation policy; avoid catching `Throwable` (which includes `Error`) indiscriminately.

### 13.4. Converting Checked Exceptions to Unchecked Does Not Mean Losing the Cause

If an API does not want to expose `IOException` in its signature, creating an `UncheckedIOException` is a dedicated option in many I/O scenarios:

```java
catch (java.io.IOException original) {
    throw new java.io.UncheckedIOException("Cannot load resource", original);
}
```

This is an illustrative snippet placed inside a `catch`; the constructor taking `IOException` preserves the original cause type. Choose an exception type consistent with your library's abstraction layer.

### 13.5. Using `throw new Exception(error.toString())` Does Not Preserve the Stack

`Throwable.toString()` usually contains the class name and message, but it is still just a string. It does not substitute for a reference to the original object and does not allow the wrapper's `getCause()` to trace back to the initial error.

### 13.6. If You Want to Add the Caller Layer's Stack, a Wrapper Helps—But Must Not Replace the Cause

When creating a wrapper, Java can record the stack at **the exception translation site**, which is very helpful for knowing which service layer the request passed through. Keeping `original` as the cause gives investigators **both** the translation site and the origination site. Do not drop the cause to "keep the stack cleaner"; you can format or filter logs in observability tools instead of severing error relationships at the source.

## 14. Code Review Checklist and Fix Workflow

When reviewing a `catch` block, check in order:

1. **Is catching here really necessary?** If this layer neither handles the error nor adds semantics, and the contract allows, consider propagating the exception as-is.
2. **Do we need to change the error type?** If so, choose a wrapper that accurately reflects the business/technical boundary.
3. **Does the constructor accept `Throwable cause`?** Avoid passing only `error.getMessage()` or `error.toString()`.
4. **Are you preserving the exact caught exception?** Do not accidentally pass `error.getCause()` and drop the `error` layer that carries useful context.
5. **Are there suppressed exceptions or deeper causes?** A proper wrapper must preserve access to them.
6. **Is any recovery or special handling required?** For example, thread interruption, task cancellation, retryable errors, or non-retryable errors.
7. **Does the logger receive the entire throwable?** If you only log strings, data is still lost at the logging boundary.
8. **Is the added message safe?** Do not embed secrets or user data that must not be logged.
9. **Do tests assert the cause?** Verify the outer exception type, cause type, and required message/structure.
10. **Is there duplicate logging or pointless wrapping?** Avoid building excessively deep error chains that provide no new information.

A fix pattern in code review:

```diff
 try {
     repository.save(entity);
 } catch (IOException error) {
-    throw new IllegalStateException("Save failed: " + error.getMessage());
+    throw new IllegalStateException("Save failed", error);
 }
```

The diff snippet is illustrative; it is not an executable command. A small difference in the constructor makes a big difference in diagnosability.

## 15. Self-Check Questions

**Question 1.** What does `throw new RuntimeException(error.getMessage());` preserve?  
**Answer:** A new message. It does not automatically set `getCause()` to `error`, does not preserve `error`'s stack trace, and does not attach suppressed exceptions from `error`.

**Question 2.** How many exception objects are involved in `throw new IllegalStateException("Cannot load", error);`?  
**Answer:** At least the new wrapper and the existing `error` object. `wrapper.getCause()` references `error`; they are not a single object.

**Question 3.** If a method is allowed to declare `throws IOException` and needs no additional context, is it mandatory to create a wrapper?  
**Answer:** No. You can propagate the error per contract or let the exception bubble up naturally.

**Question 4.** Can `Throwable.initCause` be used like a setter to replace the cause every time an exception is thrown?  
**Answer:** No. By API contract, the cause can only be initialized once.

**Question 5.** Why is logging only `exception.getMessage()` insufficient, even when the wrapper already has the cause attached?  
**Answer:** The logger only receives a string, so it has no throwable object to render the stack trace, `Caused by:`, and suppressed exceptions.

**Question 6.** An `IOException` has a suppressed `close failed`. When creating `new IllegalStateException("load failed", original)`, is the resource-closing error still accessible?  
**Answer:** Yes, via `wrapper.getCause().getSuppressed()`; the `CauseAndSuppressedDemo` example demonstrates this.

**Question 7.** Should you always extract the deepest cause and discard all wrappers when returning an error?  
**Answer:** No. Wrappers may contain critical business context; you need to distinguish technical wrappers from meaningful error layers.

**Question 8.** When converting `IOException` to `UncheckedIOException`, how do you avoid losing the cause?  
**Answer:** Use the constructor that accepts the cause argument, e.g., `new UncheckedIOException("Cannot read", original)`.

**Question 9.** In what situations can wrapping an error with a cause still be wrong?  
**Answer:** Catching too broadly, choosing an inappropriate wrapper type, masking `InterruptedException`, duplicate logging, or putting sensitive data into the message are all design mistakes to watch out for.

## 16. References

- [Java 17 — `Throwable`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html): `getCause()`, `initCause()`, stack trace, and suppressed exceptions.
- [Java 17 — `IllegalStateException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/IllegalStateException.html): constructors supporting message and cause.
- [Java 17 — `UncheckedIOException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/UncheckedIOException.html): converting `IOException` into an unchecked exception while preserving the cause.
- [Java 17 — `CompletionException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletionException.html) and [Java 17 — `ExecutionException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutionException.html): wrappers when observing asynchronous failures.

**Takeaway:** creating a new exception with only `error.getMessage()` or `error.toString()` **does not preserve the cause**. If you need to wrap an error, pass the caught `Throwable` object itself to a constructor that accepts `cause`; if wrapping is unnecessary, propagate the exception per contract. The wrapper's stack trace and the cause chain complement each other so readers can find both where the error was translated and where it actually originated.