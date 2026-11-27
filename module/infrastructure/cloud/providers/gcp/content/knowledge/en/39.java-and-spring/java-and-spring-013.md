# Structured Logging, Trace Context, and OpenTelemetry for Java

An order creation request flows through a Java API, queries Cloud SQL, calls a payment service, and publishes an event to Pub/Sub. When a customer reports "my order is slow," a log line saying `ERROR payment timeout` does not reveal which request failed, which dependency was slow, which release introduced the issue, or how many other requests were affected.

**Structured logging** turns logs into structured data queryable by field. **Trace context** links operations belonging to the same request, even across multiple services. **OpenTelemetry (OTel)** supplies the API, SDK, Java Agent, and telemetry protocol to collect traces, metrics, and logs in a vendor-neutral way. Combining all three lets operations teams jump from an error log directly to the request trace, and from there to database, HTTP client, and workload spans.

This lesson belongs to the **Java and Spring on GCP** chapter in the **CLOUD_PROVIDERS_GCP** module. The module explores Google Cloud from project organization, IAM, and VPCs to Compute Engine, GKE, Cloud Run, storage services, and databases. Through deployment scenarios, learners select services, secure resources, automate releases, and monitor reliability alongside cost. This provides the observability foundation for turning Java execution data into actionable diagnostic evidence.

## Learning Objectives

After this lesson, you will be able to:

- Distinguish plain-text logs from structured JSON logs in Cloud Logging.
- Use special fields `severity`, `message`, `logging.googleapis.com/trace`, and `logging.googleapis.com/spanId`.
- Explain the relationship among trace ID, span ID, parent span, trace context, sampling, and log correlation.
- Configure the OpenTelemetry Java Agent for Java/Spring Boot applications.
- Emit JSON logs carrying active trace context and use SLF4J for business logging.
- Propagate context across HTTP, gRPC, thread pools, and asynchronous processing.
- Route telemetry to Cloud Logging, Cloud Monitoring, and Cloud Trace.
- Query and correlate logs with traces and troubleshoot common configuration errors.
- Establish production security, cost, and operational policies for telemetry.

## 1. The Problem: Observing One Request Across Multiple Services

Suppose the `orders-api` API runs on Cloud Run. Upon receiving `POST /v1/orders`, the application:

1. Authenticates the request.
2. Reads inventory state from Cloud SQL.
3. Calls `payment-api` over HTTP.
4. Publishes an `order.created` event to Pub/Sub.
5. Returns the response to the client.

If it only logs lines like:

~~~text
INFO  create order
INFO  select inventory
ERROR payment timeout
~~~

you cannot tell which line belongs to which request when hundreds of requests run concurrently. Nor do those logs show which call accounted for most of the latency.

A solid observability design adds:

- **Structured logs:** `service`, `environment`, `event`, `route`, `status`, `duration_ms`, `trace`, `spanId`.
- **Distributed traces:** a trace represents the request's execution path, comprising child spans such as `POST /v1/orders`, `SELECT inventory`, and `POST /charge`.
- **Metrics:** request counts, error rates, latency, and saturation to reveal whether an issue is widespread.
- **Alerts/runbooks:** alerts when error rates or latency breach thresholds, linking to Logs Explorer and Trace Explorer.

### End-to-End Observability Diagram

~~~mermaid
flowchart LR
  A[HTTP client] --> B[Java / Spring API]
  B --> C[Cloud SQL]
  B --> D[Payment API]
  B --> E[Pub/Sub]
  B --> F[JSON logs → stdout]
  F --> G[Cloud Logging]
  B --> H[OpenTelemetry Java Agent / SDK]
  H --> I[OTLP exporter]
  I --> J[OpenTelemetry Collector]
  J --> K[Cloud Trace]
  J --> L[Cloud Monitoring]
  G -. trace ID .-> K
  K -. trace / span .-> G
~~~

The diagram shows one common pattern: JSON logs are collected from `stdout`, while traces and metrics travel through OTLP/Collector. You can send all three signals via OTLP if your system and Collector are configured for it, but avoid enabling multiple concurrent ingestion paths for the same log record to prevent duplicate entries.

## 2. Structured Logging in Cloud Logging

### Text Logs vs JSON Logs

Cloud Logging stores logs as `LogEntry` records. Two common payload types exist:

| Type | Example | Query capability |
|---|---|---|
| `textPayload` | `Payment failed after 1200 ms` | String matching and standard metadata filtering |
| `jsonPayload` | `{"event":"payment.failed","duration_ms":1200}` | Exact filtering by `jsonPayload.event`, `jsonPayload.duration_ms` |

With structured logging, the app emits **one JSON object per line**, instead of space-concatenated text strings. Fields with consistent names and data types enable reliable querying, aggregation, and log-based metrics.

Example JSON log line for a failed request:

~~~json
{
  "severity": "ERROR",
  "message": "Payment provider timed out",
  "service": "orders-api",
  "environment": "staging",
  "event": "payment.timeout",
  "route": "/v1/orders",
  "duration_ms": 1200,
  "payment_provider": "provider-a",
  "logging.googleapis.com/trace": "projects/demo-observability/traces/4bf92f3577b34da6a3ce929d0e0e4736",
  "logging.googleapis.com/spanId": "00f067aa0ba902b7",
  "logging.googleapis.com/trace_sampled": true
}
~~~

The values above are illustrative only; they do not reference a real live trace. In Cloud Logging, special fields are extracted into `LogEntry` metadata, while fields such as `event`, `route`, and `duration_ms` normally land in `jsonPayload`.

### Special Fields to Format Properly

| Field in JSON | Parsed field in Cloud Logging | Notes |
|---|---|---|
| `severity` | `LogEntry.severity` | Use `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`, etc. |
| `message` | Primary display message | Keep concise; never include secrets |
| `timestamp` or `time` | `LogEntry.timestamp` | Use ISO 8601 timestamp with timezone if supplied manually |
| `httpRequest` | `LogEntry.httpRequest` | HTTP details when matching schema |
| `logging.googleapis.com/trace` | `LogEntry.trace` | Full path `projects/PROJECT_ID/traces/TRACE_ID` |
| `logging.googleapis.com/spanId` | `LogEntry.spanId` | 16-hex-character Span ID |
| `logging.googleapis.com/trace_sampled` | `LogEntry.traceSampled` | **Boolean** `true`/`false`, not a string |
| `logging.googleapis.com/labels` | `LogEntry.labels` | Map of string-valued labels |
| Other domain fields | `LogEntry.jsonPayload` | Stores filterable/queryable data |

Note that this mapping applies to single-line JSON collected by the built-in logging agent on Cloud Run/GKE. If an app writes logs directly via the Cloud Logging API or OTLP, field mapping depends on the corresponding client/receiver; verify the ingestion path instead of assuming every backend translates fields identically.

### Designing a Stable Log Schema

A good business log typically includes:

- `event`: stable event identifier, such as `order.create.failed`.
- `service`, `service_version`, `environment`: operational metadata.
- `route`: **route template** (`/v1/orders/{id}`) rather than URLs with concrete IDs.
- `duration_ms`: numeric duration, not a string like `"1200ms"`.
- `error_type`: stable error classification such as `UPSTREAM_TIMEOUT`.
- `retryable`: boolean if retry tracking is needed.
- `trace` and `spanId`: technical links to the active trace/span.

Reuse consistent field names across services so one query matches the same event class everywhere. Avoid dumping full request/response bodies just for "easy debugging": payloads can contain tokens, emails, payment data, or sensitive fields.

## 3. Cloud Run, GKE, and Compute Engine Collect Logs Differently

### Cloud Run

Cloud Run automatically collects logs from container `stdout`/`stderr`. Valid single-line JSON is parsed as a structured log; entries carry `resource.type="cloud_run_revision"`, service name, and revision. Cloud Run also emits platform-generated **request logs** and separate **system logs**.

Do not install Ops Agent on Cloud Run just to capture stdout. If using the Cloud Logging API or another exporter alongside stdout, avoid writing the same event twice.

### GKE

On GKE with logging enabled, container `stdout`/`stderr` are collected from nodes into Cloud Logging. Log resource labels depend on the collection model and cluster setup—typically `k8s_container` with namespace, pod, and container labels.

Operations teams should align `service.name` in OTel with `service` in application logs, and verify actual workload labels so queries do not mix deployments.

### Compute Engine

VMs do not behave like Cloud Run. For log files on a VM, configure **Ops Agent** with a receiver and a `parse_json` processor if JSON parsing is needed; verify file paths, read permissions, and pipeline config. Ops Agent can also collect host metrics and OTLP traces/metrics depending on version and configuration.

| Environment | Typical log path | What to check |
|---|---|---|
| Cloud Run | Container `stdout`/`stderr` → Cloud Logging | Single-line JSON, trace fields, and request correlation |
| GKE | Container `stdout`/`stderr` → cluster logging pipeline | Logging enabled, resource labels, no duplicate exporter |
| Compute Engine | Ops Agent reading files or configured sources | Receivers, JSON parsing, permissions, and agent status |
| Local Java | Console or JSON file | Local viewer/collector; Cloud Logging may not be wired |

## 4. Traces, Spans, and Trace Context

### What Is a Distributed Trace?

A **trace** represents the end-to-end execution of an operation across multiple services. Inside a trace are multiple **spans**; each span records a distinct unit of work, such as controller handling, a SQL query, or an HTTP call.

- **Trace ID:** 16 bytes, commonly rendered as 32 hex characters; stays constant across the entire trace.
- **Span ID:** 8 bytes, 16 hex characters; distinct per span.
- **Parent span:** captures parent–child relationships to construct the waterfall view.
- **Attributes:** metadata such as `http.request.method`, route, database system, or peer service, following semantic conventions.
- **Events:** notable timestamps within a span.
- **Status:** span outcome, optionally recording errors and exceptions.

A log does not turn into a span by itself. A trace ID inside a log is only a **link** to find related data; spans must actually be created, sampled/exported, and ingested before Trace Explorer can render the complete trace.

### W3C Trace Context

The OpenTelemetry Java Agent uses W3C Trace Context by default to propagate context over HTTP. Illustrative header:

~~~http
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
~~~

Breakdown:

| Component | Example value | Role |
|---|---|---|
| version | `00` | Format version |
| trace-id | `4bf92f3577b34da6a3ce929d0e0e4736` | Connects spans in the same trace |
| parent-id | `00f067aa0ba902b7` | Caller's span |
| trace-flags | `01` | Sampled flag bit in header |

The `tracestate` header carries vendor-specific info when needed. `baggage` propagates key/value pairs across service boundaries; **never** store passwords, tokens, or personal data in baggage, as it can propagate onward to external systems.

### Trace Context vs Correlation ID

An app might use an `X-Request-Id` assigned by a load balancer or gateway. This is a helpful correlation ID, yet **not equivalent to a trace ID**. Request IDs may change at each hop; trace IDs stay consistent across spans of the same distributed trace.

You can log both request ID and trace ID, provided they occupy separate fields with clear generation and validation rules.

### X-Cloud-Trace-Context on Cloud Run

Cloud Run uses the `X-Cloud-Trace-Context` header and can link platform request logs by trace. For container JSON logs, `logging.googleapis.com/trace` must contain the **same trace ID as the request log** for Logs Explorer to nest child logs beneath the request log.

When using the OTel Java Agent with W3C `traceparent`, verify that the app's trace context and the platform request log share the same trace ID. If propagators or incoming headers produce two separate traces, container logs still carry valid trace IDs yet fail to nest under the expected request log. Never "patch" around this by writing an arbitrary ID into the trace field.

## 5. Three Signals in OpenTelemetry

OpenTelemetry standardizes three core signals:

| Signal | Data | Where to inspect on GCP |
|---|---|---|
| Traces | Traces, spans, parent relationships, span events | Cloud Trace / Trace Explorer |
| Metrics | Counters, histograms, gauges, and time series | Cloud Monitoring / Metrics Explorer |
| Logs | Log records, severity, attributes, and trace context | Cloud Logging / Logs Explorer |

Key components:

- **API:** invoked by application code to add instrumentation.
- **SDK:** implements collection, sampling, batching, and exporting.
- **Java Agent:** auto-instruments popular libraries via bytecode instrumentation, minimizing code edits.
- **OTLP:** protocol carrying telemetry from SDK/Agent to a Collector or compatible endpoint.
- **Collector:** receives, processes, batches, filters, and exports signals to backends.
- **Semantic conventions:** standardized attribute names for HTTP, RPC, DB, and messaging so systems share consistent meanings.

### Automatic vs Manual Instrumentation

**Automatic instrumentation** via the Java Agent creates spans for inbound HTTP, outbound HTTP, JDBC, gRPC, and other supported libraries. This provides baseline observability without altering business code.

**Manual instrumentation** uses `Tracer`, `Span`, and `Context` APIs to add spans for meaningful business steps such as `reserve-inventory` or `validate-order`.

Both combine cleanly: the Java Agent records infrastructure spans while manual spans capture business work. Avoid creating duplicate spans covering the exact same operation, which clutters traces and inflates ingestion volume.

## 6. Configuring the OpenTelemetry Java Agent

### Prerequisites

- Java and framework versions supported by your Java Agent release.
- A Spring Boot or Java HTTP server application.
- `opentelemetry-javaagent.jar` downloaded from official releases with a **pinned version**.
- An OTLP endpoint for your Collector or supported backend.
- IAM permissions for the telemetry-exporting identity.

### Enabling the Agent

On the JVM, pass `-javaagent`:

~~~bash
java -javaagent:/opt/otel/opentelemetry-javaagent.jar -jar orders-api.jar
~~~

Or via environment variable:

~~~bash
export JAVA_TOOL_OPTIONS="-javaagent:/opt/otel/opentelemetry-javaagent.jar"
java -jar orders-api.jar
~~~

In container images, copy the agent JAR into the image in a controlled build step. Never download an unpinned `latest` URL on every production startup; verify checksums and build immutable images.

### Sample OTLP Environment Variables

Example with a Collector running at hostname `otel-collector` listening for **OTLP HTTP/protobuf** on port 4318:

~~~bash
export OTEL_SERVICE_NAME="orders-api"
export OTEL_RESOURCE_ATTRIBUTES="deployment.environment.name=staging,service.version=1.2.3"
export OTEL_TRACES_EXPORTER="otlp"
export OTEL_METRICS_EXPORTER="otlp"
export OTEL_LOGS_EXPORTER="none"
export OTEL_EXPORTER_OTLP_PROTOCOL="http/protobuf"
export OTEL_EXPORTER_OTLP_ENDPOINT="http://otel-collector:4318"
export JAVA_TOOL_OPTIONS="-javaagent:/opt/otel/opentelemetry-javaagent.jar"
~~~

Explanation:

- `OTEL_SERVICE_NAME` sets the service name used to group traces and metrics.
- `OTEL_RESOURCE_ATTRIBUTES` attaches environment and release version to compare before/after deployments.
- `OTEL_TRACES_EXPORTER` and `OTEL_METRICS_EXPORTER` send both signals over OTLP.
- `OTEL_LOGS_EXPORTER=none` disables only **OTLP log export** from the Agent in this setup; the app still writes structured JSON to stdout for Cloud Run collection.
- `OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf` matches port 4318. If the Collector listens on gRPC (typically port 4317), configure the matching gRPC protocol and endpoint.
- The DNS name `otel-collector` is illustrative. In a Cloud Run sidecar, `localhost` may be used; on GKE, a Service address is typical. Choose the transport path matching your real architecture.

Never transmit unencrypted OTLP over public networks. For Collectors outside localhost or trusted networks, configure TLS, authentication, and egress policies.

### Sampling

Sampling reduces the volume of spans recorded and exported. Example configuring 10% ratio sampling (use only after understanding traffic and diagnostic needs):

~~~bash
export OTEL_TRACES_SAMPLER="parentbased_traceidratio"
export OTEL_TRACES_SAMPLER_ARG="0.10"
~~~

`parentbased_traceidratio` honors the parent's sampling decision when a valid remote parent exists. Logs can still be emitted for unsampled requests; in that case, a trace ID in a log **does not guarantee** a corresponding trace exists in Cloud Trace.

## 7. Structured JSON Logging in Java/Spring Applications

Two implementation paths are common:

1. Use SLF4J with Logback or Log4j2 JSON layouts; the Java Agent populates MDC with trace context, and the JSON encoder maps it to standard Cloud Logging fields.
2. Construct a JSON log entry manually with structured fields and trace context pulled from `Span.current()`. The second approach helps understand the wire format; for production, prefer battle-tested loggers and encoders.

### Option A: SLF4J + Log4j2 JSON Template Layout

In Spring Boot, when switching from default Logback to Log4j2, align dependencies with a compatible BOM: exclude the default logging starter as needed and add `spring-boot-starter-log4j2`. JSON Template Layout requires the `log4j-layout-template-json` module matching your Log4j2 version.

Example `log4j2.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<Configuration status="WARN">
  <Appenders>
    <Console name="JSON" target="SYSTEM_OUT">
      <JsonTemplateLayout eventTemplateUri="classpath:GcpLayout.json"/>
    </Console>
  </Appenders>
  <Loggers>
    <Root level="INFO">
      <AppenderRef ref="JSON"/>
    </Root>
  </Loggers>
</Configuration>
~~~

`GcpLayout.json` is a **custom template that must be packaged** on the classpath. The template must map severity and message, read MDC trace ID/span ID, format the trace resource name `projects/PROJECT_ID/traces/TRACE_ID`, and emit the sampled flag as a boolean. The XML config above **is not sufficient by itself** without the template and JSON Template Layout module.

Google Cloud provides a Spring Boot sample using this exact pattern. Run the sample and inspect the real template configuration in the [Java instrumentation sample](https://cloud.google.com/trace/docs/setup/java-ot) docs; avoid copying an outdated template without verifying the exact MDC key names used by your Java Agent version.

In business code, log through SLF4J:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class OrderService {
    private static final Logger logger =
        LoggerFactory.getLogger(OrderService.class);

    public void submitOrder(int itemCount) {
        logger.info("Submitting order with itemCount={}", itemCount);
        // Business logic.
    }
}
~~~

With a properly configured Java Agent, MDC holds active span info. The JSON layout converts MDC keys into matching fields. Having a trace ID in MDC **does not automatically** turn logs into structured JSON; an encoder/layout must emit the proper format.

### Option B: Emitting JSON Events with Active Trace Context

The Java snippet below demonstrates the format independently of any specific JSON logging framework. It uses Jackson 2 (`com.fasterxml.jackson.databind.ObjectMapper`), the OpenTelemetry API, and prints **one JSON object per line**. In projects using Jackson 3, adjust package/API imports accordingly.

~~~java
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import io.opentelemetry.api.trace.Span;
import io.opentelemetry.api.trace.SpanContext;
import java.util.LinkedHashMap;
import java.util.Map;

public final class GcpJsonEvents {
    private static final ObjectMapper MAPPER = new ObjectMapper();
    private final String projectId;

    public GcpJsonEvents(String projectId) {
        if (projectId == null || projectId.isBlank()) {
            throw new IllegalArgumentException("projectId is required");
        }
        this.projectId = projectId;
    }

    public void log(
        String severity,
        String event,
        String message,
        String route,
        long durationMs
    ) {
        Map<String, Object> entry = new LinkedHashMap<>();
        entry.put("severity", severity);
        entry.put("message", message);
        entry.put("service", "orders-api");
        entry.put("event", event);
        entry.put("route", route);
        entry.put("duration_ms", durationMs);

        SpanContext context = Span.current().getSpanContext();
        if (context.isValid()) {
            entry.put(
                "logging.googleapis.com/trace",
                "projects/" + projectId + "/traces/" + context.getTraceId()
            );
            entry.put(
                "logging.googleapis.com/spanId", context.getSpanId()
            );
            entry.put(
                "logging.googleapis.com/trace_sampled", context.isSampled()
            );
        }

        try {
            System.out.println(MAPPER.writeValueAsString(entry));
        } catch (JsonProcessingException error) {
            System.err.println(
                "{\"severity\":\"ERROR\",\"message\":\"log serialization failed\"}"
            );
        }
    }
}
~~~

Invoking from instrumented code:

~~~java
GcpJsonEvents events = new GcpJsonEvents("PROJECT_ID");

events.log(
    "WARNING",
    "order.payment.retry",
    "Payment timed out; retry scheduled",
    "/v1/orders",
    1200L
);
~~~

This sample teaches schema structure and is not a full replacement for a production logging library. In high-throughput applications, use an asynchronous logger or proper JSON encoder to handle flushing, backpressure, exception formatting, and consistent metadata. Never allocate a new `ObjectMapper` per request.

If `Span.current().getSpanContext().isValid()` is `false`, the code never fabricates a trace ID. Inspect the agent, active context, and when the log is emitted. On Cloud Run, also confirm the emitted trace ID matches the platform request log's trace if you want logs nested beneath the request.

### Using SLF4J MDC Manually When Needed

`MDC` (Mapped Diagnostic Context) stores key/value pairs bound to the current execution flow so logging frameworks attach them to every log line. Example:

~~~java
import org.slf4j.MDC;

public void processOrder(String routeTemplate) {
    try {
        MDC.put("route", routeTemplate);
        MDC.put("component", "order-service");
        // Logger/JSON encoder reads MDC when writing logs.
        logger.info("Processing order");
    } finally {
        MDC.remove("route");
        MDC.remove("component");
    }
}
~~~

Never call `MDC.clear()` indiscriminately if a Java Agent or other filter populated trace metadata, as doing so wipes keys managed by other components. Remove only keys added by your own code, or use a scoped MDC helper.

MDC normally relies on `ThreadLocal`, which does not automatically cross every executor, coroutine, or reactive pipeline. With WebFlux/Reactor, use supported context propagation integrations instead of assuming `MDC.put` on a request thread persists across all callbacks.

## 8. Manual Instrumentation and Context Propagation

### Adding Business Spans

Once the Java Agent creates the HTTP server span, you can add child spans for key operations:

~~~java
import io.opentelemetry.api.GlobalOpenTelemetry;
import io.opentelemetry.api.trace.Span;
import io.opentelemetry.api.trace.StatusCode;
import io.opentelemetry.api.trace.Tracer;
import io.opentelemetry.context.Scope;

public final class InventoryTrace {
    private static final Tracer TRACER =
        GlobalOpenTelemetry.getTracer("orders-api");

    public void reserveInventory(Runnable operation) {
        Span span = TRACER.spanBuilder("reserve-inventory").startSpan();
        try (Scope ignored = span.makeCurrent()) {
            operation.run();
            span.setAttribute("inventory.operation", "reserve");
        } catch (RuntimeException failure) {
            span.recordException(failure);
            span.setStatus(StatusCode.ERROR);
            throw failure;
        } finally {
            span.end();
        }
    }
}
~~~

`Scope` makes the span current inside the `try` block. Logs written inside the scope see the right context via `Span.current()`. Always call `span.end()`, even when exceptions occur.

Never attach order IDs, emails, or tokens as span attributes merely for search convenience. When considering a business identifier, evaluate sensitivity, access policies, and cardinality first; many cases need only `route`, `operation`, or `error.type`.

### Context Propagation over HTTP/gRPC

When an app uses HTTP clients or gRPC supported by the Java Agent, instrumentation automatically injects trace context into outbound requests. The target service uses a propagator to extract context and create child spans with the right parent.

If making HTTP calls with a custom client or an uninstrumented framework, inject/extract manually using OpenTelemetry propagators. Never mint a brand-new trace ID per hop; propagate the active context.

### Thread Pools and Asynchronous Tasks

For executors instrumented by the Java Agent, context propagation happens automatically. However, if you defer tasks for later, push to a queue, or switch to self-managed threads, verify propagation explicitly.

A manual pattern uses `Context.current().wrap(runnable)`:

~~~java
import io.opentelemetry.context.Context;
import java.util.concurrent.ExecutorService;

public void submitWork(ExecutorService pool, Runnable task) {
    Runnable withContext = Context.current().wrap(task);
    pool.submit(withContext);
}
~~~

Capture `Context.current()` **while inside the caller's active span**. For background work running long after a request finishes, consider starting a new trace linked to the prior context rather than keeping a completed parent span where causality becomes ambiguous.

### Messaging via Pub/Sub

With Pub/Sub, propagate trace context via message attributes or a propagator-aware integration. Consumers must extract context before starting the message-processing span. Never assume Pub/Sub's shared message ID automatically links traces.

When retries or dead-letter deliveries occur, distinguish traces for publishing versus each consumption attempt. Use span links when appropriate to model multiple causal relationships rather than forcing everything into one parent–child tree.

## 9. Sending Telemetry to Google Cloud

Two architectures are common:

### Model A: stdout Logs + OTLP Traces/Metrics

~~~text
Java / Spring
  ├─ SLF4J + JSON encoder → stdout → Cloud Logging
  └─ OTel Java Agent/SDK → OTLP → Collector → Cloud Trace / Monitoring
~~~

This fits Cloud Run and GKE cleanly because native log collection already exists. Logs ingest via platform-native stdout handling, while traces/metrics route flexibly through the Collector. This is the primary model for this lesson's exercise.

### Model B: OTLP for Logs, Traces, and Metrics

~~~text
Java OTel SDK / Agent
  └─ OTLP → Collector → Telemetry API / Cloud Logging / Cloud Trace / Monitoring
~~~

This centralizes processing in the Collector, though you must ensure the logs pipeline is supported and prevent stdout ingestion from duplicating the exact same log records. Mapping OTLP log attributes to `LogEntry` differs from how the built-in agent parses JSON.

### Choosing a Collector or In-Process Exporter

Google Cloud recommends using a Collector where the environment permits, because app instrumentation stays decoupled from backends and the Collector can batch, retry, route, and filter telemetry. In environments unsuitable for a Collector, use an in-process OTLP exporter targeting the Telemetry API endpoint per current documentation.

On Compute Engine, Ops Agent can ingest OTLP traces and metrics; note that Ops Agent's OTLP receiver does not ingest OTLP logs. VM logs are collected through dedicated logging receivers.

### Enabling APIs

Example enabling required APIs for a lab environment:

~~~bash
gcloud services enable \
  logging.googleapis.com \
  monitoring.googleapis.com \
  cloudtrace.googleapis.com \
  telemetry.googleapis.com \
  --project=PROJECT_ID
~~~

### IAM Permissions by Ingestion Path

| Component | Reference role | Notes |
|---|---|---|
| Collector writing metrics | `roles/monitoring.metricWriter` | On the metric-ingesting project |
| Collector/OTLP writing traces via Telemetry API | `roles/telemetry.tracesWriter` | Used when exporting traces via Telemetry API |
| Collector writing logs via Logging API | `roles/logging.logWriter` | When calling the API directly; Cloud Run stdout uses native collection |
| Ingesting traces via legacy Cloud Trace API | `roles/cloudtrace.agent` | Depends on API/exporter; does not replace `roles/telemetry.tracesWriter` for Telemetry API |
| Log viewers | `roles/logging.viewer` | Additional permissions may apply for restricted log views |
| Trace viewers | `roles/cloudtrace.user` | Read traces per IAM policy |
| Metric viewers | `roles/monitoring.viewer` | View Metrics Explorer and dashboards |

If using a separate quota project, the telemetry-writing identity may need `roles/serviceusage.serviceUsageConsumer` on the quota project. Use the Cloud Run/Collector service account or Workload Identity Federation for GKE; never embed service account keys in images, source code, or Dockerfiles.

### Network Design

- For OTLP HTTP/protobuf, the endpoint is typically `http://COLLECTOR_HOST:4318` inside a trusted network.
- For OTLP gRPC, the port is typically `4317`.
- The Collector must have egress and authentication to reach Google Cloud endpoints per exporter config.
- When using VPC Service Controls, Cloud NAT, proxies, private egress, or sidecars, verify ingress/egress policies and service identities.
- If the Collector stops or hits backpressure, check exporter logs, queues, and retries; telemetry can be dropped or delayed.

## 10. Hands-On: Java API on Cloud Run

This lab exercises the concepts on a Java/Spring Boot API in an isolated test project. You can use your current learning API or Google Cloud's official Spring Boot sample. Do not modify a production system.

### Step 1: Prepare Project and Workload

1. Choose a test project and ensure billing and required APIs are enabled.
2. Have a Spring Boot app with `GET /hello` or `POST /v1/orders`.
3. Identify the project ID and runtime service account.
4. Set up an OTLP receiver: a lab Collector or supported endpoint.
5. Grant least-privilege IAM for trace/metric export.
6. Configure a JSON encoder or the illustrative `GcpJsonEvents` helper.

### Step 2: Emit Logs on Requests

Example controller:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class HelloController {
    private static final Logger log =
        LoggerFactory.getLogger(HelloController.class);

    @GetMapping("/hello")
    public String hello() {
        log.info("hello endpoint invoked");
        return "hello";
    }
}
~~~

To produce structured logs, the logging framework needs a JSON layout as shown in Section 7 or a JSON helper. Simply calling `logger.info(...)` with the default console text layout produces `textPayload`, not structured `jsonPayload`.

### Step 3: Enable the OTel Agent

Package a pinned Java Agent release into your image. When starting the JVM, pass `JAVA_TOOL_OPTIONS`, `OTEL_SERVICE_NAME`, `OTEL_RESOURCE_ATTRIBUTES`, `OTEL_EXPORTER_OTLP_ENDPOINT`, and the matching protocol. On Cloud Run, configure a Collector sidecar or reachable endpoint; never copy lab hostnames into production.

### Step 4: Send Traffic

Example targeting your test service URL:

~~~bash
curl -i https://YOUR_CLOUD_RUN_URL/hello
~~~

Send several requests to generate request logs, container logs, spans, and metrics. You can add a simulated-error endpoint in staging, but never deploy test error-injection logic to production.

### Step 5: Verify JSON Logs

In Logs Explorer:

~~~text
resource.type="cloud_run_revision"
resource.labels.service_name="orders-api"
~~~

Expand a container log entry. Verify:

- Payload is `jsonPayload`, not only `textPayload`.
- `severity` appears in standard metadata.
- `jsonPayload.event` or `jsonPayload.service` holds expected values.
- `trace` has the form `projects/PROJECT_ID/traces/TRACE_ID` when an active span exists.
- `spanId` is populated inside a valid span.
- Request logs and container logs group under the same trace when context matches.

### Step 6: Inspect Cloud Trace

Open Trace Explorer and filter for `orders-api`, recent time range, and `/hello`. Pick a trace and inspect:

1. The HTTP server span.
2. Outbound HTTP/JDBC spans if the lab includes dependencies.
3. Duration, attributes, and status.
4. Parent–child relationships.
5. Correlated logs sharing the same trace ID.

With sampling enabled, some requests will have logs without exported traces. That is not necessarily a bug; inspect `trace_sampled`, the sampler, and exporter settings.

### Step 7: Verify Log–Trace Correlation

Copy the trace resource name from a log entry and filter:

~~~text
trace="projects/PROJECT_ID/traces/TRACE_ID"
~~~

Then open the trace in Trace Explorer. If the trace exists yet logs do not nest under the request log, compare trace IDs across `LogEntry.trace`, the `X-Cloud-Trace-Context` header, and the Java Agent context.

### Step 8: Clean Up

Delete lab resources when finished: the Cloud Run service, Collector, test project, or temporary log/metric/tracing configurations. Check billing to ensure no test subscriptions or exporters incur unexpected charges.

## 11. Logs Explorer Queries for Investigation

Cloud Logging query language filters both standard metadata and JSON fields.

### Errors in a Cloud Run Service

~~~text
resource.type="cloud_run_revision"
resource.labels.service_name="orders-api"
severity>=ERROR
~~~

### Finding a Specific Business Event

~~~text
resource.type="cloud_run_revision"
jsonPayload.event="payment.timeout"
~~~

### Finding Slow Requests

~~~text
resource.type="cloud_run_revision"
jsonPayload.duration_ms>1000
~~~

### Following One Trace

~~~text
trace="projects/PROJECT_ID/traces/TRACE_ID"
~~~

### Filtering by Service and Version

~~~text
jsonPayload.service="orders-api"
jsonPayload.service_version="1.2.3"
~~~

If a field is missing from `jsonPayload`, inspect the log entry in JSON view to verify its actual location. For instance, `severity` and `trace` become top-level metadata fields after standard parsing rather than staying inside `jsonPayload`.

In queries, `trace` uses the full value with the project prefix. Searching for a bare trace ID alone may miss matches unless formatted properly.

## 12. Sampling, Retention, Cost, and Security

### Trace Sampling and Log Filtering

Trace sampling cuts span volume and ingestion/storage costs. However:

- `INFO`/`ERROR` logs are not automatically sampled in lockstep with traces.
- A valid trace ID in a log does not guarantee the trace was ingested.
- Ratio-based sampling can miss rare yet critical requests.
- Evaluate tail sampling or error-prioritizing policies if your Collector architecture supports them, while verifying resource capacity.

For logs, choose sensible production levels (`INFO`/`WARN`/`ERROR`), avoiding pervasive `DEBUG` logging. Use controlled log exclusions or filtering; never drop all error logs just to cut costs.

### Cardinality and Sensitive Data

Never place the following in log labels, span attributes, or baggage without explicit requirements and safeguards:

- Passwords, API keys, bearer tokens, cookies, or session IDs.
- Payment details, identity documents, or health records.
- Full URLs containing tokens or identifiers in query strings.
- Raw request or response bodies.
- Emails, user IDs, or order IDs in high-cardinality metric labels.

Use error codes, route templates, operation types, or non-sensitive customer tiers instead. For exceptions, scrub or mask secret values from messages, stack traces, and nested causes.

### Access, Retention, and Auditing

- Restrict `roles/logging.viewer`, `roles/cloudtrace.user`, and `roles/monitoring.viewer` by job function.
- Apply log bucket retention and regions meeting organizational compliance.
- Audit Logs Router sinks and destinations to prevent exporting data outside authorized boundaries.
- For logs carrying sensitive content, use restricted log views with tighter permissions.
- Check retention windows for traces and metrics per configuration, signal type, and current policy.
- Assign an owner to the telemetry pipeline; monitor ingestion cost, span counts, log volume, and exporter errors.

## 13. Common Configuration Issues

| Symptom | Possible cause | What to check |
|---|---|---|
| Logs appear as `textPayload` | Logger emits plain text or splits JSON across lines | Inspect raw stdout and JSON encoder config |
| `severity` stays `DEFAULT` | Missing standard `severity` field or JSON parse failure | Check key name, data type, and receiver |
| No `trace` in logs | No active span or JSON layout omits trace fields | Check Agent, MDC, and `SpanContext.isValid()` |
| Logs carry a trace yet Trace Explorer shows no spans | Span unsampled, not exported, or ingestion error | Check sampler, Collector, IAM, and egress |
| Container logs do not nest under request logs | Trace ID does not match platform request log | Compare trace IDs, headers, and propagators |
| Trace splits into multiple disconnected traces | Missing propagation across HTTP/gRPC, queues, or async | Check `traceparent`, extract/inject, and context wrapping |
| Child spans have the wrong parent | Span created outside active context or lost `Scope` | Check `makeCurrent`, executors, and span lifecycle |
| Trace lacks HTTP client/JDBC spans | Agent not attached or library version unsupported | Check startup logs and Java Agent compatibility |
| Duplicate log entries | Same event sent via both stdout and OTLP/Logging API | Pick one ingestion path or deduplicate |
| Collector fails to export traces | Wrong endpoint/protocol, missing auth/IAM, or blocked network | Check exporter logs, TLS, retries, and quotas |
| Cloud Logging costs spike | Too much `DEBUG`/`INFO`, retry loops, or huge payloads | Measure log volume, filter appropriately, and fix source |
| JSON field mixes types | Same key logged sometimes as number, sometimes as string | Standardize schema and check serializers |
| Traces miss route or service name | Missing resource attributes or uninstrumented semantic fields | Check `OTEL_SERVICE_NAME` and attributes |
| Async logs lose trace context | `ThreadLocal`/MDC not propagated | Use OTel Context propagation for executors/Reactor |

### Short Diagnostic Workflow

1. **Are logs arriving?** If not, check stdout, log files, or receivers.
2. **Is the JSON valid?** If not, inspect the layout and formatter.
3. **Is trace context present?** If not, check the Agent, `Scope`, and MDC.
4. **Are spans in Cloud Trace?** If not, check sampling, exporter, and Collector.
5. **Do logs and spans correlate to the same request?** If not, compare trace IDs across systems.
6. **Is diagnostic detail sufficient?** If not, add meaningful fields containing zero secrets.

## 14. Best Practices for Java/Spring Teams

- Standardize a **log schema**: `event`, `service`, `environment`, `route`, `duration_ms`, `error_type`.
- Emit **single-line JSON** on Cloud Run/GKE so Cloud Logging parses cleanly.
- Write `logging.googleapis.com/trace` as the full resource name; 16-hex-char `spanId`; boolean `trace_sampled`.
- Use the Java Agent for baseline HTTP/JDBC spans, then add manual spans where business meaning matters.
- Align `service.name`, service version, and environment across logs, metrics, and traces.
- Verify context propagation across HTTP, gRPC, Pub/Sub, and async code.
- Never treat a trace ID in logs as proof the trace was ingested.
- Avoid exporting logs via OTLP while simultaneously collecting the same logs from stdout.
- Use service accounts and Workload Identity instead of long-lived keys.
- Never log secrets, tokens, sensitive bodies, or unsanitized raw URLs.
- Configure sampling, retention, and log filtering to balance diagnostics and budget.
- Build dashboards and alerts linking Logs Explorer and Trace Explorer with clear owners and runbooks.

## Review Questions

1. How does `jsonPayload` differ from `textPayload`, and what is the advantage of filtering by `event`?
2. Why must `logging.googleapis.com/trace` include the project prefix rather than just the trace ID?
3. A log entry contains a trace ID, yet Trace Explorer shows no trace: name at least three possible causes.
4. What role does `traceparent` play in a request spanning multiple services?
5. What happens when MDC is not propagated across a thread pool or Reactor pipeline?
6. Why should you avoid sending the exact same log via both stdout and an OTLP log exporter?
7. When should you rely on automatic Java Agent spans versus manual spans?
8. On Cloud Run, how do you verify that container logs belong to the matching request log?

## Conclusion

**Structured logging** enables Java/Spring applications to emit queryable JSON log records. **Trace context** preserves relationships across operations of a single request and links logs to spans. **OpenTelemetry** provides standardized instrumentation and protocols for collecting traces and metrics while supporting log correlation via MDC.

On Google Cloud, a practical architecture uses JSON logs on stdout in Cloud Run/GKE paired with the OpenTelemetry Java Agent/Collector for traces and metrics. When trace fields use the proper resource format, trace IDs propagate across services, and spans export reliably, operations teams can move from error logs to Cloud Trace, pinpoint slow dependencies or business steps, and use metrics to assess blast radius. This design stays reliable only when sensitive data is protected, sampling is understood, and the telemetry pipeline is verified end to end.

## References

- [Cloud Logging: Structured logging](https://cloud.google.com/logging/docs/structured-logging)
- [Cloud Run: Logging and viewing logs](https://cloud.google.com/run/docs/logging)
- [Cloud Trace: Java instrumentation sample](https://cloud.google.com/trace/docs/setup/java-ot)
- [Google Cloud: Choose an instrumentation approach](https://cloud.google.com/stackdriver/docs/instrumentation/choose-instrumentation)
- [Cloud Trace: Instrument for Cloud Trace](https://cloud.google.com/trace/docs/setup)
- [Cloud Logging: LogEntry fields](https://cloud.google.com/logging/docs/reference/v2/rest/v2/LogEntry)
- [OpenTelemetry: Java zero-code instrumentation](https://opentelemetry.io/docs/zero-code/java/agent/)
- [OpenTelemetry: Java manual instrumentation](https://opentelemetry.io/docs/languages/java/instrumentation/)
- [OpenTelemetry: Context propagation](https://opentelemetry.io/docs/concepts/context-propagation/)
- [W3C Trace Context](https://www.w3.org/TR/trace-context/)
- [Google Cloud: Collect OTLP metrics and traces with Ops Agent](https://cloud.google.com/stackdriver/docs/solutions/agents/ops-agent/otlp)
- [Cloud Logging: Query and view logs](https://cloud.google.com/logging/docs/view/logging-query-language)
