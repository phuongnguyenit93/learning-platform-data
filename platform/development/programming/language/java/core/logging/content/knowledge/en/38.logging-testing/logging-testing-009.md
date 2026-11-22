# Testing Rotation in Java Logging: File Rollover, Retention, and Recovery

## 1. What Is Rotation and Why Test It?

**Log rotation** is the mechanism of switching from the currently active log file to a new file/generation when a **trigger condition** is met: size, time interval, or a combined policy. Older files can be retained, compressed, moved, or deleted according to a retention policy.

Example:

```text
Java application
    |
    v
Rolling appender / FileHandler
    |
    +--> logs/app.log                   (actively writing)
    +--> logs/archive/app.2026-11-10.0.log.gz
    +--> logs/archive/app.2026-11-10.1.log.gz
    +--> logs/archive/app.2026-11-09.0.log.gz
    |
    v
Collector / shipper -> centralized logging
```

**Testing rotation** is not just verifying that "a new file was created." A system can create files with the right names and still suffer from serious issues:

- Missing, duplicated, or out-of-order records during file rollover.
- Splitting a log event or stack trace at an invalid boundary.
- Retaining too many generations and filling up the disk, or deleting records too early.
- Compression or file transfer failing while the appender still reports normal status.
- After a restart, the appender overwriting old files or failing to resume from the right state.
- Multiple processes writing to the same path, causing locks, name collisions, or corrupted files.
- Insufficient write permissions, disk full, or rename failures going unmonitored by the application.
- The collector tracking by file name instead of file identity, causing missed or duplicated data.

Therefore, a good test must verify **triggers, file lifecycle, record integrity, retention, failure modes, and observability**, rather than merely seeing a `.1` or `.gz` suffix.

## 2. Distinguishing Rotation from Easily Confused Mechanisms

| Concept | Behavior | What Must Be Tested |
| --- | --- | --- |
| **Size-based rotation** | Switches file when size threshold is reached | Threshold, generations, bursts, long records |
| **Time-based rotation** | Switches file by day/hour/period | Time boundaries, timezone, DST, idle periods |
| **Size-and-time rotation** | Within a single period, multiple indexed files can be created | Both period and generation index |
| **Retention / cleanup** | Deletes or cleans up old files by count, age, or total size | Neither premature deletion nor unbounded retention |
| **Compression** | Compresses rolled-over files | Compressed file is readable, source is handled properly, job completes |
| **Log shipping** | Transfers files/events to a collector | No loss/duplication when files are renamed or truncated |
| **External logrotate** | OS/external tool outside the JVM renames or copies/truncates | Whether the appender reopens the file, whether collector offsets remain valid |
| **Truncation** | File content is truncated in place | Not necessarily a safe rotation |

**Do not equate file naming** with semantics. The JDK's `java.util.logging.FileHandler`, Logback's `RollingFileAppender`, and Log4j 2's `RollingFile` differ in configuration, rollover timing, retention, and compression capabilities. Tests must align with the **actual backend and version in use**.

## 3. Defining the Contract Before Testing

Before writing an assertion, you should explicitly specify:

1. **Backend:** JUL `FileHandler`, Logback Classic, Log4j 2, or container/gateway logging?
2. **Trigger:** file reaches x bytes, midnight date change, hourly/minutely period, or combined size + time?
3. **Active file:** fixed name `app.log` or a pattern with `%d`/`%i`/`%g`?
4. **Retention:** maximum number of generations, number of days, or total size cap?
5. **Compression:** `.gz`, `.zip`, or uncompressed? Synchronous or asynchronous compression?
6. **Continuation:** append mode on restart; whether history is cleaned on startup?
7. **Reliability:** what level of record loss is acceptable on process crash, disk full, or collector lag?
8. **Permissions:** does the application have permissions to create, rename, and delete files and the archive directory?
9. **Ordering:** is per-producer event ordering required, or only that each event appears once across the files?
10. **Environment:** Windows/Linux, local disk, network mount, container writable layer, shared volume?

Do not write tests based on vague assumptions like "the file will always be exactly 1 MB." Some appenders check the size **before writing the next event** or trigger rollover **after a record has already exceeded the threshold**, so the actual file may temporarily exceed the configured value. Size is measured in **bytes**, not Java character count; UTF-8, stack traces, formatters, and headers/footers all change the byte count.

### 3.1. Observable Properties

| Property | Useful Check |
| --- | --- |
| Rollover actually occurs | Two or more files/generations observed after writing enough events |
| Active file continues receiving logs | Latest marker appears in a valid file |
| Configured generation limit not exceeded | File count stays within the defined bound |
| Old data evicted on time | Oldest marker is gone once retention triggers |
| Data within retention window preserved | Latest marker and retained markers remain readable |
| No files held open unintentionally | Handler/appender can be closed and locks are released |
| Compression completes cleanly | Archive can be decompressed and read; temp files not mistaken for final archives |
| Safe restart | Existing file state is not truncated outside policy |
| Failures are visible | Status/metrics/alerts emitted when rename or write fails |
| Collector keeps up | Logs are ingested according to contract, not merely present on disk |

A single test does not have to cover everything. **Unit tests** verify algorithms/formatters, **integration tests** verify real files and the backend, and **end-to-end tests** verify collectors, restarts, and retention in a production-like environment.

## 4. Java 17: Automated Rotation Test for JUL FileHandler

This is a **standalone program for JDK 17+** that requires no Maven, SLF4J, Logback, or broker. It uses `java.util.logging.FileHandler` with:

- Pattern `events-%g.log`: `%g` is the **generation number**.
- File limit of **240 bytes** and **3 generations**.
- `append=false` so the fresh temporary directory starts from a clean state.
- A formatter that writes only the message and a newline, avoiding timestamps or stack traces that make tests nondeterministic.
- 36 markers `EVENT-001` through `EVENT-036` with payloads long enough to trigger multiple rollovers.
- Automated checks for file count, latest marker, expired oldest marker, and lock files after closing.

**Strength:** the program checks *invariants* rather than guessing the exact number of lines in each file. Exact byte-level rollover details may vary by formatter and backend, yet the test contract remains meaningful.

Save the file **`RotationVerificationDemo.java`**:

```java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Locale;
import java.util.stream.Stream;
import java.util.logging.FileHandler;
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class RotationVerificationDemo {
    private static final int LIMIT_BYTES = 240;
    private static final int GENERATIONS = 3;

    private static List<Path> listFiles(Path dir) throws Exception {
        try (Stream<Path> stream = Files.list(dir)) {
            return stream.toList();
        }
    }

    private static void require(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    public static void main(String[] args) throws Exception {
        Path dir = Files.createTempDirectory("jul-rotation-test-");
        try {
            Logger logger = Logger.getLogger(
                    "demo.rotation." + System.nanoTime());
            logger.setUseParentHandlers(false);
            logger.setLevel(Level.INFO);

            String pattern = dir.resolve("events-%g.log").toString();
            FileHandler handler = new FileHandler(
                    pattern, LIMIT_BYTES, GENERATIONS, false);
            handler.setLevel(Level.INFO);
            handler.setEncoding(StandardCharsets.UTF_8.name());
            handler.setFormatter(new Formatter() {
                @Override
                public String format(LogRecord record) {
                    return record.getMessage() + "\n";
                }
            });

            logger.addHandler(handler);
            try {
                for (int i = 1; i <= 36; i++) {
                    logger.info(String.format(
                            Locale.ROOT,
                            "EVENT-%03d-%s", i, "X".repeat(80)));
                }
                handler.flush();
            } finally {
                logger.removeHandler(handler);
                handler.close();
            }

            List<Path> items = listFiles(dir);
            List<Path> logs = items.stream()
                    .filter(p -> p.getFileName().toString()
                            .matches("events-[0-9]+\\.log"))
                    .toList();

            require(logs.size() >= 2 && logs.size() <= GENERATIONS,
                    "Unexpected number of log generations");

            StringBuilder allContent = new StringBuilder();
            for (Path logFile : logs) {
                allContent.append(Files.readString(
                        logFile, StandardCharsets.UTF_8));
            }
            String text = allContent.toString();

            require(text.contains("EVENT-036-"),
                    "Newest log event missing");
            require(!text.contains("EVENT-001-"),
                    "Expired oldest log event still retained");

            boolean lockExists = items.stream().anyMatch(p ->
                    p.getFileName().toString().endsWith(".lck"));
            require(!lockExists, "FileHandler lock still present");

            System.out.println("PASS: rotated within 3 generations");
            System.out.println("PASS: latest message found");
            System.out.println("PASS: oldest message expired");
            System.out.println("PASS: lock released");
        } finally {
            // Delete all test files without affecting real logs.
            for (Path file : listFiles(dir)) {
                Files.deleteIfExists(file);
            }
            Files.deleteIfExists(dir);
        }
    }
}
```

Run:

```bash
javac RotationVerificationDemo.java
java RotationVerificationDemo
```

**`stdout` output when all four assertions pass**:

```text
PASS: rotated within 3 generations
PASS: latest message found
PASS: oldest message expired
PASS: lock released
```

If an assertion fails, the program throws `AssertionError` and **must not be considered a PASS**. In case of filesystem/permission errors, the program may throw an exception; this is an environment or I/O error to investigate, not an alternative passing output.

### 4.1. Step-by-Step Explanation

1. `Files.createTempDirectory` creates an isolated directory for the test run. It has a random name that is not printed in the PASS lines, so output does not depend on the path.
2. A dedicated `Logger` is created and `setUseParentHandlers(false)` prevents extra messages from printing to the root logger console.
3. `FileHandler(pattern, limit, count, append)` is the JUL API; `count=3` keeps the number of generations per `FileHandler` semantics, not "keep three days."
4. `%g` gives each file its own generation number, such as `events-0.log`, `events-1.log`. The test does not assume the exact list of existing generations unnecessarily.
5. Each message has 80 `X` characters plus the identifier prefix. After 36 writes, the 240-byte limit is exceeded multiple times, guaranteeing that the test observes rotation.
6. `handler.flush()` and `handler.close()` complete the synchronous write path of the handler. `close` also releases the lock managed by `FileHandler`.
7. `Files.list(dir)` reads files only after the handler is closed; this avoids reading a file while it is still being written.
8. The test counts **only `.log` files matching the generation pattern**, excluding `.lck` or other files from retention checks.
9. `EVENT-036-` must still be present in the retained files, while `EVENT-001-` must have been evicted after many rotations.
10. The test verifies no `.lck` file remains after closing, then deletes the temporary directory in `finally`. Never use the real application's log folder.

**Important note:** This example only proves the asserted properties of **JUL FileHandler** in the runtime environment. It does not prove compression, time-based rotation, crash durability, total ordering across multiple producers, or complete collector ingestion.

### 4.2. Why Check Markers Instead of Counting Exactly 36 Lines?

Rotation has **finite retention**. After writing 36 events while keeping only three generations, many older events are **supposed to be deleted** by policy. An assertion like "count all 36 logs at the end of the test" would be wrong for this configuration.

If the goal is **zero event loss during a specific rollover**, run a separate test with sufficiently wide retention, unique marker IDs, and read all generated files **before cleanup deletes too many generations**. Only then should you compare the input ID set against the output ID set.

### 4.3. Practical Limitations of JUL FileHandler

`FileHandler` provides size-based rotation via `limit` and `count`; it is **not a time-based rolling policy**. Patterns can use `%g` (generation), `%u` (unique ID), `%t` (temporary directory), `%h` (home), along with JUL's naming resolution rules.

- File naming may append generation/unique suffixes if the pattern lacks appropriate variables.
- The `.lck` lock file is part of the mechanism to avoid name collisions across handlers/processes; tests must close the lifecycle properly.
- `FileHandler` does not provide compression or age-based retention like the rolling policies of Logback or Log4j 2.
- For non-ASCII text, file size is measured in **encoded bytes**, not `String.length()`.
- A single large event can push a file past the limit. Therefore, tests should not hard-assert that **every file is always <= limit bytes** in all cases.
- Behavior when multiple JVMs share the same pattern and lock file limits must be tested separately; do not treat `%u` as a guarantee of multi-process coordination across all filesystems.

## 5. Size-Based Rotation: Boundaries to Test

When the policy is "rotate file when size reaches threshold," test at least these cases:

| Case | How to Test | Expectation |
| --- | --- | --- |
| Below threshold | Write a few events of known size | No rollover before actual condition is met |
| Near threshold | Write up to just under the limit | Behavior matches backend trigger algorithm |
| Just over threshold | Write an event that pushes total size over limit | Rotation triggers per defined semantics |
| Very large single event | Write a message longer than limit | No silent failure; oversize handling follows rules |
| Multiple rollovers | Write enough events | New generations created, old policy applied |
| Empty file | Create appender, send no events | Do not assume an archive always exists |
| Flush/close | Write then close appender | Data flushed per handler contract |
| Multi-byte UTF-8 | Write Vietnamese characters/emoji | Byte-size measured and decoded with correct encoding |
| Header/footer | Use formatter with head/tail | Formatting bytes accounted for in calculations |
| Long stack trace | Log a `Throwable` with multiple causes/suppressed | Rollover/formatter does not corrupt the event |

### 5.1. Avoid Assumptions About Exact Rollover Timing

A backend may check the threshold:

- **Before** appending a new event;
- **After** writing an event that exceeds the threshold;
- When a flush/rollover task runs;
- When a new period arrives and **the next event is logged**.

Therefore, "a 1 MB file must be exactly 1,048,576 bytes" is a brittle assertion. Test the contract instead: rotation occurs under sufficient load, generation count is bounded, required data remains readable, and no I/O errors are swallowed.

In particular, never use `String.length()` as a proxy for file size. `String.length()` returns the number of UTF-16 code units, whereas `Files.size(path)` returns the byte count. Log lines also include newlines that may be one or two bytes depending on the formatter/platform.

## 6. Time-Based Rotation: Testing Date/Hour Boundaries

With a time-based policy, what matters is the **time period**, not just an epoch timestamp. For example, a daily pattern `app.%d{yyyy-MM-dd}.log` can rotate when crossing into a new day.

Test cases:

1. Write an event immediately **before the period boundary**.
2. Advance to the start of the next period using a **controlled clock/test fixture** when supported by the backend.
3. Write an event after the boundary.
4. Verify the archive for the old period and the file receiving events for the new period.
5. Verify timezone, retention, and restart policy when the application starts mid-period.

**Do not assume the system must rotate immediately at 00:00:00.** Many rolling appenders trigger rollover upon the **first logging event after the boundary**; a system with no logs at midnight may not produce an archive file for the new day until activity resumes.

### 6.1. Do Not Rely Solely on Long Sleeps

A test pattern like:

```text
write log -> sleep until 00:00 -> hope file is renamed -> assert
```

is slow and prone to flakiness due to schedulers, busy CI hosts, clock skew, DST, or asynchronous compression. Prefer:

- Testing the policy/clock abstraction with a **mock/injectable clock** if the backend version and API support it.
- Isolated integration tests with a **short period** in a dedicated environment, using timeouts and condition polling.
- Re-testing after a restart on a new day/period.
- Never changing the system clock on a shared CI machine to force rollover.

If the backend does not support deterministic time control via a public API, document that limitation clearly and use dedicated integration tests rather than claiming a fully deterministic unit test.

### 6.2. Timezone and DST

When using date-based filenames:

- Servers may run in UTC or local timezone.
- Changing the configured timezone can place a timestamp into a different day.
- DST causes some days to have 23 or 25 hours, and one local hour can occur twice.
- Containers and hosts may have different timezones.
- The collector may use UTC while filenames use local time.

A good test pins the expected timezone, identifies the time source, and checks date-transition logic. Avoid assuming "every day is always 24 hours" in regions with DST. For distributed systems, UTC for log timestamps usually makes reconciliation more reliable.

## 7. Size-and-Time Rolling: Combining Time and Index

Many production applications need to split archives by day while preventing any single file from growing too large. Example filenames:

```text
app.2026-11-10.0.log.gz
app.2026-11-10.1.log.gz
app.2026-11-10.2.log.gz
app.2026-11-11.0.log.gz
```

Two independent test conditions:

1. **Same period, sufficient data:** `%i` increments without overwriting previous archives.
2. **Crossing into a new period:** the period name changes and the index resets according to the backend's policy.

When a very large event arrives right at a period boundary, test the actual library's **time/size trigger order**. Do not infer from the pattern string that the processor always evaluates time-based before size-based.

When compression is enabled, the final `.gz` file may appear **after** rollover has begun. Distinguish the states: active file switched, archive compression started, archive compression completed. Tests should not treat seeing a `.gz` filename with an unstable size as proof of successful compression.

## 8. Retention: Deleting Properly Without Deleting Wrongly

**Retention** can be defined by generation count, number of historical periods, total bytes, or a combination of these.

Examples:

- JUL `FileHandler(count=3)`: at most three generations per FileHandler semantics.
- Logback `maxHistory=7` with daily rolling: keeps roughly **seven historical periods**, not always seven files; each day can have multiple `%i` files.
- Logback `totalSizeCap`: caps total archive size managed by the rolling policy's cleanup logic, not "each individual file stays under the cap."
- Log4j 2 `DefaultRolloverStrategy max=...`: limits the index/rollover count per its strategy and file pattern; **it is not automatically a global age-based deletion policy across all days**.

### 8.1. Retention Test Matrix

| Test | Goal |
| --- | --- |
| Insufficient history | Archives still within the allowed window are not deleted |
| Exceeding generation count | Oldest generation is rotated/evicted per policy |
| Exceeding `maxHistory` | Only eligible periods are deleted; correct timezone applied |
| Exceeding total archive size | Cleanup runs under the right conditions, possibly asynchronously |
| Startup with many old archives | `cleanHistoryOnStart` or equivalent policy is respected |
| Multiple restarts | Valid data is not deleted and expired files are not kept forever |
| Directory contains unrelated files | Files not matching the rolling pattern are not deleted |
| Archive currently read by collector | Data not yet ingested is not lost per design |
| Changing naming pattern | Do not assume old archives are still cleaned up by the new policy |
| File permissions / read-only | Delete/rename failures are detected |
| Incomplete compression | Retention does not leave half-compressed files as valid final archives |

**Important:** historical file cleanup may be triggered **after rollover or at startup**, and may run asynchronously. Tests should **wait for a condition within a finite timeout** instead of asserting immediately after a log call if the backend does not guarantee synchronous cleanup.

### 8.2. Do Not Confuse Retention Testing with Lossless Delivery

When retention intentionally deletes old files, missing older markers **are not a bug**. Split this into two separate tests:

- **Integrity during rollover:** set retention wide enough, verify no events are lost during file switching.
- **Retention behavior:** intentionally exceed the limit, then verify that **the expected old data is deleted**.

Combining both and asserting "all logs from the start of the test must still exist" contradicts a finite retention configuration.

## 9. Compression: Looking Beyond the `.gz` Extension

For gzip-compressed archives, verify:

1. Rollover creates archives named according to the pattern.
2. The compression job finishes within a reasonable timeout.
3. The archive file is valid gzip format and **can be decompressed and read**.
4. The decompressed content contains the expected markers.
5. No temporary/partial output files remain per policy after completion.
6. Compression does not abnormally stall writes to the active file.
7. Cleanup does not mistakenly delete an archive being compressed or still within retention.
8. Compression speed, CPU, and I/O meet real-world load requirements.

Example commands to inspect a gzip archive in an environment with `gzip` installed:

```bash
gzip -t logs/archive/app.2026-11-10.0.log.gz
gzip -cd logs/archive/app.2026-11-10.0.log.gz
```

These are **illustrative commands**, not a guarantee that the file exists. `gzip -t` checks gzip structure/CRC, while `gzip -cd` lets you inspect the decompressed data. On Windows or CI images without `gzip`, you can use **`java.util.zip.GZIPInputStream`** to verify in Java.

Note that compression usually makes archives **smaller than raw**, but with very small or incompressible data, the compressed size can be slightly larger than the input. Do not assert "gzip file is always smaller than raw" as an absolute correctness condition.

## 10. Example Logback Configuration for Integration Testing

For an application with **SLF4J + Logback Classic** dependencies already present, you can use a **test-specific configuration** without touching production log directories.

Example `src/test/resources/logback-test.xml`:

```xml
<configuration>
    <appender name="ROLLING"
              class="ch.qos.logback.core.rolling.RollingFileAppender">
        <file>build/test-logs/app.log</file>
        <rollingPolicy
            class="ch.qos.logback.core.rolling.SizeAndTimeBasedRollingPolicy">
            <fileNamePattern>build/test-logs/archive/app.%d{yyyy-MM-dd}.%i.log.gz</fileNamePattern>
            <maxFileSize>1MB</maxFileSize>
            <maxHistory>3</maxHistory>
            <totalSizeCap>10MB</totalSizeCap>
            <cleanHistoryOnStart>true</cleanHistoryOnStart>
        </rollingPolicy>
        <encoder>
            <pattern>%d{HH:mm:ss.SSS} %-5level %logger - %msg%n</pattern>
            <charset>UTF-8</charset>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="ROLLING"/>
    </root>
</configuration>
```

This is an **integration configuration**, not standalone JDK code. The `build/test-logs` directory is only an illustrative path: Gradle typically uses `build`, while Maven may use `target`; CI tests should use a **dedicated temporary directory per run** and pass properties into the configuration instead of letting multiple tests share one path.

Meaning:

- `RollingFileAppender` writes to `build/test-logs/app.log` while active.
- `SizeAndTimeBasedRollingPolicy` configures a pattern containing both `%d` and `%i`.
- `maxFileSize=1MB` triggers size-based rotation per the version's policy.
- `maxHistory=3` limits **three historical periods** (if daily, roughly three days), not a maximum of three archive files.
- `totalSizeCap=10MB` sets a cap on total archive history when cleanup runs, not per file.
- `cleanHistoryOnStart=true` allows deleting old archives when the appender starts according to policy.

**Avoid testing directly on production configurations.** Retention or `cleanHistoryOnStart` can delete real archives. Never put test files in shared directories or rely on the host date if tests must be deterministic.

### 10.1. Logback Integration Test Flow

A solid test should:

1. Create a new temp directory and configure the appender to point there.
2. Enable a simple pattern or format with a **unique marker** per event.
3. Write enough logs to trigger size rollover within the same period.
4. Close/stop the `LoggerContext` or appender under test per framework lifecycle.
5. Inspect archives and the active file after completion; if compression is async, poll the condition with a timeout.
6. Decompress archives and verify markers/encoding.
7. Restart with the same directory to test append/retention.
8. Verify that logging backend metrics/status report no errors.
9. Clean up **only** the test directory after all appenders are closed.

In Logback, tests can leverage internal test/clock APIs appropriate for the version, but avoid writing unit tests coupled to internal classes that may change; prefer contract tests on actual file output.

## 11. Log4j 2 RollingFile: Policies and Testing

For an application using **Log4j 2**, an illustrative configuration:

```xml
<Configuration status="WARN">
    <Appenders>
        <RollingFile name="ROLLING"
                     fileName="build/test-logs/app.log"
                     filePattern="build/test-logs/archive/app-%d{yyyy-MM-dd}-%i.log.gz">
            <PatternLayout pattern="%d{ISO8601} %-5p %c - %m%n"/>
            <Policies>
                <TimeBasedTriggeringPolicy interval="1" modulate="true"/>
                <SizeBasedTriggeringPolicy size="1 MB"/>
            </Policies>
            <DefaultRolloverStrategy max="10"/>
        </RollingFile>
    </Appenders>

    <Loggers>
        <Root level="info">
            <AppenderRef ref="ROLLING"/>
        </Root>
    </Loggers>
</Configuration>
```

This is a test configuration requiring compatible Log4j 2 dependencies, **not Logback XML**. Attributes like `max`, `interval`, `modulate`, and index ordering must be evaluated against the exact version in use.

Key test points:

- Does it trigger rollover on size and time boundaries?
- Does the file pattern create distinct generations without unintended overwrites?
- How does the strategy bound the files/indices it manages?
- Does compression complete and produce readable archives?
- When **global age-based archive retention** is needed, is an appropriate `Delete` action/retention configured?
- Does shutdown/reconfiguration wait for in-flight work to finish?
- Are errors reported via the Log4j 2 status logger or monitor when the file is not writable?

**Do not conclude that `DefaultRolloverStrategy max="10"` means "total archives across all days on disk will never exceed 10 files."** This retention behavior depends on the file pattern, rollover strategy, delete conditions, and environment.

## 12. Testing Rotation Across Restarts, Crashes, and Config Changes

A Java application restarting may reopen the same active filename or continue a generation. Important cases:

| Scenario | What to Verify |
| --- | --- |
| Graceful stop after writing | Appender flushes/closes, locks are released |
| Restart when active file is not full | Appends or replaces per configuration, nothing unexpected |
| Restart when file is nearly full | Rolls over properly on the next event |
| Unexpected crash/kill | Bounded data loss per contract; do not assume shutdown hooks run |
| Directory has old archives | Startup does not mistakenly delete valid files |
| `fileNamePattern` changed | Cleanup and file enumeration handle old/new naming per policy |
| File size limit changed | Rollover after restart is interpreted correctly |
| Retention changed | Old archives are kept/deleted per updated policy |
| Timezone changed | Archive period classification is not miscalculated |
| Encoding changed | Collector can still read both old and new files |
| Log level changed | Write rate and rotation triggers adjust accordingly |
| Rolling appender fails to close | App still reports the issue via an independent monitoring path |

**A successful shutdown does not prove durable logging.** `flush()` typically moves data from application buffers to the underlying I/O layer, but does not automatically mean data is durably `fsync`ed to storage. If strict audit persistence is required, design dedicated durability/acknowledgment mechanisms instead of treating rotation as a transactional guarantee.

### 12.1. Testing a Retention Policy Change

When reducing retention from 30 days to 7 days, cleanup may run after rollover or at startup depending on the library. Tests should create **fixture files matching the pattern and timestamps**, trigger cleanup via documented APIs, and poll with a timeout if asynchronous. Do not just change the system clock or file `lastModifiedTime` assuming the policy relies on that attribute: many rolling implementations infer the period from the **filename**.

## 13. Concurrency: Multi-Threading and Multi-Process

A Java application has dozens of threads logging concurrently. Test:

1. Multiple threads writing distinct markers simultaneously.
2. Rollover occurring during a heavy burst.
3. No exceptions from rename/close while other threads are writing.
4. No encoding corruption or message truncation outside formatter limits.
5. Retained markers remain readable, and file count stays within policy after the appender settles.
6. Per-producer ordering if required by the application, while **not assuming global ordering** across threads.
7. With async loggers, wait for the queue to drain before comparing results.
8. Measure p95/p99 producer latency during rollover/compression, as file operations can introduce latency spikes.

**Multi-process** is a different problem. Two JVMs opening the same file path can collide on locks, contend on renames, or rotate independently without coordination. JUL `FileHandler` has locks/`%u`, but that cannot be used as a promise that multiple backends or multiple processes sharing a `RollingFileAppender` will operate safely.

Practical recommendation: have **each process/container write to its own stream** and ship to a collector, or use a multi-process mechanism explicitly supported and verified by the backend. Test on the **exact target OS and filesystem**; Windows has different open-file locking/rename semantics than POSIX.

## 14. External Logrotate: Rename/Reopen and Copytruncate

When a tool outside the JVM rotates logs, the internal appender may not notice immediately:

### 14.1. Rename + Create New File

```text
app.log -> app.log.1
create new app.log
```

A process still holding the old file descriptor may keep writing to the renamed file instead of the new one. If the backend does not support reopen or reconfiguration, tests must detect that the new `app.log` is not receiving log lines as expected.

### 14.2. Copytruncate

```text
copy app.log to app.log.1
truncate app.log in place
```

Between the copy and truncate steps, the process can write more data; some bytes/log events may be **lost or duplicated**. Never claim copytruncate is lossless rotation.

### 14.3. Avoid Two Owners of Rotation

If Logback `RollingFileAppender` **already rotates by policy** while the OS also runs `logrotate` on the same active file, the two mechanisms can collide. An end-to-end test must establish a clear rotation owner: **the JVM** or **an external agent**. Never run both without explicit coordination.

In containers, best practice is often for the application to write to `stdout/stderr` and let the platform manage capture/rotation. In that case, rotation testing belongs at the **container runtime/collector** layer rather than adding a `RollingFileAppender` inside the Java app.

## 15. Collectors and Rotation: Testing Zero Loss and No Duplicates

An application-level test can PASS while end-to-end observability still fails if the shipper:

- Tracks by file path instead of inode/file identity and misses data after rename.
- Reads the new file from the old offset.
- Falls behind and fails to read an archive before retention deletes it.
- Re-reads duplicates on process restart or lost offset state.
- Fails to parse multiline stack traces or JSON lines properly.
- Handles compressed or renamed files differently from its configuration.
- Cannot distinguish data with identical timestamps from multiple JVMs.

Production-like test:

```text
Java producer: emits marker ID 1..N
   -> RollingFile / FileHandler
   -> Log shipper
   -> Collector
   -> Search storage

Compare produced IDs, archived file IDs, ingested IDs,
duplicates, missing IDs and ingestion lag.
```

Use a test run with **wide enough retention** so history deletion does not intentionally drop markers. Check both the **logical ID** count and duplicate count during shipper retries. Events may be delivered **at-least-once** to the collector, producing duplicates; if exact counts are required, appropriate keys/deduplication are necessary.

**Do not use local file existence as proof that logs reached centralized logging.** Rotation and shipping are two distinct stages.

## 16. Environmental Faults to Inject in Tests

| Fault Injection | Detection and Handling Expectation |
| --- | --- |
| Log directory missing or not writable | Appender fails visibly or fails over per policy |
| Filesystem full | Warning/metric emitted; does not keep claiming writes succeeded |
| Rename rejected due to file lock | Reported; valid archives are not deleted |
| Compression failure | Error status reported; corrupted archive not treated as complete |
| Path too long or invalid | Configuration validated and error detected |
| Very slow disk I/O | Impact on producer latency and async queue is observable |
| Out of inodes / quota | Distinguished from free disk bytes |
| Collector disconnected | Backlog size, lost/duplicate counts, and recovery time measured |
| Process forcefully killed | Event loss before flush evaluated; no drain expected |
| Clock/timezone changed | Period naming and retention behave without surprises |
| Permissions changed at runtime | Known when permission re-checks are needed |
| Archive directory full separately | Do not assume active file and archive share the same filesystem |

Run these fault-injection cases in an **isolated test environment** with dedicated directories. Never use a production disk to simulate disk-full, and never alter permissions or clocks on a shared host.

## 17. Writing Reliable Tests in CI

Practices to reduce flaky tests:

- Use a dedicated directory per test (`@TempDir` in JUnit 5 or `Files.createTempDirectory`).
- Use unique path patterns so parallel tests do not collide on files.
- Write simple markers with deterministic IDs, independent of text timestamps or thread scheduling.
- Wait for the appender/handler to finish **before reading files**.
- For async compression and cleanup, **poll the condition with a timeout** rather than `Thread.sleep(100)` and hoping it finished.
- Prevent resource leaks with `try/finally` or `try-with-resources` for streams/readers.
- Count the exact target file set (archives, active, lock, tmp) instead of `Files.list(dir).count()` over everything.
- Keep tests independent of OS file listing order; sort when presenting.
- Measure size with `Files.size`, not `String.length`.
- Document backend version, default charset, timezone, and lifecycle assumptions.
- Assert against the **contract** rather than random filenames or millisecond-exact timestamps.
- Never place test logs in the same directory as real application logs; clean up files after closing handlers.

With JUnit 5, you can replace the `require(...)` helper with `assertTrue`/`assertFalse`, receive the directory from `@TempDir`, and run setup/teardown around each test. However, when using Logback/Log4j 2, create a dedicated test configuration and initialize/stop the logger context properly; **do not call `LogManager.reset()` arbitrarily** in a test suite where other loggers share the global context.

### 17.1. Testing Timeouts for Asynchronous Work

Example pseudo-code for condition polling:

```text
deadline = now_monotonic + timeout
while now_monotonic < deadline:
    if archive_ready_and_valid():
        PASS
    sleep_short_interval()
FAIL with useful diagnostics: observed files, sizes, backend status
```

This is **pseudocode**, not runnable Java. Use a **monotonic clock** for timeouts (such as `System.nanoTime()`) instead of wall-clock time, because timezone/NTP adjustments can skew wait durations. Timeouts must be finite to avoid hanging CI when rollover/compression never happens.

## 18. Monitoring to Verify Rotation in Operations

You should not discover a rotation failure for the first time when the disk fills up. Recommended signals:

| Signal | Meaning |
| --- | --- |
| Total active and archive log bytes | Tracks growth |
| File count in archive directory | Detects when retention is not running |
| Time since last rollover | Detects active logging without expected rotation |
| File open/write/rename/delete errors | Reports I/O and permission issues |
| Compression errors / invalid archives | Detects unusable files |
| Rollover/compression duration | Measures latency and CPU/I/O spikes |
| Logging queue depth / dropped events | Tracks impact when sink stalls |
| Shipper lag / ingestion lag | Shows whether the collector keeps up with archives |
| Disk usage / inode usage | Early warning before resource exhaustion |
| Restart count and config version | Correlates rotation incidents with deployments/config |

This is a **recommended set of signals**, not default metrics in every backend. Internal appender error notifications may be routed through a status logger, `StatusManager`, or management endpoint depending on the library. If the primary sink fails, logging `ERROR rotation failed` only to **that same sink** can lose the alert; use an appropriate out-of-band monitoring channel.

## 19. Common Mistakes

### 19.1. Testing Only the Filename

Checking `Files.exists("app.1.log")` does not prove the file has valid content, that the active file still receives data, or that archives were not deleted improperly.

### 19.2. Comparing `Files.size` to an Exact Byte Limit

Rollover can trigger before or after writing an event depending on the implementation; a single event can exceed the limit. Test triggers, retention, and markers instead of exact byte counts not guaranteed by the contract.

### 19.3. Using `Thread.sleep` to Cross Midnight

CI clocks/schedulers can vary; long sleeps make tests slow and flaky. Use a clock abstraction/harness when available, or an integration test with timeouts.

### 19.4. Counting `.gz` Archives Immediately After Writing

Compression may be asynchronous. A file not yet present or still being created does not prove failure. Poll with a timeout, then verify decompression and backend status.

### 19.5. Assuming `maxHistory=7` Always Means at Most 7 Files

In time-based rolling, it usually means **historical periods**. With size-and-time rolling, a single period can have multiple archives.

### 19.6. Reading Open Files and Concluding Data Is Missing

The handler may still be buffering, compression may be incomplete, or flushing may not have happened. Read after proper lifecycle completion, not at an arbitrary moment.

### 19.7. Sharing a Log Directory Between Tests and the Real App

Test retention/cleanup can delete real files. Always isolate test paths.

### 19.8. Skipping Restart Tests

An appender may rotate fine in a single run but overwrite archives or fail locking after a restart. Test both graceful and abrupt termination per contract.

### 19.9. Using Two Rotation Mechanisms on the Same File

Concurrent internal rolling and external logrotate can collide on rename/truncate. Assign clear ownership and test end-to-end.

### 19.10. Claiming Rotation Guarantees Zero Log Loss

Rotation is a file management policy; it **does not turn logging into durable transactions**, does not guarantee collector delivery, and does not prevent data loss on crashes or full async queues.

## 20. Rotation Testing Checklist

- [ ] Identify backend, version, file pattern, size/time triggers, retention, and compression.
- [ ] Use an isolated temp directory without touching production logs.
- [ ] Include unique markers per event and define integrity checks.
- [ ] Test below threshold, near threshold, over threshold, very large events, and Unicode/UTF-8.
- [ ] Verify the active file continues receiving logs after rollover.
- [ ] Count generations accurately without counting lock/tmp files as archives.
- [ ] Test retention by **count, period, and totalSizeCap** where applicable.
- [ ] Test archive compression by actually reading/decompressing, with a timeout for async jobs.
- [ ] Test time boundaries, timezone/DST, and scenarios with no events across the boundary.
- [ ] Test restart/append/crash and configuration version changes.
- [ ] Test multi-threading and avoid sharing files across multiple processes unless supported.
- [ ] If using external logrotate, test reopen behavior and copytruncate risks.
- [ ] Test collector ingestion, lag, missing/duplicate IDs, and sufficient retention for shipping.
- [ ] Fault injection: file lock, disk full, permissions, rename/compression failures.
- [ ] Control CI flakiness: temp dirs, deterministic markers, polling timeouts, closed resources.
- [ ] Monitor disk usage, errors, queue depth/drops, and status loggers independently.
- [ ] For mandatory audit logs, add separate durability and retention requirements.

**Conclusion:** Testing rotation in Java logging is about verifying **file lifecycle and data correctness across rollovers**. A strong test does not stop at "the file was renamed," but confirms that new markers are present, old data expires per policy, locks are released, compression/collectors do not lose data, and I/O errors are surfaced. Use **Java 17 FileHandler** to learn size/generation mechanics, then test against the **actual Logback/Log4j 2 setup and target deployment environment** when dealing with time-based rolling, compression, and complex retention.
