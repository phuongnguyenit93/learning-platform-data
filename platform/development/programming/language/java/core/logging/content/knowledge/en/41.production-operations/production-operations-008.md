# Log File Rotation in Java Production Operations

## 1. What Is Log File Rotation and Why Is It Needed?

**Log file rotation (log rotation, rolling)** is the process of transitioning an actively written log file to another generation or archive name and starting to write to a new file according to a policy, usually based on **size**, **time**, or a combination of both. The goal is to control the size of the active file, prevent a single file from growing indefinitely, and support collection, compression, and log lifecycle management in production.

For example, an application writes to `application.log`; whenever a threshold is reached, the file is rolled into `application.2026-01-15.1.log.gz` and the application continues writing to a new active file. Filename syntax, numbering schemes, and compression timing depend on the specific tool.

A general pipeline:

~~~text
Java application
       |
       v
Logger -> Handler / Appender
                  |
                  v
            Active log file
                  |
            Rotation policy
               /      \
        Size/time     No trigger
            |             |
            v             v
       Roll old file   Keep appending
            |
            +--> Compress/archive/retention policy
            |
            +--> File shipper / collector
                   |
                   v
              Central log store
~~~

**Four distinct responsibilities:**

- **Rotation:** closing/transitioning the active file generation and continuing to write to a new file.
- **Retention:** deciding how many files, for how long, or up to what maximum size to keep before deleting older copies.
- **Compression/archival:** compressing or moving old files to another store; this does not imply that a deletion policy is in place.
- **Collection/shipping:** an agent reads logs and sends them to a centralized system; reading a file properly does not prove the data is durably stored at the destination.

**Key takeaway:** rotation helps manage files, **it does not by itself guarantee zero log loss, no duplicates, sufficient data for auditing, or protection against leaking personal information**. You must evaluate the application, filesystem, shipper, and collector together.

## 2. Common Rotation Models

| Policy | When does it roll? | Advantages | Things to watch out for |
| --- | --- | --- | --- |
| **Size-based** | When the file reaches/exceeds a size threshold | Prevents the active file from growing too large during peak hours | Can roll many times within a single day |
| **Time-based** | By day, hour, or interval | Easy to organize logs chronologically | A single daily file can become very large |
| **Size + time** | When the interval elapses or the size threshold is reached within the interval | Controls file size and partitions by date | Filenames need both date + generation index |
| **Startup-based** | When the application starts according to a dedicated policy | Separates logs across application runs | Frequent restarts produce many small files |
| **External rotation** | OS/agent tool renames/copies the file externally | Centralized management outside Java | Must coordinate file descriptors and reopen capability |
| **Container runtime rotation** | Runtime/kubelet rotates stdout/stderr files | Application does not need to open files itself | Different from in-JVM rotation; retention and log shipping still need policies |

Some systems combine multiple layers. For example, Java writes to stdout, the container runtime rotates stdout files, a shipper reads the runtime files, and a collector stores them long-term. Configuring an extra file appender inside Java can result in **duplicate copies** if the shipper collects both stdout and that file.

### Size-based is not a strict absolute size cap

Suppose the threshold is 10 MB. A single long record can push the file past the threshold before rollover occurs. Size-based policies typically trigger at the write point or the next check, so they **do not necessarily guarantee that every file is strictly under 10 MB to the exact byte**. Systems still need log event size limits and disk protection.

### Time-based is not retention

Rolling every day creates new daily files; **it does not mean files from 30 days ago are automatically deleted**. The tool must have `maxHistory`, generation count, `totalSizeCap`, TTL, or a separate retention policy. Do not treat timestamps in filenames as proof of timely deletion.

## 3. Choosing a Strategy by Environment

Ask these questions before configuring:

1. Do logs go to **stdout/stderr**, local files, or both?
2. Is it running **a single JVM** or multiple replicas/containers writing to the same path?
3. Is the file's purpose **on-host debugging**, a source for a log shipper, or an official archive?
4. What are the average and peak log volumes in bytes/second or GB/day?
5. Are there filesystem capacity limits, retention periods, data regulations, and collection latency SLOs?
6. When an external tool renames/truncates a file while it is being written, how will the writer react?
7. When the central destination cannot accept logs, does the shipper have a **persistent queue/checkpoint** for recovery?
8. Do critical events require a **separate audit/event store** instead of relying on standard file rotation?

A useful operational rule of thumb: in containers, **write structured logs to stdout/stderr and let the platform handle rotation/shipping** if the infrastructure is properly designed, monitored, and permissioned. On VMs/bare metal that need local files, choose **one owner for rotation** (either the logging backend or an OS tool coordinated with the application). Never let two independent tools rotate the same active file.

## 4. Java Util Logging (JUL): `FileHandler` Can Rotate by Size

The JDK includes `java.util.logging.FileHandler`. An important constructor is:

~~~java
FileHandler(String pattern, int limit, int count, boolean append)
~~~

Meaning of parameters:

- `pattern`: path or filename pattern.
- `limit`: size threshold in **bytes** that the handler uses to trigger rotation.
- `count`: number of files in the handler's rotation cycle, **including the active file**, not "number of backups plus the active file".
- `append`: whether to append to an existing file on open or start a new write cycle, depending on how the handler opens files and file state.

With `count=3`, a typical cycle has at most three file generations, e.g., `app-0.log`, `app-1.log`, `app-2.log`. As rotation repeats, older generations are replaced. This behavior is **count-based retention**, not day-based retention.

### Common JUL Filename Tokens

| Token | Meaning |
| --- | --- |
| `%g` | Generation number of the file in the cycle; typically 0 is the active file being written |
| `%u` | Unique number used to resolve filename/lock collisions across `FileHandler` instances |
| `%t` | System temporary directory determined by Java |
| `%h` | User's home directory |
| `%%` | Literal percent character `%` |

For example, the pattern `logs/app-%g-%u.log` can produce names containing both generation and unique numbers. **`%u` is not a user ID or request number.** If multiple JVMs write to the same pattern, the lock/unique mechanism may create separate files; do not treat it as a complete solution for sharing a single log file across multiple processes.

**JUL `FileHandler` supports size-based rotation**, but it does not provide a rich time-based rolling policy like dedicated rolling appenders. If you need daily/hourly rotation with compression and time-based deletion, use a backend that supports those policies or configure dedicated infrastructure with proper file descriptor handling.

## 5. Standalone Java 17 Example: Rotating Three File Generations

The following program uses **plain JDK 17** with no dependencies. It creates a dedicated temporary directory per run, configures `FileHandler` with a **512-byte/file** limit and **3 generations** total, then writes 60 synthetic events. This number of events is enough to trigger multiple rotations.

To keep output deterministic and avoid writing to the console via the parent logger, the program:

- Disables `useParentHandlers`.
- Attaches a `FileHandler` with a simple formatter: one line per event.
- Closes the handler before reading the files to flush buffers and release locks.
- Verifies the existence of the three generations and the number of retained lines.
- Prints only the verification results to stdout, without printing random temporary paths.

Create the file **`FileRotationDemo.java`**:

~~~java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Locale;
import java.util.logging.FileHandler;
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;
import java.util.stream.Stream;

public class FileRotationDemo {
    private static final int FILE_LIMIT_BYTES = 512;
    private static final int FILE_COUNT = 3;
    private static final int EVENTS = 60;

    public static void main(String[] args) throws Exception {
        // Use a separate directory per run so old logs are not overwritten.
        Path directory = Files.createTempDirectory("jul-rotation-demo-");

        Logger logger = Logger.getLogger("demo.file.rotation");
        logger.setUseParentHandlers(false);
        logger.setLevel(Level.INFO);

        String pattern = directory.resolve("app-%g.log").toString();
        FileHandler handler = new FileHandler(
                pattern, FILE_LIMIT_BYTES, FILE_COUNT, false);
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
                String line = String.format(Locale.ROOT,
                        "seq=%03d event=cache_checked outcome=OK requestId=req-demo",
                        i);
                logger.info(line);
            }
        } finally {
            // Remove and close the handler before reading files and releasing locks.
            logger.removeHandler(handler);
            handler.flush();
            handler.close();
        }

        int filesFound = 0;
        long retainedLines = 0;

        for (int generation = 0;
                generation < FILE_COUNT; generation++) {
            Path file = directory.resolve(
                    "app-" + generation + ".log");
            if (Files.isRegularFile(file)) {
                filesFound++;
                try (Stream<String> lines =
                        Files.lines(file, StandardCharsets.UTF_8)) {
                    retainedLines += lines.count();
                }
            }
        }

        System.out.println("eventsGenerated=" + EVENTS);
        System.out.println("rotationFiles=" + filesFound);
        System.out.println(
                "olderEventsRemoved=" + (retainedLines < EVENTS));
    }
}
~~~

Compile and run:

~~~bash
javac FileRotationDemo.java
java FileRotationDemo
~~~

**Exact expected stdout** when run successfully on JDK 17+ on a filesystem supporting normal file creation/writing without name/lock conflicts:

~~~text
eventsGenerated=60
rotationFiles=3
olderEventsRemoved=true
~~~

**Stderr:** empty on success. Logs do not go to stdout/stderr because they are directed to the dedicated `FileHandler`. The OS temporary directory will contain `app-0.log`, `app-1.log`, `app-2.log`; the example intentionally omits printing the path since it changes on each run.

### Step-by-Step Explanation

1. `Files.createTempDirectory` creates a fresh demo directory so log files from previous runs are not overwritten.
2. `new FileHandler(pattern, 512, 3, false)` configures byte-based rollover triggers and three files in the cycle. `false` means do not intentionally append to an old file from a previous cycle.
3. `handler.setEncoding("UTF-8")` sets the handler charset; the demo message uses ASCII only for easy byte counting.
4. The formatter returns one line per record. Dynamic timestamps are omitted to keep test output simple; production systems should typically log UTC timestamps, severity, correlation IDs, and standardized metadata.
5. 60 events exceed the capacity of three 512-byte files; older generation files are **replaced upon rolling**, so `retainedLines < EVENTS`.
6. `finally` closes the handler and releases the lock before reading the files back. If another handler is writing to the same file, its lifecycle must be managed separately.
7. Filenames are resolved via `%g`. With the demo's isolated directory and no lock collisions, generations are typically 0, 1, and 2.

**Practical note:** the 512-byte threshold and three-file limit are only to make rotation easy to observe. Production values must be chosen based on log volume, investigation window, and disk space; a byte limit does not mean a file can never exceed an absolute threshold at any instant. The example **leaves files in the temporary directory** so learners can inspect them; cleaning them up should follow environment policy without accidentally deleting another process's files.

### Why Does This Example Prove Rotation but Not Full Retention?

The program writes 60 events, but only retains the events fitting in the latest three generations. `olderEventsRemoved=true` is not a bug in the program—it is the intended consequence of count-based retention.

For systems requiring long-term investigation, you must **collect/ship logs promptly before files are replaced**, or have another durable storage step. If the collector is down longer than the local files' capacity window, some logs can disappear even though `FileHandler` is working properly.

## 6. Time- and Size-Based Rotation with Logback

When a project uses **SLF4J + Logback** and needs more flexible rolling, `RollingFileAppender` can be used. The following configuration sample is **illustrative for a Linux environment with write permissions on `/var/log/example-app`**; it requires the appropriate Logback/backend dependencies and testing on your target version, and it does not apply to JUL.

~~~xml
<configuration>
    <appender name="FILE"
              class="ch.qos.logback.core.rolling.RollingFileAppender">
        <file>/var/log/example-app/application.log</file>

        <rollingPolicy
          class="ch.qos.logback.core.rolling.SizeAndTimeBasedRollingPolicy">
            <fileNamePattern>
              /var/log/example-app/archive/app.%d{yyyy-MM-dd}.%i.log.gz
            </fileNamePattern>
            <maxFileSize>10MB</maxFileSize>
            <maxHistory>14</maxHistory>
            <totalSizeCap>1GB</totalSizeCap>
        </rollingPolicy>

        <encoder>
            <pattern>%d{ISO8601} %-5level [%thread] %logger{36} - %msg%n</pattern>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="FILE"/>
    </root>
</configuration>
~~~

Meaning:

- `<file>` is the **active file** name that the appender writes to before rollover.
- `SizeAndTimeBasedRollingPolicy` uses both the date and the `%i` index; `maxFileSize` triggers rollover when the threshold is reached within the same period.
- `fileNamePattern` is the **archive** filename pattern; `.gz` indicates compression after rollover per the policy.
- `maxHistory=14` specifies the number of historical periods retained by the rolling policy; with `%d{yyyy-MM-dd}`, this typically means **14 daily periods**, not "14 files".
- `totalSizeCap` limits total archive size according to the rolling policy's cleanup capabilities and timing, **and should not be treated as a strict hard disk quota**.
- `root` attaches a file appender; if you add a console appender, make sure you know whether the shipper collects both.

**XML configuration note:** in real deployments, `fileNamePattern` should be written **on a single line with no unintended whitespace or newlines**, for example:

~~~xml
<fileNamePattern>/var/log/example-app/archive/app.%d{yyyy-MM-dd}.%i.log.gz</fileNamePattern>
~~~

Therefore, if you copy the illustrative configuration above, use the single-line version for `fileNamePattern` to avoid unintended whitespace in the value. Other settings should be benchmarked under real load and directory creation permissions should be verified.

### Logback Is Not JUL

`java.util.logging.FileHandler` and Logback's `RollingFileAppender` are **two different logging backends**. Simply adding `logback.xml` to a plain JUL application will not automatically switch `FileHandler` to Logback policies; you need proper routing/bridging/framework integration and a tested configuration. Avoid assuming that every library supports the same parameter names or retention semantics.

## 7. Log4j 2 and Rolling Policies

With Log4j 2, the typical setup uses a `RollingFile` appender and triggering policies. Illustrative configuration structure:

~~~xml
<Configuration status="WARN">
    <Appenders>
        <RollingFile name="AppFile"
                     fileName="logs/application.log"
                     filePattern="logs/archive/app-%d{yyyy-MM-dd}-%i.log.gz">
            <PatternLayout pattern="%d{ISO8601} %-5p %c - %m%n"/>
            <Policies>
                <TimeBasedTriggeringPolicy interval="1" modulate="true"/>
                <SizeBasedTriggeringPolicy size="10 MB"/>
            </Policies>
            <DefaultRolloverStrategy max="14"/>
        </RollingFile>
    </Appenders>
    <Loggers>
        <Root level="info">
            <AppenderRef ref="AppFile"/>
        </Root>
    </Loggers>
</Configuration>
~~~

**Important:** `DefaultRolloverStrategy max="14"` relates to **the rollover counter/index limit**, not "keep exactly 14 days". To control retention by age, total size, and file count across multiple days, you need delete/retention policies appropriate for your Log4j 2 version. Test rollover, file deletion, and compression after configuring rather than inferring behavior from parameter names.

When multiple policies trigger simultaneously, an event may fall near a time/size boundary. Test naming, generation numbering, and data on both sides of the rollover boundary. Do not mix XML examples between the two backends.

## 8. External Rotation Tools: rename-create and copytruncate

On Linux/Unix, tools like `logrotate` can be used to rename, compress, and delete log files. However, a file held open by the JVM requires careful understanding.

### 8.1. Rename + create: requires writer reopen

~~~text
Before rotation:
  JVM FileHandler -> file descriptor -> /var/log/app.log

OS rename:
  /var/log/app.log -> /var/log/app.log.1
  create new /var/log/app.log

If JVM does not reopen:
  JVM still writes to old descriptor (app.log.1)
  new app.log file may remain empty
~~~

On POSIX-like systems, **renaming a path** does not automatically change the file descriptor held by the process. As a result, the JVM can continue writing to the renamed file. If an external tool rotates the file, you need a **supported reopen/reconfigure mechanism**, or let the Java backend manage rolling itself. Do not assume sending `SIGHUP` to any Java application will automatically close/reopen `FileHandler`—that behavior is **not guaranteed by default in JUL**.

### 8.2. Copytruncate: still has a race condition

`copytruncate` typically copies the contents to an archive file and then truncates the active file in place, without requiring the writer to reopen the path. However, between **copy** and **truncate**, the JVM can still write more events. Bytes written in that window risk **missing from the archive and being lost on truncate**, or causing duplicates depending on the shipper/handling. Thus it is a trade-off to preserve the descriptor, **not a zero-loss log guarantee**.

### 8.3. Pick exactly one rollover owner

Do not configure both Logback/Log4j rolling **and** `logrotate` to rename/truncate **the same active file** without an explicit design. Two uncoordinated rollover schedules can cause rename races, orphaned files, writes to archive files, compressing actively written files, or missed data by shippers.

**Best practice:** choose rotation managed by the **logging backend** or by the **OS/runtime**, and ensure writers/shippers are compatible. If the program already writes stdout/stderr to the container runtime, do not try to apply `logrotate` to stdout files inside the container as if they were the same file object.

## 9. Containers, Kubernetes, and Log Files

When Java runs in a container, it is usually recommended to **log to stdout/stderr** and let the container runtime/kubelet, node agent, or logging platform manage files and rotation externally. This avoids forcing every container to have a persistent volume just for diagnostic logs.

However, understand the boundaries:

- **JVM stdout** → container stream → node/runtime log file → agent/shipper → collector involves multiple hops.
- The runtime/kubelet may have size and file-count limits; these are **node/container policies**, not Java's `FileHandler`.
- A file rotated/deleted before the agent finishes reading it can cause log loss.
- A pod being replaced or a node losing storage before logs are shipped can cause node-local data loss.
- When an application writes to both stdout and a separate file, the agent must know which source to collect to avoid **duplicate events**.
- Using a sidecar or dedicated volume may fit certain requirements, but increases responsibility for capacity, lifecycle, retention, and permissions.

Do not confuse a **pod restart** with a **daily rollover**. A new container may have a new file while the collector still correlates them by service/pod/request/trace ID; this is a distributed observability concern, not a JVM generation policy.

## 10. How File Shippers Must Handle Rotation

In production, log files are typically tailed and shipped by an agent. A proper agent must track not only the **path name**, but also file identity/offset/checkpoint according to OS capabilities and agent design.

Cases that must be handled:

| Scenario | Risk | Testing requirement |
| --- | --- | --- |
| Active file is renamed | Shipper may keep tailing the old file or switch to the new file at the wrong time | No loss of the tail end of the old file |
| New file appears with the same active name | Old checkpoint may be wrongly applied to the new file | Detect new file and start at the right offset |
| `copytruncate` shrinks the file | Old offset is past EOF; data in the race window may be lost | Detect truncation and understand the approach's limits |
| Archive file is compressed immediately | Shipper has not finished reading the original | Delay compression/retain file long enough; avoid deleting before read |
| Agent restart | Offset updated before destination acknowledgment | Recover properly; distinguish loss from duplicate delivery |
| Multiple similarly named files | Glob may match active, archive, and copied files | Specify explicit path/include/exclude rules |
| High-speed rotation | Old files disappear before the agent catches up | Increase retention/spool thresholds or shipping throughput |
| Multiline/JSON formats | Event boundaries may be split | Parse/reassemble according to log schema |
| Windows file locking | Renaming/deleting an open file may be blocked | Test with the actual JVM, shipper, and OS |

**An offset checkpoint does not mean the event is stored in the collector.** Some shippers mark data as read before delivery completes; others have persistent buffers or deeper acknowledgments. Read the agent's contract and test crashes across read–send–ACK.

### Why Is Compressing Too Early Dangerous?

After rotation, operators may want to `gzip` the old file immediately to save space. If the shipper is still reading the old file, renaming/compressing/deleting too early can prevent the agent from finishing the remainder. Verify tailer behavior and **delay compression** policies or ensure a sufficient buffer window based on actual shipping speed.

## 11. Sizing Capacity and Retention

A rotation policy should be built from actual log volume, not chosen as 10 MB / 7 days out of habit. A rough estimation model:

~~~text
monthlyStorage = ingestBytesPerDay x retentionDays x replicaCount
                 x compressionRatio (if archives are compressed)
                 + buffer
~~~

For example, four replicas, each generating 200 MB of logs/day and retained for seven days:

~~~text
200 MB/day x 4 replicas x 7 days = 5600 MB
~~~

That is a **pre-compression estimate**, excluding bursts, indexes/metadata, active files, checkpoints, shipper spools, backups/replicas, and safety headroom. If log volume fluctuates widely, measure peak rates and add headroom.

Control all of these together:

1. **Max active file size:** prevent a single file from becoming too large to tail, transfer, and inspect.
2. **Max file count or maxHistory:** cap the number of generations or historical periods.
3. **Total size cap:** prevent archives from consuming unbounded disk space.
4. **Compression:** reduces storage at the cost of CPU/I/O and may create temporary files.
5. **Backup/central retention:** policies at the destination are independent of local files.
6. **Disk free threshold:** alert before the disk fills up, rather than waiting for `ENOSPC`.
7. **Shipper backlog window:** local files must survive long enough for the agent to ship them during collector outages.

A 1 GB archive cap does not guarantee the entire filesystem stays under 1 GB: there are still active files, logs from other services, spools, and rollover/compression overhead.

## 12. Concurrency, Multiple JVMs, and Rotation Races

### 12.1. Multiple Threads in One JVM

Logging backends usually provide the synchronization/queuing needed for a shared appender. However, misconfiguring multiple handlers pointing to the same file can cause duplicate writes, races, and interleaved formatting. Use a single, clear appender configuration path and test under concurrent load.

### 12.2. Multiple Processes or Multiple Replicas

Do not let multiple JVMs/containers write to the same file on a shared volume via the same path and assume `FileHandler` or a rolling appender will safely coordinate rollover across processes. Issues include:

- Two processes renaming/deleting/compressing the file concurrently.
- Writers holding descriptors to old generations.
- File locking depending on filesystem/OS; network filesystems may have different semantics.
- JUL's `%u` can generate distinct names on conflict, but it does not turn the setup into a **multi-process rotation coordinator**.
- Multiple replicas can have nearly identical timestamps; global ordering cannot be inferred from filenames alone.

The standard solution is **a separate log path per process/replica** or writing to stdout for centralized collection by an agent/platform. For long-term storage, use a collector and schema with appropriate service, instance, and request/trace IDs for querying.

### 12.3. Async Appenders and Shutdown

With async logging, events may still be in the queue during rollover or shutdown. The system needs a bounded drain/flush/close path with clear outcomes. However, **a shutdown hook cannot save logs when the JVM is forcibly killed, the host loses power, or a container exceeds its grace period**.

A Java application calling `handler.close()` properly during shutdown reduces data loss on normal exit; it does not replace persistent queues, fsync, acknowledgments, or real failure testing when high reliability is required.

## 13. Handling Disk Full, Permission Errors, and Rotation Incidents

| Symptom | Possible Cause | What to Check |
| --- | --- | --- |
| Log file grows forever without rolling | Policy not attached to appender; wrong level/path | Inspect active logger/backend, path, and trigger |
| Still writing to `.1` after rotation | JVM holds old descriptor after external rename | Whether a reopen mechanism exists |
| New file stays empty after logrotate | Writer has not reopened; writing to old inode | Compare descriptors/inodes and application behavior |
| Missing lines around `copytruncate` | Copy–truncate race | Switch to coordinated rolling and retest |
| Fewer log generations than expected | Threshold not reached, cleanup, different filename | Check trigger, pattern, startup, and permissions |
| Disk full despite `maxHistory` | Active file, spool, other files, uncleaned archives | Measure total filesystem usage and disk headroom |
| Cannot write `.lck` / log file | Directory permissions, lock collision, disk full | Check permissions, process/file handles |
| Appender stops writing silently | Backend reports errors internally without throwing to caller | Monitor internal status/error metrics |
| Compression saves little space | Incompressible log data or too many tiny files | Measure compression ratio and CPU cost |
| Collector misses logs after rollover | Wrong tailer offset/file identity; archive deleted too early | Test shipper rename/truncate/restart |
| Single event stored twice | Reading both stdout and file, or delivery retries | Distinguish producer, shipper, and collector duplicates |
| Rotation under load spikes latency | Compression/I/O/locks running on the hot path | Measure p95/p99 and consider async or shipper |

**JUL note:** many write errors from a `Handler` may be reported via `ErrorManager` or an internal channel rather than throwing an exception directly to the code calling `logger.info()`. Therefore, do not unit-test "logger doesn't throw" and conclude no logs are lost. Observe the backend's error channel and verify the actual files.

When file rotation hits serious errors, do not disable file permissions or grant `0777` to the log directory as a quick fix. Fix permissions following least privilege, and verify ownership of the file, archive directory, and service account.

## 14. Privacy and Security of Rotated Logs

Rotation can create **additional log copies across multiple states**: active files, compressed archives, backups, shipper-transferred files, central stores, and dashboard exports. Old files may still contain tokens/PII even after the application fixes its logger calls.

Required measures:

- **Data minimization at the caller:** avoid logging passwords, tokens, cookies, raw bodies, national IDs, or unnecessary payment details.
- **Access control:** file writers, archive readers, agents, and administrators do not necessarily need the same permissions.
- **Encryption in transit/at rest:** where policy requires, protect files/spools/backups and the transport to the collector.
- **Retention by log type:** debug, security, and audit logs serve different purposes; do not apply infinite retention to all of them.
- **Scoped deletion:** delete active files/backups/central indexes per policy; local rotation does not delete remote copies.
- **Permissions on new files:** check `umask`, ownership, group, and file mode on rollover and when `logrotate` creates files.
- **Compression/archival:** compressed archives still contain the raw data inside; do not treat `.gz` as encryption.
- **Access/replay auditing:** systems requiring dedicated auditing must have schemas and reliability stronger than an ad-hoc rolling file.

In particular, putting passwords or access tokens into **log filenames** is inappropriate; filenames can appear in process listings, monitors, backups, and alerts. Names based on date/instance and application group suffice for most use cases.

## 15. Testing Rotation Before Production

### 15.1. Formatter/Handler-Level Tests

- Generate enough events to reliably exceed the threshold (do not emit three lines and assume rotation works).
- Follow proper close/flush lifecycle before inspecting results.
- Count generated files, verify naming patterns, and check sizes/line counts.
- Confirm the newest file contains the most recent events per the backend policy.
- Verify events are not split mid-line, log encoding is correct, and multiline messages do not break NDJSON if using JSON Lines.
- Verify that after multiple rollover cycles, old files are replaced/deleted per retention.
- Do not assert an exact byte size if the backend allows variance due to record boundaries.

### 15.2. Integration and Fault-Injection Tests

| Scenario | Outcome to Evaluate |
| --- | --- |
| Exceeding size while multiple threads write | No corrupted/interleaved files; acceptable throughput |
| Crossing midnight / timezone boundaries | Correct date naming, no lost records |
| Application restart mid-cycle | `append`/startup policy works; no unintended overwrites |
| Two JVMs trying to write the same name | File/lock separation works or fails explicitly |
| Disk full | Behaves per policy and alerts; does not hide errors |
| Directory lacks write permission | Backend reports observable errors |
| Rotation while agent is tailing | No loss of old file tail, no excessive duplicate reads |
| Compression before agent finishes reading | File not deleted before completion |
| Collector disconnected for hours | Local retention suffices or event loss is measurable |
| Crash right during rollover | File/offset recovery meets expectations |
| Container restart / node replacement | Clear understanding of where logs are kept and lost |
| Logs contain a synthetic sentinel secret | Secret does not appear outside approved channels |

**End-to-end check:** generate events with synthetic IDs, let the system actually rotate files, and verify the agent/collector receives those events. Compare event counts at the logger, file, shipper, and final store. Do not claim "zero log loss" just because three generations exist on disk.

### 15.3. Operational Metrics to Monitor

- Free disk space and log growth rate (bytes/s).
- Active file size, archive file count, total archive size.
- Last rollover time, rollover/compression/archive-deletion errors.
- Log events dropped due to queue/appender/collector.
- File shipper lag/backlog and age of the oldest unsent event.
- Abnormal log write rates, spikes when `DEBUG`/`TRACE` is enabled.
- Process restart count, periods with no logs written, and permission/disk-full errors.

Do not use **request addresses, individual event IDs, or per-request changing filenames** as metric labels, as this causes very high cardinality. Use standardized service, instance, reason code, and outcome labels.

## 16. Pitfalls to Avoid

**"Having rotation means the disk can never fill up."** False. Multiple applications, spool files, active files, temporary compression files, or uncleaned archives can still fill the entire filesystem.

**"`FileHandler(count=3)` keeps three backups plus the active file."** False. `count` is the number of generations in the cycle, usually **including the active file**.

**"Logrotate renames the file, so the JVM automatically writes to the new one."** Not guaranteed. You must verify reopen/file descriptor behavior or use coordinated backend rolling.

**"Using `copytruncate` never loses logs."** False. There is a race between copy and truncate.

**"Compressing archives encrypts them safely."** False. Gzip only compresses; it does not protect secrets.

**"Once local files roll/delete, logs in the collector are gone too."** False. Central retention, backups, and exports are separate policies.

**"A `logger.info` call that doesn't throw means the log was written."** Not always true. The handler/backend may handle I/O errors internally, queues may drop events, or exporters may not have delivered them yet.

**"Just let all replicas write to `/shared/app.log` for easy viewing."** Unsafe by default. Multi-process rotation/locking on shared volumes requires dedicated mechanisms.

**"Rotation guarantees audit logs aren't lost."** False. Auditing requires additional permissions, integrity, durability, retention, and purpose-built verification.

## 17. Practical Checklist

- [ ] Clearly decide whether stdout/stderr or local files are the primary log source.
- [ ] Designate one owner responsible for rotation per active file.
- [ ] Choose size/time/both to match log volume and peak load.
- [ ] Configure size limits, generation count / history periods, and total archive cap.
- [ ] Distinguish rotation, compression, archival, retention, and collection.
- [ ] When using JUL, understand `FileHandler(pattern, limit, count, append)` and tokens `%g`, `%u`.
- [ ] When using Logback/Log4j 2, verify policies for the exact backend/version and active/archive filenames.
- [ ] Avoid external renames without reopen; understand `copytruncate` risks.
- [ ] Test multi-threaded/multi-process behavior, restarts, and high log volume.
- [ ] Test file shipper offsets/checkpoints across rename, truncate, compression, and deletion.
- [ ] Monitor free disk, file count, archive size, rotate failures, drops, and shipper backlog.
- [ ] Set file and archive permissions, protect PII, and configure retention for all copies.
- [ ] Do not rely on shutdown hooks or rotation as an audit durability guarantee.

### Self-Check Questions

**Q1.** Does `FileHandler(pattern, 1024, 3, false)` mean keeping three backup copies alongside the active file?  
**A:** No. `count=3` means three files in the rotation cycle, including the file currently being written.

**Q2.** If the JVM keeps holding the file descriptor after `logrotate` renames the file, where do logs go?  
**A:** On POSIX-like filesystems, the JVM may continue writing to the renamed file until it reopens.

**Q3.** Does `copytruncate` completely prevent log loss?  
**A:** No. Records written between the copy and the truncate can be lost.

**Q4.** Is a `.gz`-compressed file as secure as an encrypted file?  
**A:** No. Compression does not provide confidentiality.

**Q5.** In a container using only stdout, is Java required to use `FileHandler`?  
**A:** No. The container platform/shipper can manage files outside the JVM; the application still needs an appropriate schema and observability.

**Q6.** Why does keeping local files for three days not prove that logs in the central store are also kept for exactly three days?  
**A:** Because each hop has its own retention, backup, and deletion policies.

**Q7.** If you count exactly three files in the directory, can you conclude every event reached the collector?  
**A:** No. You must test the shipper, ACK/offset handling, and data in the final store.

**Remember:** File rotation is one part of **logging operations**, helping manage log size and lifecycle. In Java, `FileHandler` supports byte- and generation-based rotation; Logback/Log4j 2 offer richer rolling policies. A reliable system also requires coordinating writers with the OS/runtime and shippers, retention policies, privacy controls, observability for disk-full conditions, and end-to-end testing to prevent unacceptable data loss or duplication.
