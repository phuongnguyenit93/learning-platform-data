# Retaining History Files During Log Rotation in Java

## 1. Meaning of Retaining History Log Files

**Retaining history files** is how you limit the log data kept after **log rotation** switches from the currently active file to a new one. Older files help with incident investigation, but if archives keep piling up without cleanup, disk usage can grow without bound. The goal is to **keep enough valuable data** within the allowed storage capacity, retention period, and security policy.

For example, an application performing size-based rotation:

```text
logs/
  application.0.log   <- current file
  application.1.log   <- previous generation
  application.2.log   <- older generation
```

There are three files in total, but only **two history files** alongside the current file. If you say “keep three backups” and configure “count=3” in JUL, you are likely off by one.

In Java, configuration depends on the **backend**:

- **JUL (`java.util.logging.FileHandler`):** `count` is the total **number of files in the rotation cycle**, including the current file. `count=3` typically yields generations 0, 1, and 2, with at most two older generations.
- **Logback (`RollingFileAppender` with `TimeBasedRollingPolicy`):** `maxHistory` is the **number of archive periods to keep** according to the pattern. With a daily filename pattern, `maxHistory=7` corresponds to seven daily periods, **not a guarantee of exactly seven files on disk at all times**.
- **Logback with `SizeAndTimeBasedRollingPolicy`:** a single day can produce multiple archives (incrementing `%i`); `maxHistory=7` still refers to seven daily periods, not seven files.
- **Logback’s `totalSizeCap`:** limits the **total size of archives** managed by the policy, not the absolute total size of all logs/active/backup files.

### Learning Objectives

After this lesson, you will be able to distinguish between active files, generations, archives, period counts, and storage caps; configure `FileHandler` in Java 17; use Logback’s `maxHistory`, `totalSizeCap`, `cleanHistoryOnStart`, and `maxFileSize`; verify actual file counts, cleanup lifecycle, common pitfalls, and design safe retention policies.

## 2. Key Terminology

| Term | Meaning | Example |
| --- | --- | --- |
| Active log | File currently receiving events | `application.log`, `history.0.log` |
| Generation | Position in a size-based rotation cycle | Generation `0`, `1`, `2` |
| Archive | File that has rolled out of the active state | `application.2026-01-12.log.gz` |
| Rotation trigger | Condition for switching files | Reaching a byte limit or entering a new daily period |
| `count` | Number of files in a JUL FileHandler cycle | 3 files total |
| `maxHistory` | Number of archive periods in Logback | 7 daily periods |
| `maxFileSize` | Target size per file in a size-and-time policy | 20MB |
| `totalSizeCap` | Total archive size threshold cleaned up by Logback | 1GB |
| Cleanup | Actual process of deleting old archives | On rollover or at startup depending on configuration |
| Retention | Contract for keeping data by time/count/size | 7 days, 1GB, 3 generations |

**Distinguishing files from events:** Log rotation manages **files**. It does not guarantee the number of events retained, does not guarantee durable event writes, and does not replace an audit mechanism with integrity requirements.

**Distinguishing local files from copies:** After sending logs to a collector, deleting a local archive does not mean copies in OpenSearch, Loki, object storage, or backups are also deleted. Retention policies must cover every relevant copy.

## 3. JUL FileHandler: `count` Includes the Active File

Java 17 includes `java.util.logging.FileHandler`. It can be constructed with four parameters:

```java
FileHandler handler = new FileHandler(
        "logs/application.%g.log",
        1_000_000,
        3,
        false);
```

This is a **Java snippet**, assuming `java.util.logging.FileHandler` is imported and the `logs` directory exists. Meaning:

1. **`pattern`:** filename pattern; `%g` is the generation number.
2. **`limit`:** approximate number of bytes written to a single file before rotating; 1,000,000 bytes, not one million events.
3. **`count`:** total number of files used in the rotation cycle; `count=3` means three generations, **not three old files plus one current file**.
4. **`append`:** whether to append to an existing file when opening; `false` does not guarantee that data from previous runs remains intact.

### 3.1. Relationship Between `count` and History Files

| FileHandler `count` | Files in rotation cycle | Old generations alongside active |
| ---: | ---: | ---: |
| 1 | 1 | 0 |
| 2 | 2 | 1 |
| 3 | 3 | 2 |
| 4 | 4 | 3 |
| 5 | 5 | 4 |

This table assumes the application has written enough logs for all generations to be created, a single FileHandler manages the file set without contention, and lock files or files from other processes are not counted.

If the requirement is **“keep three history files and one current file”**, the corresponding JUL setting is typically **`count=4`**.

### 3.2. How Size-Based Rotation Works

Suppose there are three files:

```text
application.0.log   <- currently writing
application.1.log   <- old
application.2.log   <- oldest
```

When the current file reaches the threshold, FileHandler rotates the generations and opens a new active generation. The oldest generation is no longer kept in the finite cycle. You should not rely on file indices 0/1/2 to infer exact retention duration, because events per day and the size of each event vary.

`limit` is an **approximate** threshold: a sufficiently large record can cause the file to exceed the limit before rollover occurs. The disk usage of one cycle is roughly `count × limit`, **not a hard filesystem quota**; there are also lock files, metadata, files from other Handlers, and records that overshoot the threshold.

### 3.3. Filename Patterns

JDK FileHandler supports several tokens:

| Token | Function |
| --- | --- |
| `%g` | Generation number 0, 1, 2, ... |
| `%u` | Unique number to resolve filename conflicts |
| `%t` | System temporary directory |
| `%h` | User home directory |
| `%%` | Literal percent sign |

For example, `history.%g.log` with `count=3` can produce `history.0.log`, `history.1.log`, `history.2.log`. If `%g` is omitted from the pattern while `count` is greater than 1, FileHandler automatically appends the generation number to the generated filename.

`%u` can be used to avoid collisions when multiple Handlers/processes open the same name. According to the JDK documentation, unique ID disambiguation is reliably guaranteed on a **local filesystem**, not as a durable shared-file mechanism across multiple JVMs on a network filesystem.

### 3.4. Formatting, Level, and Lifecycle

By default, FileHandler uses `XMLFormatter` if not reconfigured. For readable text logs, attach `SimpleFormatter` or a custom `Formatter`.

```java
handler.setLevel(java.util.logging.Level.INFO);
handler.setEncoding("UTF-8");
handler.setFormatter(new java.util.logging.SimpleFormatter());
```

This snippet operates on an already-created `handler`. The **Logger** level must also allow the event through before the Handler filters it. If the Logger blocks FINE while the Handler allows FINE, the record will still not appear.

Create the Handler at application startup, not per request. On normal shutdown, remove the Handler from the Logger and call `close()` to release file handles/locks. `FileHandler` may create a `.lck` file while active; that is **not** a history log generation.

## 4. Standalone Java 17 Example: Keeping Three File Generations

This example runs with **plain JDK 17**, without Maven/Gradle or external libraries. It creates a fresh temporary directory to avoid stale data and naming collisions; uses a small byte limit and enough events to guarantee rollovers; closes the FileHandler, and then inspects the generation files.

### 4.1. Create `HistoryFilesDemo.java`

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.logging.FileHandler;
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class HistoryFilesDemo {
    public static void main(String[] args) throws IOException {
        Path directory = Files.createTempDirectory("jul-history-");

        int limitBytes = 128;
        int fileCount = 3;
        Logger logger = Logger.getLogger("demo.rotation.history");

        logger.setUseParentHandlers(false);
        logger.setLevel(Level.INFO);

        FileHandler handler = new FileHandler(
                directory.resolve("history.%g.log").toString(),
                limitBytes,
                fileCount,
                false);

        handler.setLevel(Level.INFO);
        handler.setEncoding(StandardCharsets.UTF_8.name());
        handler.setFormatter(new Formatter() {
            @Override
            public String format(LogRecord record) {
                return record.getLevel().getName()
                        + " " + formatMessage(record)
                        + System.lineSeparator();
            }
        });

        logger.addHandler(handler);
        try {
            for (int i = 0; i < 40; i++) {
                logger.info("event=history.test index=" + i
                        + " payload=" + "X".repeat(100));
            }
        } finally {
            logger.removeHandler(handler);
            handler.close();
        }

        int existing = 0;
        for (int generation = 0; generation < fileCount; generation++) {
            String name = "history." + generation + ".log";
            boolean present =
                    Files.isRegularFile(directory.resolve(name));
            if (present) {
                existing++;
            }
            System.out.println(name + "=" + present);
        }
        System.out.println("totalFiles=" + existing);
    }
}
```

### 4.2. Compile and Run

```bash
javac HistoryFilesDemo.java
java HistoryFilesDemo
```

**Exact stdout when the program has write permission to the temporary directory on a local filesystem:**

```text
history.0.log=true
history.1.log=true
history.2.log=true
totalFiles=3
```

The output intentionally omits random temp directory paths or timestamps. It only confirms that **three generation files exist**, without asserting the record count per file or the survival of all 40 events. Older records are evicted from the rotation cycle by design.

### 4.3. Why Is the Result Deterministic?

- `Files.createTempDirectory` creates a fresh directory containing no generations from previous runs.
- `count=3` bounds the file set to generations 0, 1, and 2.
- Each message has 100 `X` characters plus other fields, large enough to repeatedly exceed the 128-byte limit; 40 messages trigger multiple rollovers.
- The Logger does not forward logs to parent Handlers, so stdout only contains the file-check output.
- The custom Formatter does not print XML headers/footers.
- `handler.close()` is executed before checking the files.

If the temporary directory cannot be created or the filesystem reports an error, the program may throw an `IOException` instead of printing the sample stdout; that is an environmental condition, not retention behavior.

### 4.4. Follow-Up Experiments

- Change `fileCount` from 3 to 2: after multiple rollovers there are two generations; only one old generation remains alongside the active file.
- Change `fileCount` to 5: increases the number of slots, so older data can persist longer for a similar volume.
- Set `limitBytes` very large while emitting only a few events: **not enough generations may be created** to observe the full `count` of files.
- Change `append=false` to `append=true`: with a directory that already contains logs, open/append behavior and rollover timing must be tested separately. In an example that creates a fresh directory, this difference does not sufficiently exercise restart scenarios.

## 5. Logback: Time-Based `maxHistory`

With **SLF4J + Logback Classic**, a common setup is `RollingFileAppender` paired with `TimeBasedRollingPolicy`. Example of a **complete `logback.xml` file**:

```xml
<configuration>
    <appender name="FILE"
              class="ch.qos.logback.core.rolling.RollingFileAppender">
        <file>logs/application.log</file>

        <rollingPolicy
              class="ch.qos.logback.core.rolling.TimeBasedRollingPolicy">
            <fileNamePattern>logs/archive/application.%d{yyyy-MM-dd}.log.gz</fileNamePattern>
            <maxHistory>7</maxHistory>
            <totalSizeCap>1GB</totalSizeCap>
            <cleanHistoryOnStart>true</cleanHistoryOnStart>
        </rollingPolicy>

        <encoder>
            <pattern>%d{yyyy-MM-dd HH:mm:ss.SSS,UTC} %-5level %logger{36} - %msg%n</pattern>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="FILE"/>
    </root>
</configuration>
```

Place the file on the runtime classpath of a Logback-backed application, such as `src/main/resources/logback.xml`. This configuration is for **Logback**, not JUL `FileHandler`. Ensure the application selects the right SLF4J backend, the path is writable, and the Appender starts successfully.

### 5.1. Meaning of the Options

- `<file>logs/application.log</file>`: path to the **currently active file**.
- `fileNamePattern` containing `%d{yyyy-MM-dd}`: each daily period gets a date-based archive name; `.gz` enables compression per the configuration.
- `maxHistory=7`: keeps **seven archive periods** on a daily cadence. Do not read this as “seven files, including active”.
- `totalSizeCap=1GB`: limits the **total size of archives**; the active file and copies in other systems are not summed as if they shared a single cap.
- `cleanHistoryOnStart=true`: runs old-archive deletion when the Appender starts, useful for short-lived jobs that do not run long enough to trigger a rollover.
- Encoder: controls content formatting; it does not determine generation counts.

### 5.2. `maxHistory` Is Not a Hard Physical File Count Limit

If using one archive per day:

```text
logs/application.log
logs/archive/application.2026-01-11.log.gz
logs/archive/application.2026-01-12.log.gz
...
```

In normal operation, seven daily periods may correspond to roughly seven archives alongside the active file. However, old files might not have been deleted yet because cleanup only runs at certain times, or there may be multiple archives within the same period if a different policy is used. Therefore, **do not write a test asserting “maxHistory=7 means the directory always has exactly seven files”**.

**Specifically: `maxHistory=0` in TimeBasedRollingPolicy does NOT mean “keep zero old files”**. It **disables history-based archive removal**, so archives can accumulate unless an external cleanup runs.

### 5.3. When Does Logback Clean Up Old Files?

In Logback, archive cleanup normally runs **during rollover**. If the application stops before a rollover occurs or emits very few events, old files may not be cleaned up yet. `cleanHistoryOnStart=true` requests cleanup immediately when the Appender starts.

Archive deletion can be **asynchronous**, so inspecting the directory at a single instant is not proof that the policy failed to run. Do not delete files immediately with an external script without understanding which Appender owns the active/archive files.

## 6. Limiting Storage with `totalSizeCap`

`maxHistory` bounds **time/periods**, but a peak traffic day can write gigabytes of logs. `totalSizeCap` adds a cap on total archive size.

Example XML snippet inside `rollingPolicy`:

```xml
<maxHistory>14</maxHistory>
<totalSizeCap>2GB</totalSizeCap>
```

This does **not** guarantee keeping a full 14 days. When volume spikes, the size cap can force Logback to delete older archives before 14 periods elapse. Logback applies the history limit and then the total archive size cap; `totalSizeCap` requires `maxHistory` to also be set.

Distinguish between:

- **Archive total:** data that has rolled over and belongs to the rolling policy.
- **Active file:** the current file, which can grow during the period and is not counted as an archive yet.
- **Files outside the pattern:** temporary files, logs from other modules, OS-created files.
- **Collector/backup:** data already replicated to other systems.

Thus `totalSizeCap=1GB` does not guarantee the entire server's logs directory stays under 1GB. Set disk/volume alerts at the deployment level.

### 6.1. Conflict Between Time and Storage

Suppose a service writes an average of 500 MB/day. Keeping 14 days typically requires far more than 2GB of storage before accounting for compression or spikes. If the archive cap is 2GB, actual retention may be much shorter.

You must choose a policy with clear priorities: enough days for investigation, fixed disk budget, reduced log volume, increased storage, or shipping archives to another store. Changing `maxHistory` alone cannot satisfy conflicting constraints.

## 7. SizeAndTimeBasedRollingPolicy: Multiple Files Per Day

When you need to bound both **individual file size** and **daily periods**, Logback provides `SizeAndTimeBasedRollingPolicy`. Replacement snippet for `rollingPolicy` in section 5:

```xml
<rollingPolicy
      class="ch.qos.logback.core.rolling.SizeAndTimeBasedRollingPolicy">
    <fileNamePattern>logs/archive/application.%d{yyyy-MM-dd}.%i.log.gz</fileNamePattern>
    <maxFileSize>20MB</maxFileSize>
    <maxHistory>7</maxHistory>
    <totalSizeCap>1GB</totalSizeCap>
    <cleanHistoryOnStart>true</cleanHistoryOnStart>
</rollingPolicy>
```

This is **not yet a standalone `logback.xml`**, as it must be placed inside an Appender with an encoder and referenced by a Logger/root. When using size-and-time, **both `%d` and `%i` are required** in the archive pattern: `%d` is the time period, and `%i` is the archive index within that period.

Example on a high-event day:

```text
application.2026-01-12.0.log.gz
application.2026-01-12.1.log.gz
application.2026-01-12.2.log.gz
application.2026-01-13.0.log.gz
application.2026-01-13.1.log.gz
```

Here there are **five archive files but only two daily periods**. With `maxHistory=7`, the system can retain multiple files for each of the seven periods, not capping total file count at seven. `totalSizeCap` may delete older archives sooner if total size exceeds the limit.

**Do not default to size-and-time for every service:** size-based rollover adds file renames and extra archives, bringing overhead and complexity. If the requirement is simply capping total archives by day, `TimeBasedRollingPolicy` with `totalSizeCap` may be sufficient.

## 8. Distinguishing Three Types of Retention Requirements

| Requirement | Typically suitable configuration | What must not be inferred |
| --- | --- | --- |
| At most three rotating files, **including active** | JUL `count=3` | Not three backups |
| Keep three old files alongside one active file | JUL `count=4` for one Handler | Not three days of retention |
| Keep seven daily archive periods | Logback daily `maxHistory=7` | Not guaranteed to be exactly seven files on disk |
| Total archives capped at roughly 1GB | Logback `maxHistory` + `totalSizeCap=1GB` | Does not include active files or external copies |
| Daily archives, each targeting at most 20MB | Size-and-time + `maxFileSize=20MB` | Not limited to one file per day |
| Retain complete transaction audits per regulation | Dedicated audit store with durability/retention | Rolling files do not provide transactional guarantees |

Before setting any numbers, ask: “How many files **in total**, how many **old files**, how many **daily periods**, how many **bytes**, and which copies are counted?”.

## 9. Estimating Storage Before Deployment

A rough sizing calculation:

```text
Daily log volume ≈ events per day × average bytes per event
Days under archive cap ≈ allowed archive size / daily log volume
```

Example: 200,000 events per day, averaging 500 bytes/event:

```text
200,000 × 500 = 100,000,000 bytes/day
```

With roughly 1GB of archive space (using ~1 billion bytes as a convention), on average this corresponds to about **10 days** before compression and overhead. This is only an illustration, not a guarantee of ten-day retention:

- A single exception stack trace can be much larger than an INFO line.
- Enabling DEBUG can increase volume by an order of magnitude or more.
- Log data has varying compression ratios.
- Peak hours/peak days differ from averages.
- The active file is not counted toward the archive cap.
- Logs duplicated across multiple Appenders/collectors consume additional storage.

Measure actual volume, budget headroom for traffic spikes, and set disk alerts. Do not use average formulas to infer mandatory retention for audit events.

## 10. Restarts, I/O Errors, and Non-Instant Cleanup

### 10.1. Restarts

In JUL, `append` affects how existing files are opened, and `count` controls the generation ring. Post-restart state also depends on existing files, sizes, lock files, and exact paths. Do not conclude from a low-volume run that retention is broken just because not all generations appear yet.

In Logback, `cleanHistoryOnStart` helps for short-lived applications; if disabled, cleanup normally waits for a rollover. Do not rely on merely changing config to guarantee old files are deleted **immediately**.

### 10.2. Crashes and Abrupt Shutdowns

Events still in buffers, async queues, or not yet flushed can be lost when a process terminates uncleanly. Archives may still be compressing or cleanup jobs may be incomplete. `count`, `maxHistory`, and `totalSizeCap` **do not guarantee every event is durably written**.

If auditing requires durability or tamper-resistance, use a dedicated audit/storage system with its own contract rather than just calling `logger.info()`.

### 10.3. Application Rotation vs. OS Rotation

Do not let Logback/JUL **simultaneously** rotate a file that a tool like `logrotate` also renames or copytruncates, unless the interaction has been explicitly designed and tested. Two mechanisms can cause lost logs, writes to stale files, or duplicate events in collectors. There should be **a single owner managing rotation** for any given log stream.

For containers, it is usually simpler for the application to write to stdout/stderr and let the runtime/collector manage container log files. Retention then belongs primarily to the collection platform rather than numerous local FileHandlers.

## 11. Multiple JVMs or Multiple Modules Multiply File Counts

A Handler with `count=3` does not mean the host has only three files. With three independent JVMs, each JVM keeps three generations:

```text
instance-A: 3 files
instance-B: 3 files
instance-C: 3 files
total:      9 files
```

Similarly, if an application has five per-module RollingFileAppenders, each Appender manages its own history. `maxHistory=7` applies **per policy**, not as a total of seven archives across the entire application.

### 11.1. Multiple Writers on the Same Path

Multiple processes using the same filename can contend over locks, renames, and rotation. FileHandler’s `%u` helps disambiguate some filenames when another process holds a file, but it is not a reliable multi-process shared rotation mechanism across all filesystems. Separating namespaces per instance or using a collector is safer.

### 11.2. Access Permissions and Sensitive Data

Old log files can still contain data the application has stopped writing. Retention should be paired with:

- Field allowlisting; never log passwords, tokens, cookies, or sensitive card numbers.
- Least-privilege read permissions on log files and archives.
- Encryption and backups where policy requires.
- Deletion policies for copies in centralized logging systems.
- Escaping messages containing newlines/control characters to prevent log injection.
- Fixed, trusted log paths; never construct paths from client input.

Deleting an archive on the host does not mean data in the collector is automatically deleted.

## 12. Monitoring Retention in Production

A valid configuration alone does not prove history logs are retained and deleted properly. Verify in order:

1. Identify the actual backend: JUL, Logback, or another system; avoid mixing syntax.
2. Identify **active files**, archives, generations, locks, and files from other processes.
3. Check actual file sizes against limits and available disk space.
4. Run a test workload to trigger at least several rollovers.
5. Inspect the final generation files and how old files are replaced.
6. For Logback, verify `maxHistory` by period rather than simply counting files.
7. Confirm cleanup on rollover and on startup if `cleanHistoryOnStart` is enabled.
8. Test restarts and inspect remaining files and append/rotation behavior.
9. Verify the collector tracks files across renames and compression without double-ingesting.
10. Set alerts for disk full, abnormal archive growth, or cleanup errors.

In systems with multiple copies, log retention must be managed across the **entire pipeline**: application → file/stream → agent → collector → storage and backup.

## 13. Common Pitfalls When Retaining History Files

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Wanted three backups, but JUL only keeps two old files | `count=3` includes the active file | Set `count=4` to keep three old generations |
| JUL `count=3` shows only one file | Not enough rollovers have occurred yet | Check volume and `limit`, write more logs |
| FileHandler exceeds `limit` by a few bytes | `limit` is an approximate threshold | Leave headroom; do not treat it as a hard quota |
| `.lck` file exists while the program is running | FileHandler uses a lock file | Do not count lock files as history files |
| JUL filenames have unexpected generation/unique suffixes | Missing `%g` or collision triggered `%u` | Check pattern and active writer processes |
| FileHandler outputs XML | Default `XMLFormatter` not replaced | Set `SimpleFormatter` or a custom `Formatter` |
| Logback keeps more than seven files despite `maxHistory=7` | Multiple archives per period or cleanup hasn't run | Check policy, `%d`/`%i`, and lifecycle |
| `maxHistory=0` causes archives to grow indefinitely | Value 0 disables history-based archive removal | Set a finite limit |
| Archives deleted before seven periods | `totalSizeCap` is too low or external cleanup ran | Compare log volume against size cap |
| Logs directory exceeds 1GB despite `cap=1GB` | Active files or other files sit outside the archive cap | Check total disk usage and policy ownership |
| One file rotated by multiple processes | Filename/path contention | Separate files per instance or use stdout/collector |
| Restart changes files unexpectedly | Append, rollover, or startup cleanup behaves differently than expected | Test specifically for your backend and version |
| File deleted but disk space not freed | Process still holds an open file descriptor | Check writer/OS and lifecycle |
| Collector drops or duplicates events on rollover | Agent does not handle rename/archive properly | Check offsets, inodes, rotation, and compression |
| Investigation data missing during an incident | Retention is shorter than detection time | Increase storage or ship archives to an appropriate store |

**Debugging workflow:** check configuration → active logger/handler/appender → filename pattern and working directory → rollover trigger → cleanup → filesystem/collector. Do not change multiple variables at once, to avoid obscuring the root cause.

## 14. Pre-Deployment Checklist

- [ ] Decided whether retention is defined by **total files**, **history files**, **daily periods**, or **storage size**.
- [ ] Understood that JUL `FileHandler.count` is **total files**, including the active file.
- [ ] Understood that Logback `maxHistory` is the number of retained time periods, not a hard physical file count.
- [ ] Chosen `limit` or `maxFileSize` based on real volume, knowing it does not guarantee exact per-byte/event quotas.
- [ ] Configured `totalSizeCap` if total archive size must be bounded, understanding it excludes active files and external backups.
- [ ] Set a `cleanHistoryOnStart` policy suited to short-lived jobs and real rollout patterns.
- [ ] Verified `fileNamePattern` includes required tokens: `%g` for JUL, `%d` and `%i` for Logback size-and-time.
- [ ] Distinguished active files, archives, generations, and lock files.
- [ ] Verified write permissions, trusted paths, disk capacity, and disk monitoring.
- [ ] Ensured no two independent mechanisms rotate the same path unless designed for it.
- [ ] Controlled sensitive data, read permissions, encryption, and retention of copies.
- [ ] Tested multiple rollovers, restarts, simulated crashes, volume spikes, and collector tailing.
- [ ] Avoided using rolling files as the sole audit store where transactional guarantees are required.
- [ ] Configured alerts and runbooks for failed cleanup or premature log loss.

### Official Technical Documentation

- [Java 17 — FileHandler](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/FileHandler.html): pattern, limit, count, append, generation, and lock.
- [Logback RollingFileAppender](https://logback.qos.ch/manual/appenders-rolling.html): TimeBasedRollingPolicy, maxHistory, totalSizeCap, cleanHistoryOnStart, and SizeAndTimeBasedRollingPolicy.
- [Logback Configuration](https://logback.qos.ch/manual/configuration.html): Appender lifecycle and configuration loading.
- [SLF4J Manual](https://www.slf4j.org/manual.html): facade and backend selection.

**Conclusion:** To **retain history files** accurately, you must first choose the **right unit**. In JUL, `count=3` means **three generations including the active file**, leaving only two old files alongside it. In time-based Logback, `maxHistory=7` refers to **seven archive periods**, not a promise of always having exactly seven files; `totalSizeCap` can reduce retained archives when volume is high. Never treat a single config value as an absolute guarantee: test rollovers, startup cleanup, storage, permissions, crashes, and your actual collector.
