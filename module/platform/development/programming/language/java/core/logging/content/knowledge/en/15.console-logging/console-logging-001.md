# Logging to stdout in Java Core Logging

## 1. What is stdout and why use it for logging?

Every typical Java process has three **standard streams** provided by the runtime environment:

| Stream | Java Name | Typical Purpose |
| --- | --- | --- |
| **Standard input** | `System.in` | Receives input data, if the program uses it |
| **Standard output (stdout)** | `System.out` | Outputs results or information that the process intends to publish |
| **Standard error (stderr)** | `System.err` | Outputs diagnostics, warnings, and errors per CLI convention |

**Logging to stdout** means that logging data is written to the **standard output stream of the process**, rather than defaulting to a file or stderr. In a terminal, stdout and stderr usually appear in the same window, so **seeing a log line on the screen does not prove it is stdout**.

Example:

```java
System.out.println("RESULT order_id=ORD-101");
System.err.println("DIAGNOSTIC gateway unavailable");
```

These are **two illustrative statements**, not a complete Java program. The first writes to stdout, and the second writes to stderr. The operating system, shell, container runtime, or process manager can **redirect** each stream to a file or collector independently of the Java code.

When logging to stdout, we still need to distinguish between:

1. **Log event**: level, message, logger name, exception, correlation ID.
2. **Formatter/Layout/Encoder**: how the event is represented as a text string or JSON.
3. **Handler/Appender**: where and how the string/bytes are written—here, stdout.
4. **Collection path**: terminal, Docker/Kubernetes, systemd, CI, or a log collector that receives data after the process writes it.

**Writing to stdout does not mean logs are durably stored or have reached a dashboard.** It only defines an output point of the process. Collection, indexing, access control, rotation, and retention belong to the downstream infrastructure.

## 2. Actual Flow from Java to the Logging System

```text
Java Application
    |
    +-- logger.info("event=...")
    |          |
    |          v
    |    Logger / LogEvent
    |          |
    |          v
    |    Level / Filter
    |          |
    |          v
    |    Formatter / Layout
    |          |
    |          v
    |    Console Handler/Appender -> stdout
    |                                  |
    +-- System.out.println(...) -------+
                                       |
                                       v
                              OS standard output
                                       |
                      +----------------+---------------+
                      |                |               |
                      v                v               v
                   Terminal       Redirect file    Container runtime
                                                        |
                                                        v
                                                  Log agent/collector
                                                        |
                                                        v
                                                Search / retention
```

Key point: **stdout is not the final "log storage destination" in every architecture**. When running directly on a host, stdout may appear in the terminal or be redirected by the shell into a file. When running in a container, the runtime may capture stdout and forward it to a logging driver/agent. When running in CI, the job runner typically captures output to display and store according to policy.

Therefore, a "console stdout logging" configuration only solves **application output**. To achieve observability, you must inspect the entire collection pipeline—especially storage location, retention period, filters, and access permissions.

## 3. How does stdout differ from stderr?

In the Java API, both `System.out` and `System.err` are `java.io.PrintStream`. They are two separate streams; where each stream is connected depends on how the process is launched.

| Aspect | stdout | stderr |
| --- | --- | --- |
| Default JDK API | `System.out` | `System.err` |
| Command-line convention | Output/results meant for machines or users | Diagnostics, error messages |
| POSIX shell redirection | `> file` or `1> file` | `2> file` |
| Must ERROR-level logs go here? | **No**: INFO, WARN, and ERROR can all be written here if the appender targets stdout | **No**: not all errors have to be written to stderr |
| Impact when terminal displays both together | Easy to confuse stdout with stderr | Easy to confuse stderr with stdout |

**Level is different from stream.** `ERROR` is a LogEvent level. `stdout` is an I/O destination. If a Console Appender is configured with `SYSTEM_OUT`, both `INFO` and `ERROR` can go to stdout. A higher level does not automatically switch output to stderr unless the backend configuration has a level-based routing mechanism.

For a **CLI that uses stdout to return data meant to be parsed by another tool**, good practice is usually to keep **stdout clean** for data/results and write diagnostics to stderr, or store logs in another channel. For example, a CLI that returns JSON to stdout while also logging text to stdout could produce:

```text
INFO Started processing
{"orderId":"ORD-101","status":"OK"}
```

That output is **no longer a single valid JSON document** for the tool reading stdout. Thus, whether "logging to stdout" is appropriate depends on **the process contract**:

- A background/container service with a log collector reading stdout: usually appropriate.
- A CLI returning machine-readable data over a pipe: must separate logs from result stdout.
- An educational program run in a terminal: can use stdout for simple observation.

## 4. The Most Direct Way: `System.out.println`

Java allows printing to stdout without a logging library:

```java
public final class PrintlnDemo {
    private PrintlnDemo() {
    }

    public static void main(String[] args) {
        System.out.println("event=application_started");
        System.out.println("event=order_created order_id=ORD-101");
    }
}
```

Save as `PrintlnDemo.java` and run:

```bash
javac -encoding UTF-8 PrintlnDemo.java
java PrintlnDemo
```

**Exact stdout:**

```text
event=application_started
event=order_created order_id=ORD-101
```

**Application stderr:** no lines under normal execution conditions.

### Why is `println` not enough for serious logging?

`System.out.println` only writes a string and a newline. It does **not automatically** provide the features typically needed from a logging system:

- Filtering by level: `DEBUG`, `INFO`, `WARN`, `ERROR`.
- Logger name, timestamp, thread, and correlation ID via shared configuration.
- Event structure and parameter formatting via a logging API.
- Consistent Throwable/cause/stack trace support.
- Appenders/Handlers, filters, formatters, routing, and multi-destination policies.
- Controlling verbosity through configuration without editing every statement in code.

`println` remains suitable for **program result output** and small demonstrations. However, for operational events, use a logger from JUL, SLF4J with a provider, Logback, or Log4j2; choose stdout **at the output destination configuration layer**, rather than replacing every call with `System.out.println`.

Do not treat `System.out.println` as an automatic way to write "structured logs." If the output is just a `key=value` string, the collector may still need to parse it; true JSON also requires proper escaping and schema.

## 5. java.util.logging (JUL): An Important Pitfall About stdout

**The JDK's `java.util.logging.ConsoleHandler` writes to `System.err` by default, not `System.out`.** The name `ConsoleHandler` refers to the console, not specifically stdout. This is a common reason learners assume a program "logged to stdout" simply because logs appeared in the terminal.

JUL example:

```java
import java.util.logging.ConsoleHandler;
import java.util.logging.Level;
import java.util.logging.Logger;

public final class JulConsoleDemo {
    private JulConsoleDemo() {
    }

    public static void main(String[] args) {
        Logger log = Logger.getLogger("example.jul");
        log.setUseParentHandlers(false);
        log.setLevel(Level.INFO);

        ConsoleHandler console = new ConsoleHandler();
        console.setLevel(Level.INFO);
        log.addHandler(console);

        try {
            log.info("event=application_started");
        } finally {
            log.removeHandler(console);
            console.close();
        }
    }
}
```

Save `JulConsoleDemo.java`, compile, and run with JDK 17+:

```bash
javac -encoding UTF-8 JulConsoleDemo.java
java JulConsoleDemo
```

The line `event=application_started` is **sent to stderr by `ConsoleHandler`**. The default formatter may include a timestamp, class/method name, and log level, so a fixed full-line string cannot be assumed. The program does not actively write anything to stdout.

You can verify this by running in a POSIX shell:

```bash
java JulConsoleDemo > stdout.log 2> stderr.log
```

Expected result: `stdout.log` is empty; `stderr.log` contains the JUL record. `System.err` does not mean it is only used for `SEVERE` level: `ConsoleHandler` can send `INFO` to stderr as well.

**There is no standard configuration on `ConsoleHandler` to simply switch its destination from stderr to stdout via a `setTarget` call.** If you want to use JUL and write to stdout, use another `Handler` targeting `System.out`, such as `StreamHandler`, or a custom handler with proper lifecycle management.

## 6. Complete Java 17+ Example: JUL Writing Properly to stdout

`java.util.logging.StreamHandler` supports initialization with an arbitrary `OutputStream`. This lets us set `System.out` as a handler's destination. However, **StreamHandler is buffered** and its `close()` **closes the provided OutputStream**, so the example flushes explicitly and **does not close `System.out`**.

Save the following full code as **`StdoutLoggingDemo.java`**:

```java
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;
import java.util.logging.StreamHandler;

public final class StdoutLoggingDemo {
    private static final Logger LOG =
            Logger.getLogger(StdoutLoggingDemo.class.getName());

    private StdoutLoggingDemo() {
    }

    public static void main(String[] args) throws Exception {
        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.INFO);

        Formatter formatter = new Formatter() {
            @Override
            public String format(LogRecord record) {
                return record.getLevel().getName() + " "
                        + formatMessage(record)
                        + System.lineSeparator();
            }
        };

        StreamHandler stdout =
                new StreamHandler(System.out, formatter);
        stdout.setLevel(Level.INFO);
        stdout.setEncoding("UTF-8");
        LOG.addHandler(stdout);

        try {
            LOG.log(Level.INFO,
                    "event=order_created order_id={0}", "ORD-101");
            LOG.log(Level.WARNING,
                    "event=payment_retry order_id={0} attempt={1}",
                    new Object[] {"ORD-101", 2});

            stdout.flush();
        } finally {
            LOG.removeHandler(stdout);
            stdout.flush();
            // Do not call stdout.close(): StreamHandler will close System.out.
        }
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac -encoding UTF-8 StdoutLoggingDemo.java
java StdoutLoggingDemo
```

**Exact stdout:**

```text
INFO event=order_created order_id=ORD-101
WARNING event=payment_retry order_id=ORD-101 attempt=2
```

**Application stderr:** no records under normal execution conditions. The program does not call `System.err` and does not attach a `ConsoleHandler`.

### Why does this example actually write to stdout?

1. `new StreamHandler(System.out, formatter)` binds the handler to standard output. This is the decisive difference compared to `new ConsoleHandler()`.
2. `LOG.setUseParentHandlers(false)` prevents a `LogRecord` from propagating to parent handlers, avoiding unintended duplicates on stderr.
3. Both the logger and handler are at the `INFO` threshold; `INFO` and `WARNING` are accepted.
4. `formatMessage(record)` formats JUL parameters using `{0}`, `{1}`. This is JUL/`MessageFormat` syntax, **not `{}` from SLF4J or Log4j2**.
5. The formatter produces a stable single line per event without printing timestamps or stack traces because the demo code does not request them.
6. `stdout.flush()` pushes `StreamHandler`'s buffered data out to `System.out` for immediate observation. Do not infer that flushing means logs are durably saved to disk or received by a collector.
7. After the example, the handler is **removed from the logger** and flushed. `StreamHandler.close()` is not called because the constructor received a **process-wide shared stream**.

### Lifecycle Notes

Since this example is a short-lived program, it uses a simple approach: **remove the handler and flush, leaving stdout owned by the process**. In a long-running service, logging management must design a lifecycle for handlers and configure them once at startup. If you want a handler that can be safely `close`d without closing stdout, use a non-closing `OutputStream` wrapper or a custom handler with an appropriate close policy.

Do not add `StreamHandler(System.out, ...)` on every request: each attachment increases the number of handlers and can produce duplicate logs. Do not close `System.out` yourself in a shared library, because other parts of the application may still use that stream.

This is a JUL example that **actually runs with JDK 17 alone**, requiring no Maven, SLF4J, or Log4j2.

## 7. Verifying by Redirecting stdout and stderr

The surest way to know which stream a log uses is to **separate stdout and stderr in the runtime environment**.

### Linux/macOS Shell

```bash
javac -encoding UTF-8 StdoutLoggingDemo.java

java StdoutLoggingDemo > stdout.log 2> stderr.log
cat stdout.log
cat stderr.log
```

With the program from section 6:

- `stdout.log` has **the exact two lines** shown above.
- `stderr.log` is empty if there are no JVM or environment warnings/errors.
- The output from `cat stdout.log` is printed to the stdout of the **`cat` command**, not a second Java execution.

Some common shell patterns:

| Command | Meaning |
| --- | --- |
| `java StdoutLoggingDemo > app.log` | Redirects only the Java process's stdout to `app.log` |
| `java StdoutLoggingDemo 2> errors.log` | Redirects only stderr to `errors.log` |
| `java StdoutLoggingDemo > app.log 2> errors.log` | Separates the two streams |
| `java StdoutLoggingDemo > combined.log 2>&1` | Redirects stdout to a file, then redirects stderr to the same destination |
| `java StdoutLoggingDemo 2>&1 | tee combined.log` | Combines both streams into a pipe and displays/saves via `tee` |
| `java StdoutLoggingDemo > /dev/null` | Discards stdout output in POSIX environments |
| `java StdoutLoggingDemo 2> /dev/null` | Discards stderr output in POSIX environments |

**Redirection order matters.** `> combined.log 2>&1` differs from `2>&1 > combined.log` in terms of where stderr ultimately ends up. The `|` symbol creates a pipe, and the shell/OS determines how streams are combined.

### Windows

In **PowerShell** and **Command Prompt**, redirection syntax has similarities, but pipeline semantics, encoding, and how error streams are routed can differ. For basic verification with a pure Java program on Windows, you can use:

```powershell
java StdoutLoggingDemo 1> stdout.log 2> stderr.log
Get-Content stdout.log
Get-Content stderr.log
```

Do not assume every PowerShell version saves bytes with the same encoding or that every Java error is a PowerShell error record. For logs containing Vietnamese characters, check the encoding across the entire path from Java to the terminal/file/collector.

### The "missing logs" mistake even when the program runs

If you only run `java App > app.log` and the application uses the **default JUL `ConsoleHandler`**, logs may still appear in the terminal because they are on **stderr** and do not go into `app.log`. This is a very common verification mistake.

## 8. Log4j2: Configuring ConsoleAppender to stdout

In **Apache Log4j 2**, `ConsoleAppender` supports choosing `SYSTEM_OUT` or `SYSTEM_ERR` as its target. The typical default target of `ConsoleAppender` is **`SYSTEM_OUT`**, but you should configure it **explicitly** for clarity and to reduce confusion.

Example `src/main/resources/log4j2.xml` file:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<Configuration status="WARN">
    <Appenders>
        <Console name="STDOUT" target="SYSTEM_OUT">
            <PatternLayout charset="UTF-8"
                    pattern="%p %c{1} - %m%n"/>
        </Console>
    </Appenders>
    <Loggers>
        <Root level="INFO">
            <AppenderRef ref="STDOUT"/>
        </Root>
    </Loggers>
</Configuration>
```

This is a **complete Log4j2 configuration file**, but compiling a program that uses Log4j2 also requires compatible versions of the `log4j-api` and `log4j-core` libraries. You cannot use `javac` with the JDK alone to run Log4j2 code.

Illustrative code in a class that already has the dependency:

```java
import org.apache.logging.log4j.LogManager;
import org.apache.logging.log4j.Logger;

public final class OrderService {
    private static final Logger LOG =
            LogManager.getLogger(OrderService.class);

    public void create(String orderId) {
        LOG.info("event=order_created order_id={}", orderId);
    }
}
```

The class above **compiles against the Log4j API** but has no `main` method, so it does not produce output when run directly. If `create("ORD-101")` is called with the configuration file above, the output line looks like:

```text
INFO OrderService - event=order_created order_id=ORD-101
```

That is an **illustrative message based on the configuration**, not the stdout of a complete `main` program in this section.

### Notable `ConsoleAppender` attributes

- `target="SYSTEM_OUT"`: writes to standard output.
- `target="SYSTEM_ERR"`: writes to standard error.
- `PatternLayout`: defines level, logger name, message, and newline. It **does not determine** the I/O destination.
- `immediateFlush`: when enabled, the appender flushes more frequently; does not guarantee that a collector has persisted the log.
- `follow="true"`: follows the current `System.out`/`System.err` reference when code reassigns standard streams at runtime; unlike the default behavior which uses the stream at configuration time.
- `direct="true"`: uses the standard file descriptor directly in certain configurations, which can improve performance, but interactions with other components writing to standard streams must be evaluated.
- `follow` and `direct` must not be used together according to the configuration documentation; do not enable both arbitrarily.

When a program calls `System.setOut(...)` at runtime, a previously configured appender **does not necessarily follow** the new standard output unless the appropriate mode is selected. Do not reassign standard streams just to "fix" logging when you can configure the right destination from the start.

### What if you want ERROR on stderr and INFO on stdout?

This is a **level-based routing requirement**, not just a `PatternLayout` attribute. You can use two `ConsoleAppender`s (one `SYSTEM_OUT`, one `SYSTEM_ERR`) and appropriate filters/routing to prevent an `ERROR` from being written to both places. Do not confuse `ERROR` (level) with stderr (stream); if only a stdout appender is attached to root, every accepted level can go to stdout.

## 9. SLF4J is an API; stdout depends on the provider

When code uses SLF4J:

```java
private static final org.slf4j.Logger LOG =
        org.slf4j.LoggerFactory.getLogger(OrderService.class);

LOG.info("event=order_created order_id={}", orderId);
```

this statement **does not decide stdout or stderr**. SLF4J is a facade. The **provider/backend**—such as Logback, `slf4j-simple`, or an adapter to JUL—determines where the record is emitted. Two applications running the same SLF4J code can write to two different streams because they have different providers at runtime.

### With Logback

Logback has a `ConsoleAppender` whose `target` accepts `System.out` or `System.err`. In a Logback configuration, such as `logback.xml`:

```xml
<configuration>
    <appender name="STDOUT"
              class="ch.qos.logback.core.ConsoleAppender">
        <target>System.out</target>
        <encoder>
            <charset>UTF-8</charset>
            <pattern>%level %logger{0} - %msg%n</pattern>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="STDOUT"/>
    </root>
</configuration>
```

This is a **Logback configuration file**, not `log4j2.xml`. It only takes effect when the application actually selects the Logback provider (e.g., `logback-classic` compatible with the SLF4J API). `System.out` in Logback **is not written as Log4j2's `SYSTEM_OUT`**; the two systems have their own syntax.

`%msg` gets the message, `%level` gets the level, `%n` adds a newline; `%logger{0}` formats the shortened logger name according to Logback's converter. Output and other fields also depend on the template and backend version.

### With `slf4j-simple`

`slf4j-simple` **writes to `System.err` by default**. If you want to switch it to stdout, you can configure the JVM property:

```bash
java -Dorg.slf4j.simpleLogger.logFile=System.out -cp "app-and-dependencies/*" example.Main
```

This is an **illustrative command**. `example.Main` and `app-and-dependencies/*` are placeholder names/paths; replace them with your actual application and a classpath containing compatible `slf4j-api` and `slf4j-simple`. The property only takes effect when the runtime selects **SimpleLogger** as the implementation; it does not switch the destination of Logback or Log4j2.

You can set it in a `simplelogger.properties` file on the classpath:

```properties
org.slf4j.simpleLogger.logFile=System.out
org.slf4j.simpleLogger.defaultLogLevel=info
```

With this configuration, an SLF4J `LOG.info(...)` call can output to stdout; the format also includes components determined by SimpleLogger. Do not add multiple SLF4J providers just to try switching stderr to stdout.

### Quick Comparison Table

| Java Logging System | How to route to stdout | Default to remember |
| --- | --- | --- |
| `System.out.println` | Calls `System.out` directly | Is stdout, but not a leveled logging system |
| JUL `ConsoleHandler` | **Cannot** change target directly; use `StreamHandler(System.out, formatter)` or a custom handler | `ConsoleHandler` → **stderr** |
| Log4j2 `ConsoleAppender` | `target="SYSTEM_OUT"` | `ConsoleAppender` typically defaults to stdout |
| Logback `ConsoleAppender` | `<target>System.out</target>` | Typically defaults to stdout |
| SLF4J + `slf4j-simple` | `org.slf4j.simpleLogger.logFile=System.out` | Defaults to **stderr** |
| SLF4J + another provider | Configure the corresponding backend | Do not infer destination from the SLF4J API |

## 10. stdout in Docker and Kubernetes

A common reason to log to stdout is that the application runs in a **container**. Instead of having the application manage sets of log files inside the container, many architectures let the runtime capture the **process's stdout/stderr** and hand them off to a logging driver, agent, or monitoring service.

```text
Java service / Logger
          |
          v
    Console Appender
          |
          v
  PID's stdout / stderr
          |
          v
    Container runtime
          |
          v
 Log driver / node agent
          |
          v
  Collector / index / dashboard
```

Operational benefits:

- Eliminates the need for each application to configure separate file paths in the container's ephemeral filesystem.
- Standardizes the collection path across multiple services if the platform already has an agent.
- Makes it easy to attach metadata such as namespace, workload, pod, container, or instance at the **collection layer**, if the pipeline is configured.
- Simplifies changing the log storage destination without modifying every logging call in Java code.

**However, there are no automatic guarantees:** the container runtime may rotate or cap logs; pods may be deleted, collectors may lose connectivity, filtering/sampling may drop events, and retention may be short. `kubectl logs` helps view logs based on the workload's actual state and availability, **not as a default long-term archive**.

### Docker Example

When a container runs an application configured to log to stdout:

```bash
docker logs my-java-service
```

This command can display **both stdout and stderr** depending on the Docker logging driver/runtime. Therefore, seeing a record with `docker logs` **is not enough to prove it was emitted on stdout**. To distinguish them, check the appender configuration and the collection system's stream-tagging capabilities.

### Kubernetes Example

```bash
kubectl logs my-pod -c my-container
```

This command is only a syntax illustration: you must use actual pod/container names and the appropriate cluster context. Many logging solutions leverage container log data to attach metadata; simply writing to stdout does not automatically mean fields like `trace_id` or `service` will exist in the record.

**Design recommendation:** a containerized application should have a single console logging strategy managed in the logging framework configuration, keep messages consistent, and verify that the infrastructure actually receives and retains them as required. Do not accidentally enable multiple sources (console plus a file read by an agent) that cause the collector to ingest the same event twice.

## 11. Structured stdout Lines: JSON Lines

For centralized logging systems, using one JSON event per line (**JSON Lines/NDJSON**) is often more useful than free-form text strings if the collector supports it.

Illustrative **single event** example:

```json
{"timestamp":"2026-11-09T12:00:00Z","level":"INFO","service":"checkout","event":"order_created","order_id":"ORD-101","correlation_id":"req-7"}
```

This is **illustrative JSON**, not the default output of JUL, Log4j2, or Logback without an encoder/layout. With JSON, the collector can parse fields such as `level` and `order_id` without guessing positions in a sentence.

When outputting JSON to stdout, keep in mind:

1. **One JSON object per event on a single line** if the collector expects NDJSON. Multi-line pretty-printed JSON can be split into multiple records by the collector.
2. **Properly escape dynamic data**: double quotes, backslashes, newlines, and control characters. Do not build JSON by arbitrary string concatenation.
3. **Stable field names**: `event`, `reason_code`, `correlation_id`, `duration_ms` with consistent semantics, types, and units.
4. **Timestamps with explicit time zones**: many systems use UTC ISO 8601; avoid timezone-less timestamps when logging from multiple hosts.
5. **Throwable/stack trace**: the backend/encoder must be configured to preserve exception details as a string or structured field without breaking line framing.
6. **Do not log secrets**: valid JSON can still contain data that should not be stored. Log collectors may distribute logs to many people and systems.
7. **Control log volume**: stdout is easy to capture, but ingestion, indexing, and retention still carry costs.

With Log4j2, you can look into `JsonTemplateLayout` (requires the `log4j-layout-template-json` artifact); with Logback, you can use a JSON encoder appropriate for your version/backend. When using SLF4J 2.x, `addKeyValue` only attaches data to the event: **the provider/encoder decides whether those fields are included in the JSON**.

## 12. Writing Multiple Log Levels to the Same stdout

The stdout destination and log levels are two **independent** concerns. You can send all enabled levels to the same stdout:

```text
INFO event=application_started
WARN event=cache_unavailable action=use_database
ERROR event=order_save_failed
```

This is illustrative output, not the program run in section 6.

Some organizations want **INFO/DEBUG on stdout** and **WARN/ERROR on stderr** so the shell or operations tooling can separate the two groups. This requires **two appenders/handlers with appropriate filters**. If you simply attach two appenders without filters, an `ERROR` event may be emitted on both streams, causing duplicate logs.

You should also avoid sending all exceptions to stderr via `System.err.println(e)` if the application already has a logger managing levels and formatters. Doing so can lose logger name, correlation ID, and event formatting, and leaves stack traces inconsistently managed.

Practical rules:

- Choose the level based on **business and operational impact**, not the stdout/stderr destination.
- Choose the stream based on the **CLI contract** or **log collection infrastructure**.
- When multiple appenders coexist, check filters, additivity, and the final record count.
- If stdout carries machine-readable data, avoid mixing logs into it regardless of level.

## 13. Buffering, Flushing, and Reliability

Writing to stdout involves multiple buffering layers depending on the API and environment. A logger call may:

1. Create a LogEvent/LogRecord.
2. Be converted into text/bytes by a Handler/Appender.
3. Sit in a formatter/stream/appender buffer or an async queue.
4. Go out to the process's stdout.
5. Be collected by the runtime/agent.
6. Be stored by a parser/collector in a queryable system.

**No single step confirms that the next step has completed.**

### `println` vs. `StreamHandler.flush()`

`System.out.println` requests printing a string and typically flushes according to the `PrintStream` configuration created by the JVM. In the `StreamHandler` example, a `LogRecord` may remain in the buffer until `flush` is called. That is why the example explicitly flushes before exiting.

**Do not arbitrarily call `StreamHandler.close()` when it owns `System.out`.** Per the Java 17 API, `StreamHandler.close()` closes the target stream. By contrast, JUL `ConsoleHandler.close()` is designed to only flush and **not close `System.err`**.

### Async logging

With asynchronous appenders/handlers, a `LOG.info` call typically places the event into a queue and returns; another thread formats and sends it later. If the application exits too quickly or crashes, events in the queue may not have been emitted yet. You must shut down the logging framework properly in the application lifecycle and understand buffer/queue limits under high load.

### stdout is not a durable storage mechanism

Even after flushing, stdout may be a pipe to another process, a runtime-managed file descriptor, or a terminal. If the collector backs up, the pipe can exert **backpressure**, slowing down or blocking log-writing threads. If the collector drops overly long records or hits storage limits, an event on stdout may still never appear on a dashboard.

For data that must be persisted (audits, transactions), do not rely solely on stdout logs. You need durable business data stores and dedicated audit mechanisms.

## 14. Security Considerations When Logging to stdout

Do not treat stdout as a private channel just because it is "only inside a container." Infrastructure may collect it centrally, replicate it, and grant read access to many people.

Recommended practices:

- **Minimize data**: do not include passwords, tokens, API keys, OTPs, card numbers, or full sensitive payloads in messages.
- **Encode/escape for the format**: for text lines, prevent CRLF injection; for JSON, use a JSON encoder that handles escaping properly.
- **Control length**: a message containing very large input data can increase costs or be split into multiple parts by the collector.
- **Attach correlation IDs safely**: correlation IDs aid tracing, but are not a reason to put PII or secrets into MDC/ThreadContext.
- **Access control**: restrict who can read application logs, CI consoles, and centralized archives.
- **Retention and deletion**: know the retention period, where data is replicated, and how data subject to deletion is handled.
- **Do not use message text as the official transaction source**: logs can be duplicated, lost, sampled, or delayed.

Especially with CLIs, a parent script or process can accidentally capture a child program's stdout and put all of it into a ticket or build artifact. Printing secrets to stdout can expose data in places nobody thinks of as a "logging system."

## 15. Troubleshooting Common Issues

| Symptom | Likely Cause to Check |
| --- | --- |
| Logs appear in terminal, but `> output.log` captures nothing | Logs are on stderr, typically JUL `ConsoleHandler` or default `slf4j-simple` |
| `DEBUG` does not appear on stdout | Logger/backend threshold or appender/handler filter is dropping DEBUG |
| `ERROR` lines appear on stdout | Console Appender is configured to output to stdout; level does not decide the stream |
| Duplicate identical log lines | Parent logger/handler, additivity, or two appenders attached to the same stdout |
| JUL `StreamHandler` called, but output arrives late | `flush` has not been called, or buffering is in effect |
| After closing a handler, `System.out.println` produces no output | `StreamHandler.close()` may have been called, accidentally closing `System.out` |
| Console logging does not show up on the dashboard | Collector is not capturing stdout, parser error, filter/sampling, or retention |
| `docker logs` shows lines, but streams cannot be distinguished | `docker logs` can display both stdout and stderr; rely on configuration and metadata |
| JSON fails to parse | Text logs and JSON mixed on the same stdout, or wrong encoder/framing |
| Logs contain forged lines from user input | Missing newline/CRLF escaping for untrusted data |
| Vietnamese characters are garbled | Encoding across handler/layout, terminal, and collector is inconsistent |
| Logs disappear when container restarts | Runtime/collector/retention/rotation does not guarantee durable storage |
| CLI output fails JSON parsing | Logging messages were mixed into stdout meant for machine-readable results |
| Under high load, the program slows down due to logging | stdout I/O, locks, buffers, collector backpressure, or too many events |

### A Logical Diagnostic Order

1. Verify whether the program **actually called the logger** and whether the level is enabled.
2. Identify which **provider/backend** or JUL implementation is actually running.
3. Locate the **target Handler/Appender**: `System.out`, `System.err`, file, or socket.
4. Check whether the **formatter/layout/encoder** is producing a readable/parseable record.
5. Separate stdout and stderr with redirection to see which stream the logs are on.
6. If in a container, confirm the runtime/agent collected and tagged the source properly.
7. If bytes reached stdout but the dashboard is missing them, check the collector/parser/filter/retention.
8. For duplicates, check additivity/parent handlers and multiple collection sources.

This traces the path from emitter to receiver; do not just switch to `System.out.println` or raise log levels to "fix" every missing-log issue.

## 16. Choices by Environment

| Environment | Typical Sensible Use of stdout |
| --- | --- |
| Terminal-based Java exercises | `System.out.println` for observing results; JUL `StreamHandler` when levels and formatters are needed |
| CLI outputting data for another program | Keep stdout for data; send diagnostics to stderr or another log channel |
| Java service in Docker/Kubernetes | Console Appender to stdout per platform policy, paired with a monitored collector |
| Desktop application | Console may not be visible to users; consider files or an appropriate diagnostic mechanism |
| Service run by systemd/process manager | stdout/stderr may be captured by the process manager; check its specific configuration and retention |
| Batch job in CI | stdout is typically recorded by CI; control secrets, log volume, and line length |
| Service with strict audit requirements | stdout for observability, plus an appropriate durable audit mechanism if required |

A service that uses per-class loggers can switch from files to stdout **solely via backend configuration**, without modifying every `LOG.info(...)` call. This is a major benefit of separating loggers, formatters, and handlers/appenders.

## 17. Self-Check Questions

1. **Where does `System.out.println` write?** The process's standard output.
2. **Where does `System.err.println` write?** The process's standard error.
3. **Does JUL `ConsoleHandler` default to stdout or stderr?** **Stderr**.
4. **How do you use JUL with stdout?** For example, `new StreamHandler(System.out, formatter)`, managing flushing and lifecycle properly.
5. **Should you call `StreamHandler.close()` when passing `System.out`?** Not arbitrarily; this API closes the output stream. Avoid closing shared stdout.
6. **Must `ERROR` go to stderr?** No. Log level and target stream are two independent settings.
7. **How do you configure a Log4j2 ConsoleAppender for stdout?** `target="SYSTEM_OUT"`.
8. **How do you configure a Logback ConsoleAppender for stdout?** `<target>System.out</target>`.
9. **Where does `slf4j-simple` write by default?** `System.err`; it can be changed with the property `org.slf4j.simpleLogger.logFile=System.out`.
10. **Why should a CLI outputting JSON not log text to stdout?** Because stdout will mix logs and data, causing JSON parsers to fail.
11. **Why does seeing a line in `docker logs` not confirm stdout?** The runtime can display both stdout and stderr.
12. **Does `flush` prove that the collector has durably saved the log?** No. It only pushes data out of the relevant buffers on the sender side.
13. **Why must `%n` or a newline be included when outputting text logs?** To separate events by line for readers and collectors.
14. **Is a JSON object on stdout always indexed into fields?** No. The collector must be configured to parse JSON and retain the fields.
15. **What happens if an application attaches two handlers that both output to stdout?** One `LogRecord` can produce two identical copies.
16. **Are stdout logs in Kubernetes automatically saved permanently?** No. You must account for the runtime, log rotation, collector, retention, and access permissions.
17. **Can you write to both stdout and a file?** Yes, using multiple appenders/handlers; you must control duplicates in the pipeline.
18. **Should stdout logs be used as the sole source confirming a financial transaction succeeded?** No; rely on a durable business state store.

## 18. References

- Oracle Java 17, `ConsoleHandler`: https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/ConsoleHandler.html
- Oracle Java 17, `StreamHandler`: https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/StreamHandler.html
- Apache Log4j 2, Console Appender: https://logging.apache.org/log4j/2.x/manual/appenders.html
- Logback, ConsoleAppender: https://logback.qos.ch/manual/appenders-console-file.html
- SLF4J SimpleLogger: https://www.slf4j.org/apidocs-2.0.17/org/slf4j/simple/SimpleLogger.html

**Takeaway:** **stdout is a process I/O destination, not a log level or log format**. In Java, `System.out.println` prints directly, JUL `ConsoleHandler` defaults to stderr while `StreamHandler(System.out, formatter)` can go to stdout; Log4j2 and Logback select stdout via `ConsoleAppender`, and SLF4J requires configuring the provider. Always verify by separating streams, manage buffering/lifecycle, protect sensitive data, and inspect the entire pipeline from stdout to storage.
