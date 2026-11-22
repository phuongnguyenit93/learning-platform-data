# Time-Based Rotation in Java Logging

## 1. Concept and Purpose

**Time-based log rotation** is a mechanism for rotating log files by time periods such as hour, day, week, or month. Instead of letting a single file grow indefinitely, the backend moves data from the previous period into a historical file (archive), optionally compresses it, and continues writing to the current file.

For example, a service writing logs by day:

```text
logs/
├── application.log                   # Active file
└── archive/
    ├── application.2026-11-07.log.gz
    ├── application.2026-11-08.log.gz
    └── application.2026-11-09.log.gz
```

The filenames and dates in the diagram are **illustrative**, not files guaranteed to exist on every run. A Logback configuration typically keeps a fixed active filename, such as `application.log`, while archives carry the name of the completed time period.

Common goals:

- Split logs to make searching and diagnosing by day/hour easier.
- Help collection tools read files and ship logs to a centralized system.
- Compress older files to reduce storage usage.
- Apply **retention** policies and cap total storage size.
- Avoid a single active file existing forever and growing too large.

**Distinguish three different things:**

1. **Trigger:** when does a log event cause the appender to decide a rollover is needed?
2. **Rollover:** how are files renamed, moved, newly opened, and archives compressed?
3. **Retention/cleanup:** how long are historical files kept and when are they deleted?

Putting a date in the filename **does not automatically guarantee** that the file is rotated on time, compressed, size-bounded, or retained for the exact number of days.

## 2. How Does Time-Based Rotation Differ from Size-Based Rotation?

| Strategy | Common Condition | Advantages | Limitations |
|---|---|---|---|
| **Time-based** | Moving to the next hour/day/month period | Archives are easy to identify by period | A high-load period can produce a very large file |
| **Size-based** | File exceeds a size threshold | Better control over individual file size | Does not automatically group files by date |
| **Size-and-time-based** | New period **or** file threshold reached | Groups by period while splitting high-load spikes | May produce multiple archives on the same day |
| **External rotation** | OS/scheduler/collector tool | Fits pipelines with unified policies | Can conflict with the JVM appender's file handle |

For example, a service normally produces 50 MB of logs per day, but on an incident day it produces 4 GB. If you only rotate by day, that day's file can become huge. When you need both **date-based naming** and protection against oversized files, you can use Logback's `SizeAndTimeBasedRollingPolicy`.

If the application only writes a few KB per day, pure time-based rotation is usually sufficient and simpler.

### Rotation Is Not Retention

- Rotation creates **historical files** or switches to a new file.
- Compression compresses historical files.
- Retention determines how long historical files exist or the total allowed size.
- Archiving may move history to another store, though it is not built into every rolling policy.

A configuration with rotation but **no retention** can still fill up the disk over time.

## 3. When Does Time-Based Rollover Happen?

Suppose a policy rotates by UTC day and the application logs:

```text
2026-11-09T23:59:58Z INFO event=order_received
2026-11-09T23:59:59Z INFO event=order_confirmed
2026-11-10T00:00:03Z WARN event=retry_scheduled
```

In a common setup with a fixed active file:

```text
Before the new day:
  logs/application.log
      contains data for period 2026-11-09

When processing the first log belonging to period 2026-11-10:
  rollover logs/application.log
      -> logs/archive/application.2026-11-09.log.gz
  continue logs/application.log for the new period
      -> write event=retry_scheduled
```

**Common misconception:** many rolling appenders perform rollover **on the first log event after the period boundary**, which does not mean a compressed file will necessarily appear right at 00:00.

For example, if the service logs nothing from 23:50 the previous day until 08:00 the next day, rollover may occur when the 08:00 log is processed. Compression/cleanup may also run on an internal schedule or asynchronously depending on the backend/version.

Therefore, do not write tests expecting an archive at exactly 00:00 if the policy is event-driven. If a system genuinely needs files closed **on a schedule independent of log traffic**, it needs a solution with proper scheduling and file-handle coordination.

## 4. Timezones Determine Period Boundaries

The same instant in time can have a different UTC date and local date:

```text
2026-11-09T16:59:59Z = 2026-11-09 23:59:59 Asia/Ho_Chi_Minh
2026-11-09T17:00:00Z = 2026-11-10 00:00:00 Asia/Ho_Chi_Minh
```

If rotating by **Vietnam day**, the boundary in the example is at 17:00 UTC; if rotating by **UTC day**, the boundary is at 00:00 UTC.

| Option | Best For | What to Check |
|---|---|---|
| UTC | Multi-region systems, centralized logging | Operators may query using a different local date |
| Business timezone | Reporting/reconciliation by local date | Every instance must use the same timezone |
| JVM/server default timezone | Quick configuration | May differ across IDEs, servers, and containers |

**Choose a timezone explicitly.** Simply adding a date to `fileNamePattern` without checking the timezone can cause two instances to write different dates in their filenames.

### 4.1. Java 17 Program Demonstrating Boundaries, Runnable Without External Libraries

The following example uses `Instant`, `ZoneId`, and `LocalDate` to demonstrate two different dates. It **does not create rolling files itself**; it is a verification of time rules before choosing a logger configuration.

Create `RotationBoundaryDemo.java`:

```java
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;
import java.time.ZoneOffset;

public final class RotationBoundaryDemo {
    public static void main(String[] args) {
        Instant before = Instant.parse("2026-11-09T16:59:59Z");
        Instant after = Instant.parse("2026-11-09T17:00:00Z");

        ZoneId utc = ZoneOffset.UTC;
        ZoneId vn = ZoneId.of("Asia/Ho_Chi_Minh");

        display(before, utc, vn);
        display(after, utc, vn);
    }

    private static void display(
            Instant instant, ZoneId utc, ZoneId vn) {
        LocalDate utcDate = instant.atZone(utc).toLocalDate();
        LocalDate vnDate = instant.atZone(vn).toLocalDate();

        System.out.println("instant=" + instant
                + " UTC=" + utcDate
                + " VN=" + vnDate);
    }
}
```

Compile and run with JDK 17+:

```bash
javac -encoding UTF-8 RotationBoundaryDemo.java
java RotationBoundaryDemo
```

**Exact stdout:**

```text
instant=2026-11-09T16:59:59Z UTC=2026-11-09 VN=2026-11-09
instant=2026-11-09T17:00:00Z UTC=2026-11-09 VN=2026-11-10
```

The two `Instant` values are one second apart, yet the application using Vietnam dates has already crossed into a new day. Most multi-region systems choose UTC for storage/observability and convert when displaying for business purposes; if local dates are required, document the rule clearly.

### 4.2. Daylight Saving Time (DST)

Some timezones observe daylight saving time: a day can be 23 or 25 hours long. If rotating by local hour, an hour label can be skipped or repeated. Archive names containing only date-hour may make it hard to distinguish two periods with the same label.

Using UTC avoids much of this confusion. If using a timezone with DST, test the transition dates, naming rules, and backend behavior; do not assume every day has 24 one-hour periods.

## 5. Does JUL FileHandler Support Time-Based Rotation?

`java.util.logging.FileHandler` (JUL) is built into the JDK and primarily supports rotation by **size** and **file count**; it does not have built-in date/time rolling policies like Logback or Log4j 2.

JUL example:

```java
import java.util.logging.FileHandler;
import java.util.logging.SimpleFormatter;

FileHandler handler = new FileHandler(
        "logs/application.%g.%u.log",
        10_000_000,
        5,
        true);
handler.setFormatter(new SimpleFormatter());
```

This is only a **Java fragment**, lacking a class, full imports, and ensuring the `logs` directory exists. The `10_000_000` parameter is the byte threshold and `5` is the generation file count; there is no "rotate at 00:00" parameter.

If a system currently uses JUL and needs daily rotation, consider:

- Switching to a backend with time-based rolling, using a bridge/adapter if you want to keep the logging API.
- Using an external rotation mechanism compatible with how JUL holds file handles.
- Writing a custom handler and scheduler with `flush`, `close`, reopen, locking, and failure handling; this is costly to test.

**Do not simply use a scheduled task to rename the file while FileHandler is still open and assume rotation was performed safely.** On some operating systems, the handle may continue writing to the old file; on others, renaming may fail or cause conflicts.

## 6. Logback TimeBasedRollingPolicy by UTC Day

In applications using **SLF4J API + Logback Classic backend**, `RollingFileAppender` combined with `TimeBasedRollingPolicy` is a common way to rotate files by time period.

Example `logback.xml`:

```xml
<configuration>
    <appender name="FILE"
              class="ch.qos.logback.core.rolling.RollingFileAppender">
        <file>logs/application.log</file>

        <rollingPolicy
                class="ch.qos.logback.core.rolling.TimeBasedRollingPolicy">
            <fileNamePattern>logs/archive/application.%d{yyyy-MM-dd,UTC}.log.gz</fileNamePattern>
            <maxHistory>7</maxHistory>
            <totalSizeCap>100MB</totalSizeCap>
            <cleanHistoryOnStart>true</cleanHistoryOnStart>
        </rollingPolicy>

        <encoder>
            <pattern>%level %logger{0} - %msg%n</pattern>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="FILE"/>
    </root>
</configuration>
```

This is a Logback configuration (not JUL or Log4j 2). Key elements:

| Element | Role |
|---|---|
| `<file>logs/application.log</file>` | Fixed active filename |
| `fileNamePattern` containing `%d{yyyy-MM-dd,UTC}` | Identifies the rotation period by **UTC day** |
| `.gz` suffix | Compresses archive files with gzip |
| `maxHistory=7` | Number of historical periods kept according to Logback's policy |
| `totalSizeCap=100MB` | Caps historical storage size via cleanup |
| `cleanHistoryOnStart=true` | Cleans history when the appender/policy starts if applicable |
| `root level="INFO"` | Selects emitted log level, independent of rotation schedule |
| `encoder` | Determines text formatting in the file |

The configuration uses `%d{yyyy-MM-dd,UTC}` in `fileNamePattern` to define the period in UTC. For patterns with multiple time components, you must determine which token controls the cycle according to Logback rules; here there is only one date token, so it is unambiguous.

### 6.1. Active File and Archive Files

When `<file>` is specified:

- During the period, events are written to `logs/application.log`.
- When the first event of a new period arrives, the backend can roll over the previous active file.
- The archive is named after the **previous period**; new period logs then continue in `logs/application.log`.
- Compression can take time; the `.gz` file does not necessarily appear instantaneously when the clock crosses the boundary.

If `<file>` is omitted, some Logback configurations derive the active filename from `fileNamePattern`. In that case, behavior and how collectors track paths differ; do not assume the same behavior as a fixed active file configuration.

### 6.2. TimeBasedRollingPolicy Is Not SizeBasedRollingPolicy

Pure `TimeBasedRollingPolicy` is driven by time. If a single period has 2 GB of logs, this configuration **will not automatically split it into multiple 20 MB files**. To combine size limits, use an appropriate combined policy.

### 6.3. Retention Notes

`maxHistory=7` is the number of **historical periods**, not a guarantee that "files are deleted at the exact 604,800th second." Cleanup is typically tied to rollover/startup and may execute asynchronously.

`totalSizeCap` limits historical storage within the policy's scope; it is not a hard filesystem quota nor does it guarantee the active file stays below the threshold. `cleanHistoryOnStart` helps handle history for infrequently run programs, but does not turn the policy into a per-second scheduled deletion service.

## 7. Runnable Maven + Java 17 Example with Logback Daily Rolling

This example creates a real log file using Logback and prints a stable stdout line for verification. Because it uses **a single small program**, the first run will not necessarily produce a compressed archive: to trigger daily rollover, events must actually occur across **two different time periods**.

### 7.1. Directory Structure

```text
daily-rotation-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── com/example/logging/DailyRotationDemo.java
        └── resources/
            └── logback.xml
```

### 7.2. The `pom.xml` File

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>daily-rotation-demo</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>ch.qos.logback</groupId>
            <artifactId>logback-classic</artifactId>
            <version>1.5.12</version>
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
                <configuration>
                    <mainClass>com.example.logging.DailyRotationDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

`logback-classic` brings Logback's backend/provider onto the runtime classpath and uses the matching SLF4J API. The versions here are **fixed example values**, not announcements of the latest releases or default security recommendations. Real projects should track supported versions and advisories.

### 7.3. The `src/main/resources/logback.xml` File

```xml
<configuration>
    <appender name="FILE"
              class="ch.qos.logback.core.rolling.RollingFileAppender">
        <file>logs/application.log</file>

        <rollingPolicy
                class="ch.qos.logback.core.rolling.TimeBasedRollingPolicy">
            <fileNamePattern>logs/archive/application.%d{yyyy-MM-dd,UTC}.log.gz</fileNamePattern>
            <maxHistory>7</maxHistory>
            <totalSizeCap>100MB</totalSizeCap>
            <cleanHistoryOnStart>true</cleanHistoryOnStart>
        </rollingPolicy>

        <encoder>
            <pattern>%level %logger{0} - %msg%n</pattern>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="FILE"/>
    </root>
</configuration>
```

Here, the appender only **writes to a file**, with no console appender attached. Therefore, `LOG.info` calls do not automatically appear on stdout.

### 7.4. The `src/main/java/com/example/logging/DailyRotationDemo.java` File

```java
package com.example.logging;

import ch.qos.logback.classic.LoggerContext;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public final class DailyRotationDemo {
    private static final Logger LOG =
            LoggerFactory.getLogger(DailyRotationDemo.class);

    public static void main(String[] args) {
        LOG.info("event=app_started service={}", "orders-api");
        LOG.debug("event=debug_probe");
        LOG.warn("event=dependency_slow attempts={}", 2);
        LOG.info("event=app_completed");

        // Demo ending: flush/close appenders via the official lifecycle.
        LoggerContext context =
                (LoggerContext) LoggerFactory.getILoggerFactory();
        context.stop();

        System.out.println("demo=completed emitted=3");
    }
}
```

In a real server application, the framework typically manages the `LoggerContext` lifecycle. **Do not stop the logger context after every request**; only do this in a terminating demo.

### 7.5. Running and Verifying Output

With JDK 17+, Maven, and dependency download access, run from the `daily-rotation-demo` directory:

```bash
mvn -q compile exec:java
```

**Stdout emitted by the Java code**:

```text
demo=completed emitted=3
```

Maven may print its own tool messages in different environments, but the line above is what the program prints.

If the configuration loads properly, the process has write permissions, starts in a fresh directory with no prior log files, and encounters no I/O errors, `logs/application.log` will contain:

```text
INFO DailyRotationDemo - event=app_started service=orders-api
WARN DailyRotationDemo - event=dependency_slow attempts=2
INFO DailyRotationDemo - event=app_completed
```

`DEBUG` is filtered out by the root INFO level. `%logger{0}` displays the short class name without changing the full logger name stored in the event.

**Do not expect to see an archive file after a single run lasting a few seconds.** Because a new UTC period has not started, the backend has no reason to roll over. To properly test rollover, write an integration test with controlled time and events across two periods; avoid changing the production system clock to force results.

## 8. Hourly, Monthly, and Other Time-Period Rotation

In Logback, the cycle is usually inferred from the precision of `%d` in `fileNamePattern`.

### 8.1. Hourly Files

```xml
<fileNamePattern>logs/archive/application.%d{yyyy-MM-dd_HH,UTC}.log.gz</fileNamePattern>
```

This is a **fragment** inside `TimeBasedRollingPolicy`, not a complete configuration. The pattern includes the hour `HH`, so the rotation period is hourly; this can be appropriate when daily log volume is very high.

### 8.2. Monthly Files

```xml
<fileNamePattern>logs/archive/application.%d{yyyy-MM,UTC}.log.gz</fileNamePattern>
```

A pattern precise to the month yields a monthly rotation period. Consider that a monthly file can grow too large. For high traffic, combine with a size trigger or use a shorter period.

### 8.3. Do Not Confuse Filename Format with Timestamps in Log Messages

`fileNamePattern` defines the period and archive name. `encoder.pattern` can contain `%d{...}` to display each event's timestamp. Both places may need the same timezone, but they are not the same property and are not interchangeable.

If a collector uses the filename for partitioning and message timestamps as query filters, standardize both the timezone and format.

## 9. Combining Daily and Size-Based Rotation

If a single day can generate a very large volume of logs, use Logback's `SizeAndTimeBasedRollingPolicy`:

```xml
<rollingPolicy
        class="ch.qos.logback.core.rolling.SizeAndTimeBasedRollingPolicy">
    <fileNamePattern>logs/archive/application.%d{yyyy-MM-dd,UTC}.%i.log.gz</fileNamePattern>
    <maxFileSize>20MB</maxFileSize>
    <maxHistory>7</maxHistory>
    <totalSizeCap>500MB</totalSizeCap>
</rollingPolicy>
```

This is a fragment used to replace `rollingPolicy` in an appropriate `RollingFileAppender`.

| Element | Effect |
|---|---|
| `%d` | Separates archives by UTC day period |
| `%i` | Sequence index for multiple files within the same period |
| `maxFileSize` | Adds a file-size trigger |
| `maxHistory` | Limits the number of historical periods |
| `totalSizeCap` | Caps total historical storage via cleanup |

Example archive output might look like:

```text
application.2026-11-09.0.log.gz
application.2026-11-09.1.log.gz
application.2026-11-09.2.log.gz
```

These names illustrate the use of `%i`, not a guarantee that three files will be produced when running a demo.

**Do not confuse** Logback's `%i` with `%g` in JUL FileHandler. Each backend has its own syntax. If you only need daily rolling, `TimeBasedRollingPolicy` is simpler with fewer knobs to tune.

## 10. Log4j 2: TimeBasedTriggeringPolicy in RollingFile

Log4j 2 uses the `RollingFile` appender with `TimeBasedTriggeringPolicy` to determine when rollover occurs based on the file pattern.

Example **`log4j2.xml`** configuration (not `logback.xml`):

```xml
<?xml version="1.0" encoding="UTF-8"?>
<Configuration>
    <Appenders>
        <RollingFile name="FILE"
                     fileName="logs/application.log"
                     filePattern="logs/archive/application-%d{yyyy-MM-dd}.log.gz">
            <PatternLayout pattern="%level %c{1} - %msg%n"/>

            <Policies>
                <TimeBasedTriggeringPolicy
                        interval="1" modulate="true"/>
            </Policies>

            <DefaultRolloverStrategy>
                <Delete basePath="logs/archive" maxDepth="1">
                    <IfFileName glob="application-*.log.gz"/>
                    <IfLastModified age="P7D"/>
                </Delete>
            </DefaultRolloverStrategy>
        </RollingFile>
    </Appenders>

    <Loggers>
        <Root level="info">
            <AppenderRef ref="FILE"/>
        </Root>
    </Loggers>
</Configuration>
```

Running this configuration requires Log4j 2 Core, a compatible API/provider, and read/write/delete permissions in the chosen directories. Log4j 2 config files are **not directly compatible** with the Logback schema.

Explanation:

- `fileName` is the active file being written to.
- `filePattern` uses the date to generate archive names.
- `interval="1"` means one period unit inferred from the pattern (here, days).
- `modulate="true"` aligns trigger intervals to time boundaries per the policy's logic, rather than simply adding an interval from startup.
- `Delete` with `IfFileName` restricts which files are considered; `IfLastModified age="P7D"` sets a file-age condition using an ISO-8601 duration.
- The cleanup condition is only an **example**; test thoroughly on a test directory before deploying because it can delete real data.

**Do not equate `age="P7D"` with Logback's `maxHistory=7`.** One evaluates file age, while the other counts historical periods. Cleanup actions may run at rollover or other lifecycle points; it is not a per-second deletion cron.

### 10.1. Timezones in Log4j 2

The example above **does not specify an explicit timezone**, because date pattern syntax and rollover mechanics should be checked against the Log4j 2 version in use. When you need UTC or local business time, pick a configuration supported by your version and verify actual archives; do not copy Logback's `%d{...,UTC}` details verbatim into Log4j 2 assuming identical semantics.

### 10.2. When to Use Log4j 2 Instead of Logback?

If the application already uses Log4j 2, leverage `RollingFile` and its policies. If you are already running SLF4J + Logback stably, there is no need to switch backends just for daily rolling. Switching backends affects dependencies/providers, config files, Throwable rendering, MDC, and collection pipelines.

## 11. Retention and Size Limits Must Be Designed Separately

A system can rotate files every day and still fill the disk if there is no cleanup. When designing, specify:

1. How many files are kept per period and in what compression format?
2. How many **historical periods** must be kept? How many **actual days of age**?
3. What is the maximum total archive size?
4. Are old files deleted on rollover, at startup, or on an independent schedule?
5. Has the agent/collector finished shipping data before files are compressed/deleted?
6. Are there audit, legal, or investigation requirements requiring longer retention?

### 11.1. maxHistory Is Not an Exact Countdown Timer

`maxHistory=7` in Logback relates to the number of historical periods; cleanup is typically event/lifecycle-driven and may be asynchronous. Do not promise "at exactly 00:00 on the eighth day, every file from seven days ago is deleted."

`cleanHistoryOnStart=true` is useful for applications that do not run continuously, though it still requires delete permissions and must be tested when the directory contains old archives from multiple instances/versions.

### 11.2. totalSizeCap Does Not Immediately Cap the Active File Size

Logback's `totalSizeCap` policy typically applies to archives cleaned up after evaluating history; it does not replace `maxFileSize` in a combined policy or a disk quota. If a traffic spike occurs mid-period, the active file can still grow very large even with `totalSizeCap` set.

### 11.3. Retention Does Not Guarantee Successful Collection

A file-reading collector may be down for hours. If archives are cleaned up before the collector catches up, data can be lost from the centralized system even though the application wrote it to disk. Compare the retention window against collector backlog, network downtime, and restore procedures.

**Never delete the active file**: Delete policies must be strictly scoped to the archive directory and exact `basePath`. Overly broad wildcards can delete files belonging to other services.

## 12. Multiple JVMs/Instances and Rotating the Same Path

Do not let multiple JVM processes/pods concurrently write to and rotate `logs/application.log` on a shared folder. Risks include:

- File lock or handle contention.
- Unsynchronized rollover rename/compress across two processes.
- One instance deleting archives that another instance still needs.
- Collector tracking the wrong inode/path, causing duplicate reads or missed lines.
- Interleaved writes or data loss during external rotation.

Controlled alternatives:

- Give each instance its own file/directory with a stable instance identifier.
- Or have instances write to stdout/stderr so the platform and collector aggregate logs centrally.
- Or use a logging system designed and verified for multi-process access.

Do not use `requestId` as a per-request filename: this creates too many files and stresses the filesystem. Request/trace IDs belong in the **event context**.

## 13. Rotation and Log Shippers/Collectors

A file-reading agent typically tracks offset and file identity. When a rolling appender moves `application.log` to an archive and reopens a new `application.log`, the agent must:

1. Finish reading the remainder of the old file when needed.
2. Detect the new file at the same path with a different identity.
3. Avoid re-reading already shipped data.
4. Handle archives being compressed or deleted in time.
5. Survive restarts of both the agent and the application.

Collector policies vary; you cannot assume every agent handles `.gz` files or every rename/copy-truncate scheme automatically.

**Do not enable both an in-JVM rolling policy and external `logrotate` on the same file** without a coordinated design. With rename, the appender may hold onto the old handle; with copy-truncate, lines written during the copy/truncate window can be lost or duplicated.

### Should You Use Files in Containers?

Many Kubernetes/container environments prefer stdout/stderr so the runtime handles rotation and agents handle collection. This reduces per-JVM file management responsibilities, though the platform still has quotas, buffers, retention, and log-loss risks.

Writing to files still makes sense for batch/desktop/legacy workloads or when local files are required, provided volumes, permissions, collectors, and shutdown are properly designed.

## 14. Async Logging and Time-Based Rolling

When wrapping `RollingFileAppender` inside `AsyncAppender`, producers typically enqueue events and a worker handles file writes later. This can reduce request latency but raises questions:

- Which period will an event created before midnight but processed after midnight be written to?
- When the queue is full, does the backend block or drop?
- On shutdown, does the worker flush the entire queue before the rolling appender closes?
- Are in-progress compression/cleanup tasks awaited or monitored?
- Can the log filename and event timestamp belong to different periods?

Behavior depends on the backend, version, and policy. **Do not rely on the archive name as the sole source of event time**, especially in multi-threaded async systems. Write full timestamps inside events and query collectors using the normalized time field.

Async also does not create durability on its own. Enqueued but unwritten events can be lost if the process is killed with `kill -9` or if the queue drops under overload. If logs are required for mandatory auditing, a separate durable pipeline is needed.

## 15. Security and Fault Tolerance

Time-based rotation does not automatically solve:

- File write permissions, archive read permissions, encryption in transit and at rest.
- Disk full, quotas, inode exhaustion, read-only filesystems, or failed mounts.
- Sensitive information in messages, Throwables, MDC, or structured fields.
- Log injection via newlines/control characters from user input.
- Failures in compression, renaming, or cleanup.
- Unflushed data, undrained async queues, and unshipped collector data.

The `.gz` suffix is only compression, **not encryption**. Avoid logging passwords, tokens, session cookies, API keys, and unnecessary sensitive data; use formatters/serializers that escape untrusted input.

Backends may report internal errors via status/error handlers rather than throwing exceptions on every `log.info(...)`. Pipeline monitoring and clear operational ownership are required.

For mandatory audit trails, especially financial transactions/auditing, file rolling is only an observability channel; it does not by itself satisfy durability, tamper-resistance, or exactly-once guarantees. You may need database transactions, transactional outbox, or a dedicated audit/event store.

## 16. Testing Time-Based Rotation

### 16.1. Testing Configuration Loading

Verify the actual backend is Logback, Log4j 2, or JUL, that the config file is being loaded, the appender has started, root level/filters allow events through, and the path is writable and unlocked.

If a logger filters out all events, no data reaches the rolling appender; you cannot conclude rotation is broken just because no archive exists.

### 16.2. Testing Two Time Periods

In an isolated test environment with a clock or test hook appropriate for the backend:

1. Log an event in the previous period.
2. Advance time across the day/hour boundary in a controlled manner.
3. Log an event in the next period.
4. Inspect the active file, archive, contents, and period name.
5. Monitor compression/cleanup until completion.
6. Verify no unexpected file loss or duplication.

Do not simply run a program for a few seconds and claim daily rotation must happen. Do not change a production machine's clock to force tests, as this affects timestamps, TLS, schedulers, and transactions.

### 16.3. Testing Overload and Restarts

- Generate high log volume within a single day to see if a size trigger is also needed.
- Restart the appender/JVM while old archives exist to test appending and cleanup.
- Test permission errors or disk-full scenarios in a test environment.
- Verify multiple instances do not rotate the same path concurrently.
- Stop the collector long enough and restart it to check for missed archives.

### 16.4. Testing Timezones/DST

Decide between UTC or local business time, and test around month/year rollovers and DST transitions if applicable. Check both timestamps inside logs and archive dates; do not rely on your terminal/IDE timezone if the server runs differently.

## 17. Troubleshooting: Why Is There No Daily Archive?

| Symptom | Common Cause | Resolution |
|---|---|---|
| No `.gz` after running 10 seconds | New period has not started | Wait for boundary or test with an appropriate clock |
| Past midnight with no archive | No log emitted after boundary or different timezone | Check new events and zone configuration |
| Archive has yesterday's date | File belongs to the period that just ended | Compare timestamps; do not assume it is a bug |
| Single-day file too large | Only time trigger is configured | Add a size-and-time policy if needed |
| Multiple files on the same day | `%i` is configured or multiple writers exist | Check size trigger and instances |
| Files older than 7 days remain | Cleanup depends on rollover/startup or misconfigured policy | Check maxHistory/Delete/status |
| No compressed file | Pattern missing `.gz`, compression unfinished/failed | Check backend internal logs |
| Archive deletion error | Permissions, path, or Delete filter wrong | Check basePath, glob, and permissions |
| Lost lines on rollover | Collector had not finished reading, external rotate conflict | Check end-to-end file → shipper flow |
| Collector misses new file | Not tracking file identity/scan interval | Configure shipper for rename/reopen |
| JUL not rotating daily | FileHandler defaults to size/count | Use an appropriate time-based solution |
| Confusing Logback with Log4j 2 | Incompatible configuration tags | Use the backend's own policy |
| Disk full despite cap | Cap applies only to history or cleanup delayed | Add quotas/monitoring/size trigger |
| File lock/rename failure | Multiple processes or filesystem error | Separate writers, check permissions and status |

### Diagnostic Steps

1. Identify the runtime logging API and backend.
2. Identify the actual loaded config file and active appender.
3. Check whether events of sufficient level reach the file sink.
4. Check the period inferred from the pattern and timezone.
5. Check whether an event occurred after the boundary.
6. Inspect rolling/compression/cleanup status and I/O errors.
7. Inspect collector/agent, inode, archive naming, and retention.
8. Adjust based on evidence rather than just renaming files and retrying.

## 18. Design Checklist and Conclusion

- [ ] Choose the right backend; do not mix Logback's `TimeBasedRollingPolicy` with Log4j 2's `TimeBasedTriggeringPolicy`.
- [ ] Explicitly define the hour/day/month period and UTC or local timezone.
- [ ] Understand that rollover may only occur when an event arrives after the boundary.
- [ ] Choose a fixed active filename or period-based filename and verify behavior.
- [ ] If traffic fluctuates heavily, consider a combined size-and-time policy.
- [ ] Define compression, retention, total size cap, and cleanup timing.
- [ ] Do not delete archives before the collector finishes reading them.
- [ ] Check file locks, multiple processes, container filesystems, and external rotation.
- [ ] Standardize event timestamps; do not rely solely on archive names.
- [ ] Monitor disk quotas, collector lag, and compression/cleanup errors.
- [ ] Test boundaries, DST, restarts, shutdown, async queues, and I/O errors.
- [ ] Protect sensitive data and separate the audit store if durability is required.

**Conclusion:** time-based rotation divides logs into defined periods for convenient management, compression, and collection. In Java, JUL's `FileHandler` mainly supports size/count; Logback provides `TimeBasedRollingPolicy` and `SizeAndTimeBasedRollingPolicy`; Log4j 2 uses `TimeBasedTriggeringPolicy` inside `RollingFile`. A sound solution must explicitly specify **timezone, trigger conditions, active filename, retention, multiple writers, and collectors**; simply adding a date to the filename is not enough.
