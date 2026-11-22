# Measuring CPU in Java Applications

This lesson belongs to the **Performance tooling** group on the topic **Measuring CPU**. The goal is to determine how much CPU time a Java application actually consumes, which threads are using the CPU, and which methods generate the largest share of the load. Then use those measurements to choose what to optimize and verify the results.

There is no single CPU number that answers every question. CPU time, wall-clock time, CPU utilization, sampling profiles, and benchmarks are different measurements. Choosing the wrong measurement can cause an application waiting on I/O to be mistaken for being CPU-bound, or cause a method that is called many times with very short duration per call to be mistaken for a hotspot.

The Java examples are compiled targeting Java 17 and run on Zulu/OpenJDK 24.0.2, Windows 11. The hands-on exercise measures the CPU time of each platform thread and the entire JVM process, then records JFR to identify hot methods.

## 1. First, identify the question you need to measure

Choose the tool based on the question:

| Question | Appropriate metric/tool |
|---|---|
| How much CPU did the Java process use in 10 seconds? | Process CPU time, Task Manager, `Get-Process`, `OperatingSystemMXBean` |
| Which thread is using the most CPU? | `ThreadMXBean`, JFR `jdk.ThreadCPULoad`, OS thread monitor |
| Which method is generating CPU load? | JFR execution samples, JDK Mission Control, async-profiler, `perf` |
| Does one algorithm run faster than another? | JMH benchmark |
| Is the JVM or the entire machine busy with CPU? | JFR `jdk.CPULoad`, OS metrics |
| Is a request slow because of CPU or because it is waiting? | CPU profile combined with JFR I/O, lock, park, sleep, and latency |
| Did CPU increase after a release? | Compare profiles, throughput, and CPU time before/after on the same workload |

Measure utilization to know the load level, use a profiler to find hot code paths, and use a benchmark to compare a piece of code in a controlled environment. These tools complement each other.

## 2. Distinguish CPU time, wall time, and CPU utilization

**Wall-clock time** is the elapsed time from the start to the end of an operation. It includes time the thread spends running, sleeping, waiting on locks, waiting on network, waiting on disk, and waiting on the scheduler.

**CPU time** is the total time the CPU actually spends running a process or thread. When a process has multiple threads running in parallel, CPU time can increase faster than wall time.

**CPU utilization** is the ratio of CPU time consumed during a wall-clock time interval. It is the rate of CPU consumption, not the total CPU time since the process started.

For example, four CPU-bound threads running in parallel for three seconds:

- Wall time may be approximately 3 seconds.
- Each thread may consume nearly 3 seconds of CPU.
- Total CPU time across the four threads may be approximately 12 seconds.
- The process may use the equivalent of four logical CPUs during that interval.

A thread that sleeps for three seconds has a wall time of three seconds but a CPU time close to zero. This is why `System.nanoTime()` cannot replace CPU time measurement.

## 3. Understand the two ways of expressing CPU percentage

There are two common ways to express process load:

1. **CPU core equivalent:** 100% equals one logical CPU running at full capacity. A process using four CPUs in parallel may display around 400%.
2. **Percentage of total machine capacity:** 100% equals all logical processors that the system counts in the denominator. A process using four CPUs on a machine with 28 logical processors equals about 14.3% of total capacity.

Formulas from CPU time and wall time:

~~~text
coreEquivalentPercent = deltaProcessCpuTime / deltaWallTime * 100

machineCapacityPercent =
    coreEquivalentPercent / availableProcessors
~~~

All time values in the division must use the same unit. The second result is already a percentage of total machine capacity because the first value is already in percent; do not multiply by 100 again.

Some dashboards normalize percentages to the whole machine, while others count 100% per CPU. Therefore, do not compare two charts directly without knowing their denominators. In a container, use the number of CPUs the JVM actually sees or the CPU quota allocated to the container; do not assume the host's physical core count.

## 4. Measure elapsed time properly

Use `System.nanoTime()` to measure an elapsed interval:

~~~java
long start = System.nanoTime();

performOperation();

long elapsedNanos = System.nanoTime() - start;
System.out.printf("elapsedMs=%.3f%n", elapsedNanos / 1_000_000.0);
~~~

`System.nanoTime()` is a monotonic clock suitable for measuring duration. It is not a CPU clock and does not tell you how long a thread has been running on the CPU.

Avoid using `System.currentTimeMillis()` to measure short operations or benchmarks. The wall-clock time-of-day can shift due to time synchronization and has a resolution unsuitable for many small measurements.

If a request takes 2 seconds but CPU time is only 30 ms, investigate the remaining time: network, database, locks, queues, file I/O, or scheduler. Optimizing a CPU loop may not improve latency in that situation.

## 5. Measure a thread's CPU time with `ThreadMXBean`

`ManagementFactory.getThreadMXBean()` returns a `ThreadMXBean`. On supported JVMs, this interface measures the CPU time of the current platform thread or another platform thread.

Example of measuring the CPU time of the currently running thread:

~~~java
import java.lang.management.ManagementFactory;
import java.lang.management.ThreadMXBean;

ThreadMXBean bean = ManagementFactory.getThreadMXBean();

if (!bean.isCurrentThreadCpuTimeSupported()) {
    throw new UnsupportedOperationException("Current-thread CPU time is not supported");
}

if (!bean.isThreadCpuTimeEnabled()) {
    bean.setThreadCpuTimeEnabled(true);
}

long cpuStart = bean.getCurrentThreadCpuTime();

performCpuWork();

long cpuNanos = bean.getCurrentThreadCpuTime() - cpuStart;
System.out.printf("threadCpuMs=%.3f%n", cpuNanos / 1_000_000.0);
~~~

Notes:

- Check `isThreadCpuTimeSupported()` or `isCurrentThreadCpuTimeSupported()` before using.
- CPU time measurement may be disabled by default; enable it with `setThreadCpuTimeEnabled(true)` when supported by the JVM.
- `getThreadCpuTime()` returns `-1` if the thread is no longer alive, measurement is not enabled, or measurement is unavailable.
- The API reports nanosecond precision, but does not guarantee actual nanosecond accuracy.
- Enabling CPU-time measurement may incur overhead on some JVMs.
- `ThreadMXBean` manages platform threads; this API does not measure CPU time of virtual threads.

To measure a thread pool, capture CPU time inside each task when the task starts and finishes. Do not wait until the task finishes and then call `getThreadCpuTime(threadId)`, because the thread may have already terminated and the API will return `-1`.

## 6. Measure the CPU time of the entire JVM process

HotSpot provides the platform extension `com.sun.management.OperatingSystemMXBean`. You can retrieve the cumulative CPU time of the process:

~~~java
import com.sun.management.OperatingSystemMXBean;
import java.lang.management.ManagementFactory;

var standardBean = ManagementFactory.getOperatingSystemMXBean();

if (standardBean instanceof OperatingSystemMXBean processBean) {
    long processCpuNanos = processBean.getProcessCpuTime();
    System.out.println("processCpuNanos=" + processCpuNanos);
}
~~~

`getProcessCpuTime()` returns the total CPU time used by the process in nanoseconds; it returns `-1` if the platform does not support it. This metric includes application threads and internal JVM threads. This API belongs to the platform extension in the `jdk.management` module, so check with `instanceof` rather than assuming every Java runtime provides the same implementation.

This extension also provides:

- `getProcessCpuLoad()`: recent CPU usage of the JVM process, in the range from 0.0 to 1.0 when available.
- `getCpuLoad()`: recent CPU usage of the whole operating environment, in the range from 0.0 to 1.0 when available.
- `getAvailableProcessors()`: number of processors visible to the JVM.

The observation window for load values depends on the implementation. The first call may not yet have a defined measurement interval; a negative value indicates data is not yet available or not supported. When you need to control the measurement interval yourself, take two samples of `getProcessCpuTime()` and `System.nanoTime()` and compute the delta.

## 7. Hands-on exercise: measure four CPU workers and one sleeping thread

The example below runs four CPU-bound workers for three seconds and one thread that only sleeps for three seconds. The program measures the CPU time of each worker, the sleeping thread, the entire JVM process, and wall time. After the measurement phase, it keeps a CPU-bound loop running for another 15 seconds so you can attach JFR from a second terminal.

Create `CpuMeasurementDemo.java`:

~~~java
import com.sun.management.OperatingSystemMXBean;
import java.lang.management.ManagementFactory;
import java.lang.management.ThreadMXBean;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public final class CpuMeasurementDemo {
    private static volatile long blackhole;

    private CpuMeasurementDemo() {
    }

    public static void main(String[] args) throws Exception {
        int processors = Runtime.getRuntime().availableProcessors();
        int workerCount = Math.min(4, processors);
        long phaseNanos = TimeUnit.SECONDS.toNanos(3);

        ThreadMXBean threadBean = ManagementFactory.getThreadMXBean();
        if (!threadBean.isThreadCpuTimeSupported()) {
            throw new UnsupportedOperationException(
                    "Thread CPU time is not supported");
        }
        if (!threadBean.isThreadCpuTimeEnabled()) {
            threadBean.setThreadCpuTimeEnabled(true);
        }

        var standardBean = ManagementFactory.getOperatingSystemMXBean();
        OperatingSystemMXBean processBean =
                standardBean instanceof OperatingSystemMXBean extension
                        ? extension : null;

        ExecutorService pool =
                Executors.newFixedThreadPool(workerCount + 1);
        CountDownLatch start = new CountDownLatch(1);
        List<Future<Long>> cpuWorkers = new ArrayList<>();

        for (int i = 0; i < workerCount; i++) {
            cpuWorkers.add(pool.submit(() -> {
                start.await();
                long cpuStart = threadBean.getCurrentThreadCpuTime();
                long wallDeadline = System.nanoTime() + phaseNanos;
                long value = 0x1234abcdL;

                while (System.nanoTime() < wallDeadline) {
                    value = value * 1664525L + 1013904223L;
                    value ^= value >>> 13;
                }

                blackhole ^= value;
                return threadBean.getCurrentThreadCpuTime() - cpuStart;
            }));
        }

        Future<Long> sleeper = pool.submit(() -> {
            start.await();
            long cpuStart = threadBean.getCurrentThreadCpuTime();
            Thread.sleep(TimeUnit.NANOSECONDS.toMillis(phaseNanos));
            return threadBean.getCurrentThreadCpuTime() - cpuStart;
        });

        long processCpuStart = processBean == null
                ? -1 : processBean.getProcessCpuTime();
        long wallStart = System.nanoTime();
        start.countDown();

        long totalWorkerCpu = 0;
        for (int i = 0; i < cpuWorkers.size(); i++) {
            long cpu = cpuWorkers.get(i).get();
            totalWorkerCpu += cpu;
            System.out.printf(Locale.ROOT, "WORKER_%d_CPU_MS=%.1f%n",
                    i + 1, cpu / 1_000_000.0);
        }

        long sleeperCpu = sleeper.get();
        long wallElapsed = System.nanoTime() - wallStart;
        long processCpuEnd = processBean == null
                ? -1 : processBean.getProcessCpuTime();

        pool.shutdown();
        pool.awaitTermination(5, TimeUnit.SECONDS);

        System.out.printf(Locale.ROOT, "AVAILABLE_PROCESSORS=%d%n", processors);
        System.out.printf(Locale.ROOT, "WORKER_COUNT=%d%n", workerCount);
        System.out.printf(Locale.ROOT, "SLEEPER_CPU_MS=%.1f%n",
                sleeperCpu / 1_000_000.0);
        System.out.printf(Locale.ROOT, "TOTAL_WORKER_CPU_MS=%.1f%n",
                totalWorkerCpu / 1_000_000.0);
        System.out.printf(Locale.ROOT, "WALL_TIME_MS=%.1f%n",
                wallElapsed / 1_000_000.0);

        if (processCpuStart >= 0 && processCpuEnd >= processCpuStart) {
            long processCpu = processCpuEnd - processCpuStart;
            double coreEquivalent =
                    processCpu * 100.0 / wallElapsed;
            double machineCapacity =
                    coreEquivalent / processors;

            System.out.printf(Locale.ROOT, "PROCESS_CPU_TIME_MS=%.1f%n",
                    processCpu / 1_000_000.0);
            System.out.printf(Locale.ROOT,
                    "CPU_CORE_EQUIVALENT_PERCENT=%.1f%n", coreEquivalent);
            System.out.printf(Locale.ROOT,
                    "MACHINE_CAPACITY_PERCENT=%.1f%n", machineCapacity);
        } else {
            System.out.println("PROCESS_CPU_TIME=UNAVAILABLE");
        }

        System.out.println(
                "PROFILE_PHASE_READY pid=" + ProcessHandle.current().pid());

        long profileDeadline =
                System.nanoTime() + TimeUnit.SECONDS.toNanos(15);
        long profileValue = 7;
        while (System.nanoTime() < profileDeadline) {
            profileValue =
                    profileValue * 6364136223846793005L
                            + 1442695040888963407L;
            profileValue ^= profileValue >>> 17;
        }
        blackhole ^= profileValue;
        System.out.println("PROFILE_PHASE_DONE");
    }
}
~~~

Compile targeting Java 17:

Windows PowerShell:

~~~powershell
javac --release 17 -encoding UTF-8 -Xlint:all -Werror CpuMeasurementDemo.java
~~~

Linux/macOS:

~~~sh
javac --release 17 -encoding UTF-8 -Xlint:all -Werror CpuMeasurementDemo.java
~~~

Run:

~~~text
java CpuMeasurementDemo
~~~

The program prints each worker's CPU time, the sleeping thread's CPU time, wall time, and total process CPU time. When you see the line `PROFILE_PHASE_READY`, switch to a second terminal to record JFR.

## 8. Read the measurement results and understand CPU core equivalent

An actual run on Windows 11 with Zulu JDK 24.0.2 and 28 logical processors produced results similar to:

~~~text
WORKER_1_CPU_MS=2937.5
WORKER_2_CPU_MS=2937.5
WORKER_3_CPU_MS=2906.3
WORKER_4_CPU_MS=2984.4
AVAILABLE_PROCESSORS=28
WORKER_COUNT=4
SLEEPER_CPU_MS=0.0
TOTAL_WORKER_CPU_MS=11765.6
WALL_TIME_MS=3009.0
PROCESS_CPU_TIME_MS=13687.5
CPU_CORE_EQUIVALENT_PERCENT=454.9
MACHINE_CAPACITY_PERCENT=16.2
PROFILE_PHASE_READY pid=79676
~~~

The timing numbers and PID vary by machine. How to interpret them:

- Each worker used nearly three seconds of CPU within about three seconds of elapsed time.
- The four workers combined used about 11.8 seconds of CPU.
- The sleeping thread had near-zero CPU time even though its wall time was also nearly three seconds.
- Process CPU time is higher than total worker CPU because the JVM also has JIT compiler, GC, and other internal threads.
- `454.9%` is equivalent to about 4.55 logical CPUs running continuously.
- `16.2%` is the share of the total capacity of the 28 logical processors reported by the JVM.

These results illustrate the difference between total CPU time and elapsed time. This is not an algorithm speed benchmark and should not be used to compare two different CPUs.

## 9. Measure process CPU on Windows with PowerShell

`Get-Process` has a `CPU` property representing the total processor time the process has used in seconds. Take two samples separated by a time interval:

~~~powershell
$javaPid = 12345
$process = Get-Process -Id $javaPid
$cpuStart = $process.CPU

$watch = [Diagnostics.Stopwatch]::StartNew()
Start-Sleep -Seconds 5
$process.Refresh()
$watch.Stop()

$cpuSeconds = $process.CPU - $cpuStart
$coreEquivalentPercent = 100 * $cpuSeconds / $watch.Elapsed.TotalSeconds
$machineCapacityPercent =
    $coreEquivalentPercent / [Environment]::ProcessorCount

"CPU core equivalent: {0:N1}%" -f $coreEquivalentPercent
"Machine capacity: {0:N1}%" -f $machineCapacityPercent
~~~

Replace `12345` with the JVM's PID. If the process exits during sampling, you need to find the new PID and start a fresh measurement interval. `Get-Process.CPU` is cumulative CPU time, not instantaneous utilization.

In Windows Task Manager, the Details tab can display CPU and CPU time; Resource Monitor and Performance Monitor provide additional per-process metrics. Make sure to select the right `java.exe` instance when multiple JVMs are running concurrently.

## 10. Measure processes and threads on Linux/macOS

On Linux, `pidstat` from the sysstat package can display CPU by process and thread:

~~~sh
pidstat -u -t -p "$JAVA_PID" 1
~~~

`top` can display individual threads:

~~~sh
top -H -p "$JAVA_PID"
~~~

On macOS, Activity Monitor helps identify CPU-consuming processes; Instruments Time Profiler lets you capture a call tree by CPU time.

OS tools are great for answering which process is busy. They do not always know Java method names. When you need to correlate CPU with Java call stacks, switch to JFR, JMC, or async-profiler.

## 11. Use Linux `perf` to measure and capture call stacks

`perf stat` measures counters over an interval:

~~~sh
perf stat -p "$JAVA_PID" -- sleep 10
~~~

Depending on the CPU and kernel, you can collect cycles, instructions, cache misses, context switches, and other counters. Not every hardware counter is available on every machine.

Capture call stack samples for 30 seconds:

~~~sh
perf record -F 99 -g -p "$JAVA_PID" -- sleep 30
perf report
~~~

`perf` can show Java, native, and kernel frames if symbol and unwind configuration are properly set up. Access to `perf_event` is restricted on some kernels or containers; check `perf_event_paranoid`, kernel policy, and user permissions before profiling.

For Java, async-profiler often makes mapping Java stacks and native stacks more convenient when you need a flame graph.

## 12. Use Java Flight Recorder to find CPU hotspots

Java Flight Recorder (JFR) records JVM and application events over a time interval. To capture a CPU profile from a running process, use `jcmd`.

After the sample program prints `PROFILE_PHASE_READY pid=...`, run in a second terminal:

~~~text
jcmd <pid> JFR.start name=cpu settings=profile duration=8s filename=cpu-profile.jfr
~~~

Check the recording:

~~~text
jcmd <pid> JFR.check name=cpu
~~~

Once the recording finishes, read the summary:

~~~text
jfr summary cpu-profile.jfr
~~~

Print key CPU events:

~~~text
jfr print --events jdk.CPULoad,jdk.ThreadCPULoad,jdk.ExecutionSample cpu-profile.jfr
~~~

- `jdk.CPULoad` shows JVM and machine-wide CPU load over time.
- `jdk.ThreadCPULoad` shows which threads are consuming CPU based on method sampling.
- `jdk.ExecutionSample` contains stack samples of executing code.
- `jdk.NativeMethodSample` can provide samples in native code.

Testing on JDK 24 recorded `jdk.ExecutionSample` and `jdk.ThreadCPULoad`; stack samples pointed to the loop in `CpuMeasurementDemo`. Sample counts and method ordering vary with recording duration and workload.

If starting the process with a recording enabled, you can use:

~~~text
java -XX:StartFlightRecording=name=cpu,settings=profile,duration=30s,filename=cpu.jfr -jar app.jar
~~~

For continuous recording, the `default` configuration is usually more appropriate. Use `profile` for short windows when you need method sampling and more detailed data. Measure overhead on a realistic workload before applying it to latency-sensitive environments.

## 13. Analyze CPU profiles with JDK Mission Control

JDK Mission Control (JMC) opens `.jfr` files and provides views for investigation:

- **Hot Methods:** methods with many execution samples.
- **Call Tree:** call stacks leading to hot methods.
- **Threads:** CPU load and state of each thread.
- **Automated Analysis:** notable performance indicators and configuration findings.
- **JVM Internals:** compiler, GC, allocation, class loading, and JVM events.

In Hot Methods, a method with many samples is where the application spends a relatively large amount of CPU time. Open Call Tree to see where that method is called from and which call paths lead to the hotspot.

Do not treat sample percentages as exact absolute CPU time. This is a sampling method. Low sample counts make conclusions unreliable; record longer on a representative workload or increase profiling detail when needed.

## 14. CPU sampling differs from wall-clock sampling

A CPU profiler takes samples from threads that are actually running on the CPU. Threads that are sleeping, waiting on locks, or waiting on I/O usually do not appear in a CPU profile.

A wall-clock profiler takes samples based on elapsed time, which can capture threads whether they are running, sleeping, or blocked. Therefore:

- A CPU profile answers: which code is consuming CPU?
- A wall-clock profile answers: where are threads spending time across the entire observation window?

If requests are slow while CPU usage is low, a wall-clock profile can reveal time spent waiting on network, locks, or queues. If CPU usage is high, a CPU profile usually finds hot methods faster.

## 15. Use async-profiler and flame graphs

async-profiler is an external sampling profiler for the JDK that supports CPU, allocation, wall-clock, lock contention, and other events. It can capture Java, native, JVM, and kernel stacks in supported environments.

A 30-second CPU profile command:

~~~text
asprof -d 30 -f cpu-profile.html <pid>
~~~

Generate a wall-clock profile:

~~~text
asprof -e wall -d 30 -f wall-profile.html <pid>
~~~

Open the HTML file in a browser to view the flame graph. In a flame graph, the horizontal width represents the proportion of samples across call stacks; a wide frame indicates that branch accounts for a large share of the sample set. The vertical axis is the call stack, not a timeline.

A CPU profile focuses on time threads spend running on the CPU. A wall-clock profile can show sleeping and blocked threads as well. Choose the right mode for your question; do not use a wall-clock graph to conclude that a method consumes a lot of CPU.

async-profiler is installed separately and is not a JDK command. Syntax, attach permissions, OS support, and kernel requirements depend on the release. On Linux, `perf_events` may be restricted by kernel policy; check the installation guide for the version you are using.

## 16. Choose a profiler by scenario

| Tool | Best suited for | Main limitations |
|---|---|---|
| JFR + JMC | CPU load, method samples, threads, GC, locks, and I/O in the JVM | Samples are statistical; recording settings affect overhead |
| `jcmd` | Starting/stopping JFR on a running JVM and fetching metadata | Does not generate flame graphs or benchmarks |
| async-profiler | CPU/native stacks, flame graphs, allocation, and wall-clock | Requires separate installation, attach permissions, and platform support |
| Linux `perf` | Process CPU, hardware counters, and kernel/native profiling | Depends on kernel, perf events, and symbols |
| Windows Task Manager/PerfMon | Process CPU and machine-wide load | Does not automatically map to Java methods |
| macOS Instruments | CPU sampling and call trees on macOS | Depends on Apple tooling environment |
| JMH | Comparing performance of an operation/algorithm | Does not replace a production profiler |

Start with built-in, low-intrusion tools. Only install additional profilers when you need call stacks, native frames, or event types that current tools do not provide.

## 17. JMH: benchmark CPU for a piece of code

Java Microbenchmark Harness (JMH) is OpenJDK's framework for benchmarking code running on the JVM. Use JMH when you need to compare two implementations or measure the throughput/latency of an operation.

JMH differs from a profiler:

- JMH answers how fast or slow an operation runs in a benchmark.
- A profiler answers where the application spends CPU in a workload.
- An OS monitor answers how much CPU the process is using on the machine.

Do not use `System.nanoTime()` in a hand-written loop to conclude one method is faster than another. The JVM has warmup, JIT compilation, dead-code elimination, constant folding, loop optimizations, GC, and scheduler effects; hand-written benchmarks easily end up measuring those instead.

## 18. Create a JMH project and run the benchmark

JMH recommends creating a standalone benchmark project using the Maven archetype:

~~~text
mvn archetype:generate -DinteractiveMode=false -DarchetypeGroupId=org.openjdk.jmh -DarchetypeArtifactId=jmh-java-benchmark-archetype -DgroupId=org.sample -DartifactId=cpu-bench -Dversion=1.0
~~~

After the project is generated:

~~~text
cd cpu-bench
mvn clean verify
java -jar target/benchmarks.jar -wi 5 -i 5 -f 3
~~~

- `-wi 5`: five warmup iterations.
- `-i 5`: five measurement iterations.
- `-f 3`: run three independent JVM forks.

These parameters are just a starting point. Adjust them according to benchmark duration, stability, startup cost, and workload variance. Keeping the JMH project separate from the application ensures the harness and annotation processor are configured properly. Running benchmarks directly inside an IDE often makes the environment harder to control.

## 19. JMH benchmark example

In the JMH project, create a benchmark class:

~~~java
package org.sample;

import java.util.concurrent.TimeUnit;
import org.openjdk.jmh.annotations.Benchmark;
import org.openjdk.jmh.annotations.BenchmarkMode;
import org.openjdk.jmh.annotations.Fork;
import org.openjdk.jmh.annotations.Level;
import org.openjdk.jmh.annotations.Measurement;
import org.openjdk.jmh.annotations.OutputTimeUnit;
import org.openjdk.jmh.annotations.Param;
import org.openjdk.jmh.annotations.Scope;
import org.openjdk.jmh.annotations.Setup;
import org.openjdk.jmh.annotations.State;
import org.openjdk.jmh.annotations.Warmup;
import org.openjdk.jmh.annotations.Mode;

@State(Scope.Thread)
@BenchmarkMode(Mode.Throughput)
@OutputTimeUnit(TimeUnit.SECONDS)
@Warmup(iterations = 5, time = 1)
@Measurement(iterations = 5, time = 1)
@Fork(3)
public class SumBenchmark {
    @Param({"1000", "100000"})
    public int size;

    private int[] values;

    @Setup(Level.Trial)
    public void setup() {
        values = new int[size];
        for (int i = 0; i < values.length; i++) {
            values[i] = i;
        }
    }

    @Benchmark
    public long sum() {
        long result = 0;
        for (int value : values) {
            result += value;
        }
        return result;
    }
}
~~~

JMH invokes the benchmark method through a harness generated by the annotation processor. Returning a value ensures the result is consumed, reducing the risk of dead-code elimination. If a benchmark does not return a value, you can use `Blackhole` as documented by JMH.

`@State(Scope.Thread)` gives each benchmark thread its own state. If you want to measure contention or throughput when multiple threads share state, choose the scope and thread count appropriate for your question. Do not change the scope just to boost throughput without reflecting a realistic workload.

`Mode.Throughput` results are operations per second; `Mode.AverageTime` measures average time per operation. Neither is CPU utilization.

## 20. How to read JMH and profiler results together

An effective workflow:

1. Use load tests or production metrics to identify slow endpoints/tasks.
2. Use JFR or async-profiler to find CPU-consuming methods and call paths.
3. Isolate the suspected logic into a JMH benchmark.
4. Compare implementations using the same inputs, JDK, forks, and warmup.
5. Apply the change to the application and rerun the end-to-end workload.
6. Confirm that throughput, latency percentiles, and CPU usage all improve together.

JMH may show a function is faster in isolation while the overall application does not improve because the bottleneck lies in network, locks, database, or another part of the code. Always verify again on a realistic workload.

## 21. Identify types of CPU bottlenecks

| Symptom | Possibilities to check |
|---|---|
| High process CPU, many `ExecutionSample` events in one method | Hot loop or CPU-intensive algorithm |
| One thread near 100% of one core, other cores idle | Sequential processing path or a single lock/worker limiting parallelism |
| Multiple threads using CPU without throughput increasing | Contention, cache pressure, oversubscription, or synchronization |
| High CPU in GC threads | Allocation rate, heap pressure, or GC work |
| High CPU in JIT compiler threads | Warmup, compilation storm, or many new classes/methods |
| Low CPU but high latency | I/O, network, database, locks, queues, or scheduler wait |
| High machine-wide CPU but low JVM CPU | Another process is consuming CPU |
| CPU increases without request rate increasing | Repeated work, retries, spin loops, or redundant processing |

Do not conclude a CPU bottleneck from a single utilization chart. Combine CPU samples with thread states, GC, I/O events, request rate, and latency to understand the root cause.

## 22. Distinguish CPU-bound from lock/I/O-bound in JFR

If `jdk.CPULoad` is high and threads have many `jdk.ThreadCPULoad` or `jdk.ExecutionSample` events, open Hot Methods and Call Tree to find hot code paths.

If threads are rarely sampled yet requests are still slow, inspect these events:

- `jdk.SocketRead` and `jdk.SocketWrite`.
- `jdk.FileRead` and `jdk.FileWrite`.
- `jdk.JavaMonitorEnter` and `jdk.JavaMonitorWait`.
- `jdk.ThreadPark` and `jdk.ThreadSleep`.
- GC pauses and allocation-related events.

Many duration-based events are only recorded by default when they exceed a threshold. Short events may not appear in the recording. You can lower thresholds to investigate, but lower thresholds produce more events and can increase overhead. Keep recordings short, monitor impact, and enable only the events you need.

## 23. A repeatable CPU measurement workflow

Before measuring:

- Choose a representative workload and document inputs, concurrency, and request rate.
- Use the same JDK vendor/version, JVM flags, heap, OS image, and dependencies.
- Warm up the application so the JIT reaches a near-stable state if steady-state is the goal.
- Avoid running other heavy benchmarks on the same machine.
- Record the number of processors visible to the JVM and any container CPU limits.
- Run multiple times to assess variance.

During measurement:

- Record wall time, process CPU time, throughput, and latency.
- Use a short JFR profile to find hot methods.
- Record timestamps, PID, JDK, build ID, and profile settings.
- Do not enable heap statistics or unrelated detailed events during latency-sensitive measurements.

After optimizing:

- Repeat the same workload and conditions.
- Compare CPU time/operation, throughput, and latency percentiles.
- Check memory allocation, GC, and lock contention to spot trade-offs.
- Keep JFR files and benchmark results along with metadata so others can reproduce them.

## 24. Common CPU measurement mistakes

### Treating wall time as CPU time

A thread that sleeps or waits on network still increases wall time. Use `ThreadMXBean` or process CPU time to measure CPU.

### Assuming 100% means the whole machine in every tool

Some tools display 100% for one logical CPU; others normalize to the whole machine. Identify the denominator before comparing.

### Measuring once and drawing conclusions

CPU load fluctuates with the scheduler, JIT, GC, and background processes. Repeat under an equivalent workload and look at trends.

### Benchmarking a method with a hand-written loop

The JIT may optimize away or eliminate the computation. Use JMH with warmup, measurement, forks, and consumed outputs.

### Looking only at methods with high call counts

High call counts do not equate to high CPU time. A method called many times that is very fast may not be a hotspot. Use samples and call trees to identify CPU-consuming branches.

### Using a CPU profile to diagnose wait time

CPU profiles typically only sample running threads. Use a wall-clock profile or JFR I/O/lock/park events to investigate wait time.

### Adding threads to fix a CPU bottleneck

Adding threads can increase throughput when parallelism is available, but it can also increase context switches, contention, and CPU saturation. Remeasure after every change.

### Ignoring GC and JIT

GC and compiler threads also consume process CPU. Check JFR events to separate application CPU from runtime overhead.

## 25. Troubleshooting invalid measurements

**CPU time returns `-1`:** check whether the JVM supports measurement, whether thread CPU time is enabled, whether the thread is still alive, and whether the API is being called on a platform thread or a virtual thread.

**Process CPU time returns `-1`:** the platform does not support `getProcessCpuTime()`. Use OS process metrics or JFR.

**CPU percentage exceeds 100%:** the tool may be using the 100%-per-logical-CPU convention. Convert to percentage of total capacity by dividing by the processor count using the same denominator.

**JFR has no `jdk.ExecutionSample`:** check the template, recording duration, whether the workload is actually CPU-bound, and event settings. Use `profile` for intentional short recordings; `default` is better suited for continuous recording.

**JFR has too few samples:** increase recording duration or run a representative workload for longer. Do not infer hot methods from a handful of samples.

**Machine-wide CPU is high while JVM CPU is low:** use Task Manager, `top`, or an OS process monitor to find the other process.

**CPU is low while requests are slow:** check socket/file I/O, monitor waits, thread parks, databases, and external services.

**JMH results fluctuate:** check warmup/forks, background load, thermal throttling, power mode, JDK version, GC, and inputs. Only increase iterations when you need more data; first eliminate causes of environmental instability.

## 26. CPU measurement checklist

- [ ] Identified whether you need to measure process, thread, method, benchmark, or whole machine.
- [ ] Distinguished CPU time from wall-clock time.
- [ ] Documented the CPU percentage convention and processor count used as the denominator.
- [ ] Used `System.nanoTime()` for elapsed time.
- [ ] Checked `ThreadMXBean` support and enabled status.
- [ ] Checked for the platform extension before using `getProcessCpuTime()`.
- [ ] Used JFR or a sampling profiler to find hot methods.
- [ ] Used JMH for microbenchmarks instead of hand-written `nanoTime()` loops.
- [ ] Warmed up the JVM and kept the workload representative.
- [ ] Considered GC, JIT, locks, and I/O when explaining CPU usage.
- [ ] Repeated measurements and recorded metadata.
- [ ] Re-verified end-to-end after optimizing.
- [ ] Did not treat sample counts as absolute CPU time.
- [ ] Did not share recordings containing internal details or sensitive data without authorization.

## 27. References

- Oracle Java SE 24 — `ThreadMXBean`: https://docs.oracle.com/en/java/javase/24/docs/api/java.management/java/lang/management/ThreadMXBean.html
- Oracle Java SE 24 — `com.sun.management.OperatingSystemMXBean`: https://docs.oracle.com/en/java/javase/24/docs/api/jdk.management/com/sun/management/OperatingSystemMXBean.html
- Oracle JDK 24 — Troubleshoot Performance Issues Using Flight Recorder: https://docs.oracle.com/en/java/javase/24/troubleshoot/troubleshoot-performance-issues-using-jfr.html
- Oracle JDK 24 — Diagnostic Tools: https://docs.oracle.com/en/java/javase/24/troubleshoot/diagnostic-tools.html
- OpenJDK — Java Microbenchmark Harness (JMH): https://github.com/openjdk/jmh
- OpenJDK — JMH project: https://openjdk.org/projects/code-tools/jmh/
- async-profiler — Getting Started: https://github.com/async-profiler/async-profiler/blob/master/docs/GettingStarted.md
- async-profiler — Profiling Modes: https://github.com/async-profiler/async-profiler/blob/master/docs/ProfilingModes.md
- Linux `perf` documentation: https://perf.wiki.kernel.org/

Measuring CPU is meaningful when you tie the metric to the question. CPU time tells you how long a process or thread has run; CPU utilization tells you the rate of CPU usage over an interval; JFR and profilers find hot methods; JMH compares operations in a controlled environment. Combine these measurements with throughput, latency, GC, locks, and I/O to pinpoint the true bottleneck before optimizing.