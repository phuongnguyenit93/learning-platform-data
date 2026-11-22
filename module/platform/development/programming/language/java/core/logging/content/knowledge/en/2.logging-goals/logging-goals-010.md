# Principles of Useful Logging in Java

A log line is valuable when a reader can rely on it to **understand the event, determine the scope of impact, and decide on the next investigation or remediation step**. Logs should not merely prove that a line of code executed; they must produce actionable evidence while the application is running, especially when a bug cannot be reproduced locally on a developer's machine.

In Java, whether you use `java.util.logging` (JUL), SLF4J with Logback, or Log4j 2, the principles for designing log content are nearly identical. Differences in APIs, log levels, and configuration will be noted where they have a practical impact.

## 1. Choose the Right Events to Log

Start with the question: **If this event appears in the logs at 3 a.m., what does it help answer?**

Prioritize events that represent a meaningful change or decision:

- **Service lifecycle:** startup success/failure; invalid required configuration; loss or recovery of connections to essential resources.
- **Business processing boundaries:** a request being accepted, completed, rejected, or canceled; a critical state-changing operation.
- **Abnormal conditions:** external dependency timeouts, retries, fallbacks, invalid data exceeding expected thresholds.
- **Failures requiring investigation:** incomplete tasks, unhandled exceptions at the responsible layer, resource errors preventing a transaction from succeeding.
- **Essential operational information:** operating mode, deployed version, component name, or readiness status; avoid logging configuration data that contains secrets.

There is no need to log every variable assignment, every loop iteration, or every successful request at `INFO` level. Depending on traffic volume, routine successful requests can be captured via access logs, traces, metrics, or sampling. Conversely, very rare but critical events need clear logs even if they seldom occur.

### Focus on Outcomes, Not Just Starting Actions

| Low-Value Log | Higher-Value Log | Why |
| --- | --- | --- |
| `Start processing` | `event=payment.started requestId=req-17 paymentId=pay-42` | Identifies the operation and IDs for tracing. |
| `Error occurred` | `event=payment.failed requestId=req-17 errorCode=UPSTREAM_TIMEOUT retryable=true` | Provides a categorizable cause and next-step guidance. |
| `Done` | `event=payment.completed paymentId=pay-42 outcome=accepted elapsedMs=28` | Shows the target entity, outcome, and time cost. |
| `Retrying...` | `event=inventory.retry requestId=req-17 attempt=2 maxAttempts=3 cause=timeout` | Shows which retry attempt this is and why. |

The examples above **illustrate message formatting**; the IDs and timings are not data from a real system. A message containing `key=value` pairs is still plain text if the backend is not configured to emit structured data.

## 2. Use the Right Severity Level

Log levels must be based on **significance to the operator**, not on message length or the code author's intuition.

| Purpose | Common SLF4J/Logback/Log4j 2 | Closest JUL Equivalent | Example |
| --- | --- | --- | --- |
| Very detailed information for investigation | `TRACE` | `FINER`, `FINEST` | Internal algorithm steps; usually disabled in production. |
| Diagnostic information | `DEBUG` | `FINE` | Logic paths, branch decisions, controlled technical values. |
| Normal but significant events | `INFO` | `INFO` | Service ready, important task completed. |
| Recoverable anomalies or conditions needing attention | `WARN` | `WARNING` | Fallback triggered, repeated retries, nearing resource exhaustion. |
| Failed operations requiring action | `ERROR` | `SEVERE` | Operation did not complete or an essential component is non-functional. |

**This is a semantic mapping, not a one-to-one API correspondence.** JUL also has `CONFIG`, `OFF`, and `ALL`. Agree on a team-wide convention instead of inventing new meanings per component.

For example, an HTTP 404 caused by a user requesting a non-existent path is usually not an `ERROR`-level server incident; it can be recorded by access logs or at `INFO/DEBUG` depending on the system. Conversely, a 404 from a downstream dependency when required data must exist may indicate a business error worth investigating. **Context determines severity.**

A few notes on levels:

1. Diagnostic logs generally belong at `DEBUG/FINE`; do not promote them to `INFO` just to see them immediately during development.
2. Transient retries that succeed can be logged at `DEBUG` or `WARN` depending on impact; do not emit `ERROR` for every attempt if the overall workflow has not failed.
3. When an operation ultimately fails, emit one clear failure event at the processing boundary with a categorized cause.
4. Adjust levels per environment or package via configuration. Leaving `DEBUG/TRACE` enabled globally long-term increases costs and risks leaking data.

## 3. Give Every Event Enough Context to Trace

A useful message typically answers six questions: **when, where, what event, which entity is involved, what the outcome was, and what led to that outcome**.

Fields to consider:

| Field | Role | Recommendation |
| --- | --- | --- |
| `timestamp` | Time of the event | Consistent format with an explicit timezone; UTC is standard in distributed systems. |
| `level` | Severity classification | Keep standardized by convention; avoid multiple variants with the same meaning. |
| `logger` / `component` | Emitting component | Stable package/class name or service name. |
| `event` / `eventName` | Event type | E.g., `order.accepted`, `inventory.fallback`, `payment.failed`; clear and stable naming. |
| `requestId` / `correlationId` | Correlate events within the same flow | Propagate across relevant layers, while considering trustworthiness and sensitive data. |
| `traceId` / `spanId` | Link logs with distributed tracing | Emit only when an actual trace context exists; never fabricate values. |
| `orderId` / `jobId` | Identify the affected entity | Use technical identifiers appropriate for access permissions. |
| `outcome` / `status` | Observed result | `success`, `rejected`, `fallback`, `failed`, or a meaningful status code. |
| `durationMs` / `elapsedMs` | Measured time cost | Include units and measure with an appropriate clock; do not guess numbers. |
| `errorCode` / `reason` | Categorizable cause | Stable codes like `TIMEOUT`, `VALIDATION_FAILED`; do not rely solely on exception text. |

You do not need to cram every field into every line. A simple success event may only need `event`, `requestId`, `outcome`, and `elapsedMs`; a network dependency failure may also need `dependency`, `attempt`, and `errorCode`. Field names and data types should remain consistent across layers so search systems do not have to handle variants like `request_id`, `requestID`, and `rid` for the same concept.

**Propagating context across threads:** MDC/Thread Context in some frameworks is bound to a thread. When using `ExecutorService`, `CompletableFuture`, virtual threads, or reactive pipelines, context is not automatically propagated according to business flow in all cases. Use the appropriate propagation mechanism and clear the context after processing to avoid mixing identifiers across requests. Core JUL does not have a built-in MDC like SLF4J/Logback.

## 4. Write Accurate, Consistent, and Actionable Messages

Messages should describe **what happened**, avoiding vague impressions. Use stable event names and clear attributes, because both humans and search systems need to recognize the same event across deployments.

Good design practices:

- Use clear verbs and outcomes: `invoice.rejected`, `cache.refresh.failed`, `connection.recovered`.
- State a categorizable cause: `reason=quota_exceeded` or `errorCode=UPSTREAM_TIMEOUT`.
- Log `success` only when the operation actually succeeded; do not place `completed` at the end of a `finally` block if the flow can throw an exception.
- Indicate retry/fallback status when it affects correctness, latency, or service quality.
- Distinguish measured values from estimates: `elapsedMs=250` is measured; `estimatedRemainingMs` is an estimate if present.

Avoid encoding all operational meaning into a free-form exception string, as those strings can change across library versions. Use a stable `errorCode` to group errors, and attach a controlled message/`Throwable` to investigate the root cause.

An event name alone does not turn a message into structured data. If you need to search and aggregate by fields, configure the backend to output JSON with dedicated fields rather than relying on regular expressions to parse strings.

## 5. Log Errors and Exceptions at the Responsible Layer

Error logs are most useful when they combine **business context + technical cause + final outcome**. In Java, pass the entire `Throwable` object when a stack trace is needed; logging only `ex.getMessage()` often loses the call chain and nested causes.

The following snippet **illustrates a processing boundary**, assuming `logger`, `requestId`, and `performCheckout()` already exist; this is not a standalone program:

```java
try {
    performCheckout();
} catch (RuntimeException ex) {
    // Only log here when this layer is responsible for recording the failure.
    logger.log(
        java.util.logging.Level.SEVERE,
        "event=checkout.failed requestId=" + requestId,
        ex
    );
    throw ex;
}
```

If upper calling layers also always log the same exception, logging and rethrowing creates **duplicate error records** for a single cause. Therefore, clearly decide which layer is responsible for logging the final error (e.g., entrypoint, job runner, or exception handler). Lower layers can throw exceptions enriched with better context without logging them immediately.

Distinguish three situations:

- **Handled error with a valid outcome:** for example, a cache lookup fails and the source data is fetched successfully; log the fallback at an appropriate level rather than defaulting to `SEVERE`.
- **Error causing an operation to fail:** log the final event at the business boundary with `errorCode`, correlation ID, and `Throwable` if helpful.
- **Expected input-data error:** for example, validation rejection; do not turn every validation error into a long stack trace. Log a standardized rejection category and avoid exposing user data.

Never swallow an exception in a `catch` block just to log a line and return "success". Logging is not a substitute for proper error handling and returning accurate results.

## 6. Reduce Noise, Duplicate Logs, and Data Volume

Excessive logging obscures important events and increases storage, transport, and search costs. High-load systems especially need to distinguish **signals requiring investigation** from **continuous statistical data**.

Common techniques:

1. **Log at meaningful boundaries:** one final outcome per operation, plus anomalies or significant state transitions. Do not log "entered method X" in every method.
2. **Avoid duplicate logging of the same error:** if an exception passes through five layers, there is no need to log five identical stack traces.
3. **Use metrics for statistics:** total requests, error rates, p95/p99 latency, and retry counts fit counters/histograms far better than an `INFO` log for every occurrence.
4. **Apply sensible sampling/rate limiting:** high-volume success flows can be sampled; be cautious with rare errors, audit events, or security events.
5. **Aggregate repeated events appropriately:** instead of thousands of identical "connection failed" lines, report the count, first/last occurrence timestamps, and recovery status while keeping the evidence needed for investigation.
6. **Separate operational levels from diagnostic levels:** keep detailed diagnostics at `FINE/DEBUG` and enable them selectively when needed, with a time limit to turn them off.

For example, at 50,000 requests/second, logging one success line per request produces 3 million lines/minute. Consider access logs, retention, sampling, and useful data volume before designing.

However, logs can be dropped due to sampling, write failures, buffering, or configuration. **Do not treat regular application logs as a transaction ledger or audit trail guaranteed never to lose events.** High-durability/audit requirements need dedicated persistent storage and controls.

## 7. Consider Performance at the Logger Call Site

Logging incurs costs for message construction, object conversion, stack trace capture, JSON formatting, memory allocation, I/O synchronization, and network transmission.

With JUL, prefer parameter passing over expensive string concatenation before level checks:

```java
// Illustrates the call only; assumes logger and orderId already exist.
logger.log(java.util.logging.Level.FINE, "Validating order {0}", orderId);
```

In JUL, placeholders use `{0}`, `{1}`; in SLF4J, the common syntax is `{}`. Use the right API. Parameterization **does not guarantee all costs are deferred**: argument expressions are still evaluated by Java before the method is invoked. If computing the data is genuinely expensive, check the level or use an API that accepts a `Supplier` where appropriate:

```java
if (logger.isLoggable(java.util.logging.Level.FINE)) {
    logger.fine(() -> "diagnostic=" + computeExpensiveDiagnostic());
}
```

This is an **illustrative snippet**, assuming `computeExpensiveDiagnostic()` is an existing method. When using `logger.fine(Supplier<String>)`, the supplier is only invoked if the logger accepts that level; do not use it as a substitute for guarding side effects in diagnostic methods. Putting expensive work inside the supplier is what saves cost.

When switching to asynchronous logging, understand queue policies, buffer overflow behavior, shutdown/flush handling, and potential log loss if the process crashes. Asynchronous logging reduces thread blocking, but it does not automatically guarantee durability for every record or strict global ordering across multiple processes.

## 8. Protect Data and Prevent Log Injection

Logs may be read by multiple operational systems, stored long-term, and forwarded to third-party infrastructure. Treat logs as a **data pipeline** that must be controlled.

**Never log raw:** passwords, access/refresh tokens, session cookies, API keys, private keys, payment card numbers, authentication payloads, or unnecessary personal data. Avoid logging entire requests/responses or calling `toString()` on sensitive objects, as new fields can accidentally appear after code changes.

Instead:

- Log only **necessary fields**; prefer error codes, operation codes, or approved internal identifiers.
- Mask/redact data at the source and in downstream receivers where required; never treat "encrypted in transit" as an excuse to log secrets.
- Do not blindly trust user-supplied data (e.g., `userAgent`, paths, HTTP headers). Newline/control characters can forge log lines. For text logs, apply escaping/sanitization and length limits; for JSON, use a standard encoder rather than manual JSON string concatenation.
- Configure proper access controls, retention, and deletion policies; security events must be handled according to dedicated policies.

Example to avoid:

```java
// Wrong because this may expose a secret in the logging system.
logger.info("Login failed, token=" + accessToken);
```

Replace this with categorized diagnostic information, such as `event=auth.denied reason=expired_credential requestId=req-17`, provided `requestId` is controlled. Never use a token as a correlation ID.

## 9. Runnable Java 17 Example: Short, Clear, Context-Rich Logging

This example uses **built-in JDK JUL**, simulating a checkout request being accepted, inventory falling back to a cached strategy, and checkout completing. Example data is fixed so the output is deterministic and verifiable.

Save the following as **`UsefulLoggingDemo.java`**:

```java
import java.util.logging.Formatter;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;
import java.util.logging.StreamHandler;

public class UsefulLoggingDemo {
    private static final Logger LOG =
            Logger.getLogger("demo.checkout");

    public static void main(String[] args) {
        // Use a fixed formatter so the example produces stable output.
        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.INFO);

        Handler output = new StreamHandler(
                System.out,
                new Formatter() {
                    @Override
                    public String format(LogRecord record) {
                        return record.getLevel().getName()
                                + " "
                                + formatMessage(record)
                                + System.lineSeparator();
                    }
                }
        );
        output.setLevel(Level.ALL);
        LOG.addHandler(output);

        String requestId = "req-17";
        String orderId = "ord-42";

        LOG.log(
                Level.FINE,
                "event=checkout.validation_started requestId={0}",
                requestId
        );

        LOG.log(
                Level.INFO,
                "event=checkout.accepted requestId={0} orderId={1}",
                new Object[]{requestId, orderId}
        );

        boolean inventoryUnavailable = true;
        if (inventoryUnavailable) {
            LOG.log(
                    Level.WARNING,
                    "event=inventory.fallback requestId={0} "
                    + "orderId={1} strategy={2}",
                    new Object[]{requestId, orderId, "cached"}
            );
        }

        long elapsedMs = 23L; // Simulated value, not an actual timing measurement.
        LOG.log(
                Level.INFO,
                "event=checkout.completed requestId={0} "
                + "outcome={1} elapsedMs={2}",
                new Object[]{requestId, "success", elapsedMs}
        );

        output.flush();
        LOG.removeHandler(output);
    }
}
```

Run on JDK 17 or later:

```bash
javac UsefulLoggingDemo.java
java UsefulLoggingDemo
```

**Exact standard output:**

```text
INFO event=checkout.accepted requestId=req-17 orderId=ord-42
WARNING event=inventory.fallback requestId=req-17 orderId=ord-42 strategy=cached
INFO event=checkout.completed requestId=req-17 outcome=success elapsedMs=23
```

Key takeaways:

1. `event` has a stable name, helping readers understand the **event type**; `requestId` and `orderId` provide consistent context.
2. `checkout.accepted` and `checkout.completed` are distinct states; the `completed` event is emitted only after the simulated processing succeeds.
3. The fallback is logged at `WARNING` because it is an abnormal condition that was recovered from; it does not mark the entire checkout as failed.
4. `FINE` is not printed because the logger threshold is `INFO`. Setting the handler to `ALL` cannot recover events already filtered out by the logger.
5. `elapsedMs=23` is a **simulated** number. In production code, measure durations with `System.nanoTime()` rather than using wall-clock timestamps to calculate elapsed time.
6. `formatMessage(record)` resolves JUL's `{0}`, `{1}`, `{2}` placeholders; `flush()` pushes buffered output from `StreamHandler`. Disabling parent handlers prevents duplicate log lines from parent JUL configuration.

The `key=value` format here is still a **text log**, chosen so the example runs without external libraries. In real systems, consider a formatter/encoder that emits dedicated JSON fields along with correlation/trace context propagation. Do not build a custom manual JSON concatenator just for logging.

## 10. Checking Log Quality Against Real Scenarios

When reviewing a new log event, run through this checklist:

| Review Question | Sign That Needs Fixing |
| --- | --- |
| When an incident occurs, what operational question does this line help answer? | Only says `Enter method`, `Hello`, `Done`. |
| Does the log accurately reflect the **event, outcome**, and timing? | Logs "success" before committing, or logs "completed" even when an exception is thrown. |
| Can two requests or two entities of the same type be distinguished? | Missing necessary request/job ID or unstable identifier fields. |
| Is the severity consistent with the impact? | Routine validation logged as `SEVERE`, unrecoverable errors logged as `DEBUG`. |
| On failure, are both context and technical cause included? | Only logs `ex.getMessage()`, missing error code, missing stack trace when needed. |
| Are logs duplicated or scaling per loop iteration without adding value? | Every layer logs the same stack trace; every item emits an `INFO` line. |
| Is the message suitable for searching/aggregating? | Field names vary across classes, missing units, all state buried in free-form text. |
| Could it leak sensitive data or allow log injection? | Tokens, objects containing personal data, or multiline inputs concatenated directly. |
| Are cost and data volume under control? | Debug enabled by default, heavy formatter, no retention or log rotation policy. |

**Before-and-after decision example:** Instead of logging `"Send request"` when starting an inventory call and `"Error"` on timeout, emit an `inventory.timeout` event where the outcome is known, including `requestId`, `dependency`, `attempt`, `timeoutMs`, and `outcome`; if a fallback occurs, emit a separate `inventory.fallback` event only when the fallback actually happens. This lets operators distinguish "one call failed but the request was saved" from "the entire request failed."

A practical rule of thumb: **good logs are verifiable, actionable for investigation, and introduce no extra risk**. Keep messages concise yet context-rich, and let metrics and traces do the jobs they are better suited for.