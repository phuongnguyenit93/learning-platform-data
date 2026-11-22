# Compiler Statistics with jstat

## 1. Overview

`jstat` is a JDK command-line tool for reading performance counters from a running Java HotSpot Virtual Machine (JVM). For compiler statistics, it helps observe Just-In-Time (JIT) compiler activity: the number of compilation tasks performed, failed tasks, invalidated tasks, and time spent on compilation.

The JVM typically starts by interpreting bytecode. When a method or code block is executed frequently enough, HotSpot can compile it into machine code to speed up subsequent runs. With tiered compilation, multiple compilation levels can be used as the application warms up.

Compiler statistics are useful when you want to:

- Check whether the JVM is performing JIT compilation.
- Observe the total number of compilation tasks and compilation time.
- Detect failed or invalidated compilation tasks.
- View the most recently compiled method.
- Compare compiler activity during warm-up and under actual load.

`jstat` provides aggregated metrics and snapshots. It does not replace a profiler, JFR, or detailed compiler logs; a single line of statistics does not by itself explain why a method was compiled, why compilation failed, or how much compilation improved latency.

## 2. Distinguishing the Two Compiler Modes

There are two output options directly related to JIT:

| Command | Content | Question Answered |
|---|---|---|
| `jstat -compiler` | Aggregated compiler activity statistics | How many compilation tasks has the JVM performed, how many failed, and how long did they take? |
| `jstat -printcompilation` | Information on the most recently compiled method | Which method was just processed by the compiler, and what are its bytecode size and compilation type? |

`-compiler` shows the overall compiler trend. `-printcompilation` shows the most recent method at the time of sampling. It is not a complete list of all methods ever compiled and does not store the full compilation history.

Both commands use the same JVM metric-collection mechanism but serve two different perspectives. Choose the output option based on the question you need to investigate.

## 3. jstat Syntax and Identifying the JVM

General syntax:

~~~bash
jstat -<option> [-t] [-h<lines>] <vmid> [<interval> [<count>]]
~~~

Components:

- `-compiler` or `-printcompilation` is the output option to inspect.
- `-t` adds a timestamp column showing the elapsed time since the target JVM started.
- `-h<lines>` reprints the header row after the specified number of samples.
- `vmid` is the Virtual Machine Identifier of the JVM to monitor.
- `interval` is the delay between samples.
- `count` is the number of samples to take.

View help:

~~~bash
jstat -help
~~~

List output options supported by the current JDK version:

~~~bash
jstat -options
~~~

On the tested JDK 24.0.2, the list includes `-compiler` and `-printcompilation` along with other options such as `-class`, `-gc`, `-gcutil`, `-gccapacity`, and `-gccause`.

Typically, `vmid` is a local JVM identifier (LVMID), which usually matches the operating system process ID, though this is not guaranteed in all cases. You can use:

~~~bash
jps -l
~~~

Locate the exact application class or JAR and use the corresponding identifier. Do not copy example PIDs from documentation into a real environment.

Example with a local process:

~~~bash
jstat -compiler 24816
jstat -printcompilation 24816
~~~

Replace `24816` with the actual LVMID/PID.

## 4. Reading jstat -compiler Output

Run:

~~~bash
jstat -compiler <pid>
~~~

The output looks like:

~~~text
Compiled Failed Invalid   Time   FailedType FailedMethod
      31      0       0     0.01          0
~~~

Column meanings:

| Column | Meaning |
|---|---|
| `Compiled` | Total number of compilation tasks performed |
| `Failed` | Number of failed compilation tasks |
| `Invalid` | Number of invalidated compilation tasks |
| `Time` | Total time spent on compilation tasks |
| `FailedType` | Compilation type of the most recent failed compilation |
| `FailedMethod` | Class and method name of the most recent failed compilation |

### Compiled

This is the number of compilation tasks performed, not the number of methods currently in the code cache and not the number of bytecode methods in the application. The value typically increases as the JVM continues running a workload that causes the JIT to compile more code.

### Failed

This is the number of failed compilation tasks. It is not the number of exceptions thrown by the application. A Java method can throw exceptions at runtime without any compilation task failing.

If this value increases, look for more details in the compiler log, JFR, or an appropriate diagnostic tool. This counter alone does not provide a stack trace or detailed root cause.

### Invalid

This is the number of invalidated compilation tasks. An invalidated compilation is a different state from a failed compilation. The JVM may have to discard compiled code when optimization assumptions no longer hold; you should not automatically treat every invalidation as an application bug.

### Time

This is the time spent on compilation tasks. The value is an aggregated metric, not request latency and not the individual compilation time of the most recent method.

### FailedType and FailedMethod

These two columns describe the most recent failed compilation: the compilation type and the associated class/method. If no compilation failure has occurred, they may display `0` or remain blank depending on the field and JVM version.

They are not a list of all compiler errors and do not explain why the failure occurred.

## 5. Reading jstat -printcompilation Output

Run:

~~~bash
jstat -printcompilation <pid>
~~~

Example output from the practice process:

~~~text
Compiled  Size  Type Method
      31   132     1 demo/CompilerStatsDemo main
~~~

Columns:

| Column | Meaning |
|---|---|
| `Compiled` | Number of compilation tasks performed for the most recently compiled method, per the jstat specification |
| `Size` | Number of bytes of bytecode for that method |
| `Type` | Compilation type |
| `Method` | Class and method name just compiled |

Class names use `/` instead of `.` as package separators, for example `demo/CompilerStatsDemo`. The `Type` column is the compilation type value reported by the JVM; do not assume a fixed number maps to C1/C2 without checking the documentation for the exact JVM version.

Note: the `Compiled` column appears in both `-compiler` and `-printcompilation`, but its interpretation depends on the output option. With `-compiler`, it is the aggregated number of compilation tasks. With `-printcompilation`, it is the information associated with the most recently compiled method as defined by the jstat documentation.

`-printcompilation` displays the latest method at the time of sampling. If multiple methods are compiled between two samples, some methods may not appear in the output. Use compiler logs or JFR when you need a detailed timeline.

## 6. Taking Multiple Samples Over Time

If you only run:

~~~bash
jstat -compiler <pid>
~~~

`jstat` prints one sample and exits.

Take 5 samples, once per second:

~~~bash
jstat -compiler <pid> 1000 5
~~~

The sampling interval can include units:

~~~bash
jstat -compiler <pid> 250ms 8
jstat -compiler <pid> 2s 5
~~~

If an interval is provided without a count, `jstat` continues sampling until the JVM exits or the user stops the command.

Add a timestamp:

~~~bash
jstat -compiler -t <pid> 1000 5
~~~

The `Timestamp` column shows the elapsed seconds since the target JVM started. It is not the current operating system wall-clock time.

Reprint the header after every 3 samples:

~~~bash
jstat -compiler -t -h3 <pid> 250ms 9
~~~

Sampling options are useful when observing compiler warm-up, but an overly short interval can generate a lot of output without adding useful information. Choose an interval long enough to observe changes and short enough to match the issue being investigated.

## 7. Complete Java 17 Example to Generate JIT Activity

Create `src/demo/CompilerStatsDemo.java`:

~~~java
package demo;

/** Generates a repeatable workload for observing JIT compiler statistics. */
public final class CompilerStatsDemo {
    private static volatile long sink;

    private static long hotMethod(int value) {
        long result = value;
        for (int i = 0; i < 100; i++) {
            result = result * 31 + i;
        }
        return result;
    }

    /**
     * Runs a warm-up workload, then stays active for jstat inspection.
     *
     * @param args command-line arguments
     * @throws InterruptedException if the sleep is interrupted
     */
    public static void main(String[] args) throws InterruptedException {
        long sum = 0;
        for (int i = 0; i < 5_000_000; i++) {
            sum += hotMethod(i);
        }
        sink = sum;

        System.out.println("READY sink=" + sink);

        while (true) {
            for (int i = 0; i < 100_000; i++) {
                sink ^= hotMethod(i);
            }
            Thread.sleep(100);
        }
    }
}
~~~

Compile with JDK 17 or later:

~~~bash
javac --release 17 -d out src/demo/CompilerStatsDemo.java
~~~

Open Terminal 1 and run:

~~~bash
java -Xms32m -Xmx128m -cp out demo.CompilerStatsDemo
~~~

Exact stdout in the test environment:

~~~text
READY sink=-3778119394682985248
~~~

Keep the process running to collect metrics from Terminal 2.

Find the PID:

~~~bash
jps -l
~~~

Collect compiler statistics:

~~~bash
jstat -compiler <pid>
~~~

Monitor 5 samples, once per second:

~~~bash
jstat -compiler -t <pid> 1000 5
~~~

View the most recently compiled method:

~~~bash
jstat -printcompilation <pid>
~~~

Track the latest method across multiple samples:

~~~bash
jstat -printcompilation <pid> 250ms 5
~~~

In the test run on JDK 24.0.2, the compiler performed 31 tasks with no failed or invalidated tasks, and total compilation time displayed as `0.01`. `-printcompilation` recorded `demo/CompilerStatsDemo main` with bytecode size `132` and compilation type `1`. Metrics may vary across runs, JDKs, CPUs, and workloads.

When finished, return to Terminal 1 and press Ctrl+C to stop the program.

## 8. Understanding Compiler Statistics Trends

Do not draw performance conclusions from a single sample. Take multiple samples and compare them over time.

| Observation | Appropriate Interpretation |
|---|---|
| `Compiled` increases | The JVM continues to perform compilation tasks |
| `Failed` increases | A compilation task failed; investigate further details |
| `Invalid` increases | A compilation task was invalidated |
| `Time` increases | Total time spent on compilation tasks increased |
| `FailedMethod` has a method name | This is the method associated with the most recent compilation failure |
| `-printcompilation` changes method | Another method became the most recently compiled method |

Notes for analysis:

- `Compiled` increasing during warm-up is normal; it does not automatically mean the compiler has a problem.
- `Failed=0` only indicates that the counter recorded no failed compilation tasks at that point. It does not prove the application is bug-free.
- `Invalid` is different from `Failed`; do not lump the two columns together as a single error type.
- `Time` is total compiler time, not CPU percentage or request processing time.
- `FailedType` and `FailedMethod` only describe the most recent failure, not the full history.
- If a method does not appear in `-printcompilation`, it may not have been compiled yet or may have been replaced by another method before the next sample.

JIT compilation depends on invocation counts, compilation thresholds, tiered compilation, compiler mode, and actual load. A short-lived application or one with few method calls may not generate enough activity for the counters to increase.

## 9. When the Compiler Has No Metrics

If the JVM is run in interpreted mode:

~~~bash
java -Xint -cp out demo.CompilerStatsDemo
~~~

The JIT compiler is disabled. In the test run on JDK 24.0.2, `jstat -compiler` displayed `-` in the compiler columns instead of `0`; `-printcompilation` also had no method compilation to report.

This is different from a compilation failure. The `-` indicates that the data field has no value in that JVM configuration.

Other cases where counters may not increase:

- The JVM has just started and no method is hot enough yet.
- The workload does not repeatedly call methods that require JIT.
- The JVM is configured to restrict or disable the compiler.
- The process exits before a sample is taken.
- Permissions or instrumentation do not allow `jstat` to read the metrics.

Before concluding that the compiler is inactive, check JVM flags, uptime, workload, and attachability.

## 10. Limitations of jstat and Complementary Tools

Oracle marks `jstat` as **experimental and unsupported**. Options, behavior, and output formats may change or be removed in future JDK releases.

Oracle documentation also recommends against writing scripts that depend on parsing `jstat` text output. If automation is unavoidable, be prepared to update scripts when the tool format changes.

`jstat -compiler` does not provide:

- Stack traces or detailed causes of compilation failures.
- A complete timeline of every compiled method.
- Individual compilation time per method.
- Complete information about the code cache or native memory.
- Allocation, lock, CPU stack, or request latency analysis.

When more data is needed:

- Use `-XX:+PrintCompilation` to log HotSpot compilation events in a configured run.
- Use Java Flight Recorder (JFR) and Java Mission Control to view runtime events over time.
- Use a profiler to analyze CPU hotspots, call trees, and method behavior.
- Use `jcmd <pid> help` to discover diagnostic commands supported by the target JVM.

Do not enable high-overhead logging or profiling in production without evaluating the performance impact and output volume.

## 11. Common Errors

### Unknown option: compiler

Check `jstat -options` to see whether the current JDK version supports this output option. Make sure you are running `jstat` from the appropriate JDK.

### Could not attach to process

Verify that the LVMID/PID still exists, the tool has permission to access the process, and the target JVM has the instrumentation `jstat` requires. Use `jps -l` to look up the identifier again.

### Compiler columns show `-`

Check whether the JVM is running with `-Xint` or a configuration that disables the compiler. A `-` is not evidence of a failed compilation.

### Compiled does not increase

The application may not have been running long enough, methods may not be hot enough, or the JIT compiler may be inactive. Generate a repeatable workload, check VM flags, and take more samples.

### Failed increases but FailedMethod is empty

`FailedMethod` only describes the most recent failure and may not provide enough information in every case. Collect compiler logs or JFR to investigate the root cause.

### -printcompilation does not show the expected method

The command only shows the most recently compiled method at the time of sampling. Another method may have been compiled afterward. Sample more frequently or use compilation logs if you need a timeline.

### Output changes after upgrading the JDK

`jstat` is an experimental/unsupported tool. Re-read `jstat -help`, `jstat -options`, and the documentation for your exact JDK version; do not assume column names or formats remain stable.

## 12. Practical Compiler Monitoring Workflow

1. Identify the JVM with `jps -l` and confirm the right PID.
2. Run `jstat -options` to verify supported options.
3. Capture an initial baseline sample with `jstat -compiler <pid>`.
4. Monitor multiple samples with `jstat -compiler -t <pid> 1000 5`.
5. Use `jstat -printcompilation <pid>` to inspect the latest method.
6. Compare `Compiled`, `Failed`, `Invalid`, and `Time` across samples.
7. If `Failed` or `Invalid` changes unusually, collect compiler logs/JFR and inspect VM flags.
8. Record the JDK version, PID, timestamp, workload, and commands run so results can be compared.
9. Stop sampling once enough data has been collected.

For production systems, start with a moderate interval and a limited sample count. Increase sampling frequency only when you have a specific question to answer.

## 13. Checklist

- [ ] Identify the right JVM using `jps -l`.
- [ ] Use `jstat -options` to check available options.
- [ ] Use `jstat -compiler` to view aggregated statistics.
- [ ] Use `jstat -printcompilation` to view the most recently compiled method.
- [ ] Understand `Compiled`, `Failed`, `Invalid`, `Time`, `FailedType`, and `FailedMethod`.
- [ ] Use interval and count to limit the number of samples.
- [ ] Use `-t` to view elapsed time since JVM startup.
- [ ] Use `-h` to repeat headers in long output.
- [ ] Do not confuse compilation failures with application exceptions.
- [ ] Do not confuse `Invalid` with `Failed`.
- [ ] Check `-Xint` or compiler flags if columns display `-`.
- [ ] Do not parse output with scripts that rely on unstable formatting.
- [ ] Use JFR, compiler logs, or a profiler when more detailed data is needed.

`jstat -compiler` shows JIT activity at an aggregated level; `jstat -printcompilation` shows the most recent method processed by the compiler. Combining samples over time with a repeatable workload helps you understand warm-up phases and detect compiler changes, while logs or profilers should be used when deeper root-cause analysis is required.

## 14. References

- [Oracle JDK 24 — The jstat Command](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jstat.html): syntax, interval/count, timestamp, compiler counters, printcompilation, and tool limitations.
- [Oracle JDK 24 — Diagnostic Tools](https://docs.oracle.com/en/java/javase/24/troubleshoot/diagnostic-tools.html): using jstat to monitor HotSpot JVM performance and resource consumption.
- [Oracle JDK 17 — The jstat Command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jstat.html): description of compiler statistics and method statistics.
- [Oracle JDK 24 — The java Command](https://docs.oracle.com/en/java/javase/24/docs/specs/man/java.html): JVM options used in practice such as `-Xint` and `-XX:+PrintCompilation`.
