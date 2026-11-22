# What Is an Appender? Role, Configuration, and Practice in Java Logging

## 1. Concept

In logging systems such as **Apache Log4j 2** and **Logback**, an **Appender** is the component responsible for **delivering log events to a destination**. That destination can be stdout/stderr, a file, a network collector, a monitoring system, or another appender. An appender typically works with a layout or encoder to turn a log event into text or structured data that the target destination can consume.

For example, a Java application writes:

```java
// Example in an application class that already has a Log4j 2 logger.
logger.info("Order {} accepted", "O-17");
```

The statement above **does not decide where the log is sent**. The logging configuration determines which logger receives the event, which filters the event passes through, and **which appenders are invoked**.

An application can send INFO events to the console while writing only WARN/ERROR events to a file. It can also route the same event to two appenders to serve two different purposes.

**Appenders do not create business events, do not retry business operations, do not commit databases, and do not guarantee audit evidence on their own.** They are components of the system observability pipeline. The return of a `logger.info(...)` call does not mean a central storage system has confirmed that the data is durably persisted.

## 2. Distinguishing Logging Components

```text
Java application / library
          |
          | logger.info(...), logger.warn(...)
          v
Logger / LoggerConfig
  - logger name
  - level and filter
          |
          v
LogEvent: level, message, timestamp,
          exception, context...
          |
          +----------------------------+
          |                            |
       AppenderRef                 AppenderRef
       Console                     File (WARN+)
          |                            |
       Appender Console            Appender File
          |                            |
       PatternLayout               PatternLayout
          |                            |
        stdout                     log file
          |                            |
       collector                collector/shipper
          +----------------------------+
                         |
                  search/storage
```

| Component | Primary Responsibility |
| --- | --- |
| **Logger** | API/code called to emit events; has a name and a level threshold. |
| **LogEvent** | Details of an event: timestamp, level, logger name, message, exception, context. |
| **AppenderRef** (Log4j 2) | Links a logger to an appender by name; can specify its own level/filter limits. |
| **Appender** | Receives events from the pipeline and outputs them to a specific destination or downstream appender. |
| **Layout / Encoder** | Formats an event into text or bytes (pattern, JSON, etc.). |
| **Filter** | Accepts or drops events according to policy. Can be placed at multiple layers. |
| **Collector / storage** | Collects logs, ships, stores, indexes, and makes them queryable after the appender has emitted them. |

In **Log4j 2**, an appender implements `org.apache.logging.log4j.core.Appender`; common implementations can extend `AbstractAppender` and use a `Layout` for formatting. In **Logback**, the corresponding interface is `ch.qos.logback.core.Appender<E>`, with the key method `doAppend(E event)`.

A logger can have multiple appenders, and an appender can be referenced by multiple loggers. **Each appender has a name so configuration can reference it**, such as `Console`, `WarningFile`, or `RemoteLogs`.

## 3. How Does an Appender Differ from a Logger?

You can remember it as:

- **Logger asks:** "What event happened, at what level, and from which component?"
- **Appender asks:** "Where should an accepted event go, and how should it be formatted/written?"

Suppose the logger `com.example.payment` is set to INFO and has two appenders:

- Console receives every event the logger allows, so INFO/WARN/ERROR all go to the console.
- File only receives WARN and above, so INFO is not written to the file.

A DEBUG event is blocked by the **logger** before reaching either destination. An INFO event is accepted by the logger but blocked on **the path to the file** due to the WARN threshold. This shows that **enabling INFO on a logger does not require every appender to also write INFO**.

Backends may allow filters in multiple places: the logger, the appender reference, or the appender itself. When investigating missing logs, you need to identify the exact layer that dropped the event.

## 4. Common Types of Appenders

| Appender | Destination / Function | When to Use | Main Limitations |
| --- | --- | --- | --- |
| **ConsoleAppender** | Stdout or stderr. | Containers, development, and operations with a stream collector. | Does not guarantee long-term retention on its own. |
| **FileAppender** | A single file. | Applications needing local logs or files tailed by a collector. | Does not rotate files automatically by default. |
| **RollingFileAppender** | Active log file + rotated archives by policy. | Steadily growing logs that require rotation. | Must manage retention, archives, and disk space. |
| **AsyncAppender** | Buffers/queues events and forwards them to downstream appenders. | Decouple sink write latency from business threads. | Bounded queue; risk of overload and data loss on crash. |
| **Socket/network appender** | Sends logs over a network connection. | External collector or logging service. | Depends on timeouts, TLS, retry/ACK, and connectivity. |
| **Specialized appenders** | Database, email, or other systems depending on plugin/backend. | Integrating with a specialized sink. | Not guaranteed to have transactional durability or low cost by default. |

### ConsoleAppender

A console appender typically writes to `System.out` or `System.err`. With Docker/Kubernetes, this is the standard way for the platform to collect logs. However, a console appender **only writes logs to a stream**; to keep logs searchable after a container is destroyed, you need a separate collector and storage policy.

### FileAppender and RollingFileAppender

A file appender writes to a configured file path. You must verify write permissions, file path, encoding, flushing, and disk space. If the file keeps growing, consider `RollingFileAppender` with a *triggering policy* (by size, time, or another appropriate condition).

Illustrative example in Log4j 2:

```xml
<RollingFile name="Rolling"
             fileName="logs/app.log"
             filePattern="logs/app-%d{yyyy-MM-dd}-%i.log.gz">
    <PatternLayout pattern="%d{ISO8601} %-5p %c - %m%n"/>
    <Policies>
        <SizeBasedTriggeringPolicy size="10 MB"/>
    </Policies>
    <DefaultRolloverStrategy max="10"/>
</RollingFile>
```

This is a **configuration snippet** inside Log4j 2's `<Appenders>`, not a complete XML file. The `max="10"` setting relates to the rollover/archive count mechanism; **it does not mean data is retained for exactly 10 days**. Time-based retention and archive deletion must be configured and verified separately.

### AsyncAppender

An `AsyncAppender` typically places a buffer in front of target appenders so the thread calling the logger does not always have to wait on sink I/O. If downstream appenders are slower than the event generation rate, the buffer will fill up. Depending on the framework and policy, the calling thread may block, fall back, or drop events. Do not treat `AsyncAppender` as durable storage.

In Log4j 2, **Async Logger** (which uses LMAX Disruptor at the logger level) is a different mechanism from `AsyncAppender`. Do not stack two asynchronous mechanisms just expecting better performance without measuring latency, throughput, queue drops, and shutdown behavior.

## 5. Routing via AppenderRef, Levels, and Filters in Log4j 2

Log4j 2 configures appenders under `<Appenders>` and references them from `<Loggers>`:

```xml
<Appenders>
    <Console name="Console" target="SYSTEM_OUT">
        <PatternLayout pattern="%p|%m%n"/>
    </Console>
</Appenders>
<Loggers>
    <Root level="INFO">
        <AppenderRef ref="Console"/>
    </Root>
</Loggers>
```

This is an **XML snippet**; to run standalone, it must be placed inside a complete `<Configuration>` element. `Console` is the appender name; `ref="Console"` is the link. If the `ref` name is misspelled, the logger will not be connected to the intended appender.

Log4j 2 supports setting `level` directly on `AppenderRef`:

```xml
<Logger name="com.example.order" level="INFO"
        additivity="false">
    <AppenderRef ref="Console"/>
    <AppenderRef ref="WarningFile" level="WARN"/>
</Logger>
```

With this configuration:

- DEBUG is lower than INFO, so the logger does not forward it.
- INFO reaches Console but does not reach WarningFile.
- WARN and ERROR reach both, unless dropped by another filter.

**The level on a logger and the level on an AppenderRef serve different purposes.** Additionally, filters can run at the logger configuration, `AppenderRef`, and appender levels. An `AppenderRef` level is a convenient way to trim unwanted events at a specific destination route; not every backend uses this syntax.

If you need complex filtering by event, marker, or context, use framework-supported filters rather than matching free-form message strings alone. However, when the concern is leaking sensitive data, **prevent the data from entering the log at the source**—do not rely on a collector to filter it out after console or file output has already received it.

## 6. Hands-On Java 17 Example: Console and File Appenders

This hands-on exercise creates a Java 17 Maven project using **Log4j 2 API + Core**. The same logger writes INFO/WARN/ERROR to the console, while **only WARN/ERROR are sent to a file**. This is a **synchronous** appender example without `AsyncAppender`.

The example pins `log4j-api:2.26.1` and `log4j-core:2.26.1`, which are released versions. Fixed version numbers keep the example reproducible, **which does not mean they are always the latest versions**; real-world applications should follow a BOM and security update policies.

### 6.1. Directory Structure

```text
appender-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── demo/
        │       └── AppenderDemo.java
        └── resources/
            └── log4j2.xml
```

### 6.2. The pom.xml File

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>appender-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>17</maven.compiler.release>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.apache.logging.log4j</groupId>
            <artifactId>log4j-api</artifactId>
            <version>2.26.1</version>
        </dependency>
        <dependency>
            <groupId>org.apache.logging.log4j</groupId>
            <artifactId>log4j-core</artifactId>
            <version>2.26.1</version>
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
                <version>3.3.0</version>
                <configuration>
                    <mainClass>demo.AppenderDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

### 6.3. The src/main/resources/log4j2.xml File

```xml
<?xml version="1.0" encoding="UTF-8"?>
<Configuration>
    <Appenders>
        <Console name="Console" target="SYSTEM_OUT">
            <PatternLayout pattern="CONSOLE|%p|%m%n"/>
        </Console>

        <File name="WarningFile"
              fileName="warning-demo.log"
              append="false">
            <PatternLayout pattern="FILE|%p|%m%n"/>
        </File>
    </Appenders>

    <Loggers>
        <Logger name="demo.AppenderDemo" level="INFO"
                additivity="false">
            <AppenderRef ref="Console"/>
            <AppenderRef ref="WarningFile" level="WARN"/>
        </Logger>
        <Root level="ERROR">
            <AppenderRef ref="Console"/>
        </Root>
    </Loggers>
</Configuration>
```

Reading the configuration from top to bottom:

1. `<Console>` defines an appender writing to stdout using the `CONSOLE|...` layout.
2. `<File>` defines an appender writing to `warning-demo.log` in the program's working directory.
3. `append="false"` lets the demo start a fresh file instead of appending to an old one; **do not copy this into production if you need to preserve log history**.
4. `Logger name="demo.AppenderDemo"` matches the Java class name and has level INFO; DEBUG is dropped at the logger.
5. Console has an unrestricted reference; WarningFile has an `AppenderRef` with a WARN threshold.
6. `additivity="false"` prevents events from this logger from propagating up to the root logger and being written to the console twice.
7. The layout intentionally omits timestamps and thread names so the demo stdout can be checked deterministically. In production, you need UTC timestamps, service name, logger name, correlation ID, and other relevant fields.

### 6.4. The src/main/java/demo/AppenderDemo.java File

```java
package demo;

import org.apache.logging.log4j.LogManager;
import org.apache.logging.log4j.Logger;

public final class AppenderDemo {

    private static final Logger LOG =
            LogManager.getLogger(AppenderDemo.class);

    private AppenderDemo() {
    }

    public static void main(String[] args) {
        LOG.debug("Debug detail");
        LOG.info("Order {} accepted", "O-17");
        LOG.warn("Gateway latency high: {} ms", 3000);
        LOG.error("Payment failed for orderId={}", "O-18");

        // Standalone demo: shut down the logging context after the events.
        LogManager.shutdown();
    }
}
```

### 6.5. Build, Run, and Output

In the directory containing `pom.xml`, you need Maven, JDK 17 or newer, and dependency download access:

```bash
mvn -q clean compile exec:java
```

If `log4j2.xml` is loaded properly and no runtime configuration overrides it, the three lines written by the application to **stdout** are:

```text
CONSOLE|INFO|Order O-17 accepted
CONSOLE|WARN|Gateway latency high: 3000 ms
CONSOLE|ERROR|Payment failed for orderId=O-18
```

The contents of `warning-demo.log` after a successful run:

```text
FILE|WARN|Gateway latency high: 3000 ms
FILE|ERROR|Payment failed for orderId=O-18
```

These are **two separate outputs**: three lines on the console and two lines in the file, not five lines on stdout. The build tool may print messages beyond the three application lines if configured differently.

Why does this happen?

| Call | Logger INFO | Console | WarningFile (WARN+) |
| --- | --- | --- | --- |
| `LOG.debug("Debug detail")` | Dropped | No | No |
| `LOG.info("Order...")` | Accepted | Writes INFO | Dropped at AppenderRef |
| `LOG.warn("Gateway...")` | Accepted | Writes WARN | Writes WARN |
| `LOG.error("Payment...")` | Accepted | Writes ERROR | Writes ERROR |

You can change the `AppenderRef` threshold of `WarningFile` to ERROR: the file will only contain the ERROR line while the console output remains unchanged. Conversely, raising the **logger** threshold from INFO to WARN will drop INFO before the event reaches either destination.

**Limitations:** this example does not make HTTP requests, connect to a collector, simulate network failures, or verify durability. It demonstrates appender routing and text formatting. You do not need to instantiate `FileAppender` directly in Java code because the XML configuration manages it.

## 7. Appenders and java.util.logging (JUL) Handlers

The JDK provides `java.util.logging`. In JUL, the component that plays the role equivalent to an appender is **`java.util.logging.Handler`**.

| Concept | Log4j 2 / Logback | JUL |
| --- | --- | --- |
| Log emission point | `Logger` | `java.util.logging.Logger` |
| Event record | `LogEvent` or `ILoggingEvent` | `LogRecord` |
| Delivers record to destination | **Appender** | **Handler** |
| Converts record to text | Layout/Encoder | `Formatter` |
| Severity levels | `WARN`, `ERROR`... | `WARNING`, `SEVERE`... |
| Attaching destination | AppenderRef/Logger config | `logger.addHandler(handler)` |

The following JUL snippet only **illustrates** the handler API within an application (it is not a standalone class):

```java
java.util.logging.Logger jul =
        java.util.logging.Logger.getLogger("demo.order");
java.util.logging.ConsoleHandler sink =
        new java.util.logging.ConsoleHandler();
sink.setLevel(java.util.logging.Level.WARNING);
jul.addHandler(sink);
```

`ConsoleHandler` has its own level threshold. By default, it writes to stderr rather than stdout; parent handlers can also cause a record to be logged multiple times. When you need a standalone runnable JUL demo, you must configure the logger, formatter, handler, propagation, and full lifecycle.

You **cannot cast** `java.util.logging.Handler` to `org.apache.logging.log4j.core.Appender`. The two frameworks share similar concepts, but their APIs are different.

## 8. How Do Logback Appenders Differ from Log4j 2?

If an application uses **SLF4J + Logback**, business code calls SLF4J, and Logback provides the appenders that perform the actual output. A typical configuration file is `logback.xml`:

```xml
<configuration>
    <appender name="CONSOLE"
              class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>CONSOLE|%level|%msg%n</pattern>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
    </root>
</configuration>
```

This is a **separate Logback configuration** example, not `log4j2.xml`. When you want to write only WARN and above to an appender, Logback can use a `ThresholdFilter` inside the appender. Do not assume Log4j 2's `level="WARN"` attribute on `AppenderRef` is handled the same way across all backends.

Regarding classes/APIs:

- Logback: `ch.qos.logback.core.Appender<E>`, `doAppend(E)`, and base classes such as `AppenderBase<E>`/`UnsynchronizedAppenderBase<E>`.
- Log4j 2: `org.apache.logging.log4j.core.Appender`, `append(LogEvent)`, `AbstractAppender`.
- JUL: `java.util.logging.Handler`, `publish(LogRecord)`, `flush()`, `close()`.

In many Java applications, **SLF4J is the facade** and Logback or Log4j 2 is the backend. Having `slf4j-api` on the classpath does not mean the application is using Logback; you must check the actual runtime provider, bridges, and configuration. If an application has multiple providers, logging behavior may not match expectations.

## 9. Layout, Context, and Security

### 9.1. PatternLayout

Example snippet inside a Log4j 2 Console appender:

```xml
<Console name="Console" target="SYSTEM_OUT">
    <PatternLayout pattern="%d{ISO8601} [%t] %-5p %c - %m%n"/>
</Console>
```

Each line includes timestamp, thread, level, logger, and message. Patterns are convenient for human reading, but hard to query deeply when messages concatenate multiple variables or contain delimiters.

### 9.2. JSON / Structured Logging

If you need to filter by service, event code, request ID, order ID, or latency, use a structured layout/encoder suitable for your backend. With Log4j 2, you can use an appropriate JSON layout or `JsonTemplateLayout` with its corresponding module. Here is an example of **desired data**, not the output of the program in section 6:

```json
{
  "timestamp": "2026-11-09T08:00:00Z",
  "level": "WARN",
  "service": "order-service",
  "event": "GATEWAY_LATENCY_HIGH",
  "correlationId": "req-100",
  "orderId": "O-17",
  "durationMs": 3000
}
```

The timestamp and IDs are synthetic data. In a real application, you must take the timestamp from the event, propagate the correlation ID consistently across layers, and avoid leaking context between requests when using thread pools.

### 9.3. Protecting Data Before the Sink

Never log passwords, OTPs, access tokens, refresh tokens, cookies, private keys, or full sensitive request bodies. An appender can write the same message to **multiple destinations**, increasing the blast radius. Use field allowlists where events are created, reliable redaction, transport encryption, and proper access controls on the log store.

With text logs, inputs containing newlines, backslashes, or control characters can make it look like multiple log records exist. Structured encoders must escape properly rather than building JSON manually from untrusted strings. **Filters at the collector run after the appender has already written data to stdout or a file, so they cannot replace leak prevention at the source.**

## 10. Additivity, Duplicate Logs, and Multi-Destination Routing

In Log4j 2 and Logback, loggers are typically organized into a hierarchy by name. For example:

```text
Root
  |
  +-- com.example
       |
       +-- com.example.orders
```

If root references the Console appender and the `com.example.orders` logger also references Console, then when **additivity=true**, an event can pass through the child logger's appenders and then continue to the parent logger's appenders, producing duplicate records.

Configuration:

```xml
<Logger name="com.example.orders"
        level="INFO"
        additivity="false">
    <AppenderRef ref="Console"/>
</Logger>
```

helps isolate the child logger's routing. However, **do not disable additivity on every logger out of habit**: many systems intentionally use an appender at root for general logs while child loggers add dedicated files. What matters is checking which destinations an event is sent to, how many times, and whether that matches your intent.

If you need two different destinations, reference two differently named appenders; do not accidentally create two identical output paths.

## 11. Lifecycle and Logging Failures

### Lifecycle

An appender is configured/initialized, used, and stopped/closed according to the logging context lifecycle. For files or sockets, file descriptors, buffers, connections, and locks must be released. Do not create a new `FileAppender` **per request** to write logs: that approach easily causes resource leaks and file contention.

In applications running inside a framework or container, the logging lifecycle is usually managed by the runtime; avoid manually closing appenders shared across services or classloaders.

### When the Sink Fails

Failure scenarios include permission denied, disk full, invalid file path, network loss, collector timeout, or formatting errors. In many Log4j 2 appenders, depending on `ignoreExceptions`, errors may be logged via the **Status Logger**, contained within the logging subsystem, or propagated to the caller as configured.

**Do not assume calling `logger.error(...)` will throw an exception if a file cannot be written.** With `AsyncAppender`, errors can also occur on a background thread and never return to the request's call stack.

Therefore, you should monitor: events emitted by the application versus events arriving at the sink, appender errors, queue drop counts, ingestion latency, file permissions/disk usage, and collector health.

### Flush Does Not Guarantee Durability

```text
LogEvent -> Appender accepted -> Buffered -> Stream/File write
                                            |
                                      Collector received
                                            |
                                      Storage indexed
```

A flush call may push buffers to the underlying layer, but **it does not automatically mean fsync**, crash-safe persistence on power loss, receipt by the collector, or indexing in storage. Audit logging requires its own evidence-guaranteeing architecture per policy, such as a transactional outbox, append-only storage, integrity controls, and appropriate access permissions. Do not treat a local `FileAppender` as the sole audit source without evaluating the risks.

## 12. Performance: Synchronous vs. Asynchronous Appenders

```text
Synchronous:
request -> logger -> FileAppender -> file/network (can be slow)

Asynchronous:
request -> logger -> AsyncAppender -> bounded queue
                                         |
                                       worker
                                         |
                                     FileAppender
```

A synchronous appender has simpler control flow, but slow I/O can increase request latency. An `AsyncAppender` reduces caller wait time under many conditions, but introduces a bounded queue, memory limits, and the risk of losing records if the process crashes before draining.

You need to clearly define:

1. Queue capacity and event size/count during peak bursts.
2. Queue-full policy: block, controlled discard, fallback, or durable spooling.
3. Shutdown behavior: draining, timeouts, forced termination, and acceptable data loss bounds.
4. Network/file failure handling: alerts, retries, failover, metrics, and monitoring.
5. Whether mutable data and context are captured accurately at event creation time.
6. Priority of retaining audit/security logs compared to routine debug logs.

Do not conclude "adding AsyncAppender is always better" without measuring **sink throughput, p95/p99 request latency, CPU, memory, drop rate, and ingestion lag**.

## 13. Common Issues and Troubleshooting

| Symptom | Possible Cause | Check / Resolution |
| --- | --- | --- |
| Logger called, but no logs appear | Logger level or filter dropped the event. | Check logger name, effective level, and filters. |
| Console has INFO, but file does not | File `AppenderRef` is set to WARN. | Verify whether the routing threshold is intentional. |
| Appender defined, but never used | No matching `AppenderRef`. | Compare `ref` names, loggers, and scope. |
| Logs appear twice | Additivity or two appenders pointing to the same sink. | Inspect the logger hierarchy, root, and `AppenderRef`s. |
| File is not created | Wrong path, write permissions, or all events filtered out. | Check `fileName`, working directory, and Status Logger. |
| File grows uncontrollably | Using a plain `FileAppender`. | Consider `RollingFile` and cleanup/retention policies. |
| Logs lost on shutdown | Async queue not drained or appender not flushed. | Check shutdown hooks, timeouts, and forced termination. |
| Errors only occur in production | Different backend/provider/classpath or appender plugin than dev. | Inspect deployed artifacts, runtime dependencies, and actual config. |
| Sensitive data appears in logs | Log message contains tokens, cookies, or PII. | Use allowlists and redaction at event creation time. |
| File has logs, but search store does not | Collector, parser, indexing, or retention issue. | Trace the pipeline downstream of the appender. |
| Many logs, but hard to query | Text pattern lacks structured fields and correlation IDs. | Standardize event schemas and use an appropriate encoder. |

**Debugging checklist for missing logs:** code actually executed → logger name/level → filter → `AppenderRef` name/level → appender filter → layout/encoding → sink and write permissions → queue/flush → collector/storage/retention. Do not just check `logger.isInfoEnabled()` and assume the appender has definitely written the log.

## 14. Exercises and Deployment Checklist

**Exercise 1:** Run the Maven demo in section 6. Explain why the Console has INFO/WARN/ERROR while the file only has WARN/ERROR.

**Exercise 2:** Change `<AppenderRef ref="WarningFile" level="WARN"/>` to ERROR. Predict the new file output without changing the console output.

**Exercise 3:** Add another Console appender to the child logger and leave additivity enabled toward the root Console; describe when duplicate logs occur, then fix it by choosing an appropriate routing setup.

**Exercise 4:** Replace `FileAppender` with `RollingFileAppender` using a size-based policy. Clearly distinguish rollover from time-based retention.

**Pre-production checklist:**

- [ ] You know whether the app uses JUL, SLF4J + Logback, or Log4j 2, and which runtime provider is active.
- [ ] Every appender has a clear name and destination; `AppenderRef`s match the intended loggers.
- [ ] Levels and filters at the logger, `AppenderRef`, and appender layers have been tested.
- [ ] No unintended duplicate logging due to additivity or multiple paths to the same sink.
- [ ] Layouts/encoders include UTC timestamps, event codes, logger/service names, and correlation IDs where needed.
- [ ] No sensitive data is logged; untrusted strings are escaped/serialized safely.
- [ ] File outputs have verified paths, permissions, rotation, retention, and collection mechanisms.
- [ ] Async sinks have clear queue-full policies, drop/error metrics, and shutdown/drain behavior.
- [ ] Sink failures produce observability signals; calling a logger is not equated with durable storage.
- [ ] Real events have been traced end-to-end from the application to the final query store.

## References

- [Apache Log4j 2 — Appenders](https://logging.apache.org/log4j/2.x/manual/appenders.html)
- [Apache Log4j 2 — Configuration / AppenderRef](https://logging.apache.org/log4j/2.x/manual/configuration.html)
- [Apache Log4j 2 — Filters](https://logging.apache.org/log4j/2.x/manual/filters.html)
- [Apache Log4j 2 — File appenders](https://logging.apache.org/log4j/2.x/manual/appenders/file.html)
- [Logback — Appenders](https://logback.qos.ch/manual/appenders.html)
- [Java 17 — java.util.logging.Handler](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Handler.html)

**Conclusion:** Loggers emit events; **Appenders deliver `LogEvent`s to one or more configured destinations**. Understanding what an appender is goes hand in hand with understanding `AppenderRef`, levels, filters, layouts, additivity, lifecycle, sink types, and durability limits—ensuring your logs are genuinely useful for operations and investigation.