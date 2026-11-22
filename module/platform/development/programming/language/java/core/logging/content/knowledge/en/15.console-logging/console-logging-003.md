# Console in Development — Using Logging Effectively When Developing Java

## 1. Why Is the Console Important During Development?

When programming Java on a local machine, the **IDE** console or **terminal** is usually the first place you observe your program's behavior. A well-timed log message helps answer key questions: which execution path ran, how input data was validated, at which step a request failed, how many times the program retried, and what the exact exception was.

**Console logging** is the practice of sending logging events to a process's standard output streams—typically **standard output (stdout)** or **standard error (stderr)**—instead of requiring file writes or network transmission. During **development**, console logging is especially useful because it is fast, easy to inspect, easy to filter, and closely aligned with the edit code → run → observe → edit feedback loop.

After this lesson, you will be able to:

- Distinguish between **System.out**, **System.err**, and **java.util.logging.ConsoleHandler**.
- Understand the Logger → LogRecord → Handler → Formatter flow and why DEBUG/FINE logs sometimes do not appear on the console.
- Use **Java Util Logging (JUL)** to produce clear console logs on Java 17+, managing levels and Formatters.
- Compile and run standalone examples, accurately reading output from stdout/stderr.
- Configure the console using **logging.properties** instead of repeatedly modifying code.
- Organize log observation in IntelliJ IDEA, Eclipse, VS Code, and terminals without depending on a specific IDE.
- Apply best practices for event names, request IDs, levels, exceptions, formatting, encoding, and filtering while debugging.
- Avoid duplicate logs, application slowdowns, leaking sensitive data, or mistaking development console output for durable audit storage.

**Scope:** This lesson belongs to the **Console logging** section of **Java Core Logging**. The main examples use **JUL built into the JDK**, requiring no Maven or external libraries. Log4j2/SLF4J are mentioned to clarify how to inspect and configure the console in projects using other backends.

## 2. What Console Logging Is and Is Not

At the operating system level, a program typically has three standard streams:

| Stream | Role | Java Equivalent |
| --- | --- | --- |
| **stdin** | Process input data | System.in |
| **stdout** | Normal program output | System.out |
| **stderr** | Error messages or diagnostic information by convention | System.err |

IDE consoles typically display stdout and stderr in the same pane, sometimes with different colors. Terminals also usually display both on screen. **That does not mean the two streams are the same channel.** They can be redirected to separate files, merged by the IDE, or collected differently by a container or log collector.

Minimal Java example:

~~~java
public class StandardStreamsDemo {
    public static void main(String[] args) {
        System.out.println("stdout: application ready");
        System.err.println("stderr: diagnostic example");
    }
}
~~~

Compile and run:

~~~bash
javac --release 17 StandardStreamsDemo.java
java StandardStreamsDemo
~~~

When displayed in a typical terminal, you will usually see two lines. However, the interleaved order between **stdout** and **stderr** is not a strict ordering guarantee when the two streams are buffered or collected independently.

**System.out.println** and **System.err.println** are direct output operations. They do not automatically add severity, Logger name, timestamp, context, Filter mechanisms, or logging framework routing. Therefore, while useful in small exercises, they **do not replace** a logging architecture for multi-module applications.

### 2.1. Console Logging with a Logging API

A common logging flow:

~~~text
Java business code
    |
    v
Logger (level, logger name, optional filter)
    |
    v
LogRecord (severity, event, metadata, exception)
    |
    v
Console Handler / Console Appender
    |
    v
Formatter / Layout
    |
    v
System.err or System.out
    |
    v
IDE console / terminal / log collector
~~~

**Terminology varies across backends:** JUL uses **ConsoleHandler**, Log4j2 uses **Console Appender**, and Logback uses **ConsoleAppender**. They share the same idea of "writing to the console," but their APIs and configurations differ. Do not copy JUL classes or configurations directly into Log4j2.

## 3. Choosing stdout or stderr in Development

There is no mandatory Java rule stating that every INFO must go to stdout and every ERROR must go to stderr. Which stream a log uses depends on the **Handler/Appender and its configuration**, not necessarily on the level of each individual line.

### 3.1. Common Conventions

- **stdout:** normal output or the log stream collected by the system under a unified policy.
- **stderr:** errors, warnings, or a diagnostic channel routed separately if the application or tooling chooses to do so.
- **JUL ConsoleHandler:** **writes to System.err by default**, even when the event is INFO.
- **Log4j2 Console Appender:** can choose **SYSTEM_OUT** or **SYSTEM_ERR** via its target configuration.

Therefore, when using **JUL ConsoleHandler**, calls to **logger.info(...)** also write to stderr. **Do not assume that "stderr means every record is an ERROR."** Severity is carried in the LogRecord's content or the level field of a structured event.

| Behavior | What It Means |
| --- | --- |
| System.out.println("hello") | Writes text directly to stdout; no level |
| System.err.println("hello") | Writes text directly to stderr; does not automatically assign ERROR |
| JUL Logger.info(...) + ConsoleHandler | May write an INFO record to stderr |
| Log4j2 INFO + Console target SYSTEM_OUT | May write an INFO record to stdout |
| Log4j2 ERROR + Console target SYSTEM_OUT | Can still write ERROR to stdout depending on configuration |

### 3.2. Why Do Logs Appear "Out of Order" in an IDE?

When an IDE merges stdout and stderr into a single pane, the display order may differ from the actual call order. Several causes:
- The two streams have separate buffering and flush schedules.
- The IDE reads output through separate threads.
- The program is multi-threaded, with multiple Loggers emitting events concurrently.
- The framework processes logs asynchronously or routes them through a queue.
- Test runners, Maven, Gradle, or containers interleave their own tool output into the same console.

If you need to prove business execution order, record **event name**, **timestamp**, **requestId**, and related metadata; do not treat the relative position of two stdout/stderr lines in an IDE window as definitive proof of causality.

## 4. Java Util Logging and ConsoleHandler

**java.util.logging.ConsoleHandler** is a built-in Handler in the JDK. According to the Java 17 API:

- It extends **StreamHandler**.
- It writes records to **System.err**.
- Its default Formatter is **SimpleFormatter**.
- The default level of **ConsoleHandler** is **INFO**, unless configured otherwise.
- It supports the configuration properties **level**, **filter**, **formatter**, and **encoding**.
- **close()** flushes but does not close the global **System.err**.

This is why when you only write:

~~~java
import java.util.logging.Logger;

Logger logger = Logger.getLogger("demo.service");
logger.fine("cache detail");
logger.info("service started");
~~~

you cannot assume FINE will appear: the Logger has its own effective level, and each Handler also has its own level. The two lines above are an illustrative snippet inside a method, not a complete class with `main()`.

### 4.1. Both Logger and Handler Have Thresholds

In JUL, for a record to be written through a Handler, it typically must:

1. Be accepted by the Logger according to its effective level and Logger Filter.
2. Be forwarded to that Handler (attached directly or via parent handlers).
3. Pass the Handler's level and filter.
4. Be processed by the Handler and Formatter while the stream is still available.

Assuming no additional Filters:

| Logger level | ConsoleHandler level | INFO | FINE | WARNING |
| --- | --- | --- | --- | --- |
| INFO | INFO | Yes | No | Yes |
| FINE | INFO | Yes | No | Yes |
| FINE | FINE | Yes | Yes | Yes |
| ALL | WARNING | No | No | Yes |
| OFF | ALL | No | No | No |

"Yes" in the table means **eligible to pass the level threshold**, not a guarantee of durable output. If the ConsoleHandler is not attached, is rejected by a Filter, or stderr is redirected elsewhere, the observed result will differ.

**Practical check:** Called **logger.setLevel(Level.FINE)** but still don't see FINE? Check **ConsoleHandler.getLevel()** and any Filters before raising levels globally.

### 4.2. Parent Loggers and Duplicate Log Lines

A Logger can forward records to its parent's Handlers. If you attach a ConsoleHandler to a child Logger while keeping **useParentHandlers=true**, a record may be processed by both the child's Handler and the root Handler. Result: a single line appears twice, possibly with different formats.

If you intentionally build a custom pipeline in an exercise, you can use:

~~~java
logger.setUseParentHandlers(false);
logger.addHandler(consoleHandler);
~~~

This is an illustrative snippet inside a method where both variables are already initialized. **Only disable parent handlers when another Handler is already attached.** If you disable forwarding without attaching a Handler to the Logger, events may have no output destination.

## 5. Standalone Java 17 Example: Separating stdout and stderr

This example demonstrates four things:

1. **System.out.println** writes to stdout.
2. **JUL ConsoleHandler** writes to stderr, even at the INFO level.
3. **Logger at FINE but Handler at INFO** causes a FINE event to be dropped.
4. Changing the Handler to **FINE** makes diagnostic records appear immediately without recreating the Logger.

The program uses **only the JDK**, with no external dependencies. A simple Formatter is written inline so the output is easy to verify and does not depend on timestamps or default formatting styles.

Create **DevConsoleLoggingDemo.java**:

~~~java
import java.util.logging.ConsoleHandler;
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class DevConsoleLoggingDemo {
    public static void main(String[] args) {
        Logger logger = Logger.getLogger("demo.checkout");
        logger.setUseParentHandlers(false);
        logger.setLevel(Level.FINE);

        ConsoleHandler console = new ConsoleHandler();
        console.setLevel(Level.INFO);
        console.setFormatter(new Formatter() {
            @Override
            public String format(LogRecord record) {
                String result = record.getLevel().getName() + "|"
                        + record.getLoggerName() + "|" + formatMessage(record);
                if (record.getThrown() != null) {
                    result += "|error=" + record.getThrown().getClass().getSimpleName();
                }
                return result + System.lineSeparator();
            }
        });
        logger.addHandler(console);
        try {
            System.out.println("stdout|application booted");
            logger.fine("event=checkout.validation_detail");
            logger.log(Level.INFO, "event=checkout.started cartId={0}", "CART-42");
            logger.log(Level.WARNING, "event=checkout.coupon_rejected",
                    new IllegalArgumentException("coupon expired"));

            console.setLevel(Level.FINE);
            logger.fine("event=checkout.diagnostic_enabled");
        } finally {
            logger.removeHandler(console);
            console.flush();
            console.close();
        }
    }
}
~~~

### 5.1. Compile and Run

~~~bash
javac --release 17 -encoding UTF-8 DevConsoleLoggingDemo.java
java DevConsoleLoggingDemo
~~~

When running in a typical terminal, you will see the following four lines, though **the relative order between stdout and stderr may vary** if the streams are collected independently.

**Verified stdout:**

~~~text
stdout|application booted
~~~

**Verified stderr:**

~~~text
INFO|demo.checkout|event=checkout.started cartId=CART-42
WARNING|demo.checkout|event=checkout.coupon_rejected|error=IllegalArgumentException
FINE|demo.checkout|event=checkout.diagnostic_enabled
~~~

During verification, the program was compiled and run successfully with **javac --release 17**; output was captured **separately** from stdout and stderr to avoid conflating the two streams.

### 5.2. Step-by-Step Walkthrough

**Step 1 — Configure the Logger.** The Logger named **demo.checkout** is set to the FINE threshold. **setUseParentHandlers(false)** prevents forwarding to the root Handler, avoiding duplicate output or extra formatting.

**Step 2 — Create the ConsoleHandler.** The Handler is set to level INFO, so it only accepts INFO records and above. The Formatter produces lines of the form **LEVEL|logger|message**, using **formatMessage(record)** to apply JUL parameters with MessageFormat syntax **{0}**.

**Step 3 — Print to stdout.** **System.out.println("stdout|application booted")** bypasses the Logger, has no level, and carries no correlation fields. It is simply a direct output message.

**Step 4 — Emit the first FINE event.** **logger.fine("event=checkout.validation_detail")** passes the Logger threshold, but the Handler is at INFO, so no corresponding line appears on stderr.

**Step 5 — Emit INFO and WARNING.** For INFO, the Formatter substitutes **{0}** with **CART-42**. WARNING includes a Throwable, so the Formatter appends **error=IllegalArgumentException**.

**Step 6 — Lower the Handler threshold.** **console.setLevel(Level.FINE)** allows **event=checkout.diagnostic_enabled** to be written to stderr. This demonstrates the independent roles of the Logger and Handler.

**Step 7 — Clean up resources.** Afterward, the code detaches the Handler, flushes, and closes it. Closing ConsoleHandler does not close the global System.err. In a server application, do not close shared Handlers on every request; Handler lifecycle belongs to the application or logging backend.

### 5.3. Intentional Limitations of the Demo

This Formatter only prints the **Throwable's class name**, not the full stack trace. This was chosen to keep stdout/stderr **exact and easy to compare** in the lesson. In real-world troubleshooting, you usually need the exception cause and stack trace; use SimpleFormatter or a Formatter/Layout that supports them, and ensure sensitive data is controlled.

The demo creates the Handler programmatically; in a larger application, configure it via a framework or properties file so you do not have to modify business code every time you change levels. The custom Formatter in this example is not a production JSON encoder and does not fully handle log injection.

## 6. Redirecting and Inspecting Both Streams in the Terminal

Using redirection lets you know for certain **which lines belong to stdout and which belong to stderr**.

### 6.1. Linux/macOS Shell

~~~bash
java DevConsoleLoggingDemo 1> app.stdout 2> app.stderr
~~~

- **1>** redirects the stdout file descriptor.
- **2>** redirects the stderr file descriptor.
- After running, **app.stdout** contains **stdout|application booted**.
- **app.stderr** contains the three INFO/WARNING/FINE lines from ConsoleHandler.

To combine both streams into a single file (though without guaranteeing exact chronological order across sources), use:

~~~bash
java DevConsoleLoggingDemo > combined.log 2>&1
~~~

To view and save at the same time in Bash, use:

~~~bash
java DevConsoleLoggingDemo 2>&1 | tee combined.log
~~~

**Caution:** Redirecting both streams into a single output does not give them a strict total ordering. With multiple threads or buffering, you must rely on event timestamps and IDs to infer execution sequence.

### 6.2. Windows PowerShell

Example of redirecting streams to two files:

~~~powershell
java DevConsoleLoggingDemo 1> app.stdout 2> app.stderr
~~~

PowerShell has its own handling for native commands and error streams; different PowerShell versions or console encodings can cause the redirected stderr representation to differ from the raw bytes. If you are investigating encoding issues or need to preserve exact byte output, test on the exact PowerShell version in use or use a tool/process API that captures each stream separately.

You can inspect the files with:

~~~powershell
Get-Content .\app.stdout
Get-Content .\app.stderr
~~~

**Windows cmd.exe**, PowerShell, and Bash differ in quoting, escaping, and redirection semantics. Do not copy syntax verbatim from one shell to another without verifying it.

### 6.3. Searching Logs with grep, findstr, or Select-String

**Linux/macOS**:

~~~bash
grep 'event=checkout' app.stderr
grep 'WARNING' app.stderr
~~~

**PowerShell**:

~~~powershell
Select-String -Path .\app.stderr -Pattern 'event=checkout'
Select-String -Path .\app.stderr -Pattern 'WARNING'
~~~

**Benefit of event keys:** If every checkout start uses **event=checkout.started**, human-readable wording can evolve while your search queries still have a stable identifier. If you only grep natural-language sentences, rewording or localization can break your queries.

## 7. Configuring the Console with logging.properties

In a JUL project, changing levels or Formatters via a configuration file is easier to maintain than calling **logger.setLevel** in multiple places.

Example **logging.properties**:

~~~properties
# Root Logger
.level = INFO

# Output through JUL ConsoleHandler
handlers = java.util.logging.ConsoleHandler
java.util.logging.ConsoleHandler.level = INFO
java.util.logging.ConsoleHandler.formatter = java.util.logging.SimpleFormatter
java.util.logging.ConsoleHandler.encoding = UTF-8

# Enable deeper diagnostics for one package
com.example.checkout.level = FINE

# Format: level|logger|message|optional throwable
java.util.logging.SimpleFormatter.format = %4$s|%3$s|%5$s%6$s%n
~~~

When starting a compiled application:

~~~bash
java -Djava.util.logging.config.file=logging.properties -cp out com.example.Main
~~~

This command **illustrates** how to specify a configuration file. It assumes **com.example.Main** already exists in the `out` directory. It is **not the command to run the Section 5 demo**, because that demo creates its Handler and Formatter programmatically.

**Key points to note:**
- **.level=INFO** sets the root Logger to INFO.
- **ConsoleHandler.level=INFO** prevents FINE from appearing on the console even though the **com.example.checkout** Logger is set to FINE.
- To output FINE logs from checkout, set **java.util.logging.ConsoleHandler.level=FINE** in the configuration.
- **ConsoleHandler.encoding=UTF-8** sets the encoding at the Handler; the terminal, IDE, or collector still needs to decode it properly.
- **SimpleFormatter.format** uses **java.util.Formatter** syntax. Per the JDK documentation, **%3$s** is the Logger name, **%4$s** is the level, **%5$s** is the message, and **%6$s** is the exception/stack trace if present.
- Specify the file via the system property **at JVM startup**. Editing the file on disk does not cause JUL to automatically reload it into a running application.

### 7.1. A Misleading FINE Configuration

~~~properties
com.example.checkout.level = FINE
java.util.logging.ConsoleHandler.level = INFO
~~~

Looking at the first line, you might expect the console to print FINE; in reality, the Handler threshold drops FINE. Always check **both the Logger effective level and the Handler level**.

In JUL, a child Logger can have its own level different from root. Once a record passes the child Logger's threshold and is forwarded to parent Handlers, the root Logger's threshold is not necessarily re-checked as if it were a new log call; however, the root Handler's threshold still applies.

### 7.2. Reloading Configuration During Development

Editing the file and **restarting the application** is the simplest and most reliable approach. JUL provides **LogManager.readConfiguration** to reload config, but this operation can reset configuration and detach or close attached Handlers. When hot reloading, you must have a plan to rebuild and verify the logging pipeline; never call `readConfiguration` per request.

If you are using Spring Boot, Logback, or Log4j2, level configuration and reloading belong to the configuration system actually used by that framework/backend. Do not assume JUL's `logging.properties` always controls Logback or Log4j2.

## 8. Console Logging in the IDE

A typical development loop:

~~~text
Edit code
   |
   v
Run / Debug
   |
   v
Observe console (event, level, requestId, exception)
   |
   v
Set breakpoint / test hypothesis
   |
   v
Fix code or adjust logging level
   |
   v
Run again
~~~

In IntelliJ IDEA, Eclipse, or VS Code, the Run/Debug console is typically attached to the Java process you just launched. Presentation, filters, and tabs vary by IDE version, but several general principles always hold:

- Verify you are viewing **the right process/configuration**. Multiple Java programs or test runners may each have their own console.
- Check whether **stdout and stderr** share the same pane; IDEs may use different colors, but not every color indicates log severity.
- Observe **when logs appear** relative to a breakpoint; the debugger may pause one thread while other threads continue logging.
- If logs suddenly disappear, check **Logger/Handler levels**, Filters, the console target, and whether your updated configuration was actually loaded.
- If the console is flooded with lines, improve searchability with event keys or `requestId` rather than just increasing the console buffer size.

### 8.1. The Console Does Not Replace a Debugger

The console shows the sequence of events and failure paths; the debugger lets you inspect variables, call stacks, thread states, and method boundaries. The two tools complement each other:

| What You Need to Know | Appropriate Tool |
| --- | --- |
| Which request failed among many requests | Logs with requestId / traceId |
| Variable values at a breakpoint | Debugger |
| Order of events and retries | Log events + timestamps |
| Why a branch was taken | Debugger, tests, well-placed logs |
| Which thread an error occurred on | Log thread field + debugger thread view |
| Recurring errors over a long period | Log storage/collector or appropriate file logging |

If an issue only occurs in production, a local debugger may not be able to reproduce it. In that case, structured logs, metrics, and traces play a bigger role; development logging should establish events and fields that remain useful in other environments.

## 9. Writing Messages That Make the Console Easy to Read

A useful console log does not need to be long, but it must carry actionable information. For example:

**Poor:**

~~~text
Started
OK
Error
Something failed
Retrying...
~~~

**Better:**

~~~text
INFO event=checkout.started cartId=CART-42
WARNING event=checkout.coupon_rejected reasonCode=expired
INFO event=checkout.completed cartId=CART-42 durationMs=35
~~~

### 9.1. Event Keys and Parameters

Choose **stable event keys** such as **checkout.started**, **checkout.completed**, and **payment.retry**. Variable data belongs in parameters or structured fields.

In JUL, parameterization with **Formatter.formatMessage(LogRecord)** typically uses **MessageFormat** and placeholders **{0}**, **{1}**:

~~~java
logger.log(Level.INFO, "event=checkout.started cartId={0}", "CART-42");
~~~

This is an illustrative snippet inside a method with `logger` and imports already in place. If you use the **SLF4J/Log4j2 API**, the common parameterization syntax is **{}**, not **{0}**. Do not mix conventions or assume all backends interpret them identically.

**Parameterization keeps formatting consistent**, but Java still evaluates argument expressions before the logger call. If computing a diagnostic value is expensive, consider **logger.isLoggable(Level.FINE)** in JUL or the corresponding lazy logging mechanism in your backend.

### 9.2. Levels Must Reflect Intent

| JUL Level | Development Example |
| --- | --- |
| SEVERE | Critical task failure requiring attention |
| WARNING | Retries, fallbacks, notable invalid input |
| INFO | Component startup, key successful operations to observe |
| CONFIG | Permitted configuration details |
| FINE | Internal decisions for debugging |
| FINER, FINEST | Very granular detail; enable within a narrow scope |

Enabling **FINEST** application-wide can generate massive output and drown out important lines. When investigating a module, enable detailed logging only for that specific package, verify the Handler level, and lower the level once finished.

### 9.3. Should You Print Entire Objects?

Never assume an object's **toString()** is safe or cheap. It may expose passwords, tokens, emails, session cookies, personal data, or produce an overly large string. When debugging, select specific fields, truncate content, and avoid triggering side-effecting operations just to format a log.

**A pretty log line that leaks data or significantly alters execution timing is not a good log.**

## 10. Exceptions on the Console

When an error occurs, logging **"Something went wrong"** is rarely enough. In JUL, you can pass a Throwable using an overload:

~~~java
try {
    performCheckout();
} catch (IllegalStateException ex) {
    logger.log(Level.WARNING, "event=checkout.failed", ex);
}
~~~

This snippet assumes **performCheckout()** and **logger** already exist in the method; it is not a standalone program. If the Handler uses **SimpleFormatter**, the Throwable can be formatted with its stack trace, helping identify the call stack.

**Key considerations:**
- Choose the level based on impact; not every exception is SEVERE.
- Log the exception at **a meaningful handling boundary**, avoiding logging the same exception in the repository, service, and controller and miscounting it as multiple errors.
- Do not swallow a Throwable and lose its cause; conversely, do not expose full stack traces to end users.
- Library exception messages may contain URLs, queries, payloads, tokens, or sensitive data; sanitize or control them before sending to a sink.
- A stack trace spans multiple lines **for a single event**. When aggregating logs with grep or a collector, configure formatting/encoding properly so continuation lines are not mistaken for separate events.

The Section 5 demo intentionally prints only the **error type** so the output is exact. To view stack traces in practice, use an appropriate Formatter/Layout instead of a formatter that discards error details.

## 11. Console Logging in Projects Using Log4j2 and SLF4J

In many projects, code calls the SLF4J or Log4j API instead of JUL. **The console is still a destination**, but configuration is governed by the backend.

### 11.1. Log4j2 Console Appender Example

An illustrative XML configuration:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<Configuration>
  <Appenders>
    <Console name="DEV_CONSOLE" target="SYSTEM_OUT">
      <PatternLayout pattern="%d{HH:mm:ss.SSS} %-5level [%t] %logger{1} - %msg%n"/>
    </Console>
  </Appenders>
  <Loggers>
    <Logger name="com.example.checkout" level="DEBUG" additivity="false">
      <AppenderRef ref="DEV_CONSOLE"/>
    </Logger>
    <Root level="INFO">
      <AppenderRef ref="DEV_CONSOLE"/>
    </Root>
  </Loggers>
</Configuration>
~~~

This is a **Log4j2 configuration file**, not standalone Java code. It only takes effect when a compatible Log4j2 implementation/provider is loaded and the file is discovered. Here, the Console Appender writes to **SYSTEM_OUT**, unlike JUL ConsoleHandler's **System.err** default. The checkout LoggerConfig is set to DEBUG; **additivity="false"** prevents events handled there from also being forwarded to the Root Appender.

**Do not copy XML directly into JUL `logging.properties`**: the two systems use different APIs and configuration formats. If an application uses the SLF4J facade, check which provider/backend is active (Logback, Log4j2, or another) before changing console logging.

### 11.2. Are Log Colors Necessary?

Color-coding by severity can make development consoles faster to scan; some backends and IDEs support highlighting and ANSI colors. However:

- Not all terminals and IDEs support ANSI identically.
- ANSI escape codes can end up literally inside redirected files if styling is not disabled appropriately.
- Long-term storage or machine-readable pipelines should have a clear schema rather than relying on colors.
- Display color never replaces a log's level or fields.

You can enable colors in development after verifying compatibility; never rely on color alone to conclude that a record is an ERROR.

## 12. Console in Development vs. Production

**The console is not only for development.** In container/Kubernetes environments or certain cloud platforms, production applications often log to stdout/stderr so the runtime or log collector can gather them. The difference lies in **configuration and operational policy**, not that the console somehow becomes wrong in production.

| Aspect | Development | Production |
| --- | --- | --- |
| Purpose | Fast feedback while editing/testing | Operational observability and incident investigation |
| Typical levels | INFO, enabling DEBUG/FINE as needed | INFO/WARN/ERROR with limits; controlled debug |
| Format | Human-readable | Usually requires schema, timestamps, IDs, parseable output |
| Where viewed | IDE/terminal | Dashboards, collectors, log search |
| Storage | Can be temporary | Explicit retention, access control, and cost |
| Volume | Verbose acceptable in narrow scope | Must control throughput, sampling, and queues |
| Sensitive data | Still must be protected | Strictly enforced by policy |

**Do not rely on console scrollback as durable storage.** IDEs may cap line counts or clear output on restart; a terminal buffer is no substitute for retention. If logs must be kept, use files, a collector, or a logging platform with a clear policy.

### 12.1. Console and Containers

Containerized applications typically write to the console so an external log collector can ingest them. Illustrative path:

~~~text
Java application
   |
   +--> stdout / stderr
             |
             v
       Container runtime
             |
             v
      Log collection agent
             |
             v
      Central log backend
~~~

Do not assume that **stderr always becomes an error in the backend**. The runtime may attach stream metadata, while the true severity usually lives in the level field or event payload. Design a schema so search systems do not have to guess severity from the stream name.

## 13. Encoding and Vietnamese Text on the Console

Java `String` supports Unicode, yet output can still become garbled if the charset at any link in the chain is incompatible.

For example, the line:

~~~text
INFO event=order.created message=Đơn hàng đã được tạo
~~~

can turn into corrupted characters if the source file, JVM console encoding, terminal, IDE, or collector decodes it with the wrong charset.

**Verification steps:**
1. Save source files and catalogs in **UTF-8**.
2. When compiling Java source containing accented characters, pass **javac -encoding UTF-8** to make the source charset explicit.
3. For JUL ConsoleHandler, set **java.util.logging.ConsoleHandler.encoding=UTF-8** when appropriate; still verify that the terminal supports UTF-8.
4. For other backends, configure the charset in their encoder/appender according to their API.
5. Inspect stdout and stderr separately if only one stream displays corrupted text.
6. Do not assume font rendering glitches mean the underlying data is corrupted; the bytes may be valid while the console renders them incorrectly.

**Note:** **System.out.println** and **ConsoleHandler** are separate output paths, so configuring ConsoleHandler's encoding does not automatically control every `System.out.println` call in the application.

## 14. Security and Log Quality While Debugging

Development often tempts engineers to log the "entire request" to track down a bug. This is a risky habit:

- Never log **passwords, OTPs, access tokens, refresh tokens, session cookies, API keys, or private keys**.
- Never log full payloads containing personal data or payment details.
- Never send those secrets to DEBUG/FINE assuming "it's off in production" is enough; log levels can be changed.
- Never allow raw input containing newlines or control characters to forge fake console lines (**log injection**).
- Never let an object's **toString()** unexpectedly print secret fields.
- Enable verbose logging within a narrow scope and for a limited time; lower the threshold after investigating.
- For exceptions, be mindful that messages or stack traces may contain endpoints, queries, or tokens.

**Recommendation:** Use event codes and selected fields, such as **event=auth.login_failed reasonCode=invalid_credentials**, rather than printing usernames/passwords or raw request bodies.

### 14.1. Performance Impact

Console I/O can be slow, especially when writing thousands of lines in a loop or when an IDE/terminal is overloaded. Synchronous logging operations can increase latency and skew benchmark results.

Example to avoid on a hot path:

~~~java
for (int i = 0; i < 1_000_000; i++) {
    System.out.println("processed=" + i);
}
~~~

This is an illustrative snippet, not a standalone program. If you want to measure an algorithm's throughput, do not benchmark it while printing a million lines to the console and conclude the algorithm is slow. Log at appropriate levels, control frequency, and use dedicated metrics or benchmarks.

**Async logging** can improve throughput for some workloads, but it introduces queue limits, dropped records, backpressure, and shutdown considerations. Do not assume async is always faster or always preserves every event.

## 15. Console Logging in Unit Tests and Integration Tests

Logs are helpful when a test fails, but **you should not make console text the sole output contract of a unit test** unless the test specifically targets a formatter or handler.

Strategies:

- **Business logic tests:** assert business outcomes, state, and exceptions; use logs for diagnostics, not as a replacement for assertions like "there is an INFO line."
- **Logging policy tests:** attach a test (in-memory) Handler to verify events, levels, and parameters rather than depending on the IDE console.
- **Integration tests:** emit a sample event and confirm the sink and collector actually receive it; check for duplicates.
- **Stream tests:** if you need to verify stdout/stderr, spawn a child process and capture both streams separately as in the demo; avoid swapping **System.setOut** in a parallel test suite.
- **Encoding tests:** use Vietnamese characters, quotes, newlines, and control characters to test formatters and encoders.

Because Loggers and Handlers can be shared infrastructure within a JVM, tests that attach or remove Handlers must restore configuration so they do not affect other tests. Calling **LogManager.reset()** in every unit test can break logging for the entire test runner.

## 16. Diagnosing Common Console Issues

### 16.1. "I Enabled FINE, but Nothing Appears"

Check in order:

1. Does the Logger name match the configuration?
2. Does the Logger's effective level allow FINE? What does **logger.isLoggable(Level.FINE)** return?
3. Is **ConsoleHandler.getLevel()** still INFO?
4. Is a Filter rejecting the record?
5. Is ConsoleHandler actually attached to the Logger or an ancestor?
6. Is **useParentHandlers** preventing records from reaching the root Handler?
7. Does the application use JUL, or is the runtime actually SLF4J/Log4j2/Logback?
8. Is the open console attached to the exact process you just ran?

### 16.2. "INFO Appears on stderr—Does That Mean the App Errored?"

Not necessarily. **JUL ConsoleHandler writes to System.err by default**, even for INFO. Read the **record's Level**; do not use the stream name as a proxy for severity.

### 16.3. "One Log Appears Twice"

Check **logger.getHandlers()**, parent handlers, the root Logger, bridges, and whether the IDE/test runner reprints output. If you attached a custom Handler while the Logger still forwards to root, two destinations may write the same record.

### 16.4. "Lines Appear Out of Order"

Determine whether two separate streams are being merged by the IDE/terminal, or whether multi-threading/async processing is involved. Include timestamps and `requestId`; do not rely on color ordering in the console to infer business order.

### 16.5. "Logs Are Lost When the Program Exits"

Check Handler buffering/flushing, async queues, and shutdown lifecycle. JUL's ConsoleHandler flushes on publish, but another pipeline may buffer. When writing data that requires durability, use an appropriate storage mechanism rather than relying on a terminal buffer.

### 16.6. "Vietnamese Text Appears Completely Garbled"

Check source encoding, `javac` encoding, Handler encoding, stdout/stderr encoding, terminal/IDE charset, and the collector. Test with a fixed Vietnamese sentence to isolate the faulty link.

### 16.7. "Too Many Lines in the Console"

Lower the level of unrelated packages, filter by event key/`requestId`, remove logs from hot loops, and prioritize high-value events. Do not indiscriminately set OFF on important error events.

### 16.8. "I See the Stack Trace, but Not the Initial Log Line"

This may be caused by a multi-line Formatter, an IDE filter, truncated output, or a collector splitting lines incorrectly. Ensure exception formatting and multi-line policies are aligned, and inspect raw output before tuning parsers.

## 17. Practical Workflow for a Development Bug

Suppose checkout occasionally rejects a coupon even when the user believes the coupon is valid.

**Step 1 — Place events at key boundaries.**

~~~text
event=checkout.started cartId=CART-42
event=coupon.validating couponType=PROMO
event=checkout.coupon_rejected reasonCode=expired
~~~

Do not log the raw coupon code if it is sensitive; log a normalized `reasonCode`.

**Step 2 — Enable verbose logging only for the checkout package.** Adjust the Logger and ConsoleHandler levels if using JUL, or LoggerConfig/Appender if using another backend.

**Step 3 — Reproduce the bug with controlled test inputs.** Use a debugger to inspect expiration conditions, timezones, and business state; logs show which steps executed.

**Step 4 — Filter by event and ID.** In multi-request applications, include `requestId`/`traceId` if available to avoid mixing logs from different checkouts.

**Step 5 — Inspect exceptions.** Read the class, cause, and stack trace when needed, without exposing secrets to the console.

**Step 6 — Verify the fix.** Run passing and failing test cases, ensuring logs still convey accurate meaning. Do not replace tests with simply seeing "INFO success."

**Step 7 — Restore levels.** Reduce verbosity after the investigation so you do not clutter the console or inflate deployment costs.

This workflow leverages the console for rapid feedback while preserving clear boundaries between observability, testing, and business logic.

## 18. Checklist for Good Console Logging

A development configuration is effective when:

- The console displays **severity** and **logger/module name**.
- Important events have **stable event keys**.
- **requestId/traceId** is present when investigating concurrent requests, with context propagated and cleaned up properly.
- INFO/WARNING/SEVERE events appear at desired thresholds; DEBUG/FINE are enabled only within scope.
- You know clearly whether the backend uses **stdout or stderr**.
- Handlers/Appenders are attached properly without unintended duplicates.
- Exceptions carry sufficient context without leaking secrets.
- Unicode/Vietnamese characters are preserved accurately.
- The console is not flooded by logs inside hot loops.
- Redirection, filtering, and flush timing have been verified.
- Business tests still have independent assertions.
- A policy exists for transitioning to production with appropriate retention, access control, and collectors.

## 19. Hands-On Exercises and Self-Check Questions

### Exercise A — Distinguish stdout and stderr

Run **DevConsoleLoggingDemo.java** and redirect the streams:

~~~bash
java DevConsoleLoggingDemo 1> app.stdout 2> app.stderr
~~~

Inspect each file. Explain why the INFO-level log appears in **app.stderr** instead of `app.stdout`.

**Hint:** JUL ConsoleHandler writes to System.err by default, whereas System.out.println writes to stdout.

### Exercise B — Logger and Handler Thresholds

Keep the Logger at FINE. Change the Handler from INFO to WARNING and re-run. Then change it to FINE. Predict the number of console lines each time and explain which records are blocked at the Handler layer.

**Hint:** A WARNING Handler drops INFO/FINE; a FINE Handler accepts INFO/WARNING/FINE passed by the Logger.

### Exercise C — Customize the Formatter

Add a **thread name** or **event time** field to the Formatter. Avoid hardcoding a specific timestamp in a README since execution time changes. Verify that the Logger name, level, and message remain intact.

### Exercise D — Avoid Duplicate Output

Try removing **setUseParentHandlers(false)** when the Logger has its own Handler, then observe. The result depends on Handlers attached to root and environment configuration. Analyze why the same event can be printed multiple times.

### Exercise E — Modify logging.properties

Set root to INFO, the checkout package to FINE, and ConsoleHandler to INFO; confirm FINE is blocked. Then set ConsoleHandler to FINE and compare. Make sure the application you run actually loads that configuration file rather than overriding it with a programmatically configured Handler.

### Exercise F — Simulate Log Injection

Use input containing a newline, such as a product name with a line break. Observe the issue when concatenating it directly into a message; propose an encoder or escaping strategy so output cannot forge a new event. Use only non-sensitive test data.

### Self-Check Questions

**1. Are System.out.println and ConsoleHandler equivalent?**  
No. System.out.println writes raw text directly; ConsoleHandler receives a LogRecord with a level, Filter, and Formatter, and writes to System.err by default.

**2. Does JUL ConsoleHandler write to stdout or stderr by default?**  
**System.err**, even for INFO.

**3. Why doesn't Logger FINE + Handler INFO print FINE?**  
Because the record passes the Logger, but is dropped by the INFO Handler.

**4. Which Formatter does ConsoleHandler use by default?**  
**SimpleFormatter**, unless configured otherwise.

**5. In a properties file, which thresholds must be checked to print FINE on the console?**  
The Logger's effective level and ConsoleHandler's level, along with any Filters and forwarding paths.

**6. Should console colors be used as the official severity indicator?**  
No. Colors depend on the IDE, terminal, and encoder, whereas level is part of the event data.

**7. Why might the console display lines in a different order than when the two streams were written?**  
Because stdout and stderr have independent buffering and collection mechanisms, alongside multi-threading or async processing if present.

**8. In a test, does seeing an "INFO success" line replace an assertion?**  
No. You must assert business state and outcomes; logs are only supporting diagnostics.

**9. Should tokens be logged at the FINE level in development?**  
No. Levels can be re-enabled, and terminals or log collectors can still retain sensitive data.

**10. Is console logging still appropriate in production containers?**  
Yes, when stdout/stderr are managed by a container runtime/collector, provided there are policies for schema, retention, access control, volume, and durability.

## 20. Official Documentation

- **Oracle Java 17 — ConsoleHandler:** https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/ConsoleHandler.html
- **Oracle Java 17 — java.util.logging package:** https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/package-summary.html
- **Oracle Java 17 — SimpleFormatter:** https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/SimpleFormatter.html
- **Oracle Java 17 — LogManager:** https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/LogManager.html
- **Apache Log4j2 — Appenders and Console Appender:** https://logging.apache.org/log4j/2.x/manual/appenders.html

Refer to the documentation matching your project's **actual JDK and backend**. If the application uses SLF4J/Logback/Log4j2, Console Appender configuration must follow that backend's API rather than assuming JUL properties apply.

## 21. Key Takeaways

**The console in development is a fast-feedback tool for observing program behavior, not just System.out.println.** A logging API gives console lines consistent levels, Logger names, messages, context, and filtering policies. With JUL, **ConsoleHandler writes to System.err by default and has an INFO threshold**, so setting a Logger to FINE is not enough to see FINE logs if the Handler has not been updated.

When debugging, understand the full path **event source → Logger → Handler/Appender → Formatter → stdout/stderr → IDE/terminal**, and combine logs with a debugger, tests, event IDs, security practices, and log volume control. This separation keeps the console practical during development while laying a logging foundation that scales to larger environments.
