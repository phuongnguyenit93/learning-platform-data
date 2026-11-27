# Sampling for High Traffic in Spring Boot Observability

When Spring Boot runs under high traffic, distributed tracing can generate hundreds of thousands or millions of spans per minute. Keeping every trace provides granular data but easily blows through network, CPU, memory, collector, and tracing backend budgets. **Sampling for high traffic** is the practice of designing an intentional collection policy: retaining enough representative traces to detect and investigate issues while keeping telemetry volume bounded during both normal load and incidents.

In the **SPRING_BOOT_OBSERVABILITY** module, sampling works alongside **Micrometer Observation, metrics, logs, context propagation, and exporters**. Metrics require consistent coverage to compute SLIs/SLOs; traces supply detailed paths for a subset of transactions; logs preserve error context per data policy. Lowering the trace rate does not mean degrading the reliability of every signal at the same ratio.

This lesson walks through volume estimation, head/parent/tail sampling, Spring Boot configuration, collectors, span budgets, and backpressure through to rollout strategy, effectiveness measurement, and incident handling. All numbers are **planning examples** and must be replaced with real measurements from each system.

## 1. Why Does High Traffic Need Budgeted Sampling?

A single request can create many spans: HTTP server, business observations, database calls, HTTP clients, retries, and messaging. Request count is not span count; calculate based on actual instrumentation depth.

For example, a checkout request creates on average:

| Span source | Spans/request (illustrative) |
| --- | ---: |
| HTTP server | 1 |
| Business observations | 3 |
| Database client calls | 4 |
| HTTP client calls | 2 |
| Additional average retries/messaging | 1 |
| **Total** | **11** |

If the system receives 5,000 requests/second with an average of 11 spans/request, the source can generate roughly **55,000 spans/second** before sampling. A retained trace can contain all 11 spans; 10% sampling does not mean selecting 10% of individual scattered spans, but typically selecting roughly 10% of traces.

Components carrying the load:

- **Application:** creating spans, maintaining context, serializing, and enqueueing exports.
- **Exporter:** batching, retries, timeouts, queues, and network I/O.
- **Collector:** receiving OTLP, transforming, sampling, batching, and routing.
- **Backend:** ingesting, indexing, storing, querying, and retention.
- **Operations:** resource cost, ingest/drop alerts, and incident searchability.

Sampling is not the only lever. If each request creates hundreds of useless spans, fix instrumentation. If each span carries huge attributes, cap metadata. If the collector runs out of memory, address capacity/backpressure. Sampling reduces retained traces, yet **cannot fix broken instrumentation and does not replace resource management**.

## 2. Estimating Trace Volume Before Choosing a Rate

A preliminary model:

\[
\text{Spans/second} \approx
\text{Requests/second} \times
\text{Average spans/request}
\]

With head-based sampling at rate \(p\), for new traces and a simple policy:

\[
\text{Exported spans/second} \approx
\text{Spans/second} \times p
\]

Example:

| Parameter | Hypothetical value |
| --- | ---: |
| Traffic | 5,000 requests/second |
| Average | 11 spans/request |
| Pre-sampling span rate | 55,000 spans/second |
| Head sampling | 10% |
| Expected exported span rate | 5,500 spans/second |

This is an estimate. Actual rates vary with parent-based sampling, request mix, spans/request, tail sampling, retries, exporter drops, and downstream services.

### Storage Capacity Estimate

Suppose average serialized payload is 1.5 KB/span and the backend stores 5,500 spans/second:

\[
5{,}500 \times 1.5\ \text{KB} = 8{,}250\ \text{KB/second}
\]

That corresponds to roughly 8.25 MB/second in decimal units, nearly 713 GB/day under continuous ingest before compression, indexing, and replication. This is only a **rough estimate**, because span sizes fluctuate sharply and storage overhead depends on the backend.

Do not take a single byte/span measurement from one small request as representative of all traces. Measure p50/p95/p99 distributions of bytes/span, spans/trace, and trace duration under both normal load and bursts.

## 3. Distinguishing Sampling, Span Limits, and Backpressure

| Mechanism | What does it decide? | Example |
| --- | --- | --- |
| Trace sampling | Keep or drop a trace | Select 5% of new traces |
| Span/attribute limits | Limit contents of an already-recorded trace | Max N attributes/span or N events |
| Rate limiting/backpressure | Limit processing/export throughput | Collector caps ingest or queues |

Trace-level sampling preserves parent-child structure better than selecting individual spans independently. Keeping only random spans inside a trace causes trace viewers to lose links and miss critical steps. Span/attribute limits control bloat within each trace once selected.

Backpressure is a safeguard when producers outpace processing capacity. It can cause queue growth, retries, drops, or higher latency; do not treat backpressure as an intentional sampling policy.

## 4. Head-Based Sampling for High Request Volumes

A head-based sampler decides right when the trace begins, usually based on the Trace ID, remote parent context, and attributes available at the start of the request.

```text
Incoming request
      |
      v
Create root span/context
      |
      v
Head sampler decision
      |
      +---- keep (p%) --------> recording spans
      |                            |
      |                            v
      |                     processor/exporter
      |
      +---- drop (1-p) ------> non-recording context
                                   |
                                   +--> context can still propagate
```

Advantages: early decision, reduces recording/export right at the application, minimal need to buffer traces in memory awaiting a final verdict, and easy to apply probabilistic/parent-based policies.

Limitations: decides before the request's final outcome is known; a selected request may succeed normally while a dropped request may end in a rare error or severe latency. If services fail to respect the parent sampling context, distributed traces can split into fragments.

Head sampling fits as a baseline policy when traffic is high and cost must be trimmed at the source. However, it cannot know with certainty at selection time whether a request will fail later.

## 5. Parent-Based Sampling and the Sampled Flag

In distributed tracing, the sampling decision can propagate alongside trace context. With W3C Trace Context, the `traceparent` header includes a flags field:

```text
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
             |  |                                |                |
             |  Trace ID                         Parent Span ID   flags
             version
```

In version `00`, the lowest bit of flags is the sampled bit: `01` indicates the bit is set; `00` indicates it is unset. Flags are neither credentials nor an authorization mechanism.

A **parent-based sampler** respects the sampling decision from parent context. If service A selects a trace, service B can continue recording child spans of the same trace; if the parent was not sampled, downstream generally follows that decision.

OpenTelemetry SDK example:

```java
Sampler sampler = Sampler.parentBased(
        Sampler.traceIdRatioBased(0.05));
```

For a new trace with no parent, the probabilistic sampler decides at roughly 5%. For a trace with a parent, the parent-based sampler normally follows the parent's sampled decision on default branches. Remote/local parent branches can be customized, provided you understand the impact on trace consistency.

### Traces From External Callers

An external client can send trace context. The system must decide whether to trust the parent sampled flag or enforce an ingress policy at the trust boundary. If untrusted callers can force `sampled=true`, they can inflate telemetry volume. If the parent is always overwritten, traces can fragment.

Ingress policies should specify which callers may continue context, how headers/baggage are validated, resource caps, and policies for untrusted parent context. Do not rewrite `traceparent` manually via string manipulation in filters/controllers; use a standard propagator.

## 6. Configuring Head Sampling in Spring Boot

With Spring Boot versions supporting Micrometer Tracing auto-configuration, you can set sampling probability:

```yaml
spring:
  application:
    name: orders-service

management:
  tracing:
    sampling:
      probability: 0.05
  otlp:
    tracing:
      endpoint: http://otel-collector:4318/v1/traces
```

`0.05` sets 5% for new traces per the auto-configured sampler in matching versions. It is not sampling for metrics, log rates, or Prometheus scrapes. The OTLP/HTTP endpoint and collector DNS are only examples; configure exact protocols, TLS/auth, networking, and collector receivers properly.

Spring Boot, Micrometer, and bridge versions differ in namespaces, exporter auto-configuration, and endpoint binding. Verify dependencies/BOM, property metadata, and actual export output. If the application owns `SdkTracerProvider` manually, configure the sampler on the provider actually used by instrumentation; avoid building an extra provider alongside auto-configuration.

### Initial Rates Are Not SLAs

| Situation | Trial level to consider | Notes |
| --- | ---: | --- |
| Local/low-load test | 100% | Easy debugging |
| Staging | 50–100% | Based on collector capacity |
| High-traffic production | 1–5% | Baseline to measure, not a rule |
| Low-load yet critical service | Can be higher | Balance cost |

Do not pick 1% just because another system uses 1%. At 100 requests/day, 1% keeps very few traces; at 100,000 requests/second, 1% still creates huge span volumes.

## 7. Tail-Based Sampling to Prioritize Error and Slow Traces

Tail-based sampling waits for the collector to receive spans before deciding whether to retain a trace. Policies can prioritize `ERROR` span status, traces exceeding duration thresholds, critical services/routes, and sample a portion of normal traces.

```text
Services (head sampling sufficient to send candidate traces)
             |
             v
       OTel Collector
             |
      group by Trace ID
             |
        wait decision window
             |
        tail sampling rules
          /          \
     error/slow     normal
        keep        sample
          \          /
             v
        tracing backend
```

The tail sampler cannot recover spans dropped by the SDK before export. If the head sampler runs at 1% and the tail sampler tries to retain errors, the collector can only pick errors from within the 1% of traces that arrived. For tail sampling to catch errors reliably, the source must ship enough candidate traces and network/collector budgets must sustain that volume.

Operational requirements:

1. **Trace affinity:** spans sharing a Trace ID must arrive at the same decision point/collector shard.
2. **Decision wait:** the collector waits long enough to receive spans from slower services; waiting too briefly leaves traces incomplete.
3. **Memory:** size for concurrent awaiting traces, trace sizes, and wait duration.
4. **Overflow:** know what the collector does when limits are exceeded: drop, evict, or fallback.
5. **Policy priority:** specify which traces win when multiple policies match, if the processor supports it.
6. **Error semantics:** instrumentation must set span status/attributes properly; an exception does not automatically mean every span receives status `ERROR`.

Tail-sampling processor syntax and capabilities depend on the OpenTelemetry Collector distribution/version. The following config illustrates logic only and must be verified against the installed component schema:

```yaml
processors:
  tail_sampling:
    decision_wait: 10s
    policies:
      - name: keep-errors
        type: status_code
        status_code:
          status_codes: [ERROR]
      - name: keep-slow
        type: latency
        latency:
          threshold_ms: 1500
      - name: sample-normal
        type: probabilistic
        probabilistic:
          sampling_percentage: 2
```

This example expresses the idea "keep errors, keep slow traces, sample a fraction of normal traces." Field names, policy evaluation, probabilistic implementation, and processing order must be cross-checked against your exact collector version. Ensure `sample-normal` does not conflict with `keep-errors`/`keep-slow`.

## 8. Combining Head and Tail Sampling

| Combination | Benefit | Risk |
| --- | --- | --- |
| 100% head + tail policies | Collector sees every candidate trace | Collector/network bear full volume |
| 20% head + tail policies | Reduces volume at source | Drops 80% of traces before collector, including errors |
| Parent-based head + collector tail | Keeps context consistent from SDK | Needs trace affinity and sufficient memory |
| 0% head + tail | Zero spans sent to collector | Tail sampler has no data to select |

No single head/tail ratio fits every service. Whichever approach you use, inspect the full path rather than just one application's configured ratio. If the goal is prioritizing rare errors, low head sampling can drop error traces before the collector ever sees them.

## 9. Capping Spans and Metadata Inside Each Trace

Trace-level sampling does not bound the size of retained traces. A single trace can hold thousands of spans or huge attributes. Under high traffic, add inner budgets:

| Component | Control measure |
| --- | --- |
| Spans/trace | Avoid low-value nested spans; inspect fan-out, retries, and batches |
| Span attributes | Limit key counts and value lengths; normalize enums |
| Span events | Record major milestones only; avoid logging inside loops |
| Span links | Keep only necessary batch/fan-out links |
| Exception details | Exclude raw payloads/secrets; bound stack/event sizes |
| Resource attributes | Stable service/process metadata only |
| Baggage | Small key allowlist; cap total header size |

The OpenTelemetry SDK supports limits on span attributes/events/links and attribute value lengths; configuration depends on SDK/auto-configuration and version. These limits do not replace metric tag controls, log event size budgets, or HTTP header limits.

Do not arbitrarily truncate IDs used for joins. Choping an order ID or business key can cause two distinct objects to collide on a prefix. Better not to record an ID if unnecessary; if needed, use an approved field and controlled format.

## 10. Backpressure, Queues, and Exporters Under Rising Traffic

Applications can record spans faster than the exporter/collector can ship them. When that happens, full queues, export timeouts, retries, and drops emerge. Sampling lowers recorded trace volume, but does not fix every operational bottleneck.

Monitor:

- Exporter queue occupancy/capacity if exposed by the SDK.
- Successful/failed span exports, timeouts, and retries.
- Collector accepted/refused/dropped spans and queue utilization.
- Collector CPU, memory, GC, and network throughput.
- Backend ingest latency, rejections, throttling, and storage saturation.

Do not grow queues indefinitely. Oversized queues merely delay drops and increase memory; if a process crashes, buffered spans in memory are lost too. Configure bounded queues, batch sizes, timeouts, and retries aligned with collector/backend capacity.

When emergency volume reduction is required, reduce sampling rates or enforce protective collector policies. Roll out changes consistently across services while retaining a minimum baseline to investigate critical failures.

## 11. Metrics and Exemplars: Jumping From Charts to Traces

In some registries/backends, **exemplars** let a histogram/counter metric sample reference a trace context without turning Trace ID into a series-wide label. This lets operators jump from a latency/error spike on a dashboard to an example trace when supported by the backend.

| Approach | Metric cardinality | Trace link |
| --- | --- | --- |
| Attach Trace ID as a tag on every metric | Very high; each trace can spawn new series | Direct reference, but prohibitively expensive |
| Use low-cardinality tags | Stable | Does not point to a specific transaction |
| Use exemplars if stack supports it | Keeps series labels stable | Attaches a trace reference to a sample |

Exemplar support requires compatibility across Micrometer registry, exporter, Prometheus/server or metrics backend, scraping, and UI. Sampling traces too low also causes exemplars to point to traces absent from the backend; recording an exemplar does not guarantee the trace was kept.

Metrics remain the primary source for request rate, error rate, and latency distributions. Tracing provides detailed examples for a slice of traffic. Never substitute sampled trace counts for request counts from metrics.

## 12. Logs Need Their Own Policy

Trace sampling does not automatically lower logging volume. If every request still emits many INFO logs, the log backend can become the bottleneck even when tracing drops 95%.

Design guidelines:

- Use metrics for rates, error ratios, and latency distributions.
- Write structured logs for meaningful business/error events, avoiding per-loop logs.
- Cap message lengths, stack traces, and field counts.
- Protect tokens, cookies, customer data, and request bodies.
- Populate Trace ID/Span ID via MDC when context exists and logging integration is configured.
- Choose a separate log sampling policy if needed; do not assume logs are only emitted when a trace is sampled.

A log carrying a Trace ID does not prove the trace was exported. If a trace was head-sampled out, log correlation may still include the Trace ID depending on the implementation. That correlation hint is helpful, though you cannot open the trace if the backend never retained it.

## 13. Sampling Policies by Traffic Type

| Traffic type | Suggestion |
| --- | --- |
| Health/readiness probes | Usually do not need traces on every probe; track health via metrics |
| Business-critical checkout/payment | Keep a rate sufficient for investigation; consider tail retention for errors/slowness |
| Long batch/jobs | Limit per-item spans; use span links or summaries to represent batches |
| Internal polling/heartbeats | Can exclude from tracing or sample very low if low value |
| Error/high-latency requests | Prioritize via tail policies if the pipeline permits |
| Traffic from untrusted callers | Validate context, cap metadata, and govern ingress sampling |

Route-specific policies must use stable attributes rather than raw URLs with IDs. With head samplers, many HTTP attributes such as status code do not exist yet when the root span starts; you cannot decide based on an outcome that has not occurred. That is why tail sampling is valuable for error/latency rules.

Do not exclude health checks everywhere by default. Probes can aid instance lifecycle debugging; sampling decisions must weigh operational needs and cost.

## 14. Safe Rollout of Sampling Changes

1. **Baseline:** record requests/s, spans/request, ingest bytes/s, collector memory, exporter errors, trace completeness, and backend cost.
2. **Set target:** e.g., cut ingest by 60% while retaining traces for errors/slowness recognizable by policies.
3. **Staging/load tests:** generate normal traffic, bursts, downstream errors, and high latency; check parent-child trees and selected spans.
4. **Canary a subset of services/instances:** adjust sampling ratio or tail policy, measuring volume delta and drops.
5. **Monitor SLOs and debugging:** confirm metrics retain full request/error/latency coverage and log correlation/exemplar lookups still work.
6. **Expand gradually:** roll out broadly only once collector/backend stay stable and policies prove they retain required cases.
7. **Clear rollback:** know how to revert config and avoid thrashing when the backend is overloaded.

### Rollout Metrics

| Group | Metrics |
| --- | --- |
| Application source | Sampled ratio, exporter queues/drops/errors |
| Collector | Accepted/refused spans, tail decisions, memory, overflow |
| Backend | Ingest rate, rejections, query latency, retention usage |
| Observability quality | Trace completeness, errors with representative traces, spans/trace |
| Independent signals | Request/error/latency metrics and log ingestion |

A 5% sampling ratio in the app does not guarantee exactly 5% of traces in the backend: parent context, remote sampling, multiple services, collector policies, and exporter failures all affect it. Measure the real rate by root traces and traffic profile.

## 15. Investigating When the Tracing Backend Overloads

Suppose production handles 8,000 requests/second averaging 14 spans/request. Theoretical span rate is 112,000 spans/second. Collector memory is high, the backend rejects ingest, and the trace viewer misses spans.

Do not simply slam sampling to 0 immediately. Instead:

1. Confirm what trace rate applications are actually sending and check for duplicate instrumentation.
2. Identify which spans drive volume: database loops, retries, health probes, or business spans.
3. Inspect exporter queues, retries, and collector refused/dropped metrics; retry storms can amplify load.
4. Trim low-value spans, bound attributes/events, and apply a head rate within budget.
5. If error/slow traces must be kept, evaluate tail sampling while ensuring adequate collector memory, trace affinity, and decision wait.
6. Check independent metrics/logs so you never lose SLIs and error details while adjusting sampling.
7. Scale capacity or shard collectors/backends realistically; never treat unbounded queues as a solution.

Target state after remediation: the backend receives complete representative traces with low drop rates; metrics maintain full coverage; logs capture critical errors; CPU/memory/ingest stay within budget.

## 16. Scenario Exercise

A Spring Boot system handles 6,000 requests/second, averaging 12 spans/request, with 5% head sampling and a hypothetical average payload of 1 KB/span.

**Questions**

1. What is the estimated pre-sampling span rate?
2. What is the expected selected span rate under simplified assumptions and no other policies?
3. What is the estimated raw ingest payload per second?
4. Does 5% sampling guarantee retaining all errors?
5. To prioritize errors and slow traces, what sampling structure should be considered?
6. Which metrics should be measured before rollout?

**Solution Hints**

1. Pre-sampling: 6,000 × 12 = 72,000 spans/second.
2. After 5% head sampling: roughly 3,600 spans/second under the assumptions.
3. At 1 KB/span: roughly 3,600 KB/second, or 3.6 MB/second raw payload, excluding compression, protocol, and storage overhead.
4. No. A rare error can still be missed by the head sampler.
5. Parent-based head sampling as a baseline paired with tail sampling at the collector to retain error/latency traces, ensuring enough candidate spans are sent and capacity suffices.
6. Measure span count/trace, bytes/span, requests/s, exporter queues/drops, collector memory/accepted/refused, backend ingest/rejections, trace completeness, request/error/latency metrics, and log ingestion.

### Completion Checklist

| Topic | Verification |
| --- | --- |
| Estimate spans/request and ingest rate | Can calculate pre/post-sampling volume |
| Head-based sampling | Understands early decisions and risk of missing rare errors |
| Parent-based sampling | Understands sampled decisions across services |
| Tail-based sampling | Knows collector needs full spans and state retention |
| Span/attribute limits | Distinguishes from trace sampling |
| Backpressure | Knows queues, retries, and drops are not sampling policies |
| Metrics/logs | Independent policies preserving SLI coverage |
| Exemplars | Knows how to link metric samples to traces without Trace ID labels |
| Cardinality/privacy | Avoids IDs or sensitive payloads in tags |
| Rollout | Has baseline, canary, impact tracking, and rollback |

**Remember:** At high traffic, sampling must start from a **measured telemetry budget**, not a gut-feel percentage. Head-based and parent-based sampling reduce volume at the source; tail-based sampling can prioritize errors/slowness but demands sufficient collector resources and candidate span delivery. Span/metadata limits, backpressure, stable metrics, structured logs, exemplars, and context propagation complement one another. Roll out incrementally, measuring trace completeness and diagnostic usefulness alongside cost so observability stays effective under heavy load.
