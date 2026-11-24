# 2.5 Choosing Sampling Intervals, Observation Duration, and Incident Windows

## Learning Objectives

In Java/JVM diagnostics, a measurement tool can function properly while still yielding wrong conclusions because of **sampling too sparsely**, **observing too briefly**, or **picking a time window that misses when the incident actually happened**. This lesson helps you design measurements with sufficient resolution and representativeness, bounded overhead, and preserved evidence before, during, and after an incident.

After this lesson, you will be able to:

- Distinguish sampling interval, metric collection/export cadence, aggregation window, chart/query step, observation duration, and incident window.
- Estimate how many data points/statistical samples are needed to answer a question, and understand the effects of dropped samples and misaligned sampling times.
- Select appropriate settings for metrics, logs/traces, JFR, CPU/allocation profilers, thread dumps, and fleeting incidents.
- Design **before – during – after** windows around an incident to compare against baseline, verify hypotheses, and confirm recovery.
- Record sufficient timestamps, units, configurations, and measurement limitations so others can reproduce and evaluate the conclusion.

## 1. Before Picking Numbers: Understand What You Are Measuring

Separate these concepts clearly; calling all of them "sampling interval" causes confusion:

| Concept | Symbol Used Here | Meaning | Example |
| --- | --- | --- | --- |
| **Sample interval** | `Δs` | Interval between two consecutive value/stack samples by design | CPU sampling every 10 ms, gauge read every 1 s |
| **Scrape/collection/export interval** | `Δc` | Interval at which the system pulls or pushes data from the process to observability storage | Prometheus scrape every 15 s; exporter pushes metrics every 30 s |
| **Aggregation window** | `Wagg` | Interval over which events/samples are aggregated into rate, average, max, histogram, percentile | `rate(...[5m])`; p95 computed over 5 minutes |
| **Chart/query step** | `Δq` | Spacing between points plotted on a dashboard or returned by a query | Chart displays one point every 60 s |
| **Observation duration** | `Tobs` | Total start-to-end span of collecting/retaining evidence | 2-minute JFR recording; 6-hour heap monitoring |
| **Incident window** | `Winc` | Time range containing the incident plus baseline/recovery segments to compare | From 10:22:14 to 10:23:02 UTC, with before/after |

A **gauge** metric may only retain the last value at collection time; a **counter** is a cumulative total (requiring delta/rate over time); a **histogram** aggregates multiple observations between exports while preserving bucket distribution. With **event recording** (logs, traces, JFR events), raw records carry their own timestamps, so they are not equivalent to polling an instantaneous value periodically.

### Actual Measurement Pipeline

```text
Application event / state
          |
          v
Instrumentation, polling, or sampling [Δs / event-driven]
          |
          v
Aggregate by interval, rate, histogram, drop/filter [Wagg]
          |
          v
Buffer -> collector -> storage / retention [Δc, lag]
          |
          v
Query, downsampling, dashboard [Δq]
          |
          v
Conclusion about timing and root cause
```

If an incident lasts 8 seconds, the application can still emit thousands of requests. A latency histogram updated **per request** can retain the count of slow requests even if the system exports histograms every 30 seconds. Conversely, a `last_request_duration` gauge polled once per minute can miss that entire 8-second event. Likewise, a dashboard using `Δq = 5m` can smear out a spike that raw data at 15 s step still shows.

**Key takeaway:** increasing scrape frequency does not recover detail already aggregated away upstream; collecting at high resolution yet querying at low resolution can also hide signals. Inspect **from measurement point to display**, not just dashboard settings.

## 2. Choose Sampling Interval Based on Signal Lifetime

The first step is stating the **diagnostic question** and **characteristic duration of the phenomenon**.

| Situation | Signal Needed | Method / Resolution Direction | What to Avoid |
| --- | --- | --- | --- |
| JVM CPU stays elevated for 10–20 minutes | Process CPU, runnable threads, throughput | Metrics at a few seconds to tens of seconds usually suffice for trends; profile while CPU is high to find hotspots | Relying on a 1-hour average to conclude there was no peak |
| GC pauses of tens to hundreds of ms | GC pause duration and timestamp | **JFR/GC events or pause histograms**, since events are recorded when they occur | Looking only at a heap gauge scraped every 30 s and inferring no pauses |
| Bursts of slow requests lasting 5–10 s | Request latency, counts, traces, queues, pools | Per-request updated histograms/counters, trace/error spans, and short-step dashboards | Scraping a `last` gauge every 1 minute |
| Lock contention recurring over 1–2 minutes | Thread states, JFR lock/park events, blocked time | Recording covering the stall period; capture multiple spaced thread snapshots within overhead bounds | Reading one thread dump and immediately blaming a cause |
| CPU hotspot only during a 45 s batch job | CPU samples during the batch phase | Start recording before the job runs; use a profiler with frequency and duration fit for the 45 s phase | Profiling for 5 minutes after the batch finishes |
| Memory grows gradually over hours | Live heap, RSS, allocation, GC, workload | Track multiple load/GC cycles over hours; compare matching system states | Concluding a leak from two heap snapshots seconds apart |

For a signal whose shortest duration to detect is `τ`, an **initial rule-of-thumb estimate** for polling instantaneous values is picking `Δs` several times smaller than `τ` (for instance `Δs ≤ τ/4`) to try catching a few points during one occurrence. This is **not a guarantee**: clock skew, jitter, collector overload, dropped samples, and smoothing can still mask the incident. Periodic polling can also suffer from **aliasing**: recurring oscillations synchronized with the polling cadence make data look artificially steady.

Do not interpret the Nyquist theorem as a guarantee that "scraping at twice the failure rate catches failures"; Nyquist applies to continuous band-limited signals under proper sampling conditions, not automatically to brief spikes, counters, sampled traces, or aperiodic events. If a rare phenomenon lasts only milliseconds, **event-based instrumentation** or histograms are usually far better than trying to scrape every gauge every millisecond.

### Selection Rules by Data Type

**Gauge:** sample fast enough relative to the rate of change you need to see, and never treat gaps between points as proof of no spike. A gauge retaining "last value" cannot reconstruct the maximum that occurred inside the interval.

**Counter:** collect cumulative counters and compute change over actual elapsed time; check for counter resets on restarts, dropped samples, and collection intervals. Example: if a counter rises from 1,000 to 1,180 in 30 s, the average rate over **that interval** is `180/30 = 6 events/s`; never claim every single second in that interval had exactly 6 events.

**Histogram/summary:** verify how many events were actually recorded into the distribution and the aggregation scope. For latency, p99 needs enough requests in the window; with just a few requests, p99 cannot justify long-term stability claims. Per-minute p95/p99 values **cannot be arithmetically averaged** to get a 10-minute p95/p99; merge compatible distributions or recompute from raw data.

**Logs/traces:** mostly timestamped events; besides `Δc`, check log sampling, head/tail trace sampling, dropped spans, buffering, clock skew, and export lag. If an error is very rare and only 1% of traces are randomly sampled, you might see zero error traces even when an incident occurred. Error-retention or tail-sampling policies must balance overhead and decision delay.

**Profiler/JFR:** distinguish *stack sampling period* from *recording duration* and *per-event thresholds/periods*. Many JFR events are recorded on event occurrence per config; there is no single `Δs` for all JFR event types. A thread dump is a state snapshot at invocation time, not automatically a statistical profiling sample series.

## 3. Choose Observation Duration for Representative Data

A rough approximation for regular polling is:

```text
Expected N ≈ Tobs / Δs     (ignoring boundary endpoints)
Tobs ≈ target N × Δs
```

This is the **expected sample count**, not the actual valid samples received. Count actual samples when timeouts, pauses, misses, backpressure, restarts, or state-filtered sampling occur.

For example, `Δs = 15 s` and `Tobs = 5 minutes` give roughly `20` polling intervals; exact point counts depend on scheduling. That suffices to see short-term trends of a steady gauge, **not to assert** you caught a 1-second spike. A chart line with 20 points also does not mean 20 requests: each point could summarize thousands of requests.

For a profiler, if the tool **actually collects 100 stack samples/second** for 60 seconds, the nominal sample count is ~`6,000`. Actual captured samples may be fewer due to idle threads, sampling lag, event filters, and system load. When a method makes up a very small fraction of samples, extend duration/align with the workload or switch tools; endlessly cranking up sample rate does not substitute for representative data and can raise overhead.

### Three Factors Governing Duration

1. **Cover the phenomenon lifecycle:** a 45-second job needs capture starting before the job runs, spanning the job, and a tail afterward; a memory leak needs observation across multiple GC/workload cycles, potentially spanning hours. Choose `Tobs` based on application cycles, not one universal number.
2. **Enough data to compare:** capture pre-incident baseline, in-incident window, and post-intervention window; windows should share comparable traffic, routes, versions, and load conditions when comparing performance.
3. **Bound cost:** recordings, profiles, logs, and traces consume CPU/I/O/memory/disk/network and may contain sensitive data. Use appropriate sampling/retention, predefine stop conditions, and avoid running heavy profiling indefinitely in hopes of catching a rare bug.

For example, if a bug happens once every 40 minutes on average yet lasts only 4 seconds, running a heavy 2-minute profiler has a high miss probability. A more practical approach is lightweight background telemetry, **a rolling buffer retaining recent history**, and a trigger capturing high-detail evidence when error rate, latency, or a log pattern crosses a threshold. Never say "could not reproduce" merely because your measurement window did not cover the opportunity for the error to occur.

## 4. Incident Window: Capture Enough Before, During, and After

Define timestamps clearly in **a single consistent timezone** (prefer storing UTC in data):

- `t_detect`: when systems/humans **detected** the incident; usually later than actual onset.
- `t_start`: earliest evidence-backed sign of the incident, possibly an estimate with stated uncertainty.
- `t_end`: when symptoms ended per defined criteria; differs from alert resolution if alerts have delay/hysteresis.
- `t_change`: when a new build was deployed, config changed, or test ran; mark separately so it is not confused with incident onset.

Suggested interval split:

```text
t_pre              t_start             t_end               t_post
|------------------|===================|-------------------|
       BASELINE          INCIDENT             RECOVERY
     pre-incident       in-incident         post / post-change
```

Example: a latency spike is observed during `10:22:14Z–10:23:02Z` (48 seconds). You might choose baseline `10:17:00Z–10:22:14Z`, incident `10:22:14Z–10:23:02Z`, recovery `10:23:02Z–10:28:00Z`. This is a **methodological example**, not a 5-minute rule for every system.

Intervals should be long enough to see background trends, nearby GC/workload behavior, and verify recovery, yet narrow enough not to dilute a 48-second incident into a 1-hour average. For windowed queries, check exactly which timestamps belong to the interval; the usual convention is `[start, end)`. If a `rate(...[5m])` point at 10:25 covers data from 10:20 to 10:25, it is **not** a measurement strictly at 10:25.

### What Can Skew the Window?

- **Clock skew** across nodes: logs, traces, DB, and metrics may have timestamps off by seconds; comparison requires NTP sync and recording any known skew.
- **Ingest/export lag:** an event occurs at 10:22 yet appears on the dashboard at 10:24; window by *event time* if supported, rather than equating display time with occurrence time.
- **Scrape phase offset:** one process is scraped at second 02, another node at second 11; "the same minute point" actually spans different instants.
- **Rolling/window smoothing:** a "5m average" graph can stay elevated after the incident ended or lag behind the spike's true start.
- **Restarts/GC/deployments:** counter resets, instance replacement, or JIT warm-up can put before and after samples in different populations.
- **Missing data:** gaps must be flagged as *missing/no data*, never turned into zeros or treated as healthy behavior.

When `t_start` is uncertain, record the uncertainty range, e.g., "occurred within 10:21:45Z–10:22:14Z", and widen evidence extraction accordingly. Notably, data **prior to detection** is often more valuable than turning on a profiler after the incident has already passed.

## 5. Before, During, and After: Design Measurement by Question

### A. When Monitoring Normal Health

Keep low-cost metrics long enough to see trends: request rate, error rate, duration distribution, CPU, heap/RSS, GC, thread pools, queues, and saturation. A 10–30 second interval can be a starting trial for some systems, yet must be tuned for SLAs, spike frequency, exporter cost, cardinality, and storage capacity. For sub-second behavior, use events/histograms or appropriate tracing.

Match dashboard `Δq` to `Δc`, and avoid smooth interpolation lines that trick readers into thinking interpolated points are real measurements. Every chart should clarify **units**, **aggregation interval**, **sampling interval**, and **aggregation function**.

### B. When Profiling a Specific Load Phase

Start recording **before the load phase arrives**, cover warm-up/steady-state or keep each phase cleanly separated, record timestamps of the target phase, and fix stop time. If the goal is a steady-state bottleneck, do not mix startup JIT/class loading into the conclusion. If the goal is slow startup, then warm-up itself is what must be measured.

Correlate the profile with process CPU, throughput, and latency over the same interval. A CPU profile showing few samples in a method does not prove that method isn't slow due to blocking, I/O, or locks; you may need wall-clock/lock events.

### C. When Tracing a Rare Incident Detected Late

Maintain a lightweight continuous mechanism capable of **retaining a few minutes before a trigger** (metrics with adequate retention, structured logging, rolling JFR buffer with suitable `maxage`/`maxsize`). When an alert fires: mark `t_detect`, extract pre-trigger data, capture high-resolution data if safe, then stop the extra capture.

You cannot rewind time to recover dropped stack samples or raw requests that were never recorded. Enabling a profiler after the service stops being slow only observes the *post-incident* state; explicitly document evidence limits.

### D. When Measuring the Effect of a Change

Compare `W_before` and `W_after` windows with traffic, routes, versions, caches, datasets, and network conditions as equivalent as possible. Record change timestamp and allow a stabilization period after the change before evaluating results (depending on cache warm-up, rollout, JIT). If before has 10,000 requests and after has 12, post-change latency percentiles are very unstable; never compare two p99 numbers alone and declare improvement.

If workload has daily/weekly cycles, "the 5 minutes right before the incident" may be unrepresentative: include the corresponding time window from the prior day or same-traffic-profile baseline to avoid comparing apples to oranges.

## 6. Distinguish Metric Windows from Actual Measured Events

Suppose a service records **every request** into a classic histogram `http_request_duration_seconds`. A 15-second scrape does not mean the service only observed one request every 15 seconds; the histogram buckets/count/sum accumulated all observations across the interval.

The PromQL examples below use **hypothetical metric names** to illustrate concepts (real environments may use different names and labels):

```promql
sum by (route) (rate(http_request_duration_seconds_count[5m]))
```

This is the approximate request rate per `route` over a 5-minute window, not the request count at the exact instant a chart point is drawn. To know sample size in an interval, inspect the corresponding counter increase:

```promql
sum by (route) (increase(http_request_duration_seconds_count[5m]))
```

Estimating p95 from **classic histogram buckets**:

```promql
histogram_quantile(
  0.95,
  sum by (le, route) (
    rate(http_request_duration_seconds_bucket[5m])
  )
)
```

- `[5m]` is the **rate window**, not the scrape interval. Two chart points 30 seconds apart use **two heavily overlapping 5-minute windows**; do not treat them as independent.
- `histogram_quantile` is an estimate from buckets subject to bucket-width error; do not turn an "estimate" into an exact per-request claim. Native histogram configurations have different query syntax than this classic-bucket example.
- With low sample counts, error ratios or percentiles fluctuate wildly. Record **observation count**, not just percentiles.
- Never average per-instance `p95` values to get cluster-wide `p95`; sum compatible bucket counts before computing the quantile, provided label/bucket schemas match.
- On counter resets from restarts or prolonged missing data, inspect rate/increase function semantics, actual sample rate, and session metadata; never use raw negative deltas to infer negative throughput.

If you store only **average latency** per 1-minute window, you cannot recover lost p99. To catch tail-latency faults, measure distributions where events occur (histograms, suitable traces) and pick windows with enough requests.

## 7. Java 17+ Example: A Spike Disappears in Sparse Snapshots

The exercise below generates **completely deterministic synthetic data** consisting of one latency measurement per second over 60 seconds. Every second is `100 ms` except second `27` which is `1900 ms`. We compare:

- `snapshot`: inspecting only the value at the start of each 10-second period, like a sparsely polled gauge.
- `avg`: mean across all 10 events occurring in the period.
- `max`: maximum value in that exact period.

Create **`SamplingWindowDemo.java`**:

```java
import java.util.Locale;

public class SamplingWindowDemo {
    private static long latencyAt(int second) {
        return second == 27 ? 1900L : 100L;
    }

    public static void main(String[] args) {
        for (int start = 0; start < 60; start += 10) {
            long sum = 0;
            long max = Long.MIN_VALUE;

            for (int second = start; second < start + 10; second++) {
                long latency = latencyAt(second);
                sum += latency;
                max = Math.max(max, latency);
            }

            System.out.printf(Locale.ROOT,
                    "[%02d,%02d): snapshot=%d ms | avg=%.0f ms | max=%d ms%n",
                    start, start + 10, latencyAt(start), sum / 10.0, max);
        }
    }
}
```

Compile and run with JDK 17 or higher:

```bash
javac SamplingWindowDemo.java
java SamplingWindowDemo
```

**Exact stdout:**

```text
[00,10): snapshot=100 ms | avg=100 ms | max=100 ms
[10,20): snapshot=100 ms | avg=100 ms | max=100 ms
[20,30): snapshot=100 ms | avg=280 ms | max=1900 ms
[30,40): snapshot=100 ms | avg=100 ms | max=100 ms
[40,50): snapshot=100 ms | avg=100 ms | max=100 ms
[50,60): snapshot=100 ms | avg=100 ms | max=100 ms
```

Explanation: in window `[20,30)`, there are 9 events of `100 ms` and 1 event of `1900 ms`; the mean is `(9×100 + 1900)/10 = 280 ms`. The snapshot at `t=20 s` sees only `100 ms`, missing the spike. Average shows a shift yet **does not reflect the severity of the slowest request**; max preserves the peak. In production, to know the fraction and distribution of slow requests, collect histograms/counters with sufficient counts; a single max value can also be dominated by one outlier.

What the demo **does not simulate**: jitter, real wall clocks, concurrency, missing samples, export lag, bucket-interpolated percentiles, and measurement overhead. It is a minimal model distinguishing **instantaneous snapshots** from **statistics over all events in a window**.

### Clocks and Durations in Real Code

When building instrumentation yourself, use `System.nanoTime()` to compute **durations within the same process**, and `Instant.now()`/standard timestamps to correlate events across systems. Measuring duration by subtracting `Instant.now()` can be distorted by wall-clock adjustments; conversely, raw `System.nanoTime()` values have no meaning as absolute timestamps across machines/processes.

```java
// Illustrative snippet placed around a measured operation; not a standalone program.
long startedNanos = System.nanoTime();
java.time.Instant eventTimeUtc = java.time.Instant.now();

performOperation();  // Actual application method

long elapsedNanos = System.nanoTime() - startedNanos;
double elapsedMillis = elapsedNanos / 1_000_000.0;
```

For schedulers/pollers, record both **scheduled time** and **actual time** of each sample. If the nominal interval is 1 s yet a GC pause stretches one gap to 4 s, compute rate over the **actual 4 s** and flag the gap; do not force samples into "uniform 1 s" without evidence. When reading `nanoTime`, ensure both readings occur in the same JVM and take differences; never compare two raw values from two different JVMs.

## 8. JFR and JVM Tools: Aligning Recordings to Windows

With JDK 21, `jcmd` can start/dump/stop Java Flight Recorder on a target JVM; commands require the exact PID and attach permissions. In examples, **12345 is only a hypothetical PID**—do not run it accidentally against another process.

### Short Recording When Incident Timing Is Known

```bash
jcmd 12345 help JFR.start
jcmd 12345 JFR.start name=cpu-spike settings=profile duration=120s filename=cpu-spike.jfr
jcmd 12345 JFR.check
```

Start **before or right when** the spike may occur and note the timestamp. The output file is written when the recording stops; if `filename` is relative, check the JVM's working directory/write permissions. The `profile` settings collect more data than `default` and should normally run **briefly and under control**. Do not expect a 120-second recording to contain an incident that ended 10 minutes before it started.

### Continuous Rolling Buffer to Keep Minutes Before an Alert

For rare incidents, consider a `default` recording bounded by age and disk size:

```bash
jcmd 12345 JFR.start name=rolling settings=default disk=true maxage=15m maxsize=256m
jcmd 12345 JFR.check
```

Right when an incident occurs, dump the retained history:

```bash
jcmd 12345 JFR.dump name=rolling filename=incident.jfr maxage=10m
```

When the recording is no longer needed:

```bash
jcmd 12345 JFR.stop name=rolling
```

This is a **JDK 21 parameter usage example**, not a recommended default configuration for every service. `maxage=15m` caps **data retention age**, and `maxsize=256m` caps **stored data size**; at high event rates, the size cap can evict older data before 15 minutes. `maxsize` must fit the JVM's actual chunk limits. A `rolling` recording does not auto-stop without `duration`, and `JFR.dump` **does not stop** the recording.

A JFR recording contains only enabled events matching configured thresholds/filters, not everything the JVM ever did. When analyzing, inspect event timestamps, gaps, sample counts, what phase the application was in, and GC/thread state; never treat absence of an event as absolute proof the phenomenon did not happen.

### Thread Dumps Differ from Sampling Profilers

```bash
jcmd 12345 Thread.print
```

The command above is **a single snapshot**. To watch state evolve, capture several snapshots at defined intervals, record timestamps, and bound frequency/impact. Calling dumps too frequently adds overhead and produces huge files; `RUNNABLE`, `WAITING`, or `BLOCKED` at one instant does not reveal long-term CPU ratios.

With a dedicated sampling profiler, document sampling mode (CPU/on-CPU, wall-clock, allocation, lock), period, overhead, exclusions, and which threads are counted. Sample counts on a flame graph reflect distribution by **mode and actual capture duration**, and do not automatically translate into request counts or method invocation counts.

## 9. Trade-Off Between Resolution, Duration, and Cost

Longer duration at higher resolution yields more evidence, yet is not free. For polled data, raw point count is roughly:

```text
points ≈ number_of_series × (Tobs / Δc)
```

For example, with **600 time series** over 1 hour:

| Collection interval | Theoretical points/series | Total raw points |
| --- | ---: | ---: |
| 60 s | 60 | 36,000 |
| 15 s | 240 | 144,000 |
| 5 s | 720 | 432,000 |

This is an **estimate of point counts**, not direct storage bytes or CPU cost; systems also incur compression, metadata, retention, and query overhead. If metric labels contain `userId`, `requestId`, unnormalized URLs, or high-cardinality values, series counts can explode unexpectedly. Raising scrape frequency without matching storage/query capacity causes dropped samples and noise.

For traces/logs/JFR, cost also depends on **events/second, event size, stack depth, sampling policy, flush cadence, retention, and disk write speed**. Overly detailed recording can slow down the service itself; establish baseline overhead and monitor impact, especially in production.

A practical strategy is **multi-resolution telemetry**:

1. Continuous background monitoring with low-cost signals and long retention to learn *when/where*.
2. Use histograms and event timestamps so brief critical signals are not lost.
3. Use rolling buffers or triggers to keep evidence **before and during incidents**.
4. Enable detailed profiler/JFR over a bounded window when deep analysis is needed; turn it off once data is collected.
5. Downsample old data for long-term trends, while preserving critical raw incident evidence and documenting retention limits.

Pick a sampling resolution just sufficient for your goal, then **verify actual captured sample counts**. "Configured 10 ms" does not mean "one valid sample every 10 ms".

## 10. Step-by-Step Selection Process

Fill in justification for each decision before collecting data:

| Step | Question to Answer | Example of a Specific Enough Answer |
| --- | --- | --- |
| 1. Goal | What do we want to determine? | "Did a GC pause coincide with the 30 s p99 spike?" |
| 2. Phenomenon timescale | How short is the shortest occurrence? Periodic or rare? | "5–30 s spikes, roughly twice per hour" |
| 3. Signal type | Gauge, counter, histogram, event, or stack sample? | "Request latency histogram + JFR GC events" |
| 4. Cadence | What are `Δs`, `Δc`, `Wagg`, `Δq`? | "15 s scrape; 1m and 5m rate windows; raw events keep timestamps" |
| 5. Total duration | How many load/event cycles and valid samples are needed? | "2h background tracking; 120s detailed recording on trigger" |
| 6. Incident window | When do baseline/in-incident/recovery start/end? | "5 min before, entire spike, 5 min after, UTC" |
| 7. Overhead and retention | CPU, I/O, disk, bandwidth, sensitive data, retention? | "Short JFR profile; rolling default capped in size" |
| 8. Verification | Right data type, right timezone, enough samples, same build/load? | "Verify timestamps, gaps, counts, scrape lag, and restarts" |

There is no single optimal `Δs`/`Tobs` pair for every incident. Sound choices must start from **the phenomenon to detect**, **the evidence required to conclude**, and **acceptable cost/impact**.

### Measurement Session Log Template

```text
Goal: identify bottleneck for slow requests during the 14:00 UTC batch run
Service/JDK/build: service name, JDK version, specific commit/release
Scope: affected nodes/pods/routes/tenants
Time zone: UTC; clock sync status and observed skew
Incident: t_start, t_detect, t_end (with uncertainty)
Baseline: [t_pre, t_start)
Incident: [t_start, t_end)
Recovery: [t_end, t_post)
Signals: process CPU + request histogram + JFR sample/lock events
Collection/sampling: Δs, Δc, Wagg, Δq, event timestamps
Recording: actual start/end; settings; sampling mode; file size
Data quality: expected/actual point counts; gaps; resets; dropped events
Context: request rate, dataset, deploy/config changes, GC/workload phase
Conclusion: what the data confirms, what remains a hypothesis
```

The "expected/actual point counts" line is a core QA step: if you intended 120 points yet received only 40 due to collector overload, re-evaluate trustworthiness before interpreting charts.

## 11. Common Mistakes and Fixes

| Mistake | Why It Is Wrong | Right Approach |
| --- | --- | --- |
| "Scraped every 1 minute, so any sub-minute spike is lost." | True for instantaneous gauges; continuously updated histograms/events can still retain spike counts. | Check metric type and where aggregation happens. |
| "Dashboard plots 1 point per 5 minutes, so raw data only has that." | Query step/downsampling can hide finer stored detail. | Inspect raw resolution, query range, aggregation function, and retention. |
| "20 metric points equals 20 requests." | Points can be aggregates from thousands of events. | Check `count` and measurement semantics. |
| "100 Hz for 60 seconds guarantees 6,000 useful samples." | Actual samples depend on sampler, thread state, filters, pauses, and overhead. | Inspect actual sample count, sampling mode, and load phase. |
| "Observed 5 minutes without errors, so the bug doesn't exist." | Rare incident, wrong timing, no pre-buffer, or wrong signal. | Track failure frequency, use event triggers/rolling retention, widen coverage. |
| "Post-change p99 is lower, so performance improved." | Small sample size or different before/after workload; percentiles have estimation error. | Compare same traffic mix, sample counts, duration, histogram, and uncertainty. |
| "Fill no-data gaps with 0 to make charts look nicer." | Fabricates fake signals that look like recovery or zero traffic. | Preserve missing state and investigate collector/network/restarts. |
| "A post-incident profile is the incident's profile." | Describes workload at capture time, which may differ completely from failure time. | Capture before/during trigger or explicitly note limits. |
| "15 s / 5m is an immutable universal rule." | GC pauses, CPU trends, and memory leaks operate on different timescales. | Choose per signal, question, overhead, and retention. |

## 12. Self-Check Scenarios

**1. Request latency p99 occasionally spikes for 3 seconds, scraped every 30 seconds. Must you lower scrape interval to 100 ms?**

Not necessarily. Check whether the latency metric is a **per-request updated histogram** or an instantaneous gauge. With a full histogram, a 30-second scrape still captures slow requests. To pinpoint **which exact 3 seconds**, you need timestamped events/traces or narrower-window metrics; lowering scrape to 100 ms can cause needless overhead without solving precision.

**2. CPU profiler captured 10 seconds and did not show the suspected method. Can you rule it out?**

No. You must know whether the suspected workload ran during those 10 seconds, whether the profiler used CPU or wall-clock sampling, valid sample count, and whether the method was filtered or blocked on locks/I/O. Re-capture covering the relevant phase and cross-check metrics.

**3. An alert fired at 10:30, an engineer started JFR at 10:33 and saw everything looked normal. Can we say the JVM was fine at 10:30?**

No. Newly started JFR holds no data prior to 10:33. You need metrics/logs/traces saved from 10:30 or a rolling recording retaining history; otherwise, document "missing evidence at incident time".

**4. A counter increased from 9,000 to 9,500 across a 100-second collection gap. Can we infer all 500 events happened in the final second?**

No. The 500 difference only tells you total increase between the two readings (assuming no reset); the interval average rate is `5 events/s`, and exact timing cannot be reconstructed without timestamped events.

**5. How do you compare throughput before and after a rollout without misleading yourself?**

Record `t_change`, warm-up window, request count, traffic mix, routes, instance count, and consistent metric definitions. Pick before/after windows long enough to cover load cycles without mixing the rollout transition, and inspect error rate, saturation, and latency distribution simultaneously. Without load control, call the result an *observed correlation* rather than proving the rollout caused it.

## 13. Practical Summary

Choose **sampling interval** from the duration of the signal to capture and the metric type; choose **observation duration** for enough opportunities and representative sample counts; choose **incident windows** to preserve baseline, incident, and recovery. When reporting, always state actual timestamps, sources, aggregations, sampling, gaps, and overhead. A trustworthy measurement is one taken at **the right time, for the right phenomenon, with enough data to test hypotheses**—not merely the one with the most points.

### References

- [Oracle JDK 21 — `jcmd` diagnostic commands](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html): `JFR.start`, `JFR.dump`, `JFR.stop`, `maxage`, `maxsize`, and attach permissions.
- [OpenTelemetry — Metrics Data Model](https://opentelemetry.io/docs/specs/otel/metrics/data-model/): gauge/sum/histogram, timestamps, aggregation temporality, and observation counts.
- [Prometheus — Histograms and Summaries](https://prometheus.io/docs/practices/histograms/): percentile estimation, aggregation, and rate semantics.