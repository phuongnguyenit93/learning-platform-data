# Postmortem Using Telemetry

A postmortem is the process of reconstructing an incident after it occurred, explaining why the system responded the way it did, and identifying changes to reduce the likelihood of recurrence. A good postmortem is evidence-based, describes user impact, and focuses on improving systems rather than blaming individuals.

In the `SPRING_BOOT_OBSERVABILITY` module, this lesson brings together signals produced by Micrometer Observation, metrics, logs, and distributed tracing into a verifiable narrative. You will use telemetry to pinpoint when an incident began, trace the failing execution path, quantify impact scope, and turn findings into concrete operational action items.

## Objectives

After this lesson, you will be able to:

- Distinguish the roles of metrics, logs, and traces during incident investigations.
- Build a timeline from alerts, deployment events, and telemetry data.
- Correlate requests, traces, spans, and logs to follow a failure across multiple components.
- Quantify impact using aggregate figures while accounting for sampling limits and missing data.
- Write a postmortem with root causes, contributing factors, and measurable action items.

## What Evidence Does Telemetry Provide?

The three signals answer three different sets of questions. During investigations, use them together:

| Signal | Core Question | Typical Evidence |
|---|---|---|
| Metrics | What changed, when did it start, and how wide was the impact? | Error rates, throughput, p95/p99 latency, CPU usage, heap, connection pools, queue depth |
| Logs | What events or decisions did the application record? | Exceptions, timeouts, validation failures, business state, configuration and version details |
| Traces | Which components did a request traverse and where did it slow down or fail? | Root spans, child spans, per-step durations, errors on client/server spans, inter-service relationships |

For example, metrics show an HTTP 5xx spike right after a deployment. Traces reveal database call span durations climbed sharply. Logs on those same traces record database connection acquisition timeouts. When all three pieces align, a connection pool exhaustion hypothesis stands on far firmer ground than looking at a single exception line alone.

Metrics are suited for evaluating trends and scale because they aggregate across requests. Logs provide specifics of individual events. Traces map execution paths and timing relationships across operations. A sampled trace does not represent total traffic; never use found trace counts as a substitute for aggregate metric counts.

## Preparing Telemetry Before an Incident Occurs

A postmortem is only as strong as the data the system already emits. In Spring Boot applications, standardize naming and context attachment across the entire execution path.

### Use consistent identifying attributes

Every signal should carry enough metadata to identify the running environment and version, such as:

- `service.name`: stable service name, e.g., `order-service`.
- `deployment.environment`: environment such as `production` or `staging`.
- `service.version`: deployed version or commit.
- `traceId` and `spanId`: correlate logs with their matching trace.
- Route template, HTTP method, status code, and operation name: group requests cleanly.

Never attach user IDs, emails, order IDs, request URLs containing identifiers, or arbitrary strings to metric labels. High-variance values inflate cardinality, consume memory, and hurt query performance. For HTTP metrics, prefer route templates like `/orders/{id}` over raw paths like `/orders/847291`.

### Preserve context propagation across requests

Traces are only useful when context crosses every boundary: HTTP clients, message brokers, async executors, and downstream services. If a processing step starts a new span without linking to the parent trace, postmortems face fragmented traces that make tracing the original request difficult.

Use instrumentation and Observations aligned with your Spring Boot stack; verify both synchronous and asynchronous flows. For message queues, propagate trace context via message headers and build proper span relationships when consumers process messages. Never invent a fresh trace ID per log line or per tier.

### Emit structured, correlatable logs

Logs should include timestamp, level, logger name, message, service, version, and trace context when available. For key events, add a stable operation name or error code. Avoid logging tokens, passwords, personal data, or sensitive payloads.

Example abbreviated JSON log:

```json
{
  "timestamp": "2026-11-22T09:05:14.218Z",
  "level": "ERROR",
  "service.name": "order-service",
  "service.version": "2026.11.22.1",
  "traceId": "4bf92f3577b34da6a3ce929d0e0e4736",
  "spanId": "00f067aa0ba902b7",
  "operation": "inventory.reserve",
  "error.code": "DEPENDENCY_TIMEOUT",
  "message": "Inventory reservation timed out"
}
```

Actual field names depend on your encoder and logging configuration. What matters is that trace IDs in logs match traces shipped by exporters. Even if an application writes plain text logs, trace ID and span ID can be injected into MDC so log platforms can search them.

### Understand sampling and retention

Sampling lowers trace collection costs, yet it can drop the trace of a failing request. With fixed-rate head sampling alone, rare errors or high-latency outliers may go unrecorded. Consider tail sampling or collector policies that prioritize error and slow traces where supported by your architecture.

Metrics, logs, and traces can have different retention periods. Before an incident strikes, know which data persists, what ingest lag exists, and whether host clocks are synchronized. During investigations, record exact data sources and query windows so others can reproduce your findings.

## Telemetry-Driven Investigation Workflow

### 1. Define the incident and preserve evidence

Record detection time, who or what detected it, affected services, observed symptoms, and current status. Pick a time window spanning the normal pre-incident period, onset, mitigation, and recovery.

Save dashboards, queries, representative trace IDs, relevant logs, and deployment events. Note timezones; normalize timelines to UTC when comparing data across services. Never edit or delete original evidence during an investigation.

### 2. Build a timeline from multiple sources

Start from metrics or alerts to pinpoint when behavior shifted. Then cross-reference against:

- New version deployments, rollbacks, or feature flag changes.
- Configuration updates, secret rotations, quotas, or resource limit changes.
- Events from databases, caches, message brokers, and downstream dependencies.
- Traffic shifts, batch job schedules, or routine operational tasks.

Never assume a deployment caused an incident merely because two events happened close together. Inspect data before and after the deploy, check services that were not deployed at the time, and find causal evidence connecting the change to the symptoms.

### 3. Quantify impact scope

Use metrics to answer quantitative questions:

- How many requests failed or slowed down?
- Which routes, tenants, deployment regions, or dependencies were affected?
- How long did error rates and latency remain elevated?
- Were nominally successful requests indirectly affected, such as delayed processing or message backlogs?
- When did the system return to normal levels?

Distinguish absolute counts from rates. Ten errors in a minute mean something very different when a service handles one hundred requests versus one million requests. Where possible, compare against a baseline from the same time of day or similar traffic profile. State formulas and measurement windows clearly in the report.

### 4. Follow traces to locate abnormal execution steps

Pick representative traces for both failing and successful requests within the same window. Compare root spans and child spans to identify:

- Which span accounts for most of the duration?
- Did errors originate in the ingress service or a downstream dependency?
- Are there retries, timeouts, queue waits, or unexpected sequential calls?
- Did context break across HTTP, message brokers, or executors?

A long span alone does not prove that component is the root cause. For instance, an HTTP client span can stretch out because the target service is slow, because a connection could not be acquired, or because the client is waiting between retries. Expand investigation to server-side spans, connection pool metrics, and logs sharing that trace ID.

### 5. Use logs to confirm the failure mechanism

After narrowing down with metrics and traces, search logs by trace ID, span ID, operation, error code, and time window. Find the earliest failure event in the chain rather than reading only the final exception at the API layer.

Inspect logs from both caller and callee. One service may log a timeout while the target service logs rejected requests due to resource exhaustion. Cross-check timestamps and trace context to avoid conflating unrelated requests occurring close together.

### 6. Identify root causes and contributing factors

Causes must explain the sequence of events with supporting evidence. Separate:

- **Direct cause:** the trigger condition causing failure, such as a new query holding database connections longer.
- **Contributing factors:** conditions worsening severity, such as small pools, concurrent retries, or missing timeouts.
- **Detection gaps:** why alerts failed to catch the issue early or dashboards failed to point to the right component.
- **Recovery gaps:** why rollback, load shedding, or traffic shifting took longer than expected.

You can ask iterative "why" questions to deepen analysis, stopping at modifiable system conditions. Avoid conclusions like "operator carelessness." Where evidence is insufficient to confirm, state hypotheses and confidence levels alongside action items to gather missing proof.

### 7. Finalize action items and verify effectiveness

Each action item should state a verifiable change, an owner, a due date, and completion criteria. Prioritize mitigations that reduce impact or prevent recurrence, followed by improvements to detection and diagnosability.

Examples:

| Action Item | Completion Criteria |
|---|---|
| Add alert when HTTP 5xx ratio breaches threshold over 5m | Alert tested with synthetic data and linked to a runbook |
| Monitor connection pool wait times | Dashboard displays active, idle, pending, and timeouts |
| Bound retries and set timeouts on dependency calls | Load test verifies retries do not amplify failures |
| Add trace context to consumer logs | Consumer logs are searchable from message traces |
| Add performance checks for modified queries | Pipeline enforces regression thresholds with saved results |

Avoid vague action items like "improve monitoring" or "be more careful during deploys." Break large work into verifiable steps and track action items after the postmortem concludes.

## Putting It into Practice with Spring Boot and Micrometer

Spring Boot Actuator provides endpoints to inspect application health and metrics. In production, expose only needed endpoints and protect them with appropriate authentication, authorization, and network policies.

Example checking HTTP metrics via Actuator:

```bash
curl -s http://localhost:8080/actuator/metrics/http.server.requests
```

This endpoint shows whether the metric is recorded and which tags are present. With the Prometheus registry, metric names typically translate into series like `http_server_requests_seconds_count` and `http_server_requests_seconds_bucket`. Exact names and label sets depend on versions, registries, and instrumentation; check actual output at `/actuator/prometheus` before writing queries.

Common PromQL queries used during investigations:

**5xx error request rate by route and method:**

```promql
sum by (uri, method) (
  rate(http_server_requests_seconds_count{status=~"5.."}[5m])
)
```

**Ratio of 5xx error requests to total requests:**

```promql
sum(rate(http_server_requests_seconds_count{status=~"5.."}[5m]))
/
clamp_min(sum(rate(http_server_requests_seconds_count[5m])), 1e-9)
```

**p95 latency by route from histograms:**

```promql
histogram_quantile(
  0.95,
  sum by (le, uri) (
    rate(http_server_requests_seconds_bucket[5m])
  )
)
```

These queries assume matching metric and label names exist. If your system emits different names or labels, adjust to match real data. Never add high-cardinality labels just for finer queries. When dissecting a single request, use traces and logs.

In systems with Micrometer Tracing, traces can ship via OTLP or another configured exporter. When reading traces, inspect service name, operation, parent-child relationships, duration, status, and exception events. Cross-reference traces with logs via trace ID. If a span is missing in part of a trace, check instrumentation, context propagation, sampling, and exporter status before assuming that step never executed.

Micrometer Observation gives a single instrumentation point per operation; attached handlers can emit both metrics and traces. Metrics track aggregate behavior, while traces follow individual executions. When creating custom Observations, choose stable operation names and attach only low-cardinality key-values with bounded value sets. Per-request identifying values belong in traces or logs, not metric tags.

## Example: Order API Latency Spike After Deployment

Suppose `order-service` deploys version `2026.11.22.1`. Minutes later, p95 latency on `POST /orders` climbs from around 180 ms to 1.8 seconds and the 5xx rate jumps from 0.2% to 6%.

| UTC Time | Observation | Evidence Source |
|---|---|---|
| 09:00 | New version deployed | Deployment event |
| 09:04 | p95 rises and 5xx errors begin climbing | HTTP metrics |
| 09:05 | Traces show database query spans dominating duration | Distributed traces |
| 09:06 | Connection pool shows queued requests; logs record timeouts | Pool metrics and logs |
| 09:18 | Rolled back the new release | Deployment event |
| 09:22 | p95 and error rate return near baseline | HTTP metrics |

The investigation team picks traces from both successful and failing requests within the same window. Failing traces consistently show markedly longer database query spans. Logs linked by the same trace ID record timeouts waiting for query results; database metrics confirm query duration rose post-deploy. After rollback, indicators gradually returned to baseline.

This evidence supports concluding that a query-path change in the new release increased database execution time, held connections longer, and caused requests to time out waiting. Connection pool limits forced concurrent requests to queue, widening impact, though pool size was not the initial trigger.

The postmortem should document how to verify the hypothesis—such as comparing queries or query plans across versions, reproducing on test data, and re-testing after the fix. Action items may include optimizing the query, adding query performance regression checks, monitoring pool wait times, and alerting on latency alongside error rate. Without query-plan evidence yet, record it as an unverified hypothesis rather than presenting it as proven fact.

## Reusable Postmortem Template

```markdown
# Postmortem: <incident name>

## Overview
- Start/End time (UTC):
- Service and version:
- Facilitator:
- Impact severity:

## Summary
- What happened?
- How were users affected?
- How did the system recover?

## Impact
- Failed request count and error rate:
- Latency before, during, and after incident:
- Affected routes, dependencies, or regions:
- Data sources and calculation method:

## Timeline
| UTC Time | Event | Evidence |
|---|---|---|

## Technical Analysis
- Metrics and dashboards:
- Representative trace IDs/spans:
- Related logs and error codes:
- Deployment/configuration changes:
- Direct cause:
- Contributing factors:
- Unconfirmed items:

## Response and Recovery
- Mitigation actions:
- Recovery timestamp:
- What worked well / what did not:

## Action Items
| Action | Owner | Due Date | Completion Criteria |
|---|---|---|---|

## Lessons Learned
- What helped detect or mitigate faster?
- What evidence was missing?
- Which changes need re-verification after completion?
```

## Common Pitfalls

- **Looking only at the final error log:** an API exception may simply be the consequence of a downstream timeout. Follow traces and logs across all involved layers.
- **Using traces to infer error rates:** sampling can drop requests. Use metrics for rates and traces to understand individual execution flows.
- **Equating correlation with causation:** a deployment near an incident is only a lead. Prove the change produced the symptoms.
- **Using high-cardinality labels:** placing user IDs or transaction IDs into metrics can overload the metrics backend. Keep those values in logs or traces if data policy permits.
- **Ignoring clock skew and ingest lag:** unsynchronized timestamps can scramble timeline ordering. Check UTC alignment, clock sync, and backend ingest delays.
- **Writing unmeasurable action items:** every item needs an owner and verifiable completion criteria.

A dependable postmortem enables another engineer to trace the evidence, understand why the incident happened, and verify remediations. When metrics establish scope, traces map the path, and logs explain specific events, telemetry becomes the foundation for improving Spring Boot application reliability incident after incident.
