# JVM Diagnostic Workflow in Java Core JDK Tooling

## 1. Purpose of JVM Diagnostics

JVM diagnostics is the process of collecting and analyzing evidence to determine why a Java application fails to start, runs slowly, consumes high CPU, grows in memory, hangs, or terminates abnormally.

A sound workflow must answer four questions:

1. Which JVM version is running, and with what startup flags and resource limits?
2. Is the symptom occurring in the Java heap, garbage collection, threads, class loading, native memory, I/O, or the operating system?
3. What evidence confirms the hypothesis and can be collected without worsening the incident?
4. After changing configuration or code, how do we verify that the root cause has been resolved?

Do not start by immediately increasing -Xmx, switching the garbage collector, or restarting the process. First, record the timestamp, PID, JDK version, JVM arguments, system load, and symptoms. Preserve logs, thread dumps, or recordings before restarting whenever possible.

## 2. Classifying Symptoms Before Choosing Tools

| Symptom | Area to Investigate First | Appropriate Evidence |
|---|---|---|
| JVM fails to start | Launcher, JDK, classpath, module path | java -version, command line, stderr, first exception |
| Application exits immediately | Application exception or configuration | Stack trace, application log, exit code |
| High CPU usage | Running threads, JIT, loops, lock contention | JFR, repeated thread dumps, OS thread monitor |
| Slow or hung requests | Thread pool, locks, network, disk, dependencies | Thread dumps, JFR, application traces |
| Continuously growing heap | Object retention, allocation rate, GC | GC log, histogram, heap dump, JFR |
| Long GC pauses | Heap pressure, allocation, collector behavior | GC log, JFR, heap usage after GC |
| Rising RSS/container memory | Heap, direct buffers, metaspace, thread stacks, JNI/native | NMT, JFR, OS/cgroup metrics |
| Growing Metaspace | Class loading or classloader leak | VM.metaspace, VM.classloader_stats, class load log |
| JVM crash or process killed | Native code, VM, OS, container limit | hs_err log, core dump, kernel/container events |
| Runtime class/method errors | Incompatible JDK/API or dependencies | Stack trace, java version, classpath, dependency tree |

A single symptom can have multiple causes. For example, high CPU can come from computation, garbage collection, spin loops, or contention. Looking at a single CPU graph is not enough to draw a conclusion.

## 3. General Diagnostic Workflow

~~~mermaid
flowchart TD
    A["Record symptoms and timestamp"] --> B["Identify PID, JDK, and JVM arguments"]
    B --> C["Collect low-impact data"]
    C --> D{"Primary symptom"}
    D -->|"Hung / slow"| E["Capture multiple thread dumps and JFR"]
    D -->|"Heap / GC"| F["GC log, heap info, histogram"]
    D -->|"Native memory"| G["NMT and OS / cgroup metrics"]
    D -->|"Crash / startup"| H["hs_err, core dump, stderr"]
    E --> I["Correlate timeline and hypotheses"]
    F --> I
    G --> I
    H --> I
    I --> J["Select targeted follow-up measurements"]
    J --> K["Fix root cause and verify after change"]
~~~

The typical order of priority is:

1. Identify the exact process and environment.
2. Collect version, command line, flags, uptime, and application logs.
3. Collect thread dumps or JFR if there is a performance issue.
4. Inspect heap and GC if memory pressure is suspected.
5. Use a histogram or heap dump when object retention analysis is needed.
6. Use NMT and OS tools when RSS far exceeds the heap.
7. Analyze hs_err/core dumps if the JVM crashes.
8. Compare data before and after the fix.

## 4. Preparing Evidence and Timestamps

Before running tools, record:

- Incident start and end times, preferably in UTC.
- PID of the Java process and application name.
- Host, container, pod, or service instance.
- JDK vendor, version, build number, and architecture.
- JVM command line, heap limits, collector, and flags.
- Application release, commit SHA, and active configuration.
- CPU, RAM, disk, network, and container memory limit.
- Relevant Request ID, correlation ID, or job ID.
- Recent changes: deploy, config, dependency, traffic, or infrastructure.

Record the timestamp of each dump to correlate with application logs, GC logs, and metrics. When comparing two environments, check the JDK build, JVM flags, container limits, traffic, and dependency versions.

Do not dump the entire environment into regular logs. JVM arguments, system properties, environment variables, and diagnostic files may contain tokens, passwords, connection strings, or personal data.

## 5. Identifying the Right Java Process

Use JDK tools from the JDK bin directory. On Windows, executable names have the `.exe` extension; on Linux/macOS, invoke the command name directly.

List JVMs observable by the JDK:

~~~bash
jcmd -l
~~~

You can also use:

~~~bash
jps -lv
~~~

`jcmd -l` displays the PID, main class/module, and arguments of the JVMs recognized by the tool. In containerized environments, processes may reside in separate PID namespaces; `jcmd -l` from the host will not necessarily list processes inside an isolated Docker container. In that case, run the tool inside the appropriate container or namespace and use `ps` to identify the PID.

On Linux:

~~~bash
ps -eo pid,ppid,user,stat,%cpu,%mem,rss,etime,args | grep '[j]ava'
~~~

On Windows PowerShell:

~~~powershell
Get-CimInstance Win32_Process -Filter "Name = 'java.exe' OR Name = 'javaw.exe'" |
    Select-Object ProcessId, ParentProcessId, ExecutablePath, CommandLine
~~~

Do not confuse the Java process PID with native thread IDs in a thread dump. The PID is used to invoke `jcmd`; the thread ID helps correlate Java threads with OS threads.

## 6. Requirements to Attach with jcmd

`jcmd` sends diagnostic commands to a running JVM. According to JDK 17 documentation, the tool must run on the same machine and under the same effective user/group ID that started the JVM.

If attaching fails, check:

- Whether the PID is correct and the process is still running.
- Whether the tool is running under the correct user.
- Whether the tool is in the same host/container/PID namespace.
- Whether the JDK is compatible with the target JVM.
- Whether the JVM disabled the attach mechanism via `DisableAttachMechanism`.
- Whether security policies, endpoint protection, or OS permissions are blocking attach.
- Whether the process is deeply hung inside the VM or native code.

Use `help` to see the commands actually supported on that JVM:

~~~bash
jcmd 12345 help
jcmd 12345 help Thread.print
jcmd 12345 help GC.heap_dump
~~~

Available diagnostic commands may vary across JVM implementations and JDK releases. Do not assume every command exists on every runtime.

## 7. Gathering JVM Baseline Information

Start with low-impact commands:

~~~bash
jcmd 12345 VM.version
jcmd 12345 VM.command_line
jcmd 12345 VM.flags
jcmd 12345 VM.uptime
jcmd 12345 VM.info
~~~

Meaning:

| Command | Information |
|---|---|
| VM.version | HotSpot and JDK build version |
| VM.command_line | JVM arguments, main class, and classpath |
| VM.flags | Effective flags, including default values |
| VM.uptime | How long the JVM has been running |
| VM.info | General VM overview information |
| VM.system_properties | Process system properties |

`VM.system_properties` may contain sensitive data or internal endpoints. Only collect it when necessary and redact it before sharing.

Additionally, record the version from the launcher:

~~~bash
java -version
javac -version
~~~

`java -version` shows the runtime invoked from the current PATH. `jcmd PID VM.version` shows the JVM of the target process. These two values may differ if multiple JDKs are installed on the machine.

## 8. Reading JVM Flags and Heap Limits

The `VM.flags` command displays the flags currently in effect for the JVM:

~~~bash
jcmd 12345 VM.flags
~~~

Common flags to watch:

- `InitialHeapSize` and `MaxHeapSize`.
- `UseG1GC`, `UseZGC`, or whichever collector is enabled.
- `MaxMetaspaceSize` and `MetaspaceSize`.
- `ThreadStackSize`.
- `NativeMemoryTracking`.
- `HeapDumpOnOutOfMemoryError` and `HeapDumpPath`.
- `StartFlightRecording`.
- Flags related to containers and CPU ergonomics.

`-Xms` is the initial heap size, and `-Xmx` is the maximum heap limit. `-Xmx` is not the total RAM limit of the process. The JVM also uses metaspace, code cache, thread stacks, direct buffers, GC structures, native libraries, and other native regions.

Do not increase `-Xmx` just because process RSS is rising. First identify which memory region is growing.

## 9. Collecting Thread Dumps

A thread dump shows where Java threads are, whether they are running, waiting on a monitor, waiting on a condition, or blocked.

Recommended command:

~~~bash
jcmd 12345 Thread.print -l
~~~

Depending on the JVM, you can request extended information:

~~~bash
jcmd 12345 Thread.print -e
~~~

`Thread.print -l` includes information about `java.util.concurrent` locks. This diagnostic command has medium impact, depending on the number of threads.

To save the output:

~~~bash
jcmd 12345 Thread.print -l > thread-1.txt
~~~

Do not take only a single thread dump if the application is hung. Capture about three snapshots spaced 5 to 10 seconds apart:

~~~bash
jcmd 12345 Thread.print -l > thread-1.txt
sleep 5
jcmd 12345 Thread.print -l > thread-2.txt
sleep 5
jcmd 12345 Thread.print -l > thread-3.txt
~~~

Compare the stack trace of the same thread across multiple snapshots:

- A stack that remains unchanged for a long time may indicate the thread is waiting or stuck.
- A stack that changes continuously indicates the thread is making progress.
- `RUNNABLE` repeatedly in the same code section may indicate a high-CPU loop.
- `BLOCKED` is usually related to waiting on a monitor.
- `WAITING` or `TIMED_WAITING` may mean waiting on a condition, queue, sleep, or I/O.
- Many threads waiting on the same lock may indicate lock contention.

`RUNNABLE` does not necessarily mean the thread is actively using CPU. Correlate with native thread IDs, OS thread metrics, and JFR.

## 10. Detecting Deadlocks and Lock Contention

HotSpot thread dumps can detect certain deadlocks based on monitors and JVM-supported synchronizers.

~~~bash
jcmd 12345 Thread.print -l
~~~

Look for the deadlock report section and inspect:

- Which thread holds the lock.
- Which thread is waiting for the lock.
- The dependency chain between threads.
- Stack traces at the lock acquisition points.
- Whether the lock is held while performing network, disk, or callback calls.

Java deadlocks typically form a wait cycle: Thread A holds lock 1 and waits for lock 2, while Thread B holds lock 2 and waits for lock 1.

If there is no deadlock but many threads are `BLOCKED`, the system may be experiencing contention. Use JFR to inspect monitor wait times and locate the bottleneck critical section.

## 11. Diagnosing High CPU

High CPU can be caused by:

- A thread executing an excessive loop or heavy computation.
- Many concurrent requests increasing allocation and GC.
- Lock contention causing threads to stay active with little progress.
- JIT compiler or class loading spikes during startup.
- Heavy serialization, regex, parsing, or data processing.
- Native methods or JNI libraries consuming CPU.

Workflow:

1. Record process CPU and per-OS-thread CPU.
2. Capture several thread dumps spaced a few seconds apart.
3. Compare `RUNNABLE` threads and recurring stack traces.
4. Collect a JFR profile during a period exhibiting the symptom.
5. Correlate Execution Sample, Thread CPU Load, GC, and monitor events.
6. Identify the method or subsystem consuming the time.
7. Fix the code or configuration and re-measure under the same workload.

On Linux, you can use:

~~~bash
top -H -p 12345
ps -L -p 12345 -o pid,tid,psr,pcpu,stat,comm
~~~

Do not conclude from a single snapshot. A thread may be `RUNNABLE` at the moment of the dump while only using CPU briefly.

## 12. Inspecting the Current Heap

Get an overview:

~~~bash
jcmd 12345 GC.heap_info
~~~

This command shows heap type, total capacity, used space, young/survivor regions, and metaspace. It is a point-in-time snapshot and cannot replace trend monitoring.

To view object statistics by class:

~~~bash
jcmd 12345 GC.class_histogram
~~~

The histogram lists instance counts and total bytes per class, sorted with the largest byte counts at the top. On HotSpot, byte arrays typically appear as `[B`.

`GC.class_histogram` has high impact and its cost depends on heap size and object count. Avoid running it continuously in production unless necessary.

A large histogram alone does not prove a memory leak. You need to determine which objects are still reachable, what holds references to them, and how much retained heap they account for.

## 13. Taking a Heap Dump to Find Object Retention

A heap dump is an object graph snapshot of the Java heap in HPROF format. It helps analyze:

- Which objects occupy the most retained heap.
- Which collections or caches are growing abnormally.
- Which reference chains keep objects alive.
- Which static fields or `ThreadLocal` variables hold unexpected objects.
- Which classloaders remain alive after the application reloads a module.

Using `jcmd`:

~~~bash
jcmd 12345 GC.heap_dump heap.hprof
~~~

`GC.heap_dump` has high impact, depending on heap size and contents. According to JDK 17 help, the command requests a Full GC unless the `-all` option is used. The filename syntax is a positional argument after the command; the example above is verified on JDK 17.

Heap dumps can be very large. Before creating one, check disk space, write permissions, output location, and whether the pause duration is acceptable.

Open the HPROF file with Eclipse Memory Analyzer (MAT) or a compatible tool. Start with:

- Histogram: which classes have many instances/bytes.
- Dominator Tree: which objects retain the most memory.
- Retained Heap: the amount of memory that would be freed if an object were removed.
- Path to GC Roots: the reference chain keeping an object alive.
- Leak Suspects: clusters of objects worth investigating.

Do not look only at Shallow Heap. A small object can retain a very large object graph.

## 14. Automatic Heap Dump on OutOfMemoryError

You can configure the JVM to generate a heap dump when an `OutOfMemoryError` occurs:

~~~bash
java \
  -XX:+HeapDumpOnOutOfMemoryError \
  -XX:HeapDumpPath=./diagnostics \
  -jar app.jar
~~~

Create the `diagnostics` directory before launching and ensure the process has write permissions. If no path is specified, the default file may be created in the process working directory.

Heap dumps can be nearly as large as the heap and contain sensitive data. Enforce quotas, retention, access control, and cleanup procedures. Do not let multiple heap dumps accumulate and fill up the disk.

Automatic heap dumps preserve evidence at the time of OOM. They do not explain the cause by themselves; you still need to classify the OOM message and analyze retained objects.

## 15. Reading Garbage Collection Logs

JDK 9+ uses Unified Logging. With JDK 17, you can enable GC logging:

~~~bash
java \
  -Xlog:gc*,gc+phases=debug:file=gc.log:time,uptime,level,tags:filecount=5,filesize=20M \
  -jar app.jar
~~~

The configuration above writes GC events and phase details to `gc.log` with timestamps, uptime, level, tags, and log rotation.

A more concise configuration:

~~~bash
-Xlog:gc*:file=gc.log:time,uptime,level,tags
~~~

In GC logs, monitor:

- Frequency of Young GC and Full GC.
- Pause duration and time between GCs.
- Heap before and after GC.
- GC cause.
- Old generation after Full GC.
- Metaspace usage.
- Allocation pressure and humongous allocations.
- Safepoint duration when the application is paused.

If Full GCs happen repeatedly while heap after GC barely drops, the live set may be too large or objects are being retained. If the heap drops well but GCs occur too frequently, the allocation rate may be high or the heap may be too small.

Do not switch collectors solely based on GC count. Correlate GC pauses with latency, throughput, allocation, and workload.

## 16. Understanding OutOfMemoryError by Resource Type

`OutOfMemoryError` is not always a Java heap leak.

| Message | Common Meaning | Evidence to Collect |
|---|---|---|
| Java heap space | Cannot allocate object in Java heap | GC log, histogram, heap dump, Xmx |
| GC overhead limit exceeded | GC runs most of the time but reclaims very little heap | GC log, live set, heap dump |
| Metaspace | Insufficient native memory for class metadata | VM.metaspace, classloader stats, class load/unload |
| Compressed class space | Exhausted metadata region for compressed class pointers | VM.flags, metaspace, and class loading |
| Direct buffer memory | Cannot allocate direct buffer | Direct buffer metrics, NMT, and library usage |
| unable to create native thread | Cannot create more OS threads | Thread count, OS limits, native memory, stack size |
| Requested array size exceeds VM limit | Requested array exceeds VM limit | Allocation size and array creation code |
| Native allocation failure | Native memory or OS resources exhausted | NMT, OS memory, swap, JNI/native library |

For `Java heap space`, the issue may be a heap too small for the workload, an allocation spike, or a memory leak. Do not increase `Xmx` before checking the live set after GC.

`GC overhead limit exceeded` usually indicates the JVM spends most of its time in GC while reclaiming very little memory. By HotSpot rules, this may be reported when GC takes roughly 98% of the time, reclaims less than 2% of the heap, and repeats across consecutive GC cycles. This is a signal to analyze the heap and allocations, not simply disable the warning.

## 17. Distinguishing Heap Leaks from Native Memory Growth

A Java process uses multiple types of memory:

- Java heap for objects.
- Metaspace for class metadata.
- Compressed class space for class metadata in a dedicated region.
- Code cache for JIT-compiled code.
- Thread stacks for each thread.
- Direct buffers and native allocations.
- GC, compiler, symbol table, and VM structures.
- JNI/native libraries and other memory mappings.

If RSS/container memory grows while heap usage does not increase proportionally, check direct buffers, thread stacks, metaspace, JNI/native libraries, memory mappings, and other processes.

Do not subtract `Xmx` from RSS and conclude that the difference is a native leak. `Xmx` is the heap limit, not the committed heap or total process memory.

## 18. Native Memory Tracking (NMT)

NMT tracks internal allocations of the HotSpot JVM. It must be enabled at JVM startup:

~~~bash
java -XX:NativeMemoryTracking=summary -jar app.jar
~~~

For more detailed allocation stacks:

~~~bash
java -XX:NativeMemoryTracking=detail -jar app.jar
~~~

`detail` provides more information but incurs higher overhead. According to Oracle JDK 17 documentation, NMT can reduce JVM performance by about 5–10% and uses additional memory itself for tracking. Only enable detail mode when needed.

Retrieve statistics:

~~~bash
jcmd 12345 VM.native_memory summary
~~~

Set a baseline after the application has warmed up:

~~~bash
jcmd 12345 VM.native_memory baseline
~~~

Get the diff after a period under load:

~~~bash
jcmd 12345 VM.native_memory summary.diff
jcmd 12345 VM.native_memory detail.diff
~~~

Common categories include Java Heap, Class, Thread, Code, GC, Compiler, Internal, Symbol, and Native Memory Tracking.

NMT only tracks internal JVM allocations. It does not cover all allocations made by native code outside the JVM or JNI libraries. If a native leak outside the JVM is suspected, use OS tools such as `pmap` on Linux or PerfMon on Windows and compare over time.

## 19. Reading Reserved and Committed in NMT

NMT typically displays two numbers:

- **Reserved:** virtual address space the JVM has reserved.
- **Committed:** memory that has been committed so the JVM can use it.

A large reserved value does not automatically mean the process is consuming that amount of RAM. On 64-bit systems, the JVM may reserve a large heap region while committing only a portion of it.

When investigating memory pressure, focus on committed trends, OS resident memory, container limits, and individual categories. Compare at matching timestamps rather than comparing two snapshots taken under different loads.

For example, if Thread committed grows alongside thread count, inspect thread pools or thread leaks. If Class/Metaspace grows alongside loaded class count, inspect classloader lifecycles. If Internal or Other grows while the heap stays stable, continue with native tools and JFR.

## 20. Diagnosing Metaspace and Classloaders

Metaspace growth can be caused by:

- The application generating many dynamic classes.
- Framework proxies or bytecode generation continuously creating classes.
- Plugin/module reloads where old classloaders remain referenced.
- `ThreadLocal`, static registries, or callbacks retaining classloaders.
- Class unloading not occurring as expected.

Useful commands:

~~~bash
jcmd 12345 VM.metaspace
jcmd 12345 VM.classloader_stats
jcmd 12345 VM.classloaders
~~~

Enable class loading/unloading logs when needed:

~~~bash
-Xlog:class+load=info,class+unload=info
~~~

Track loaded/unloaded class counts and Metaspace across multiple deployment cycles. If class and classloader counts keep rising after each reload, inspect references to old classloaders.

Increasing `MaxMetaspaceSize` can delay an OOM but does not fix a classloader leak.

## 21. Java Flight Recorder (JFR)

JFR collects events about the JVM and application such as CPU load, thread activity, allocations, GC, class loading, lock contention, file I/O, and socket I/O.

You can start a recording at JVM startup:

~~~bash
java \
  -XX:StartFlightRecording=filename=recording.jfr,duration=2m,settings=profile \
  -jar app.jar
~~~

Or start one on a running process:

~~~bash
jcmd 12345 JFR.start name=incident settings=profile duration=2m filename=incident.jfr
~~~

Check active recordings:

~~~bash
jcmd 12345 JFR.check
~~~

Dump data from a running recording:

~~~bash
jcmd 12345 JFR.dump name=incident filename=incident-partial.jfr
~~~

Stop a recording:

~~~bash
jcmd 12345 JFR.stop name=incident
~~~

Analyze the file:

~~~bash
jfr summary incident.jfr
jfr print --events jdk.GarbageCollection incident.jfr
~~~

You can open JFR files with JDK Mission Control (JMC) to inspect timelines, CPU, threads, allocations, GC, locks, and I/O.

Recording with the `profile` configuration for a fixed duration generally has low overhead, though actual overhead depends on workload and event settings. According to Oracle documentation, standard profile recordings with default settings are typically under 2% for most applications. Heap Statistics can trigger a Full GC at the start and end of a recording; do not enable it indiscriminately in latency-sensitive measurements.

## 22. Continuous Flight Recording

JFR can run continuously with a circular buffer to retain recent events. When an incident occurs, the team can dump data covering the preceding period.

Example continuous recording configuration:

~~~bash
java \
  -XX:StartFlightRecording=disk=true,maxage=1h,maxsize=250m \
  -jar app.jar
~~~

When evidence is needed:

~~~bash
jcmd 12345 JFR.check
jcmd 12345 JFR.dump filename=incident-last-hour.jfr
~~~

Continuous recording is useful for rare bugs whose occurrence cannot be predicted. Set age/size limits, manage disk usage, and specify where files are stored.

JFR recordings may contain information about processes, environments, file paths, exceptions, hosts, threads, and application activity. Treat recording files as sensitive data.

## 23. Using jstat for Periodic GC Observation

`jstat` provides periodic JVM statistics. Example:

~~~bash
jstat -gcutil 12345 1000 10
~~~

This command samples every 1,000 ms for a total of 10 samples. Columns typically show utilization percentages of heap regions, GC counts, and GC times.

`jstat` can be used to quickly observe trends before enabling additional logging. However, `jstat` only provides aggregate metrics; it does not show which objects are retained or which threads are blocking requests.

Combine `jstat` with GC logs, JFR, and heap analysis when pinpointing root causes.

## 24. Diagnosing JVM Crashes and Fatal Error Logs

A Java exception normally produces a stack trace in the application log. A JVM crash occurs when the runtime or native code encounters a fatal error, such as `SIGSEGV`, an access violation, or a bug in a JNI library.

HotSpot usually generates an `hs_err_pid` file on a fatal error. You can specify its location:

~~~bash
java \
  -XX:ErrorFile=./diagnostics/hs_err_pid%p.log \
  -jar app.jar
~~~

Create the `diagnostics` directory before launching and ensure write permissions. If unspecified, the JVM usually attempts to write the file to the working directory; if that fails, it may use the OS temporary directory.

Fatal error logs may contain:

- Signal/exception that caused the crash.
- JDK and JVM version/configuration.
- Faulting thread and stack trace.
- Running threads and their states.
- Heap summary.
- Loaded native libraries.
- Command-line arguments.
- Environment variables.
- OS and CPU information.

Look for `Problematic frame`, `Current thread`, `Native frames`, `Loaded libraries`, and `VM arguments`. If the frame points to a JNI or native library, investigate that library's binary, version, ABI, and memory handling.

Do not assume every `SIGSEGV` is a Java source bug. It may be a VM bug, native code, driver, or memory corruption. Preserve the `hs_err` log and core dump before restarting if possible.

## 25. Core Dumps and Operating System Tools

A core dump is a process snapshot created by the OS when a process crashes or upon request. The file can be very large and require significant storage space.

On Linux, if system policy allows, you can enable core dumps for the current shell:

~~~bash
ulimit -c unlimited
~~~

Core dump location and management depend on the kernel, systemd, container runtime, and host configuration.

For HotSpot core dumps, you can use the Serviceability Agent:

~~~bash
jhsdb jstack --exe /path/to/java --core /path/to/core
~~~

To obtain mixed Java/native stacks from a running process, the JDK provides `jhsdb jstack` with the `--mixed` option. This is an advanced operation that can impact the process; only use it when standard thread dumps are insufficient or the JVM is unresponsive.

OS tools to correlate with:

- Linux: `ps`, `top`, `top -H`, `pmap`, `vmstat`, `iostat`, `dmesg`, and cgroup files.
- Windows: Task Manager, Process Explorer, PerfMon, Event Viewer, and Windows Error Reporting.
- macOS: Activity Monitor, `sample`, `vmmap`, and Console.

Correlate the crash timestamp with OS logs to look for the OOM killer, access violations, disk full, permission issues, or native library failures.

## 26. Diagnosing Applications Running in Containers

In containers, cgroup RAM/CPU limits may be lower than host resources. The JVM can be killed even before the heap reaches `-Xmx`.

Total process memory can include:

- Java heap.
- Metaspace and class space.
- Thread stacks.
- Direct buffers.
- Code cache.
- GC/native structures.
- JNI/native libraries.
- Memory-mapped files.

On Linux cgroup v2, inspect:

~~~bash
cat /sys/fs/cgroup/memory.current
cat /sys/fs/cgroup/memory.max
cat /sys/fs/cgroup/memory.events
~~~

For cgroup v1, paths and filenames differ, typically using `memory.usage_in_bytes` and `memory.limit_in_bytes`.

Exit code 137 often appears when a process receives `SIGKILL` in a container, but it is not enough on its own to conclude an OOM kill. Check `memory.events`, kernel logs, pod events, and container runtime events.

If the heap is stable while container memory grows, inspect direct buffers, thread counts, native memory, JNI, and other processes in the same cgroup. Do not set `-Xmx` equal to the entire container memory; leave headroom for non-heap/native and OS overhead.

## 27. Common Startup and Linkage Errors

| Error | Investigation Direction |
|---|---|
| Could not find or load main class | Check main class, classpath, module path, and working directory |
| NoClassDefFoundError | Check runtime dependencies, classloaders, and earlier initialization errors |
| NoSuchMethodError | Check dependency versions and binary compatibility |
| UnsupportedClassVersionError | Class was compiled with a newer Java version than the running runtime |
| ExceptionInInitializerError | Inspect the root cause in the `Caused by` section |
| Unrecognized VM option | Flag does not exist or is unsupported on the current JDK |
| Could not reserve enough space for object heap | Heap reservation, process architecture, address space, or OS limits |
| Native library load failed | Check native library path, architecture, ABI, and OS dependencies |

Always read the first exception and the `Caused by` chain. The final exception may only be a consequence of an earlier initialization failure.

## 28. Evaluating Memory Leaks by Trend

A memory leak in Java is typically an object that remains reachable through an unintended reference chain.

Strong indicators:

- Heap after GC increases steadily across equivalent load cycles.
- Full GC fails to reclaim much old-generation memory.
- A group of classes grows in instance count or retained heap over time.
- Caches, collections, listeners, `ThreadLocal` variables, or static registries fail to release data.
- Classloaders or Metaspace grow after each reload.

Workflow:

1. Collect GC logs and heap usage under steady load.
2. Take histograms at two or more points in time.
3. Compare class counts and bytes.
4. Take a heap dump once sufficient evidence is gathered.
5. Use dominator tree and path to GC roots to find the reference chain.
6. Fix object lifecycle or ownership.
7. Re-run the same workload and compare the live set after GC.

A large heap is not automatically a leak. An application may legitimately have a large live set. Check whether growth continues once workload and state have stabilized.

## 29. Production-Safe Workflow by Impact Level

| Level | Tool | When to Use |
|---|---|---|
| Low | jcmd -l, VM.version, VM.flags, VM.uptime | Identifying process and environment |
| Low | GC.heap_info, VM.classloader_stats | Checking overview snapshots |
| Low to medium | JFR.start, JFR.check, JFR.dump | Performance analysis over time |
| Medium | Thread.print -l | Hangs, deadlocks, lock contention |
| Medium | VM.native_memory summary | Native memory when NMT is enabled |
| High | GC.class_histogram | Need to identify classes occupying heap |
| High | GC.heap_dump | Analyzing object graph/retained heap |

Before taking a heap dump or histogram in production:

- Check disk space and output path.
- Estimate heap size and object count.
- Determine acceptable pause/impact.
- Use the correct user and PID namespace.
- Record timestamp and reason for collection.
- Restrict file access permissions.
- Do not upload files to public sharing locations.
- Do not restart the process before collecting needed data, unless the system requires immediate service restoration.

Collect enough evidence to answer the current question. Do not enable all logging and profiling at high levels simultaneously, as doing so can add load and alter the symptoms.

## 30. Java 17 Example for Practicing Diagnostics

Create `JvmDiagnosticDemo.java`:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CountDownLatch;

public class JvmDiagnosticDemo {
    private static final List<byte[]> RETAINED = new ArrayList<>();

    public static void main(String[] args) throws InterruptedException {
        for (int i = 0; i < 24; i++) {
            RETAINED.add(new byte[512 * 1024]);
        }

        CountDownLatch stop = new CountDownLatch(1);
        for (int i = 1; i <= 2; i++) {
            Thread worker = new Thread(() -> {
                try {
                    stop.await();
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                }
            }, "diagnostic-worker-" + i);
            worker.setDaemon(true);
            worker.start();
        }

        System.out.println(
            "diagnostic-demo-ready pid=" + ProcessHandle.current().pid()
        );
        Thread.sleep(120_000);
    }
}
~~~

Compile with JDK 17:

~~~bash
javac --release 17 JvmDiagnosticDemo.java
~~~

Run with bounded heap, NMT, GC log, and JFR:

~~~bash
java \
  -Xms64m \
  -Xmx128m \
  -XX:NativeMemoryTracking=summary \
  -Xlog:gc*:file=gc.log:time,uptime,level,tags:filecount=5,filesize=20M \
  -XX:StartFlightRecording=filename=recording.jfr,duration=2m,settings=profile \
  JvmDiagnosticDemo
~~~

The program prints the PID in the format:

~~~text
diagnostic-demo-ready pid=12345
~~~

From a second terminal, replace PID with the actual value:

~~~bash
jcmd -l
jcmd 12345 VM.version
jcmd 12345 VM.command_line
jcmd 12345 VM.flags
jcmd 12345 Thread.print -l
jcmd 12345 GC.heap_info
jcmd 12345 GC.class_histogram
jcmd 12345 VM.native_memory summary
~~~

You can also practice heap dump and JFR:

~~~bash
jcmd 12345 GC.heap_dump heap.hprof
jcmd 12345 JFR.check
jcmd 12345 JFR.dump filename=incident.jfr
jfr summary incident.jfr
~~~

Heap dumps can request a Full GC and create large files. Only run that command on a sample or in an environment that can tolerate the impact.

## 31. Verification Results on JDK 17.0.15

A Java 17 sample was compiled and run with Amazon Corretto 17.0.15 on Windows 11. The JVM was started with a 64–128 MB heap, NMT summary, Unified GC Logging, and Flight Recorder. With `javac --release 17`, the class file has major version 61.

Operations that ran successfully:

| Operation | Observed Result |
|---|---|
| jcmd -l | Found PID and main class JvmDiagnosticDemo |
| VM.version | Reported OpenJDK 64-Bit Server VM 17.0.15+6-LTS |
| VM.command_line | Displayed -Xms, -Xmx, NMT, GC log, and JFR flags |
| VM.flags | Confirmed MaxHeapSize 128 MB, UseG1GC, and NMT summary |
| Thread.print -l | Displayed diagnostic-worker-1 and diagnostic-worker-2 |
| GC.heap_info | Displayed G1 heap, used heap, and Metaspace |
| GC.class_histogram | Byte array `[B` appeared among the largest object groups |
| VM.native_memory summary | Displayed Java Heap, Class, Thread, and native categories |
| VM.native_memory baseline/summary.diff | Successfully captured baseline and allocation delta |
| GC.heap_dump heap2.hprof | Generated an HPROF heap dump of approximately 19 MB |
| JFR.start and jfr summary | Created a 5-second recording and read the event summary |
| Unified GC logging | Wrote gc.log with timestamps and log rotation |

These results confirm the syntax and workflow on a HotSpot JDK 17.0.15 sample. They do not prove every command has the same impact across all JVMs or production workloads. Always check `help` on the target process and evaluate impact before collecting large data sets.

## 32. Checklist When Handling a JVM Incident

- [ ] Record timestamp, PID, host/container, and symptom.
- [ ] Identify the process JDK vendor/version/build.
- [ ] Collect the JVM command line and flags.
- [ ] Record heap limits, container memory/CPU limits, and OS resource limits.
- [ ] Preserve application logs and GC logs around the time of failure.
- [ ] If hung/slow, capture multiple thread dumps spaced a few seconds apart.
- [ ] If CPU is high, correlate OS thread usage and JFR.
- [ ] If heap is growing, compare heap after GC and histograms.
- [ ] If needed, take a heap dump after checking disk space and impact.
- [ ] If RSS grows beyond the heap, check NMT and OS/cgroup metrics.
- [ ] If Metaspace grows, check classloader stats and class load/unload.
- [ ] If the JVM crashes, preserve the `hs_err` log, core dump, and OS logs.
- [ ] Redact secrets and sensitive data before sharing.
- [ ] Document hypotheses, evidence, and results of each measurement.
- [ ] After fixing, re-run the same workload and compare metrics.

## 33. Common Diagnostic Mistakes

| Mistake | Why It Is Ineffective | Better Approach |
|---|---|---|
| Increasing Xmx immediately on OOM | May mask a leak or native memory issue | Classify the OOM and inspect the live set |
| Taking only one thread dump | Cannot see progress or repeated states | Capture multiple snapshots over time |
| Concluding a memory leak from high used heap | The heap may hold a valid cache | Compare heap after GC and retained heap |
| Using jmap/jstack before trying jcmd | These are older tools in JDK 17 guidance | Prefer jcmd; use specialized tools when needed |
| Taking a heap dump without checking disk | Can fill up the filesystem | Check heap size and disk space first |
| Enabling NMT detail permanently without measuring overhead | Can degrade performance | Enable summary first, detail when needed |
| Looking only at total process CPU | Does not identify which thread or stack causes load | Combine OS thread metrics and JFR |
| Restarting before collecting evidence | Loses thread state, recordings, and process context | Collect necessary data first if safe |
| Treating exit 137 as sole proof of OOM | SIGKILL has multiple causes | Check cgroup/kernel/container events |
| Sharing heap dumps/JFR publicly | May expose application data and secrets | Control access, redact, and enforce retention |

## 34. References

- Oracle — Java SE 17 Troubleshooting Guide: https://docs.oracle.com/en/java/javase/17/troubleshoot/
- Oracle — Prepare Java for Troubleshooting: https://docs.oracle.com/en/java/javase/17/troubleshoot/prepare-java-troubleshooting.html
- Oracle — Diagnostic Tools for Java 17: https://docs.oracle.com/en/java/javase/17/troubleshoot/diagnostic-tools.html
- Oracle — The jcmd Command: https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html
- Oracle — The java Command and Unified Logging: https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html
- Oracle — Debug JVM Issues: https://docs.oracle.com/en/java/javase/17/troubleshoot/debug-jvm-issues.html
- Oracle — Java Flight Recorder API: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/jdk/jfr/package-summary.html
- Oracle — JDK Mission Control: https://www.oracle.com/java/technologies/jdk-mission-control.html

Effective JVM diagnostics relies on timestamped data and controlled impact. Start by identifying the process, version, and flags; use thread dumps/JFR for performance issues, GC logs/histograms/heap dumps for heap issues, NMT/OS metrics for native memory, and hs_err/core dumps for crashes. After each change, re-run under the same conditions to confirm the root cause has been resolved.
