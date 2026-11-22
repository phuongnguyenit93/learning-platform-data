# Avoiding Overly Format-Dependent Tests When Testing Logging in Java

## 1. The problem: tests pass or fail because of log formatting, not behavior

When testing logging, a tempting approach is to capture stdout or file contents and compare an **entire log line** against an expected string:

```text
2026-01-01 10:00:00.123 INFO [main] example.OrderService - Cancel rejected: orderId=O-42
```

However, that string contains many *presentation* elements: timestamp, timezone, thread name, logger name, whitespace, delimiters, and message formatting. Simply changing the Logback pattern, changing the locale/timezone, running through a thread pool, switching to a JSON encoder, or updating a library can cause the test to fail even though **the business event and logging decision have not changed**.

Conversely, a test that only checks whether a string contains `"ERROR"` can also pass falsely when the code emits a different message containing the word ERROR, even though **the actual level is INFO** or the Throwable was lost.

**Goal:** test the **observable contract** of the application rather than freezing every detail of how logs are rendered. For most business unit/integration tests, ask:

- Was the event emitted, and the right **number of times**?
- Does the event have the right **level**?
- Is the event associated with the appropriate **logger/component**?
- Are the **action, outcome, reasonCode, resourceId, and correlation ID** correct?
- When technical diagnosis is needed, is the **Throwable/cause** attached?
- Are sensitive events **dropped or redacted** according to policy?
- If a logger/filter/delivery layer is blocked, what actually reaches the **sink**?

Only test the **exact format** when the format itself is part of the requirement—for example, a JSON log ingestion contract, escaping to prevent log injection, parser field names, or an audit format committed to by customers or downstream systems.

## 2. Separating three layers: event, presentation, and transport

A typical logging pipeline:

```text
Business code
    |
    | logger.info("action={} outcome={}", action, outcome)
    v
[SEMANTIC EVENT]
  level, loggerName, template, arguments,
  MDC, marker, throwable, timestamp...
    |
    v
[ENCODER / FORMATTER]
  PatternLayout / JSON encoder / custom formatter
    |
    v
[DELIVERY]
  console, file, async queue, agent, network collector
    |
    v
[OBSERVED OUTPUT]
  text line, JSON object, indexed log, alert
```

Different layers should have appropriate tests:

| Layer | Testing question | Preferred observation method |
| --- | --- | --- |
| **Event semantics** | Is it logged with the right level, message template, arguments, and context? | Capture `ILoggingEvent` or `LogRecord` in memory |
| **Logging policy/filter** | Which events are allowed to reach an appender? | Capture at the appender after the filter, inspect the event set |
| **Encoder** | Does the output have the JSON fields, escaping, and timestamp matching the contract? | Feed a fixed event to the encoder, parse the structured output |
| **Transport/delivery** | Do logs reach the file/collector, drain after async, and handle errors properly? | Integration test at the real sink with timeout/ack/fault injection |
| **Audit/business result** | Do business state and audit events match? | Compare database/result with events, do not just mock the logger |

If the requirement is "a rejected operation must have a reasonCode", unit tests should not fail just because the pattern changes from `%d %-5level %msg%n` to JSON. But if the ingestion system requires a string JSON field named `reasonCode`, that **is a format contract** and needs its own test.

## 3. Elements that make full-line comparisons brittle

| Element | Why it changes even when the app is correct | Recommendation |
| --- | --- | --- |
| Timestamp and precision | Clock, timezone, format style, resolution | Check for a valid timestamp or inject `Clock`; do not hardcode "current time" |
| Thread name | JUnit runner, executor, virtual threads, thread pool | Only assert thread when required; do not rely on `main` |
| Logger name | Package/class refactoring, logger wrappers | Assert namespace/event type if that is the contract |
| Level text/padding | `INFO`, `INFO `, alignment, ANSI colors | Assert the event's enum level |
| Whitespace/line endings | Linux `\n`, Windows `\r\n`, layout changes | Parse data or normalize when format truly matters |
| Throwable/stack trace | Class names, line numbers, suppressed/cause, JDK | Assert exception type/cause, do not compare the entire trace |
| Ordering | Async appenders, multiple threads, batching | Match by ID/set; only check ordering where guaranteed |
| Localized message | Locale and message bundles | Assert `reasonCode` or error type |
| MDC fields | Context propagation, added/removed keys | Assert required fields, do not compare every field |
| JSON field order | Serializers usually do not guarantee key order | Parse JSON and compare fields, do not compare JSON strings |
| Escaping | Encoder changes equivalent escape order/style | Parse output and compare meaning; test escaping at the encoder level |
| Log pattern | Adding `traceId`, `spanId`, changing layout | Test semantic events independently of the pattern |

**Brittle tests** fail frequently due to changes outside the behavior being protected. **Overly loose tests** pass when logs are missing critical data. The solution is not to drop all assertions, but to choose **the contract at the right layer**.

## 4. When to assert exact values vs. semantics only

A practical rule of thumb:

- **Assert exact values** for codes with stable contracts: `action=ORDER_CANCEL`, `outcome=REJECTED`, `reasonCode=ORDER_ALREADY_SHIPPED`, level enum, event count, required IDs.
- **Do not assert exact values** for full real timestamps, thread names assigned by JUnit, call stack class/method/line, whitespace positions, and file paths if they are not part of the contract.
- **Only assert the message template** when the template itself is a controlled contract (e.g., a downstream parser still relies on the template) or when the test wants to prove arguments are passed properly. In systems with structured fields, prefer asserting fields over text templates.
- **Only assert ordering** when causality or protocol specifies it. Requiring an operation's `STARTED` event before `FINISHED` may be a contract; ordering between two independent concurrent requests usually is not.
- **Only assert exception class/cause** when testing error-handling contracts; do not pin individual stack trace frames.
- **Keep a few dedicated snapshot/golden tests** for formats with compatibility requirements (JSON exporters, audit systems, log shipping protocols). Keep them at the encoder layer rather than duplicating them across every business unit test.

Example comparing two testing approaches:

```java
// Brittle: timestamp, thread, and logger layout are all locked down.
assertEquals(
    "2026-01-01 10:00:00 INFO [main] OrderService - Rejected order O-42",
    capturedConsoleLine);

// More resilient: when using Logback ILoggingEvent in tests.
assertEquals(Level.INFO, event.getLevel());
assertEquals("ORDER_ALREADY_SHIPPED",
             event.getMDCPropertyMap().get("reasonCode"));
```

This is an **illustrative snippet**, not a standalone Java file. An important precondition: to assert MDC, the event must be captured from the right thread/moment and there must be a policy of placing `reasonCode` in MDC; if the application does not use MDC for that field, inspect the corresponding structured key/value or message arguments instead. Do not put every business field into MDC just to make testing convenient.

## 5. Understanding log structures in JUL and Logback

Java has multiple logging ecosystems:

- **`java.util.logging` (JUL)** in the JDK provides `Logger`, `LogRecord`, `Handler`, and `Formatter`. `LogRecord` holds level, logger name, message, parameters, thrown, and timestamp.
- **SLF4J** is a facade. `logger.info("item={} status={}", item, status)` is a facade call, while how the event is stored depends on the backend.
- **Logback** provides `ILoggingEvent` with level, loggerName, template `getMessage()`, `getArgumentArray()`, `getFormattedMessage()`, `getMDCPropertyMap()`, and `getThrowableProxy()`.
- **Log4j2** has its own events/appenders and test APIs; you cannot directly cast an event to Logback's `ILoggingEvent` if the backend is Log4j2.

When the goal is testing semantics, capture at **the point closest to the event** that still verifies integration. When you want to test console JSON, test the encoder as well; when you want to test collector loss, test the sink/transport as well. Do not turn a test for a single business rule into an all-layer integration test unless needed.

## 6. Standalone Java 17: inspecting log events instead of formatter strings

The following pure-JDK example demonstrates capturing `LogRecord` using an in-memory `Handler`. No SLF4J, Logback, or Maven is needed. The program intentionally **does not configure a console pattern**: it reads the event's level, template, parameters, and Throwable directly, so changing `Formatter` does not affect the checks.

### 6.1. File `SemanticLogDemo.java`

```java
import java.util.ArrayList;
import java.util.List;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class SemanticLogDemo {
    public static void main(String[] args) {
        Logger logger = Logger.getLogger("example.logging.semantic");
        logger.setUseParentHandlers(false);
        logger.setLevel(Level.ALL);

        List<LogRecord> captured = new ArrayList<>();

        Handler memory = new Handler() {
            @Override
            public void publish(LogRecord record) {
                if (isLoggable(record)) {
                    captured.add(record);
                }
            }

            @Override
            public void flush() {}

            @Override
            public void close() {}
        };
        memory.setLevel(Level.ALL);
        logger.addHandler(memory);

        try {
            logger.log(
                Level.INFO,
                "action={0} outcome={1}",
                new Object[] {"ORDER_CANCEL", "REJECTED"});

            logger.log(
                Level.SEVERE,
                "dependency failed",
                new IllegalStateException("simulated"));

            LogRecord businessEvent = captured.get(0);
            LogRecord errorEvent = captured.get(1);

            System.out.println("events=" + captured.size());
            System.out.println("firstLevel="
                    + businessEvent.getLevel().getName());
            System.out.println("firstTemplate="
                    + businessEvent.getMessage());
            System.out.println("action="
                    + businessEvent.getParameters()[0]);
            System.out.println("outcome="
                    + businessEvent.getParameters()[1]);
            System.out.println("hasThrowable="
                    + (errorEvent.getThrown() != null));

            logger.setLevel(Level.WARNING);
            logger.info("ignored by level");
            System.out.println("afterDisabledInfo="
                    + captured.size());
        } finally {
            logger.removeHandler(memory);
            memory.close();
        }
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac SemanticLogDemo.java
java SemanticLogDemo
```

**Exact expected stdout** when running the program standalone:

```text
events=2
firstLevel=INFO
firstTemplate=action={0} outcome={1}
action=ORDER_CANCEL
outcome=REJECTED
hasThrowable=true
afterDisabledInfo=2
```

Explanation:

1. `Handler` receives the exact two initial `LogRecord`s because both the logger and handler allow everything from `Level.ALL`.
2. `LogRecord.getMessage()` returns the **message template**, not the full console line. Parameters remain accessible via `getParameters()`.
3. `LogRecord.getThrown()` checks whether a Throwable was attached to the event without rendering a stack trace.
4. When the logger switches to `Level.WARNING`, the `logger.info(...)` call is blocked and the event count remains two.
5. `Logger.setUseParentHandlers(false)` prevents root handlers from producing extra output; `finally` removes the handler so no test appender is left behind.

This is a **single-threaded** demo with an in-memory sink. It does not prove exact JSON or console formatting, nor does it prove a collector persisted anything. In real multi-threaded tests, you need a thread-safe collector and clear completion rules. Do not use the demo `ArrayList` as a production appender.

**Notably:** the program does not assert thread names, timestamps, or final formatted strings. It verifies what **must remain true even if the format changes**.

## 7. JUnit 5 + SLF4J/Logback: capturing `ILoggingEvent` properly

In a project using SLF4J with Logback, you can attach an event-capturing appender to a **dedicated test logger**. The test can then inspect level, template, arguments, MDC, and Throwable without depending on `PatternLayout`.

### 7.1. Maven structure

```text
log-semantic-tests/
├── pom.xml
└── src/
    └── test/
        └── java/
            └── example/
                └── LoggingContractTest.java
```

`pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>example</groupId>
    <artifactId>log-semantic-tests</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>ch.qos.logback</groupId>
            <artifactId>logback-classic</artifactId>
            <version>1.5.16</version>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.11.4</version>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.2.5</version>
            </plugin>
        </plugins>
    </build>
</project>
```

The pinned versions illustrate a reproducible environment and **do not imply the latest versions**. For real applications, use unified dependency management and ensure only one active SLF4J provider is on the classpath.

### 7.2. Complete test code

Save `src/test/java/example/LoggingContractTest.java`:

```java
package example;

import ch.qos.logback.classic.Level;
import ch.qos.logback.classic.Logger;
import ch.qos.logback.classic.LoggerContext;
import ch.qos.logback.classic.spi.ILoggingEvent;
import ch.qos.logback.core.AppenderBase;
import org.junit.jupiter.api.Test;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;

import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.CopyOnWriteArrayList;

import static org.junit.jupiter.api.Assertions.*;

class LoggingContractTest {

    // Captures events AFTER logger and appender levels/filters.
    static final class CaptureAppender
            extends AppenderBase<ILoggingEvent> {
        private final CopyOnWriteArrayList<ILoggingEvent> events =
                new CopyOnWriteArrayList<>();

        @Override
        protected void append(ILoggingEvent event) {
            // Freeze lazy fields such as formatted message/MDC
            // while the event is still in the producing thread's context.
            event.prepareForDeferredProcessing();
            events.add(event);
        }

        List<ILoggingEvent> snapshot() {
            return List.copyOf(events);
        }
    }

    static final class Rig implements AutoCloseable {
        final Logger logger;
        final CaptureAppender capture;

        Rig() {
            LoggerContext context =
                    (LoggerContext) LoggerFactory.getILoggerFactory();

            logger = context.getLogger(
                    "example.test.logging." + UUID.randomUUID());
            logger.setLevel(Level.TRACE);
            logger.setAdditive(false);

            capture = new CaptureAppender();
            capture.setContext(context);
            capture.setName("capture-" + UUID.randomUUID());
            capture.start();

            logger.addAppender(capture);
        }

        @Override
        public void close() {
            logger.detachAppender(capture);
            capture.stop();
        }
    }

    @Test
    void checksLevelArgumentsAndMdcInsteadOfRenderedLine() {
        Map<String, String> previous = MDC.getCopyOfContextMap();

        try (Rig rig = new Rig()) {
            MDC.put("requestId", "req-17");

            rig.logger.info(
                    "action={} outcome={}",
                    "ORDER_CANCEL", "REJECTED");

            List<ILoggingEvent> events = rig.capture.snapshot();
            assertEquals(1, events.size());

            ILoggingEvent event = events.get(0);
            assertEquals(Level.INFO, event.getLevel());
            assertEquals(
                    "action={} outcome={}", event.getMessage());
            assertArrayEquals(
                    new Object[] {"ORDER_CANCEL", "REJECTED"},
                    event.getArgumentArray());
            assertEquals(
                    "req-17",
                    event.getMDCPropertyMap().get("requestId"));
        } finally {
            if (previous == null) {
                MDC.clear();
            } else {
                MDC.setContextMap(previous);
            }
        }
    }

    @Test
    void keepsTheRealThrowableWithoutCheckingStackFrames() {
        try (Rig rig = new Rig()) {
            IllegalStateException problem =
                    new IllegalStateException("simulated");

            rig.logger.error(
                    "Payment failed id={}", "pay-7", problem);

            ILoggingEvent event = rig.capture.snapshot().get(0);

            assertEquals(Level.ERROR, event.getLevel());
            assertEquals("Payment failed id={}", event.getMessage());
            assertNotNull(event.getThrowableProxy());
            assertEquals(
                    IllegalStateException.class.getName(),
                    event.getThrowableProxy().getClassName());
        }
    }

    @Test
    void confirmsDisabledLevelProducesNoInfoEvent() {
        try (Rig rig = new Rig()) {
            rig.logger.setLevel(Level.WARN);

            rig.logger.info("Not visible {}", "detail");
            rig.logger.warn("Degraded dependency {}", "storage");

            List<ILoggingEvent> events = rig.capture.snapshot();
            assertEquals(1, events.size());
            assertEquals(Level.WARN, events.get(0).getLevel());
            assertEquals(
                    "Degraded dependency {}",
                    events.get(0).getMessage());
        }
    }
}
```

Run from the directory containing `pom.xml`, requiring JDK 17+ and Maven:

```bash
mvn test
```

**Expected:** 3 tests pass and Maven reports `BUILD SUCCESS` if dependencies can be downloaded and the environment is configured properly. Detailed Maven/Surefire output may vary; check `target/surefire-reports` when an assertion fails.

### 7.3. Why does this approach reduce brittle tests?

- The first test asserts the **level** via enum and **template + argument array** instead of the full formatted line. If the console pattern changes or a timestamp is added, the test still passes.
- The second test asserts that **ThrowableProxy** has the right exception class. It does not force the test to compare stack line numbers, file paths, or JVM frame ordering.
- The third test confirms the logger level blocks `INFO` while `WARN` remains. It does not infer filtering from the absence of a line on stdout.
- The test logger has a **dedicated name** and `additive=false` so events do not leak into root appenders and cause noise. `try-with-resources` always detaches the appender after each test.
- `prepareForDeferredProcessing()` is called in `append` so data such as MDC is snapshotted while still in the producer's context; if you only keep a reference to the event and read MDC later, lazy fields can cause incorrect test results.
- `CopyOnWriteArrayList` is suitable for capturing small volumes in tests. It is not a high-throughput sink for benchmarks or production traffic.

**Limitations:** This is an in-memory logging-backend integration test; it does not test JSON encoders, files, or remote collectors. Random logger names isolate tests, so if the application has filters based on fixed logger names, test that policy separately with the appropriate logger name.

## 8. Do not over-mock the logger

A common test pattern:

```java
// Illustrative Mockito code in a project with mocks configured.
verify(logger).info(
    "Order {} rejected because {}",
    "O-42", "ORDER_ALREADY_SHIPPED");
```

This check can be useful if **the template itself is the contract** of an adapter, but it has many drawbacks:

- The test locks down the exact method overload and argument count, even though the log at the sink could still be valid after a refactor.
- It does not verify that the logger level is enabled, that filters/appenders are wired properly, or that the final event reaches the sink.
- It does not verify MDC, markers, Throwable, or encoders if those are not part of the mock.
- It can fail over wording changes in the message that do not alter business outcomes.
- If a mock is shared, call counts are easily affected by helper code or internal retries.

**Prioritize testing component behavior first.** For a requirement like "each business rejection emits one audit event", capture the real event or an audit publisher interface and assert action/outcome/reasonCode/count, rather than forcing the entire message text to match an English sentence.

Mocking is still appropriate in unit tests of **a logging adapter** when you need to confirm data is forwarded to an interface. However, that tests the adapter contract, not as a substitute for backend integration tests.

## 9. Checking meaningful values: avoid overly broad `contains`

Avoid swinging from overly strict tests to overly loose ones:

```java
assertTrue(line.contains("ERROR"));
assertTrue(line.contains("order"));
```

Both assertions can pass for the message `"order not found ERROR_LABEL"` even when the actual level is INFO, or when the event belongs to a different order. Similarly, `assertNotNull(event)` does not verify the failure reason or correlation ID.

### How to choose assertions

- **Level:** compare `event.getLevel()` rather than searching for the word `ERROR` in the message.
- **Message template/arguments:** compare the `(template, arguments)` tuple if the application still passes fields via placeholders; or compare structured fields by key/type.
- **Business outcome:** compare `eventType`, `action`, `outcome`, `reasonCode`, and allowed resource IDs.
- **Exception:** compare class/cause/cause chain per contract, not every stack frame.
- **Count:** `assertEquals(1, events.size())` when exactly one event is the contract; avoid only asserting `anyMatch` if duplicates are a bug.
- **Presence/absence:** test both valid emissions and cases that **must not be emitted** (level/filter/secrets).
- **Causality:** only assert ordering between milestones guaranteed by the contract.

If you have built a dedicated `AuditEvent` class, test that object as business data—code, enum, ID, timestamp—and test the logging adapter that forwards it to the sink in a separate layer. This is more resilient than parsing messages back out of a console line.

## 10. Structured logging and JSON: test the schema, not key order

A JSON event produced by a formatter:

```json
{
  "timestamp": "2026-01-01T10:00:00Z",
  "level": "INFO",
  "service": "order-service",
  "eventType": "BUSINESS_OPERATION_RESULT",
  "action": "ORDER_CANCEL",
  "outcome": "REJECTED",
  "reasonCode": "ORDER_ALREADY_SHIPPED",
  "requestId": "req-17"
}
```

If downstream systems require these fields, **the JSON format is a real contract**. Still, comparing raw JSON strings is unnecessary: key order, indentation, or equivalent escape encodings can change while JSON semantics remain identical.

Example in a project already using Jackson:

```java
// Illustrative snippet; requires ObjectMapper, JsonNode,
// outputJson, and appropriate Jackson imports.
JsonNode node = objectMapper.readTree(outputJson);

assertEquals("INFO", node.path("level").asText());
assertEquals("BUSINESS_OPERATION_RESULT",
             node.path("eventType").asText());
assertEquals("ORDER_CANCEL",
             node.path("action").asText());
assertEquals("REJECTED",
             node.path("outcome").asText());
assertEquals("ORDER_ALREADY_SHIPPED",
             node.path("reasonCode").asText());
assertTrue(node.path("timestamp").isTextual());
```

**Note:** `path(...).asText()` may return an empty string when a field is missing. When the schema requires mandatory fields and specific types, add `hasNonNull`, `isTextual`, and schema validation. Do not treat the few assertions above as complete JSON schema validation.

If the contract requires **one JSON object per line** (NDJSON), tests can verify that each line parses into a JSON object and contains no control characters that break records; do not force whitespace or key order to match a golden text file.

### Test what the encoder must actually guarantee

| Requirement | How to test |
| --- | --- |
| Valid `timestamp` field | Parse ISO-8601 and check range/clock if applicable |
| `level` and `reasonCode` | Check keys and types/values |
| `requestId` is not dropped | `hasNonNull` + string type |
| Message containing `\r\n` | Serialize/parse stays a single JSON object with valid escaping |
| Vietnamese Unicode | Parse round-trip and compare content |
| Throwable | Check exception/type/stack fields per schema without relying on line numbers |
| Schema version | Assert `schemaVersion` and version compatibility |
| Sensitive information | Use a dummy token, check fields/output at every sink that must be protected |

If there is an uncontrolled consumer or a legacy format fixed byte-for-byte, you may need a **golden-file test** of the verbatim output. That is an exception with a specific reason, not the default for every logging test.

## 11. Timestamp, Clock, and timezone: controlled testing

Avoid:

```java
assertEquals(
    "2026-01-01 10:00:00.000",
    extractTimestamp(logLine));
```

if the application actually uses `Instant.now()`. CI systems running in different timezones, slow schedulers, or different clock precisions will make the test fail randomly.

Three strategies:

1. **Inject `Clock`:** business classes/event producers create timestamps with `Instant.now(clock)`. In tests, use `Clock.fixed(...)`; only assert a fixed timestamp when you control the time source.
2. **Assert validity:** parse the timestamp and verify it falls between before and after the operation within a reasonable tolerance, if the contract does not require an exact instant.
3. **Test the formatter separately:** feed an event with a fixed timestamp to the encoder and verify the specified timezone/format.

Java 17 illustrative code:

```java
Clock fixed = Clock.fixed(
    Instant.parse("2026-01-01T10:00:00Z"),
    ZoneOffset.UTC);
Instant occurredAt = Instant.now(fixed);
assertEquals(
    Instant.parse("2026-01-01T10:00:00Z"),
    occurredAt);
```

This snippet uses `Clock`, `Instant`, `ZoneOffset`, and `assertEquals` from JUnit; it is not a standalone program. With backend loggers, event timestamps may be generated by the framework rather than the application's `Clock`; if you need to test the exact formatter timestamp, control the event/encoder instead of trying to alter the real system clock.

Do not normalize all timestamps to a single value in production: tests should only control the clock within the scope of a fixture.

## 12. Exceptions and stack traces: test the essence, not frames

Exception stack traces can change when:

- Refactoring methods/packages or adding wrappers.
- JDK/compiler changes line numbers or frame counts.
- Running through reflection, proxies, Spring AOP, or thread pools.
- Loggers/encoders change how `cause` and `suppressed` are rendered.
- The same Throwable is logged at different layers.

Brittle example:

```java
assertTrue(text.contains("at com.example.PaymentService.pay(PaymentService.java:87)"));
```

Moving code or adding a single line breaks the test. If the actual requirement is "dependency failure preserves the cause", check:

```java
assertEquals(Level.ERROR, event.getLevel());
assertNotNull(event.getThrowableProxy());
assertEquals(
    "java.net.SocketTimeoutException",
    event.getThrowableProxy().getClassName());
```

This snippet is based on Logback's `ILoggingEvent` and requires actually throwing/attaching a `SocketTimeoutException` in the fixture. If the application wraps exceptions, the test should inspect the **cause chain** per the contract, rather than forcing the top-level class to equal the root cause.

Some advice:

- For expected **business errors**, a `reasonCode`/outcome is usually enough; a full stack trace is not required.
- For unexpected **technical failures**, keep the Throwable with a useful cause at one responsible boundary, avoiding duplicate logging across multiple layers.
- If a requirement demands the encoder print exceptions, test that the encoder **includes the exception field/section**, rather than comparing every byte of the stack trace unless there is a special reason.
- Do not assert the caller's line number unless that itself is the feature under test, such as a debugging tool library that locates call sites.

## 13. MDC, correlation IDs, and thread propagation

A system needs `requestId` or `traceId` to correlate logs across services. Proper tests should:

1. Set a dummy correlation value such as `req-17`.
2. Execute the action within the appropriate MDC scope.
3. Capture the event while the context is still accurate.
4. Assert **the event's MDC map**, rather than searching for a string in output that depends on the `%X{requestId}` pattern.
5. Restore MDC in `finally` so other tests are not polluted.

With SLF4J:

```java
Map<String, String> before = MDC.getCopyOfContextMap();

try {
    MDC.put("requestId", "req-17");
    service.handle(command);
} finally {
    if (before == null) {
        MDC.clear();
    } else {
        MDC.setContextMap(before);
    }
}
```

This is a snippet in an application that already has `MDC`, `Map`, `service`, and `command`. Do not assume `requestId` is automatically present on `ExecutorService` workers, `CompletableFuture`, or reactive pipelines; context may need to be propagated explicitly. If a test must verify **context propagation**, use a real executor with another thread, capture the event on that thread, verify the right ID, and then verify the ID does not leak to the next task.

**Do not use real requestIds or bearer tokens in fixtures.** Test IDs should be non-sensitive, schema-valid, and repeatable.

## 14. Async logging: do not assert immediately and do not use `Thread.sleep`

When a backend uses an async appender, events may be placed in a queue and appended to the sink by another thread. This test:

```java
logger.info("Operation completed");
assertEquals(1, sink.events().size()); // May run too early.
```

is unstable because the collector is checked before the worker has processed the event. Adding `Thread.sleep(200)` only reduces the probability of failure; **it provides no guarantee**.

### Bounded waiting approaches

- Use a `BlockingQueue<ILoggingEvent>` in the test appender; the test calls `poll(timeout)` to wait for **the event to reach the sink**.
- Or use a `CountDownLatch` counted down in `append(...)`, waiting with a finite timeout.
- Or use the system's flush/drain/await API if supported by the contract.
- For network collectors, only assert "sink received" when testing delivery, rather than inferring it from an empty producer queue.

Illustrative capture code for Logback:

```java
// Snippet; requires importing AppenderBase, ILoggingEvent,
// BlockingQueue, LinkedBlockingQueue, and TimeUnit.
final class QueueAppender extends AppenderBase<ILoggingEvent> {
    final BlockingQueue<ILoggingEvent> received =
            new LinkedBlockingQueue<>();

    @Override
    protected void append(ILoggingEvent event) {
        event.prepareForDeferredProcessing();
        received.offer(event);
    }
}

// After attaching the appender to the right pipeline and starting it:
ILoggingEvent event = appender.received.poll(
        2, TimeUnit.SECONDS);
assertNotNull(event);
assertEquals("OPERATION_FINISHED", event.getMessage());
```

This snippet is **not standalone** (`appender`, `assertNotNull`/`assertEquals`, and appender attachment are not fully declared). Tests should choose a timeout appropriate for the environment and finally `stop()` the appender/async worker in `finally`.

### Be careful with "no event" assertions

`queue.poll(100ms) == null` **does not by itself prove** an event was filtered; the worker might simply be slow. If the backend has a single FIFO queue and a sequential consumer, you can send an accepted **sentinel event** *after* the event under test, wait for the sentinel to arrive at the sink, and then inspect the set of events processed before it. This only holds when the queue/sink contract and filters do not break the FIFO assumption; do not apply it blindly to multiple workers or partitions.

If the backend has a discard policy or queue overflow, missing events may be caused by overload rather than filtering. To test filters, create a non-discarding environment or control the queue policy separately.

## 15. Testing levels, filters, and multiple appenders

An event can be dropped at multiple points:

```text
logger.info(...)
  |
  v
Logger level / TurboFilter
  |
  v
Logging event
  |
  +--> ConsoleAppender -- filter A --> console
  |
  +--> FileAppender ---- filter B --> file
```

Suppose `filter A` blocks periodic health logs while `filter B` does not. You cannot assert "the log does not exist in the system" just because the console does not show it. The test must specify **which target sink is being tested**.

In Logback, appender filters return `DENY`, `NEUTRAL`, or `ACCEPT`. If a logger already blocks an event by level, `ACCEPT` on an appender filter will not make the event reappear. `TurboFilter` operates earlier and has semantics that should be tested separately.

Strategies:

- **Logger-level test:** set the intended level, emit multiple levels, and assert event counts at an appender with no other filters.
- **Appender filter test:** set the logger to a permissive level, attach the filter to a specific appender, and test which events are accepted/dropped at that appender.
- **Multiple appender test:** capture each sink and compare separate event sets; do not mix logs from root and child loggers.
- **Configuration test:** if filters are defined in `logback-spring.xml` by profile, use a Spring Boot integration test with the appropriate profile. Do not just call `filter.decide` directly and assume production configuration is right.
- **TurboFilter test:** isolate the `LoggerContext` and test semantics at the early layer. Do not reset the test suite's shared root context without control.

**Keep tests properly scoped:** changing the console pattern should not break a logger-level test. Conversely, changing a sink's filter should fail that sink's test if it alters the contract.

## 16. Comparing events across multiple threads

Another brittle test compares global event ordering:

```java
assertEquals(List.of("worker-A-start", "worker-B-start"),
             receivedMessages);
```

If two workers run concurrently, the scheduler may let B log before A without any bug. With concurrency:

- Assign a unique `operationId`/`taskId` to each workflow.
- Wait for all tasks to finish and for the sink to process all events per contract.
- Compare **sets/multisets** by ID or count by actor/task, not an unguaranteed interleaved order.
- If ordering is required within **one** task, group by task ID and verify the `STARTED -> FINISHED` relationship.
- Use a thread-safe collector and take a snapshot after synchronization completes.
- Do not assume timestamps across multiple hosts give an exact total order when clocks drift.

An important caveat: a **set** hides duplicates. If the requirement is "each operation has exactly one terminal event", check a **multiset/count** rather than only unique IDs. You can use an `operationId -> count` map and assert the exact event count for each operation.

## 17. When are golden/snapshot tests truly useful?

Snapshots are not always bad. They are useful when log consumers have a specific presentation contract:

- An exporter emitting text logs for a legacy system that only reads a fixed pattern.
- A JSON encoder with a versioned schema where downstream parsers are sensitive to field types.
- An internal-standard audit line requiring exact field names, escaping, or delimiters.
- An SDK feature where the log output itself is the user-facing product.

Still, design golden tests smartly:

1. Supply a **fixed event fixture** (timestamp, level, logger, MDC, exception).
2. Snapshot **only the formatter/encoder output**, not every business unit test.
3. For JSON, parse the object and compare schema/values instead of raw strings if byte-level checks are unnecessary.
4. If byte-level output is genuinely required, document why: delimiters, field order, newlines, encoding, or signatures.
5. Update golden files only after reviewing the semantics and consumer contract; do not click "update snapshots" just to turn CI green without understanding the diff.
6. Keep real secrets and personal data out of fixtures.

Have a few focused golden tests rather than hundreds of assertions repeating the same console pattern.

## 18. Common failing test patterns and fixes

| Test pattern | Problem | Fix |
| --- | --- | --- |
| `assertEquals(fullConsoleLine, actual)` | Timestamp/thread/pattern change easily | Capture semantic events |
| Compare entire stack trace | Refactoring/JDK changes frames | Assert Throwable type/cause |
| `assertTrue(text.contains("ERROR"))` | Message contains ERROR but level is not ERROR | Assert enum level |
| `assertTrue(text.contains("id=42"))` | May match another ID or field | Assert explicit field/value |
| Mock every exact logger call | Locks template/overload, does not check sink | Test adapter contract and capture real events |
| Compare order across independent threads | Scheduler does not guarantee order | Compare counts/multisets; order only within guaranteed scope |
| `Thread.sleep` for async | Flaky when CI is slow | Latch/queue/ack with timeout |
| Wait 100ms then assert no event | Event may just arrive late | Barrier/sentinel and FIFO contract |
| Compare raw JSON strings | Key order/whitespace changes | Parse JSON and compare schema |
| Test `now()` timestamp with fixed string | Clock and timezone change | Inject `Clock` or parse/range check |
| Read MDC after thread cleared it | Event may not have snapshotted MDC | Prepare event before deferring, test on right thread |
| Attach appender to root without cleanup | Logs from other tests bleed in | Dedicated logger, `additive=false`, detach/stop |
| Test missing event only with mock logger | Does not test filters, queues, or sinks | Observe after the layer being protected |
| Assert at least one event | Misses duplicates | Assert exact event count when required by contract |
| Test only the success path | Misses level/secret/filter on errors | Test failure, negative, and security cases |

## 19. Practical testing matrix for low-format-coupling logging

Suppose an application must log order cancellation outcomes. A test matrix might look like this:

| Scenario | Business behavior | Event contract | Not required |
| --- | --- | --- | --- |
| Cancel succeeded | Order becomes `CANCELLED` | 1 event `ORDER_CANCEL/SUCCEEDED`, right `requestId` | Timestamp format `yyyy-MM-dd HH:mm:ss` |
| Order already shipped | Unchanged | `REJECTED`, `reasonCode=ALREADY_SHIPPED`, `INFO` per policy | 100% identical Vietnamese/English wording |
| Storage failure | Not committed | `FAILED`, `ERROR`, appropriate Throwable/cause | Individual stack frames and line numbers |
| Logger DEBUG disabled | No DEBUG events at sink | Count matches logger level | Full console line |
| Health-check filter | Normal events remain, health dropped at right appender | Set of received IDs | Log ordering in another appender |
| Async delivery | Terminal event reaches sink within timeout | Right ID, outcome, count | Event appearing immediately after call |
| Concurrent requests | Each operation has exact terminal event | Multiset of IDs, no loss/duplicates | Total order across threads |
| JSON exporter | Valid fields/schema and escaping | Parse JSON, types/required keys | Key order, indentation |
| Input contains CR/LF | Does not forge extra records | Escaping/validation at sink | Whether JSON writes `\\n` or equivalent escape |
| Dummy token in request | Not exposed at protected sinks | No dummy token in final output | Exact message phrasing |

This matrix separates **business correctness**, **event semantics**, **encoder correctness**, and **delivery**. Each layer has its own oracle, so when a test fails, maintainers know where to investigate.

### Acceptance criteria for a logging test

A good test should:

- Fail when **critical logging behavior** breaks (lost exception, wrong severity, missing `reasonCode`, leaked secret, duplicate event).
- Still pass when only **output decoration** changes without affecting the contract (whitespace, runtime timestamp, thread name).
- Have **isolated** fixtures/infrastructure and reliable cleanup, avoiding flakiness across the full test suite or parallel CI.
- Produce failure messages that pinpoint the wrong **field/event**, rather than dumping thousands of log lines.
- Maintain a clear boundary between unit tests for event semantics and integration tests for encoders/collectors.

## 20. Security: avoid using format tests to mask data leaks

One genuine reason to inspect final output is **secret redaction and log injection**. However, that is not a reason to lock down the entire log line in every test.

- Use a **unique dummy secret** in fixtures, such as `FAKE_TOKEN_TEST_73`, never real passwords or credentials.
- If the requirement is "tokens must not enter the collector", testing the event at the start of the pipeline is not enough; check **the final sink that could receive the token** and every relevant appender.
- If input contains `\r`/`\n`, test that the encoder or schema prevents forged log entries. For JSON encoders, round-trip parse and verify the message remains a single field.
- When handling emails, IDs, addresses, or sensitive payloads, use an allowlist of permitted fields instead of logging the entire DTO and writing tests to redact individual strings.
- Avoid printing raw logs containing dummy secrets into broadly visible CI reports if unnecessary, though dummy secrets should still be clearly recognizable.
- A single `logger.info` call can fan out to multiple sinks. Just because one sink redacts does not prove every other sink is safe.

### Distinguishing two problems

**Brittle format testing** slows down refactoring because valid layout changes cause failures. **Security output testing** protects a real contract and may need exactness at the encoder/sink layer. Do not drop security tests on the grounds of "tests are too format-dependent"; simply place assertions in the right spot.

## 21. Pre-merge checklist for a logging change

- [ ] Clearly identify whether the test protects event semantics, filter, encoder, transport, or audit.
- [ ] Do not compare full console lines if timestamp/thread/pattern are not part of the contract.
- [ ] Compare levels using enums/APIs, not by inferring from words in the message.
- [ ] Compare action/outcome/reasonCode/ID via appropriate fields or template/arguments.
- [ ] When exceptions matter, assert type/cause rather than locking every stack frame.
- [ ] When a JSON schema matters, parse JSON and assert types/fields rather than locking key order.
- [ ] With async logging, use latch/queue/ack/timeout instead of fixed sleeps.
- [ ] With concurrency, compare counts/multisets and only enforce ordering where guaranteed.
- [ ] Test that logs are emitted the exact number of times, not just "at least one log".
- [ ] Isolate test loggers/appenders, detach/stop them, and restore MDC.
- [ ] Include negative tests for levels/filters and sensitive data.
- [ ] Test CR/LF input, Unicode, and exceptions at the encoder layer when format requirements exist.
- [ ] Use dummy secrets in tests; never copy production data into fixtures.
- [ ] Update snapshots/golden files only after reviewing the contract with consumers.
- [ ] When switching backends, review capture APIs (JUL/Logback/Log4j2) and do not cast to the wrong event type.

**Remember:** resilient logging tests do not mean "fewer assertions." Assert **strongly on meaningful behavior**—which event, which level, which fields, which exception, which sink—and stay **intentionally loose on non-contract presentation details**. Only lock down byte-level format when the format itself is the product/API being protected; everything else should be tested through event structure and clear delivery boundaries.
