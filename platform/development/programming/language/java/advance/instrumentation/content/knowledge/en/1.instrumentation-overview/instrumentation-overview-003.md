# Distinguishing Sampling-Based Observation from Instrumentation-Based Data Collection

## 1. Objectives and Scope

In Java, when you want to understand where a program is spending CPU, how long a request takes, or how many times a method is called, there are two common ways to collect evidence:

- **Sampling-based observation/profiling:** observing the state of the program at specific points in time or across a subset of events, then using those observations to estimate trends.
- **Instrumentation-based collection:** placing measurement points (*probes/hooks*) at defined locations in the execution flow; when the program passes through a measurement point, the collection code runs and records an event, metric, or duration.

After this lesson, you should be able to distinguish **directly observed data** from **statistical estimates**, choose a measurement approach based on the question you need to answer, understand the impact on the JVM, and avoid confusing **stack/CPU sampling** with **trace sampling**.

Here, "instrumentation" includes manually written measurement code as well as code introduced by libraries, AOP, or a Java agent transforming bytecode. Developers do not necessarily need to modify source code to have instrumentation.

## 2. Two Operating Mechanisms

### 2.1. Sampling: Asking "What Is the Program Doing Right Now?"

A sampler may wake up periodically, inspect running threads, capture stack traces or runtime state, and accumulate the occurrence counts of each method/call path. For example:

~~~text
Time:        0ms     10ms     20ms     30ms     40ms
             |--------|--------|--------|--------|
Work:        [   A   ][B][      A      ][   C   ]
Sampling:      ^        ^        ^        ^

Result: number of samples that saw A/B/C, not the actual number of calls to A/B/C.
~~~

If method A appears in 70/100 matching CPU samples, we have **suggestive evidence** that A or a call path containing A accounts for a significant portion of the observed CPU time. You must not conclude that "A was called 70 times" or "each call to A takes 70% of the time."

There are two different measurement options:

- **CPU/on-CPU sampling:** observes execution that is actively using the CPU; suitable for finding hot methods and CPU-intensive call paths. Work waiting on I/O or locks may appear rarely or not at all in this type of sample.
- **Wall-clock/elapsed-time sampling:** considers real elapsed time, and can observe waiting, sleeping, or blocked work depending on the tool and configuration. Useful when latency is high while CPU usage is not.

Sampling frequency, measurement window, thread selection, and stack type determine what the results mean. A 10 ms sampling interval does not mean every operation shorter than 10 ms disappears, but short/rare operations **are easily missed**. Changing the frequency does not automatically turn sample counts into exact invocation counts.

### 2.2. Instrumentation: Asking "What Happened at This Point?"

Suppose we want to measure a request:

~~~text
request arrives
    |
    +--> probe START: record timestamp and context
    |
    +--> business logic / DB call / HTTP call
    |
    +--> probe END: compute duration, record status/error
    |
response returned
~~~

A measurement point can produce:

- **Metric:** counting calls/errors, recording duration histograms, payload sizes.
- **Trace/span:** start/end timestamps, parent–child relationships, attributes, and errors for an operation.
- **Event/log:** deterministic events such as retries, cache misses, or connection open/close.

If **every** call passes through the probe and recording is not dropped, the counter at the probe reflects the number of times that location was traversed; the duration measurement reflects the elapsed time across the chosen boundary. It can still have bias due to measurement overhead, probe placement, clocks, concurrency, and data loss during telemetry export.

Instrumentation can be added in several ways:

1. **Manual:** calling a timer/counter or the OpenTelemetry API directly in Java.
2. **Library/framework:** interceptors, filters, aspects, or decorators wrapping operations.
3. **Java agent:** using the Instrumentation API and bytecode transformation at class load/retransform time to insert hooks into methods. This is *zero-code* with respect to the application source, yet it is still instrumentation at runtime.

## 3. Comparison by What You Can Actually Measure

| Perspective | Sampling | Instrumentation |
|---|---|---|
| Unit of data | Snapshot/stack/event selected at a point in time | A single traversal of a probe, span, metric observation, or event |
| Strongest questions | "Which call paths use the most CPU?", "What are the trends during the window?" | "How many errors occurred?", "Which steps did this request take?", "How long did this operation take?" |
| Very short/rare methods | May not appear in samples | Can be recorded if the path is instrumented |
| Total call count | Cannot be inferred directly from sample count | Can be counted approximately/exactly at the probe, depending on configuration and export path |
| Business details | Usually limited if only stacks are captured | Can attach status, error type, operation name, trace context |
| Cost typically depends on | Samples/second, stack type, thread count, recording time | Probe traversal frequency, data volume, synchronization, allocation, exporter |
| Program impact | Can skew samples, consume CPU/memory if sampled too densely | Can slow down hot paths, alter JIT/inlining and concurrency characteristics |
| Initial setup | Usually convenient for exploring unknown areas | Requires choosing measurement points; agents/frameworks can add many points automatically |
| Safe conclusion | Distribution/estimate with uncertainty | Events observed at the instrumented boundaries |

**There is no rule that sampling is always cheaper or instrumentation is always more accurate.** A profiler sampling too densely with heavy stack capture can incur high overhead; a minimal counter can be very lightweight. Conversely, tracing every call inside a loop of millions of iterations can be many times more expensive than sampling.

## 4. Quantitative Example: Same Program, Two Perspectives

Suppose over 60 seconds a service handles 100,000 requests, of which 250 fail:

- If you place a **counter** at the exact request completion point, recording every request and error without loss, you get the total count, total errors, and error rate: 250 / 100,000 = 0.25%.
- If you only take **100 CPU stack samples**, you cannot deduce the 250 failed requests. Stack samples do not contain request counts, and many requests are too short to be observed.
- If you record a **span for every request** and then choose to retain 10% of traces, the number of stored spans will also not equal the total number of requests. You can combine counters for all requests with trace sampling to reduce trace storage cost.

Suppose a call path appears in 60/100 CPU samples. The correct interpretation is "roughly 60% of the captured CPU samples belong to this call path within the measured window and configuration." This is a signal to prioritize investigation, **not** an absolute duration or an exact call count.

For rare events, there is also the risk of missing them completely. In a simple model, if the probability of catching a state in a single independent sample is p, the probability of seeing it at least once after n samples is 1 − (1 − p)^n. This formula is only an intuitive illustration: real-world samples can be correlated over time, so do not apply it mechanically to guarantee confidence.

## 5. Java 17+ Example: Manual Instrumentation

Save the following as **InstrumentedDemo.java**:

~~~java
public class InstrumentedDemo {
    // Single-threaded example only; these counters are not thread-safe.
    private static long calls;
    private static long failures;
    private static long totalNanos;

    static int square(int n) {
        long start = System.nanoTime(); // Elapsed-time clock.
        try {
            if (n < 0) {
                throw new IllegalArgumentException("negative value");
            }
            return n * n;
        } catch (RuntimeException ex) {
            failures++;
            throw ex;
        } finally {
            calls++;
            totalNanos += System.nanoTime() - start;
        }
    }

    public static void main(String[] args) {
        int sum = square(2) + square(3);
        try {
            square(-1);
        } catch (IllegalArgumentException expected) {
            // Keep the program running to inspect the metrics.
        }

        System.out.println("sum=" + sum);
        System.out.println("calls=" + calls);
        System.out.println("failures=" + failures);
        // totalNanos is a runtime measurement that varies across runs.
    }
}
~~~

Run with JDK 17 or later:

~~~bash
javac --release 17 InstrumentedDemo.java
java InstrumentedDemo
~~~

Stdout:

~~~text
sum=13
calls=3
failures=1
~~~

**Explanation:** The failing call is still counted in **finally**; the duration measurement uses **System.nanoTime()** (for measuring elapsed intervals, not calendar timestamps). The value of **totalNanos** depends on the machine, JIT, and current load, so there is no fixed nanosecond output. Where you place the timer determines which work it includes.

In multi-threaded applications, replace shared variables with thread-safe mechanisms such as **LongAdder**, a histogram/metric SDK, or a dedicated collector. Do not print logs or acquire expensive locks every time a hot method runs. To compute p95/p99, you must observe the **latency distribution** using a histogram or appropriate statistical method; having only total time and call count only gives you the average, not percentiles.

## 6. Java 17+ Example: Periodic Stack Sampling

The following example implements a small sampler to illustrate the difference in *mechanism*. It is **not** a replacement for JFR or a production profiler. Save as **SamplingDemo.java**:

~~~java
import java.util.concurrent.atomic.AtomicInteger;

public class SamplingDemo {
    private static volatile boolean recording = true;
    private static volatile long workResult;

    static void busyForMillis(long millis) {
        long end = System.nanoTime() + millis * 1_000_000L;
        long n = 0;
        while (System.nanoTime() < end) {
            n++;
        }
        workResult = n;
    }

    public static void main(String[] args) throws InterruptedException {
        Thread target = Thread.currentThread();
        AtomicInteger hits = new AtomicInteger();

        Thread sampler = new Thread(() -> {
            while (recording) {
                for (StackTraceElement frame : target.getStackTrace()) {
                    if (frame.getClassName().equals("SamplingDemo")
                            && frame.getMethodName().equals("busyForMillis")) {
                        hits.incrementAndGet();
                        break;
                    }
                }

                try {
                    Thread.sleep(10);
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                    return;
                }
            }
        });

        sampler.start();
        busyForMillis(300);
        recording = false;
        sampler.join();

        System.out.println("finished=true");
        System.out.println("busySamples=" + hits.get());
    }
}
~~~

Run:

~~~bash
javac --release 17 SamplingDemo.java
java SamplingDemo
~~~

The first line is always **finished=true** when the program exits normally; the second line is **busySamples=...**, an integer that varies with thread scheduling and observation timing (it can be 0 if the sampler does not get a chance to run). This is **not a call count**: **busyForMillis** is called only **once**, yet it can appear in multiple snapshots.

**Why is this only for illustration?** **Thread.getStackTrace()** and **Thread.sleep(10)** have their own overhead, resolution, and bias; observing a thread can also perturb the results. Production profilers choose appropriate JVM/OS sampling mechanisms and data formats. A large number of samples does not guarantee a good measurement if the wrong CPU-vs-wall mode is used or the collection window is unrepresentative.

## 7. JVM Tools: Recognizing the Collection Strategy

### 7.1. Java Flight Recorder (JFR)

JFR is built into the JDK and collects many types of events. When execution-sampling events like **jdk.ExecutionSample** are enabled, you analyze stack/method distributions by sampling. JFR also has **instant or duration events** (such as certain lock, GC, and I/O events) and supports **custom events** from the application.

Therefore, calling all of JFR "sampling only" would be wrong: **a single tool can combine sampling and event instrumentation**. The event types, recording mode, and settings determine what the data means.

You can try it on a running JVM (substitute a real PID, keep the recording long enough, and ensure access permissions):

~~~bash
jcmd <PID> JFR.start name=investigate settings=profile duration=30s filename=profile.jfr
jfr summary profile.jfr
jfr print --events jdk.ExecutionSample profile.jfr
~~~

Inspect **jfr summary** to check which event types are actually present in the recording. The absence of samples in the file is not enough to prove a method never ran; it could be due to configuration, time window, thread state, or frequency.

### 7.2. Async-profiler and Sampling Profilers

CPU profilers like async-profiler are often useful for finding hot stacks on the JVM with configurable, controlled overhead. Make sure to check the mode—**CPU**, **wall**, **allocation**, or **lock**: the same tool name produces samples with different meanings depending on the selected event. A flame graph built from stack samples represents the distribution of samples across call paths, not directly a chart of how many times methods were called.

### 7.3. Java Agents, Interceptors, and OpenTelemetry

A Java agent or interceptor can add probes at the entry/exit of HTTP handlers, DB queries, or library calls. OpenTelemetry provides both **zero-code instrumentation** (typically via an agent) and **code-based instrumentation** (APIs written in the application) to produce telemetry such as metrics/traces/logs.

**Distinguishing two easily confused types of "sampling":**

- **Stack/CPU sampling:** chooses points in time to observe the call stack, used for profiling.
- **Trace sampling:** decides which traces/spans are recorded/exported/retained, for example by ratio or after knowing the outcome. It can be applied **after the code has already been instrumented** and does not turn a trace into a CPU profile.

Thus, a system can **instrument 100% of requests for metrics**, **sample a fraction of traces** to reduce storage volume, and simultaneously **sample CPU stacks** when investigating performance.

## 8. Accuracy, Coverage, and Overhead

### 8.1. Right Question First, Right Tool Second

- **Hot CPU:** use CPU sampling over a representative window; read inclusive/exclusive stacks properly and verify across multiple runs.
- **High latency but low CPU:** examine wait/blocked/I/O/lock states, wall-clock sampling, and request/DB duration instrumentation.
- **Request counts, error counts, retry rates:** counters at defined boundaries; verify that both error paths and async paths are counted.
- **Where a specific request went:** distributed tracing with spans and context propagation across threads/services; stack profiles do not replace cross-service causality.

### 8.2. Budgeting Overhead

For sampling, the total number of observations is roughly **sampling rate × duration × number of observed entities**, while the cost per sample depends on the stack/event type and storage format. For instrumentation, total probe executions are close to **the number of times code paths traverse the measurement point**. Do not tie these factors to a single fixed overhead number across all JVMs.

Common sources of impact:

- Probes inside loops/hot methods, allocating objects, writing synchronous logs, or acquiring shared locks.
- Capturing stacks too frequently, across many threads, or exporting too much data.
- Bytecode weaving altering call path structure/JIT inlining; profilers and JFR recording also have costs.
- Recording high-cardinality attributes (user ID, request ID, raw URL) increasing memory usage, metric series, or backend storage.
- Telemetry being buffered, batched, sampled, or dropped under load; exported counts may be lower than actual occurrences.

When comparing benchmarks, keep workload, JIT warm-up, memory allocation, GC, thread count, and environment consistent; measure a baseline against different collection configurations. **Do not assume a tool has zero impact on the program just because it does not modify source code.**

### 8.3. "Accurate" Comes with Conditions

Instrumentation measures accurately **at the probe boundaries** if all call paths are traversed and no data is lost; it does not automatically prove what caused slowness inside. Request duration may include network wait, queuing, or downstream calls. If you only measure inside a controller, you may miss time spent before the controller and after the response is committed.

Sampling provides a **distribution estimate**, subject to uncertainty from sample count, thread scope, bias, and time window. The top frame shows what was running at the sample moment; the inclusive stack shows the caller chain containing that point. A common mistake when conflating the two is attributing the same CPU usage to every frame in the stack ("each method used that much CPU") or treating sample counts as total call counts.

## 9. Choosing a Measurement Approach by Scenario

| Scenario | Initial Priority | Why |
|---|---|---|
| Unknown CPU hotspot in a service | CPU sampling / JFR profiler | Broad exploration without instrumenting every method upfront |
| Need to count requests, errors, retries, cache misses | Counter/event instrumentation | The unit of observation is each event to be counted |
| Need API p95/p99 latency | Timer/histogram at request boundaries | Requires duration distribution, including non-traced requests |
| Need to follow a journey across multiple services | Trace instrumentation + trace context | Requires events with parent–child / causal links |
| Only a very fast branch causes rare errors | Targeted probe/log or intentional event | Periodic snapshots easily miss short branches |
| High latency but CPU is not high | Duration metrics + wait/lock/I/O events, wall profiling | A CPU-only profile can hide waiting time |
| Want to keep telemetry cost low | Lower sampling rate, limit probes, batch/sample traces | Need to balance coverage and cost based on actual measurements |

An effective workflow: **(1)** state the question and unit of measurement; **(2)** use sampling to locate suspect areas when hotspots are unknown; **(3)** place instrumentation at boundaries that need quantification; **(4)** correlate metrics, traces, profiler data, and system load; **(5)** reduce/tune probes after investigation. Use multiple sources of evidence when concluding root cause.

## 10. Common Pitfalls and How to Fix Them

1. **"100 samples in method X means X was called 100 times."** False: one long call can be sampled many times; a million short calls may appear in only a few samples.
2. **"No stack trace means the code didn't run."** False: it could be missed due to frequency, time window, thread state, or disabled events.
3. **"Instrumentation always captures everything."** False: probes may miss paths, traces may be sampled/dropped, agents may skip classes/methods, or the app may crash before flushing.
4. **"Trace sampling and CPU sampling are the same."** False: the former decides which trace data is kept; the latter chooses points in time to observe stacks/CPU.
5. **"JFR only does sampling."** False: JFR has sample events, timed/duration events, and custom events; check each type.
6. **"Recording duration tells you CPU time."** False: **System.nanoTime()** in the example measures elapsed time, including waiting; for CPU time, use an appropriate measurement.
7. **"Adding logs to every method gives free observability."** False: I/O, string formatting, allocations, locks, and exporters can significantly alter system behavior.
8. **"Seeing p99 change means we know the cause."** Not enough: check workload, baseline, GC, lock/I/O, and telemetry overhead.

## 11. Self-Verification Exercises

**Experiment A — seeing sampling miss or double-count:** run **SamplingDemo** several times, change **Thread.sleep(10)** to **Thread.sleep(100)**, and reduce **busyForMillis(300)** to **busyForMillis(20)**. Observe how **busySamples** changes dramatically; it is a snapshot count, not a call count. Results are not fixed across machines.

**Experiment B — instrumentation recording errors too:** run **InstrumentedDemo** and change the number of calls. Even when a call throws an exception, **finally** still increments **calls**; **failures** records accurately along the catch branch in the example. If you move this code to multiple threads, replace plain counters with proper synchronization tools before asserting exact counts.

**Check-yourself questions:**

- An API receives 1 million requests but retains only 1% of traces. Can you use the number of stored traces as the total request count? **No**; use an appropriate request counter.
- A flame graph shows many samples in the parser. Is that enough to conclude the parser was called the most times? **No**; it suggests the parser accounted for many samples under the profiler's mode.
- You want to know which specific DB call was slow and which request it belonged to—what do you choose? **A span/timer at the DB boundary with trace context attached**, then correlate with profiling if needed.
- The CPU profile shows few samples, yet p99 latency increased. Should you ignore the issue? **No**; investigate wait/lock/I/O, queues, and timing events.

## 12. Key Takeaways

**Sampling answers "across our observations, where was the program most often?"** It is very useful for finding hot execution areas and trends, provided you read the results as **estimates**.

**Instrumentation answers "what happened when code passed through the chosen measurement point?"** It is well suited for counters, durations, traces, and business details, provided you understand **probe coverage and the data export path**.

The two approaches **complement each other**: profiling to find problems, instrumentation to measure critical behavior, and trace sampling to control trace storage costs. Evaluate conclusions based on the measurement question, data semantics, time window, and actual overhead.

### References

- [Oracle — Java Flight Recorder API Programmer's Guide (JDK 17)](https://docs.oracle.com/en/java/javase/17/jfapi/)
- [Oracle — Using Java Flight Recorder](https://docs.oracle.com/en/java/java-components/jdk-mission-control/7/user-guide/using-jdk-flight-recorder.html)
- [OpenTelemetry — Instrumentation](https://opentelemetry.io/docs/concepts/instrumentation/)
