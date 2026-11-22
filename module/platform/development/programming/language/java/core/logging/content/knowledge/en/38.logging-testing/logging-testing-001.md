# Testing Logger Invocations in Java (Testing logging)

## 1. Goal: What Does "Logger Was Called" Mean?

When a unit test requires **testing that a logger was called**, the first question is: **do you need to verify a call to the Logging API, an event accepted by the backend, or data actually written to the destination?** Those three meanings are different.

For example, in a service:

```java
// Illustrative snippet, depends on the logger and business variables.
logger.info("order_created id={}", orderId);
```

There are three boundaries:

1. **Invocation** — did the application code call `logger.info(...)` with the expected template and arguments? This can be checked using Mockito/a mock logger. This **does not prove** that the event was written.
2. **Emitted event** — did the logger/backend, after evaluating levels and filters, create and send the event to a test handler/appender? You can capture `LogRecord` (JUL) or `ILoggingEvent` (Logback).
3. **Output/delivery** — what data did the console, file, JSON encoder, async queue, or collector receive? An integration test at the actual destination is required, because a successful call does not prove the file or collector durably stored it.

This lesson belongs to the **Testing logging** topic and focuses on choosing the right test, writing reliable tests, avoiding coupling to implementation details, and avoiding situations where tests pass while no logs are actually produced.

After this lesson, you will be able to:
- Use `Mockito.verify(...)` to check logger invocations by count, level, template, and arguments.
- Write a **standalone** Java 17+ example using a JUL `Handler` to capture events and distinguish invocation from emitted events.
- Integrate JUnit 5 + Logback `ListAppender` to assert level/logger/message/exception/context.
- Understand the impact of levels/filters, SLF4J backends, parameterized logging, async logging, and parallel test execution.
- Decide when to test logging and when to test business behavior instead of logger internals.
- Test what must not be logged, such as tokens/passwords or sensitive data, without putting real secrets into tests.

## 2. Choosing the Right Test Target

| What to prove | Level | How to do it | What it does not prove |
| --- | --- | --- | --- |
| Code calls `info("...", args)` once | Unit | Mockito mock/spy of injected `org.slf4j.Logger` | Whether the backend wrote the event |
| `warn/error` is not called on the success path | Unit | `verify(..., never())` or event assertions | That the entire system logs no warnings |
| INFO event has the right template, parameters, throwable | Unit/integration | JUL `Handler` or Logback `ListAppender` | Whether the file or collector stored it |
| File/console contains valid schema JSON | Integration | Test encoder + appender in a temp directory / test sink | That all production requests are always logged |
| Async event reaches destination after worker | Integration | Wait for event with timeout, flush/drain per backend | Durability guarantee on process crash |
| Mandatory audit log is stored safely | Integration/E2E | Real/simulated audit write path, ack, retention, and permissions | That `verify(logger)` alone is sufficient |

**Recommendation:** if a log is a required contract for operations or security, prefer testing the **event** and stable fields rather than only testing a specific logger method. If you genuinely need to know whether code calls a contract-defined API wrapper, mocking is a simple and fast option.

Avoid turning every `DEBUG` call into a mandatory assertion. If a test fails whenever diagnostic log text changes while business behavior remains correct, the test is coupled too tightly to the implementation.

## 3. Distinguishing APIs, Backends, and Test Configurations

Common components in the Java ecosystem:
- **JUL**: `java.util.logging.Logger`, `LogRecord`, `Handler`, `Filter`; built into the JDK.
- **SLF4J**: `org.slf4j.Logger` is a facade/API. When mocking an SLF4J logger with Mockito, you are testing methods on this interface; **no real backend is needed to verify invocation**.
- **Logback Classic**: a backend commonly paired with SLF4J; provides `ch.qos.logback.classic.Logger`, `ILoggingEvent`, `ListAppender`.
- **Log4j 2 Core**: another backend, with its own appender/filter configuration and `LogEvent`. You cannot cast a Log4j Logger to a Logback Logger.
- **Spring Boot**: integrates logging configuration and `OutputCaptureExtension` for console tests; capturing depends on backend/console configuration.

Overview of the processing flow:

```text
Business code
    |
    v
Logging API: logger.info(...)
    |
    +--> Mockito mock: records method invocation, without going through a real backend
    |
    +--> Real logger: level/filter
                    |
                    v
                 LogEvent
                    |
                    v
              Appender/Handler
                    |
                    v
              Console/File/Queue
                    |
                    v
                  Collector
```

When Mockito `verify` passes, the only certainty is that **the mock received the matching call**. When `ListAppender` sees an event, you can confirm the event reached this appender, **not** automatically infer that every other appender received it as well.

### Example: Same Call, Different Outcomes

Suppose the code calls `logger.info("order_created")`:
- **Mock** logger: Mockito records the call, even without a backend.
- Real logger at **WARN** level: `info` is called in code, but the INFO event may be discarded before event creation.
- Real logger at **INFO** level, appender threshold **WARN**: the backend may create the event, but this appender does not receive it.
- Real **async** logger: the event may be enqueued, but has not reached the sink at the moment the test asserts.
- Real logger with **file appender I/O error**: the call may return, yet the file does not contain the event.

Therefore, using `verify(logger).info(...)` to prove "it was written to the file" is an invalid assertion.

## 4. Using Mockito to Verify Logger Invocations

### 4.1. Designing for Testability: Injecting the Logger When Appropriate

For code that needs its event-emission policy tested, you can pass `org.slf4j.Logger` via the constructor or inject a small application-owned interface. Example using **JUnit 5 + Mockito + SLF4J API**, split into two files in the same package or placed under test sources according to Java conventions:

File **`OrderService.java`**:

```java
import org.slf4j.Logger;

public final class OrderService {
    private final Logger logger;

    public OrderService(Logger logger) {
        this.logger = java.util.Objects.requireNonNull(logger);
    }

    public void createOrder(String orderId) {
        if (orderId == null || orderId.isBlank()) {
            throw new IllegalArgumentException("Invalid orderId");
        }

        // Minimal example: a real application would also contain order creation business logic.
        logger.info("order_created id={}", orderId);
    }
}
```

File **`OrderServiceTest.java`**:

```java
import org.junit.jupiter.api.Test;
import org.slf4j.Logger;

import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.Mockito.*;

class OrderServiceTest {
    @Test
    void invokesInfoExactlyOnce() {
        Logger logger = mock(Logger.class);
        OrderService service = new OrderService(logger);

        service.createOrder("42");

        verify(logger, times(1))
                .info("order_created id={}", "42");
    }

    @Test
    void doesNotLogInvalidOrderId() {
        Logger logger = mock(Logger.class);
        OrderService service = new OrderService(logger);

        assertThrows(IllegalArgumentException.class,
                () -> service.createOrder(" "));

        verifyNoInteractions(logger);
    }
}
```

**Dependencies:** `slf4j-api` and JUnit Jupiter/Mockito test dependencies; these files **do not compile with the plain JDK alone**. Use the versions managed by your project to avoid conflicts. When mocking `Logger` with Mockito, Logback is not strictly required just to call `verify`, though other parts of the application may require a provider.

Explanation:
1. `mock(Logger.class)` creates a mock of the SLF4J interface, writing nothing to console or file.
2. `service.createOrder("42")` executes the code under test.
3. `verify(logger, times(1)).info("order_created id={}", "42")` verifies **exactly one invocation**, including the template and argument at the call site.
4. `verifyNoInteractions(logger)` makes sense for the invalid-input branch because the service is designed not to touch the logger in that branch.
5. If you call `verify(logger).info(...)` without specifying a mode, Mockito checks for one invocation by default. `times(n)` makes the expected count explicit.

**You do not have to inject `Logger` into every class.** If a class conventionally uses a `private static final` logger, changing the design solely to mock a `DEBUG` call is usually not worth it. Consider capturing events in a backend test or testing business behavior instead.

### 4.2. `verify`, `never`, `atLeastOnce`, and `ArgumentCaptor`

Common verification modes:

```java
// The following snippets assume "logger" is a mocked SLF4J Logger.
verify(logger, times(1)).info("order_created id={}", "42");
verify(logger, never()).warn("unsafe_input");
verify(logger, atLeastOnce()).info(anyString(), any());
```

**Overload note:** SLF4J has multiple overloads (`info(String)`, `info(String,Object)`, `info(String,Object,Object)`, varargs). The test must verify **the exact overload called by production code**. A two-argument call is interpreted differently from an argument array or a fluent builder.

`ArgumentCaptor` is useful when arguments are structured or when only specific fields need checking:

```java
import org.mockito.ArgumentCaptor;

ArgumentCaptor<String> template =
        ArgumentCaptor.forClass(String.class);

// Illustration with a mock logger, after the code has emitted an info(String) call.
verify(logger).info(template.capture());
org.junit.jupiter.api.Assertions.assertTrue(
        template.getValue().startsWith("event="));
```

This is a **standalone integration snippet** that is only valid when production calls the `info(String)` overload. Do not copy it into code that uses `info(String,Object)` and expect the captor to match a different signature.

Avoid overusing `verifyNoMoreInteractions`, because adding a new diagnostic log statement will break the test even though the important contract remains intact. Use it when the goal is to strictly constrain all interactions, not by default.

### 4.3. `isInfoEnabled()` and Mock Defaults

If production code has a guard:

```java
if (logger.isInfoEnabled()) {
    logger.info("details={}", buildSummary());
}
```

A Mockito mock returns `false` by default for booleans when unstubbed. Consequently, the `info` call **never happens**, even when the service logic matches the intended condition. To test the enabled branch, stub it:

```java
when(logger.isInfoEnabled()).thenReturn(true);
```

For the SLF4J 2.x fluent API, `logger.atInfo()` returns a `LoggingEventBuilder`. A mock usually does not automatically provide a builder with real behavior; you must stub the builder/chain or switch to an integration test that captures events. **Do not verify `logger.info(...)` if production uses `logger.atInfo().log(...)`:** they are two different API call paths.

### 4.4. Why You Should Not Mock `LoggerFactory` Indiscriminately

A common pattern:

```java
private static final Logger LOG =
        LoggerFactory.getLogger(OrderService.class);
```

The logger is initialized at class-loading time; a test that statically mocks `LoggerFactory` **after the class has already been initialized** usually cannot replace the field's value. Trying to mutate a `private static final` field via reflection or replacing the root logger can cause flaky tests and affect parallel suites.

There are three reasonable options:
- If logging is an important business contract, inject an application-owned logging/audit facade.
- If you want to verify real events, attach an appender/handler to the actual logger the class uses.
- If the log is non-essential, test the service's behavior and omit logger-call assertions.

## 5. Standalone Java 17+ Example: Capturing `LogRecord` with JUL

This example uses only the JDK, requiring no Mockito, JUnit, or SLF4J. It demonstrates that **a call in code** and **an event actually reaching a handler** are two different things.

Create file **`LoggerInvocationDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class LoggerInvocationDemo {
    static final class MemoryHandler extends Handler {
        private final List<LogRecord> events = new ArrayList<>();

        @Override
        public synchronized void publish(LogRecord record) {
            if (isLoggable(record)) {
                events.add(record);
            }
        }

        @Override public void flush() {}
        @Override public void close() {}

        synchronized List<LogRecord> snapshot() {
            return List.copyOf(events);
        }
    }

    static void createOrder(Logger logger, String orderId) {
        logger.log(Level.INFO, "order_created id={0}", orderId);
    }

    public static void main(String[] args) {
        Logger logger = Logger.getAnonymousLogger();
        logger.setUseParentHandlers(false);
        logger.setLevel(Level.INFO);

        MemoryHandler capture = new MemoryHandler();
        capture.setLevel(Level.ALL);
        logger.addHandler(capture);

        try {
            createOrder(logger, "42");
            List<LogRecord> observed = capture.snapshot();
            if (observed.size() != 1) {
                throw new AssertionError(
                        "Expected one emitted INFO record");
            }

            LogRecord event = observed.get(0);
            if (event.getLevel() != Level.INFO
                    || !"order_created id={0}".equals(
                            event.getMessage())
                    || event.getParameters() == null
                    || event.getParameters().length != 1
                    || !"42".equals(event.getParameters()[0])) {
                throw new AssertionError(
                        "Unexpected record fields");
            }

            System.out.println(
                    "captured_info_events=" + observed.size());
            System.out.println("level=" + event.getLevel());
            System.out.println("template=" + event.getMessage());
            System.out.println(
                    "parameter=" + event.getParameters()[0]);

            logger.setLevel(Level.WARNING);
            createOrder(logger, "43");
            if (capture.snapshot().size() != 1) {
                throw new AssertionError(
                        "INFO must be filtered by logger level");
            }
            System.out.println(
                    "after_info_disabled=" + capture.snapshot().size());
        } finally {
            logger.removeHandler(capture);
            capture.close();
        }
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac LoggerInvocationDemo.java
java LoggerInvocationDemo
```

**Exact standard output:**

```text
captured_info_events=1
level=INFO
template=order_created id={0}
parameter=42
after_info_disabled=1
```

### What the Output Means

1. `createOrder(logger, "42")` calls `Logger.log(Level.INFO, String, Object)`. With logger level `INFO` and handler level `ALL`, one `LogRecord` reaches `MemoryHandler`.
2. `LogRecord.getMessage()` holds the **template** `order_created id={0}`, not the text with `{0}` substituted by a `Formatter`. Parameter `42` is in `getParameters()[0]`; the test verifies both separately.
3. `logger.setLevel(Level.WARNING)` then disables `INFO`. `createOrder(logger, "43")` still **calls the log method**, but the logger discards the event, so the handler still has only **one** record.
4. Because of `setUseParentHandlers(false)`, JUL's root `ConsoleHandler` does not print extra lines to stderr.
5. `snapshot()` returns a copy of the list so the test cannot corrupt the internal collection; synchronizing the methods keeps adding/copying safe when multiple threads share the handler. This test runs synchronously, with no async appender.
6. `finally` removes the handler to avoid leaking state when run in a suite; the logger is created privately via `getAnonymousLogger()`, so it does not mutate named loggers used by other parts of the application.

**This tests events received by a handler, not a Mockito call verification.** It is closer to runtime behavior, yet it still **does not prove a file or collector received the log**. When handler filters, levels, or custom formatters are involved, verify semantics at the exact point you want to guarantee.

## 6. JUL in Real Unit Tests

To test a class that uses JUL with a real logger, you can attach an in-memory handler to **that class's exact logger** for the scope of the test.

Procedure:
1. Obtain the logger by name or through an injection mechanism supported by the application.
2. Save `logger.getLevel()`, `logger.getUseParentHandlers()`, and any state that will be modified.
3. Attach a test `Handler` with `Level.ALL`, and set the logger level high enough to allow the events under test.
4. Invoke the business action and collect `LogRecord` instances.
5. Assert level, logger name, template, parameters, `getThrown()`, and key message fields.
6. In `finally`, remove the handler, restore level/parent state, and close the handler.

If the logger has an active `Filter` or other handlers, changing the level alone may not be enough for events to reach the test handler. Only change filters when genuinely necessary, and remember to restore them. Avoid `LogManager.reset()` per test because it affects the **entire JVM**, causing races and stripping handlers from other tests.

### Testing Exceptions

With JUL:

```java
// Integration snippet inside a method handling an exception.
try {
    riskyOperation();
} catch (RuntimeException ex) {
    logger.log(Level.SEVERE, "order_processing_failed", ex);
    throw ex;
}
```

`LogRecord.getThrown()` lets you assert the exception type, whereas a formatter may change how the stack trace is rendered. Prefer asserting the error type/important fields rather than comparing a verbatim stack trace containing source line numbers.

## 7. Logback `ListAppender`: Testing Real Events

With **SLF4J + Logback Classic**, you can use `ch.qos.logback.core.read.ListAppender<ILoggingEvent>` to collect events before a console formatter turns them into text. This approach fits well when production code has a `private static final` logger and you do not want to mock a private field.

Example with **JUnit 5 + SLF4J + Logback Classic**:

```java
import ch.qos.logback.classic.Level;
import ch.qos.logback.classic.Logger;
import ch.qos.logback.classic.spi.ILoggingEvent;
import ch.qos.logback.core.read.ListAppender;
import org.junit.jupiter.api.Test;
import org.slf4j.LoggerFactory;

import static org.junit.jupiter.api.Assertions.assertEquals;

class LogbackEventTest {
    @Test
    void emitsAnInfoEvent() {
        Logger logger = (Logger) LoggerFactory.getLogger(
                "test.order.logging");

        Level oldLevel = logger.getLevel();
        boolean oldAdditivity = logger.isAdditive();

        ListAppender<ILoggingEvent> capture = new ListAppender<>();
        capture.start();
        logger.setLevel(Level.INFO);
        logger.setAdditive(false);
        logger.addAppender(capture);

        try {
            logger.info("order_created id={}", "42");

            assertEquals(1, capture.list.size());
            ILoggingEvent event = capture.list.get(0);

            assertEquals(Level.INFO, event.getLevel());
            assertEquals("test.order.logging",
                         event.getLoggerName());
            assertEquals("order_created id=42",
                         event.getFormattedMessage());
        } finally {
            logger.detachAppender(capture);
            logger.setLevel(oldLevel);
            logger.setAdditive(oldAdditivity);
            capture.stop();
        }
    }
}
```

The example above makes a **direct call to a real logger** to isolate the demonstration. In a business test, replace `logger.info(...)` with the action that triggers the log, and attach `ListAppender` to the logger that the application class actually uses.

Key takeaways:
- `LoggerFactory.getLogger(...)` returns an SLF4J logger; casting to `ch.qos.logback.classic.Logger` only succeeds if **the current provider is Logback Classic**.
- `ListAppender` records `ILoggingEvent` instances, allowing assertions on `getLevel()`, `getFormattedMessage()`, `getLoggerName()`, and for exceptions, `getThrowableProxy()`.
- `setAdditive(false)` prevents events from also propagating to parent appenders, which is useful for local test isolation; it must be restored so other tests are not affected.
- `capture.start()` is called before attaching; `detachAppender`/`stop()` in `finally` prevents retaining memory and events from leaking into subsequent tests.
- `capture.list` should not be read while an async worker is still writing or when multiple tests share the same logger; this example uses synchronous logging.

**Do not treat a failed cast as a Mockito bug.** It indicates that the runtime provider is not Logback or that the classpath is mismatched. If the backend is Log4j 2, use Log4j 2's appender/test utilities instead of Logback's `ListAppender`.

### Events May Not Be Formatted as You Expect

`ILoggingEvent.getMessage()` is typically the template (e.g., `order_created id={}`), while `getFormattedMessage()` returns the string with arguments populated. With JUL, `LogRecord.getMessage()` may contain the `{0}` template and `getParameters()` holds the parameters. Thus, even though both are "testing log content," the inspection APIs differ.

For structured logging (SLF4J 2.x key/value, Log4j 2 JSON layout, MDC), verify individual fields/context on the event or actual JSON output. Matching a single substring does not prove full schema compliance or privacy.

## 8. Spring Boot: Testing Console Text

If the goal is "the application's console output contains the expected message," Spring Boot provides JUnit 5's `OutputCaptureExtension` to capture `System.out`/`System.err`.

Example **integration snippet** requiring Spring Boot test, JUnit Jupiter, AssertJ, and a suitable console appender:

```java
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.boot.test.system.CapturedOutput;
import org.springframework.boot.test.system.OutputCaptureExtension;

import static org.assertj.core.api.Assertions.assertThat;

@ExtendWith(OutputCaptureExtension.class)
class ConsoleLoggingTest {
    @Test
    void containsWarning(CapturedOutput output) {
        // Illustrative only when the backend sends WARN to the console.
        org.slf4j.LoggerFactory.getLogger("test.console")
                .warn("order_retry_scheduled");

        assertThat(output).contains("order_retry_scheduled");
    }
}
```

This approach depends on the logger being configured to output to the console at the appropriate level. It **does not** verify how many times the logger was called in code and can be noisy if other tests also write to stdout/stderr in the same JVM.

Spring Boot documentation notes that capturing JUL/Log4j 2 may require additional configuration because handlers/appenders may hold references to streams other than the ones the extension temporarily swaps. **Do not arbitrarily reset the global `LogManager` in parallel tests** just to capture stdout; prefer local handlers/appenders or isolated test forks.

If you only need to verify events at the logger level, `ListAppender` or a memory handler is usually clearer and more stable than capturing console text.

## 9. Which Assertions Are Valuable?

### 9.1. When Testing API Calls

With a mock logger, assertions can focus on:
- Did the log call use the right API level (`debug`, `info`, `warn`, `error`)?
- Does the template/event code match the contract?
- Were key arguments (ID, error code, outcome enum) passed accurately?
- Did a branch call it exactly once or not at all?
- Did the call happen **after** the successful business action or on the error branch?

Useful test example: when validation fails, the application must call the `WARN` logger with error code `INVALID_ORDER`, and must not call `order_created`.

Limitations:
- Mockito only confirms that the mock object received the call.
- Template formatting, JSON serialization, and schema correctness are not verified.
- A real logger/provider may disable the level or filter out the event.
- If code merely logs a `"success"` string without performing the business logic, a mock test can still pass. **Always pair with business assertions.**

### 9.2. When Testing Events

With `LogRecord`/`ILoggingEvent`:
- `level`, `loggerName`, `message template`, and essential formatted message content.
- Parameters/key-values, error code, `requestId`/trace ID according to the schema.
- `Throwable`/`ThrowableProxy` on error events (rather than only message text).
- Event count within an isolated action.
- Absence of unauthorized secrets, PII, or raw payloads.
- Whether the event actually passes filters/thresholds in the test configuration.

Do not assert the entire formatted string containing timestamps, thread IDs, line numbers, locations, or stack trace text that varies by JVM/build. Timestamps and random IDs should be checked by pattern/type/range rather than a hardcoded value.

### 9.3. When Testing Files/Collectors

If the requirement is "write a JSON event to a file":
1. Create a dedicated temporary directory for the test, and configure the appender and logger in a controllable state.
2. Invoke the business action.
3. Wait for the event to be written and flushed/drained if async; use a contract-appropriate timeout.
4. Parse the JSON against the schema, verify required fields, and ensure dummy secrets do not appear.
5. Close the appender, delete temp files according to the test lifecycle, and restore logger config.
6. For collectors, use a test sink instead of a production endpoint.

Do not use `verify(logger).info(...)` and conclude that a file/collector received the event, and do not treat the mere existence of a file as proof that all events were written.

## 10. Notes on Logger Levels and Filters

A logger can be **called** without emitting an event:

```text
Code: logger.info("ready")
  |
  +--> Mockito mock: invocation is recorded
  |
  +--> Real logger level=ERROR: INFO is discarded
  |
  +--> Real logger level=INFO: event is created
                                 |
                                 +--> appender filter DENY: sink does not receive
                                 |
                                 +--> appender accept: sink receives
```

With JUL, both `Logger.setLevel` and `Handler.setLevel` must be considered. With Logback, logger level, turbo filters, and appender filters are distinct layers. With Log4j 2, filters can be placed at multiple layers.

A test aiming to prove **"DEBUG was called when the feature flag is enabled"** should use a mock if the log call is the contract. A test aiming to prove **"DEBUG does not appear in production"** must use a real backend/config and assert the event/output; you cannot just verify the code did not call `debug`, because the application might call it and let the backend discard it.

Avoid letting tests depend on the root logger level on a developer's machine or CI environment. Place `logback-test.xml` or an appropriate test config in `src/test/resources` and verify that the test runtime classpath actually loads that file. For JUL, use a local logger as in Section 5 if you do not need the entire `LogManager`.

## 11. Async Logging, Parallel Tests, and Wait Conditions

### 11.1. Why Do Tests Fail Intermittently?

An async logger/appender typically places events into a queue, and a worker writes them later. Code might run:

```java
service.process();
assertEquals(1, capturedEvents.size());
```

and fail intermittently because the worker **has not yet transferred the event to the test appender**. Or, if the appender drops events when the queue is full, the event may genuinely be lost.

The right approach:
- With a **mock logger**, `verify` runs after the code calls the method; if the main code itself is async (executor/future), wait for the log-triggering task to finish.
- With a **real async appender**, use a `CountDownLatch`, a signaling test appender, polling with a deadline, or backend-specific flush/drain APIs. Wait for the event to reach the sink rather than sleeping an arbitrary duration.
- Set a finite timeout with a clear failure message; never wait indefinitely and hang CI.
- Distinguish "not yet arrived" from "dropped" when the queue is full or the event was filtered.
- If a test needs to verify shutdown/flush behavior, make it a separate integration test rather than mixing it into a mock unit test.

**Do not use `Thread.sleep(100)` and assume the event has been written.** On a slow CI machine, queue or scheduler latency can be longer.

### 11.2. Global Logger State Can Contaminate Other Tests

The following operations commonly affect multiple tests in the same JVM:
- Changing the root level or attaching an appender/handler to the root logger.
- Swapping `System.out`/`System.err` or calling `System.setProperty` for the logging backend.
- Calling `LogManager.reset()` or reconfiguring a shared `LoggerContext`.
- Attaching a `ListAppender` to a fixed-name logger across multiple tests running in parallel.
- Setting MDC/ThreadContext and forgetting to clear/restore it.

Mitigations:
1. Use dedicated loggers or test contexts whenever possible.
2. If you modify levels/filters, save the old values and restore them in `finally`.
3. Detach/stop appenders and remove/close handlers immediately after the test.
4. Restore old MDC state or clear test-owned keys; pay attention to context propagation across executors and virtual threads.
5. For integration tests that must alter global config, consider running in a separate fork/process or disabling parallel execution.
6. Do not assert total log counts from frameworks/SDKs while other threads may still be logging.

**`ListAppender` holds a list of events**, not a built-in thread-safe synchronization mechanism for multiple concurrent writers. Under async or parallel execution, ensure thread-safe collection, snapshotting, and a clear deadline before asserting.

## 12. Testing Exceptions and Error Branches

A logger being called inside a `catch` block does not prove the code handled the exception properly. You should also test:
- The business exception is thrown or returned according to the contract.
- `WARN`/`ERROR` includes a valid error code and ID.
- The `Throwable` is passed to the logging API using the proper overload, not merely concatenated via `ex.getMessage()`, which loses the stack trace.
- No misleading `"success"` log appears on the error path.
- No secrets leak in exception messages, arguments, MDC, or formatted output.

Conceptual example for SLF4J:

```java
// Illustrative integration snippet in a service.
try {
    saveOrder(order);
} catch (RuntimeException error) {
    LOG.error("order_save_failed orderId={}", orderId, error);
    throw error;
}
```

Note SLF4J's overloads with arguments and `Throwable`: use the right API/version; `error` is treated as a throwable by SLF4J in the matching overload, while `orderId` is the argument. When verifying a mock, match the exact method signature and matchers; in integration tests, inspect `ILoggingEvent.getThrowableProxy()` rather than requiring a full stack trace string comparison.

If a library logs on your behalf—such as an HTTP filter, job framework, or transaction manager—test **events at that real logger/backend**; do not verify a mock logger that the application never uses.

## 13. Testing Privacy and What Must Not Be Logged

Testing logging also requires **negative assertions** on data:
- Do not log passwords, tokens, `Authorization` headers, cookies, full request/response bodies, or payment details.
- Do not log raw user input containing CR/LF that could forge log lines.
- Do not pass DTOs full of sensitive fields into `toString()`.
- Do not copy the entire MDC/headers without an allowlist.
- Do not log user IDs/emails unless there is a valid purpose and compliant policy.

Test with **dummy canaries**, never real credentials:
1. Create a dummy payload containing `token=TEST_ONLY_SECRET`.
2. Execute both success and error code paths.
3. Capture the event or formatted output after the encoder.
4. Assert that the canary **does not appear**, and identifier fields conform strictly to the approved schema.
5. If there are multiple appenders or collectors, check **all relevant output paths**.

Checking `verify(logger).info("...", safeField)` alone is insufficient: another logging interceptor might still log the request body, or another appender with a `%X` pattern might write sensitive MDC keys to a file. When security or privacy is the goal, write integration tests reaching the end of the pipeline.

## 14. Choosing a Solution by Scenario

| Scenario | Best testing approach | Notes |
| --- | --- | --- |
| Service has an injected logger and needs to verify INFO called once | Mockito `verify` | Fast; verifies invocation only |
| Class uses `private static final Logger` | Logback `ListAppender` / JUL `Handler` | Avoids reflection hacks on static final fields |
| Want to test that INFO is filtered at WARN | Event capture with real level config | Mocks do not simulate backend filtering |
| Want to test template, MDC, throwable | Capture `ILoggingEvent` / `LogRecord` | Inspects fields without depending on console format |
| Want to test JSON output and masking | Encoder/appender test | Parse JSON; test with canaries |
| Want to test exact console text in Spring Boot | `OutputCaptureExtension` | Only when a matching console backend is active |
| Want to test async delivery/flush | Integration test with sink and deadline | Not just `verify` |
| Want to test order-creation business logic | Assert return value/DB/collaborator calls | Logging is a supplementary assertion if needed |
| Want to prove durable audit logging | Test audit pipeline/transaction | A logger call is an insufficient condition |

In general, keep **few unit tests tightly coupled to log text**; instead, test only events mandated for operations, safety, or compliance, treating routine diagnostic logs as implementation details. For systems requiring a stable log structure, maintain schema and integration tests rather than merely verifying call counts.

## 15. Common Mistakes and How to Fix Them

| Mistake | Why it is wrong | How to fix |
| --- | --- | --- |
| `verify(logger).info(...)` and concluding the file was written | A mock does not go through the backend | Test the appender/file/collector separately |
| Attaching a handler while logger level is WARN, INFO events are dropped | No record is emitted to capture | Set the test level explicitly or test filtering behavior |
| Using a mock Logger when code has an `isInfoEnabled()` guard | Mock boolean defaults to false | Stub the guard for the branch under test |
| Verifying `info(String)` overload while code calls `info(String,Object)` | Mockito matches a different signature | Verify template and arguments with the exact overload |
| Mocking `LoggerFactory` after the static logger initialized | Does not replace the cached field | Inject an abstraction or capture real events |
| Modifying the root logger in parallel tests | Contaminates other tests | Use isolated loggers/contexts and clean up |
| Forgetting to detach/stop `ListAppender` | Memory leak, captures events from later tests | Clean up in `finally` |
| Reading `capture.list` before async completion | Race condition / flaky test | Wait on event arrival + timeout |
| Comparing full strings with timestamps/threads/stack traces | Output varies across environments | Assert stable fields |
| Asserting that every DEBUG call must appear | Logs are legitimately disabled by levels/filters | Clarify whether you are testing invocation or emission |
| Overly broad `verifyNoMoreInteractions` | New logs unnecessarily break tests | Constrain only important interactions |
| Using console capture for Log4j/JUL and seeing no output | Streams were bound before capture started | Configure backend or use event capture |
| Test passes because only `logger.info` was called instead of service logic | Does not test the business path | Invoke the real code under test |
| Mock provider mismatch or Logback cast failure | Runtime backend is not Logback | Use test utilities matching the actual provider |
| Checking only the message and ignoring sensitive data in MDC | Can leak via layout/pipeline | Test all event fields and final output |

## 16. Checklist for Reliable Logging Tests

- [ ] Clearly identify the goal: **API invocation**, emitted event, or output/delivery.
- [ ] Use the right API: JUL, SLF4J, Logback, or Log4j 2; check backend/version.
- [ ] With Mockito, verify the exact overload, template, arguments, count, and guards.
- [ ] With handlers/appenders, configure levels/filters accurately and capture events from **the logger of the code under test**.
- [ ] Include business assertions; do not test logging instead of the primary outcome.
- [ ] For exceptions, check the error code and throwable separately; avoid full stack trace strings.
- [ ] For MDC, assert only approved fields; clean up the context.
- [ ] Test privacy/log injection using dummy data at the actual output boundary.
- [ ] For async logging, use a deadline and sink signal; do not use fixed `Thread.sleep`.
- [ ] Restore level, additivity, handlers/appenders, system/global state, and temp files.
- [ ] Do not mutate the shared root logger in parallel suites without isolation.
- [ ] Run in CI with a test runtime logging config matching the design, without relying on IDE defaults.

## 17. Practice Exercises

1. Run `LoggerInvocationDemo`. Explain why `createOrder` is called twice, yet `MemoryHandler` captures only one event when `INFO` is disabled on the second call.
2. In `OrderServiceTest`, change `times(1)` to `times(2)` and observe the test failure. Then call `createOrder` twice to see the difference.
3. Add an `isInfoEnabled()` branch to the service using a mock logger; run the test without stubbing and then after `when(logger.isInfoEnabled()).thenReturn(true)`.
4. With Logback, attach `ListAppender` to a real service's logger. Try `INFO` and `WARN`, and verify `getLevel` and `getFormattedMessage`.
5. Configure a real logger at `WARN` and call `INFO`. Write two tests: one verifying invocation with a mock, and one asserting that no `INFO` event was emitted.
6. In an error branch, emit `LOG.error(..., throwable)` and assert `ThrowableProxy` and the error code without comparing the full stack trace.
7. With an async appender, write a sink test using `CountDownLatch`/timeout; compare it with a fixed-sleep test and explain why sleep is flaky.
8. Create a payload containing `TEST_ONLY_SECRET` and input with newlines; verify that the logger event/output does not record this raw data.
9. Run two parallel tests sharing the same logger name to observe state leakage; fix it using separate loggers, cleanup, or isolated test JVMs.
10. Classify five logging test requirements into invocation, emission, and delivery. Explain why one type of test does not automatically prove the others.

## 18. Key Takeaways

- **"Logger was called"** may mean only an API call; mock verification does not mean an event was created or written to a sink.
- With Mockito, `verify(logger)` checks the exact method, arguments, and invocation count, which is convenient when a logger or logging facade is injected.
- With JUL `Handler` and Logback `ListAppender`, you inspect real **emitted events** and their level, template, parameters, and throwable.
- Logger levels/filters, appender thresholds, async queues, and I/O errors can prevent the same logger call from producing the expected output.
- Stable tests require logger isolation, state restoration, conditional async waiting with timeouts, and avoiding assertions on non-deterministic timestamps or stack traces.
- Do not turn every `DEBUG` log into a brittle test; prioritize business assertions and log events that serve as genuine operational, security, or audit contracts.

### References

- Mockito 5 — `verify`, `times`, `never`, `ArgumentCaptor`: https://javadoc.io/doc/org.mockito/mockito-core/latest/org.mockito/org/mockito/Mockito.html
- JUnit 5 — *User Guide*: https://junit.org/junit5/docs/current/user-guide/
- SLF4J — *User Manual*: https://www.slf4j.org/manual.html
- Logback — *Manual* and appender API: https://logback.qos.ch/manual/appenders.html
- Oracle Java 17 — `java.util.logging.Logger`: https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Logger.html
- Oracle Java 17 — `java.util.logging.LogRecord`: https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/LogRecord.html
- Spring Boot — *Test Utilities / OutputCaptureExtension*: https://docs.spring.io/spring-boot/reference/testing/test-utilities.html
