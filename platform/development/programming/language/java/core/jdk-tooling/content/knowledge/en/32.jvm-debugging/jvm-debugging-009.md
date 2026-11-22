# Safe Production Debugging with Java

## 1. Goals and Principles

Safe production debugging means gathering enough evidence to identify the root cause of an incident while keeping the application serving requests, protecting data, and controlling the impact on the JVM.

In production environments, prioritize diagnostics using metrics, logs, distributed traces, JFR, and diagnostic commands with an appropriate impact level. Breakpoints, heap dumps, class histograms, enabling global debug logging, or changing JVM flags can alter load, pause times, disk usage, or application behavior.

A sound workflow should:

- Identify the exact JVM, container, JDK version, and the time the error occurred.
- Record a baseline from metrics before running diagnostic commands.
- Start with low-impact information.
- Increase collection level once a specific hypothesis is formed.
- Limit duration, size, and data scope.
- Record the command, timestamp, PID, and results for cross-referencing.
- Protect all dump files, recordings, and logs as sensitive data.

No diagnostic command is completely free. Even read-only commands must attach to the JVM, take a snapshot, or print data; the time and impact depend on thread count, heap size, collector, event settings, and current load.

## 2. Classifying Impact Levels Before Running Commands

`jcmd` is the primary diagnostic tool recommended by Oracle for modern HotSpot JDKs. Each diagnostic command includes an Impact rating in the target JVM's help output. The Impact level is a guide to relative cost, not a guarantee that the command is always safe under every load.

Example verified on Azul JDK 24.0.2:

| Impact Level | Example Commands | Effect and Notes |
|---|---|---|
| Impact: Low | `VM.version`, `VM.uptime`, `VM.flags`, `VM.log list` | Reads version, uptime, flags, or current log configuration |
| Impact: Low | `JFR.dump` | Writes data from a running recording to a file |
| Impact: Medium | `GC.heap_info` | Reads general heap information |
| Impact: Medium | `Thread.print`, `Thread.dump_to_file` | Captures thread stack traces; cost depends on thread count |
| Impact: Medium | `JFR.start` | Starts a recording; impact varies by profile and event settings |
| Impact: Medium | `VM.native_memory` | Reads native memory statistics if NMT is enabled |
| Impact: High | `GC.class_histogram` | Scans the heap to tally objects by class |
| Impact: High | `GC.heap_dump` | Writes an HPROF file; requires a full GC by default unless `-all` is used |

Always verify the exact command on the target JVM:

~~~bash
jcmd <pid> help
jcmd <pid> help Thread.print
jcmd <pid> help GC.heap_dump
jcmd <pid> help JFR.start
~~~

Command names, options, and Impact levels may vary by JVM vendor and JDK version. Use the help output from the affected process rather than blindly copying a command from a development machine.

## 3. Identifying the Right JVM Before Attaching

List the Java processes visible to JDK tools:

~~~bash
jcmd -l
~~~

Alternatively, use:

~~~bash
jps -l
~~~

Confirm the PID using the main class, command line, service name, or information from the process manager. On a machine running multiple Java applications, never guess the PID based solely on output line order.

Check the version and uptime:

~~~bash
jcmd <pid> VM.version
jcmd <pid> VM.uptime
~~~

View the diagnostic commands supported by the JVM:

~~~bash
jcmd <pid> help
~~~

`jcmd` must run on the same machine as the JVM and with the same effective user/group identifiers (UID/GID) that started the JVM. When using Docker or containers, the PID inside the container may differ from the PID on the host. Run commands inside the appropriate container or PID namespace and confirm the process using `ps` or `jcmd -l` there.

Do not run diagnostics on an unidentified process. Record the PID, application name, container/pod, node, and JDK version to avoid collecting data from the wrong instance.

## 4. Starting with JVM Information Commands

The following commands are typically the initial inspection step:

~~~bash
jcmd <pid> VM.version
jcmd <pid> VM.uptime
jcmd <pid> VM.flags
jcmd <pid> GC.heap_info
~~~

- `VM.version` reports the JVM/JDK version.
- `VM.uptime` reports how long the JVM has been running.
- `VM.flags` prints the current VM flags, including heap sizing and collector flags.
- `GC.heap_info` provides an overview of the heap and metaspace.

`VM.flags` can help detect unexpected heap or collector configurations. `GC.heap_info` has Medium Impact, so consider current load before running it repeatedly.

Avoid printing all system properties, command lines, or VM environment details to public chat channels or tickets. `VM.command_line`, `VM.system_properties`, and `VM.info` can expose startup arguments, paths, environment variables, internal URLs, or misconfigured credentials. If collection is necessary, store them in a restricted-access location and redact them before sharing.

## 5. Using Thread Dumps to Investigate Hung Requests

A thread dump records thread states and stack traces at a point in time. It is a fast way to find threads running on CPU, waiting on a monitor, waiting on a condition, or blocked.

Print a thread dump with lock information:

~~~bash
jcmd <pid> Thread.print -l
~~~

Write to a plain-text file:

~~~bash
jcmd <pid> Thread.dump_to_file -format=plain C:\secure\incident\threads.txt
~~~

Write to JSON:

~~~bash
jcmd <pid> Thread.dump_to_file -format=json C:\secure\incident\threads.json
~~~

`Thread.print` and `Thread.dump_to_file` have Medium Impact, depending on the number of threads. Dump files can be large in applications with thousands of threads; check disk space and write permissions before saving.

If the application is hung, take several thread dumps spaced about 5–10 seconds apart. Compare the same thread across samples to see whether its stack is progressing or stuck at the same location. A thread in the `RUNNABLE` state is not necessarily consuming CPU; correlate it with CPU metrics and the stack trace. `BLOCKED` typically indicates waiting on a monitor; `WAITING` and `TIMED_WAITING` may be normal behavior for pools, schedulers, or I/O.

### Capturing a Thread Dump via OS Signals

If you cannot attach with `jcmd` but have access to the JVM console:

- Windows: press Control+Break in the console attached to the JVM.
- Linux/Unix: send `SIGQUIT` using `kill -QUIT <pid>`.

HotSpot typically writes the thread dump to the process's stdout/stderr. Check where the service redirects output. This signal is not the same as `SIGKILL`; never use `kill -9` to obtain a thread dump because it terminates the process without allowing the JVM to handle the diagnostic request.

## 6. Reading Thread Dumps and Identifying Anomalies

Common thread states:

| State | Meaning | What to Check |
|---|---|---|
| `RUNNABLE` | Thread is running or ready to run in the JVM | CPU, repeated stacks, and hot methods |
| `BLOCKED` | Thread is waiting to acquire an intrinsic monitor | Thread holding the lock, lock order, and synchronized blocks |
| `WAITING` | Thread is waiting indefinitely for a condition | Pools, queues, latches, futures, or signals |
| `TIMED_WAITING` | Thread is waiting for a bounded period | Sleeps, timed waits, parks, or timeouts |

Abbreviated example from a thread dump showing lock contention:

~~~text
"safe-worker-0"
   java.lang.Thread.State: TIMED_WAITING (sleeping)
   at demo.SafeDebugTarget.work(SafeDebugTarget.java:14)
   - locked <0x...> (a java.lang.Object)

"safe-worker-1"
   java.lang.Thread.State: BLOCKED (on object monitor)
   at demo.SafeDebugTarget.work(SafeDebugTarget.java:14)
   - waiting to lock <0x...> (a java.lang.Object)
~~~

In this example, `safe-worker-1` is waiting on the object monitor held by `safe-worker-0`. Find the thread holding the lock, inspect the stack traces of both, and determine why the critical section is taking so long.

`Thread.print -l` displays locks and ownable synchronizers. If the JVM detects a deadlock, the thread dump may print a deadlock description along with the involved threads. Do not conclude a deadlock exists from a single `BLOCKED` thread alone; verify the lock-wait cycle and check multiple snapshots over time.

## 7. Using JFR to Capture Short-Window Incidents

Java Flight Recorder (JFR) records timestamped runtime events, including CPU samples, allocation samples, GC, lock contention, threads, and I/O. JFR is built into HotSpot and can be used in production with appropriate settings.

Start with the default configuration for 60 seconds:

~~~bash
jcmd <pid> JFR.start name=incident settings=default duration=60s filename=incident.jfr
~~~

Check the recording:

~~~bash
jcmd <pid> JFR.check name=incident verbose=true
~~~

To save a snapshot while the recording continues:

~~~bash
jcmd <pid> JFR.dump name=incident filename=incident-snapshot.jfr
~~~

If the recording has no duration and needs to be stopped manually:

~~~bash
jcmd <pid> JFR.stop name=incident
~~~

`default.jfc` generally has low overhead and is suitable for baseline collection. `profile.jfc` enables additional profiling data, which can increase overhead and file size; use it only for short windows when investigating specific questions such as CPU hotspots, allocations, or lock contention.

Example of a short 30-second profile when a hypothesis requires deeper CPU/allocation visibility:

~~~bash
jcmd <pid> JFR.start name=profile settings=profile duration=30s filename=profile.jfr
~~~

JDK help classifies `JFR.start` as Medium Impact because the overhead depends on settings. Do not enable multiple heavy profiles simultaneously without evaluating total cost. If you need `path-to-gc-roots` to investigate a memory leak, understand that collection can take time and briefly pause the JVM.

## 8. Analyzing Recordings Without Modifying the Application

View a file summary:

~~~bash
jfr summary incident.jfr
~~~

View CPU execution samples:

~~~bash
jfr print --events jdk.ExecutionSample incident.jfr
~~~

View allocation samples:

~~~bash
jfr print --events jdk.ObjectAllocationSample incident.jfr
~~~

View monitor contention:

~~~bash
jfr print --events jdk.JavaMonitorEnter incident.jfr
~~~

Correlate timestamps in the recording with request latency, logs, metrics, and distributed traces. For example, if latency spikes when `jdk.JavaMonitorEnter` has long durations, inspect the waiting thread, the thread holding the monitor, and the stack traces. If CPU spikes and the same stack appears in many execution samples, examine the hot method and call path.

The absence of an event in a recording does not prove the issue did not occur. The event may be disabled, its threshold may be too high, sampling may have missed it, or the recording may not cover the right time window.

## 9. Checking the Heap Before Taking a Heap Dump

`GC.heap_info` provides an overview of the heap, metaspace, and collector regions. Use it for a quick heap health check before considering heavier operations.

A histogram tallies instance counts and shallow sizes by class:

~~~bash
jcmd <pid> GC.class_histogram
~~~

On JDK 24, `GC.class_histogram` has High Impact because its cost depends on heap size and contents. Consider current load and pause times before running it, especially on large heaps or overloaded systems. Do not run histograms repeatedly just to track a metric that can be obtained from standard metrics.

A histogram shows which classes account for the most objects/bytes, but does not explain the reference paths keeping objects alive. To understand why objects remain reachable, analyze a heap dump using a tool such as Eclipse Memory Analyzer (MAT).

## 10. Heap Dumps Are High-Cost Operations

Create an HPROF heap dump:

~~~bash
jcmd <pid> GC.heap_dump C:\secure\incident\heap.hprof
~~~

Create a gzipped dump:

~~~bash
jcmd <pid> GC.heap_dump -gz=1 C:\secure\incident\heap.hprof.gz
~~~

`GC.heap_dump` has High Impact, depending on heap size and contents. By default, the command triggers a full GC before dumping unless `-all` is specified. A full GC can cause significant pauses and increase application latency.

`-all` dumps unreachable objects as well, so it does not trigger a full GC by default. The dump may include uncollected objects; choose the mode based on your investigation question.

Before creating a heap dump:

1. Confirm the exact PID and instance.
2. Check disk space, quotas, and write permissions.
3. Choose a path with appropriate ACLs and enough room for a large file.
4. Review current load and agree on an operational window if needed.
5. Choose live/all based on the investigation goal.
6. Record the start/end times and dump type.
7. Restrict who can read the file and set a retention period.

Heap dumps can contain passwords, access tokens, sessions, request payloads, customer data, and caches. Open them only with approved analysis tools; never upload them to public services or share them in tickets or chats with broad access.

## 11. Native Memory Tracking Must Be Enabled at JVM Startup

The Java heap is not the process's entire memory footprint. Native memory can also come from metaspace, code cache, thread stacks, GC structures, direct buffers, JNI, and native libraries.

Native Memory Tracking (NMT) tracks internal JVM allocations. NMT must be enabled at JVM startup with a flag:

~~~bash
java -XX:NativeMemoryTracking=summary -jar application.jar
~~~

Or for more detail:

~~~bash
java -XX:NativeMemoryTracking=detail -jar application.jar
~~~

You can then query it:

~~~bash
jcmd <pid> VM.native_memory summary
jcmd <pid> VM.native_memory baseline
jcmd <pid> VM.native_memory summary.diff
~~~

NMT cannot be enabled retroactively on a running JVM that was started without the flag. On JDK 24, the command returns `Native memory tracking is not enabled` if the process does not have NMT enabled.

NMT can reduce performance by roughly 5–10% and consumes extra memory for tracking. It cannot track all native allocations performed by JNI code or libraries outside the JVM. Enable NMT in production only after weighing the overhead and tracking goals; use OS tools when investigating native memory outside NMT's scope.

## 12. Checking Current Logging Before Changing Configuration

View the active Unified Logging configuration:

~~~bash
jcmd <pid> VM.log list
~~~

This command shows the current outputs, tags, and levels. If GC logs or application logs already exist, analyze that data before enabling additional logging.

Enabling trace/debug for all tags can generate massive log volume, increase I/O, fill disks, and hurt latency. If you must change log levels, restrict the tags, output, duration, and size; record the original configuration so you can restore it accurately.

Do not use `VM.log` to change production logging without understanding the output and impact. Avoid enabling global debug logging simply because the root cause is not yet known.

## 13. Choosing Tools by Symptom

| Symptom | Evidence to Collect First | Next Step |
|---|---|---|
| High CPU | CPU metrics, several thread dumps, JFR execution samples | Identify hot stacks and methods |
| High latency with low CPU | Repeated thread dumps, JFR lock/I/O events, request traces | Find threads waiting on locks, network, or file I/O |
| Hung requests | `Thread.print -l` and 2–3 snapshots a few seconds apart | Find blocked threads, deadlocks, or exhausted pools |
| Continuously growing heap | Heap/GC metrics, GC logs, JFR allocation samples | Histogram; consider heap dump if needed |
| Growing process RSS with stable heap | NMT if enabled, direct buffer and OS metrics | Check metaspace, thread stacks, JNI/native libraries |
| OOM | OOM logs, heap dump if configured, GC history | Analyze retained heap and allocation paths |
| JVM crash | Fatal error log, core dump, OS logs | Analyze with Serviceability Agent/native debugger |

Do not use a heap dump to investigate every memory issue. If RSS grows while the Java heap remains stable, a heap dump may not answer the question; check NMT, direct buffers, thread counts, and native allocations.

## 14. Debuggers and JDWP in Production

JDWP is the protocol that controls a debugger. A debugger can read state, set breakpoints, evaluate expressions, and control threads. These operations can alter timing, pause threads, or cause requests to hang.

Do not expose a JDWP port to the Internet or untrusted networks. Avoid configuring listeners on all interfaces, do not leave a debugger port open longer than the investigation window, and do not use breakpoints that can suspend an application serving live traffic.

If a debugger must be used in production, obtain operational approval, restrict network access via VPN/bastion/firewall allowlist, keep the window short, and have a detach plan. Prefer JFR, thread dumps, and metrics for initial diagnosis because they collect evidence without stopping threads at breakpoints.

Do not restart an application mid-incident just to enable remote debugging without evaluating the restart impact and recovery plan.

## 15. Diagnostics in Docker and Kubernetes

The PID on the host may differ from the PID inside a container. Running `jcmd -l` on the host will also not necessarily list JVMs running in a separate Docker process.

Example of entering a container:

~~~bash
docker exec -it <container-name> sh
~~~

Then run inside the container:

~~~bash
ps -ef
jcmd -l
jcmd <pid> VM.version
~~~

For Kubernetes:

~~~bash
kubectl exec -it <pod-name> -c <container-name> -- sh
~~~

Select the right container when a pod has multiple containers. Use JDK tools already present in the image or an organization-approved diagnostic image; avoid installing packages or modifying production images during an incident without an established process.

Ensure the user running `jcmd` has the same effective UID/GID as the JVM. If the container lacks a shell or JDK tools, use a platform-approved ephemeral/debug container mechanism and verify the PID namespace, filesystem, and attach permissions before proceeding.

## 16. Attach Errors and How to Handle Them

### `jcmd -l` Does Not Show the Process

Verify that the process is running, and that you are in the right host/container/PID namespace with the right user. In Docker, run the command from inside the appropriate container or namespace.

### Unable to Open Socket File or Attach Failure

Check effective user/group, filesystem permissions, the JDK tool being used, whether the PID still exists, and the attach mechanism. The JVM may have been started with `-XX:+DisableAttachMechanism`, which prevents attach commands from working.

Do not change process permissions or restart the service just to bypass an attach error without approval. Collect available logs/metrics and use platform-supported diagnostic mechanisms.

### Command Not Supported

Run `jcmd <pid> help` and `jcmd <pid> help <command>`. Available commands depend on the JVM vendor, version, and enabled features.

### Unable to Write Dump/Recording File

Check the filesystem path as seen by the process or tool, write permissions, free disk space, and quotas. Place files on a dedicated volume with access controls.

### JFR Recording Missing Expected Events

Check settings, enabled events, thresholds, periods, and the recording time window. Run `jcmd <pid> JFR.check name=profile verbose=true` to inspect the actual configuration.

### NMT Has No Data

NMT must be enabled at JVM startup. Without the flag, `VM.native_memory` reports that tracking is not enabled; plan to enable it in an appropriate deployment after evaluating the overhead.

## 17. Protecting Diagnostic Data

The following artifacts can contain sensitive information:

- Heap dumps: objects, fields, tokens, passwords, requests/responses, caches, and business data.
- Thread dumps: thread names, stack traces, class/method names, and occasionally data embedded in names or messages.
- JFR: stack traces, classes, file paths, threads, system information, and custom event fields.
- JVM command line/system properties/environment: internal endpoints, users, tokens, or misconfigured credentials.
- GC/JVM logs: file paths, configurations, service names, and environment details.

Store artifacts in restricted-access directories, encrypt them at rest and in transit if policy requires, set deletion deadlines, track recipients, and avoid broad sharing. Before sending artifacts outside the organization, review and redact sensitive data according to policy.

## 18. Production Incident Runbook

1. Record the start time, symptoms, scope of impact, sample requests, and affected service instances.
2. Collect existing metrics/logs/traces; save a baseline of CPU, heap, GC, thread count, RSS, and latency.
3. Identify the exact JVM, PID, container, JDK version, and user.
4. Read `VM.version`, `VM.uptime`, `VM.flags`, and `GC.heap_info` if appropriate.
5. For hangs/latency, capture 2–3 thread dumps 5–10 seconds apart; inspect lock owners, blocked threads, and repeated stacks.
6. For CPU or latency, run a short default JFR recording with an explicit duration and filename.
7. Analyze the recording using `jfr summary`, `jfr print`, or JDK Mission Control.
8. Run a histogram or heap dump only when you have a specific memory question, after evaluating High Impact, pauses, disk space, and access controls.
9. If native memory is suspected, check whether NMT is enabled and combine with OS metrics.
10. Record commands, outputs, timestamps, durations, operators, and any changes applied.
11. Verify application health after diagnostics: latency, error rate, CPU, memory, GC, and thread count.
12. Close recordings/debug sessions, restore logging if modified, and enforce retention policies on artifacts.

## 19. Complete Java 17 Example for Practicing Thread Dumps and JFR

Create `src/demo/SafeDebugTarget.java`:

~~~java
package demo;

import java.util.ArrayList;
import java.util.List;

/** Generates controlled allocation and monitor contention for diagnostics. */
public final class SafeDebugTarget {
    private static final Object LOCK = new Object();
    private static final List<byte[]> RETAINED = new ArrayList<>();
    private static volatile long sink;

    private static void work() {
        while (!Thread.currentThread().isInterrupted()) {
            byte[] bytes = new byte[1024];
            sink += bytes.length;

            synchronized (LOCK) {
                try {
                    Thread.sleep(20);
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                    return;
                }
            }
        }
    }

    public static void main(String[] args) throws InterruptedException {
        for (int i = 0; i < 8; i++) {
            RETAINED.add(new byte[256 * 1024]);
        }

        for (int i = 0; i < 2; i++) {
            new Thread(SafeDebugTarget::work, "safe-worker-" + i).start();
        }

        System.out.println("READY retainedKiB=" + RETAINED.size() * 256);
        Thread.sleep(120_000);
    }
}
~~~

Compile:

~~~bash
javac --release 17 -d out src/demo/SafeDebugTarget.java
~~~

Run in Terminal 1:

~~~bash
java -Xms32m -Xmx128m -cp out demo.SafeDebugTarget
~~~

Exact stdout:

~~~text
READY retainedKiB=2048
~~~

In Terminal 2, find the PID and capture a thread dump:

~~~bash
jcmd -l
jcmd <pid> Thread.print -l
~~~

Save a JSON thread dump:

~~~bash
jcmd <pid> Thread.dump_to_file -format=json threads.json
~~~

Start a 5-second JFR recording:

~~~bash
jcmd <pid> JFR.start name=practice settings=default duration=5s filename=practice.jfr
~~~

After the recording completes:

~~~bash
jfr summary practice.jfr
jfr print --events jdk.JavaMonitorEnter practice.jfr
~~~

In a test run on Azul JDK 24.0.2, the thread dump showed one worker in the `BLOCKED` state waiting on the monitor held by the other worker. The 5-second recording captured 37 `jdk.JavaMonitorEnter` events during the test run. Event counts can vary with scheduling, CPU, and run duration; the goal is to practice correlating thread dumps with JFR events.

When finished, stop the program with Ctrl+C in Terminal 1.

## 20. Pre-Production Diagnostics Checklist

- [ ] Confirm the exact JVM, PID, container, and JDK version.
- [ ] Run `jcmd <pid> help` to verify commands on the target JVM.
- [ ] Check the command's Impact before running it.
- [ ] Collect metrics/logs/traces and a baseline before attaching.
- [ ] Start with `VM.version`, `VM.uptime`, `VM.flags`, or `GC.heap_info` when appropriate.
- [ ] Use repeated thread dumps to analyze hangs, blocks, and deadlocks.
- [ ] Prefer JFR `default` and a bounded duration for initial profiling.
- [ ] Use `profile` or custom events only with a clear hypothesis and collection window.
- [ ] Avoid histograms and heap dumps until High Impact, full GC, pauses, and disk space are evaluated.
- [ ] Use NMT only if enabled at startup and the 5–10% overhead is acceptable.
- [ ] Do not enable global debug logging or expose JDWP to public networks.
- [ ] Protect thread dumps, JFR files, heap dumps, and JVM metadata as sensitive data.
- [ ] Record timestamps, commands, results, and the operator.
- [ ] Recheck application health after completing diagnostics.

## 21. References

- [Oracle JDK 24 — Diagnostic Tools](https://docs.oracle.com/en/java/javase/24/troubleshoot/diagnostic-tools.html): classification of monitoring tools, JFR, jcmd, thread dumps, heap histograms, heap dumps, and Native Memory Tracking.
- [Oracle JDK 24 — The jcmd Command](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jcmd.html): syntax, Impact levels, and options for diagnostic commands.
- [Oracle JDK 24 — Troubleshooting Guide](https://docs.oracle.com/en/java/javase/24/troubleshoot/troubleshooting-guide.pdf): how to collect thread dumps, heap dumps, JVM information, and diagnose hung processes.
- [Oracle JDK 24 — Submit a Bug Report](https://docs.oracle.com/en/java/javase/24/troubleshoot/submit-bug-report.html): collecting thread stacks and core dumps when deep investigation is required.
- [Oracle JDK 24 — JFR Configurations](https://docs.oracle.com/en/java/javase/24/jfapi/flight-recorder-configurations.html): choosing Flight Recorder configurations and trade-offs between default and profile.

Safe production debugging is about gathering evidence at escalating levels of impact. Start with metrics, thread dumps, and lightweight JFR configurations; move to histograms, heap dumps, or native-memory tracking only when you have a specific goal, have evaluated the cost, and have a plan to protect the collected data.
