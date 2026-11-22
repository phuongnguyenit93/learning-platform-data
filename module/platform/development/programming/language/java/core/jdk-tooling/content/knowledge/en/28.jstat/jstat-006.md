# Interval sampling with jstat

@@jstat@@ is a command-line tool for monitoring performance counters of a running Java HotSpot VM. It samples GC statistics, heap capacity and utilization, class loading, and JIT compilation at a specified interval.

The core idea of *interval sampling* is to read the same set of counters multiple times, separated by a fixed time interval. A single line of data shows the state at one point in time; comparing consecutive lines reveals the growth rate of GC counters, changes in Eden/Old/Metaspace utilization, and overall JVM behavior trends.

Oracle marks @@jstat@@ as *experimental and unsupported*: options and output formats may change or be removed in future JDK releases. It works well for live inspection and proven runbooks, but you should not build new automation that depends on parsing its tabular output.

## 1. What is interval sampling?

A *sample* is a single read by @@jstat@@ of the target JVM's counters, printed as one row of data. The *sampling interval* is the wait time between two consecutive samples. The *count* is the number of data rows to print before exiting.

Example:

~~~bash
jstat -gcutil 12345 1000 5
~~~

This command reads GC statistics for the JVM with VM identifier @@12345@@, every 1,000 ms (1 second), and prints 5 samples. After the fifth sample, @@jstat@@ exits.

If you omit @@count@@:

~~~bash
jstat -gcutil 12345 1000
~~~

The tool continues sampling every second until the target JVM exits or the operator stops the command with @@Ctrl+C@@. According to the documentation, the default count is infinite. To bound execution time and make results reproducible, explicitly specify both interval and count.

Interval sampling is useful because counters such as GC count and total GC time are usually cumulative values since JVM startup. Looking at a single row does not show the current rate. Comparing two rows at different times tells you how many GCs occurred and how much total GC time increased during that window.

## 2. Syntax and meaning of interval/count

General syntax per Java SE 21:

~~~text
jstat <statOption> [-t] [-h n] <vmid> [interval [count]]
~~~

| Component | Meaning |
|---|---|
| @@statOption@@ | Statistics group to print, such as @@-gcutil@@, @@-gc@@, @@-class@@ |
| @@-t@@ | Adds a Timestamp column: seconds elapsed since the target JVM started |
| @@-h n@@ | Reprints the header row after every @@n@@ samples |
| @@vmid@@ | Virtual Machine Identifier of the JVM to monitor |
| @@interval@@ | Time between samples; integer with @@ms@@ or @@s@@, defaulting to milliseconds |
| @@count@@ | Total number of samples; positive integer, defaulting to infinite |

Some common forms:

~~~bash
# Every 250 ms, take 10 samples
jstat -gcutil 12345 250 10

# Every 1 second, take 60 samples
jstat -gcutil 12345 1s 60

# Every 2 seconds, continue until stopped
jstat -gcutil 12345 2s

# With timestamp and repeat header every 5 samples
jstat -gcutil -t -h 5 12345 1s 30
~~~

@@interval@@ must be a positive integer. You can specify the unit with @@ms@@ or @@s@@; if only a number is given, the default unit is milliseconds. @@count@@ must also be a positive integer.

### 2.1. Choosing an interval for your goal

| Goal | Suggested sampling interval | How to use |
|---|---|---|
| Initial GC health check | 1–5 seconds | Observe trends over a few minutes |
| Tracking a short load spike | 250 ms–1 second | Capture only for a short window when you need to see rapid changes |
| Long-term monitoring during load tests | 1–5 seconds | Choose a count large enough to cover the entire test |
| One-off check | No repeat or small count | View only the current snapshot |

These are reference ranges, not tool limits. Choose the interval based on how fast the behavior you want to observe changes and the collection overhead. An interval that is too long can miss short GCs or brief spikes; an interval that is too short produces excessive output, increases monitoring activity, and makes trends harder to read.

A sample is not an event log. If a GC occurs and finishes between two samples, the counter may only show that the total event count increased; you cannot determine exact event start/end times from a single @@jstat@@ row.

### 2.2. Timestamp and repeated headers

@@-t@@ adds a @@Timestamp@@ column at the start of the output. This value is the elapsed time in seconds since the target JVM started, not wall-clock date and time:

~~~bash
jstat -gcutil -t 12345 500ms 8
~~~

Timestamp helps calculate the actual elapsed time between two samples and compare data within the same JVM session. Actual resolution can vary due to system load and thread scheduling; do not assume every sample is always spaced by an exact 500 ms.

@@-h n@@ reprints the header after every @@n@@ data rows. This is helpful during long monitoring sessions, when saving output to a file, or when reading scrolling logs:

~~~bash
jstat -gcnew -h 10 12345 1s 100
~~~

The header appears at the top and repeats after every 10 samples. It saves the reader from having to scroll back to the top of the file to recall what each column means.

## 3. Identifying the VMID before sampling

@@jstat@@ takes a @@vmid@@ (Virtual Machine Identifier). For a local JVM, the VMID is typically the local VM identifier (lvmid), which usually matches the OS process ID, though this is not guaranteed.

List running Java processes:

~~~bash
jps -l
~~~

Example:

~~~text
5485 jdk.jcmd/sun.tools.jcmd.JCmd
2125 com.example.orders.OrderApplication
7810 org.example.worker.BatchWorker
~~~

In this example, @@2125@@ is the lvmid of the application to monitor:

~~~bash
jstat -gcutil 2125 1s 10
~~~

You can also identify the process using OS tools such as @@ps@@ on Linux/macOS or Task Manager/PowerShell on Windows:

~~~powershell
Get-Process java
~~~

@@jps@@ and @@jstat@@ may not see JVMs running in separate Docker process/PID namespaces when invoked from the host. In that case, determine the VMID inside the target container or namespace.

### 3.1. Remote VMID and jstatd

@@jstat@@ supports remote monitoring over RMI if the target host is running @@jstatd@@. A remote VMID has the form:

~~~text
<lvmid>@<hostname>
~~~

Example:

~~~bash
jstat -gcutil 40496@remote.example.test 1s 60
~~~

The target host must have @@jstatd@@ and the RMI registry configured according to the JDK documentation. This is a legacy remote-management mechanism; restrict network access, permissions, and security policies accordingly. Never expose @@jstatd@@ publicly on the Internet. For new systems, consider secured JMX, JFR, or an authenticated, encrypted monitoring platform.

## 4. Choosing the right statistics group

List the stat options available on your current JDK:

~~~bash
jstat -options
~~~

View help:

~~~bash
jstat -help
~~~

Common options in Java SE 21:

| Option | Information |
|---|---|
| @@-gc@@ | Utilization and capacity of heap regions, metaspace, and GC counters |
| @@-gcutil@@ | Summary of region utilization as percentages |
| @@-gccause@@ | Summary like @@-gcutil@@ plus the cause of the last/current GC |
| @@-gccapacity@@ | Minimum, maximum, and current capacity of each generation/space |
| @@-gcnew@@ | New Generation, Eden, and Survivor statistics |
| @@-gcnewcapacity@@ | Capacities of New Generation spaces |
| @@-gcold@@ | Old Generation and Metaspace statistics |
| @@-gcoldcapacity@@ | Old Generation capacity |
| @@-gcmetacapacity@@ | Metaspace and Compressed Class Space capacity |
| @@-class@@ | Number of classes loaded/unloaded and class loader time |
| @@-compiler@@ | JIT compiler statistics |
| @@-printcompilation@@ | Most recently compiled method and compilation info |

The exact set of options and columns depends on the JDK, JVM vendor, and collector. Running @@jstat -options@@ on the target machine is the authoritative check.

### 4.1. -gcutil: viewing percentage utilization

@@-gcutil@@ is usually the first choice when you need a quick view of GC trends:

~~~bash
jstat -gcutil -t 12345 1s 20
~~~

Common columns on HotSpot:

| Column | Meaning |
|---|---|
| @@S0@@ | Survivor Space 0 utilization percentage |
| @@S1@@ | Survivor Space 1 utilization percentage |
| @@E@@ | Eden utilization percentage |
| @@O@@ | Old Space utilization percentage |
| @@M@@ | Metaspace utilization percentage |
| @@CCS@@ | Compressed Class Space utilization percentage |
| @@YGC@@ | Total number of Young GCs since JVM startup |
| @@YGCT@@ | Total Young GC time, in seconds |
| @@FGC@@ | Total number of Full GCs since JVM startup |
| @@FGCT@@ | Total Full GC time, in seconds |
| @@GCT@@ | Total GC time reported by the JVM, in seconds |

Some newer JDKs or collectors may include columns like @@CGC@@ or @@CGCT@@ for concurrent GC. Columns may be absent, show @@-@@, or have different semantics depending on the collector; check the actual header and the documentation for the running JDK.

### 4.2. -gc: viewing capacity and utilization in KB

@@-gc@@ displays capacity and used amounts instead of only percentages:

~~~bash
jstat -gc -t 12345 1s 10
~~~

Common columns:

| Column | Meaning |
|---|---|
| @@S0C@@ / @@S1C@@ | Current capacity of Survivor 0/1 (KB) |
| @@S0U@@ / @@S1U@@ | Used space in Survivor 0/1 (KB) |
| @@EC@@ / @@EU@@ | Eden capacity and used space (KB) |
| @@OC@@ / @@OU@@ | Old Space capacity and used space (KB) |
| @@MC@@ / @@MU@@ | Metaspace committed and used (KB) |
| @@CCSC@@ / @@CCSU@@ | Compressed Class Space committed and used (KB) |
| @@YGC@@ / @@YGCT@@ | Young GC count and total Young GC time |
| @@FGC@@ / @@FGCT@@ | Full GC count and total Full GC time |
| @@GCT@@ | Total GC time |

To calculate the percentage utilization of a space in a sample:

\[
\text{Usage \%} = \frac{\text{Used}}{\text{Capacity}} \times 100
\]

For example, if @@OU@@ is 12,288 KB and @@OC@@ is 16,384 KB, Old Space is using about 75% of its current capacity. Capacity can change as the heap expands or shrinks, so observe both used and capacity.

### 4.3. -gccause: viewing GC causes

~~~bash
jstat -gccause -t 12345 1s 20
~~~

This option adds:

- @@LGCC@@: cause of the last GC.
- @@GCC@@: cause of the current GC, if any.

Common causes include @@Allocation Failure@@ or @@No GC@@. This is useful diagnostic context, but it does not replace GC logs when you need detailed per-event analysis, pause phases, or deeper root causes.

### 4.4. Other options

- @@-gcnew@@: inspects Eden/Survivor, tenuring threshold, and Young GC. Common columns include @@TT@@, @@MTT@@, @@DSS@@, @@EC@@, @@EU@@, @@YGC@@, @@YGCT@@.
- @@-gcold@@: inspects Old Space, Metaspace, and GC counters.
- @@-gccapacity@@, @@-gcnewcapacity@@, @@-gcoldcapacity@@: inspects capacity bounds and current capacity.
- @@-gcmetacapacity@@: inspects Metaspace/Compressed Class Space capacity.
- @@-class@@: inspects how many classes the class loader has loaded/unloaded, byte counts, and time spent.
- @@-compiler@@: inspects succeeded/failed compilation tasks and JIT time.
- @@-printcompilation@@: inspects recently compiled methods across samples.

Examples for monitoring class loading and JIT:

~~~bash
jstat -class -t 12345 2s 15
jstat -compiler -t 12345 2s 15
jstat -printcompilation 12345 1s 20
~~~

## 5. Reading trends across samples

The most important rule in interval sampling is distinguishing **instantaneous values** from **cumulative counters**.

### 5.1. Instantaneous values

Columns such as @@E@@, @@O@@, @@S0@@, @@S1@@, and @@M@@ represent percentage utilization at the moment of the sample. They can rise or fall between rows:

- @@E@@ increases as the application allocates objects into Eden.
- After a Young GC, @@E@@ usually drops sharply as live objects are copied/promoted and Eden is reclaimed.
- @@S0@@ and @@S1@@ alternate roles in traditional generational collectors.
- @@O@@ increases when objects are promoted or retained longer; it drops when a collection reclaims objects.
- @@M@@ reflects Metaspace usage, related to class metadata.

Eden reaching nearly 100% before a Young GC can be normal behavior. Do not conclude that GC is unhealthy just because a single sample shows @@E=100@@. Check whether Eden is reclaimed after collection and whether collection frequency is reasonable for the load.

Old Space climbing steadily across many GC cycles may indicate long-lived objects, high promotion rates, or heap pressure. However, a single high @@O@@ value does not prove a memory leak; examine post-collection trends, heap dumps, GC logs, or JFR.

### 5.2. Cumulative counters

@@YGC@@, @@YGCT@@, @@FGC@@, @@FGCT@@, and @@GCT@@ are cumulative metrics since JVM startup. They normally do not decrease between samples. To understand activity within a window, take the difference between two rows:

\[
\Delta YGC = YGC_2 - YGC_1
\]

\[
\Delta GCT = GCT_2 - GCT_1
\]

Illustrative example:

| Counter | Sample 1 | Sample 2 | Delta |
|---|---:|---:|---:|
| Timestamp | 10.0 s | 20.0 s | 10.0 s |
| YGC | 120 | 150 | 30 |
| YGCT | 2.40 s | 3.00 s | 0.60 s |
| FGC | 3 | 4 | 1 |
| FGCT | 0.50 s | 0.80 s | 0.30 s |
| GCT | 2.90 s | 3.80 s | 0.90 s |

In this 10-second window:

- There were 30 Young GCs, or roughly 3 Young GCs/sec.
- Total Young GC time increased by 0.60 s; the average duration based on counters is 0.60 / 30 = 0.02 s (20 ms) per event.
- There was 1 Full GC, with FGCT increasing by 0.30 s.
- GCT increased by 0.90 s over the 10-second window.

You can compute a reference ratio:

\[
\text{GC time ratio} \approx
\frac{\Delta GCT}{\Delta t} \times 100\%
\]

In the example: @@0.90 / 10 × 100 = 9%@@. This is only a reference ratio derived from the GC time counter; it does not always equal the exact percentage of time the application was paused, especially with concurrent or parallel collectors. When you need exact pause times, use GC logs or JFR.

If @@YGC@@ grows rapidly while @@YGCT@@ grows very little, collections are likely short. If @@FGC@@ increases frequently and @@FGCT@@ rises significantly, investigate Full GC causes, Old Space usage, allocation/promotion rates, and GC logs.

### 5.3. Computing per-interval rates

Given two samples with timestamps @@t1@@ and @@t2@@:

\[
\text{GC events/sec} =
\frac{YGC_2 - YGC_1}{t_2 - t_1}
\]

\[
\text{Average Young GC duration} =
\frac{YGCT_2 - YGCT_1}{YGC_2 - YGC_1}
\]

The second formula is only meaningful when the Young GC count increased during that interval. If the delta is 0, there are no events to average.

Do not directly compare cumulative counters across two different JVMs or across a JVM restart. When the PID/VMID changes or the JVM restarts, start a new sample series.

## 6. Hands-on: sampling GC of a running JVM

This example creates a Java 17+ JVM that continuously allocates objects so you can easily observe Eden and GC behavior. This is a test workload; do not use this small heap configuration as a production default.

Create @@JstatWorkload.java@@:

~~~java
public final class JstatWorkload {
    private static final byte[][] retained = new byte[128][];

    public static void main(String[] args) throws Exception {
        System.out.println("JstatWorkload ready");
        long end = System.nanoTime() + 30_000_000_000L;
        int index = 0;
        long checksum = 0;

        while (System.nanoTime() < end) {
            byte[] block = new byte[64 * 1024];
            block[0] = (byte) index;
            retained[index++ & (retained.length - 1)] = block;
            checksum += block[0];

            if ((index & 127) == 0) {
                Thread.sleep(1);
            }
        }

        System.out.println("checksum=" + checksum);
    }
}
~~~

Compile and run in the first terminal:

~~~bash
javac --release 17 JstatWorkload.java
java -Xms32m -Xmx64m -XX:+UseSerialGC JstatWorkload
~~~

Exact initial stdout:

~~~text
JstatWorkload ready
~~~

The program continues running for about 30 seconds. In a second terminal, find the VMID:

~~~bash
jps -l
~~~

Replace @@12345@@ with the actual VMID and start sampling:

~~~bash
jstat -gcutil -t -h 5 12345 250ms 20
~~~

This command takes 20 samples, spaced roughly 250 ms apart, with timestamps and a repeated header every 5 rows.

To view actual capacities:

~~~bash
jstat -gc -t 12345 1s 10
~~~

To view GC causes:

~~~bash
jstat -gccause -t 12345 1s 10
~~~

To observe class loading/JIT:

~~~bash
jstat -class 12345 1s 10
jstat -compiler 12345 1s 10
~~~

On Windows PowerShell, you can save output to a file:

~~~powershell
jstat -gcutil -t -h 5 12345 250ms 20 |
    Tee-Object -FilePath .\gc-samples.txt
~~~

When the count finishes, @@jstat@@ exits automatically. If monitoring indefinitely, press @@Ctrl+C@@ in the second terminal; stop the demo application in the first terminal when done.

## 7. Saving and analyzing samples

A monitoring session should record:

- Application/instance name and VMID/PID.
- Start time, JDK version, and active GC.
- @@jstat@@ options, interval, and count.
- Full output, including headers and timestamps.
- Load context: test case, request rate, or deployment event.

Example saving a series of GC samples:

~~~bash
jstat -gcutil -t -h 10 12345 1s 300 > gc-samples.txt
~~~

With 300 samples at a 1-second interval, this captures roughly 5 minutes of monitoring. Actual wall-clock duration may be slightly longer due to scheduling and command execution time.

To read the file:

1. Identify the header and understand each column.
2. Use timestamps to divide the data into analysis windows.
3. Compute deltas for cumulative counters.
4. Compare space utilization before and after GC.
5. Flag windows with Full GCs, rapid Young GC growth, or steadily rising Old Space.
6. Correlate with application logs, request rates, metrics, and GC logs.

Do not keep only the last few lines if your goal is to analyze a spike. You need samples before, during, and after the event to understand what changed.

## 8. Limitations of jstat and pairing with other tools

### 8.1. Output is not a stable interface for automation

Oracle warns against writing scripts that depend on parsing @@jstat@@ output because the format can change between releases. If your organization still needs to parse it:

- Pin the JDK, vendor, and version in the runtime environment.
- Test the parser whenever upgrading the JDK.
- Do not assume column ordering is fixed.
- Handle added columns, missing columns, or @@-@@ values.
- Save raw output so it can be re-analyzed.

For new automation, consider JMX/Micrometer, JFR, or a metrics pipeline with an explicit schema instead of parsing CLI tables.

### 8.2. Collector and version affect interpretation

Column names like Eden, Survivor, and Old reflect the generational model of generational collectors. Not all collectors share the same heap layout. Some columns may display @@-@@, show 0, or not accurately reflect the heap structure of the active collector.

Before analyzing:

1. Identify the collector and JDK using startup flags or the appropriate diagnostic command.
2. Read the actual @@jstat@@ header.
3. Cross-check with the JDK/vendor and collector documentation.
4. Use GC logs or JFR if you need phase-level details.

### 8.3. jstat does not replace GC logs or JFR

@@jstat@@ provides counter snapshots and high-level trends. It does not provide full causes, phases, per-event pause durations, or object allocation call paths.

- GC log: analyze individual GC events, pauses, phases, before/after heap sizes, and causes.
- JFR: track events over time, allocations, GC, locks, and many other JVM activities.
- JDK Mission Control: analyze JFR files and timeline metrics.
- @@jcmd@@: query heap info, thread dumps, VM flags, system properties, and control JFR.

Use @@jstat@@ to spot the time window or trend worth investigating; use specialized tools to pinpoint the root cause.

## 9. Common errors and troubleshooting

| Symptom | Possible cause | How to check |
|---|---|---|
| @@jstat@@ not recognized | JDK @@bin@@ is not in @@PATH@@, or only a runtime image is installed | Check @@where.exe jstat@@ on Windows or @@which jstat@@ on Linux/macOS |
| VMID not found | Wrong PID/lvmid or the JVM has exited | Re-run @@jps -l@@ and verify the process |
| JVM not visible in Docker | JVM is in a different PID namespace/container | Run @@jps@@/@@jstat@@ inside the target container |
| Cannot read performance data | Permissions, perfdata disabled, or JVM does not expose expected instrumentation | Check user, runtime, JVM flags, and @@UsePerfData@@ setting |
| Some columns show @@-@@ | Collector does not provide that counter or it does not apply | Identify the GC collector and check the matching JDK docs |
| No GC seen across several samples | Low load, interval too short, or no collection in the observation window | Increase observation duration or use a controlled test workload |
| E rises then drops sharply | Eden was allocated into and reclaimed after Young GC | Cross-check @@YGC@@ and @@YGCT@@ |
| O rises across many samples | Promotion or long-lived objects; possible heap pressure | Check post-GC trends, @@FGC@@, GC logs, and heap |
| Counters drop suddenly | JVM restarted, VMID changed, or sample series switched to another process | Verify PID, start time, and JVM session |
| Header hard to read in long files | Header is only printed at the top | Use @@-h n@@ to repeat the header |
| Parsing script breaks after JDK upgrade | Output format or columns changed | Check @@jstat -options@@ and update the parser with tests |

## 10. Practical sampling workflow

1. Identify the target JVM using @@jps -l@@ or OS tools.
2. Verify the JDK, collector, and permissions to read performance data.
3. Run @@jstat -options@@ to see available stat options.
4. Start with @@-gcutil@@ at around a 1-second interval and a finite count.
5. If you need capacity details, add @@-gc@@; if you need causes, use @@-gccause@@.
6. Add @@-t@@ for time-based comparison and @@-h n@@ to keep files readable.
7. Compute deltas of cumulative counters between samples.
8. Flag windows with rapid GC growth, Full GCs, rising Old Space, or unusual Metaspace.
9. Capture GC logs or JFR when detailed event and phase analysis is needed.
10. Save output together with JDK version, interval, count, and load context.

## 11. Pre-conclusion checklist

- [ ] Correct VMID and target instance.
- [ ] Confirmed JDK/vendor and collector.
- [ ] Checked available options with @@jstat -options@@.
- [ ] Recorded interval, count, and timestamps.
- [ ] Did not confuse cumulative counters with instantaneous utilization.
- [ ] Computed deltas between samples from the same JVM session.
- [ ] Checked both used and capacity when evaluating heap.
- [ ] Did not conclude a memory leak from a single high Old Space value.
- [ ] Did not conclude GC pressure from a single sample with Eden near 100%.
- [ ] Cross-checked GC logs/JFR when exact causes or pause times were needed.
- [ ] Not relying on a CLI parser untested against the target JDK.

## 12. Key takeaways

Interval sampling with @@jstat@@ helps you track how a JVM changes over time. @@interval@@ controls sampling frequency, @@count@@ controls the number of samples, @@-t@@ adds elapsed time since JVM startup, and @@-h n@@ repeats headers to keep output readable.

Use @@-gcutil@@ to view percentage utilization, @@-gc@@ to view capacity and usage, and @@-gccause@@ to view GC causes, then compare consecutive rows. Counters such as @@YGC@@, @@YGCT@@, @@FGC@@, and @@GCT@@ are cumulative; compute per-interval deltas rather than looking only at totals since JVM startup. Treat @@jstat@@ as a trend-observation tool, and use GC logs or JFR to determine deeper root causes.

References:

- [The jstat Command — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jstat.html)
- [The jps Command — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jps.html)
- [The jstatd Command — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jstatd.html)
- [Java SE 21 Troubleshooting Guide](https://docs.oracle.com/en/java/javase/21/troubleshoot/troubleshooting-guide.pdf)