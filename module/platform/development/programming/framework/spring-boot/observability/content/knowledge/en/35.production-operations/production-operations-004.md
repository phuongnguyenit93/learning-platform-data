# Sampling by Environment

In the **SPRING_BOOT_OBSERVABILITY** module, Spring Boot uses Micrometer Observation to connect application behavior with metrics, logs, and distributed tracing. In production deployments, request and span counts can be very high. Sending every trace to the backend preserves maximum detail but increases bandwidth, storage usage, and processing cost. Sampling solves this problem by selecting a subset of traces to record and export.

The sampling rate must fit each environment. On a developer workstation, teams typically need visibility into nearly every request for debugging. In staging, enough data is needed to validate production-like behavior. In production, the rate must balance investigation capability against operational budget. There is no single number that fits every system; the decision must account for traffic volume, average spans per trace, incident investigation needs, and tracing backend capacity.

## 1. What Is Sampling and What Problem Does It Solve?

A distributed trace describes the path of a request across multiple components, from the ingress service to HTTP calls, database queries, or message consumers. Each operation is typically represented by a span. As traffic grows, the number of traces and spans grows along with transport, storage, indexing, and query costs.

Sampling is the decision of whether to record and export a trace. If the sampling rate is 0.1, the system selects approximately 10% of eligible traces. A rate of 1.0 selects all eligible traces; a rate of 0.0 selects none under that sampler.

Sampling is typically applied to tracing. It should not be misunderstood as a sampling rate for all observability signals:

- Metrics are still recorded for requests according to configured handler metrics, even when a trace is not sampled. This keeps request rate, error rate, and latency charts representative of total traffic.
- Application logs continue to be written according to logging configuration. Whether a trace is exported is a separate decision; whether a log entry can link to a stored trace also depends on how the tracer and logging framework integrate context.
- Tracing sampling decides which traces/spans are recorded or exported by the tracing pipeline.

Because metrics and tracing serve different purposes, never lower trace sampling and then use exported trace counts to infer total request counts. Use metrics for aggregate measurement, and use traces to inspect the execution path of selected requests.

## 2. Head-Based Sampling vs. Tail-Based Sampling

Two common ways to organize sampling are head-based and tail-based.

**Head-based sampling** makes the decision early, usually when the trace is created. With a configured probability, the sampler selects or drops the trace upfront. This approach is simple, low-overhead, and suitable when data volume must be bounded right inside the application.

Advantages of head sampling:

- Reduces the number of spans recorded and sent right at the service.
- Easy to configure per environment using application properties.
- Early decisions minimize memory and network overhead in services.
- Suits high-traffic systems where uniform sampling is sufficient.

The limitation is that the sampler does not know the final outcome of the request when making the decision. A request that later returns an error or experiences unusual latency can still be excluded if the initial decision did not select it. Raising the sampling rate improves the odds of capturing rare cases, while also increasing cost.

**Tail-based sampling** defers the decision until the collector has received enough of the trace or enough data to evaluate a policy. The collector can prioritize retaining traces with errors, latency above a threshold, or attributes matching targeted criteria.

Tail sampling is useful when you must capture rare cases such as production errors or slow requests above a latency threshold. In return, the collector must buffer spans for a window of time, assemble spans belonging to the same trace, and have sufficient resources to process them. Spans of the same trace must be routed to the same collector instance or to a layer capable of aggregating traces.

If applications already drop most traces via head sampling, the collector cannot recover dropped traces for tail sampling. Consequently, a tail-sampling architecture usually requires applications to send a sufficiently broad stream of incoming traces, after which the collector decides which ones to keep. This increases load on the collector and network, so it must be designed alongside resource limits and system protection policies.

| Criterion | Head-based sampling | Tail-based sampling |
| --- | --- | --- |
| Decision timing | When the trace starts or very early in its lifecycle | After the collector receives the required trace data |
| Available information | Context and attributes available at the start | Outcome, errors, latency, and received spans |
| Advantages | Simple, reduces load early, easy to configure in apps | Can prioritize error or slow traces |
| Limitations | Can miss rare errors or unusual latency spikes | Requires buffering, collector resources, and trace-aware routing |
| Typical configuration point | Sampler in the application or tracing SDK | Collector/pipeline supporting tail sampling |

You do not have to pick a single mechanism for an entire system. You can use head sampling to bound incoming traffic and tail sampling on a dedicated pipeline, as long as you remember that a tail sampler can only choose from traces that actually reach the collector.

## 3. Configuring Sampling via Spring Boot Profiles

In Spring Boot 3.x integrated with Micrometer Tracing, the tracing sampling rate can be configured with:

~~~yaml
management:
  tracing:
    sampling:
      probability: 1.0
~~~

The value is a probability between 0.0 and 1.0. Manage this value via environment configuration so the rate can be changed without modifying business code.

The examples below illustrate a starting set of values. These are reference values for design and testing, not universal standards:

**application-dev.yml**

~~~yaml
management:
  tracing:
    sampling:
      probability: 1.0
~~~

**application-staging.yml**

~~~yaml
management:
  tracing:
    sampling:
      probability: 0.5
~~~

**application-prod.yml**

~~~yaml
management:
  tracing:
    sampling:
      probability: 0.05
~~~

In this example, dev captures all traces for easy debugging; staging captures roughly half for testing; production captures roughly 5% to control volume. A low-traffic production service with high investigation needs may require a higher rate. A service handling tens of thousands of requests per second may need a lower rate or a specialized sampling policy.

Activate the profile in deployment configuration, for example:

~~~text
SPRING_PROFILES_ACTIVE=prod
~~~

You can also set the property directly via an environment variable so the deployment platform controls the value:

~~~text
MANAGEMENT_TRACING_SAMPLING_PROBABILITY=0.05
~~~

When using environment variables, verify Spring Boot's configuration precedence. External values can override values in profile files. This is convenient for Kubernetes or other deployment platforms, but it can also cause the effective configuration to differ from the file in the repository. Log or inspect the effective configuration safely during startup and check deployment manifests when troubleshooting.

Avoid placing a single rate in a shared configuration file and copying it across every environment. Keep a sensible default for development while explicitly defining overrides for staging and production. In production, manage sampling changes as tracked operational changes that can be audited and rolled back.

## 4. Choosing a Rate Based on Traffic and Budget

The sampling rate alone does not tell you how many spans will be sent. Span volume also depends on root trace count, how many services participate, and the average number of spans per trace.

You can make a rough estimate:

~~~text
selected traces per second
    = root traces per second × sampling probability

exported spans per second
    ≈ selected traces per second × average spans per trace
~~~

For example, a service receives about 20,000 root traces per second, uses a probability of 0.02, and averages 12 spans per trace:

- Estimated selected traces: 20,000 × 0.02 = 400 traces/second.
- Estimated exported spans: 400 × 12 = 4,800 spans/second.

This is only an estimate. Actual numbers can differ due to traces spanning multiple services, spans added or dropped at each tier, retries, batching, uneven traffic, and exporter configuration.

When choosing a production rate, consider:

1. **Traffic and trace breadth.** A single request crossing many services can generate many spans. Do not look only at one service's request rate.
2. **Capacity and retention.** Account for ingest, retention, indexing, and query budgets in the tracing backend.
3. **Investigation goals.** If analyzing rare errors is essential, a rate that is too low may make waiting for a useful trace take far too long.
4. **Representativeness.** Sampled traces should reflect all important endpoints, clients, and business flows.
5. **Application impact.** Monitor CPU, memory, exporter queues, and bandwidth when raising sampling.

A safe rollout strategy is to start from a calculated low rate, measure real load, and increase gradually while the backend has headroom. Whenever you change the rate, record the timestamp and new value so dashboard viewers understand why trace or span counts shifted.

## 5. Keeping Sampling Decisions Consistent Across Services

Distributed tracing is only useful when spans of the same request are linked into a single trace. In a multi-service system, the sampling decision made at the head of the trace must travel with the trace context across HTTP, messaging, and propagation-aware execution boundaries.

For example, service A receives a request and decides to sample it. When calling service B, A propagates the trace context in headers. Service B should follow the parent trace's decision using the tracer's parent-based behavior. If each service decides independently, part of a trace may be exported while other parts are dropped, leaving incomplete traces that are hard to read.

Configure consistent propagation, such as W3C Trace Context or B3 according to your system's chosen standard. Avoid mismatched propagation settings across services. When multiple tracing bridges or SDKs are present, verify the sampler behavior of the exact bridge and version running.

Sampling probability configures the origin sampling decision; it does not replace propagation. If context is lost across an executor, message broker, or thread boundary, spans may start a new trace or lose parent-child relationships even when the sampling rate is set properly. Therefore, check both propagation and sampling whenever traces appear fragmented.

For asynchronous flows, a message producer normally passes trace context in message metadata/headers. The consumer extracts that context to create a continuation span. When messages are reprocessed or trigger new business workflows, decide clearly between a parent-child relationship or a span link rather than assuming every execution behaves like a single synchronous request.

## 6. Combining Sampling with Metrics and Logs

Never reduce metrics recording just to cut down trace volume. Metrics provide the aggregate statistical view: total requests, error rates, percentile latency, and resource utilization. Tracing provides detail on individual sampled executions. The two signals complement each other.

A typical investigation flow:

1. Use metrics to spot elevated error rates or p95/p99 latency.
2. Narrow down the affected service, endpoint, or time window.
3. Use sampled traces to see which services the request traversed and which span was slow or failed.
4. Use logs correlated by trace ID/span ID to inspect related execution details.

When a trace is not sampled, the application may still log a trace ID depending on the tracer and configuration. However, the tracing backend may have no corresponding spans to open. Dashboards should therefore handle cases where logs contain a trace ID that does not exist in the tracing backend.

Never write sensitive data into span attributes or logs just because a trace is sampled. Sampling is not a data protection mechanism. Identifiers, tokens, personal information, and payment data must still follow filtering, masking, and access-control policies.

## 7. Handling Rare Cases and Production Errors

Uniform probabilistic head-based sampling can miss rare failures. If an error occurs in only 1 out of 100,000 requests, a 1% sampling rate may require many requests before capturing an error trace. You can improve investigation readiness by:

- Temporarily increasing the sampling rate during an incident after evaluating load and backend capacity.
- Using tail-based sampling in the collector to prioritize traces with error status or latency exceeding a threshold, if the architecture allows the collector to receive enough incoming traces.
- Maintaining solid metrics and logs to detect errors even when no trace was sampled.
- Alerting on error rate, latency, and saturation rather than on the count of exported error traces.

When using tail sampling, define clear policies: retain error traces, retain traces exceeding latency thresholds, retain a small percentage of normal traces, and cap the total volume retained. Policies must account for traces with many spans, wait times for late spans, and behavior under collector overload. If the collector runs out of memory or restarts before a trace completes, tail-sampling policies can lose buffered data.

Avoid enabling 100% sampling across all of production just to investigate one endpoint when overall traffic is high. Scope the change narrowly, bound its duration, assess added load, and plan the return to normal configuration. If using a custom sampler based on request attributes, prefer stable attributes like normalized routes; never branch unconditionally on raw URLs containing IDs or user input.

## 8. Safely Changing Sampling in Production

Changing sampling changes the observed count of traces and spans. Ingest dashboards can spike or drop even when request traffic has not changed. Always record the sampling probability alongside the rollout timestamp so telemetry shifts are not mistaken for application behavior changes.

A safe change procedure can include:

1. Record the current rate, request rate, span rate, backend capacity, and goal of the change.
2. Estimate the new trace/span rate from traffic and average spans per trace.
3. Update configuration through the profile or environment variable of the target environment.
4. Roll out gradually and verify the effective configuration value on running instances.
5. Monitor exporter queues, export errors, CPU, memory, network, and backend ingest rates.
6. Verify traces contain complete spans across services and propagation remains intact.
7. Document the outcome, keep the new setting if stable, or roll back if over budget.

If raising the rate causes frequent exporter timeouts, full queues, or backend ingest rejections, reduce load or scale the pipeline before proceeding. If trace volume is low while metrics indicate an incident, check sampling decisions at the root service, propagation headers, and sampler configuration across bridges.

## 9. Operational Checklist

Before releasing a sampling configuration, verify:

- Each environment has a clearly defined sampling rate.
- The effective value of management.tracing.sampling.probability matches the deployment configuration.
- The chosen rate accounts for request rate, spans per trace, and backend budget.
- Services honor the sampling decision propagated in trace context.
- Metrics still reflect full traffic according to the metrics handler configuration.
- Logs do not depend on trace export to record critical errors.
- Collectors have sufficient capacity if tail sampling is used.
- Dashboards and alerts distinguish sampling changes from real traffic shifts.
- A mechanism exists to temporarily adjust sampling and restore normal settings after an incident.

Sampling by environment is an operational decision that directly affects cost and investigation effectiveness. With Spring Boot and Micrometer Tracing, configure explicit rates per environment, propagate decisions consistently across services, and monitor real volume at exporters and backends. Use metrics to observe the system as a whole, logs to preserve operational events, and sampled traces to dissect individual execution paths.
