# Controlling Tag, Histogram, Trace Sampling, and Probe Frequency Costs

## 1. Where Do Observability Costs Come From?

An application can handle business logic well yet consume heavy resources just recording, exporting, and storing operational metrics. This cost does not sit in one single place:

- **Inside the application:** memory storing meters, updating counters/buckets, generating trace information, running health checks, and building responses.
- **Over the network:** scrape payloads, exported spans, and external checks.
- **In the observability system:** ingestion, indexing, retention, and querying data.
- **In operations:** maintaining configuration, finding incidents amid excessive data or missing required data.

The goal is to **keep enough information to detect and investigate incidents at a controlled cost**. Reducing metrics until dashboards no longer accurately reflect the service is not a good outcome.

The four mechanisms in this article affect different parts:

| Mechanism | Quantity to control | What can be lost if tuned wrongly? |
| --- | --- | --- |
| Metric tags | Number of label combinations and rate of new combination creation | Useful grouping or all metrics exceeding limits |
| Histogram | Bucket count, number of meters with histograms, and statistics memory | Resolution of the latency distribution |
| Trace sampling | Number of traces/spans recorded and exported | Path details of a specific request |
| Probe frequency | Number of checks and cost per check | Speed of detecting unserviceable state |

This article uses **Spring Boot 3.3.x** configuration. Thresholds, ratios, and intervals are design examples and must be measured on the actual service before applying.

## 2. Building a Cost Model Before Changing Configuration

### 2.1. Count Label Combinations, Not Just Metric Names

One metric name can correspond to very many time series. For example, an HTTP request counter has labels route, method, status, and instance.

Suppose there are:

- 40 route templates.
- 4 HTTP methods.
- 5 status values actually used in the model.
- 6 instances.
- Each combination exports a classic histogram with 20 finite buckets.

Maximum combinations under the assumption:

```text
Label combinations = 40 × 4 × 5 × 6 = 4,800
```

Each histogram combination has finite buckets, the +Inf bucket, sum, and count. With B finite buckets, that portion has B + 3 series. [Prometheus histogram structure](https://prometheus.io/docs/practices/histograms/)

Therefore:

```text
Histogram portion series = 4,800 × (20 + 3) = 110,400
```

This models combinations assumed to exist; not every system produces the full Cartesian product. If exception, region, or partner name labels are added, calculate their actual combinations.

The numbers also exclude extra series such as timer max, other meters, scrape metrics, and observability system replicas. Timers can export additional statistics depending on the backend. [Micrometer Timers](https://docs.micrometer.io/micrometer/reference/concepts/timers.html)

### 2.2. Collection Frequency Multiplies Sample Count Further

If all 110,400 active series are scraped every 15 seconds:

```text
Samples/second ≈ 110,400 / 15 = 7,360
Samples/day ≈ 7,360 × 86,400 = 635,904,000
```

That is a theoretical sample count over a steady day. Do not convert this sample count directly into a fixed dollar cost or disk size: formats, compression, indexing, retention, replication, and billing models vary.

Longer retention increases the data volume to store. Prometheus describes capacity and retention factors in its storage documentation. [Prometheus storage](https://prometheus.io/docs/prometheus/latest/storage/)

Besides active series count, track the **rate at which new series appear**. A label with few values at any one instant that keeps changing across deployments can still make historical series grow rapidly.

## 3. Controlling Tags Right Where Metrics Are Created

### 3.1. Choose Labels by the Questions to Answer

Tags in Micrometer are typically exported as labels in Prometheus. Each label combination creates a separate series. [Prometheus label conventions](https://prometheus.io/docs/practices/naming/)

Before adding a tag, answer:

1. Which dashboard or alert needs to group by this tag?
2. How many distinct values exist?
3. Do values grow with users, requests, or time?
4. Is there sensitive data or personal identifiers?
5. Can that question be answered by logs/traces of one request instead of a metric?

| Expected value | Usually appropriate decision |
| --- | --- |
| HTTP method, bounded outcome groups | Use when grouping is needed |
| Route templates like /orders/{id} | Better than individual order IDs |
| Environment, deployment region with manageable value set | Consider per operational scope |
| userId, orderId, requestId, traceId | Do not use as per-entity metric labels |
| URL query strings or free-form error text | Normalize or exclude from labels |
| Release version | Use only when needed; evaluate release count and historical series |

A label with 10,000 values is usually riskier than one with three values, yet you cannot evaluate a tag in isolation while ignoring multiplication with the remaining tags.

Do not turn requestId into a dynamic metric name. Switching from dynamic labels to dynamic names still creates an unbounded number of meters.

### 3.2. Normalize into a Finite Set

For an API with paths like:

```text
/orders/18401
/orders/18402
/orders/18403
```

The goal is a route template:

```text
/orders/{id}
```

When recording custom metrics, pull values from a defined set, e.g. channel only having web, mobile, partner. Do not assign an externally supplied header directly as channel.

If an OTHER bucket is needed, define its meaning and mapping upfront. Truncating strings, hashing IDs, or taking the first few characters does not automatically make the value count finite.

Common tags are added to many meters, so an unbounded label there has wide blast radius. Adding labels to every meter simply because the data is available is a choice to avoid.

### 3.3. Use Limits as a Guardrail

Spring Boot 3.3 has URI value limits for HTTP metrics:

```yaml
management:
  metrics:
    web:
      server:
        max-uri-tags: 100
      client:
        max-uri-tags: 100
```

In this version, the default for both properties is 100; the example states them explicitly to document policy. When exceeded, metrics with new URI values are rejected by the filter. [Spring Boot 3.3 URI tag properties](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/index.html#appendix.application-properties.actuator)

Understand the consequences accurately:

- It does not limit how many HTTP requests the application can receive.
- It does not automatically group all remaining URIs into an OTHER bucket.
- It does not limit other tags such as customerId or partner.
- Dropping metrics after hitting the cap can cause total traffic or errors on dashboards to be missing.

Prioritize fixing the label source. When hitting the limit, have a way to detect it via warnings/logs provided by the library or intentional cross-checks against gateway metrics and independent sources. Do not assume every version has a dedicated counter counting rejected meters.

### 3.4. Limiting Tags on Custom Metrics

The following example is an additional configuration class in a Spring Boot application with Micrometer; it is not a standalone Java program:

```java
package example.observability;

import io.micrometer.core.instrument.config.MeterFilter;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class MetricTagBudgetConfiguration {
    @Bean
    MeterFilter checkoutChannelLimit() {
        return MeterFilter.maximumAllowableTags(
                "checkout.operations",
                "channel",
                3,
                MeterFilter.deny());
    }
}
```

The filter applies to meter names with the matching prefix. If only three approved channel values are desired, still validate values before recording; a count limit is not an allowlist by name.

With the deny branch, Micrometer uses a no-op meter for rejected registrations. [MeterFilter and the deny mechanism](https://docs.micrometer.io/micrometer/reference/concepts/meter-filters.html)

Register the filter before the relevant meters are created. Do not treat adding a filter late as a complete fix for already-created meters and memory. When reducing tags, also verify aggregation and metric semantics; removing labels from two different gauges does not automatically produce a valid gauge sum.

## 4. Choosing Histograms Based on Decisions to Make

### 4.1. Do You Need the Whole Distribution Curve or Just a Few SLO Thresholds?

Two different needs:

- Need to explore p95/p99 across a sufficiently wide latency range.
- Only need the proportion of requests meeting thresholds such as 100 ms, 300 ms, 1 s.

You do not need to enable the same bucket count for every timer. Select meters that affect user experience or operational objectives.

Micrometer distinguishes aggregatable-bucket histograms from per-meter pre-calculated percentiles; pre-calculated percentiles cannot be aggregated by averaging across instances. [Micrometer histograms and percentiles](https://docs.micrometer.io/micrometer/reference/concepts/histogram-quantiles.html)

### 4.2. Option A: Need Histograms for Percentile Exploration

This is supplementary configuration for Spring Boot 3.3:

```yaml
management:
  metrics:
    distribution:
      percentiles-histogram:
        "http.server.requests": true
      minimum-expected-value:
        "http.server.requests": 5ms
      maximum-expected-value:
        "http.server.requests": 5s
      slo:
        "http.server.requests": 100ms,300ms,1s
```

The expected value range bounds auto-generated buckets and affects statistics memory. SLO thresholds can add needed buckets. Do not treat 5 s as a request timeout or a cutoff truncating processing durations above 5 s. [Spring Boot distribution configuration](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html#actuator.metrics.customizing.per-meter-properties)

Measure actual buckets in the endpoint after configuring; do not assume another version's default bucket count as guaranteed.

### 4.3. Option B: Keep Only Necessary SLO Thresholds

This option **replaces Option A**; do not merge two YAML blocks with duplicate keys:

```yaml
management:
  metrics:
    distribution:
      percentiles-histogram:
        "http.server.requests": false
      slo:
        "http.server.requests": 100ms,300ms,1s
```

In the Prometheus histogram model under consideration, SLO buckets still exist even without auto-generated percentile buckets enabled. Do not interpret percentiles-histogram=false as "no buckets at all". [Buckets created by service level objectives](https://docs.micrometer.io/micrometer/reference/concepts/histogram-quantiles.html)

With three finite buckets, the histogram portion of the 4,800-combination example is:

```text
4,800 × (3 + 3) = 28,800 series
28,800 / 15 × 86,400 = 165,888,000 samples/day
```

Compared to the initial 110,400 series, this modeled portion drops by about 73.9%. This is not a promise that total system cost drops by exactly 73.9%: other meters and costs remain.

In return, a distribution with fewer buckets has lower resolution. Do not keep presenting p99 as if it still had the same precision; update dashboards and acceptance criteria accordingly.

### 4.4. Actions That Do Not Substitute for Each Other

- Lowering trace sampling does not reduce metric buckets.
- Reducing bucket count does not reduce label combinations of count/sum.
- Lowering scrape frequency does not eliminate histogram update cost per request.
- Dropping series in Prometheus does not remove meters and statistics memory in the JVM.
- Shortening backend retention does not fix unbounded labels at the application.

Measure cost reduction at the exact layer where you reduced it.

## 5. Trace Sampling: Reduce Data While Understanding What Is Dropped

### 5.1. Sampling Rate Is a Probabilistic Decision

For a tracing system that already has the appropriate bridge, exporter, and backend, configure:

```yaml
management:
  tracing:
    sampling:
      probability: 0.02
```

Spring Boot 3.3 defaults to 0.1; the value above chooses 0.02 for sampling governed by the corresponding property. Adding the property alone does not install the entire tracing system. [Spring Boot 3.3 Tracing](https://docs.spring.io/spring-boot/3.3/reference/actuator/tracing.html)

Do not understand 2% as exactly two traces out of every 100 requests, nor as a hard cap on spans per second.

In Spring Boot 3.3's default OpenTelemetry implementation, the root-trace sampler is ratio-based and wrapped in a parent-based sampler. An incoming parent context's sampling decision affects the child span's decision. [Spring Boot 3.3.13 sampler configuration source](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.13/spring-boot-project/spring-boot-actuator-autoconfigure/src/main/java/org/springframework/boot/actuate/autoconfigure/tracing/OpenTelemetryAutoConfiguration.java)

Therefore, setting a low rate on a downstream service does not necessarily reduce traces already sampled upstream. Check root trace creation sites, propagation, custom samplers, and agent configuration if present.

### 5.2. Estimating Span and Data Volume

Suppose at the root trace creation site:

```text
Traffic = 2,000 requests/second
Sampling ratio = 0.02
Average = 8 spans/sampled trace
Average = 500 bytes/span in the model
```

Estimate:

```text
Sampled traces/second ≈ 2,000 × 0.02 = 40
Spans/second ≈ 40 × 8 = 320
Data/second ≈ 320 × 500 = 160,000 bytes
Data/day ≈ 13,824,000,000 bytes ≈ 13.824 GB
```

GB here is 10^9 bytes. The model excludes compression, protocol overhead, retries, indexing, replication, or span-count differences between fast and error traces.

Measure span size and spans per trace separately. Even if traffic does not grow, a new library creating more spans can still raise total data volume.

The sampling rate does not equate to an equal percentage drop in CPU. Some instrumentation, context propagation, or metric update overhead remains.

### 5.3. Head Sampling Does Not Guarantee Capturing Rare Errors

Head sampling decides early, before the full outcome of the trace is known. It cannot alone guarantee retaining every error trace that occurs later. [Head sampling and its limits](https://opentelemetry.io/docs/concepts/sampling/#head-sampling)

Suppose there are 10 distinct error traces and each is independently sampled with 2% probability. The chance of keeping at least one error trace is:

```text
1 - (1 - 0.02)^10 ≈ 18.3%
```

This is an illustration under probabilistic assumptions, not a deterministic forecast for every sampler. It shows that cutting the rate sharply can lose evidence for investigating rare errors.

Error metrics must still count completely within the defined scope; do not treat kept error traces as the system's total error count. If metrics are also being dropped by tag limits, address that issue separately.

### 5.4. When Decisions Are Needed After Outcomes Are Known

Tail sampling inspects collected trace data to select by conditions such as errors or latency. It shifts the cost problem: data must be received, state held, and decisions awaited. [OpenTelemetry tail sampling](https://opentelemetry.io/docs/concepts/sampling/#tail-sampling)

All spans of a trace must reach the same decision point; wait configuration, trace retention capacity, and late-arriving span handling affect results. [Tail sampling processor](https://github.com/open-telemetry/opentelemetry-collector-contrib/blob/main/processor/tailsamplingprocessor/README.md)

Spans already dropped earlier at the application cannot be recovered. If upstream only generates/exports 2% of traces, downstream layers cannot guarantee keeping 100% of system errors.

A reasonable policy should clearly state:

- Where sampling occurs and whether it applies to root traces or parent-sampled traces.
- Whether errors, slow requests, or low-traffic services are prioritized.
- Budgets for spans/second, bytes/second, and queues.
- How dropped data, exporter errors, or full queues are monitored.
- How to temporarily raise collection during investigations and how to revert.

Do not turn user IDs into metric tags to compensate for missing traces. Trace attributes and logs also need bounds on size, sensitive data, and query cost.

## 6. Probe Frequency: Health Checks Are Also Load

### 6.1. Count Everyone Calling Checks

A service can simultaneously be checked by kubelet, load balancers, uptime monitors, deployment verifiers, and operator tools.

Estimate steady-state call cadence:

```text
Probe QPS ≈ instance count × sum(1 / period of each probe type)
```

For example, 120 instances, liveness every 10 seconds and readiness every 5 seconds:

```text
120 × (1/10 + 1/5) = 36 checks/second
36 × 86,400 = 3,110,400 checks/day
```

This excludes startup probes, other check sources, or cadence changes when unready. This is a budgeting estimate; measure actual frequency.

If each check holds a database connection for 40 ms, the model above corresponds to an average of about 1.44 connections serving probes system-wide. That is connection occupancy time, not 1.44 CPU seconds per second.

Reducing the cost of each check is sometimes more effective than merely lengthening the period.

### 6.2. Keep Liveness and Readiness Meanings Accurate

Liveness supports restart decisions; readiness supports deciding whether to keep sending traffic to the container. Startup probes are for the startup phase. [Kubernetes probe types](https://kubernetes.io/docs/concepts/workloads/pods/probes/)

In Spring Boot, do not put external systems into liveness. A shared database outage is not a reason for all instances to restart together. Including external systems in readiness must be decided based on the service's serving ability and fallback mechanisms. [Spring Boot health probe scope](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.kubernetes-probes.external-state)

Example configuration using only internal availability state for both groups:

```yaml
management:
  endpoint:
    health:
      show-details: never
      show-components: never
      probes:
        enabled: true
        add-additional-paths: true
      group:
        liveness:
          include: [livenessState]
        readiness:
          include: [readinessState]
```

Additional paths expose the groups at `/livez` and `/readyz` on the application port. [Spring Boot 3.3 probe paths](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.kubernetes-probes)

This example does not prove the application still serves every function when a dependency fails. Business error observation and an appropriate readiness policy are needed; do not change health to always UP just to lower check load.

If additional health groups already exist, review their meaning before changing the include list. Replacing blindly with sample config can drop a needed condition.

### 6.3. Choose Period Together with Failure Threshold

The snippet below sits inside a containers[] element of a Kubernetes manifest, assuming application port 8080 and permitted probe paths:

```yaml
ports:
  - name: http
    containerPort: 8080

startupProbe:
  httpGet:
    path: /livez
    port: http
  periodSeconds: 5
  timeoutSeconds: 2
  failureThreshold: 24

livenessProbe:
  httpGet:
    path: /livez
    port: http
  periodSeconds: 10
  timeoutSeconds: 2
  failureThreshold: 3

readinessProbe:
  httpGet:
    path: /readyz
    port: http
  periodSeconds: 10
  timeoutSeconds: 2
  failureThreshold: 2
```

periodSeconds, timeoutSeconds, and failureThreshold must be considered together. The startup probe delays running liveness/readiness until startup checks succeed. [Kubernetes probe configuration](https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/)

With 120 instances, the two steady probes in this configuration have a nominal rate:

```text
120 × (1/10 + 1/10) = 24 checks/second
```

Compared to 36 checks/second, that drops by about one third. In exchange, some readiness transitions may be detected more slowly. Verify the time to stop receiving traffic when the application is unready.

Do not treat multiplying period × failureThreshold as an exact time guarantee. When the failure occurs within the period, timeouts, and execution scheduling all affect it; readiness when unready can also be checked more frequently than the nominal period.

### 6.4. Bound the Cost of a Single Check

Health checks should do small, bounded work, produce no business side effects, and not execute full user transactions.

If an external system must be called, set a timeout on the client performing that call. A timeout on the probe caller does not guarantee server-side work is automatically canceled.

Spring Boot's slow-indicator-threshold property logs a warning when an indicator is slow, not a timeout to cancel the indicator. [Slow health indicator warning](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.health.writing-custom-health-indicators)

Cache results only after defining acceptable staleness and testing error-reflection time. Do not arbitrarily cache liveness/readiness state just to make cost charts look nicer.

## 7. Separate Scrape Cadence from Probe Cadence

Probes drive orchestration decisions; scrapes collect metrics for observation. They may both travel over HTTP, yet do not substitute for each other.

If the scrape interval increases from 15 to 60 seconds, sample volume for a steady series set drops roughly fourfold. However:

- Meters are still updated inside the application as activity occurs.
- Gauges can miss brief spikes occurring between scrapes.
- Rate queries need windows with enough samples.
- Alerts and dashboards must be re-tested against the new data cadence.
- Liveness/readiness cadence does not automatically change with scrape interval.

Similarly, lowering probe cadence does not reduce spans or metric series. Do not use one knob to solve costs at another layer.

If metric relabeling is used to drop data at Prometheus, the data has already been fetched from the application before being discarded at ingestion. It can reduce backend storage volume without eliminating the work of building and transmitting responses. [Position of metric relabeling](https://prometheus.io/docs/prometheus/latest/configuration/configuration/#metric_relabel_configs)

Do not drop labels blindly at downstream layers: ensure series still preserve valid identifiers and semantics after transformation. Setting ingestion limits also requires alerting when scrapes fail, rather than treating it as a safe way to take partial data.

## 8. Measure Before and After with Real Data

### 8.1. Track Series Count and Scrape Cost

The following query examples assume the orders job has target label environment=prod; replace with your system's verified labels:

```promql
sum(scrape_samples_scraped{job="orders", environment="prod"})
```

```promql
sum(scrape_samples_post_metric_relabeling{job="orders", environment="prod"})
```

```promql
scrape_duration_seconds{job="orders", environment="prod"}
```

These are series Prometheus creates per target scrape. [Auto-generated scrape metrics](https://prometheus.io/docs/concepts/jobs_instances/)

To see which metric names have the most series in that scope:

```promql
topk(
  10,
  count by (__name__) (
    {job="orders", environment="prod"}
  )
)
```

To check how many URI values currently exist on HTTP count:

```promql
count(
  count by (uri) (
    http_server_requests_seconds_count{
      job="orders",
      environment="prod"
    }
  )
)
```

Queries observing series counts also have cost. Run them within a narrow scope; do not put a system-wide scan query on an auto-refreshing panel with too fast an interval.

Ingested series count does not reveal the exact meter count or JVM memory. When needed, also measure heap, application CPU, and registry statistics using appropriate tools. Post-relabeling sample count dropping while scrape responses remain large signals that cost was only reduced downstream.

### 8.2. Track Traces and Probes Beyond Configuration Numbers

For tracing, measure spans created/exported/received, transmitted bytes, queues, retries, and dropped data. Specific metric names depend on the exporter/collector; read actual data instead of assuming every library uses the same names.

For probes, measure call counts, processing time, timeouts, state transitions, and restart counts. Use appropriate HTTP metrics or access logs; if health requests bypass the instrumentation in use, add a suitable measurement source.

Distinguish four kinds of data loss:

1. Intentionally not selected by sampling.
2. Meters rejected due to tag limits.
3. Queue/exporter/collector dropping data unintentionally.
4. Scrape or ingestion failures.

These four kinds have different meanings. Seeing data volume drop alone is not enough to know the system was optimized successfully.

## 9. Change Process and Practice Exercise

### 9.1. Change One Factor with Rollback Criteria

1. Record baseline load, instance count, configuration, and measurement range.
2. State the questions to answer and minimum data to retain.
3. Pick one change: normalize tags, adjust buckets, adjust sampling, or adjust probes.
4. Test in a suitable environment under the same load shape.
5. Compare costs at the application, network, and backend.
6. Induce a controlled failure scenario to verify detection/investigation capability.
7. Roll out with limits, monitor, and revert if necessary signals are lost.

Do not compare "before" during peak hours against "after" during off-peak hours and attribute all difference to the new config. When normalizing per request or per instance, still keep absolute numbers so a real load surge is not missed.

### 9.2. Acceptance Criteria for Each Change

| Change | Cost evidence | Evidence observability remains intact |
| --- | --- | --- |
| Normalize URIs | New URI values/series drop | Critical APIs still have counts, errors, and latency |
| Reduce buckets | Bucket count and scrape samples drop | SLO thresholds remain queryable; new resolution is documented |
| Lower sampling | Spans/bytes drop per real model | Cross-service traces stay consistent; rare-error investigation limits are accepted |
| Change probe period | Call counts and check cost drop | Time to pull out of service and hang detection still meet requirements |
| Drop data at backend | Ingest/storage volume drops | Does not drop alerts or create series collisions after transformation |

### 9.3. Practice Exercise with Verifiable Numbers

A service has 40 routes, 4 methods, 5 statuses, and 6 instances; assume all combinations exist. It exports 20 finite buckets, scraped every 15 seconds. The system creates 2,000 root traces/second, samples 2%, averages 8 spans/trace and 500 bytes/span. The cluster has 120 instances, liveness 10 seconds and readiness 5 seconds.

Build a budget table and verify the results:

- 4,800 label combinations.
- 110,400 series for the modeled histogram portion.
- 635,904,000 samples/day for that portion.
- If switched to three finite buckets: 28,800 series, 165,888,000 samples/day.
- Around 320 spans/second, corresponding to 13.824 GB/day under the size assumptions.
- Nominal probe rate 36 checks/second; if readiness changes to 10 seconds, 24 checks/second.

Next, explain what information may be lost and what tests must be run for each change. Do not accept a proposal stating only "cost reduced" without pointing out what observability remains preserved.

An operational policy should have an owner, budget, measurement method, limit-hit indicators, and a rollback method. When those elements are clear, observability cost becomes a verifiable engineering decision rather than a set of properties copied by habit.
