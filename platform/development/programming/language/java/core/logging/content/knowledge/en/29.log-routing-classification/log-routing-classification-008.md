# Multiple Logging Destinations in Java Core Logging

## 1. A Single Log Event Can Go to Multiple Places

In a Java application, operational information rarely serves only one audience. Developers want to see logs on the terminal, on-call engineers need to filter incidents from files or a centralized system, and the operations team may need a dedicated channel for alerts. **Multiple logging destinations** is the ability of a logger to route a log event to **more than one handler/appender**, according to different classification policies.

For example, a successfully created order can be written to a file for lookup, while a payment error goes both to the file and to the console. The two lines in the two destinations can originate from the **same log event**, not two separate `logger.error(...)` calls.

~~~text
                     Application code
                   logger.info/warn/error
                             |
                        Logger level
                             |
                      Shared log event
                             |
                   +---------+---------+
                   |                   |
             Console handler        File handler
             level = WARNING        level = INFO
                   |                   |
               stderr             logs/app.log
                   |
             Log collector
~~~

In the diagram, an `INFO` event only goes to the file; a `WARNING` or `SEVERE` event can appear on both the console and the file. The key point is that **each destination can independently decide whether to accept an event**.

Practical benefits include: interactive monitoring during development, preserving processing history, integrating with centralized collection systems, creating appropriate audit channels, and reducing noise for each reader. In return, you need to manage duplicate writes, I/O, latency, disk space, security, and filtering policies.

## 2. Distinguishing Logger, Handler, Appender, and Formatter

Terminology is not completely uniform across libraries:

| Component | Role | Example |
| --- | --- | --- |
| **Logger** | API/log source name and effective log level | `java.util.logging.Logger`, logger via SLF4J |
| **Log event / LogRecord** | Data of a single log entry: level, message, timestamp, source... | `java.util.logging.LogRecord` |
| **Handler** in JUL | Receives an event and handles an output destination | `ConsoleHandler`, `FileHandler` |
| **Appender** in Logback/Log4j 2 | Role similar to a handler in the corresponding backend | `ConsoleAppender`, `RollingFileAppender` |
| **Filter** | Decides whether an event is processed at a specific point | Logger filter, handler/appender filter |
| **Formatter/Layout/Encoder** | Converts an event into a string or bytes suitable for the output destination | `SimpleFormatter`, pattern/JSON encoder |

Typical flow of Java Util Logging (JUL):

1. The **source logger** checks its own level and filter. Events rejected here usually do not proceed to handlers.
2. The event is forwarded to handlers attached to the logger and, if `useParentHandlers=true`, to the parent logger's handlers.
3. **Each handler** applies its own level/filter, formats the accepted event, and writes it to its destination.
4. If the backend uses a buffer or async queue, the event may be emitted or flushed after the log method call returns.

**The two filtering levels do not replace each other:** if the source logger is set to `WARNING`, an `INFO` event cannot be written to the file simply by setting FileHandler to `INFO` because it was already blocked at the source. Conversely, setting the logger to `FINE` does not force every handler to log `FINE`; each handler can reject it.

In JUL, the parent logger's level is not necessarily re-checked for an event created by a child logger; **the level/filter of the handlers on the parent logger** determines whether the event is emitted through those handlers. This is important to understand when the root logger has multiple handlers.

## 3. Java 17 Example: Console Receives Only Warnings, File Receives INFO and Above

This example uses `java.util.logging`, built into JDK 17, with no extra dependencies required. We create **one shared logger** and attach two handlers:

- `ConsoleHandler`: prints `WARNING` and `SEVERE` to **stderr**.
- `FileHandler`: writes `INFO`, `WARNING`, `SEVERE` to a file in the `logs` directory.
- Source logger: allows `FINE` and above, to clearly show that the final decision also depends on the handlers.

Create the file **`MultiDestinationLoggingDemo.java`**:

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.logging.ConsoleHandler;
import java.util.logging.FileHandler;
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class MultiDestinationLoggingDemo {
    private static final class PlainFormatter extends Formatter {
        @Override
        public String format(LogRecord record) {
            return record.getLevel().getName() + ": "
                    + formatMessage(record)
                    + System.lineSeparator();
        }
    }

    public static void main(String[] args) throws IOException {
        Files.createDirectories(Path.of("logs"));

        Logger logger = Logger.getLogger("demo.routing.multi");
        logger.setLevel(Level.FINE);
        logger.setUseParentHandlers(false);

        ConsoleHandler console = new ConsoleHandler();
        console.setLevel(Level.WARNING);
        console.setFormatter(new PlainFormatter());

        FileHandler file = new FileHandler(
                "logs/application-%g.log", 1_048_576, 2, false);
        file.setLevel(Level.INFO);
        file.setFormatter(new PlainFormatter());

        logger.addHandler(console);
        logger.addHandler(file);
        try {
            logger.fine("cache hit");
            logger.info("order created");
            logger.warning("retry scheduled");
            logger.severe("payment failed");
        } finally {
            logger.removeHandler(console);
            logger.removeHandler(file);
            console.flush();
            file.flush();
            console.close();
            file.close();
        }
    }
}
~~~

Run from a directory with permission to create `logs`, with no other process locking the same file:

~~~bash
javac MultiDestinationLoggingDemo.java
java MultiDestinationLoggingDemo
~~~

**Stdout:** no lines, because the program does not call `System.out` and `ConsoleHandler` outputs to stderr by default.

**Stderr:**

~~~text
WARNING: retry scheduled
SEVERE: payment failed
~~~

**Contents of `logs/application-0.log` after the program finishes in a single-process run:**

~~~text
INFO: order created
WARNING: retry scheduled
SEVERE: payment failed
~~~

The file `logs/application-0.log` is generated by `FileHandler` from the pattern `application-%g.log`, with the first generation being `0`. If multiple JVMs run concurrently using the same pattern and file locking is active, the actual filename may be modified to avoid conflicts (e.g., by appending a unique number); do not rely on a single fixed filename in a multi-process setup. Each output line has no timestamp because we used `PlainFormatter`; the line separator depends on the operating system.

**Routing table explanation:**

| Event emitted from logger | Logger level `FINE` | Console `WARNING` | File `INFO` |
| --- | --- | --- | --- |
| `FINE cache hit` | Accepted | Dropped | Dropped |
| `INFO order created` | Accepted | Dropped | Written |
| `WARNING retry scheduled` | Accepted | Written | Written |
| `SEVERE payment failed` | Accepted | Written | Written |

The table shows there is no need to call `logger.warning(...)` twice to write to two destinations. One event is emitted once and **fanned out** to the matching handlers.

`setUseParentHandlers(false)` is important in this example: if the logger still forwards events to its parent logger's handlers, the console might receive another copy of the log, making it look like a duplicate write. In production applications, handler inheritance may be intentional; understand where handlers are attached before disabling it.

`FileHandler` uses `limit=1_048_576` bytes and `count=2`, meaning the example configures a ~1 MiB size limit and two file generations in JUL's rotation mechanism. With only three lines, no rotation occurs. `append=false` reinitializes the selected file when the program starts; do not use this for data that must be retained permanently without a proper rotation/retention policy.

## 4. When You Want to Partition Logs into Mutually Exclusive Channels

**Intentional duplication** and **mutually exclusive partitioning** are two different requirements.

- **Fan-out:** `WARNING` appears on both the console and the file, as in the example above.
- **Partition:** `INFO` goes to the normal channel; `WARNING`/`SEVERE` goes to the alert channel; each event enters only one destination group.

When using JUL, if you want a channel that strictly receives only `INFO`, setting `handler.setLevel(Level.INFO)` is **not enough**, because it also accepts `WARNING` and `SEVERE`. You must add a filter that matches the **exact level**:

~~~java
// Integration snippet: two Handlers have already been created and have their lifecycle managed.
infoHandler.setLevel(Level.INFO);
infoHandler.setFilter(record -> record.getLevel() == Level.INFO);

alertHandler.setLevel(Level.WARNING);
~~~

This is an illustrative snippet requiring existing `infoHandler` and `alertHandler` variables, not a standalone program. It assumes only standard JUL levels are considered. In real systems with custom levels or business-based classification, choose filters based on more appropriate fields.

**Do not confuse severity with data category.** For example, `AUDIT`, `SECURITY`, and `BUSINESS` are not necessarily synonymous with `WARNING` or `ERROR`; routing audit logs to a separate destination should usually rely on logger name, marker, or structured metadata, depending on the backend.

| Purpose | Routing suggestion | Things to decide |
| --- | --- | --- |
| Dev console | Level suitable for direct reading | Are `DEBUG`/`FINE` needed? |
| Production stdout/stderr | Events useful for monitoring systems | Which stream does the log collector read? |
| History file | Events for lookup and troubleshooting | Rotation, retention, access permissions |
| Audit trail | Business events requiring traceability | Required fields, access control, durability |
| Alert/error channel | Actionable errors or warnings | Anti-spam/deduplication, alert rate |
| Remote collector | Normalized events with trace/request ID | Network, queue, retry, backpressure |

An event can be sent to multiple destinations if two independent purposes require it. However, if a collection system already reads stdout and pushes to a central store while the application also sends the exact same event directly to that store, you can create **duplicate records at the pipeline level**.

## 5. Configuring Multiple Destinations with JUL's `logging.properties`

Instead of attaching handlers manually in Java code, JUL supports file-based configuration. The following example is a configuration **specifically for an application using JUL**, not to be used simultaneously with the programmatic handler attachment in section 3:

~~~properties
# Root logger is attached with two handlers.
handlers = java.util.logging.ConsoleHandler, java.util.logging.FileHandler
.level = INFO

# Console only shows warnings and errors.
java.util.logging.ConsoleHandler.level = WARNING
java.util.logging.ConsoleHandler.formatter = java.util.logging.SimpleFormatter

# File receives INFO and above.
java.util.logging.FileHandler.level = INFO
java.util.logging.FileHandler.formatter = java.util.logging.SimpleFormatter
java.util.logging.FileHandler.pattern = logs/application-%g.log
java.util.logging.FileHandler.limit = 1048576
java.util.logging.FileHandler.count = 2
java.util.logging.FileHandler.append = true

# Concise format, shared by both handlers.
java.util.logging.SimpleFormatter.format = %4$s: %5$s%n
~~~

Assuming the file is located at `config/logging.properties`, the `logs` directory already exists, and there is a `MyApplication` class that actually uses JUL:

~~~bash
java -Djava.util.logging.config.file=config/logging.properties MyApplication
~~~

The command above illustrates how to load configuration into an existing application; it is **not** the command to run the demo file from section 3. The `-D...` argument must appear before the main class name or `-jar`. `FileHandler` does not automatically create missing parent directories; prepare the directory and write permissions beforehand.

Because `.level=INFO`, loggers inheriting this default level normally do not emit `FINE` events. ConsoleHandler at `WARNING` filters out events generated at lower levels; FileHandler at `INFO` accepts the corresponding ones. If a child logger is configured at `FINE`, its `FINE` events can still be dropped by both existing handlers.

**Note on logger names and runtime:** JUL's `logging.properties` file does not configure Logback or Log4j 2. When an application calls the SLF4J API, you must identify the active provider/backend before choosing the configuration file.

## 6. Two Appenders in Logback (SLF4J)

For an application using SLF4J and the **Logback Classic** backend, the following minimal `logback.xml` sends the same `INFO` and above events to both the console and a file:

~~~xml
<configuration>
    <appender name="STDOUT" class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%d{HH:mm:ss.SSS} %-5level [%thread] %logger - %msg%n</pattern>
        </encoder>
    </appender>

    <appender name="FILE" class="ch.qos.logback.core.FileAppender">
        <file>logs/application.log</file>
        <append>true</append>
        <encoder>
            <pattern>%d{yyyy-MM-dd HH:mm:ss.SSS} %-5level %logger - %msg%n</pattern>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="STDOUT"/>
        <appender-ref ref="FILE"/>
    </root>
</configuration>
~~~

This is a **Logback** XML file, placed on the classpath (typically `src/main/resources/logback.xml` in Maven/Gradle projects) or a location supported by the backend. The application must have compatible SLF4J and Logback dependencies for the example to take effect. A plain `FileAppender` **does not provide rotation/retention**; for long-running or high-volume workloads, use `RollingFileAppender` and an appropriate rolling policy.

To have the console show only `WARN` and above while the file keeps `INFO`, add the following filter **inside the STDOUT appender**:

~~~xml
<filter class="ch.qos.logback.classic.filter.ThresholdFilter">
    <level>WARN</level>
</filter>
~~~

This is an **integration XML snippet** to place inside `<appender name="STDOUT"> ... </appender>`, not a standalone `logback.xml` file. With root level `INFO`, `DEBUG` events are still blocked by root; `INFO` events go to the file but are rejected by the console filter; `WARN` and `ERROR` appear in both.

Be careful with **additivity**: when a child logger attaches an appender and still forwards events to root, the same appender may be referenced through multiple paths, causing duplicate output. Understand the logger hierarchy and only use `additivity="false"` when you genuinely want to cut propagation to parent loggers, as doing so can also prevent events from reaching intended destinations.

## 7. Two Appenders in Log4j 2

For an application using **Log4j 2**, an example `log4j2.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<Configuration>
    <Appenders>
        <Console name="CONSOLE" target="SYSTEM_OUT">
            <PatternLayout pattern="%d{HH:mm:ss.SSS} %-5p %c - %m%n"/>
        </Console>
        <File name="FILE" fileName="logs/application.log" append="true">
            <PatternLayout pattern="%d{yyyy-MM-dd HH:mm:ss.SSS} %-5p %c - %m%n"/>
        </File>
    </Appenders>
    <Loggers>
        <Root level="info">
            <AppenderRef ref="CONSOLE"/>
            <AppenderRef ref="FILE"/>
        </Root>
    </Loggers>
</Configuration>
~~~

This configuration distributes events across two appenders, but has **no rolling policy** for the `File` appender; in production you may need `RollingFile` combined with `Policies` and a retention strategy. This is a Log4j 2 configuration file and its syntax cannot be applied directly to JUL or Logback.

Log4j 2 supports filters at multiple locations, such as logger, appender reference, or appender. To classify by severity, marker, or other data, place the filter in the **right location** for your goal and verify the actual behavior. When using async logging, the time an event is created and the time it is written to file/network may differ.

## 8. Interaction Between Multiple Destinations and Log Collection Systems

On a personal machine, writing directly to files can be convenient. In containers or orchestration systems, a common approach is:

~~~text
Java application
      |
      +--> stdout / stderr --> container runtime --> log collector
      |                                        |
      |                                        +--> search / archive / alerts
      |
      +--> file (only when required and with a suitable volume)
~~~

The collection system may already replicate logs to search, archive, and alert destinations. In this case, configuring an additional remote appender inside the application for the **same event stream** easily increases bandwidth or produces duplicate records.

If using files inside containers, check volumes, container lifecycle, write permissions, disk space, and rotation mechanisms. A file inside a container's ephemeral filesystem can be lost when the container is replaced. With multiple replicas, each process may need its own file, or better yet, use stdout/stderr streams so the collector can attach metadata (service, pod, host, environment).

**Structured logging** helps multiple destinations share the same original event while formatting it differently:

- Console for developers: human-readable pattern.
- File/collector: JSON containing `timestamp`, `level`, `logger`, `message`, `traceId`, `spanId` when available.
- Audit: clear schema and access-control policy, not just "copying all regular logs".

One event can be formatted **differently in each appender**. That does not alter the original business content, but which fields appear in each output depends on the layout/encoder, MDC/tracing integration, and filters.

## 9. Performance, Reliability, and Lifecycle of Multiple Destinations

**Cost multiplies with destinations.** If an event is emitted simultaneously to console, file, and network, the application may have to run multiple formatters/encoders, perform multiple I/O operations, or enqueue multiple times. Synchronous logging can slow down requests if one destination is slow. With async appenders/handlers, the cost can shift to a queue/worker, but you must define the policy when the queue is full.

**One destination failing does not automatically guarantee another succeeds.** Depending on the backend, I/O errors may be reported via a status/error manager, ignored, cause blocking, or make a write path fail. Do not treat a log appearing on the console as proof that the event was definitely saved to a file or reached the centralized system.

**Flush and shutdown:** data in buffers/queues is not guaranteed to be durably written yet. When the application stops, the backend needs time/proper shutdown paths to flush and release file handles, sockets, or workers. In the JUL example, calling `flush`/`close` ensures the file is closed before inspecting its contents. When using a framework, prefer the logging lifecycle managed by the framework.

**Rotation and retention:** continuously growing files will fill the disk without a rotation/deletion policy. Configuring by size, time, and retention period depends on the backend; monitor actual disk usage. A handler in one JVM may be thread-safe across multiple threads, but that does not mean **multiple different JVMs can concurrently write to an arbitrary file** without risk.

**Per-destination security:** the console is viewed through a log platform, files are read by OS accounts, and remote collectors may store data in another system. Each destination needs appropriate log levels, masking/redaction, access permissions, and retention. Do not duplicate passwords, tokens, or sensitive personal data just to "have complete logs everywhere".

## 10. Common Issues and How to Troubleshoot Them

| Symptom | Cause to check | Resolution |
| --- | --- | --- |
| An event appears twice on the console | Both child logger and root have console handler/appender; additivity | Check logger hierarchy, parent handlers, and appender-ref |
| INFO appears in file but not on console | Console has WARNING threshold, file has INFO threshold | This may be the intended policy, not a bug |
| No INFO appears anywhere | Source logger is at WARNING or a filter rejects it | Check source level/filter before checking destinations |
| Log file does not appear | Missing directory, no write permission, wrong working directory | Check actual path and errors when opening the handler |
| Logs appear on console but missing in collector | Collection pipeline error, dropped events, or reading only one stream | Check collector, stdout/stderr, queue, filter, export |
| One event has multiple copies in central system | Both reading stdout and sending directly remotely, or multiple pipelines reading the same source | Establish a single primary collection path, add deduplication if needed |
| File grows without bound | FileAppender without rolling/retention | Configure rolling policy and monitor disk space |
| Tasks slow down when logging heavily | Synchronous I/O, heavy formatting, many destinations, or full queue | Measure cost, reduce verbosity, consider controlled async |
| Logs missing request/trace ID | MDC/tracing context not included in event/encoder | Attach context per request and check each layout |
| Logs lost on shutdown | Buffer/queue not flushed or process terminated abruptly | Use shutdown hook/lifecycle and proper exit policy |

## 11. Self-Check

With the `MultiDestinationLoggingDemo` program:

1. Why does `FINE cache hit` not appear? → The logger accepts `FINE`, but **both handlers** have higher thresholds.
2. Why is `INFO order created` only in the file? → FileHandler accepts from `INFO`; ConsoleHandler only accepts from `WARNING`.
3. If `logger.setLevel(Level.WARNING)` is changed, does `INFO` still go to the file? → No, the source logger filters it out first.
4. If `console.setLevel(Level.INFO)` is changed, what changes? → The console also prints `INFO: order created`, while `FINE` is still dropped by both handlers.
5. If `logger.setUseParentHandlers(false)` is removed in an application with handlers on root, what can happen? → Events may also go to parent handlers, creating extra or duplicate output.
6. If the same event is received by both file and console, did the application call the logger twice? → No; a single event can be fanned out to two handlers.
7. If the log file exists, is it guaranteed that the data has been sent to the remote collector? → No; you must verify the collection path separately.

**Key takeaway:** Multiple logging destinations allow distributing **a single log event** to handlers/appenders with separate levels, filters, formats, and storage policies. Set the logger level low enough to emit the necessary events, configure each destination for its intended purpose, avoid unintended duplicate writes, and thoroughly verify performance, access permissions, rotation, and the actual collection pipeline.