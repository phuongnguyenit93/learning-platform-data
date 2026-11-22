# Per-Appender Configuration in Java Logging

## 1. What Is an Appender and Why Configure Them Separately?

In Java Logging, a **logger** is the point that application code calls to emit messages such as `log.info("Created order")`. An **appender** is the component that receives an enabled *logging event* and **writes it to a specific destination**: terminal, file, rolling file, socket, telemetry system, or another appender. In `java.util.logging` (JUL), the component with the same role is called a **Handler**.

An application often needs multiple output destinations with different policies:

- **Console**: primarily displays `WARN`/`ERROR` for quick monitoring by the operations team.
- **File**: stores `INFO` and above, including timestamp, logger name, and trace information.
- **Audit**: records separately defined business events with dedicated access control, storage, and retention.
- **Async**: places a queue in front of an expensive sink so business threads do not have to wait directly on every I/O operation.

Therefore, "per-appender configuration" means **each destination has its own name, layout/encoder, filter, write policy, storage limits, and logger attachment**. You should not try to solve every requirement with a single global `root level`.

Desired example:

| Event | Console | Application File | Audit |
| --- | --- | --- | --- |
| `com.example.orders` – `DEBUG` | No | No (if the logger is only at INFO) | No |
| `com.example.orders` – `INFO` | No | Yes | No |
| `com.example.orders` – `ERROR` | Yes | Yes | No |
| `com.example.payment` – `DEBUG` | No | Yes (when the package logger is at DEBUG) | No |
| `com.example.audit` – `INFO` | No | No if `additivity=false` is configured | Yes |

The result above depends on **the entire decision chain** of loggers and appenders; declaring an appender in XML does not make it log automatically. A logger must **reference** it.

## 2. The Decision Chain: Logger Level, Routing, Appender Filter, Output

```text
Application: logger.info("message")
            │
            ▼
Does the logger effective level allow the event?
     ├── No: stop here
     └── Yes: create LogEvent
                 │
                 ▼
       Logger/appender references + additivity
                 │
         ┌───────┴──────────┬────────────────┐
         ▼                  ▼                ▼
   CONSOLE appender     FILE appender    AUDIT appender
   threshold WARN       threshold INFO   audit route
   short pattern        detailed pattern separate policy
         │                  │                │
      stdout/stderr       rolling file    audit file/channel
```

**Logger level** controls *whether an event is generated/enabled*. Logback has a fundamental rule: an event at level `p` is enabled if `p` is greater than or equal to the logger's **effective level** `q`. A logger can inherit its parent's level if it has not been assigned its own level.

**Appender filter/threshold** decides *which destination receives an already-created event*. For example, the root logger is at `INFO`, the Console appender only accepts `WARN` and above, while File accepts `INFO` and above. A `DEBUG` event from a logger whose effective level is `INFO` **is not created**; setting the File appender to "DEBUG" cannot recover that event either. Conversely, when a child logger is at `DEBUG`, an enabled `DEBUG` event can reach the root's appender via additivity, provided the appender filter allows it.

**Layout/encoder** defines how an event becomes bytes: text pattern, JSON, encoding, and line endings. It does not decide whether an event is created. In Logback, `PatternLayoutEncoder` both applies the pattern and encodes; in Log4j 2, it is `PatternLayout` or an appropriate JSON layout.

**Destination/retention** specifies where logs go, when they roll over, how long they are kept, who has read permissions, and what happens when the sink is full or fails. These are typically **per-appender** properties.

## 3. Common Appender Groups

| Appender / Handler | Output Destination | Key Configuration | Suitable Use Cases |
| --- | --- | --- | --- |
| `ConsoleAppender` (Logback/Log4j 2), `ConsoleHandler` (JUL) | stdout/stderr | Target, layout, level/filter | Containers, local development, terminal |
| `FileAppender` / `FileHandler` | One or more files | Path, append/overwrite, encoding, lock, level | Simple tools or applications |
| `RollingFileAppender` / `RollingFile` | Active file and archive files | File name pattern, trigger, max size, history, compression | High-volume logging apps needing disk limits |
| `AsyncAppender` | Queue in front of another appender | Capacity, discard/full policy, flush timeout | Outputs with significant I/O, where trade-offs are acceptable |
| Network/OTLP appender or bridge | Endpoint/Collector | Timeout, batch, retry, TLS, auth, batching | Centralized telemetry |
| Routing/Sifting appender | Selects target appender by context | Routing key, lifecycle, and number of routes | Separating log streams by controlled tenant/case |

Not every framework shares the same names or defaults. For instance, JUL `FileHandler` supports size/count limits and rotates by file count, but is not a direct equivalent to Logback's `SizeAndTimeBasedRollingPolicy`.

## 4. Logback Example: One Policy per Appender

Suppose a Spring Boot application uses SLF4J with a Logback backend. Create `src/main/resources/logback-spring.xml`. The following example includes:

- `CONSOLE` printing only `WARN` and above;
- `APP_FILE` storing `INFO` and above by default, with the payment package allowed at `DEBUG`;
- `AUDIT_FILE` dedicated to the `com.example.audit` logger, separated from root appenders.

```xml
<configuration>
    <appender name="CONSOLE" class="ch.qos.logback.core.ConsoleAppender">
        <filter class="ch.qos.logback.classic.filter.ThresholdFilter">
            <level>WARN</level>
        </filter>
        <encoder>
            <charset>UTF-8</charset>
            <pattern>%d{HH:mm:ss.SSS} %-5level [%thread] %logger{36} - %msg%n</pattern>
        </encoder>
    </appender>

    <appender name="APP_FILE"
              class="ch.qos.logback.core.rolling.RollingFileAppender">
        <file>logs/application.log</file>
        <rollingPolicy
            class="ch.qos.logback.core.rolling.SizeAndTimeBasedRollingPolicy">
            <fileNamePattern>logs/application.%d{yyyy-MM-dd}.%i.log.gz</fileNamePattern>
            <maxFileSize>20MB</maxFileSize>
            <maxHistory>14</maxHistory>
            <totalSizeCap>1GB</totalSizeCap>
        </rollingPolicy>
        <encoder>
            <charset>UTF-8</charset>
            <pattern>%d{yyyy-MM-dd HH:mm:ss.SSS} %-5level [%thread] %logger{36} trace_id=%X{trace_id} - %msg%n</pattern>
        </encoder>
    </appender>

    <appender name="AUDIT_FILE"
              class="ch.qos.logback.core.rolling.RollingFileAppender">
        <file>logs/audit.log</file>
        <rollingPolicy
            class="ch.qos.logback.core.rolling.TimeBasedRollingPolicy">
            <fileNamePattern>logs/audit.%d{yyyy-MM-dd}.log.gz</fileNamePattern>
            <maxHistory>30</maxHistory>
            <totalSizeCap>500MB</totalSizeCap>
        </rollingPolicy>
        <encoder>
            <charset>UTF-8</charset>
            <pattern>%d{yyyy-MM-dd HH:mm:ss.SSS} %-5level %logger{36} - %msg%n</pattern>
        </encoder>
    </appender>

    <logger name="com.example.payment" level="DEBUG"/>

    <logger name="com.example.audit"
            level="INFO" additivity="false">
        <appender-ref ref="AUDIT_FILE"/>
    </logger>

    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
        <appender-ref ref="APP_FILE"/>
    </root>
</configuration>
```

This is a **configuration to place inside a Spring Boot application that already has Logback**, not standalone Java code. The `logs/` directory is resolved relative to the process working directory; the parent directory must have create/write permissions and sufficient disk space. When deploying in a container, you must decide whether to write internal files or only write to stdout and let the platform collect them.

### 4.1. Section-by-Section Breakdown

**`CONSOLE`:** `ThresholdFilter` drops events below `WARN`. Logback's `ThresholdFilter` returns `DENY` for levels below the threshold and `NEUTRAL` for events meeting the threshold. Only `WARN`/`ERROR` levels already enabled by the logger reach this step. The pattern prints level, thread, logger, and message; the printed timestamp is the time of the logging event.

**`APP_FILE`:** `RollingFileAppender` keeps the active file open at `logs/application.log`. `SizeAndTimeBasedRollingPolicy` creates archives by date and index `%i` when the file exceeds the configured size within the same day. Both `%d` and `%i` tokens are required for combined date + size rolling. `maxHistory=14` keeps at most 14 historical date cycles, and `totalSizeCap=1GB` caps total archive size according to Logback's mechanism; it **does not guarantee that the currently active file** is always strictly under the limit immediately or that total disk usage is exactly 1GB.

**`AUDIT_FILE`:** uses separate daily rolling and retention; the audit logger has `additivity=false` so logs sent to `AUDIT_FILE` **do not propagate** to root's `CONSOLE`/`APP_FILE`. This is a routing operation, not a mechanism that guarantees durable or tamper-evident audit logging. For regulatory audit requirements, you also need to verify durable writes, access protection, legal retention, and a dedicated pipeline.

**`com.example.payment`:** is set to `DEBUG` and still inherits root's appenders (because additivity defaults to `true`). When this package emits `DEBUG`, `APP_FILE` writes it because that appender has no filter blocking DEBUG; `CONSOLE` filters it out because it only accepts WARN and above. Root at INFO **does not re-filter DEBUG** already enabled on a child logger in Logback. Do not assume that root INFO will block all DEBUG logs from child loggers.

**`trace_id=%X{trace_id}`:** only contains data if MDC has been properly populated by the application or instrumentation. A per-appender pattern does not generate a trace ID on its own. When it is empty, check propagation/MDC before concluding the appender is broken.

### 4.2. Relationship Between Logger Level and Appender Filter

Suppose we have the following calls:

```java
private static final org.slf4j.Logger ORDER =
        org.slf4j.LoggerFactory.getLogger("com.example.orders.OrderService");
private static final org.slf4j.Logger PAYMENT =
        org.slf4j.LoggerFactory.getLogger("com.example.payment.PaymentService");
private static final org.slf4j.Logger AUDIT =
        org.slf4j.LoggerFactory.getLogger("com.example.audit.ChangeLog");

public void process() {
    ORDER.debug("Order cache lookup");
    ORDER.info("Order created");
    ORDER.error("Order submission failed");
    PAYMENT.debug("Payment attempt prepared");
    AUDIT.info("Role changed");
}
```

This snippet is an **illustrative method inside a class that already declares the three logger fields**; running it requires SLF4J, Logback dependencies, and a real application class. You cannot copy this snippet alone into a file and run it with `javac` without a classpath.

Under the configuration above, events flow as follows:

| Call | Enabled at logger? | `CONSOLE` | `APP_FILE` | `AUDIT_FILE` |
| --- | --- | --- | --- | --- |
| `ORDER.debug` | No, effective INFO | No | No | No |
| `ORDER.info` | Yes | No, below WARN | Yes | No |
| `ORDER.error` | Yes | Yes | Yes | No |
| `PAYMENT.debug` | Yes, logger DEBUG | No, below WARN | Yes | No |
| `AUDIT.info` | Yes | No, additivity false | No, additivity false | Yes |

Do not rely on this table to assume "each log appears exactly once": an event can intentionally be sent to **two destinations** (console + file). A *duplicate* issue is two unwanted copies in the **same sink or the same ingest pipeline** caused by overlapping route/appender/collector configuration.

## 5. Appender-Level Filtering: ThresholdFilter, LevelFilter, Filter Chain

In Logback:

- `ThresholdFilter` allows events at or **above a threshold** to pass through (such as WARN/ERROR to console).
- `LevelFilter` checks for **equality with a single level**. To store only ERROR, you can set level ERROR, `onMatch=ACCEPT`, `onMismatch=DENY`.
- Each filter returns one of `DENY`, `NEUTRAL`, or `ACCEPT`. `DENY` blocks; `ACCEPT` allows; `NEUTRAL` passes the event to the next filter for evaluation. When combining multiple filters, order and return states matter.

Example of an appender that accepts only `ERROR`, dropping `WARN`, `INFO`, and `DEBUG`:

```xml
<filter class="ch.qos.logback.classic.filter.LevelFilter">
    <level>ERROR</level>
    <onMatch>ACCEPT</onMatch>
    <onMismatch>DENY</onMismatch>
</filter>
```

Place this snippet **inside the appender** that needs filtering. Do not add a whole new appender if a corresponding sink already exists. Test with both ERROR and WARN events to verify the filter works correctly; appender filters run after the logger's enabled gate.

With multiple appenders, a policy like "console WARN, file INFO" should be expressed directly on each appender/filter (or on the appender reference if the framework supports it), while the logger level describes the business log level allowed to be generated.

## 6. Configuring a Package to Write to Only One Destination

When you need to isolate a package's logs from root, you can configure:

```xml
<logger name="com.example.audit"
        level="INFO" additivity="false">
    <appender-ref ref="AUDIT_FILE"/>
</logger>
```

Meaning:
- Loggers whose names start with the `com.example.audit` package, following standard logger hierarchy inheritance, will match this configuration.
- `additivity=false` prevents events from propagating up to ancestor appenders (including root).
- If you forget to reference `AUDIT_FILE`, events may not reach any intended destination.
- If you keep `additivity=true` while also attaching `AUDIT_FILE` to an ancestor, you risk sending duplicate events to the same appender or creating unintended output paths.

Another scenario: you want isolated audit logs **and** you also want audit WARN/ERROR messages on the operations console. In that case, you can directly reference both `AUDIT_FILE` and `CONSOLE` on the audit logger with `additivity=false`; the `CONSOLE` filter will still only accept WARN and above. Do not change `additivity` globally if only one namespace needs special routing.

### 6.1. Inheriting Level Does Not Mean Inheriting Layout

A child logger can inherit its **effective level** from its parent and deliver events through appenders attached to ancestors. However, `CONSOLE`'s pattern/encoder remains the console pattern, and `APP_FILE`'s pattern/encoder remains the file pattern. A logger does not have a "parent-level layout" applied across all appenders. This allows a single event to appear concise in the terminal while carrying richer metadata in the file.

## 7. Equivalent Example in Log4j 2

Log4j 2 uses `Appender`, `AppenderRef`, and filters/levels on loggers or references. Example `src/main/resources/log4j2.xml` in an application that **has chosen Log4j 2 Core as its backend**:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<Configuration status="WARN">
    <Appenders>
        <Console name="CONSOLE" target="SYSTEM_OUT">
            <PatternLayout charset="UTF-8"
                pattern="%d{HH:mm:ss.SSS} %-5level %c{1.} - %msg%n"/>
        </Console>

        <RollingFile name="APP_FILE"
            fileName="logs/application.log"
            filePattern="logs/application-%d{yyyy-MM-dd}-%i.log.gz">
            <PatternLayout charset="UTF-8"
                pattern="%d{yyyy-MM-dd HH:mm:ss.SSS} %-5level [%t] %c - %msg%n"/>
            <Policies>
                <TimeBasedTriggeringPolicy interval="1" modulate="true"/>
                <SizeBasedTriggeringPolicy size="20MB"/>
            </Policies>
        </RollingFile>
    </Appenders>

    <Loggers>
        <Logger name="com.example.payment" level="DEBUG"/>

        <Root level="INFO">
            <AppenderRef ref="CONSOLE" level="WARN"/>
            <AppenderRef ref="APP_FILE"/>
        </Root>
    </Loggers>
</Configuration>
```

Here `CONSOLE` is an appender with its own pattern; `AppenderRef ref="CONSOLE" level="WARN"` filters **at the reference from root to console**, instead of using Logback's `ThresholdFilter` inside the appender. `APP_FILE` stores from INFO upward for normal loggers; DEBUG events from `com.example.payment` also reach `APP_FILE` via additivity. Do not run both Logback and Log4j 2 backends simultaneously in the same application just to apply both examples.

Important notes for `RollingFile`:

- `TimeBasedTriggeringPolicy` and `SizeBasedTriggeringPolicy` are placed together under `Policies`. `%d` represents the archive date/time, and `%i` is the incrementing index for multiple rollovers within the same period.
- **Rollover does not automatically equal infinite retention or 14/30-day retention**. To delete archives by age or total size, you must configure an appropriate `RolloverStrategy`/`Delete` action or manage retention externally; this example omits full retention rules to avoid equating `max index` with "number of days kept".
- When adding a JSON layout, verify that the dependency/layout is actually on the classpath (for example, `JsonTemplateLayout` typically requires a separate module). `PatternLayout` in the example is sufficient to run on a standard Log4j 2 Core setup.
- Log4j 2 supports filters at different levels (global, logger, appender, appender reference); a filter on a reference does not necessarily affect other loggers that directly reference the same appender.

If using Spring Boot, choose a compatible starter/backend and avoid keeping Logback on the classpath, which causes SLF4J binding conflicts. The configuration file must have the right name and location for the active backend.

## 8. Standard Java: Runnable Example with Per-Handler Configuration

No external libraries are needed to see the principle "the logger enables events, each destination filters independently." JUL uses `java.util.logging.Logger` and `java.util.logging.Handler`. The following example configures **console for WARNING and above**, and **file for INFO and above**; the logger enables FINE and above.

Save as `PerHandlerDemo.java`:

```java
import java.io.IOException;
import java.util.logging.ConsoleHandler;
import java.util.logging.FileHandler;
import java.util.logging.Formatter;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class PerHandlerDemo {
    private static final class OneLineFormatter extends Formatter {
        @Override
        public String format(LogRecord record) {
            return record.getLevel().getName()
                    + " " + formatMessage(record) + "\n";
        }
    }

    public static void main(String[] args) throws IOException {
        Logger logger = Logger.getLogger("demo.application");
        logger.setUseParentHandlers(false);
        logger.setLevel(Level.FINE);

        Handler console = new ConsoleHandler();
        console.setLevel(Level.WARNING);
        console.setFormatter(new OneLineFormatter());

        FileHandler file = new FileHandler("demo.log", false);
        file.setLevel(Level.INFO);
        file.setEncoding("UTF-8");
        file.setFormatter(new OneLineFormatter());

        logger.addHandler(console);
        logger.addHandler(file);

        try {
            logger.info("Started");
            logger.fine("Cache detail");
            logger.warning("Disk nearly full");
        } finally {
            logger.removeHandler(console);
            logger.removeHandler(file);
            console.close();
            file.close();
        }
    }
}
```

Compile and run with JDK 17+ in a directory with write permissions:

```bash
javac --release 17 PerHandlerDemo.java
java PerHandlerDemo
cat demo.log
```

`ConsoleHandler` writes to **stderr** by default, so `java PerHandlerDemo` alone writes nothing to stdout. Stderr output of the Java command:

```text
WARNING Disk nearly full
```

Then the contents of `demo.log` (also the stdout of `cat demo.log`):

```text
INFO Started
WARNING Disk nearly full
```

`FINE Cache detail` is dropped at both handlers, even though the logger enabled the FINE event. For console, `INFO Started` is dropped due to the WARNING threshold. For file, both INFO and WARNING meet the threshold. `setUseParentHandlers(false)` prevents parent logger handlers from printing an extra copy. When the program ends, `close()` flushes and closes both handlers; avoid leaving file handlers open unnecessarily.

In PowerShell, you can run:

```powershell
javac --release 17 PerHandlerDemo.java
java PerHandlerDemo
Get-Content demo.log
```

If run multiple times, `new FileHandler("demo.log", false)` will **overwrite** the file rather than append; this is only to make the example output easy to compare. Do not use `append=false` for production log files unless you want to lose old logs on every startup. When the file is locked by another process, JUL may pick another filename using its unique lock rule or fail to create it; the example assumes no other process is using `demo.log`.

Terminology comparison:

| JUL | Logback/Log4j 2 | Meaning |
| --- | --- | --- |
| `Logger` | Logger | Emits events and checks effective level |
| `Handler` | Appender | Delivers events to a destination |
| `Handler.setLevel(...)` | Filter/threshold or reference level | Filters per destination |
| `Formatter` | Layout/Encoder | Converts events to text/bytes |
| `setUseParentHandlers(false)` | `additivity=false` (similar concept) | Prevents forwarding events to parent handlers/appenders |
| `FileHandler` | File/Rolling appender | File output, though rolling features differ |

## 9. Where Does AsyncAppender Fit in the Design?

An async appender **is not a final storage destination**. It is usually an intermediate layer with a queue and worker thread, backed by a file, console, or network appender. In Logback, replace the direct sink appender-ref on root with the async one:

```xml
<appender name="ASYNC_FILE" class="ch.qos.logback.classic.AsyncAppender">
    <queueSize>1024</queueSize>
    <discardingThreshold>0</discardingThreshold>
    <neverBlock>false</neverBlock>
    <maxFlushTime>10000</maxFlushTime>
    <appender-ref ref="APP_FILE"/>
</appender>

<root level="INFO">
    <appender-ref ref="CONSOLE"/>
    <appender-ref ref="ASYNC_FILE"/>
</root>
```

This snippet uses **the same `APP_FILE` defined earlier** and illustrates replacing only the root section; in a complete configuration, avoid leaving root still referencing `APP_FILE` directly at the same time, otherwise a single event could be written to the file twice.

- `queueSize` is measured in events, not MB.
- `discardingThreshold=0` disables dropping low-level logs when queue space runs low, but does not guarantee zero loss.
- `neverBlock=false` allows calling threads to block when the queue is full; `true` prioritizes avoiding blocking by potentially dropping events.
- `maxFlushTime` is the wait limit when stopping the appender, not a per-write timeout.

The console destination on root remains synchronous in this example. If you want both file and console to be async, consider creating clear routes and measuring queue/drop behavior on each route; wrapping everything in async is not always better.

**Log4j 2 `AsyncAppender` and `AsyncLogger` are different.** `AsyncAppender` wraps one or more appenders; `AsyncLogger` is an asynchronous logger mechanism based on a ring buffer/Disruptor. If the application already uses `AsyncLogger`, do not layer `AsyncAppender` on top of every sink without measuring the benefit and queue-full policy.

## 10. Layout and Context Data Should Be Configured per Destination

Two appenders can share the same level while presenting different formats:

- **Terminal:** short pattern for quick reading, e.g., time, level, abbreviated logger, message.
- **File for tracing:** detailed pattern or JSON with ISO timestamp, logger, thread, `trace_id`, `span_id`, exception.
- **Centralized ingest system:** log records with a defined schema, consistent field types, and standard timestamps; an OTel logs bridge/exporter can be chosen depending on architecture.

Example Logback pattern with MDC:

```xml
<pattern>%d{yyyy-MM-dd'T'HH:mm:ss.SSSXXX} %-5level [%thread] trace_id=%X{trace_id} span_id=%X{span_id} %logger{36} - %msg%n</pattern>
```

`%X{trace_id}` only reads MDC; it **does not automatically propagate trace context** across threads or HTTP. If log messages contain newlines or special characters, plain-text output can be hard to parse or vulnerable to log injection when untrusted data is concatenated directly. For collectors that require accurate parsing, use a JSON encoder capable of escaping values and standardizing field names.

Set UTF-8 charset explicitly to reduce encoding issues across machines, combined with consistent locale/timezone settings between services and backends. Never log passwords, access tokens, session cookies, or sensitive content; mask data before passing events to any appender. A masking policy on a file appender does not guarantee that another console appender also masks the data.

## 11. File Appenders: Rotation, Retention, and Access Permissions

**Rotation** (rollover) is switching the active file to an archive when a time or size threshold is reached. **Retention** is deciding which archives are kept or deleted. They are two separate concepts:

- Logback `SizeAndTimeBasedRollingPolicy` has `maxFileSize`, `fileNamePattern` with `%d` and `%i`, `maxHistory`, and `totalSizeCap`.
- Log4j 2 `RollingFile` uses `Policies` to trigger and `RolloverStrategy`/delete actions to manage the archive set.
- JUL `FileHandler` has a size limit and count, but do not assume age-based deletion like the rolling policies above.

Check four key areas:

1. **Paths:** working directory, environment variables, volume mounts, file and folder permissions. Use absolute paths when you need to predict the exact write location.
2. **Capacity:** active logs, archives, compression, and batches/backups share the disk. Alert before the disk is full; archive caps do not cover files outside their scope.
3. **Multiple processes:** two JVMs writing to the same file can contend for locks, corrupt ordering, or make rollover unpredictable. Prefer a separate stdout/file per instance or a sharing mechanism documented and supported by the framework.
4. **Shutdown:** flush/close appenders according to the lifecycle. With async, stopping while events remain in the queue can lose trailing logs. Flushing at the Java level does not guarantee that a remote backend has durably persisted them.

If the application runs in Kubernetes/containers, the common approach is to write to stdout/stderr and let the deployment layer manage collection/rotation. When still using `RollingFileAppender`, ensure the log directory is properly mounted/managed to avoid losing logs when containers are replaced.

## 12. Systematically Testing Per-Appender Configuration

Set up a small test matrix with four events from the same logger/package:

```java
log.debug("cache hit");
log.info("request accepted");
log.warn("upstream slow");
log.error("operation failed", exception);
```

This is an **illustrative snippet inside a method with valid `log` and `exception` variables**, not a standalone program. Run it in a real application and verify:

1. **Logger level:** in an INFO namespace, DEBUG is not generated; in a DEBUG namespace, DEBUG is generated and still has to pass each sink's filter.
2. **Each destination:** in the sample config, console has only WARN/ERROR, while the application file has INFO/WARN/ERROR (plus DEBUG for payment).
3. **Audit routing:** audit events appear in the audit file and do not leak into the main console/file when `additivity=false`.
4. **No duplicates:** if two copies of the same event appear in one file, check root + child appender references, additivity, two async paths into the same sink, and duplicate log shipper ingestion.
5. **Rollover:** generate enough events to trigger the size policy, and verify archives match `%d`/`%i` and retention after rollover; do not judge solely from the sample file name pattern.
6. **Metadata:** are timestamp, level, thread, logger, exception stack trace, and MDC/trace ID accurate from the moment the event is created?
7. **Sink failure:** simulate a full disk in a test environment or change write permissions, then observe status/error reporting and impact on request latency.
8. **Shutdown:** perform a graceful shutdown with a backlog, measure drain time, and confirm any loss policy is acceptable.

Do not use a log line "printed to the terminal" as proof that the file or OTLP received the event: each appender is a separate delivery path.

## 13. Common Configuration Mistakes

| Symptom | Typical Cause | How to Verify / Fix |
| --- | --- | --- |
| Console logs appear, but file is empty | File appender not referenced; path not writable; filter/level | Check runtime config and directory permissions, test with an event at the right level |
| DEBUG is not written even though file "allows DEBUG" | Logger effective level is INFO | Lower the logger/package level, then check file-side filters |
| INFO still appears on console | Missing ThresholdFilter/reference level, or another console appender exists | Print attached appenders, inspect effective config |
| Logs appear twice | Appender referenced both directly and via root/async; additivity; two pipelines | Inspect routing paths and collectors |
| Incomplete stack traces | Pattern/layout does not handle throwables; exception logged with wrong parameter | Use the overload accepting `Throwable`, inspect the actual encoder/layout |
| File grows unbounded | Using plain `FileAppender` or missing retention/delete | Enable real rolling + retention and monitor disk |
| Archives overwrite each other | Missing `%i` when combining time/size; colliding patterns across instances | Check `fileNamePattern` and per-process paths |
| Slow logging despite async | Sink bottleneck fills queue, blocking producer | Measure queue depth, full-queue policy, and actual I/O |
| MDC/`trace_id` empty in file | Context not set/propagated, or wrong pattern | Check producer context, instrumentation, and MDC key |
| XML configuration not applied | Wrong filename, backend, package binding, or syntax error | Check backend startup status/config debug output |

Avoid having both Logback and Log4j 2 bindings active at the same time; SLF4J should have only one appropriate provider. When using Spring Boot, do not edit `logback-spring.xml` and `log4j2.xml` at the same time and guess from whichever file "looks right" — verify which backend the application actually loaded.

## 14. Workflow for Designing Per-Appender Configuration

A practical sequence when designing:

1. **List outputs:** console, rolling application file, audit file, collector, management system.
2. **Specify which events go to each destination:** log levels, namespaces, environments, sensitive data policies.
3. **Set logger levels low enough to emit required events**, then apply per-destination filters/reference levels.
4. **Define format/schema** for each destination, ensuring reader compatibility and trace correlation.
5. **Set rotation, retention, write permissions, and resource limits**, especially for files and async queues.
6. **Verify additivity/routing** so no events are lost or unexpectedly duplicated.
7. **Test load, failures, and graceful shutdown**, verifying event counts in/out and log loss behavior.

A configuration is considered correct when logs reach the **right destination, at the right level, in the right format**, with well-understood resource limits and application impact. Appenders are where per-output policies are attached; logger levels and routing determine the event stream to which those policies apply.

## References

- [Logback – Architecture: logger level and additivity](https://logback.qos.ch/manual/architecture.html)
- [Logback – RollingFileAppender, rolling policies, and retention](https://logback.qos.ch/manual/appenders-rolling.html)
- [Logback – Filter, ThresholdFilter, LevelFilter](https://logback.qos.ch/manual/filters.html)
- [Apache Log4j 2 – Configuring loggers, AppenderRef, additivity](https://logging.apache.org/log4j/2.x/manual/configuration.html)
- [Apache Log4j 2 – Rolling file appenders and triggering policies](https://logging.apache.org/log4j/2.x/manual/appenders/rolling-file.html)
- [JDK 21 – java.util.logging.Handler](https://docs.oracle.com/en/java/javase/21/docs/api/java.logging/java/util/logging/Handler.html)
- [JDK 21 – java.util.logging.FileHandler](https://docs.oracle.com/en/java/javase/21/docs/api/java.logging/java/util/logging/FileHandler.html)
