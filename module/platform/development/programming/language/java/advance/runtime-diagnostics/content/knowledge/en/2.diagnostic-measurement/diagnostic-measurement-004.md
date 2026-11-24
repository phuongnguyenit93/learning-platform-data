# 2.4 Gauges, Counters, Rates, and Latency Distributions

> **Java Advance – runtime-diagnostics** · **2. Measurement Methodology**

## 1. Objectives and Concept Map

When observing a Java application, a dashboard might show *heap used = 900 MiB*, *requests completed = 2,000,000*, *throughput = 120 requests/s*, and *p99 latency = 800 ms*. All four are numbers, yet they represent four different types of information. Conflating them easily leads to misdiagnosis: reading a counter as active requests, reading a gauge as throughput, averaging p99s, or calling every spike a root cause.

After this lesson, you will be able to:

- Distinguish **gauges**, **counters**, **rates**, and **latency distributions**.
- Choose suitable metrics for heap, threads, queues, requests, exceptions, GC, CPU, I/O, and timeouts in the Java runtime.
- Calculate delta/rate/increase, and recognize counter resets, missing samples, mismatched units, and unsuitable measurement windows.
- Read mean, median, p95, p99, cumulative histograms, fraction under an SLO threshold, and limits of aggregation.
- Combine multiple metrics into a testable diagnostic hypothesis rather than inferring root cause from a single chart.

| Type | Question | Examples | Calculations to Use |
| --- | --- | --- | --- |
| Gauge | **How much is there right now?** | Heap bytes used, active requests, borrowed connections, queue depth | Value at point in time, min/max, trend; do not infer event count directly |
| Counter | **How much has happened/accumulated?** | Requests completed, exceptions, GC collections, bytes sent, CPU time seconds | Difference over a reset-free interval; rate/increase accounting for resets |
| Rate | **How much happens per unit time?** | Requests/s, errors/s, bytes/s, GC/s, CPU seconds/s | Counter change divided by time; pick a window with enough samples |
| Distribution | **How long do requests take, how heavy is the slow tail?** | Latency buckets, p50/p95/p99, duration sum/count | Histograms, percentiles, fraction under SLO, weighted mean |

A key point: **rate is usually derived from a counter**, yet rate itself is a time-based transformation; **percentiles are computed from a distribution**, not from a request rate. Metric names must accompany unit, measured subject, timestamp, and scope such as route/instance/version.

## 2. Gauge – Point-in-Time State Snapshot

A gauge \(G(t)\) represents a state at time \(t\); it can go up, go down, return to 0, or stay flat.

Examples in Java/JVM:

- *jvm_memory_used_bytes*: bytes currently in use in the measured memory region.
- *jvm_threads_live_threads*: number of live threads; distinct from threads actively executing requests.
- *active_connections*, *idle_connections*, *pending_connections*: pool state at sampling time.
- *in_flight_requests*: requests that entered the measured scope and have not yet finished.
- *queue_depth*: items currently sitting in the queue.

Suppose an in-flight gauge has these samples:

| Timestamp | In-flight requests |
| --- | ---: |
| 10:00:00 | 5 |
| 10:00:15 | 18 |
| 10:00:30 | 40 |
| 10:00:45 | 9 |

At 10:00:30 there are **40 unfinished requests**. You cannot say "there were 40 new requests in 15 seconds" or "throughput is 40 requests/s". In-flight can rise because incoming traffic increased, requests run longer, retries surged, an executor stalled, or downstream slowed down. To distinguish them, you need **arrival rate**, **completion rate**, **timeout count**, and **latency** over the same interval.

**Why can gauges mislead?** If scraped every 15 seconds, a 300-item queue depth spike lasting 2 seconds between scrapes can be missed completely. A panel plotting the last value in a window is also different from one plotting the maximum value in the window. Know whether a panel shows *last*, *avg*, *max*, min, or interpolated values; for brief incidents, combine with logs/traces or max over an appropriate window.

A gauge is state, not completed work. Queue depth dropping 40 → 10 could be due to successful processing, timeouts, cancellations, queue transfers, or eviction; looking at the gauge alone cannot tell you that 30 requests were successfully processed.

**Note on memory:** heap used rising over a short period is not enough to conclude a leak. Many newly allocated objects reclaimed by GC still create a sawtooth curve. Inspect the post-GC trend across normal collection cycles, allocation rate, committed heap, RSS, and load conditions. Heap used is a **gauge**, whereas cumulative allocated bytes (if tracked) is a **counter**.

## 3. Counter – Cumulative Total Over the Metric's Lifecycle

A counter \(C(t)\) counts how many times an event occurred or how much work was consumed. Over a continuous reset-free interval, a counter normally **never decreases**:

\[
C(t_2) \ge C(t_1)\quad \text{when }t_2 \ge t_1.
\]

Common counters: completed requests, exceptions, retries, cache misses, bytes sent, GC count, total CPU time. A counter holds the **total since counting started**, not the total for the window currently displayed on the dashboard.

Example on the same JVM:

| Timestamp | completed_requests_total |
| --- | ---: |
| 10:00:00 | 1,200 |
| 10:01:00 | 1,380 |

Over the 60-second interval there were **180 completed requests** assuming no reset and consistent completion definition. The number 1,380 does not say the JVM has 1,380 concurrent requests running.

### Counter Resets and Instance Replacement

A JVM/process restart can reset a counter to 0. Suppose at 10:01 counter = 1,380, and at 10:02 it is 12 due to a restart. The raw difference \(12-1380=-1368\) is **not** minus 1,368 requests; it is a reset boundary. Many time-series systems provide rate/increase functions that handle counter resets, yet accuracy still depends on sample count and the exact restart timing. Events occurring between two scrapes may not be exactly recoverable.

When multiple pods/JVMs exist, **compute rate per individual counter series before summing**. Summing raw counters across pods can drop simply because an old pod disappeared, breaking subtraction/rate calculations. Sharing the same service label does not mean sharing the same counter lifecycle.

Some counters accumulate **duration** or **bytes** instead of **event counts**. For instance, total CPU seconds increasing by 120 in 60 wall seconds means an average CPU-time rate of roughly 2 CPU-seconds/second, corresponding to average time usage of two cores before factoring in quotas and dashboard conversions. Never read total CPU seconds directly as instantaneous CPU percentage.

Counters can also overflow or be reinitialized by the instrumentation lifecycle. For calculations needing high precision, check the instrumentation contract, timestamps, and process start time.

## 4. Delta, Increase, and Rate – Change Over a Time Interval

For a **non-resetting** counter, the average rate over \([t_1,t_2]\) is:

\[
r=\frac{C(t_2)-C(t_1)}{t_2-t_1}.
\]

If \(C\) is in requests and \(t\) is in seconds, rate has units of requests/s. Going from 1,200 → 1,380 requests in 60 seconds:

\[
\Delta C=180\ \text{requests};\qquad r=180/60=3\ \text{requests/s}.
\]

| Reading | Question | Unit |
| --- | --- | --- |
| Current counter | Total completed since process started? | requests |
| 5-minute increase | How many requests occurred in 5 minutes? | requests |
| 5-minute rate | Average requests completed per second in this window? | requests/s |
| In-flight gauge | How many requests are currently active at sample time? | requests |
| Gauge slope | How fast is the active count changing per second? | requests/s, yet **not throughput** |

An observability engine's calculation can be more complex than a two-point difference: Prometheus *rate* uses samples within the window, handles counter resets, and extrapolates to window boundaries. The two-point formula above explains units and meaning, and **does not claim to replace every time-series engine verbatim**.

### Error Rate and Error Ratio Are Two Different Things

In 60 seconds, with 300 completed requests and 12 failed requests:

- **Request rate:** \(300/60=5\) requests/s.
- **Event error rate:** \(12/60=0.2\) errors/s.
- **Error ratio:** \(12/300=0.04=4\%\) failed requests.

In everyday speech, some people call 4% an "error rate"; on dashboards, explicitly label **errors/s** vs. **error ratio (%)** along with the denominator. When there are zero requests in the window, `0/0` is **undefined**; do not automatically report 0% as if the system were healthy.

Do not mix retry attempts with logical requests: if a single user request retries three times, the network-attempts counter may increment by 3 while the logical-requests counter increments by 1. Both quantities are useful, yet must have separate names and measurement points.

### Short Windows, Long Windows, and Sample Counts

- A 30-second rate reacts fast to spikes, yet is noisy under sparse scraping.
- A 5-minute rate is smoother, yet can mask a 20-second bottleneck.
- A 1-hour rate suits broad traffic patterns, not short timeline investigations.
- A missed scrape does not mean the metric dropped to 0. With only one sample, there is not enough basis to compute a reliable rate.
- Use actual timestamps when comparing two points; an 8-second scrape delay makes blindly dividing by 15 seconds wrong.
- With counter resets, use counter-aware functions or split reset-free segments; never treat negative differences as rates.

**Specifically for gauges:** \((G(t_2)-G(t_1))/\Delta t\) measures the slope of state, not incoming events. Queue depth rising by 20 items/minute only says arrival − departure = 20/minute, while the true arrival rate can be much higher.

## 5. Latency Is a Distribution, Not a Single Number

Latency \(L_i\) must be defined by concrete **start and end points**. Client-observed time may include network, proxy, retries, connection setup, and queuing before application handling; server handler latency may exclude those. Never directly compare two metrics with different scopes and infer cause by subtracting them.

Consider 10 hypothetical requests with sorted durations (ms):

\[
20,\ 30,\ 35,\ 40,\ 45,\ 50,\ 70,\ 100,\ 300,\ 900.
\]

Sum = **1,590 ms**; mean = \(1590/10=159\) ms. Yet most requests took only 20–100 ms, while one request took 900 ms. Mean **does not reveal the shape of the slow tail**.

### Mean, Median, p95, and p99

- **Mean:** total latency divided by request count. Useful for total processing time and workload estimation; very sensitive to outliers.
- **p50/median:** threshold that roughly 50% of observations do not exceed.
- **p95:** threshold that roughly 95% of observations do not exceed; focuses on the slowest 5% tail.
- **p99:** threshold that roughly 99% of observations do not exceed; critical when SLOs are tail-sensitive.
- **Max:** largest observation in a window, sensitive to a single anomalous request.

Finite-sample quantiles follow various conventions. With **nearest-rank**, after sorting \(n\) observations, quantile \(p\) is the element at 1-based position \(\lceil p\cdot n\rceil\). In the 10-request example:

| Metric | Result |
| --- | ---: |
| Min / Max | 20 ms / 900 ms |
| Mean | 159 ms |
| p50 | 45 ms |
| p90 | 300 ms |
| p95 | 900 ms |
| p99 | 900 ms |

p95 and p99 both equal 900 ms because there are **only 10 samples**; this is not evidence that those percentiles are "stable" at 900 ms. Libraries using different interpolation methods may produce different numbers. Comparing dashboards requires knowing the calculation method and measurement window.

If a route receives only 20 requests in a minute, p99 is nearly determined by the single slowest request; do not assert tail-latency trends with false precision. Track **request count**, timeout rate, p50/p95/p99, and distribution together to read the true story.

### Why Can Timeouts Make p99 Look Artificially Good?

A timer recorded only when a request **succeeds** omits requests that timed out, were rejected, or were cancelled. As the system degrades, the slowest requests disappear from the sample set, causing *successful-request* p99 to drop! Therefore look concurrently at *arrival*, *completed*, *errors*, *timeouts*, *drops*, in-flight, and latency by outcome. Metric definition is part of the evidence.

## 6. Histograms – Storing Distributions as Buckets

A histogram counts observations by threshold. In a **classic cumulative histogram**, the "≤100 ms" bucket also includes requests in the "≤50 ms" bucket. That is, buckets are **cumulative across boundaries**.

Applying the 10 requests above:

| Cumulative bucket | Request count |
| --- | ---: |
| ≤50 ms | 6 |
| ≤100 ms | 8 |
| ≤500 ms | 9 |
| +Inf | 10 |

Valid deductions:

- Requests in the interval (50,100] ms: \(8-6=2\).
- In the interval (100,500] ms: \(9-8=1\).
- Above 500 ms: \(10-9=1\).
- Fraction of requests ≤100 ms: \(8/10=80\%\).

**Do not sum 6 + 8 + 9 + 10 to say there were 33 requests.** Each bucket includes requests from smaller thresholds. The **+Inf** bucket contains all valid observations.

A classic duration histogram typically exposes:

- **_bucket{le="..."}**: cumulative counter per threshold \(le\) (*less than or equal*).
- **_count**: total number of recorded observations.
- **_sum**: sum of measured durations, in the metric's unit.

For **non-negative** durations, these quantities have counter semantics. Mean latency over a window can be computed as:

\[
\overline{L}_{\text{window}} =
\frac{\Delta\text{duration\_sum}}{\Delta\text{duration\_count}}.
\]

Metrics systems may use native histograms or summary/quantile sketches instead of classic buckets; check the exact metric type and aggregation semantics. Do not assume every histogram exports a `*_bucket` series.

### Percentiles from Histograms Are Only Estimates

Knowing bucket ≤500 ms has 9 requests and +Inf has 10 does not tell you whether the last request was **501 ms, 900 ms, or 30 s**. Histogram buckets store threshold counts, not exact durations. Estimating p95/p99 relies on bucket boundaries and interpolation rules; overly wide buckets make estimates coarse.

Design buckets near SLO thresholds: if the target is **95% of requests ≤300 ms**, having a **0.3 s** boundary lets you compute SLO compliance directly. Too many buckets across high-cardinality labels increase metric cost, while too few buckets lose tail detail. Across multiple pods, buckets need **compatible** boundaries and units before summing.

### Do Not Average p99 Across Instances

p99 is not associative: if JVM A has p99 = 100 ms and JVM B has p99 = 900 ms, **500 ms is not the service-wide p99**. To calculate a system-wide percentile, merge distribution data (compatible histogram buckets or mergeable statistical sketches), then estimate. Client-side summaries with precomputed quantiles usually cannot be summed or averaged into a global p99.

Mean also has a weighting trap: instance A processes **1** request with mean 900 ms, B processes **99** requests with mean 100 ms. System-wide mean = \((1\cdot900+99\cdot100)/100=108\) ms, **not** the unweighted average \((900+100)/2=500\) ms. Sum **duration sum** and **duration count** separately, then divide.

## 7. Designing Measurements in Java: Clocks, Lifecycle, and Concurrency

### Use the Right Clock

- Use **System.nanoTime()** for elapsed-time differences inside the same process. Absolute values of `nanoTime` are not calendar timestamps and cannot be compared across JVMs.
- Use **Instant.now()** or timezone-aware timestamps when placing events on a timeline; wall clock can be adjusted.
- Pick start/end points matching the question: when the HTTP request enters the server, when the handler starts, when acquiring a connection, or when calling a dependency?

**Illustrative snippet, not a standalone program**: inside a handler receiving a passed-in task *work.run()*, measure:

~~~java
long startedNanos = System.nanoTime();
try {
    work.run();
} finally {
    long elapsedNanos = System.nanoTime() - startedNanos;
    // Record elapsedNanos into a duration recorder/histogram here.
}
~~~

Do not forget to record metrics in error or timeout branches according to your observation contract. Convert nanoseconds to milliseconds/seconds **consistently** without premature rounding. For an in-flight gauge, increment when the request starts and decrement in *finally* so exceptions do not "leak" the count.

### Instrumenting Multi-Threaded Counters and Histograms

To count each request once, place instrumentation at exact lifecycle points:

- *started_total* increments when accepting the request.
- *completed_total* increments at the defined termination point; status is only known after processing.
- *in_flight* increments on entry, decrements on exit regardless of exceptions.
- *duration* is observed exactly once per completed or terminated request per measurement policy.
- Retry attempts and logical requests must have separate metrics if both are tracked.

In Java, shared variables need concurrency-safe operations like **AtomicInteger** or **LongAdder**, or a metrics library. However, **thread-safe updates to individual variables do not make a cross-metric snapshot across count/sum/buckets atomic**; a scrape occurring mid-update can see slight discrepancies. This is why you should pick an appropriate observability library, understand update lag, and avoid using instantaneous snapshots to prove strict invariants.

High-throughput applications should not retain every individual latency value unboundedly just to calculate percentiles; use histograms, summaries, or quantile sketches with explicit contracts and bounded cost.

## 8. Runnable Java 17+ Example: From Gauge to Latency Distribution

The program below uses **plain JDK** with no external libraries. For repeatable results, durations are predefined: this is a **measurement simulation**, not a real speed benchmark. Create **MetricsDemo.java**.

~~~java
import java.util.Arrays;
import java.util.Locale;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.LongAdder;

public class MetricsDemo {
    private static final long[] LIMITS_MS = {50, 100, 500};
    private final AtomicInteger inFlight = new AtomicInteger();
    private final LongAdder completed = new LongAdder();
    private final LongAdder durationSumMs = new LongAdder();
    private final LongAdder[] buckets = {
        new LongAdder(), new LongAdder(), new LongAdder()
    };

    private void beginRequest() {
        inFlight.incrementAndGet();
    }

    private void endRequest(long elapsedMs) {
        if (elapsedMs < 0) throw new IllegalArgumentException("Negative latency");
        durationSumMs.add(elapsedMs);
        for (int i = 0; i < LIMITS_MS.length; i++) {
            if (elapsedMs <= LIMITS_MS[i]) buckets[i].increment();
        }
        completed.increment();
        inFlight.decrementAndGet();
    }

    private static long nearestRank(long[] sorted, double quantile) {
        return sorted[(int) Math.ceil(quantile * sorted.length) - 1];
    }

    public static void main(String[] args) {
        MetricsDemo m = new MetricsDemo();
        long[] observedMs = {20, 30, 35, 40, 45, 50, 70, 100, 300, 900};

        for (long ms : observedMs) {
            m.beginRequest();
            m.endRequest(ms);
        }
        // Three new requests are still in progress when reading the gauge.
        for (int i = 0; i < 3; i++) m.beginRequest();

        System.out.println("in_flight=" + m.inFlight.get());
        System.out.println("completed_total=" + m.completed.sum());
        for (int i = 0; i < LIMITS_MS.length; i++) {
            System.out.println("duration_le_" + LIMITS_MS[i]
                + "_ms_total=" + m.buckets[i].sum());
        }
        System.out.println("duration_le_inf_total=" + m.completed.sum());
        System.out.println("duration_sum_ms=" + m.durationSumMs.sum());

        long[] sorted = observedMs.clone();
        Arrays.sort(sorted);
        System.out.printf(Locale.ROOT, "mean_ms=%.1f%n",
            (double) m.durationSumMs.sum() / m.completed.sum());
        System.out.println("p50_ms=" + nearestRank(sorted, 0.50));
        System.out.println("p95_ms=" + nearestRank(sorted, 0.95));
        System.out.println("p99_ms=" + nearestRank(sorted, 0.99));

        // Two snapshots of another counter, 60 seconds apart.
        long counterBefore = 1200, counterAfter = 1380;
        System.out.printf(Locale.ROOT, "rate_per_second=%.1f%n",
            (counterAfter - counterBefore) / 60.0);
    }
}
~~~

Commands:

~~~bash
javac MetricsDemo.java
java MetricsDemo
~~~

Stdout:

~~~text
in_flight=3
completed_total=10
duration_le_50_ms_total=6
duration_le_100_ms_total=8
duration_le_500_ms_total=9
duration_le_inf_total=10
duration_sum_ms=1590
mean_ms=159.0
p50_ms=45
p95_ms=900
p99_ms=900
rate_per_second=3.0
~~~

Interpretation:

- **in_flight=3** is a gauge representing three open requests.
- **completed_total=10** is a counter: ten completed requests.
- **duration_le_100_ms_total=8** is a cumulative bucket; **8/10** requests completed within 100 ms.
- **duration_sum_ms=1590** is used with count 10 to produce mean 159 ms.
- Quantiles in the example are computed **from the sorted raw array** via nearest-rank, not inferred from buckets.
- **rate_per_second=3.0** is calculated from two hypothetical counter snapshots 1,200 and 1,380 **separate** from the ten-request demo counter; separated to illustrate a rate calculation with proper units.

This program is a single-threaded educational pattern of recording logic; it has no scraping library, does not tag metrics by route/status, and does not simulate real concurrency. In production applications, use thread-safe timers/gauges/counters from an appropriate library, metrics with clear scope and lifecycle, a consistent completion definition, and check for skew when reading multiple counters concurrently.

## 9. Query Examples Using Prometheus Classic Histograms

The metric names below are **illustrative hypotheses**. Apply them only if your system actually exports those metrics and labels; for native histograms or other backends, query APIs may differ.

**Service-wide throughput**, requests/s:

~~~promql
sum(rate(http_requests_total[5m]))
~~~

**5xx error rate**, errors/s:

~~~promql
sum(rate(http_requests_total{status=~"5.."}[5m]))
~~~

**Error ratio** (0–1), provided requests exist and share the same counting point:

~~~promql
sum(rate(http_requests_total{status=~"5.."}[5m]))
/
sum(rate(http_requests_total[5m]))
~~~

If the denominator is 0 or no series exists, handle **no traffic/no data** properly—never arbitrarily treat it as 0% errors.

**Per-route p95 estimate from classic cumulative buckets**, in seconds:

~~~promql
histogram_quantile(
  0.95,
  sum by (route, le) (
    rate(http_request_duration_seconds_bucket[5m])
  )
)
~~~

**System-wide mean latency** over a 5-minute window:

~~~promql
sum(rate(http_request_duration_seconds_sum[5m]))
/
sum(rate(http_request_duration_seconds_count[5m]))
~~~

**Fraction completed in at most 300 ms**, only if a 0.3-second bucket actually exists:

~~~promql
sum(rate(http_request_duration_seconds_bucket{le="0.3"}[5m]))
/
sum(rate(http_request_duration_seconds_count[5m]))
~~~

Checklist items:

1. The `*_seconds` suffix indicates units of **seconds**; 0.3 s = 300 ms, do not enter 300 into a second-denominated threshold.
2. The **le** label must be preserved when summing classic buckets for *histogram_quantile*.
3. Compute **rate per counter series before summing** so resets and membership changes work semantically.
4. When grouping by *route*, aggregate only instances sharing the same bucket boundaries and latency recording semantics.
5. A bucket larger than the SLO threshold cannot accurately deduce the fraction under a smaller SLO without a matching boundary.
6. Quantiles from buckets **are estimates**, dependent on bucket width and sample count.

Do not use raw request IDs, user IDs, order IDs, or URLs containing dynamic IDs as metric labels: cardinality grows roughly by the **product** of label values, easily exhausting metric storage and leaking sensitive data. Use route templates like `/orders/{id}`, and place detailed IDs in controlled traces/logs.

## 10. Multiple JVMs, Multiple Routes, and Traffic Mix

When aggregating across a distributed system, the first question is: do the series share **the same unit, same window, same counting point, and same outcome definition**? Typically valid combinations:

- Sum per-JVM rates to get total requests/s.
- Sum in-flight gauges if requests are counted once within the intended scope.
- Sum duration sums and counts, then divide to get weighted mean.
- Sum histogram bucket rates sharing identical boundaries, then estimate percentiles.
- Compute error ratio as total error rate divided by total request rate, rather than averaging ratios across low-traffic and high-traffic pods equally.

Error-prone combinations:

- Averaging per-pod p99s as global p99.
- Averaging per-pod means without weighting by request count.
- Summing raw absolute counters of new and old pods and taking differences across membership changes.
- Aggregating latencies of very fast and very slow routes without splitting by route; shifting traffic mix can make global p99 look better even while one route regresses.

Example: route A has 9,900 fast requests, route B has 100 very slow requests. Global p99 can mask much of what happens on B. Dashboards should therefore keep both an **aggregate view** (overall impact) and **views by route/status/version/instance** (localization), using bounded labels to avoid cardinality explosion.

Dashboards may alter formulas by resolution: one panel renders percentiles from raw samples, another from 5-minute histograms. Those two values need not match identically; inspect sources and aggregation formulas before comparing.

## 11. Sampling, Dropped Samples, and Tail Latency Traps

### Sample Count and Statistical Stability

p99 in a window with only 10–20 requests is virtually dominated by the single slowest observation. With 100 requests, the 1% region still corresponds to roughly one request. When analyzing low-traffic routes, report request count alongside or widen the window with justification—do not proclaim minute-by-minute p99 as a stable truth.

### Missing Data Is Not Zero

A recently restarted JVM, an unreachable scrape target, or a dropped series label creates data gaps. Never interpolate missing data as 0 requests/s or 0 heap used without verifying. When stitching timelines from dashboards and logs/JFR, verify timezones, timestamps, clock skew, and pipeline ingestion delay.

### Trace Sampling Differs from Metrics

Tracing might sample only 1% of requests, or deliberately retain slow/error traces. That sample is great for finding stacks/mechanisms, yet **does not represent the latency distribution of all traffic**. When histograms record every request while tracing is sampled, never compute "system-wide" p99 directly from an error-biased trace set without weights and sampling corrections.

### Timeouts and Coordinated Omission

If a load generator only sends a new request when the previous one finishes, when the server stalls, measured arrival rate drops along with the server. This hides latency that users arriving at a fixed rate would experience (**coordinated omission**). In benchmarks, specify arrival schedule, timeouts, rejections, and how unfinished requests are recorded.

Similarly, a latency histogram recording only successful requests drops timed-out/dropped requests; p99 falls while real user experience worsens. Read **p99 + request volume + timeouts/drops/rejections + error ratio** together.

## 12. Practice Scenario: Finding Why API p99 Spiked

*Hypothetical scenario: numbers illustrate diagnostic methodology, not benchmark results.*

After a deployment, `/orders` p99 jumps from 180 ms to 1.4 s for 10 minutes. The dashboard shows:

| Data | Before | During Incident | Type |
| --- | ---: | ---: | --- |
| Completed request rate | 120/s | 115/s | Counter → rate |
| In-flight | 12 | 90 | Gauge |
| Pending DB pool | 0 | 35 | Gauge |
| Timeout rate | 0.05/s | 5/s | Counter → rate |
| p99 server latency | 180 ms | 1.4 s | Distribution |
| Mean latency | 90 ms | 240 ms | Sum/count |
| Heap used | 620 MiB | 670 MiB | Gauge |
| GC pause p99 | 10 ms | 12 ms | Distribution |

**What can be stated immediately:** in-flight and pending connections rose while completion rate did not increase, and both p99 and timeout rate spiked. Signs align with requests **waiting on a resource** or slow downstream responses, yet are insufficient to conclude "DB pool config is wrong".

**Hypothesis H1 – DB pool exhausted due to holding connections too long:** if true, we should see connection acquire time or query duration increase, many requests waiting on the pool, and stacks/traces pointing to the call path.

**Hypothesis H2 – traffic or retries exceeded capacity:** if true, arrival/attempt rate should rise more sharply than completion rate; queues and in-flight accumulate, and gateway/client retries may amplify the load.

**Hypothesis H3 – GC pauses:** with GC pause p99 at 12 ms versus request p99 at 1.4 s, H3 is less supported if pause timestamps do not coincide with latency spikes. Still, verify the exact window, instances, and other stop-the-world events before ruling it out completely.

**Investigation steps:** correlate slow traces with connection-acquire spans and DB latency; inspect pool/queue metrics and thread states; compare arrival/completion/timeout rates, deploy diffs, and healthy control instances. If a test fix reducing connection hold time drops pending counts and stabilizes p99 under equivalent load, you gain evidence for the mechanism. Do not immediately raise pool size if the DB is already saturated: increasing concurrency can degrade both upstream and the DB together.

An accurate report states **correlations**, **supporting/refuting evidence**, **testable mechanisms**, **reproduction conditions**, **fixes**, and **before/after measurements**. A single metric never proves causality.

## 13. Common Mistakes When Building or Reading Dashboards

| Mistake | Why It Is Wrong | How to Fix |
| --- | --- | --- |
| Reading raw request counter as throughput | Counter is total since process start | Compute rate over window, handle resets |
| Treating in-flight as requests/s | In-flight counts active requests, not completions | Check arrival/completion rates and latency |
| Computing rate from two points assuming ideal scrape interval | Actual timestamps may drift, samples may drop | Use real timestamps / engine rate functions |
| Computing negative rate after JVM restart | Counter reset to zero | Detect resets, compute per series |
| Averaging per-pod p99s | Quantiles do not aggregate linearly | Merge histograms or distributions first |
| Averaging per-pod means without traffic weighting | Pods handle different request counts | Sum(duration_sum)/sum(duration_count) |
| Summing cumulative buckets | Same request is counted in multiple buckets | Total uses count/+Inf; intervals use bucket deltas |
| Using a 1 s bucket to assert a 300 ms SLO | Exact count within 300 ms is unknown | Instrument an explicit 0.3 s boundary |
| Comparing ms latency against `*_seconds` metrics without conversion | Off by 1,000× | State units explicitly, convert properly |
| Looking only at p99 under low traffic | Tail samples are too sparse | Report count and window/methodology |
| Success p99 dropped ⇒ quality improved | Timed-out requests dropped out of sample | Inspect timeouts/drops and all outcomes |
| Heap used rose ⇒ memory leak | Heap is a gauge and fluctuates with GC/load | Inspect retained trend, allocation rate, RSS |
| Mixing logical requests and retry attempts | Double-counts and skews error ratio | Separate metrics by counting point |
| Metric labels contain dynamic IDs | Cardinality/cost explosion and data exposure | Use route templates and bounded labels |

## 14. Measurement and Interpretation Checklist in Runtime Diagnostics

Before concluding, answer all of these questions:

1. **What does this number measure?** Gauge/counter/rate/histogram/summary? Which unit?
2. **Where is the measurement point?** Client, gateway, handler, queue, pool, database, JVM, or OS?
3. **Which time/window?** Scrape interval, event timestamps, timezone, restarts/missing samples?
4. **What is the denominator?** How many requests were actually recorded? Are timeouts, failures, or drops excluded?
5. **How is it aggregated?** Per-route, per-instance, or service-wide? Compatible buckets? Any invalid percentile averaging?
6. **Is the metric distorted by load?** Traffic mix, autoscaling, retries, sampling, queues, GC, heap, and CPU quota?
7. **Which hypotheses can be refuted?** Which metrics or traces/stacks/JFR data will confirm or raise confidence?
8. **Was it re-measured after the fix?** Compare under equal conditions, monitoring latency distribution, rates, errors, in-flight, and resource cost.

## 15. Practice Exercises with Answers

**A.** A completed-request counter goes from 2,400 to 2,760 in exactly 2 minutes, with no resets. How many requests occurred and how many requests/s?

**Answer:** 360 requests, \(360/120=3\) requests/s.

**B.** Queue depth increases 15 → 35 after one minute. Can you conclude the arrival rate is 20 requests/minute?

**Answer:** No. That is a net increase of 20 items; you need enqueue, dequeue, and timeout/drop counts to know arrival and completion rates.

**C.** In one minute there are 240 completed requests and 18 errors. What are the request rate, event error rate, and error ratio?

**Answer:** 4 requests/s, 0.3 errors/s, and 7.5%.

**D.** A classic histogram has ≤100 ms: 80, ≤300 ms: 95, +Inf: 100. How many requests fell in (100,300] ms and how many >300 ms?

**Answer:** 95−80=15 requests in (100,300] ms; 100−95=5 requests over 300 ms.

**E.** Pod A has 1 request with mean 900 ms, pod B has 99 requests with mean 100 ms. What is the service-wide mean?

**Answer:** 108 ms, equal to total duration divided by total count. Do not take the unweighted average of 500 ms.

**F.** Two pods have p99 of 100 ms and 900 ms respectively. Is the global p99 equal to 500 ms?

**Answer:** You cannot deduce that; you need compatible distributions/histograms and request volumes.

**G.** After a deploy, successful-request p99 drops, while timeouts/s and in-flight both increase. Can you report that the system got faster?

**Answer:** Not yet. Slow requests may be timing out and disappearing from the success distribution; inspect all outcomes, arrival/completion rates, pending queues, and traces.

## Key Takeaways

**Gauge = current state**, **counter = accumulated total**, **rate = rate of change over time**, **distribution = how latency is spread**. Units, windows, resets, and sample counts govern diagnostic value. Mean does not replace p99; per-pod p99s cannot be averaged into a global p99. Combine throughput, waiting-state gauges, histograms/quantiles, errors/timeouts, JVM metrics, and traces on the same timeline to move from symptoms to testable hypotheses.