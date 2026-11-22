# Console and File Logging in Java

## 1. What Are Console Logs and File Logs?

Logging is the practice of recording events during program execution to monitor state, diagnose root causes of errors, and support operations. A log event typically includes a **level**, **timestamp**, **source** (logger/class), **message**, and sometimes an **exception/stack trace**.

Two common log output destinations:

- **Console log**: writes to the process's output stream, usually `stdout` or `stderr`. Whoever runs the application sees it in the terminal; Docker, systemd, or the deployment platform can also collect these streams.
- **File log**: writes to a file on disk, such as `logs/app.0.log`, so it can be read after the terminal session ends. You need to manage the path, size, file rotation, and write permissions.

A single event can be written **simultaneously to both the console and a file**. In Java 17+, the built-in `java.util.logging` (JUL) library does this through three components:

```text
Logger (creates event, checks level)
  ├── ConsoleHandler (filters level, formats) → System.err
  └── FileHandler    (filters level, formats) → file on disk
```

`Logger` decides whether an event is emitted; each `Handler` has its own level filter and a `Formatter` to turn the event into text. Therefore, to see `FINE` in the file, both `Logger` **and** `FileHandler` must allow `FINE`.

## 2. Choosing Console vs. File

| Criterion | Console log | File log |
| --- | --- | --- |
| Output destination | Process `stdout`/`stderr` | File on the filesystem |
| Direct observation | Convenient when running from an IDE/terminal | Requires opening, searching, or reading the file |
| Retention | Depends on the terminal or log collection system | Persists according to file lifecycle and retention policy |
| Container operations | Often suitable because platforms collect standard streams | Requires persistent volumes or a forwarder if long-term retention is needed |
| Risks to manage | Logs scrolling off or being lost if not collected | Disk full, missing write permissions, oversized files, duplicate data |

Do not use `System.out.println(...)` as the primary logging mechanism for an application: that call has no level, filter, formatter, or file rotation mechanism. `System.out` is still appropriate for **business output of a command-line program**; logging should go through a logging API. Note that JUL's `ConsoleHandler` writes to **`System.err`** by default, even though a terminal screen usually displays both streams.

## 3. Java 17 Example: Writing Simultaneously to Console and File

Create `ConsoleFileLoggingDemo.java`:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.logging.ConsoleHandler;
import java.util.logging.FileHandler;
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class ConsoleFileLoggingDemo {
    private static final Logger LOG =
            Logger.getLogger(ConsoleFileLoggingDemo.class.getName());

    public static void main(String[] args) throws IOException {
        Files.createDirectories(Path.of("logs"));

        // Do not forward to parent logger handlers,
        // preventing the same event from appearing twice.
        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.ALL);

        // Short formatter so example output is easy to compare.
        Formatter format = new Formatter() {
            @Override
            public String format(LogRecord record) {
                return record.getLevel().getName() + " | "
                        + formatMessage(record) + System.lineSeparator();
            }
        };

        ConsoleHandler console = new ConsoleHandler();
        console.setLevel(Level.INFO);
        console.setFormatter(format);

        // 1 MiB/file, up to 3 generations, append content on subsequent runs.
        FileHandler file =
                new FileHandler("logs/app.%g.log", 1_048_576, 3, true);
        file.setLevel(Level.FINE);
        file.setFormatter(format);
        file.setEncoding("UTF-8");

        LOG.addHandler(console);
        LOG.addHandler(file);

        try {
            LOG.info("Application started");
            LOG.fine("Loaded application configuration");
            LOG.warning("Cache is nearly full");
        } finally {
            LOG.removeHandler(console);
            LOG.removeHandler(file);
            console.close();
            file.close();
        }
    }
}
```

Compile and run from the directory containing the file:

```bash
javac ConsoleFileLoggingDemo.java
java ConsoleFileLoggingDemo
```

**Console output (stderr stream)** when running the program:

```text
INFO | Application started
WARNING | Cache is nearly full
```

**New content written to `logs/app.0.log`** on the first run when the `logs` directory has no prior logs:

```text
INFO | Application started
FINE | Loaded application configuration
WARNING | Cache is nearly full
```

You can view the file with `cat logs/app.0.log` on Linux/macOS or `Get-Content logs/app.0.log` in PowerShell. With `append=true`, subsequent runs **append** records to the existing file; the file contents may then include previous runs. If the file reaches its limit and rotates, older records may be in another generation file. When multiple processes compete for the same file name, JUL may automatically append a unique suffix to the name.

**Explanation of each decision:**

1. `Files.createDirectories(...)` creates the target directory before opening `FileHandler`; a missing directory or lack of write permissions can cause handler initialization to fail.
2. `LOG.setLevel(Level.ALL)` lets the logger emit `FINE` as well, but `console.setLevel(Level.INFO)` only displays `INFO` and above; `file.setLevel(Level.FINE)` still accepts `FINE`.
3. `setUseParentHandlers(false)` prevents events from propagating up to the root logger and causing duplicate logs when the application attaches its own handlers as in this example.
4. `Formatter` here intentionally omits timestamps for stable, easy-to-follow output. Real applications should include time, level, logger name, context, and exception rendering.
5. Calling `close()` in `finally` flushes and releases resources, including the file lock used by `FileHandler`. For long-running applications, keep handlers alive until application shutdown instead of creating a handler for every message.

Do not call `new FileHandler(...)` per request or inside a logging loop: doing so wastes resources, creates many file locks, and can scatter logs.

## 4. Levels Determine Which Logs Reach Each Destination

Common JUL levels, from most severe to most detailed:

| Level | Typical usage |
| --- | --- |
| `SEVERE` | Serious error; the operation cannot complete |
| `WARNING` | Notable anomaly, though the program can continue |
| `INFO` | Important operational events: startup, connection, operation completion |
| `CONFIG` | Configuration information useful for diagnostics |
| `FINE`, `FINER`, `FINEST` | Increasingly detailed technical information for debugging |

`ALL` enables all levels; `OFF` disables logging. A level below the **logger's** threshold will not create an event for handlers to process. A level below a **handler's** threshold will be dropped at that destination only.

For example: logger = `ALL`, console = `INFO`, file = `FINE` means a `FINE` record appears only in the file. If you change the logger to `INFO`, the `FINE` record **appears nowhere**, even though the file handler is still set to `FINE`. Each handler can also have its own `Filter`.

When you need to log an error with its stack trace, use the overload that accepts an exception:

```java
try {
    int port = Integer.parseInt("not-a-number");
} catch (NumberFormatException ex) {
    LOG.log(Level.SEVERE, "Invalid port configuration", ex);
}
```

The snippet above illustrates logging an exception **inside the class that already declared `LOG` in the previous example**. With the custom formatter in section 3, the stack trace **is not printed yet** because that formatter only outputs the level and message. To display exceptions in a real application, use `SimpleFormatter` or a custom formatter that reads `record.getThrown()` and prints the stack trace. `LOG.log(..., ex)` itself still stores the exception in the `LogRecord`.

## 5. Configuration via logging.properties

With JUL, you can change handlers and levels using a configuration file at JVM startup instead of editing code every time. This is **a separate program, independent of the programmatic handler creation example in section 3**.

Create `ConfiguredLoggingDemo.java`:

```java
import java.util.logging.Logger;

public class ConfiguredLoggingDemo {
    private static final Logger LOG =
            Logger.getLogger(ConfiguredLoggingDemo.class.getName());

    public static void main(String[] args) {
        LOG.info("Service started");
        LOG.fine("Configuration details loaded");
        LOG.warning("Cache nearing capacity");
    }
}
```

Create `logging.properties` in the same directory:

```properties
handlers=java.util.logging.ConsoleHandler,java.util.logging.FileHandler
.level=INFO

java.util.logging.ConsoleHandler.level=INFO
java.util.logging.ConsoleHandler.formatter=java.util.logging.SimpleFormatter

java.util.logging.FileHandler.level=FINE
java.util.logging.FileHandler.pattern=logs/configured.%g.log
java.util.logging.FileHandler.limit=1048576
java.util.logging.FileHandler.count=3
java.util.logging.FileHandler.append=true
java.util.logging.FileHandler.encoding=UTF-8
java.util.logging.FileHandler.formatter=java.util.logging.SimpleFormatter

ConfiguredLoggingDemo.level=FINE
```

Before running, **create the `logs` directory** because the configured `FileHandler` is initialized while loading the logging configuration. Then run:

```bash
javac ConfiguredLoggingDemo.java
java -Djava.util.logging.config.file=logging.properties ConfiguredLoggingDemo
```

`SimpleFormatter` includes a timestamp, logger name, level, and can print stack traces by default; **do not compare the output verbatim** with the short formatter example in section 3. The logical result is still: console has `INFO` and `WARNING`; the file also has `FINE`. The configuration file path in `-Djava.util.logging.config.file` is read by the JVM when initializing the logging system; relative paths are resolved from the current working directory.

Choose **only one way to own configuration** for a running example: if you both instantiate handlers in code and declare handlers via configuration, you must understand parent loggers and record propagation to avoid duplicate logs. In projects using Spring Boot or SLF4J/Logback, actual configuration is governed by the project's logging backend; do not assume JUL configuration keys apply to Logback.

## 6. File Rotation, Formatting, and Storage Location

**Rotation** keeps a single file from growing indefinitely. With `FileHandler("logs/app.%g.log", 1_048_576, 3, true)`:

- `pattern` is the file name pattern; `%g` is the generation number, such as `app.0.log`, `app.1.log`, `app.2.log`.
- `limit` caps each file at roughly 1 MiB before rotating.
- `count=3` keeps at most three generations in this rotation scheme; older records may be overwritten as files wrap around.
- `append=true` continues writing to an existing file when possible, unlike overwriting from scratch.

JUL's `FileHandler` **rotates by size**; it does not natively provide date-based retention policies, compression of old files, or shipping logs to a centralized system. Those needs require operational tooling or an appropriate logging backend. Avoid placing log files inside source directories or committing logs to Git; use a deployment directory with write permissions and a clear retention policy.

**Formatting:** JUL's `FileHandler` often defaults to `XMLFormatter` if no formatter is configured; readers may be surprised that the file is not plain text lines. Choose `SimpleFormatter` or a formatter suited to your reading/querying needs. Timestamps should include a time zone or use a consistent format such as ISO 8601. When running across multiple threads or machines, timestamps and log order are not guaranteed to reflect exact causal relationships; add a request/correlation ID when tracing is needed.

**Console in deployment environments:** prefer sending application logs to standard streams and letting the platform collect/centralize them in containerized deployments. If writing to both console and file, decide which is the primary source of truth to avoid double collection or storing local files that are lost when a container is replaced.

## 7. Common Errors and How to Check Them

| Symptom | Possible cause | How to fix |
| --- | --- | --- |
| One event appears twice on the console | Both the current logger's handler and a parent logger's handler emit the record | Check `setUseParentHandlers(false)` or the logger/handler hierarchy configuration |
| `FINE` logs do not appear in the file | Either the logger or the file handler threshold is set to `INFO` | Check **both** levels and any filters |
| Cannot create the log file | Directory does not exist, insufficient permissions, or wrong path | Create the directory, verify the path relative to the working directory, inspect startup errors |
| File contains XML instead of text | Default `XMLFormatter` is active | Configure `SimpleFormatter` or your desired formatter |
| File contains many records from previous runs | `append=true` | This is expected behavior; check rotation and retention policies |
| Log files fill up the disk | No size/generation limit or no monitoring | Configure rotation, retention, and disk-space alerts |
| `LOG.log(..., ex)` is called but no stack trace appears | Custom formatter ignores `getThrown()` | Use a formatter that supports exceptions |
| Logs disappear when a container is replaced | Files live on the container's ephemeral filesystem | Collect `stdout`/`stderr` or configure persistent storage |

When debugging logging issues, check in order: **logger name → logger level → useParentHandlers → attached handlers → handler level/filter → formatter → path/write permissions → log collection system**. This helps distinguish filtered records, unexpected formatting, and actual write failures at the destination.

## 8. Best Practices

- Use `INFO` for important state changes, `WARNING` for anomalies, and `SEVERE` for errors; enable `FINE/FINER/FINEST` only when diagnosing issues to limit volume and noise.
- **Never log passwords, tokens, API keys, sensitive personal data**, or full requests/responses containing secrets; filter or mask sensitive data before logging.
- Log exceptions with the `Throwable` object and a formatter that supports stack traces; do not log only `ex.getMessage()` when you need to find the root cause.
- Name loggers by class/package so you can configure verbosity per area; avoid mixing `System.out.println` with the logger system.
- Define rotation, retention, access permissions, and log collection targets before deployment; monitor logging failures as well, since logs can be lost when disks fill up.
- Verify **both destinations** in practice: which events appear on the console, which appear in the file, whether the format has enough context, and whether exceptions preserve stack traces.

**Key takeaway:** Console and file are two **output destinations** for the same logging event. Combining `Logger`, levels, `Handler`, and `Formatter` lets you control what goes to each destination without duplicating log calls in your source code.
