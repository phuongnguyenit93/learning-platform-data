# 15.6 Analyzing execution samples, call trees, and sample shares in JFR

## 1. Objectives of execution sample analysis

An API sees rising p99 latency and high process CPU; in JDK Mission Control (JMC), the Hot Methods table shows `parse() 42%`, `hash() 28%`, and `serialize() 12%`. These percentages are typically calculated from **observed stack sample counts**, which does not automatically mean each function consumed that exact percentage of **machine-wide CPU time** or **request wall-clock latency**.

This lesson explains how to use `jdk.ExecutionSample` to:

- Identify methods executing Java code that appear frequently in samples.
- Build a **call tree** from caller to callee, tracing the call paths leading to hot methods.
- Distinguish **self/exclusive samples** from **inclusive/total samples**.
- Compute **sample shares** with an explicit denominator, time range, and thread filter.
- Recognize sampling bias, coverage gaps, effects of JIT/inlining, stack depth, native code, and blocking.
- Confirm hypotheses with CPU/GC/I/O measurements and before–after experiments.

**Principle:** execution sampling is a statistical snapshot of *Java code running at the moment a sample is taken*, not a stopwatch measuring the exact execution time of every method call.

## 2. What does a `jdk.ExecutionSample` contain?

Java Flight Recorder (JFR) records events with timestamps and metadata. For `jdk.ExecutionSample`, commonly useful fields include:

| Field | Meaning | Pitfall to avoid |
| --- | --- | --- |
| `startTime` | Timestamp when a sample was captured | Not when the method call began |
| `sampledThread` | Thread whose stack was sampled | Not automatically the thread managing the recorder |
| `stackTrace` | Sequence of method frames on the stack | Not a trace of every call that occurred |
| `state` | Thread state described by the event (depends on JDK/viewer version) | Cannot deduce total blocked/runnable time from a single state |
| Event count | Number of observations matching filters | Not invocation count, CPU nanoseconds, or request count |

A stack sample might look like:

~~~text
(top: currently executing point)
com.example.Tokenizer.scan()
com.example.JsonParser.parse()
com.example.Controller.handle()
com.example.Dispatcher.dispatch()
(bottom: root caller)
~~~

When building a tree from caller to callee, read **from bottom to top**:

`Dispatcher.dispatch() → Controller.handle() → JsonParser.parse() → Tokenizer.scan()`.

Each event **counts as one sample**. A method called 1 million times for a tiny duration each time may appear rarely; a method running continuously for a long time may appear many times. The number of frames in one stack is not additional samples.

### Distinguishing related events

- **`jdk.ExecutionSample`:** samples threads executing Java code. Threads waiting on I/O, monitors, `park`, or executing native code may not appear in this event.
- **`jdk.NativeMethodSample`:** samples threads executing native code, with different scope and semantics; it does not turn `ExecutionSample` into a full native profiler.
- **`jdk.CPULoad`/`jdk.ThreadCPULoad` and OS process CPU metrics:** show CPU load, but do not replace stack-path analysis.
- **Duration/wait events:** `jdk.SocketRead`, `jdk.ThreadPark`, `jdk.JavaMonitorEnter`, and GC-related events help investigate slowdowns from waiting, locks, and pauses. Enablement and thresholds affect event counts.

Templates and JDK releases can use different periods. `20 ms` or `10 ms` is a **requested sampling configuration**, not a guarantee that every thread gets exactly one event per interval. Never multiply `sampleCount × 10 ms` to compute true CPU time. With virtual threads, many tasks unmounted while waiting on I/O may be completely absent from execution samples even when they dominate response latency.

## 3. Call trees: how inclusive differs from self

A **top-down call tree** merges stack samples sharing the same call-path prefix, from the caller at the bottom of the stack up to the executing frame. How the two columns count:

- **Inclusive/total sample count at a node:** number of samples whose call path passes through the node, including samples landing in descendants of that node.
- **Self/exclusive sample count at a node:** number of samples landing right at that node itself, not in any displayed descendant. Think of the top frame being inside that node's method.
- **Caller/parent:** the method that invoked the node; one method can appear under **multiple callers**, creating multiple nodes in the call tree.

Purely hypothetical example, after filtering down to **100 valid samples** for one workload:

~~~text
Worker.run                      100 inclusive,  0 self
├── Api.handle                   70 inclusive,  0 self
│   ├── Parser.decode            45 inclusive, 15 self
│   │   └── Parser.scan           30 inclusive, 30 self
│   └── Validator.verify         25 inclusive, 25 self
└── Batch.handle                 30 inclusive,  5 self
    └── Encoder.encode           25 inclusive, 25 self
~~~

**How to read it accurately:**

1. `Api.handle` accounts for **70/100 = 70% inclusive**; this means 70 samples had a call path passing through the API, not that `handle`'s own body consumed 70% CPU.
2. `Parser.decode` has **45 inclusive**, consisting of **15 self** and **30** in `Parser.scan`. If you only look at hot leaves, `Parser.scan` has 30 self samples; if you look at caller branches, you must inspect `Parser.decode` too.
3. `Batch.handle` has **30 inclusive**, consisting of **5 self** and **25 self** in `Encoder.encode`.
4. The sum of self across non-overlapping nodes equals **15 + 30 + 25 + 5 + 25 = 100**. **Do not add inclusive counts of parent and child**: the same sample is counted at every node along the stack path, so summing inclusive numbers exceeds 100.

Note: JMC may hide JDK frames, group by package/method, or show truncated stacks. When grouping changes, visible self counts at a node can shift; always check raw event stacks or aggregation settings to understand the denominator.

### Top-down, bottom-up, Hot Methods, and flame graphs

- **Top-down/call tree:** answers "which caller paths lead into hot code?" If `HashUtil.hash()` sits under both `Api.authenticate()` and `Batch.index()`, the two branches must be evaluated separately.
- **Bottom-up/Hot Methods:** answers "which methods appear most often, and which callers generate those samples?" Merges the same method across call paths, then opens **predecessors/callers** to trace back to the source.
- **Flame graph:** stacks are grouped by call path; bar width is usually proportional to **sample count**, not individual call start/end times. Height represents stack depth, not CPU load.

When looking for code to optimize, inspect **self samples** and the methods actually doing the work. When identifying the responsible business path, inspect **inclusive + caller tree**. Both require filtering to the right time window and relevant threads.

## 4. Computing sample shares with a valid denominator

Given a set `S` of `N` **selected `jdk.ExecutionSample` events with valid stacks**:

`selfPct(m) = 100 × selfCount(m) / N`

`inclusivePct(node) = 100 × inclusiveCount(node) / N`

Example `N=500`; node `Parser.decode` appears in 125 stacks, but only 40 times as the leaf:

- **Inclusive:** `125 / 500 = 25%`.
- **Self:** `40 / 500 = 8%`.

If the GUI is filtered down to `100` samples for one API, percentages must be computed against `N=100`; do not compare 25% of the whole process directly with 25% of one API. Explicitly document **event type**, **recording**, **time window**, **thread filter**, **stack availability**, **node/method grouping**, and total `N`.

A safe statement is "`Parser.scan` appears in **30% of execution samples in the selected set**." The claim "`Parser.scan` uses exactly **30% of system CPU**" cannot be inferred from this data alone. Likewise, if `parse` is 40% of samples, optimizing it does not guarantee a 40% p99 reduction.

### Why can sample share change while performance does not?

Sample share is a **relative ratio**. Suppose across two recordings:

| Recording | Samples in `parse` | Total selected samples | Share |
| --- | ---: | ---: | ---: |
| Before | 300 | 750 | 40% |
| After | 350 | 1,750 | 20% |

Looking at 40% → 20%, one might claim `parse` became "twice as fast," yet sample counts also depend on recording length, period, thread count, workload, and CPU quota; other code may simply have gotten hotter. **Never use sample share as a substitute for CPU time/request, throughput, latency, and controlled benchmarks.**

With small sample counts such as **8 samples**, 5/8 = 62.5% can swing wildly between runs. Samples taken close together can also be correlated; do not misuse statistical formulas that assume strictly independent trials.

## 5. Limitations and biases of execution sampling

1. **Short-lived tasks:** a method running for a few microseconds very frequently may rarely appear because the odds of catching that frame are low; sample count does not indicate invocation count.
2. **Waiting and native code:** `jdk.ExecutionSample` cannot represent total wall-clock latency when threads spend most of their time waiting on DB, sockets, locks, semaphores, or running native code. Cross-check duration events, `NativeMethodSample`, and OS/native profilers when appropriate.
3. **Unevenness across threads:** a sampling period does not guarantee every thread is sampled equally often. Thread scheduling, sampler behavior, thread counts, and CPU quotas affect selection probability.
4. **JIT/inlining:** interpreted, compiled, inlined, and lambda frames may be decoded or displayed differently across JDKs and viewers; do not treat method names as an invariant static call graph.
5. **Missing/truncated stacks:** stack traces can be depth-limited during **recording** or merely during **printing**; those two limits differ. A tree missing deep callers distorts context.
6. **Time-window selection:** startup/JIT, GC, idle, warm-up, and peak traffic have distinct profiles; only compare windows under equivalent load.
7. **Aggregation bias:** filtering threads, packages, methods, event types, or dropping empty-stack samples changes the denominator `N`. Document active filters whenever reporting percentages.
8. **Causal inference:** a hot call path is a **clue**. It might reflect a slow helper, callers invoking it too often, or excessive data / a poor algorithm. Run experiments to tell them apart.

Avoid setting arbitrarily tiny sampling periods in production: volume and profiling overhead can spike; pick enough samples for the diagnostic goal, measure overhead, and prefer bounded recordings when possible.

## 6. Capturing a recording with `jcmd` and reading it with `jfr`

On JDK 17+ with JFR, find the target JVM's PID and use tools from a compatible JDK:

~~~bash
jcmd <PID> JFR.start name=cpu-probe settings=profile duration=60s filename=cpu-probe.jfr
~~~

Choose `settings=profile` for a profiling-focused template. Always **check the actual configuration** of `jdk.ExecutionSample` on your JDK/template instead of assuming a fixed default period. After the recording finishes and the file is ready:

~~~bash
jfr summary cpu-probe.jfr
jfr print --events jdk.ExecutionSample --stack-depth 32 cpu-probe.jfr
~~~

`jfr summary` lists event types and counts, letting you see whether enough samples exist. `jfr print` displays individual events and stacks. `--stack-depth 32` limits the number of frames **printed**; it does not recover frames that were never recorded. Do not dump millions of events to the terminal; open JMC or use a streaming parser/filter.

In **JDK Mission Control (JMC)**, open `cpu-probe.jfr` and navigate to Method Profiling/Hot Methods/Call Tree depending on your JMC version. Practical workflow:

1. Select the **time window** with abnormal CPU/p99, excluding idle or warm-up if outside your scope.
2. Select the **thread scope** and `jdk.ExecutionSample`; check the post-filter event count.
3. Read **Hot Methods/self** to see where execution sits, then open **call tree/inclusive** to find the call paths accounting for most samples.
4. Pick a leaf and walk up callers: which code path or request flow leads to that leaf most often?
5. Cross-check CPU load, GC, and lock/I/O events; do not assume every slow request is CPU-bound.
6. Choose one evidence-backed small optimization (remove redundant parsing, batch sensibly, eliminate wasted work) and re-measure under the same load and JFR settings.

View names can vary across JMC releases. In a JFR recording, `sampledThread` is the sampled thread; be careful when a thread pool runs multiple request types on the same worker.

## 7. Java 17+ lab: record JFR yourself, read samples, and compute shares

This lab requires only **JDK 17+** (the `jdk.jfr` module is part of the JDK) and runs a CPU worker with two call paths sharing `busyLoop()`. `apiPath()` computes for about **2.4 seconds**, `batchPath()` computes for about **0.8 seconds**, and then the worker sleeps for **0.4 seconds**. It explicitly enables `jdk.ExecutionSample` with a requested period of **10 ms**, filters by `sampledThread`, counts stacks containing path A/B, and computes percentages out of **worker samples with stacks**.

**File `ExecutionSampleLab.java`:**

~~~java
import java.nio.file.Path;
import java.time.Duration;
import java.util.concurrent.TimeUnit;

import jdk.jfr.Recording;
import jdk.jfr.consumer.RecordedEvent;
import jdk.jfr.consumer.RecordedFrame;
import jdk.jfr.consumer.RecordedStackTrace;
import jdk.jfr.consumer.RecordedThread;
import jdk.jfr.consumer.RecordingFile;

public class ExecutionSampleLab {
    private static volatile long sink;

    private static void busyLoop(long millis) {
        long deadline = System.nanoTime()
                + TimeUnit.MILLISECONDS.toNanos(millis);
        long value = 0x9e3779b97f4a7c15L;
        while (System.nanoTime() < deadline) {
            value ^= value << 13;
            value ^= value >>> 7;
            value ^= value << 17;
        }
        sink = value;
    }

    private static void apiPath() {
        busyLoop(2_400);
    }

    private static void batchPath() {
        busyLoop(800);
    }

    public static void main(String[] args) throws Exception {
        Path output = Path.of("execution-sample-lab.jfr");

        try (Recording recording = new Recording()) {
            recording.enable("jdk.ExecutionSample")
                    .withPeriod(Duration.ofMillis(10))
                    .withStackTrace();
            recording.start();

            Thread worker = new Thread(() -> {
                apiPath();
                batchPath();
                try {
                    Thread.sleep(400);
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                }
            }, "jfr-cpu-worker");
            worker.start();
            worker.join();

            recording.stop();
            recording.dump(output);
        }

        long workerSamples = 0;
        long pathA = 0;
        long pathB = 0;

        for (RecordedEvent event : RecordingFile.readAllEvents(output)) {
            if (!event.getEventType().getName()
                    .equals("jdk.ExecutionSample")) {
                continue;
            }
            RecordedThread sampled = event.getThread("sampledThread");
            if (sampled == null ||
                    !"jfr-cpu-worker".equals(sampled.getJavaName())) {
                continue;
            }
            RecordedStackTrace trace = event.getStackTrace();
            if (trace == null || trace.getFrames().isEmpty()) {
                continue;
            }

            boolean hasA = false;
            boolean hasB = false;
            for (RecordedFrame frame : trace.getFrames()) {
                if (frame.getMethod() == null) {
                    continue;
                }
                String method = frame.getMethod().getName();
                if (method.equals("apiPath")) {
                    hasA = true;
                }
                if (method.equals("batchPath")) {
                    hasB = true;
                }
            }

            workerSamples++;
            if (hasA) {
                pathA++;
            }
            if (hasB) {
                pathB++;
            }
        }

        System.out.printf(
                "workerSamples=%d pathA=%d pathB=%d other=%d%n",
                workerSamples, pathA, pathB,
                workerSamples - pathA - pathB);
        if (workerSamples > 0) {
            System.out.printf("A=%.1f%% B=%.1f%%%n",
                    100.0 * pathA / workerSamples,
                    100.0 * pathB / workerSamples);
        }
    }
}
~~~

Run from the directory containing the Java file:

~~~bash
javac ExecutionSampleLab.java
java ExecutionSampleLab
jfr summary execution-sample-lab.jfr
jfr print --events jdk.ExecutionSample --stack-depth 16 execution-sample-lab.jfr
~~~

**Output format**, not fixed stdout:

~~~text
workerSamples=<N> pathA=<A> pathB=<B> other=<O>
A=<a.a>% B=<b.b>%
~~~

Variables `N/A/B/O` depend on the environment and sampler; if `N=0`, the program intentionally skips printing the percentage line. In a JDK 24 run, for example, you might get only **8 samples** across over 3 seconds of CPU work, causing percentages to fluctuate sharply. Do not force an exact **75:25** split even though the two CPU phases have roughly a 3:1 duration ratio; extend test duration or repeat recordings if you need a larger sample size.

**Key points in the code:**

- `Recording.enable("jdk.ExecutionSample")` and `withPeriod(10 ms)` configure sampling; they are not an automatic CPU time measurement.
- `getThread("sampledThread")` filters to the worker thread; events from other threads are excluded from the denominator.
- `getFrames()` holds the stack; checking whether `apiPath`/`batchPath` appears in any frame counts **inclusive by call path**, not self samples in those two methods.
- `busyLoop` shared by A and B easily dominates the hot leaf; to see which side drives the load, inspect its **caller path**.
- `Thread.sleep(400)` adds wall-clock time to the worker without adding execution samples during the sleep. This helps distinguish CPU sampling from latency.
- `RecordingFile.readAllEvents` holds all events in memory, suitable for short labs. For large recordings, iterate `RecordingFile` sequentially or use JMC to avoid excessive memory usage.

To compute **self** at a method, check events whose **top-of-stack frame** is that method and count them. When `busyLoop` is the currently executing frame and `apiPath` sits beneath it, `apiPath` gets +1 inclusive while `apiPath`'s self does not increment. If frames are truncated or JIT inlining alters how a viewer displays them, inspect the raw stack trace before concluding.

## 8. Interpreting results in three scenarios

### A. A large hot method due to unnecessary repeated calls from a caller

Hot Methods: `JsonParser.parse` accounts for 38% of self samples. The caller tree shows most samples come from a request mapper re-parsing a payload already parsed in an earlier layer. A sensible optimization may be **removing the redundant parse** or reusing the parsed result within the request scope, rather than rewriting the parser. Verify semantics, benchmarks, and regression tests.

### B. Slow requests that do not show up in CPU samples

A request takes 1.5 seconds, mostly waiting on a connection pool or socket; Java CPU execution is very brief. `jdk.ExecutionSample` may show too little to explain p99. In this case, inspect `SocketRead`, `ThreadPark`, pool metrics, DB query tracing, timeouts, and the request's call path. **Few execution samples do not prove requests are fast.**

### C. A helper used across multiple processing flows

`HashUtil.hash` accounts for 35% of whole-process samples, yet the caller tree shows most come from batch indexing and only a small portion from API authentication. If your goal is improving API p99, optimizing the batch job may have no direct impact. Isolate the right caller, workload, and time window, then re-measure after making changes.

## 9. Checklist before reporting a hotspot

- [ ] Recorded JDK version, JFR template/period, duration, and CPU quota.
- [ ] `jdk.ExecutionSample` enabled; sufficient sample events and valid stack percentage.
- [ ] Defined time window, thread filter, event type, and **denominator N**.
- [ ] Understood stack orientation: top is the execution point, bottom is the caller; top-down trees reverse stack reading order.
- [ ] Distinguished **inclusive** (whole subtree) from **self** (execution directly at that node).
- [ ] Did not add inclusive counts of parent/child nodes, and did not treat sample % as exact CPU time % or response latency %.
- [ ] Inspected callers/bottom-up if the hot method is a shared helper.
- [ ] Checked for native code, blocking, GC/JIT, short-lived methods, and missing samples/truncated stacks.
- [ ] Verified under matched load for throughput, CPU time/request, p95/p99, and error rate after optimization.

### References

- OpenJDK JEP 328 — Flight Recorder: https://openjdk.org/jeps/328
- Oracle JDK 21 — `jfr` tool: https://docs.oracle.com/en/java/javase/21/docs/specs/man/jfr.html
- Oracle JDK 21 — `jcmd` tool: https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html
- Oracle JDK Mission Control — reading profiling and recordings: https://docs.oracle.com/en/java/java-components/jdk-mission-control/9/user-guide/using-jdk-flight-recorder.html
- Oracle JFR API — `RecordingFile`: https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingFile.html

**Conclusion criterion:** A hot path backed by `jdk.ExecutionSample` is an **optimization candidate based on sample share within the observed set**. Only claim impact on CPU, throughput, or SLAs after cross-checking those metrics and confirming with a before/after experiment.
