# OpenTelemetry Compatibility: Correlating Java Logging with Trace Context

## 1. The Problem to Solve

In a Java application handling many concurrent requests, log lines are often interleaved. When a request traverses multiple services, looking at timestamps and thread names alone makes it very difficult to tell which logs belong to the same execution flow. **OpenTelemetry (OTel) helps attach tracing context to logs** so operators can find all logs from a trace, or find the trace from an error log line.

For example, consider a request flowing through `api-service → order-service → payment-service`. If all three services propagate the trace context properly, logs emitted during the same request share the same `trace_id`; each span (a measured unit of work) has its own `span_id`. This is **log–trace correlation**.

“OpenTelemetry compatibility” within the scope of Java Logging has three distinct aspects:

1. **Context propagation**: preserving trace context across synchronous calls, across threads/tasks, and across service boundaries.
2. **Attaching context to logs**: injecting the active trace/span IDs into plain-text logs or structured log records.
3. **Collecting and exporting data**: sending logs and traces along with service identity metadata to an observability backend, potentially via OTLP/Collector.

Having `trace_id` in console logs **does not mean** the application is exporting logs over OTLP; conversely, sending logs to a Collector does not guarantee those logs carry trace context if no valid span existed when they were written.

## 2. Components and Terminology

| Component | Meaning in this article |
| --- | --- |
| SLF4J, Logback, Log4j 2, JUL | APIs or frameworks that create and format logs in Java; you can continue using them when integrating OTel. |
| OTel API | Provides `Tracer`, `Span`, `Context`; used by both application code and instrumentation to describe context. |
| OTel SDK | Implements telemetry collection, processing, and export. The API alone does not export data. |
| Java agent / Spring Boot starter | Two ways to deploy automatic instrumentation; choose based on your ecosystem and project configuration capabilities. |
| MDC (Mapped Diagnostic Context) | A context map used by logging frameworks when creating log events, typically thread-bound. |
| OTLP | The protocol for transmitting telemetry from applications/Collectors to a receiver or supported backend. |
| OTel Collector | A component that can receive, process, and forward traces, metrics, and logs. |

Key identifier fields:

- `trace_id`: 16 bytes, typically represented as **32 hex characters**, sharing the same value across all spans belonging to a trace.
- `span_id`: 8 bytes, typically represented as **16 hex characters**, identifying a specific span; changes when entering a new span.
- `trace_flags`: trace context flags; in W3C Trace Context, the sampled bit indicates that the sampling decision is propagated, **not a guarantee that the trace has been stored in the backend**.
- `service.name`: a resource attribute identifying the source of telemetry; each service should be given a clear, distinct name.

Example of a valid W3C Trace Context header:

```http
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
```

Here, the leading `00` is the version; the next 32 characters are the trace ID; the following 16 characters are the **parent span ID passed from upstream**; and `01` is the trace flags. When the receiving service creates a server span, the new span typically has a **different span ID**, while continuing to use the request's trace ID. An additional `tracestate` header may also be present per the W3C standard.

Do not use an arbitrary request ID in place of `trace_id` if that ID does not conform to the trace context model. You can keep a separate `request_id` for business logic or gateway purposes, but you must clearly define the relationship between the two IDs.

## 3. Log-to-Trace Correlation Flow

```text
HTTP request (traceparent)
        │
        ▼
Instrumentation reads context → creates/sets current span
        │
        ├── Java application → SLF4J → Logback/Log4j
        │                              │
        │                              ├── MDC on log event
        │                              │   → console/file contains trace_id, span_id
        │                              │
        │                              └── OTel logging appender (if enabled)
        │                                  → OTel LogRecord → OTLP
        │
        └── OTel tracing SDK → span → OTLP
                                        │
                                  OTel Collector
                                        │
                              Observability backend
```

Two common logging pipelines:

**Pipeline A – text logs with IDs:** the framework still writes to stdout/file; the pattern layout prints `trace_id` and `span_id`. A log shipper/Collector can read the logs, parse these fields, and correlate them with traces if the backend supports it. MDC injection by itself **does not send logs over the network**.

**Pipeline B – OTel log records:** a logging appender/bridge converts log events into OTel LogRecords with standard fields such as `TraceId`, `SpanId`, `SeverityText`, `Body`, and `Resource`; the SDK/exporter sends them via OTLP. Field names displayed when searching in the backend may differ from the MDC key name `trace_id`.

You can combine both pipelines, but you must configure them so you **do not ingest duplicate log events** (for example, sending directly over OTLP while also scraping the exact same stdout line).

## 4. Easy Integration to Start: Java Agent + SLF4J/Logback

For a Java application already using SLF4J and Logback (such as Spring Boot), the Java agent is usually a good starting point because it automatically instruments many supported HTTP clients/servers and logging frameworks. You do not need to replace every `logger.info(...)` call with the OpenTelemetry Logger API. In practice, the OTel Logs API is primarily intended for bridges/appenders; application code can continue using its familiar logging API.

### Step 1: Run the application with the agent

Download the agent from the official release:

```bash
curl -L -o opentelemetry-javaagent.jar \
  https://github.com/open-telemetry/opentelemetry-java-instrumentation/releases/latest/download/opentelemetry-javaagent.jar
```

Example running on Bash when you **already have** `app.jar` and an OTLP receiver listening on `localhost:4318`:

```bash
OTEL_SERVICE_NAME=orders-service \
OTEL_TRACES_EXPORTER=otlp \
OTEL_LOGS_EXPORTER=otlp \
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318 \
OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf \
java -javaagent:./opentelemetry-javaagent.jar -jar app.jar
```

`OTEL_SERVICE_NAME` identifies the service; `OTEL_EXPORTER_OTLP_ENDPOINT` is the OTLP receiver address, **not the application's HTTP endpoint**. If no Collector/backend is running, the application can still log to the console, but telemetry export will fail. In modern Java agent versions, the default OTLP protocol is typically `http/protobuf`, though declaring it explicitly helps avoid confusing port 4317 (gRPC) with 4318 (HTTP).

Equivalent example in PowerShell:

```powershell
$env:OTEL_SERVICE_NAME = "orders-service"
$env:OTEL_TRACES_EXPORTER = "otlp"
$env:OTEL_LOGS_EXPORTER = "otlp"
$env:OTEL_EXPORTER_OTLP_ENDPOINT = "http://localhost:4318"
$env:OTEL_EXPORTER_OTLP_PROTOCOL = "http/protobuf"
java "-javaagent:.\opentelemetry-javaagent.jar" -jar ".\app.jar"
```

You do not need to enable `OTEL_LOGS_EXPORTER=otlp` just to print IDs in console lines. If your pipeline only scrapes stdout/files, you can set `OTEL_LOGS_EXPORTER=none` to avoid exporting duplicates via the log bridge, depending on your system's telemetry policy.

### Step 2: Print IDs in text logs

With Logback, configure the pattern on the appender that actually writes to the console/file. For example, `src/main/resources/logback-spring.xml` in Spring Boot:

```xml
<configuration>
    <appender name="STDOUT" class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%d{HH:mm:ss.SSS} %-5level [%thread] %logger{36} trace_id=%X{trace_id} span_id=%X{span_id} trace_flags=%X{trace_flags} - %msg%n</pattern>
        </encoder>
    </appender>
    <root level="INFO">
        <appender-ref ref="STDOUT"/>
    </root>
</configuration>
```

`%X{trace_id}`, `%X{span_id}`, and `%X{trace_flags}` read values from the **log event's** MDC. The agent includes instrumentation that injects the current span's context into the MDC copy when a log event is created. If the application already has a custom Logback configuration, edit the **existing pattern** rather than accidentally creating a second console appender and duplicating logs.

For Spring Boot using the default pattern, a more concise option is:

```properties
logging.pattern.level=trace_id=%mdc{trace_id} span_id=%mdc{span_id} trace_flags=%mdc{trace_flags} %5p
```

Choose **one** approach that matches your active logging configuration; `logging.pattern.level` will not necessarily override a custom `logback-spring.xml` that defines its own encoder/pattern.

With Log4j 2, the idea is similar, using `%X{trace_id}` and `%X{span_id}` in `PatternLayout`. Make sure to choose instrumentation compatible with your exact framework, version, and appender initialization.

### Step 3: Keep using the normal logger in business code

The following example is a controller for **an existing Spring Boot project** with `spring-boot-starter-web` and SLF4J; it is a sample application class, not a standalone Java program that can be run with a single `javac` command:

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class OrderController {
    private static final Logger LOG =
            LoggerFactory.getLogger(OrderController.class);

    @GetMapping("/orders/{id}")
    public ResponseEntity<String> getOrder(@PathVariable long id) {
        LOG.info("Đang đọc đơn hàng id={}", id);
        return ResponseEntity.ok("order-" + id);
    }
}
```

Start the service with the agent and call:

```bash
curl -H 'traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01' \
  http://localhost:8080/orders/42
```

The response body from the controller is `order-42`. If the agent instruments the HTTP server and MDC logging properly, the log line may look like this (the IDs/span and timestamp are **illustrative**, not fixed output):

```text
10:15:32.421 INFO  [http-nio-8080-exec-1] OrderController trace_id=4bf92f3577b34da6a3ce929d0e0e4736 span_id=8b2d4ce1028fe355 trace_flags=01 - Đang đọc đơn hàng id=42
```

The trace ID matches the incoming header; the span ID in the log is the ID of the current server-side span, which does not necessarily match the parent span ID from the header. During health checks, application startup, or logging outside a valid span, the ID fields may be empty; this is **not automatically an MDC error**.

## 5. Creating Manual Spans When Business Logic Needs More Detail

The agent creates spans for many framework operations, but it cannot automatically understand business steps such as `invoice.validate`. When that granularity is needed, code can use the OTel API. The example below is **a method integrated into an existing class** (with SLF4J and a `io.opentelemetry:opentelemetry-api` dependency matching the project version); the code does not configure an SDK/exporter itself:

```java
import io.opentelemetry.api.GlobalOpenTelemetry;
import io.opentelemetry.api.trace.Span;
import io.opentelemetry.api.trace.StatusCode;
import io.opentelemetry.api.trace.Tracer;
import io.opentelemetry.context.Scope;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public final class InvoiceService {
    private static final Logger LOG =
            LoggerFactory.getLogger(InvoiceService.class);
    private static final Tracer TRACER =
            GlobalOpenTelemetry.getTracer("invoice-service");

    public void validate(long invoiceId) {
        Span span = TRACER.spanBuilder("invoice.validate").startSpan();
        try (Scope scope = span.makeCurrent()) {
            LOG.info("Kiểm tra hóa đơn id={}", invoiceId);
            if (invoiceId <= 0) {
                throw new IllegalArgumentException("invoiceId phải dương");
            }
        } catch (RuntimeException ex) {
            span.recordException(ex);
            span.setStatus(StatusCode.ERROR);
            LOG.error("Không thể kiểm tra hóa đơn id={}", invoiceId, ex);
            throw ex;
        } finally {
            span.end();
        }
    }
}
```

Inside `try (Scope scope = span.makeCurrent())`, `Span.current()` points to the newly created span; when the scope closes, the previous context is restored. `span.end()` completes the span whether the method succeeds or throws an exception. If no actual SDK/provider is configured, the API may run in no-op mode and export no traces; simply adding the API dependency **does not turn a system into an observability pipeline**.

To inspect without relying on a logging pattern:

```java
Span span = Span.current();
if (span.getSpanContext().isValid()) {
    String traceId = span.getSpanContext().getTraceId();
    String spanId = span.getSpanContext().getSpanId();
    // These two IDs can be used for controlled diagnostics.
}
```

The snippet above requires importing `io.opentelemetry.api.trace.Span` and having an active valid context. Avoid manually calling `MDC.put("trace_id", ...)` in every method if the agent already instruments logging: this easily causes conflicting values, missing MDC cleanup, and maintenance overhead. Only add MDC entries manually when explicitly required, and always ensure `remove`/restoration in a `finally` block.

## 6. Preserving Trace Context Across Threads and Services

**Across services:** on an instrumented HTTP client, context is injected into outbound requests; the downstream HTTP server extracts the context and creates a child span. As a result, both services share the same trace ID. For messaging/Kafka or custom protocols, you must use the corresponding instrumentation/propagator; do not assume HTTP headers are carried across every transport. The common default is W3C `tracecontext` together with `baggage`; if two parties use different formats, compatible propagators must be configured.

**Across threads/tasks:** the current context is typically bound to the execution scope. A `new Thread`, `ExecutorService`, `CompletableFuture`, or asynchronous callback can lose context if not instrumented or wrapped. With the OTel Context API, you can explicitly propagate context when submitting work:

```java
import io.opentelemetry.context.Context;
import java.util.concurrent.Executor;
import org.slf4j.Logger;

public void submit(Executor executor, Logger logger) {
    Context captured = Context.current();
    executor.execute(captured.wrap(
            () -> logger.info("Hoàn thành tác vụ bất đồng bộ")));
}
```

This is **an additional method in an existing class**, receiving `Executor` and `Logger` from outside. `captured.wrap(...)` sets the captured context on the worker thread executing the task and restores it when the task finishes. You can use `Context.taskWrapping(executor)` to wrap an entire executor. If the agent/framework already propagates context automatically across supported executors, avoid redundant wrapping; verify using actual trace IDs.

Note that **MDC and OTel Context are not identical**. MDC may hold application-specific keys such as `user_key` or `request_id`; propagating OTel Context does not automatically copy arbitrary MDC keys. Likewise, copying MDC across threads does not guarantee that the active OTel span remains accurate.

## 7. Choosing an Integration Strategy and Setting Up the Pipeline

| Need | Approach | Key verification |
| --- | --- | --- |
| Trace IDs in stdout/file | Agent or MDC instrumentation + Logback/Log4j 2 pattern | Log events during a request have the correct `trace_id` and `span_id`. |
| Export structured logs via OTLP | OTel logging appender/bridge + SDK/exporter + Collector | LogRecords reaching the backend contain TraceId, SpanId, and service.name when a span is active. |
| Collect stdout only via Collector | Pattern/JSON logs with IDs + collector/filelog receiver or log shipper | Backend parses the IDs and can query them together with traces. |
| Create business spans | OTel API `Tracer`/`Span` within the current context | Traces show the additional business work with a sensible parent–child hierarchy. |
| Asynchronous execution | Executor instrumentation or `Context.wrap(...)` | Logs inside the task preserve the original request's trace ID. |

**The Java agent and Spring Boot starter** can address similar needs, but you should not enable both instrumentation suites simultaneously thinking telemetry will be “more complete.” When manually configuring an OTel Logback/Log4j appender alongside the agent, check export counts to avoid duplicates.

On the backend, at a minimum, you must be able to correlate these attributes:
- Trace: `trace_id`, `span_id`/parent, service name, and duration.
- Log: message/`Body`, level/`SeverityText`, timestamp, service/resource, and TraceId/SpanId when present.
- Resource: distinguishes services and deployment environments, e.g. `service.name=orders-service`.

The query system should support searching logs by trace ID and pivoting from a log to its trace. Displaying a “View trace” button depends on the backend and how data is parsed/indexed—it is not a feature guaranteed merely by adding the agent.

## 8. Verifying with Concrete Scenarios

1. **One request, multiple logs:** send a request with a valid `traceparent` to an instrumented endpoint. Logs within the same trace must share the same trace ID; the span ID may change when executing inside different spans.
2. **Across two services:** A calls B via an instrumented HTTP client/server; logs in A and B should share the same trace ID, while the client and server spans are distinct spans.
3. **Across an async task:** log before and inside the executor; inspect the trace ID values. If lost, check context propagation, scope, and capture timing.
4. **Logs outside a request:** startup/background logs without an active span may lack IDs; do not fabricate dummy `000...` strings or reuse the previous request's trace ID.
5. **At the Collector/backend:** verify that traces arrive, logs arrive, both signals carry the same service identity, and join/correlation is supported. Avoid declaring success solely because the console prints IDs.
6. **Sampling:** if a log has a trace ID but the backend shows no trace, check sampling, export, and retention settings; a log can still carry the context of a span that was not recorded.
7. **Deduplication:** compare the number of log events emitted by the application with the number of ingested log records. If doubled, check for simultaneous OTLP appender and stdout collector ingestion.

An example of a desired error log might be:

```text
2026-11-10T10:00:00Z ERROR service=orders-service trace_id=4bf92f3577b34da6a3ce929d0e0e4736 span_id=8b2d4ce1028fe355 order=42 - Payment gateway timeout
```

This is only a **formatting sample**, not an actual log line or Java execution output. Operators take the trace ID from the log to find the entire request path, then inspect which span had the corresponding latency or error.

## 9. Common Issues and Troubleshooting

| Symptom | Common cause | What to check |
| --- | --- | --- |
| `trace_id` is always empty | No current span; agent not loaded; logging instrumentation not applied to the framework | Check `-javaagent`, version compatibility, whether the request creates a span, and whether the MDC layout is applied. |
| Traces appear in backend but console prints no IDs | MDC keys missing from pattern, or appender uses a different layout | Check the active Logback/Log4j config and the `trace_id`/`span_id` key names. |
| Service A and B have different trace IDs | Context not injected/extracted, wrong propagator, or downstream call uses an uninstrumented client | Inspect `traceparent`/carrier on the wire and inbound/outbound instrumentation. |
| Logs in async task lose IDs | Context broken across thread switch | Check executor instrumentation and `Context.current().wrap(...)`; avoid capturing too late. |
| Log has IDs but trace cannot be opened | Traces not exported, sampled out, mismatched TTL, or backend lacks correlation support | Check sampling, exporter, Collector pipeline, `service.name`, and field mapping. |
| Duplicate logs | Multiple appenders or both stdout and OTLP collecting the same event | Choose one primary pipeline or filter out the duplicate route in the Collector. |
| Old request's context appears in a new request | Scope/MDC leaked across thread pool without restoration | Always close `Scope`, clean up manual MDC in `finally`; never store span IDs in static/global fields. |

Operational principles to uphold:
- **Never log secrets, tokens, cookies, passwords, or entire baggage**. Baggage can cross trust boundaries and easily leak data if dumped directly.
- Do not turn `trace_id` into a user identifier or security proof; it is for correlation, not identity verification.
- Do not attempt to print fake IDs when `SpanContext.isValid()` is `false`.
- Apply sampling, log levels, filtering, and retention appropriate to your traffic; OTel does not eliminate the need to manage log/trace costs.
- Ensure consistent time policies, service identity, and field mappings at export/indexing time; otherwise both signals may exist but remain hard to correlate.

## 10. Knowledge Self-Check

1. Why does `trace_id` usually stay the same when a request travels from service A to B, while `span_id` changes?
2. When is MDC + stdout sufficient, and when do you need an OTel log appender + OTLP?
3. What happens to log correlation when a task runs on an executor without context propagation?
4. Why might a log with a valid trace ID still fail to find a corresponding trace in the backend?
5. How can you distinguish a missing-instrumentation bug from a log emitted outside a valid span?

A system achieves **OpenTelemetry compatibility** when trace context is propagated accurately, log events carry appropriate IDs while inside a span, logs/traces are exported through the chosen pipeline, and operators can actually run correlated queries in the backend.

## References

- [OpenTelemetry – Java instrumentation and context propagation](https://opentelemetry.io/docs/languages/java/instrumentation/)
- [OpenTelemetry – Java agent: Getting started](https://opentelemetry.io/docs/zero-code/java/agent/getting-started/)
- [OTel Java agent – MDC log correlation](https://github.com/open-telemetry/opentelemetry-java-instrumentation/blob/main/docs/logger-mdc-instrumentation.md)
- [OpenTelemetry – Logs Data Model](https://opentelemetry.io/docs/specs/otel/logs/data-model/)
- [OpenTelemetry – Java API and Context](https://opentelemetry.io/docs/languages/java/api/)
- [OpenTelemetry – Exporter and propagator configuration](https://opentelemetry.io/docs/languages/sdk-configuration/general/)