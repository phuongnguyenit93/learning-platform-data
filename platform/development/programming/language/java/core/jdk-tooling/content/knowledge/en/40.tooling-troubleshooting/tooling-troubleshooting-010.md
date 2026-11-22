# Java Troubleshooting Workflow

Troubleshooting is the process of gathering evidence to determine whether an issue lies in the application, JVM, JDK, dependencies, or operating system. A good workflow starts with a verifiable symptom, records the initial state, selects a tool suited to the hypothesis, and verifies the result after each change.

In Java Core JDK Tooling, the most commonly used tools are jcmd, Java Flight Recorder (JFR), jfr, jstat, jdeps, jar, javap, and operating system tools. jcmd sends diagnostic commands directly to a running JVM; JFR records runtime events for later analysis; the remaining tools help inspect GC, modules, bytecode, archives, and process state.

The goal is not to run every tool. Choose a measurement small enough to test a single hypothesis, preserve the evidence, and avoid altering the failure state before understanding it.

## 1. General Troubleshooting Workflow

~~~text
Record the symptom and timestamp
              |
              v
Identify the application, PID, and environment
              |
              v
Collect a low-overhead baseline
              |
              v
Classify: startup / CPU / hang / heap / GC / native / crash
              |
              v
Select tools and gather evidence
              |
              v
Correlate logs, metrics, threads, and recordings
              |
              v
Formulate a testable hypothesis
              |
              v
Change one factor and re-measure
              |
              v
Confirm root cause, save results, and monitor
~~~

Follow these steps:

1. Record what users or the system observed.
2. Identify the start time, frequency, and scope of impact.
3. Record the Java version, JVM, OS, container, configuration, and running commit.
4. Save relevant logs, exit codes, thread dumps, or recordings.
5. Classify the symptom and start with low-overhead tools.
6. Compare the results against a normal state or a known good run.
7. State the hypothesis and the evidence supporting or refuting it.
8. Change one factor and re-run the same measurement.
9. Confirm the issue is resolved and monitor for recurrence.

A good hypothesis can be disproven with data. For example, “requests are slow because threads are waiting for database connections” can be tested using thread dumps, JFR socket events, pool metrics, and query durations.

## 2. Recording Symptoms Before Running Tools

Do not just write “the application is slow” or “Java errored out.” Describe the event with concrete details:

| Information | Questions to answer |
|---|---|
| Timestamp | When did the error start? In which time zone? |
| Scope | The entire service, one instance, one endpoint, or one task? |
| Frequency | Continuous, load-dependent, scheduled, or random? |
| Behavior | Crash, timeout, hang, high CPU, OOM, or incorrect result? |
| Impact | Failed requests, increased latency, restarts, data loss, or alerts only? |
| Load | Requests/second, connection count, queue depth, and concurrency when it occurred? |
| Recent changes | Release, config, JDK, dependencies, traffic, database, or infrastructure? |
| Evidence | Stack traces, logs, metrics, PID, exit code, dumps, and recordings? |

Capture a window before, during, and after the incident if possible. Synchronize timestamps across application logs, the JVM, containers, and the operating system. If machines have clock skew, correlating events can lead to wrong conclusions.

Distinguish between when an error first occurred and when it was first detected. For example, the heap may grow steadily for hours before an OOM; the OOM log is merely the point at which the symptom becomes obvious.

## 3. Identifying the Right Java Runtime and Running Process

A machine may have multiple JDKs installed. The `java` command in the terminal is not necessarily the service's runtime. Check the executable and environment of the actual process.

### Checking the JDK in the Terminal

Linux/macOS:

~~~bash
java -version
javac -version
command -v java
echo "$JAVA_HOME"
~~~

Windows PowerShell:

~~~powershell
java -version
javac -version
Get-Command java -All
$env:JAVA_HOME
$env:PATH -split ';'
~~~

Also check the JDK vendor and full version, OS, kernel, CPU architecture, JAVA_HOME, PATH, working directory, Maven/Gradle Wrapper version, and runtime flags.

The following commands display the VM settings and system properties of the runtime invoked from the terminal:

~~~bash
java -XshowSettings:properties -version
java -XshowSettings:vm -version
~~~

These two commands do not read the configuration of a running service process. Use jcmd to retrieve information from the target JVM.

### Finding the PID

~~~bash
jcmd -l
~~~

This command lists the JVMs visible to the tool. You can also run:

~~~bash
jcmd
~~~

On Linux, OS tools can also help locate processes:

~~~bash
ps -ef | grep '[j]ava'
top -p <pid>
~~~

On Windows PowerShell:

~~~powershell
Get-Process java, javaw -ErrorAction SilentlyContinue
Get-CimInstance Win32_Process -Filter "Name='java.exe' OR Name='javaw.exe'" | Select-Object ProcessId, ExecutablePath, CommandLine
~~~

In Docker, `jcmd -l` may not list a JVM running in a separate Docker process. Obtain the PID from inside the container and run the diagnostic tool in the same environment. jcmd must run on the same host as the JVM and under the same effective user/group that started the JVM.

## 4. Collecting a Baseline with jcmd

jcmd is a useful starting point for many JVM issues. First, ask the JVM itself which commands it supports:

~~~bash
jcmd <pid> help
~~~

Get the JVM version:

~~~bash
jcmd <pid> VM.version
~~~

Get the launch command line, flags, system properties, and uptime:

~~~bash
jcmd <pid> VM.command_line
jcmd <pid> VM.flags
jcmd <pid> VM.system_properties
jcmd <pid> VM.uptime
~~~

Get the heap status:

~~~bash
jcmd <pid> GC.heap_info
~~~

This information helps spot differences between a failing environment and a healthy one—such as a different JDK, different Xmx, different collector, missing system property, or the service loading the wrong configuration file.

Do not share raw `VM.system_properties` or command-line output if it may contain passwords, tokens, internal URLs, credentials, or sensitive data. Store the original in an access-controlled location and create a redacted copy before sharing.

### Attach Requirements

jcmd must run on the same machine and under the same effective user/group as the JVM. If attach is refused:

- Verify that the PID belongs to the right process and the process is still running.
- Run jcmd as the user that started the service.
- Check that the JDK tool is compatible with the target JVM.
- Check the container PID namespace and mount/runtime environment.
- Confirm the JVM has not disabled the attach mechanism via startup flags.
- Inspect the actual error message before concluding the cause.

Do not assume the application is broken just because jcmd cannot attach. When attach is not possible, use logs, configured JMX, existing JFR recordings, or appropriate OS tools.

## 5. Choosing Tools by Symptom

| Symptom | Evidence to collect first | Suitable tools |
|---|---|---|
| Fails to start | stderr, exit code, Java version, command line | java, jar, jdeps, javap |
| High CPU | Per-process/thread CPU, sample stacks, recording | top/Task Manager, jcmd, JFR, JMC |
| Hang or timeout | Multiple thread dumps, lock owners, I/O wait | jcmd Thread.print, JFR |
| Deadlock | Thread dump with lock cycle | jcmd Thread.print -l |
| Growing heap/OOM | Heap info, histogram, heap dump, GC log | jcmd GC.*, jstat, JFR |
| Long GC pauses | GC log, pause events, allocation rate | -Xlog:gc*, jstat, JFR |
| High RSS but low heap | Native memory, thread count, native libraries | NMT, OS tools, JFR |
| JVM crash | hs_err log, core dump, OS/kernel logs | Fatal Error Log, jhsdb, debugger |
| Class/module errors | Classpath, module graph, manifest, class version | jar, jdeps, javap, java |
| TLS/network | Exception, certificate chain, socket timing | keytool, JFR, OS/network tools |

Start with low-overhead data. Increase the level of detail when initial results are insufficient to distinguish between hypotheses.

## 6. High CPU and Slow Application Response

High CPU can be caused by tight computation loops, excessive retries, serialization, regex, lock contention, logging, or increased request volume. Low CPU with slow requests often points to I/O wait time, connection pools, locks, or downstream services.

### Observing Processes and Threads

Linux:

~~~bash
top -H -p <pid>
~~~

Windows: use Task Manager or Performance Monitor to track process and thread CPU usage. Compare against request rate, queue depth, thread pool usage, and host/container CPU.

Take a thread dump:

~~~bash
jcmd <pid> Thread.print
~~~

Get extended thread information and locks:

~~~bash
jcmd <pid> Thread.print -e -l
~~~

Compare multiple thread dumps spaced about 5–10 seconds apart. A single stack trace is only a point-in-time snapshot. If the same thread is repeatedly in the same computation path with high CPU, that points to hot code. If threads are repeatedly in WAITING or BLOCKED state, check lock owners, queues, sockets, and downstream dependencies.

On Linux, you can match the native thread ID in a thread dump with the TID from `top -H`. Thread dumps display `nid` in hexadecimal; convert the TID properly before comparing.

Do not conclude that every WAITING thread is a bug. Idle thread pool workers waiting for tasks, schedulers, and many background threads are normally in a waiting state.

### Using JFR to Find Bottlenecks

Start a short recording on a running JVM:

~~~bash
jcmd <pid> JFR.start name=incident settings=profile duration=2m filename=incident.jfr
~~~

`profile` collects more data than `default` and is suited for short recordings when deeper investigation is needed. For continuous recordings or overhead-sensitive environments, consider `settings=default`.

After the recording completes:

~~~bash
jfr summary incident.jfr
jfr view all-views incident.jfr
~~~

You can filter specific events to inspect:

~~~bash
jfr print --events jdk.ExecutionSample,jdk.CPULoad,jdk.JavaMonitorWait,jdk.ThreadPark,jdk.SocketRead,jdk.FileRead incident.jfr
~~~

Use JDK Mission Control (JMC) to inspect flame graphs, threads, locks, GC, and I/O along a timeline. Monitor wait/park events help locate synchronization waits; socket/file events help uncover I/O wait time; execution samples identify code consuming CPU.

JFR only records events that are enabled and meet the thresholds of the recording settings. The absence of an event in the file does not prove that the event did not occur.

## 7. Hangs, Timeouts, and Deadlocks

When an application hangs, first determine whether the process is still alive or stopped, whether CPU is elevated, and whether the issue affects a single request or the entire process.

Take at least three thread dumps a few seconds apart:

~~~bash
jcmd <pid> Thread.print -l > thread-1.txt
jcmd <pid> Thread.print -l > thread-2.txt
jcmd <pid> Thread.print -l > thread-3.txt
~~~

In PowerShell, you can redirect output using:

~~~powershell
jcmd <pid> Thread.print -l | Out-File -Encoding utf8 thread-1.txt
jcmd <pid> Thread.print -l | Out-File -Encoding utf8 thread-2.txt
jcmd <pid> Thread.print -l | Out-File -Encoding utf8 thread-3.txt
~~~

Read the dumps systematically:

1. Look for deadlock notices if the JVM detected any.
2. Find BLOCKED threads and the monitor/lock they are waiting on.
3. Identify the thread holding the lock and inspect its stack trace.
4. Compare the same thread across dumps to see whether its state changes.
5. Check threads waiting on sockets, files, databases, or queues.
6. Correlate with request IDs, application logs, and timeout timestamps.

Deadlocks typically form a cycle: thread A holds lock X and waits for Y, while thread B holds Y and waits for X. A single BLOCKED thread may simply be waiting for a lock normally.

The JDK can also generate a thread dump via the Control+Break mechanism. On Windows, press Control+Break in the process console; on Linux, send SIGQUIT with `kill -QUIT PID`. This may write the dump to JVM stderr/logs, so you must know where those logs are collected.

`Thread.print` has overhead proportional to the number of threads. If a process has tens of thousands of threads, the dump can be large and take time. Use it at appropriate times and store the output where disk space is sufficient.

## 8. Heap, Memory Leaks, and OutOfMemoryError

Distinguish between types of memory issues:

- Java heap OOM: the heap lacks space for an allocation.
- Metaspace OOM: insufficient space for class metadata.
- Direct buffer OOM: direct buffer memory is exhausted.
- Native thread creation failure: the OS cannot allocate a thread/stack.
- Native memory OOM: the JVM or a native library cannot allocate memory.
- Process killed by OS/container: may not produce a Java `OutOfMemoryError` or heap dump.

### Heap Info and Class Histogram

Get the heap summary:

~~~bash
jcmd <pid> GC.heap_info
~~~

Get the class histogram:

~~~bash
jcmd <pid> GC.class_histogram
~~~

A histogram shows which classes have many instances or occupy the most heap. Take snapshots at different times to see whether object counts continue to grow after load drops.

`GC.class_histogram` has high impact depending on heap size and contents. Do not run it continuously as a cheap metric.

### Heap Dump

When you need to analyze object retention:

~~~bash
jcmd <pid> GC.heap_dump heap.hprof
~~~

Heap dumps can be large, time-consuming, and cause pauses; the default command may trigger a full GC. Check available disk space before running. Use MAT or a compatible heap analyzer to inspect the dominator tree, retained size, GC roots, and object paths.

Heap dumps often contain in-memory application data such as tokens, sessions, personal data, requests, and configuration. Restrict access, encrypt at rest/in transit, and apply a retention policy.

### Automatic Preparation for OOM

You can configure these at startup:

~~~bash
-XX:+HeapDumpOnOutOfMemoryError
-XX:HeapDumpPath=/var/log/myapp
-XX:ErrorFile=/var/log/myapp/hs_err_pid%p.log
~~~

`HeapDumpOnOutOfMemoryError` creates a heap dump when the JVM detects an `OutOfMemoryError`. `ErrorFile` specifies the location of the fatal error log for severe VM errors. Ensure the directory exists, is writable, and has enough free space.

A process killed by the cgroup OOM killer or the operating system may not have a chance to write a heap dump. In that case, check container events, kernel logs, exit codes, memory limits, and RSS.

## 9. GC and Pause Times

When GC is suspected, measure pauses and trends over time before changing the collector or heap size.

### GC Logs

Enable Unified Logging at startup:

~~~bash
-Xlog:gc*,safepoint:file=logs/gc-%p.log:time,uptime,level,tags:filecount=5,filesize=20M
~~~

Logs can show GC pause frequency and duration, heap before/after collection, allocation pressure, collector phases, and non-GC safepoint pauses. Keep log rotation enabled to prevent unbounded growth.

Do not conclude GC is the root cause from a single long pause; correlate request latency, CPU, allocation rate, and GC timestamps.

### Monitoring with jstat

~~~bash
jstat -gcutil <pid> 1000 10
~~~

This command takes 10 samples, 1 second apart. The columns show utilization of heap regions and GC counts/times according to the JVM. Exact column names and meanings depend on options and JDK version; consult the help output for your specific `jstat` version.

### Analyzing GC with JFR

You can filter GC phase pauses:

~~~bash
jfr print --events jdk.GCPhasePause incident.jfr
~~~

Correlate pause durations with latency. If heap occupancy increases after each cycle and does not return to a stable baseline, investigate object retention using histograms or heap dumps. If the heap is stable while process RSS grows, expand the investigation to native memory.

Do not call `System.gc()` or `jcmd GC.run` in production just to “see if the heap shrinks.” A full GC can alter the very phenomenon you are diagnosing and cause significant pauses.

## 10. Native Memory and High RSS

The heap is not all of the JVM's memory. A process also uses metaspace, code cache, thread stacks, GC structures, direct buffers, JNI/native libraries, and other native regions.

If RSS grows while heap usage stays relatively flat, check native memory, thread count, direct buffers, and native libraries.

### Native Memory Tracking (NMT)

NMT must be enabled at JVM startup:

~~~bash
-XX:NativeMemoryTracking=summary
~~~

You can choose `detail` for more granular allocation information:

~~~bash
-XX:NativeMemoryTracking=detail
~~~

NMT adds overhead and only tracks internal HotSpot JVM memory; it does not track all allocations from third-party native code. You cannot enable NMT on an already running JVM if it was not enabled at startup.

Get the summary:

~~~bash
jcmd <pid> VM.native_memory summary
~~~

Set a baseline after the application has warmed up:

~~~bash
jcmd <pid> VM.native_memory baseline
~~~

After some time:

~~~bash
jcmd <pid> VM.native_memory summary.diff
jcmd <pid> VM.native_memory detail.diff
~~~

Compare `reserved` and `committed`. Reserved is the address space set aside in advance; committed is the memory actually backed/allocated for subsystem use. Steadily growing committed memory can be a clue to native memory growth, but it must be analyzed by category and actual load.

If NMT does not explain the RSS, check OS memory maps, the native allocator, JNI libraries, direct buffers, and container memory limits.

## 11. Startup, Classpath, and Module Errors

Errors occurring before the application serves requests are usually related to the Java executable, version, classpath, module path, manifest, configuration, or dependencies.

### Inspecting JARs and Manifests

~~~bash
jar --list --file application.jar
~~~

View the module descriptor:

~~~bash
jar --describe-module --file application.jar
~~~

Inspect bytecode and methods:

~~~bash
javap -classpath application.jar -verbose com.acme.Main
javap -classpath application.jar -c -p com.acme.Main
~~~

Check dependencies/modules:

~~~bash
jdeps --recursive --multi-release 17 application.jar
~~~

For modular applications, inspect module resolution:

~~~bash
java --show-module-resolution --module-path mods -m com.acme.app/com.acme.Main
~~~

### Common Errors

| Error | Common cause | Evidence to check |
|---|---|---|
| UnsupportedClassVersionError | Runtime is older than compiled bytecode | javap -verbose, java -version |
| ClassNotFoundException | Class missing from runtime classpath or classloader | command line, dependency tree, class load log |
| NoClassDefFoundError | Class was resolved previously but cannot be loaded or failed initialization | Root exception, dependencies, and classloader |
| NoSuchMethodError | Runtime loaded a different class version than compile time | Dependency tree, actual JAR, class origin |
| NoSuchFieldError | Binary-incompatible API | Dependency versions and bytecode |
| InaccessibleObjectException | Module encapsulation blocks reflection | Module path and opens/exports |
| ServiceConfigurationError | Missing service provider or invalid descriptor | META-INF/services, module provides/uses |
| UnsatisfiedLinkError | Native library missing, wrong architecture, or failed to load | OS, architecture, library path, and native dependencies |

To see where classes are loaded from, enable Unified Logging at startup:

~~~bash
java -Xlog:class+load=info -jar application.jar
~~~

The output can be very large. Enable it briefly and filter for the package/class under investigation.

### Comparing Build and Runtime

Check the compile-time vs. runtime JDK vendor/version, compiler `--release` and class file version, resolved dependency versions, actual classpath/module path, manifest `Class-Path`, module descriptor, multi-release JARs, and service providers.

Do not just look at a POM or `build.gradle` and assume the process is using the right dependencies. Inspect the actual deployed JAR file and its digest.

## 12. Configuration, TLS, and I/O Errors

When an application cannot connect to a database, API, or HTTPS endpoint, determine whether the failure occurs at DNS, TCP, TLS, authentication, protocol, or the application layer.

Check:

1. Are the hostname and port correct?
2. What address does DNS resolve to?
3. Is the TCP connection established?
4. Does the TLS handshake succeed?
5. Is the certificate chain trusted and not expired?
6. Are authentication and authorization correct?
7. Is the connection pool exhausted or holding connections too long?
8. Is the downstream service experiencing latency, timeouts, or rate limiting?

Use `keytool` to inspect keystores/truststores:

~~~bash
keytool -list -keystore truststore.p12 -storetype PKCS12
~~~

If TLS debugging is needed, you can enable it in a controlled run:

~~~bash
-Djavax.net.debug=ssl:handshake
~~~

TLS debug output can be very verbose and contain sensitive information. Enable it only for as long as needed, restrict log access, and turn it off once collection is complete.

JFR `SocketRead`/`SocketWrite` and `FileRead`/`FileWrite` events help identify I/O wait times. Correlate them with network metrics, database logs, and server-side traces to determine which side is introducing latency.

## 13. Crashes and Postmortem Diagnostics

When the JVM crashes, disappears, or exits abnormally, preserve:

- Fatal error log, typically named `hs_err_pid*.log`.
- Core dump or Windows crash dump, if generated.
- Application stdout/stderr and service manager logs.
- Exit code, signal, and timestamp when the process terminated.
- OS/kernel logs and container termination reason.
- JDK vendor/version, executable path, and native library list.
- Artifact digest, command line, and redacted environment variables.

The fatal error log is usually the first document to read after a severe VM error. It can contain the signal, problematic frame, thread, native stack, JVM flags, and system information.

You can configure the log location:

~~~bash
-XX:ErrorFile=/var/log/myapp/hs_err_pid%p.log
~~~

For core dumps, Serviceability Agent tools such as `jhsdb` can read information from the core file. The JDK binary used for analysis must be compatible with the binary that produced the core. Analyzing native crashes may require an OS debugger such as `gdb` or WinDbg.

Distinguish between a Java exception, a Java `OutOfMemoryError`, a fatal JVM error, and an OS kill. They have different log/dump mechanisms. A process terminated by SIGKILL or a container OOM kill usually cannot write a fatal error log.

## 14. Containers and the Operating System

A JVM running in a container may see different CPU/memory limits than the host. Collect both container limits and process metrics.

Linux/container:

~~~bash
cat /proc/<pid>/status
cat /proc/meminfo
ps -o pid,ppid,%cpu,%mem,rss,vsz,stat,etime,cmd -p <pid>
top -H -p <pid>
~~~

If running Docker, check `docker inspect`, memory limits, CPU quota, restart count, and `OOMKilled` state. In Kubernetes, correlate pod events, requests/limits, restart reasons, node pressure, and container logs.

On Windows, you can use `Get-Process`, `Get-CimInstance Win32_Process`, Performance Monitor, and Event Viewer. On macOS, use Activity Monitor, `vm_stat`, and appropriate system tools.

Do not look only at heap percentage. RSS includes native memory and can be affected by page cache, mapped files, and shared libraries. Compare heap, NMT, RSS, container limits, and OS metrics over the same time window.

## 15. Reproducing and Confirming the Root Cause

Once you have a hypothesis:

1. Create the smallest possible reproduction scenario.
2. Keep the JDK, flags, dependencies, and relevant inputs unchanged.
3. Record a baseline before making any change.
4. Change a single factor.
5. Run with the same load and duration.
6. Compare logs, latency, CPU, memory, and recordings.
7. Repeat to rule out random variation.
8. Add a regression test for the fixed bug.

If the bug only appears in production, build an environment close to production in JDK, container limits, traffic, dependencies, and configuration. Do not copy sensitive production data onto personal machines; use anonymized data or an appropriate synthetic dataset.

A root cause is only confirmed when evidence explains the symptom and a controlled change alters the outcome as predicted.

## 16. Java 17+ Example: Checking Basic Diagnostic MXBeans

The JDK provides the Java Management API for applications to read runtime information. The example below verifies that the main MXBeans are accessible. It demonstrates how a Java program can self-check its ability to read runtime metrics; a `PASS` result only confirms these APIs work, not that the entire application is healthy.

Structure:

~~~text
diagnostic-probe/
  src/
    DiagnosticProbe.java
  out/
~~~

File `src/DiagnosticProbe.java`:

~~~java
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryUsage;
import java.lang.management.RuntimeMXBean;
import java.lang.management.MemoryMXBean;
import java.lang.management.ThreadMXBean;

public final class DiagnosticProbe {

    private DiagnosticProbe() {
    }

    public static void main(String[] args) {
        RuntimeMXBean runtime = ManagementFactory.getRuntimeMXBean();
        MemoryMXBean memory = ManagementFactory.getMemoryMXBean();
        ThreadMXBean threads = ManagementFactory.getThreadMXBean();

        MemoryUsage heap = memory.getHeapMemoryUsage();

        if (runtime.getUptime() < 0
                || heap.getUsed() < 0
                || threads.getThreadCount() < 1) {
            throw new IllegalStateException("JVM diagnostic probe failed");
        }

        System.out.println("runtimeMXBean=OK");
        System.out.println("heapMXBean=OK");
        System.out.println("threadMXBean=OK");
        System.out.println("DIAGNOSTIC_RESULT=PASS");
    }
}
~~~

Compile from the project directory:

~~~bash
javac -d out src/DiagnosticProbe.java
~~~

Run:

~~~bash
java -cp out DiagnosticProbe
~~~

Exact stdout:

~~~text
runtimeMXBean=OK
heapMXBean=OK
threadMXBean=OK
DIAGNOSTIC_RESULT=PASS
~~~

You can extend the probe to print runtime uptime, heap used/max, thread count, loaded class count, and JVM input arguments. When logging these values, use clear metric names and units; avoid printing system properties or environment variables that contain secrets.

In real systems, MXBeans are well-suited for controlled metrics and health diagnostics. When you need stack traces, event timelines, or allocation/lock profiling, use jcmd/JFR as appropriate.

## 17. Common Troubleshooting Mistakes

| Mistake | Consequence | Better approach |
|---|---|---|
| Running every tool at once | Creates noise and extra overhead | Choose tools based on a hypothesis |
| Taking only one thread dump | Cannot tell if the state persists | Compare multiple snapshots |
| Confusing heap with RSS | Misses native memory or container limits | Correlate heap, NMT, RSS, and OS |
| Blaming GC from a single pause | Misguided tuning that hides the bottleneck | Pair GC logs with latency/JFR |
| Taking a heap dump without checking disk space | Exhausts disk or increases pauses | Check space and impact first |
| Running jcmd as a different user | Attach fails | Use the same effective user/group |
| Comparing logs across mismatched timezones | Corrupted timeline | Normalize timestamps and timezones |
| Checking only source build config | Misses actual binary/runtime | Inspect deployed command line, JAR, and digest |
| Increasing heap immediately on OOM | May cause the container to be killed sooner | Distinguish heap OOM from native/container OOM |
| Sharing dumps without access controls | Exposes in-memory data | Restrict permissions, encrypt, and redact data |

Do not change multiple JVM flags at once during an ongoing incident. Every change must have a reason, a hypothesis, and a confirming measurement.

## 18. Troubleshooting Report Template

| Field | What to record |
|---|---|
| Incident ID | Incident ID or ticket |
| Symptom | Symptom and verbatim error message |
| Timeline | Timestamps, timezone, and key milestones |
| Impact | Affected users/services/endpoints |
| Environment | JDK vendor/version, OS, container, CPU/RAM limits |
| Application | Version, commit SHA, and artifact digest |
| JVM config | Command line, flags, heap, collector, redacted system properties |
| Evidence | Logs, thread dumps, JFR, GC logs, heap/native dumps if any |
| Hypothesis | Suspected cause and supporting evidence |
| Experiment | Change tested, inputs, and run conditions |
| Result | Before/after metrics and reproduction results |
| Root cause | Cause confirmed by evidence |
| Fix | Change deployed |
| Regression | Tests and post-fix monitoring metrics |
| Follow-up | Action items and owners |

Do not put passwords, tokens, private keys, personal data, or raw heap dumps into public tickets.

## 19. Pre-Conclusion Troubleshooting Checklist

- [ ] Described the symptom with timestamp, scope, and impact.
- [ ] Identified the exact PID and Java executable of the process.
- [ ] Recorded JDK vendor/version, OS, architecture, and container limits.
- [ ] Saved the command line and JVM flags with secrets redacted.
- [ ] Saved logs and timestamps in a consistent timezone.
- [ ] Selected tools suited to the incident type.
- [ ] Assessed impact and disk space before generating dumps.
- [ ] Compared multiple snapshots or recordings where needed.
- [ ] Distinguished between heap, native memory, and OS/container memory.
- [ ] Checked dependencies and classpath/module path for startup errors.
- [ ] Verified the artifact digest and the actual deployed binary.
- [ ] Reproduced or confirmed the hypothesis with measurements.
- [ ] Checked for regressions and monitored after the change.
- [ ] Stored evidence with appropriate access controls and retention.

## 20. Key Takeaways

- Troubleshooting starts with a verifiable symptom and a baseline of the right process.
- Identify the exact JDK, PID, command line, flags, OS, and container limits.
- jcmd is the primary tool for querying a running JVM; check supported commands with `help`.
- Thread dumps should be compared over time to spot locks, deadlocks, and stuck threads.
- JFR/JMC helps locate CPU, synchronization, GC, and I/O bottlenecks along a timeline.
- Histograms and heap dumps help find object retention; they can cause pauses and require significant disk space.
- GC logs and jstat help inspect allocation, heap usage, and pause times.
- NMT must be enabled at startup and only tracks internal HotSpot memory.
- Heap, RSS, and container memory are different measurements.
- jar, jdeps, and javap help inspect archives, modules, and bytecode.
- Fatal error logs, core dumps, and OS logs are key evidence when the JVM crashes.
- Change one factor at a time and use the same measurement to confirm the result.
- Protect dumps and logs because they may contain sensitive data.

## Official References

- [Oracle JDK 26 — Diagnostic Tools](https://docs.oracle.com/en/java/javase/26/troubleshoot/diagnostic-tools.html)
- [Oracle JDK 26 — jcmd Command](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jcmd.html)
- [Oracle JDK 26 — jfr Command](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jfr.html)
- [Oracle JDK 26 — Troubleshoot Performance Issues Using Flight Recorder](https://docs.oracle.com/en/java/javase/26/troubleshoot/troubleshoot-performance-issues-using-jfr.html)
- [Oracle JDK 26 — Native Memory Tracking](https://docs.oracle.com/en/java/javase/26/troubleshoot/diagnostic-tools.html)
- [Java Management Extensions (JMX) Technology](https://docs.oracle.com/en/java/javase/26/management/monitoring-and-management-using-jmx-technology.html)
- [The jstat Command — JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jstat.html)
- [The jdeps Command — JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jdeps.html)
- [The jar Command — JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jar.html)
- [The javap Command — JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/javap.html)