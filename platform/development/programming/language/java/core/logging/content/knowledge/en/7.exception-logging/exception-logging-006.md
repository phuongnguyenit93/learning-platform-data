# Log Once or Multiple Times When Handling Exceptions in Java?

## 1. Why Can One Exception Produce Multiple Log Lines?

A call in a Java system typically traverses multiple layers: controller → service → repository → external library or service. When an operation fails, an exception may be thrown from a lower layer, caught to add context in a middle layer, and then propagated to an outer handling layer.

For example, if the database does not respond, the repository throws `SQLException`, the service converts it into `OrderSaveException`, and the API returns an HTTP 500 error. If all three layers log `ERROR` with the same stack trace, an operator may see three "errors" even though in reality only **a single request-handling execution failed**.

```text
Repository: ERROR database unavailable      ← same incident
Service:    ERROR cannot save order ORD-7    ← same incident
Controller: ERROR request req-42 failed      ← same incident
```

These lines are an **illustrative scenario**. The harm of duplicate logging goes beyond storage cost: it increases noise, triggers duplicate alerts, makes it hard to count failed requests accurately, and misleads readers into thinking multiple independent incidents occurred.

**A useful default rule: for each logical failure, choose one place responsible for writing an error record with full context and the exception.** Intermediate layers should propagate, translate, or handle the exception according to their responsibility. This rule does not forbid multiple records when there are **multiple distinct events** (each retry, compensation step, recovery, or business state); what matters is distinguishing *duplicate records of the same error* from *distinct milestones during processing*.

## 2. Distinguishing Exception, Event, and Logical Failure

Three related but non-identical concepts:

- **Exception:** an object signaling an abnormal condition at a point in the execution flow. One exception can pass through multiple layers without becoming multiple incidents.
- **Log event:** something the application intentionally records, such as `payment_attempt_failed`, `retry_scheduled`, `order_request_failed`, or `recovery_succeeded`.
- **Logical failure:** the unit of work we want to track, such as an HTTP request, a job, or a message-processing execution from a queue. This unit may involve multiple attempts, multiple internal exceptions, and a final outcome.

Example:

```text
Request req-42
  ├─ attempt 1 → timeout → will retry
  ├─ attempt 2 → timeout → will retry
  └─ attempt 3 → succeeded
Request result: SUCCESS
```

The two timeouts are two **failed attempt events**, but the request **did not ultimately fail**. If every retry is logged as `ERROR` with the same stack trace, the system may be misread as experiencing a severe incident even though it recovered normally.

Conversely:

```text
Request req-43
  ├─ attempt 1 → timeout → retry
  ├─ attempt 2 → timeout → retry
  └─ attempt 3 → timeout → retries exhausted
Request result: FAILED
```

In the second scenario, you can log retry milestones at an appropriate detail level and then log **one final failure event** with the root exception/cause chain. Retries in critical systems may warrant a separate log per attempt, but each log must have a clear reason and context.

## 3. How to Choose Where to Log: Who Owns the Final Decision?

You should usually log an exception **at the boundary where the error is handled or the outcome of the unit of work is determined**. For example:

| Boundary | Typical action | When to log the exception? |
|---|---|---|
| Repository/adapter | Call DB, filesystem, HTTP, message broker | Usually rethrow or translate to an exception with context; avoid logging the same error if an upper layer will log it |
| Service | Apply business logic, retry, fallback | Log retry/fallback events if useful; if unable to handle, propagate the exception so the outer layer logs the final error |
| HTTP controller / exception handler | Decide the HTTP response | Can log an unexpected request error once with `requestId` and the exception, then build a safe response |
| Scheduled job / background worker | Decide the job status | Log the final failure or processing result once, with `jobId` |
| Message consumer | Process message, choose ack/nack/requeue | Log where the final outcome of the processing attempt is decided, with `messageId`/`attempt` |
| Handler that catches and recovers in place | Catch the exception and genuinely continue with a fallback | Can log an appropriate recovery event, depending on importance |

**Where an exception is thrown is not necessarily the best place to log it.** A lower layer often does not know the full `requestId`, business impact, or whether the caller has a fallback. An outer layer, on the other hand, may miss error details if a middle layer drops the `cause`. A generally effective collaboration pattern is: **lower layers preserve the cause; the outer layer logs one context-rich error record**.

Do not mechanically apply "always log in the controller": CLI programs, batch jobs, consumers, desktop applications, and background services have different handling boundaries. Identify **the owner responsible for the outcome of the unit of work**.

## 4. Anti-Pattern: Catch, Log, and Rethrow at Every Layer

Suppose the application uses SLF4J:

```java
// Repository: the same exception is logged and rethrown
try {
    writeToDatabase(order);
} catch (SQLException error) {
    log.error("Database write failed", error);
    throw error;
}

// Service: logs the same incident again and rethrows
try {
    repository.save(order);
} catch (SQLException error) {
    log.error("Cannot save order {}", order.id(), error);
    throw new OrderSaveException("Order save failed", error);
}

// API handler: logs the exception again when the request fails
log.error("Request {} failed", requestId, error);
```

These are **three illustrative snippets from different layers**, not a standalone Java program. If all three run along the same error path, the logs will repeat the same root cause.

The issue is not whether the messages match character-for-character; the messages may differ and still describe **the same logical failure**. The stack traces logged at the repository, service, and API layers may share the exact same root cause.

A more sensible fix:

```java
// Repository: let the exception propagate; do not log the same error.
writeToDatabase(order);

// Service: translate the error type to reflect the domain, preserving the cause.
try {
    repository.save(order);
} catch (SQLException error) {
    throw new OrderSaveException(
            "Cannot save order " + order.id(), error);
}

// API boundary: log exactly once when the request is known to have failed.
log.error("requestId={} event=order_save_failed orderId={}",
        requestId, order.id(), error);
```

**Syntax note:** the snippet above assumes the SLF4J API, and that `repository`, `OrderSaveException`, `order`, and the variable `error` exist in their respective scopes; it is a code-organization sketch. A runnable JUL example is in Section 7.

After converting `SQLException` into `OrderSaveException`, use a constructor that stores `cause`. Do not throw `new OrderSaveException("Cannot save order")` and discard the original exception. When logging at the boundary, the full stack trace/cause chain remains intact for diagnosis.

### 4.1. Three Choices in Every `catch` Block

For a caught exception, explicitly choose one of the main paths:

1. **Handled and continue:** log a fallback/recovery event if truly needed. Do not rethrow the same error.
2. **Cannot handle:** propagate the exception or translate it into an appropriate exception type, **preserving `cause`**. Let the layer that owns the outcome log the final error record.
3. **Convert into an intentional outcome:** for example, return an expected business error response, or mark a job as failed. Decide the log level and location based on actual impact; do not default user errors to `SEVERE`.

Merely "logging" **is not the same as handling an error**. If the application must roll back, return a failure status, retry, or cancel a task, those actions still need to be performed.

## 5. When Should You Write Multiple Log Records?

There are cases where **multiple logs are right** because they record *genuinely different events*:

### 5.1. Retries

Attempts have distinct `attempt` values. An `attempt_failed` or `retry_scheduled` record shows that the system is recovering. Suggested guideline:

- Expected and frequent retries: can be logged at `DEBUG`/`FINE` or aggregated via metrics.
- Rare retries that affect latency or indicate a degraded dependency: `WARN`/`WARNING` may be appropriate.
- Retries exhausted and the request/job ultimately fails: log one final error event with the `Throwable`/cause chain at the appropriate boundary.

There is no mandatory level-mapping table for every application. If you log a warning for each attempt, include `attempt`, `maxAttempts`, `dependency`, and `requestId` to show these are distinct attempts rather than duplicate error records.

### 5.2. Fallback and Recovery

For example, calling a payment API fails and the system switches to a backup:

```text
WARN  requestId=req-42 event=primary_provider_unavailable provider=A
INFO  requestId=req-42 event=fallback_succeeded provider=B
```

These are two distinct states: the primary dependency encountered an issue, and the fallback mechanism succeeded. If the transaction still succeeds overall, you should not automatically log an extra `ERROR request failed`.

### 5.3. Compensation and Rollback Steps

An operation may fail and then trigger a refund, inventory reservation release, or data compensation. The primary error and the **compensation result** are two independent events with operational significance. Both may need separate logs; if compensation also fails, that is a **new incident** with its own cause and severity.

### 5.4. Service Boundaries and Different Units of Work

In a distributed system, service A calls service B and receives an error. B may log that **the request at B** failed; A may log that **the business operation at A** failed. The two services own different units of work, so sometimes both logs are necessary. Use `traceId`/`requestId`, structured errors, and policies that avoid useless stack-trace duplication.

"Log once" is a **design rule for a single logical failure unit**, not a guarantee that the entire distributed system will emit only one record. Collectors can also receive duplicates due to forwarding or resend mechanisms.

### 5.5. Audit and Security

A security or business event that requires auditing may need a dedicated record alongside diagnostic error logs. Audit trails have specific requirements for integrity, access control, retention, and legal accountability. Do not use "log only once" as an excuse to drop required audit evidence.

## 6. When Should You NOT Log More?

### 6.1. Catching Only to Add a Sentence and Rethrow

```java
catch (IOException error) {
    log.error("Read config failed", error);
    throw error;
}
```

If an upper layer is guaranteed to log the final error with full context, that `log.error` line is usually redundant. Instead, let the exception propagate or throw a specialized exception with `cause`. If this layer is the only place holding important information (such as a resource path), add that information to the exception type or a safe message so the outer layer can see it.

### 6.2. Logging the Exception and Calling `printStackTrace()`

```java
catch (Exception error) {
    log.error("Operation failed", error);
    error.printStackTrace();
}
```

With many backends, both the logger and `printStackTrace()` output the stack trace, which can cause duplicate records and break structured formatting. Choose a single logging mechanism configured to fit your logging system; do not print extra stack traces out of habit.

### 6.3. One Error, Multiple Handlers/Appenders Writing Together

Not all duplicate lines come from multiple `catch` blocks. In JUL, a record can reach both a logger's attached handler and parent handlers if `useParentHandlers` is enabled. In Logback/Log4j 2, additivity or multiple appenders pointing to the same destination can also cause duplicates.

For example: a single `LOG.log(Level.SEVERE, ..., error)` call appears twice on the console. In that case, **check propagation, handlers, appenders, and collector configuration** rather than hastily deleting valuable business messages.

### 6.4. Errors Handled as Designed

For example, a user enters an invalid email or searches for a non-existent resource as a normal API outcome. You may need to return HTTP 400/404 and metrics, but **do not automatically treat every such case as a severe exception requiring an ERROR-level stack trace**. Log levels should reflect abnormality and operational impact.

## 7. Standalone Java 17+ Example: Log One Final Error, Multiple Events on Retry

This example uses the JDK's **`java.util.logging`**, requiring no external dependencies. There are two scenarios:

1. Saving an order fails in the repository layer; the service layer **wraps the exception and preserves the cause**; only the orchestration layer logs the final error.
2. A job fails on the first attempt, schedules a retry, and succeeds on the second attempt; it logs **two meaningfully different events**, without emitting a false `SEVERE` for a recovered job.

### 7.1. Source Code

Create `LogOnceOrManyDemo.java`:

```java
import java.util.logging.ConsoleHandler;
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class LogOnceOrManyDemo {
    private static final Logger LOG =
            Logger.getLogger(LogOnceOrManyDemo.class.getName());

    public static void main(String[] args) {
        configureLogger();
        processRequest();
        executeRetriedJob();
    }

    private static void configureLogger() {
        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.INFO);

        ConsoleHandler console = new ConsoleHandler();
        console.setLevel(Level.INFO);
        console.setFormatter(new Formatter() {
            @Override
            public String format(LogRecord record) {
                String text = record.getLevel().getName()
                        + " " + formatMessage(record);

                Throwable error = record.getThrown();
                if (error != null) {
                    text += " | exception="
                            + error.getClass().getSimpleName()
                            + ":" + error.getMessage();

                    if (error.getCause() != null) {
                        Throwable cause = error.getCause();
                        text += " | cause="
                                + cause.getClass().getSimpleName()
                                + ":" + cause.getMessage();
                    }
                }
                return text + System.lineSeparator();
            }
        });
        LOG.addHandler(console);
    }

    private static void processRequest() {
        try {
            saveOrder("ORD-7");
        } catch (OrderSaveException error) {
            // A single final log at the request-handling boundary.
            LOG.log(Level.SEVERE,
                    "requestId=req-42 orderId=ORD-7 event=order_save_failed",
                    error);
        }
    }

    private static void saveOrder(String orderId) {
        try {
            simulateDatabaseWrite();
        } catch (IllegalStateException cause) {
            // Preserve the cause and add context; do not duplicate the log.
            throw new OrderSaveException(
                    "cannot save " + orderId, cause);
        }
    }

    private static void simulateDatabaseWrite() {
        throw new IllegalStateException("database unavailable");
    }

    private static void executeRetriedJob() {
        for (int attempt = 1; attempt <= 2; attempt++) {
            try {
                performAttempt(attempt);
                LOG.info("jobId=job-9 event=job_completed attempt="
                        + attempt);
                return;
            } catch (IllegalStateException error) {
                if (attempt < 2) {
                    LOG.warning(
                            "jobId=job-9 event=retry_scheduled attempt="
                            + attempt + " reason=temporary_timeout");
                } else {
                    // Log SEVERE only if all attempts fail.
                    LOG.log(Level.SEVERE,
                            "jobId=job-9 event=job_failed attempts="
                            + attempt, error);
                }
            }
        }
    }

    private static void performAttempt(int attempt) {
        if (attempt == 1) {
            throw new IllegalStateException("temporary timeout");
        }
    }

    private static final class OrderSaveException
            extends RuntimeException {
        private OrderSaveException(String message, Throwable cause) {
            super(message, cause);
        }
    }
}
```

Compile and run with **JDK 17 or later** in the directory containing the file:

```bash
javac -encoding UTF-8 LogOnceOrManyDemo.java
java LogOnceOrManyDemo
```

Exact output according to the configured formatter:

```text
SEVERE requestId=req-42 orderId=ORD-7 event=order_save_failed | exception=OrderSaveException:cannot save ORD-7 | cause=IllegalStateException:database unavailable
WARNING jobId=job-9 event=retry_scheduled attempt=1 reason=temporary_timeout
INFO jobId=job-9 event=job_completed attempt=2
```

**Stream note:** JUL's `ConsoleHandler` writes to **stderr** by default, so the example produces no stdout. The output above is the three lines displayed on the console (stderr); if redirecting the two streams separately, read stderr.

### 7.2. Why Is the Output Correct?

- `simulateDatabaseWrite()` throws `IllegalStateException`, but this method **does not log**.
- `saveOrder(...)` catches the error and throws `OrderSaveException` with `cause`, still **without logging**.
- `processRequest()` knows the request failed, so it logs **one** `order_save_failed` event at `SEVERE` with the request ID and order ID.
- The demo formatter reads `record.getThrown()` and displays the exception + cause on a single line. Because the output has no dynamic timestamps or stack traces, it can be compared deterministically.
- `executeRetriedJob()` hits one failed attempt, logs `WARNING retry_scheduled`, then completes on the second attempt and logs `INFO job_completed`. These are **two distinct events**. No `SEVERE job_failed` is logged because the job succeeded.
- If you modify the simulation so both attempts fail, the `else` branch logs **one final `SEVERE`** and does not mark the work as succeeded.

**Limitation of the demo formatter:** it only prints the exception type, message, and direct cause to keep stdout/stderr deterministic. In real operations, you need a formatter/backend capable of recording **full stack traces, nested causes, and suppressed exceptions** where appropriate. The demo code illustrates *which layer decides to log*, not a complete production configuration.

## 8. Logging Exceptions Properly in JUL, SLF4J, and Other Backends

### 8.1. Java Util Logging (JUL)

With JUL, to attach the exception alongside the message, use the overload that accepts `Throwable`:

```java
LOG.log(Level.SEVERE, "event=order_save_failed", error);
```

If you use `LOG.severe(error.getMessage())`, the application only passes the message, not the `Throwable` object, to the logger. The formatter may have no stack trace/cause to output.

If you need **both `{0}` parameters and a Throwable**, you can create a `LogRecord` with `parameters` and `thrown`:

```java
LogRecord record = new LogRecord(
        Level.SEVERE, "requestId={0} event=order_failed");
record.setParameters(new Object[]{"req-42"});
record.setThrown(error);
LOG.log(record);
```

The snippets in this section are **API illustrations** assuming `LOG` and `error` are already declared in scope, not standalone programs. A formatter needs `formatMessage(record)` to substitute `{0}` and support for `record.getThrown()` to include the exception.

### 8.2. SLF4J/Logback

In applications with SLF4J, the common pattern is:

```java
log.error("requestId={} orderId={} event=order_save_failed",
        requestId, orderId, error);
```

A trailing `Throwable` argument is treated by the SLF4J API as the exception in standard parameterized logging overloads. A working provider/backend and a layout that prints `Throwable` are required; do not assume SLF4J's `{}` placeholder works identically to JUL's `{0}`.

The example below logs only the error message and can lose the stack trace:

```java
log.error("Save failed: {}", error.getMessage());
```

If the logger is at ERROR level but the layout/encoder does not print throwables, the stack trace can still be missing even when the call passes the exception object. Check the **call site**, backend configuration, and formatter together.

### 8.3. Log4j 2

Log4j 2 also provides exception-logging overloads and its own patterns/layouts. How a `Throwable` is attached can depend on the `Message` type and overload. Use the exact API for your running version, pass the exception with the right type, and verify the output. Do not mechanically copy additivity or throwable converter configurations across JUL, Logback, and Log4j 2.

### 8.4. Logging Once Does Not Mean Dropping Information

A final record should contain **sufficient context**:

- Stable event name: `event=order_save_failed`.
- Work identifiers: `requestId`, `jobId`, `messageId`, or `traceId`.
- Non-sensitive business identifiers: `orderId`, error code, involved component.
- Exception type, appropriate message, and stack trace/cause chain when needed.
- Impact: request failed, retry succeeded, data rolled back, or task pending.

**You do not need to log every piece of data at every layer.** Context can be propagated via specialized exceptions, result structures, tracing, or controlled MDC. The logger at the boundary is responsible for assembling the information and emitting the necessary record.

## 9. When Exceptions Are Handled and Recovered

Suppose a repository throws a transient error, but the service can use a cache:

```java
try {
    return remoteCatalog.load(productId);
} catch (RemoteServiceException error) {
    log.warn("productId={} event=using_cached_catalog",
            productId);
    return catalogCache.get(productId);
}
```

This snippet is **illustrative** and not standalone; it assumes a valid cache and a business-approved fallback. It records the milestone that the application had to use the cache; do not emit `ERROR` or return a failure result when the fallback succeeds.

If the fallback itself throws an exception, that is **a new failure or a new step within the same request** that must be handled. Depending on the domain, you can keep both the original cause and the fallback error in cause/suppressed exceptions so the sequence of events is not lost. Do not log both errors at every layer just to "make sure there is a log."

Also distinguish **expected errors in business flows** from **unexpected technical exceptions**. For instance, `ItemNotFoundException` may normally lead to HTTP 404 without needing a SEVERE stack trace; by contrast, a lost database connection typically requires operational investigation.

## 10. With Concurrency and Asynchronous Processing

In multithreaded applications, "the final handling site" is not necessarily on the same call stack as where the error originated:

- With `ExecutorService`/`Future`, a task error may be stored in the `Future` and surfaced when `get()` is called. Choose the place managing the task to log the error and update state; avoid having the task log and the caller log again upon catching `ExecutionException`.
- With `CompletableFuture`, if `exceptionally`, `whenComplete`, and the code calling `join()` all log the same failure, log volume multiplies. Clearly assign which callback or boundary owns the final error.
- With scheduled jobs, a thread's uncaught exception handler or the framework may log errors automatically. When adding application logs, check the default logs to avoid duplicates.
- With message consumers, retry/redelivery can cause **the same message** to be processed again. Log the attempt ID and message ID, combine with idempotency and metrics, and do not infer unique message counts from log line counts.

`requestId`/`traceId` fields are especially helpful when multiple threads interleave. MDC/thread context must be propagated and cleared properly when using thread pools. Logging once in application code also **does not guarantee exactly-once delivery** in a log collection pipeline.

## 11. Log Levels, Alerts, and Performance

### 11.1. Choosing Levels by Outcome

| Scenario | Reference level | Why |
|---|---|---|
| Unexpected request/job failure, unrecovered | `ERROR` / JUL `SEVERE` | Needs investigation of cause and impact |
| One attempt failed, but retry may resolve it | `DEBUG`/`FINE` or `WARN`/`WARNING` | Depending on frequency and operational value; include attempt context |
| Valid fallback was used | `INFO` or `WARN`/`WARNING` | Indicates degraded state, not necessarily a final failure |
| User input invalid per business rules | `INFO`/`DEBUG` or do not log | Not necessarily a system incident |
| Security incident requiring an audit trail | Per security/audit policy | May need a dedicated audit channel with its own schema and retention |

There is no universal level table that applies automatically to every business domain. JUL's `SEVERE` is close in meaning to `ERROR` in many backends, but they do not share the same name and are not always equivalent across all configurations.

### 11.2. Do Not Use ERROR Line Counts to Infer True Error Counts

If one failure is logged three times, a monitoring system counting every line will report three times as many errors. Conversely, sampling or log filtering can make the line count **lower** than the actual number of errors.

When measuring error rates or SLOs, use **metrics** at clear measurement points (such as one HTTP request outcome or one job completion) rather than simply counting `ERROR` events. Logs provide details for investigation; traces link steps across the same request.

### 11.3. Do Not Log Stack Traces for Every Attempt

Long stack traces consume CPU, memory, bandwidth, and storage. For high-frequency retries, you can log one summary record with the attempt count, dependency, duration, and final exception, while keeping per-attempt details at debug level or in appropriately labeled metrics.

Do not strip away important technical causes just to shrink logs. Keep **enough evidence to investigate real incidents** while avoiding duplicating the same stack trace. When using sampling, ensure critical alerts and mandatory audit records are not dropped outside policy.

## 12. Security and Investigability

Passing an exception to a logger can accidentally expose **exception messages containing sensitive data** in logs. Messages from HTTP clients, JDBC, or other libraries sometimes include URL query strings, personal identifiers, or portions of input data. Do not automatically log full request bodies, access tokens, passwords, session cookies, SQL parameters, or responses containing personal information.

Business fields like `orderId` can aid investigation, but access-control policies and retention periods must be considered. For untrusted input, sanitize newline/control characters to prevent log injection, and use a JSON encoder that ensures proper escaping when needed.

If you write a custom formatter, decide how `Throwable` is rendered: error type, message, stack trace, cause chain, and suppressed exceptions. A formatter that only outputs `error.getMessage()` can both leak data and omit useful diagnostic evidence.

## 13. Common Mistakes and How to Spot Them

| Symptom | Likely cause | How to fix |
|---|---|---|
| One failed request has 3–4 nearly identical stack traces | Multiple `catch` layers logging and rethrowing | Choose a boundary to log the final error; propagate `cause` in middle layers |
| One logger call produces two identical lines | Parent handlers/appenders or collector duplication | Check propagation/additivity, destinations, and pipeline |
| Error disappears after service wraps the exception | Wrapper drops `cause`, or outer handler drops `Throwable` | Use a constructor with `cause`, pass `Throwable`, check formatter |
| Logs show ERROR, but API returns success | Retry/fallback recovered | Use levels and events that reflect attempt/recovery |
| Retries happen, but attempt count is missing | Missing `attempt`, `maxAttempts`, or metric | Log attempt context or aggregate at the boundary |
| One failure triggers multiple alerts and wrong error counts | Alerts count duplicated logs | Count metrics per unit of work and reduce duplicate logs |
| Error is logged, yet the task is still treated as succeeded | Caught, logged, and ignored | Handle status, return error, rollback/retry/propagate appropriately |
| Error appears twice through async callbacks | Multiple observers on the same `Future`/`CompletionStage` | Assign where to log and where to only propagate/return the result |
| Cannot correlate logs across services | Missing `requestId`/`traceId` | Propagate correlation IDs properly and use structured fields |

### Self-Check Exercise

A payment request makes three attempts: the first two time out, and the third succeeds. In the HTTP handler layer, a developer also logs `ERROR` when catching two timeout exceptions that were already handled by the service.

Determine:

1. What is the final outcome of the **request**?
2. Should the two timeouts be counted as **two failed requests**?
3. If you want to know what each attempt did, which fields should you add?
4. Where should the final error be logged if all three attempts fail?
5. If both the service and the handler emit the same stack trace, how do you reduce duplicate logs while preserving the cause?

**Check hints:** the request ultimately succeeded, so there is no final request failure. The two timeouts are failed attempt events that can be tracked with `attempt` and `requestId` at an appropriate level. If retries are exhausted, the owner of the request or job outcome logs one final error record with `Throwable`; lower layers propagate the cause and context.

## 14. Per-Exception Decision Checklist

Before adding `logger.error(...)` or `LOG.log(Level.SEVERE, ...)`, check:

1. **Has the error already been handled?** If not, should the current layer propagate or wrap it with `cause` instead of logging?
2. **Is this an attempt or a final failure?** If retrying, name the event and set the level appropriately for an attempt.
3. **Who owns the outcome of the unit of work?** HTTP boundary, consumer, job runner, or a function with a fallback?
4. **Has another logger/framework already logged the same failure?** Check catch/rethrow paths, exception handlers, appenders, and collectors.
5. **Does this record add new information?** If it only repeats a stack trace, it can usually be omitted; if it is an independent event, log it with its own context.
6. **Is the original exception preserved?** Pass `Throwable`, the cause chain, and the stack trace when appropriate.
7. **Are there enough identifiers to correlate?** `requestId`, `jobId`, `attempt`, `traceId`, and event name.
8. **Are there security or cost implications?** Avoid sensitive data, log flooding, and false alerts.

**Practical rule:** for **one logical failure**, usually log **one final error record** where there is sufficient context and responsibility for handling the outcome; other layers propagate or handle the exception. When there are retries, fallbacks, rollbacks, compensations, audits, or independent units of work, **multiple records can be correct** because they describe different events. Log quality is judged by how well it explains what happened and helps investigate root causes—not by how many times the same stack trace is printed.
