# Sampling Probability: Choosing the Trace Collection Rate in Spring Boot

> **Chapter:** Sampling  
> **Lesson:** Sampling probability  
> **Module:** `SPRING_BOOT_OBSERVABILITY` — Setting up observability for Spring Boot using Micrometer Observation, metrics, logs, and distributed tracing. Learn context propagation, tags/cardinality, exporters, sampling, and signal correlation to investigate errors, latency, and application behavior in production environments.

## 1. Why Is Sampling Needed?

A Spring Boot service can receive thousands of requests per second. Each request creates a server span, business spans, HTTP client spans, and database spans. Sending every trace provides full visibility but increases CPU, network, storage capacity, and query costs. Sampling too little, on the other hand, can miss a rare error or a very slow request.

**Sampling probability** is the probability used to decide which traces are recorded and exported to the tracing backend. Spring Boot configuration typically looks like this:

~~~yaml
management:
  tracing:
    sampling:
      probability: 0.1
~~~

A value of `0.1` represents a 10% probability in the corresponding probabilistic sampler. It does not mean that out of every 10 requests, exactly one trace is guaranteed to be kept, nor does it mean metrics only count 10% of requests.

~~~mermaid
flowchart LR
  A["Request / parent context"] --> B["Sampler"]
  B --> C{"Sampling decision"}
  C -->|"sampled"| D["Record spans"]
  C -->|"not sampled"| E["Do not export trace per policy"]
  D --> F["Processor / reporter"]
  F --> G["Exporter"]
  G --> H["Collector / tracing backend"]
~~~

This lesson focuses on probability, head-based and parent-based sampling, Spring Boot configuration, propagation, cost estimation, limitations when trying to retain rare error traces, and testing approaches.

## 2. What Does Sampling Probability Mean?

Suppose the sampler selects each trace independently with probability p. For N eligible traces, the expected number of selected traces is:

\[
E[S] = N \times p
\]

For example, with N=100,000 and p=0.1, the expected number of traces is 10,000. The actual number may be higher or lower.

| Probability | Expected rate | Interpretation |
| ---: | ---: | --- |
| 0.0 | 0% | Do not select new traces under this sampler |
| 0.01 | 1% | On average, about 1 in 100 traces |
| 0.05 | 5% | On average, about 5 in 100 traces |
| 0.1 | 10% | On average, about 10 in 100 traces |
| 0.5 | 50% | On average, about half |
| 1.0 | 100% | Select every eligible trace under the policy |

This is a probability, not an exact per-minute quota. Over a small batch of requests, the number of retained traces can fluctuate noticeably.

### 2.1. Statistical Variance

Under a simple Bernoulli model:

\[
Var(S) = Np(1-p), \quad \sigma=\sqrt{Np(1-p)}
\]

With N=100 and p=0.1, the expected number of traces is 10 and the standard deviation is 3. Observing 6 or 14 traces in a short interval does not prove the sampler is broken. Observe a sufficiently large traffic sample and rule out exporter drops before evaluating the rate.

### 2.2. Trace Sampling Does Not Sample Every Signal

Tracing probability does not automatically reduce Micrometer Counters/Timers, application logs, actual requests processed, or business events in the database. 10,000 requests can still increment a Counter 10,000 times even if only a fraction of traces are exported. Each signal has its own pipeline and retention policy.

## 3. Head-Based Sampling

**Head-based sampling** makes the decision when the trace starts, usually at the root span or upon receiving context from upstream. The decision can be propagated to other services via the trace context and sampled flag.

~~~mermaid
sequenceDiagram
  participant Client
  participant Gateway
  participant Order as order-service
  participant Inventory as inventory-service
  Client->>Gateway: Request
  Note over Gateway: Root sampler decides
  Gateway->>Order: Request + trace context
  Order->>Inventory: Request + trace context
  Inventory-->>Order: Response
  Order-->>Gateway: Response
  Gateway-->>Client: Response
  Note over Gateway,Inventory: Downstream respects parent decision
~~~

Its advantages are early decision-making, low overhead, and easy consistency across services. Its limitation is that the sampler usually does not yet know whether the request will ultimately fail or become very slow. A trace dropped at the start generally cannot be kept in full simply because an error occurs at the end.

Therefore, head-based probability does not guarantee capturing every rare error, timeout, or slow trace.

## 4. Parent-Based Sampling

In a distributed system, a request passes through a gateway and then multiple services. If each service decides independently, a trace can be split into recorded parts and dropped parts.

A **parent-based sampler** uses the parent's sampling decision when a valid parent exists. A sampled parent usually causes children to keep recording; a not-sampled parent usually causes children not to record per that decision. When there is no parent, the root sampler decides.

~~~text
No parent: root sampler selects sampled / not sampled
Parent sampled: child typically records per parent
Parent not-sampled: child typically does not record
Remote parent: decision taken from extracted trace context
~~~

In OpenTelemetry, a parent-based sampler can be combined with a trace-ID-ratio root sampler. Specific names and configuration depend on the SDK, bridge, and version. Do not equate every Brave/Micrometer implementation with the OpenTelemetry SDK's internal sampler.

Increasing probability solely on a downstream service will not necessarily record a trace that upstream already dropped. To change that behavior, you must design an end-to-end sampling policy.

## 5. Configuration in Spring Boot

With Spring Boot 3.x and Micrometer Tracing plus an appropriate bridge:

~~~yaml
management:
  tracing:
    sampling:
      probability: 0.1
~~~

Local example using Zipkin:

~~~yaml
spring:
  application:
    name: order-service
management:
  tracing:
    sampling:
      probability: 1.0
  zipkin:
    tracing:
      endpoint: http://localhost:9411/api/v2/spans
~~~

The service name provides metadata for tracing. Probability 1.0 is convenient for low-traffic local/test environments. The Zipkin endpoint configures where spans are sent when the corresponding reporter is installed.

If the application runs in Docker, `localhost` from inside the application container points to that container itself. When Zipkin is another service on the same network, use the service hostname such as `http://zipkin:9411/api/v2/spans`.

### 5.1. Dependencies and Bridges

Actuator provides the management/Observation foundation, but sampling is only useful when a tracing implementation and exporter are present. Maven example for the Brave bridge and Zipkin Reporter:

~~~xml
<dependencies>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
  </dependency>
  <dependency>
    <groupId>io.micrometer</groupId>
    <artifactId>micrometer-tracing-bridge-brave</artifactId>
  </dependency>
  <dependency>
    <groupId>io.zipkin.reporter2</groupId>
    <artifactId>zipkin-reporter-brave</artifactId>
  </dependency>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
  </dependency>
</dependencies>
~~~

Use a compatible Spring Boot BOM/parent. With the OpenTelemetry bridge and exporter, dependencies differ. Do not mix multiple tracing bridges in the same application without a clear architecture. Properties and auto-configuration vary by version; verify the configuration metadata of your actual Spring Boot version.

## 6. Sampling Decision and Trace Context Propagation

Trace context carries the sampling decision between services. W3C Trace Context uses the `traceparent` header with a flags field; the sampled bit indicates the sampled state. B3 can propagate sampling information via the `b3` or `X-B3-Sampled` header.

~~~http
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
~~~

Flags `01` in the example has the sampled bit enabled. This is wire propagation data; do not modify it manually in business code.

When the gateway selects sampled, it injects the trace context. `order-service` extracts the context before creating the server span, the parent-based sampler continues the decision for children, and subsequent services keep injecting/extracting. If the gateway does not sample, downstream services typically respect that decision.

### 6.1. Broken Propagation

If downstream does not receive the context, it may start a new root trace and sample independently. The waterfall is split, trace IDs differ, and the system-wide sampling ratio is no longer as intended.

Check HTTP client instrumentation, inbound/outbound headers, W3C/B3 compatibility, proxy forwarding, service mesh, and async context propagation. A correct sampling probability cannot fix broken propagation.

## 7. Estimating Trace and Span Counts

Initial estimate:

\[
Traces_{kept/day} \approx Requests_{traced/day} \times p
\]

For example, with 500 requests/second, 86,400 seconds/day, and p=0.05:

\[
500 \times 86{,}400 = 43{,}200{,}000
\]

\[
43{,}200{,}000 \times 0.05 = 2{,}160{,}000\ traces/day
\]

If each trace averages 8 spans, there will be roughly 17.28 million spans/day. If an average serialized span is 1.2 KB, raw payload is around 20.7 GB/day.

This is a sizing calculation, not an exact forecast. Actual size depends on span count, attributes, events, resource metadata, compression, protocol, batching, retries, indexing, and retention.

| Factor | Impact |
| --- | --- |
| Request rate | Increases potential traces |
| Sampling probability | Increases expected traces |
| Spans per trace | Increases record count |
| Attributes and events | Increases payload and indexing cost |
| Retention | Increases cumulative storage |
| Indexing/search | Can cost more than payload transfer |

Reducing probability is not the only way to optimize cost. Limit unnecessary attributes/events, payload size, retention, and indexing.

## 8. Low Probability Misses Rare Errors

With N requests, error rate q, and independent sampling p, the expected number of retained error traces is:

\[
E[Errors_{kept}] = N \times q \times p
\]

For example, 1,000,000 requests, error rate 0.01% (q=0.0001), sampling p=0.01:

\[
1{,}000{,}000 \times 0.0001 \times 0.01 = 1
\]

Only one error trace is expected to be kept. If there are 100 independent errors, the probability of retaining zero error traces is:

\[
P(0)=(1-p)^{100}=(0.99)^{100}\approx0.366
\]

About 36.6% under this simple model. Low sampling may suffice for common traffic but does not guarantee retaining rare errors. Use metrics/logs to detect and quantify them; consider tail sampling if the pipeline supports it.

Do not use the error trace count in the backend as the overall error rate when sampling is not calibrated for it. SLIs/SLOs should be based on metrics with clear semantics.

## 9. Head Sampling vs. Tail Sampling

| Aspect | Head-based probability | Tail sampling |
| --- | --- | --- |
| Decision timing | When the trace starts | After the Collector receives spans to evaluate |
| Knows final outcome | Usually not | Can inspect received status/duration |
| Retains rare errors | Not guaranteed | Can prioritize if spans reach Collector and policy matches |
| Resources | Early decision, lightweight | Requires buffers/state and capacity |
| Risks | Misses errors appearing later | Missing spans, buffer full, decision delay |

Tail sampling is not a simple `management.tracing.sampling.probability` property. It is typically a processor/policy in the OpenTelemetry Collector or a backend with equivalent capabilities.

~~~text
Conceptual policy:
  keep trace if it has an ERROR span
  or total duration exceeds slow threshold
  keep an additional small ratio of normal traces
~~~

The Collector can only decide based on the spans it has received. If the head sampler at the source dropped the trace and never sent spans, the tail sampler cannot recover that data. Tail sampling requires buffering, timeouts, capacity planning, and consistent trace routing to the decision tier.

## 10. Sampling by Environment

Do not use a single default probability across all environments. Illustrative example:

~~~yaml
# application-local.yml
management:
  tracing:
    sampling:
      probability: 1.0
~~~

~~~yaml
# application-staging.yml
management:
  tracing:
    sampling:
      probability: 0.5
~~~

~~~yaml
# application-prod.yml
management:
  tracing:
    sampling:
      probability: 0.05
~~~

Local can capture all traces when traffic is small; staging uses a high rate to verify instrumentation; production balances investigation quality with budget. These numbers are only examples—measure actual traffic and capacity.

An environment variable using relaxed binding typically looks like:

~~~text
MANAGEMENT_TRACING_SAMPLING_PROBABILITY=0.05
~~~

Verify the effective configuration source, active profiles, environment variables, and centralized config. Changing configuration does not necessarily alter the decision for traces that have already started. If dynamic sampling changes are needed, use a mechanism supported by the implementation.

## 11. Metrics, Logs, and Trace Sampling

| Signal | Sampling/filtering policy | Role |
| --- | --- | --- |
| Counter/Timer metrics | Not reduced by tracing probability in typical setups | Counts, latency, error rate |
| Traces | SDK/tracer sampler, Collector tail sampler | Waterfall of selected executions |
| Application logs | Logging level/filter/agent | Event details |
| Business audit | Business retention policy | Guarantees storage of critical events |

A request without a trace can still have logs and metrics. Conversely, a sampled trace does not guarantee that every related log record is retained.

Some systems support **exemplars** to link a metric data point to a trace ID. Exemplars do not turn trace ID into a metric label and do not replace a sampling policy. Do not attach `traceId` to every Counter/Timer because cardinality will explode.

## 12. Verifying Sampled Decisions and Propagation

W3C `traceparent` example:

~~~http
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
~~~

Flags `01` has the sampled bit enabled; flags `00` indicates an unsampled trace per W3C Trace Context. B3 single-header can look like:

~~~http
b3: 4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-1
~~~

Do not manually forge headers to force production sampling. Inspect using approved instrumentation/proxies and avoid logging headers that contain credentials.

Debug checklist:

- Does the gateway receive trace context from upstream or start a new trace?
- Where is the root sampler and what is the effective probability?
- Does client instrumentation inject headers?
- Does downstream properly extract W3C/B3?
- Does the parent-based policy respect the sampled decision?
- Does a proxy/service mesh drop headers?
- Do async executors/Reactor preserve context?
- Does the Exporter/Collector receive the spans?

## 13. Choosing Probability by Operational Requirements

Choose based on goals, not simply because a number is popular:

- **Routine latency:** a moderate rate may suffice to view typical waterfalls.
- **Rare errors:** low head probability can miss them; metrics must measure error rates, and tail sampling can prioritize traces if the Collector receives spans.
- **Payment flows:** per-operation/service priority policies can be useful, but data must be protected.
- **Production incidents:** sampling can be increased temporarily in a controlled manner after verifying capacity.
- **Audit/compliance:** tracing sampling does not replace audit systems that must store every event.

### 13.1. Budget-Based Estimation

Suppose the backend accepts at most 5 million spans/day, each trace averages 10 spans, and the service handles 10 million requests/day:

\[
p \approx \frac{5{,}000{,}000}{10{,}000{,}000 \times 10}=0.05
\]

5% is a starting point assuming every request produces one trace and 10 spans/trace. In practice, account for background jobs, retries, messaging consumers, other services, and burst traffic.

### 13.2. Controlled Changes

Increase when the backend still has budget and current traces are insufficient for investigation. Decrease when the exporter/collector is overloaded, exceeds quota, or costs are too high. Before cutting drastically, remove unnecessary attributes/events and duplicate instrumentation. Every change needs an owner, time limit, dashboard, and rollback condition.

## 14. Sampling and Baggage

Baggage can be propagated alongside trace context, but it **does not automatically control sampling**. A field like `region=ap-south` does not keep a trace unless a custom sampler/policy reads that attribute at decision time.

With a head-based sampler, an attribute/baggage might not exist yet when the root decision is made. Attaching `priority=high` after an Observation starts does not necessarily alter root sampling. A tail sampler can read attributes after the Collector receives spans, if the policy supports it.

Do not put trace ID or unique baggage IDs into metric tags to drive sampling; that introduces cardinality and data risks.

## 15. Common Pitfalls and Diagnostics

| Symptom | Possible cause | How to check |
| --- | --- | --- |
| No traces seen at probability 0.1 | Traces not selected | Send sufficient test traffic, check sampled decision |
| Sampling 1.0 yet UI lacks traces | Missing bridge/exporter, network error, storage/index | Inspect pipeline |
| Gateway has trace, downstream missing span | Lost header or missing instrumentation | Check client/server integration |
| Downstream starts new trace | Parent context not extracted | Check W3C/B3 and proxy |
| Backend ratio diverges from probability | Parent decisions, multiple sources, drops on export | Check sampler, Collector, and ingest |
| Rare error traces absent | Head sampling dropped early | Metrics, tail sampling, or priority policy |
| Metrics count drops with trace ratio | Confusing the two pipelines | Check MeterRegistry and tracing |
| Raising probability overloads Collector | Spans/attributes exceed capacity | Queue, exporter errors, memory |
| Changing property does not alter ratio | Property precedence or config not applied | Verify effective config |
| Error logged but no error trace | Sampling, Observation not recording error, exporter drop | Check error callback and export |

Workflow: verify effective property; generate sufficient workload; check trace context/sampled flags; correlate root with downstream spans; check exporter/Collector queues and drops; use unsampled metrics to assess actual errors; verify logging correlation separately.

## 16. Scenario: Rare Errors Missed at 1% Sampling

**Context:** `order-service` handles 2 million requests per day. Downstream timeouts occur on 0.02% of requests. Probability is 0.01 (1%).

Expected errors:

\[
2{,}000{,}000 \times 0.0002=400
\]

Expected retained error traces:

\[
400 \times 0.01=4
\]

Only about four error traces per day are expected. Metrics can still reflect all ~400 errors.

### Investigation and Improvement

1. Metrics dashboards detect the rising timeout rate.
2. Logs record normalized exceptions and trace ID when context exists.
3. Sampled traces reveal slow downstream spans.
4. The team evaluates capacity and tail sampling if the pipeline receives full spans.
5. Remove unnecessary attributes, maintain baseline sampling, and monitor queues/drops after changes.

**Takeaway:** low probability reduces cost but does not guarantee traces for rare errors. Metrics quantify impact; traces help pinpoint specific execution paths.

## 17. Hands-On Exercises and Self-Check Questions

### Exercise A — Verify Probability

Send 10,000 requests in a test environment, trying probabilities 1.0, 0.5, 0.1, and 0.01. Count traces in the backend when the exporter is not dropping, compare with expectations, and explain variance. Verify the request Counter still records all requests.

### Exercise B — Parent Propagation

Set up a gateway and `order-service`. The gateway starts the trace, the HTTP client forwards trace context, and downstream extracts context. Verify the same trace ID for sampled and not-sampled parents. Then intentionally strip the header in a test to observe split traces.

### Exercise C — Cost Estimation

A service processes 1,000 requests/second, 5% probability, average 12 spans/trace. Calculate requests/day, traces/day, spans/day, and payload if an average span is 0.8 KB. List factors that make reality differ from the estimate.

### Exercise D — Rare Errors

An error occurs on 0.001% of requests with 1% head sampling. Calculate the expected error traces in one million requests. Explain why tail sampling only keeps traces if spans reach the Collector and what buffer resources it needs.

### Exercise E — Production Review

Review probability per environment, config precedence, root/parent policy, propagation format, spans/trace, exporter capacity, relationship with metrics/logs, owner, and rollback conditions.

### Self-Check Questions

1. How is a sampling probability of 0.1 interpreted?
2. Why are 10 requests not guaranteed to produce exactly one trace?
3. When does a head-based sampler decide, and what is its limitation?
4. How does parent-based sampling use the upstream decision?
5. What role does the W3C sampled flag play?
6. Why does trace sampling not reduce Micrometer Counters?
7. How does the expected number of error traces depend on traffic, error rate, and probability?
8. How does tail sampling differ from head-based sampling?
9. Why might increasing probability on a child not record a not-sampled parent?
10. Why shouldn't the trace backend be used to count total requests?
11. Is 100% sampling always safe in production?
12. When traces are missing, how should sampling, propagation, exporter, and backend be checked?

**Completion criteria:** understand probability and statistical variance; distinguish head/parent/tail sampling; configure Spring Boot; understand sampled flags/propagation; estimate spans/cost; distinguish traces from metrics/logs; diagnose missing traces and design controlled sampling.

## 18. Key Takeaways

- `management.tracing.sampling.probability` configures trace selection probability per the tracing integration; `0.1` means roughly 10% expected, not an exact per-minute ratio.
- **Head-based sampling** decides early and saves resources, but can miss errors/slowness appearing later.
- **Parent-based sampling** keeps decisions consistent via trace context across services; check sampled flags when downstream spans are missing.
- **Tail sampling** can prioritize errors/latency after the Collector receives spans, but requires buffers/capacity/policies. It cannot recover spans dropped by a head sampler at the source.
- Trace sampling does not automatically reduce Counter/Timer metrics or application logs. Use metrics for SLIs/SLOs and traces to inspect details of specific executions.
- Estimate costs based on request rate, probability, spans/trace, span size, retention, and indexing.
- Only increase sampling in a controlled way, scoped by environment and time limit. Do not default to 100% in production or treat tracing as an audit store.

## References

- [Spring Boot Reference — Tracing](https://docs.spring.io/spring-boot/reference/actuator/tracing.html)
- [Spring Boot Reference — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html)
- [Micrometer Tracing Reference](https://docs.micrometer.io/tracing/reference/)
- [OpenTelemetry Specification — Sampling](https://opentelemetry.io/docs/specs/otel/trace/sdk/#sampling)
- [OpenTelemetry — Sampling concepts](https://opentelemetry.io/docs/concepts/sampling/)
- [OpenTelemetry Collector — Tail Sampling Processor](https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/main/processor/tailsamplingprocessor)
- [W3C Trace Context](https://www.w3.org/TR/trace-context/)
