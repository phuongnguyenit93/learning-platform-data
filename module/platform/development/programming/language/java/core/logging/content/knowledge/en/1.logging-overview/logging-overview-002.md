# Problems That Logging Solves

## 1. Why Do Applications Need Logging?

Suppose an order service works normally on a developer's machine, but occasionally returns errors when running on a server. Users only see a "Order failed" message; developers are not sitting next to the server to observe every statement. If the program does not record meaningful events, the operations team has a hard time knowing which request was affected, when the error occurred, which steps had already been executed, and what technical cause was detected.

**Logging** is the practice of an application recording **runtime events** as log records so that humans or other systems can look them up, filter them, and analyze them. The primary goal is to **create a contextual trail of what the application observed at runtime**.

Logging is useful even when a program has no errors: it shows that the application has started, received a request, performed an important task, or completed an operation. When an incident occurs, the preceding normal events help pinpoint where the abnormal behavior began.

For example, the following two messages carry very different amounts of information:

```text
Error!
```

```text
level=SEVERE service=order-api requestId=req-42 orderId=ord-17
event=inventory_reservation_failed cause=InventoryServiceUnavailable
```

The second record makes it possible to find the exact request, identify the failing step, and narrow down the component to investigate. It **does not by itself prove the root cause**; the development team still needs to cross-check source code, dependent systems, and other evidence.

## 2. Problems That Logging Helps Solve

### 2.1. Observing a Running Program Outside the Development Environment

In server applications, background tasks, scheduled jobs, or multithreaded systems, it is not always possible to pause the program with a debugger. Logs record milestones such as "application ready", "processing started", "calling dependent service", "retrying", and "completed".

As a result, operators can answer: **Did the application actually receive the work? At which step did it stop?** This is operational observability—it does not mean every single statement must be logged.

### 2.2. Reconstructing What Happened Before and After an Error

An exception usually tells *what failed* at a specific location in the code. Logs at related milestones tell *the sequence of events leading up to the error*:

```text
10:15:03.100 INFO  requestId=req-42 event=order_received
10:15:03.120 INFO  requestId=req-42 event=inventory_reservation_started
10:15:03.310 WARN  requestId=req-42 event=inventory_retry attempt=2
10:15:03.620 ERROR requestId=req-42 event=inventory_reservation_failed
```

This is an illustrative sequence; timestamps, log levels, and event names depend on the application. Milestones help narrow down the time window of an incident and distinguish between "request not yet received", "started but dependency is slow", and "ended with an error".

**Limitation:** you cannot conclude that a step did not happen merely because no log for that step was found. Logs may have been filtered, dropped, written late, or not programmed in the corresponding branch.

### 2.3. Diagnosing Errors and Reducing Root-Cause Investigation Time

When catching an unexpected error at an appropriate handling boundary, the log should contain the **operation**, **relevant context**, and **original exception**. In Java, calling `logger.log(Level.SEVERE, "Message", exception)` retains the `Throwable` object so that the formatter/handler can record the error details and stack trace.

For example, instead of logging only "Could not save", you should know which order-saving operation it was, which request it occurred in, and what type of exception was thrown. The stack trace shows the call path leading to the error; error codes or responses from dependent services can help investigate further.

You should not catch an exception, log only a message, and swallow it if upstream callers still need to know that the operation failed. Nor should you log **the same exception at every layer**, turning one error into dozens of duplicate records. Define which layer is responsible for logging and how errors are propagated or handled.

### 2.4. Correlating Events of the Same Request

Servers handle many requests concurrently; sorting logs by time alone can interleave different execution flows. Including a consistent **requestId** or **correlationId** in log records makes it possible to filter events belonging to the same transaction.

For example, when `req-42` passes through API → order service → inventory service, each component needs to propagate or log an appropriate correlation identifier. Thread name alone is not enough because thread pools can reuse threads for different requests. In distributed systems, `traceId` and `spanId` often help link logs with distributed tracing; they must be propagated properly across service boundaries.

### 2.5. Supporting Operations, Alerting, and User Support

Logs help support staff look up an event by request ID, timestamp, or operation; help on-call engineers correlate deployment changes with spikes in errors; and provide data for alerting systems when collected and analyzed properly.

Messages with a stable structure, clear severity levels, and consistent context are usually much easier to search than free-form sentences like "Entered method A" or "Got here". However, **logs do not replace metrics** for counts, error rates, latency, or SLOs; metrics are typically better suited for tracking trends, while logs help inspect specific event details.

### 2.6. Providing a Trail for Business Auditing

Certain critical actions (such as order status changes or configuration updates) require a trail of "what action, when, and what result". Diagnostic logs can assist with lookup, but **audit trails have their own requirements** regarding completeness, access control, tamper resistance, retention periods, and data protection. Never assume that a few ordinary log lines satisfy audit or regulatory requirements.

## 3. What Information Should a Useful Log Record Contain?

Every record does not necessarily need every field, but it needs enough context to answer investigation questions without exposing sensitive data.

| Component | Role | Example |
|---|---|---|
| Timestamp and time zone | Identify when the event occurred and correlate across systems | `2026-11-09T03:15:03.620Z` |
| Level | Distinguish normal operations, warning signs, and errors | `INFO`, `WARNING`, `SEVERE` |
| Source | Identify the service, component, or logger | `order-api`, `InventoryClient` |
| Event/operation | Indicate the action and state; should have a stable name | `event=reserve_failed` |
| Correlation ID | Group logs belonging to the same request/job/transaction | `requestId=req-42` |
| Safe business context | Aid tracing without exposing secrets | `orderId=ord-17` |
| Error details when present | Provide exception type, message, and appropriate stack trace | `IllegalStateException` |

Timestamps and log locations can be added by the logger/handler; there is no need to manually concatenate every field into every string. In real-world applications, JSON or key–value logs with a consistent schema are usually convenient for centralized logging systems. Do not log tokens, passwords, API keys, card data, sensitive content, or full request/response payloads indiscriminately; identifiers should also be reviewed against security policies.

### Choosing Log Levels by Meaning

In the JDK's `java.util.logging` (JUL):

- **`SEVERE`:** critical errors or unexpected operation failures that require attention.
- **`WARNING`:** abnormal conditions that can be handled or recovered from, such as retries or invalid input that should be monitored.
- **`INFO`:** key operational milestones, such as starting and completing a meaningful task.
- **`FINE` / `FINER` / `FINEST`:** diagnostic details, usually enabled selectively.

Other frameworks may use names like `ERROR`, `WARN`, `DEBUG`, `TRACE`. **The level reflects the severity of the event**, not the length of the message. For example, running out of stock under normal business rules is not necessarily `SEVERE`, whereas a dependent data store going down can be a serious operational failure.

## 4. Java 17+ Example: Seeing the Journey of a Request

The following program simulates two order requests. The first request fails because the inventory service is unavailable; the second succeeds. The example uses the JDK's built-in logger, **requiring no external dependencies**.

Save the entire code into `LoggingProblemDemo.java`:

```java
import java.util.logging.ConsoleHandler;
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class LoggingProblemDemo {
    private static final Logger LOG =
            Logger.getLogger(LoggingProblemDemo.class.getName());

    public static void main(String[] args) {
        configureLogging();
        processOrder("req-42", "ord-17", false);
        processOrder("req-43", "ord-18", true);
    }

    private static void configureLogging() {
        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.INFO);

        ConsoleHandler handler = new ConsoleHandler();
        handler.setLevel(Level.INFO);
        handler.setFormatter(new Formatter() {
            @Override
            public String format(LogRecord record) {
                String cause = "";
                if (record.getThrown() != null) {
                    Throwable error = record.getThrown();
                    cause = " cause=" + error.getClass().getSimpleName()
                            + ":" + error.getMessage();
                }
                return record.getLevel().getName() + " "
                        + record.getMessage() + cause
                        + System.lineSeparator();
            }
        });
        LOG.addHandler(handler);
    }

    private static void processOrder(
            String requestId, String orderId, boolean inventoryAvailable) {
        String context = "requestId=" + requestId + " orderId=" + orderId;
        LOG.info(context + " event=order_received");

        try {
            reserveInventory(inventoryAvailable);
            LOG.info(context + " event=inventory_reserved");
        } catch (IllegalStateException error) {
            LOG.log(Level.SEVERE,
                    context + " event=inventory_reservation_failed", error);
        }
    }

    private static void reserveInventory(boolean available) {
        if (!available) {
            throw new IllegalStateException("inventory service unavailable");
        }
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac LoggingProblemDemo.java
java LoggingProblemDemo
```

Console output (the handler uses the standard error stream, `stderr`):

```text
INFO requestId=req-42 orderId=ord-17 event=order_received
SEVERE requestId=req-42 orderId=ord-17 event=inventory_reservation_failed cause=IllegalStateException:inventory service unavailable
INFO requestId=req-43 orderId=ord-18 event=order_received
INFO requestId=req-43 orderId=ord-18 event=inventory_reserved
```

**Reading the output:** filtering for `requestId=req-42` shows that the request was received, and then the inventory reservation step failed; `requestId=req-43` has normal completion events. The exception is passed to `LOG.log(..., error)` so the logger can provide diagnostic information. The custom formatter here only prints the error type and message so that the output is **stable and easy to verify**; in a real application, use a formatter/handler that preserves stack traces and timestamps, and configure appropriate output destinations, retention policies, and collection mechanisms.

This example only illustrates two simulated scenarios. The `inventory service unavailable` event is an error intentionally created by the program when the `inventoryAvailable` flag is `false`; it does not prove that an actual network service or database failed.

## 5. How Does Logging Differ from `System.out.println`?

| Aspect | `System.out.println` | Logging via API/framework |
|---|---|---|
| Purpose | Print strings to stdout | Record contextual events for monitoring and diagnostics |
| Severity levels | No built-in levels | Has levels to adjust verbosity |
| Context/metadata | Must be concatenated manually if needed | Can configure timestamp, logger name, thread, correlation ID |
| Destination | Stdout | Console, file, collector, or handler/appender as configured |
| Exception handling | Usually printed manually or via `printStackTrace` | Has APIs to log alongside a `Throwable` |
| Operational management | Hard to adjust uniformly when scattered | Typically supports filtering, formatting, configuration, and centralized collection |

`println` is still useful when learning a language or writing small programs. In long-lived applications, logging helps organize information by event, tune verbosity, and integrate with operations. However, using a logging API **does not by itself guarantee** that logs are durably stored or centralized; that also depends on configuration and infrastructure.

## 6. Common Mistakes and Limitations of Logging

1. **Logging too little or lacking context:** "Processing error" does not tell which request or operation failed. Log the correlation ID, event name, and exception at the appropriate layer.
2. **Logging too much:** printing inside every loop or logging entire payloads can increase I/O overhead, consume storage, drown out useful signals, and hurt performance. Choose important milestones, adjust levels, or sample intentionally.
3. **Logging sensitive data:** do not put passwords, access tokens, secrets, or unnecessary personal data into logs. Watch out for exception messages, URL queries, and user input as well; guard against newlines or control characters that can forge log records.
4. **Losing the error cause:** logging only `error.getMessage()` can drop the stack trace and cause chain. Pass the `Throwable` to the logger where the error is recorded, while avoiding repeating the same error across multiple layers.
5. **Wrong log level:** logging an expected business condition as `SEVERE` creates false alerts; logging a real error as `FINE` may cause it to be filtered out.
6. **Missing correlation identifiers:** interleaved log lines from multiple requests are hard to use for reconstructing an execution flow.
7. **Treating logs as an absolute source of truth:** logs can be filtered, stuck in an unflushed buffer, lost in a crash, affected by clock skew, or expired by retention. Do not use "no log found" as definitive proof that an event did not occur.

Three complementary signal sources in operations are **logs** (detailed events), **metrics** (aggregated measurements over time), and **traces** (the path and duration of a request across components). Logging solves the event-trail problem well; it does not replace testing, quantitative monitoring, or distributed tracing.

## 7. How to Evaluate Whether Your Logs Actually Solve the Problem

For a hypothetical incident, try answering the following questions using only the necessary log records: **(1)** which request or job was affected; **(2)** when it started and ended; **(3)** what the last successfully recorded step was; **(4)** what the error event and exception were; **(5)** whether events in the same context can be correlated without exposing sensitive data.

If any answer is missing, add **the exact missing event and context fields**, rather than randomly increasing the number of `println` statements. A useful logging system helps development and operations teams narrow the scope of investigation, explain what the application observed, and resolve incidents faster, within the limits of the evidence that the logs actually recorded.
