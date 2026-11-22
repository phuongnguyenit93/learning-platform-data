# Recoverable Errors in Exception Logging (Java)

## 1. Understanding Recoverable Errors

In Java, a **recoverable error** is an abnormal situation for which the program has a designed recovery path: safe retry, using a fallback, returning a controlled business error, or continuing with a still-valid state. For example, an external service call times out but succeeds on retry, a cache fails while the source data remains accessible, or an optional configuration is missing and has a safe default value.

**Catching an exception does not mean it has been successfully handled.** A catch block that only prints a message and ignores the error can leave the system continuing with invalid data. Exception handling decides how the program reacts; exception logging creates evidence so developers and operators can understand what happened.

Recoverability **depends on context**. An `IOException` when reading from a cache can be handled by reading from the database, whereas an `IOException` when writing mandatory financial data may require the transaction to fail. Checked exceptions and unchecked exceptions are merely Java's way of categorizing declaration/catching obligations; they do not inherently correspond to the severity of an incident.

Within a request, you should distinguish:

- **Attempt failed:** An individual attempt failed; recovery mechanisms remain available.
- **Recovered:** The request or operation ultimately succeeded after retry/fallback.
- **Degraded:** The system returns a result compliant with its contract, but had to use a fallback or reduce part of its functionality.
- **Operation failed:** No safe handling path remains; the operation ultimately failed and must return an appropriate error result.

A request may have three failed attempts but **no final operation failure** if the fourth attempt succeeds. Logs and metrics must clearly reflect this distinction.

## 2. Choosing Log Levels by Error Impact

Depending on the Java logging library, log level names differ. Java Util Logging (**java.util.logging**, JUL) uses **SEVERE, WARNING, INFO, CONFIG, FINE, FINER, FINEST**. SLF4J and common backends typically use **ERROR, WARN, INFO, DEBUG, TRACE**.

| State | Suggested JUL | Suggested SLF4J | Rationale |
| --- | --- | --- | --- |
| A retry fails but recovers as designed | FINE or WARNING depending on abnormality | DEBUG or WARN | Avoids misleading on-call engineers into thinking every attempt is a total failure |
| Fallback is triggered and service is degraded | WARNING | WARN | System is operating off the primary path and warrants monitoring |
| Completed after recovery | INFO if the event has operational value | INFO | Indicates the final outcome succeeded |
| Invalid user input per API contract | Usually does not need SEVERE; INFO/FINE or no log | INFO/DEBUG or no log | Validated input errors are not necessarily system failures operationally |
| Critical request fails after all recovery attempts | SEVERE | ERROR | Must clearly record the failure outcome and root cause |
| System invariant violated or unfixed bug | SEVERE at final handling boundary | ERROR at final handling boundary | Usually requires preserving stack trace and investigating |

This is a guideline for choosing levels, **not an exact mapping between JUL and SLF4J across all bridges**. Choose levels based on impact, frequency, actionability, and project conventions.

For example, network retries occurring 100 times per second that mostly succeed may only need FINE/DEBUG along with a **retry_count** metric. Logging WARNING with a stack trace for every attempt can generate excessive log volume. Conversely, a rarely triggered fallback in a critical feature may be worth logging at WARNING.

## 3. Common Error-Handling Strategies

### 3.1. Bounded Retry

Retry is useful when an error is likely transient and the operation is **safe to execute again**. It can be applied to certain connection errors, timeouts, or 503 responses, depending on the API contract and operation type.

A proper workflow:

1. Identify the specific exception types eligible for retry; do not catch `Exception` broadly.
2. Set limits on attempt count and total duration; avoid infinite loops.
3. If needed, apply backoff and jitter to reduce the risk of many clients retrying simultaneously.
4. Respect deadlines, cancellation, and thread interruption signals.
5. On success, return the result and emit a recovered event when appropriate.
6. When attempts are exhausted, log the final failure at the responsible boundary, preserving the cause.

**A timeout does not prove the server did not execute the operation.** For payments, order creation, sending emails, or write operations, retrying can cause duplicate side effects without an idempotency key or deduplication mechanism. Do not retry a non-idempotent operation just because an `IOException` occurred.

### 3.2. Controlled Fallback

For example, the cache is unreachable but the database is still operational:

~~~text
Read cache
  -> IOException
  -> switch to reading from database
  -> database returns valid data
  -> operation succeeds, record fallback if noteworthy
~~~

A fallback only counts as recovery if it satisfies the business contract. Never substitute fake default values for payment data, access permissions, or mandatory encryption keys.

If fallbacks occur continuously, it may indicate performance degradation that needs attention. You should track metrics on fallback count and impact; avoid spamming the same warning for every single request.

### 3.3. Converting Input Errors into Controlled Responses

A user submitting a malformed date may receive HTTP 400 or a validation message per the API contract. This is an expected input error and does not necessarily require an ERROR log with a stack trace. Avoid logging the entire request payload as it may contain personal data.

### 3.4. Propagating When Recovery Is Not Possible

The Repository layer might not know whether the business requirement allows retries. In that case, propagate the exception—optionally wrapping it with context and cause—so the Service layer or API boundary can decide. Logging SEVERE at every layer and then rethrowing causes a single incident to appear multiple times in the logs.

## 4. Standalone Java 17 Example: Transient Failure and Exhausted Retries

This example uses **java.util.logging (JUL)** built into the JDK. A simulated dependency encounters I/O errors before returning a result; there are no real network calls or side effects.

- **req-A** fails once, then succeeds on the second attempt.
- **req-B** fails until both attempts are exhausted. The processing method logs the final error and rethrows `IOException`; the caller turns it into a controlled failure result without duplicate logging.

Create the file **RecoverableExceptionLoggingDemo.java**:

~~~java
import java.io.IOException;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class RecoverableExceptionLoggingDemo {
    private static final Logger LOGGER =
            Logger.getLogger(RecoverableExceptionLoggingDemo.class.getName());

    public static void main(String[] args) throws Exception {
        Handler output = new Handler() {
            @Override
            public void publish(LogRecord record) {
                if (!isLoggable(record)) {
                    return;
                }

                String cause = record.getThrown() == null
                        ? ""
                        : " | cause="
                            + record.getThrown().getClass().getSimpleName();

                System.out.println(
                        record.getLevel().getName()
                        + " | " + record.getMessage()
                        + cause);
            }

            @Override
            public void flush() {
                // No buffer to flush.
            }

            @Override
            public void close() {
                // Does not own any resources to close.
            }
        };

        output.setLevel(Level.ALL);
        LOGGER.setUseParentHandlers(false);
        LOGGER.setLevel(Level.INFO);
        LOGGER.addHandler(output);

        try {
            System.out.println("SCENARIO | temporary failure");
            process("req-A", new ExampleGateway(1), 3);

            System.out.println("SCENARIO | retries exhausted");
            try {
                process("req-B", new ExampleGateway(9), 2);
            } catch (IOException e) {
                // Exception was already logged at the point where the final outcome was determined.
                System.out.println("RESULT | req-B | failed");
            }
        } finally {
            LOGGER.removeHandler(output);
            output.close();
        }
    }

    private static void process(
            String requestId,
            ExampleGateway gateway,
            int maxAttempts) throws IOException {

        if (maxAttempts < 1) {
            throw new IllegalArgumentException("maxAttempts must be >= 1");
        }

        for (int attempt = 1; attempt <= maxAttempts; attempt++) {
            try {
                String result = gateway.send();

                if (attempt > 1) {
                    LOGGER.info(
                            "RECOVERED requestId=" + requestId
                            + " attempts=" + attempt);
                }

                System.out.println(
                        "RESULT | " + requestId + " | " + result);
                return;
            } catch (IOException e) {
                if (attempt < maxAttempts) {
                    LOGGER.log(
                            Level.WARNING,
                            "RETRY_SCHEDULED requestId=" + requestId
                            + " attempt=" + attempt,
                            e);
                } else {
                    LOGGER.log(
                            Level.SEVERE,
                            "OPERATION_FAILED requestId=" + requestId
                            + " attempts=" + attempt,
                            e);
                    throw e;
                }
            }
        }
    }

    private static final class ExampleGateway {
        private int failuresRemaining;

        private ExampleGateway(int failuresBeforeSuccess) {
            failuresRemaining = failuresBeforeSuccess;
        }

        String send() throws IOException {
            if (failuresRemaining > 0) {
                failuresRemaining--;
                throw new IOException("temporary unavailability");
            }
            return "accepted";
        }
    }
}
~~~

Compile and run with **JDK 17 or later**:

~~~bash
javac -encoding UTF-8 RecoverableExceptionLoggingDemo.java
java RecoverableExceptionLoggingDemo
~~~

**Exact stdout per program logic:**

~~~text
SCENARIO | temporary failure
WARNING | RETRY_SCHEDULED requestId=req-A attempt=1 | cause=IOException
INFO | RECOVERED requestId=req-A attempts=2
RESULT | req-A | accepted
SCENARIO | retries exhausted
WARNING | RETRY_SCHEDULED requestId=req-B attempt=1 | cause=IOException
SEVERE | OPERATION_FAILED requestId=req-B attempts=2 | cause=IOException
RESULT | req-B | failed
~~~

Explanation:

1. **req-A**'s first attempt throws `IOException`. Since attempts remain, the method logs WARNING with code **RETRY_SCHEDULED** and a reference to the `Throwable`.
2. **req-A**'s second attempt returns **accepted**, so it logs INFO **RECOVERED**. No SEVERE is logged because the request ultimately succeeded.
3. For **req-B**, the first attempt is only an attempt failure; the second is the final failure, so it logs **SEVERE OPERATION_FAILED** and executes **throw e**.
4. The caller catches the exception and represents the failed result **without logging the same exception again**. A single failed operation is not turned into multiple severe errors by duplicate logging.
5. **LOGGER.log(Level, String, Throwable)** retains the `Throwable` in the log record. The demo Handler only prints the `IOException` type to keep output simple; a production Formatter can print the stack trace and cause chain.
6. The Handler is set to **Level.ALL**, the Logger to **Level.INFO**, and **setUseParentHandlers(false)** prevents default log lines from parent Handlers. The demo Handler intentionally prints to **stdout**; JUL's standard `ConsoleHandler` typically prints to **stderr**.

This is an instructional example. Running in production requires adding timeouts, retry budgets, backoff/jitter, idempotency, transaction state, cancellation, and proper observability. In particular, **do not copy this retry loop for a real payment API** without duplicate-processing protections.

## 5. Logging Exceptions with Cause, Avoiding Lost Stack Traces

### 5.1. Logging Only getMessage() Is Not Enough for Investigation

Illustrative snippet inside a class that has `LOGGER` and a `readRemote()` method:

~~~java
try {
    readRemote();
} catch (IOException e) {
    LOGGER.warning("Remote failed: " + e.getMessage());
}
~~~

The message may show that an error occurred, but the `LogRecord` does not automatically contain the `Throwable` when only a string is passed. As a result, the stack trace, cause chain, and technical metadata for the Formatter are lost. Furthermore, some exception messages generated by dependencies may accidentally contain URLs, input data, or sensitive information.

When the cause is needed, use the JUL overload that accepts a **Throwable**:

~~~java
try {
    readRemote();
} catch (IOException e) {
    LOGGER.log(
            Level.WARNING,
            "REMOTE_READ_RETRYABLE operation=fetchCatalog",
            e);
}
~~~

**The two snippets above are examples placed inside a method that already has the relevant components; they are not standalone files.** Note: inside the catch block, you must actually retry, fall back, or propagate if you cannot handle it. Logging does not replace error handling.

### 5.2. Preserve the Cause When Wrapping Exceptions

~~~java
try {
    persistOrder(orderId);
} catch (IOException e) {
    throw new IllegalStateException(
            "Order persistence failed for request " + requestId,
            e);
}
~~~

The constructor overload taking **e** preserves the root cause. If a lower layer only adds context and rethrows, it usually does not need to log the error right there when an upper layer is responsible for logging the final failure. Logging the same stack trace in Repository, Service, and Controller typically creates more noise than help during investigation.

### 5.3. Counting Attempts Differs from Counting Operations

A request may have three **ATTEMPT_FAILED** lines but ultimately succeed. If a dashboard counts each of these lines as a failed request, the error rate will be inflated. You should use consistent **event_code**, **operation**, **attempt**, **request_id**, and **outcome** fields; metrics for the final outcome should be recorded at the operation completion boundary.

## 6. Configuring Log Levels for Recoverable Errors

JUL has thresholds at both the **Logger** and the **Handler**. For example:

~~~java
LOGGER.setLevel(Level.FINE);
handler.setLevel(Level.INFO);
~~~

A `LOGGER.fine(...)` call can still produce no output because the Handler blocks it. If the Logger is set to INFO, FINE may be blocked before a record is even created. In applications with multiple Handlers or loggers inheriting from parents, you must check the entire processing pipeline.

Typically, production uses **INFO** as a baseline and enables **FINE/DEBUG** per class during investigation. Normal retries can be logged at FINE; noteworthy recovery events use INFO; continuous fallbacks or degradation use WARNING; final failures of essential features use SEVERE. However, **there is no mandatory level scheme for every project**.

With JUL, avoid building expensive diagnostic strings before a call that may be filtered out:

~~~java
LOGGER.log(
        Level.FINE,
        () -> "Diagnostics: " + buildExpensiveDetails()
);
~~~

This is an illustrative snippet assuming **buildExpensiveDetails()** already exists. The `Supplier` form defers computing the message when the Logger does not accept FINE; the Handler can still filter it afterward. With SLF4J, the API uses a different placeholder syntax, typically **{}**; do not use SLF4J placeholders in JUL and expect similar automatic formatting.

## 7. Optional Configuration and Default-Value Fallbacks

Defaults can be used when a **non-mandatory** configuration is missing or malformed, provided the default value is safe and designed in advance. The following illustrative snippet sits inside a method that already has **Properties properties**, **long timeoutMillis**, and **LOGGER**:

~~~java
String raw = properties.getProperty("client.timeout.ms");

if (raw == null) {
    LOGGER.info("CONFIG_DEFAULT_USED key=client.timeout.ms");
    timeoutMillis = 2000L;
} else {
    try {
        long parsed = Long.parseLong(raw);
        if (parsed <= 0) {
            LOGGER.warning(
                    "INVALID_OPTIONAL_CONFIG key=client.timeout.ms");
            timeoutMillis = 2000L;
        } else {
            timeoutMillis = parsed;
        }
    } catch (NumberFormatException e) {
        LOGGER.log(
                Level.WARNING,
                "INVALID_OPTIONAL_CONFIG key=client.timeout.ms",
                e);
        timeoutMillis = 2000L;
    }
}
~~~

The 2000 ms value is only an example. Real projects must also validate upper bounds, timeout contracts, and security requirements. **Mandatory configurations** such as encryption keys or access permissions must never be silently replaced with dummy values just to let the application keep starting up.

## 8. Exceptions That Should Not Be Handled with Ordinary Retries

**InterruptedException** represents an interruption/cancellation signal while a thread is waiting. If the method cannot propagate this exception, it normally needs to restore the interrupt flag and exit work appropriately:

~~~java
try {
    Thread.sleep(500);
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    LOGGER.log(Level.FINE, "Retry wait interrupted", e);
    return;
}
~~~

This is an **illustrative snippet inside a void method**. If the method is allowed to declare `throws InterruptedException`, propagating it can also be appropriate. Do not swallow the cancellation signal and loop retries indefinitely.

**NullPointerException** from an internal bug or **IllegalStateException** for an invalid state usually requires fixing the logic, not catching and continuing. Serious **Error** types such as `OutOfMemoryError` should not be caught broadly like normal business errors.

**Do not catch `Exception` just to "make sure it doesn't fail."** A catch block should have a specific purpose: recover, translate the error into a defined result, close/roll back resources, or add context before passing up to the responsible layer. Use try-with-resources for `AutoCloseable` resources where appropriate to avoid leaks even when exceptions occur.

## 9. Why Duplicate Logging Is Harmful

Suppose a database write fails in the Repository. If the Repository logs ERROR and rethrows, the Service logs ERROR and rethrows, and the Controller logs ERROR again, the on-call engineer may see three errors that look like three separate incidents.

A clearer separation of responsibilities:

- **Repository:** propagate the exception or wrap it with cause and technical context; do not log a final error if it has not handled it.
- **Service:** perform valid retries/fallbacks; log a state-transition event when noteworthy.
- **API boundary or business completion layer:** knows whether the operation ultimately succeeded or failed and logs a single appropriate final error record.

There is no rigid rule that only one log may exist in every case; a specific diagnostic log at a lower layer and a summary log at the boundary can be reasonable if they carry **different information**. What to avoid is repeating the same exception and stack trace at every layer without adding context.

## 10. Structured Logging to Distinguish Transient from Final Errors

For recoverable errors, the following fields are valuable:

| Field | Purpose |
| --- | --- |
| **timestamp** | Event time, with an explicit timezone |
| **level** | Log level, such as WARNING or SEVERE |
| **service/logger_name** | Originating component |
| **event_code** | Stable code such as RETRY_SCHEDULED or OPERATION_FAILED |
| **request_id/trace_id** | Correlates attempts belonging to the same request |
| **operation** | Specific operation such as fetchCatalog |
| **attempt/max_attempts** | Current attempt and retry budget |
| **exception_type/cause** | Exception class and cause chain |
| **outcome** | retrying, recovered, degraded, or failed |

Conceptual JSON example:

~~~json
{
  "timestamp": "2026-11-09T10:00:00Z",
  "level": "WARN",
  "service": "checkout",
  "logger_name": "com.example.gateway.Client",
  "event_code": "RETRY_SCHEDULED",
  "request_id": "req-A",
  "operation": "authorize",
  "attempt": 1,
  "max_attempts": 3,
  "exception_type": "IOException",
  "outcome": "retrying"
}
~~~

**This is not JSON automatically generated by JUL.** You need an appropriate Formatter/encoder and correlation propagation mechanism. Event codes enable more reliable querying than matching message wording. Never include access tokens, passwords, session cookies, secret keys, payment payloads, or sensitive personal data in logs at any level.

## 11. Metrics and Alerting for Self-Healing Errors

Logs answer **what happened and why**. Metrics can answer **how many times and how severe the impact is**. For recoverable errors, you should observe:

- **retry_count / retry_rate:** How often retries are needed.
- **fallback_count / fallback_rate:** How often the fallback path is used.
- **operation_failure_rate:** Rate of operations that ultimately fail.
- **latency p95/p99:** Successful retries can still increase latency.
- **circuit-breaker state / dependency health:** Detects degrading dependencies.

For example, a request with four attempts where the first three fail and the last succeeds: metrics should reflect **three failed attempts** and **one successful operation**. Do not configure alerting to treat every WARNING/ERROR log as an incident requiring immediate paging.

If the log pipeline drops or samples logs, do not infer absolute request counts from logs without verifying reliability. Dedicated metrics and tracing complement logs in observing system behavior.

## 12. Cost and Safety of Exception Logging

If a service handles **1,000 requests/second**, **10%** require a retry, and each attempt failure logs a stack trace of about **2 KB**, the log volume from this alone is:

~~~text
1,000 requests/s × 10% = 100 retries/s
100 retries/s × 2,000 bytes = 200,000 bytes/s
200,000 bytes/s × 86,400 s = 17.28 GB/day
~~~

This figure does not even include indexing, metadata, or replication. When retries are frequent and successfully recovered, prefer FINE/DEBUG, aggregated metrics, or appropriate rate limiting; still retain evidence of important final failures.

Error data from third-party libraries is not safe by default. Exception messages may contain URLs, headers, or user information. Design redaction rules, read permissions, retention, and auditing for your logging system, and avoid logging raw requests/responses when only technical IDs are needed.

## 13. Common Mistakes and How to Fix Them

| Mistake in Code or Operations | Risk | How to Fix |
| --- | --- | --- |
| Catch `Exception` and ignore | Hides errors, leaves invalid state | Catch only what you handle; fall back or propagate properly |
| Log every retry as SEVERE | False alarms, inflated error rates | Separate ATTEMPT_FAILED from OPERATION_FAILED |
| Log only `e.getMessage()` | Loses `Throwable` and stack trace | Use the overload taking `Throwable` when needed |
| Log at every layer then rethrow | One error produces multiple duplicate records | Define clear boundaries for final error logging |
| Unbounded retries | Increases load, slows down, or loops infinitely | Limit attempt count, total duration, and use backoff |
| Retry non-idempotent side-effecting operations | Creates duplicate transactions/orders | Use idempotency keys and check API contracts |
| Ignore `InterruptedException` | Fails to stop task when cancelled | Propagate or restore the interrupt flag |
| Use defaults for mandatory configuration | Application runs incorrectly or unsafely | Fail in a controlled manner, no fake fallbacks |
| Log payloads/secrets at DEBUG | Data leakage | Log only necessary fields and apply redaction |
| Page based solely on error log line counts | Misrepresents impact, many false alerts | Use final-outcome metrics and SLOs |
| Log recovery before actual completion | Inaccurate audit trail | Only log recovered after the step is confirmed successful |

## 14. Checklist Before Completing a Catch Block

1. Verify whether **this exception is truly recoverable in the current context**.
2. Choose to retry, fall back, return a business error, or rethrow with cause.
3. Check **idempotency**, retry limits, deadlines, and state correctness.
4. Choose the log level based on **final outcome and impact**, not solely on the exception name.
5. Preserve `Throwable`/cause when diagnostics are needed and avoid keeping only the message.
6. Record event code, request ID, operation, attempt, and outcome where appropriate.
7. Do not duplicate logs for the same incident across multiple layers without added value.
8. Do not log tokens, passwords, or sensitive data; control access and retention.
9. Have metrics for retry/fallback/failure, as well as alert conditions when self-healing is no longer sufficient.
10. Ensure thread cancellation, rollback, and resource closing follow the contract.

## 15. Self-Check Questions

**1.** An `IOException` occurs once, but the retry succeeds. Is it mandatory to log SEVERE?

No. The final outcome succeeded; you can log FINE/WARNING for the attempt and INFO for recovered, depending on frequency and importance.

**2.** Does `Logger.warning(e.getMessage())` preserve the stack trace in the `LogRecord`?

No. You must pass the `Throwable` object using the appropriate overload when diagnostics are needed.

**3.** Why does a timeout during payment not automatically mean you should retry?

Because the server may have already executed the transaction and lost the response; retrying without idempotency can create duplicate payments.

**4.** A request has three failed attempts and then succeeds. How many final operation failures should be counted?

**Zero final operation failures**; that is three failed attempts and one successful operation.

**5.** Why shouldn't you catch `InterruptedException` and keep looping?

Because it is a cancellation signal. You need to propagate it or restore the interrupt flag and terminate processing appropriately.

**6.** A lower layer already logged an exception and rethrew it; is it always necessary for the upper layer to log the same exception again?

No. You should assign responsibility boundaries and avoid duplicate stack traces, unless there is genuinely useful, distinct information to add.

**Key takeaway:** A recoverable error is one with a **correct and bounded recovery path**. Record events according to their real impact, preserve the cause for investigation, distinguish individual attempt failures from final operation failures, and monitor both recovery and degradation to operate Java applications safely.
