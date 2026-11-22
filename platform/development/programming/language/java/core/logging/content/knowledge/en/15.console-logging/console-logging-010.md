# Testing Console Output in Java Logging: From System.out to ConsoleAppender

## 1. What Does Testing Console Output Verify?

Many Java applications write information to the **console** for developers to view in an IDE, for processes to be monitored by the operating system, or for container runtimes and log collectors to gather. A line logged via a logger is not guaranteed to reach the console; conversely, content seen in the terminal may come from a logger, from `System.out.println`, from Maven, or from another library.

**Testing console output** means verifying that in a defined scenario:

1. **The right events** are emitted, with none missing or emitted by mistake.
2. **The right stream** receives the record: standard output (`stdout`) or standard error (`stderr`).
3. **The right format**: level, logger, event code, message, context fields, line endings, charset.
4. **The right count and order when there is a contract**: no unintended duplication; no assumption of a global order between two independent streams.
5. **Proper error handling**: exception type, cause, and stack trace are present when needed.
6. **No data leaks**: tokens, passwords, or private information do not appear in messages, MDC, or exceptions.
7. **Correctness at runtime**: records pass through the logger, filter, appender, encoder, and finally reach the observable output.

Key point to remember: a test checking a `logger.error(...)` call is **not equivalent** to testing the bytes actually written to `stderr`. Unit tests can verify events inside the JVM; integration tests must go through the real output configuration.

Example of two desired outputs:

```text
stdout: INFO|OrderService|event=order.created order_id=O-17
stderr: ERROR|PaymentService|event=payment.failed code=UPSTREAM_TIMEOUT
```

The `stdout:` and `stderr:` parts above are only **explanatory labels**. In a real console, they are typically two separate byte streams and do not automatically prepend those labels to the lines.

### The Goal Is Not to "Assert Every Character in the Terminal"

Good tests assert **the contract that needs to be protected**. If timestamps, random IDs, thread names, or stack trace line numbers legitimately change, comparing the entire terminal output as a fixed string can cause many false-positive test failures. However, if the system specifies that stdout must only contain JSON Lines, then **the validity of each JSON object and the field names** are the contract worth testing.

## 2. Stdout and Stderr: Two Different Channels

The JDK has three standard streams:

| Stream | Java API | Common Purpose |
| --- | --- | --- |
| Standard input | `System.in` | Receives input data from a terminal or pipeline. |
| Standard output | `System.out` | Informational output, program results, logs routed to stdout. |
| Standard error | `System.err` | Error diagnostics, warnings, or logs routed to stderr. |

**There is no Java rule stating that all ERROR logs must go to stderr.** That is decided by the logging backend and appender configuration. For example:

- `System.out.println(...)` goes to the current `System.out`.
- `System.err.println(...)` goes to the current `System.err`.
- `java.util.logging.ConsoleHandler` writes to `System.err` by default, though its level, formatter, and handler can be configured differently.
- `Logback ConsoleAppender` can choose `System.out` or `System.err` via `<target>`.
- `Log4j 2 Console` can be configured with `target="SYSTEM_OUT"` or `target="SYSTEM_ERR"`.

In containers, the deployment platform may collect both streams and display them in a single UI. Seeing two lines appear next to each other in a terminal **does not prove** they went through the same stream.

### Should INFO Go to Stdout and ERROR Go to Stderr?

That is an **optional policy**, not a requirement. If the infrastructure requires stream separation, configure appenders/filters so each level goes to its intended destination. If the platform only has a single stdout pipeline with a `level` field, sending both INFO and ERROR to stdout can also be reasonable.

When testing, verify **the project's policy** rather than imposing one universal rule across all backends.

## 3. Console Testing Layers

There are at least four levels of testing, each protecting something different:

| Level | What Is Observed? | Common Tools | What It Cannot Prove |
| --- | --- | --- | --- |
| Business logic unit test | Does the scenario emit the right log event/level? | Spy/mock logger, ListAppender, CapturingHandler | Which stream receives the real output and how it is encoded. |
| Format test | How are Message, Throwable, MDC, and pattern/JSON formatted? | Real layout/encoder + byte buffer | Whether the collector/container received the data. |
| Standard streams test in JVM | Data written via `System.out` and `System.err` in a code block | `System.setOut`, `System.setErr`, `ByteArrayOutputStream` | Whether an appender already captured another stream before replacement; child processes. |
| Integration test with a child process | Actual JVM output after startup/configuration | `ProcessBuilder` + file/pipe, exit code | Whether an external collector stored and displayed it accurately. |

In CI, combine **fast event-level tests** with **a few integration tests from a fresh process**. There is no need to spin up an entire server/container to test every small log statement, but you also should not check only `getFormattedMessage()` and claim production stdout/stderr is accurate.

## 4. Assertion Criteria to Choose Clearly

A console test can verify:

- **Required lines present:** `event=order.created` appears after successful processing.
- **Forbidden lines absent:** no `ERROR` when a recovery operation succeeds.
- **Stream routing:** `INFO` goes to stdout, `ERROR` goes to stderr according to the declared configuration.
- **Level and content:** the message does not merely contain the word `error`, but has the right level and event code.
- **Occurrence count:** a final failure produces exactly one `payment.failed` event code at the observed destination.
- **Exceptions:** stack trace and cause are not dropped when diagnostics are needed.
- **Line delimiters:** text records are separated properly by newlines; multi-line exceptions are handled properly by the collector.
- **Unicode:** Vietnamese text and non-ASCII characters are not corrupted.
- **Security:** fake secrets do not appear in any stream or field.
- **Process status:** a failing command has a non-zero exit code if that is the application contract; merely logging an ERROR **does not automatically** make a process exit with 1.

With multi-threaded logging, do not assert an absolute order across all events unless the program has synchronization guaranteeing that order. If two threads write independently, **the interleaved order of stdout and stderr is not a reliable contract**.

## 5. Standalone Java 17 Example: Capturing Stdout and Stderr in the Same JVM

The first example needs no logging library outside the JDK. It demonstrates how to **temporarily replace the standard streams**, run a scenario, retrieve the bytes, decode UTF-8, perform an **exact** content comparison, and restore the original streams in `finally`.

Save as **`ConsoleCaptureTest.java`**:

```java
import java.io.ByteArrayOutputStream;
import java.io.PrintStream;
import java.nio.charset.StandardCharsets;

public final class ConsoleCaptureTest {
    private ConsoleCaptureTest() {
    }

    private static void scenario() {
        System.out.println("INFO|order.created|order_id=O-17");
        System.err.println("ERROR|payment.failed|code=DOWN");
    }

    private static void requireEquals(
            String expected, String actual, String label) {
        if (!expected.equals(actual)) {
            throw new AssertionError(label + " mismatch: ["
                    + actual + "]");
        }
    }

    public static void main(String[] args) {
        PrintStream savedOut = System.out;
        PrintStream savedErr = System.err;

        ByteArrayOutputStream outBytes = new ByteArrayOutputStream();
        ByteArrayOutputStream errBytes = new ByteArrayOutputStream();

        PrintStream captureOut =
                new PrintStream(outBytes, true, StandardCharsets.UTF_8);
        PrintStream captureErr =
                new PrintStream(errBytes, true, StandardCharsets.UTF_8);

        try {
            System.setOut(captureOut);
            System.setErr(captureErr);
            scenario();
        } finally {
            captureOut.flush();
            captureErr.flush();
            System.setOut(savedOut);
            System.setErr(savedErr);
            captureOut.close();
            captureErr.close();
        }

        String stdout = new String(
                outBytes.toByteArray(), StandardCharsets.UTF_8);
        String stderr = new String(
                errBytes.toByteArray(), StandardCharsets.UTF_8);

        String lineEnd = System.lineSeparator();
        requireEquals(
                "INFO|order.created|order_id=O-17" + lineEnd,
                stdout, "stdout");
        requireEquals(
                "ERROR|payment.failed|code=DOWN" + lineEnd,
                stderr, "stderr");

        System.out.println("PASS stdout");
        System.out.println("PASS stderr");
        System.out.println("PASS streams_separated");
    }
}
```

Compile and run with JDK 17+:

```bash
javac -encoding UTF-8 ConsoleCaptureTest.java
java ConsoleCaptureTest
```

**Exact stdout:**

```text
PASS stdout
PASS stderr
PASS streams_separated
```

Why only the three PASS lines appear: the lines from `scenario()` went into the test buffers; after `finally`, `System.out` and `System.err` were restored. The PASS messages were printed after restoration, so they appear on the real console.

### How It Works

1. `ByteArrayOutputStream` holds data in memory; each stream has its **own buffer**.
2. `PrintStream(..., true, StandardCharsets.UTF_8)` converts characters to UTF-8 bytes and enables appropriate auto-flushing.
3. `System.setOut` and `System.setErr` swap the **process-global references**; subsequent `System.out.println`/`System.err.println` calls generally go through the temporary streams.
4. `finally` restores both original streams **even if the scenario throws an exception**, preventing later tests from reading the wrong buffer.
5. `captureOut.close()` and `captureErr.close()` only close the test streams, not the JVM's `savedOut` or `savedErr`.
6. `new String(bytes, UTF_8)` decodes using the exact charset the test used for encoding.
7. `System.lineSeparator()` reflects the operating system's line ending, so the example does not hard-code `\n` on systems using `\r\n`.

**Important limitation:** this test checks data flowing through the `System.out`/`System.err` references at the time `scenario()` is called. It is **not sufficient** to verify a `ConsoleAppender` that was initialized earlier and may have already cached its output stream. Some backends write through a saved stream, file descriptor, or another mechanism; replacing `System.out` after startup may fail to capture logs. Therefore, backend output tests should use a test appender or a **child process**, as shown in the next section.

### When Not to Use `System.setOut`

Avoid using it indiscriminately in a parallel test suite or in an application actively serving requests, because `System.out` and `System.err` are **global** state:

- Test A replaces `System.out`, while Test B logs concurrently and accidentally writes into A's buffer.
- A library may have cached the stream reference beforehand.
- Another thread still writes to the old stream or the new stream unexpectedly.
- Calling `setOut` does not affect logs sent directly to files, sockets, or native streams.

If you use this style of test, isolate the affected tests, do not run tests that modify standard streams in parallel, and always restore the streams in `finally`. For larger systems, prefer running a child JVM.

## 6. Java 17 Example: Testing Console Output from a Child Process

A **process-based test** observes the target process from the outside. It helps verify startup, actual output, exit code, and stdout/stderr separation. This approach is closer to deployment conditions than merely swapping `System.out` inside the test JVM.

We will create **two Java files** in the same directory:

```text
console-process-test/
├── ConsoleChild.java
└── ConsoleProcessTest.java
```

### 6.1. Program Under Test: `ConsoleChild.java`

```java
import java.io.PrintStream;
import java.nio.charset.StandardCharsets;

public final class ConsoleChild {
    public static void main(String[] args) {
        PrintStream out =
                new PrintStream(System.out, true, StandardCharsets.UTF_8);
        PrintStream err =
                new PrintStream(System.err, true, StandardCharsets.UTF_8);

        out.println("READY|order=O-17|note=Đã tạo đơn");
        err.println("WARN|retry=1|note=Thử lại");

        if (args.length > 0 && "fail".equals(args[0])) {
            System.exit(7);
        }
    }
}
```

We explicitly use UTF-8 for both outputs to test Vietnamese text independently of the terminal's default charset. The two wrappers in this example **do not close `System.out` or `System.err`**; process termination will release those streams.

When run with the `fail` argument, the program outputs two lines and exits with **exit code 7**. This is **intentionally simulated** application behavior; Logback/JUL do not automatically turn ERROR or WARN into exit code 7.

### 6.2. Test Program: `ConsoleProcessTest.java`

```java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.concurrent.TimeUnit;

public final class ConsoleProcessTest {
    private static void require(
            boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    public static void main(String[] args) throws Exception {
        String javaExe = Path.of(
                System.getProperty("java.home"),
                "bin",
                System.getProperty("os.name").startsWith("Windows")
                        ? "java.exe" : "java"
        ).toString();

        Path stdoutFile = Files.createTempFile("console-check-", ".out");
        Path stderrFile = Files.createTempFile("console-check-", ".err");

        try {
            Process child = new ProcessBuilder(
                    javaExe,
                    "-cp",
                    System.getProperty("java.class.path"),
                    "ConsoleChild",
                    "fail"
            ).redirectOutput(stdoutFile.toFile())
             .redirectError(stderrFile.toFile())
             .start();

            if (!child.waitFor(10, TimeUnit.SECONDS)) {
                child.destroyForcibly();
                child.waitFor();
                throw new AssertionError("child timeout");
            }

            String stdout = Files.readString(
                    stdoutFile, StandardCharsets.UTF_8);
            String stderr = Files.readString(
                    stderrFile, StandardCharsets.UTF_8);
            String newline = System.lineSeparator();

            require(child.exitValue() == 7, "wrong exit code");
            require(stdout.equals(
                    "READY|order=O-17|note=Đã tạo đơn" + newline),
                    "wrong stdout: " + stdout);
            require(stderr.equals(
                    "WARN|retry=1|note=Thử lại" + newline),
                    "wrong stderr: " + stderr);

            System.out.println("PASS exit_code=7");
            System.out.println("PASS stdout_utf8");
            System.out.println("PASS stderr_utf8");
        } finally {
            Files.deleteIfExists(stdoutFile);
            Files.deleteIfExists(stderrFile);
        }
    }
}
```

### 6.3. Compile and Run

From the directory containing both files, using JDK 17+:

```bash
javac -encoding UTF-8 ConsoleChild.java ConsoleProcessTest.java
java -cp . ConsoleProcessTest
```

**Exact stdout of the test program:**

```text
PASS exit_code=7
PASS stdout_utf8
PASS stderr_utf8
```

The child program exits with code 7, but `ConsoleProcessTest` treats **7 as the expected result**, so the test program still finishes successfully when all conditions pass.

### Why Use Temporary Files for Output?

`ProcessBuilder` can open pipes for stdout/stderr, but if a test only reads one pipe while the child writes a large amount to the other pipe, the OS buffer can fill up and block the child. This example **redirects both streams to two temporary files** to avoid having to drain both concurrently while preserving stream separation.

In addition:

- `waitFor(10, TimeUnit.SECONDS)` prevents the test from hanging forever on a stuck child.
- On timeout, `destroyForcibly()` followed by `waitFor()` ensures the test attempts to terminate the child before cleaning up.
- `redirectOutput` and `redirectError` keep both streams separate, unlike `redirectErrorStream(true)`, which **merges stderr into stdout**.
- Waiting for the child to exit before reading the files avoids reading incomplete data.
- `Files.readString(..., UTF_8)` verifies proper Vietnamese UTF-8 decoding.
- `Files.deleteIfExists` cleans up resources even when an assertion fails.

**Example limitation:** it launches the Java class in the same directory using the test's `java.class.path`; for a fat JAR, module path, Maven Surefire, or container, adjust the launch command to match the real artifact command. The main strength of this test style is that you can use the **production startup command** for real verification.

## 7. Testing Logback's ConsoleAppender

If the application uses **SLF4J + Logback**, `System.out.println` is not equivalent to `logger.info`. You must also test the Logback configuration to know which events go to stdout and which go to stderr.

Example of an explicit policy:

- Only **INFO** level events go to `System.out`.
- Only **ERROR** level events go to `System.err`.
- The same event must not appear in both streams.

You can configure two `ConsoleAppender` instances and two `LevelFilter` filters.

### 7.1. Project Structure

```text
logback-console-check/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── demo/
        │       └── LogbackConsoleApp.java
        └── resources/
            └── logback.xml
```

### 7.2. The `pom.xml` File

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>logback-console-check</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>ch.qos.logback</groupId>
            <artifactId>logback-classic</artifactId>
            <version>1.5.16</version>
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
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

`logback-classic` provides the SLF4J backend/provider along with its required dependencies. The pinned version is for lesson reproducibility; it is **not a claim about the latest security-patched release**. For real applications, follow your framework's dependency management and security advisories.

### 7.3. The `src/main/resources/logback.xml` File

```xml
<configuration>
    <appender name="INFO_OUT" class="ch.qos.logback.core.ConsoleAppender">
        <target>System.out</target>
        <filter class="ch.qos.logback.classic.filter.LevelFilter">
            <level>INFO</level>
            <onMatch>ACCEPT</onMatch>
            <onMismatch>DENY</onMismatch>
        </filter>
        <encoder class="ch.qos.logback.classic.encoder.PatternLayoutEncoder">
            <pattern>%level|%logger{0}|%msg%n</pattern>
            <charset>UTF-8</charset>
        </encoder>
    </appender>

    <appender name="ERROR_ERR" class="ch.qos.logback.core.ConsoleAppender">
        <target>System.err</target>
        <filter class="ch.qos.logback.classic.filter.LevelFilter">
            <level>ERROR</level>
            <onMatch>ACCEPT</onMatch>
            <onMismatch>DENY</onMismatch>
        </filter>
        <encoder class="ch.qos.logback.classic.encoder.PatternLayoutEncoder">
            <pattern>%level|%logger{0}|%msg%n</pattern>
            <charset>UTF-8</charset>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="INFO_OUT" />
        <appender-ref ref="ERROR_ERR" />
    </root>
</configuration>
```

**Why `LevelFilter` is needed on both appenders:** if you only use `ThresholdFilter level="INFO"` for stdout, it normally accepts **INFO, WARN, and ERROR**, not just INFO. Then an ERROR event would also go to stdout as well as stderr, causing a "single destination only" test to fail.

The `LevelFilter` in this sample configuration allows **only the exact level** specified. As a result, `WARN` is dropped from both targets. This is solely a **practice-exercise policy**, not a recommendation to drop all WARN logs in production. A real configuration might add a dedicated WARN appender or design thresholds that cover every level you need to retain.

### 7.4. The `src/main/java/demo/LogbackConsoleApp.java` File

```java
package demo;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public final class LogbackConsoleApp {
    private static final Logger LOG =
            LoggerFactory.getLogger(LogbackConsoleApp.class);

    private LogbackConsoleApp() {
    }

    public static void main(String[] args) {
        LOG.info("event=start order_id={}", "O-17");
        LOG.error("event=failed code={}", "UPSTREAM_TIMEOUT");
    }
}
```

Compile and run from the project directory:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.LogbackConsoleApp
```

**Two application records expected (separated by stream):**

```text
stdout: INFO|LogbackConsoleApp|event=start order_id=O-17
stderr: ERROR|LogbackConsoleApp|event=failed code=UPSTREAM_TIMEOUT
```

The `stdout:` and `stderr:` labels are documentation annotations, **not part of the real messages**. Maven commands may produce extra output from the runner or environment. When both streams are displayed in the same terminal window, the visual order between the two lines may not strictly match the call order because the two streams are handled independently.

### 7.5. How to Test the Backend Properly

To verify the configuration above:

1. Launch **the application in a new process** so Logback loads `logback.xml` from that process's classpath.
2. Capture stdout and stderr **separately**; you can use shell redirection or `ProcessBuilder` as in Section 6.
3. Assert that the INFO line appears only on stdout and the ERROR line appears only on stderr.
4. Assert there are no duplicate records at the same destination.
5. Check the message and stable fields, avoiding dependence on timestamps from a different pattern.
6. Add a WARN test case and prove the behavior matches the policy; in this learning configuration it is dropped from both streams.
7. Re-read the output if you change dependencies, configuration files, or the launch command; do not infer from source alone that `logback.xml` was definitely loaded.

If running through Maven, remember to distinguish Maven's lines from the program's lines. For strict testing of the final artifact, execute **the real Java/JAR startup command** instead of comparing all of Maven's stdout.

### Warning About `System.setOut` with Logback

`ConsoleAppender` can capture a reference to `System.out` or `System.err` during initialization. If a unit test replaces `System.out` **after the backend has initialized**, the appender may keep writing to the old stream, causing the test to capture an empty buffer even though the user still sees logs.

Therefore, **do not assume `System.setOut` captures every Logback ConsoleAppender**. With Logback, you can test events with `ListAppender<ILoggingEvent>`, test layout output with a test appender writing to a `ByteArrayOutputStream`, or test **with a subprocess** for the real stdout/stderr path.

## 8. Testing JUL (`java.util.logging`) Console Output

The JDK provides `java.util.logging.Logger` and `ConsoleHandler`. A common point of confusion: JUL's standard `ConsoleHandler` normally writes to **stderr**, even when the record has level `INFO`. The `INFO` level does not automatically make JUL switch to stdout.

Illustrative snippet:

```java
java.util.logging.Logger log =
        java.util.logging.Logger.getLogger("demo.payment");

log.info("event=payment.started");
```

If the default JUL `ConsoleHandler` is in use, the result may appear on stderr with a timestamp and logger name determined by `SimpleFormatter`; do not hard-code a specific stdout line without controlling the configuration.

### Checking Levels at Both Logger and Handler

JUL can have levels on both the source logger and the handler. A `FINE` log blocked by the source logger never reaches the handler. If the logger accepts `FINE` but the handler is set to `INFO`, the record can still be dropped at the handler.

Tests should consider:

- Logger name and effective level.
- Handlers attached to child/parent loggers.
- Whether `useParentHandlers` causes duplicate logs.
- Whether the handler target/formatter uses the right stream and encoding.
- Whether an exception passed in `LogRecord` appears in the output.

**Do not equate JUL levels with Logback levels:** JUL uses `SEVERE` for high severity and has no `Level.ERROR` constant; Logback and Log4j 2 use `ERROR`.

### Testing JUL Events Without Capturing the Console

When the goal is only to verify message, level, and Throwable, you can create an in-memory `Handler` that stores `LogRecord` instances, disable parent handlers in the test, and inspect `getLevel()`, `getMessage()`, and `getThrown()`. This is an **event test** and does not prove that `ConsoleHandler`'s formatter produced the right text.

When the goal is to verify stderr on a real process, run a subprocess and capture stderr separately. Distinguishing these two goals prevents many brittle tests.

## 9. JUnit 5: Organizing Tests Without Breaking Other Tests

When converting the two Java 17 examples into JUnit tests, the most important thing is **state isolation**.

### Testing Output from a Pure Java Method

You can use the following pattern inside a JUnit 5 test class, with `out`/`err` created using UTF-8:

```java
PrintStream originalOut = System.out;
PrintStream originalErr = System.err;

try {
    System.setOut(capturedOut);
    System.setErr(capturedErr);

    // Call a method to test in the same JVM.
    applicationAction.run();
} finally {
    System.setOut(originalOut);
    System.setErr(originalErr);
}
```

This is an **illustrative snippet**, not a standalone program: `capturedOut`, `capturedErr`, and `applicationAction` must be declared. In a complete JUnit test, add `@Test`, assertions, and cleanup for the test buffers/streams; run sequentially or lock the shared resource so two tests do not modify standard streams at the same time.

JUnit 5 provides parallel execution controls and resource locks, but they are only fully effective when every test using the global resource follows the same isolation rules. You cannot expect a resource lock in one test to stop all external libraries from continuing to write to stdout.

### If You Only Want to Check Logback Events

You can use `ListAppender<ILoggingEvent>` in a test to collect events without touching `System.out`. Then check:

- Whether `getLevel()` equals `Level.ERROR`/`Level.INFO`.
- Whether `getLoggerName()` matches the logging component.
- Whether `getFormattedMessage()` contains the event code and required context.
- Whether `getThrowableProxy()` is present when logging an exception.
- Whether MDC and key-value fields are attached properly for the backend/version.

After the test, detach and stop the temporary appender, and restore logger levels and additivity in `finally`; backend loggers are typically JVM-shared objects rather than scoped to a single test method.

**Limitation:** `ListAppender` proves the event reached the test appender, **not** that the real `ConsoleAppender` writes properly to stdout/stderr. Add an integration test for stdout/stderr when that is an important requirement.

## 10. Checking Output Strings: What Is Stable and What Is Dynamic

### 10.1. When Full String Comparison Works

Exact string comparison works well for deterministic formats:

```text
INFO|order.created|order_id=O-17
```

when the code and pattern contain no data that varies per run. In tests, build the expected string with `System.lineSeparator()` if the program uses platform-dependent `println`.

In particular, in the `ConsoleCaptureTest.java` example, comparing two separate streams including the newline is an intentional contract.

### 10.2. When Not to Compare the Full String

Real-world patterns often look like:

```text
%d{ISO8601} %-5level [%thread] %logger - %msg%n
```

Timestamps and thread names can vary. Stack trace source line numbers also change after refactoring.

In that case:

- Parse or extract level, event code, trace ID, and message separately.
- Verify the timestamp is valid and falls within a reasonable time window.
- Check the logger name as intended (full or abbreviated).
- For exceptions, check type, cause, and stack trace markers rather than depending on line numbers.
- For asynchronous logging, wait for events/processes to finish with a bounded timeout.
- When multiple threads log, compare the set of records or group by correlation ID instead of enforcing a global order.

### 10.3. Detecting Duplicate Logs

An `order.created` event appearing twice can happen because:

1. The code calls the logger twice.
2. Both a child logger and root logger attach appenders while additivity/propagation is enabled.
3. Two appenders write to the same stream.
4. A framework and a logging bridge are configured inconsistently.
5. A collector re-receives a record due to retries and duplicates it.
6. A business operation actually ran twice due to a retry or client resend.

Tests should define **the counting target**: in one process's stdout, in stderr, in each file, or in a central store. Two appenders intentionally sending the same event to **two different destinations** is not necessarily a bug.

## 11. Charset, Unicode, and Newlines in Console Output

### Charset

Java strings are Unicode, but console output consists of **bytes**. A logger/encoder may use UTF-8 while the terminal or collector decodes with a different encoding. The result is corrupted Vietnamese text.

For tests:

- When creating a test `PrintStream`, specify `StandardCharsets.UTF_8`.
- When reading `byte[]` or files, use `StandardCharsets.UTF_8`.
- With Logback or Log4j 2, specify the corresponding charset in the encoder/layout when needed.
- When testing a real terminal, check both the writer and the reader rather than only fixing an object's `toString()`.
- For byte streams that went through a collector, verify the charset end-to-end across the pipeline.

In the child-process example, the code explicitly uses `PrintStream(..., UTF_8)` and the test reads with `Files.readString(..., UTF_8)` to catch Unicode issues deterministically.

### Line Endings

`System.out.println` uses the environment's line separator. With text layouts, the `%n` conversion typically adds the appropriate newline. When testing on Windows and Linux:

- Do not hard-code `\n` if the contract is "OS-native newline".
- If the project specifies fixed LF (for example, JSON Lines sent over a protocol), assert `\n` per that contract.
- If **normalizing CRLF → LF**, only do so in tests where the project accepts both forms; do not normalize if you need to catch formatting bugs.
- Do not casually call `trim()` when you want to verify exact whitespace, newlines, or empty content. `trim()` can hide missing or extra characters.

### Multiline Output and Stack Traces

A single exception record can produce multiple physical lines. If the observability system assumes "one line = one event", the parser may split a stack trace into multiple fake records.

Tests should distinguish:

- **Number of events emitted by the logger:** checked at the event layer or by event ID.
- **Number of console lines:** can be greater than the number of events when stack traces are present.
- **Number of records stored by the collector:** depends on multiline or structured logging configuration.

If the contract requires one JSON object per line, use a proper JSON encoder with escaping and verify that each line parses as valid JSON, rather than concatenating raw JSON with a pattern.

## 12. Testing Log Levels and Destinations

A test matrix should clearly state inputs and expected outcomes:

| Scenario | Level | Verification Goal |
| --- | --- | --- |
| Order created successfully | INFO | Success event appears in expected channel, no spurious ERROR. |
| Temporary retry failure then recovery | WARN/DEBUG (per policy) | Does not mistakenly log a "final failure". |
| Final payment failure | ERROR/SEVERE | Contains event code, error code, trace, and Throwable when needed. |
| DEBUG disabled | DEBUG | Produces no DEBUG output, even if the code has log calls. |
| Logger writes to filtered appender | INFO/WARN/ERROR | Stream receives only the levels allowed by the filter. |
| Stdout collector outage | Level-independent | Console has data, but it may be missing in the central store. |

**There is no universal rule requiring WARN to go to stderr.** Some applications send all levels to stdout and include a `level` field; others split by severity. Tests must be derived from the agreed logging diagram, not just from level names.

## 13. Testing Sensitive Data and Log Injection

Console logs may be forwarded to external services or retained for months. Therefore, "it's just the console" does not mean data can be printed carelessly.

Create tests using a **fake token**, for example:

```text
SECRET_TEST_TOKEN_123
```

Then ensure **neither stdout nor stderr** contains this string during error scenarios. Check all of the following:

- Formatted messages.
- MDC/ThreadContext or additional key-value fields.
- Exception messages and stack traces.
- Library/SDK events that might print requests or headers.
- All appenders that output to console/file.
- The log collector, if integration tests exist.

Example to avoid:

```java
log.info("Authorization={}", authorizationHeader);
```

This is an illustrative snippet assuming `log` and `authorizationHeader` variables exist. Using the `{}` placeholder **does not automatically mask tokens**. Log injection can also occur if an input value contains newlines and is written to the console as multiple forged lines. Use typed fields, encoders with proper escaping, and an allowlist policy for logged data.

**Never use real secrets in tests.** For sensitive data, test with fake strings that have a similar shape.

## 14. Pitfalls When Testing Console Output in CI/CD

### 14.1. Maven/Gradle Also Write to the Console

A command like:

```bash
mvn test
```

can print build info, warnings, and plugin errors in addition to application output. If a test compares all of `mvn`'s stdout against a fixed string, it can easily break when the environment or plugin version changes.

Good practices:

1. Run the application JAR/class separately or use the test runner API to observe only the child process's output.
2. If you still need to inspect Maven output, filter by a clear identifier such as `event_code` instead of treating every build line as an application log.
3. Save stdout and stderr separately in CI when diagnostics are needed.
4. When a test fails, print the captured output to the test report **after restoring the streams** to avoid polluting the data being asserted.

### 14.2. The Console May Be Redirected Outside the Application

The shell may send stdout to a file and stderr to the screen; containers may merge both; IDEs may colorize or group by thread. Checking output by opening a terminal **is not enough** to know which bytes belong to which stream. A subprocess with separate redirections enables clear verification.

### 14.3. Color/ANSI and Interactive Mode

Some backends or frameworks may use ANSI escape codes to colorize logs. Output that visually reads `ERROR` actually contains extra control characters in the string. When testing:

- Disable colors if the production contract is plain text.
- Or parse/strip ANSI codes under allowed rules if color is purely presentational and not protected data.
- Do not blindly strip all control characters when you need to detect log injection.

### 14.4. Parallel Tests

When multiple threads/processes write concurrently, logs can interleave according to scheduler order. A reliable test will:

- Attach an event ID or request ID.
- Synchronize tasks when order must be asserted.
- Wait with an explicit timeout.
- Assert the set of records instead of assuming a fixed sequence.
- Never let one test's `System.setOut` affect other tests.

### 14.5. Test Timeouts and Orphan Processes

A hung subprocess can hang CI along with it. Use `waitFor(timeout, unit)`, terminate the process on timeout, and collect diagnostics. If the program spawns **additional child processes**, killing only the parent PID may not terminate the entire process tree; complex workflows need process-tree management or CI sandboxing.

## 15. Common Issues Table for Console Output Testing

| Symptom | Likely Cause | How to Handle |
| --- | --- | --- |
| `System.out` buffer is empty, but logs appear on screen | Backend captured the stream before `setOut` | Use a subprocess or a test appender/encoder. |
| INFO appears on stderr with JUL | JUL ConsoleHandler normally writes to stderr | Check the backend and handler; do not infer from level. |
| ERROR appears on both stdout and stderr | Two appenders use overlapping thresholds | Use LevelFilter or non-overlapping routing policy when needed. |
| Two lines appear in a different order | The two standard streams are displayed/interleaved independently | Assert each stream separately; do not enforce order between stdout and stderr. |
| Test fails on Windows | Different CRLF, charset, or shell redirection | Use `System.lineSeparator()` and explicit charsets. |
| Vietnamese characters are garbled | Encoder and reader do not both use UTF-8 | Inspect output bytes and decode consistently. |
| Test passes, but collector has no logs | Only tested inside JVM, not the full pipeline | Add staging integration tests with the collector. |
| Test times out | Child blocked on pipe, deadlocked, or slow startup | Drain concurrently, redirect to files, or intentionally merge streams; set a timeout. |
| One ERROR spans multiple lines | Multi-line stack trace | Check events and multiline configuration. |
| Only message logged, no cause visible | Passed `ex.getMessage()` instead of the Throwable | Check that the event has the Throwable and the formatter outputs stack traces. |
| No DEBUG logs | Blocked by logger level or filter | Check effective level, handler/appender, and provider. |
| Running `mvn exec` prints many extra lines | Maven/plugins also write to the console | Distinguish application output from runner tool output. |
| Log contains a secret | Sensitive data passed into event or Throwable | Test with fake tokens and protect all streams and appenders. |
| Subsequent tests fail strangely | Forgot to restore `System.out/System.err` | Always use `finally` and isolate global tests. |
| Console logged error, but process exited 0 | Logging does not determine the exit code | Test exit code as a separate contract. |

## 16. Practice Exercises

### Exercise 1 — Distinguishing Two Streams

Given the code:

```java
System.out.println("INFO|ready");
System.err.println("ERROR|failed");
```

Question: can you guarantee that the ERROR line will appear **after** the INFO line when viewed in a terminal?

**Hint:** No. The two statements are called in that order on the thread, but stdout and stderr are two independent streams and may be collected by the terminal/IDE/collector in a way that does not preserve cross-stream ordering. Assert each stream separately.

### Exercise 2 — Checking the Debug Window

A logger is configured with root level `INFO`. The code has:

```java
log.debug("event=diagnostic id={}", id);
```

Why does changing the pattern to include `%msg` still not show `DEBUG`?

**Hint:** The event may already be dropped at the logger level before reaching the formatter/appender. Check effective levels and filters, not just the layout.

### Exercise 3 — Fixing a Test with Global Side Effects

A test calls `System.setOut(new PrintStream(buffer))` and finishes without restoring it. What is the consequence?

**Hint:** Other tests and libraries may keep writing into that buffer, causing missing output or overlapping assertions. Use `try/finally` and keep references to the original streams. When running tests in parallel, use a subprocess.

### Exercise 4 — Avoiding Deadlock When Reading a Child Process

A child writes a huge amount of data to both stdout and stderr. The parent calls `child.getInputStream().readAllBytes()` first and only reads stderr afterward. What is the risk?

**Hint:** The child may block because the stderr pipe is full and be unable to exit, while the parent waits for stdout to finish. Use two concurrent reader threads, redirect to two files, or use `redirectErrorStream(true)` if you **do not need** to distinguish streams.

### Exercise 5 — Asserting Logback Output

With the configuration from Section 7, answer:

1. Where do INFO events go?
2. Where do ERROR events go?
3. Where do WARN events go?
4. Why can replacing `LevelFilter` with `ThresholdFilter level="INFO"` on stdout cause duplicate ERROR output?

**Hint:** INFO goes to stdout, ERROR goes to stderr, and WARN is dropped by both filters (per the **illustrative** configuration). Threshold INFO also accepts higher levels, so ERROR can go to both stdout and stderr. In production, define a complete policy for WARN rather than accidentally dropping warnings.

### Exercise 6 — Testing for Secrets

A piece of code logs a fake token via `logger.error("failed token={}", token)`. Should the test only check `System.out`?

**Hint:** No. The record may be routed to stderr or multiple other appenders. Test every destination that needs protection, plus exception messages and structured fields; never use real tokens.

### Exercise 7 — Unit Tests vs. Integration Tests

A unit test sees `ILoggingEvent.getFormattedMessage()` is correct, but the running application has no logs in the centralized system. List the layers that need checking.

**Hint:** The active provider/backend, logger level/filters, appender/target, formatter/encoder, stdout/stderr or file, collector/agent, parser/multiline rules, index, access permissions, and search time window. A correct `ILoggingEvent` is only one part of the path.

## 17. Checklist Before Considering Console Output Tests Complete

1. **Know the exact backend:** JUL, Logback, or Log4j 2; do not guess solely from Java imports.
2. **Know the target stream:** stdout, stderr, file, or both.
3. **Include both success and failure cases:** do not test only a single ERROR line.
4. **Test events and output separately:** semantic unit tests + stream integration tests.
5. **Do not pollute JVM state:** restore `System.out/System.err` and loggers/appenders if modified.
6. **Prevent subprocess hangs:** timeouts, process cleanup, and buffer/pipe management.
7. **Check charset:** UTF-8, especially with Unicode and Vietnamese text.
8. **Check formatting:** level, event code, message, context, newlines, and Throwable.
9. **Check for duplicate and missing logs:** per stream, appender, and collector; do not just count lines containing the word ERROR.
10. **Check security:** fake secrets do not appear in stdout, stderr, stack traces, MDC, or other channels.
11. **Do not assert dynamic data as constants:** timestamps, threads, and stack trace line numbers need appropriate assertions.
12. **Run with the real artifact/command when needed:** Maven/IDE output does not substitute for the deployed JVM's output.
13. **Verify the collector if that is part of the contract:** seeing logs on the console does not automatically mean the centralized system received them.

**Conclusion:** Testing console output is more than "seeing text printed on the screen." Verify **event → logger/filter → appender/encoder → stdout or stderr → collector** according to your goal. Use `ByteArrayOutputStream` for simple code within a single JVM, use a test appender to inspect logger events, and use `ProcessBuilder` when you need to assert real console output, exit codes, charsets, and runtime configuration.