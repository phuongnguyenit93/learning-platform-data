# Troubleshooting Errors with Logging in Java

**Troubleshooting/debugging** is a core goal of logging: when a program behaves incorrectly, logs help reconstruct the events that occurred, narrow down where the failure happened, and verify the root cause. This is especially essential for errors that only appear in production environments, errors that cannot be reproduced immediately on a developer's machine, or errors that propagate across multiple processing layers.

Logging does not fix errors by itself, and a single `ERROR` line does not prove the root cause. The value of logs lies in **contextual, chronologically ordered evidence**, enabling investigators to distinguish symptoms, impact, and causes.

## 1. What Questions Do Logs Answer?

When investigating an error, look for evidence to answer:

1. **What happened?** Which operation failed; was the error returned to a user, a background task, or during startup?
2. **When and where did it happen?** Timestamp, component, method, processing step, and relevant deployment version.
3. **Who or what was affected?** A single request, a job, a resource, or the entire service? Only log internal identifiers that are permitted to be stored.
4. **What happened right before the error appeared?** The last successful step, validated data, outbound calls, and state changes.
5. **Where did the exception originate?** The exception type, stack trace, and `Caused by` chain showing the call flow and the most immediate cause.
6. **Is the error recurring?** Does the same symptom appear across multiple requests, after a deployment, or when the system is under load?

For example, `Payment failed` alone is almost never enough to investigate. The same event enriched with `requestId`, `operation`, `stage`, `outcome`, exception type, and timestamp helps identify which request failed and at which step.

## 2. How Should Logs Be Written for Troubleshooting?

An important event should carry fields with stable meanings:

| Field | Purpose | Example |
| --- | --- | --- |
| `timestamp` | Order events and compare against the reported error time | `2026-01-15T08:30:12.345Z` |
| `level` | Distinguish normal progression, warnings, and failures | `INFO`, `WARNING`, `SEVERE` |
| `service` / `component` | Identify where the event originated | `order-service`, `ConfigLoader` |
| `requestId` / `jobId` / `runId` | Correlate lines belonging to the same unit of work | `req-42` |
| `operation` and `stage` | Know what is being done and which step was reached | `createOrder`, `validate` |
| `outcome` and stable error code | Distinguish success/failure and group errors | `failed`, `INVALID_TIMEOUT` |
| `durationMs` or dependency info | Spot slowness, timeouts, and retries | `durationMs=1200` |
| `exception` with cause | Trace the location and technical cause | `NumberFormatException` |

An easily filterable log might look like:

```text
2026-01-15T08:30:12.345Z INFO service=order-service requestId=req-42 operation=createOrder stage=validate outcome=started
2026-01-15T08:30:12.349Z WARNING service=order-service requestId=req-42 operation=createOrder stage=validate outcome=failed errorCode=INVALID_QUANTITY
```

The two lines above are **illustrative sample data demonstrating structure**, not the output of running the program in a later section.

**Practical principles:**

- Log events at key boundaries: start of processing, data validation, calls to dependent systems, retries, and completion. Do not log every line of code.
- Use the same correlation ID throughout the flow; across HTTP/message queues, propagate the ID through the application's mechanism rather than expecting `ThreadLocal` to cross threads or processes automatically.
- Log events where **full business context** is available; record the exception as a `Throwable` so the stack trace is preserved.
- Use stable field names and error codes for filtering with search tools. Separate human-readable message strings from machine-readable error codes.
- Timestamps should include an explicit time zone, typically UTC/ISO 8601, especially when multiple services run across different time zones.
- Log only what is needed for operations. Never log passwords, access tokens, session cookies, secret keys, or sensitive personal data; sanitize input that may contain newlines to prevent log injection.

### Choosing the Right Log Level in Java

In `java.util.logging` (JUL), common levels include:

| JUL Level | When to use |
| --- | --- |
| `FINE`, `FINER`, `FINEST` | Diagnostic details, usually enabled selectively only when needed |
| `INFO` | Normal operational milestones and notable events |
| `WARNING` | Abnormal situations where the system can still continue, expected input errors, or retries |
| `SEVERE` | Serious failure of an operation or component that requires attention |

The log level depends on **operational impact and policy**, not just the exception class name. For instance, invalid user input typically does not warrant `SEVERE`; misconfigured startup settings that prevent a service from running may require `SEVERE`. JUL also includes other levels such as `CONFIG` and `OFF`.

## 3. Error Investigation Workflow Using Logs

1. **Identify the symptom.** Note the time, environment, operation, request/job ID if available, actual result, and expected result.
2. **Narrow down the time window and component.** Find failed events near the reported error time; check clock skew before inferring ordering across multiple machines.
3. **Filter by correlation ID.** Group lines sharing the same `requestId`, `jobId`, or `runId`, then sort chronologically. If flows run concurrently, use additional IDs and event ordering to avoid treating interleaved lines as a single request.
4. **Find the transition from normal to abnormal.** Identify the last successful step and the first failed step; inspect timeouts, retries, dependency status, and error codes.
5. **Read the full exception.** Inspect the exception type, stack trace, `Caused by`, and frames belonging to application code. The top line of a stack trace is where the exception was created/thrown, not necessarily the ultimate business cause.
6. **Form a testable hypothesis.** For example: a non-numeric config value, connection refused, missing permissions, or data failing a precondition. Cross-check configuration, permitted validated inputs, operational metrics, and successful runs.
7. **Verify after fixing.** Reproduce in a controlled manner, test both failure and success cases, and confirm that logs pinpoint the handling point and the error does not recur. If log data was insufficient, add meaningful events for next time.

**Do not infer the root cause from the final log line alone.** A `NullPointerException` in the presentation layer may be the consequence of a null value returned by an earlier step; `Connection timed out` could also be a symptom of high load or a network issue. Additional evidence is needed to confirm the hypothesis.

## 4. Java 17+ Example: Investigating Misconfiguration with `java.util.logging`

The following example runs standalone on JDK 17+ with no external libraries. A startup run has `runId=boot-42`; the program attempts to parse a timeout from the string `five-seconds` and detects an invalid value. The logs show the step that started, the step that failed, the exception, and the cause preserved via the `cause` chain.

Save the content as `InvestigateFailureDemo.java`:

```java
import java.io.PrintWriter;
import java.io.StringWriter;
import java.util.logging.ConsoleHandler;
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class InvestigateFailureDemo {
    private static final Logger LOGGER =
            Logger.getLogger(InvestigateFailureDemo.class.getName());

    public static void main(String[] args) {
        configureLogging();

        String runId = "boot-42";
        LOGGER.info("runId=" + runId
                + " operation=startupConfig stage=readTimeout outcome=started");

        try {
            int timeoutMillis = parseTimeoutMillis("five-seconds");
            LOGGER.info("runId=" + runId
                    + " operation=startupConfig stage=readTimeout outcome=completed"
                    + " timeoutMillis=" + timeoutMillis);
        } catch (IllegalArgumentException e) {
            LOGGER.log(Level.SEVERE,
                    "runId=" + runId
                            + " operation=startupConfig stage=readTimeout outcome=failed",
                    e);
        }
    }

    private static int parseTimeoutMillis(String raw) {
        try {
            int value = Integer.parseInt(raw);
            if (value <= 0) {
                throw new IllegalArgumentException(
                        "timeoutMillis must be positive");
            }
            return value;
        } catch (NumberFormatException e) {
            throw new IllegalArgumentException(
                    "timeoutMillis must be an integer", e);
        }
    }

    private static void configureLogging() {
        LOGGER.setUseParentHandlers(false);
        LOGGER.setLevel(Level.INFO);

        ConsoleHandler console = new ConsoleHandler();
        console.setLevel(Level.INFO);
        console.setFormatter(new Formatter() {
            @Override
            public String format(LogRecord record) {
                StringBuilder message = new StringBuilder();
                message.append(record.getLevel())
                        .append(' ')
                        .append(formatMessage(record))
                        .append(System.lineSeparator());

                if (record.getThrown() != null) {
                    StringWriter buffer = new StringWriter();
                    record.getThrown().printStackTrace(new PrintWriter(buffer));
                    message.append(buffer);
                }
                return message.toString();
            }
        });

        LOGGER.addHandler(console);
    }
}
```

Compile and run:

```bash
javac InvestigateFailureDemo.java
java InvestigateFailureDemo
```

**Illustrative output excerpt (written to stderr)**, with stack trace lines abbreviated because file line numbers and JDK details may vary:

```text
INFO runId=boot-42 operation=startupConfig stage=readTimeout outcome=started
SEVERE runId=boot-42 operation=startupConfig stage=readTimeout outcome=failed
java.lang.IllegalArgumentException: timeoutMillis must be an integer
    at InvestigateFailureDemo.parseTimeoutMillis(InvestigateFailureDemo.java:...)
    at InvestigateFailureDemo.main(InvestigateFailureDemo.java:...)
Caused by: java.lang.NumberFormatException: For input string: "five-seconds"
    ...
```

**Evidence analysis:**

- The `INFO` line shows the program entered the configuration reading step; there is no `outcome=completed` line.
- The `SEVERE` line ties the incident to `runId=boot-42` and `stage=readTimeout`, allowing all events from this run to be found.
- `IllegalArgumentException` expresses the configuration rule at the application layer; `Caused by: NumberFormatException` points to the failed string-to-number conversion.
- Replacing `"five-seconds"` with `"5000"` follows the success branch and logs `timeoutMillis=5000`. A value like `"0"` is still rejected because the timeout must be positive.

The formatter here intentionally simplifies logs for learning purposes. In production, add a timestamp with a time zone, service name, and a consistent log format; a JSON formatter can be used if the log collection system requires it. `ConsoleHandler` writes to **stderr** by default, not stdout.

The sample program catches the exception in `main` to display the full evidence. It **does not automatically exit with a non-zero exit code** just because `LOGGER.log(Level.SEVERE, ...)` was called. A real application must decide whether to abort startup, return an error, or transition to an unready state according to its policy; logging does not replace error handling.

## 5. Logging Exceptions Properly to Preserve the Cause

Logging only the exception message often cuts the investigation short:

```java
catch (Exception e) {
    LOGGER.severe("Startup failed: " + e.getMessage());
}
```

This drops the stack trace and `cause` chain from the log record. When actually handling or reporting an error at an appropriate boundary, pass the entire exception object:

```java
catch (Exception e) {
    LOGGER.log(Level.SEVERE,
            "runId=" + runId + " operation=startupConfig outcome=failed",
            e);
}
```

The second snippet assumes `LOGGER` and `runId` are already in method scope, so it is an **illustrative pattern inside a `catch` block**, not a standalone program.

When translating exceptions across layers, preserve the original cause using a constructor that accepts `cause` (for example, `new IllegalArgumentException("Invalid config", e)`). Avoid logging the same stack trace at every layer and rethrowing without adding context: that produces duplicate records and makes one failure look like multiple incidents. A common convention is to add context when crossing layers and log the full exception once at the final handling boundary.

An expected exception that is handled successfully—such as retrying and recovering—may only need `WARNING` along with the attempt count and outcome. Do not use `SEVERE` for every exception.

## 6. Correlating Traces Across Multiple Threads or Services

For a request flowing through a controller, service, repository, or multiple services, a **correlation ID** helps group the right events together:

```text
INFO  requestId=req-42 component=OrderController stage=received
INFO  requestId=req-42 component=OrderService stage=validated
WARNING requestId=req-42 component=InventoryClient stage=reserve outcome=retry attempt=1
SEVERE requestId=req-42 component=OrderService stage=reserve outcome=failed errorCode=UPSTREAM_TIMEOUT
```

This is an illustrative scenario. From this sequence, we know the error occurred after validation, during the inventory reservation step; we should inspect the dependency's logs and the timeout cause before concluding the bug is in business logic.

`java.util.logging` does not provide a built-in mechanism to automatically propagate `requestId` across all threads and services. The application must attach the ID to the task context and forward it when spawning tasks, sending messages, or making HTTP calls. In other logging libraries, MDC/thread context can help, but you still need to handle thread handoffs and clear the context to avoid assigning the wrong ID.

When log volume is high, prioritize searching by time range + `service` + correlation ID + `errorCode`, rather than scanning the entire file manually.

## 7. Logging Mistakes That Make Troubleshooting Harder

| Mistake | Consequence | Improvement |
| --- | --- | --- |
| Logging only `"error"` or `e.getMessage()` | Unknown step, lost stack trace | Log operation, stage, ID, and `Throwable` |
| No correlation ID | Logs from concurrent requests mix together | Propagate an ID per request/job |
| Logging only on error, with no prior milestones | Cannot see the last successful step | Log start/end milestones and key boundaries |
| Logging the same exception at every layer | Duplicate stack traces, noisy alerts | Pick a primary logging boundary; preserve cause when rethrowing |
| Logging raw input or secrets | Data leaks, risk of log forging | Mask/omit sensitive data, sanitize untrusted input |
| Enabling debug logging indiscriminately | Wastes resources, hard to find signal | Control log level, duration, and retention policy |
| Inconsistent timestamps or time zones | Hard to reconstruct sequence across systems | Use a standard timestamp format and check clock sync |
| Treating every error as `SEVERE` | Misleading alert severity, hard to prioritize | Classify by actual impact and recoverability |

Distinguish **logs**, **metrics**, and **traces**: logs describe individual events; metrics show trends, rates, and latency; distributed traces show the path and timing of a request's steps. When troubleshooting distributed systems, combining all three is more reliable than relying on a single exception line.

## 8. Checklist Before Considering an Error Explained

- There is evidence of the time, environment, component, and impact scope.
- Related logs for the same request/job/run and the failure starting point have been found.
- The full stack trace, `Caused by` chain, dependency state, and relevant context have been read.
- **Symptoms**, **hypotheses**, and **verified causes** are clearly separated.
- There is a reliable reproduction or verification method, along with post-fix results.
- Any added logs provide investigative value without exposing sensitive data or creating noise.

**The expected outcome of logging for troubleshooting** is being able to answer *what broke, at which step it broke, which unit of work it belonged to, why it likely happened, and what evidence confirms it*. Good logs reduce the time to find root causes and make future investigations easier, but conclusions must still rest on actual verification.
