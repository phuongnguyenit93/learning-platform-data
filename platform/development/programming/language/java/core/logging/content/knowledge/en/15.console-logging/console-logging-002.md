# Logging to stderr in Java: Proper Stream Console Logging

## 1. What is stderr?

When a Java program runs in a terminal or is started by the operating system as a process, it typically has two standard output streams:

- **stdout (standard output):** the stream intended for the program's primary output. Accessed in Java via `System.out`.
- **stderr (standard error):** the stream typically intended for error messages, warnings, and diagnostic information. Accessed in Java via `System.err`.

These two streams are **logically independent**. Both may appear in the same terminal window, but the shell, IDE, container runtime, or log collection system can route them to **two different destinations**.

On POSIX-compliant operating systems and shells, stdout is normally associated with file descriptor **1**, and stderr with file descriptor **2** (stdin is 0). Shell redirection syntax is typically based on these numbers.

```text
                    Java Application
                           │
               ┌───────────┴───────────┐
               │                       │
               ▼                       ▼
      System.out / stdout       System.err / stderr
       file descriptor 1         file descriptor 2
               │                       │
               ▼                       ▼
       Results / data          Diagnostics / warnings /
                               errors / stack traces
```

**Key point:** `stderr` is an **output destination**, not a log level. An `INFO` record can be sent to stderr; an `ERROR` record can be written by a backend to stdout, a file, or a collector. Severity level and output stream are **two separate decisions**.

### When should you use stderr?

In a **command-line program (CLI)**, a useful convention is:

- **stdout:** data or results for the user and other commands to process.
- **stderr:** errors, warnings, progress, or diagnostic information that is not part of the primary result.
- **exit code:** the exit status indicating success or failure; it cannot be replaced by merely printing the text `ERROR`.

For example, a calculation tool might print `42` to stdout, and `WARNING | Using fallback configuration` to stderr. Users can still pipe stdout to a file for processing without mixing in diagnostic messages.

In **server applications**, the stdout/stderr output policy depends on the infrastructure and logging backend. Many container platforms collect both streams; sometimes they are labeled differently, but you should not assume every environment handles the two streams identically.

## 2. How to Write Directly to stderr in Java

`System.err` is a `java.io.PrintStream` object provided by the JVM. You can call `print`, `println`, or `printf`, just like with `System.out`:

```java
System.out.println("result=42");                       // stdout
System.err.println("ERROR | Cannot open configuration"); // stderr
System.err.printf("WARNING | Retry attempt %d%n", 2);   // stderr
```

This is an **illustrative snippet**, placed inside a method (such as `main`) to run. `%n` in `printf` produces a platform-specific line separator, which is preferable to hardcoding newline characters in many cases.

Using `System.err` has the following advantages:

1. Built into the JDK, requiring no additional libraries.
2. Can be redirected and collected separately from `System.out` results.
3. Suitable for minimal CLI errors, startup messages before the logger system is initialized, or small demos.

However, `System.err.println(...)` **does not become a logging framework on its own**: it has no level filtering, logger names, timestamps, correlation IDs, rolling files, log retention, JSON encoders, or multi-destination routing mechanisms. To control those factors, use JUL, SLF4J with a backend, Logback, Log4j2, or the logging solution chosen by your application.

### stderr does not mean “the program has failed”

Despite the name *standard error*, it is completely reasonable to send **non-fatal diagnostic messages** to stderr, such as startup progress or statistics while stdout carries machine-readable data. What matters is that the **output contract** is clear and consistent.

Conversely, if a fatal error occurs, merely writing a line to stderr **does not automatically make the exit code non-zero**. The program must return an appropriate exit code or throw an exception if that is the chosen policy.

## 3. Complete Java 17 Example: stdout for Results, stderr for Diagnostics

Create the file `CliStderrDemo.java`:

```java
import java.io.PrintStream;

public final class CliStderrDemo {

    static int run(String input, PrintStream out, PrintStream err) {
        try {
            int value = Integer.parseInt(input);
            out.println(value * 2);
            err.println("INFO | Parsed integer");
            return 0;
        } catch (NumberFormatException exception) {
            // This is an expected input error: no need to print the full stack trace.
            err.println("ERROR | Input must be an integer");
            return 2;
        }
    }

    public static void main(String[] args) {
        if (args.length != 1) {
            System.err.println(
                    "ERROR | Usage: java CliStderrDemo <integer>");
            System.exit(2);
            return;
        }

        int exitCode = run(args[0], System.out, System.err);
        if (exitCode != 0) {
            System.exit(exitCode);
        }
    }
}
```

This is a **standalone program** that runs on JDK 17 or later without external libraries.

Compile:

```bash
javac CliStderrDemo.java
```

Run with a valid argument:

```bash
java CliStderrDemo 21
```

**Two lines are produced:**

```text
42
INFO | Parsed integer
```

Here, `42` belongs to **stdout**, while `INFO | Parsed integer` belongs to **stderr**. When both streams are rendered in the same terminal, **you should not rely on their merged display order** as an API guarantee: buffering, the terminal, and collection mechanisms can affect ordering between streams.

Run with invalid input:

```bash
java CliStderrDemo abc
```

The program prints no result data to stdout. It writes exactly one line to stderr:

```text
ERROR | Input must be an integer
```

In this case, the process terminates with **exit code 2**, because the code calls `System.exit(2)`. With a valid argument, `main` finishes normally, so the exit code is **0**.

### Why does the example have a run(out, err) method?

Passing `PrintStream out` and `PrintStream err` into the method instead of calling `System.out/System.err` everywhere offers a major benefit: **testability**. In unit tests, you can pass mock `PrintStream` instances that write to memory instead of mutating the JVM's two global streams. This is especially useful when an application runs multiple tests concurrently.

Input errors are handled as short messages rather than unexpected exceptions that dump a full stack trace. This keeps stderr readable and avoids flooding logs with routine user input mistakes.

## 4. Redirecting stdout and stderr in the Shell

The two streams are easiest to distinguish when routed to two separate files.

### 4.1. Bash, zsh, and compatible shells on Linux/macOS

After compiling `CliStderrDemo.java`, run:

```bash
java CliStderrDemo 21 1> success.out 2> success.err
```

**Exact** result:

**File `success.out`:**

```text
42
```

**File `success.err`:**

```text
INFO | Parsed integer
```

With invalid input:

```bash
java CliStderrDemo abc 1> failure.out 2> failure.err
```

`failure.out` is empty; `failure.err` contains:

```text
ERROR | Input must be an integer
```

Check the exit code immediately after the Java invocation using `echo $?` in Bash/zsh:

```bash
java CliStderrDemo abc 1> failure.out 2> failure.err
echo $?
```

The exit code is `2`. If another command runs in between, `$?` may reflect that intermediate command instead of Java.

Common syntax:

| Shell syntax | Meaning |
| --- | --- |
| `> output.txt` or `1> output.txt` | Redirect stdout to file (overwrite) |
| `2> error.txt` | Redirect stderr to file (overwrite) |
| `1>> output.txt` | Append stdout to file |
| `2>> error.txt` | Append stderr to file |
| `> all.log 2>&1` | Send stdout to file and point stderr to the same destination chosen for stdout |
| `2> /dev/null` | Discard stderr in POSIX shells; use intentionally |
| `1> /dev/null` | Discard stdout in POSIX shells |

**Operator order matters:** `> all.log 2>&1` combines both streams into the file; `2>&1 > all.log` can leave stderr pointing to stdout's destination **before** stdout is redirected to the file. Do not swap the order without understanding exactly which descriptor it references.

Even when both streams point to the same file, the order of lines from the two streams **does not always reflect the exact order of Java calls**, especially when buffering or multiple threads/processes are involved.

### 4.2. Windows PowerShell

PowerShell also supports redirection for external Java processes:

```powershell
javac CliStderrDemo.java
java CliStderrDemo 21 1> success.out 2> success.err
java CliStderrDemo abc 1> failure.out 2> failure.err
$LASTEXITCODE
```

After the last Java command, `$LASTEXITCODE` is expected to be `2`. For the most recent successful invocation, the expected value is `0`.

PowerShell has its own stream system, and output/encoding handling for native commands can vary by version. Therefore, when automating integration, verify the actual file contents and exit codes on your target PowerShell/Windows version. Do not mistake Java's stderr messages for a thrown PowerShell exception; it is simply output from a child process.

### 4.3. Windows cmd.exe

In Command Prompt:

```bat
javac CliStderrDemo.java
java CliStderrDemo abc 1> failure.out 2> failure.err
echo %ERRORLEVEL%
```

The expected value is `2`. The `1>` and `2>` syntax here also represents stdout and stderr.

### 4.4. Why separate stdout in a CLI?

If stdout is consumed by a pipeline expecting JSON, CSV, numbers, or a file list, a diagnostic line injected into stdout can **corrupt machine-readable output**:

```text
WRONG: stdout contains both data and messages
42
WARNING | Using default configuration
```

Separating the two streams:

```text
stdout: 42
stderr: WARNING | Using default configuration
```

A command can succeed while emitting warnings to stderr; **having stderr output does not automatically mean a non-zero exit code**. Reliable scripts should rely on the exit code and data contract, not simply searching for the word “ERROR” in a text file.

## 5. Stack Traces: Throwable.printStackTrace() Writes to stderr by Default

In Java, `Throwable.printStackTrace()` writes the stack trace to `System.err` by default.

Standalone example: create the file `StderrStackTraceDemo.java`:

```java
public final class StderrStackTraceDemo {
    public static void main(String[] args) {
        try {
            Integer.parseInt("invalid");
        } catch (NumberFormatException exception) {
            System.err.println("ERROR | Invalid port configuration");
            exception.printStackTrace();
        }
        System.out.println("demo-finished");
    }
}
```

Compile, run, and separate the streams:

```bash
javac StderrStackTraceDemo.java
java StderrStackTraceDemo 1> result.txt 2> trace.txt
```

**Exact `result.txt` file:**

```text
demo-finished
```

**File `trace.txt`** contains the error message line and the `NumberFormatException` stack trace; illustrative format:

```text
ERROR | Invalid port configuration
java.lang.NumberFormatException: For input string: "invalid"
    at java.base/java.lang.NumberFormatException.forInputString(...)
    ...
    at StderrStackTraceDemo.main(StderrStackTraceDemo.java:<line>)
```

The `...` and `<line>` placeholders are **not verbatim output**. Stack frames and line numbers depend on the JDK and compiled source code. Do not compare an entire stack trace against a fixed string in tests.

There are three different ways to write this:

```java
exception.printStackTrace();               // Defaults to System.err.
exception.printStackTrace(System.err);    // Explicitly specify PrintStream.
System.err.println(exception);            // Only toString(), not full frames.
```

These are **illustrative calls inside a method that has an `exception` variable**. `System.err.println(exception)` typically prints only the exception name and message via `toString()`, not the full frames.

**Important limitation:** `printStackTrace()` goes directly to the stream/writer without passing through levels, handlers, filters, formatters, MDC, or the application's logging backend. In an application that already uses a logging framework, pass the entire `Throwable` object to the logger at the appropriate error-handling site:

```java
logger.log(java.util.logging.Level.SEVERE,
        "Failed to load configuration", exception);
```

This is the JUL API, assuming `logger` is a `java.util.logging.Logger`. For the exception's full stack trace to appear, the formatter/handler must support `LogRecord.getThrown()`; JUL's `SimpleFormatter` does this.

Do not call both `exception.printStackTrace()` and `logger.log(..., exception)` for the same error without a clear reason, as it can produce duplicate records in the console/collector.

## 6. JUL: ConsoleHandler Writes to stderr by Default

`java.util.logging` (JUL) is the logging API built into the JDK. `ConsoleHandler` is the handler that sends logs to the console, and **by default it outputs via `System.err`**. This is **different** from using `System.err.println(...)` directly:

| Characteristic | `System.err.println(...)` | JUL `ConsoleHandler` |
| --- | --- | --- |
| Default destination | stderr | stderr |
| Logger-level threshold | None | Yes |
| Handler-level threshold | None | Yes |
| Formatter | Developer-crafted message | `Formatter`, typically `SimpleFormatter` by default |
| Exception details | Printed manually by developer | `LogRecord` can carry a `Throwable` |
| Handler inheritance | None | Supports parent handlers |
| Formatting, filtering | Custom-written | JUL configuration |

A program using `Logger.info(...)` **is not guaranteed** to produce stdout lines; if the record reaches JUL's `ConsoleHandler`, it can be printed to stderr even though its level is INFO. This is a common reason learners see “INFO logs inside the error file” when using `2> error.log`.

### 6.1. Runnable Java 17 Example with ConsoleHandler

Create the file `JulStderrDemo.java`:

```java
import java.util.logging.ConsoleHandler;
import java.util.logging.Formatter;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class JulStderrDemo {
    public static void main(String[] args) {
        Logger logger = Logger.getLogger(JulStderrDemo.class.getName());

        // Save the logger's old configuration so changes are not kept after the demo.
        Level oldLevel = logger.getLevel();
        boolean oldParentHandlers = logger.getUseParentHandlers();
        Handler[] oldHandlers = logger.getHandlers();

        // A handler for the demo, not using the root's default handler.
        ConsoleHandler console = new ConsoleHandler();
        console.setLevel(Level.INFO);
        console.setFormatter(new Formatter() {
            @Override
            public String format(LogRecord record) {
                return record.getLevel().getName() + " | "
                        + formatMessage(record) + System.lineSeparator();
            }
        });

        for (Handler handler : oldHandlers) {
            logger.removeHandler(handler);
        }
        logger.setUseParentHandlers(false);
        logger.setLevel(Level.FINE);
        logger.addHandler(console);

        try {
            logger.fine("Hidden because console threshold is INFO");
            logger.info("Service ready");
            logger.warning("Using fallback configuration");
            System.out.println("result=OK");
        } finally {
            logger.removeHandler(console);
            console.close();
            logger.setLevel(oldLevel);
            logger.setUseParentHandlers(oldParentHandlers);
            for (Handler handler : oldHandlers) {
                logger.addHandler(handler);
            }
        }
    }
}
```

Compile and run:

```bash
javac JulStderrDemo.java
java JulStderrDemo 1> jul.out 2> jul.err
```

**Exact `jul.out` file:**

```text
result=OK
```

**Exact `jul.err` file:**

```text
INFO | Service ready
WARNING | Using fallback configuration
```

The `FINE` line is not printed—**not because stderr is only for ERROR**, but because `console.setLevel(Level.INFO)` filters out FINE. The logger is set to `FINE` so it accepts the record, but the handler filters it out before formatting.

`logger.setUseParentHandlers(false)` prevents records from propagating to the root logger's handlers, avoiding duplicate logs in the demo. The code restores the existing level/propagation and handlers in `finally`; `console.close()` only closes the handler created by the demo. This is a standalone learning program; in a server handling concurrent requests/threads, you should not swap out shared handlers on the fly while the system is serving traffic.

**A deeper note:** `ConsoleHandler` retains its target stream for the lifetime of the handler. If a program calls `System.setErr(...)` **after** the handler has already been created, do not assume the existing handler will automatically follow the new stream. Log destinations should be configured at startup rather than unexpectedly swapping JVM-wide streams.

### 6.2. JUL's logging.properties

You can use a `logging.properties` file to enable the root ConsoleHandler:

```properties
handlers = java.util.logging.ConsoleHandler
.level = INFO
java.util.logging.ConsoleHandler.level = INFO
java.util.logging.ConsoleHandler.formatter = java.util.logging.SimpleFormatter
```

When you have a valid JUL application, specify the file at JVM startup:

```bash
java -Djava.util.logging.config.file=logging.properties MyApplication
```

Here `MyApplication` simply refers to **an existing main class in your application**, not a new demo file. `ConsoleHandler` will write accepted records to stderr according to JUL's behavior. `SimpleFormatter` typically adds timestamps, class/method names, and levels, so the output will differ from `JulStderrDemo`'s compact formatter.

The **logger** level and the **ConsoleHandler** level are two independent thresholds. If the logger allows FINE but the handler only allows INFO, FINE messages still will not appear. In JUL, `getHandlers()` only returns handlers attached **directly** to the target logger; logs may still reach parent/root handlers if `useParentHandlers` is enabled.

## 7. SLF4J SimpleLogger: How to Configure stderr?

**SLF4J** is a logging facade for Java. An `org.slf4j.Logger` object does not decide on its own whether to write to stdout or stderr; that belongs to the **provider/backend**.

With the `slf4j-simple` provider, the `org.slf4j.simpleLogger.logFile` property lets you choose the destination:

```properties
org.slf4j.simpleLogger.defaultLogLevel=info
org.slf4j.simpleLogger.logFile=System.err
```

This is illustrative content for `simplelogger.properties`, typically placed on the classpath, such as `src/main/resources/simplelogger.properties` in a Maven application. `System.err` is a target value supported by `slf4j-simple`; other SLF4J implementations **do not use the same file or the same property names**.

Example SLF4J calls in a class with `org.slf4j.Logger LOG`:

```java
LOG.info("Application started");
LOG.error("Cannot process request");
```

With the configuration above and an active provider, **both INFO and ERROR can end up on stderr**. This illustrates that **the stderr destination is not an automatic condition for the ERROR level**, and **the ERROR level does not automatically select stderr**.

If you change the property to:

```properties
org.slf4j.simpleLogger.logFile=System.out
```

the SimpleLogger provider will route logs to stdout as configured. For Logback or Log4j2 backends, use their respective appender configurations instead of SimpleLogger properties.

SLF4J API 2.x requires a compatible runtime provider. If the provider is missing, calls may fall back to NOP and log nothing as expected; if multiple providers are present, the chosen backend may not be what you expect. When stderr lines are missing, check the **actual provider** and dependency tree rather than just editing the `LOG.error(...)` call.

## 8. Logback: Selecting System.err with ConsoleAppender

With Logback Classic, `ConsoleAppender` has a `target` property. In `logback.xml`, you can specify:

```xml
<configuration>
    <appender name="STDERR"
              class="ch.qos.logback.core.ConsoleAppender">
        <target>System.err</target>
        <encoder>
            <pattern>%-5level | %logger{1} - %msg%n</pattern>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="STDERR"/>
    </root>
</configuration>
```

This is a **minimal complete Logback configuration file**; to use it, the application needs the SLF4J API and a compatible Logback backend/provider. If the code calls:

```java
LOG.info("Service started");
LOG.warn("Slow dependency");
LOG.error("Request failed");
```

then with the root/logger at INFO and no other filters, all three records can be emitted to **stderr** because the appender targets `System.err`. Do not infer that `INFO` automatically goes to stdout or `ERROR` automatically goes to stderr: a single appender can receive multiple levels.

If the application already has its own Logback config, edit the file that is actually loaded rather than creating a competing `logback.xml`. `org.slf4j.Logger` does not have a generic `setOutputStream(System.err)` API to change the destination; routing belongs to the provider and appenders.

## 9. Log4j2: ConsoleAppender Target SYSTEM_ERR

With **Apache Log4j2**, a Console appender can specify `target="SYSTEM_ERR"` in `log4j2.xml`:

```xml
<Configuration status="WARN">
    <Appenders>
        <Console name="StderrConsole" target="SYSTEM_ERR">
            <PatternLayout pattern="%level | %msg%n"/>
        </Console>
    </Appenders>

    <Loggers>
        <Root level="info">
            <AppenderRef ref="StderrConsole"/>
        </Root>
    </Loggers>
</Configuration>
```

This configuration defines a console appender that writes every event **accepted by root** at INFO or above to stderr. To use it, the program needs matching Log4j2 API/Core at runtime; `log4j2.xml` must be placed where Log4j2 can load it, such as Maven's `src/main/resources/log4j2.xml`. This is a **configuration example**, not a standalone Java program.

Example source code using the Log4j2 API:

```java
import org.apache.logging.log4j.LogManager;
import org.apache.logging.log4j.Logger;

public final class Log4jStderrSnippet {
    private static final Logger LOG =
            LogManager.getLogger(Log4jStderrSnippet.class);

    public static void main(String[] args) {
        LOG.info("Initialized");
        LOG.error("Unavailable dependency");
        System.out.println("result=OK");
    }
}
```

This class **compiles if the project already provides the Log4j2 API dependency**, while writing to stderr as configured requires Log4j2 Core and `log4j2.xml` at runtime. `Log4jStderrSnippet.java` is not a JDK-only example; it cannot be run with plain `javac` without the external JARs.

### What if you want ERROR on stderr and INFO/WARN on stdout?

This is a **different** requirement from “send all console logging to stderr.” When you need to split levels across streams, declare **two separate appenders and filter them so they do not overlap**:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<Configuration status="WARN">
    <Appenders>
        <Console name="Stdout" target="SYSTEM_OUT">
            <ThresholdFilter level="ERROR"
                             onMatch="DENY"
                             onMismatch="NEUTRAL"/>
            <PatternLayout pattern="%level | %msg%n"/>
        </Console>

        <Console name="Stderr" target="SYSTEM_ERR">
            <ThresholdFilter level="ERROR"
                             onMatch="ACCEPT"
                             onMismatch="DENY"/>
            <PatternLayout pattern="%level | %msg%n"/>
        </Console>
    </Appenders>

    <Loggers>
        <Root level="INFO">
            <AppenderRef ref="Stdout"/>
            <AppenderRef ref="Stderr"/>
        </Root>
    </Loggers>
</Configuration>
```

This sample configuration is for Log4j2 using standard filters/levels:

- **Stdout:** when an event from root is ERROR or higher, the filter denies it; INFO/WARN are allowed to continue.
- **Stderr:** accepts only ERROR/FATAL; INFO/WARN are denied.
- **Root INFO:** drops DEBUG/TRACE before events reach either appender.

This is a **stream-splitting configuration example**, not Log4j2's default behavior. Other filters or child loggers with their own settings can change the outcome. Without complementary filters, an ERROR event can be **received by both appenders** and emitted twice across both streams.

**Note on duplicate log detection:** when an event is intentionally or accidentally emitted on both stdout and stderr, the collection system may store it as two records. If the requirement is a single destination per level, verify the filter and additivity configuration with actual test logs.

## 10. Distinguishing Log Levels from Output Streams

Common correlations, though **not a mandatory rule**:

| Call / system | Level | Possible destination |
| --- | --- | --- |
| `System.out.println("OK")` | No log level | stdout |
| `System.err.println("Warning")` | No log level | stderr |
| `Throwable.printStackTrace()` | No JUL/SLF4J log level | stderr by default |
| JUL `Logger.info(...)` via ConsoleHandler | INFO | stderr |
| JUL `Logger.severe(...)` via ConsoleHandler | SEVERE | stderr |
| SLF4J `LOG.error(...)` | ERROR | Determined by provider/backend |
| Log4j2 `LOG.info(...)` + `target="SYSTEM_ERR"` | INFO | stderr |
| Logback `LOG.error(...)` + `target=System.out` | ERROR | stdout |

An important sanity-check question: **“If I call LOG.error(...), is it guaranteed to go to stderr?”** — **No**. It follows the path logger → provider/backend → filter → appender/handler → configured destination.

Similarly, **`System.err` has no inherent log level**. It receives whatever strings are sent to it without understanding whether a string is “WARN” or “ERROR”. If you want an INFO→stdout, ERROR→stderr rule, the **logging backend or CLI logic** must enforce it; there is no universal built-in mapping in Java.

## 11. Capturing Output in Tests Without Mutating Global System.err

A testable design passes output streams as parameters, such as `CliStderrDemo.run(String, PrintStream, PrintStream)` in section 3.

Example of a test without JUnit, using JDK 17. Create `CliStderrCheck.java` in the same directory after creating `CliStderrDemo.java`:

```java
import java.io.ByteArrayOutputStream;
import java.io.PrintStream;
import java.nio.charset.StandardCharsets;

public final class CliStderrCheck {
    public static void main(String[] args) throws Exception {
        ByteArrayOutputStream outBytes = new ByteArrayOutputStream();
        ByteArrayOutputStream errBytes = new ByteArrayOutputStream();

        try (PrintStream out =
                     new PrintStream(outBytes, true, StandardCharsets.UTF_8);
             PrintStream err =
                     new PrintStream(errBytes, true, StandardCharsets.UTF_8)) {

            int exitCode = CliStderrDemo.run("21", out, err);
            out.flush();
            err.flush();

            String capturedOut =
                    outBytes.toString(StandardCharsets.UTF_8);
            String capturedErr =
                    errBytes.toString(StandardCharsets.UTF_8);

            boolean passed = exitCode == 0
                    && capturedOut.equals("42" + System.lineSeparator())
                    && capturedErr.equals(
                            "INFO | Parsed integer" + System.lineSeparator());

            System.out.println(passed ? "PASS" : "FAIL");
            if (!passed) {
                throw new AssertionError("Unexpected CLI streams");
            }
        }
    }
}
```

This is a **standalone test program**, but it requires the `CliStderrDemo` class in the same directory/classpath:

```bash
javac CliStderrDemo.java CliStderrCheck.java
java CliStderrCheck
```

**Exact stdout when the check passes:**

```text
PASS
```

Key takeaway: the test captures mock `PrintStream` instances and compares the two strings separately without calling `System.setOut(...)` or `System.setErr(...)`. The closed streams are **test-created streams**, not the process's standard streams.

### Why be cautious with System.setErr?

`System.setErr(PrintStream)` mutates the JVM's global stderr reference. It can be a useful technique for certain specialized tests, but it carries risks:

- Other threads in the same JVM may start accidentally writing into the test's stream.
- Logging handlers/appenders created **earlier** may hold a reference to a different stream and not follow the change.
- Failing to restore the state can affect subsequent tests.
- Accidentally closing `System.err` breaks error printing for other components.

For self-managed CLI code, **dependency injection of PrintStream** is usually cleaner and has less side-effect risk. For logging frameworks, test the appender/handler in a test configuration or use the backend's test appender rather than arbitrarily mutating global streams.

## 12. stderr in IDEs, Containers, and Log Collection Systems

### IDEs

Java IDEs may display stdout and stderr in **the same console**, sometimes using different colors or fonts. This is purely a **display presentation**: it does not merge the two streams into one. To verify, run the program in a shell with `1>` and `2>` as shown above.

### Docker / Kubernetes

Many container platforms collect both a process's stdout and stderr and forward them to a log driver/collector. For example, `docker logs` or `kubectl logs` typically let you view logs emitted by a containerized process, though storage, stream labels, and retention policies depend on the environment.

Do not assume that:

- Every container platform automatically maps `stderr` to ERROR severity.
- `stdout` cannot contain WARN or ERROR.
- Both streams are always merged in exact chronological order.
- Every line is stored long-term without size limits or truncation.

When deploying on Kubernetes, logs may be aggregated by pod, container, and instance. For distributed debugging, include a service name, valid request ID/trace ID, and timestamp in log records. However, **writing a trace ID into a log does not create a distributed trace on its own**.

### Background Programs

Service managers, task schedulers, or serverless environments may route stderr to a journal, file, collection system, or dedicated monitoring UI. “I don't see it in the terminal” **does not mean the log wasn't emitted**; check the destination to which the runtime environment attaches the stream.

## 13. Production Considerations When Using stderr

**1. Do not log secrets.** Error lines or stack traces can contain file paths, SQL, auth headers, tokens, API keys, or user data. Do not log entire request bodies just for debugging. A line sent to stderr can be forwarded to a collector and persist for a long time.

**2. Do not overuse it for CLI success output.** If primary output will be read by scripts, keep stdout clean. A progress bar or diagnostic message can use stderr, but provide appropriate quiet/verbose modes.

**3. Do not automatically close standard streams.** Avoid `System.err.close()` and `System.out.close()`. Other parts of the application may still need these streams. Only close streams you create or own.

**4. Do not assume flush guarantees durability.** `System.err.flush()` or `PrintStream` flushes buffers within its control, but does not guarantee logs are durably persisted to disk or a collector. The process can crash, the collector can lose connectivity, or queues can fill up.

**5. Keep one event per line when possible.** In multithreaded applications, multiple fragmented `print(...)` calls can interleave message pieces; calling `println(...)` with a complete message is usually easier to read. Stack traces remain multiline and require proper formatting/collector configuration so they aren't split into contextless events.

**6. Prevent log injection.** Untrusted data can contain newlines, tabs, or control characters. Do not interpolate raw user input directly into a log line where it can forge new log lines. Use structured logging, strip unsafe characters, and rely on proper backend escaping.

**7. Do not manually synchronize everything on System.err.** When multiple threads log concurrently, a logging framework managing events, levels, formatting, and sinks is better suited than scattered `println` calls. Still, the framework must target the right destination; a slow appender can hurt throughput.

**8. Maintain a consistent stream policy.** If a CLI decides `stdout=data` and `stderr=diagnostics`, enforce that rule across all success and failure branches. If a server uses stdout for all structured logs, don't force ERROR to stderr just because of the level's name.

## 14. Common Issues and Diagnostics

| Symptom | Possible cause | How to check/fix |
| --- | --- | --- |
| `System.err.println` does not appear in `out.txt` | stderr is separate from stdout; only `1>` was redirected | Use `2> err.txt` to capture stderr |
| JUL `INFO` logs appear in `err.txt` | `ConsoleHandler` outputs to stderr by default | This is expected behavior; it does not mean INFO became ERROR |
| `LOG.error(...)` goes to stdout | Backend/appender sets `SYSTEM_OUT`/`System.out` | Check actual config; level does not determine stream |
| `LOG.info(...)` missing from stderr | Filtered by logger or handler, wrong provider/backend, stream redirected elsewhere | Check logger level, handler/appender, config file, and destination |
| Same exception appears twice | Calling both `printStackTrace` and logging, or multiple appenders/handlers | Pick one pipeline and check additivity/parent handlers |
| Redirected both streams to a file but order looks strange | Buffering, multiple threads, or redirection order | Do not rely on interleaved order; add timestamps/correlation IDs |
| Exit code is still 0 after printing ERROR | Only printed a message without changing process status | Set the proper exit code, e.g., `System.exit(2)` for CLI errors |
| Stream not visible in IDE | IDE merges/hides stderr or filters the console | Run in a shell with `1>` and `2>` to compare |
| Test changing `System.setErr` breaks other tests | Mutated global stream without restoring | Pass `PrintStream` as a parameter or use a test appender |
| Logs truncated during collection | Event length limits, multiline stack traces, collector config | Check end-to-end pipeline and multiline configuration |
| Only INFO appears, FINE does not in JUL | Logger/ConsoleHandler threshold is INFO | Check `isLoggable(Level.FINE)` and `handler.getLevel()` |
| Log file not updated even though stderr has records | Only Console appender/handler configured; no file sink | Add a file appender/handler with an appropriate retention policy |

### Layer-by-Layer Diagnostic Checklist

1. **Source API:** is the code calling `System.err` directly, JUL, SLF4J, or Log4j2?
2. **Level:** is the event filtered at the logger before being created?
3. **Handler/appender:** is the declared destination `stderr`, `stdout`, or a file?
4. **Filter and layout:** does the event pass through to the destination without losing the Throwable/context?
5. **Process redirect:** where do the shell/IDE/service manager route `fd 1` and `fd 2`?
6. **Collector:** does the platform label streams, split/truncate lines, or apply different retention?
7. **Exit status:** does the command return the right exit code independently of stderr text?
8. **Safety:** do messages and stack traces avoid leaking sensitive data or creating duplicate logs?

## 15. Self-Check Questions

**Q1:** In Java, which call writes directly to stderr?  
**Answer:** `System.err.println("...")` or similar methods on `System.err`.

**Q2:** Does `System.err.println("ERROR")` automatically cause the program to return a non-zero exit code?  
**Answer:** No. Writing text and setting the process exit code are two separate things.

**Q3:** For `java CliStderrDemo 21 > result.txt 2> diagnostic.txt`, where does the value `42` go?  
**Answer:** In `result.txt`. The line `INFO | Parsed integer` goes to `diagnostic.txt`.

**Q4:** Does JUL `ConsoleHandler` write to stdout or stderr by default?  
**Answer:** stderr. It can write INFO/WARNING/SEVERE records to stderr if levels and filters accept them.

**Q5:** Is SLF4J `LOG.error(...)` guaranteed to output to stderr?  
**Answer:** No. The provider/backend and handler/appender configuration determine the stream.

**Q6:** Why does `Throwable.printStackTrace()` easily cause duplicate logs?  
**Answer:** It prints directly to stderr; if the same exception is also passed to a logger with a console appender, both paths can emit the same stack trace.

**Q7:** To send INFO/WARN to stdout and ERROR/FATAL to stderr in Log4j2, what is needed?  
**Answer:** Two console appenders with targets `SYSTEM_OUT`/`SYSTEM_ERR` and matching filters so they do not overlap.

**Q8:** Why should you avoid calling `System.setErr(...)` in parallel unit tests?  
**Answer:** It mutates the JVM's global stream, can affect other threads/tests, and does not guarantee existing handlers will follow the new stream.

**Q9:** If a command produces stderr output but exits with code 0, did it definitely fail?  
**Answer:** No. stderr may contain warnings or progress updates. You must rely on the program's contract and actual exit code.

**Takeaway:** **stderr is an output stream independent of stdout, not the ERROR level.** For Java CLIs, keep stdout for results and stderr for diagnostics, while returning appropriate exit codes. With logging frameworks, clearly trace **logger → handler/appender → stream** and verify the backend configuration before concluding where an event will be written.
