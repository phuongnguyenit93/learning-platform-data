# Preserve root cause: keeping the root cause when logging exceptions in Java

## 1. What does “Preserve root cause” mean?

When an operation in a Java application fails, an exception can be **wrapped across multiple layers**: database driver, repository, service, controller, message consumer, or asynchronous task. Each layer can add useful context, but if it throws a new exception **without passing the original exception as the cause**, the system can lose the most important clue for finding the root cause.

**Preserve root cause** is the principle of **retaining the exception that caused the failure** in the `Throwable.getCause()` chain, while logging with the **actual `Throwable` object** so investigators have the stack trace and `Caused by` relationship, rather than just a single error description string.

Example scenario:

```text
HTTP POST /orders
        |
        v
OrderController
        |
        v
OrderService.createOrder
        |
        v
OrderRepository.save
        |
        v
Database driver: connection refused
        |
        +-- SQLException / IOException
                |
                +-- RepositoryException(cause = original)
                        |
                        +-- OrderProcessingException(cause = repository exception)
                                |
                                +-- Controller / exception handler logs Throwable
```

If the controller only sees `OrderProcessingException: Cannot create order` without `Caused by`, operators cannot easily tell whether the failure was caused by a database connection issue, data validation, a timeout, a data constraint, or a code bug.

The goal is not to extract a `getMessage()` string from the very bottom and discard every wrapper. An outer-layer exception can explain **which business operation failed**, while the deepest exception provides the **technical cause**. **Preserving the entire cause chain** gives readers both perspectives.

## 2. Understanding `Throwable`: message, stack trace, cause, and suppressed

Java uses `Throwable` as the root class for `Exception` and `Error`. Key components:

| Component | API | Meaning |
| --- | --- | --- |
| Exception type | `getClass()` | Which class categorizes the error |
| Message | `getMessage()` | Textual detail; may be `null` or contain sensitive data |
| Stack trace | `getStackTrace()` / `printStackTrace()` | Frames attached to where the throwable was created or had its stack updated |
| Cause | `getCause()` | The throwable that caused the current exception, if any |
| Suppressed exceptions | `getSuppressed()` | Additional errors retained, typically in `try-with-resources` |
| Original throwable | The `Throwable` object itself | The complete input for loggers and diagnostic tools |

Example:

```java
// Illustrative integration snippet.
try {
    callStorage();
} catch (java.io.IOException original) {
    throw new IllegalStateException("Cannot complete checkout", original);
}
```

`IllegalStateException` creates a **new stack trace at the wrapping site** while having `getCause() == original`, so the old stack trace is still preserved in the cause chain. This is **contextual wrapping**: adding information without erasing the original evidence.

A throwable may **have no cause**. Do not force every error to have an underlying cause. Moreover, the *deepest cause* is not necessarily the only thing worth observing: in a distributed system, the technical root error might be `SocketTimeoutException`, but the `PaymentGatewayException` wrapper is what indicates which gateway and which operation were involved.

### 2.1. “Root cause” is not synonymous with “message of the last cause”

The following two outputs do not have the same diagnostic value:

```text
Cannot create order
Caused by: Connection timed out
```

and:

```text
OrderProcessingException: Cannot create order
    at OrderService.createOrder(...)
Caused by: RepositoryException: Unable to persist order
    at OrderRepository.save(...)
Caused by: SocketTimeoutException: Connection timed out
    at ... driver/network ...
```

The first example only shows **the result of truncating to text**; the second example is a structure reminiscent of a layered stack trace. The `...` markers are only for illustration, **not actual stdout of a program**.

To preserve evidence in logging, pass the **`Throwable`**, rather than building a summary string and discarding the exception.

## 3. Wrong and right ways to wrap exceptions

### 3.1. Wrong: creating a new exception with only a message

```java
// Wrong: loses the cause reference, and the original stack trace is not in the chain.
try {
    repository.save(order);
} catch (java.sql.SQLException original) {
    throw new RuntimeException("Save failed: " + original.getMessage());
}
```

`new RuntimeException(String)` does not accept a cause. Calling `RuntimeException.getCause()` on the new wrapper returns `null` unless set through another mechanism. The original stack trace information is detached from the throwable propagated upward.

The message may also contain query parameters, internal addresses, or sensitive data that the application should not duplicate into the outer error's message.

### 3.2. Right: passing the original cause to the constructor

```java
// Integration snippet, assuming repository and order are variables in the application.
try {
    repository.save(order);
} catch (java.sql.SQLException original) {
    throw new RuntimeException("Order persistence failed", original);
}
```

The wrapper preserves the business context and keeps `original` as the cause. From an upper layer, you can read:

```java
Throwable immediateCause = failure.getCause();
```

This is an **integration snippet**; `failure` must be a declared `Throwable`. You can traverse `getCause()` multiple times if deeper analysis is needed.

### 3.3. Right: declaring a custom exception with a constructor accepting a cause

```java
public final class OrderProcessingException extends RuntimeException {
    public OrderProcessingException(String message, Throwable cause) {
        super(message, cause);
    }
}
```

This is a **standalone compilable class** if saved in `OrderProcessingException.java`. In the application, throw:

```java
// Integration snippet; original is the Throwable that caused the failure.
throw new OrderProcessingException("Cannot create order", original);
```

If a custom exception only has a `(String)` constructor, developers often accidentally lose the cause when wrapping. For business exception classes, provide constructors that match actual handling needs, and avoid adding purposeless constructors.

### 3.4. `throw original` or `throw new Wrapper(..., original)`?

- **Rethrow** (`throw original;`) preserves the exact throwable object, its stack trace, and its cause. Suitable when the current layer does not need to change the exception type and the method signature allows it.
- **Wrap with cause** adds a type and context at the boundary between persistence, service, and transport layers; the wrapper's stack trace starts at the wrapping site, while the original stack trace is preserved in the cause.
- **Wrap without cause** is usually a diagnostic bug.
- **Replace intentionally** is only reasonable when there is an explicit policy requirement (for example, preventing internal exceptions from crossing a trust boundary). Even when returning a sanitized error response, the system can retain the cause in protected internal logs.

Do not switch to `throw new RuntimeException(original.getMessage())` just to avoid a checked exception; doing so loses the cause chain and can duplicate sensitive data.

## 4. Java 17: standalone example proving the cause is preserved through logging

The program below simulates:

1. The storage layer throws an `IOException`.
2. The business layer wraps it into `OrderProcessingException` **with a cause**.
3. The boundary catches the wrapper and determines the deepest throwable type for classification.
4. JUL `Logger.log(Level, String, Throwable)` receives **the wrapper itself**, not just an error string.
5. The demo handler prints stable metadata for deterministic stdout. In a real application, a formatter can print the full stack trace.

Save the file **`RootCauseLoggingDemo.java`**:

```java
import java.io.IOException;
import java.util.Collections;
import java.util.IdentityHashMap;
import java.util.Set;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class RootCauseLoggingDemo {
    private static final class OrderProcessingException
            extends RuntimeException {
        OrderProcessingException(String message, Throwable cause) {
            super(message, cause);
        }
    }

    private static void saveOrder() throws IOException {
        throw new IOException("storage unavailable");
    }

    private static void createOrder() {
        try {
            saveOrder();
        } catch (IOException original) {
            throw new OrderProcessingException(
                    "cannot create order", original);
        }
    }

    private static Throwable deepestCause(Throwable failure) {
        Set<Throwable> seen = Collections.newSetFromMap(
                new IdentityHashMap<Throwable, Boolean>());
        Throwable current = failure;
        seen.add(current);

        while (current.getCause() != null
                && seen.add(current.getCause())) {
            current = current.getCause();
        }
        return current;
    }

    public static void main(String[] args) {
        Logger logger = Logger.getLogger("demo.root-cause");
        logger.setUseParentHandlers(false);
        logger.setLevel(Level.ALL);

        Handler output = new Handler() {
            {
                setLevel(Level.ALL);
            }

            @Override
            public void publish(LogRecord record) {
                if (record != null && isLoggable(record)) {
                    System.out.println(record.getLevel().getName()
                            + " " + record.getMessage());
                    Throwable thrown = record.getThrown();
                    if (thrown != null) {
                        System.out.println("thrownType="
                                + thrown.getClass().getSimpleName());
                        Throwable cause = thrown.getCause();
                        System.out.println("causeType="
                                + (cause == null
                                    ? "none"
                                    : cause.getClass().getSimpleName()));
                    }
                }
            }

            @Override
            public void flush() {
                System.out.flush();
            }

            @Override
            public void close() {
                flush(); // Do not close the JVM's System.out.
            }
        };

        logger.addHandler(output);
        try {
            try {
                createOrder();
            } catch (OrderProcessingException failure) {
                Throwable root = deepestCause(failure);
                logger.log(
                        Level.SEVERE,
                        "event=order_failed rootType="
                                + root.getClass().getSimpleName(),
                        failure); // Important: pass the original Throwable.
            }
        } finally {
            logger.removeHandler(output);
            output.close();
        }
    }
}
```

Compile/run with **JDK 17 or later**:

```bash
javac RootCauseLoggingDemo.java
java RootCauseLoggingDemo
```

Exact output on **`stdout`**:

```text
SEVERE event=order_failed rootType=IOException
thrownType=OrderProcessingException
causeType=IOException
```

Because the demo handler prints selected fields manually, there is **no long stack trace or line number** in the output above. This does not mean the exception lost its stack trace: `record.getThrown()` is still `OrderProcessingException`, and `getCause()` is still `IOException`. A real JUL formatter such as `SimpleFormatter` can use the `LogRecord.thrown` field to print the stack trace and `Caused by` lines.

### 4.1. Key points to note

- `saveOrder()` simulates the failure closest to the source. `IOException` still exists even though the `createOrder()` layer throws a different exception.
- The `super(message, cause)` constructor preserves the `IOException` instance; there is no need to call `printStackTrace()` in the service layer.
- `deepestCause` uses a set based on **object identity** to avoid infinite loops in case of an unusual cause cycle. For a normal chain, the result is the last throwable before `null`.
- `IdentityHashMap` in the example makes the traversal helper safer; **it does not automatically determine the true business root cause**.
- `logger.log(Level.SEVERE, message, failure)` passes a `Throwable` to JUL so the backend/formatter can preserve the entire cause chain.
- `logger.setUseParentHandlers(false)` avoids extra printing from the root handler; the demo handler writes only to `stdout` without timestamp dependencies.
- `finally` removes the handler to avoid side effects when the demo runs inside another JVM.
- The example intentionally prints only the **type** of the cause rather than `IOException.getMessage()` to reduce the chance of leaking internal environment details into aggregated logs.

### 4.2. Why you do not always need to find the deepest cause manually

`logger.log(..., failure)` already preserves the wrapper and chain. In a production application, you may only need:

```java
// Integration snippet; logger is java.util.logging.Logger.
logger.log(Level.SEVERE, "Order processing failed", failure);
```

A helper that walks to the bottom of the cause chain is only useful when you need to **classify errors**, such as recording `rootCauseType`, aggregating statistics by exception class, or deciding on retries. If you only want the full stack trace, **passing the throwable itself** is usually better than replacing it with the deepest cause: the logger also needs the context from the outer wrapping layers.

## 5. Logging patterns that lose cause information

| Pattern | Consequence | Recommendation |
| --- | --- | --- |
| `log.error("Failed: " + e.getMessage())` | Logs only the message string, usually without stack trace or cause chain | `log.error("Failed", e)` |
| `log.error("Failed: {}", e.getMessage())` | The placeholder does not recover the throwable | Pass `e` as a Throwable |
| `log.error(e.toString())` | Only type name + message; does not preserve the chain as an exception | Log `e` using an overload that accepts Throwable |
| `e.printStackTrace()` | Prints directly to stderr, bypassing logger configuration/formatting/routing | Use a logger with Throwable |
| `throw new RuntimeException(e.getMessage())` | The new wrapper's cause is null | `throw new RuntimeException("...", e)` |
| `throw new RuntimeException("Unexpected")` | Replacing the error can lose evidence | Attach the cause unless policy requires otherwise |
| Only `log.error("{}", e.getCause())` | May only print `toString()` of the immediate cause and lose context | Log the full original exception |
| `log.error("Failed", e)` at every layer | Does not lose the cause, but creates duplicate logs and increases noise | Log at the responsible boundary |

For **SLF4J**, the simple, clear way:

```java
// Integration snippet: log is org.slf4j.Logger.
log.error("Unable to process order", exception);
```

This is the overload that accepts a `Throwable`, unlike `log.error("Unable to process order: " + exception.getMessage())`.

With business parameters:

```java
// Integration snippet: orderId is a validated identifier, exception is Throwable.
log.error("Unable to process orderId={}", orderId, exception);
```

In common SLF4J versions, a **`Throwable` in the last argument position** is recognized as the event's cause, separate from message placeholders. If a provider/version or overload causes ambiguity, you can use the explicit form `log.error("Unable to process orderId=" + safeOrderId, exception)` at the boundary, while still ensuring `safeOrderId` is validated and does not introduce sensitive data.

For JUL:

```java
// Integration snippet: logger is java.util.logging.Logger.
logger.log(Level.SEVERE, "Order processing failed", exception);
```

JUL does not use `log.error(...)` and instead uses `Level.SEVERE`; do not mix `java.util.logging.Level` with level enums from Log4j 2 or other framework APIs.

## 6. Do not equate cause with suppressed exceptions

Another important case is **suppressed exceptions**, which commonly occur when an operation has already failed and closing a resource in `try-with-resources` also fails.

Example:

```text
Primary failure: data processing failed
       |
       +-- Suppressed: closing file/socket/connection also failed
```

A suppressed exception **is not necessarily the cause of the primary error**. Java stores them via `Throwable.getSuppressed()`; standard `printStackTrace()` output typically renders a `Suppressed:` section alongside `Caused by:`.

If a developer only inspects `getCause()` or prints a single deepest cause, cleanup failure information can be missed. For retry mechanisms and data-loss investigations, resource-closing errors are sometimes highly significant.

### 6.1. Standalone Java 17 example of suppressed exceptions

Save the file **`SuppressedCauseDemo.java`**:

```java
public class SuppressedCauseDemo {
    static final class FragileResource implements AutoCloseable {
        @Override
        public void close() throws Exception {
            throw new Exception("close failed");
        }
    }

    public static void main(String[] args) {
        try (FragileResource ignored = new FragileResource()) {
            throw new IllegalStateException("work failed");
        } catch (Exception failure) {
            System.out.println("primaryType="
                    + failure.getClass().getSimpleName());
            System.out.println("causePresent="
                    + (failure.getCause() != null));
            System.out.println("suppressedCount="
                    + failure.getSuppressed().length);
            System.out.println("suppressedType="
                    + failure.getSuppressed()[0]
                            .getClass().getSimpleName());
        }
    }
}
```

Compile and run:

```bash
javac SuppressedCauseDemo.java
java SuppressedCauseDemo
```

**`stdout`** output:

```text
primaryType=IllegalStateException
causePresent=false
suppressedCount=1
suppressedType=Exception
```

Explanation:

- The body throws `IllegalStateException`: that is the **primary exception**.
- When exiting `try-with-resources`, `close()` throws `Exception`. Java adds the close error to the **suppressed** array of the primary throwable.
- The primary exception has `getCause() == null`, yet it still has a suppressed exception. Therefore, “no cause” **does not mean there are no related errors**.
- The code intentionally prints type/count instead of a stack trace for deterministic output; a real logger should keep the primary throwable intact so the formatter can display suppressed exceptions.

**Do not mechanically replace suppressed exceptions with cause**: they represent different relationships. If writing manual resource-management code where a new cleanup error would mask the primary processing error, consider calling `addSuppressed(cleanupFailure)` with the right semantics, though `try-with-resources` usually handles this more safely.

## 7. Cause chains across multiple application layers

Consider three boundaries:

```text
Repository: data access
    -> Service: business operation
        -> Controller/Message handler: entry boundary
```

The **Repository** can translate library errors into an exception belonging to the persistence-layer abstraction:

```java
// Integration snippet: invoke the actual repository inside a method.
try {
    jdbcOperation();
} catch (java.sql.SQLException cause) {
    throw new DataAccessFailure(
            "Unable to execute order persistence operation", cause);
}
```

The **Service** adds business context:

```java
try {
    persistOrder(order);
} catch (DataAccessFailure cause) {
    throw new OrderProcessingException(
            "Unable to create order", cause);
}
```

The two snippets above are **integration snippets** only; `DataAccessFailure`, `OrderProcessingException`, `jdbcOperation`, `persistOrder`, and `order` must be defined in your application. The key point is that the same chain travels upward instead of being replaced by a message string.

The **Boundary** (web exception handler, scheduled job wrapper, message consumer) decides on logging:

```java
// Integration snippet: logger and operationId are already declared.
try {
    applicationService.execute();
} catch (OrderProcessingException failure) {
    logger.log(Level.SEVERE,
            "operation failed, operationId=" + safeOperationId,
            failure);
    throw failure;
}
```

This pattern of **both logging and rethrowing** can create **duplicate logs** if an outer layer also logs. In practice, you usually designate **one boundary responsible for logging unhandled exceptions**, and simply preserve the chain when crossing internal layers. If you must log before rethrowing for a business reason, verify whether the next layer logs it again.

### 7.1. When is `throw;` or `throw e;` enough?

Java does not have `throw;` like some other languages. Inside `catch (SomeException e)`, use `throw e;` to rethrow **the same throwable** if the method signature permits.

```java
try {
    performOperation();
} catch (java.io.IOException e) {
    // Safe cleanup/metrics can be done here without replacing the throwable.
    throw e;
}
```

The snippet requires `performOperation()` to be declared, and the enclosing method must allow throwing `IOException`. `throw e;` preserves the existing object and stack trace. There is no need to wrap an exception if the current layer does not actually add meaningful information or a required abstraction.

### 7.2. Custom exceptions must not lose the cause

If you create a custom exception, consider providing a suitable constructor:

```java
public class ServiceFailure extends RuntimeException {
    public ServiceFailure(String message, Throwable cause) {
        super(message, cause);
    }
}
```

This is a standalone class that can be saved as `ServiceFailure.java`. Do not wrap every exception into the same `ServiceFailure("Error")` without a cause; callers and operators will not be able to distinguish database, validation, and downstream failures.

## 8. Logging once: preserving the cause does not mean logging at every layer

An anti-pattern:

```text
Repository catches SQLException -> ERROR + stack
Service catches RepositoryException -> ERROR + stack
Controller catches ServiceException -> ERROR + stack
Gateway catches request failure -> ERROR + stack
```

One real failure can produce 4 stack traces. When errors repeat continuously, the application suffers a **log storm**, the async logging queue fills up, disk/collector capacity is overwhelmed, and critical signals are buried in noise.

Practical rules:

1. Lower layers **wrap with cause and propagate upward**, avoiding logging errors they do not handle.
2. A layer that can **genuinely recover** (successful retry, successful fallback) logs an event with appropriate semantics; do not log `ERROR` after full recovery if the system does not need an alert.
3. The **entry/final handling layer** decides once to log the full event with the Throwable when an error cannot be handled.
4. If policy requires separately auditing a rejected/failed action, record an audit event under its own schema/retention rather than treating it as a repeated stack trace dump.
5. If per-layer context is needed, wrap the cause with a short, stable message; do not dump payloads.

**“Log once” is not an absolute rule.** A retry attempt, a circuit breaker transition, or a separate side effect can be independent events worth recording. However, those records should have distinct event codes, attempt/count fields, and appropriate levels rather than copying the same stack trace everywhere.

## 9. Async exceptions: `CompletionException` and `ExecutionException`

In Java concurrency, exceptions can be **automatically wrapped** by an asynchronous API:

- `CompletableFuture.join()` typically throws `CompletionException` when a task completes exceptionally.
- `Future.get()` or `CompletableFuture.get()` can throw `ExecutionException` wrapping the underlying cause.
- There are also `CancellationException` and `InterruptedException` with distinct semantics.

Integration snippet example:

```java
try {
    resultFuture.join();
} catch (java.util.concurrent.CompletionException wrapper) {
    Throwable cause = wrapper.getCause();
    // Logging the wrapper as Throwable preserves the cause chain if set.
    log.error("Background task failed", wrapper);
    // Do not automatically turn every cause into a retryable error.
}
```

This is an integration snippet assuming `resultFuture` and `log` are available. If the application normalizes errors at a boundary, it can use `wrapper.getCause()` as the classification source, but **should not discard the wrapper if it helps identify the async boundary**.

An anti-pattern:

```java
// Wrong: creates a new exception with only a message string, losing the cause.
catch (java.util.concurrent.ExecutionException e) {
    throw new RuntimeException(e.getMessage());
}
```

Better:

```java
// Snippet inside a method that may throw a runtime exception.
catch (java.util.concurrent.ExecutionException e) {
    throw new RuntimeException("Async operation failed", e);
}
```

You can handle the underlying cause directly instead of re-wrapping depending on the API contract, but preserve the chain or have a clear reason for normalization.

### 9.1. Do not unwrap infinitely

A “root cause” helper can walk `getCause()` multiple times. However:

- It may encounter `null` and must stop.
- Library-created exceptions can have unusual cause relationships; loops must be avoided.
- `InterruptedException`, `CancellationException`, and `TimeoutException` have distinct handling semantics—**they are not mere wrappers**.
- `SQLException` can also carry `getNextException()` in addition to the cause chain.
- Suppressed exceptions are a separate branch, not on the normal `getCause()` path.

Therefore, do not collapse everything into a single `rootCause.message` string and drop the original `Throwable`. Only normalize **well-understood wrapper types** for a specific policy.

## 10. `InterruptedException`: preserve both the cause and the interrupt flag

Java uses interrupts to signal a cancellation/stop request. When `InterruptedException` is thrown and caught, blocking APIs typically **clear the interrupt status**. If a method cannot rethrow the checked exception, restore the interrupt flag before wrapping:

```java
// Integration snippet; taskQueue is a BlockingQueue<?>.
try {
    taskQueue.take();
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    throw new IllegalStateException("Consumer interrupted", e);
}
```

This is an example when the method signature **does not allow `throws InterruptedException`** and the policy is to terminate processing appropriately. Conversely, if possible, **rethrow it directly** and let the caller handle it:

```java
public void awaitWork() throws InterruptedException {
    taskQueue.take(); // taskQueue is an existing BlockingQueue<?> field.
}
```

The snippet above is an integration fragment requiring `taskQueue`. Not every interrupt should be logged at `ERROR`: during an orderly shutdown, an interrupt can be a normal signal. However, **swallowing the interrupt and only logging a message** can leave a worker running in an invalid lifecycle state.

Keeping `cause=e` lets investigators see later that the operation was interrupted; `Thread.currentThread().interrupt()` ensures the execution thread continues to observe the cancellation signal. The two actions solve **two different problems** and do not replace each other.

## 11. Root cause for HTTP, services, and message consumers

### 11.1. Web controller / exception handler

Suppose an HTTP request fails due to storage. The client can receive a sanitized response such as:

```json
{
  "errorCode": "ORDER_PROCESSING_FAILED",
  "message": "Không thể xử lý yêu cầu lúc này",
  "requestId": "req-2041"
}
```

This is an **illustrative** response, not output from the Java program above. It does not expose stack traces, hostnames, SQL queries, or credentials. Internally, the handler should emit a log correlated with `requestId`, `errorCode`, `exceptionType`, and the **`Throwable`** so operators can find the cause.

Do not return `rootCause.getMessage()` or `Throwable.printStackTrace()` directly in an HTTP response. The deepest message may contain network configuration, file paths, table names, SQL, or sensitive input data.

For expected input errors (such as 400 validation failures), an `ERROR` stack trace is usually unnecessary every time; classify error codes and log levels appropriately to avoid noise.

### 11.2. Message consumer

A consumer processing an event may fail at the database:

```text
Message received
  -> business handler
  -> RepositoryException(cause=SQLException)
  -> Consumer boundary
      -> classified failure/retry or DLQ
```

Recommended log fields:

- `messageId`/broker coordinates (validated), `consumerGroup`, `attempt`, `errorCode`.
- `exceptionType` and `rootCauseType` for classification, **without exposing raw messages**.
- Full `Throwable` when investigation is needed, with appropriate frequency and access control.
- Outcome `retry_scheduled` / `dead_lettered` / `processing_failed` must reflect the **actual state**, not be inferred solely from the exception class.

A root cause of `SQLTimeoutException` can be a signal for retrying, but **the retry policy must consider idempotency, retry limits, backoff, and already-committed side effects**. Never retry infinitely just because the root cause contains the word “timeout”.

### 11.3. Scheduled jobs

In a scheduled job, errors may be wrapped or caught by the scheduler so subsequent runs continue. Log `jobName`, `runId`, and `scheduleTime` appropriately and preserve the `Throwable`. Do not just print `"Job failed"` and swallow the exception when the scheduler needs failure status for retries or alerts.

## 12. Safely finding the “root cause” in a cause chain

A typical helper:

```java
// Integration snippet; caller ensures failure != null.
Throwable current = failure;
while (current.getCause() != null) {
    current = current.getCause();
}
```

This illustrates the idea, but if the cause chain is non-standard or contains a **cycle**, it may never terminate. The standalone Java 17 code in Section 4 uses an identity set to avoid loops.

When receiving error data from complex libraries, you should:

1. Keep the original Throwable as the primary source.
2. Use a safe helper if you need the **deepest cause type**.
3. Inspect meaningful special wrappers, such as `CompletionException` or `ExecutionException`, before classifying.
4. Check `getSuppressed()` when resource cleanup, transaction rollback, or shutdown is involved.
5. For SQL, check `SQLException.getNextException()` if the driver chains related errors.
6. Do not assume “the deepest cause is always the real root cause” when a problem involves multiple factors or concurrent downstream failures.

A deep `NullPointerException` may show the crash site, but it does not by itself explain **why the value was null**. True root cause analysis also requires log context, metrics, traces, configuration, deployment events, and business data.

### 12.1. Do not use `Throwable.getMessage()` as an error code

`getMessage()` can vary by Java version, driver, locale, or input data. Some messages also contain sensitive queries or identifiers. For an error dashboard:

```json
{
  "event": "order.processing_failed",
  "errorCode": "STORAGE_UNAVAILABLE",
  "exceptionType": "OrderProcessingException",
  "rootCauseType": "IOException",
  "requestId": "req-2041"
}
```

This is an illustrative structured event. `errorCode` should be determined by the application according to policy, not by grabbing an arbitrary prefix of the exception text and using it as a high-cardinality metric label.

## 13. Root cause and structured logging

A good exception event typically includes:

| Field | Role |
| --- | --- |
| `timestamp` | Timestamp in UTC / consistent format |
| `event` | For example `order.processing_failed` |
| `level` | Severity level according to policy |
| `service`, `environment`, `instance` | Which system/instance experienced the error |
| `requestId`/`traceId`/`messageId` | Request or event correlation |
| `errorCode` | Stable error code for dashboards |
| `exceptionType` | Outer exception type |
| `rootCauseType` | Deepest cause type when appropriate |
| `operation` | Validated name of the failed operation |
| `durationMs` | Processing duration when meaningful |
| `throwable` | Throwable object for the backend to render stack trace and cause chain |
| `retryable` / `attempt` | Classified retry context |

Not every event needs all of the fields above; choose a useful subset based on risk level and observability tooling. **Do not arbitrarily serialize the full exception object to JSON** if the serializer will traverse the entire object graph, expose internal fields, or hit reference cycles. Use a logging API with `Throwable` and an encoder designed to handle exceptions.

With **SLF4J + Logback**, the call:

```java
// Integration snippet; log, requestId, and cause are already declared.
log.error("event=order_failed requestId={}", requestId, cause);
```

passes the throwable as the final argument. In ecosystems with a structured logging API, you can add dedicated key-value fields while still ensuring the throwable is preserved. Libraries and backends differ in how they configure stack trace encoders, JSON layouts, message templates, and MDC.

**MDC** is only context attached to an event: it does not preserve causes by itself. You must clear MDC in `finally` when using thread pools and propagate it properly across async boundaries. `traceId` helps cross-service investigation, but it does not prove an error had a cause in another JVM; usually you have a **distributed trace linking events across processes**, not an automatic `Throwable.getCause()` chain across HTTP/Kafka.

## 14. When log formats or frameworks lose stack traces

Even when code passes a `Throwable`, the final log may fail to show the cause due to configuration:

- The pattern/layout only prints `%msg` without outputting the exception properly.
- The JSON encoder omits the stack trace field or sets a stack depth limit.
- An appender/filter drops `ERROR` events.
- The async queue is full, logs are dropped, or the JVM crashes before flushing.
- A collector/parser truncates overly long messages or mis-groups multiline logs.
- Overly broad redaction rules strip all diagnostic information.
- Log routing sends stack traces to a sink that investigators do not have permission to read.

Example of a common Logback pattern:

```xml
<configuration>
    <appender name="STDOUT"
              class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%d{HH:mm:ss.SSS} %-5level %logger - %msg%n%ex</pattern>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="STDOUT"/>
    </root>
</configuration>
```

This is an illustrative configuration for a project with a compatible Logback Classic setup; `%ex` instructs it to display the exception in the pattern. For JSON logging, check whether the encoder outputs `stack_trace`/cause chains. Field names vary by library and version; do not assume a Logback pattern works in Log4j 2.

**Do not look at a single text line and conclude the root cause was lost.** Some collectors store exceptions in a separate field or split stack traces across multiple fields. Check the **final data at the sink** and query permissions. When a logger is disabled by level or the formatter does not output the `Throwable`, having the cause in the Java object does not guarantee operators will see it.

## 15. Log levels and error classification

Preserving the cause does not mean every exception belongs at `ERROR`.

| Situation | Considered level | Reason |
| --- | --- | --- |
| Expected invalid user validation | INFO/WARN or dedicated event | Not an infrastructure failure |
| Valid non-existent resource | DEBUG/INFO depending on policy | Avoid false alarms |
| Retryable timeout within budget | WARN or budgeted retry event | Needs monitoring, but the system may self-recover |
| Final operation failure | ERROR with appropriate throwable | Requires investigation/alert |
| Interrupt caused by normal shutdown | DEBUG/INFO depending on policy | Avoid noisy ERROR spikes |
| `OutOfMemoryError` or `StackOverflowError` | Critical incident requiring specialized handling | Do not arbitrarily catch and treat as recoverable |

`errorCode` and `outcome` should describe the **business/technical meaning**, while `level` expresses observability priority. Do not choose the log level based solely on the deepest exception type.

Be careful with `catch (Throwable t)`: it also catches `Error`, which can indicate severe JVM failures and leave the application running in an unsafe state. Normally, catch only the exception types you actually know how to handle; at special boundaries you may need last-resort failure monitoring, but it must follow proper operational policy.

## 16. Security and privacy when logging root causes

A deep cause in the stack can contain:

- JDBC URLs, hostnames, database names, or schemas.
- SQL queries with literal values, or unique constraints containing personal data.
- HTTP URLs containing query tokens or sensitive paths.
- Internal file paths, OS account names, or environment details.
- Authorization headers or message contents inside exception messages.
- Library and version details that could help an attacker infer infrastructure.

Guidelines:

1. **Do not send raw stack traces/cause chains to public clients.** Clients receive a sanitized error code/request ID; internal logs retain the throwable under access control.
2. **Do not put raw exception messages into metric labels** or unbounded-cardinality fields.
3. **Do not serialize payloads to “add context”** if the payload contains PII/secrets.
4. Use validated `errorCode`, `safeId`, `operation`, and `traceId` for investigation.
5. Restrict access, retention, and transport paths for logs containing stack traces.
6. If redaction is needed, implement and test it at the appropriate layer so it **does not wipe out the cause chain information** needed for operations.
7. Separate application logging from mandatory audit trails; auditing may require minimal data sources, integrity guarantees, and separate permissions.
8. Watch out for **log injection** when context or `Throwable.getMessage()` contains newlines/control characters; use encoders/structured logging with proper escaping.

**Preserving the root cause does not mean exposing all internal details.** Keep evidence inside the trusted zone and present safe information at external boundaries.

## 17. Testing cause preservation across application layers

Do not test only a message text. Verify the **Throwable relationships** and log output:

| Case | What to prove |
| --- | --- |
| Wrap with `super(message, cause)` | `wrapper.getCause() == original` |
| Wrap across 2–3 layers | Full chain: service → repository → I/O/SQL |
| Wrong wrap taking only message | Test detects that the cause was lost |
| Rethrow `throw e;` | Does not create an unnecessary new throwable |
| JUL logging with `Throwable` | `LogRecord.getThrown()` contains the original wrapper |
| SLF4J logging with exception | Test appender/event preserves throwable and stack trace |
| `try-with-resources` with processing + close errors | Close error is in `getSuppressed()` |
| `CompletableFuture.join()` failure | Cause of `CompletionException` is preserved |
| `Future.get()` failure | `ExecutionException` contains the task's error |
| Interrupt while blocking | Interrupt flag is handled according to contract |
| Custom handler/formatter | Stack trace/cause is output as expected |
| JSON log collector | Throwable is still present at the sink, not truncated away |
| Exception message containing token or newline | Does not leak secrets or forge log lines |
| One error across multiple layers | Does not create redundant duplicate stack traces |
| Full async logging queue | Has metrics/backpressure/failure policy; does not assume logs always arrive |

A simple unit test can use:

```java
// Integration snippet; original and wrapper are constructed Throwables.
if (wrapper.getCause() != original) {
    throw new AssertionError("Root cause lost");
}
```

To test JUL logging, create a test handler that captures `LogRecord` and verifies `record.getThrown()` is the exact object; for SLF4J/Logback, use an appropriate test appender. In end-to-end tests, also verify the formatter, collector, and stored data, because an exception can be preserved in the JVM and dropped downstream.

**Do not infer success from the number of `Caused by:` lines**: some encoders fold/truncate stack traces and some SDKs convert exceptions into separate fields. Tests must align with the actual observability target.

## 18. Diagnosing root cause in production

When investigating an `order.processing_failed` event:

1. Grab `requestId` or `traceId`, `service`, `environment`, and the timestamp.
2. Open the boundary log that has the **`Throwable`**; inspect the outer exception type.
3. Walk the **`Caused by` chain** to understand failures in lower layers.
4. Check **Suppressed** if the error involves resource closing or cleanup.
5. Correlate the timestamp with metrics such as connection pool saturation, latency, network errors, disk, and deployment/config changes.
6. If the incident spans multiple services, use distributed traces and error codes to link causes across processes; do not expect `Throwable.getCause()` to cross network boundaries automatically.
7. Check retries, circuit breakers, rollbacks, and committed side effects to assess impact.
8. Conclude the system-level cause only after gathering sufficient evidence, rather than reading only the last exception line.

Example: the deepest cause is `SocketTimeoutException`. The operational cause could be an overloaded downstream service, DNS/network issues, a stalled connection pool, a GC pause, or an overly low timeout. The cause chain shows the **observable failure point**, while root-cause analysis needs **correlated evidence** to find the deeper system-level cause.

## 19. Common mistakes

### 19.1. Logging only `e.getMessage()`

Loses the type, stack, and causes in the logging event. Use the logger overload that accepts `Throwable`.

### 19.2. Wrapping with `new RuntimeException(e.toString())`

Still produces only text. Pass `e` as the cause.

### 19.3. Assuming `throw new Exception("...", cause)` preserves the exact original stack in the wrapper

The wrapper gets a new stack at the wrapping site. What matters is that **the old cause is still preserved**, not that the wrapper's stack matches the original stack.

### 19.4. Logging stack traces at every layer

Does not lose the cause, but creates duplicate records, increases cost, and obscures signals. Choose the appropriate boundary.

### 19.5. Logging only the deepest cause

Can discard the wrapper's business context and suppressed exceptions. Pass the throwable at the boundary, and use the deepest type as an additional field when needed.

### 19.6. Swallowing `InterruptedException`

Can break the thread lifecycle and lose the cancellation reason. Rethrow or restore the interrupt flag, and preserve the cause if wrapping is required.

### 19.7. Ignoring suppressed exceptions

Cleanup errors can be overlooked if you only call `getCause()`. Use a formatter that supports suppressed exceptions or inspect `getSuppressed()` when needed.

### 19.8. Treating an exception class as the final root-cause diagnosis

`IOException`, `SQLException`, or a timeout is an **observable technical symptom**; you still need to examine infrastructure, state, and other dependencies.

### 19.9. Printing stack traces directly to clients

Risks exposing internals. External boundaries should return a safe code/message and request ID, while internal logs protect the throwable.

### 19.10. Ignoring encoder/collector configuration

The code has `log.error("...", e)`, but the JSON layout only stores the message or the system drops/truncates stack traces. Verify all the way to the actual storage destination.

## 20. Implementation checklist

- [ ] When wrapping an exception, always consider the `(message, cause)` constructor.
- [ ] Do not replace the cause chain with `getMessage()`/`toString()` when creating upper-layer errors.
- [ ] Rethrow the same throwable when no abstraction change is needed.
- [ ] Pass the **actual `Throwable`** to JUL, SLF4J, Log4j 2, or the corresponding logging API.
- [ ] Keep both the business-context wrapper and the deeper cause; do not print only the deepest message.
- [ ] Understand the difference between `getCause()` and `getSuppressed()`.
- [ ] For async wrappers, do not blindly unwrap `CompletionException`/`ExecutionException`.
- [ ] When catching `InterruptedException`, handle the interrupt according to contract; do not swallow cancellation signals.
- [ ] Choose one error boundary responsible for logging the full throwable to avoid duplicate stacks.
- [ ] Do not log full stack traces for high-frequency expected validation errors unless needed.
- [ ] Use stable error codes and correlation IDs; do not use raw exception messages as metric labels.
- [ ] Do not expose stack traces/PII/secrets to clients or unauthorized sinks.
- [ ] Verify that the logging encoder, async queue, collector, and storage retain and allow querying the throwable.
- [ ] Test `wrapper.getCause() == original`, suppressed exceptions, rethrows, async behavior, and redaction.
- [ ] Investigate root causes using logs + traces + metrics + actual state, rather than concluding from the last exception alone.

**Conclusion:** **Preserve root cause** means **adding context without breaking the cause chain**: wrap with `new ...Exception("context", original)`, pass the **`Throwable`** to the logger, preserve both `Caused by` and `Suppressed`, and choose a responsible logging boundary. That way, a single business-layer error record still leads operators back to the original technical failure, without compromising privacy or logging reliability.
