# Sampling for Errors in Distributed Tracing with Spring Boot

In production, a service can handle tens of thousands of requests per minute. Recording all spans for every request forces the tracing backend to ingest massive data volumes, consuming CPU, memory, bandwidth, and storage costs. Conversely, sampling too aggressively can leave a rare error or abnormally high-latency request without any trace for investigation. **Sampling for errors** is the practice of designing a trace collection policy so important cases like errors, timeouts, or high latency have a high likelihood of being retained while keeping costs under control.

In the **SPRING_BOOT_OBSERVABILITY** module, sampling is part of setting up observability for Spring Boot using Micrometer Observation, metrics, logs, and distributed tracing. This lesson belongs to the **Sampling** chapter and focuses on **Sampling for errors**: distinguishing head-based and tail-based sampling, understanding the limits of probabilistic sampling, configuring Spring Boot/Micrometer Tracing, setting up the OpenTelemetry Collector, controlling context propagation, cardinality, exporters, and correlating metrics–logs–traces during incident investigations.

## Learning Objectives

After this lesson, you will be able to:

1. Explain why sampling is needed and the trade-off between investigative visibility and telemetry cost.
2. Distinguish head-based sampling from tail-based sampling, knowing when each makes its decision.
3. Explain why a probabilistic head sampler cannot know whether a request will fail at the end of processing.
4. Configure sampling probability in Spring Boot Micrometer Tracing for development and production environments.
5. Build a Collector tail-sampling policy to keep traces with an error status or high latency.
6. Understand parent-based sampling, propagation of the sampled flag, and trace-aware span routing requirements for tail sampling.
7. Avoid deriving error rates or SLOs from a sampled set of traces.
8. Test and operate sampling alongside exporters, logs, metrics, baggage, and security policies.

## 1. Why Is Sampling Needed?

An instrumented request can generate many spans: HTTP server, business Observations, HTTP client, database, and message producer/consumer. At thousands of requests per second, the number of generated spans can vastly exceed the request count. Storing 100% of traces causes ingest and retention costs to grow with traffic and instrumentation granularity.

**Sampling** selects which portion of tracing data is recorded or exported. A good policy balances:

- **Diagnostic value:** prioritizing failed requests, timeouts, high latency, and critical flows.
- **Cost:** capping span counts, queue sizes, bandwidth, and retention duration.
- **Representativeness:** still keeping a sample of normal traffic to compare against errors.
- **Trace completeness:** striving to retain related spans within the same trace.
- **Decision latency:** choosing early sampling versus waiting to observe final outcomes.

### 1.1. Example of Impact

Suppose `order-service` handles 100,000 requests in one hour. Out of those, 200 requests fail, corresponding to 0.2%. With 1% probabilistic sampling at the start of the trace, the expected number of retained error traces is only around 2; the chance of missing the entire error group remains substantial.

With independent sampling probability `p`, each trace has probability `1-p` of being dropped. If there are `n` independent error traces, the probability of **retaining zero error traces** is:

\[
P(\text{retaining zero error traces})=(1-p)^n
\]

For example, with 1% sampling and only 10 error traces:

\[
P=(1-0.01)^{10}\approx 90.4\%
\]

This is a simple probability example assuming independent decisions and one draw per trace. It illustrates that low sampling can wipe out all trace evidence of a rare error.

### 1.2. Sampling Is Not Request Rate Limiting

Sampling only decides which telemetry data is recorded/retained. It **must never be used to drop business requests**, does not reduce database call counts, and does not replace an API rate limiter. Requests still execute per application logic; business/HTTP metrics can continue recording every request even when only a subset of traces is stored.

## 2. Two Core Strategies: Head-Based and Tail-Based

The most important difference is **when the sampling decision is made**:

| Characteristic | Head-based sampling | Tail-based sampling |
| --- | --- | --- |
| Decision timing | When the trace/span starts or is initialized | After the Collector receives enough of the trace to evaluate |
| Available information | Context and metadata present at start time | Can observe status, errors, duration, and attributes appearing later |
| Can prioritize end-of-request errors? | No, if the error only arises after the decision | Yes, if the complete trace is sent to the sampler |
| Cost at the application | Lower, can skip spans early | Application must still create and send spans requiring evaluation |
| Infrastructure | Sampler inside the tracing SDK | Collector/pipeline with buffers, policies, and capacity |
| Complexity | Relatively simple | Higher; requires routing, memory, and wait windows |
| Use cases | Probabilistic sampling, high traffic, early decisions | Keeping errors, high latency, final status, or late attributes |

~~~mermaid
flowchart TD
    Request["Request starts"] --> Head{"Head sampler<br/>decides immediately"}
    Head -- "Drop" --> HeadDrop["Do not record dropped spans"]
    Head -- "Record" --> HeadTrace["Record spans in SDK"]
    HeadTrace --> HeadExport["Exporter sends spans"]
    HeadExport --> BackendA["Trace backend"]
    Request --> TailRecord["SDK records spans per collection policy"]
    TailRecord --> TailExport["Exporter sends spans"]
    TailExport --> Buffer["Collector buffers by trace ID"]
    Buffer --> Decide{"Enough time/data?"}
    Decide -- "Not yet" --> Buffer
    Decide -- "Yes" --> Policy{"Policy: error / latency / sample"}
    Policy -- "Keep" --> Keep["Export trace"]
    Policy -- "Drop" --> Drop["Drop trace"]
    Keep --> BackendB["Trace backend"]
~~~

In the tail sampling diagram, spans must be sent to the Collector for the Collector to decide. If the SDK head sampler already dropped the trace before export, the tail sampler cannot recover that data.

## 3. Head-Based Sampling: Deciding at the Start of the Trace

**Head-based sampling** makes the span-recording decision when the trace is initialized. The simplest approach is probabilistic sampling:

- 100%: record every instrumented trace.
- 10%: expect to record roughly 1 in 10 traces.
- 1%: expect to record roughly 1 in 100 traces.
- 0%: record no traces under that probabilistic policy.

In Spring Boot with Micrometer Tracing, you can configure:

~~~yaml
management:
  tracing:
    sampling:
      probability: 0.10
~~~

This is a 10% probability for the sampling strategy integrated by Spring Boot/Micrometer Tracing. Detailed behavior also depends on the tracing bridge and version. In development environments, `1.0` can be used for easy visibility; production should choose based on traffic, backend capacity, and investigation requirements.

### 3.1. Why Can't a Head Sampler Know About End-of-Request Errors?

Suppose `POST /orders` starts normally, yet 2 seconds later `inventory-service` times out. The head sampler already had to decide when the request began, before the timeout outcome existed.

~~~mermaid
sequenceDiagram
    participant Client
    participant Order as order-service
    participant Sampler
    participant Inventory as inventory-service
    Client->>Order: POST /orders
    Order->>Sampler: Start trace
    Sampler-->>Order: Sample? decide immediately
    Order->>Inventory: HTTP reserve
    Inventory-->>Order: Timeout
    Order-->>Client: HTTP 503
    Note over Sampler: Decision was already made<br/>before knowing the request failed
~~~

If the trace was dropped at the head, the exporter does not have complete spans to send simply because the final response was HTTP 503. This is a fundamental limitation of probabilistic head-based sampling, not a configuration bug.

### 3.2. Parent-Based Sampling and Trace Consistency

In distributed tracing, the sampling decision at the root generally needs to propagate consistently down through services. **Parent-based sampling** uses the decision from the parent/remote parent as the basis for children. W3C Trace Context includes trace flags, where the sampled flag indicates sampling state per protocol rules.

When an HTTP client injects `traceparent` and a receiving service extracts context:

- Child spans can inherit the sampling decision per parent-based policy.
- If a trace is marked not sampled, downstream should not arbitrarily record an isolated branch that causes inconsistency.
- If each service decides sampling independently, the backend may receive incomplete traces or disconnected trace fragments.

Consistent cross-service sampling requires a shared understanding of trace context/propagators and proper sampler configuration. A probability setting on each service must not be treated as an automatic guarantee of a complete span tree if different services enforce conflicting policies.

### 3.3. Advantages and Limitations

**Advantages:**

- Early decision reduces the number of spans recorded and sent.
- Easy to configure, with minimal buffering requirements at the Collector.
- Fits high-traffic systems with a fixed tracing budget.

**Limitations:**

- Cannot prioritize errors that appear only after the request starts.
- A rare error may have no traces at all.
- A fixed probability can retain too much normal traffic while still missing critical error groups.
- Sampled traces should not be used as the source for exact error rates or SLOs.

## 4. Tail-Based Sampling: Keeping Traces After Seeing the Outcome

**Tail-based sampling** defers the decision until the Collector has received the necessary spans of a trace within a waiting window. At that point, policies can inspect status, latency, or attributes and decide to retain the trace.

Example policies:

| Condition | Desired decision |
| --- | --- |
| Has a span with status `ERROR` | Keep trace |
| Has an HTTP 5xx span per convention | Keep trace if policy has a matching condition |
| Trace exceeds 2 seconds | Keep trace |
| Has a specific categorized exception | Keep trace when information is safe and reliable |
| Normal trace | Keep only at a baseline probability, e.g., 1–5% |

Strength: traces can be retained based on final outcomes, including errors occurring after the root span starts. Trade-off: **the Collector must receive, buffer, and process spans before deciding**, requiring appropriate resources and routing.

### 4.1. Tail Sampling Needs the Complete Trace

Suppose a trace contains spans from `order-service`, `inventory-service`, and `payment-service`. If spans belonging to the same trace are sent to different tail-sampling Collector instances, each instance only sees part of the trace and can make wrong or inconsistent decisions.

Therefore, deploying tail sampling requires a **trace-aware routing** mechanism so spans with the same trace ID reach the same tail-sampling decision point, or an explicit gateway/agent architecture designed to guarantee that. Standard round-robin load balancers do not automatically send spans of the same trace to the same Collector.

### 4.2. Decision Wait and Buffering

A tail sampler typically waits for a `decision_wait` duration to receive additional spans. If the window is too short, late-arriving spans may be excluded from the decision. If too long, the number of traces held in memory grows, increasing resource usage and export latency.

Sizing factors:

- New traces per second.
- Average spans per trace.
- Average size of spans/attributes/events.
- Decision wait duration.
- Maximum traces/buffer capacity and processing throughput.
- Delay or out-of-order arrival across services.

Tail sampling requires monitoring dropped traces, late spans, buffer utilization, memory pressure, and keep/drop decisions. Never configure policies and simply assume the Collector has enough capacity for production peaks.

## 5. Configuring Tail Sampling in the OpenTelemetry Collector

Illustrative learning configuration for a Collector receiving OTLP/HTTP, batching, and deciding to keep traces with errors or high latency:

~~~yaml
receivers:
  otlp:
    protocols:
      http:
        endpoint: 0.0.0.0:4318

processors:
  memory_limiter:
    check_interval: 1s
    limit_mib: 512
  tail_sampling:
    decision_wait: 10s
    num_traces: 50000
    expected_new_traces_per_sec: 1000
    policies:
      - name: keep-errors
        type: status_code
        status_code:
          status_codes: [ERROR]
      - name: keep-slow
        type: latency
        latency:
          threshold_ms: 2000
      - name: baseline-sample
        type: probabilistic
        probabilistic:
          sampling_percentage: 2
  batch:
    timeout: 5s

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

This is an illustrative configuration for a Collector distribution that includes these components. Specific versions may change schema or processor support. In production, check the documentation for your exact version, memory limiter, retries, real exporters, and trace-aware routing.

### 5.1. Meaning of the Policies

- `status_code` retains traces containing an `ERROR` span status per data received by the Collector.
- `latency` retains traces whose duration exceeds the configured threshold.
- `probabilistic` applies a baseline rate to remaining traces to observe normal traffic.

When combining multiple policies, verify combination semantics (keep if any policy matches, or how the specific processor/version evaluates them). The example above illustrates the idea of **prioritizing errors/slowness while keeping a baseline sample**; check Collector version docs to ensure policies compose as expected.

### 5.2. Are Application Errors Marked as ERROR?

A status-based tail sampler can only retain error traces if span status/attributes were recorded properly by instrumentation. If a controller returns HTTP 500 yet the span still has status `UNSET` or `OK` due to how exceptions/responses are handled, the `status_code` policy may miss it.

Therefore:

1. Verify how HTTP server instrumentation maps status codes/exceptions.
2. Inspect actual spans in the Collector debug/test exporter.
3. Ensure business errors are recorded on span status/events using appropriate semantics.
4. When keeping HTTP 5xx is required, consider adding a policy on span attributes/HTTP status if the component supports it and the attribute is actually present.

Do not assume every error sets status `ERROR`. A request with an error handled into a fallback 200 may also need business-level tagging, provided the policy is explicitly designed.

### 5.3. A Tail Sampler Cannot Keep Spans That Never Reached the Collector

If a service lacks an exporter, the SDK drops spans before sending, the network fails, or a branch is blocked, the Collector cannot evaluate those spans. Tail sampling is a decision over **received data**, not a system-wide trace recovery tool.

## 6. Combining Head and Tail Sampling

A common deployment lets the SDK send sufficient data to the Collector within controlled bounds, then lets the tail sampler prioritize error/slow traces and sample normal ones. However, if the SDK's head sampler already dropped most traces before export, the tail sampler can only decide on the remaining subset.

| Architecture | Advantage | Limitation |
| --- | --- | --- |
| 10% head sampling, no tail | Simple, reduces data early | Only ~10% of eligible traces; errors can be dropped |
| 100% head sampling + tail sampling | Collector has full visibility into errors/slowness | Increases network, Collector buffers, and CPU |
| Head sampling > 0% + tail sampling | Trims some data before Collector | Cannot recover traces dropped at the head |
| Tail sampling only while upstream component drops spans | No benefit if critical spans aren't sent | Requires clear SDK sampler/recording and routing design |

Some deployments use a head sampler that forwards most traces for tail decisions, though that can generate substantial cost right at the application and network. Measure throughput and memory before rolling out system-wide.

### 6.1. Setting Policies by Business Priority

Not all errors carry equal investigative value. You can prioritize:

1. **Critical errors:** exceptions or `ERROR` status on payment/order flows.
2. **High latency:** requests exceeding service thresholds or dependency timeouts.
3. **Critical flows:** key routes or operations identified by stable attributes.
4. **Normal baseline:** a small ratio for comparison against error traces.

Do not put emails, user IDs, or payloads into policy attributes. Use route templates, service names, operation names, and bounded values.

## 7. Spring Boot Sampling and Trace Context Propagation

Spring Boot with Micrometer Tracing configures sampling probability via:

~~~yaml
management:
  tracing:
    sampling:
      probability: 0.10
~~~

This is an example of head-based sampling probability. For tail sampling in the Collector, Spring Boot does not replace the Collector processor. Both components must be configured and monitored separately.

### 7.1. W3C `traceparent` and the Sampled Flag

An illustrative header:

~~~http
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
~~~

In this header, the flags byte has the sampled bit enabled in the example. The remote service uses extracted context to continue the trace per its propagator/sampler. With a parent-based policy, the sampling decision is typically inherited from the remote parent.

**Baggage and the sampled flag serve different roles:** baggage carries metadata; trace flags carry tracing context state. Do not use baggage to decide whether a service records spans or grants authorization.

### 7.2. When Downstream Fails After the Root Was Head-Dropped

If the root trace was dropped by the head sampler and the parent-based sampler propagates the non-recording decision downstream, subsequent services cannot spontaneously construct a full trace for the tail sampler to retain the error. An independent sampler downstream might record isolated spans, but the trace will lack root/parent spans and produce an incomplete tree.

That is why tail sampling strategies usually require a configuration that collects enough spans before the final decision. Do not mix parent-based head sampling with the expectation that the tail sampler will recover every dropped error.

## 8. Sampling and Statistical Truth: Metrics Remain the Source for SLIs

A sampled set of traces **is not a reliable default denominator** for computing system-wide error rates or SLOs. Sampling can be uneven across services, routes, error statuses, or policies; tail sampling even intentionally retains far more error traces than normal traces.

For example, suppose a tail policy retains 100% of errors and 2% of normal traces. The error ratio inside the trace backend will inevitably be higher than the true error rate in request traffic. That is the intended outcome of an error-prioritizing policy, yet it cannot be used as the error rate.

### 8.1. Using Metrics for Error Rates and Latency Distributions

Example PromQL request error ratio based on an HTTP counter:

~~~promql
sum(rate(http_server_requests_seconds_count{
  service="order-service",
  status=~"5.."
}[5m]))
/
sum(rate(http_server_requests_seconds_count{
  service="order-service"
}[5m]))
~~~

Metric/label names must be checked against the actual Prometheus registry output. Micrometer/Spring Boot may use labels like `application`, `uri`, `status`, or `outcome` depending on version/instrumentation; do not assume a `service` label exists automatically.

With a classic histogram, p95 can be computed as:

~~~promql
histogram_quantile(
  0.95,
  sum by (le) (
    rate(http_server_requests_seconds_bucket{
      uri="/orders"
    }[5m])
  )
)
~~~

Instrumented/aggregated metrics do not depend on whether a request's trace was stored. Therefore, use metrics for request rates, error ratios, p95/p99, and SLOs; use sampled traces to investigate concrete cases.

### 8.2. Exemplars Connect Metrics to Traces

Some registries/backends support **exemplars** to attach a trace reference to a metric sample or histogram bucket. When configured properly, operators can jump from a metrics panel directly to a sample trace. Exemplars do not alter error rate formulas and must never be replaced by putting trace IDs into labels.

## 9. Combining Error Sampling with Logs, Baggage, and Cardinality

When an error trace is retained, span attributes and logs should provide enough context to investigate without leaking PII/secrets.

~~~mermaid
flowchart TD
    Error["Failed / timed-out request"] --> Metrics["Metrics: error rate, p95, request rate"]
    Error --> Trace["Trace sampling policy keeps trace"]
    Trace --> Span["Span status + route + dependency"]
    Error --> Log["Logs: error code + traceId/spanId"]
    Trace --> Backend["Trace backend"]
    Span --> Backend
    Metrics --> Dashboard["Dashboard / alert"]
    Log --> LogBackend["Log backend"]
    Dashboard -. "Select anomalous window" .-> Backend
    LogBackend -. "Look up traceId" .-> Backend
~~~

### 9.1. Baggage Is Not a Condition for Keeping Errors

Baggage can carry information like `orders.channel=web` if the field is verified and approved for propagation. However, do not put `error=true` into baggage just so the tail sampler can spot errors: errors are span/exception states or HTTP outcomes and belong on proper spans/attributes per instrumentation semantics.

Do not trust `priority=high` or `tenant.tier=premium` sent by a client to trigger priority sampling unless authenticated. A malicious client could intentionally force every request to be retained, driving up costs.

### 9.2. Cardinality and Privacy

Do not put `request.id`, `user.id`, emails, tokens, or payloads into metric labels. Span attributes can support deeper investigation, yet still require privacy review, size limits, and access controls. Sampling is not a security mechanism: if sensitive fields are exported, a retained trace can still expose data.

### 9.3. Logs Need Correlation Even When Traces Are Not Kept

A log event can be emitted with `traceId`/`spanId` from the active context, yet the backend has no trace because the sampler dropped it or the exporter failed. Retain logs per their own policy without assuming every trace ID in logs has a matching trace in the backend. Never log raw request headers or full baggage dumps.

## 10. Testing Sampling Layer by Layer

Sampling requires testing SDK decisions, Collector policies, and metrics/logs integrity.

| Test layer | Goal | Evidence |
| --- | --- | --- |
| Sampler unit test | Head sampler rules per input/context | Accurate record/drop decisions |
| Tracing SDK test | Span recording and parent-based behavior | Trace IDs, sampling flags, exported spans |
| Collector policy test | Status/latency/probabilistic policies | Error traces kept, baseline traces sampled |
| Pipeline integration | SDK → Collector → backend | Real trace queryable by ID |
| Metrics regression | Error rate/p95 independent of sampling | HTTP metrics remain complete per instrumentation |
| Load/capacity test | Collector queue/memory/throughput | No out-of-budget drops and reasonable latency |

### 10.1. Testing Spring Boot Sampling Probability

In test environments, you can configure sampling `1.0` to observe all traces through SDK/Collector. Then configure a lower probability and send enough requests to observe a rate near expectations. Do not test with a handful of requests and expect exact 10% retention; probabilistic sampling fluctuates.

### 10.2. Testing Tail Sampling Policies

With a Collector running in tests:

1. Generate a trace with span status `ERROR`.
2. Generate a normal trace below the latency threshold.
3. Generate a normal trace exceeding the latency threshold.
4. Route all spans of each trace to the same tail-sampling instance.
5. Wait past `decision_wait` and inspect the trace backend/test exporter.
6. Confirm error and slow traces are kept while normal traces are kept only at baseline probability.
7. Try sending a late span after the decision window to understand late/drop behavior and metrics for your version.

Do not hardcode expectations that normal traces are always dropped when baseline sampling is non-zero. Use seeded/deterministic test setups or isolated policies when non-random assertions are needed.

### 10.3. Verifying Cross-Service Completeness

Trigger a request from `order-service` to `inventory-service`. Verify matching trace IDs, parent-child links, and that spans from both services arrive at the same tail-sampler. If traces spread across multiple Collector instances, tests must verify trace-ID routing rather than checking only a single successful export.

### 10.4. Testing Metrics Independence

Send a known batch of succeeding and failing requests, confirming HTTP Counters/Timers record everything per instrumentation. Then change sampling probability and verify **request metrics do not shrink to the ratio of sampled traces**. This is a critical regression test whenever operations teams change sampling policies.

## 11. Troubleshooting Sampling for Errors

| Symptom | Possible cause | How to check |
| --- | --- | --- |
| Rare errors lack traces | Head sampling dropped traces at the start | Increase targeted sampling or use tail sampling |
| Trace has root but lacks children | Downstream instrumentation/exporter/propagation failure | Check W3C context and each service's export |
| Trace backend shows very high error ratio | Tail policy prioritizes errors | Do not use trace set to compute error rates |
| Collector does not keep error trace | Span status is not `ERROR` or attribute policy mismatches | Inspect raw span data and exception/status mapping |
| Error trace lost before Collector | Head sampler or SDK not recording | Check SDK sampler/recording config |
| Inconsistent tail decisions | Spans of same trace hit different Collector instances | Trace-aware routing/load balancing |
| Late-arriving spans dropped | `decision_wait` too short or inter-service latency | Measure span arrival delay, adjust wait/capacity |
| Collector OOM/drops rising | `num_traces`/buffers/attributes too large | Sizing, memory limiter, scaling, and sampling |
| Too many normal traces kept | High baseline probability or broad OR policy | Review policy composition and expected volume |
| Request metrics missing after sampling change | Metrics instrumentation bug or wrong query | Compare MeterRegistry/Prometheus independently |
| Log has trace ID yet UI has no trace | Trace dropped or exporter/backend failure | Separate sampling decision from export pipeline |
| Error trace kept but lacks useful details | Missing attributes or overly aggressive sanitization | Add bounded, safe, necessary metadata |

### 11.1. Investigation Order

1. **Confirm error via metrics:** HTTP error count, request rate, latency, and route.
2. **Check sampling policy:** head probability, parent-based behavior, and tail rules.
3. **Confirm span recording:** span status, attributes, and trace context at SDK/Collector.
4. **Check export:** OTLP exporter errors, queues, Collector receiver, and pipeline.
5. **Check trace-aware routing:** do all spans of the trace reach the same tail sampler?
6. **Check decision window/capacity:** late spans, memory pressure, and dropped traces.
7. **Open correlated logs:** by trace ID if the trace was stored; otherwise use log/error codes and metrics to investigate.

Do not assume the sampler is broken simply because a trace does not appear immediately; batching and decision wait introduce delay. Conversely, waiting forever will not fix a wrong exporter endpoint or a disconnected Collector pipeline.

## 12. Production Checklist and Budget Operations

| Criterion | Required evidence |
| --- | --- |
| Clear sampling goals | Know whether keeping rare errors, high latency, or baseline traffic |
| Head/tail strategy fits needs | Understand when decisions happen |
| Consistent parent-based behavior | Compatible W3C trace context and samplers across services |
| Errors marked properly on spans | Verified span status/HTTP attributes |
| Trace-ID-based tail routing | Spans of the same trace arrive at the same decision point |
| Tail buffer sized properly | `decision_wait`, `num_traces`, memory, and peak traffic justified |
| Representative baseline sampling | Sample of normal traffic available for comparison |
| Exporter/Collector monitored | Errors, retries, dropped spans, late spans, and receiver health |
| Metrics SLIs independent of trace sampling | Error rate, request rate, and latency come from proper metrics |
| No PII/secrets in telemetry | Privacy review, allowlists, and redaction |
| Cardinality under control | No dynamic IDs in metric labels |
| Planned graceful shutdown | Processors have a window to flush within limits |
| Failure/slow/baseline cases tested | Tests confirm policies retain intended traces |
| Runbook for missing traces | Team distinguishes sampling, propagation, exporter, and backend |

### 12.1. Estimating Tail Sampler Capacity

A rough estimate:

\[
\text{buffer size} \approx
\text{new traces/sec} \times \text{decision wait (sec)}
\]

For example, 800 new traces/second with a 10-second decision wait means roughly **8,000 traces awaiting decisions** at any given moment, before accounting for spans per trace, traffic spikes, retries, late arrivals, and data structure overhead. At an average of 12 spans/trace, the Collector must also hold roughly 96,000 spans for those traces.

This is only a preliminary estimate. Real sizing must factor in span size, attributes/events, concurrency, peak rates, memory overhead, and Collector version specifics. Set `num_traces` with headroom; never set it equal to the average product and treat that as safe.

### 12.2. Sampling Policy Changes Are Operational Changes

When raising sampling rates or changing error retention policies:

- Monitor ingest rate, backend cost, and retention.
- Measure exporter queues/dropped spans and Collector memory.
- Compare retained trace ratios across policies.
- Verify metrics SLI semantics remain unchanged.
- Record policy change timestamps to explain trace volume shifts.

Do not compare "error trace counts" across two weeks without accounting for sampling policy changes.

## 13. Lab Exercise: Keeping Error and High-Latency Traces

**Context:** `order-service` handles `POST /orders` and calls `inventory-service`. Normal traffic is high while timeouts are rare. The team needs to keep traces for errors and requests slower than 2 seconds, plus a small sample of normal traffic.

**Tasks:**

1. Configure Spring Boot Actuator, Micrometer Tracing, and the OpenTelemetry bridge; verify HTTP server/client instrumentation.
2. Enable 100% head sampling in a test environment to inspect the baseline trace tree.
3. Set up a Collector OTLP receiver and `tail_sampling` processor with policies for status `ERROR`, latency `2,000 ms`, and baseline probability `2%`.
4. Ensure spans of the same trace route to the same tail-sampling instance.
5. Send 10 fast successful requests, 2 requests slower than 2 seconds, and 1 error request; wait past the decision window.
6. Check whether the Collector/export backend kept the error and slow traces; confirm baseline can keep some normal traces.
7. Inspect actual span status/HTTP attributes; if an error trace failed to match, identify how instrumentation marks errors.
8. Lower SDK head sampling to 10%, observing that the tail sampler cannot retain traces dropped by the SDK.
9. Send a batch of requests with known success/error counts; verify the Prometheus error ratio still reflects all requests per instrumentation.
10. Watch memory, queues, late spans, and exporter failures as test traffic increases.
11. Write a runbook for missing error traces: distinguishing head drops, tail policy mismatches, routing, exporter, and backend.

**Expected deliverables:** Spring Boot and Collector configurations, error/slow traces retained per policy in the test environment, metrics SLIs independent of sampled traces, and a brief report on cost, limitations, and scenarios where traces can still be lost.

## 14. Key Takeaways

**Head-based sampling** decides early when the trace starts; it is simple and trims data before export, yet cannot know if a request will fail at the end. **Tail-based sampling** waits for the Collector to receive spans and can prioritize errors or high latency, but requires buffers, decision windows, capacity, and trace-ID routing. Once the SDK drops a trace, the Collector cannot recover that data.

To capture useful traces for incidents, verify span status/attributes, parent-based propagation, sampling policies, exporters, and the Collector pipeline as an end-to-end chain. **Metrics remain the primary source for request rates, error ratios, latency distributions, and SLOs**; sampled traces help investigate individual cases, and logs supply events and correlation. Protecting data, controlling cardinality, and monitoring the telemetry pipeline itself are prerequisites for production operations.

**References:**

- [Spring Boot — Tracing](https://docs.spring.io/spring-boot/reference/actuator/tracing.html)
- [Spring Boot — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html)
- [Micrometer Tracing — Reference](https://docs.micrometer.io/tracing/reference/)
- [OpenTelemetry — Sampling](https://opentelemetry.io/docs/concepts/sampling/)
- [OpenTelemetry Collector — Tail Sampling Processor](https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/main/processor/tailsamplingprocessor)
- [OpenTelemetry Collector — Configuration](https://opentelemetry.io/docs/collector/configuration/)
- [W3C — Trace Context](https://www.w3.org/TR/trace-context/)
