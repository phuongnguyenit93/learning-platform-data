# Trace Sampling Budget in Spring Boot

Distributed tracing generates telemetry proportional to request traffic, spans per trace, and attribute size. Keeping every trace can exceed ingest capacity, drive up network/storage/indexing costs, and slow down queries. Sampling too aggressively or at the wrong point can drop critical traces such as errored requests, high-latency calls, or dependency failures. A **trace sampling budget** is a measurable budget for recording, processing, transmitting, and storing traces that balances investigation capability against resources.

In the SPRING_BOOT_OBSERVABILITY module, a sampling budget connects Micrometer Tracing, OpenTelemetry, the Collector, exporters, and the backend. This lesson focuses on estimating trace volume, choosing head vs. tail sampling, prioritizing errors and slow traces, allocating Collector/backend capacity, controlling attribute size/cardinality, testing policies, and operating sampling safely.

## Learning Objectives

1. Explain sampling and sampling budgets in distributed tracing.
2. Estimate trace/span volume from request rate and spans per trace.
3. Distinguish head sampling, tail sampling, and probabilistic sampling.
4. Design policies that prioritize errors, high latency, and critical traffic.
5. Understand propagation of sampling decisions across distributed services.
6. Size Collector memory, throughput, queues, and backend ingest.
7. Distinguish trace sampling from metrics aggregation and retention.
8. Control attribute size, cardinality, and sensitive data.
9. Test sampling policies, dropped spans, and trace completeness.

## 1. What Is a Trace Sampling Budget?

Sampling decides which traces are recorded and forwarded. A sampling budget caps the volume of traces/spans the system can handle within a defined time window or cost limit.

The budget should include:
- requests/second flowing through the system;
- the fraction of requests that create traces;
- average spans and distribution of spans/request;
- size of span attributes, events, and links;
- bytes/second across applications and the Collector;
- Collector memory/CPU/queue capacity;
- backend ingest/indexing/storage capacity;
- retention and query workload.

You cannot simply pick a sampling probability without measuring the factors above.

### 1.1. From Requests to Trace Volume

A trace typically contains a server span, client spans, database spans, and business spans. A single request may create a few spans or hundreds of spans if there is fan-out, ORM N+1 queries, or many async tasks.

~~~text
Request
  ├─ HTTP server span
  ├─ Business span
  ├─ HTTP client span
  ├─ JDBC span
  └─ Additional child spans
          |
          v
      Trace payload
          |
          v
    Collector / Backend
~~~

Spans per trace and span size can vary widely. Use p50/p95/p99 and workload profiles rather than relying solely on averages.

## 2. Estimating the Trace Budget

An initial model:
- `R`: incoming requests per second;
- `S`: average spans per request/trace;
- `P`: head sampling probability;
- `B`: average serialized bytes per span.

When each request creates one trace and sampling happens independently at the head:

\[
\text{sampled traces/sec} \approx R \times P
\]

\[
\text{sampled spans/sec} \approx R \times S \times P
\]

\[
\text{ingest bytes/sec} \approx R \times S \times P \times B
\]

For example, a service receives 2,000 requests/second, averaging 12 spans/trace, with 5% sampling and 1.2 KB average per span:

- Sampled traces: 2,000 × 0.05 = 100 traces/second.
- Sampled spans: 2,000 × 12 × 0.05 = 1,200 spans/second.
- Raw payload: 1,200 × 1.2 KB = 1.44 MB/second.

This is a raw payload estimate. Protocol framing, compression, retries, replication, indexing, and backend overhead can make actual resource consumption differ substantially.

### 2.1. Size for Peak Traffic

Do not calculate only from average RPS. If traffic triples during peak hours, spans/second and bytes/second can grow proportionally. Use sustained peak traffic and burst profiles to size headroom.

### 2.2. Uneven Span Distributions

Simple requests might produce 4 spans; fan-out requests might produce 80. Use a spans/trace histogram and p95/p99 to catch outliers. A few huge traces can consume a large share of memory/bytes even at low trace counts.

### 2.3. Attribute Size

Spans with many attributes, events, stack traces, or baggage can be far larger than simple spans. Cap attribute counts, string lengths, event counts, stack trace sizes, baggage keys/values, captured headers, and SQL text. Shrinking span size is often more effective than adjusting sampling when unnecessary attributes are attached to every trace.

## 3. Head Sampling

A head sampler decides whether to record a trace when the trace starts, usually at the root span. The decision is made before the final request outcome is known.

Advantages:
- reduces spans and CPU early;
- makes ingest rates easy to predict;
- avoids holding whole traces in the Collector;
- supports distributed decisions when trace context propagates sampling flags.

Limitations:
- does not know whether the request will error or run slowly at the end;
- traces dropped at the head may not be fully recorded downstream;
- a static sampling probability may not fit changing traffic.

### 3.1. Parent-Based Sampling

A parent-based sampler typically honors the parent's sampling decision. If the root trace is sampled, downstream spans continue sampling; if the parent is not sampled, child spans generally do not record/export under that decision. This keeps traces consistent across services.

### 3.2. Probability Sampler

Example Spring Boot sampling probability configuration:

~~~yaml
management:
  tracing:
    sampling:
      probability: 0.05
~~~

Illustrative value of 5%. Properties and the tracing bridge must match your Spring Boot version. Sampling probability is not an exact per-minute ratio; at low traffic, actual trace counts fluctuate statistically.

### 3.3. Head Sampling Cannot Prioritize Future Errors

If a trace is dropped at the root by the sampling decision, an error occurring later cannot make the sampler go back in time to keep the trace. Prioritizing errors/slow traces requires tail sampling or a strategy that carries enough data to the decision point.

## 4. Tail Sampling

Tail sampling defers the decision until the Collector has received enough spans for the trace or the decision wait window expires. The Collector can retain a trace if it has an error span, latency above a threshold, a critical operation/service, a prioritized traffic class, or is randomly selected to represent normal traffic.

The advantage is deciding based on the final outcome. The drawback is that the Collector must maintain state/buffers for pending traces, ingest spans from multiple services, and handle late-arriving spans.

### 4.1. Trace Affinity

Spans sharing the same Trace ID must reach the same tail-sampling decision point. If spans split across independent Collectors, each Collector sees only part of the trace and may decide incorrectly or export incomplete traces. Route by Trace ID to the proper Collector/decision tier, or use an architecture with state coordination.

### 4.2. Decision Wait and Late Spans

The Collector waits for a decision wait window to receive additional spans. Too short a wait drops late-arriving spans; too long a wait increases memory usage and export delay. Choose based on end-to-end span arrival distribution and trace duration, not just average request time.

### 4.3. Tail Sampling Is Not Free

Tail sampling reduces data stored in the backend, yet still requires ingesting and buffering candidate spans prior to the decision. It shifts part of the cost from backend storage to Collector memory/CPU/network. Budgets must include unsampled candidate traffic.

## 5. Combining Head and Tail Sampling

An architecture can use head sampling to cap traffic before the Collector, then tail sampling to choose key traces from the remaining traffic. However, if the head sampler drops a trace, the tail sampler cannot recover it.

Example:
- head sampling keeps 20% of traffic;
- tail sampling keeps errors within that 20%;
- tail sampling keeps 10% of the remaining successful traces.

This policy guarantees errors only within the subset forwarded by the head sampler. If nearly all errors must be kept, head sampling must pass enough traffic to the tail tier or use an appropriate adaptive/consistent sampling approach.

### 5.1. Priority Rules

A tail sampling policy might prioritize:
1. traces with error status;
2. traces exceeding a latency threshold;
3. traces involving critical operations;
4. a percentage of successful traces as a baseline;
5. dropping remaining traces when the budget is full.

Do not keep only errors: you need baseline successful traces to compare latency and understand normal behavior.

### 5.2. Adaptive Sampling

Adaptive sampling adjusts the sampling rate according to traffic or budget. When RPS rises, the rate can drop to keep spans/second within limits; when traffic is low, the rate can rise. Distributed services need decision propagation/consistency to avoid partial traces. Rate changes need smoothing and guardrails to avoid oscillation.

## 6. Distributed Sampling and Propagation

The sampling decision travels with the trace context. With W3C Trace Context, `traceparent` carries trace ID, parent span ID, and trace flags; the sampled flag tells downstream whether the trace is being recorded under the current decision.

~~~text
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
                                                                 ^^
                                                           sampled flag
~~~

Services must align on a sampling strategy. If service A samples while service B drops on its own, traces may miss database/client spans. If service B starts a new root trace instead of continuing context, distributed correlation breaks.

### 6.1. Parent-Based Consistency

Use a parent-based strategy when downstream should respect upstream sampling decisions. With message queues, inject trace context into message headers and extract it at the consumer; consumer spans either continue the trace or use links depending on messaging semantics.

### 6.2. Trust Boundary

Do not blindly trust the sampling flag from every external caller. Public ingress can apply its own sampler/normalization before propagating decisions internally. If external callers can force `sampled=true` on every request, the backend could be flooded. Design the trust boundary at the gateway/ingress.

## 7. Budgeting for the OpenTelemetry Collector

The Collector receives telemetry, runs processors, and exports to the backend. With tail sampling, it also holds trace state. Budget for receiver throughput, processor CPU, memory limiter, batch queues, tail sampling cache, exporter queue/retries, and network egress.

### 7.1. Memory Limiter

The memory limiter processor lets the Collector reject/apply backpressure when memory nears its limit. Set limits according to container memory and leave headroom for runtime/other components. If the limiter continually rejects data, reduce input, scale capacity, or fix backend bottlenecks; do not raise memory indefinitely.

### 7.2. Batch Processor and Exporter Queue

The batch processor groups telemetry to cut network overhead. The exporter sending queue absorbs short backend slowdowns. Overly large queues hold excessive data in memory/disk and raise delay; overly small queues drop during bursts.

### 7.3. Tail Sampling Capacity

Tail sampling needs memory proportional to pending traces, spans/trace, and payload size. Estimate:

\[
\text{buffer memory} \approx
\text{in-flight traces} \times
\text{avg spans/trace} \times
\text{avg bytes/span} \times
\text{overhead factor}
\]

The overhead factor depends on implementation and data structures; benchmark/load test rather than assuming `1`.

### 7.4. Collector Scaling

Tail sampling state requires trace-aware routing. Scaling Collectors behind random load balancing can split spans of the same trace across replicas. Route by Trace ID before the tail-sampling tier or use an architecture with decision coordination. Test trace completeness during scaling and when a Collector restarts.

## 8. Backend Ingest, Storage, and Retention Budget

Sampling is only part of the cost. The backend handles ingest, indexing, querying, replication, and retention.

A raw daily storage model:

\[
\text{GB/day} \approx
\frac{\text{bytes/sec} \times 86.400}{1.000.000.000}
\]

At 1.44 MB/second, raw payload is roughly 124 GB/day before compression/replication/index overhead. Compression can shrink storage; indexing and replication can raise total cost. Use real backend measurements to set budgets.

### 8.1. Retention by Trace Class

Different retention periods can apply to error traces, slow traces, normal sampled traces, critical workflow traces, and synthetic test traces. The backend must support classification and corresponding policies. Do not assume every trace backend supports attribute-based retention; sometimes routing to separate tenants/datasets is required.

### 8.2. Storage Budget and Query Budget

Retaining traces longer aids investigating older incidents but raises storage/indexing cost. Traces with heavy attributes make querying/indexing heavier. Track ingest bytes, stored bytes, query latency, dropped spans, and retention expiry.

## 9. Sampling Does Not Replace Metrics

Metrics are typically aggregated and recorded across 100% of metered calls; trace sampling keeps only a subset of traces. If you need accurate request rates/error ratios/latency SLIs, do not compute them directly from sampled traces when sampling is non-uniform or adaptive.

| Need | Appropriate source |
| --- | --- |
| Request rate | Metrics |
| Error ratio/SLO | Metrics |
| p95/p99 latency by endpoint | Metrics histogram |
| Specific request across multiple services | Trace |
| Dependency call sequence | Trace |
| Pool saturation | Metrics |
| Error details and stack context | Logs/traces per policy |

If using trace-derived metrics, understand sampling bias and how the backend extrapolates. Metrics instrumentation should operate independently of trace sampling decisions.

## 10. Cardinality, Privacy, and Payload Budget

Trace sampling reduces trace count, not sensitive data or attribute cardinality inside retained spans. Each sampled span can still carry an oversized payload.

Shrink payloads by allowlisting HTTP headers, avoiding capturing request/response bodies by default, redacting tokens/cookies/query secrets, normalizing SQL and stripping bind values, capping baggage, event counts, and string lengths, avoiding exception messages containing user data, and dropping attributes with no investigative purpose.

### 10.1. Span Count Budget

Set a spans/trace budget per operation class. If an endpoint unexpectedly produces 500 spans due to N+1 queries or fan-out, even 5% sampling can generate huge payloads. Monitor p95/p99 spans per trace and alert on anomalies.

### 10.2. Trace Size Budget

Cap span attribute counts, event counts, and payload bytes if supported by the SDK/backend. When truncating/dropping attributes, preserve essential metadata such as operation, status, service identity, and timing. Record dropped/truncated telemetry so you know if the budget is degrading investigation capability.

## 11. Testing the Sampling Budget

| Test | Goal |
| --- | --- |
| Sampler unit test | Decisions by parent/status/attributes |
| Statistical test | Sampled ratio matches expectations over a large sample |
| Distributed propagation test | Services preserve the same trace decision |
| Tail sampling test | Error/slow traces are retained |
| Late span test | Decision wait handles late-arriving spans |
| Collector load test | Memory/queue/throughput under peak |
| Backend ingest test | Stays within ingest budget |
| Privacy test | Sensitive attributes are not exported |
| Failure test | Collector/backend outages yield expected queue/drop behavior |

### 11.1. Testing Head Sampling

Generate a sufficiently large batch of traces with deterministic trace IDs or sampler test hooks. Verify the parent sampled decision propagates through child spans. For probability samplers, actual ratios fluctuate; use appropriate confidence intervals rather than asserting exact numbers on small samples.

### 11.2. Testing Tail Sampling

Send traces with error status, duration above threshold, normal success, and critical operations. Verify the policy retains the right classes and drops the rest. Verify all spans of a Trace ID are exported together, including spans arriving late within the decision window.

### 11.3. Load Testing the Collector

Generate simulated peak traffic with spans/trace and attribute sizes close to production. Monitor memory, CPU, queue length, refused spans, exporter failures, and tail decision latency. Test a Collector restart to see whether buffered traces are lost.

## 12. Troubleshooting the Sampling Budget

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Backend ingest exceeds budget | RPS/spans/trace/size increased | Recalculate volume, adaptive/head sampling, and payload limits |
| Error traces missing | Head sampler dropped before outcome was known | Tail sampling or error-aware strategy |
| Traces show only some services | Inconsistent sampling decision or lost propagation | Parent-based sampling and context tests |
| Tail sampler drops spans | Short decision wait or misrouting | Increase wait with evidence, Trace-ID routing |
| Collector OOM | Oversized tail buffers/queues | Memory limiter, capacity, and queue budget |
| Exporter queue full | Backend slow or outage | Scale/fix backend, bounded queue, and alerts |
| Abnormal trace size | N+1/fan-out/large events/attributes | Span count/size budget and instrumentation review |
| Oscillating sampling rate | Adaptive policy lacks smoothing | Rate limits, hysteresis, and observability |
| Skewed SLI metrics | Using sampled traces as count source | Use independent metrics recording |
| Trace storage grows despite stable sample rate | Attribute size or spans/trace grew | Track bytes/span and spans/trace |
| Collector replicas have partial traces | Broken trace affinity | Route by Trace ID to tail-sampling tier |
| Unable to find older traces | Short retention or wrong tenant | Check retention, routing, and policy |

### 12.1. Investigation Workflow

1. Measure RPS and traces created.
2. Measure p50/p95/p99 spans/trace and serialized bytes/span.
3. Compare sampling decisions at ingress, services, and Collector.
4. Check propagation headers and parent-based behavior.
5. Inspect Collector memory, queues, refused/dropped spans, and exporter errors.
6. Check backend ingest/storage/query capacity.
7. Verify retention policies and trace routing.
8. Cross-check SLI metrics independently of trace sampling.

## 13. Production Checklist

| Criterion | Evidence |
| --- | --- |
| Volume model grounded in real data | RPS, spans/trace, bytes/span |
| Peak budget calculated | Sustained peak and bursts |
| Sampling strategy documented | Head/tail/parent/adaptive |
| Error/slow trace policy | Test cases proving retention |
| Consistent distributed decisions | Parent context propagation |
| Tail sampling trace affinity | Trace ID routing |
| Collector memory/queue budget | Load tests and alerts |
| Backend ingest/storage budget | Bytes/day, retention, replication |
| Metrics independent of sampling | SLIs not computed from sampled traces |
| Payload/cardinality bounded | Attributes/events/baggage allowlist |
| Pre-export privacy | Redaction tests |
| Dropped spans observed | Collector/exporter metrics |
| Controlled policy changes | Versioned config and rollout |
| Clear failure behavior | Backend outage/Collector restart tests |

## 14. Lab Exercise: Building a Trace Sampling Budget for order-service

**Scenario:** `order-service` receives 1,500 requests/second at peak, averaging 15 spans per trace, p95 of 35 spans, and an average serialized span size of 1 KB. The backend has a limited ingest budget; operations wants to keep error traces and slow traces while still retaining a baseline of successful traces.

**Tasks:**
1. Calculate spans/second and bytes/second at 10% head sampling.
2. Estimate daily payload before compression/replication.
3. Measure p50/p95/p99 spans/trace with a workload test.
4. Choose parent-based head sampling or tail sampling and explain the trade-off.
5. Design a policy prioritizing errors, high latency, and critical operations.
6. If using tail sampling, configure Trace-ID routing and decision wait.
7. Size Collector in-flight trace memory and exporter queue budget.
8. Set limits for span attributes, events, baggage, and SQL/HTTP capture.
9. Verify SLI metrics remain complete when trace sampling changes.
10. Load test peak/bursts and monitor refused/dropped spans.
11. Simulate a Collector/backend outage and verify queue/backpressure.
12. Write a runbook for adjusting sampling when traffic or backend capacity changes.

**Expected deliverables:** volume model, justified sampling policy, Collector/backend budget, test evidence, privacy limits, and runbook.

## 15. Key Takeaways

A trace sampling budget must be calculated from request rate, spans per trace, and bytes per span, plus Collector, network, backend indexing, replication, and retention overhead. Head sampling cuts load early but cannot prioritize errors occurring after the decision; tail sampling can keep errors/slow traces but requires buffers, memory, decision wait, and Trace-ID routing. Combining head and tail sampling requires understanding that the tail sampler only decides over spans that reach it.

Sampling does not replace metrics: request rate, error ratio, and SLOs should be measured via independent metrics recording. Monitor dropped/refused spans, Collector queues, bytes/span, and spans/trace to tell when the budget is exceeded. Shrink payloads with pre-export allowlists/redaction, cap baggage, and avoid dynamic identifiers. Test policies across services and under peak load; adjust sampling with versioning, guardrails, and runbooks.

**References:**
- [OpenTelemetry — Sampling](https://opentelemetry.io/docs/concepts/sampling/)
- [OpenTelemetry — Trace SDK Sampling](https://opentelemetry.io/docs/specs/otel/trace/sdk/#sampling)
- [OpenTelemetry Collector — Tail Sampling Processor](https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/main/processor/tailsamplingprocessor)
- [OpenTelemetry Collector — Memory Limiter Processor](https://github.com/open-telemetry/opentelemetry-collector/tree/main/processor/memorylimiterprocessor)
- [OpenTelemetry Collector — Load Balancing Exporter](https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/main/exporter/loadbalancingexporter)
- [Spring Boot — Tracing](https://docs.spring.io/spring-boot/reference/actuator/tracing.html)
- [Micrometer Tracing — Reference](https://docs.micrometer.io/tracing/reference/)
