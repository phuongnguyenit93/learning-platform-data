# Exceptions and Log Levels in Java

## 1. Mental Model: An Exception Does Not Automatically Mean ERROR

In Java, an **exception** is a mechanism for signaling a situation that interrupts the normal flow of execution. A **log level** is how an application describes the significance of an event to operators. The two concepts are related, but they are not equivalent.

For example, consider the same `IOException` when reading a file:

- A **required** configuration file cannot be read at startup, preventing the application from running: a critical failure, typically requiring `SEVERE` in `java.util.logging` or `ERROR` in SLF4J.
- An **optional** file does not exist and the application applies default values as designed: can be logged at `INFO`, `FINE`, or not logged at all.
- A file is temporarily unreadable, the application performs a controlled retry, and a recovery path is in place: `WARNING` or lower depending on how abnormal it is and operational policy.

It is the same **exception type**, yet the business impact differs. Conversely, a business condition that throws no exception (for instance, a data state violating a critical invariant) may still need to be logged at `SEVERE`.

**Core principle:** choose the log level based on *what happened, whether it was expected, what the impact is, whether it is recoverable, and whether anyone needs to take action*. Do not pick a level solely by the exception class name or simply because code entered a `catch` block.

Three separate questions should be distinguished:

1. **How should the exception be handled?** Recover, return a result, retry, translate into another exception, or rethrow?
2. **What event should be logged?** Is there enough diagnostic information, context identifiers, and cause?
3. **At what level and at which boundary should it be logged?** Who is responsible for concluding on the outcome and avoiding duplicate logs?

Logging provides observability; it **does not catch or handle exceptions in place of `try/catch`**. Calling `logger.log(Level.SEVERE, ...)` does not by itself stop the program, roll back a transaction, or return HTTP 500.

## 2. Exception Categories and Log Levels

In Java, `Throwable` is the superclass of `Exception` and `Error`. Common categories include:

| Category | Examples | What to Understand |
| --- | --- | --- |
| Checked exception | `IOException`, `SQLException` | The compiler requires catching or declaring `throws` where applicable; not severe by default |
| Unchecked exception | `IllegalArgumentException`, `IllegalStateException`, `NullPointerException` | Not required to be declared with `throws`; log level still depends on context |
| `Error` | `OutOfMemoryError`, `StackOverflowError` | Usually signals a serious JVM/infrastructure-level issue; normal business flows should not be designed around catching and continuing |
| Custom business exception | `OrderAlreadyCancelledException`, `CreditLimitExceededException` | May represent an expected outcome; whether to log and at what level is a business/operational decision |

For example, an `IllegalArgumentException` caused by a user submitting a recognized invalid option that returns a proper 400 response may be a normal situation. However, an `IllegalArgumentException` caused by internal code passing invalid arguments and corrupting an important transaction may be a critical bug. There is no rule that `RuntimeException == ERROR` or `checked Exception == WARNING`.

A log record is also not an exception. In JUL, a `LogRecord` can carry a message, a log level, and a **reference to a `Throwable`** via `getThrown()`. An `INFO` record can certainly have no exception, and a `SEVERE` record can describe an error condition without a specific `Throwable` object.

## 3. Log Levels in Java: Using the Right API Names

### JDK `java.util.logging` (JUL)

Common levels, ordered from highest severity/notability to detailed diagnostic information:

| JUL | Common Practical Meaning | Examples |
| --- | --- | --- |
| `SEVERE` | Serious failure; an operation/service did not complete or cannot safely continue | Retries exhausted and business operation failed; required resource failed to open at startup |
| `WARNING` | Anomaly requiring attention; the system can recover/is degraded or needs monitoring | System fell back to a secondary path; a downstream service temporarily lost connection |
| `INFO` | Notable operational/business event occurring within normal flow | An invalid request is rejected according to business rules |
| `CONFIG` | Configuration information | Enabling/disabling a feature or confirming non-sensitive configuration values |
| `FINE`, `FINER`, `FINEST` | Increasingly detailed diagnostic information | An internal check step, state used for investigation |
| `OFF`, `ALL` | Special levels for enabling/disabling filter thresholds | `ALL` is not a level representing an incident |

In JUL, **there are no `Level.ERROR`, `Level.WARN`, or `Level.DEBUG` constants**. To log a serious error with JUL, use `Level.SEVERE`. Names and exact semantics may differ across logging frameworks.

### SLF4J with Logback or Compatible Implementations

The standard SLF4J API levels are `ERROR`, `WARN`, `INFO`, `DEBUG`, and `TRACE`. Typically:

- `ERROR`: an important operation failed and requires investigation or action.
- `WARN`: an anomaly that could affect the system, potentially still recoverable.
- `INFO`: normal progress that is meaningful to operations.
- `DEBUG`, `TRACE`: technical details for investigation.

These are **operational conventions**, not a Java standard forcing every application to use identical levels. Some frameworks such as Log4j 2 also support `FATAL`, though you should not assume every API provides that level.

**Do not equate level values across frameworks.** The JUL pattern `LOG.log(Level.SEVERE, "...", e)` serves a similar role to `LOG.error("...", e)` in SLF4J, but configuration, filtering thresholds, formatting, and APIs differ.

## 4. How to Decide the Level When an Exception Occurs

Ask these questions in order:

1. **Is the situation expected in the workflow?** For example, invalid user input, insufficient credit limit, or cancelling an already completed request may be normal outcomes.
2. **Did the business step complete as committed?** If not, it is a failure that needs clear classification.
3. **Did the system recover successfully?** Was there a fallback, retry, or alternative path that preserved the request?
4. **What is the impact and scope?** Missing optional data is very different from losing the core database.
5. **Who needs to react to this log?** If alerts trigger on error levels, logging `ERROR` for expected cases creates alert noise.
6. **Has the event already been logged elsewhere?** An exception propagating through multiple layers should not produce multiple identical `ERROR` lines.

A reference decision table:

| Situation | Handling | Usually Appropriate Level | Notes |
| --- | --- | --- | --- |
| Invalid input with a designed error response returned | Valid rejection | `INFO`/`FINE` or do not log | Do not log stack traces for routine user errors |
| Expired card, insufficient balance | Expected business decision | `INFO` if tracking is needed | Use a stable `reason_code` |
| Cache failed, but direct DB read succeeded | Recovered via fallback | `WARNING` when this signals an anomaly | May use DEBUG/metrics only if very frequent and measured separately |
| Gateway call timed out once, retry scheduled | Not yet a final failure | `WARNING` or `INFO` depending on abnormality | Include attempt/operation id; avoid alerting on every minor retry |
| Gateway exhausted all retries, payment request failed | Unrecoverable | `SEVERE` / `ERROR` at the decision point | Log once with root cause and correlation id |
| **Optional** config file not found, defaults used | Continues per policy | `INFO`/`CONFIG`/`FINE` | Do not assume `FileNotFoundException` is always ERROR |
| **Required** config cannot be read, startup aborted | Cannot serve | `SEVERE` / `ERROR` | Typically an error requiring intervention |
| Request cancelled by user or graceful shutdown | Expected termination | `FINE`/`INFO` or do not log | Be especially careful with `InterruptedException` |
| Logic bug causing loss of an important task's result | Unexpected failure | `SEVERE` / `ERROR` | Preserve the exception and sufficient context to debug |

These recommendations should be tuned to your SLAs, event volume, and alerting rules. A rare exception that is fully handled might still warrant `WARNING`; a retry in a normal mechanism occurring very frequently might only need `FINE` plus an aggregated metric.

## 5. Runnable Java 17+ Example: INFO, WARNING, SEVERE with Throwable

This program demonstrates three scenarios so you can clearly observe how they differ:

- An order missing an ID is **rejected by rule**: logs `INFO`, without creating a pointless exception.
- A simulated payment gateway times out but will be retried: logs `WARNING` with an attached `IOException`.
- A required invoice store fails and the task cannot complete: logs `SEVERE` with an `IllegalStateException`.

The program uses JDK `java.util.logging`; to keep the output concise and deterministic, the formatter prints only the exception class and message. **`LogRecord` still carries the `Throwable`**, though this formatter **does not print the full stack trace**. A later section shows how to print full details when investigating real issues.

Create **`ExceptionLogLevelDemo.java`** with the following content:

```java
import java.io.IOException;
import java.util.logging.ConsoleHandler;
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class ExceptionLogLevelDemo {
    private static final Logger LOG =
            Logger.getLogger(ExceptionLogLevelDemo.class.getName());

    private ExceptionLogLevelDemo() {
    }

    private static void setupLogging() {
        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.INFO);

        ConsoleHandler handler = new ConsoleHandler();
        handler.setLevel(Level.INFO);
        handler.setFormatter(new Formatter() {
            @Override
            public String format(LogRecord record) {
                String result = record.getLevel().getName()
                        + " " + formatMessage(record);
                Throwable cause = record.getThrown();
                if (cause != null) {
                    result += " exception="
                            + cause.getClass().getSimpleName()
                            + " detail=" + cause.getMessage();
                }
                return result + System.lineSeparator();
            }
        });
        LOG.addHandler(handler);
    }

    private static void rejectInvalidOrder() {
        LOG.info("event=order_rejected reason_code=EMPTY_ORDER_ID");
    }

    private static void schedulePaymentRetry() {
        try {
            throw new IOException("gateway timeout");
        } catch (IOException e) {
            LOG.log(Level.WARNING,
                    "event=payment_gateway_timeout action=retry_scheduled",
                    e);
        }
    }

    private static void failRequiredInvoiceStep() {
        try {
            throw new IllegalStateException("invoice store unavailable");
        } catch (IllegalStateException e) {
            LOG.log(Level.SEVERE,
                    "event=invoice_generation_failed action=abort",
                    e);
        }
    }

    public static void main(String[] args) {
        setupLogging();

        rejectInvalidOrder();
        schedulePaymentRetry();
        failRequiredInvoiceStep();

        LOG.fine("event=diagnostic_detail message=hidden");
    }
}
```

Compile and run in the directory containing the file with JDK 17 or later:

```bash
javac -encoding UTF-8 ExceptionLogLevelDemo.java
java ExceptionLogLevelDemo
```

**stderr output** (because JUL's `ConsoleHandler` writes to `System.err` by default):

```text
INFO event=order_rejected reason_code=EMPTY_ORDER_ID
WARNING event=payment_gateway_timeout action=retry_scheduled exception=IOException detail=gateway timeout
SEVERE event=invoice_generation_failed action=abort exception=IllegalStateException detail=invoice store unavailable
```

**stdout output:** none. Terminals usually display both streams, so you will still see the stderr lines on screen.

### What to Observe

- `rejectInvalidOrder()` throws no exception; the log level reflects the **business outcome**, regardless of whether a `Throwable` exists.
- Both `schedulePaymentRetry()` and `failRequiredInvoiceStep()` have exceptions, yet their levels differ because recovery status and impact differ.
- `LOG.log(Level.WARNING, "...", e)` uses the overload taking a `Throwable`; `record.getThrown()` in the formatter still retrieves the exception object.
- `LOG.fine(...)` does not appear because both the logger and the handler are set to `INFO`. Enable `FINE` on **both** the logger and the handler if you actually want to see this record.
- `LOG.setUseParentHandlers(false)` prevents forwarding logs to parent logger handlers in this example, avoiding duplicate output beyond the expected lines.
- The code in `failRequiredInvoiceStep()` **catches the exception and only logs**, so the program still finishes `main`. This is a log-observation example; in a real application, when a required step fails, you must also **return a failure status, abort, roll back, or rethrow** according to the business contract. A `SEVERE` log line alone does not cause any of those behaviors.

### Why Is the Full Stack Trace Not Printed in This Example?

With a standard formatter, line numbers and headers in a stack trace can vary by code location, time, thread, and configuration. The example controls the formatter to keep output clear and reproducible. **Do not treat omitting stack traces here as a default recommendation for production**: unexpected errors usually require stack traces (and cause chains) to locate the origin.

## 6. Logging Exceptions with the Right API to Preserve Diagnostics

With JUL, the recommended way to preserve an exception is:

```java
try {
    performCriticalOperation();
} catch (IOException e) {
    LOG.log(Level.SEVERE, "event=operation_failed", e);
    throw new IllegalStateException("Critical operation failed", e);
}
```

This is an **illustrative snippet inside a class**, assuming `LOG` and `performCriticalOperation()` are already declared; it is not a standalone runnable file. The snippet shows the `Logger.log(Level, String, Throwable)` overload. In a multi-layer application, **you should not necessarily both log `SEVERE` and rethrow** as in this syntax demo: if an outer layer also logs, it creates duplicates. The next section explains how to choose the logging boundary.

Ways that easily lose information:

```java
// Logs only a string, losing the Throwable in the log record:
LOG.severe("operation failed: " + e.getMessage());

// Logs only toString(), without producing a stack trace:
LOG.warning("operation failed: " + e);
```

Both approaches may show the exception name or message, but `LogRecord.getThrown()` will not have the exception attached. As a result, formatters/encoders may **lack the `Throwable` object needed to print the stack trace and cause chain**.

With JUL, a standard option when you need stack traces is `java.util.logging.SimpleFormatter`, for example:

```java
ConsoleHandler handler = new ConsoleHandler();
handler.setFormatter(new java.util.logging.SimpleFormatter());
```

This is an illustrative configuration snippet. `SimpleFormatter` can print the timestamp, source, message, and stack trace of a `LogRecord` containing a `Throwable`; exact output can be affected by configuration and runtime. It is not represented by a fixed stdout string here.

### Distinguishing Three Levels of Exception Information

| Information | Source | Value |
| --- | --- | --- |
| **Exception type** | `e.getClass()` or `e.toString()` | Preliminary classification |
| **Exception message** | `e.getMessage()` | Partial error context; may be `null` or contain unsafe data |
| **Stack trace and cause chain** | `Throwable` passed to logger, processed by formatter/encoder | Enables tracing the call path and root cause during investigation |

Do not rely solely on `getMessage()` for diagnosis. The root cause sometimes resides in `e.getCause()` or a deeper nested exception. When translating exceptions across layers, preserve the cause:

```java
try {
    readFromGateway();
} catch (IOException e) {
    throw new IllegalStateException("Cannot complete order", e);
}
```

This is a non-standalone example. The `IllegalStateException(String, Throwable)` constructor keeps `IOException` as the cause; omitting the `e` argument makes the original failure much harder to trace.

## 7. An Exception Crossing Multiple Layers: Where to Log?

A processing flow might look like this:

```text
HTTP Controller
    |
    v
OrderService
    |
    v
PaymentGatewayClient
    |
    X  IOException / timeout
```

If `PaymentGatewayClient`, `OrderService`, and `Controller` all do:

```java
LOG.log(Level.SEVERE, "payment failed", e);
throw e;
```

then **a single failure** can generate three error records with nearly identical stack traces. This creates log noise, increases cost, and causes alerts to miscount failed transactions.

Instead, define **responsibility boundaries**:

- **Infrastructure/client layer:** may add context or translate to an appropriate exception while **preserving the cause**. It does not have to log at `SEVERE` if an upper layer will decide the final outcome.
- **Service layer:** if it recovers completely, log a meaningful fallback/retry event at an appropriate level; if it cannot recover, throw an exception with context so the final boundary can decide.
- **Boundary layer** such as an HTTP exception handler, job runner, or message consumer: usually the place that knows whether a request/job **finally failed** or was handled; log one error record with `request_id`, `order_id`, `operation_id`, and the exception when truly needed.
- **Monitoring infrastructure:** use metrics and traces to track frequency/volume; avoid duplicating stack traces just to increase error "visibility".

The "**log or rethrow**" rule is a guideline to prevent duplicate logs, not an absolute ban. You can log a **different, independently valuable event** at a lower layer (for example, "retry scheduled") and still propagate the final exception upward. In that case, clearly distinguish the event names and outcomes so two records do not look like two separate failures.

### Example of Sensible Retry Handling

Suppose a network call fails on the first attempt but succeeds on the next. You might see:

```text
WARNING event=dependency_unavailable attempt=1 action=retry
INFO event=payment_completed attempts=2 outcome=SUCCESS
```

This is illustrative log output, not output from the Java program in Section 5. Do not log `SEVERE payment_failed` on the first attempt if the business operation ultimately succeeds; if all retries fail and the request cannot recover, log the **final failure event** at the appropriate level.

In high-traffic services, even `WARNING` for every single retry can be too noisy. You can lower the log level or log a summary warning while tracking retry counts via metrics; choose based on your operational needs.

## 8. Understanding `catch`, `throw`, and Log Levels

The code below **catches and recovers**:

```java
try {
    return readOptionalConfig();
} catch (IOException e) {
    LOG.log(Level.INFO,
            "event=optional_config_unavailable action=use_defaults",
            e);
    return defaultConfig();
}
```

If using default values is routine and no stack trace is needed, you can omit `e` or use `FINE`; if unavailable configuration signals degradation worth monitoring, `WARNING` may be appropriate. Pick the level based on operational meaning.

The code below **only translates the exception type and propagates it**:

```java
try {
    return callGateway();
} catch (IOException e) {
    throw new PaymentUnavailableException(
            "Gateway could not be reached", e);
}
```

Because this layer does not yet know whether the request will ultimately fail or be retried/recovered above, **there is no need to log `ERROR` here**. The boundary layer can log once when the outcome is known. `PaymentUnavailableException` is an assumed exception class name that must be declared in the project; this snippet is not standalone.

The code below **swallows the exception**:

```java
try {
    chargePayment();
} catch (IOException e) {
    LOG.log(Level.SEVERE, "payment failed", e);
}
// Execution continues as if the payment succeeded.
```

This is a control-flow bug if payment is a required step. **Logging `SEVERE` does not inform subsequent code that the operation failed.** You must return a failure result, apply a designed retry/fallback, or throw an appropriate exception; never treat logging as error handling.

## 9. Level Filtering: Logger, Handler/Appender, and Collector

A call to `LOG.log(Level.FINE, "...", e)` does not guarantee operators will see the record. In JUL, emission is checked at least at the logger and each handler:

```text
Logger level: INFO
    |
    +-- INFO     -> allowed through
    +-- WARNING  -> allowed through
    +-- SEVERE   -> allowed through
    +-- FINE     -> filtered out at logger
    |
    v
Handler level: WARNING
    |
    +-- INFO     -> filtered out at handler
    +-- WARNING  -> reaches formatter/destination
    +-- SEVERE   -> reaches formatter/destination
```

A logging system may also have a `Filter`, parent logger handlers, dynamic configuration, and downstream collectors. In JUL, a handler with threshold `INFO` normally accepts `INFO`, `WARNING`, and `SEVERE` unless filtered elsewhere. Do not look only at `logger.setLevel(Level.FINE)` and conclude `FINE` will definitely reach the file or console; **the handler must accept it as well**.

In SLF4J/Logback or other backends, `DEBUG`/`INFO`/`WARN`/`ERROR` levels and appender/filter mechanisms have their own rules. Check the actual configuration instead of mechanically translating level names.

**Log level is not a transaction-priority mechanism.** Raising or lowering a level must not change error-handling flow or order state. Disabling logs must preserve identical business outcomes. Relying on a logger `Supplier` executing to perform a business action is a design flaw.

## 10. When Do You Need a Stack Trace vs. Just an Outcome Code?

Stack traces are invaluable for **unexpected** errors that require fixing code or configuration. However, stack traces for every **expected** case can create log noise, consume bandwidth, and risk exposing sensitive details.

| Situation | What to Log? |
| --- | --- |
| User submits malformed input | Event name, validation error code, correlation id if needed; usually no stack trace |
| Business rule valid rejection | Fixed `reason_code`, `outcome`, and safe object identifier |
| Network call failed, retry scheduled | Attempt count, recovery action, error type; stack trace only if genuinely helpful for investigation |
| Unexpected error causing request/job failure | One record at the appropriate boundary, with `Throwable` and enough context to debug |
| Fatal startup error | Reason service cannot start, relevant non-sensitive config, `Throwable`/stack if available |
| Failure already thoroughly captured by monitoring | Consider reducing duplicate logs in intermediate layers |

Operators need both **context** and **cause**. For instance, a `NullPointerException` and stack trace locate the code line, but without knowing the affected request or entity, reproducing the bug remains hard. Conversely, an order ID without the underlying exception is sometimes insufficient to find a technical bug.

A meaningful error record might include:

```text
event=invoice_generation_failed
order_id=ORD-101
correlation_id=req-7a
attempt=3
outcome=FAILED
reason_code=INVOICE_STORAGE_UNAVAILABLE
exception=IOException   # illustrates the error type name
```

The lines above illustrate recommended fields, not a suggestion to log one field per line. Actual output may be JSON or single-line `key=value`, with the stack trace stored as a dedicated property or properly escaped.

## 11. Rethrowing Exceptions and Preserving the Cause Chain

When a low-level exception is translated into a domain-meaningful exception, do not drop the cause:

```java
try {
    repository.save(order);
} catch (SQLException e) {
    throw new OrderPersistenceException(
            "Could not persist order", e);
}
```

This illustrative example uses assumed classes and variables from a real application. Custom exception constructors should accept `Throwable cause` and call `super(message, cause)` or an equivalent mechanism. Creating only `new OrderPersistenceException("Could not persist order")` without passing `e` can lose the original cause's stack trace when logged at an upper layer.

An exception sometimes already contains a nested cause, for example:

```text
OrderPersistenceException: Could not persist order
    caused by SQLException: Connection unavailable
        caused by SocketTimeoutException: Read timed out
```

With a formatter that supports full stack traces, the cause chain enables deep investigation; each layer does not need to log separately for operators to "see" all three errors.

**Do not log `e.getMessage()` verbatim as unconditionally safe data.** Messages from SQL drivers, HTTP clients, or dependencies can contain internal addresses, user input, URLs with query strings, identifiers, or sensitive strings. Apply masking/redaction policies and access controls at the log destination.

## 12. `InterruptedException`, Task Cancellation, and `Error`

Certain situations are easily logged at the wrong level:

### `InterruptedException`

In multithreaded systems, interruption is usually a **signal requesting stop or cancellation**. When catching this exception in a method that cannot rethrow it, you should normally restore the interrupt flag:

```java
try {
    Thread.sleep(1_000);
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    // Terminate the work or propagate the cancellation signal to the appropriate layer.
    return;
}
```

This snippet sits inside a method returning `void` or a compatible return type. During a graceful shutdown, being interrupted is **not automatically `SEVERE`**. Logging thousands of error stack traces while an application shuts down can obscure real incidents. However, if interruption leads to unexpected consequences or breaks a commitment, handling and log level must reflect the context.

### Requested Cancellation

`CancellationException` or task-cancellation states can be normal outcomes. A job cancelled by user request typically warrants an `INFO` or `FINE` event (if tracking is needed), not necessarily `ERROR`.

### Severe `Error`

`OutOfMemoryError` and `StackOverflowError` are special cases. After an out-of-memory error, even logging may no longer work reliably; do not design a general recovery strategy around "catch every `Throwable`, log `SEVERE`, and continue." Let the application/process be managed by proper supervision and restart mechanisms when needed.

## 13. HTTP Status Is Not a Direct Mapping to Log Level

In a web service, the HTTP status is the **protocol outcome of a request**; the log level is the **operational notability**.

Some illustrative scenarios:

| Response | Situation | Potentially Appropriate Level |
| --- | --- | --- |
| 400 | User sent malformed data, validated and returned as designed | Do not log / `DEBUG` / `INFO` depending on policy |
| 404 | Requested resource not found | Usually does not require `ERROR` |
| 409 | Valid business-state conflict | `INFO` or do not log, with reason code if needed |
| 429 | Policy-based rate limiting | Usually tracked via metrics; `INFO` or `WARN` depending on anomaly |
| 500 | Unexpected internal error causing request failure | Usually `ERROR`/`SEVERE` with exception at the error-logging boundary |
| 503 | Downstream service unavailable after exhausting retries | May be `ERROR`/`SEVERE` if the request genuinely failed |
| 200 | Fallback succeeded while downstream service is degraded | May warrant `WARNING` even though the request succeeded |

This table is not a rigid standard. For instance, occasional 404s from automated crawlers may be normal behavior; a spike of 404s for a critical asset after deployment may indicate a deployment bug worth alerting on via metrics/frequency.

A global exception handler should not log every `Exception` at `ERROR` without distinguishing expected errors from unexpected ones. Clearly classify domain exceptions, validation conditions, request states, and system exceptions before deciding the message and level.

## 14. Example with SLF4J: Passing Throwable as the Error Argument

In an application using SLF4J with a compatible backend (such as Logback), a common error-logging pattern is:

```java
private static final org.slf4j.Logger LOG =
        org.slf4j.LoggerFactory.getLogger(PaymentService.class);

void reportFailure(String orderId, java.io.IOException cause) {
    LOG.error("event=payment_failed order_id={}", orderId, cause);
}
```

This is an **illustrative snippet inside `PaymentService`**, requiring the class declaration and SLF4J/backend dependencies; it is not a standalone JDK-runnable file. The trailing `cause` argument is recognized by SLF4J as a `Throwable` in the matching call signature, allowing the backend to output the stack trace; `orderId` fills the `{}` placeholder. This syntax differs from JUL:

```java
LOG.log(Level.SEVERE,
        "event=payment_failed order_id=" + orderId,
        cause);
```

The JUL snippet is an example inside a class with an appropriate `LOG` and `cause`. This is the `Logger.log(Level, String, Throwable)` API; JUL has no `LOG.severe(String, Throwable)` overload. To keep a consistent JUL pattern with both parameters and a `Throwable`, you can construct a `LogRecord` explicitly or attach structured fields via backend mechanisms; do not assume every overload accepts both a parameter array and an exception simultaneously.

**Common SLF4J mistake:**

```java
// Avoid: converts the exception into plain message text only.
LOG.error("payment failed: {}", cause.getMessage());

// Usually better at the error-reporting boundary:
LOG.error("event=payment_failed", cause);
```

In the first case, `cause.getMessage()` is a string; the backend may have no `Throwable` object to render a stack trace. In the second case, the backend receives the exception. Even so, **an expected exception** should not be logged at `ERROR` merely because a `cause` variable is in scope.

## 15. Exceptions and Structured Log Messages

A good log message separates structured fields from free-form prose. For example, an illustrative JSON record:

```json
{
  "timestamp": "2026-11-09T12:00:00Z",
  "level": "ERROR",
  "service": "invoice-service",
  "event": "invoice_generation_failed",
  "order_id": "ORD-101",
  "correlation_id": "req-7a",
  "outcome": "FAILED",
  "reason_code": "INVOICE_STORAGE_UNAVAILABLE",
  "exception_type": "java.io.IOException"
}
```

This is **illustrative data from a hypothetical backend**, not JSON output from the JUL program in this article.

Stay consistent with:

- **`event`**: a stable event name; use the same name for the same failure type instead of varying prose descriptions.
- **`outcome` / `reason_code`**: codes from a controlled vocabulary, unlike `e.getMessage()` which can vary across libraries or versions.
- **`correlation_id` / `trace_id`**: helps correlate logs from the same execution flow; do not use this alone as sole proof of a successful transaction.
- **`attempt` / `operation_id`**: distinguishes retry attempts and avoids miscounting a repeated incident.
- **`exception_type` / stack trace**: diagnostic description; does not replace business-meaningful fields.

In particular, **avoid creating alerts based solely on exception class names**. An `IOException` could be a minor retry or a final failure of a core service; event, outcome, and context help tell them apart.

When designing centralized logging, enforce access control and retention policies. Stack traces and request context can reveal internal structure; never put passwords, tokens, API keys, card details, or sensitive payloads into logs. For input data containing newlines, use proper encoders/escaping to prevent log injection.

## 16. A Practical Exception-Logging Policy

A development team can agree on the following rules for a Java service:

1. **Define final handling boundaries** for HTTP requests, jobs, event consumers, and background tasks. This is where success, recovery, or failure is known.
2. **Classify expected outcomes** (validation, business rejections, requested cancellations) separately from **system errors**. Give each group clear `event` and `reason_code` values.
3. **Set levels for final outcomes**: normal operation at `INFO` or lower; recoverable degradation at `WARNING` when noteworthy; unexpected failures of critical features at `SEVERE`/`ERROR`.
4. **Choose where to log stack traces**: prefer the boundary that decides failure status, preserve the cause when translating exceptions, and avoid duplicate copies of the same stack across layers.
5. **Combine logs and metrics**: track error counts and latency via metrics; use logs with correlation IDs to investigate individual cases. Avoid firing alerts on individual retries handled normally by the system.
6. **Verify filtering configuration** across logger, handler/appender, formatter, and collector: a level disabled at one stage can cause records to disappear.
7. **Manage secrets and data**: filter sensitive data, keep detail proportional to need, and control access, retention, and storage cost when stack traces are frequent.
8. **Test real scenarios**: invalid input, dependency recovering after retry, and dependency failing completely. Verify that log levels, line counts, cause details, and business outcomes are all appropriate.

A useful three-case verification example:

```text
CASE 1: Invalid input
Expected: HTTP 400 / rejection outcome, no system error
Log: none / INFO per policy

CASE 2: Network timeout; retry success
Expected: business operation completes, possibly with a WARNING for the retry
Log: recovery event, no duplicate final error logged

CASE 3: Network timeout; retries exhausted
Expected: clear business failure
Log: one ERROR/SEVERE at the decision boundary, preserving Throwable and context
```

## 17. Common Mistakes

- **Logging every exception at `SEVERE`/`ERROR`:** triggers false alerts on expected cases; evaluate impact and recoverability instead.
- **Logging stack traces for every validation error:** noisy and expensive; use `event` and `reason_code` when tracking is needed.
- **Logging only `e.getMessage()`:** loses the stack trace and cause chain in the log record; pass `Throwable` to the appropriate overload when needed.
- **Catching and logging an error, then continuing as if it succeeded:** logging does not handle errors. Update the result, roll back, retry, or rethrow according to contract.
- **Logging and rethrowing at every layer:** one exception generates multiple `ERROR` lines; pick a single responsible boundary.
- **Logging `ERROR` on the first retry even when a retry succeeds:** alerts can falsely report a recovered transaction as failed; distinguish attempts from final outcomes.
- **Confusing JUL `Level.SEVERE` with `Level.ERROR`:** JUL has no `Level.ERROR`; use the API's actual constants.
- **Confusing logger level with handler level:** records may be filtered out before reaching their destination.
- **Ignoring interruption when catching exceptions:** can break thread stop/cancellation mechanisms; restore the `interrupt` flag when appropriate.
- **Putting sensitive data into exception messages:** stack traces and messages may be shipped to many systems; restrict and mask sensitive data.
- **Assuming `ERROR` level means rollback or HTTP 500:** logging does not control transactions or protocol responses.
- **Counting `ERROR` log lines to measure failed transactions:** retries, duplicate logs, sampling, and collector drops can skew counts; define a canonical outcome event and reconcile against the source of truth.

## 18. Self-Check Questions

1. **Is `FileNotFoundException` always an `ERROR`?** No. A missing optional file with defaults is very different from a missing required file that stops the service.
2. **Why might invalid input not need a stack trace?** Because it is an expected outcome handled by rules; a stack trace does not help find a system bug in normal cases.
3. **Which JUL level typically corresponds to a serious error?** `Level.SEVERE`, not `Level.ERROR`.
4. **How do you log `IOException e` at `WARNING` with the exception object in JUL?** `LOG.log(Level.WARNING, "event=retry_scheduled", e);`.
5. **If `Logger.log(Level.SEVERE, ..., e)` runs, does Java automatically rethrow the exception?** No. Logging methods do not control exception propagation.
6. **What problems can occur if an exception is logged at the client, service, and controller?** Duplicate stack traces, miscounted incidents, increased log volume, and harder investigation.
7. **A user cancels a task, interrupting the thread. Is that necessarily a critical error?** No. Handle interruption and choose the log level according to your cancellation/shutdown policy.
8. **A `FINE` record does not appear on the console even though the code called it. Why?** It may be filtered at the logger, handler, or another stage in the pipeline.
9. **A service returns 200 via fallback while the cache is failing. Might `WARNING` be needed?** Yes, if the degradation is worth monitoring; HTTP 200 does not dictate the entire log level.
10. **When is passing `Throwable` necessary?** When you need the stack trace or cause to investigate an error, especially for unexpected failures at a responsible logging boundary.
11. **Is `getMessage()` always safe to log verbatim?** No; it may contain sensitive data, user input, or characters that disrupt log formatting.
12. **If two retries fail and the third attempt succeeds, should there be three `SEVERE` logs?** Usually no. Track individual attempts and the final outcome separately, avoiding final-error alerts when the operation recovered.

**Key takeaway:** an exception answers **"what situation interrupted execution?"**, whereas a log level answers **"how noteworthy is this event to operations?"**. In Java, choose the level based on impact and recoverability, pass `Throwable` to preserve diagnostics when needed, log once at the appropriate boundary, and keep business outcomes correct regardless of whether logs are emitted.
