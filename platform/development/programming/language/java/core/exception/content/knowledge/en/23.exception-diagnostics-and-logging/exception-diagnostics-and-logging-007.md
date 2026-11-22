# Choosing the Layer Responsible for Logging to Avoid Duplicating the Same Error in Java

An exception can pass through multiple layers: repository → service → controller → global exception handler. If **each layer logs an `ERROR` with the full stack trace and then rethrows**, a single business failure will produce multiple identical log events. Logs become noisy, storage costs increase, counting actual incidents becomes difficult, and the alerting system may trigger multiple alerts for the same request.

This lesson belongs to **Java Core – Exception / Diagnostics and Logging**. The goal is to determine **which layer owns the error-handling decision and is responsible for logging**, while preserving cause information across layers. Pure JDK examples run on **Java 17+**; snippets containing `logger` are integration code illustrating a logging framework.

## 1. Core principle: log where the outcome is handled

Start by asking: **“Which layer has enough context and actually decides what happens to this failure?”**

- If a layer **cannot resolve** the error and only propagates it, it should normally **preserve the cause, add useful context, and rethrow; do not log an `ERROR` stack trace here**.
- If a layer **actually handles/recovers from** the error and no longer propagates it as a failure to the caller, that layer is where an appropriate log (`DEBUG`, `INFO`, `WARN`, or `ERROR` depending on impact) may be needed.
- If the error **reaches the terminal boundary** and the request/job/message is marked as failed, the final handling boundary is typically where **a single rich error event is logged**, followed by returning an error code or completing processing.
- If another component is already guaranteed to log the final failure (for example, a framework exception resolver or job runner), you must know **the existing logging contract** so you do not create a duplicate.

“Logging once” here means **one primary error event per failure within an ownership scope**, typically a request, a job, or a business operation. This is not a ban on all logs in other layers: progress logs, metrics, recovery warnings, purposeful audit logs, or information with different semantics still have value.

A processing diagram:

```text
Request R-100
   │
   ▼
Controller ───────────────┐
   │                     │
   ▼                     │
Service                  │
   │                     │
   ▼                     │
Repository               │
   └── throws IOException │
          │              │
          ├─ Repository: keep error as-is; no duplicate ERROR
          ▼              │
      Service: add context via cause; no duplicate ERROR
          │              │
          ▼              │
     Controller / global handler
          │
          ├─ log one ERROR + Throwable + requestId
          └─ return appropriate error result
```

What to optimize for is not “the fewest logs” but **each log having a clear purpose and a single clear owner**.

## 2. Why does “log and throw” easily cause duplicates?

Suppose every layer does the following:

```java
try {
    repository.load();
} catch (IOException e) {
    logger.error("Repository failed", e);
    throw e;
}
```

This is an **illustrative snippet**, assuming `repository` and `logger` are available. If the service also does:

```java
try {
    repository.load();
} catch (IOException e) {
    logger.error("Service failed", e);
    throw new IllegalStateException("Không tải được hồ sơ", e);
}
```

and the controller/global handler adds `logger.error("Request failed", e)`, one I/O error has turned into **three stack traces**. The logs may have different wording, yet they belong to the same failure chain, making operators think there are three independent incidents.

Common consequences:

1. **Inaccurate error counts:** a dashboard counting `ERROR` logs sees three lines when only one request failed.
2. **Harder grouping:** the same error appears with multiple messages and wrapper exceptions.
3. **Increased cost:** three long stack traces, especially if the centralized logging system charges by ingested data volume.
4. **Alert noise:** rules based on `ERROR` count trigger faster than the actual number of failed requests.
5. **Data exposure in multiple places:** each copy can contain stack traces, messages, parameters, or sensitive information.
6. **Harder-to-read timelines:** duplicate logs obscure other events that were actually useful prior to the failure.

This practical rule is often phrased as **“log or throw”**: if the current layer must rethrow, let the responsible downstream/outer layer do the logging. This is a default design principle, **not an absolute rule**; security, audit, operational standards, or system boundaries may require an additional event with a distinct meaning.

## 3. Lower layers: propagate exceptions and preserve `cause`

A repository typically knows that reading data failed, but it does not necessarily know whether the overall request will fail: the service might try a cache, retry, or choose a fallback source. Therefore, the repository should **return errors according to its contract** so the layer with enough context can decide.

In intermediate layers, there are two main options:

- **Propagate the original exception:** when the exception type and API contract allow it.
- **Wrap the exception and preserve the cause:** when you need to translate from a technical error into the business context of the current layer.

Example:

```java
try {
    return dataSource.read();
} catch (IOException e) {
    throw new IllegalStateException("Không nạp được cấu hình của khách hàng", e);
}
```

This is an **illustrative snippet** inside a method with an appropriate return type, not a standalone program. The constructor `IllegalStateException(message, e)` preserves the `getCause()` link so the outermost handler can still see the `IOException`.

Do not wrap like this:

```java
throw new IllegalStateException("Không nạp được cấu hình");
```

if it replaces an exception you just caught, because doing so **loses the cause**. You should also avoid creating wrappers at every step without adding real context; an overly deep wrapper chain makes stack traces hard to read.

**Goal:** preserve the cause and necessary context so that **a single final logging point** can tell the full story of the failure.

## 4. Standalone Java 17 example: one error, one logging point

Create the file `SingleBoundaryLogDemo.java`:

```java
import java.io.IOException;

public class SingleBoundaryLogDemo {
    static String readProfile() throws IOException {
        throw new IOException("database unavailable");
    }

    static String loadProfile() {
        try {
            return readProfile();
        } catch (IOException e) {
            throw new IllegalStateException(
                    "không tải được hồ sơ", e);
        }
    }

    static String controller() {
        return loadProfile();
    }

    public static void main(String[] args) {
        try {
            controller();
        } catch (IllegalStateException failure) {
            // Illustrates the log event at the request boundary.
            System.out.println(
                    "ERROR requestId=R-100 operation=profile.load");
            System.out.println("outer = "
                    + failure.getClass().getSimpleName()
                    + ": " + failure.getMessage());

            Throwable cause = failure.getCause();
            System.out.println("cause = "
                    + cause.getClass().getSimpleName()
                    + ": " + cause.getMessage());
        }
    }
}
```

Compile and run:

```bash
javac SingleBoundaryLogDemo.java
java SingleBoundaryLogDemo
```

Exact output:

```text
ERROR requestId=R-100 operation=profile.load
outer = IllegalStateException: không tải được hồ sơ
cause = IOException: database unavailable
```

`readProfile()` throws an `IOException`, `loadProfile()` wraps it with additional context **without logging it itself**, and `controller()` propagates it. `main()` acts as **the request boundary**, responsible for recording one final event. The `System.out` statements are only for producing easily verifiable illustrative output; **production applications should use a logging framework** and pass the Throwable object itself to preserve the stack trace.

If using an SLF4J-style logging API at the boundary, the corresponding statement could be:

```java
logger.error(
        "Không tải được hồ sơ, requestId={}",
        requestId,
        failure);
```

This is **integration code**, assuming `logger` is SLF4J-compatible and `requestId` and `failure` already exist. In a typical logging configuration, the Throwable object in the last argument is printed together with its stack trace and cause. Check the specific overload of the API/logger you are using; do not rely on concatenating `failure.getMessage()` as a substitute for the Throwable.

## 5. Which layer is the error-handling boundary?

Depending on the application type, the “final layer” can be:

| Application | Typical responsible point | Handling outcome |
|---|---|---|
| HTTP/REST | Global exception handler or delegated HTTP filter | Valid HTTP response, error code/correlation ID, log failed request |
| Batch/CLI | Job runner or `main()` entry point | Log failed job result, exit status/retry policy |
| Queue consumer | Handler at the message consumption boundary | Decide ack/nack, retry, dead-letter, log final failure |
| Scheduler | Execution framework of the scheduled job | Determine task failure and track schedule execution |
| Executor/Future | Component **observing the result** via `get()`/`join()` or error-managing callback | Read cause, decide retry/cancel/fallback, and log |
| Reusable library | Usually **does not** own the application's final outcome | Throw meaningful exceptions, preserve cause; do not log ERROR for every caller |

These are **typical locations**, not mandatory class names. A framework may already log unhandled exceptions automatically; many deployments also have a service mesh, tracing, or centralized error reporting. Before adding a new logger yourself, determine who already records the failure event.

### Spring MVC example (integration snippet)

In a Spring Web application, you can choose a `@RestControllerAdvice` to centralize converting unexpected errors into a standard response:

```java
@RestControllerAdvice
class ApiExceptionHandler {
    private static final org.slf4j.Logger LOG =
            org.slf4j.LoggerFactory.getLogger(ApiExceptionHandler.class);

    @ExceptionHandler(Exception.class)
    ResponseEntity<ApiError> handle(Exception error,
                                    HttpServletRequest request) {
        String requestId = request.getHeader("X-Request-Id");
        LOG.error("Unhandled request failure, requestId={}",
                  requestId, error);

        return ResponseEntity.status(500)
                .body(new ApiError("INTERNAL_ERROR", requestId));
    }
}
```

This is an **architectural example, not standalone runnable code**: it requires Spring MVC, Jakarta Servlet, corresponding imports, and an `ApiError` record/class. This snippet intentionally illustrates **ownership placement** only; in practice, you need to classify 4xx/5xx, obtain the request ID from a trusted source (do not blindly trust client-supplied headers), manage security, and avoid letting the framework or another filter log the same stack trace again.

Do not expose raw `error.getMessage()` and stack traces of internal errors in the HTTP response. The client response should contain a safe error code and correlation ID; detailed diagnostics belong in access-controlled logging systems.

## 6. If an intermediate layer handles the error, logging there can be right

An exception that **has been handled and is not propagated** is no longer a request failure. For example, a remote API temporarily fails, but the service has a valid cache. The service itself **owns the fallback decision**, so it can log a `WARN` or metric about degraded mode; the controller receives successful data and should not log an `ERROR` for the same root cause.

Create the file `RecoveredFailureLogDemo.java`:

```java
import java.io.IOException;

public class RecoveredFailureLogDemo {
    static String remoteName() throws IOException {
        throw new IOException("upstream unavailable");
    }

    static String loadName() {
        try {
            return remoteName();
        } catch (IOException e) {
            // The service decides to recover using cached data.
            System.out.println(
                    "WARN fallback=cache reason=upstream_unavailable");
            return "Tên trong cache";
        }
    }

    public static void main(String[] args) {
        System.out.println("response = " + loadName());
    }
}
```

Run:

```bash
javac RecoveredFailureLogDemo.java
java RecoveredFailureLogDemo
```

Output:

```text
WARN fallback=cache reason=upstream_unavailable
response = Tên trong cache
```

Here `main` receives no exception and does not need to log an `ERROR`. The service layer genuinely **changed the outcome from failure to degraded success**, so logging there carries a different meaning: the system used a fallback. For frequent, recoverable remote errors, a `fallback_count` metric or sampled logging is more effective than thousands of identical stack traces.

Depending on the business logic, a recovered error may not even need a `WARN` log: a routine cache miss, an expected `FileNotFoundException`, or a normal worker shutdown signal should usually be `INFO`/`DEBUG` or not logged at all. **The log level depends on abnormality and impact**, not merely on whether an exception occurred.

## 7. A failure retried multiple times: counting attempts vs. counting operations

Retries complicate the picture: **one operation** can consist of multiple **attempts**. If every attempt logs an `ERROR` with a stack trace and the outermost layer also logs the overall failure, dashboards can easily mistake one incident for four.

Distinguish between:

- **Attempt failure:** a single attempt fails, but the policy may retry. You can record a `retry_attempts` metric, `DEBUG` log, or short log if needed for investigation.
- **Operation failure:** after exhausting all attempts, the entire operation fails to achieve its goal. This is usually where the final `ERROR` is logged, including the attempt count and final cause.
- **Operation success after retry:** there should be no “unable to complete” `ERROR` for an operation that ultimately succeeded; you can record a metric or `INFO`/`WARN` about latency and retry usage.

### Standalone example: three attempts, one final error log

File `RetryOnceLogDemo.java`:

```java
import java.io.IOException;

public class RetryOnceLogDemo {
    static String attemptRead(int attempt) throws IOException {
        throw new IOException("upstream unavailable");
    }

    static String readWithRetry() {
        IOException last = null;

        for (int attempt = 1; attempt <= 3; attempt++) {
            try {
                return attemptRead(attempt);
            } catch (IOException e) {
                last = e;
                // Record a retry metric here if needed, not an ERROR each time.
            }
        }

        throw new IllegalStateException(
                "thất bại sau 3 lần thử", last);
    }

    public static void main(String[] args) {
        try {
            readWithRetry();
        } catch (IllegalStateException failure) {
            System.out.println(
                    "ERROR operation=remote.read attempts=3");
            System.out.println("error = " + failure.getMessage());
            System.out.println("cause = "
                    + failure.getCause().getClass().getSimpleName()
                    + ": " + failure.getCause().getMessage());
        }
    }
}
```

Commands:

```bash
javac RetryOnceLogDemo.java
java RetryOnceLogDemo
```

Output:

```text
ERROR operation=remote.read attempts=3
error = thất bại sau 3 lần thử
cause = IOException: upstream unavailable
```

The task is tried three times, yet the `ERROR` log for the operation appears **only once** at the end. The sample intentionally does not sleep so the output is easy to verify; production retries need bounded attempts, timeouts, appropriate exponential backoff/jitter, checks for which errors are actually retryable, and **idempotency** to avoid repeating side effects (such as charging a payment twice).

If you need detailed tracing per attempt, log at `DEBUG` or emit a metric with `attempt`, `operationId`, and a classified outcome; **it is not necessary to repeat the entire stack trace**. Individual attempts are distinct technical events that can be useful, not three independent operation failures.

## 8. Asynchronous code: who observes and who logs the exception?

With `ExecutorService.submit(...)`, errors from a `Callable` are typically held inside the `Future`. If nobody calls `get()`, the error can be silently missed. If multiple components read and log the same `Future`, the error can be duplicated.

Key points to distinguish:

- `Future.get()` can throw `ExecutionException`; **the cause** is in `getCause()`.
- `CompletableFuture.join()` typically reports exceptional completion via `CompletionException`; inspect the underlying cause.
- `CompletableFuture.whenComplete(...)` is suitable for recording/observing the result without changing its value, but **if you log both in the callback and at the caller's `join()`**, duplicates easily happen.
- `CompletableFuture.exceptionally(...)` and `handle(...)` can recover an error into a normal result; in that case, the recovery callback can record degraded mode, while the caller does not log an additional operation failure.
- `cancel(...)`, `InterruptedException`, and `CancellationException` are important lifecycle signals; do not automatically treat them as `ERROR`.

### Standalone example: log where the final stage is observed

Create the file `AsyncBoundaryLogDemo.java`:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;

public class AsyncBoundaryLogDemo {
    public static void main(String[] args) {
        CompletableFuture<Integer> parsed =
                CompletableFuture.completedFuture("abc")
                        .thenApply(Integer::parseInt);

        CompletableFuture<Integer> processed =
                parsed.thenApply(value -> value + 1);

        try {
            System.out.println(processed.join());
        } catch (CompletionException failure) {
            Throwable cause = failure.getCause();
            System.out.println(
                    "ERROR operation=parseAndIncrement");
            System.out.println("cause = "
                    + cause.getClass().getSimpleName());
        }
    }
}
```

Run:

```bash
javac AsyncBoundaryLogDemo.java
java AsyncBoundaryLogDemo
```

Output:

```text
ERROR operation=parseAndIncrement
cause = NumberFormatException
```

`thenApply(Integer::parseInt)` fails; downstream stages carry the exceptional completion. There is no intermediate `ERROR` at each `thenApply`. `main`, which owns the final outcome, logs a single event. If you use `whenComplete` to log immediately on `parsed`, then the final observing layer must **not log the same error again**, or that callback should only record metrics without printing a stack trace.

In an application with multiple independent `Future`s, you must have a strategy to **observe each operation**: a failure in two different jobs is genuinely two events that need to be logged. “Log once” does not mean ignoring multiple operations just because they happen to throw the same exception type.

## 9. Classifying log levels by actual outcome

Having an exception does not automatically mean `ERROR`. A decision matrix you can apply:

| Situation | Typically appropriate level | Reason |
|---|---|---|
| Unexpected, unrecovered request failure | `ERROR` at the boundary | Needs investigation of an operation failure |
| Temporary error handled by fallback; service still works | `WARN`, sometimes `INFO`/metric | Quality is degraded, but the operation completed |
| Retry attempt with budget remaining | `DEBUG`/metric or short log | Not the final failure yet |
| Expected invalid input, returning HTTP 400 | Possibly `INFO`/metric or no log | May be normal client behavior |
| Task intentionally cancelled during shutdown | `DEBUG`/`INFO` or no log | Normal lifecycle |
| Security/audit error requiring its own trail | Controlled security log, level per policy | Different purpose from technical error stack traces |
| Resource-closing failure with major impact | `ERROR` at the responsible boundary | Risk of data or resource corruption |
| Exception propagated across multiple layers | One primary error log, preserving cause | Avoid repeating the same failure chain |

Log levels should match SLAs, operational requirements, and system expectations. For example, a normal 404 does not need a stack trace, whereas a 404 caused by unexpectedly missing system data may warrant investigation.

Do not rely solely on an exception's class name like `IllegalArgumentException` to automatically treat it as a client error; classify by **context**: this exception could be caused by a bug inside the service rather than HTTP input.

## 10. Logging completely once: what content is enough?

An error event at the boundary should include essential fields, depending on the system:

- **`operation`**: the operation that failed (`order.create`, `invoice.export`, `message.consume`).
- **`requestId` / `correlationId` / `traceId`**: links the event to a request or trace, taken from a trusted source.
- **`service`, `environment`, `version`**: where and in which build the error occurred (usually added by logging infrastructure).
- **`exception`**: the complete Throwable, with cause and suppressed exceptions, passed to the right logging API overload.
- **`errorCode` / `failureClass`**: an aggregatable error classification that does not depend on varying messages.
- **Actual outcome**: HTTP status, job status, retry exhausted, fallback used, dead-letter route if applicable.
- **Useful but safe details**: sanitized entity IDs, attempt count, duration, dependency name.

Do not put passwords, tokens, secrets, keys, cookies, or payloads containing personal data into logs. Exception messages from libraries sometimes already contain internal data; you need sanitization policies, access controls, and appropriate retention.

Example of a placeholder-based logging call (integration code, requires an SLF4J-compatible logger):

```java
logger.error(
        "operation={} requestId={} errorCode={} attempts={}",
        operation,
        requestId,
        errorCode,
        attempts,
        failure);
```

Here `failure` is a **Throwable**, not `failure.toString()` or `failure.getMessage()`. Converting only to a message string typically drops the stack trace, `Caused by`, `Suppressed`, and source line numbers. Some JSON logging systems have a dedicated field for exceptions; configure the encoder/appender to preserve this information instead of concatenating long strings manually.

### Correlation ID is not a unique key for counting errors

A single request can have **multiple independent failures** or contain multiple items; a single job can run multiple operations. If you want logical deduplication, design a key that distinguishes `operationId + failureClass + attempt/phase`, together with an event ownership mechanism. Never automatically drop all logs sharing the same `requestId`, as that can discard distinct information.

A useful variation is to track **a metric for total failed requests** at the boundary, leaving logs as the channel for investigation. Metrics should count final operations rather than counting `ERROR` log lines, which can change with configuration.

## 11. `Caused by` and `Suppressed` must be preserved across layers

When a layer wraps an exception using a constructor that takes `cause`, the runtime can print:

```text
java.lang.IllegalStateException: Không tạo được báo cáo
    at app.ReportService.export(ReportService.java:40)
Caused by: java.io.IOException: Hết dung lượng ổ đĩa
    at app.FileWriter.save(FileWriter.java:20)
    ... 1 more
```

This is an **illustrative** stack trace; line numbers are for demonstration only. `... 1 more` refers to matching frames at the bottom of the stack, not another exception.

If you use `try-with-resources`, a `close()` failure can appear under `Suppressed:`. A single logging point at the end with **the full Throwable** can preserve the outer message, cause, and suppressed exceptions. If each layer logs `e.getMessage()` on its own and drops the cause, you both create duplicates and lose critical data.

Logging once does not mean less information: **one complete stack trace with its cause/suppressed chain** is usually far more valuable than multiple disconnected error lines.

## 12. Avoiding duplicates when the framework or runtime already logs

In many frameworks, an unhandled exception can be logged by:

- The HTTP error handler or error dispatcher.
- The job scheduler, executor wrapper, or task framework.
- The consumer framework when a message handler throws an error.
- The container/application server when a request or task escapes.
- Telemetry/APM collectors that automatically generate exception events.

Therefore, you must **check the behavior of the error-handling path you are using**. If your global handler logs and then returns a normal response, the framework might not log the stack trace again; however, if the handler logs and then `throw`s for the framework to handle, duplicates can appear.

Common design approaches:

1. **Let the framework own it:** application layers add context and rethrow; the framework logs the error at the boundary if it has enough data.
2. **Application owns it:** a global handler logs and translates the error into the final result; avoid logging again in filters/controllers/services.
3. **Separate metrics/audit from error logs:** instrumentation can record metrics or span status without copying the entire stack trace.

You cannot pick the right approach from the technology name alone. You need to inspect the logger configuration, exception resolver, middleware code, and the actual logs of a controlled failing request.

## 13. When should an exception be logged multiple times?

There are situations with **different purposes or different boundaries** where multiple events make sense:

- Service A calls service B. B should log the failure of **B's own** operation; A can also log the failure of **A's own** request if A's contract fails. These are **two operations in two services**, even with the same technical root cause, and should be linked via trace/correlation IDs.
- A retry attempt has a `DEBUG` log explaining timing and backoff, while exhaustion produces a final `ERROR` log. These are **events with different meanings**, not repeating the exact same stack trace.
- A mandatory audit/security event is logged independently of the operation error; its structure, retention, and read permissions may differ.
- A recovered error emits a `WARN` about fallback; an independent piece of work later fails. They are not the same failure and should not be merged.

What to avoid is **copying the same exception stack with the same “operation failed” conclusion at consecutive layers**, without adding new information or owning a new outcome.

If there is a genuine reason to log before rethrowing, the message must clearly state the **distinct event** (for example, a separate rollback failure), its reason, and its severity. Do not turn an exception into one logged three times simply because three places have a `catch` block.

## 14. Transaction boundaries, rollback, and cleanup

An exception can cause a transaction to roll back or `close()` to fail. Not every error appearing in the same flow is a duplicate:

- **Primary error:** the business operation failed.
- **Rollback/cleanup error:** another system recovery step also failed, with its own consequences.
- **Suppressed exception:** Java can attach additional resource-closing failures to the primary Throwable.

At the boundary, log one sufficiently detailed event that preserves these branches. If cleanup creates **an independent incident** requiring separate alerting or intervention, you can log a separate event with a clear label, avoiding the same “request failed” phrasing as the primary error.

Design-pattern example (illustrative snippet, `cleanup` is application-defined):

```java
try {
    performOperation();
} catch (Exception primary) {
    try {
        cleanup();
    } catch (Exception cleanupFailure) {
        primary.addSuppressed(cleanupFailure);
    }
    throw primary;
}
```

The enclosing method must handle or declare `Exception`; this snippet is not standalone. `addSuppressed(...)` preserves the cleanup failure alongside the primary exception, allowing the responsible layer to log everything completely once. If `cleanupFailure` has separate consequences that require alerting, instrumentation can emit a metric or an event with a different meaning.

## 15. Logging, propagation, and `InterruptedException`

`InterruptedException` signals that **the current thread was requested to interrupt while waiting**, usually related to shutdown or task cancellation. You should not log an `ERROR` with a stack trace at every layer by default.

In a worker that wants to stop cooperatively (snippet placed inside a `Runnable` or appropriate method):

```java
try {
    queue.take();
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    return;
}
```

`queue` is a declared `BlockingQueue`. `Thread.currentThread().interrupt()` restores the interrupt flag because blocking wait operations typically clear the flag when throwing the exception. If this shutdown is **expected**, log at `DEBUG`/`INFO` or do not log; if it is an unexpected event, the worker boundary can log details after classification.

Do not catch a generic `Exception`, print the stack trace, and then continue an infinite loop: the wait operation may keep throwing repeatedly while the interrupt flag remains set, causing a log storm.

`CancellationException` from a cancelled `Future` is also usually a lifecycle signal, not automatically a business error. `ExecutionException` and `CompletionException` report failures of asynchronous tasks and typically contain a cause that needs classification.

## 16. Measuring and verifying that logs are not duplicated

How you test a logging change should be based on **a repeatable scenario**:

1. Trigger a request/job with a deterministic error, tagged with a unique `requestId`.
2. Verify the final outcome is correct: failure status or fallback, not just by glancing at the console.
3. Count **primary `ERROR` events for the operation** by `requestId` and event code. Normally you expect one event per operation failure.
4. Verify that the `Throwable` is printed completely with cause and suppressed exceptions when applicable, not just a message string.
5. Test retries as well: multiple attempts but only one `ERROR` log if it ultimately fails; if it succeeds, there should be no operation-failed conclusion.
6. Test async `get()`/`join()` and callbacks: avoid logging in both the callback and the boundary for the same failure.
7. Test a recovered error: a `WARN`/metric about fallback may appear, but no extra error event should be generated in the controller.
8. Check for PII/secrets and correlation IDs; ensure the centralized logging pipeline does not duplicate events itself.
9. Compare **the failed-operations metric** with the count of final error logs over the same time window; the two numbers do not have to be identical if sampling or multiple independent events exist, but large discrepancies need explanation.

In automated tests, you can use an in-memory appender of your logging framework to assert message/code, level, throwable, and event count at the boundary. **Do not match the entire stack trace character-by-character**, because line numbers, frame names, and JDK classes can change; what needs verification is ownership, cause, and primary log count.

### Distributed observability

A service may receive the same `requestId` across multiple hops. Attach `service`, `operation`, or span IDs to distinguish events from each hop. Log aggregation often provides grouping by trace ID; this does not replace controlling duplicates at the source.

## 17. Anti-patterns and how to fix them

### A. `catch` only to log and rethrow as-is

```java
try {
    repository.save(entity);
} catch (Exception e) {
    logger.error("save failed", e);
    throw e;
}
```

This is an integration snippet assuming `repository`, `entity`, and `logger` already exist. If this layer does nothing else, **remove the `catch`** or only wrap the error meaningfully according to the contract while preserving the cause. Let the boundary handle logging.

### B. Calling `printStackTrace()` alongside a logger

```java
e.printStackTrace();
logger.error("failed", e);
```

Both mechanisms can print the stack trace, causing duplicates across stdout/stderr and the logger. Choose the system's standard logging mechanism.

### C. Logging the message but dropping the Throwable

```java
logger.error("Request failed: {}", e.getMessage());
```

This can omit the stack trace, cause, and suppressed exceptions. At the place responsible for logging the error, pass **the exception object** to the right logger overload.

### D. Wrapping an error while cutting off the cause

```java
throw new IllegalStateException("Service failed");
```

If you are translating a caught exception, pass the cause: `new IllegalStateException("Service failed", e)`. Do not convert checked exceptions into bare messages and discard the causal chain.

### E. Retrying every error and logging every attempt

Retrying immutable data-validation errors can be pointless; logging `ERROR` on every attempt creates a log storm. Classify retryable errors, set attempt limits, timeouts/backoff, unify the operation ID, and log the conclusion at the end.

### F. Using a single log level for every exception

A valid 404 or a requested cancellation is not like a DB outage. Choose the level based on **operational impact** and outcome, not on the Java class name.

### G. Not defining an owner when using a global handler

The controller logs `ERROR`, the service logs `ERROR`, global advice also logs `ERROR`, and the container prints another stack trace. Clearly pick one place and check whether the framework logs by default.

### H. Hiding errors behind unmonitored fallbacks

If the service returns cached data instead of fresh data, the operation may succeed, but quality is degraded. Record a metric or `WARN` to track degraded mode without turning the request into an `ERROR`.

### I. Treating log lines as the unit of incident measurement

`ERROR` counts are easily skewed by configuration and duplication. Use metrics on **operation outcome**, request status, traces, and stable event codes; use logs to investigate root causes.

### J. Building overly broad deduplication keys

If you deduplicate per `requestId`, you can swallow independent errors within the same request. Design event identity around **operation/failure phase/service**, rather than treating every Throwable sharing a correlation ID as one error.

## 18. Decision table when reviewing a `catch`

| Situation in `catch` | Usually right action | Log stack trace here? |
|---|---|---|
| Cannot handle; rethrowing original error | Propagate | Usually **no** |
| Translating technical error into contextual exception | Wrap exception preserving cause, rethrow | Usually **no** |
| Successfully recovered via fallback | Return fallback data/response, update metric | Maybe `WARN`/`INFO`, not necessarily full stack |
| Retries exhausted and operation failed | Throw to boundary or handle at the boundary itself | **Yes**, one final error event |
| HTTP handler deciding final response | Classify, log event if no other owner exists | Possibly **yes** |
| Worker interrupted for shutdown | Restore flag / exit per contract | Usually not `ERROR` |
| Cleanup also failed | Attach as suppressed, evaluate independent impact | Only separate log if independently meaningful |
| Audit required by policy | Log structured audit event | Per policy; distinct from error log |

**Key takeaway:** A Throwable can pass through many `catch` blocks, but not every `catch` needs a log. Intermediate layers preserve **cause and context**, recovery layers record **what was handled**, and the boundary owning the failed outcome logs **one rich primary event**. Clear ownership keeps logs sufficient for investigation while accurately reflecting the number of operations that truly failed.
