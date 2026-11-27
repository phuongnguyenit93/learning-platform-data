# Histograms in Micrometer and Spring Boot

A `POST /orders` API with an average processing time of 180 ms looks fast, yet that average can hide customers waiting 2–3 seconds. To understand **latency distribution**, you need to observe not just a single mean, but the proportion of requests falling into different time ranges. A **Histogram** is the right tool for that job.

In the **SPRING_BOOT_OBSERVABILITY** module, histograms are part of **metrics foundation** when establishing observability for Spring Boot using Micrometer Observation, metrics, logs, and distributed tracing. From histograms, operations teams can estimate p95/p99, measure threshold compliance rates, evaluate SLOs, and detect *tail latency* slowdowns. Combining metrics with logs and traces moves investigations from "how many requests are slow?" to "which component slowed down a request and why?"

## Learning Objectives

After this lesson, you will be able to:

1. Explain histograms, buckets, sample counts, and the meaning of cumulative buckets in Prometheus.
2. Distinguish histograms from averages, client-side percentiles, and measurements via `Timer` and `DistributionSummary`.
3. Enable histograms for HTTP and business metrics in Spring Boot/Micrometer.
4. Use PromQL to compute p95/p99, request rate, and the percentage of requests meeting an SLO threshold.
5. Choose sensible bucket boundaries, control series count, and recognize accuracy limits.
6. Interpret data properly when trace sampling, exporters, or context propagation have issues.
7. Test, deploy, and use histograms to investigate real-world application latency.

## 1. What Does a Histogram Express?

Suppose we measure the duration of 10 order-creation requests (each number is one sample, in ms):

~~~text
40, 55, 80, 90, 120, 150, 200, 270, 420, 1800
~~~

The mean is **322.5 ms**, yet 9 requests are under 500 ms and one very slow request took 1,800 ms. Watching only the average makes it hard for operators to see how the tail shifted.

A histogram divides the value axis into **buckets** with defined boundaries. With boundaries at 100, 300, and 500 ms:

| Non-Overlapping Interval | Requests in Interval | Cumulative Count up to Boundary |
| --- | ---: | ---: |
| ≤ 100 ms | 4 | 4 |
| (100, 300] ms | 4 | 8 |
| (300, 500] ms | 1 | 9 |
| > 500 ms | 1 | 10 |

These values are hypothetical data used throughout the conceptual section. A different tool may pick different bucket boundaries, altering the granularity observed.

**Cumulative buckets** mean the ≤ 300 ms bucket **already includes** requests ≤ 100 ms. Thus cumulative counts are always non-decreasing as boundaries grow. Never sum all cumulative buckets together to get total requests, as that would count each request multiple times.

~~~mermaid
flowchart LR
    A["10 duration measurements"] --> B["≤ 100 ms: 4"]
    A --> C["≤ 300 ms: 8"]
    A --> D["≤ 500 ms: 9"]
    A --> E["+Inf: 10"]
    B -. "Included in" .-> C
    C -. "Included in" .-> D
    D -. "Included in" .-> E
~~~

In a **Prometheus classic histogram**, each bucket carries an `le` (*less than or equal*) label: `le="0.1"` means values not exceeding **0.1 seconds**. The `le="+Inf"` bucket holds the total samples across the entire distribution, matching the `_count` counter under consistent data. For timers, Micrometer normally exports Prometheus's base time unit of **seconds**, even when Java code records `Duration.ofMillis(100)`.

### 1.1. Components Typically Found in a Classic Histogram

For timing metric `http.server.requests` exported to Prometheus, an illustrative scrape looks like:

~~~text
http_server_requests_seconds_bucket{method="POST",uri="/orders",le="0.1"} 4
http_server_requests_seconds_bucket{method="POST",uri="/orders",le="0.3"} 8
http_server_requests_seconds_bucket{method="POST",uri="/orders",le="0.5"} 9
http_server_requests_seconds_bucket{method="POST",uri="/orders",le="+Inf"} 10
http_server_requests_seconds_count{method="POST",uri="/orders"} 10
http_server_requests_seconds_sum{method="POST",uri="/orders"} 3.225
~~~

This is **simulated output** with simplified labels and boundaries for readability; it is not a verbatim Spring Boot scrape. Real scrapes also include status, outcome, instance, application, and many more buckets. Total time `_sum` equals **3.225 seconds** because the 10 samples add up to 3,225 ms.

- `_bucket{le="..."}`: counter of observations not exceeding that threshold.
- `_count`: total number of observations.
- `_sum`: sum of observed values in the corresponding unit; seconds for Prometheus timers.
- `+Inf`: unbounded upper bucket ensuring values above the highest boundary are still counted.

Buckets, count, and sum are usually cumulative per-process counters over time. When analyzing rates over a window such as 5 minutes, use `rate(...)` or `increase(...)`; do not compare raw counts across processes with different start times.

> This section discusses **classic histograms with `_bucket` series**. Prometheus also supports **native histograms** with a different representation and query behavior. Do not apply classic histogram queries verbatim if your system exports or stores native histograms.

## 2. How Does a Histogram Differ from Averages, Percentiles, and Summaries?

| Representation | Answers Well | Multi-Instance Aggregation | Limitations |
| --- | --- | --- | --- |
| **Count / Sum / Average** | How many runs, total time, and mean? | Can sum count/sum then divide for mean | Hides distribution tail |
| **Client-side percentiles** | What is each instance's p95? | Cannot average instance p95s to get cluster p95 | Tied to each instance's window and data |
| **Classic histogram** | How many samples fall below thresholds? What is approx. p95? | Can sum matching buckets if boundaries match | Quantiles are interpolated, subject to bucket error |
| **Distributed trace** | Where did one specific request slow down? | Does not replace full-traffic statistics | Traces may be dropped by sampling |

A **percentile** is intuitively understood as follows: p95 is the mark below which roughly 95% of samples fall. p99 sits deeper in the tail. Percentiles reveal slow-request user experience, yet they **are not error rates** and do not automatically measure an SLO target.

In Micrometer:

- `publishPercentiles(0.95, 0.99)` requests exporting application-computed percentiles per registry/meter mechanism; do not sum or average percentiles across multiple instances.
- `publishPercentileHistogram()` requests exporting percentile histograms so supporting backends (such as Prometheus) can estimate quantiles after aggregating buckets.
- `serviceLevelObjectives(...)` adds buckets at specific business thresholds to measure; useful **even without enabling a full percentile histogram**, depending on registry support.

For example, instance A having p95 = 100 ms and instance B having p95 = 500 ms **does not mean** cluster p95 = 300 ms. Request counts and distribution shapes on each instance can differ dramatically. To get cluster-wide p95 with classic histograms, sum the **growth rates of each bucket** sharing the same `le` first, then pass them into `histogram_quantile`.

### 2.1. Percentiles Are Estimated, Not Individual Request Measurements

Imagine a histogram with only 100 ms and 1,000 ms buckets. If p95 lands in the second bucket, the backend knows it falls inside that range without knowing exact positions within it; functions like `histogram_quantile` perform **interpolation** to estimate the value.

Therefore:

- Coarser boundaries around the region of interest produce less precise p95/p99 estimates.
- Denser boundaries increase series count and storage/query costs.
- An exact SLO threshold, such as "at most 500 ms," should usually have a **bucket right at 500 ms** to measure threshold compliance directly rather than guessing from a percentile.

## 3. Histograms in Micrometer: Timer and DistributionSummary

Micrometer offers several `Meter` types. Two are commonly paired with histograms:

| Meter | What It Measures | Units and Examples |
| --- | --- | --- |
| `Timer` | Durations of **completed** operations | `http.server.requests`, `orders.checkout.duration` |
| `DistributionSummary` | Distribution of numerical values not necessarily representing time | Payload size (bytes), items per order |

A `Timer` records duration and completion counts. A `LongTaskTimer` tracks how many long tasks are still running and their current elapsed age, suited for work lasting minutes or hours; **do not replace a normal `Timer` with `LongTaskTimer` just to enable p95 histograms**.

### 3.1. Relationship with Micrometer Observation

In Spring Boot, **Micrometer Observation** connects to metrics via `MeterObservationHandler`. An Observation around a business operation can create a Timer per convention/handler settings. Histogram configuration should then target the **meter name** produced by that Observation.

~~~mermaid
flowchart TD
    Request["HTTP request or business operation"] --> Obs["Observation + Convention"]
    Obs --> MeterHandler["MeterObservationHandler / MeterRegistry"]
    MeterHandler --> Timer["Timer: count, sum, buckets"]
    Timer --> Prom["Prometheus scrape or metrics exporter"]
    Prom --> Dashboard["PromQL / SLO dashboard"]
    Obs --> TraceHandler["Tracing handler: spans"]
    TraceHandler --> OTLP["OTLP exporter → Trace backend"]
    Request --> Log["Application logs"]
    OTLP -. "Trace ID" .-> Log
~~~

Do not unintentionally create both a **manual Timer** and an **Observation Timer** for the **same operation, same name, and same semantics**: data could be double-counted. Establish one primary instrumentation path and use traces/logs for additional context.

## 4. Enabling Histograms for HTTP in Spring Boot

With **Spring Boot 3.x** and managed compatible dependencies, you can use Actuator and the Prometheus registry:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'
}
~~~

Example `application.yml` for a test environment:

~~~yaml
spring:
  application:
    name: order-service

management:
  endpoints:
    web:
      exposure:
        include: "health,prometheus"
  metrics:
    distribution:
      percentiles-histogram:
        http.server.requests: true
      slo:
        http.server.requests: 100ms, 300ms, 500ms, 1s
      minimum-expected-value:
        http.server.requests: 1ms
      maximum-expected-value:
        http.server.requests: 5s
~~~

Each property serves a distinct role:

- **`percentiles-histogram`:** enables buckets supporting quantile estimation in compatible backends. Histograms export only when supported by the registry.
- **`slo`:** adds boundaries at 100, 300, **500 ms**, and 1 second to directly measure requests meeting key milestones. In some versions/registries these are also referred to as service-level-objective boundaries.
- **`minimum-expected-value` / `maximum-expected-value`:** bounds the generated bucket range for percentile histograms to avoid creating unneeded buckets. They are not rules that drop slow requests beyond max; `_count` and `+Inf` must still be interpreted per exporter behavior.
- **`exposure`:** allows access to `/actuator/prometheus`. In production, restrict this endpoint by network and access controls.

For HTTP server data, the Micrometer meter name is typically `http.server.requests`; Prometheus commonly normalizes it to `http_server_requests_seconds_*`. **Exact names depend on your Spring Boot/Micrometer versions and configuration**. Before building dashboards, verify actual names at `/actuator/prometheus`.

### 4.1. Local Verification Steps

1. Start the application with the Prometheus registry.
2. Send several fast and slow requests to `POST /orders` (you can simulate delays with a stubbed dependency).
3. Open `http://localhost:8080/actuator/prometheus`; locate `http_server_requests_seconds_bucket`, `_count`, and `_sum`.
4. Verify a `le="0.5"` bucket exists for the configured 500 ms threshold.
5. Inspect actual `method`, `uri`, `status`, and `outcome` labels to learn how to filter queries.

Illustrative command:

~~~bash
curl -s http://localhost:8080/actuator/prometheus
~~~

If expected route series are absent, confirm requests actually arrived, HTTP instrumentation is enabled, no filter denied the meter, and the registry/exporter supports histograms. An endpoint returning data locally does not prove an external Prometheus server is scraping successfully.

### 4.2. Should You Enable Histograms for Every Metric?

Usually **no**. Each histogram has many buckets, and each bucket multiplies across every tag combination. Enabling them globally in a large system can sharply increase metrics cost.

Prioritize operations affecting user experience: critical HTTP routes, dependency calls with explicit SLOs, message processing, or business steps needing tail monitoring. For measurements needing only count or average, a histogram adds little value.

## 5. Creating a Histogram for a Business Timer

When an operation is not auto-instrumented at the desired boundary, create a dedicated Timer. The example below measures **order confirmation duration**, excluding the outer HTTP request overhead.

~~~java
package com.example.orders.metrics;

import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.stereotype.Service;

import java.time.Duration;

@Service
public class CheckoutService {
    private final Timer checkoutTimer;
    private final CheckoutGateway gateway;

    public CheckoutService(MeterRegistry registry, CheckoutGateway gateway) {
        this.gateway = gateway;
        this.checkoutTimer = Timer.builder("orders.checkout.duration")
                .description("Time to confirm an order")
                .tag("operation", "checkout")
                .publishPercentileHistogram()
                .serviceLevelObjectives(
                        Duration.ofMillis(250),
                        Duration.ofMillis(500),
                        Duration.ofSeconds(1))
                .minimumExpectedValue(Duration.ofMillis(1))
                .maximumExpectedValue(Duration.ofSeconds(5))
                .register(registry);
    }

    public void checkout(String checkoutReference) {
        // checkoutReference must never be attached as a metric tag.
        checkoutTimer.record(() -> gateway.confirm(checkoutReference));
    }
}

interface CheckoutGateway {
    void confirm(String checkoutReference);
}
~~~

Points to understand:

1. `orders.checkout.duration` is a stable name for the business operation. Per-call identifiers never belong in the name.
2. `publishPercentileHistogram()` requests backend-friendly histogram export; `serviceLevelObjectives(...)` adds business thresholds.
3. `minimumExpectedValue(...)` and `maximumExpectedValue(...)` bound histogram buckets; pick values matching expected latency.
4. `Timer.record(Runnable)` measures callback runtime; if the callback throws an exception, the exception still propagates after Timer records the duration.
5. A Timer **does not automatically supply an error rate** merely from callbacks throwing exceptions. To track errors, use HTTP outcome signals, a separate counter, observation/tracing errors, or explicit outcome classification.

This is a **manual Timer** example. If the app already has a custom `Observation` with a metrics handler for `orders.checkout.duration`, standardize on one mechanism to avoid double-counting. In apps with many operations, creating `Timer` instances and tags consistently via `MeterRegistry` or a `MeterBinder` can be cleaner.

### 5.1. When to Use `DistributionSummary`?

For numerical quantities such as payload size in bytes, use `DistributionSummary`:

~~~java
import io.micrometer.core.instrument.DistributionSummary;
import io.micrometer.core.instrument.MeterRegistry;

DistributionSummary payloadSize = DistributionSummary
        .builder("orders.request.payload")
        .baseUnit("bytes")
        .description("Incoming order payload size in bytes")
        .publishPercentileHistogram()
        .serviceLevelObjectives(1024, 4096, 16384)
        .register(registry);

payloadSize.record(2048);
~~~

Here `registry` is an injected or application-provided `MeterRegistry`. The value `2048` means 2,048 bytes. Never use `Timer` to measure bytes, or `DistributionSummary` to measure time when `Timer` fits better. For very large or very small values, configure `scale`, expected-value bounds, and suitable buckets to optimize the histogram.

## 6. Reading Histograms with PromQL

The examples below target a **Prometheus classic histogram** exported from the HTTP timer. Assumptions:

- The HTTP meter has Prometheus name `http_server_requests_seconds`.
- The route is normalized to `uri="/orders"` with `method="POST"`.
- Histograms are enabled and traffic is sufficient for quantile estimation.
- A bucket exists at `le="0.5"` from configuring a 500 ms threshold.

Always adjust labels to your live data, and use the **exact same request scope** for SLI numerators and denominators.

### 6.1. Requests per Second

~~~promql
sum(
  rate(http_server_requests_seconds_count{
    method="POST", uri="/orders"
  }[5m])
)
~~~

`_count` rises as more requests are recorded. `rate(...[5m])` computes average per-second growth over 5 minutes while accounting for restarts/resets. Use `increase(...[5m])` when estimating total occurrences over a window.

### 6.2. Average Latency

~~~promql
sum(rate(http_server_requests_seconds_sum{
  method="POST", uri="/orders"
}[5m]))
/
sum(rate(http_server_requests_seconds_count{
  method="POST", uri="/orders"
}[5m]))
~~~

Output is in **seconds**. Handle zero-denominator cases on low-traffic dashboards. Averages help track overall serving time, yet do not replace quantiles and threshold compliance ratios.

### 6.3. Cluster-Wide p95

~~~promql
histogram_quantile(
  0.95,
  sum by (le) (
    rate(http_server_requests_seconds_bucket{
      method="POST", uri="/orders"
    }[5m])
  )
)
~~~

Interpretation:

1. `rate(..._bucket[5m])` computes the per-second growth rate of **each bucket** in each series.
2. `sum by (le)` sums matching buckets across all filtered instances/statuses.
3. `histogram_quantile(0.95, ...)` estimates p95 from the summed buckets.

For p99, replace `0.95` with `0.99`. Never use `avg(p95_instance)` to approximate cluster p95. For p95 per route, keep `uri` in the grouping:

~~~promql
histogram_quantile(
  0.95,
  sum by (le, uri) (
    rate(http_server_requests_seconds_bucket{method="POST"}[5m])
  )
)
~~~

Querying by route requires `uri` to have a bounded value set, normally a route template (e.g., `/orders/{id}`), never raw URLs containing dynamic IDs.

### 6.4. Share of Requests Completing Within 500 ms

Suppose the SLI is **the proportion of all instrumented `POST /orders` requests completing in at most 500 ms**, without excluding HTTP error statuses. When an exact `le="0.5"` bucket exists:

~~~promql
sum(
  rate(http_server_requests_seconds_bucket{
    method="POST", uri="/orders", le="0.5"
  }[30m])
)
/
sum(
  rate(http_server_requests_seconds_count{
    method="POST", uri="/orders"
  }[30m])
)
~~~

For example, `0.992` equals **99.2%** of requests meeting the threshold in that window. If the SLO targets 99% of requests ≤ 500 ms, this ratio can serve as the latency SLI.

If the SLI counts only valid requests or separates successes from failures, define that rule explicitly and **apply identical filters** to numerator and denominator. To combine both success and timeliness, design a histogram carrying outcome/status labels or dedicated event counters; never assume "fast" automatically means "successful."

### 6.5. Why Should p95 Alone Not Define an SLO?

"p95 under 500 ms" and "99% of requests under 500 ms" are **two different commitments**. A p95 is a quantile; it does not accurately measure compliance with a fixed threshold when bucket boundaries are coarse. For an SLO anchored on a 500 ms deadline, an exact 500 ms bucket is usually better.

In practice, specify calculations over 7/28/30-day windows, valid traffic scope, and error-budget burn alerts. A 5-minute query helps with diagnostics, yet can be noisy on low-traffic services.

## 7. How Should You Choose Buckets?

Buckets are a **technical design decision** tied directly to the thresholds operators must answer. There are two common situations:

1. **Fixed SLO:** "99% of requests complete in ≤ 500 ms." Include an exact **500 ms** bucket to measure compliance directly.
2. **Flexible quantiles:** you need p50, p90, p95, p99 or comparisons across request types. Enable percentile histograms over an appropriate time range so the backend can estimate quantiles.

Example for an API where most requests take 20–400 ms but occasional ones take seconds:

| Time Region | Goal | Guidance |
| --- | --- | --- |
| 1–20 ms | Spot ultra-fast paths | Keep only enough resolution if useful |
| 50–300 ms | Analyze typical latency | Denser buckets where your main interest lies |
| 500 ms | Business SLO | Add an exact 500 ms bucket |
| 1–5 seconds | Spot timeouts/retries | Keep buckets covering the tail |
| > 5 seconds | Spot extreme slowdowns | Highest bucket plus `+Inf`; revisit range if hit frequently |

With `maximumExpectedValue=5s`, very slow requests still update `_count`, `_sum`, and `+Inf`, though tail resolution may not support meaningful p99 estimates. Never treat expected-value ranges as timeouts or request-rejection mechanisms.

### 7.1. Histogram Cardinality

Each label set typically maps to **many series**, one per bucket boundary plus `_sum` and `_count`. Suppose:

- 10 normalized routes,
- 3 HTTP methods,
- 5 status/outcome groups,
- 20 bucket boundaries,
- 30 instances.

A rough estimate of **bucket series** is **10 × 3 × 5 × 20 × 30 = 90,000**, before adding count/sum series and other labels. This is an estimation model, not a fixed series count Micrometer creates in every app.

If every route also embeds an order ID or user ID, combinations scale with request volume. Therefore:

- Use route templates like `/orders/{id}` instead of raw URLs.
- Constrain labels to small, meaningful value sets for analysis.
- Never put emails, tokens, request IDs, trace IDs, or exception messages into low-cardinality labels.
- Enable histograms only on meters that truly need distribution visibility.
- Estimate costs and measure actual series counts after configuration changes.

**High-cardinality metadata** can be valuable inside distributed trace spans, yet must not become metric labels. It still remains subject to security and retention policies because it may persist in the trace backend.

## 8. Moving from Histograms to Traces and Logs During Incident Investigation

Histograms tell you how slow an operation is across traffic, yet **do not show which step slowed down a specific request**. In Spring Boot, combine metrics with Micrometer Observation, correlated logging, and distributed tracing.

~~~mermaid
sequenceDiagram
    participant Client
    participant Order as order-service
    participant Inventory as inventory-service
    participant Metrics as Metrics backend
    participant Trace as Trace backend
    Client->>Order: POST /orders
    Note over Order: HTTP timer records duration
    Order->>Inventory: reserve + traceparent
    Inventory-->>Order: timeout after 2.4 seconds
    Note over Order: Observation and log record error
    Order-->>Client: HTTP 503
    Order-->>Metrics: Buckets, count, sum updated
    Order-->>Trace: Send spans if retained by sampling
~~~

Suppose 5-minute p95 jumps from 350 ms to 1.2 seconds:

1. **Verify via histogram:** inspect p95/p99, request rate, ≤ 500 ms compliance, routes, and deployment versions. This establishes severity and blast radius.
2. **Find concrete traces:** open sampled slow traces and inspect HTTP spans, business steps, and calls to `inventory-service` to locate where time was spent.
3. **Check logs:** use trace ID/span ID (if recorded by logging configuration) to uncover immediate causes like timeouts, retries, pool exhaustion, or business state errors.
4. **Inspect dependencies:** compare downstream call histograms/durations, saturation, and retry counts to confirm a systemic trend rather than one outlier trace.
5. **Remediate and re-measure:** adjust config, roll back, or fix upstream issues, then confirm SLIs/SLOs return within acceptable bounds.

**Exemplars** are a capability in some backends/registries that attach trace references to metric samples, creating a direct bridge from a histogram data point to a matching trace. However, exemplars do not exist automatically; they require support across Micrometer registry, tracing, exporter, Prometheus, and dashboards. Without exemplars, you can still search traces by time window, service, route, and error within retention limits.

### 8.1. Why Do Metrics Exist Without Traces?

Tracing can be sampled. At a 10% sampling probability, most requests **will not store a trace**, while metrics can still aggregate all instrumented requests. Beyond sampling:

- An HTTP client or executor failed to propagate `traceparent`/context, breaking the trace.
- Tracing handler/bridge is unconfigured, so no spans are emitted.
- OTLP exporter, Collector, or backend errors prevented spans from being stored.
- The dashboard is querying the wrong service name, environment, or time range.
- Retention policies expired older traces.

Registering a histogram does not set up tracing, and tracing does not replace histograms. **Metrics show trends, traces show per-request execution paths, and logs capture concrete events.**

## 9. Testing Histograms in Your Application

Tests should focus on meaningful outcomes: the Timer records the expected count, SLO buckets appear in the exporter, and dashboard queries return sensible results. Avoid tests that merely echo builder method calls.

### 9.1. Unit Test for Timer with an In-Memory Registry

~~~java
import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

import java.time.Duration;
import java.util.concurrent.TimeUnit;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class CheckoutHistogramTest {

    @Test
    void recordsCountAndDuration() {
        try (SimpleMeterRegistry registry = new SimpleMeterRegistry()) {
            Timer timer = Timer.builder("orders.checkout.duration")
                    .tag("operation", "checkout")
                    .publishPercentileHistogram()
                    .serviceLevelObjectives(Duration.ofMillis(100),
                            Duration.ofMillis(500))
                    .register(registry);

            timer.record(Duration.ofMillis(80));
            timer.record(Duration.ofMillis(200));
            timer.record(Duration.ofMillis(800));

            assertEquals(3L, timer.count());
            assertEquals(1080.0,
                    timer.totalTime(TimeUnit.MILLISECONDS), 0.01);
            assertTrue(timer.max(TimeUnit.MILLISECONDS) >= 800.0);
        }
    }
}
~~~

This test verifies three samples totaling 1,080 ms with a max of at least 800 ms. **`SimpleMeterRegistry` is not Prometheus**, so do not use this test to assert `_bucket` series were exported properly. To verify **bucket boundaries and exported metric names**, use an integration test or an environment with a real Prometheus registry and inspect scrape output.

### 9.2. Integration Testing on Spring Boot

A useful scenario:

1. Configure histograms for `http.server.requests` and a 500 ms SLO bucket.
2. Send a controlled set of fast/slow requests to the instrumented route without relying on unpredictable network latency.
3. Verify `/actuator/prometheus` emits `_bucket`, `_count`, `_sum`, and the 0.5-second bucket with normalized route labels.
4. Confirm count increases match requests sent; with multiple instances, test aggregation queries.
5. Verify metric labels **do not contain** request IDs, user IDs, trace IDs, or sensitive data.
6. In staging, verify Prometheus actually scrapes and dashboards compute p95 or ≤ 500 ms compliance.

If using Observation to generate a business Timer, confirm the handler is registered and produces the expected meter name. For error analysis, separately verify HTTP outcomes or error metrics are captured, because latency histograms do not replace error-rate metrics.

## 10. Common Pitfalls

| Symptom or Mistake | Why It Is Wrong | How to Fix |
| --- | --- | --- |
| Averaging per-instance p95 values | Percentiles do not aggregate this way | Sum buckets by `le` first, then call `histogram_quantile` |
| Using raw `_bucket` as a 5-minute request count | Buckets are cumulative counters since startup | Use `rate` or `increase` over the window |
| Summing cumulative buckets together | Same request is counted multiple times | Use `_count` for totals, or subtract adjacent buckets |
| Computing p95 without enabling histograms | No matching `_bucket` series exist | Enable `percentiles-histogram` or configure SLO buckets |
| Setting a 500 ms SLO without a 0.5 s bucket | Cannot measure SLO compliance directly | Add a bucket at the exact SLO boundary |
| Forgetting Prometheus units are seconds | SLO thresholds off by 1,000× | Use `0.5` for 500 ms in queries |
| Computing p95 over too few requests | Quantiles swing wildly and mislead | Use longer windows; display request rate alongside p95 |
| Enabling histograms on every timer | Excessive time series and cost | Pick meters needing distributions and estimate cardinality |
| Putting raw URLs or IDs in labels | Series grow with every request | Normalize routes and bound tag value sets |
| Running overlapping manual Timer and Observation Timer | Double-counts the same operation | Designate a single authoritative measurement owner |
| Histograms exist yet no traces appear | Histograms do not control trace sampling/exporters | Check tracing bridge, propagation, and OTLP pipeline |
| Using `maximumExpectedValue` as a timeout | Expected range does not abort requests | Configure timeouts on HTTP clients/app and measure outcomes |
| Running classic histogram queries on native histograms | Incompatible data types and query semantics | Verify histogram representation in your backend |

### 10.1. Caution When Comparing p95 Across Two Releases

A canary receiving little traffic or a different mix of requests can show a different p95 even with zero bugs. When comparing releases, check request rate, route mix, user tier (if safely grouped), measurement window, and bucket configuration. Two histograms should only be summed when **bucket boundaries are compatible**, and any bucket change across versions must be evaluated before running mixed deployments.

## 11. Pre-Production Checklist

| Question | Required Evidence |
| --- | --- |
| What decision does the histogram support? | Defined SLI/SLO or p95/p99 investigation need |
| Are SLO boundaries exact? | Bucket exists at target threshold, e.g., 500 ms |
| Is the expected value range appropriate? | min/max expected covers important real-world latencies |
| Is cardinality acceptable? | Normalized routes/tags with cost estimates |
| Is double instrumentation avoided? | Same operation not unintentionally counted twice |
| Are metrics exported properly? | Buckets/count/sum visible at exporter or backend |
| Are PromQL units and summation correct? | `rate` before `sum by(le)`, seconds vs. ms verified |
| Is the SLI request scope unambiguous? | Consistent numerator/denominator filters, low-traffic handling |
| Do logs and traces support root-cause debugging? | Trace IDs and spans present per configuration |
| Are sampling limits understood? | Missing trace not mistaken for an unexecuted request |
| Are exporter and retention monitored? | Telemetry pipeline tracks errors, quotas, and storage config |

## 12. Hands-On Exercise: Measuring Order-Creation Latency

**Context:** `order-service` (Spring Boot) exposes `POST /orders`, calls `inventory-service`, and writes to a database. Operational target: **at least 99% of valid requests complete within at most 500 ms** over the defined SLO window.

**Tasks:**

1. Install Actuator and the Prometheus registry, and configure HTTP server request histograms with a 500 ms SLO bucket.
2. Send 10 requests with simulated latencies: 40, 55, 80, 90, 120, 150, 200, 270, 420, and 1,800 ms.
3. Manually calculate cumulative requests ≤ 100 ms, ≤ 300 ms, ≤ 500 ms, and `+Inf`; explain why you never sum bucket counters together.
4. Inspect exported metrics at `/actuator/prometheus`; note the actual metric name and route labels.
5. Write PromQL for request rate, p95, and the share of requests ≤ 500 ms, ensuring queries cover only valid requests per your SLI definition.
6. Add a `Timer` for a business step not isolated by the HTTP timer, compare HTTP server duration against that step's duration, and avoid double-counting.
7. Simulate an `inventory-service` timeout. Observe how the histogram shifts, locate a slow trace if retained by sampling, and look up logs by trace ID.
8. Estimate the series increase from adding 2 regions, 3 outcomes, and 10 buckets across 20 instances. Explain why order IDs must not be metric labels.
9. Propose a dashboard showing request rate, p95, 500 ms compliance rate, error rate, and a link to traces/logs.

**Verification hint:** with the 10 samples in step 2, there are **4 requests ≤ 100 ms**, **8 requests ≤ 300 ms**, **9 requests ≤ 500 ms**, and **10 requests in `+Inf`**; the ≤ 500 ms completion rate is **90%**. This tiny sample only checks calculation logic, not a production SLO. Real SLO evaluation requires live traffic, a proper window, and clear valid-request policies.

## 13. Takeaway

A **Histogram** turns a stream of measurements into bucketed distributions. Paired with **Micrometer Timer** or **DistributionSummary**, it lets Spring Boot export latency or value distributions; Prometheus can sum compatible classic buckets and compute p95/p99 or SLO threshold compliance rates.

Three core principles are **right bucket boundaries**, **right PromQL math**, and **right cardinality budget**. During production investigations, histograms show the scope and severity of slowdowns, while traces and logs uncover specific paths and root causes; correlation depends on context propagation, sampling, exporters, and observability pipeline configuration.

**References:**

- [Micrometer — Histograms and Percentiles](https://docs.micrometer.io/micrometer/reference/concepts/histogram-quantiles.html)
- [Micrometer — Timers](https://docs.micrometer.io/micrometer/reference/concepts/timers.html)
- [Micrometer — Distribution Summaries](https://docs.micrometer.io/micrometer/reference/concepts/distribution-summaries.html)
- [Spring Boot — Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html)
- [Prometheus — Histograms and Summaries](https://prometheus.io/docs/practices/histograms/)
