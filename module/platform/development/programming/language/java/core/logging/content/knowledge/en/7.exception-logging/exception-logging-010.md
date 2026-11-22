# Checking Exception Logging in Java

## 1. Why Check Exception Logging?

When a Java application encounters an exception, exception handling and logging are two related but distinct responsibilities. A method may throw the right `Exception`, while the log may miss the cause, log at the wrong level, expose sensitive data, appear multiple times, or fail to reach the collection system. Therefore, **checking exception logging** means verifying that a failure scenario produces **a record with the right meaning, the right diagnostic content, and the right destination**.

Imagine a scenario where the payment gateway does not respond. The request eventually fails and the API returns an appropriate error code. If the log only writes `"Payment failed"`, the on-call operator does not know which request, which downstream dependency, which error code, or where the stack trace is. If every layer logs `ERROR` and then rethrows the same exception, a single transaction can produce five identical records. If the logger records accurately but the appender fails to forward the data, the monitoring system still sees no incident.

Verification needs to answer two groups of questions:

- **Directly in application code:** which exact event is emitted, at what level, from which logger, whether the original exception is attached, whether the required fields are present, and whether an error log is accidentally emitted on success?
- **Along the operational pipeline:** is the record formatted/encoded properly, does it reach the file/console/collector, is it filtered or duplicated, can it be traced by `trace_id`, and is any sensitive data exposed?

Both groups are necessary. A unit test capturing a `LogRecord` proves the application created the record; it **does not by itself prove** that JSON was encoded properly or that the centralized system actually received the log.

## 2. What Makes a Satisfactory Exception Log Record?

Example of a structured ERROR record:

```json
{
  "timestamp": "2026-01-01T10:15:30Z",
  "level": "ERROR",
  "service": "checkout",
  "environment": "prod",
  "logger": "com.example.payment.PaymentService",
  "event_code": "payment.failed",
  "error_code": "GATEWAY_UNAVAILABLE",
  "request_id": "req-7",
  "trace_id": "trace-42",
  "outcome": "failed",
  "exception_type": "java.lang.IllegalStateException",
  "message": "Không thể hoàn tất thanh toán"
}
```

This is a **log structure illustration**, not the default output of JUL or SLF4J. The stack trace may be stored in a separate field, inside the record body, or as an exception object depending on the backend.

Aspects to check:

| Aspect | Verification Question | Common Mistakes |
| --- | --- | --- |
| Event | Does `event_code` accurately express the failure type? | Overly generic codes like `unknown.error` or a `"failed"` code before retries are exhausted. |
| Level | Is `ERROR`/`SEVERE` used for final failures per policy? | Logging ERROR for valid rejections, or only logging DEBUG when an operation truly fails. |
| Source | Do the logger name and service match the handling component? | Using a single unclear logger name for the entire application. |
| Context | Are `request_id`/`trace_id`, error code, and target entity present when allowed? | Unable to correlate logs with a request or job. |
| Exception | Are the `Throwable` and cause chain included when needed? | Logging only `ex.getMessage()`, losing the error type and origin location. |
| Count | Is one logical failure logged repeatedly across multiple layers? | The same exception is logged in the repository, service, and controller. |
| Output | Do the formatter, handler, and collector preserve enough information? | Recording a log with a Throwable, but the encoder strips the stack trace. |
| Sensitive data | Are tokens, passwords, payment details, or private data present? | Logging the entire request body or an exception message containing secrets. |
| Behavior | Does logging alter the outcome of exception handling? | Swallowing the error after logging, or throwing a new error that drops the cause. |

**Criteria must be tied to the semantics of the operation.** A failed retry attempt that later recovers may warrant `WARN`; a final failure that prevents a transaction from completing usually warrants `ERROR`. In `java.util.logging` (JUL), the constant closest in meaning to ERROR is **`Level.SEVERE`**; JUL has no `Level.ERROR`. SLF4J/Logback and `System.Logger` have the level name `ERROR`.

## 3. Choosing the Right Logging Point to Check the Right Thing

A common pattern when an exception propagates across multiple layers:

```text
Repository: calls database -> throws SQLException
    |
    v
Service: adds context, converts to PaymentStorageException
    |
    v
API boundary: decides request failed -> logs one ERROR with cause
    |
    v
Returns error response per API contract
```

There is no rigid rule saying "only log once per exception." A lower layer may need its own technical event, and an upper layer needs the final business event; two events with different meanings remain valid. However, **logging + rethrowing the same error with the same content at every layer** easily causes duplicates and skews counts.

With retries:

```text
payment.attempt_failed, attempt=1 -> WARN
payment.attempt_failed, attempt=2 -> WARN
payment.failed, attempts=3         -> ERROR
```

If the final attempt succeeds, the `payment.failed` event meaning "the logical operation ultimately failed" **should not appear**. When testing, check the success path, the recovered retry path, and the final failure path; do not just trigger an exception and assert "there is an ERROR line."

For HTTP, a valid `400` or `404` is usually not a system error requiring ERROR. A `500` response also does not guarantee there is exactly one ERROR line because a proxy or infrastructure layer may generate the response before the application logs anything. Therefore, **the number of ERROR log records does not automatically equal the number of failed requests**; measuring service error rates requires metrics or explicitly defined request-completion events.

## 4. Two Verification Layers: In-JVM Records and Formatted Output

### 4.1. Checking In-JVM Records

In JUL, `LogRecord` stores rich information that can be inspected directly:

- `getLevel()`: the log level.
- `getLoggerName()`: the source logger name.
- `getMessage()`: the raw message, which may be a template with parameters.
- `getParameters()`: parameters used when formatting the message, if any.
- `getThrown()`: the exception attached to the record, if any.
- `getInstant()`: the timestamp of the record.
- `getThreadID()` is a legacy API; in modern Java you may inspect thread information, but do not rely on fixed values in tests.

Checking `record.getThrown()` is more reliable than searching for the word `Exception` in arbitrarily formatted output. If code passes a Throwable object to `Logger.log(Level.SEVERE, message, throwable)`, JUL retains it in `LogRecord` so the formatter can output the stack trace. **Having a Throwable in LogRecord does not guarantee every formatter will print the stack trace.**

### 4.2. Checking Formatted Records

The formatter produces the text or JSON that the collection system sees. Additional checks are needed to verify that:

1. Level, event code, and context fields are output with the right types and names.
2. The Throwable, stack trace, and cause chain are represented according to the required contract.
3. Values containing quotes, newlines, and Unicode characters are escaped properly without breaking JSON or creating log injection.
4. Sensitive data is masked or stripped before leaving the application.
5. An event is not output twice to **the same destination** because both parent and child handlers/appenders are active.

These steps are usually **integration tests of the encoder/appender/collector**. Testing verbatim output strings down to every timestamp, thread, or stack trace line number is brittle. Check stable fields or parse the JSON and assert individual properties; only compare the full string when the format itself is a contract that must be preserved.

## 5. Runnable Java 17 Example: Capturing and Checking Error Logs with a Handler

This example uses **JUL built into the JDK**, requiring no JUnit or external libraries. We create a handler that stores `LogRecord` instances in memory, run a success case and a failure case, and then verify the key assertions.

Goals of the example:

- No ERROR/SEVERE on successful processing.
- On final failure, **exactly one** `SEVERE`.
- Correct logger name, event code, error code, and request ID.
- `LogRecord` retains the original `IllegalStateException`.
- Logger configuration is restored after the check to avoid affecting other code in the same JVM.

Save as `ErrorLogCheckDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class ErrorLogCheckDemo {
    private static final Logger LOG =
            Logger.getLogger("demo.payment");

    private static final String ERROR_MESSAGE =
            "event_code=payment.failed "
            + "error_code=GATEWAY_UNAVAILABLE "
            + "request_id=req-7";

    static final class CapturingHandler extends Handler {
        private final List<LogRecord> events = new ArrayList<>();

        @Override
        public void publish(LogRecord record) {
            if (isLoggable(record)) {
                events.add(record);
            }
        }

        List<LogRecord> snapshot() {
            return List.copyOf(events);
        }

        @Override
        public void flush() {
            // In-memory, no output stream to flush.
        }

        @Override
        public void close() {
            // Owns no external resources.
        }
    }

    private static boolean processPayment(boolean gatewayFails) {
        try {
            if (gatewayFails) {
                throw new IllegalStateException("gateway unavailable");
            }
            return true;
        } catch (IllegalStateException failure) {
            LOG.log(Level.SEVERE, ERROR_MESSAGE, failure);
            return false;
        }
    }

    private static void require(boolean condition, String reason) {
        if (!condition) {
            throw new AssertionError(reason);
        }
    }

    public static void main(String[] args) {
        Level previousLevel = LOG.getLevel();
        boolean previousUseParentHandlers = LOG.getUseParentHandlers();

        CapturingHandler capture = new CapturingHandler();
        capture.setLevel(Level.ALL);
        LOG.setLevel(Level.ALL);
        LOG.setUseParentHandlers(false);
        LOG.addHandler(capture);

        try {
            require(processPayment(false), "success should return true");
            require(capture.snapshot().isEmpty(),
                    "success must not produce an error log");

            require(!processPayment(true),
                    "failure should return false");

            List<LogRecord> records = capture.snapshot();
            require(records.size() == 1, "expected exactly one error");

            LogRecord error = records.get(0);
            require(error.getLevel() == Level.SEVERE, "wrong level");
            require("demo.payment".equals(error.getLoggerName()),
                    "wrong logger");
            require(ERROR_MESSAGE.equals(error.getMessage()),
                    "missing event metadata");
            require(error.getThrown() instanceof IllegalStateException,
                    "missing original exception");
            require("gateway unavailable".equals(
                    error.getThrown().getMessage()), "wrong cause");

            System.out.println("PASS success_without_error");
            System.out.println("PASS error_count=1");
            System.out.println("PASS level=SEVERE");
            System.out.println("PASS event_code=payment.failed");
            System.out.println("PASS throwable=IllegalStateException");
        } finally {
            LOG.removeHandler(capture);
            LOG.setLevel(previousLevel);
            LOG.setUseParentHandlers(previousUseParentHandlers);
            capture.close();
        }
    }
}
```

Run with JDK 17 or later:

```bash
javac ErrorLogCheckDemo.java
java ErrorLogCheckDemo
```

**Expected stdout (exact):**

```text
PASS success_without_error
PASS error_count=1
PASS level=SEVERE
PASS event_code=payment.failed
PASS throwable=IllegalStateException
```

### Example Breakdown

- `CapturingHandler.publish` receives a `LogRecord` when the handler's level and filter allow it. In a test harness, the handler does not need to write to a file or connect over the network.
- `LOG.setLevel(Level.ALL)` enables all levels at the source logger, and `capture.setLevel(Level.ALL)` performs no additional filtering. If the logger is set to `OFF` or the handler does not accept that level, the log-capturing test will collect no data.
- `LOG.setUseParentHandlers(false)` prevents records from propagating to parent logger handlers, avoiding extra console output that could pollute results. This is purely test isolation configuration.
- `processPayment(false)` emits no ERROR; `processPayment(true)` simulates a final failure outcome and emits exactly one `SEVERE` with the exception. The `catch` block handles it and returns `false`, so the exception does not escape the method; the test verifies both behavior and logging together.
- Checking `records.size() == 1` catches accidental duplicate logging. However, in a system with many log types during the same flow, **filter by `event_code` and specific level** rather than assuming the total log count must be 1.
- `getThrown()` verifies the exception is still present. Because the handler only captures records in memory, it **does not print the stack trace**; a separate formatter test is needed if the criterion is "the operator sees the stack trace."
- The `finally` block removes the handler and restores the level and propagation configuration. JUL loggers are shared objects by name within the JVM, so tests should not leave configuration changes behind after running.

**Note:** the code runs sequentially to keep the test predictable. The `ArrayList` in this example handler is **not safe for concurrent writes from multiple threads**. If the application logs concurrently, use a concurrency-safe collector and synchronize waiting for records; do not copy this illustrative handler into production.

## 6. How to Test When Using SLF4J, Logback, and JUnit

Many Spring or Java server applications use SLF4J as the API and Logback as the backend. A typical call looks like:

```java
try {
    paymentGateway.charge(orderId);
} catch (GatewayException exception) {
    log.error("event_code=payment.failed order_id={}", orderId, exception);
    throw exception;
}
```

The snippet above is **illustrative**, not a standalone program: `paymentGateway`, `GatewayException`, `orderId`, and `log` belong to a specific application. In SLF4J, passing `Throwable` as the final argument to a formatting overload lets the backend store the cause and output the stack trace. In real designs, decide which layer is responsible for logging the final error so outer layers do not log the same error again.

A common testing approach with Logback is attaching a **`ListAppender<ILoggingEvent>`** to the logger under test; after running the scenario, read the event list and check:

- Whether `ILoggingEvent.getLevel()` equals `ch.qos.logback.classic.Level.ERROR`.
- Whether `getLoggerName()` matches the logger/class under test.
- Whether `getFormattedMessage()` contains the event code and stable fields.
- Whether `getThrowableProxy()` contains the expected exception type and cause.
- For structured logging, whether the backend preserves key-value pairs such as `event_code` and `request_id`.

When using JUnit 5, the corresponding checks can be written with `assertEquals`, `assertNotNull`, `assertTrue`, or the project's existing assertion library. Examples like this **require SLF4J/Logback/JUnit dependencies and proper backend configuration**, unlike the standalone JUL program in Section 5.

A safe test procedure with a temporary appender:

1. Create a dedicated appender and call `start()` before attaching it.
2. Attach it to the exact logger to observe.
3. Run the test scenario and read events; for asynchronous backends, use a bounded wait with an explicit condition.
4. In `finally`, detach the appender and call `stop()`; restore the logger level, additivity, and any modified configuration.
5. Avoid running tests in parallel if they mutate the same global logger/configuration without isolation, as records from another test may leak into the list.

Do not assert verbatim against a stack trace with fixed source line numbers and thread names. After refactoring, location details may change even when behavior remains correct. Check **the exception type, meaningful message, cause chain, and event code**. If the log format is a formal contract, use a separate integration test to verify the format.

## 7. Checking Stack Traces and Cause Chains

Exceptions can be wrapped across processing layers:

```text
PaymentException: Không thể hoàn tất thanh toán
    caused by GatewayTimeoutException: timeout
        caused by SocketTimeoutException: read timed out
```

During investigation, the **outermost exception** describes the business failure, while the **inner cause** usually points to the technical root cause. If code only logs:

```java
log.severe(exception.getMessage());
```

then the log may contain only a single sentence with no cause chain. This is an **illustrative snippet** with pre-existing `log` and `exception` variables; it is not a standalone program.

With JUL, pass the `Throwable` into the call:

```java
log.log(java.util.logging.Level.SEVERE,
        "event_code=payment.failed", exception);
```

In tests, `LogRecord.getThrown()` lets you retrieve the Throwable and walk `getCause()` to verify the causal relationship. With Logback, the exception may be represented as an `IThrowableProxy` rather than the original Throwable object where events are read.

Several important points:

- **Having a Throwable is different from having a rendered stack trace:** the formatter decides how to present it. Testing `getThrown() != null` only proves the record holds the exception.
- **Having a stack trace does not mean having enough context:** a stack trace does not by itself identify which request, which operation, or the impact level. You still need event codes, error codes, and correlation IDs.
- **Do not create a new exception and drop the cause:** if you catch a low-level error and translate it into a business error, preserve the original exception as the cause whenever the constructor/API allows.
- **Do not log a stack trace on every retry:** a huge volume of records can increase cost, add noise, and obscure the final failure. Balance this according to policy and diagnostic needs.
- **Exception messages may contain sensitive data:** do not blindly log connection strings, URLs with credentials, tokens, or personal data; sanitize content before output.

## 8. Checking Error Logs on a Running System

Unit tests only observe inside the JVM. To know whether logs are useful in operations, test in a development or staging environment with a **safe simulated failure scenario**:

1. **Pick a scenario with a deterministic outcome:** for example, a mock dependency returning a timeout so the request returns the expected error. Avoid causing failures in production just to generate logs.
2. **Attach correlation IDs:** a unique `request_id` or `trace_id` for the test, along with clear service, environment, and timestamp.
3. **Trigger a single operation and note the timestamp:** if retries occur, confirm the attempt count and final outcome.
4. **Check at the source:** does the service's console/file log at the expected level? Does the JSON or text contain `event_code`, `error_code`, logger, and exception?
5. **Check in the collector:** search by `service`, `environment`, `event_code`, and `trace_id` over a time window wide enough for ingestion latency. Compare fields after parsing.
6. **Check record count by purpose:** is there exactly one `payment.failed` for the final failure, or are there duplicate records in the same channel? If multiple copies exist due to fan-out to different channels, distinguish that from unintended duplication.
7. **Check security and actionability:** no secrets are present, the log has enough information to find the root cause, and operators have access to the right channel.
8. **Check success and recovery:** when the dependency recovers or a fallback succeeds, no spurious "final failure" event is emitted.

An **illustrative** query example in a tool with field-filtering syntax:

```text
service = "checkout"
AND environment = "staging"
AND event_code = "payment.failed"
AND trace_id = "trace-test-42"
```

Actual syntax varies across Elastic, Loki, Splunk, cloud services, and custom systems. The core idea is **filtering on parsed fields**, rather than relying on the raw text line containing assumed whitespace.

### When Logs Are Missing, Trace the Pipeline

```text
Did the code call the logger?
   |
   +-- No -> Check conditional branches, whether the exception is caught or thrown
   |
   +-- Yes -> Does the logger accept the level/filter?
                |
                +-- No -> Check the effective level and filter on the logger
                |
                +-- Yes -> Does the handler/appender receive and encode it properly?
                             |
                             +-- No -> Check level, filter, formatter, additivity
                             |
                             +-- Yes -> Does the collector receive, parse, and store it?
                                          |
                                          +-- No -> Check buffer, drops, collection config, access permissions
                                          |
                                          +-- Yes -> Are you querying the right fields, environment, time range, index?
```

**Do not immediately conclude "the code didn't log" just because the search UI is empty.** The collector may ship slowly, drop data when buffers fill, read the wrong stdout/file, misparse JSON, or alter environment labels. Conversely, seeing data in the collector does not mean every event is delivered exactly once. If full guarantees are required for SLI/SLO measurement or auditing, put proper measurement and reconciliation mechanisms in place.

## 9. Checking Duplicate, Missing, and Wrong-Level Logs

### 9.1. Duplicate Logs from Multiple Layers Catching the Same Exception

```java
try {
    repository.save(order);
} catch (StorageException exception) {
    log.error("Cannot save order", exception);
    throw exception;
}
```

This is an **illustration** with hypothetical variables and classes, not standalone code. If the outer service and controller also log ERROR for the same failure, a single operation can produce three ERROR lines.

The solution is to define events by responsibility: inner layers can **add context and rethrow**, while the handling boundary that knows the final outcome logs `order.save_failed`. If an inner layer needs to log a separate technical event, assign a different code and clearly distinguish an "attempt error" from a "final failure."

### 9.2. Duplicate Logs from Configuration

In JUL, a record from a child logger can pass through both its own handler and its parent's handler when `useParentHandlers=true`. In Logback, the analogous setting is `additivity`. An exception may be logged only once in code, yet the console still shows two lines if the same destination is attached at multiple levels.

Test using a single event with a unique synthetic `event_code` and `trace_id`; verify the count at each destination. Do not blindly "fix" this by disabling all propagation, as you might accidentally cut off a shared collection channel.

### 9.3. Wrong Log Levels

Different scenarios should have different tests:

| Scenario | Usually Reasonable Expectation |
| --- | --- |
| Invalid input, application returns response per contract | Do not emit a system error at ERROR; INFO/DEBUG if needed. |
| Single timeout, but subsequent retry succeeds | WARN/DEBUG for the attempt, do not emit the final `payment.failed` event. |
| Dependency unavailable after all recovery paths and request fails | ERROR in SLF4J/Logback, `SEVERE` in JUL. |
| Exception handled via fallback that still meets the contract | Do not treat as a final failure; level depends on actual impact. |
| Process cannot start due to invalid critical configuration | ERROR/SEVERE at the startup boundary, preserving the cause. |

Log levels do not replace HTTP status codes, rollback behavior, or retry mechanisms. Tests should verify **the return value or exception** alongside **the logs** to catch code that logs an error without actually handling it properly.

### 9.4. Never Compare a Fixed Timestamp or Stack Trace

Fields such as `timestamp`, `thread`, log ordering across threads, and line numbers in stack traces can change between runs. When testing:

- Compare the level, event code, error code, and stable semantic parts.
- Check that the timestamp is valid or within a reasonable time window rather than asserting an exact instant.
- For asynchronous events, use a synchronization mechanism or bounded wait instead of arbitrary `Thread.sleep(...)`.
- For concurrent records, compare the set of events or group by correlation ID rather than requiring a fixed global order.

### 9.5. Checking Only the Message and Ignoring the Throwable

A line like `"payment failed: timeout"` may look right, yet omit the exception type, cause chain, and stack trace. Check `LogRecord.getThrown()` or the backend's exception structure; then have an integration test to ensure the formatter actually outputs what operators need.

## 10. Checking Information Security in Error Logs

Exception paths are especially prone to data leaks: exception messages can contain SQL statements with values, endpoints with tokens, credentials, or input payloads.

Add test cases using **fake secret values** such as `SECRET_TEST_TOKEN_123` and verify that **the final output** does not contain that string, while still retaining the error code and trace ID needed for investigation. Check the message, structured fields, stack trace, and collected data, because masking one field still leaves data exposed if the exception message leaks it.

Principles:

- Log only the fields needed for investigation; do not automatically log entire requests/responses or domain objects via `toString()`.
- Control exception messages from external libraries and dependencies; you may need to map them to safe error codes at the logging boundary.
- Prevent log injection: input containing newlines or control characters can forge "fake log lines" if concatenated directly into text; use safe formatters/encoders and typed data fields.
- Apply read permissions, retention, and deletion policies appropriate to each log type; ERROR does not mean data may be kept indefinitely.
- For audit logs or events requiring guaranteed delivery, do not rely solely on standard loggers because buffers and network issues can drop data.

Never put real secret values into tests to see if they get logged. Use fake data with the same input shape to verify masking and stripping mechanisms.

## 11. Common Mistakes and How to Fix Them

| Issue | Symptom | Check and Fix |
| --- | --- | --- |
| Logging `ex.getMessage()` instead of Throwable | No stack trace or cause | Pass the Throwable to the logging overload; test `getThrown()` and the formatter. |
| Logging ERROR on every catch | Many alerts with no real impact | Distinguish recovered retries from final failures. |
| Logging and rethrowing at every layer | One error has multiple stack traces | Define the event-emitting boundary and separate event codes if meanings differ. |
| Unit test only searches for the word "error" | Wording changes break the test | Check level, event code, and structured fields. |
| Capturing `LogRecord` and assuming the stack trace printed | Unit test PASSES but console lacks the exception | Test the formatter/encoder separately. |
| Logger and handler levels differ | Logger is called but no output appears | Check level and filters at both layers. |
| Attaching a handler and forgetting to remove it | Subsequent tests receive extra records, duplicate logs | Clean up handlers/appenders and restore configuration in `finally`. |
| Testing concurrent logging with `ArrayList` | Data corruption or flaky results | Use a thread-safe sink and a bounded wait. |
| Collector fails to parse `event_code` | Cannot filter by event code | Check JSON/encoder and ingestion mapping. |
| Comparing the entire stack trace | Tests break after harmless refactoring | Assert Throwable type, cause, and stable fields. |
| Logs contain passwords/tokens | Data exposure risk | Test output with fake secrets; sanitize data before logging. |
| Counting ERRORs as the request failure rate | Metrics skew due to duplicate or missing logs | Use metrics or completion events with clear denominators and rules. |

## 12. Self-Check Exercises

Suppose an order service has three scenarios:

**A.** A request is missing a required field and returns HTTP 400 as designed.  
**B.** The first database call times out, and a retry succeeds.  
**C.** The database call fails after all retries, and the request ultimately fails.

Answer the following:

1. Which scenario typically requires `ERROR`/`SEVERE`? What criteria should guide the levels for the remaining scenarios?
2. If the repository, service, and controller layers all call `log.error(...)` and rethrow the same error C, how many ERROR lines can one request produce? How do you test to distinguish duplicate logging from valid fan-out?
3. The record for C has `event_code=order.save_failed`, `request_id=req-7`, but only stores the string `exception.getMessage()`. What diagnostic data may be lost?
4. A unit test captures a `LogRecord` with `getThrown() != null`. Does that prove the stack trace appears in the centralized log store?
5. When searching by `trace_id` in the log system yields no results, which layers will you check in order?

**Suggested Answers:**

- Under common policies, C requires ERROR/SEVERE because the logical operation ultimately failed. A usually does not need a server-error level. B can use WARN/DEBUG for the failed attempt and INFO for the successful result, depending on impact and operational needs.
- If all three layers log once, three records can appear for one operation; each record may also be emitted to multiple destinations. Check the event code, logger, request ID, code sites emitting logs, and where handlers/appenders are attached; count **per destination**.
- Logging only the message can lose the exception type, stack trace, and cause chain; pass the Throwable and ensure the formatter handles it properly.
- Not yet. The unit test proves the in-JVM record holds the Throwable. You must test the formatter, appender, and collection pipeline to confirm the log store actually has the stack trace.
- Check whether the execution branch calls the logger; the logger's level/filter; the handler/appender and formatting; the buffer/collector and parsing; and finally the service, environment, time window, index, access permissions, and query.

**Completion Criterion:** You can write a test case verifying "no error log on success, exactly one final failure log on error," checking `level`, `event_code`, `Throwable`, and correlation fields; and then explain why formatter and collector testing are still required before trusting that operators will see complete error logs.
