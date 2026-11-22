# Testing File Output in Java Logging

## 1. Why Test Actual Log Files?

When developing a Java application, a `logger.info` or `logger.error` call does not guarantee that a record has been written to a file. An event may be blocked by a level/filter, the logger may not have a `FileHandler`/`FileAppender` attached, the configuration may point to `stdout`, the appender may not have started, the data may still be in a buffer/async queue, the file may have rotated to an archive, the directory may not be writable, or the actual logging provider may differ from what the test expects.

The **Testing File Output** topic in the **Testing logging** group helps verify the **final result at the file sink**: whether the file exists, contains the expected events, uses the right encoding/format, has no blocked logs or unintended duplicates, and properly closes its resources. Testing API calls and testing output files are two different tasks.

Contract example:

~~~text
Logger name: example.orders
Effective level: INFO
File: application.log
Encoding: UTF-8
Format: LEVEL|MESSAGE\n

Input:
  INFO  ĐƠN_HÀNG id=42
  WARN  RETRY attempt=2
  DEBUG DEBUG_IGNORED

Expected file contents (two physical lines):
  INFO|ĐƠN_HÀNG id=42
  WARNING|RETRY attempt=2
~~~

This example uses JUL's `WARNING` level name instead of `WARN` used by many other backends. It is not the default output of every framework; tests must know the **actual backend and formatter**.

### Learning Outcomes

After this lesson, you will know how to:

1. Distinguish between mock loggers, capturing `Handler`/`ListAppender`, and real file integration tests.
2. Set up temporary directories, isolated paths, and safe cleanup.
3. Run a Java 17 program using JUL `FileHandler` and read/verify UTF-8 output.
4. Apply the same principles to JUnit 5 `@TempDir`.
5. Test Logback `FileAppender`, Log4j 2 `FileAppender`, and Spring Boot configurations.
6. Test level/filter, append/truncate, rolling/rotation, async flush, and multithreading.
7. Reduce flaky tests caused by timestamps, sleep, shared files, and unclosed resources.
8. Design filesystem error, security, CI, and end-to-end tests tailored to the sink type.

## 2. Which Layer Should You Test?

The logging pipeline passes through multiple components:

~~~text
Java code
   |
   +--> Logger API (JUL / SLF4J / Log4j 2)
            |
            v
       Level / Filter / Logger hierarchy
            |
            v
       Log event / MDC
            |
            v
       Formatter / Encoder / Layout
            |
            v
       Handler / Appender
            |
            +--> File / Rolling file
            +--> Console stdout/stderr
            +--> Async queue -> worker -> file
            +--> Remote sink
            |
            v
       Filesystem / container runtime / collector
~~~

| Test type | What it verifies | What it does not verify |
| --- | --- | --- |
| Mock logger | Code calls the right level and template | Whether the file was written |
| JUL capturing Handler | Actual `LogRecord` reached the handler | Encoding, file path, disk I/O |
| Logback `ListAppender` | `ILoggingEvent`, marker, MDC, throwable | `FileAppender` and byte output |
| File integration test | File existence, content, charset, flush, close | Whether the collector/cloud backend ingested it |
| Rolling test | Active/archive files, rollover conditions | Copies in backend/expired backups |
| Container end-to-end | Runtime/collector receives logs | Absolute zero-loss guarantee on crash |

When the requirement is **Testing File Output**, a test that only asserts on a mock or `ListAppender` is not enough. It is valuable for logging logic, but you still need a test that reads the **actual file** from the sink being verified.

### Choosing Clear PASS Criteria

The test contract should specify:

- How the file path is resolved.
- Whether it is a new file or appended to an existing one.
- Which levels and filters are enabled.
- The exact layout/encoding.
- How many events are expected and which events must not be written.
- Whether a single event is allowed to have a multi-line stack trace.
- When the file is considered complete for reading (flush/close/drain).
- Whether rollover or async delivery is involved.
- Whether the test is allowed to delete files/archives after running.

Do not rely on a standalone `Files.exists` assertion as proof that logging works. The file could have been created empty, or it could be a stale file from a previous test.

## 3. Designing Safe Test Fixtures

A good test uses a temporary path created by the test itself:

~~~java
// Java 17 snippet, used inside a test method.
java.nio.file.Path directory =
        java.nio.file.Files.createTempDirectory("log-file-test-");
java.nio.file.Path file = directory.resolve("application.log");
~~~

### Why Not Use a Fixed File in the Source Tree?

If a test writes directly to `logs/application.log`, several issues can occur:

- Test A leaves a line with the same content, causing Test B to falsely pass.
- Two parallel tests append simultaneously, interleaving content or overwriting each other's data.
- CI has a different working directory than the IDE.
- Windows locks open files, causing cleanup to fail.
- A test accidentally writes to production logs or deletes files it does not own.
- A test fails midway and leaves behind stale files or lock files.

Use `Files.createTempDirectory` or JUnit `@TempDir` to create a dedicated path per test. If a test requires multiple processes writing concurrently, design a separate fixture and locking mechanism; do not assume single-JVM synchronization substitutes for cross-JVM synchronization.

### File Handles and Cleanup

`FileHandler`, `FileAppender`, and async appenders have a start/stop/flush/close lifecycle. **Reading after closing the sink** reduces the risk of incomplete reads and releases file handles on Windows. When testing continuous streaming behavior while the appender remains open, use supported flush APIs and explicit synchronization.

During cleanup, delete only the files/paths that the fixture actually created. Do not run recursive delete commands on a real application directory just to clean up test logs.

### Charset

Explicitly specify UTF-8 on both the encoder/handler and when reading:

~~~java
Files.readString(file, StandardCharsets.UTF_8);
Files.readAllLines(file, StandardCharsets.UTF_8);
~~~

This is a snippet with appropriate imports. Do not rely on the platform's default charset, especially when handling Vietnamese text, quotes, escapes, or Unicode characters.

## 4. Standalone Java 17 Program: JUL `FileHandler`

The following example **requires no Maven/Gradle or external libraries outside the JDK**. It creates a real file, emits `INFO`/`WARNING`/`FINE` events, flushes and closes the `FileHandler`, reads back the UTF-8 file, and asserts the exact content. The temporary directory uses a random name, while stdout only contains fixed `PASS` lines.

**File: FileOutputTestDemo.java**

~~~java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.logging.FileHandler;
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class FileOutputTestDemo {
    private static void require(boolean condition, String reason) {
        if (!condition) {
            throw new AssertionError(reason);
        }
    }

    public static void main(String[] args) throws Exception {
        Path dir = Files.createTempDirectory("jul-file-test-");
        Path file = dir.resolve("application.log");

        try {
            Logger logger =
                    Logger.getLogger("example.testing.fileoutput");
            logger.setUseParentHandlers(false);
            logger.setLevel(Level.INFO);

            FileHandler handler =
                    new FileHandler(file.toString(), false);
            handler.setEncoding(StandardCharsets.UTF_8.name());
            handler.setLevel(Level.ALL);
            handler.setFormatter(new Formatter() {
                @Override
                public String format(LogRecord r) {
                    return r.getLevel().getName() + "|"
                            + formatMessage(r) + "\n";
                }
            });

            logger.addHandler(handler);
            try {
                logger.info("ĐƠN_HÀNG id=42");
                logger.warning("RETRY attempt=2");
                logger.fine("DEBUG_IGNORED");
                handler.flush();
            } finally {
                logger.removeHandler(handler);
                handler.close();
            }

            require(Files.isRegularFile(file), "File not created");

            List<String> lines = Files.readAllLines(
                    file, StandardCharsets.UTF_8);
            List<String> expected = List.of(
                    "INFO|ĐƠN_HÀNG id=42",
                    "WARNING|RETRY attempt=2");

            require(lines.equals(expected),
                    "Wrong file content: " + lines);
            require(Files.size(file) > 0, "File is empty");

            System.out.println("PASS: file exists");
            System.out.println("PASS: UTF-8 content and order");
            System.out.println("PASS: FINE event filtered");
        } finally {
            Files.deleteIfExists(file);
            Files.deleteIfExists(dir);
        }
    }
}
~~~

**Compile and run with JDK 17 or later:**

~~~bash
javac -encoding UTF-8 FileOutputTestDemo.java
java FileOutputTestDemo
~~~

**Exact stdout when the machine allows creating files in the temp directory:**

~~~text
PASS: file exists
PASS: UTF-8 content and order
PASS: FINE event filtered
~~~

There are no timestamps or temporary paths in stdout. The logger writes only to `FileHandler`; `setUseParentHandlers(false)` prevents it from propagating up to the root console handler.

### Mechanism Breakdown

1. **`createTempDirectory`** creates a fresh directory for the run, reducing collisions with stale files.
2. **`FileHandler(file.toString(), false)`** opens the file with `append=false`. JUL has a lock and unique filename mechanism; because each run has its own directory, lock contention is largely avoided in this demo.
3. **`setEncoding(UTF-8)`** specifies the write encoding. The same charset is used in `Files.readAllLines`.
4. **Logger `level=INFO`** filters out `FINE` at the call site. Handler level `ALL` allows the two events that passed the logger filter to reach the file.
5. **`Formatter.format`** fixes the format to `LEVEL|MESSAGE` and LF, without adding dynamic timestamps or thread names.
6. **`handler.flush`** flushes the handler buffer via its API; **`handler.close`** completes the lifecycle before the test reads the file.
7. **`logger.removeHandler`** prevents the logger from retaining a closed handler.
8. **`List.equals`** verifies the exact two lines, their order, Vietnamese diacritics, and the absence of `FINE` or extra events.
9. **`Files.size > 0`** serves as an additional positive check.
10. **`finally` cleanup** deletes only the file and directory created by the test. If `FileHandler` was not closed and still holds a lock, deletion may fail and the test must not falsely report `PASS`.

This result proves the semantics of the sample program in a normal environment; **it does not prove fsync durability, power-loss safety, async delivery, multi-process locking, or collector ingestion**. If I/O fails, the test should fail or report a clear error rather than swallowing the exception and printing `PASS`.

### Why Not Test Using `Thread.sleep`?

Some loggers have buffers or async queues. `Thread.sleep(1000)` might be enough on one machine, but it establishes no synchronization relationship between "event enqueued" and "file written". For the synchronous JUL `FileHandler` in the example, explicit `flush` and `close` are the proper verification points. For an async appender, you must wait for the drain/stop or completion signal of the backend in use.

## 5. Rewriting in JUnit 5 with `@TempDir`

In projects using JUnit Jupiter 5, `@TempDir` manages a temporary directory tied to the test lifecycle. The following class is a **real integration test for JUL `FileHandler`**, though it requires JUnit 5 and a compatible test runner; it will not compile standalone with just JDK `javac`.

**File: src/test/java/example/JulFileOutputTest.java**

~~~java
package example;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.UUID;
import java.util.logging.FileHandler;
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class JulFileOutputTest {
    @TempDir
    Path tempDir;

    @Test
    void writesExactUtf8LogFile() throws Exception {
        Path file = tempDir.resolve("events.log");

        Logger logger = Logger.getLogger(
                "example.filetest." + UUID.randomUUID());
        logger.setUseParentHandlers(false);
        logger.setLevel(Level.INFO);

        FileHandler handler = new FileHandler(
                file.toString(), false);
        handler.setEncoding(StandardCharsets.UTF_8.name());
        handler.setLevel(Level.ALL);
        handler.setFormatter(new Formatter() {
            @Override
            public String format(LogRecord r) {
                return r.getLevel().getName() + "|"
                        + formatMessage(r) + "\n";
            }
        });

        logger.addHandler(handler);
        try {
            logger.info("ĐÃ_GHI");
            logger.fine("NOT_WRITTEN");
            handler.flush();
        } finally {
            logger.removeHandler(handler);
            handler.close();
        }

        assertTrue(Files.isRegularFile(file));
        assertEquals(
                List.of("INFO|ĐÃ_GHI"),
                Files.readAllLines(file, StandardCharsets.UTF_8));
    }
}
~~~

### What Makes This Test Isolated?

- `@TempDir` provides a fresh directory path for the fixture.
- `UUID` creates a unique logger name per test, reducing interference when multiple tests share the same JVM.
- `logger.setUseParentHandlers(false)` prevents events from appearing in unexpected root handlers.
- Uses a concise `Formatter` independent of timezone, PID, thread, or wall-clock time.
- The handler is closed before asserting, which is critical when CI runs on Windows.
- Asserting `equals` on the full list detects missing lines, extra lines, out-of-order lines in synchronous cases, and encoding errors.
- JUnit cleans up `@TempDir` according to its lifecycle; `FileHandler` no longer holds a file lock during cleanup.

### Points to Distinguish

If a unit test uses Mockito `verify(logger).info(...)`, it does not prove that the logging backend wrote to a file. If a test uses Logback `ListAppender`, it proves that Logback created the event and delivered it to an in-memory appender, **not that `FileAppender` opened a file**. Keep both types of tests when they protect different contracts.

With Maven/Gradle, configure JUnit Jupiter and a compatible runner (Maven Surefire or Gradle `useJUnitPlatform`). Use the version managed by your project/BOM; there is no need to add a new version solely for this illustrative example.

## 6. Which Tests Should Include Positive and Negative Checks?

An empty file can cause an assertion like "does not contain `DEBUG`" to pass even if the logger is completely broken. Therefore, every important negative test should have a **positive control**:

~~~text
Emit INFO READY
Emit DEBUG SHOULD_NOT_APPEAR

Expected:
  file contains READY
  file does not contain SHOULD_NOT_APPEAR
~~~

Commonly useful checks:

| Condition | Positive check | Negative check |
| --- | --- | --- |
| Level filter | `INFO` is written | `DEBUG`/`FINE` is blocked |
| Business routing | `BUSINESS` goes to `business.log` | `TECHNICAL` does not leak in |
| Security redaction | Sanitized event appears | Fake token does not appear |
| Logger hierarchy | One record at the target sink | No duplicate from parent |
| Async drain | All IDs present after stop | No missing IDs from premature read |
| Rotation | Active + archive files exist | Nothing written outside fixture directory |
| Append | Old and new events present | Not truncated against policy |
| Truncate | Only new events present | Old data not retained |
| JSON Lines | Parses as valid object | No fake lines from CR/LF |

Asserting only `contains("INFO")` is too weak: the string `INFO` could appear in the message body or in an old file. It is better to assert the format, event identity, and event count whenever the contract allows.

## 7. Logback: Real `FileAppender` and Test Configuration

In an SLF4J + Logback application, `ListAppender` tests are useful for verifying `ILoggingEvent`, markers, MDC, or throwables. However, when file output is required, a real `FileAppender` is needed.

Example **src/test/resources/logback-test.xml**:

~~~xml
<configuration>
    <appender name="TEST_FILE"
              class="ch.qos.logback.core.FileAppender">
        <file>build/logging-test/application.log</file>
        <append>false</append>
        <encoder>
            <pattern>%level|%msg%n</pattern>
            <charset>UTF-8</charset>
        </encoder>
    </appender>

    <logger name="example.filetest"
            level="INFO" additivity="false">
        <appender-ref ref="TEST_FILE"/>
    </logger>

    <root level="WARN"/>
</configuration>
~~~

This is a **Logback configuration sample**, not a JUnit file that automatically verifies results. The path `build/logging-test/application.log` is illustrative only; when tests run concurrently, a fixed path causes collisions. In a real suite, configure an isolated **`LoggerContext`/`FileAppender` with a file from `@TempDir`**, or run tests in processes with separate output paths. Do not use this XML sample as the default CI configuration if your suite runs in parallel.

### Mechanisms to Assert

- Logger `example.filetest` has level `INFO` and references the correct `FileAppender`.
- `additivity="false"` stops test logger events from propagating to `root`; useful when a test wants an isolated sink.
- `PatternLayoutEncoder` formats each event as `LEVEL|MESSAGE` followed by a newline.
- Charset is set to `UTF-8`, matching the test's file reader.
- The appender must start successfully. If the path is not writable, Logback may report an error in its status manager without `logger.info` throwing an exception.
- After `appender.stop`/`context.stop`, read the file to verify; do not just check a "logger enabled" state.
- If a test modifies logger configuration on the shared default context, restore it or use a separate context so other tests are not affected.

### Programmatic Testing with `LoggerContext`

When you need a dynamic file path from `@TempDir`, a typical workflow is:

~~~text
create isolated LoggerContext
create PatternLayoutEncoder with context and UTF-8
start encoder
create FileAppender with test file path and encoder
start appender
create test logger with additivity=false
log known marker event
stop appender and LoggerContext
read and assert test file
~~~

This is a **workflow**, not a standalone Java snippet. Logback APIs and context lifecycles have version-specific details; check status and stop all resources in a `finally` block. Using the global `LoggerFactory` across multiple parallel tests can cause unintended logger hierarchy interference.

## 8. Log4j 2: `FileAppender` and Layout

Log4j 2 provides `FileAppender`, `RollingFileAppender`, `LoggerConfig`, `AppenderRef`, filters, and async mechanisms. An example fixture **src/test/resources/log4j2-test.xml**:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<Configuration status="WARN">
    <Appenders>
        <File name="TEST_FILE"
              fileName="target/logging-test/application.log"
              append="false">
            <PatternLayout pattern="%level|%msg%n"
                           charset="UTF-8"/>
        </File>
    </Appenders>

    <Loggers>
        <Logger name="example.filetest"
                level="info" additivity="false">
            <AppenderRef ref="TEST_FILE"/>
        </Logger>
        <Root level="warn"/>
    </Loggers>
</Configuration>
~~~

This is only an illustrative fixture **for Log4j 2 Core**, not for Logback. Tests must verify that the configuration is actually loaded by the active logging provider. In a project using the SLF4J API, the binding/provider determines the final backend; simply placing `log4j2-test.xml` on the classpath will have no effect if the provider is Logback.

**Proper testing:** create an isolated logging context or test process with a temporary file path, emit events, stop the appender/context, read the file back in UTF-8, and inspect both the content and the backend's status errors.

If using `AsyncLogger`/`AsyncAppender`, avoid reading the file immediately after `log.info`. Wait for the queue to drain/stop using the backend/version's API, then assert. A test that passes by luck does not prove the queue will not drop events when the backend is slow.

## 9. Spring Boot: File Writing Must Match the Real Backend

Spring Boot can use either Logback or Log4j 2 depending on dependencies; it also bootstraps logging fairly early. Configuration snippet:

~~~properties
logging.level.root=INFO
logging.file.name=build/logging-test/boot.log
~~~

The `logging.file.name` property instructs Boot's corresponding mechanism to write to a file; **it does not create separate files per logger category**. The path above is only an example and is unsafe when multiple tests write concurrently.

In Spring Boot integration tests, consider:

- Is the logging configuration loaded before or after the test sets the property?
- Does Spring Test cache `ApplicationContext` between tests?
- Does the backend have a file appender and write permissions?
- Is there an async appender that must be stopped/drained before the test ends?
- Does this test need to verify real Spring Boot startup/configuration, or just a single event?
- Are multiple test classes running in parallel sharing the same file?

`@SpringBootTest` is suitable for smoke-testing integration when you want to verify Boot's logging runtime. For small logic checks, use an isolated test logger/backend to avoid the overhead and side effects of the whole application context. When modifying global system properties, remember to restore them and isolate the process if the logging configuration is already cached.

## 10. Append and Truncate

A key file output concern is whether the file is opened in append mode or starts fresh.

| Scenario | Setup | Result to verify |
| --- | --- | --- |
| New file | Does not exist yet | File is created and contains event |
| Append | File has old lines, `append=true` | Old + new, properly separated |
| Truncate | File has old lines, `append=false` | Only new content remains |
| Logger restart | Appender stopped/started | Data retained per contract |
| Multiple processes on same path | Locking policy must be defined | Do not infer safety from single-JVM test |

In JUL:

~~~java
// Snippet; target is a valid Path created by the test.
FileHandler appendHandler =
        new FileHandler(target.toString(), true);
~~~

To test append, write fixture lines first, open the handler in append mode, log new records, close, and then read. However, **`FileHandler` has a pattern and lock mechanism**; if the file is already held by another handler, the actual filename may receive a unique suffix. Therefore, do not read a guessed path when lock contention exists.

Never let tests write to a user's `application.log` or a production pipeline. Overwriting/truncating in a test can cause data loss if the wrong path is used.

## 11. `RollingFile` and Rotation

In production, logs may be rotated by date or size:

~~~text
application.log
application.2026-11-09.log.gz
application.2026-11-08.log.gz
~~~

The names above are illustrative. The **active file** and **archives** are distinct datasets. A test that only reads `application.log` might conclude events are missing even though they were moved to a compressed file by the rolling policy.

Important test conditions:

1. The rollover threshold is actually triggered according to the configured policy.
2. The active file continues receiving new events.
3. Archives exist matching the expected pattern.
4. Compressed archives can be opened and contain the right content if required by policy.
5. No events are lost or duplicated within the guarantees being tested.
6. `maxHistory`/`totalSizeCap`/retention are interpreted correctly for the backend.
7. After a restart or reload, the appender does not delete or overwrite archives incorrectly.
8. Generated files are cleaned up only within the temp directory.

### Avoiding Clock-Related Flakiness

Waiting for midnight to trigger a daily rollover makes tests depend on timezone, daylight saving time, run schedules, and CI speed. It is better to use a triggering policy that can be invoked intentionally or configure size-based rotation in a small fixture, then stop the appender and inspect the result.

Do not assert exact archive date names if the backend uses a different timezone or the period has not been mocked. Do not confuse `maxHistory` with per-`LogRecord` TTL: file rotation and copy retention in a collector/index/backup are separate concerns.

## 12. Async Logging: Wait for Drain, Do Not Use Fixed Sleep

With async logging:

~~~text
Application thread
   |
   +---> log event created
              |
              v
         bounded queue
              |
              v
         logging worker
              |
              v
         file sink
~~~

When `logger.info` returns, the event may still be in the queue. Reading the file immediately afterward is not guaranteed to see the data; `Thread.sleep(1000)` only delays execution without confirming the queue has finished.

Test plan:

1. Configure the async backend with an explicit queue capacity and overflow policy.
2. Emit identifiable event IDs.
3. Wait for completion/drain/stop using a mechanism supported by the backend.
4. Close the sink safely.
5. Read the file and verify the event set, count, and dropped count.
6. For overflow tests, use a controlled slow sink to reproduce blocking/dropping instead of relying on lucky timing.
7. Separate requirements: `INFO` logs may be discarded per policy while `ERROR` logs may have a different policy; assert according to the contract.

Async reduces I/O waiting under normal conditions, **but it does not mean non-blocking, lossless, or durable storage**. If a critical event must be guaranteed, a dedicated durable storage architecture is needed rather than just a file/async queue.

## 13. Testing Multithreaded File Writing

If eight workers log concurrently, a test should not demand a global ordering:

~~~text
worker-A: event-A1 event-A2
worker-B: event-B1 event-B2
worker-C: event-C1 event-C2
~~~

Depending on scheduling, the order of `A1`/`B1`/`C1` may vary on every run. For a backend that guarantees each event is not corrupted or interleaved under test conditions, assert:

- Each event has a unique `event_id`.
- Total event count and unique ID count match the no-drop contract.
- No records are unexpectedly merged or truncated.
- Each event parses cleanly in the expected format.
- `MDC`/`correlation_id` values do not leak across threads.
- Per-producer ordering is checked only if the backend actually guarantees it.
- After workers finish, stop/close the appender before reading the file.

Example test: 4 tasks × 50 events, expecting 200 unique IDs after stop if the sink does not drop. These numbers are illustrative test data, not default parameters. When sampling or a drop policy is allowed, assertions must match that policy.

An appender that is thread-safe within one JVM is not automatically safe for **multiple JVMs writing to the same file**. Multi-process tests require their own fixtures and corresponding locking verification.

## 14. JSON Lines: Parse Instead of Just `contains`

In structured logging, an event can be a JSON line:

~~~json
{"timestamp":"2026-11-10T03:00:00Z","level":"INFO","event_type":"ORDER_ACCEPTED","order_id":"O-42"}
~~~

When the output contract is one JSON object per line, tests should:

- Parse each line with a standard JSON parser.
- Assert each object has `event_type`/`level` and required fields.
- Check types: `status` is numeric, `duration_ms` is numeric, `timestamp` is valid.
- Verify data containing quotes, backslashes, CR/LF, and Unicode is properly escaped.
- Verify no fake JSON lines are created via log injection.
- Verify no passwords, tokens, or sensitive payloads are present.
- Verify no duplicate events violate the contract.

The following snippet requires Jackson and is not standalone JDK Java code:

~~~java
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;

// outputFile is a Path provided by the fixture.
ObjectMapper mapper = new ObjectMapper();
for (String line : Files.readAllLines(
        outputFile, StandardCharsets.UTF_8)) {
    JsonNode value = mapper.readTree(line);
    if (!value.isObject() || !value.hasNonNull("event_type")) {
        throw new AssertionError("Invalid event schema");
    }
}
~~~

Do not parse JSON with `split(",")` because string values can contain commas, quotes, or escapes. If a test only asserts that the file contains `"ORDER_ACCEPTED"`, malformed JSON could still pass. Always validate the actual output structure.

## 15. Exceptions and Stack Traces: One Event Can Span Multiple Lines

When code logs:

~~~java
// SLF4J snippet, requires a real logger and exception.
log.error("Order failed id={}", orderId, exception);
~~~

A text layout may output the stack trace across multiple physical lines. In this case, `Files.readAllLines(...).size()` does not equal the number of events; that is not necessarily a bug.

Choose assertions based on the format:

- Text layout: check the prefix, exception class, and meaningful parts; avoid hardcoding line numbers.
- JSON layout: a single JSON line contains a properly escaped `stack_trace`; parse and assert.
- Output with multiline aggregation at a collector: test the collector configuration separately.
- Exception messages from user input: check redaction and log injection.
- Do not use a dynamic stack trace for byte-for-byte full-file comparisons if the code may be refactored.

A fixed text formatter like the JUL example in section 4 works well for exact content tests; however, production formatters must still be tested against their own schemas and behavior.

## 16. Failure Scenarios: File Write Errors

You cannot conclude logging succeeded just because the API did not throw an exception. Many backends report internal errors through a status manager or error handler rather than throwing on every `logger.info`.

| Failure | What to observe |
| --- | --- |
| Directory does not exist | Does the appender create the path or report an error? |
| No write permission | Does the appender fail to start or emit an error status? |
| Disk/quota full | Are logs dropped, does the backend report errors, or does the app block? |
| File held by another process | How do locking or unique file suffixes behave? |
| File renamed/deleted while open | Which handle does the sink continue writing to? |
| Rotation cannot rename/compress | Is there an error status and how does it recover? |
| Async queue full | Which block/drop/fallback policy applies? |
| Process restarts mid-event | What remains in the buffer/log file? |

Never run disk-full tests by filling up a developer machine's disk or a shared CI runner. Use a quota-limited volume/sandbox with safe cleanup. Never change permissions on real directories just to induce errors.

### Key Points When Testing Failures

- Distinguish between "logger API accepted" and "file sink write succeeded".
- If the backend has a status manager/error callback, assert the error signal.
- To test recovery, verify the appender can write to a new file after the error is resolved, per contract.
- Do not silently turn I/O errors into `PASS`; only ignore them under an explicit, controlled policy.
- For audit/business-critical events requiring transactional guarantees, file logging is usually insufficient; consider an outbox or durable event store.

## 17. Containers and Collectors: File Output May Not Be the Goal

Spring Boot applications in Docker/Kubernetes typically write to `stdout`/`stderr` for a runtime/collector to gather. In that architecture, a test requiring "`application.log` must exist on the local filesystem" **misses the target**.

| Actual sink | How to verify |
| --- | --- |
| JUL `FileHandler`/`FileAppender` | Read file in temp directory or volume |
| `ConsoleAppender` | Capture `stdout`/`stderr` or container logs at the appropriate layer |
| Docker runtime logging | Inspect container driver/runtime logs per test environment |
| Kubernetes | Observe container logs and collector |
| Centralized backend | Query events by controlled test ID |
| Remote appender | Check acknowledgment/record at destination via API |

For container logs, distinguish between ephemeral local container files, container runtime log files on the node, and the centralized storage backend. A test that only checks `docker logs` does not prove the collector ingested them; a test that queries an index does not prove all events are durably retained during an outage.

An end-to-end test can emit an event with a unique test ID, then verify output in Java, in the container runtime, and finally in the collector/backend. Limit resource usage, avoid personal data, and clean up test artifacts according to a dedicated retention policy.

## 18. CI and Preventing Flaky Tests

Common causes of flakiness:

1. Tests A and B write to the same file path.
2. A test reads a stale file or leftover content from `append=true`.
3. The global logger context is mutated by another test.
4. A test uses `Thread.sleep` to wait for async flush.
5. An unclosed `FileHandler`/`Appender` causes deletion failures on Windows.
6. A test compares real timestamps or thread names.
7. The platform charset differs from UTF-8.
8. A test asserts global ordering of concurrent events.
9. Rolling moved events to an archive, but the test only reads the active file.
10. Relative paths resolve differently across IDE/Maven/Gradle/CI.
11. The actual runtime backend differs from what the test configured.
12. Sink errors only appear in backend status, not as exceptions.

**CI checklist before merging tests:**

- Each test has its own temp dir/file.
- Positive control event confirms the sink is working.
- Negative checks cover key levels/filters/redactions.
- Synchronization uses lifecycle APIs rather than guessed delays.
- Stop/close in `finally`.
- Read as UTF-8 or parse JSON by schema.
- No raw PII/credentials in fixtures.
- Tests run fast enough without waiting for wall-clock rollover.
- On failure, display helpful diffs/metadata without exposing secrets.
- Safe under parallel execution.
- No modifications to production files/configs.
- Re-verify after upgrading the JDK, logging backend, or build/test runner.

## 19. Troubleshooting File Output

| Symptom | Possible cause | Check |
| --- | --- | --- |
| File does not appear | Wrong backend/config, different path resolution, appender failed to start | Runtime provider, `LoggerContext`, path, and status |
| File is empty | Level/filter, not flushed/closed yet | Positive control, effective level, lifecycle |
| Logs exist but fail on Vietnamese text | Mismatched charset | Encoder/file reader UTF-8 |
| Extra lines | Additivity, parent handler, or stale file | Disable parent, temp dir, exact count |
| Missing lines | Async not drained, rolling, dropped | Queue, archive files, errors |
| `.0` or `.1` files | JUL pattern generation or unique lock | `FileHandler` `%g`/`%u`, file contention |
| JUnit `@TempDir` fails to clean up | Handler not closed | `finally`, context stop |
| Passes locally, fails in CI | Permissions/working directory/OS | Temp dir, isolated path, charset |
| Logback XML has no effect | Different provider or config not loaded | Runtime logging dependency |
| Log4j 2 test creates no file | Logger does not ref appender or appender start failed | Configuration status |
| Stack trace increases line count | Multi-line text layout | Assert event schema instead of line count |
| JSON `contains` passes but parse fails | Custom string concatenation/bad escaping | Use standard JSON encoder and parser |
| Async test passes/fails intermittently | Sleep/reading before flush | Await/stop/drain via API |
| File deleted but disk space not freed | Process still holds inode/handle | Check process handles and filesystem |

A reliable diagnostic sequence is: identify provider → load config → effective logger level → appender start → sink path → emit positive control → stop/flush → read right file + archive → compare schema, charset, and event IDs.

## 20. Security and Privacy in Test Logs

Test files can also be collected into CI artifacts, backups, or dashboards. Therefore:

- Use synthetic data; never copy production HTTP bodies/headers into tests.
- Assert that fake tokens/passwords are absent from output; never log real secrets.
- When testing log injection, run only in test environments and verify CR/LF input does not create fake event lines.
- Placeholder logging is not a sanitizer; the output formatter/JSON encoder controls escaping.
- Log `request_id`/`trace_id` in controlled fixtures rather than real customer identifiers.
- If tests produce archives or error files, clean them up and set retention policies.
- Restrict read permissions on CI artifacts appropriately; do not publish sensitive log files in public reports.
- Never `chmod`/alter ACLs on production directories to simulate failure scenarios.
- Never use logger output as proof of an exactly-once transaction. File tests do not replace durable auditing.

## 21. Practice Exercises

**Exercise 1 – Level filtering.** Run `FileOutputTestDemo.java`, change the logger level from `INFO` to `FINE`, and update the expected list to include `FINE|DEBUG_IGNORED`. Verify the level and line count are correct; then revert to `INFO`.

**Exercise 2 – Append/truncate.** Create a temporary file with an existing line, open `FileHandler` with `append=true`, and log a new event. Assert both are kept. Run again with `append=false` and assert the old line is gone.

**Exercise 3 – JUnit `@TempDir`.** Run `JulFileOutputTest` with at least two test methods using separate files/loggers. Verify the tests are order-independent and release file locks cleanly.

**Exercise 4 – Logback `FileAppender`.** In a project using Logback, create an isolated `LoggerContext` with a path inside `@TempDir`, set `additivity=false`, log `INFO`, stop the appender, and read the file. Compare with a `ListAppender` test.

**Exercise 5 – Log4j 2 `RollingFile`.** Create a small size-based rollover fixture, emit events, stop the context, and inspect both the active file and the decompressed archives.

**Exercise 6 – Async logging.** Use an async appender with a controlled slow sink. Emit events with IDs, compare a fixed-sleep approach against official drain/stop, and explain why the results differ.

**Exercise 7 – Concurrency.** Have multiple threads write unique event IDs. After stopping, assert the total count of unique IDs and that no lines are merged/corrupted; do not assert global ordering.

**Exercise 8 – JSON/redaction.** Use a real JSON encoder to log values containing quotes, Unicode, CR/LF, and a fake token. Parse each JSON line; assert valid events and that the token is not exposed.

**Exercise 9 – Container.** If a production service logs to console rather than creating a file, redesign the test around `stdout`/runtime/collector. Explain why you should not add a `FileAppender` just to make a generic test pass.

## 22. Summary

**Testing file output in Java must touch the real file**, not just verify a logger call. Use isolated test paths, verifiable events, explicit UTF-8, proper flush/close lifecycles, both positive and negative assertions, and safe cleanup. The standalone Java 17 JUL program demonstrates the core mechanics, while JUnit 5 `@TempDir` supports stable fixtures in real projects.

With Logback and Log4j 2, test the actual `FileAppender`/`LoggerContext` rather than relying solely on `ListAppender`. For rolling files, check archives; for async logging, wait for drain/stop; for multithreading, verify the event set rather than arbitrary ordering; for Spring Boot and containers, test the real log destination the application uses. Keep CI results deterministic while avoiding sensitive data or touching files outside test scope.

### References

- Oracle Java 17 FileHandler: https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/FileHandler.html
- Oracle Java 17 Logger: https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Logger.html
- Oracle Java 17 Formatter: https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Formatter.html
- Oracle Java 17 Files: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html
- JUnit 5 @TempDir: https://docs.junit.org/5.11.4/user-guide/index.html#writing-tests-built-in-extensions-TempDirectory
- Logback Appenders: https://logback.qos.ch/manual/appenders.html
- Logback Configuration: https://logback.qos.ch/manual/configuration.html
- Apache Log4j 2 File Appenders: https://logging.apache.org/log4j/2.x/manual/appenders/file.html
- Apache Log4j 2 Rolling File: https://logging.apache.org/log4j/2.x/manual/appenders/rolling-file.html
- Apache Log4j 2 Async Logging: https://logging.apache.org/log4j/2.x/manual/async.html
- Spring Boot Logging: https://docs.spring.io/spring-boot/reference/features/logging.html
- OWASP Logging Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html
