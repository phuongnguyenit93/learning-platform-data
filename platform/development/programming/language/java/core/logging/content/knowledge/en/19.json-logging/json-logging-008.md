# Field Context in JSON Logging: Attaching Context to Understand and Trace Events

In **JSON logging**, **field context** consists of structured fields that help answer **under what circumstances an event occurred**: which service, which request/job, which trace, which tenant or environment, and what operational attributes are needed to correlate related events. If you only log `"Payment failed"`, an on-call engineer knows an error happened, but not which transaction or request it belongs to. When context is added selectively, logs can be filtered, correlated, and analyzed by stable keys.

Example of a JSON record:

```json
{
  "timestamp": "2026-11-09T12:00:00Z",
  "level": "ERROR",
  "service": "checkout-service",
  "eventName": "payment.failed",
  "requestId": "req-17",
  "traceId": "0123456789abcdef0123456789abcdef",
  "paymentId": "pay-42",
  "errorCode": "UPSTREAM_TIMEOUT",
  "outcome": "failure"
}
```

`eventName` and `errorCode` indicate **what happened**; `requestId`, `traceId`, and `service` indicate **which context the event is attached to**. These values are illustrative examples only, not a mandatory field list for every system.

**Core principle:** field context must have a **clear name, data type, origin, and lifecycle**. There is no need to push every piece of available information into logs. Only add fields that genuinely support operations, comply with data policies, and do not make events noisy or hard to maintain.

## 1. Distinguishing Field Context from Event-Describing Fields

A logging event typically has multiple groups of attributes:

| Field Group | Question Answered | Examples |
| --- | --- | --- |
| **Event information** | What happened? | `eventName`, `outcome`, `errorCode` |
| **Severity and timestamp** | When, and how severe? | `timestamp`, `level` |
| **Resource/service context** | Which service/instance/environment did the event come from? | `service`, `environment`, `instanceId` |
| **Request/operation context** | Which request, job, transaction, or operation does it belong to? | `requestId`, `jobId`, `correlationId` |
| **Distributed tracing context** | Which trace/span across services does it belong to? | `traceId`, `spanId` |
| **Business entity** | Which entity is the record/task about? | `orderId`, `paymentId`, `customerType` |
| **Diagnostics and performance** | How long did the result take, what technical error occurred? | `durationMs`, `exceptionType`, `retryAttempt` |
| **Human-readable message** | What is the brief description? | `message` |

**Context is not completely separate from event data.** An `orderId` both identifies the entity of an event and serves as a correlation key linking events within the same workflow. Grouping helps make schema design easier to understand; systems may store fields at the top level or under a nested object.

Compare three ways of logging:

```text
Payment failed
Payment failed requestId=req-17 traceId=0123456789abcdef0123456789abcdef
```

and:

```json
{"eventName":"payment.failed","requestId":"req-17","traceId":"0123456789abcdef0123456789abcdef","errorCode":"UPSTREAM_TIMEOUT"}
```

The final JSON version contains **dedicated keys** for `requestId` and `traceId`—assuming the encoder actually emits them as JSON fields—so tools can filter or group without parsing the entire message. **Simply placing the string `requestId=...` inside `message` is not structured field context.**

## 2. What Is Field Context Used For?

### 2.1. Correlation: Linking Logs of the Same Request

A request passing through multiple layers can emit logs at the controller, service, repository, and when calling external dependencies. With the same `requestId`, you can search for:

```text
requestId=req-17
  12:00:00.001 API received
  12:00:00.010 inventory reserved
  12:00:00.029 payment call started
  12:00:00.305 payment timed out
  12:00:00.308 API returned failure
```

The data above is illustrative only. Actual logs may arrive at the collector out of strict order: clock skew across machines, buffering, async appenders, and network latency can cause arrival order to differ from emission order. Context helps **filter and join by key**, but does not replace distributed tracing when exact parent–child relationships are needed.

### 2.2. Pinpointing the Source of Errors Across Multiple Instances

When production runs multiple replicas, reading only `"Connection timeout"` is not enough. Fields such as `service`, `environment`, `region`, and `instanceId` can show whether errors are concentrated on a single instance/zone or spreading system-wide.

### 2.3. Analyzing Retries, Batches, and Background Jobs

Not all work starts from an HTTP request. Batch jobs and message consumers can attach `jobId`, `messageId`, or `attempt`. Avoid fabricating a fake `requestId` when there is actually no request; use context that accurately reflects the operation's lifecycle.

### 2.4. Dashboards, Alerts, and Incident Investigation

Stable context fields enable queries such as:

- Finding error logs for a specific `traceId` or `requestId`.
- Comparing timeout counts by `service` and `environment`.
- Distinguishing retries across `attempt` values when an operation ultimately fails.
- Correlating logs with metrics, traces, or operational error codes, provided those systems use compatible identifiers.

**Do not assume every field should be added to metric labels.** High-cardinality values such as `requestId`/`traceId` are well suited for looking up logs or traces, but are usually unsuitable as labels for every time-series metric because they can create an enormous number of data series.

## 3. Types of Context and Their Lifecycles

### 3.1. Resource- or Service-Level Context

Example:

```json
{"service":"checkout-service","environment":"production","region":"ap-southeast-1","instanceId":"checkout-7"}
```

These fields are usually **stable over the lifetime of a process or deployment**, rather than per-request data. They can be injected into logs by backend/encoder configuration or enriched by the collector from infrastructure metadata.

**Do not hardcode `environment=production` inside individual business methods.** Resource attributes should be configured centrally, and you should verify that collector values and application values do not conflict.

### 3.2. Request-Level Context

Example:

```json
{"requestId":"req-17","route":"/checkout","httpMethod":"POST"}
```

These fields typically exist from the time a request enters the application until the response is returned; they can be set by middleware/filter/interceptor and cleared when the request finishes. For `route`, prefer a **route template** such as `/orders/{id}` if supported by your infrastructure, avoiding raw paths containing personal data or dynamic IDs that create overly large grouping cardinalities.

### 3.3. Distributed Trace Context

Example:

```json
{"traceId":"0123456789abcdef0123456789abcdef","spanId":"0123456789abcdef"}
```

In W3C/OpenTelemetry-style tracing, a trace ID is typically represented as **32 hex characters** and a span ID as **16 hex characters**, with specific validity rules. The strings in the example have illustrative shapes of the proper length; real applications must obtain them from the **active tracing context**, not invent them arbitrarily.

**Distinctions:**

- `requestId`: a request identifier defined by the application/infrastructure, which may differ from `traceId`.
- `traceId`: a cross-service trace identifier when tracing is enabled.
- `spanId`: an identifier for a specific span within a trace.
- `correlationId`: a general organization-defined label, sometimes spanning multiple requests.

Do not arbitrarily copy `requestId` into `traceId`; if tracing is not enabled, leave the trace context absent according to the schema or use the official trace initialization mechanism—do not fabricate a fake ID that sends investigators to the wrong trace.

### 3.4. Event- or Operation-Level Context

Example:

```json
{"eventName":"payment.retry","paymentId":"pay-42","attempt":2,"maxAttempts":3}
```

`attempt` is meaningful only for the current retry attempt and should not be kept in the entire thread's context if other operations are unrelated. Many frameworks support **per-event key–value fields**; that is usually a better place for attributes belonging to a single log emission.

## 4. Organizing Context in JSON: Flat or Nested?

Two common representations exist.

### Flat fields

```json
{
  "timestamp": "2026-11-09T12:00:00Z",
  "level": "INFO",
  "service": "checkout-service",
  "requestId": "req-17",
  "traceId": "0123456789abcdef0123456789abcdef",
  "eventName": "checkout.started",
  "orderId": "ord-42"
}
```

Pros: simple queries when the index/collector expects top-level fields. Cons: names can collide across resource metadata, request context, and event payloads; harder to group attributes sharing the same scope.

### Nested context object

```json
{
  "timestamp": "2026-11-09T12:00:00Z",
  "level": "INFO",
  "eventName": "checkout.started",
  "context": {
    "service": "checkout-service",
    "environment": "demo",
    "requestId": "req-17",
    "traceId": "0123456789abcdef0123456789abcdef"
  },
  "orderId": "ord-42"
}
```

Pros: clear context boundaries, helping avoid overwriting top-level fields. Cons: queries must know paths like `context.requestId`, and depending on the backend, nested objects and dotted fields may be indexed differently.

**Do not treat the two forms as automatically equivalent.** The JSON:

```json
{"context.requestId":"req-17"}
```

has a **key containing a dot**, which is structurally different in JSON from:

```json
{"context":{"requestId":"req-17"}}
```

Some collectors/search engines may normalize or interpret dotted names, but the behavior must be verified against the actual pipeline.

**Choose according to an agreed schema.** If your organization uses OpenTelemetry Semantic Conventions, Elastic Common Schema (ECS), or an official log schema, follow the corresponding field names and locations; do not force a `context` object if it does not fit the standard. This article uses a nested `context` to clarify the concept, not to claim every backend must output it that way.

## 5. Field Context Must Have Stable Data Types and Semantics

| Illustrative Field | JSON Type | Meaning | Scope/Lifecycle |
| --- | --- | --- | --- |
| `service` | string | Logical service name. | Deployment or application |
| `environment` | string | Runtime environment. | Deployment |
| `instanceId` | string | Instance/pod emitting the event. | Instance |
| `requestId` | string or absent/null per schema | Current request. | Request |
| `traceId` | string or absent/null | Current trace if present. | Trace |
| `spanId` | string or absent/null | Current span if present. | Span |
| `jobId` | string or absent/null | Job being processed. | Background job |
| `orderId` | string | Permitted order identifier. | Event/operation |
| `attempt` | number (integer) | Attempt number; 1-based or 0-based convention must be explicit. | Retry event |
| `durationMs` | number | Duration in milliseconds. | Latency-measuring event |
| `eventName` | string | Stable event code. | Event |
| `errorCode` | string or null | Controlled error code. | Failure event |

Keep **names, types, units, semantics, and enums** consistent. For example, `attempt` should not be the number `2` sometimes and the string `"retry-2"` other times; `durationMs` must be in milliseconds, not silently switched to microseconds; `outcome` should use a consistent set of values.

**Missing, null, and empty strings are different:**

- **Missing field (absent)**: can mean the attribute does not apply, e.g., a background job has no `requestId`.
- **`null`**: the field exists but has no value; use only when the schema allows it and consumers interpret it correctly.
- **`""`**: an empty string, not automatically equivalent to `null`/absent.
- **`"unknown"`**: a value with special meaning; if used, it must be part of the contract, not used arbitrarily.

If a collector requires a field on every record, you can define a `null` or absent policy, but do not fabricate fake IDs or reuse an ID from a previous request to fill the gap.

## 6. Attaching Context at the Right Processing Boundaries

Standard design for an HTTP request:

```text
Incoming HTTP request
  |
  +-- Middleware creates/reads valid requestId
  +-- Obtains tracing context from tracer
  +-- Sets context for the current scope
  |
  v
Controller --> Service --> Repository --> Dependency
  |             |            |
  |             |            +--> logs same requestId/traceId
  |             +--> logs same requestId/traceId
  +--> logs final result
  |
  v
Finally / scope close --> clears/restores context
```

Key principles:

1. **Single source of truth:** middleware or tracing instrumentation defines `requestId`/`traceId`. Lower layers read from context or accept parameters rather than regenerating IDs themselves.
2. **Propagate only trusted values:** if reading a correlation ID from an external header, apply validation, length limits, control-character protection, and a policy for spoofed headers.
3. **Clear scope:** set context when a request or job starts, and clear/restore it when processing ends.
4. **No bleed into other requests:** pooled worker threads can be reused, so missing cleanup leaks context from a previous request.
5. **Do not obscure business data:** context like `requestId` does not replace event-specific `orderId`/`outcome`/`errorCode`.

For systems with many APIs, middleware is the appropriate place to standardize field names. Avoid copying manual `requestId` setup statements into every service method.

## 7. MDC in SLF4J: Execution-Thread-Bound Context

With SLF4J, **Mapped Diagnostic Context (MDC)** is commonly used to attach string key–value pairs to a processing scope. **Illustrative snippet** inside an application method using SLF4J + an MDC-capable backend:

```java
import org.slf4j.MDC;

// Assume LOG, requestId, and traceId already exist.
MDC.put("requestId", requestId);
MDC.put("traceId", traceId);
try {
    LOG.info("event=checkout.started");
    processCheckout();
} finally {
    MDC.remove("traceId");
    MDC.remove("requestId");
}
```

This snippet is **not a standalone class**: in real source code, `import` sits at the top of the file, `processCheckout()` is an application method, and variables must be declared. Assume `requestId` and `traceId` have already been validated and hold appropriate values.

MDC does not produce JSON by itself. It only passes context information to the backend; **the encoder/layout must be configured to output fields**. With a Logback text pattern, e.g., `%X{requestId}` or `%X{traceId}` can print values into a text line. To emit dedicated JSON fields, you need a structured encoder and corresponding mapping.

### Safer Scope: Restoring Previous Values When Nesting

If an inner layer overwrites an existing key, simply calling `remove()` can erase the outer layer's context. When nested scopes exist, **save and restore** the previous context. For example, SLF4J provides `MDC.getCopyOfContextMap()` and `MDC.setContextMap(...)`; an appropriate scope helper can retain a copy and restore it in `finally`.

For a single key, many SLF4J versions provide `MDC.putCloseable(key, value)` returning a closeable object to remove the key; however, to restore **an overwritten previous value**, you must check the helper's semantics and build a proper scope yourself. Do not assume "close" equates to restoring the entire previous map.

### MDC May Hold Only Strings

MDC typically stores `String` values. Therefore, `durationMs` or `attempt` placed in MDC may be emitted as JSON strings if the encoder does not convert types. Numbers needed for aggregation should be emitted as per-event typed fields when the backend/API supports them, or via verified schema mapping.

## 8. Log4j2 ThreadContext

The Log4j2 API provides `org.apache.logging.log4j.ThreadContext` to manage key–value context per execution thread, typically used with Log4j2 Core:

```java
// Illustrative snippet inside a method; LOG/requestId/traceId already exist.
org.apache.logging.log4j.ThreadContext.put("requestId", requestId);
org.apache.logging.log4j.ThreadContext.put("traceId", traceId);
try {
    LOG.info("event=checkout.started");
} finally {
    org.apache.logging.log4j.ThreadContext.remove("traceId");
    org.apache.logging.log4j.ThreadContext.remove("requestId");
}
```

This is an **illustrative snippet**, not a standalone program. Just like MDC, `ThreadContext` does not guarantee JSON output on its own. `PatternLayout` can use `%X{requestId}` in text; for structured output, you need an appropriate layout/encoder and dependencies.

Log4j2 also offers context data and scoped context mechanisms supporting certain configuration styles; behavior depends on version. In real applications, prefer scoping mechanisms provided by your framework/instrumentation, and verify which data the backend records during asynchronous processing.

**Avoid two different sources for the same field:** if application code uses SLF4J MDC while another component writes directly to Log4j2 `ThreadContext`, yet the runtime uses a different backend, the context may not reach the same pipeline. Verify the active provider, bridge, and integration.

## 9. Context Across ExecutorService, CompletableFuture, and Async Tasks

MDC/`ThreadContext` is usually bound to the current thread. **Do not assume** a task submitted to an executor will see the submitting thread's context. A worker thread may be a different thread or reused across multiple requests. Common symptoms therefore include:

- Child task logs **missing `requestId`**.
- Request B logs carrying **`requestId` from Request A** due to missing context cleanup on the thread pool.
- Retry or callback logs having the wrong `traceId`.
- Queries by `requestId` failing to connect asynchronous processing steps.

### Illustrating MDC Snapshot Propagation Across an Executor

The following illustrative snippet sits inside a method that has SLF4J `executor` and `LOG`:

```java
// Illustrative snippet with imports java.util.Map and org.slf4j.MDC.
java.util.Map<String, String> captured =
        org.slf4j.MDC.getCopyOfContextMap();

executor.submit(() -> {
    java.util.Map<String, String> previous =
            org.slf4j.MDC.getCopyOfContextMap();

    try {
        if (captured == null) {
            org.slf4j.MDC.clear();
        } else {
            org.slf4j.MDC.setContextMap(captured);
        }

        LOG.info("event=checkout.async_step");
    } finally {
        if (previous == null) {
            org.slf4j.MDC.clear();
        } else {
            org.slf4j.MDC.setContextMap(previous);
        }
    }
});
```

This is **non-standalone illustrative code**, because `executor` and `LOG` must be created by the application, with shutdown/lifecycle and task exceptions managed per contract. The core idea is **capture a snapshot at submission time, apply it before running, and restore the worker thread's context in `finally`**.

Do not share a single mutable map across multiple requests. If your framework or tracing library already provides official context propagation, use it instead of writing custom wrappers everywhere. In reactive systems or virtual threads, context may be bound to different scopes; verify the right API/instrumentation.

### AsyncAppender Does Not Solve Propagation by Itself

Distinguish **passing context across application processing steps** from **an async appender/async logger writing events**. An async appender may capture certain context data at the moment an event is created, but it does not magically give a `CompletableFuture` task a `requestId` if context was never propagated to it. The source of truth remains the application's execution scope.

## 10. Per-Event Key–Value Fields vs. Request-Scoped Context

Not every attribute belongs in MDC. Compare:

| Attribute | Appropriate Scope | Reason |
| --- | --- | --- |
| `requestId` | Request context | Reused across many events in the same request. |
| `traceId` / `spanId` | Tracing context | Tied to the trace/span managed by the tracing subsystem. |
| `service` / `environment` | Resource attributes | Rarely changes; can be configured at backend/collector. |
| `orderId` | Operation or event | May change if a request processes multiple orders. |
| `attempt` | Retry event | Valid only for one attempt; must not leak to other logs. |
| `durationMs` | Specific event | Measured when the operation finishes; should have numeric type. |
| `errorCode` | Failure event | Meaningful only on error/rejection; must not linger after recovery. |
| `userRole` | Request context if truly needed | Must consider privacy and value stability. |

If a request processes 100 orders, putting `orderId` into MDC and forgetting to update or clear it will cause subsequent orders' logs to carry the wrong ID. In this case, keeping `requestId` in MDC and passing `orderId` per event can be safer.

### SLF4J 2.x Fluent Key–Value API

SLF4J 2.x can attach per-event key–value pairs explicitly:

```java
// Illustrative snippet requiring SLF4J 2.x, LOG, orderId, and durationMs.
LOG.atInfo()
   .addKeyValue("eventName", "checkout.completed")
   .addKeyValue("orderId", orderId)
   .addKeyValue("durationMs", durationMs)
   .log("Checkout completed");
```

These are **per-event attributes** and do not automatically create request-scoped MDC entries. These fields can preserve the data type of the original value, but **the backend and encoder must actually emit them as JSON fields**; a pattern containing only `%msg` may ignore key–value pairs.

Share helper/schema constants for field names so module A does not use `request_id` while module B uses `requestId`. However, defining key constants alone is not enough: semantics, units, enums, and types must also remain consistent.

## 11. Standalone Java 17 Example: Context Object in JSON Logs

The program below uses **JUL (`java.util.logging`) built into JDK 17**, requiring no Maven or external libraries. It demonstrates the idea of **context captured per event** as an immutable record and emitted as a `context` object in JSON.

- `service` and `environment` are application-level metadata.
- `requestId` is request context.
- `traceId` is tracing information when available; the second event illustrates the no-trace case with `null`.
- `orderId` and `outcome` are per-event data placed outside the `context` object.
- Logger and handler use explicit levels; the formatter receives context from the `LogRecord` itself, without relying on `ThreadLocal` during formatting.
- Time is fixed for **predictable stdout**.

**Save as `ContextFieldsDemo.java`:**

```java
import java.io.ByteArrayOutputStream;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.logging.Formatter;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;
import java.util.logging.StreamHandler;

public final class ContextFieldsDemo {
    private static final Logger LOG =
            Logger.getLogger("demo.checkout");

    private record Context(
            String service,
            String environment,
            String requestId,
            String traceId
    ) {}

    private record Event(
            String eventName,
            String orderId,
            String outcome,
            Context context
    ) {}

    private static String jsonString(String value) {
        if (value == null) {
            return "null";
        }
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
                        String hex = Integer.toHexString(c);
                        out.append("\\u")
                           .append("0".repeat(4 - hex.length()))
                           .append(hex);
                    } else {
                        out.append(c);
                    }
                }
            }
        }
        return out.append('"').toString();
    }

    private static final class JsonFormatter extends Formatter {
        @Override
        public String format(LogRecord record) {
            Event event = (Event) record.getParameters()[0];
            Context ctx = event.context();

            return "{"
                    + "\"timestamp\":"
                    + jsonString(record.getInstant().toString())
                    + ",\"level\":"
                    + jsonString(record.getLevel().getName())
                    + ",\"logger\":"
                    + jsonString(record.getLoggerName())
                    + ",\"eventName\":"
                    + jsonString(event.eventName())
                    + ",\"context\":{"
                    + "\"service\":" + jsonString(ctx.service())
                    + ",\"environment\":" + jsonString(ctx.environment())
                    + ",\"requestId\":" + jsonString(ctx.requestId())
                    + ",\"traceId\":" + jsonString(ctx.traceId())
                    + "}"
                    + ",\"orderId\":" + jsonString(event.orderId())
                    + ",\"outcome\":" + jsonString(event.outcome())
                    + "}\n";
        }
    }

    private static void emit(
            Level level,
            Instant timestamp,
            Event event
    ) {
        LogRecord record = new LogRecord(level, event.eventName());
        record.setInstant(timestamp);
        record.setLoggerName(LOG.getName());
        record.setParameters(new Object[]{event});
        LOG.log(record);
    }

    public static void main(String[] args) throws Exception {
        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.INFO);

        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        Handler handler = new StreamHandler(bytes, new JsonFormatter());
        handler.setEncoding(StandardCharsets.UTF_8.name());
        handler.setLevel(Level.ALL);
        LOG.addHandler(handler);

        try {
            Instant time = Instant.parse("2026-11-09T12:00:00Z");

            Context requestOne = new Context(
                    "checkout-service",
                    "demo",
                    "req-17",
                    "0123456789abcdef0123456789abcdef"
            );
            emit(
                    Level.INFO,
                    time,
                    new Event(
                            "checkout.started",
                            "ord-42",
                            "started",
                            requestOne
                    )
            );

            Context requestTwo = new Context(
                    "checkout-service",
                    "demo",
                    "req-18",
                    null
            );
            emit(
                    Level.WARNING,
                    time,
                    new Event(
                            "checkout.rejected",
                            "ord-43",
                            "rejected",
                            requestTwo
                    )
            );
        } finally {
            LOG.removeHandler(handler);
            handler.close();
        }

        System.out.print(bytes.toString(StandardCharsets.UTF_8));
    }
}
```

### Compile and Run

Requires JDK 17 or later:

```bash
javac ContextFieldsDemo.java
java ContextFieldsDemo
```

**Exact standard output of the program (two JSON lines):**

```json
{"timestamp":"2026-11-09T12:00:00Z","level":"INFO","logger":"demo.checkout","eventName":"checkout.started","context":{"service":"checkout-service","environment":"demo","requestId":"req-17","traceId":"0123456789abcdef0123456789abcdef"},"orderId":"ord-42","outcome":"started"}
{"timestamp":"2026-11-09T12:00:00Z","level":"WARNING","logger":"demo.checkout","eventName":"checkout.rejected","context":{"service":"checkout-service","environment":"demo","requestId":"req-18","traceId":null},"orderId":"ord-43","outcome":"rejected"}
```

### Why Does This Example Correctly Demonstrate the Concept?

1. `Context` is an **immutable** record containing only attributes with the same semantic scope; each request has its own snapshot. You cannot mutate a shared map and accidentally affect an older event when the formatter runs later.
2. `Event` separates `eventName`, `orderId`, and `outcome` from `context`, preventing event-only details from leaking into other logs.
3. `emit` creates a `LogRecord` with timestamp, level, logger name, and parameters containing `Event`; `JsonFormatter` retrieves that exact snapshot.
4. `logger.setUseParentHandlers(false)` prevents records from also going to the parent logger's console handler; data goes only into the `StreamHandler` configured in the program.
5. `handler.close()` flushes records before the program reads `ByteArrayOutputStream`, so stdout contains the exact two JSON events emitted.
6. `JsonFormatter` outputs fixed keys. The second event sets `traceId:null` instead of fabricating a fake trace ID; null/absent handling must be defined by the actual schema.
7. `jsonString` escapes quotes, backslashes, certain newlines, and control characters. This is a **simplified serializer for learning**, not a replacement for a proven JSON library or structured logging encoder in production, especially with unusual Unicode and untrusted data.
8. The example does not claim JUL has built-in JSON logging. We implemented a custom `Formatter` solely to illustrate **how a context snapshot becomes a JSON object**.

**Note:** putting a hex `traceId` in the demo does not create a real trace. In distributed systems, obtain trace/span IDs from an active tracer or instrumentation; do not guess them from `requestId`.

## 12. Including Context in JSON Output with Logback or Log4j2

### 12.1. Logback

With Logback Classic as the SLF4J backend, MDC can be output using a text pattern:

```xml
<!-- Illustrative snippet inside Logback's <encoder>. -->
<pattern>%level requestId=%X{requestId} traceId=%X{traceId} %logger - %msg%n</pattern>
```

The result is **text**, not a JSON object just because it has `=` key-value pairs. To get true JSON:

- Choose a JSON encoder/layout compatible with your running Logback version.
- Configure MDC fields or SLF4J key–value pairs to be emitted as explicit JSON keys.
- Test events with and without context, with exceptions, and with characters requiring escaping.
- Ensure field schemas are compatible with the collector and are not overwritten by metadata added by the pipeline.

**Do not assemble JSON manually using a pattern like `{"requestId":"%X{requestId}"}`** if values are not properly JSON-escaped; this can produce invalid JSON or log injection when data contains quotes, backslashes, or newlines.

### 12.2. Log4j2

Log4j2 `PatternLayout` can read `ThreadContext` via `%X{requestId}`. For JSON structured output, Log4j2 provides dedicated layouts, such as `JsonTemplateLayout` in versions with the appropriate module. You must add the corresponding dependency/layout template and verify the key mapping in the template.

Do not assume every context value should be serialized. Choose an **allowlist of required keys** to avoid leaking internal/sensitive context data into logs. When a backend automatically attaches exceptions, logger names, timestamps, or trace attributes, check field names and precedence to avoid key overwrites.

### 12.3. JUL

JUL has `LogRecord` and `Formatter`, but does not provide a standard MDC API equivalent to SLF4J MDC. With pure JUL code, you can:

- Pass required context in parameters/event wrappers (as in the demo).
- Use a tested, application-specific context propagation mechanism rather than a shared static mutable map.
- Use a JUL → SLF4J bridge if the system is designed around a unified backend that can map levels and context appropriately.

**A bridge does not invent `requestId`/`traceId` on its own.** If JUL code contains no context and no instrumentation propagates it, routing logs to Logback will not turn every event into correlated JSON.

## 13. Keeping Context Accurate with Nested Scopes and Transactions

A request can open multiple sub-operations:

```text
requestId=req-17
  |
  +-- checkout.start
  |
  +-- inventory.reserve
  |     +-- inventoryOperationId=inv-9
  |
  +-- payment.authorize
  |     +-- paymentId=pay-42
  |
  +-- checkout.completed
```

Do not leave `paymentId` in MDC across the entire thread if subsequent unrelated inventory events occur after `payment.authorize`. Approaches:

- **Request scope:** keep `requestId` and `traceId` in the broader scope.
- **Operation scope:** use a scoped context if a processing branch needs the same `paymentId` across multiple logs; remember to restore the previous value when finished.
- **Event fields:** record `paymentId`, `attempt`, and `durationMs` directly on the event if they are only meaningful at that point.
- **Resource fields:** keep `service` and `environment` stable at the encoder/collector, without mutating them per request.

If a request processes multiple orders, `orderId` may vary by branch; do not attach a single `orderId` to every log and assume all operations belong to the same order.

### On Rollback or Retry

Context only aids correlation. It **does not by itself prove a transaction committed**. With retries, a timeout on attempt 1 may recover on attempt 2. Logs should include `attempt`, `maxAttempts`, and `outcome` at the appropriate level; log `ERROR` only for a final failure when that reflects business behavior.

Do not set `outcome=failure` at request scope too early and forget to update it after a fallback succeeds. Each event's outcome should be emitted at the point where sufficient information is available.

## 14. Context and Exceptions: Complementary, Not Interchangeable

Example:

```json
{
  "level": "ERROR",
  "eventName": "payment.failed",
  "context": {
    "service": "checkout-service",
    "requestId": "req-17",
    "traceId": "0123456789abcdef0123456789abcdef"
  },
  "paymentId": "pay-42",
  "errorCode": "UPSTREAM_TIMEOUT",
  "exceptionType": "java.net.SocketTimeoutException"
}
```

Context fields explain **which request was being processed**. `errorCode` and exception/stack trace explain **what failed and where the cause lies**. Complete context cannot replace **passing `Throwable` through the proper API** when stack traces, causes, and suppressed exceptions are needed.

SLF4J example in `catch`:

```java
// Illustrative snippet; LOG and paymentId exist, and MDC already holds requestId.
catch (RuntimeException ex) {
    LOG.error("event=payment.failed paymentId={}", paymentId, ex);
    throw ex;
}
```

This is not standalone code. `paymentId` in the message is still text; if you want a dedicated JSON field, use an appropriate structured event API/encoder. If an upper layer is already responsible for logging the stack trace, avoid duplicate logging and rethrowing across multiple layers.

**Safety principle:** do not stuff the entire exception message into `requestId` or `traceId` to "preserve information," as doing so corrupts context semantics and can expose sensitive data. Keep context and error details in their proper fields.

## 15. Security and Privacy of Context

Context is easy to abuse because it looks like "harmless" metadata. In practice, many values can identify individuals or expose infrastructure details.

| Field | Potential Risk | Mitigation |
| --- | --- | --- |
| `userId` / `customerId` | Links activity to an individual. | Log only when truly needed; restrict access/retention; pseudonymize per policy. |
| `email` / `phone` | Direct personal information. | Avoid logging or mask upstream before emission whenever possible. |
| `sessionId` | Can enable session hijacking or behavioral tracking. | Never log session tokens/cookies; use permitted non-sensitive IDs if needed. |
| `authorization` / `apiKey` | Authentication secrets. | Strictly avoid logging tokens/secrets. |
| `clientIp` | May be personal data depending on context. | Review policy; reduce granularity and retention. |
| `tenantId` | May reveal customer structure. | Emit only when permitted; enforce cross-tenant access controls. |
| `requestId` / `traceId` | Can link multiple operations and systems. | Use only issued identifiers; avoid embedding secrets inside IDs. |
| `httpPath` / `query` | May contain sensitive data or tokens in URLs. | Prefer route templates; strip sensitive query parameters. |

**Do not put raw request headers or entire request bodies into MDC**: frameworks may emit every MDC field across many logs, spreading sensitive data far more widely than a single controlled event.

### Protecting Against Log Injection

If `requestId` comes from an untrusted header, an attacker can send newlines or very long strings. Code must validate length/characters and have a policy to generate a new ID when invalid. A standard structured JSON encoder will escape characters in values, but that does not replace validation and size limits.

### Controlling Cardinality and Record Size

`requestId` and `traceId` typically have high cardinality—which is useful for tracing, but can drive up indexing costs. Avoid turning them into **dynamic field names** or labels on every metric. Apply deliberate indexing, retention, and sampling strategies suited to your operational tools.

## 16. Schema Governance and Cross-Service Compatibility

Field context is part of the log schema contract. For example, if all services use `requestId` today but a new service switches to `req_id` without pipeline mapping, cross-service queries will miss logs.

Establish rules for:

1. **Canonical names:** `service`, `environment`, `requestId`, `traceId`, `eventName`, and shared keys.
2. **Types and encoding:** string context; numeric fields like `durationMs` emitted as numbers if used for aggregation.
3. **Semantics:** `traceId` must be a real tracing ID; do not substitute a request ID.
4. **Presence rules:** which requests may lack `traceId`, which jobs lack `requestId`, and how `null`/absent is represented.
5. **Privacy classification:** which fields are allowed to be emitted, which must be masked, and which must never be logged.
6. **Schema ownership:** which team approves additions/renames and versioning for breaking changes.
7. **Mapping:** if multiple frameworks/standards use different field names, choose a canonical set or normalize in a controlled manner at the collector.

### Migration When Renaming a Context Key

Changing `requestId` to `request_id` is not just renaming a Java variable. Dashboards, alerts, tracing links, and historical data may depend on the old name. A sound plan may include:

- Inventorying consumers reading the old key.
- Defining the new schema and transition date/version window.
- Updating the encoder/collector first or temporarily supporting both keys if needed.
- Testing logs from both old and new versions during a rolling deploy.
- Stopping dual-write once consumers have fully migrated; avoid keeping aliases forever and inflating storage.

**Do not mix types or semantics during a rename.** If switching from `durationMs` to `durationNs`, consumers must be updated for both name and unit; do not silently change the unit while keeping the old name.

## 17. Testing Field Context in JSON Logging

A good test suite does not merely assert that `logger.info(...)` was called; it inspects **the event after the serializer/encoder**.

### Recommended Tests

| Test | What to Verify |
| --- | --- |
| JSON parsing | Each line is a valid JSON object when the pipeline uses NDJSON. |
| Required fields | `timestamp`, `level`, `service`, and `eventName` appear per contract. |
| Request scope | Two consecutive requests have distinct `requestId` values without mixing. |
| Missing trace | An event without a valid trace uses absent/`null` per schema, not a stale trace. |
| Async propagation | Logs inside executors/callbacks retain the right correlation ID after scope propagation. |
| Cleanup | Completed requests do not leak MDC/`ThreadContext` into subsequent thread-pool tasks. |
| Type | `durationMs` is a number when required by schema; context IDs remain strings. |
| Escaping | Quotes, backslashes, Vietnamese characters, newlines, and control characters do not break JSON. |
| Throwable | Error events include exception/cause per policy without accidentally dropping stack traces. |
| Privacy | Secret fields are absent; request headers/bodies are not logged automatically. |
| Multiple backends | Runtime actually uses the intended provider, layout/encoder, and field mapping. |
| Collector compatibility | Fields from app, agent, and log index do not overwrite or unexpectedly rename each other. |

### Context-Leak Test Scenario

```text
Request A -> requestId=req-A -> log A
Request A ends -> context cleared
Thread is reused
Request B -> requestId=req-B -> log B

Expected:
- Log A carries only req-A.
- Log B carries only req-B.
- No record from B carries req-A.
```

A test can run two sequential tasks on the same single-thread executor, deliberately setting and clearing context to detect leaks. Asserting only on message text is insufficient: you must parse the actual `requestId` field in the JSON output.

### Multi-Service Context Testing

Send a request with tracing context through service A → B. Verify that A and B emit the same `traceId` when part of the same trace, and that `spanId` values match the current spans. If B lacks a trace, determine whether it is a propagation bug, sampling/tracing configuration, or an uncreated span; do not assign a random `traceId` in logs to make the test pass.

## 18. Common Mistakes and How to Fix Them

| Symptom | Cause | Solution |
| --- | --- | --- |
| JSON has `message:"requestId=..."` but no `requestId` field | Only text placeholders were used. | Use MDC/`ThreadContext` or typed key–value pairs + a real JSON encoder. |
| `requestId` is empty in async tasks | Context was not propagated from the submitting thread. | Propagate snapshot/scope through the executor or use official instrumentation. |
| Request B logs carry Request A's `requestId` | MDC was not cleared/restored on a pooled thread. | Clean up in `finally` and test thread reuse. |
| `traceId` equals `requestId` but no trace is found | Copied or fabricated a fake trace ID. | Obtain `traceId`/`spanId` from the active tracer. |
| User/token info appears in every log | Too much data attached to MDC. | Allowlist keys, exclude secrets, and limit scope. |
| `durationMs` emitted as a string | Number stored as an MDC `String` or coerced by encoder. | Emit typed per-event fields or use verified type mapping. |
| Two services use `requestId` vs. `request_id` | No shared schema. | Agree on canonical names and apply migration/collector mapping. |
| Keys like `user_123` or `req_17` are used | Dynamic data placed into field names. | Keep keys fixed; put values inside the field. |
| Context configured in Logback, but runtime picks Log4j2 | A different backend is active; config is not loaded. | Verify the active provider/bridge and actual configuration. |
| JSON parse error when context contains quotes | Assembling JSON via text patterns without escaping. | Use a proven JSON encoder/layout. |
| JSON has both `context.requestId` and a `context` object | Two representations or collector mappings conflict. | Choose one schema and normalize intentionally. |
| Few logs, yet high storage/index costs | Indexing every high-cardinality field or too many keys. | Review index mappings, retention, and sampling. |
| Async appender still misses `requestId` in child tasks | Confusing async logging with application context propagation. | Propagate scope before the task emits logs. |
| Error event lacks stack trace despite having context | Logged error text only without attaching `Throwable`. | Use the exception logging API and check encoder/collector. |
| Context missing in background jobs | Code assumed only HTTP requests have context. | Define `jobId`/`workflowId` and bootstrap context per job. |

## 19. Production Review Checklist for Field Context

- [ ] Which context fields are truly needed: resource, request, tracing, operation?
- [ ] Are key names, JSON types, semantics, and presence conditions documented in the schema?
- [ ] Have you avoided confusing `requestId`, `traceId`, `spanId`, and `correlationId`?
- [ ] Are ID values validated, length-bounded, and sourced from the right origin?
- [ ] Is resource metadata (`service`, `environment`, `instance`) attached centrally from a single source of truth?
- [ ] Does MDC/`ThreadContext` have a clear scope and get cleared/restored even when exceptions occur?
- [ ] Do executors, callbacks, reactive chains, and virtual threads propagate context properly?
- [ ] Have per-event fields like `durationMs`, `errorCode`, and `attempt` been kept out of request scope?
- [ ] Does the JSON encoder actually emit context as fields rather than concatenating into `message`?
- [ ] Does the pipeline use flat or nested layout, and how are dotted field names handled?
- [ ] Are passwords, tokens, session cookies, sensitive headers, and unnecessary personal payloads excluded?
- [ ] Does the collector/index parse JSON, preserve the schema, map types, and control cardinality?
- [ ] Have tests verified that two requests on the same thread pool do not mix context?
- [ ] Do error events include `Throwable`/cause and useful context without duplicate logging across layers?
- [ ] When renaming keys, is there a migration plan so dashboards and alerts do not break?

## 20. Self-Check Questions

1. Why might a `requestId` inside the text `message` not count as a JSON context field?
2. How do `service`, `requestId`, and `orderId` belong to different lifecycles?
3. When a request passes through `CompletableFuture`, why might MDC on the caller thread not appear in the child task?
4. Why must context be cleared or restored when a thread pool is reused?
5. How does `traceId` differ from `requestId`, and where should a trace ID come from?
6. How does choosing flat fields vs. a nested `context` object affect queries and collectors?
7. Why should `durationMs` be a number rather than a string from MDC?
8. When is `orderId` better suited to per-event fields than request-wide MDC?
9. Why should tokens or entire request bodies never be placed in context?
10. In the JUL demo, what advantage does passing an immutable `Context` in `LogRecord` have over using a static mutable map?
11. Does `AsyncAppender` automatically perform context propagation for Java executors?
12. Why can a single service renaming `requestId` to `req_id` break dashboards even though the JSON remains valid?

**Conclusion:** **Field context turns each JSON record into part of a correlatable operational picture.** To make context useful, establish its **origin and lifecycle**, keep **names, types, and semantics stable**, propagate context across synchronous and asynchronous boundaries, clean up after each scope, **emit only permitted fields**, and test data **after the encoder/collector**. Context explains *which request, trace, and service an event belongs to*; it does not replace event fields, exception details, or logging pipeline durability guarantees.
