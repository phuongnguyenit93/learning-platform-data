# Logging to Files in Java: FileHandler, RollingFileAppender, and Safe Operations

## 1. Why Does an Application Need to Log to Files?

**File logging** is the practice of writing program events to one or more files on a storage system instead of only displaying them on the terminal. When a Java application handles requests, runs jobs, or communicates with a database, log files can help with:

- Investigating what happened before and after an incident occurred.
- Retaining technical evidence after a terminal session ends.
- Forwarding data to an agent or centralized platform via a file-reading mechanism.
- Separating logs by program, environment, or event type according to policy.
- Applying rotation, compression, retention, and access permissions.

Example contents of an `orders.log` file:

```text
INFO | event=order_received orderId=ORD-7
WARNING | event=payment_retry_scheduled attempt=2
SEVERE | event=order_save_failed orderId=ORD-8
```

In this example, **the content has already been formatted into text by a formatter**, while the file is the **destination**. Switching from console to file does not automatically change log levels, generate request IDs, or make messages safe.

Do not confuse **successfully writing to a file** with **guaranteeing that logs persist forever**. Files can be rotated, deleted by retention policy, affected by full disks or I/O errors, missed by a collector, or still sitting in a buffer when the process terminates abruptly.

In particular, in containers/Kubernetes, writing to **stdout/stderr** for the platform to collect is sometimes more suitable than local files; the choice must be based on your deployment architecture.

## 2. Components Involved in File Logging

A typical processing flow:

```text
Java business code
    |
    | logger.info(...), logger.log(...)
    v
Logging API / facade
    |
    v
Logging backend, level, and filter
    |
    v
Handler / Appender
    |
    +-- Formatter / Encoder
    |
    +-- Write to orders.log
    |
    v
File system (buffer, permissions, disk space...)
    |
    v
Log collector / shipper (if any)
```

Depending on the framework, the exact order among filters, formatters/encoders, and appenders varies. Their main responsibilities:

| Component | Example | Responsibility |
|---|---|---|
| API | JUL `Logger`, SLF4J `Logger` | Application emits events |
| Level/filter | `INFO`, `WARNING`, `ERROR` | Selects which events are kept |
| File sink | JUL `FileHandler`, Logback `FileAppender` | Writes received events to a file |
| Formatter/encoder | `SimpleFormatter`, `PatternLayoutEncoder` | Converts events to text/XML/JSON |
| Rolling policy | Size/time based | Renames/switches the active file and manages history |
| File system | Local disk, volume | Physically stores bytes; can fail |
| Collector | File-reading agent | Forwards events to search/aggregation systems |

A backend can allow attaching **multiple appenders** to write to both console and file. In that case, two copies might be forwarded to the collection system, easily doubling the number of lines if the collector reads both destinations. You should define a single primary pipeline.

## 3. The Simplest Approach in the JDK: JUL FileHandler

`java.util.logging` (JUL) is included with the JDK and requires no external libraries. To write to a file, we use:

- `java.util.logging.Logger`: where the application emits logs.
- `java.util.logging.FileHandler`: handler that writes events to a file.
- `java.util.logging.Formatter`: determines how output is rendered.
- `java.util.logging.Level`: determines severity level.
- `LogRecord`: a log event carrying a message, parameters, Throwable, and metadata.

Conceptual example:

```java
Logger log = Logger.getLogger("com.example.orders");
FileHandler file = new FileHandler("logs/orders.log", true);
file.setFormatter(new SimpleFormatter());
log.addHandler(file);
log.info("event=order_created");
```

This is an **illustrative snippet** that assumes the `logs` directory already exists and imports are declared. The `true` constructor argument enables **append mode**: attempting to add events to an existing file rather than starting over from scratch. The complete example in section 5 will create the directory, close the handler, and verify that the file was written correctly.

### 3.1. Path Conditions and Write Permissions

`FileHandler` is not a full directory-structure management tool. The application should ensure the parent directory exists before opening the file and that the account running the JVM has write permission there. A relative path such as `logs/orders.log` is resolved against the **process working directory**, not necessarily the directory containing the `.java` or `.jar` file.

Paths in development and production environments can differ. For example, running via an IDE, Maven, a service manager, or a container often has its own working directory; for stable configuration, use an explicit path specified in runtime config.

### 3.2. The Default Format Is Not Single-Line Text Like the Example

When creating a `FileHandler` without setting a formatter, JUL typically uses **`XMLFormatter`**. Therefore, calling `new FileHandler(...)` does not guarantee the file will contain text lines like `INFO event=...`. For plain text, set `SimpleFormatter` or write a custom `Formatter`.

`SimpleFormatter` can include timestamp, source, level, message, and exception; the output depends on the pattern and configuration. For data meant to be parsed by a collector, define a schema and escaping strategy rather than relying on something that merely "looks like JSON."

### 3.3. Appender Differs from Handler in Name, Not Purpose

In Logback, `FileAppender` or `RollingFileAppender` serves a role similar to JUL `FileHandler`. In Log4j 2, there are `File` and `RollingFile` appenders. **Do not copy configurations directly between them**: classes, levels, XML properties, and rolling policies have different semantics.

## 4. Append, Overwrite, and File Lifecycle

### 4.1. Appending (append)

```java
new FileHandler("logs/orders.log", true);
```

When the file opens successfully without lock conflicts, append mode preserves existing content and adds new events at the end. This is suitable when an application restarts and needs to continue writing to the same file.

However, append **does not replace rotation and retention**. Without a limit, the file can grow indefinitely until the disk is full. For long-running environments, configure rolling/rotation or delegate that responsibility to an external tool.

### 4.2. Overwriting from the Beginning (overwrite)

```java
new FileHandler("logs/orders.log", false);
```

Depending on the constructor, pattern, and how the backend opens the file, `false` selects **non-append mode**. This is useful for demos or tests that need deterministic output; in production, it can wipe out previous logs when the process restarts.

**Decide on append behavior based on log retention requirements**, not just by choosing `false` to make the file look shorter. When reproducing output for this lesson, we will intentionally use `false` and note that this is not a production policy.

### 4.3. Flush and Close

- `flush()` instructs the handler/stream to push out buffered data.
- `close()` closes the resource, releasing the file handle and associated lock mechanism.
- When the JVM dies abruptly, `finally` blocks or shutdown hooks **may not run**, and data in buffers/queues can be lost.
- Flushing in the application does not by itself guarantee that data has been fsynced to physical disk or processed by the collector.

A short-lived program must close the handler after writing, especially before reading the file back to verify its contents. Long-running server applications usually let the logging framework or process lifecycle manager close handlers at an appropriate shutdown phase rather than opening and closing a handler per request.

## 5. Complete Java 17+ Example: Write File, Close Handler, Read Result Back

This example uses **only the JDK**, with no Maven, SLF4J, Logback, or other dependencies. It does the following:

1. Creates the `logs` directory if it does not exist.
2. Opens `logs/orders.log`, sets UTF-8 encoding and a text formatter.
3. Logs INFO, WARNING, and SEVERE; attempts a FINE event to demonstrate handler-level filtering.
4. Closes the file handler.
5. Reads back the exact file that was written and prints each line to **stdout**.

### 5.1. File `FileLoggingDemo.java`

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.logging.FileHandler;
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class FileLoggingDemo {
    private static final Logger LOG =
            Logger.getLogger(FileLoggingDemo.class.getName());

    public static void main(String[] args) throws IOException {
        Path logDir = Path.of("logs");
        Files.createDirectories(logDir);

        Path logFile = logDir.resolve("orders.log");

        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.ALL);

        // false: start a fresh file so demo output is deterministic.
        FileHandler handler = new FileHandler(logFile.toString(), false);
        handler.setLevel(Level.INFO);
        handler.setEncoding(StandardCharsets.UTF_8.name());
        handler.setFormatter(new Formatter() {
            @Override
            public String format(LogRecord record) {
                return record.getLevel().getName()
                        + " | " + formatMessage(record)
                        + System.lineSeparator();
            }
        });

        LOG.addHandler(handler);
        try {
            LOG.log(Level.INFO,
                    "event=order_received orderId={0}", "ORD-7");
            LOG.log(Level.WARNING,
                    "event=payment_retry_scheduled attempt={0}", 2);
            LOG.fine("event=debug_probe");
            LOG.log(Level.SEVERE,
                    "event=order_save_failed orderId={0}", "ORD-8");
        } finally {
            LOG.removeHandler(handler);
            handler.flush();
            handler.close();
        }

        List<String> lines = Files.readAllLines(
                logFile, StandardCharsets.UTF_8);
        for (String line : lines) {
            System.out.println(line);
        }
    }
}
```

**Filename and class check:** the public class is `FileLoggingDemo`, so the code must be in `FileLoggingDemo.java`. The program calls only APIs built into Java 17 and imports neither Logback nor SLF4J.

### 5.2. Compiling and Running

In the directory containing `FileLoggingDemo.java`, using JDK 17 or newer:

```bash
javac -encoding UTF-8 FileLoggingDemo.java
java FileLoggingDemo
```

When run as a single process with write permissions and no other process holding a lock on `logs/orders.log`, the **exact stdout produced by the program** is:

```text
INFO | event=order_received orderId=ORD-7
WARNING | event=payment_retry_scheduled attempt=2
SEVERE | event=order_save_failed orderId=ORD-8
```

The `logs/orders.log` file also contains the three corresponding lines, using the operating system's line separator. The program does not print logs directly to the console from JUL, because `LOG.setUseParentHandlers(false)` is set and only `FileHandler` is attached. **The stdout output comes from the `System.out.println` loop after reading the file**, not from the file handler writing to stdout. Under normal conditions, stderr contains no logger messages from this example.

### 5.3. Why Are There Only Three Lines?

- `LOG.setLevel(Level.ALL)` allows the logger to emit detailed events.
- `handler.setLevel(Level.INFO)` only allows events at INFO or higher to reach the file.
- `LOG.fine("event=debug_probe")` is **filtered out by the handler**, so it does not appear in the file.
- `Formatter.formatMessage(record)` uses the parameters array to substitute JUL's `{0}`. This is **not SLF4J's `{}` syntax**.
- The formatter calls `getLevel().getName()`, so it outputs `WARNING` and `SEVERE` exactly as JUL names them rather than converting them to `WARN` or `ERROR`.
- `false` in the constructor resets the file when running the demo, avoiding accumulation from previous runs.
- `handler.close()` releases the file before the read-back loop; however, in the presence of lock collisions or I/O errors, exceptions should be handled according to application policy.

If you change `handler.setLevel(Level.INFO)` to `Level.ALL`, the `FINE` line will appear. If you keep the handler at `ALL` but change the logger to `INFO`, `FINE` is still dropped at the logger. **Logger and handler provide two separate layers of level control.**

### 5.4. An Intentional Limitation of the Demo

The custom `Formatter` above outputs only the level and message; if an event contains a `Throwable`, this example does not print the stack trace. In production, use a formatter that supports exceptions or properly handle `record.getThrown()`. Do not discard the cause chain just to keep log files looking tidy.

Also, do not call `Files.readAllLines` on huge log files: it loads the entire file into memory. Reading the file in the example is only for **verifying small output**. For large files, use streaming/tailing/collectors instead of loading the whole file onto the heap.

## 6. Logging Exceptions to Files: Preserving Throwable and Stack Trace

When an error occurs, a proper log call can pass the exception object:

```java
try {
    repository.save(order);
} catch (Exception error) {
    LOG.log(Level.SEVERE, "event=order_save_failed", error);
    throw error;
}
```

This snippet is a **JUL illustration**, not a standalone program; `repository` and `order` are undeclared. Moreover, **logging and rethrowing** can cause duplicate logs if an outer layer also logs the same exception. It is usually better to designate one boundary responsible for final error logging; intermediate layers propagate exceptions while preserving their cause.

In JUL, `LOG.log(Level.SEVERE, message, error)` attaches the `Throwable` to the `LogRecord`. However, the formatter decides how to render it. `SimpleFormatter` can output the stack trace, whereas the demo formatter in section 5 does not inspect `record.getThrown()`.

If writing a custom formatter, you can retrieve the exception:

```java
Throwable error = record.getThrown();
if (error != null) {
    // Choose a reliable procedure to append the stack trace/cause.
}
```

This is a **fragment** inside `format(LogRecord)`. Do not simply log `error.getMessage()` and assume that is enough information, because you can lose the exception type, root cause, and suppressed exceptions.

### MessageFormat and Throwable Are Separate Parts

JUL uses `{0}`, `{1}` for message parameters. If you need **both a parameterized message and a Throwable**, you can construct a `LogRecord` with both parameters and thrown:

```java
LogRecord record = new LogRecord(
        Level.SEVERE, "event=order_failed orderId={0}");
record.setParameters(new Object[]{"ORD-7"});
record.setThrown(error);
LOG.log(record);
```

The snippets above illustrate the API and assume `error` already exists. With a custom formatter, `formatMessage(record)` handles parameters and separate formatter logic handles the `Throwable`.

## 7. Configuring FileHandler with logging.properties

You do not always need to create handlers in code. JUL supports `LogManager` configuration, for example via a `logging.properties` file:

```properties
handlers=java.util.logging.FileHandler
.level=INFO

java.util.logging.FileHandler.level=ALL
java.util.logging.FileHandler.pattern=logs/application.%g.%u.log
java.util.logging.FileHandler.limit=1048576
java.util.logging.FileHandler.count=3
java.util.logging.FileHandler.append=true
java.util.logging.FileHandler.encoding=UTF-8
java.util.logging.FileHandler.formatter=java.util.logging.SimpleFormatter

java.util.logging.SimpleFormatter.format=%4$-7s %3$s - %5$s%6$s%n
```

This configuration is a **standalone properties file example**; make sure the `logs` directory already exists or use a path guaranteed to be writable. Depending on organizational policy, you can replace the log path with a mounted or dedicated directory with appropriate permissions.

With JUL's default loading mechanism, you can specify the file via a JVM property when running the application:

```bash
java -Djava.util.logging.config.file=logging.properties com.example.Main
```

This command is a **run template**, requiring `com.example.Main` to be compiled and the configuration file to exist at the specified path. In application servers or Spring Boot, the logging system may be managed by the framework through a different mechanism.

### 7.1. Property Meanings

| Property | Meaning |
|---|---|
| `handlers` | Handlers attached by configuration |
| `.level` | Root logger level as organized by LogManager |
| `FileHandler.level` | Filtering threshold specific to the file handler |
| `FileHandler.pattern` | Filename pattern and substitution tokens |
| `FileHandler.limit` | Size limit per file according to FileHandler rules |
| `FileHandler.count` | Number of files used in the rotation cycle |
| `FileHandler.append` | Append to existing file or start fresh |
| `FileHandler.encoding` | Character encoding used when writing |
| `FileHandler.formatter` | Formatter used to convert LogRecord to string |
| `SimpleFormatter.format` | Text pattern for SimpleFormatter |

Setting `.level=INFO` with handler `ALL` **does not enable FINE** if the root logger already filters it out. To see FINE, you must consider the effective level of the logger, handler, and filters along the path.

### 7.2. JUL Pattern Syntax Differs from Logback Pattern Syntax

In `SimpleFormatter`:

```text
%4$-7s  -> level, left-aligned, minimum 7 characters
%3$s    -> logger name
%5$s    -> formatted message
%6$s    -> Throwable section if present
%n      -> newline character
```

This is `java.util.Formatter` syntax for `SimpleFormatter`. It is **not** `%-7level`, `%logger`, `%msg` from Logback's `PatternLayout`. Each backend has its own set of tokens.

### 7.3. Why Might Configuration Have No Effect?

Common causes:

- The JVM did not load the expected `logging.properties`; the `-Djava.util.logging.config.file` path is wrong.
- A framework/container configured loggers/handlers in another way.
- The application also attaches its own handler in code, and events travel through two paths.
- A level or filter blocks the event before it reaches `FileHandler`.
- The directory or file is not writable, and the error is reported through an error handler/status rather than where the log emitter is watching.
- The file format is XML instead of the expected text format.

Do not guess "Logback isn't working" when the code is actually using JUL. Identify the logging API, backend, and configuration file actually being loaded.

## 8. File Rotation with JUL FileHandler

If an application logs without bounds, files can become a major burden. **Rotation** means switching to a new file when a condition is met, typically size or time.

JUL `FileHandler` supports rotation by **size** and **file count**. Illustrative constructor:

```java
FileHandler handler = new FileHandler(
        "logs/app.%g.%u.log",
        1_000_000,
        3,
        true);
```

This is a fragment requiring appropriate imports and directory. The parameters in order are:

1. Filename pattern.
2. Byte threshold per file.
3. Number of files in the rotation cycle.
4. Whether to append.

As logs approach or reach the threshold according to `FileHandler`'s implementation, the backend rotates through file generations. Do not assume that all three files will always be exactly `1_000_000` bytes or that every write splits cleanly on the boundary; a single record can push the size past the threshold depending on the write and rotation mechanism.

### 8.1. Filename Tokens

Important `FileHandler` tokens:

| Token | Meaning |
|---|---|
| `%g` | Generation number in the rotation cycle |
| `%u` | Unique number to resolve name/lock conflicts |
| `%t` | System-determined temporary directory |
| `%h` | Home directory of the user running the JVM |
| `%%` | Literal `%` sign |

For example, `logs/app.%g.%u.log` separates generation and unique index. If `%g` is omitted in a multi-file rotation setup, JUL may append the generation automatically. The actual filename is also affected by file lock state, other processes, platform, and pattern.

### 8.2. FileHandler Lacks Full Time-Based Rolling Policies

In the JDK, `FileHandler` **does not provide built-in daily rolling, `.gz` compression, exact N-day retention, and age-based deletion** like many dedicated rolling appenders.

If you need:

```text
Create a group of log files per day
Switch to the next file when a file reaches 10 MB
Compress historical files
Keep only 14 days
Cap total size at 1 GB
```

consider **Logback `RollingFileAppender`**, Log4j 2 `RollingFile`, external log rotation outside the JVM, or an appropriate collector. Avoid writing a complex custom `FileHandler` just to mimic full rolling policies if your project already has a backend that supports them.

### 8.3. Rotation Does Not Mean Exact Time-Based Retention

A file-count limit policy may not satisfy a requirement to "delete logs older than 90 days." Distinguish between:

- **Size-based rotation:** switch files when a size limit is reached.
- **Time-based rotation:** switch files by day/hour or time interval.
- **Retention:** determines how long old files are kept or how many are retained.
- **Compression:** compresses historical data; saves space but adds I/O.
- **Archiving:** moves old logs to separate storage; not automatically performed by rotation.

Define and test each responsibility, especially in environments with data retention regulations.

## 9. Using SLF4J + Logback to Write Files

In applications using the **SLF4J API** and **Logback backend**, `FileAppender` writes directly to a file, while `RollingFileAppender` is usually chosen when rotation is needed. Below is a configuration for learning how to select a target appender; it **does not use JUL syntax**.

### 9.1. Simple FileAppender

File `logback.xml`:

```xml
<configuration>
    <appender name="FILE"
              class="ch.qos.logback.core.FileAppender">
        <file>logs/orders.log</file>
        <append>true</append>
        <encoder>
            <pattern>%d{yyyy-MM-dd'T'HH:mm:ss.SSSXXX} %-5level %logger{36} - %msg%n</pattern>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="FILE"/>
    </root>
</configuration>
```

In Logback, `%d` is the timestamp, `%-5level` is the padded level, `%logger{36}` is the shortened logger name for display, and `%msg%n` is the message plus newline.

This is a **Logback configuration file**; running it requires the SLF4J API and a compatible Logback Classic provider. Do not use `java.util.logging.FileHandler` if your application uses Logback as its backend without an appropriate bridge.

**Difference from the JUL demo:** Logback can create parent directories during `FileAppender` initialization depending on the version's capabilities, but you must still verify write permissions, mounts, and actual paths; do not treat "auto-create directories" as immunity against I/O errors.

### 9.2. RollingFileAppender by Day and Size

A fuller `logback.xml`:

```xml
<configuration>
    <appender name="FILE"
              class="ch.qos.logback.core.rolling.RollingFileAppender">
        <file>logs/orders.log</file>

        <rollingPolicy
                class="ch.qos.logback.core.rolling.SizeAndTimeBasedRollingPolicy">
            <fileNamePattern>logs/orders.%d{yyyy-MM-dd}.%i.log.gz</fileNamePattern>
            <maxFileSize>10MB</maxFileSize>
            <maxHistory>14</maxHistory>
            <totalSizeCap>1GB</totalSizeCap>
        </rollingPolicy>

        <encoder>
            <pattern>%d{yyyy-MM-dd'T'HH:mm:ss.SSSXXX} %-5level %logger{36} - %msg%n</pattern>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="FILE"/>
    </root>
</configuration>
```

This configuration illustrates a **SizeAndTimeBasedRollingPolicy** in Logback with the active file `logs/orders.log`, historical files containing both date and index, and gzip compression.

- `%d{yyyy-MM-dd}` defines daily grouping.
- `%i` distinguishes multiple files within the same period when the size limit is exceeded.
- `maxFileSize` sets the size threshold for rolling over.
- `maxHistory=14` asks to keep the corresponding number of **historical periods**, not a guarantee of minute-exact clock deletion.
- `totalSizeCap` sets a cap on historical size according to the backend's policy and cleanup order, not a quota for the entire disk.

Verify properties, cleanup lifecycle, and behavior when changing Logback versions. **This is not a guarantee tested across every filesystem.** File rotation can generate significant compression/file-creation overhead, so monitor I/O and storage.

### 9.3. Java Code Example Calling SLF4J

In an application that already has SLF4J + Logback provider:

```java
private static final org.slf4j.Logger LOG =
        org.slf4j.LoggerFactory.getLogger(OrderService.class);

LOG.info("event=order_accepted orderId={}", orderId);
```

This is a **fragment** inside a class with `OrderService` and an `orderId` variable; it is not a standalone Java file. The call uses SLF4J's `{}` placeholder. Logback reads the appender configuration and writes to the file; business code does not need to call `new FileHandler(...)`.

An advantage is that **replacing `FileAppender` with `RollingFileAppender` usually requires no changes to SLF4J calls** when the API and backend are properly separated.

## 10. Log4j 2: File and RollingFile Appenders

Log4j 2 also provides file and rolling appenders, but with its own configuration format. Example `log4j2.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<Configuration>
    <Appenders>
        <RollingFile name="FILE"
                     fileName="logs/orders.log"
                     filePattern="logs/orders-%d{yyyy-MM-dd}-%i.log.gz">
            <PatternLayout
                    pattern="%d{ISO8601} %-5p %c{1} - %m%throwable%n"/>
            <Policies>
                <TimeBasedTriggeringPolicy interval="1"
                                           modulate="true"/>
                <SizeBasedTriggeringPolicy size="10 MB"/>
            </Policies>
            <DefaultRolloverStrategy max="10"/>
        </RollingFile>
    </Appenders>

    <Loggers>
        <Root level="info">
            <AppenderRef ref="FILE"/>
        </Root>
    </Loggers>
</Configuration>
```

This is an example **Log4j 2 configuration**, requiring Log4j 2 Core, matching API/provider, and a version supporting these components.

`DefaultRolloverStrategy max="10"` relates to the file index policy during rollover; it **should not be naively understood as keeping all logs for exactly 10 days**. If you need age-based or path-condition deletion, use the delete/retention strategy supported by Log4j 2 and verify the result in a real environment.

Do not use Log4j 2 XML in `logback.xml`; tokens like `%d` and `%p` look similar, but the two backends do not share a configuration schema.

### 10.1. Which Solution Should You Choose?

| Need | Reasonable Choice |
|---|---|
| Small Java tool, no dependencies | JUL `FileHandler` |
| SLF4J app already using Logback | Logback `FileAppender` or `RollingFileAppender` |
| App standardized on Log4j 2 | Log4j 2 `File`/`RollingFile` |
| Container microservice with stdout collector | Usually prefer console appender + collector |
| Audit logs requiring integrity/durability | Dedicated audit pipeline or compliant storage |

No backend solves all risks simply by having "File" or "Rolling" in its name.

## 11. Writing to One File from Multiple Threads and Multiple Processes

### 11.1. Multiple Threads in One JVM

Mainstream backends/handlers typically handle internal synchronization appropriately. However, **event ordering** still depends on thread scheduling and queue/appender mechanisms:

- Two threads emitting events close together may enqueue or write in an order that does not match business order.
- An event's timestamp may differ from the moment bytes are physically written to the file.
- File content may reflect a valid processing order, but it is not automatically a linear history of the entire system.

When you need to trace the event flow of a request, log `requestId`/`traceId` and necessary business identifiers. Do not rely solely on line position in a file to infer causality between concurrent tasks.

### 11.2. Multiple JVMs/Processes Writing to One File

This is a harder problem. It is not safe by default for two JVMs to open `logs/orders.log` in append mode simultaneously. You may encounter lock contention, interleaved output, delays, or rotation causing lost/mixed data.

JUL `FileHandler` uses locking and the `%u` token to distinguish files on collision; do not rely on that to have multiple processes share a single file across arbitrary filesystems. In Logback/Log4j 2, multi-process/prudent mode configurations have their own limitations on rolling and features.

Practical approaches that are usually safer:

- Each process/instance writes to its own destination with a stable name/ID.
- Or emit logs to stdout/stderr and let the platform collect from multiple instances.
- Or use a centralized mechanism/agent designed for multi-process collection.

Do not put the PID or individual request ID into the logger name; that does not solve file separation or correlation.

### 11.3. JUL File Locks

While a `FileHandler` is open, you may see a lock file ending in `.lck` associated with the pattern. After the handler closes normally, the lock is usually released. If a process dies abnormally or the environment has issues, investigate the lock/collision state and permissions; do not arbitrarily delete a lock file that another process is using.

## 12. When Should You Write to Files Instead of stdout/stderr?

In containers or orchestration systems, applications are commonly recommended to write logs to stdout/stderr for the runtime/agent to collect, because files in a container's ephemeral filesystem can disappear when the container is replaced.

Advantages of stdout/stderr:

- No need for the application to manage local file paths and directory permissions itself.
- The collector can attach pod/container/service metadata and centralize logs.
- Reduces the need for per-instance file rotation when the platform already handles it.

However, understand the limitations:

- The runtime and collector still have buffering, rotation, quotas, and risk of log loss.
- Each container platform has its own stdout/stderr and retention policies.
- Excessive console logging can hurt performance; stdout is not "free."
- If strict forensic/audit guarantees are required, ordinary console collection may lack sufficient integrity.

File logging still makes sense for desktop apps, batch jobs on fixed hosts, legacy software, outputs that must be compatible with a file shipper, or environments requiring local storage. Choose based on the **actual collection path**.

## 13. Log Rotation, Retention, and Operational Cost

When choosing file logging, consider three groups of questions:

### 13.1. Volume and Growth Rate

If an application generates 1,000 log events/second averaging 500 bytes each, raw log throughput is roughly 500,000 bytes/second. Over an ideal constant-rate day, that is about 43.2 GB of data before compression and metadata. This is only an illustrative calculation, excluding bursts, stack traces, or duplicated output.

Therefore, you should:
- Limit log volume with appropriate levels/filters.
- Avoid logging full payloads, SQL results, or large objects unnecessarily.
- Size rotation/retention and quotas for peak load, not just average load.
- Monitor storage pressure, inode count, and log shipping rate.

### 13.2. Retention Must Match Policy

Do not delete logs earlier than compliance requires, nor keep unnecessary personal data or sensitive information indefinitely. Policies depend on business domain, law, and organization; this article does not prescribe a single mandatory day count for all applications.

When a rolling policy compresses/deletes files, verify that the collector has finished reading all data before deletion. A file can be rotated and deleted **before the agent successfully collects it** if the pipeline is disrupted long enough.

### 13.3. Account for Both Storage and Collection

An application may simultaneously:
1. Write logs to a local file.
2. Have an agent read the file and send it to a collector.
3. Have the collector store indexed data and backups.

Account for costs at all three stages, including retention, replication, and network. **Rotating a file in the application does not delete data in the collector**, and deleting data in the collector does not clean up local files.

## 14. Synchronous vs. Asynchronous File Logging and Data Guarantees

Synchronous file writing usually happens on the calling thread that emits the event, though Java streams/OS may still buffer. Asynchronous writing typically adds an in-JVM queue to reduce waiting time for business threads.

Comparison:

| Property | Synchronous FileAppender/FileHandler | Async Appender Wrapping File |
|---|---|---|
| Thread performing file write | Usually caller | Appender worker |
| Caller latency under slow I/O | Can increase | Usually lower while queue has space |
| Backlog memory | Lower at logging layer | Queue holds additional events |
| When sink is slow for long | Caller may block | Queue full -> block/drop per policy |
| When JVM is force-killed | Buffered/in-flight records may be lost | Additional queued events not yet written by worker |
| Shutdown | Needs flush/close | Needs queue drain, then flush/close |

Logback's `AsyncAppender` has parameters such as `queueSize`, `discardingThreshold`, `neverBlock`, and `maxFlushTime`. Configuration can favor latency or preserve events by blocking producers when the queue is full; **no mode automatically guarantees exactly-once delivery**.

If logs are genuinely business-critical data that must not be lost (audit, reconciliation, transactions), use a durable architecture designed for that goal: transactional outbox, database/event log, or an audit store with acknowledgment semantics, rather than trusting `flush()` or `AsyncAppender` to suffice.

## 15. File Formats: Text, JSON, and Multiline Handling

### 15.1. Plain Text

Plain text is convenient when you need to `tail` or read directly:

```text
2026-11-09T08:15:03.125Z INFO  order-api event=order_accepted orderId=ORD-7
2026-11-09T08:15:04.140Z ERROR order-api event=order_save_failed orderId=ORD-8
```

The lines above are a **schema example**, not the automatic output of the program in section 5. If a parser splits on spaces, you need stable rules when messages contain spaces or special characters.

### 15.2. JSON Lines

A collector-friendly format is **one JSON object per event per line**:

```json
{"timestamp":"2026-11-09T08:15:03.125Z","level":"INFO","logger":"com.example.orders.OrderService","event":"order_accepted","orderId":"ORD-7","traceId":"trace-42"}
```

This is an illustrative JSON sample. JUL `FileHandler` does not automatically turn messages into JSON with business fields; you need an encoder/formatter or suitable converter. Logback/Log4j 2 also require a supported and properly configured JSON layout/encoder.

Do not build JSON by string concatenation when free-form input is present. Quotes, backslashes, newlines, and control characters must be properly escaped by a standard serializer. **SLF4J/JUL placeholders do not automatically become structured fields.**

### 15.3. Multiline Stack Traces

When a formatter writes a full stack trace, a single ERROR event can span many text lines. If a file shipper defaults to treating **every newline as a new event**, it may split the stack trace into fragmented events.

Solutions:
- Configure multiline parsing in the shipper/collector matching your actual pattern and backend.
- Or use JSON lines / structured format with the exception serialized into a valid field.
- Ensure user-supplied input cannot spoof a new timestamp/level line.

The goal is to preserve the message, cause chain, and relationships of an exception, not merely to make the console look pretty.

## 16. Security When Logging to Files

Log files often contain transaction IDs, request IDs, exception messages, and sometimes user data. Files must be managed as **potentially sensitive data assets**, not harmless debug artifacts.

### 16.1. Paths, Permissions, and Ownership

- Choose a log directory writable by the process but not publicly accessible to unrelated users.
- Restrict read permissions on log files by operational role.
- Be cautious with shared directories, user-controlled path inputs, symlinks, or overly permissive mounts.
- Never construct file paths by concatenating untrusted values such as username, URL path, or arbitrary request parameters.
- Monitor quotas so a repeating error does not fill a filesystem holding critical data.

### 16.2. Do Not Log Secrets or Excessive Data

Never log passwords, access tokens, API keys, session cookies, card data, connection strings containing credentials, or request/response bodies with unnecessary personal data. Exception messages from HTTP/JDBC libraries can also contain URL queries, inputs, or sensitive details.

Apply redaction/masking at the source, encoder/formatter, and pipeline where appropriate. **Simply raising the level from DEBUG to INFO does not guarantee sensitive data is removed**, as those values can appear in INFO or ERROR logs.

### 16.3. Log Injection

If a user supplies a string containing newlines, they can forge multi-line output and corrupt log analysis tools. Text formatters should sanitize or encode untrusted input per policy. For JSON, use a standard serializer to escape newlines and quotes rather than building JSON via concatenation.

### 16.4. Files Shipped Elsewhere

Local file permissions do not automatically protect data after an agent sends it to a collector. Add TLS/transport policies, access controls, encryption at rest, retention limits, query auditing, and deletion policies as required.

## 17. Handling Failures When File Logging Fails

File logging can fail because of:
- Missing directory or insufficient permissions.
- Another process holding a lock on the file.
- Disk full, inode exhaustion, quota exceeded, or read-only filesystem.
- Mounted/network filesystem failure.
- Closed appender, misconfiguration, or resource exhaustion.
- Failed rotation/rename/compression.
- Collector failing to read/process the file even though the program wrote successfully.

In JUL, internal handler errors may be routed to an `ErrorManager`/logging error mechanism rather than surfacing as a normal exception at `LOG.info(...)`. In Logback/Log4j 2, check the backend's **internal status reporting** and diagnostics.

**Do not assume a successful logger call means the file write succeeded.** When an application depends on logs as a strict requirement, implement error detection and appropriate data persistence mechanisms.

Another risk is **recursive logging**: if a file appender fails and uses the same logger/appender to report its own failure, it can create a loop, spike load, and obscure the root cause. Internal error reporting must use a separate path.

## 18. Verification and Troubleshooting

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Log file missing | Wrong working directory, config not loaded, or appender not initialized | Verify actual path and internal status |
| Write permission denied | JVM user lacks permission or volume is read-only | Adjust directory/mount permissions per policy |
| File is in XML format | JUL `FileHandler` using default formatter | Set `SimpleFormatter` or custom `Formatter` |
| File cleared after restart | Opened with `append=false` | Switch to `append=true` and an appropriate rolling policy |
| File grows without rotating | Using plain `FileAppender` or JUL `FileHandler` without limit | Enable verified rolling/rotation |
| Strange filenames or `.lck` files | `FileHandler` generation/unique tokens, collisions/locks | Check pattern, processes, locks, and `close()` |
| DEBUG/FINE missing from file | Filtered by logger level, handler/appender level, or filter | Verify effective level at both layers |
| Events appear twice | Both console+file collected or parent handler active | Check output paths and propagation/additivity |
| File has logs but dashboard empty | Agent/collector not reading, parser error, or indexing lag | Trace file -> shipper -> collector end-to-end |
| File lost after container restart | Written to ephemeral container filesystem | Use stdout collection or managed persistent volume |
| Stack trace split into multiple records | Collector treats each newline as a separate event | Configure multiline parsing or JSON encoder |
| Garbled Unicode characters | Mismatched encoding/decoder | Standardize on UTF-8 and check reader/collector |
| Logging works but app slows down | Synchronous I/O, high log volume/formatting cost | Measure throughput; tune level, appender, or bounded async |
| Tail logs lost on shutdown | Missing flush/close, async queue backlog, killed too early | Design shutdown grace period and inspect backlog |
| Disk full | No retention/quota/monitoring | Add rolling, historical cleanup, and disk alerts |
| Log file misparsed | Unstable text format or unescaped newlines in input | Standardize encoder/schema and escaping |

### Ordered Investigation Checklist

1. Identify the **logging API and backend**: JUL, Logback, Log4j 2, or a bridge.
2. Identify the **actual loaded config file** and initialized handlers/appenders.
3. Check effective logger level, handler/appender level, and filters.
4. Check working directory, file pattern, file locks, permissions, and disk space.
5. Check formatter/encoding and parameterized or exception messages.
6. Check append/rotation/retention and whether multiple instances write to the same file.
7. Verify whether the actual file receives new bytes before checking the agent/collector.
8. If the file has data but the dashboard does not, inspect the pipeline downstream of the file instead of arbitrarily changing log levels.

## 19. Self-Check Exercises

### Scenario A: Logs "Disappear" After Every Run

A Java tool uses `FileHandler("logs/tool.log", false)`. On each rerun, old logs vanish.

- Explain the cause.
- Suggest switching to append when content should be preserved.
- If the tool runs for weeks, what additional mechanism is needed to prevent unbounded file growth?

**Hint:** `append=false` disables appending. Change it to `true` to keep prior content; also configure rotation, retention/quotas, and check locking.

### Scenario B: Running via Maven Puts the File Elsewhere

Code opens `Path.of("logs", "app.log")`. When launched from an IDE vs. a service manager, the file appears in two different directories.

**Explanation:** relative paths resolve against the process working directory. For consistency, configure an explicit log directory per environment, or use console/agent collection matching your deployment architecture.

### Scenario C: Log File Has Two Lines per Event

An application attaches a `FileHandler` directly to a logger while a parent handler is also active; the collector also reads both console and file.

**Explanation:** multiple paths can duplicate events. Trace the `logger -> handler` and `appender -> collector` flows, remove unintended duplicate destinations, and do not merely delete a `logger.info(...)` call.

### Scenario D: Final Job ERROR Is Missing from File Even Though stdout Has It

An application uses an async file appender; the queue still has a backlog when the container is terminated before the worker finishes.

**Explanation:** the event was enqueued, not necessarily written. Ensure proper shutdown/lifecycle handling and evaluate event-loss risk; mandatory audit data should use a mechanism more durable than an in-memory queue.

## 20. Pre-Deployment Checklist for File Logging

- [ ] Chosen the right logging API/backend and **actual file appender/handler**.
- [ ] File path and working directory are explicit, with proper write permissions.
- [ ] Append/overwrite mode matches requirements, avoiding log loss on restart.
- [ ] Logger level, handler/appender level, and filters permit the intended events.
- [ ] Formatter/encoder has consistent format and encoding, handling `Throwable`/cause chains.
- [ ] Configured size/time rotation and retention/quotas per requirements.
- [ ] Tested behavior for file locks, disk full, permission denied, and mount failures.
- [ ] Not arbitrarily writing to a shared file from multiple JVMs/instances.
- [ ] If a collector reads the file, verified end-to-end delivery, multiline handling, rotation, and latency.
- [ ] If using async, configured queue-full policy, flush/shutdown, and acceptable loss bounds.
- [ ] No secrets logged; proper escaping and file permissions are in place.
- [ ] Chosen stdout/stderr vs. file based on actual container/server architecture.
- [ ] Monitoring in place for disk usage, write errors, file count, and collector backlog.
- [ ] Ran test output and read back the file to verify levels, encoding, and format.

**Conclusion:** logging to files in Java can start very simply with JUL's `FileHandler` or Logback/Log4j 2's `FileAppender`. Reliable file logging, however, requires more than a path: **file lifecycle management, permissions, formatting, rotation, retention, I/O error handling, and the collection pipeline**. When an application is packaged and deployed across multiple instances or containers, consider stdout + collector before assuming every process must manage its own log files.
