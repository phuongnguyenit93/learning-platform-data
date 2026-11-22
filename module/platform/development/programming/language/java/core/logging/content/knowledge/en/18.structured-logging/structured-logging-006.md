# Standard Event Codes in Java Structured Logging

## 1. What is a Standard Event Code?

A **standard event code** is a **stable, governed, and predefined identifier with an agreed meaning** for a type of event that an application logs. Its goal is to allow both humans and processing systems to recognize **what happened** without depending on the exact wording of the message, display language, thread name, or source code path.

Example of an event group for a checkout flow:

| eventCode | eventName | Meaning |
| --- | --- | --- |
| `ORD-1001` | `order.checkout.started` | Checkout processing started |
| `ORD-1002` | `order.checkout.succeeded` | Checkout completed successfully |
| `ORD-1500` | `order.checkout.failed` | Checkout failed and could not be completed |
| `PAY-2001` | `payment.authorization.declined` | Payment processor declined authorization |
| `INF-9001` | `infrastructure.dependency.unavailable` | A required dependency is unavailable |

The values above are **illustrative conventions defined by a project**, not a mandatory code catalog from the JDK, SLF4J, Logback, Log4j2, or OpenTelemetry.

A text-based log might look like:

~~~text
ERROR eventCode=ORD-1500 eventName=order.checkout.failed requestId=req-17 orderId=O-42 outcome=failed
~~~

A **truly structured** log might look like:

~~~json
{
  "timestamp": "2026-11-09T10:15:00Z",
  "level": "ERROR",
  "service": "order-service",
  "eventCode": "ORD-1500",
  "eventName": "order.checkout.failed",
  "message": "Cannot complete checkout",
  "requestId": "req-17",
  "orderId": "O-42",
  "outcome": "failed",
  "errorType": "InventoryUnavailableException"
}
~~~

These are **two illustrative records**, not the default output produced by every logging framework. In JSON, `eventCode` and `eventName` are queryable fields; in plain text, they remain just part of the message unless the pipeline parses them into fields.

**Core principle:** a code belongs to the **event type**, whereas the ID of a request, order, user, or exception belongs to a **specific occurrence**. Do not generate dynamic codes like `ORD-1500-O-42`; keep `ORD-1500` fixed and store `orderId=O-42` in a separate field.

## 2. Why Does a System Need Standard Event Codes?

Compare two styles of error logs:

~~~text
Without code:
ERROR Checkout could not be completed
ERROR Checkout failed
ERROR Không thể hoàn tất thanh toán đơn hàng

With code:
ERROR eventCode=ORD-1500 message="Checkout could not be completed"
ERROR eventCode=ORD-1500 message="Checkout failed"
ERROR eventCode=ORD-1500 message="Không thể hoàn tất thanh toán đơn hàng"
~~~

The three messages may differ due to version, translation, or wording, but if they genuinely represent **the same failure type**, the system can still group them by `ORD-1500`.

Concrete benefits:

1. **Consistent search:** query by `eventCode` instead of regex-matching a message string that might change.
2. **More accurate alerting:** track the occurrence rate of critical error codes over a time window and per service.
3. **Stable dashboards:** count successful/failed checkouts by event type rather than keyword matching.
4. **Incident response support:** a code links directly to a runbook, owner, common root causes, and recommended actions.
5. **Cross-version analysis:** messages can be improved while code-based queries continue to work.
6. **Cross-team integration:** services, collectors, and support systems share a common catalog defining event types.
7. **Reduced grouping-key cardinality:** a managed `eventCode` catalog is typically much smaller and more stable than request IDs, dynamic paths, or exception messages.

**Not every log line needs a code.** Short-lived DEBUG logs used for temporary investigation may not need a long-term event contract. Prioritize defining codes for **operational milestones, state transitions, significant outcomes, actionable failures, or integration events** that have clear search or reporting value.

## 3. Distinguishing `eventCode` from Commonly Confused Fields

| Field | Question it answers | How does it typically change? |
| --- | --- | --- |
| `eventCode` | **Which event type** is this according to the system catalog? | Stable for the same type; never embeds dynamic IDs |
| `eventName` | Human-readable semantic name of the event type? | Stable per contract, e.g. `order.checkout.failed` |
| `level` / `severity` | How severe is the event in this context? | May change based on policy or impact |
| `message` | Human-language description for this occurrence? | Wording, language, and context may vary |
| `errorCode` | Business/API error code returned to the caller? | May match or differ from `eventCode`; requires explicit mapping |
| `requestId` | Which request does this event belong to? | Varies per request; very high cardinality |
| `traceId` / `spanId` | Which trace/span is this event associated with? | Varies per execution |
| `orderId` / `jobId` | Business entity of the event? | Varies per order/job |
| `exception.type` | What kind of technical exception occurred? | Depends on the failure and the layer where it originated |
| `schemaVersion` | Which version of the log structure contract is used? | Changes when the schema evolves intentionally |

### 3.1. An Event Code Is Not a Log Level

An `ORD-1500` event is normally logged at ERROR when checkout actually fails. However, in a flow where an error is recovered via retry, a team might log a different technical event at WARN, and then log `ORD-1002` when checkout succeeds. Do not bake severity into the code and assume one log level is always right in every situation.

The code states **what** happened; the level states the **impact / observation priority** of that occurrence. If an event can have multiple levels depending on the situation, the catalog must specify the exact rules—or split it into separate event types if the meanings truly differ.

### 3.2. An Event Code Is Not an HTTP Response Status

A checkout request may return HTTP 503, but `ORD-1500` does not automatically mean HTTP 503. An internal system event code can relate to multiple APIs or statuses, or multiple event codes can lead to the same HTTP status.

Example:

~~~text
Internal log:
  eventCode=ORD-1500, outcome=failed, dependency=inventory

Public HTTP response:
  status=503, errorCode=ORDER_TEMPORARILY_UNAVAILABLE, requestId=req-17
~~~

The mapping between `eventCode` and `errorCode` must be explicitly defined; **do not expose stack traces, internal infrastructure codes, or sensitive details in public responses** just so users see the same identifier.

### 3.3. An Event Code Does Not Replace Context

Logging `eventCode=ORD-1500` alone is not enough to find which request failed. A useful record also needs `requestId`, service, operation, outcome, and other permitted fields. Conversely, having only `requestId` without `eventCode` makes it very hard to aggregate by event type.

## 4. Designing a Naming Convention

An easy-to-manage internal convention:

~~~text
<DOMAIN>-<NUMBER>

ORD-1001
ORD-1002
ORD-1500
PAY-2001
INF-9001
~~~

This is **a design choice**, not a mandatory industry standard. You can choose purely numeric codes, mnemonic strings, or system-managed UUIDs; in this learning material, we use a domain prefix and a four-digit number for readability in logs.

### Recommended Rules

1. **Stable:** as long as the event type's meaning does not change, the code does not change even if the message or class name changes.
2. **Unique within the catalog:** never reuse the same code for two events with different meanings.
3. **Free of per-occurrence data:** never embed `userId`, email, `orderId`, timestamps, or request parameters into the code.
4. **Paired with a semantic name:** a short code like `ORD-1500` can be paired with `eventName=order.checkout.failed` so readers understand it immediately.
5. **Defined ownership:** each code group has a person or team responsible for defining, reviewing, and maintaining it.
6. **Decoupled from source code lines:** refactoring should not break dashboards or alerts.
7. **Clear event boundaries:** specify when the code is emitted; if "checkout failed" means final failure, do not emit it on every transient retry.
8. **Security guidance:** document which fields are required, which fields may contain sensitive data, allowed log levels, and retention periods.
9. **Deprecation policy:** deprecated codes must never be silently reassigned to a new meaning.
10. **Compatibility rules:** keep the same code for the same meaning; introduce a new code or a new `schemaVersion` when the meaning or data contract changes incompatibly.

An illustrative format check:

~~~regex
^(ORD|PAY|INF)-[0-9]{4}$
~~~

A regex only validates **syntax**; it does not guarantee that a code is registered or semantically valid. A registry/enum and CI tests should enforce code uniqueness, valid naming, and complete descriptions.

### 4.1. Should You Use Self-Describing Codes or Numeric Codes?

- **Prefixed numeric codes:** compact, easy to process, stable, e.g. `ORD-1500`. Downside: requires looking up a registry to know the meaning.
- **Semantic names:** easy to read, e.g. `order.checkout.failed`. If used as the sole primary key, renaming one to "sound nicer" becomes a breaking change.
- **Using both:** an immutable code for machines and a clear semantic name for humans; ensure both reference the exact same definition in the registry.

No Java rule requires using both. What matters is **a contract that both the application and the collector understand and test**.

## 5. The Event Catalog as the Source of Truth

Do not let every developer invent codes by concatenating strings at the logging call site. Maintain an **event catalog** versioned alongside the product or in a shared registry.

Example:

| eventCode | eventName | When to emit | Default level | Required fields | Owner |
| --- | --- | --- | --- | --- | --- |
| `ORD-1001` | `order.checkout.started` | When checkout officially starts | INFO | `requestId`, `orderId` | Order |
| `ORD-1002` | `order.checkout.succeeded` | When checkout completes successfully | INFO | `requestId`, `orderId`, `durationMs` | Order |
| `ORD-1500` | `order.checkout.failed` | When checkout ends in failure | ERROR | `requestId`, `orderId`, `error.type` | Order |
| `PAY-2001` | `payment.authorization.declined` | When a declined decision is received from the processor | WARN or INFO by impact | `requestId`, safe `paymentAttemptId` | Payments |
| `INF-9001` | `infrastructure.dependency.unavailable` | When a required dependency is unavailable | ERROR | `dependency`, `requestId` if available | Platform |

**The catalog above is for practice only.** Before adopting it in a real system, designers must clearly specify triggers, semantics, data fields, deduplication rules, retry logging behavior, and runbooks.

A complete registry entry might include:

~~~yaml
eventCode: ORD-1500
eventName: order.checkout.failed
description: Checkout ended in failure after all retry/fallback policies were applied.
owner: order-platform
defaultLevel: ERROR
requiredAttributes:
  - requestId
  - orderId
  - outcome
  - error.type
optionalAttributes:
  - durationMs
  - dependency
  - traceId
outcome: failed
piiPolicy: Log only permitted internal identifiers; do not log tokens or payment payloads.
runbook: docs/runbooks/order-checkout-failure.md
status: active
~~~

This is an **illustrative YAML schema**, not a mandatory deployment file. The `runbook` field is an example path in a hypothetical repository and does not imply that such a file exists. If your organization has its own catalog system, use your organization's actual registry format.

### Why Does the Registry Need "When to Emit"?

Suppose checkout attempts to call inventory three times: the first two time out and the third succeeds. If the code emits `ORD-1500` on **every retry**, dashboards might count three final failures even though the request succeeded. You can use a separate event like `inventory.read.retry_scheduled` for a transient attempt and emit `ORD-1500` only when the entire checkout genuinely fails.

Agreeing on **event semantics** matters more than making the code look pretty. A stable code emitted at the wrong moment will skew monitoring metrics.

## 6. Structured Log Schema and Field Rules

An event typically has the following group of fields:

| Field | Suggested type | Rules |
| --- | --- | --- |
| `timestamp` | ISO-8601 UTC string / native timestamp | Time the event occurred, explicit timezone |
| `level` | enum/string | Matches the chosen logging framework or ingest standard |
| `service` | string | Stable service name |
| `eventCode` | string | Value from the catalog, low cardinality |
| `eventName` | string | Registered event type name |
| `message` | string | Human-readable description, may evolve |
| `requestId` | string | Safe ID for request correlation |
| `traceId` / `spanId` | string | When tracing is configured |
| `operation` | string | Operation name from a controlled set of values |
| `outcome` | string | `started`, `succeeded`, `failed`, or another convention |
| `durationMs` | number | Unit is milliseconds; do not append `"ms"` to the number |
| `error.type` | string | Error type when a failure occurs |
| `error.message` / `stack_trace` | string | Only when needed and in accordance with secret-handling policy |
| `schemaVersion` | integer/string | Version of the structural contract |

Example JSON log with separate fields:

~~~json
{
  "timestamp": "2026-11-09T10:15:00Z",
  "level": "INFO",
  "service": "order-service",
  "eventCode": "ORD-1002",
  "eventName": "order.checkout.succeeded",
  "message": "Checkout completed",
  "requestId": "req-17",
  "traceId": "5dbf59d442a240a18cc82d48c2eb7e44",
  "operation": "checkout",
  "orderId": "O-42",
  "outcome": "succeeded",
  "durationMs": 42,
  "schemaVersion": 1
}
~~~

This record illustrates the **target format**, not the default output of `Logger.info(...)`. If a layout only produces plain text containing `eventCode=...`, the pipeline needs a parser to turn it into fields. For true structured logging, prefer an encoder that outputs JSON/NDJSON or a structured format supported by your collection system.

### 6.1. Separating Schema Version from Event Code

A new `region` field added as optional can keep the same `eventCode` if the event type has not changed. Changing a field from numeric `durationMs` to a string `"42ms"` can break consumers; use schema evolution rules, versioning, or a new field to avoid breaking changes.

Do not create a code like `ORD-1500-v2` just because a display field was renamed, unless the organization decides it is a new event type with a different meaning.

### 6.2. Field Names Must Be Consistent

`eventCode`, `event.code`, and `event_code` are not automatically treated as the same field. Pick one convention and apply it consistently across services, indexers, dashboards, and alerts. If the collector requires a different mapping, define the transformation layer explicitly; do not let each service invent its own field names.

The examples in this lesson use `eventCode`/`eventName` in illustrative JSON. Projects following external standards may choose different names once the mapping is defined.

## 7. Standalone Java 17: Enum Catalog and JSON Lines with `eventCode`

The JDK includes `java.util.logging` (JUL), but JUL **does not provide a built-in event code standard**. We can define a catalog using an `enum` and write a `Formatter` that outputs JSON Lines to demonstrate how a record carries code, name, outcome, correlation ID, and error type.

This example uses only JDK 17; **no Maven or external libraries are required**. The custom formatter is primarily for learning the mechanics; production systems should use a proven structured encoder/backend to handle timestamps, full exceptions, Unicode, throughput, and sensitive data.

Create the file **StandardEventCodeDemo.java**:

~~~java
import java.io.IOException;
import java.util.logging.Formatter;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;
import java.util.logging.StreamHandler;

public final class StandardEventCodeDemo {
    private static final Logger LOG =
            Logger.getLogger(StandardEventCodeDemo.class.getName());

    private StandardEventCodeDemo() {
    }

    private enum EventCode {
        CHECKOUT_STARTED(
                "ORD-1001", "order.checkout.started",
                "Checkout started", Level.INFO),
        CHECKOUT_SUCCEEDED(
                "ORD-1002", "order.checkout.succeeded",
                "Checkout succeeded", Level.INFO),
        CHECKOUT_FAILED(
                "ORD-1500", "order.checkout.failed",
                "Checkout failed", Level.SEVERE);

        final String code;
        final String name;
        final String message;
        final Level level;

        EventCode(String code, String name, String message, Level level) {
            this.code = code;
            this.name = name;
            this.message = message;
            this.level = level;
        }
    }

    private static String jsonString(String value) {
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
                        out.append("\\u");
                        for (int n = hex.length(); n < 4; n++) {
                            out.append('0');
                        }
                        out.append(hex);
                    } else {
                        out.append(c);
                    }
                }
            }
        }
        return out.append('"').toString();
    }

    private static final class EventJsonFormatter extends Formatter {
        @Override
        public String format(LogRecord record) {
            Object[] p = record.getParameters();
            EventCode event = (EventCode) p[0];
            String requestId = (String) p[1];
            String orderId = (String) p[2];
            String outcome = (String) p[3];

            StringBuilder out = new StringBuilder("{\"level\":");
            out.append(jsonString(record.getLevel().getName()));
            out.append(",\"eventCode\":").append(jsonString(event.code));
            out.append(",\"eventName\":").append(jsonString(event.name));
            out.append(",\"message\":").append(jsonString(record.getMessage()));
            out.append(",\"requestId\":").append(jsonString(requestId));
            out.append(",\"orderId\":").append(jsonString(orderId));
            out.append(",\"outcome\":").append(jsonString(outcome));

            if (record.getThrown() != null) {
                out.append(",\"errorType\":")
                   .append(jsonString(
                           record.getThrown().getClass().getSimpleName()));
            }
            return out.append("}\n").toString();
        }
    }

    private static void configureLogger() {
        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.ALL);

        Handler handler = new StreamHandler(
                System.out, new EventJsonFormatter()) {
            @Override
            public synchronized void publish(LogRecord record) {
                super.publish(record);
                flush();
            }
        };
        handler.setLevel(Level.ALL);
        LOG.addHandler(handler);
    }

    private static void emit(
            EventCode event, String requestId,
            String orderId, String outcome, Throwable cause) {
        LogRecord record = new LogRecord(event.level, event.message);
        record.setLoggerName(LOG.getName());
        record.setParameters(
                new Object[] {event, requestId, orderId, outcome});
        record.setThrown(cause);
        LOG.log(record);
    }

    public static void main(String[] args) {
        configureLogger();

        emit(EventCode.CHECKOUT_STARTED,
                "req-17", "O-42", "started", null);

        emit(EventCode.CHECKOUT_SUCCEEDED,
                "req-17", "O-42", "succeeded", null);

        emit(EventCode.CHECKOUT_FAILED,
                "req-18", "O-43", "failed",
                new IOException("store timeout"));
    }
}
~~~

### 7.1. Compile and Run

In the directory containing the file above:

~~~bash
javac -encoding UTF-8 StandardEventCodeDemo.java
java StandardEventCodeDemo
~~~

**Exact stdout from the example's formatter:**

~~~json
{"level":"INFO","eventCode":"ORD-1001","eventName":"order.checkout.started","message":"Checkout started","requestId":"req-17","orderId":"O-42","outcome":"started"}
{"level":"INFO","eventCode":"ORD-1002","eventName":"order.checkout.succeeded","message":"Checkout succeeded","requestId":"req-17","orderId":"O-42","outcome":"succeeded"}
{"level":"SEVERE","eventCode":"ORD-1500","eventName":"order.checkout.failed","message":"Checkout failed","requestId":"req-18","orderId":"O-43","outcome":"failed","errorType":"IOException"}
~~~

These are **three separate JSON objects, one per line** (NDJSON/JSON Lines), not a single JSON array containing three elements. `SEVERE` is JUL's severity level name; a Logback/Log4j2 system may call the corresponding level `ERROR`. Do not equate level names across backends without defining a mapping.

Why is the output predictable?

1. `EventCode` is an `enum`: three fixed codes, three fixed names, and three fixed messages—never constructed from dynamic IDs.
2. `emit(...)` creates a `LogRecord` containing the event's message, level, parameters, and an optional `Throwable`.
3. `EventJsonFormatter` reads `EventCode` from `record.getParameters()` and emits JSON keys in a fixed order.
4. The logger disables parent handlers and attaches a single `StreamHandler` writing to stdout; the handler calls `flush()` after each event.
5. Timestamps are omitted in the example to keep expected stdout deterministic; production logs should include timestamps, logger/service, tracing context, and additional diagnostic fields.
6. The failure event carries a real `IOException` in `record.getThrown()`, but the illustrative formatter only prints `errorType`, **not the stack trace or cause**. Production setups need a layout/encoder that preserves and protects error details appropriately.

**Practical limitation:** `jsonString(...)` is a minimal helper for valid input strings in this demo; it does not replace a production JSON library that handles all invalid Unicode/surrogate cases, number/boolean formatting, and schema validation. Do not write a large custom serializer just for application logging when the backend provides a standard encoder.

### 7.2. Why Store `eventCode` in an `enum`?

Compare this to:

~~~java
// Poor code governance: each place dynamically concatenates its own code.
LOG.info("eventCode=ORD-" + orderId + " checkout failed");
~~~

`enum EventCode` centralizes code declarations, binds `code` to `name`, `message`, and default level, reduces typos, and prevents different call sites from reusing the same name with different meanings.

In systems with multiple modules or services, the catalog can be packaged as a shared library, a registry file, or generated code. However, **do not force every service to redeploy a shared library just to change a message string**; versioning and backward compatibility need a clear strategy.

## 8. SLF4J 2.x: Passing `eventCode` via Key/Value

In a project using **SLF4J 2.x** and a compatible logging provider/backend, the fluent API provides `addKeyValue(...)`:

~~~java
// Snippet in a service with SLF4J Logger LOG and corresponding variables.
LOG.atInfo()
   .addKeyValue("eventCode", "ORD-1002")
   .addKeyValue("eventName", "order.checkout.succeeded")
   .addKeyValue("requestId", requestId)
   .addKeyValue("orderId", orderId)
   .addKeyValue("outcome", "succeeded")
   .log("Checkout succeeded");
~~~

This approach is better than stuffing all metadata into a single string `"eventCode=... orderId=..."`, because the event builder passes key/value pairs at the API layer.

**However, `addKeyValue(...)` does not produce JSON by itself.** The provider and encoder/layout must actually emit those fields to the destination and preserve their types. If the configuration only prints `%msg`, key/value fields may not appear at all. Backends vary in structured logging and JSON encoder capabilities; verify the actual output and supported versions.

A failure example:

~~~java
// Example snippet inside a catch block with Throwable e.
LOG.atError()
   .addKeyValue("eventCode", "ORD-1500")
   .addKeyValue("eventName", "order.checkout.failed")
   .addKeyValue("requestId", requestId)
   .setCause(e)
   .log("Checkout failed");
~~~

`setCause(e)` attaches the `Throwable` so the backend can print the stack trace/cause. Do not replace it with only `e.getMessage()` when full error diagnostics are needed. When retries or fallbacks are involved, choose the event type that matches the **final outcome** of the operation rather than emitting the final failure code on every attempt.

A useful coding rule: extract event codes into an enum/constants or generate them from a registry; **do not copy string literals** across hundreds of call sites without duplicate/typo checks. The two snippets above use string literals directly to illustrate the API, but production code should tie them to the catalog.

## 9. Logback and Log4j2: How to Preserve Fields as Structured Data?

### 9.1. Logback

Logback Classic is commonly used as the SLF4J backend. It provides encoders/layouts and extensions for JSON output; preserving key/value pairs from SLF4J 2.x depends on the version and encoder used.

In a text-based configuration, you can include the event code in a readable structured-text message:

~~~text
INFO eventCode=ORD-1002 eventName=order.checkout.succeeded orderId=O-42 outcome=succeeded
~~~

However, **JSON-like text is not JSON**. If you need accurate queries by `eventCode`, use an encoder that supports structured data or a reliable parser in your collector. Do not claim Logback automatically produces `eventCode` just because `LOG.info(...)` was called.

If you use MDC to inject a code into a pattern such as `%X{eventCode}`, manage its scope carefully. **MDC is thread-bound context**, whereas `eventCode` is an attribute of a single event; putting a code into MDC and forgetting to clear it can leak the previous event's code onto subsequent events. With SLF4J 2.x, attaching key/value pairs directly to the event is usually cleaner for `eventCode`.

### 9.2. Log4j2

Log4j2 supports structured layouts, including **JSON Template Layout**, which lets you define a schema and field mappings. This is a capability of the backend/encoder, not an automatic property of `eventCode`.

A snippet illustrating code emission using the Log4j API:

~~~java
// Example snippet in a class with Log4j2 Logger LOG, requestId, and orderId.
LOG.info("eventCode={} eventName={} requestId={} orderId={}",
        "ORD-1002", "order.checkout.succeeded",
        requestId, orderId);
~~~

This is a **parameterized text message**; it does not automatically create an `eventCode` field in JSON output. To emit structured fields, use an appropriate message/context API and configure JSON Template Layout with the right resolvers/templates; exact capabilities depend on the libraries/modules and release version.

You can use a `JsonTemplateLayout` template to produce fields following a shared convention, but verify that:

- Every service emits valid `eventCode` values.
- The encoder actually outputs `eventCode`/`eventName` as independent fields.
- The collector does not rename fields or infer the wrong data types.
- `Throwable`, `traceId`, and `timestamp` are encoded properly.
- Field ordering is not relied upon as a business contract; JSON objects do not guarantee meaningful key order.

**Do not copy a Logback layout example directly into Log4j2** and expect class names or placeholders to be compatible. Their APIs, dependencies, and layout configuration syntax differ.

## 10. Integrating with OpenTelemetry Event Semantics

OpenTelemetry defines an **event** as a named occurrence at a specific point in time, accompanied by attributes. Its semantic conventions emphasize **stable event names that do not contain dynamic data**. In this internal design, `eventName=order.checkout.failed` represents the event type, while `requestId` and `orderId` are attributes of the occurrence.

Keep these distinctions in mind:

- `eventCode` in this lesson is an **internal code** defined by the organization. Never claim that OpenTelemetry or SLF4J mandates an `eventCode` field.
- `eventName` can map to the event-naming mechanism of an SDK, tracing, or logging system, but check the exact data model and mapping used by that system.
- An **event** describes a checkpoint or state change; a **span** is appropriate when measuring an operation with duration and boundaries. Not every log line is an official OpenTelemetry event.
- `traceId` and `spanId` are only meaningful when tracing and context propagation are actually active; generating a random string does not create a valid distributed trace.

OpenTelemetry semantic conventions can evolve across versions. For production integration, consult the current documentation and normalize field names in the collector rather than conflating internal names with mandatory external standard names.

## 11. Using Event Codes for Search, Measurement, and Alerting

### 11.1. Querying by Code

Assuming the collector stores JSON with an `eventCode` field, a **pseudocode** query looks like:

~~~text
WHERE service = "order-service"
  AND eventCode = "ORD-1500"
  AND timestamp >= now() - 15 minutes
GROUP BY environment, errorType
~~~

This is not universal syntax across all log analytics products. Each backend has its own query language, field indexing, and time functions. The key advantage is that the same code can be grouped even when messages change.

### 11.2. Alerts Should Consider Frequency and Impact

Do not set up paging alerts just because a single `PAY-2001` event appears if it could be a normal declined payment. Define clear signals:

- The rate of `ORD-1500` events per minute exceeds a threshold.
- The ratio of `ORD-1500` to total completed checkouts increases, rather than relying only on absolute counts when traffic fluctuates.
- `INF-9001` repeatedly exceeds a threshold and impacts many requests.
- A critical code **fails to appear** when expected (e.g., missing completion events), while accounting for the effects of sampling and log filtering.

**Important:** if logs can be dropped in async queues, sampled, or lost in transit to the collector, log counts are not exact transaction counts. For SLOs or business metrics, combine metrics/traces with reliable data sources. Event codes improve query precision, but they do not guarantee delivery.

### 11.3. Cardinality Must Be Controlled

`eventCode` should be a field with a finite, governed set of values suitable for grouping. In contrast, `requestId`, `orderId`, `exceptionMessage`, or dynamic URL paths have high cardinality; never put them directly into **`eventCode`**, and do not turn them into metric labels by default if doing so causes time-series explosion.

A fixed enum of a few hundred event codes is very different from generating a code per user ID. Defining overly granular codes per parameter value can bloat the catalog and make dashboards hard to use.

## 12. Governance and Evolution of the Event Catalog

### Registering a New Event

1. **Define the purpose:** is the event for debugging, auditing, alerting, or measuring a business journey?
2. **Check the catalog:** is there already a code representing the same semantics? Do not create two codes just because two teams prefer different names.
3. **Pick a domain and unused code:** e.g., `ORD-1501`; never reuse an old code.
4. **Assign a semantic name:** e.g., `order.checkout.rejected_by_policy`; do not include dynamic IDs.
5. **Document the trigger clearly:** when is it emitted—before/after commit, before/after retries, once or per attempt?
6. **Define fields:** data types, required/optional status, units, size limits, and security policies.
7. **Choose the default level:** based on impact, not just because the name contains the word "error".
8. **Attach owner and runbook:** who responds when the code spikes, and how to verify/recover.
9. **Add tests:** unique codes, valid pattern, schema, JSON mapping, and emission at the right stage.
10. **Update dashboards/alerts with control:** ensure the new code is indexed and on-call engineers have the context they need.

### Changing an Existing Code

- **Changing message/display formatting:** usually safe to keep the same code if the event meaning has not changed.
- **Adding an optional field:** usually compatible if consumers ignore unknown fields.
- **Changing a required field, type, or meaning:** evaluate `schemaVersion`, migration, and consumers.
- **Changing event semantics:** create a new code; deprecate the old code with a clear timeline and policy.
- **Merging or splitting events:** update the catalog and existing queries using the old code; avoid silent breaks.
- **Retiring a code:** mark it deprecated/retired; never reassign it to a new event.

Changing an **existing event code** can be a breaking change for dashboards, alerts, data pipelines, and runbooks. Review it as carefully as changing a public API or data contract.

## 13. Security and Privacy

Event codes must not contain secrets, yet an event has **many other fields** that could carry sensitive information. Rules:

1. Never put passwords, access tokens, cookies, API keys, or payment payloads into `message` or `attributes`.
2. Never use email addresses, phone numbers, card numbers, or usernames as part of `eventCode`. Use safe internal IDs for correlation in accordance with data policy.
3. Avoid logging full request/response bodies or large Java objects; select only the fields needed for investigation.
4. Use a JSON encoder that properly escapes newlines and control characters to prevent log forging.
5. For `Throwable`, preserve the cause when needed for diagnostics, but restrict exposing stack traces, endpoints, SQL, or private paths in public responses.
6. Enforce access controls, retention, and data protection across console, files, archives, collectors, and backups.
7. Define an allowlist of loggable fields for each code; do not let an open schema automatically serialize every property of an object.

A properly coded `ORD-1500` event can still be a dangerous log if `message` contains a session token. **Standard codes help with identification; they do not perform masking or redaction automatically.**

## 14. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Concatenating `orderId`/`requestId` into the code | Every event produces a new code; grouping breaks | Put dynamic IDs in separate fields |
| Using `message` as the alert key | Rewording breaks alert rules | Group by stable `eventCode`/`eventName` |
| Copy-pasting literal codes everywhere | Typos and duplicate meanings | Use a catalog, enum/constants, and CI |
| Logging `ORD-1500` on every retry | Dashboards miscount final failures | Define triggers clearly and use separate attempt events |
| Changing meaning while keeping the code | Existing consumers misinterpret data | Create a new code and version/migrate |
| Reusing a deprecated code | Historical and new logs get mixed together | Never reuse codes |
| Confusing `eventCode` with HTTP `errorCode` | Exposes internal data or breaks mappings | Separate API and log contracts; define an explicit mapping |
| Only adding `eventCode=...` to plain text | Collector lacks structured fields | Use a structured encoder/schema or a tested parser |
| Calling `LOG.atInfo().addKeyValue(...)` without `log(...)` | Event is never emitted | End the fluent chain with `log()` |
| Formatter drops `Throwable` | Stack trace/cause lost in output | Use an encoder supporting error attributes per policy |
| Missing `requestId`/`traceId` | Cannot correlate events to a request | Add safe correlation fields and propagate context |
| Using code as a metric label with dynamic IDs attached | Cardinality explosion | Use a fixed, registered set of codes |
| Logging the same event at multiple layers | Duplicate counts and noise | Define clear event emission boundaries |
| Putting `eventCode` into MDC without clearing it | Subsequent events carry the stale code | Attach fields per event or clear scope in `finally` |
| Forgetting `schemaVersion` on breaking changes | Parsers/dashboards fail or drop fields | Manage schema evolution and migrations |

## 15. Checklist for Reviewing an Event Code System

Before going to production, verify:

- **Catalog:** every code has a single meaning, no duplicates, no dynamic data, and clear owner and trigger.
- **Naming:** `eventName` is readable and consistent across domains and actions/state transitions.
- **Schema:** `eventCode`, `eventName`, `level`, `timestamp`, `service`, `outcome`, and required fields have the right types.
- **Emission:** codes are emitted at the right time, not mislogged on transient retries or emitted twice for the same outcome.
- **Error handling:** `Throwable` is preserved per policy; API responses do not leak internal data.
- **Structured encoder:** the collector genuinely receives `eventCode` as a field, not an unparsed string.
- **Correlation:** `requestId`/`traceId` propagate properly across threads/async boundaries and are cleaned up afterward.
- **Privacy:** no unnecessary secrets or PII; data is escaped and governed by retention policies.
- **Monitoring:** dashboards/alerts query by code while accounting for sampling/drop limits.
- **Backward compatibility:** tests cover codes, required fields, deprecation, and version changes.
- **Performance:** measure log events/s, bytes/s, allocations/GC, and latency under realistic workloads.
- **Runbook:** codes link to remediation guides; when an alert fires, on-call staff know the next action.

## 16. Practice Exercises

1. **Distinguish:** given `ORD-1500`, `order.checkout.failed`, `ERROR`, `requestId=req-17`, and `HTTP 503`, identify which is `eventCode`, `eventName`, severity, correlation ID, and API status.
2. **Design a catalog:** create at least four codes for a data-import job lifecycle: started, major progress checkpoint, succeeded, and failed. Each code must define a trigger and required fields.
3. **Run on JDK 17:** create `StandardEventCodeDemo.java`; compare the three NDJSON lines against the expected stdout. Why does `ORD-1500` not contain `O-43`?
4. **Add an event:** add an enum constant `CHECKOUT_CANCELLED` with a new code, distinct name, and appropriate outcome. Verify it does not duplicate any code or alter an existing code's meaning.
5. **SLF4J 2.x:** convert a text log `"Checkout succeeded"` to the fluent API with `eventCode`, `eventName`, `requestId`, and `outcome`. Explain why the backend/encoder must still support key/value pairs.
6. **Schema testing:** write assertions checking that `eventCode` matches the pattern, `durationMs` is a number, and `requestId` is non-empty. Verify consumer behavior when a new optional field appears.
7. **Retry:** a checkout times out twice and succeeds on the third attempt. Should `ORD-1500` be emitted if it is defined as final failure?
8. **Dashboard:** compute the checkout failure rate from final-outcome events; explain what goes wrong if both retries and final failures are counted together.
9. **Cardinality:** if an `eventCode` is built by concatenating a code with one million `requestId` values, how many keys will a `GROUP BY eventCode` produce? Why is this unsuitable for alerting?
10. **Security:** a log has a standard `eventCode`, but its `message` contains a token. Propose changes at the emission site, encoder, and access-control layer to reduce risk.
11. **Versioning:** a team changes `durationMs` to a string `duration`. Describe a migration path that avoids breaking dashboards and how to preserve `eventCode` if the event meaning is unchanged.

## 17. References

- SLF4J Manual — Fluent Logging API: https://slf4j.org/manual.html
- Apache Log4j 2 — Layouts and structured logging: https://logging.apache.org/log4j/2.x/manual/layouts.html
- Apache Log4j 2 — JSON Template Layout: https://logging.apache.org/log4j/2.x/manual/json-template-layout.html
- OpenTelemetry — Semantic conventions for events: https://opentelemetry.io/docs/specs/semconv/general/events/
- Java SE 17 — `java.util.logging`: https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/package-summary.html

**Key takeaway:** a standard event code is an **immutable identifier for a cataloged event type**, not a log level, message, public `errorCode`, or request ID. For true structured logging, emit codes into **structured fields**, keep schemas and semantics stable, define triggers/owners/required attributes, enforce security controls, and test the entire ingest pipeline. Well-designed codes keep systems easy to query, alert on, and investigate **even as log messages or Java implementations evolve**.