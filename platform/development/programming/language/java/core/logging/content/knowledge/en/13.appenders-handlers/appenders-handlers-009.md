# Level-Based Appenders in Java Logging

## 1. What Is a Level-Based Appender?

A **level-based appender** is a configuration pattern where a log destination only receives events matching a specific severity level. In a Java system, you might want:

- `INFO` events to go to the regular log stream;
- `WARN` events to go to the warning stream;
- `ERROR` events to go to the error investigation channel;
- or **all events from `WARN` and above** to be routed to a dedicated risk-monitoring sink.

For example, suppose the application logs:

```text
INFO  event=order.created orderId=ord-17
WARN  event=inventory.low sku=sku-9
ERROR event=payment.failed errorCode=UPSTREAM_TIMEOUT
```

Instead of having every appender output all three lines, you attach a **dedicated level filter to each appender**. The `INFO_ONLY` appender only processes `INFO` lines, `WARN_ONLY` only processes `WARN`, and `ERROR_ONLY` only processes `ERROR`.

In the Java ecosystem, it is important to distinguish:

1. **`Logger` decides whether an event is created/accepted based on its effective level.**
2. **`Appender` decides where and under what conditions an event accepted by the Logger is written.**
3. **`Filter` attached to an appender decides whether to accept only an exact level, a minimum threshold level, or more complex conditions.**
4. **`Encoder`/`Layout` determines the representation of the event**, not its level-based routing.
5. **`additivity` controls forwarding events to ancestor loggers' appenders**, which can cause duplicate logs if misconfigured unintentionally.

This article focuses on **Logback with SLF4J**, because Logback provides the characteristic `LevelFilter` and `ThresholdFilter` classes. At the end, we compare it with `java.util.logging.Handler` and note considerations for other backends. Java examples use JDK 17, SLF4J, and Logback Classic.

## 2. Where Appenders Fit in the Logging Pipeline

A common model looks like this:

```text
Application code:
logger.info(...), logger.warn(...), logger.error(...)
                       |
                       v
                SLF4J API
                       |
                       v
               Logback Logger
                 Level check
                       |
                       v
                 LoggingEvent
                       |
          +------------+------------+
          |            |            |
          v            v            v
      INFO_ONLY     WARN_ONLY    ERROR_ONLY
      LevelFilter   LevelFilter  LevelFilter
          |            |            |
          v            v            v
      Encoder      Encoder      Encoder
          |            |            |
          +---------- log sinks ---------> stdout / file / collector
```

Each appender **has its own filters and encoder**. Even when appenders are all referenced on the root logger, level filtering is evaluated per appender when it receives an event.

For example: Logger `com.example.payment` has an effective level of `INFO`. A `logger.debug("...")` call is dropped at the Logger; it **cannot be "rescued" by an appender configured for DEBUG**. A `logger.error("...")` call is accepted by the Logger; the appenders may receive the event, and each appender's filter decides whether to output it.

**Operational rule:** For a log to be written to a destination, **both the Logger must accept the event and the Appender must accept it**. Do not look at only one of the two configurations.

## 3. The Logback Level Hierarchy

In Logback Classic, the common levels in ascending order of severity are:

```text
TRACE < DEBUG < INFO < WARN < ERROR
```

`ALL` and `OFF` are special configuration values that allow all levels or block all levels; they are not normal event levels for `trace/debug/info/warn/error` calls.

Basic Logger selection rule: a call at level `L` is accepted when `L` has a severity at least equal to the Logger's effective level. For example:

| Logger Effective Level | TRACE | DEBUG | INFO | WARN | ERROR |
| --- | --- | --- | --- | --- | --- |
| `TRACE` | Yes | Yes | Yes | Yes | Yes |
| `DEBUG` | No | Yes | Yes | Yes | Yes |
| `INFO` | No | No | Yes | Yes | Yes |
| `WARN` | No | No | No | Yes | Yes |
| `ERROR` | No | No | No | No | Yes |
| `OFF` | No | No | No | No | No |

This table describes **Logger acceptance**, before considering any Appender or Filter. The level of a parent Logger where an appender is attached **does not re-filter events that a child Logger has already accepted**. A child Logger explicitly set to `DEBUG` can send `DEBUG` records to an appender attached to an `INFO` root logger; to block `DEBUG` at that appender, an appropriate filter must be configured.

When multiple Loggers share a hierarchical name, a Logger without an explicitly set level typically inherits its effective level from the nearest appropriate ancestor. `additivity=true` allows events to be propagated to ancestor appenders. These are two separate mechanisms.

## 4. Two Different Needs: "Exactly One Level" vs. "At or Above a Level"

This is the first question to answer before writing XML.

### 4.1. Accepting Exactly One Level: `LevelFilter`

If the goal is **strictly INFO**, without accepting WARN or ERROR, use `ch.qos.logback.classic.filter.LevelFilter`:

```xml
<filter class="ch.qos.logback.classic.filter.LevelFilter">
    <level>INFO</level>
    <onMatch>ACCEPT</onMatch>
    <onMismatch>DENY</onMismatch>
</filter>
```

This is a **configuration snippet inside a Logback appender**; it is not a standalone `logback.xml` file.

- `level=INFO`: matches the event's level by equality.
- `onMatch=ACCEPT`: lets `INFO` events pass immediately at this filter.
- `onMismatch=DENY`: rejects all other levels.
- `WARN` and `ERROR` are **not** accepted, even though they are more severe than `INFO`.

You can use `LevelFilter` for `WARN`, `ERROR`, or `DEBUG` in the same way. To reject all levels except `ERROR`, set `level=ERROR`.

### 4.2. Accepting a Minimum Level and Above: `ThresholdFilter`

If the requirement is **WARN and above**, use `ch.qos.logback.classic.filter.ThresholdFilter`:

```xml
<filter class="ch.qos.logback.classic.filter.ThresholdFilter">
    <level>WARN</level>
</filter>
```

This is also a **configuration snippet inside an appender**. `ThresholdFilter` rules:

- Events below `WARN`, such as `INFO` or `DEBUG`: `DENY`.
- Events at `WARN` and above, such as `WARN` and `ERROR`: `NEUTRAL`, so subsequent filters can still evaluate them.
- If no other filter blocks them, the appender writes the `WARN`/`ERROR` events that passed the Logger's level check.

**Do not confuse them:** `ThresholdFilter(WARN)` does **not** mean "WARN only". It includes `ERROR` and any events with a level higher than `WARN` in Logback.

### 4.3. Comparison Table

Assuming the source Logger is set to `TRACE` so all common calls reach the filters:

| Event | `LevelFilter(INFO)` (INFO only) | `LevelFilter(ERROR)` (ERROR only) | `ThresholdFilter(WARN)` |
| --- | --- | --- | --- |
| TRACE | Denied | Denied | Denied |
| DEBUG | Denied | Denied | Denied |
| INFO | Accepted | Denied | Denied |
| WARN | Denied | Denied | Accepted |
| ERROR | Denied | Accepted | Accepted |

The table says "Accepted" assuming **no other filter blocks it**. In practice, an appender might still not output anything if it has not started, has an invalid I/O target, or has additional filters configured afterward.

A classic mistake: using `ThresholdFilter` with `INFO` for an `info.log` file and assuming it only contains `INFO`. In reality, that filter lets **INFO, WARN, and ERROR** through. If you need to separate by exact level, use `LevelFilter`.

## 5. FilterReply: ACCEPT, DENY, and NEUTRAL

Logback evaluates regular filters on an appender in **order**. Each filter can return one of three results:

| Result | Meaning |
| --- | --- |
| `DENY` | Rejects the event immediately at this appender; remaining filters are not evaluated |
| `ACCEPT` | Accepts immediately; stops evaluating remaining filters |
| `NEUTRAL` | Undecided; continues evaluating the next filters |

If no filter decides to reject the event, the appender accepts it by default once all other conditions are met.

This matters when an appender has **multiple filters**. If the first filter returns `ACCEPT`, subsequent filters are never consulted—even if a later filter is supposed to block a certain message type or apply an extra condition.

For example, if you need to accept only `INFO` **while still passing through another safety filter**, you can use:

```xml
<filter class="ch.qos.logback.classic.filter.LevelFilter">
    <level>INFO</level>
    <onMatch>NEUTRAL</onMatch>
    <onMismatch>DENY</onMismatch>
</filter>
```

When the event is `INFO`, this filter does not finalize the decision; downstream filters still get a chance to process it. When the event is anything other than `INFO`, it is rejected. The `ACCEPT/DENY` pattern is suitable for a **single filter** and standalone examples, whereas a filter chain requires carefully designed ordering and return values.

Note: An appender filter only controls **events reaching that appender**; it does not replace mandatory data-protection rules at the point where logs are created.

## 6. Example of Level-Based Routing with Multiple Appenders

Suppose the application has the following target channels:

```text
                   Logger (INFO or lower)
                              |
             +----------------+----------------+
             |                |                |
          INFO_ONLY        WARN_ONLY        ERROR_ONLY
        LevelFilter      LevelFilter      LevelFilter
          INFO            WARN             ERROR
             |                |                |
        INFO Channel     WARN Channel    ERROR Channel
```

An `ERROR` event only goes to `ERROR_ONLY`; it does not leak into `WARN_ONLY` if `WARN_ONLY` uses `LevelFilter(WARN)`. Conversely, if `WARN_ONLY` is changed to `ThresholdFilter(WARN)`, an `ERROR` event will appear **in both `WARN_PLUS` and `ERROR_ONLY`**. That may be an intentional policy (error logs appearing in both the warning channel and the error channel), but if both write to the same destination, it easily creates duplicate records.

There are two valid routing styles:

- **Mutually exclusive channels:** `INFO_ONLY`, `WARN_ONLY`, `ERROR_ONLY`; each event goes to exactly one corresponding channel.
- **Overlapping (nested) channels:** `APP_ALL` receives all events accepted by the Logger; `ALERTS` receives `WARN+`; `ERRORS` receives `ERROR`. An error may be sent to three destinations because operational requirements call for it.

There is no rule that every event must go to exactly one appender: the right number of destinations depends on your collection contract. What you want to avoid is **unintentional duplication** caused by attaching an appender multiple times, additivity, or using the wrong filter semantics.

## 7. Runnable Java 17 Example: Routing INFO, WARN, ERROR to Three Channels

This is a **complete program** using SLF4J and Logback Classic. The example uses **three `ConsoleAppender` instances all writing to `System.out` solely to demonstrate level-based routing using the prefixes `INFO_SINK`, `WARN_SINK`, and `ERROR_SINK`**. In production, the three destinations might be three separate files/collectors, or a single JSON stream with a `level` field so a centralized system can route them.

The program is designed for deterministic output without timestamps or thread names; the code emits events sequentially. The root configuration `INFO` blocks `DEBUG` before it reaches any appender. The `LevelFilter` on each appender handles **exactly one level**.

### 7.1. Project Structure

```text
level-appender-demo/
  settings.gradle
  build.gradle
  src/
    main/
      java/
        demo/
          LevelAppenderDemo.java
      resources/
        logback.xml
```

### 7.2. `settings.gradle`

```groovy
rootProject.name = 'level-appender-demo'
```

### 7.3. `build.gradle` (Groovy DSL)

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.slf4j:slf4j-api:2.0.17'
    runtimeOnly 'ch.qos.logback:logback-classic:1.5.18'
}

application {
    mainClass = 'demo.LevelAppenderDemo'
}
```

Versions are pinned for reproducibility; **this is not a claim that they are the latest versions**. In a real project, use tested backend versions, apply security patches, and keep the SLF4J API and provider synchronized. Keep only **one** SLF4J provider on the runtime classpath.

### 7.4. `src/main/resources/logback.xml`

```xml
<configuration>
    <appender name="INFO_ONLY" class="ch.qos.logback.core.ConsoleAppender">
        <target>System.out</target>
        <filter class="ch.qos.logback.classic.filter.LevelFilter">
            <level>INFO</level>
            <onMatch>ACCEPT</onMatch>
            <onMismatch>DENY</onMismatch>
        </filter>
        <encoder>
            <pattern>INFO_SINK %level %msg%n</pattern>
        </encoder>
    </appender>

    <appender name="WARN_ONLY" class="ch.qos.logback.core.ConsoleAppender">
        <target>System.out</target>
        <filter class="ch.qos.logback.classic.filter.LevelFilter">
            <level>WARN</level>
            <onMatch>ACCEPT</onMatch>
            <onMismatch>DENY</onMismatch>
        </filter>
        <encoder>
            <pattern>WARN_SINK %level %msg%n</pattern>
        </encoder>
    </appender>

    <appender name="ERROR_ONLY" class="ch.qos.logback.core.ConsoleAppender">
        <target>System.out</target>
        <filter class="ch.qos.logback.classic.filter.LevelFilter">
            <level>ERROR</level>
            <onMatch>ACCEPT</onMatch>
            <onMismatch>DENY</onMismatch>
        </filter>
        <encoder>
            <pattern>ERROR_SINK %level %msg%n</pattern>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="INFO_ONLY"/>
        <appender-ref ref="WARN_ONLY"/>
        <appender-ref ref="ERROR_ONLY"/>
    </root>
</configuration>
```

The file above is **complete XML**; it must be named `logback.xml` in `src/main/resources` so it is on the runtime classpath. Do not add a fourth root appender if you want the exact demo output. Encoders are attached directly to each `ConsoleAppender`.

All three appenders get a chance to process every event **accepted by the Logger**, but each appender only outputs when its own filter accepts the level. Therefore, each `INFO`/`WARN`/`ERROR` event produces exactly one line.

### 7.5. `src/main/java/demo/LevelAppenderDemo.java`

```java
package demo;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public final class LevelAppenderDemo {
    private static final Logger LOG =
            LoggerFactory.getLogger(LevelAppenderDemo.class);

    public static void main(String[] args) {
        LOG.debug("event=diagnostic.hidden");
        LOG.info("event=order.created orderId={}", "ord-17");
        LOG.warn("event=inventory.low sku={}", "sku-9");
        LOG.error("event=payment.failed errorCode={}", "UPSTREAM_TIMEOUT");
    }
}
```

There are no `ch.qos.logback` imports in the Java source: **SLF4J is the facade**, and Logback is selected via the runtime dependency. `{}` is SLF4J's parameterized placeholder, unlike `{0}` in the JUL/`MessageFormat` API.

### 7.6. Compile and Run

From the `level-appender-demo` directory, using JDK 17 and a Java 17-compatible Gradle:

```bash
gradle run --quiet
```

If the project includes a Gradle Wrapper, you can replace `gradle` with `./gradlew` on Linux/macOS or `gradlew.bat` on Windows. This example does not include a Gradle Wrapper; Gradle and access to Maven Central are required for the initial dependency download.

**Exact stdout of the application code with the configuration above:**

```text
INFO_SINK INFO event=order.created orderId=ord-17
WARN_SINK WARN event=inventory.low sku=sku-9
ERROR_SINK ERROR event=payment.failed errorCode=UPSTREAM_TIMEOUT
```

Explanation of each case:

1. `LOG.debug(...)` is dropped at the Logger by the root level `INFO`. No appender sees `DEBUG`.
2. `LOG.info(...)` goes to all three appenders; only `INFO_ONLY` with `LevelFilter(INFO)` accepts it.
3. `LOG.warn(...)` is only accepted by `WARN_ONLY` because this is an **exact WARN match**, not `WARN+`.
4. `LOG.error(...)` is only accepted by `ERROR_ONLY`. The `WARN_ONLY` appender does not accept `ERROR` because `LevelFilter` matches by equality.
5. `%level`, `%msg`, `%n` in `logback.xml` are Logback conversion patterns, not SLF4J message parameterization syntax.
6. There is no timestamp, thread, or Logger name in the demo pattern, so the output above does not depend on the clock or thread names. Gradle dependency download messages or build tool warnings, if any, are not stdout defined by this program.

### 7.7. Try Changing a Condition

**Experiment A:** Change root from `INFO` to `DEBUG`. Now the `DEBUG` call is accepted by the Logger, **but there is no `DEBUG_ONLY` appender** in the XML, so it still does not appear. This demonstrates that **Logger acceptance alone is not enough** to guarantee output.

**Experiment B:** Replace `WARN_ONLY` with `ThresholdFilter(WARN)` while keeping `ERROR_ONLY`. Logical result: `WARN` events appear at `WARN_SINK`; `ERROR` events appear at **both `WARN_SINK` and `ERROR_SINK`**. If both write to stdout, you will see two lines for one `ERROR` event. This can be right when you want both channels simultaneously, but it is an unwanted duplicate if you intended them to be separate.

**Experiment C:** Keep `LevelFilter(WARN)` but change root to `ERROR`. Now `WARN` is dropped at the Logger, and the `WARN_ONLY` appender cannot recover it. Only `ERROR` is dispatched and received by `ERROR_ONLY`.

## 8. Another Example: An Appender That Only Accepts WARN and ERROR

When a monitoring tool needs an `ALERTS` channel containing all `WARN` or higher events, `ThresholdFilter` is much more concise than combining multiple `LevelFilter`s:

```xml
<appender name="ALERTS" class="ch.qos.logback.core.ConsoleAppender">
    <target>System.err</target>
    <filter class="ch.qos.logback.classic.filter.ThresholdFilter">
        <level>WARN</level>
    </filter>
    <encoder>
        <pattern>ALERTS %level %logger - %msg%n</pattern>
    </encoder>
</appender>
```

This is an **appender configuration snippet**; it must be placed inside `<configuration>` and referenced by a Logger or root. If you attach this appender alongside an `ALL_EVENTS` appender, `WARN`/`ERROR` may appear in both; that is not necessarily a bug if `ALL_EVENTS` is the general log and `ALERTS` is the alerting channel.

Similarly, if you want a file storing `ERROR` and above, you can use `ThresholdFilter(ERROR)`. For standard levels, the result is equivalent to `ERROR` only; however, `LevelFilter(ERROR)` more explicitly expresses the **exact-match** requirement.

## 9. Level-Based Appenders and File Splitting

A log file layout might look like:

```text
logs/
  application.log   -> INFO, WARN, ERROR (if accepted by Logger)
  warnings.log      -> WARN, ERROR
  errors.log        -> ERROR
```

In this case:

- `APPLICATION`: general appender; without a Filter, it receives events that passed the Logger/forwarding path.
- `WARNINGS`: appender with `ThresholdFilter(WARN)`.
- `ERRORS`: appender with `LevelFilter(ERROR)` or `ThresholdFilter(ERROR)`.

**Clear consequence:** a single `ERROR` event appears in three files. This is not a "duplication bug" if each file serves a different purpose, but it increases disk usage and ingestion cost. When a collector reads all three files simultaneously as three independent event sources, the centralized system may **count one error as three** unless deduplication is designed in. Decide whether you genuinely need multiple files or just a single JSON stream with a `level` field.

When using `RollingFileAppender`, the appender manages file rotation and history according to its rolling policy, while the level filter decides which events enter that file. Do not use multiple independent `FileAppender` instances writing to the **same file path** unless configured to support concurrent writing; this can cause file contention, duplicated content, or rollover failures.

In Docker/Kubernetes, it is usually better to write logs to stdout/stderr and let the platform/collector layer handle collection, storage, and routing by the `level` field. Configuring a separate local file for each severity level is not always the best choice.

## 10. Appenders, Logger Hierarchy, and Additivity

Suppose an `ERROR_ONLY` appender is attached to root. Child Logger `com.example.payment` has additivity enabled by default, so `ERROR` events from the child Logger (if accepted) can propagate up to the root appender.

```text
root logger [INFO] -> ERROR_ONLY
    |
    +-- com.example [INHERITED]
         |
         +-- com.example.payment [DEBUG, additivity=true]
```

`com.example.payment` allows `DEBUG`/`INFO`/`WARN`/`ERROR` according to its own level, but the `ERROR_ONLY` appender at root still only outputs `ERROR`. **Setting root to `INFO` does not block `DEBUG` emitted by a `DEBUG` child Logger** if the root appender lacks an appropriate Filter; the appender's filter is what controls the output.

If you attach `ERROR_ONLY` to both the child Logger and root while leaving additivity enabled, **the same `ERROR` event can be passed to the appender twice** and produce duplicate output. To avoid this:

- Attach shared appenders at only one place in the Logger tree.
- Or set `additivity="false"` on the child Logger when that branch has its own appenders and genuinely does not need to propagate to ancestors.
- Do not disable additivity blindly: if the child Logger has no appenders of its own, events may have nowhere to be written.

Example **configuration snippet** in a `logback.xml` file:

```xml
<logger name="com.example.payment" level="DEBUG" additivity="false">
    <appender-ref ref="PAYMENT_ERROR"/>
</logger>
```

Here `PAYMENT_ERROR` must be an already-declared appender. If that appender only has an `ERROR` filter, `INFO`/`WARN` events accepted by the child Logger will not be printed anywhere in this branch unless corresponding appenders are also attached. Therefore, you must design **complete routing paths for every level you want to retain**, not just fix duplication for one level.

## 11. Comparison with `java.util.logging.Handler`

When using **JUL (`java.util.logging`)** instead of Logback, the destination-side term is `Handler`. `Handler.setLevel(Level.WARNING)` sets the Handler's **minimum threshold**: it accepts `WARNING` and more severe levels, unless another Filter blocks them.

**Illustrative code snippet**:

```java
java.util.logging.ConsoleHandler handler =
        new java.util.logging.ConsoleHandler();
handler.setLevel(java.util.logging.Level.WARNING);
```

In JUL, `WARNING` is close to Logback's `WARN`, and `SEVERE` is close to `ERROR`, but the level systems and configuration mechanisms are **not identical**. Do not copy Logback's `LevelFilter`/`ThresholdFilter` XML directly into `java.util.logging` or assume `Handler.setLevel(WARNING)` means "WARNING only".

If you want **strictly WARNING only** on a JUL Handler, you can combine the level with a `Filter`:

```java
handler.setLevel(java.util.logging.Level.WARNING);
handler.setFilter(record ->
        record.getLevel().equals(java.util.logging.Level.WARNING));
```

This is a **code snippet** tied to a declared `handler`; you must add the Handler to an appropriate Logger or `LogManager` for logs to appear. It filters for the exact `Level.WARNING` object; if a project uses custom levels with the same/equivalent severity, you must define the matching rules explicitly.

In JUL, `Logger.setLevel(null)` means inheriting the effective level from the parent, and `setUseParentHandlers(false)` disables forwarding events to parent Handlers. These concepts are close to Logback's level inheritance and additivity, but **differ in API and configuration**. When running SLF4J with Logback, do not configure a JUL Handler expecting it to control Logback appenders.

## 12. Level Filtering Is Not the Solution for Every Routing Need

Level filters are well-suited for severity-based decisions, but real-world requirements sometimes call for:

- Sending only **`ERROR` events from the payment module** to the alerting channel.
- Sending only events with `marker=AUDIT` or a critical `errorCode`.
- Separating logs safely by `tenantId` or `jobId`.
- Dropping events containing protected data or coming from noisy test sources.
- Enabling sampling/rate limiting when log volume is too high.

These needs **cannot be fully solved with `ThresholdFilter` alone**. Consider logger hierarchy, `EvaluatorFilter`, `TurboFilter`, markers, MDC, or a dedicated collector/router system. In Logback, regular filters are attached to appenders; `TurboFilter` plays a different role at the logging context layer. Advanced configurations should be verified against the exact Logback version in use.

Especially for sensitive data, **you must restrict it at the moment the message/field is created**, rather than relying on a destination filter to mask every secret already placed in a log. Exception messages or `toString()` calls can contain tokens, cookies, or payloads that a level filter cannot inspect.

## 13. Performance and Risk of Log Loss

Splitting events by level can reduce volume at certain destinations, but it is not free:

1. **The Logger still has to check the level** before an event reaches any appender.
2. For every event that passes the Logger, **each referenced appender** may evaluate its filters.
3. Creating many appenders can increase management, encoder, I/O, and configuration overhead.
4. If one event goes to multiple destinations, total volume and ingestion costs can rise.
5. With `AsyncAppender`, queues and discard/blocking policies can cause some events to be dropped or slow down logging threads; do not assume level filtering guarantees all `WARN`/`ERROR` events are saved.
6. If the process crashes or the filesystem fills up, an event that passed a filter is not guaranteed to be durably written.

If you need to reduce `INFO` costs, do not just move `INFO` to another file while the collector still ingests both files. Set logger/filter/collector policies aligned with your goal. At the same time, do not accidentally drop all `WARN`/`ERROR` logs needed for incident investigation.

For durable auditing and transaction reconciliation, an ordinary appender does not replace a storage solution with durability guarantees, access control, and tamper-resistance policies.

## 14. Troubleshooting When a Level-Based Appender Does Not Work

| Symptom | Common Cause | How to Check |
| --- | --- | --- |
| `INFO` appender has no `INFO` logs | Logger is at `WARN`/`ERROR`, or appender is not referenced | Check effective Logger level, `appender-ref`, and filters |
| `INFO` appender also contains `ERROR` | Used `ThresholdFilter(INFO)` instead of `LevelFilter(INFO)` | Switch to `LevelFilter` when you want `INFO` only |
| `WARN` appender also receives `ERROR` | Used `ThresholdFilter(WARN)` | Expected behavior; use `LevelFilter` if you want `WARN` only |
| `ERROR_ONLY` declared, but no `ERROR` appears | Logger disabled, another filter blocks it, appender not started, I/O error | Check Logger, filter chain, appender lifecycle, and target |
| `DEBUG` does not appear despite `DEBUG_ONLY` | Root or effective Logger is still at `INFO` | Enable `DEBUG` on the source Logger, then check the appender |
| One `ERROR` event produces two identical lines | Two appenders share the same target, additivity, or duplicate references | Trace the event path; check filters and targets |
| Same appender processes too many messages | Appender attached at root for all packages | Split logger hierarchy or filter by module/marker |
| Added another filter, but it has no effect | First filter returns `ACCEPT`, short-circuiting later filters | Check filter order and `ACCEPT/NEUTRAL/DENY` |
| File is empty when using `RollingFileAppender` | Missing write permissions, appender failed to start, not enough events, or bad rolling policy | Inspect Logback internal status, path, and write permissions |
| Logs sent to wrong destination after framework change | Runtime backend is not Logback | Verify SLF4J provider, starter, and matching config file |
| Logs only lost under high load | Async queue, discarding, backpressure, or overloaded collector | Check queue size, drop counters, shutdown hooks, and bandwidth |

### Step-by-Step Verification Process

1. Identify the **actual active backend** (Logback vs. JUL/Log4j 2).
2. Verify the log call executes and the **effective Logger allows that level**.
3. Verify the event has a path to the appender via `appender-ref` and additivity.
4. Check the filter: **exact-level vs. threshold**, and `ACCEPT/NEUTRAL/DENY` ordering.
5. Verify the appender has started, the encoder is valid, and stdout/stderr/file/collector targets work.
6. Test `INFO`, `WARN`, and `ERROR` individually; then test `DEBUG` and multi-appender scenarios.
7. Verify the setup does not duplicate/drop logs, is monitored, and handles load.

Do not change too many settings at once; record the input, expected logs, and actual output for each level to pinpoint which layer is dropping the event.

## 15. Project Adoption Checklist

- [ ] Clarify whether the requirement is **an exact level** or **at or above a threshold**.
- [ ] Use `LevelFilter` for `INFO`-only/`WARN`-only/`ERROR`-only; use `ThresholdFilter` for `WARN+` or `ERROR+`.
- [ ] Confirm the effective Logger accepts the events intended for the appender.
- [ ] Check filter order and distinguish `DENY`, `NEUTRAL`, and `ACCEPT`.
- [ ] Ensure appenders have valid `encoder` and `target` settings and are referenced by Logger/root.
- [ ] Avoid referencing an appender at multiple Logger levels if it causes unintended duplication.
- [ ] If `additivity=false`, ensure the child Logger still has appropriate destinations for levels you need to keep.
- [ ] Distinguish Logback Appenders from JUL Handlers; do not mix APIs/configs mechanically.
- [ ] Avoid writing one event to multiple files unless there is a clear operational reason and cost plan.
- [ ] For containers, consider emitting a single stream with a severity field instead of multiple local files.
- [ ] Test `INFO`/`WARN`/`ERROR`, filtered-out logs, I/O errors, and async behavior under load.
- [ ] Protect secrets, limit sensitive data, and control retention/collectors.

### Technical References

- [Logback Manual — Filters](https://logback.qos.ch/manual/filters.html): `LevelFilter`, `ThresholdFilter`, and evaluation order rules.
- [Logback Manual — Configuration](https://logback.qos.ch/manual/configuration-xml.html): Logger hierarchy, `appender-ref`, and additivity.
- [Logback Manual — Appenders](https://logback.qos.ch/manual/appenders.html): Appender lifecycle, filters, and encoders.
- [Java Platform — java.util.logging.Handler](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Handler.html): Handler levels and filters in JUL.

**Conclusion:** **Level-based appenders** let you route events accepted by a Logger to different destinations. In Logback, `LevelFilter` matches **an exact level**, while `ThresholdFilter` passes **a threshold and above**. Combining the right Logger level, filters, additivity, and output targets helps prevent lost logs, avoid duplicates, and ensure critical severities reach the right monitoring channels.
