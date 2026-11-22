# Level-Based Filtering in Java Logging

## 1. Concept and Purpose

**Level-based filtering** is the mechanism that decides whether a log event continues to be processed or emitted to a destination based on the **severity/level** of the event. For example, in a production environment, an application typically wants to retain `INFO`, `WARN`, and `ERROR`; when investigating an issue, an engineer can enable `DEBUG` for a specific package without enabling DEBUG for all libraries.

A log call passes through multiple stages, often represented as follows:

```text
Business code
  │
  ├─ logger.debug("...") / logger.info("...")
  ▼
Effective level check at logger
  │
  ├─ Blocked: event is not passed down to appender
  ▼
Additional filters (if configured)
  │
  ▼
Appender / handler / destination
  │
  ├─ Destination-specific level filter
  ├─ Other conditional filters (if any)
  ▼
Formatter / encoder / I/O → console, file, collector
```

**Two distinct decisions must be differentiated:**

1. **Does the logger allow emitting an event at that level?** This is usually an early and inexpensive check based on the *effective logger level*.
2. **Does the specific destination accept an event that passed the logger?** A file appender might only keep WARN and above while the console keeps INFO and above. The appender/handler level and its filters govern this step.

API names, check timing, and whether a filter can override the logger level can differ across Logback, Log4j2, and `java.util.logging` (JUL). Do not assume every library shares an identical pipeline: for instance, Log4j2 has global filters that can affect logger-level decisions; Logback has `TurboFilter` at an early layer.

## 2. Log Levels and Threshold Principles

In SLF4J with a backend such as Logback, common levels increase in severity as follows:

```text
TRACE < DEBUG < INFO < WARN < ERROR
```

For example, when **a logger has an INFO threshold** and no special filter intervenes:

| Event level | Passed by logger? | Explanation |
| --- | --- | --- |
| TRACE | No | Lower than INFO |
| DEBUG | No | Lower than INFO |
| INFO | Yes | Matches threshold |
| WARN | Yes | More severe than INFO |
| ERROR | Yes | More severe than INFO |

When set to `WARN`, normally only WARN and ERROR pass through. When set to `DEBUG`, DEBUG/INFO/WARN/ERROR pass through; TRACE remains blocked. This is a **threshold comparison**, not "accept only events named INFO".

**Exact level filtering** is a different rule: an "INFO only" configuration can allow INFO while rejecting DEBUG, WARN, and ERROR at that filter position. Do not confuse *exact match* with *threshold*.

Special levels:

- `ALL`: typically represents allowing all loggable levels in the corresponding mechanism.
- `OFF`: typically represents disabling logging at the corresponding threshold/component.
- Log4j2 also has `FATAL`, which is normally more severe than ERROR. Logback-classic does not have a separate standard FATAL level in the set above.
- JUL uses the names `SEVERE`, `WARNING`, `INFO`, `CONFIG`, `FINE`, `FINER`, `FINEST`, along with `OFF` and `ALL`. Severity ordering across frameworks **must not be compared directly by name or internal numeric values**.

Frameworks or plugins may support custom levels. In such cases, consult the documentation of the active backend for precedence ordering rather than inferring it from string names.

## 3. Logger Levels and Effective Level

Loggers typically have hierarchical names, for example:

```text
ROOT
└── com.example
    └── com.example.payment
        └── com.example.payment.gateway
```

Suppose:

- The root logger is set to `WARN`.
- `com.example.payment` is set to `DEBUG`.
- `com.example.payment.gateway` has no explicit level set.

Under standard level inheritance, the gateway logger has an **effective level of DEBUG**, because it inherits from the nearest ancestor logger (`payment`) that has a defined level. Other loggers under root without an explicit level inherit WARN.

In Logback, the *basic selection rule* is applied at the logger that actually receives the log call, based on that logger's effective level. If a child logger is set to DEBUG and calls `debug(...)`, propagating the event up to the root appender via `additivity` **does not cause root to re-apply its WARN threshold to drop that event**. To make the root appender accept only WARN and above, you need a filter on the appender itself or an appropriate appender layout.

Example:

```text
com.example.payment = DEBUG
ROOT                = WARN

payment.debug(...) ─► passed by payment logger
                    └─► appender inherited from ROOT
                        ├─ no WARN filter: may write DEBUG
                        └─ with ThresholdFilter WARN: blocks DEBUG
```

A common misconception is thinking "root WARN always drops all DEBUG from every child logger". That is not true for appender inheritance in Logback as shown above.

## 4. Level Filtering at the Appender or Handler

The appender/handler controls output emission. This is the right place when different destinations serve different purposes, for example:

- Console keeps `INFO` and above to observe runtime progress.
- Incident archive file keeps `WARN` and above.
- A short-term analysis file specifically for the payment package can enable `DEBUG`.
- An appender dedicated to collecting business logs in a custom format might accept only one event type, though you should consider adding a marker or structured field if level alone does not convey enough meaning.

**Note on blocking order:** if the logger has already blocked DEBUG, adding a DEBUG filter at the appender usually cannot "recover" that DEBUG event. To write DEBUG to a destination, you must verify both the initial logger decision and all filters along the path to that destination.

Threshold examples:

| Effective logger | Destination | Destination threshold | DEBUG | INFO | WARN | ERROR |
| --- | --- | --- | --- | --- | --- | --- |
| DEBUG | Console | INFO | Blocked at destination | Written | Written | Written |
| DEBUG | Alert file | WARN | Blocked at destination | Blocked at destination | Written | Written |
| INFO | Debug file | DEBUG | Blocked at logger | Written | Written | Written |

This table assumes the appender/handler only has the threshold listed above, no other filters, and a healthy sink. "Written" here means **eligible to be sent to the sink**; it does not guarantee the data is persisted on disk or indexed by a collector.

## 5. Logback: ThresholdFilter

The following `logback.xml` configuration example uses Logback-classic, with **a console appender keeping WARN and above**, while the payment package logger enables DEBUG so it can be used by another appender when needed.

```xml
<configuration>
    <appender name="CONSOLE" class="ch.qos.logback.core.ConsoleAppender">
        <filter class="ch.qos.logback.classic.filter.ThresholdFilter">
            <level>WARN</level>
        </filter>
        <encoder class="ch.qos.logback.classic.encoder.PatternLayoutEncoder">
            <pattern>%d{HH:mm:ss.SSS} %-5level %logger - %msg%n</pattern>
        </encoder>
    </appender>

    <logger name="com.example.payment" level="DEBUG"/>

    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
    </root>
</configuration>
```

With log calls from `com.example.payment.CheckoutService`:

```java
// Illustrative snippet for an application with SLF4J and Logback, not a standalone Java file.
private static final org.slf4j.Logger LOG =
    org.slf4j.LoggerFactory.getLogger(CheckoutService.class);

LOG.debug("payment gateway selected");  // passed by logger, blocked by console
LOG.info("checkout accepted");          // passed by logger, blocked by console
LOG.warn("payment is slow");            // accepted by console
LOG.error("payment failed");            // accepted by console
```

**Expected output on the console** is WARN and ERROR, assuming no other filters. Timestamps, logger names, and the actual output location depend on the environment, so a rigid stdout block is not assumed for this integration snippet.

Logback's `ThresholdFilter` blocks events **below** the threshold; for events at or above the threshold, it returns `NEUTRAL` so subsequent filters can continue deciding. This is important to note: "passing the threshold filter" is not a guarantee that all remaining filters are bypassed.

Without an appender threshold, the root appender in the example above could receive DEBUG from child loggers due to additivity even though root has level INFO. You should test the actual behavior when combining filters with special child logger configurations.

## 6. Logback: LevelFilter for an Exact Level

When you need to **log only INFO** to an appender, use `LevelFilter` instead:

```xml
<configuration>
    <appender name="INFO_ONLY" class="ch.qos.logback.core.ConsoleAppender">
        <filter class="ch.qos.logback.classic.filter.LevelFilter">
            <level>INFO</level>
            <onMatch>ACCEPT</onMatch>
            <onMismatch>DENY</onMismatch>
        </filter>
        <encoder class="ch.qos.logback.classic.encoder.PatternLayoutEncoder">
            <pattern>[%level] %msg%n</pattern>
        </encoder>
    </appender>

    <root level="DEBUG">
        <appender-ref ref="INFO_ONLY"/>
    </root>
</configuration>
```

With root at DEBUG, DEBUG, INFO, WARN, and ERROR calls are eligible to pass the logger; **only events that are exactly INFO** are accepted by the appender above. Because `onMismatch=DENY`, WARN and ERROR are also dropped from **this appender**. If you need to store WARN/ERROR in a separate destination, you must configure an additional appender.

### What do ACCEPT, DENY, and NEUTRAL mean?

- `DENY`: rejects the event at that filter layer; the event does not continue along that route.
- `NEUTRAL`: the filter makes no decision; passes control to the next filter or the default rule of the current layer.
- `ACCEPT`: accepts according to the processing rules of the current filter/layer, typically ending evaluation of subsequent filters in the same chain or attachment point.

Different frameworks and filter layers have different mechanics. **ACCEPT at an appender does not reverse an event that was already blocked at the logger earlier**; nor does it guarantee the sink writes successfully. Do not use ACCEPT/NEUTRAL as synonyms for "already printed to console".

Logback also has **TurboFilter**, which evaluates earlier than appender filters. Certain TurboFilter policies returning ACCEPT can affect logger-level selection, so the rule "logger level is an impassable gate" does not hold for all advanced Logback configurations.

## 7. Log4j2: ThresholdFilter, LevelMatchFilter, and Filter Placement

In Log4j2 Core, filters can be placed **globally**, on a **LoggerConfig**, on an **AppenderRef**, or on an **Appender**. The final outcome depends on placement and preceding filters. The Log4j2 documentation explicitly notes that global filters are applied first; depending on the result, they can make subsequent decisions differ from looking at the logger level alone.

Example `log4j2.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<Configuration>
    <Appenders>
        <Console name="CONSOLE" target="SYSTEM_OUT">
            <ThresholdFilter level="WARN"
                             onMatch="ACCEPT"
                             onMismatch="DENY"/>
            <PatternLayout pattern="%d{HH:mm:ss.SSS} %-5level %logger - %msg%n"/>
        </Console>
    </Appenders>
    <Loggers>
        <Logger name="com.example.payment" level="DEBUG"/>
        <Root level="INFO">
            <AppenderRef ref="CONSOLE"/>
        </Root>
    </Loggers>
</Configuration>
```

For events from the payment package with no other filters:

- DEBUG, INFO: do not pass the console's WARN threshold.
- WARN, ERROR, FATAL: eligible to pass to the console.
- The payment package's level differs from root and determines initial logging activation for that package according to the Log4j2 configuration.

In Log4j2, `ThresholdFilter` matches when an event has a severity **equal to or higher than** the selected threshold; `LevelMatchFilter` matches **one exact level**. Example for INFO only:

```xml
<!-- Place inside a compatible Appender -->
<LevelMatchFilter level="INFO"
                  onMatch="ACCEPT"
                  onMismatch="DENY"/>
```

This is only a **filter configuration snippet**, not a complete `log4j2.xml` file. To use it, place it inside an appropriate appender/layer.

**Difference from Logback:** even though both use the name `ThresholdFilter` and common level names, Log4j2's configuration, filter placement, `onMatch`/`onMismatch` defaults, and event flow follow their own contract. Do not copy a Logback XML configuration directly into Log4j2.

## 8. Java Util Logging (JUL): Logger Level and Handler Level

JUL is the `java.util.logging` system bundled with the JDK. Instead of `Appender`, JUL uses `Handler`. A Logger has an effective level, and each Handler has its own level/Filter.

Common JUL levels from highest to lowest:

```text
SEVERE > WARNING > INFO > CONFIG > FINE > FINER > FINEST
```

`OFF` typically disables a logger; `ALL` enables all available levels. Calling `logger.setLevel(null)` makes the logger inherit the effective level of the nearest parent with a concrete level.

A naming difference is that **JUL FINE is close in purpose to detailed logging like DEBUG**, but there is no 1:1 mapping rule for every event when using a logging bridge. If you use an SLF4J/JUL bridge, check which component performs the actual filtering and which backend outputs the logs.

In addition to level checks, JUL allows attaching a `java.util.logging.Filter` to a Logger or Handler to filter based on `LogRecord`. That is an additional step; a Handler filter cannot make visible an event that was already skipped by the logger due to level.

## 9. Complete Java 17 Example: Filtering at Logger and Handler

The following program uses **plain JDK**, requiring no Maven/Gradle or external libraries. The Handler writes directly to `System.out` so the output is deterministic and easy to compare. The example demonstrates in sequence:

1. The logger accepts from `FINE`, but the handler only accepts from `WARNING`.
2. Lowering the handler threshold to `INFO` to also receive INFO.
3. Raising the logger threshold to `WARNING`: INFO is blocked again at the logger.
4. Attaching a Filter that accepts only exact `WARNING`, unlike a threshold.

Save the file **`LevelFilteringDemo.java`**:

```java
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class LevelFilteringDemo {
    private static final Logger LOG = Logger.getLogger("demo.payment");

    private static final class StdoutHandler extends Handler {
        StdoutHandler() {
            setLevel(Level.WARNING);
        }

        @Override
        public void publish(LogRecord record) {
            // Handler guards its own condition for accepting events.
            if (isLoggable(record)) {
                System.out.println(
                    record.getLevel().getName() + " | " + record.getMessage());
            }
        }

        @Override
        public void flush() {
            System.out.flush();
        }

        @Override
        public void close() {
            flush();
        }
    }

    public static void main(String[] args) {
        LOG.setUseParentHandlers(false); // Avoid duplicate output via root handlers.
        StdoutHandler handler = new StdoutHandler();
        LOG.addHandler(handler);

        try {
            System.out.println("A: logger=FINE, handler=WARNING");
            LOG.setLevel(Level.FINE);
            LOG.fine("detail A");            // Blocked by handler.
            LOG.info("order created A");     // Blocked by handler.
            LOG.warning("slow partner A");   // Logged.
            LOG.severe("failed A");          // Logged.

            System.out.println("B: logger=FINE, handler=INFO");
            handler.setLevel(Level.INFO);
            LOG.fine("detail B");            // Still blocked by handler.
            LOG.info("order created B");     // Logged.
            LOG.warning("slow partner B");   // Logged.

            System.out.println("C: logger=WARNING, handler=INFO");
            LOG.setLevel(Level.WARNING);
            LOG.info("order created C");     // Blocked by logger.
            LOG.warning("slow partner C");   // Logged.

            System.out.println("D: exact WARNING filter");
            LOG.setLevel(Level.ALL);
            handler.setLevel(Level.ALL);
            LOG.setFilter(record -> record.getLevel() == Level.WARNING);
            LOG.info("order created D");     // Blocked by filter.
            LOG.warning("slow partner D");   // Logged.
            LOG.severe("failed D");          // Blocked by filter.
        } finally {
            LOG.setFilter(null);
            LOG.removeHandler(handler);
            handler.close();
        }
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac --release 17 LevelFilteringDemo.java
java LevelFilteringDemo
```

**Exact** stdout output:

```text
A: logger=FINE, handler=WARNING
WARNING | slow partner A
SEVERE | failed A
B: logger=FINE, handler=INFO
INFO | order created B
WARNING | slow partner B
C: logger=WARNING, handler=INFO
WARNING | slow partner C
D: exact WARNING filter
WARNING | slow partner D
```

Explanation:

- In **A**, the logger accepts FINE/INFO/WARNING/SEVERE, but the handler at threshold WARNING blocks the first two events.
- In **B**, changing the handler threshold to INFO makes INFO appear; FINE still does not meet the handler threshold.
- In **C**, even though the handler allows INFO, the logger raised its threshold to WARNING, so INFO never reaches the handler.
- In **D**, both logger and handler allow all levels, but `Logger#setFilter(...)` only lets events with `Level.WARNING` pass. Thus SEVERE is also blocked, demonstrating that **exact match differs from threshold**.
- `setUseParentHandlers(false)` disables forwarding to parent handlers, avoiding unexpected lines. The handler formats the message itself so the output has no non-deterministic timestamps.

This example runs on plain JDK and does **not** prove that Logback/Log4j2 share the same API or internal filter ordering. In real applications, configure the logging framework in use and test against the actual backend.

## 10. Choosing Appropriate Thresholds by Environment and Goal

A common policy, not a mandatory standard:

| Environment | Common threshold | Meaning |
| --- | --- | --- |
| Local development | DEBUG or INFO | Observe processing flow during development |
| CI/test | INFO or WARN with per-test logs | Keep failure signals without excessive noise |
| Normal production | INFO | Record operational state and warnings/errors |
| Production during time-boxed investigation | DEBUG for a specific package | Collect extra data for a feature group |
| Production alerting sink | WARN or ERROR | Retain only high-severity events at this sink |

The choice is not simply "production = WARN". Removing all INFO can cause the system to lose important events needed for investigation, such as "request accepted", "job completed", deployment version, or audit events designed at INFO.

Conversely, keeping all DEBUG enabled in production can increase I/O, volume, storage costs, application latency, and the risk of leaking sensitive data into logs. Distinguish **business/audit logs** from routine diagnostic logs, and do not rely solely on level to guarantee mandatory retention.

## 11. Changing Levels in a Spring Boot Application

With Spring Boot using Logback or Log4j2 via the corresponding starter, you can configure logger levels like this:

```properties
# application.properties
logging.level.root=INFO
logging.level.com.example.payment=DEBUG
logging.level.org.springframework.web=WARN
```

These keys adjust levels at the logger scope. If the backend's appender has its own filter, setting DEBUG for the payment package **still does not guarantee** DEBUG will appear in every sink.

With Spring Boot Actuator and the `loggers` endpoint enabled, authorized, and secured, operators can read/change levels while the JVM is running:

```http
GET /actuator/loggers/com.example.payment
```

The response typically shows:

- `configuredLevel`: the level explicitly declared for the logger, which may be `null`.
- `effectiveLevel`: the effective level after inheritance.

Temporarily set DEBUG:

```http
POST /actuator/loggers/com.example.payment
Content-Type: application/json

{"configuredLevel":"DEBUG"}
```

Send `{"configuredLevel":null}` to clear the directly assigned level per the endpoint contract, allowing the corresponding inherited level to apply. This is a **runtime** change and does not automatically modify startup configuration files.

You should restrict access to the configuration-writing endpoint, record who made the change and when, schedule a revert, and avoid enabling DEBUG on root unnecessarily. In a multi-instance system, changing one instance does not apply to all instances by default.

## 12. Performance: Early Filtering and Log Creation Cost

### Logger Filtering and Sink Filtering Are Not Equivalent in Cost

When a logger drops an event at the initial level check, the framework typically avoids creating or passing a full log event. If the logger lets it pass and the appender blocks it later, the system may have already paid the cost of creating the event, capturing context, partial formatting, queuing, and traversing filters.

Therefore:

- Use logger levels to limit overall log volume when low-level events are not needed.
- Use appender/handler levels when **different destinations need different policies**.
- Measure CPU, allocation, queue depth, dropped events, and sink I/O before increasing DEBUG/TRACE volume.
- Do not assume setting a WARN threshold on a file appender makes all DEBUG calls "free" if the logger still has DEBUG enabled.

### Parameterization Does Not Guarantee Expensive Calls Are Deferred

In SLF4J, placeholder syntax helps the framework defer part of message formatting:

```java
// SLF4J snippet: the expensive argument is still evaluated before calling the method.
logger.debug("Snapshot: {}", buildExpensiveSnapshot());
```

Java evaluates `buildExpensiveSnapshot()` **before** calling `debug(...)`, even when DEBUG is disabled. For genuinely expensive computations:

```java
// SLF4J snippet: only build the data when DEBUG is enabled on the logger.
if (logger.isDebugEnabled()) {
    logger.debug("Snapshot: {}", buildExpensiveSnapshot());
}
```

`isDebugEnabled()` reflects loggability at the logger layer per the API/backend contract; additional filters at the appender can still drop the event. Do not treat this flag as proof that the file or collector will definitely receive the event.

In JUL, you can use the overload that accepts `Supplier<String>` so the message is only constructed when the level requires it under JUL's mechanism:

```java
// JUL snippet for Java 17+; logger is java.util.logging.Logger.
logger.fine(() -> buildExpensiveSnapshot());
```

These examples illustrate data-computation cost; they are not three standalone programs. Pay attention to data captured in lambdas and thread safety if production code uses async logging.

## 13. Do Not Use Level as the Sole Security or Retention Policy

Level only expresses **observability priority**, not data sensitivity or legal reliability. Keep in mind:

- `DEBUG` can accidentally contain tokens, cookies, passwords, or personal data. Enabling DEBUG for investigation must be paired with data masking/redaction rules.
- `ERROR` is not automatic proof of a severe incident: an expected business error might be logged as ERROR due to a poor choice.
- `INFO` is not a trustworthy audit log by default. Audit events may require durable storage, access control, integrity checks, and separate retention.
- An alert based on `ERROR` counts can lose signal if a logger/appender is blocking or misconfigured; cross-check with metrics, traces, and alert tests.
- Events filtered out at the source **cannot be recovered** merely by changing a downstream collector's filter.

If the requirement is "store only failed transaction events", level alone may not suffice: you need a structured event type/status or an appropriate marker/attribute. Do not force every business error log to carry ERROR just to satisfy a filter condition.

## 14. Common Mistakes with Level Filtering

| Symptom | Possible Cause | How to Check |
| --- | --- | --- |
| DEBUG missing even though logger is set to DEBUG | Appender threshold INFO/WARN; another filter blocking; config not reloaded | Check effective level and the entire logger → appender path |
| Root set to WARN but DEBUG still appears | Child logger has DEBUG and inherits an appender without a threshold (e.g., Logback) | Check child loggers, additivity, and appender filters |
| Only INFO appears, even ERROR is missing | Using exact `LevelFilter` instead of threshold | Switch to threshold if the goal is INFO and above |
| Changed sink filter but throughput did not improve | Events are still created/queued before the filter step | Measure allocation/queue, consider filtering earlier at the logger |
| INFO logs appear in console but not in file | Console and file use different thresholds/filters | Compare configurations of each appender |
| Logger level shows null | Inheriting from parent | Check effective level |
| Set to WARN but ERROR still missing | Another DENY filter, failing sink, log not emitted, appender not attached | Check internal status, appender, and test event |
| Reverts to INFO instead of DEBUG after restart | Changed runtime level without updating startup source | Check config files and initialization mechanism |
| Enabling DEBUG slows down the application | I/O/queue overloaded, producer blocked, or heavy formatting | Measure CPU, queue, latency, sink throughput |
| Duplicate log lines output | Multiple appenders attached or additivity | Check appender routing and `additivity=false` where appropriate |
| Library logs do not change level as expected | Different logging bridge/backend or wrong logger name | Identify actual backend, logger name, and configuration |
| Missing investigation data after level filtering | Threshold too high or unsuitable retention | Re-evaluate INFO/WARN needs and metric/trace collection paths |

## 15. How to Test Filter Configurations Properly

A reliable test should cover the full matrix of **logger level × appender/handler level × additional filters**.

1. **Create test data covering all levels.** Emit TRACE/DEBUG/INFO/WARN/ERROR or the corresponding JUL level set, each event with a unique ID; know clearly which logger emits each.
2. **Verify thresholds with an expectation table.** For INFO, INFO/WARN/ERROR are eligible; for WARN, WARN/ERROR are eligible. If exact-match is configured, only the specified level should appear in that sink.
3. **Verify inheritance.** Set root to WARN and a child logger to DEBUG; inspect the child's effective level and appender/handler path to avoid false conclusions.
4. **Verify multiple sinks independently.** Console and file may have different rules; confirm events reach the intended sink rather than just "appearing somewhere".
5. **Verify runtime/reload changes.** Change INFO→DEBUG then revert, inspect effective state and actual events; also verify across restarts if persistent configuration is required.
6. **Verify under overload.** When DEBUG spikes, measure latency, queue depth, dropped logs, and I/O; with async logging, do not equate enqueued with durably stored.
7. **Verify sensitive data blocking.** Emit test logs containing no real secrets; confirm masking and sink access permissions still apply even when DEBUG is enabled.

A test case can write concise expectations:

```text
Logger package = DEBUG
Appender console threshold = INFO
Appender file threshold = WARN

DEBUG -> not output to console/file
INFO  -> output to console only
WARN  -> output to console and file
ERROR -> output to console and file
```

If results do not match, check step by step whether the event was created, whether the logger passed it, whether the appender is properly attached, whether any filter blocked it, and whether the sink wrote successfully.

## 16. Key Takeaways

- **Threshold** means "from this level and above"; **exact match** means "only this exact level" at that filter.
- **Effective logger level** controls emission/propagation at the logger layer; appender/handler filters control each destination.
- **Root logger level does not mean a threshold re-applied to every event from child loggers**, especially with additivity and level overrides.
- Logback, Log4j2, and JUL have different APIs, defaults, and filter layers; always check against the **actual backend**.
- Filters only decide event routing; they do not guarantee sink writes, compensate for retention, or replace security policies.
- When debugging production, open levels in a narrow scope, time-box them, monitor cost, and revert.

**Remember:** to understand why a log line is present or missing, check **the logger's emission level**, **the filters along the route to the appender/handler**, and **the actual state of the sink**. These three layers explain most "enabled logging but no logs appear" incidents.

### Technical References

- [Logback — Filters, LevelFilter, ThresholdFilter](https://logback.qos.ch/manual/filters.html)
- [Logback — Logger level, basic selection, and additivity](https://logback.qos.ch/manual/architecture.html)
- [Apache Log4j2 — Filters](https://logging.apache.org/log4j/2.x/manual/filters.html)
- [Oracle Java 17 — java.util.logging.Logger](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Logger.html)
- [Spring Boot — Logging](https://docs.spring.io/spring-boot/reference/features/logging.html)
