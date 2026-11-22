# Avoid Uncontrolled Production Dumps in Java

A dump is diagnostic data captured from a process or JVM at a point in time or over a time interval. Thread dumps, heap dumps, core dumps, Java Flight Recorder (JFR), and GC logs answer different questions. They also differ in pause time, CPU usage, file size, sensitive data exposure, and storage requirements.

In production, taking a dump without identifying the exact process, goal, resource limits, and storage location can worsen an incident. A heap dump can trigger a full GC and cause long pauses; an unbounded recording can fill up the disk; a core dump can contain most of the process memory; and a command targeting the wrong PID can affect multiple JVMs. Therefore, taking a dump must be a purposeful step in the incident process, with clear scope and time bounds.

## 1. What Is a Dump and When Is It Needed?

A dump is a state record for post-collection analysis. It does not fix the issue by itself, nor does it prove root cause without context.

| Data Type | Suitable Question | Typical Impact Level | Data It May Contain |
|---|---|---|---|
| Thread dump | What are threads running, waiting on a lock, or deadlocked? | Medium, depends on thread count | Thread names, stacks, locks, class names, some environment info |
| Heap dump (HPROF) | Which objects are retained in the heap? | High, depends on heap and contents | Object graph, strings, requests, tokens, business data |
| Class histogram | How many objects per class are in the heap? | High, depends on heap | Class names and counts/estimated memory |
| JFR recording | How do CPU, allocation, GC, locks, or I/O vary over time? | Low to high, depending on settings | Events, threads, stack traces, classes, exceptions, and metadata |
| GC log | When does GC occur, and how do pauses and heap change? | Usually low if configured appropriately | Heap metrics, timestamps, GC causes, and runtime metadata |
| Core dump | In what state did the JVM/process hit a native error or crash? | Very high; may stop the process and create a large file | Process memory, native state, threads, heap regions, and sensitive data |
| JVM fatal error log | Why did the JVM crash at the native/JVM layer? | Usually generated on crash | JVM flags, thread/native stacks, libraries, OS, and process info |

The impact levels of diagnostic commands are the JDK's assessment for those commands; actual impact also depends on heap size, thread count, CPU, I/O, filesystem, and current load. Do not interpret "low impact" as zero overhead or safe to run arbitrarily.

### 1.1. Choosing Data Based on Symptoms

- Application hangs or requests wait for a long time: start with a few thread dumps spaced a few seconds apart to compare progress and locks.
- High CPU or increased latency: use existing metrics/logs first, then consider a short JFR recording with default settings.
- Continuously growing heap or OOM: check heap metrics and GC first; only take a heap dump when object retention analysis is needed and sufficient disk space/permissions are available.
- Long GC pauses: start with GC logs and JFR; a heap dump is not the first tool for measuring pauses.
- JVM crash at the native layer: preserve the fatal error log; take a core dump only when the investigation requires native memory/a debugger and is approved.
- Transient errors: a bounded recording or pre-configured continuous logging is usually more useful than taking a manual dump after the incident has ended.

Do not take all types of dumps at once "just in case." Every additional file increases cost, sensitive data exposure, and the risk of impacting the service.

## 2. Why Uncontrolled Production Dumps Are Dangerous

### 2.1. Causing Pauses or Increasing Load

Heap dumps and class histograms may need to traverse a large number of objects. In JDK 17, `jcmd <pid> GC.heap_dump` is rated as high impact and requests a full GC by default, unless the `-all` option is used. A full GC can pause the application, increase tail latency, and cause health checks or requests to time out.

Thread dumps are usually lighter than heap dumps, but their impact is rated medium and depends on thread count. A process with tens of thousands of threads can produce large output and take time to collect.

JFR can run continuously with the `default` profile, which has low overhead. The `profile` configuration records more events and has higher overhead; it is suitable for short periods when detailed data is needed. Enabling too many events, deep stack traces, or an excessively high sampling frequency can increase CPU usage and storage size.

### 2.2. Filling Up Disk or Exhausting Quotas

A heap dump can be nearly as large as the heap data written out; a core dump can be very large depending on memory mappings and OS configuration. If written to a filesystem holding application logs, a container writable layer, or a shared volume, running out of disk space can prevent the application from writing logs, creating temporary files, or starting up.

JFR recordings also need time and size limits. An unbounded recording without `maxage`/`maxsize` or a cleanup policy can accumulate data unexpectedly.

Before creating a file, you must know:

- The target directory and actual filesystem.
- Free space, quotas, and ephemeral storage limits.
- Whether the file is written to a dedicated volume or the container layer.
- Expected size and generation time.
- Behavior when disk is full: command failure, partial file, or process impact.

Do not write dumps to a shared temporary directory or a critical production volume without confirming quotas and cleanup.

### 2.3. Leaking Sensitive Data

A heap dump can contain live objects: access tokens, sessions, request/response bodies, user information, payment data, passwords in strings, or decrypted configuration. A core dump can contain both native and JVM memory, so the scope of exposed data can be even broader than a heap dump.

Thread dumps and JFR do not usually contain the entire object heap, but they can still expose URLs, hostnames, file paths, thread names, stack traces, exception messages, tenant names, or data attached to events. GC logs are generally less sensitive, but can reveal runtime structure and operational details.

Classify dumps as sensitive production data. Do not attach raw files to public tickets, unencrypted emails, or unapproved chat channels.

### 2.4. Targeting the Wrong Process

`jcmd` sends a diagnostic command to a specified PID or main class name. According to JDK documentation, PID `0` sends the command to all JVMs accessible by the tool. Running `jcmd 0 ...` in production can affect multiple services/processes at once.

Similarly, choosing a non-unique main class name can match multiple processes. Always verify the exact PID, service instance, container, and namespace before sending a command. Do not copy a PID from another machine or reuse an old PID after a process restart, because the OS can reuse PIDs.

### 2.5. Analyzing Files Without Context

A single heap dump does not show which objects are growing over time. A single thread dump may not distinguish between a thread waiting legitimately and a deadlock. A JFR recording taken after an incident has ended may not contain the needed events.

Record the timestamp, timezone, PID, instance/pod, build version, request impact, and symptoms. If taking multiple snapshots, preserve their order and the time intervals between them for comparison.

## 3. Assess Impact Before Collection

Before each operation, answer the following questions:

1. **Hypothesis:** What needs to be proven? Deadlock, heap retention, GC pauses, CPU hotspot, or native crash?
2. **Right process:** Have the service, instance, PID, container, and JVM version been confirmed?
3. **Current load:** Is the service healthy, degraded, or currently unavailable?
4. **Impact:** Does the JDK rate the command as Low, Medium, or High? Can it trigger a full GC, pause, or heavy I/O?
5. **Capacity:** Where will the file be written, how much space is available, and are there limits?
6. **Data:** Could the file contain customer info, tokens, secrets, or personal data?
7. **Permissions:** Who approves it, who is allowed access, and who is responsible for analysis?
8. **Limits:** What are the capture count, duration, `maxage`, `maxsize`, and retention period?
9. **Stop plan:** If latency, error rate, or disk usage increases, who stops the recording and how?

If you do not yet have answers for the process, disk, or data handling permissions, stop at existing metrics/logs and ask the responsible owner for confirmation. Do not take a dump simply because a command is easy to run.

## 4. Choose Lower-Impact Tools First

A generally suitable order is:

1. Metrics, application logs, already-enabled GC logs, and dashboards.
2. JVM identity/heap summary and a few controlled thread dumps.
3. A short JFR recording with default settings, bounded by time and size.
4. Heap dump when there is evidence of memory retention/OOM and pause, disk, and privacy impacts have been assessed.
5. Core dump when investigating a native/process crash with a dedicated runbook.

This is a suggested order, not a rigid rule. If the service has already crashed, you cannot take a thread dump from a stopped process; use the fatal error log and crash artifacts saved by the OS.

### 4.1. Identifying the Right JVM

On the host:

~~~bash
jcmd -l
~~~

In a container, the PID namespace may differ from the host. Oracle documentation notes that `jcmd -l` does not list JVMs running in a separate Docker process; use tools such as `ps` inside the target container to identify the internal PID.

After confirming the right PID, check the version:

~~~bash
jcmd 12345 VM.version
~~~

Replace `12345` with the verified PID. `jcmd` must run on the same machine as the JVM and under the same effective user/group identity used to start the JVM. Attach permissions may also be restricted by containers, security policies, or how the JVM was launched.

Do not use PID `0` to "find processes." Do not use a generic main class name if multiple instances may share the same name.

## 5. Controlled Thread Dumps

A thread dump is a snapshot of the stack traces of threads in the JVM. It is useful when investigating hung requests, lock contention, thread pool worker exhaustion, or deadlocks.

Take a dump:

~~~bash
jcmd 12345 Thread.print -l
~~~

The `-l` option requests printing lock information for `java.util.concurrent`. JDK 17 rates `Thread.print` as medium impact, depending on thread count.

When state comparison is needed:

~~~bash
jcmd 12345 Thread.print -l > /secure/diagnostics/thread-01.txt
~~~

Then capture one or two more dumps at a short interval, such as 10–15 seconds, following the runbook. Use filenames with a UTC timestamp and instance/PID so previous snapshots are not overwritten. The interval and count should match how fast the incident evolves; do not create a continuous capture loop.

When reading the dumps, look for:

- Which threads are `BLOCKED` and who is the monitor/lock owner?
- Which threads are `WAITING`/`TIMED_WAITING` on a queue, future, socket, or condition?
- Do multiple dumps show the same stack trace and lock owner?
- Is a thread pool out of workers, or are all workers waiting on the same dependency?
- Are threads making progress between snapshots or stuck at the exact same point?

A thread in `WAITING` is not an error by default; thread pools and schedulers normally have waiting threads when idle. Correlate with request latency, thread states, lock owners, and multiple snapshots.

## 6. JFR: Bounded Recordings

JFR records time-series events such as CPU sampling, GC, allocation, lock contention, exceptions, and some I/O operations. It is often a good choice for high CPU or fluctuating latency because it preserves the sequence of events within a time window.

In JDK 17, the `default` profile is designed for low overhead and can be used for long-running recordings; `profile` collects more data with higher overhead and should be used for short periods when detail is needed.

Example of a 60-second recording with bounded retention time and size:

~~~bash
jcmd 12345 JFR.start name=incident-2026-11-10 settings=default duration=60s maxage=10m maxsize=256M filename=/secure/diagnostics/incident-12345.jfr
~~~

Limits to understand:

- `duration=60s` automatically stops the recording after one minute.
- `maxage=10m` limits the age of data kept on disk in the recording.
- `maxsize=256M` limits the recording size on disk.
- `filename` specifies the output file location.
- `settings=default` uses the default configuration with lower overhead than `profile`.

The `maxsize` value must be compatible with the configured max chunk size. Check the options on the exact JDK using:

~~~bash
jcmd 12345 help JFR.start
~~~

Monitor the recording:

~~~bash
jcmd 12345 JFR.check name=incident-2026-11-10
~~~

When a recording has a finite `duration`, wait for it to finish and then inspect the file. If using a recording without a `duration`, an owner must be responsible for stopping it and specifying where to save the output:

~~~bash
jcmd 12345 JFR.stop name=incident-2026-11-10 filename=/secure/diagnostics/incident-12345.jfr
~~~

If you stop a recording without specifying `filename`, the recording data may be discarded instead of saved. Never start an unbounded recording and forget to monitor it.

View an offline summary:

~~~bash
jfr summary /secure/diagnostics/incident-12345.jfr
~~~

JFR is not "free." The impact of `JFR.start` depends on settings and event configuration; the `profile` option and custom events can increase overhead. JDK 17 documentation states that a modified default configuration can exceed 1% overhead. Measure in a representative environment before applying intensive recordings in production.

### 6.1. Avoid Enabling `path-to-gc-roots` Arbitrarily

Path to GC roots is useful when suspecting a memory leak because it helps trace which roots are retaining an object. However, collecting these paths takes time and can pause the application briefly. Only enable it when a memory leak hypothesis is clear and additional collection is approved.

Do not enable all events, deep stack traces, or high-frequency sampling just to get "more data." Select events based on the question you need to answer.

## 7. Heap Dump: Only When an Object Graph Is Needed

An HPROF heap dump contains the state of objects in the Java heap. Analysis tools can use the dominator tree, retained size, reference paths, and histograms to find objects retaining memory.

Example command:

~~~bash
jcmd 12345 GC.heap_dump /secure/diagnostics/heap-12345.hprof
~~~

JDK 17 rates `GC.heap_dump` as high impact, depending on heap size and contents. The command requests a full GC by default unless the `-all` option is used. A full GC can cause a major pause. A heap dump also requires sufficient disk space and time to write the file.

The `-all` option includes unreachable objects in the dump; it changes the set of objects written, not a "safe" or "no-pause" mode. Only use it when the analysis question requires it and the operator understands the consequences.

Before taking a heap dump:

- Is there evidence of heap retention or OOM requiring object graph analysis?
- How large is the current heap, and does the target filesystem have enough free space?
- Can the service tolerate a pause/full GC under current load?
- What data will the file contain, and who is authorized to read it?
- Can it be taken from a less-loaded replica or a reproduction environment?
- Are secure file transfer and a deletion deadline in place?

If a heap dump on OOM is needed, the JVM provides these options:

~~~text
-XX:+HeapDumpOnOutOfMemoryError
-XX:HeapDumpPath=/secure/diagnostics
~~~

This mechanism automatically generates a heap dump when an `OutOfMemoryError` occurs. It must be pre-configured with appropriate disk quotas, permissions, and retention. Automatic dumping does not mean zero impact; a process experiencing OOM may lack resources to complete the operation, and the file may contain sensitive data. Do not enable it fleet-wide without checking disk capacity and retention policies.

## 8. Class Histograms Are Not Lightweight Heap Dumps

`GC.class_histogram` provides heap statistics by class. It is useful to see which classes account for a large number of objects, but JDK 17 rates this command as high impact because its cost depends on heap size and contents.

Do not use histograms as a cheap default measurement in production. If needed, verify the PID, limit the number of captures, check impact on the exact JDK, and store the output as diagnostic data. A histogram does not provide an object graph or reference paths like a heap dump, so it cannot replace retained object analysis.

You can start with `GC.heap_info` to view a high-level summary of the heap; JDK 17 rates this command as medium impact. Cross-check with metrics/GC logs before choosing heavier operations.

## 9. GC Logs: Bounded Continuous Collection

GC logs are generally useful for tracking pauses, heap occupancy, and GC frequency. On Java 17, unified logging can be configured at startup:

~~~text
-Xlog:gc*:file=/var/log/myapp/gc.log:time,uptime,level,tags:filecount=5,filesize=20M
~~~

This example creates rotating log files: up to five files, each around 20 MB. Choose the path, file count, and size according to your volume, throughput, and actual operational policies.

GC logs differ from heap dumps:

- GC logs record GC events and heap statistics over time.
- Heap dumps record the object graph at a single point in time.
- GC logs are usually suitable for monitoring trends and pauses.
- Heap dumps are suitable for analyzing object retention when a memory leak hypothesis already exists.

Do not enable GC logging with an unbounded file path on a shared filesystem. Check rotation, write permissions, quotas, and how logs are collected when a container restarts.

## 10. Core Dumps and JVM Fatal Error Logs

A core dump is data generated by the OS/debugger from a process upon a crash or when requested. It can contain native memory, the Java heap, thread stacks, loaded libraries, and other process data. The file size can be large, and generating a core dump can stall the process or spike I/O.

A JVM fatal error log (typically named `hs_err_pid*.log`) is a text file written by HotSpot when encountering a fatal error. This file can contain the signal/exception, native stack, threads, JVM flags, loaded libraries, and environment details. It differs from a core dump: a fatal error log is a text report, whereas a core dump is an OS-level memory/process snapshot.

Operational rules:

- Preserve the original fatal error log along with the timestamp and build/runtime identity.
- Take a core dump only when needed to analyze a native/JVM crash with a debugger or the responsible team.
- Never run a command that forces a process to abort just to "test whether a core dump is generated."
- Check the OS core pattern, quotas, filesystem, read permissions, and retention policy before enabling core dumps.
- Analyze offline on a machine with restricted access; do not open sensitive production files on unmanaged personal machines.

A core dump is not a substitute for a heap dump for every OOM. Choose the data type based on the error type and the intended analysis tools.

## 11. Control Storage Location, Access Permissions, and Retention

Every dump needs a clear lifecycle:

1. **Dedicated directory:** Use a dedicated diagnostics volume; do not write to the application directory or container writable layer unless necessary.
2. **Least privilege:** Only the service account or incident responders may create or read the files.
3. **Encryption:** Encrypt at rest and in transit; manage keys according to organizational procedures.
4. **Naming:** Include service, instance, PID, UTC timestamp, dump type, and incident ID.
5. **Quotas:** Limit file count, total size, and size per incident.
6. **Retention:** Set a retention period matching the purpose; delete automatically upon expiration.
7. **Audit:** Log who created, downloaded, analyzed, shared, and deleted the file.
8. **Transfer:** Use an approved artifact store or secure channel; verify checksums after transfer.
9. **Redaction:** Where possible, filter or extract only the necessary parts before sharing widely.
10. **Cleanup:** Confirm that copies, analysis caches, and temporary files are all cleaned up after the incident.

Do not assume that files in `/tmp` or a personal workspace will disappear on their own. Container volumes, node disks, backups, and artifact stores can retain copies longer than expected.

## 12. Runbook for Production Diagnostics

A controlled procedure can include the following steps:

### Step 1: Record the Incident

Record the incident ID, service, environment, build/version, instance/pod, PID, UTC timestamp, symptoms, relevant metrics, and owner. Do not include tokens or customer data in filenames or logs.

### Step 2: Check the Baseline

Use dashboards, application logs, GC logs, and already-collected JVM info. Determine whether the issue affects the entire fleet or a single replica. Do not take dumps on all replicas at once.

### Step 3: Select One Representative Process

Identify the exact PID on the right host/container and check the JVM version. Verify the service identity to avoid attaching to a sidecar, agent, or another JVM on the same node.

### Step 4: Start with Lower-Impact Measurements

If the process is hung, take a small number of thread dumps per the runbook. If CPU/latency is high, consider a short default JFR recording with bounded `duration`/`maxage`/`maxsize`. Monitor latency, error rate, CPU, memory, and disk during collection.

### Step 5: Escalate Only With Justification

Take a heap dump only when an object graph is needed to check retention/leaks and full GC, pause, disk, and privacy impacts have been assessed. Take a core dump only when investigating a native/JVM crash with owner approval.

### Step 6: Verify the File

Check file existence, size, timestamp, checksum, and basic contents. Do not open or send raw files to unapproved analysis tools.

### Step 7: Analyze and Close the Incident

Analyze in a restricted-access environment. Document conclusions, evidence, limitations, and remediation. Afterward, delete the files per retention policy, verify copies/backups, and revoke temporary permissions.

### Step 8: Improve Observability

If the issue recurs, prioritize metrics, logs, bounded JFR, GC logging, and appropriate alerts so you do not need to take uncontrolled emergency dumps next time.

## 13. Safe Automation

Automated dumps can be useful if limits are designed in:

- Enable heap dump on OOM only on workloads where disk capacity, path, permissions, and retention have been verified.
- Use a JFR default continuous recording with `maxage`/`maxsize` limits when there is a clear operational need.
- Limit the number of concurrent recordings on a single JVM.
- Set quotas per service/instance so one process cannot fill the node disk.
- Use unique filenames by PID/time/incident ID to avoid overwriting.
- Alert when a recording exists past its time limit or disk usage exceeds a threshold.
- Do not automatically take heap/core dumps on every replica just for a short-lived alert.
- Review runbooks when upgrading the JDK because commands, options, and impact levels may change.

When using continuous JFR, on-call responders should know how to check existing recordings with `JFR.check` and how to dump the required time window. Do not start a new recording when a suitable one is already running, unless there is a clear reason.

## 14. Anti-Patterns to Avoid

| Anti-Pattern | Risk | Appropriate Practice |
|---|---|---|
| Running `jcmd 0 GC.heap_dump ...` | Sends command to every accessible JVM | Specify a verified PID |
| Taking a heap dump as soon as memory rises | Full GC/pause, large file, data exposure | Check metrics/GC logs, assess retention, and get approval |
| Looping heap dumps continuously | Increases pauses, CPU, and disk I/O | Define minimum snapshot count, compare histograms/metrics first |
| Running class histograms at short intervals | High-impact command | Use lighter metrics; take histograms only when needed |
| Unbounded JFR `profile` recording | High overhead and accumulating files | Use `default` or explicit `duration`/`maxage`/`maxsize` |
| Enabling `path-to-gc-roots` at all times | Time-consuming collection, possible pauses | Enable only during targeted memory leak investigations |
| Writing dumps to `/tmp` or root filesystem | Can fill disk/container layer | Use a diagnostics volume with quotas |
| Storing dumps on personal machines | Loss of access control and retention | Use an approved secure storage location |
| Posting heap/core dumps in tickets/chat | Exposes all or most process data | Share filtered analysis results, or use secure transfer |
| Omitting PID/instance/time | Unknown which process the dump belongs to | Attach metadata and incident ID |
| Failing to stop recordings | File size and overhead keep growing | Set `duration`/`maxage`/`maxsize`, assign an owner to monitor |
| Leaving copies behind after an incident | Sensitive data persists unexpectedly | Clean up and audit all copies |

## 15. Java 17 Example: Creating a Lab Process for Safe Practice

The example below creates a small process to understand how to inspect JVM state. Run it in a lab directory on a development machine, not as a production command.

Create `DumpLab.java`:

~~~java
import java.util.ArrayList;
import java.util.List;

public final class DumpLab {
    public static void main(String[] args) throws InterruptedException {
        List<byte[]> retained = new ArrayList<>();
        for (int i = 0; i < 8; i++) {
            retained.add(new byte[128 * 1024]);
        }

        System.out.println("DUMP_LAB_READY");
        if (args.length > 0 && "--self-test".equals(args[0])) {
            return;
        }
        while (true) {
            Thread.sleep(1000);
        }
    }
}
~~~

Compile and run:

~~~bash
javac --release 17 -d out DumpLab.java
java -Xms16m -Xmx32m -cp out DumpLab
~~~

Output:

~~~text
DUMP_LAB_READY
~~~

Open a second terminal, find the PID of the lab process with `jcmd -l`, then replace `<pid>` with the actual PID:

~~~bash
jcmd <pid> VM.version
jcmd <pid> Thread.print -l
jcmd <pid> GC.heap_info
~~~

To try JFR, use a short bounded recording:

~~~bash
jcmd <pid> JFR.start name=lab settings=default duration=10s maxage=1m maxsize=64M filename=lab.jfr
jcmd <pid> JFR.check name=lab
jfr summary lab.jfr
~~~

A heap dump should only be tried in the lab after understanding that the command requests a full GC by default:

~~~bash
jcmd <pid> GC.heap_dump lab.hprof
~~~

You can verify the lab code and stdout without keeping the process running long-term using:

~~~bash
java -Xms16m -Xmx32m -cp out DumpLab --self-test
~~~

Exact output:

~~~text
DUMP_LAB_READY
~~~

After practicing, stop the lab process with Ctrl+C and delete lab files as needed. This example is not a production runbook; production requires defined process identity, approval, secure storage, resource budgets, and retention.

## 16. Checklist Before, During, and After Taking a Dump

### Before Taking

- [ ] Diagnostic question and required dump type are defined.
- [ ] Exact service, instance, container, PID, and JDK version are confirmed.
- [ ] Command impact on the exact JDK has been checked.
- [ ] Current load and pause/latency tolerance have been assessed.
- [ ] Disk space, quotas, filesystem, and storage location have been checked.
- [ ] Potential sensitive data exposure has been identified.
- [ ] Approver, owner, and file recipient are assigned.
- [ ] Limits on time, count, size, and retention are set.
- [ ] Stop conditions are prepared if service health or disk degrades.

### During Collection

- [ ] Target only the exact PID; never use PID 0.
- [ ] Do not take multiple dump types simultaneously unless necessary.
- [ ] Monitor latency, error rate, CPU, memory, and disk.
- [ ] Record UTC timestamp, incident ID, PID, and instance.
- [ ] Stop the recording when the time limit is reached or the goal is met.

### After Collection

- [ ] Verify the file, size, timestamp, and checksum.
- [ ] Store the file in an encrypted location with proper access controls.
- [ ] Do not send raw files over unapproved channels.
- [ ] Analyze offline in a restricted-access environment.
- [ ] Document conclusions and the limitations of the evidence.
- [ ] Delete the file and all copies when retention expires.
- [ ] Revoke temporary access permissions.
- [ ] Update runbooks/observability to avoid repeating emergency dumps.

## 17. Key Takeaways

A dump is evidence with a cost, not a default action every time production has an error. Thread dumps help inspect threads/locks; heap dumps help analyze object retention but have high impact and request a full GC by default; JFR provides time-series data with overhead depending on settings; GC logs help track pauses/heap; core dumps serve native/process crash investigations and can contain highly sensitive memory.

Choose the data type based on your hypothesis, verify the exact process, bound time/size, monitor impact, and manage files like production data. Only take a dump when the goal, owner, access permissions, storage location, and deletion deadline are clearly defined.

References:

- [Oracle Java SE 17 — The jcmd Command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html)
- [Oracle Java SE 17 — Diagnostic Tools](https://docs.oracle.com/en/java/javase/17/troubleshoot/diagnostic-tools.html)
- [Oracle Java SE 17 — Prepare for Troubleshooting](https://docs.oracle.com/en/java/javase/17/troubleshoot/prepare-java-troubleshooting.html)
- [Oracle Java SE 17 — Troubleshooting Guide](https://docs.oracle.com/en/java/javase/17/troubleshoot/troubleshooting-guide.pdf)
- [Oracle Java SE 17 — The java Command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html)
- [Oracle Java SE 17 — jfr Command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jfr.html)
- [JDK Flight Recorder — Java Flight Recorder API](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/jdk/jfr/package-summary.html)