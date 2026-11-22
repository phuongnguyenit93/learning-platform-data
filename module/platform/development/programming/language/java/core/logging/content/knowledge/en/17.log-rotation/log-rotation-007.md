# Synchronizing Rotation in Java Logging

## 1. What Is Synchronizing Rotation?

**Log rotation (log rollover)** is the process of moving the active log file being written to an archive file and opening or continuing a current file, typically when a size threshold is reached, across a time boundary, or at startup. **Synchronizing rotation** means ensuring that the parties involved in writing logs and rotating files do not concurrently perform conflicting steps that cause records to be lost, duplicated, written to the wrong file, or left in a corrupted state.

For example, a Java service uses:

```text
logs/application.log          # active file being written
logs/application.log.1        # most recently rotated file
logs/application.log.2        # older file
```

If two threads both see that `application.log` is full and both try to rename it, the result can be wrong:

```text
Thread A: checks size -> rotation needed
Thread B: checks size -> rotation needed
Thread A: renames application.log to application.log.1
Thread B: renames application.log to application.log.1 (the old file was already renamed)
Thread A: opens a new application.log file
Thread B: writes using the old handle or opens a different file
```

This is a **race condition**: the outcome depends on the interleaving order of operations. The issue is not only that two log lines might appear out of order; it is also that **the rotation decision, file operations, and switching writers to the new file must be coordinated properly**.

An implementation must clarify the **synchronization scope**:

1. Multiple threads within **a single JVM process**, sharing one logging manager.
2. Multiple loggers/appenders or multiple logger contexts **within the same JVM**.
3. Two or more **independent JVMs/processes** writing to the same file path.
4. An application alongside an **external rotation tool**, such as `logrotate` on Linux.
5. Multiple containers/pods sharing the same **volume or network filesystem**.
6. A log shipper/collector reading a file while it is being renamed, compressed, or deleted.

**`synchronized` in Java only solves coordination between threads using the same monitor within one JVM.** It does not automatically protect resources from another JVM, the `logrotate` tool, or external actors.

## 2. Invariants to Protect

A good rotation workflow should uphold the following properties, within its designed guarantee scope:

| Invariant | Meaning |
| --- | --- |
| **One rollover decision per boundary** | Two actors do not rotate the same file state without awareness of each other |
| **A clear write order within the protected scope** | Records are serialized validly and are not interleaved at dangerous points |
| **No unintended writes to the wrong file** | Writers must open/rebind the appropriate handle when the active file is replaced |
| **No archive name collisions** | Important archives are not accidentally overwritten by two concurrent rotations |
| **Retention does not delete data still in use** | Archives that a writer or collector still depends on and has not processed are not compressed/deleted |
| **No unintended duplicate output** | A single event does not become two records merely due to appender/collector configuration |
| **Errors are detected and have a policy** | If rename, open, compress, or flush fails, the system is not silently treated as safe |
| **Clear scope of guarantees** | Do not claim "zero log loss" without durable write mechanisms and full acknowledgments |

In a single-JVM exercise, you can test that "12 events are saved as exactly 12 distinct lines." In a distributed system, a requirement of "zero log loss even on crash" also involves durable queues, flush/fsync, storage, collector acknowledgments, and recovery strategies; **a mutex or `synchronized` alone cannot solve this**.

### Rotation Is a Stateful Sequence of Operations

```text
Receive new event
      |
      v
Check policy (size/time)
      |
      +--- below threshold ----> write to active file
      |
      +--- threshold reached --> acquire rotation coordination lock
                                  |
                                  v
                         flush/close or swap handle
                                  |
                                  v
                         archive/rename old file
                                  |
                                  v
                         open/set new active file
                                  |
                                  v
                         write next event
                                  |
                                  v
                         allow other writers to continue
```

The exact implementation depends on the framework. Not every appender necessarily closes the file before every operation or performs compression synchronously; some use a manager and asynchronous compression tasks. What matters is that **steps that can conflict must be coordinated**, while post-processing operations can be decoupled if the framework ensures sufficient safety.

## 3. Common Race Conditions When Multiple Threads Write

Suppose each thread checks the file size as follows:

```java
// Illustrates the wrong idea only; not a standalone program.
if (Files.size(logFile) >= limitBytes) {
    rotate(logFile);
}
append(logFile, message);
```

This code has multiple problems:

- **Check-then-act race:** after thread A measures the size, thread B may have already written or rotated.
- **Unsynchronized renaming:** two threads may both move the file to the same archive name.
- **Internal state drift:** line counters, byte counters, and archive indices may no longer match the actual file.
- **Writing while the file is changing:** the old file handle still points to the old file object on some platforms; on others, renaming may be rejected because the file is still open.
- **Threshold overshoot:** two threads checking concurrently before appending cause the file size to far exceed the intended limit.
- **Lost error information:** if the code merely logs an exception during rotation without a recovery strategy, the system may continue writing to the wrong destination.

In Java, `volatile boolean rotating` is **not enough** to make the entire check–rotate–write sequence an atomic operation. `volatile` provides certain visibility/ordering guarantees for a variable, not a critical section across multiple file operations.

Using a **shared monitor**, a `Lock`, or a logging manager with proper internal synchronization is the solution within **a single process**. In practice, **you should not write a custom rolling logger from scratch when Log4j2/Logback already provides a suitable rolling appender**.

## 4. Single-JVM Scope: Share a Manager Instead of Rotating Per Logger

In an application using a logging framework:

```text
HTTP thread A ----\
HTTP thread B -----+--> Shared Rolling Appender/Manager --> active log file
Worker thread C --/
```

A shared appender/manager can decide how to serialize events and coordinate rollovers according to the library's design. This is fundamentally different from three threads each writing their own independent `Files.move(...)` code.

Recommended practices:

1. Configure appenders **once at startup**, then let class loggers use them.
2. Let the framework manage policies, file renaming, buffering, open resources, and shutdown lifecycle.
3. Do not call `new FileHandler` / `new RollingFileAppender` **per request**.
4. Do not let multiple modules choose the same `fileName` with different `filePattern` or retention settings without understanding manager sharing rules.
5. Do not synchronize on an arbitrary application object and assume every other logger in the JVM uses that same monitor.
6. Define behavior clearly during application shutdown or rolling reconfiguration, avoiding two generations of appenders actively managing the same path at once.

For Log4j2, the Rolling File Appenders documentation states that appenders with the same `fileName` (or the same `filePattern` when `fileName` is omitted) **can share a `RollingFileManager`** within an appropriately managed runtime scope. Sharing the same manager avoids duplicate rollovers **within that manager-sharing scope**, but it is **not a distributed lock across multiple JVMs**.

When multiple independent managers write to the same file, Log4j2 may calculate size inaccurately because it relies on the data each manager has written, rather than continuously measuring all writes from other processes. This is why you should not assume that two JVMs using the same `filePattern` will coordinate rotation safely.

## 5. Runnable Java 17+ Example: Synchronizing Rotation Between Two Threads

To demonstrate the principle without framework dependencies, the following program illustrates **a single shared writer** with a `synchronized append` method. The writer maintains an active file and two archive files, rotating every **4 lines**. Two threads concurrently write **6 records** each to the single writer. The example intentionally rotates by **line count** (easy to verify) rather than size or timestamp.

**Important limitation:** this is an **educational single-JVM model**, not a complete rolling appender or production solution. It opens and closes the file on each append for simplicity, and has no handling for power loss, disk full, multi-process locking, compression, collectors, async queues, or access permissions.

Save the entire code to **`SynchronizedRotationDemo.java`**:

```java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.nio.file.StandardOpenOption;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public final class SynchronizedRotationDemo {
    private static final int MAX_LINES = 4;

    private SynchronizedRotationDemo() {
    }

    private static final class RollingWriter {
        private final Path active;
        private int linesInActive;
        private int rollovers;

        private RollingWriter(Path active) {
            this.active = active;
        }

        synchronized void append(String record) throws IOException {
            if (linesInActive == MAX_LINES) {
                rotate();
            }

            Files.writeString(active, record + "\n",
                    StandardCharsets.UTF_8,
                    StandardOpenOption.CREATE,
                    StandardOpenOption.APPEND);
            linesInActive++;
        }

        private void rotate() throws IOException {
            Path first = active.resolveSibling("app.log.1");
            Path second = active.resolveSibling("app.log.2");

            Files.deleteIfExists(second);
            if (Files.exists(first)) {
                Files.move(first, second,
                        StandardCopyOption.REPLACE_EXISTING);
            }
            if (Files.exists(active)) {
                Files.move(active, first,
                        StandardCopyOption.REPLACE_EXISTING);
            }

            linesInActive = 0;
            rollovers++;
        }

        synchronized int rollovers() {
            return rollovers;
        }
    }

    private static void writeSix(
            RollingWriter writer, String prefix) {
        for (int i = 1; i <= 6; i++) {
            try {
                writer.append(prefix + "-" + i);
            } catch (IOException e) {
                throw new UncheckedIOException(e);
            }
        }
    }

    public static void main(String[] args) throws Exception {
        Path directory = Files.createTempDirectory("rotation-lab-");

        try {
            RollingWriter writer =
                    new RollingWriter(directory.resolve("app.log"));
            ExecutorService pool = Executors.newFixedThreadPool(2);

            try {
                Future<?> first =
                        pool.submit(() -> writeSix(writer, "A"));
                Future<?> second =
                        pool.submit(() -> writeSix(writer, "B"));

                first.get();
                second.get();
            } finally {
                pool.shutdownNow();
            }

            List<String> observed = new ArrayList<>();
            for (String name : List.of(
                    "app.log.2", "app.log.1", "app.log")) {
                observed.addAll(Files.readAllLines(
                        directory.resolve(name),
                        StandardCharsets.UTF_8));
            }

            Set<String> expected = new HashSet<>();
            for (int i = 1; i <= 6; i++) {
                expected.add("A-" + i);
                expected.add("B-" + i);
            }

            Set<String> distinct = new HashSet<>(observed);
            boolean verified =
                    observed.size() == 12
                    && distinct.equals(expected)
                    && writer.rollovers() == 2;

            System.out.println("records=" + observed.size());
            System.out.println("unique=" + distinct.size());
            System.out.println("rollovers=" + writer.rollovers());
            System.out.println("verified=" + verified);
        } finally {
            for (String name : List.of(
                    "app.log.2", "app.log.1", "app.log")) {
                Files.deleteIfExists(directory.resolve(name));
            }
            Files.deleteIfExists(directory);
        }
    }
}
```

Compile and run with **JDK 17+**:

```bash
javac -encoding UTF-8 SynchronizedRotationDemo.java
java SynchronizedRotationDemo
```

**Exact stdout when file read/write succeeds:**

```text
records=12
unique=12
rollovers=2
verified=true
```

**Stderr:** no output from the program when there are no errors.

### Why Is the Result Deterministic Even Though Two Threads Run in Non-Deterministic Order?

- Thread A produces `A-1` through `A-6`; thread B produces `B-1` through `B-6`.
- The **interleaving order between A and B is not fixed** due to the JVM scheduler, but each record is still written **once** because each thread loops exactly 6 times.
- Both threads share **the same `RollingWriter` object**.
- The `synchronized append` method holds the same monitor while **checking the threshold, rotating, and writing**. Therefore, the other thread cannot enter `append` in the middle of that sequence.
- After 4 records, the 5th event triggers the first rollover; after 8 records, the 9th event triggers the second rollover; at the end, there are two archives and the active file.
- The program reads `app.log.2`, `app.log.1`, and `app.log` without caring which record ended up in which file.
- The `Set` verifies that all 12 expected IDs are present. Combining this with `observed.size() == 12` detects both missing IDs and duplicate lines.
- `Future.get()` waits for both tasks to complete and surfaces any exception thrown by a task; verification only runs afterward.
- Files are placed in a **dedicated temporary directory** and deleted after verification; the program never touches production logs.

### Limitations of the Demo

`synchronized` only protects the monitor of **this writer within this JVM**. If you create **two separate `RollingWriter` instances** pointing to the same `app.log`, each object has its own lock and they are not coordinated. If you run **two JVMs**, `synchronized` in JVM A has no effect on JVM B.

Furthermore, the `delete/move/move` operations are separate steps. `Files.move` does not turn **the entire rotation sequence** into an atomic filesystem transaction. If an error occurs midway or the process crashes, the archive state may be incomplete. The program also does not attempt `ATOMIC_MOVE` because support and semantics vary by filesystem. In production, use a logging framework, configure safe retention, and use appropriate durable storage paths.

## 6. Log4j2: RollingFileAppender and Rollover Coordination

**Apache Log4j 2** provides `RollingFileAppender` and `RollingRandomAccessFileAppender`. They combine:

- **Appender/manager:** holds file resources and performs writes.
- **TriggeringPolicy:** decides **when** a rollover is needed based on size, time, or startup.
- **RolloverStrategy:** decides **how to move files**, archive names, archive count, compression, and cleanup.
- **Layout:** formats each `LogEvent` before writing.

Example **`log4j2.xml`** in `src/main/resources`, using an active file and archives by date/index:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<Configuration status="WARN">
    <Appenders>
        <RollingFile name="ROLLING"
                     fileName="logs/application.log"
                     filePattern="logs/application-%d{yyyy-MM-dd}-%i.log.gz"
                     append="true">
            <PatternLayout charset="UTF-8"
                    pattern="%d{ISO8601} %-5p %c{1} - %m%n%ex"/>
            <Policies>
                <SizeBasedTriggeringPolicy size="10 MB"/>
                <TimeBasedTriggeringPolicy interval="1"
                                           modulate="true"/>
            </Policies>
            <DefaultRolloverStrategy max="7"/>
        </RollingFile>
    </Appenders>
    <Loggers>
        <Root level="INFO">
            <AppenderRef ref="ROLLING"/>
        </Root>
    </Loggers>
</Configuration>
```

This configuration illustrates **a single Logging Manager** receiving events from loggers across an application, without requiring callers to lock files at every `LOG.info` call site.

**Notes on `filePattern`:**

- `%d{yyyy-MM-dd}` stamps the archive's time period, suitable when using a time-based policy.
- `%i` allows **multiple archives within the same time period** when the size policy triggers multiple times. Omitting `%i` in a size+time configuration can cause target name collisions and risk overwriting files.
- `max="7"` is the maximum archive index count for the strategy, **not automatically equivalent to "keep 7 days of logs"** when each day can produce multiple archives. Retention by days or total size must be designed explicitly.
- `TimeBasedTriggeringPolicy` is typically evaluated when a `LogEvent` enters the rolling path; you should not assume a timer will always rotate the file at exactly 00:00 when no logs arrive. `CronTriggeringPolicy` uses a different scheduling mechanism and may place logs near a schedule boundary into an adjacent period's file.
- **Do not enable two different time-based policies simultaneously** without checking the documentation; Log4j2 warns of undefined results when combining Cron and TimeBased policies.

### Scoped Synchronization in Log4j2

Apache's documentation states that appenders with the same active file name in an environment that shares `RollingFileManager` appropriately can use the same manager, avoiding duplicate rollovers **within the manager's scope**. However, you must not infer that an appender in **another JVM** will share that manager.

Key distinctions:

| Case | Coordination Level |
| --- | --- |
| Multiple threads → **one** `RollingFileAppender` | The appender/manager coordinates writes and rollovers within its runtime |
| Multiple loggers → same `AppenderRef` | Still routes through the same appender; typically the preferred setup |
| Multiple logger contexts in a JVM sharing a manager | `RollingFileManager` sharing mechanism applies per documentation and config compatibility |
| Two separate JVMs sharing the same file path | Do **not** automatically share an in-memory manager; risk of rotation collisions |
| Two containers mounting a shared volume to the same filename | No distributed mutex by default; requires architectural change or external coordination |

Log4j2 offers a `locking` option on certain file/rolling appenders, but **file locking alone does not solve all rollover races**, especially with other processes, renames, archive retention, and network filesystems. Lock semantics may be advisory depending on the OS, so you must verify that applications **consistently follow the locking protocol**.

One subtle detail: when multiple independent managers write to the same file, the size tracked by each manager may not fully reflect writes made by other managers. Thus, even when regular appends "seem to work," the **size rollover threshold** can still be miscalculated.

Documentation: https://logging.apache.org/log4j/2.x/manual/appenders/rolling-file.html

## 7. Logback: RollingFileAppender and Prudent Mode

In **Logback** (commonly used with SLF4J), `RollingFileAppender` combines a `RollingPolicy` and optionally a `TriggeringPolicy` depending on the type. Java code using `org.slf4j.Logger` does not itself determine when files rotate; you must inspect the provider and `logback.xml`.

A basic template for **one process managing one file**:

```xml
<configuration>
    <appender name="ROLLING"
              class="ch.qos.logback.core.rolling.RollingFileAppender">
        <file>logs/application.log</file>
        <encoder>
            <pattern>%d{yyyy-MM-dd HH:mm:ss.SSS} %-5level %logger - %msg%n</pattern>
        </encoder>
        <rollingPolicy
            class="ch.qos.logback.core.rolling.SizeAndTimeBasedRollingPolicy">
            <fileNamePattern>logs/application.%d{yyyy-MM-dd}.%i.log.gz</fileNamePattern>
            <maxFileSize>10MB</maxFileSize>
            <maxHistory>7</maxHistory>
            <totalSizeCap>1GB</totalSizeCap>
        </rollingPolicy>
    </appender>

    <root level="INFO">
        <appender-ref ref="ROLLING"/>
    </root>
</configuration>
```

This is a **Logback configuration**, not Log4j2. `maxHistory` and `totalSizeCap` support retention policies; you must verify the actual Logback version's behavior, how total size caps are enforced, and the impact when cleanup runs.

### Prudent Mode and Multiple JVMs

Logback provides **prudent mode** to support multiple JVMs writing to the same file via coordinated file access, but the documentation highlights **important limitations**:

1. `FixedWindowRollingPolicy` is not supported in prudent mode.
2. In prudent mode with `TimeBasedRollingPolicy`, **archive compression is not allowed**.
3. The `file` property of `RollingFileAppender` must be **left blank/omitted** because it is not allowed to pin to an active file in that way.

Reference configuration when prudent mode is required:

```xml
<configuration>
    <appender name="PRUDENT"
              class="ch.qos.logback.core.rolling.RollingFileAppender">
        <prudent>true</prudent>
        <encoder>
            <pattern>%d{HH:mm:ss.SSS} %-5level %logger - %msg%n</pattern>
        </encoder>
        <rollingPolicy
            class="ch.qos.logback.core.rolling.TimeBasedRollingPolicy">
            <fileNamePattern>logs/shared.%d{yyyy-MM-dd}.log</fileNamePattern>
            <maxHistory>7</maxHistory>
        </rollingPolicy>
    </appender>

    <root level="INFO">
        <appender-ref ref="PRUDENT"/>
    </root>
</configuration>
```

**Do not add `<file>logs/shared.log</file>` or `.gz` to `fileNamePattern` in this prudent mode setup.** Even when the system supports coordinated writes, prudent mode **does not turn a shared NFS/SMB directory into a durable distributed log store**, and locking can degrade performance. In most multi-replica deployments, **having each process write its own log and collecting via an agent** is simpler and safer.

Documentation: https://logback.qos.ch/manual/appenders-rolling.html

## 8. JUL FileHandler: Limitations and Per-Process Uniqueness

The JDK's **`java.util.logging.FileHandler`** can rotate files based on size limits and file counts. Example programmatic configuration:

```java
import java.util.logging.FileHandler;
import java.util.logging.Logger;

Logger logger = Logger.getLogger("example");
FileHandler file = new FileHandler(
        "logs/app.%u.%g.log", 1_000_000, 5, true);
logger.addHandler(file);
```

This is an **illustrative snippet inside a method where the `logs` directory already exists**, not a standalone Java program.

In `FileHandler`:

- `limit`: byte threshold per file as enforced by the handler.
- `count`: number of generation files in the rotation cycle.
- `%g`: generation number used in the filename.
- `%u`: uniqueness number useful for reducing collisions with other handlers/processes.
- `append`: whether to append to existing files.
- The handler also has its own formatter, level, and `close` lifecycle.

`%u` **does not mean multiple JVMs are jointly managing a shared archive**. A common safe approach is for each process to use separate files or let infrastructure collect logs afterward.

In JUL, `FileHandler` differs from `ConsoleHandler`; the latter writes to stderr by JDK default and performs no disk rotation. Do not mix JUL filename patterns like `%u`/`%g` with Log4j2 `%d`/`%i` or Logback `%d`/`%i`: each system has its own configuration rules.

JDK documentation: https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/FileHandler.html

## 9. Multiple JVMs or Containers: Do Not Share One Active File

Dangerous setup:

```text
JVM A ---\
          +---- /shared/logs/application.log
JVM B ---/
          |
          +---- both A and B have their own rolling policies
```

Even if both JVMs manage to write individual lines, **rotation** coordination also requires:

- Agreeing on which file is active and which files are archives.
- Coordinating when to rename the file.
- Knowing which archive indices are in use.
- Not deleting an archive that another JVM still treats as active or still needs.
- Not computing file size from a local counter that misses bytes written by another JVM.
- Ensuring every process uses the exact same file-locking mechanism (if used).
- Understanding how the network filesystem handles renames, caching, locks, and crashes.

**Preferred recommendation:** give each JVM/container an independent active log, then let an **agent/collector** merge events at collection time.

```text
JVM A -> stdout or app-A.log ----\
                                  +--> log collector --> search / retention
JVM B -> stdout or app-B.log ----/
```

Each process manages rotation for **its own file** (or does not rotate at all if writing to stdout). The collector can attach `service`, `instance_id`, `hostname`, `pod`, and `trace_id` so operators can query across all instances without multiple processes touching the same file.

If an organization mandates a shared file, you must evaluate a backend-supported configuration/mechanism (e.g., certain Logback prudent mode cases), filesystem, permissions, locking, throughput, and fault tolerance. Do not assume that `Files.move(..., ATOMIC_MOVE)` combined with a `FileLock` is enough to build a production shared rolling logger.

## 10. Application-Managed Rotation vs. External `logrotate`

On Linux, `logrotate` is often scheduled via cron/systemd to rename, compress, and clean up files. It **is unaware** of locks inside a Java class unless there is an explicit coordination protocol.

Two common scenarios:

### Rename and Create a New File

```text
Before:
  application.log (application holds an open file descriptor)

logrotate:
  rename application.log -> application.log.1
  create new application.log

Application:
  may still hold the file descriptor pointing to the old file
```

On POSIX-like operating systems, renaming a path **does not automatically change the file object an open descriptor points to**. Thus, the application may continue writing to the renamed file until it closes and reopens its descriptor. On some other platforms, renaming an open file may be forbidden altogether.

Solving this requires **the application to safely reopen the file** upon receiving an appropriate signal/hook, or using a rolling appender that manages its own files. Do not assume every Java logging appender supports signal-triggered reopening.

### `copytruncate`

`copytruncate` is `logrotate`'s method of copying the active file to an archive and then **truncating the active file to zero length**. It is useful for processes that cannot easily reopen files, but there is a **window between copy and truncate** during which newly written data may **not be in the copy and then get truncated from the active file**.

This is a **documented limitation in the `logrotate` manual**, not a Java-specific bug. Example configuration:

```text
/var/log/my-service/application.log {
    size 10M
    rotate 7
    copytruncate
    compress
    missingok
    notifempty
}
```

The snippet above is a **`logrotate` configuration sample**, not Log4j2 or Logback XML. Do not deploy it to production without verifying paths and file ownership.

**`copytruncate` does not guarantee zero log loss.** It can lose data during the copy–truncate window under heavy load. Therefore, when a Java application already uses an official `RollingFileAppender`, it is usually best to let **the framework handle rotation** and not have `logrotate` manage the same file simultaneously.

Documentation: https://man7.org/linux/man-pages/man8/logrotate.8.html

## 11. Warning When Using Plain File Appenders With External Rotation

According to Log4j2 documentation, standard **File Appenders** do not provide a mechanism for external tools to force-reopen an open file. If an external tool renames the file, the application's file descriptor may still point to the old file. Consequently, pairing with `logrotate` often leads to `copytruncate`, which has a data-loss window.

This leads to a practical rule of thumb:

- Use `FileAppender` if you have a **specific reason not to need self-rotation** and the storage path is appropriate.
- Use `RollingFileAppender` if you want **Log4j2 to manage rollover and archiving**.
- Use `ConsoleAppender` writing to stdout/stderr when container infrastructure already handles collection and rotation at the runtime layer.
- If you want external `logrotate` management, choose a design **explicitly supported by both the application and the rotation tool**, rather than just setting up cron and hoping the file descriptor switches on its own.

Log4j2 documentation: https://logging.apache.org/log4j/2.x/manual/appenders/file.html

## 12. Async Logging and Synchronizing Rotation

**Async logging** reduces the time a business thread waits on I/O by placing `LogEvent`s into a queue for another thread to process. However, async does not eliminate file coordination issues:

```text
Request threads
    |
    v
Async queue
    |
    v
Consumer / file manager
    |
    v
Rolling appender + rotation
    |
    v
File
```

In a typical design, a single consumer/manager processes events along a coordinated write path, minimizing impact on request threads. However:

- **A full queue** can cause the application to block, drop events, or switch behavior depending on configuration.
- **Crashing before flush/drain** can lose events still sitting in memory.
- **Ordering across threads** only reflects the order in which the queue accepted events, not necessarily remote business timestamps.
- **Rotation while the queue has pending data** must be managed by the framework; never rename files externally while an async worker is writing.
- **Stop/shutdown** must include a wait/drain mechanism within configured timeouts and contracts.
- **Hot reconfiguration** may create a new appender; avoid having two generations of appenders actively rotating the same file.

**`AsyncAppender` is not a durable message queue.** If compliance or audit requirements forbid data loss, you need a dedicated durable storage channel, not just a larger appender queue.

## 13. Compression, Archive Cleanup, and Retention

A rotation does more than create a new file. Typical tasks include:

1. Moving the active file to an archive (rename/move).
2. Compressing the archive, e.g., `.gz`.
3. Updating indices/paths according to policy.
4. Deleting old archives by file count, age, or total size.
5. Resuming writes to the active file.
6. Allowing agents/collectors to finish reading un-ingested archives if the pipeline requires it.

Post-processing steps may run **asynchronously**, introducing additional contention scenarios:

- An archive is just renamed when the next rotation tries to use the same name.
- Compression reads an archive while another writer is still writing to that inode.
- Cleanup deletes a file before the log shipper finishes reading it.
- An archive file lacks final metadata/EOF, yet the collector detects and partially ingests it.
- Retention is too short, causing files to be deleted before the collector catches up.

You need **collision-free archive naming** that allows indices to increment across multiple rotations in the same day, clear separation between writer archiving and reader infrastructure, and verification of how your log shipper handles renames/truncation.

Do not assume `maxHistory=7` or `max=7` means "7 days" across all backends. Similar or identical property names do not imply identical semantics. With a time + size policy, a single day can produce multiple files.

## 14. Time-Based Rotation and Clock Synchronization

Daily/hourly rotation introduces additional issues:

- **Different timezones:** two machines may roll over days at different times if defaults rely on system timezone.
- **Clock adjustments (NTP/manual):** time jumps can cause policies to observe unexpected boundaries.
- **DST (Daylight Saving Time):** a day in some timezones can be 23 or 25 hours long; never assume every day is 24 hours.
- **`LogEvent` time vs. file rotation time:** async queues and processing delays can place events near a boundary into a different archive.
- **Cron policies:** timer-based mechanisms may rotate near a scheduled boundary, while boundary events may be distributed differently than expected.
- **TimeBased policies:** operate on time intervals derived from `filePattern`, so verify behavior when no logs arrive.
- **Multiple replicas starting at different times:** a UTC convention and per-process files are far easier to reason about than trying to share archive names.

Risk-mitigation practices:

1. Standardize on a single timezone (many systems choose UTC) in logging policies.
2. Include explicit timezone offsets in record timestamps, independent of archive filenames.
3. Use a `filePattern` that includes both the period and an index when multiple files per period are possible.
4. Test behavior before/after rollover boundaries and when restarting after downtime.
5. Do not treat archive filenames as absolute proof of the exact timestamp of every event inside.

## 15. Rename, Locking, and Filesystem Atomicity

Relevant primitives:

| Mechanism | What It Provides | What It Does Not Provide |
| --- | --- | --- |
| `synchronized` | Mutual exclusion between threads using the same monitor in a JVM | Does not lock other JVMs or external tools |
| `ReentrantLock` | Explicit locking between threads sharing the same lock object | Not a distributed lock |
| `FileChannel.lock()` | OS-level file locking via Java API, within OS support | Does not coordinate rollover decisions, multiple filenames, or retention; may be advisory |
| `Files.move(...)` | Renames/moves a file at the filesystem level | Does not make multiple move/delete steps a single transaction |
| `StandardCopyOption.ATOMIC_MOVE` | Requests an atomic move if the provider/filesystem supports it | Not guaranteed on all systems, nor atomic across the whole rotation sequence |
| `flush()` | Pushes data out of relevant buffers | Does not confirm durable collector storage; not always equivalent to fsync |
| `FileChannel.force(...)` | Requests syncing file updates to the storage device per API contract | Does not provide exactly-once delivery in distributed logging |

With `ATOMIC_MOVE`, you must handle `AtomicMoveNotSupportedException` when the provider does not support it. On Windows, moving a file held open by a process has different restrictions than on POSIX. On NFS/SMB, caching, locking, and semantics must be tested on the actual target environment.

Even when an individual rename is atomic, the overall sequence:

```text
delete archive.2
move archive.1 -> archive.2
move active -> archive.1
open new active
```

is **not atomic as a transaction**. If a crash occurs between steps 2 and 3, the archive state may be abnormal. Therefore, restart recovery and error-handling logic must be designed realistically.

## 16. When Rotation Fails: What to Handle and Monitor

Common failure sources include:

| Error / Scenario | Possible Consequence | What to Check |
| --- | --- | --- |
| Disk full or quota exhausted | Logging/rotation fails | Disk usage, quota, appender status |
| Missing rename/delete permissions | Rollover fails or file remains unchanged | Owner, permissions, filesystem |
| Archive name collision | Files overwritten or rotation fails | `filePattern`, policies, multiple writers |
| Two processes rotating simultaneously | Filenames/counters drift out of sync | Whether an active file is shared |
| File descriptor still open | Rename/reopen behaves unexpectedly | OS handles, appender manager, external tools |
| Archive compression failure | Saved archive may be incomplete | Status Logger, compression errors, archive names |
| Slow log shipper/agent | Files cleaned up before ingestion completes | Retention vs. backlog |
| JVM crash mid-rotation | Incomplete archive state | Startup recovery, file reconciliation |
| Async queue full or not drained | Lost/delayed logs despite valid policy | Queue/drop metrics, shutdown hooks |
| Clock/timezone inconsistency | Archives roll on unexpected schedules | Timezone, DST, policy, server time |

**Do not call `LOG.error` to report an error in the broken appender itself without understanding how the Status Logger routes it.** When the logging system is already failing, using the same appender to log a new error may never reach its destination or may cause an error loop. You need external monitoring/diagnostics such as metrics, managed stdout/stderr, or file/disk checks.

In Log4j2, `ignoreExceptions` controls whether the application receives certain exceptions from an appender. Setting it to `false` can let logging errors propagate to the caller, but **does not turn logging into durable storage**. When using a failover appender, exception propagation must be configured compatibly.

## 17. How to Test Synchronized Rotation

A reliable test does not just check that a file was renamed. It verifies **data integrity within the expected scope**.

### Testing One JVM With Multiple Threads

1. Create a dedicated test directory; never use production logs.
2. Use a single shared writer/rolling appender with a very small rollover threshold to trigger multiple rotations.
3. Run multiple threads, each writing records with a **unique** ID: `threadId-sequence`.
4. Wait for all tasks to finish and drain any logging queues.
5. Read **all remaining archives and the active file**. If retention deleted files, adjust the test policy so all events are preserved.
6. Count total IDs, unique IDs, missing IDs, and duplicate IDs.
7. Verify that no lines are truncated/interleaved and that the file remains parseable.
8. Repeat the test multiple times under different scheduler conditions to catch hard-to-reproduce races.

The Section 5 example checks `records=12`, `unique=12`, and `verified=true`. Because thread interleaving is non-deterministic, **do not assert a fixed ordering between thread A and thread B**.

### Testing Multiple Processes

If a system requires multiple JVMs to share a file, run **two separate processes** concurrently. Check file locks, renames, file sizes, and archive counts after each round. Do not substitute a two-thread test for this: they test **different locking scopes**.

### Testing Collisions With External Tools

In an isolated environment, generate logs continuously while running `logrotate` on a fast schedule. Check for lost records in the copy–truncate window, file descriptors after rename, and whether data lands in the expected file. Never run destructive tests against production log files.

### Testing Crashes and Restarts

Force-stop the process at various points near rollover; restart it and observe:

- Can the configuration read the existing state/archives?
- Are old archives accidentally deleted?
- Does resuming writes create duplicate filenames?
- How many unflushed records are lost?
- Does the collector duplicate or skip files after a rename?

A passing single-JVM test is not enough to prove safety under crashes, distributed filesystems, or collector downtime.

## 18. Common Mistakes to Avoid

**1. Rolling manually with `if (size > limit) move(...)` in each thread.** This is a check-then-act race. Use a shared manager or a properly scoped critical section.

**2. Assuming `volatile` can replace a lock.** Visibility does not make check + rename + write atomic.

**3. Using `synchronized` and assuming multiple JVMs are protected.** A monitor is scoped to a specific object within a single JVM.

**4. Two appenders targeting the same file with different policies/configs.** This can cause manager, `filePattern`, and retention conflicts; use a single configuration and verify manager-sharing behavior.

**5. Two pods writing to the same active file on a shared volume.** Prefer per-instance files/streams or a centralized collection pipeline.

**6. Using Log4j2 `RollingRandomAccessFile` as if it safely allows multiple processes to open the same file.** Its access/append characteristics differ from `RollingFile`; check the implementation documentation.

**7. Using both framework rolling and `logrotate` on the same file.** Both may compete to rename and archive. Pick a single owner for rotation.

**8. Treating `copytruncate` as lossless.** The `logrotate` manual explicitly documents a data-loss window between copy and truncate.

**9. Treating a file lock as a distributed rotation protocol.** A file lock does not coordinate threshold checks, archive indexing, renames, and cleanup across processes.

**10. Omitting `%i` in `filePattern` when time+size can trigger multiple rollovers per period.** Archive names can collide.

**11. Enabling compression with Logback prudent mode without reading the limitations.** Prudent mode with `TimeBasedRollingPolicy` does not support compression and restricts the `file` element.

**12. Setting retention shorter than collector lag.** Archives may be cleaned up before the agent finishes ingesting them.

**13. Equating Log4j2 `max=7` with Logback `maxHistory=7`.** They belong to different backends with different semantics; verify the actual policy.

**14. Forgetting the async queue during shutdown.** Un-drained events can be lost even when rotation logic is correct.

**15. Relying on archive timestamps as the exact time of every contained event.** Clock skew, timezones, async queues, and rollover boundaries can shift events.

**16. Concluding "zero log loss" just because a 12-line test passed.** The demo test only proves behavior for two threads, one process, and normal I/O.

## 19. Self-Check Questions

1. **What is synchronizing rotation?** Coordinating policy checks, renaming/archiving, switching the active file, and writing `LogEvent`s to prevent races and inconsistent state.
2. **Why is `volatile boolean rotating` insufficient?** The check–rotate–append steps still do not form an atomic critical section.
3. **Does `synchronized` between two threads protect another JVM?** No. Monitors are per-object and per-JVM.
4. **Why should you use a shared appender/manager?** To keep file state, policies, and rollover coordination consistent within its managed scope.
5. **If two threads write 6 lines each and rotate every 4 lines, how many rollovers occur in the example?** Two; 12 lines split into 3 batches of 4 lines.
6. **Why does the program check a `Set` of IDs instead of comparing line order?** Because thread interleaving is non-deterministic, whereas the expected set of IDs is fixed.
7. **Does Log4j2 share `RollingFileManager` across independent JVMs?** Not automatically; it is an in-runtime manager-sharing mechanism, not a distributed lock.
8. **Why can multiple managers writing to the same file cause inaccurate size rollovers?** Each manager tracks its own written bytes and does not accurately know what other managers wrote.
9. **When is `%i` needed?** When multiple rotations can happen within the same time period, such as combining time + size policies.
10. **Can `logrotate copytruncate` lose data?** Yes, due to the window between copy and truncate documented in the manual.
11. **Does renaming a file on POSIX automatically point an appender's open file descriptor to the new path?** No; the descriptor continues pointing to the pre-rename file object.
12. **Does Logback prudent mode allow archive compression?** No, not in the documented `TimeBasedRollingPolicy` prudent configuration.
13. **Does `ATOMIC_MOVE` turn the entire delete/move/open sequence into a transaction?** No. It only requests atomicity for a single move when supported.
14. **Does using `AsyncAppender` guarantee no unflushed events are lost on crash?** No. In-memory queues can be lost.
15. **If a log shipper reads archives slowly, what should you check?** Retention/cleanup, rename tracking, buffering, and whether ingestion can keep up before files are deleted.
16. **In a multi-container system, what is usually the simplest way to avoid shared rotation?** Have each instance write to its own stream/file and collect centrally via an agent.
17. **Does writing the expected number of lines without I/O errors guarantee zero log loss in all scenarios?** No. You also need crash, multi-process, collector, and durability tests if stronger guarantees are required.
18. **Should you use both Log4j2 `RollingFileAppender` and `logrotate` on the same active file?** Usually no; designate a single owner responsible for rotation.

## 20. References

- Apache Log4j 2, Rolling file appenders: https://logging.apache.org/log4j/2.x/manual/appenders/rolling-file.html
- Apache Log4j 2, File appenders and external reopen limitations: https://logging.apache.org/log4j/2.x/manual/appenders/file.html
- Logback, RollingFileAppender / prudent mode: https://logback.qos.ch/manual/appenders-rolling.html
- Linux manual `logrotate(8)`, `copytruncate`: https://man7.org/linux/man-pages/man8/logrotate.8.html
- Java 17, `FileHandler`: https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/FileHandler.html
- Java 17, `Files.move`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html

**Takeaway:** synchronizing rotation is a **stateful multi-step coordination problem**, not simply calling `rename` under an arbitrary lock. Within a single JVM, share an appender/manager or use an appropriate critical section. Across multiple JVMs or external tools, never treat `synchronized`, `FileLock`, or `ATOMIC_MOVE` alone as a complete solution. Prefer giving each instance its own file/stream, letting the logging framework manage rotation, and collecting centrally with an agent; test integrity, failures, crashes, and retention according to your required guarantee scope.
