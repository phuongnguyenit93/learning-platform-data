# GC Options in Java

GC (Garbage Collection) is the mechanism by which the JVM automatically reclaims heap memory occupied by objects that are no longer referenced. GC options are the group of JVM options used to select a garbage collector, adjust heap size, set pause targets, configure logging, and enable memory-related diagnostic features.

GC options are JVM arguments, so they must be placed before the main class name or before the `-jar` option. A Java application does not receive these options in `String[] args`. For example:

~~~bash
java -Xms256m -Xmx1g -XX:+UseG1GC -Xlog:gc* -jar service.jar
~~~

The command above sets an initial heap of 256 MiB, a maximum heap of 1 GiB, selects G1 GC, and enables GC logging. These values only illustrate the syntax; an appropriate configuration must be based on actual load, memory limits, latency requirements, and the JDK version in use.

## 1. Where Does GC Operate in JVM Memory?

Regular Java objects are allocated on the heap. When an object is no longer reachable from GC roots, the JVM can treat it as garbage and reclaim the corresponding memory.

GC roots typically include references from active thread stacks, static variables, JNI references, and certain internal JVM structures. An object still retained by any live reference chain cannot be reclaimed, even if the application is no longer actively using it.

Some memory regions commonly observed during diagnostics:

- **Heap:** where most Java objects and arrays are stored.
- **Young generation:** in generational collectors, where new objects are typically allocated.
- **Old generation:** where longer-lived objects reside after surviving multiple collection cycles.
- **Metaspace:** stores class metadata; this is not part of the regular heap.
- **Thread stacks, code cache, direct/native memory:** consume process memory but are not inside the Java heap.

GC primarily manages the heap. Increasing the heap does not automatically resolve abnormal growth in Metaspace, thread stacks, direct buffers, or native memory. When a process is memory-constrained by a container, total memory usage also includes off-heap regions.

## 2. How to Set GC Options at Startup

General syntax:

~~~bash
java [JVM options] -jar application.jar [application arguments]
~~~

Example:

~~~bash
java -Xms512m -Xmx2g -XX:+UseG1GC -jar application.jar --profile=prod
~~~

In this example:

- **-Xms512m**: initial heap is 512 MiB.
- **-Xmx2g**: maximum heap is 2 GiB.
- **-XX:+UseG1GC**: instructs the JVM to use G1.
- **--profile=prod**: application argument, passed to `main` or handled by a framework.

Distinguish between the following groups:

| Group | Example | Purpose |
|---|---|---|
| Heap sizing | -Xms, -Xmx | Set initial and maximum heap size |
| Collector selection | -XX:+UseG1GC | Choose the GC algorithm |
| GC tuning | -XX:MaxGCPauseMillis=200 | Set a GC control target |
| GC logging | -Xlog:gc* | Log GC events |
| Diagnostics | -XX:+HeapDumpOnOutOfMemoryError | Generate data for investigating memory errors |

There is no single optimal set of GC flags for every application. The same configuration can produce different results when changing the JDK, collector, heap size, allocation rate, hardware, or container limits.

## 3. Common Garbage Collectors

HotSpot provides multiple collectors with different goals. Choose a collector based on workload characteristics and operational requirements; do not choose solely by name or by a benchmark that does not resemble the real environment.

| Collector | Selection Flag | Key Characteristics | Suitable Use Cases |
|---|---|---|---|
| Serial GC | -XX:+UseSerialGC | Collects using a single GC thread; simple, has stop-the-world pauses | Small applications, small heaps, low-CPU environments |
| Parallel GC | -XX:+UseParallelGC | Uses multiple GC threads to optimize throughput; major phases have pauses | Batch jobs or workloads prioritizing total work completed |
| G1 GC | -XX:+UseG1GC | Divides heap into regions and collects by region; balances throughput and pauses | General-purpose server applications |
| ZGC | -XX:+UseZGC | Concurrent collector aimed at very short pauses | Applications requiring low latency and large heaps |
| Shenandoah | -XX:+UseShenandoahGC | Collects and relocates objects concurrently with the application | Workloads needing reduced pauses, on JDK builds that support it |
| Epsilon GC | -XX:+UseEpsilonGC | Does not reclaim memory | Benchmarks or special scenarios with bounded allocation |

### Serial GC

Serial GC performs collection work using a single GC thread. When stop-the-world phases are needed, application threads are paused. This collector has low thread-coordination overhead and can suit small programs, small heaps, or CPU-constrained environments.

~~~bash
java -XX:+UseSerialGC -jar application.jar
~~~

Do not choose Serial just because it is simple if a server application has many threads and a high allocation rate. Pauses can become long when the heap is large.

### Parallel GC

Parallel GC uses multiple threads to perform collection phases. Its typical goal is to maximize throughput—the ratio of CPU time spent on the application versus time spent on GC.

~~~bash
java -XX:+UseParallelGC -jar application.jar
~~~

This collector is suitable for batch processing, background jobs, or workloads that prioritize completing a large amount of work in less total time. It still has stop-the-world pauses; high throughput does not mean low latency.

### G1 GC

G1 divides the heap into regions instead of relying strictly on one contiguous Young area and one contiguous Old area. It can collect Young regions and select a set of Old regions during mixed collections. G1 performs some work concurrently with the application and aims for more predictable pause times.

~~~bash
java -XX:+UseG1GC -jar application.jar
~~~

On common server-class HotSpot configurations, G1 is the default collector in modern JDK versions. However, the default can depend on the JDK version, architecture, and JVM ergonomics; verify the running process instead of assuming.

A commonly used option:

~~~bash
java -XX:+UseG1GC -XX:MaxGCPauseMillis=200 -jar application.jar
~~~

**MaxGCPauseMillis** is a soft target for G1 to adjust its GC behavior. It is not a guarantee that every pause will be shorter than 200 ms. Setting the target too low can cause the collector to spend excessive resources on GC, reducing throughput or increasing memory pressure.

Do not start by manually setting a long list of flags such as `G1HeapRegionSize`, `InitiatingHeapOccupancyPercent`, or `ParallelGCThreads`. Let JVM ergonomics choose the defaults first, and only change them when GC logs and measurements point to a specific issue.

### ZGC

ZGC is a collector aimed at low latency by performing most of the heavy work concurrently with application threads. Pauses are typically short, though the collector still consumes CPU and memory to perform concurrent work.

~~~bash
java -XX:+UseZGC -jar application.jar
~~~

In JDK 21, Generational ZGC can be enabled with:

~~~bash
java -XX:+UseZGC -XX:+ZGenerational -jar application.jar
~~~

Generational ZGC separates work by object age to take advantage of the fact that many objects are short-lived. Flags and default states change across JDK versions; read the documentation for the exact version before migrating configurations between JDK 17, 21, and newer releases.

ZGC can be useful when latency requirements are strict or heaps are large, but it is not automatically faster than G1 for every workload. Compare pauses, CPU, throughput, memory usage, and tail latency under realistic load.

### Shenandoah

Shenandoah also targets low pause times by performing most collection and object relocation work concurrently with the application.

~~~bash
java -XX:+UseShenandoahGC -jar application.jar
~~~

Shenandoah availability depends on the JDK distribution, platform, and how the vendor built the JVM. If the JVM does not support the collector, the command may fail at startup. Do not assume every JDK build includes the same set of collectors.

### Epsilon GC

Epsilon is a collector that does not reclaim memory. It only allocates until the heap is exhausted; therefore, it is not a choice for typical long-running applications.

~~~bash
java -XX:+UseEpsilonGC -Xms256m -Xmx256m -jar allocation-benchmark.jar
~~~

Epsilon is useful in certain benchmarks or tests to measure allocation overhead without GC. Use it only when the workload is controlled and there is enough heap for the entire run.

### Note on CMS

Concurrent Mark Sweep (CMS) was deprecated in JDK 9 and removed from HotSpot in JDK 14. Legacy flags such as `-XX:+UseConcMarkSweepGC` are not suitable for JDK 17 or JDK 21. For legacy applications, migrate to a supported collector and re-measure behavior before deploying.

## 4. Heap Sizing and Memory Limits

Two fundamental options:

~~~bash
-Xms512m
-Xmx2g
~~~

- **-Xms** sets the initial heap size.
- **-Xmx** sets the maximum heap size.

Example configuring G1 with a 2 GiB maximum heap:

~~~bash
java -Xms512m -Xmx2g -XX:+UseG1GC -jar application.jar
~~~

A heap that is too small can cause frequent GC, allocation failures, or `OutOfMemoryError`. A heap that is too large can increase process footprint, the duration of some GC phases, and memory contention with the operating system or container.

You can size the heap as a percentage of the memory visible to the JVM using HotSpot options:

~~~bash
java -XX:InitialRAMPercentage=20 -XX:MaxRAMPercentage=60 -jar application.jar
~~~

The percentage values in the example are illustrative only. The JVM calculates them from the RAM limit it detects, which may differ from the host's physical RAM. In container environments, check the container memory limit and how the JDK detects cgroups.

Do not allocate the entire container limit to the heap. The process also needs memory for Metaspace, thread stacks, code cache, direct buffers, native libraries, and other components. If `Xmx` or `MaxRAMPercentage` is set too high, the process may be killed by the OS/container even before the heap reaches its limit.

Distinguish between:

- **Java heap usage:** the memory metric for objects managed by GC.
- **Process RSS / container memory:** the actual memory currently used by the process or container.
- **Native memory:** off-heap memory, including various JVM and library allocations.

When RSS grows while the heap remains stable, investigate native memory, thread count, direct buffers, and native libraries rather than simply increasing `Xmx`.

## 5. Pause Targets and Tuning Flags

Some tuning flags used in practice:

| Option | Meaning | Notes |
|---|---|---|
| -XX:MaxGCPauseMillis=200 | Pause target for collectors that support this flag, commonly used with G1 | Soft target, not a guaranteed SLA |
| -XX:ParallelGCThreads=N | Number of threads used for parallel GC phases | An inappropriate value can contend with the application for CPU |
| -XX:ConcGCThreads=N | Number of threads used for concurrent GC work in supported collectors | Affects CPU usage and GC processing speed |
| -XX:+DisableExplicitGC | Ignores explicit GC requests such as `System.gc()` | May affect applications or libraries that rely on those requests |
| -XX:+UseStringDeduplication | Allows G1 to deduplicate the backing storage contents of certain `String` instances | Has CPU overhead; enable only when measurements show it helps |

Do not apply these flags as a fixed formula. A value that is optimal on a multi-CPU machine may cause CPU starvation in a quota-limited container. Internal or experimental flags can also change or be removed across releases.

For G1, start with default flags and a pause target aligned with service requirements. If pauses exceed the threshold, analyze the cause from GC logs: live data volume, allocation rate, concurrent marking, evacuation failure, CPU throttling, or lack of heap headroom. Then change only one factor at a time and re-measure.

Do not call `System.gc()` periodically to deal with a memory leak. GC cannot reclaim objects that are still referenced; an explicit GC request also does not guarantee that the entire heap is collected immediately.

## 6. GC Logging with Unified Logging

Since JDK 9, the JVM uses Unified Logging. Basic option:

~~~bash
java -Xlog:gc -jar application.jar
~~~

For more detailed logging:

~~~bash
java -Xlog:gc* -jar application.jar
~~~

To write logs to a file with rotation:

~~~bash
java -Xlog:gc*:file=gc.log:time,uptime,level,tags:filecount=5,filesize=10M -jar application.jar
~~~

Meaning:

- **gc*** selects tags starting with `gc`, covering many related event groups.
- **file=gc.log** writes to a file instead of only to the console.
- **time** adds system wall-clock time.
- **uptime** adds the JVM uptime.
- **level** displays the log level.
- **tags** displays the event's tag set.
- **filecount=5** keeps at most 5 rotated log files.
- **filesize=10M** sets the size threshold for each log file.

You can combine specific tags when you want to focus on a particular group of data:

~~~bash
java -Xlog:gc+heap=debug -jar application.jar
~~~

The logging syntax has multiple components; colons separate the `what`, `output`, `decorators`, and `output options` sections. When configuring logging in scripts, check shell quoting and file paths on the target operating system.

GC logs typically show:

- Timestamps and durations of GC events.
- Heap capacity before and after certain cycles.
- Collection type and active phases.
- The reason the JVM triggered GC.
- Pause information and concurrent GC work.

Do not evaluate solely by the number of GC cycles. Look at pause times, amount of memory reclaimed, allocation rate, post-GC heap usage, and impact on application latency. High GC frequency can be normal for workloads with fast allocation and short-lived objects.

## 7. Collecting GC Information While the Application Is Running

Several JDK tools let you inspect JVM state without restarting immediately.

List Java processes:

~~~bash
jcmd -l
~~~

View active JVM flags:

~~~bash
jcmd <pid> VM.flags
jcmd <pid> VM.command_line
~~~

View heap information:

~~~bash
jcmd <pid> GC.heap_info
~~~

Monitor GC metrics periodically:

~~~bash
jstat -gcutil <pid> 1000 10
~~~

The `jstat` command samples every second for 10 iterations. Common columns:

- **S0, S1:** Survivor space utilization percentage.
- **E:** Eden utilization percentage.
- **O:** Old Generation utilization percentage.
- **M:** Metaspace utilization percentage.
- **YGC, YGCT:** count and total time of Young GC.
- **FGC, FGCT:** count and total time of Full GC.
- **GCT:** total recorded GC time.

Column names and displayed regions can vary by collector or version. Read the header printed by `jstat` itself.

JFR can record GC events over a time window:

~~~bash
jcmd <pid> JFR.start name=gc-investigation settings=profile duration=60s filename=gc-investigation.jfr
jfr summary gc-investigation.jfr
~~~

JFR helps correlate GC with allocations, thread activity, and other runtime events. When an issue only appears under load, a recording spanning the incident window is usually more valuable than a snapshot taken while the system is idle.

Diagnostic operations require appropriate permissions and can be affected by containers, the Attach mechanism, or security policies. Do not run heavy commands continuously against production processes without assessing the impact.

## 8. Heap Dump on OutOfMemoryError

You can instruct the JVM to generate a heap dump when an `OutOfMemoryError` occurs:

~~~bash
java -XX:+HeapDumpOnOutOfMemoryError -XX:HeapDumpPath=/var/log/app/heap.hprof -jar application.jar
~~~

A heap dump captures object state and references at the time of the dump. It can be opened in a heap analysis tool to find:

- Which classes have a large number of objects.
- Which objects hold a large amount of retained heap.
- Which reference chains keep objects alive.
- Which collections, caches, or listeners are growing uncontrollably.

Heap dumps can be very large, consume disk space, and contain sensitive data. Create the directory in advance, grant proper write permissions to the user running the application, plan disk capacity, and protect the file. If the JVM is killed by the OS or container OOM killer before throwing `OutOfMemoryError` in Java, this option may not be triggered.

A heap dump does not replace GC logs. GC logs show behavior over time; a heap dump provides a snapshot for analyzing the reference graph.

## 9. GC Selection and Tuning Workflow

A practical workflow should be based on operational goals:

1. **Define requirements:** throughput, average latency, p95/p99, maximum pause time, memory limits, and peak load.
2. **Record the baseline:** JDK distribution/version, collector, `Xms`/`Xmx`, CPU quota, container memory, and current GC logs.
3. **Measure a representative workload:** use data, concurrency, and run duration close to production.
4. **Analyze:** compare pauses, allocation rate, post-GC live set, CPU, RSS, and tail latency.
5. **Form a hypothesis:** heap too small, long-lived objects, high allocation rate, GC starved of CPU, or unsuitable collector.
6. **Change one factor at a time:** one flag or one setting per iteration so you know what caused the difference.
7. **Re-run the same workload:** compare the same metrics, not just a single GC event.
8. **Roll out in a controlled manner:** monitor after rollout and keep the ability to revert to a known configuration.

Some symptoms and investigation directions:

| Symptom | Investigation Direction |
|---|---|
| Frequent Young GC | Allocation rate, temporary objects, heap size, and processing speed |
| Old Gen grows after each cycle | Long-lived objects, caches, collections retaining references, heap dump |
| Long pauses | GC logs, live object volume, evacuation, CPU quota, and collector |
| Repeated Full GC | Live set, allocation failure, heap configuration, and cause logs |
| RSS grows while heap does not | Metaspace, thread stacks, direct buffers, native allocations |
| High CPU during GC | GC frequency, collector, allocation rate, GC thread count, and CPU limit |

You cannot conclude a memory leak just because the heap grows over a period of time. The application may be loading valid data or warming up a cache. Observe across multiple GC cycles and determine whether the live set continues to grow.

## 10. Hands-on Example with Java 17+

The program below creates many short-lived byte arrays to generate allocation pressure on the heap. Arrays are only held for the current batch, so older batches can be reclaimed as the loop continues. The program does not call `System.gc()`.

Create `GcOptionsDemo.java`:

~~~java
public class GcOptionsDemo {
    private static volatile long sink;

    public static void main(String[] args) {
        long checksum = 0;

        for (int round = 0; round < 256; round++) {
            byte[][] batch = new byte[32][];

            for (int i = 0; i < batch.length; i++) {
                byte[] data = new byte[64 * 1024];
                data[0] = (byte) i;
                data[data.length - 1] = (byte) round;
                batch[i] = data;

                checksum += data[0] + data[data.length - 1];
            }
        }

        sink = checksum;
        System.out.println("Completed allocation workload.");
    }
}
~~~

Compile:

~~~bash
javac GcOptionsDemo.java
~~~

Run with G1, a 64 MiB maximum heap, and GC logging:

~~~bash
java -Xms32m -Xmx64m -XX:+UseG1GC -Xlog:gc*:file=gc.log:time,uptime,level,tags GcOptionsDemo
~~~

Program output:

~~~text
Completed allocation workload.
~~~

The `gc.log` file contains the generated GC events; the line count, timings, and details depend on the JDK, host machine, and runtime state. To try Parallel GC, run the same program with:

~~~bash
java -Xms32m -Xmx64m -XX:+UseParallelGC -Xlog:gc*:file=parallel-gc.log:time,uptime,level,tags GcOptionsDemo
~~~

You can compare the two logs by pause times, collection count, post-GC heap usage, and completion time. A single run is not enough to conclude which collector is better; repeat multiple times under the same load conditions.

## 11. Configuration Mistakes and Operational Notes

**Placing JVM options after the JAR name**

~~~bash
java -jar application.jar -XX:+UseG1GC
~~~

In the command above, `-XX:+UseG1GC` is passed to the application. Place the option before `-jar`:

~~~bash
java -XX:+UseG1GC -jar application.jar
~~~

**Using a collector not supported by the JVM**

A JDK distribution might not include Shenandoah or an optional collector. Test on the exact binary to be deployed and check JVM startup messages.

**Selecting multiple collectors at once**

Each process needs one appropriate collector. Do not arbitrarily combine flags for Serial, Parallel, G1, ZGC, or Shenandoah. Choose one collector and verify with `VM.flags`.

**Treating MaxGCPauseMillis as a hard limit**

It is a control target, not a guarantee that pauses will always stay below the configured value. Actual latency also depends on live set, CPU, allocation rate, and workload.

**Increasing Xmx to fix a memory leak**

If objects are no longer needed but are still referenced, increasing the heap only delays the problem. Use GC logs, class histograms, and heap dumps to find the reference path.

**Using flags from documentation for a different JDK version**

A flag's status, name, or behavior can change across JDK releases. Read the documentation for the corresponding version and test on the same JDK distribution as the deployment environment.

**Enabling GC logging without managing disk space**

GC logs can grow continuously. Use rotation, size limits, retention policies, and appropriate permissions.

**Assuming the heap is the entire process memory**

The JVM also uses Metaspace, stacks, code cache, and native memory. Setting `Xmx` close to the memory limit can cause the container to be killed.

## 12. Selection Guidelines

- Start with the default collector of the JDK in use and measure a baseline.
- G1 is a good general-purpose choice for many server applications.
- Parallel is suitable when throughput matters more than short pauses.
- Serial is suitable for small programs or low-CPU environments.
- ZGC or Shenandoah are worth trying when low latency is required and the JDK build supports them.
- Epsilon is only for special scenarios that do not need memory reclamation.
- Change tuning flags only when metrics demonstrate an issue.
- Monitor heap, native memory, CPU, pauses, and latency together.

GC options determine how the JVM reclaims the heap and consumes resources to do so. A good configuration meets SLOs under realistic workloads, has sufficient logging for investigation, and stays within the CPU and memory limits of the deployment environment.
