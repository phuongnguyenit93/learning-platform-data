# Avoiding False Conclusions in Java Performance Analysis

## Objectives

After this lesson, you will be able to define the right question to measure; distinguish between latency, throughput, CPU time, wall-clock time, allocation rate, and GC time; control the effects of JIT warm-up, caches, workload, concurrency, and environment; avoid microbenchmark pitfalls such as dead-code elimination, constant folding, and loop optimization; use JMH properly; read GC, heap, CPU, and JFR metrics without over-interpreting them; recognize profiler overhead, sampling bias, and cumulative counters; compare repeatable results; and validate hypotheses before changing code or JVM configuration.

## 1. Why Is It Easy to Draw Wrong Conclusions About Performance?

A single metric only describes one aspect of system behavior at a point in time or over a measurement window. It does not explain the root cause on its own.

For example:

- High CPU usage does not by itself prove that a specific method is the bottleneck.
- 85% heap usage does not by itself prove there is a memory leak.
- An increasing GC count does not by itself prove the garbage collector is misconfigured.
- A method having many samples in a profiler does not mean it was invoked that exact number of times.
- A single benchmark run that is 12% faster does not prove the new version is always faster.
- A lower average latency does not guarantee that the slowest requests also improved.
- Increasing RSS while the Java heap remains stable is not necessarily a Java heap leak.

A reliable conclusion needs to connect three parts:

1. **Observation:** actual metrics, traces, events, or measurement results.
2. **Hypothesis:** a mechanism that can explain the observation.
3. **Verification:** a measurement or experiment capable of confirming or refuting the hypothesis.

For example, old-generation occupancy increasing after every GC cycle is an observation. A hypothesis might be that long-lived objects are being retained unintentionally. Verification requires comparing the live set after GC across multiple points in time, inspecting the class histogram or heap dump, and tracing references back to GC roots. Looking at a single heap chart is not enough to conclude a leak.

## 2. Define the Exact Question to Measure

Before opening a profiler or changing JVM flags, write the question in a measurable form.

Examples of good questions:

- After which deployment did P95 and P99 latency of the payment endpoint increase?
- Does throughput drop when the number of workers increases from 8 to 16?
- Did the allocation rate per request increase after switching serializers?
- How much time did GC pauses take during the incident window?
- Did JVM CPU time increase, or is the process waiting on the database?
- Does Metaspace or native memory grow over several hours of execution?
- How much does a code change improve throughput under the same workload?

Avoid overly broad questions such as "Is the JVM slow?" or "Is there a GC problem?". Specify:

- **Target:** a method, an endpoint, a JVM, a service, or the entire system.
- **Operation:** request, transaction, batch, message, or benchmark operation.
- **Metric:** latency, throughput, CPU, allocation, pause, error rate, or memory.
- **Measurement window:** before/after deployment, peak hours, a batch cycle, or warm-up period.
- **Conditions:** load, data, thread count, JDK, collector, and runtime configuration.

If you have not defined the question and the metrics to observe, it is very easy to pick a chart that looks unusual and force a cause onto it.

## 3. Compare Under Equivalent Conditions

A comparison is only meaningful when the important conditions are sufficiently similar.

When comparing two application versions or two JVM configurations, record at least:

| Category | Information to Keep Equivalent or Record |
|---|---|
| Runtime | JDK vendor, version, build, JVM flags, garbage collector |
| Hardware | CPU model, core/logical processor count, RAM, NUMA if relevant |
| Operating System | OS/kernel, filesystem, container runtime |
| Resource Limits | CPU quota, memory limit, affinity, cgroup/container limits |
| Application | Commit/build, dependencies, configuration, feature flags |
| Workload | Request mix, payload, dataset, cache state, concurrency |
| Data | Size, distribution, database and cache state |
| Environment | Background processes, network, storage, and downstream services |
| Measurement | Tool version, template, sampling interval, warm-up, measurement duration |

Do not compare results from an idle laptop against a CI machine sharing CPU and conclude that a code change made the program faster.

If conditions cannot be kept completely identical, clearly document the differences and the limits of your conclusion. Change only one significant factor per experiment so you know which factor produced the effect.

### Containers and Shared Resources

A JVM running inside a container can be limited by CPU or memory even when the host still has free resources. CPU throttling, memory limits, noisy neighbors, and other processes competing for CPU can cause results to fluctuate.

When JVM CPU usage is low but latency is high, check whether threads are waiting on locks, I/O, connection pools, or CPU quota. When CPU is high, inspect other processes and overall host CPU utilization as well.

Do not assume that the CPU count visible on the host is the number of CPUs the JVM is allowed to use. Check container limits and affinity settings before interpreting throughput or CPU percentage.

## 4. Distinguish Between Metric Types

Metrics with different units answer different questions.

| Metric | Meaning | Question Answered |
|---|---|---|
| Wall-clock time | Real elapsed time | How long does the user have to wait? |
| CPU time | CPU execution time for a thread/process | How much CPU time did the code consume? |
| Latency | Time to complete a single request/operation | How long does one operation take? |
| Throughput | Number of operations completed per unit of time | How much work does the system process? |
| Allocation rate | Bytes of objects allocated per second | How fast is the JVM creating objects? |
| GC pause | Time the application is stopped by GC pauses | How long does GC interrupt the application? |
| Heap used | Amount of Java heap currently in use | How much heap do objects currently occupy? |
| RSS | Resident memory of the process | How many RAM pages is the process holding? |

A request with 500 ms wall-clock latency that only uses 20 ms of CPU may be spending most of its time waiting on the database, network, locks, or queues. Optimizing a CPU loop in this case will likely not improve latency significantly.

Conversely, high CPU time close to wall-clock time may suggest a CPU-bound task, though a profiler is still needed to find the code path and confirm.

### Latency vs. Throughput

Latency and throughput are related, but they cannot replace each other:

- Latency measures the duration of a single operation.
- Throughput measures the number of operations completed within a time interval.

As concurrency increases, throughput may rise up to a saturation point and then plateau, while latency continues to climb due to queueing, contention, or resource saturation.

A system that processes more requests while P99 spikes sharply can degrade user experience. Inspect throughput alongside P50, P95, P99, and error rate.

### Averages Can Hide Tail Latency

Suppose 99 requests complete in 20 ms and one request takes 2 seconds. The average of the 100 requests is about 39.8 ms. This average figure does not reveal that the slowest request took 2 seconds.

Choose percentiles aligned with your SLOs and ensure a sufficiently large sample size. P99 from a set of only a few dozen requests is unstable; a handful of samples can swing the result dramatically.

When comparing latency, use the same percentile, the same window, the same workload, and the same load generation method. Never compare the average of one run against the P99 of another.

## 5. JIT and Warm-Up: Do Not Mistake Startup for Steady State

Java HotSpot does not necessarily execute every method the same way from the start of the process to the end.

During the initial phase:

- Classes are loaded and initialized.
- The interpreter may execute bytecode before methods are compiled.
- The runtime collects profiles on data types, branches, and call sites.
- The JIT compiler may compile or inline methods once eligible.
- Caches, connection pools, and application state are warmed up.
- Background tasks such as compilation continue running while the application serves work.

Therefore, the timing of the first few requests can differ significantly from steady state.

### When the Goal Is Measuring Steady State

1. Run the application with a representative workload.
2. Wait for class loading, JIT compilation, and caches to stabilize at an appropriate level.
3. Exclude warm-up samples from the main measurement results.
4. Measure over a window long enough to reflect the workload.
5. Repeat across independent processes/forks for microbenchmarks.
6. Record the warm-up duration and iteration count.

### When the Goal Is Measuring Startup

Do not discard warm-up if the actual question is startup time or time from process start to readiness. In that case, separately measure process launch to `main`, `main` to application ready, first request latency, and warm-up to steady-state latency.

Startup performance and steady-state performance are two different goals. Do not use steady-state numbers to claim faster startup.

## 6. Why Hand-Rolled Stopwatches and Loops Are Error-Prone

Measuring a piece of code with `System.nanoTime` inside a simple loop looks easy, but many factors can skew the results:

- The JVM may not have JIT-compiled the method yet.
- The JIT may inline, unroll, or optimize the code differently than expected.
- If the result is unused, the computation may be eliminated.
- Constant inputs may enable constant folding.
- Timer and loop overhead may exceed the work being measured.
- Garbage collection may occur inside or outside the measurement window.
- Thread scheduling, CPU frequency, and background processes introduce noise.
- A single run does not reflect variance distribution.

For example, a benchmark calls a method and discards its return value. If the result is never observed, the compiler can eliminate a computation that has no side effects. The measured time is then not the execution time of the logic you intended to measure.

OpenJDK JMH has dedicated samples for dead-code elimination, constant folding, and loop optimization to demonstrate these pitfalls.

## 7. Using JMH for Microbenchmarks

**Java Microbenchmark Harness (JMH)** is an OpenJDK framework for building, running, and analyzing Java benchmarks. JMH manages warm-up, measurement iterations, forks, state, and result consumption to mitigate many common measurement errors.

JMH is useful when you need to compare an algorithm, data structure, method, or JVM code snippet under controlled conditions.

JMH does not automatically turn a flawed benchmark into a valid one. The author must still choose representative workloads, inputs, state, and measurements. The JMH project recommends creating a separate benchmark project using the Maven archetype and running it from the command line, because running directly inside an IDE has a harder-to-control environment.

### Creating a JMH Project

You need a JDK and Maven. Create a sample project:

~~~bash
mvn archetype:generate -DinteractiveMode=false -DarchetypeGroupId=org.openjdk.jmh -DarchetypeArtifactId=jmh-java-benchmark-archetype -DgroupId=org.sample -DartifactId=performance-lab -Dversion=1.0
~~~

After creating the project, place your benchmark class in the source tree under the corresponding package, then build:

~~~bash
cd performance-lab
mvn clean verify
~~~

Run the generated benchmark jar:

~~~bash
java -jar target/benchmarks.jar
~~~

View available options:

~~~bash
java -jar target/benchmarks.jar -h
~~~

The archetype sets up the required dependencies and annotation/bytecode processing. Simply adding `jmh-core` to a regular project is not enough to create a properly configured benchmark project.

### Example Benchmark with Warm-Up, Measurement, and Fork

Create **ArraySumBenchmark.java** in package **org.sample**:

~~~java
package org.sample;

import java.util.concurrent.TimeUnit;
import org.openjdk.jmh.annotations.Benchmark;
import org.openjdk.jmh.annotations.BenchmarkMode;
import org.openjdk.jmh.annotations.Fork;
import org.openjdk.jmh.annotations.Level;
import org.openjdk.jmh.annotations.Measurement;
import org.openjdk.jmh.annotations.Mode;
import org.openjdk.jmh.annotations.OutputTimeUnit;
import org.openjdk.jmh.annotations.Param;
import org.openjdk.jmh.annotations.Scope;
import org.openjdk.jmh.annotations.Setup;
import org.openjdk.jmh.annotations.State;
import org.openjdk.jmh.annotations.Warmup;

@State(Scope.Thread)
@BenchmarkMode(Mode.AverageTime)
@OutputTimeUnit(TimeUnit.MICROSECONDS)
@Warmup(iterations = 5, time = 1)
@Measurement(iterations = 5, time = 1)
@Fork(3)
public class ArraySumBenchmark {
    @Param({"64", "4096"})
    int size;

    int[] values;

    @Setup(Level.Trial)
    public void setup() {
        values = new int[size];
        for (int i = 0; i < values.length; i++) {
            values[i] = i + 1;
        }
    }

    @Benchmark
    public long sum() {
        long total = 0;
        for (int value : values) {
            total += value;
        }
        return total;
    }
}
~~~

Explanation:

- **@State(Scope.Thread)** creates separate state for each benchmark thread, avoiding unintended array sharing.
- **@Param** runs the benchmark with two input sizes.
- **@Setup(Level.Trial)** prepares data before the iterations of a trial, excluding array creation cost from each operation.
- **@Warmup** runs 5 warm-up iterations, 1 second each.
- **@Measurement** measures 5 iterations, 1 second each.
- **@Fork(3)** runs 3 independent JVM forks.
- **@BenchmarkMode(Mode.AverageTime)** measures average time per operation.
- **@OutputTimeUnit** displays results in microseconds.
- The method returns the result so JMH consumes it, preventing dead-code elimination.

Run the specific benchmark:

~~~bash
java -jar target/benchmarks.jar ArraySumBenchmark
~~~

JMH will print the score, error, and unit for each parameter. Exact values depend on CPU, JDK, OS, workload, and machine state; there is no fixed numeric stdout to use as a universal baseline.

### Reading JMH Results

A typical result table contains these columns:

- Benchmark: name of the benchmark method.
- Mode: measurement mode such as throughput or average time.
- Cnt: number of measurement samples/iterations aggregated in the output.
- Score: measured score.
- Error: uncertainty reported alongside the score.
- Units: measurement unit.

Do not just pick the row with the best Score. Look at Error, number of forks, workload, and consistency across runs. If the difference is small compared to the variance, the data is insufficient to claim one implementation is better.

## 8. Common Microbenchmark Pitfalls

### Dead-Code Elimination

If the result of a computation is unused, the JVM can eliminate that computation.

How to avoid it:

- Return the result from the benchmark method when appropriate.
- Use **Blackhole** to consume results when the benchmark processes multiple values.
- Ensure the measured work actually affects the observed output.

Do not add arbitrary side effects just to stop compiler optimization. New side effects may cause the benchmark to measure a different workload.

### Constant Folding

If the input is always a constant and the computation can be determined ahead of time, the JIT can precompute the result or simplify the computation.

How to avoid it:

- Use runtime inputs from state or parameters.
- Avoid fixed `final` primitives as inputs if the goal is to measure data-dependent computation.
- Check the official JMH sample on constant folding.

Do not turn the benchmark into an artificial workload just to prevent optimization. Inputs should have a distribution close to real data.

### Loop Optimization and Unrolling

Wrapping multiple operations in your own loop to reduce invocation overhead can cause the JIT to unroll, pipeline, or hoist the computation. The cost per operation obtained by dividing total time by the loop count can become unrealistic.

Let JMH invoke the benchmark method via its harness. Loops are still valid when they are an actual part of the algorithm being measured, such as iterating over an array in the `sum` method above; avoid creating artificial loops just to measure a tiny addition.

### Benchmark Overhead and Fixtures

If setup runs on every invocation, setup time can dominate the method being measured. If setup only needs to run once per trial, use **@Setup(Level.Trial)**. If you need setup per iteration or per invocation, choose the appropriate level and understand whether that cost is included in the measurement.

### Not Using Forks

Running multiple benchmarks in the same JVM allows JIT profiles, class loading, and state from earlier benchmarks to affect later ones. Forking creates separate JVM processes to reduce cross-benchmark interference.

Use multiple forks when you need stable conclusions. Too few forks can make results dependent on a single runtime state.

### Running Benchmarks Directly in an IDE

An IDE can add background tasks, debuggers, plugins, classpaths, and JVM settings that differ from real environments. JMH recommends running benchmarks from the command line in a properly configured project.

## 9. Do Not Confuse Microbenchmarks with Load Tests

A microbenchmark answers questions about a snippet of code or an operation in isolation. It does not fully simulate a service receiving live traffic.

| Test Type | Goal | Appropriate Tool |
|---|---|---|
| Microbenchmark | Compare methods/algorithms/data structures | JMH |
| Component benchmark | Measure a component with controlled dependencies | JMH or a suitable harness |
| Load test | Measure a service under concurrency and request mix | Load test tools like Gatling/k6 or your organization's standard tool |
| Soak test | Observe drift, leaks, and degradation over a long period | Load generator + metrics/JFR |
| Startup test | Measure process launch and readiness | Scripts/harnesses measuring process lifecycle |
| Production profiling | Find bottlenecks on real workloads | JFR/JMC, profilers, metrics, and tracing |

A method that is faster in JMH may not make an endpoint faster if the real bottleneck is the database, network, a different serialization step, a queue, or a lock.

Conversely, a slow load test does not prove an individual method is the cause. Use a profiler or traces to locate the hot code paths in actual requests.

## 10. Reading GC and Heap Metrics Without Over-Interpreting

### High Heap Usage Does Not Automatically Prove a Leak

Heap can grow because workload just increased, caches are warming up, long-lived objects are retained by design, the JVM expanded committed heap, GC has not run yet at the snapshot time, the live set genuinely grew, or objects are being retained unintentionally.

Inspect post-GC heap usage across multiple cycles. If the post-GC live set grows continuously under an equivalent workload, that is a signal to investigate. Next, use a class histogram, heap dump, dominator tree, and paths to GC roots to identify which objects are being retained.

### High GC Count Does Not Automatically Prove a GC Problem

An application creating many short-lived objects can have frequent young GCs while still meeting its latency and throughput targets.

Look at allocation rate, young/old GC frequency, pause time distribution, time spent in GC, heap occupancy before and after GC, promotion, collector and heap configuration, and application latency in the same window.

A collector with many small collections and short pauses can perform better than a collector with fewer collections but long pauses. Do not compare based on GC count alone.

### Cumulative Counters vs. Gauges

Counters such as GC count or total GC time typically accumulate monotonically since JVM startup. To calculate the value within a window, take the difference between two readings:

~~~text
deltaGC = GC_count_after - GC_count_before
deltaGCTime = GC_time_after - GC_time_before
~~~

Gauges such as heap used represent a current snapshot. Do not treat a cumulative counter as a rate or compare two processes with very different uptimes without normalizing.

### Heap, Committed, Reserved, and RSS

These concepts are distinct:

- Heap used: objects currently occupying the Java heap.
- Heap committed: amount of heap memory the JVM has committed and can use.
- Reserved address space: virtual address space reserved by the JVM.
- RSS: resident memory pages of the process in RAM.

RSS can grow due to metaspace, code cache, thread stacks, direct buffers, native libraries, or memory mappings even while heap used stays flat.

If you suspect native memory growth, use Native Memory Tracking (NMT) if enabled at JVM startup, combined with OS tools. NMT only tracks supported internal HotSpot memory categories; it does not cover every allocation from external native code outside the JVM.

## 11. High CPU, Low CPU, and Profiler Samples

### High CPU Does Not Immediately Point to the Faulty Method

High CPU can come from higher request volume, expensive loops or algorithms, serialization/deserialization, regex/parsing, garbage collection, JIT compilation, compression/encryption/hashing, busy waits, retry loops, or excessive logging.

Use JFR or a profiler to inspect threads and stack samples, then verify the code path. Check processes and CPU quotas at the OS/container level.

### Low CPU Does Not Mean the Application Is Healthy

Low CPU with high latency can occur when threads are waiting on a database, remote APIs, network/file I/O, connection pools, thread pool queues, monitors/locks, rate limiters, or downstream timeouts.

In this situation, adding more CPU or optimizing arithmetic will not resolve the wait.

### Sampling Is Not an Exact Invocation Count

A sampling profiler periodically captures thread stacks at specific intervals. A method that appears frequently in samples may be consuming significant time, but sample count is not the exact number of times the method was called.

Interpret samples alongside recording duration, sampling period, thread state, and event type. A method not appearing in samples does not mean it never ran.

JFR has duration events, instant events, sample events, and custom events. Each type describes different activity. A duration event is recorded with start/end timestamps; a sample event is an observation at a point in time or sampling interval. Do not add different event types together as if they share the same unit.

### Profilers Also Have Overhead

JFR is built into the JVM and designed for low overhead. However, templates and event settings vary in detail and impact.

- **default.jfc** is suitable for low-overhead background monitoring.
- **profile.jfc** collects more events and can have a higher impact.
- Method profiling and allocation profiling can generate additional data.
- Low event thresholds or detailed stack traces can increase event volume.

Measure a baseline without profiling, then enable the required profiling configuration and compare. If the target workload is pause-sensitive for latency, avoid enabling event settings that trigger extra work before evaluating their impact.

## 12. Analyzing JFR Within the Proper Scope

JFR records timestamped events and provides visibility into the JVM, application, threads, GC, CPU, allocations, locks, and I/O.

A sensible workflow:

1. Select a recording covering the entire incident or workload.
2. Record the JDK version, template, and event settings.
3. Check Overview and Environment to understand the machine, process, and workload.
4. Identify the time range with abnormal latency or CPU.
5. Inspect GC pauses, allocations, and heap within that same window.
6. Inspect thread/CPU samples and lock contention.
7. Check file/socket I/O if CPU does not explain the latency.
8. Read stack traces and source code for the hotspots.
9. Cross-reference with application metrics, logs, and distributed traces.

Do not pick a prominent chart and ignore the timeline. A method with many samples over a long recording might simply reflect that it runs frequently; verify whether those samples occurred during the slow period.

If a recording uses the default template without allocation profiling enabled, you cannot conclude allocations are low just because few allocation events appear. Before interpreting the absence of an event, confirm the event was enabled with an appropriate threshold/period.

## 13. Be Careful with Concurrency and Load Generation

A single-threaded benchmark does not describe performance when multiple threads access shared state or shared resources concurrently.

As concurrency increases, you may encounter lock contention, queueing and context switching, cache-line contention/false sharing, memory bandwidth saturation, connection pool exhaustion, thread pool saturation, CPU throttling, increased GC pressure from total allocation, and overloaded downstream services.

Measure across multiple concurrency levels and observe both throughput and latency. If throughput stops increasing while P99 rises sharply, the system may be saturated or queues may be backing up.

### Check for False Sharing and Shared State

Threads updating independent fields located close together on the same cache line can interfere with each other. A benchmark using a shared counter or shared state may end up measuring contention instead of the algorithm you intended to compare.

Choose **@State(Scope.Thread)** when each thread needs its own data. Choose shared scope only when sharing state is part of the real workload.

### The Load Generator Can Also Become the Bottleneck

If the load-generating machine runs out of CPU, network, or connections, measured throughput may be capped by the load generator. Monitor resources on both client and server sides.

Ensure virtual users, request rate, think time, and request distribution match the test objective. A load test that fails to generate the target load cannot be used to conclude that the server can handle that load.

## 14. Statistics and Variance: Do Not Cherry-Pick the Best Result

Runtime performance fluctuates due to JIT, GC, CPU frequency, OS scheduler, background processes, network, and workload.

For reliable results:

- Run multiple iterations and multiple forks when using JMH.
- Keep configuration and workload consistent across runs.
- Save raw results rather than copying only a single Score.
- Inspect the score together with error/uncertainty.
- Observe the distribution and outliers; do not arbitrarily delete bad samples.
- Record machine conditions and execution time.
- Re-run when results are inconsistent.
- Evaluate whether the improvement is practically meaningful.

Do not pick the fastest run as the representative result. Do not discard an outlier just because it changes your conclusion; first investigate the cause, such as GC, CPU throttling, or a background task.

### Comparing Improvement Magnitude

Suppose the baseline measures 100 microseconds/op and the new version measures 97 microseconds/op. The nominal difference is 3%. If variance across forks is also around a few percent, there is not enough evidence to claim a 3% improvement.

Look at error/uncertainty, fork count, and repeatability. If the difference is smaller than the noise, improve the measurement design or conclude that no reliable difference has been observed yet.

### Outliers Can Be Signals

A very large latency sample may reflect a GC pause, lock convoy, network retransmission, disk stall, or retry. Do not discard tail latency when the goal is reliability or user experience.

When investigating outliers, preserve timestamps to correlate with JFR, GC logs, distributed traces, and downstream systems.

## 15. Separating Correlation from Causation

Two metrics rising at the same time does not prove one caused the other.

For example:

- CPU and latency rising together may be caused by increased traffic, not necessarily CPU causing latency.
- Heap and request rate rising together may be due to a larger workload.
- GC and error rate rising together may be due to a traffic burst or shared memory pressure.
- A method with a high sample count may simply be the most frequently called code path, not the sole cause of latency.

To test causality:

1. Formulate a hypothesis with a specific mechanism.
2. Identify which metrics should change if the hypothesis is true.
3. Change only one controlled factor.
4. Run the baseline and experiment under equivalent workloads.
5. Repeat and check whether the results are stable.
6. If possible, roll back to see if the metrics return to baseline.
7. Record side effects such as memory, CPU, and error rate.

For example, if you suspect a new serializer increases allocation, measure allocated bytes/request, CPU time/request, and latency under the same payload. Run the same workload with the old and new serializers, then compare. Only when allocation and/or CPU change as predicted across multiple runs do you have a solid basis for a conclusion.

## 16. Common Examples of False Conclusions

### "Heap is at 90%, there must be a memory leak"

A snapshot might have been taken right before GC or while caches were warming up.

What to do: observe post-GC live set across multiple cycles under equivalent load; check allocation rate; if the live set grows continuously, use a histogram/heap dump to find retained objects.

### "GC ran 200 times, the collector is too slow"

GC count is a cumulative counter and depends on uptime, allocation rate, heap size, and collector.

What to do: compute the delta within the same window; inspect pause distribution, total GC time, allocation, and latency; determine which collections affect SLOs.

### "Method A has the most samples, optimizing it will give the biggest speedup"

Sample count can reflect how frequently a method is called, not just the cost per call. The method may also appear on the stack of many callers.

What to do: inspect self/total time, call paths, thread states, and the incident window; verify with targeted benchmarking or profiling.

### "CPU is low, so the JVM is not the bottleneck"

Threads may be waiting on a database, locks, network, or connection pools.

What to do: inspect thread states, I/O events, lock waits, downstream latency, and queue depth.

### "The new version is faster because one run was faster"

A single run may have encountered different JIT warm-up, GC, CPU frequency, or background tasks.

What to do: run multiple forks/iterations, control the environment, and inspect error/uncertainty.

### "Average latency dropped, so user experience is better"

Average can decrease even while P99 increases.

What to do: inspect P50/P95/P99, error rate, and request mix; compare the same window and the same percentile.

### "JFR has no allocation events, so the app is not allocating"

The template or event settings may not have allocation profiling enabled, or the threshold/period may be unsuitable.

What to do: check event settings, template, and recording duration; if needed, run a profiling recording with appropriate configuration.

### "RSS is growing, the Java heap must be leaking"

RSS includes memory outside the Java heap such as native allocations, thread stacks, direct buffers, and mapped files.

What to do: compare heap used/committed against RSS; use NMT if enabled; check direct buffers, thread count, native libraries, and OS metrics.

## 17. A Repeatable Performance Investigation Workflow

### Phase 1: Confirm the Symptom

1. Identify the affected endpoint/job/JVM.
2. Choose metrics reflecting the symptom: P99, throughput, CPU, GC pause, or memory.
3. Determine the start time and occurrence window.
4. Compare against baseline/SLOs and workload.
5. Note deployments, config changes, traffic, and downstream events.

### Phase 2: Gather Evidence

1. Collect application metrics and distributed traces.
2. Check OS/container CPU, memory, disk, network, and throttling.
3. Inspect GC logs and JFR.
4. Inspect thread states, locks, and I/O.
5. Use histograms/heap dumps if there is evidence of memory growth.
6. Record JDK, collector, JVM flags, and tool settings.

### Phase 3: Test Hypotheses

1. Pick one bottleneck backed by evidence.
2. Create a small experiment reproducing the workload.
3. Use JMH for code-level microbenchmarks.
4. Use load/soak tests for service-level behavior.
5. Change only one factor.
6. Repeat and measure the same metrics.
7. Check side effects and error/uncertainty.

### Phase 4: Verify Changes

1. Run regression tests.
2. Run benchmarks/load tests under equivalent conditions.
3. Compare the same percentiles and units.
4. Check CPU, memory, GC, throughput, and error rate.
5. Roll out in a controlled manner if your process allows.
6. Monitor production metrics after the change.
7. Roll back if SLOs or error rates degrade.

## 18. Common Issues and How to Handle Them

### Benchmark runs too fast or yields unrealistic results

**Cause:** dead-code elimination, constant folding, overly simple inputs, or optimized-away loops.

**Resolution:** use JMH; return results or use `Blackhole`; use runtime state/parameters; read JMH samples on dead code, constant folding, and loops.

### Large variance between runs

**Cause:** insufficient warm-up, shared CPU, GC, CPU throttling, thermal state, or mismatched workload or data.

**Resolution:** control the environment; use warm-up and forks; record raw results; monitor OS/JVM metrics; repeat rather than picking the best result.

### Benchmark in IDE differs from command line

**Cause:** different JVM options, classpath, background processes, debuggers, plugins, or annotation processors.

**Resolution:** create a dedicated JMH project using the Maven archetype and run the executable benchmark jar from the command line.

### Throughput increases but latency degrades

**Cause:** higher concurrency causing queueing, lock contention, or downstream saturation.

**Resolution:** inspect throughput alongside P95/P99, error rate, queue depth, thread states, and connection pools; test across multiple concurrency levels.

### GC metrics increase but the application still meets SLOs

**Cause:** high allocation throughput with short, low-impact collections.

**Resolution:** evaluate pause distribution, GC time ratio, throughput, and live set; optimize only when there is real impact.

### High CPU but profiler shows no clear hotspot

**Cause:** recording too short, insufficient sampling, native code, compilation, GC, or another process using CPU.

**Resolution:** extend the window and check JFR event settings; inspect OS process metrics, GC, compiler, and native stacks if needed.

### JFR profile changes the results

**Cause:** templates/event settings collect more detail and introduce overhead.

**Resolution:** measure a baseline; use `default` for background observation; use short targeted `profile` recordings; document settings when comparing.

### RSS memory grows while heap is stable

**Cause:** native memory, thread stacks, direct buffers, code cache, or memory mappings.

**Resolution:** inspect NMT if enabled, direct buffers, thread count, OS memory maps, and native libraries; do not blame the Java heap without evidence.

### Average looks good but users still experience slowness

**Cause:** tail latency, request mix, or slow downstream dependencies.

**Resolution:** measure P95/P99 per endpoint and request segment; correlate with traces, queues, and dependency latency.

### Changing multiple settings at once obscures the cause

**Cause:** changing code, heap, collector, thread pools, and caches simultaneously.

**Resolution:** return to a reproducible baseline; change one factor at a time; record version and configuration for each trial.

## 19. Pre-Conclusion Checklist

### Question and Environment

- [ ] The measurement question is specific and has appropriate metrics.
- [ ] Workload, inputs, concurrency, and measurement window are defined.
- [ ] JDK, JVM flags, collector, and OS are recorded.
- [ ] CPU/memory quotas and background processes have been checked.
- [ ] Data and cache states are equivalent across runs.

### Measurement

- [ ] Wall-clock time, CPU time, latency, and throughput are distinguished.
- [ ] Appropriate percentiles are inspected, not just averages.
- [ ] Warm-up is included if the goal is steady state.
- [ ] JMH is used for JVM microbenchmarks.
- [ ] Dead-code elimination, constant folding, and loop optimization have been checked.
- [ ] Multiple iterations/forks are used where needed.
- [ ] Raw results and uncertainty are preserved.
- [ ] Unexplained outliers are not arbitrarily discarded.

### Metric Interpretation

- [ ] Cumulative counters have been properly converted to deltas/rates.
- [ ] Heap usage is observed across multiple GC cycles.
- [ ] GC count is evaluated alongside pause times and latency.
- [ ] High/low CPU is correlated with thread states and I/O.
- [ ] JFR samples are understood as samples, not exact invocation counts.
- [ ] Templates and event settings have been verified.
- [ ] RSS is distinguished from Java heap.
- [ ] Profiler overhead has been accounted for.

### Conclusions and Changes

- [ ] There is a hypothesis and supporting evidence.
- [ ] There is an experiment capable of refuting the hypothesis.
- [ ] Each experiment changes only the factor under test.
- [ ] Results are repeatable under equivalent conditions.
- [ ] Improvement exceeds noise and is operationally meaningful.
- [ ] Regression tests and post-change monitoring plans are in place.

## 20. Official References

- [Diagnostic Tools — Java SE 26 Troubleshooting Guide](https://docs.oracle.com/en/java/javase/26/troubleshoot/diagnostic-tools.html) — JFR, JMC, `jcmd`, monitoring, event categories, and native memory tracking.
- [OpenJDK Java Microbenchmark Harness (JMH)](https://github.com/openjdk/jmh/) — guide to creating benchmark projects, Maven archetype, command-line usage, and samples.
- [JMH Sample 08: Dead Code](https://github.com/openjdk/jmh/blob/master/jmh-samples/src/main/java/org/openjdk/jmh/samples/JMHSample_08_DeadCode.java) — why computations with unused results can be eliminated.
- [JMH Sample 10: Constant Folding](https://github.com/openjdk/jmh/blob/master/jmh-samples/src/main/java/org/openjdk/jmh/samples/JMHSample_10_ConstantFold.java) — avoiding benchmark inputs that the compiler can precompute.
- [JMH Sample 11: Loops](https://github.com/openjdk/jmh/blob/master/jmh-samples/src/main/java/org/openjdk/jmh/samples/JMHSample_11_Loops.java) — how loop unrolling, pipelining, and hoisting can skew per-operation cost.
- [JMH Sample 35: Profilers](https://github.com/openjdk/jmh/blob/master/jmh-samples/src/main/java/org/openjdk/jmh/samples/JMHSample_35_Profilers.java) — how to use profilers, forks, and hardware counters to understand benchmarks.
- [Avoiding Benchmarking Pitfalls on the JVM — Oracle](https://www.oracle.com/technical-resources/articles/java/architect-benchmarking.html) — JVM benchmarking pitfalls, JIT optimizations, and how JMH helps reduce risk.

Never draw conclusions from a single number or a single chart. Define the right question, control the measurement conditions, understand how the JIT and profiler can affect the data, and cross-reference metrics with workload, timeline, and independent evidence. A performance conclusion should only be used to change code or configuration when the measurement is repeatable and the hypothesis has been verified.
