# Testing Filters in Java Logging Systems

## 1. Why Test Filters?

A logging filter decides **which log events are forwarded or dropped** based on level, source, marker, MDC, content, or application-specific policy. A misconfigured filter can cause critical logs to vanish, diagnostic logs to flood the system, or sensitive information to appear where it is not allowed.

For example, a service wants to drop periodic health-check logs carrying `channel=health` while keeping business events carrying `channel=orders`. The goal of testing is to verify **the exact events received at the appender**, not merely to verify that the filter's condition-evaluation method returns a value.

In Java, there is no single logging filter mechanism shared across all libraries:

- **`java.util.logging` (JUL)** has `java.util.logging.Filter` with `isLoggable(LogRecord)` and its own level/handler mechanism.
- **SLF4J** is a facade. In the hands-on example, **Logback** is the backend that executes loggers, appenders, and `Filter<ILoggingEvent>`.
- **Log4j2** has its own filters and evaluation mechanism; do not use Logback classes directly when an application uses Log4j2.

This article uses **SLF4J + Logback** as a concrete testing model, then explains how to apply the same principles to JUL, async logging, and multi-environment configurations.

### Where Does a Log Event Go?

```text
Business code
    |
    v
logger.info(...), logger.debug(...)
    |
    v
Logger decision (level, possibly Logback TurboFilter)
    |  -- rejected --> no event created/forwarded
    v
ILoggingEvent
    |
    v
Appender A -- filter A --> sink A (console/file/collector)
    |
    +----> Appender B -- filter B --> sink B
```

Multiple appenders can receive the same event. A filter attached to appender A only governs writing at **A**; it does not automatically block appender B. When a filter sits at different points in the pipeline, both the object under test and the conditions for waiting on events change.

## 2. Understanding Levels and Three-Outcome Filters

Do not confuse **logger thresholds** with **appender filters**.

- A logger threshold checks whether an event qualifies to be emitted by the logger. For example, a `WARN` logger normally does not create or forward an `INFO` event.
- An appender filter runs after the event reaches the appender. It can drop the event at that specific sink, even when the logger let it through.
- A Logback `TurboFilter` is consulted earlier in the logging enablement decision. A TurboFilter can affect level checks, so it must be tested separately if the application uses one.

With `ch.qos.logback.core.filter.Filter`, the `decide(event)` method returns one of three `FilterReply` values:

| Result | Meaning in an appender's filter chain | Testing expectation |
| --- | --- | --- |
| `DENY` | Reject the event at that appender | Sink does not receive the event |
| `NEUTRAL` | Undecided; evaluate the next filter | Does not by itself determine accept/drop |
| `ACCEPT` | Accept the event and stop evaluating remaining filters on that appender | If it reached an active appender, the sink receives the event |

If all filters return `NEUTRAL`, the appender continues processing the event using its default mechanism. **An appender filter's `ACCEPT` cannot resurrect an event already blocked by the logger level before reaching the appender.** Conversely, in Logback, an early-stage **TurboFilter** `ACCEPT` decision can alter how logger thresholds are evaluated, so you must not extrapolate from appender filters to TurboFilters.

Filter order is part of the contract: encountering `DENY` or `ACCEPT` stops evaluation of subsequent filters in the same chain; encountering `NEUTRAL` continues. Do not design filters that rely on side effects, because later filters may never be called.

## 3. Building a Test Matrix from Real Requirements

Suppose the requirement is **do not write periodic health-check logs on one appender, while keeping all other logs**. The chosen Logback rule is:

```text
event.MDC["channel"] == "health"  -> DENY
all other cases                   -> NEUTRAL
```

A minimal test matrix:

| Case | Logger level | MDC `channel` | Event level | Filter returns | Event at sink? |
| --- | --- | --- | --- | --- | --- |
| 1 | `DEBUG` | `health` | `INFO` | `DENY` | No |
| 2 | `DEBUG` | `orders` | `INFO` | `NEUTRAL` | Yes |
| 3 | `DEBUG` | missing key | `WARN` | `NEUTRAL` | Yes |
| 4 | `WARN` | any | `INFO` | filter may not be called | No |
| 5 | `WARN` | any | `WARN` | `NEUTRAL/ACCEPT` per filter | Yes |
| 6 | `INFO` | any | `DEBUG` | does not reach normal appender filter | No |

Beyond the happy path, consider edge cases: an empty MDC map, a missing key, an empty value or wrong letter case, combined filters, configuration changes, multiple threads, and appender errors. Do not implicitly add a policy to drop strings like `healthcheck` if the rule only compares against the exact value `health`.

Assertions should stick to **observable output** and the appropriate level of interaction. Unit testing `decide(...)` is fast and easy to analyze, but integration testing through the logger/appender is what proves the filter is wired into the right place.

## 4. Java 17 + JUnit 5 Example: Testing a Logback Appender Filter

This self-contained example uses a small Maven project with Java 17, Logback, and JUnit Jupiter. The tests use an in-memory appender so they do not depend on the console, files, timestamps, or OS scheduling.

### 4.1. Structure and Dependencies

```text
logging-filter-test/
├── pom.xml
└── src/
    └── test/
        └── java/
            └── example/
                └── LoggingFilterTest.java
```

`pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>logging-filter-test</artifactId>
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

The versions above are for a reproducible example and are not meant to claim they are the latest releases. Real projects should use unified dependency management and avoid putting two competing SLF4J providers on the classpath.

### 4.2. Testing the Filter and Decision Chain

Create `src/test/java/example/LoggingFilterTest.java`:

```java
package example;

import ch.qos.logback.classic.Level;
import ch.qos.logback.classic.Logger;
import ch.qos.logback.classic.LoggerContext;
import ch.qos.logback.classic.spi.ILoggingEvent;
import ch.qos.logback.core.AppenderBase;
import ch.qos.logback.core.filter.Filter;
import ch.qos.logback.core.spi.FilterReply;
import org.junit.jupiter.api.Test;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;

import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.CopyOnWriteArrayList;

import static org.junit.jupiter.api.Assertions.*;

class LoggingFilterTest {

    // Only deny events with MDC channel = health.
    static final class DenyHealthFilter extends Filter<ILoggingEvent> {
        @Override
        public FilterReply decide(ILoggingEvent event) {
            String channel = event.getMDCPropertyMap().get("channel");
            return "health".equals(channel)
                    ? FilterReply.DENY
                    : FilterReply.NEUTRAL;
        }
    }

    static final class AcceptAllFilter extends Filter<ILoggingEvent> {
        @Override
        public FilterReply decide(ILoggingEvent event) {
            return FilterReply.ACCEPT;
        }
    }

    static final class DenyAllFilter extends Filter<ILoggingEvent> {
        @Override
        public FilterReply decide(ILoggingEvent event) {
            return FilterReply.DENY;
        }
    }

    // Test sink that only stores events that pass all appender filters.
    static final class MemoryAppender extends AppenderBase<ILoggingEvent> {
        private final CopyOnWriteArrayList<ILoggingEvent> events =
                new CopyOnWriteArrayList<>();

        @Override
        protected void append(ILoggingEvent event) {
            event.prepareForDeferredProcessing();
            events.add(event);
        }

        List<ILoggingEvent> snapshot() {
            return List.copyOf(events);
        }
    }

    // Each test gets its own logger; the appender is detached when finished.
    static final class Rig implements AutoCloseable {
        final Logger logger;
        final MemoryAppender sink;

        @SafeVarargs
        Rig(Level level, Filter<ILoggingEvent>... filters) {
            LoggerContext context =
                    (LoggerContext) LoggerFactory.getILoggerFactory();
            logger = context.getLogger(
                    "example.logging.filter." + UUID.randomUUID());
            logger.setLevel(level);
            logger.setAdditive(false);

            sink = new MemoryAppender();
            sink.setContext(context);
            sink.setName("memory-" + UUID.randomUUID());

            for (Filter<ILoggingEvent> filter : filters) {
                filter.setContext(context);
                filter.start();
                sink.addFilter(filter);
            }
            sink.start();
            logger.addAppender(sink);
        }

        @Override
        public void close() {
            logger.detachAppender(sink);
            sink.stop();
        }
    }

    @Test
    void deniesHealthButKeepsBusinessAndMissingMdc() {
        Map<String, String> before = MDC.getCopyOfContextMap();
        try (Rig rig = new Rig(Level.DEBUG, new DenyHealthFilter())) {
            MDC.put("channel", "health");
            rig.logger.info("health probe ok");

            MDC.put("channel", "orders");
            rig.logger.info("order accepted {}", 42);

            MDC.remove("channel");
            rig.logger.warn("retry scheduled");

            List<ILoggingEvent> events = rig.sink.snapshot();
            assertEquals(2, events.size());

            assertEquals(
                    List.of("order accepted 42", "retry scheduled"),
                    events.stream()
                            .map(ILoggingEvent::getFormattedMessage)
                            .toList());

            assertEquals(Level.INFO, events.get(0).getLevel());
            assertEquals(Level.WARN, events.get(1).getLevel());
            assertEquals("orders",
                    events.get(0).getMDCPropertyMap().get("channel"));
            assertFalse(
                    events.get(1).getMDCPropertyMap().containsKey("channel"));
        } finally {
            if (before == null) {
                MDC.clear();
            } else {
                MDC.setContextMap(before);
            }
        }
    }

    @Test
    void appenderAcceptCannotUndoLoggerLevel() {
        try (Rig rig = new Rig(Level.WARN, new AcceptAllFilter())) {
            rig.logger.info("not created for this appender");
            rig.logger.warn("visible warning");

            assertEquals(
                    List.of("visible warning"),
                    rig.sink.snapshot().stream()
                            .map(ILoggingEvent::getFormattedMessage)
                            .toList());
        }
    }

    @Test
    void acceptStopsRemainingAppenderFilters() {
        // ACCEPT on the first filter ends the chain: DenyAll is not applied.
        try (Rig rig = new Rig(
                Level.INFO, new AcceptAllFilter(), new DenyAllFilter())) {
            rig.logger.info("accepted first");
            assertEquals(
                    List.of("accepted first"),
                    rig.sink.snapshot().stream()
                            .map(ILoggingEvent::getFormattedMessage)
                            .toList());
        }
    }
}
```

Run in the `logging-filter-test` directory with JDK 17 or higher and Maven:

```bash
mvn test
```

The expected result is **3 passing tests** and Maven reporting `BUILD SUCCESS`. Execution time, Maven dependency download lines, and detailed report formatting are not fixed; check `target/surefire-reports/` when an assertion fails.

### 4.3. Interpreting the Test Results

**Test 1 — MDC filtering:** The log call carrying `channel=health` is dropped by `DenyHealthFilter` before reaching `MemoryAppender.append(...)`. The remaining two events are present in the right order, with the right levels and messages, and with/without the corresponding MDC field. Using `"health".equals(channel)` is safe even when the `channel` key is absent.

**Test 2 — logger level:** The `WARN` logger drops the `INFO` call before the `AcceptAllFilter` appender filter has a chance to intervene. An appender filter returning `ACCEPT` cannot bypass an earlier level check.

**Test 3 — filter order:** `AcceptAllFilter` precedes `DenyAllFilter`; after the `ACCEPT` decision, the appender does not need to call the subsequent filter. The test verifies **the event was written**, which is the observable outcome of the filter chain.

**Why is this test stable?** The appender is an in-memory sink that runs synchronously with the logger call; the test reads data after the logger call returns. `CopyOnWriteArrayList` ensures safe collection if multiple producers are added later; it is a good choice for small functional tests, not a good collector for high-load benchmarks. Each logger has a unique name and `additive=false` so the root appender does not mix events from other tests. `try-with-resources` always detaches the appender; MDC is restored in `finally`.

**Example limitations:** The code tests a Logback appender filter. It does not prove that a filter configured in a real config file is active, does not test sending logs over the network, and does not measure async logging latency. Those requirements need appropriate integration tests.

## 5. Reading Return Values Directly: Unit Testing Filter Policies

When filtering logic has multiple branches (for example, conditions on message, marker, user type, or configuration), unit testing `decide(...)` covers edge cases faster than integration testing the entire logging pipeline.

However, a test calling `decide` only verifies **the rule**; it does not prove the filter is attached to the right appender, in the right order, or that a log passed the level/encoder. Combine these layers:

1. **Unit tests:** test an input → `DENY/NEUTRAL/ACCEPT` table, including null, empty string, letter case, and missing config.
2. **Integration tests with an in-memory appender:** verify the logger itself emits the expected events with the right count, level, MDC, and message.
3. **Configuration tests:** initialize a context from the real config and verify the effective logger/appender/filter.
4. **End-to-end tests:** if requirements involve a collector or file, set up an isolated test sink/environment and verify the final output.

Do not write meaningless assertions like "`decide` returns `DENY` so no appender in the application receives the log." Another appender without that filter can still write the event.

### Edge Cases Worth Testing

- Missing MDC key, `""` value, whitespace, or different letter case: verify normalization rules or exact matching.
- Filters depending on formatted messages: distinguish `event.getMessage()` (template) from `event.getFormattedMessage()` (with arguments substituted) at the moment the filter runs.
- Marker-based rules: verify the marker is properly attached to the event and how missing markers are handled.
- Multiple filters: `NEUTRAL` forwards, `ACCEPT` and `DENY` terminate; changing the order can change the result.
- Incompatible logger level: the event may never reach the filter; do not assume a bug in the filter just because a `decide(...)` invocation counter did not increment.
- Multiple appenders: an event may be received by the file appender while being dropped at the console appender.
- Appender not `start()`ed or already `stop()`ped: do not treat the absence of events as proof that the filter works correctly.

## 6. Testing Filters Declared in Logback Configuration

Many applications do not create filters in code, but declare them in `logback.xml` or `logback-spring.xml`. You must test **the configuration that is actually active**, because a correctly named class that is never attached to an appender has no effect.

Example `logback.xml` that only lets the console receive events at `WARN` or above, while the root logger allows from `INFO`:

```xml
<configuration>
    <appender name="CONSOLE"
              class="ch.qos.logback.core.ConsoleAppender">
        <filter class="ch.qos.logback.classic.filter.ThresholdFilter">
            <level>WARN</level>
        </filter>
        <encoder>
            <pattern>%-5level %logger{36} - %msg%n</pattern>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
    </root>
</configuration>
```

With this configuration:

- `logger.info("ready")` is allowed by the root logger, but `ThresholdFilter` on `CONSOLE` rejects events below `WARN`.
- `logger.warn("retry")` and `logger.error("failed")` are received by the console, unless another filter blocks them.
- If a file appender also exists without `ThresholdFilter`, that file may still record `INFO`.

Another filter type is `LevelFilter`, which compares **one specific level** and responds accordingly:

```xml
<filter class="ch.qos.logback.classic.filter.LevelFilter">
    <level>INFO</level>
    <onMatch>DENY</onMatch>
    <onMismatch>NEUTRAL</onMismatch>
</filter>
```

Placing this filter on an appender drops **the exact INFO level**, without automatically dropping `DEBUG` or `WARN`; those levels still depend on the logger threshold and other filters. Unlike `ThresholdFilter`, it is not a way to express a minimum threshold.

### Testing Configuration Without Polluting the Entire Test Suite

An isolated configuration test can:

1. Create a dedicated `LoggerContext` for the test.
2. Use the Logback configurator for your version to load the test `logback.xml`.
3. Attach a capturing appender or inspect the effective filter/level configuration in that context.
4. Emit `INFO/WARN/ERROR` and assert the expected sink behavior.
5. Call `stop()` on the context in `finally`, without mutating the global root logger/context serving other tests.

When using `logback-spring.xml` with `<springProfile>` tags, loading it with a plain Logback parser may not understand Spring Boot extensions. In that case, use an integration test that boots the Spring Boot application with `@ActiveProfiles("test")` (or the target profile), then inspect the effective levels, appenders, and filters. Checking only `Environment.getActiveProfiles()` is not enough to prove the final logs are filtered properly.

If the application can change levels or filters at runtime, write a dedicated test for before–after states and restore all modified settings; avoid letting tests mutate the same root logger in parallel.

## 7. TurboFilter and Differences in Evaluation Timing

A Logback `TurboFilter` is invoked earlier than an appender filter and can decide before an event is even created. It can help avoid event creation overhead for logs guaranteed to be dropped, or enforce a context-wide policy.

To test a TurboFilter, verify these specific scenarios:

| Condition | Expectation to verify |
| --- | --- |
| TurboFilter returns `DENY` | Log call does not reach the appender, even if the normal level allows it |
| TurboFilter returns `NEUTRAL` | Logback continues deciding using the normal level threshold |
| TurboFilter returns `ACCEPT` | Logback can allow the event even if the normal logger threshold is insufficient |
| TurboFilter uses marker/MDC | Condition reads the right context on **the logger-calling thread** |
| One TurboFilter precedes another | Final outcome and decision order match the configured chain |

This differs from **appender filter** `ACCEPT` in Test 2. A TurboFilter integration test should measure the actual outcome of a logger call at a level that would otherwise be blocked, and check enablement state through the corresponding API. Do not assume every backend or facade has the same evaluation order as Logback.

To avoid configuration leaks, TurboFilter tests should use an isolated `LoggerContext` or register and remove the filter in a controlled way. Do not arbitrarily mutate the application-wide TurboFilter list while other tests run in parallel.

## 8. Filters with Asynchronous Logging

In Logback you can use `AsyncAppender`: log events enter a queue, and a worker transfers them to the target appender. **Where the filter is attached determines when it runs:**

```text
Producer thread
    |
    v
Logger level / TurboFilter
    |
    v
AsyncAppender
   |  (Filter attached to AsyncAppender: filters before entering the queue)
   v
Queue
    |
    v
Worker thread
    |
    v
Target appender
   |  (Filter attached to target appender: filters after dequeuing)
   v
Sink
```

Therefore, the same filtering condition can behave differently in terms of queue cost, execution thread, and when the event is observed. An event dropped before the queue usually never enters the backlog; an event dropped at the target appender may still occupy queue space beforehand.

### How to Test Async Filters Reliably

- Use a `BlockingQueue<ILoggingEvent>` or a latch-backed collector in the test appender. Call `poll(timeout)` to wait for **events delivered to the sink**; do not assert immediately after `logger.info(...)`.
- For **DENY** cases, you cannot just wait a short moment and conclude the event will never arrive. Send a **barrier/sentinel event** guaranteed to be accepted on **the same queue and same ordered consumer**; once the sentinel reaches the sink, earlier events that were queued and eligible to reach the sink must have been processed according to the implementation's ordering guarantees. Only then assert the count and the dropped events.
- For queues with discard or overload policies, configure the behavior explicitly and set sufficient capacity for functional tests. If the goal is to test a filter, do not let events be lost due to a full queue and mistake that for a `DENY` result.
- Set finite timeouts and clean up `AsyncAppender.stop()` in `finally`; when testing shutdown, understand `maxFlushTime` and the flush guarantees of your Logback version.
- MDC data must be checked on an event prepared/captured when the producer created the log. `ILoggingEvent.getThreadName()` reflects the event's source thread; if you want to verify which worker actually appended, record `Thread.currentThread().getName()` inside the test appender.

**Especially with MDC:** filtering by `MDC["requestId"]` in an async appender must rely on the event snapshot, not blindly read the worker's `MDC.get(...)` and treat it as the producer's MDC. MDC is normally bound to the current thread; the worker may not have the log-producing thread's context.

## 9. Testing with Multiple Threads and Multiple Appenders

A system handling concurrent requests must avoid filters reading unsynchronized shared state. The simpler, more stateless, and more immutable a filter is, the easier it is to trust.

A test scenario:

1. Create an isolated test logger with `MemoryAppender`, a non-discarding policy, and `N` producers.
2. Each producer emits events with unique IDs such as `P0-0`, `P0-1`, ...; half are tagged `channel=health`, and the rest `channel=orders`.
3. Start producers together using a `CountDownLatch`, wait on all `Future.get(timeout)`; each task sets and cleans up its own thread's `MDC` inside `try/finally`.
4. After the sink has received all allowed events via proper synchronization, compare the **set of received IDs** against the expected set. This detects extra, missing, or duplicate events without relying on cross-producer interleaving order.
5. If both console and file appenders are active, collect results **per appender** to prove the filter only applies to the sink it is attached to.

Do not enforce a global order across producers; the scheduler may validly interleave them. If the backend guarantees FIFO on a single queue and each producer submits events sequentially, you can verify **per-producer order**. In multi-threaded tests, the test appender needs a thread-safe collector and safely published state.

Performance tests must be separated from correctness tests: `CopyOnWriteArrayList` is handy for a handful of events in a unit/integration test, but its copy cost grows sharply when writing hundreds of thousands of events. For benchmarks, use an appropriate collector and load, warm up the JVM, and gather statistics across multiple runs.

## 10. Common Mistakes When Testing Filters

| Symptom | Common cause | Fix |
| --- | --- | --- |
| Filter returns `DENY` but log still appears | Another appender has no filter, logger additivity is enabled, or another config is active | Check the exact logger, each appender, and the active config |
| Filter is never called | Logger level blocked it earlier, appender is not started, or filter is not attached | Check the level layer and lifecycle first |
| Expecting `ACCEPT` to log a `DEBUG` event blocked at the logger | Confusing an appender filter with a TurboFilter | Separate tests by pipeline stage |
| Extra events appear when running the full test suite | Sharing the root appender and missing cleanup | Use unique logger names, `additive=false`, and detach appenders |
| Async tests flake occasionally | Asserting before the worker appends, or queue drops events | Wait on sink/sentinel with a timeout and configure queue explicitly |
| MDC-based filter behaves wrongly across requests | Thread pool reuses threads without restoring MDC | Set and clear MDC at task boundaries |
| Message-based filter misses arguments | Comparing `getMessage()` template against a formatted string | Use the right event field and test parameterized logs |
| Test checks `decide` return value but production does not filter | Filter is not configured or order is wrong | Add an integration test using the real configuration |
| File and console logs differ | Different filters on each sink | Verify each appender, level, and encoder individually |
| Test breaks other loggers | Resetting global `LoggerContext` or changing root between tests | Isolate contexts and restore in `finally` |
| "Hide secrets" config still leaks data | Only lowering log level or filtering a few messages | Verify redaction at the source and final output fields |

### What Not to Do

Do not use `Thread.sleep(500)` as a guarantee that an async filter has finished. Do not catch all `Exception`s in a filter and blindly return `ACCEPT` without a safe fallback decision and error visibility. Do not test data safety by only asserting that a phrase is absent from one appender if another appender could still write it.

Filters should avoid heavy I/O, database queries, repeatedly creating exceptions, depending on volatile time, or mutating the event object against its contract. Filters sit on the logging hot path; if a filter itself becomes slow or hangs, it can directly impact the application or the async queue.

## 11. Security: Filters Do Not Replace Rules Against Logging Sensitive Data

Some applications plan to use filters to drop logs containing passwords, tokens, or personal data. This is an additional defense layer, **not a complete guarantee**:

- A filter placed on one appender may not protect another appender.
- Formatted strings and object serialization can expose data in ways the filtering rule did not anticipate.
- Stack traces, markers, and MDC can carry sensitive data outside `message`.
- Other loggers or other backends may not use that filter.
- If redaction is needed, you need data validation policies at the source, appropriate encoders/structured logging, and tests at the final sink.

Security tests should use **synthetic fake secret strings defined by the test**, emit events through the real path, and verify those strings do not appear in any sink reachable under the contract. Never put real secrets into test fixtures or logs.

## 12. Checklist Before Accepting a Logging Filter

- [ ] Clearly define the purpose: filtering by level, MDC, marker, message, package, or another policy.
- [ ] Know whether the filter is attached to a logger/TurboFilter or a specific appender, and understand evaluation order.
- [ ] Include `DENY`, `NEUTRAL`, and `ACCEPT` cases, and distinguish level gating from filtering.
- [ ] Include positive tests (kept events) and negative tests (dropped events), including null/missing inputs.
- [ ] Unit tests verify the decision; integration tests verify events reach the right sink.
- [ ] Tests isolate loggers, MDC, and lifecycle without disturbing the application-wide root logger.
- [ ] If using async, wait on a sink/sentinel signal with a timeout and explicit queue configuration.
- [ ] If multi-threaded, use a thread-safe collector and do not assert cross-producer ordering.
- [ ] If multiple appenders exist, test each sink and its filtering policy separately.
- [ ] Ensure sensitive data is handled at both the source and the logging pipeline.
- [ ] When changing profiles or logging backends, re-test effective filters and levels.

**Remember:** `FilterReply` is a decision at **one layer** of the logging pipeline; to know whether a filter actually works, you must verify which events reach **the right appender** under the right configuration. Stable tests cleanly separate levels, filters, async delivery, MDC, and per-sink policies.
