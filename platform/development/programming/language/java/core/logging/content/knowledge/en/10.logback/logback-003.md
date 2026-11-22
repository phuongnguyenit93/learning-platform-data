# Logback Appenders in Java

## 1. What Is an Appender?

In **Logback**, an *appender* is the component that **receives a log event and forwards it to a destination or another processing step**. That destination can be the console, a file, a file with a rotation policy, a network connection, or an appender wrapped by an asynchronous logging mechanism. If a logger permits an event but has no active appender path configured for it, the user still will not see the log record where expected.

One way to visualize this:

~~~text
Java code using SLF4J Logger
       |
       v
Logback Logger (log level, TurboFilter, parent-child hierarchy)
       |
       v
Appenders attached to the logger / parent loggers
       |
       +--> ConsoleAppender --> stdout / stderr
       |
       +--> FileAppender --> log file
       |
       +--> RollingFileAppender --> active file + archive
       |
       +--> AsyncAppender --> queue --> target appender
~~~

Logback is commonly used as **the backend for SLF4J**. SLF4J provides the `Logger.info(...)`, `Logger.warn(...)`, and `Logger.error(...)` APIs; Logback handles execution, formatting, and dispatching events to appenders.

**Clearly distinguish the three roles:**

- **Logger:** receives the call, applies the effective log level and certain filtering decisions; a logger can own a list of appenders and inherit event-dispatch paths through parent loggers.
- **Appender:** decides **where to send the event** and can apply its own filters. A logger can have multiple appenders attached; a single appender can be referenced by multiple loggers.
- **Encoder/Layout:** determines **how the event is represented** when it reaches the destination: a text line, a pattern with timestamp/thread/level, or data encoded in another format. The appender determines the output path; the encoder/layout determines what is written along that path.

For example, the same event `LOG.info("orderId={} status={}", id, status)` can be written to the console using a short pattern while simultaneously being written to a file using a pattern that includes the timestamp and thread name. That is two appenders receiving the same event, not business code calling the logger twice.

## 2. Where Do Appenders Sit in the Logback Architecture?

### 2.1. How an Event Travels from Logger to Appender

In an application using SLF4J with the Logback Classic backend:

1. A `LOG.info(...)` call creates a logging request through SLF4J.
2. Logback checks whether the log level is enabled on the corresponding logger. Global filters such as `TurboFilter` may also influence whether the event is accepted.
3. When the event is accepted, Logback creates/provides an `ILoggingEvent` containing the log level, logger name, message, arguments, thread data, throwable, and related context.
4. The event is passed to the logger's effective appenders and, if additivity allows, to appenders attached to parent loggers.
5. Each appender can apply filters, encode the event, and perform the write operation, or forward it to a worker/next destination.

The exact path may vary depending on the Logback version and appender type. Not every appender formats events into text strings; an asynchronous appender may simply forward the event through a queue to another appender.

### 2.2. Log Level and Appender Filters Are Two Separate Layers

If the root logger is set to `INFO`, DEBUG/TRACE events from loggers inheriting this threshold are normally dropped right at the logger. They never reach `ConsoleAppender` or `FileAppender` for further processing.

If the logger accepts an INFO event, but an appender has a `ThresholdFilter` allowing only WARN and above, **that appender** does not output INFO; another appender without that filter can still output INFO. This allows different destinations to have different policies.

Example operational target:

| Event Source | ConsoleAppender | FileAppender |
| --- | --- | --- |
| DEBUG (disallowed by logger) | Does not reach appender | Does not reach appender |
| INFO (allowed by logger) | Written | Not written if file filter requires WARN+ |
| WARN (allowed by logger) | Written | Written |
| ERROR (allowed by logger) | Written | Written |

This is an **illustrative configuration model**, not a mandatory default policy of Logback.

### 2.3. Additivity Controls Whether Events Propagate to Parent Loggers

A logger is usually named after a package or class, such as `example.checkout.Service`. By default, Logback sets **additivity=true**: an event accepted by a child logger is sent to that logger's appenders **and** to the appenders of its parent loggers, all the way up to root.

Example:

~~~xml
<logger name="example.checkout" level="DEBUG">
    <appender-ref ref="FILE"/>
</logger>

<root level="INFO">
    <appender-ref ref="FILE"/>
</root>
~~~

If the same `FILE` appender is referenced on both the child logger and root, an event from `example.checkout.Service` can be received by that appender **twice**. Do not mistake this for two separate exceptions; it can simply be **duplicate logging caused by configuration**.

One way to fix this if you only want logs from this package to go to `FILE` and **not** to parent appenders:

~~~xml
<logger name="example.checkout" level="DEBUG" additivity="false">
    <appender-ref ref="FILE"/>
</logger>
~~~

Setting `additivity="false"` cuts off event propagation to parent loggers. Only use this when you have already attached **all required appenders** to the child logger; if you set it to false and forget to attach an appender, there may be no output destination at all. Also, the root `INFO` threshold **does not re-filter** a DEBUG event already accepted by a child logger just because it passes through an appender attached to root; individual appender filters can still apply.

## 3. Common Appenders

| Appender | Primary Function | When Useful | Key Considerations |
| --- | --- | --- | --- |
| `ConsoleAppender` | Writes to `System.out` or `System.err` | CLI apps, containers, development, stdout log collectors | Console/log drivers still incur I/O and can bottleneck |
| `FileAppender` | Appends to a single file | Apps needing a fixed log file on a host/volume | Must manage file size, permissions, and disk space |
| `RollingFileAppender` | Writes to an active file and performs **rollover/archiving** by policy | Long-running apps needing bounded log files and retention policies | Must configure rolling/triggering policies and retention properly |
| `AsyncAppender` | Enqueues events and dispatches them to a target appender | Reducing synchronous write overhead on business threads | Queue capacity, blocking/dropping, shutdown, and memory cost |
| `SiftingAppender` | Routes events to dynamic appenders based on a context key | Separating files per tenant/job within a controlled scope | Dynamic appender/file count can grow rapidly; complex lifecycle |
| `SocketAppender` | Sends log events over the network to a compatible receiver | Certain centralized log collection architectures | Must account for transport reliability, format, connectivity, and security |

Not every appender lives in the same module or has identical features across all Logback versions. `ConsoleAppender`, `FileAppender`, and `RollingFileAppender` belong to Logback Core; `AsyncAppender` is typically used in Logback Classic with `ILoggingEvent`. Other specialized appenders may require additional modules or libraries.

**Do not choose an appender by name alone.** Choose based on requirements: do you need stdout for a container collector, local files with rotation, lower latency, or forwarding logs to another system? Then define the loss, retention, and data protection policies for that destination.

## 4. Configuring Appenders in logback.xml

Logback configuration typically lives in `src/main/resources/logback.xml` and is placed on the runtime classpath. In XML configuration, appenders are declared with the `<appender>` tag, named via `name`, and given an implementation class via `class`. Loggers or the root logger attach appenders using `<appender-ref ref="..."/>`.

Example:

~~~xml
<configuration>
    <appender name="CONSOLE"
              class="ch.qos.logback.core.ConsoleAppender">
        <target>System.out</target>
        <encoder>
            <pattern>%level %msg%n</pattern>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
    </root>
</configuration>
~~~

Here:

- `CONSOLE` is the project-defined appender name; `ref="CONSOLE"` must match it exactly.
- `ConsoleAppender` writes to stdout in this configuration.
- `<encoder>` defaults to Logback Joran's `PatternLayoutEncoder` with the pattern `%level %msg%n`: log level, a space, message, and newline.
- `<root level="INFO">` sets the threshold on the root logger; loggers inheriting this level typically emit only INFO/WARN/ERROR.
- An appender that is **defined but not referenced** by the relevant logger path will not receive the expected events.

A common pattern for troubleshooting:

~~~xml
<pattern>%d{yyyy-MM-dd HH:mm:ss.SSS} %-5level [%thread] %logger{36} - %msg%n</pattern>
~~~

`%d` is the timestamp, `%-5level` is the padded log level, `%thread` is the thread name, `%logger{36}` abbreviates the logger name, `%msg` is the message, and `%n` is a newline. The pattern can also include `%X{requestId}` if the application uses MDC properly.

**Appenders and encoders do not automatically turn messages into JSON.** For structured logging, you must use a supported encoder/layout and configure it accordingly. Writing messages in `key=value` format by itself still produces a plain text string.

## 5. Runnable Java 17 Example: Same Event to Console and File

This example uses **SLF4J API 2.0.17** with **Logback Classic 1.5.18**, a compatible pair of versions for practicing on JDK 17. This is **not a claim about the latest version**; real projects should use dependency management and approved versions. Because Logback is external to the JDK, you need Maven/Gradle or an appropriate classpath; `javac` alone without dependencies will not find `org.slf4j.*`.

Create the following structure:

~~~text
logback-appender-demo/
  pom.xml
  src/main/java/example/AppenderDemo.java
  src/main/resources/logback.xml
~~~

### 5.1. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>logback-appender-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.slf4j</groupId>
            <artifactId>slf4j-api</artifactId>
            <version>2.0.17</version>
        </dependency>
        <dependency>
            <groupId>ch.qos.logback</groupId>
            <artifactId>logback-classic</artifactId>
            <version>1.5.18</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
                <configuration>
                    <release>17</release>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>example.AppenderDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`slf4j-api` provides the Logger API, and `logback-classic` provides the SLF4J provider and Logback backend. Maven automatically pulls in Logback's required transitive dependencies; no other SLF4J provider needs to be declared for this example.

### 5.2. AppenderDemo.java

~~~java
package example;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public final class AppenderDemo {
    private static final Logger LOG =
            LoggerFactory.getLogger(AppenderDemo.class);

    private AppenderDemo() {
    }

    public static void main(String[] args) {
        String orderId = "O-42";

        LOG.debug("step=validate orderId={}", orderId);
        LOG.info("operation=checkout orderId={} state={}",
                orderId, "started");
        LOG.warn("operation=checkout orderId={} event={}",
                orderId, "fallback");
        LOG.info("operation=checkout orderId={} state={}",
                orderId, "completed");
    }
}
~~~

The code calls SLF4J rather than referencing `ConsoleAppender` or `FileAppender` directly. Therefore, changing output destinations later mostly involves changing backend configuration without modifying business logging statements.

### 5.3. logback.xml

~~~xml
<configuration>
    <appender name="CONSOLE"
              class="ch.qos.logback.core.ConsoleAppender">
        <target>System.out</target>
        <encoder>
            <pattern>%level %msg%n</pattern>
            <charset>UTF-8</charset>
        </encoder>
    </appender>

    <appender name="FILE"
              class="ch.qos.logback.core.FileAppender">
        <file>target/appender-demo.log</file>
        <append>true</append>
        <encoder>
            <pattern>%level %msg%n</pattern>
            <charset>UTF-8</charset>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
        <appender-ref ref="FILE"/>
    </root>
</configuration>
~~~

Console and file are **two separate destinations** here. The `FILE` appender writes to `target/appender-demo.log` relative to the process working directory; when running via Maven in the project directory, `target` is already created by the build step. `<append>true</append>` appends to the existing file on each run, so subsequent runs will keep growing the file; do not assume the file always has only three lines. If you want to start with a fresh file for an exercise, explicitly delete the test file before running.

### 5.4. Running and Checking Output

In the `logback-appender-demo` directory:

~~~bash
mvn -q compile exec:java
~~~

The **application** log output written to stdout with the configuration above is:

~~~text
INFO operation=checkout orderId=O-42 state=started
WARN operation=checkout orderId=O-42 event=fallback
INFO operation=checkout orderId=O-42 state=completed
~~~

The DEBUG line does not appear because the root logger uses the INFO threshold. The file `target/appender-demo.log` also receives those three application lines on the first run with a new file; subsequent runs append three more lines. Depending on Maven, the OS, or the launch environment, tool-specific messages may appear alongside the three sample log lines.

Simply changing `root level="INFO"` to `DEBUG` and re-running will cause `step=validate orderId=O-42` to be received by both appenders before the INFO/WARN lines, since neither appender has a filter excluding DEBUG.

**Configuration check:** if you want to keep only ERROR/WARN logs in the file while allowing the console to receive INFO as well, add a filter on the `FILE` appender (Section 8). Changing the filter on `FILE` will not directly affect `CONSOLE` logs.

## 6. RollingFileAppender: Log Files with a Rotation Policy

`FileAppender` writes continuously to a single file, so if an application runs for a long time without size management, the file can grow very large or fill up the volume. `RollingFileAppender` extends file writing with a **rolling policy**; when a rollover time or condition is met, the old file can be moved to an archive and the active file continues receiving events.

A common daily rotation configuration:

~~~xml
<!-- Place inside <configuration> to replace the example's FILE appender. -->
<appender name="FILE"
          class="ch.qos.logback.core.rolling.RollingFileAppender">
    <file>target/appender-demo.log</file>
    <append>true</append>

    <rollingPolicy
        class="ch.qos.logback.core.rolling.TimeBasedRollingPolicy">
        <fileNamePattern>target/archive/app.%d{yyyy-MM-dd}.log.gz</fileNamePattern>
        <maxHistory>7</maxHistory>
        <totalSizeCap>100MB</totalSizeCap>
    </rollingPolicy>

    <encoder>
        <pattern>%d{yyyy-MM-dd HH:mm:ss.SSS} %-5level %msg%n</pattern>
        <charset>UTF-8</charset>
    </encoder>
</appender>
~~~

This configuration uses a fixed active file name and daily archives. `fileNamePattern` contains `%d{...}` to specify the time unit. `maxHistory=7` caps history by day periods, and `totalSizeCap=100MB` caps total archive size via the policy's cleanup mechanism. **Limits do not necessarily delete files at the exact instant a threshold is crossed**; cleanup is typically tied to rollover, with an optional cleanup-on-start setting depending on version and configuration. The active file and external backup mechanisms are also not necessarily counted under this archive cap.

**If you need both time-based and size-based rotation**, Logback provides `SizeAndTimeBasedRollingPolicy`. Example `rollingPolicy` replacement:

~~~xml
<rollingPolicy
    class="ch.qos.logback.core.rolling.SizeAndTimeBasedRollingPolicy">
    <fileNamePattern>target/archive/app.%d{yyyy-MM-dd}.%i.log.gz</fileNamePattern>
    <maxFileSize>10MB</maxFileSize>
    <maxHistory>7</maxHistory>
    <totalSizeCap>100MB</totalSizeCap>
</rollingPolicy>
~~~

In this combined policy, `%i` is an index used to name archives within the same period when the size limit is reached. **Do not simply add `<maxFileSize>` to a plain `TimeBasedRollingPolicy` and expect size-based rotation**; you must use a policy that supports that condition. The values 10MB / 7 days / 100MB are examples; choose them based on actual throughput, retention, and disk capacity.

### Operational Considerations for Rolling Files

- Ensure the target path has write permissions and the volume has sufficient space.
- Do not let multiple processes write to the same file arbitrarily; file synchronization, prudent mode, locking, and multi-process rollover require explicit design.
- Avoid letting an external rotation tool and Logback manage the same file without coordination; renaming or truncating the file externally can cause lost or duplicate lines.
- Test rollover and retention conditions in a realistic environment, rather than only checking that the active file appears.
- Compressed/archived log files can still contain sensitive data and need appropriate access and deletion policies.

## 7. AsyncAppender: Offloading Part of Logging from Business Threads

Logback Classic's `AsyncAppender` is a **wrapper appender**: it receives an `ILoggingEvent` and places it in a queue, after which a worker thread forwards the event to a target appender. It does not decide the final file or console destination on its own; it still needs to reference an appropriate appender.

Example wrapping `FILE` with `ASYNC`:

~~~xml
<!-- FILE must be defined beforehand and be a valid target appender. -->
<appender name="ASYNC"
          class="ch.qos.logback.classic.AsyncAppender">
    <queueSize>512</queueSize>
    <discardingThreshold>0</discardingThreshold>
    <neverBlock>false</neverBlock>
    <includeCallerData>false</includeCallerData>
    <appender-ref ref="FILE"/>
</appender>
~~~

In the same configuration file, replace root with:

~~~xml
<root level="INFO">
    <appender-ref ref="CONSOLE"/>
    <appender-ref ref="ASYNC"/>
</root>
~~~

With this setup, the console writes synchronously and `FILE` receives events via `ASYNC`. **Do not reference both `FILE` directly and `ASYNC` (which forwards to `FILE`) on the same log path**, or the file may receive every event twice.

Important options:

| Property | Meaning | Impact to Understand |
| --- | --- | --- |
| `queueSize` | Number of slots in the queue | A larger queue holds more events/memory; a smaller queue fills up sooner |
| `discardingThreshold` | Threshold at which less important events start being dropped when the queue nears capacity | Logback Classic discards lower levels like TRACE/DEBUG/INFO in this situation |
| `neverBlock` | Behavior when the queue is full | `false` typically allows waiting to enqueue; `true` avoids blocking but can drop events |
| `includeCallerData` | Whether to collect full caller information | Enabling it can incur extra stack inspection cost |
| `maxFlushTime` | Wait limit for the worker to flush when stopping the appender | If the queue is not drained in time, unwritten events may be lost |

**Distinguishing the two policies:** `discardingThreshold=0` disables early dropping of lower-priority levels as the queue fills up, but **does not guarantee zero log loss** in all scenarios such as a crash/kill or when configured to drop events when full. `neverBlock=false` can cause business threads to block if the queue fills up. This is a trade-off between application latency and log completeness.

Async offloads part of encoding/I/O to a worker thread, but **does not reduce total resource usage to zero**. Monitor CPU, heap, GC, queue depth, throughput, p95/p99 latency, dropped event counts, and shutdown time. Do not assume an in-memory async appender is a durable audit storage solution.

### When Should You Choose Async?

Consider it when file or network writes on the request path cause noticeable latency, when high event volume benefits from batching/buffering, and when the application has a defined strategy for slow collectors. For a small CLI emitting a few INFO lines, a simple synchronous appender may be enough. For events that must be preserved, verify end-to-end reliability of the collection pipeline.

## 8. Appender Filters: Different Policies per Destination

Logback provides filters that return `DENY`, `NEUTRAL`, or `ACCEPT` depending on the filter. Two common ones in Logback Classic:

### 8.1. ThresholdFilter: From a Level and Above

Example where `FILE` accepts only WARN and ERROR:

~~~xml
<appender name="FILE"
          class="ch.qos.logback.core.FileAppender">
    <file>target/warnings.log</file>

    <filter class="ch.qos.logback.classic.filter.ThresholdFilter">
        <level>WARN</level>
    </filter>

    <encoder>
        <pattern>%level %msg%n</pattern>
    </encoder>
</appender>
~~~

`ThresholdFilter` denies events lower than WARN and lets events from WARN and above pass through the appender. Meanwhile, `CONSOLE` can still output INFO if it does not have a matching filter attached.

### 8.2. LevelFilter: Exact Level Match

When a destination should receive **only ERROR**, you can use:

~~~xml
<filter class="ch.qos.logback.classic.filter.LevelFilter">
    <level>ERROR</level>
    <onMatch>ACCEPT</onMatch>
    <onMismatch>DENY</onMismatch>
</filter>
~~~

This filter block **must be placed inside an appender declaration**, not as a standalone root element. `LevelFilter` configures explicit actions for match and mismatch; it differs from `ThresholdFilter`, which is based on level ordering.

**Logger level remains the first gate.** If a logger blocks DEBUG, no appender filter can "recover" DEBUG events that were already discarded. If an appender blocks INFO, raising the logger level to DEBUG only causes the logger to emit more events; the appender still enforces its own policy.

## 9. SiftingAppender and Dynamic Routing

`SiftingAppender` can create or select different appenders based on a **discriminating key value** on the event, typically from MDC. For example, separating logs by `jobId` when there is a bounded number of jobs and a clear lifecycle/retention policy.

Concept:

~~~text
MDC jobId=A -> SiftingAppender -> appender for job A -> file A
MDC jobId=B -> SiftingAppender -> appender for job B -> file B
~~~

This is a conceptual diagram. `SiftingAppender` is useful when splitting destinations aids investigation or access control, but it can easily create **a huge number of appenders and files** if the key has high cardinality or is controlled by user input. Never use raw request IDs or untrusted user input directly as file names. You must bound key cardinality, appender lifecycle, write permissions, path safety, and cleanup.

In large multi-tenant systems, writing **a single JSON stream with a safe `tenantId` field** and splitting it at the collector layer can be easier to operate than thousands of dynamic files. The right choice depends on system requirements.

## 10. Network Log Shipping and Containerized Applications

Not every system needs `SocketAppender`. In container environments, applications usually write to the console and let the runtime/agent collect and forward logs. Common pattern:

~~~text
SLF4J -> Logback ConsoleAppender -> stdout/stderr
       -> container log driver/agent -> collector -> storage/search
~~~

The advantage is that the application focuses on emitting events while the external pipeline handles transport and storage. However, stdout **still consumes I/O**, and the driver/agent can experience backpressure or event loss depending on configuration.

If an appender sends directly over a socket, you must understand the receiver format, retry behavior, network connectivity, transport security, and how to handle an unavailable collector. **Do not assume a log is durable just because `logger.info(...)` returned**; the event may still be in a queue, a buffer, or unacknowledged by the collector.

Choose the output path based on the application's infrastructure; not every backend needs to send logs directly over the network. If retention has legal or audit requirements, use a purpose-built reliability mechanism rather than relying solely on a standard queue-based appender.

## 11. Writing a Custom Appender: When and What to Watch Out For

Logback provides base classes such as `AppenderBase<E>` and `UnsynchronizedAppenderBase<E>` in `logback-core`. When you genuinely need a specialized destination, you can write a custom appender handling `ILoggingEvent` in Logback Classic.

Example **illustrating the mechanism**, not a production-ready implementation:

~~~java
import ch.qos.logback.classic.spi.ILoggingEvent;
import ch.qos.logback.core.AppenderBase;

public final class CountingAppender
        extends AppenderBase<ILoggingEvent> {

    private long acceptedCount;

    @Override
    protected void append(ILoggingEvent event) {
        acceptedCount++;
        // For illustration only: does not write to console, file, or network.
    }

    public long getAcceptedCount() {
        return acceptedCount;
    }
}
~~~

`AppenderBase` provides basic lifecycle and filter support and invokes the subclass's `append(...)` method while the appender is started. The code above only demonstrates how events are received; **do not use an unsynchronized `long` counter to collect metrics in a multithreaded environment**, and do not build a custom appender for functionality that already exists without evaluating thread-safety, I/O cost, lifecycle, and error handling.

When you need metrics for log counts, a metrics system or a proven appender is often a better fit. For a real custom appender, you must design `start()`/`stop()`, resource management, exception handling, safe stream closing, and ensure that any internal logging inside the appender does not trigger an infinite loop.

## 12. MDC, Formatters, and Data Safety in Appenders

An appender receives events that already carry context information, but **whether that context is written to the log depends on the encoder/layout**. Example Logback pattern:

~~~xml
<pattern>%d{HH:mm:ss.SSS} %-5level requestId=%X{requestId} %msg%n</pattern>
~~~

If the application sets `requestId` in MDC, the pattern can include that value on every line. In applications using thread pools, MDC is typically thread-bound; application code must clear the context when a request finishes and explicitly propagate context across asynchronous boundaries using an appropriate mechanism.

Using MDC helps correlate logs across steps, but **does not automatically create a distributed trace**. Tracing requests across services requires a proper tracing and trace ID propagation mechanism. A TRACE-level log line and an event with a `traceId` are two completely different concepts.

Appenders and encoders also **do not automatically protect secrets**. Never log passwords, tokens, cookies, or payloads containing unnecessary personal data. If user input contains newlines or control characters, use an encoder with appropriate escaping or sanitize fields to prevent log forging. Log files, archives, and collectors should have proper access controls and retention policies.

Prefer concise, context-rich messages:

~~~text
operation=checkout requestId=req-12 orderId=O-42 outcome=success durationMs=28
~~~

This example avoids logging card numbers, passwords, addresses, or full request payloads, while still making it easy to look up a request and measure duration when fields are emitted and processed consistently.

## 13. Troubleshooting: Missing Logs, Duplicate Logs, or Lost Logs

### Missing Logs

1. Verify that SLF4J has a compatible **Logback provider** on the runtime classpath; without a provider, calls may fall back to NOP or another implementation.
2. Check logger thresholds (`INFO`, `DEBUG`, etc.), inherited levels, and appender filters.
3. Verify that the appender is declared, has the right `name`, and **is referenced** via `appender-ref` on the relevant logger path.
4. Check the target path, write permissions, file size, stderr/stdout, and the process working directory.
5. Check for XML parsing or appender initialization errors. Logback's startup status messages or `StatusPrinter` can help identify an appender that failed to start or a file that could not be opened.
6. If using `AsyncAppender`, inspect queue/drop behavior and shutdown. Events may not have been flushed yet or may have been dropped from the queue.

### Duplicate Logs

- Check whether the same appender is attached to both a child logger and root with `additivity=true`.
- Check whether the same file/console destination is connected via **two paths**: directly and through `AsyncAppender`.
- Check whether multiple handlers or logging bridges create a routing loop. Bidirectional bridge modules can route events across frameworks unexpectedly.
- Check whether application code logs the same exception at multiple layers and rethrows it repeatedly. That is code-level duplication, distinct from appender duplication.

### Lost or Out-of-Order Logs

- Logs may have been filtered at the logger/appender, or dropped by an async queue under heavy load.
- Events in a queue or buffer may not be flushed if the process is killed or crashes.
- Multiple threads and centralized systems may process or transmit events concurrently. Do not rely on arrival order across threads to establish strict causal ordering.
- For rolling files, check rollover, retention, and both active and archive files when searching for older events.
- For JSON output, confirm that the encoder actually includes the fields you are searching for and renders the full `Throwable` when investigating exceptions.

## 14. Choosing an Appender by Operational Goal

| Need | Typically Suitable Option | What to Verify |
| --- | --- | --- |
| App running in a container with a log agent | `ConsoleAppender` -> stdout/stderr | Log driver/agent, routing, volume, backpressure |
| CLI / small application | `ConsoleAppender` | Log level, format, noise |
| Server needing log files | `RollingFileAppender` | Rollover, `maxHistory`, `totalSizeCap`, volume capacity |
| Synchronous appender hurting p99 latency | `AsyncAppender` -> target appender | `queueSize`, drop/block behavior, shutdown, dropped event count |
| Only WARN/ERROR to a specific destination | `ThresholdFilter` on that appender | Logger must still accept WARN/ERROR |
| Split logs by a bounded key | `SiftingAppender` | Cardinality, lifecycle, file count, security |
| Centralized collection over network | Console + agent or suitable network appender | Retry, encoding, reliability, TLS/access control |

When changing configuration, test all three scenarios: normal operation, high log volume under load, and a slow or failing log destination. Measure **CPU, GC/heap, throughput, p95/p99 latency, bytes/s, queue depth, and dropped events**. Do not conclude that async is effective just because `LOG.info(...)` call time decreased: the write work may simply be piling up in the queue.

## 15. Common Configuration Mistakes and How to Avoid Them

| Mistake | Consequence | How to Fix |
| --- | --- | --- |
| Declaring an appender but forgetting `appender-ref` | Logger does not send events to the destination | Attach the appender to the appropriate logger/root |
| Misspelled `ref` name | Appender cannot be referenced | Match `name` and `ref` exactly |
| Setting logger level to DEBUG with an appender WARN filter | DEBUG logs do not appear at that destination | Check both logger level and appender filters |
| Attaching the same appender to both child and root | An event can be written twice | Check additivity and keep only the intended path |
| Routing to the same `FILE` directly and through `ASYNC` | Duplicate lines in the file | Use a single path to the same destination |
| Using plain `FileAppender` long-term | File grows without bound | Use appropriate rolling and retention policies |
| Configuring size rollover with the wrong policy | Does not rotate as expected | Use `SizeAndTimeBasedRollingPolicy` when both time and size are needed |
| Async queue too small with unclear discard rules | Drops TRACE/DEBUG/INFO or blocks requests | Tune policy based on requirements; measure drops/blocks |
| Enabling `includeCallerData` for all events | Increases stack inspection overhead | Enable only when truly needed and benchmark under load |
| Using only `%msg` while expecting MDC or `Throwable` details | Logs lack context and error details | Configure the pattern/encoder accordingly |
| Logging raw user input or secrets | Data leaks, log forging | Choose safe fields, escape/limit input, enforce access control |
| Treating an async appender as durable storage | Unflushed queue entries can be lost on crash | Design separate end-to-end durability guarantees |

## 16. Practice Exercises

1. **Console + file:** run the Maven example in Section 5. Explain why three application log lines appear on stdout and in the file while DEBUG does not. Change root to DEBUG and predict how many events both appenders will receive.
2. **Additivity:** attach `FILE` to both `logger name="example"` and root at the same time. With default additivity, explain why the file can receive duplicate entries. Fix it by adjusting the attachment point or setting `additivity="false"` with the required appenders.
3. **Filter:** add `ThresholdFilter WARN` to `FILE` while keeping root at INFO. Predict how many lines appear on the console and in the file in **a single run with a new file**.
4. **Rolling:** replace `FILE` with `RollingFileAppender`, configured with daily archiving and `maxHistory`. Distinguish the roles of `file`, `fileNamePattern`, and the rolling policy; describe how to verify retention during rollout.
5. **Async:** suppose an application emits 10,000 logs/s while the target appender can only write 8,000 logs/s. By how many events/s does the queue grow on average before blocking or discarding kicks in? Discuss how `neverBlock` and `discardingThreshold` affect behavior as the backlog grows.
6. **Security:** design a pattern that includes `requestId` from MDC without logging tokens. Explain how to clear MDC and why the encoder must handle input containing newlines.
7. **Diagnosis:** an application has INFO calls in code, yet the file is empty while the console still shows INFO. List the order in which you would check the logger, appender filters, `appender-ref`, file permissions, startup status, and async settings.

**Key Takeaway:** An appender is the component that determines **the routing and output destination** of log events in Logback. Loggers decide event levels, appenders can have their own filters, and encoders/layouts determine formatting. Understanding **`appender-ref`, additivity, `File`/`RollingFile`/`Console`/`AsyncAppender`, queue policies, and retention** helps ensure logs reach the right destination, avoid duplicates or loss, and keep logging costs under control.