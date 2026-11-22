# Testing Messages in Java Logging: Content, Parameters, and Output

## 1. What Does "Testing Messages" Verify?

In Java Logging, **testing messages** means verifying that an application emits **the right log event, the right level, the right message template, the right parameters/context, and the right exception information**, while not emitting disallowed content. Depending on the goal, a test may inspect the in-memory log event object or the string/JSON after the formatter, encoder, and appender have actually run.

A call such as:

~~~java
// SLF4J or Log4j 2; log is an initialized logger.
log.info("order={} state={}", orderId, state);
~~~

has at least three things that can be verified:

1. **Message template:** `"order={} state={}"`.
2. **Arguments:** e.g. `["ORD-42", "PAID"]`.
3. **Formatted message:** `"order=ORD-42 state=PAID"`.

If you only assert that `logger.info(...)` was called, the test may fail to catch a wrong formatter, a disabled logger, an improperly attached appender, or altered final text. If you only compare an entire console line containing a timestamp and thread ID, the test often becomes brittle when the layout or timezone changes.

**Learning objective:** identify which layer needs to be tested and write assertions at the right layer, without assuming every test must read the actual console or a real file.

## 2. Distinguishing the Three Layers of a Log Message

~~~text
Business method
    │  log.info(template, arguments, throwable?)
    ▼
Logger facade/API + level + filter
    │
    ▼
Logging event: template + args + level + Throwable + context
    │
    ▼
Formatter / Layout / JSON encoder
    │
    ▼
Appender / Handler / async queue
    │
    ▼
Console, file, memory, socket, collector
~~~

Each layer answers a different question:

| Testing Layer | Core Question | Example Assertion |
| --- | --- | --- |
| **Call site** | Did the code decide to log the right event? | Business method creates an event when state is FAILED |
| **Event object** | Are level, template, arguments, cause, and MDC correct? | `getMessage()` equals template; `getThrown()` is the exception |
| **Formatted output** | What content does the reader or collector receive? | Text contains `order=ORD-42 state=PAID`; JSON has `orderId` |
| **Routing/filter** | Did the event reach the right sink at the right level? | INFO present, FINE/DEBUG blocked |
| **Async delivery** | Did the event reach the sink after the worker processed it? | Wait for completion signal before asserting |
| **Security/privacy** | Is there any secret/PII data or log injection? | Output and exception fields do not contain fake sentinels |

**Choosing the right boundary:** For unit tests that only care about the template, an in-memory handler/appender is usually enough. For requirements checking JSON schema or file rotation, you must run a formatter/appender closer to production. For delivery/durability guarantees, integration tests and storage contracts are required; they cannot be inferred from an assertion on an event alone.

## 3. Write the Message Contract Before Writing Assertions

Start from business intent, not from whatever log string happens to appear.

For example, after a payment operation:

| Condition | Event Code | Level | Allowed Message/Fields | Must Not Contain |
| --- | --- | --- | --- | --- |
| Payment completed | `PAYMENT_COMPLETED` | INFO | orderId, result, elapsedMs | Card number, token, raw request |
| Transient payment error | `PAYMENT_RETRY` | WARN or DEBUG per policy | orderId, attempt, reasonCode | Raw exception containing secrets |
| Payment denied | `PAYMENT_DENIED` | INFO/WARN per policy | orderId, reasonCode | CVV, cardholder info |
| Computing details | `PAYMENT_DEBUG` | DEBUG/FINE | branch, cache status, rule version | Unfiltered payload |
| No error | Must not emit `PAYMENT_FAILED` | — | — | Misleading record |

For each event, define:

- **When it is created** and under what conditions it must not be created.
- **Expected event count**: once, per retry, or once for the entire workflow?
- **Log level** and behavior when the level is disabled.
- **Message template** and **parameters**, or the field list in structured logs.
- **Exception**: whether it is genuinely attached as a `Throwable`.
- **Disallowed data**: tokens, passwords, raw bodies, headers, PII.
- **Sinks** that must see the event: console, file, audit, remote collector.

Good tests usually combine assertions that **expected content is present** with assertions that **forbidden content is absent**.

## 4. Testing Messages Is Not Always Testing the Complete String

Example of a console line:

~~~text
2026-11-10 03:14:02.417 [worker-17] INFO  demo.OrderService - order=ORD-42 state=PAID
~~~

Time, thread, class name, and whitespace can vary across machines. If a test has to compare the entire line, you inadvertently bake many irrelevant layout details into the contract.

Prefer:

- Event unit tests: compare **template**, **arguments**, **formattedMessage**, **level**, **loggerName**.
- Formatter tests: use an event with an explicitly fixed timestamp/locale/zone or assert by field, rather than comparing against the real-time clock.
- JSON tests: parse the JSON and assert fields and data types, avoiding key-order comparisons.
- File tests: use a temporary directory, wait for flush/close, and read with the right charset.
- Route tests: attach an in-memory appender to a **specific logger**, rather than intercepting JVM-wide stdout unnecessarily.

A fixed string is appropriate to assert when it is **part of the contract**: event codes, prefixes, templates, field names, or messages consumed by a downstream parser. Text meant only for human developers should be allowed to change without breaking business tests.

## 5. Standalone Java 17: Capturing and Inspecting LogRecord with an In-Memory Handler

This example **does not use JUnit** and needs no external libraries. The program executes its own assertions in Java 17, exiting with a non-zero code on failure. It verifies event presence, event absence, and security properties.

Create **MessageLoggingTest.java**:

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.logging.Formatter;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class MessageLoggingTest {
    private static final Logger LOG = Logger.getLogger("demo.message");

    record Captured(Level level, String template, Object[] arguments,
                    String rendered, Throwable thrown) {}

    static final class CapturingHandler extends Handler {
        private final List<Captured> events = new ArrayList<>();
        private final Formatter renderer = new Formatter() {
            @Override
            public String format(LogRecord record) {
                return formatMessage(record);
            }
        };

        @Override
        public void publish(LogRecord record) {
            if (!isLoggable(record)) return;
            Object[] params = record.getParameters();
            events.add(new Captured(record.getLevel(), record.getMessage(),
                    params == null ? new Object[0] : params.clone(),
                    renderer.format(record), record.getThrown()));
        }

        @Override public void flush() {}
        @Override public void close() {}
        List<Captured> snapshot() { return List.copyOf(events); }
    }

    private static void check(boolean passed, String description) {
        if (!passed) throw new AssertionError(description);
    }

    public static void main(String[] args) {
        CapturingHandler capture = new CapturingHandler();
        capture.setLevel(Level.ALL);
        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.INFO);
        LOG.addHandler(capture);

        try {
            LOG.log(Level.INFO, "order={0} state={1}",
                    new Object[]{"ORD-42", "PAID"});
            IllegalStateException cause = new IllegalStateException("failure");
            LOG.log(Level.WARNING, "send failed", cause);

            AtomicInteger supplierCalls = new AtomicInteger();
            LOG.fine(() -> {
                supplierCalls.incrementAndGet();
                return "expensive diagnostics";
            });

            String secret = "TEST_SECRET_DO_NOT_LOG";
            LOG.log(Level.INFO, "credentialPresent={0}",
                    new Object[]{!secret.isEmpty()});

            List<Captured> result = capture.snapshot();
            check(result.size() == 3, "number of events");
            Captured first = result.get(0);
            check(first.level() == Level.INFO
                    && first.template().equals("order={0} state={1}")
                    && Arrays.equals(first.arguments(),
                            new Object[]{"ORD-42", "PAID"})
                    && first.rendered().equals("order=ORD-42 state=PAID"),
                    "template/arguments/rendered");
            check(result.get(1).level() == Level.WARNING
                    && result.get(1).template().equals("send failed")
                    && result.get(1).thrown() == cause,
                    "Throwable preserved");
            check(supplierCalls.get() == 0
                    && result.stream().noneMatch(e -> e.level() == Level.FINE),
                    "disabled fine event");
            check(result.stream().noneMatch(e ->
                    e.rendered().contains(secret)
                    || e.template().contains(secret)),
                    "secret absent");

            System.out.println("PASS: template, arguments, formatted message");
            System.out.println("PASS: throwable and level");
            System.out.println("PASS: disabled FINE and lazy supplier");
            System.out.println("PASS: secret not logged");
            System.out.println("captured=" + result.size());
        } finally {
            LOG.removeHandler(capture);
            capture.close();
        }
    }
}
~~~

Run in the directory containing the file:

~~~bash
javac --release 17 MessageLoggingTest.java
java MessageLoggingTest
~~~

**Exact standard output (stdout):**

~~~text
PASS: template, arguments, formatted message
PASS: throwable and level
PASS: disabled FINE and lazy supplier
PASS: secret not logged
captured=3
~~~

**Standard error (stderr):** empty when the test passes. **Exit code:** `0`. If an assertion fails, the program throws `AssertionError`, the JVM fails, and the stack trace is printed to stderr.

### How to Read This Test

1. `LOG.setLevel(Level.INFO)` enables INFO/WARNING while disabling FINE.
2. `capture.setLevel(Level.ALL)` does not block events at the handler level.
3. `setUseParentHandlers(false)` prevents the root logger from also printing to the console, keeping the test isolated.
4. `CapturingHandler.publish` receives the `LogRecord`, checks `isLoggable`, and clones the parameters array to avoid holding onto a reference that might be mutated later.
5. `record.getMessage()` returns the JUL template `"order={0} state={1}"`; `Formatter.formatMessage(record)` produces the string with `{0}` and `{1}` substituted.
6. `record.getThrown()` preserves the exact `IllegalStateException` instance passed to the `log(Level, String, Throwable)` overload.
7. The `Supplier` in `LOG.fine(() -> ...)` does not run because FINE is disabled; `supplierCalls==0` and no FINE event is recorded.
8. The `secret` variable is never passed to the logger; only the boolean `credentialPresent` is passed. The assertion verifies the sentinel does not appear in either the template or the formatted message.
9. `result.size()==3` catches extra or missing events within the test's own scope.

**Limitation:** The handler uses `ArrayList` to illustrate single-threaded synchronous processing and is **not a thread-safe collector**. For concurrent logging, use a thread-safe queue and a completion-waiting mechanism. Cloning `Object[]` is a **shallow copy**; mutable element objects can still change. In this demo, arguments are immutable strings/booleans, so it causes no issue.

## 6. JUL: Template, Parameters, and Formatter Are Three Different Things

`java.util.logging.LogRecord` contains:

- `getMessage()`: **unformatted** text, which may be a resource bundle key.
- `getParameters()`: argument array, or null.
- `getThrown()`: `Throwable` attached to the event, or null.
- `getLevel()` and `getLoggerName()`: event properties.
- `getInstant()`/`getLongThreadID()`: metadata, if needed for inspection.

JUL typically uses `{0}`, `{1}` placeholders following `MessageFormat`. This differs from SLF4J/Log4j 2, which typically use `{}`.

Example:

~~~java
LOG.log(Level.INFO, "user={0} action={1}",
        new Object[]{"usr-42", "EXPORT"});
~~~

This snippet illustrates usage inside a class where `LOG`/`Level` are already defined. When `LogRecord` is created, `getMessage()` may be `"user={0} action={1}"`; after `formatMessage`, the string is `"user=usr-42 action=EXPORT"`.

Do not write a test like:

~~~java
// Wrong expectation for JUL: getMessage does not substitute placeholders itself.
check(record.getMessage().equals("user=usr-42 action=EXPORT"), "message");
~~~

Choose `formatMessage(record)` when testing text output; choose `getMessage()` and `getParameters()` when testing the template contract.

**Localization:** When a `Logger`/`LogRecord` has a resource bundle, the formatter may replace the message key with a locale-specific string. In that case, the test must control the bundle/locale and be clear about whether it is testing the key or the localized text.

**Mutable LogRecord:** The JDK Javadoc advises clients not to continue modifying a `LogRecord` after submitting it to the logging framework. If a handler hands a record off to another thread, snapshot/prepare metadata first; do not hold arbitrary references and assume fields will remain unchanged.

## 7. Testing Log Levels and Unemitted Events

A good message test does not only verify that `INFO` is present. It should also verify:

- When `DEBUG/FINE` is disabled, debug events do not appear.
- When `WARN/WARNING` is enabled, warning events appear at the right level.
- A logger and a handler/appender can have **two separate level thresholds**.
- A filter on the logger or appender can block an event even when the level allows it.
- When additivity/parent handlers are enabled, an event may be printed multiple times across multiple sinks.

**There are two distinct types of negative assertions:**

1. **No event:** the logger is disabled/filtered, so the collector receives no record.
2. **Event present, but fields do not contain forbidden values:** the event is emitted, yet secrets are not exposed.

Do not test both cases with a single `assertFalse(console.contains(...))` and consider it sufficient; if the appender is misconfigured and writes **no events at all**, the privacy test will falsely PASS. You need a positive assertion proving the sink actually works.

Testing with a `Supplier` in JUL/SLF4J Fluent/Log4j 2 Supplier also verifies that **expensive expressions are not evaluated** when the level is disabled. The absence of a log message alone does not prove arguments were evaluated lazily: if you write `log.debug("value={}", expensive())`, Java still calls `expensive()` beforehand.

## 8. Testing Throwable: Message Text Does Not Replace the Exception

These two calls are different:

~~~java
// JUL: only text describing the exception; LogRecord.thrown remains null.
LOG.warning("failed: " + exception);

// JUL: the exception is properly attached to the event.
LOG.log(Level.WARNING, "failed", exception);
~~~

This is an illustration where `exception` is an existing `Throwable`. A test that only checks the text `"failed"` will **not** know whether the exception was lost.

In a JUL test:

~~~java
check(captured.thrown() == exception, "Throwable identity");
~~~

This requires `captured` to be an event snapshot and `exception` to be in test scope. Identity comparison is appropriate when you want to guarantee the exact object was passed. You can inspect type, cause chain, and message/class if needed; avoid asserting the entire stack trace when there is no stable contract on line numbers/source lines.

With SLF4J/Logback, check `ILoggingEvent.getThrowableProxy()` or the cause field per the API. With Log4j 2 Core, check `LogEvent.getThrown()` or the event throwable proxy depending on version. **Do not just search for the exception name in text**: a class name written into the message does not prove the backend received a structured `Throwable`.

**Privacy:** Exception messages, suppressed exceptions, MDC, and stack traces can carry tokens or PII. A "no secret leaked" event test must check the exception portion emitted by the encoder, not just `getFormattedMessage()`.

## 9. SLF4J: Mock the Call or Capture the Real Event?

SLF4J is a **facade**. A `logger.info(...)` call itself may be routed to Logback, Log4j 2, or another provider.

Two testing approaches:

**A. Mock the logger/call site:** Useful when code is designed around a small injected interface like `EventLogger` or `AuditRecorder`. You can verify the method was called with the right `eventCode` and args. This is fast, but does not prove the provider, level, layout, sink, or stack trace.

**B. Capture events from the real backend:** Attach a test appender to the designated logger, invoke the business logic, and assert on `ILoggingEvent`/`LogEvent`. This is the right approach when the goal is **testing messages** at the event level and verifying routing.

Example of a business method using SLF4J:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

final class OrderPublisher {
    private static final Logger LOG =
            LoggerFactory.getLogger(OrderPublisher.class);

    void reportSuccess(String orderId) {
        LOG.info("order={} state={}", orderId, "PAID");
    }
}
~~~

This snippet **requires `slf4j-api` and a provider**. When using a static logger, direct mocking can be difficult or couple the test to the implementation; a backend-specific test appender is usually simpler for event verification.

However, the backend test must match the runtime version. Do not use Logback's `ListAppender` when production/test runtime actually runs the Log4j 2 backend.

## 10. Logback Classic: JUnit 5 Example with ListAppender

When the application uses **SLF4J + Logback Classic** and JUnit Jupiter, you can attach `ch.qos.logback.core.read.ListAppender<ILoggingEvent>`. It collects events into an in-memory list, allowing you to inspect both the template and the formatted message.

Example test class **LogbackMessageTest.java**:

~~~java
import ch.qos.logback.classic.Level;
import ch.qos.logback.classic.Logger;
import ch.qos.logback.classic.spi.ILoggingEvent;
import ch.qos.logback.core.read.ListAppender;
import org.junit.jupiter.api.Test;
import org.slf4j.LoggerFactory;

import static org.junit.jupiter.api.Assertions.*;

class LogbackMessageTest {
    @Test
    void capturesMessageTemplateAndArguments() {
        Logger logger =
                (Logger) LoggerFactory.getLogger("test.orders.message");
        Level previousLevel = logger.getLevel();
        boolean previousAdditivity = logger.isAdditive();

        ListAppender<ILoggingEvent> appender = new ListAppender<>();
        appender.setContext(logger.getLoggerContext());
        appender.start();
        logger.setLevel(Level.INFO);
        logger.setAdditive(false);
        logger.addAppender(appender);
        try {
            logger.info("order={} state={}", "ORD-42", "PAID");

            assertEquals(1, appender.list.size());
            ILoggingEvent event = appender.list.get(0);
            assertEquals(Level.INFO, event.getLevel());
            assertEquals("order={} state={}", event.getMessage());
            assertArrayEquals(
                    new Object[]{"ORD-42", "PAID"},
                    event.getArgumentArray());
            assertEquals("order=ORD-42 state=PAID",
                    event.getFormattedMessage());
        } finally {
            logger.detachAppender(appender);
            appender.stop();
            logger.setLevel(previousLevel);
            logger.setAdditive(previousAdditivity);
        }
    }
}
~~~

**Prerequisites to run:** The project needs compatible versions of JUnit 5, `slf4j-api`, and `logback-classic`/`logback-core`; this is **not** JDK-only code. Run according to your project's Maven/Gradle configuration. `LoggerFactory.getLogger(...)` must return a Logback `Logger`; if another backend is active, the cast will fail.

**Why this test is useful:**

- Verifies events produced by the **real logger/backend**, not just verifying a mock was called.
- Compares `getMessage()` (`{}` template), `getArgumentArray()` (arguments), and `getFormattedMessage()` (complete string).
- Proves the `INFO` level and event count.
- Attaches the appender to a dedicated test logger with `additive=false` to keep events from propagating to root.
- Uses `finally` to detach/stop the appender and restore level/additivity so subsequent tests are unaffected.

**Limitation:** `ListAppender` is an in-memory collector; it does **not** prove JSON output, encoding, file flush, or that a remote sink received the event. `ListAppender.list` is a plain list and should not be read/written concurrently from multiple threads without synchronization; for async logging, wait and use a thread-safe collection or an appropriate test appender.

When a test suite runs in parallel, mutating the configuration of a fixed-name logger can cause interference. Use a dedicated logger per test or isolate `LoggerContext` and manage its lifecycle.

## 11. Logback: MDC, Throwable, and No-Log Conditions

With Logback `ILoggingEvent`, you also have:

- `getLoggerName()`: name of the logger that actually emitted the event.
- `getMDCPropertyMap()`: key-value context on the event; useful for verifying propagation/snapshotting.
- `getThrowableProxy()`: exception information for the formatter.
- `getThreadName()`: source thread name on the event; avoid asserting auto-generated names unless controlled.
- `getMarkerList()` or the corresponding marker API for your version.

MDC tests should not only assert that the layout text contains `requestId`. If the goal is context propagation, check the field on the event, and test the layout separately if needed:

~~~java
// Illustration in a JUnit/Logback test with a captured event variable.
assertEquals("req-91",
        event.getMDCPropertyMap().get("requestId"));
~~~

In application code, use `MDC.putCloseable(...)` or `try/finally` to prevent context from leaking from one test to another. Never let one test forget `MDC.clear()/remove()` and cause a later test to PASS by accident due to stale data.

Testing exceptions:

~~~java
// Verify the proxy is non-null when log.warn("...", exception) is called properly.
assertNotNull(event.getThrowableProxy());
~~~

This is a fragment inside a test that already has an `ILoggingEvent` named `event`. If you need to confirm the exception type, read `getClassName()` on the proxy. Comparing an entire stack trace line-by-line is usually too brittle.

**Negative level test:** `logger.setLevel(Level.INFO)`, emit `debug(...)`, and assert the appender list gained no event. However, also emit an INFO event to verify the appender is active; otherwise, an empty-list test can falsely PASS when the appender was never started.

## 12. Log4j 2 Core: Testing with a Test Appender, Not Guessing Stdout

If the backend is Log4j 2, use `org.apache.logging.log4j.core.LogEvent` and an in-memory or test appender attached to a test-specific **LoggerContext/LoggerConfig**.

A test appender can capture an immutable snapshot in its `append` method:

~~~java
// Illustrative fragment inside a custom Log4j 2 Core appender.
// Not a standalone Java class: requires class declaration, lifecycle,
// a thread-safe collection, and wiring the appender to LoggerConfig.
@Override
public void append(org.apache.logging.log4j.core.LogEvent event) {
    capturedEvents.add(event.toImmutable());
}
~~~

In tests, check:

- `event.getLevel()` and `event.getLoggerName()`.
- `event.getMessage().getFormat()`: original format/template text depending on the `Message` type.
- `event.getMessage().getFormattedMessage()`: formatted text.
- `event.getThrown()`: actual `Throwable`.
- `event.getContextData()`: context map as `ReadOnlyStringMap`, checking structured fields such as `traceId`.
- Marker, source, timestamp, thread name only when part of the contract.

Do not assume every `Message` subtype uses the same `{}` syntax: `ParameterizedMessage` differs from `StringFormattedMessage` or `MapMessage`. If the application uses a different message factory, adjust assertions accordingly.

**Important with Async Logger/ReusableMessage:** Do not retain a mutable `LogEvent` reference or parameters array and assert on it later on the test thread. Snapshot at the appender boundary—for example with `event.toImmutable()`—or design the collector to store immutable fields separately. Verify your SDK/backend version before relying on internal APIs.

When you need to verify JSON Template Layout, **test the actual layout output** by parsing the JSON. Testing at the `LogEvent` level does not prove the JSON template, exception resolver, context fields, or key encoding are correct.

## 13. Testing Text Messages, Layouts, and Structured JSON

**Text layout:** An event can be right at the API level yet printed incorrectly due to the pattern. For example, a Logback/Log4j 2 pattern missing `%msg`, using the wrong newline, or an encoder using a different charset.

Include tests at the layout/sink level:

~~~text
eventCode=ORDER_PAID orderId=ORD-42 state=PAID
~~~

In production, this string may be wrapped with timestamp/level. Assert the message portion and semantic fields, unless the full-line format is an official contract with a downstream parser.

**JSON layout:** Structured logging may produce:

~~~json
{
  "eventCode": "ORDER_PAID",
  "level": "INFO",
  "orderId": "ORD-42",
  "state": "PAID",
  "attempt": 1,
  "credentialPresent": false
}
~~~

Tests should parse the JSON and verify:

1. `eventCode` is the expected string.
2. `attempt` is a **number**, not the string `"1"`, if the schema specifies a number.
3. `credentialPresent` is a boolean.
4. Secret keys such as `password` or `authorization` are absent.
5. Required correlation fields are present.
6. Vietnamese diacritics, Unicode, newlines, and quotes are properly escaped/encoded.
7. No extra or missing events occur when multiple messages are logged.

Two JSON objects with different key orders can still be semantically equivalent. Comparing the entire JSON string with fixed field order makes tests break unnecessarily.

**Schema/version:** When logs are automatically consumed by a collector or audit system, field names, types, and `schemaVersion` become a stable contract; tests should be stricter than for free-form human debug text.

## 14. When Must You Read Real Files or Real Console?

**Reading files** is appropriate to verify:

- The file appender created the right path and charset.
- The actual pattern/JSON encoder wrote the expected text/fields.
- Rotation or rollover policies create files according to the rules.
- Flush/close drains data when requested by the test.
- Audit/app/diagnostic sinks are separated according to configuration.

Use a temporary directory (JUnit `@TempDir`), avoiding production log paths, hardcoded filenames, or deleting other tests' data. After writing, **wait for processing and close/flush** the appender via its API before calling `Files.readString(path, UTF_8)`. If the appender has an async queue, flushing the stream does not automatically mean the queue has drained.

**Console/stderr:** Replacing `System.out/System.err` JVM-wide in a test can interfere with other tests, especially under parallel execution. In JUL, `ConsoleHandler` typically writes to stderr; in Logback/Log4j 2, the sink depends on configuration. Only redirect console in integration tests with controlled isolation, and restore streams in `finally`.

**Remote collector:** If business requirements demand logs reach a collector, test with a mock HTTP sink/ephemeral collector or test environment; distinguish "request sent" from "indexed and queryable." Do not rely on a fixed one-second sleep to conclude data has arrived.

## 15. Asynchronous Logging: Synchronizing Tests Properly

With `AsyncAppender`, AsyncLogger, background writers, or network shipping, calling `log.info(...)` and immediately asserting the collector has the event often creates **flaky tests**.

Wrong synchronization:

~~~java
// Illustrative snippet: arbitrary timing, dependent on CI machine speed.
log.info("job={}", jobId);
Thread.sleep(100);
assertEquals(1, captured.size());
~~~

The right approach is to use a **meaningful completion milestone**:

- A `CountDownLatch` counted down when the test appender **actually receives the event**.
- A `CompletableFuture`/test probe to wait for the event with an explicit **deadline**.
- The backend's `stop/drain/flush` lifecycle when testing the full pipeline.
- For remote collectors: bounded polling with a unique test ID, followed by content verification.

Conceptual fragment example:

~~~java
// Inside the test appender when the matching eventId is received:
latch.countDown();

// On the test thread, PASS only when the event actually arrives:
boolean arrived = latch.await(3, java.util.concurrent.TimeUnit.SECONDS);
assertTrue(arrived);
~~~

This is a **fragment** requiring `latch` and `assertTrue` from your test framework. Do not call `latch.countDown()` right at the log call site; that only proves the caller ran, not that the appender received the event.

**Async negative tests are harder than positive tests.** Not seeing an event immediately may just mean it has not been processed yet. To prove a message was filtered out, test the filter/level condition independently or wait for a deterministic barrier/drain before asserting absence. A fixed 50ms sleep is not a processing barrier.

**Event order:** With multiple threads or multiple async consumers, do not arbitrarily assert global log order. If the system only guarantees order within a partition or a single logger, test within that scope; otherwise, compare the set of events by event ID.

## 16. Testing Repeated Messages, Counts, and Non-Duplication

`assertContains("failed")` alone does not catch duplicate logging.

For example, an exception passing through multiple layers:

~~~text
Controller: log.error("failed")
Service:    log.error("failed")
Retry:      log.warn("failed")
~~~

If the contract specifies **one error event at the request boundary**, the test should assert:

- Exactly 1 ERROR event.
- Consistent event code and request ID.
- Stack trace is not printed repeatedly along the same path if policy forbids it.
- Retry debug/metric logs have their own event code and are not counted as new business failures.

If business logic specifies one log per retry, the test should assert **exactly three events with attempts 1, 2, 3** rather than trying to eliminate all duplicates. Distinguish **logical event ID** from **transport attempt**.

You can filter captured events by `eventCode` or template and count them, instead of checking `list.size()` on the entire sink when unrelated events may be present. In the pure-JDK demo in Section 5, `size()==3` is reasonable because the test logger is isolated and only emits three events.

## 17. Log Messages and Security: Testing Without Real Secrets

Use fake sentinels:

~~~text
TEST_SECRET_DO_NOT_LOG
TEST_PASSWORD_ONLY_FOR_TEST
TEST_CARD_NUMBER_NOT_REAL
~~~

Use synthetic test data; **never copy production credentials/PII** into fixtures or CI logs. Assertions should search for the sentinel across all accessible outputs:

- Formatted message and template.
- Arguments, key-value fields, MDC/ThreadContext.
- Throwable message, cause, and suppressed exceptions.
- Final JSON encoder/PatternLayout output.
- Console/file and collector records in integration tests.

A test that only checks `message.contains("TEST_SECRET") == false` can falsely PASS if the event was never emitted. Combine an assertion that the **expected event exists** with an assertion that the **secret is absent**.

Do not rely solely on regex masking in the layout: a log event may pass through another appender, another JSON encoder, or a log shipper before masking runs. Prefer **minimization/allowlisting at the source**, using sink redaction as an additional layer.

Also test **log forging**: input containing `\nERROR forged`, CR, control characters, or JSON escape sequences can fabricate fake entries if the formatter is unsafe. Assertions should verify the output is properly formatted/escaped and produces no extra forged records.

## 18. Testing Message Parameterization and Lazy Evaluation

Things not to confuse:

| API | Template | Mechanism |
| --- | --- | --- |
| JUL | `"id={0}"` | `MessageFormat`/`Formatter.formatMessage` |
| SLF4J | `"id={}"` | `{}` with backend/provider |
| Log4j 2 default | `"id={}"` | Typically via `ParameterizedMessage` |
| `String.format` at caller | `"id=%s"` | Builds string **before** logger call if invoked directly |

When the level is disabled:

~~~java
// Wrong if the goal is to avoid an expensive call:
log.debug("snapshot={}", expensiveSnapshot());
~~~

Even with placeholders, Java evaluates `expensiveSnapshot()` before calling the method. With SLF4J 2.x fluent builder:

~~~java
log.atDebug().addArgument(() -> expensiveSnapshot())
        .log("snapshot={}");
~~~

This snippet requires SLF4J 2.x and a corresponding logger. In JUL, use `Logger.log(Level, Supplier<String>)`. A test can increment a counter inside the supplier and assert **counter equals 0** when the level is disabled and **equals 1** when enabled. The demo in Section 5 verified the disabled case.

Do not test "laziness" merely by asserting the formatted text is absent; the expensive function may still have run even though the logger ultimately discarded the event.

## 19. Avoiding Environment-Brittle Assertions

Factors that commonly make log text differ between a laptop and CI:

- Timestamp, timezone, locale, and DST.
- Thread name, thread ID, virtual thread, pool index.
- IP address, hostname, process ID, ephemeral port.
- Map/JSON field order, exception source line numbers.
- Windows/Linux paths, path separators, CRLF/LF newlines.
- Locale-dependent number/date formatting and `toString()` implementations.
- Logger hierarchy/level mutated by other tests.
- Asynchronous batching, sampling, rate limiting, buffering/flushing.
- Versions of SLF4J, Logback, Log4j 2, or JSON encoder.

Mitigations:

1. Fix fixture domain values and locale/timezone **when they are part of the test contract**.
2. Assert semantic fields rather than depending on the entire log sentence if it is not standardized.
3. Use dedicated loggers to avoid out-of-scope global configuration.
4. For stack traces, check type/cause/metadata rather than comparing every line and line number.
5. Use bounded timeouts for async, not `Thread.sleep` guesses.
6. Test Unicode and multiple OSes if messages are processed by another parser/collector.
7. Restore logger level, additivity, appenders, and MDC after each test.

If the contract requires **byte-level formatting**, byte-level tests are appropriate, but you must pin charset, newline, timezone, and version rather than assuming they never change.

## 20. How Do Unit Tests, Component Tests, and Integration Tests Differ?

| Type | Setup | Captures | Does Not Prove |
| --- | --- | --- | --- |
| JUL in-memory handler unit test | No dependencies outside JDK | Template, level, arguments, Throwable, event count | File/stdout/collector |
| Mocked AuditRecorder/EventLogger unit test | Fake/mock interface | Business branch calls the right recorder | Logger backend received it |
| Logback ListAppender component test | SLF4J + Logback test runtime | Backend event, MDC, level, Throwable proxy | Final JSON/file output |
| Log4j 2 appender component test | Isolated Log4j 2 Core config | LogEvent and routing | Remote delivery |
| Formatter/encoder test | Real layout, deterministic input | Formatted text/JSON schema, escaping | Network/storage completion |
| File sink integration test | FileAppender/FileHandler + temp dir | Path, charset, flush/close | Durability on machine crash |
| Collector end-to-end test | Broker/agent/collector test environment | Ingest, parsing, indexing, correlation | All production crash/permission states |

Do not cram every requirement into one giant test. Have multiple clearly scoped tests that separate responsibilities across business logic, event contracts, and environment configuration.

## 21. Extending the Example with JUnit 5 and Test Fixtures

When converting the `MessageLoggingTest` demo into a JUnit unit test:

- Set up the test handler in `@BeforeEach` or inside the test method.
- Use `@AfterEach` or `try/finally` to detach the handler and restore the level.
- Use `assertEquals`, `assertSame`, `assertArrayEquals`, and `assertFalse` instead of `check`.
- Use `@TempDir` if the test writes file output.
- If handling async, add latches/futures in the fixture with a bounded deadline.
- Do not share the `""`/root logger across all tests when running in parallel.

**Ensuring isolation:** JUL loggers can be reused from `LogManager` by name, so simply creating a new `Logger` variable in a test is not enough if you ignore global state. When modifying level, filter, parent handlers, or attached handlers, save the previous values and restore them at the end of the test.

A good fixture captures only events from the application under test, does not alter test-runner framework logs, and does not print secret records to the CI console.

## 22. Recommended Test Case Suite for Log Messages

| Test Case | Stimulus | Assertion |
| --- | --- | --- |
| Normal INFO message | Successful operation | Template, args, formatted text, and count match |
| Multi-parameter placeholder | 2–3 arguments | No lost or swapped argument positions |
| Null data | Missing field | Formatter does not crash, renders per contract |
| Unicode characters | Vietnamese, emoji | No charset corruption, text/JSON valid |
| Message with quotes/newlines | Fake untrusted input | Safe escaping, no forged lines |
| Direct exception | `IllegalStateException` | Throwable field/proxy is accurate |
| Exception with cause | Wrapper exception | Cause chain preserved when policy requires |
| FINE/DEBUG level disabled | Debug log call | No event emitted; Supplier does not run |
| FINE/DEBUG level enabled | Debug log call | Event emitted with right logger/level |
| Filter/marker | Matching/non-matching event | Kept/dropped at the right sink |
| MDC | requestId set and cleaned up | No bleed across requests/tests |
| Duplicate | One operation emitted multiple times | Count matches contract, no extra logs |
| Privacy | Fake token/password sentinel | Absent from event and sink |
| Formatter | PatternLayout or custom formatter | Text correct, no unintended Throwable output |
| JSON schema | Known keys and types | Parse JSON, assert fields, ignore key order |
| Async | Write to queue | Wait on appender with deadline, no blind sleep |
| File sink | Flush/close via temp dir | Content readable in expected charset |
| Collector | App → ingest integration | Event reaches collector with event ID |
| Configuration off | Different level/filter/sink | Detects unintended logger silence |
| Parallel tests | Multiple loggers/test cases | No leaked handlers, MDC, or level changes |

Not every project needs every test. Choose depth by risk: audit/security messages or log formats contracted with a collector need stricter testing than human-only debug text.

## 23. Common Mistakes

| Mistake | Problem | Fix |
| --- | --- | --- |
| Only verifying `log.info(...)` was called | Doesn't tell if level/backend emitted an event | Capture `LogRecord`/`ILoggingEvent`/`LogEvent` |
| Comparing `LogRecord.getMessage()` to `{0}`-substituted text | Confuses template with formatted output | Use `Formatter.formatMessage` |
| Using `{}` in JUL | Wrong API placeholder | Use `{0}`, `{1}` |
| Comparing full console lines with real timestamps | Flaky across clocks/locales/threads | Assert semantic fields or fix metadata |
| Testing Logback by attaching an appender to root | Collides with other tests, causes duplicates | Dedicated logger, detach in `finally` |
| Forgetting to start the appender | Events never arrive, negative tests falsely PASS | Assert a positive event first |
| Treating `ListAppender` as a JSON output test | Does not test encoder/layout | Test the JSON encoder directly |
| Holding mutable `LogEvent` across async | Fields may be reused/mutated | Snapshot/memento during `append` |
| `Thread.sleep(100)` for async waiting | CI runs faster/slower inconsistently | Latch/Future/barrier with a deadline |
| Asserting no log immediately after an async call | Event may still be in flight | Drain/await before negative assertion |
| Only asserting `contains("failed")` | Misses duplicates/wrong event code | Assert count, level, template, args |
| Only testing message when an exception occurs | Doesn't verify actual `Throwable` attachment | Assert `getThrown`/`getThrowableProxy` |
| Ignoring MDC/ThreadContext | Context may leak or mix | Test propagation and cleanup |
| Logging fake raw tokens to shared console for privacy tests | Easy to leak into CI logs | In-memory capture, test sentinels, no real secrets |
| Not restoring logger config | Breaks other tests, hard to reproduce | `try/finally` or test fixture lifecycle |
| Inferring durability from test output | Rendered does not mean fsynced/committed | Test sink durability contract separately |

## 24. Code Review Checklist Before Adding Logging Tests

1. Does the test specify the **testing layer**: call site, event, formatter, sink, or collector?
2. Is there a contract for event code, template, arguments, level, count, and `Throwable`?
3. Are the right API placeholders used: JUL `{0}`, SLF4J/Log4j 2 `{}`?
4. Does it distinguish `getMessage()` from `getFormattedMessage()`/`formatMessage()`?
5. Is there a positive assertion proving the appender actually received an event?
6. Are there negative assertions for extra events, disabled levels, and fake secrets?
7. Is the handler/appender attached to the right logger, started, and cleaned up?
8. Does the test avoid accidentally mutating root level, stdout/stderr, or global configuration?
9. Is the exception properly attached to the event; are cause and MDC checked when needed?
10. For JSON, does it parse and assert keys/types/escaping instead of comparing raw strings?
11. For async, does it wait on a reliable completion/barrier before asserting?
12. For file/collector, does it use an isolated directory and test environment?
13. Does it use synthetic data, with no real passwords/tokens/PII in fixtures or CI logs?
14. Does it cover Unicode, nulls, multiple parameters, escaping, and logger hierarchy?
15. When switching backends/versions, does the test state its assumptions and specific API packages?
16. Are test results reliable across parallel runs and multiple operating systems?

## 25. Self-Check Questions

1. In JUL, how does `LogRecord.getMessage()` differ from `Formatter.formatMessage(record)`?
2. Why is mocking and verifying `logger.info(...)` insufficient to prove an event was written to a file?
3. When DEBUG is disabled, does the absence of a log message prove `expensive()` did not run?
4. When logging an error, how do you know the `Throwable` was attached to the event rather than merely concatenated into text?
5. Why is Logback's `ListAppender` not enough to prove a JSON encoder outputs the right schema?
6. Why should you attach a test appender to a dedicated logger and restore level/additivity in `finally`?
7. What waiting mechanism should async pipeline event tests use instead of `Thread.sleep`?
8. Why can a negative assertion immediately after an async log call falsely PASS?
9. Should structured JSON be tested by string comparison or JSON parsing? Why?
10. Why does a privacy test need both a positive assertion that the event is present and a negative assertion that it contains no sentinel?
11. When a business operation logs ERROR twice across controller and service, what issue does `contains("failed")` miss?
12. When using `Log4j 2 LogEvent` through an async appender, why might `toImmutable()` be needed?
13. Should timestamps, timezones, thread IDs, and stack trace line numbers always be hardcoded in expected messages?
14. Can you conclude a file is durable on disk just because a test appender received the event?

**Hints:** (1) raw template vs. formatted text; (2) filters, layout, sink, and write errors still sit in between; (3) no, arguments can be evaluated eagerly; (4) assert `getThrown`/Throwable proxy; (5) JSON encoder has not run; (6) isolate state; (7) latch/future/barrier with deadline; (8) event may not have arrived yet; (9) parse and compare fields/types; (10) avoid false PASS when the sink is silent; (11) duplicates; (12) avoid holding mutable/reused events; (13) only when required by contract and metadata is pinned; (14) no.

## 26. Official References

- [Java SE 17 — LogRecord](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/LogRecord.html): `getMessage()`, `getParameters()`, `getThrown()`, level, timestamp.
- [Java SE 17 — Logger](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Logger.html): logging overloads, levels, `Supplier`, and handlers.
- [Java SE 17 — Handler](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Handler.html): `publish`, `isLoggable`, lifecycle.
- [Java SE 17 — Formatter](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Formatter.html): `formatMessage(LogRecord)` and localization.
- [SLF4J Manual](https://www.slf4j.org/manual.html): parameterized logging, fluent API, provider/backend.
- [Logback — Manual](https://logback.qos.ch/manual/index.html): configuring loggers/appenders, layouts, and MDC.
- [Logback — Appenders](https://logback.qos.ch/manual/appenders.html): appender lifecycle/filters, event capture points.
- [Log4j 2 — API](https://logging.apache.org/log4j/2.x/manual/api.html): Logger, Message, Throwable, and event API.
- [Log4j 2 — Messages](https://logging.apache.org/log4j/2.x/manual/messages.html): message templates and Message types.
- [Log4j 2 — JSON Template Layout](https://logging.apache.org/log4j/2.x/manual/json-template-layout.html): schema, field resolution, and JSON encoding.
- [JUnit User Guide](https://docs.junit.org/current/user-guide/): JUnit Jupiter assertions, lifecycle, and `@TempDir`.
- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): data not to log, sanitization, and log injection.
