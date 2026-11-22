# Measuring p50, p95, p99 Latency and Throughput After Restore

After restoring a Java application from a CRaC checkpoint, you need to measure how fast and steadily the application actually serves requests. A successful JVM restore or an HTTP 200 from a health endpoint is not enough to conclude good performance. The application may still need time to recreate connection pools, load credentials, warm up caches, start workers, or reach steady processing state. During that period, latency of the initial requests can be significantly higher than latency once the system has stabilized.

The three commonly used percentiles are p50, p95, and p99. p50 describes latency at the middle of the distribution; p95 indicates that 95% of requests complete within at most that duration; p99 focuses on the slowest tier of requests. Throughput indicates how many requests or operations the system completes per unit of time. When evaluating post-restore performance, measure both latency and throughput because a system can keep latency low by processing few requests, or achieve high throughput while generating severe tail latency.

A meaningful measurement must separate restore duration, restore-to-readiness time, first-request latency, warm-up phase latency, and steady-state latency. At the same time, control the offered load, successful request count, errors, execution environment, and dependency state. This document presents how to design measurements, collect histograms, compute percentiles, measure throughput, and compare post-restore results against baselines.

## 1. Quantities to Measure

Do not collapse all intervals into a single number called startup latency. With CRaC, multiple milestones exist, and each answers a distinct operational question.

### 1.1. Restore duration

Restore duration is the time from starting the restore command or API call until the runtime recovers the process and transfers control to the application. This value reflects the cost of the checkpoint engine, reading the image, reconstructing memory mappings, and restoring process state.

Not every runtime exposes the same event or metric for restore start/end milestones. Use engine/JDK logs or telemetry if available; if measuring strictly from outside, specify clearly the start and end points used. Do not label the time from container creation to readiness as pure restore duration.

### 1.2. Restore-to-ready duration

Restore-to-ready is the elapsed interval from when the application resumes execution after restore until readiness opens. This interval may include:

- afterRestore callbacks of CRaC Resources.
- Recreating database pools, HTTP clients, broker clients, and sockets.
- Fetching new credentials or verifying certificates.
- Reading metadata of the current replica.
- Loading or refreshing caches.
- Joining consumer groups or acquiring leases.
- Health checks of mandatory dependencies.

This is typically the crucial quantity for orchestration systems because it determines when an instance can receive traffic.

### 1.3. First-request latency

First-request latency is the latency of the first request or initial batch of requests after readiness opens. Initial requests may trigger lazy initialization, open new connections, load previously unused classes, populate cache entries, or execute DNS/TLS handshakes.

Do not measure only a single first request. Measure a first-request window—for instance, the first 10, 100, or 1,000 requests depending on traffic volume and service type. Specify clearly whether this window begins when readiness opens or when the first request is dispatched.

### 1.4. Warm-up latency

Warm-up latency describes latency while the application transitions from its newly restored state toward stability. During this stage, caches may be populated, connection pools expand, JIT may continue optimizing code, and dependencies may still be recovering.

Measure latency across time windows or request count windows starting from readiness. Do not omit this phase from reports if real users can send requests during warm-up.

### 1.5. Steady-state latency

Steady-state latency is the latency once the application satisfies predefined stability conditions, such as:

- Cache hit ratio has reached its target level.
- Connection pools have attained their configured connection count.
- Workers and consumers are active.
- No mandatory bootstrap tasks remain.
- CPU, memory, and request rate no longer show major upward/downward drift within the observation window.

Do not pick an arbitrary warm-up interval and call everything afterward steady-state. Define stability criteria using metrics or application state.

### 1.6. Throughput and Goodput

Throughput is the number of requests or operations completed per unit of time. Goodput is the number of operations completed successfully according to the business contract within the same period.

Report separately:

- Offered rate: the rate at which the load generator attempts to send requests.
- Accepted rate: the rate at which the application accepts or admits requests into processing.
- Completed throughput: the rate of completed requests, including errors if the metric counts all finished responses.
- Successful throughput/goodput: the rate of successfully completed requests.
- Error rate: the proportion of failed or timed-out requests.

A service that returns errors quickly can still exhibit high completed throughput. Therefore, do not use requests/second alone to conclude good performance.

## 2. Properly Understanding p50, p95, and p99

Percentiles describe positions within a latency distribution. Given a sample set sorted in ascending order:

- p50 is the value at or below which approximately 50% of samples fall.
- p95 is the value at or below which approximately 95% of samples fall.
- p99 is the value at or below which approximately 99% of samples fall.

Example:

| Percentile | Latency | Interpretation |
|---|---:|---|
| p50 | 18 ms | Half of requests complete within at most ~18 ms |
| p95 | 75 ms | 95% of requests complete within at most ~75 ms |
| p99 | 210 ms | 99% of requests complete within at most ~210 ms |

In this example, roughly 1% of requests are slower than 210 ms. p99 does not mean every request completes within 210 ms; very slow outliers may still exist.

### 2.1. Why Are All Three Percentiles Needed?

p50 reflects typical experience and is usually less sensitive to isolated outliers. p95 reveals the slow tail affecting a noticeable share of users. p99 highlights tail latency caused by queueing, lock contention, garbage collection, network retries, connection pool exhaustion, or slow dependencies.

Looking only at p50 can make a system appear fast while 5% or 1% of requests suffer severe delays. Looking only at p99 can miss that the bulk of requests slowed down markedly. Read all three alongside throughput, error rate, and recovery time.

### 2.2. Example Latency Distribution

Suppose 10,000 requests have the following distribution:

| Latency Range | Request Count |
|---|---:|
| Under 20 ms | 5,000 |
| 20–50 ms | 4,000 |
| 50–100 ms | 900 |
| 100–250 ms | 90 |
| Over 250 ms | 10 |

p50 lies near the 20 ms boundary; p95 lies around 50 ms; p99 lies near 100 ms. Exact values depend on individual sample latencies and the percentile algorithm, and cannot be derived precisely from a coarse bucket table alone.

### 2.3. Percentiles Cannot Be Summed or Averaged to Aggregate

Do not average replica p99 values to produce a cluster-wide p99. For instance, replica A serves 1,000 requests with a p99 of 20 ms, while replica B serves 10,000 requests with a p99 of 200 ms. The average of the two p99s is 110 ms, which is not the p99 of all 11,000 requests.

To compute cluster-wide percentiles, merge histograms/buckets or combine raw samples across replicas within the same time window and metric definition. With Prometheus histograms, sum bucket rates by the le label and apply histogram_quantile. With client-side percentiles precomputed per process, the underlying distribution cannot be reconstructed for exact aggregation.

### 2.4. Sample Size and Reliability of p99

Tail percentiles require sufficient samples. With only 100 requests, p99 effectively hinges on the single slowest request. With 1,000 requests, the 1% tail holds roughly 10 samples. With 10,000 requests, there are roughly 100 samples in the 1% tail.

A practical rule of thumb is collecting at least tens of thousands of samples per key traffic segment when seeking stable p99 comparisons; the exact count required also depends on variance and the effect size you want to detect. This is a heuristic, not a statistical guarantee. For critical measurements, repeat multiple independent trials and estimate confidence intervals using bootstrapping or suitable statistical methods.

Do not compare the p99 of a 200-request trial against a 200,000-request trial and conclude one build is faster from a single number.

## 3. Defining Latency Measurement Boundaries

Latency depends on its start and end boundaries. Before collecting data, agree on measurement boundaries.

### 3.1. Client-side end-to-end latency

Client-side latency measures from when the load generator starts sending the request until it receives the complete response. It includes:

- Waiting time inside the load generator.
- DNS lookup if the client must resolve names.
- TCP and TLS handshakes if connections are not reused.
- Network round trip.
- Queueing at proxies/load balancers.
- Server-side processing duration.
- Response serialization and data transmission back to the client.

This perspective aligns closest with user experience, provided the load generator is not overloaded and clocks are accurate.

### 3.2. Server-side processing latency

Server-side latency measures from when the server receives the request or dispatches it into the handler until the handler completes. This metric helps isolate internal application issues from the network and load balancer.

If server-side p99 is low while client-side p99 is high, check proxy queueing, networking, the client, connection setup, or the load generator. If both are high, the cause likely sits inside the application, dependencies, or host resources.

### 3.3. Queueing latency

A request may sit in an accept queue, event loop, executor, or thread pool before the handler starts executing. Measuring only inside the handler can miss queueing latency.

When load exceeds processing capacity, queueing typically drives rapid spikes in p95/p99. Capture request arrival, processing start, and completion timestamps when the framework supports it.

### 3.4. Using a Monotonic Clock

To measure durations inside the JVM, use a monotonic clock like System.nanoTime(); do not subtract two System.currentTimeMillis() timestamps. The wall clock can jump due to NTP or administrative adjustments; a monotonic clock is designed for elapsed interval measurement.

Example:

~~~java
long started = System.nanoTime();
try {
    handleRequest();
} finally {
    long elapsedNanos = System.nanoTime() - started;
    requestTimer.record(elapsedNanos, TimeUnit.NANOSECONDS);
}
~~~

Do not mix durations recorded in nanoseconds, microseconds, and milliseconds without unit conversion. When storing histograms, maintain one uniform unit and document it clearly in the metric name or metadata.

## 4. Designing Measurements Specifically for CRaC Restore

A post-restore performance report should be split into distinct phases so it does not conceal behavior right after recovery.

### 4.1. Timeline Milestones

Record at a minimum:

| Milestone | Meaning |
|---|---|
| T0 | Restore command/API begins |
| T1 | Runtime finishes restore and application resumes execution |
| T2 | afterRestore callbacks start/finish |
| T3 | Mandatory dependencies have been verified |
| T4 | Readiness opens |
| T5 | First request is sent |
| T6 | First request completes |
| T7 | Steady-state window begins |
| T8 | Measurement window ends |

From these milestones, you can calculate:

\[
T_{restore} = T1 - T0
\]

\[
T_{restore\_to\_ready} = T4 - T1
\]

\[
T_{first\_request} = T6 - T5
\]

\[
T_{restore\_to\_first\_success} = T6 - T1
\]

Explicitly document how T1 is determined. Some engines do not expose a public callback at the exact moment runtime restore completes; in such cases, use the closest observable milestone and name the metric precisely, such as process-resumed-to-ready.

### 4.2. Splitting Measurement Windows

Report at least three separate windows:

1. **First-request window:** the first request and the initial group of requests immediately after readiness.
2. **Warm-up window:** the phase during which the application ramps up caches, connections, and processing capacity.
3. **Steady-state window:** the phase where stability criteria are met and the primary load is measured.

For example, a run might assign the first 100 requests to the first-request window, the next 2 minutes to warm-up, and the following 10 minutes to steady-state. These numbers are merely examples; choose windows matching your workload and real SLOs.

Do not drop the first-request window from the report. If the service receives traffic immediately after readiness, latency of the initial requests is part of production experience.

### 4.3. Measuring Before and After Readiness

If sending requests prior to readiness, the goal is verifying routing and proper request rejection while the instance is not yet ready. Do not mix 503 responses or timeouts from this phase into post-readiness business request latency.

Record separately:

- Timestamp when readiness closes.
- Timestamp when readiness opens.
- Requests rejected prior to readiness.
- First request routed after readiness.
- Elapsed time from restore to the first successful request.

Do not omit error responses from the overall report. You may exclude them from the latency distribution of successful requests if explicitly defined, provided error rates and error counts are reported separately so results are not artificially polished.

### 4.4. Comparing Against Cold Start and Warm Restart

To identify what CRaC improves, include at least three baselines:

- **Cold start:** normal JVM launch without restoring a checkpoint.
- **CRaC restore:** recovering from a checkpoint image.
- **Warm restart or steady instance:** an already-stabilized instance serving as a reference for latency free of startup effects.

Compare both restore-to-ready and request latency. CRaC can cut time to readiness while post-restore p99 still spikes if connection pools, caches, or credentials have not recovered cleanly.

## 5. Measuring Latency and Throughput in the Same Run

Latency and throughput must be measured within the same load window to understand their relationship.

### 5.1. Offered load and achieved throughput

Offered load is the rate at which the load generator attempts to dispatch requests. Achieved throughput is the rate at which requests actually complete.

Example:

- The load generator attempts to send 1,000 requests/second.
- The application completes 850 requests/second.
- 100 requests/second time out.
- 50 requests/second are missed or not generated due to generator overload.

Reporting only "850 RPS" is insufficient. Reports must present offered rate, completed rate, success rate, error rate, and dropped iterations.

### 5.2. Throughput Over a Time Window

If N requests complete over a W-second measurement window:

\[
Throughput = \frac{N}{W}
\]

For example, 60,000 requests completed in 60 seconds corresponds to 1,000 completed requests/second.

If counting only successful requests:

\[
Goodput = \frac{N_{success}}{W}
\]

Apply the same definition across all baselines. Never compare one run's completed throughput against another run's successful throughput.

### 5.3. Per-Replica and Cluster-Wide Throughput

Record:

- Per-replica RPS.
- Total cluster RPS.
- Successful RPS.
- Error RPS.
- Count of in-flight requests.
- Queue depth and count of rejected requests.

Aggregate throughput can climb even while one replica is overloaded or starved of traffic. Monitor per-replica request distribution to detect load imbalances.

### 5.4. Throughput Cannot Be Interpreted in Isolation

A system can boost RPS by raising concurrency at the cost of spiking p99. Once the server saturates, queues lengthen and requests wait longer. Therefore, every load point needs the full set of metrics:

- Offered RPS.
- Successful RPS.
- p50, p95, p99.
- Error/timeout rate.
- CPU, memory, GC, and thread/connection pools.
- Queue depth or in-flight requests.

The sustainable load operating point usually sits below saturation and satisfies latency and error-rate SLOs.

## 6. Choosing a Load Model: Open-Loop vs. Closed-Loop

The load model directly shapes the observed latency.

### 6.1. Closed-loop load

In closed-loop testing, a virtual user sends its next request only after the previous request completes. When the server slows down, the sending rate automatically drops. This model fits simulating interactive users waiting for a response before acting again.

The drawback is that under server overload, the load generator throttles its own offered rate. Results may fail to reflect the latency experienced by a continuous arrival stream.

### 6.2. Open-loop load

In open-loop testing, the load generator dispatches requests on a schedule independent of response time—for example, a fixed 500 requests/second even while the server slows down.

This model suits evaluating a system at a fixed arrival rate and exposing queueing. However, if the generator lacks resources, requests can queue inside the generator itself or be dropped. Monitor dropped iterations and whether requests dispatch on schedule.

### 6.3. Coordinated omission

Coordinated omission occurs when the load generator issues a new request only after the previous request finishes. When the server stalls, the generator pauses too; requests that would have arrived during the stall are missing from latency samples. Reported percentiles can look unrealistically good.

To minimize distortion:

- Use open-loop arrival rates when simulating continuous traffic.
- Choose tools that measure latency from scheduled send time or apply appropriate corrections.
- Report dropped/late iterations.
- Verify the generator is not CPU/network bottlenecked.
- If using closed-loop, label it clearly as a user-driven workload and do not interpret it as open-loop service capacity.

Do not simply toggle a correction flag and assume all skew disappears. Read the tool's documentation and verify how it computes latency.

## 7. Instrumentation in Java Applications

Latency can be collected using Micrometer Timer, OpenTelemetry Histogram, or a histogram library such as HdrHistogram. The goal is retaining sufficient fidelity to compute percentiles across time windows and request groups.

### 7.1. Using Micrometer Timer

Example with Micrometer:

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import java.util.concurrent.TimeUnit;

public final class RequestMetrics {
    private final Timer requestTimer;

    public RequestMetrics(MeterRegistry registry) {
        this.requestTimer = Timer.builder("orders.request.duration")
                .description("Thoi gian xu ly request Orders")
                .tag("operation", "create-order")
                .publishPercentileHistogram()
                .register(registry);
    }

    public void record(long startedNanos) {
        long elapsed = System.nanoTime() - startedNanos;
        requestTimer.record(elapsed, TimeUnit.NANOSECONDS);
    }
}
~~~

The example above produces histograms so backends like Prometheus can compute percentiles across buckets. Bucket configuration and SLA boundaries should match the service's latency range. Avoid adding unbounded tags such as user ID, order ID, or request ID, as they inflate cardinality.

### 7.2. Client-Side Percentiles and Histograms

Micrometer can publish percentiles precomputed per process via percentile configuration, yet standalone percentile values cannot be combined to form cluster-wide percentiles. When aggregating across multiple replicas, prefer aggregatable histograms/buckets.

Distinguish:

- Client-side percentile: computed on a single instance; useful when inspecting individual replicas.
- Histogram bucket: counts observations per bucket; aggregatable across replicas sharing the same bucket layout.
- Raw samples: offer maximum flexibility for percentile calculation, at high storage and transport cost.

### 7.3. OpenTelemetry Histogram

With OpenTelemetry, record durations using a Histogram instrument. Use consistent units, such as seconds, and attach bounded-cardinality attributes like route template, method, status class, or operation type.

Do not use full URLs containing dynamic IDs as attributes. Use route templates such as /orders/{id} instead. When exporting data, confirm the backend supports windowed histogram aggregation and quantile calculation.

### 7.4. Measuring on Both Client and Server

Maintain at least two metric layers:

- Client-side end-to-end duration to reflect user experience and queueing/network delays.
- Server-side handler duration to analyze internal application processing.

If proxies or gateways sit in front, capture upstream duration and queue duration as well. Keep metric names and boundaries clear so quantities with different definitions are never compared directly.

## 8. Computing p50, p95, and p99 with Prometheus Histograms

With the Micrometer Prometheus registry and histogram buckets, you can query via PromQL:

~~~promql
histogram_quantile(
  0.50,
  sum by (le) (
    rate(orders_request_duration_seconds_bucket[5m])
  )
)
~~~

~~~promql
histogram_quantile(
  0.95,
  sum by (le) (
    rate(orders_request_duration_seconds_bucket[5m])
  )
)
~~~

~~~promql
histogram_quantile(
  0.99,
  sum by (le) (
    rate(orders_request_duration_seconds_bucket[5m])
  )
)
~~~

These examples compute cluster-wide percentiles by aggregating buckets across replicas. To inspect individual instances, preserve the instance label inside the sum:

~~~promql
histogram_quantile(
  0.99,
  sum by (instance, le) (
    rate(orders_request_duration_seconds_bucket[5m])
  )
)
~~~

Actual metric names depend on naming conventions and the registry. Check the metrics endpoint to confirm exact names and units. Histogram quantile is a bucket-based approximation; accuracy depends on bucket boundaries and the distribution of observations.

### 8.1. Measuring Throughput with Counters

If the Timer exposes count:

~~~promql
sum(rate(orders_request_duration_seconds_count[1m]))
~~~

The result yields completed observations per second if the Timer records once per completed request.

To count only successful requests, use a metric tagged with outcome/status or a dedicated counter. Example:

~~~promql
sum(
  rate(http_server_requests_seconds_count{status=~"2.."}[1m])
)
~~~

The status label name depends on instrumentation. Verify actual label names and define "success" per the API contract; some systems treat 3xx or specific business responses as successful.

### 8.2. Error rate

Example 5xx response ratio:

~~~promql
sum(rate(http_server_requests_seconds_count{status=~"5.."}[5m]))
/
sum(rate(http_server_requests_seconds_count[5m]))
~~~

Client-side timeouts may not appear as server 5xx responses. Also track timeouts and dropped requests from the load generator. Do not conclude the error rate is zero solely because the server logs no 5xx errors.

### 8.3. Do Not Aggregate Precomputed Percentiles

Avoid expressions such as:

~~~promql
avg by (cluster) (instance_request_p99)
~~~

to represent cluster-wide p99. Aggregate histogram buckets first and compute the quantile afterward as shown above. If only summary/client-side percentiles exist without histograms, report per-replica percentiles or collect raw samples on the measurement side.

## 9. Using a Load Generator to Measure Post-Restore Performance

You can use k6, Gatling, wrk2, or equivalent tools. Choose the tool based on workload and load generation needs:

- HTTP API: k6, Gatling, wrk2.
- gRPC: tools supporting the corresponding protocol and concurrency model.
- Message consumers: producer/consumer load harnesses measuring processing rate and end-to-end event latency.
- Method/JVM microbenchmarks: JMH; never use JMH as a substitute for network-based service benchmarks.

### 9.1. k6 Example with a Constant Arrival Rate

Illustrative script:

~~~javascript
import http from 'k6/http';
import { check } from 'k6';

export const options = {
  scenarios: {
    restored_service: {
      executor: 'constant-arrival-rate',
      rate: 300,
      timeUnit: '1s',
      duration: '5m',
      preAllocatedVUs: 50,
      maxVUs: 300,
    },
  },
  thresholds: {
    http_req_failed: ['rate<0.01'],
    http_req_duration: [
      'p(95)<150',
      'p(99)<300',
    ],
  },
};

export default function () {
  const response = http.get(
    'http://service-under-test/health/business'
  );
  check(response, {
    'status is successful': (r) => r.status === 200,
  });
}
~~~

This example checks a simple endpoint. In real benchmarks, target representative endpoints, realistic payloads, and proper test data. Never use a lightweight health endpoint to represent an order-creation flow backed by databases and brokers.

In k6, Trend metrics such as http_req_duration can display p50, p95, and p99 in the summary. Save the JSON summary or time-series output to compare runs. Watch dropped_iterations, VUs, and generator errors; if the generator fails to sustain the target arrival rate, results do not reflect the intended load.

### 9.2. Separating First-Request and Steady-State Scenarios

Do not run a single script and dump all requests into one percentile if the goal is comparing phases. Tag phases such as:

- first_request
- warmup
- steady_state

Or run separate scenarios and save outputs by phase name. Ensure the first-request test genuinely starts right after replica readiness, and the steady-state test begins only after warm-up conditions are satisfied.

### 9.3. Multi-Replica Testing

In a multi-replica environment:

- Send traffic through the load balancer to measure cluster experience.
- Send traffic directly to individual replicas to measure inter-instance variance.
- Keep workload and arrival rate identical across baseline comparisons.
- Record how many replicas remained actually ready throughout the measurement window.
- Monitor load balancing and request counts per replica.

If one replica just restored while sibling replicas are already steady, measure the newly restored replica's latency separately from cluster-wide latency. Those two numbers answer two distinct questions.

## 10. Constructing a Representative Workload

A benchmark is meaningful only when its workload reflects real behavior.

### 10.1. Choosing the Request Mix

Define proportions for:

- Cache-read requests.
- Database-read requests.
- Database-write requests.
- Requests calling external services.
- Requests with large payloads.
- CPU-intensive requests.
- Multi-step business requests.

Do not benchmark a static endpoint and extrapolate that the entire application is faster. CRaC can improve startup, yet it does not change the cost of database queries or external APIs.

### 10.2. Payloads and Data

Keep payload sizes, data distributions, and cache hit ratios consistent across runs. If the dataset is too small and fits entirely in cache, results may not represent production. If each run uses different data, variations may arise from data locality rather than restore.

### 10.3. Concurrency and Arrival Rate

Test multiple load levels:

- Low load to measure baseline latency.
- Moderate load near normal operating levels.
- High load near saturation.
- Overload beyond capacity to observe how the system degrades.

At each load point, record latency, throughput, errors, CPU, and queue depth. Never compare p99 at 100 RPS against p99 at 2,000 RPS and attribute the entire difference to CRaC.

### 10.4. Keeping Dependencies Consistent

Databases, brokers, caches, external APIs, and networking must share identical configurations across comparative runs. If a dependency restarts or experiences varying background contention, post-restore latency will be skewed.

For tests specifically targeting dependency recovery, deliberately alter the dependency during downtime and report it as a separate fault scenario. Never blend fault scenarios into baseline benchmarks.

## 11. Recommended Benchmarking Workflow

A benchmark run can be structured into the following steps.

### Step 1: Record the Environment

Record:

- JDK vendor, version, build, and CRaC engine.
- Application version, commit, and checkpoint image digest.
- CPU model, core count, memory, and kernel.
- Container limits and cgroup CPU/memory quotas.
- Runtime, orchestration, and node type.
- Database, broker, cache, and dependency versions.
- JVM flags, GC, heap size, and thread/connection pool settings.
- Network topology and load generator version.

### Step 2: Create Checkpoint

1. Launch the application.
2. Execute warm-up following the defined procedure.
3. Verify application state is suitable for checkpointing.
4. Create the checkpoint image.
5. Record digest and logs.

### Step 3: Restore and Wait for Readiness

1. Restore from the reference image.
2. Record runtime resume timestamp.
3. Record afterRestore callbacks and resource recreation duration.
4. Verify dependency health.
5. Record readiness-open timestamp.

### Step 4: Measure First-Request

Send a small request window right after readiness. Save per-request latencies or a separate histogram, response statuses, errors, and timeouts. Note explicitly whether connections are reused.

### Step 5: Measure Warm-Up

Run the warm-up workload per production policy. Track cache hits, pool sizes, CPU, GC, and latency across consecutive windows. Mark when the application satisfies steady-state conditions.

### Step 6: Measure Steady-State

Run the workload at predefined arrival rates over a sufficiently long window. Collect p50, p95, p99, successful throughput, error rate, dropped iterations, CPU, memory, GC, and queue depth.

### Step 7: Repeat

Repeat multiple independent trials. Whenever possible, interleave cold-start baselines and CRaC restores to mitigate effects from shifting system load or time-of-day variance.

### Step 8: Aggregate

Compute percentiles per phase, per endpoint, and cluster-wide. Compare using identical definitions, identical load, and identical windows. Report sample counts and confidence intervals where appropriate.

## 12. Comparing Against Baselines and Computing Improvements

To compare CRaC with cold start, keep workload and environment identical.

### 12.1. Sample Comparison Table

| Metric | Cold start | CRaC restore | Change |
|---|---:|---:|---:|
| Restore/start-to-ready | 8.2 s | 1.4 s | -82.9% |
| First-request p50 | 24 ms | 20 ms | -16.7% |
| First-request p95 | 110 ms | 95 ms | -13.6% |
| First-request p99 | 340 ms | 290 ms | -14.7% |
| Steady-state p50 | 14 ms | 14 ms | Unchanged |
| Steady-state p95 | 48 ms | 49 ms | +2.1% |
| Steady-state p99 | 130 ms | 135 ms | +3.8% |
| Successful throughput | 900 RPS | 895 RPS | -0.6% |

Numbers in the table are illustrative only. They demonstrate how CRaC can improve readiness time and first-request latency while steady-state remains essentially unchanged. Cases can also occur where restore-to-ready drops sharply while p99 rises because callbacks open connections in bursts or caches remain unwarmed.

### 12.2. Calculating Percentage Improvement

For a metric where lower values are better, percentage reduction:

\[
Improvement(\%) =
\frac{Baseline - New}{Baseline} \times 100
\]

For throughput, higher values are generally better:

\[
ThroughputGain(\%) =
\frac{New - Baseline}{Baseline} \times 100
\]

Do not apply the same formula blindly to every metric. For error rate, dropped iterations, and resource consumption, specify clearly which direction is favorable and check SLOs.

### 12.3. Interpreting Results Phase by Phase

If restore-to-ready drops while first-request p99 climbs, the application may be opening readiness before connection pools or caches are truly ready. If first-request looks good yet steady-state throughput drops, examine resource limits, pool sizes, GC, CPU quotas, and load balancing.

If p50 improves while p99 worsens, the majority of requests may run faster while a small subset suffers from connection creation, locks, GC, or dependency retries. Analyze histograms and traces of slow requests rather than looking at one percentile.

## 13. Analyzing Post-Restore Tail Latency

Tail latency often reveals issues hidden by p50.

### 13.1. Simultaneous Connection Pool Recreation

After restore, concurrent requests may simultaneously trigger connection creation. If the database caps connections, some requests must wait on the pool or handshakes. Monitor:

- Active/idle/pending connections.
- Connection creation duration.
- Pool acquire latency.
- Database connection limits and server load.
- Errors/timeouts while the pool is unready.

You can pre-warm a subset of connections before readiness if policy allows, while avoiding opening excessive cluster-wide connections simultaneously.

### 13.2. Post-Restore Cache Misses

Caches may be snapshotted with stale entries or invalidated upon restore. If many replicas reload caches concurrently after restore, the backing data source can face a traffic spike.

Monitor cache hit ratio, load duration, refresh count, and request latency by cache state. If caches populate asynchronously, readiness must reflect whether those caches are mandatory for serving.

### 13.3. Garbage Collection and Memory Pressure

Restoring can place the heap into a different state from cold start. As load rises, allocation bursts or cache refreshes can trigger GC pauses and elevate p99.

Monitor:

- GC pause duration and frequency.
- Allocation rate.
- Heap occupancy.
- Old generation pressure.
- CPU throttling.
- Container memory limits and OOM events.

Do not blame GC solely because p99 rises around a GC event. Use GC logs, JFR, or telemetry to correlate directly with slow requests.

### 13.4. JIT and Class Loading

Some code paths may not have executed prior to checkpoint or may need further optimization after restore. Early requests can trigger class loading, initialization, or compilation. Measure latency against request count/elapsed time after readiness to see whether this effect subsides.

Do not merge initial requests into steady-state when analyzing warm-up. Conversely, if production routes traffic immediately upon readiness, do not ignore first-request latency in SLOs.

### 13.5. Dependency Recovery and Retry Storms

When many replicas restore together, they may simultaneously fetch tokens, open connections, join broker consumer groups, or load caches. Overloaded dependencies produce tail latency and retry storms.

Test restoring in batches and staggered waves. Track request rates toward dependencies, errors, retries, and readiness times. Jitter/backoff and concurrency caps help dampen recovery bursts.

## 14. Controlling Error and Ensuring Repeatability

Benchmarks can be influenced by CPU frequency scaling, background load, GC, filesystem caches, networking, database load, and the load generator itself.

### 14.1. Controlling the Environment

- Use the same node type, CPU quota, and memory limit.
- Keep JDK, GC, JVM flags, and dependency versions identical.
- Use the same checkpoint image digest across restore runs being compared.
- Maintain databases, brokers, and caches in equivalent states.
- Ensure the load generator does not share a saturated CPU with the service if that distorts measurements.
- Record CPU throttling, noisy neighbors, and network congestion.

### 14.2. Independent Repetitions

Run multiple independent trials for both cold start and CRaC restore. Each trial should have its own checkpoint/restore lifecycle; do not slice multiple windows from the same process and treat them as independent trials.

Aggregate:

- Median across trial-level p50/p95/p99.
- Min/max range or confidence intervals.
- Sample count per trial.
- Average throughput and variance.
- Error rate and dropped count.

Do not report only the best trial. If trials fluctuate widely, investigate root causes before drawing conclusions.

### 14.3. Bootstrap confidence interval

When raw latency samples are available, bootstrapping can estimate confidence intervals for p95/p99:

1. Sample randomly with replacement from the request latency dataset.
2. Compute the target percentile for the bootstrap sample.
3. Repeat many iterations.
4. Take the quantiles of the resulting bootstrap percentile distribution as the confidence interval.

For time-correlated data, sampling individual requests independently can underestimate variance. Block bootstrapping or trial/window-level analysis may be needed to preserve temporal structure.

### 14.4. Clocks and Cross-Machine Timestamps

Never subtract wall-clock timestamps from two machines without verified clock synchronization. For end-to-end timings, prefer durations measured by a single load generator from send to response completion. For correlating traces across hosts, use a tracing system and clock synchronization, avoiding distributed timestamps as primary duration measurements unless clock skew has been assessed.

## 15. Common Measurement Pitfalls

| Mistake | Consequence | Fix |
|---|---|---|
| Measuring only JVM restore time | Omits bootstrap and readiness time | Measure restore-to-ready and first-success separately |
| Measuring only p50 | Conceals tail latency | Report p50, p95, and p99 alongside error rate |
| Averaging replica p99s | Does not yield cluster-wide p99 | Merge histogram buckets or raw samples |
| Using too few samples | Unstable p99 | Increase sample counts and run multiple trials |
| Failing to separate first-request from steady-state | Warm-up gets hidden inside one number | Tag phases and measure separate windows |
| Counting only successful requests | Ignores timeouts and errors | Report success latency together with error/timeout rate |
| Using closed-loop yet interpreting as open-loop | Coordinated omission makes latency appear lower | Choose the right load model and state it clearly |
| Overloaded load generator | Planned offered rate is never met | Track dropped iterations and generator resources |
| Measuring only server handler | Misses queues, network, and proxies | Measure client-side end-to-end latency too |
| Failing to hold workload constant | Unfair comparisons | Keep request mix, payloads, data, and rate fixed |
| Merging replicas with vastly different request counts without weighted histograms | Skewed cluster percentiles | Aggregate bucket counts/rates properly |
| Omitting sample counts | Difficult to assess statistical reliability | Save counts and window durations |
| Reporting only total RPS | May include error responses | Report completed RPS, successful RPS, and error rate |
| Ignoring CPU throttling | Misattributes bottlenecks to CRaC | Record quotas, throttling, and node load |
| Using wall clock for JVM durations | Clock adjustments corrupt durations | Use System.nanoTime() |

## 16. Example Post-Restore Monitoring Dashboard

A post-restore performance dashboard can be organized into four panels.

### 16.1. Recovery timeline

- Restore duration.
- Restore-to-ready duration.
- Callback duration per Resource.
- Pool/client recreation duration.
- Time to first successful request.

### 16.2. Latency

- p50, p95, p99 by route/operation.
- Client-side end-to-end latency.
- Server-side handler latency.
- First-request window.
- Warm-up window.
- Steady-state window.

### 16.3. Throughput and Reliability

- Offered RPS.
- Completed RPS.
- Successful RPS/goodput.
- Error and timeout rate.
- Dropped/late iterations.
- In-flight requests and queue depth.

### 16.4. Resources and Dependencies

- CPU, memory, heap, and GC.
- Connection pool active/idle/pending.
- Cache hit ratio.
- Database/broker latency.
- Retry count and circuit breaker state.
- CPU throttling and network errors.

Dashboards should support filtering by service, replica, version, checkpoint image digest, and test run. Avoid using request IDs or user IDs as high-cardinality metric labels.

## 17. Sample Benchmark Report Template

A report should record complete configuration for reproducibility:

~~~text
Test run ID:
Date/time:
Application version/commit:
Checkpoint image digest:
JDK vendor/version/build:
CRaC engine:
Kernel/container runtime:
Node CPU/memory:
Container CPU/memory limits:
JVM flags/GC:
Dependency versions:
Load generator/version:
Workload mix:
Offered arrival rate:
Concurrency:
Warm-up policy:
Steady-state condition:
Measurement window:
Sample count:

Recovery:
- Restore duration:
- Restore-to-ready:
- Time to first successful request:

First-request window:
- p50:
- p95:
- p99:
- successful throughput:
- error/timeout rate:

Warm-up window:
- p50:
- p95:
- p99:
- successful throughput:
- error/timeout rate:

Steady-state window:
- p50:
- p95:
- p99:
- completed throughput:
- successful throughput:
- error/timeout rate:
- dropped iterations:

Resources:
- CPU:
- memory/heap:
- GC pause:
- connection pool:
- cache hit ratio:
- queue depth:

Baseline:
- cold start:
- CRaC restore:
- trial count:
- confidence interval/variance:

Conclusion:
- SLO met/missed:
- Notable differences:
- Measurement limitations:
~~~

Do not save only dashboard screenshots. Store raw results, histograms, load generator summaries, lifecycle logs, and configurations so percentile calculations can be audited.

## 18. Acceptance Criteria for Post-Restore Performance

Criteria must align with the application's SLOs. The examples below are templates; replace thresholds with targets suited to your workload.

**AC-01 — Readiness**

- Condition: restore from the standard checkpoint image.
- Result: readiness opens within the agreed restore-to-ready threshold.
- Evidence: timestamps for runtime resume, callbacks, dependency health, and readiness transition.

**AC-02 — First-request latency**

- Condition: dispatch at least N requests right after readiness.
- Result: p50/p95/p99 meet first-request SLO thresholds; errors and timeouts are reported separately.
- Evidence: raw latencies or histogram with sample count.

**AC-03 — Steady-state latency**

- Condition: application meets warm-up criteria and receives fixed offered load.
- Result: p50/p95/p99 meet thresholds over the defined measurement window.
- Evidence: histogram, sample count, load generator rate, and error rate.

**AC-04 — Throughput**

- Condition: run workload at predefined arrival rate.
- Result: successful throughput reaches minimum target while error rate and tail latency remain within SLO.
- Evidence: completed/successful request counts, dropped iterations, and server metrics.

**AC-05 — No abnormal degradation across replicas**

- Condition: restore multiple replicas from the same image and distribute traffic via a load balancer.
- Result: no replica exhibits unexplained p99 or error rate breaches.
- Evidence: per-instance histograms, request distribution, and resource metrics.

**AC-06 — Fair comparison against baseline**

- Condition: cold start and CRaC restore use identical workload, node class, dependencies, and load generator.
- Result: report presents restore-to-ready, first-request, steady-state p50/p95/p99, and goodput under identical definitions.
- Evidence: configuration, image digest, raw results, and trial count.

A benchmark passes only when latency, throughput, and error rate all satisfy criteria. High throughput with SLO-breaching p99 or high error rates is not a passing outcome.

## 19. Investigation Workflow When Results Fall Short

If p50, p95, or p99 is worse than target:

1. Confirm the load generator delivered the full offered rate without saturating.
2. Confirm sample counts and measurement windows are sufficiently large.
3. Compare client-side vs. server-side latency to isolate network/queue vs. handler.
4. Inspect per-instance and per-route histograms to spot anomalous replicas or operations.
5. Correlate slow requests with GC, CPU throttling, queue depth, and pool acquisition.
6. Check whether afterRestore callbacks perform heavy synchronous work before readiness.
7. Inspect cache warm-up, token refreshes, connection creation, and broker rebalances.
8. Check for retry storms or dependency saturation when multiple replicas restore simultaneously.
9. Re-run benchmarks changing one variable at a time to isolate root causes.

If throughput is low:

- Check offered rate, dropped iterations, and VUs/concurrency.
- Check CPU quotas, memory pressure, and GC.
- Check thread pools, connection pools, and queue capacities.
- Check whether the database/broker is the bottleneck.
- Check whether load balancing distributes requests evenly.
- Check whether the application is failing fast instead of completing business logic.

Do not optimize solely for p99 if the real issue lies in throughput or error rate. One tuning change might improve percentiles while cutting goodput, or vice versa.

## 20. Key Principles to Remember

- Separate restore duration, restore-to-ready, first-request, warm-up, and steady-state latency.
- p50 describes the median, while p95 and p99 capture tail latency; report all three with sample counts.
- Never average replica percentiles to obtain cluster-wide percentiles; merge histogram buckets or raw samples.
- Use a monotonic clock like System.nanoTime() to measure durations inside the JVM.
- Measure both client-side end-to-end and server-side processing when diagnosing root causes.
- Report offered rate, completed throughput, successful throughput, error rate, and dropped iterations separately.
- Pick open-loop or closed-loop based on goals; watch out for coordinated omission.
- Separate first-request and warm-up from steady-state without dropping them from reports.
- Use histograms with suitable buckets so percentiles aggregate cleanly across multiple replicas.
- Hold workload, dependencies, nodes, JDK, GC, container limits, and load generator constant across baselines.
- Repeat multiple trials and report variance/confidence intervals when comparing p95/p99.
- Conclude that CRaC improves performance only when latency, throughput, and error rate are measured under identical contracts and SLOs.

Measuring p50, p95, p99, and throughput after restore determines whether an application recovers rapidly and serves steadily. By cleanly separating recovery, first-request, warm-up, and steady-state phases while controlling the load model and histogram aggregation, teams can evaluate CRaC benefits with reproducible numbers rather than merely feeling that the JVM started faster.
