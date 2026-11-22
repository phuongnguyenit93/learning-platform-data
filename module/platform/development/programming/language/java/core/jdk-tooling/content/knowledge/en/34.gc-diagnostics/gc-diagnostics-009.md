# Analyzing GC Logs in Java

A **GC log** is a log recorded by the Java Virtual Machine to describe garbage collection (GC) activity: collection type, timestamp, heap usage before and after GC, pause duration, phases, and certain CPU or Metaspace details. Analyzing GC logs helps determine whether the JVM is collecting too frequently, experiencing overly long pauses, retaining too many objects, or encountering allocation issues.

Since Java 9, HotSpot uses **Unified Logging** with the **-Xlog** syntax. This is the modern way to configure GC logging, replacing older examples that used multiple individual `PrintGC` flags. For G1, you can start with **-Xlog:gc*=info** for an overview; when investigating root causes, add phase, heap, CPU, safepoint, or debug-level logs.

A GC log provides evidence of collector behavior, not an object graph map. It shows how the heap changes and what the GC did, but it does not by itself identify which object holds a reference or which class causes a memory leak. When you need that level of detail, combine it with JFR, heap histograms, heap dumps, and application metrics.

## 1. What Is a GC Log Used For?

GC logs help answer questions such as:

- Which garbage collector is the JVM using?
- How frequently do Young GC, Mixed GC, or Full GC occur?
- How long does each pause last?
- How much heap remains after each collection?
- Are the old generation or Metaspace growing continuously?
- Are there evacuation failures, allocation failures, or humongous allocations?
- Which phases is the GC spending time on?
- Does GC CPU time come from the VM, the operating system, or scheduling?
- Are there non-GC safepoints causing long application pauses?
- Did changes to code, heap, or GC configuration improve latency?

GC logs are especially useful when investigating:

- Periodic spikes in request latency.
- Abnormal CPU spikes.
- Continuous Young GC occurrences.
- Long Full GC pauses.
- Heap not shrinking after GC.
- Growing Metaspace or lack of class unloading.
- `OutOfMemoryError` or `GC overhead limit exceeded`.
- Pause times exceeding SLOs.

### GC Logs Do Not Replace Application Monitoring

GC logs only describe JVM/collector activity. They do not directly show which requests are slow, p95/p99 latency, database queries, queue backlogs, or business error rates.

During production investigations, correlate GC logs with application metrics, distributed tracing, OS/container metrics, and JFR.

## 2. Unified Logging and the -Xlog Syntax

Since JDK 9, HotSpot has integrated Unified Logging. GC is a group of tags within this system.

General syntax:

~~~bash
-Xlog:<selections>:<output>:<decorators>:<output-options>
~~~

Components:

- **selections:** tags, tag combinations, and log levels.
- **output:** stdout, stderr, or file.
- **decorators:** timestamp, uptime, level, tags, PID, etc.
- **output-options:** rotation, file size, and number of files to retain.

A tag selection can combine multiple tags using a plus sign (`+`). Commas separate different selections.

Example:

~~~bash
-Xlog:gc
~~~

Writes only messages with the exact `gc` tag at `info` level or higher to `stdout` using the default configuration.

Broader example:

~~~bash
-Xlog:gc*=info
~~~

Writes messages with the `gc` tag and related GC tags at `info` level. This is a useful starting point for an overview across many collectors.

### Difference Between gc and gc*

- **gc:** selects only messages with the exact `gc` tag.
- **gc*:** selects tag sets containing `gc` and additional related tags, such as `gc,start`, `gc,heap`, and `gc,phases`.

Therefore, `gc*` produces more detailed logs and can generate many more lines.

### Log Levels

Commonly used levels:

| Level | Meaning |
|---|---|
| off | Disable messages |
| error | Errors |
| warning | Warnings |
| info | Operational information |
| debug | Diagnostic details |
| trace | Very detailed |

If you only need a high-level overview, start at `info`. Only enable `debug` or `trace` for the specific tags under investigation and for a limited duration.

## 3. Enabling GC Logging at JVM Startup

G1 example on Java 17+:

~~~bash
java -Xms512m -Xmx512m -XX:+UseG1GC -Xlog:gc*=info -jar app.jar
~~~

The command above:

- Configures minimum and maximum heap to 512 MB.
- Explicitly selects G1.
- Logs GC information and related tags.
- Writes to `stdout` by default.

To write to a file with timestamps and useful decorators:

~~~bash
java -Xms512m -Xmx512m -XX:+UseG1GC "-Xlog:gc*=info:file=gc.log:time,uptime,level,tags" -jar app.jar
~~~

On Windows PowerShell, wrap the entire option containing colons in double quotes as shown to prevent the shell from interpreting special characters.

### Using a More Concise Log

~~~bash
java "-Xlog:gc:file=gc.log:time,uptime,level,tags" -jar app.jar
~~~

This configuration selects only the `gc` tag at `info` level. When you need phase breakdowns or heap details, use `gc*` or add specific selections.

### Logging G1 Phase Details

~~~bash
java "-Xlog:gc*=info,gc+phases=debug:file=gc.log:time,uptime,level,tags" -jar app.jar
~~~

`gc+phases=debug` adds detailed information about GC phases. The plus sign in tag syntax means a message must carry both the `gc` and `phases` tags.

Do not enable all tags at `trace` level in production for extended periods without evaluating log volume, I/O, and storage capacity.

## 4. Decorators: Reading Timestamps and Log Sources

A log line may start with:

~~~text
[2026-11-10T20:17:50.458+0700][0.038s][info][gc]
~~~

Components:

- **time:** wall-clock date and time.
- **uptime:** elapsed time since JVM startup.
- **level:** log level, such as `info`.
- **tags:** tag set, such as `gc`.

Useful decorators:

| Decorator | Meaning |
|---|---|
| time | Local date and time |
| utctime | UTC date and time |
| uptime | Time since JVM start |
| uptimemillis | Uptime in milliseconds |
| timemillis | Wall-clock epoch milliseconds |
| pid | Process ID |
| tid | Thread ID |
| level | Log level |
| tags | Tag set of the message |
| hostname | Hostname |
| none | No decorators added |

Example adding PID and hostname:

~~~bash
-Xlog:gc*=info:file=gc-%p.log:time,uptime,pid,hostname,level,tags
~~~

`%p` is replaced by the JVM's PID in the filename. You can also use `%t` for the startup timestamp and `%hn` for the hostname depending on JDK version support.

Uptime is very useful for correlating with application logs or deployment times. Wall-clock time is useful for correlating with external monitoring, though timezone and clock synchronization must be accounted for.

## 5. Log Rotation and Size Management

GC logs can grow rapidly, especially when using `gc*=debug` or `trace`. Enable file rotation to avoid an unbounded single file.

Example:

~~~bash
java "-Xlog:gc*=info:file=gc-%p.log:time,uptime,level,tags:filecount=5,filesize=20M" -jar app.jar
~~~

Meaning:

- **file=gc-%p.log:** filename containing the PID.
- **filesize=20M:** target size of about 20 MB per file.
- **filecount=5:** keep at most 5 archive files in addition to the active file.

File size and count should be chosen based on retention requirements, logging rate, and volume capacity. Rotation does not replace backup or retention policies.

### Key Considerations

- Ensure the output directory exists and the JVM has write permissions.
- Use a volume with sufficient capacity.
- Do not write GC logs to a nearly full filesystem.
- Monitor both the active file and archive files.
- Do not delete logs currently being used for an incident investigation.
- If running multiple JVMs, include PID or timestamp in filenames to avoid overwriting.

The JVM supports output options such as `filesize` and `filecount`. Check `java -Xlog:help` on your target JDK to confirm the syntax.

## 6. Common GC Logging Configurations

| Goal | Configuration |
|---|---|
| GC summary | -Xlog:gc |
| GC and related tags | -Xlog:gc*=info |
| Detailed GC phases | -Xlog:gc+phases=debug |
| Heap usage/regions | -Xlog:gc+heap=info |
| GC CPU time | -Xlog:gc+cpu=info |
| GC ergonomics | -Xlog:gc+ergo=debug |
| Reference processing | -Xlog:gc+ref=debug |
| Safepoints | -Xlog:safepoint=info |
| Multiple groups together | -Xlog:gc*=info,safepoint=info |

You can write GC and safepoint logs to the same file:

~~~bash
java "-Xlog:gc*=info,safepoint=info:file=gc.log:time,uptime,level,tags" -jar app.jar
~~~

If phase breakdowns are needed:

~~~bash
java "-Xlog:gc*=info,gc+phases=debug,gc+cpu=info,safepoint=info:file=gc-detail.log:time,uptime,level,tags:filecount=5,filesize=20M" -jar app.jar
~~~

You do not need to enable every selection for every incident. Start with `info` logs, identify what is missing, and add the corresponding tags.

## 7. Enabling or Checking Logging on a Running JVM

If a JVM is already running without GC logging enabled, you can inspect or enable dynamic logging via the `VM.log` diagnostic command if supported by the runtime.

List current configuration:

~~~bash
jcmd <pid> VM.log list
~~~

View syntax for the exact JVM:

~~~bash
jcmd <pid> help VM.log
~~~

Example configuring a new output file:

~~~bash
jcmd <pid> VM.log output=gc-dynamic.log what="gc*=info" decorators="time,uptime,level,tags"
~~~

This command instructs the JVM to enable the selection and output according to supported parameters. Relative paths are resolved against the JVM's working directory. Check `VM.log list` after configuring to confirm.

You can trigger log output rotation:

~~~bash
jcmd <pid> VM.log rotate=true
~~~

Dynamic logging is useful when you cannot restart immediately, but keep in mind:

- It only applies to the lifetime of the current JVM process.
- It does not persist configuration for the next restart.
- It may be restricted by attach permissions and runtime settings.
- You must verify that the output file is created and written to.
- Do not use `disable=true` carelessly as it may clear other logging configurations.

For long-term operational configurations, place `-Xlog` in the startup command or service configuration.

## 8. Anatomy of a GC Log Line

A G1 summary line may look like this:

~~~text
[2026-11-10T20:17:50.458+0700][0.038s][info][gc] GC(0) Pause Young (Normal) (G1 Evacuation Pause) 17M->2M(32M) 0.767ms
~~~

Reading each part:

| Component | Meaning |
|---|---|
| timestamp | Wall-clock time |
| uptime | JVM running time |
| info | Log level |
| gc | Tag |
| GC(0) | Collection event ID |
| Pause Young | Collection type and stop-the-world pause |
| Normal | Collection group/cause |
| G1 Evacuation Pause | G1 collection context |
| 17M | Heap usage before GC |
| 2M | Heap usage after GC |
| (32M) | Heap capacity at that moment |
| 0.767ms | Pause duration recorded in the summary |

### How to Read A->B(C)

Pattern:

~~~text
17M->2M(32M)
~~~

means:

- Before collection: heap usage is approximately 17 MB.
- After collection: heap usage is approximately 2 MB.
- Capacity: approximately 32 MB.

These are aggregate heap metrics at the time of collection, not per-object retained sizes. For collections that only process part of the heap, do not interpret the post-GC value as the exact total live set of the application.

Capacity can change over time as the heap expands or shrinks. Therefore, read all three numbers rather than looking only at percentages or post-GC values.

### GC ID Correlates Related Lines

A single collection can emit multiple lines for start, tasks, phases, heap, metaspace, and cpu. Lines sharing the same `GC(n)` belong to the same collection.

Use this ID to match phase breakdowns with the summary line and avoid accidentally combining lines from two different collections.

## 9. Distinguishing Young, Mixed, Concurrent, and Full GC

Collection names depend on the collector and JDK version. For G1, common types include:

### Young GC

G1 collects regions belonging to the young generation. This is typically a stop-the-world pause. Surviving objects are moved to survivor or old regions depending on their age and state.

Frequent Young GCs are not necessarily a bug. If the allocation rate is high, frequent young collections are normal behavior.

Check:

- Interval between collections.
- Duration of each pause.
- Amount of heap reclaimed.
- Changes in survivor/old regions.
- Request latency during the same period.

### Concurrent Start

A young pause can initiate a concurrent marking cycle. G1 then executes marking phases while application threads continue running.

Concurrent marking helps identify old generation regions eligible for reclamation. It does not mean the entire GC is concurrent; stop-the-world pauses such as Remark and Cleanup still occur.

### Mixed GC

After marking completes, G1 may perform Mixed collections. The collection set includes young regions plus selected old regions for reclamation.

Mixed GCs often appear as a series of pauses during the space reclamation phase. Do not treat every Mixed pause as a Full GC.

### Full GC

Full GC is typically a stop-the-world operation that can be very expensive. In G1, the log may record:

~~~text
Pause Full (G1 Compaction Pause)
~~~

If Full GCs recur, investigate allocation rate, old-generation occupancy, whether concurrent marking completes in time, humongous allocations, and excessive object retention.

A single Full GC may be caused by `System.gc()` or an external tool request. Always check the cause in the log before drawing conclusions.

## 10. Analyzing G1 Phase Breakdowns

G1 divides work within a pause into multiple phases. Enable:

~~~bash
-Xlog:gc+phases=debug
~~~

Common phase groups:

- Pre Evacuate Collection Set.
- Merge Heap Roots.
- Evacuate Collection Set.
- Post Evacuate Collection Set.
- Other.

Among these, **Evacuate Collection Set** is usually the main part of moving live objects out of the selected regions. If this phase dominates the pause, duration may relate to the volume of live objects to copy, the number of roots/references to scan, and CPU capacity.

Some sub-phases:

- Ext Root Scanning.
- Code Root Scan.
- Scan Heap Roots.
- Object Copy.

### Why Are Pauses Long?

A long pause can be caused by:

- Too many live objects to copy.
- Large heap or large collection set.
- Large remembered sets.
- Many roots/references to scan.
- CPU throttling or contention.
- High allocation pressure.
- Heap fragmentation or evacuation failure.
- OS overhead in memory management.

Do not look only at total duration. Identify which phase takes the most time, then correlate with CPU, heap, and workload.

## 11. Reading GC CPU Time and Safepoints

### GC CPU Breakdown

Enable:

~~~bash
-Xlog:gc+cpu=info
~~~

Example line:

~~~text
GC(0) User=0.20s Sys=0.00s Real=0.01s
~~~

Meaning:

- **User:** total CPU time of GC workers in user mode.
- **Sys:** CPU time in kernel/system mode.
- **Real:** actual elapsed wall-clock time of the pause.

User time can exceed Real time because GC runs in parallel across multiple workers. For example, total worker CPU might be 200 ms while the wall-clock pause is only 10 ms.

If Sys time is abnormally high, check the OS, memory allocation, filesystem, container limits, and environmental factors.

### Safepoint Logging

GC pauses typically occur at safepoints, but the JVM also enters safepoints for many other operations. Enable:

~~~bash
-Xlog:safepoint=info
~~~

Safepoint logs show how long the JVM takes to request and reach a safepoint, how long application threads are stopped, and related details.

If request latency is high without corresponding pauses in the GC summary, check safepoint logs for other stop-the-world events.

Do not directly sum all durations from GC and safepoint logs if they describe overlapping time windows or have different boundaries. Understand each field and ID before aggregating.

## 12. Heap, Generations, and Metaspace

Some log lines provide the state of heap regions:

~~~text
Eden regions: 20->0(18)
Survivor regions: 2->3(4)
Old regions: 10->10
Humongous regions: 1->1
Metaspace: 8152K->8152K(1056768K)
~~~

The numbers above only illustrate the structure.

### Eden and Survivor

Eden holds newly allocated objects in G1. Survivor holds objects that survived a collection and continue to be retained.

If Eden fills up frequently, Young GC will occur. This can be a sign of a high allocation rate, not necessarily a memory leak.

### Old Regions

Long-lived objects may be promoted to the old generation. If old regions grow continuously and do not decrease after GC cycles, investigate the live set, caches, sessions, collections, or reference retention.

### Humongous Regions

In G1, objects with a size of at least half a region are treated as humongous objects. They occupy humongous regions and have distinct allocation/reclamation handling.

If humongous regions increase significantly:

- Check for very large arrays or objects.
- Check the region size.
- Check payload, buffer, and batch sizes.
- Check whether GCs are triggered early due to humongous allocations.
- Evaluate fragmentation and the ability to find enough contiguous regions.

Do not conclude fragmentation from a single humongous count line; inspect heap state and collection history.

### Metaspace

Metaspace stores class metadata in native memory. The Metaspace line reflects metadata state as logged by the JVM.

If Metaspace grows continuously, it may be due to continuous class loading, a class loader leak, or frameworks generating dynamic classes. Combine class loading counters, JFR, `jcmd VM.classloader_stats`, and heap analysis to find the cause.

Metaspace is not Java heap. Do not add Metaspace to heap usage and treat it as the process's total RSS.

## 13. Common Abnormal GC Symptoms

### Overly Frequent Young GC

Symptoms:

- Short intervals between Young pauses.
- Eden fills back up quickly.
- Young GC count increases continuously.
- Total GC time accounts for a significant percentage.

Possible causes include a high allocation rate, excessive temporary object creation, or inappropriate heap/young sizing.

Investigation steps:

1. Use JFR allocation profiling.
2. Find methods allocating many objects.
3. Inspect object lifetimes and allocation rates.
4. Reduce unnecessary allocations.
5. Review workload and heap sizing.

### Post-GC Heap Trending Upward

If the heap value after collection increases over time, the live set may be growing.

Possible causes include:

- Unbounded caches.
- Unreleased session or request state.
- Queue backlogs retaining objects.
- Static collections or listeners holding references.
- Old class loaders remaining reachable.

This is a symptom worth investigating, not yet proof of a memory leak. Compare across multiple cycles under the same workload and heap capacity.

### Repeated Full GC

Look for lines such as:

~~~text
Pause Full (G1 Compaction Pause)
~~~

Check the cause and preceding collections. Full GCs can relate to high old generation occupancy, concurrent marking failing to keep up with allocation, humongous objects, or explicit GC requests.

If a Full GC reclaims very little heap, inspect object retention and heap dumps.

### Evacuation Failure

G1 may log:

~~~text
Evacuation Failure: Allocation
~~~

or:

~~~text
Evacuation Failure: Pinned
~~~

- **Allocation:** insufficient destination regions to move objects into.
- **Pinned:** objects are pinned (for example via JNI critical access) and cannot be moved during that evacuation.

Evacuation failures can leave regions temporarily unusable and increase collection pressure. Check heap occupancy, live set, allocation rate, native/JNI usage, and subsequent Full GCs.

### Abnormally Long Pauses

Check:

- Total pause duration.
- Phase breakdown.
- GC worker count.
- User/Sys/Real CPU time.
- Heap size and live objects.
- CPU throttling or OS scheduling.
- Safepoint synchronization.

If Real time is high while User/Sys cannot explain it, check scheduling and time spent waiting to reach a safepoint. If User time is high, the GC may be doing heavy parallel work.

### Growing Metaspace or Metaspace OOM

Check class loading/unloading, class loader stats, and native memory. If class count and Metaspace grow together, investigate class loader lifecycles, dynamic proxies, plugins, and redeployments.

## 14. Measuring GC Metrics Over Time

Do not evaluate a collector based on a single isolated pause. Collect a time series over a representative period.

Metrics to aggregate:

| Metric | How to Read |
|---|---|
| GC count | Number of collections by type |
| Pause duration | Duration of each stop-the-world pause |
| Pause p50/p95/p99/max | Pause distribution |
| Time between GC | Interval between collections |
| Heap before/after | Occupancy before/after collection |
| Old occupancy after GC | Live set/retention trend |
| Allocation rate | Volume of objects allocated over time |
| Promotion rate | Rate at which objects move to old generation |
| GC CPU time | CPU spent on the collector |
| Metaspace usage | Class metadata trend |
| Humongous regions | Number of regions holding large objects in G1 |
| Safepoint duration | JVM stop duration due to safepoints |

### Pause Time Ratio

For collectors with stop-the-world pauses, you can estimate the fraction of time the application is paused by GC by dividing total pause time by the observation window.

This is only an approximation:

- Avoid double-counting start and summary lines.
- Distinguish pause duration from concurrent GC duration.
- Concurrent collectors also consume CPU while the application is running.
- Safepoints may include additional overhead outside GC work.

Do not use a single ratio to declare a collector good or bad. Evaluate it alongside throughput, latency, and CPU budget.

## 15. Log Differences Across Garbage Collectors

Phase and event names depend on the collector. Do not apply G1 reading rules to every JVM.

| Collector | General Characteristics When Reading Logs |
|---|---|
| Serial GC | Single-threaded, stop-the-world collections; logs typically focus on young/full collections |
| Parallel GC | Stop-the-world collections with multiple workers; inspect worker CPU and pauses |
| G1 GC | Region-based; includes Young, Concurrent Start, Mixed, marking, and evacuation phases |
| ZGC | Designed for very short pauses, heavy concurrent work; logs have collector-specific phases and cycles |
| Shenandoah | Concurrent evacuation/reclamation; logs have collector-specific phases and cycles |

First identify the actual collector via JVM flags or GC initialization lines. Do not infer the collector from a single event name alone.

Example checking flags:

~~~bash
java -XX:+PrintFlagsFinal -version
~~~

Or inspect startup logs with appropriate `gc` init logging configured.

### G1

G1 tries to balance throughput and pause-time goals. Tuning a pause target does not guarantee every pause stays below the target. Inspect the collection set, live data, and phase costs.

### Parallel

Parallel GC targets throughput. Longer pauses can be a trade-off to finish collections quickly and maximize application runtime between pauses.

### ZGC and Shenandoah

These collectors focus on minimizing pauses by shifting most work into concurrent phases. Do not look only at stop-the-world pauses; monitor CPU overhead, allocation headroom, concurrent cycle duration, and throughput.

## 16. Legacy GC Logging and Migrating to -Xlog

Older documentation may use:

~~~bash
-verbose:gc
-XX:+PrintGCDetails
-Xloggc:gc.log
~~~

Since JDK 9, Unified Logging replaces legacy GC logging configuration with `-Xlog`.

Oracle notes that `-verbose:gc` is an alias for `-Xlog:gc`. Other legacy flags have their own compatibility histories and may vary by JDK. Do not copy an entire flag set from a Java 8 runbook to a modern JDK without verifying it.

Recommended modern configuration:

~~~bash
-Xlog:gc*=info:file=gc.log:time,uptime,level,tags
~~~

Check help:

~~~bash
java -Xlog:help
~~~

Help lists the tags, levels, decorators, and output options supported by the exact runtime.

## 17. Analyzing GC Logs with Tools

### Using PowerShell to Filter Logs

Find Young and Full GC:

~~~powershell
Select-String -Path .\gc.log -Pattern "Pause Young|Pause Full"
~~~

Find evacuation failures:

~~~powershell
Select-String -Path .\gc.log -Pattern "Evacuation Failure"
~~~

Find Metaspace:

~~~powershell
Select-String -Path .\gc.log -Pattern "Metaspace"
~~~

### Using grep on Linux/macOS

~~~bash
grep -E "Pause Young|Pause Full" gc.log
grep -E "Evacuation Failure" gc.log
grep -E "Metaspace" gc.log
~~~

These commands only filter lines for quick investigation; they do not replace a parser that understands log structure.

### JDK Mission Control and JFR

JFR lets you view GC events, allocations, thread CPU, locks, and I/O on a single timeline. JMC is well-suited when analyzing the relationship between GC and workload.

Start a recording:

~~~bash
jcmd <pid> JFR.start name=gc-analysis settings=profile duration=60s filename=gc-analysis.jfr
~~~

Then open the file in JMC and inspect Garbage Collections, Heap, Allocation, and Threads.

### GC Log Analyzers

You can use GCViewer or other GC log analyzers to summarize pause distributions, throughput, and heap trends. Verify that the tool supports the exact JDK log format you are using.

GC logs may contain hostnames, PIDs, file paths, and internal details. If using an online analysis service, upload only when authorized and after assessing sensitive data. Prefer local tools for production logs.

## 18. Java 17+ Lab: Generating and Analyzing a GC Log

This lab intentionally creates allocation pressure to observe Young GC and calls `System.gc()` once to produce a Full GC with a clear cause. Do not use `System.gc()` as a production optimization technique; this call is solely for log demonstration.

Create **GcLogDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.List;

public final class GcLogDemo {
    private static final List<byte[]> retained = new ArrayList<>();

    public static void main(String[] args) throws InterruptedException {
        System.out.println("READY");

        for (int i = 0; i < 300; i++) {
            byte[] block = new byte[256 * 1024];
            block[0] = (byte) i;

            if (i % 20 == 0) {
                retained.add(block);
            }
        }

        System.out.println("Retained blocks: " + retained.size());

        System.gc();
        Thread.sleep(100);

        System.out.println("DONE");
    }
}
~~~

Compile:

~~~bash
javac --release 17 GcLogDemo.java
~~~

Run with G1 and a 32 MB heap:

~~~bash
java -Xms32m -Xmx32m -XX:+UseG1GC "-Xlog:gc*=info:file=gc.log:time,uptime,level,tags" GcLogDemo
~~~

Exact stdout:

~~~text
READY
Retained blocks: 15
DONE
~~~

The program creates 300 arrays of 256 KiB each. Every 20 iterations, one array is kept in a static list. Since the loop runs from 0 to 299, 15 arrays are retained.

### Viewing the GC Summary

Open `gc.log` and look for lines such as:

~~~text
GC(0) Pause Young (Normal) (G1 Evacuation Pause) 17M->2M(32M) 0.767ms
GC(6) Pause Full (System.gc()) 13M->4M(32M) 2.844ms
~~~

These are representative lines from a test run on OpenJDK 24.0.2. Timestamps, GC IDs, heap usage, and durations vary by environment.

Interpretation:

- Young GC collects temporary objects and reduces heap usage.
- Full GC was triggered by the `System.gc()` call.
- Heap after Full GC remains around 4 MB because the static list retains the arrays.
- Capacity is 32 MB as configured by `-Xms`/`-Xmx`.
- Pause durations in this example are very short because the heap is small and the workload is simple.

Find collections:

~~~powershell
Select-String -Path .\gc.log -Pattern "Pause Young|Pause Full"
~~~

Find heap initialization and Metaspace:

~~~powershell
Select-String -Path .\gc.log -Pattern "Heap Max Capacity|Metaspace"
~~~

### Experimenting with Changes

You can re-run with a larger heap:

~~~bash
java -Xms64m -Xmx64m -XX:+UseG1GC "-Xlog:gc*=info:file=gc-64m.log:time,uptime,level,tags" GcLogDemo
~~~

Compare Young GC count, heap before/after, and pauses. A larger heap may reduce collection frequency, but it does not automatically make an application better; it can increase memory footprint or alter pause behavior.

You can run with detailed phase logging:

~~~bash
java -Xms32m -Xmx32m -XX:+UseG1GC "-Xlog:gc*=info,gc+phases=debug:file=gc-detail.log:time,uptime,level,tags" GcLogDemo
~~~

Compare total pause time against individual phases to understand where the GC spends its time.

## 19. Troubleshooting by Log Symptoms

### Continuous GC Activity

- Check the interval between Young GCs.
- Inspect allocation rate with JFR.
- Identify methods creating many objects.
- Check heap size and workload.
- Reduce unnecessary allocations before switching collectors.

### Post-GC Heap Growing Across Cycles

- Inspect old regions and live set.
- Check caches, sessions, queues, and static collections.
- Use class histograms and heap dumps.
- Find paths to GC roots with MAT.
- Compare under the same workload over time.

### Long Full GC

- Identify the cause: explicit GC, allocation pressure, or old generation state.
- Check for prior evacuation failures.
- Check whether concurrent marking completes in time.
- Check humongous allocations and fragmentation.
- Check live object volume and CPU availability.

### Pauses Exceeding SLO

- Inspect phase breakdowns.
- Inspect User/Sys/Real times.
- Check heap size and collection set.
- Check CPU throttling, scheduling, and memory pressure.
- Correlate safepoints and request latency.
- Do not simply lower `MaxGCPauseMillis` without understanding the root cause.

### Continuously Growing Metaspace

- Inspect class load/unload counters.
- Check class loader statistics.
- Investigate plugins, redeployments, and dynamic proxies.
- Use heap dumps/JFR to find reachable loaders.
- Check Metaspace limits and native memory.

### No GC Events in the Log

- Verify the right JVM and right file.
- Check that `-Xlog` selection includes the `gc` tag.
- Check log level, output path, and write permissions.
- Check rotation and archive files.
- Inspect `jcmd <pid> VM.log list` if using dynamic logging.
- Confirm the JVM actually performed GC during the observation window.

### GC Log Too Large

- Reduce from `gc*=debug`/`trace` to `info`.
- Enable only necessary phases/tags.
- Enable file rotation.
- Shorten recording duration.
- Establish retention and secure storage.

## 20. Complete GC Log Analysis Workflow

1. Identify the service, JVM PID, JDK version, and active collector.
2. Collect GC logs under a representative workload.
3. Record timestamps, uptime, PID, and tags.
4. Confirm the log captures all collections during the investigation window.
5. Calculate GC count, intervals, and pause durations.
6. Inspect heap before/after and capacity.
7. Track old generation, survivor, humongous regions, and Metaspace.
8. Look for Full GC, evacuation failures, and allocation failures.
9. Enable `gc+phases` and `gc+cpu` when pause analysis is needed.
10. Use safepoint logs if stop times are not explained by GC summaries.
11. Combine with JFR to inspect allocations, threads, and CPU.
12. Use heap dumps/MAT if object retention analysis is needed.
13. Correlate with application latency, throughput, error rate, and OS/container metrics.
14. Form a hypothesis and change only one primary factor at a time.
15. Record a baseline and re-measure after optimization.
16. Store logs per retention policy and protect internal data.

## 21. GC Log Checklist

- Identify the exact JDK and garbage collector.
- Use Unified Logging with `-Xlog`.
- Start with `gc*=info` for an overview.
- Add `gc+phases=debug` when phase breakdowns are needed.
- Add `gc+heap`, `gc+cpu`, and `safepoint` as appropriate.
- Include `time`, `uptime`, `level`, `tags`, and `PID` if needed.
- Enable rotation and control disk usage.
- Read GC ID, cause, heap before/after/capacity, and duration.
- Distinguish Young, Mixed, Concurrent, and Full GC.
- Check for evacuation failures and humongous regions.
- Track post-GC heap and Metaspace over time.
- Do not conclude a memory leak from a single log line.
- Do not apply G1 reading rules to every collector.
- Combine with JFR, heap dumps, metrics, and tracing.
- Compare under the same workload before and after changes.
- Protect logs and enforce retention policies.

## 22. Key Terminology

| Term | Meaning |
|---|---|
| GC log | Log of garbage collection activity |
| Unified Logging | HotSpot's logging system using `-Xlog` syntax |
| GC ID | Identifier for a collection and its related log lines |
| Young GC | Collection of the young generation |
| Mixed GC | G1 collection covering young and selected old regions |
| Full GC | Whole-heap collection, often with a long pause |
| Concurrent marking | Phase that marks objects while the application continues running |
| Evacuation | Moving live objects out of the collection set |
| Evacuation failure | Inability to move some objects during a collection |
| Humongous object | Object at least half the size of a G1 region |
| Heap occupancy | Amount of heap in use |
| Capacity | Current heap capacity logged |
| Metaspace | Native memory holding class metadata |
| Safepoint | Point where the JVM can safely stop all application threads |
| Pause duration | Time the application is stopped during a pause |
| Allocation rate | Volume of objects/memory allocated over time |
| Promotion | Moving long-lived objects to the old generation |
| JFR | Java Flight Recorder |
| JMC | JDK Mission Control |
| GC tuning | Adjusting collector, heap, and allocation to meet targets |

GC log analysis starts with accurately reading the collection type, cause, heap before/after, and pause duration. When investigating root causes, expand to phase breakdowns, CPU, safepoints, JFR, and heap analysis. Only change GC or heap settings once data points to a specific bottleneck, and always re-measure on an equivalent workload.

## References

- Oracle JDK 24 — Garbage Collector Implementation: https://docs.oracle.com/en/java/javase/24/gctuning/garbage-collector-implementation.html
- Oracle JDK 24 — G1 Garbage Collector: https://docs.oracle.com/en/java/javase/24/gctuning/garbage-first-g1-garbage-collector1.html
- Oracle JDK 24 — G1 GC Tuning: https://docs.oracle.com/en/java/javase/24/gctuning/garbage-first-garbage-collector-tuning.html
- Oracle JDK 24 — The java Command and -Xlog: https://docs.oracle.com/en/java/javase/24/docs/specs/man/java.html
- Oracle JDK 24 — The jcmd Command: https://docs.oracle.com/en/java/javase/24/docs/specs/man/jcmd.html
- Oracle JDK 24 — Troubleshooting Guide: https://docs.oracle.com/en/java/javase/24/troubleshoot/troubleshooting-guide.pdf
