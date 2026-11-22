# Unstable Format Dependencies in Java Core Logging

## Learning Objectives

This lesson belongs to the **Logging Anti-patterns** group, topic **Unstable Format Dependencies**. A Java system can log everything properly, yet monitoring, alerts, dashboards, or investigation workflows still break if downstream components **depend on how log lines are rendered**. Changing a message sentence, adding a trace ID to a pattern, changing locale/timezone, switching from text to JSON, or upgrading the logging backend version can break log parsers without the application reporting any error.

After this lesson, you will be able to:

- Distinguish **event meaning**, **message template**, **formatted message**, **logging event**, **structured fields**, and **encoder/layout**.
- Identify anti-patterns that rely on token positions, text regex, exception strings, stack trace/line numbers, locale timestamps, thread names, and JSON field order.
- Define event codes, error codes, field types, timestamp semantics, schema versions, and compatibility rules.
- Understand how JUL, SLF4J, Logback, Log4j 2, and log collectors handle fields, without assuming metadata at the source always reaches the backend.
- Run a standalone Java 17 demo proving a wording-based classifier misses an event even when structured metadata still describes the same error.
- Design v1/v2 migrations, consumer contract tests, canaries, and monitoring for format drift.
- Prevent format changes from causing log injection, secret leaks, lost audits/alerts, or duplicate event counts.

**Core principle:** Human-readable messages are allowed to change. Machine consumers must rely on **structured, versioned, and tested data contracts**, rather than turning presentation formats into implicit APIs.

## 1. A Small Change Can Break Alerts

Initially, the app logs:

```text
2026-11-10 09:00:00 ERROR [checkout] Order failed: order-42
```

An alerting system applies the rule:

```text
line contains "ERROR [checkout] Order failed:"
```

When the Java team switches to structured JSON, the event becomes:

```json
{
  "timestamp": "2026-11-10T02:00:00Z",
  "level": "ERROR",
  "service": "checkout",
  "event_code": "order.processing_failed",
  "order_id": "order-42",
  "error_code": "DOWNSTREAM_TIMEOUT",
  "message": "Payment provider timed out"
}
```

From a business perspective, the error still exists. However, the old alert stops matching because the layout and wording changed. The dashboard might display "0 errors" while HTTP 5xx responses and business metrics continue to rise.

**The design flaw is not JSON.** A downstream component depended on the text layout without a schema contract, tests, or migration.

Changes that commonly cause format drift:

1. Adding `trace_id`, `span_id`, MDC, thread name, or markers to the prefix.
2. Switching from text PatternLayout to a JSON encoder, or renaming structured fields.
3. Upgrading JDK/Logback/Log4j 2, or replacing the backend or log shipper.
4. Changing wording from English to Vietnamese, or changing exception names.
5. Changing timezone, Locale, date precision, or daylight-saving display.
6. Adding cause/suppressed exceptions that make stack traces long or multiline.
7. Log collectors changing how nested JSON is flattened, fields are renamed, or events are filtered.
8. Switching sources between stdout/file/HTTP, changing framing and serialization.
9. Multi-instance rollouts causing v1 and v2 to coexist.
10. Security redaction altering message content, causing regex parsers to stop matching.

Some changes are necessary and beneficial. We need to **protect consumers from wrong dependencies**, not freeze every format forever.

## 2. What Is the Data Contract vs. Mere Presentation?

A common logging pipeline:

```text
Java application
  |
  +-- event meaning / code / attributes / exception / context
  |
  v
JUL LogRecord / SLF4J event / Log4j 2 LogEvent
  |
  +-- effective level, filters, sampling, routing
  |
  v
Formatter / Encoder / Layout
  |
  +-- text pattern, JSON, XML, binary representation
  |
  v
file / stdout / network appender
  |
  v
agent / collector (parse, transform, enrich, filter)
  |
  v
index / search / dashboard / alert
```

You need to distinguish:

| Component | Role | Should it be a stable semantic key? |
| --- | --- | --- |
| `event_code` | Identifier for the event type, e.g., `order.processing_failed` | Yes, per contract |
| `error_code` | Error category, e.g., `DOWNSTREAM_TIMEOUT` | Yes, per defined enum |
| `message template` | `"Order {} failed"` | Not by default |
| `formatted message` | `"Order order-42 failed"` | No, usually for human readers |
| `logger name` | Package/class calling the logger | Not as a business ID |
| `thread name` | Thread handling the work at a point in time | Not as an operation ID |
| `exception message` | Diagnostic details from libraries/application | Not as a stable error code |
| `stack trace` | Call frames/cause/suppressed | Do not parse as a business protocol |
| `trace_id` | Cross-service correlation | Yes per trace protocol, but not a unique event ID |
| `timestamp` | Event/ingest time per schema | Yes if semantics/timezone/precision are clear |
| `schema_version` | Selects how to interpret fields | Yes |

Having structured fields at the source is not enough: the layout/encoder must serialize them, the collector must parse them accurately, the index must preserve the right types, and dashboards must query the right names.

**Structured logging can also be unstable** if teams arbitrarily rename `duration_ms` to `duration` or change a number to a string. JSON is a representation format, not a substitute for schema governance.

## 3. Anti-pattern: Splitting Logs by Position

```java
// Anti-pattern, not a reliable way to parse production logs.
String[] tokens = line.split(" ");
String severity = tokens[2];
String owner = tokens[3];
```

If the pattern changes from `timestamp level logger message` to `timestamp trace_id level thread logger message`, token positions shift. Spaces inside timestamps or messages, newlines in exceptions, and delimiters in input make splitting even more error-prone.

**Instead:** use structured fields with keys and types. If processing legacy text is unavoidable, you need a versioned grammar, quoting/escaping, malformed input tests, and parse error metrics; never silently return fake data when the parser breaks.

| Fragile parsing approach | Change that breaks it |
| --- | --- |
| `line.split(" ")[2]` | Adding a field to the prefix |
| `contains("Order failed")` | Translating or rewording the message |
| `substring(indexOf("user="))` | User value contains the delimiter |
| `split(",")` | Message contains commas or CSV quoting |
| `grep "ERROR"` | JUL uses `SEVERE` or text contains ERROR |
| `split("\n")` | Stack trace spans multiple lines |
| Exact timestamp regex | Timezone/locale/precision changes |
| Stack frame regex | Class/file/line refactoring |

## 4. Anti-pattern: Depending on Message Wording

An error can be phrased as:

```text
Order failed: order-42
Đơn hàng order-42 xử lý thất bại
Payment provider did not answer in time
```

If monitoring only searches for `"Order failed:"`, the latter two sentences are missed. Language/copywriting is not an event identifier.

Stable model:

```text
event_code=order.processing_failed
order_id=order-42
error_code=DOWNSTREAM_TIMEOUT
```

Wording can still be improved. **Keep the event code unchanged when the meaning is unchanged**, and change the code/version when the semantics truly change.

Event identifiers should:

- Be namespaced by domain: `auth.access_denied`, `payment.authorization_failed`.
- Not contain dynamic IDs; `order.failed.order-42` causes high cardinality.
- Not rely on class/method names that will change during refactoring.
- Distinguish `attempted`, `accepted`, `committed`, `rolled_back`, and `unknown`.
- Have an owner, documentation, retention, and a versioning/deprecation policy.
- Not use `exception.getMessage()` as an enum error code.

A `TimeoutException` can occur when the remote service already performed the side effect but the client did not receive the response. The log should describe a **timeout/UNKNOWN outcome**, rather than inferring from the exception string that the business operation definitely failed.

## 5. Anti-pattern: Using Stack Traces as an API

```text
java.lang.IllegalStateException: checkout failed
    at com.example.OrderService.process(OrderService.java:77)
Caused by: java.net.SocketTimeoutException: remote timeout
    at com.example.Client.call(Client.java:135)
    Suppressed: java.io.IOException: cleanup failed
```

Line numbers, package names, call frames, wrapping, and frame abbreviation can change after refactoring, JDK updates, or library implementation changes. A regex matching `"OrderService.java:77"` is unstable for error classification.

Instead:

- `event_code` for the event.
- `error_code` for the error category.
- `exception_type`, `cause_type`, or cause fields per schema.
- `stack_trace` for diagnostics, which may be truncated/redacted.
- `trace_id`/`operation_id` to correlate the flow.

Test Throwable/cause/suppressed via APIs at the model layer first, then test the serializer layout separately. Do not force full stack trace formatting to become a golden string when it is not a public contract.

### Multiline

A stack trace can have hundreds of lines. Line-oriented shippers may split one exception into hundreds of events, whereas valid NDJSON typically encodes newlines inside a string. When changing formats, update the multiline parser and verify the **logical event count** at the backend, not just whether the source printed the exception.

## 6. Anti-pattern: Ambiguous Timestamps and Locales

Two formats:

```text
10/11/2026 09:30:00
2026-11-10T02:30:00Z
```

If the first line uses Vietnam time and the corresponding day/month order, they may represent the same instant; however, the first line **carries no offset/timezone**. `10/11` can also be interpreted with a different day/month order.

In Java:

- `Instant` represents a point on the UTC timeline.
- `OffsetDateTime` includes an offset.
- `ZonedDateTime` includes a zone, suitable for display/calendar logic.
- `LocalDateTime` has no offset/zone and is insufficient as a global event timestamp.
- `System.nanoTime()` is for measuring elapsed duration, not recording epoch timestamps across hosts.

Java 17 integration snippet:

```java
import java.time.Clock;
import java.time.Instant;

Clock clock = Clock.systemUTC();
Instant occurredAt = Instant.now(clock);
String eventTimestamp = occurredAt.toString();
```

This is a snippet, not a standalone runnable class. The schema must distinguish `event_timestamp` from `observed_timestamp`/ingest timestamp. If an upgrade changes the meaning of `timestamp` from when the event occurred to when the collector received it, that is a **semantic breaking change** even if both are ISO-8601.

Clock skew between hosts can make timestamps appear out of order; business ordering may require aggregate versions/sequences rather than sorting by timestamp alone.

## 7. Anti-pattern: Parsers Depending on Severity Text

JUL has `Level.SEVERE` and `Level.WARNING`; SLF4J/Logback typically use `ERROR` and `WARN`. If a parser only accepts `ERROR`, it can miss JUL `SEVERE` after a bridge/backend change.

**Solution:** Normalize severity according to a published and tested mapping. Distinguish raw source severity from the canonical `severity` field if the pipeline has multiple backends. Do not parse by searching for the token `ERROR` in the message: an INFO message can also contain the word "ERROR".

Logger name, thread name, hostname, stack frames, and version-specific placeholders are all useful metadata, but they do not by themselves establish the identity of a business operation.

## 8. Designing a Structured Logging Contract

A sample event:

```json
{
  "schema_version": 1,
  "timestamp": "2026-11-10T02:30:00Z",
  "level": "ERROR",
  "service": "checkout",
  "event_code": "order.processing_failed",
  "order_id": "order-42",
  "error_code": "DOWNSTREAM_TIMEOUT",
  "retry_count": 2,
  "duration_ms": 350,
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "message": "Payment provider did not answer in time"
}
```

This is **illustrative JSON proposed by the lesson**; it is not the default output of JUL/Logback/Log4j 2.

| Field | What the contract should define | Anti-pattern |
| --- | --- | --- |
| `schema_version` | Schema version | Breaking field changes without versioning |
| `timestamp` | Clear instant/offset, required precision | Converting to a local date string |
| `level` | Canonical enum | Mixing `WARN`/`WARNING` without mapping |
| `event_code` | Stable meaning | Changing with wording/copywriting |
| `order_id` | String, preserving leading zeros | Coercing to a number |
| `error_code` | Low-cardinality enum | Raw `exception.getMessage()` |
| `retry_count` | Number, defined count of attempts/retries | String `"two"` |
| `duration_ms` | Number in milliseconds | String `"350ms"` |
| `trace_id` | Correlation, with nullability policy | Using as a unique event ID |
| `message` | Text for human readers | Machine parsers depending on sentence wording |

### Types, Nullability, Versioning

These JSON types differ:

```json
{"duration_ms": 250, "retryable": true, "order_id": "00042"}
```

and:

```json
{"duration_ms": "250ms", "retryable": "yes", "order_id": 42}
```

They are incompatible with downstream latency calculations, boolean filtering, and IDs with leading zeros. **Changing types or units is usually a breaking change.**

The three states below can also have different meanings:

```json
{"trace_id": null}
```

```json
{"trace_id": ""}
```

```json
{}
```

Consumers must know required/optional fields, nullability, and fallbacks. Adding an optional field can be compatible if consumers ignore unknown fields; removing a required field or renaming/changing semantics requires migration. Adding an enum value can also break consumers that use exhaustive matching.

### Nested and Flattened Fields

```json
{"error": {"code": "DOWNSTREAM_TIMEOUT"}}
```

and:

```json
{"error.code": "DOWNSTREAM_TIMEOUT"}
```

are two representations that must be agreed upon. One backend treats dots as nested paths; another may treat them as literal keys. Do not assume both query the same way.

**JSON object key order is not a stable contract.** Test by field name and type, not by key order in the raw string.

## 9. Standalone Java 17: Message Changes, Event Code Stays Constant

This example uses **only JDK 17+ and `java.util.logging`**, requiring no SLF4J, Logback, Maven, or collector. Two log records have the same error type and metadata, but their formatted messages are in different languages. The English-text filter matches only 1/2; the counter reading `EventData.eventCode` matches 2/2.

**Limitation:** `LogRecord.getParameters()` lets you attach parameters, but the default Formatter/Handler **does not automatically guarantee** serializing objects into structured JSON. In the example, an in-memory Handler reads the parameters. In production, querying `event_code` in the backend requires a properly configured formatter/exporter and integration tests.

Create **`LogFormatContractDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class LogFormatContractDemo {
    record EventData(int schemaVersion,
                     String eventCode,
                     String orderId,
                     String errorCode) {
    }

    static final class CaptureHandler extends Handler {
        private final List<LogRecord> records = new ArrayList<>();

        CaptureHandler() {
            setLevel(Level.ALL);
        }

        @Override
        public void publish(LogRecord record) {
            if (isLoggable(record)) {
                records.add(record);
            }
        }

        @Override
        public void flush() {
        }

        @Override
        public void close() {
        }

        List<LogRecord> snapshot() {
            return List.copyOf(records);
        }
    }

    static EventData dataOf(LogRecord record) {
        Object[] parameters = record.getParameters();
        if (parameters == null || parameters.length != 1
                || !(parameters[0] instanceof EventData data)) {
            throw new IllegalStateException(
                    "Missing structured EventData");
        }
        return data;
    }

    static void require(boolean condition, String label) {
        if (!condition) {
            throw new IllegalStateException(
                    "Assertion failed: " + label);
        }
    }

    public static void main(String[] args) {
        Logger logger = Logger.getLogger(
                "demo.logging.format.contract");
        logger.setUseParentHandlers(false);
        logger.setLevel(Level.ALL);

        CaptureHandler capture = new CaptureHandler();
        logger.addHandler(capture);

        EventData stable = new EventData(
                1,
                "order.processing_failed",
                "order-42",
                "DOWNSTREAM_TIMEOUT");

        try {
            logger.log(Level.WARNING,
                    "Order failed: order-42", stable);
            logger.log(Level.WARNING,
                    "Đơn hàng order-42 xử lý thất bại", stable);

            List<LogRecord> actual = capture.snapshot();
            require(actual.size() == 2, "record count");

            int fragileTextMatches = 0;
            int stableCodeMatches = 0;

            for (LogRecord record : actual) {
                require(record.getLevel() == Level.WARNING,
                        "warning level");
                if (record.getMessage().startsWith("Order failed:")) {
                    fragileTextMatches++;
                }

                EventData data = dataOf(record);
                require(data.schemaVersion() == 1,
                        "schema version");
                require("order-42".equals(data.orderId()),
                        "order ID");
                require("DOWNSTREAM_TIMEOUT".equals(data.errorCode()),
                        "error code");
                if ("order.processing_failed"
                        .equals(data.eventCode())) {
                    stableCodeMatches++;
                }
            }

            require(fragileTextMatches == 1, "fragile parser");
            require(stableCodeMatches == 2, "stable event code");

            System.out.println("log_records=" + actual.size());
            System.out.println("matched_by_english_text="
                    + fragileTextMatches);
            System.out.println("matched_by_event_code="
                    + stableCodeMatches);
            System.out.println("schema_version="
                    + stable.schemaVersion());
            System.out.println("stable_error_code="
                    + stable.errorCode());
            System.out.println("test=PASS");
        } finally {
            logger.removeHandler(capture);
            capture.close();
        }
    }
}
```

Compile and run:

```bash
javac LogFormatContractDemo.java
java LogFormatContractDemo
```

**Exact stdout:**

```text
log_records=2
matched_by_english_text=1
matched_by_event_code=2
schema_version=1
stable_error_code=DOWNSTREAM_TIMEOUT
test=PASS
```

### Why Is This Result Correct?

1. The Logger and Handler use `Level.ALL`, allowing both WARNING records.
2. The `Logger.log(Level, String, Object)` overload creates a `LogRecord` whose parameters array contains the `EventData` object.
3. The first message has the prefix `Order failed:`; the second does not, so the text classifier matches only one event.
4. Both records have `eventCode` equal to `order.processing_failed`, so the semantic classifier matches both.
5. `setUseParentHandlers(false)` prevents JUL parent handlers from printing warnings to stderr; stdout has only the six lines from the program.
6. Assertions verify the level, schema version, ID, and error code. Only after passing all checks does it print `test=PASS`.
7. `CaptureHandler` uses `ArrayList` because this is a single-threaded demo; a real concurrent Handler needs appropriate synchronization/collections.
8. This is only an **in-memory test**; it does not prove JSON output, collector ingestion, or index durability.

**Try modifying it:** Change the English sentence to another phrasing; the text filter changes, while the event code can stay the same if the semantics are identical. Changing one record's code to another value will cause the stable count assertion to fail. If you suppress WARNING by setting the logger level to SEVERE, both disappear; structured data does not bypass filters on its own.

## 10. SLF4J 2.x and Logback: Metadata Needs an Encoder

SLF4J 2.x supports fluent key-value pairs:

```java
// SLF4J 2.x integration snippet, requires a logger and backend.
logger.atWarn()
      .addKeyValue("event_code", "order.processing_failed")
      .addKeyValue("order_id", "order-42")
      .addKeyValue("error_code", "DOWNSTREAM_TIMEOUT")
      .log("Payment provider did not answer in time");
```

Attributes attached to a logging event do **not automatically** appear as JSON fields in every layout. For example, an appender with only `%msg%n` may not print them. You must configure an encoder that outputs the fields properly and write integration tests against the raw output.

### MDC

```java
// SLF4J snippet, requires an existing logger and traceId.
try (org.slf4j.MDC.MDCCloseable scope =
             org.slf4j.MDC.putCloseable("trace_id", traceId)) {
    logger.warn("event_code={} error_code={}",
            "order.processing_failed", "DOWNSTREAM_TIMEOUT");
}
```

MDC is useful for correlation, but it does not automatically propagate across all executors or `CompletableFuture`s. With thread pool reuse, you must clean up/restore it to avoid attaching the previous request's trace ID. Never put passwords, bearer tokens, or raw payloads into MDC. If a new encoder automatically exports the entire MDC, it may expose information that was previously not printed: **format migrations must include security checks**.

A message template like `"retry_count={}"` does not guarantee that the JSON field `retry_count` is a number. Use a structured encoder with typed fields when consumers need to perform calculations.

## 11. Logback PatternLayout Easily Breaks Legacy Regex

Old text pattern:

```xml
<encoder>
    <pattern>%d{yyyy-MM-dd HH:mm:ss.SSS} %-5level [%thread] %logger - %msg%n</pattern>
</encoder>
```

New pattern:

```xml
<encoder>
    <pattern>%d{yyyy-MM-dd'T'HH:mm:ss.SSSXXX} %-5level trace=%X{trace_id} %logger - %msg%n</pattern>
</encoder>
```

This is an **XML encoder snippet**, not a complete `logback.xml` file. When deploying, check the version, timezone, appender, status, and effective config.

A parser fixed on the order `TIMESTAMP LEVEL [THREAD] LOGGER - MESSAGE` will fail when the thread is removed or a trace ID is inserted. Multiple pods running v1/v2 simultaneously can also emit both formats interleaved during a rolling deployment.

If raw text is a **mandatory wire contract**, do not edit the pattern arbitrarily: version it, document the grammar, handle escaping, write contract tests, and plan a rollout and deprecation window. If text is only for human readers, migrate consumers to structured fields.

### Log4j 2 Differs from Logback

Log4j 2 has PatternLayout and structured layouts; its API and config are not identical to Logback's. Do not copy Logback tokens/XML into Log4j 2 without testing. Pay attention to severity mapping (JUL `WARNING/SEVERE` vs. SLF4J `WARN/ERROR`) and whether exceptions, markers, and MDC are serialized.

## 12. What Other Risks Exist When Moving from Text → JSON?

### JSON Escaping

```java
// Anti-pattern: concatenating JSON with raw input.
String json = "{\"user\":\"" + userInput + "\"}";
```

When `userInput` contains quotes, newlines, backslashes, or control characters, the output can become invalid or cause log injection. Use a proper encoder/serializer and test Unicode, quotes, CR/LF, record size, and truncation.

### NDJSON and Multiline

A structured JSON log can contain a multiline stack trace inside **a single escaped JSON string field**. If a formatter pretty-prints the object across multiple lines while the shipper still reads line by line, it can break record framing. You must test whether one logical event produces exactly one structured record in the sink/index.

### Nested vs. Flattened

```json
{"error": {"code": "DOWNSTREAM_TIMEOUT"}}
```

Differs from:

```json
{"error.code": "DOWNSTREAM_TIMEOUT"}
```

Backends may interpret dotted keys differently. Do not guess that query paths will remain the same when changing collectors/encoders.

### Do Not Test with Exact Raw Strings

JSON key order and whitespace should not be part of the contract. Parse JSON into an object and assert keys, types, and values. Only use golden raw snapshots when the raw byte layout itself is a published interface; otherwise, snapshots with timestamps, threads, and stack frames are often flaky.

## 13. Versioned Event Catalog

A catalog should define:

- Event codes and stable meanings; e.g., `order.processing_failed` differs from `order.processing_retried`.
- Schema version (per event family or stream).
- Required/optional attributes, types, nullability, and units.
- Timestamp source and precision.
- Severity mapping when using multiple logging backends.
- Exception type/cause/stack trace policy.
- Correlation IDs and the trust level of incoming headers.
- Masking/PII, retention, and read permissions by category.
- Owner, review, deprecation, migration, and rollback.

### Changes That Usually Require a New Version

| Change | Impact |
| --- | --- |
| Adding an optional field | Can be backward-compatible if consumers ignore unknown fields |
| Removing a required field | Breaking |
| Renaming `error_code` | Breaking for existing queries |
| `duration_ms` number → string | Type-breaking |
| milliseconds → seconds while keeping the old name | Semantically breaking |
| `timestamp` event-time → ingest-time | Meaning-breaking |
| Adding an enum value | Can break exhaustive consumers |
| Changing message wording while preserving semantics | Usually non-breaking if message is presentation-only |
| Adding an optional cause field | Usually compatible if policy allows |
| Changing route/tenant/retention | Can affect security/compliance; needs independent review |

Versioning does not solve everything automatically. Consumers must test supported versions; parsers must not silently map "unknown" to a wrong business value.

## 14. Controlled v1/v2 Migration

**Phase 1 — Inventory:** List parsers, alert rules, dashboards, SIEM detections, saved searches, batch exports, operator scripts, tests, and runbooks. A legacy consumer grepping logs may still be critical for incident response.

**Phase 2 — Contract:** Finalize event codes, schema versions, field types, nullability, timestamps, error/severity semantics, security, and owners.

**Phase 3 — Trial Emission:** Use staging to emit events through the real encoder; read output at stdout/file/collector, parse, validate, and check data minimization.

**Phase 4 — Dual-run:** When needed, allow v1 and v2 during a compatibility window. Separate indexes/routes or use event IDs to avoid double-counting; check security sinks as well.

**Phase 5 — Migrate Consumers:** Move alerts/dashboards/SIEM to structured fields instead of human text. Maintain fixtures for both v1/v2 and positive/negative tests.

**Phase 6 — Cutover:** Monitor parser rejections, index mapping errors, missing required fields, canaries, and event counts. Define a rollback path and account for data of both versions coexisting until retention expires.

**Phase 7 — Retire Legacy:** Only stop v1 after all required consumers have migrated and the migration window has closed.

Do not generate extra business events just to change formats. A single source event fanned out to two sinks can create **two representations**; you must define dedup/routing rules and not treat them as two business operations.

## 15. Contract Tests Instead of Fragile Snapshots

### Source Unit Tests

- Events have the correct `event_code`, `error_code`, and `outcome`.
- Required metadata is complete, with the right types and units.
- Exception cause/type is attached, not just the exception message.
- Dynamic IDs are not interpolated into the event code.
- Success does not emit a terminal error; rollback does not emit a committed success.
- Sensitive data is stripped/masked.
- Rewording messages does not break semantic assertions.

### Encoder Integration Tests

1. Attach a test appender/handler or test sink.
2. Emit known events, including a `Throwable` with cause and suppressed exceptions.
3. Read the **actual serialized output** and parse the JSON with the project's standard library.
4. Assert keys/types, timestamp, severity mapping, correlation, and redaction.
5. Test quotes, backslashes, newlines, Unicode, and oversized payloads.
6. Ensure output is not split across multiple lines outside policy.
7. Verify duplicates/routing and appender filters.
8. Test against the actual backend/framework versions used in production.

### Consumer Contract Fixtures

```text
v1 legacy input      -> parsed while supported
v2 structured input  -> schema-valid
malformed JSON       -> explicit parse error
missing required     -> visible validation failure
wrong numeric type   -> validation failure
unknown enum         -> documented fallback/version
newline injection    -> safe escaping
multiline exception  -> logical event count as expected
```

You do not have to reject unknown optional fields if the contract allows extensibility. However, a missing required field or wrong mapping must never silently return a default value that looks like success.

### End-to-End Tests

Emit a canary with a dedicated `event_id` through JVM → appender → shipper → collector → backend. Query **structured attributes** `event_code`/`error_code`/`schema_version`, and verify types, correct tenant, no duplicates, and no leaked secrets. Because the pipeline can be eventually consistent, use polling with a deadline, distinguishing **not emitted**, **not ingested**, **not searchable**, and **query error**.

## 16. Format Drift Testing Matrix

| Code | Scenario | Expectation |
| --- | --- | --- |
| F1 | Change message from English to Vietnamese | Event code stays unchanged |
| F2 | Add trace ID to text pattern | Structured query does not depend on token position |
| F3 | Change display timezone and locale | Machine timestamp remains unambiguous |
| F4 | Change time precision | Schema parser handles per version |
| F5 | Exception adds cause/suppressed | Exception type and error code remain accurate |
| F6 | Input contains quotes, commas, newlines | Valid JSON and no injection |
| F7 | Count/duration number becomes string | Validation detects breaking change |
| F8 | Optional field missing/null/empty | Follows nullability policy |
| F9 | Add outcome enum value | Consumer has compatibility handling |
| F10 | Rename event code | Contract test fails if not migrated |
| F11 | Rolling deploy v1/v2 | Alerts do not break or double-count |
| F12 | MDC trace ID missing/leak | Never attached to the wrong user/request |
| F13 | JUL SEVERE / SLF4J ERROR | Correct severity mapping |
| F14 | Nested vs. flattened JSON | Query understands the structure properly |
| F15 | Multiline stack trace | One logical exception event per policy |
| F16 | Encoder exports additional MDC fields | No tokens/PII leaked |
| F17 | Queue drop or sampling | Distinguish deliberate filtering from loss |
| F18 | Collector parser wrong without throwing | Semantic assertions catch it |
| F19 | JSON key order changes | Key-based parser does not break |
| F20 | Backfill/replay legacy logs | Preserves event time, version, ID, and dedup |

## 17. Monitoring Format Drift in Production

The hardest situation is **silent failure**: the application still logs, but the parser no longer produces the field the dashboard uses. Combine metrics and canaries:

| Suggested Metric | What it detects |
| --- | --- |
| `log_events_emitted_total` | How many events were emitted at source instrumentation |
| `log_events_ingested_total` | How many the collector received |
| `log_parse_failures_total` | Parser could not understand the input |
| `log_schema_validation_failures_total` | Wrong field/type/enum |
| `log_required_field_missing_total` | Missing event code/timestamp/service |
| `log_index_rejections_total` | Index mapping or validation rejection |
| `log_multiline_fragments_total` | One exception was split |
| `log_events_sampled_out_total` | Intentional sampling |
| `log_queue_dropped_total` | Unintended queue loss |
| `log_canary_missing_total` | Synthetic event did not reach the sink by the deadline |

**The names above are suggestions only**, not automatically present in every framework/distribution. Limit metric labels to service, environment, schema version, and error category; never use `message_id`, `trace_id`, `user_id`, or raw exception messages as labels.

Illustrative canary:

```json
{
  "schema_version": 1,
  "event_code": "logging.contract.canary",
  "event_id": "canary-20261110-001",
  "service": "checkout",
  "timestamp": "2026-11-10T02:30:00Z",
  "probe": true
}
```

An independent checker queries by field, not just `message contains "canary"`. If the event arrives with a wrong field type: **SCHEMA_FAILURE**. If the backend query fails to work: **QUERY_ERROR/UNKNOWN**, rather than concluding all logs were lost. Canaries follow the real route, contain no secrets, and have a clear sampling policy.

## 18. Runbook When the Dashboard Suddenly Shows Zero ERRORs

Hypothetical example: a release just deployed, error counts on the dashboard drop to 0, yet HTTP 5xx metrics rise.

1. **Verify business errors** from metrics/traces instead of concluding from log counts alone.
2. **Isolate** the service, release, instance, environment, and time of change.
3. **Find raw events** in stdout/files before the agent: did logger level, filters, or sampling change?
4. **Check the effective format**: PatternLayout, encoder, schema version, timestamp, log provider.
5. **Check the collector**: parse/rejection counters, mappings, multiline handling, transforms, routing.
6. **Check the backend**: index/tenant, search permissions, ingest lag, missing required fields.
7. **Inspect alert queries**: are they still grepping text like `Order failed` or relying on token indexes?
8. **Remediate under control**: fix the parser/query or roll back the format per the compatibility plan, without disabling logging security.
9. **Reconcile** source, collector, index counts, and canaries; account for sampling/duplicates.
10. **Postmortem**: update contract fixtures, schema validation, alerts, and the deprecation checklist.

When reprocessing legacy logs, preserve original timestamps and event IDs; never replay business commands just to "backfill logs." Log data must never trigger a new business side effect.

## 19. Security When Formats Change

A new JSON encoder may emit the entire MDC or structured arguments that previously did not appear in text. Risks include:

- Exposing tokens, cookies, passwords, or private keys from headers.
- Exception messages containing URLs/queries, SQL, or personal data.
- User input with newlines causing log injection if a text serializer does not escape them.
- Field schema changes causing logs to be routed to an overly permissive index/tenant.
- Redaction operating only on the message without filtering JSON fields/MDC.
- Lower sampling leading teams to mistakenly assume sensitive data is "rarely leaked" and therefore acceptable.
- Alerts/metrics accidentally using raw exception messages as labels, causing leaks and high cardinality.

Test with fake canary secrets across all fields, exceptions, and sinks; use data allowlists, retention, and RBAC. Never assume switching to structured JSON is automatically secure or automatically satisfies audit requirements.

## 20. Implementation Checklist

- [ ] Inventoried all consumers reading raw log text/regex/positions?
- [ ] Defined stable event codes and error codes?
- [ ] Defined schema version, types, units, and required/optional/nullability?
- [ ] Timestamps have clear source, timezone/offset, and precision?
- [ ] Not using message text, exception messages, or line numbers as business IDs?
- [ ] Formatter/encoder actually serializes structured fields?
- [ ] JUL/SLF4J/Log4j 2 severity mapping tested?
- [ ] JSON has proper escaping and multiline framing?
- [ ] No new tokens/PII exposed due to encoder/MDC changes?
- [ ] Consumer tests cover v1/v2, missing fields, and unknown enums?
- [ ] Golden snapshots only lock fields that actually belong to the contract?
- [ ] End-to-end canary queries by `event_code` and `schema_version`?
- [ ] Separate metrics for parse/schema/index rejections and queue/sampling loss?
- [ ] Compatibility window and rollback plan in place for rolling deployments?
- [ ] Alerts/SIEM do not depend on translatable phrasing?
- [ ] Not using diagnostic logs as the source of truth for audits/transactions?
- [ ] Owner and review process defined for breaking schema changes?
- [ ] Tested both positive and negative events, duplicates, and routing?
- [ ] Recovery and safe data backfill procedure in place if format drift occurs?
- [ ] Dashboard distinguishes no events from ingestion/query failures?

**Completion criteria:** You can distinguish presentation formats from event contracts; understand why regex/text parsers/stack traces are fragile; run a Java 17 program producing **one text match but two event-code matches**; and design schemas, tests, and migrations without breaking observability.

## 21. Self-Check Questions

1. Why can adding a trace ID to `PatternLayout` break parsers even though the event did not change?
2. What is the difference between a message template, a formatted message, and a structured field?
3. If a team switches from English to Vietnamese, should alerts look for the event code or the message string?
4. Why should `exception.getMessage()` not be used as a stable error code?
5. Are stack trace line numbers suitable as long-term error identification keys?
6. How does `Instant` differ from `LocalDateTime` when hosts are in multiple timezones?
7. Why should JSON key order and whitespace not be used as a schema?
8. Is changing `duration_ms` to the string `"250ms"` a breaking change?
9. If SLF4J attaches key-value pairs but the encoder does not serialize them, will the collector have those fields?
10. What is needed when mapping JUL `WARNING`/`SEVERE` to backend `WARN`/`ERROR`?
11. Why can a parser that throws no errors still map business semantics incorrectly?
12. How many erroneous records can a multiline stack trace create?
13. Why does a dual-route migration risk double-counting?
14. When are golden snapshots useful, and what should you avoid locking down?
15. A release causes dashboard ERRORs to drop to 0 while 5xx rises: which hops should you check?
16. What is the risk of a new structured JSON format exporting the entire MDC?
17. Why is querying a canary by raw message insufficient to prove the schema is correct?
18. Which metric should be monitored to detect missing required fields?
19. A single trace has multiple logs: is a trace ID a unique event ID?
20. If the backend query is unavailable, should the checker conclude MISSING or UNKNOWN?

## References

- [Java SE 17 — LogRecord](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/LogRecord.html) — message, parameters, Throwable.
- [Java SE 17 — Logger](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Logger.html) — log overloads and routing.
- [Java SE 17 — Formatter](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Formatter.html) — formatting records.
- [Java SE 17 — Instant](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Instant.html) — UTC timestamps.
- [SLF4J Manual](https://www.slf4j.org/manual.html) — fluent key-value API.
- [Logback Manual — Layouts](https://logback.qos.ch/manual/layouts.html) — PatternLayout/MDC.
- [Logback Manual — Architecture](https://logback.qos.ch/manual/architecture.html) — logger hierarchy/levels.
- [Apache Log4j 2 — Pattern Layout](https://logging.apache.org/log4j/2.x/manual/pattern-layout.html) — format/encoder.
- [OpenTelemetry Logs Data Model](https://opentelemetry.io/docs/specs/otel/logs/data-model/) — structured log fields and timestamps.
- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html) — log security/injection.
