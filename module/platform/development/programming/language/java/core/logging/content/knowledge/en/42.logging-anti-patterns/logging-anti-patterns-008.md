# Unbounded Log Files — An Anti-Pattern in Java Logging

## 1. What is this anti-pattern?

**Unbounded log files** is a design/operational flaw where an application continuously writes to a single file, or creates new archive files without a policy limiting total storage size and data age. In production, the file can grow until it fills the filesystem, container quota, or node disk. The initial issue may just be running out of space, but eventually it can break **logging, performance, business data persistence, and incident investigation**.

An example that easily creates this problem:

```java
// UNSAFE illustration when used unbounded in production.
// JUL FileHandler(pattern, append) sets no rotation limit or count.
java.util.logging.FileHandler handler =
        new java.util.logging.FileHandler("logs/application.log", true);
```

Or with Logback, configuring only a plain `FileAppender`:

```xml
<!-- Anti-pattern: file without a rolling/retention policy -->
<appender name="FILE" class="ch.qos.logback.core.FileAppender">
    <file>logs/application.log</file>
    <append>true</append>
    <encoder>
        <pattern>%d{ISO8601} %-5level %logger - %msg%n</pattern>
    </encoder>
</appender>
```

These snippets may be syntactically valid, but they **do not bound file size or lifecycle**. If the service logs heavily and runs for a long time, the file keeps growing. Exiting the JVM does not guarantee the file is automatically deleted; the next startup with `append=true` can keep appending to the old file.

**Note:** a file appender is not automatically an anti-pattern if the system already has an **external rotation and retention mechanism** that is controlled, tested, and monitored. The issue is **having no effective bounding policy on the actual data write path**.

## 2. When does the flaw become an incident?

For example, a system writes 250 log events/second, each event around 700 bytes after encoding:

```text
bytes_per_second = 250 × 700 = 175,000 B/s
bytes_per_day    = 175,000 × 86,400 = 15,120,000,000 B/day
                 ≈ 15.12 GB/day (decimal GB)
```

If the filesystem only has about 10 GiB (~10.74 billion bytes) free, then at the **assumed steady rate**, that space could be exhausted in roughly **17 hours**. This is an illustrative calculation, not a substitute for real measurement: log rate varies with traffic, JSON size, stack traces, compression, replicas, other data on disk, and disk cleanup policies.

When write volume spikes due to repeated errors, brute-force logins, retry storms, or accidentally enabling DEBUG, the remaining time can be much shorter.

### Typical chain of consequences

```text
No effective rotation / retention
               │
               ▼
        File or archive grows
               │
               ▼
     High disk usage / inode usage
               │
       ┌───────┴────────┐
       ▼                ▼
Appender write      Filesystem full
error / lost logs       │
       │                ▼
       │          Database/cache/tmp
       │          may also be affected
       ▼                │
Blind observability ◄───┘
       │
       ▼
Incident hard to investigate and may persist
```

**It is not just "large files slow down search."** Oversized files also make copying, compressing, transferring, tailing, backing up, or recovering difficult; disk-full conditions can impact other components sharing the filesystem. A synchronous appender can increase request latency if file writes become slow or fail repeatedly. The exact behavior on I/O errors **depends on the backend and configuration**—do not assume every logger throws an exception that breaks the request.

## 3. Why limiting by a single parameter is not enough

At least four layers of limits need to be distinguished:

| Layer | Example | What does it limit? | What does it not solve? |
| --- | --- | --- | --- |
| **Per-event size** | Message/stack trace truncation | Prevents a single event from taking MBs | Does not stop millions of small events |
| **Log emission rate** | Level/rate limit/selective sampling | Reduces bytes/second | Does not guarantee mandatory logs are kept |
| **Active file size** | Rollover at 50 MB | Prevents the active file from growing forever | Archives can still grow unbounded |
| **Archive count/age/total size** | 7 days, 1 GB archive | Conditionally cleans up old files | Not a hard filesystem quota |
| **Infrastructure capacity limits** | Volume quota, container node limit, alerts | Protects shared resources | Does not automatically preserve audits when full |
| **Backend retention** | Index/object lifecycle | Bounds centralized copies | Does not handle local files/collector spool |

For example, having `maxFileSize=50MB` without **archive cleanup** can still create thousands of compressed files. Having `maxHistory=7` without size-based rollover means the active file can grow larger than expected on an unusual day. Even with `maxFileSize`, `maxHistory`, and `totalSizeCap`, if the app uses a directory without a disk quota and multiple other services also write there, infrastructure can still run out of space.

**Rule of thumb:** control **per-event size + data emission + rotation + retention + filesystem/backend capacity**. Every layer must have an owner and monitoring.

## 4. Identifying causes in practice

Common symptoms:

- `df -h` reports the log filesystem is nearly full, while the application is still writing a lot of INFO/DEBUG.
- `du` shows a single `application.log` file growing continuously, or the archive has a huge number of `application.2026-...log.gz` files.
- Monitoring reports rapidly dropping free disk space, `ENOSPC` / "No space left on device".
- The backend stops receiving complete logs because the appender or node collector cannot read/write.
- High CPU/I/O during rotation/compression, or the collector falls behind because files are too large.
- After a deploy/restart, files are not cleaned up because the policy failed to initialize or only runs cleanup on rollover.
- One app's log rotates, while access logs from Tomcat, a gateway, or another application server keep growing.
- A pod's stdout is rotated by kubelet, yet the application writes auxiliary files to a volume not managed by kubelet.

### Do not conclude from a single symptom

| Symptom | Possible causes | What to check |
| --- | --- | --- |
| Disk full | Log files, DB, cache, image layers, inode exhaustion | Actual filesystem and top consumers |
| Active file too large | No rollover or policy startup failure | Effective appender config and status logs |
| Too many archives | No retention or glob mismatch | Cleanup timing, policy, and permissions |
| File deleted but free disk does not increase | Process still holds an unlinked file descriptor | Process handles/file descriptors |
| Files inside container are small but node is full | Node stdout files, image layers, or other log services | Node log directory and kubelet configuration |
| Search backend is empty | Broken collector or wrong parser/query/permissions | Source → collector → index → dashboard |
| Logs still filling after reducing INFO | ERROR storm or other files/collector spool | Event rate, size, sink ownership |

Keep in mind that **source files, archives, collector buffers, indexes, and backups** are separate copies; cleaning up one layer does not mean all of them are cleaned up.

## 5. Incorrect Logback configuration and fixing it with a rolling policy

### Wrong approach: FileAppender only

```xml
<appender name="APP" class="ch.qos.logback.core.FileAppender">
    <file>logs/app.log</file>
    <append>true</append>
    <encoder>
        <pattern>%d %-5level %logger - %msg%n</pattern>
    </encoder>
</appender>
```

This configuration has no triggering/rolling policy: **the active log has no lifecycle bound in Logback**.

### Better approach: SizeAndTimeBasedRollingPolicy

Example `logback.xml` using Logback-classic (requires the dependency matching the application's version):

```xml
<configuration>
    <appender name="APP"
              class="ch.qos.logback.core.rolling.RollingFileAppender">
        <file>logs/app.log</file>

        <rollingPolicy
                class="ch.qos.logback.core.rolling.SizeAndTimeBasedRollingPolicy">
            <fileNamePattern>logs/archive/app.%d{yyyy-MM-dd}.%i.log.gz</fileNamePattern>
            <maxFileSize>50MB</maxFileSize>
            <maxHistory>7</maxHistory>
            <totalSizeCap>1GB</totalSizeCap>
            <cleanHistoryOnStart>true</cleanHistoryOnStart>
        </rollingPolicy>

        <encoder>
            <pattern>%d{ISO8601} %-5level [%thread] %logger - %msg%n</pattern>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="APP"/>
    </root>
</configuration>
```

**Exact explanation of each parameter:**

- `RollingFileAppender` writes to the active file `logs/app.log` and moves old files to the archive when rollover conditions are met.
- In `SizeAndTimeBasedRollingPolicy`, the pattern requires **both `%d` and `%i`** to distinguish the date and the file index.
- `maxFileSize=50MB` is the size-based rollover threshold for the **active file**; it is not a hard total filesystem limit and can be exceeded due to timing or event size.
- `maxHistory=7` with a daily pattern means **7 archive day-periods**, **not 7 files**. If a single day produces 40 files due to high traffic, the total archive count can exceed 7 files.
- `totalSizeCap=1GB` limits the **total size of archives** managed by cleanup after history constraints are applied; it does not cover all files on disk, may not include the active file, and cleanup can run asynchronously.
- `cleanHistoryOnStart=true` allows archive cleanup at appender startup. Cleanup is also typically tied to rollover, so expired files are not guaranteed to be deleted to the exact millisecond.
- The `.gz` suffix enables archive compression; compression consumes CPU and can fail. Monitor compression/rename errors and temporary disk usage.
- `root level=INFO` only decides which log levels are permitted to emit; it does **not** guarantee the appender will never log secrets or that an ERROR storm will not exceed quota.

**Important limitation:** `maxHistory`/`totalSizeCap` do not replace **filesystem quotas, disk alerts, backend retention, or audit governance**. For production, values like `50MB`, `7`, and `1GB` are **examples**—calculate them from actual log rate, size, and retention requirements.

### When only total archive bounds are needed, size+time is not always necessary

Logback also provides `TimeBasedRollingPolicy`:

```xml
<rollingPolicy class="ch.qos.logback.core.rolling.TimeBasedRollingPolicy">
    <fileNamePattern>logs/archive/app.%d{yyyy-MM-dd}.log.gz</fileNamePattern>
    <maxHistory>7</maxHistory>
    <totalSizeCap>1GB</totalSizeCap>
    <cleanHistoryOnStart>true</cleanHistoryOnStart>
</rollingPolicy>
```

This snippet **replaces the rollingPolicy section** inside a `RollingFileAppender`; it is not a complete appender on its own. It bounds time and total archive size, **without setting a per-active-file size threshold**. Per Logback documentation, only use `SizeAndTimeBasedRollingPolicy` when file-size rollover is genuinely needed, as it involves additional renaming work and edge cases to monitor.

### Daily rollover does not necessarily happen at 00:00

In Logback, rollover is driven by **incoming log events**. If no events arrive after midnight, rollover can wait until the next event. Therefore, do not use a Logback rolling policy as a second-accurate scheduler to enforce strict data-deletion deadlines.

## 6. Log4j2 RollingFile: separate triggers, separate retention

Log4j2 Core provides `RollingFileAppender` with **triggering policies** and a **rollover strategy**. An example configuration with both time-based and size-based rollover:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<Configuration status="WARN">
    <Appenders>
        <RollingFile name="APP"
                     fileName="logs/app.log"
                     filePattern="logs/archive/app-%d{yyyy-MM-dd}-%i.log.gz">
            <PatternLayout pattern="%d{ISO8601} %-5p %c - %m%n"/>
            <Policies>
                <TimeBasedTriggeringPolicy interval="1"/>
                <SizeBasedTriggeringPolicy size="50MB"/>
            </Policies>
            <DefaultRolloverStrategy max="20">
                <Delete basePath="logs/archive" maxDepth="1" testMode="true">
                    <IfFileName glob="app-*.log.gz"/>
                    <IfLastModified age="P7D"/>
                </Delete>
            </DefaultRolloverStrategy>
        </RollingFile>
    </Appenders>
    <Loggers>
        <Root level="info">
            <AppenderRef ref="APP"/>
        </Root>
    </Loggers>
</Configuration>
```

**The configuration above intentionally sets `testMode="true"`: it does not delete files, it only dry-runs the candidate list** via the Status Logger mechanism. It is a starting point to observe behavior; to enable actual retention, you must verify the glob, filenames, paths, permissions, retention period, and legal requirements, then **explicitly enable deletion through an approved change** (e.g., adjusting `testMode` per the documentation for your deployed version). Do not copy this and assume archives are expiring while still in test mode.

Common pitfalls:

- `SizeBasedTriggeringPolicy` decides **when to roll over**; `TimeBasedTriggeringPolicy` triggers rollover based on the time period in the pattern.
- Combining time and size requires **`%d` and `%i`** in `filePattern`; with only a date, multiple rollovers on the same day can collide on filename.
- `DefaultRolloverStrategy max="20"` limits the **archive counter index per strategy**, which is not equivalent to a hard quota of "at most 20 files across all days" or 20-day retention.
- `Delete` uses a base path and `PathCondition`s to identify eligible archive files; in the example, it also requires the name to match and `lastModified >= 7 days`.
- `IfLastModified` measures **file modification time**, not necessarily the timestamp of individual events inside the file.
- The Delete action executes via the **rollover mechanism**, not as an independent millisecond-accurate cron job.
- When using namespaces, multi-tenancy, or multiple services in the same directory, an overly broad glob can delete unrelated files by mistake.

**Do not treat `testMode="false"` as a generic directive applicable everywhere.** It is a specific property of Log4j2's Delete action; before enabling real deletion, check the documentation and test with the **exact deployed application version**.

## 7. JUL: `FileHandler` with `limit` and `count`

Not every Java application uses Logback or Log4j2. The JDK's `java.util.logging.FileHandler` (JUL) supports rotating a bounded set of files by size.

Example:

```java
// Snippet for use in an application with an existing logger + managed lifecycle.
java.util.logging.FileHandler bounded =
        new java.util.logging.FileHandler(
                "logs/app-%g.log", 10_000_000, 5, true);
bounded.setLevel(java.util.logging.Level.ALL);
bounded.setFormatter(new java.util.logging.SimpleFormatter());

logger.addHandler(bounded);
// On shutdown, detach and close the handler at the appropriate time.
```

Explanation:

- `limit=10_000_000` is an **approximate byte limit per file**, not an exact 10 MiB.
- `count=5` is the number of files in the rotation; older files are overwritten as writing continues.
- `%g` is the generation index; the pattern can also include `%u` to avoid filename collisions between `FileHandler` instances where appropriate.
- `append=true` controls how an existing file is handled; it does not replace bounding the generation count.
- JUL `FileHandler` does not natively provide daily archive policies or compliance retention: if long-term storage is needed, design a separate pipeline.

**Common anti-pattern in JUL:** the constructor `new FileHandler("logs/app.log", true)` creates a file with **limit=0 (unlimited) and count=1** per the JDK specification. Successfully constructing a handler does not mean storage protection is in place.

Another example in `logging.properties`:

```properties
handlers=java.util.logging.FileHandler
.level=INFO

java.util.logging.FileHandler.pattern=logs/app-%g.log
java.util.logging.FileHandler.limit=10000000
java.util.logging.FileHandler.count=5
java.util.logging.FileHandler.append=true
java.util.logging.FileHandler.level=INFO
java.util.logging.FileHandler.formatter=java.util.logging.SimpleFormatter
```

Verify that the config file is actually loaded by the JVM's `LogManager` and that the handler is attached to the right logger/hierarchy. Setting properties when the application uses a Logback backend (without bridging JUL appropriately) may not produce the intended result.

## 8. Runnable Java 17: verifying file rotation with JUL

The example below uses **plain JDK 17**, with no external libraries. It:

1. Creates an **isolated temporary directory** using `Files.createTempDirectory`.
2. Attaches a `FileHandler` with a **1,024-byte/file** limit and **3 generations**.
3. Emits 150 short records to actually trigger rollovers.
4. Closes the handler, counts `event-*.log` files, and verifies only 3 non-empty files exist.
5. Deletes **only the files in the temporary directory created by the demo** and prints a deterministic output.

This demo only proves that the **rotated file set is bounded in count**; it does not prove a hard disk quota, audit safety, or time-based retention. Older data **is overwritten** as files rotate: this is expected for bounded rotation, but you must evaluate event preservation requirements for real systems.

Create **`BoundedJulLogDemo.java`**:

```java
import java.nio.file.DirectoryStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Locale;
import java.util.logging.FileHandler;
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class BoundedJulLogDemo {
    private static int exercise(Path directory) throws Exception {
        Logger logger = Logger.getLogger("demo.bounded.rotation");
        logger.setUseParentHandlers(false);
        logger.setLevel(Level.INFO);

        Path pattern = directory.resolve("event-%g.log");
        FileHandler handler =
                new FileHandler(pattern.toString(), 1024, 3, false);
        handler.setLevel(Level.ALL);
        handler.setFormatter(new Formatter() {
            @Override
            public String format(LogRecord record) {
                return record.getLevel().getName() + " "
                        + record.getMessage() + "\n";
            }
        });

        logger.addHandler(handler);
        try {
            for (int i = 0; i < 150; i++) {
                String id = String.format(Locale.ROOT, "%03d", i);
                logger.info("event=processed request_id=req_" + id);
            }
            handler.flush();
        } finally {
            logger.removeHandler(handler);
            handler.close();
        }

        int files = 0;
        try (DirectoryStream<Path> stream =
                     Files.newDirectoryStream(directory, "event-*.log")) {
            for (Path path : stream) {
                files++;
                if (Files.size(path) <= 0L) {
                    throw new AssertionError("Empty log generation");
                }
            }
        }
        if (files != 3) {
            throw new AssertionError("Expected three log generations");
        }
        return files;
    }

    public static void main(String[] args) throws Exception {
        Path directory =
                Files.createTempDirectory("jul-rotation-demo-");
        int files;
        try {
            files = exercise(directory);
        } finally {
            // Delete only the dedicated temporary directory just created by the program.
            try (DirectoryStream<Path> stream =
                         Files.newDirectoryStream(directory)) {
                for (Path path : stream) {
                    Files.deleteIfExists(path);
                }
            }
            Files.deleteIfExists(directory);
        }

        System.out.println("records_emitted=150");
        System.out.println("configured_limit_bytes=1024");
        System.out.println("configured_generations=3");
        System.out.println("rotated_files=" + files);
        System.out.println("verification=PASS");
    }
}
```

Compile/run:

```bash
javac --release 17 BoundedJulLogDemo.java
java BoundedJulLogDemo
```

**Stdout on a successful run:**

```text
records_emitted=150
configured_limit_bytes=1024
configured_generations=3
rotated_files=3
verification=PASS
```

**What to understand about this test:**

- `logger.setUseParentHandlers(false)` prevents duplicating logs to the console via the parent handler.
- The handler writes each line as two parts, `INFO` and the message, independent of `SimpleFormatter`'s locale/timestamp format.
- With 150 records of known size, the program generates enough data to cross the threshold multiple times and cycle through all three generations.
- `FileHandler` may write slightly past `limit` because it checks per record/rollover point; the test does **not** assert an exact 1,024-byte hard cap.
- `FileHandler` overwrites older logs once the generation count is reached, so having a bounded file count does **not** mean every event is preserved.
- The temporary directory is cleaned up after the handler is closed. Run in an environment with permission to create/delete temp files; do not run as administrator/root unnecessarily.
- Never replace `directory` with a production directory or add code that deletes real log files just to experiment with rotation.

## 9. Bounding local files does not cover every log copy

A service may write:

```text
Application logger
      │
      ├── local rolling file  ──────────────► filesystem quota
      │           │
      │           └── file tailer/collector ─► central backend/index
      │                                         │
      │                                         └── archive / backup / export
      └── stdout/stderr ────────────────────► container/node log
                                                │
                                                └── collector
```

**A single event can have multiple copies.** The local file may be capped at 1 GB, while the backend retains 90 days and has separate backups; total storage still grows under separate policies. Or the application logs to both stdout and a file, and the collector scrapes both, causing duplicates and doubling ingest volume.

Retention should explicitly state:

- **Local active + archives:** who handles rotation and cleanup?
- **Node/container runtime:** how many stdout/stderr files are kept?
- **Collector buffer/spool:** when the backend is unreachable, where are logs buffered and for how long?
- **Search index/data stream:** is the index lifecycle based on index age/rollover or event timestamp?
- **Object archive:** expiration, versioning, legal hold, snapshots, restore policy?
- **Exports:** do CSVs, notebooks, ticket attachments, and backups have separate retention limits?

**Do not confuse "deleted the file at the source" with "removed sensitive data from the entire system."** If a token is accidentally logged, handle the leak/rotate the credential and locate all copies rather than merely lowering `maxHistory`.

## 10. Kubernetes and containers: stdout does not mean infinite

In Kubernetes, the common pattern is for applications to write to `stdout/stderr`, the container runtime writes those to log files on the node, and **kubelet manages rotation**. The node configuration parameters are:

```yaml
# Illustrative kubelet configuration parameters snippet;
# not a Pod manifest or Java config.
containerLogMaxSize: 10Mi
containerLogMaxFiles: 5
```

Kubernetes documentation describes typical defaults as **10Mi** and **5 files**, though actual cluster configuration may differ. This is a **node-local log rotation** policy, not the search backend's retention period.

Operational points:

1. `kubectl logs` may only read the current/most recent log file; do not rely on it as a long-term historical source.
2. Pod deletion/eviction or node loss can wipe local logs; if long-term retention is required, use a collector and centralized backend.
3. Custom logs written by the application to a volume are not automatically rotated by kubelet just because stdout is rotated.
4. Log emission rate can outpace kubelet/collector processing, leading to node disk pressure or loss of uningested logs.
5. Using a sidecar that "tails a file and prints to stdout" can create **two copies** on the node. Define a clear policy.
6. Do not alter node-wide quotas to band-aid an application spamming ERRORs without investigating the root cause.

**Kubernetes rotation and Java rolling files operate in two different places.** In particular, if the application configures its own `RollingFileAppender` writing to `/app/logs` on a persistent volume, kubelet's container log policy does not manage that volume.

## 11. External logrotate: avoid conflicting with the appender

On Linux VMs, the OS sometimes runs `logrotate`. If Java already uses its own `RollingFileAppender`, **do not let two rotation systems compete over the same file** unless explicitly designed and tested.

Two common mechanisms:

- **rename + reopen:** the external tool renames the file and signals the process to reopen a new file. Java loggers do not automatically handle signals like every Linux daemon; without reopening, the process can keep writing to the old file descriptor.
- **copytruncate:** the external tool copies the file and truncates the original so the process keeps writing. Between copy and truncate there is a race window that can **drop log events**. Do not use it for audit channels requiring preservation without evaluating the risk.

If using `logrotate` for Java, verify that the backend supports that rotation style, that the log shipper detects inode/file changes, post-rotation permissions, and potential loss/duplication. **Prefer a single rotation owner per source file.**

Do not run `rm` or `truncate` on an active file as a "quick fix" when disk space runs low: besides losing evidence, an unlinked file can continue consuming disk space until the process closes its file descriptor.

## 12. File growth, inodes, and disk quotas

A full disk is not only caused by byte volume:

- **Large files:** a single `app.log` taking many GBs.
- **Excessive file count:** creating hundreds of thousands of small files per day can exhaust inodes.
- **Shared filesystem:** application logs, databases, temp files, heap dumps, and crash files competing for space.
- **Hidden copies:** container layers, snapshots, collector spools, and unlinked files still held open by a process.
- **Compression:** requires CPU/I/O and sometimes temporary space; it may not free disk immediately.
- **Replicas:** a central backend may multiply index size; local quotas do not affect replicas.

**Safe read-only observation commands** (Linux/VM; adjust paths for your environment, requires appropriate permissions):

```bash
df -h
df -i
du -sh /var/log/myapp
find /var/log/myapp -maxdepth 1 -type f -printf '%s %p\n'
# If descriptor diagnostics are permitted on Linux:
lsof +L1
```

The commands above are **diagnostic suggestions**, not complete proof when filesystem mounts/overlays differ or containers are isolated. `lsof +L1` can show unlinked files that are still open; do not assume every process has permission to run it.

For Kubernetes:

```bash
kubectl -n prod get pods -l app=myapp -o wide
kubectl -n prod describe pod myapp-0
kubectl -n prod logs deployment/myapp --since=10m --tail=100
```

Namespace, pod, and label names are **illustrative placeholders for operational commands**, not existing cluster objects. `kubectl logs deployment/myapp` may not fetch logs from all replicas; inspect specific pods/containers as needed.

Avoid running **delete/modify** commands directly in the first step; prioritize identifying the files, owner, pattern, lifecycle, and retention requirements first.

## 13. When the disk is nearly full: safe remediation playbook

**Goal:** restore write capability and protect the service **without accidentally deleting logs needed for investigation/audit**.

### Phase 1 — Isolate

1. Identify which filesystem/mount is full, which process is writing, and how many bytes/inodes remain.
2. Check where growth is occurring: a single active file, archives, stdout/node, collector spool, or index/backend?
3. Check appender startup/status errors, effective logger levels, and recent config/deploy changes.
4. Identify business incidents causing WARN/ERROR storms, brute-force attempts, or retry loops; this may be the **root cause to fix**, not just a volume issue.
5. Identify log types with retention/audit/legal hold requirements to avoid destroying evidence.

### Phase 2 — Reduce risk without destroying evidence

- If unnecessary DEBUG/TRACE was recently enabled, consider reverting **only the relevant logger/package** per an approved change record.
- Fix repetitive spam in code or replace noisy events with meaningful aggregates/metrics, without dropping mandatory security/audit events.
- If adding storage/volumes or separating filesystems is needed, follow the infra process with quotas/monitoring and a rollback plan.
- Use the **authoritative** retention tool for files/indexes/archives; use dry-run, explicit glob scope, and approval when audits are involved.
- If data must be deleted, verify archives/backups, legal holds, permissions, and impact on collector tail offsets **before** making changes.
- Avoid mass restarts without knowing whether restarting will drop logs buffered in an in-memory queue.

### Phase 3 — Recover and verify

- Verify filesystem free bytes/inodes return to a safe range and are no longer climbing toward danger thresholds.
- Verify new events appear at the local source, collector, and expected backend; queue lag/drops decrease.
- Measure p95/p99 latency, CPU, GC, I/O, and business throughput.
- Check that critical security/audit events remain intact as far as can be reconciled.
- Verify the retention policy actually executes on rollover/startup, not just "the XML was edited."
- Document any data that was lost or unconfirmed; do not promise zero loss if you only checked new events.

**Specifically:** deleted files still held open by a process descriptor can continue consuming disk. Diagnose with the appropriate tools and only restart/reopen when authorized, accounting for shutdown impact and backlog.

## 14. Retention and audit: bounding does not mean dropping all old logs

A system managing role changes, logins, or transactions may need an audit trail that outlives debug logs. A 3-generation rotating file configuration is **unsuitable** if it overwrites mandatory events before they are durably persisted.

| Data type | Purpose | Example policy requiring approval |
| --- | --- | --- |
| DEBUG/TRACE | Recent diagnostics | Can be short, with sampling/rotation |
| APPLICATION/ERROR | Operational investigation | Local rolling + sufficient backend days |
| HTTP_ACCESS | Request/latency analysis | Safe metadata, appropriate retention |
| SECURITY_EVENT | Detecting malicious behavior | Protected channel, loss monitoring |
| AUDIT | Accountability/reconciliation | Durable storage, separate access control, evidence preservation |

**There is no universal default number of days valid for every organization**; comply with relevant business, contractual, industry, and legal requirements. Under a legal hold, data must not be deleted simply because `maxHistory` is reached. Audits often need to be separated from short-lived file appenders and routed to a pipeline with appropriate retention rules.

Some designs use a **transactional outbox** or dedicated audit store to record business state alongside the event in a single transaction. That solves durability at one boundary, but still requires retry/duplicate handling, access control, retention, and downstream monitoring.

## 15. Limit **event volume** while preserving the right signal

Even with file rotation enabled, an error repeating thousands of times per second drives up CPU, I/O, disk, collector load, and ingest costs.

Ways to reduce volume:

- Set sensible logger levels; do not leave root at DEBUG in production long-term.
- Do not log raw request/response bodies, tokens, headers, or DTO `toString()` outputs containing PII.
- Use **concise structured fields**, event ID, outcome, error code, and route template.
- Coalesce repetitive logs in a controlled way: e.g., report `retry_failed_count=100` per interval while keeping a representative sample.
- For high-frequency diagnostics, use metrics/histograms instead of writing a log line every time.
- Sampling by event class can work for debug traffic, but **do not arbitrarily sample mandatory security/audit events**.
- When an async logging queue fills up, know whether the appender will **block, discard, or spool**; do not treat dropped logs as free space savings.

**Do not use rate limiting to mask business errors.** If WARNs spike because a database is unresponsive, fix the root cause while intentionally reducing noise.

## 16. Async appenders and disk-full impact

A synchronous file appender can slow down request threads due to file writes. An async appender reduces some producer-side overhead, **but does not make an infinite disk problem disappear**:

```text
Producer ──► Bounded queue ──► Consumer ──► File appender
                 │               │              │
                 │               │          disk / quota
                 │               │              │
              full queue ◄──── sink slow/error ─┘
                 │
           block / discard / fallback
```

**Policies involve trade-offs:**

- **Block:** preserves more events in some scenarios, but can spike request p99 latency or make the service unavailable.
- **Discard:** keeps requests moving, but drops events; unsuitable for mandatory audits without another mechanism.
- **Spool to disk:** buffers during network outages, but requires its own independent quota and cleanup.
- **Sync fallback:** can cause latency spikes right when the sink is already slow.

When the JVM is killed, an in-memory queue can lose unflushed data. A "clean" file rotation setup does not prove end-to-end event preservation.

## 17. Metrics and alerts to configure

The metrics below are **instrumentation suggestions**, not default names across all loggers:

| Signal | Alert when |
| --- | --- |
| `log_file_active_bytes` | Active file is abnormally large relative to policy |
| `log_archive_total_bytes` | Archives approach cap or cleanup fails to reduce size |
| `log_archive_file_count` | File count grows without bound |
| `filesystem_free_bytes` | Free space drops below safe threshold |
| `filesystem_free_inodes` | Inodes are low even when disk bytes remain |
| `log_bytes_written_rate` | Write rate spikes suddenly after a deploy |
| `logging_events_dropped_total` | Events are dropped due to policy or errors |
| `logging_queue_depth` | Queue remains elevated over time |
| `logging_sink_write_errors_total` | Appender hits permission/ENOSPC/I/O errors |
| `collector_ingest_lag_seconds` | Source has events but backend lags |
| `collector_spool_bytes` | Spool growth threatens node disk |
| `archive_cleanup_errors_total` | Rollover/delete/permission failures |
| `last_successful_rollover_timestamp` | Rollover does not happen as expected |
| `audit_event_gap_count` | Gaps detected if the system defines reliable sequencing |

For disk, **use both percentage and remaining bytes**, because very small and very large filesystems have different practical thresholds. You can configure a "time to full" forecast based on recent growth rate, but treat it as an estimate since traffic varies.

Do not turn request IDs, trace IDs, arbitrary filenames, or user IDs into unbounded-cardinality metric labels.

### SLOs and policy enforcement

Checks can take forms such as:

- The active file does not grow indefinitely across multiple rollover periods.
- After archive cleanup, archive bytes remain within the published policy in steady state.
- No expired file remains **too long** without processing, except under valid legal hold.
- Log ingestion and audit latency stay within agreed thresholds.
- No disk-full event corrupts the application database or temporary storage due to filesystem contention.
- Every retention change and delete permission change has a change record or audit entry.

**Do not promise "maxFileSize=50MB means the file will never exceed 50MB by a single byte."** Measure against appropriate thresholds, accounting for active + archive + temp + other writers and cleanup latency.

## 18. Regression testing: proving rotation and retention work

### Testing Logback/Log4j2 on a temporary filesystem

1. Run the service/fixture with the **exact production backend version** and an isolated test directory, never production.
2. Set small thresholds and emit a few hundred **secret-free** events; verify rollover is triggered.
3. Verify the active file and archive pattern, file index, compression, encoding, and event IDs.
4. Simulate multiple time periods in the fixture using an appropriate mechanism without waiting days; verify cleanup runs on rollover or startup.
5. Verify `maxHistory` by **time period**, not by assuming a fixed file count.
6. Verify `totalSizeCap` on **archives**; include active and temporary files in separate capacity tests.
7. Verify archives have no duplicate/missing events beyond defined semantics; during rapid rotation, confirm the collector does not lose its tail offset.
8. Place a file outside the glob and confirm cleanup **does not delete it by mistake**.
9. Test permission denied, rename/compress failures, and disk pressure in an isolated environment.
10. Reconcile source events against the backend (ingest) if the system uses a collector.
11. Verify alerts fire when an appender fails to initialize or the rotation policy is ineffective.
12. Test across application restarts/deploy rollouts, since cleanup may only occur after rollover/startup.

### Boundary and negative tests

| Case | Outcome to prove |
| --- | --- |
| FileAppender only, no rolling | Preflight/config linter flags the anti-pattern |
| `maxFileSize` set without retention | Archives grow → policy test FAILS |
| Logback `maxHistory=0` | Does not delete archives by age; another policy is required |
| Combined daily + size rollover | Has `%d` and `%i`; multiple files in one day do not overwrite each other |
| Right at rollover boundary | Active file is not corrupted and no events are lost outside policy |
| Extremely long single event | Rollover may slightly exceed threshold; event size cap works |
| Disk full | Alert fires; application follows tested failure policy |
| No logs for many hours | Cleanup follows actual semantics, without assuming exact cron timing |
| Collector blocked | Node/app archive has sufficient spool and reports when events are lost |
| Multiple processes on same file | Cannot accidentally co-write without a supported mechanism |
| Legal hold/audit | Mandatory data is not deleted under debug log policy |
| Restore from backup | Retention is re-evaluated; expired data is not resurrected outside policy |
| Old file not matching glob | Reported/investigated, not wiped indiscriminately across the directory |
| JVM killed during compression | Failure is detectable and an appropriate copy is preserved |
| Release upgrades backend version | Rolling and retention configs remain valid |

### Canary data test

Use only **fake** strings such as `FAKE_SECRET_CANARY_479` in fixtures. The goal is to ensure nobody uses "log cleanup" as a substitute for **not logging secrets in the first place**. Strip sensitive fields at the source before reaching the sink. Never use real tokens for testing.

## 19. Preventing accidental deletion with globs or retention jobs

An overly broad cleanup job is just as dangerous as missing cleanup:

```text
/var/log/apps/
   checkout/
       checkout.2026-11-10.0.log.gz
   identity/
       audit.2026-11-10.log.gz
```

Setting `Delete basePath="/var/log/apps"` with an overly broad glob like `*.log.gz` can delete another service's audit logs. **Separate directories/namespaces by owner and retention class**, apply least-privilege delete permissions, restrict `maxDepth`/patterns, check symbolic links, and run dry-run before enabling.

Do not arbitrarily run shell scripts like `find /var/log -type f -mtime +7 -delete` on production servers. A broad command can delete files with the wrong age, wrong owner, wrong timezone/mtime, or data under legal hold.

When retention must be adjusted, follow a change process:

1. Inventory files/indexes/owners and current policies.
2. Run a **dry-run**, listing candidates, total bytes, and legal hold exceptions.
3. Confirm data still needed for incidents/audits is stored in the proper location.
4. Approve the scope and rollback/escalation conditions.
5. Roll out incrementally, checking counts/sizes before and after.
6. Audit who made the change and monitor for anomalies.
7. Reconcile source/archive/backend and the recovery plan.

## 20. Related anti-patterns to avoid

| Anti-pattern | Why is it dangerous? | Replace with |
| --- | --- | --- |
| Single `FileAppender`, no rolling | Active file grows forever | `RollingFileAppender` or explicit host rotation |
| Bounding only per-file size | Archives can still grow unbounded | `maxHistory`/size cap/retention |
| Daily `maxHistory` with huge single-day traffic | Active/archives for one period can be huge | Add size-based rolling if needed |
| Raising root to DEBUG indefinitely | Volume, CPU, and PII exposure increase | Package-scoped, time-bounded/rollback, safe fields |
| Logging full request/response in production | Huge events, secret leaks | Structured allowlisted fields |
| Rotating the same file with both app and logrotate | Races, stale FDs, lost/duplicated data | Single rotation owner |
| `copytruncate` for mandatory audits | Race window drops lines | Durable audit sink, proper reopen design |
| Checking only `kubectl logs` | Limited node history, lacks backend durability | Central ingestion + retention |
| Deleting active file to free disk | Loses evidence, may not free bytes | Controlled disk-full playbook |
| Treating file cap as a disk quota | Active/temp/other apps still consume disk | Separate quotas and disk alerts |
| Sampling all logs including audits | Drops legally/operationally required events | Distinct policies by event kind |
| Skipping cleanup because "storage is cheap" | Privacy/retention risks, rising costs | Data lifecycle policy |
| Cleaning only indexes, not snapshots | Data copies still persist | End-to-end retention inventory |
| Testing quotas with production files | Can cause an outage | Isolated temp/namespace tests |
| Using filenames from client input | Path injection or privilege bypass | Static directory/pattern, validated IDs |

## 21. Recommended design by environment

### Java running on VMs

Use a properly configured `RollingFileAppender`/`FileHandler`, a dedicated directory or filesystem quota, free space/inode alerts, and a file-tailing collector. Clearly define **who owns rotation** (Java appender or `logrotate`). For mandatory audits, design a dedicated channel rather than relying solely on short-lived debug files.

### Java in Docker/Kubernetes

Typically prefer `stdout/stderr` with node-level rotation and centralized log shipping; if the application still writes local files, enforce separate rolling/cleanup and volume policies. Evaluate whether writing to both places causes duplicates. Backend logging has a retention period independent of kubelet.

### Systems with centralized logging

Collectors, indexes, and object storage must have lifecycles, quotas, retention classes, and lag/drop metrics. A well-bounded file appender will not protect the backend if ingest rate or retention grows unbounded. Use structured logs with a stable schema and strip PII at the source.

### Audit or evidentiary systems

Do not treat rolling file counts as an evidence-preservation guarantee. Require reliable event IDs, actor/outcome fields, transactional semantics where needed, durable storage, separated permissions, and business-driven legal hold/retention. Deletions/archival must be evidenced and approved.

## 22. Rollout process from unbounded files to bounded files

Do not change configuration directly and assume all data is automatically safe. Process:

1. **Measure baseline:** bytes/s, events/s, free disk, archives, backend retention, and sensitive data risks.
2. **Classify:** application/debug/access/security/audit logs; choose retention and priority per class.
3. **Choose an owner:** appender, runtime, `logrotate`, or collector owns rotation; avoid two systems modifying the same file.
4. **Design configuration:** size/time rolling, retention/total archive cap, quotas, and alerts.
5. **Test config in staging:** startup status, rollover, compression, cleanup, permissions, and log shipper.
6. **Review audit/retention impact:** do not overwrite required logs; identify legal holds and copies.
7. **Roll out to a few instances first:** compare disk usage, event rate, collector lag, and request latency.
8. **Check active file + archive + tmp + deleted-open files:** do not look at just one file's size.
9. **Verify the backend receives new events:** no data lost due to file tail rotation/inode changes.
10. **Enable alerts and operational docs:** alert recipients, thresholds, disk-full playbook, rollback owner.
11. **Re-check after the first rollover day and one retention cycle:** did cleanup happen as expected?
12. **Keep a change record:** who changed the config, why, how to roll back, and remaining risks.

A migration may need to preserve legacy historical files before applying the new policy. Do not ad-hoc delete old files that do not match the new pattern; identify their owner and retention requirements first.

## 23. Self-check questions

**1. Is setting `maxFileSize=50MB` enough to guarantee the disk will not fill up?**

No. It only triggers rollover based on the active file's size. Archives, other files, temporary files, node stdout logs, and backend copies can still grow. You need retention, quotas, and monitoring.

**2. Does Logback's `maxHistory=7` mean keeping exactly 7 files?**

No. With a daily date pattern, it means 7 **archive day-periods**. A single day can produce multiple files when combined with size-based rolling.

**3. Can an actively written `app.log` be deleted via shell to free space immediately?**

You should not. Doing so can lose logs and may not reclaim disk space if a file descriptor is still open. Diagnose first, assess evidence preservation needs, and follow an owned playbook.

**4. Why does bounding local files not guarantee system-wide retention?**

Because collectors, backend indexes, archives, snapshots, backups, exports, and container stdout each have **their own lifecycle**.

**5. Is enabling DEBUG briefly still risky if files are already rotated?**

Yes. DEBUG can increase I/O, queue lag, log ingest cost, and accidentally expose tokens/PII. Rotation does not address the sensitivity of individual events.

**6. In what kind of system can a single large file be valid?**

It can be valid if the application intentionally writes to a file and the host/collector handles rotation, retention is tested, quotas and monitoring are in place, and it aligns with business policy. **The anti-pattern is lacking effective protection**, not using the `FileAppender` API in every situation.

## 24. Code review and operations checklist

- [ ] No active log file grows unbounded without a rotation owner.
- [ ] Policies exist for both **file size** and **archive count/age/total size** as appropriate.
- [ ] Understood that `maxFileSize` is a rollover threshold, not a filesystem quota.
- [ ] Understood that `maxHistory` counts day-periods when using a date pattern, not file count.
- [ ] Understood that cleanup runs on rollover/startup or via a designed mechanism, not guaranteed to the second.
- [ ] Disk/volume quotas or alerts exist for free bytes, inodes, and time-to-full.
- [ ] Multiple processes/pods cannot accidentally write to the same file without support.
- [ ] Appender rolling and `logrotate` are not competing over the same file.
- [ ] In Kubernetes, node stdout rotation and separate pod/volume files are handled distinctly.
- [ ] Collector tail offsets are verified across rollovers to avoid lost/duplicated events.
- [ ] Separate policies exist for DEBUG, application, security, and audit logs.
- [ ] Rotation/retention is not used as a substitute for stripping passwords, tokens, and PII at the source.
- [ ] Runbooks exist for disk-full, compression/rename failures, collector lag, and sink errors.
- [ ] Rollover, multiple archives in one day, restarts, failures, and retention have been tested.
- [ ] Archive deletion uses restricted globs/paths, least privilege, and dry-run before enabling.
- [ ] Owner, change record, monitoring, rollback plan, and post-rollout verification are in place.
- [ ] Backend copies, archives, snapshots, and exports have their own lifecycles.
- [ ] Audits and legal holds are not deleted under short-lived debug log policies.

**Remember:** unbounded log files are a **resource and reliability anti-pattern**, not just a storage issue. Fixing it properly requires bounding **the active file, archive count/total size, event rate, infrastructure capacity, and backend lifecycle**, while protecting security/audit events. Rotation is a mechanism; **retention + quotas + monitoring + testing** are what form a reliable operational safeguard.

### References

- [Logback — RollingFileAppender, TimeBasedRollingPolicy, SizeAndTimeBasedRollingPolicy](https://logback.qos.ch/manual/appenders-rolling.html)
- [Logback — Appenders, lifecycle and error status](https://logback.qos.ch/manual/appenders.html)
- [Apache Log4j2 — Rolling file appenders, triggering policies, Delete action](https://logging.apache.org/log4j/2.x/manual/appenders/rolling-file.html)
- [Oracle Java 17 — java.util.logging.FileHandler](https://docs.oracle.com/javase/17/docs/api/java.logging/java/util/logging/FileHandler.html)
- [Kubernetes — Logging architecture and container log rotation](https://kubernetes.io/docs/concepts/cluster-administration/logging/)
- [OWASP — Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html)
- [NIST SP 800-92 — Guide to Computer Security Log Management](https://csrc.nist.gov/pubs/sp/800/92/final)
