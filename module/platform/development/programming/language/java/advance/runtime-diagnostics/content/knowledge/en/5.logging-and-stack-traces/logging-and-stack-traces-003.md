# 5.3 java.util.logging: Logger, Handler, Formatter, and Log Level Configuration

`java.util.logging` (commonly abbreviated as **JUL**) is the built-in logging API in Java SE, belonging to the `java.logging` module. It lets a program emit event records without depending directly on the output destination: the same log call can be filtered by level, routed to the console, a file, or a custom `Handler`, and formatted appropriately for operators.

In JVM diagnostics, calling `logger.info(...)` is not enough. An investigator must be able to answer: **why didn't a FINE line appear, why was an event printed twice, why was a stack trace lost, which exact configuration is in effect, and how will raising verbosity impact the system?**

This lesson covers the `Logger → LogRecord → Handler → Formatter` data flow, the `Level` hierarchy and name-based inheritance, configuration via `logging.properties` and Java 17+ code, common pitfalls during log collection, and a controlled procedure for enabling/disabling log levels during incidents.

## 1. Processing Model of a JUL Record

A call such as:

```java
private static final java.util.logging.Logger LOG =
        java.util.logging.Logger.getLogger("com.example.checkout");

LOG.info("checkout started"); // Illustration inside a method, not a standalone file.
```

travels through multiple layers with distinct responsibilities:

```text
                         Logger "com.example.checkout"
  log(Level, message)  ─────────────┐
                                    ▼
                          Effective Logger Level
                          + Logger Filter (if any)
                                    │
                          passes → LogRecord
                                    │
                     ┌──────────────┴──────────────┐
                     ▼                             ▼
               Own Handlers              Parent Logger Handlers
                     │                    (forwarded by default)
              Handler Level                        │
              + Handler Filter               Handler Level
                     │                       + Handler Filter
                     ▼                             ▼
                 Formatter                     Formatter
                     │                             │
                     ▼                             ▼
               stdout/file/…                   stderr/file/…
```

Division of responsibilities:

| Component | Question it decides | Key point to remember |
| --- | --- | --- |
| `Logger` | Which component emitted the record, and at what level should it be created? | Has a hierarchical name; has an effective level and optionally a `Filter` |
| `Level` | Is the record important enough to pass the threshold? | A Logger's threshold is **distinct** from a Handler's threshold |
| `LogRecord` | Which timestamp, level, message, parameters, and error does the event carry? | The data object passed through the pipeline |
| `Handler` | Where is the record sent, and is it filtered further? | Each Handler has its own level and Filter |
| `Formatter` | How is the LogRecord turned into text/XML or another format? | Does not decide whether the record is created |
| `LogManager` | How are the Logger namespace and centralized config managed? | Supports properties files and runtime updates |

**Whether a log line appears is the outcome of the entire pipeline**, not just `Logger.getLevel()`. If a Logger allows `FINE` but `ConsoleHandler` is still set to `INFO`, the FINE record is not emitted by ConsoleHandler. Conversely, once a child Logger creates a LogRecord, forwarding to parent Handlers by default does not re-evaluate the parent Logger's level check.

### 1.1. What Does LogRecord Contain?

`LogRecord` captures information such as:

- `getLevel()`, `getLoggerName()`, and the raw message;
- `getInstant()`: event timestamp as an `Instant` (Java 17);
- `getParameters()`: parameters for the Formatter to format the message;
- `getThrown()`: the underlying `Throwable`, for stack trace output;
- source class/method names if supplied or inferred;
- thread identity and metadata depending on API/version.

`LogRecord` does not automatically become JSON with a trace ID. Basic JUL **does not have MDC/structured context like some other frameworks**; if you need request/trace IDs, design context propagation, formatting, and compatibility with thread pools or virtual threads separately, without assuming context automatically follows every async task.

## 2. Logger: Naming, Hierarchy, Effective Level, and Parent Handling

### 2.1. Creating a Logger and Holding a Reference

The standard convention is naming by package/class:

```java
import java.util.logging.Logger;

public final class CheckoutService {
    private static final Logger LOG =
            Logger.getLogger(CheckoutService.class.getName());

    public void process() {
        LOG.info("checkout accepted");
    }
}
```

This is a **class compilable with JDK 17+**, though without `main` it is just an application component. `Logger.getLogger(name)` retrieves or creates a Logger managed by `LogManager`. Keep a strong reference, such as a `static final` field: LogManager may only hold weak references to Loggers in the namespace, so transient `getLogger` calls are not guaranteed to point to the same object if no strong reference remains.

Dots in Logger names form a hierarchy, for example:

```text
"" (root)
└── com
    └── com.example
        └── com.example.checkout
            └── com.example.checkout.PaymentService
```

This is a **logical name tree**; the actual parent is the nearest **existing** ancestor Logger—not every intermediate node in the diagram has necessarily been instantiated. The Root Logger has the empty string `""` as its name.

### 2.2. Assigned Level vs. Effective Level

`logger.getLevel()` returns the level **set directly on the Logger**, which can be `null`. When `null`, the Logger inherits the effective level of the nearest parent with a defined level. Therefore:

- `logger.setLevel(Level.FINE)`: overrides this Logger's threshold to FINE.
- `logger.setLevel(null)`: clears its own threshold, falling back to the inherited threshold.
- `logger.isLoggable(Level.FINE)`: checks whether a FINE request passes the **Logger's effective threshold**.
- `logger.getLevel() == null` does **not** mean the Logger is disabled.

Changing a parent's level can affect children that inherit from it. A child with an explicitly set level continues using its own level.

**Diagnostic warning:** `isLoggable(Level.FINE) == true` does not guarantee the FINE line reaches a file/console. A Handler can still reject the record via its level or Filter; emission can also fail due to I/O or output configuration.

### 2.3. Logger Level and Handler Level Are Two Gates

Example:

| Logger effective level | ConsoleHandler level | Emitted event | Result at ConsoleHandler |
| --- | --- | --- | --- |
| `INFO` | `INFO` | `FINE` | Record not created at Logger threshold |
| `FINE` | `INFO` | `FINE` | Logger passes, Handler drops |
| `INFO` | `FINE` | `FINE` | Logger drops; lower handler threshold cannot help |
| `FINE` | `FINE` | `FINE` | Emitted if not blocked by a Filter |
| `WARNING` | `INFO` | `SEVERE` | Emitted |
| `OFF` | `ALL` | `SEVERE` | No log created because Logger is disabled |

This matrix applies to **one connected Handler**. A Logger can dispatch the same LogRecord to multiple Handlers; final output also depends on parent handlers, filters, I/O errors, and per-handler settings.

### 2.4. Parent Handlers and the "Log Printed Twice" Bug

By default, `logger.getUseParentHandlers()` is `true`. If a Handler is attached to Logger `com.example.checkout` while root also has a ConsoleHandler, one LogRecord may be printed by both Handlers, making it look as if the program logged twice.

```java
Logger log = Logger.getLogger("com.example.checkout");
log.setUseParentHandlers(false);
```

Setting `false` stops forwarding to the parent, **but you must attach a dedicated Handler or valid output path**; otherwise logs will vanish. If the intent is for all services to share the root ConsoleHandler, the simple approach is not attaching extra ConsoleHandlers to individual Loggers. When analyzing duplicate logs, also check whether the log collector reads both stdout and a file, uses appenders from another framework, bridges, or a pipeline delivering records multiple times.

A subtle pitfall: **parent Logger level/filter is not re-applied as an independent gate to a LogRecord already accepted by a child** along the forwarding path; what governs parent output is usually the **parent Handler** configuration. Therefore, to suppress FINE on the shared console, inspect ConsoleHandler's level, not just root `.level`.

## 3. Level Ordering and Choosing the Right Level

Standard JUL levels, ordered from highest priority to lowest:

| Level | Standard numeric value | Common usage |
| --- | ---: | --- |
| `OFF` | `Integer.MAX_VALUE` | Disables logging on the corresponding Logger/Handler |
| `SEVERE` | 1000 | Severe error preventing a function from completing |
| `WARNING` | 900 | Abnormal condition that is recoverable or needs attention |
| `INFO` | 800 | Key operational milestones, lifecycle states |
| `CONFIG` | 700 | Configuration information, depending on use case |
| `FINE` | 500 | Debug details during investigation |
| `FINER` | 400 | Deeper detail, easily generates large log volume |
| `FINEST` | 300 | Very granular tracing, enable only with strict bounds |
| `ALL` | `Integer.MIN_VALUE` | Allows all levels through the threshold (aside from other Filters) |

`Level.SEVERE` is higher than `Level.WARNING`, then `INFO`... An `INFO` threshold accepts `INFO`, `WARNING`, and `SEVERE`. A `FINE` threshold accepts everything from FINE upward. `ALL` and `OFF` are two special values; libraries can also define custom levels, so keep the numeric-value rule in mind when comparing.

**Event classification guidance:**

- `SEVERE`: transaction cannot proceed due to a serious failure; must include cause and safe context.
- `WARNING`: retry due to a transient dependency issue, unexpected configuration, yet a recovery path exists.
- `INFO`: startup/shutdown, sanitized version/port/profile, important operational outcomes.
- `CONFIG`: configuration strategy selection useful for diagnostics; must never contain secrets.
- `FINE`/`FINER`/`FINEST`: internal decisions, execution branches, bounded detailed snapshots.

Do not treat INFO as a place to print full request payloads, do not use SEVERE for every exception that succeeds on retry, and do not leave FINEST as the default on busy production systems.

## 4. Proper Logging API Usage

### 4.1. Convenience Methods and `log(...)`

```java
Logger log = Logger.getLogger("com.example.checkout");

log.severe("payment failed");
log.warning("retry scheduled");
log.info("checkout completed");
log.config("strategy selected");
log.fine("cache miss");
log.finer("validation detail");
log.finest("per-field trace");
```

This is a snippet within a method or static initializer scope, not a standalone application. Depending on the threshold, only some calls produce a LogRecord. You can use overloads taking `Level`:

```java
log.log(Level.WARNING, "attempt={0}", 2);
log.log(Level.INFO, "order={0}, status={1}",
        new Object[]{"A-12", "accepted"});
```

Messages here use `{0}`, `{1}` parameters in `java.text.MessageFormat` style when the Formatter calls `formatMessage(record)`; **not** `%s` from `String.format` or `{}` from some other logging facades. A custom Formatter that does not call `formatMessage` may leave placeholders unexpanded.

### 4.2. Logging Exceptions and Full Stack Traces

Use the overload taking `Throwable`:

```java
try {
    // Operation that may throw an error.
} catch (RuntimeException ex) {
    log.log(Level.SEVERE, "Cannot complete checkout", ex);
}
```

This is an illustrative snippet inside a method, not standalone runnable code. The `ex` argument is stored in `LogRecord.getThrown()`. Suitable standard formatters can output the stack trace; **custom Formatters must explicitly handle Throwable** to preserve the stack trace. `log.severe(ex.getMessage())` logs only a string, losing exception type, cause chain, stack frames, and context.

Avoid both logging SEVERE at a low layer and rethrowing to log the same exception again at the controller layer unless there is a specific reason; this easily causes one failure to be counted as multiple incidents.

### 4.3. Lazy Message Construction to Reduce Cost

For strings that cost CPU/RAM to build:

```java
log.fine(() -> "snapshot=" + buildExpensiveSnapshot());
```

This is a snippet assuming `buildExpensiveSnapshot()` exists. `Supplier<String>` defers string construction if the Logger rejects FINE. You can also use:

```java
if (log.isLoggable(Level.FINE)) {
    log.fine("snapshot=" + buildExpensiveSnapshot());
}
```

**Limitation:** `isLoggable` only checks the Logger's threshold, unaware of whether the final Handler will actually write it. Even with a Supplier, logging high volumes, formatting stack traces, serializing large objects, synchronous I/O, and context gathering still incur overhead. Never pass entire objects containing passwords/tokens/PII directly into `toString()` for "quick debugging".

### 4.4. Using Filter for Rules Finer Than Level

A `Filter` can be attached to a Logger or Handler:

```java
import java.util.logging.Filter;
import java.util.logging.LogRecord;

Filter onlyWarnings = new Filter() {
    @Override
    public boolean isLoggable(LogRecord record) {
        return record.getLevel().intValue()
                >= java.util.logging.Level.WARNING.intValue();
    }
};
```

This is an illustrative snippet that can go inside a method; `onlyWarnings` must be attached via `logger.setFilter(...)` or `handler.setFilter(...)` to take effect. Use a Handler Filter when you want to alter **a single sink** (e.g., a warnings file) without affecting other sinks. Do not rely on a simplistic Filter for data security; because records can carry parameters/exceptions/stack traces, redaction must be explicitly designed and tested.

## 5. Standalone Java 17+ Example: Logger + Handler + Formatter

This example intentionally uses `StreamHandler` wired to `System.out` and a custom `Formatter` to produce **deterministic stdout**, independent of the current date/time. It is a complete Java program demonstrating two-tier filtering and why `flush()` matters.

Save as **`JulFlowDemo.java`**:

```java
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;
import java.util.logging.StreamHandler;

public class JulFlowDemo {
    public static void main(String[] args) {
        Logger logger = Logger.getLogger("training.jul.flow");
        logger.setUseParentHandlers(false);
        logger.setLevel(Level.FINE);

        Formatter formatter = new Formatter() {
            @Override
            public String format(LogRecord record) {
                return record.getLevel().getName()
                        + " | " + formatMessage(record)
                        + System.lineSeparator();
            }
        };

        StreamHandler handler =
                new StreamHandler(System.out, formatter);
        handler.setLevel(Level.FINE);
        logger.addHandler(handler);

        logger.fine("cache miss");
        logger.log(Level.WARNING, "attempt={0}", 2);
        logger.finest("not emitted");

        handler.flush();
        logger.removeHandler(handler);
        // Do not close because the handler holds System.out for the demo.
    }
}
```

Compile/run in the file's directory using **JDK 17+**:

```bash
javac JulFlowDemo.java
java JulFlowDemo
```

Stdout (the content of each line is fixed; line separators depend on OS):

```text
FINE | cache miss
WARNING | attempt=2
```

Why are there only two lines?

1. Logger `training.jul.flow` has threshold `FINE`, so it accepts FINE and WARNING while dropping FINEST upfront.
2. `StreamHandler` is set to `FINE`, so it accepts both remaining `LogRecord`s. If the handler were set to `INFO`, the FINE line would be dropped by the Handler.
3. `formatter.formatMessage(record)` resolves placeholder `{0}` to produce `attempt=2`.
4. `setUseParentHandlers(false)` prevents parent/root Handlers from printing duplicates.
5. `StreamHandler` can buffer output, so the example calls `flush()` to ensure both lines are observed before the program exits. `StreamHandler.close()` closes the underlying stream; do not arbitrarily close `System.out` when the application continues using it.

**Note when bringing into an application:** do not configure Handlers on every request; initialize logging centrally once, manage Handler lifecycles, and avoid races where multiple threads mutate levels/handlers concurrently. The program above illustrates the mechanism, not a full production configuration.

## 6. External Configuration via `logging.properties`

### 6.1. How Is the Configuration File Loaded?

JUL uses a global `LogManager`. Default configuration depends on the runtime; you can specify a properties file at JVM startup:

```bash
java -Djava.util.logging.config.file=logging.properties \
     -cp . JulConfigDemo
```

`-Djava.util.logging.config.file=...` is a **JVM system property** and must be passed in the options section before the main class name. If using a relative path, verify the service's working directory matches expectations. In deployments, stable absolute paths are usually easier to audit. `java.util.logging.config.class` is an alternative mechanism to supply a configuration class; inspect actual startup flags if a specified file appears to have no effect.

Do not confuse JUL's `logging.properties` with `logback.xml`, `log4j2.xml`, or framework-specific logging properties. An application may use a facade or bridge that causes behavior different from pure JUL.

### 6.2. Small Properties Example and Corresponding Program

Create **`logging.properties`** with:

```properties
# Handler for the root logger.
handlers = java.util.logging.ConsoleHandler

# Global threshold.
.level = INFO

# Console threshold and formatter; ConsoleHandler writes to stderr.
java.util.logging.ConsoleHandler.level = FINE
java.util.logging.ConsoleHandler.formatter = java.util.logging.SimpleFormatter

# Compact format for demo, omitting timestamp.
java.util.logging.SimpleFormatter.format = %4$s: %5$s%6$s%n

# Raise verbosity only for the target logger.
training.jul.config.level = FINE
```

Save **`JulConfigDemo.java`**:

```java
import java.util.logging.Logger;

public class JulConfigDemo {
    private static final Logger LOG =
            Logger.getLogger("training.jul.config");

    public static void main(String[] args) {
        LOG.fine("cache miss");
        LOG.info("service started");
        LOG.finest("not emitted");
    }
}
```

Compile and run (Linux/macOS):

```bash
javac JulConfigDemo.java
java -Djava.util.logging.config.file=logging.properties \
     -cp . JulConfigDemo
```

In a pure JDK 17 environment with no other logging configuration overriding it, **stderr** contains:

```text
FINE: cache miss
INFO: service started
```

There is no FINEST line because the target Logger is at FINE. Both the root handler and `ConsoleHandler` must permit FINE for the detail line to appear; here `.level=INFO`, while the child has `training.jul.config.level=FINE` and the handler has `ConsoleHandler.level=FINE`. Forwarding to the root handler does not re-check the root Logger level as an independent log call.

The tokens `%4$s` and `%5$s` in `SimpleFormatter.format` select the Level and formatted message respectively; `%6$s` selects the exception representation if present; `%n` is the newline character. This is `java.util.Formatter` syntax for **record formatting**, distinct from `{0}` message arguments. In environments where the system property `java.util.logging.SimpleFormatter.format` is preset, the system property may take precedence over the config file value; inspect startup args if output differs from expectations.

### 6.3. Core Configuration Keys

| Properties key | Effect | Common mistake |
| --- | --- | --- |
| `handlers=...` | List of Handlers attached to the root Logger | Mistaking it for a list of all Loggers |
| `.level=INFO` | Root logger level | Thinking this always blocks records already emitted by a child with a lower level |
| `com.example.level=FINE` | Level for logger named `com.example` and inheritance | Using a name that doesn't match the Logger in code |
| `com.example.handlers=...` | Dedicated Handlers for the named logger | Forgetting to check `useParentHandlers`, causing duplicates |
| `com.example.useParentHandlers=false` | Do not forward records to parent Handlers | Not attaching a dedicated Handler, causing logs to disappear |
| `java.util.logging.ConsoleHandler.level=FINE` | ConsoleHandler threshold | Changing only the Logger level and still not seeing FINE |
| `java.util.logging.ConsoleHandler.formatter=...` | Selects Formatter class | Class cannot be loaded or lacks an appropriate constructor |
| `java.util.logging.SimpleFormatter.format=...` | Controls SimpleFormatter text representation | Confusing `%4$s` with message placeholder `{0}` |
| `java.util.logging.FileHandler.pattern=...` | Specifies file pattern | Setting a path without permissions or missing directory |

Handler class names must be exact and instantiable by LogManager appropriately. Every key, path, level, and handler class should be verified in the **deployed file**, not only in a local copy.

### 6.4. Why Does Updating the File Not Immediately Change a Running JVM's Logs?

JUL typically reads configuration when LogManager initializes; editing the file on disk does not automatically reload running Loggers. Changes can be made programmatically via `Logger.setLevel`/`Handler.setLevel` or an appropriate management mechanism. `LogManager.readConfiguration(...)` re-reads configuration, which can reset/recreate Handlers and alter global logging state; do not invoke it inside a request for a "quick reload" without understanding its impact on the whole application and frameworks.

The JDK also provides `LogManager.updateConfiguration(...)` for merge-based updates; exact behavior depends on the API and properties, and is not equivalent to changing a single level. In production, use established configuration mechanisms, bound the scope, and record how to revert to the previous level.

## 7. Handlers: Output Destinations and Lifecycle Management

### 7.1. Built-in Handlers

| Handler | Destination/characteristics | When useful |
| --- | --- | --- |
| `ConsoleHandler` | Writes to **`System.err`**, defaults to `SimpleFormatter` and INFO threshold | Containerized apps collecting stdout/stderr centrally |
| `FileHandler` | Writes files, supports rotation by size/count | When standalone files are needed with rotation/retention procedures |
| `StreamHandler` | Writes to `OutputStream`; requires attention to flush/close | Tests with controlled output or adapters |
| `MemoryHandler` | Buffers a number of records, pushes upon trigger threshold | Investigating cases where only a pre-error window is desired |
| `SocketHandler` | Sends records over the network in configured format | Only when cost/connectivity/transmission are controlled |
| Custom `Handler` | Custom destination, filtering/buffering | When built-ins do not meet the observability contract |

Not every Handler is asynchronous; logging calls can execute formatting and I/O on the calling thread. A slow Handler or failing I/O destination can increase latency or cause data loss. Understand buffering, flushing, error reporting, and collector limits.

### 7.2. FileHandler, Rotation, and Filenames

`FileHandler` commonly uses properties such as:

```properties
handlers = java.util.logging.FileHandler
.level = INFO

java.util.logging.FileHandler.level = INFO
java.util.logging.FileHandler.formatter = java.util.logging.SimpleFormatter
java.util.logging.FileHandler.pattern = %t/checkout-%u-%g.log
java.util.logging.FileHandler.limit = 1048576
java.util.logging.FileHandler.count = 3
java.util.logging.FileHandler.append = true
```

`%t` is the system temp directory, `%u` is a uniqueness number to resolve file conflicts, and `%g` is the generation number for rotation. The example sets an approximate limit of 1 MiB per file and rotates across 3 files; the limit is **approximate** at write time. This is an educational setup: the temp directory is not by default a durable or secure log storage location. Do not assume `count=3` is a sufficient retention policy for production.

Several important points:

- `FileHandler` may default to `XMLFormatter`; when readable text is desired, specify a text formatter explicitly.
- `append=false` risks overwriting/clearing existing file contents depending on open/rotation policy; check startup behavior.
- If multiple JVMs write to the same file or run on a network filesystem, `%u`/file locking does not guarantee conflict-free coordination across all environments.
- Check write permissions, disk quotas, OS/collector-driven rotation, container ephemeral storage, and retention periods.
- File write failures may only be reported via `ErrorManager` or stderr depending on the Handler; a missing file does not always mean the application emitted no events.

In containers, the common practice is for **each application to send appropriate logs to stdout/stderr for collector scraping**, rather than creating multiple files on an ephemeral filesystem. However, the concrete choice depends on operational infrastructure and security requirements.

### 7.3. Attaching and Removing Handlers

Operations:

```java
Logger logger = Logger.getLogger("com.example.checkout");
Handler[] ownHandlers = logger.getHandlers();

for (Handler handler : ownHandlers) {
    logger.removeHandler(handler);
    handler.flush();
    // handler.close() if this Handler is owned by the application
    // and permitted to close per appropriate lifecycle.
}
```

`getHandlers()` returns Handlers **attached directly** to this Logger, not necessarily including Handlers inherited from parents. Do not hastily close a shared Handler without knowing ownership. With a `StreamHandler` holding `System.out`, `close()` can close the output stream itself; conversely, file Handlers need to be closed to release resources at shutdown. Swapping Handlers at runtime can drop or duplicate records during transition if not properly coordinated.

## 8. Formatters and Formats Useful for Diagnostics

### 8.1. SimpleFormatter and XMLFormatter

`SimpleFormatter` produces human-readable strings. It can include timestamp, caller, level, message, and throwable; the default format should not be hardcoded as an immutable standard across all JDK configurations.

`XMLFormatter` produces an XML representation of records; structured format is useful when matching a pipeline, though not automatically optimal for modern log aggregation systems. If JSON/structured logs are desired, you need an appropriate formatter/bridge/adapter with verified escaping and schema; JUL in JDK 17 does not include a built-in JSONFormatter simply by toggling a property.

### 8.2. Timestamps Need Clear Anchor, Offset, and Timezone

In Java 17, `LogRecord.getInstant()` gives the event instant. A custom Formatter can output UTC:

```java
// Snippet inside a custom Formatter.
String timestampUtc =
        java.time.format.DateTimeFormatter.ISO_INSTANT
                .format(record.getInstant());
```

The `record` variable must be a `LogRecord` within the formatter method; this does not run standalone. If using `SimpleFormatter` with `%1$...`, date/time is formatted using the JVM's `ZoneId.systemDefault()` for the date field. Two pods with different timezones can render the same instant as different strings. Using timestamps with explicit offset/UTC alongside instance/trace IDs makes correlation with GC/JFR/traces much more accurate.

**Precision differs from accuracy:** printing nanoseconds does not guarantee node clocks are synchronized to the nanosecond. When comparing logs across multiple hosts, account for clock skew and ingestion delay, especially when inferring sub-millisecond or millisecond ordering.

### 8.3. Custom Formatters Must Handle Throwable, Escaping, and Output

If a simple text formatter like the `JulFlowDemo` example only calls `formatMessage(record)`, it will not automatically print the stack trace for `LogRecord.getThrown()`. For production, a Formatter should:

- handle `record.getThrown()`, cause chains, and stack traces per policy;
- escape newlines, delimiters, and input data to prevent log injection and parsing failures;
- record UTC timestamp, level, logger, and thread/request/trace ID when genuinely available;
- bound payload sizes and redact sensitive data without randomly truncating core error messages;
- account for time formatting and character encoding (UTF-8 if required by the pipeline);
- handle synchronization/performance matching how the Handler invokes the formatter.

With structured logging, separate metadata fields from message text so downstream tools do not have to parse strings with fragile regexes.

## 9. Observing and Changing Log Levels on a Running Process

### 9.1. Verify JUL Is Actually in Use

Before editing `logging.properties`, verify whether logs go through JUL or through SLF4J/Logback/Log4j2/container adapters. Some applications install a JUL → SLF4J bridge or another bridge; in that case, final Handlers and levels may be managed by the target framework. Never install arbitrary bidirectional bridges, as they can cause loops, duplicates, or management conflicts.

Inspect **actual launch args**, the `java.util.logging.config.file` system property (if any), config files inside the image/mounts, and deployed logging frameworks. `-Xlog:gc*` is HotSpot's **JVM Unified Logging**, independent of application JUL `Logger`s: changing JUL to `FINE` does not enable GC logs and vice versa.

### 9.2. Inspecting Configuration in Code

A diagnostic snippet can print the name, configured level, useParentHandlers, and direct Handlers:

```java
Logger log = Logger.getLogger("com.example.checkout");
System.out.println("name=" + log.getName());
System.out.println("setLevel=" + log.getLevel());
System.out.println("parent=" +
        (log.getParent() == null ? "<none>" : log.getParent().getName()));
System.out.println("toParent=" + log.getUseParentHandlers());

for (java.util.logging.Handler h : log.getHandlers()) {
    System.out.println("handler=" + h.getClass().getName()
            + " level=" + h.getLevel());
}
```

This is a **snippet placed inside a method**, not a complete file. It lists only **own** Handlers, excluding parent Handlers; `getLevel()` may be null while the effective level is still defined. If a framework/bridge replaced Handlers after startup, reading the initial `logging.properties` file alone will not reflect the full runtime state.

On Java 17, `java.lang.management.PlatformLoggingMXBean` can be used via the Java Management API to inspect or change JUL logger levels depending on permissions and connectivity. It is not an interface to edit arbitrary Handlers/filters. The older `java.util.logging.LoggingMXBean` API is deprecated; prefer the platform interface appropriate to the JDK version.

### 9.3. Safe Procedure for Raising Diagnostic Verbosity

1. **Pick a narrow Logger** by package/class related to the error, e.g., `com.example.checkout.PaymentGateway`; do not raise root for the entire JVM unnecessarily.
2. **Record baseline:** current effective level, parent chain, Handler levels, log rate/sec, latency, and disk/network budget.
3. **Identify actual destinations:** ConsoleHandler, file, framework bridge, or collector; check Handler thresholds too, not just the Logger.
4. **Raise temporarily** from INFO to FINE (only if needed), for a bounded window and with a ready rollback path.
5. **Monitor signals:** log volume surge, CPU/GC, latency, I/O, disk quota, log write errors; stop if impact is high.
6. **Collect records with context:** UTC timestamp, instance, request/trace ID, app version, error milestones.
7. **Restore and verify:** return logger/handler levels to baseline; confirm log rate and performance return to normal.
8. **Document findings:** which event distinguished hypotheses; who can view the logs; data retention limits.

Do not turn on `FINEST` cluster-wide indefinitely. If an error occurs very rarely, you can use sampling/request-ID-scoped logging as supported by the application, provided security is designed and critical evidence is not missed.

### 9.4. Impact of Reloading Configuration

Live updates via `Logger.setLevel` have narrow scope; changing `Handler.setLevel` affects every Logger sharing that Handler. `LogManager.readConfiguration` can reset and close prior Handlers, breaking programmatic configuration or disrupting output if used carelessly. `LogManager.updateConfiguration` has merge/replace semantics per API rules and must be tested with specific providers/handlers.

Do not equate "config file edited" with "JVM applied the config". When logs disappear right after a deploy, check what loads configuration, when LogManager initializes, and application startup output.

## 10. JUL Troubleshooting Matrix

| Symptom | Hypothesis to check | Evidence / verification |
| --- | --- | --- |
| `logger.fine(...)` does not appear | Logger effective level is higher than FINE | `getLevel()`, parent chain, `isLoggable(FINE)` |
| `isLoggable(FINE)` is true but no FINE line | Handler level/filter drops record; no Handler to sink | `getHandlers()`, parent Handlers, `getUseParentHandlers()`, filter/collector |
| One event appears twice | Own Handler and parent Handler both write; or collector reads 2 sources | Handler config, `useParentHandlers`, log path, and collector pipeline |
| No logs from a package | Logger name differs from property; `useParentHandlers=false` with no own Handler | Compare Logger name in code vs. file; inspect handler graph |
| Level changed with no effect | Only edited file without reload; framework bridge; high handler level | Startup arguments and runtime state, bridge, current Handler |
| INFO prints to stderr, not stdout | `ConsoleHandler` writes to `System.err` | Check stdout/stderr collector, do not assume console = stdout |
| Exception message present without stack trace | Logged `ex.getMessage()` or Formatter ignores `getThrown()` | `log(..., ex)` API overload, Formatter source/schema |
| FileHandler does not create file | Path/permissions/quota, missing directory, file locks | `pattern`, user/cwd, ErrorManager, filesystem |
| Files rename when full | Rotation via `limit/count/%g/%u` | FileHandler properties, actual file names, retention |
| Timestamps off by hours vs. JFR/GC | Formatter uses different host timezone; ingest time mistaken for event time | `LogRecord.getInstant()`, timezone, event vs. observed time |
| Slower errors after enabling FINEST | High log volume, expensive formatting, or blocking I/O | Log rate, latency, CPU/disk, Handler implementation |
| Message still has literal `{0}` | Formatter does not call `formatMessage`; record lacks parameters | How `log(...)` was called, Formatter implementation |
| Context mixed across multiple requests | Custom ThreadLocal used with async task execution | Request/trace ID propagation, context lifecycle, thread pools |
| JUL config does not control framework logs | App uses Logback/Log4j2/bridge | Verify actual logging backend/bridges, configuration owner |

**Diagnostic principle:** first verify whether the event is created at the Logger; next trace its *path to the final Handler*; finally check the Formatter, I/O, and collector. This avoids endlessly lowering levels without knowing where the record is being dropped.

## 11. Log Quality for JVM Incident Investigation

### 11.1. Recording Enough Information to Reconstruct Events

A useful incident log record typically needs:

- event timestamp with explicit offset (UTC preferred), level, logger/service, and instance;
- stable operation or event code, success/failure status;
- request/trace/span ID when available and permitted;
- sanitized object identifier, duration, and units where needed;
- exception type, cause, and stack trace on genuine failures;
- build version, deployment revision, and JVM instance/host when merging sources.

Not everything must be printed inside `message`; with a structured log schema, fields should be separated. `LogRecord` natively carries level/message/time/thrown, whereas additional application context must be programmed and tested.

### 11.2. Log Levels Do Not Replace Metrics or Tracing

- `INFO` shows lifecycle and major events, but cannot accurately measure error rates or p99.
- `FINE` reveals execution paths, yet finding CPU hotspots may require JFR/profilers and finding GC pauses may require JFR/GC logs.
- High log volume adds I/O and distorts timing; do not infer "when it happened" solely from the order the collector received records.
- To measure request rates, structured metric counters with controlled label cardinality are usually preferable to logging every request in detail.

### 11.3. Sensitive Data, Injection, and Retention

Never log plaintext passwords, API keys, access tokens, session cookies, card numbers, sensitive payloads, or all of `System.getProperties()`. For exceptions, stack traces can inadvertently expose paths/hostnames/queries/parameters: restrict log access and enforce corresponding retention policies.

User input containing newlines or delimiters can **forge another log line** when concatenated directly into plain text; Formatters/encoders must escape properly or use structured fields. Even when FINE is enabled only temporarily, data can persist for a long time in collectors and backups.

## 12. Two-Layer Level Diagnostic Practice

Starting from `JulFlowDemo`, modify step by step and predict the output:

| Change | Does the FINE line reach stdout? | Reason |
| --- | --- | --- |
| Keep Logger FINE, Handler FINE | Yes | Both thresholds allow it |
| Change Logger to INFO, keep Handler FINE | No | Logger drops before creating the FINE LogRecord |
| Change Logger to FINE, Handler to INFO | No | Handler drops after Logger creates the LogRecord |
| Change both Logger and Handler to FINEST | Yes; plus the FINEST line | Both accept FINEST |
| Call `setUseParentHandlers(true)` in the demo | May emit an extra record via parent Handler | Depends on root config; risk of duplicate output |

In a real application, if `isLoggable(FINE)` is true yet the console does not show FINE, check the Handler level **before** tweaking more Logger settings. If FINE still fails to reach the collector even when both thresholds pass, check Filters, Handler presence, stream direction, output errors, and the collector pipeline.

## 13. Common Mistakes

1. **Changing only Logger level and forgetting Handler level.** ConsoleHandler defaulting to INFO can drop FINE.
2. **Interpreting `getLevel()==null` as unconfigured.** It may mean the level is inherited from a parent.
3. **Attaching a ConsoleHandler to every class.** Easily produces duplicate logs because parent handlers remain active.
4. **Setting `useParentHandlers=false` without attaching a dedicated Handler.** Log lines vanish.
5. **Using `System.out.println` instead of structured logging.** Loses level, logger name, configuration, and routing (even though println can be handy for brief local checks).
6. **Logging exceptions using only the message.** Loses Throwable/stack trace and deeper cause.
7. **Putting expensive `String.format`/concatenation into disabled FINE calls.** Creates unnecessary overhead.
8. **Assuming `ConsoleHandler` writes to stdout.** It writes to `System.err`.
9. **Using `%s` in parameterized JUL messages expecting SLF4J-style substitution.** JUL typically uses `{0}` with `MessageFormat`.
10. **Not knowing which file actually loaded configuration.** The file in the repo may not be the file used by the JVM.
11. **Confusing JUL with JVM `-Xlog` or another logging backend.** Adjusting the wrong system has no effect.
12. **Enabling FINEST everywhere during an incident.** Can saturate I/O, bloat log cardinality, and drive up costs.
13. **Not flushing/closing Handlers properly per lifecycle.** Risks losing trailing data or leaking file descriptors.
14. **Custom Formatters dropping Throwable and timestamp.** When an incident occurs, evidence is missing.
15. **Logging sensitive data without retention bounds.** "Debug" verbosity is not an exemption from data protection policy.
16. **Forgetting to revert levels after investigation.** Log volume and risk remain elevated long-term.

## 14. Configuration Checklist Before Production or During Incidents

- [ ] Are Loggers named consistently by package/class and held with strong references?
- [ ] Are effective Logger levels, explicitly assigned levels, and inheritance clear?
- [ ] Have level + Filter of every Handler and parent handlers been checked?
- [ ] Is `useParentHandlers` set intentionally to avoid duplicate or missing logs?
- [ ] Have the `logging.properties` source, JVM `-D` flags, and actual logging backend been confirmed?
- [ ] Are destinations (`stderr`, stdout, file, or collector) clearly identified?
- [ ] Does the Formatter include proper UTC/offset timestamps, level, logger name, message, and Throwable?
- [ ] For FileHandler, are path, rotation, quota, permissions, and retention planned?
- [ ] Are secret payloads avoided, with injection/escaping and access controls handled?
- [ ] Is there a plan for enabling FINE/FINER/FINEST narrowly, with time bounds and abort thresholds?
- [ ] Is there a way to revert logger/handler levels and verify restoration?
- [ ] Are logs correlated with metrics, JFR, GC logs, or traces when analyzing root causes?

**Self-check question:** An application has Logger `com.example.checkout` set to `FINE`, root ConsoleHandler set to `INFO`, and `useParentHandlers=true`. Why does `logger.isLoggable(Level.FINE)` return `true` while FINE does not appear? What are two fixes that affect only the necessary scope? Explain the `LogRecord` path clearly, the consequence of adding a dedicated Handler, and how to avoid duplicate lines.

## References

- Oracle Java SE 17, [`java.util.logging` package](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/package-summary.html): JUL architecture and components.
- Oracle Java SE 17, [`Logger` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Logger.html): effective levels, hierarchy, parent handlers, Supplier, parameters, and Throwable.
- Oracle Java SE 17, [`Level` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Level.html): ordering, values, and OFF/ALL levels.
- Oracle Java SE 17, [`Handler` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Handler.html) and [`ConsoleHandler`](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/ConsoleHandler.html): thresholds, Filters, and `System.err`.
- Oracle Java SE 17, [`Formatter` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Formatter.html), [`SimpleFormatter`](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/SimpleFormatter.html): formatting and `formatMessage`.
- Oracle Java SE 17, [`FileHandler` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/FileHandler.html): `pattern`, `limit`, `count`, `append`, `%u`, and `%g`.
- Oracle Java SE 17, [`LogManager` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/LogManager.html): `logging.properties`, startup config, and runtime updates.
- Oracle Java SE 17, [`LogRecord` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/LogRecord.html): event data, instant, and Throwable.

A diagnostics-ready JUL setup must answer: **which Logger created the record → which thresholds and Filters it passed → which Handler received it → how the Formatter rendered it → whether the collector actually ingested it**. Once you know each step precisely, you can raise verbosity just enough to find bugs without noisy, missing, or duplicated evidence.
