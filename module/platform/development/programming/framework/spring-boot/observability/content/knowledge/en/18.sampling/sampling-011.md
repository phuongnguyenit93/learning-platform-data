# Balancing Cost and Observability

In the **Sampling** chapter of the **SPRING_BOOT_OBSERVABILITY** module, sampling is the decision of which traces are recorded and sent to the observability system. Sampling helps control telemetry traffic, storage capacity, and backend costs, yet every dropped trace also means losing some detail that might be needed during an investigation. The goal is not to drive trace counts as low as possible, but to retain sufficient evidence to understand errors, latency, and application behavior in production environments.

With Spring Boot, sampling policies must be considered alongside **Micrometer Observation, Micrometer Tracing, exporters, the Collector, metrics, and logs**. A fixed ratio may suit ordinary traffic yet miss rare errors; sampling too high can overload the Collector and backend; inconsistent head sampling across services can fragment traces. This lesson explains how to evaluate those trade-offs and build a verifiable policy.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain how sampling affects retained trace counts, ingest cost, and investigative capability.
2. Distinguish head sampling, parent-based sampling, and tail sampling.
3. Estimate span volume, bytes, and storage costs based on traffic, sampling ratio, and retention.
4. Select sampling policies according to workload, SLOs, critical transactions, and investigation requirements.
5. Understand why head sampling needs consistent decisions across services.
6. Explain the limits of tail sampling when traces span multiple services, multiple Collectors, or late-arriving spans.
7. Use metrics and logs to cover statistics and events that trace sampling does not retain.
8. Control cardinality, baggage, attributes, and sensitive data.
9. Roll out sampling changes in phases while measuring coverage, dropped spans, and backend impact.

## 2. What Problem Does Sampling Solve?

A trace typically contains many spans. If an API handles 2,000 requests/second and each request creates an average of 8 spans, the system can generate roughly 16,000 spans/second before sampling. With multiple services, retries, batch jobs, or fan-out, volume grows fast.

Sampling decides which slice of traces is recorded:

- **Sampling too high:** increases ingest, serialization, network, Collector memory/queues, and storage/indexing costs.
- **Sampling too low:** reduces evidence for rare errors, tail latency, critical transactions, and anomalous behavior.
- **Inconsistent sampling:** one service keeps spans while another drops them, leaving incomplete waterfalls.
- **Unobserved sampling:** not knowing whether data was lost at the sampler, exporter, Collector, or backend.

**Trace sampling is not request sampling for metrics.** Micrometer counters, timers, and histograms can continue aggregating every instrumented request while only a subset of traces is stored. Do not treat backend trace counts as request counts or SLO denominators.

## 3. Three Layers of Sampling Decisions

### Head Sampling

Head sampling decides whether to record a trace right when the trace begins, usually before knowing whether the request will ultimately succeed or fail and how long it will take.

Example keeping 10% of traces in Spring Boot/Micrometer Tracing on supported versions:

~~~yaml
management:
  tracing:
    sampling:
      probability: 0.1
~~~

Its advantage is an early decision, reducing the spans serialized and shipped out of the application, limiting network and Collector load. It is a simple approach when only a representative sample of normal traffic is needed.

Its limitation is that the sampler does not yet know whether the request will error or become slow at decision time. A rare error can fall into a dropped trace. If services decide independently, distributed traces can end up incomplete.

### Parent-Based Sampling

Parent-based sampling allows child services to follow the sampling decision already present in parent context. If service A decides to sample a trace, service B continues recording spans belonging to that trace; if the parent was marked not sampled, child services typically follow suit.

This matters for distributed tracing: services must preserve the same trace context and respect the propagated sampling decision. If a service starts its own root trace or unintentionally overrides the policy, data can split or become inconsistent.

### Tail Sampling

Tail sampling decides after the Collector has received part or all of a trace's spans. Policies can select traces using information known only once the request completes, such as:

- Trace has an error span status.
- Duration exceeds a threshold.
- Involves an important operation or service.
- Trace belongs to a prioritized traffic group.

Its advantage is retaining error/slow traces without keeping every normal request. However, the Collector must receive spans before deciding, hold temporary state, wait for related spans, and have sufficient capacity to group spans belonging to the same trace.

**Tail sampling cannot recover spans dropped by a head sampler before export.** If the application does not send a trace to the Collector, the Collector has no data to classify and keep.

| Criterion | Head sampling | Parent-based | Tail sampling |
| --- | --- | --- | --- |
| Decision timing | When trace starts | Follows parent decision | After Collector receives spans |
| Knows final request outcome | No | No, aside from parent-provided state | Yes, if enough spans arrive before timeout |
| Reduces network from app | Yes | Yes when parent decides to drop | Usually no; spans must reach Collector |
| Advantages | Simple, low upstream cost | Keeps decisions consistent | Prioritizes errors/slowness from final data |
| Limitations | Can miss rare errors | Depends on propagation and parent decision | Consumes memory/CPU, must group spans by trace |

Strategies can be combined. Clearly understand SDK head sampling and Collector tail sampling so important traces are not accidentally dropped before the tail policy gets a chance to inspect them.

## 4. Estimating Cost Before Choosing a Rate

A simple model:

- Request rate: requests per second.
- Average spans per request: mean spans per trace.
- Sampling ratio: fraction of traces retained.
- Average span size: span size after serialization/encoding.
- Retention: how long the backend stores data.

~~~text
spans_per_second =
    requests_per_second
    * average_spans_per_request
    * sampling_ratio

bytes_per_second =
    spans_per_second
    * average_serialized_span_bytes

daily_ingest_bytes =
    bytes_per_second * 86400
~~~

Hypothetical example:

| Parameter | Value |
| --- | ---: |
| Request rate | 2,000 requests/second |
| Average | 8 spans/request |
| Sampling ratio | 10% |
| Average span size | 1.5 KB |

Estimate: 200 traces/second retained; 1,600 spans/second; raw payload ~2.4 MB/second; equivalent to ~207 GB/day in decimal units.

This is a raw payload calculation, not a backend invoice. Actual size also depends on attributes, events, resource metadata, compression, batching, protocol overhead, indexing, replication, and retention.

### Sampling Ratio Is Not Exact Cost Savings Percentage

Cutting from 100% to 10% can sharply lower sent traces, yet does not mean total system costs drop by exactly 90%. Instrumentation still runs; Collectors, metrics, logs, indexing overhead, and baseline costs remain.

To budget accurately, measure spans/second before and after sampling, exported bytes, exporter queues/retries, Collector received/sent/refused/dropped spans, backend ingest/index growth, query latency, retention, replication, and CPU/memory.

## 5. Choosing Sampling by Trace Value

Not every request carries equal investigative value.

| Traffic type | Observability goal | Consideration |
| --- | --- | --- |
| High-load normal read requests | Understand common paths and baseline latency | Moderate head sampling rate may suffice. |
| Critical checkout/payment flows | Keep evidence for high-impact paths | Consider policies retaining verified transaction groups. |
| Error requests | Investigate rare errors and exceptions | Tail sampling can prioritize error status if full spans arrive. |
| Very slow requests | Understand tail latency and dependencies | Duration-based tail sampling can help. |
| Health checks/noise traffic | Avoid ingesting low-value requests | Consider excluding or sampling at a very low rate per policy. |
| Batch jobs | Track critical steps or job failures | Use operation naming and dedicated policies; avoid oversized traces. |

Never put raw customer IDs, emails, order IDs, or tokens into sampling attributes. Use grouping attributes with bounded values such as operation names or transaction classes. Values driving priority policies must come from trusted sources and must not be forgeable by callers to consume ingest resources.

### Clearly Define What Counts as an Error

A server span with error status is a useful signal, yet a business rejection may be a 4xx response rather than an exception. Conversely, an error on a client span might not show up on a downstream server span. Policies must clarify whether to keep traces based on any span's status, the entry server span's status, exception/error events, overall trace duration, or controlled business attributes.

Do not assume every HTTP 4xx is a system failure; define business semantics and SLOs.

## 6. Spring Boot: Configuring Sampling Probability

Spring Boot 3.x example with Micrometer Tracing and the OpenTelemetry bridge:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    implementation 'io.micrometer:micrometer-tracing-bridge-otel'
    implementation 'io.opentelemetry:opentelemetry-exporter-otlp'
}
~~~

Example keeping all traces in a lab:

~~~yaml
spring:
  application:
    name: order-api

management:
  tracing:
    sampling:
      probability: 1.0
  otlp:
    tracing:
      endpoint: http://otel-collector:4318/v1/traces
~~~

100% sampling helps observe spans while verifying instrumentation and exporters in test environments. Do not carry this config straight to high-traffic production without assessing capacity and retention.

Illustrative production trial with 5% sampling:

~~~yaml
management:
  tracing:
    sampling:
      probability: 0.05
~~~

These are only illustrative values. Appropriate rates must be sized from traffic, spans per trace, attribute sizes, backend capacity, and investigative requirements. If using the Brave bridge or a custom sampler bean, configuration/precedence can differ; inspect the effective configuration of Spring Boot and the tracer implementation.

### Be Careful with Custom Samplers

When declaring a custom sampler, verify it is actually used by the tracer/SDK wired into the Micrometer Tracing bridge. Instantiating a standalone OpenTelemetry SDK can send Micrometer spans and direct OTel spans down two different pipelines with unshared contexts, different resource attributes, or different exporters.

Only add custom beans for concrete needs and when you understand where auto-configuration is being replaced or extended.

## 7. Parent-Based Sampling and Trace Completeness

In a request spanning multiple services, the ingress service usually creates the root/server span. When calling downstream, client instrumentation injects trace context and sampling flags. The child service extracts context and makes a decision consistent with the parent-based policy.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant A as order-api
    participant B as inventory-api
    participant X as Trace backend

    C->>A: HTTP request
    Note over A: Root decision: sample / drop
    A->>B: RPC + trace context + sampling flags
    Note over B: Follow parent decision
    B-->>A: Response
    A-->>C: Response
    A->>X: Export spans if sampled
    B->>X: Export spans if sampled
~~~

If `order-api` decides to sample a trace yet `inventory-api` uses an independent root sampler and decides to drop, the backend may show the root and client spans while missing `inventory`'s server span. Common causes of incomplete traces:

- A service fails to extract W3C Trace Context or B3 properly.
- Client instrumentation does not inject headers.
- Context is lost across async/thread boundaries.
- A service uses a non-parent-based custom sampler.
- Services use different tracers/versions with incompatible propagation.
- Exporter/backend drops part of the data or spans arrive late.

When a trace is missing a service, inspect **trace IDs, parent span IDs, propagation, and samplers at every hop** before increasing the system-wide sampling ratio.

## 8. Tail Sampling at the OpenTelemetry Collector

Tail sampling is useful when retaining traces based on outcomes known only after a request finishes. Illustrative configuration example:

~~~yaml
receivers:
  otlp:
    protocols:
      grpc:
        endpoint: 0.0.0.0:4317
      http:
        endpoint: 0.0.0.0:4318

processors:
  memory_limiter:
    check_interval: 1s
    limit_mib: 1024
  tail_sampling:
    decision_wait: 10s
    num_traces: 50000
    policies:
      - name: keep-errors
        type: status_code
        status_code:
          status_codes: [ERROR]
      - name: sample-normal
        type: probabilistic
        probabilistic:
          sampling_percentage: 5
  batch: {}

exporters:
  debug:
    verbosity: basic

service:
  pipelines:
    traces:
      receivers: [otlp]
      processors: [memory_limiter, tail_sampling, batch]
      exporters: [debug]
~~~

This is an illustrative configuration, not a production config to deploy verbatim. Verify your Collector version and distribution: the tail sampling processor must be included in your build; processor ordering affects data; the `debug` exporter is only for testing. Production needs a backend exporter, TLS/auth, queues/retries, and proper resource limits.

Parameters:

- **decision_wait:** how long the Collector waits for more spans before deciding.
- **num_traces:** limit on traces held in tail sampling state; size according to traffic.
- **status_code:** illustrative policy retaining traces with status `ERROR`.
- **probabilistic:** illustrative policy retaining a fraction of normal traces.
- **memory_limiter:** protects the Collector against memory pressure; set thresholds based on process/container limits.

There is no guarantee every error is retained. An error span can arrive after the wait window, fail to arrive due to exporter drops, or spans of one trace may land on different Collectors.

### Tail Sampling Needs Enough Spans

If a distributed trace sends spans to multiple independent Collectors, each Collector only sees a fragment. Tail samplers can make decisions from incomplete data or disagree. Architectures typically require routing/trace affinity so spans of the same trace reach the same processor.

This creates a trade-off: tail sampling retains important traces better, yet increases requirements for stateful routing, memory, networking, and operational complexity.

## 9. Combining Head and Tail Sampling

A combined strategy can look like:

1. Applications use a parent-based sampler to keep decisions consistent across the entire trace.
2. Applications skip clearly low-value/noise traces when doing so does not hurt investigative goals.
3. Traces shipped to the Collector are classified by the tail sampler on errors, duration, and policies.
4. The Collector exports selected traces to the backend.
5. Metrics and logs continue collecting via their own pipelines.

However, **5% head sampling followed by tail sampling cannot recover errors inside the 95% dropped at the application**. If the Collector must decide to retain errors after seeing them, applications must forward relevant data to the tail-sampling tier, or head policies must ensure those transaction groups are sent.

## 10. Sampling and Metrics: Covering Aggregates

Metrics provide aggregate statistics across traffic, ideal for request rates, error rates, latency histograms, and saturation. Metrics are not reduced by default alongside trace sampling ratios.

| Investigation need | Appropriate source |
| --- | --- |
| Service-wide request rate and error rate | Counters/rates and HTTP server metrics. |
| P95/P99 by route | Timer histograms and metrics backend queries. |
| Path of an individual request | Trace if sampled and stored; correlation ID in logs. |
| Exception messages, business events | Structured logs. |
| Which dependency drives latency up | Client/server spans paired with dependency metrics. |
| JVM/GC/connection pool pressure | Runtime and application metrics. |

Example PromQL for error ratio:

~~~promql
sum(rate(http_server_requests_seconds_count{
  job="order-api",status=~"5.."
}[5m]))
/
sum(rate(http_server_requests_seconds_count{
  job="order-api"
}[5m]))
~~~

Series names and labels depend on exporter/instrumentation. Verify actual payloads, handle zero denominators, and filter accurately by service/route. This query uses metrics, not traces.

When trace ratios are low, keep sufficient metric histograms for SLOs and logs with proper correlation. Metrics tell you where an issue happens and how often; sampled traces help explain an individual execution path.

## 11. Sampling Does Not Replace Cardinality Controls

A trace can carry many attributes and events. Reducing trace counts while keeping hundreds of long attributes on every span still creates large payloads and high indexing costs.

- Use stable span names; avoid embedding order IDs or user IDs in names.
- Use low-cardinality tags for metrics such as `operation`, `outcome`, `method`, and route templates.
- Add high-cardinality trace attributes only for concrete diagnostic purposes.
- Never put tokens, cookies, emails, card numbers, or request bodies into traces/baggage.
- Limit repetitive events or massive stack traces.
- Review resource attributes to avoid creating excessive unnecessary service-instance groupings.

Sampling reduces how many traces/records are kept; cardinality/attribute policies reduce the size and index dimensions of each record. Measure both.

## 12. Baggage and Sampling

Baggage propagated with context can help policies classify traces using small metadata, provided external values are controlled. Useful fields when verified and allowlisted include request class, tenant tier, or region.

Do not use customer ID, email, session ID, or tokens to drive priority sampling. Callers must not be allowed to tag themselves "premium" to force trace retention or inflate resource usage. Policy-driving values must be verified at trust boundaries or produced by trusted services.

Tail-sampling policies can inspect attributes like transaction class, provided you verify the Collector sees that attribute on the right span. Having baggage in context does not mean it automatically becomes a span attribute; instrumentation/processors must explicitly copy or convert it if needed.

## 13. Logs and Correlation When Traces Are Sampled Out

When a trace is dropped by a head sampler, the backend may lack the trace even though the application still emits logs. Therefore:

- Keep logging meaningful exceptions and business events.
- Use controlled correlation/request IDs; trace IDs only link to traces when traces are stored.
- Never log full baggage dumps or gRPC metadata.
- Never treat an unfound trace as proof that a request never executed.
- Keep full metric coverage to detect error rate and latency drift.

Logs can contain a trace ID yet the backend finds no trace due to sampling. This is an expected possible outcome, not necessarily an exporter error. During investigation, use timestamps, service, route, managed request IDs, and metrics to reconstruct context.

## 14. Sampling and Distributed Trace Completeness

| Situation | Symptom | Risk |
| --- | --- | --- |
| Root sampled, child dropped | Entry span present, downstream server span missing | Incomplete waterfall. |
| Root dropped, child self-sampled | Child trace lacks parent span | Detached spans cannot be linked completely. |
| One service fails to propagate context | Trace ID changes between services | Misleading dependency analysis. |
| Tail sampling split across multiple Collectors | Backend holds partial trace fragments | Policies decide on incomplete data. |
| Spans arrive after `decision_wait` | Some spans missing from retained trace | Trace lacks completion segments. |

When choosing samplers for OpenTelemetry or Brave, verify parent-based behavior and the propagation formats supported by services. In mixed systems, test W3C/B3 at gateways and every HTTP/gRPC/messaging boundary.

## 15. Runbook: Adjusting Sampling When Costs Rise

Suppose tracing backend ingest triples after a deployment. Do not immediately drop sampling across the entire system without finding the volume driver.

1. **Identify the source of growth:** which service increased spans/second, attribute bytes, or events? Is it traffic, retry loops, or duplicate instrumentation?
2. **Inspect sampling decisions:** ratios per service, parent-based behavior, and whether a custom sampler overrides settings.
3. **Measure span size:** did attributes, events, exception stack traces, baggage, or resource metadata grow?
4. **Inspect the Collector:** received/sent/refused/dropped spans, exporter queues/retries, tail sampler state, memory, and CPU.
5. **Inspect the backend:** ingest bytes, index growth, retention, and query cost.
6. **Identify high-value trace groups:** errors, slow requests, critical transactions, batch jobs, or noise traffic.
7. **Test policy in staging/canary:** compare error coverage, p95/p99, complete traces, and cost.
8. **Controlled rollout:** apply per service/traffic cohort, watching dropped spans and backend health.
9. **Confirm SLO evidence:** metric histograms/error rates and logs maintain coverage.
10. **Document the policy:** owner, rationale, review thresholds, and rollback steps.

Do not lower sampling to mask Collector or backend failures. If exporter queues fill up because the backend times out, cutting trace volume buys temporary breathing room, yet the underlying ingest failure must still be fixed.

## 16. Common Pitfalls

| Symptom | Possible cause | How to check |
| --- | --- | --- |
| Fewer traces than expected ratio | Parent decisions, custom sampler, traffic mix, or exporter drops. | Check sampled flags, sampler config, and pipeline counters. |
| Error traces not found | Head sampler dropped; error lacked status; Collector/backend drop. | Compare error metrics/logs with sampling decisions and Collector stats. |
| Root span present, child services missing | Inconsistent propagation/sampler or uninstrumented downstream. | Check `traceparent`/B3 and parent-based sampler. |
| Tail sampler misses slow traces | Evaluated span lacks attribute/duration, late spans, or split trace. | Check policy inputs, wait duration, and trace routing. |
| Collector memory spikes sharply | Tail sampling holds too much state or long trace durations. | Check trace counts, wait time, traffic, and memory limiter. |
| Trace count drops yet ingest bytes fall less | Large span sizes/attributes or shared backend metrics/logs dominate volume. | Measure bytes/span and separate signals. |
| More traces than expected requests | Many spans/request, retries, or duplicate instrumentation. | Analyze spans/trace and client/server instrumentation. |
| Logs have trace ID yet backend lacks trace | Trace sampled out or exporter/backend drop. | Check sampler and trace pipeline. |
| Metrics also drop with sampling | Instrumentation/handler or query impacted unintentionally. | Check MeterRegistry and metrics scraping separately. |
| Backend overloaded despite low sampling | High cardinality, retention/indexing, service count, or large payloads. | Measure dimensions, bytes, index, queries, and storage policies. |

## 17. Self-Check Exercises

### Exercise 1 — Volume Estimation

A service receives 500 requests/second, each creating an average of 10 spans, with 20% sampling. Estimate retained spans/second.

**Answer:** 500 × 10 × 0.2 = **1,000 spans/second**. This is an estimate prior to exporter drops, additional instrumentation, or trace fan-out.

### Exercise 2 — Head Sampling Misses Rare Errors

An API uses 1% head sampling. A failing request is dropped by the sampler at the start. Can a tail sampler at the Collector still retain that trace?

**Answer:** No. The Collector never receives spans dropped by the head sampler. For tail sampling to classify a trace, applications must send relevant data to the Collector.

### Exercise 3 — Metrics Exceed Traces

Metrics record 100,000 requests in an hour while the backend holds roughly 5,000 traces. Does that mean 95,000 requests were lost by the application?

**Answer:** You cannot conclude that. The ratio can reflect 5% sampling. Metrics and tracing are separate pipelines; inspect the sampler, exporter, and Collector to confirm whether traces were dropped intentionally or failed in transit.

### Exercise 4 — Tail Sampling Has Errors Yet Drops

A trace encounters an error in service C, yet the backend only stores spans from A and B. Name two possible causes.

**Answer:** C's error span arrived after the decision wait or failed to export; or spans of the same trace routed to different Collectors so the tail sampler lacked the full trace. Also check whether status/error attributes were set properly.

### Exercise 5 — Should Sampling Be Raised to Fix Fragmented Traces?

Services A and B show different trace IDs. Should probability be raised from 10% to 100%?

**Answer:** That does not fix the root cause. Check context propagation, W3C/B3 compatibility, client/server instrumentation, and async boundaries. Sampling ratio changes how many traces are selected, not how two separate contexts link together.

### Exercise 6 — Why Didn't Costs Drop 90%?

Sampling dropped from 100% to 10%, yet the backend bill decreased by less than 90%. List three possible explanations.

**Answer:** Baseline platform/index/replication costs remain; span sizes grew due to attributes/events; metrics/logs or other pipelines still consume ingest; retention/query and storage overhead do not scale down linearly.

## 18. Sampling Policy Design Checklist

- [ ] Defined investigative goals and traffic groups of differing value.
- [ ] Measured traffic, spans/request, span sizes, and ingest before setting rates.
- [ ] Clearly understand head sampling and parent-based sampling per service.
- [ ] If using tail sampling, Collector receives complete spans with proper trace-based routing.
- [ ] Capacity planned decision wait, max traces, memory limits, and peak traffic.
- [ ] Policies exist for errors, slow traces, business-critical operations, and noise traffic.
- [ ] No sensitive data or caller-forgeable values used as priority conditions.
- [ ] Trace context propagation and sampled flags are consistent across HTTP, gRPC, and messaging.
- [ ] Metrics preserve full coverage for request count, error rate, latency histograms, and SLOs.
- [ ] Logs retain exceptions/business events and correlation per policy even when traces are sampled out.
- [ ] Dashboards track received/sampled/exported/dropped spans, exporter queues, and backend ingest.
- [ ] Measure both span counts and bytes; control attributes/events/cardinality.
- [ ] Sampling changes tested in staging/canary with clear rollback criteria.
- [ ] Assigned owner, rationale, and review schedule when traffic or SLOs shift.

**Remember:** Sampling is a decision on how to allocate an observability budget. Head sampling cuts costs early without knowing request outcomes; parent-based sampling keeps traces consistent; tail sampling can prioritize errors/slowness but requires the Collector to receive complete spans and hold state. Use metrics for aggregate statistics, logs for essential events, and selected traces to understand execution paths. A good policy preserves critical evidence within cost limits—not merely the policy with the lowest rate.
