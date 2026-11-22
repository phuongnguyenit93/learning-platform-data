# Choosing Standard Fields in a Java Logging Strategy

## 1. Why standardize fields?

**Choosing standard fields** means deciding on the **name, data type, meaning, source, presence condition, and protection level** for each field in a log record. A Java log line that only writes `"Error occurred"` makes it difficult for dashboards to query, group errors, or link to a trace. Conversely, an event with many uncontrolled fields can waste resources and expose sensitive data.

For example, two services both log about an HTTP request but use inconsistent names:

```text
orders-api: requestId=req_42 code=503 took=17
billing-api: req_id=req_42 httpStatus="503" elapsed=17000000
```

Without a contract, readers do not know whether `took` and `elapsed` share the same unit, whether status is a number or a string, or whether `requestId` and `req_id` come from the same trusted source.

The goal is a stable **event schema** that can be parsed, tested, filtered, aggregated into metrics, and correlated with other logs/traces without guessing from a message sentence. This lesson belongs to the **Logging Strategy Design** group and applies to JUL, SLF4J, Logback, Log4j 2, and OpenTelemetry in the Java ecosystem.

After this lesson, you will be able to:
- Distinguish between core envelope, resource, correlation, and event-specific fields.
- Choose timestamp, severity, event code, service/environment/version, trace/span ID, error type, HTTP/messaging attributes, and duration.
- Know which parts belong to the **OpenTelemetry Logs Data Model**, which belong to **Elastic Common Schema (ECS)**, and which are just application JSON conventions.
- Define data types, units, null/optional/conditional fields, enums, and schema versions.
- Avoid tokens/PII/raw payloads and high-cardinality index labels.
- Write a complete Java 17+ example, inspect emitted JSON, and test against log injection.
- Design migrations and schema test suites from the call site to the collector/dashboard.

## 2. Four field groups and necessity levels

| Group | Examples | When is it needed? |
| --- | --- | --- |
| **Core envelope** | timestamp, severity, event name or message | Most events; used to know when and what happened |
| **Resource** | service.name, service.version, deployment.environment.name | Describes the log emission source; taken from deploy/config |
| **Correlation** | request/correlation ID, trace ID, span ID | When an event belongs to a request, job, or trace |
| **Event-specific** | http.route/status/duration, Kafka topic/partition/offset, error.type | Only when the event is relevant and the data is meaningful |

Do not apply all fields to all events. `service.started` has no `http.route`; `message.processing.failed` may have a Kafka offset but no HTTP status. A field that is **not applicable** should usually be omitted rather than filled with a dummy value.

Example of an application-defined JSON schema:

```json
{
  "timestamp": "2026-11-10T00:00:00Z",
  "severity_text": "ERROR",
  "event_name": "http.server.request.completed",
  "service.name": "orders-api",
  "deployment.environment.name": "production",
  "http.request.method": "GET",
  "http.route": "/orders/{id}",
  "http.response.status_code": 503,
  "duration_ms": 17,
  "correlation_id": "req_42",
  "error.type": "upstream_timeout"
}
```

**Important:** This is an **application JSON format**, not automatically a standard OTLP payload just because the field names look like OpenTelemetry. If exporting OTLP, you need to map timestamp, severity, and event name to the corresponding LogRecord fields, `service.name` to Resource, and HTTP properties to Attributes.

## 3. OpenTelemetry Logs Data Model: which field belongs to which layer?

OpenTelemetry LogRecord has separately defined components:

| Component | Meaning | How to map from application JSON |
| --- | --- | --- |
| `Timestamp` | Time the event occurred | `timestamp` |
| `ObservedTimestamp` | Time the observer/collector saw the event | Set at the pipeline/observer when available |
| `SeverityText` | Level text such as INFO/WARN/ERROR | `severity_text` |
| `SeverityNumber` | Level on the OTel scale | Map from the logging framework; do not use raw JUL numbers |
| `EventName` | Stable event type name | `event_name` |
| `Body` | Human-readable/structured content | `message` or an approved body |
| `Resource` | Emission source | `service.name`, `service.version`, environment |
| `InstrumentationScope` | Scope/logger that created the record | Logger name/library, if available |
| `Attributes` | Event-specific attributes | `http.route`, duration, error.type |
| `TraceId`, `SpanId`, `TraceFlags` | Trace context | Only when valid and an active span exists |

### Timestamp and observed timestamp

An event is created in the JVM at `10:00:00.000Z` but received by the collector at `10:00:00.200Z`. These two timestamps are **not the same**. If a dashboard uses ingest time instead of the original event time, investigating log delays and event ordering can be wrong. Conversely, the event timestamp can also be skewed by clock skew on the host.

Use UTC with `Instant`/ISO 8601 or a backend-typed timestamp. When computing duration on the same JVM, use `System.nanoTime()` instead of subtracting two wall-clock timestamps. Synchronize infrastructure clocks and verify that the parser does not shift timestamps to another timezone.

### SeverityText and SeverityNumber

Each Java framework uses its own level scale:
- JUL: `FINE`, `INFO`, `WARNING`, `SEVERE`.
- SLF4J/Logback: `TRACE`, `DEBUG`, `INFO`, `WARN`, `ERROR`.
- OTel: defined `SeverityNumber` ranges.

Do not treat a JUL level number directly as an OTel SeverityNumber. Use a unified mapper from the bridge/backend. `severity_text` is the level of concern, **not synonymous** with `http.response.status_code` or business outcome. A valid `404` may be logged at INFO, while a `503` due to upstream timeout may be ERROR per service policy.

### Event name vs. message

```text
event_name=order.reservation.failed
error.type=out_of_stock
message="Inventory reservation rejected"
```

`event_name`/`error.type` are for machines, stable, and have a controlled value set; `message` is a human-readable description whose wording, locale, or context can change. Do not construct event names by concatenating the message, order ID, or trace ID:

```text
# Wrong: event_name=order.42.failed
# Right: event_name=order.processing.failed
```

## 4. Recommended core fields

| Recommended JSON field | Type | Policy |
| --- | --- | --- |
| `timestamp` | ISO 8601 UTC string or timestamp type | Record time of occurrence, with timezone |
| `severity_text` | enum/string | Standardized log level |
| `event_name` | string enum | Stable event name |
| `message` | optional string | Concise, no secrets/raw DTOs |
| `service.name` | string | Comes from deploy/resource config |
| `service.version` | string | Distinguishes releases/rollbacks |
| `deployment.environment.name` | string | test/staging/production per policy |
| `logger.name` | string | When needed to identify code component/scope |
| `correlation_id` | string safe ID | When there is an independent request/job ID |
| `trace_id`, `span_id` | standard IDs | When a tracing context actually exists |
| `error.type` | low-cardinality enum | On error |
| `duration_ms` | non-negative long | When the operation has a processing duration |
| `http.response.status_code` | integer 100–599 | When a response status exists |
| `http.route` | route template | When the web router knows the route |

**Not every key above is an OTel top-level field.** They belong to the application's JSON contract, which the backend/bridge later maps to OTel/ECS. Avoid using the exact OTel name while assigning a different type/semantics.

### Field names

- Choose one convention for custom keys (`snake_case` or namespace `app.*`); keep semantic convention keys intact when integrating with OTel.
- Do not simultaneously keep `requestId`, `req_id`, and `request_id` for the same meaning unless there is a migration plan.
- Do not reuse the `status` key for HTTP code, business status, and job state. Use `http.response.status_code` and `business.outcome` separately.
- Do not embed runtime values into field names (e.g., a `user_42` key), which causes the schema to grow unboundedly.
- If fields are added by a collector/encoder, check for collisions with application-provided fields.
- Distinguish source field names from target field names in mapping documentation.

### Data types and units

| Wrong | Right or clearer |
| --- | --- |
| `"status":"503"` when numeric aggregation is needed | `"http.response.status_code":503` |
| `"duration":"17ms"` | `"duration_ms":17` |
| `"retryable":"true"` | `"retryable":true` |
| `"timestamp":"10/11/26 07:00"` | `"timestamp":"2026-11-10T00:00:00Z"` |
| `"attempt":"third"` | `"retry_attempt":3` |
| `"trace_id":"null"` | Omit or use JSON null per contract |
| `"http.route":"/users/58392"` | `"http.route":"/users/{id}"` |

**Renaming alone is not enough to change units.** ECS `event.duration` is defined in **nanoseconds**: 17 ms must be mapped to 17,000,000 ns, not kept as 17 with an ECS name.

## 5. Required, conditional, optional, and unknown

A schema should explicitly state the rules:
- **Required for all events:** timestamp, service, environment, event name or message per internal contract.
- **Conditional:** HTTP status if the response has been sent/known; `error.type` when the event is a failure; trace ID if there is an active span.
- **Optional:** instance ID, deployment version, route if the router has not determined it yet.
- **Forbidden:** password, token, raw request body, or unapproved sensitive data.

Three states to distinguish:
1. **Not applicable:** a startup event has no HTTP route → omit the field.
2. **Unknown:** request has not completed yet → a started/unknown event has its own contract; do not fill in 200.
3. **Valid value of 0:** duration may be rounded to 0 ms → do not treat it as missing.

Do not write the string `"null"` to represent a missing trace. Do not generate an all-zero ID and treat it as a valid trace ID. If a client-provided correlation ID is invalid, reject it or generate a safe new ID, while recording the invalid input in a separate metric.

## 6. Correlation ID, request ID, and trace/span ID

### Correlation ID

A `correlation_id` generated by the application/ingress helps trace from access logs to application logs and background tasks. It is **not** a user identifier and must not contain tokens/emails. Input from headers like `X-Request-ID` is untrusted data; limit its length, character set, and trusted sources, and prevent CR/LF injection.

### Trace/Span ID

A W3C Trace ID is typically 16 bytes displayed as 32 hex characters; a span ID is 8 bytes displayed as 16 hex characters. Do not put `req_42` into the OTel `TraceId` field just because it links requests. For ECS, the corresponding keys are `trace.id` and `span.id`; OTel uses top-level `TraceId`/`SpanId`. If a project uses JSON `trace_id`, it must have a clear mapping.

**Only attach a real trace context.** When there is no active span, do not fabricate a trace ID. If sampling causes the trace backend not to keep the span, logs may still carry trace context, but the link to the trace will not open. With thread pools, async logging, message consumers, and virtual threads, context propagation must be tested in practice.

### MDC/ThreadContext

An SLF4J integration snippet requiring the SLF4J library on the classpath:

```java
String previous = org.slf4j.MDC.get("correlation_id");
try {
    org.slf4j.MDC.put("correlation_id", validatedRequestId);
    performBusinessOperation();
} finally {
    if (previous == null)
        org.slf4j.MDC.remove("correlation_id");
    else
        org.slf4j.MDC.put("correlation_id", previous);
}
```

This snippet **does not run standalone** because `performBusinessOperation` and `validatedRequestId` belong to the application. Do not copy the entire MDC/headers; another library may have put PII into the context. When an async exporter sends logs later, it must snapshot the context at the time the event occurs, not read the worker's MDC at send time.

## 7. HTTP fields and route safety

OpenTelemetry HTTP semantic conventions define fields such as:
- `http.request.method`: GET, POST, etc., or values normalized by instrumentation.
- `http.route`: **route template**, for example `/orders/{id}`, when the framework can actually determine it.
- `http.response.status_code`: integer if the status has been sent/received.
- `error.type`: low-cardinality error type when the operation has an error per contract.
- Some network/server details only when needed and approved.

**Do not log the raw path instead of `http.route`.** A path like `/reset-password/abc123` may contain a token right inside a path segment; stripping the query string alone is not enough. When the framework has not determined the route, omit `http.route` or use a safe application-controlled category instead of guessing every pattern with regex.

### Duration

Use `System.nanoTime()` to measure elapsed duration within a single process. Convert the result to ms and record `duration_ms` as a number; or use the backend's field with its corresponding unit. Time to first byte, server handling time, and end-to-end browser latency cannot be arbitrarily merged into one field.

Example 503:
- `http.response.status_code=503`: response status.
- `error.type=upstream_timeout`: error type.
- `severity_text=ERROR`: level decided by application policy.
- `business.outcome=FAILED`: if required by the business contract, not inferred automatically from status.

## 8. Fields for errors/exceptions

An error event may contain:
- Stable `event_name`, e.g., `inventory.reservation.failed`.
- `error.type` such as `upstream_timeout`, `validation_error`, `out_of_stock`.
- `exception.type` if the error class is needed (e.g., `java.net.SocketTimeoutException`).
- `exception.message` per policy; **may contain URLs, SQL, input, or secrets**.
- Controlled `exception.stacktrace` for errors that need investigation.
- `correlation_id`/trace ID for linking.
- `retry_attempt`, `retryable` if the handling contract includes those concepts.

OpenTelemetry has semantic conventions for `exception.type`, `exception.message`, and `exception.stacktrace`; do not include all of them in every log when unnecessary.

Integration example using SLF4J (requires `LOG`, `client`, and `approvedOrderRef` from the program):

```java
try {
    client.reserve();
} catch (java.net.SocketTimeoutException error) {
    LOG.error("event=inventory.reservation.failed "
              + "error_type=upstream_timeout order_ref={}",
              approvedOrderRef, error);
    throw error;
}
```

Only log `approvedOrderRef` if policy allows; do not dump the entire request/order DTO. When using the SLF4J overload that takes a throwable, verify that the backend actually receives the throwable. If the throwable message contains secrets, fix how the error is constructed or route logs to a channel with strict access control.

## 9. Fields for message queues, jobs, and databases

**Kafka/message processing** usually needs topic, partition, offset, and consumer group to know which record was received:
- `messaging.system`, `messaging.destination.name`, and partition/offset metadata according to the semantic conventions/library in use.
- `event_name=message.processing.failed`, `error.type`, `retry_attempt` when applicable.
- `correlation_id`/trace context, with validated headers.
- Do not log raw key/value/headers; they may contain PII.
- A Kafka offset **is not a global ID**; you must consider topic + partition + offset.

**Background jobs** may need:
- `job.name`/`job.type` with a finite set of values.
- Application-generated `job.run_id`, `retry_attempt`, `duration_ms`.
- `business.outcome`/`error.type` per contract.
- Do not log the entire job input or recipient list.

**Database operations** may need:
- `db.system.name`/`db.operation.name` per instrumentation version.
- `duration_ms` and `error.type`.
- Connection pool info or query category for investigation.
- Avoid raw SQL bind params, connection strings containing passwords, and result sets.

Some OTel messaging/database conventions are still in Development status. Pin SDK/agent versions and mappings, and do not assume every backend emits the same keys.

## 10. Privacy and forbidden fields

| Data | Risk | Replace with |
| --- | --- | --- |
| Password, OTP, API key, bearer/refresh token | Account/access takeover | Auth status/error code, no real value |
| Authorization, Cookie, Set-Cookie | Session secrets | Remove |
| Request/response body, DTO `toString()` | Widespread PII/business data leak | Event DTO allowlist |
| Raw URL/query | Email, token, recovery code | Route template |
| Email, phone, IP, user/tenant ID | Personal identification/tracking | Log only with purpose, policy, and retention |
| SQL parameters/result set | Personal/business data | Operation name, outcome |
| Raw exception message | May contain input data | error.type and approved diagnostic channel |
| Entire MDC/headers | Uncontrolled context | Allowlist keys |
| Arbitrary client-provided ID | Log injection and high cardinality | Server-generated/validated ID |

Hashing an email does not automatically make it anonymized. A consistent hash can still be guessed or linked across records. When pseudonymization is needed, you need a policy, key/mapping management, and appropriate access controls.

### Preventing log injection

Untrusted data may contain `\r`, `\n`, quotes, tabs, or control characters. If concatenated into plain-text logs, they can break structure and forge fake log lines. First, **do not log** unnecessary raw input; if needed, validate values/lengths and use a structured encoder that escapes according to the format. Parameterized logging separates the template from arguments, but does not by itself guarantee CRLF escaping at the output sink.

## 11. Standalone Java 17+ program: emitting events with standard fields

This example uses only JDK 17, JUL, and a small JSON serializer for a **controlled set of fields**. No Spring Boot/SLF4J/Jackson required. The program:
1. Emits an HTTP 503 event with a fixed timestamp and ERROR severity.
2. Uses a route template, numeric status/duration, and a validated correlation ID.
3. Has an `authorization` field containing a **fake** secret that is intentionally not logged.
4. Verifies that raw path, query, and token are not leaked.
5. Tests a correlation ID input containing a newline being replaced with `invalid`.
6. Captures events with a JUL memory handler and prints fixed output.

**Do not use this hand-written serializer as a production JSON library.** In real deployments, use a standard Logback/Log4j 2 encoder, Jackson, or the OTel SDK to handle all types, escaping, Unicode, and schemas.

Create the file **`StandardLogFieldsDemo.java`**:

```java
import java.time.Instant;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class StandardLogFieldsDemo {
    record HttpOutcome(Instant occurredAt, String requestId,
            String rawPath, int status, long durationMs,
            String authorization) {}

    static String safeRequestId(String id) {
        return id != null && id.matches("[A-Za-z0-9_-]{1,32}")
                ? id : "invalid";
    }

    static String safeRoute(String path) {
        return path != null && path.matches("/orders/[0-9]{1,8}")
                ? "/orders/{id}" : "/unmapped";
    }

    static String jsonQuote(String value) {
        StringBuilder out = new StringBuilder("\"");
        for (int i = 0; i < value.length(); i++) {
            char c = value.charAt(i);
            switch (c) {
                case '"' -> out.append("\\\"");
                case '\\' -> out.append("\\\\");
                case '\n' -> out.append("\\n");
                case '\r' -> out.append("\\r");
                case '\t' -> out.append("\\t");
                default -> {
                    if (c < 0x20) {
                        out.append(String.format(
                                java.util.Locale.ROOT,
                                "\\u%04x", (int) c));
                    } else {
                        out.append(c);
                    }
                }
            }
        }
        return out.append('"').toString();
    }

    static String json(Map<String, Object> fields) {
        StringBuilder out = new StringBuilder("{");
        for (var entry : fields.entrySet()) {
            if (out.length() > 1) out.append(",");
            out.append(jsonQuote(entry.getKey())).append(":");
            Object value = entry.getValue();
            if (value instanceof String s) {
                out.append(jsonQuote(s));
            } else if (value instanceof Number n) {
                out.append(n);
            } else {
                throw new IllegalArgumentException(
                        "Unsupported field type");
            }
        }
        return out.append("}").toString();
    }

    static String eventJson(HttpOutcome e) {
        if (e.occurredAt() == null || e.status() < 100
                || e.status() > 599 || e.durationMs() < 0) {
            throw new IllegalArgumentException("Invalid outcome");
        }

        boolean failed = e.status() >= 500;
        Map<String, Object> fields = new LinkedHashMap<>();
        fields.put("timestamp", e.occurredAt().toString());
        fields.put("severity_text", failed ? "ERROR" : "INFO");
        fields.put("event_name", "http.server.request.completed");
        fields.put("service.name", "orders-api");
        fields.put("deployment.environment.name", "test");
        fields.put("http.request.method", "GET");
        fields.put("http.route", safeRoute(e.rawPath()));
        fields.put("http.response.status_code", e.status());
        fields.put("duration_ms", e.durationMs());
        fields.put("correlation_id", safeRequestId(e.requestId()));
        if (failed) {
            fields.put("error.type", "upstream_timeout");
        }
        return json(fields);
    }

    public static void main(String[] args) {
        Logger log = Logger.getAnonymousLogger();
        log.setUseParentHandlers(false);
        log.setLevel(Level.INFO);

        List<String> emitted = new ArrayList<>();
        Handler capture = new Handler() {
            @Override public void publish(LogRecord record) {
                if (isLoggable(record)) {
                    emitted.add(record.getMessage());
                }
            }
            @Override public void flush() {}
            @Override public void close() {}
        };
        capture.setLevel(Level.ALL);
        log.addHandler(capture);

        try {
            Instant fixed =
                    Instant.parse("2026-11-10T00:00:00Z");
            HttpOutcome result = new HttpOutcome(
                    fixed, "req_42", "/orders/42",
                    503, 17, "Bearer FAKE_SECRET");
            String line = eventJson(result);
            log.severe(line);

            String suspicious = eventJson(new HttpOutcome(
                    fixed, "bad\nERROR forged",
                    "/orders/42?token=FAKE_SECRET",
                    200, 4, "FAKE_SECRET"));

            if (emitted.size() != 1
                    || !line.contains(
                        "\"http.response.status_code\":503")
                    || !line.contains("\"duration_ms\":17")
                    || !line.contains(
                        "\"http.route\":\"/orders/{id}\"")
                    || !line.contains(
                        "\"error.type\":\"upstream_timeout\"")
                    || line.contains("FAKE_SECRET")
                    || line.contains("/orders/42")
                    || !suspicious.contains(
                        "\"correlation_id\":\"invalid\"")
                    || suspicious.contains("FAKE_SECRET")
                    || suspicious.contains("\n")) {
                throw new AssertionError(
                        "Log schema contract failed");
            }

            System.out.println(
                    "captured_events=" + emitted.size());
            System.out.println(emitted.get(0));
            System.out.println("secret_leaked=false");
            System.out.println("invalid_id_rejected=true");
        } finally {
            log.removeHandler(capture);
            capture.close();
        }
    }
}
```

Compile/run:

```bash
javac StandardLogFieldsDemo.java
java StandardLogFieldsDemo
```

**Exact standard output:**

```text
captured_events=1
{"timestamp":"2026-11-10T00:00:00Z","severity_text":"ERROR","event_name":"http.server.request.completed","service.name":"orders-api","deployment.environment.name":"test","http.request.method":"GET","http.route":"/orders/{id}","http.response.status_code":503,"duration_ms":17,"correlation_id":"req_42","error.type":"upstream_timeout"}
secret_leaked=false
invalid_id_rejected=true
```

### Explanation and limitations

- A fixed `Instant` keeps the test independent of the clock. Production reads real time with an explicit timezone/precision.
- `LinkedHashMap` preserves key order in the demo output; **key order is not a JSON contract**.
- Status and duration are serialized as numbers. `error.type` is only present on failed events in the demo.
- `safeRoute` only handles one example route, not a general router. With Spring MVC, obtain the template from the framework.
- `safeRequestId` rejects IDs containing CR/LF. Real systems should issue server-generated IDs or validate the header source.
- `authorization` is not read in `eventJson`; the fake secret does not appear.
- `Handler` shows that the event reached the local logger, not that the collector stored it.
- `jsonQuote` demonstrates escaping; it is not a full JSON library for all production data.

## 12. SLF4J 2.x, Logback, and structured key/value

A traditional parameterized call:

```java
// Integration: LOG is an initialized org.slf4j.Logger.
LOG.info("event={} status={} duration_ms={}",
         "http.server.request.completed",
         statusCode, durationMs);
```

It builds a message according to the backend; **it does not guarantee three separate JSON fields** in the output. SLF4J 2.x has a fluent API with `addKeyValue`:

```java
LOG.atInfo()
   .addKeyValue("event_name", "http.server.request.completed")
   .addKeyValue("http.route", routeTemplate)
   .addKeyValue("http.response.status_code", statusCode)
   .addKeyValue("duration_ms", durationMs)
   .log("HTTP request completed");
```

This is an **integration snippet** requiring slf4j-api 2.x, a provider, and an appropriate encoder. You must end with `log(...)`; if forgotten, no event is emitted. The backend/layout must be configured to output key-value pairs (not just the message) for a JSON collector to see the fields. Do not pass raw DTOs, headers, or secrets through `addKeyValue`.

With Logback:
- You can add MDC, throwable, logger name, thread, and resource metadata via the encoder.
- Do not print the entire MDC via a pattern if libraries might put PII into it.
- With async logging, snapshot the context at event time rather than reading MDC from the exporter worker later.
- With JUnit/Logback `ListAppender`, check `getKeyValuePairs()`/formatted output according to the version.
- If the backend is Log4j 2, use the corresponding layout/test utilities; do not cast to Logback.

JUL `LogRecord` also carries level/logger/message/parameters/throwable, but `getMessage()` may be an unformatted template. A JUL→SLF4J/OTel bridge must map fields consistently and avoid bridge loops.

## 13. Mapping OpenTelemetry and ECS safely

A system may collect via OpenTelemetry while storing in Elasticsearch/ECS or Loki. Do not equate different names when they have distinct semantics.

| App JSON | OpenTelemetry | ECS | Notes |
| --- | --- | --- | --- |
| `timestamp` | `Timestamp` | `@timestamp` | Event time |
| `severity_text` | `SeverityText` | `log.level` | Severity mapping |
| `event_name` | `EventName` | `event.action`/`event.code` per taxonomy | Not 1:1 by default |
| `service.name` | Resource `service.name` | `service.name` | Service config |
| `deployment.environment.name` | Resource attribute of the same name | `service.environment` per ECS mapping | Check ECS version |
| `http.request.method` | HTTP attribute | `http.request.method` | Enum |
| `http.route` | Template attribute | Not synonymous with `url.path` | Target may need a custom field |
| `http.response.status_code` | HTTP attribute | `http.response.status_code` | Number |
| `duration_ms` | Custom attribute (ms) | `event.duration` (ns) if mapped | **Must multiply by 1,000,000** |
| `correlation_id` | Custom attribute | Custom field per policy | Not TraceId |
| `trace_id`/`span_id` | `TraceId`/`SpanId` | `trace.id`/`span.id` | Different ID formats |
| `error.type` | Error semantic attribute | `error.type` | Stable values |

ECS also has `event.outcome` with values `success`/`failure`/`unknown` when outcome is meaningful, `event.created` and `event.ingested` as pipeline timestamps distinct from `@timestamp`, and `ecs.version` to store the mapping version.

**Do not use** `event.outcome=ERROR` because ERROR is a level, not an outcome. ECS `event.duration` is measured in nanoseconds, unlike a custom `duration_ms` field. When converting OTel/ECS, use tested config/processors rather than just renaming keys on the dashboard.

Semantic conventions may be Stable or Development depending on the version; especially for messaging/database fields, check the SDK/agent version in use.

## 14. Choosing indexed labels and avoiding high cardinality

Log fields and metric/index labels are two different decisions:

| Field | Useful in logs? | Should it be a Loki/metric label? |
| --- | --- | --- |
| `service.name` | Yes | Usually yes, finite value set |
| `deployment.environment.name` | Yes | Usually yes |
| `service.version` | Yes | Consider if versions change frequently |
| `http.route` template | Yes | Possible after measuring route count |
| `error.type` enum | Yes | Possible |
| `correlation_id` | Yes per policy | **No** per-request label |
| `trace_id`/`span_id` | Yes when tracing is present | **No** high-cardinality label |
| `duration_ms` | Yes | Do not use continuous values as labels |
| `user_id`/raw URL/token | Avoid or forbid | No |

A separate label per request can create millions of streams/time series, increase memory/query costs, and defeat grouping. With Loki, keep IDs in parsed fields/structured metadata as supported by the backend, and choose stable stream labels. With Prometheus metrics, do not turn random IDs into labels.

## 15. Schema versioning and migration

A field strategy needs:
- **Owner** responsible for the dictionary of fields and event types.
- **Contract** documenting name, type, unit, source, sensitivity, and required/optional/conditional.
- **Schema version** for changes that could break queries.
- **Migration** for field renames/type changes; support dual-read in dashboards during the transition period.
- **Compatibility tests** at the logger, encoder, collector, and storage layers.
- **Deprecation policy** to remove old aliases in a planned way.
- **Retention/RBAC** by event type and sensitive data.

Illustrative contract example in **application-defined** YAML, not an OTel/ECS config:

```yaml
name: http.server.request.completed
schema_version: 1
owner: orders-platform
required:
  timestamp: "UTC ISO 8601"
  severity_text: "INFO|WARN|ERROR"
  service.name: "string"
  deployment.environment.name: "string"
  event_name: "stable enum"
  http.request.method: "enum"
  duration_ms: "integer >= 0"
conditional:
  http.response.status_code: "integer when response exists"
  error.type: "low-cardinality code when failed"
optional:
  http.route: "trusted route template"
  correlation_id: "validated or server-generated ID"
forbidden:
  - authorization
  - cookie
  - password
  - raw_request_body
  - raw_url_query
```

Do not force a connection aborted before a response into HTTP 200 just because an old schema requires a status. Adjust conditional fields and classify failures with a clear contract.

## 16. Testing standard fields

### 16.1. Unit testing the builder

Cases to test:
1. A 503 event has a numeric status, `error.type` enum, and non-negative duration.
2. A 200 event has no `error.type` if specified by the contract.
3. Null timestamp or status 99/600 is rejected.
4. Negative duration is rejected.
5. IDs containing CR/LF, quotes, or excessive whitespace/length do not go directly into JSON.
6. Routes containing raw IDs/queries do not appear; unknown routes are handled safely.
7. Fake tokens/cookies/Authorization and payloads are not serialized.
8. Strings are escaped by a standard encoder; JSON parses successfully.
9. Service/env are not taken from unverified request headers.
10. Optional/missing/null match the contract; zero is distinct from unknown.

### 16.2. Integration testing appender/collector

After emitting events:
- Verify the Logback/Log4j 2/JUL event has the right level, logger, K/V, and throwable.
- Verify JSON output through the real encoder, ensuring numbers remain numbers; do not rely solely on substring matching.
- Cross-check source fields against Resource/Attributes/Severity/Timestamp at the Collector.
- Verify ECS duration mapping is in nanoseconds and trace IDs are properly formatted.
- Test MDC cleanup, async propagation, and schema under scaled replicas.
- Use fake canaries in staging to verify sinks, exports, archives, and RBAC.
- Test legacy dashboards/alerts when a new schema version rolls out in parallel.
- Use a bounded timeout when waiting for async operations; do not use a fixed `Thread.sleep` to assume an event was stored.
- Do not treat a passing appender test as proof that the collector/storage received the log.

### 16.3. Code review checklist

| Question | Requirement |
| --- | --- |
| Does the field answer a query/runbook? | Has a purpose/consumer |
| Are the name and mapping standard? | Clear dictionary/version |
| Is the type right? | JSON number/bool/timestamp |
| Is the unit stated in the key/contract? | Clear ms/ns/bytes |
| Is the source trusted? | Config/server-generated/validated |
| Is it PII/secret? | Minimization and policy |
| Could it be high-cardinality? | Not an arbitrary indexed label |
| When is it not applicable? | Required/conditional/optional |
| Is the schema tested at the backend? | Has integration tests |
| Does changing the field break dashboards? | Migration/deprecation |
| Does it appear in multiple sinks? | Check redaction/ACL/retention |

## 17. Common mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Each module names request ID differently | Cannot correlate logs | Dictionary + migration |
| Logging raw DTO/toString | Leaks PII when fields are added | Event DTO allowlist |
| Status as string, duration with "ms" text | Broken aggregations | Clear numeric type/unit |
| Mapping `duration_ms` to `event.duration` | ECS unit is ns | Convert accurately |
| Putting raw URL into `http.route` | Breaks semconv, PII/cardinality | Route template |
| Writing `trace_id=req_42` | Not a W3C trace ID | Separate correlation field |
| Using `event.outcome=INFO` | Confuses outcome with log level | Standard outcome enum |
| Logging full `exception.message` | May contain secrets | Review/sink policy |
| Copying all MDC/headers | PII and log injection | Allowlist, validate |
| Creating a label per request ID | High cardinality | Keep ID as parsed field |
| Renaming fields without versioning | Dashboards drop data | Migration/dual-read |
| Assuming flat JSON = OTLP | Wrong OTel model | Map top-level/Resource/Attributes |
| Forgetting `.log()` on SLF4J fluent | No event emitted | Terminate the builder |
| Testing only source code | Collector may rename/stringify | E2E contract tests |

## 18. Exercises

1. Run `StandardLogFieldsDemo` and explain why `http.response.status_code` is a number and `timestamp` is an ISO 8601 string.
2. Change status 503 to 200, observe `error.type` being omitted; discuss when severity should not be inferred from status.
3. Pass a request ID containing newline/quotes or excessive length; verify the field is replaced with `invalid`.
4. Add another safe route and compare it with using a raw URL containing `?token=FAKE_SECRET`.
5. Use JUnit 5 to write negative tests for null time, negative duration, and invalid status.
6. Map the JSON to an OTel LogRecord: Timestamp, SeverityText, EventName, Resource, Attributes.
7. Map the JSON to ECS and convert 17 ms to 17,000,000 ns.
8. Attach a valid W3C trace ID and create a link to the trace backend, distinguishing it from a self-generated correlation ID.
9. Add a Kafka event with topic/partition/offset; explain why offset alone is not enough.
10. Use SLF4J 2.x `addKeyValue` with a JSON encoder and verify the fields emitted at the sink.
11. Design a schema for `order.processing.failed` with `error.type` and business outcome without leaking the order DTO.
12. Try a migration between `requestId` and `correlation_id`; design dashboard dual-read.
13. Create a fake canary test for Authorization, Cookie, raw query, CRLF, MDC, and exception message.
14. Choose indexed labels for Loki/Prometheus and explain why trace ID is not used as a label.
15. Review three events: service started, HTTP error, and Kafka retry; distinguish required/conditional/optional.

## 19. Takeaways

- **Standard fields** require a name, type, unit, meaning, trusted source, presence condition, and protection level.
- Separate core envelope, Resource, correlation, and event-specific attributes; do not force every event to have all the same fields.
- OTel top-level Timestamp/Severity/EventName/TraceId differ from Resource and Attributes; custom JSON requires mapping when exporting OTLP.
- ECS `event.duration` is in nanoseconds; converting from `duration_ms` requires multiplying by 1,000,000.
- `http.route` is a route template; do not use raw URLs, and correlation ID is not TraceId.
- Avoid tokens/PII/raw DTOs/headers, log injection, and high-cardinality indexed labels.
- Keep field/event names stable, schema versions clear, and test migrations from the logger to the backend.

### References

- OpenTelemetry — Logs Data Model: https://opentelemetry.io/docs/specs/otel/logs/data-model/
- OpenTelemetry — Semantic conventions for events: https://opentelemetry.io/docs/specs/semconv/general/events/
- OpenTelemetry — HTTP semantic conventions: https://opentelemetry.io/docs/specs/semconv/http/http-spans/
- OpenTelemetry — Exception attributes: https://opentelemetry.io/docs/specs/semconv/registry/attributes/exception/
- OpenTelemetry — Deployment attributes: https://opentelemetry.io/docs/specs/semconv/resource/deployment-environment/
- Elastic — ECS Base fields: https://www.elastic.co/docs/reference/ecs/ecs-base
- Elastic — ECS Event fields: https://www.elastic.co/docs/reference/ecs/ecs-event
- Elastic — ECS Log fields: https://www.elastic.co/docs/reference/ecs/ecs-log
- Elastic — ECS Tracing fields: https://www.elastic.co/docs/reference/ecs/ecs-tracing
- SLF4J — User Manual: https://slf4j.org/manual.html
- Oracle Java 17 — Logger: https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Logger.html
- OWASP — Logging Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html
