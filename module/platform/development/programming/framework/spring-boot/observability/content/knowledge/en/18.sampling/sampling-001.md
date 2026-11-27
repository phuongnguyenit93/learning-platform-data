# What Is Trace Sampling in Spring Boot Observability?

In the **Sampling** chapter of the **SPRING_BOOT_OBSERVABILITY** module, *trace sampling* is the technique of selecting a subset of traces to record and export, rather than storing every trace for every request. Sampling helps control span volume, bandwidth, CPU, buffer memory, and storage costs, while still retaining enough data to investigate errors, latency, and application behavior.

A Spring Boot service can receive tens of thousands of requests per minute. If each request creates multiple spans across the HTTP server, business observations, HTTP client, database, and messaging, the total number of spans grows rapidly with traffic and call graph depth. Sampling defines a policy for selecting traces; it is **not** a way to disable metrics, not a mechanism for deleting logs, and does not guarantee that every error trace will be kept.

This lesson belongs to the **SPRING_BOOT_OBSERVABILITY** module and focuses on Micrometer Observation, metrics, logs, and distributed tracing: understanding traces/spans, sampling decisions, head-based and tail-based sampling, parent-based sampling, probability configuration in Spring Boot, propagation, limitations, and how to verify results in a real environment.

## 1. What Problem Does Trace Sampling Solve?

A trace can contain many spans. For example, a checkout request passes through the HTTP server, a business step, two database calls, and an HTTP client call to a payment service:

```text
POST /checkout
  └─ order.confirm
       ├─ inventory.reserve
       │    └─ database query
       └─ payment.authorize
            └─ HTTP POST payment-provider
```

If one request creates six spans, 10,000 requests can generate around 60,000 spans in the corresponding window (excluding retries, messaging, and spans from other libraries). Under high traffic, keeping every trace can increase:

- Network export volume and pressure on the collector.
- CPU usage for creating, processing, serializing, and sending spans.
- Queue/buffer memory in the SDK, exporter, and collector.
- Ingest, indexing, query, and retention costs in the tracing backend.

Sampling lets you select representative traces for observation. For example, 10% probabilistic sampling can significantly reduce the volume of exported spans compared to recording everything, at the trade-off that some individual requests will not have a complete trace in the backend.

**Sampling is a trade-off between cost and observability.** A rate that is too low can miss rare incidents; a rate that is too high can exceed the budget. The policy needs to consider traffic volume, service criticality, investigation needs, SLOs, backend capacity, and data sensitivity.

## 2. Trace, Span, and Sampling Decision

A **Trace** represents a distributed processing journey. A **Span** represents a unit of work within that journey. Spans share a Trace ID and have parent-child relationships or links. Sampling is typically decided at the trace level; spans within the same trace should be handled according to a consistent policy so the trace does not randomly miss important segments.

| Concept | Meaning |
| --- | --- |
| Trace ID | Identifier of a trace across multiple services |
| Span ID | Identifier of a specific span |
| Parent span | The span that provides the parent context for the next span |
| Sampling decision | Choosing whether to record/export a trace according to a policy |
| Recording span | A span being recorded by the SDK that can be processed/exported |
| Non-recording span/context | Context may continue propagating, but the span is not recorded as a recording span |
| Export | Sending recorded span data to the collector/backend |

**Creating a context is not the same as exporting a span.** A request can have a valid Trace ID so downstream services continue propagating it, yet the sampling decision can cause spans not to be recorded or exported. Similarly, a recorded span can still fail to reach the backend if the exporter, network, collector, or backend encounters an error.

## 3. What Is Head-Based Sampling?

**Head-based sampling** decides whether to record a trace near the start of the trace, usually when the root span is created. This decision is typically based on information already available at the start of the request, such as Trace ID, parent context, service, or initial attributes.

```text
Request starts
      |
      v
Tracer creates root span/context
      |
      v
Head sampler decides
      |
      +---- sampled ----> record spans per policy
      |                         |
      |                         v
      |                      processor/exporter
      |
      +---- not sampled --> context may continue propagation
                            but spans are not exported for the trace
```

Advantages of head sampling:

- Early decision, easy to deploy per service.
- Reduces most recording/export work right from the start.
- Requires little need to hold the entire trace in memory while waiting for a final decision.
- Easy to apply probabilistic or parent-based policies in the SDK.

Limitations:

- The decision happens before the final outcome of the request is known.
- A request selected at the start may succeed normally; a dropped request may end with a rare error or high latency.
- If services do not respect the parent sampling context, a distributed trace can split: one service records spans while another does not.

Head sampling is suitable as a baseline policy when traffic is high and cost needs to be reduced at the source. However, it cannot know for certain at selection time whether a request will fail in the future.

## 4. Parent-Based Sampling and the Sampled Flag

In distributed tracing, the sampling decision can be propagated alongside the trace context. With W3C Trace Context, the `traceparent` header contains a flags field:

```text
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
             |  |                                |                |
             |  Trace ID                         Parent Span ID   flags
             version
```

In the version `00` example, the lowest bit of flags represents the sampled flag: `01` indicates the sampled bit is set; `00` indicates this bit is not set. Do not arbitrarily interpret other bits or use flags as an authorization mechanism.

A **parent-based sampler** respects the sampling decision from the parent context according to configured branches for sampled or not-sampled local/remote parents. As a result, if service A selects a trace, service B can continue recording child spans of the same trace; if the parent was dropped, downstream services also typically follow that decision.

Example in the OpenTelemetry SDK:

```java
Sampler sampler = Sampler.parentBased(
        Sampler.traceIdRatioBased(0.10));
```

General meaning:

- For a new trace with no parent, the probabilistic sampler decides at roughly 10%.
- For a trace with a parent, the parent-based sampler typically follows the parent's sampled decision in the default branches.
- You can customize samplers for remote/local parent sampled/not-sampled cases if needed, but you must understand the impact on trace consistency.

A downstream service should not unilaterally flip a not-sampled trace to sampled if the goal is to keep a uniform decision across the system. Conversely, some systems with a decision-upgrade strategy at the collector layer (tail sampling) must retain enough data from the start via a dedicated mechanism; this cannot be achieved merely by ignoring the parent flag in individual services.

## 5. Probabilistic Sampling in Spring Boot with Micrometer Tracing

On Spring Boot versions that support Micrometer Tracing auto-configuration, you can configure the sampling rate in `application.yml`:

```yaml
spring:
  application:
    name: orders-service

management:
  tracing:
    sampling:
      probability: 0.10
```

The value `0.10` is an example: 10% probabilistic sampling for new traces depending on the active implementation/policy. It does not mean the system will keep exactly one out of every ten requests in every time window; probabilistic sampling can fluctuate noticeably over small sets of requests.

Some Spring Boot/Micrometer generations use properties under the `management.tracing.sampling.probability` namespace; verify the exact project version and bridge installed. This property controls tracing sampling via auto-configuration—it is **not** the Prometheus metrics scrape rate and does not set log sampling.

If a project configures the OpenTelemetry SDK manually instead of letting Spring Boot own the tracer, the sampler must be configured on the corresponding `SdkTracerProvider`. Avoid configuring one sampler through Spring Boot while also creating an independent `SdkTracerProvider` that the actual instrumentation does not use.

### Initial Rate Choices

| Environment/goal | Example policy | Notes |
| --- | --- | --- |
| Local development | 1.0 (100%) | Convenient for debugging, only use under low load |
| Integration/staging | 0.5 or 1.0 | Depends on backend capacity and test data |
| High-traffic production | 0.01–0.10 | A starting point for experimentation, not a universal rule |
| Critical low-traffic service | May be higher | Balance cost and diagnostic value |

Do not set production rates purely by habit. Measure spans/request, requests/second, ingest cost, and rare incident frequency before choosing.

## 6. How Is Tail-Based Sampling Different?

**Tail-based sampling** defers the decision to keep or drop a trace until the collector or a downstream component has received all (or sufficiently many) spans of the trace. Therefore, the policy can rely on observed post-processing outcomes:

- Keep traces with an error status.
- Keep traces whose latency exceeds a threshold.
- Keep traces from important services/routes.
- Sample a small percentage of normal successful traces.

```text
Application services
     |
     +--> send recording spans (via exporter)
                  |
                  v
             OTel Collector
                  |
                  v
          tail-sampling processor
                  |
          +-------+--------+
          |                |
      error/slow         normal
       keep              sample
          |                |
          +-------+--------+
                  |
                  v
          tracing backend
```

Advantage: it can prioritize error/slow traces without knowing the outcome at the start of the request. Limitations:

1. **The collector must receive the necessary spans** before making a decision. If the SDK head-samples out a trace before export, the tail sampler cannot recover spans that were never sent.
2. Spans sharing the same Trace ID must be routed to the same sampling decision point; fragmentation or missing spans prevents the policy from seeing the full trace.
3. The collector must hold trace state in memory during a waiting window; high traffic and long-running traces can create memory/queue pressure.
4. Decision wait, expected trace duration, concurrent trace count, and overflow strategies must be configured.
5. A "keep all errors" policy can only keep errors that reach the collector and are recognizable via status/attributes; not every business error automatically produces an `ERROR` span status.

Tail sampling is commonly performed at the OpenTelemetry Collector with an appropriate processor. This is a collector-side configuration and is not enabled solely by Spring Boot's `management.tracing.sampling.probability` property.

## 7. Comparing Head-Based and Tail-Based Sampling

| Criterion | Head-based | Tail-based |
| --- | --- | --- |
| Decision timing | Start of the trace | After the collector receives spans |
| Knows whether the trace later errors/is slow? | Usually no | Yes, if spans/status/latency reach the collector |
| Load reduction at the application | Strong, because traces are dropped early | Usually lower; applications still must export data to the collector |
| Collector memory requirement | Lower | Higher due to buffering traces while awaiting a decision |
| Cross-service consistency | Relies on parent-based propagation | Requires grouping spans by Trace ID and centralized decision-making |
| Best suited for | Baseline probabilistic sampling, high-load systems | Prioritizing error/slow traces and outcome-based policies |
| Main limitation | Can miss rare error traces | Consumes collector resources and requires sufficient spans |

The two techniques can be combined: head sampling at a rate greater than 0 but less than 1 to reduce load, followed by tail sampling selecting from the received spans; however, if head sampling is too low, the tail collector can only select from the remaining traces. When the requirement is to keep nearly every error, the ingest path must be designed so errors have the opportunity to reach the collector.

## 8. How Does Sampling Affect Metrics, Logs, and Traces?

Tracing sampling does not mean sampling all telemetry.

| Signal | Typical impact when a trace is sampled out |
| --- | --- |
| Traces | Recording/export spans from that trace are usually not sent to the backend under head sampling |
| Metrics | Micrometer metric handlers can still independently record counters/timers/gauges |
| Logs | The application still writes logs per logging configuration; logs may lack a correlation span or carry a non-recording context depending on the implementation |
| Baggage/propagation | Context may still be propagated; do not assume the sampled flag always causes all context information to disappear |

For example, `http.server.requests` still increments and `payment.authorizations` still records success/error outcomes, yet the trace for a successful request might not be exported due to sampling. That is normal when the metric pipeline operates independently.

Conversely, if an `ObservationPredicate` rejects the entire observation, that observation may produce neither metrics nor spans from the handlers attached to the registry. This is a decision **not to create an observation**, which is different from a tracing sampler that only decides trace recording/export. Do not use a random predicate to simulate sampling because it can drop metrics as well.

### Do Not Put Trace ID into Metric Tags to Compensate for Dropped Traces

Trace ID has nearly a unique value per trace. Adding it to a metric tag makes the number of time series grow with traffic, leading to cardinality explosion. Use low-cardinality dimensions instead, such as:

- `service`, `route` template, `method`, `status`.
- `provider`, `region`, or `operation` with a bounded set of values.
- `outcome=success/error/declined` with clear semantics.

Metrics help detect trends; sampled traces help inspect individual transactions deeply; structured logs with correlation help look up details within data policy boundaries.

## 9. Sampling and Context Propagation Across Services

The sampling decision and trace context are propagated across services. With W3C Trace Context, the sampled flag resides in the flags field of `traceparent`; a parent-based sampler can use the parent's decision to keep child span recording consistent.

```text
Client
  |
  v
orders-service
  root/server span: Trace ID=T, sampled=true
  |
  +-- HTTP client span
       inject traceparent (traceId=T, parent span id=C, flags=01)
                 |
                 v
          payment-service
            extract context
            parent-based sampler observes sampled parent
            create child span with Trace ID=T
```

If `orders-service` chooses `sampled=true` but `payment-service` does not respect the parent context or receives a malformed header, the trace may miss downstream spans. If a gateway strips `traceparent`, downstream services may start a new Trace ID. If the parent is not-sampled, child services typically continue the non-recording decision under a parent-based strategy.

For messaging and async execution, corresponding propagation via message headers/executor context is required. A task running on another thread does not automatically have the current span just because the request thread was sampled. Context propagation, sampling, and scoping are three related but distinct responsibilities.

## 10. Limitations and Policy Considerations

Sampling does not exempt you from controlling data and cost:

**Rare error traces:** a 1% probability can miss many errors if an error only occurs a few times. Tail sampling can prioritize errors, but the collector must receive spans and retain enough state.

**Traffic bursts:** the number of selected traces in a short window can exceed expectations. Exporter buffers/queues and collector limits are needed; an average rate does not describe peak load.

**Long traces:** a workflow with hundreds of spans or running for many minutes increases the cost per trace. Sampling by trace count does not directly cap the number of spans inside each trace.

**Backend retention:** keeping 100% of traces for seven days is completely different from keeping 10% of traces for thirty days. Sampling rate, spans/request, ingest volume, and retention together determine cost.

**Security/privacy:** sampling is not redaction. A retained trace can still contain tokens, emails, raw URLs, or sensitive payloads if instrumentation records those fields. Filter data at the source/collector and manage access permissions.

**Statistical accuracy:** probabilistic sampling is suitable for trend analysis when you clearly understand the policy and dataset. Do not treat the count of sampled traces as actual total requests without knowing the sample ratio and how parent/remote sampling is handled. Critical SLIs should typically rely on metrics with appropriate coverage, not solely on stored trace counts.

## 11. Investigation Example: Rare Errors That Need Traces Retained

Suppose `orders-service` receives 20,000 requests/minute. Head-based probabilistic sampling at 5% can send an average of roughly 1,000 traces/minute if every request starts a new trace and the policy applies independently under simplified assumptions. A payment error occurring 4 times a day might not fall into the selected traces.

**No trace does not mean the error did not happen.** Metrics can still show that `payment.authorize{outcome="error"}` increased; logs can record `error.kind=timeout` and trace correlation if a context is present. The operations team can:

1. Use metrics to identify the time window, provider, and error rate.
2. Use structured logs to identify the error kind and Trace ID if available.
3. Inspect the sampling decision/flags of the related trace.
4. Evaluate tail sampling or dedicated sampling rules for specific services/routes/errors.
5. Ensure errors are represented with appropriate status/attributes so the collector can identify them.
6. Verify whether the collector receives enough spans, holds traces within the decision window, and does not drop them due to overflow.

An illustrative collector policy could be: keep traces with an ERROR span status; keep traces whose duration exceeds a threshold; sample a portion of normal traces. This is **conceptual logic**; processor syntax, policy ordering, decision wait, and fallbacks depend on the OpenTelemetry Collector version and distribution in use—check the documentation of the deployed component.

## 12. Manual SDK Configuration with OpenTelemetry (When the App Owns the SDK)

If you do not rely on Spring Boot auto-configuration to own the tracing provider and instead build the SDK directly, you can set the sampler on `SdkTracerProvider`:

```java
import io.opentelemetry.sdk.trace.SdkTracerProvider;
import io.opentelemetry.sdk.trace.samplers.Sampler;

SdkTracerProvider tracerProvider = SdkTracerProvider.builder()
        .setSampler(
                Sampler.parentBased(
                        Sampler.traceIdRatioBased(0.10)))
        .build();
```

This snippet only illustrates configuring the sampler. A real application also needs `Resource`, `SpanProcessor`, `SpanExporter`, propagators, and lifecycle shutdown. If Spring Boot already creates the provider via a Micrometer Tracing bridge, do not create an independent provider and expect auto-configured instrumentations to automatically switch to it.

Common samplers in the OpenTelemetry SDK include:

| Sampler | Meaning |
| --- | --- |
| `alwaysOn()` | Records every new trace evaluated by this sampler; only suitable for testing or very low load if no other policy exists |
| `alwaysOff()` | Does not record traces evaluated by this sampler |
| `traceIdRatioBased(p)` | Selects by ratio based on the Trace ID |
| `parentBased(root)` | Respects the parent decision; uses `root` for new traces without a parent |

Do not use `alwaysOn()` as the default production configuration when traffic and cost have not been evaluated. Also do not use `alwaysOff()` to work around a broken exporter: it only stops recording spans and does not fix OTLP connectivity.

## 13. Sampling Selection and Verification Workflow

A practical workflow:

1. **Measure baseline:** requests/second, spans/request, bytes/span, trace duration, ingest rate, collector memory, and backend cost.
2. **Define goals:** how much ingest to reduce, which error types must be kept, which routes/services are critical, and retention requirements.
3. **Choose strategy:** probabilistic head-based as baseline; parent-based for consistency; tail-based if decisions need to be made on error/latency after spans arrive.
4. **Configure in the right place:** Spring Boot/Micrometer Tracing SDK for head sampling; collector processor for tail sampling; avoid misapplying sampling to metric/log pipelines.
5. **Verify propagation:** W3C `traceparent`/sampled flag across services, executors, and message consumers.
6. **Verify export:** spans received, dropped spans, queue overflow, retries, collector errors, and backend ingest.
7. **Cross-check signals:** metrics still reflect requests/errors; logs contain sufficient investigation fields; representative traces have complete parent-child trees.
8. **Monitor after changes:** compare ingest volume, retained error traces, trace completeness, and investigation time; adjust policy based on evidence.

### Minimum Verification Matrix

| Scenario | Expected result |
| --- | --- |
| No parent, 100% rate | New trace is recorded if the SDK/exporter works |
| No parent, rate below 1 | Only a fraction of new traces are recorded per the sampler |
| Remote parent sampled=true with parent-based sampler | Child typically continues being sampled per the parent |
| Remote parent sampled=false | Child typically follows the non-sampling decision |
| Trace head-sampled out | Context propagation may still occur; no corresponding spans are exported |
| Trace sampled but exporter fails | Recording decision may be right, but backend lacks the trace |
| Metric handler active, low tracing sample rate | Metrics are still recorded independently |
| Predicate rejects observation | That observation does not emit signals from the corresponding handlers |
| Tail sampler intended to keep errors | Collector must receive the required span/status before the decision |
| Executor does not propagate context | Worker may lose current span/Trace ID even if the original request was sampled |

## 14. Scenario Exercise

A Spring Boot system is configured with:

```yaml
management:
  tracing:
    sampling:
      probability: 0.01
```

After a deployment, metrics record 30 timeout errors on `payment.authorize` within 10 minutes. Logs show Trace IDs for some errors, yet the tracing backend only finds two traces. The team concludes: "metrics and logs are out of sync with tracing, so Micrometer is broken."

**Questions:**

1. Can 1% sampling partially explain why only a few traces are found?
2. Why do metrics and logs still exist when a trace is missing from the backend?
3. What should be verified before raising sampling to 100%?
4. How can error traces be prioritized while keeping costs under control?

**Analysis Hints:**

- 1% sampling can cause most traces not to be recorded/exported. A small sample of 30 errors will not necessarily yield many traces at a 1% probability.
- Metrics have a separate pipeline, and log statements are still emitted according to the logging configuration. Log correlation may carry a Trace ID from the context even when the trace is not exported, depending on the implementation.
- Check the head sampler/parent-based policy, propagation, exporter/collector drops, backend retention, instrumentation, and spans/request before changing the rate.
- If keeping errors is required, consider tail sampling at the collector with error/latency policies; ensure spans are sent to the collector, grouped properly by trace, and have sufficient resources while waiting for decisions. Use metrics to track overall error rates.

### Completion Checklist

| Topic | Can explain/verify |
| --- | --- |
| Distinguish trace and span | Shared Trace ID, distinct Span ID, parent relationship |
| Head-based sampling | Decides near trace start, unaware of final outcome |
| Parent-based sampling | Respects parent's sampled decision per policy |
| Tail-based sampling | Decides after collector receives spans; incurs state and resource cost |
| Spring Boot property | Knows location of `management.tracing.sampling.probability` on supported versions |
| W3C sampled flag | Understands flags in `traceparent`, does not use as auth |
| Metrics/logs | Not dropped by default alongside tracing sampling |
| ObservationPredicate | Distinguishes rejecting the whole observation from trace sampling |
| Cardinality | Does not use Trace ID as a metric tag |
| Exporter/collector | Distinguishes recording decision from data actually ingested |

**Remember:** Trace sampling selects which traces are recorded/exported to balance cost and diagnostic visibility. **Head-based sampling** decides early; **parent-based sampling** keeps decisions consistent across services; **tail-based sampling** can prioritize error/slow traces after the collector receives data, at the cost of extra memory and operations. Spring Boot/Micrometer Tracing sampling does not replace metric collection or logging. For reliable observability, combine broad-coverage metrics, structured logs, representative traces, proper context propagation, and end-to-end verified exporters/collectors.
