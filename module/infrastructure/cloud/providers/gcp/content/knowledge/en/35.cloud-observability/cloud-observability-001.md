# Cloud Observability and Workload Telemetry Design

In the `CLOUD_PROVIDERS_GCP` module, you explore Google Cloud from project organization, IAM, and VPC to Compute Engine, GKE, Cloud Run, storage services, and databases. Deployment scenarios help you choose services, protect resources, automate releases, and track reliability and cost. The **Cloud Observability** chapter brings those operational capabilities into a unified workflow: generating telemetry from workloads, collecting and storing data, detecting signs of degradation, and tracing root causes to the right component.

This lesson guides you through designing telemetry for applications running on Google Cloud. You will distinguish between metrics, logs, and traces; use OpenTelemetry to standardize instrumentation; choose a collection approach suited to Compute Engine, GKE, and Cloud Run; and build dashboards, SLIs/SLOs, and actionable alerts.

## 1. What is Observability and What Problems Does It Solve?

Observability is the ability to infer the internal state of a system from the data it emits. Monitoring typically focuses on tracking known metrics and conditions, such as CPU exceeding 90% or an increasing error rate. Observability also enables investigating unforeseen situations by combining multiple signals, following a request across services, and asking new questions of the collected data.

Telemetry is the data generated while applications and infrastructure operate. The three most common signal groups are metrics, logs, and traces:

| Signal | Description | Questions Answered |
| --- | --- | --- |
| **Metrics** | Numeric data aggregated over time, typically with a metric name, labels, timestamp, and value. | How healthy is the system? Is the trend changing? |
| **Logs** | Event records with a timestamp and detailed content. | What happened at a specific point in time? |
| **Traces** | The path of a request across components; each trace consists of multiple spans representing individual operations. | Where did the request go, and which component consumed the time? |

The three signals complement one another. A metric shows that a service's error rate rose from 0.2% to 8%; a trace reveals that most of the wait time occurred in a database call; and the log for the corresponding span provides the error code or business context needed to pinpoint the cause. Relying on a single signal is often insufficient to reach a conclusion.

Beyond these three signals, **profiling** measures CPU and memory consumption by function or code segment. Error Reporting groups application errors so operators can track recurring failures. These are supporting tools in the root-cause investigation process.

### 1.1. Questions to Answer During Design

Start from how users experience the service, then choose what data to collect:

- Can users invoke critical functionality?
- How long do requests take at the median and in the tail of the distribution (p95, p99)?
- How are error, retry, and timeout rates changing?
- Is the service exhausting CPU, memory, connection pools, workers, or queue capacity?
- When a service is slow, which downstream dependency is causing the latency?
- Does a new release increase errors, latency, or cost per request?

For HTTP services, the four golden signals commonly used are **latency, traffic, errors, and saturation**. For background workers, add queue depth, oldest message age, consumer lag, retries, and dead-letter count. For databases, track connection pool usage, transaction latency, lock waits, connection count, and storage capacity.

## 2. Designing Telemetry for Workloads

Good design starts with a consistent telemetry contract. This contract defines service names, environments, versions, resources, log formats, metric names, span attributes, and how trace context is propagated across components.

### 2.1. Defining Service Identity

Every signal should clearly describe which service and version emitted it. With OpenTelemetry, commonly useful resource attributes include:

| Attribute | Example | Purpose |
| --- | --- | --- |
| `service.name` | `orders-api` | Stable name of the service. |
| `service.namespace` | `commerce` | Group or business domain containing the service. |
| `service.version` | `2026.11.19-4f2a1c` | Distinguishes releases. |
| `deployment.environment.name` | `production` | Distinguishes production, staging, and development. |
| `cloud.region` | `asia-southeast1` | Identifies the deployment region. |
| `k8s.namespace.name` | `commerce-prod` | Identifies the Kubernetes namespace. |
| `k8s.deployment.name` | `orders-api` | Identifies the Kubernetes workload. |
| `host.name` | `orders-vm-01` | Identifies the host when running on a VM. |

Use consistent spelling for service name, environment, and version across metrics, logs, and traces. When comparing an old version against a new version, you can filter the same dashboard by `service.version`.

Do not put per-request changing information into resource attributes. A resource describes where telemetry originates; values such as request ID or trace ID belong to individual log entries or spans.

### 2.2. Choosing Metrics That Reflect Service Health

Metrics should measure what users or dependent systems actually care about. A basic metric set for an API might include:

| Metric | Suitable Data Type | Usage |
| --- | --- | --- |
| Total requests | Counter | Measure traffic and calculate error rates. |
| Succeeded/failed requests | Counter or categorized by result code | Track availability and errors by endpoint or business group. |
| Request duration | Histogram | Compute p50, p95, p99 and build latency SLIs. |
| In-flight requests | Gauge | Detect abnormal spikes in concurrency. |
| CPU and memory | Gauge | Monitor resource utilization. |
| Queue depth and oldest message age | Gauge | Detect workers falling behind incoming work. |
| Retries and dead-letter count | Counter | Detect dependency failures or unprocessable messages. |
| Connection pool used/available | Gauge | Detect connection exhaustion risk. |

For counter metrics, values generally increase monotonically; the query system computes the rate of increase over a time window. Histograms preserve the observed distribution, making them better suited than averages for evaluating tail latency. Gauges represent a value at the time of measurement, such as the number of pending messages.

Do not monitor only CPU and memory. A service can have low CPU utilization and still fail to serve requests because it is waiting on a database, out of connection pool slots, or hitting concurrency limits. Place metrics where users perceive service quality and at resources that can become bottlenecks.

### 2.3. Writing Structured Logs

Use JSON-structured logs instead of hard-to-parse plain text strings. Each entry should include a timestamp, severity, message, service name, environment, version, and request-relevant attributes. Emit one event per entry so Cloud Logging can filter by fields.

Example of a JSON log linked to a trace:

~~~json
{
  "severity": "ERROR",
  "message": "Payment authorization timed out",
  "service": "checkout-api",
  "environment": "production",
  "service_version": "2026.11.19",
  "request_id": "req-7f13",
  "logging.googleapis.com/trace": "projects/PROJECT_ID/traces/TRACE_ID",
  "logging.googleapis.com/spanId": "SPAN_ID",
  "logging.googleapis.com/trace_sampled": true,
  "http": {
    "request_method": "POST",
    "status_code": 504
  },
  "dependency": "payment-provider"
}
~~~

The special fields `logging.googleapis.com/trace`, `logging.googleapis.com/spanId`, and `logging.googleapis.com/trace_sampled` allow Cloud Logging to link the log entry with the corresponding trace and span. When using a Logging client library or OpenTelemetry context, the library can populate these correlation fields automatically.

A good log describes a meaningful event: a request timeout, retries exceeding a threshold, a circuit breaker changing state, a database connection failure, or a rejected transaction. Avoid logging entire request/response bodies solely for debugging convenience. Never log access tokens, passwords, secret keys, cookies, payment details, or unnecessary personal data. If a business identifier must be logged, use a controlled ID and restrict log read permissions.

### 2.4. Creating End-to-End Request Traces

A trace represents the complete journey of a request. The root span represents the incoming request; child spans can represent database queries, HTTP calls to other services, cache operations, or message processing.

Example of a checkout flow:

~~~text
checkout-api (root span)
  ├── validate-cart
  ├── inventory-api
  │     └── inventory-db-query
  ├── payment-api
  │     └── payment-provider-request
  └── publish-order-event
        └── orders-worker (consumer span)
~~~

Each span should have a short operation name, start/end timestamps, status, and attributes needed for analysis. Do not include unique user or request IDs in span names; high-cardinality span names make data difficult to group and analyze.

To prevent traces from breaking at service boundaries, applications must propagate trace context via HTTP headers or message metadata. OpenTelemetry supports the W3C Trace Context propagator; the standard header is `traceparent`. When one service calls another, the new span must retain the same trace ID and reference the appropriate parent span. For asynchronous processing via Pub/Sub or queues, attach context to message metadata and restore context in the consumer if the library or platform does not do so automatically.

Not every Google Cloud service initiates or propagates trace context in the same way. Verify the capabilities of each component along the path. Cloud Trace stores and displays traces; context propagation is the responsibility of the application, instrumentation libraries, or intermediate services.

## 3. OpenTelemetry and Telemetry Collection Architecture

OpenTelemetry (OTel) is an open-source, vendor-neutral set of APIs, SDKs, instrumentation libraries, and collection tools. It enables applications to emit metrics, logs, and traces using a consistent model. OTLP (OpenTelemetry Protocol) is the protocol for transmitting telemetry between applications, collectors, and backends.

### 3.1. Components in the Pipeline

An OTel pipeline typically includes the following components:

- **Instrumentation:** libraries or agents that generate telemetry from frameworks, HTTP clients, database clients, and business code.
- **SDK:** manages providers, processors, samplers, and exporters within the application process.
- **Exporter:** sends signals from the SDK to a destination, typically over OTLP.
- **Collector:** a process that receives, processes, and forwards telemetry. A collector can receive from multiple workloads and export to one or more backends.
- **Backend:** the system that stores, queries, visualizes, and alerts on data, such as Cloud Logging, Cloud Monitoring, and Cloud Trace.

The collector can perform batching, enrich resource attributes, filter data, limit memory usage, transform formats, or route to multiple backends. A collector configuration requires receivers, processors, exporters, and service pipelines corresponding to each signal.

Overview diagram of a telemetry pipeline:

~~~mermaid
flowchart LR
  subgraph W[Workload]
    APP[Application + OpenTelemetry SDK]
    LOG[Structured logs stdout/stderr]
  end
  APP -->|OTLP| COL[Collector / Agent / Sidecar]
  LOG --> CL[Cloud Logging]
  COL --> CL
  COL --> CM[Cloud Monitoring]
  COL --> CT[Cloud Trace]
  CL --> ER[Error Reporting]
  CL --> VIEW[Dashboards and alerting]
  CM --> VIEW
  CT --> VIEW
  CP[Cloud Profiler] --> VIEW
~~~

### 3.2. Two Ways to Send Telemetry to Google Cloud

| Delivery Method | Data Flow | When to Use |
| --- | --- | --- |
| Collector-based export | Application OTel SDK → OTLP → OTel Collector → Google Cloud | Environments capable of running a collector; need filtering, centralized processing, retry management, and keeping application code backend-neutral. |
| Direct export | Application OTel SDK → Telemetry API | Environments where running a separate collector process is inconvenient, or small workloads requiring simple configuration. |

Google recommends using a collector when the deployment environment supports it. When a collector is not practical, you can export directly from the application process. Using OTLP keeps application instrumentation more neutral; when changing backends, you can update the collector or exporter configuration without rewriting all measurement logic.

### 3.3. Configuring OpenTelemetry with Environment Variables

Standard OpenTelemetry environment variables allow applying the same configuration pattern across multiple languages. Illustrative example:

~~~bash
OTEL_SERVICE_NAME=orders-api
OTEL_RESOURCE_ATTRIBUTES=service.namespace=commerce,deployment.environment.name=production,service.version=2026.11.19
OTEL_EXPORTER_OTLP_ENDPOINT=http://OTEL_COLLECTOR_HOST:4318
OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf
OTEL_PROPAGATORS=tracecontext,baggage
~~~

Replace `OTEL_COLLECTOR_HOST` with the actual collector endpoint. The SDK must be initialized and framework instrumentation enabled; setting environment variables alone does not automatically generate all business spans. Verify that the exporter, protocol, and endpoint are supported by the SDK in use. If the collector requires authentication or TLS, configure credentials according to your environment's guidelines.

For Java applications, you can start with the OpenTelemetry Java agent to auto-instrument common frameworks, then add manual spans for critical business steps. For other languages, select the corresponding SDK/agent and check the list of auto-instrumented libraries. Avoid creating manual spans for every small function; focus on service boundaries, dependency calls, and meaningful business operations.

## 4. Choosing a Collection Strategy by Google Cloud Platform

Each platform handles agents, sidecars, and background processes differently. Choose a pipeline based on workload lifecycle, signal types, and required level of control.

### 4.1. Compute Engine

On VMs, **Ops Agent** is the primary choice for collecting OS logs and metrics, along with telemetry from applications and third-party software via configured receivers. For applications needing distributed tracing or custom metrics, instrument with the OpenTelemetry SDK and send OTLP to the Ops Agent receiver or an appropriate collector.

A common deployment pattern:

1. Install Ops Agent on VMs using management policies or automation tools.
2. Configure the application to write JSON logs to a file readable by the agent.
3. Use the OpenTelemetry SDK to generate metrics and traces for requests and dependencies.
4. Configure the OTLP receiver on the agent/collector and grant permissions to write telemetry to the project.
5. Verify VM metrics in Cloud Monitoring, logs in Logs Explorer, and traces in Cloud Trace.

If you only need Prometheus-format metrics, Ops Agent includes a Prometheus receiver to scrape application or exporter endpoints. Avoid installing multiple overlapping agents on the same VM, as this can cause duplicate collection, consume extra resources, and make data sources harder to identify.

### 4.2. Google Kubernetes Engine (GKE)

GKE automatically collects application logs written to `stdout` and `stderr`; therefore, prefer single-line JSON logs. For Prometheus metrics, Google Cloud Managed Service for Prometheus provides PromQL-compatible metric storage and querying. Managed collection reduces the operational overhead of running Prometheus collectors, including deployment, scaling, and sharding configuration.

If your applications already use OpenTelemetry, you can deploy **Managed OpenTelemetry for GKE**. This feature provides an in-cluster collector to receive OTLP traces, metrics, and logs; workloads still need to be instrumented and configured to send telemetry to the endpoint. The default OTLP HTTP and gRPC endpoints are documented for GKE as follows:

~~~text
OTLP/HTTP: http://opentelemetry-collector.gke-managed-otel.svc.cluster.local:4318
OTLP/gRPC: http://opentelemetry-collector.gke-managed-otel.svc.cluster.local:4317
~~~

Managed OpenTelemetry for GKE can use the `Instrumentation` resource to automatically configure compatible workloads. If you need custom filtering, transformation, or routing rules for telemetry, consider the Google-Built OpenTelemetry Collector. For Prometheus metrics, choose Managed Service for Prometheus and a collection method compatible with existing exporters.

In GKE, attach resource attributes such as cluster, namespace, workload, and container to distinguish data across environments. When a Pod is replaced, service identity and version must still enable operators to identify which workload is emitting telemetry.

### 4.3. Cloud Run

Cloud Run automatically collects container logs written to `stdout` and `stderr`. The service also generates traces for incoming/outgoing HTTP request latency. If you need detailed traces inside the application, instrument with OpenTelemetry to create custom spans and propagate context to downstream services.

For custom telemetry:

- Use the OpenTelemetry SDK and an OpenTelemetry sidecar to collect OTLP metrics and traces.
- If the application exposes Prometheus-format metrics, use the Prometheus sidecar for Cloud Run.
- If a collector runs in the background to export telemetry, check CPU allocation mode and instance-based billing configuration per Cloud Run guidelines; background processes need CPU to continue processing after a request completes.
- Monitor log, metric, and trace ingestion costs as instance counts or sampling rates increase.

For Cloud Run functions, collection behaves somewhat differently: `stdout`/`stderr` logs are collected automatically; you can use log-based metrics when custom metrics are needed, as direct metric writing is not supported under current instrumentation guidelines for Cloud Run functions.

### 4.4. Quick Selection Table

| Environment | Logs | Metrics | Traces |
| --- | --- | --- | --- |
| Compute Engine | JSON file + Ops Agent | Ops Agent, Prometheus receiver, or OTel | OTel SDK → Ops Agent/collector OTLP receiver |
| GKE | JSON `stdout`/`stderr` collected by platform | Managed Service for Prometheus or OTel Collector | Managed OpenTelemetry for GKE or Google-Built OTel Collector |
| Cloud Run | JSON `stdout`/`stderr` collected by platform | OTel sidecar or Prometheus sidecar | Platform HTTP traces and OTel custom spans/sidecar |

These are common deployment patterns, not an exhaustive list. Verify runtime, SDK, agent version, and signal type capabilities before finalizing your architecture.

## 5. Using Google Cloud Observability Services

Google Cloud provides integrated services to store, query, visualize, and alert on telemetry.

| Service | Role | Common Tools |
| --- | --- | --- |
| **Cloud Logging** | Collects, stores, queries, and analyzes logs; supports log-based metrics, log-based alerts, and log routing. | Logs Explorer, Log Analytics, log buckets, sinks. |
| **Cloud Monitoring** | Collects and queries metrics; monitors resources, builds dashboards, and triggers alerts. | Metrics Explorer, dashboards, alerting policies, uptime checks. |
| **Cloud Trace** | Displays traces and analyzes per-span latency in distributed requests. | Trace Explorer, trace waterfall, trace scope. |
| **Error Reporting** | Detects and groups errors from logs to track error frequency and history. | Error groups and error list in Console. |
| **Cloud Profiler** | Collects CPU and memory allocation profiles with low overhead to locate resource-intensive code. | Time-series profiles and flame graphs. |
| **Managed Service for Prometheus** | Collects, stores, and queries Prometheus-model metrics. | PromQL, exporters, managed collection. |

### 5.1. Cloud Logging

Cloud Logging automatically collects logs from many Google Cloud resources; applications, on-premises systems, and other cloud environments can also send logs to a project. Use Logs Explorer to filter by resource, severity, service, timestamp, and JSON fields.

Example query for Cloud Run error logs:

~~~text
resource.type="cloud_run_revision"
severity>=ERROR
resource.labels.service_name="checkout-api"
~~~

Example query for logs containing a specific request ID:

~~~text
resource.type="cloud_run_revision"
jsonPayload.request_id="req-7f13"
~~~

Adapt resource types and fields to your actual platform and log schema. For structured logs, filter by specific fields rather than searching free-form strings across the entire payload.

Log sinks route logs to another log bucket, a centralized monitoring project, BigQuery, Cloud Storage, or Pub/Sub depending on your goal. Before creating a sink, determine which logs require long-term storage, who has read access, how long retention should be, and whether the destination has appropriate permissions.

### 5.2. Cloud Monitoring

Cloud Monitoring stores time series and provides Metrics Explorer, dashboards, alerting policies, uptime checks, and SLO monitoring. Use dashboards to place related indicators side by side, such as request rate, error rate, p95 latency, CPU, memory, and queue depth.

Metric-based alerts fit numerical trends and sustained conditions. Log-based alerts fit significant single events appearing in logs, such as a circuit breaker opening or a recovery job failing. SQL-based alerts fit complex patterns requiring aggregation across multiple log entries. Choose the alert type based on the operational question; every alert must have an owner, severity level, next action, and runbook link.

### 5.3. Cloud Trace and Log-Trace Correlation

Trace Explorer displays traces as waterfalls, helping pinpoint slow spans and latency-inducing dependencies. When log entries contain matching trace and span ID fields, you can open logs directly from a trace or view related logs in Logs Explorer.

For logs to be linked, entries must share the same trace resource and have matching timestamps. When using OpenTelemetry, ensure logs are emitted within a span context so trace ID and span ID are attached to the log record. Correlation shifts the workflow from "which request was slow?" to "which database query slowed down that request?" without manually searching through multiple log files.

### 5.4. Error Reporting and Cloud Profiler

Error Reporting analyzes logs to detect and group errors. When an error group spikes after a release, compare the error start time, version, and stack trace against deployment events.

Cloud Profiler collects CPU and memory allocation data to identify functions or code paths consuming resources. Use the profiler after metrics or traces indicate a performance issue that requires code-level investigation. Traces tell you which step of a request is slow; profiles help find what code is consuming resources during that step.

## 6. Designing SLIs, SLOs, and Alerts

Telemetry delivers value when turned into operational decisions. An SLI is an indicator measuring service quality; an SLO is the target goal for an SLI over a period of time; an error budget is the allowable margin of error before violating the SLO.

### 6.1. Choosing User-Experience SLIs

Two fundamental SLIs for APIs are availability and latency:

- **Availability SLI:** count of good requests divided by total valid requests.
- **Latency SLI:** count of requests completed below a latency threshold divided by total measured requests.

Example objectives for a checkout service:

- Availability: at least 99.9% of valid requests succeed over a 30-day window.
- Latency: at least 95% of requests complete under 300 ms over the same window.

These are examples illustrating how to write SLOs; actual thresholds should be based on user needs, baselines, and service commitments. Do not use CPU directly as a user-experience SLI when request success and latency can be measured.

### 6.2. Calculating the Error Budget

With a 99.9% availability SLO, the allowable rate of bad requests is:

\[
1 - 0.999 = 0.001 = 0.1\%
\]

If there are 1,000,000 valid requests in the window, the corresponding error budget is:

\[
1,000,000 \times 0.001 = 1,000 \text{ requests}
\]

Error budgets help development and operations teams weigh release risk. If the budget is burning quickly, teams can slow down change velocity and prioritize reliability work. A 100% SLO leaves zero error budget and is rarely a practical operational target.

### 6.3. Creating Actionable Alerts

Alerts should focus on user-impacting symptoms and error budget burn rate. Examples:

| Condition | Alert Objective | Suggested Action |
| --- | --- | --- |
| Rapid error budget burn | Detect services at risk of breaching SLO. | Check error rate, version, and dependencies. |
| Sustained p95 latency above target | Detect experience degradation. | Open sample traces and locate slow spans. |
| Sudden spike in HTTP 5xx | Detect request failures. | Group errors by route, version, and downstream service. |
| Rising queue age or consumer lag | Detect workers falling behind. | Check worker count, retries, and dependencies. |
| Disk nearly full or steady memory growth | Detect resource exhaustion risk. | Determine growth rate, remaining capacity, and scaling plan. |
| Missing telemetry for expected duration | Detect broken agent or collection pipeline. | Check collector, IAM permissions, endpoint, and exporter. |

Do not alert on every isolated error if no action is required. Group alerts by service and root cause, set evaluation durations long enough to avoid noise, and route to the appropriate on-call notification channel. Alerts without clear remediation steps lead to alert fatigue.

## 7. Controlling Telemetry Quality, Cost, and Security

Telemetry volume can grow rapidly with traffic, service count, label count, and retention duration. Designing upfront keeps data useful without creating an operational burden.

### 7.1. Controlling Cardinality

Cardinality is the number of distinct time series generated by a metric and its label set. Putting `user_id`, `request_id`, email, or full URLs into metric labels can cause time series counts to explode. Use metric labels with bounded value sets, such as method, route template, status class, region, or service version.

For request ID, trace ID, and user ID, store them in logs or traces when there is a valid reason and enforce access controls. Do not turn unique identifiers into metric labels.

### 7.2. Reducing Cost While Preserving Investigation Capability

- Use trace sampling for high-traffic workloads; ensure all services participating in a request respect the sampling context.
- Create detailed spans only at business boundaries or dependencies requiring analysis.
- Use appropriate histograms and limit metric labels.
- Set log bucket retention based on operational and audit needs; route long-term logs to appropriate storage.
- Monitor log ingestion volume, trace span counts, and metric time series counts.
- Remove repetitive debug logs or telemetry with no investigative value after assessing impact.

Cloud Trace supports sampling on the data-sending components. Cloud Trace does not perform tail-based sampling natively; if you need sampling decisions made after seeing the entire trace, use an intermediate collector with a Tail Sampling Processor and ensure spans sharing a trace ID reach the same collector. Sampling and context propagation are distinct concerns: sampling decides whether to record spans, while propagation links spans across services.

Never drop security logs, audit logs, or mandatory compliance records solely to cut costs. Maintain retention policies and access controls aligned with organizational requirements.

### 7.3. Protecting Telemetry Data

- Never log or attach secrets, tokens, passwords, private keys, cookies, or sensitive personal data to logs/spans.
- Redact or mask sensitive fields before export; do not rely on log readers to manually ignore sensitive values.
- Grant least-privilege IAM permissions for viewing logs, metrics, and traces; separate pipeline administration from query permissions.
- Protect collector endpoints using network controls, authentication, and TLS appropriate to your deployment architecture.
- Govern log sinks, buckets, retention, and centralized storage projects.
- Include telemetry configuration in code review and deployment workflows just like application config.

### 7.4. Multi-Project Observability

For systems spanning multiple projects, use observability scopes to view telemetry centrally. Google Cloud Application Monitoring can display logs, metrics, and traces for App Hub applications across projects via log scopes, metrics scopes, and trace scopes. Configure IAM permissions for operators and clearly define which project serves as the querying or management hub.

Organizing data by application/service ensures dashboards, alerts, and runbooks reflect actual operational structure rather than merely project boundaries.

## 8. Real-World Scenario: Investigating a Slow Checkout API

Suppose users report that checkout takes 4 seconds while the p95 target is 300 ms. The system consists of Cloud Run `checkout-api`, GKE `inventory-api`, an external payment service, and Cloud SQL.

Investigate in sequence:

1. **Confirm impact scope:** Open the Cloud Monitoring dashboard and check request rate, error rate, p50/p95/p99 latency, and when the degradation began. Compare by `service.version` and environment to see if the issue started after a release.
2. **Find a representative trace:** Open Cloud Trace, filter by service and time range, and select a high-latency trace. Inspect the waterfall to identify the span consuming the most time.
3. **Inspect dependencies:** If the span calling `inventory-api` takes 3 seconds, inspect inventory's child spans, database queries, and connection pool behavior. If the payment span is slow, determine whether the delay comes from network wait, retries, or provider processing.
4. **Open related logs:** From the trace, open logs sharing the trace ID/span ID. Check timeouts, status codes, retry counts, and sanitized error details.
5. **Check resources:** Inspect CPU, memory, instance count, concurrency, queue depth, and connection pools. If the trace shows internal processing consuming CPU, use Cloud Profiler to locate resource-intensive functions.
6. **Evaluate recent changes:** Correlate the start time with releases, autoscaling configuration, database changes, quotas, or dependency incidents.
7. **Remediate and verify:** Deploy a controlled fix, then verify that p95, error rate, and error budget return to target levels. Update dashboards, alerts, and runbooks if gaps in telemetry were uncovered.

If a trace lacks downstream service spans, check context propagation across HTTP headers or message metadata. If logs do not appear alongside the trace, verify the trace/span fields in log entries. If metrics stop updating, check the collector, exporter, IAM permissions, endpoint, and quotas before concluding the workload has no activity.

## 9. Workflow for Implementing Observability on a New Workload

You can follow this sequence for a workload running on Google Cloud:

1. Identify critical functionality, dependencies, service owners, and SLIs to measure.
2. Standardize resource attributes, metric names, log schemas, and trace context.
3. Instrument the application with OpenTelemetry; enable auto-instrumentation for supported frameworks and add spans for critical business steps.
4. Choose a collector/agent for the environment: Ops Agent on VMs, Managed OpenTelemetry or Google-Built OTel Collector on GKE, sidecar or direct export on Cloud Run.
5. Emit structured logs and verify correlation across logs, metrics, and traces.
6. Build dashboards from user, dependency, and infrastructure perspectives.
7. Define SLIs/SLOs, error budgets, and alerting policies; add uptime checks or synthetic monitors for critical flows.
8. Grant least-privilege IAM, configure retention, control sensitive data, and monitor ingestion costs.
9. Run a controlled failure exercise to confirm operators can detect, investigate, and recover using the designed telemetry.

## 10. Telemetry Design Checklist

- [ ] Every workload has a stable `service.name`, environment, and version.
- [ ] Metrics measure traffic, latency, errors, and saturation alongside workload-specific signals.
- [ ] Histograms are used for latency distributions; metric label cardinality is controlled.
- [ ] Logs are JSON with severity, message, timestamp, and service metadata.
- [ ] Logs and traces are linked via trace ID/span ID when context is available.
- [ ] Trace context is propagated across HTTP and message metadata at service boundaries.
- [ ] Sampling is chosen based on traffic volume, cost, and investigation needs.
- [ ] The collector/agent fits the lifecycle of Compute Engine, GKE, or Cloud Run.
- [ ] Dashboards can answer questions about service health and dependencies.
- [ ] SLIs/SLOs reflect user experience and include an error budget.
- [ ] Alerts have owners, appropriate thresholds, notification channels, and runbooks.
- [ ] Telemetry contains no secrets or unnecessary personal data.
- [ ] Retention, IAM, log routing, and ingestion costs are governed.
- [ ] Detection, investigation, and post-remediation verification workflows have been tested.

## References

- [Google Cloud Observability overview](https://docs.cloud.google.com/stackdriver/docs/observability) — roles of Cloud Logging, Cloud Monitoring, Cloud Trace, and Error Reporting.
- [Observability in Google Cloud](https://docs.cloud.google.com/stackdriver/docs) — concepts of metrics, logs, traces, and combining telemetry.
- [Choose an instrumentation approach](https://docs.cloud.google.com/stackdriver/docs/instrumentation/choose-approach) — OpenTelemetry recommendations, collectors, and collection methods for GKE, Compute Engine, and Cloud Run.
- [Telemetry (OTLP) API overview](https://docs.cloud.google.com/stackdriver/docs/reference/telemetry/overview) — OTLP protocol and telemetry ingestion API.
- [Managed OpenTelemetry for GKE](https://docs.cloud.google.com/kubernetes-engine/docs/concepts/managed-otel-gke) — managed collector and OTLP endpoints for GKE.
- [Google Cloud Managed Service for Prometheus](https://docs.cloud.google.com/stackdriver/docs/managed-prometheus) — collecting Prometheus metrics in Kubernetes and other environments.
- [Cloud Trace overview](https://docs.cloud.google.com/trace/docs/overview) — trace explorer, instrumentation, and latency analysis.
- [Trace context](https://docs.cloud.google.com/trace/docs/trace-context) — propagating trace context across components.
- [Link log entries with traces](https://docs.cloud.google.com/trace/docs/trace-log-integration) — linking log entries with traces and spans.
- [Trace sampling](https://docs.cloud.google.com/trace/docs/trace-sampling) — sampling, quotas, and tail-based sampling.
- [Cloud Monitoring alerting overview](https://docs.cloud.google.com/monitoring/alerts) — metric-based, log-based, and SQL-based alerting.
- [SLO monitoring concepts](https://docs.cloud.google.com/stackdriver/docs/solutions/slo-monitoring) — SLIs, SLOs, and error budgets.
- [Cloud Profiler documentation](https://docs.cloud.google.com/profiler/docs) — CPU and memory allocation profiling.
- [Cloud Logging overview](https://docs.cloud.google.com/logging/docs/overview) — log collection, querying, storage, and routing.
