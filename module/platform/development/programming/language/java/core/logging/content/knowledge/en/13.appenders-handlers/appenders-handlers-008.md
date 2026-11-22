# Multiple Appenders in Java Logging

## 1. What Are Multiple Appenders?

In a logging system, an **appender** is the component that receives log events from a logger and delivers them to an **output destination** such as the console, a file, or a log collection system. **Multiple appenders** means that a single logger or logger configuration can distribute **the same event** to two or more destinations, rather than forcing business code to call a separate logger for each place it wants to write.

For example, in an order-processing application:

- `INFO`, `WARN`, and `ERROR` are sent to the **console** for runtime observation.
- `WARN` and `ERROR` are also saved to a **file** for investigation.
- If the infrastructure needs structured data, another collection destination can receive events in JSON format.

```text
                           A WARN Event
                                │
                              Logger
                                │
                ┌───────────────┴───────────────┐
                ▼                               ▼
        Console Appender                  File Appender
         INFO and above                  WARN and above
                │                               │
                ▼                               ▼
              stdout                      warnings.log
```

When the same `WARN` appears **once on the console and once in the file**, that is **intentional fan-out**. When it appears **twice on the same console** because a child logger and the root logger both invoke the same appender, that is usually **duplicate logging caused by configuration**.

**Terminology note:** Log4j2 and Logback call the log-output component an **Appender**; the JDK standard library `java.util.logging` (JUL) calls the equivalent component a **Handler**. This lesson uses Log4j2 for the main examples, then compares it with Logback and JUL. The three frameworks do not share the same configuration syntax.

## 2. When Do You Need Multiple Appenders?

Some common use cases:

| Need | Possible Logging Destination | Points to Manage |
| --- | --- | --- |
| Observing the application during development | Console | Readable log levels, not too much noise |
| Tracking errors on a server | Console + RollingFile | Rotation, disk space, write permissions |
| Collecting logs from containers | Stdout/stderr → collector | Format, service labels, instance |
| Analyzing log data by field | JSON appender/encoder or collector | Schema, correlation ID, sensitive data |
| Auditing with dedicated requirements | Separate audit destination | Permissions, retention, integrity; do not treat regular logs as durable audit records |

More appenders are not always better. If the platform already captures stdout, forwards it to a centralized system, and replicates it across multiple storage backends, adding a network appender inside the JVM can increase complexity and cause duplicate storage. Before configuring, determine **who is responsible for final delivery**: the application, the collector, or the deployment platform.

### Components in the Log Pipeline

- **Logger:** receives calls like `LOG.info(...)` and `LOG.error(...)` and determines the effective level.
- **Event:** contains the level, message, logger name, thread, exception, context, and framework-specific metadata.
- **Appender:** forwards an event to a destination; a single appender can be referenced by multiple loggers.
- **AppenderRef:** in Log4j2, connects a logger/root configuration to a declared appender.
- **Layout/encoder:** formats the content when writing.
- **Filter:** accepts, denies, or passes an event on for further evaluation.
- **Root logger:** the top-level configuration and the point that can receive events from child loggers via the logger hierarchy.

**Business code emits events; logging configuration chooses destinations.** That is why you should not create separate `consoleLogger` and `fileLogger` instances and call both for every event.

## 3. Logger Levels and Appender Filtering Are Different

This is the most common configuration mistake when using multiple destinations.

Suppose a logger has level `DEBUG`. That **does not mean** every appender must print `DEBUG`. A configuration can choose to have the console output only `INFO+` and the file output only `WARN+`. In that case:

| Emitted Event | Accepted by DEBUG Logger? | Console INFO+ | File WARN+ |
| --- | --- | --- | --- |
| `LOG.debug("Cache hit")` | Yes | No | No |
| `LOG.info("Order accepted")` | Yes | Yes | No |
| `LOG.warn("Inventory low")` | Yes | Yes | Yes |
| `LOG.error("Payment failed")` | Yes | Yes | Yes |
| `LOG.fatal("Cannot start")` | Yes | Yes | Yes |

This table assumes the appenders are referenced properly, there are no additional filters, and the destinations are working. **Each AppenderRef/appender filters independently**: an event can be created by a logger yet received by only one appender.

In **Log4j2**, you can set a filter level directly on `AppenderRef`:

```xml
<Root level="debug">
    <AppenderRef ref="Console" level="info"/>
    <AppenderRef ref="WarningFile" level="warn"/>
</Root>
```

This is a **configuration snippet** and does not yet include the declarations of the two appenders. The levels on `AppenderRef` are thresholds for each event-receiving path, whereas `Root level="debug"` is the threshold of the root logger. If root is raised to `ERROR`, `WARN` events are no longer accepted by root; lowering the appender threshold to `WARN` **will not recover** events already filtered out at the logger.

High-level processing flow:

```text
LOG.warn(...)
   │
   ▼
Does the Logger create a WARN event?
   │ Yes
   ▼
WARN Event
   ├─ Console AppenderRef INFO: accepted ──> Console
   └─ WarningFile AppenderRef WARN: accepted ──> File
```

In addition to levels, filters placed on a logger, appender reference, or appender can change the outcome. Therefore, evaluate **each stage** rather than drawing conclusions from the root level alone.

## 4. Log4j2 Java 17 + Maven Example: Console and File

This standalone example uses **Log4j2 API** to emit logs and **Log4j2 Core** to output events. Neither Spring Boot nor SLF4J is required. After one run, logs will appear on the console and in a file, but **the contents of each destination differ** due to level thresholds.

### 4.1. Project Structure

```text
multi-appender-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── demo/
        │       └── MultipleAppendersDemo.java
        └── resources/
            └── log4j2.xml
```

### 4.2. The pom.xml File

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>multi-appender-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.apache.logging.log4j</groupId>
            <artifactId>log4j-api</artifactId>
            <version>2.24.3</version>
        </dependency>
        <dependency>
            <groupId>org.apache.logging.log4j</groupId>
            <artifactId>log4j-core</artifactId>
            <version>2.24.3</version>
            <scope>runtime</scope>
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
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

Versions are pinned so the example has a clear dependency set; they are **not a claim about the latest versions**. In a real project, align Log4j2 versions with your dependency management configuration and maintained patches.

### 4.3. The src/main/resources/log4j2.xml File

```xml
<?xml version="1.0" encoding="UTF-8"?>
<Configuration status="WARN">
    <Appenders>
        <Console name="Console" target="SYSTEM_OUT">
            <PatternLayout pattern="%level | %msg%n"/>
        </Console>

        <File name="WarningFile"
              fileName="logs/application.log"
              append="false">
            <PatternLayout pattern="%level | %msg%n"/>
        </File>
    </Appenders>

    <Loggers>
        <Root level="debug">
            <AppenderRef ref="Console" level="info"/>
            <AppenderRef ref="WarningFile" level="warn"/>
        </Root>
    </Loggers>
</Configuration>
```

What this configuration means:

1. `Console` writes to `SYSTEM_OUT`. `WarningFile` writes to `logs/application.log` relative to the working directory.
2. Both use `PatternLayout` to print a single line in the form `INFO | message`.
3. The root logger allows `DEBUG` and above so events reach the distribution step.
4. `AppenderRef` `Console` forwards only `INFO`/`WARN`/`ERROR`/`FATAL`.
5. `AppenderRef` `WarningFile` forwards only `WARN`/`ERROR`/`FATAL`.
6. `append="false"` causes the **demo** file to be overwritten when the appender initializes, so file results do not accumulate across runs. For a real application, **do not use this option if you need to preserve history**; configure appropriate append/rolling behavior instead.

This is a minimal example of log distribution, without a rolling policy, JSON, or exception stack traces. Later sections introduce those elements as needed.

### 4.4. The src/main/java/demo/MultipleAppendersDemo.java File

```java
package demo;

import org.apache.logging.log4j.LogManager;
import org.apache.logging.log4j.Logger;

public final class MultipleAppendersDemo {
    private static final Logger LOG =
            LogManager.getLogger(MultipleAppendersDemo.class);

    public static void main(String[] args) {
        String orderId = "ORD-42";

        LOG.debug("Cart validation started");
        LOG.info("Order {} accepted", orderId);
        LOG.warn("Inventory below threshold: {}", 2);
        LOG.error("Payment gateway unavailable for {}", orderId);

        System.out.println("application-finished");
    }
}
```

### 4.5. Running and Inspecting Both Destinations

With JDK 17+ and Maven, run in the `multi-appender-demo` directory:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.MultipleAppendersDemo
```

**Stdout produced by the program and the Console appender**, ignoring Maven's own messages:

```text
INFO | Order ORD-42 accepted
WARN | Inventory below threshold: 2
ERROR | Payment gateway unavailable for ORD-42
application-finished
```

**Contents of `logs/application.log`:**

```text
WARN | Inventory below threshold: 2
ERROR | Payment gateway unavailable for ORD-42
```

View the file on Linux/macOS:

```bash
cat logs/application.log
```

Or in PowerShell:

```powershell
Get-Content logs/application.log
```

The output matches when the environment loads `log4j2.xml` as written, the filesystem allows creating the file, and no external configuration overrides it. If `DEBUG` appears on the console, the application may be using a different configuration or another appender. If the file is empty or does not exist, check the ref level, file path, write permissions, and status logging.

**Try it yourself:** change `<AppenderRef ref="WarningFile" level="warn"/>` to `level="info"`, run again, and compare the file: the file should now include the `INFO` line as well. Change root to `level="error"`: neither `INFO` nor `WARN` appears even though both `AppenderRef`s still have lower thresholds.

## 5. You Do Not Need a Separate Logger per Destination

If you want to write the same event to both the console and a file, you should not write:

```java
consoleLogger.warn("Inventory low");
fileLogger.warn("Inventory low");
```

Those two calls are **two separate events**, coupling business logic to log output. Every time you add a third destination, you would have to change source code. With multiple appenders, you only need:

```java
LOG.warn("Inventory low");
```

and the configuration handles the fan-out. This snippet assumes the logger variable is already declared. **Destinations and formatting belong to the backend; event content belongs to business logic.** When you want to send logs to a centralized collection system, you can change the appender/collector configuration without modifying every `LOG.warn(...)` call.

A single appender can also be referenced by **multiple loggers**. There is no need to create a separate physical Console appender for each class; sharing a destination at the root/package level is usually simpler and more consistent.

## 6. Additivity: Why Is a Line Printed Twice?

**Additivity** is the mechanism that forwards events from a child logger configuration to the appenders of a parent logger or the root logger. It lets child loggers **inherit shared output paths**, but it can also cause duplicate logs.

A Log4j2 example that easily produces duplicates if the `Console` appender is declared on both the `demo.payment` logger and root:

```xml
<Loggers>
    <Logger name="demo.payment" level="debug">
        <AppenderRef ref="Console"/>
    </Logger>
    <Root level="info">
        <AppenderRef ref="Console"/>
    </Root>
</Loggers>
```

This is an **XML snippet**, assuming the `Console` appender exists. The child logger can process an event at `Console`, and then due to default additivity, pass it up to root and process it again through `Console`.

**Two ways to fix this:**

- **Attach the appender only on root:** the child logger sets its own level when needed, without referencing the same console again.
- **Have the child logger manage its own destinations:** set `additivity="false"` and reference **all** destinations it needs.

Example of the second approach:

```xml
<Logger name="demo.payment" level="debug" additivity="false">
    <AppenderRef ref="Console" level="info"/>
    <AppenderRef ref="WarningFile" level="warn"/>
</Logger>
```

**Warning:** if you disable additivity but only reference `Console`, events from this logger will not reach `WarningFile` if it is only attached to root. Do not use `additivity="false"` mechanically; trace the actual event path first.

Distinguish clearly between:

- **Proper fan-out:** one `WARN` appears on the console and in the file, once at each destination.
- **Unwanted duplicate:** one `WARN` appears twice in the console because two levels in the hierarchy reference the console.
- **Duplicate from application code:** an exception is logged in the repository, service, and controller, creating three independent events, and each event is then distributed to two appenders.

## 7. Each Appender Can Have Its Own Layout and Policy

An event does not have to use the same format at every destination:

| Destination | Suggested Format | Why? |
| --- | --- | --- |
| Console | Short: level, logger, message | Easy to read in the terminal |
| Investigation file | Timestamp, thread, logger, message, stack trace | Helps trace errors |
| Collector | Structured JSON matching a schema | Field-based search and correlation ID |
| Dedicated audit | Selected fields, protected | Compliance and traceability requirements |

A Log4j2 configuration snippet illustrating two different patterns, placed inside the `<Appenders>` section of a complete file:

```xml
<Console name="ReadableConsole" target="SYSTEM_OUT">
    <PatternLayout
        pattern="%d{HH:mm:ss} %-5level %logger{1} - %msg%n"/>
</Console>

<File name="DetailedFile" fileName="logs/detailed.log">
    <PatternLayout
        pattern="%d{ISO8601} %-5level [%t] %logger requestId=%X{requestId} - %msg%n%ex"/>
</File>
```

Some pattern tokens: `%d` is the timestamp; `%t` is the thread name; `%logger` is the logger name; `%msg` is the message; `%n` is a newline; `%ex` is the exception stack trace; `%X{requestId}` is a context field if set.

In Log4j2, the `ThreadContext` API provides correlation data; similarly, the SLF4J/Logback ecosystem commonly refers to **MDC (Mapped Diagnostic Context)**. Context behavior can differ across backends and bridges. For a field to appear at a destination, **that destination's** layout/encoder must support it. Do not assume that having `requestId` in memory will make every appender print it automatically.

To use JSON output, choose an appropriate module/layout such as `JsonTemplateLayout` and the `log4j-layout-template-json` module (if supported by your version/design), rather than assuming any appender produces JSON by default. Sensitive fields should be excluded or masked when emitting the event; relying solely on the layout is not a complete safeguard.

## 8. RollingFile: Do Not Let Files Grow Forever

A plain `File` appender in a demo is enough to understand event distribution, but it does not automatically guarantee rotation or retention. In production, **RollingFile** is usually more suitable than an unboundedly growing file.

Log4j2 snippet inside `<Appenders>`:

```xml
<RollingFile name="RollingFile"
             fileName="logs/application.log"
             filePattern="logs/archive/app-%d{yyyy-MM-dd}-%i.log.gz">
    <PatternLayout
        pattern="%d{ISO8601} %-5level %logger - %msg%n"/>
    <Policies>
        <SizeBasedTriggeringPolicy size="10 MB"/>
        <TimeBasedTriggeringPolicy/>
    </Policies>
    <DefaultRolloverStrategy max="5"/>
</RollingFile>
```

And inside a logger/root:

```xml
<AppenderRef ref="RollingFile" level="warn"/>
```

`RollingFile` can rotate by size, time, and the configured strategy. However, `max="5"` in the rollover strategy **does not automatically mean keeping logs for exactly five days**. You need to verify the pattern, index count, file deletion policy, and actual permissions.

In containers, some systems prefer stdout/stderr collected by the platform. Writing both to a local file and an external collector can increase disk usage and I/O without any benefit if local files are not persisted after a container is replaced.

## 9. Logback Example: Same Concept, Different Syntax

If an application uses the **SLF4J** facade and the **Logback Classic** backend, appenders still play a similar role, but the configuration file is `logback.xml`, not `log4j2.xml`.

The following XML is an **illustrative Logback configuration file**:

```xml
<configuration>
    <appender name="CONSOLE" class="ch.qos.logback.core.ConsoleAppender">
        <filter class="ch.qos.logback.classic.filter.ThresholdFilter">
            <level>INFO</level>
        </filter>
        <encoder>
            <pattern>%level | %msg%n</pattern>
        </encoder>
    </appender>

    <appender name="WARNING_FILE" class="ch.qos.logback.core.FileAppender">
        <file>logs/warnings.log</file>
        <append>true</append>
        <filter class="ch.qos.logback.classic.filter.ThresholdFilter">
            <level>WARN</level>
        </filter>
        <encoder>
            <pattern>%level | %msg%n</pattern>
        </encoder>
    </appender>

    <root level="DEBUG">
        <appender-ref ref="CONSOLE"/>
        <appender-ref ref="WARNING_FILE"/>
    </root>
</configuration>
```

`ThresholdFilter` on `CONSOLE` allows only `INFO` and above, while the filter on the file allows only `WARN` and above. Root `DEBUG` is the entry threshold of the pipeline.

**Do not copy Log4j2's `level` attribute from `AppenderRef` onto Logback's `appender-ref`** and expect the same threshold to be applied. Syntax and filters differ between backends. Logback's `FileAppender` also does not roll automatically; when file rotation is needed, use `RollingFileAppender` with a properly configured rolling policy.

If a Spring Boot application uses Logback by default, replacing the main example's `log4j2.xml` with the Logback file above without changing the backend means the Log4j2 XML has no effect. Always verify which implementation is actually loaded.

## 10. JUL: Multiple Handlers Instead of Multiple Appenders

The JDK's `java.util.logging` (JUL) uses `Handler` to route logs to multiple destinations. The API names differ, but the principle of **one logger → multiple receivers** still holds.

Complete Java 17 example with no dependencies outside the JDK. Create `MultiHandlerDemo.java`:

```java
import java.io.IOException;
import java.util.logging.ConsoleHandler;
import java.util.logging.FileHandler;
import java.util.logging.Formatter;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class MultiHandlerDemo {
    public static void main(String[] args) throws IOException {
        Logger logger = Logger.getLogger("demo.MultiHandlerDemo");
        logger.setLevel(Level.ALL);
        logger.setUseParentHandlers(false);

        Formatter shortFormat = new Formatter() {
            @Override
            public String format(LogRecord record) {
                return record.getLevel().getName() + " | "
                        + formatMessage(record) + System.lineSeparator();
            }
        };

        ConsoleHandler console = new ConsoleHandler();
        console.setLevel(Level.INFO);
        console.setFormatter(shortFormat);

        FileHandler file = new FileHandler("jul-events.log", false);
        file.setLevel(Level.WARNING);
        file.setFormatter(shortFormat);

        logger.addHandler(console);
        logger.addHandler(file);

        try {
            logger.fine("Hidden detail");
            logger.info("Order accepted");
            logger.warning("Inventory low");
            logger.severe("Payment failed");
            System.out.println("jul-finished");
        } finally {
            logger.removeHandler(console);
            logger.removeHandler(file);
            console.close();
            file.close();
        }
    }
}
```

Run:

```bash
javac MultiHandlerDemo.java
java MultiHandlerDemo
```

**`ConsoleHandler` lines on stderr:**

```text
INFO | Order accepted
WARNING | Inventory low
SEVERE | Payment failed
```

**Stdout printed by the program:**

```text
jul-finished
```

**The `jul-events.log` file:**

```text
WARNING | Inventory low
SEVERE | Payment failed
```

JUL's `ConsoleHandler` writes to **stderr** by default, unlike `SYSTEM_OUT` in the Log4j2 example. Because stderr and stdout are two separate streams, do not assume their combined display order is strictly deterministic in every terminal. Here, `FileHandler` writes a new file and may create a temporary internal lock file while running; the example closes the handlers when finished.

Notice `logger.setUseParentHandlers(false)` to prevent records from continuing to JUL's default root handler, which could cause duplicate output. This is a standalone program example; in a real application, save/restore configuration when needed and manage handlers according to the application lifecycle. **The logger level and each handler's level are two separate filtering steps**, following the same principle as multiple appenders.

## 11. AsyncAppender: Distribution Does Not Always Mean Synchronous

When there are multiple destinations, total overhead can increase: each event may need to be formatted multiple times and written to multiple devices. If one appender writes slowly to a file or network, log-processing time can affect business threads.

Log4j2 provides both **AsyncAppender** and **AsyncLogger**. They are not the same component:

- **AsyncAppender:** an asynchronous appender that receives events and forwards them through a queue to target appenders.
- **AsyncLogger:** an asynchronous processing mechanism at the logger layer, with its own version-specific dependency and configuration requirements.

Illustrative XML snippet:

```xml
<Async name="AsyncWarningFile">
    <AppenderRef ref="RollingFile"/>
</Async>
```

A logger that wants asynchronous output to the file should reference `AsyncWarningFile` instead of referencing `RollingFile` directly on the same logging path. If **both** are referenced, a single event can be written to the file **twice**.

There is no guarantee that async is **always faster**: you must measure throughput, latency, and queue saturation. When the JVM crashes or is killed abruptly, events still in the queue/buffer may not reach their destination. When multiple appenders run asynchronously, the observed order of records between two destinations can also differ. Test overflow behavior, shutdown/flush, and real-world operability.

## 12. Security and Reliability When Writing to Multiple Destinations

**Multiple copies of logs mean multiple places where access must be controlled.** An event can contain stack traces, file paths, queries, or user data. Console, file, and collector destinations may have different retention periods and read permissions. Do not log passwords, tokens, API keys, authentication cookies, or sensitive personal data expecting an appender alone to mask them.

Key principles:

1. **Sanitize data at the source:** do not construct messages containing secrets; use safe correlation IDs.
2. **Set appropriate levels per destination:** avoid sending sensitive `TRACE`/`DEBUG` details to files or collectors unnecessarily.
3. **Bound file growth:** configure rotation, retention, read/write permissions, and disk monitoring.
4. **Check appender failures:** unwritable files, unavailable collectors, full queues.
5. **Do not confuse two destinations with durable backup:** console + file on the same machine does not replace transactions, the outbox pattern, or tamper-evident audit storage.
6. **Protect configuration:** only authorized users should be able to change appenders, levels, and log destinations.
7. **Test exception handling:** the same `Throwable` can go to multiple layouts; ensure stack traces are neither dropped nor accidentally printed twice.
8. **Limit duplicate logging in application code:** if both the repository and controller log the full exception and each event goes to two appenders, line counts can grow rapidly.

For events with mandatory audit requirements, you need a reliable storage design with dedicated integrity policies, access controls, and retention. **Regular appenders do not by themselves provide immutable audit guarantees**.

## 13. Troubleshooting Multiple Appenders

| Symptom | Common Cause | How to Fix |
| --- | --- | --- |
| `INFO` appears on console but not in file | File `AppenderRef` is set to `WARN` | If `INFO` is needed in the file, adjust its threshold |
| `DEBUG` does not appear even though root is `DEBUG` | `AppenderRef` thresholds at `INFO`/`WARN` block `DEBUG` | Check the level at each destination |
| `WARN` appears twice on console | Both child logger and root reference console with additivity enabled | Keep a single reference path or disable additivity when all destinations are declared |
| `WARN` appears once on console, once in file | Two appenders are configured to receive `WARN` | This is proper fan-out |
| File is lost after each run | `append="false"` overwrites the file | Use append/rolling as required by operations |
| File is not created | Configuration not loaded, missing permissions, wrong path, or no events pass filters | Check runtime config, directory, and status logs |
| File layout is missing stack traces | `Throwable` not passed or layout does not output exceptions | Use an overload accepting `Throwable`; check converters |
| Adding async writes to the file twice | Both `AsyncAppender` and target appender are referenced | Keep a single path to the sink when needed |
| File grows without bound | Only `FileAppender` is used, without rolling/retention | Configure `RollingFile` and verify rotation |
| `log4j2.xml` changes have no effect on output | Application uses Logback/JUL or a different config file | Verify the actual backend and runtime classpath |
| Lines are missing when JVM stops | Queue/buffer not flushed, or destination failure | Test shutdown and durability policies |
| All appenders are silent | Events are filtered out at the logger from the start | Check logger level/filters before inspecting sinks |

### Event-Path Checklist

1. Check whether the application actually uses Log4j2, Logback, or JUL.
2. Identify the logger name and effective level.
3. Verify the actual configuration file loaded at runtime.
4. List all `AppenderRef`/handler entries on the current logger and any parent loggers that can receive events.
5. Check `additivity` (Log4j2/Logback) or `useParentHandlers` (JUL).
6. Check the level/filter on **each** `AppenderRef`/appender.
7. Check layouts, exception handling, context (`MDC`/`ThreadContext`), and destination paths.
8. Check backend status, write permissions, file rotation, and collectors.
9. Emit test events at `DEBUG`/`INFO`/`WARN`/`ERROR` and compare console output with the file.

## 14. Self-Check Questions

**Question 1:** Root logger is `DEBUG`, Console `AppenderRef` is `INFO`, File `AppenderRef` is `WARN`. Where does `LOG.info(...)` go?  
**Answer:** Console only. The file blocks it because of the `WARN` threshold.

**Question 2:** With the same configuration, where does `LOG.error(...)` go?  
**Answer:** Both console and file, assuming no other filters block it and both destinations are working.

**Question 3:** Why does `LOG.debug(...)` not appear even though root is at `DEBUG`?  
**Answer:** Both destinations' `AppenderRef` thresholds are set higher than `DEBUG`.

**Question 4:** If a `WARN` event appears twice on the console, is that necessarily proper fan-out?  
**Answer:** No. The intended fan-out in the example is one copy on the console and one in the file. Two lines on the same console can be caused by additivity or logging twice in code.

**Question 5:** When should you use `additivity="false"`?  
**Answer:** When a logger has its own appenders and you do not want events to continue up to parent/root appenders; you must declare all destinations you want to keep.

**Question 6:** In JUL, what concept corresponds to multiple appenders?  
**Answer:** Multiple `Handler` instances; you can use `Logger.addHandler(...)` and set a level and formatter for each handler.

**Question 7:** Is having two appenders enough to guarantee logs are never lost?  
**Answer:** No. Infrastructure failures, write permissions, crashes, or buffering can still lose logs.

**Question 8:** Why should you avoid `append="false"` on a production log file that needs to retain history?  
**Answer:** Because the file contents can be overwritten every time the appender initializes; you need properly designed append, rolling, and retention policies.

**Key takeaway:** **Multiple appenders allow a single log event to be distributed to multiple independent destinations**. Operating them reliably requires considering **logger level**, **per-destination thresholds/filters**, **layouts**, **additivity**, and file/async lifecycles. Distinguish proper fan-out from duplicate logs, protect sensitive data, and verify the output of each appender.
