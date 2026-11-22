# Sampling Profiling in Java

Sampling profiling is a way of observing a program by periodically capturing stack traces of its threads. Each sample shows which method a thread was executing at the moment the sample was taken. When enough samples are collected under a representative workload, the frequency with which a method appears helps estimate where the JVM spends the most CPU time.

Java Flight Recorder (JFR) is built into the JDK and can be analyzed with JDK Mission Control (JMC). When additional modes such as CPU, wall-clock, allocation, or lock profiling are needed, async-profiler is a popular third-party option. The two tools use different collection mechanisms; choose based on the type of question you need to answer.

## 1. How Does a Sampling Profiler Work?

A sampling profiler periodically requests or collects stack traces of running threads. For example, with a 10 ms sampling period over a 10-second window, a continuously running thread can be sampled approximately 1,000 times. Each sample contains the stack trace at that point in time.

If the `calculatePrice()` method appears in 400 out of 1,000 samples for a thread, the initial estimate is that roughly 40% of that thread's CPU time was spent in that method or in frames attributed to it. This is a statistical estimate, not an exact measurement of invocation counts or absolute method execution time.

### 1.1. Sampling vs. Instrumentation

| Measurement approach | Mechanism | Strengths | Limitations |
|---|---|---|---|
| Sampling | Captures stacks periodically | Typically low overhead, suitable for finding hotspots in running applications | Subject to statistical error; very short or rare methods may not appear |
| Instrumentation | Inserts probes into methods/events and records every occurrence | Can count invocations or measure each call | Probes add overhead; can alter program behavior and timing |
| Benchmark | Runs a controlled workload to measure time/throughput | Compares code versions under reproducible conditions | Does not replace profiling an application under real load |

Sampling is suited for finding where to optimize first. After identifying a hotspot, use a controlled benchmark to measure whether a change actually improves results.

### 1.2. From Sample Counts to CPU Estimates

Suppose a profiler records 2,000 CPU samples:

| Method/stack group | Samples | Sample share |
|---|---:|---:|
| `parseRequest()` | 900 | 45% |
| `calculateTax()` | 700 | 35% |
| `formatResponse()` | 300 | 15% |
| Other methods | 100 | 5% |

The sample share approximates the CPU time share of the stacks within the profiling window, provided the collected samples are sufficiently representative. Do not interpret 45% as meaning `parseRequest()` is called in 45% of requests or accounts for 45% of request latency.

If a method appears in many stack traces, it may be a parent frame for multiple call paths. When reading Hot Methods, Call Tree, or a flame graph, clarify whether you are looking at top frames, self time, or inclusive time.

### 1.3. Error Margin and Sample Size

The fewer samples you have, the more the estimate fluctuates. For a sample proportion `p` and `n` independent samples, the approximate standard error is:

\[
SE \approx \sqrt{\frac{p(1-p)}{n}}
\]

For example, if `p = 0.4` and `n = 400`, the standard error is about 2.45 percentage points. The rough 95% interval is around ±4.8 percentage points around the observed proportion. This is statistical intuition; real-world samples can be correlated due to periodicity, load, and the scheduler, so do not treat this formula as an exact guarantee.

A method appearing in 2 out of 20 samples is not enough evidence to conclude it is a hotspot. Increase the recording duration, collect more samples, and repeat under a similar workload.

## 2. CPU Sampling and Other Profiling Modes

Before choosing a profiler, identify what you need to know:

| Question | Suitable mode | Data to inspect |
|---|---|---|
| Which Java/native code is consuming CPU? | CPU sampling | Stacks of running threads, Hot Methods, Call Tree |
| Where are threads spending time, including waiting? | Wall-clock sampling | Stacks of threads in running, sleeping, or blocked states |
| Which code creates many objects/heap pressure? | Allocation profiling | Call sites and allocation volume |
| Which locks are threads waiting on and for how long? | Lock contention profiling | Locks/monitors, waiting threads, stack sites |
| Are threads blocked by I/O or GC? | Wall-clock + JFR duration events | Socket/file I/O, monitor wait, park, GC pauses |

### 2.1. CPU Sampling

CPU sampling captures a thread's stack while the thread is executing. JFR uses the `jdk.ExecutionSample` event for Java method sampling and `jdk.NativeMethodSample` for native method sampling. Threads that are sleeping, waiting on I/O, or blocked are not targeted by execution sampling while they are not running.

Therefore, a CPU profile answers the question "What is the CPU doing?" It does not by itself explain the full duration of a slow request. If a request takes 900 ms but the thread only runs on the CPU for 80 ms, investigate the wait time using a wall-clock profile, JFR duration events, tracing, or dependency metrics.

### 2.2. Wall-Clock Sampling

Wall-clock sampling samples based on elapsed real time and can observe threads in running, sleeping, or blocked states. It helps find where threads spend time, even when they are not consuming CPU.

Async-profiler supports wall-clock mode via `-e wall`. When viewing a wall-clock profile, a thread waiting on a queue or I/O may show many samples in the waiting stack. A worker sleeping because there is no work is not automatically a bottleneck; determine whether the thread is on the request's critical path.

### 2.3. Allocation and Lock Profiling

Allocation profiling finds call sites that create many objects or generate heap pressure. An application with an unremarkable CPU profile can still be slow due to a high allocation rate causing frequent GC.

Lock profiling finds lock wait events. JFR can record events such as `jdk.JavaMonitorEnter` and `jdk.ThreadPark`; async-profiler has a lock mode to aggregate lock wait time. Use this data to identify waiting threads, contended locks, and the stack sites holding locks.

Allocation and lock modes have different semantics, sampling mechanisms, and overhead than CPU sampling. Do not directly compare percentages between two different profile types as if they were the same quantity.

## 3. JFR Method Sampling in the JDK

JFR is the built-in performance event recorder in the HotSpot JDK. You can enable a recording at JVM startup or attach to a running JVM with `jcmd`.

Two built-in templates are available:

- `default.jfc`: collects a baseline dataset with low overhead, suitable for continuous recording.
- `profile.jfc`: collects more detailed information for short-term investigation; overhead and recording size may be higher.

Templates and event settings vary by JDK/vendor. Check the `JAVA_HOME/lib/jfr/default.jfc` or `profile.jfc` file of the actual runtime before assuming a sample period.

### 3.1. Checking the Sample Period in a Template

Open `JAVA_HOME/lib/jfr/profile.jfc` and look for the `jdk.ExecutionSample` event:

~~~xml
<event name="jdk.ExecutionSample">
  <setting name="enabled">true</setting>
  <setting name="period">10 ms</setting>
</event>
~~~

The snippet above illustrates how a template can configure the period. The actual value depends on the JDK version. On the tested JDK 24.0.2 Zulu, `profile.jfc` sets `jdk.ExecutionSample` to 10 ms and `default.jfc` to 20 ms. These are values for that runtime, not mandatory constants across all JDK releases.

### 3.2. Starting a Recording on a Running JVM

Find the PID:

~~~bash
jcmd -l
~~~

Start a 30-second recording:

~~~bash
jcmd 12345 JFR.start name=cpu-profile settings=profile duration=30s filename=cpu-profile.jfr
~~~

Replace `12345` with the actual PID. Check the status:

~~~bash
jcmd 12345 JFR.check name=cpu-profile verbose=true
~~~

Once the recording finishes, view the summary:

~~~bash
jfr summary cpu-profile.jfr
~~~

Print execution samples:

~~~bash
jfr print --events jdk.ExecutionSample --stack-depth 32 cpu-profile.jfr
~~~

`jdk.ExecutionSample` typically records only threads executing Java code at the time of sampling. `jdk.NativeMethodSample` provides samples in native methods if the template enables that event.

### 3.3. Changing the Sampling Period

You can override an event's period for a recording without modifying the original template:

~~~bash
jcmd 12345 JFR.start name=cpu-5ms settings=profile duration=30s filename=cpu-5ms.jfr jdk.ExecutionSample#period=5ms
~~~

The command above requests a 5 ms period for `jdk.ExecutionSample`. The actual sample count may differ from expectations because threads do not run continuously, as well as due to scheduling, runtime behavior, and sampling mechanism limits. Lowering the period increases the number of samples, the recording size, and potentially the overhead.

Create a custom `.jfc` file if you need to reuse the configuration:

~~~bash
jfr configure --input "$JAVA_HOME/lib/jfr/profile.jfc" --output cpu-sampling.jfc jdk.ExecutionSample#period=5ms
~~~

Then use that file:

~~~bash
jcmd 12345 JFR.start name=cpu-profile settings=/path/to/cpu-sampling.jfc duration=30s filename=cpu-profile.jfr
~~~

Check the exact syntax for your runtime:

~~~bash
jcmd 12345 help JFR.start
jfr help configure
~~~

### 3.4. Continuous Recording and Short-Term Profiling

A lightweight recording can run continuously:

~~~bash
jcmd 12345 JFR.start name=continuous settings=default disk=true maxage=1h maxsize=512m
~~~

When a spike occurs, dump the most recent window:

~~~bash
jcmd 12345 JFR.dump name=continuous filename=incident.jfr maxage=10m
~~~

Continuous recording with `default.jfc` is suitable for preserving context before an incident. When more stack samples and detailed events are needed, create a short `profile` recording during a window with a representative load.

Do not run multiple dense `profile` recordings without measuring overhead. `jcmd` reports JFR's impact level depending on configuration; check the JFR help on the exact JVM you are using.

## 4. Reading a CPU Profile with JDK Mission Control

Open the `.jfr` file in JDK Mission Control (JMC). Useful areas typically include:

1. **Automated Analysis:** initial warnings and areas to inspect.
2. **Code → Hot Methods:** methods that appear most frequently in execution samples.
3. **Code → Call Tree:** view hot methods in caller/callee relationships.
4. **Threads:** see which threads are running and their stacks.
5. **Method Profiling / Execution Samples:** filter samples by time, thread, and stack.
6. **Flame Graph:** view aggregated stacks by depth; width represents sample weight.

### 4.1. Hot Methods and Call Tree

Hot Methods helps find methods with many samples. Call Tree helps answer where those methods are called from. For example, `parseJson()` may have many samples because one endpoint calls it very frequently, or because a single call processes an overly large payload.

Do not just optimize the method at the top of the table. Check callers, workload, input size, and self time. A method that appears frequently on the stack but is only a parent frame may simply be aggregating the time of its child methods.

### 4.2. Flame Graph

A flame graph represents merged stack traces:

- The horizontal axis represents the sample weight of the stacks.
- The vertical axis represents call depth.
- Wider blocks indicate more samples.
- Narrower blocks indicate fewer samples.

Read from the root frame up to the leaf frames to understand the call path. A wide block for a method shows that many samples pass through that method; it does not mean the method always runs continuously or was called a fixed number of times.

JMC and other tools name their views differently across versions. If you do not see a Flame Graph view, use Hot Methods and Call Tree or export the profile to a tool that supports flame graphs.

## 5. Sampling with async-profiler

Async-profiler is a third-party sampling profiler for the HotSpot JVM. It supports CPU, wall-clock, allocation, lock contention, native memory, and various hardware/software performance events. It can collect Java, native, and kernel frames depending on the platform and configuration.

You must install the correct async-profiler build for your OS, CPU architecture, and JVM. The `asprof` commands below assume the profiler is installed and on `PATH`; syntax and capabilities may vary between versions.

### 5.1. CPU Profile

~~~bash
asprof -e cpu -d 30 -f cpu.html 12345
~~~

Captures CPU stacks for 30 seconds and writes a flame graph to `cpu.html`.

### 5.2. Wall-Clock Profile

~~~bash
asprof -e wall -t -i 50ms -d 30 -f wall.html 12345
~~~

Samples all threads by wall clock every 50 ms for 30 seconds. `-t` splits the profile by thread. Use this when you want to see where threads spend time, including sleeping or blocked states.

### 5.3. Allocation Profile

~~~bash
asprof -e alloc --alloc 500k -d 30 -f allocation.html 12345
~~~

`--alloc 500k` sets the average allocation sampling interval by allocated bytes. The profile shows call sites generating allocation pressure. This is not an exact constructor call count; supported intervals and allocation types depend on the JVM and profiler version.

### 5.4. Lock Profile

~~~bash
asprof -e lock --lock 5ms -d 30 -f locks.html 12345
~~~

Lock mode helps find lock contention wait times and the associated stack sites. The `5ms` threshold filters out waits shorter than the configured threshold; check the documentation for your profiler version before using specific options.

### 5.5. Exporting JFR and Multiple Events

Async-profiler can also output JFR files:

~~~bash
asprof -e cpu -f cpu-profile.jfr 12345
~~~

You can combine CPU, allocation, and lock events into a single JFR file if your profiler version supports multi-event profiling:

~~~bash
asprof -e cpu,alloc,lock -f combined-profile.jfr 12345
~~~

Some multi-event outputs only support JFR. Check `asprof --help` and the `ProfilerOptions.md` documentation for your exact release.

### 5.6. OS Permissions and Container Environments

CPU profiling using hardware performance counters on Linux may require `perf_event` permissions or appropriate kernel configuration. In containers, counter access may be restricted by the host, seccomp, or capabilities. Async-profiler has different mechanisms and options depending on the platform; read the container installation/profiling guide before changing system permissions.

Do not grant broad root privileges just to try out a profiler. Determine the minimum required permissions on the host and test in a staging environment.

## 6. Understanding Sampling Interval and Overhead

The sampling interval determines how often the profiler collects stacks. Choosing an interval is a trade-off:

| Interval | Characteristics | When to use |
|---|---|---|
| 1–5 ms | More samples, finer detail, higher overhead and data volume | Short investigations needing to distinguish closely spaced hotspots |
| 10–20 ms | Balanced level commonly used in many templates | General-purpose profiling |
| 50–100 ms | Fewer samples, lower overhead/size | Long observations or low-variance workloads |

These are reference ranges, not rules for every profiler. Check the default period, limits, and overhead of the specific tool. For short workloads or very fast methods, a long interval may miss the method.

### 6.1. Sample Period Is Not Method Runtime

If samples are 10 ms apart and a stack shows `calculate()` running, it does not mean `calculate()` ran for exactly 10 ms. A sample only records state at a single point in time. Many samples falling into the same method indicate that the method accounts for a significant portion of execution time within the measurement window.

Similarly, a method not appearing does not prove it did not run. The method may be too short, rare, missed by sampling, or JIT-inlined into its caller.

### 6.2. Safepoint Bias and Sampling Bias

Some traditional profilers collect stacks primarily at safepoints. If code frequently hits safepoints while other code rarely does, the profile can be skewed toward locations that are easier to sample.

Async-profiler is designed to reduce safepoint bias by combining `perf_events` with `AsyncGetCallTrace` on HotSpot. Even so, every profiler has limitations: native frames, JIT-inlined frames, platform, and configuration can affect the captured stacks. Understand the tool's mechanism rather than treating a flame graph as an absolute map of every CPU instruction.

### 6.3. Aliasing with Periodic Workloads

If a workload repeats on an exact period and the sampler also samples on a similar period, samples may land on the same phase and miss the rest. To reduce this risk:

- Record long enough to cover many cycles.
- Run multiple recordings at different times.
- Use a workload with cadence and data close to production.
- Cross-check with metrics, traces, and other profile modes.

Do not blindly increase sampling frequency without limit to fix error; that can add heavy overhead and alter the workload being measured.

### 6.4. Stack Depth and JIT Inlining

Stacks that are too shallow can miss important callers. Stacks that are too deep produce large files and hard-to-read tables. Use `--stack-depth` in `jfr print` or `-j` in async-profiler when needed.

The JIT compiler can inline methods, so a source method does not necessarily appear as a separate frame in every sample. Use symbol/debug information and the profiler's inline-frame display options when needed; do not disable the JIT just to get prettier stacks if your goal is to measure production performance.

## 7. A Reliable Profiling Workflow

1. Define the question: CPU hotspot, wall-clock wait, allocation, or lock contention.
2. Select the right JVM/PID and verify JDK, GC, CPU, OS, and profiler versions.
3. Define a representative workload, request rate, concurrency, dataset, and measurement window.
4. Warm up the JVM if measuring steady state so class loading and JIT compilation do not dominate the results.
5. Start with a moderate interval and a duration long enough to gather many samples.
6. Capture a baseline under the same workload before modifying code.
7. Read Hot Methods/Call Tree/flame graph; check self time, inclusive time, callers, and threads.
8. If CPU is low but requests are slow, switch to wall-clock, lock, I/O, and distributed tracing.
9. Change one evidence-backed cause; rerun the same workload and compare.
10. Repeat recordings if differences are small or results are unstable.

### 7.1. Controlling Measurement Conditions

To compare two versions:

- Use the same JDK/vendor, JVM flags, and GC.
- Use the same CPU/machine or explicitly document environmental differences.
- Use the same dataset, request mix, concurrency, and warm-up duration.
- Measure multiple times and compare both throughput and p50/p95/p99.
- Do not run other benchmarks concurrently on the same host if they introduce CPU noise.
- Save the JFR/profile files, command lines, and version info for reproducibility.

A sampling profile shows where CPU is consumed; benchmarks and metrics tell you whether a change actually improved user-facing performance.

## 8. Java 17+ Hands-On: Creating Two Hot Paths to Profile

This example creates two CPU-bound threads with two different computation methods and one sleeping thread. The goal is to generate recognizable stack samples; actual method percentages vary by CPU, JIT, and thread scheduling.

Create `ProfilingSamplingFixture.java`:

~~~java
public final class ProfilingSamplingFixture {
    private static volatile long blackhole;

    public static void main(String[] args) throws Exception {
        Thread hotA = new Thread(() -> {
            long value = 1;
            while (!Thread.currentThread().isInterrupted()) {
                value = hotPathA(value);
                blackhole = value;
            }
        }, "fixture-hot-a");

        Thread hotB = new Thread(() -> {
            long value = 2;
            while (!Thread.currentThread().isInterrupted()) {
                value = hotPathB(value);
                blackhole ^= value;
            }
        }, "fixture-hot-b");

        Thread waiter = new Thread(() -> {
            while (!Thread.currentThread().isInterrupted()) {
                try {
                    Thread.sleep(40);
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                }
            }
        }, "fixture-waiter");

        hotA.setDaemon(true);
        hotB.setDaemon(true);
        waiter.setDaemon(true);
        hotA.start();
        hotB.start();
        waiter.start();

        System.out.println("ProfilingSamplingFixture ready");
        new java.util.concurrent.CountDownLatch(1).await();
    }

    private static long hotPathA(long x) {
        for (int i = 0; i < 1200; i++) {
            x = (x * 1664525L + 1013904223L) ^ (x >>> 13);
        }
        return x;
    }

    private static long hotPathB(long x) {
        for (int i = 0; i < 300; i++) {
            x = Long.rotateLeft(x + i * 31L, 7)
                * 0x9E3779B97F4A7C15L;
        }
        return x;
    }
}
~~~

Compile and run in the first terminal:

~~~bash
javac --release 17 -d out ProfilingSamplingFixture.java
java -cp out ProfilingSamplingFixture
~~~

Exact stdout:

~~~text
ProfilingSamplingFixture ready
~~~

In a second terminal, find the PID:

~~~bash
jcmd -l
~~~

Record a 5-second profile with a 5 ms sample period:

~~~bash
jcmd 12345 JFR.start name=sample-5ms settings=profile duration=5s filename=sample-5ms.jfr jdk.ExecutionSample#period=5ms
~~~

After the recording finishes, view event counts:

~~~bash
jfr summary sample-5ms.jfr
~~~

View the most sampled methods:

~~~bash
jfr view hot-methods sample-5ms.jfr
~~~

Print sample stacks:

~~~bash
jfr print --events jdk.ExecutionSample --stack-depth 16 sample-5ms.jfr
~~~

In a test run of the fixture on JDK 24.0.2, a 5-second recording had 1,738 `jdk.ExecutionSample` events and 48 `jdk.NativeMethodSample` events. The Hot Methods view placed the fixture's two hot code paths at the top. Exact counts and percentages vary across machines and runs; what matters is that samples include thread names, `STATE_RUNNABLE` state, and stack traces pointing to the running code.

Some methods may be JIT-inlined, so the method names appearing in Hot Methods can differ between runs. Do not use the percentages from this test run as a fixed threshold for other machines.

## 9. Choosing a Tool by Goal

| Tool | Built into JDK? | Best suited for |
|---|---|---|
| JFR + JMC | Included in modern HotSpot JDKs; JMC may require separate installation | CPU samples, GC, locks, I/O, allocations, and timeline events |
| `jfr` CLI | Included in JDK | Summaries, event filtering, and hot-method views if supported by the version |
| async-profiler | Third-party | CPU, wall-clock, allocation, lock, native/kernel stacks, and flame graphs |
| JMH | Benchmarking library | Method microbenchmarking under controlled conditions |
| APM/distributed tracing | Application platform | End-to-end latency, dependencies, and request paths |

No single profile answers every question. Use CPU sampling to find hot code; wall-clock and duration events to find waiting; allocation/lock profiles for specific pressure sources; and APM to connect request steps.

## 10. Common Issues and Troubleshooting

| Symptom | Possible cause | Resolution |
|---|---|---|
| No `jdk.ExecutionSample` seen | Template disabled method sampling or recording too short | Check `profile.jfc`, `JFR.check`, and `jfr summary` |
| Sample count too low | Long interval, short duration, or low-CPU workload | Extend recording duration and verify workload is running |
| Hot Methods vary widely between runs | Unstable workload, too few samples, or JIT still warming up | Standardize warm-up, increase duration, and repeat |
| Waiting threads missing from CPU profile | ExecutionSample only samples running threads | Use wall-clock profile, JFR lock/I/O events, or thread timeline |
| Short methods do not appear | Method missed by sampling or inlined | Collect more samples, inspect callers, and use other profiles if needed |
| Flame graph has many native frames | Native library/JVM consuming CPU or missing symbols | Inspect native stacks and install appropriate debug symbols |
| JFR file too large | Low interval, long recording, or too many events enabled | Increase interval, cap duration/maxsize, and enable only needed events |
| Profiling reduces throughput | Detailed template, overly frequent sampling, or multiple profilers running | Use `default` for continuous, short `profile` runs, and measure overhead |
| `asprof` fails to attach | Wrong architecture/JVM, missing OS permissions, or container restrictions | Check profiler build, `perf_event` permissions, and attach logs |
| `hot-methods` view not available | JDK release does not provide that view | Run `jfr help view`, use `jfr print`, or open in JMC |

## 11. Pre-Conclusion Checklist

- [ ] Identified the question to answer: CPU, wall-clock, allocation, or lock.
- [ ] Verified the correct PID, JVM, JDK/vendor, and profiler version.
- [ ] Representative workload with appropriate warm-up.
- [ ] Recording is long enough and has enough samples to interpret.
- [ ] Verified the actual period in the template or recording command.
- [ ] Did not confuse sample percentage with invocation count or request latency.
- [ ] Inspected callers, callees, self time, and inclusive time.
- [ ] Checked for JIT inlining and native frames where needed.
- [ ] Used wall-clock/lock/I/O profiles if the CPU profile does not explain latency.
- [ ] Compared against a baseline under equivalent conditions.
- [ ] Measured throughput and latency after making changes.
- [ ] Assessed overhead and sanitized profile/JFR files before sharing.

## 12. Key Takeaways

Sampling profiling captures stack traces periodically to estimate where a program spends time. CPU sampling focuses on running threads; wall-clock sampling also observes sleeping or waiting threads. Sample percentages are statistical estimates, not exact method invocation counts or request durations.

Start with a short JFR `profile` recording, inspect `jdk.ExecutionSample`, Hot Methods, and Call Tree in JMC. Adjust `jdk.ExecutionSample#period` when more samples are needed and monitor overhead. Use async-profiler when you need wall-clock, allocation, lock, or native profiling. Finally, validate hotspots with a reproducible workload or benchmark and re-measure latency/throughput before concluding an improvement.

References:

- [Java Flight Recorder package — Settings and configuration (Java SE 21)](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/package-summary.html)
- [Troubleshoot Performance Issues Using Flight Recorder — Java SE 24](https://docs.oracle.com/en/java/javase/24/troubleshoot/troubleshoot-performance-issues-using-jfr.html)
- [Diagnostic Tools — Java SE 24](https://docs.oracle.com/en/java/javase/24/troubleshoot/diagnostic-tools.html)
- [JDK Mission Control — Using JDK Flight Recorder](https://docs.oracle.com/en/java/java-components/jdk-mission-control/9/user-guide/using-jdk-flight-recorder.html)
- [async-profiler — Profiling Modes](https://github.com/async-profiler/async-profiler/blob/master/docs/ProfilingModes.md)
- [async-profiler — Profiler Options](https://github.com/async-profiler/async-profiler/blob/master/docs/ProfilerOptions.md)
- [async-profiler — Project and Downloads](https://github.com/async-profiler/async-profiler)