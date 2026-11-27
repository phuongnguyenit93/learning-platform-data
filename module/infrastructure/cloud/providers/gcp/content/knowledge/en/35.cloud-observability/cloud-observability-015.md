# Hands-On: Correlating Logs, Metrics, and Traces with OpenTelemetry

In the `CLOUD_PROVIDERS_GCP` module, you explore Google Cloud from project organization, IAM, and VPC to Compute Engine, GKE, Cloud Run, storage services, and databases. As these workloads communicate with each other, a single request can pass through multiple services, queues, and databases. If logs, metrics, and traces are collected separately, operations teams struggle to determine which request corresponds to a spike on a chart and at which step a specific error occurred.

This hands-on lab uses OpenTelemetry (OTel) to generate and correlate all three signals within a single execution flow. You will instrument a Java/Spring Boot application, propagate trace context across components, emit JSON logs carrying trace ID and span ID, record a histogram metric inside a span's context to generate exemplars, and forward telemetry through an OpenTelemetry Collector to Google Cloud Observability.

## 1. Expected Outcomes and Correlation Model

Upon completing this lab, a request to `checkout-api` will produce:

- A trace containing an HTTP server span and business spans such as `payment.authorize`.
- JSON logs recording events during execution, stamped with the active span's trace ID and span ID.
- A histogram metric recording payment processing duration alongside an exemplar pointing to a sample span in the trace.

The three correlations rely on distinct mechanisms:

| Correlation | Mechanism | Outcome |
| --- | --- | --- |
| Logs ↔ Traces | Record trace ID and span ID in log records or Cloud Logging `LogEntry`. | Open the trace from a log; view request logs from a trace. |
| Metrics ↔ Traces | Record histograms inside a span's context so the SDK generates exemplars. | Jump from a metric chart data point to a representative trace. |
| Traces ↔ Traces | Propagate W3C Trace Context over HTTP or message metadata. | Services and workers appear in the same trace with proper parent-child relationships or links. |

Data flow diagram:

~~~mermaid
flowchart LR
  REQ[HTTP request] --> APP[Spring Boot + OTel Java Agent]
  APP --> SPAN[Server span and business spans]
  APP --> METRIC[Histogram and counter]
  APP --> LOG[Structured JSON log]
  SPAN -->|OTLP| COL[OpenTelemetry Collector]
  METRIC -->|OTLP with exemplars| COL
  LOG -->|stdout / log agent| LOGGING[Cloud Logging]
  COL --> TRACE[Cloud Trace]
  COL --> MON[Cloud Monitoring]
  LOGGING -->|trace and span fields| TRACE
  MON -->|exemplar trace link| TRACE
~~~

The critical requirement is emitting all signals within the same execution context. If a log is written after the context closes, or a metric is recorded without passing the span's context, data may still be stored but the correlation link is lost.

## 2. Preparing the Google Cloud Project

Choose a project for this lab. Enable the required APIs:

~~~bash
gcloud config set project PROJECT_ID

gcloud services enable \
  logging.googleapis.com \
  monitoring.googleapis.com \
  cloudtrace.googleapis.com \
  telemetry.googleapis.com
~~~

If using a dedicated service account for the Collector to send logs, metrics, and traces via the Telemetry API, grant the corresponding write roles on the project:

~~~bash
gcloud projects add-iam-policy-binding PROJECT_ID \
  --member="serviceAccount:otel-collector@PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/logging.logWriter"

gcloud projects add-iam-policy-binding PROJECT_ID \
  --member="serviceAccount:otel-collector@PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/monitoring.metricWriter"

gcloud projects add-iam-policy-binding PROJECT_ID \
  --member="serviceAccount:otel-collector@PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/telemetry.tracesWriter"
~~~

Replace `PROJECT_ID` with the actual project ID and ensure the service account exists. On Cloud Run or GKE, bind this service account to the Collector using the appropriate service identity or Workload Identity mechanism. Locally, use Application Default Credentials (ADC) from your developer account during testing. Never embed service account JSON keys inside images or repositories.

Readers viewing the results need corresponding view roles:

| Need | IAM Role |
| --- | --- |
| View logs | Logs Viewer — `roles/logging.viewer` |
| View metrics and dashboards | Monitoring Viewer — `roles/monitoring.viewer` |
| View traces | Cloud Trace User — `roles/cloudtrace.user` |

In production, grant roles to the appropriate operations groups or service accounts following least privilege. The Collector's telemetry-writing permissions and on-call engineers' telemetry-reading permissions are separate responsibilities.

## 3. Instrumenting the Java Application with OpenTelemetry

This lab uses Spring Boot as an example. The OpenTelemetry Java Agent automatically creates spans for supported frameworks, including inbound HTTP requests and common outbound HTTP/database calls. We add a business span and a histogram metric to observe the payment step.

### 3.1. Launching with the OpenTelemetry Java Agent

Place the Java agent JAR at a stable path in the image or runtime environment, then start the application with `-javaagent`.

~~~bash
java -javaagent:/opt/otel/opentelemetry-javaagent.jar -jar app.jar
~~~

Configure resource identity and the OTLP exporter using environment variables:

~~~bash
OTEL_SERVICE_NAME=checkout-api
OTEL_RESOURCE_ATTRIBUTES=service.namespace=commerce,deployment.environment.name=lab,service.version=1.0.0
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
OTEL_EXPORTER_OTLP_PROTOCOL=grpc
OTEL_PROPAGATORS=tracecontext,baggage
OTEL_METRICS_EXEMPLAR_FILTER=trace_based
~~~

In this example, the Collector runs on the same host, Pod, or Cloud Run instance and listens on gRPC port 4317. If the Collector runs elsewhere, update the endpoint to a reachable internal address. Never expose an OTLP receiver to the public Internet without authentication, TLS, and network controls.

The Java agent auto-instruments supported frameworks. To create spans and metrics capturing custom business rules, the application uses the OpenTelemetry API. Add the `opentelemetry-api` dependency matching your standardized Java agent/SDK version; do not initialize a second standalone SDK when the agent already manages the global OpenTelemetry instance.

### 3.2. Creating a Span and Histogram in the Same Context

The service example below creates a `payment.authorize` span, logs while the span is active, and records metrics before ending the span. Imports are streamlined to focus on telemetry flow.

~~~java
import io.opentelemetry.api.GlobalOpenTelemetry;
import io.opentelemetry.api.common.AttributeKey;
import io.opentelemetry.api.common.Attributes;
import io.opentelemetry.api.metrics.DoubleHistogram;
import io.opentelemetry.api.metrics.LongCounter;
import io.opentelemetry.api.trace.Span;
import io.opentelemetry.api.trace.StatusCode;
import io.opentelemetry.context.Context;
import io.opentelemetry.context.Scope;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class PaymentService {
    private static final Logger logger =
        LoggerFactory.getLogger(PaymentService.class);

    private static final String INSTRUMENTATION_SCOPE =
        "com.example.checkout";

    private final io.opentelemetry.api.trace.Tracer tracer =
        GlobalOpenTelemetry.get().getTracer(INSTRUMENTATION_SCOPE);

    private final io.opentelemetry.api.metrics.Meter meter =
        GlobalOpenTelemetry.get().getMeter(INSTRUMENTATION_SCOPE);

    private final DoubleHistogram authorizationDuration =
        meter.histogramBuilder("payment.authorization.duration")
            .setDescription("Duration calling payment provider")
            .setUnit("s")
            .build();

    private final LongCounter authorizationCalls =
        meter.counterBuilder("payment.authorization.calls")
            .setDescription("Number of calls to payment provider")
            .build();

    public void authorize(String orderId) {
        Span span = tracer.spanBuilder("payment.authorize").startSpan();
        long startNanos = System.nanoTime();
        String result = "error";

        try (Scope scope = span.makeCurrent()) {
            span.setAttribute("payment.provider", "demo");

            try {
                logger.info(
                    "payment_authorization_started orderId={}", orderId);

                callPaymentProvider(orderId);

                result = "success";
                span.setStatus(StatusCode.OK);
                logger.info(
                    "payment_authorization_completed orderId={}", orderId);
            } catch (RuntimeException exception) {
                span.recordException(exception);
                span.setStatus(StatusCode.ERROR);
                logger.error(
                    "payment_authorization_failed orderId={}",
                    orderId,
                    exception);
                throw exception;
            } finally {
                Attributes attributes = Attributes.of(
                    AttributeKey.stringKey("provider"), "demo",
                    AttributeKey.stringKey("result"), result
                );

                // Context.current() holds the active payment.authorize span.
                Context context = Context.current();

                authorizationCalls.add(1, attributes, context);

                double elapsedSeconds =
                    (System.nanoTime() - startNanos) / 1_000_000_000.0;

                // Pass context so the SDK can attach an exemplar to the current span.
                authorizationDuration.record(
                    elapsedSeconds, attributes, context);
            }
        } finally {
            span.end();
        }
    }

    private void callPaymentProvider(String orderId) {
        // Replace with actual HTTP/gRPC call in the application.
    }
}
~~~

When an HTTP request enters the controller, the Java agent starts a server span. Because `spanBuilder(...).startSpan()` defaults to the current context as parent, the `payment.authorize` span becomes a child span of the request. `span.makeCurrent()` binds the business span to the current context; every log and metric recorded inside that scope can share the same trace context.

In the code, metrics only use attributes with bounded value sets such as `provider` and `result`. Do not add `orderId`, email, request ID, or trace ID to metric labels, because each unique value spawns a new time series and inflates cardinality.

### 3.3. Propagating Context Across Downstream Calls

When the Java agent instruments supported HTTP clients, it automatically injects the W3C `traceparent` header into outbound requests. The receiving service reads this header and creates a child span if it is also instrumented.

Illustrative W3C Trace Context header:

~~~text
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
~~~

Here, the trace ID remains constant across the request; the span ID changes at each operation; and the trailing flags indicate trace flags, including sampled status. Never generate a brand-new trace ID per service when those services are processing the same request.

For asynchronous work, context does not always follow automatically across executors or threads. Capture context where work is submitted and restore it in the worker. Example with Java OpenTelemetry Context:

~~~java
Context captured = Context.current();

executor.submit(captured.wrap(() -> {
    logger.info("background task started");
    processMessage();
}));
~~~

With Pub/Sub or message brokers, propagate trace context in message attributes/headers using W3C Trace Context and extract it in the consumer. If a message represents multiple requests or fans in from multiple sources, span links may be needed instead of forcing everything into a simple parent-child relationship.

## 4. Linking Logs with Traces via Structured Logging

The OpenTelemetry Java Agent can inject active span details into the MDC (Mapped Diagnostic Context) of supported logging frameworks. With Logback or Log4j2, commonly populated fields are:

- `trace_id`: trace ID of the current span.
- `span_id`: span ID of the current span.
- `trace_flags`: trace flags of the current context.

For Cloud Logging to automatically link logs to traces, JSON logs must include the corresponding special fields:

| JSON Field | Meaning |
| --- | --- |
| `logging.googleapis.com/trace` | Trace resource name, typically formatted as `projects/PROJECT_ID/traces/TRACE_ID`. |
| `logging.googleapis.com/spanId` | 16-character hexadecimal span ID. |
| `logging.googleapis.com/trace_sampled` | Boolean indicating whether the trace was sampled for storage. |

Example JSON log after a logging layout maps MDC fields to Cloud Logging special fields:

~~~json
{
  "severity": "INFO",
  "message": "Payment authorization completed",
  "event": "payment_authorization_completed",
  "service": "checkout-api",
  "environment": "lab",
  "order_id": "order-demo-42",
  "logging.googleapis.com/trace": "projects/PROJECT_ID/traces/4bf92f3577b34da6a3ce929d0e0e4736",
  "logging.googleapis.com/spanId": "00f067aa0ba902b7",
  "logging.googleapis.com/trace_sampled": true
}
~~~

This illustrates the output structure. In a real application, use Log4j2 JSON Template Layout or an equivalent logging configuration to read `trace_id`, `span_id`, and `trace_flags` from MDC and map them to Cloud Logging's fields. The sampled bit in `trace_flags` must be converted to a boolean `true` or `false`. Google Cloud provides a `GcpLayout.json` template for Log4j2. Simply writing `trace_id` as an ordinary JSON field without mapping it to `logging.googleapis.com/trace` lets Logs Explorer display the log but will not create the expected trace link.

If logs are sent directly via the Cloud Logging client library, set `trace`, `spanId`, and `traceSampled` on `LogEntry`. If logs are sent via OTLP Logs, ensure `LogRecord` is emitted inside the active OpenTelemetry Context holding the span; trace ID and span ID travel with the log record. For applications using traditional logging frameworks, structured JSON to stdout is simple and common: Cloud Run/GKE collects stdout/stderr automatically; on Compute Engine, use Ops Agent or an appropriate log collection agent.

Never log access tokens, session cookies, passwords, full payment details, or personal data. Trace IDs and order IDs in this example serve solely for correlation and illustration; in production, select non-sensitive business identifiers and restrict log read permissions.

## 5. Linking Metrics with Traces via Exemplars

Metrics are aggregated data. A histogram may record thousands of measurements over an interval, yet the chart displays only the distribution. An exemplar is a representative sample measurement tagged with the corresponding request's trace ID. This lets operators click a point on a latency chart and open a sample request's trace.

To generate exemplars from OpenTelemetry:

1. Configure both the OpenTelemetry trace SDK and metric SDK.
2. Record metrics while a span is active.
3. Pass `Context.current()` from the span into the metric recording call.
4. Use a histogram/distribution metric and configure an appropriate exemplar filter, typically `trace_based`.
5. Ensure traces are sampled and exported successfully; an exemplar cannot open a trace that was never stored.

In the service example from section 3, the following call runs inside `span.makeCurrent()`:

~~~java
authorizationDuration.record(
    elapsedSeconds,
    attributes,
    Context.current()
);
~~~

This detail is decisive. Omitting context and calling `authorizationDuration.record(elapsedSeconds)` still records the measurement in the histogram, but the SDK lacks the span context needed to attach an exemplar pointing to the trace.

In Cloud Monitoring, histograms/distributions are typically rendered as heatmaps. When metric data points carry exemplars, charts render markers; clicking a marker reveals sample details and opens the linked trace. Never add trace ID to metric labels as a substitute for exemplars. Trace IDs have extreme cardinality and make metrics unaggregatable.

Exemplars are representative samples, not links to every metric write. Therefore, not every single request appears as a dot on the chart. Exemplar counts also depend on sampling, the exemplar reservoir, metric type, and backend storage/rendering behavior.

## 6. Collecting and Exporting Telemetry with OpenTelemetry Collector

The Collector receives OTLP from applications, applies processors, and sends telemetry to the Google Cloud Telemetry API. This keeps applications relatively backend-neutral; the Collector handles authentication and export.

### 6.1. Minimal Collector Configuration for the Lab

The following example illustrates an OTLP gRPC receiver and an OTLP gRPC exporter to Google Cloud. Use the Google-Built OpenTelemetry Collector, which bundles the Google Cloud authentication extension. This is a learning configuration to clarify telemetry flow; production deployments should start from Google-Built Collector's recommended config and retain necessary processors, health checks, resource detection, memory limiters, and batch settings.

~~~yaml
receivers:
  otlp:
    protocols:
      grpc:
        endpoint: 0.0.0.0:4317

processors:
  memory_limiter:
    check_interval: 1s
    limit_percentage: 65
    spike_limit_percentage: 20
  batch:
    timeout: 5s

exporters:
  otlp_grpc:
    endpoint: telemetry.googleapis.com:443
    balancer_name: pick_first
    auth:
      authenticator: googleclientauth

extensions:
  googleclientauth:

service:
  extensions: [googleclientauth]
  pipelines:
    traces:
      receivers: [otlp]
      processors: [memory_limiter, batch]
      exporters: [otlp_grpc]
    metrics:
      receivers: [otlp]
      processors: [memory_limiter, batch]
      exporters: [otlp_grpc]
    logs:
      receivers: [otlp]
      processors: [memory_limiter, batch]
      exporters: [otlp_grpc]
~~~

The `logs` pipeline above receives log records sent over OTLP. If your application writes JSON to stdout, ensure the platform or a filelog receiver collects that stdout; no receiver in this minimal configuration reads log files directly. Regardless of path, logs must preserve trace context or special fields to link with traces.

With the Google-Built Collector, the `otlp_grpc` exporter sends telemetry to `telemetry.googleapis.com:443` and uses `googleclientauth` to authenticate via ADC/service identity. Run the Collector under an identity with appropriate write permissions. Binding receivers to `0.0.0.0` should only be used inside controlled internal networks; restrict access to ports 4317/4318 to trusted workloads.

### 6.2. Choosing a Path for Logs

Two common patterns exist:

| Log Collection Method | Flow | When to Use |
| --- | --- | --- |
| Structured stdout | Java logger → JSON stdout → Cloud Run/GKE logging agent or Ops Agent → Cloud Logging | Application already uses SLF4J/Logback/Log4j2 and wants to keep its existing logging framework. |
| OTLP Logs | OTel Logs SDK/appender → OTLP receiver → Collector → Telemetry API | Want to send OTel-standard LogRecords through the same Collector pipeline. |

Avoid shipping the exact same log through both a stdout agent and an OTLP pipeline unless intentionally deduplicating. Choose one primary delivery path and verify trace context is preserved along it.

### 6.3. Flushing and Application Lifecycle

When an application or Collector shuts down, buffered batch data may not yet be exported. The SDK must shut down cleanly to flush processors/exporters; the Collector also needs shutdown signals and time to drain batches. For terminated containers, configure a termination grace period long enough for both the application and Collector to flush cleanly.

Monitor the Collector itself using health checks and self-observability metrics. If the Collector runs out of memory, fails authentication, or loses connectivity to the Telemetry API, all three signals can disappear even while the application keeps running.

## 7. End-to-End Practice

Use a Spring Boot endpoint that invokes the payment step. Suppose a controller exposes `GET /orders/{id}` and calls `paymentService.authorize(id)`.

### Step 1: Run the Application and Collector

- Start the Collector with the configuration from section 6.
- Launch Spring Boot with the OpenTelemetry Java Agent.
- Set `OTEL_SERVICE_NAME=checkout-api`, resource attributes for environment/version, and the OTLP endpoint pointing to the Collector.
- Ensure the Collector's service account has telemetry write permissions.

### Step 2: Generate Test Traffic

Send several successful requests and a few controlled failing requests. For example:

~~~bash
curl http://localhost:8080/orders/order-demo-42
curl http://localhost:8080/orders/order-demo-43
curl http://localhost:8080/orders/order-demo-fail?simulateFailure=true
~~~

Adjust routes and failure simulation to match your sample app. Never use real production data for testing.

### Step 3: Verify Traces

In Google Cloud Console:

1. Open **Trace → Trace Explorer**.
2. Select the project and the time window covering your test requests.
3. Filter by service `checkout-api` or search for the `payment.authorize` span.
4. Open a trace and confirm the HTTP server span is the parent of the business span.
5. If requests call downstream services, confirm the trace ID is preserved and downstream spans appear.

### Step 4: Verify Linked Logs

Open **Logging → Logs Explorer** and filter by service and event:

~~~text
resource.type="cloud_run_revision"
jsonPayload.service="checkout-api"
jsonPayload.event="payment_authorization_completed"
~~~

If running on GKE or Compute Engine, adapt `resource.type` and fields to your actual resource type. Open a log entry and check the `trace` and `spanId` fields. Click the trace link or open Trace Explorer by trace ID to inspect the matching waterfall.

If logs lack special fields, check your logging layout and MDC mapping. If logs are sent over OTLP, verify `LogRecord` carries trace context. Putting `trace_id` inside plain message text alone will not create automatic links.

### Step 5: Verify Metrics and Exemplars

Open **Monitoring → Metrics Explorer**:

1. Search for `payment.authorization.duration` or the mapped OTLP metric name.
2. Select a histogram/distribution chart and the lab time range.
3. Verify the metric has data and resource labels accurately identify service/environment.
4. If exemplars appear, click a marker on the heatmap to open the sample trace.
5. Cross-check the trace with logs sharing the same trace ID and span ID.

Missing exemplars do not necessarily mean metric export failed. Check first whether measurements were recorded inside an active span, context was passed, the span was sampled and exported, the metric is a histogram/distribution, and the exemplar filter is enabled.

## 8. Querying and Cross-Referencing All Three Signals

Once data is flowing, use shared fields to pivot from one signal to another.

| Goal | Starting Point | Fields Used to Correlate |
| --- | --- | --- |
| Open trace from log | Logs Explorer | `trace`, `spanId`, `traceSampled` |
| Find logs from trace | Trace Explorer → Logs & Events | Trace ID, span ID, and time window |
| Open trace from metric | Metrics Explorer histogram exemplar | Trace ID inside exemplar |
| Find errors by service version | Logs Explorer or Metrics Explorer | `service.name`, `service.version`, environment |
| Follow request across services | Trace Explorer | Trace ID, parent span ID, and span links |

Example filtering logs for a specific trace in Logs Explorer:

~~~text
trace="projects/PROJECT_ID/traces/TRACE_ID"
~~~

Example filtering service error logs in a time range:

~~~text
resource.type="cloud_run_revision"
severity>=ERROR
jsonPayload.service="checkout-api"
jsonPayload.environment="production"
~~~

Fields inside `jsonPayload` depend on the log schema emitted by your application. `trace` is a top-level LogEntry field; do not confuse it with `jsonPayload.trace_id` if the application only writes trace ID as an ordinary JSON attribute.

## 9. Troubleshooting Common Correlation Issues

| Symptom | Possible Cause | What to Check |
| --- | --- | --- |
| Trace exists, but logs aren't linked | Logging layout omits trace/span special fields; log written outside active span. | Check MDC, `logging.googleapis.com/trace`, `spanId`, and where logging happens. |
| Log has trace ID, but Trace Explorer can't find trace | Trace not sampled/exported, wrong project ID, or exporter error. | Check `trace_sampled`, Collector logs, ADC, and trace ID. |
| Each service starts its own trace | Trace context not propagated via HTTP or message metadata. | Check `traceparent`, propagators, and client/server instrumentation. |
| Metric has data, but no exemplars | Histogram recorded outside span, Context not passed, trace unsampled, or exemplar filter disabled. | Record metric inside span, pass context, and check exemplar configuration. |
| Async worker logs lack parent trace | Context lost across thread switch or queue. | Capture/restore Context or inject/extract W3C context via message attributes. |
| Only partial telemetry reaches Google Cloud | Collector pipeline missing a signal, exporter error, missing IAM role, or unflushed batch. | Check receivers/pipelines/exporters, write permissions, health endpoint, and shutdown. |
| Logs appear twice | Same record shipped via both stdout agent and OTLP Logs. | Pick one primary collection path or deliberately filter duplicates. |
| Metric dashboard has too many time series | Unique IDs used as metric attributes. | Remove user/request/trace IDs from metric labels; keep IDs in logs/traces. |

A trace may not be saved even though logs are still recorded. If sampling drops a trace, logs can still carry its trace ID, yet clicking the trace link yields no trace. This is expected behavior when sampling is enabled, not necessarily a logging bug.

## 10. Operational Best Practices

- **Use consistent resource identity:** `service.name`, namespace, version, and environment must match across logs, metrics, and traces.
- **Propagate context end to end:** use W3C Trace Context for HTTP and message metadata; ensure context is restored in async workers.
- **Log inside the right span:** log errors inside the span executing the dependency or business step so span ID pinpoints where the failure originated.
- **Use exemplars for metrics:** record histograms inside active spans and pass context; never put trace IDs in metric labels.
- **Keep metric cardinality low:** use route templates, status classes, providers, and results with bounded value sets.
- **Design intentional sampling:** important investigative traces must have a chance to be stored; downstream services must honor incoming sampling context.
- **Protect data:** never log secrets or sensitive personal data; enforce least-privilege IAM and protect OTLP endpoints and log storage.
- **Monitor the pipeline:** track Collector health, memory, export errors, dropped spans/metrics/logs, and batch latency.
- **Verify after release:** send a test request and verify all three signals, trace-log links, and metric exemplars in staging before broad rollout.

## 11. Lab Completion Checklist

- [ ] Enabled Logging, Monitoring, Trace, and Telemetry APIs.
- [ ] Granted telemetry write permissions to the Collector's service account.
- [ ] Launched the application with the OpenTelemetry Java Agent and configured OTLP endpoint.
- [ ] Confirmed server span and business span `payment.authorize` appear in the same trace.
- [ ] Propagated trace context across downstream calls or message metadata.
- [ ] Emitted JSON logs inside active spans and mapped trace/span to Cloud Logging special fields.
- [ ] Recorded histogram metrics inside active spans with `Context.current()`.
- [ ] Enabled trace-based exemplar filter and verified exemplars on the histogram.
- [ ] Opened the trace from both a log entry and an exemplar.
- [ ] Checked Collector health, IAM permissions, sampling, and cardinality.
- [ ] Tested a failing request and verified logs, span status, exceptions, and metrics reflect the failure accurately.

## References

- [Java instrumentation sample for Cloud Trace](https://docs.cloud.google.com/trace/docs/setup/java-ot) — using OpenTelemetry Java Agent, configuring structured JSON logs, and linking logs with traces.
- [Link log entries with traces](https://docs.cloud.google.com/trace/docs/trace-log-integration) — `trace`, `spanId`, `traceSampled` fields and linking log entries.
- [Correlate metrics and traces by using exemplars](https://docs.cloud.google.com/stackdriver/docs/instrumentation/advanced-topics/exemplars) — requirements for generating exemplars from metric measurements and span context.
- [Google-Built OpenTelemetry Collector](https://docs.cloud.google.com/stackdriver/docs/instrumentation/google-built-otel) — Collector, receivers, processors, and exporters for Google Cloud.
- [Collector-based instrumentation samples](https://docs.cloud.google.com/trace/docs/setup/sample-overview) — OTLP architecture, IAM permissions, APIs, and Java samples.
- [Choose an instrumentation approach](https://docs.cloud.google.com/stackdriver/docs/instrumentation/choose-approach) — choosing between collector-based export and direct export.
- [Structured logging](https://docs.cloud.google.com/logging/docs/structured-logging) — JSON payloads and Cloud Logging special fields.
- [OpenTelemetry Java SDK](https://opentelemetry.io/docs/languages/java/sdk/) — SDK, tracer provider, meter provider, logger provider, and context propagation.
- [OpenTelemetry Java instrumentation](https://opentelemetry.io/docs/languages/java/instrumentation/) — agent, instrumentation libraries, and context propagation.
