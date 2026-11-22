# Testing Log Levels in Java

## Lesson Objectives

**Testing log levels** means verifying whether logging events at **TRACE, DEBUG, INFO, WARN, ERROR** (or the corresponding levels in **java.util.logging**) are actually accepted and routed to the intended destination according to the expected configuration.

In the **Java Core Logging** module, this is a key part of **Testing logging**: not only proving that a logger call is executed, but also proving that **lower levels are blocked**, **important levels are retained**, **child loggers inherit properly**, and **handlers/appenders/filters do not distort the outcome**.

After this lesson, you will be able to:

1. Understand the difference between an event's level, a directly configured level, the **effective level**, and a handler/appender threshold.
2. Write **positive** and **negative** tests against the same logger; avoid false positives.
3. Practice seven **pure JDK Java 17** test cases with stable assertions and stdout.
4. Test **Logback with JUnit 5 + ListAppender**, as well as Log4j2 and Spring Boot configurations.
5. Control the interaction between the root logger, package loggers, additivity, filters, and dev/test/prod environments.
6. Handle tricky cases: async logging, different output streams, parallel test execution, wrong backends, and config reloads.
7. Build a test suite that ensures useful WARN/ERROR events are not lost while DEBUG/TRACE are not enabled excessively by accident.

## 1. Log Levels and the Outcome of a Logger Call

Consider an application using SLF4J:

~~~java
// Illustration inside a class that already has an SLF4J logger and an orderId variable.
log.trace("Validate step 1 for orderId={}", orderId);
log.debug("Validation details, orderId={}", orderId);
log.info("Order accepted, orderId={}", orderId);
log.warn("Inventory latency is high, orderId={}", orderId);
log.error("Order failed, orderId={}", orderId, exception);
~~~

If **effective logger level = INFO**, TRACE/DEBUG calls are typically dropped at the logger; INFO/WARN/ERROR can proceed to the appender.

**Can proceed** does not mean it is guaranteed to be stored in a file or centralized backend. Another appender filter, a full queue, a disk error, or a collector issue can prevent the record from appearing where you query it.

You need to distinguish:

| Concept | Question |
| --- | --- |
| **Event level** | At what level does the call create an event? |
| **Configured logger level** | What level is directly set on that logger? |
| **Effective logger level** | After inheritance, what level does the logger actually use? |
| **Handler/appender threshold** | Does the target sink further drop lower levels? |
| **Filter** | Are there rules based on message, marker, MDC, or metadata? |
| **Routing** | Which console, file, or collector receives an eligible event? |
| **Delivery** | Did the sink/queue process it successfully, or only buffer the event in memory? |

A logger-level unit test can verify the first three columns. To confirm that a record is actually emitted, attach a **test handler/appender**. To confirm a collector or storage, you need an integration test on the corresponding path.

## 2. Different Systems Have Different Level Sets

With Logback Classic and standard SLF4J:

~~~text
TRACE < DEBUG < INFO < WARN < ERROR
~~~

With Log4j2, in addition to those levels there are typically **FATAL, ALL, OFF** and the ability to define custom levels. Do not blindly apply Logback's level table to every backend.

**java.util.logging (JUL)** in the JDK uses different levels:

| JUL Level | intValue | Common Usage |
| --- | ---: | --- |
| **SEVERE** | 1000 | Severe error |
| **WARNING** | 900 | Warning |
| **INFO** | 800 | Operational information |
| **CONFIG** | 700 | Configuration information |
| **FINE** | 500 | Debugging details |
| **FINER** | 400 | More detailed |
| **FINEST** | 300 | Very deep detail |
| **OFF** | Integer.MAX_VALUE | Blocks events at this threshold |
| **ALL** | Integer.MIN_VALUE | Does not filter out any level at this threshold |

**FINE** is close to DEBUG in purpose and **SEVERE** is close to ERROR, but there is no universal rule requiring every bridge/provider to map them identically. An application bridging JUL through SLF4J or Log4j2 must be tested against the **real backend**.

### 2.1. Basic Matrix for Logback

Without special filters, a logger with a standard effective level behaves as follows:

| Logger effective level | TRACE | DEBUG | INFO | WARN | ERROR |
| --- | --- | --- | --- | --- | --- |
| TRACE | Yes | Yes | Yes | Yes | Yes |
| DEBUG | No | Yes | Yes | Yes | Yes |
| INFO | No | No | Yes | Yes | Yes |
| WARN | No | No | No | Yes | Yes |
| ERROR | No | No | No | No | Yes |
| OFF | No | No | No | No | No |

This is the **logger threshold matrix**; it does not include appender filters, markers, sampling, async queues, or custom levels.

A complete test must check **both directions**: events expected to appear **actually appear**, and events expected to be blocked **actually do not appear**. Checking only the negative direction easily causes a **false positive** when the entire logging system is disabled.

## 3. Testing Logger Level or Final Output?

There are at least three distinct testing goals.

**Goal A — configuration:** verify that package **com.example.orders** is at DEBUG and root is at INFO. This test can read the effective level. It is fast, but it does not prove output.

**Goal B — event emission and filtering:** log DEBUG, INFO, WARN; use an in-memory appender to check which events passed through. This is suitable for most unit tests.

**Goal C — full pipeline:** verify that console/file/collector actually writes records and does not create duplicates. This requires an integration test with the appender/encoder/collector in use.

~~~text
Code calls log.debug()
       │
       ▼
Logger effective level
       │
       ▼
Logger filter / backend rule
       │
       ▼
Event is created
       │
       ▼
Handler / Appender threshold + filter
       │
       ▼
Async queue (if any)
       │
       ▼
Console / File / Collector
       │
       ▼
Storage / Query
~~~

Each stage can drop an event. Therefore, a test that **does not see DEBUG on stdout** cannot by itself conclude the cause is `logger.INFO`: the handler might write to stderr, there may be no provider, the appender may not be attached, or the queue may not have drained yet.

## 4. Inheritance and Logger Hierarchy

Suppose the configuration is as follows:

~~~text
root                              INFO
└── com.example
    ├── com.example.orders        DEBUG
    │   ├── OrderService          inherits DEBUG
    │   └── workflow.Checkout     inherits DEBUG
    └── com.example.payments      inherits INFO
        └── PaymentService        inherits INFO
~~~

Expectations:

- **com.example.orders.OrderService** allows DEBUG and above.
- **com.example.orders.workflow.Checkout** inherits the DEBUG threshold.
- **com.example.payments.PaymentService** does not emit DEBUG, but still emits INFO/WARN/ERROR.
- A class with a direct level override uses its own level, not necessarily the package level.
- A logger named **business** does not automatically belong to the `com.example.orders` hierarchy just because it is declared in a class inside the `orders` package.

### 4.1. JUL getLevel() Returns null

In JUL, a child logger can have:

~~~java
// Illustration, not a complete main method.
java.util.logging.Logger child =
        java.util.logging.Logger.getLogger(
                "com.example.orders.OrderService");
System.out.println(child.getLevel());
~~~

If the result is **null**, this normally means the logger **inherits its level from its parent**, **not** that the logger is disabled. Tests must not treat `null` as `OFF`.

Logback is similar in that the configured level can be `null`; to inspect the final level, use Logback's **getEffectiveLevel()** API. Log4j2 uses a different `LoggerConfig` architecture; avoid guessing the effective level from a config object that does not actually apply to the logger under test.

### 4.2. Parent Loggers Do Not Necessarily Re-filter Records Accepted by a Child Logger

A common pitfall:

~~~text
JUL parent logger level = WARNING
JUL child logger level  = FINE
JUL parent handler      = ALL
child.fine("details")
~~~

A **FINE** record from the child can reach a handler attached to the parent, because forwarding a record to parent handlers **does not mean re-checking the parent logger's level**. The handler has its own level, so with `ALL` it allows the record.

In Logback, once a child logger at DEBUG accepts an event, the event can reach an appender attached to the root logger at INFO via additivity. If you want an appender to receive only WARN/ERROR, place a threshold/filter on the appender itself or at the appropriate filtering point.

**Lesson:** testing the logger level and testing the handler/appender level are two different tests.

## 5. Test Matrix to Prepare

| Case | Setup | Expected Result |
| --- | --- | --- |
| Logger INFO | Logger INFO, handler ALL | FINE is blocked; INFO/WARNING/SEVERE are recorded. |
| Handler WARNING | Logger FINE, handler WARNING | FINE/INFO are blocked at the handler; WARNING/SEVERE are recorded. |
| Inherit | Parent WARNING, child null | Child emits only WARNING/SEVERE. |
| Override | Parent WARNING, child FINE, handler ALL | Child emits FINE/INFO/WARNING/SEVERE. |
| Handler filter | Logger INFO, handler ALL, filter drops message INFO | INFO is dropped by the filter; WARNING/SEVERE are kept. |
| OFF | Parent OFF, child inherit | No events are recorded. |
| ALL | Parent ALL, handler ALL | All four events from FINE to SEVERE are recorded. |
| Package scope | Only orders DEBUG | Payments does not emit DEBUG. |
| Async | AsyncAppender/AsyncLogger enabled | Test waits for completion condition instead of asserting too early. |
| Root/additivity | Child has its own appender | Exact expected record count in each sink. |
| Environment | Production profile | Effective level matches policy after all overrides. |

For every negative test (event does not appear), always include at least **one positive control** showing that the same handler/appender is active. Otherwise, the test can accidentally pass when no appender is attached at all.

## 6. Pure JDK Java 17: A Standalone Seven-Test Suite

This is a complete program requiring only **JDK 17**. It needs no JUnit, Maven, Spring Boot, Logback, or external dependencies.

The program creates a **parent logger named per test**, a **child logger simulating a class in the package**, and a **CaptureHandler** that stores `LogRecord`s passing through the handler in a list. Each case sets the logger level, handler level, and filter, then compares against the expected result using **AssertionError**. It does not use Java's `assert` statement because `assert` may be disabled by default in the JVM without `-ea`.

### 6.1. Full Source Code

Save as **LogLevelTestDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.logging.Filter;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class LogLevelTestDemo {

    private static int sequence = 0;

    static final class CaptureHandler extends Handler {
        private final List<String> events = new ArrayList<>();

        CaptureHandler(Level level, Filter filter) {
            setLevel(level);
            setFilter(filter);
        }

        @Override
        public void publish(LogRecord record) {
            if (isLoggable(record)) {
                events.add(record.getLevel().getName()
                        + ":" + record.getMessage());
            }
        }

        @Override
        public void flush() {
            // No I/O in this demo.
        }

        @Override
        public void close() {
            // Uses an in-memory list only.
        }

        List<String> captured() {
            return List.copyOf(events);
        }
    }

    static void check(
            String label,
            Level parentLevel,
            Level handlerLevel,
            Level childLevel,
            Filter filter,
            List<String> expected) {

        String name = "demo.level.case" + (++sequence);
        Logger parent = Logger.getLogger(name);
        Logger child = Logger.getLogger(name + ".OrderService");

        Level previousParent = parent.getLevel();
        Level previousChild = child.getLevel();
        boolean previousParentUse =
                parent.getUseParentHandlers();
        boolean previousChildUse =
                child.getUseParentHandlers();

        CaptureHandler capture = new CaptureHandler(
                handlerLevel, filter);

        try {
            parent.setUseParentHandlers(false);
            child.setUseParentHandlers(true);
            parent.setLevel(parentLevel);
            child.setLevel(childLevel);  // null = inherit
            parent.addHandler(capture);

            child.fine("fine");
            child.info("info");
            child.warning("warning");
            child.severe("severe");

            List<String> actual = capture.captured();
            if (!expected.equals(actual)) {
                throw new AssertionError(
                        label + " expected=" + expected
                        + " actual=" + actual);
            }
            System.out.println("PASS " + label);
        } finally {
            parent.removeHandler(capture);
            capture.close();

            parent.setLevel(previousParent);
            child.setLevel(previousChild);
            parent.setUseParentHandlers(previousParentUse);
            child.setUseParentHandlers(previousChildUse);
        }
    }

    public static void main(String[] args) {
        List<String> all = List.of(
                "FINE:fine",
                "INFO:info",
                "WARNING:warning",
                "SEVERE:severe");

        check("logger INFO",
                Level.INFO, Level.ALL, null, null,
                List.of("INFO:info",
                        "WARNING:warning",
                        "SEVERE:severe"));

        check("handler WARNING",
                Level.FINE, Level.WARNING, null, null,
                List.of("WARNING:warning", "SEVERE:severe"));

        check("inherit WARNING",
                Level.WARNING, Level.ALL, null, null,
                List.of("WARNING:warning", "SEVERE:severe"));

        check("child overrides FINE",
                Level.WARNING, Level.ALL, Level.FINE, null,
                all);

        check("handler filter INFO",
                Level.INFO, Level.ALL, null,
                record -> !"info".equals(record.getMessage()),
                List.of("WARNING:warning", "SEVERE:severe"));

        check("logger OFF",
                Level.OFF, Level.ALL, null, null,
                List.of());

        check("logger ALL",
                Level.ALL, Level.ALL, null, null,
                all);

        System.out.println("ALL 7 TESTS PASSED");
    }
}
~~~

### 6.2. Compile and Run Commands

~~~bash
javac LogLevelTestDemo.java
java LogLevelTestDemo
~~~

**Expected stdout when running normally on JDK 17:**

~~~text
PASS logger INFO
PASS handler WARNING
PASS inherit WARNING
PASS child overrides FINE
PASS handler filter INFO
PASS logger OFF
PASS logger ALL
ALL 7 TESTS PASSED
~~~

There are no timestamps, ports, thread IDs, or random paths. If a test fails, the program throws an **AssertionError** with expected/actual instead of printing `PASS`. The exit code is then non-zero.

### 6.3. Analysis of the Seven Cases

**logger INFO case:** `FINE` is blocked at the logger before reaching the handler. `INFO`, `WARNING`, and `SEVERE` pass the threshold and are retained by the `ALL` handler.

**handler WARNING case:** The `FINE` logger accepts all four events, but the handler only records `WARNING` and `SEVERE`. This illustrates why **Logger.isLoggable(Level.FINE)** is not enough to claim that logs reached the sink.

**inherit WARNING case:** The child has a `null` level and inherits from the `WARNING` parent, so `INFO`/`FINE` do not proceed.

**child overrides FINE case:** Parent is `WARNING`, child is `FINE`. The parent's `ALL` handler still receives `FINE` from the child when parent handlers are enabled, because the parent logger does not re-filter the event by its `WARNING` level during propagation.

**handler filter INFO case:** The `INFO` logger accepts `INFO`, `WARNING`, and `SEVERE`. The handler filter actively drops the **info** message, so only `WARNING` and `SEVERE` are captured. This test distinguishes **level filtering** from **record-attribute filtering**.

**OFF case:** Parent is `OFF`, child does not override, and no events appear, not even `SEVERE`.

**ALL case:** Parent is `ALL` and handler is `ALL`, so all four events are accepted.

### 6.4. Why Are These Tests Independent?

- Each case creates a unique logger name with a sequence number; none touches the application-wide root logger.
- `parent` and `child` are kept in local variables, preventing the logger hierarchy relationship from being lost during the case.
- `parent` has **setUseParentHandlers(false)** so records are not also printed through the root handler.
- The handler stores only the level and message; it does not format timestamps or depend on stdout/stderr from a logging backend.
- Calls are synchronous on a single thread; there is no queue or concurrent writer.
- **finally** detaches the handler and restores `level` and `useParentHandlers` so test configuration does not leak.
- The test does not use Java's **assert** keyword; assertions are always evaluated when running the program.

### 6.5. Limitations of the Example

The demo proves the thresholds of **JUL loggers and JUL handlers**. It does not prove that:

- Logback or Log4j2 is actually being used by the application.
- Production `ConsoleAppender`/`FileAppender` emits messages.
- A JSON encoder matches its schema or sensitive data is redacted.
- An async queue has drained, a file has flushed, or a collector has received events.
- Spring Boot active profiles and overrides are correct.
- Another package-named logger has the expected policy.

Each limitation must be tested at the appropriate level rather than trying to use a single unit test to replace all integration tests.

## 7. JUnit 5 and Structured Testing

In a real project, use a test runner such as **JUnit Jupiter** with Maven/Gradle and CI.

Organizational pattern:

~~~text
Arrange: create capture, set level and filter
Act:     invoke code that triggers events
Assert:  level, logger, message/fields, count
Finally: detach/close capture, restore config
~~~

If using JUL, you can turn the `check` method in the demo into a JUnit 5 test class and replace the manual `AssertionError` with **assertEquals(expected, actual)**.

A good unit test typically **does not write real files** if the goal is only to test levels. Separating file/collector tests keeps runs fast and reduces flakiness.

### 7.1. Testing Logback with ListAppender

For projects with **SLF4J + Logback Classic + JUnit 5**, Logback provides **ListAppender**, an in-memory appender that stores **ILoggingEvent** instances.

Example test class placed under the test source root as **LogbackLevelTest.java**:

~~~java
import ch.qos.logback.classic.Level;
import ch.qos.logback.classic.Logger;
import ch.qos.logback.classic.spi.ILoggingEvent;
import ch.qos.logback.core.read.ListAppender;
import org.junit.jupiter.api.Test;
import org.slf4j.LoggerFactory;

import static org.junit.jupiter.api.Assertions.assertEquals;

public class LogbackLevelTest {

    @Test
    void infoLoggerRejectsDebug() {
        Logger logger = (Logger) LoggerFactory.getLogger(
                "tests.logging.orders.LevelProbe");

        Level oldLevel = logger.getLevel();
        ListAppender<ILoggingEvent> capture =
                new ListAppender<>();
        capture.start();
        logger.addAppender(capture);

        try {
            logger.setLevel(Level.INFO);

            logger.debug("debug-should-not-appear");
            logger.info("order-accepted");
            logger.warn("inventory-slow");

            assertEquals(2, capture.list.size());
            assertEquals(Level.INFO,
                    capture.list.get(0).getLevel());
            assertEquals("order-accepted",
                    capture.list.get(0).getFormattedMessage());
            assertEquals(Level.WARN,
                    capture.list.get(1).getLevel());
        } finally {
            logger.detachAppender(capture);
            capture.stop();
            logger.setLevel(oldLevel);
        }
    }
}
~~~

This is a **test class runnable in a project with configured dependencies**, not a standalone program on the plain JDK classpath. The expected outcome is a **PASSing JUnit test** when the Logback backend is active and no global turbo filter or custom filter alters behavior.

Strengths of `ListAppender`:

- Captures **ILoggingEvent** objects rather than just reading console text.
- Inspects **getLevel**, **getFormattedMessage**, and **getLoggerName**.
- When an exception is present, checks **getThrowableProxy()** instead of guessing from message strings alone.
- Needs no timestamps or file I/O.
- Easily verifies actual messages formatted from SLF4J placeholders.

**Limitation:** `ListAppender` attached directly to a logger does not guarantee an event passes production appenders/filters; tests for **console thresholds, file encoding, rotation, and collectors** must run at their respective layers.

### 7.2. Cleanup Matters More Than Passing Once

In Logback, **setLevel(null)** can return a logger to inheriting its parent's level. Always save and restore **oldLevel**, even when it is `null`. Do not leave a newly enabled `INFO`/`DEBUG` level affecting other tests.

If a test must use the same logger as production code, ensure no parallel test is modifying that logger's level or appenders. You can create a dedicated logger name in unit tests or isolate the context for integration tests.

## 8. Logger Inheritance and Logback Test Configuration

Example **logback-test.xml** for a Logback project (this is XML configuration, not Java source):

~~~xml
<configuration>
    <appender name="CONSOLE"
              class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%level %logger - %msg%n</pattern>
        </encoder>
    </appender>

    <logger name="com.example.orders" level="DEBUG"/>

    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
    </root>
</configuration>
~~~

Tests should verify:

- Child logger **com.example.orders.OrderService** accepts DEBUG.
- Another logger **com.example.payments.PaymentService** does not accept DEBUG because root is INFO.
- INFO/WARN/ERROR appear on `CONSOLE` if no other filter is present.
- A similarly named package **com.example.order** does not automatically receive DEBUG.
- A child logger with an override behaves according to its override, not just the parent package level.

### 8.1. Adding an Appender Threshold

If `CONSOLE` is given a **ThresholdFilter** at `WARN`:

~~~xml
<filter class="ch.qos.logback.classic.filter.ThresholdFilter">
    <level>WARN</level>
</filter>
~~~

This XML snippet **must be placed inside a valid appender**; it cannot be used standalone as a config file.

In that case, the `orders` logger still has **effective level DEBUG**, but `CONSOLE` will not print DEBUG or INFO. A test reading the effective level can PASS, while a console output test will see only WARN/ERROR. **This is not a contradiction**—it is two separate filtering layers.

### 8.2. Watch Out for Additivity

If the `orders` logger has its own appender and **additivity=true**, events can continue up to the root appender. Tests should verify that an event reaches each sink the intended number of times. Attaching the same console appender at multiple levels can produce duplicate lines.

With **additivity=false**, the child logger must have an appropriate appender; otherwise, events may reach no destination even when the level allows them.

### 8.3. logback-test.xml Differs from Production Config

Logback has a configuration lookup order for test vs. production runs. Having **logback-test.xml** on the test classpath can make tests run with a different policy than the deployed application's **logback.xml** or **logback-spring.xml**.

Unit tests verifying logic with `logback-test.xml` do not prove the production runtime is correct. To verify production configuration, run integration/smoke tests with the **corresponding artifact, profile, and dependencies**.

## 9. Log4j2: Testing LoggerConfig and AppenderRef

In Log4j2, routing and filtering can live on **LoggerConfig**, a `LoggerConfig` filter, **AppenderRef**, or the appender itself. An illustrative test configuration is **log4j2-test.xml**:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<Configuration status="WARN">
    <Appenders>
        <Console name="CONSOLE" target="SYSTEM_OUT">
            <PatternLayout pattern="%p %c - %m%n"/>
        </Console>
    </Appenders>

    <Loggers>
        <Logger name="com.example.orders" level="debug"
                additivity="false">
            <AppenderRef ref="CONSOLE"/>
        </Logger>

        <Root level="info">
            <AppenderRef ref="CONSOLE"/>
        </Root>
    </Loggers>
</Configuration>
~~~

Expectations:

- DEBUG in **com.example.orders.OrderService** can reach `CONSOLE`.
- DEBUG in **com.example.payments.PaymentService** is blocked by root INFO.
- The `orders` logger does not forward to root because `additivity=false`, yet it still has a destination because it has its own `CONSOLE` ref.
- INFO/WARN/ERROR are processed according to the policy and any filters.

Do not take Logback XML and assume Log4j2 interprets every detail the same way. When testing programmatic level changes, use the context/config update API matching your Log4j2 version.

If tests use Log4j2 async loggers or async appenders, an **accepted event** may not be written immediately. Wait for completion with an appropriate timeout or use a suitable test appender rather than arbitrary sleeps.

## 10. Spring Boot: Testing Levels by Profile and Property Sources

Spring Boot commonly allows configuring:

~~~properties
logging.level.root=INFO
logging.level.com.example.orders=DEBUG
logging.level.com.example.payments=WARN
~~~

This file is a **policy example**, not a mandatory default. It can vary across profiles:

~~~properties
# application-dev.properties
logging.level.com.example.orders=DEBUG
~~~

~~~properties
# application-prod.properties
logging.level.com.example.orders=INFO
~~~

When running tests, a loaded property **is not guaranteed to be the final value** if higher-priority sources exist, such as command-line overrides, environment variables, or runtime dynamic changes.

### 10.1. Profile Test Scenarios

| Context | What to Verify |
| --- | --- |
| dev | Debug-enabled packages allow DEBUG; other packages keep standard levels. |
| test | No extra DEBUG noise from libraries or application packages outside what is being asserted. |
| staging | Levels and sinks are close to production policy, with any differences approved. |
| prod | Root INFO; no package has DEBUG enabled outside the allowlist. |
| Missing profile | Safe base config and startup behavior follow conventions. |
| Conflicting profiles | Effective config is deterministic; invalid combinations are caught if policy requires it. |
| Runtime override | Actual level changes and is restored properly, with auditing if needed. |

A test using **@SpringBootTest(properties = "logging.level.com.example.orders=DEBUG")** can inspect the Spring environment, but it should not only assert:

~~~java
// Illustration in a test with Spring Environment.
assertEquals("DEBUG",
        environment.getProperty(
                "logging.level.com.example.orders"));
~~~

That assertion checks the **resolved property value**, not that Logback/Log4j2/JUL actually emits DEBUG to an appender. The test must check the **effective level** in the backend and **event capture**.

### 10.2. Actuator Loggers

When an application includes Spring Boot Actuator and the **/actuator/loggers** endpoint is enabled/exposed, authorized callers can view and change levels at runtime.

When testing this:

1. Protect the endpoint; do not leave it publicly open.
2. Read the initial level.
3. Temporarily enable DEBUG on an approved package.
4. Confirm DEBUG appears through the target appender.
5. Restore the original level in `finally`/cleanup.
6. Verify other packages are unaffected.
7. Do not run other tests in parallel that mutate the same logging context.

**Do not use production to test runtime DEBUG elevation** if it could log sensitive information or spike volume. Use a controlled test environment.

## 11. Two-Sided Testing: Positive and Negative

**Positive assertion:** an event at an allowed level is captured, e.g., **INFO:order-created**.

**Negative assertion:** an event below the threshold does not appear, e.g., **DEBUG:validation-details**.

Both must use the same test harness or the same verified logging path. If you only have a negative assertion, the test can PASS simply because the appender was completely detached.

Example logger policy `INFO` with events:

~~~text
DEBUG validation.details
INFO  order.accepted
WARN  inventory.slow
ERROR dependency.unavailable
~~~

The test should verify:

- DEBUG is absent.
- INFO/WARN/ERROR are present.
- There are no unintended duplicates.
- Each event's level and logger name are correct.
- For ERROR with an exception, the throwable/cause is preserved if required by policy.

### 11.1. Avoiding Brittle Tests

Assert stable properties:

- Exact event level.
- Logger name and event name.
- Stable error code.
- Event occurrence count within a defined test case.
- Presence/absence of `Throwable`.
- Key structured fields and absence of sensitive data.

Avoid asserting:

- Absolute timestamps.
- Stack trace line numbers.
- Environment-dependent thread IDs.
- Full natural-language messages that change easily.
- Global ordering across different threads.
- Layout whitespace when formatting is not part of the contract.

Do not write tests that depend on logs from third-party libraries unless you own their format/level or have a stable contract.

## 12. Testing Exception Logging and Severity

**A Java exception type does not by itself determine the log level.** A normal business conflict might be logged at INFO/WARN; an unhandled system failure might be logged at ERROR; a transient retry attempt does not necessarily warrant ERROR.

Example:

~~~java
// Illustration; requires an SLF4J logger, orderId, and Throwable in the application.
logger.error("Order failed, id={}", orderId, exception);
~~~

If the application uses Logback, tests can verify:

- The event is at **ERROR**.
- The logger name is correct.
- **ILoggingEvent.getThrowableProxy()** is non-null when the cause is needed.
- There are not three stack traces for the same failure chain caused by service/controller/advice each logging and rethrowing.
- The event is recorded at the appropriate boundary.

With JUL, use **LogRecord.getThrown()** to verify that the `Throwable` was attached. Simply asserting text from **exception.getMessage()** does not prove the stack trace or cause was preserved.

An `ERROR` log record does not mean the HTTP response must be 500, and HTTP 404 does not force logging `ERROR`. **HTTP status, business outcome, and log severity are three separate dimensions**.

## 13. Testing Console, File, and Stderr Properly

In JUL, **ConsoleHandler typically writes to System.err**. Logback or Log4j2 `ConsoleAppender` can write to stdout or stderr depending on configuration.

If a test only redirects `System.out`, you may miss JUL logs. If an appender holds a reference to an old stream initialized before redirection, changing `System.out` afterward may still have no effect.

**Choosing the right tool:**

- Level tests: attach an **in-memory Handler/ListAppender**.
- Formatter tests: use a test appender with the target encoder/formatter.
- Console tests: identify stdout vs. stderr and when the appender is initialized.
- File tests: use a dedicated temporary directory and close/flush before reading the file.
- Collector tests: use an integration environment and a unique event ID.
- Async tests: wait for completion using a condition/latch with a timeout.

Do not mutate JVM-wide **System.out/System.err** in parallel tests without isolation; this can lose output from other tests.

## 14. Async Logging and Assertion Timing

In async logging, a logger call can be enqueued before the worker writes the event:

~~~text
Test thread                  Worker thread
-----------                  -------------
logger.info("created")
assert 1 event   ← may be too early
                             dequeue
                             appender writes
~~~

If the test asserts immediately, results can be **flaky**, especially under CI load.

Best practices:

1. Pick the capture point you actually want to measure.
2. Wait on a **CountDownLatch** or a condition signaled by the test appender, with a bounded timeout.
3. Do not use `Thread.sleep(1000)` as proof that the worker finished.
4. If testing shutdown, stop the context/appender via the proper lifecycle and verify the queue drains.
5. Test queue overflow/dropping separately; do not mix it into basic level tests.
6. Clean up workers, appenders, and the logging context after the test.

**An event not appearing within the timeout** can be caused by an undrained queue, a failing appender, or a drop—it does not by itself prove the logger level is too high. To conclude, inspect metrics or check each layer.

## 15. Test Isolation and Cleanup

Loggers and logging backends are typically **shared mutable state within a JVM/classloader**. One test enabling root DEBUG can make every other test emit extra logs. An unremoved `Handler`/`Listener` can cause events to appear twice.

State restoration table:

| State | Action Required |
| --- | --- |
| Logger level | Save old value and restore it, including `null`. |
| Root/package appender | Detach only appenders added by the test; do not remove framework-owned appenders. |
| Handler level/filter | Use a dedicated instance and close it properly. |
| Parent handlers/additivity | Restore pre-test values. |
| MDC / ThreadContext | Clear or restore keys added by the test. |
| Async queue/context | Stop/drain at the right time; avoid leaving threads alive. |
| System properties | Restore if modified by the test. |
| File output | Use an isolated temporary path and clean up. |
| Runtime level override | Revert level after the test; do not leave DEBUG enabled. |

With JUnit 5, you can use **@AfterEach**, though **finally** directly inside the test often guarantees cleanup even when an assertion throws. When a test must alter root/global `LogManager` state, separate execution or use the test framework's resource-lock mechanism; do not assume two tests mutating global logging can run safely in parallel.

## 16. Package Levels and Actual Logger Names

Suppose Spring Boot has:

~~~properties
logging.level.root=INFO
logging.level.com.example.orders=DEBUG
~~~

Tests:

- **com.example.orders.OrderService** has DEBUG.
- **com.example.orders.validation.Validator** has DEBUG.
- **com.example.payments.PaymentService** does not have DEBUG.
- **com.example.order.OrderService** (distinct from `orders`) does not automatically receive the rule.
- A class using `LoggerFactory.getLogger("business")` does not automatically belong to the `orders` branch.
- Loggers created by libraries may use arbitrary namespaces.

Do not infer the logger hierarchy from the Java file path if the code creates a logger with an arbitrary string name. When a test misses an event, **print or inspect the actual logger name** in the capture.

## 17. Security: Disabling DEBUG Is Not Enough to Protect Secrets

DEBUG/TRACE often carry rich diagnostic data, so testing levels in production helps reduce exposure risk. However, it must not be treated as the sole safeguard.

Information that should not be logged at any level:

- Passwords, API keys, bearer tokens, session cookies.
- Raw request/response bodies containing PII.
- Payment details or integration secrets.
- SQL parameters containing unnecessary user data.
- Unvetted exception messages from external APIs.
- User input containing CR/LF that can cause **log injection** in text layouts.

A privacy test should use **dummy data** such as `dummy-token-for-test`, enable DEBUG in an isolated environment, and verify the output **does not contain the raw dummy token** after encoding. Testing only at INFO when DEBUG is off can miss real leaks when an operator temporarily enables DEBUG.

Verification checklist:

- Sensitive data does not appear in INFO/WARN/ERROR.
- When DEBUG is intentionally enabled, redaction still works.
- MDC/correlation IDs are validated; inputs with CRLF do not forge fake events.
- Events log to the right environment/sink without sending test data to production.
- Tests disable/remove level overrides after completion.

## 18. Verifying Logging in Deployed Environments

A unit test on a developer machine does not prove the **production runtime configuration** is correct. Different configuration sources can override one another:

- `logback-test.xml` on the test classpath.
- `logback.xml`, `logback-spring.xml`, or `log4j2.xml` inside the artifact.
- `application-dev.yml`, `application-prod.yml`.
- Environment variables such as **LOGGING_LEVEL_ROOT**.
- JVM system properties or command-line overrides.
- Dynamic level changes from management endpoints.

Smoke tests should verify:

1. The application uses the **right backend/provider**.
2. The active environment/profile is selected properly.
3. Effective root/package levels after startup match policy.
4. DEBUG does not leak from other packages.
5. Important WARN/ERROR events are still written through the target appender.
6. The collector destination/namespace matches the environment.
7. If runtime levels change, reverting to the baseline policy can be verified.

**Do not enable DEBUG directly in production just to run a proof test**, as it can cause log flooding or data exposure. Use an authorized staging/test environment.

## 19. Common Testing Mistakes

**1. Only reading Logger.getLevel().** For inheriting loggers, `getLevel()` can be `null`; check the effective level or actual behavior.

**2. Missing a positive control.** A "DEBUG does not appear" test passes even if logging is completely disabled.

**3. Forgetting handler/appender thresholds.** A DEBUG logger does not guarantee the sink also accepts DEBUG.

**4. Forgetting filters.** Events can be dropped by marker/message/MDC even when the level allows them.

**5. Assuming root INFO blocks all child DEBUG.** In JUL/Logback, events already accepted by a child can reach parent handlers/appenders via propagation.

**6. Enabling root DEBUG to test one package.** Easily affects other tests and generates unnecessary log volume.

**7. Not restoring level/appender.** Makes subsequent tests flaky or produces duplicate logs.

**8. Asserting stdout when the backend writes to stderr.** Seeing no logs does not mean the logger filtered them properly.

**9. Using Thread.sleep for async.** Unreliable between local machines and CI.

**10. Testing a test config file and claiming production is right.** You need smoke tests against the real artifact/runtime.

**11. Exact matching on stack traces or timestamps.** Breaks easily across JDK versions, threads, and patterns.

**12. Not checking subpackages or similar names.** Easy to configure DEBUG too broadly.

**13. Counting ERROR logs as failed request counts.** One failure can be logged multiple times across layers or sampled/dropped.

**14. Not attaching a Throwable in ERROR tests.** Text checks pass while losing the cause needed for investigation.

**15. Running multiple tests in parallel that mutate the same logger.** Causes races and irreproducible results.

**16. Not verifying the SLF4J provider.** Having the API without a matching backend leaves tests seeing no logs.

**17. Treating ListAppender as proof of durability.** It only captures in memory.

**18. Assuming every 4xx must log WARN/ERROR.** HTTP status and log level are different concepts.

**19. Not testing runtime override behavior.** An environment variable can enable DEBUG unexpectedly even if the prod file says INFO.

**20. Using real secrets as test data.** Always use dummy strings and test against data exposure.

## 20. Logging Test Review Checklist

Before merging a log-level test, check:

- [ ] The test identifies the right backend and logger name.
- [ ] The test distinguishes whether configured level or effective level is being checked.
- [ ] There is a **positive assertion** for events that must be recorded.
- [ ] There is a **negative assertion** for levels that must be blocked.
- [ ] Handler/appender thresholds and filters are accounted for if they affect expectations.
- [ ] Routing via parent handlers/additivity is defined.
- [ ] If capturing messages, the test checks formatted vs. original message as intended.
- [ ] If testing exceptions, both level and `Throwable`/cause are checked.
- [ ] The test does not depend on unstable timestamps, stack lines, or thread ordering.
- [ ] Async tests have a completion condition and a timeout.
- [ ] Cleanup restores logger levels, filters, appenders/handlers, MDC, streams, and temp files.
- [ ] The test does not touch root/global loggers concurrently with other tests.
- [ ] Profiles and runtime overrides are tested if environment policy requires it.
- [ ] No secrets or PII are placed in test data.
- [ ] Separate integration/smoke tests exist when the target is a real file or collector.

## 21. Practice Exercises

1. Run **LogLevelTestDemo.java**, record all seven `PASS` lines, and explain each case.
2. Change logger `INFO` to `WARNING` while keeping the old `expected`. Which test fails, and what events remain in `actual`?
3. Change `Handler WARNING` to `ALL` in case 2. Why do `FINE` and `INFO` appear as well?
4. In the child override case, set the child level to `INFO`. Why does the `WARNING` parent not automatically block `INFO` events accepted by the child and forwarded to the `ALL` handler?
5. Add JUL `CONFIG` to the `INFO` logger; predict whether `CONFIG` appears and why.
6. Set `setUseParentHandlers(false)` on the child. Does the handler attached to the parent still receive events?
7. Change the filter in case 5 to exclude `WARNING`. What is the new `expected`?
8. Create a Logback JUnit test with `ListAppender`, switch the logger to `DEBUG`, and verify a `DEBUG` event appears. What must be restored in `finally`?
9. Add `ThresholdFilter` `WARN` to `CONSOLE` in `logback-test.xml`. Why can reading the effective level give a different answer than the output?
10. Create loggers `com.example.order` and `com.example.orders`; verify package rules are not confused.
11. Design an async test using `CountDownLatch` instead of `Thread.sleep` to confirm the appender receives an event.
12. Build a production profile smoke test: root `INFO`, one approved `DEBUG` package, other packages not emitting `DEBUG`; verify the right provider, log destination, and redaction.

## 22. Summary

**Testing log levels is testing event filtering and routing outcomes**, not just reading a configuration line. Three key rules:

1. **Effective logger level** decides whether an event passes the source logger; child loggers can inherit from or override their parent.
2. **Handler/appender thresholds, filters, and propagation** decide where an accepted event goes and whether it is filtered further.
3. **Positive + negative assertions, state isolation, and cleanup** make tests reliable; async, file, collector, and runtime config require corresponding integration tests.

The Java 17 JUL example makes independent thresholds clear. For Logback, use `ListAppender` and JUnit; for Log4j2 or Spring Boot, verify the actual running backend and config. Never let a "DEBUG did not appear" test hide a worse bug: **logging is completely broken, or WARN/ERROR are being lost too**.

### References

- Java SE 17 Level: https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Level.html
- Java SE 17 Logger: https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Logger.html
- Java SE 17 Handler: https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Handler.html
- Logback architecture and additivity: https://logback.qos.ch/manual/architecture.html
- Logback filters: https://logback.qos.ch/manual/filters.html
- Logback configuration: https://logback.qos.ch/manual/configuration.html
- Logback ListAppender source: https://logback.qos.ch/xref/ch/qos/logback/core/read/ListAppender.html
- Log4j2 configuration: https://logging.apache.org/log4j/2.x/manual/configuration.html
- Log4j2 filters: https://logging.apache.org/log4j/2.x/manual/filters.html
- Spring Boot logging: https://docs.spring.io/spring-boot/reference/features/logging.html
- Spring Boot Actuator Loggers: https://docs.spring.io/spring-boot/reference/actuator/loggers.html
- JUnit Jupiter User Guide: https://docs.junit.org/current/user-guide/
- OWASP Logging Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html