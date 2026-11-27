# `SdkLoggerProvider`

In the **OpenTelemetry** chapter of the **SPRING_BOOT_OBSERVABILITY** module, `SdkLoggerProvider` is the central OpenTelemetry Java SDK component used to create loggers that emit log records. The provider manages shared configuration such as resource, instrumentation scope, and log record processors. Processors receive records, handle them according to policy, and forward them to an exporter or the next destination.

When setting up observability for Spring Boot using **Micrometer Observation, metrics, logs, and distributed tracing**, the logs pipeline must be understood separately. Micrometer Observation helps measure operations and produce spans/metrics via handlers; SLF4J/Logback continues accepting application log statements; and the OpenTelemetry Logs SDK provides a standard API and pipeline for emitting log records to a Collector/backend. **Configuring OTLP tracing does not automatically mean logs are exported over OTLP.**

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain the role of `SdkLoggerProvider` in the OpenTelemetry Logs SDK.
2. Distinguish `LoggerProvider`, `Logger`, `LogRecordBuilder`, `LogRecordProcessor`, and `LogRecordExporter`.
3. Understand how Resource attributes and instrumentation scope are attached to log records.
4. Configure an exporter with a batch processor to export logs over OTLP.
5. Manage provider lifecycles and close resources on application shutdown.
6. Distinguish logging via SLF4J/Logback from emitting log records via the OpenTelemetry API.
7. Choose how to integrate the logging framework with OpenTelemetry in Spring Boot.
8. Inspect logs in the exporter/Collector/backend and isolate pipeline failures.
9. Control attributes, cardinality, sensitive data, batching, and storage costs.
10. Combine logs with trace context, metrics, and distributed tracing for incident investigation.

## 2. `SdkLoggerProvider` in the Logs Pipeline

| Component | Responsibility |
| --- | --- |
| **`SdkLoggerProvider`** | Creates `Logger` instances, manages `Resource`, configures `LogRecordProcessor`s, and applies shared policies. |
| **`Logger`** | Creates log records scoped to an instrumentation scope. |
| **`LogRecordBuilder`** | Builds a record with body, severity, timestamp, and attributes before emitting. |
| **`LogRecordProcessor`** | Receives records and processes them; can forward immediately or batch before export. |
| **`LogRecordExporter`** | Sends records to a destination such as an OTLP receiver. |
| **`Resource`** | Describes the telemetry source: service name, version, environment. |
| **`Instrumentation scope`** | Describes the library/module emitting telemetry, typically including name and version. |

~~~mermaid
flowchart LR
    App["Application / instrumentation"] --> Provider["SdkLoggerProvider"]
    Provider --> Logger["Logger"]
    Logger --> Builder["LogRecordBuilder"]
    Builder --> Emit["emit()"]
    Emit --> Processor["LogRecordProcessor"]
    Processor --> Exporter["LogRecordExporter"]
    Exporter --> Collector["OTLP Collector"]
    Collector --> Backend["Logs backend"]
~~~

The provider creates loggers and wires processors to exporters. The logger creates records; the processor decides whether records are handled immediately or batched; the exporter transports them. The Collector/backend receives, processes, stores, and indexes the data for querying.

**`SdkLoggerProvider` is neither a logging backend nor a Logback appender.** It is one part of the SDK pipeline. For log statements written with SLF4J/Logback to enter the OpenTelemetry pipeline, a corresponding integration component—such as an appender/bridge—is required. Creating `SdkLoggerProvider` alone without code calling the OpenTelemetry Logger API or a logging bridge will not route normal log calls into this pipeline.

## 3. Resource and Instrumentation Scope

### Resource Describes the Service Emitting Telemetry

Attaching a Resource to the provider helps the backend identify which service, version, and environment emitted the data:

~~~java
Resource resource = Resource.getDefault().merge(
        Resource.create(Attributes.of(
                AttributeKey.stringKey("service.name"), "order-api",
                AttributeKey.stringKey("service.version"), "1.4.2",
                AttributeKey.stringKey("deployment.environment"), "production"
        ))
);
~~~

This is an illustrative example. In real environments, do not hard-code version/environment in source if they vary per deployment; supply them via environment variables, build metadata, or platform configuration.

Keep resource identity stable:
- `service.name` is consistent across logs, metrics, and traces.
- `service.version` indicates the running release.
- `environment`/`namespace` filters data by environment.
- `host`/`pod`/`instance` attributes are added only when genuinely useful.

Do not put user ID, request ID, order ID, or per-request values into Resource. Resource describes the telemetry-emitting entity; request-specific information belongs in the log record or span.

### Instrumentation Scope Describes Where Records Originate

A `Logger` is obtained from the provider with a scope name. The scope can be the library or module producing log records, not necessarily identical to the service name:

~~~java
Logger logger = loggerProvider.get("com.example.order.instrumentation");
~~~

If a scope version is needed, use the API matching your project's OpenTelemetry SDK version. Do not embed request IDs or customer names into instrumentation scope; scope is relatively static metadata.

## 4. Creating `SdkLoggerProvider` and an OTLP Exporter

Java example illustrating OpenTelemetry Logs SDK configuration with an OTLP gRPC exporter and batch processor. Exact APIs/packages should be managed under a single compatible OpenTelemetry BOM version:

~~~java
import java.time.Duration;

import io.opentelemetry.api.common.AttributeKey;
import io.opentelemetry.api.common.Attributes;
import io.opentelemetry.api.logs.Logger;
import io.opentelemetry.api.logs.Severity;
import io.opentelemetry.exporter.otlp.logs.OtlpGrpcLogRecordExporter;
import io.opentelemetry.sdk.OpenTelemetrySdk;
import io.opentelemetry.sdk.logs.SdkLoggerProvider;
import io.opentelemetry.sdk.logs.export.BatchLogRecordProcessor;
import io.opentelemetry.sdk.resources.Resource;

public final class LogsSdkExample {

    public static void main(String[] args) {
        Resource resource = Resource.getDefault().merge(
                Resource.create(Attributes.of(
                        AttributeKey.stringKey("service.name"), "order-api",
                        AttributeKey.stringKey("service.version"), "1.4.2"
                ))
        );

        var exporter = OtlpGrpcLogRecordExporter.builder()
                .setEndpoint("http://localhost:4317")
                .setTimeout(Duration.ofSeconds(5))
                .build();

        var processor = BatchLogRecordProcessor.builder(exporter)
                .setScheduleDelay(Duration.ofSeconds(1))
                .setMaxQueueSize(2048)
                .setMaxExportBatchSize(512)
                .build();

        SdkLoggerProvider loggerProvider =
                SdkLoggerProvider.builder()
                        .setResource(resource)
                        .addLogRecordProcessor(processor)
                        .build();

        OpenTelemetrySdk openTelemetry = OpenTelemetrySdk.builder()
                .setLoggerProvider(loggerProvider)
                .build();

        Logger logger = openTelemetry.getLogsBridge()
                .get("com.example.order");

        logger.logRecordBuilder()
                .setSeverity(Severity.INFO)
                .setSeverityText("INFO")
                .setBody("Order validation completed")
                .setAttribute(AttributeKey.stringKey("operation"), "validate")
                .setAttribute(AttributeKey.stringKey("outcome"), "success")
                .emit();

        loggerProvider.close();
    }
}
~~~

This standalone provider example demonstrates the individual components. In a Spring Boot application, never create a new provider per request or per service call. The provider should be instantiated once, shared across the application context, and closed on application shutdown. For servers, ensure shutdown hooks/lifecycles invoke close only after log-emitting work has finished.

Notes:

- The sample gRPC endpoint uses `localhost` port `4317`; the Collector must enable an OTLP gRPC receiver on that address.
- If using OTLP/HTTP, choose the matching HTTP exporter and configure the proper logs endpoint/path. Do not simply change the port number in the URL without changing the transport.
- The batch processor groups records before export to reduce network overhead; tune parameters based on throughput, memory, and acceptable latency.
- Keep SDK versions and package names aligned; avoid mixing arbitrary exporter/API versions.
- Production requires TLS/auth and secret management; plain HTTP `localhost` is for controlled labs only.

### Why Use `BatchLogRecordProcessor`?

The batch processor suits server applications producing high volumes of log records. It buffers records before export to avoid per-record network overhead. In trade-off, records remain queued briefly and must be flushed cleanly at shutdown.

A batch processor requires bounded queue and batch sizes. If the queue fills up or the exporter fails continuously, new records can be dropped. Monitor exporter failures, queue pressure, and dropped records using the diagnostics available in your SDK/version.

A synchronous processor can be convenient in tests or debugging because records ship immediately. However, exporting synchronously on the logging path increases business thread latency and couples application stability to backend availability. Never default to synchronous export in production without capacity testing.

## 5. Emitting Log Records via the OpenTelemetry API

Once a provider exists, obtain a logger for an instrumentation scope and emit a record:

~~~java
Logger logger = loggerProvider.get("com.example.payment");

logger.logRecordBuilder()
        .setSeverity(Severity.WARN)
        .setSeverityText("WARN")
        .setBody("Payment authorization requires review")
        .setAttribute(AttributeKey.stringKey("payment.operation"), "authorize")
        .setAttribute(AttributeKey.stringKey("payment.outcome"), "review")
        .emit();
~~~

Components of a log record:

- **Body:** log message text or an API-supported data type.
- **Severity:** level such as `TRACE`, `DEBUG`, `INFO`, `WARN`, `ERROR`.
- **Severity text:** original level label if preserving the source logging framework's naming.
- **Attributes:** structured fields for searching and filtering.
- **Timestamp/observed timestamp:** when the event occurred and/or when the SDK observed it, depending on API.
- **Trace context:** trace ID, span ID, and flags if emitted within an active tracing context and supported by SDK context integration.

Do not log one long unstructured sentence expecting the backend to parse every field. Use attributes for stable, meaningful fields while controlling cardinality and sensitive data.

### Severity Reflects Operational Meaning

Do not log every business rejection at `ERROR` if the system treats it as a normal outcome. A transaction declined for insufficient limit might be `WARN` or `INFO` depending on semantics. Downstream connection failures or unhandled exceptions generally warrant higher severity. Align conventions across services so alerts and queries stay meaningful.

## 6. Creating the Provider as a Spring Bean and Managing Lifecycle

In Spring Boot, the provider's lifecycle should match the application's lifecycle. Conceptual configuration example:

~~~java
import java.time.Duration;

import io.opentelemetry.api.common.AttributeKey;
import io.opentelemetry.api.common.Attributes;
import io.opentelemetry.exporter.otlp.logs.OtlpGrpcLogRecordExporter;
import io.opentelemetry.sdk.logs.SdkLoggerProvider;
import io.opentelemetry.sdk.logs.export.BatchLogRecordProcessor;
import io.opentelemetry.sdk.resources.Resource;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class OpenTelemetryLogsConfiguration {

    @Bean(destroyMethod = "close")
    SdkLoggerProvider sdkLoggerProvider() {
        Resource resource = Resource.getDefault().merge(
                Resource.create(Attributes.of(
                        AttributeKey.stringKey("service.name"), "order-api"
                ))
        );

        var exporter = OtlpGrpcLogRecordExporter.builder()
                .setEndpoint("http://otel-collector:4317")
                .setTimeout(Duration.ofSeconds(5))
                .build();

        var processor = BatchLogRecordProcessor.builder(exporter)
                .setScheduleDelay(Duration.ofSeconds(1))
                .build();

        return SdkLoggerProvider.builder()
                .setResource(resource)
                .addLogRecordProcessor(processor)
                .build();
    }
}
~~~

This bean illustrates the lifecycle of a standalone `SdkLoggerProvider`. **Do not add this configuration blindly to an application whose OpenTelemetry SDK is already managed by Spring Boot, an agent, or another starter.** Two separate providers can route logs and traces down different pipelines, causing duplicates, missing context, or shutdown issues.

Before defining your own bean, identify who owns the `OpenTelemetry` instance and providers in the application. If a unified SDK already exists, register the logger provider inside that SDK or use its corresponding autoconfiguration mechanism. Create an independent provider only intentionally after verifying it does not establish a competing pipeline.

### Where to Close the Provider

Declaring `destroyMethod = "close"` lets Spring close the provider when the application context shuts down. Closing the provider flushes processors and shuts down exporters per SDK implementation. Never close the provider after individual log statements or while requests are still running.

When initialized manually outside Spring, use `try/finally` or a clear lifecycle owner. On shutdown, allow in-flight requests to finish per graceful shutdown policy before closing the logs pipeline.

## 7. `SdkLoggerProvider` and SLF4J/Logback in Spring Boot

Most Spring Boot applications log like this:

~~~java
private static final Logger log =
        LoggerFactory.getLogger(OrderService.class);

log.info("Order accepted: {}", orderId);
~~~

This uses the SLF4J logging facade backed by a logging framework such as Logback. The snippet above **does not automatically invoke the OpenTelemetry Logs API `Logger`** just because `SdkLoggerProvider` is on the classpath.

Two common integration approaches:

| Approach | How It Works | When Appropriate |
| --- | --- | --- |
| Call OpenTelemetry Logs API directly | Code uses the OpenTelemetry `Logger` to emit structured log records. | Instrumentation/libraries needing to emit structured OTel log records directly. |
| Bridge/appender from logging framework | SLF4J/Logback remains the logging API; an appender/bridge forwards events into the OpenTelemetry pipeline. | Applications with existing log statements that want to preserve standard logging usage. |

Do not send the same log event through both a legacy appender and an OTel appender and export both if the backend has no deduplication policy. That creates duplicate records and extra cost.

### Do Not Confuse with Micrometer Tracing Log Correlation

Micrometer Tracing can inject trace ID and span ID into logging context/MDC. A log pattern printing trace IDs links logs with traces, yet **correlation is not OTLP log export**. Logs might still be collected by an agent, appender, or separate pipeline.

Likewise, an OTLP tracing exporter shipping spans does not automatically ship SLF4J events as OTLP logs. To deliver logs to the same Collector, configure a dedicated logs pipeline and confirm the Collector enables the matching logs receiver/exporter.

## 8. Trace Context in Log Records

A log record emitted while a trace/span is active can carry trace context so the backend links the log to the trace. This depends on the active context and how the logging API/bridge reads context.

Useful fields:
- Trace ID to locate the distributed trace.
- Span ID to pinpoint the span associated with the event.
- Service name/version to filter by service.
- Operation, outcome, and error category with controlled values.
- Timestamp to align timelines across logs, metrics, and spans.

Do not generate random trace IDs and attach them as if they were real trace context. If a separate correlation ID is needed, give it its own field name and never confuse it with the standard Trace ID.

If a log is emitted on a thread without active context, trace ID and span ID may be absent. For async/reactive code, ensure context propagates into the execution context where the log actually fires. Having MDC populated on the calling thread does not prove it propagated to the worker thread.

## 9. Attributes, Cardinality, and Privacy

Log attributes accelerate backend search, yet each attribute adds payload size, indexing cost, and data exposure risk.

| Attribute | Suitability | Notes |
| --- | --- | --- |
| `operation=authorize` | Usually suitable | Bounded value set. |
| `outcome=success/error/review` | Usually suitable | Useful for filtering and breakdowns. |
| `service.name=order-api` | Resource-appropriate | Describes the service, not a request. |
| UUID-style `request.id` | Only with clear purpose | High cardinality; consider dedicated logs with appropriate retention/access. |
| `customer.email` | Avoid by default | Personal data. |
| `authorization` | Never | Credential/secret. |
| Full request body | Avoid by default | May contain PII, secrets, and large payloads. |

Guidelines:
- Record only attributes needed for investigation.
- Use stable field names and consistent data types.
- Never store access tokens, cookies, passwords, API keys, session secrets, or sensitive payment details.
- Mask/redact personal data per policy prior to export.
- Avoid repeatedly logging huge stack traces or massive payloads.
- Apply appropriate retention and access control; logs often carry more sensitive data than metrics.
- Never blindly copy all baggage or gRPC metadata into log records.

Trace sampling does not replace log filtering policies. A log record can still carry sensitive data even when its associated trace was sampled out.

## 10. Batching, Queues, and Exporter Errors

`BatchLogRecordProcessor` reduces per-record overhead but introduces an in-memory queue and can drop records if the queue fills or the exporter repeatedly fails.

Signals to monitor:
- Export successes, failures, and timeouts.
- Queue saturation or dropped log records.
- Batch size and schedule delay.
- Collector accepted, refused, and dropped records.
- Network latency and TLS/authentication errors.
- Backend ingestion rate, storage growth, and indexing delay.

When the exporter cannot connect, never let logging block business requests indefinitely. Timeouts, retries, and queues must be bounded with clear overload behavior. Log observability itself needs independent monitoring; relying solely on logs to alert that the log exporter is losing logs can hide failures.

Increasing queue size delays drops at the cost of higher memory consumption. Diagnose why downstream is slow, adjust batching/throughput or capacity, and keep hard bounds to protect the application.

## 11. Testing `SdkLoggerProvider`

A thorough test verifies that records are created, received by the processor, and delivered to the exporter. Use a mock exporter or an SDK-version-compatible test exporter so unit tests do not depend on a live Collector.

Assertions should cover:
1. Resource attributes include the right service name and version.
2. Instrumentation scope matches the expected module name.
3. Body and severity are accurate.
4. Required attributes are exported with expected types.
5. Trace context is attached when logging inside an active span and supported integration.
6. Provider flush/close does not drop pending records.
7. When the exporter fails, the application does not hang beyond timeout/queue policy.

~~~mermaid
sequenceDiagram
    participant T as Test / Spring Boot app
    participant P as SdkLoggerProvider
    participant E as OTLP exporter
    participant C as Collector
    participant B as Test backend

    T->>P: Emit log record
    P->>E: Processor export batch
    E->>C: OTLP logs request
    C->>B: Forward log record
    B-->>T: Test query finds record
~~~

The Collector accepting a request does not prove the backend indexed the log. End-to-end tests should query the record post-export, or at least verify Collector acceptance and forwarding for the test topology.

### Distinguishing Record Creation Errors from Export Errors

| Outcome | Interpretation |
| --- | --- |
| Cannot obtain a logger | Provider unconfigured/closed or incompatible dependency/API. |
| Record emitted yet exporter never called | Processor not attached, a different provider is active, or processor shut down. |
| Exporter receives record yet Collector does not | Wrong endpoint/transport, TLS/auth failure, network issue, or receiver disabled. |
| Collector receives record yet backend lacks it | Logs pipeline missing matching exporter, record filtered, or backend indexing lag. |
| Backend shows log without trace ID | Log emitted outside active trace context or bridge failed to capture context. |
| Backend shows duplicate records | Log event forwarded by multiple appenders/pipelines simultaneously. |

## 12. Combining `SdkLoggerProvider` with Micrometer Observation

Micrometer Observation models operations and can produce metrics/tracing through handlers. `SdkLoggerProvider` emits logs via the OpenTelemetry Logs API. Both can serve the same operation without replacing one another.

~~~text
Operation: order.authorize
  Observation:
    - Timer / metrics
    - Span / distributed trace
  Log records:
    - authorization started
    - authorization failed
    - attributes: operation, outcome, error.type
~~~

Typical investigation workflow:
1. Metrics reveal a rising error ratio on the payment route.
2. Logs reveal the error type and timestamp, carrying trace ID/span ID when correlation works.
3. Traces reveal which dependency caused the slowdown or failure.
4. Verified low-footprint baggage/attributes help group events by request class or region if needed.
5. After remediation, metrics confirm error ratio and latency return to normal thresholds.

Do not emit a log record for every event merely to replace metrics. Counters/timers fit statistical aggregation; logs fit semantic events; traces fit execution paths. Each signal needs its own granularity and retention.

## 13. Common Pitfalls When Deploying `SdkLoggerProvider`

| Symptom | Possible Cause | Where to Check |
| --- | --- | --- |
| SLF4J logs missing from OTLP | Only `SdkLoggerProvider` created without bridge/appender or direct OTel Logs API calls | Trace path from logging framework to OTel pipeline |
| Traces exist yet logs are empty | Only tracing exporter configured; logs pipeline disabled | Check logger provider, processor, exporter, and Collector logs receiver |
| Provider creates two pipelines | Custom SDK/provider competes with auto-configuration or agent | Establish one lifecycle owner and shared instance |
| Logs missing `service.name` | Resource not attached to provider or wrong SDK instance | Inspect Resource inside payload |
| Logs missing trace ID | No active context or bridge fails to read trace context | Inspect span scope, async propagation, and log instrumentation |
| Duplicate logs appear | Legacy appender and OTel appender both forward events | Review appenders/pipelines and duplicate forwarding |
| Logs lost on shutdown | Processor not flushed/closed in lifecycle or shutdown too abrupt | Manage provider lifecycle and graceful shutdown |
| Queue full | Slow Collector/backend, timeouts, or insufficient throughput | Check queue, exporter retries, batch size, and capacity |
| Collector receives logs yet backend misses them | Logs pipeline filters/drops or backend ingestion/indexing fails | Inspect Collector pipeline and backend |
| Payloads contain PII/secrets | Attributes/body logged unfiltered | Redact at source and processors; review access/retention |

## 14. Runbook: Logs Do Not Appear in the Backend

1. **Identify log source:** is code calling SLF4J/Logback or the OpenTelemetry Logger API?
2. **Check provider:** is the right `SdkLoggerProvider` created and are loggers retrieved from that provider?
3. **Check processor:** was the batch/simple processor attached before building the provider?
4. **Check exporter:** are endpoint, protocol, TLS, credentials, and timeouts valid?
5. **Check Collector:** is the logs receiver enabled and does the logs pipeline have the right processors/exporters?
6. **Check backend:** check ingestion, filtering, indexing, retention, and query time window.
7. **Check trace correlation:** was the log emitted inside an active span/context or on another thread?
8. **Check duplication or filtering:** are legacy appenders, bridges, or Collector processors dropping/duplicating events?
9. **Test shutdown:** emit a record, flush/close the provider properly, and confirm the final record exports.
10. **Check security:** confirm credentials/TLS are right and payloads stay free of prohibited secrets/PII.

Find the first boundary lacking evidence rather than immediately adding dependencies or creating another provider. A pipeline may ingest traces cleanly while still lacking logs configuration.

## 15. Self-Check Exercises

### Exercise 1 — Is a Provider Enough for SLF4J?

An application creates an `SdkLoggerProvider` and OTLP exporter. Services still call only SLF4J `Logger`. Can we conclude logs are exported?

**Answer:** No. A logging bridge/appender or integration is required to forward log events from SLF4J/Logback into the OpenTelemetry Logs pipeline. Creating the provider alone does not intercept standard logging calls.

### Exercise 2 — Traces Exist, Logs Missing

The backend finds spans for `order-api` but no log records. What should be checked first?

**Answer:** Tracing exporter and logs exporter are separate pipelines. Check `SdkLoggerProvider`, `LogRecordProcessor`, exporter, and the Collector's logs receiver/pipeline.

### Exercise 3 — Why Not Create a Provider Per Request?

A service builds a new `SdkLoggerProvider` per request just to put request ID into Resource. What is wrong with this design?

**Answer:** Resource describes the service/process, not individual requests. Creating providers continuously adds overhead, spawns multiple exporters/processors, complicates closing, and risks losing logs. Request metadata belongs in appropriate log attributes/context with cardinality and privacy controls.

### Exercise 4 — Duplicate Logs

A log appears twice in the backend after adding an OTel appender. What might cause this?

**Answer:** The same event is being sent through both a legacy appender and the OTel appender, or multiple bridges/pipelines are forwarding it. Audit logger hierarchy, additivity, and appender forwarding.

### Exercise 5 — Empty Trace ID

A log record is exported without a trace ID or span ID. Does that prove the exporter is broken?

**Answer:** No. The record may have been emitted outside an active span, on a thread that lost context, or via a logger that does not read trace context. Check scope and context propagation before blaming the exporter.

### Exercise 6 — Queue Full

The batch processor drops records when the Collector slows down. Should we make the queue unbounded?

**Answer:** No. An unbounded queue can exhaust application memory. Bound the queue, measure throughput, tune timeouts/retries, batch size, Collector/backend capacity, and overload policies.

## 16. Implementation Checklist

- [ ] Identify logging source: SLF4J/Logback or OpenTelemetry Logs API.
- [ ] `SdkLoggerProvider` is managed by one clear lifecycle owner.
- [ ] Loggers are obtained from the right provider with stable instrumentation scopes.
- [ ] Resource carries appropriate `service.name`/`version`/`environment`.
- [ ] `LogRecordProcessor` is registered before building the provider.
- [ ] Exporter uses the right OTLP transport, endpoint, TLS/auth, and timeout.
- [ ] Batch queue, batch size, and schedule delay are capacity-planned.
- [ ] Spring logging framework has a bridge/appender when forwarding SLF4J events.
- [ ] No independent provider competes with an already managed SDK/agent.
- [ ] Provider flushes/closes cleanly with lifecycle and graceful shutdown.
- [ ] Log body/severity/attributes are structured with controlled cardinality and privacy.
- [ ] Trace context links when records emit inside active spans and supported integrations.
- [ ] Collector has a logs receiver and dedicated logs pipeline, not just a traces pipeline.
- [ ] Unit and end-to-end tests verify records reach the backend.
- [ ] Monitor exporter errors, queue pressure, dropped records, and backend ingestion.
- [ ] Logs, metrics, and traces serve their proper roles in incident runbooks.

**Key takeaway:** `SdkLoggerProvider` is the OpenTelemetry Logs SDK provider: it creates `Logger` instances and connects log records to processors and exporters. In Spring Boot, clarify whether logs originate from SLF4J/Logback or the OpenTelemetry API, manage the provider along the application lifecycle, configure a dedicated OTLP logs pipeline, and verify delivery through the Collector and backend. When logs carry proper resource, severity, attributes, and trace correlation, they complement metrics and distributed tracing to diagnose incidents while keeping costs and sensitive data under control.
