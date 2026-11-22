# Handling Full Log Files — Safe File Logging in Java

## 1. What Is a "File Full" Situation in Logging?

**File logging** is how an application writes log events to files through a **Handler/Appender**. A critical operational scenario is **being unable to continue writing logs because no storage resources remain**, often referred to simply as "file full" or "disk full".

More precisely, it is important to distinguish:

- **File reaches configured limit:** for example, a rolling appender allows at most 10 MB per file before switching to the next file. This is a **rotation condition**, not necessarily an out-of-disk-space condition.
- **Filesystem out of space:** the operating system may report an I/O error such as **ENOSPC** (*No space left on device*) when writing. The current log file itself might still be small while the partition containing it is full.
- **Inode or quota exhaustion:** the filesystem has no inodes left for new files, the user/container has exceeded its quota, or the system lacks metadata resources; exact behavior and error messages depend on the filesystem and operating system.
- **Read-only filesystem or improper write permissions:** logs cannot be written, but the cause is not lack of space; for example, a read-only filesystem or permission denied.
- **Container/node storage limits:** a Pod or container may hit its ephemeral storage limit or be evicted before you see the entire host disk run out of space.
- **Collector or remote destination full:** this can affect the log pipeline or queue, but it is different from a local FileAppender reporting no space left on device.

**This lesson focuses on how a Java application should handle situations where a log file can no longer be written**, including detection, capacity bounding, fallback choices, alerting, and preserving business behavior.

An illustrative incident example:

~~~text
ERROR component=file-logging event=log.write.failed reason=ENOSPC
WARN  component=observability event=log.sink.degraded action=fallback_stderr
~~~

These are **illustrative lines**, not the default output of JUL or Logback. When the file destination fails, the warning event itself may also **fail to be written to the file**, so an independent signaling path is required.

## 2. Why Can a Full Log File Affect the Application?

A system that logs continuously can grow in disk usage due to:

1. **No rotation:** a single application.log file grows indefinitely.
2. **Rotation without retention:** old files are renamed forever without being deleted according to a policy.
3. **DEBUG/TRACE enabled broadly:** event volume spikes sharply.
4. **Oversized stack traces and payloads:** a repeating failure produces thousands of multi-line records.
5. **Unbounded retries:** the same logging failure or network error is logged repeatedly.
6. **Multiple replicas writing to the same partition:** total disk usage grows faster than anticipated.
7. **Other data sharing the filesystem:** databases, uploaded files, or temp files consume space, even if app logs are small.
8. **Logs unlinked while a process still holds the file open:** actual disk space may not be freed immediately.
9. **Quota/inode limits:** write operations can fail even when reported free bytes appear available.
10. **Compression/rotation failures:** temporary extra space may be needed for the new file, compressed archive, and metadata.

Consequences may include:

- Loss of new logs or partially truncated log records.
- Logger/Appender repeatedly reporting internal errors, creating noise on stderr and in monitoring.
- Application threads experiencing extra latency due to slow I/O, retries, or lock contention.
- Other components sharing the same volume also failing: writing temp files, caches, uploads, and sometimes even application data.
- Container restarts or Pod evictions due to storage limits.
- Harder incident investigation because **the most critical logs disappear right when the system is under pressure**.

**Never assume that a log-writing failure will automatically throw a business exception.** Many logging backends intentionally handle I/O errors internally to avoid breaking application flows; some wrappers or systems have different policies. You must know the contract of the library you are using.

## 3. Objectives When Responding to Full File Logging

There are three objectives to balance:

| Objective | Meaning |
| --- | --- |
| **Failure observability** | Have a signal that logging has degraded, even when the file can no longer be written |
| **Correct application behavior** | Do not lose data or falsely report success just because the logger is broken |
| **Controlled recovery** | Reduce write rate, free space according to policy, adjust configuration, and verify logging resumes |

Two scenarios have very different policies:

**Routine diagnostic logs:** a failure to write an INFO line can be handled as **best effort**, degrading/falling back to console, emitting a metric/alert, and letting business operations continue if safe.

**Audit logs or events that must be durably persisted by contract:** you must not silently drop logs if writing them is a mandatory condition for completing a transaction. Use an appropriate durable mechanism such as a transactional outbox, event store, or a properly designed audit store; if it cannot be persisted, **reject or halt the operation per policy**. A plain FileAppender is usually **not sufficient** to provide strict audit guarantees.

Do not apply the same "catch and ignore" approach to both categories of events.

## 4. How Java Applications Write to Log Files

### 4.1. With JUL

A typical path:

~~~text
java.util.logging.Logger
            |
            v
       LogRecord
            |
            v
        FileHandler
       (level/filter)
            |
            v
         Formatter
            |
            v
       File system
~~~

**java.util.logging.FileHandler** is the JDK's file logging handler, supporting filename patterns, size limits, and rotating file counts. When the handler encounters an issue while writing, JUL uses an **ErrorManager** to report internal errors.

Key point: **do not assume `LOGGER.info(...)` throws `IOException` to its caller**. The handler typically catches and reports I/O errors through its own error-reporting mechanism. Emitting a log is not equivalent to a file write transaction whose boolean success the application can directly check.

### 4.2. With SLF4J + Logback

~~~text
org.slf4j.Logger
        |
        v
Logback Classic Logger
        |
        v
RollingFileAppender / FileAppender
        |
        v
Encoder / OutputStream
        |
        v
File system
~~~

Logback has an internal **status** system to report Appender failures and configuration initialization issues. A `logger.error(...)` call may still not throw an I/O exception up to business code. You should monitor appender/status in a way appropriate to your Logback version and deployment infrastructure.

**Logback ConsoleAppender** can write to stdout/stderr independently of FileAppender. However, attaching both appenders to root usually means **both receive normal logs**, not an automatic "switch to console only when the file is full" mechanism. If you want conditional failover, you must explicitly design and test it rather than inferring it from having two appenders.

### 4.3. An Appender Error Does Not Necessarily Mean the Filesystem Is Full

Besides disk space, you may encounter:

- Permission denied due to user or mount permissions.
- No such file or directory because the log directory does not exist.
- File descriptor limit or too many open files.
- Read-only filesystem.
- Lock conflict or colliding file patterns across multiple processes.
- Disk or storage device hardware failure.
- Quota/inode exhaustion.

Diagnosis must be based on **I/O error and filesystem evidence**, not by assuming every FileHandler failure is ENOSPC.

## 5. How Rotation Differs from Disk-Space Management

**Log rotation** is the mechanism of switching from an active log file to another file based on a condition such as size or time. **Retention** decides how long and how many old files to keep; **disk-capacity management** handles the overall storage budget.

Example:

~~~text
app.log            (active file)
app.2026-11-09.0.log.gz
app.2026-11-09.1.log.gz
app.2026-11-08.0.log.gz
...
~~~

If you only rotate without cleaning up old files, disk usage still grows. If you only cap the number of files while a single file can grow too large, the system can still fill up. You need to combine:

- **maxFileSize** threshold per segment.
- **maxHistory** or file age rules.
- **totalSizeCap** or a corresponding archive budget.
- Clear deletion/compression policies and access permission checks.
- Monitoring of filesystem capacity/quota/inodes and growth rate.
- Avoiding multiple applications dumping logs onto the same volume without budgeting.

Even with all these settings enabled, **there is no absolute guarantee that the filesystem will never fill up**. Active files, temporary files during compression, other data sources, and cleanup task timing all play a role.

## 6. Example Bounded Logback RollingFileAppender Configuration

Here is **an illustrative `logback.xml` for Java using Logback Classic**, with time- and size-based file rotation:

~~~xml
<configuration>
    <appender name="FILE"
              class="ch.qos.logback.core.rolling.RollingFileAppender">
        <file>logs/app.log</file>

        <rollingPolicy
            class="ch.qos.logback.core.rolling.SizeAndTimeBasedRollingPolicy">
            <fileNamePattern>logs/archive/app.%d{yyyy-MM-dd}.%i.log.gz</fileNamePattern>
            <maxFileSize>10MB</maxFileSize>
            <maxHistory>7</maxHistory>
            <totalSizeCap>100MB</totalSizeCap>
            <cleanHistoryOnStart>true</cleanHistoryOnStart>
        </rollingPolicy>

        <encoder>
            <charset>UTF-8</charset>
            <pattern>%d{yyyy-MM-dd'T'HH:mm:ss.SSSXXX} %-5level %logger - %msg%n</pattern>
        </encoder>
    </appender>

    <appender name="CONSOLE"
              class="ch.qos.logback.core.ConsoleAppender">
        <target>System.err</target>
        <encoder>
            <charset>UTF-8</charset>
            <pattern>%level | %logger | %msg%n</pattern>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="FILE"/>
        <appender-ref ref="CONSOLE"/>
    </root>
</configuration>
~~~

How to read this and its essential limitations:

1. **RollingFileAppender** writes to the active file **logs/app.log** and uses the rolling policy for archives.
2. **fileNamePattern** uses the date and index **%i** to name rotated segments; **.gz** indicates compressed archives.
3. **maxFileSize=10MB** limits the size of each segment before rollover under the policy; it does not mean the entire partition only needs 10 MB.
4. **maxHistory=7** in a daily policy typically retains up to a number of historical time periods, not strictly seven files; a single day can have multiple segments.
5. **totalSizeCap=100MB** caps total archive size via the policy's cleanup; it is **not an instant hard quota for the filesystem** and does not account for any other files on disk.
6. **cleanHistoryOnStart=true** helps run policy-based cleanup at startup; it does not replace ensuring sufficient free space for the application to run.
7. **logs and logs/archive** need appropriate paths and permissions; do not assume the volume is always writable in every container.
8. **ConsoleAppender** is attached in parallel: normally **every log meeting the threshold** goes to both file and stderr. It provides another observability channel when the file fails, but **is not an automatic failover that activates only when the file is full**.
9. The illustrative timestamp pattern includes an offset; if strict UTC is required, configure the timezone on the formatter according to your backend version's capabilities and verify the output.
10. Parameters, archive handling, and compression behavior should be verified against the exact Logback version in use.

A system with multiple replicas may create multiple volumes/files, so **100 MB per instance is not the total budget for the entire cluster**.

### Why Is Disk Alerting Still Necessary?

When a filesystem runs out of space, the appender may fail to create a new file or write a new record **before cleanup finishes**. Exhaustion can also come from uploads, caches, or other files outside the archive list; `totalSizeCap` does not control them.

Other rolling configurations (time-based, fixed-window, external logrotate) have different semantics. Do not blindly combine two rotation mechanisms controlling the same active file: you can lose records or corrupt file names/indices.

## 7. With JUL FileHandler: limit and count

JUL built into the JDK provides basic rotation capabilities. Example `logging.properties` file:

~~~properties
handlers = java.util.logging.FileHandler, java.util.logging.ConsoleHandler
.level = INFO

java.util.logging.FileHandler.pattern = logs/jul-%g.log
java.util.logging.FileHandler.limit = 1048576
java.util.logging.FileHandler.count = 3
java.util.logging.FileHandler.append = true
java.util.logging.FileHandler.level = INFO
java.util.logging.FileHandler.encoding = UTF-8
java.util.logging.FileHandler.formatter = java.util.logging.SimpleFormatter

java.util.logging.ConsoleHandler.level = INFO
java.util.logging.ConsoleHandler.encoding = UTF-8
java.util.logging.ConsoleHandler.formatter = java.util.logging.SimpleFormatter
~~~

Here:

- **limit=1048576** is the file size limit in bytes (approximately 1 MiB).
- **count=3** is the number of files in the rotation group.
- **%g** is the file generation index.
- **append=true** requests appending where appropriate; it does not turn FileHandler into unbounded storage.
- **JUL's ConsoleHandler defaults to stderr**, unlike Logback's ConsoleAppender which typically defaults to stdout.
- Actual filenames may include additional suffixes to avoid conflicts between handlers/processes.
- You must create the **logs** directory and ensure write permissions before running, if the filesystem does not provide them automatically.

Configuring both handlers **does not guarantee the file can always be written or prove that console will retain every record**, but it provides an alternative output path and aids diagnostics. Do not use JUL FileHandler while expecting it to read `logback.xml`; they are different backends.

### Does FileHandler Report IOException to Business Code?

Normally, logging APIs **do not return a write-success result for each `LOGGER.info(...)` call**. JUL has an **ErrorManager** to receive notifications from the Handler. Therefore, if **you must know that a record has been durably stored** before a transaction succeeds, do not use plain FileHandler as a transactional mechanism.

A dedicated writer class can return a result or throw `IOException`, but that is **the writer class's I/O contract**, which is different from a framework `Logger` call.

## 8. Runnable Java 17 Example: Safely Simulating Out-of-Space

You do not need to—and **should not—deliberately fill a real disk** to test this lesson. You can **inject an `IOException`** into an output sink to mock a full filesystem.

The example below **simulates a file-writing mechanism**, not a reimplementation of JUL FileHandler or Logback FileAppender. It shows how a component with direct I/O control can:

1. Write the first record successfully.
2. Receive an `IOException` from a simulated byte-limited sink.
3. Emit **a single alert** to stderr instead of retrying the broken sink indefinitely.
4. Route subsequent diagnostic records to stderr on a best-effort basis.
5. Inform operators that **there is no guarantee all logs were saved**, and that audit data requires a separate mechanism.

Create **FileFullLoggingDemo.java**:

~~~java
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.util.Objects;

public class FileFullLoggingDemo {
    public static void main(String[] args) {
        QuotaOutputStream simulatedFile =
                new QuotaOutputStream(40);
        SafeFileSink sink = new SafeFileSink(simulatedFile);

        sink.log("INFO event=app.started");
        sink.log("WARN event=task.retry");
        sink.log("ERROR event=task.failed");

        System.out.println("SIMULATED_FILE:");
        System.out.print(simulatedFile.snapshot());
    }

    // Simulates a file write destination that can hold at most 40 bytes.
    private static final class QuotaOutputStream extends OutputStream {
        private final ByteArrayOutputStream stored =
                new ByteArrayOutputStream();
        private final int capacity;

        QuotaOutputStream(int capacity) {
            this.capacity = capacity;
        }

        @Override
        public void write(int value) throws IOException {
            if (stored.size() >= capacity) {
                throw new IOException("SIMULATED_ENOSPC");
            }
            stored.write(value);
        }

        @Override
        public void write(byte[] source, int offset, int length)
                throws IOException {
            Objects.checkFromIndexSize(offset, length, source.length);

            // Simulates writing either the whole record or nothing,
            // keeping the demo output deterministic.
            if (length > capacity - stored.size()) {
                throw new IOException("SIMULATED_ENOSPC");
            }
            stored.write(source, offset, length);
        }

        String snapshot() {
            return stored.toString(StandardCharsets.UTF_8);
        }
    }

    private static final class SafeFileSink {
        private final OutputStream destination;
        private boolean degraded;

        SafeFileSink(OutputStream destination) {
            this.destination = destination;
        }

        void log(String message) {
            if (degraded) {
                System.err.println("FALLBACK | " + message);
                return;
            }

            byte[] record = (message + "\n")
                    .getBytes(StandardCharsets.UTF_8);

            try {
                destination.write(record);
                destination.flush();
            } catch (IOException failure) {
                degraded = true;
                System.err.println(
                        "ALERT | file-log-unavailable reason="
                        + failure.getMessage());
                System.err.println("FALLBACK | " + message);
            }
        }
    }
}
~~~

Run with **JDK 17 or higher**, no Maven or external libraries needed:

~~~bash
javac -encoding UTF-8 FileFullLoggingDemo.java
java FileFullLoggingDemo
~~~

**Exact stdout of the Java program:**

~~~text
SIMULATED_FILE:
INFO event=app.started
~~~

**Exact stderr of the Java program:**

~~~text
ALERT | file-log-unavailable reason=SIMULATED_ENOSPC
FALLBACK | WARN event=task.retry
FALLBACK | ERROR event=task.failed
~~~

If your terminal merges stdout/stderr, lines may **interleave differently** because they are two independent streams. Therefore, the output above describes **two separate streams**, without guaranteeing line ordering when a terminal or IDE combines them.

### Step-by-Step Analysis

- **QuotaOutputStream(40)** holds at most 40 bytes in memory; it does not write to the real filesystem and **carries no risk of filling the disk**.
- The first record **INFO event=app.started** plus its newline fits within the quota, so it is stored in the simulated file buffer.
- The second record requires more bytes than remain under the 40-byte limit, so the simulated sink throws **IOException("SIMULATED_ENOSPC")**.
- **SafeFileSink** transitions to the **degraded** state after the first failure, alerts once, and redirects the second record to stderr.
- The third record does not retry the broken sink; it goes straight to stderr. This avoids an unbounded retry loop while the filesystem is still full.
- Finally, the program prints what was "saved to the simulated file" to stdout for easy inspection.
- **ByteArrayOutputStream** and the sample messages use ASCII only, so byte lengths and output reproduce identically on Java 17.

### Limitations to Understand So You Do Not Misapply This

1. **This is an illustrative sink where we control `IOException` directly.** In Logback or JUL, FileAppender/FileHandler may catch and handle I/O errors internally without throwing to the Logger caller.
2. **Real file writes are not necessarily line-atomic.** A write call may partially write bytes before failing; the demo intentionally writes all-or-nothing so output is deterministic.
3. **`degraded` is a one-way state in the demo.** A real application needs a controlled recovery flow, health/status reporting, and alerts rather than permanently ignoring the file after a transient error.
4. **`System.err` may also be unavailable** or uncollected. Console fallback is a best-effort measure, not a durability guarantee.
5. **Do not use this example as an audit store.** If a contract requires durable event persistence, use a dedicated transactional mechanism or reject the operation when persistence cannot be guaranteed.
6. **The example is single-threaded.** In a multi-threaded server, transitioning to degraded state, closing/reopening the sink, and managing ordering require explicit thread safety.
7. **The alert line is emitted only once** to prevent a log storm in the demo; production systems need metric increments, alerting, and incident response workflows even without repeated log lines.

### Should stderr Fallback Be Used for All Log Types?

No. For **diagnostic logs**, stderr/stdout is a natural choice if the infrastructure collects those streams. For **mandatory audit events**, writing to stderr does not provide sufficient access control, ordering, or retention guarantees. You must define the **failure policy** for each category of information before applying a fallback.

## 9. Checking Errors in Linux Before Freeing Space

When there are signs of a full disk, identify **the exact filesystem and root cause**. On Linux, common diagnostic commands include:

~~~bash
# Filesystem disk space for the log directory
df -h /var/log/myapp

# Check filesystem inodes
df -i /var/log/myapp

# Estimate log directory disk usage
du -sh /var/log/myapp

# Find large files in the target directory without scanning the entire system unnecessarily
du -ah /var/log/myapp | sort -h | tail -n 20

# With appropriate permissions, check for unlinked files still held open
sudo lsof +L1
~~~

**These are diagnostic commands**, not commands to run blindly in every environment. The directory must exist; permissions, installed utilities, and the OS can affect the output.

### Reading the Results Correctly

- **`df -h`** reports on the **filesystem**, not the size of an individual log file.
- **`df -i`** checks inode counts, which is especially useful when there are many small files.
- **`du`** sums space for files visible along the scanned path; it **may not match `df`** because of unlinked-but-open files, filesystem metadata, and other reasons.
- **`lsof +L1`** is useful for identifying files that no longer have a directory entry but are still held open by a process; not every container has `lsof` or permissions to inspect all processes.
- **Quotas** can block writes even when `df` shows free space; use quota/cgroup/volume tools appropriate for your environment.
- **Permission denied** or **read-only filesystem** must be handled differently from ENOSPC; freeing disk space does not fix incorrect permissions.

In container environments, determine whether **the log path resides on the writable layer, a mounted volume, or the node filesystem** before interpreting `df`/`du`. Statistics from inside a container do not always reflect all storage limits enforced by the orchestrator.

### Cleanup Actions to Avoid

**Do not recklessly run `rm -rf`** on a production log directory. Never delete audit files under mandatory retention, logs still needed for investigation, or business data just to free a few GB.

**Do not arbitrarily delete an open log file expecting space to be freed immediately:** on Unix systems, the process may keep holding the file descriptor, and the disk blocks are not released until the file is actually closed. Likewise, do not truncate an actively written file without understanding the policy, as this can lose data, create unexpected gaps, or break the appender's expectations.

Prefer **approved rotate/retention procedures**, clean up archives that have aged past retention, and if you need to close/reopen a handler, do so through the application lifecycle or a controlled operational procedure.

## 10. Remediating When the Filesystem Is Truly Out of Space

An ordered operational procedure:

### Step 1 — Confirm the Error Source

Check the I/O message, filesystem path, free space, inodes, quotas, and permissions. Distinguish ENOSPC from read-only, permission errors, file locks, or storage backend failures.

### Step 2 — Assess Impact

Determine whether the service is:

- Only losing diagnostic logs.
- Slowing down due to appender I/O.
- Losing the ability to write application data on the same filesystem.
- Being restarted/evicted by the container runtime.
- Violating audit requirements or preconditions for continuing transactions.

If business data or audit records cannot be preserved, **do not continue falsely reporting success**. Isolate or halt work according to policy.

### Step 3 — Ensure an Alternative Observability Channel

If safe and deployed, prefer a console appender or metrics/health signals that do not depend on the failing file path. Avoid calling the broken FileAppender itself to report that the FileAppender is broken.

Do not create an error loop like "file write failed → logger logs this error to the same file → fails → infinite loop". Use an internal error/status channel and rate-limit alerts appropriately.

### Step 4 — Reduce Write Pressure

Adjust DEBUG/TRACE levels, throttle repeating events, trim redundant payloads and stack traces, and apply appropriate sampling. This **slows the growth rate**, though it does not by itself free space that is already full.

Do not turn off all ERROR logs or delete critical evidence just to make dashboards look quiet.

### Step 5 — Free or Expand Resources According to Policy

Check archives past their retention window and perform approved cleanup. Expand the volume/quota or move logs to an appropriate destination if needed. For open logs, understand the backend's rotation/reopen mechanism.

Avoid directly editing runtime-managed files or deleting files suspected to be logs without confirming which application owns them.

### Step 6 — Restore Write Capability

Once enough space is available, a handler/appender that entered an error state **does not necessarily recover completely on its own**. Depending on the version/backend, you may need to reconfigure, reopen the file via an application mechanism, or perform a controlled restart.

If the filesystem itself is fixed but the backend still does not accept logs, inspect the internals of the FileHandler/Appender rather than assuming free disk space is enough.

### Step 7 — Verify End-to-End

Generate a **non-sensitive test event** with a dedicated event code, verify it reaches the right file/console in the expected format, and confirm the collector can query it. At the same time, monitor disk usage, inodes, file-write errors, archive growth rate, latency, and alert health.

**Do not declare recovery solely because `df` shows more free space.** You must have evidence that **the log-writing path is actually working again**.

## 11. Running Out of Space in Docker and Kubernetes

File logging inside containers has several differences:

| Write Location | Common Risks | Recommended Approach |
| --- | --- | --- |
| Container writable layer | Data lost when container is removed; subject to ephemeral storage limits | Prefer stdout/stderr when infrastructure has a collector |
| Mounted external volume | Separate quota/full/permissions; multiple replicas may contend | Manage capacity, rotation, and permissions per volume |
| stdout/stderr logs | Runtime/daemon/node still has to store or forward streams | Configure logging driver, rotation, and log collector |
| File existing only inside image/runtime | `docker logs`/`kubectl logs` will not see this file automatically | Export to console or use a sidecar/agent to read the file |
| Separate audit store | Higher durability and access-control requirements than normal logs | Use a dedicated event-storage mechanism with an appropriate contract |

**Switching to console logging does not make the disk-space problem disappear.** The Docker daemon or kubelet may still buffer logs on the node before a collector ships them. Configure rotation/retention at the right layer, check quotas, and monitor the node as well.

Some illustrative operational commands:

~~~bash
# Docker: check the logging driver on the daemon
docker info --format '{{.LoggingDriver}}'

# Specific container: logging driver and log options of the container
docker inspect --format '{{json .HostConfig.LogConfig}}' my-java-app

# Kubernetes: inspect Pod events/conditions when suspecting storage eviction
kubectl describe pod my-java-app -n demo

# Kubernetes: view container logs if still available
kubectl logs my-java-app -n demo -c app --tail=100
~~~

Names like **my-java-app**, **demo**, and **app** are examples only; replace them with your actual resources. `kubectl logs` only provides logs from containers/runtimes that are still available and is **not an infinite historical store**. In Kubernetes, ephemeral storage eviction and node disk pressure have their own thresholds and policies—not every Pod failure is caused by a full filesystem.

### Why Shouldn't All Logs Be Stored Directly on One Shared Persistent Volume?

A single PV shared by multiple replicas can suffer from filename collisions, permission conflicts, and I/O bottlenecks. If file logging is mandatory, design clear per-instance paths and ownership, compatible rolling policies, centralized collection, and a recovery plan. For many Kubernetes environments, console + collector is a simpler choice for diagnostic logs.

## 12. Early Monitoring Instead of Waiting for Write Failures

A good strategy detects **the risk of filling up before ENOSPC occurs**.

Signals to consider:

- **Filesystem available bytes** and utilization percentage on critical volumes/paths.
- **Available inodes** on inode-based filesystems.
- **Quota or ephemeral storage usage** per container, Pod, namespace, or volume.
- **Log growth rate** to estimate time to exhaustion.
- **File/appender write error count** over time.
- **Age of the last successfully written file**, if there is a reliable way to measure it.
- **Log collector health**: backlog, dropped events, parse errors, delivery latency.
- **Frequency of ERROR levels and stack traces**, as a log storm can drive rapid disk growth.
- **Archive cleanup timing and remaining archive count**, to detect when retention stops running.

One way to think about alerting:

~~~text
Risk = low remaining space + high write rate
       + no reliable fallback/collector path
~~~

Do not set a single static threshold for every filesystem. For example, 80% may be too early for a well-managed large volume, yet too late for a small volume growing at several GB per minute. Evaluate based on **remaining bytes, consumption rate, and the operations team's response time**.

### Why Not Use the Log File Itself as the Only Alerting Channel?

If the file is full, a "Disk full" log line may never be saved. You need an observability channel in a **different failure domain**: metrics, health checks, orchestration events, or storage-platform alerts. Never assume on-call engineers will see an ERROR if the logging pipeline itself is broken.

## 13. Should the Application Stop When It Cannot Write Logs?

There is no single right answer for all log types.

| Event Type | Typical Reasonable Policy |
| --- | --- |
| DEBUG/TRACE | Best effort: controlled dropping is acceptable; increment metrics if needed |
| Operational INFO | Best effort, with alerting when the sink degrades |
| Diagnostic WARN/ERROR | Prefer an independent backup channel and preserve evidence |
| Audit with durability requirements | Do not treat console fallback as equivalent; use a dedicated store or reject the operation if needed |
| Critical business state | Guarantee via transactions/storage with a contract, not just a Logger |

If business operations can still complete safely when diagnostic logs are lost, halting the entire system may cause a larger outage. Conversely, if operations require a mandatory event to be recorded before returning success, **do not inadvertently "fail open"**.

Document clearly:

- Which log categories are best effort?
- When the log sink is unavailable, does the component continue accepting requests?
- How much time before alerting/escalating?
- What fallback and recovery mechanisms exist?
- Who approves skipping or halting audit operations?
- Do tests accurately simulate the failure domain?

## 14. Handling Errors Without Creating Loops or Hiding Root Causes

When file logging fails, some seemingly reasonable approaches are dangerous:

**Wrong — trying to log the error message through the same broken sink:**

~~~java
// Dangerous illustrative code: failure handling uses the broken file logger again.
try {
    writeLogFile(message);
} catch (java.io.IOException ex) {
    fileLogger.error("Write log failed", ex);
}
~~~

The snippet above is an **illustrative fragment**, not a standalone program; variables and methods must be defined in a real class. If `fileLogger` writes to the same broken file, the message may go nowhere. If the error handler performs unbounded retries, it risks causing a log storm and exhausting CPU.

**Better — report status via an independent path and rate-limit:**

~~~text
FILE_SINK_FAILED
   |
   +--> mark degraded / increment metric
   |
   +--> emit a status message to stderr or another channel
   |
   +--> apply the defined fallback or fail-stop policy
   |
   +--> alert and recover in a controlled manner
~~~

Some backends have internal status reporting when an appender fails; use the APIs and monitoring mechanisms supported by your backend. **Do not simply wrap `LOG.info` in a `catch (IOException)` block and expect to reliably catch FileAppender I/O errors.**

### Retrying While the File Is Still Full

Do not perform unbounded synchronous write retries inside request-handling threads. If you want to attempt recovery, use **backoff, retry limits, a circuit breaker/degraded state, and a re-check mechanism**. If an appender has stopped working, understand the backend's lifecycle API; do not arbitrarily close/reopen a FileHandler from multiple threads.

## 15. Security and Retention When Freeing Files

When the disk is full, prioritize preserving data with legal or investigative value:

- Do not delete archives within their mandatory retention period.
- Do not broadcast logs containing tokens or personal data to a wider console channel just to have a fallback.
- Do not manually upload sensitive logs to an unapproved external service.
- If archives must be compressed or moved, maintain encryption, permissions, and integrity according to policy.
- Do not set `777` permissions on the log directory to "fix" a permission error.
- If logs were truncated or lost during an incident, record **the time window and scope of data loss** in a separate incident system; do not fabricate records as if they had been generated.
- Limit log payloads, stack traces, and sensitive information even when disk space is still available.

**Freeing disk space is an operational action with data impact**—never automatically delete files based solely on a `.log` extension without knowing their ownership and retention policy.

## 16. Common Mistakes

| Mistake | Consequence | Appropriate Fix |
| --- | --- | --- |
| Treating `maxFileSize` as the whole-disk capacity limit | Still hits ENOSPC even with rotation enabled | Combine retention, `totalSizeCap`, and filesystem monitoring |
| Using rotation without cleaning up archives | Old files grow indefinitely | Configure history and storage budgets |
| Checking only `df -h` and ignoring inodes/quotas | Misdiagnosing the root cause | Check `df -i` and quotas |
| Catching `IOException` around `LOG.info` expecting to catch FileAppender errors | Write errors are handled internally by the backend | Use the backend's status/error reporting |
| Logging errors using the same broken FileAppender | Alerts are never seen | Independent error channel and health metrics |
| Unbounded file write retries | High CPU/I/O, log storms | Limit retries, use degraded state and backoff |
| Deleting an open file expecting `df` to drop immediately | Blocks remain held by the file descriptor | Check `lsof` and close/reopen in a controlled manner |
| Arbitrarily truncating an active file | May lose data and break rotation | Use approved tools and policies |
| Configuring two appenders and calling it "automatic failover" | Logs are usually duplicated; no conditional failover | Design output paths properly and test them |
| Enabling DEBUG too broadly | Logs grow rapidly and fill the disk | Enable selectively and with a time limit |
| File logging in a container without collecting files | `docker logs`/`kubectl logs` are empty | Use console logging or a file-reading agent |
| Active file is full while waiting only for archive cleanup | Logs are still lost | Check sink status, volume, and real recovery |
| Sharing disk space with business data | Business data writes also fail | Separate budgets/volumes, consider fail-stop |
| Not recording log loss during an incident | Flawed investigation due to missing data | Document gaps in an independent incident timeline |
| Relying on console fallback for mandatory audits | Fails storage guarantees | Use a durable event/audit store |

## 17. Checklist for Handling a Full Log File

You can use this checklist in operational runbooks:

1. **Is there evidence of ENOSPC?** Which error, which path, at what time?
2. **Which filesystem?** Is the active file on the host, a volume, an overlay, or a container layer?
3. **How much space remains?** `df -h`, growth rate, and other workloads sharing it.
4. **Is there an inode/quota issue?** `df -i`, quota, or ephemeral storage limits.
5. **Which appender failed?** Logback FileAppender/RollingFileAppender, JUL FileHandler, or another system?
6. **Where are logs still going?** stdout/stderr, collector, metrics, status listener?
7. **Were logs lost or truncated?** Since when, and on which service/replica?
8. **Does the issue affect only logs or also business data?** Should requests be paused?
9. **Are rotation/retention running?** Are there old archives eligible for cleanup?
10. **Are there unlinked files still held open?** Handle with the right process and timing.
11. **Has log volume been reduced?** Log levels, payloads, repeating stack traces.
12. **Is safe capacity restored and is the sink working again?** Emit a test event and read it back at the actual destination.
13. **Do alerts/monitoring see the incident?** Is there a monitoring path independent of the log file?
14. **Are architecture adjustments needed?** Console + collector, separate quotas, object-storage archiving, or a durable audit store?
15. **Have the runbook and postmortem been updated?** Root cause, lost data, preventive measures.

## 18. Self-Check Knowledge Quiz

**Question 1.** Does setting `maxFileSize=10MB` on RollingFileAppender guarantee the filesystem will never fill up?

**Answer:** No. It limits each segment under the policy, not the total capacity of the filesystem. You also need retention, an archive budget, and real disk-usage monitoring.

**Question 2.** If you call `LOGGER.info(...)` inside a `try` block and `catch (IOException)` outside, are you guaranteed to catch FileHandler errors?

**Answer:** No. JUL and Logback typically handle Handler/Appender I/O errors internally; check the backend's ErrorManager/status or use a dedicated writer with an explicit error-return contract when needed.

**Question 3.** Why might a deleted log file not immediately reduce `df` usage?

**Answer:** On Unix filesystems, a process may still hold an open file descriptor to the unlinked inode. Inspect and close/reopen through the proper lifecycle rather than arbitrarily deleting active files.

**Question 4.** Does running out of inodes always mean there are zero free bytes left?

**Answer:** No. Free bytes may remain, yet the filesystem cannot create new files because all inodes are exhausted. Always check `df -i` and actual conditions.

**Question 5.** Can stderr fallback be used for all mandatory audit events?

**Answer:** No. Best-effort console output does not guarantee integrity, durability, or auditability; use an appropriate audit store or an operation-rejection policy.

**Question 6.** Why should you avoid logging file-write errors to the same broken FileAppender?

**Answer:** The warning line will not reach the file and may trigger an error loop. Use an independent status channel, metric, or rate-limited console output.

**Question 7.** If a container uses ConsoleAppender, do you still need to worry about disk space?

**Answer:** Yes. The container runtime or node may buffer log streams before shipping them; rotation, quotas, and retention are still required at the infrastructure layer.

**Question 8.** Is `totalSizeCap=100MB` in a rolling policy a hard quota across all files of the application?

**Answer:** No. It caps archives managed by the cleanup policy; it does not control other files, the active file, or temporary space needed during rotation and compression.

**Question 9.** Why does the Java example simulate out-of-space with `QuotaOutputStream` instead of creating a huge real file?

**Answer:** To test the `IOException` branch and fallback behavior deterministically without filling the filesystem or harming the learning environment or other services.

**Question 10.** Once `df -h` shows free space again, can you immediately declare logging recovered?

**Answer:** Not yet. The Handler/Appender may still be in an error state; verify by emitting a non-sensitive test event and confirming the record reaches the target file or collector.

**Key Takeaway:** When a log file fills up, the solution is not just "delete some files." You must **distinguish rotation from ENOSPC**, understand **how the backend reports write errors**, monitor **filesystem/quotas/inodes**, maintain an **independent alerting path**, recover safely under retention policies, and **never trade away business or audit correctness just to keep logs running**.
