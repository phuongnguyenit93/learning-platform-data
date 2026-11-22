# Monitoring Heap Statistics with jstat

## 1. What is jstat?

**jstat** (JVM Statistics Monitoring Tool) is a command-line tool in the JDK used to read instrumentation counters from a running Java HotSpot VM. It provides metrics on garbage collection (GC), heap region capacities, Metaspace, and several other runtime activities.

For **Heap statistics**, jstat helps answer:

- How much memory are Eden, Survivor, and Old space currently using?
- What are the current and maximum capacities of each generation?
- How does heap utilization change over time?
- How many Young GC and Full GC events have occurred?
- Is total GC time increasing rapidly or slowly?
- What triggered the most recent GC?

jstat is especially useful when you need to observe a JVM across multiple consecutive samples. A single reading is only a snapshot; a series of samples shows how allocation, GC, and memory usage evolve over time.

jstat monitors an instrumented HotSpot JVM. Built-in instrumentation is enabled by default, and you typically do not need to launch the application with a special JVM flag just to use jstat.

## 2. Checking jstat and Available Options

jstat is distributed with the JDK. Check the help output:

~~~bash
jstat -help
~~~

List the statistics groups supported by the current JDK build:

~~~bash
jstat -options
~~~

On JDK 24.0.2 in the test environment, the list includes:

~~~text
-class
-compiler
-gc
-gccapacity
-gccause
-gcnew
-gcnewcapacity
-gcold
-gcoldcapacity
-gcmetacapacity
-gcutil
-printcompilation
~~~

Available options can vary across JDK releases, vendors, or platforms. Check `jstat -options` on the specific JDK you are using instead of assuming every build has the same list.

## 3. General Syntax

Syntax:

~~~text
jstat -<option> [-t] [-h<lines>] <vmid> [<interval> [<count>]]
~~~

Meaning:

| Component | Description |
|---|---|
| option | Type of statistics to display, for example `-gc` or `-gcutil`. |
| vmid | Target JVM identifier. For a local JVM, this is typically the `lvmid`. |
| interval | Sampling interval between consecutive samples. |
| count | Number of samples to collect. |
| -t | Adds a timestamp column measured from JVM startup. |
| -hN | Repeats the header line after every N samples. |

Example collecting 5 GC samples, 1 second apart:

~~~bash
jstat -gc 12345 1s 5
~~~

The interval can also be specified in milliseconds:

~~~bash
jstat -gc 12345 500ms 10
~~~

If `interval` is omitted, jstat collects a single sample. If `interval` is provided without `count`, the tool continues sampling until the JVM exits or the user stops the command with Ctrl+C.

The default unit for `interval` is milliseconds. Both `interval` and `count` must be positive integers.

## 4. Finding the Target JVM and VMID

Before running jstat, identify the target JVM. You can use:

~~~bash
jcmd -l
jps -l
~~~

Example:

~~~text
12345 com.example.orders.OrderApplication
~~~

In the jstat command:

~~~bash
jstat -gc 12345 1s 5
~~~

`12345` is an example `lvmid`. The LVMID usually matches the operating system PID, but this is not guaranteed in all cases. When you need to verify the OS PID, cross-check using your operating system's process management tools.

A VMID can take the form:

~~~text
<lvmid>
<lvmid>@<hostname>[:<port>]
~~~

The `lvmid` part is required; `hostname` and `port` are used for remote monitoring. jstat can only observe JVMs that the current user account and environment have permission to access.

## 5. Creating a Sample JVM for Practice

Create the file **JstatHeapProbe.java**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class JstatHeapProbe {
    private static final List<byte[]> KEEP = new ArrayList<>();

    public static void main(String[] args) throws Exception {
        for (int i = 0; i < 20; i++) {
            KEEP.add(new byte[1024 * 1024]);
        }

        System.out.println(
                "JstatHeapProbe ready; pid=" +
                ProcessHandle.current().pid());

        long end = System.nanoTime() + 120_000_000_000L;
        while (System.nanoTime() < end) {
            for (int i = 0; i < 12; i++) {
                byte[] temporary = new byte[512 * 1024];
                if (temporary.length == 0) {
                    throw new AssertionError();
                }
            }
            Thread.sleep(80);
        }
    }
}
~~~

This program retains 20 byte arrays of 1 MiB each while creating temporary allocations so GC activity can be observed. `ProcessHandle.current().pid()` prints the PID of the sample JVM. The program runs for up to two minutes to allow time for collecting multiple samples.

Compile with JDK 17 or later:

~~~bash
javac --release 17 -encoding UTF-8 JstatHeapProbe.java
~~~

Run with a 128 MiB heap limit and G1 GC:

~~~bash
java -Xms64m -Xmx128m -XX:+UseG1GC JstatHeapProbe
~~~

Example stdout:

~~~text
JstatHeapProbe ready; pid=12345
~~~

The PID is dynamic. Open a second terminal, replace `12345` with the actual PID, and try:

~~~bash
jstat -gc 12345 500ms 5
jstat -gcutil 12345 500ms 5
~~~

This Java sample was compiled with `javac --release 17` and run on JDK 24.0.2; jstat observed the Young GC counters increasing while allocations continued. After practicing, stop the sample process with Ctrl+C.

## 6. Using -gc to Inspect Region Capacities

The **-gc** option displays the capacity and utilization of heap regions along with several GC counters.

Run:

~~~bash
jstat -gc 12345
~~~

Example output captured from a test JVM on JDK 24.0.2:

~~~text
S0C    S1C    S0U   S1U      EC      EU       OC       OU     MC    MU    CCSC CCSU YGC YGCT FGC FGCT CGC CGCT GCT
0.0  1024.0  0.0  99.5  16384.0  4096.0  56320.0  42096.8  320.0 83.4 128.0 6.7 2 0.001 0 0.000 2 0.001 0.002
~~~

Memory size columns in this option are reported in KB.

| Column | Meaning |
|---|---|
| S0C, S1C | Current capacity of Survivor space 0 and 1. |
| S0U, S1U | Used space of Survivor space 0 and 1. |
| EC | Current capacity of Eden space. |
| EU | Used Eden space. |
| OC | Current capacity of Old space. |
| OU | Used Old space. |
| MC | Committed Metaspace capacity. |
| MU | Used Metaspace. |
| CCSC | Committed Compressed Class Space capacity. |
| CCSU | Used Compressed Class Space. |
| YGC | Number of Young GC events since JVM startup. |
| YGCT | Total Young GC time, in seconds. |
| FGC | Number of Full GC events since JVM startup. |
| FGCT | Total Full GC time, in seconds. |
| GCT | Total GC time according to JVM counters, in seconds. |

On the tested JDK 24.0.2 build, the output also includes `CGC` and `CGCT` for concurrent GC count and time reported by the JVM/collector. These columns do not appear in every version or configuration; always read the actual output header.

`MC`, `MU`, `CCSC`, and `CCSU` describe class metadata storage regions. They are not part of the Java object heap capacity.

## 7. Using -gcutil to View Percentage Utilization

The **-gcutil** option displays region utilization as a percentage of current capacity.

~~~bash
jstat -gcutil 12345
~~~

Example output from a test G1 JVM:

~~~text
S0  S1     E      O      M     CCS  YGC  YGCT  FGC  FGCT  CGC  CGCT  GCT
-   -   0.00  92.82  62.76  16.64  24  0.011   0  0.000   2  0.000  0.011
~~~

Meaning of the percentage columns:

| Column | Meaning |
|---|---|
| S0 | Survivor space 0 utilization percentage. |
| S1 | Survivor space 1 utilization percentage. |
| E | Eden utilization percentage. |
| O | Old space utilization percentage. |
| M | Metaspace utilization percentage. |
| CCS | Compressed Class Space utilization percentage. |

The `YGC`, `YGCT`, `FGC`, `FGCT`, and `GCT` columns are cumulative counts/durations, not percentages.

A `-` indicates that the column has no reported value in the current configuration or collector. For example, G1 output on JDK 24.0.2 may display `-` for `S0` and `S1`. Do not interpret this symbol as 0% utilization.

`-gcutil` is well suited for identifying which region is growing in utilization percentage. When you need the absolute sizes corresponding to those percentages, also run `-gc`.

## 8. Using Capacity Options

Capacity options show the minimum, maximum, and current capacities of generations or memory spaces.

| Option | Information |
|---|---|
| -gccapacity | Capacities of New Generation, Old Generation, Survivor, Eden, and Metaspace. |
| -gcnewcapacity | Capacities of New Generation and its spaces. |
| -gcoldcapacity | Capacity of Old Generation. |
| -gcmetacapacity | Capacities of Metaspace and Compressed Class Space. |

Examples:

~~~bash
jstat -gccapacity 12345
jstat -gcnewcapacity 12345
jstat -gcoldcapacity 12345
jstat -gcmetacapacity 12345
~~~

Common columns in `-gccapacity`:

- `NGCMN`: Minimum New Generation capacity.
- `NGCMX`: Maximum New Generation capacity.
- `NGC`: Current New Generation capacity.
- `OGCMN`: Minimum Old Generation capacity.
- `OGCMX`: Maximum Old Generation capacity.
- `OGC`: Current Old Generation capacity.
- `EC`, `S0C`, `S1C`, `OC`: Current capacity of each space.
- `MCMN`, `MCMX`, `MC`: Minimum, maximum, and committed Metaspace capacity.

These capacities help you understand how far the JVM can expand each generation. They do not replace checking `-Xms` and `-Xmx`; when you need to confirm those JVM flags, run:

~~~bash
jcmd 12345 VM.flags
~~~

## 9. Using -gcnew and -gcold to Focus on Individual Generations

When investigating a specific region, you can narrow the output.

### New Generation

~~~bash
jstat -gcnew 12345
~~~

Common columns:

- `S0C`, `S1C`: Capacities of the two Survivor spaces.
- `S0U`, `S1U`: Used Survivor space.
- `TT`: Current tenuring threshold.
- `MTT`: Maximum tenuring threshold.
- `DSS`: Desired survivor size.
- `EC`, `EU`: Eden capacity and used space.
- `YGC`, `YGCT`: Young GC count and total time.

`TT` is the object age threshold related to whether objects remain in Survivor or are promoted to Old Generation. Its value can change dynamically based on GC behavior.

### Old Generation

~~~bash
jstat -gcold 12345
~~~

This option focuses on Old space and Metaspace:

- `OC`, `OU`: Old space capacity and used space.
- `MC`, `MU`: Metaspace committed and used.
- `CCSC`, `CCSU`: Compressed Class Space committed and used.
- `YGC`, `FGC`, `FGCT`, `GCT`: Corresponding GC counters.

Not every collector models the heap in terms of traditional generations. Read the actual columns provided by the target JVM.

## 10. Using -gccause to Inspect GC Causes

The **-gccause** option displays statistics similar to `-gcutil`, while adding the cause of the last GC and the current GC if one is in progress.

~~~bash
jstat -gccause 12345
~~~

Two additional columns:

- `LGCC`: Cause of the last GC.
- `GCC`: Cause of the current GC if GC activity is underway; otherwise, it may display `No GC`.

Example causes include allocation failure or collector-specific events. Cause names depend on the JVM and collector.

This option is useful when utilization increases or GC counters change and you need extra context on why GC was triggered.

## 11. Collecting Multiple Samples with Interval, Count, Timestamp, and Header

A single sample only shows the state at one point in time. To observe trends, collect multiple samples.

Example collecting 10 samples, one per second:

~~~bash
jstat -gcutil 12345 1s 10
~~~

Add a timestamp measured from JVM startup:

~~~bash
jstat -gcutil -t 12345 1s 10
~~~

Repeat the header every 5 samples:

~~~bash
jstat -gcutil -t -h5 12345 1s 10
~~~

Meaning:

- `-t`: Adds a `Timestamp` column, in seconds since JVM startup.
- `-h5`: Reprints the header every 5 samples to keep long output readable.
- `1s`: Interval between consecutive samples.
- `10`: Total number of samples to collect.

On JDK 24.0.2, the following command was tested successfully:

~~~bash
jstat -gcutil -t -h2 12345 250ms 4
~~~

If `count` is omitted, jstat continues printing samples until the JVM exits or the user stops the command. In production monitoring, choose an interval sufficient for observation while avoiding excessive output.

## 12. Understanding Cumulative GC Counters

Columns such as `YGC`, `FGC`, and GC time columns are typically cumulative counters since JVM startup.

Example:

| Sample | YGC | YGCT | FGC | FGCT | GCT |
|---|---:|---:|---:|---:|---:|
| T1 | 20 | 0.120 | 1 | 0.030 | 0.150 |
| T2 | 24 | 0.145 | 1 | 0.030 | 0.175 |
| T3 | 30 | 0.190 | 2 | 0.060 | 0.250 |

From T1 to T2:

- 4 additional Young GCs occurred.
- Total Young GC time increased by 0.025 seconds.
- No new Full GC occurred.
- Total GC time increased by 0.025 seconds.

From T2 to T3:

- 6 additional Young GCs occurred.
- 1 additional Full GC occurred.
- Total GC time increased by 0.075 seconds.

The table above uses illustrative numbers to explain how to compute deltas between samples; it is not fixed output from a real JVM.

To evaluate trends, calculate the difference between samples:

- Delta YGC = later sample `YGC` minus earlier sample `YGC`.
- Delta FGC = later sample `FGC` minus earlier sample `FGC`.
- Delta GCT = later sample `GCT` minus earlier sample `GCT`.

The ratio of Delta GCT to the elapsed wall-clock time between two samples helps estimate the share of cumulative time reported for GC. This is not an exact measurement of pause time, especially for collectors with concurrent phases. Use GC logs or Java Flight Recorder when you need to analyze pauses and individual phases.

## 13. Analyzing Heap Statistics to Identify Issues

Several signals can guide further investigation:

### Rapidly Growing Eden and Continuously Increasing YGC

The application may be allocating objects at a high rate. This can be normal workload behavior or a sign of allocation pressure.

Check allocation rate, object lifetimes, and GC logs before concluding there is a problem.

### Old Space Growing Across Multiple GC Cycles

If Old space grows continuously and does not drop noticeably after comparable GC cycles, many objects may be getting promoted or held by long-lived references.

Inspect caches, sessions, queues, static collections, and object retention.

### Sharp Increase in FGC or FGCT

Full GC can cause long pauses and impact latency. Check the cause using `-gccause`, GC logs, and JFR.

A single `FGC` is not enough to conclude the application is unhealthy; evaluate frequency, duration, and workload.

### Growing Metaspace

Metaspace growth can be related to loading new classes, dynamic class generation, or unreleased class loaders.

Metaspace is not the Java Heap. If a class loader leak is suspected, gather class loading/unloading statistics and perform heap analysis.

### High but Stable Utilization

High utilization in a heap region is not necessarily an issue if the application is stable, GC is healthy, and sufficient capacity remains. Correlate with latency, allocation, GC frequency, and heap limits.

Do not conclude a memory leak from a single snapshot or from utilization percentage alone.

## 14. How the Collector Affects Reading Metrics

jstat column names are built around the memory pools and generations exposed by the JVM. Interpretation can differ depending on the collector.

- With collectors that have distinct Eden, Survivor, and Old Generation spaces, `S0`/`S1`/`E`/`O` map straightforwardly to those regions.
- With G1, the heap is divided into regions that are dynamically assigned roles. Some `S0`/`S1` columns may display `-` or not map directly to individual G1 regions.
- With ZGC or Shenandoah, the heap model differs from traditional generations; do not mechanically apply Eden/Survivor/Old interpretations.
- Metaspace and Compressed Class Space are separate metadata regions, not generations of the Java Heap.

Before interpreting metrics, check the active collector with:

~~~bash
jcmd 12345 VM.flags
~~~

Look for flags such as `UseG1GC`, `UseSerialGC`, `UseParallelGC`, `UseZGC`, or `UseShenandoahGC` if present. Read the header and documentation for the exact JDK and collector in use.

## 15. Comparing jstat with jcmd and Other Tools

| Tool | Best used when |
|---|---|
| jstat -gc | You need to track heap region capacities and utilization across multiple samples. |
| jstat -gcutil | You need a quick view of utilization percentages and GC trends. |
| jstat -gccapacity | You need min/max/current capacities of generations and spaces. |
| jstat -gccause | You need the cause of the most recent or current GC. |
| jcmd GC.heap_info | You need a general point-in-time heap snapshot. |
| jcmd VM.flags | You need to inspect active heap and GC configuration flags. |
| GC logs / JFR | You need deep analysis of pause times, phases, allocation, and trends. |

jstat is convenient for quick sampling, whereas `jcmd` provides on-demand diagnostic commands. Do not use a `jcmd` heap summary as a substitute for time-series sampling when your goal is trend analysis.

## 16. Permissions and Remote JVM Monitoring

For a local JVM:

- Run jstat on the same host as the target JVM.
- Use a user account with permission to access the JVM's instrumentation.
- Use the `lvmid` identified via `jps` or OS tools.
- With Docker, run the tool inside the container or in a PID namespace that can see the JVM.

jstat supports remote VMIDs via hostname and RMI when the target host runs `jstatd`. Example syntax:

~~~bash
jstat -gcutil 12345@remote.example 1s 10
~~~

However, `jstatd` in JDK 24 is marked experimental, unsupported, and deprecated. `jstatd` does not authenticate remote clients; it can expose instrumentation for every JVM that the `jstatd` account can observe to users on the network.

Do not enable `jstatd` in production or on untrusted networks without a security review, network access restrictions, and appropriate policies. When local diagnostics suffice, prefer local jstat.

## 17. Limitations and Considerations When Using jstat

jstat is marked **experimental and unsupported** by Oracle. Options and behavior may change or be removed in future JDK releases.

Output formatting may also change. JDK documentation advises against building production scripts that depend on parsing jstat output. If you must parse it, accept that scripts may require updates when upgrading the JDK.

Additional considerations:

- jstat monitors instrumented HotSpot VMs, not every process named `java`.
- LVMID is usually, but not always, the OS PID.
- Reported metrics depend on the collector and JDK version.
- jstat does not show total process RAM; native memory, direct buffers, thread stacks, and code cache must be inspected separately.
- A single sample is not enough to conclude a memory leak or GC bottleneck.
- Use a reasonable interval; avoid overly frequent polling in production.
- Output may reflect sensitive configuration and operational data; review before sharing.

## 18. Common Errors and Troubleshooting

| Symptom | Possible Cause | Resolution |
|---|---|---|
| `jstat` is not recognized | JDK `bin` is not in `PATH` or only a minimal runtime is installed. | Check `JAVA_HOME`, `PATH`, and the JDK `bin` directory. |
| `jstat -options` lacks the desired option | Current JDK/vendor/platform does not provide that option. | Use an option listed by `jstat -options`. |
| Invalid argument or interval error | Interval/count is not a positive integer or has an invalid suffix. | Use forms like `250ms`, `1s`, and a positive count. |
| Could not find VM | Wrong `lvmid`, JVM already exited, or insufficient user permissions. | Run `jps -l`, verify the process and user. |
| Attach or instrumentation failure | Different user, namespace, or inaccessible instrumentation. | Use the same service account and matching process environment. |
| Some columns display `-` | Collector or memory pool does not report that column. | Read the remaining columns and check the collector. |
| Capacities do not match `-Xmx` | jstat shows per-pool capacity, not always total maximum heap. | Check `jcmd VM.flags` and distinguish current vs. max capacity. |
| YGC/FGC rise but heap used does not drop | Continuous allocation, retained references, or promotion. | Monitor multiple samples and inspect GC logs/JFR. |
| GCT rises without matching latency | GC time counters are not a complete measure of pause/latency. | Analyze GC logs or JFR. |
| Remote jstat cannot connect | `jstatd`/RMI registry not running, wrong host/port, or firewall blocked. | Check the service and network policy; do not open remote monitoring casually. |

## 19. Workflow for Monitoring Heap Statistics

A repeatable workflow:

1. Identify the JDK version and target JVM.
2. Run `jstat -options` to see available options.
3. Use `jps -l` or `jcmd -l` to find the `lvmid`.
4. Run `jstat -gc` to inspect capacities in KB.
5. Run `jstat -gcutil` to view utilization percentages.
6. Use `-gccapacity`, `-gcnew`, or `-gcold` when region-specific details are needed.
7. Use `-gccause` to check GC causes.
8. Add `-t`, `interval`, and `count` to collect a timestamped sample series.
9. Compare counter deltas and utilization across multiple GC cycles.
10. Use `jcmd VM.flags` to confirm heap and collector configuration.
11. Use GC logs or JFR when deep analysis is required.
12. Record the JDK, collector, workload, and sampling time when reporting findings.

## 20. Checklist Before Concluding a Heap Issue

- [ ] Identified the correct JVM and `lvmid`.
- [ ] Checked available options with `jstat -options`.
- [ ] Understood KB units in `-gc` and percentages in `-gcutil`.
- [ ] Distinguished current capacity from maximum capacity.
- [ ] Understood that `YGC`, `FGC`, and GC times are cumulative counters.
- [ ] Considered the active collector before interpreting `S0`/`S1`/`E`/`O`.
- [ ] Collected multiple samples with an appropriate interval and count.
- [ ] Checked GC causes if counters increased abnormally.
- [ ] Distinguished Java Heap from Metaspace and native memory.
- [ ] Compared trends across comparable GC cycles.
- [ ] Used GC logs/JFR when pause or allocation analysis is needed.
- [ ] Evaluated access permissions and `jstatd` risks when monitoring remotely.
- [ ] Noted that jstat is experimental/unsupported and output format may change.

## 21. References

- Oracle JDK 24 — The jstat Command: https://docs.oracle.com/en/java/javase/24/docs/specs/man/jstat.html
- Oracle JDK 24 — Diagnostic Tools: https://docs.oracle.com/en/java/javase/24/troubleshoot/diagnostic-tools.html
- Oracle JDK 24 — The jstatd Command: https://docs.oracle.com/en/java/javase/24/docs/specs/man/jstatd.html

jstat helps monitor heap and GC activity across consecutive samples. By choosing the right option, understanding units and cumulative counters, accounting for the collector, and comparing trends rather than relying on a single snapshot, you can identify allocation pressure and anomalies for deeper investigation with `jcmd`, GC logs, or Java Flight Recorder.