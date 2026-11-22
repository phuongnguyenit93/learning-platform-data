# Deleting Expired Log Files in Java — Retention Policies After Log Rotation

## 1. What is deleting expired log files?

In a continuously running Java system, logs are written to the console, files, or a centralized system. When using **file logging**, data accumulates by day, by traffic volume, or by size. **Log rotation** is the process of moving the currently active file to an archive file and continuing to write to a new file; **retention/cleanup** is the policy that determines which archives have exceeded their allowed storage period and can be deleted.

Example:

```text
logs/
  app.log                           <- active file being written
  archive/
    app-2026-10-01.log.gz           <- old archive
    app-2026-10-25.log.gz           <- recent archive
    app-2026-11-08.log.gz           <- yesterday's archive
```

If operations specify keeping archives for about 30 days, the cleanup job can evaluate aged-out archives; **it must not blindly delete `app.log` while the application is writing to it**. Nor should it arbitrarily delete files belonging to other modules, files not yet picked up by a collector, or records that must be preserved for investigation.

Two activities must be distinguished:

- **Rollover/rotation:** decides *when to create a new log generation*; for example, when the file exceeds 10 MB or when a new day begins.
- **Deletion/retention:** decides *which archives no longer need to be kept*; for example, files that are 30 days old, exceed the retained file count, or exceed the total allowed storage size.

**Deleting files cannot be treated as a harmless operation.** Deleted files may contain investigative evidence or be the only copy of certain events. The policy must have a clear scope, conditions, owner, and verification method.

## 2. How do rotation, retention, backup, and ingestion differ?

| Concept | Goal | Example | Limitation |
| --- | --- | --- | --- |
| **Rotation** | Replace the active file with a new generation. | `app.log` is archived daily. | Does not include a deletion deadline by default. |
| **Time retention** | Select archives by age or calendar period. | Keep 30 daily archive periods. | Not identical to keeping exactly 30 × 24 hours. |
| **Count retention** | Limit the number of archive files/generations. | Keep at most 10 generation files. | A single day can produce multiple files. |
| **Size retention** | Limit total archive storage size. | Total archives at most 5 GB. | May evict recent files during log spikes. |
| **Backup** | Create a recoverable copy. | Store on controlled object storage. | Rotation does not automatically create an independent backup. |
| **Log ingestion** | Collect and store events for querying. | Shipper forwards logs to a central store. | Deleting too early can lose unread logs. |

A system can configure both **30 retention periods and a 5 GB maximum** simultaneously. However, if the organization **requires retaining logs for a minimum of 30 days**, setting a size cap that is too small can cause a conflict: files get deleted before the retention period ends. This must be resolved in storage design, ingestion, or an approved policy—never by arbitrarily deleting mandatory data to free disk space.

**Deleting local archives does not mean deleting logs everywhere.** Collectors, search indexes, object storage, backups, and filesystem snapshots have their own retention policies. Conversely, if there is no second copy, deleting local files can cause the information to disappear completely.

## 3. Conditions for a proper retention policy

Before enabling automatic deletion, answer:

1. **Who owns the archives?** An appender, a service, an OS scheduler, or a log management system? Avoid multiple owners deleting the same files.
2. **Which directory is allowed for deletion?** Prefer separating the active `logs/app.log` from `logs/archive/`.
3. **Which filenames are allowed?** For example, only `app-YYYY-MM-DD-i.log.gz`, not all `*.log` files on the volume.
4. **How is "expired" measured?** From last-modified time, the date in the filename, archive creation time, or a daily/monthly period?
5. **How are boundary thresholds handled?** Delete when *older than* 30 days or *at least 30 days old*?
6. **Is there a minimum retention requirement?** Audits, security, customer contracts, or legal holds may prohibit deletion even past the age threshold.
7. **Is the archive complete?** Do not select files that are currently being compressed, renamed, uploaded, or still in use by a writer/shipper.
8. **When does the job run?** On rollover, at startup, or on an independent schedule?
9. **Is there a dry-run mode?** You must be able to preview the list of files and byte count scheduled for deletion before enabling it for the first time.
10. **What happens on error?** Permission errors, locks, disk issues, symlinks, and collector lag must be reported, not silently treated as success.

A safe policy can be stated clearly as:

> "Only delete archives whose names belong to the allowlist within the service-owned archive directory, have finished writing, and are past the policy age. Do not delete active logs, symlinks, files of other applications, files under legal hold, or files that have not met collection requirements. Each cleanup run records file/byte counts and errors."

**30 days in these examples is purely a learning assumption**, not a Java default retention period or a universal legal requirement.

## 4. Determining "file age": mtime, filename date, and archive periods

### 4.1. Age by absolute timestamp

If the requirement is "older than 30 times 24 hours," Java 17 provides `Instant` and `Duration`:

```java
import java.time.Duration;
import java.time.Instant;

Instant cutoff = Instant.now().minus(Duration.ofDays(30));
```

Compare `Files.getLastModifiedTime(path).toInstant()` with the cutoff. If using `modified.isBefore(cutoff)`, a file **exactly equal to the cutoff is kept**. If using `!modified.isAfter(cutoff)`, a file **equal to the cutoff is also selected**. The policy must decide this upfront.

With a fixed reference time of `2026-11-09T00:00:00Z`, 30 × 24 hours earlier is `2026-10-10T00:00:00Z`:

| Archive `mtime` | Compared to cutoff | Result with `isBefore` |
| --- | --- | --- |
| `2026-10-01T00:00:00Z` | Older | Delete if within scope and conditions are met. |
| `2026-10-10T00:00:00Z` | Equal | Keep. |
| `2026-10-25T00:00:00Z` | Newer | Keep. |

### 4.2. Age by daily/monthly periods

If a system creates archives daily using the `%d{yyyy-MM-dd}` pattern, configuring it to keep 30 daily periods is a way of retaining **daily log groups**, which is not always equivalent to an exact 720-hour threshold.

With **monthly** rollover, Logback's `maxHistory=6` can mean six monthly periods. Do not translate `maxHistory=30` into "30 files" or "30 days" if the pattern is not daily or if multiple files can be created per period.

### 4.3. Do not assume filename equals mtime

A file named `app-2026-10-01.log.gz` may have been copied or recompressed on Nov 09, giving its last-modified time a new value. Conversely, backup/restore operations can also preserve an old mtime.

Therefore:

- **Filter by mtime:** suitable if mtime is the authoritative age source; you must understand the impact of copying/compressing.
- **Filter by date in filename:** requires a strict filename parser, clear timezone/period semantics, and avoiding trusting arbitrary input.
- **Filter by storage metadata:** can make sense when archives live in object storage with an official lifecycle policy.

Do not automatically mix age sources without defining which field is authoritative.

## 5. Prefer letting the rolling framework manage its own files

In applications using **Logback** or **Log4j 2**, you should leverage the rolling appender and retention policy when they meet your needs. The framework knows the naming pattern and rollover timing of archives, which generally reduces the risk of accidental deletion compared to a script scanning an entire directory.

A clear design:

```text
Application Logger
       |
RollingFileAppender
       |
       +--> active: logs/app.log
       |
       +--> archives: logs/archive/app-<date>-<index>.log.gz
                              |
                         Retention policy
                              |
                     delete only matching archives
```

**Deletion is usually tied to rollover time, not an independent clock.** In many configurations, rollover only occurs when a log event arrives after the time boundary. A service that emits no logs for a week may not trigger archive cleanup even if archives have expired; when it restarts or emits a new log event, the mechanism gets a chance to run.

If you need strict cleanup deadlines even when the application is idle or stopped, you need a solution with an independent scheduler or a storage lifecycle policy with an appropriate contract.

## 6. Logback: TimeBasedRollingPolicy, maxHistory, and totalSizeCap

Logback supports `RollingFileAppender` and `TimeBasedRollingPolicy`, allowing scheduled archive rotation and automatic cleanup of old periods.

Example `logback.xml` for an application with a valid Logback backend:

```xml
<configuration>
    <appender name="FILE"
              class="ch.qos.logback.core.rolling.RollingFileAppender">
        <file>logs/app.log</file>
        <rollingPolicy
            class="ch.qos.logback.core.rolling.TimeBasedRollingPolicy">
            <fileNamePattern>logs/archive/app.%d{yyyy-MM-dd}.log.gz</fileNamePattern>
            <maxHistory>30</maxHistory>
            <totalSizeCap>5GB</totalSizeCap>
            <cleanHistoryOnStart>true</cleanHistoryOnStart>
        </rollingPolicy>
        <encoder>
            <pattern>%d{ISO8601} %-5level %logger - %msg%n</pattern>
        </encoder>
    </appender>
    <root level="INFO">
        <appender-ref ref="FILE"/>
    </root>
</configuration>
```

Explanation of each element:

- `<file>logs/app.log</file>` is the **active file**. It is not an expired archive selected for deletion by the archive schedule.
- `fileNamePattern` contains `%d{yyyy-MM-dd}`, meaning rollover occurs by **daily period**, and archives can be compressed thanks to the `.gz` suffix.
- `maxHistory=30` specifies keeping **30 daily archive periods**, not a measurement accurate to the millisecond.
- `totalSizeCap=5GB` is an additional total **archive** size limit; per Logback documentation, using `totalSizeCap` requires `maxHistory`. Logback applies `maxHistory` first and `totalSizeCap` afterward.
- `cleanHistoryOnStart=true` requests history cleanup when the appender starts, which is useful for short-lived jobs that rarely trigger rollover. The default is typically false.
- `<root>` references the `FILE` appender to route events to the file. If the appender is not referenced properly, logging will not work as expected.

### Important limitations

**maxHistory does not mean deletion happens exactly at midnight.** Cleanup usually runs during rollover and may be asynchronous; startup cleanup only happens when enabled. An old archive may remain on disk until the next processing cycle.

If you need to limit the size of **each individual archive file**, Logback provides `SizeAndTimeBasedRollingPolicy`, which uses both `%d` and `%i` in the filename pattern. `totalSizeCap` does not replace a per-file size limit; it only controls the **total archive size**.

**Note:** if you are required to keep logs for at least 30 days, `totalSizeCap=5GB` can delete archives younger than 30 days when total size exceeds the cap. That is a policy trade-off that must be approved, not copied from an example without calculating actual log volume.

## 7. Log4j 2: Delete action, IfFileName, and IfLastModified

Log4j 2 provides `RollingFileAppender` with rollover strategies, including a **Delete action** to remove archives after rollover cycles. To delete files by age without affecting other files, combine a **specific basePath + filename condition + age condition**.

Complete `log4j2.xml` example:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<Configuration>
    <Appenders>
        <RollingFile name="FILE"
                     fileName="logs/app.log"
                     filePattern="logs/archive/app-%d{yyyy-MM-dd}-%i.log.gz">
            <PatternLayout pattern="%d{ISO8601} %-5p %c - %m%n"/>
            <Policies>
                <TimeBasedTriggeringPolicy interval="1"
                                           modulate="true"/>
                <SizeBasedTriggeringPolicy size="10 MB"/>
            </Policies>
            <DefaultRolloverStrategy>
                <Delete basePath="logs/archive"
                        maxDepth="1"
                        testMode="true">
                    <IfFileName glob="app-*.log.gz">
                        <IfLastModified age="P30D"/>
                    </IfFileName>
                </Delete>
            </DefaultRolloverStrategy>
        </RollingFile>
    </Appenders>
    <Loggers>
        <Root level="INFO">
            <AppenderRef ref="FILE"/>
        </Root>
    </Loggers>
</Configuration>
```

**This configuration is in preview mode with `testMode="true"`, so it does not actually delete files.** According to Log4j 2, the Delete action in test mode logs messages via the Status Logger for the files that would be selected; operators must verify the output before enabling real deletion.

Reading the configuration:

1. `fileName="logs/app.log"` is the **active file** path.
2. `filePattern="logs/archive/..."` places archives in a separate directory. `%d` selects the time period, and `%i` distinguishes multiple files within the same period when the size trigger fires.
3. `TimeBasedTriggeringPolicy` and `SizeBasedTriggeringPolicy` decide when to **roll over**, not directly when to delete.
4. `DefaultRolloverStrategy` holds additional post-rollover actions.
5. `Delete basePath="logs/archive" maxDepth="1"` restricts traversal to **one level** inside the archive directory.
6. `IfFileName glob="app-*.log.gz"` allows only names belonging to the archive family, not arbitrary files.
7. `IfLastModified age="P30D"` checks the file's **last modification age**. The age condition is nested inside the filename condition, so both must match.
8. `testMode="true"` performs no deletion; only after verifying the target file set and obtaining approval should you switch to real deletion mode.

**Execution timing:** The Delete action runs during rollover. It is not a standalone nightly cron job. If the application emits no logs, an archive may already be older than the threshold and still remain on disk until the next rollover.

**Symlink safety:** per Log4j 2 documentation, `followLinks` defaults to false, reducing the risk of recursing through symbolic links outside `basePath`. Do not enable `followLinks=true` without verifying the exact ownership of all paths.

### IfLastModified differs from maxHistory

- **Log4j 2 `IfLastModified age="P30D"`:** based on mtime age when the action runs, matching files that have reached the specified age.
- **Logback `maxHistory=30`:** based on **archive periods** managed by the rolling policy.
- **Java `Instant.isBefore(cutoff)`:** strict "older than cutoff" condition; does not delete files whose timestamp equals the cutoff.

Do not assume identical **exact-boundary** behavior across these three mechanisms. If retention requires second-level precision, define the comparison operator, timestamp source, and timezone explicitly.

### When is IfAll needed?

Log4j 2 supports `IfAll` to require multiple path conditions simultaneously, in addition to nesting `IfLastModified` inside `IfFileName` as shown in the example. Complex multi-condition configurations should be tested for combination logic; do not assume all conditions are OR or AND in every XML position.

### Do not use an overly broad basePath

Unsafe example:

```xml
<!-- Do not use arbitrarily in a directory containing multiple file types. -->
<Delete basePath="logs" maxDepth="99">
    <IfLastModified age="P30D"/>
</Delete>
```

That configuration can select files that are not application archives. A better approach is a dedicated `basePath` combined with a filename allowlist + age condition, along with `testMode`/dry-run.

## 8. JUL FileHandler: count/limit, not file age

The JDK provides `java.util.logging.FileHandler` with limits on file size and generation count:

```java
// Illustrative snippet in an application that already has a logger and handles IOException.
java.util.logging.FileHandler handler =
        new java.util.logging.FileHandler(
                "logs/app-%g.log", 1_000_000, 5, true);
handler.setFormatter(new java.util.logging.SimpleFormatter());
logger.addHandler(handler);
```

Where:

- `%g` is the generation index during rotation.
- `1_000_000` is the file byte limit in the rotation mechanism.
- `5` is the number of generations, **not 5 days**.
- `true` enables append mode per the `FileHandler` API.

**JUL `FileHandler` has no direct option like `maxAge=30d`** to delete archives by age like the two mechanisms above. If you use only JUL and need time-based retention, you must choose another logging backend or design a separate cleanup job with clear boundaries that never deletes files currently held open by `FileHandler`.

Be aware of file locks and differing behavior when multiple JVMs write concurrently; do not pair `FileHandler` with a wildcard deletion schedule without evaluating generation file ownership.

## 9. When should you use a separate scheduler/job?

A separate cleanup job may make sense when:

- The service does not emit logs frequently enough for rollover-triggered cleanup to run on time.
- Archives are produced by multiple components under one unified storage policy with clear ownership.
- You need to confirm that a collector has read/uploaded an archive before deleting the local copy.
- There are legal holds, storage tiers, or custom retention rules that rolling policies do not handle.
- You are using JUL or a logger without built-in age retention.

However, a separate job also increases risk: cleanup could run mid-compression, mid-rename, mid-upload, while a writer still has the file open, or while another appender is also deleting.

A responsible job design should include:

1. **Single ownership / lock/lease:** prevent multiple instances from cleaning the same set of files.
2. **Directory isolation:** an archive directory dedicated to the service, with least-privilege permissions.
3. **Filename and file-type allowlist:** never accept names directly from user/request input.
4. **Do not follow symlinks** and do not recurse outside the approved scope.
5. **A single consistent timestamp policy**, with defined cutoff and boundary semantics.
6. **Dry-run by default** before enabling actual deletion for the first time.
7. **Archive completion condition**: compression/rename/shipping finished per contract.
8. **Per-batch limits**, byte limits, timeouts, and sensible retries.
9. **Metrics and audit**: candidates/deleted/error counts, bytes, and execution timestamps.
10. **Fail-safe recovery**: when uncertain, skip the file and raise an alert instead of deleting blindly.

**Do not enable deletion in the rolling appender and also run a cron job deleting those same files** without explicit coordination.

## 10. Standalone Java 17 example: dry-run first, then delete simulated archives

This example runs **only inside a temporary directory created by the program itself**. It requires no third-party libraries and never scans or deletes real system logs. The program creates dummy files with known mtimes, selects only archives matching `app-YYYY-MM-DD.log.gz`, and runs two passes:

- `DRY_RUN`: prints decisions without deleting.
- `APPLY`: deletes expired files inside the demo directory itself.

For reproducible results, the reference time is fixed at `2026-11-09T00:00:00Z`; the cutoff is 30 days earlier. Files with the `.gz` extension contain only sample text, **not real GZIP data**: the exercise tests *file selection decisions*, not appender compression.

### File RetentionCleanupDemo.java

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.attribute.FileTime;
import java.time.Duration;
import java.time.Instant;
import java.util.Comparator;
import java.util.List;
import java.util.regex.Pattern;
import java.util.stream.Stream;

public final class RetentionCleanupDemo {

    private static final Pattern ARCHIVE =
            Pattern.compile("app-\\d{4}-\\d{2}-\\d{2}\\.log\\.gz");

    private static final List<String> DEMO_NAMES = List.of(
            "app-2026-10-01.log.gz",
            "app-2026-10-10.log.gz",
            "app-2026-10-25.log.gz",
            "current.log",
            "notes.txt");

    private RetentionCleanupDemo() {
    }

    public static void main(String[] args) throws IOException {
        Path directory = Files.createTempDirectory("retention-demo-");

        try {
            create(directory, DEMO_NAMES.get(0),
                    "2026-10-01T00:00:00Z");
            create(directory, DEMO_NAMES.get(1),
                    "2026-10-10T00:00:00Z");
            create(directory, DEMO_NAMES.get(2),
                    "2026-10-25T00:00:00Z");
            create(directory, DEMO_NAMES.get(3),
                    "2026-09-01T00:00:00Z");
            create(directory, DEMO_NAMES.get(4),
                    "2026-09-01T00:00:00Z");

            Instant now = Instant.parse("2026-11-09T00:00:00Z");
            Instant cutoff = now.minus(Duration.ofDays(30));

            review(directory, cutoff, false);
            review(directory, cutoff, true);

            System.out.println("OLD_EXISTS="
                    + Files.exists(directory.resolve(DEMO_NAMES.get(0))));
            System.out.println("RECENT_EXISTS="
                    + Files.exists(directory.resolve(DEMO_NAMES.get(2))));
            System.out.println("ACTIVE_EXISTS="
                    + Files.exists(directory.resolve(DEMO_NAMES.get(3))));
        } finally {
            for (String name : DEMO_NAMES) {
                Files.deleteIfExists(directory.resolve(name));
            }
            Files.deleteIfExists(directory);
        }
    }

    private static void create(Path directory, String name,
                               String isoTime) throws IOException {
        Path path = directory.resolve(name);
        Files.writeString(path, "sample", StandardCharsets.UTF_8);
        Files.setLastModifiedTime(path,
                FileTime.from(Instant.parse(isoTime)));
    }

    private static void review(Path directory, Instant cutoff,
                               boolean apply) throws IOException {
        String phase = apply ? "APPLY" : "DRY_RUN";

        try (Stream<Path> stream = Files.list(directory)) {
            for (Path file : stream.sorted(
                    Comparator.comparing(
                            p -> p.getFileName().toString())).toList()) {

                String name = file.getFileName().toString();

                if (!Files.isRegularFile(file, LinkOption.NOFOLLOW_LINKS)
                        || !ARCHIVE.matcher(name).matches()) {
                    System.out.println(phase + " SKIP " + name);
                    continue;
                }

                Instant modified = Files.getLastModifiedTime(
                        file, LinkOption.NOFOLLOW_LINKS).toInstant();

                if (modified.isBefore(cutoff)) {
                    System.out.println(phase + " DELETE " + name);
                    if (apply) {
                        Files.delete(file);
                    }
                } else {
                    System.out.println(phase + " KEEP " + name);
                }
            }
        }
    }
}
```

### Compile and run

Save with the exact name `RetentionCleanupDemo.java`. In the directory containing the file, with JDK 17 or later:

```bash
javac -encoding UTF-8 RetentionCleanupDemo.java
java RetentionCleanupDemo
```

**Exact stdout from the code above:**

```text
DRY_RUN DELETE app-2026-10-01.log.gz
DRY_RUN KEEP app-2026-10-10.log.gz
DRY_RUN KEEP app-2026-10-25.log.gz
DRY_RUN SKIP current.log
DRY_RUN SKIP notes.txt
APPLY DELETE app-2026-10-01.log.gz
APPLY KEEP app-2026-10-10.log.gz
APPLY KEEP app-2026-10-25.log.gz
APPLY SKIP current.log
APPLY SKIP notes.txt
OLD_EXISTS=false
RECENT_EXISTS=true
ACTIVE_EXISTS=true
```

### Explanation of each result

1. The cutoff is `2026-10-10T00:00:00Z` because `Duration.ofDays(30)` computes 30 × 24 hours.
2. The Oct 01 archive has an `mtime` older than the cutoff, so the dry-run pass only prints `DELETE`; the apply pass actually calls `Files.delete(file)`.
3. The Oct 10 archive has an `mtime` **equal to** the cutoff. `Instant.isBefore()` returns false, so it is kept.
4. The Oct 25 archive is newer than the cutoff, so it is also kept.
5. `current.log` has a very old mtime but **does not match the archive pattern**. It is kept.
6. `notes.txt` also does not match the pattern, so it is not deleted.
7. `Files.list(directory)` lists only direct children; `Files.isRegularFile(..., NOFOLLOW_LINKS)` helps exclude symbolic links.
8. `stream.sorted(...)` ensures deterministic output order, independent of how the filesystem enumerates entries.
9. `finally` cleans up only the created demo filenames and the self-managed temporary directory; it never touches production paths.

**Safety limitation:** this is a learning exercise, not a production deletion tool. Checking `isRegularFile` and then calling `delete` still has a *time-of-check to time-of-use race* if another process is permitted to swap the file/symlink during cleanup. It lacks legal holds, collector confirmation, locks/leases, permissions, and deletion auditing. Do not change `directory` to a real system path and run it directly.

## 11. Why should you not delete an open file?

An active log may be held open by an appender via a file descriptor/handle. Deleting it has OS-dependent consequences:

- On POSIX systems, unlinking the filename may succeed, while the process continues writing through the old descriptor; disk space may not be reclaimed until the descriptor is closed.
- On Windows, the delete operation may fail because the file is open/locked depending on sharing mode.
- A collector tailing the file may lose track if the file is renamed/deleted unexpectedly.

Therefore, do not delete the active `app.log` just because its `mtime` looks old. The current file should be managed by the rolling appender and confirmed as a completed archive before retention is applied.

Likewise, files currently being compressed or uploaded should not be selected simply because their name resembles an archive. You need temporary file conventions and an "archive completed" criterion.

## 12. logrotate, cron, and container runtimes

On Linux, `logrotate` is an external tool outside Java that supports scheduled rotation/cleanup. In some container systems, stdout/stderr are rotated by the runtime or log driver, while the application does not own the underlying physical files of that stream.

If using external tools:

- Pick **one clear owner**: the rolling framework, `logrotate`, or a storage lifecycle policy.
- Do not let `logrotate` and Logback/Log4j 2 rotate the same file independently.
- `logrotate` concepts such as `daily`, `rotate N`, `maxage N`, and `compress` do not have the exact same semantics as `maxHistory` in every framework.
- `copytruncate` can lose a small window of log lines if the writer continues writing between the copy and truncate steps; evaluate that risk.
- For inode/offset-based collectors or file shippers, verify that they understand the rename/rotation policy and do not miss archives.
- For container logs, prefer handling retention via the platform or central log store rather than deleting files the JVM does not own.

Do not suggest wildcard deletion commands without an allowlist or direct deletion commands in `/var/log` without knowing the exact paths and owners.

## 13. If disk is still full after deletion

A job may report deleting many files while volume usage does not drop as expected. Causes:

1. Files were unlinked, but a process still holds open descriptors.
2. New logs are being produced faster than cleanup runs.
3. The largest files sit outside the archive directory and do not match the rule.
4. Filesystem snapshots, backups, or overlay layers still hold the data.
5. Deletions failed due to permissions, and errors were not monitored.
6. The Delete action has not run because no rollover occurred, or Logback startup cleanup is disabled.
7. Archive mtimes were updated during compression/copying, so they have not passed the threshold.
8. The collector has not caught up, causing the job to skip files as designed by the safety policy.

Measure separately: candidate files, successfully deleted files, deleted bytes, actual disk usage, open file descriptors, and ingestion lag. Never treat "delete was scheduled" as proof that disk space was freed.

## 14. Security, privacy, and compliance

Logs can contain security events, operational details, or personal data. Deletion policies must align with:

- Minimum and maximum retention periods required by the organization or applicable regulations.
- Legal holds or evidence-preservation orders during investigations.
- Privacy: do not retain sensitive data longer than legally necessary.
- Backups, remote collectors, object storage, and other replicas.
- Read/delete permissions and auditing of the user or process performing cleanup.

**Never log passwords, OTPs, access tokens, refresh tokens, session cookies, or private keys regardless of retention.** Deleting logs after a month does not keep that data safe during the month it exists.

The cleanup job should log necessary operational metadata: policy version, deleted file set, byte count, timestamp, and errors; **do not copy the full contents of deleted files** into the cleanup log. Under strict audit requirements, cleanup logs should also be written to a secure destination so the job does not delete its own audit trail.

## 15. Testing an expired-file deletion strategy

| Test case | What to verify |
| --- | --- |
| Expired archive matching allowlist | Selected according to policy. |
| File right at cutoff | Behavior matches the implementation's comparison operator. |
| Recent archive | Not deleted. |
| Active file even if very old | Not deleted while still owned by the writer. |
| File in same directory with different name | Not deleted. |
| Symlink pointing outside archive | Not followed / target not deleted. |
| File being compressed or read by shipper | Excluded until complete. |
| File with old date in name but new mtime | Outcome matches the chosen time source. |
| Multiple files per day | Period-based `maxHistory` vs. file-count limits are distinguished. |
| Service silent for many days | Verify whether cleanup needs a startup or scheduler trigger. |
| Disk full or permission denied | Errors are measured; no false completion reported. |
| Multi-instance concurrent cleanup | Single owner/lock/lease prevents races. |
| Legal hold active | File is retained even if expired. |
| File deleted before collector ACK | Detected and prevented to avoid losing critical events. |
| Job crashes mid-run | Next run handles remaining work safely/idempotently. |
| Volume does not shrink after unlink | Check open descriptors, snapshots, or other sources. |

Useful metrics:

- `log_archive_files_total`: current number of archives.
- `log_archive_bytes_total`: total archive size in bytes.
- `log_cleanup_candidates_total`: files eligible under the policy.
- `log_cleanup_deleted_total`: files successfully deleted.
- `log_cleanup_deleted_bytes_total`: total bytes of successfully deleted files.
- `log_cleanup_errors_total`: delete/permission/path errors.
- `log_archive_oldest_age_seconds`: age of the oldest archive.
- `log_collector_lag_seconds`: lag of the collection pipeline.

These are **illustrative suggested metric names**, not metrics emitted by default by Java/Logback/Log4j 2. When exposing metrics, avoid using full file paths or unique event IDs as high-cardinality metric labels.

## 16. Auditable retention rollout process

1. **Survey data:** identify where logs are produced, the authoritative store, local archives, and replicas.
2. **Define approved policy:** retention age/period, total size cap, exceptions, and legal holds.
3. **Choose an owner:** rolling appender, cron/job, or storage lifecycle, avoiding overlapping decisions.
4. **Separate directories:** isolate active files from archives, use a filename allowlist, and apply least-privilege permissions.
5. **Choose the mechanism:** Logback `maxHistory/totalSizeCap`, Log4j 2 `Delete` and `PathConditions`, or a dedicated job when required.
6. **Define when cleanup runs:** rollover, startup, or scheduler; check idle/long-sleeping service cases.
7. **Run dry-run/testMode:** record candidate list, count, and bytes; have an authorized reviewer verify.
8. **Test in an isolated environment:** boundaries, symlinks, permissions, active files, collector lag, crashes, and restarts.
9. **Enable real deletion:** only after the file list matches scope and violates no retention requirements.
10. **Observe:** measure actual deleted files/bytes, errors, archive age, and remaining disk space.
11. **Practice recovery:** for logs requiring backup, verify that secondary copies remain usable.
12. **Review periodically:** policies, patterns, framework versions, log volume, and legal requirements can change.

**Do not simply "set maxHistory and forget it."** A retention policy is complete only when there is evidence that cleanup runs properly, does not delete the wrong files, and preserves required data.

## 17. Common mistakes

1. **Assuming rotation automatically cleans up archives by age** without configuring retention.
2. **Thinking `maxHistory=30` means 30 files** even when the pattern is daily.
3. **Thinking keeping 10 files means keeping 10 days** even when a single day produces hundreds of files.
4. **Assuming mtime equals the date in the filename** after copying, compressing, or restoring.
5. **Using `FileHandler` count=5 as 5-day age retention.**
6. **Believing cleanup runs at midnight** when it is actually tied to rollover.
7. **Deleting all `*.log` files in `logs/`** without ownership or an allowlist.
8. **Deleting the active file** still held open by an appender.
9. **Enabling `followLinks` and deep scanning**, potentially escaping the archive scope.
10. **Skipping `testMode`/dry-run** before enabling real deletion.
11. **Deleting before the collector ingests**, losing the last copy.
12. **Running two cleanup owners simultaneously** without coordination.
13. **Seeing disk usage stay high and deleting even more files** while descriptors remain open.
14. **Setting a total size cap lower than the minimum required retention** without resolving the requirement conflict.
15. **Relying on `isRegularFile` followed by `delete` as absolute race protection.**
16. **Treating retention as a secret-hiding mechanism** instead of redacting at the source.

## 18. Pre-production checklist

- [ ] Approved policy exists, defining age/period and deletion boundaries.
- [ ] Cleanup owner is known for the exact archive directory.
- [ ] Active file is protected; archives live in a separate directory.
- [ ] Allowed filenames and timestamp source are precisely specified.
- [ ] Logback/Log4j 2/JUL configuration matches the chosen framework and version.
- [ ] `maxHistory`, `count`/`maxFiles`, and `totalSizeCap` are clearly distinguished.
- [ ] Cleanup trigger (rollover, startup, or schedule) is known.
- [ ] Dry-run/`testMode` has been executed and the candidate file list verified.
- [ ] Symlinks are not followed outward; in-progress files are not deleted.
- [ ] Legal holds and collector/backup status have been checked.
- [ ] Error metrics/logs, deletion auditing, and post-cleanup disk checks are in place.
- [ ] Tested for write permissions, disk full, restarts, races, open files, and multi-instance runs.
- [ ] Recovery plan exists for mandatory data.
- [ ] No unnecessary tokens/passwords/PII are written to logs.
- [ ] Tested on dummy archives and verified in a realistic environment before enabling delete.

## Official references

- [Apache Log4j 2 — Rolling File Appenders and Delete Action](https://logging.apache.org/log4j/2.x/manual/appenders/rolling-file.html)
- [Logback — RollingFileAppender, maxHistory, totalSizeCap](https://logback.qos.ch/manual/appenders-rolling.html)
- [Java 17 — Files, mtime, and NOFOLLOW_LINKS](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html)
- [Java 17 — Instant](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Instant.html)
- [Java 17 — FileHandler](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/FileHandler.html)

**Key takeaway:** Deleting expired log files is a **retention policy bounded by age, filename, path, and permissions**. Use your logging backend's built-in tools when possible, delete only completed archives, never touch the active file, run a dry-run first, and measure actual outcomes; local deletion does not mean every copy has been handled.