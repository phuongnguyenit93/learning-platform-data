# Stable Field Names in Structured Logging

**Stable field names** is the principle of defining and maintaining **consistent structured data key names in logs** over time, across services, environments, application versions, and processing pipelines. When an event logs `requestId` today, it should not be arbitrarily changed tomorrow to `request_id`, `requestID`, or `rid` while dashboards, alerts, and queries still rely on the old name.

In **structured logging**, a log is not just a human-readable string. Each event can consist of **key–value** pairs such as `eventName`, `level`, `service`, `requestId`, `orderId`, `durationMs`, and `errorCode`. Field names are part of the **data contract (log schema)** between the application emitting logs and its consumers: collectors, indexers, dashboards, alerting systems, incident investigation tools, and operational analytics.

**Goal:** not to force every event to contain every field, but to ensure **each field name is clearly defined and preserves its meaning, data type, and unit**, while schema changes are managed like API changes.

## 1. Why Do Stable Field Names Matter?

Consider two records describing the same type of request:

```json
{"eventName":"checkout.completed","requestId":"req-17","durationMs":23,"outcome":"success"}
{"eventName":"checkout.completed","request_id":"req-18","duration_ms":"19ms","result":"ok"}
```

A human can tell both lines mean the same thing. However, a system searching by `requestId` will miss the second record; a chart computing `avg(durationMs)` cannot automatically treat `"19ms"` as the number `19`; and a rule counting `outcome="success"` will not match `result="ok"`.

These inconsistencies cause several types of failures:

1. **Incomplete query results:** logs are still written, but queries filtering by the old field name no longer see part of the events.
2. **Inaccurate alert evaluations:** error counts or failure rates are undercounted or drop to zero because a group of services switched field names.
3. **Broken dashboard continuity:** data before and after a deployment lands in two different fields and cannot be viewed together reliably.
4. **Broken correlation:** tracing from an API gateway to another service fails if one uses `traceId` and another uses `trace_id` without normalization in the pipeline.
5. **Increased ingest/index costs:** multiple aliases for the same concept bloat schemas, mappings, and processing rules.
6. **Harder incident investigation:** on-call engineers must remember multiple naming variants and write fallback queries.
7. **Backward-compatibility risks:** automated log-consuming tools often depend on field names even though logs do not have a formal public API type.

**Stability encompasses multiple dimensions**: preserving the name, definition, data type, unit, missing-field handling, and allowed value set. A `durationMs` field is still "semantically unstable" if a later release silently changes its value to microseconds.

## 2. Distinguishing Field Names, Values, and Event Names

A structured event typically looks like this:

```json
{
  "timestamp": "2026-11-09T12:00:00Z",
  "level": "INFO",
  "service": "checkout-service",
  "eventName": "checkout.completed",
  "requestId": "req-17",
  "orderId": "ord-42",
  "durationMs": 23,
  "outcome": "success",
  "errorCode": null
}
```

Where:

- **Field name** is the key name such as `requestId` or `durationMs`, which must have a clear meaning and remain consistent.
- **Field value** such as `req-17` or `23` varies per event.
- **Event name** such as `checkout.completed` is a **categorical value** that should also be stable because metrics and alerts may query by it.
- **Schema** describes which fields are allowed or required, their data types, units, value sets, and conditions of appearance.
- **Format** is how the event is serialized into JSON, text, or another structure. Changing the layout does not automatically fix field names emitted inconsistently by the application.

**Common mistake:** creating dynamic key names, such as `"user_" + userId`, instead of keeping the `userId` key and placing the ID in the value. With many users, dynamic keys can cause **field explosion** in the index; that is a different issue from high-cardinality values, though both must be managed.

```json
{"user_101":"logged_in","user_102":"logged_in"}
```

**Avoid** using the structure above to represent a user login event. Use stable key names:

```json
{"eventName":"auth.login","userId":"101","outcome":"success"}
```

This example illustrates structure only. `userId` may be sensitive data under your organization's policy; consider whether it may be logged, how pseudonymization is applied, and its retention period.

## 3. Building a Log Schema with a Clear Contract

A minimal schema should specify **name, type, semantics, unit, required/optional, source, and security requirements**. Example for the checkout domain:

| Field name | JSON data type | Meaning / unit | Presence policy |
| --- | --- | --- | --- |
| `schemaVersion` | number (integer) | Version of the log event contract. | Required when event-level versioning is used. |
| `timestamp` | string | Event time, ISO 8601/RFC 3339 with timezone. | Required, unless added by the backend/collector. |
| `level` | string | Severity by convention, such as `INFO`, `WARN`, `ERROR`. | Required. |
| `service` | string | Stable service name per deployment system. | Required in centralized logging. |
| `logger` | string | Logger namespace/class. | Recommended for filtering by component. |
| `eventName` | string | Stable event name such as `checkout.completed`. | Required for named business events. |
| `requestId` | string | ID of a request or equivalent unit of work. | Context-dependent; may be absent in background jobs. |
| `traceId` | string | Trace ID when tracing is enabled. | Context-dependent; do not fabricate if no trace exists. |
| `orderId` | string | Order identifier permitted for storage. | Only on order-related events. |
| `durationMs` | number (integer/decimal per schema) | Duration in **milliseconds**. | Present on events where duration was measured. |
| `outcome` | string (enum) | Status such as `success`, `failure`, `rejected`. | Present on work-completion events. |
| `errorCode` | string or null | Stable error code; not a free-form message. | Present when an error occurs, or `null` per contract. |

This is an **illustrative schema**, not mandatory field names for every Java framework. If your system already uses **OpenTelemetry Semantic Conventions, Elastic Common Schema (ECS)**, or an internal standard, **choose one primary convention and maintain a clear mapping table** rather than renaming everything to match this example.

A high-quality schema answers questions like: *"From what point to what point does `durationMs` measure? Does it include retry time? If not measured, is the field absent, `null`, or `0`?"* Without a clear definition, even if the name stays the same, the data remains hard to compare.

## 4. Rules for Naming Stable Fields

### 4.1. Choose One Naming Convention and Apply It Consistently

Common styles:

| Convention | Example | Notes |
| --- | --- | --- |
| `camelCase` | `requestId`, `durationMs`, `errorCode` | Aligns naturally with Java property names, though not mandatory. |
| `snake_case` | `request_id`, `duration_ms`, `error_code` | Common in some data systems and observability tools. |
| Namespaced or nested names | `http.response.status_code` or nested object `http.response.status_code` | Understand the difference between dotted key strings and nested objects. |

**No single style is right for every organization.** What matters is that **the schema and pipeline agree on one style**, rather than letting each team invent its own names for the same concept.

If you implement OpenTelemetry or ECS, you must follow **the field names and structure defined by the adopted standard**. Do not force camelCase onto standard fields defined differently.

### 4.2. Names Must Express Meaning and Avoid Generic Terms

Compare:

| Hard-to-use name | Problem | Clearer example |
| --- | --- | --- |
| `id` | Unclear which entity the ID belongs to. | `requestId`, `orderId`, `jobId` |
| `status` | HTTP status, job state, or business outcome? | `httpStatusCode`, `jobStatus`, `outcome` |
| `time` | Point in time or duration? | `timestamp`, `durationMs` |
| `error` | Boolean, message, code, or object? | `errorCode`, `errorMessage`, `exceptionType` |
| `name` | Logger name, user name, or service name? | `logger`, `service`, `customerType` |
| `data` | Arbitrary content, hard to map. | Fields with specific, controlled semantics |

Do not make names overly long by repeating unnecessary namespace levels. A good name should be **concise yet unambiguous**.

### 4.3. Units Must Be Part of the Contract

A common issue that breaks dashboards is using the same field name while changing the unit:

```json
{"eventName":"api.completed","duration":250}
{"eventName":"api.completed","duration":0.25}
```

Here `duration` does not indicate milliseconds or seconds. Fix it by specifying one clear unit:

```json
{"eventName":"api.completed","durationMs":250}
{"eventName":"api.completed","durationMs":125}
```

If the application uses `durationMs`, **every producer must emit a number in milliseconds**—never a string `"250ms"`, and never switching to nanoseconds while keeping the same name. If a different precision is needed later, manage it as a schema change (e.g., adding `durationNs` with a migration plan).

### 4.4. Do Not Use Dynamic Values as Key Names

**Wrong:**

```json
{"request_472":"success","request_473":"failure"}
```

**Right:**

```json
{"requestId":"472","outcome":"success"}
{"requestId":"473","outcome":"failure"}
```

Variable data belongs in values. Besides field explosion, dynamic keys prevent type enforcement, mappings, and field-level access control.

### 4.5. Do Not Stuff All Data into `message`

**Text message only:**

```json
{"message":"order ord-42 completed in 23ms"}
```

Readable by humans, but systems must parse the string, which breaks easily when wording or language changes. **With explicit fields:**

```json
{"eventName":"checkout.completed","orderId":"ord-42","durationMs":23,"outcome":"success","message":"Checkout completed"}
```

Keep `message` for human readability; data used for queries and alerts should have dedicated fields. Avoid extracting structured fields from `message` via regex when the API and backend already support structured logging.

## 5. Keep Data Types and Value Sets Stable

Using the same name is not enough if events emit values with different types:

```json
{"durationMs":23}
{"durationMs":"23"}
{"durationMs":"23ms"}
```

In a well-defined JSON schema, `durationMs` is a **number**, not a string. An index or search backend may infer a mapping from the first value or report a conflict when a later record has a different type. Exact behavior depends on the ingestion system, but regardless of the symptom, this is an inconsistent schema.

### Data Type Guidelines

- **IDs:** usually string even when they look numeric, because IDs are not used for arithmetic and may have leading zeros.
- **Durations and sizes:** usually number with a clear unit; integer may be used if precision requirements are met.
- **HTTP status:** if the schema defines a number, do not mix `200` and `"200"`.
- **Boolean:** use only `true`/`false` for binary properties; do not mix with `"yes"`/`"no"`.
- **Timestamp:** choose a published format and timezone; do not switch between epoch milliseconds and date-time strings in the same field.
- **Error code:** should be a stable code such as `UPSTREAM_TIMEOUT` or `INVALID_ORDER`; do not rely on free-form `errorMessage` strings for alert classification.
- **Enum:** standardize `success`/`failure`/`rejected` instead of randomly switching to `ok`/`failed`/`denied`.

**Enum values are also part of the contract.** A dashboard filtering on `outcome="failure"` will break if a subsequent release emits `outcome="failed"`, even though the field name did not change.

### Null, Absent, Empty String, and Zero Are Not Equivalent

| Representation | Possible intended meaning | What to define |
| --- | --- | --- |
| `errorCode` omitted | This event has no error attribute, or the producer does not know the value. | Distinguish "not applicable" from "missing data" if the business requires it. |
| `"errorCode": null` | The contract includes the field, but no specific error occurred. | Does the collector preserve `null` or drop the field? |
| `"errorCode": ""` | Empty string, often hard to distinguish from missing data. | Avoid using this to mean "no error" when clearer options exist. |
| `"durationMs": 0` | Actual duration is zero within the recorded precision. | Never use `0` to mean "not measured." |

The choice **does not have to be identical for every field**. What matters is that the producer, schema, and consumer agree, and tests enforce the choice.

## 6. Stability Scopes: Within One Service, Across Services, and Across Versions

### One Service, Multiple Code Paths

Controllers, services, and batch jobs must use **the same name for the same semantics**. Do not let a REST controller log `requestId` while a background job logs `reqId` for the same concept if unified tracing is the goal.

### Multiple Services

If services share `traceId` and `spanId` within a tracing pipeline, standardize the ID format, context attachment point, and propagation mechanism. Do not treat `requestId` and `traceId` as interchangeable:

- **requestId** may identify a request at an API boundary and does not necessarily share the lifecycle of a distributed trace.
- **traceId** follows a trace across multiple services when tracing is enabled.
- **spanId** identifies a single span within a trace.
- **correlationId** may represent a business workflow identifier spanning longer than a single request or trace, if defined by the organization.

You may attach multiple IDs, but never swap values between fields just because "they are all IDs."

### Multiple Application Versions

During rolling or blue-green deployments, **two versions may emit logs simultaneously for a period**. The new schema must be handled while services and dashboards are not yet upgraded together. This is why renaming a field requires a backward-compatible rollout rather than just editing code and deploying.

## 7. Java 17: Standalone Example Emitting JSON with Fixed Field Names

This example uses **Java Util Logging (JUL)** built into JDK 17 to illustrate the stable schema concept. It emits two events with:

- **Fixed field names:** `schemaVersion`, `timestamp`, `level`, `service`, `logger`, `eventName`, `requestId`, `orderId`, `durationMs`, `outcome`, `errorCode`.
- **Fixed data types:** `durationMs` and `schemaVersion` are numbers; IDs and enums are strings; `errorCode` is a string or `null`.
- **Fixed field order** for easy output inspection, though **JSON object key order should generally not be a query requirement**.
- Fixed timestamp in the demo for reproducible stdout. Real applications should use event timestamps from the real clock or framework.

**Do not confuse this example with a built-in JUL structured logging API:** this snippet uses a custom `Formatter` to demonstrate the schema. In production, use a proven JSON encoder or structured logging library rather than maintaining a manual serializer.

### 7.1. Source Code `StableFieldNamesDemo.java`

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

public final class StableFieldNamesDemo {
    private static final Logger LOG =
            Logger.getLogger("demo.checkout");

    // This record describes business values and does not create dynamic field names.
    private record EventFields(
            String requestId,
            String orderId,
            long durationMs,
            String outcome,
            String errorCode
    ) {}

    private static final class JsonFormatter extends Formatter {
        @Override
        public String format(LogRecord record) {
            EventFields event = (EventFields) record.getParameters()[0];
            StringBuilder out = new StringBuilder("{");

            numberField(out, "schemaVersion", 1);
            stringField(out, "timestamp", record.getInstant().toString());
            stringField(out, "level", record.getLevel().getName());
            stringField(out, "service", "checkout-service");
            stringField(out, "logger", record.getLoggerName());
            stringField(out, "eventName", record.getMessage());
            stringField(out, "requestId", event.requestId());
            stringField(out, "orderId", event.orderId());
            numberField(out, "durationMs", event.durationMs());
            stringField(out, "outcome", event.outcome());
            stringField(out, "errorCode", event.errorCode());

            return out.append("}\n").toString();
        }
    }

    private static void prefix(StringBuilder out, String name) {
        if (out.length() > 1) {
            out.append(',');
        }
        out.append('"').append(name).append("\":");
    }

    private static void stringField(
            StringBuilder out, String name, String value) {
        prefix(out, name);
        if (value == null) {
            out.append("null");
        } else {
            out.append('"').append(escapeJson(value)).append('"');
        }
    }

    private static void numberField(
            StringBuilder out, String name, long value) {
        prefix(out, name);
        out.append(value);
    }

    // Simple serializer for demo purposes only; do not use in production.
    private static String escapeJson(String value) {
        StringBuilder out = new StringBuilder();
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
                        out.append(String.format("\\u%04x", (int) c));
                    } else {
                        out.append(c);
                    }
                }
            }
        }
        return out.toString();
    }

    private static void emit(
            Level level,
            String eventName,
            Instant timestamp,
            EventFields fields
    ) {
        LogRecord record = new LogRecord(level, eventName);
        record.setInstant(timestamp);
        record.setLoggerName(LOG.getName());
        record.setParameters(new Object[]{fields});
        LOG.log(record);
    }

    public static void main(String[] args) throws Exception {
        LOG.setLevel(Level.INFO);
        LOG.setUseParentHandlers(false);

        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        Handler handler = new StreamHandler(bytes, new JsonFormatter());
        handler.setLevel(Level.ALL);
        handler.setEncoding(StandardCharsets.UTF_8.name());
        LOG.addHandler(handler);

        try {
            Instant fixedTime = Instant.parse("2026-11-09T12:00:00Z");

            emit(Level.INFO, "checkout.completed", fixedTime,
                    new EventFields("req-17", "ord-42",
                            23, "success", null));

            emit(Level.WARNING, "checkout.rejected", fixedTime,
                    new EventFields("req-18", "ord-43",
                            7, "rejected", "INVALID_ORDER"));
        } finally {
            LOG.removeHandler(handler);
            handler.close();
        }

        System.out.print(bytes.toString(StandardCharsets.UTF_8));
    }
}
```

### 7.2. Compile and Run

Requires JDK 17 or later:

```bash
javac StableFieldNamesDemo.java
java StableFieldNamesDemo
```

**Exact standard output** of the program, one JSON object per line:

```json
{"schemaVersion":1,"timestamp":"2026-11-09T12:00:00Z","level":"INFO","service":"checkout-service","logger":"demo.checkout","eventName":"checkout.completed","requestId":"req-17","orderId":"ord-42","durationMs":23,"outcome":"success","errorCode":null}
{"schemaVersion":1,"timestamp":"2026-11-09T12:00:00Z","level":"WARNING","service":"checkout-service","logger":"demo.checkout","eventName":"checkout.rejected","requestId":"req-18","orderId":"ord-43","durationMs":7,"outcome":"rejected","errorCode":"INVALID_ORDER"}
```

**Why can we trust this output?**

1. Both `Logger` and `Handler` allow `INFO` and `WARNING`, and `setUseParentHandlers(false)` prevents events from propagating to parent logger handlers.
2. `emit` uses `LogRecord` with the message as the **event name**, a fixed timestamp, and `EventFields` holding values with explicit Java types.
3. `JsonFormatter` fixes **static key names** via `stringField`/`numberField` calls; it never constructs key names from request IDs or dynamic content.
4. `EventFields.durationMs` is a `long`, so JSON is written as a number rather than mixed with strings like `"23ms"`.
5. `errorCode` can be `null` on a successful event and a string on a rejected event; this is a clearly documented schema choice.
6. `handler.close()` flushes and closes the `StreamHandler` before reading from `ByteArrayOutputStream`. Final output comes only from `System.out.print`, with no machine timestamps or non-deterministic thread names.
7. `escapeJson` escapes basic JSON characters in strings. This is a **simplified educational serializer** that does not cover all Unicode, structured exception, or schema validation needs, so do not copy it into production as a general-purpose JSON library.

**Takeaway from the example:** when values change from `req-17` to `req-18` and from `success` to `rejected`, **field names and types stay the same**. This allows every record to be queried with the exact same query across runs.

## 8. Keeping Field Names Stable with SLF4J, Logback, and Log4j2

### 8.1. Message Placeholders Alone Are Not Structured Fields

```java
// Illustrative snippet inside a class with an SLF4J logger.
LOG.info("orderId={} durationMs={}", orderId, durationMs);
```

This call **does not guarantee** that the JSON output will have separate `orderId` and `durationMs` keys. On many backends, it only produces a formatted message string such as `"orderId=ord-42 durationMs=23"`.

To emit real keys, you need a structured logging API or a context/key-value facility along with an encoder/layout configured to output them. You can still write a friendly message, but machine-consumed fields must appear as separate attributes.

### 8.2. SLF4J 2.x Fluent Key–Value API

In SLF4J 2.x, you can use the fluent API to attach key–value pairs to a logging event:

```java
// Illustrative code; requires SLF4J 2.x and a compatible backend.
LOG.atInfo()
   .addKeyValue("eventName", "checkout.completed")
   .addKeyValue("orderId", orderId)
   .addKeyValue("durationMs", durationMs)
   .log("Checkout completed");
```

This is an **illustrative snippet, not a standalone program**: `LOG`, `orderId`, `durationMs`, and the required dependencies must already exist. The `addKeyValue(...)` API makes field names explicit at the SLF4J event level, but **does not guarantee the default backend will automatically print them as JSON**. Verify your actual provider, pattern/encoder, and ingestion pipeline.

A benefit of this API is that field names are visible at the log call site, but if codebases mix `"durationMs"`, `"latency"`, and `"duration"`, the API alone will not keep the schema stable. Centralize field names in constants, a controlled schema, or a strongly typed internal helper API.

### 8.3. MDC: Stable Keys, Context-Bound Values

SLF4J MDC or Log4j2 ThreadContext is commonly used for execution-flow data such as `requestId` and `traceId`:

```java
// Illustrative code inside a method with LOG and requestId variables.
org.slf4j.MDC.put("requestId", requestId);
try {
    LOG.info("event=checkout.started");
} finally {
    org.slf4j.MDC.remove("requestId");
}
```

MDC avoids passing the request ID manually to every method, but it does not standardize key names on its own. If middleware writes `correlation_id` and a controller queries `requestId`, the pipeline still ends up with two different fields.

**Watch out for types:** MDC typically stores **strings**, so storing `durationMs` in MDC may serialize it as a JSON string unless the encoder or schema explicitly converts it. Numbers used for aggregation should be emitted with the proper type or mapped through a verified step.

**Watch out for concurrency:** MDC/ThreadContext is usually tied to thread context. `CompletableFuture` tasks, `ExecutorService` workers, reactive pipelines, or virtual threads do not automatically inherit the same context. Use proper context propagation and clear fields in the right scope to avoid mixing IDs across requests.

### 8.4. Logback and Log4j2 on the Backend

- **Logback:** choose a compatible encoder/layout to emit events, MDC, and key–value pairs as separate fields. `PatternLayoutEncoder` produces a text pattern; not every text configuration produces structured JSON.
- **Log4j2:** provides `ThreadContext` and various layouts. `JsonTemplateLayout` can be used when the corresponding module and template are installed at compatible versions.
- **JUL:** `LogRecord`/`Formatter` can format logs to an internal standard, but a custom JSON formatter like the demo above should not replace a standard encoder in production.
- **Collector:** can normalize field names at ingest time. If you standardize at the collector, the application and pipeline must agree on source/target fields to avoid double-renaming or inconsistent mappings.

**General rule:** standardizing the schema at the **producer** is ideal for consistency; collector-side mapping can help when integrating libraries or legacy services, but must be documented, tested, and monitored so it does not mask data errors.

## 9. Renaming Fields and Managing Schema Evolution

Renaming a field is a **breaking change for consumers** relying on it. It should never be done as a simple Java variable refactor.

Suppose the system currently emits:

```json
{"durationMs":120}
```

The project wants to move to a new schema using `processingTimeMs` to better reflect business processing time. If you rename it in one shot:

```json
{"processingTimeMs":120}
```

existing dashboards querying `durationMs` may stop displaying data. How to manage the change:

1. **Assess impact:** find all queries, dashboards, alerts, ETL jobs, downstream consumers, docs, and contract tests using the old name.
2. **Define the new name:** confirm semantics, type, unit, and whether a rename is truly needed or only a description update.
3. **Publish the version:** record the change in the schema registry/docs; bump `schemaVersion` according to policy if applicable.
4. **Compatibility phase:** when truly needed, emit **both field names in parallel** for a short period, or map the old name to the new one at the collector. Mark the old name as deprecated.
5. **Update consumers:** dashboards, alerts, ETL, tests, and other services must understand the new name before the old one is removed.
6. **Observe in production:** measure the percentage of records still using the old name and identify un-migrated producers.
7. **Remove the old name only after migration completes:** agree on a sunset date, update docs/schemas, and verify no consumers remain dependent.
8. **Consider historical data:** older records still carry the old name; dashboards querying across the transition need an alias/mapping or a query supporting both.

### Example Time-Bounded Dual-Write Strategy

```json
{"schemaVersion":2,"durationMs":120,"processingTimeMs":120}
```

This is a **transitional pattern**; never keep two aliases forever. It enlarges records and risks divergence if a producer computes them inconsistently. If you choose dual-write, derive both fields from **a single source of truth** and add tests verifying equality.

Depending on infrastructure needs, you can **skip** dual-write and transform at the collector or use version-aware queries in consumers. Either way, have a compatibility plan—never delete an old field while it is still in use.

### Changing Meaning Without Changing the Name Is Even More Dangerous

If `durationMs` previously measured the entire request but now only measures database time, dashboards may continue rendering normally while **the metrics become fundamentally wrong**. When the definition changes, introduce a new field with clear semantics (e.g., `dbDurationMs`) or version the schema and update consumers in a controlled manner.

## 10. Designing a Field Dictionary and Ownership

For multi-team environments, maintain a concise **field dictionary** reviewed like code. An entry should include:

| Attribute | Example for `durationMs` |
| --- | --- |
| Canonical name | `durationMs` |
| JSON type | Number, non-negative per contract |
| Unit | Milliseconds |
| Semantics | Elapsed time from start of checkout processing to final outcome |
| Required/optional | Present on `checkout.completed` or `checkout.failed` when measured |
| Missing behavior | Absent when not measured; do not use `0` for missing |
| Source | Application timer, never derived from user-supplied strings |
| Privacy classification | Contains no direct personal data |
| Consumers | Latency dashboards, alerts, incident investigation |
| Owner | Event schema owner team |
| Introduced/deprecated | Release/schema version where introduced or changed |

For `errorCode`, maintain a stable code catalog. For `requestId`, define format, length, retention, and access permissions. For `timestamp`, define timezone, clock source, and late-arriving data policy.

**Schema ownership** matters just as much as naming conventions: without someone reviewing changes, each module will invent its own names. You can provide constants, helpers, or typed event builders to reduce typos, without over-engineering abstractions.

## 11. Unified Naming and Avoiding Conflicts Across Multiple Sources

### 11.1. Avoid Overwriting Reserved Fields

Backends and collectors often provide built-in fields such as timestamp, severity, resource/service, logger, and exception. If an application also emits `timestamp` with a different meaning or uses `level` for a customer tier, ingestion may overwrite it or create ambiguity.

If the application field is actually `customerLevel`, do not name it `level` when `level` is reserved for log severity. Use a namespace or a full descriptive name per the chosen schema.

### 11.2. Dots in Field Names Are Not Always Nested Objects

The following two structures **are not identical JSON representations**:

```json
{"http.response.status_code":200}
{"http":{"response":{"status_code":200}}}
```

Some indexers and query engines treat dots as nested paths or handle them differently. Do not assume the collector automatically converts between the two. If your organization uses dotted names, explicitly decide on the source JSON shape, mapping, and downstream query syntax.

### 11.3. Do Not Unconditionally Mix Source Fields and Normalized Fields

A service might emit `requestId` while the standard pipeline expects `request.id`. You can convert at the collector, but you need:

- A versioned mapping definition.
- Precedence rules when both source and target fields exist.
- Data type checks and null/missing handling.
- Traceability between raw input events and post-ingest events during incident debugging.
- Contract tests to detect when a service changes a source field before the pipeline is updated.

This approach supports legacy migration; do not treat collector mapping as an excuse for each service to keep inventing arbitrary names.

## 12. Testing Schema Stability

Do not only test that the application called `logger.info(...)`. With structured logging, **the output after the encoder/formatter** is what consumers actually receive.

### Recommended Test Categories

1. **Schema key test:** events of type `checkout.completed` contain all documented required keys.
2. **Type test:** `durationMs` is a number; `errorCode` is string/null; `schemaVersion` is an integer.
3. **Value test:** `outcome` is within the allowed enum set; `eventName` is a stable name.
4. **Null/missing test:** successful events handle `errorCode` per policy; background jobs lacking `requestId` are not assigned fake IDs.
5. **Timestamp test:** timestamp includes timezone and parses under the committed format.
6. **Escaping test:** quotes, Unicode, newlines, and control characters do not break JSON structure or enable log injection.
7. **Throwable test:** on errors, exception type/stack trace/cause are emitted per contract without leaking secrets.
8. **Cross-service test:** two services use `traceId` with consistent format and semantics.
9. **Compatibility test:** existing dashboards/queries still work during schema migration.
10. **Deployment test:** run against the real production backend/encoder, since local/test configurations may differ.

### Simple Type-Checking Rule Example

Once a JSON event is parsed into a map, you can assert:

```text
assert keys contain {"timestamp", "level", "service", "eventName"}
assert type(durationMs) == number
assert type(requestId) == string when requestId exists
assert outcome in {"success", "failure", "rejected"}
assert schemaVersion == expectedVersion
```

This is **pseudocode for a contract test**, not executable Java. In Java, use a JSON parser such as Jackson or Jakarta JSON to read the object and assert types/keys—avoid exact JSON string comparison if key ordering is not guaranteed by the contract.

### Golden Sample Events

Store reviewed example records for each `eventName`, covering success, rejected, failure, and missing-optional-field cases. Whenever the encoder or schema changes, compare keys, types, enums, and semantics; update snapshots only after reviewing downstream consumer impact.

## 13. Performance and Security of Stable Fields

### 13.1. Cardinality and Index Cost

Stable field names prevent uncontrolled **proliferation of new field names**, but do not by themselves solve **high-cardinality values**. For example, `requestId` can have millions of unique values: placing it in the value is structurally correct, yet indexing every ID still consumes resources. Plan indexing and retention policies for your platform.

Avoid serializing an arbitrary request object or map directly into thousands of dynamic field names. When flexible metadata is needed, consider allowlists, size/element limits, and safe storage shapes (schema-bound nested objects, safe payload fields, or dropping unneeded parts).

### 13.2. Sensitive Data

Fields such as `userId`, `email`, `clientIp`, `sessionId`, and `authorization` may contain personal data or secrets. Stable field names make masking policies easier to apply, but **do not make sensitive values safe**.

Never log passwords, access tokens, session cookies, private keys, or full request bodies unnecessarily. Evaluate storage necessity, encryption at rest, access controls, retention periods, and third-party access. If personal identifiers must be logged, consider managed pseudonymization/hashing under appropriate policy; do not assume simple hashing provides absolute anonymization.

### 13.3. Size Limits and Untrusted Data

String fields like `errorMessage` or user-agent may contain newlines, control characters, or large payloads. Use a structured encoder with proper JSON escaping, enforce field length limits, and never use input data as key names. A stable naming convention does not replace input validation.

### 13.4. Logs Are Not Always the Business Source of Truth

Logs can be sampled, filtered, dropped when async queues fill up, or lost to I/O errors and retention limits. Do not use standard application logs as the sole proof that a financial transaction was durably persisted. Mandatory audit trails require dedicated, durable storage and confirmation mechanisms.

## 14. Common Mistakes and Fixes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Mixing `requestId` / `request_id` / `rid` | Queries lose request correlation across sources. | Choose a canonical name or normalize under a contract. |
| `durationMs` sometimes number, sometimes string | Aggregations and mappings can fail. | Define one JSON type; enforce at encoder and via schema tests. |
| Changing `durationMs` from ms to µs while keeping the name | Dashboards show severely wrong metrics. | Rename/version semantics and update consumers. |
| `outcome="ok"` and `outcome="success"` meaning the same thing | Alerts and metrics split counts incorrectly. | Define a stable enum; map during migration. |
| Using `user_42` as a key name | Field explosion; schema and index become unmanageable. | Use `userId` as key, `"42"` as value, and review privacy. |
| Using a generic `id` field for every entity | Unclear which entity the ID identifies. | Use `orderId`/`jobId`/`requestId` per semantics. |
| Parsing all data from `message` | Regex breaks easily when text changes. | Emit true structured key–value fields. |
| Renaming a field in code without updating dashboards | Consumers silently drop data. | Run a migration with contract tests and temporary dual-write/mapping. |
| Renaming a field without updating the collector | Events are mis-mapped or fields go missing. | Version changes and run end-to-end tests. |
| Treating `null` as `0` | Latency and error metrics are skewed. | Define null/missing/zero behavior explicitly. |
| MDC stores a number as string while index expects number | Type mismatch or unexpected coercion. | Emit typed fields or apply consistent mapping. |
| Logging `traceId` without propagating context across async tasks | Broken traces and wrong correlations. | Propagate context and clean up in the right scope. |
| Naming fields after internal Java object structures | Class refactors break the log schema. | Decouple the log schema contract from model/DTO field names. |
| Retaining sensitive fields indefinitely | Data exposure and compliance risks. | Minimize, enforce access control, retention, and redaction. |
| Keeping multiple alias fields forever | Bloated logs and complex queries. | Set a deprecation period, removal deadline, and clear owner. |

## 15. Review Checklist Before Adding a New Field

- [ ] Is this name already in the field dictionary or adopted data standard?
- [ ] Does the name accurately describe its semantics without ambiguity or conflict with system fields?
- [ ] Is the naming convention consistent with the rest of the services?
- [ ] Is the JSON type explicit (e.g., number rather than a number stored as a string)?
- [ ] If there is a unit, do the name and contract specify milliseconds, bytes, ratio, or epoch?
- [ ] Can the field be omitted; how are absent, null, empty string, and zero handled?
- [ ] If it is an enum, are the allowed values stable and rules for adding new values defined?
- [ ] Could the data be a secret or personal data; does it truly need to be logged?
- [ ] Does the field have high cardinality or dynamic keys that could pressure the index?
- [ ] Is the field emitted in code rather than just printed in `message`, and does the encoder output it as a separate field?
- [ ] If renaming, have the migration plan, `schemaVersion`, dashboards, and existing queries been evaluated?
- [ ] Are there contract tests and verification against the real runtime backend/collector?
- [ ] Which team owns the definition and approves changes to this field?

## 16. Knowledge Check

1. If two services log `requestId` and `request_id`, what kinds of queries can break? Will changing the log layout fix it automatically?
2. Why are `durationMs:23` and `durationMs:"23ms"` incompatible?
3. When a field does not apply to an event, how should you choose between omitting it and setting `null` so consumers interpret it correctly?
4. How do `requestId`, `traceId`, and `spanId` differ in semantic scope?
5. Why should you avoid using `"order_" + orderId` as a key in a structured log event?
6. Does calling SLF4J `LOG.info("durationMs={}", value)` guarantee a JSON field named `durationMs`?
7. Before renaming `durationMs` to `processingTimeMs`, which consumers must be evaluated before deployment?
8. What are the advantages and risks of dual-writing two fields during a transition period?
9. Do stable field names solve issues with logs containing tokens, private data, or indexing costs?
10. In the Java 17 demo, why does the formatter output `durationMs` as a number and keep `errorCode` under the same contract even when its value can be `null`?

**Conclusion:** In structured logging, **a field name is a data interface with consumers**, not just a convenient string in code. Choose canonical names, define types, units, and semantics, stay consistent across services and versions, manage renames like API changes, test actual output, and protect sensitive data. Doing so ensures logs can be queried, correlated, aggregated, and alerted on reliably over time.