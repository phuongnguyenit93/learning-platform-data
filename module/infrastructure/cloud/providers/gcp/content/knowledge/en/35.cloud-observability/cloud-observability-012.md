# Cloud Trace and Distributed Tracing

In a multi-service system, a user request may pass through a load balancer, API gateway, Cloud Run or GKE, and then call databases, caches, and external services. When a request is slow or fails, logs from any single component usually reveal only part of the story. Distributed tracing stitches those operations into a single trace so operators can see the request's path, time spent at each step, and where latency occurs.

Cloud Trace is Google Cloud's service for ingesting, storing, and exploring traces. OpenTelemetry provides APIs, SDKs, and context propagation mechanisms so applications emit traces using a portable, cross-platform standard. Combining both enables development teams to trace applications running on Compute Engine, GKE, Cloud Run, and other GCP services.

Within **CLOUD_PROVIDERS_GCP**, distributed tracing adds a request-centric lens to operating projects, networking, workloads, storage, and databases. It helps pinpoint slow downstream dependencies, verify post-release impact, correlate logs and metrics, and evaluate system reliability and cost.

After this lesson, learners will be able to:

- Explain traces, spans, parent-child relationships, and trace context.
- Describe how trace context propagates across HTTP, RPC, queues, and asynchronous tasks.
- Instrument applications using the OpenTelemetry SDK or agent.
- Send traces from workloads to Cloud Trace via an exporter or OpenTelemetry Collector.
- Read waterfalls, spot slow spans, and link traces with logs.
- Choose sampling strategies, span attributes, and appropriate trace data protections.

## 1. What Problem Does Distributed Tracing Solve?

Logs typically describe a single event within one component: a request received, a database query failing, or a container throwing an exception. Metrics aggregate numbers over time: request rate, error rate, CPU, or latency percentiles. Traces answer a different question: **which components did a specific request pass through, and where was time spent?**

For example, an order API might call an inventory service, a payment service, and a database. The user experiences a 2.4-second request. Reading only the API's logs might show when the request started and ended, without clarifying which downstream service slowed it down. Traces show the child spans and their respective durations.

~~~mermaid
flowchart LR
    U[Client] --> G[HTTPS Load Balancer]
    G --> A[orders-api]
    A --> B[inventory-service]
    A --> C[payment-service]
    A --> D[Cloud SQL]
    B --> E[Inventory database]
    C --> F[Payment provider]
~~~

Each component can create one or more spans. When spans carry the same trace ID and connect via parent-child relationships or links, Cloud Trace renders them on a unified timeline.

Distributed tracing is especially valuable when:

- A request traverses multiple microservices or deployment regions.
- Latency climbs while CPU and memory on the entry service remain normal.
- A dependency such as a database, third-party API, or message broker responds slowly.
- Failures affect only specific requests, tenants, revisions, or code paths.
- A team needs to compare execution behavior before and after a deployment.

Tracing does not replace logs and metrics. Traces explain a request's path; logs store detailed event context; metrics reveal system-wide trends and impact magnitude.

## 2. The Trace and Span Model

### 2.1. Trace

A **trace** represents the journey of an operation across one or more components. A trace has a unique identifier called a trace ID. Spans belonging to the same trace assemble into the end-to-end picture.

A trace typically includes:

- Trace ID: trace identifier propagated across components.
- Root span: the top-level span representing the initial measured operation.
- Child spans: sub-operations such as HTTP calls, database queries, or business logic steps.
- Trace context: metadata needed for downstream components to continue the same trace.

Not every trace is complete. A service might lack instrumentation, context might be dropped across a queue, or sampling might discard part of a trace. Consider instrumentation coverage before concluding a dependency was not called.

### 2.2. Span

A **span** is a unit of work with a start time and end time. A span typically contains:

| Component | Meaning | Example |
|---|---|---|
| Name | Operation name | `POST /orders`, `inventory.lookup` |
| Start/end time | Execution interval | 10:15:03.120–10:15:03.185 |
| Trace ID | Trace the span belongs to | Shared ID for the request |
| Span ID | Unique identifier of the span | ID of the lookup operation |
| Parent span ID | Parent span if present | Span of `orders-api` |
| Attributes | Properties describing the operation | HTTP method, route, DB system |
| Events | Timestamped occurrences within the span | Retry, cache miss, exception |
| Status | Outcome of the span | OK or ERROR |
| Links | References to other span contexts | A consumer processing a batch of multiple messages |

A parent span normally brackets the duration of its child spans. Child spans can run sequentially or concurrently, so never blindly sum all span durations to infer total request duration. When calls execute in parallel, overall latency depends on the critical path and completion time of the slowest branch.

Example trace:

~~~text
Trace: create-order
└── HTTP POST /orders                 2,400 ms
    ├── inventory.lookup                180 ms
    │   └── SQL SELECT inventory         95 ms
    ├── payment.authorize              1,850 ms
    │   └── HTTP POST payment-provider 1,720 ms
    └── SQL INSERT order                 70 ms
~~~

In this example, calling the payment provider dominates the duration. Optimizing the INSERT query would not noticeably improve request latency; investigate the payment dependency first.

### 2.3. Attributes, Events, Status, and Links

- **Attributes** describe span context. Favor operationally meaningful attributes such as service name, normalized route, database type, HTTP status, and deployment version.
- **Events** record milestones inside a span, such as starting a retry or receiving a dependency response.
- **Status** indicates whether the span encountered an error. When catching an exception, record the error and set status appropriately if auto-instrumentation has not already done so.
- **Links** connect a span to one or more external span contexts without forcing a parent-child hierarchy. Links are helpful in batch processing or tasks triggered by multiple messages.

Never put passwords, tokens, sensitive request payloads, or personal data into attributes, events, or baggage. Avoid high-cardinality values like user IDs, emails, session IDs, or raw URLs with IDs as common tags. They complicate trace analysis and can increase costs or data exposure risk.

## 3. Trace Context and Cross-Service Propagation

For services to record spans under the same trace, they must propagate trace context across communication boundaries. If every service starts a brand-new trace, the UI displays disconnected fragments that are hard to tie back to the original request.

### 3.1. W3C Trace Context

OpenTelemetry supports the W3C Trace Context standard. The primary HTTP header is `traceparent`, structured as:

~~~text
traceparent: 00-<trace-id>-<parent-id>-<trace-flags>
~~~

Where:

- `trace-id` is 32 hex characters identifying the trace.
- `parent-id` is 16 hex characters identifying the calling span.
- `trace-flags` holds flags such as sampled state.
- `tracestate` is an optional header carrying vendor-specific key-value pairs per standard.

Illustrative example:

~~~http
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
tracestate: vendor=value
~~~

When service A calls service B, A's instrumentation injects context into headers. B's instrumentation extracts context, creating a new span with the same trace ID and A's span as its parent. This preserves causality across many services without manually passing trace IDs through every business function.

### 3.2. Legacy Google Cloud Header Compatibility

Some older components or systems may use the `X-Cloud-Trace-Context` header. Common format:

~~~text
X-Cloud-Trace-Context: TRACE_ID/SPAN_ID;o=TRACE_TRUE
~~~

This is a Google Cloud compatibility format. When integrating mixed systems, confirm proxies, gateways, and tracing libraries share compatible propagators or perform proper header translation. Do not assume every framework automatically translates between W3C Trace Context and legacy headers.

### 3.3. HTTP, RPC, and Message Queues

For HTTP or RPC, context is typically injected into request metadata/headers. For message queues, producers write trace context into message attributes or headers; consumers extract context when processing messages.

Cases requiring attention:

- **Synchronous HTTP:** the caller's client span and the callee's server span must connect via context.
- **Asynchronous tasks:** context must be preserved when dispatching work to executors, schedulers, or background workers.
- **Message queues:** context must travel with the message through the broker; queue wait time may need distinct representation from processing time.
- **Batch processing:** one batch may combine multiple messages with different trace contexts. Consider creating a new consumer span linked to the source contexts rather than arbitrarily picking one message as the parent.
- **Trust boundaries:** when accepting context from untrusted clients, evaluate whether to honor incoming context or start a fresh trace. Never use trace context for authentication or authorization.

OpenTelemetry provides propagators to inject and extract context. Use built-in framework instrumentation whenever available; write custom header handling only for proprietary protocols after testing compatibility.

## 4. Cloud Trace in the GCP Observability Architecture

Cloud Trace ingests traces from applications or collectors and provides an interface to inspect trace details, spans, and latency distributions. Applications must be instrumented and configured with an exporter; Cloud Trace cannot infer internal spans from an uninstrumented application.

~~~mermaid
flowchart LR
    A[Applications and libraries] --> B[OpenTelemetry API / SDK / Agent]
    B --> C[OTLP]
    C --> D[OpenTelemetry Collector]
    D --> E[Cloud Trace]
    A --> F[Cloud Logging]
    E --> G[Trace waterfall and latency analysis]
    F --> H[Log Explorer]
    G --> I[Correlate traces, logs, and metrics]
    H --> I
    J[Cloud Monitoring] --> I
~~~

Components:

1. **Instrumentation:** libraries or agents generating spans when the application handles requests, calls dependencies, or performs business work.
2. **OpenTelemetry SDK:** manages tracer providers, resources, processors, samplers, and exporters in-process.
3. **OTLP:** standard protocol for transmitting telemetry from SDKs to collectors or supported backends.
4. **OpenTelemetry Collector:** receives, batches, filters, or samples traces before exporting to backends. Collectors can also aggregate telemetry from multiple workloads.
5. **Cloud Trace:** stores and visualizes traces for searching and analysis.

A collector is not mandatory for every small architecture. Applications can export directly using compatible exporters. However, a collector decouples backend configuration from application code and centralizes authentication, batching, retries, sampling, and multi-source telemetry management.

### 4.1. Preparing the Project and Permissions

Before sending traces to Google Cloud:

1. Select the target project storing traces and identify the workload project if different.
2. Enable the Cloud Trace API on the trace-receiving project.
3. Grant the exporter or collector identity appropriate trace write permissions, typically `roles/cloudtrace.agent` on the target project.
4. Use Application Default Credentials (ADC), workload-attached service accounts, or Workload Identity; avoid storing long-lived JSON keys in images or source code.
5. Verify network egress and DNS along the telemetry delivery path if workloads run in restricted networks.

If the collector runs under its own service account, grant trace write permissions to the collector's identity. Do not confuse the application's business API permissions with the trace exporter's permissions.

### 4.2. Resource Attributes

Resource attributes describe where telemetry originates. Set at minimum:

| Attribute | Example | Purpose |
|---|---|---|
| `service.name` | `orders-api` | Identifies the service |
| `service.version` | `2026.11.19` | Compares releases |
| `deployment.environment.name` | `production` | Distinguishes environments |
| `service.namespace` | `commerce` | Groups services by business domain |
| `cloud.region` | `asia-southeast1` | Identifies execution region |
| `cloud.platform` | `gcp_cloud_run` or matching value | Describes hosting platform |

Values should reflect the real environment and follow semantic conventions supported by the OpenTelemetry version in use. Avoid naming the same workload differently across logs, traces, and metrics.

## 5. Instrumenting Applications with OpenTelemetry

There are two primary ways to create spans:

- **Automatic instrumentation:** agents or libraries automatically instrument HTTP frameworks, database clients, RPC, and common dependencies. This yields traces quickly with minimal source changes.
- **Manual instrumentation:** developers create spans around custom business operations to measure logic that auto-instrumentation does not understand.

Start with automatic instrumentation for popular frameworks, then add manual spans at valuable business boundaries. Creating excessive tiny spans for every internal helper function clutters traces and inflates volume.

### 5.1. Java Example Using the OpenTelemetry API

The snippet below demonstrates creating a span for an inventory lookup. The `tracer` variable comes from the initialized OpenTelemetry SDK in the application:

~~~java
Span span = tracer.spanBuilder("inventory.lookup").startSpan();

try (Scope scope = span.makeCurrent()) {
    span.setAttribute("inventory.region", region);
    span.setAttribute("inventory.source", "primary");

    return inventoryRepository.findBySku(sku);
} catch (RuntimeException exception) {
    span.recordException(exception);
    span.setStatus(StatusCode.ERROR, "inventory lookup failed");
    throw exception;
} finally {
    span.end();
}
~~~

Key points:

- `startSpan()` starts timing the operation.
- `makeCurrent()` binds the span to the active context so instrumented child calls inherit it as parent.
- `setAttribute()` attaches helpful investigative context.
- `recordException()` and `setStatus()` capture failures when exceptions cross the block.
- `end()` must run whether the operation succeeds or fails.

This is a condensed snippet; include appropriate imports, tracer initialization, and OpenTelemetry dependencies for your application. Do not put sensitive SKUs, customer info, or confidential data in span attributes without valid justification and controls.

### 5.2. Example Running the Java Agent

For Java applications using common frameworks, you can start with the OpenTelemetry Java agent to auto-instrument supported libraries:

~~~bash
java \
  -javaagent:/opt/opentelemetry-javaagent.jar \
  -Dotel.service.name=orders-api \
  -Dotel.resource.attributes=service.version=2026.11,deployment.environment.name=production \
  -Dotel.exporter.otlp.endpoint=http://otel-collector:4317 \
  -Dotel.exporter.otlp.protocol=grpc \
  -jar app.jar
~~~

This example assumes the collector is reachable at `otel-collector:4317` and accepts OTLP over gRPC. Adjust host, port, protocol, agent launch flags, and resource attributes for your environment. The application sends OTLP to the collector; the collector is configured with a Google Cloud exporter to ship traces to Cloud Trace.

### 5.3. Minimal OpenTelemetry Collector Configuration

Illustrative configuration for a collector distribution bundling an OTLP receiver and Google Cloud exporter:

~~~yaml
receivers:
  otlp:
    protocols:
      grpc:
        endpoint: 0.0.0.0:4317
      http:
        endpoint: 0.0.0.0:4318

processors:
  batch:

exporters:
  googlecloud:

service:
  pipelines:
    traces:
      receivers: [otlp]
      processors: [batch]
      exporters: [googlecloud]
~~~

The collector must run with an identity authorized to write traces and valid ADC. Some collector distributions do not bundle the `googlecloud` exporter; choose an appropriate distribution, verify components in your deployed version, and validate the configuration before release. In production, add memory limiters, retry/queue settings, TLS or OTLP auth, health checks, and monitoring for the collector itself.

## 6. Deploying Tracing Across GCP Services

### 6.1. Cloud Run

- Instrument the application with the OpenTelemetry SDK or agent.
- Set a stable `service.name` and include service version/revision to differentiate releases.
- Configure direct export or send OTLP to an appropriate sidecar/collector endpoint for your architecture.
- Grant Cloud Trace permissions to the identity actually exporting traces.
- Preserve trace context across outbound HTTP calls and background tasks.
- Combine traces with Cloud Run request logs to investigate the same request.

Cloud Run automatically provides some request metadata and platform logs, but internal application span detail depends on instrumentation. Never assume all database or HTTP client calls are traced without checking the corresponding libraries.

### 6.2. Google Kubernetes Engine

- Choose a collector deployment topology: sidecar, DaemonSet, or centralized gateway depending on workload density and network boundaries.
- Bind the collector's identity using Workload Identity for GKE or your organization's approved identity mechanism.
- Set resource attributes identifying cluster, namespace, workload, and service.
- Ensure Pods can reach the collector over OTLP and the collector can reach Google Cloud.
- Verify context propagation across service meshes, ingress, egress, and message brokers.
- Avoid double-instrumenting the same communication layer via both an agent and a library if it creates redundant spans.

For shared collectors, restrict who can send telemetry to the endpoint and protect it against unauthorized access. Tune batching, memory, and retries so the collector does not become a bottleneck under load.

### 6.3. Compute Engine

- Install OpenTelemetry Collector or run an exporter in the application.
- Use the VM-attached service account or a workload identity with trace write permissions.
- Allow egress to the collector or required telemetry endpoints per network policy.
- Set consistent service name, version, environment, and region attributes.
- Monitor the collector process, export queues, and telemetry export errors.

Do not grant VM admin permissions to an application just to write traces. Restrict Cloud Trace permissions to the identity performing exports.

## 7. Sampling and Managing Trace Volume

A system handling thousands of requests per second can generate massive span volumes. Sampling decides which traces are retained and sent to the backend, balancing observability, system overhead, and cost.

### 7.1. Head-Based Sampling

Head-based sampling makes the decision upfront, typically when the root span begins. For instance, a sampler selects a percentage of requests based on trace ID. Downstream services must honor the incoming sampling decision so traces do not break mid-flight.

Advantages:

- Simple to implement and reduces volume before spans are transmitted.
- Applied consistently across services when using a parent-based sampler.

Limitations:

- The decision is made before knowing whether the request will be slow or fail.
- An error trace can still be dropped if it was not sampled at the head.

### 7.2. Tail-Based Sampling

Tail-based sampling defers the decision until the collector receives part or all of a trace. The collector can prioritize retaining traces with errors, high latency, or specific inspection criteria.

The benefit is sampling based on final outcomes. In return, the collector must buffer traces in memory or queues for a window; under-provisioned collectors risk dropping data or adding latency.

Tail sampling must be designed into a supporting collector or pipeline; do not assume Cloud Trace automatically retains all spans before letting you sample arbitrarily.

### 7.3. Choosing a Sampling Policy

- Start with a rate high enough to validate instrumentation in dev/test environments.
- High-traffic production should tune rates based on volume, investigative goals, and budget.
- Consider prioritizing error or high-latency traces if using tail sampling.
- Retain a baseline fraction of successful traces for comparison.
- Ensure all services inherit sampling decisions when using head-based sampling.
- Monitor created spans, successfully exported spans, and exporter errors.

Sampling reduces visibility into rare requests. Never treat a single trace as proof that all other requests behave identically; combine traces with aggregate metrics and on-demand logs.

## 8. Reading Traces in Cloud Trace

When opening a trace in Cloud Trace, read top-down from the root operation to child spans.

1. **Identify the root span:** check operation name, service, timestamp, and total duration.
2. **Inspect the waterfall:** see which spans start, finish, and overlap in parallel; identify the critical path.
3. **Spot unusually long spans:** compare durations of HTTP clients, RPCs, database calls, and internal work.
4. **Inspect status and events:** check exceptions, retries, timeouts, or error attributes.
5. **Compare traces:** pick a fast successful trace and a slow trace under similar conditions to isolate differences.
6. **Correlate logs and metrics:** use trace ID, span ID, timestamp, and service name to open related logs; check metrics to gauge prevalence.

Common diagnostic patterns:

| Pattern in Trace | Possible Issue to Check |
|---|---|
| Long root span with no matching child spans | Missing instrumentation, unmeasured synchronous work, or internal blocking |
| One HTTP client span dominates duration | Remote dependency, DNS, TLS, retries, or timeouts |
| Multiple slow database spans | Query plan, connection pool, locks, I/O, or database load |
| Child span starts late | Queueing, thread pool saturation, scheduler delay, or resource contention |
| Trace split across multiple trace IDs | Lost context propagation or incompatible propagators |
| Span errored while outer request succeeded | Application retried or fell back; check final outcome and retry cost |
| Request trace missing altogether | Sampling, permissions, exporter, API config, or missing instrumentation |

Span duration can include network wait, queueing, or dependency time. A long span does not automatically prove that service's CPU is busy; cross-check metrics and operation type.

## 9. Linking Cloud Trace with Cloud Logging

When logs carry trace ID and span ID, operators can jump straight from a log entry to the matching trace. With structured logging, applications can emit Cloud Logging's special fields:

~~~json
{
  "severity": "ERROR",
  "message": "payment authorization failed",
  "logging.googleapis.com/trace": "projects/PROJECT_ID/traces/TRACE_ID",
  "logging.googleapis.com/spanId": "SPAN_ID",
  "logging.googleapis.com/trace_sampled": true
}
~~~

Trace and span values must be actual IDs from the active context. The trace field should follow the full project-qualified format shown above. When using a logging library or agent, prefer automatic integration rather than generating synthetic trace IDs that do not match active spans.

During investigation:

- From a log, grab the trace ID to open the trace.
- From a span, match the span ID to logs emitted during that operation.
- Use timestamp and request ID to verify both records belong to the same request.
- If logs lack trace IDs, check whether the logger reads current context and uses proper structured logging formatting.

Trace context links observability signals; it should never carry credentials or substitute for audit identities. Action-performing identities must still be recorded in principal fields or corresponding audit logs.

## 10. Distinguishing Logs, Metrics, and Traces

| Signal | Question Answered | Examples |
|---|---|---|
| Logs | What specific event occurred? | Exceptions, policy changes, rejected requests |
| Metrics | How is the system performing over time? | Request rate, error rate, p95 latency, CPU |
| Traces | Which steps did a request take and where did it slow down? | API call to payment provider took 1.8 seconds |

An effective investigation workflow often starts from an alerting metric, uses traces to pinpoint the slow path, and uses logs to read detailed error payloads or recent changes. These three signals reinforce each other; avoid trying to turn every log into a metric or tracing isolated events unrelated to requests.

## 11. Common Issues and How to Handle Them

**Each service starts a separate trace.** Check propagators, header forwarding, and client/server instrumentation. Ensure context is injected before sending and extracted upon receipt.

**Trace is missing an intermediate service.** Confirm that service is instrumented, emitting spans, and not dropped by sampling. Check proxy or service mesh paths.

**Trace has spans but lacks useful attributes.** Add controlled resource attributes and span attributes. Use normalized route templates instead of URLs containing dynamic IDs.

**No traces appear in Cloud Trace.** Check the Cloud Trace API, exporter/collector permissions, ADC, endpoints, egress, exporter errors, and sampling decisions.

**Duplicate traces or spans.** Check whether both an agent and an SDK instrument the same library; avoid wrapping already auto-instrumented operations in redundant manual spans.

**Trace stops at an async boundary.** Pass context through message metadata or task context; verify whether executors and callbacks preserve context.

**Cannot find logs from a trace.** Ensure the logger reads active context and emits trace/span fields; verify log bucket and access permissions.

**Trace contains sensitive data.** Update instrumentation to strip or mask attributes/events, and audit baggage and trace read permissions.

**Collector overloaded.** Monitor memory, queues, retries, and export errors; tune batching, sampling, and collector replicas to match load. Never raise sampling or queue sizes indefinitely without evaluating resources.

## 12. Practice: Finding a Latency-Inducing API Dependency

Suppose `orders-api` on Cloud Run exhibits elevated p95 latency after releasing a new revision. The goal is finding the slow dependency.

1. Open the Cloud Monitoring dashboard and confirm when p95 latency rose.
2. In Cloud Trace, search for traces belonging to `orders-api` during that window.
3. Pick one slow trace and one fast successful trace under comparable conditions.
4. Compare the root span and child spans; inspect HTTP client calls, database calls, and wait gaps.
5. If the payment span is long, open attributes/events to check endpoint, status, and retry count if instrumented.
6. Copy the trace ID and search related logs in Logs Explorer.
7. Cross-check audit logs and revisions to pinpoint related config changes or releases.
8. Test a fix in an appropriate environment, then track p95, error rate, and traces afterward.

A trace diagram might look like:

~~~text
orders-api / POST /orders              2.4 s
├── inventory-service / lookup         180 ms
│   └── Cloud SQL / SELECT               95 ms
├── payment-service / authorize      1,850 ms
│   └── payment-provider / POST       1,720 ms
└── orders-db / INSERT                  70 ms
~~~

If the payment provider is the slowest segment, the team can review timeouts, retry policies, circuit breakers, or asynchronous processing. Do not blindly increase timeouts: doing so holds request resources longer and increases concurrency while the dependency is degraded.

## 13. Principles for Safe and Useful Tracing

- Name spans after stable operations; never embed dynamic IDs in span names.
- Use resource attributes to identify service, version, environment, and region.
- Instrument communication boundaries and critical business operations.
- Ensure context propagation across HTTP, RPC, queues, and background tasks.
- Keep attributes operationally meaningful; avoid PII, tokens, and secrets.
- Choose sampling aligned with traffic and investigative needs; track export success rates.
- Monitor the collector and telemetry pipeline itself like a production workload.
- Grant trace write permissions to exporter identities; grant trace read permissions to investigating teams.
- Govern retention, access control, and telemetry costs per operational requirements.
- Test end-to-end tracing after major changes to gateways, frameworks, service meshes, or message brokers.

## 14. Cloud Trace Implementation Checklist

### Instrumentation and Context

- [ ] Each service has a stable `service.name` and accurate version/environment.
- [ ] HTTP/RPC clients and servers are instrumented.
- [ ] Critical database or dependency calls emit useful spans.
- [ ] Trace context propagates across HTTP, queues, and async tasks.
- [ ] Verified via testing that spans stitch into the same trace.

### Sending Traces to Google Cloud

- [ ] Cloud Trace API is enabled on the target project.
- [ ] Exporter/collector uses ADC or workload identity.
- [ ] Trace-sending identity holds appropriate `roles/cloudtrace.agent` permissions.
- [ ] Endpoints, DNS, egress, and OTLP protocol are working.
- [ ] Collector has appropriate batching, retries, and memory limits.
- [ ] Export errors and dropped spans are monitored.

### Operations and Protection

- [ ] Traces can be opened from logs or request IDs.
- [ ] Spans carry sufficient status, attributes, and events for investigation.
- [ ] Sampling retains enough healthy baseline and error traces for observability goals.
- [ ] No secrets or personal data are recorded in traces.
- [ ] Trace read permissions and retention periods are appropriately restricted.
- [ ] Latency/error-rate metrics are correlated with traces during incidents.

## 15. Official References

- [Cloud Trace documentation](https://cloud.google.com/trace/docs)
- [Set up Cloud Trace](https://cloud.google.com/trace/docs/setup)
- [Trace context and propagation](https://cloud.google.com/trace/docs/trace-context)
- [OpenTelemetry traces concepts](https://opentelemetry.io/docs/concepts/signals/traces/)
- [OpenTelemetry context propagation](https://opentelemetry.io/docs/concepts/context-propagation/)
- [OpenTelemetry Java documentation](https://opentelemetry.io/docs/languages/java/)
- [OpenTelemetry Collector](https://opentelemetry.io/docs/collector/)
- [Google Cloud exporter for OpenTelemetry Collector](https://github.com/GoogleCloudPlatform/opentelemetry-operations-collector)

When bringing tracing to production, test an end-to-end request from entry point to final dependency. A useful trace requires unbroken context, business-meaningful spans, linked logs, and sampling suited to real traffic. When these pieces work together, Cloud Trace helps teams pinpoint slow segments and act on evidence.
