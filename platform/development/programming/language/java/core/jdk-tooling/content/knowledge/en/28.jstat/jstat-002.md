# Monitoring GC Statistics with jstat

## 1. What is jstat?

`jstat` is a command-line tool in the JDK used to read performance and resource metrics from a running Java HotSpot Virtual Machine (JVM). For Garbage Collection (GC) monitoring, `jstat` reports the capacity and utilization of heap regions, memory pool utilization percentages, GC counts, cumulative GC times, and the cause of the most recent GC.

These metrics are useful when you need to:

- Check whether the heap is approaching its capacity.
- Observe Eden growing and then dropping after a young GC.
- Track the old generation after each collection.
- Detect rapid increases in GC counts or GC time.
- Inspect Metaspace and Compressed Class Space.
- Compare JVM state before and after changing heap or GC configuration.
- Collect periodic samples while an application is running.

`jstat` reads instrumentation data provided by the JVM. The tool does not trigger GC on its own, modify the heap, or replace GC logs or profilers. It provides metric snapshots so operators can identify trends.

## 2. Prerequisites and Identifying the Target JVM

`jstat` monitors an already running JVM. You must identify the correct Virtual Machine Identifier (VMID) before sampling.

Use `jcmd` to list Java processes:

~~~bash
jcmd -l
~~~

Example:

~~~text
10312 GCStatsDemo
18420 com.example.orders.OrderService
27116 com.example.worker.BatchWorker
~~~

In simple local cases, the VMID is usually the process PID. According to the specification, the local VM identifier is often—but not always—the same as the operating-system PID.

You can cross-check with OS tools:

~~~bash
# Linux
ps -ef | grep java

# Windows PowerShell
Get-CimInstance Win32_Process -Filter "Name = 'java.exe'" |
    Select-Object ProcessId, CommandLine
~~~

Practical prerequisites:

- Use a JDK that includes `jstat`, and ensure the target JVM is a HotSpot JVM with compatible instrumentation.
- The user running the tool must have permission to read the target JVM's monitoring data.
- Inside containers, check the PID namespace and the process user.
- If multiple JDKs are installed, invoke `jstat` from a JDK compatible with the monitored JVM.
- Do not guess the PID from the application name; confirm it using `jcmd -l` or OS tools.

Check the statistical options supported by your installation:

~~~bash
jstat -options
~~~

In JDK 24.0.2 used in this lab, the returned list includes:

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

The actual list may vary by JDK, JVM vendor, and platform. Run `jstat -options` in the target environment instead of assuming all installations support the same set of options.

## 3. jstat Syntax

General syntax:

~~~bash
jstat -<option> [-t] [-h<lines>] <vmid> [<interval> [<count>]]
~~~

Where:

| Component | Meaning |
|---|---|
| `-<option>` | Selects the metric group, such as `-gc` or `-gcutil`. |
| `-t` | Adds a timestamp column measured from JVM startup. |
| `-h<lines>` | Repeats the header line after the specified number of samples. |
| `<vmid>` | Identifier of the JVM to monitor, typically the PID for a local JVM. |
| `<interval>` | Sampling interval between two samples. |
| `<count>` | Number of samples to collect before exiting. |

Examples:

~~~bash
# Single snapshot
jstat -gc 18420

# Collect 5 snapshots, 1 second apart
jstat -gc 18420 1s 5

# Collect 10 snapshots of utilization percentages with timestamp
jstat -gcutil -t 18420 1s 10

# Reprint the header every 5 samples
jstat -gc -t -h5 18420 1s 12
~~~

The interval can use milliseconds (`ms`) or seconds (`s`). If no suffix is given, the default unit is milliseconds. For example, `1000` equals 1000 ms; `1s` is also one second.

If `count` is omitted, `jstat` continues sampling until the JVM exits or the user stops the command. Use `Ctrl+C` to end continuous monitoring.

`-t` displays the elapsed time in seconds since the target JVM started. It is not a calendar timestamp. `-h5` reprints the header after every five data lines, making long outputs easier to read without scrolling back to the top of the terminal.

You can view help with:

~~~bash
jstat -help
~~~

General options such as `-help` and `-options` are run standalone, without combining a VMID or output option in the same command.

## 4. Choosing the Right Statistics Option

Key options grouped by purpose:

| Option | Primary Data | When to Use |
|---|---|---|
| `-gc` | Capacity and usage of heap spaces, Metaspace, and GC counters. | Analyzing memory in KB. |
| `-gcutil` | Pool utilization percentages and GC counters. | Quickly spotting trends. |
| `-gccause` | Same metrics as `-gcutil` plus GC causes. | Finding the reason for the most recent collection. |
| `-gccapacity` | Min/max/current capacities of generations and spaces. | Checking heap configuration and expansion headroom. |
| `-gcnew` | Eden, Survivor, and young generation tenuring info. | Investigating young GC and promotion. |
| `-gcnewcapacity` | Capacities of the new generation and survivors. | Checking young generation limits. |
| `-gcold` | Old generation along with Metaspace and Compressed Class Space. | Tracking old space and class metadata. |
| `-gcoldcapacity` | Old generation capacity. | Checking how far the old generation can expand. |
| `-gcmetacapacity` | Metaspace and Compressed Class Space capacities. | Investigating metadata and class loading. |
| `-class` | Class loading/unloading. | Checking class loader activity. |
| `-compiler` | JIT compilation statistics. | Inspecting the compiler. |
| `-printcompilation` | Most recently compiled method. | Viewing recent JIT compilation activity. |

When investigating GC, it is common to start with `-gcutil` to spot trends, switch to `-gc` for detailed capacities and numbers, and then use `-gccause` or the capacity options when digging into root causes.

## 5. Reading jstat -gc Output

`-gc` displays heap statistics and GC counters. A sample JDK 24.0.2 output looks like:

~~~text
S0C S1C S0U S1U EC EU OC OU MC MU CCSC CCSU YGC YGCT FGC FGCT CGC CGCT GCT
0.0 0.0 0.0 0.0 29696.0 2048.0 35840.0 7361.3 320.0 81.7 128.0 6.1 0 0.000 1 0.003 0 0.000 0.003
~~~

The values above are an illustrative snapshot from a test environment. They vary depending on heap size, collector, application activity, and sampling time.

### Eden and Survivor Group

| Column | Meaning | Unit |
|---|---|---|
| `S0C` | Current Survivor space 0 capacity. | KB |
| `S1C` | Current Survivor space 1 capacity. | KB |
| `S0U` | Survivor space 0 utilization. | KB |
| `S1U` | Survivor space 1 utilization. | KB |
| `EC` | Current Eden capacity. | KB |
| `EU` | Eden utilization. | KB |

Eden typically grows as the application allocates objects. When a young GC occurs, surviving objects are moved to Survivor or promoted to the old generation depending on object age, tenuring threshold, and heap state.

Therefore, `EU` may climb steadily and then drop sharply after a young GC. This is normal behavior if collections are fast and post-GC usage remains stable.

### Old Generation Group

| Column | Meaning | Unit |
|---|---|---|
| `OC` | Current old space capacity. | KB |
| `OU` | Old space utilization. | KB |

An increase in `OU` can result from long-lived objects being promoted from the young generation or the application retaining many objects. If old space usage keeps rising across multiple GCs, investigate object retention and potential memory leaks.

A single snapshot with high `OU` is not enough to conclude a memory leak. Look at the post-collection trend, heap capacity, allocation rate, and object data in a heap dump or JFR.

### Metaspace and Compressed Class Space Group

| Column | Meaning | Unit |
|---|---|---|
| `MC` | Metaspace committed capacity. | KB |
| `MU` | Metaspace utilization. | KB |
| `CCSC` | Compressed Class Space committed capacity. | KB |
| `CCSU` | Compressed Class Space utilization. | KB |

Metaspace stores class metadata and is allocated in native memory. It is not a regular object heap region.

Compressed Class Space holds class metadata managed via compressed class pointers when that feature is enabled. If the number of loaded classes grows continuously, Metaspace may grow. Check class loaders and unloaded class counts before concluding there is a classloader leak.

In Java 8 and later, Metaspace replaced the Permanent Generation (PermGen) from older Java versions. Do not apply PermGen column guidance from legacy JDK documentation to modern runtimes.

### GC Counters Group

| Column | Meaning | Unit |
|---|---|---|
| `YGC` | Number of young generation GC events. | Count |
| `YGCT` | Total young GC time. | Seconds |
| `FGC` | Number of full GC events. | Count |
| `FGCT` | Total full GC time. | Seconds |
| `GCT` | Total recorded GC time. | Seconds |

The counters are cumulative since JVM startup. When comparing two snapshots, look at the delta of the counters over that interval rather than only the absolute values.

Some JDK builds, including the verified JDK 24.0.2 environment, also display `CGC` and `CGCT` for concurrent GC count and time. These columns may not appear in every build or option reference. Always read the actual header from the target JVM.

GC time in `jstat` is an aggregate counter, not a list of individual pauses. For concurrent collectors, concurrent GC time does not equate to application stop-the-world pause time. Use GC logs or JFR when you need timestamps and durations of individual events.

## 6. Reading jstat -gcutil: Utilization Percentages

`-gcutil` displays the percentage of capacity used for each pool instead of KB values.

Example output:

~~~text
Timestamp S0 S1 E O M CCS YGC YGCT FGC FGCT CGC CGCT GCT
2.3       -  -  20.69 20.54 25.54 4.74 0 0.000 1 0.003 0 0.000 0.003
3.4       -  -  75.86 20.54 25.54 4.74 0 0.000 1 0.003 0 0.000 0.003
4.4       -  -  27.27 17.24 40.08 5.54 1 0.002 2 0.006 0 0.000 0.007
~~~

Meaning:

| Column | Meaning |
|---|---|
| `S0` | Survivor space 0 utilization percentage. |
| `S1` | Survivor space 1 utilization percentage. |
| `E` | Eden utilization percentage. |
| `O` | Old space utilization percentage. |
| `M` | Metaspace utilization percentage. |
| `CCS` | Compressed Class Space utilization percentage. |

The percentage columns are calculated against each pool's current capacity, not as a share of the total heap. Do not add `E`, `O`, `M`, and `CCS` together into a single combined percentage.

In JDK 24.0.2 testing with G1 GC, `S0` and `S1` show `-`. For collectors or memory pools not represented by these traditional columns, `jstat` may not provide corresponding values. Treat `-` as unavailable/not applicable in that output, not as proof that there are no live objects in Survivor.

With G1, interpret metrics according to the actual collector and combine with GC logs/JFR when you need region-level detail. Do not infer heap state from a single Survivor column.

## 7. Viewing GC Causes with jstat -gccause

`-gccause` displays the same utilization percentages and counters as `-gcutil`, plus two additional columns:

| Column | Meaning |
|---|---|
| `LGCC` | Cause of the last garbage collection. |
| `GCC` | Cause of the current GC, if one is in progress. |

Run:

~~~bash
jstat -gccause 18420 1s 10
~~~

Example output in the test environment:

~~~text
S0 S1 E O M CCS YGC YGCT FGC FGCT CGC CGCT GCT LGCC       GCC
-  -  22.22 19.57 40.95 5.54 2 0.003 3 0.009 0 0.000 0.012 System.gc() No GC
~~~

In the example:

- `LGCC=System.gc()` indicates the most recent GC was triggered by a `System.gc()` call.
- `GCC=No GC` indicates no GC was running at the time of the sample.

Common causes include allocation failure, metadata threshold, explicit GC, or collector-specific reasons. Exact names depend on the JVM and collection type.

Calling `System.gc()` is only a GC request. The JVM may ignore it if configured to do so, such as when explicit GC is disabled. Do not use `System.gc()` in production applications just to force metrics to change.

## 8. Viewing Generation Capacities with jstat -gccapacity

`-gccapacity` focuses on min/max/current capacities of generations and spaces.

~~~bash
jstat -gccapacity 18420
~~~

Common columns:

| Column | Meaning | Unit |
|---|---|---|
| `NGCMN` | Minimum new generation capacity. | KB |
| `NGCMX` | Maximum new generation capacity. | KB |
| `NGC` | Current new generation capacity. | KB |
| `S0C`, `S1C` | Current Survivor space capacities. | KB |
| `EC` | Current Eden capacity. | KB |
| `OGCMN` | Minimum old generation capacity. | KB |
| `OGCMX` | Maximum old generation capacity. | KB |
| `OGC` | Current old generation capacity. | KB |
| `OC` | Current old space capacity. | KB |
| `MCMN` | Minimum Metaspace capacity. | KB |
| `MCMX` | Maximum Metaspace capacity. | KB |
| `MC` | Committed Metaspace. | KB |
| `CCSMN` | Minimum Compressed Class Space capacity. | KB |
| `CCSMX` | Maximum Compressed Class Space capacity. | KB |
| `CCSC` | Committed Compressed Class Space. | KB |

Example from testing:

~~~text
NGCMN NGCMX NGC S0C S1C EC OGCMN OGCMX OGC OC MCMN MCMX MC CCSMN CCSMX CCSC YGC FGC CGC
0.0   65536.0 31744.0 0.0 0.0 31744.0 0.0 65536.0 33792.0 33792.0 0.0 1114112.0 320.0 0.0 1048576.0 128.0 4 5 0
~~~

Current capacity does not necessarily equal maximum capacity. The collector can resize generations based on heap configuration and runtime state.

Do not sum all capacity columns to calculate total heap unless you understand how the active collector maps generations and spaces. Use `jcmd PID GC.heap_info` or GC logs to confirm the heap layout of the running collector.

## 9. Monitoring the Young Generation with jstat -gcnew

`-gcnew` displays metrics specific to the new generation:

~~~bash
jstat -gcnew 18420
~~~

Columns:

| Column | Meaning |
|---|---|
| `S0C`, `S1C` | Survivor 0 and Survivor 1 capacity, KB. |
| `S0U`, `S1U` | Survivor 0 and Survivor 1 utilization, KB. |
| `TT` | Current tenuring threshold. |
| `MTT` | Maximum tenuring threshold. |
| `DSS` | Desired survivor size, KB. |
| `EC` | Eden capacity, KB. |
| `EU` | Eden utilization, KB. |
| `YGC` | Number of young GCs. |
| `YGCT` | Total young GC time, seconds. |

The tenuring threshold controls the object age for promotion from Survivor to the old generation. The JVM can adjust the threshold based on actual survivor usage and the desired survivor size.

If `TT` drops, objects may be promoted earlier. Increased promotion can raise `OU`. However, do not conclude a promotion problem from a single sample; examine a series of samples and the collector configuration.

## 10. Checking Young Generation Capacity

`-gcnewcapacity` reports the limits and current capacity of the new generation:

~~~bash
jstat -gcnewcapacity 18420
~~~

Common columns:

- `NGCMN`, `NGCMX`, `NGC`: minimum, maximum, and current new generation capacity.
- `S0CMX`, `S0C`: maximum and current Survivor 0 capacity.
- `S1CMX`, `S1C`: maximum and current Survivor 1 capacity.
- `ECMX`, `EC`: maximum and current Eden capacity.
- `YGC` and `FGC`: young GC and full GC counts.

This data is useful for checking how much the young generation can expand and whether its current capacity changes during execution.

Generation/space columns are collector-dependent. With G1, a region-based heap does not necessarily map directly to a fixed Eden/Survivor model across all traditional columns. Interpret the output according to the actual collector and JDK.
## 11. Monitoring Old Generation and Metaspace

`-gcold` provides old generation and Metaspace metrics:

~~~bash
jstat -gcold 18420
~~~

Common columns:

| Column | Meaning |
|---|---|
| `MC` | Metaspace committed, KB. |
| `MU` | Metaspace used, KB. |
| `CCSC` | Compressed Class Space committed, KB. |
| `CCSU` | Compressed Class Space used, KB. |
| `OC` | Old space capacity, KB. |
| `OU` | Old space used, KB. |
| `YGC`, `FGC` | Young GC and full GC counts. |
| `FGCT`, `GCT` | Full GC time and total GC time, seconds. |

Old generation capacity:

~~~bash
jstat -gcoldcapacity 18420
~~~

Main columns:

- `OGCMN`: old generation minimum capacity.
- `OGCMX`: old generation maximum capacity.
- `OGC`: old generation current capacity.
- `OC`: old space current capacity.
- `YGC`, `FGC`, `FGCT`, and `GCT`: GC-related counters.

Monitoring Metaspace:

~~~bash
jstat -gcmetacapacity 18420
~~~

Columns include `MCMN`, `MCMX`, `MC`, `CCSMN`, and `CCSMX` along with GC counters.

Metaspace growth can be the result of normal class loading. If loaded classes increase without unloading in an application that uses many dynamic class loaders, check class loader lifecycles and class unloading. A Metaspace metric alone does not prove a leak.

## 12. Additional Statistics: Class Loading and JIT

`jstat` also provides options that do not directly measure GC but are helpful when analyzing JVM behavior.

### Class loader

~~~bash
jstat -class 18420
~~~

Columns:

- `Loaded`: number of classes loaded.
- First `Bytes`: KB of classes loaded.
- `Unloaded`: number of classes unloaded.
- Second `Bytes`: KB of classes unloaded.
- `Time`: time spent performing class load/unload operations.

If `Loaded` grows continuously, compare `Unloaded` and Metaspace. In applications using many dynamic proxies, plugins, or custom class loaders, class loading/unloading is a worthwhile area to investigate.

### JIT compiler

~~~bash
jstat -compiler 18420
~~~

Columns:

| Column | Meaning |
|---|---|
| `Compiled` | Number of compilation tasks performed. |
| `Failed` | Number of compilation tasks that failed. |
| `Invalid` | Number of compilation tasks invalidated. |
| `Time` | Time spent performing compilation. |
| `FailedType` | Compilation type of the most recent failure. |
| `FailedMethod` | Class and method of the most recent failure. |

View the most recently compiled method:

~~~bash
jstat -printcompilation 18420
~~~

Columns include `Compiled`, `Size`, `Type`, and `Method`. This reports information about the most recent method compilation, not a complete list of every method in the code cache.

## 13. Java 17 Allocation Example for Observing GC

Create `GCStatsDemo.java`:

~~~java
import java.util.ArrayDeque;
import java.util.Deque;

public class GCStatsDemo {
    public static void main(String[] args) throws Exception {
        Deque<byte[]> retained = new ArrayDeque<>();
        long cycle = 0;

        System.out.println("GCStatsDemo ready");

        while (true) {
            for (int i = 0; i < 12; i++) {
                retained.addLast(new byte[256 * 1024]);

                if (retained.size() > 24) {
                    retained.removeFirst();
                }
            }

            cycle++;

            if (cycle % 8 == 0) {
                System.gc();
                System.out.println("requested explicit GC at cycle " + cycle);
            }

            Thread.sleep(250);
        }
    }
}
~~~

The program allocates objects in batches, retains a bounded number of arrays to maintain a steady live set, and drops older arrays to keep allocating. Every eight cycles, it requests an explicit GC so you can observe the GC cause column in the lab.

This is a lab program with an infinite loop. The `System.gc()` call is strictly for observation; do not use it as a GC tuning technique in production applications.

Compile:

~~~bash
mkdir -p out
javac --release 17 -d out src/GCStatsDemo.java
~~~

Run with a fixed 64 MB heap and G1 GC:

~~~bash
java -Xms64m -Xmx64m -XX:+UseG1GC -cp out GCStatsDemo
~~~

Stdout starts with:

~~~text
GCStatsDemo ready
requested explicit GC at cycle 8
requested explicit GC at cycle 16
~~~

Subsequent lines appear over time. Exact timing and cycle counts may vary depending on machine speed.

## 14. End-to-End jstat Hands-On Workflow

Open a second terminal while `GCStatsDemo` is running.

Find the PID:

~~~bash
jcmd -l
~~~

Assume the PID is `10312`.

Take a heap snapshot:

~~~bash
jstat -gc 10312
~~~

Track utilization percentages across five samples:

~~~bash
jstat -gcutil -t 10312 1s 5
~~~

Track GC causes:

~~~bash
jstat -gccause 10312 1s 10
~~~

Check capacities:

~~~bash
jstat -gccapacity 10312
jstat -gcmetacapacity 10312
~~~

Check young and old generations:

~~~bash
jstat -gcnew 10312
jstat -gcnewcapacity 10312
jstat -gcold 10312
jstat -gcoldcapacity 10312
~~~

View class loading and compiler stats:

~~~bash
jstat -class 10312
jstat -compiler 10312
jstat -printcompilation 10312
~~~

Print timestamps and repeat headers:

~~~bash
jstat -gc -t -h5 10312 1s 12
~~~

Cross-check the heap summary with `jcmd`:

~~~bash
jcmd 10312 GC.heap_info
jcmd 10312 VM.flags
~~~

In JDK 24.0.2 testing, `jstat` displayed Eden/old/metaspace usage, capacities, young/full GC counters, GC times, and the `System.gc()` cause. `jcmd GC.heap_info` confirmed the G1 heap had 64 MB total committed/reserved in the lab configuration.

When finished, stop the demo program with `Ctrl+C` in the terminal running Java. Do not leave test processes running in the background longer than needed.

## 15. Reading GC Trends Instead of Isolated Numbers

A single snapshot only shows the state at one point in time. To spot issues, compare multiple samples and observe what happens before and after collections.

### Eden grows rapidly and drops after young GC

If `E` climbs steadily and drops after `YGC` increments, the application is allocating objects and the JVM is reclaiming or moving objects in the young generation. This is generally normal behavior.

Investigate further if young GCs occur too frequently, GC time rises, or throughput drops.

### Old space grows across multiple collections

If `O` or `OU` keeps rising after multiple young GCs, many objects may be surviving and getting promoted. If old occupancy stays high after a full GC, check object retention, unbounded caches, or potential memory leaks.

Do not conclude a leak solely from old space growing over a short period. A workload might be warming up or intentionally holding a cache.

### GC counters increase rapidly

`YGC`, `FGC`, and collector-specific counters are cumulative. Compute the delta between two samples:

- `ΔYGC`: number of new young GCs during the observation window.
- `ΔFGC`: number of new full GCs during the observation window.
- `ΔYGCT` and `ΔFGCT`: additional GC time accumulated during that window.

If GC counts climb rapidly alongside high latency, allocation pressure, or high CPU usage, inspect GC logs/JFR for exact collection types and pauses.

### Metaspace grows

If `MU` and `M` increase, check class loading, class unloading, and class loader lifecycles. Metaspace can grow as the application loads more classes; growth is only concerning if it never stabilizes or is not reclaimed across repeated workloads.

### Capacity changes

`-gccapacity` shows current capacity alongside min/max. If a heap or generation changes capacity, the JVM may be resizing regions based on allocation/promotion demand. Cross-check with `-Xms`, `-Xmx`, the collector, and GC logs.

## 16. Limitations to Understand When Reading Metrics

**Pool percentages are not total heap percentages.** `E` and `O` are percentages of each pool's own capacity. Do not add them to compute total heap utilization.

**Counters are cumulative.** `YGC` and `FGC` generally increase monotonically from JVM startup. Compare deltas over time.

**GC time is not a pause log.** `YGCT`, `FGCT`, and `GCT` are aggregate times. They do not tell you when individual pauses started, how long each lasted, or how application threads were stopped.

**Collectors represent spaces differently.** Some traditional columns such as Survivor 0/1 may not have values in certain configurations. A `-` does not mean all objects in that region have disappeared.

**Metaspace is not part of the Java heap.** `MC` and `MU` measure metadata in native memory. Do not add Metaspace to heap occupancy as if it were an object heap pool.

**Metrics can change across JDKs.** Headers, column names, and option sets are not a guaranteed stable interface across all releases.

**jstat does not show which objects are live.** If you suspect a memory leak, use a heap dump, class histogram, JFR, or a heap analysis tool to identify the objects and the references keeping them alive.

## 17. Monitoring Remote JVMs with VMID

In addition to a local PID, a VMID can include a hostname and RMI port. Example:

~~~bash
jstat -gcutil 40496@remote.domain 1s 10
~~~

Remote monitoring typically requires `jstatd` and an RMI registry on the target host. Configuring remote services must comply with your organization's network and security policies.

Key points to note:

- A remote VMID does not mean `jstat` can automatically connect to any JVM over IP.
- Remote monitoring requires appropriate server instrumentation and a configured RMI connection.
- Restrict firewalls, ports, and access permissions.
- Do not expose RMI monitoring broadly to the Internet.
- In containers, determine the VMID within an environment that can access the target JVM.

If you are only monitoring a local JVM, using the local PID/VMID is the simplest approach.

## 18. Common Errors and Troubleshooting

| Symptom | Common Cause | Resolution |
|---|---|---|
| `jstat` command not found | JDK `bin` is not in `PATH`. | Check `JAVA_HOME` and run the executable from `bin`. |
| VMID not found | Wrong PID, JVM exited, or VMID is not a local PID. | Run `jcmd -l` and verify the process. |
| Desired statistics option unavailable | Current JDK/vendor does not provide that option. | Run `jstat -options` in the target environment. |
| Output shows `-` for S0/S1 | Collector or memory pool does not report those values. | Check the collector and other columns; do not treat `-` as zero live data. |
| Eden stays near 100% | Application is allocating fast and a young GC is imminent. | Observe the next sample, `YGC`, and GC time. |
| Old occupancy increasing | Objects are being promoted or retained long-term. | Track post-GC usage and investigate retention with JFR/heap dump. |
| Metaspace increasing | Classes are being loaded or class loaders are not freed. | Check Loaded/Unloaded, class loader lifecycles, and Metaspace trends. |
| Expected GCC cause not visible | No GC occurred during the sample or collector reports a different cause. | Take more samples and cross-check GC logs. |
| Irregular sampling intervals | High host load or scheduling delays the command. | Use timestamps, increase the interval, and avoid overly tight polling. |
| jstat cannot connect in a container | Different PID namespace, user, or perfdata visibility. | Run in the matching namespace/user and verify JVM instrumentation. |
| Output parsing script breaks after JDK upgrade | Header or output format changed. | Avoid relying on custom column parsers; use more stable monitoring APIs. |

## 19. Production GC Monitoring Workflow

1. Identify the exact PID, JDK version, and active collector.
2. Check heap configuration with `jcmd PID VM.flags`.
3. Capture a baseline with `jstat -gcutil -t PID 1s 10`.
4. If percentages or counters look abnormal, gather details with `jstat -gc` and `jstat -gccause`.
5. Inspect generation capacities with `jstat -gccapacity`.
6. If Metaspace is suspect, use `jstat -gcmetacapacity` and `jstat -class`.
7. Compare counter deltas over the same time window.
8. Correlate with request latency, throughput, allocation rate, CPU, and application logs.
9. Collect GC logs or JFR if you need pause durations, event timelines, and detailed causes.
10. Record the collector, heap flags, sampling timestamps, and JDK version in your investigation report.

### Enabling GC logging when per-event detail is needed

On modern HotSpot JVMs, you can configure Unified Logging at JVM startup:

~~~bash
java -Xlog:gc*:file=gc.log:time,uptime,level,tags -jar app.jar
~~~

GC logs show individual events and pauses in much finer detail than `jstat`'s aggregate metrics. Changing JVM options usually requires restarting the application; follow your system's deployment procedures.

### Combining with JFR

JFR records runtime events over time, which is useful when correlating GC with allocations, threads, locks, class loading, and application activity. You can use `jcmd PID JFR.start`, `JFR.check`, `JFR.dump`, and `JFR.stop` to control recordings if supported by the JVM.

## 20. Stability Notes for jstat

Oracle JDK 24 documentation marks `jstat` as an experimental and unsupported tool. Options and functionality may change or be removed in future releases.

The documentation also advises against writing scripts that depend on parsing `jstat` output because the format can change. Therefore:

- Use `jstat` for interactive diagnostics and quick checks.
- Do not treat column names and column order as a stable API.
- Do not build production alerting systems that depend on unguarded output parsers.
- For long-term monitoring, prefer JMX, metrics exporters, JFR, or observability platforms with stable schemas.
- Re-verify output and options when upgrading the JDK.

## 21. GC Statistics Reading Checklist

- Confirmed the exact JVM and VMID.
- Checked supported options with `jstat -options`.
- Chose appropriately among `-gc`, `-gcutil`, and `-gccause`.
- Understood that capacity/used columns are in KB and utilization columns are in %.
- Distinguished Eden, Survivor, Old Generation, Metaspace, and Compressed Class Space.
- Read YGC/FGC alongside cumulative times, not just counts.
- Understood LGCC and GCC when using `-gccause`.
- Checked the active collector before interpreting Survivor columns.
- Compared multiple samples and used timestamps when needed.
- Cross-checked with heap flags, GC logs, JFR, and application metrics.
- Avoided concluding a memory leak from a single snapshot.
- Avoided using `jstat` output as a stable parser format for production automation.

## 22. References

- [The jstat Command — JDK 24](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jstat.html)
- [The jcmd Command — JDK 24](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jcmd.html)
- [Java Flight Recorder API — JDK 24](https://docs.oracle.com/en/java/javase/24/docs/api/jdk.jfr/jdk/jfr/package-summary.html)

`jstat` helps you observe GC statistics through JVM snapshots: heap capacities, pool utilization percentages, collection counts, GC times, and the most recent GC cause. Read the units carefully, track deltas over time, account for the active collector and JDK, and use GC logs or JFR to confirm pause, allocation, and object retention issues.
