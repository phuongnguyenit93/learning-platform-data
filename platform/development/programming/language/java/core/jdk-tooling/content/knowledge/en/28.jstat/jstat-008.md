# Reading jstat Columns in Java

**jstat** is a JDK command-line tool for sampling performance statistics and resource utilization of a running Java HotSpot VM. It is especially useful when you need to observe the heap, garbage collector (GC) regions, GC counts, GC times, metaspace, class loading, and JIT compilation.

jstat column names are abbreviations such as S0C, EU, O, YGC, YGCT, FGC, and GCT. To interpret the output accurately, you need to understand which metric group a column belongs to, its unit, whether the value is instantaneous or cumulative, and what changes between samples indicate.

This guide focuses on how to read each column group, correlate columns with one another, and use sample series to identify trends. Available options and output formats can vary across JDK versions, platforms, and JVMs. Always check the supported options on the target machine with jstat -options before using them.

## 1. What Does jstat Measure?

jstat uses built-in instrumentation in the HotSpot VM to display performance and resource statistics for a running application. Common data groups include:

- **Heap and GC**: capacity and utilization of Eden, Survivor, and Old Generation.
- **GC counters**: Young GC and Full GC counts, along with the time spent on GC.
- **Metaspace**: committed capacity and used capacity.
- **Compressed Class Space**: capacity allocated for compressed class metadata.
- **Class loading**: number of classes loaded, unloaded, and time spent processing them.
- **JIT compiler**: number of compilation tasks, failed compilations, and the most recently compiled method.

jstat is well suited for observing trends over time. A single output line represents one sample at a point in time; multiple consecutive lines show how counters and memory regions change.

jstat does not explain the root cause of an issue on its own. For example, a rising Old Generation percentage could be caused by normal object promotion, a workload shift, or unexpected object retention. Correlate multiple columns, workload behavior, and other diagnostic tools before drawing conclusions.

## 2. Sampling Syntax and Selecting a JVM

General syntax:

~~~bash
jstat -<statOption> [-t] [-h n] <vmid> [interval [count]]
~~~

Where:

- statOption selects the metric group to display.
- -t adds a timestamp column showing elapsed time since the JVM started.
- -h n reprints the header every n samples.
- vmid identifies the target JVM.
- interval is the time between samples.
- count is the number of samples to collect.

Example: collect 10 GC utilization samples, one per second:

~~~bash
jstat -gcutil 2125 1000 10
~~~

Example: add a timestamp and reprint the header every 5 lines:

~~~bash
jstat -gcutil -t -h 5 2125 1000 10
~~~

If count is omitted, jstat continues sampling until the JVM exits or the operator stops the command. If interval is omitted, the command prints a single sample.

The default unit for interval is milliseconds. You can specify seconds or milliseconds using the syntax supported by your current JDK. Both interval and count must be positive numbers.

### Finding the Target JVM

Use jps:

~~~bash
jps -l
~~~

Example:

~~~text
2125 com.acme.JstatDemo
5485 jdk.jcmd/sun.tools.jcmd.JCmd
~~~

2125 is an example LVMID. The LVMID is usually the operating system PID, though it is not guaranteed to always match the OS PID. jps might also not list JVMs running in separate Docker processes; in that case, determine the LVMID within the appropriate environment or PID namespace.

You can inspect processes using OS tools. On Linux:

~~~bash
ps -eo pid,user,group,args
~~~

On Windows, use Task Manager or PowerShell to match process IDs with their command lines.

jstat is typically used on local JVMs. For remote monitoring, VMID can specify a hostname and requires jstatd on the target machine. Do not enable remote monitoring services indiscriminately; enforce proper network, account, and access controls.

## 3. Listing Available statOptions

Before choosing columns, run:

~~~bash
jstat -options
~~~

This command lists the statOptions supported by the jstat installation on the current platform.

Common options include:

| Option | Statistics Group |
|---|---|
| -class | Class loader |
| -compiler | JIT compiler |
| -gc | Heap capacity, utilization, and GC counters |
| -gccapacity | Generation and space capacities |
| -gccause | GC utilization and the cause of the last/current GC |
| -gcnew | New Generation behavior |
| -gcnewcapacity | New Generation capacities |
| -gcold | Old Generation and metaspace |
| -gcoldcapacity | Old Generation capacities |
| -gcmetacapacity | Metaspace capacities |
| -gcutil | Utilization summary in percentages |
| -printcompilation | Information on the most recently compiled method |

Not every JVM or collector provides all metric groups in the same way. If an option does not appear in jstat -options, do not assume it can be used on that machine.

## 4. Column Naming Conventions

jstat column names are typically composed of abbreviations:

- C: Capacity, current or maximum capacity depending on the column.
- U: Used, amount currently in use.
- MN: Minimum, minimum capacity.
- MX: Maximum, maximum capacity.
- S0 and S1: Survivor Space 0 and Survivor Space 1.
- E: Eden.
- O: Old Generation/Old Space.
- M: Metaspace.
- CCS: Compressed Class Space.
- YGC: Young Garbage Collection count.
- FGC: Full Garbage Collection count.
- T: Time or threshold depending on the column group.

Examples:

| Column | Interpretation |
|---|---|
| S0C | Current capacity of Survivor Space 0 |
| S0U | Used space in Survivor Space 0 |
| EC | Current capacity of Eden |
| EU | Used space in Eden |
| OC | Current capacity of Old Space |
| OU | Used space in Old Space |
| MC | Committed Metaspace |
| MU | Used Metaspace |
| YGC | Number of Young GC events |
| YGCT | Total Young GC time |

C and U usually appear in pairs so you can compare available capacity against current usage. If you need a usage percentage, read the corresponding column in -gcutil or calculate Used/Capacity × 100 when both columns measure the same space.

## 5. Reading -gc: Capacity and Utilization

Command:

~~~bash
jstat -gc 2125 1000 10
~~~

The -gc group displays capacities and usage for Survivor, Eden, Old Space, Metaspace, and Compressed Class Space along with GC counters.

Common columns:

| Column | Meaning | Unit |
|---|---|---|
| S0C | Current Survivor Space 0 capacity | KB |
| S1C | Current Survivor Space 1 capacity | KB |
| S0U | Survivor Space 0 utilization | KB |
| S1U | Survivor Space 1 utilization | KB |
| EC | Current Eden capacity | KB |
| EU | Eden utilization | KB |
| OC | Current Old Space capacity | KB |
| OU | Old Space utilization | KB |
| MC | Metaspace committed size | KB |
| MU | Metaspace utilization | KB |
| CCSC | Compressed Class Space committed size | KB |
| CCSU | Compressed Class Space used | KB |
| YGC | Number of Young GC events | Count |
| YGCT | Total Young GC time | Seconds |
| FGC | Number of Full GC events | Count |
| FGCT | Total Full GC time | Seconds |
| GCT | Total GC time | Seconds |

### Capacity and Used

Example:

~~~text
S0C    S1C    S0U    S1U    EC      EU      OC      OU
512.0  512.0  120.0  0.0    8192.0  6144.0  32768.0  12288.0
~~~

How to read it:

- Survivor 0 has a capacity of 512 KB, with 120 KB used.
- Survivor 1 has a capacity of 512 KB, with 0 KB used.
- Eden has a capacity of 8,192 KB, with 6,144 KB used.
- Old Space has a capacity of 32,768 KB, with 12,288 KB used.

These numbers are illustrative examples only. Do not sum all capacities in a single row to estimate total process RAM; heap, metaspace, thread stacks, and native memory belong to different scopes.

### Metaspace and Compressed Class Space

MC/MU and CCSC/CCSU are two separate pairs:

- MC is the committed metaspace size.
- MU is the used metaspace size.
- CCSC is the committed compressed class space size.
- CCSU is the used compressed class space size.

Metaspace stores class metadata in native memory. It is not part of the Java heap like regular objects. CCS is the region associated with compressed class pointers when the JVM uses that mechanism.

If MU or CCSU grows continuously across many samples, investigate class loading, class unloading, dynamic proxies, generated classes, or class loader lifecycles. A single increase is not enough to conclude there is a class loader leak.

## 6. Reading -gcutil: Utilization Percentages

Command:

~~~bash
jstat -gcutil 2125 1000 10
~~~

-gcutil is a popular option for quickly observing heap region utilization and GC counters.

Columns:

| Column | Meaning |
|---|---|
| S0 | Survivor Space 0 utilization as a percentage of current capacity |
| S1 | Survivor Space 1 utilization as a percentage of current capacity |
| E | Eden utilization as a percentage of current capacity |
| O | Old Space utilization as a percentage of current capacity |
| M | Metaspace utilization as a percentage of current capacity |
| CCS | Compressed Class Space utilization percentage |
| YGC | Number of Young GC events |
| YGCT | Total Young GC time, in seconds |
| FGC | Number of Full GC events |
| FGCT | Total Full GC time, in seconds |
| GCT | Total GC time, in seconds |

Example:

~~~text
S0     S1     E      O      M      CCS    YGC   YGCT    FGC   FGCT   GCT
0.00   75.00  82.00  40.00  65.00  45.00  10    0.450   1     0.100  0.550
0.00   75.00  98.00  40.00  65.00  45.00  10    0.450   1     0.100  0.550
75.00  0.00   2.00   42.00  65.00  45.00  11    0.470   1     0.100  0.570
~~~

How to read it:

- E rises from 82% to 98% before a Young GC.
- After GC, E drops to 2%.
- YGC increments from 10 to 11.
- S0/S1 swap roles; one Survivor Space receives the surviving objects.
- O increases from 40% to 42%, likely because some objects were promoted to the Old Generation.
- GCT increases from 0.550 to 0.570 seconds, meaning cumulative GC time increased by 0.020 seconds.

This is simulated data to illustrate how to read the columns, not measured output from a specific JVM.

### Why Does E Typically Rise and Then Drop?

The application allocates new objects in Eden. When Eden fills up, a Young GC can occur. Surviving objects are moved to a Survivor space or promoted to the Old Generation; unreachable objects are reclaimed. Therefore, E typically climbs between Young GCs and drops after collection.

### Why Do S0 and S1 Alternate?

In a copying generational collector, the two Survivor spaces can alternate roles as source and destination after each Young GC. As a result, S0 may be in use in one sample and nearly empty in the next while S1 rises. Do not treat a sharp swing between S0 and S1 across samples as an anomaly on its own.

### Why Does O Increase?

Objects that survive multiple Young GCs can be promoted to the Old Generation. An increase in O after a Young GC can be normal behavior. What matters is whether O drops, stabilizes, or keeps climbing over multiple GC cycles.

If O steadily increases and does not drop after appropriate collections, investigate the live set, caches, collections, listeners, and object references using a heap dump or JFR. jstat only shows utilization trends; it does not identify which objects are retaining memory.

## 7. Reading -gccause: Adding GC Causes

Command:

~~~bash
jstat -gccause 2125 1000 10
~~~

-gccause displays the same columns as -gcutil and adds:

| Column | Meaning |
|---|---|
| LGCC | Cause of last garbage collection |
| GCC | Cause of current garbage collection, if any |

Cause strings can vary by collector and JDK. Some strings may describe allocation failure, explicit GC, or a specific collection type.

Illustrative example:

~~~text
S0 S1 E O M CCS YGC YGCT FGC FGCT GCT LGCC              GCC
0  70 80 45 60 40 12  0.5  1   0.1  0.6 Allocation Failure No GC
~~~

How to use it:

- Check LGCC to see what triggered the most recent event.
- Check GCC to see the reported cause of a collection currently in progress.
- Correlate with the samples where YGC or FGC increments.
- Do not assume every Allocation Failure is an error; it can be a normal trigger when an allocation region needs to be reclaimed.

If you see repeated explicit GCs, check for code calling System.gc(), frameworks, or runtime settings. Do not disable explicit GC based on a single jstat line alone; verify the cause and impact first.

## 8. Reading -gccapacity: Generation Capacities

Command:

~~~bash
jstat -gccapacity 2125 1000 10
~~~

This group focuses on the capacities of the New Generation, Old Generation, Survivor, Eden, Metaspace, and Compressed Class Space.

Common columns:

| Column | Meaning | Unit |
|---|---|---|
| NGCMN | Minimum New Generation capacity | KB |
| NGCMX | Maximum New Generation capacity | KB |
| NGC | Current New Generation capacity | KB |
| S0C | Current Survivor 0 capacity | KB |
| S1C | Current Survivor 1 capacity | KB |
| EC | Current Eden capacity | KB |
| OGCMN | Minimum Old Generation capacity | KB |
| OGCMX | Maximum Old Generation capacity | KB |
| OGC | Current Old Generation capacity | KB |
| OC | Current Old Space capacity | KB |
| MCMN | Minimum Metaspace capacity | KB |
| MCMX | Maximum Metaspace capacity | KB |
| MC | Metaspace committed size | KB |
| CCSMN | Minimum Compressed Class Space capacity | KB |
| CCSMX | Maximum Compressed Class Space capacity | KB |
| CCSC | Compressed Class Space committed size | KB |
| YGC | Number of Young GC events | Count |
| FGC | Number of Full GC events | Count |

Capacity is not the amount of live object data. Read NGC or OGC to see the currently allocated region size; read EU/OU or the E/O percentages to understand utilization.

Example:

~~~text
NGCMN  NGCMX    NGC     S0C    S1C     EC     OGCMN  OGCMX    OGC      OC
1024.0  65536.0  8192.0  512.0  512.0   7168.0  4096.0  131072.0  32768.0  32768.0
~~~

In this example, the New Generation currently has an 8 MB capacity and can expand up to 64 MB per the reported limit; the Old Generation currently has a 32 MB capacity and a 128 MB maximum.

These illustrative values can depend on the collector and how the JVM models generations. Do not apply the exact same New/Old Generation model to every collector.

## 9. Reading -gcnew: New Generation Behavior

Command:

~~~bash
jstat -gcnew 2125 1000 10
~~~

-gcnew focuses on Eden and the Survivor spaces, along with tenuring information.

Columns:

| Column | Meaning | Unit |
|---|---|---|
| S0C | Survivor 0 capacity | KB |
| S1C | Survivor 1 capacity | KB |
| S0U | Survivor 0 used | KB |
| S1U | Survivor 1 used | KB |
| TT | Current tenuring threshold | Age cycles |
| MTT | Maximum tenuring threshold | Age cycles |
| DSS | Desired survivor size | KB |
| EC | Eden capacity | KB |
| EU | Eden used | KB |
| YGC | Number of Young GC events | Count |
| YGCT | Total Young GC time | Seconds |

### TT and MTT

The tenuring threshold is the age threshold used to decide when objects that survive long enough can be promoted to the Old Generation. Object age is measured in the number of relevant collections survived, not in seconds.

MTT is the maximum tenuring threshold. The actual TT can adjust dynamically based on Survivor Space pressure and surviving data.

### DSS

DSS is the desired survivor size—the Survivor target size the JVM aims to use under its GC policy. If surviving objects exceed that target, the JVM may lower TT to promote objects sooner.

### Example

~~~text
S0C   S1C   S0U   S1U   TT  MTT  DSS   EC       EU      YGC  YGCT
512.0 512.0 80.0  0.0   15  15   256.0 8192.0  7000.0  20   0.620
512.0 512.0 0.0   190.0  2  15   256.0 8192.0  120.0   21   0.645
~~~

After the Young GC, EU drops sharply and S1U rises. TT drops from 15 to 2 in this example, suggesting the JVM may be lowering the age threshold before promoting objects due to Survivor pressure. This is an illustrative example; drawing a conclusion requires observing more samples and the actual collector behavior.

## 10. Reading -gcnewcapacity: New Generation Limits

Command:

~~~bash
jstat -gcnewcapacity 2125 1000 10
~~~

Common columns:

| Column | Meaning | Unit |
|---|---|---|
| NGCMN | Minimum New Generation capacity | KB |
| NGCMX | Maximum New Generation capacity | KB |
| NGC | Current New Generation capacity | KB |
| S0CMX | Maximum Survivor 0 capacity | KB |
| S0C | Current Survivor 0 capacity | KB |
| S1CMX | Maximum Survivor 1 capacity | KB |
| S1C | Current Survivor 1 capacity | KB |
| ECMX | Maximum Eden capacity | KB |
| EC | Current Eden capacity | KB |
| YGC | Number of Young GC events | Count |
| FGC | Number of Full GC events | Count |

This group answers questions about New Generation limits and capacities. It does not directly show how many objects are live; to check usage, read -gc or -gcnew.

If NGC approaches NGCMX while EU is frequently high and YGC climbs rapidly, you may need to examine heap sizing or allocation pressure. Do not increase the heap automatically based solely on capacity; compare against live set size, GC times, and RAM/container limits.

## 11. Reading -gcold: Old Generation and Metaspace

Command:

~~~bash
jstat -gcold 2125 1000 10
~~~

Common columns:

| Column | Meaning | Unit |
|---|---|---|
| MC | Metaspace committed size | KB |
| MU | Metaspace utilization | KB |
| CCSC | Compressed Class Space committed size | KB |
| CCSU | Compressed Class Space used | KB |
| OC | Old Space capacity | KB |
| OU | Old Space used | KB |
| YGC | Number of Young GC events | Count |
| FGC | Number of Full GC events | Count |
| FGCT | Total Full GC time | Seconds |
| GCT | Total GC time | Seconds |

-gcold lets you observe two distinct areas in the same output:

- Old Space: OC and OU.
- Class metadata: MC/MU and CCSC/CCSU.

Do not confuse MU with OU. MU is Metaspace utilization; OU is Old Space utilization. Metaspace resides outside the Java heap.

If MU rises continuously, check loaded classes, unloaded classes, and class loader lifecycles. If OU rises after every GC cycle without dropping, investigate live objects and promotion.

## 12. Reading -gcoldcapacity: Old Generation Capacity

Command:

~~~bash
jstat -gcoldcapacity 2125 1000 10
~~~

Columns:

| Column | Meaning | Unit |
|---|---|---|
| OGCMN | Minimum Old Generation capacity | KB |
| OGCMX | Maximum Old Generation capacity | KB |
| OGC | Current Old Generation capacity | KB |
| OC | Current Old Space capacity | KB |
| YGC | Number of Young GC events | Count |
| FGC | Number of Full GC events | Count |
| FGCT | Total Full GC time | Seconds |
| GCT | Total GC time | Seconds |

Example output:

~~~text
Timestamp  OGCMN  OGCMX    OGC      OC      YGC  FGC  FGCT  GCT
150.1      1408.0 60544.0  11696.0  11696.0 194  80   2.874 3.799
150.4      1408.0 60544.0  13820.0  13820.0 194  81   2.938 3.863
150.7      1408.0 60544.0  13820.0  13820.0 194  81   2.938 3.863
~~~

How to read it:

- OGC increases from 11,696 KB to 13,820 KB.
- FGC increments from 80 to 81.
- FGCT increases from 2.874 seconds to 2.938 seconds.
- GCT increases from 3.799 seconds to 3.863 seconds.
- OGCMX remains 60,544 KB, so the current capacity still has room to grow within the reported limit.

Growing capacity does not automatically mean a leak. The JVM may expand a generation to accommodate allocation or promotion. Check OU, utilization percentage, Full GCs, and post-collection trends.

## 13. Reading -gcmetacapacity: Metaspace Capacity

Command:

~~~bash
jstat -gcmetacapacity 2125 1000 10
~~~

Common columns:

| Column | Meaning | Unit |
|---|---|---|
| MCMN | Minimum Metaspace capacity | KB |
| MCMX | Maximum Metaspace capacity | KB |
| MC | Metaspace committed size | KB |
| CCSMN | Minimum Compressed Class Space capacity | KB |
| CCSMX | Maximum Compressed Class Space capacity | KB |
| YGC | Number of Young GC events | Count |
| FGC | Number of Full GC events | Count |
| FGCT | Total Full GC time | Seconds |
| GCT | Total GC time | Seconds |

Use this group when investigating:

- Applications that generate many classes dynamically.
- Proxy frameworks or bytecode generation.
- Repeated creation of ClassLoaders.
- Metaspace growth over time.
- Class unloading not occurring as expected.

MC is committed capacity, not the actual bytes of metadata currently in use. To check actual usage, compare against MU in -gc or -gcold.

If MC rises while MU stays flat, the JVM may simply have committed additional memory. If MU rises continuously alongside increasing Loaded counts and flat Unloaded counts, inspect class loaders and dynamic class generation.

## 14. Reading -class: Class Loading Statistics

Command:

~~~bash
jstat -class 2125 1000 10
~~~

Columns:

| Column | Meaning | Unit |
|---|---|---|
| Loaded | Total number of classes loaded | Classes |
| Bytes | Total size of loaded class data | KB |
| Unloaded | Total number of classes unloaded | Classes |
| Bytes | Total size of unloaded class data | KB |
| Time | Time spent performing class loading/unloading | Seconds |

Example:

~~~text
Loaded  Bytes   Unloaded  Bytes  Time
8500    12400.0 120       180.0  4.250
8550    12520.0 120       180.0  4.280
8600    12650.0 140       205.0  4.310
~~~

The Loaded and Unloaded counters are typically cumulative. When Loaded rises quickly, the application may be loading many new classes. This can be normal during startup, warm-up, or plugin loading.

If class loading continues rising over a long period, combined with growing Metaspace and low class unloading, check for:

- Continuous dynamic class or proxy generation.
- Frameworks generating classes per request.
- ClassLoaders created without being released.
- Plugin reloads where old class loaders remain reachable.
- Redeploy or application server configurations.

A large Loaded count does not automatically indicate a class loader leak. Verify which class loaders hold the classes and whether old class loaders can be garbage collected.

## 15. Reading -compiler and -printcompilation

### -compiler

Command:

~~~bash
jstat -compiler 2125 1000 10
~~~

Columns:

| Column | Meaning |
|---|---|
| Compiled | Number of compilation tasks performed |
| Failed | Number of compilation tasks that failed |
| Invalid | Number of compilation results invalidated |
| Time | Total time spent performing compilation tasks, in seconds |
| FailedType | Compilation type of the most recent failure |
| FailedMethod | Class and method associated with the most recent failure |

Compiled and Time usually rise during JVM warm-up as the JIT compiles hot methods. Rising Failed counts should be reviewed alongside FailedType and FailedMethod; some failures or invalidations are normal internal JIT behavior rather than immediate application errors.

### -printcompilation

Command:

~~~bash
jstat -printcompilation 2125 1000 10
~~~

Columns:

| Column | Meaning |
|---|---|
| Compiled | Number of compilation tasks for the most recently compiled method |
| Size | Number of bytecode bytes in the most recently compiled method |
| Type | Compilation type |
| Method | Class name and method name of the most recently compiled method |

-printcompilation reports information about the most recent method compilation at each sample. It is not a complete list of all methods compiled by the JIT.

Class names in Method may use slashes instead of dots to separate package names.

## 16. Reading GC Counters Over Time

The YGC, YGCT, FGC, FGCT, and GCT columns are cumulative counters/total times since the JVM started.

| Column | Meaning |
|---|---|
| YGC | Number of Young GC events |
| YGCT | Total time spent in Young GC |
| FGC | Number of Full GC events |
| FGCT | Total time spent in Full GC |
| GCT | Total GC time |

Example of two samples taken 10 seconds apart:

~~~text
Sample  YGC  YGCT   FGC  FGCT  GCT
1       100  2.500  2    0.800 3.300
2       105  2.650  2    0.800 3.450
~~~

During the sampling interval:

- 5 additional Young GCs occurred.
- Total Young GC time increased by 0.150 seconds.
- No new Full GCs occurred.
- Total GC time increased by 0.150 seconds.

You can calculate the approximate GC time ratio over the interval:

~~~text
GC time delta / elapsed time * 100
0.150 / 10 * 100 = 1.5%
~~~

This is the rate of cumulative GC time increase during the sampling interval, not an exact measurement of total process CPU utilization. With very short intervals, timestamp resolution and OS scheduling jitter can cause the ratio to fluctuate.

### Distinguishing GC Count from GC Time

A fast-rising YGC with a small YGCT increase can mean many short Young GCs. A small FGC increase with a sharp FGCT jump can indicate expensive Full GCs. Always examine both counts and times rather than looking at a single column.

## 17. Reading Multiple Column Groups Together

Never draw performance conclusions from a single column in isolation. Useful combinations include:

| Observation | Columns to Inspect Together | Investigation Direction |
|---|---|---|
| Eden frequently near full | E, EU, EC, YGC, YGCT | Allocation rate and Young GC frequency |
| Old Space steadily rising | O, OU, OC, FGC, FGCT | Promotion, live set, memory leak |
| Survivor frequently full | S0, S1, S0U, S1U, TT, DSS | Surviving objects and promotion |
| Metaspace rising | M, MU, MC, Loaded, Unloaded | Class loading and class loader lifecycle |
| Repeated Full GCs | FGC, FGCT, GCT, GCC, LGCC | Full GC cause and pause duration |
| Class count continuously rising | Loaded, Unloaded, MU, CCSU | Dynamic class generation or class loader leak |
| JIT compilations rising | Compiled, Time, Failed, Invalid | Warm-up and compilation activity |

### Example: Allocation Pressure

If E repeatedly climbs high and drops sharply, YGC rises steadily, and O stays roughly flat, the application may be allocating many short-lived objects. Measure the allocation rate with JFR or a profiler before resizing the heap.

### Example: Growing Live Set

If O climbs across many GC cycles without dropping accordingly, more objects may be staying alive. jstat only reveals the trend. Use a heap dump to find object dominators and Paths to GC Roots.

### Example: Class Loader Pressure

If Loaded rises continuously, Unloaded barely changes, and MU/CCSU also rise, inspect class-generating frameworks, proxies, plugins, or class loader lifecycles. You cannot confirm a leak from these counters alone.

### Example: Rising GC Pauses

If YGCT or FGCT climbs rapidly relative to elapsed runtime, compute the deltas between samples. Pair with JFR to see individual GC event durations, collector type, allocation pressure, and other pauses.

## 18. Practicing with jstat and a Java Process

The following example creates a Java 17+ process that continuously allocates objects and retains a small set of byte arrays. The goal is to generate enough allocation activity to observe the Eden and Young GC columns.

Directory structure:

~~~text
project/
  src/
    com/acme/JstatDemo.java
  out/
~~~

File src/com/acme/JstatDemo.java:

~~~java
package com.acme;

public final class JstatDemo {
    public static void main(String[] args) throws InterruptedException {
        byte[][] live = new byte[16][];

        System.out.println("READY");

        while (true) {
            for (int i = 0; i < live.length; i++) {
                live[i] = new byte[64 * 1024];
            }
            Thread.sleep(250);
        }
    }
}
~~~

Compile:

~~~bash
javac --release 17 -d out src/com/acme/JstatDemo.java
~~~

Run with a bounded heap:

~~~bash
java -Xms64m -Xmx128m -cp out com.acme.JstatDemo
~~~

Exact stdout:

~~~text
READY
~~~

The process continues running, allocating roughly 1 MB every 250 ms while keeping the 16 most recent byte arrays live. Actual allocation throughput and GC frequency depend on the JVM, collector, and hardware.

Open a second terminal and find the LVMID:

~~~bash
jps -l
~~~

Assuming the LVMID is 2125, practice with:

~~~bash
jstat -gcutil 2125 1000 10
jstat -gc 2125 1000 10
jstat -gcnew 2125 1000 10
jstat -gccause 2125 1000 10
jstat -class 2125 1000 10
jstat -compiler 2125 1000 10
~~~

Observe:

1. E rises during allocation.
2. YGC increments when a Young GC occurs.
3. E drops after collection.
4. S0/S1 may alternate receiving surviving objects.
5. O may increase if objects are promoted.
6. YGCT and GCT increase cumulatively.

The exact numbers are not fixed, so exact jstat metric stdout cannot be provided for every machine. Only the program's READY line is fixed output. When finished, press Ctrl+C in the terminal running the Java process to stop it.

## 19. Timestamps and Repeating Headers

### Adding a Timestamp with -t

~~~bash
jstat -gcutil -t 2125 1000 5
~~~

Timestamp is the elapsed time in seconds since the target JVM started. It helps correlate jstat samples with logs, metrics, and incident timelines.

Timestamp is not wall-clock time. To align it with real-time logs, record the start time when running the command or use a monitoring system with its own timestamps.

### Printing Headers Periodically with -h

~~~bash
jstat -gcutil -h 5 2125 1000 20
~~~

The header is reprinted every 5 samples. This is helpful when output is long or saved to a log file, as readers can identify column names after many rows of data.

You can combine -t and -h:

~~~bash
jstat -gcutil -t -h 5 2125 1000 20
~~~

## 20. Limitations and Caveats When Interpreting jstat

### jstat Is a HotSpot Tool

jstat reads instrumentation provided by the HotSpot VM. Its output is not a standard Java API with identical semantics across every JVM implementation.

### Not Every Collector Shares the Same Generation Model

Column names such as Eden, Survivor, and Old Generation reflect a generational heap model. The collector, JDK release, and platform can change available columns or how they are represented. Check -options and the documentation for the exact JDK you are running.

### Do Not Write Parsers Tightly Coupled to the Output

The jstat documentation warns against writing scripts that parse its output, as the format may change in future releases. If integration is unavoidable, isolate the parser, check the JDK version, handle missing columns, and test against every target JDK. For long-term monitoring, prefer JMX metrics, JFR, or a metrics solution with a stable schema.

### jstat Is Experimental and Unsupported

The command reference describes jstat as experimental and unsupported; options and functionality may change or be removed. Do not build long-term production platforms that depend on jstat text output.

### Instrumentation Has Limitations

Oracle notes that jstat instrumentation is inaccessible on FAT32 filesystems. Additionally, sampling has finite resolution; intervals that are too short can produce excessive output without adding useful insight.

### Do Not Confuse Heap with Total Process Memory

jstat focuses on the counters and pools exposed by HotSpot instrumentation. If RSS grows while the heap remains stable, inspect direct memory, native allocations, metaspace, thread stacks, and OS metrics.

## 21. Which Tool to Use When Deeper Information Is Needed?

| Need | Suitable Tool |
|---|---|
| Quick sampling of heap and GC | jstat |
| List available JVM diagnostic commands | jcmd PID help |
| Track GC events and pauses over time | JFR and JDK Mission Control |
| Inspect the heap object graph | jcmd GC.heap_dump and Eclipse MAT |
| Track class loading and class unloading | jstat -class, JFR |
| Track HotSpot native memory | Native Memory Tracking |
| Continuous metric-based monitoring | JMX or an application metrics framework |

jcmd is the diagnostic command utility recommended by Oracle to replace several legacy tools such as jstack, jinfo, and jmap; it does not directly replace every time-series column of jstat. JFR/JMC is suited when you need an event timeline and deeper analysis.

JFR provides a low-overhead default template and a profile template that collects more data with higher performance impact. Choose the template based on your goal and collection window.

## 22. Troubleshooting

| Symptom | Possible Cause | Resolution |
|---|---|---|
| jstat not recognized | JDK bin directory is not in PATH | Check JAVA_HOME and PATH |
| JVM not visible in jps | JVM is in a separate Docker process or different namespace | Run ps in the right namespace or run the tool inside the container |
| LVMID does not work as PID | LVMID does not always match the OS PID | Re-verify using jps and OS tools |
| Instrumentation inaccessible | Filesystem environment or JVM does not expose data | Check filesystem, especially FAT32, and the target JVM |
| Unknown option | Option is not supported on that platform/JDK | Run jstat -options |
| Output missing expected columns | Wrong statOption selected or collector does not provide that group | Choose the right option and check JDK version |
| E always high | Allocation pressure or sampling right before GC | Observe multiple samples, YGC, and YGCT |
| O steadily rising | Promotion or growing live objects | Check after GC; use a heap dump to find references |
| M steadily rising | Class metadata growth or uncollected class loaders | Correlate Loaded/Unloaded and class loader lifecycles |
| FGC rising rapidly | Full GCs occurring frequently | Use gccause and JFR to identify causes and pauses |
| S0/S1 swinging sharply between samples | Survivor spaces alternating after collections | Read alongside S0U/S1U, TT, and YGC |
| Header lost in long logs | Header only printed on the first sample | Use -h n |
| Script fails to parse output | Format or columns changed between JDKs | Avoid brittle parsers; check version or switch to JMX/JFR |
| jstat does not reflect RSS | Tool does not measure all native memory | Use NMT and OS tools |

## 23. Practical Workflow for Reading jstat

1. Identify the running JDK and JVM implementation.
2. Use jps or OS tools to find the right LVMID/PID.
3. Run jstat -options to see which column groups are supported.
4. Start with -gcutil for an overall picture.
5. If you need absolute capacities, use -gc.
6. If you need New Generation details, use -gcnew and -gcnewcapacity.
7. If you need Old Generation details, use -gcold and -gcoldcapacity.
8. If you need metaspace details, use -gcmetacapacity and correlate with -class.
9. If you need GC causes, use -gccause.
10. If you suspect class loading or JIT issues, use -class, -compiler, and -printcompilation.
11. Collect multiple samples with a reasonable interval; use -t and -h as needed.
12. Compare deltas of YGC, FGC, YGCT, FGCT, and GCT between samples.
13. Correlate metrics with workload and GC timing.
14. Use JFR, heap dumps, JMX, or NMT when deeper root-cause analysis is needed.
15. Record the JDK version, collector, options, interval, and timestamp so others can reproduce the measurement.

## 24. Key Takeaways

- jstat reads performance and resource consumption statistics from HotSpot instrumentation.
- jstat requires no special startup flags; built-in instrumentation is enabled by default in HotSpot.
- Use jstat -options to list the statOptions available on the target machine.
- -gc shows capacity and used values for Survivor, Eden, Old Space, Metaspace, and CCS along with GC counters.
- -gcutil shows utilization percentages for S0, S1, E, O, M, and CCS.
- -gccause adds LGCC and GCC to show the last and current GC causes.
- -gccapacity, -gcnewcapacity, -gcoldcapacity, and -gcmetacapacity focus on capacity limits.
- -gcnew helps inspect S0/S1, TT, MTT, DSS, EC, and EU.
- -class tracks class loading/unloading; -compiler and -printcompilation track JIT compilation.
- YGC/FGC are cumulative counters; YGCT/FGCT/GCT are cumulative GC times in seconds.
- Use deltas between samples to understand GC frequency and cost over a time window.
- LVMID usually, but not always, matches the OS PID.
- jstat is experimental/unsupported per the command reference; options and output may change.
- Do not write parsers tightly coupled to jstat text output.
- jstat does not measure total RSS or all native memory; use NMT, JFR, JMX, and OS tools when needed.

## Official References

- [The jstat Command — Java SE 17 Tool Specifications](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jstat.html)
- [Diagnostic Tools — JDK 26, The jstat Utility](https://docs.oracle.com/en/java/javase/26/troubleshoot/diagnostic-tools.html)
- [The jcmd Command — JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jcmd.html)
- [Java Flight Recorder — JDK 26 Diagnostic Tools](https://docs.oracle.com/en/java/javase/26/troubleshoot/diagnostic-tools.html)
- [JDK Mission Control](https://www.oracle.com/java/technologies/jdk-mission-control.html)
