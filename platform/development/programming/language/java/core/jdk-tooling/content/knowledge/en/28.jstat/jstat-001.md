# The jstat Command in Java

`jstat` (Java Virtual Machine Statistics Monitoring Tool) is a JDK command-line tool used to monitor statistics for a running Java HotSpot VM. It can display information about garbage collection (GC), heap space utilization, class loading, the JIT compiler, and method compilation status across sampling intervals.

`jstat` is useful when you need a quick look at an active JVM: whether Eden is continuously filling up, whether young/full GC counts are rising rapidly, whether the old generation keeps growing after GC, whether Metaspace is growing with class loading, or which methods the compiler is compiling.

In the Oracle JDK 21 documentation, `jstat` is marked as **experimental and unsupported**. Options and output formats may change or be removed in future JDK releases. Use `jstat -options` to see the statistics supported by the installed JDK, avoid writing automation that depends on fixed column positions, and consider JFR/JMX for long-term monitoring.

## 1. What is jstat used for?

`jstat` reads counters and statistics exposed by HotSpot for an instrumented JVM. It is a sampling tool: each output line represents the state at query time, while many columns are cumulative counters since JVM startup.

Common use cases:

- Monitoring young GC and full GC frequency.
- Viewing utilization of Eden, Survivor, Old Generation, and Metaspace.
- Observing how heap capacity changes over time.
- Checking the number of loaded/unloaded classes and class loading time.
- Monitoring HotSpot JIT compiler activity.
- Comparing multiple samples to identify trends before taking a heap dump or enabling deeper profiling.

`jstat` is not a full profiler. It does not show which specific objects are retaining heap memory, does not provide allocation call trees, and does not replace GC logs or JFR. When you notice abnormal metrics, use those results to guide the next investigation step.

## 2. Command syntax

General syntax:

```sh
jstat -<statOption> [-t] [-h <lines>] <vmid> [<interval> [<count>]]
```

Components:

| Component | Meaning |
|---|---|
| `-<statOption>` | Statistics group to display, such as `-gcutil`, `-gc`, or `-class` |
| `-t` | Adds a timestamp column showing elapsed time since the target JVM started |
| `-h <lines>` | Repeats the column header every specified number of samples |
| `<vmid>` | Virtual machine identifier of the JVM to monitor |
| `<interval>` | Sampling interval between outputs; defaults to milliseconds |
| `<count>` | Number of samples to collect; if omitted, continues until the JVM stops or the command is terminated |

Example collecting 10 samples, 1 second apart:

```sh
jstat -gcutil 24680 1000 10
```

In this example, `24680` is an illustrative VMID. Replace it with the VMID of your actual application.

If `interval` is omitted, the tool prints only a single sample. If `interval` is specified without `count`, the tool continues printing samples until the target process exits or the operator presses Ctrl+C.

The interval must be a positive number; the default unit is milliseconds. The JDK documentation also describes seconds (`s`) or milliseconds (`ms`) units. When a value has no suffix, such as `1000`, it is interpreted as 1,000 milliseconds.

## 3. Viewing supported options

The list of output options can vary by JDK, vendor, or platform. Check directly with:

```sh
jstat -options
```

General help:

```sh
jstat -help
```

Common output options in Oracle JDK 21:

| Option | Statistics |
|---|---|
| `-class` | Class loader activity |
| `-compiler` | HotSpot JIT compiler activity |
| `-gc` | Heap space capacities, utilization, and GC counters |
| `-gccapacity` | Generation and memory space capacities |
| `-gccause` | GC summary similar to `-gcutil`, plus the cause of GC |
| `-gcnew` | New generation statistics |
| `-gcnewcapacity` | New generation capacity |
| `-gcold` | Old generation and Metaspace statistics |
| `-gcoldcapacity` | Old generation capacity |
| `-gcmetacapacity` | Metaspace capacity |
| `-gcutil` | Summary of space utilization percentages and GC counters |
| `-printcompilation` | HotSpot method compilation statistics |

Not every JDK version provides the exact same set of options. In particular, names containing `perm` in very old Java documentation refer to Permanent Generation; since Java 8, PermGen has been replaced by Metaspace. On JDK 21, use the Metaspace options instead of following legacy PermGen guides.

## 4. Quick GC monitoring with -gcutil

`-gcutil` is one of the most useful options for observing GC:

```sh
jstat -gcutil 24680 1000 10
```

Sample output:

```text
  S0     S1      E      O      M    CCS    YGC    YGCT    FGC    FGCT     GCT
  0.00  72.50  68.20  45.10  82.30  75.20    120   1.240      2   0.380   1.620
  0.00  72.50  91.40  45.10  82.30  75.20    120   1.240      2   0.380   1.620
  0.00  35.20   4.10  48.30  82.50  75.30    121   1.258      2   0.380   1.638
```

The numbers above only illustrate how to read the output; they are not fixed output values or standard performance thresholds.

| Column | Meaning |
|---|---|
| `S0` | Survivor space 0 utilization as a percentage of its current capacity |
| `S1` | Survivor space 1 utilization as a percentage of its current capacity |
| `E` | Eden space utilization as a percentage of its current capacity |
| `O` | Old space utilization as a percentage of its current capacity |
| `M` | Metaspace utilization as a percentage of its current capacity |
| `CCS` | Compressed Class Space utilization percentage |
| `YGC` | Number of young GC events |
| `YGCT` | Total young GC time, in seconds |
| `FGC` | Number of full GC events |
| `FGCT` | Total full GC time, in seconds |
| `GCT` | Total GC time, in seconds |

`S0` and `S1` typically alternate roles between young collections. Eden usually increases as the application allocates objects and drops after a young GC. Eden reaching nearly 100% is not automatically an error; it is normal behavior right before a collection.

`O` should be observed as a trend. If old-space utilization rises steadily and remains high after multiple GCs, the application may be retaining objects longer, the workload may have increased, or the heap may be under pressure. Inspect multiple samples and the workload before concluding there is a memory leak.

`M` and `CCS` relate to Metaspace and Compressed Class Space, not the regular Java object heap. If they grow continuously, check class loading, classloader lifecycles, proxy generation, and application redeployments.

## 5. Viewing capacity and utilization in KB with -gc

`-gc` displays capacity and utilization in KB along with GC counters:

```sh
jstat -gc 24680 1000 5
```

Common columns on JDK 21:

| Column | Meaning |
|---|---|
| `S0C` / `S1C` | Current capacity of Survivor space 0/1 |
| `S0U` / `S1U` | Current used size of Survivor space 0/1 |
| `EC` / `EU` | Eden capacity and utilization |
| `OC` / `OU` | Old space capacity and utilization |
| `MC` / `MU` | Metaspace committed size and utilization |
| `CCSC` / `CCSU` | Compressed Class Space committed size and used size |
| `YGC` / `YGCT` | Number of young GCs and total young GC time |
| `FGC` / `FGCT` | Number of full GCs and total full GC time |
| `GCT` | Total GC time |

Capacity and used columns are typically reported in KB as defined by each option. Do not confuse committed/capacity values with the total memory usage of the entire process. A Java process also includes native memory, thread stacks, code cache, direct buffers, and other off-heap regions.

You can use `-gc` to view absolute sizes instead of percentages. `-gcutil` is convenient for spotting trends quickly; `-gc` is useful when you need to convert usage to KB and compare it against heap limits.

## 6. Tracking GC causes with -gccause

`-gccause` displays the same columns as `-gcutil` plus the cause of the last GC and the current GC cause if one is in progress:

```sh
jstat -gccause 24680 1000 10
```

Two additional columns:

| Column | Meaning |
|---|---|
| `LGCC` | Cause of the last garbage collection |
| `GCC` | Cause of the current collection, if any |

Causes can depend on the collector and situation, such as allocation failure or an explicit collection request from the application. Actual values must be read from the live output.

Do not assume every full GC is caused by a memory leak. GC can be triggered by allocation pressure, metadata pressure, explicit GC requests, or collector policies. Combine `LGCC`/`GCC` with GC logs and other metrics to understand the root cause.

## 7. Viewing generation capacities with -gccapacity

`-gccapacity` displays the minimum, maximum, and current capacities of the generations/spaces:

```sh
jstat -gccapacity 24680
```

Main columns on JDK 21:

| Column | Meaning |
|---|---|
| `NGCMN` | Minimum new generation capacity |
| `NGCMX` | Maximum new generation capacity |
| `NGC` | Current new generation capacity |
| `S0C` / `S1C` | Current capacity of Survivor space 0/1 |
| `EC` | Current Eden capacity |
| `OGCMN` | Minimum old generation capacity |
| `OGCMX` | Maximum old generation capacity |
| `OGC` | Current old generation capacity |
| `OC` | Current old space capacity |
| `MCMN` / `MCMX` | Minimum/maximum Metaspace capacity |
| `MC` | Metaspace committed size |
| `CCSMN` / `CCSMX` | Minimum/maximum Compressed Class Space capacity |
| `CCSC` | Compressed Class Space committed size |

`YGC` and `FGC` columns are also included in this output. Capacities can change as the heap expands or shrinks according to JVM policies. Be sure to distinguish current capacity from actual utilization.

## 8. Monitoring the new generation with -gcnew

`-gcnew` focuses on the young generation:

```sh
jstat -gcnew 24680 1000 10
```

Columns:

| Column | Meaning |
|---|---|
| `S0C` / `S1C` | Survivor space 0/1 capacity |
| `S0U` / `S1U` | Survivor space 0/1 utilization |
| `TT` | Current tenuring threshold |
| `MTT` | Maximum tenuring threshold |
| `DSS` | Desired survivor size |
| `EC` / `EU` | Eden capacity and utilization |
| `YGC` | Number of young GC events |
| `YGCT` | Total young GC time |

The tenuring threshold is the age threshold an object must reach before it is considered for promotion out of the young generation. The actual value can change depending on Survivor space occupancy and adaptive collector policies.

If Survivor space does not have enough room for surviving objects, the JVM may promote objects earlier. Read `TT` together with `DSS`, `S0U`, `S1U`, and GC logs rather than drawing conclusions from a single column.

## 9. Viewing new generation capacity with -gcnewcapacity

`-gcnewcapacity` displays the bounds and capacities of the young generation spaces:

```sh
jstat -gcnewcapacity 24680
```

Main columns:

- `NGCMN`, `NGCMX`, `NGC`: minimum, maximum, and current new generation capacity.
- `S0CMX` and `S1CMX`: maximum Survivor space 0/1 capacity.
- `S0C` and `S1C`: current Survivor space 0/1 capacity.
- `ECMX` and `EC`: maximum and current Eden capacity.
- `YGC` and `FGC`: number of young/full GC events.

Use this option when you need to know how much the JVM can expand the young generation and where its current capacity stands. Combine it with `-gcnew` to understand utilization and promotion behavior.

## 10. Monitoring the old generation with -gcold and -gcoldcapacity

`-gcold` displays old space and related Metaspace utilization:

```sh
jstat -gcold 24680 1000 5
```

Columns typically include `MC`, `MU`, `CCSC`, `CCSU`, `OC`, `OU`, `YGC`, `FGC`, `FGCT`, and `GCT`.

`-gcoldcapacity` displays old generation capacities:

```sh
jstat -gcoldcapacity 24680
```

Main columns:

- `OGCMN`: minimum old generation capacity.
- `OGCMX`: maximum old generation capacity.
- `OGC`: current old generation capacity.
- `OC`: current old space capacity.
- `YGC`, `FGC`, `FGCT`, `GCT`: GC counters and times.

If `OU` consistently increases after young GCs and does not drop significantly after appropriate collections, check object lifetimes, caches, queues, static references, and heap dumps. However, old space growth can also be normal behavior when the workload increases or the heap is expanding.

## 11. Monitoring Metaspace with -gcmetacapacity

Metaspace stores class metadata and is allocated from native memory. It is separate from the Java object heap.

Run:

```sh
jstat -gcmetacapacity 24680
```

Columns:

| Column | Meaning |
|---|---|
| `MCMN` | Minimum Metaspace capacity |
| `MCMX` | Maximum Metaspace capacity |
| `MC` | Metaspace committed size |
| `CCSMN` | Minimum Compressed Class Space capacity |
| `CCSMX` | Maximum Compressed Class Space capacity |
| `YGC` | Number of young GCs |
| `FGC` | Number of full GCs |
| `FGCT` | Total full GC time |
| `GCT` | Total GC time |

If Metaspace grows continuously, check whether classloaders are being released after redeployments, whether the application is dynamically generating classes continuously, or whether frameworks are generating new proxies/lambdas/classes.

Metaspace growth is not necessarily a leak. New classes loaded during startup or while caches/frameworks initialize can cause this region to grow and then stabilize. Look at the trend after the workload has stabilized.

## 12. Monitoring class loading with -class

`-class` displays class loader statistics:

```sh
jstat -class 24680 1000 10
```

Columns:

| Column | Meaning |
|---|---|
| `Loaded` | Number of classes loaded |
| `Bytes` | Number of KB loaded |
| `Unloaded` | Number of classes unloaded |
| `Bytes` | Number of KB unloaded |
| `Time` | Time spent performing class load and unload operations |

These counters are typically cumulative from JVM startup. If `Loaded` rises continuously while `Unloaded` remains nearly flat, the application may be loading more classes with workload growth or classloaders may not be getting released.

To investigate further, combine `-class` with `-gcmetacapacity`, `jcmd VM.classloader_stats`, and a heap dump when needed. Class loading metrics alone are not sufficient to conclude a classloader leak.

## 13. Monitoring the JIT compiler with -compiler and -printcompilation

`-compiler` displays summary statistics about the HotSpot JIT compiler:

```sh
jstat -compiler 24680
```

Columns typically include:

- `Compiled`: number of compilation tasks performed.
- `Failed`: number of compilation tasks that failed.
- `Invalid`: number of compilation tasks invalidated.
- `Time`: time spent performing compilations.
- `FailedType`: compile type of the last failed compilation.
- `FailedMethod`: class and method of the last failed compilation.

`-printcompilation` displays method compilation information:

```sh
jstat -printcompilation 24680 1000 5
```

Columns:

| Column | Meaning |
|---|---|
| `Compiled` | Number of compilation tasks for the most recently compiled method |
| `Size` | Number of bytes of bytecode in the method |
| `Type` | Compilation type |
| `Method` | Class and method name; class name uses `/` instead of dots |

These statistics help observe JIT activity, but they do not replace a CPU profiler. If you want to know which methods consume the most CPU, use JFR, async-profiler, or an appropriate profiling tool.

## 14. Adding timestamps and repeating headers

`-t` adds a `Timestamp` column at the beginning of the output. The value is the number of seconds elapsed since the target JVM started, not wall-clock time.

```sh
jstat -gcutil -t 24680 1000 5
```

`-h <n>` prints the column header again after every n samples. For example:

```sh
jstat -gcutil -t -h 5 24680 1000 15
```

This is useful when output is long, the terminal scrolls past many samples, or you save output to a file for later review. Repeating headers keep readers from having to scroll back to the top to recall column meanings.

Do not use this timestamp as wall-clock time to correlate directly with external logs. Record the collection start time in your shell or monitoring system if you need timeline correlation.

## 15. Understanding VMID and finding the JVM to monitor

`vmid` is the Virtual Machine Identifier. For a local JVM, the commonly used component is the LVMID (local VM identifier), which usually—but not always—matches the OS PID.

You can find running JVMs with:

```sh
jps -l
```

Example:

```text
24680 com.example.JstatDemo
25120 com.example.OrderService
```

Then run:

```sh
jstat -gcutil 24680 1000 10
```

If `jps` does not show the process, you can use OS tools such as `ps` on Linux/macOS or Task Manager/PowerShell on Windows. In Docker, the LVMID seen inside a container may differ from the PID on the host; run the tool in the appropriate PID namespace.

The tool generally requires access to the JVM on the same machine and appropriate attach permissions. If attaching fails, check user/group ownership, OS permissions, attach configuration, and the container environment.

## 16. Monitoring remote JVMs with jstatd

`jstat` supports remote VMIDs. The general VMID syntax according to the documentation is:

```text
[protocol:][//]lvmid[@hostname[:port][/servername]]
```

Example:

```sh
jstat -gcutil 40496@remote.domain 1000
```

With a hostname and default protocol, `jstat` uses RMI. On the target host, `jstatd` and an RMI registry must be running and configured to expose instrumentation data. The default RMI registry port is typically 1099 unless another port is specified.

Remote monitoring does not work simply by appending a hostname. You must properly configure `jstatd`, RMI, security policies, and network permissions. Only enable the service in controlled environments, restrict network access, and follow your organization's security policies.

If you are only monitoring JVMs on the same machine, using a simple local VMID requires much less configuration.

## 17. Hands-on Java 17+ example: creating an allocation workload

The following example continuously allocates byte arrays, holds a sliding window of objects in a two-dimensional array, and replaces them on the next loop iteration. This workload helps you observe Eden and young GC while the program runs.

Create `JstatDemo.java`:

```java
public class JstatDemo {
    public static void main(String[] args) throws InterruptedException {
        System.out.println("READY");

        byte[][] window = new byte[128][];
        while (true) {
            for (int i = 0; i < window.length; i++) {
                window[i] = new byte[256 * 1024];
            }
            Thread.sleep(100);
        }
    }
}
```

Compile:

```sh
javac JstatDemo.java
```

Run with a fixed 128 MB heap:

```sh
java -Xms128m -Xmx128m JstatDemo
```

Exact stdout:

```text
READY
```

The program keeps running after printing READY. Open a second terminal, find the PID using `jps -l`, and run:

```sh
jstat -gcutil <pid> 1000 10
```

To view capacities in KB:

```sh
jstat -gc <pid> 1000 10
```

To add timestamps and periodic headers:

```sh
jstat -gcutil -t -h 5 <pid> 1000 15
```

This workload is designed to generate continuous allocations, but exact GC event counts, utilization percentages, and collection timing depend on the JDK, collector, heap configuration, and host machine. Do not use a fixed output number as a pass/fail criterion.

After practicing, return to the terminal running the program and press Ctrl+C to stop the process.

## 18. Reading GC trends across multiple samples

Do not draw conclusions from a single line of output. Observe multiple samples over time and compare columns side by side.

### Eden rising then dropping

If `E` climbs steadily and then drops sharply while `YGC` increases, a young collection has usually occurred. After the collection, Survivor usage may increase and some objects may be promoted to the old generation.

### Old space growing steadily

If `O` or `OU` increases across multiple samples and does not drop significantly after appropriate collections, check:

- Unbounded caches or missing eviction policies.
- Growing queue/task backlogs.
- Objects held by static collections or listeners.
- Session/request lifecycles not being cleaned up.
- Increased workload or concurrency compared to baseline.

This is a signal to investigate, not standalone proof of a memory leak.

### Full GC increasing rapidly

Track the delta of `FGC` and `FGCT` between samples. If full GC counts rise quickly and total full GC time grows significantly, the application may be under memory pressure or experiencing an allocation/retention issue.

Also inspect `LGCC`/`GCC` from `-gccause` and cross-reference GC logs to identify the cause.

### Metaspace growing

If `M`, `MU`, or `MC` grows continuously, check class loading and classloader lifecycles. If the application is redeployed multiple times, check whether old classloaders are still retained by threads, `ThreadLocal`, static references, or framework registries.

### GC time increasing

`YGCT`, `FGCT`, and `GCT` are cumulative times in seconds. Compare the increase between two samples to see whether GC time is rising rapidly. Combine this with wall-clock time and workload; cumulative totals alone do not show individual request latency or individual pause durations.

## 19. Limitations and analysis caveats

- `jstat` is marked experimental/unsupported in Oracle JDK 21 documentation; options and formats may change.
- Output is a whitespace-separated text table, not an API with a stable schema.
- Avoid writing scripts that depend on column positions or output formatting; if parsing is unavoidable, add version-specific tests and expect to update them when upgrading JDKs.
- Generation/space columns depend on the collector and how the JVM exposes statistics; do not assume identical heap layouts across all collectors.
- Some columns are cumulative counters since JVM startup, not values for just the most recent interval.
- The `-t` timestamp is elapsed time since JVM start, not a wall-clock timestamp.
- A single sample is not enough to conclude a memory leak or GC problem.
- `jstat` does not measure total process RSS, native memory, direct buffers, or thread stacks.
- Do not use `jstat` as a substitute for GC logs, JFR, or heap dumps when root-cause analysis is needed.

For production workloads, choose an appropriate interval. An interval that is too short makes output noisy and hard to read, while continuous collection can add overhead. Start with 1–5 seconds to observe overall trends, then adjust based on the incident and operational requirements.

## 20. Alternative and complementary tools

| Tool | Information | When to use |
|---|---|---|
| `jcmd <pid> GC.heap_info` | High-level heap summary | Quick heap snapshot check |
| `jcmd <pid> GC.class_histogram` | Instance statistics by class | Finding classes consuming the most heap |
| `jcmd <pid> GC.heap_dump` | Creates a heap dump | Analyzing the object graph and retained heap |
| `jcmd <pid> VM.classloader_stats` | Classloader statistics | Investigating classloader/metaspace issues |
| JFR/JDK Mission Control | GC, allocation, CPU, thread, and runtime events over time | Investigating complex or intermittent issues |
| JMX MemoryMXBean/GC MXBeans | Memory pool and GC metrics via API | Integrating metrics into monitoring systems |
| GC logging | Detailed GC events via logs | Analyzing pauses, causes, phases, and collector behavior |

Example checking heap with jcmd:

```sh
jcmd 24680 GC.heap_info
```

Checking classloaders:

```sh
jcmd 24680 VM.classloader_stats
```

Enabling GC logging for the next launch:

```sh
java -Xlog:gc*:file=gc.log:time,uptime,level,tags -jar app.jar
```

GC logging records far more detailed events than `jstat` statistical samples. JFR provides a timeline and many other event types, which is helpful when correlating GC with allocation, CPU, and thread behavior.

## 21. Common errors and troubleshooting

| Symptom | Common cause | Resolution |
|---|---|---|
| `jstat: command not found` | JDK not installed or `JAVA_HOME/bin` not in PATH | Use the right JDK and verify the executable path |
| `Could not find vmid` | Incorrect VMID or process has stopped | Use `jps -l`/`ps` to re-identify the process |
| JVM not visible in `jps` | JVM is in a different container namespace or user lacks permissions | Run in the matching container/user |
| Attach refused | OS permissions or attach mechanism blocked | Check user/group, policies, and runtime configuration |
| `jstat -options` lacks expected option | Different JDK version, vendor, or collector | Use the options supported by the target JDK |
| Metaspace columns missing as expected | Older JDK or different runtime/provider | Check the JDK version and `jstat -options` |
| YGC/FGC counts unchanged | No collection occurred during the sampling window | Increase observation time and check workload |
| `O` rises without dropping | Objects promoted/retained, workload increased, or collector has not reclaimed yet | Compare multiple samples, GC logs, and heap histograms |
| `M` grows continuously | Classes continuously loaded or classloaders not released | Check class loading and classloader statistics |
| Output hard to read over long runs | Header only appears at the top | Use `-h n` to repeat the header |
| Script parses wrong columns | Text output changed across JDKs or has different columns | Avoid fixed parsers; use structured JMX/JFR/APIs |
| Remote VMID fails to connect | `jstatd`/RMI not running or blocked by network/policy | Verify service, registry, port, and policy |
| Heap metrics stable but RSS grows | Off-heap or native memory growing | Check direct memory, NMT, and OS tools |

When the tool cannot connect, check the VMID, permissions, and namespace first. When metrics look abnormal, confirm across multiple samples and other tools before changing heap or GC flags.

## 22. Workflow for monitoring a JVM with jstat

A practical workflow:

1. Identify the application, JDK version, and PID/VMID.
2. Run `jstat -options` to see available statistics.
3. Start with `jstat -gcutil <vmid> 1000 10` to observe GC trends.
4. If you need absolute sizes, run `jstat -gc <vmid> 1000 10`.
5. If full GCs are increasing, run `jstat -gccause` and cross-reference GC logs.
6. If old-space usage is growing, take a histogram or heap dump to find object retention.
7. If Metaspace is growing, check `-class`, `-gcmetacapacity`, and classloader statistics.
8. If you need to inspect JIT activity, use `-compiler` or `-printcompilation`.
9. Record timestamps, workload, heap settings, and collector alongside the samples.
10. Switch to JFR/JMX/GC logs if long-term monitoring or deep analysis is needed.

In an incident report, state the options run, VMID, interval, count, JDK version, and sampling window. Distinguish percentages from KB, cumulative counters from instantaneous values, and heap statistics from native/process memory.

## 23. Checklist

- [ ] Identified the correct JVM and VMID.
- [ ] Checked output options with `jstat -options`.
- [ ] Understood the interval and count syntax.
- [ ] Used `-gcutil` to view utilization and GC counters.
- [ ] Used `-gc` when capacities in KB were needed.
- [ ] Checked GC causes with `-gccause` when needed.
- [ ] Understood the `-gcnew`, `-gcold`, and `-gcmetacapacity` options.
- [ ] Distinguished class loading from JIT compilation statistics.
- [ ] Used `-t` and `-h` when timestamps/repeating headers were needed.
- [ ] Compared multiple samples under comparable workloads.
- [ ] Avoided concluding a memory leak from a single sample.
- [ ] Remembered that `jstat` is experimental/unsupported in JDK 21.
- [ ] Avoided parsing output as a stable protocol.
- [ ] Considered JFR, JMX, GC logs, and `jcmd` for deeper analysis.

## 24. References

- Oracle JDK 21 Tool Reference — The `jstat` Command: https://docs.oracle.com/en/java/javase/21/docs/specs/man/jstat.html
- Oracle JDK 21 Tool Reference — The `jcmd` Command: https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html
- Oracle Java Troubleshooting Guide — Diagnostic Tools: https://docs.oracle.com/en/java/javase/21/troubleshoot/diagnostic-tools.html
- Oracle Java SE 21 API — `java.lang.management`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/package-summary.html

`jstat` provides a quick view into GC, heap spaces, class loading, and JIT compilation for a HotSpot JVM. Choose the right stat option, read counters as trends, and collect multiple samples under comparable workloads. Because the tool is marked experimental/unsupported and its output is not a stable format, use JFR, JMX, GC logs, and `jcmd` diagnostic commands when deep monitoring or analysis is required.
