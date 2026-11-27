# Dashboards and Alerts Based on Real Service Impact

A Circuit Breaker dashboard must answer two distinct questions: are users receiving service at the expected quality, and how are dependency protection mechanisms behaving? An `OPEN` state is an important diagnostic signal, yet on its own it does not prove users are experiencing an outage. If the fallback still returns suitable data and the API meets its SLO, an open circuit may be protecting the system as designed. Conversely, a breaker staying `CLOSED` while API latency or error rate climbs is also an incident that must be caught.

Therefore, dashboards should put traffic, request success rate, latency, and SLOs first. Charts for Circuit Breaker, TimeLimiter, fallback, and Bulkhead explain the root cause and how the system is reacting. Alerts must prioritize real service impact, followed by internal warning signs requiring investigation.

## 1. Define SLIs and SLOs Before Building Dashboards

An SLI (Service Level Indicator) measures service quality; an SLO (Service Level Objective) is the agreed target for that indicator over a time window. For an API using a Circuit Breaker to call `inventory-service`, you can start from the following SLIs:

| SLI | How to Measure | Operational Question |
| --- | --- | --- |
| Request success rate | Requests completing per contract divided by total eligible requests | Are users receiving usable responses? |
| Server-side error rate | 5xx requests or SLO-defined service errors divided by total requests | How many requests are failing due to the system? |
| Latency | p50, p95, and p99 of request processing time | How long are users waiting? |
| Timeout request rate | Requests exceeding deadlines at the API or dependency | Is the system responding before the deadline? |
| Fallback rate | Fallback invocations by dependency and reason | How frequently is the system serving backup data? |

For example, an API sets a target of 99.9% of eligible requests succeeding over 30 days and p95 under 800 ms. These are illustrative targets only. Agree on how to count eligible requests, how to classify 4xx business errors, timeouts, and fallback responses before building dashboards. A fallback response may count as a success under the API contract or as a degraded response; never assume all fallbacks are always successes or always errors.

For an inventory flow, if cache returns stale data that remains business-acceptable for up to 60 seconds, the SLI might count that response as conditionally successful while the dashboard displays the stale data rate separately. If stale data is unsafe, an `unavailable` response should count toward service errors or a separate degradation SLI. Rules must derive from the business contract.

## 2. Collecting Metrics from Spring Boot and Resilience4j

Spring Boot Actuator integrates Micrometer and can export metrics to many systems. With Spring Cloud CircuitBreaker using Resilience4j, you need Actuator and the `resilience4j-micrometer` module to enable auto-configuration for Resilience4j metrics. If Prometheus scrapes the application directly, add the Prometheus registry:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    implementation 'io.github.resilience4j:resilience4j-micrometer'
    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'
}
```

To expose the required endpoints in an internal observability environment:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
  endpoint:
    health:
      show-details: when_authorized
```

Prometheus scrapes data at `/actuator/prometheus`. The `metrics` endpoint is helpful for verifying meter names and tags during development; the `prometheus` endpoint provides the scrape format. Expose only necessary endpoints and secure them with authentication, authorization, and management networks. Never expose management endpoints on the public Internet.

Spring MVC and Spring WebFlux provide a default server request metric named `http.server.requests`. Micrometer normalizes names for Prometheus export, typically to `http_server_requests_seconds_*`. HTTP client metrics use `http.client.requests`; this helps separate incoming API request latency from downstream service call duration.

Resilience4j Micrometer provides these key meters (Micrometer names prior to Prometheus normalization):

| Meter | Information | Dashboard Usage |
| --- | --- | --- |
| `resilience4j.circuitbreaker.calls` | Timer for successful, failed, and ignored calls; carries `name` and `kind` tags | Call rate and duration per dependency, splitting success/failure |
| `resilience4j.circuitbreaker.state` | State gauge with `state` and `name` tags | Timeline of `CLOSED`, `OPEN`, and `HALF_OPEN` per breaker ID |
| `resilience4j.circuitbreaker.failure.rate` | Gauge of failure rate in the window | Compare against `failureRateThreshold` |
| `resilience4j.circuitbreaker.slow.call.rate` | Gauge of slow-call rate | Spot degrading dependencies before errors surge |
| `resilience4j.circuitbreaker.not.permitted.calls` | Counter of rejected calls | See how many requests the breaker blocked |
| `resilience4j.timelimiter.calls` | Counter by outcome, including `successful`, `failed`, `timeout` | Separate timeouts from other failures |
| `resilience4j.bulkhead.*` | Gauges for concurrency, queue, capacity, and thread pool depending on Bulkhead type | Detect capacity exhaustion and queue buildup |

Prometheus renames meters according to registry conventions, such as replacing dots with underscores and appending unit suffixes to timers. Exact names also depend on Micrometer/Resilience4j versions and registry type. Before writing PromQL, inspect `/actuator/prometheus` or `/actuator/metrics` to confirm actual metric names, tags, and types emitted by the application.

## 3. Enabling Histograms for p95 and p99

To compute percentiles that can be aggregated across multiple instances in Prometheus, histogram buckets are needed. Enable histograms and configure SLO buckets for server requests:

```yaml
management:
  metrics:
    distribution:
      percentiles-histogram:
        http.server.requests: true
      slo:
        http.server.requests: 100ms, 300ms, 500ms, 800ms, 1s, 2s
```

`percentiles-histogram` generates buckets that aggregate cleanly across instances; `slo` adds buckets at chosen target boundaries. Histograms incur storage overhead and multiply series counts by tag cardinality, so enable them only on meters that truly need them and keep tag cardinality low.

PromQL example calculating p95 on server requests:

```promql
histogram_quantile(
  0.95,
  sum by (le) (
    rate(http_server_requests_seconds_bucket{job="order-service", uri!~"/actuator.*"}[5m])
  )
)
```

This query illustrates aggregate p95 calculation. You can add `uri`, `method`, `region`, or `status` to `by (...)` when breaking down results. Use URI templates such as `/orders/{id}` rather than URLs containing real IDs. If histograms are not enabled or metric names differ, the query will return no data; verify scraping before using it in alerts.

## 4. Dashboard Layout Following Investigation Order

A useful dashboard guides the on-call engineer from customer impact down to technical root cause. Organize it into the following rows:

### Row 1 — User-Facing Service Health

- Request rate per second, split by critical route.
- 2xx/3xx, 4xx, and 5xx rates according to product classification.
- API p50, p95, and p99 latency; mark SLO thresholds.
- Timeout or deadline-breach request rate.
- SLO attainment and remaining error budget over a 7/30-day window.

This is the default view when opening the dashboard. On-call responders must immediately see whether a customer-impacting incident is happening, which endpoints are affected, and when it started.

### Row 2 — Fallback Impact

- Fallback invocations by dependency and reason: `dependency_error`, `timeout`, `circuit_open`, `bulkhead_full`.
- Share of responses served from cache or stale data; p95/max cache data age.
- Failed fallbacks or cases where no backup data was available.
- Requests returning `503`, `504`, or degraded status per API contract.

Fallbacks can keep an API running while a dependency is broken. The dashboard must reveal whether fallbacks are successfully protecting customers or merely masking errors with unreliable data.

### Row 3 — Per-Dependency Circuit Breakers

- `CLOSED`, `OPEN`, and `HALF_OPEN` states by breaker ID, displayed as a timeline.
- Failure rate and slow-call rate compared against configured thresholds.
- Successful/failed calls per minute and latency per dependency.
- Rejected calls (`not permitted`) and state transition timestamps.
- Time spent in `OPEN`, reopen counts after `HALF_OPEN`, and probe outcomes.

Use meaningful breaker names such as `inventory`, `payment`, or `profile`, consistent with IDs in configuration and source code. Do not merge all dependencies into one aggregate line when investigating a specific service is required.

### Row 4 — Timeouts, Retries, and Bulkheads

- Timeout count and timeout rate per dependency.
- Retry attempts, retry exhaustion, and extra request load generated by retries.
- Active semaphore permits versus concurrency limits.
- Thread-pool Bulkhead: active threads, queue depth, queue capacity, and rejections.
- HTTP client connection pool: leased connections, pending waits, timeouts, and connection errors if exposed by the client.

These charts help distinguish a slow dependency, exhausted pools, overly tight timeouts, and load-amplifying retries. If queues grow while p95 rises, enlarging queue capacity may make requests wait even longer rather than fixing the root cause.

### Row 5 — Resources and Deployment Changes

- JVM heap, GC pauses, thread count, and CPU.
- Connection pools, executor pools, and event-loop saturation where applicable.
- Application version, deployment region, and deployment timestamp annotations.
- Errors per instance/pod to spot a single misbehaving node.

Overlay deployment, configuration, or dependency incident annotations on the same timeline as latency and error rates. This helps pinpoint whether an incident started right after a specific change.

## 5. PromQL Examples for Primary Panels

The examples below assume Prometheus scrapes the application with `job="order-service"`, Spring Boot emits standard HTTP metrics, and the `status` tag is present. Replace labels with your environment's actual labels.

**Request rate:**

```promql
sum(rate(http_server_requests_seconds_count{job="order-service", uri!~"/actuator.*"}[5m]))
```

**5xx rate:**

```promql
sum(rate(http_server_requests_seconds_count{job="order-service", status=~"5..", uri!~"/actuator.*"}[5m]))
/
clamp_min(sum(rate(http_server_requests_seconds_count{job="order-service", uri!~"/actuator.*"}[5m])), 0.001)
```

**Failed Circuit Breaker calls by ID:**

```promql
sum by (name) (rate(resilience4j_circuitbreaker_calls_seconds_count{kind="failed"}[5m]))
```

**Circuit Breaker error rate by ID:**

```promql
sum by (name) (rate(resilience4j_circuitbreaker_calls_seconds_count{kind="failed"}[5m]))
/
clamp_min(
  sum by (name) (rate(resilience4j_circuitbreaker_calls_seconds_count{kind=~"failed|successful"}[5m])),
  0.001
)
```

**Breakers currently OPEN:**

```promql
max by (name) (resilience4j_circuitbreaker_state{state="open"})
```

With Resilience4j state gauges, a value of `1` indicates the active state while other states may report `0`. Confirm metric semantics for your library version. Never sum state gauges together and interpret the result as a request count.

**Request p95:** use the `histogram_quantile` query from the histogram section. When breaking down by route, add `uri` to both `sum by (le, uri)` and keep identical filters across panels.

Resilience4j's `calls` metric is a timer, so Prometheus typically exports `_count`, `_sum`, `_max`, or histogram bucket series depending on configuration. If `resilience4j_circuitbreaker_calls_seconds_count` does not exist, look up the raw meter in Actuator and inspect the scrape output; never build alerts on guessed metric names.

## 6. Recording Fallbacks with a Custom Metric

Resilience4j provides metrics for call states and outcomes, yet applications often need to know why a fallback ran and whether that result was business-acceptable. Add a `Counter` with tags drawn from a finite value set:

```java
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.stereotype.Component;

@Component
public class FallbackMetrics {
    private final MeterRegistry meterRegistry;

    public FallbackMetrics(MeterRegistry meterRegistry) {
        this.meterRegistry = meterRegistry;
    }

    public void record(String dependency, String reason) {
        meterRegistry.counter(
                "app.fallback.calls",
                "dependency", dependency,
                "reason", reason
        ).increment();
    }
}
```

Call `record("inventory", "circuit_open")` in the corresponding fallback branch. You can add separate counters for failed fallbacks, cache hits/stale responses, or data rejected for being too old. Never put `sku`, user IDs, request IDs, exception messages, or URLs containing IDs into metric tags; those values create massive cardinality and can overload the monitoring system. Use logs or traces to inspect individual requests.

## 7. Designing Alerts by Impact Severity

Categorize alerts by required operational response:

| Level | Example Conditions | Action |
| --- | --- | --- |
| Page / Critical | API error rate continuously breaches SLO; p95/p99 violates target with sufficient traffic; fast error-budget burn | Wake on-call engineer, start service incident runbook |
| Warning | Critical dependency breaker remains open; fallback usage spikes; timeouts or Bulkhead rejections rise while API still meets SLO | Investigate during business hours or per on-call rotation |
| Info | Brief `OPEN` transition, breaker recovers automatically, fallback sustains responses, and SLIs do not degrade | Record in dashboard/event log; no page needed |

Do not page merely because a breaker transitioned to `OPEN` once. Opening can be the intended protective behavior; if fallbacks are serving cleanly, paging immediately creates noisy alerts. Conversely, if the API returns 5xx errors or latency breaches SLO, alert even if the breaker remains `CLOSED`.

Configure `for` so conditions persist long enough before firing. For service errors, use a short window for fast detection while requiring minimum traffic so a single stray request does not trigger an alert. Thresholds below are illustrative; tune them for your SLOs, baselines, and endpoint criticality.

## 8. Prometheus Alert Rules Example

The following rule group alerts on sustained server-side errors and open breakers. `CustomerFacing5xxRateHigh` carries severity `page`; the breaker alert carries severity `warning` so responders correlate it with user impact:

```yaml
groups:
  - name: order-service-circuit-breaker
    rules:
      - alert: CustomerFacing5xxRateHigh
        expr: |
          (
            sum(rate(http_server_requests_seconds_count{job="order-service",status=~"5..",uri!~"/actuator.*"}[5m]))
            /
            clamp_min(sum(rate(http_server_requests_seconds_count{job="order-service",uri!~"/actuator.*"}[5m])), 0.001)
          ) > 0.05
          and
          sum(rate(http_server_requests_seconds_count{job="order-service",uri!~"/actuator.*"}[5m])) > 1
        for: 10m
        labels:
          severity: page
        annotations:
          summary: "order-service HTTP 5xx rate is high"
          description: "More than 5% of requests failed for 10 minutes with traffic above 1 req/s. Check SLIs, dependencies, and fallbacks."

      - alert: CustomerLatencyP95High
        expr: |
          histogram_quantile(
            0.95,
            sum by (le) (
              rate(http_server_requests_seconds_bucket{job="order-service",uri!~"/actuator.*"}[5m])
            )
          ) > 0.8
        for: 10m
        labels:
          severity: page
        annotations:
          summary: "order-service p95 latency exceeds target"
          description: "p95 exceeded 800 ms for 10 minutes. Inspect slow routes and dependency call durations."

      - alert: InventoryCircuitBreakerOpen
        expr: max by (name) (resilience4j_circuitbreaker_state{name="inventory",state="open"}) == 1
        for: 2m
        labels:
          severity: warning
        annotations:
          summary: "Circuit Breaker inventory is OPEN"
          description: "Check failure rate, slow-call rate, timeouts, fallbacks, and order-service SLIs."
```

In this example, 5% errors, 1 req/s, 800 ms, and the `for` durations are illustrative thresholds. The p95 alert requires histogram buckets to be enabled. If an endpoint has very low request volume, tailor its minimum traffic condition; if SLOs define latency per route, group queries by `uri` rather than aggregating the whole application.

The `InventoryCircuitBreakerOpen` alert reports internal status only. On-call engineers should open the dashboard to inspect API error rate, latency, fallback behavior, and cache data before deciding whether to page. Adjust severity or routing according to your organization's operational policy.

## 9. Error Budget and Burn Rate Alerting

If your organization manages SLOs using error budgets, supplement static 5xx thresholds with burn rate alerts. With a 99.9% availability SLO, the error budget is 0.1% of eligible requests. Burn rate measures how fast the budget is consumed relative to the sustainable rate:

```text
burn_rate = observed_error_ratio / allowed_error_ratio
```

For example, a 1.44% error ratio against a 0.1% budget equals a 14.4x burn rate. If sustained, the budget will exhaust far faster than planned. In practice, combine multiple windows: a short window to detect severe outages quickly and a long window to avoid paging on brief spikes.

```promql
(
  sum(rate(http_server_requests_seconds_count{job="order-service",status=~"5.."}[5m]))
  /
  clamp_min(sum(rate(http_server_requests_seconds_count{job="order-service"}[5m])), 0.001)
) / 0.001 > 14.4
```

This query illustrates instantaneous burn rate for a 99.9% SLO; pair it with a longer window, traffic guardrails, and eligible-request filters before deploying it as a paging rule. Do not copy this threshold verbatim if your product has a different SLO, error definition, or evaluation window.

## 10. Cardinality, Sampling, and Data Quality

Dashboards can mislead or become expensive if metrics carry uncontrolled tags:

- Use route templates for `uri`, never concrete URLs with IDs.
- Use breaker ID, dependency, region, environment, and version as tags with finite value sets.
- Never attach user IDs, order IDs, tokens, query strings, or exception messages as tags.
- Never generate a new meter name per request; use stable meter names with bounded tags.
- Verify scrape targets are up, timestamps are current, sample counts are sufficient, and no series are missing before concluding a service is error-free.
- If histograms grow too large, restrict them to critical routes or enable buckets only on meters needed for SLO calculations.

Metrics are aggregated data. When investigating a specific request, use distributed traces and logs with correlation IDs. Do not replace metrics with log events; metrics excel at trend detection and alerting, while traces and logs excel at root-cause analysis for individual requests.

## 11. Runbook When an Alert Fires

When paged for a service-impacting failure:

1. Confirm scope: which endpoints, which regions, error/latency rates, and start time.
2. Compare against SLO and error budget; verify traffic is sufficient rather than triggered by a handful of requests.
3. Open the fallback and Circuit Breaker rows to identify which dependency is `OPEN`, `not_permitted` rate, timeouts, slow calls, and fallback reasons.
4. Check whether fallback data is fresh and contract-compliant; inspect cache hits, data age, and failed fallbacks.
5. Inspect Bulkhead queues, thread pools, HTTP connection pools, JVM, GC, and CPU to spot application-side bottlenecks.
6. Correlate with deployment timestamps, configuration changes, network errors, or dependency incidents.
7. Execute service runbook actions: shed load, roll back, shift traffic, restore the dependency, or fail over to an approved backup data source.
8. After recovery, confirm SLIs return to target, breakers stay stably closed, fallbacks subside, and queues/backlogs clear.

For alerts where a breaker is open while SLIs remain healthy, check fallbacks and monitor the dependency; never force-close a Circuit Breaker merely to make the dashboard green. Forcing a circuit closed can send traffic back into an unrecovered dependency.

## 12. Dashboard and Alert Acceptance Checklist

- Default dashboard view displays request rate, error ratio, p95/p99, and SLOs ahead of breaker states.
- Drill-down is possible from API routes down to dependencies and breaker IDs.
- Separate visibility exists for `OPEN`, `HALF_OPEN`, `not_permitted`, timeouts, fallbacks, and Bulkhead rejections.
- Data is tracked for fallback/cache quality and staleness.
- Histograms are enabled for routes requiring percentiles/SLOs; PromQL returns meaningful results.
- Paging alerts tie to user impact or burn rate; standalone breaker alerts remain warning/info.
- Rules include `for` durations, traffic guardrails, summaries, descriptions, and runbook links.
- Actuator endpoints are exposed selectively and secured.
- Metric tags contain no user IDs or high-cardinality values.
- Errors, timeouts, OPEN breakers, fallbacks, and recovery have been tested to confirm dashboards and alerts fire properly.

## References

- [Spring Cloud CircuitBreaker – Collecting Metrics](https://docs.spring.io/spring-cloud-circuitbreaker/reference/spring-cloud-circuitbreaker-resilience4j/collecting-metrics.html): Actuator dependencies, `resilience4j-micrometer`, and metrics auto-configuration.
- [Resilience4j – Micrometer](https://resilience4j.readme.io/docs/micrometer): Circuit Breaker, TimeLimiter, Bulkhead meters, and Prometheus export.
- [Spring Boot – Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html): Micrometer, HTTP server metrics, histograms, SLO buckets, and the Prometheus endpoint.
- [Spring Boot – Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html): endpoint exposure and access control.
- [Prometheus – Alerting Rules](https://prometheus.io/docs/prometheus/latest/configuration/alerting_rules/): PromQL alert expressions, `for`, labels, and annotations.
