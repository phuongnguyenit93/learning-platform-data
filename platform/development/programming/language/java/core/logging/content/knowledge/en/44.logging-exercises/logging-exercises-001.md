# Hands-on Project: Designing a Logging Baseline for a Java Service

## 1. Project Problem Statement

A Java application may function correctly and still be **hard to operate** if its logs consist only of disconnected sentences such as `Start process`, `Error happened`, or `User request: ...`. When an error occurs, the development team cannot answer which request failed, which service produced the log, what the impact is, how long it took, or whether it can be correlated with traces/metrics. Conversely, logging raw HTTP bodies and tokens for debugging convenience increases the risk of data leakage.

In this project, you will build a **logging baseline** — a **minimal, structured, secure, and operable logging contract** — for a hypothetical Java service named **`checkout-api`**. "Baseline" does not mean logging everything or building a complete observability architecture. It is a set of principles, schema, configuration, and tests good enough for similar services to follow while still leaving room for extension.

**Required deliverables:**

1. A **log schema** with field names, JSON types, semantics, required/optional rules, and data protection rules.
2. An **event catalog**: which events should be logged at INFO/WARN/ERROR, the event source, and the true outcome.
3. **Console JSONL** configuration for container environments or rolling files for VMs when needed; distinguishing each log source.
4. **Correlation context** with reliable request/trace IDs that do not leak when threads are reused.
5. A **test suite for schema, sensitive data, async behavior, and logging failures**.
6. A **minimal operational runbook**: how to search for events, investigate when logs are lost/delayed, and restore configuration.
7. **Acceptance evidence**: actual output, test PASS/FAIL results, effective config, retention policy, and designated owners.

The project has **two hands-on parts**. Part A is a standalone **pure JDK 17** program to learn the contract and self-verify the results. Part B is a **Spring Boot/SLF4J integration guide** with configuration for supported versions; the Spring snippets are only used when the project has the corresponding dependencies/framework.

## 2. Business Scenario and Scope

Suppose `checkout-api` receives a `POST /orders/{id}/checkout` request, checks inventory, and confirms a checkout operation. Possible outcomes are:

- **200**: checkout completed, event `checkout.completed`.
- **409**: request rejected by business rules such as out of stock, event `checkout.rejected`.
- **502/504**: dependency/gateway failure, event `checkout.dependency_failed` with a safe reason code.
- **401/403**: rejected by authentication or authorization, security handler emits a separate safe event.
- **202**: if only an async job is created, the event must reflect `checkout.accepted`; **do not** log "completed" before the worker actually finishes.

This scenario is solely for illustrating logging; **do not implement real payments** and do not log card data. A request may pass through an API gateway, service, worker, and collector; avoid double-counting or treating every event as a committed transaction.

### Implementation Scope

| In Scope | Out of Scope |
| --- | --- |
| Application events and safe HTTP metadata | Building a SIEM/trace backend from scratch |
| JSONL, levels, error codes, correlation IDs | Writing a new production JSON encoder from scratch |
| Redaction/field allowlist, privacy tests | Logging bodies/passwords/tokens for testing |
| stdout/file rolling, collector boundary | Claiming end-to-end exactly-once logging |
| Selective backend/encoder/collector tests | Replacing an audit store with an INFO logger |
| Minimal SLOs, retention, and runbook | Automatically deleting production logs |

**Principle:** do not invent framework APIs; standalone JDK examples are clearly separated from Spring Boot snippets, and collector configuration must be verified by the operators of the real system.

## 3. Proposed Baseline Architecture

```text
HTTP caller / scheduled job
          │
          ▼
Authentication + route matching
          │
          ├─ trusted actor/request/trace context
          ▼
Application service / business outcome
          │
          ├─ Structured event builder (allowlisted fields)
          │
          ▼
SLF4J facade / JUL / chosen backend
          │
          ├─ level + filters
          ├─ JSON encoder (1 event / 1 line)
          └─ bounded appender / stdout
                       │
                       ▼
             node agent / collector
                       │
              buffering + retry
                       │
                       ▼
            central log backend/index
                       │
              retention + RBAC
                       │
                search / alert

Security/audit event ──► independent audit policy/sink when required
Metrics & tracing ─────► own pipelines; correlate via trusted IDs
```

### Responsibility Boundaries

- **Business/application code** decides the event name, target, outcome, reason code, and business timing.
- **Security layer** determines the authenticated actor; never take `userId` from raw request headers/bodies.
- **Logging facade/backend** checks levels, encodes, and forwards events to stdout/file; **this does not mean the central backend has received them**.
- **Collector** gathers data, buffers, parses/routes, and forwards to the backend; requires lag, retry, and dropped-record metrics.
- **Search/storage** manages indexing, query permissions, retention, archiving, and investigation capabilities.
- **Tracing** creates/propagates trace/span context when properly instrumented. **Do not treat a trace ID as a human identity.**
- **Audit pipeline** has its own durability semantics when used as legal/business evidence; do not use a discarding `AsyncAppender` as the sole storage point for mandatory audit logs.

Every stage must have an owner. If the source logs correctly but the collector is misconfigured, the issue cannot be fixed simply with `logging.level.root=DEBUG`.

## 4. Logging Baseline vs. Metrics, Traces, and Audit

| Signal | Best Answers | Example |
| --- | --- | --- |
| **Application log** | What specific event occurred? | `checkout.rejected`, `error.code=OUT_OF_STOCK` |
| **HTTP access log** | Request to service, status, latency? | `POST /orders/{id}/checkout 409 4ms` |
| **Metric** | How much did error rate/latency change? | `checkout_rejected_total`, latency histogram |
| **Trace** | Which services/spans did the request traverse, where was time spent? | `trace_id`, `span_id`, dependency call |
| **Security event** | Which authentication/authorization was denied? | `authorization_denied` |
| **Audit event** | Which actor modified a resource and what was the business outcome? | `actor.id`, `target.id`, `COMMITTED` |

The access log line and the business event line **do not have to share the same status/outcome semantics**: HTTP 202 means the request was accepted, while the worker may fail later. Do not infer "business success" solely from HTTP 200.

Logging does not replace metrics: counting INFO logs can be skewed by sampling, async discards, or unindexed logs. Logging also does not replace tracing: a trace ID alone does not reveal every span or parent-child relationship.

## 5. Finalizing the JSONL Schema Before Coding

A **sample application event** can be represented as:

```json
{
  "@timestamp": "2026-11-10T03:15:00Z",
  "schema.version": 1,
  "level": "INFO",
  "service.name": "checkout-api",
  "event.name": "checkout.completed",
  "http.route": "/orders/{id}/checkout",
  "http.status_code": 200,
  "duration_ms": 12,
  "outcome": "SUCCESS",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "request_id": "req_101"
}
```

**This is the project's schema, not a guaranteed automatic output from every Logback encoder, OpenTelemetry, or ECS.** A library may use the key `log.level` instead of `level` or a nested object `http.status_code`; configure mappings and test the final output accordingly.

### Field Contract Table

| Field | JSON Type | Required | Source and Constraints |
| --- | --- | --- | --- |
| `@timestamp` | string | Yes | UTC ISO-8601, from the clock where the event is created |
| `schema.version` | integer | Yes | Schema contract version; not a string |
| `level` | string | Yes | Normalized severity from the backend |
| `service.name` | string | Yes | From trusted deployment config |
| `event.name` | string | Yes | Event code from a server-controlled enum/catalog |
| `http.route` | string | For HTTP events | Matched route template/class, not raw URI |
| `http.status_code` | integer | For HTTP completed | HTTP code 100–599; do not quote like `"200"` |
| `duration_ms` | integer | For completed events | Non-negative duration, measured with a monotonic clock |
| `outcome` | string | Yes | `SUCCESS`, `DENIED`, `FAILED`, `ACCEPTED`... per catalog |
| `trace_id` | string | If tracing context exists | 32 lowercase hex chars when using W3C Trace Context; do not fake IDs |
| `span_id` | string | Optional | 16 lowercase hex chars when an actual span exists |
| `request_id` | string | If request context exists | Format/length per policy, validate before logging |
| `error.code` | string | For business errors with codes | Safe enum; do not use raw exception message |
| `actor.type`/`actor.id` | string | Per security/audit contract | Verified principal; subject to privacy/retention |
| `tenant.id` | string | If multi-tenant | Verified tenant, not from raw header |

### Field Name and Shape Rules

- **Do not rename fields on a whim:** `duration_ms` is different from `duration` and `duration_ns`. Changing the unit while keeping the key is a serious bug.
- **Data types must be exact:** `http.status_code=200` is a JSON number; `success=true` is a boolean, not a string.
- **Do not derive keys from raw input:** event names and fields must be controlled by code/config.
- **Add fields only with purpose:** email, IP, and user ID can be PII; they are not "free" fields.
- **Error code is a stable enum** (e.g., `OUT_OF_STOCK`), distinct from exception messages that may contain secrets.
- **Null and missing:** define clearly. Startup logs may have no trace ID; do not log `trace_id="null"` as a real ID.
- **Timestamp:** UTC event time differs from ingestion time; the backend may add its own fields.
- **Schema version:** changing field names/types requires versioning/migration and checking dashboards/alerts.

The dotted fields in the example are **flat JSON keys**. If you choose nested objects, use a consistent nested schema and test the exact shape. Do not mix both styles arbitrarily.

## 6. Choosing JSON Lines Over Free-Form Text

JSONL requires each event to produce **one JSON object on one physical line**, making it easy for collectors to parse and type-check. Newlines inside a message must be encoded as the `\n` escape sequence inside a JSON string, never splitting one event across two lines.

Example:

```json
{"event.name":"checkout.rejected","message":"request\nrejected","http.status_code":409}
```

When read by a JSON parser, `message` contains a logical newline, but the raw JSONL remains a single line.

**Do not conclude a string is valid JSON merely by seeing it start with `{`.** You must parse it with a library capable of checking types, UTF-8, escaping, object shape, length, and duplicate-key policy if needed. Especially for stack traces, do not emit raw multi-line exceptions outside JSON if the pipeline contract requires JSONL.

In production, use the framework/backend JSON encoder or a tested library such as Jackson/logstash encoder. The simplified encoder code in the Java 17 section below is for learning only and intentionally does not support every value type.

## 7. Event Catalog: What to Log, at What Level, and When?

| Event | Suggested Level | Trigger | Key Fields |
| --- | --- | --- | --- |
| `checkout.started` | DEBUG or do not log per request | Workflow start | operation/request ID, no payload |
| `checkout.completed` | INFO | Business transaction completed | outcome, duration, target type, status |
| `checkout.rejected` | INFO/WARN per policy | Business rule rejection | reason code, status, request ID |
| `checkout.dependency_failed` | ERROR | Dependency failure requiring operational attention | safe error code, dependency class, trace |
| `checkout.retry_scheduled` | DEBUG/INFO | Valid retry scheduled | attempt, backoff class, operation ID |
| `authorization_denied` | Separate security event | Authorization layer denial | verified actor/anonymous, action, outcome |
| `health.checked` | Usually metric or minimal access log | Health probe | Avoid spamming app logs on every probe unless needed |
| `application.started` | INFO | Startup succeeded | safe version/environment |
| `configuration.changed` | Audit/admin event | Configuration changed | verified actor, change ID, no secrets |

**There is no universal INFO/WARN/ERROR rule for all organizations.** For example, an HTTP 409 from a normal business rule can be INFO rather than an infrastructure failure that wakes up on-call. ERROR should be reserved for actionable failures; do not turn every 4xx into ERROR if it causes alert fatigue.

### Common Mistakes to Avoid

- Logging INFO at the start of a controller saying "checkout success" before the transaction commits.
- Logging the same dependency failure at the HTTP client, service, controller, and exception handler as four duplicate ERRORs with no distinction.
- Calling `logger.error("Failed", e)` with an exception containing a raw URI/token.
- Logging `user={...}` using a username from the request body as the authenticated actor.
- Logging raw request/response objects or card information just to debug an issue.
- Printing a huge stack trace on every retry loop iteration with unbounded volume.

## 8. Designing Privacy and Security into the Baseline

**Never log by default:** passwords, OTPs, access/refresh tokens, `Authorization` headers, `Cookie`/`Set-Cookie`, session secrets, API keys, reset codes, PAN/CVV, private keys, raw request/response bodies, or URL queries containing secrets.

### Allowlist Instead of Blacklist

Suppose a request contains:

```text
POST /orders/991/checkout?promo=...&token=FAKE_SECRET_CANARY_494
Authorization: Bearer FAKE_SECRET_CANARY_494
Body: {"card":"FAKE_SECRET_CANARY_494"}
```

A safe log may contain only:

```json
{"event.name":"checkout.completed","http.route":"/orders/{id}/checkout","http.status_code":200,"duration_ms":12}
```

Do not put raw `requestURI`, query, headers, or body into the event; replace them with the router's **trusted matched route template**. Fields like `trace_id` or `request_id` should be length/format validated; never use them as proof of a logged-in user.

Risks that must be tested:

- **Log forging (CWE-117):** strings containing CRLF/control characters create fake records if a text formatter does not neutralize them.
- **Nested JSON:** a new `metadata.password` field can slip past old regexes.
- **Exception strings:** an HTTP client may include a response body or a URL containing a token inside its message.
- **PII in paths:** reset tokens, emails, or user identifiers may appear in the path even when the query string is stripped.
- **MDC/baggage:** personal data attached to context spreads into every subsequent event.
- **Backend copies:** dashboard masking does not remove data already written to files, indexes, or backups.

**A good baseline does not collect secrets at the source.** Collector masking is an additional defense layer, not the sole control.

## 9. Correlation: Attaching the Right IDs Without Leaking Across Requests

Logs are much easier to search when every event in the same request has a consistent `request_id` and, if the system uses distributed tracing, `trace_id`/`span_id`.

### Do Not Confuse the Three ID Types

| ID | Meaning | Do Not Infer |
| --- | --- | --- |
| `request_id` | Correlation key at the HTTP/app boundary | Does not prove user identity or transaction commit |
| `trace_id` | Key for a trace across multiple spans/services | Not synonymous with auth identity |
| `operation_id`/`job_id` | Key for a workflow that may span queues/retries | Does not imply one log per business action by default |

### Trust Boundary

`traceparent` and `X-Request-ID` may be sent by clients. When accepting IDs from the edge, validate them against spec/format/length and trusted proxy policy; do not print arbitrary raw strings or trust them as the actor. In multi-tenant systems, tenant identity must come from the authenticated context.

### ThreadLocal/MDC and Async

- For synchronous requests, you can set MDC in a filter and restore it in `finally`.
- Thread pools reuse threads; missing restore causes request B to inherit context from A.
- `@Async`, `CompletableFuture`, message consumers, and scheduled tasks do not automatically receive the right context just because the producer has MDC. Capture/propagate allowed metadata and clear it upon completion.
- Tracing libraries/Micrometer can handle propagation when configured, but **do not assume it is enabled by default** if dependencies/instrumentation have not been added.
- When there is no active trace, omit the field or indicate the state clearly; do not fabricate a "nice-looking" trace ID.

## 10. Hands-on Part A — Pure Java 17 with No External Dependencies

We will build **`LoggingBaselineDemo.java`** with these properties:

1. Writes JSONL through a real **JUL Logger and Handler**, rather than concatenating strings and pretending to call a logger.
2. Each event has typed fields: schema version, status, duration; codes use an allowlist.
3. Two requests have different trace/request IDs, and context is restored after processing.
4. Input contains a **fake canary**, and the token/card must not appear in output.
5. Tests in `main` verify event count, JSON field literals, event isolation, and the canary; failures throw `AssertionError`.
6. Timestamp is fixed for reproducible stdout. Production applications must read from a real `Clock`.

**Note:** The JSON encoder in this demo **only supports String/Integer/Long/Boolean data from a fixed schema**. Do not put it into production to replace Jackson or a dedicated encoder. The handler prints the encoded content controlled by the demo; the program does not implement an HTTP server, auth, queue, file rotation, or collector.

Create the file **`LoggingBaselineDemo.java`**:

```java
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.regex.Pattern;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class LoggingBaselineDemo {
    private static final Pattern TRACE =
            Pattern.compile("[0-9a-f]{32}");
    private static final Pattern REQUEST =
            Pattern.compile("[A-Za-z0-9_-]{1,64}");

    private static final ThreadLocal<RequestContext> CONTEXT =
            new ThreadLocal<>();

    record RequestContext(String traceId, String requestId) {
        RequestContext {
            if (traceId == null || !TRACE.matcher(traceId).matches()
                    || requestId == null
                    || !REQUEST.matcher(requestId).matches()) {
                throw new IllegalArgumentException("Invalid context IDs");
            }
        }
    }

    record SensitiveInput(String authorization, String card) {}

    private static void within(
            RequestContext context, Runnable work) {
        RequestContext previous = CONTEXT.get();
        CONTEXT.set(context);
        try {
            work.run();
        } finally {
            if (previous == null) {
                CONTEXT.remove();
            } else {
                CONTEXT.set(previous);
            }
        }
    }

    // Simple encoder only for application-controlled data.
    private static String quote(String text) {
        StringBuilder out = new StringBuilder("\"");
        for (int i = 0; i < text.length(); i++) {
            char ch = text.charAt(i);
            switch (ch) {
                case '"' -> out.append("\\\"");
                case '\\' -> out.append("\\\\");
                case '\n' -> out.append("\\n");
                case '\r' -> out.append("\\r");
                case '\t' -> out.append("\\t");
                default -> {
                    if (ch < 0x20) {
                        String hex = Integer.toHexString(ch);
                        out.append("\\u")
                                .append("0".repeat(4 - hex.length()))
                                .append(hex);
                    } else {
                        out.append(ch);
                    }
                }
            }
        }
        return out.append('"').toString();
    }

    private static String json(Map<String, Object> fields) {
        StringBuilder out = new StringBuilder("{");
        boolean first = true;
        for (Map.Entry<String, Object> item : fields.entrySet()) {
            if (!first) {
                out.append(',');
            }
            first = false;
            out.append(quote(item.getKey())).append(':');
            Object value = item.getValue();
            if (value instanceof String s) {
                out.append(quote(s));
            } else if (value instanceof Integer
                    || value instanceof Long
                    || value instanceof Boolean) {
                out.append(value);
            } else {
                throw new IllegalArgumentException("Unsupported field type");
            }
        }
        return out.append('}').toString();
    }

    private static void event(
            Logger logger,
            Level level,
            String eventName,
            int status,
            long durationMs,
            String outcome,
            String errorCode,
            SensitiveInput ignoredSensitiveInput) {

        if (!Set.of("checkout.completed", "checkout.rejected")
                .contains(eventName)) {
            throw new IllegalArgumentException("Unknown event");
        }
        if (!Set.of("SUCCESS", "DENIED").contains(outcome)
                || status < 100 || status > 599
                || durationMs < 0) {
            throw new IllegalArgumentException("Invalid event fields");
        }
        RequestContext ctx = CONTEXT.get();
        if (ctx == null) {
            throw new IllegalStateException("Missing request context");
        }

        Map<String, Object> fields = new LinkedHashMap<>();
        fields.put("@timestamp", "2026-11-10T03:15:00Z");
        fields.put("schema.version", 1);
        fields.put("level", level.getName());
        fields.put("service.name", "checkout-api");
        fields.put("event.name", eventName);
        fields.put("http.route", "/orders/{id}/checkout");
        fields.put("http.status_code", status);
        fields.put("duration_ms", durationMs);
        fields.put("outcome", outcome);
        fields.put("trace_id", ctx.traceId());
        fields.put("request_id", ctx.requestId());

        if (errorCode != null) {
            if (!Set.of("OUT_OF_STOCK").contains(errorCode)) {
                throw new IllegalArgumentException("Invalid error code");
            }
            fields.put("error.code", errorCode);
        }

        // Log only allowlisted fields, do not read token/card input.
        logger.log(level, json(fields));
    }

    private static void require(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    public static void main(String[] args) {
        Logger logger = Logger.getLogger("demo.logging.baseline");
        logger.setUseParentHandlers(false);
        logger.setLevel(Level.INFO);

        List<String> lines = new ArrayList<>();
        Handler capture = new Handler() {
            @Override
            public void publish(LogRecord record) {
                if (isLoggable(record)) {
                    lines.add(record.getMessage());
                }
            }

            @Override public void flush() {}
            @Override public void close() {}
        };
        capture.setLevel(Level.ALL);
        logger.addHandler(capture);

        SensitiveInput secret = new SensitiveInput(
                "Bearer FAKE_SECRET_CANARY_494",
                "FAKE_SECRET_CANARY_494");

        try {
            within(new RequestContext(
                    "4bf92f3577b34da6a3ce929d0e0e4736",
                    "req_101"),
                    () -> event(logger, Level.INFO,
                            "checkout.completed", 200, 12L,
                            "SUCCESS", null, secret));

            require(CONTEXT.get() == null,
                    "Context leaked after first request");

            within(new RequestContext(
                    "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                    "req_102"),
                    () -> event(logger, Level.WARNING,
                            "checkout.rejected", 409, 4L,
                            "DENIED", "OUT_OF_STOCK", secret));

            require(CONTEXT.get() == null,
                    "Context leaked after second request");
            require(lines.size() == 2, "Expected two events");
            require(lines.get(0).contains(
                    "\"http.status_code\":200"),
                    "Numeric HTTP status missing");
            require(lines.get(1).contains(
                    "\"error.code\":\"OUT_OF_STOCK\""),
                    "Safe error code missing");
            require(lines.get(0).contains(
                    "\"request_id\":\"req_101\"")
                    && !lines.get(0).contains("req_102"),
                    "First request ID incorrect");
            require(lines.get(1).contains(
                    "\"request_id\":\"req_102\"")
                    && !lines.get(1).contains("req_101"),
                    "Second request ID incorrect");

            for (String line : lines) {
                require(!line.contains("FAKE_SECRET_CANARY_494"),
                        "Sensitive input leaked");
                require(line.indexOf('\n') < 0
                        && line.indexOf('\r') < 0,
                        "JSONL event has physical newline");
                System.out.println(line);
            }
        } finally {
            logger.removeHandler(capture);
            capture.close();
        }
    }
}
```

Run commands:

```bash
javac --release 17 LoggingBaselineDemo.java
java LoggingBaselineDemo
```

**Exact stdout (two JSONL records):**

```json
{"@timestamp":"2026-11-10T03:15:00Z","schema.version":1,"level":"INFO","service.name":"checkout-api","event.name":"checkout.completed","http.route":"/orders/{id}/checkout","http.status_code":200,"duration_ms":12,"outcome":"SUCCESS","trace_id":"4bf92f3577b34da6a3ce929d0e0e4736","request_id":"req_101"}
{"@timestamp":"2026-11-10T03:15:00Z","schema.version":1,"level":"WARNING","service.name":"checkout-api","event.name":"checkout.rejected","http.route":"/orders/{id}/checkout","http.status_code":409,"duration_ms":4,"outcome":"DENIED","trace_id":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","request_id":"req_102","error.code":"OUT_OF_STOCK"}
```

**How to interpret the output:**

- `schema.version`, `http.status_code`, and `duration_ms` are JSON numbers rather than strings.
- The first event is INFO, and the second event is **WARNING** according to `java.util.logging.Level.WARNING`. In SLF4J/Logback the equivalent is typically **WARN**; if the dashboard expects the `WARN` enum, normalize or map it properly for the backend.
- `trace_id` and `request_id` are not mixed between the two contexts.
- `FAKE_SECRET_CANARY_494` does not appear even though it is present in `SensitiveInput`.
- Because `handler` is attached to a real JUL Logger, we verify that the logger/handler actually receives both events; however, the example does not test a collector or durable storage.
- `quote(...)` escapes quotes, backslashes, and ASCII control chars, and **is not a general-purpose production JSON serializer** (it does not handle Unicode surrogates, nested data, binary data, and many other types). Use a tested JSON encoder in real deployments.
- The fixed timestamp is a **fixture**, not how production obtains time. Real applications must record UTC/offset from a trusted clock source.
- The `ThreadLocal` in the example is for synchronous demo use only. When using executors/async, propagate context in a controlled manner and restore it in the worker.
- The business outcome values in the sample are hardcoded for illustration; production must reflect the actual business outcome that occurred.

## 11. Hands-on Part B — Spring Boot/SLF4J Integration

For new applications already using a **Spring Boot version with built-in structured logging**, you can start with JSON logging to the console. Per the Spring Boot 4.x documentation, the following properties are supported:

```properties
# application.properties for a compatible Spring Boot release
spring.application.name=checkout-api
logging.level.root=INFO
logging.level.com.example.checkout=INFO

# Use Spring Boot's built-in JSON Logstash format.
logging.structured.format.console=logstash
```

**Important points:**

- These properties **have no effect on the pure JDK program** in Part A.
- `logging.structured.format.console=logstash` is a **format identifier supported by Spring Boot in compatible releases**; on older Boot versions, you may need to add a separate JSON encoder. Do not apply it blindly to a Spring Boot version that does not support the property.
- If you already provide a custom `logback-spring.xml` or Log4j2 configuration, **your appender configuration may need to use the corresponding structured encoder/layout**. Setting the property alone may not override a custom pattern.
- The `logstash` format typically includes default backend fields such as `@timestamp`, `level`, `logger_name`, and `message`; **it does not match the JDK exercise schema 100% by default**.
- SLF4J 2 key-value pairs can appear in JSON if the encoder/framework supports them, but **you must run an integration test to verify field shapes and types**.
- Per the same Spring Boot documentation, you can choose `ecs` or `gelf` instead of `logstash` when the backend consumes those formats. Do not change formats without updating parsing/mapping and dashboards.
- **Do not enable both console JSON and file JSON if the collector gathers from both sources**: doing so can duplicate events or increase costs.

### Maven/Gradle and Versions

For a Spring Boot project, create the project using your organization's supported Spring Boot version, add Web and Test (and Actuator if you plan to use metrics/health), keep a single framework-selected logging backend, and lock versions in the repository build. The Part B examples are **integration guidance for an existing project**, not a standalone `pom.xml` with fixed versions for every environment.

If you only want to run the Part A example, **no Maven, SLF4J, Spring Boot, or JSON dependency is required**.

## 12. Spring Service: Structured Fields with SLF4J 2.x

Example **snippet** in a Spring Boot service with a configured `org.slf4j.Logger`:

```java
// Integration snippet; requires Spring Boot/SLF4J 2.x and the service logger.
logger.atInfo()
      .addKeyValue("event.name", "checkout.completed")
      .addKeyValue("http.route", "/orders/{id}/checkout")
      .addKeyValue("http.status_code", 200)
      .addKeyValue("duration_ms", 12L)
      .addKeyValue("outcome", "SUCCESS")
      .log("Checkout completed");
```

Here `.addKeyValue(...)` makes the key-value pairs clearer than text string concatenation. **However, it does not automatically guarantee** that the encoder produces the exact same JSON schema, because the backend/JSON format may serialize fields differently.

Corresponding code for an error case:

```java
// Snippet with an initialized logger; log only a safe reason code.
logger.atWarn()
      .addKeyValue("event.name", "checkout.rejected")
      .addKeyValue("http.route", "/orders/{id}/checkout")
      .addKeyValue("http.status_code", 409)
      .addKeyValue("error.code", "OUT_OF_STOCK")
      .addKeyValue("outcome", "DENIED")
      .log("Checkout rejected");
```

For consistent output, consider a **project-built** `AuditEventBuilder` / `ApplicationEventLogger` to standardize names, outcomes, units, field restrictions, and field collision policies. These class names are design abstractions, **not mandatory Spring classes**.

### Avoiding Duplicate Fields

A JSON encoder may automatically add `level`, `service.name`, `trace_id`, `@timestamp`. If the application also adds the same names via MDC/key-value, the output may contain duplicate JSON keys or overwrite values depending on the backend. Define **field ownership** clearly.

| Field | Suggested Owner |
| --- | --- |
| Timestamp/log level/logger | Logging backend/encoder |
| Service name/environment/version | Trusted deployment/config |
| Event name/action/outcome | Business/security code |
| HTTP route/status/duration | HTTP instrumentation/business boundary |
| Trace ID/span ID | Tracing instrumentation |
| Request ID | Gateway/filter generation/validation |
| Tenant/actor | Verified security context |
| Ingest time/host/agent ID | Collector/backend |

Never take `service.name` or `tenant.id` from self-reported client headers.

## 13. Correlation in Spring: MDC, Tracing, and Propagation

If Micrometer Tracing is enabled with the right dependencies/config in Spring Boot, the Spring Boot documentation describes correlation logging based on `traceId`/`spanId` in MDC. That helps find logs tied to a trace, but **it does not mean tracing dependencies are automatically enabled just because Actuator was added**. Verify that your build includes the appropriate tracing implementation.

A snippet for setting a safe request ID in the current scope:

```java
// SLF4J snippet; validatedRequestId comes from a validated source.
String old = org.slf4j.MDC.get("request_id");
org.slf4j.MDC.put("request_id", validatedRequestId);
try {
    handleCheckoutRequest();
} finally {
    if (old == null) {
        org.slf4j.MDC.remove("request_id");
    } else {
        org.slf4j.MDC.put("request_id", old);
    }
}
```

**This is not a complete HTTP filter class.** It illustrates saving and restoring a single key. Never omit `finally` in a thread pool; do not use `MDC.clear()` to wipe out parent-layer context that you do not own.

### Asynchronous Processing

If the service enqueues a job:

1. While the HTTP request is authenticated, capture correlation metadata and `initiated_by` according to a valid schema.
2. Protect job metadata before passing it to a queue/DB; do not carry passwords/tokens into the job for logging convenience.
3. The worker runs under a **service identity** and has its own context; if you need to trace the initiator, record `initiated_by` with verified evidence.
4. Set up context within the message handler's scope and restore it upon completion.
5. On retries, keep `operation_id` and an attempt ID to distinguish a retry from a new operation.
6. Do not assume MDC is a distributed tracing system: propagation across processes/networks requires proper instrumentation.

Passing trace context through an HTTP client should rely on framework-supported builders/instrumentation; a manually created `new RestClient`/`new WebClient` may not be auto-instrumented depending on version/configuration.

## 14. HTTP Access Logs: Avoid Duplication and Do Not Dump Payloads

Application events in the service do not replace the HTTP server's access log. There are two common approaches:

- **Container/gateway access log** records method/status/duration and can capture requests before they reach the controller.
- **Application filter/instrumentation** records metadata based on the matched route and business boundary.

If both emit logs, that can be reasonable **as long as source/hop/event type are distinguished**, but you should not count log lines as actual request counts without a deduplication mechanism.

### Fields Not to Use by Default

- `getRequestURI()` / raw URL: may contain IDs, reset tokens, emails, queries.
- `getHeader("Authorization")`, `getCookies()`, `getQueryString()`.
- Request/response bodies, file uploads, and DTO `toString()`.
- Exception stack traces containing raw HTTP client responses.
- Unvalidated IDs from clients.

A safe access event may contain only `method`, **trusted matched route template**, `status`, `duration_ms`, validated `request_id`, and source service. For login/token/payment endpoints with special policies, you can use labels like `AUTH_ENDPOINT` or `PAYMENT_ENDPOINT`.

**Async/SSE/streaming:** a filter's `finally` block does not always correspond to response completion; if final status/duration is required, use the server/access logger or appropriate lifecycle instrumentation. Do not call `response.getStatus()` before completion and claim it is the final status.

## 15. Environment-Specific Configuration

A baseline should have **a single source of truth for policy** and clear profiles:

| Environment | Format and Sink | Level and Purpose |
| --- | --- | --- |
| Local/dev | Console text or JSON as needed | Package-level DEBUG, no real secrets logged |
| Test/CI | JSONL/captured appender | INFO and schema/secret/trace tests; deterministic fixtures |
| Staging | Close to production | End-to-end verification, collector, retention, async |
| Production container | stdout/stderr JSONL + collector | Root INFO, reviewed package overrides |
| Production VM | Rolling file or stdout/systemd | File size + archive retention + permissions |

### Development Must Not Be a "No-Privacy" Environment

Do not enable raw bodies/tokens just because it is "running locally." Test data may be copied from production or end up in CI logs. Use fake canaries and test accounts.

### Minimal Production Baseline

- Root logger level INFO; reduce unnecessary DEBUG/TRACE.
- JSON structured output following the agreed format/schema.
- No secrets logged; exception/dependency logs are reviewed.
- Correlation IDs for request flows, with no context leakage.
- Health signals and ownership for queue/collector/sink.
- Retention classified by application/access/security/audit.
- Runbook for temporary DEBUG changes and rollback.
- Tests to detect schema drift, missing fields, and raw secrets.

## 16. Async Logging: Choose Trade-Offs Before Enabling

An async appender can reduce disk/network wait times on the request thread, but it is not magic. When the sink is slow:

```text
Application thread
    |
    ▼
Bounded queue ──► Consumer ──► File/stdout/collector
    |
    ├─ queue has space: enqueue
    └─ queue full: block / discard / fallback per policy
```

With Logback `AsyncAppender`, options such as `queueSize`, `discardingThreshold`, `neverBlock`, and `maxFlushTime` control load handling and event loss. Logback documentation notes that by default it may discard INFO/DEBUG/TRACE early when the queue is nearly full (depending on configuration). If `neverBlock=false`, producers can be blocked when the queue is full; `neverBlock=true` can drop events instead of blocking.

**Do not set `discardingThreshold=0` and claim "zero log loss."** Crashes, un-drained shutdowns, appender write errors, and backend failures can still cause loss.

### Questions That Must Have Answers

- How many events/bytes is the queue bounded to, and how many seconds of peak traffic can it absorb?
- When full, do you prioritize **request latency** or **log retention**?
- Which events can be discarded? Do mandatory audit/security events have a separate sink?
- Does the app have metrics for queue depth/dropped/wait/sink errors?
- Does shutdown/deploy rollout drain the queue within a bounded time?
- During prolonged collector outages, how long can node disk/spooling hold out?
- Do replays or retries create duplicates? Are there event IDs/operation IDs for reconciliation?

**Evaluate with load tests** using a slow sink and traffic bursts; do not choose a policy based solely on an ideal-case throughput benchmark.

## 17. File Rotation and Retention Are Not the Same Thing

If an application running on a VM needs file logging, **`FileAppender` without rolling** can let the file grow unboundedly. Logback provides `RollingFileAppender` with size/time policies:

```xml
<!-- Logback snippet; choose when deploying a file sink on a VM. -->
<appender name="APPLICATION"
          class="ch.qos.logback.core.rolling.RollingFileAppender">
    <file>logs/application.log</file>
    <rollingPolicy
            class="ch.qos.logback.core.rolling.SizeAndTimeBasedRollingPolicy">
        <fileNamePattern>logs/archive/app.%d{yyyy-MM-dd}.%i.log.gz</fileNamePattern>
        <maxFileSize>50MB</maxFileSize>
        <maxHistory>7</maxHistory>
        <totalSizeCap>1GB</totalSizeCap>
        <cleanHistoryOnStart>true</cleanHistoryOnStart>
    </rollingPolicy>
    <encoder>
        <pattern>%d{ISO8601} %-5level %logger - %msg%n</pattern>
    </encoder>
</appender>
```

**This snippet uses a text pattern; it does not automatically produce JSON, nor does `logging.structured.format.console` automatically turn file output into JSON.** If the file sink needs structured JSON, swap in the appropriate encoder or use a supported/tested Boot structured file configuration. This is not a complete `logback-spring.xml`.

- `maxFileSize` triggers rollover; it is not an absolute hard quota.
- `maxHistory=7` with a daily date pattern means 7 archive periods, not strictly 7 files.
- `totalSizeCap` caps the total archives managed by the policy, not the entire filesystem.
- Cleanup may run on rollover/startup and is not guaranteed to the exact second.
- Application access logs, Tomcat, gateway, container stdout, and the central backend each have separate retention.

In Kubernetes, stdout/stderr are typically rotated by the container runtime/kubelet; files written directly to a volume are not automatically managed by kubelet. Do not let both the rolling appender and host `logrotate` **rotate the same file** without testing; `copytruncate` can introduce a log-loss window.

**Retention must be classified:** DEBUG/application/access logs can be kept shorter than security/audit logs. There is no single default number of days valid for every organization; decide based on business, contractual, legal, and legal-hold requirements.

## 18. Audit/Security Events: A Separate Path When Durability Matters

A permission change may require answering "who did it, who was affected, and what was the true outcome?" Baseline application logging is helpful, but it is not enough to prove audit reliability.

Audit events should be clearly separated:

```json
{
  "event.name": "role.granted",
  "actor.type": "USER",
  "actor.id": "user_42",
  "target.type": "USER",
  "target.id": "user_91",
  "outcome": "COMMITTED",
  "operation_id": "op_19"
}
```

Do not use `target.id` as the actor; do not take the actor from a raw `X-User-ID`. If a worker runs under a service identity on behalf of a user, you can record `executor=SERVICE` and `initiated_by=USER` **if the link has been verified**, rather than conflating them.

For post-transaction audits, consider a **transactional outbox** or dedicated storage to tie business state to the event within the same transaction; you still need retries, duplicate handling, store protection, and proof that the event was ultimately ingested.

### Do Not Arbitrarily Sample Audit Events

Sampling 1/100 debug logs may make sense under high traffic, but sampling `role.granted` events can destroy evidence. Choose policies by **event kind** and retention requirements; do not apply the same discard mechanism to all streams.

## 19. Baseline Error Handling and Exception Hygiene

When a dependency fails, you need to know:

- The **service-type** dependency name, not necessarily sensitive internal URLs/hosts.
- A server-defined safe reason code, such as `PAYMENT_TIMEOUT` or `INVENTORY_UNAVAILABLE`.
- Status and business outcome at the right checkpoint.
- Request/trace/operation ID to locate the processing chain.
- Duration and attempt number when retrying.
- Exception type/stack trace **only when reviewed for potential secrets**.

Avoid:

```java
// UNSAFE example, snippet:
logger.error("Failed request {}", request);
logger.error("Headers={}, body={}", headers, body);
logger.error("Dependency error " + exception.getMessage());
```

These calls can pull tokens/PII from DTOs, headers, or library messages. Replace them with an event containing allowlisted fields and an error code; if stack traces are needed, route them to a sink with its own policy and testing.

**An error event should have a clear owner.** Do not let the same exception be logged as ERROR repeatedly at every layer when no new information is added. You can log one ERROR at the HTTP/business boundary while inner steps use metrics or controlled debug context.

## 20. Baseline Testing: Unit, Integration, and End-to-End

A log schema that looks right in code does not guarantee the JSON encoder/backend is correct. At least three layers are needed:

| Layer | Test Scope |
| --- | --- |
| Unit | Event catalog, required fields, safe codes, allowed value types |
| Integration | Real logger + encoder + appender, JSONL output, levels/filters, MDC |
| End-to-end | Collector → backend mapping/query, retention, dropped/lag, view permissions |

### Core Contract Test Suite

1. **Schema:** events have required fields; optional fields appear only when allowed.
2. **Type:** `http.status_code` and `duration_ms` are JSON numbers; `success` is boolean if in contract.
3. **Time:** timestamps parse cleanly, with explicit UTC/offset, not locale-dependent.
4. **Escape:** quotes/backslashes/CR/LF/Unicode do not split JSONL into multiple physical lines.
5. **Privacy:** fake canaries in headers/body/query/exceptions do not appear in JSON.
6. **Correlation:** requests A and B do not mix trace/request/tenant IDs.
7. **No context:** scheduled/startup events have a clear policy when request ID is absent.
8. **Error case:** safe error code, never automatically dumping a `Throwable` containing a token.
9. **Level:** INFO/WARN/ERROR are emitted or filtered according to actual effective config.
10. **Async:** drain or synchronize before assertions, rather than relying on lucky `Thread.sleep(...)`.
11. **Backpressure:** full queue, slow sink, shutdown, retry, and dropped semantics are tested.
12. **Collector:** parses types accurately, indexes the right service/tenant, time lag within threshold.
13. **Retention:** deletion follows policy; archives/backups/holds are verified separately.
14. **Deployment:** release/version changes do not break the schema or duplicate events.

### JSON Assertions with Jackson (Integration Test Snippet)

Assuming the test fixture has captured **one JSON line from the actual encoder** into `line`, you can use:

```java
// JUnit 5 + Jackson snippet; line is an actual JSONL line
// captured by the test fixture from appender/file/stdout.
com.fasterxml.jackson.databind.JsonNode node =
        new com.fasterxml.jackson.databind.ObjectMapper().readTree(line);

org.junit.jupiter.api.Assertions.assertTrue(node.isObject());
org.junit.jupiter.api.Assertions.assertTrue(
        node.path("http.status_code").isIntegralNumber());
org.junit.jupiter.api.Assertions.assertEquals(
        200, node.path("http.status_code").intValue());
org.junit.jupiter.api.Assertions.assertTrue(
        node.path("duration_ms").isIntegralNumber());
org.junit.jupiter.api.Assertions.assertFalse(
        line.contains("FAKE_SECRET_CANARY_494"));
```

**Do not just call `node.path(...).asInt()`** and assume you checked the type: some conversion APIs coerce numeric strings into ints. Check `isIntegralNumber()` or use a schema validator first.

If using ECS/Logstash/nested JSON, update the JSON paths to match **the chosen and test-verified format**; do not force the sample project's flat-key assertions onto a different format without mapping.

## 21. Baseline Release Gates for CI/CD

Recommended minimum set:

| Gate | PASS When |
| --- | --- |
| **Compile** | JDK 17 demo builds and runs, exit code 0 |
| **Content schema** | Required field names/types are valid for each event |
| **Secret scanner** | Canary does not appear in output/logs |
| **JSONL parser** | Each line parses into one valid JSON object |
| **Event isolation** | Request/trace IDs do not leak across contexts |
| **Logger config** | Effective levels/format match the profile |
| **Backend compatibility** | Encoder output parses and indexes per agreed schema |
| **Async/failure** | Does not breach p99 thresholds; dropped policy behaves as expected |
| **Operational safety** | Retention/quota/owners have evidence and alerts |
| **Audit preservation** | Mandatory events are not mistakenly sampled |

A passing test does not mean production will always preserve logs during a crash. Clearly separate **unit correctness**, **appender delivery**, **collector ingestion**, and **durability requirements**.

### Use Reproducible Fixtures

Inject `Clock.fixed`, use fake IDs/actors, and use **canary tokens**; never use real secrets in CI. Isolate logger state, MDC, and output capture between tests to avoid flaky tests during parallel execution.

## 22. Acceptance Test Data Matrix

This table helps reviewers immediately see what the project has completed:

| Scenario | Expected Event | Status/Outcome | Must Not Appear |
| --- | --- | --- | --- |
| Checkout succeeds | `checkout.completed` | 200 / SUCCESS | Token/card/raw body |
| Out of stock | `checkout.rejected` | 409 / DENIED | PII in error message |
| Dependency timeout | `checkout.dependency_failed` | 504 / FAILED | Full URL with token |
| Login denied | Security event from auth layer | 401/403 / DENIED | Password/OTP, self-reported actor |
| Job accepted | `checkout.accepted` | 202 / ACCEPTED | Marking completed before worker |
| Worker completed | `checkout.completed` | COMMITTED/SUCCESS per business rules | Confusing service executor with initiator |
| Health probe | Metric or minimal access log | 200/UP per schema | INFO log spam every few seconds |
| Unknown URL | Generic route class | 404 / FAILED per HTTP semantics | Client-supplied raw path/query |
| Logger sink failure | Appender error + metric | Delivery incident | Claiming saved before ack |

Do not log `actor.id=user_42` from a username in a rejected login request. An unauthenticated login attempt should be recorded as a clearly distinguished anonymous/claimed identifier if policy requires it.

## 23. Minimal Monitoring and SLOs

Recommended metric set (**not available by default** in every SLF4J backend):

| Metric / Signal | Purpose |
| --- | --- |
| `logging_events_attempted_total` | Number of events the application intended to emit |
| `logging_events_filtered_total` | Number filtered out by level/policy |
| `logging_events_dropped_total` | Number lost due to queue/overload |
| `logging_queue_depth` | Appender backlog |
| `logging_sink_errors_total` | File/stdout/socket write errors |
| `collector_receiver_accepted_total` | Number received by collector (per collector semantics) |
| `collector_exporter_failed_total` | Failures sending to backend |
| `log_ingest_lag_seconds` | Delay from event → searchable backend |
| `last_seen_log_event_timestamp` | Most recent data per source |
| `log_storage_used_bytes` | Risk of exceeding quota/retention |
| `audit_delivery_errors_total` | Audit pipeline needs separate evaluation |

**Do not compare counters across different boundaries as an exact equality:** windows, retries, filtered-by-design events, batch acks, and duplicates can cause discrepancies.

Example SLO targets **that must be tailored by the organization**:

- 95% of application events are searchable in the backend within 2 minutes of ingestion under steady load.
- Queue backlog does not persist beyond an agreed threshold.
- Zero unalerted sink errors.
- Production disk maintains safe capacity per forecast.
- Zero canaries or raw secrets entering disallowed sinks.
- Security/audit pipeline meets its own durability requirements.

If backend search is temporarily empty, distinguish **not yet seen**, **delayed**, and **lost**. A producer logging INFO does not prove the backend stored it.

## 24. Runtime Configuration and Access Permissions

### Containers

Applications typically write to stdout/stderr, and a collector reads and forwards them. Ensure:

- Consistent JSONL on the collected stream, avoiding mixed multi-line text.
- Node-local log rotation policy independent of backend retention.
- Health/metrics for the collector, disk spool, queue, and retries.
- Reliable namespace/service/tenant routing.
- Do not enable both file + stdout if that causes duplicate collection.

### VMs

If using a file appender, define the log directory, filesystem permissions, process user, quota, rotation, and collector tail behavior. An open `app.log` file may not release disk space immediately when unlinked; do not use `rm`/`truncate` as a default remediation.

### RBAC & Privacy

- **View/search** permissions differ from **change retention** and **delete**.
- Security/audit logs may require separate permissions and immutable archives.
- Dashboard masking does not delete raw copies in indexes, snapshots, backups, and exports.
- When an incident involves tokens/PII, revoke/rotate credentials and notify security—do not just lower the log level.

## 25. Failure Drill Scenarios for the Project

### Case 1: Collector Disconnected

The application continues printing JSONL, but no new events appear in the backend. Check source stdout, collector retries/lag, buffer policy, and how long it can buffer before logs are dropped. Do not restart the entire cluster just because the dashboard is empty.

### Case 2: Queue Full

Generate a burst in staging; verify whether the appender blocks the producer or discards events. Measure request p95/p99 and the number of lost events; ensure mandatory audit events are not dropped under debug policies.

### Case 3: Accidental DEBUG Enabled

Notice byte/s rate spiking after a deploy; check effective logger levels, size/event, serializer, MDC, stack traces, and log volume. Restore the target logger through the change process; do not suppress all ERRORs if they indicate real incidents.

### Case 4: Token in Exception

A fake canary appears in an HTTP client message; tests must FAIL. Fix at the source/encoder and check all copies: app file, stdout, collector, index, exports; for real secrets, trigger security response and rotation.

### Case 5: Wrong Trace ID Due to ThreadLocal

Two requests share a thread pool; the logger uses `MDC.put` without cleanup. Reproduce in a concurrent test, add scoping/restore, and confirm tenant/trace IDs do not mix.

### Case 6: Schema Drift

Changing the JSON encoder turns `http.status_code` from a number into a string. Dashboard aggregations break even though events still appear. Contract tests must catch this, and rollouts must follow schema versioning/migration.

### Case 7: Misconfigured Retention

Application logs are deleted after 7 days when investigations need 30 days; check ILM/index-age/rollover, node file rotation, and archives/snapshots. Do not delete or alter legal holds without authorization.

## 26. Extension Exercises for Learners

A complete project can be finished step by step:

**Phase 1 — Baseline contract:** create the event catalog and JSON schema; decide required/optional fields, units, enums, and PII classes. Explain why `status` is a number and why raw URLs are not logged.

**Phase 2 — JDK demo:** run `LoggingBaselineDemo.java`, verify the two JSONL records on stdout; modify the code to test missing context, invalid request ID, and log-forging negative cases.

**Phase 3 — Spring integration:** use a supported Spring Boot release, enable `logging.structured.format.console=logstash`, add SLF4J key-value fields in a service, and inspect the actual encoder output. Add mapping if the format does not match the chosen contract.

**Phase 4 — Context:** integrate request IDs across a trusted boundary and tracing if available; test two concurrent requests and an async job to confirm no context leaks.

**Phase 5 — Privacy:** inject `FAKE_SECRET_CANARY_494` into header/body/error fixtures, scan stdout/appender/backend; block at the source and add regression tests.

**Phase 6 — Operations:** configure the logging sink for VM/container, collector, retention/alerting, a slow-sink test, and an operational playbook.

**Phase 7 — Handoff:** review schema version, owners, CI gates, SLOs, privacy policy, and rollback instructions; save test evidence.

### Grading Rubric for the Hands-on Project

| Criterion | Passing Standard |
| --- | --- |
| Problem fit | Specific logging baseline architecture and goals for `checkout-api` |
| Data accuracy | Event catalog, schema, types, units, and outcomes are defined |
| Runnable | JDK 17 demo runs and outputs two valid JSONL records |
| Secure | No secrets/tokens/cards logged; uses route templates |
| Observable | Correlated request/trace IDs with context isolation |
| Integrated | Spring Boot JSON layout + SLF4J verified against actual output |
| Operable | Retention/quota, dropped/lag metrics, and runbook included |
| Tested | Unit/integration/E2E matrix and canary checks |
| Clear boundaries | Distinguishes app logging, access logs, audit, and tracing |
| Handoff ready | Owners, config/version, and acceptance evidence provided |

**Fails** if it only contains `logger.info("hello")`, or merely switches format from text to JSON without verifying schema, secrets, correlation, retention, and log searchability.

## 27. Common Anti-Patterns

| Anti-pattern | Why It Is Wrong | Replace With |
| --- | --- | --- |
| Logging free-form messages without a schema | Queries/aggregations break easily | Event codes + structured fields |
| Logging everything as ERROR | Alert fatigue, hides real severity | Level policy by event/outcome |
| Dumping raw requests/responses | Leaks tokens/PII, huge log volume | Field allowlist + route template |
| Hand-building JSON via string concatenation in prod | Escaping/type/encoding bugs | Tested JSON encoder |
| Using trace ID as the actor | Traces do not prove identity | Verified principal and audit schema |
| MDC without cleanup | Leaks request/tenant across thread pool | Scoped put + finally/restore |
| Unbounded async queue or "never lose logs" | OOM/drop/block or false assurance | Bounded queue, counters, failure tests |
| Non-rolling file logs | Disk full, hard to operate | Rolling/retention/quota or stdout with node rotation |
| Writing audit logs to a discarding debug log | Evidence can be lost | Dedicated audit policy/outbox |
| Changing JSON encoder without backend tests | Mapping/type/field drift | Consumer contract tests |
| Assuming dashboard presence means durability | Collector/index may lag or fail | End-to-end checks + acknowledgement semantics |
| Enabling root DEBUG during an incident | Volume/PII/CPU spike | Scoped temporary change + rollback |
| Not classifying data by retention | Keeps PII too long or deletes audit early | Retention by event kind and legal review |
| Using IDs as metric labels | Cardinality and cost explosion | Low-cardinality route/status/service |
| Printing raw exceptions | May contain tokens/bodies | Safe codes and controlled stack traces |

## 28. Sample Handoff README for a Real Service

When deploying the project into an organization's repository, each service's operational documentation should answer:

```text
Service: checkout-api
Owner: application on-call / observability on-call
Logging facade/backend: SLF4J + configured JSON backend
Default output: stdout JSONL (container)
Format contract: baseline schema v1 + accepted encoder mapping
Environment: production / staging / dev
Levels: root INFO, package overrides under change control
Correlation: validated request ID + trace/span context if enabled
Sensitive fields: token/password/card/raw body excluded at source
Event catalog: checkout.completed, checkout.rejected, ...
Retention classes: app/access/security/audit defined by owner
Sink/backpressure: known queue and failure policy
SLO/alerting: lag, dropped, sink errors, disk quota
Search workflow: service → event.name → trace/request ID
Change workflow: scoped DEBUG with expiry and rollback
Test evidence: schema JSON, privacy canary, async isolation, ingest
Escalation: application, platform, security/compliance
```

This is an illustrative template, not real environment values. Do not put secrets, sensitive internal URLs, or credentials into the handoff README.

## 29. Final Acceptance Checklist

- [ ] Clear objectives: troubleshooting, security, performance, and required level of detail.
- [ ] Full pipeline documented: Java → stdout/file → collector → backend.
- [ ] Event catalog includes event codes, owners, levels, outcomes, and emission conditions.
- [ ] Schema defines field names/types/units, required/optional status, and version.
- [ ] UTC timestamps, numeric status/duration, and safe route templates.
- [ ] Sensitive data excluded at the source; canary test PASSES.
- [ ] Log forging/escaping verified with a real JSON parser during integration.
- [ ] Request/trace IDs validated and never used as identity.
- [ ] MDC/context does not leak across requests, async workers, or tenants.
- [ ] Actual Spring Boot/SLF4J output format reconciled with the schema.
- [ ] File/stdout has an owner, rotation/quota, or appropriate collector policy.
- [ ] Separate retention policies for app, access, security, and audit.
- [ ] Observability for queue/backpressure, sink errors, dropped events, and ingest lag.
- [ ] Never claim logger call = backend saved.
- [ ] Tests cover startup, INFO/WARN/ERROR, missing fields, and schema drift.
- [ ] At least one sink failure test and one fake privacy leak test.
- [ ] Temporary DEBUG changes have authorization, scope, expiration, and rollback.
- [ ] Runbook exists for safely searching logs by event/ID and escalating to owners.
- [ ] Release gates, CI evidence, schema contract, and version change process in place.
- [ ] Clear boundaries: baseline does not replace audit durability, metrics, or traces.

**Remember:** a **compliant logging baseline** is not simply "turning on a logger" or "outputting JSON." It is a **shared contract across Java code, logging backend, collector, operations, and security**: log the right events, with the right types, in the right context, without leaking secrets, delivered to where they can be searched, retained for the right duration, and verified by real tests.

### References

- [Spring Boot — Logging, structured logging, and formats](https://docs.spring.io/spring-boot/reference/features/logging.html)
- [Spring Boot — Tracing, correlation IDs, and propagation](https://docs.spring.io/spring-boot/reference/actuator/tracing.html)
- [Spring Boot — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html)
- [SLF4J Manual — Fluent Logging API](https://www.slf4j.org/manual.html)
- [Logback — AsyncAppender](https://logback.qos.ch/manual/appenders-async-sift.html)
- [Logback — RollingFileAppender](https://logback.qos.ch/manual/appenders-rolling.html)
- [Oracle — java.util.logging.Logger (Java 17)](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Logger.html)
- [OpenTelemetry — Logs Data Model](https://opentelemetry.io/docs/specs/otel/logs/data-model/)
- [OWASP — Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html)
- [Kubernetes — Logging architecture](https://kubernetes.io/docs/concepts/cluster-administration/logging/)
