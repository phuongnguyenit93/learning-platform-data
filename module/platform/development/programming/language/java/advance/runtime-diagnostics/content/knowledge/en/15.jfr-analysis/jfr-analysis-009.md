# 15.9 Cross-checking automated analysis results against evidence and load context

## Objectives

After opening a Java Flight Recorder (JFR) recording, Java Mission Control (JMC) or an automated analyzer may report findings such as "high CPU," "contention detected," "heavy GC," "notable allocation," or "hot method." These are **signals to investigate**, and do not by themselves prove the root cause of latency, reduced throughput, or application errors.

This lesson focuses on the step most often skipped: **cross-checking automated findings against raw JFR events and the system's load context**. The analyst needs to know which data the tool relied on, whether that data is representative, whether the finding aligns with the symptom timeline, and what extra measurements are needed before changing code, heap, GC, or infrastructure.

After this lesson, you will be able to:

1. Read an automated analysis result as a **testable hypothesis** rather than a conclusion.
2. Check recording quality: time span, event types, event thresholds, sampling, stack traces, missing data, and tool limitations.
3. Verify findings with raw JFR events, APM/logs/OS timelines, and application metrics.
4. Normalize comparisons by duration, request rate, workload type, concurrency, payload/data size, and environment conditions.
5. Evaluate conflicting findings, distinguish correlation from causation, and decide when data is sufficient to test a change.
6. Document conclusions with sources, confidence bounds, falsification conditions, and a re-measurement plan.

Scope: HotSpot/OpenJDK Java 17+ (`jfr` commands illustrated for JDK 21), JFR/JMC, and JFR-based analysis systems. Rule names, scores, default events, and JMC UI layouts may vary by version. Do not assume every recording contains every event type.

## 1. What does automated analysis actually provide?

A JFR analyzer can:

- **Aggregate data:** event counts, durations, distributions, CPU samples, allocation samples, stack frames, thread states, and GC phases.
- **Apply rules/thresholds:** for instance, flagging high CPU usage, long GC pauses, monitor wait counts, or low profiling event counts.
- **Compare patterns:** compare snapshots, time intervals, or baselines if supplied with the corresponding data.
- **Provide explanations/recommendations:** turn a signal into prose describing a bottleneck or optimization direction, including when the tool uses AI/LLMs.

Distinguish four levels:

| Level | Example | What can be claimed |
| --- | --- | --- |
| **Raw observation** | JFR contains 35 `jdk.GarbageCollection` events in the recorded window | Events were recorded in the file, assuming a valid file |
| **Derived metric** | Total GC pause of X ms/minute in a segment | Depends on event selection, window calculation, and avoiding double-counting |
| **Heuristic finding** | Rule flags "GC may be impacting performance" | An indicator based on the rule's threshold; requires context checking |
| **Root-cause claim** | "GC is the primary cause of checkout p99 rising" | Requires cross-checking request latency, timing, workload, and competing causes |

Automated results mainly help **prioritize investigation**. A severity/score in some JMC versions is a rule-based ranking—**not the probability that a conclusion is right**, not a p-value, and not a direct measure of user impact. A rule may flag a valid event that is irrelevant to SLOs; conversely, a major incident may go unflagged if an event was disabled or filtered by a threshold.

**Example:** "Found monitor contention" shows corresponding events exist; to conclude contention caused timeouts, you must still inspect threads, stacks, durations, frequency, load phase, and affected requests.

## 2. Three core questions before trusting a finding

### 2.1. What is the tool talking about?

Turn prose into a measurable statement:

> Between T1–T2, on JVM P, with configuration C, signal E appeared at level M, involving thread/method/GC phase K.

Record the exact rule name, warning level, flagged target, time range, and event references. If an AI summary says "memory leak" without citing object retention, post-GC heap trends, or classloader roots, it is merely a hypothesis.

### 2.2. What data directly supports it?

Trace back to one or more event types, fields, aggregations, stack traces, and the recording interval. State clearly:

- Was the event **recorded per occurrence**, recorded above a threshold, or **sampled**?
- Are there enough samples to identify a trend? Were events disabled, filtered out, missing stacks, or timed out before flushing?
- Was the result computed over the **entire file** or only the **symptom window**? Was it diluted by warm-up or idle phases?
- Were numbers re-verified on the actual exported JFR recording rather than just a dashboard screenshot?

### 2.3. Does the load context match?

Cross-check capture timing and application state: requests/s, request mix, concurrency, payload, batch size, CPU quota/throttling, heap/GC flags, instance count, worker count, JDK version, warm-up, deployments/restarts, and upstream/downstream errors. Two recordings with different event counts due to **different amounts of work** are not necessarily a regression.

A finding deserves priority only when it combines **material symptom + mechanistic evidence + temporal alignment + comparable context (or explained differences)**.

## 3. Profiling the recording before analyzing its contents

A `.jfr` file does not carry complete system context on its own. Start an incident note with a minimal table:

| Group | Information to record | Why it matters |
| --- | --- | --- |
| Identity | Service, instance/pod, PID, build/commit, deployment | Prevents mixing data from another process |
| JVM | JDK/vendor/version, collector, JVM flags, and memory limits | Events and behavior change across JVMs and configs |
| Recording | Filename, start/end time, duration, timezone, `.jfc` settings, sampling/thresholds | Confirms whether the file observed the right window |
| Data quality | Present event types, counts, stack availability, truncated file, chunk coverage if available | Prevents concluding from nonexistent data |
| Workload | RPS, request mix, concurrency, payload/batch size, warm-up/steady-state | Compares equal amounts of work |
| SLO | p95/p99, error rate, timeouts, throughput, CPU/RSS, business requirements | Shows whether the finding has real impact |
| Change markers | Deploys, rollouts, autoscaling, cache rebuilds, batch jobs, traffic events | Explains noise and before/after conditions |

Not every file contains JDK/OS settings or full event configuration in an easily queryable form. When metadata is missing, pull it from deployment manifests, launch commands, metric labels, Java version, and contemporaneous logs. Record "unknown" if unverifiable.

### 3.1. Recording duration and actual data span can differ

A continuous recording with `maxage`/`maxsize` may retain only the last few minutes even if it ran for hours. A fixed-duration recording may stop before an alert fires. A recording exported late or written to an unstable filesystem may miss the target phase.

First prove **the file covers the error window**, with pre–during–post data where needed. If it does not cover it, the right conclusion is **insufficient evidence**, not "no anomalies."

### 3.2. Choosing the right time intervals

Split at minimum into:

1. **Baseline:** before the spike, with relatively stable workload and configuration.
2. **Incident:** the interval where p99/errors/throughput/CPU violated targets.
3. **Recovery:** after the spike, if available.
4. **Control:** another interval with similar load and no errors, when obtainable.

Any "whole recording" report must be re-checked on the **incident window**. If the first 58 minutes are idle and the last 2 minutes are peak load, a 60-minute average hides the real peak. Conversely, a single 200 ms anomaly warning does not represent two hours of operation.

### 3.3. Aligning clocks

Use timestamps with explicit timezone/UTC, and know which system produced each timestamp: JFR, application logger, APM, container runtime, or node. If clocks skew, a pause and a request timeout can look simultaneous or artificially offset. Duration events have start/end times, while sample events only have an observation timestamp. Match by overlapping intervals rather than arbitrarily pairing two points.

**Never use file-open time or artifact-upload time** as the event timestamp. Never use a post-restart PID to explain an old process.

## 4. JFR has observational limits: coverage, thresholds, and sampling

### 4.1. "No events seen" has many meanings

Not seeing `jdk.JavaMonitorEnter` or `jdk.SocketRead` can happen because:

- Recording configuration did not enable that event type.
- A threshold only recorded operations exceeding a cutoff; shorter operations were dropped.
- The recording started after the phenomenon ended.
- The file kept only a rolling recent window; older data was evicted.
- Events were filtered during export/printing; displayed stack depth was too shallow.
- Sampling was sparse, the window was short, or samples were missed.
- The application used a mechanism different from the event you searched for: e.g., waiting on `ReentrantLock`/parking is not waiting on a Java object monitor.
- Activity occurred but stayed below the rule's detection threshold.

Thus **0 recorded events ≠ 0 real-world activity**, unless you prove the capture covered the activity in question.

### 4.2. Samples are not exact counters

`jdk.ExecutionSample` and CPU stack sampling provide **stack samples**, not every method invocation. A method with many samples may be a hotspot, yet sample share does not automatically equal request wall-clock latency share—especially when threads wait on I/O/locks or spend CPU in native/GC/JIT. "Zero samples in method A" does not prove A spent no time.

For allocation sampling, sample count is not true allocation count; use weights/estimates and the tool's supported scope when concluding on allocation rate. Differing sampling modes, periods, data volumes, stack filters, and versions make raw count comparisons error-prone.

### 4.3. Durations, thresholds, and overlapping events

A `jdk.GarbageCollection` event describes a GC operation; GC phase events (if present in the file) have their own structure. Never add the duration of a parent GC event and its subphase events into "total pause" because you will double-count; never treat every GC duration as a Stop-The-World pause if the collector has concurrent phases. Look for exact pause events or collector-appropriate GC logs when correlating latency.

For `jdk.JavaMonitorEnter`, `jdk.ThreadPark`, and file/socket I/O, thresholds can cause only operations above the cutoff to be recorded. A recording with a 20 ms threshold and one with a 5 ms threshold **do not contain comparable event sets**, even for the same event type.

### 4.4. Automated analysis rules have preconditions

A rule may require enough CPU samples, enough duration, or matching events. When data is scarce, an "OK" result sometimes just means "the rule did not trigger." Inspect the rule's explanation, preconditions, enabled event list, missing samples, and reported confidence; never turn "no warnings" into "healthy application."

For AI/LLM summaries, require citations to event types, metrics, time windows, units, and reproducible reasoning. Fluent prose that cannot be cross-checked lacks operational value.

## 5. Cross-checking evidence by finding type

| Automated finding | JFR evidence to inspect | Independent evidence | Falsification questions |
| --- | --- | --- | --- |
| "High CPU / Hot Methods" | `jdk.CPULoad`, `jdk.ThreadCPULoad`, `jdk.ExecutionSample`, stacks/call trees, and sample counts | Process/container CPU, throttling, RPS, native/GC/JIT CPU, traces | Did CPU rise because load doubled or due to a regression? Are there enough samples? |
| "GC impact / Long pauses" | GC events/pause phases, heap before/after, duration, and timestamps | GC logs, p99 latency, allocation rate, CPU, heap headroom | Do pauses overlap slow requests? Are concurrent phases being misread? |
| "Allocation pressure" | Allocation sampling, classes and stacks, estimated rates if supported | Allocation profiler, RPS/payload, heap trend, GC rate | Did allocations rise because requests rose? Is there retention/leak evidence? |
| "Possible memory leak" | Live/old object samples if enabled, heap usage and GC trends | Heap dump/dominator tree, GC roots, cache occupancy, same load | Are objects retained long-term or just valid workload? |
| "Monitor contention" | `jdk.JavaMonitorEnter`, monitor class, blocking threads, stacks, durations | Thread dumps, request traces, lock metrics, thread pools | Does monitor waiting coincide with the incident and sit on the critical path? |
| "Thread parking / blocked" | `jdk.ThreadPark`, stacks, parked duration, thread states | Executor queues, pool saturation, DB connection pool, p99 traces | Is waiting normal by design or resource saturation? |
| "Slow I/O" | `jdk.SocketRead`/`SocketWrite`, `jdk.FileRead`/`FileWrite` (if enabled) | Network RTT, DB latency, filesystem metrics, upstream errors | Which side is slow? Do above-threshold events represent traffic? |
| "High classloading/JIT" | Class load/compile events if recorded, code paths, and warm-up timeline | Deploys/restarts, cache warm-up, compilation counters | Only during startup or in steady state? |
| "Low CPU but high latency" | `ThreadPark`/monitor/socket/file events, CPU samples if present | Traces, downstream latency, queuing, CPU throttling | What is the app waiting on? Does low CPU mean idle or blocked? |

This table is a **verification roadmap**, not a claim that all listed events are enabled in `default.jfc`. For each file, check which event types exist and their sample counts before running commands.

## 6. Normalize by workload instead of comparing raw event totals

### 6.1. Compare equal-length windows or normalize by time

Suppose recording A is 10 minutes and recording B is 20 minutes. B has 100 GC events and A has 70. Concluding "B is worse because it has more GCs" is unfounded. Compute events/minute, GC pause ms/minute, and corresponding throughput; then inspect collector type, workload mix, and what each event represents.

Useful rates when samples are sufficiently representative:

- **Request rate:** observed requests / seconds.
- **Event rate:** recorded events / minute (only comparable under identical settings/thresholds).
- **Allocation rate:** bytes/s or bytes/request if the tool provides reliable estimates.
- **GC pause burden:** total **STW pause** / matching duration; never lump in concurrent phases or nested events.
- **Wait burden:** total wait time across relevant threads, avoiding mistaking concurrent waits across many threads for wall-clock time of one request.
- **Error rate:** errors / requests of the same type.
- **CPU:** process/cgroup CPU over time, factoring in quotas and throttling.

### 6.2. Normalize by request count, mix, and work size

The same 100 events/minute can mean very different things if:
- A serves 200 requests/s, while B serves 2,000 requests/s;
- A reads 2 KiB payloads, while B reads 2 MiB;
- A is mostly cache hits, while B is mostly database writes;
- A has concurrency 20, while B has concurrency 1,000;
- A has 1 replica, while B has 8 replicas with uneven traffic.

Per-request counts only help for event types sensibly tied to requests with comparable event coverage. For batch jobs, normalize per record processed, job, MiB of data, or transaction type rather than HTTP requests. **Never substitute per-request rates for per-request latency:** a single slow request can drag out even when total event rate is low.

### 6.3. Distribution matters: p99 is not the average

Rising p99 latency cannot be explained by average GC values alone. A handful of pauses or lock waits coinciding with bad requests can drive tail latency; conversely, high total GC time that misses critical requests does not prove GC caused an SLO breach.

Always inspect:
- Time-aligned charts (request p99, GC pauses, CPU, locks, I/O).
- Percentiles and sample counts by route/transaction, especially the affected user cohort.
- Request counts per time bucket; p99 over 20 requests is very noisy.
- Background conditions, bursts/peak load, and warm-up elapsed.

**Simpson's paradox:** service-wide latency can rise solely because the share of a slow route increased, even while every individual route stayed unchanged. Check route mix before claiming a JVM regression.

### 6.4. Changing observation config changes the output

Recording A uses `default.jfc`, while B uses `profile.jfc` or a different custom threshold; raw counts and stack sample counts are not directly comparable. If forced to compare, use only events with compatible settings/coverage, or capture a control recording with **identical event settings**. Record profiling overhead so observation itself does not distort the workload.

## 7. A sequential, reproducible verification workflow

### Step 1 — Capture the finding verbatim

Save the analyzer output: rule name, tool version, alert level/score, description, thread/method/class if listed, formula/threshold if known, time interval, sample count, and detail page URL/path. Do not immediately rephrase it as root cause.

### Step 2 — Define the business/technical question

For example: "During 10:03–10:05, checkout p99 exceeded 500 ms against a 200 ms SLO; is monitor contention accounting for most of the critical-path time?" A concrete question beats "What is wrong in JFR?"

### Step 3 — Check recording quality

Verify the file opens, matches the right JVM, covers the timestamps, has data for relevant events, uses suitable sampling/thresholds, has inspectable stack traces, and has no missing chunks or retention gaps. If gaps exist, document limitations before concluding.

### Step 4 — Trace back to raw events and recompute units

For a GC rule: open GC/pause events, check time span, duration, and cause; cross-check GC logs if available. For monitor contention: check event duration, lock class, thread, and stack; do not merely count events. For CPU: check sample counts, period, process CPU, and GC/JIT/native activity. If the tool does not publish its formula, present your own calculation with an explicit method.

### Step 5 — Align timelines with the application and resources

Using a common timezone/UTC, align JFR with APM p95/p99, error rate, request counts, thread/queue pools, service dependencies, CPU throttling, RSS, and GC logs. Find the **exact onset** where metrics degraded and check whether event durations are large enough to explain the impact.

### Step 6 — Check load context and competing hypotheses

Compare request mix, throughput, payloads, deployments, warm-up, caches, CPU/memory quotas, replicas, and service dependencies. Formulate at least one competing hypothesis: slow database, low CPU quota, network, queue saturation, memory leak, batch job, or application bug. What evidence would falsify each hypothesis?

### Step 7 — Assign confidence levels and decide next action

Label findings "observed," "likely," or "unverified" based on evidence. If sufficient, design a small experiment with guardrails; if insufficient, specify **what to capture**, for how long, and where. Avoid tuning CPU/GC/heap/locking from a single red warning.

**Practical rule:** Every recommendation must follow **finding → raw evidence → workload context → symptom → hypothesis → verification test**.

## 8. Command-line tools: cross-check yourself instead of reading only summaries

Examples use JDK 21's `jfr` command on an existing `recording.jfr` file where you have read access. On JDK 17, confirm available subcommands with `jfr help` since tools and versions differ. None of the commands below invent missing data in the file.

### 8.1. Inspect file contents and event inventory

~~~bash
jfr --version
jfr summary recording.jfr
jfr metadata recording.jfr
jfr --help print
~~~

- **summary:** time span, size, event types, and recorded counts; event count is the count in the file, not every runtime operation.
- **metadata:** describes event types and fields/schemas; an event type existing in metadata does not prove instances exist.
- **help:** verifies syntax on the installed JDK, avoiding newer options on older JDKs.

If the file is very large, do not print all events to the console; filter, export JSON selectively, or analyze in JMC. JFR files can contain sensitive operational info.

### 8.2. Inspect relevant raw events

~~~bash
jfr print --events jdk.GarbageCollection recording.jfr
jfr print --events jdk.CPULoad recording.jfr
jfr print --events jdk.JavaMonitorEnter recording.jfr
jfr print --events jdk.ThreadPark recording.jfr
jfr print --events jdk.ExecutionSample recording.jfr
~~~

These commands display matching events **if recorded**. Empty output does not prove the service had zero GC/CPU/locks; check settings, recording span, thresholds, and `summary`.

To get structured output for verification scripts:

~~~bash
jfr print --json --events jdk.GarbageCollection recording.jfr
~~~

JSON structure depends on event/JDK schema; do not hardcode assumptions that every vendor and version shares identical fields. To build a timeline table, parse JSON, extract `startTime`/`duration` appropriate for the event type, and join with APM metrics by timestamp. In production environments, export selectively so sensitive data is not exposed.

### 8.3. When using JMC

You can follow this sequence:

1. Open the right recording and review **Automated Analysis Results** (location/label may vary by version).
2. Select a warning of interest and record the rule name and logic/threshold if shown.
3. Follow links to the underlying page: GC, Memory, Threads, Java Application, Code/Hot Methods, I/O, or corresponding events.
4. Select the time range matching the SLO violation; compare event histograms and timelines.
5. Open stack traces/call trees and thread details to see where events originated, remembering the stack where an event fired is not necessarily what retains an object or the upstream cause.
6. Record event counts, sample counts, thresholds, and evidence reproducible via CLI/API.
7. Compare against non-JFR metrics, then update your assessment.

Tab names, rules, and layouts depend on the JMC version. Automated rules do not replace understanding JFR event semantics.

## 9. Example 1 — Hot Methods warning while the app is mostly waiting

An analyzer lists method A at 60% of execution samples and concludes "method A is causing request latency."

**Cross-check steps:**
- Check total sample count and profiling duration. With only 10 samples, 6 samples in A cannot represent thousands of requests.
- Check process CPU / `jdk.CPULoad`. If CPU is low, method A may hold a large share **of very little CPU time**.
- Trace slow requests; if most wall-clock time is socket reads to a DB or queue waiting, CPU hotspot A cannot explain total latency.
- Check for native code, GC/JIT activity, missing sampling coverage, or other threads doing work.
- Compare two windows with identical workload and settings to see if A grew in **absolute level** and impacted p99.

**Sound conclusion:** "A stands out in execution samples; it is not yet proven that A dominates end-to-end latency." Only if A actually consumes heavy CPU while the service is CPU-bound is optimizing A a worthwhile hypothesis to test.

**Common error:** turning 60% of samples into "60% of requests were slowed by A" or "60% of user wait time was spent in A." Those have different denominators.

## 10. Example 2 — GC rule warns, yet request timeouts come from downstream

Illustrative scenario (hypothetical numbers):

| Metric | 10:00–10:05 baseline | 10:10–10:15 incident |
| --- | --- | --- |
| Checkout p99 | 120 ms | 750 ms |
| Requests/s | 400 | 420 |
| Total GC pause | 400 ms/5 min | 650 ms/5 min |
| Full GC | 0 | 0 |
| DB query p99 | 85 ms | 680 ms |
| CPU throttling | Negligible | Negligible |

JMC flags an increase in young GC count. Yet total pause time rose by only 250 ms **over five minutes**, while many requests experienced rising database p99. Check whether GC pause timestamps overlap slow requests; totals alone cannot allocate latency to individual requests. DB latency and traces are the stronger hypothesis to investigate first.

**Do not conclude GC is harmless just from a small total:** a single long pause overlapping a batch of requests can still hurt tail latency. Equally, never conclude "GC is the root cause" just because a dashboard colored GC red.

If GC logs show multi-hundred-ms pauses **right when** p99 spikes while DB traces stay flat, the hypothesis shifts. Reasoning must follow evidence, not the order of tool warnings.

## 11. Example 3 — Allocation samples rise because load rose

Two recordings with identical settings, 10 minutes each:

| Measurement | Baseline | Peak |
| --- | --- | --- |
| Throughput | 200 req/s | 400 req/s |
| Total requests | 120,000 | 240,000 |
| Allocation sample count | 1,000 | 2,200 |
| GC CPU or pauses | Measured separately | Measured separately |
| Route mix, payloads | Assumed similar | Must verify |

Looking solely at 1,000 → 2,200 samples, a tool may flag "higher allocation." Yet load also doubled. Samples per request rose roughly 10% **under comparable sampling conditions**; if settings, sample periods, event weights, or workload mix differed, even that ratio can mislead.

To conclude on allocation efficiency, prefer estimated bytes/request from tools that account for sampling weights, plus allocation profiles of code paths, route/payload mix, and GC/CPU. **Sample counts do not automatically convert into created object counts or actual bytes.**

A retention/leak claim also requires proof of objects **held** after GC and heap growth/dominator paths; heavy allocation pressure does not mean a memory leak.

## 12. Example 4 — Monitor contention rises without necessarily being the bottleneck

An automated rule warns of many `jdk.JavaMonitorEnter` events on a `synchronized` block. Ask:

1. What is the event capture threshold? A recording with a 5 ms threshold will have very different counts from a 20 ms one.
2. How many threads participate, which stacks, which lock class/object, and what is total wait time on the critical path?
3. Do waits coincide with request latency spikes or happen in background batches?
4. How did request RPS, concurrency, and queue length change?
5. Are there `ReentrantLock`, thread parking, or connection pool waits outside `JavaMonitorEnter`?
6. What happens if contention drops? Does p99 drop, CPU rise, or throughput change?

80 events/s in a 50,000 req/s system carries a different weight than 80 events/s at 100 req/s. Still, check durations: a few very long blocking events can stall a critical path. You need **rate, duration, target, timeline, and impact**.

## 13. Example 5 — Low CPU, many waiting threads, rule says "application idle"

Some tools treat low CPU usage and few execution samples as a signal that the workload is doing nothing. Yet checkout p99 can still be high because:

- Threads are waiting on databases/sockets, network, mutexes, or connection pools.
- Queues grow and requests wait unserved by workers.
- Containers suffer burst CPU throttling; average CPU hides the throttled moments.
- Requests/second drop due to upstream backpressure while remaining requests are very slow.

Compare thread states/park/socket events against APM traces, pool metrics, upstream/downstream latency, and request counts; distinguish **no work** from **work unable to run**. An "idle" rule may be true under CPU-utilization definitions while false as a "healthy application" conclusion.

## 14. Java 17+ example: normalizing and comparing aggregated evidence

The following program **does not read JFR files** and does not pretend to deduce root cause. It demonstrates the mandatory check before comparing two automated results: normalizing selected event counts by requests and GC pauses per minute while keeping p99 as the target metric.

Suppose both intervals are 600 seconds long with identical JDK/collector/event settings/thresholds and no missing critical data. Numbers are purely for practicing the method.

Save as **EvidenceRates.java**:

~~~java
import java.util.Locale;

public class EvidenceRates {
    record Window(
            String name,
            long seconds,
            long requests,
            long monitorEvents,
            long gcPauseMillis,
            double p99Millis) {

        double requestsPerSecond() {
            return (double) requests / seconds;
        }

        double monitorEventsPerTenThousandRequests() {
            return monitorEvents * 10_000.0 / requests;
        }

        double gcPauseMillisPerMinute() {
            return gcPauseMillis * 60.0 / seconds;
        }
    }

    static void show(Window window) {
        System.out.printf(
                Locale.ROOT,
                "%s: rps=%.0f, monitor/10k=%.1f, GC-pause-ms/min=%.0f, p99=%.0fms%n",
                window.name(),
                window.requestsPerSecond(),
                window.monitorEventsPerTenThousandRequests(),
                window.gcPauseMillisPerMinute(),
                window.p99Millis());
    }

    public static void main(String[] args) {
        Window baseline = new Window("baseline", 600, 120_000, 24, 900, 110);
        Window incident = new Window("incident", 600, 240_000, 80, 1_200, 330);

        show(baseline);
        show(incident);
    }
}
~~~

Compile and run with JDK 17+:

~~~bash
javac EvidenceRates.java
java EvidenceRates
~~~

Exact stdout of the program:

~~~text
baseline: rps=200, monitor/10k=2.0, GC-pause-ms/min=90, p99=110ms
incident: rps=400, monitor/10k=3.3, GC-pause-ms/min=120, p99=330ms
~~~

Meaning:

- Raw monitor events rose from 24 to 80, while requests doubled. Normalizing shows 2.0 → 3.3 events/10,000 requests, though **event duration and critical-path involvement remain unknown**.
- Total GC pause rose from 900 to 1,200 ms over 10 minutes, i.e., 90 → 120 ms/min. This alone does not show whether pauses coincided with p99 spikes.
- p99 rose from 110 to 330 ms, yet **you cannot attribute the 3x latency jump to monitors or GC** from aggregate numbers alone.
- Before trusting the monitor/10k rate, verify identical event type, threshold, and request mix; if events were sampled/filtered, counts may not be representative.
- To act, drill down into raw events and timestamps, traces, CPU/pools, pinpoint objects/stacks, and run a baseline under equal load or a controlled experiment.

**Limitations of this illustration:** 10-minute aggregates can hide incident timing; non-overlapping events are not guaranteed; "GC pause ms" must come from a proper pause source without double-counting. The program merely performs explicit arithmetic and does not validate input data semantics.

## 15. When results from different sources conflict

Contradictions are a signal to inspect your observation sources:

| Automated finding | Other evidence | Appropriate reading |
| --- | --- | --- |
| High CPU hotspot | Low process CPU | Check sample count, capture timing, thread filter, and idle time |
| GC pauses cause p99 | p99 spikes do not overlap pauses | Cause not proven; check DB/queues/network |
| Allocation hotspot surges | RPS/payload grew proportionally | Normalize by work; inspect bytes/request and GC consequences |
| No lock contention | JFR disabled lock events / threshold too high | Conclude "not observed," not "absent" |
| Memory leak | Post-GC heap flat under equal workload | Need object retention trends/heap dump before calling it a leak |
| Slow File I/O | Most requests wait on remote DB | Follow the critical path; do not optimize I/O outside impact scope |
| "OK" or no warnings | JFR contains only 30 seconds of idle time | Insufficient coverage; do not extrapolate to peak |
| Many thread samples in A | p99 rises when downstream B slows | Re-frame hypothesis around distributed traces and timestamps |

Resolution steps:

1. Check whether each source measures the right **unit** and **scope**.
2. Check clock sync, time windows, sampling/thresholds, aggregations, and missing data.
3. Identify the most direct source for the question: latency → traces/SLO; GC pauses → pause events/GC logs; code CPU → CPU samples plus process CPU; memory retention → heap trends/dumps.
4. Record why sources disagree and what extra evidence is needed; never discard inconvenient data.
5. If data still cannot adjudicate, conclude **inconclusive** rather than inserting a confident guess.

## 16. Evidence levels and action decisions

Use this practical hierarchy rather than treating it as a universal statistical law:

| Level | What exists | Decision |
| --- | --- | --- |
| **Signal** | A warning or AI summary lacking citations | Form a hypothesis; do not tune yet |
| **Sourced observation** | Raw event + capture config + verified time window | Investigate the specific resource/thread/method |
| **Plausible correlation** | JFR events align with symptoms, backed by workload/SLO/traces | Prioritize a verification test; keep competing hypotheses |
| **Confirmatory experiment** | Baseline and candidate under matched conditions, one primary variable, repeatable results, no guardrail breaches | Basis for controlled rollout |
| **Insufficient data** | Recording lacks events/time range, settings differ, or workload context missing | Capture additional data and state limitations clearly |

A high-scoring rule may still be just a "signal" if raw evidence is missing. A low-scoring rule can still be critical if a handful of events sit on a key transaction path and cause timeouts. Prioritize by **SLO impact and evidence quality**, not UI color alone.

## 17. Verifying with controlled experiments

Suppose you suspect queue/lock contention after inspecting JFR. Design a small change and measure:

1. **Lock down background conditions:** build, JDK, JVM flags/GC, pool sizes other than the test variable, CPU/memory limits, replica count, dependencies, request mix, and payloads.
2. **State a falsifiable hypothesis:** "Shortening the `synchronized` critical section will reduce wait time on stack X at 800 RPS peak and improve checkout p99."
3. **Measure baseline:** identical recording settings, event thresholds, post-warm-up window, p95/p99, error rate, throughput, CPU/RSS, GC, thread/queue metrics, and monitor event durations.
4. **Change one primary variable:** the relevant code or pool/config; avoid changing GC and infrastructure at the same time.
5. **Run identical load repeatedly:** multiple trials, avoiding mixing bursts with steady state, and watch for regressions.
6. **Verify the mechanism:** contention events on stack X drop in raw JFR **and** p99/throughput improve accordingly. If event count dropped only because thresholds changed or load fell, that is not success.
7. **Guardrails and rollback:** SLOs, error rates, CPU/GC/memory footprint, downstream pressure. If one metric looks prettier while system safety degrades, roll back.
8. **Record confidence-calibrated conclusions:** keep the change only when evidence repeats and cost/benefit makes sense.

For GC/heap tuning, the same logic applies: understand live set, allocation pressure, pause timeline, and container memory headroom before picking a collector or flags. An automated "increase heap" suggestion when a process is already near its cgroup limit can trigger OOMKilled.

## 18. Auditable analysis report template

You can use the following Markdown for an investigation ticket. It is a **framework of real facts to fill in during an incident**, not a pre-baked conclusion:

~~~text
# JFR finding cross-check

Service / instance / PID:
Build / JDK / collector / JVM flags:
Recording file / SHA-256 (if preserving evidence):
Recording time range / timezone:
JFR settings / event thresholds / sampling:
Incident window and SLO violation:
Traffic RPS / route mix / concurrency / payload:
Automated tool version / rule name / score:
Original recommendation:

Raw event evidence:
- Event types:
- Event count / duration / sample count:
- Affected thread/method/stack:
- Exact timestamps / time window:
- Missing data / coverage limits:

Independent evidence:
- APM traces, p95/p99, errors:
- CPU/RSS/throttling, GC logs, thread/pool metrics:
- Deployment, warm-up, downstream events:

Alternative hypotheses / what would falsify each:
Current confidence / why:
Decision: investigate / controlled experiment / defer
Candidate change / measurement / guardrails / rollback:
Follow-up recording and outcome:
~~~

Do not write this template into a JFR file; it is a log for documenting the investigation process. When sharing `.jfr` files or stack traces, check for sensitive data like paths, class names, thread names, custom event payloads, and application-logged tokens.

## 19. Checklist for evaluating an automated finding

- [ ] I have the exact rule/finding name, tool version, and time interval evaluated by the rule.
- [ ] I know whether the finding is a raw event, derived metric, heuristic, or causal guess.
- [ ] I have the exact JFR file from the affected process/instance/version.
- [ ] I verified the recording covers pre–during–post incident intervals, or documented the gap.
- [ ] I know whether event types were enabled, their sampling/thresholds, and whether samples/stacks are sufficient.
- [ ] I inspected raw event timestamps, durations, threads/methods/stacks, and how the tool aggregated them.
- [ ] I did not turn "no events" into "no activity" when coverage was insufficient.
- [ ] I aligned timelines with APM traces, p95/p99, error rates, GC logs, and OS/cgroup metrics.
- [ ] I recorded workload: RPS, request mix, payloads, concurrency, warm-up, batches/caches/deploys.
- [ ] I compared normalized rates and did not double-count nested events/phases or confuse samples with actual counts.
- [ ] I considered at least one competing hypothesis and one condition that could falsify the automated recommendation.
- [ ] I only propose code/config changes when a test confirms SLO impact with guardrails/rollback.
- [ ] I clearly state confidence levels and gaps rather than claiming a certain root cause on insufficient data.

## 20. Conclusion

**Automated analysis helps decide where to look first; raw JFR evidence and load context determine how far you can trust a conclusion.** The right diagnostic sequence is:

**Automated finding → verify recording and event coverage → recompute metrics on the exact window → align SLO/trace/OS timelines → normalize workload → rule out competing hypotheses → controlled experiment → scoped conclusion.**

When a tool emits an appealing warning without pinning down the exact events, exact timestamps, exact resource contention, and user-facing impact, the right move is to **collect more evidence**. Conversely, when raw events, application traces, and workload context all point to the same mechanism and an experiment confirms improvement, automated analysis has fulfilled its role: shortening the path from observation to a testable engineering decision.

### References

- Oracle JDK 21 — `jfr` command (`summary`, `metadata`, `print`, `view`): https://docs.oracle.com/en/java/javase/21/docs/specs/man/jfr.html
- Oracle Java 17 — Troubleshoot Performance Issues Using JFR: https://docs.oracle.com/en/java/javase/17/troubleshoot/troubleshoot-performance-issues-using-jfr.html
- Oracle JDK 21 — `jcmd`/JFR controls: https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html
- OpenJDK Mission Control project: https://github.com/openjdk/jmc
