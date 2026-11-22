# Writing Logging Tests in Java Core Logging

## 1. Practical Project Introduction

This lesson belongs to the **Practical Project** group, topic **Writing Logging Tests**. In a Java application, a `logger.info(...)` or `logger.error(...)` call might execute without throwing an exception, but that does not prove the log has the right level, complete context, preserved exception, no sensitive information, no duplicates, or reached the intended file/collector. For logging to become a reliable operational component, we need to **test observable behavior**.

This project builds a three-tier logging test suite:

1. **Unit/event test:** Capture the logging event directly at the logger/handler/appender and verify its level, message, parameters, exception, and event count.
2. **Integration test:** Use the actual backend (JUL, Logback, Log4j 2), filter, formatter/encoder, routing, and async appender to verify serialized output.
3. **End-to-end test:** Trace an event with a unique ID from the JVM to the agent/collector/index, verifying its schema and queryability within a deadline.

The main lab uses **Java 17** and the built-in `java.util.logging` library in the JDK, without requiring Maven or a broker. It then expands to **JUnit 5 + SLF4J + Logback** in a project with the corresponding dependencies. Each section clearly states the scope of what has been proven, without using a passing unit test to infer that the collector has stored the log.

### Learning Outcomes

After completing this lesson, you will be able to:

- Create a test fixture that captures `LogRecord` or `ILoggingEvent` without relying on capturing all of `System.out`.
- Assert the exact `Level`, logger name, event code, message template, parameters, and MDC/context.
- Test both positive **and** negative events: errors must be logged; success must not emit ERROR; filtered INFO must not be emitted; a single exception must not be logged multiple times.
- Verify that `Throwable` is actually attached, not just the `exception.getMessage()` string; check cause and suppressed exceptions when appropriate.
- Verify that tokens, passwords, payloads, or personal data are not leaked from messages, exceptions, and metadata.
- Clean up appenders/handlers, levels, MDC, and global state so tests run independently and repeatably.
- Write regression/contract tests for structured logs and formatters, avoiding tests overly coupled to phrasing or line numbers.
- Build test cases for async logging, routing, overload, collector latency, appender failure, and CI.
- Understand the boundary: logging is observability, **not a replacement** for assertions on business outcomes or transaction durability.

## 2. Problem Statement and Acceptance Criteria

**Context:** A checkout processing service needs to log when an order succeeds and when a payment error occurs. Assumed conventions for this exercise:

| Event | Condition | Level | Contract |
| --- | --- | --- | --- |
| `checkout.succeeded` | Processing completes per handler contract | INFO | Has `order_id`, no Throwable |
| `checkout.failed` | Handler fails due to gateway timeout | ERROR in SLF4J/Logback or SEVERE in JUL | Has `order_id`, `error_code`, Throwable, and cause |
| `checkout.recovered` | Retry/fallback succeeds, if applicable | INFO/WARN depending on policy | Does not emit false terminal failure |
| INFO blocked by effective level WARNING | Logger configured to keep WARNING and above only | No INFO emitted | Must not appear in capture sink |
| Appender filter rejects INFO | Handler/Appender filter rejects the record | Does not reach that sink | Must be distinguished from logger level |
| Secret from request | A dummy token parameter is passed into the handler | Secret not logged | Protects both formatted output and exception chain |

**Acceptance criteria:**

- [ ] Two handler calls on the happy/error paths produce **exactly two records** in the test Handler.
- [ ] Success is INFO, with a message template and order ID in parameters.
- [ ] Failure is SEVERE, preserving the exact thrown Throwable instance and root cause.
- [ ] No duplicate ERROR and no false success for the failed request.
- [ ] Dummy token `TEST_SECRET_DO_NOT_LOG` does not appear in the captured records.
- [ ] When the effective level is WARNING, success INFO does not enter the Handler.
- [ ] When the Handler filter rejects INFO, the record does not reach that sink.
- [ ] The test cleans up/restores logger state after running.
- [ ] The Java 17 program prints `test=PASS` after assertions and produces deterministic stdout.
- [ ] Tests depending on external backends are clearly marked and not presented as standalone JDK code.

**Not accepted as verification:** “The application ran without throwing”, “the console looks like it has ERROR”, “Mockito verified the logger was called”, or “took a snapshot and compared the full timestamp”. Each of these only proves a small part of the logging pipeline.

## 3. Understanding the Logging Pipeline Before Testing

A typical path:

```text
Business code
    |
    +--> Logger call, message template, Throwable, context
    |
    v
Logger level / filter
    |
    v
LogRecord / LoggingEvent
    |
    +--> appender / handler filter
    |
    v
Formatter / JSON encoder
    |
    +--> sync file/stdout OR async queue
    |
    v
Log agent / shipper
    |
    v
Collector / parser / exporter
    |
    v
Index / storage / dashboard / alert
```

Testing at each hop answers a different question:

| Test Type | What It Can Assert | What It Does Not Prove |
| --- | --- | --- |
| Business test | Whether success/failure/rollback worked | Whether logs were emitted |
| Verify logger mock | Which logger API arguments the code called | Whether the real backend creates an event |
| In-memory JUL Handler | Real `LogRecord` published, including level/message/Throwable | Whether console/file/collector received it |
| Logback ListAppender | `ILoggingEvent` with level/template/MDC/ThrowableProxy | JSON serialization and remote sink |
| Encoder/formatter integration | Serialized text/JSON matches schema and escaping | Whether remote collector received/indexed it |
| File/stdout integration | Local sink received the log | Whether the agent read and shipped it properly |
| End-to-end canary | Specific event found in backend within deadline | That all other events are guaranteed not lost |
| Load/failure injection | Queue/drop/blocked/write failure follows policy | That no future logging incident will occur |

**Assertion design principle:** Do not use evidence at one hop to draw conclusions for downstream hops. An appender enqueuing a log does not mean durable storage; a collector returning 2xx does not automatically guarantee the event is searchable, unless the backend contract states so.

### Positive and Negative Tests

A good test suite includes:

- **Positive:** When an exception occurs, `checkout.failed` is emitted with the right level, order ID, and Throwable.
- **Negative:** No `checkout.succeeded` for a failed order; no token logged; no two stack traces printed; filtered INFO does not reach the sink.
- **Count:** When policy allows only one terminal event, assert **exactly 1** event of that type, not just `>=1`.
- **Identity/context:** The same request ID/order ID appears on the right records, without leaking MDC from another request.
- **Boundary:** When testing async logging, observe after an appropriate drain/ack rather than concluding just because nothing appeared after 50 ms.

## 4. Recommended Project Structure

The main exercise creates a single directly runnable Java 17 file:

```text
logging-test-lab/
  LoggingTestLab.java
```

Compile with `javac LoggingTestLab.java` and run with `java LoggingTestLab`. No JUnit is needed because this is an **executable self-checking harness**: each condition uses an assertion and the process exits with an error if any fails.

When integrating into a real Maven/Gradle project, you can expand it to:

```text
src/
  main/java/com/example/checkout/CheckoutService.java
  test/java/com/example/checkout/CheckoutLoggingTest.java
  test/resources/logback-test.xml
```

Use JUnit Jupiter and the real backend, separating fixtures/helper classes when needed. Avoid sharing the root logger across multiple tests running in parallel, as it can cause races or state leakage.

### Test Naming

Test names should describe **observable behavior**:

- `shouldEmitInfoWithOrderIdOnSuccess`
- `shouldAttachThrowableOnFailure`
- `shouldNotLogSecretToken`
- `shouldNotEmitInfoWhenDisabled`
- `shouldNotDuplicateTerminalFailure`
- `shouldRestoreLoggerConfiguration`
- `shouldSerializeErrorAsStructuredJson`
- `shouldKeepTraceContextForAsyncWork`

Avoid generic names like `testLog()` or only checking a text snapshot, which leaves future maintainers unsure which contract is being protected.

## 5. Standalone Java 17: Writing a Real Logging Test Suite

The program uses an in-memory `java.util.logging.Handler`. The Handler keeps a list of `LogRecord` instances that JUL actually dispatches to it. The service logs an INFO event on success and a SEVERE event with a Throwable on failure.

**Scope limitation:** This is a unit/event test for JUL, not a simulation of durable files, JSON logs, network collectors, or async logging. The program runs on a single thread; `ArrayList` is safe within this demo's scope, but it is not thread-safe when using a shared Handler across multiple threads.

Create the file **`LoggingTestLab.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.logging.Filter;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class LoggingTestLab {
    static final class MemoryHandler extends Handler {
        private final List<LogRecord> records = new ArrayList<>();

        MemoryHandler() {
            setLevel(Level.ALL);
        }

        @Override
        public void publish(LogRecord record) {
            if (isLoggable(record)) {
                records.add(record);
            }
        }

        @Override
        public void flush() {
        }

        @Override
        public void close() {
        }

        List<LogRecord> snapshot() {
            return List.copyOf(records);
        }
    }

    static final class CheckoutException extends RuntimeException {
        CheckoutException(String message, Throwable cause) {
            super(message, cause);
        }
    }

    static final class CheckoutService {
        private final Logger logger;

        CheckoutService(Logger logger) {
            this.logger = logger;
        }

        void checkout(String orderId, String secret, boolean shouldFail) {
            // secret deliberately never goes into a log record.
            if (!shouldFail) {
                logger.log(Level.INFO,
                        "event=checkout.succeeded order_id={0}",
                        orderId);
                return;
            }

            try {
                throw new IllegalStateException("gateway timeout");
            } catch (IllegalStateException cause) {
                CheckoutException failure = new CheckoutException(
                        "checkout failed", cause);
                logger.log(Level.SEVERE,
                        "event=checkout.failed order_id=" + orderId
                        + " error_code=GATEWAY_TIMEOUT", failure);
                throw failure;
            }
        }
    }

    static void require(boolean condition, String description) {
        if (!condition) {
            throw new IllegalStateException(
                    "Assertion failed: " + description);
        }
    }

    public static void main(String[] args) {
        Logger logger = Logger.getLogger("lab.checkout");
        Level originalLevel = logger.getLevel();
        boolean originalParentSetting = logger.getUseParentHandlers();

        MemoryHandler capture = new MemoryHandler();
        logger.setUseParentHandlers(false);
        logger.setLevel(Level.ALL);
        logger.addHandler(capture);

        String testSecret = "TEST_SECRET_DO_NOT_LOG";
        CheckoutService service = new CheckoutService(logger);

        try {
            service.checkout("order-7", testSecret, false);

            CheckoutException caught = null;
            try {
                service.checkout("order-8", testSecret, true);
            } catch (CheckoutException failure) {
                caught = failure;
            }

            require(caught != null, "exception propagated");

            List<LogRecord> events = capture.snapshot();
            require(events.size() == 2, "exactly two events");

            LogRecord success = events.get(0);
            LogRecord failure = events.get(1);

            require(success.getLevel() == Level.INFO, "success level");
            require("event=checkout.succeeded order_id={0}"
                    .equals(success.getMessage()), "success template");
            require(success.getParameters() != null
                    && success.getParameters().length == 1
                    && "order-7".equals(
                        success.getParameters()[0]), "success order id");
            require(success.getThrown() == null,
                    "success has no exception");

            require(failure.getLevel() == Level.SEVERE,
                    "failure level");
            require("event=checkout.failed order_id=order-8"
                    .concat(" error_code=GATEWAY_TIMEOUT")
                    .equals(failure.getMessage()), "failure message");
            require(failure.getThrown() == caught,
                    "Throwable identity");
            require(caught.getCause() instanceof IllegalStateException,
                    "root cause type");
            require("gateway timeout".equals(
                    caught.getCause().getMessage()), "root cause message");

            for (LogRecord event : events) {
                String text = event.getMessage();
                require(!text.contains(testSecret), "secret in message");
                Throwable thrown = event.getThrown();
                if (thrown != null) {
                    require(!String.valueOf(thrown.getMessage())
                            .contains(testSecret), "secret in exception");
                    if (thrown.getCause() != null) {
                        require(!String.valueOf(
                                thrown.getCause().getMessage())
                                .contains(testSecret), "secret in cause");
                    }
                }
            }

            // Negative case 1: logger level blocks INFO.
            logger.setLevel(Level.WARNING);
            service.checkout("order-9", testSecret, false);
            require(capture.snapshot().size() == 2,
                    "logger level excludes INFO");

            // Negative case 2: Handler filter rejects INFO.
            logger.setLevel(Level.ALL);
            Filter onlySevere = record ->
                    record.getLevel().intValue() >= Level.SEVERE.intValue();
            capture.setFilter(onlySevere);
            service.checkout("order-10", testSecret, false);
            require(capture.snapshot().size() == 2,
                    "handler filter excludes INFO");

            System.out.println("events=" + events.size());
            System.out.println("success_level="
                    + success.getLevel().getName());
            System.out.println("success_order="
                    + success.getParameters()[0]);
            System.out.println("failure_level="
                    + failure.getLevel().getName());
            System.out.println("failure_exception="
                    + caught.getClass().getSimpleName());
            System.out.println("cause="
                    + caught.getCause().getClass().getSimpleName());
            System.out.println("logger_filtered_info=PASS");
            System.out.println("handler_filtered_info=PASS");
            System.out.println("secret_absent=PASS");
            System.out.println("duplicate_absent=PASS");
            System.out.println("test=PASS");
        } finally {
            capture.setFilter(null);
            logger.removeHandler(capture);
            capture.close();
            logger.setLevel(originalLevel);
            logger.setUseParentHandlers(originalParentSetting);
        }
    }
}
```

Run commands:

```bash
javac LoggingTestLab.java
java LoggingTestLab
```

**Exact stdout:**

```text
events=2
success_level=INFO
success_order=order-7
failure_level=SEVERE
failure_exception=CheckoutException
cause=IllegalStateException
logger_filtered_info=PASS
handler_filtered_info=PASS
secret_absent=PASS
duplicate_absent=PASS
test=PASS
```

### Why Does the Program Print This Exact Output?

1. `Logger` is set to `Level.ALL` and the Handler to `Level.ALL`. Each event reaches the Handler immediately on the same thread because this is a synchronous JUL Handler in the demo.
2. Success logs `Level.INFO` with a **message template** and one parameter `order-7`. `LogRecord.getMessage()` returns the template, not necessarily the formatted text.
3. Failure creates an `IllegalStateException` as the cause, wraps it in `CheckoutException`, calls the `logger.log(Level, String, Throwable)` overload, and rethrows **the same instance**. `getThrown() == caught` must hold.
4. The list has exactly two records after the two operations. If the code logged a terminal failure twice, the count assertion would fail.
5. The dummy secret is passed into the method but never placed in the message or exception. This test protects the captured fields, **and does not replace** checking the full JSON encoder/MDC/sink in production.
6. Next, the logger changes to `Level.WARNING`; the INFO call from success is blocked **before the Handler**, so the record count does not increase.
7. The logger returns to ALL, but the Handler has a filter accepting only `SEVERE` and above. The INFO success may be created at the logger, but **is not added to the capture**.
8. `setUseParentHandlers(false)` prevents JUL parent handlers from printing extra logs to stderr. `finally` restores the level, parent handlers, and removes the Handler to prevent leaking into other tests.
9. No timestamps or thread IDs are printed and no randomness is used, so stdout does not depend on time or locale.
10. Only when **all assertions** pass does the `test=PASS` line appear.

**Technical note:** Because `java.util.logging.Logger` uses a hierarchy and configuration can be modified elsewhere, the demo keeps the fixture on logger `lab.checkout` in a standalone JVM run. In a parallel test suite, avoid sharing a logger name or mutating the root logger due to race risks; create dedicated loggers/appropriate isolation instead.

### Try Breaking It to See the Tests Catch Bugs

- Change `Level.SEVERE` to `Level.INFO` in failure: the `failure level` assertion fails.
- Change `logger.log(Level.SEVERE, message, failure)` to `logger.severe(failure.getMessage())`: `getThrown()` is lost, test fails.
- Log an extra ERROR before rethrowing: `events.size() == 2` fails.
- Concatenate `testSecret` into the message: the security assertion fails.
- Remove `setUseParentHandlers(false)`: stdout may look the same, but stderr/root appender outputs extra logs; an integration test is needed if parent routing is part of the contract.
- Remove the Handler filter: `order-10` success is captured, negative assertion fails.
- Replace the success template with different phrasing while keeping the event code contract: a strict template test will fail; consider testing based on event code/fields when the project uses structured logging to avoid unnecessary coupling to wording.

## 6. Difference Between Level Filter and Handler Filter

In JUL:

- `Logger.setLevel(Level.WARNING)` decides which records the logger accepts based on effective level. INFO is dropped before reaching the Handler.
- `Handler.setLevel(...)` and `Handler.setFilter(...)` control which records **are processed by a specific Handler**. One logger can fan out to multiple handlers with different rules.
- `Logger.setUseParentHandlers(false)` blocks propagation to parent handlers; if parent handlers are enabled and handlers are also attached to the child logger, duplicate output can appear across sinks.

This creates two distinct test cases:

1. **Not created:** INFO is blocked by the level right at the logger.
2. **Does not reach sink:** INFO passes the logger but is rejected by the Handler filter.

If you only assert “not found in file X”, you do not know whether it was filtered at the logger, routed to file Y, dropped by the appender, or not yet searchable in the backend.

### Negative Assertions Must Wait for the Right Boundary

In the synchronous Handler demo, reading the snapshot right after the logger call is sufficient. With an async appender, an event may still be sitting in the queue; to prove it did not reach the sink, you must know the queue has drained/flushed per its semantics and that the observation deadline has passed. `Thread.sleep(100)` is not a guarantee in CI.

## 7. Testing Exceptions: Attaching the Real Throwable

A common bug with SLF4J:

```java
// Passing text only: many backends will not have the Throwable.
logger.error("Checkout failed: {}", exception.getMessage());
```

Whereas:

```java
// Passing Throwable: the backend can render the stack trace/cause.
logger.error("Checkout failed", exception);
```

These two are **SLF4J snippets**, assuming a declared logger and exception. A test that only checks for `Checkout failed` in the output will not catch the first variant losing the stack trace.

What to verify:

- Correct exception type.
- Correct outer exception/cause chain.
- Suppressed exceptions if the code uses try-with-resources/`addSuppressed`.
- Exception is attached to the logging event, not merely formatted as a string.
- Error code/outcome is meaningful in business terms.
- Stack trace in the real encoder is rendered/redacted according to policy.
- No secrets in `Throwable.getMessage()`, cause/suppressed, or structured stacktrace fields.

Do not hard-code stack trace line numbers as a golden string: changing a single source line will break the test needlessly. Test the model via API, and test the layout/encoder via stable properties.

### An Exception Can Be Logged Multiple Times

```text
Repository throws
     |
Service logs ERROR and rethrows
     |
ControllerAdvice logs ERROR again
     |
Container logs another ERROR
```

Three identical error lines can cause an alert to count three times for a single failed request. You should define a **terminal error ownership boundary**. Lower layers can throw exceptions with a cause without logging; the boundary layer emits one complete event. During retries, you can log separate attempt events and one terminal event when retries are exhausted.

There is no absolute rule that an exception across an entire distributed system is logged only once: multiple services may need their own events with different context. Tests should assert **the expected number of logical events for the scope**.

## 8. Moving to JUnit 5 + SLF4J + Logback

In a real application using SLF4J with Logback Classic, `ch.qos.logback.core.read.ListAppender` can capture `ILoggingEvent` instead of `System.out`. The following example **does not run on JDK alone**; it requires compatible versions of JUnit Jupiter, `slf4j-api`, `logback-classic`, and `logback-core` on the test classpath.

### Sample Test Class

```java
import ch.qos.logback.classic.Level;
import ch.qos.logback.classic.Logger;
import ch.qos.logback.classic.spi.ILoggingEvent;
import ch.qos.logback.core.read.ListAppender;
import org.junit.jupiter.api.Test;
import org.slf4j.LoggerFactory;

import static org.junit.jupiter.api.Assertions.*;

class CheckoutLogbackTest {
    @Test
    void attachesThrowableAndKeepsRequiredFields() {
        Logger logger = (Logger) LoggerFactory.getLogger(
                "test.checkout.logging.example");

        Level previousLevel = logger.getLevel();
        boolean previousAdditivity = logger.isAdditive();

        ListAppender<ILoggingEvent> appender = new ListAppender<>();
        appender.setContext(logger.getLoggerContext());
        appender.start();

        logger.setLevel(Level.ERROR);
        logger.setAdditive(false);
        logger.addAppender(appender);

        try {
            IllegalStateException cause =
                    new IllegalStateException("gateway unavailable");

            logger.error("event={} order_id={}",
                    "checkout.failed", "order-7", cause);

            assertEquals(1, appender.list.size());
            ILoggingEvent event = appender.list.get(0);

            assertEquals(Level.ERROR, event.getLevel());
            assertEquals("test.checkout.logging.example",
                    event.getLoggerName());
            assertEquals("event=checkout.failed order_id=order-7",
                    event.getFormattedMessage());

            assertNotNull(event.getThrowableProxy());
            assertEquals(IllegalStateException.class.getName(),
                    event.getThrowableProxy().getClassName());
        } finally {
            logger.detachAppender(appender);
            appender.stop();
            logger.setLevel(previousLevel);
            logger.setAdditive(previousAdditivity);
        }
    }
}
```

**Explanation:**

- The test uses a dedicated logger name rather than modifying the application's root logger.
- `getFormattedMessage()` checks placeholder rendering; `getMessage()` in JUL and Logback are two APIs with different semantics—check the backend documentation.
- `getThrowableProxy()` is Logback's representation of the Throwable, not always the same Java object identity as the original exception.
- `setAdditive(false)` prevents test records from propagating to root appenders; it must be restored after the test.
- `finally` detaches and stops the appender, and restores level/additivity so other tests are unaffected.
- A passing unit test with `ListAppender` **does not prove** that the file/JSON encoder/collector received the event.

### Dependency Configuration Notes

With Maven, the project needs JUnit Jupiter for tests and SLF4J + a compatible Logback backend. With Gradle, add the equivalents in `testImplementation` or runtime according to your build setup. **Do not force learners to copy an unverified version**: pick versions compatible with Spring Boot/BOM or the platform in use, and inspect the dependency tree to avoid multiple SLF4J providers at the same time.

When using a Log4j 2 backend, **do not force-cast the logger to `ch.qos.logback.classic.Logger`**. Use a fixture for the Log4j 2 API/implementation or another testing abstraction. A program using the SLF4J facade does not necessarily use Logback at runtime.

## 9. Testing MDC / Correlation IDs

Logs for observability require context, such as `request_id`, `trace_id`, `message_id`, or `operation_id`. If context is missing or wrong, dashboards may merge two users' logs into the same trace.

With SLF4J, you can scope an MDC key:

```java
String prior = org.slf4j.MDC.get("request_id");
try {
    org.slf4j.MDC.put("request_id", "req-test-7");
    // Call the logging code within this scope.
} finally {
    if (prior == null) {
        org.slf4j.MDC.remove("request_id");
    } else {
        org.slf4j.MDC.put("request_id", prior);
    }
}
```

This is an **integration snippet**, not standalone Java JDK. If there are multiple keys, restore the context map or use a closeable scope appropriate for the backend.

Tests should cover:

1. Events while request A runs have `request_id=A`.
2. After scope A ends, request B no longer carries ID A.
3. If a worker executes on another thread, context is propagated as designed.
4. If trace context is missing or untrusted, the log has a clear fallback.
5. Passwords, tokens, emails, or raw payloads are not placed into MDC.
6. The encoder actually outputs the keys needed for querying; a `%msg`-only layout may ignore MDC.
7. Multi-tenant/authorization data is not taken from untrusted headers without validation.

**Do not assume MDC propagates across every `ExecutorService`/`CompletableFuture`.** Tests should check thread pool reuse and cleanup; use proper framework instrumentation rather than relying on incidental `ThreadLocal` behavior.

## 10. Writing Tests for Structured JSON Logs

When moving from text to JSON, you must test the **schema**, not just substrings.

An illustrative event:

```json
{
  "schema_version": 1,
  "timestamp": "2026-11-10T02:00:00Z",
  "level": "ERROR",
  "service": "checkout",
  "event_code": "checkout.failed",
  "order_id": "order-7",
  "error_code": "GATEWAY_TIMEOUT",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "exception_type": "java.lang.IllegalStateException",
  "duration_ms": 245
}
```

This is an **example schema**, not the default output of Logback/Log4j 2/OpenTelemetry. Proper tests should:

- Parse the serialized output using the project's JSON library, then assert required keys and **types**.
- Verify the timestamp has a clear offset/UTC, independent of host timezone.
- Verify `duration_ms` is a number and `order_id` is a string to preserve leading zeros.
- Verify event code/error code and stable enum values.
- Verify `exception_type` and stack trace/cause according to policy.
- Verify `trace_id` when context exists, and missing/null semantics when absent.
- Verify no secrets appear in the **entire** output, including exceptions and MDC.
- Verify quotes, backslashes, newlines, and Unicode are escaped properly.
- If NDJSON uses one event per line, test that a multiline stack trace is not split into multiple logical events.
- Verify collector transforms/index mappings do not alter field types or names outside the contract.

A test like `assertTrue(jsonText.contains("error_code"))` is too weak: `"error_code"` might only appear inside the message field. You must parse and assert `$.error_code` at the agreed location.

### Schema Version and Compatibility

Changing `"duration_ms": 245` to `"duration_ms": "245ms"` can break dashboards/aggregations. Adding an optional field can be compatible if consumers ignore unknown fields; changing types, renaming required fields, or changing the meaning of `timestamp` is usually breaking. Write contract tests with v1/v2 fixtures and migration rules, rather than assuming “having JSON” is stable enough.

## 11. Testing Log Levels and Logger Hierarchy

A practical test suite should answer:

| Scenario | Assertion |
| --- | --- |
| Logger level INFO | DEBUG/FINE not emitted; INFO/WARN/ERROR may emit per backend |
| Logger level WARN | INFO does not pass effective level |
| Handler/Appender filter | Rejected event does not reach **that sink** |
| Child logger with additivity | Record reaches/does not reach parent as configured |
| Two appenders | Correct routing, no unexpected duplication |
| Root logger level differs from child | Effective level/route follows framework, not intuition |
| Async appender | Enqueue/flush/drain and drop decisions match policy |
| Logger configuration reload | Level/filter updates per policy without losing critical events |

Note that JUL uses `FINE/INFO/WARNING/SEVERE`, whereas SLF4J/Logback typically use `DEBUG/INFO/WARN/ERROR`. Tests should rely on the actual backend's level enum rather than searching for the string `"ERROR"` in the message.

### Additivity and Duplicates

In Logback, a child logger with an appender and `additive=true` can forward the same event up to the parent appender. If both send to the same collector, the backend may show two equivalent records. Do not conclude the business logic failed twice just because there are two ERROR lines.

To detect duplicates:

- Emit events with a unique `event_id`/`operation_id`.
- Filter by `event_code` + ID + route.
- Assert the count at each appender/sink and the total count per fan-out policy.
- Check whether the agent collects both file and stdout from the same source.
- For retries, distinguish valid **attempt events** from the **terminal failure** that must be emitted only once per contract.

## 12. Testing Exception Cause, Suppressed, and Handled Errors

An exception can be wrapped:

```text
CheckoutException: checkout failed
  Caused by IllegalStateException: gateway timeout
    Suppressed IOException: cleanup failure
```

To test this properly:

- `outer.getCause()` has the right type/error code.
- `outer.getSuppressed()` or `cause.getSuppressed()` is on the exact object where the suppressed exception was attached; they do not automatically move to the outer exception.
- The logging event has a Throwable or ThrowableProxy, not just text.
- The formatted stack trace includes `Caused by`/`Suppressed` if required by encoder policy, without asserting exact source line numbers.
- If the exception is handled/recovered, the policy level/outcome reflects **recovered** rather than creating a false terminal error.

Do not call `printStackTrace()` and then `logger.error(...)` with the same Throwable at every layer. It causes duplicates, lacks structured metadata, and makes sensitive data harder to govern.

### Testing Retries

For message-driven/HTTP retries:

1. First attempt hits a transient failure and logs `retry_planned` per policy.
2. Subsequent attempts include `attempt`, error category, and backoff.
3. If attempt 3 succeeds, a success/recovered outcome is logged; no terminal `retry_exhausted`.
4. If the budget is exhausted, there is exactly one terminal failure event and DLQ policy handling.
5. Do not log “retry confirmed by broker” solely because the application decided to retry.
6. If a remote side effect times out, the outcome may be UNKNOWN; the log must not assert that a business rollback definitely occurred.

The event codes in this section are **application contract examples**, not built-in Java logging events.

## 13. Testing Security and Redaction

This is one of the most important reasons to test logging: exceptions can carry sensitive information even when developers do not intend it.

### Canary Secret

Use a dummy string:

```text
TEST_SECRET_DO_NOT_LOG
```

Trigger an error with input containing this string, then inspect **all output fields**:

- Message/formatted message.
- MDC/structured arguments.
- Exception text, cause, suppressed, and stack trace.
- HTTP header/query/URL fields.
- File/stdout, agent export, and index.
- The logging backend's internal status/error channel when applicable.

The test must assert that the canary string is **absent** from disallowed sinks, without leaking real secrets in test fixtures.

### Log Injection

Input containing a newline:

```text
username=bob
ERROR admin granted
```

If a text appender writes directly without escaping, the output can look like a new ERROR log. A standard JSON encoder will escape newlines inside strings when configured properly. Tests must parse a single valid JSON event without creating a fake logical event. Do not manually concatenate JSON from raw input or pass entire objects containing tokens to the logger.

### Data Minimization

- Log only allowed IDs/metadata.
- Avoid passwords, tokens, private keys, cookies, card numbers, and PII.
- Use error codes instead of raw exception messages when possible.
- Avoid using user IDs or raw message strings as Prometheus labels due to cardinality and privacy.
- Audit/security logs have their own retention/access/integrity policies and should not share DEBUG/INFO sampling decisions.

**Sampling does not make logging secrets safe**: an event kept with 1% probability can still leak data.

## 14. Async Logging: Testing at the Right Time

With Logback `AsyncAppender`, Log4j 2 `AsyncLogger`, or a network exporter:

```text
caller -> enqueue -> writer thread -> sink -> agent -> collector -> index
```

When `logger.error(...)` returns, the event may only be sitting in the queue. Immediately asserting that the backend “did not receive it” will be flaky.

A proper test should:

1. Attach a unique `test_event_id`.
2. Identify the **hop** being tested: queue accepted, file written, collector acknowledged, or searchable.
3. Use flush/drain/ack per backend semantics if available.
4. Poll with a **finite deadline**, not just `Thread.sleep(100)`.
5. When the deadline expires, distinguish `NOT_EMITTED`, `FILTERED`, `DROPPED`, `NOT_DELIVERED`, `NOT_SEARCHABLE`, or `QUERY_ERROR` when evidence is available.
6. Measure drops/queue depth/blocked enqueue duration, especially under high load.
7. Test shutdown while pending events remain, according to policy.

**Do not equate appender accepted with durable storage.** A write to an OS buffer, a network client publish confirm, or an HTTP 2xx does not necessarily have the same durability semantics across all backends.

### Failure Injection

Inject failures in staging or an isolated test fixture:

| Failure | Required Assertion |
| --- | --- |
| Appender file permission denied | Status/error counter increases; business response follows fail-open/closed policy |
| Disk full/read-only | Write/flush failure is signaled, no recursive logging |
| Async queue full | Blocked/dropped per policy, with dedicated counter |
| Collector timeout | Bounded retry/backoff; queue age/backlog observable |
| TLS/auth failure | No fallback to plaintext or overly permissive sink |
| Log shipper down | Canary missing, backlog/recovery clear |
| Index rejects schema | Rejected/parse error metrics increase |
| Duplicate delivery | Stable event ID/dedup policy works |
| Formatter exception | Does not cause log error recursion loop |
| Abrupt shutdown | Flush/durability limits are known |

Do not intentionally fill production disks or kill production collectors just to test. Use staging/isolated environments and a clear rollback plan.

## 15. Maven/Gradle and CI Integration

A production project should have these test layers:

- **Fast unit:** In-memory Handler/ListAppender, business error classification, exception propagation.
- **Encoder integration:** JSON schema, level filter, MDC, stack trace, sensitive data masking.
- **Infrastructure integration:** File appender, rotation, stdout/shipper, queue behavior.
- **End-to-end with deadline:** Collector/index canary and alert rules.
- **Performance/chaos:** Burst exceptions, full queue, blocked callers, retry/export outages.

Not every Pull Request needs to run E2E against a real collector; however, when changing logging config, encoders, schemas, bridges, or agents, an appropriate pipeline is needed to prove compatibility.

### Ways to Keep Tests Non-Flaky

1. Use unique IDs per test.
2. Avoid test order dependencies.
3. Use `Clock.fixed(...)` when the **application's** timestamp is under test; the logger backend may use its own clock.
4. Do not assert exact current timestamps, thread names, or stack frame line numbers unless they are part of the contract.
5. Clean up appenders/handlers and restore levels, filters, and additivity in `finally`.
6. Avoid `System.setOut`/`System.setErr` across a parallel suite unless process-isolated.
7. Use dedicated logger names or test contexts to avoid shared static config.
8. For async, wait on a signal/timeout rather than a fixed sleep.
9. Use dummy tokens, never production secrets in fixtures.
10. Check for warnings about multiple SLF4J providers/bindings and verify the actual backend in CI matches expectations.

### Artifacts for Review

A Pull Request implementing logging tests should include:

- List of acceptance criteria / per-event contracts.
- Test code and how to run it.
- Unit and integration test results.
- **Safe dummy** serialized log samples illustrating the schema.
- Notes on async/durability boundaries not tested at the unit level.
- Documentation of logging bugs caught and remaining operational items.
- No tokens, raw customer payloads, or stack traces containing real data.

## 16. Comprehensive Test Matrix

| ID | Scenario | Positive Assertion | Negative Assertion |
| --- | --- | --- | --- |
| L1 | Checkout success | One INFO `checkout.succeeded` with ID | No ERROR/Throwable |
| L2 | Checkout fail | One SEVERE/ERROR with Throwable and cause | No false success |
| L3 | Error in service then propagated | Boundary emits terminal event | Not logged 2–3 times for same error outside policy |
| L4 | INFO disabled | Does not reach Handler due to logger level | Not mistaken for sink failure |
| L5 | Handler filter denies INFO | Target sink does not receive it | Event can still route to another sink per policy |
| L6 | Wrapped exception | Cause/suppressed preserved | Not just outer message |
| L7 | Recovery success | Outcome RECOVERED and appropriate log level | No false terminal failure |
| L8 | Retry exhausted | One terminal event and attempt count | Does not retry past budget |
| L9 | Appender additivity | Correct routes/count | No duplication outside policy |
| L10 | MDC scope | Requests A/B have correct context | No cross-thread ID leak |
| L11 | Logger config reload | Effective level and filters correct | No silent drop of critical events |
| L12 | JSON encoder | Required fields/types/timestamp correct | Numeric fields not stringified |
| L13 | Input with newline/quote | Valid JSON parse | No log injection |
| L14 | Input with dummy secret | Redacted across all sinks | No secret leak in cause/MDC |
| L15 | Long/multiline stack trace | Exception type and single logical record | Not split into multiple events outside policy |
| L16 | Async delivery | Event reaches designated hop within deadline | No speculative sleep |
| L17 | Collector down | Retry/backlog/alert present | Do not assume logger call means indexed |
| L18 | Full async queue | Blocked/dropped per policy, metrics accurate | No silent loss of critical events |
| L19 | Source log vs indexed log | Reconcile event ID/schema | Do not count duplicates as business errors |
| L20 | Logging status/handler failure | Internal health/metrics detect it | No recursive logging |
| L21 | Framework upgrade | Contract fields and severity mapping intact | Do not rely on raw message snapshots |
| L22 | Shutdown/restart | Expected flush/recovery per contract | Do not claim durability without ACK |
| L23 | Security audit | Route/retention/access correct | No forced sampling outside policy |
| L24 | No traffic | No false alerts when idle | Canary/health still detects pipeline breakage |

Each project should clearly document **event meanings and expected counts** before running tests. An INFO/WARN policy in an example may differ from a real system; tests must check the real contract rather than turning illustrative conventions into mandatory rules for every service.

## 17. Debugging When Logging Tests Fail

### Test Reports “expected 1 event, got 0”

Check in order:

1. Did the code actually enter the logging branch?
2. Are the logger name and logger instance correct?
3. Did the effective logger level filter out the event?
4. Did a logger/appender filter return `DENY`?
5. Was the Appender/Handler started and attached before calling the code?
6. Did root/additivity or routing send it to a different sink?
7. Is the test using a different backend than the assumed Logback cast?
8. For async, has the event been drained yet?
9. Does the collector/index have a parse/schema/query error if this is an E2E test?

Do not rush to relax acceptance criteria to `>=0` or add `Thread.sleep(1000)` just to make it “pass”.

### Test Reports “expected 1 event, got 2”

- Does the code log-and-rethrow at multiple layers?
- Do both the child logger and root have appenders receiving the same event?
- Was a test appender attached in a previous run and never detached?
- Does the agent collect both stdout and file?
- Did a retry/duplicate message legitimately create a new event?
- Is a parallel test suite sharing a logger name and capture list?

Use `event_code`, `operation_id`, and `test_event_id` to distinguish a logic duplicate from permitted fan-out.

### Test Has Message but Missing Stack Trace

- Was `Throwable` passed to the right logger overload?
- Was the exception converted to `exception.getMessage()` text?
- Is the encoder configured not to print Throwables?
- Did the formatter truncate the stack trace or hit an output size limit?
- Did a collector transform strip `exception.stacktrace`?
- Was the cause chain lost when the code wrapped/rethrew?

### Security Test Fails

- Is the sensitive data in the message, parameters, MDC, exception message, or suppressed exceptions?
- Is a new encoder automatically serializing extra headers or object fields?
- Does redaction run at the source, appender, collector, or only in the UI?
- Which sink receives the raw event before redaction?
- Is sensitive data exported to internal status/metrics?

If the dummy token slips through, fix it at the source or with proper allowlisting/redaction; **do not lower the sampling rate to “reduce exposure”**.

## 18. Practice Exercises and Extensions

### Exercise A — Add Another Negative Unit Test

Modify the Java 17 program so a logger allows only `Level.SEVERE`. Invoke success and failure on two new orders. Assert that only the failure record is present and no success event reaches the Handler. Be sure to initialize a separate capture so old records do not mix in.

**Expected result:** Correct count, failure has Throwable, service behavior does not depend on INFO being filtered.

### Exercise B — Verify Suppressed Exceptions

In the failure path, add a suppressed `IOException` to the cause. Test:

- Cause is still `IllegalStateException`.
- `cause.getSuppressed().length == 1`.
- Suppressed type is `IOException`.
- The log event keeps the same outer Throwable.
- Do not assert exact text stack trace line numbers.

### Exercise C — Combine with a Structured Encoder

Use a JSON encoder appropriate for your backend. Test at least:

```json
{
  "event_code": "checkout.failed",
  "order_id": "order-8",
  "error_code": "GATEWAY_TIMEOUT",
  "level": "ERROR"
}
```

This is an **illustrative schema subset**, not JUL output. Parse the JSON into an object and assert field types/names; do not use `contains("checkout.failed")` as the sole assertion. Also check `trace_id`/timestamp/exception per contract.

### Exercise D — Detect Duplicates Caused by Additivity

Attach appenders to both a child logger and parent logger in a separate Logback test, leave `additive=true`, and log one event. Observe both sinks; then set `additive=false`, re-run, and assert correct routing. Restore the configuration in `finally`.

### Exercise E — Async Collector Canary

Emit a synthetic event with a unique `test_event_id`. Wait for the event to appear in the index within a 30-second deadline or an environment-appropriate deadline. If the query fails, distinguish `QUERY_ERROR` from `MISSING`; if it times out, record the last confirmed hop.

Do not perform fault injection that causes an outage in production without approval.

## 19. Testing Anti-Patterns to Avoid

| Anti-Pattern | Risk | Better Approach |
| --- | --- | --- |
| Searching only for `"ERROR"` in console | INFO messages can also contain this word | Assert the event's level enum |
| Only verifying a logger mock | Backend/encoder/filter remain untested | Add Handler/ListAppender integration |
| Snapshotting whole lines with timestamps | Tests flake when time/locale changes | Assert stable contract fields |
| Not detaching test appenders | Events from other tests get captured/duplicated | Use `finally` to clean up |
| Mutating the root logger suite-wide | Parallel tests interfere with each other | Dedicated logger/test context |
| Capturing `System.out` globally | Global state and async output cause races | In-memory event capture or subprocess test |
| Comparing full stack traces | Refactoring changes line/frame numbers | Assert Throwable/cause and layout properties |
| Omitting negative assertions | Misses false success, duplicates, leaks | Assert absence and exact counts |
| Fixed sleep to wait for async | Slow/flaky CI | Poll with deadline/signal/drain |
| Logging real secrets to test redaction | Can leak into test logs/CI | Use dummy tokens |
| JSON substring assertions | Field may only appear inside message | Parse object and validate schema |
| Using `trace_id` as a metric label | High cardinality and privacy risk | Use bounded labels |
| Counting sampled log lines as error rate | Sampling/loss skews numbers | Authoritative business metrics |
| Testing audit with diagnostic logger | Does not guarantee durability/compliance | Separate audit path/transactional contract |
| Treating enqueue == persisted | Logs can be lost after enqueue | Test each ACK boundary |

## 20. Pre-Completion Project Checklist

- [ ] Defined contracts for success/failure logs, event codes, and error codes?
- [ ] Unit tests verify exact level, logger name, message/parameters, and outcome?
- [ ] Failure test verifies real Throwable and cause chain?
- [ ] Tested exact counts and no duplicate terminal logs?
- [ ] Negative tests exist for logger level and handler/appender filters?
- [ ] Verified canary secret is not leaked in messages/exceptions/metadata?
- [ ] Handler/appender attached before and detached after test?
- [ ] Logger level, filter, and parent/additivity restored?
- [ ] Raw timestamps or stack line numbers not used as primary assertions?
- [ ] JDK 17 demo compiles and produces documented stdout?
- [ ] With SLF4J/Logback, ListAppender reads LoggingEvent and ThrowableProxy properly?
- [ ] Backend tests do not cast Log4j 2 to a Logback logger?
- [ ] JSON schema tests parse required fields/types and escaping?
- [ ] MDC context propagated and cleaned up across thread pools/async?
- [ ] Tests exist for log routing and duplicate ingestion?
- [ ] Async deadlines/drain and queue drop metrics covered when needed?
- [ ] E2E canary exists when proving real collector/index ingestion?
- [ ] Alerting and business error rates do not rely solely on log line counts?
- [ ] No production secrets/PII logged in test fixtures or CI artifacts?
- [ ] Runbook exists for missing/extra events or structured fields in tests?
- [ ] Regression contract tests exist when upgrading frameworks/encoders?

**Completion criterion:** You can run `LoggingTestLab.java` with all assertions passing, explain why each assertion is necessary, and know how to extend to Logback/JUnit, structured JSON, and end-to-end instead of equating a logger call with log delivery.

## 21. Self-Check Questions

1. Does `assertThrows(...)` prove a log event was created and written to a sink?
2. Does JUL `LogRecord.getMessage()` contain the template or the formatted message in the demo?
3. How do you verify the exact `Throwable` instance that the code rethrew?
4. Why should event count tests use an exact count at a defined boundary?
5. How does a logger level filter differ from a Handler filter?
6. Why does a passing `ListAppender` test not prove the collector received the log?
7. When an exception is wrapped, where should you check cause/suppressed?
8. Should changing message phrasing fail a semantic logging contract test?
9. Why is a mock logger insufficient to test a JSON encoder?
10. Which test detects MDC from request A leaking into request B?
11. Should `Thread.sleep(100)` be used as a guarantee for an async appender?
12. When an event appears in both child and parent appenders, could it be an additivity duplicate or a repeated business error?
13. Why does 10% sampling skew error rate calculations from log line counts?
14. Is checking only `getFormattedMessage()` enough for a canary secret test?
15. When a collector query errors, should a canary checker return `MISSING` or `UNKNOWN`?
16. If JSON output has `duration_ms` as a string, what should schema tests do?
17. Does an error log written to stdout mean it is searchable in the index?
18. When a test log is missing, how do you distinguish level, filter, routing, queue, and collector?
19. Why should tokens/PII not be placed in the MDC of a production-like test?
20. If a required audit log fails to persist, does a diagnostic logger test prove compliance?

## References

- [Oracle Java SE 17 — Logger](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Logger.html) — overloads, effective level, and parent handlers.
- [Oracle Java SE 17 — Handler](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Handler.html) — publish, filter, close/flush.
- [Oracle Java SE 17 — LogRecord](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/LogRecord.html) — message, parameters, level, and thrown exception.
- [Oracle Java SE 17 — Level](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Level.html) — INFO/WARNING/SEVERE.
- [SLF4J Manual](https://www.slf4j.org/manual.html) — logging facade, parameterized logging, and MDC.
- [Logback Manual — Architecture](https://logback.qos.ch/manual/architecture.html) — logging events, hierarchy, and additivity.
- [Logback Manual — Appenders](https://logback.qos.ch/manual/appenders.html) — appender lifecycles, async logging.
- [Logback Manual — Filters](https://logback.qos.ch/manual/filters.html) — filtering levels and TurboFilter.
- [JUnit 5 User Guide](https://junit.org/junit5/docs/current/user-guide/) — test fixtures and assertions.
- [OpenTelemetry Logs Data Model](https://opentelemetry.io/docs/specs/otel/logs/data-model/) — structure and semantics of log records.
- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html) — log security and data minimization.
