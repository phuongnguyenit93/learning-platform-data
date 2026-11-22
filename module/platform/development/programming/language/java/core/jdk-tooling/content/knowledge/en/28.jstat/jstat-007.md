# Sample Count in jstat

In `jstat`, the **count** parameter specifies how many times the tool samples and prints statistics from a running JVM. Each sample is a point-in-time snapshot of JVM counters or metrics. For example, `jstat -gcutil <pid> 250ms 5` requests 5 samples, spaced approximately 250 milliseconds apart.

Count is the number of sample data rows that `jstat` prints; it is not the number of garbage collections, objects, or application events. Columns such as `YGC` and `FGC` in GC reports are separate cumulative GC event counters.

## 1. Syntax and Position of Count

General syntax:

~~~sh
jstat <statOption> [-t] [-h lines] <vmid> [interval [count]]
~~~

Components:

| Component | Meaning |
|---|---|
| `<statOption>` | Type of statistics to view, such as `-gcutil`, `-gc`, or `-class` |
| `-t` | Adds a timestamp column showing elapsed time since the target JVM started |
| `-h lines` | Repeats the header row after every `lines` samples |
| `<vmid>` | Identifier of the target JVM; for a local JVM this is usually the PID |
| `interval` | Time interval between samples |
| `count` | Number of samples to collect before exiting |

`count` comes after `interval` in the syntax. Therefore, to request 5 samples 250 ms apart, both parameters must be passed:

~~~sh
jstat -gcutil 18360 250ms 5
~~~

The command above requests 5 samples from the JVM with VMID `18360`. You cannot omit `interval` and place `count` in the next position; that positional argument will be interpreted as the interval.

## 2. How Count and Interval Work

`interval` determines the sampling cadence; `count` determines the number of samples. Both parameters follow these rules:

- Interval must be a positive integer.
- The default unit is milliseconds (`ms`).
- You can explicitly specify the `ms` or `s` suffix.
- Count must be a positive integer.
- When `interval` is provided without `count`, count defaults to infinite: `jstat` continues printing samples until the target JVM terminates or the user stops the command.
- In testing with JDK 24.0.2, if only the stat option and VMID are passed without an interval, `jstat` prints a single snapshot and exits.

Equivalent interval examples:

~~~sh
jstat -gcutil 18360 250 5
jstat -gcutil 18360 250ms 5
jstat -gcutil 18360 1s 5
jstat -gcutil 18360 1000ms 5
~~~

The first two commands collect 5 samples 250 ms apart. The last two collect 5 samples 1 second apart.

Do not treat `interval` as a strict real-time schedule. Actual timing can drift due to counter read time, system load, thread scheduling, and JVM latency. Spacing between rows is usually close to the requested interval, but can be longer when the machine is busy.

## 3. Finite Count Examples

Collect 3 GC utilization samples, 200 ms apart:

~~~sh
jstat -gcutil 18360 200ms 3
~~~

The output contains one header row and exactly 3 data rows. Below is illustrative output from JDK 24.0.2; values vary by process:

~~~text
  S0     S1      E      O      M     CCS    YGC    YGCT    FGC    FGCT    CGC    CGCT     GCT
   -      -    4.26   0.00      -      -      0   0.000      0   0.000      0   0.000   0.000
   -      -    6.38   0.00      -      -      0   0.000      0   0.000      0   0.000   0.000
   -      -    8.51   0.00      -      -      0   0.000      0   0.000      0   0.000   0.000
~~~

What to verify here is that there are exactly 3 sample rows after the header, not that the numbers match the example identically.

Some useful commands:

~~~sh
jstat -gcutil <pid> 1s 10
jstat -gc <pid> 500ms 6
jstat -class <pid> 2s 4
~~~

- The first command collects 10 GC utilization samples, roughly 1 second apart.
- The second command collects 6 heap/GC statistics samples in KB, roughly 500 ms apart.
- The third command collects 4 class loading statistics samples, roughly 2 seconds apart.

## 4. Default Infinite Count and How to Stop It

If you pass an interval without a count, `jstat` samples indefinitely:

~~~sh
jstat -gcutil 18360 1s
~~~

The command keeps printing one data row roughly every second. It terminates when the target JVM exits or when the user stops the `jstat` process with `Ctrl+C`.

Infinite mode is useful when observing a load phase or waiting for a GC event. However, if you only need a short report, specify a finite count to avoid forgetting a running monitoring process and generating unnecessary output.

You can choose the sample count based on your observation goal:

| Goal | Example | Sample Count |
|---|---|---:|
| Quick check | `jstat -gcutil <pid> 250ms 3` | 3 |
| Short observation | `jstat -gcutil <pid> 1s 10` | 10 |
| Monitor until stopped manually | `jstat -gcutil <pid> 1s` | Infinite |

If the target JVM terminates before reaching the requested count, sampling stops along with the target process; the actual number of rows may be fewer than the requested count.

## 5. Count vs. GC Event Counts

This is the most common point of confusion. `count` counts how many times `jstat` takes a sample. Meanwhile, GC columns reflect how many GC events have occurred inside the JVM.

With the `-gcutil` option:

| Column | Meaning |
|---|---|
| `YGC` | Cumulative number of young-generation GC events |
| `FGC` | Cumulative number of full GC events |
| `YGCT` | Total young GC time |
| `FGCT` | Total full GC time |
| `GCT` | Total GC time |

For example, the command:

~~~sh
jstat -gcutil 18360 250ms 5
~~~

collects 5 samples. If no new GC occurs during those 5 observation intervals, `YGC` and `FGC` values can stay identical across all 5 rows. If a GC occurs between two samples, these counters increment. The number of GC events does not necessarily equal 5.

Simply put:

- `count=5`: the tool reads state 5 times.
- `YGC=8`: the JVM has recorded 8 young GC events since the counters started.
- One sample does not equal one GC event.

## 6. Combining Count with -h and -t

The `-h` option controls how often the header repeats. For example:

~~~sh
jstat -gcutil -h2 18360 250ms 5
~~~

This command collects 5 samples and reprints the header after every 2 samples. The output looks like:

~~~text
S0  S1  E  O  M  CCS  YGC  YGCT  FGC  FGCT  CGC  CGCT  GCT
-   -   4  0  -  -    0    0.0   0    0.0   0    0.0   0.0
-   -   6  0  -  -    0    0.0   0    0.0   0    0.0   0.0
S0  S1  E  O  M  CCS  YGC  YGCT  FGC  FGCT  CGC  CGCT  GCT
-   -   8  0  -  -    0    0.0   0    0.0   0    0.0   0.0
-   -  10  0  -  -    0    0.0   0    0.0   0    0.0   0.0
S0  S1  E  O  M  CCS  YGC  YGCT  FGC  FGCT  CGC  CGCT  GCT
-   -  12  0  -  -    0    0.0   0    0.0   0    0.0   0.0
~~~

Reprinted headers do not count toward `count`. With 5 samples and `-h2`, there are 5 data rows and 3 header occurrences: at the start of the output, after sample 2, and after sample 4.

The `-t` option adds a `Timestamp` column at the beginning of each sample:

~~~sh
jstat -gcutil -t 18360 250ms 5
~~~

Timestamp is the number of seconds elapsed since the target JVM started, not wall-clock time. It helps correlate samples with process age and runtime events. On a busy system, timestamps may not be spaced at exact intervals due to scheduling latency.

Both options can be combined:

~~~sh
jstat -gcutil -t -h2 18360 250ms 5
~~~

## 7. Choose the Stat Option Before Choosing Count

Count applies to the output option you select. Use `jstat -options` to view the available statistics options on your current JDK.

Some commonly used options:

| Option | Contents |
|---|---|
| `-gcutil` | Heap space utilization percentages and GC counters |
| `-gc` | Heap space capacities and utilization in KB along with GC counters |
| `-class` | Class loading/unloading statistics |
| `-compiler` | JIT compiler activity |
| `-gccause` | GC statistics and the cause of the last/current GC |

Example collecting 8 class loading samples:

~~~sh
jstat -class 18360 1s 8
~~~

Example collecting 6 GC utilization samples:

~~~sh
jstat -gcutil 18360 500ms 6
~~~

Count only determines how many times data is collected. It does not turn `-gcutil` into `-gc` or change column meanings. Pick the right stat option for the question you are investigating, then decide on the interval and count.

## 8. Runnable Java 17+ Practice Example

The following program continuously allocates byte arrays and retains a ring buffer of the 200 most recent arrays. It generates heap activity to observe with `jstat`. The program runs until you press Ctrl+C.

Create `StatProbe.java`:

~~~java
public class StatProbe {
    public static void main(String[] args) throws InterruptedException {
        byte[][] retained = new byte[200][];
        int next = 0;

        System.out.println("stat-probe-ready");

        while (true) {
            retained[next] = new byte[64 * 1024];
            next = (next + 1) % retained.length;
            Thread.sleep(20);
        }
    }
}
~~~

Compile with Java 17 or later:

~~~sh
mkdir -p out
javac --release 17 -d out StatProbe.java
~~~

Run the application:

~~~sh
java -Xms128m -Xmx128m -cp out StatProbe
~~~

Exact stdout when the program starts:

~~~text
stat-probe-ready
~~~

Keep this terminal open. Open a second terminal and find the PID:

~~~sh
jcmd -l
~~~

Suppose the PID is `18360`. Collect 3 samples:

~~~sh
jstat -gcutil 18360 200ms 3
~~~

The output has one header and exactly 3 data rows. Next, collect 5 samples with timestamps and a header repeated every 2 samples:

~~~sh
jstat -gcutil -t -h2 18360 200ms 5
~~~

In testing with JDK 24.0.2, the first command printed exactly 3 samples; the second printed exactly 5 samples and 3 headers. Heap values, GC counters, and timestamps depend on machine speed and execution timing.

When finished, return to the terminal running `StatProbe` and press `Ctrl+C` to stop the JVM.

## 9. Choosing Interval and Count for Monitoring Goals

No single interval/count pair fits every situation. Choose based on how fast metrics change and how long you need to observe:

- For a quick before/after check around an operation, use a few samples with a short interval.
- When observing GC or heap utilization during a sustained workload, use an interval of around one second and a count large enough to cover that phase.
- When waiting for an event whose timing is unknown, you can omit count and stop manually once enough data is collected.
- When redirecting output to a file, use a finite count to bound file size and recording duration.

An interval that is too short increases read frequency and produces lots of output, without guaranteeing detection of very brief events. An interval that is too long can miss short-lived changes between samples. Choose a frequency sufficient to answer your investigation question, rather than simply picking the smallest possible value.

Samples are taken at discrete points in time. If a GC starts and finishes between two samples, you may see the GC counter increase without directly observing the state during the GC. Use GC logs, Java Flight Recorder, or an appropriate observability tool if you need a more detailed timeline.

## 10. Saving Output and Automation Caveats

You can redirect output to a file for later review:

~~~sh
jstat -gcutil 18360 1s 60 > gc-samples.txt
~~~

This command writes at most 60 samples, roughly one second apart. In PowerShell:

~~~powershell
jstat -gcutil 18360 1s 60 | Out-File -Encoding utf8 gc-samples.txt
~~~

Do not rely long-term on parsing `jstat` output with rigid scripts. Oracle documentation warns that output formats may change across releases. If you need production telemetry, consider JMX, Java Flight Recorder, or a metrics system with a more stable schema.

`jstat` is marked in the JDK documentation as an experimental and unsupported tool; options and functionality may change or be removed in future JDK releases. Check `jstat -help` and `jstat -options` on the exact JDK you are using.

## 11. Common Issues and Troubleshooting

| Symptom | Common Cause | Resolution |
|---|---|---|
| Only one sample printed, then exits | No interval passed; in tested JDK 24.0.2, the command prints one snapshot | Add both interval and count if you need a sample series |
| Command runs forever without stopping | Interval provided without count; count defaults to infinite | Pass a finite count or press Ctrl+C |
| Fewer data rows than count | Target JVM exited before reaching count or attach was interrupted | Check target JVM status and error output |
| Invalid interval error | Interval is not a positive integer or unit format is wrong | Use formats like `250ms` or `1s` |
| Invalid count error | Count is not a positive integer | Use a positive integer, such as 5 or 10 |
| Header appears multiple times | `-hN` is being used | Header repeats per sample count; headers are not counted toward `count` |
| Mistaking YGC/FGC for sample count | Confusing cumulative GC counters with sample count | Count is the number of data rows; YGC/FGC are GC event counts |
| JVM not found | Wrong PID, JVM already stopped, or different container/PID namespace | Use `jcmd -l` or `jps -l` in the right environment |
| Metrics change unevenly | Workload fluctuations and OS scheduling | Inspect timestamps, increase interval if needed, and check supplementary logs/recordings |
| Output parsing script breaks after JDK upgrade | `jstat` format can change | Avoid column-based parser dependencies; use telemetry with a stable schema |

## 12. Sample Count Workflow

1. Identify the target JVM using `jcmd -l` or `jps -l`.
2. Choose the stat option that fits your goal, such as `-gcutil` for heap/GC percentages.
3. Choose a positive interval with a clear unit like `250ms` or `1s`.
4. Choose a positive count matching the number of samples to collect.
5. Add `-t` if you need to correlate elapsed time since JVM startup.
6. Add `-hN` if the output is long and repeating headers aid readability.
7. Run the command and count data rows, excluding headers.
8. Compare samples over time; distinguish `count` from cumulative GC counters.
9. If continuous monitoring is needed, decide clearly how it will stop or use a finite count.
10. Keep the experimental/unsupported caveats in mind and avoid depending on the output format for long-term scripts.

### Checklist

- [ ] Correct VMID/PID selected.
- [ ] Appropriate stat option selected.
- [ ] Interval is a positive integer and the unit is understood.
- [ ] Count is a positive integer when a finite number of samples is desired.
- [ ] Understood that omitting count when interval is given runs indefinitely.
- [ ] Understood that count is the number of samples, not GC events.
- [ ] Distinguished headers repeated by `-h` from data rows.
- [ ] Used `-t` when elapsed time since JVM startup is needed.
- [ ] Verified actual sample count and target JVM status.
- [ ] Considered that output format may change in future JDK releases.

The `count` parameter bounds how many samples `jstat` collects, while `interval` sets the sampling cadence. By understanding both parameters, distinguishing samples from GC counters, and combining `-h`/`-t` properly, you can gather just enough metrics for JVM analysis without leaving a monitoring command running unintentionally.

## References

- [Oracle JDK 24 — The jstat Command](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jstat.html)
- [Oracle JDK 24 — Diagnostic Tools, jstat Utility](https://docs.oracle.com/en/java/javase/24/troubleshoot/diagnostic-tools.html)
- [Oracle JDK 24 — JDK Tool Specifications](https://docs.oracle.com/en/java/javase/24/docs/specs/man/index.html)