# Garbage Collection Configuration in Java

**GC configuration** is the process of selecting a garbage collector, setting heap limits, and tuning the JVM's memory collection behavior. Proper configuration helps balance three goals: latency, throughput, and memory footprint.

The HotSpot JVM provides multiple collectors such as Serial, Parallel, G1, ZGC, and Shenandoah. Each collector has a different design and different goals. A configuration that works well for a batch job needing high throughput may not be suitable for an API requiring stable response times. Therefore, GC configuration must be driven by application requirements and measurements on a representative workload.

This article covers choosing a collector, configuring the heap, understanding key GC flags, enabling GC logging, tuning G1 and ZGC, configuring in containers, inspecting active flags, and practicing with Java 17+.

## 1. Goals of GC configuration

GC configuration typically balances three goals:

| Goal | Meaning | Example requirement |
|---|---|---|
| Throughput | Percentage of time the JVM spends on application work rather than GC | Batch job processing many records per second |
| Latency | Time the application must wait due to GC pauses | API requiring stable P95/P99 response times |
| Footprint | Amount of RAM the JVM consumes | Service running in a container with a small memory limit |

These goals can conflict:

- Reducing pauses often requires the collector to do more concurrent work, which can increase CPU usage and reduce throughput.
- Increasing the heap can reduce GC frequency but increases the memory footprint.
- Decreasing the heap can save RAM but causes GC to run more frequently.
- Setting the pause target too low can cause the JVM to collect more frequently and reduce throughput.

There is no single optimal flag set for every application. Define your goals using SLOs and metrics such as throughput, P95/P99 latency, GC pauses, CPU usage, post-GC heap size, and memory limits.

## 2. Ergonomics: how does the JVM choose defaults automatically?

HotSpot uses **ergonomics** to automatically select the collector, heap size, and number of GC threads based on the execution environment.

In JDK 26, G1 is the default collector on server-class machines; Serial may be selected on non-server-class environments. The JVM determines whether a machine is server-class based on available CPU and memory. The JVM also dynamically adjusts many parameters at runtime.

Some automatic decisions include:

- Default collector based on the environment class.
- Initial/minimum and maximum heap sizes based on available memory.
- Number of GC threads based on CPU and heap size.
- Young generation size based on allocation behavior.
- Certain thresholds for starting G1 concurrent marking.
- Expanding or shrinking the heap to balance throughput and footprint.

The JVM usually tunes itself better than a set of flags copied from another machine. Start with the defaults, measure the workload, and only change parameters directly related to observed issues.

### Checking the selected collector

You can run:

~~~bash
java -XX:+PrintCommandLineFlags -version
~~~

Or inspect flags after the JVM has started:

~~~bash
jcmd 2125 VM.flags
~~~

Replace `2125` with the process PID. You can view additional JVM information with:

~~~bash
jcmd 2125 VM.info
~~~

GC bean names can also be inspected via JMX or a Java program using `GarbageCollectorMXBean`. Do not rely on a single configuration flag alone if the application runs in a different environment or JDK.

## 3. Choosing a garbage collector

### Serial GC

Enable with:

~~~bash
-XX:+UseSerialGC
~~~

Serial GC uses a single thread to perform major GC work. It is suitable for small applications, few threads, small heaps, or CPU-constrained environments.

Advantages:

- Simple configuration.
- Low overhead from multiple GC worker threads.
- Can be suitable for desktop applications, small tools, or light workloads.

Limitations:

- GC pauses can be long when the heap or live set is large.
- Does not leverage multiple CPUs to speed up collection.
- Generally unsuitable for multi-threaded servers with strict latency requirements.

### Parallel GC

Enable with:

~~~bash
-XX:+UseParallelGC
~~~

Parallel GC is also known as the throughput collector. It uses multiple threads to perform collections, making it especially suitable for throughput-oriented workloads that can tolerate longer pauses.

Advantages:

- Optimized for throughput.
- Can utilize multiple CPUs to shorten collection times.
- Suitable for batch processing and compute-heavy batch workloads.

Limitations:

- Major collections still involve stop-the-world pauses.
- Pauses can be longer than with concurrent collectors.
- Can consume significant CPU while GC is running.

### G1 GC

Enable explicitly with:

~~~bash
-XX:+UseG1GC
~~~

G1 is the default collector on server-class machines in JDK 26. It divides the heap into regions, collects regions in a collection set, and performs part of its work concurrently.

Advantages:

- Balances throughput and latency.
- Adjusts the young generation to meet the pause-time goal.
- Can reclaim old regions incrementally through mixed collections.
- Suitable for server applications and relatively large heaps.

Limitations:

- Incurs overhead for remembered sets, marking, and concurrent work.
- Does not guarantee that every pause will stay below the pause target.
- Certain allocation patterns or object graphs can still trigger a Full GC.

### ZGC

Enable with:

~~~bash
-XX:+UseZGC
~~~

ZGC prioritizes low latency and performs most of its expensive work concurrently with application threads. It is suitable for applications requiring very short pauses or large heaps.

Since JDK 24, ZGC runs in generational mode by default, and the `-XX:+ZGenerational` flag has been removed. Do not copy the `ZGenerational` flag from older JDK documentation.

ZGC is designed to be self-tuning. The most important parameter is usually `-Xmx`, because the collector needs enough heap to hold the live set plus headroom for allocations while GC is running.

### Shenandoah GC

Enable on supported distributions/platforms:

~~~bash
-XX:+UseShenandoahGC
~~~

Shenandoah is a concurrent collector aimed at low pauses that do not scale linearly with heap size. Availability and specific options depend on the JDK distribution and platform. Check your vendor's documentation before using it.

### Quick selection table

| Collector | Primary goal | When to try |
|---|---|---|
| Serial | Simplicity, small footprint | Small applications, limited CPU |
| Parallel | High throughput | Batch jobs, bulk processing |
| G1 | Balanced throughput/latency | Server applications, common starting point |
| ZGC | Very low latency | Latency-sensitive services, large heaps |
| Shenandoah | Low latency | Workloads needing low pauses on supported JDK builds |

Select only one primary collector per JVM. Do not pass conflicting collector flags at the same time.

## 4. Configuring heap size

The two most fundamental flags:

| Flag | Meaning |
|---|---|
| -Xms | Initial/minimum heap size |
| -Xmx | Maximum heap size |

Example:

~~~bash
java -Xms512m -Xmx2g -jar app.jar
~~~

The JVM starts with a 512 MB heap and can expand up to 2 GB.

In server deployments, `Xms` and `Xmx` are sometimes set to the same value to avoid heap resizing at runtime:

~~~bash
java -Xms2g -Xmx2g -jar app.jar
~~~

This approach can increase the initial memory footprint. Only use it when you understand your memory budget and have a latency-stability reason to do so.

### Do not set Xmx to the entire machine RAM

The Java heap is only part of the process memory. The JVM also needs memory for:

- Metaspace and class metadata.
- Thread stacks.
- Direct buffers and native allocations.
- JIT code cache.
- GC metadata and internal structures.
- Native libraries and memory-mapped regions.

If a container has a 2 GB limit, do not set `Xmx=2g` by default. The heap must leave headroom for native memory regions and any sidecar or auxiliary processes in the same container.

### Using MaxRAMPercentage

HotSpot can calculate the maximum heap based on available memory:

~~~bash
java -XX:MaxRAMPercentage=60 -jar app.jar
~~~

In JDK 26, the default for `-XX:MaxRAMPercentage` is 25%. The value `60` in the example is a percentage of the maximum memory detected by the JVM, which is not always the physical host RAM.

You can also set the initial heap by percentage:

~~~bash
-XX:InitialRAMPercentage=10
~~~

When configuring containers, measure peak RSS, native memory, metaspace, and thread count before choosing a percentage. Do not combine `Xmx` with `MaxRAMPercentage` expecting both to take effect together; one configuration can override the other's sizing behavior.

## 5. Configuring pause-time and throughput goals

### MaxGCPauseMillis

Flag:

~~~bash
-XX:MaxGCPauseMillis=200
~~~

Sets the desired maximum pause target to 200 ms. This is a **soft goal**, not a hard limit or SLA guarantee. The JVM adjusts the heap and GC policy to try to meet the target.

In JDK 26, this pause-time target is supported by G1 and Parallel. For G1, the default value is 200 ms.

Lowering the target can shrink the young generation, cause GC to run more frequently, and reduce throughput. If set too low, the JVM may struggle to meet the goal under real workloads.

### GCTimeRatio

Flag:

~~~bash
-XX:GCTimeRatio=19
~~~

Sets the target ratio of GC time to application time:

\[
\text{GC fraction} = \frac{1}{1+\text{GCTimeRatio}}
\]

With a value of 19:

\[
\frac{1}{1+19}=0.05=5\%
\]

This is a goal for GC time according to the collector's policy, not a pause-percentile measurement. Defaults and exact behavior depend on the collector.

### Footprint

The maximum heap is capped by `Xmx`. The JVM tries to balance throughput and pause goals before shrinking the footprint. If the heap is too small to hold the live set plus allocation headroom, GC will run frequently and performance can degrade severely.

## 6. Configuring G1 GC

G1 is usually the first choice for server applications. Oracle documentation recommends starting with the defaults and only adjusting the pause target or `Xmx` when metrics show it is necessary.

Starting configuration:

~~~bash
java -XX:+UseG1GC -Xms1g -Xmx2g -XX:MaxGCPauseMillis=200 -jar app.jar
~~~

### Adaptive IHOP

G1 uses the Initiating Heap Occupancy Percent (IHOP) to decide when to start concurrent marking.

Related flags:

~~~bash
-XX:InitiatingHeapOccupancyPercent=45
-XX:+G1UseAdaptiveIHOP
~~~

Adaptive IHOP is enabled by default. G1 observes marking duration and old-generation allocation rates to tune the threshold automatically. The 45% value is used during initial cycles before enough data is collected.

Only disable adaptive IHOP if logs show the default prediction is unsuitable and you have evidence for a manual threshold:

~~~bash
-XX:-G1UseAdaptiveIHOP -XX:InitiatingHeapOccupancyPercent=35
~~~

Do not hardcode IHOP just because heap usage hits a certain percentage in a single observation.

### G1ReservePercent

Flag:

~~~bash
-XX:G1ReservePercent=10
~~~

G1 reserves a portion of the heap to reduce the risk of promotion failure during evacuation. The default is 10%. Increasing the reserve reduces the heap available for application objects, so account for it in your heap budget.

### G1HeapRegionSize

Flag:

~~~bash
-XX:G1HeapRegionSize=16m
~~~

G1 chooses the region size automatically based on heap size, typically aiming for around 2,048 regions. Only set it manually when GC logs show issues with humongous objects or region sizing. The value must be a power of 2 within the JDK-supported range.

### Avoid fixing the young generation size with G1

Flags such as `-Xmn`, `-XX:NewSize`, `-XX:MaxNewSize`, or generation ratio settings can prevent G1 from dynamically resizing the young generation. Dynamic young generation sizing is G1's primary mechanism for meeting its pause-time goal.

Do not fix the young generation size if you want G1 to balance pause time and throughput automatically.

### Mixed collections

After concurrent marking, G1 can reclaim old regions across multiple mixed collections. Several flags influence this phase:

| Flag | Meaning |
|---|---|
| -XX:G1MixedGCCountTarget | Target number of mixed collections in a phase |
| -XX:G1HeapWastePercent | Allowable heap waste before stopping further old-region reclamation |
| -XX:G1MixedGCLiveThresholdPercent | Live data threshold for selecting an old region |

Only tune these flags when GC logs point to a specific issue in the space-reclamation phase.

## 7. Configuring Parallel GC

Parallel GC is suitable when throughput matters more than pause latency.

Example:

~~~bash
java -XX:+UseParallelGC -Xms2g -Xmx4g -XX:GCTimeRatio=19 -jar batch.jar
~~~

You can set the number of GC worker threads:

~~~bash
-XX:ParallelGCThreads=4
~~~

Setting too many threads can cause GC to compete with application threads for CPU. Setting too few can lengthen collections. By default, the JVM chooses the thread count based on available CPUs and heap size.

Parallel GC supports a pause-time goal via:

~~~bash
-XX:MaxGCPauseMillis=500
~~~

The 500 ms value is only a hint to the collector. When a pause goal is set, the JVM may adjust the heap and other parameters, which can reduce throughput.

### When to choose Parallel?

- Batch jobs that need to complete as much work per second as possible.
- Longer pauses are acceptable.
- Sufficient CPU is available to run multiple GC workers.
- Throughput is more important than tail latency.

Do not choose Parallel simply because it uses more GC threads. Always benchmark end-to-end with the same workload.

## 8. Configuring ZGC

ZGC targets low pauses and tunes many parameters automatically. A starting configuration is usually simple:

~~~bash
java -XX:+UseZGC -Xms2g -Xmx8g -jar latency-service.jar
~~~

### Xmx and allocation headroom

Because ZGC performs much of its work concurrently, the heap must have enough space for:

- The application's live set.
- Allocations occurring while GC is running.
- Allocation spikes.
- A buffer for workload variations.

If the heap nears exhaustion before a concurrent cycle reclaims enough memory, application threads may experience allocation stalls. Increasing `Xmx` can provide headroom, provided it fits within the process/container memory budget.

### SoftMaxHeapSize

Flag:

~~~bash
-XX:+UseZGC -Xmx8g -XX:SoftMaxHeapSize=6g
~~~

`SoftMaxHeapSize` is a soft limit for sizing heuristics. ZGC tries to keep the heap below 6 GB, while still allowing it to grow up to `Xmx=8` GB if needed to avoid stalling the application.

`SoftMaxHeapSize` does not replace `Xmx`. `Xmx` remains the hard limit.

### Do not re-enable ZGenerational

Since JDK 24, ZGC is generational by default. The `-XX:+ZGenerational` flag has been removed. Modern JDK configurations only need:

~~~bash
-XX:+UseZGC
~~~

### When to try ZGC?

- APIs or interactive services with very tight latency SLOs.
- Large heaps where GC pauses are the bottleneck.
- Sufficient CPU headroom is available for concurrent GC.
- Measurements confirm that GC pauses are causing latency spikes.

ZGC can consume more CPU than throughput-oriented collectors. Compare CPU usage, throughput, and memory headroom—not just pause times.

## 9. Configuring Shenandoah

On JDK distributions that support Shenandoah:

~~~bash
java -XX:+UseShenandoahGC -Xms2g -Xmx8g -jar app.jar
~~~

Shenandoah is a concurrent low-pause collector. Some JDK builds allow selecting specific modes or heuristics. Available flags and support status depend on the vendor, platform, and release.

Verify options on the exact target runtime:

~~~bash
java -XX:+PrintFlagsFinal -version
~~~

Do not copy Shenandoah flags from an OpenJDK build to Oracle JDK or another vendor without verifying support.

## 10. GC logging is an essential part of tuning

Before changing flags, you need to know what GC is doing. Use unified logging:

~~~bash
java -Xlog:gc*:file=logs/gc-%p.log:time,uptime,level,tags:filecount=5,filesize=20M -jar app.jar
~~~

This configuration:

- Logs all `gc*` tags.
- Includes timestamp and uptime.
- Records log level and tags.
- Rotates up to 5 files.
- Targets 20 MB per file.

For more detailed G1 diagnostics:

~~~bash
-Xlog:gc*=debug
~~~

To view heap region information:

~~~bash
-Xlog:gc+heap=info
~~~

To view GC phases:

~~~bash
-Xlog:gc+phases=debug
~~~

List available tags and levels:

~~~bash
java -Xlog:help
~~~

Do not leave overly verbose debug logging enabled long-term without evaluating disk space and overhead.

## 11. Inspecting active GC flags

Flags passed on the command line do not always reflect the full runtime state. The JVM applies ergonomic defaults, and some flags may be modified by launchers, environment variables, or containers.

### Print command-line flags

~~~bash
java -XX:+PrintCommandLineFlags -version
~~~

### Print all flags and their final values

~~~bash
java -XX:+PrintFlagsFinal -version
~~~

You can filter on Linux:

~~~bash
java -XX:+PrintFlagsFinal -version 2>&1 | grep -E "UseG1GC|UseParallelGC|UseZGC|MaxHeapSize|InitialHeapSize|MaxGCPauseMillis"
~~~

In PowerShell:

~~~powershell
java -XX:+PrintFlagsFinal -version 2>&1 | Select-String "UseG1GC|UseParallelGC|UseZGC|MaxHeapSize|InitialHeapSize|MaxGCPauseMillis"
~~~

### Inspect a running process

~~~bash
jcmd 2125 VM.flags
jcmd 2125 VM.info
jcmd 2125 GC.heap_info
~~~

Use the actual JVM PID. `VM.flags` shows runtime flags; `VM.info` provides an overview; `GC.heap_info` displays heap information.

### Inspect a specific option

You can run:

~~~bash
java -XX:+PrintFlagsFinal -version
~~~

Search for the flag of interest and check its final value. Some diagnostic or experimental options require unlocking and are not recommended for standard production configurations.

## 12. Configuring GC in Docker and Kubernetes

On Linux, HotSpot has container support enabled by default in JDK 26. The JVM can read container memory and CPU limits to size the heap and thread pools. The `-XX:+UseContainerSupport` flag enables this feature and is on by default on Linux. It can be disabled with `-XX:-UseContainerSupport`, though you generally should not disable it if the application relies on container resource limits.

Example for a container with a 2 GiB memory limit:

~~~bash
java -XX:MaxRAMPercentage=60 -jar app.jar
~~~

With `MaxRAMPercentage` set to 60, ergonomic maximum heap sizing is calculated from the available memory detected by the JVM. This is only an example; the remaining memory must be sufficient for metaspace, native memory, thread stacks, direct buffers, and other components.

### Container CPU limits

The JVM uses the available CPU count to size GC threads and thread pools. To override the CPU count seen by the JVM:

~~~bash
-XX:ActiveProcessorCount=4
~~~

This flag affects the CPU count the JVM uses for heuristics, even when container support is disabled.

### Verifying container awareness

You can enable diagnostic logging:

~~~bash
-Xlog:os+container=trace
~~~

Use this log to verify how the JVM detects memory and CPU limits. Do not assume the JVM always sees the entire host's resources.

### Planning a memory budget

Example for a container with a 2 GiB memory limit:

| Component | Illustrative budget |
|---|---:|
| Java heap maximum | 1.2 GiB |
| Metaspace | 160 MiB |
| Direct/native buffers | 200 MiB |
| Thread stacks | 160 MiB |
| Code cache and JVM internals | 100 MiB |
| Headroom | Remainder |

These numbers only illustrate how to plan a budget; they are not defaults. Measure actual RSS and native memory before finalizing `Xmx`.

## 13. Common GC flags

| Flag | Purpose | Notes |
|---|---|---|
| -Xms | Initial/minimum heap | Can increase initial footprint |
| -Xmx | Maximum heap | Must leave room for native memory |
| -XX:MaxRAMPercentage | Calculate max heap from available memory | JDK 26 default is 25% |
| -XX:MaxGCPauseMillis | Pause target | Soft goal, not a guarantee |
| -XX:GCTimeRatio | Throughput goal | Larger values mean a smaller target GC time fraction |
| -XX:ParallelGCThreads | Stop-the-world GC worker count | Setting too high can cause CPU contention |
| -XX:ConcGCThreads | Concurrent GC worker count | Affects application CPU usage |
| -XX:+DisableExplicitGC | Ignore `System.gc()` requests | Use only after verifying impact |
| -XX:+UseStringDeduplication | Deduplicate String backing data with G1 | Adds processing overhead |
| -XX:MaxMetaspaceSize | Limit native memory for class metadata | Not a heap limit |
| -XX:ActiveProcessorCount | Override CPU count used by JVM | Useful when partitioning CPUs |

There is no reason to put all of these flags in a single launch command. Choose only the options needed for your specific collector and goals.

## 14. Configurations to avoid

### Fixing too many G1 parameters

If you hardcode `Xmn`, `SurvivorRatio`, and generation sizes, G1 loses part of its ability to dynamically resize the young generation to meet its pause target.

### Setting the pause target too low

An overly low pause target can force GC to run more frequently and reduce throughput. If the target is unachievable for the actual workload, lowering the target will not fix the root cause.

### Setting Xmx equal to the container memory limit

The heap is not the entire process memory. The JVM can be OOM-killed by the container before the Java heap reaches `Xmx` if native memory and other regions consume the rest.

### Disabling explicit GC without investigating the cause

`-XX:+DisableExplicitGC` ignores `System.gc()` calls from the application or libraries. If the system relies on explicit GC for a specific task, behavior can change. Check the GC cause and codebase before enabling it.

### Copying flags from older JDKs

Some options change or become deprecated, obsolete, or removed. For example, `-XX:+ZGenerational` is no longer valid in JDK 24+ because Generational ZGC is now the default mode. Always check the documentation for your exact JDK version.

## 15. Java 17+ practice: checking GC configuration via MXBeans

The following example checks whether `GarbageCollectorMXBean` instances are present, whether the maximum heap size is positive, and whether the G1 flag was passed on the command line.

File `GcConfigCheck.java`:

~~~java
import java.lang.management.GarbageCollectorMXBean;
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryMXBean;
import java.lang.management.RuntimeMXBean;
import java.util.List;

public final class GcConfigCheck {
    public static void main(String[] args) {
        List<GarbageCollectorMXBean> collectors =
                ManagementFactory.getGarbageCollectorMXBeans();

        MemoryMXBean memory =
                ManagementFactory.getMemoryMXBean();

        RuntimeMXBean runtime =
                ManagementFactory.getRuntimeMXBean();

        boolean gcBeansPresent = !collectors.isEmpty();
        boolean maxHeapPositive =
                memory.getHeapMemoryUsage().getMax() > 0;
        boolean g1FlagPresent =
                runtime.getInputArguments().contains("-XX:+UseG1GC");

        System.out.println("GC_BEANS_PRESENT=" + gcBeansPresent);
        System.out.println("MAX_HEAP_POSITIVE=" + maxHeapPositive);
        System.out.println("G1_FLAG_PRESENT=" + g1FlagPresent);
    }
}
~~~

Compile:

~~~bash
javac --release 17 GcConfigCheck.java
~~~

Run with G1 and a 256 MB maximum heap:

~~~bash
java -XX:+UseG1GC -Xmx256m GcConfigCheck
~~~

Exact stdout on HotSpot:

~~~text
GC_BEANS_PRESENT=true
MAX_HEAP_POSITIVE=true
G1_FLAG_PRESENT=true
~~~

This program checks the flags passed on the command line rather than inferring the active collector from the flag name alone. For full runtime verification, combine `jcmd PID VM.flags`, `jcmd PID VM.info`, and GC bean information.

## 16. Safe GC tuning workflow

1. Define the primary goal: throughput, latency, or footprint.
2. Record JDK vendor/version, collector, heap size, CPU, and container limits.
3. Run with the default collector and near-default settings.
4. Enable GC logging with log rotation.
5. Collect JFR if you need to analyze GC phases, allocations, or threads.
6. Measure a baseline using a representative workload over a sufficiently long duration.
7. Calculate total pause time, max/P95/P99 pause, GC time, throughput, and RSS.
8. Inspect heap usage before/after GC and the live set size.
9. If the heap is too small, evaluate `Xmx` and memory headroom.
10. If pauses are long, identify the slow collector phase before changing flags.
11. If throughput is low, inspect GC CPU usage, allocation rate, and collector overhead.
12. Change only one group of flags at a time.
13. Re-run with the same workload, warmup, and measurement duration.
14. Compare against the baseline and verify memory limits.
15. Document the rationale, flags, results, and test conditions.

Do not optimize based on a single Full GC or a single log line. Look for trends across multiple runs and ensure workloads are comparable.

## 17. Troubleshooting GC configuration

| Symptom | Possible cause | Resolution |
|---|---|---|
| Unrecognized flag | Flag removed or unavailable on vendor/JDK | Check `PrintFlagsFinal` and release docs |
| JVM reports conflicting collector options | Multiple collector flags passed together | Keep only one collector |
| Heap exceeds container limit | `Xmx`/`MaxRAMPercentage` leaves no native headroom | Recalculate memory budget and check RSS |
| JVM does not detect container CPU | Container support or cgroup detection behaves unexpectedly | Enable `os+container` logging |
| Long G1 pauses | Specific phase is slow, heap pressure, or large live set | Inspect `gc*=debug`, JFR, and GC phases |
| G1 GC runs too frequently | Young generation constrained or high allocation rate | Check `Xmn`/`MaxNewSize` and allocation profile |
| G1 Full GC | Evacuation failure, humongous allocations, or old-gen pressure | Check GC logs, heap headroom, and object retention |
| ZGC allocation stall | Insufficient headroom while concurrent GC runs | Evaluate `Xmx`, allocation rate, and live set |
| Low Parallel throughput | GC consumes too much CPU or pause target is too tight | Check `GCTimeRatio`, GC threads, and workload |
| RSS exceeds Xmx | Native memory, metaspace, stacks, or direct buffers | Use NMT and OS metrics |
| GC log grows too fast | Logging too verbose or rotation not configured | Limit level, `filecount`, and `filesize` |
| Behavior changes after JDK upgrade | Ergonomics, defaults, or options changed | Compare `PrintFlagsFinal` and release notes |

## 18. Key takeaways

- GC configuration balances throughput, latency, and memory footprint.
- Start with the default collector and measure before tuning.
- G1 is the default collector on server-class machines in JDK 26.
- Serial suits small environments; Parallel prioritizes throughput; G1 balances both; ZGC and Shenandoah target low pauses.
- `Xms` sets initial/minimum heap; `Xmx` sets maximum heap.
- The Java heap is not all of process memory; leave room for native memory, metaspace, stacks, and direct buffers.
- `MaxGCPauseMillis` is a soft goal, not a hard guarantee.
- `GCTimeRatio` sets a target ratio of GC time to application time.
- G1 adaptive IHOP is enabled by default; avoid fixing the young generation if you want G1 to auto-tune pauses.
- ZGC from JDK 24 onward is generational by default; do not use the removed `ZGenerational` flag.
- `MaxRAMPercentage` defaults to 25% in JDK 26; in containers, verify the memory limit detected by the JVM.
- `ActiveProcessorCount` can override the CPU count the JVM uses for sizing GC and thread pools.
- GC logs and JFR are the foundation for identifying which phase or behavior needs tuning.
- Change one group of flags at a time, run the same workload, and compare against the baseline.

## Official references

- [HotSpot VM Garbage Collection Tuning Guide — JDK 26](https://docs.oracle.com/en/java/javase/26/gctuning/)
- [Ergonomics — JDK 26](https://docs.oracle.com/en/java/javase/26/gctuning/ergonomics.html)
- [Available Collectors — JDK 26](https://docs.oracle.com/en/java/javase/26/gctuning/available-collectors.html)
- [G1 Garbage Collector — JDK 26](https://docs.oracle.com/en/java/javase/26/gctuning/garbage-first-g1-garbage-collector1.html)
- [G1 Tuning — JDK 26](https://docs.oracle.com/en/java/javase/26/gctuning/garbage-first-garbage-collector-tuning.html)
- [Parallel Collector — JDK 26](https://docs.oracle.com/en/java/javase/26/gctuning/parallel-collector1.html)
- [The Z Garbage Collector — JDK 26](https://docs.oracle.com/en/java/javase/26/gctuning/z-garbage-collector.html)
- [The java Command — JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/java.html)