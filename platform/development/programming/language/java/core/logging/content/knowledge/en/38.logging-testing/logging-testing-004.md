# Testing Exceptions in Java Core Logging

## Learning Objectives

This lesson belongs to the **Testing logging** group, topic **Testing exceptions**. When a Java application encounters an exception, the logging system must provide enough trace information for investigation without producing false information, logging too many duplicates, or exposing sensitive data. A test that only searches for the string `"ERROR"` in the console is usually insufficient: an exception may be logged at the wrong level, lose its `Throwable`/stack trace, be filtered out at an appender, be logged multiple times across layers, or arrive late at the backend through an async pipeline.

After this lesson, you can:

- Distinguish between testing **an exception being thrown**, **an exception being caught/handled**, and **an exception being logged**.
- Verify `level`, logger name, event code, message template/structured fields, exception class, `Throwable`, cause chain, and suppressed exceptions.
- Understand when to log `ERROR`/`WARN`, and when a successfully handled exception should not generate false error logs.
- Write a JDK-only Java 17 test to capture `java.util.logging.LogRecord` using a `Handler` and assert exact results.
- Use Logback's `ListAppender` with JUnit 5 to inspect events without relying on console text; recognize differences when the backend is Log4j 2.
- Detect duplicate logs, duplicate stack traces, MDC/correlation bugs, log injection, secret leaks, and unintended changes in stack trace encoding.
- Test asynchronous logging with deadlines and verify the log path from logger to appender and collector/index.
- Build a test matrix for business errors, rollbacks, retries, exception chains, failures in logging sinks, and regressions.

**Core principle:** Tests must prove both what the system **actually emits** and what the system **must not emit**. A thrown exception is not necessarily logged; an existing log event does not necessarily reach the monitoring system; an `ERROR` line does not prove that the stack trace or context is correct.

## 1. Three Different Things: Throw, Handle, and Log

In Java:

- **Throw:** `throw new IllegalStateException(...)` transfers control through exception propagation.
- **Handle:** `catch` processes the exception, converts it to another result, retries, compensates, or rethrows. Catching an exception does not automatically mean the error has been resolved.
- **Log:** the logger is invoked and the logging pipeline may create a `LogRecord`/`LoggingEvent` and send it to a handler/appender/sink.

These three activities are independent to a certain degree. Consider the example:

```java
try {
    service.process(command);
} catch (IllegalStateException ex) {
    logger.error("event=command.failed command_id={}", commandId, ex);
    throw ex;
}
```

This is an **SLF4J snippet**, requiring the corresponding variables and dependencies, not a standalone program. If a global exception handler also logs that exception when rethrown, the same error can produce **two identical ERROR events**. This may be valid if the two events add different meaning and are permitted by policy, but by default you should choose a single boundary responsible for logging the full error.

Conversely, an exception may be handled and the application recovers:

```java
try {
    cached = remoteCache.get(key);
} catch (CacheUnavailableException ex) {
    cached = localFallback.get(key);
    // Can increment a metric and log a rate-limited WARN.
    // Not necessarily ERROR if the request still succeeds within SLA.
}
```

This is Java pseudocode with hypothetical types. If you log `ERROR` and then handle it successfully as normal, dashboards may trigger false alerts. Log level policy should be based on **business impact** and whether the error was handled, not merely the existence of a `catch` block.

### Exact Conditions to Test

| Scenario | Application Outcome | Expected Logging Behavior |
| --- | --- | --- |
| No error | SUCCESS | No `exception.failed`; may have success log per policy |
| Exception handled and fallback succeeds | RECOVERED | WARN/INFO or metric depending on policy, not ERROR by default |
| Unhandled exception, request fails | FAILED | One complete error event at the appropriate boundary, with Throwable and correlation ID |
| Exception wrapped and propagated | FAILED | Log outer exception with cause chain, not just message string |
| Transient error being retried | RETRY_PENDING | Log attempts moderately, avoid repeating ERROR stack traces on every attempt |
| Retries exhausted | EXHAUSTED | Clear terminal event with full cause and attempt count |
| Expected invalid input exception | REJECTED | May be WARN/INFO, not always a system incident |
| Exception from logging appender | LOGGING_FAILURE | Report via pipeline status/monitoring; do not create a recursive error logging loop |
| Exception containing a secret | FAILED | No secret leaked in message, stack trace, MDC, or encoded output |

Do not use an assertion that "an exception was thrown" as a substitute for asserting that "the right log event was emitted." A business logic unit test and a logging test can complement each other, but they verify two different contracts.

## 2. Testing Layers in the Logging Pipeline

A conceptual logging pipeline:

```text
Business code -> Logger call -> level/filter -> LogRecord/LoggingEvent
                                            |
                                            v
                                       Handler/Appender
                                            |
                      +---------------------+---------------------+
                      |                     |                     |
                  stdout/file          async queue          network exporter
                      |                     |                     |
                      +---------------------+---------------------+
                                            |
                                       agent/collector
                                            |
                                      index/query/alert
```

Different points need separate tests:

| Layer | What does the test tell you? | What can it not assert? |
| --- | --- | --- |
| Business code unit test | Which exception is thrown, caught, wrapped, and what outcome is returned | Whether a logging event is emitted to the right sink |
| In-memory event test | Which event, level, template, Throwable, and MDC the Logger/Handler/Appender receives | Whether the file/console/collector/index has received it |
| Encoder/layout test | Whether text/JSON has the right fields, stack trace, escaping, and redaction | Whether the event was successfully transmitted over the network |
| Sink integration test | Which records the real console/file/appender receives | Whether the backend can search/query the log |
| End-to-end log pipeline | Whether the event appears at the collector/index within deadline with the right schema | That every future event is guaranteed never to be lost |
| Load/failure test | Async buffering, dropping, retry, and blocking under overload | Correctness does not need to be tested under normal load |

**A good choice:** Use an in-memory appender to verify `Throwable` accurately, quickly, and without flakiness; use separate integration tests for file/JSON; use separate end-to-end tests to prove forwarding/ingestion. Avoid forcing every unit test to wait for an external log collector.

### Positive and Negative Assertions

A good test asserts both directions:

- **Positive:** When checkout fails, there is exactly one `event=checkout.failed` with `ERROR` and the appropriate cause.
- **Negative:** There is no `checkout.succeeded`, no two duplicate error events, no token logged, and no exception sent to the wrong audit sink.
- **Count:** If policy requires one event at a boundary, assert exact count = 1, not just `>=1`.
- **Subject:** With two concurrent requests, request A's event carries A's ID, without B's MDC leaking in.
- **Timing:** In async logging, an absence assertion is only valid after flushing/draining and observing for the full deadline.

A string search in output does not automatically distinguish whether an event was logged twice, emitted on a parent logger, or encoded from two different exceptions with the same message.

## 3. Verifying Properties of an Exception Log

### 3.1. Level

SLF4J/Logback/Log4j 2 backends typically use `TRACE`, `DEBUG`, `INFO`, `WARN`, and `ERROR`. In JUL, the semantically corresponding levels include `FINE`, `INFO`, `WARNING`, and `SEVERE`; JUL **does not have** `Level.ERROR` or `Level.DEBUG`.

Test levels according to policy:

- Errors that fail a request and require intervention: `ERROR` or `SEVERE`.
- Transient timeouts with retry that are expected to recover: `WARN` or lower depending on noise budget.
- Expected validation failures: may be `INFO`/`WARN` or a separate audit log.
- Recovered errors: do not automatically keep `ERROR` if it causes misleading alerts.
- Security decisions/audits have their own event path/retention; log level must not replace audit policy.

Tests should check the event's **level enum** rather than matching the string `"ERROR"` which could appear inside a message. At the same time, an event with the right level that is dropped by the effective logger level or an appender filter still will not appear at the destination; you need to test the actual configuration.

### 3.2. Logger Name, Event Code, Message, and Metadata

Test stable fields:

- `loggerName`/package to distinguish the source.
- Standard `event_code` or marker such as `order.failed`, without depending on the entire translated/formatted sentence.
- `request_id`, `operation_id`, `message_id`, or `trace_id` depending on context.
- Permitted resource IDs, service, environment, error category.
- `outcome` consistent with the business state.

You can test the **message template** at the logger and the **formatted message** at the appender, but those are two different stages. A test that only asserts the raw template text does not verify whether placeholders were rendered properly in the final output. A test that only searches output text does not necessarily detect missing structured fields or a missing `Throwable`.

**Do not test full timestamps, thread IDs, or location line numbers** using fixed values if those fields are not part of the contract. Timestamps/stack frames depend on the machine, version, compilation, and runtime conditions. For tests needing deterministic time, inject `Clock.fixed` where application timestamps are created; do not assume every logging backend's timestamp uses that `Clock`.

### 3.3. Throwable and Stack Trace

In JUL, `LogRecord.getThrown()` returns the `Throwable` attached to the record. In Logback, `ILoggingEvent.getThrowableProxy()` and `IThrowableProxy` reflect the exception captured by the backend. Verify:

1. A `Throwable`/exception proxy is present, not just an `ex.getMessage()` string.
2. The **outermost** exception type is correct; if wrapped, the cause chain is intact.
3. The stack trace has frames useful for investigation; the root cause is not lost due to using the wrong logger overload.
4. Suppressed exceptions are preserved on the `Throwable`, if the flow uses try-with-resources or manual suppression.
5. No message/stack trace contains secrets when the encoder or policy requires redaction.
6. The record is not duplicated by log-and-rethrow across multiple layers, additivity, or duplicate collector ingestion.

In many frameworks, calling:

```java
logger.error("Processing failed: {}", exception.getMessage());
```

only produces **message text**, without attaching the `Throwable` for the backend to print the stack trace; conversely:

```java
logger.error("Processing failed", exception);
```

attaches the exception to the logging event per the standard SLF4J API. This is an SLF4J snippet, not pure JDK Java. With parameterized logging, SLF4J usually accepts `Throwable` in the last position, but you must verify the overload/version of the running backend. Do not confuse a `Throwable` passed as a normal format argument with the backend actually receiving an exception cause.

### 3.4. Cause and Suppressed Exceptions

A modern error may have:

```text
IllegalArgumentException: order processing failed
  caused by IllegalStateException: database unavailable
    suppressed IOException: resource close failed
```

For the original `Throwable`, test:

- `outer.getCause()` is the right cause type.
- `outer.getCause().getSuppressed()` contains the secondary exception if added.
- Wrapping an exception does not replace the entire root cause with a message string.
- If the encoder has a stack trace depth limit, test long cause chains per policy, but do not try to print infinite stack traces or sensitive payloads.

A suppressed exception is **different** from a cause: `getSuppressed()` is an array on the specific `Throwable` to which it was attached, not automatically on the outer exception. Stack trace formatters may display them in different positions; testing the model via API is usually more durable than comparing the entire trace text.

## 4. Standalone Java 17: Testing `LogRecord` and `Throwable`

This example uses **only JDK 17+**, without needing Maven, JUnit, Spring Boot, Logback, or Log4j 2. It uses `java.util.logging.Logger` and an in-memory `Handler` to record what JUL actually emits to the handler. The program simulates a repository throwing an error, a service wrapping the exception, logging it **once** at the handling boundary, and propagating it.

Test goals:

- Exactly one record is received by the handler.
- Level `SEVERE`, logger name, and message are correct.
- `LogRecord.getThrown()` is the **same instance** as the exception caught by the caller.
- Cause is `IllegalStateException` and there is one suppressed `IOException`.
- No output from parent handlers; stdout only prints assertion results.
- Changing a critical detail (level, message, or cause) causes the test to fail with `IllegalStateException`.

### File `ExceptionLoggingTestDemo.java`

```java
import java.io.IOException;
import java.util.ArrayList;
import java.util.List;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class ExceptionLoggingTestDemo {
    private static final class MemoryHandler extends Handler {
        private final List<LogRecord> records = new ArrayList<>();

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

    private static void repositoryWrite() {
        IllegalStateException root =
                new IllegalStateException("database unavailable");
        root.addSuppressed(new IOException("cleanup failed"));
        throw root;
    }

    private static void processOrder(Logger logger) {
        try {
            repositoryWrite();
        } catch (IllegalStateException root) {
            IllegalArgumentException outer =
                    new IllegalArgumentException(
                            "order processing failed", root);
            logger.log(Level.SEVERE,
                    "event=order.failed order_id=order-7", outer);
            throw outer;
        }
    }

    private static void require(boolean condition, String name) {
        if (!condition) {
            throw new IllegalStateException(
                    "assertion failed: " + name);
        }
    }

    public static void main(String[] args) {
        Logger logger = Logger.getLogger("demo.exception.boundary");
        logger.setUseParentHandlers(false);
        logger.setLevel(Level.INFO);

        MemoryHandler capture = new MemoryHandler();
        capture.setLevel(Level.ALL);
        logger.addHandler(capture);

        try {
            IllegalArgumentException caught = null;
            try {
                processOrder(logger);
            } catch (IllegalArgumentException failure) {
                caught = failure;
            }

            require(caught != null, "exception propagated");

            List<LogRecord> records = capture.snapshot();
            require(records.size() == 1, "one event");

            LogRecord record = records.get(0);
            require(record.getLevel().equals(Level.SEVERE), "level");
            require("demo.exception.boundary".equals(
                    record.getLoggerName()), "logger name");
            require("event=order.failed order_id=order-7"
                    .equals(record.getMessage()), "message");
            require(record.getThrown() == caught, "throwable identity");

            Throwable cause = caught.getCause();
            require(cause instanceof IllegalStateException, "cause");
            require(cause.getSuppressed().length == 1, "suppressed");
            require(cause.getSuppressed()[0] instanceof IOException,
                    "suppressed type");

            System.out.println("record_count=" + records.size());
            System.out.println("level=" + record.getLevel().getName());
            System.out.println("logger=" + record.getLoggerName());
            System.out.println("message=" + record.getMessage());
            System.out.println("exception="
                    + record.getThrown().getClass().getSimpleName());
            System.out.println("cause="
                    + cause.getClass().getSimpleName());
            System.out.println("suppressed_on_cause="
                    + cause.getSuppressed().length);
            System.out.println("parent_handlers="
                    + logger.getUseParentHandlers());
            System.out.println("test=PASS");
        } finally {
            logger.removeHandler(capture);
            capture.close();
        }
    }
}
```

Compile and run:

```bash
javac ExceptionLoggingTestDemo.java
java ExceptionLoggingTestDemo
```

**Exact stdout:**

```text
record_count=1
level=SEVERE
logger=demo.exception.boundary
message=event=order.failed order_id=order-7
exception=IllegalArgumentException
cause=IllegalStateException
suppressed_on_cause=1
parent_handlers=false
test=PASS
```

**Why is the output deterministic?**

1. The program creates and calls code in a **single thread**, using a `Handler` that stores records in an `ArrayList`; there is no async queue and no printed timestamp.
2. `Logger#setUseParentHandlers(false)` prevents records from propagating further to JUL root/parent handlers, so no default `SEVERE` messages intrude on stdout/stderr.
3. Logger level `INFO` allows `SEVERE`; handler level `ALL` does not block the record. Each call to `processOrder` emits only one event.
4. `logger.log(Level.SEVERE, message, outer)` uses the overload accepting `Throwable`, so `LogRecord.getThrown()` is `outer`. The `catch` block in the caller receives the same instance because the code rethrows it.
5. `root.addSuppressed(...)` attaches the `IOException` to the root cause; when wrapped with `IllegalArgumentException(message, root)`, the cause/suppressed chain remains intact.
6. `snapshot` is called after the synchronous logger call has returned and on the same thread. It does not prove thread safety if multiple threads are used; concurrent appender/handler tests need synchronized collections or inspection after workers complete.
7. `test=PASS` only appears after **all assertions pass**. If the code changes so that it does not log or loses the `Throwable`, the program throws an error before the PASS line.

### Try Breaking Things to See What the Test Catches

- Change `Level.SEVERE` in `processOrder` to `Level.FINE`: the logger's effective level `INFO` will drop the event; the `one event` assertion fails.
- Change `logger.log(Level.SEVERE, "...", outer)` to `logger.severe(outer.getMessage())`: the record has no `Throwable` attached; the identity assertion fails, and the message differs.
- Omit `outer` when rethrowing and throw a new exception without a cause: the cause or identity assertion fails.
- Call the logger twice for the same event: the `records.size() == 1` assertion detects the duplicate.
- Enable `setUseParentHandlers(true)`: the current test prints `parent_handlers=true` but **does not automatically detect duplicates at the parent handler**. To test duplication in external sinks, you need an integration test for the parent/console; an in-memory handler only sees records delivered to itself.

**Example limitations:** This is a **JUL `LogRecord` content test**; it does not test stack trace text rendered by a `Formatter`, file permissions, JSON serialization, collector ingestion, or durability. Those layers need further tests below. It also does not prove security policy because the exception strings in the program only contain dummy data.

## 5. Logback + SLF4J + JUnit 5: Capturing Events with `ListAppender`

When an application uses SLF4J with Logback Classic, you should inspect `ILoggingEvent` instead of capturing `System.out`. A common approach is attaching `ch.qos.logback.core.read.ListAppender` to a dedicated test logger.

The example below is **not pure JDK Java**. It requires a project with JUnit Jupiter, `slf4j-api`, and compatible `logback-classic`/`logback-core` on the test classpath. The code illustrates a test class in a Maven/Gradle project with dependencies configured; it is not a standalone program run with `javac`.

### JUnit 5 / Logback Classic Example

```java
import ch.qos.logback.classic.Level;
import ch.qos.logback.classic.Logger;
import ch.qos.logback.classic.spi.ILoggingEvent;
import ch.qos.logback.core.read.ListAppender;
import org.junit.jupiter.api.Test;
import org.slf4j.LoggerFactory;

import static org.junit.jupiter.api.Assertions.*;

class ExceptionLogbackTest {
    @Test
    void capturesThrowableAndFormattedMessage() {
        Logger logger = (Logger) LoggerFactory.getLogger(
                "example.test.exception.capture");

        Level oldLevel = logger.getLevel();
        boolean oldAdditivity = logger.isAdditive();

        ListAppender<ILoggingEvent> capture = new ListAppender<>();
        capture.setContext(logger.getLoggerContext());
        capture.start();

        logger.setLevel(Level.ERROR);
        logger.setAdditive(false);
        logger.addAppender(capture);

        try {
            IllegalStateException failure =
                    new IllegalStateException("db unavailable");

            logger.error("event=order.failed order_id={}",
                    "order-7", failure);

            assertEquals(1, capture.list.size());
            ILoggingEvent event = capture.list.get(0);

            assertEquals(Level.ERROR, event.getLevel());
            assertEquals("example.test.exception.capture",
                    event.getLoggerName());
            assertEquals("event=order.failed order_id=order-7",
                    event.getFormattedMessage());

            assertNotNull(event.getThrowableProxy());
            assertEquals(IllegalStateException.class.getName(),
                    event.getThrowableProxy().getClassName());
        } finally {
            logger.detachAppender(capture);
            capture.stop();
            logger.setLevel(oldLevel);
            logger.setAdditive(oldAdditivity);
        }
    }
}
```

Analysis:

- Using a dedicated logger name prevents the test from attaching to a global business logger used by other tests.
- `setAdditive(false)` prevents the test logger's events from propagating up to parent appenders during the test; the old value is restored afterward.
- `setLevel(ERROR)` ensures the demonstration event is created; another test can check the negative case when the level blocks it.
- `getFormattedMessage()` verifies that placeholders were rendered into the expected ID.
- `getThrowableProxy()` shows that Logback received the `Throwable`, unlike just having the exception message text.
- `finally` detaches/stops the appender and restores level/additivity so the test does not cause side effects for subsequent tests.

**Note:** `ILoggingEvent.getThrowableProxy()` is Logback's representation, not the original `java.lang.Throwable`. When you need to inspect the cause chain, you can check `IThrowableProxy.getCause()` and the appropriate class/message info; if you need exact `Throwable` object identity in a unit test, keep a reference at the call site or use an appropriate capture layer. Do not assume every backend preserves the same object identity or the same stack trace formatting.

If a suite runs in parallel and configures the same logger, changing level/additivity can cause races. Use unique logger names, separate test configurations, framework test isolation, or serialize within the appropriate scope; avoid arbitrarily mutating the root logger in every test. With Spring Boot, `@SpringBootTest` may initialize logging config from a profile; verify which test actually uses `logback-test.xml`, `logback-spring.xml`, or another override.

## 6. Testing Cause Chains, Suppressed Exceptions, and Stack Trace Formatting

At the model layer, check cause/suppressed via API; at the layout layer, check output by **stable characteristics**. An exception stack trace typically contains:

- The outermost exception line, class name, and message.
- One or more stack frames for the call path.
- `Caused by:` and deeper causes if the formatter outputs them in full.
- `Suppressed:` if suppressed exceptions exist and the formatter supports them.
- Information from MDC/structured fields when the layout is configured appropriately.

**Illustrative** console output example:

```text
ERROR event=order.failed order_id=order-7
java.lang.IllegalArgumentException: order processing failed
    at demo.OrderService.process(OrderService.java:42)
Caused by: java.lang.IllegalStateException: database unavailable
    at demo.OrderRepository.write(OrderRepository.java:17)
    Suppressed: java.io.IOException: cleanup failed
```

**Do not use line numbers 42/17 or the indentation style above as a golden string across all JDKs/backends.** Formatters may abbreviate common frames, add colors, change timestamp styles, or limit cause depth. Not every `Throwable` has a normal stack trace—for example, code may disable stack traces or the backend may truncate them.

### Recommended Assertion Levels

- **Unit:** `Throwable` is non-null, class/cause/suppressed are correct, and it is attached to the event.
- **Layout integration:** output shows stack trace/`Caused by`/`Suppressed` indicators when policy requires; JSON format contains exception fields matching the schema.
- **End-to-end:** collector/index stores and displays exception type, masked message, stack trace, or permitted error fields.
- **Security:** no password/token/PII appears in **any** part of the formatted log, including nested exception messages.

If the system intentionally truncates stack traces to limit size, tests must assert that the truncation policy works properly while preserving error codes/trace IDs/causes needed for investigation. Do not require storing the full trace of every exception if doing so violates data policy or log volume budgets.

## 7. When Is Capturing `stdout`/`stderr` Useful?

Some legacy systems write `ex.printStackTrace()` directly to `System.err`; some small programs use JUL's `ConsoleHandler` or `ConsoleAppender`. When you need to verify final output you can capture stdout/stderr, but this type of test is error-prone and flaky:

- `java.util.logging.ConsoleHandler` by default usually writes to **stderr**, not necessarily stdout.
- `System.setOut(...)`/`System.setErr(...)` is **global JVM state**; parallel tests can interfere with each other.
- An appender may hold a reference to the old stream when initialized, so swapping `System.out` when a test starts may not capture it.
- Async logging may write after the test has already restored the stream.
- Text output also depends on layout, timezone, locale, timestamp, and stack trace formatting.
- Frameworks may log via socket/file instead of console, making a console test prove nothing about the real sink.

**Prefer** in-memory event capture for unit tests, and test stdout/stderr in a separate process test (e.g., running a CLI in a subprocess) when the **console path is a contract that must be verified**. If capturing global streams in the same JVM, restore them in `finally` and ensure the suite does not run concurrently with other tests affecting streams.

Do not use `printStackTrace()` as a business logging system. It lacks structured context, routing, levels/filters, and dedicated sensitive-data policies. Once an exception is already logged through a structured logger, an extra `printStackTrace()` usually causes duplicates and makes management harder.

## 8. Testing "Log Exactly Once" and Error-Handling Boundaries

An error can appear at three layers:

```text
Repository -> Service -> HTTP Controller / Global Exception Handler
    |            |                    |
  throw         wrap                 respond
                 |
              log?                log?
```

If Repository logs ERROR and throws, Service logs ERROR and throws, and Global Handler logs ERROR again, one exception can create three identical events. This creates noise, increases collector cost, and makes operators think there are three independent errors.

A commonly useful design:

1. Low layers **throw exceptions with causes** and appropriate error codes, without necessarily logging if they do not handle the error themselves.
2. The boundary responsible for handling the request/job logs one error event with operation ID, event code, and `Throwable` once.
3. If a lower layer performs retry/recovery, log necessary state transitions and total retry count, rather than printing ERROR stack traces on every step.
4. Tracing/metrics systems can collect separate signals; exception logging does not replace everything.

**There is no absolute rule that "every exception across a distributed system is logged only once."** Service A and Service B may need to log separately at their service boundaries with different context. Tests need to know the contract: how many **logical events** are expected for one exception in one request/operation, and where.

### How to Test for Duplicates

- Issue a request with a unique `test_request_id`/`operation_id`.
- Capture the list of events at the logger/appender under test.
- Filter by `event_code` and ID; assert the expected count of events of that type.
- Check other sinks and verify intentional additivity/fan-out.
- For collectors, check for duplicates caused by an agent reading both stdout and a file.
- When retrying, distinguish valid **attempt events** from the **terminal failure event**; do not count every WARN attempt as a terminal ERROR.

**Do not use message text alone as a deduplication key:** two real requests can share the same text, while one request can produce multiple event codes. Combine event ID/request ID/operation ID and routing policy.

## 9. Testing "Do Not Log" Is a Real Requirement

A good exception test suite does not only verify emitted events. It must also prove **no event is emitted in cases that must stay silent**:

- Success path has no ERROR.
- Recovered exception is not logged as a terminal failure.
- Exception converted by a handler into an expected business response does not produce useless ERROR stack traces.
- Library exception caught and handled only produces a metric/INFO per policy.
- Sensitive data is never leaked on the error path.
- Sensitive audit events are not emitted to the general stdout logger when routing requires separation.
- No repeated ERRORs due to additivity or multiple exception handlers.

Example matrix:

| Case | Expected ERROR | Expected WARN | Forbidden Things |
| --- | ---: | ---: | --- |
| Handler success | 0 | 0 | No stack trace |
| Retry transient attempt | 0 per policy | 1 | Do not report terminal failure prematurely |
| Retry exhausted | 1 | May have attempt summary | No two terminal ERRORs |
| Validation rejection expected | 0 or per policy | 0/1 | Do not log raw request body |
| Auth rejected | Audit/security per policy | Per policy | Do not leak token |
| Unexpected failure | 1 | Not required | Do not lose Throwable |
| Failed sink | Report via separate status/metrics | Per pipeline | No recursive logger failure |

These numbers are **an example policy for one system**. If your project's policy differs, write explicit expected events first and test the exact contract. Negative assertions must observe a wide enough scope; "not seen in `ListAppender` A" does not mean the event did not leak to appender B.

## 10. Common Pitfalls When Using JUnit/Mockito to Test Logging

Some teams only mock `Logger` and verify:

```java
verify(logger).error("operation failed", exception);
```

This is a **hypothetical Mockito/SLF4J snippet**, requiring a mock logger and declared variables. It can be useful to verify that **business code calls the logger API**, but it does not confirm that the backend created a `LoggingEvent`, formatted the message, preserved the cause, or sent it to a sink. If you mock a logger that production initializes via static/final `LoggerFactory`, swapping in a mock may also require a logger-injection/test-seam design that differs from production code.

Layer your tests:

- Mock verify for logic checking "was this logging API called" when that is a unit requirement.
- In-memory Appender/Handler to verify **actual emitted events**.
- Integration tests for real encoders/filters/routing.
- End-to-end tests for agents/collectors/indexes.

**Do not overfit tests to a specific log method** if the contract is only event code and level. Refactorings such as using the SLF4J fluent API, switching logger wrappers, or changing templates can break Mockito `verify` even though operators still see the same valid event. Focus on behavior with business value.

### Avoiding State Leaks Between Unit Tests

- When attaching an appender in a test, detach and stop it in `finally`.
- When changing level, additivity, or filters, restore the old values.
- Do not modify the root logger across the entire test suite without isolation.
- Use dedicated logger names per suite or specialized setup fixtures.
- For parallel tests, use thread-safe appenders or per-process/per-context test setup.
- Do not depend on test execution order if tests share static loggers/global configuration.

If multiple tests attach a `ListAppender` to the same logger without detaching, an event from test B can end up in test A's buffer, causing false positives or unexpected log volume.

## 11. Testing MDC, Trace ID, and Exceptions Across Async Boundaries

Exceptions do not always occur on the initial thread. With `ExecutorService`, `CompletableFuture`, message listeners, or schedulers, there can be a thread boundary:

```text
HTTP request thread
  MDC: request_id=req-17
       |
       v
Submit async task
       |
       v
Worker thread
  MDC: absent / propagated / stale
       |
       v
Exception thrown -> log ERROR
```

Bugs to catch:

- ERROR event is missing `trace_id`/`request_id` because context was not propagated.
- Worker thread still holds MDC from a previous message/request, attaching the wrong tenant or actor.
- Exception is wrapped in `CompletionException`/`ExecutionException` but the log only contains the wrapper message, losing the cause.
- Async failure is swallowed when a `Future` is not observed, leaving no log or metric.
- Log is emitted, but the async appender has not drained when the test finishes.

### Testing Context Propagation

With Logback/SLF4J, `MDC.getCopyOfContextMap()` can return a map or null; tests should use a propagation mechanism appropriate for the framework and executor type. Do not assume MDC automatically propagates across thread pools. When scoping is needed:

```java
// SLF4J snippet, assuming MDC is already integrated.
String previous = org.slf4j.MDC.get("request_id");
try {
    org.slf4j.MDC.put("request_id", "req-17");
    // Invoke code within the request scope.
} finally {
    if (previous == null) {
        org.slf4j.MDC.remove("request_id");
    } else {
        org.slf4j.MDC.put("request_id", previous);
    }
}
```

This is not a standalone program. If there are multiple MDC keys, use proper full-map scoping/restoration; if running async, carry context in a controlled way and clean it up in the worker. **Do not put tokens, passwords, or raw payloads into MDC**, because every log in that scope can inherit them.

### Assertions with Asynchronous Appenders

With async logging, an event may be created on the caller thread while the appender executes later. Tests need:

1. A unique `test_event_id` to identify the event.
2. A finite deadline or a flush/drain mechanism supported by the backend.
3. Inspection of queue/worker status and dropped event counts under overload.
4. Distinguishing an event that **has not arrived yet** from an event that was **filtered/dropped**.
5. Asserting absence at the wrong sink **after** the pipeline has had enough time to process.

**Do not use `Thread.sleep(100)` and assume logs will always be there.** On slow CI or under load, processing time varies. Use bounded polling and explicit wait mechanisms; if the backend does not expose flush, design a test sink that signals when an event is received.

## 12. Testing Redaction and Log Injection on Exception Paths

This is the easiest part to overlook: sensitive information can live in **exception messages**, **cause chains**, **suppressed exceptions**, **stack trace fields**, **MDC**, or **request objects** passed to the logger.

### Canary Secrets and Negative Testing

Use a dummy string such as `TEST_SECRET_DO_NOT_EMIT` in simulated input:

```text
Input:
  authorization_header = "Bearer TEST_SECRET_DO_NOT_EMIT"
  account_id = "acct-test-7"

Expected log:
  event=remote.call.failed
  account_id=acct-test-7
  error_code=HTTP_TIMEOUT

Forbidden anywhere in emitted/logged output:
  TEST_SECRET_DO_NOT_EMIT
  Authorization: Bearer
```

These are **test inputs/expectations**, not real data. Tests can scan the entire formatted output of **every target appender**, not just `getFormattedMessage()`. If an encoder prints `ThrowableProxy` itself, the canary string may appear in cause text even if the message template masked it.

**Proper mitigations** in priority order:

1. **Do not put secrets into exception messages or logger arguments in the first place.**
2. Use error codes, exception types, permitted IDs, and minimal metadata.
3. If masking/redaction is needed, apply it consistently across output paths; test message, exception, and structured fields.
4. Verify that the encoder escapes newlines and control characters when receiving untrusted input.
5. Separate audit/security paths and log read permissions according to appropriate policy and retention.

### Log Injection

A user-supplied string may contain newlines:

```text
username = "bob\nERROR admin-access-granted"
```

If the logger writes that string directly into an unescaped text line, an attacker can make the output look like multiple records or inject fake error-level labels. Standard structured JSON encoders typically escape these characters per JSON rules, but you must still test the actual implementation. Do not assume "using JSON" guarantees safety if code concatenates JSON strings by hand without escaping.

Test injection with dummy input, checking for exactly **one parseable JSON event** with the content inside a single field rather than creating a second log line. For text logs, verify the escaping/sanitization approved by your organization. Do not fix the issue by arbitrarily stripping all useful context without replacing it with a safe error code.

## 13. Testing Exceptions in JSON/Structured Logging

Many production systems use JSON logs; an illustrative output:

```json
{
  "timestamp": "2026-11-10T02:00:00.000Z",
  "level": "ERROR",
  "logger": "com.example.checkout.OrderService",
  "service": "checkout",
  "event_code": "order.failed",
  "request_id": "req-test-17",
  "order_id": "order-7",
  "exception_type": "java.lang.IllegalStateException",
  "error_code": "DB_UNAVAILABLE",
  "exception_message": "database unavailable"
}
```

This is **illustrative JSON**, not the default schema of Logback/Log4j 2/OpenTelemetry. When testing structured output, prefer parsing JSON into an object and asserting by key/value rather than comparing the entire string: field order, whitespace, or timestamp formatting may legitimately change.

### JSON Checklist

- Includes `timestamp`, `level`, `logger`, `event_code`, and appropriate request/operation IDs.
- Exception is properly represented via `exception.type`/`exception.stacktrace`/`exception.message` **according to the chosen schema**, without guessing field names.
- Fields containing secrets are removed/masked; full objects/requests are not copied uncontrolled.
- Stack trace sections may contain escaped newlines in JSON; output remains parseable.
- Logger/collector does not split one event into multiple unintended records.
- Events from multiple threads are not interleaved due to a buggy encoder or context capture.
- Cause chain/suppressed exceptions are preserved or summarized per policy; information is not accidentally lost when changing encoders.
- Collector/index parsers preserve event code, error code, trace ID, and status needed for querying.

Be careful when using `Throwable.getMessage()` as a direct field; if the exception message contains URLs/queries/tokens, the serializer will copy it verbatim unless redacted beforehand. Security tests must cover this case.

## 14. How Should the Application React When Logging Fails?

An appender/handler can also fail:

- File cannot be written, disk full, missing permissions.
- Console/stdout is congested or writes block.
- Network collector times out or refuses connection.
- Async queue is full, events are dropped or producers are blocked.
- Encoder throws an exception when serializing an object or handling unexpected data.
- Errors in a custom filter/formatter cause reentrant logging or recursion.

**Do not assume a logger will always throw an exception to the caller when a sink fails.** Some frameworks handle errors internally via `ErrorHandler`/status loggers, warnings, or drops depending on configuration. That is why you must test **events reaching the sink and error metrics**, not just assert that the business method does not throw.

A failure-injection test can:

1. Attach a simulated failing sink at an allowed test point.
2. Trigger a business exception and call the logger.
3. Observe the contract: does the caller block/throw, and through what status/metric is the error reported?
4. Ensure there is no recursive loop: "logging failure -> log error via same failing sink -> logging failure".
5. Verify that audit/critical logs have a separate storage path and policy if required.
6. Recover the sink, verify retry/buffer/drain mechanisms, and reconcile event counts.

The goal is not to "swallow every logging error" for every application. For mandatory audits with a fail-closed policy, failing to store the audit log may require the business logic to reject the transaction. This is an architectural decision based on requirements, not something inferred from a logger API.

## 15. Testing Exceptions at Real Boundaries

### 15.1. HTTP/Controller/Global Exception Handler

With Spring MVC or similar frameworks, an exception can be handled at:

- Service layer.
- Controller.
- Filter/interceptor.
- `@ControllerAdvice`/global exception handler.
- Web container and reverse proxy.

Choose a clear logging boundary. An end-to-end test should verify:

1. Response status matches the error type.
2. One appropriate error event exists with the request ID.
3. No exception message, stack trace, or internal data leaks into the HTTP response when not permitted.
4. No duplicate ERROR records from both service and global handler if policy allows only one event.
5. Expected validation/business errors do not dump stack traces en masse.
6. Request context is cleared after handling.

A controller test that only asserts HTTP 500 does not guarantee the log has a stack trace; conversely, the presence of an ERROR event does not prove the response mapping is correct.

### 15.2. Message Listener/Consumer

With Kafka/RabbitMQ/JMS:

- A failed processing attempt may cause message retry, NACK/requeue, DLQ routing, or retry topic.
- Logs should retain `message_id`/`operation_id`, `attempt`, error code, and known state.
- Do not log `message.processed` success if the handler threw.
- Do not log `dlq_confirmed` when only requesting DLQ without confirmation.
- If the same message retries multiple times, tests should distinguish attempt logs from terminal failure.
- When the handler succeeds but ACK/offset commit fails, the message may be redelivered; idempotency is needed—do not conclude there were two side effects solely from two logs.

These assertions relate to exception logging, but **broker acknowledgements require integration tests**. An in-memory logger test does not prove that Kafka committed the offset or RabbitMQ actually sent an ACK.

### 15.3. Scheduled Tasks/Background Workers

An uncaught exception in a scheduler or async task may:

- Be logged separately by the framework and then ignored/pause the job.
- Be stored in a `Future`, only surfacing when `get()` is called.
- Be wrapped in `ExecutionException` or `CompletionException`.
- Trigger `UncaughtExceptionHandler` if truly an uncaught exception on the thread.

Tests must identify **who owns final error handling**, avoiding logging inside the task and logging again when the future is awaited. With `Future.get()`, unwrap the cause properly and log the job context; `Future.get()` can also throw `InterruptedException`, requiring a policy to preserve the interrupt flag when appropriate.

### 15.4. Startup/Shutdown

Exceptions occurring while logging is not yet configured or during shutdown may not reach normal appenders. Integration tests must consider initialization order, fallback status/error output, flush/drain on stop, startup log levels, and potential data remaining in queues when a process is killed. Do not test "exception was logged" by checking immediately after `System.exit` without a process/sink observation mechanism.

## 16. Exception Logging Test Matrix

| ID | Scenario | Positive Check | Negative Check |
| --- | --- | --- | --- |
| E1 | Processing succeeds | Success log/metric per policy | No ERROR or exception |
| E2 | Unexpected exception | One ERROR event, right exception class/cause | No lost Throwable, no duplicate logs |
| E3 | Wrapped exception | Cause chain and error code preserved | Not only the outer message |
| E4 | try-with-resources close failure | Suppressed recognized per policy | Suppressed not confused with root cause |
| E5 | Fallback recovery | Outcome RECOVERED, WARN/metric per policy | No false terminal failure |
| E6 | Validation exception | 4xx/REJECTED per app contract, appropriate log level | No raw input/unnecessary stack trace |
| E7 | Retry then succeed | Valid attempts, one final success | No terminal ERROR once recovered |
| E8 | Retry exhausted | One terminal event and attempt count | No multiple terminal events emitted |
| E9 | Rethrow across layers | Logged at boundary, correlation present | No 2–3 identical stack traces outside policy |
| E10 | Effective logger level disabled | Event not created per rule | No accidental INFO/DEBUG emission |
| E11 | Appender filter denies | Event does not reach rejected sink | Do not confuse "logger called" with delivered |
| E12 | Async appender delay | Event received before deadline | No flaky tests using fixed sleep |
| E13 | Async queue full | Block/drop policy works, telemetry present | Do not report 100% delivered when dropped |
| E14 | Root/additivity | Exact event count per appender | No unintended duplicates |
| E15 | Exception contains dummy canary token | Safe metadata logged, redacted across all sinks | No canary in message/stack/MDC |
| E16 | Newline injection in input | JSON/text properly escaped/sanitized | No fake log lines created |
| E17 | Thread pool reuse | Correct request/message ID per thread | No stale MDC from previous request |
| E18 | Logging sink exception | Error status/metric, recovery per policy | No recursive log storm |
| E19 | Collector/index failure | Distinguish sink emitted vs. ingested | Do not conclude missing log means no business error |
| E20 | Version/backend migration | Level, event code, Throwable, schema compatible | No lost causes or silent routing changes |

This matrix is a starting point. Organizations can add audit logging, security logging, or stack trace sanitization requirements. Events and levels must be standardized according to the actual logging contract; do not assume every framework shares the same configuration.

## 17. Testing Asynchronous Logging Properly

Suppose an application uses Logback `AsyncAppender`, Log4j 2 `AsyncLogger`, or an async exporter. When `logger.error(...)` returns:

- The event may only have been placed into an in-memory queue.
- The formatter/sink worker has not finished writing.
- The collector may not have ingested it yet.
- The index may not be searchable yet.

Tests should not assert in the same millisecond that the backend has received the event. A disciplined approach:

1. Emit an event with a unique `test_event_id`.
2. Identify **at which hop the record must appear** for the test—e.g., in-memory appender, file, collector, or index.
3. If the backend exposes a valid flush/drain API, use it according to its exact semantics; do not assume `flush()` means durable across all hops.
4. Poll with a finite deadline, reasonable interval, and cancel/cleanup when the test finishes.
5. Check both the positive event and forbidden events at the wrong sinks.
6. If the event is not seen, inspect filter metrics, queue drops, appender errors, collector ingest lag, and indexing.
7. Report the outcome clearly: **not emitted**, **emitted but not delivered**, **delivered but not searchable**, or **observed**.

**Do not use `Thread.sleep(500)` as a correctness guarantee** in CI. It can both slow down tests and be flaky when machines are overloaded.

### Under High Load

An exception event usually has a longer stack trace than an info event. Error bursts can push the logging pipeline from normal operation to queue-full, causing app threads to block or drop events depending on policy. Therefore, performance tests should measure:

- Exception events/s, bytes/s, and average/p95 log payload size.
- CPU/allocations for exception capture and stack formatting.
- Appender queue depth, blocked enqueue duration, dropped events.
- Sink write latency, collector/index visibility latency.
- Request/consumer p95/p99 and total terminal failures.
- Retention rate of ERROR/critical logs per policy, not inferred from seeing fewer logs.

Do not lose audit/security exception logs just to increase throughput without an appropriate policy decision.

## 18. Regression Testing for Logging Framework or Encoder Changes

When upgrading Logback, Log4j 2, SLF4J, or the JDK, or switching from text layout to JSON, the following differences can appear:

- Message formatting and `Throwable` extraction from varargs change if the wrong overload is used.
- Stack trace converters may abbreviate, limit depth, or omit `Caused by`.
- JSON field names may change from `exception` to `exception.type`/`error.type`.
- MDC keys may be renamed, lost in async contexts, or overwritten.
- Root/additivity/appender refs increase log counts or send logs to the wrong sink.
- Level/filter changes prevent error events from reaching the console/file.
- Tests using exact strings/line numbers break even though the actual contract is still valid.

To make regressions less flaky, separate:

1. **Contract assertions:** event code, level, exception type/cause, safe metadata, count, and routing.
2. **Formatter assertions:** JSON parsing/schema, stack trace presence, redaction, newline escaping.
3. **Environment assertions:** appender activated, config profile, destination, and ingestion path.
4. **Nonfunctional checks:** performance, queue behavior, retention/audit requirements.

For output snapshots/golden files, only snapshot stable parts or normalize timestamps, thread IDs, and stack frame locations using clear rules. Do not normalize away the very fields you need to test, such as exception type or trace ID, which would hide regressions.

## 19. Runbook When an Exception Is "Missing from Logs"

1. **Verify the real error occurred:** status/metrics/traces, exception handler, business outcome. Do not treat the absence of an ERROR line as the absence of an error.
2. **Check where the exception was caught:** did a handler swallow/recover it, does the framework have another global exception handler, was it wrapped in `CompletionException`/`ExecutionException`?
3. **Inspect the logger call:** was the right overload used to attach `Throwable`, are the message template/structured fields empty?
4. **Check effective log level and filters:** was the event created, is there a `DENY` at the logger/turbo filter/appender?
5. **Check logger hierarchy/additivity:** did the event go to a parent/different appender or get logged twice?
6. **Check async queue/sink:** were logs dropped, not yet drained, file unwritable, stdout/agent congested?
7. **Check collector/index:** parser error, missing JSON field, wrong namespace, clock skew, or ingest delay?
8. **Check redaction/security:** was the message masked or dropped by policy due to sensitive data, and is that policy correct?
9. **Reproduce with a test case:** trigger an exception with a unique ID/test metadata in an allowed environment and trace hop by hop.
10. **Prevent recurrence:** add a regression test at the exact failure layer and dashboard metrics; avoid adding logs indiscriminately and creating noise.

If the issue only appears after deployment, check the active logging profile, versions/dependencies, and loaded config—not just the config file in the repository. An application with multiple SLF4J providers or the wrong binding may emit startup warnings and route through a different backend than expected.

## 20. Pre-Signoff QA Checklist for Exception Logging

- [ ] Are there tests for success, failure, handled/recovered, expected rejection, and retry exhausted paths?
- [ ] Are log levels and logger names asserted from actual events, not just keyword searches in strings?
- [ ] Does every required error event have the right event code, request ID/correlation ID, and outcome?
- [ ] Is `Throwable` attached to the event via the right API overload, not just `exception.getMessage()`?
- [ ] Are cause chains and suppressed exceptions preserved at both model and layout layers per policy?
- [ ] Are there event count tests and negative assertions to catch duplicate logs?
- [ ] Are parent/additivity/routing tested when multiple appenders/sinks exist?
- [ ] Is redaction tested with a canary secret across message, `Throwable`, cause, suppressed, and MDC?
- [ ] Is structured JSON parseable; do newline/control characters avoid creating log injection?
- [ ] Does async logging have proper deadlines/flushes rather than relying on fixed sleeps?
- [ ] Do tests clean up appenders, levels, filters, MDC, and global streams in `finally`?
- [ ] Are tests independent of real timestamps, stack trace line numbers, and test suite order?
- [ ] Are there integration/end-to-end tests when proving logs reach files/collectors/indexes is required?
- [ ] Is there monitoring when the appender, collector, or queue itself fails?
- [ ] For audit/security events, are storage/access permissions and retention tested separately?
- [ ] Do test results clearly distinguish **logger call**, **event emitted**, **sink received**, and **backend searchable**?

**Completion criteria:** You can write a test that triggers an exception with a cause, use `Handler`/`ListAppender` to assert exactly one error event with the full `Throwable`, test the no-log cases, protect sensitive data, and additionally verify async sinks when needed.

## 21. Self-Check Questions

1. Why does `assertThrows(...)` not prove that an exception was logged?
2. What is the difference between `logger.error("failed: {}", ex.getMessage())` and `logger.error("failed", ex)`?
3. In JUL, how do you retrieve the `Throwable` from a `LogRecord`?
4. Why should you assert exception/cause via API before comparing the entire formatted stack trace?
5. On which object's `getSuppressed()` does a suppressed exception reside?
6. A service recovers successfully after a cache timeout: must it log `ERROR`?
7. Why does an in-memory `ListAppender` not prove that a file/collector received the event?
8. When both the root logger and a child logger have appenders, how can additivity affect log counts?
9. How do you verify that an exception containing a dummy token does not leak into a JSON encoder's stack trace?
10. What observation mechanism should replace `Thread.sleep(100)` in async logging tests?
11. In `CompletableFuture`, when an exception is wrapped by `CompletionException`, how do you recover the cause in a test?
12. Why can logging an exception at every layer of a request path create false alerts?
13. How can a test that only checks the count of `ERROR` logs miss request ID leakage across threads?
14. If an `ERROR` event has been written to the console but cannot be found in the index, which hops need to be checked?
15. Why should a failing logger not log a new exception to that same failing appender?

## References

- [Java SE 17 — Throwable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html) — cause, stack trace, and suppressed exceptions.
- [Java SE 17 — LogRecord](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/LogRecord.html) — `getThrown()`, level, and logger name.
- [Java SE 17 — Logger](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Logger.html) — `log(Level, String, Throwable)` and effective level.
- [Java SE 17 — Handler](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Handler.html) — `publish` and filter/handler behavior.
- [Logback Manual — Architecture](https://logback.qos.ch/manual/architecture.html) — hierarchy, additivity, and selection rule.
- [Logback Manual — Filters](https://logback.qos.ch/manual/filters.html) — appender filters and TurboFilter.
- [Logback Manual — Appenders](https://logback.qos.ch/manual/appenders.html) — appender/sink and async behavior.
- [SLF4J Manual](https://www.slf4j.org/manual.html) — parameterized logging, Throwable handling, and API.
- [JUnit 5 User Guide](https://junit.org/junit5/docs/current/user-guide/) — writing and organizing tests.
- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html) — sensitive data, log injection, and log protection.
