# 2.7 Identifying Biases from Startup, JIT, GC, Sampling, and the Observer Tool Itself

A performance number does not explain its own cause. The exact same Java method can run slowly on cold startup, faster after JIT optimization, suddenly stall due to GC, or be preempted by the OS scheduler. A profiler can alter behavior; an unsuitable sampling strategy can miss the slowest invocations entirely. In **performance measurement and JVM diagnostics**, the job is not merely collecting numbers, but identifying **which phase, subject, tool, and conditions they represent**.

This lesson focuses on Java 21 and principles applicable across many JVMs. The **jcmd**, **-Xlog**, and certain compiler behaviors described are specific to **JDK 21 on HotSpot**; on other VMs or JDK versions, verify capabilities against the actual process.

## Learning Objectives

After this lesson, you will be able to:
- Distinguish **startup/cold**, **warmup**, and **steady state** when designing measurements.
- Recognize signs of **JIT compilation, tiered compilation, OSR, and deoptimization** that can shift results, while avoiding attributing causes without evidence.
- Analyze the impact of **GC pauses, concurrent GC, allocation, and safepoints** on latency, throughput, and CPU.
- Identify **sampling bias**, periodic sampling synchronized with events, under-sampled p95/p99, and **coordinated omission**.
- Evaluate the **observer effect** caused by logging, profilers, JFR, thread dumps, agents, metric collection, or even timing loops themselves.
- Design a comparison run with baselines, variable controls, repetitions, cross-checking across multiple data sources, and complete metadata retention.

## 1. First: Define Exactly "What Was Measured"

Suppose a result shows a request took **120 ms**. Ask:

- What are the **start/end boundaries**: at the load generator, HTTP gateway, queue, Java method, or database?
- Was **wall-clock elapsed time** or **CPU time** used? **System.nanoTime()** is suited for elapsed intervals within the same process, yet wall time also counts time spent waiting on I/O, waiting on locks, paused for GC, or waiting for OS CPU scheduling.
- Are you measuring **one invocation**, a batch, an end-to-end request, or **response times across all requests**?
- How many measurements were taken? Were any requests dropped, timed out, retried, or excluded from the distribution?
- Were the metrics collected in **cold, warmup, steady state**, or a mix of all three?
- Did the observation happen **before or after enabling** logging, profilers, or diagnostic commands?

A helpful mental model:

**Observed time = application work + waiting time + runtime effects + observation effects + interactions among factors.**

This is **not a strict additive sum**: GC and the application can run concurrently; JIT can alter execution paths; observation tools can shift GC frequency or thread scheduling. To trace root causes, inspect the **timeline** rather than mechanically subtracting counters.

| Metric | Question Answered | Easy to Misunderstand |
| --- | --- | --- |
| **End-to-end latency** | How long the caller waited, including queues/network per measurement point | Equating it with method CPU time. |
| **Throughput** (requests/s, ops/s) | How many units of work completed in a defined time | Assuming higher throughput always means better p99; throughput can rise while tail latency worsens. |
| **CPU time / CPU utilization** | CPU resources consumed within the measured scope | Does not include full wait time; high CPU utilization does not prove the app is compute-bound. |
| **Allocation rate / heap occupancy** | How objects are allocated and memory is occupied | Assuming high heap usage automatically means long GC pauses. |
| **GC count / GC time / pause events** | What work the collector performed, and when | Assuming summing GC time yields exact per-request latency impact. |
| **p50, p95, p99, max** | Tail of the latency distribution | Few samples or averaging p99s misrepresents the underlying distribution. |

In reports, include **units**, **sampling rules**, and **measurement windows**. For instance, "p99 80 ms across 50,000 completed requests over 5 minutes post-warmup" is far more useful than "p99 = 80".

## 2. Startup Bias: Cold Differs from Steady State

### 2.1. Why First Calls Do Not Represent Subsequent Calls

During the early phase of a Java process, several things can occur:
1. JVM initializes runtime structures, class loaders, memory, and system subsystems.
2. Classes are **loaded, verified, linked**, and **initialized** on demand; static initializers in app or library code can do heavy work.
3. Frameworks wire dependencies, configure connections, proxies, and serializers; application or OS caches are still cold.
4. Methods initially execute interpreted or compiled at lower tiers; HotSpot gathers profiles to guide optimizations.
5. JIT compiles and may recompile methods; GC/heap adapts to allocation patterns.
6. After some time, major factors may stabilize relatively, yet there is **no guarantee** the JVM reaches a permanent fixed state.

That is why the same workload can exhibit a slower "**first call**" without a code regression. Conversely, if production requires immediate responsiveness right after deploy or scale-out, **cold-start latency is a real requirement**; never polish results by discarding the start.

### 2.2. Define the Measurement Mode Before Running

**Startup measurement** requires multiple **independent fresh processes** with concrete milestones (e.g., launch to ready, or first request to response). Each run should record cache state, warm filesystem, DNS, connections, concurrent processes, and CPU quota. Restarting a Java process does not necessarily clear the OS filesystem cache; state experimental limitations clearly.

**Steady-state measurement** requires a dedicated warmup with load, data, code paths, thread counts, and configs closely matching the measurement phase. **There is no fixed warmup iteration count** valid for every application. Inspect trends over time and compiler/GC signals to choose the transition point; while throughput, CPU, allocation, or tail latency are still drifting heavily, calling it steady state is premature.

**Phase-transition measurement** (e.g., load ramp-up, first call to a new feature, cache expiration, thread pool resize) must preserve the entire timeline. Mixing warmup and steady state and reporting a single average erases the exact behavior that needs analysis.

### 2.3. Bias from Choosing the Start Point

- Starting the stopwatch **before the first class initializes** includes startup/class initialization; starting after classes are loaded measures a different scope.
- Do not "warm up" only the **success** branch and then measure the **exception** branch; execution paths and branch profiles differ.
- Warming up with small data, empty caches, and few threads and then measuring large data, full caches, and many threads is **not** the same regime.
- Comparing two builds in fixed order A then B can be skewed by caches, CPU thermal throttling, or shifting background load. Repeat, alternate order, and isolate processes to mitigate risk.

## 3. JIT Bias: Java Code Can Change Execution Paths Mid-Measurement

### 3.1. Mechanisms to Understand

In common JDK 21 HotSpot configurations, **tiered compilation** lets the runtime use multiple execution/compilation levels, typically combining the interpreter, C1, and C2 compilers. A method can be compiled once sufficiently "hot"; an active loop can transition into compiled code via **on-stack replacement (OSR)**. Compilation is usually handled by background compiler threads, so measurements can also be affected by CPU consumed by the compiler.

HotSpot can apply **inlining**, **constant folding**, **loop optimization**, or **escape analysis** using runtime profiling info. If optimization assumptions cease to hold, the VM can **deoptimize**, fall back to another tier, and later recompile. This is normal JVM behavior; a single latency uptick does not automatically prove deoptimization occurred.

Common noise sources:

| Phenomenon | Possible Symptom | Evidence Required |
| --- | --- | --- |
| **Methods compiled gradually** | Early batches fluctuate heavily, later batches run faster | Per-batch timeline, compiler activity, constant workload conditions. |
| **Background compilation competing for CPU** | CPU rises alongside latency | Compiler threads/events and total process CPU; rule out other load. |
| **OSR / deoptimization / recompilation** | Timing shifts after some iterations or new branch taken | Compilation/deoptimization data matching timestamps, not just latency graphs. |
| **Dead-code elimination or constant folding in benchmarks** | Microbenchmark looks "too fast to believe", real input folded to constant | Inspect runtime data, observable side effects, and benchmark design. |
| **Escape analysis / inlining eliminates allocations** | Measured object count differs from syntactic **new** count | Define allocation measurement, optimization state, and actual profile. |
| **Different code/cache or data branches** | Same method behaves differently depending on data | Hold input distribution, branch behavior, and allocations equivalent. |

**Never conclude "caused by JIT" solely from early vs. late batch differences.** Class loading, page cache, GC, CPU frequency, scheduler, and I/O can all happen concurrently.

### 3.2. Avoid Microbenchmarks That Mislead the Measurer

Illustrative snippet **not to be used for real benchmarking**:

~~~java
long start = System.nanoTime();
for (int i = 0; i < 1_000_000; i++) {
    int result = 21 * 2;
}
long elapsed = System.nanoTime() - start;
~~~

This snippet is not a standalone complete program. **result** is unused, and the multiplication is a constant; the compiler can eliminate almost all the work. Reported time mostly reflects loop overhead and other runtime factors, revealing nothing about the cost of multiplication with real inputs.

Avoid adding **System.out.println()**, diagnostic object allocations, or file writes inside **each iteration** of the benchmarked region if they are not part of the work under test. Those actions consume time and alter JIT profiles and allocations. Never "fix" it merely by increasing loop counts: compilers can optimize differently for longer loops.

When evaluating **a small Java operation**, use **JMH (Java Microbenchmark Harness)**, an OpenJDK harness providing warmups, measurement iterations, JVM forks, and result consumption (`Blackhole`). Use meaningful state and inputs, check compiler optimizations, run multiple independent forks, and inspect variance. JMH reduces common pitfalls yet **does not turn an unrepresentative workload into a production measurement**.

For **end-to-end requests**, a load test controlling arrival rates, wait times, concurrent clients, and runtime telemetry is far more appropriate than a single-method JMH benchmark.

## 4. GC Bias: Not Just Pauses

A GC event can affect observations in multiple ways:

- **Stop-the-world** phases pause application threads; requests active during that window see increased wall latency.
- Collectors perform **concurrent** work that still consumes CPU/memory bandwidth and can contend with the application even without a matching pause.
- Application allocation rate, live set, heap sizing, GC policy, and collection timing shape behavior, sometimes shifting when inputs or JIT change.
- **Safepoints**, lock contention, OS scheduling, and CPU throttling also introduce pauses or waits; never label a timeline gap "GC" just because a gap appears.
- Diagnostic commands like **GC.class_histogram** or **GC.heap_dump** can carry heavy impact and even distort the incident data under investigation.

### 4.1. Check Temporal Correlation

Suppose request R took **250 ms**, and during that request a **40 ms** GC pause occurred. You have evidence that the pause **may have contributed** to latency, yet you cannot automatically claim "request spent 210 ms in app work + 40 ms in GC": the request could have waited in queues/locks/I/O, and intervals can overlap depending on measurement boundaries.

To draw stronger conclusions:
1. Synchronize or convert timestamps onto a single time axis; distinguish **absolute timestamps** from **JVM uptime**.
2. Place **request traces**, GC/safepoint events, load, CPU, and queue depth side by side.
3. Verify whether affected requests actually **overlap** the pause, rather than relying only on GC count rising in the same minute.
4. Check for other contributors: lock waits, disk/network, request backlog, or compiler contention.
5. Verify across multiple occurrences instead of a single coincidence.

**GarbageCollectorMXBean.getCollectionCount()** and **getCollectionTime()** are cumulative counters that can return **-1** when unsupported. Their semantics/precision depend on the implementation; specifically, **do not take the delta of summed GC times across collectors and treat it as total pause experienced by one request**. Use GC logs or timestamped JFR events when finer temporal alignment is needed.

### 4.2. Collect Just Enough Data on HotSpot/JDK 21

When you control JVM startup, you can enable Unified Logging at a suitable level. Example:

~~~bash
java -Xlog:gc,safepoint:file=gc.log:uptime,level,tags -jar application.jar
~~~

Illustrative command with an application JAR name. On HotSpot, this logs events tagged **gc** or **safepoint** to a file with JVM uptime, level, and tags. Choose higher verbosity only when needed, verify disk space/rotation, and remember **logging also adds overhead**.

For a running process, list supported commands on the target JVM before running them:

~~~bash
jcmd 12345 help
jcmd 12345 help GC.heap_info
jcmd 12345 help JFR.start
jcmd 12345 VM.version
~~~

**12345 is an illustrative PID only**; replace it with the real PID. Available commands, attach permissions, and tools depend on VM/JDK/container. Start recordings only after understanding duration, file size, permissions, and impact. For JFR, distinguish **duration events**, **sampling events**, and **counters**: not every event tells the story of every execution.

## 5. Sampling Bias: Measuring a Lot Does Not Mean Measuring Right

### 5.1. Distinguish the Sample from the Population

**Sampling** saves resources by observing only a subset of events, requests, instants, or stacks. Yet samples can be unrepresentative:

- **Periodic aliasing:** sampling every 1 second can always land on the idle or busy phase of a 1-second cycle.
- **Selection bias:** recording only successful requests while dropping timeouts, fail-fasts, and rejections makes latency metrics look artificially good.
- **Survivorship bias:** inspecting only surviving JVMs while ignoring processes that crashed/OOM'd or restarted before the snapshot.
- **Threshold bias:** profilers/JFR events record only events meeting duration/size thresholds; "no events" can mean below threshold or event disabled.
- **Nonuniform sampling:** samples drawn from only one thread, instance, AZ, route, or load level; unweighted aggregation skews representation.
- **Burst masking:** per-minute averaging hides spikes of a few hundred milliseconds, even though those spikes affect users.

Sampling CPU stacks is **different** from sampling request latency. Stack sampling shows code appearing in samples per the profiler's policy; appearance frequency is not directly the percentage of end-to-end request time spent in that method. Collection methods tied to safepoints or thread states can bias stack capture; understand the profiler's mechanism.

### 5.2. Runnable Java 21 Example: Periodic Aliasing

Suppose there are **100 requests**. Every 10th request (10, 20, 30, …) has latency **100 ms**; the remaining 90 requests take **10 ms**. The true distribution has **mean = 19 ms**, **p50 = 10 ms**, **p95 = 100 ms** (nearest-rank). If you sample only every 10th request, the result depends entirely on **the starting phase**.

**File SamplingAliasDemo.java**

~~~java
import java.util.Arrays;

public class SamplingAliasDemo {
    private static int latencyMs(int requestNumber) {
        return requestNumber % 10 == 0 ? 100 : 10;
    }

    private static int sampleMean(int firstRequest) {
        int total = 0;
        int count = 0;
        for (int request = firstRequest; request <= 100; request += 10) {
            total += latencyMs(request);
            count++;
        }
        return total / count;
    }

    private static int percentileNearestRank(double percentile) {
        int[] values = new int[100];
        for (int request = 1; request <= 100; request++) {
            values[request - 1] = latencyMs(request);
        }
        Arrays.sort(values);
        int index = (int) Math.ceil(percentile * values.length) - 1;
        return values[index];
    }

    public static void main(String[] args) {
        System.out.println("True mean: 19 ms");
        System.out.println("True p50: " + percentileNearestRank(0.50) + " ms");
        System.out.println("True p95: " + percentileNearestRank(0.95) + " ms");
        System.out.println("Sample 5,15,... mean: " + sampleMean(5) + " ms");
        System.out.println("Sample 10,20,... mean: " + sampleMean(10) + " ms");
    }
}
~~~

~~~bash
javac --release 21 SamplingAliasDemo.java
java SamplingAliasDemo
~~~

**Exact stdout:**

~~~text
True mean: 19 ms
True p50: 10 ms
True p95: 100 ms
Sample 5,15,... mean: 10 ms
Sample 10,20,... mean: 100 ms
~~~

In this example, the mean line prints the hand-computed value: **(90 × 10 + 10 × 100) / 100 = 19**. Both sample groups contain 10 requests yet yield opposite conclusions. This is a deterministic simulation example, **not a simulation of how JFR samples stacks**. The lesson is to inspect **how samples and sampling phases are chosen**, not just sample count.

Improve by varying phase/timing appropriately, covering all segments, combining event-based metrics, and never discarding failures; when sampling unevenly, weight by selection probability instead of taking an unweighted mean.

### 5.3. Percentiles, Sample Size, and Coordinated Omission

- **p99** is a percentile of **the distribution of observed latencies**, and cannot be computed by averaging p99s across JVMs, threads, or minutes. Global p99 requires merged distribution data or properly mergeable histograms.
- With **100 requests**, nearest-rank p99 is just one of the top values; tail uncertainty is high. Report sample count, error/timeout counts, and measurement duration.
- **Coordinated omission** occurs in some **closed-loop** load generators: clients wait for the previous request to complete before sending the next, so during a server stall, requests that should have arrived on schedule never enter the dataset. Reported latency can look lower than what users experience under **open-loop** traffic with an independent arrival schedule. To evaluate responsiveness at an expected arrival rate, track **scheduled arrival times**, queue waits, and timeouts; pick load generators/models fit for the goal rather than inventing ad-hoc adjustments without basis.
- Sampling profilers can miss very brief spikes due to sampling intervals or policies; shrinking the interval increases catch probability yet also increases overhead. Never interpret "no samples" as "no such behavior".

## 6. Observer Tool Bias: The Observer Effect

Diagnostics is not invisible. Adding instrumentation can increase work, allocations, synchronization, I/O, event volume, and change JIT optimization boundaries.

| Tool / Measurement Method | Potential Impact Source | How to Mitigate or Verify |
| --- | --- | --- |
| **System.nanoTime() around a batch** | Clock-read cost, start/end timing, scheduler | Measure enough work per batch and compare overhead when changing granularity; do not wrap tiny ops in separate timers and trust them blindly. |
| **Logging per iteration/request** | String formatting, allocation, locks, I/O, flushes, backpressure | Log off hot paths when possible; separate logging config; run A/A tests with and without logs. |
| **JMX/metrics scraping** | Getters/counters, locks, serialization, network, polling rate | Pick reasonable intervals and granularity, watch exporter cost; avoid excessive polling. |
| **JFR** | Event/buffer/stack writes, config-dependent overhead, duration thresholds | Start with suitable events/templates, bounded recordings, check overhead and event loss. |
| **Sampling profiler** | Signals/timers/stack walking/agents; mechanism depends on profiler | Record sampling rate, stack type, dropped samples; compare equivalent baselines. |
| **Thread dump** | Capturing stacks/locks can impact the process; scales with thread count | Capture only when needed, record timestamps; do not spam dumps to "increase certainty". |
| **Heap dump / class histogram** | Heavy impact, pauses and I/O, files can be huge | Use only when heap investigation requires it; record timestamps so dump-induced pauses are not confused with the original incident. |
| **Agents, bytecode instrumentation** | Extra branches/methods, context propagation, allocations, class transformation | Test impact under equivalent workload; distinguish startup agents from dynamic attach agents. |

If variant **A** runs without a profiler and **B** runs with a profiler, seeing higher p99 in B only suggests **possible** overhead. Keep request rate, hardware, data, process state, GC, and timing equivalent; try **A/A** or **A–B–B–A**/multi-run alternating sequences before attributing.

**Do not assume tool impact pushes in only one direction.** Instrumentation sometimes adds time, yet can also alter thread scheduling, code hotness, GC cadence, and lock timing—making some runs *faster* or making rare races vanish. Hence measuring overhead simply as "with tool minus without tool" is only an estimate under controlled conditions, not a universal constant to add/subtract from every request.

## 7. Java 21 Example: Observing Batch Drift Without Jumping to Causes

The complete example below records elapsed time via **System.nanoTime()** and collection count deltas via MXBeans when supported. It performs input-dependent work so the compiler cannot trivially discard the entire result, yet it is **not a JMH benchmark** and does not prove observed differences come solely from JIT or GC.

**File MeasurementPhases.java**

~~~java
import java.lang.management.GarbageCollectorMXBean;
import java.lang.management.ManagementFactory;
import java.util.Locale;

public class MeasurementPhases {
    private static volatile long published;

    private static long work(int seed) {
        long value = seed | 1L;
        for (int i = 0; i < 3_000; i++) {
            value = Long.rotateLeft(
                    value + 0x9E3779B97F4A7C15L + i, 9)
                    ^ (value >>> 11);
        }
        return value;
    }

    private static long totalCollections() {
        long count = 0;
        for (GarbageCollectorMXBean bean
                : ManagementFactory.getGarbageCollectorMXBeans()) {
            long current = bean.getCollectionCount();
            if (current < 0) {
                return -1;
            }
            count += current;
        }
        return count;
    }

    private static void runBatch(String label, int seedOffset) {
        long beforeGc = totalCollections();
        long start = System.nanoTime();

        long checksum = 0;
        for (int i = 0; i < 1_000; i++) {
            checksum ^= work(seedOffset + i);
        }

        long elapsedNanos = System.nanoTime() - start;
        long afterGc = totalCollections();
        published ^= checksum;

        String gcDelta = beforeGc >= 0 && afterGc >= 0
                ? Long.toString(afterGc - beforeGc)
                : "unknown";
        System.out.printf(Locale.ROOT,
                "%s: %.3f ms, GC count delta=%s%n",
                label, elapsedNanos / 1_000_000.0, gcDelta);
    }

    public static void main(String[] args) {
        runBatch("first", 1);
        for (int i = 0; i < 8; i++) {
            runBatch("warmup-" + (i + 1), 1_001 + i * 1_000);
        }
        runBatch("measurement-1", 20_001);
        runBatch("measurement-2", 21_001);
        System.out.println("Published checksum: " + published);
    }
}
~~~

~~~bash
javac --release 21 MeasurementPhases.java
java MeasurementPhases
~~~

**How to read the output:** the program always prints labels **first**, **warmup-1** through **warmup-8**, **measurement-1**, **measurement-2**, and then **Published checksum** in order. **There is no fixed timing stdout** because nanos, GC counts, and compiler activity depend on machine/JVM/load. **GC count delta=0** only means the read counters did not increment in that span; it does not prove the JVM had no concurrent GC work or runtime effects. **GC count delta=unknown** means at least one collector did not report a count.

Even though results feed a **volatile** field to prevent complete dead-code elimination, that is **not enough** to rule out all compiler optimizations, scheduler noise, CPU frequency scaling, safepoints, caches, or input differences. Eight warmup batches are illustrative only and **do not guarantee steady state**. To compare the performance of **work** itself, convert it into a JMH benchmark with controlled inputs and forks.

To inspect GC activity of this example on HotSpot/JDK 21, you can run a separate pass with logging:

~~~bash
java -Xlog:gc,safepoint:file=measurement-gc.log:uptime,level,tags MeasurementPhases
~~~

This is **a separate run**: enabling logging and creating a file is an observation variable. Never compare timings between the two commands as a causal experiment without repeating, alternating order, controlling state, and evaluating overhead.

## 8. Diagnostic Scenario: p99 Spikes After a Deploy

Suppose a Java 21 service on HotSpot shows p99 latency rising from **80 ms** to **230 ms** after a deploy. This is a **hypothetical dataset for analysis practice**, with no cause yet confirmed. A sound workflow:

**Step 1 — Verify data and scope.** Confirm p99 uses the same measurement point, same route/load/concurrency, including appropriate timeouts and failed requests. Check request count at p99, warmup time, deployment platform, CPU quota, and active JDK runtime. If the new build was measured right after startup while the old build was measured after 30 minutes, they are not directly comparable.

**Step 2 — Inspect the timeline rather than a single number.** Plot p50/p95/p99 latency, throughput, CPU, and request queues over time. If only the first 2 minutes are bad and then recover, prioritize startup/cache/JIT hypotheses. If tail latency spikes periodically, suspect GC, batch jobs, locks, or sampling aliasing. If the whole window degrades, look at workload, configuration, and true code regressions.

**Step 3 — Look for correlated runtime signals.** Start with the lightest sources available: JMX/metrics, GC/safepoint logs, bounded JFR, request tracing. On HotSpot JDK 21, verify permissions and **jcmd PID help** before issuing commands. If GC pauses rise concurrently, check whether requests overlap pauses and whether allocation/live set changed. If compiler activity spikes early in the session, check whether variance subsides post-warmup.

**Step 4 — Rule out observer tool effects.** If only the new build has debug logging/agents/profilers enabled, run a control pass with matching config. Never conclude root cause from charts with differing observer configurations.

**Step 5 — Repeat to verify.** Run multiple A/B passes under comparable conditions, randomizing or alternating order sensibly, separating startup and steady state, and recording distributions plus sample counts. Only then state conclusions, confidence level, and remediation steps.

Examples of distinct **evidence-backed** conclusions:

| Verified Observation | Supported Hypothesis | What Cannot Be Concluded Yet |
| --- | --- | --- |
| Slow mainly in first 90 seconds; stabilizes afterward | Warmup, class initialization, caches, or compiler activity | Insufficient evidence to blame JIT alone. |
| Request spikes overlap GC pauses and rise with allocation | GC likely contributes to tail latency | Cannot attribute 100% of spike duration to GC. |
| Peaks every 10 seconds, fixed-period sampling consistently misses them | Sampling is aliasing with load periodicity | True distribution unknown without supplemental sampling. |
| Slow only when verbose logging is on; repeated A/A with same workload also slows | Observation overhead is a major component | Exact per-request fixed overhead unknown. |
| Slow in all phases after holding environment and collection equivalent | Likely code path, I/O, contention, or config change | Cannot rule out JIT/GC without inspecting telemetry. |

## 9. Low-Bias, Repeatable Measurement Workflow

### 9.1. Before Collecting

1. **Write the measurement question:** cold-start readiness, algorithm time/op, CPU, throughput under load, or end-to-end p99? One chart cannot answer everything.
2. **Keep work units clear:** request route, payload size, read/write ratio, client count, arrival rate, cache state, error rate, timeouts, retries, and concurrency.
3. **Record the environment:** full Java version, VM name/vendor, GC, JVM flags/heap, CPU/core quota, RAM/container, build, OS, network, tool versions, timezone, and clock source.
4. **Choose the mode:** independent cold-start runs, or warmup + steady state; if both are needed, report separately.
5. **Define sampling:** all requests or sampled? Sample rate, sampling frame, duration, event thresholds, missing/lost samples, and timeout handling policy.
6. **Estimate observer cost:** which tools are mandatory in production, which are temporary, and what overhead is acceptable.

### 9.2. During the Run

- Measure elapsed duration within the JVM with **System.nanoTime()**; across distributed systems, stamp wall-clock time at each service and account for clock skew.
- Separate **startup → warmup → measurement** windows with clear timestamps. Do not drop transition-phase data if transitions are what users actually suffer from.
- Record request rate, concurrency, queue depth, CPU, GC, and error rate **on the same timestamps** as latency. Unaligned data creates spurious causality.
- Use minimal detail needed to answer the question; escalate from metrics/JMX to JFR/logs or dumps only when justified.
- Never change heap, GC, logging level, profiler interval, or workload between two runs labeled "same conditions" without recording the change.
- When **GC, safepoints, compiler activity, or profiler sample loss** occur, annotate the timeline rather than silently deleting those intervals from statistics.

### 9.3. After the Run

- Report **number of independent runs (forks/processes)**, sample count per run, median across runs, spread, and request latency distribution; add confidence intervals only if methodology and run count truly support them.
- Compare p50/p95/p99 per time window or load level. Do not aggregate percentiles via arithmetic mean; merge compatible raw data/histograms for a combined percentile.
- Keep **A/A** measurements to estimate natural variance, then judge whether A/B differences exceed that noise and repeat consistently.
- Save inputs, configurations, commands, baselines, and evidence (JFR files, GC logs, metrics). With containers, note whether paths are **inside the container** or **on the host**.
- Write a structured conclusion separating: **observations**, **hypotheses**, **evidence**, **competing explanations**, **confidence level**, and **next verification steps**.

### 9.4. Minimal Per-Run Data Table

| Field | Why It Is Needed |
| --- | --- |
| **Run ID / build / commit** | Ties results to exact code. |
| **Full Java version / VM / vendor / flags** | Explains JIT/GC/tool differences across runtimes. |
| **Host/container CPU quota, RAM, OS** | Controls for scheduling, throttling, and resources. |
| **Cold/warmup/measurement timestamps** | Avoids phase mixing, anchors events on timeline. |
| **Payload, rate, concurrency, route, cache state** | Ensures equivalent work is measured. |
| **Sample policy, sample count, failures/timeouts** | Shows which population samples represent and what was missed. |
| **p50/p95/p99, throughput, CPU, allocation, GC/safepoint events** | Cross-checks symptoms and noise sources. |
| **Profiler/JFR/logging config, overhead comparison** | Assesses impact of observation itself. |

## 10. Symptom-to-Cause Discrimination Map

| Signal | Hypotheses to Check | Discriminating Questions |
| --- | --- | --- |
| First call slow, later calls fast | Class init, cache, tiered JIT, initial I/O | Does it repeat per **new process**, or only the first call of **one method**? |
| Slows down after minutes, then speeds back up | Deoptimization, recompile, GC, CPU throttling, contention | Are there simultaneous compiler/GC/CPU/queue events? |
| p99 rises while p50 stays nearly flat | GC pauses, lock convoys, queue spikes, network outliers | Does tail overlap pauses/queues/locks; are samples sufficient? |
| High CPU while throughput does not grow | Spinning, concurrent GC, contention, compiler, overload | Does CPU belong to app threads, GC, or compiler; did it hit CPU quota? |
| Heap grows and drops periodically | Normal or abnormal allocation/GC rhythm | Does post-GC live set trend upward long-term; what is pause frequency? |
| Profiler reports "not seeing" a method | Very short method, low sample rate, JIT optimization, sampling bias | Does the tool sample CPU or wall time; what are thresholds and stack policy? |
| Enabling debug logging makes slowness vanish | Observer effect alters concurrency/timing | Does A/A reproduce when swapping order under fixed workload? |
| Load test reports great p99 even though server stalled | Coordinated omission, timeouts excluded, client queue uncounted | Do requests arrive on an independent schedule or wait for prior responses? |

Do not treat this table as an automated diagnosis engine. Symptoms can have **multiple concurrent causes**. Always cross-check timestamps and full measurement scopes.

## 11. Common Mistakes

1. **"Skipping the first 10 runs counts as warmup."** There is no universal cutoff; compilers and application state can keep shifting afterward.
2. **"Later batches are faster, so JIT definitely optimized it."** Fails to rule out caches, GC, OS scheduling, CPU frequency, or measurement distortion.
3. **"GC count didn't rise, so latency spikes are unrelated to GC."** Counters have scopes and update lag; concurrent GC/safepoints or different time windows still matter.
4. **"GC time equals total slowness added to requests."** Pause times do not add linearly to every request and can overlap other activities.
5. **"One timely thread dump is a representative sample."** It is a single point-in-time snapshot, affected by capture mechanics, and does not measure session-wide frequency.
6. **"p99 across 100 requests suffices to compare two builds."** Tail percentiles are unstable with small samples; check sample count and repeat runs.
7. **"Average of per-instance p99s is system-wide p99."** Statistically wrong; merge raw data or compatible histograms.
8. **"A profiler is a neutral observer."** Enabling profilers/logging/agents can alter execution paths and timing.
9. **"More verbose logging yields more accurate results."** More data can simultaneously add heavy overhead, dropped events, or I/O bottlenecks.
10. **"No spike in sampled data means no spike occurred."** Sampling policy, phase, event thresholds, and sample loss govern detection ability.
11. **"JMH ran faster, so users definitely get faster responses."** Microbenchmarks do not replace end-to-end latency under load, queuing, and I/O.
12. **"Production and laptop differ solely due to hardware."** JDK vendor/flags, GC, container quotas, workload, and observer configs also differ.

## 12. Self-Check and Applied Exercises

**Q1.** Cold start takes 2.5 seconds, then the API settles at 40 ms/request. Do you report one number or two? **Hint:** report at least startup readiness and steady-state request latency separately, because they have different boundaries and goals.

**Q2.** When JFR is enabled, p99 increases 12%. Can you conclude JFR adds exactly 12% overhead? **Hint:** not yet; you need A/A runs, multiple comparable trials, load variance checks, event settings, profiling overhead analysis, and causal evidence.

**Q3.** An API has 12 ms mean latency and 500 ms p99. What should you suspect first? **Hint:** check distribution, sample count, errors/timeouts, request queues, GC/safepoint timeline, and tail events; never replace p99 with average.

**Q4.** JIT activity and a GC pause occur at the same time as a slow request. How do you conclude? **Hint:** temporal coincidence alone is insufficient; measure overlap, rule out competing hypotheses, repeat, and report confidence rather than slapping on a single label.

**Q5.** A test client waits for a response before sending the next request; during a 10-second server stall, statistics show very few high-latency requests. **Hint:** check for coordinated omission and scheduled arrival timestamps. Clients can stop generating load while the service is congested.

## Key References

- [Java SE 21 — System.nanoTime and elapsed time clocks](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/System.html#nanoTime())
- [Java SE 21 — GarbageCollectorMXBean and counter limitations](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/GarbageCollectorMXBean.html)
- [JDK 21 — jcmd and the impact of each diagnostic command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html)
- [JDK 21 — java command and Unified Logging (-Xlog)](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html)
- [OpenJDK JMH — benchmark guide and official samples](https://github.com/openjdk/jmh)
- [JDK 21 — Java Flight Recorder and diagnostic tools](https://docs.oracle.com/en/java/javase/21/troubleshoot/diagnostic-tools.html)

**Expected outcome of a trustworthy measurement:** you can state **what was measured, on which dataset, in which phase, via which sampling method, which tools were enabled, whether the tools altered the system, and what evidence separates JIT/GC/load/observation**. Until you can answer those, do not treat metric deltas as verified performance regressions or improvements.