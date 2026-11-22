# The `level` Field in JSON Logging: Standardizing Log Severity

In **JSON logging**, each record should have a dedicated field to represent the **severity of the event**, commonly named `level`. Instead of embedding the text `INFO`, `WARN`, or `ERROR` into a hard-to-parse text line, structured logs use **keys and values with explicit data types**, enabling searching, filtering, grouping, and building automated alerts.

For example:

```json
{"timestamp":"2026-11-09T03:15:30.123Z","level":"WARN","service":"order-service","event":"inventory_retry","requestId":"req-17","attempt":2}
```

This is **illustrative JSON**. The `level` field has the value `"WARN"` as a **JSON string**, not an enum predefined by JSON itself. The application and collection system must agree on the value set, casing, conversion rules from the source logging API, and the policy for handling unknown levels.

This lesson belongs to the **JSON logging** group and focuses on the **`level` field**: its meaning, data type, naming, value set, how to map JUL/SLF4J/Log4j 2 levels, its relationship with level filtering, comparison with OpenTelemetry/ECS, how to emit single-line JSON safely in Java 17, and how to verify results from the collector.

## 1. What is the `level` field, and how does it differ from `message`?

A structured logging record might contain:

```json
{
  "timestamp": "2026-11-09T03:15:30.123Z",
  "level": "ERROR",
  "logger": "com.example.order.OrderService",
  "service": "order-service",
  "event": "checkout_failed",
  "requestId": "req-17",
  "errorCode": "UPSTREAM_TIMEOUT",
  "message": "Cannot complete checkout"
}
```

Meaning of each field:

| Field | Answers the question | Example |
| --- | --- | --- |
| `timestamp` | When was the event recorded? | `2026-11-09T03:15:30.123Z` |
| **`level`** | How severe is the event classified as? | `ERROR` |
| `logger` | Which logger/category emitted the event? | `com.example.order.OrderService` |
| `service` | Which application/service generated the log? | `order-service` |
| `event` | What stable event type occurred? | `checkout_failed` |
| `requestId` | Which request is this? | `req-17` |
| `errorCode` | Which business/technical error category? | `UPSTREAM_TIMEOUT` |
| `message` | Human-readable description of the event | `Cannot complete checkout` |

**Key point:** `level` is an **assessment of the severity/observability priority of the log event**, not `errorCode`, not HTTP status, not the logger name, and not a mechanism for classifying sensitive data.

For example, an HTTP request returning `404` can be logged at `INFO` when it is an expected situation; an internal `500` error can be logged as `ERROR`. There is no automatic rule that `HTTP status = 4xx` always equals `WARN` or that every exception must be `ERROR`.

### Why use a dedicated field?

With text logs:

```text
2026-11-09 10:15:30 ERROR com.example.OrderService - checkout failed
```

Search systems often have to parse based on position or regex. If the message contains the word `ERROR`, a simple text query can produce false positives.

With JSON:

```json
{"level":"INFO","message":"Previous ERROR was recovered"}
```

A system that reads the `level` field properly will know this is **INFO**, even though `message` contains the word `ERROR`. This distinction is critical when computing error rates or triggering alerts.

## 2. Recommended Contract for the `level` Field

If the application owns its JSON schema and does not yet have to follow an external schema, a simple contract is:

- **Key:** `level` — fixed, lowercase; do not arbitrarily rename it to `logLevel` in some services.
- **Data type:** **JSON string**.
- **Core values:** `TRACE`, `DEBUG`, `INFO`, `WARN`, `ERROR`.
- **Additional value:** `FATAL` if the API/backend and policy genuinely distinguish a fatal level; do not add it arbitrarily when it carries no meaning.
- **Casing:** consistent uppercase, e.g., `WARN` instead of logging `warning` in one place and `Warn` in another.
- **Meaning:** the level of the **emitted event**; not the current configuration threshold of the entire application.
- **Unknown values:** have an explicit handling policy; do not silently replace every unfamiliar level with `ERROR`.

Reference table:

| Normalized level | When it is useful | Typical priority |
| --- | --- | --- |
| `TRACE` | Extremely detailed low-level execution flow | Usually disabled in production |
| `DEBUG` | Information helping developers investigate | Enabled selectively |
| `INFO` | Normal operational events that are useful | Usually retained |
| `WARN` | Unusual situation, risk, retry, or degradation | Frequency should be monitored |
| `ERROR` | Failed operation or issue requiring investigation | Often needs context-aware alerting |
| `FATAL` (system-dependent) | Critical failure making the process/system unable to continue | Not every API supports it separately |

**Do not assume `FATAL` is a default SLF4J level**: the standard SLF4J API provides `TRACE`, `DEBUG`, `INFO`, `WARN`, and `ERROR`; Log4j 2 adds `FATAL`. Mapping must originate from the **source API** and the collection system's contract, not from an imaginary table shared across all backends.

If the system needs both the **original** level and the **normalized** level, you can use:

```json
{"level":"WARN","original_level":"WARNING","message":"Slow dependency response"}
```

In this example, `WARNING` is the original level name from **JUL**, while `WARN` is the normalized value for consistent querying across services. The two fields have different responsibilities. Do not store two conflicting fields without defining a mapping rule.

## 3. Store `level` as a String or a Number?

There are several ways to represent severity:

```json
{"level":"ERROR"}
```

```json
{"severity_number":17}
```

These are **two different example schemas**; it does not mean `17` is a mandatory encoding for `ERROR` across all backends. The **string** type is usually easier to read and works well when there are only a few levels; numeric severity can be useful for sorting/comparison and for telemetry standards that define numeric ranges.

**Rule: do not mix types for the same key.** These are two events that must not coexist in the same index/schema if `level` is declared as a string:

```json
{"level":"ERROR"}
{"level":1000}
```

`1000` could be JUL's `Level.SEVERE.intValue()`, but it is **not synonymous** with `ERROR` in a team-chosen JSON standard or OpenTelemetry's `SeverityNumber`. If you want to store JUL's original number, use an explicit name such as `jul_level_value` and document its unit/level system.

### OpenTelemetry Logs: `SeverityText` and `SeverityNumber`

OpenTelemetry defines two concepts:

- **`SeverityText`**: the **original** log level string as provided by the source (the name does not need to match a global enum).
- **`SeverityNumber`**: the **standardized** severity number in the OpenTelemetry model.

Numeric ranges in the OpenTelemetry Logs Data Model:

| `SeverityNumber` range | Level group |
| --- | --- |
| `1–4` | TRACE |
| `5–8` | DEBUG |
| `9–12` | INFO |
| `13–16` | WARN |
| `17–20` | ERROR |
| `21–24` | FATAL |

The value `0` can be used when the level is unspecified according to the model's rules. **Do not infer** JUL `SEVERE = 1000` as `SeverityNumber = 1000`: you must apply the logging source's mapping to the appropriate OTel range. In an application-designed JSON record, naming a field `severity_number` is only valid when a contract confirms it uses the **same semantics** as OTel; do not claim to be a native OpenTelemetry record merely because the name looks similar.

### Elastic Common Schema: `log.level`

If the target is **Elastic Common Schema (ECS)**, `log.level` is a keyword field for the **original log level** of the event. When representing ECS as JSON, the object may have the structure:

```json
{"log":{"level":"WARNING"},"message":"Slow dependency response"}
```

Some pipelines use the field path syntax `log.level` when mapping/searching; nested JSON representation and dotted field names must follow the target system's contract. **Do not treat a custom `level` field as automatically equivalent to ECS `log.level`** without configuring a mapping. ECS `event.severity` also has a numeric meaning defined by the event source, not an arbitrary numeric alias for a JUL level.

**In summary:** You can choose `level` as an uppercase string for an internal schema, but when sending to OTel/ECS you need **explicit mapping**: field name, type, preservation of raw severity, and numeric severity semantics.

## 4. Mapping Levels Across JUL, SLF4J, Logback, and Log4j 2

Java frameworks have different level names and APIs. Below is a **suggested normalization table**, not a mandatory contract for every bridge.

| JUL (`java.util.logging.Level`) | Common SLF4J / Logback | Example JSON `level` | Notes |
| --- | --- | --- | --- |
| `SEVERE` | `ERROR` | `ERROR` | Severe error in JUL |
| `WARNING` | `WARN` | `WARN` | Do not log `WARNING` in one service and treat it as `WARN` without mapping |
| `INFO` | `INFO` | `INFO` | Informational event |
| `FINE` | `DEBUG` | `DEBUG` | Approximate equivalent |
| `FINER` / `FINEST` | `TRACE` or nearby detail level | `TRACE` | Depends on policy and granularity |
| `CONFIG` | No mandatory equivalent | Per policy or store raw `CONFIG` | Do not silently treat as `ERROR` |
| `OFF` / `ALL` | Threshold configuration levels | **Not a normal event** | Used to control filtering |

With **Log4j 2**, common level names include `TRACE`, `DEBUG`, `INFO`, `WARN`, `ERROR`, `FATAL`, along with `OFF` and `ALL` for configuration. Some frameworks also allow custom levels. With **SLF4J 2.x**, common calls include:

```java
// Fragment in a class where org.slf4j.Logger LOG is already declared.
LOG.trace("event=trace_probe");
LOG.debug("event=inventory_lookup");
LOG.info("event=order_created");
LOG.warn("event=retry_scheduled");
LOG.error("event=payment_failed");
```

This snippet requires the SLF4J API and a provider in the project, not a standalone JDK program.

**Important:** Bridges between APIs may translate levels according to the bridge's own rules. Therefore, the JSON `level` field emitted by the final backend may reflect the **translated level** rather than matching 100% of the original level name. If you need an audit trail of the source, keep `original_level` during mapping and ensure the backend/pipeline actually provides that data.

### Do not confuse `level` with exception type or HTTP status

```json
{"level":"WARN","http.status_code":429,"errorCode":"RATE_LIMITED","event":"request_rejected"}
```

```json
{"level":"ERROR","http.status_code":500,"exceptionType":"IllegalStateException","event":"request_failed"}
```

The objects above are illustrative. HTTP `429` can be an expected rate-limiting outcome; `500` usually indicates a server error needing attention. However, `level` must be based on **impact and operational policy**, not merely on the presence of a `Throwable`.

An `IllegalArgumentException` at a validation boundary is not necessarily `ERROR`; conversely, a process failing to catch a critical error may need a higher level. Classify by **actual outcome, recoverability, degree of anomaly, and need for investigation**.

## 5. Log Threshold vs. the `level` Field

There are two distinct points in time:

1. **Before the event is written:** the logger/provider/handler decides whether the event passes the filter threshold.
2. **When the event is serialized:** the encoder outputs the `level` field of the **accepted event**.

For example:

```text
Logger level = INFO
     |
     +-- DEBUG: does not emit JSON from this logger
     +-- INFO : may be logged (if the handler/appender allows)
     +-- WARN : may be logged
     +-- ERROR: may be logged
```

If a `DEBUG` event is filtered **before reaching the encoder**, querying `level=DEBUG` on a dashboard cannot recover that event. Increasing retention, fixing the JSON parser, or enabling the `level` field in the dashboard **cannot restore logs that were never created**.

In JUL, there are also levels on `Logger` and levels on each `Handler`. Both must permit the record before it reaches the formatter. With Logback/Log4j 2, there are also level hierarchies, appender filters, threshold filters, or async pipelines depending on configuration.

**Do not confuse** the value in JSON `"level":"INFO"` with the setting `root.level=INFO`. The first is **metadata of a single record**; the second is a **filtering policy** affecting which records are created/written.

### The `level` in an emitted event should remain consistent

If the application writes:

```json
{"level":"INFO","event":"startup_complete"}
```

then the collector should not automatically change it to `ERROR` just because the message contains the word `failed` or the service name contains `error`. If you want to enrich or reroute an event to a priority stream, use **another field** such as `alert.priority` or a documented mapping, without destroying the original level data unexplained.

## 6. Runnable Java 17 Example: JUL Emitting JSON with `level`

The following program **requires no libraries outside the JDK**. It uses JUL `Logger`, `ConsoleHandler`, `Formatter`, and `LogRecord` to:

- Write each event as **one JSON object per line**.
- Produce a **normalized** `level` and an `original_level` **preserving the JUL level name**.
- Demonstrate the mapping `WARNING → WARN` and `SEVERE → ERROR`.
- Escape quotes, backslashes, newlines, and basic control characters so messages do not break JSON.
- Use a fixed timestamp on `LogRecord` so **the output is deterministic and verifiable**.
- Set the logger/handler threshold to INFO to demonstrate that `FINE` is not emitted.

This is educational code to show how event data is formatted. In production, you should use a **maintained JSON encoder/serializer** rather than maintaining a custom-written JSON serializer.

Save the file as **`JsonLevelDemo.java`**:

```java
import java.time.Instant;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeFormatterBuilder;
import java.util.logging.ConsoleHandler;
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class JsonLevelDemo {
    private static final Logger LOG =
            Logger.getLogger(JsonLevelDemo.class.getName());

    private static final DateTimeFormatter TIME =
            new DateTimeFormatterBuilder()
                    .appendInstant(3)
                    .toFormatter();

    private JsonLevelDemo() {
    }

    private static String normalizedLevel(Level level) {
        if (level == Level.SEVERE) return "ERROR";
        if (level == Level.WARNING) return "WARN";
        if (level == Level.INFO) return "INFO";
        if (level == Level.FINE) return "DEBUG";
        if (level == Level.FINER || level == Level.FINEST) return "TRACE";

        // For CONFIG/custom Level: keep the original name as-is.
        return level.getName();
    }

    private static String jsonString(String value) {
        StringBuilder out = new StringBuilder("\"");
        String hex = "0123456789abcdef";

        for (int i = 0; i < value.length(); i++) {
            char c = value.charAt(i);
            switch (c) {
                case '"':
                    out.append("\\\"");
                    break;
                case '\\':
                    out.append("\\\\");
                    break;
                case '\n':
                    out.append("\\n");
                    break;
                case '\r':
                    out.append("\\r");
                    break;
                case '\t':
                    out.append("\\t");
                    break;
                default:
                    if (c < 0x20) {
                        out.append("\\u00")
                           .append(hex.charAt((c >>> 4) & 15))
                           .append(hex.charAt(c & 15));
                    } else {
                        out.append(c);
                    }
            }
        }

        return out.append('"').toString();
    }

    private static void emit(Level level, Instant timestamp, String message) {
        LogRecord record = new LogRecord(level, message);
        record.setInstant(timestamp);
        record.setLoggerName(LOG.getName());
        LOG.log(record);
    }

    public static void main(String[] args) {
        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.INFO);

        ConsoleHandler console = new ConsoleHandler();
        console.setLevel(Level.INFO);
        console.setFormatter(new Formatter() {
            @Override
            public String format(LogRecord record) {
                return "{"
                        + "\"timestamp\":"
                        + jsonString(TIME.format(record.getInstant()))
                        + ",\"level\":"
                        + jsonString(normalizedLevel(record.getLevel()))
                        + ",\"original_level\":"
                        + jsonString(record.getLevel().getName())
                        + ",\"logger\":"
                        + jsonString(record.getLoggerName())
                        + ",\"message\":"
                        + jsonString(formatMessage(record))
                        + "}"
                        + System.lineSeparator();
            }
        });

        LOG.addHandler(console);
        try {
            Instant t = Instant.parse("2026-11-09T03:15:30.123Z");

            emit(Level.INFO, t, "event=created orderId=ord-7");
            emit(Level.WARNING, t.plusMillis(1),
                    "input=\"bad\"\nnext-line");
            emit(Level.SEVERE, t.plusMillis(2),
                    "event=checkout_failed");
            emit(Level.FINE, t.plusMillis(3),
                    "event=debug_hidden");
        } finally {
            LOG.removeHandler(console);
            console.close();
        }

        System.out.println("done=true");
    }
}
```

Compile and run with JDK 17+:

```bash
javac -encoding UTF-8 JsonLevelDemo.java
java JsonLevelDemo
```

**JSON lines written by the program to `stderr`:**

```json
{"timestamp":"2026-11-09T03:15:30.123Z","level":"INFO","original_level":"INFO","logger":"JsonLevelDemo","message":"event=created orderId=ord-7"}
{"timestamp":"2026-11-09T03:15:30.124Z","level":"WARN","original_level":"WARNING","logger":"JsonLevelDemo","message":"input=\"bad\"\nnext-line"}
{"timestamp":"2026-11-09T03:15:30.125Z","level":"ERROR","original_level":"SEVERE","logger":"JsonLevelDemo","message":"event=checkout_failed"}
```

On the second line, `\\\"` and `\\n` are **escape sequences inside the JSON string**; they do not create a second JSON record. The `emit(Level.FINE,...)` call produces no output because it is filtered by the INFO threshold.

**`stdout` explicitly written by the program:**

```text
done=true
```

JUL `ConsoleHandler` writes logs to **stderr**; `System.out.println` uses stdout. When a terminal merges both streams, strict interleaving order is not guaranteed, but the three JSON records above are written in the order of the `emit` calls in this synchronous example.

### Analyzing the output

1. `INFO` remains `INFO` after normalization.
2. JUL's `WARNING` becomes `WARN` in the `level` field, while `original_level` preserves `WARNING`.
3. `SEVERE` becomes `ERROR` so services sharing a common schema can query by `level=ERROR`.
4. `LOG.setLevel(INFO)` and `console.setLevel(INFO)` both affect whether an event is written. `FINE` is dropped before the formatter.
5. `record.getInstant()` is the timestamp attached to the `LogRecord`; formatting from this field does not re-read the system clock when the encoder runs.
6. `jsonString` escapes messages containing double quotes and newlines, preserving **one event = one JSON line** in the example case.
7. `LOG.setUseParentHandlers(false)` prevents parent handlers from writing extra differently formatted output; in a real application you must follow the overall logging architecture and not disable propagation arbitrarily.

**Limitations of the demo JSON serializer:** The `jsonString` method handles common control characters and `U+0000` through `U+001F`, but it does not check every malformed Unicode case (such as isolated surrogates), message size limits, sensitive content, arbitrary data types, or complex field types. If messages come from requests or untrusted sources, production needs an **official JSON serializer, redaction, byte limits, schema validation, and collector testing**. Do not log entire request bodies or tokens just because the encoder has escaping.

## 7. Using SLF4J, Logback, and Log4j 2 in Real Applications

For applications already using SLF4J or Log4j 2, you usually **do not need to write your own formatter** like in the demo. Use a provider/backend and encoder that support structured logging matching your version and desired schema.

### SLF4J 2.x

```java
// Fragment in a class with org.slf4j.Logger LOG.
LOG.atWarn()
   .addKeyValue("event", "inventory_retry")
   .addKeyValue("attempt", 2)
   .log("Inventory temporarily unavailable");
```

This is the fluent API of **SLF4J 2.x**; it does not run standalone with the JDK. `atWarn()` selects the WARN level, and `addKeyValue` attaches key-value pairs to the logging event according to the API/provider's capabilities. **Whether key-value pairs appear as real JSON fields or only inside text depends on the encoder/backend**. Do not infer from this call that the provider serializes every field into a JSON schema by default.

The `Logger` object must come from the SLF4J API, and the runtime needs a compatible provider. In environments using Logback or Log4j Core, choose a JSON encoder/layout matching your version and verify the actual output.

### Logback

In Logback, `level` typically comes from Logback classic's `ILoggingEvent`, handled by the API/provider. With an appropriate JSON encoder, it can be mapped to the `level` key:

```json
{"level":"WARN","logger":"com.example.InventoryService","message":"Retry scheduled"}
```

This is **illustrative output**, not a fixed default for every Logback version. Some encoders choose `level`, `level_value`, `severity`, or add other metadata; you need to inspect the schema. **`level_value`** (if present) is an internal backend number, not automatically identical to OpenTelemetry `SeverityNumber`.

With Spring Boot using the default Logback backend, level policies can be tuned via `logging.level.root`, `logging.level.com.example`, and Boot's configuration mechanisms; however, **enabling JSON output** requires an encoder/layout/integration supported by the framework version. A `logback-spring.xml` file helps configure Logback with Spring extensions, and does not guarantee JSON format by itself unless a corresponding encoder is configured.

### Log4j 2

Log4j 2 has the `Log4j API`, Log4j Core, and version-specific JSON layouts/encoders. The level field typically comes from **`LogEvent.getLevel()`** or the backend equivalent; custom levels may exist:

```json
{"level":"ERROR","logger":"com.example.PaymentService","message":"Gateway timeout"}
```

This is also illustrative JSON. If you use JSON Template Layout, you must configure the field resolver, key names, and field positions according to your schema; do not assume every Log4j layout emits `level` as an uppercase string. Do not copy Logback's `<encoder>` into Log4j 2 XML or confuse `log4j-to-slf4j` with the `log4j-slf4j2-impl` provider.

**Principle:** `level` must be taken from **log event metadata**, not parsed from text messages with regex, and the serializer must output the exact field and type agreed upon with the collector.

## 8. Filtering by the `level` Field in JSON Lines

A common setup is **one log event = one JSON object per line** (JSON Lines/NDJSON). You can then use a JSON parser instead of searching for the string `ERROR` across the entire message.

With the `jq` tool (installed separately, not included in the JDK) and a file `app.jsonl` containing one JSON object per line:

```bash
jq -c 'select(.level == "ERROR")' app.jsonl
```

This command filters objects whose `level` field is exactly the string `ERROR` (case-sensitive). It does not select an `INFO` record just because its message contains the word ERROR. Counting records by level:

```bash
jq -r '.level // "UNKNOWN"' app.jsonl | sort | uniq -c
```

This command is an **illustrative tool on Unix-like environments**, not Java code. It assumes each line is valid JSON and `.level` is a string or null; if the value is a number or object, the aggregation needs schema checks. For logging systems with millions of events, querying a log storage/collector with a properly indexed field is usually more efficient than downloading the entire file in a terminal.

### Filtering in a Java application using a JSON parser

If a service needs to ingest JSON logs from another system, you can use Jackson (an external dependency outside the JDK), a suitable JSON parser, and schema validation. Do not call `split(",")` or use regex just to read JSON:

```json
{"level":"INFO","message":"ERROR was retried, then recovered"}
```

Splitting by commas or searching for the literal `ERROR` across the entire line can miscount or break fields that contain commas in `message`. A **JSON parser** must identify `level` by the proper key and type; the collector should handle invalid records, missing keys, or schema mismatches without crashing the entire pipeline.

### Results depend on field indexing

If a dashboard cannot find `ERROR` events, check:

1. Did the logger actually emit the event at the ERROR level?
2. Did the backend/provider filter the event before the encoder?
3. Did the encoder emit `level` as a string?
4. Did the collector rename/drop/map `level` elsewhere, such as `log.level` or `SeverityText`?
5. Does the storage have an index/mapping with the right keyword/string type?
6. Does the dashboard/query use the exact field name and case-sensitive condition?
7. Was **event time** confused with ingestion time, resulting in selecting the wrong time range?

Do not increase retention expecting to find an event that was filtered before being written; and do not alter messages just to make a parser detect the right level.

## 9. Choosing `level` in Real-World Scenarios

Suppose an application logs JSON for an order-processing flow:

```json
{"level":"INFO","event":"request_received","requestId":"req-17","route":"/orders/{id}"}
{"level":"DEBUG","event":"discount_rule_applied","requestId":"req-17","rule":"seasonal"}
{"level":"WARN","event":"inventory_retry","requestId":"req-17","attempt":1}
{"level":"INFO","event":"order_completed","requestId":"req-17","durationMs":128}
```

This is **an illustrative scenario**; in a production environment with an INFO threshold, the DEBUG event may not appear. If the retry succeeds, you should not automatically tag the entire request as `ERROR` just because a retry step occurred. Conversely, when retries are exhausted and the request ultimately fails, the system can log an `ERROR` event with the error code, dependency, and `Throwable`.

Some evaluation guidelines:

- **`TRACE`/`DEBUG`:** store only what helps investigation; do not log every parameter, body, password, or token.
- **`INFO`:** notable operational milestones; avoid creating an INFO log for every tiny operation under high traffic.
- **`WARN`:** events worth noticing where the application continues or has a recovery mechanism; short-lived retries are not necessarily final errors.
- **`ERROR`:** failed operations or unexpected issues needing investigation; include `Throwable` and `errorCode` when appropriate.
- **`FATAL`:** use only when the logging framework and organizational convention support this level; do not assume `FATAL` means the JVM will definitely exit.
- **Audit/security events:** may have separate policies for completeness, retention, and alerting; do not inadvertently apply level-based sampling/filtering that loses required evidence.

`level` reflects **the severity of the event**, and does not directly determine the owner, ticket priority, or system-wide incident severity. Alerting decisions should combine `errorCode`, rate, service, route, impacted users, and SLOs, rather than only matching `level="ERROR"`.

## 10. Limiting Cardinality, Field Pollution, and Untrusted Data

`level` should belong to a **small, stable set of values**. Practices to avoid:

```json
{"level":"ERROR-request-92742"}
```

```json
{"level":"Failed for customer 123"}
```

Creating a per-request or per-user level value increases cardinality, makes grouping/aggregation difficult, and mixes business data into technical metadata. With structured logging:

```json
{"level":"ERROR","event":"checkout_failed","requestId":"req-17","errorCode":"UPSTREAM_TIMEOUT"}
```

This is a more controllable way to separate information. However, `requestId` or other fields may still be data that require appropriate access control and retention.

### Log injection and JSON escaping

If input contains newlines or double quotes, the encoder must escape them properly:

```json
{"level":"WARN","message":"client sent: \"bad\"\nvalidation failed"}
```

The line above is **a single JSON object**, where `\\n` is the literal backslash + `n` in the JSON text rather than a physical newline. If you concatenate JSON manually with user-supplied strings without escaping, it can produce invalid JSON, split records, or attempt to spoof the `level` field.

Do not take the level from a client-supplied field such as `X-Log-Level: ERROR` and trust that the event is ERROR. Severity must be set by **an authorized application/observability system** according to policy. Do not let users arbitrarily change logger configurations or choose levels to cause log spam.

Do not log tokens, session cookies, passwords, `Authorization` headers, or sensitive personal payloads. A JSON serializer only solves encoding; **it does not solve redaction or access control**.

## 11. Migrating from Text Logging to JSON Logging

When migrating a Java system from text to structured JSON, you need a plan for the `level` field so existing dashboards do not break.

**Step 1 — Inventory sources:** identify which JUL, SLF4J, Logback, Log4j 2, and bridges the application uses. Which backend's level is the source of truth for an event?

**Step 2 — Define the schema:** choose `level` as an uppercase string or follow ECS/OTel field conventions. If renaming to `severity`, `severity_text`, or `log.level`, document the mapping explicitly.

**Step 3 — Decide on original values:** will you keep `original_level`? For example, JUL `WARNING` is normalized to `WARN`. For custom `Level` values, choose a policy instead of forcing them to `ERROR` without knowing their meaning.

**Step 4 — Configure the serializer:** the formatter/encoder must read `Level` from the event; write **one JSON object per line** if the collector expects JSON Lines, and keep `Throwable`/stack traces in structured data.

**Step 5 — Configure collector/index:** choose the right field and type. When old and new schemas coexist, avoid having the same key be a string in some records and a number in others within one index.

**Step 6 — End-to-end testing:** emit INFO, WARN, and ERROR; one enabled DEBUG and one disabled DEBUG; verify the events, types, casing, counts, timestamps, and index.

**Step 7 — Review alerts and retention:** alerts should no longer rely on text regex once the field exists; review error rates, dropped events, and cardinality impact before and after migration.

Do not simply swap the formatter and consider the JSON migration finished. **The contract must be verified at the actual output of the collector and dashboard**, especially when multiple languages/libraries send logs together.

## 12. Common Mistakes with the `level` Field

| Symptom | Possible cause | Fix |
| --- | --- | --- |
| Some places log `WARN`, others log `WARNING` | JUL and SLF4J do not use the same names | Normalize values; keep the original level if needed |
| `level` is sometimes a string, sometimes a number | Inconsistent schema/encoder | Pick one type; map numbers separately, avoid type conflicts |
| DEBUG does not appear even though JSON encoder has `level` | Backend filtered the event beforehand | Check logger threshold and handler/appender filters |
| INFO event with `ERROR` in `message` is miscounted | Dashboard searches text instead of the JSON field | Query specifically on `level` or `log.level` |
| Collector shows `severity_text` without `level` | OTel mapping renamed the field | Check pipeline mapping/schema |
| `level=1000` is treated as standard ERROR | Confused JUL `intValue` with `SeverityNumber` | Apply standard mapping; do not use raw JUL numbers |
| `FATAL` is not supported by the framework | Source API has no FATAL | Use a supported level or map per policy |
| `original_level` differs from `level` | Normalized from WARNING → WARN | Distinguish raw vs. normalized names; this may be expected |
| One exception is logged as multiple ERRORs | Multiple layers log and rethrow | Define one place to log errors fully, keeping cause and correlation |
| JSON cannot be found in the index | Backend emitted text or collector parsing failed | Verify decoder/schema from raw output |
| Stack trace splits into multiple events | Multiline text encoder / line-based collector parsing | Compact JSON, escape newlines, or configure multiline handling |
| Events are missing under high traffic | Rate limiting, async queue drop, ingest quota | Monitor drop metrics and queue policies |
| Custom level turns into `ERROR` without justification | Normalizer has an overly broad fallback | Preserve original value or flag unmapped per policy |
| JSON has the `level` key twice | Manual concatenation / uncontrolled object merge | Use a serializer/schema validation; avoid duplicate keys |
| Severity rises but alerts do not fire | Wrong field/casing in query, sampling, or routing | Check pipeline, thresholds, and alert rules |
| Sensitive data appears in JSON | Entire object/request passed to encoder | Apply allowlists/redaction and appropriate retention |

**Note on duplicate keys:** A JSON object containing two different `level` keys may be handled inconsistently by parsers; avoid emitting output like `{"level":"INFO","level":"ERROR"}`. The severity field needs **a single source of truth** so queries and alerts are unambiguous.

## 13. Pre-Production Verification Checklist for the `level` Field

1. **Field name:** `level` or `log.level`/`SeverityText`? Are the contract and pipeline mapping clear?
2. **Type:** JSON string or numeric severity standardized under a specific model?
3. **Valid values:** Do `TRACE`, `DEBUG`, `INFO`, `WARN`, `ERROR`, and `FATAL` (if present) have consistent casing?
4. **Level source:** Is the value taken from backend event metadata, not regex on `message` or client headers?
5. **API mapping:** Are JUL `WARNING`/`SEVERE`, SLF4J `WARN`/`ERROR`, and Log4j custom levels handled per policy?
6. **Original value:** When normalizing, is `original_level` or `SeverityText` preserved with accurate semantics if needed?
7. **Filtering:** Test both disabled and enabled levels; do not confuse having the field with the event being emitted?
8. **One event/one record:** Does the JSON encoder properly escape newlines, quotes, backslashes, and `Throwable`?
9. **Sensitive data:** Are `message`, MDC, and HTTP fields filtered; is user input prevented from overriding `level`?
10. **Collector/storage:** Are the field and type indexed properly, and are dashboards and alerts unaffected by unintended changes?
11. **Quality observability:** Are level counts, log volume, drop metrics, null/unmapped field rates, and duplicate rates tracked?
12. **Schema migration:** Is there versioning, mapping documentation, and testing with other backends/languages?
13. **Operations:** ERROR does not automatically mean a system-wide critical incident; alerts should tie to business signals, SLOs, and error rates.

**Conclusion:** The `level` field in JSON logging represents **the severity of each log event as structured data**. Choose a stable type and value set, map carefully from the source logging API, preserve raw severity when needed, and do not confuse it with logger thresholds or `SeverityNumber` values from a different standard. When the backend, encoder, and collector all respect the contract, searching, counting, and alerting by level will be far more accurate than parsing free-form text strings.

## References

- Oracle Java 17 — `LogRecord`: https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/LogRecord.html
- Oracle Java 17 — `java.util.logging.Level`: https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Level.html
- OpenTelemetry — Logs Data Model (SeverityText/SeverityNumber): https://opentelemetry.io/docs/specs/otel/logs/data-model/
- Elastic — ECS Log Fields (log.level): https://www.elastic.co/docs/reference/ecs/ecs-log
- SLF4J Manual: https://www.slf4j.org/manual.html
- Logback Architecture: https://logback.qos.ch/manual/architecture.html
- Apache Log4j 2 — Log levels: https://logging.apache.org/log4j/2.x/manual/customloglevels.html
