# FileHandler in Java Util Logging

**`java.util.logging.FileHandler`** is a Java Util Logging (**JUL**) `Handler` used to write `LogRecord` instances to files on the filesystem. Instead of only seeing logs on the console, an application can persist events for investigation after the process exits. `FileHandler` supports configuring filename patterns, appending vs. starting a new file, size limits and file rotation, as well as choosing a formatter and level.

To use `FileHandler` properly, you need to distinguish three things: **whether the logger accepts the event**, **whether the handler accepts the event**, and **what format the handler uses to write the record to the file**. Creating a new `FileHandler` is not enough: you must attach it to a logger or configure `LogManager`, set the formatter/level, manage the handler lifecycle, and verify the actual output.

## 1. Role in the JUL Architecture

A typical logging flow:

```text
Java code
   |
   | logger.log(Level.INFO, "...") / logger.info(...)
   v
java.util.logging.Logger
   | check effective level, filter
   v
java.util.logging.LogRecord
   | may propagate to parent logger
   v
java.util.logging.FileHandler
   | check handler level, filter
   | Formatter -> string/bytes
   v
Log file on disk
```

`FileHandler` is a subclass of `StreamHandler`; it manages the output stream and related files. The content of each record is formatted by a `Formatter`, such as `SimpleFormatter` or `XMLFormatter`. `FileHandler` does not decide on its own whether an event is `INFO` or `SEVERE`: the level is specified by the logging code, and the handler can filter out records based on its threshold.

| Component | Responsibility | Example |
| --- | --- | --- |
| `Logger` | Receives logging requests and decides whether to create/forward an event. | `Logger.getLogger("com.example.orders")` |
| `Level` | The level of the event and the corresponding filtering threshold. | `INFO`, `FINE`, `WARNING` |
| `LogRecord` | Object carrying the level, message, logger name, parameters, `Throwable`, and metadata. | `order.failed` event with a `Throwable` |
| `FileHandler` | Receives records to write to a file; manages opening/closing, locking, and rotation. | `new FileHandler("app.log", true)` |
| `Formatter` | Converts a record into formatted text/XML. | `SimpleFormatter`, `XMLFormatter` |
| `Filter` | Accepts or rejects events according to additional rules. | Only accept records for a specific group of events |
| `LogManager` | Reads and manages JUL configuration. | `logging.properties` |

**Distinction:** `ConsoleHandler` writes to the console stream (typically stderr); `FileHandler` writes to a file. Both are JUL handlers and can be attached to the same logger simultaneously. A record reaching multiple handlers can be written to multiple destinations. This is different from **duplicate logging**, where the same record appears multiple times unexpectedly at a single destination due to handler configuration and propagation.

## 2. Creating and Attaching a FileHandler

Common constructors:

| JUL Constructor | Purpose |
| --- | --- |
| `new FileHandler()` | Uses default configuration or JUL properties from `LogManager`, including the pattern and write policies. |
| `new FileHandler(String pattern)` | Uses the specified pattern; starts a new file by default. |
| `new FileHandler(String pattern, boolean append)` | Explicitly chooses whether to append (`true`) or start a new file (`false`) when opening. |
| `new FileHandler(String pattern, int limit, int count)` | Limits the number of bytes per file and the number of rotated generations; uses the default append mode. |
| `new FileHandler(String pattern, int limit, int count, boolean append)` | Explicitly sets the pattern, limit, generation count, and append mode. |

Modern JDKs also provide overloads accepting `long limit`; when you need limits beyond the `int` range, check your JDK version and the official API. The examples in this article use the common overloads available on JDK 17.

Creating a `FileHandler` can throw `IOException` (failing to open/create/lock the file), or errors for invalid arguments/configuration. The parent directory of the path must exist, and the process needs sufficient write permissions. When creating a handler manually, consider how to handle startup failures rather than assuming the operation always succeeds.

Minimal example (illustrative snippet inside a method, assuming `logger` has already been created):

```java
import java.io.IOException;
import java.util.logging.FileHandler;
import java.util.logging.Level;
import java.util.logging.SimpleFormatter;

void attachFileLogging(java.util.logging.Logger logger)
        throws IOException {
    FileHandler file = new FileHandler("application.log", true);
    file.setLevel(Level.INFO);
    file.setFormatter(new SimpleFormatter());
    logger.addHandler(file);
}
```

The snippet above only illustrates how to attach a handler; **it is not a complete standalone Java class**. Because the handler continues operating after the method returns, the application must manage the reference and call `close()` at the appropriate time, typically on service shutdown. Do not create a new `FileHandler` per request: each instance has its own output stream/lock and can create many files or exhaust resources.

## 3. Filename Patterns and Placeholders

`FileHandler` takes a `pattern` string to determine filenames. JUL supports the following placeholders:

| Placeholder | Meaning | Use Case |
| --- | --- | --- |
| `%h` | Home directory of the user running the process. | `%h/application.log` |
| `%t` | System/JVM temporary directory. | `%t/myapp.log` |
| `%g` | Generation number for file rotation, starting at 0. | `app.%g.log` |
| `%u` | Unique number to avoid filename/lock conflicts. | `app.%u.log` |
| `%%` | Literal `%` character in the filename. | `metrics-%%-service.log` |

In a JUL pattern, these placeholders are **FileHandler rules**, not shell environment variables and not message placeholders like `{0}`. `%g` and `%u` are computed by the file management mechanism; do not use them as substitutes for `requestId` or deployment version IDs.

Some examples:

```text
%h/java-app.log
%t/java-app-%u.log
%h/logs/app-%u.%g.log
```

If you place the pattern in `%h/logs/app-%u.%g.log`, you must **create the `logs` directory beforehand** under the home directory or have a directory preparation mechanism at deployment time. `FileHandler` does not automatically create arbitrary directory trees.

Notes:

- With multiple rotated generations (`count > 1`), if the pattern does not contain `%g`, the JUL implementation automatically appends the generation part to the name according to its rules. Use `%g` explicitly to avoid confusion.
- If a filename is held by another handler/process and a unique name is needed, `FileHandler` can add a uniqueness component when `%u` is absent. Do not guess the exact filename when multiple JVMs run concurrently; choose a pattern containing `%u` and inspect the actual result.
- A `FileHandler` instance uses the files it manages, not a cross-machine log aggregation system. If a container is replaced, files in the local filesystem may no longer exist unless a volume is mounted or logs are forwarded to another system.
- Place logs in a directory with write permissions, sufficient disk space, and appropriate security and retention policies. Avoid paths containing sensitive information.

## 4. Append, Overwrite, and Lifecycle Handling

**`append=false`** means that when opening the handler, write mode starts the target file fresh (replacing existing file contents according to `FileHandler` behavior). **`append=true`** allows appending to existing data when opening a suitable file. This does not replace rotation/retention policies and does not guarantee durable writes in every crash scenario.

```java
// Illustrative snippet, not a standalone program.
FileHandler overwrite = new FileHandler("app.log", false);
FileHandler append = new FileHandler("another-app.log", true);
```

The two handlers in the example intentionally use **two different files** to avoid lock contention; both must be closed after use. Do not open two handlers for the same file and expect both to write safely and concurrently to a shared stream.

### When to close a handler?

- When the application actually shuts down or changes logging configuration, call `close()` to flush, close the stream, and release resources/locks.
- When detaching a handler from a logger with `removeHandler(handler)`, that **does not automatically close** the handler; you still need to call `close()`.
- For logging in unit tests or demos, use `try/finally` to ensure the handler is closed even if an error occurs.
- `flush()` pushes buffered content to the output stream; `close()` also closes the stream and releases resources. Do not treat `flush()` as synonymous with guaranteeing data has been fsynced to storage.
- Do not call `close()` immediately after every record: doing so creates unnecessary I/O, locking, and file management overhead; a handler typically has a long lifecycle matching the service.

`FileHandler` may create a lock file with the `.lck` suffix while active to coordinate and prevent multiple handlers from claiming the same filename. The lock file is normally released when the handler is closed properly. If the process is terminated abruptly, leftover lock files may remain; check the behavior of your JDK version and filesystem before deleting or reusing them, especially on shared filesystems.

## 5. Size Limits and Rotation

Rotation prevents a single log file from growing forever. With the constructor:

```java
// Limit of approximately 1 MiB/file, keeping 3 generations.
// Illustrative snippet, not a standalone program.
FileHandler handler = new FileHandler(
        "app-%u.%g.log",
        1024 * 1024,
        3,
        true
);
```

- **`pattern`** determines how files are named across generations and instances.
- **`limit`** is the file size threshold in **bytes**, not the number of records or Unicode characters.
- **`count`** is the number of generation files a handler can manage for that pattern; it must be a positive number.
- **`append`** controls how file contents are handled on open and affects cases where old logs already exist.

When the size reaches the threshold, `FileHandler` rotates the files, keeping the configured set of file generations. With `app-%u.%g.log`, generation `0` is typically the file currently being written to, while higher-numbered generations store older data. Once `count` is reached, the oldest data can be replaced according to the rotation mechanism. JUL rotation is **size-based**; it does not run on a daily schedule or by number of retention days.

**Limitations to understand:**

1. The `limit` threshold is not a guarantee that the final file size *never exceeds* the exact configured byte count: a large record can cause the file to exceed the threshold before rotation occurs.
2. `count=3` does not mean keeping three days of history; under heavy load, three generations can be replaced very quickly.
3. `limit=0` means no size-based rotation limit is enforced in JUL; to avoid filling the disk, you still need a system-level policy.
4. Rotation is different from **retention**: retention is the rule for long-term deletion/preservation based on time, total size, or governance requirements. `FileHandler` does not provide a full retention, archive compression, indexing, or log-shipping system.
5. When an application spawns multiple instances or multiple JVMs, each handler has its own locking and files; you cannot deduce the total number of files on the machine from a single handler's `count`.

If the environment requires daily rotation, compression of old files, time-based deletion, or storage in object storage, consider an appropriate log collector/log rotation tool or a backend that supports richer policies. Avoid having two systems rotate the same file without understanding how they interact, as this can cause lost records or writes to unintended files.

## 6. Formatter: How Is File Content Written?

The default formatter for `FileHandler` in JUL is typically `XMLFormatter`, so file contents may not be plain text lines but structured XML (`<log>...`). To make logs convenient to read with a text editor or `grep`, you can use `SimpleFormatter` or a custom formatter.

```java
// Illustrative snippet inside a method with a handler variable.
handler.setFormatter(new java.util.logging.SimpleFormatter());
```

`SimpleFormatter` writes human-readable text and supports displaying `Throwable` information; the output can include timestamp, logger/source, level, message, and stack trace, depending on configuration. If the application needs JSON for field-based filtering, you must use an appropriate formatter/encoder (from a library or verified code); changing the file extension to `.json` does not automatically produce valid JSON.

### Encoding

In multilingual environments, you should specify the encoding when logging non-ASCII text (such as Vietnamese) and when collectors read the file:

```java
// Illustrative snippet; may throw UnsupportedEncodingException.
handler.setEncoding("UTF-8");
```

The encoding setting must be consistent with the formatter and file analysis tools. Choose it before writing records that need to preserve Unicode characters; do not assume all operating systems/JDKs use the same default charset. Do not manually concatenate text/JSON if the data source may contain untrusted control characters.

### Logging Exceptions

To preserve error details in the file, pass the `Throwable` object to the logger using the appropriate overload:

```java
// Snippet inside a catch block; assumes logger already exists and ex is a Throwable.
logger.log(
        java.util.logging.Level.SEVERE,
        "event=order.persist_failed orderId=ord-42",
        ex
);
```

`FileHandler` receives the `LogRecord` containing `thrown`. The formatter decides whether to display the stack trace/cause; a custom formatter that only outputs `record.getMessage()` will lose the error details in the file even though `Throwable` was passed properly. In JUL, passing an exception to the `log(Level, String, Throwable)` overload is different from passing arguments for `{0}` placeholders.

## 7. Standalone Java 17 Example: Writing to a File and Checking Output

This example creates a dedicated temporary directory, writes two events to a file with a simple formatter, closes the handler, reads the file to the console, and deletes the temporary files. No dependencies outside the JDK are required. Because temporary paths vary by machine, the program only prints the **log contents**, not the path.

Save the file as **`FileHandlerDemo.java`**:

```java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.logging.FileHandler;
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class FileHandlerDemo {
    public static void main(String[] args) throws Exception {
        Path directory = Files.createTempDirectory("jul-file-handler-");
        Path logFile = directory.resolve("application.log");

        Logger logger = Logger.getLogger(FileHandlerDemo.class.getName());
        logger.setUseParentHandlers(false);
        logger.setLevel(Level.FINE);

        FileHandler file = new FileHandler(logFile.toString(), false);
        file.setEncoding(StandardCharsets.UTF_8.name());
        file.setLevel(Level.INFO);
        file.setFormatter(new Formatter() {
            @Override
            public String format(LogRecord record) {
                return record.getLevel().getName()
                        + " | " + formatMessage(record)
                        + System.lineSeparator();
            }
        });
        logger.addHandler(file);

        try {
            logger.fine("job=42 internal-validation");
            logger.log(Level.INFO, "job={0} started", 42);
            logger.log(Level.WARNING, "job={0} fallback", 42);
        } finally {
            logger.removeHandler(file);
            file.close();
        }

        for (String line : Files.readAllLines(
                logFile, StandardCharsets.UTF_8)) {
            System.out.println(line);
        }

        Files.deleteIfExists(logFile);
        Files.deleteIfExists(directory);
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac FileHandlerDemo.java
java FileHandlerDemo
```

**Exact standard output when run successfully:**

```text
INFO | job=42 started
WARNING | job=42 fallback
```

Explanation:

1. `Files.createTempDirectory` creates an isolated directory so it does not touch existing log files; `application.log` is a fixed name inside that temporary directory.
2. `logger.setLevel(Level.FINE)` allows the logger to accept `FINE`, but `file.setLevel(Level.INFO)` causes the handler to drop the `FINE` event. This illustrates that **logger and handler thresholds are two separate steps**.
3. `formatMessage(record)` replaces the JUL `{0}` placeholder with `42`; the formatter produces one `LEVEL | message` line per record and does not add a machine-dependent timestamp.
4. `removeHandler(file)` detaches the handler from the logger; `file.close()` flushes/closes the stream and releases the lock. That allows us to read the file afterward.
5. `Files.readAllLines(..., UTF_8)` reads the exact two lines written; the loop prints them to the console so the example does not depend on paths or timestamps in the output.
6. `Files.deleteIfExists` cleans up the demo file and directory. `FileHandler` normally cleans up its lock file on close; if file or permission errors occur, the program may throw an exception. This is an instructional example, not a production log management configuration for a service.

**Do not** create a new handler in a loop for every message in a real application. Typically, loggers are declared per class, handlers are configured centrally once, and they are closed during lifecycle shutdown. When running in containers or ephemeral environments, consider using console logging plus a collector rather than relying entirely on local files.

## 8. Configuring FileHandler with logging.properties

In a plain JUL application, you can configure the handler using a `logging.properties` file. The example below uses the user's home directory (via `%h`) to avoid requiring a subdirectory that has not been created yet:

```properties
# Root logger: accept INFO and above.
.level=INFO

# Write via FileHandler (ConsoleHandler can also be added if desired).
handlers=java.util.logging.FileHandler

# Filename pattern; %u avoids contention, %g is for rotation.
java.util.logging.FileHandler.pattern=%h/myapp-%u.%g.log

# 1 MiB/file, three generations, append on open.
java.util.logging.FileHandler.limit=1048576
java.util.logging.FileHandler.count=3
java.util.logging.FileHandler.append=true

# Handler accepts INFO and above, text format, and UTF-8.
java.util.logging.FileHandler.level=INFO
java.util.logging.FileHandler.formatter=java.util.logging.SimpleFormatter
java.util.logging.FileHandler.encoding=UTF-8
```

You can specify the configuration file for the JVM when starting an existing class:

```bash
java -Djava.util.logging.config.file=logging.properties com.example.Main
```

The command above **is illustrative**, assuming `com.example.Main` is already compiled and on the classpath. It is not meant to run `FileHandlerDemo` from section 7 because that demo creates and configures the handler in code.

When using configuration files, note:

- The JVM must read the right configuration file from the start; if the application or a framework later reconfigures JUL, the result may differ.
- `.level` controls the root logger, while `FileHandler.level` controls the handler itself. A child logger can set a different level.
- The pattern, home directory write permissions, size limit, append mode, and the effect of `%g`/`%u` must all be verified in the deployment environment.
- `SimpleFormatter` produces plain text output; it does not automatically convert logs into structured JSON.
- If the app uses SLF4J/Logback as its backend, this `logging.properties` file **does not automatically manage Logback's file appender**. Check the actual logging backend to avoid misconfiguration.
- Attaching `FileHandler` both via the root logger and manually to a logger with `useParentHandlers=true` can cause events to reach multiple handlers; if they target the same destination or use similar formatters, duplicate logs will appear.

## 9. Deployment Considerations

### Log files in containers

Containers can be replaced, so files in the local filesystem are not a reliable durable store for log history. If your organization uses a collector that reads stdout/stderr, logging to the console can be simpler and more appropriate. If you genuinely need `FileHandler`, you must clearly design volumes, write permissions, rotation, and the log collection pipeline—especially when multiple replicas run concurrently.

### Multiple JVMs or multiple instances

Do not force multiple processes to write to the same file path without a coordination plan. `FileHandler` uses locking and uniqueness mechanisms, but it does not turn a single file into a shared log with guaranteed ordering across machines. A pattern with `%u` helps reduce local collisions; in distributed systems, instance/pod metadata is typically attached and logs are shipped to a centralized collector.

### Disk or permission errors

There are two distinct types of errors:

- **Errors opening/creating the file** when initializing `FileHandler`: can throw `IOException` or related errors. Choose a clear startup policy—for example, fail startup if file logging is mandatory, or fall back to console logging if permitted.
- **Write errors at runtime** (out of disk space, permission changes, filesystem errors): some errors in a handler may be reported via `ErrorManager`; do not assume every `logger.info(...)` call will throw an exception for business code to catch. Monitor pipeline health and disk usage.

Applications that require a reliable audit trail or zero log loss must have a dedicated durable storage/write design. A standard `FileHandler` does not guarantee that every logged record cannot be lost after a crash or power failure.

### Retention and sensitive data

Size-based rotation does not answer how long files should be kept. Organizations still need a retention policy, cleanup of old logs, backups if required, read/write permissions, and sensitive data controls. Do not log passwords, tokens, session cookies, or unnecessary personal payloads, even when files reside only on internal machines.

## 10. Common Errors When Using FileHandler

| Symptom | Possible Cause | How to Check and Fix |
| --- | --- | --- |
| No file is created | Handler not attached to logger, wrong path, parent directory does not exist, or no write permission. | Verify `addHandler`/`handlers`, absolute path, file creation permissions; catch errors from the constructor. |
| File exists but is empty | Logger or handler is filtering out the level, filter blocks it, not flushed/closed yet, or reading the wrong file. | Check `Logger.getLevel()`/effective level, `Handler.getLevel()`, filters, pattern, and actual filename. |
| File contains XML instead of expected text lines | `FileHandler` is using `XMLFormatter` or another configured formatter. | Select `SimpleFormatter` or an appropriate formatter and re-check the file. |
| Old contents are erased on startup | Opened with `append=false` or replaced due to rotation. | Review the append mode, pattern, and `count`/`limit` settings before changing. |
| Multiple files with unexpected suffixes | Generation/uniqueness suffixes or filename contention. | Check `%g`, `%u`, number of handlers/processes, and lock files. |
| One event appears multiple times | Handlers attached at multiple logger levels with parent propagation; or configured on both root and child logger. | Check `useParentHandlers`, attached handlers, and sinks. |
| File grows too large | `limit=0`, no proper rotation, or excessive log volume. | Configure size limit and generation count; manage retention and disk space. |
| Missing cause/stack trace | Formatter only prints `message`, or code only passes `ex.getMessage()`. | Pass `Throwable` via the proper API and check the formatter/pipeline. |
| Non-ASCII/Vietnamese characters are garbled | Write encoding and read encoding differ. | Configure UTF-8 and ensure the collector/reader uses the same charset. |
| Some logs lost at shutdown | Handler not flushed/closed, process killed abruptly, or other async logging in the pipeline. | Close the handler properly in the lifecycle; understand durability limits. |
| Two applications contend for the same file | Sharing a local pattern without proper locking/uniqueness handling. | Use per-instance directories/files or a centralized collector; do not force a single shared file. |

## 11. Pre-Production Checklist

1. **Purpose:** Do you actually need to log to a file, or is console + collector a better fit?
2. **Path:** Is the pattern clear, does the directory exist, are write permissions granted, and are filenames free of sensitive data?
3. **Scale:** Are the byte limit, generation count, and retention strategy sufficient for real traffic?
4. **Open mode:** Do `append` and restart behavior match expectations, especially with pre-existing files?
5. **Configuration:** Have logger and handler thresholds, filters, propagation, formatter, and charset been verified?
6. **Exceptions:** Is `Throwable` attached to the record, and does the formatter output the cause/stack trace when needed?
7. **Lifecycle:** Is the handler reused, closed on shutdown, and never recreated per request?
8. **Operations:** Are disk usage, write errors, and I/O impact on processing threads monitored?
9. **Security:** Have access permissions, backup/deletion, data masking, retention policies, and container filesystems been accounted for?
10. **QA:** Have restarts, rotation, multiple concurrent instances, write-permission failures, and actual output been tested in a production-like environment?

**Key takeaway:** `FileHandler` is responsible for **writing `LogRecord` instances to files, managing filenames, and handling rotation**; `Logger` and `Handler` together decide which records are accepted; and `Formatter` decides what information is written. Proper configuration must consider lifecycle, capacity, and operational conditions rather than just calling `new FileHandler(...)`.
