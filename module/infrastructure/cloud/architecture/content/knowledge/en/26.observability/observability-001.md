# Designing Logs, Metrics, Traces, and Operational Events

## 1. Observability Begins with Operational Questions

A cloud system has many components running concurrently: load balancers, API gateways, applications, queues, databases, caches, containers, VMs, and provider-managed services. When a request is slow or fails, looking only at CPU or a single isolated log line is usually not enough to know where the problem started, who it affects, and how to handle it.

**Observability** is the ability to infer the internal state of a system from the signals it emits. A good design helps operations teams answer: what happened, where it happened, which users are affected, when it started, what change it is related to, and what remediation action is appropriate.

In the **CLOUD_ARCHITECTURE** module, architecture is designed from business requirements through networking, compute, data, and deployment model choices. Logs, metrics, traces, and events are part of the operational architecture and must be designed alongside reliability, security, scalability, cost, and Well-Architected principles.

After this lesson, you will be able to:

- Distinguish between logs, metrics, distributed traces, and events.
- Design telemetry around operational questions and business journeys.
- Standardize structured logs, metric labels, and trace context.
- Correlate logs, metrics, and traces using timestamps, resource identity, and correlation IDs.
- Select appropriate SLIs, SLOs, alerts, and dashboards.
- Design a telemetry pipeline with OpenTelemetry Collector or an equivalent component.
- Control sampling, cardinality, retention, access, and sensitive data.
- Evaluate the cost, reliability, and operational effectiveness of an observability platform.

## 2. Four Signal Types and the Questions Each Answers

| Signal | Description | Typical Questions |
|---|---|---|
| **Log** | Record of an event/occurrence at a point in time, usually with detailed context | Which request failed? Which validation was rejected? Which error code appeared? |
| **Metric** | Numerical measurement aggregated over time or dimensions | Are error rate, p95 latency, CPU, or queue depth increasing or decreasing? |
| **Trace** | Chain of spans representing the path of an operation across multiple processes/services | Was the request slow at the gateway, Inventory, database, or provider? |
| **Event** | Notification of a change or occurrence with business/operational significance | When was the booking confirmed? Which deployment just happened? When was a tenant suspended? |

These concepts can be related, but they should not be used interchangeably. A log can record an event; a trace can contain events/span events; a metric can count logs or events. Each type is optimized for a different kind of query.

### 2.1. BookingCloud Example

A customer creates a booking. The request passes through the API gateway, Booking service, Inventory service, Payment provider, and database.

- Metrics show that over the last 5 minutes, the API p95 latency increased from 180 ms to 2.4 seconds.
- Traces show that most of the time was spent in the Inventory service, specifically waiting for a database connection.
- Inventory logs record that the connection pool reached its limit and requests timed out.
- Events show that 3 minutes ago a new version was deployed that increased concurrency.

When combining all four signals, the operations team can form a root-cause hypothesis and identify the change that needs to be rolled back or adjusted.

~~~mermaid
flowchart TB
    USER["User creates booking"] --> GW["API gateway"]
    GW --> BOOK["Booking service"]
    BOOK --> INV["Inventory service"]
    INV --> DB[("Inventory DB")]
    BOOK --> PAY["Payment provider"]
    BOOK --> OUT["Telemetry pipeline"]
    GW --> OUT
    INV --> OUT
    DB --> OUT
    OUT --> LOG["Logs"]
    OUT --> METRIC["Metrics"]
    OUT --> TRACE["Traces"]
    OUT --> EVENT["Operational events"]
    LOG --> QUERY["Investigation / dashboards / alerts"]
    METRIC --> QUERY
    TRACE --> QUERY
    EVENT --> QUERY
~~~

## 3. Start from Business Journeys and Failure Modes

Do not start with the question "which agent should we install?". Start with user journeys and the things that can break.

### 3.1. Mapping Services

For BookingCloud, list:

- Components that receive requests and perform authentication.
- Services that own business logic.
- Databases, caches, queues, and object storage.
- External dependencies such as payment/email providers.
- Batch jobs, schedulers, and asynchronous consumers.
- Control plane, deployment pipelines, and management components.

Each component should have a service name, owner, environment, version, region/zone, and dependency map. Without a consistent service identity, it is difficult to group telemetry or find the responsible owner.

### 3.2. Identify Key Questions

| Journey | Questions to Answer | Priority Signals |
|---|---|---|
| Sign in | Are authentication failures increasing at the provider or in the application? | Metric + log + trace |
| Create booking | What are the success rate and completion time? | Metric + trace + event |
| Hold slot | Is the timeout coming from the service or the database? | Trace + log + DB metric |
| Payment | Is the outcome unknown, declined, or a provider outage? | Event + audit log + metric |
| Send email | What are the backlog and oldest message age? | Queue metric + event + worker log |
| Deploy | How does the new version affect latency/errors? | Deployment event + metric + trace |

### 3.3. Failure Modes That Need Telemetry

- Latency increases while error rate has not yet increased.
- Errors increase in a specific region or tenant tier.
- Database connection pool exhaustion or slow queries.
- Increasing queue backlog and high consumer lag.
- Cache misses/stampede or hot keys.
- Retry amplification and open circuit breakers.
- An external dependency returning 429/5xx.
- Certificates about to expire or TLS handshake failures.
- Deployment/config changes altering behavior.
- Disk, memory, CPU, or quotas approaching limits.

## 4. Logs: Recording What Happened

Logs are suited for events requiring detail, especially when investigating errors, security incidents, and anomalous behavior. Log design must answer who did what, on which resource, where, and with what outcome.

### 4.1. Structured Logging

Prefer structured logs such as JSON instead of free-form strings that are hard to parse. A record might look like:

~~~json
{
  "timestamp": "2026-11-18T10:15:30.125Z",
  "severity": "ERROR",
  "service.name": "inventory-service",
  "service.version": "2.4.1",
  "deployment.environment": "production",
  "cloud.region": "ap-southeast-1",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "span_id": "00f067aa0ba902b7",
  "request_id": "req-7812",
  "tenant_tier": "standard",
  "event_name": "inventory.hold.failed",
  "error.type": "DatabaseTimeout",
  "error.code": "POOL_EXHAUSTED",
  "duration_ms": 1200
}
~~~

The values above are illustrative only. Do not log access tokens, passwords, private keys, payment credentials, sensitive request bodies, or PII unless strictly necessary. Instead, use controlled IDs, masking, or pseudonymization.

### 4.2. Fields to Standardize

| Field | Purpose |
|---|---|
| timestamp | Time of occurrence; standardize on UTC and synchronized clocks |
| severity | TRACE/DEBUG/INFO/WARN/ERROR following convention |
| service.name | Group logs by workload/service |
| service.version | Compare behavior across releases |
| environment/region/zone | Isolate environment and failure domain |
| trace_id/span_id | Link to distributed trace |
| request_id/correlation_id | Track operations across the system |
| event_name/error.code | Machine-readable analysis |
| duration/status | Outcome and processing time |
| safe tenant scope | Analyze impact by tier/segment; avoid exposing unnecessary identifiers |

Not every record needs to have every field; standardize the schema and nullability rules.

### 4.3. Choosing Severity

- **DEBUG:** details used in development or controlled investigation; usually disabled or sampled in production.
- **INFO:** meaningful normal operational milestones.
- **WARN:** abnormal situations that may self-recover or do not yet have major impact.
- **ERROR:** failed operation that requires investigation or handling.
- **FATAL/CRITICAL:** component cannot continue operating or severe impact; naming depends on convention.

Do not log the same exception as ERROR at every layer; that creates dozens of records for a single error and makes it harder to pinpoint the origin. The layer that owns the operation is typically responsible for logging the final error; intermediate layers can add appropriate debug/trace logs.

### 4.4. Log Sampling and Avoiding Log Storms

During an outage, each failing request can generate many logs. If the log pipeline is a synchronous dependency, logging can also slow down requests or lose logs when the system is overloaded.

Measures:

- Use structured logging with clear log levels.
- Apply rate limiting/sampling for repetitive logs.
- Keep full security audit and rare error logs per policy; do not arbitrarily sample mandatory events.
- Use asynchronous/buffered exporters with bounded queues.
- Track metrics for dropped logs, exporter failures, and backlog.
- Avoid logging full payloads or repeating full stack traces continuously.

## 5. Metrics: Measuring State and Trends

Metrics are suited for continuous monitoring, dashboards, alerting, and calculating SLIs. A metric is typically a numerical measurement with a timestamp, value, and a set of dimensions/labels.

### 5.1. Counter, Gauge, Histogram, and Summary

| Type | Meaning | Example |
|---|---|---|
| Counter | Monotonically increases during process lifetime; may reset on restart | Total requests, total errors, processed messages |
| Gauge | Value that can go up or down | Active connections, queue depth, memory usage |
| Histogram | Observed distribution by buckets/count/sum | Request duration, payload size |
| Summary | Client-computed quantiles/summaries depending on the system | Per-process latency quantiles |

Histograms are usually useful for aggregating across multiple instances; summary quantiles cannot always be accurately merged across replicas. Choose the type appropriate for your metrics backend.

### 5.2. RED for Services

For request-handling services, track:

- **Rate:** requests per second.
- **Errors:** count or rate of failed requests.
- **Duration:** latency distribution, commonly viewing p50/p95/p99.

### 5.3. USE for Resources

For resources/infrastructure:

- **Utilization:** usage level of CPU, memory, disk, network, or pools.
- **Saturation:** queuing/waiting level or pressure exceeding capacity.
- **Errors:** resource errors, such as disk errors or network drops.

RED and USE complement each other. RED tells you whether user-facing services are healthy or degraded; USE helps locate the resource that may be the cause.

### 5.4. Metrics for BookingCloud

~~~text
http_server_requests_total{service,route,status_class}
http_server_request_duration_seconds_bucket{service,route}
booking_create_total{outcome}
inventory_hold_duration_seconds_bucket{region}
db_pool_active_connections{service}
db_pool_waiting_requests{service}
queue_messages_ready{queue}
queue_oldest_message_age_seconds{queue}
cache_requests_total{cache_name,result}
payment_provider_requests_total{provider,outcome}
~~~

These are illustrative metric names. Do not put booking_id, user_id, raw URL, email, or trace_id into metric labels.

### 5.5. Cardinality

Cardinality is the number of distinct label combinations. If every request creates a label with a user ID or a URL containing a unique ID, the number of time series can explode, consuming excessive RAM and storage and slowing down queries.

Principles:

- Use route templates such as /bookings/{id}, not raw URLs.
- Only keep dimensions with a bounded, useful set of values.
- Do not add user ID, order ID, or trace ID as metric labels.
- Use logs/traces to investigate details of a single entity.
- Monitor active series, label churn, and metric ingestion volume.

## 6. Distributed Tracing: Following a Request Across Services

A trace records the path of an operation across services/processes. A trace consists of multiple **spans**; each span has start/end times, parent relationships, attributes, and events.

### 6.1. Traces and Spans

- Trace ID identifies the entire operation.
- Span ID identifies a unit of work.
- Parent span ID represents the caller/containment relationship.
- Span attributes describe the service, route, peer, status, or operation.
- Span events record milestones within a span, such as retries or validation results.

~~~mermaid
flowchart LR
    T["Trace: Create booking"] --> G["Gateway span"]
    G --> B["Booking API span"]
    B --> I["Inventory client span"]
    I --> DB["Database span"]
    B --> P["Payment client span"]
    B --> Q["Publish event span"]
~~~

Traces show where time is spent and the relationships between calls. They do not by themselves explain business correctness or which data was committed; combine them with logs and events.

### 6.2. Context Propagation

When service A calls B, trace context must be propagated via HTTP headers, messaging metadata, or the corresponding context mechanism. W3C Trace Context is widely used with headers such as traceparent and tracestate.

For asynchronous messages, the producer injects context into the message; the consumer extracts context to continue the trace or create a suitable linked span. A workflow can span queues and multiple processes, so do not rely on thread-local context.

If context is not propagated, the trace breaks into multiple separate traces and end-to-end latency becomes hard to analyze.

### 6.3. Parent-Child and Span Links

Parent-child is suited for nested calls within the same operation. For consumers processing multiple messages or batches that combine multiple source traces, span links can represent relationships without forcing everything into a simple parent-child tree.

### 6.4. Trace Instrumentation

Auto-instrumentation can be used for HTTP clients/servers, database drivers, messaging, and runtimes. Add manual spans around important business operations:

- booking.create
- inventory.hold
- payment.authorize
- booking.confirm
- notification.dispatch

Do not create overly fine-grained spans for every line of code if they add no value. Do not include unique IDs in span names; use operation names/route templates to avoid cardinality issues in the trace backend.

### 6.5. Sampling

Trace volume can be very large. Sampling decides which traces are kept:

- **Head sampling:** decides at the start of the trace, before knowing the final outcome. Low cost and easy to scale, but may miss rare error traces.
- **Tail sampling:** decides after collecting the trace (or enough of it), allowing prioritization of error/slow traces, but requires buffering, state, and collector/backend resources.
- **Parent-based sampling:** children generally follow the parent's decision to maintain a consistent trace.

A common strategy is to keep a small percentage of normal traces while retaining more error traces, high-latency traces, or critical operations. Consider privacy, quotas, sampling bias, and the tail sampler's ability to handle traces distributed across multiple collectors.

## 7. Operational Events and Audit Events

Events represent meaningful changes. Examples:

- Deployment started/succeeded/failed.
- Feature flag changed.
- Tenant suspended/activated.
- Database failover completed.
- Certificate rotation or KMS key policy changed.
- Queue consumer exceeded retry threshold.
- Booking transitioned from PENDING to CONFIRMED.

### 7.1. Distinguishing Business Events from Logs

Logs typically serve diagnostics and may not be designed for other consumers to depend on. Business events have schemas, owners, delivery semantics, and compatibility policies; they can trigger workflows.

Audit events record significant actions with identity, action, resource, outcome, and timestamp. Audits require integrity, retention, and separate access controls; do not sample arbitrarily if the organization requires full retention.

### 7.2. Sample Event Schema

~~~json
{
  "eventId": "evt-8124",
  "eventType": "booking.confirmed",
  "schemaVersion": 1,
  "occurredAt": "2026-11-18T10:15:30Z",
  "source": "booking-service",
  "subject": "booking/bkg-8124",
  "correlationId": "corr-7812",
  "data": {
    "tenantTier": "standard",
    "bookingStatus": "confirmed"
  }
}
~~~

The payload above is illustrative only. Include only minimal data and avoid unnecessary PII/secrets. Event schemas need to specify version, keys, timestamps, source, delivery/duplicate semantics, and consumer handling.

### 7.3. Ordering, Duplicates, and Replay

Event brokers may deliver duplicate messages or not guarantee global ordering. Consumers need idempotency/event IDs, partition keys, or sequence numbers per business requirements. Replay must be controlled because reprocessing audit/events can cause side effects.

Operational events like "deployment completed" can often be used to annotate dashboards or correlate releases with metrics; do not turn every log into an event bus if there are no clear consumers or contracts.

## 8. Correlating Logs, Metrics, Traces, and Events

The greatest value emerges when all four signal types can navigate seamlessly to one another.

### 8.1. Correlation Fields

Standardize appropriate fields:

- trace_id/span_id.
- request_id/correlation_id.
- service.name/version/environment.
- deployment_id or change_id.
- region/zone/cluster/namespace.
- operation/event name.
- safe tenant tier or segment when permitted.

Do not use a correlation ID as a high-cardinality metric label. It belongs in logs/traces and links to events.

### 8.2. Investigating from Alert to Root Cause

A typical workflow:

1. A metric alert fires when p95 booking latency exceeds the SLO burn threshold.
2. Dashboards break down latency by region, route, and service version.
3. A trace exemplar or sampled trace leads to a slow request.
4. The trace shows the Inventory DB span has high wait time.
5. Logs filtered by trace ID reveal that the connection pool is nearly exhausted.
6. Deployment events show a new version increased worker concurrency.
7. The runbook guides rolling back or limiting concurrency, then monitoring recovery.

~~~mermaid
flowchart TD
    ALERT["Metric alert"] --> DASH["Service dashboard"]
    DASH --> TRACE["Slow/error trace"]
    TRACE --> LOG["Related structured logs"]
    DASH --> EVENT["Deployment / config events"]
    LOG --> ROOT["Root-cause hypothesis"]
    EVENT --> ROOT
    ROOT --> ACTION["Runbook / mitigation"]
    ACTION --> VERIFY["Verify SLI and user impact"]
~~~

### 8.3. Time Synchronization

Timestamps must have a consistent format and synchronized clocks. Use UTC for storage/cross-region queries; use a monotonic clock for in-process durations. Clock drift can cause incorrect log/trace ordering or negative span durations.

## 9. SLI, SLO, and Alerting

Observability is not about collecting everything. The goal is to know whether user experience and reliability are meeting commitments.

### 9.1. SLI

A **Service Level Indicator (SLI)** is a measurement reflecting an aspect of service quality. Examples:

- Availability: proportion of valid requests served successfully.
- Latency: proportion of requests completed under a time threshold.
- Freshness: age of data or projection lag.
- Queue processing: proportion of messages processed within a deadline.
- Durability: proportion of operations confirmed as durably stored per semantics.

Define the numerator and denominator clearly. Do not count client-aborted requests or validation errors against availability without reason; do not exclude system errors just to make metrics look good.

### 9.2. SLO and Error Budget

An SLO is a target for an SLI over a time window. Illustrative examples:

- 99.9% of valid create-booking requests succeed over a rolling 30-day window.
- 95% of GET catalog requests complete under 300 ms.
- 99% of booking events are processed by consumers within 60 seconds.

The error budget is the allowable amount of errors/violations under the SLO. When the burn rate is too fast, the team can slow down releases, focus on reliability work, or take mitigation steps.

### 9.3. Symptom-Based Alerting

Prioritize alerts on user-visible symptoms:

- Booking success rate degrades.
- p95/p99 latency exceeds SLO.
- Unknown payment outcomes increase.
- Queue oldest message age exceeds deadline.
- Error budget burn rate is too fast.

Cause-based alerts such as high CPU, nearly full disk, or connection pool nearing limits are also useful, but need appropriate severity and routing; avoid paging for every abnormal metric that has no impact.

### 9.4. Multi-Window / Multi-Burn-Rate

A short window detects rapid burn; a long window confirms sustained impact. Short and long windows can be combined to avoid alerting on brief spikes. Thresholds should match the SLO and operational capacity, rather than copying a single generic configuration across all services.

### 9.5. Alerts Must Be Actionable

Every critical alert needs:

- Owner/on-call route.
- Severity and user impact.
- Linked dashboard.
- Runbook or diagnostic steps.
- Resolve/auto-close conditions.
- Escalation path when unresolved.

Alerts without an action or owner usually become noise.

## 10. Telemetry Pipeline and OpenTelemetry

### 10.1. Pipeline Architecture

~~~mermaid
flowchart LR
    APP["Apps / SDKs / agents"] --> COL["Collector / agent"]
    INFRA["Cloud / network / DB telemetry"] --> COL
    COL --> PROC["Filter / enrich / batch / sample"]
    PROC --> LOGS["Log backend"]
    PROC --> METRICS["Metrics backend"]
    PROC --> TRACES["Trace backend"]
    PROC --> EVENTS["Event / audit store"]
    LOGS --> UI["Dashboards / query"]
    METRICS --> UI
    TRACES --> UI
    EVENTS --> UI
~~~

**OpenTelemetry (OTel)** provides APIs, SDKs, semantic conventions, and protocols/collectors to generate, collect, and export telemetry. It does not lock you into a single backend; it can export to one or more observability systems depending on the architecture.

### 10.2. Collector Responsibilities

A collector/agent can:

- Receive telemetry via OTLP or appropriate receivers.
- Parse, normalize, and enrich resource attributes.
- Batch/compress to reduce network overhead.
- Filter/drop sensitive fields.
- Apply sampling or tail sampling.
- Route based on signal/environment/tenant policy.
- Retry exports with bounds and internal queuing.
- Expose health/queue/drop metrics of the pipeline itself.

The collector is a critical component. If it fails or its backlog grows, telemetry can be lost right when the system is experiencing an incident. Deploy with HA, bounded buffers, resource limits, and dedicated alerts.

### 10.3. Agents, Gateways, and Collector Tiers

Options:

| Model | Advantages | Trade-offs |
|---|---|---|
| Agent/sidecar per workload | Close to source, enriches with pod/host metadata | Many instances and resource overhead |
| Node/daemon collector | One collector serves multiple workloads on a node | Requires accurate tenant/pod metadata isolation |
| Gateway collector tier | Centralizes routing, tail sampling, and policy | Adds a hop and requires scaling/HA |
| Direct export from app | Simple for small workloads | App depends on backend; retries/buffers harder to control |

An agent/node collector can be combined with a gateway tier. Decisions depend on deployment model, network boundaries, telemetry volume, tail sampling requirements, and failure tolerance.

### 10.4. Telemetry Backpressure

Do not allow exporters to retry infinitely or queue unboundedly. When a backend is unavailable:

- Buffer within memory/disk limits.
- Drop telemetry by priority policy if buffers fill up; preserve security audits per separate requirements.
- Track metrics for dropped spans/logs, queue depth, export errors, and retry counts.
- Prevent the telemetry pipeline from consuming all CPU/memory of business workloads.
- Prioritize essential signals; drop debug/high-volume attributes first.

## 11. Security and Privacy in Telemetry

Telemetry often contains more sensitive information than expected: URL query strings, headers, SQL parameters, user attributes, IPs, emails, file paths, or payloads.

### 11.1. Data Minimization and Redaction

- Never log credentials, access tokens, session cookies, private keys, or payment secrets.
- Mask email/phone/address or replace with pseudonymized identifiers when correlation is needed.
- Do not capture request/response bodies by default unless there is a clear purpose and controls.
- Control SQL statement/parameter capture.
- Reduce precision of client IPs or omit the field if unnecessary.
- Use attribute allowlists instead of collecting every available context attribute.

### 11.2. Access Control

Separate telemetry read permissions by role: application developers can view service logs; security teams view audit/security events; analysts only view masked aggregates; tenant customers only view their own tenant's data if the product provides an observability portal.

Multi-tenant telemetry requires tenant-scoped queries and policies; a shared dashboard must never leak logs/traces from other tenants.

### 11.3. Retention and Data Residency

Choose retention based on signal type, incident investigation needs, compliance, and cost. Debug logs can be kept briefly; audits may need longer retention per policy; aggregated metrics can be kept longer than raw high-resolution data. Verify whether storage regions and export paths to other backends meet data residency requirements.

### 11.4. Auditing the Telemetry Platform

Log who queries/exports telemetry or changes retention, sampling, access policies, and alert routes. Protect logs/audits from being modified or deleted by the application role currently under investigation.

## 12. Sampling, Retention, and Cost

Telemetry volume can grow with request rate, spans per request, log bytes per request, and label cardinality. Cost is not just storage, but also ingestion, indexing, querying, network egress, collector compute, and licensing.

### 12.1. Value-Based Sampling

- Keep a baseline trace percentage for normal traffic.
- Prioritize error traces, slow traces, or critical operations when using tail sampling.
- Retain security audits as required; do not equate audit logs with debug logs.
- Sample debug logs at the source when volume is high.
- Do not sample SLI metrics in a way that distorts the denominator.

### 12.2. Retention Tiers

| Data | Example Retention Strategy |
|---|---|
| High-cardinality debug logs | Short, sampled, and restricted access |
| Application error/security logs | Based on operational needs and policy |
| Audit events | Based on legal/contractual requirements and tamper protection |
| High-resolution metrics | Shorter; downsample for long-term storage |
| Aggregated metrics/SLO history | Longer for trend analysis |
| Traces | Sampling/retention based on error, latency, and purpose |

These are tiering principles, not universal day-count recommendations. Each organization must agree on retention and deletion policies.

### 12.3. Reducing Cost Without Losing Investigation Capability

- Reduce cardinality and drop unused attributes.
- Standardize route/service naming.
- Separate debug, operational, and audit data.
- Use targeted sampling.
- Compress/batch telemetry.
- Downsample older metrics.
- Choose retention based on investigative value.
- Track cost per million spans/log records and query volume.

## 13. Dashboards and Runbooks

Dashboards should be organized around services and business journeys, not only infrastructure.

### 13.1. Recommended Dashboards

- **Service health:** request rate, error rate, p95/p99, saturation.
- **Dependencies:** latency/errors across databases, caches, queues, and providers.
- **Business flow:** bookings created/confirmed/failed, payments pending/unknown, cancellations.
- **Infrastructure:** CPU, memory, network, disk, connection pools, autoscaling.
- **Queues/workers:** backlog, oldest message age, retries, DLQ, processing latency.
- **Releases:** metrics by service version, deployment events, canary vs baseline.
- **Security:** denied access, unusual egress, auth failures, policy changes.
- **Telemetry pipeline:** dropped data, collector backlog, export failures, ingestion cost.

### 13.2. Runbooks

A runbook should document:

1. What the alert means and potential user impact.
2. Relevant dashboards, trace queries, and log filters.
3. Likely causes and how to distinguish between them.
4. Safe mitigation actions: rollback, scale, failover, rate limit, or disable feature.
5. Actions that must NOT be taken because they could lose data or bypass security.
6. Conditions to verify recovery.
7. When to escalate to the owner, provider, or security team.

Runbooks should be tested through incident drills; outdated documentation becomes a source of slower incident response.

## 14. Testing Telemetry as a System Feature

Do not just test that the application runs; verify that telemetry reaches the backend, is queryable, and contains no sensitive data.

### 14.1. Instrumentation Tests

- Create-booking requests carry a trace ID across the gateway and services.
- Error logs correlate properly to the trace/span.
- Metric labels use route templates, not unique IDs.
- Deployment events include service/version/environment.
- Async consumers receive propagated context or appropriate links.
- Collector export and backend ingestion work end-to-end.

### 14.2. Testing When the Telemetry Backend Fails

- Shut down the log backend and observe whether the app blocks.
- Slow down the trace exporter to verify queues/buffers.
- Restart the collector to test retries and data loss behavior.
- Generate high-volume traffic to test memory/cardinality limits.
- Verify business requests remain within SLO when the observability backend is degraded.
- Verify alerts fire for telemetry loss/drops.

### 14.3. Privacy/Security Tests

Send requests containing fake secrets/PII and verify redaction across logs, traces, events, exceptions, and collectors. Use an unauthorized role to attempt querying another tenant's telemetry; access must be denied.

## 15. Reference Architecture for BookingCloud

~~~mermaid
flowchart TB
    subgraph WORKLOAD["Production workloads"]
      GW["API gateway"]
      BOOK["Booking service"]
      INV["Inventory service"]
      PAY["Payment service"]
      WORK["Workers"]
      DB[("Databases / cache / queue")]
    end
    GW --> BOOK
    BOOK --> INV
    BOOK --> PAY
    BOOK --> DB
    INV --> DB
    WORK --> DB
    GW --> COL["OTel node/sidecar collectors"]
    BOOK --> COL
    INV --> COL
    PAY --> COL
    WORK --> COL
    DB --> INFRA["Cloud integration / exporters"]
    INFRA --> COL
    COL --> GATE["Collector gateway tier"]
    GATE --> L["Log backend"]
    GATE --> M["Metrics backend"]
    GATE --> T["Trace backend"]
    GATE --> E["Event/audit store"]
    L --> OPS["Dashboards / alerting / on-call"]
    M --> OPS
    T --> OPS
    E --> OPS
~~~

This design allows telemetry to be standardized and processed before being routed to signal-specific backends. The pipeline needs dedicated network paths, identity, TLS, buffers, quotas, and its own observability.

## 16. Well-Architected Review

| Pillar | Review Questions | Required Evidence |
|---|---|---|
| **Operational Excellence** | Does telemetry help on-call engineers find root causes and act quickly? | Dashboards, runbooks, trace/log correlation, incident drills |
| **Security** | Do logs/traces contain secrets/PII? Who can query or export them? | Redaction tests, RBAC, audits, retention, and tenant isolation |
| **Reliability** | Does collector/backend disconnection impact the application? | Bounded buffers, drop metrics, HA, pipeline failure tests |
| **Performance Efficiency** | Do instrumentation and exporters add excessive latency/CPU/memory? | Overhead benchmarks, sampling, batching, cardinality control |
| **Cost Optimization** | Along which dimensions do ingestion, indexing, storage, query, and egress grow? | Cost per signal/tenant/service, retention, sampling reports |
| **Sustainability** | Is redundant telemetry being collected or raw data kept longer than needed? | Data inventory, downsampling, lifecycle, dropped-unused-field reviews |

Good observability is not collecting the maximum possible amount of data. It is collecting enough signals to answer critical questions safely, reliably, and at controllable cost.

## 17. Lab: Designing Observability for the Create-Booking Flow

BookingCloud has a POST create-booking request passing through the API gateway, Booking service, Inventory service, Payment service, and notification queue. Recently p95 latency increased and some requests timed out, but the dashboard only shows CPU and total request count.

Perform the following:

**Exercise 1 — Service map:** diagram the synchronous and asynchronous request flows; list services, datastores, external dependencies, and owners.

**Exercise 2 — Log schema:** propose JSON logs for booking create success/failure containing service/version, trace ID, request ID, operation name, error code, and duration; exclude secrets/PII.

**Exercise 3 — Metrics:** select RED metrics for each service, USE metrics for databases/queues/caches, and business metrics for booking success/pending/failed.

**Exercise 4 — Traces:** describe spans and parent-child relationships from the gateway to Inventory, Payment, and the database; propagate context through the notification queue.

**Exercise 5 — Events:** select events for deployments, payment outcomes, and booking state transitions; define schema/version/owner.

**Exercise 6 — SLI/SLO:** define success rate, latency, and queue processing freshness with clear numerators/denominators.

**Exercise 7 — Alerts/runbook:** create symptom-based alerts for declining booking success and rising p95 latency; link to dashboards, traces, logs, and deployment events.

**Exercise 8 — Privacy/cost:** choose sampling, cardinality, retention, redaction, and access policies.

**Exercise 9 — Failure test:** shut down the telemetry backend, simulate an Inventory outage, and verify the application is not blocked by the logging pipeline.

### Self-Check Results Framework

| Current Problem | Signals Needed | Possible Actions |
|---|---|---|
| Only seeing CPU and request count | RED, USE, p95/p99 | Isolate affected service/resource |
| Unknown which service is slow | Distributed traces | Find the span with high latency |
| Logs not linked to requests | trace_id/request_id | Open logs from the trace |
| Unknown if a release caused errors | Deployment/config events + version metrics | Rollback/canary analysis |
| Queue is delayed | Oldest message age, consumer lag | Scale consumers or investigate poison messages |
| Telemetry is expensive | Cardinality/ingestion/retention metrics | Reduce labels and apply appropriate sampling |
| Logs contain PII | Redaction and access audits | Mask data, restrict permissions, enforce retention |

The results must demonstrate that operators can move from an alert to related traces/logs and identify remediation steps, while telemetry neither leaks data nor noticeably impacts workloads.

## 18. Production Readiness Checklist for Observability

- [ ] Service map, owners, and dependencies are defined.
- [ ] Logs are structured with standardized timestamps and consistent severities.
- [ ] Metrics cover RED for services and USE for critical resources.
- [ ] Cardinality is controlled; no unique IDs in metric labels.
- [ ] Trace context is propagated across HTTP and message queues.
- [ ] Spans represent key operations/dependencies; sampling is intentional.
- [ ] Events/audits have defined schemas, owners, retention, and delivery semantics.
- [ ] Logs, metrics, traces, and events correlate via trace ID, request/correlation ID, service, and version.
- [ ] SLIs/SLOs have clear numerators/denominators, windows, and exclusion policies.
- [ ] Alerts have owners, severities, dashboards, and runbooks.
- [ ] Collectors/exporters have bounded buffers, bounded retries, and drop metrics.
- [ ] Telemetry backend failures do not block business requests.
- [ ] Secrets/PII are redacted; access control and tenant isolation are tested.
- [ ] Retention, region/data residency, and deletion policies are approved.
- [ ] Dashboards exist for the telemetry pipeline itself and ingestion costs.
- [ ] Instrumentation, privacy, sampling, outages, and overhead have been tested.

Logs provide event details; metrics reveal trends and impact; traces pinpoint the path and time spent across each component; events record meaningful changes. When standardized, correlated, and operated alongside SLIs/SLOs, these four signals form the foundation that enables teams to understand system state, respond quickly, and improve cloud architecture based on evidence.
