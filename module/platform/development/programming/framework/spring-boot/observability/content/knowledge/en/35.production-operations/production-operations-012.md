# Rolling Out Observability Changes with a Canary Strategy

Canarying an observability change means introducing an instrumentation or telemetry change into production in small increments, observing the outcome, and only then expanding it. The change may live in Spring Boot code, Micrometer settings, trace sampling, metric tags, log formats, exporter endpoints, or collector configuration. The goal is to confirm two things simultaneously: the application still meets its SLOs, and observability data remains complete, accurate, and within acceptable cost.

The key distinction is that observability changes directly affect how the system itself is measured. A release might cause zero request failures while still wiping out dashboard time series, breaking trace export, or triggering a sharp jump in active series. Therefore, a proper canary must verify both application behavior and the health of the telemetry pipeline.

## When Should You Canary an Observability Change?

Use a canary rollout whenever a change can impact production telemetry data or operational cost, such as:

- Adding a new Observation or changing Observation names, conventions, and key-values.
- Adding, removing, or renaming metrics; changing common tags; enabling histograms or altering buckets.
- Changing distributed tracing sampling rates, propagation, or exporter configuration.
- Changing log structure, how trace IDs/span IDs enter logs, or log filters.
- Switching telemetry destination endpoints, protocols, credentials, or collectors.
- Upgrading Micrometer libraries, tracing bridges, exporters, or agents that might alter signal formats or emission behavior.

A UI or business change can also use a canary, yet the question here is different: does the observability change alter how the system is measured or prevent signals from reaching their destination? You must separate the impact of the application itself from the impact of the measurement change.

## Define What to Protect Before Rolling Out

Before releasing, frame the change as a testable hypothesis. For example: "Adding a histogram for HTTP server requests will enable tracking latency percentiles in Prometheus; active series growth will stay within the defined cap, and request latency will not increase noticeably."

Document the impact scope:

| Component | Questions to Answer |
| --- | --- |
| Metrics | Which metrics are added, removed, or renamed? Which tags change? How many extra series are expected from histograms? |
| Logs | Does field structure change? Do logs still carry trace ID and span ID when a tracing context is present? |
| Traces | Do sampling rate, propagation, span names, attributes, or exporters change? |
| Export pipeline | Do endpoint, protocol, authentication, queues, retries, or timeouts change? |
| Consumers | Which dashboards, alerts, recording rules, queries, collectors, and storage systems depend on the old schema? |

Choose the metrics that govern expansion or rollback ahead of time. Include three groups:

1. **Application health:** request rate, error rate, p95/p99 latency, CPU and memory saturation, garbage collection, connection pools, and existing SLOs.
2. **Telemetry health:** whether scrape targets work, exporters report send errors, queues fill up, data is dropped, ingest latency rises, and logs/traces still reach the backend.
3. **Data quality and cost:** whether expected metrics or spans appear, tags carry valid values, and cardinality and ingest volume stay within budget.

Set thresholds against actual SLOs, baselines, and budgets. Never apply a single universal percentage across every service. Under low traffic, require enough requests or spans for statistically meaningful results; a canary receiving too little traffic cannot prove a change is safe.

## Design Data for Clean Comparison

A canary is only useful when the new version and the stable version can be compared under equivalent conditions. Attach a stable release identifier to telemetry resources or metrics if your backend and cardinality policy permit. For metrics, a version tag separates the two groups for comparison; for traces, a resource attribute like service version enables version filtering. Never use user IDs, order IDs, trace IDs, raw URLs, exception messages, or random values as low-cardinality metric tags.

Micrometer distinguishes low-cardinality and high-cardinality key-values in an Observation. Low-cardinality key-values suit bounded value sets such as provider or outcome. High-cardinality key-values can carry detailed context for traces, while still obeying sensitive-data rules and size limits. Never put personal data, tokens, request bodies, or secrets into telemetry.

For example, a provider name should come from a controlled set such as **visa**, **bank_transfer**, or **wallet**. Never use arbitrary merchant names or transaction codes as metric tags. When a transaction must be traced, use controlled correlation mechanisms with appropriate data protection policies.

Pay special attention to schema changes:

- Renaming a metric can leave existing dashboards and alerts with no data.
- Adding a common tag can recreate time series across many meters. Queries grouping by the old tag set may stop matching.
- Enabling histograms adds series for buckets, count, and sum; impact depends on meter count, tag count, and bucket layout.
- Changing sampling alters stored trace counts. Never compare total trace counts across two versions as if they represented total request counts.
- When two versions emit the same metric with different tag sets or buckets, aggregate queries must account for that difference explicitly.

If consumers need a transition window, preserve compatibility temporarily: update dashboards and alerts to read both old and new schemas, or dual-emit the new metric for a bounded period. Dual emission increases ingest and cardinality, so define an end date and cleanup criteria for the old schema upfront.

## Example Spring Boot Configuration

A Spring Boot application can expose health probes and a Prometheus endpoint so operations systems can inspect app health and scrape metrics. The example below illustrates enabling HTTP request histograms, adding a version tag, and setting tracing sampling:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,prometheus
  endpoint:
    health:
      probes:
        enabled: true
  metrics:
    tags:
      application: checkout-api
      version: canary-2026-11-22
    distribution:
      percentiles-histogram:
        http.server.requests: true
  tracing:
    sampling:
      probability: 0.1
~~~

This example assumes an application with Actuator, a matching Micrometer registry, and a configured tracing bridge/exporter. The Prometheus endpoint is available only when the Prometheus registry is on the classpath. Sampling probability takes effect only when tracing is enabled with a trace export path. Exact property names and integration details must be verified against your Spring Boot version.

Do not copy this configuration verbatim across every service without evaluating impact:

- **management.metrics.tags.version** adds a version tag to applicable meters. This helps canary comparisons, though it can multiply series count and require updating existing queries.
- **percentiles-histogram.http.server.requests** emits histogram series for HTTP server requests. Check bucket counts and backend cardinality before expanding.
- **tracing.sampling.probability** adjusts the share of sampled traces. Raising sampling can increase ingest costs; lowering sampling can leave too little data for debugging rare errors.
- Expose management endpoints only on internal networks or behind proper authentication and authorization. Never open Prometheus or sensitive actuator endpoints directly to the Internet.

When adding custom Observations, keep names stable and add only low-cardinality key-values with bounded value sets:

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;

public final class PaymentService {
    private final ObservationRegistry observationRegistry;
    private final PaymentGateway gateway;

    public PaymentService(
            ObservationRegistry observationRegistry,
            PaymentGateway gateway) {
        this.observationRegistry = observationRegistry;
        this.gateway = gateway;
    }

    public PaymentResult authorize(PaymentCommand command) {
        return Observation.createNotStarted(
                        "payment.authorize",
                        observationRegistry)
                .lowCardinalityKeyValue(
                        "payment.provider",
                        command.provider().metricValue())
                .observe(() -> gateway.authorize(command));
    }
}
~~~

In this example, **metricValue()** must return a value from a controlled provider set. Never substitute transaction IDs or user-supplied strings. If the operation is already auto-instrumented at the same boundary, avoid wrapping it in a duplicate Observation that double-counts latency and operation counts. Observations produce metrics or traces only when the registry has the required handlers and exporters configured.

## Canary Rollout Workflow

### 1. Capture baseline

Collect data from the current version over a representative timeframe. Record traffic, error rate, latency, resource usage, series count, scrape success rate, exporter failures, log volume, and trace volume. Ensure dashboards can filter by service, environment, deployment region, and version.

Audit existing queries and alerts relying on metrics or tags about to change. If renaming metrics or modifying histograms, prepare compatible queries before deploying.

### 2. Roll out to a small slice

Deploy the canary to a single instance or a small, representative slice of traffic. Keep the old version running as a control group. Whenever possible, run both groups in the same zone and infrastructure tier to minimize skew from differing networks, loads, or host configs.

Never select a canary solely on a single user cohort or a route with skewed traffic. Compare identical endpoints, regions, timeframes, and request types. When traffic distribution is uneven, normalize by request count or slice by cohort before drawing conclusions.

### 3. Verify both application and telemetry paths

First confirm startup, readiness, and liveness behave normally. Then verify:

- New metrics appear with exact expected names, tags, and values tracking traffic.
- Prometheus scrapes succeed; targets do not disappear and scrape duration does not spike abnormally.
- Histograms include expected buckets; dashboards and alerts evaluate cleanly.
- Traces are created, propagation across service boundaries works, and exporters deliver data.
- Logs remain parseable, contain correlation ID/trace ID when context exists, and introduce no formatting errors.
- Cardinality, queues, retries, drops, and ingest costs remain within bounds.

An endpoint returning HTTP 200 does not prove telemetry landed safely. Check the application, Collector, and receiving backend alike.

### 4. Compare under equal conditions

Compare canary and stable over the same time window and traffic segment. Use ratios rather than raw totals: errors/request, requests/second, CPU/request, or spans emitted per sampled request. For latency, use compatible histogram configurations and compare matching endpoints. If buckets differ, never interpret two percentiles as identical measurements.

When sampling rates differ, stored trace counts differ even if application behavior is identical. Use unsampled metrics to judge request volume and error rate; use traces to verify span structure, propagation, and diagnostic quality. Display each version's sampling rate clearly on dashboards.

### 5. Expand incrementally

Increase traffic share or instance count only when all three check groups—application health, telemetry health, and data budget—meet agreed thresholds. You can step from one instance to a small percentage, then scale up in stages. Each stage must hold long enough to observe representative load and gather sufficient samples; never expand just because the canary started cleanly.

If a signal lacks sufficient samples yet, hold the current canary percentage and wait longer or generate safe synthetic load. Never treat "no errors seen" as proof when metrics or traces are simultaneously being lost.

### 6. Finalize and clean up the old schema

Once the full rollout succeeds, monitor over a window matching your traffic cycle. Update dashboards, alerts, runbooks, and docs to reflect the new schema. Remove legacy metrics, tags, or configs only after confirming no consumers still depend on them and the compatibility window has closed.

## Halt and Rollback Criteria

Roll back or halt expansion if any of these conditions occur:

- Canary error rate, latency, or saturation breaches agreed SLO/baseline thresholds.
- Requests succeed yet expected metrics, logs, or traces fail to reach the backend.
- Exporters fail continuously, queues grow without draining, data drops occur, or ingest lag exceeds limits.
- Cardinality or cost exceeds budget; a new tag accepts unbounded values.
- Critical dashboards, recording rules, or alerts lose data readability during the canary.
- Trace context fails to propagate, logs lose correlation, or duplicate spans appear.

When rolling back, shift traffic back to the stable version and restore the last known-good instrumentation/exporter configuration. Re-check data after rollback because stopping telemetry emission can leave historical gaps. If an incompatible schema caused the issue, keep dashboards and alerts reading both schemas until transition completes.

Never let telemetry system failures break business requests. Export and shipping must use proper timeouts, queues, retries, and resource caps; avoid synchronous calls to observability backends on the request path. At the same time, monitor export errors explicitly so isolating telemetry never turns into silent data loss.

## Reading Signals When a Canary Misbehaves

| Symptom | Possible Cause | How to Check |
| --- | --- | --- |
| Dashboard shows gaps after deploy | Metric name/tag changed, scrape endpoint changed, or exporter failed | Inspect targets, new schema, queries, and exporter logs |
| Series count spikes suddenly | Added a common tag, high-cardinality tag, or enabled histograms | Inspect series by metric/tag, drop unbounded dimensions, and review buckets |
| Fewer traces while request metrics stay steady | Sampling rate changed or exporter dropped spans | Compare sampling config, queues, retries, and send failures |
| Logs lose trace correlation | MDC/correlation context or propagation changed | Check trace context across service boundaries and logging config |
| Canary latency rises while stable stays normal | Instrumentation overhead, blocking exporter, or traffic skew | Compare CPU/request, allocations, endpoints, and traffic conditions |
| Alerts fire despite healthy service | Queries do not handle new tags/schema or series are missing on one version | Test alert expressions against both stable and canary data |

## Pre-Expansion Canary Checklist

- [ ] Defined baseline and halt thresholds for application, telemetry, and cost.
- [ ] Separated canary and stable versions using a bounded-cardinality dimension.
- [ ] Dashboards, alerts, and recording rules handle both old and new schemas.
- [ ] Expected metrics, logs, and traces all arrive in the backend.
- [ ] Sampling rates and histogram settings are documented for accurate comparison.
- [ ] No high-cardinality tags contain IDs or user-controlled data.
- [ ] Exporters neither slow down nor break business execution paths.
- [ ] A rollback procedure exists along with post-rollback data verification steps.

An observability change should be considered complete only when it runs across the full target scope, signals remain complete and comparable, consumers are compatible, and operational costs stay within budget.
