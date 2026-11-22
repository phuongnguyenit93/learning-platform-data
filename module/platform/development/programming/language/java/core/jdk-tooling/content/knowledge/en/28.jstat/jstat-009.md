# Limitations of jstat

**jstat** is a JDK command-line tool used to read performance counters exposed by the Java HotSpot VM. It is commonly used to observe garbage collection statistics, heap region utilization, class loading, and JIT compiler activity.

jstat is useful when you need a quick, sample-by-sample view over time. However, it is not a full monitoring system, does not record all runtime events, and does not explain the root cause of an issue. In Oracle JDK 24, jstat is classified as **experimental and unsupported**; its options and functionality may change or be removed in future releases.

This article focuses on data limitations, timing accuracy, supported JVM scope, counter interpretation, remote monitoring, and when to switch to JFR, JMX, jcmd, or OS tools.

## 1. What Does jstat Measure?

jstat reads data from the built-in instrumentation and performance counters of the Java HotSpot VM. These counters provide aggregated information about certain JVM activities, such as:

- Capacity and utilization of heap regions.
- Number of young GC and full GC events that have occurred.
- Total accumulated GC time.
- Capacity and utilization of metaspace.
- Number of classes loaded and unloaded.
- Aggregated JIT compiler statistics.
- Cause of the last GC and the current GC, if any.

jstat does not collect every event inside the JVM. It reads counters published by the VM and displays snapshots at a sampling interval.

### jstat Is Not a Profiler

A profiler or event recorder can capture allocations, stack traces, lock contention, method execution, GC events, and exact timestamps. jstat primarily provides aggregated metrics such as GC counts and total time spent.

For example, jstat can show that the young GC count increased from 20 to 25 between two samples. It does not tell you when each GC started, which objects caused allocation pressure, or which methods created the most objects.

## 2. jstat Only Supports a Specific JVM Scope

jstat is designed for an **instrumented Java HotSpot VM**. You should not assume it can monitor every JVM implementation or every process named `java`.

Practical limitations:

- Non-HotSpot JVMs may not expose the counters that jstat requires.
- A JVM that is not instrumented or does not publish performance data may be inaccessible.
- The user running jstat needs appropriate observation/attach permissions for the target process.
- JVMs running inside a container or a different PID namespace may be difficult to locate from the host.
- LVMID is usually the OS PID, but it is not guaranteed to always match.
- On systems using FAT32, the Oracle Troubleshooting Guide explicitly states that instrumentation is inaccessible.

According to the Oracle JDK 24 Troubleshooting Guide, HotSpot instrumentation is enabled by default and jstat typically does not require starting the JVM with special options. That does not mean every runtime, filesystem, account, or deployment environment can access the data.

### Identifying the Correct VMID

Simple syntax for a local JVM:

~~~bash
jstat -gcutil 12345 1000ms 5
~~~

`12345` is an illustrative LVMID. Find the process using `jps` or OS tools and verify it before running.

Linux/macOS:

~~~bash
ps -p 12345 -o pid,ppid,user,etime,args
~~~

Windows PowerShell:

~~~powershell
Get-CimInstance Win32_Process -Filter "ProcessId = 12345" |
    Select-Object ProcessId, ParentProcessId, Name
~~~

Do not store a PID long-term for later reuse. A PID can be reassigned by the operating system after the original process exits.

## 3. jstat Is an Experimental and Unsupported Tool

Oracle JDK 24 explicitly documents jstat as **experimental and unsupported**. The documentation also states that all options and functionality may change or be removed in future releases.

This directly affects how you should use it:

- Do not treat the output as a stable data interface.
- Do not assume all JDK vendors or versions have the same list of options.
- Do not build critical automation around a fixed output column.
- Do not assume column names, column order, or semantics will always remain the same.
- Check the help output and documentation for the exact JDK running your application.

Check the version and available options:

~~~bash
java --version
jstat --help
jstat -options
~~~

On a tested OpenJDK 24.0.2 build, the option list includes:

~~~text
-class
-compiler
-gc
-gccapacity
-gccause
-gcmetacapacity
-gcnew
-gcnewcapacity
-gcold
-gcoldcapacity
-gcutil
-printcompilation
~~~

This list is the result of a specific toolchain, not a guarantee that future JDK releases will retain all of those options.

## 4. Output Is Not a Stable Format for Parsing

jstat displays data in a table with whitespace-separated columns. The header describes the column names; the selected option determines which columns appear.

Oracle warns against writing scripts that parse jstat output because the format may change in future releases.

Example:

~~~text
Timestamp         S0     S1      E      O      M     CCS    YGC    YGCT
        120.1      -  82.40  54.21  70.10  91.00  88.10     18   0.420
        121.1      -  82.40  66.32  70.10  91.00  88.10     18   0.420
~~~

This is illustrative output. Do not use the numbers in this example as a performance baseline.

A script that splits strings by whitespace can break when:

- Column names or the number of columns change.
- Inapplicable values are displayed as a hyphen (`-`).
- A collector or JDK release adds or removes counters.
- The output contains warnings or diagnostic messages.
- A newer version changes number formatting.

If you need machine-readable metrics, use JMX MXBeans, JFR, a monitoring agent, or an API with a more stable contract. If you still must use jstat in an internal script, pin the JDK version, validate the output format, handle errors, and be prepared to update the script during upgrades.

## 5. Sampling Does Not Record Every Event

General syntax:

~~~bash
jstat -<option> [-t] [-h<lines>] <vmid> [<interval> [<count>]]
~~~

Where:

- `option` selects the statistics group.
- `vmid` identifies the target JVM.
- `interval` is the time between samples.
- `count` is the number of samples to print.
- `-t` adds a column for elapsed time since JVM startup.
- `-h n` repeats the header after every `n` data lines.

Example taking 5 samples, one per second:

~~~bash
jstat -gcutil 12345 1000ms 5
~~~

You can also use seconds as the unit:

~~~bash
jstat -gcutil 12345 1s 5
~~~

If `count` is omitted, jstat continues printing samples until the JVM exits or you stop the command. For one-off checks, specify `count` to avoid leaving a monitoring process running indefinitely.

### Sampling Can Miss Short-Lived Events

Suppose a GC occurs and finishes between two samples. jstat may never show that event in progress; cumulative counters like `YGC` or `YGCT` will simply reflect the increase in the next sample.

Therefore:

- A 5-second sampling interval can miss many short changes.
- A 100 ms sampling interval gives higher resolution, but is still not an event trace.
- An unchanged value between two samples does not prove there was no system activity.
- The timing of a change is only bounded to the window between two samples, not the exact event timestamp.

Choose the interval based on the question you need to answer. Do not use a single interval for every situation.

### Very Frequent Sampling Also Has Limits

jstat must read counters, connect to the JVM, and write output. Polling very frequently across many JVMs increases query volume, output size, and administrative overhead. Even though the tool is generally lighter than a profiler, continuous polling at extremely short intervals should not be treated as free.

For long-term monitoring, use JFR, JMX, or a monitoring platform with proper sampling, storage, and alerting mechanisms.

## 6. jstat Timestamps Are Not Wall-Clock Time

The `-t` option adds a `Timestamp` column:

~~~bash
jstat -gcutil -t 12345 1000ms 5
~~~

`Timestamp` is the number of seconds elapsed since the target JVM started. It is not a UTC or local wall-clock date/time.

Timestamp resolution depends on several factors and can drift when threads experience scheduling delays on heavily loaded systems. Therefore, do not rely on this column alone to correlate precisely with timestamps in application logs, load balancers, or other monitoring systems.

If you need time correlation:

1. Record the wall-clock time when sampling starts.
2. Record the JDK version, host, process identity, and timezone.
3. Use GC logs or JFR with timestamps for a detailed timeline.
4. Account for scheduling delays and clock synchronization differences across machines.

### Repeating Headers with -h

~~~bash
jstat -gcutil -h5 12345 1000ms 20
~~~

The header is reprinted after every 5 samples. This option makes long logs easier to read; it does not increase accuracy or add new data.

## 7. Heap Percentages Are Not Byte Counts

The `-gcutil` option displays utilization as a percentage of the current capacity of each memory pool region.

Common columns:

| Column | Meaning |
|---|---|
| S0, S1 | Survivor space utilization percentage |
| E | Eden utilization percentage |
| O | Old space utilization percentage |
| M | Metaspace utilization percentage |
| CCS | Compressed class space utilization percentage |
| YGC | Cumulative young GC count |
| YGCT | Total accumulated young GC time |
| FGC | Cumulative full GC count |
| FGCT | Total accumulated full GC time |
| GCT | Total accumulated GC time |

Example:

~~~bash
jstat -gcutil 12345 1000ms 5
~~~

If `O` rises from 70% to 85%, it only indicates that the old space is using a larger proportion of its current capacity. You cannot conclude that the heap grew by exactly 15% or that the application has a memory leak.

Region capacity can change as the heap expands or shrinks. To view capacity figures in KB, use:

~~~bash
jstat -gc 12345 1000ms 5
jstat -gccapacity 12345 1000ms 5
~~~

Read capacity and utilization together to understand what denominator the percentages are based on.

### High Percentages Are Not Automatically Errors

High old space or metaspace utilization can be a normal operating state for an application. The garbage collector may retain live objects, caches, or loaded classes by design.

You should also evaluate:

- Post-GC utilization.
- Trends across multiple load cycles.
- GC frequency and duration.
- Heap capacity and configured limits.
- Request latency, throughput, and memory pressure.
- Object graphs or class loaders if a leak is suspected.

Never conclude a memory leak from a single sample.

## 8. Cumulative Counters Are Not Per-GC Event Statistics

Columns such as `YGC`, `YGCT`, `FGC`, `FGCT`, and `GCT` are cumulative counters since JVM startup.

Example:

| Sample | YGC | YGCT (s) | FGC | FGCT (s) |
|---|---:|---:|---:|---:|
| 1 | 20 | 0.800 | 2 | 0.450 |
| 2 | 24 | 0.940 | 2 | 0.450 |

Between the two samples:

- 4 new young GCs occurred.
- Total young GC time increased by 0.140 seconds.
- No new full GCs occurred according to this counter.

These numbers only illustrate how to read counters. They do not tell you how long each individual GC pause lasted or the exact time each one occurred.

### You Cannot Infer Pause Distribution from Total Time

If `YGCT` increases by 140 ms across 4 GCs, you cannot conclude that each pause lasted 35 ms. One event might have taken 100 ms while the other three were much shorter.

To see individual pauses, use unified GC logging:

~~~bash
-Xlog:gc*
~~~

Or use JFR to capture GC events and analyze them in JDK Mission Control.

### Counters Reset When the JVM Restarts

Counters reset with the JVM lifecycle. When a process restarts, `YGC`, `FGC`, and `YGCT` can drop back to small values. If a monitoring pipeline stores data across restarts without tracking process identity, delta calculations can become incorrect.

Always record the PID/LVMID, start time, or application instance identity alongside the metric series.

### Collectors May Expose Collector-Specific Counters

Some collectors or JDK versions publish additional collector-specific counters. For example, G1 output on OpenJDK 24.0.2 may show `CGC` and `CGCT` for concurrent cycles and time. Do not assume every collector exposes the same columns.

## 9. jstat Does Not Reveal the Root Cause of Memory Growth

jstat can show that heap utilization is rising or that GC counts are increasing. It cannot tell you which objects are retaining heap or which classes are driving high allocation rates.

jstat does not directly provide:

- A list of live objects.
- Reference paths to GC roots.
- Retained heap per object.
- Allocation stack traces per allocation.
- A dominator tree.
- Which objects hold unreleased caches or collections.
- Field contents or object reference relationships.

### When You Suspect a Memory Leak

Use jstat to spot the trend, then collect deeper diagnostic data:

~~~bash
jcmd 12345 GC.class_histogram
jcmd 12345 GC.heap_dump heap.hprof
~~~

`GC.class_histogram` shows which classes have the highest instance counts and shallow bytes. A heap dump lets you use MAT or HPROF-compatible tools to inspect the dominator tree and paths to GC roots.

Heap dumps can cause pauses and contain sensitive data. Only collect one after assessing impact, disk space, and access controls.

## 10. jstat Does Not Measure Full Native Memory or Process Memory

jstat focuses on a subset of HotSpot performance counters. Its heap and metaspace columns do not represent the entire memory footprint of the process.

Memory regions or consumers that may require other tools:

- Native thread stacks.
- JNI/native libraries.
- Direct ByteBuffers and native allocations.
- Code cache.
- GC native structures.
- Memory mappings.
- Process RSS/working set.
- Container/cgroup memory limits and usage.
- Memory of child processes or sidecars.

Metaspace and compressed class space appear in certain jstat options, but that does not mean jstat measures all native memory.

### Alternative Tools

If you need to analyze native memory, enable Native Memory Tracking at JVM startup:

~~~bash
-XX:NativeMemoryTracking=summary
~~~

Then run:

~~~bash
jcmd 12345 VM.native_memory summary
~~~

NMT must be enabled when the JVM starts; it cannot be fully enabled retroactively on a running process. NMT also incurs overhead and has different detail levels.

To inspect actual process memory, use OS tools such as `ps`, `top`, Task Manager, or container metrics. Do not sum jstat regions and treat the result as process RSS.

## 11. jstat Does Not Reflect Overall Application Health

jstat is not a health check. It does not know whether a service is processing requests successfully, whether the database is reachable, or whether queues are backed up.

jstat does not directly provide:

- Request rates and error rates.
- Latency percentiles such as p95/p99.
- Thread pool queue lengths.
- Deadlocks and full stack traces.
- Database connection pool health.
- HTTP dependency latency.
- Business transaction success rates.
- Per-core process CPU usage.

A JVM can have a stable heap while the application is still bottlenecked by lock contention, I/O, networking, thread starvation, or the database. Conversely, high heap utilization can be completely normal if GC is operating effectively.

Combine jstat with application metrics, logs, distributed tracing, JFR, and OS monitoring to evaluate the system.

## 12. Option Groups Have Narrow Scopes

jstat provides multiple output options, each presenting only a specific group of counters.

| Option | Primary Data | What Cannot Be Concluded from This Option Alone |
|---|---|---|
| `-class` | Loaded/unloaded class counts and time | Cannot identify which class loaders retain classes or the cause of a leak |
| `-compiler` | JIT compilation statistics and last compilation | Not a CPU profile or full compilation history |
| `-gc` | Capacity and utilization of selected heap spaces, GC counters | Not total process memory or individual GC events |
| `-gccapacity` | Capacity of generations/spaces | Cannot show which objects occupy the space |
| `-gccause` | GC summary and last/current GC cause | Not a complete history of all GC events |
| `-gcnew` | New generation statistics | Does not explain allocation stacks or specific object promotions |
| `-gcnewcapacity` | New generation capacity | Does not show heap pressure from the whole process |
| `-gcold` | Old generation and metaspace counters | Does not show reference paths retaining objects |
| `-gcoldcapacity` | Old generation capacity | Not retained heap per object |
| `-gcmetacapacity` | Metaspace capacity | Does not identify specific class loaders causing metaspace growth |
| `-gcutil` | Utilization percentages and GC counters | Percentages are not absolute byte counts |
| `-printcompilation` | Compilation method statistics | Does not replace JFR or a profiler |

Run:

~~~bash
jstat -options
~~~

to see the options available in your running JDK. Do not assume options have identical semantics across all collectors or releases.

## 13. -gccause Only Reports the Most Recent GC Cause

The option:

~~~bash
jstat -gccause 12345 1000ms 5
~~~

displays a summary similar to `-gcutil` plus:

- `LGCC`: cause of the last GC.
- `GCC`: cause of the current GC, if any.

This is not a log of all GC events. If you need timestamps, durations, GC types, phases, concurrent work, and pause details, use GC logs or JFR.

## 14. Remote Monitoring Depends on jstatd and RMI

jstat can monitor a remote JVM using a VMID with a hostname:

~~~bash
jstat -gcutil 40496@remote.domain 1000ms 10
~~~

This uses RMI and requires `jstatd` on the target host. The RMI registry uses port `1099` by default unless another port is specified.

### jstatd Carries Risks and Is Deprecated

In JDK 24, `jstatd` is **deprecated for removal**. This status applies to `jstatd`, not as a statement that local `jstat` has been deprecated for removal. `jstat` itself remains documented as experimental and unsupported.

The Oracle JDK 24 `jstatd` documentation also notes:

- `jstatd` runs with credentials that have permission to access the target JVMs' instrumentation.
- `jstatd` provides no authentication for remote clients.
- Instrumentation for JVMs accessible to `jstatd` can be exposed to users over the network.
- The remote RMI interface is proprietary and guaranteed to be subject to change.

Do not expose `jstatd` to a public network just for convenience when viewing counters. If you cannot control remote access risks, do not run the daemon; use local `jstat` or a secured monitoring system.

For new systems, prefer JMX with authentication/TLS, JFR streaming, or an approved monitoring agent rather than building new infrastructure that depends on `jstatd`.

## 15. Filesystems, Permissions, and Container Environments

### Process Access Permissions

jstat must be able to read the instrumentation of the target JVM. If the user running the tool lacks the required permissions, the command may fail to find the VM or read its counters.

Do not automatically run as root/Administrator to bypass every error. Verify ownership, attach permissions, and approved operational procedures.

### FAT32

The Oracle JDK 24 Troubleshooting Guide explicitly states that instrumentation is inaccessible on FAT32 filesystems. If the JVM data directory or instrumentation storage resides on FAT32, jstat may not work as expected.

Check the environment's filesystem instead of assuming the JVM lacks performance counters.

### Containers and PID Namespaces

In containers, the PID inside a namespace can differ from the PID observed from the host. jstat requires a VMID valid within the scope where the tool is running.

- Run jstat inside the container if the JDK and required permissions are available.
- Or determine the LVMID/PID matching the host and namespace.
- Do not pass a container-internal PID to a command running on the host in a different namespace.
- Check container process visibility limits and security policies.

jstat does not replace container metrics. JVM memory and container memory usage are two different scopes.

## 16. Practical Walkthrough: Reading a Sample Series

Suppose you run:

~~~bash
jstat -gcutil -t -h5 12345 1000ms 10
~~~

This command takes 10 samples, spaced roughly one second apart, adds an elapsed timestamp, and repeats the header every 5 samples.

Suppose two consecutive samples show:

~~~text
Timestamp         S0     S1      E      O      M     CCS    YGC    YGCT    FGC    FGCT    GCT
       100.0       -  80.00  65.00  72.00  91.00  88.00     20   0.800      2   0.450   1.250
       101.0       -  80.00  12.00  73.50  91.00  88.00     21   0.840      2   0.450   1.290
~~~

This is illustrative data.

You can cautiously infer:

- `YGC` increased from 20 to 21, so one additional young GC occurred between the two samples.
- `YGCT` increased by 0.040 seconds, meaning total accumulated young GC time rose by 40 ms.
- `FGC` is unchanged, so no new full GC occurred according to this counter in that interval.
- `E` dropped sharply because eden utilization changed after the GC cycle.
- `O` rose from 72% to 73.5%, but you need to inspect capacity and more samples before concluding abnormal old-space growth.

From these two lines alone, you cannot determine the exact GC timestamp, the pause duration of the event, which classes caused allocation, or which objects are retained in the old generation.

If you need more detail:

1. Use `-gc` or `-gccapacity` to inspect capacity in KB.
2. Collect GC logs or JFR for an event timeline.
3. Use a heap histogram or heap dump when object-level analysis is needed.
4. Check OS/container metrics if native memory or memory limits are suspected.

## 17. Choosing Alternative Tools by Question

| Question | Appropriate Tool |
|---|---|
| Quick heap utilization and GC counters | jstat |
| GC event timeline and pause details | Unified GC logging or JFR |
| Allocation, lock, and runtime events | JFR + JDK Mission Control |
| Programmatic metrics inside the application | JMX MXBeans |
| One-time inspection of JVM flags or diagnostic state | jcmd |
| Object counts by class | jcmd GC.class_histogram |
| Reference graph and retained heap | Heap dump + MAT |
| Native memory by category | Native Memory Tracking + jcmd |
| Process RSS, CPU, cgroup usage | OS/container monitoring |
| Health, latency, throughput | Application metrics and distributed tracing |
| Long-term monitoring of many JVMs | Secured JMX/agent/monitoring platform |

### JFR Example

JFR can record runtime events over a period of time:

~~~bash
jcmd 12345 JFR.start name=runtime-audit duration=60s filename=runtime-audit.jfr
~~~

You can then open the file in JDK Mission Control or inspect it with the `jfr` tool. Event names and contents depend on the recording configuration and JDK version. JFR is better suited when you need to correlate GC, allocation, CPU, locks, and application behavior.

### JMX Example

MXBeans such as `MemoryMXBean`, `GarbageCollectorMXBean`, and `MemoryPoolMXBean` provide APIs to read memory usage and GC counters. They are well suited for structured monitoring, though JMX endpoints still need to be secured with authentication, TLS, and network controls.

## 18. Common Mistakes When Interpreting jstat

### Rising Heap Percentage Means a Memory Leak

Insufficient evidence. Capacity can change, caches can be valid, and objects may be reclaimed in a subsequent cycle. Compare multiple samples, check post-GC usage, and analyze the object graph if needed.

### GCT Increase Means the Application Paused for Exactly That Duration

`GCT` is cumulative GC time from a counter. It does not tell you pause distribution or per-request latency. Use GC logs or JFR to inspect individual events.

### Unchanged Counters Mean the JVM Is Idle

The JVM may be idle, or changes may have happened between two samples. jstat only takes snapshots, not an event stream.

### O or M Near 100% Is Always an Error

Not necessarily. Check capacity, GC behavior, memory pools, and configured limits. High metaspace usage alone does not prove a class loader leak.

### jstat Failing to Connect Means the JVM Is Hung

The cause could be a wrong PID, attach permissions, an invalid VMID, namespaces, filesystem issues, or inaccessible instrumentation. Verify the process with OS tools first.

### Remote jstat Fails Even Though the JVM Is Running

Check `jstatd`, the RMI registry, ports, hostname, network, and permissions. Remember that `jstatd` is deprecated for removal in JDK 24 and has no authentication for remote clients.

### Parser Script Breaks After Upgrading the JDK

jstat output is not a stable format. Stop relying on token positions; switch to JMX, JFR, or a structured monitoring API.

## 19. Responsible jstat Workflow

1. Identify the exact JDK vendor/version and check `jstat -help` and `jstat -options`.
2. Verify the target JVM, VMID, host, user, and container namespace.
3. Choose the right option for the question: `gcutil`, `gc`, `gccause`, `class`, or `compiler`.
4. Choose a reasonable interval and count; avoid excessively tight polling.
5. Add `-t` if elapsed time is needed and record the wall-clock start time separately.
6. Record the JDK, collector, heap flags, host, and process identity.
7. Read percentages alongside capacity; do not draw conclusions from a single column.
8. Compare cumulative counters using deltas between samples.
9. Use GC logs or JFR if you need an event timeline or pause distribution.
10. Use heap dumps or histograms if you need object-level diagnosis.
11. Use OS/NMT metrics if you need native memory and process RSS.
12. Do not parse jstat output in critical automation.
13. Do not expose remote `jstatd` without a security assessment; prefer secured monitoring solutions.
14. Store results by release/runtime and re-evaluate after upgrading the JDK.

## 20. Limitations Checklist to Remember

- jstat is experimental and unsupported in Oracle JDK 24.
- jstat only reads instrumentation from an instrumented HotSpot VM.
- LVMID is usually, but not necessarily, the OS PID.
- Instrumentation is inaccessible on FAT32 according to the Oracle Troubleshooting Guide.
- Counters are snapshots or cumulative totals, not event traces.
- Sampling can miss short-lived changes between two reads.
- Timestamp `-t` is elapsed time since JVM startup, not wall-clock time.
- Output format can change; do not parse it in production scripts.
- `gcutil` reports percentages of current capacity, not absolute bytes.
- `YGC`/`FGC` and GC times are cumulative counters, not pause distributions.
- `gccause` only reports the most recent/current cause, not the full history.
- jstat does not provide an object graph, retained heap, or allocation stack traces.
- jstat does not measure full native memory, RSS, or container usage.
- Remote monitoring depends on `jstatd`/RMI; `jstatd` is deprecated for removal as of JDK 24.
- `jstatd` does not authenticate remote clients in the JDK 24 documentation.
- Use JFR, JMX, jcmd, GC logs, and OS/container metrics for deeper investigations.

## 21. Key Terms to Remember

| Term | Meaning |
|---|---|
| jstat | Tool for reading HotSpot JVM performance counters |
| Instrumented VM | A JVM that publishes instrumentation data for management tools |
| VMID | Virtual machine identifier used by jstat to locate a JVM |
| LVMID | Local VM identifier, usually but not necessarily the OS PID |
| Sampling interval | Time interval between two samples |
| Count | Number of samples jstat will print |
| Snapshot | State of counters at a single point in time |
| Cumulative counter | Counter accumulated since JVM startup |
| YGC / FGC | Young GC / Full GC counts |
| YGCT / FGCT / GCT | Cumulative GC times |
| Heap capacity | Current capacity or limit of a memory pool |
| Utilization | Percentage of capacity currently in use |
| Metaspace | Native memory region storing class metadata |
| JFR | Java Flight Recorder, a tool for recording runtime events |
| JMX MXBean | Structured API for managing and monitoring a JVM |
| NMT | Native Memory Tracking |
| jstatd | RMI daemon allowing remote jstat/jps access to JVMs |
| JMX | Java Management Extensions |
| GC log | Log of garbage collection events |
| Retained heap | Memory kept alive by an object together with objects only it references |

jstat is well suited for quickly viewing aggregated HotSpot JVM counters. Its limitations around instrumentation scope, sampling, cumulative counters, unstable output format, lack of object-level detail, and remote `jstatd` mean it cannot replace a full observability stack. Use jstat to guide your investigation, then switch to JFR, JMX, jcmd, GC logs, or OS metrics for questions that require deeper detail.

## References

- Oracle JDK 24 — [The jstat Command](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jstat.html)
- Oracle JDK 24 — [The jstatd Command](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jstatd.html)
- Oracle JDK 24 — [Release Notes: jstatd Is Deprecated for Removal](https://www.oracle.com/java/technologies/javase/24-relnote-issues.html)
- Oracle JDK 24 — [Troubleshooting Guide: The jstat Utility](https://docs.oracle.com/en/java/javase/24/troubleshoot/troubleshooting-guide.pdf)
- Oracle JDK 24 — [Java Flight Recorder and JDK Mission Control](https://docs.oracle.com/en/java/javase/24/troubleshoot/diagnostic-tools.html)
