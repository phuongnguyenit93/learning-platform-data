# jstat and Runtime Metrics in Java

## Objectives

After this lesson, you will be able to use jstat to sample statistics from a running HotSpot JVM; choose the right metric group for garbage collection, heap, metaspace, class loading, and the JIT compiler; read capacity, utilization, and cumulative counter columns; distinguish a point-in-time snapshot from trends over time; detect signs of GC pressure or memory growth; collect metrics using Java Management Extensions (JMX) and Platform MXBeans; combine jstat with jcmd, Java Flight Recorder (JFR), JDK Mission Control (JMC), and GC logs; and establish a repeatable runtime monitoring workflow.

## 1. What is jstat?

**jstat** (Java Virtual Machine Statistics Monitoring Tool) is a command-line tool in the JDK used to read performance counters exposed by the Java HotSpot VM. It gathers statistics on resources and runtime activity of a running JVM, and is especially useful when investigating heap sizing, garbage collection, class loading, and JIT compilation.

jstat can help answer:

- How heavily are Eden, survivor, and the old generation being utilized?
- How are the young GC and full GC counts increasing?
- How much total time has the JVM spent on GC?
- Are metaspace and compressed class space growing?
- How many classes has the JVM loaded/unloaded?
- How many methods has the JIT compiler compiled?
- Did a GC cycle or heap change occur between two samples?

jstat reads instrumentation built into HotSpot. According to the Java SE 26 Troubleshooting Guide, you do not need to start the JVM with a special option to enable this instrumentation; it is enabled by default. However, instrumentation is not accessible on a FAT32 filesystem.

jstat is primarily a statistical observation tool. It does not fully show which objects are retaining heap, which methods are allocating, which threads are causing latency, or which requests are slow. To find the root cause, you typically need to combine it with GC logs, JFR/JMC, JMX, thread dumps, heap dumps, or OS-level metrics.

## 2. Support Status and Version Differences

The Java SE 26 Troubleshooting Guide still includes a section describing jstat and how to use it. That page links to the jstat command documentation in the Tool Specifications; the link currently redirects to the Java SE 17 documentation. That command reference marks jstat as **experimental and unsupported**, and warns that options and functionality may change or be removed in future releases.

This has two practical implications:

1. jstat remains useful for inspecting existing systems and quickly observing the HotSpot runtime when the installed JDK provides the tool.
2. You should not build new monitoring systems with a hard dependency on a specific set of jstat columns or output format. Verify the actual options with `jstat -options` on the target JDK, and prefer JMX/JFR/metrics with a stable contract for long-term integration.

Do not confuse jstat with jcmd. jstat displays statistical tables based on performance counters. jcmd sends diagnostic commands to the JVM—for example, viewing heap info, printing thread dumps, or controlling JFR. The two tools complement each other.

## 3. Basic Syntax

General syntax:

~~~bash
jstat [generalOption]
jstat outputOption [-t] [-h lines] [-J javaOption] vmid [interval[s|ms] [count]]
~~~

Where:

- generalOption: help option or an option to list statistics groups.
- outputOption: a metric group, such as -gcutil, -gc, -class, or -compiler.
- -t: adds a Timestamp column representing the elapsed time in seconds since the target JVM started.
- -h n: repeats the header row after every n samples.
- -J javaOption: passes an option to the JVM running the jstat tool itself, not the target JVM.
- vmid: Virtual Machine Identifier used to identify the JVM to monitor.
- interval: sampling interval; defaults to milliseconds, or can be specified with `s` or `ms`.
- count: number of samples to print; if omitted, jstat continues sampling until the JVM exits or the user stops the command.

Example taking 10 samples, 1 second apart:

~~~bash
jstat -gcutil <PID> 1000 10
~~~

You can write the interval with an explicit unit:

~~~bash
jstat -gcutil <PID> 1s 10
~~~

According to the documentation, `interval` and `count` must be positive integers. If `count` is omitted, the command runs continuously; press Ctrl+C to stop.

### Viewing Help and Listing Options

~~~bash
jstat -help
jstat -options
~~~

`jstat -options` lists the stat options supported by the running jstat binary. Available options may vary by JDK release, vendor, and platform. Always verify on the target machine before using a command from older documentation.

Common groups include:

- -class: class loader statistics.
- -compiler: JIT compiler statistics.
- -gc: heap space capacities and utilization.
- -gccapacity: minimum, maximum, and current capacities of generations/spaces.
- -gccause: GC statistics along with the cause of the last GC and the current GC, if any.
- -gcnew: new generation statistics.
- -gcnewcapacity: new generation capacities.
- -gcold: old generation and metaspace statistics.
- -gcoldcapacity: old generation capacities.
- -gcmetacapacity: metaspace and compressed class space capacities.
- -gcutil: summary of percentage utilization and GC counters.
- -printcompilation: most recent method compilation statistics.

If an option does not appear in `jstat -options`, do not assume the JVM supports it.

## 4. Identifying the Target JVM with VMID

jstat uses a VMID (Virtual Machine Identifier) to identify a JVM. The most essential component is the LVMID (Local Virtual Machine Identifier). The LVMID is usually the operating system process ID, though not always.

### Finding the LVMID

Using jps:

~~~bash
jps -l
~~~

Or using jcmd:

~~~bash
jcmd -l
~~~

On Linux:

~~~bash
ps -ef | grep '[j]ava'
~~~

On Windows PowerShell:

~~~powershell
Get-CimInstance Win32_Process |
    Where-Object { $_.Name -match '^java(w)?\.exe$' } |
    Select-Object ProcessId, Name, CommandLine
~~~

Example jps output:

~~~text
4128 com.example.OrderService
7852 org.apache.catalina.startup.Bootstrap
~~~

In this case, `4128` is likely the LVMID for `OrderService`. Confirm the exact process before collecting data.

In Docker or containers with isolated PID namespaces, tools run from the host may not see the JVM inside. Find the PID from the appropriate namespace/container and run the tool in an environment that can access that JVM.

### VMID Structure

The general structure is described as:

~~~text
[protocol:][//]lvmid[@hostname[:port][/servername]]
~~~

- protocol: communication protocol; if omitted when monitoring a local JVM, jstat uses the platform-optimized local protocol.
- lvmid: ID of the target JVM.
- hostname: hostname or IP of the target machine.
- port: RMI registry port when using the RMI protocol.
- servername: remote object name, implementation-dependent.

For a local JVM, usually only the PID/LVMID is needed:

~~~bash
jstat -gcutil 4128 1000 10
~~~

## 5. Periodic Sampling and Reading Output

jstat outputs a text table. Each line is one sample; the first row contains column names.

Example:

~~~bash
jstat -gcutil -t -h 5 4128 1s 12
~~~

This command:

- Selects the `-gcutil` statistics group.
- Adds a Timestamp column with `-t`.
- Repeats the header every 5 samples with `-h 5`.
- Monitors the JVM with LVMID `4128`.
- Samples every 1 second.
- Stops after 12 samples.

Timestamp is the elapsed time in seconds since the target JVM started, not an absolute date/time. Its resolution can vary when the machine is under heavy load.

Do not conclude there is a memory leak or abnormal GC from a single line. Observe multiple samples, compare cumulative counters, and correlate with request timing, deployments, or load changes.

## 6. Monitoring GC with -gcutil

`-gcutil` is one of the most useful options for quickly observing garbage collection. It shows space utilization as percentages along with GC counts and times.

Common columns:

| Column | Meaning |
|---|---|
| S0 | Survivor space 0 utilization percentage |
| S1 | Survivor space 1 utilization percentage |
| E | Eden utilization percentage |
| O | Old space utilization percentage |
| M | Metaspace utilization percentage |
| CCS | Compressed Class Space utilization percentage, if exposed by the runtime |
| YGC | Number of young generation GC events since JVM start |
| YGCT | Total young generation GC time, typically in seconds |
| FGC | Number of full GC events since JVM start |
| FGCT | Total full GC time, typically in seconds |
| GCT | Total cumulative GC time, typically in seconds |

The exact set of columns can differ across JDKs and VMs. Some JDK 26 outputs do not display `CCS`; rely on the actual header.

Example:

~~~bash
jstat -gcutil 2834 250 7
~~~

Illustrative output from Oracle's documentation:

~~~text
S0     S1      E      O      M     YGC    YGCT    FGC    FGCT    GCT
0.00  99.74  13.49   7.86  95.82      3   0.124      0   0.000   0.124
0.00  99.74  13.49   7.86  95.82      3   0.124      0   0.000   0.124
0.00  99.74  13.49   7.86  95.82      3   0.124      0   0.000   0.124
0.00  99.74  13.49   7.86  95.82      3   0.124      0   0.000   0.124
0.00  99.74  13.49   7.86  95.82      3   0.124      0   0.000   0.124
0.00  99.74  13.49   7.86  95.82      3   0.124      0   0.000   0.124
0.00  99.74  13.49   7.86  95.82      3   0.124      0   0.000   0.124
~~~

This is illustrative output from the documentation, not metrics from a live application.

### Reading Trends

- `E` rising rapidly and then dropping after a young GC is normal behavior when an application creates short-lived objects.
- `YGC` increasing indicates additional young collections have occurred.
- `O` rising after GC cycles may indicate objects are being promoted or the live set is growing.
- `O` staying high and steadily climbing across GC cycles is a signal to investigate, though not by itself proof of a memory leak.
- `FGC` rising continuously or `FGCT` climbing rapidly may indicate memory pressure or a configuration that needs review.
- `GCT` is total cumulative time; take the difference between two samples and divide by the elapsed observation interval to estimate the fraction of time spent in GC.

The counters `YGC`, `YGCT`, `FGC`, `FGCT`, and `GCT` are cumulative values since JVM startup. Do not read them as events occurring within a single sample row. To compute the change over an interval, subtract the earlier sample from the later sample.

## 7. Viewing Capacity and Utilization with -gc

`-gc` displays the capacity and utilization of heap spaces in KB. It is useful when you need to know whether a high utilization percentage is due to a small space or a large actual capacity.

Common columns:

| Column | Meaning |
|---|---|
| S0C / S1C | Current survivor space 0/1 capacity, KB |
| S0U / S1U | Survivor space 0/1 utilization, KB |
| EC | Current Eden capacity, KB |
| EU | Eden utilization, KB |
| OC | Current old space capacity, KB |
| OU | Old space utilization, KB |
| MC | Metaspace committed, KB |
| MU | Metaspace utilization, KB |
| CCSC | Compressed class space committed, KB |
| CCSU | Compressed class space utilization, KB |
| YGC / YGCT | Young GC count and total time |
| FGC / FGCT | Full GC count and total time |
| GCT | Total GC time |

Example:

~~~bash
jstat -gc <PID> 1000 10
~~~

If `EU` is close to `EC`, Eden is nearly full and a young GC may occur soon. This is not a bad sign on its own; what matters is whether GC reclaims enough space and whether the application meets its latency targets.

If `OU` climbs continuously across multiple GC cycles, check a class histogram, heap dump, or JFR to see which objects remain alive and which allocation sites created them.

## 8. Viewing GC Causes with -gccause

`-gccause` displays a summary similar to `-gcutil` and adds the cause of the last GC as well as the current GC, if one is in progress.

Additional columns:

- `LGCC`: cause of the last garbage collection.
- `GCC`: cause of the current garbage collection, if any.

Example:

~~~bash
jstat -gccause <PID> 1s 20
~~~

This option helps correlate memory changes with the reason GC was triggered. However, it is only summary information; it does not replace GC logs when you need individual events, phases, pause times, and detailed causes.

## 9. Monitoring Generations and Metaspace

### -gcnew

`-gcnew` displays new generation statistics:

| Column | Meaning |
|---|---|
| S0C / S1C | Survivor space capacity |
| S0U / S1U | Survivor space utilization |
| TT | Current tenuring threshold |
| MTT | Maximum tenuring threshold |
| DSS | Desired survivor size, KB |
| EC | Eden capacity, KB |
| EU | Eden utilization, KB |
| YGC | Young GC count |
| YGCT | Total young GC time |

Example:

~~~bash
jstat -gcnew -h 5 <PID> 250 20
~~~

`TT` is the object age threshold for promotion from survivor space to the old generation under the collector's policy. If survivor space cannot hold the surviving objects, the JVM may adjust the tenuring threshold. Do not force `TT` manually based on a single snapshot; inspect GC logs and collector behavior.

### -gcold

`-gcold` displays old generation and metaspace statistics. Common columns include `MC`, `MU`, `CCSC`, `CCSU`, `OC`, `OU`, `YGC`, `FGC`, `FGCT`, and `GCT`.

Example:

~~~bash
jstat -gcold <PID> 1s 20
~~~

### -gcmetacapacity

`-gcmetacapacity` displays the minimum, maximum, and committed capacities of metaspace and compressed class space.

~~~bash
jstat -gcmetacapacity <PID> 2s 15
~~~

Metaspace stores class metadata and is managed outside the Java heap. If metaspace grows continuously, inspect class loading/unloading and class loader lifecycles. Normal heap occupancy does not rule out a metaspace issue.

## 10. Monitoring Capacity with Capacity Options

The capacity options show how much a generation or space can grow.

| Option | Purpose |
|---|---|
| -gccapacity | Generation and space capacities |
| -gcnewcapacity | New generation and survivor/Eden capacities |
| -gcoldcapacity | Old generation capacity |
| -gcmetacapacity | Metaspace and compressed class space capacities |

Examples:

~~~bash
jstat -gccapacity <PID> 1s 10
jstat -gcnewcapacity <PID> 1s 10
jstat -gcoldcapacity -t <PID> 1s 10
jstat -gcmetacapacity <PID> 1s 10
~~~

Columns such as `NGCMN`, `NGCMX`, `NGC`, `OGCMN`, `OGCMX`, `OGC`, `MCMN`, `MCMX`, and `MC` represent the minimum, maximum, or current capacity for each region.

A generation increasing in capacity does not automatically mean a memory leak. The JVM may expand the heap to meet allocation and promotion demand and keep that capacity for reuse. Compare capacity against utilization and GC behavior.

## 11. Monitoring Class Loading with -class

`-class` displays class loader activity.

Common columns:

| Column | Meaning |
|---|---|
| Loaded | Number of classes loaded according to the counter |
| Bytes | Number of KB of class data loaded |
| Unloaded | Number of classes unloaded |
| Bytes | Number of KB of class data unloaded |
| Time | Total time spent loading/unloading |

Example:

~~~bash
jstat -class <PID> 2s 15
~~~

The loaded/unloaded counters are cumulative statistics. If class loading continues to increase while the application handles normal workload warm-up, that can be expected. If the class count grows continuously after every deploy/reload, investigate class loader leaks, dynamic proxies, generated classes, or plugin lifecycles.

Class unloading only occurs when a class loader and its classes become eligible for reclamation under JVM rules. Do not conclude there is a leak solely because `Loaded` is high; inspect `Unloaded`, classloader statistics, and metaspace.

## 12. Monitoring the JIT Compiler with -compiler and -printcompilation

### -compiler

`-compiler` displays statistics for the HotSpot Just-in-Time compiler.

| Column | Meaning |
|---|---|
| Compiled | Number of compilation tasks performed |
| Failed | Number of compilation tasks that failed |
| Invalid | Number of compilation tasks invalidated |
| Time | Total compilation time |
| FailedType | Compile type of the last failed compilation |
| FailedMethod | Class/method of the last failed compilation |

Example:

~~~bash
jstat -compiler <PID> 1s 10
~~~

### -printcompilation

`-printcompilation` displays statistics for the most recently compiled method, typically including:

- Compiled: sequence number or count of compilation tasks for the most recent method.
- Size: bytecode size.
- Type: compilation type.
- Method: class and method compiled.

~~~bash
jstat -printcompilation <PID> 1s 10
~~~

These metrics are useful when investigating warm-up, compilation activity, or method compilation. They do not replace JFR when you need to know which methods consume CPU in real time or allocation stack traces.

## 13. Hands-On Example: Creating an Allocating JVM to Monitor

This example retains up to 32 byte arrays in a queue while continuously allocating new arrays. The program generates steady allocations while keeping a bounded amount of live data, allowing you to observe Eden, survivor, and old generation changes over time.

Create `JstatTarget.java`:

~~~java
import java.util.ArrayDeque;
import java.util.Deque;

public class JstatTarget {
    private static final Deque<byte[]> retained = new ArrayDeque<>();

    public static void main(String[] args) throws InterruptedException {
        System.out.println("jstat-target-ready");

        while (true) {
            if (retained.size() == 32) {
                retained.removeFirst();
            }

            retained.addLast(new byte[128 * 1024]);
            Thread.sleep(100);
        }
    }
}
~~~

### Compile

Use JDK 17 or later:

~~~bash
javac --release 17 JstatTarget.java
~~~

### Start the Target JVM

Terminal A:

~~~bash
java JstatTarget
~~~

Exact output:

~~~text
jstat-target-ready
~~~

Keep the program running. It continues allocating and discarding arrays in a loop; there is no need to trigger an `OutOfMemoryError`.

### Find the PID

Terminal B:

~~~bash
jps -l
~~~

Find the `JstatTarget` line and note its LVMID/PID.

### Sample GC Utilization

~~~bash
jstat -gcutil <PID> 1s 15
~~~

Observe `E`, `S0`, `S1`, `O`, `M`, `YGC`, `YGCT`, `FGC`, `FGCT`, and `GCT`. Values will vary depending on the JDK, collector, machine load, and when sampling starts.

### Sample Capacity in KB

~~~bash
jstat -gc -t <PID> 1s 15
~~~

Use `EC`/`EU`, `OC`/`OU`, and the capacity/utilization columns to understand which actual capacities back the percentages in `-gcutil`.

### View GC Causes

~~~bash
jstat -gccause <PID> 1s 15
~~~

### View Class Loading and JIT

~~~bash
jstat -class <PID> 2s 10
jstat -compiler <PID> 2s 10
~~~

### Stop the Program

Return to Terminal A and press Ctrl+C. `jstat` only reads statistics; it does not modify the heap or stop the target JVM.

## 14. Reading Runtime Metrics via Java Management Extensions (JMX)

`jstat` is convenient for quick sampling from the terminal. When an application needs to export metrics to dashboards, alerts, or a monitoring backend, JMX Platform MXBeans provide a more structured management API.

Key MXBeans:

| MXBean | Data |
|---|---|
| MemoryMXBean | Heap and non-heap memory usage |
| MemoryPoolMXBean | Usage, peak usage, and thresholds per memory pool |
| GarbageCollectorMXBean | Collection count and collection time per GC |
| ClassLoadingMXBean | Loaded, total loaded, and unloaded class counts |
| CompilationMXBean | JIT compilation time if supported by the VM |
| ThreadMXBean | Thread count, peak count, thread CPU time, and deadlock detection |
| RuntimeMXBean | Uptime, input arguments, and JVM/system properties |
| OperatingSystemMXBean | OS and processor information; extensions depend on the JDK |

`ManagementFactory` provides factory methods to obtain MXBeans in the current JVM or create proxies to access MXBeans from a remote `MBeanServerConnection`.

### Java Example: Reading Metrics from MXBeans

Create `RuntimeMetrics.java`:

~~~java
import java.lang.management.ClassLoadingMXBean;
import java.lang.management.GarbageCollectorMXBean;
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryMXBean;
import java.lang.management.MemoryUsage;

public class RuntimeMetrics {
    public static void main(String[] args) {
        MemoryMXBean memory = ManagementFactory.getMemoryMXBean();
        MemoryUsage heap = memory.getHeapMemoryUsage();

        System.out.printf("heap.used.bytes=%d%n", heap.getUsed());
        System.out.printf("heap.committed.bytes=%d%n", heap.getCommitted());
        System.out.printf("heap.max.bytes=%d%n", heap.getMax());

        ClassLoadingMXBean classes =
                ManagementFactory.getClassLoadingMXBean();

        System.out.printf("classes.current=%d%n",
                classes.getLoadedClassCount());
        System.out.printf("classes.total=%d%n",
                classes.getTotalLoadedClassCount());
        System.out.printf("classes.unloaded=%d%n",
                classes.getUnloadedClassCount());

        for (GarbageCollectorMXBean gc :
                ManagementFactory.getGarbageCollectorMXBeans()) {
            System.out.printf(
                    "gc.name=%s count=%d time.ms=%d%n",
                    gc.getName(),
                    gc.getCollectionCount(),
                    gc.getCollectionTime());
        }
    }
}
~~~

Compile and run:

~~~bash
javac --release 17 RuntimeMetrics.java
java RuntimeMetrics
~~~

Output values depend on the JVM, collector, timing, and workload; there is no single fixed stdout across all machines.

Meaning:

- `heap.used.bytes`: heap memory currently in use at the time of reading.
- `heap.committed.bytes`: heap memory committed by the JVM.
- `heap.max.bytes`: maximum heap limit; some VMs may return `-1` if undefined.
- `classes.current`: number of classes currently loaded.
- `classes.total`: total number of classes loaded since the JVM started.
- `classes.unloaded`: number of classes unloaded.
- `gc.count`: number of collections for the corresponding collector.
- `gc.time.ms`: cumulative collection time in milliseconds.

Some MXBeans may return `-1` if a metric is unsupported or unavailable. `GarbageCollectorMXBean` can have multiple instances because a JVM may use multiple collectors.

MXBeans provide a snapshot at the moment they are called. To build a time series, the application or monitoring agent needs to sample periodically, attach timestamps, and export metrics using a stable schema.

## 15. Using jcmd, JFR, and JMC to Supplement Data

`jstat` shows how counters change. When you need to understand the root cause or a more detailed timeline, use the appropriate tool.

### jcmd PerfCounter.print

~~~bash
jcmd <PID> PerfCounter.print
~~~

This command prints the performance counters published by the process. It is useful when you need low-level counters or want to inspect the raw data that `jstat` summarizes.

### Viewing Heap and JVM Status

~~~bash
jcmd <PID> GC.heap_info
jcmd <PID> VM.uptime
jcmd <PID> VM.flags
~~~

`GC.heap_info` provides an overview of the heap; `VM.uptime` and `VM.flags` help correlate runtime state, uptime, and JVM configuration.

### Collecting JFR

~~~bash
jcmd <PID> JFR.start name=runtime settings=default duration=2m filename=runtime.jfr
~~~

Check the recording:

~~~bash
jcmd <PID> JFR.check
~~~

JFR collects time-stamped events such as GC, allocations, threads, locks, I/O, and latency. The `default` template has lower overhead; `profile` collects more data but can introduce higher overhead.

Open `runtime.jfr` in JDK Mission Control to inspect memory, GC, threads, method profiling, and the event timeline. JFR is well suited when you need to know what happened between two `jstat` samples.

### JConsole

JConsole is a JMX tool included in the JDK. It graphs heap/non-heap usage, memory pools, GC count/time, thread count, class loading, and CPU usage. JConsole can connect to local or remote JVMs when the management agent is properly configured.

Do not enable remote JMX in production without proper authentication, TLS, authorization, network binding, and firewall rules. When you only need runtime data, use local attach or an organization-configured monitoring agent.

## 16. Distinguishing Metrics, Counters, and Rates

To avoid misreading dashboards, classify your data properly:

### Gauge

A gauge is a point-in-time value that can go up or down:

- Heap used.
- Eden utilization.
- Old generation utilization.
- Metaspace usage.
- Current loaded class count.
- Current live thread count.

### Counter

A counter typically increases cumulatively since process start:

- YGC, FGC.
- YGCT, FGCT, GCT.
- Total loaded class count.
- Unloaded class count.
- Compilation count.

To measure activity within a window, take the delta between two readings.

### Rate

A rate is the speed of change over time:

- GC events per second.
- Allocation bytes per second.
- Class load rate.
- Compilation rate.
- GC time percentage over an interval.

For example, if `GCT` increases from 12.0 seconds to 13.5 seconds over 30 wall-clock seconds, total GC time increased by 1.5 seconds. The approximate GC time percentage in that interval is `1.5 / 30 = 5%`. This is an estimate derived from counters; it does not replace pause-time distributions or JFR events.

Do not treat a cumulative counter as a gauge. A large `GCT` value might simply mean the JVM has been running for a long time; examine the rate of increase over a specific interval.

## 17. Performance Investigation Workflows Using Runtime Metrics

### Scenario A: Heap Growing Continuously

1. Run `jstat -gcutil` at regular intervals.
2. Observe `E` and `O` before/after young GC.
3. If `O` after GC climbs continuously, check GC logs and live set size.
4. Capture a class histogram to see which classes have growing instance counts.
5. Take a heap dump if you need to trace references keeping objects alive.
6. Use JFR to locate allocation sites and when object growth occurs.
7. Cross-check with caches, sessions, queues, listeners, and class loader lifecycles.

### Scenario B: GC Occurring Too Frequently

1. Monitor `YGC`/`YGCT` and Eden utilization.
2. Calculate the `YGC` delta over a time window.
3. Observe allocation rates using JFR or a profiler.
4. Identify which short-lived objects are being allocated heavily.
5. Check throughput, request rate, and heap sizing.
6. Optimize allocations or data structures before simply increasing heap size.

Frequent young GCs can be a normal consequence of high allocation throughput. Treat it as an issue only when it affects latency/throughput or misses operational targets.

### Scenario C: Increasing Full GCs

1. Monitor `FGC`, `FGCT`, and `GCCause`.
2. Correlate timestamps with GC logs.
3. Check old generation occupancy and promotion rates.
4. Determine whether full GCs are triggered by allocation pressure, explicit GC, metadata pressure, or another cause.
5. If there are many full GCs and long pauses, capture JFR or detailed GC logs.
6. Only change heap/collector settings after understanding the workload and root cause.

### Scenario D: Class Loading or Metaspace Growing

1. Monitor `-class` and `-gcmetacapacity`.
2. Compare `Loaded`/`Unloaded` across deployments or reloads.
3. Check class loader counts with `jcmd VM.classloader_stats`.
4. Use `VM.classloaders` or a heap dump if you need to find references retaining a class loader.
5. Inspect dynamic proxies, bytecode generation, plugins, and application redeploys.

### Scenario E: JVM is Slow but Heap is Stable

`jstat` does not provide enough visibility into CPU, lock contention, I/O, or request latency. Check:

- JFR CPU/thread/lock/I/O events.
- JConsole or JMX `OperatingSystemMXBean`.
- Thread dumps when blocking or deadlocks are suspected.
- OS tools for CPU, memory, disk, and network.
- Application metrics such as request rate, latency percentiles, queue depth, and error rate.

Do not conclude GC is the cause merely because heap metrics changed around the same time the application slowed down.

## 18. Limitations to Keep in Mind

- `jstat` reads HotSpot performance counters; it is not a general-purpose profiler.
- It does not provide an object graph or retained heap information.
- It does not show exact allocation stack traces for objects.
- Not every metric exists on every JDK or collector.
- Legacy generation columns may not accurately reflect the structure of every garbage collector.
- Output formats and option names can change or be removed.
- Do not write scripts that parse `jstat` output as a stable API.
- Sampling too frequently does not improve diagnosis without a hypothesis; choose an appropriate interval.
- On FAT32, the HotSpot instrumentation used by `jstat` is inaccessible.
- Remote `jstat` uses `jstatd`/RMI and requires security configuration; do not expose RMI broadly on public networks.

For long-term monitoring systems, prefer JMX MXBeans, JFR, GC logs, and metrics exporters with a stable schema.

## 19. Monitoring a Remote JVM with jstatd

`jstat` can monitor a remote JVM via `jstatd`, an RMI server daemon. A VMID can include both LVMID and hostname:

~~~bash
jstat -gcutil 40496@remote.domain 1000 10
~~~

This example assumes `jstatd` is running on `remote.domain` and the RMI registry is reachable as configured. `jstatd` allows tools like `jps`/`jstat` to access JVM instrumentation on a remote host.

Before using it:

- Configure `jstatd` according to the documentation for your exact JDK.
- Use the minimal security policy required.
- Restrict network interfaces and firewalls to authorized monitoring hosts only.
- Do not expose the RMI registry or remote objects to the public Internet.
- Verify the LVMID in the remote environment.
- Check compatibility between the client tool and the target JVM.

If remote instrumentation is not strictly needed, a JMX exporter, JFR, or your organization's observability stack may be a better fit.

## 20. Common Errors and Troubleshooting

### jstat Cannot Find the JVM

**Symptom:** reports VM not found or cannot read VMID.

**Cause:** wrong PID, JVM has exited, process is in a different container/PID namespace, or user lacks permission to access instrumentation.

**Resolution:** identify the LVMID using `jps -l` or OS tools inside the correct namespace; confirm the JVM is still running and use the matching JDK environment.

### jstat Reports Invalid Option

**Symptom:** the tool does not recognize `-gcutil`, `-gcnew`, or another option.

**Cause:** the option is not present in the current `jstat` build or differs across JDKs/vendors.

**Resolution:** run `jstat -options` on the target runtime; do not treat option tables from another version as a guarantee of support.

### Cannot Access Instrumentation on FAT32

**Symptom:** `jstat` cannot read data even though the JVM is running.

**Cause:** HotSpot instrumentation is not accessible on FAT32.

**Resolution:** use a filesystem that supports the instrumentation mechanism, or use JMX/JFR/GC logs instead.

### Metric Columns Do Not Match Documentation

**Symptom:** missing `CCS`, different column names, or generation numbers that differ from examples.

**Cause:** differences in JDK release, vendor, collector, or VM implementation.

**Resolution:** read the actual output header, check `jstat -options`, and verify which collector is in use. Do not extrapolate from an older sample output.

### Counters Increase Without Showing the Interval Rate

**Symptom:** `YGC`/`FGC`/`GCT` show large numbers.

**Cause:** these are cumulative counters since JVM startup.

**Resolution:** take the delta between two samples, divide by the elapsed wall-clock time, and correlate with latency/throughput.

### Output Parsing Script Breaks After a JDK Upgrade

**Symptom:** columns change, headers differ, or the parser misreads values.

**Cause:** `jstat` output is not a stable format; the documentation advises against writing scripts that depend on it.

**Resolution:** migrate to JMX MXBeans, JFR, or a metrics exporter with a clear schema. If you must still use `jstat`, limit the script's scope and re-test on every JDK upgrade.

### Remote jstat Fails to Connect

**Symptom:** RMI error, timeout, or failure to resolve the remote JVM.

**Cause:** `jstatd` is not running, the RMI registry/port is blocked, wrong LVMID, or security policy denies access.

**Resolution:** check `jstatd`, the RMI registry, firewall, policy, and VMID; allow connections only from authorized monitoring hosts.

### jstat Does Not Explain CPU or Latency

**Symptom:** heap/GC look normal, yet the application is still slow.

**Cause:** the bottleneck may be in CPU, locks, I/O, network, thread pools, or the database.

**Resolution:** capture JFR, thread dumps, JMX/OS metrics, and application metrics; do not use GC statistics to draw conclusions about non-GC causes.

## 21. Operational Checklist

### Before Sampling

- [ ] Identify the JDK vendor/version and target HotSpot JVM.
- [ ] Identify the exact LVMID/PID.
- [ ] Run `jstat -options` to verify available stat options.
- [ ] Choose metrics based on the question you need to answer.
- [ ] Pick an interval/count suited to the workload.
- [ ] Confirm the filesystem supports instrumentation.
- [ ] If remote, verify `jstatd`/RMI and the security policy.

### During Sampling

- [ ] Use `-t` if you need to correlate elapsed time.
- [ ] Use `-h` to repeat headers when taking many samples.
- [ ] Distinguish gauges from cumulative counters.
- [ ] Compute deltas for `YGC`, `FGC`, `YGCT`, `FGCT`, and `GCT`.
- [ ] Observe multiple samples rather than concluding from a single row.
- [ ] Do not parse the output as a stable API.

### After Sampling

- [ ] Cross-check with GC logs, JFR, or JMX when more detail is needed.
- [ ] Record the JDK version, collector, PID, and collection timestamp.
- [ ] Check post-GC heap trends, not just peak occupancy.
- [ ] Investigate class loading/metaspace if counters grow abnormally.
- [ ] Capture a histogram/heap dump when object-level evidence is needed.
- [ ] Protect the output if it contains environment details or sensitive data.
- [ ] Only adjust heap/GC configuration when backed by evidence and testing.

## 22. Official References

- [Diagnostic Tools — Java SE 26 Troubleshooting Guide](https://docs.oracle.com/en/java/javase/26/troubleshoot/diagnostic-tools.html) — `jstat` utility, VMID, built-in instrumentation, GC examples, and runtime monitoring.
- [The jstat Command — Java SE 17 Tool Specifications](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jstat.html) — syntax, interval/count, VMID, stat options, output columns, and the experimental/unsupported warning. This is the page to which the `jstat` link in the Java SE 26 Troubleshooting Guide currently redirects.
- [The jcmd Command — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jcmd.html) — diagnostic commands, `PerfCounter.print`, heap info, JFR, and supplementary diagnostics.
- [ManagementFactory — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/java/lang/management/ManagementFactory.html) — accessing Platform MXBeans within the JVM and via `MBeanServer`.
- [MemoryMXBean — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/java/lang/management/MemoryMXBean.html) — heap/non-heap memory usage and memory notifications.
- [ClassLoadingMXBean — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/java/lang/management/ClassLoadingMXBean.html) — class loading/unloading statistics.
- [GarbageCollectorMXBean — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/java/lang/management/GarbageCollectorMXBean.html) — collection count/time per garbage collector.
- [Java SE Monitoring and Management Guide — Java SE 26](https://docs.oracle.com/en/java/javase/26/management/java-se-monitoring-and-management-guide.pdf) — Platform MXBeans, JMX, and JVM monitoring.

`jstat` provides quick visibility into HotSpot runtime counters, especially for heap, GC, class loading, and JIT compilation. Choose the right stat option, read trends across multiple samples, compute deltas for cumulative counters, and combine with JMX/JFR when you need structured metrics or detailed root causes.
