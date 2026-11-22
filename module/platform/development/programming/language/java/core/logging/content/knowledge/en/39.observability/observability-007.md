# Log Enrichment in Java Core Logging and Observability

## 1. What Is Log Enrichment?

**Log enrichment** is the process of adding **semantic and structured metadata** to a log event so that a human reader or observability system can determine **what event occurred**, **where it happened**, **which request/trace it belongs to**, **which entity it affected**, and **what the outcome was** — without having to guess from a free-form message string.

Example before enrichment:

~~~text
INFO Order saved
ERROR Payment timeout
~~~

After enrichment, it is still the same type of message, but it can be investigated and aggregated:

~~~json
{
  "timestamp": "2026-11-10T03:00:00Z",
  "severity": "ERROR",
  "service.name": "checkout",
  "service.version": "1.0.0",
  "deployment.environment.name": "production",
  "event": "payment_failed",
  "errorCode": "PAY-TIMEOUT",
  "requestId": "req-42",
  "traceId": "4f0e2c13b69a497389d74e71a52b4e62",
  "spanId": "00f067aa0ba902b7",
  "orderRef": "ord-demo-7",
  "outcome": "failed"
}
~~~

This is **illustrative JSON**, not a native OpenTelemetry LogRecord payload or default JUL output. The field naming in the example helps explain the meaning; when implementing OpenTelemetry, you must map properly into `Resource`, `Attributes`, and the dedicated `TraceId`/`SpanId` fields of the data model.

Enrichment is different from merely **writing longer messages**. Messages can be for humans; dedicated fields allow filtering, grouping, correlation, and schema testing. It is also different from **capturing the entire context**: redundant, incorrect, or sensitive metadata increases cost, risk, and noise. The value of enrichment comes from **the right fields, from the right source, with the right lifecycle**.

### Operational Goals

- Trace from `requestId` to all logs of the same request across multiple layers of a service.
- Trace from `traceId`/`spanId` to traces, latency, and related processing spans.
- Distinguish logs across versions and environments when multiple deployments run concurrently.
- Group errors by `event`, `errorCode`, `outcome`, and `dependency` without parsing messages.
- Identify which worker/job/message or which tenant a log came from **after the context has been authenticated/validated**.
- Increase search/alerting value without turning every field into a high-cardinality metric label.

One request may emit multiple logs, one trace may span multiple services and spans, and the same event may be exported to multiple sinks. Enrichment helps **connect them within the right scope**, but does not by itself solve duplicate logs, distributed tracing, audit trails, or business idempotency.

## 2. Three Layers of Information to Distinguish

A clear schema classifies metadata by **stability level and source**.

| Layer | Sample Fields | Lifecycle | Trusted Source |
| --- | --- | --- | --- |
| **Resource / source** | `service.name`, `service.version`, `deployment.environment.name`, `service.instance.id` | Relatively stable within an instance/deployment | Deploy config, SDK, orchestrator, or verified collector |
| **Processing context** | `requestId`, `traceId`, `spanId`, `correlationId`, `tenantRef`, `messageId` | Request, span, message, or job | Middleware, tracing SDK, validated envelope |
| **Event attributes** | `event`, `errorCode`, `outcome`, `attempt`, `durationMs`, `orderRef` | Specific to each log event | Business logic at the time the event is emitted |

For example, the same `checkout` service may process thousands of requests, so `service.name` usually does not need to be recomputed in every method. `requestId` changes per request; `event=order_completed` and `durationMs=34` only make sense for the order completion record.

### In the OpenTelemetry Logs Model

OpenTelemetry distinguishes:

- **`Timestamp`:** the time the event occurred, distinct from `ObservedTimestamp`, which is when the collection system observed it.
- **`SeverityText`/`SeverityNumber`:** log level; not an error code.
- **`Body`:** event content, which may be a string or structured value depending on the exporter.
- **`Resource`:** metadata describing the telemetry source, such as service and environment.
- **`Attributes`:** metadata specific to the log record; suitable for `orderRef`, `errorCode`, `outcome`.
- **`TraceId` and `SpanId`:** dedicated fields for trace correlation; not just two keys in text.
- **`InstrumentationScope`:** information about the instrumentation component emitting the signal.
- **`EventName`:** structured event type name when the signal is represented using the event model.

This is the target model; **do not blindly dump every field into a single Map and call it OpenTelemetry**. If you only output JSON from Logback and have a collector parse it, you need to know which adapter maps which fields into each part of an OTel LogRecord. If using an OpenTelemetry SDK/bridge, check whether the actual version and exporter map the structure as expected.

**Do not assume** the source `Timestamp` and the collector `ObservedTimestamp` are identical. Differences may indicate buffering/queuing, clock drift, or transport delay; clock synchronization and clear conventions are required before measuring latency.

## 3. Choosing a Consistent Schema

A useful schema does not need hundreds of fields. Start with a **core set of values** and declare an explicit contract:

| Field | Recommended Type | Meaning | Notes |
| --- | --- | --- | --- |
| `event` / `event.name` | bounded string | Event type: `order_received`, `order_processed` | Do not embed requestId into the event name |
| `service.name` | bounded string | Logical service name | Same across replicas of the same service |
| `service.version` | string | Binary/deploy version | Do not confuse with event schema version |
| `deployment.environment.name` | bounded string | `development`/`staging`/`production`... | Belongs to Resource in OTel |
| `service.instance.id` | string | Instance emitting the event | Can have high cardinality; do not use arbitrarily as a metric label |
| `requestId` | validated string | Request correlation | Not traceId or userId |
| `traceId`, `spanId` | W3C format when actually traced | Trace/span correlation | Do not fabricate values to fill empty fields |
| `messageId` | string per message contract | Logical message | Preserve across redelivery if it is the same message |
| `tenantRef` | appropriately validated/masked string | Partitioning by tenant | Do not treat this value as authorization |
| `errorCode` | bounded enum/string | Stable error type | Do not use raw Throwable message |
| `durationMs` | non-negative number | Processing duration | Store as a number, do not concatenate `"34ms"` if the schema requires a number |
| `attempt` | integer | Processing attempt | Keep separate from message ID and error code |
| `outcome` | bounded string | `success`, `failure`, `cancelled`... | Distinct from log level |
| `orderRef` | safe string | Business reference for debugging | Retain only when policy allows |

If an official semantic convention already fits the signal, **prefer that convention's name and type** over custom names. Names like `requestId` and `orderRef` in the example are **application-custom** fields; do not claim them as standard OpenTelemetry attributes. Do not use a standard name while changing its semantics: consistency across services matters more than making individual log lines look pretty.

### Schema Version and Source of Truth

When you want to rename `durationMs` to `duration_ms` or change a numeric string to a number, that can be a **breaking change for collectors/queries/dashboards**. You should define:

1. Field name, data type, source, constraints, and value when missing.
2. Which fields are required on which events; do not force `errorCode` to be present on a success event.
3. Schema version or migration plan for the log pipeline when making incompatible changes.
4. Trust level: whether a field is verified by the application, determined by the collector, or supplied by the client.
5. Conflict resolution when two layers populate the same field: do not silently overwrite a verified value with an unverified header.

A naive normalization like turning every missing value into `"unknown"` can conflate different kinds of events. You must distinguish **missing because not applicable**, **missing due to propagation failure**, and **unknown because unverifiable** in quality monitoring.

## 4. Which Layer Should Enrich?

~~~text
Business code
   |
   +-- event attributes: event, outcome, errorCode, orderRef
   |
   v
Request/message middleware
   |
   +-- scoped context: requestId, tenantRef, correlationId
   |
   v
Logging API/backend
   |
   +-- MDC / key-value pairs + encoder/layout
   |
   v
SDK/agent/collector
   |
   +-- resource: service/version/environment/pod metadata
   +-- validate/transform/redact according to schema
   |
   v
Log storage / index / dashboard
~~~

**There is no single layer suitable for every field.** Some guidelines:

- **At the point where the event occurs:** record the event name, error code, outcome, duration, and safe business IDs. A collector usually cannot accurately infer a failed payment from free-form text.
- **At request middleware:** generate/validate `requestId`, extract principal/tenant from authentication, set up the scope, and clean up on completion. Do not blindly trust client-supplied `X-Request-Id` or `X-Tenant-Id`.
- **At tracing instrumentation:** read the actual trace/span context from the active SDK/agent. Propagate trace context across async and network boundaries via supported libraries.
- **At deployment config / OpenTelemetry resource:** identify service name, version, environment, and instance. If missing in the app, the collector can supplement it from trusted sources like Kubernetes metadata.
- **At the collector:** can add/modify/delete fields, normalize schemas, and perform additional redaction, but **cannot fix missing origin information**. A log that already leaked a secret to stdout/file before reaching the collector is still a security incident at the source.
- **At the backend:** indexes/searches/manages retention and access control; this is not the place to invent the identity or business truth of an event.

### Value Conflicts

If the application writes `service.name=checkout` but the collector sets `service.name=payments`, events may be misattributed to the wrong dashboard/runbook. If a client header says `tenantId=B` while the authenticated principal only has access to tenant A, do not let the header decide log partitioning. Design a **clear source of truth and precedence**, fail closed for fields used in data isolation, and alert when conflicts are detected.

**Enrichment must be idempotent**: if a collector retries or passes through the same processor twice, it must not create duplicate field arrays, concatenate strings repeatedly, or lose valid values. Use intentional insert/update/upsert policies and test with data that already has fields populated.

## 5. Standalone Java 17 Example: Attaching Event Metadata and Propagating Across a Thread Pool

The following example uses **Java 17 only**, with no dependency on OpenTelemetry, SLF4J, or Logback. It illustrates three ideas:

- Fixed resource metadata in the example (`service`, `environment`, `version`).
- Request context (`requestId`, `traceId`, `spanId`) managed by scope.
- Per-event data (`event`, `orderRef`, `outcome`) captured per log record and passed through a custom `java.util.logging.Handler`.

**Important:** `java.util.logging.LogRecord` does not have a standard MDC/attribute map API directly corresponding to OpenTelemetry. To stay independent of external libraries, the demo places an immutable `EventData` into `LogRecord.parameters`, and the lesson-defined handler reads it. This is a **demo-specific contract**, not a convention automatically understood by all JUL Formatters or exporters.

Create the file **`LogEnrichmentDemo.java`**:

~~~java
import java.util.Objects;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.function.Supplier;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class LogEnrichmentDemo {
    // Context for the current execution; exists only on the current thread.
    record Context(String requestId, String traceId, String spanId) {}

    // Data snapshot per event, independent of the writer thread.
    record EventData(
            String service, String environment, String version,
            String requestId, String traceId, String spanId,
            String event, String orderRef, String outcome) {}

    private static final Logger LOG =
            Logger.getLogger("demo.enrichment");
    private static final ThreadLocal<Context> CURRENT =
            new ThreadLocal<>();

    // Proper scoping even with nested calls or thrown exceptions.
    private static <T> T within(Context next, Supplier<T> work) {
        Context before = CURRENT.get();
        try {
            if (next == null) {
                CURRENT.remove();
            } else {
                CURRENT.set(next);
            }
            return work.get();
        } finally {
            if (before == null) {
                CURRENT.remove();
            } else {
                CURRENT.set(before);
            }
        }
    }

    // Capture context at submission time and restore it on the worker.
    private static Runnable capture(Runnable task) {
        Context snapshot = CURRENT.get();
        return () -> within(snapshot, () -> {
            task.run();
            return null;
        });
    }

    private static void emit(
            String event, String orderRef, String outcome) {

        Context ctx = Objects.requireNonNull(
                CURRENT.get(), "context missing");

        EventData data = new EventData(
                "checkout", "development", "1.0.0",
                ctx.requestId(), ctx.traceId(), ctx.spanId(),
                event, orderRef, outcome);

        LogRecord record = new LogRecord(Level.INFO, event);
        record.setLoggerName(LOG.getName());

        // Demo-specific JUL contract: EventData inside parameters.
        record.setParameters(new Object[] { data });
        LOG.log(record);
    }

    private static final class StructuredHandler extends Handler {
        @Override
        public void publish(LogRecord record) {
            if (!isLoggable(record)) {
                return;
            }

            Object[] params = record.getParameters();
            if (params == null || params.length != 1
                    || !(params[0] instanceof EventData e)) {
                return;
            }

            // Demo data is controlled; production requires a structured
            // encoder, escaping/control-character handling, and redaction.
            System.out.println(
                    "service=" + e.service()
                    + " env=" + e.environment()
                    + " version=" + e.version()
                    + " event=" + e.event()
                    + " requestId=" + e.requestId()
                    + " traceId=" + e.traceId()
                    + " spanId=" + e.spanId()
                    + " orderRef=" + e.orderRef()
                    + " outcome=" + e.outcome());
        }

        @Override
        public void flush() {
            // No I/O buffer.
        }

        @Override
        public void close() {
            // No external resources to close.
        }
    }

    public static void main(String[] args) throws Exception {
        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.ALL);

        StructuredHandler handler = new StructuredHandler();
        handler.setLevel(Level.ALL);
        LOG.addHandler(handler);

        ExecutorService pool = Executors.newSingleThreadExecutor();
        try {
            Future<?> first = within(
                    new Context(
                            "req-A",
                            "11111111111111111111111111111111",
                            "aaaaaaaaaaaaaaaa"),
                    () -> {
                        emit("order_received", "ord-7", "accepted");
                        return pool.submit(capture(() ->
                                emit("order_processed", "ord-7",
                                        "success")));
                    });
            first.get();

            // Same worker is reused, but context must be B.
            Future<?> second = within(
                    new Context(
                            "req-B",
                            "22222222222222222222222222222222",
                            "bbbbbbbbbbbbbbbb"),
                    () -> pool.submit(capture(() ->
                            emit("order_processed", "ord-8",
                                    "success"))));
            second.get();
        } finally {
            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                pool.shutdownNow();
            }
            LOG.removeHandler(handler);
            handler.close();
        }
    }
}
~~~

Compile and run with JDK 17 or later:

~~~bash
javac -encoding UTF-8 LogEnrichmentDemo.java
java LogEnrichmentDemo
~~~

**Deterministic stdout**, because the program calls `get()` on each `Future` before processing the next request and the custom handler does not add timestamps:

~~~text
service=checkout env=development version=1.0.0 event=order_received requestId=req-A traceId=11111111111111111111111111111111 spanId=aaaaaaaaaaaaaaaa orderRef=ord-7 outcome=accepted
service=checkout env=development version=1.0.0 event=order_processed requestId=req-A traceId=11111111111111111111111111111111 spanId=aaaaaaaaaaaaaaaa orderRef=ord-7 outcome=success
service=checkout env=development version=1.0.0 event=order_processed requestId=req-B traceId=22222222222222222222222222222222 spanId=bbbbbbbbbbbbbbbb orderRef=ord-8 outcome=success
~~~

Key takeaways from the example:

1. `EventData` is an immutable Java `record`; fields are **packaged into the event at log emission time**. The handler reads the event itself, not the current `ThreadLocal` of the logging thread.
2. `within(...)` saves `Context before`, sets the new context, and restores it in `finally`. It supports nested scopes without losing the caller's scope. Missing scope should be explicit; the demo chooses to throw an exception rather than silently logging a fake `requestId`.
3. `capture(...)` reads the snapshot on the **submitting thread**. The thread pool worker receives the snapshot and cleans/restores it after execution. Request B does not get tagged with A's `requestId` even on the same worker.
4. `traceId`/`spanId` in the example are **dummy values provided by the lesson**, not generated by OpenTelemetry and not proof of a real span. In production, read them from the active tracing SDK context and never assign client-supplied strings.
5. `setParameters(...)` is how the demo transports metadata to `StructuredHandler`. Standard JUL formatters may treat `parameters` as message format arguments and **do not automatically convert `EventData` into OTel attributes**. A proper bridge/formatter/handler is needed to send to real systems.
6. The demo prints known `key=value` pairs with **no JSON escaping/sanitization for arbitrary input**; do not use this in production for client-controlled fields. In production, use a structured encoder, schema validation, sanitization, and redaction.
7. `get()` waits for each task to complete before the next step, so stdout order is deterministic. In a multi-threaded system, do not assert ordering across independent requests.
8. `pool.shutdown()` is only for the demo's lifecycle. A server normally owns a shared executor and does not shut it down per request; place scoping/cleanup at application boundaries.

### Why Doesn't the Example Use SLF4J?

The goal is for learners to run and verify enrichment logic using only JDK 17. SLF4J/Logback, Log4j 2, and OpenTelemetry are better for real-world deployments but require external dependencies and backends. Do not confuse a hand-rolled `ThreadLocal` with SLF4J's MDC or official tracing SDK propagation.

## 6. SLF4J 2.x: How Do Event Key–Value Pairs and MDC Differ?

SLF4J has two common mechanisms:

- **MDC (`Mapped Diagnostic Context`):** a key–value map bound to the current thread, suitable for `requestId`/`tenantRef`/`correlationId` shared across multiple log calls within the same scope.
- **Fluent logging API (SLF4J 2.x):** `atInfo()`/`atError()`, `addKeyValue(...)`, `setCause(...)`, then `log(...)` to attach attributes **specific to a single event**.

Example **snippet** for an application with SLF4J 2.x and a compatible backend; `LOG`, `orderRef`, `durationMs`, and `outcome` are application-defined:

~~~java
LOG.atInfo()
   .addKeyValue("event", "order_processed")
   .addKeyValue("orderRef", orderRef)
   .addKeyValue("durationMs", durationMs)
   .addKeyValue("outcome", outcome)
   .log("Order processed");
~~~

You must **end with `log()`**; calling `addKeyValue` and forgetting `log()` emits no event. The SLF4J 2.x Fluent API does not exist in SLF4J 1.7. Having key–value pairs in the API **does not guarantee** the active formatter outputs JSON or prints those pairs: you must configure a supporting backend/encoder and integration-test actual log output.

Example of attaching request scope:

~~~java
// Snippet in a class/middleware with org.slf4j.MDC.
import java.util.Map;
import org.slf4j.MDC;

Map<String, String> before = MDC.getCopyOfContextMap();
try {
    MDC.put("requestId", verifiedRequestId);
    MDC.put("correlationId", correlationId);
    businessOperation();
} finally {
    if (before == null) {
        MDC.clear();
    } else {
        MDC.setContextMap(before);
    }
}
~~~

`verifiedRequestId` and `correlationId` must be validated and must not contain secrets. `businessOperation()` represents actual application code. `MDC.getCopyOfContextMap()` preserves the caller's context in nested calls; `finally` prevents request B from inheriting request A's metadata on a reused server thread pool.

**Do not put `errorCode` into the request-wide MDC and forget to remove it**, because an error handled early in the request could cause subsequent success logs to still carry that error code. `errorCode`, `durationMs`, and `outcome` are usually better suited as **event attributes** via the fluent API.

### Logback Pattern Displaying MDC

Minimal **`logback.xml`** configuration example (requires Logback Classic on the classpath):

~~~xml
<configuration>
    <appender name="CONSOLE"
              class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%d{ISO8601} %-5level service=checkout req=%X{requestId} corr=%X{correlationId} %logger - %msg%n</pattern>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
    </root>
</configuration>
~~~

`%X{requestId}` and `%X{correlationId}` **only display** fields currently in the MDC; they do not create fields on their own. The `service=checkout` part is hardcoded in the example pattern; in production, put service/environment in Resource/deployment configuration metadata for consistency across appenders. Text patterns do not automatically convert fluent key–value pairs into structured JSON. If JSON is needed, choose an encoder that supports structured fields and test the actual output. Do not assume all backends or Logback versions share the same JSON encoder.

### Log4j 2 ThreadContext

In Log4j 2, the equivalent of MDC is `ThreadContext`. Example snippet using the Log4j 2 API (not a standalone JDK program):

~~~java
import org.apache.logging.log4j.CloseableThreadContext;
import org.apache.logging.log4j.LogManager;
import org.apache.logging.log4j.Logger;

Logger log = LogManager.getLogger("checkout");

try (CloseableThreadContext.Instance ignored =
             CloseableThreadContext.put("requestId", verifiedRequestId)
                                   .put("correlationId", correlationId)) {
    log.info("event=order_received");
}
~~~

Validate inputs and ensure the scope is cleaned up. `ThreadContext` has both a context map and a stack; in thread pools, do not assume parent thread data is automatically propagated. You can use `ThreadContext.getImmutableContext()` to snapshot and `CloseableThreadContext.putAll(snapshot)` upon entering a worker, following the backend's contract. For async/reactive frameworks, use the appropriate propagation mechanism instead of hardcoding a `ThreadLocal` where request context no longer exists.

## 7. Enriching `traceId`/`spanId` Properly

**Log–trace correlation** is a major use case for enrichment. A request may pass through API, checkout, payment, and DB; if logs contain `TraceId`/`SpanId` matching the real span, you can jump from an error log to the trace, and from the trace to logs of other services.

~~~text
TraceId = 4f0e...4e62
    |
    +-- Span API request         -> log event=request_received
    |
    +-- Span checkout operation  -> log event=order_processed
    |
    +-- Span payment dependency  -> log event=payment_timeout
~~~

**Do not generate a new `traceId` on every `logger.info(...)` call**: there is no real trace and correlation breaks. Tracing APIs/SDKs provide a `SpanContext` holding the trace ID/span ID of the active span. Use instrumentation/bridges that read the context into logs; avoid copying a raw `traceparent` from an unvalidated request and treating it as proof of a service relationship.

Per W3C Trace Context, `traceparent` encodes version, trace-id, parent-id, and flags. Real values must be validated by a parser/propagator. If `SpanId` is present, `TraceId` should also be present in the `LogRecord`; do not attach a span ID that does not belong to the corresponding trace. For distributed messaging, context propagation via headers/envelopes must be designed explicitly and cannot rely solely on thread-local MDC.

**Trace sampling does not mean dropping all logs.** `traceId` may appear in some logs even when the span is not exported; whether you can open the actual trace depends on sampling/exporter settings. Do not promise that every log with a `traceId` will open a trace in the backend.

### OpenTelemetry Java and Logging Frameworks

OpenTelemetry provides a **bridge/appender** path from existing logging frameworks like Logback/Log4j 2 to OpenTelemetry Logs, and a collector/OTLP path for collection infrastructure. OpenTelemetry's Logs API is designed differently from typical user-facing logging APIs; when an application already uses SLF4J/Logback, you usually do not need to replace every `LOG.info(...)` with manual Logs SDK API calls.

Deployment can follow:

~~~text
SLF4J / Logback event
      |
      v
OTel appender/bridge (if configured)
      |
      v
OTel LogRecord + TraceId/SpanId + Resource + Attributes
      |
      v
SDK exporter (OTLP)
      |
      v
Collector -> log backend
~~~

Or:

~~~text
Logback structured stdout
      |
      v
Agent/collector parses JSON
      |
      v
Maps fields/schema into OTel or backend
~~~

These are two different deployment paths with different context-capture capabilities and operational requirements. **Do not enable both ingest paths simultaneously for the same event into the same index** without a strategy for deduplication, provenance, and cost.

## 8. Resource Enrichment in OpenTelemetry

Commonly used Resource attributes:

- `service.name`: logical service name, identical across replicas of the same service.
- `service.namespace`: namespace if needed to distinguish services across teams/groups.
- `service.version`: application/artifact version.
- `service.instance.id`: identifier for an instance (not synonymous with pod name in every environment).
- `deployment.environment.name`: environment name such as `development`, `staging`, `production`.
- Infrastructure attributes such as container/Kubernetes/cloud if appropriate instrumentations or collectors and permissions are in place.

Specifically, the current standard name is `deployment.environment.name`. The older name `deployment.environment` has been marked deprecated in the semantic conventions registry. When reading older docs/libraries, check the version and migration mapping so you do not store both fields inconsistently.

**Illustrative** environment configuration example for a runtime with an OpenTelemetry SDK/Java agent supporting OTel environment variables:

~~~text
OTEL_SERVICE_NAME=checkout
OTEL_RESOURCE_ATTRIBUTES=service.version=1.0.0,deployment.environment.name=production
~~~

These variables **do not make JUL automatically output JSON/OTLP**. They only take effect when an appropriate instrumentation/SDK/agent is installed and loaded. In production, set them via manifests/deployments/secrets/config systems, avoiding mismatched values between the application and the collector.

A Resource should describe the source, not the request: do not put `requestId` or `userId` into `service.name` or Resource and keep it across requests. Doing so breaks telemetry grouping and creates meaningless entity proliferation.

## 9. Enrichment at the Collector and Overwrite Rules

A collector can enrich using a resource processor, attributes processor, or transform processor depending on distribution/version. Examples include adding `service.name` from trusted deployment metadata, renaming legacy fields, deleting sensitive fields, or normalizing values.

Common operations:

| Operation | Meaning | When to Use |
| --- | --- | --- |
| **insert** | Add only if not already present | Provide defaults without overwriting app-verified values |
| **update** | Modify only if already present | Normalize a key guaranteed to exist |
| **upsert** | Insert or update | Normalize fields with a clear priority source of truth |
| **delete** | Remove field | Strip metadata that is not permitted to be retained |
| **transform/rename** | Rename/cast according to schema | Version migration or source mapping |

A processor only takes effect when it is actually included in the collector's pipeline. If you configure a processor but omit it from `service.pipelines.logs.processors`, data passes through without being enriched. Exact names and syntax depend on the collector version and installed processor set; do not assume every transform is available in every distribution.

**Preserve source data integrity:** the collector cannot determine a request's tenant by blindly reading `X-Tenant-Id`; whereas `service.version` from deploy config can be trusted if the pipeline is tightly managed. You can record provenance or emit alerts when fields conflict.

For sensitive fields, perform redaction **directly in the application**, with the collector as an additional layer. A token written to stdout/file/queue before the collector can still be read or backed up even if stripped at the final backend.

### JSON and Data Types

A major benefit of structured logging is preserving types:

~~~json
{
  "event": "order_processed",
  "durationMs": 34,
  "attempt": 2,
  "success": true,
  "traceId": "4f0e2c13b69a497389d74e71a52b4e62"
}
~~~

`durationMs` is a number, `attempt` is a number, and `success` is a boolean. If a formatter turns everything into strings like `"34ms"`/`"true"`, query and aggregation systems may have to parse them or hit type-mapping errors. A schema should define null/missing behavior and versioning. Do not let the same field be a number today and a string tomorrow if the index/backend requires consistent types.

## 10. The Biggest Pitfall: Context Across Async, Thread Pools, and Message Brokers

`MDC` and many context management approaches are bound to the current thread. In Java, `ExecutorService`, `CompletableFuture`, reactive code, schedulers, or message consumers can execute work on a different thread.

Two failure modes:

1. **Missing context:** request A has `requestId=A`/`traceId=A` on the web thread, but the worker does not receive it. Logs in the worker cannot be traced back to the source request.
2. **Leaked/mixed context:** a worker retains request A's context after a task finishes, then processes B and stamps A's ID onto B's events. This is a critical bug when fields are used to partition logs by tenant.

To avoid this, **capture at the task submission boundary**, **restore/set at the worker boundary**, and **clean up in `finally`**. With SLF4J MDC:

~~~java
// Snippet: org.slf4j.MDC, java.util.Map.
static Runnable withMdc(Runnable task) {
    Map<String, String> captured = MDC.getCopyOfContextMap();
    return () -> {
        Map<String, String> before = MDC.getCopyOfContextMap();
        try {
            if (captured == null) {
                MDC.clear();
            } else {
                MDC.setContextMap(captured);
            }
            task.run();
        } finally {
            if (before == null) {
                MDC.clear();
            } else {
                MDC.setContextMap(before);
            }
        }
    };
}
~~~

Example usage: `executor.execute(withMdc(() -> LOG.info("event=...")))` when the caller has an active MDC. This is a snippet placed in a class where `MDC` and `executor` are already declared, not a standalone runnable file.

**Note on reset:** restoring `before` fits nested scopes. For **independent** tasks, the framework should ensure a worker starts and ends with a clean context; if `before` already contained leaked data from prior code, restoring it does not fix the leak source. Test a worker processing `A → B → no-context`.

### Async Appenders and Event Snapshots

An async logger may enqueue events and process them on a separate I/O thread. Do not read `MDC.get("requestId")` on the writer thread and attach it to the event being written: that is the writer's MDC, not necessarily the producer's context. Use the MDC snapshot/event data that the backend attached to the event per its contract. With a tracing SDK, context propagation must be handled by the supported API/instrumentation; copying a few strings into MDC does not create spans or parent–child links.

### Across Message Brokers

Producers must place correlation/trace context into **message metadata transmitted over the broker**, not just into MDC. Consumers validate/extract context, establish the scope during processing, and then clean up. `messageId` identifies the logical message; `traceId` identifies the trace; `correlationId` identifies the workflow per contract; one field does not automatically substitute for the other two. Do not trust user-supplied headers as proof of tenant authentication.

## 11. Selecting Metadata Deliberately to Avoid Degrading Log Quality

**More enrichment does not automatically mean better observability.**

### Cardinality

There is a key distinction between:

- **Log field** `requestId`: can have millions of values; useful for finding a single request in a backend with appropriate indexing and retention.
- **Metric label** `requestId`: can create millions of time series, spiking CPU/memory/cost; **do not** do this.
- **Resource attribute** `service.instance.id`: can have many instances; useful for identifying the source, though backend grouping behavior must be evaluated.
- **Event name/error code** from a bounded catalog: well suited for aggregation and metric dimensions.

Fields like `userId`, `sessionId`, `orderId`, full URLs, raw exception messages, tokens, or string timestamps should not become metric labels. If you need traffic analysis across a large number of tenants, calculations/aggregations must account for cardinality limits and privacy—do not assume every log field belongs as a metric dimension.

### Size and Cost

Adding many fields to each event increases JSON size, ingest/index/storage costs, and formatting time. At 1 million events/day, adding just 200 bytes/event adds roughly 200 MB/day (before compression/indexing/replicas). Monitor actual data, set limits on string lengths, field counts, and schemas. Do not copy entire HTTP headers, object `toString()` outputs, or large JSON payloads to "enrich" logs.

### Field Reliability and Correctness

A wrong `traceId` is worse than a missing field because it leads investigators to link logs to the wrong trace. A wrong `tenantRef` can route logs to an inappropriate location; authentication and data lineage must accompany enrichment. Do not infer user identity from raw user-agent/IP without authorization and a clear benefit.

If required metadata is missing, emit a telemetry quality alert and investigate the boundary; do not fabricate `requestId=random` in the collector and claim it is the source request ID.

## 12. Security and Privacy in Enrichment

OWASP recommends against directly logging many kinds of sensitive data: passwords, access tokens, session identifiers, encryption keys, sensitive personal data, and connection strings. Enrichment can inadvertently increase exposure because fields become easy to query and are replicated across multiple backends.

| Field/Situation | Risk | Approach |
| --- | --- | --- |
| `user.email`, `phone`, `ip.address` | Personal identification, long-term storage | Log only with valid purpose/basis; mask/pseudonymize where appropriate |
| Access tokens, cookies, JWTs | Credential exposure | **Do not log**; do not hash casually and assume it is safe |
| Client-supplied `tenantId` | Spoofing, misattributed tenant logs | Obtain from authenticated principal/envelope |
| Full URL with query string | Tokens/PII in query parameters | Log route template or allowlisted fields |
| `exception.getMessage()`, stack trace | May contain SQL, hosts, secrets, user input | Inspect/redact before sending to unauthorized sinks |
| `requestId` containing newlines | Log injection and parsing errors | Validate format/length, escape control characters |
| Long-lived stable `userRef` | Enables tracking an individual over time | Restrict scope/retention and query permissions |
| Separate file/collector sidecars | Data may appear in secondary sinks | Test all outputs, not just the primary dashboard |

**Hashing/pseudonymization does not mean absolute anonymity.** For predictable IDs that need correlation, consider keyed, versioned, and scoped HMAC rather than plain SHA-256; however, the best solution is usually **not collecting unnecessary fields**.

Apply:

1. Data minimization before emitting logs.
2. Schema allowlists and input limits.
3. RBAC/tenant isolation at the backend/query layer, not just UI filters.
4. Retention, encryption, and auditing of log access.
5. Testing with fake sensitive markers across stdout, files, collectors, tracing, and backups.
6. Policies for missing/conflicting fields that never fail-open into another tenant's sink.

Enrichment **does not change caller permissions**; knowing a `requestId`/`traceId` must not be treated as authorization to query someone else's data.

## 13. Practical Before/After Examples

### A. Debugging Payment Timeout

Before:

~~~text
ERROR request failed
~~~

After:

~~~json
{
  "event": "payment_attempt_failed",
  "errorCode": "PAY-TIMEOUT",
  "service.name": "billing",
  "dependency": "payment-gateway",
  "requestId": "req-42",
  "attempt": 2,
  "outcome": "retry_scheduled",
  "durationMs": 5030
}
~~~

An enriched log like this shows it was a transient attempt failure and will be retried. Do not use `errorCode=PAY-TIMEOUT` alone to conclude there was a **final failure**; you need `outcome` and `attempt`.

### B. Finding Bugs That Only Occur in a New Version

Before:

~~~text
WARN validation failed
~~~

After:

~~~json
{
  "event": "request_validation_failed",
  "errorCode": "REQ-VALIDATION-001",
  "service.name": "checkout",
  "service.version": "2.4.1",
  "deployment.environment.name": "production",
  "requestId": "req-51",
  "route": "/orders/{orderId}",
  "outcome": "rejected"
}
~~~

Using a **route template** instead of a URL containing `orderId` and query parameters enables grouping by endpoint while exposing less data. If you need to identify a specific request, keep `requestId` in protected logs. Service version should come from artifact/deployment configuration rather than being inferred at runtime.

### C. Correlating with Tracing

Before:

~~~text
INFO request started
INFO db query slow
ERROR gateway timeout
~~~

After, you can attach the corresponding `TraceId` and `SpanId` from the **real tracing SDK** to jump from the log to the slow span. If an event occurs outside an active span, `SpanId` may not exist; do not fabricate dummy values to "fill out the schema."

### D. Message Consumer Redelivery

Before:

~~~text
INFO processing message
INFO processing message
~~~

After:

~~~text
event=message_received messageId=msg-1001 attempt=1 consumer=billing
event=message_failed messageId=msg-1001 attempt=1 errorCode=PAY-TIMEOUT
event=message_received messageId=msg-1001 attempt=2 consumer=billing
event=message_processed messageId=msg-1001 attempt=2 outcome=success
~~~

Enrichment reveals two deliveries of the same message due to a retry. However, it does not guarantee idempotency: side effects require separate database/transport mechanisms if duplicate processing is not allowed.

## 14. Testing Enrichment: More Accurate Than Just Watching the Console

### Application-Level Tests

- **Resource:** `service.name`, `service.version`, `deployment.environment.name` match the instance; no environment mixing.
- **Request scope:** two consecutive requests on the same thread pool do not leak `requestId`, `tenantRef`, or trace context.
- **Event scope:** `errorCode` only on error events, `durationMs` is numeric and non-negative, `outcome` matches business result.
- **Async:** events inside tasks receive the context captured at submission, not the writer thread's values; callbacks/`CompletableFuture` have proper propagation.
- **Missing trace:** when there is no active span, no fake trace ID is fabricated; schema handles optionality properly.
- **Malicious input:** headers with control characters/newlines, oversized values, tenant spoofing, and user-supplied IDs do not break partitioning or cause log injection.
- **Sensitive data:** fake markers like `TEST_PRIVATE_VALUE` do not appear in unauthorized outputs.
- **Log levels:** when DEBUG is disabled, expensive enrichment is not computed unnecessarily; critical errors are not silently dropped by the pipeline.

### Backend/Collector Tests

- **Data types:** `durationMs` remains a number and is not converted to a string in the collector/index.
- **Structured fields:** SLF4J `addKeyValue` actually reaches the sink, not just staying inside the API object.
- **OTel mapping:** `service.name` is in Resource, `traceId`/`spanId` are in trace fields, event attributes are accurate, and timestamp vs. observed time are not confused.
- **Processor order:** are collector transformations enabled in `service.pipelines.logs` and in the right order?
- **Conflicts:** test when both app and collector provide the same key, especially trusted values; no improper overwrites.
- **Duplicate ingest:** does writing both stdout and OTLP from the app ingest the same event into the index twice?
- **Cardinality and cost:** measure field counts, average event size, index mapping, query latency, and high-cardinality metrics.
- **Access control:** a user with tenant A permissions cannot find tenant B data by modifying UI/query filters.
- **Retention:** are logs with pseudonymous identifiers retained for too long?

### Java Testing Approach

With JUL, a test handler can capture `LogRecord` instances. With Logback/Log4j 2, use a real test appender/encoder and assert field values. **Do not just mock `LOG.info(...)`**, because mocking does not prove MDC/key–value pairs are emitted by the backend. With OpenTelemetry, test `LogRecord` objects against the actual SDK/exporter in use or query the backend in integration tests, rather than only comparing console strings.

## 15. Common Pitfalls and How to Fix Them

| Symptom | Typical Cause | Fix / Check |
| --- | --- | --- |
| `%X{requestId}` is empty | MDC not set, wrong key, or callback runs on another thread | Set scope at boundary, pass snapshot properly |
| Request B has A's `requestId` | Forgot to clean MDC on thread pool | `finally`, restore/clear, and test A → B → no-context |
| Log has `traceId` but trace won't open | Self-generated ID, trace not exported, sampling, or wrong context | Read from active span, check exporter/sampling |
| `addKeyValue` does not appear in JSON | Backend/layout does not support the fields | Use a real JSON/structured encoder and integration test |
| `service.name` is `unknown_service` | OTel Resource not configured | Set `OTEL_SERVICE_NAME` and check SDK/agent |
| Both `deployment.environment` and `deployment.environment.name` appear | Old/new semantic conventions and inconsistent mapping | Standardize by version and migration plan |
| `durationMs` is sometimes a number, sometimes a string | Producer/collector schema mismatch | Enforce typed fields + contract tests |
| Same log appears twice in backend | Collecting stdout and OTLP/file in parallel | Diagram ingest pipeline, remove unintended duplicate routes |
| Tenant A sees B's logs | Wrong context/routing or backend not enforcing ACL | Authenticate tenant, enforce server-side authorization |
| Metric cardinality spikes | Using `requestId`/`userId` as labels | Use only bounded labels, keep dynamic IDs in logs |
| Log contains raw token despite collector redaction | Data already exposed in stdout/file before processor | Redact at source and check all sinks |
| Exceptions lose fields | Caught/rethrown across another boundary, MDC cleared | Test error paths, scoping, and event capture |
| Enrichment is very slow | Formatting/serializing large objects even when level is off | Lazy computation, bounded attributes, profiling |
| Collector overwrites `service.version` wrongly | Multiple competing value sources | Define trusted sources and precedence |
| Too many `unknown` fields | Not distinguishing missing from propagation failure | Manage optional schema + alert on missing context |

## 16. Practical Implementation Checklist

1. **Choose observability goals**: request lookup, latency investigation, error classification, message tracing, or deployment distinction; do not enrich endlessly.
2. **Design the schema** around Resource / request-span / event attributes, applying semantic conventions where possible.
3. **Maintain sources of truth:** service/version from deploy, tenant from authenticated principal, event/outcome from business logic, trace/span from tracing instrumentation.
4. **Standardize fields and types**: stable keys, typed numbers/durations, missing/null policies, schema evolution.
5. **Enrich at the right place**: event attributes at log time, context at middleware, resource at runtime/collector; do not mistakenly write to global MDC.
6. **Keep scopes safe**: `try/finally` to clean MDC; thread pools/reactive/message brokers propagate context across boundaries without leaking between tasks.
7. **Pick one verified ingest pipeline**: structured stdout or OTLP bridge, distinguish sinks, and avoid duplicates.
8. **Minimize data**: do not log credentials, full bodies/headers, or unnecessary PII; validate inputs and redact at the source.
9. **Test end-to-end**: appender, JSON encoder, OTel mapping, collector, backend, access control, missing context, error paths.
10. **Monitor telemetry quality**: missing trace/request rates, parser errors, mismatched field types, duplicate ingest, queue drops, and cost.
11. **Long-term governance**: field catalog, owners, versioning, retention, and policies for adding/removing fields.

**Remember:** Log enrichment is attaching **the right metadata to the right event in the right context**, not just increasing character count in messages. Resource identifies the source, context links the request/trace, and event attributes explain the action and outcome. Context accuracy, async propagation, typed schemas, data protection, and testing against real sinks determine whether enrichment truly improves observability.

### Official References

- OpenTelemetry — [Logs Data Model](https://opentelemetry.io/docs/specs/otel/logs/data-model/), [Log correlation](https://opentelemetry.io/docs/specs/otel/logs/), [Semantic Conventions](https://opentelemetry.io/docs/specs/otel/semantic-conventions/).
- OpenTelemetry — [Service Resource attributes](https://opentelemetry.io/docs/specs/semconv/resource/#service), [Deployment environment](https://opentelemetry.io/docs/specs/semconv/resource/deployment-environment/), [Java instrumentation and logging](https://opentelemetry.io/docs/languages/java/instrumentation/).
- SLF4J — [Manual, Fluent API, MDC](https://www.slf4j.org/manual.html), [MDC API](https://www.slf4j.org/api/org/slf4j/MDC.html).
- Logback — [Mapped Diagnostic Context](https://logback.qos.ch/manual/mdc.html), [Configuration](https://logback.qos.ch/manual/configuration.html).
- Apache Log4j 2 — [Thread Context](https://logging.apache.org/log4j/2.x/manual/thread-context.html).
- OWASP — [Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html).
- Oracle Java 17 — [`java.util.logging.LogRecord`](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/LogRecord.html), [`java.util.concurrent.ExecutorService`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html).
