# Hands-on Project: Setting Up Log File Rotation in Java 17

## 1. Lab Objectives

In this project, you will **configure log rotation** for a Java application, generate enough logs to force rollover, and **verify** the file names, generation count, retention of new logs, and storage limits yourself. After a minimal run using Java's built-in library, the lesson expands on how to bring that policy into a service using Logback, coordinate with a log shipper, and check for production risks.

The expected outcome is not just "having a log file," but being able to answer:

1. **When is the active file rotated?** By size, time, or both.
2. **What are the names of the active file and old files?** Knowing which file contains new data.
3. **Are file count/age/size limits set?** Rotation and retention are two related but distinct decisions.
4. **When the collector is down, are logs deleted before being read?**
5. **When the JVM restarts or multiple instances run concurrently, are logs accidentally overwritten, lost, or duplicated?**
6. **When the disk is full or write permissions are missing, does the system emit observable error signals?**

The main lab uses **JDK 17 or later**, `java.util.logging.FileHandler`, and a single Java file; **no Maven, Spring, or external services are required**. The Logback configuration in the later section is an **extension step** for real projects using Logback; it does not apply directly to a plain JUL program.

### Completion Criteria

- [ ] Compile and run the Java 17 example.
- [ ] Have **three** file generations after generating enough logs to rotate multiple times.
- [ ] The event with the latest sequence number is still present in the retained files.
- [ ] Events older than the file-count retention limit have been replaced.
- [ ] Understand why `count=3` does not mean "active file + three backups."
- [ ] Have a policy for when to rotate, delete/compress files, and handle slow file-reading agents.
- [ ] Have a testing checklist for restarts, disk full, file permissions, and collector outages.

## 2. Lab Context and Architecture

Suppose an inventory management service writes diagnostic events as follows:

~~~text
event=inventory_checked seq=001 outcome=OK
event=inventory_checked seq=002 outcome=OK
...
~~~

If it writes to a single file forever, the file can grow huge and fill up the filesystem. We want **the active file to rotate when it exceeds a threshold**, and only keep a few recent generations for use in a development environment.

~~~text
Inventory service
      |
      v
JUL Logger
      |
      v
FileHandler
      |
      +--- app-0.log   (active generation in JUL)
      +--- app-1.log   (previous generation)
      +--- app-2.log   (older generation)
      |
      +--- older files replaced after rollovers
~~~

In the lab, each run uses a **new temporary directory** to avoid conflicts with existing logs. Configuration values are intentionally kept small:

| Property | Lab Value | Why |
| --- | --- | --- |
| JDK | Java 17+ | Uses standard API, no dependencies needed |
| Limit | 512 bytes | Easy to trigger rollover with a few dozen lines |
| Count | 3 | Easy to observe the three-generation limit |
| Append | `false` | Do not append to an old file cycle from a previous run |
| Pattern | `app-%g.log` | Generates names by generation number |
| Logs generated | 100 events | Far exceeds the total capacity of three files |
| Log level | `INFO` | Simulated events are standard informational messages |
| Encoding | UTF-8 | Avoids relying on default charset |
| Verification output | Four stdout lines | Independent of temporary paths and timestamps |

**Do not use the 512-byte and three-file configuration for production.** These parameters are for testing rollover; real applications must calculate based on bytes/sec, shipper latency, retention period, and filesystem capacity.

## 3. Environment Setup

You need JDK 17 or later and permission to create files in the OS's default temporary directory.

Check:

~~~bash
java -version
javac -version
~~~

In a practice directory, create the file:

~~~text
rotation-lab/
└── RotationLab.java
~~~

Steps to create/run on macOS or Linux:

~~~bash
mkdir rotation-lab
cd rotation-lab
# Create RotationLab.java from the source code in Section 4.
javac RotationLab.java
java RotationLab
~~~

On Windows PowerShell:

~~~powershell
New-Item -ItemType Directory rotation-lab
Set-Location rotation-lab
# Create RotationLab.java from the source code in Section 4.
javac RotationLab.java
java RotationLab
~~~

`javac` generates `RotationLab.class` bytecode and auxiliary classes produced by the compiler. Running `java RotationLab` uses the current classpath in a small project without a package declaration. If your environment uses modules/packages or runs via an IDE, adjust the paths according to your actual project.

**Administrator/root privileges are not required.** If the temporary directory does not allow creating files, the test should fail with a clear reason; you should not grant full-filesystem permissions just to run the lab.

## 4. Writing a Java 17 Program That Actually Rotates Files

Create **`RotationLab.java`** with the full content:

~~~java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Locale;
import java.util.logging.FileHandler;
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class RotationLab {
    private static final int LIMIT_BYTES = 512;
    private static final int FILE_COUNT = 3;
    private static final int EVENTS = 100;

    public static void main(String[] args) throws Exception {
        // Separate directory for each run: avoids name collisions and overwriting.
        Path directory = Files.createTempDirectory("rotation-lab-");

        Logger logger = Logger.getLogger("lab.rotation.inventory");
        logger.setUseParentHandlers(false);
        logger.setLevel(Level.INFO);

        // %g is the generation number in FileHandler's file set.
        String pattern = directory.resolve("app-%g.log").toString();
        FileHandler handler = new FileHandler(
                pattern, LIMIT_BYTES, FILE_COUNT, false);

        handler.setEncoding(StandardCharsets.UTF_8.name());
        handler.setLevel(Level.INFO);
        handler.setFormatter(new Formatter() {
            @Override
            public String format(LogRecord record) {
                return formatMessage(record)
                        + System.lineSeparator();
            }
        });
        logger.addHandler(handler);

        try {
            for (int i = 1; i <= EVENTS; i++) {
                String message = String.format(
                        Locale.ROOT,
                        "event=inventory_checked seq=%03d outcome=OK",
                        i);
                logger.info(message);
            }
        } finally {
            // Close file, flush buffer, release file lock.
            logger.removeHandler(handler);
            handler.flush();
            handler.close();
        }

        int found = 0;
        long retainedEvents = 0;
        boolean newestPresent = false;

        for (int gen = 0; gen < FILE_COUNT; gen++) {
            Path path = directory.resolve("app-" + gen + ".log");
            if (!Files.isRegularFile(path)) {
                continue;
            }

            found++;
            List<String> lines = Files.readAllLines(
                    path, StandardCharsets.UTF_8);
            retainedEvents += lines.size();

            for (String line : lines) {
                if (line.contains("seq=100")) {
                    newestPresent = true;
                }
            }
        }

        boolean oldEventsRemoved = retainedEvents < EVENTS;

        if (found != FILE_COUNT ||
                !oldEventsRemoved ||
                !newestPresent) {
            throw new IllegalStateException(
                    "Rotation verification failed");
        }

        System.out.println("generated=100");
        System.out.println("rotationFiles=3");
        System.out.println("oldEventsRemoved=true");
        System.out.println("newestEventPresent=true");
    }
}
~~~

Compile and run:

~~~bash
javac RotationLab.java
java RotationLab
~~~

**Exact stdout on a successful run** with JDK 17+ and a filesystem that allows creating/writing/renaming files:

~~~text
generated=100
rotationFiles=3
oldEventsRemoved=true
newestEventPresent=true
~~~

**Stderr:** no output on the success path. The log directory is created in the temp directory with a random suffix; the program **does not print that path**, keeping stdout deterministic.

### Why Is the Output Deterministic?

- 100 log events are longer than the total capacity of three 512-byte files, so multiple rollovers occur.
- The pattern contains the `%g` token, so the lab files are typically named `app-0.log`, `app-1.log`, `app-2.log`.
- The three most recent generations cannot hold all 100 events; `oldEventsRemoved` becomes `true`.
- Event `seq=100` is emitted last, so it must remain in the retained generation if the handler wrote successfully.
- The formatter does not add timestamps or random thread names; stdout is only a test report and does not print the directory name.

This is a **basic verification** of the file lifecycle in the lab. If the system uses an unusual filesystem, the temp directory lacks permissions, or the handler cannot write, the program may report an error or throw an exception; in that case, it must not be considered a successful result.

### Program Limitations

- No `.gz` compression, day-based retention, or collector.
- Does not verify that every event is stored long-term: the lab intentionally proves that old events are replaced.
- `FileHandler` is created and written within a single-process JVM; multiple JVMs sharing the same path have not been tested.
- The formatter uses `event=...` strings, not JSON. When production uses NDJSON, a JSON encoder is needed to ensure proper escaping and one event per line.
- Because there is no I/O error-handling code in `ErrorManager`, `logger.info()` not throwing **does not by itself prove** that every file write succeeded; the lab reads the files back after closing the handler.
- Although Java may hold a handle to the file, `FileHandler` is responsible for closing/opening within its own rotation mechanism; an external tool renaming the file can still cause other issues.

## 5. Reading and Interpreting the Files After Rotation

After closing `FileHandler`, you can temporarily modify the lab to print `directory.toAbsolutePath()` during a **single investigative run** if you want to know the exact path. Do not leave that print statement in the version used to match the stdout above, because the path changes between runs.

Alternatively, replace `Files.createTempDirectory(...)` with a dedicated directory in a permitted project path, such as `Path.of("lab-logs")` and `Files.createDirectories(directory)` when you want to inspect it with a file explorer. Be sure to **intentionally rename or delete old demo data** before each run; never delete a log directory shared with a real service.

JUL generation meaning table:

| Path | Typical Meaning |
| --- | --- |
| `app-0.log` | Active/most recent generation |
| `app-1.log` | Previous generation |
| `app-2.log` | Older retained generation |
| `app-3.log` | Not included in the lab's `count=3` policy |

When the active file exceeds the threshold, `FileHandler` rotates the file generations. Files older than the configured generation count are replaced. Therefore:

- Do not expect `app-2.log` to always have a creation time older by an exact number of minutes; rollover depends on log rate.
- Do not use `File.lastModified()` as the sole proof of event ordering across multiple machines.
- Do not treat `count=3` as **three backups plus active**. It is the **total number of generations**.
- Do not expect every file to be **exactly** 512 bytes; records are written in chunks, so the size can exceed the limit at the moment rotation triggers.
- Do not rely on inspecting the active file to conclude that the collector has received everything.

If you want more thorough testing, parse the sequence number from each line, distinguish active and archive files, verify they only contain allowed string formats; then compare the sequences against an independent test data source to determine the retained/deleted range. However, **do not expect all 100 events to remain**, because retention in the lab is intentionally low.

## 6. What Parameters Does `FileHandler` Actually Control?

The JDK API has the constructor:

~~~java
FileHandler(String pattern, int limit, int count, boolean append)
~~~

Key parameters:

| Parameter | Meaning and Notes |
| --- | --- |
| `pattern` | File name pattern; may contain tokens such as `%g`, `%u` |
| `limit` | Size threshold in **bytes** for rotation, not line count |
| `count` | Total number of files in the handler's rotation cycle, including the active file |
| `append` | When opening a file, whether to append to an existing file or start fresh per policy |

Common naming tokens:

- `%g`: generation number of the file in the cycle.
- `%u`: unique number to resolve certain name/lock collisions.
- `%t`: OS/JVM temporary directory.
- `%h`: user account's home directory.
- `%%`: a literal `%` character.

Example:

~~~text
logs/service-%g-%u.log
~~~

**`%u` is not a user ID, process ID, or request ID**, and does not guarantee multiple JVMs can safely share the same active file. The unique number and lock behavior depend on the environment; assign separate paths or instance identities for each process when needed.

JUL `FileHandler` is suitable for learning **size- and generation-based rotation**. It does not provide a rich time-based rolling policy like some dedicated backends. If a problem requires daily/hourly rollover, archive compression, and age-based deletion, use a backend or infrastructure that supports those configurations and test on the actual version.

### Configuring JUL via a Properties File (Extension)

Besides creating `FileHandler` directly in code, JUL can be configured from a `logging.properties` file. Example configuration snippet:

~~~properties
handlers=java.util.logging.FileHandler
.level=INFO

java.util.logging.FileHandler.pattern=logs/app-%g.log
java.util.logging.FileHandler.limit=10485760
java.util.logging.FileHandler.count=5
java.util.logging.FileHandler.append=true
java.util.logging.FileHandler.encoding=UTF-8
java.util.logging.FileHandler.formatter=java.util.logging.SimpleFormatter
~~~

In an application where `LogManager` loads this file at JVM startup, you can run with the system property:

~~~bash
java -Djava.util.logging.config.file=logging.properties MainClass
~~~

**This is an integration recipe**, not a command to run `RotationLab.java` from Section 4 directly; the lab program **attaches its own FileHandler** and disables parent handlers, so it does not use the root logger's `FileHandler` as in the properties example. To use properties for a real service, replace `MainClass` with your application class, and ensure the `logs/` directory exists and is writable.

Choose only **one way to configure `FileHandler` for the same purpose**. If you both use a root `FileHandler` from `logging.properties` and attach a handler to a logger with parent handlers enabled, events may be duplicated or scattered across multiple unintended files.

## 7. When Should You Switch to a Logback Rolling Policy?

Many Java projects use SLF4J with Logback instead of JUL directly. A time-and-size-based Logback configuration can provide:

- A stable active file, e.g., `application.log`.
- Archives by date and index when exceeding the daily threshold.
- `.gz` compression for old files.
- Limits on the number of history periods and total archive size.

Place the file as **`logback.xml`** in the classpath resources of a project **that already uses Logback as its logging backend**:

~~~xml
<configuration>
  <property name="LOG_DIR" value="./logs"/>

  <appender name="ROLLING"
            class="ch.qos.logback.core.rolling.RollingFileAppender">
    <file>${LOG_DIR}/application.log</file>

    <rollingPolicy
      class="ch.qos.logback.core.rolling.SizeAndTimeBasedRollingPolicy">
      <fileNamePattern>${LOG_DIR}/archive/application.%d{yyyy-MM-dd}.%i.log.gz</fileNamePattern>
      <maxFileSize>10MB</maxFileSize>
      <maxHistory>7</maxHistory>
      <totalSizeCap>1GB</totalSizeCap>
    </rollingPolicy>

    <encoder>
      <pattern>%d{ISO8601} %-5level [%thread] %logger{36} - %msg%n</pattern>
    </encoder>
  </appender>

  <root level="INFO">
    <appender-ref ref="ROLLING"/>
  </root>
</configuration>
~~~

**Note:** This is an **extension** configuration, not a file you need to create to run `RotationLab.java`. It requires dependencies/configuration compatible with the Logback version in use. The project must verify that the XML is accepted by the parser and test rollover on that exact backend; Logback and JUL do not automatically replace each other.

Meaning:

- `<file>`: path to the active file being written.
- `fileNamePattern` has `%d` for date and `%i` for index within the same period.
- `.gz`: requests archive compression as supported by the rolling policy.
- `maxFileSize=10MB`: size-based rollover threshold within the same day.
- `maxHistory=7`: number of **history periods** retained; when the pattern is daily, do not interpret this as "seven files."
- `totalSizeCap=1GB`: total archive size cap managed by the cleanup policy; not a hard limit for the entire filesystem.

Configuring `./logs` is only appropriate when the deployment has a persistent filesystem and write permissions. In production, use a path provided by the operations team, ensure the directory is created/monitored, and test when deploying on containers, VMs, or shared storage.

**If using structured JSON logs**, use a proper JSON encoder instead of the text pattern above and test NDJSON/escaping. **Do not replace `%msg%n` with manual JSON string concatenation**: input containing quotes, newlines, or backslashes can break syntax and the log shipper.

## 8. Do Not Mix Multiple Rotation Mechanisms on the Same File

A service may experience rotation at multiple layers:

~~~text
Application -> stdout
                 |
                 v
        Container runtime logs
                 |
           runtime rotation
                 |
               shipper
                 |
              collector
~~~

or:

~~~text
Application -> RollingFileAppender
                        |
                        v
                  application.log
                        |
                        v
                     shipper
                        |
                        v
                     collector
~~~

If an application already lets Logback rotate `application.log`, configuring an OS tool like `logrotate` to rename/truncate **that same file** can cause conflicts. Decide on **one component responsible for rotating the active file**; if multiple components must coordinate, establish a clear contract for reopen, rename, and checkpointing.

### Rename-create

On POSIX-like systems, if an external tool renames `application.log` to `application.log.1` and creates a new `application.log`, **the file descriptor held by the JVM may still point to the old file**. In that case, the JVM keeps writing to the archived file while the new active file remains empty until the writer properly reopens it.

Do not assume that every Java application receiving `SIGHUP` will automatically reopen its log file; you need a mechanism supported and tested by the backend/framework.

### Copytruncate

With `copytruncate`, an external tool copies the file to an archive and then truncates the active file in place. This avoids requiring an immediate reopen, but introduces a **race condition between copy and truncate**: bytes written in that window can be lost. Therefore, `copytruncate` is not a lossless log-preservation solution.

**In containers:** many systems choose to log to stdout/stderr and let the container runtime/node agent rotate logs; the application does not have to manage rolling files itself. However, a successful stdout write **does not prove the collector has stored it**. Logs can be lost if the runtime rotates/deletes them before the shipper can read them.

## 9. Rotation Is Not Retention, Compression, or Backup

Four concepts:

| Component | What It Does | What It Does Not Solve on Its Own |
| --- | --- | --- |
| Rotation | Switches from the active file to a new generation | Does not guarantee long-term log retention |
| Retention | Keeps/deletes by age, file count, or size | Does not prove logs have been shipped |
| Compression | Reduces archive size, e.g., `.gz` | Does not encrypt contents |
| Archival/backup | Stores to another location | Requires separate lifecycle policies and read permissions |

The lab's `FileHandler(count=3)` performs **rotation with a generation-count limit**, but has no "delete after 30 days" or compression policy. Logback adds time/size policies, but these must also be measured and monitored.

**Estimate capacity before setting retention:** take the service's bytes/sec or GB/day, multiply by the number of instances and the required retention window. Add space for the active file, peak bursts, temporary compression, shipper spool files, metadata, and headroom. An archive cap does not cover all data on disk.

For example, if one instance emits an average of 20 MB/hour, keeping 24 hours locally requires about 480 MB **before compression**, excluding peaks and other files. If the collector can be down for 48 hours, a 24-hour local retention **risks deleting logs before they can be sent**. You must base this on actual recovery SLOs and shipper backlog, not just pick a neat count.

### Collector Retention Is a Separate Matter

Deleting local archives after seven days **does not delete** copies in the central store, backups, or alert exports. Conversely, keeping logs centrally for 30 days does not help recover local files if the shipper never forwarded the events. Access permissions and data retention must be set at **every storage hop**.

## 10. Coordinating with a File Shipper During Rollover

In production, a file agent typically tails `application.log`, tracks file identity/offset, and forwards events to a collector.

| Scenario | Risk | How to Verify |
| --- | --- | --- |
| Active file is renamed | Shipper keeps reading old file or misses the tail | Tail the old file to EOF before dropping it |
| New file reuses active name | Old offset applied to new file | Shipper detects new file by file identity |
| File is truncated | Offset past EOF or data loss in race | Test truncation/recovery |
| Archive compressed immediately after rollover | Agent has not finished reading old file | Delay compression/deletion or increase ship throughput |
| Continuous rotation under peak load | Old generations lost before agent catches up | Increase retention/spool or raise throughput |
| Agent restarts after reading but before ACK | Events lost or duplicated | Verify checkpoints and delivery semantics |
| Glob matches both active and archive | An event may be read twice | Configure include/exclude rules and file conditions |
| Multiline JSON | One event split into multiple records | Use NDJSON or proper multiline parser |

**A read offset does not automatically equal an event ACKed by the collector.** Some agents have persistent queues, while others only have local checkpoints; reliability must be evaluated against the actual agent's contract, not `FileHandler`.

**Duplicate risk:** if the agent re-reads a file after a rename/restart or the exporter retries when an ACK is lost, the same event can appear twice. If deduplication is needed, emit a stable `eventId` and use appropriate ingestion rules; "writing once in Java" does not guarantee exactly-once delivery to the collector.

### A Simple End-to-End Test

In a test environment with an agent/collector:

1. Log events with a unique synthetic `eventId`.
2. Increase volume to force file rotation.
3. Wait for the agent to process using an observable mechanism with a timeout, rather than relying on a fixed `sleep` as a guarantee.
4. Query for `eventId` at the collector and compare counts.
5. Restart the agent after the file has been renamed; verify no events are lost outside policy.
6. Temporarily stop the collector from receiving, and inspect the queue/backlog and whether old events get deleted.
7. Document the guarantees: at-most-once, at-least-once, deduplication, or best effort.

## 11. Failure Cases to Test

A configuration that works in a healthy environment is not enough. The project must also test failure paths:

| Test | Expectation and Criteria |
| --- | --- |
| Exceed size multiple times | Rollover occurs, file count does not grow unbounded |
| Restart mid-cycle | Append/overwrite follows policy, no unintended data loss |
| Directory without write permission | Clear error or backend status/metric, no assumption of write success |
| Disk full | Application and logging backend have defined behavior |
| Two JVMs writing to the same path | No interleaved data or rename races; separate files/instances |
| Running in a thread pool | No corrupted logs and no leaked MDC/context if used |
| Rollover while tailing | Agent reads the full tail of the file before deletion |
| Premature compression/archival | Files not deleted before shipper finishes reading |
| Application forcefully killed | Understand risk of losing buffered/unflushed logs |
| Collector down for hours | Backlog/retention meets SLO, drop count is measurable |
| Enabling `DEBUG` under high traffic | Disk headroom and rolling policy still hold up |
| File/path with Unicode or invalid characters | Path/charset handled or fails in a controlled manner |
| Message containing newlines | When using JSON, each event still parses as valid NDJSON |
| Fake secret in log message | No tokens/passwords emitted outside the allowlist |

### Safe Disk-Full and File-Permission Testing Tips

**Do not try to fill up a real production machine's filesystem.** Use a test volume with a small quota/limit or a separate sandbox filesystem. Start by simulating a quota, writing past the limit, and observing the logging backend's error channel. Before cleaning up files, verify the exact lab path so you do not accidentally delete another service's data.

**Do not modify permissions of a shared directory** to induce errors in a real environment. Create a dedicated test directory; change permissions only within permitted scope. Never use "chmod 777" or run a service as root just so `FileHandler` can write.

With JUL, handler I/O errors may be routed to `ErrorManager` or the logging backend's diagnostic channel rather than thrown directly to the caller. Therefore, you must verify **the actual files, backend errors, and metrics/drops**, not just assert that `logger.info()` does not throw.

## 12. Choosing a Production Policy

Do not copy the lab's `512 bytes, count=3`. Define a deployment policy:

| Field | Configuration Question |
| --- | --- |
| `logSource` | stdout, file, or both? Does it create duplicates? |
| `rotationOwner` | JUL/Logback/Log4j2, logrotate, or container runtime? |
| `trigger` | size, time, or size+time? |
| `maxFileSize` | Based on peak log rate and tail/ship capability? |
| `maxHistory` / `count` | Retain for how many hours/days or generations? |
| `totalSizeCap` | Accounts for active, spool, compression, and headroom? |
| `compression` | Compatible with the agent's file-reading speed? |
| `privacy` | Do logs contain PII/secrets? Read permissions and retention at every destination? |
| `failureMode` | On disk full/collector down, block, drop, or fail closed? |
| `shutdown` | Does it flush/drain within the allowed shutdown window? |
| `monitoring` | Disk free, archive size, rotate failures, shipper lag, drop count? |

### An Example Policy, Not a Default

For a VM service with its own log file, you might start with a **10 MB active file**, daily size+time archiving, **seven history periods**, a total archive cap, and an agent shipping to a central store. However, if the log rate is high or the collector can be disconnected for a long time, these numbers may be completely insufficient. You must check operational data, add headroom, and get retention approved.

For containers with a full stdout pipeline, you may **not need `FileHandler`**: use a JSON encoder to stdout, let the runtime handle rotation, and let the shipper handle buffering/retries. You still need to verify node-level file limits and agent read timing; "stdout is enough" is only true when the entire pipeline is properly configured and operated.

## 13. Security, Privacy, and File Permissions

Rotation creates additional copies: active files, archives, compressed files, shipper spools, central stores, and backups. These copies can retain **sensitive information** even after the application code is fixed to stop logging that data.

- Only log allowlisted data: event code, severity, controlled request/trace ID, outcome, error code.
- Do not log passwords, access tokens, cookies, OTPs, raw payment details, or unnecessary DTOs/bodies.
- Set directory/file permissions for the appropriate service account and agent; restrict read access to archives.
- Gzip only **compresses**, it does not encrypt. If content confidentiality is needed, use proper encryption and key management.
- Rotation and retention do not automatically delete copies at the collector/backups.
- Do not log URLs/queries containing tokens or raw exception messages that may contain PII.
- When testing, use **fake** sentinel secrets, never real credentials.
- Do not write log files into a directory publicly served by a static web server.
- With multi-tenancy, only log minimal tenant references when truly necessary; avoid arbitrarily splitting files by user ID.

**Note on timestamps/IDs:** a request ID is not a username, yet it can still be linked to an individual through other logs. Retention and access control must still consider data context.

## 14. Lab Implementation and Handover Checklist

### Lab Code Verification

- [ ] JDK 17+ available, `RotationLab.java` compiles with `javac`.
- [ ] Runs successfully, stdout consists of the exact four lines specified.
- [ ] `app-0.log`, `app-1.log`, `app-2.log` exist under the run's temporary directory.
- [ ] `seq=100` is retained; event count in files is less than 100 due to the low count policy.
- [ ] Handler is `flush()`ed, `close()`d, and removed from the logger in `finally`.
- [ ] `System.out.println` is not used to simulate writing primary logs to a file.
- [ ] No external dependencies or compilers outside JDK 17 for the main lab.

### Production Configuration Verification

- [ ] A single rotation owner is chosen for each active file.
- [ ] Peak log rate measured, sufficient disk free/headroom, and retention estimated.
- [ ] Appender/handler and shipper tested together during rename/truncate/compression.
- [ ] Active/archive files have proper permissions and directories.
- [ ] Alerts configured for disk full, rollover errors, shipper lag, queue backlog, and drops.
- [ ] No collection loop ingesting both stdout and files causing duplicates.
- [ ] Plans in place for restarts, shutdowns, log collector outages, and file shipper recovery.
- [ ] Tests verify no PII/tokens logged and archive read access is controlled.
- [ ] Separate retention policies for local logs, central store, backups, and audit logs.
- [ ] Configuration changes tested in staging before production.

## 15. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Interpreting `count=3` as 3 backups + active | Wrong retention estimate | Total files in JUL is 3 |
| Interpreting `limit=512` as 512 lines | Files rotate differently than expected | Limit measures bytes, not records |
| Creating handler without attaching to logger | Expected events not written | `logger.addHandler(handler)` and appropriate level |
| Leaving parent handler enabled in lab | Duplicate logs in console/file | Understand hierarchy and `setUseParentHandlers` |
| Not closing handler | Lock not released; output may be unflushed | `try/finally`, close before reading to verify |
| Letting JUL and logrotate rotate the same file | Rename/truncate race, empty active file | Single rotation owner and reopen policy |
| Using `copytruncate` and claiming zero log loss | Race condition drops bytes | Choose coordinated rolling and test |
| Only counting files without checking latest log | Rollover may occur while losing the last event | Assert latest sequence/event ID |
| Compressing/deleting archives while agent is still reading | Collector misses file tail | Optimize shipper lag and retention window |
| Running multiple JVMs on the same file | Lock/rename race and interleaved data | Separate paths per instance |
| Keeping archives indefinitely | Disk full and increased data risk | Retention + total cap + metrics |
| Treating `.gz` as encryption | Sensitive logs can be read | Access control and encryption |
| Assuming `logger.info()` not throwing is enough | Handler may report errors on a separate channel | Verify file/sink and backend errors |
| Ingesting both stdout and file into the same index | Duplicate events | Define a single collection source |

## 16. Self-Check Questions

**Q1.** Why does the lab generate 100 events, yet fewer than 100 lines remain at the end?  
**A:** Because `FileHandler` keeps at most three generations per `count=3`; older generations are replaced across multiple rollovers.

**Q2.** Does `FileHandler(limit=512)` mean a file will never exceed exactly 512 bytes?  
**A:** No. Rotation can happen after a record or at specific check points, so there is some variance around the threshold.

**Q3.** If you need daily rotation and archive compression, can you just change `count` in JUL?  
**A:** No. You need a rolling policy/backend or infrastructure that supports time-based rotation and compression, plus compatibility testing.

**Q4.** When an OS tool renames the active file, does the JVM automatically start writing to the new file?  
**A:** Not by default. The old file descriptor may still point to the renamed file; you need a reopen or backend-native rolling.

**Q5.** Does `copytruncate` completely eliminate the risk of log loss?  
**A:** No. There is a race condition between copying and truncating while the application is writing.

**Q6.** Does having three active/archive files prove the collector received all events?  
**A:** No. You must verify the agent, checkpoints, ACKs, queues, and data at the destination.

**Q7.** Why should you check file permissions and retention for archives, not just the active file?  
**A:** Archives still contain the original data, may include PII/secrets, and have additional copies across downstream hops.

**Q8.** In a container that only logs to stdout, is Java required to use `FileHandler`?  
**A:** No. Rotation can be handled by the container runtime/node agent; you still need to configure the shipper and test slow-collector scenarios.

**Summary:** Setting up rotation properly means **configuring triggers + file limits + handler lifecycle + verifiable results**. The Java 17 lab demonstrates byte-based rollover and generation-based retention. For production deployment, you must also consider file permissions, disk capacity, writer-to-shipper compatibility, deletion/compression policies, delivery retries, and security requirements. Only when these layers work together do you have a reliable file logging system.
