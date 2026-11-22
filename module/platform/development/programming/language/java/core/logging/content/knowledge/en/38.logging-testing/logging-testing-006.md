# Testing Structured Fields in Java Logging

## 1. What are structured fields and why test them?

**Structured logging** represents an event as **fields with explicit names, data types, and semantics**, rather than just an unstable plain-text sentence. For example:

```text
2026-11-10 INFO checkout completed status=200 took 17 ms
```

The line above is human-readable, but an analysis system has to infer its structure with regex. With structured logging, you can write:

```json
{"timestamp":"2026-11-10T03:15:00Z","level":"INFO","event.name":"checkout.completed","service.name":"checkout-api","trace_id":"4bf92f3577b34da6a3ce929d0e0e4736","http.status_code":200,"duration_ms":17,"success":true}
```

The `http.status_code` and `duration_ms` fields are **numbers**, `success` is a **boolean**, and timestamp, level, and trace ID are **strings**. The backend can filter, group, and compute with proper types without parsing a free-form message.

**Testing structured fields** means verifying—from the moment the application builds the event until the encoder/collector emits the final format—that:

- **Field names, types, values, units of measurement**, and business semantics are correct.
- **Required fields are not missing**, and optional fields handle `null`/absence properly.
- No **secret fields or non-allowlisted data** are added.
- Strings are **properly escaped**; a single event does not break JSON Lines or inject fake log entries.
- `trace_id`/`span_id`, request ID, and MDC are attached from the **right request/thread**.
- The schema is not silently altered by the encoder, appender, logging level, async queue, or collector.
- Events that should be logged are actually emitted and received properly; not merely “a mock logger was called”.

The field names illustrated in this lesson represent an **application-chosen contract**. OpenTelemetry, ECS, Logstash, and observability platforms have their own conventions, which may change across versions. Lock down the actual contract before writing assertions.

## 2. Distinguishing the three testing layers

A Java system may pass through:

```text
Business code (action, outcome, timing)
   │
   ▼
Event builder / structured fields / MDC
   │
   ▼
SLF4J facade + backend (Logback / Log4j2 / JUL)
   │
   ▼
Encoder / JSON layout
   │
   ▼
Appender / async queue / file / stdout
   │
   ▼
Collector / parser / enrichment
   │
   ▼
Search / dashboard / alert / export
```

| Testing layer | Verifies | Does not prove |
| --- | --- | --- |
| **Event builder unit test** | Field name/type/value; missing/invalid schema is rejected | Whether the real JSON encoder emits the right bytes or whether the appender writes |
| **Backend/encoder integration test** | JSONL/file/stdout string, MDC, exceptions, escaping, level/filter | Whether the collector ingests/indexes properly or drops logs under overload |
| **End-to-end / contract test** | Data through collector to backend, mapping/index/retention, dashboard queries | That every record is durable under every crash scenario if not tested |

**Choose the layer that matches the question.** Mocking `logger.info(...)` checks that the logging API was called, but **does not confirm** that `duration_ms` in the final JSON is a number. Conversely, comparing JSON from the encoder does not prove the collector won't convert numbers into strings.

A good test suite usually spans multiple layers without **duplicating every test case at every layer**: unit tests cover logic; a representative set of integration/end-to-end cases covers wiring and contracts.

## 3. Defining the schema contract before writing tests

For example, the `checkout-api` service chooses the following contract:

| Field | JSON type | Required? | Key rules |
| --- | --- | --- | --- |
| `timestamp` | string | Yes | ISO-8601 with explicit timezone; independent of machine locale |
| `level` | string | Yes | Consistent value set, e.g., INFO/WARN/ERROR |
| `event.name` | string | Yes | Controlled code: `checkout.completed` or `checkout.failed` |
| `service.name` | string | Yes | Service identity from trusted configuration, not from HTTP headers |
| `trace_id` | string | Yes for HTTP events in the example | 32 lowercase hex digits per the chosen policy |
| `http.status_code` | integer | Yes | HTTP status 100–599, not the string `"200"` |
| `duration_ms` | integer | Yes | Non-negative duration in milliseconds |
| `success` | boolean | Yes | `true`/`false`, not `"true"` |
| `message` | string | Yes in the example | Short safe message; must not contain raw secrets |
| `error.code` | string | Optional | Stable error code, present only on applicable events |
| `user.id` | string | Policy-dependent | May be PII; sourced from trusted principal, appropriate retention |

**Do not assume every system has the same required fields.** A JVM startup log without an HTTP context typically has no trace ID; the same applies to errors occurring before a request enters tracing instrumentation. You may need schemas per `event.name`/`event.kind` or an explicit null policy.

### Validity conditions must be specified concretely

- **Field names:** `http.status_code` differs from `httpStatus` and `status`. Renaming a single field can break dashboards.
- **Types:** `200` is a number; `"200"` is a string. `null`, a missing key, and an empty string are not equivalent.
- **Semantics:** `duration_ms=17` is only valid when measurements share the same start/end points and unit.
- **Enums:** `level` may use `WARN` while another backend uses `WARNING`; a clear adapter/contract is needed.
- **Timestamps:** string with timezone that is parseable; do not test using a locale-dependent date `toString()`.
- **Correlation:** a properly formatted trace ID **is not enough** to prove it belongs to the current request; test both propagation and isolation.
- **Privacy:** fields such as `authorization`, `password`, and `cookie` must not be emitted if excluded by the contract.
- **No unexpected extra fields:** changing encoders or library versions may emit `threadName`, `logger_name`, or `caller_data`; decide which fields are accepted or need normalization.

When a team uses JSON Schema, it can describe types, required fields, patterns, and `additionalProperties`. However, you must decide whether the backend is allowed to add infrastructure fields like `host.name`; do not lock down a rigid schema when the system intentionally enriches metadata at the collector.

## 4. Positive, negative, and boundary testing

A test suite that only checks `assertEquals("INFO", event.level)` is insufficient.

| Test category | Input data | Expected outcome |
| --- | --- | --- |
| Positive | Status 200, duration 17, valid trace ID | All fields present with correct types and values |
| Missing required | Missing `event.name` or `trace_id` when required by contract | Rejected or reports a clear validation failure |
| Wrong type | `"http.status_code":"200"` | Rejected; does not silently coerce the string |
| Wrong unit | Duration measured in nanoseconds but assigned to `duration_ms` | Logic/unit conversion test catches the mismatch |
| Invalid value | Status 0 or 700, negative duration | Rejected or handled according to an explicit policy |
| Unknown field | `authorization`, `password`, typo `duraton_ms` | Not emitted; does not accidentally become an event field |
| Null/optional | No error code on success | Absent or null per contract, without mixing both styles |
| Escaping | Message with quotes, backslashes, newlines | Valid JSON; a single JSONL line is not split |
| Unicode | Message with Vietnamese text, emoji | Content matches and encoder does not corrupt UTF-8 |
| Long payload | Very long string, nested object | Bounded per policy, no unbounded memory growth |
| Context isolation | Request A/B with different trace/tenant | No MDC/field leakage when thread pool threads are reused |
| Security | Canary token in request | Does not appear in any unauthorized log field |
| Async | Multiple events enqueued | Records received completely per policy and after drain |
| Version drift | Encoder/layout/backend upgrade | Contract tests detect renamed, retyped, or missing fields |

**Test against parsed objects**, not just `jsonLine.contains("status")`. A substring can match inside `message`, JSON string escapes, another field, or the string `"200"` even when the number `200` is required.

## 5. JSON Lines, escaping, and one-event-per-line integrity

Most common in logging systems is **JSONL**: each event is one JSON object, on one physical line, terminated by a newline. Newline characters inside `message` must be encoded as the two characters `\n` within the JSON string rather than a raw newline that splits the event.

Valid example:

```json
{"event.name":"checkout.completed","message":"checkout\ncompleted","http.status_code":200}
```

The parsed JSON value of `message` will contain a logical newline, but the JSONL record still occupies **one physical line**.

Properties to verify:

1. JSON can be parsed by an independent library such as Jackson.
2. Each line corresponds to exactly one object, with no plain-text timestamp prefix outside the JSON unless required by the pipeline contract.
3. `"`, `\`, CR, LF, tab, and control characters are properly escaped.
4. UTF-8 preserves Vietnamese diacritics and does not corrupt surrogate pairs.
5. Numeric and boolean fields are not accidentally quoted.
6. No trailing garbage or plain-text log lines are mixed into the JSONL stream.
7. Exception records have a consistent shape instead of multi-line free-form stack traces outside JSON.

**Do not write your own serializer for production** when Jackson or a reliable JSON encoder is available. The plain JDK example below only illustrates the kinds of assertions to make; real integration tests must use the exact encoder/layout deployed by the application.

## 6. Runnable Java 17 example: testing schema, types, escaping, and canary

This standalone example uses **Java 17** with no Maven/Gradle or external libraries. It has three parts:

- `buildEvent` selects fields via an allowlist, without using raw Authorization or request body.
- `validate` verifies the exact field set, types, enums, ranges, timestamp, and trace ID.
- `toJson` is a **minimalist encoder for learning purposes** to test escape characters and JSON value shapes. Do not use this custom encoder as a production library.

For reproducible results, timestamp, duration, status, trace ID, and request are fixed. Only PASS messages are printed to stdout; the canary token is never printed.

Save as **`StructuredFieldsTestDemo.java`**:

```java
import java.time.Instant;
import java.time.format.DateTimeParseException;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Set;
import java.util.regex.Pattern;

public final class StructuredFieldsTestDemo {
    private static final Set<String> FIELDS = Set.of(
            "timestamp", "level", "event.name", "service.name",
            "trace_id", "http.status_code", "duration_ms",
            "success", "message");

    private static final Set<String> EVENT_NAMES = Set.of(
            "checkout.completed", "checkout.failed");

    private static final Pattern TRACE_ID =
            Pattern.compile("[0-9a-f]{32}");

    // Two sensitive fields are present in the input, but must not be copied to the event.
    record HttpContext(
            String trustedRoute,
            int status,
            long durationMs,
            String traceId,
            String authorization,
            String body) {}

    static Map<String, Object> buildEvent(HttpContext request) {
        if (!"/checkout".equals(request.trustedRoute())) {
            throw new IllegalArgumentException("Unexpected route");
        }

        Map<String, Object> event = new LinkedHashMap<>();
        event.put("timestamp", "2026-11-10T03:15:00Z");
        event.put("level", "INFO");
        event.put("event.name", "checkout.completed");
        event.put("service.name", "checkout-api");
        event.put("trace_id", request.traceId());
        event.put("http.status_code", request.status());
        event.put("duration_ms", request.durationMs());
        event.put("success", Boolean.TRUE);
        event.put("message", "checkout\ncompleted");
        return event;
    }

    private static String requiredText(
            Map<String, Object> event, String key) {
        Object value = event.get(key);
        if (!(value instanceof String text) || text.isBlank()) {
            throw new IllegalArgumentException("Invalid string: " + key);
        }
        return text;
    }

    static void validate(Map<String, Object> event) {
        if (!event.keySet().equals(FIELDS)) {
            throw new IllegalArgumentException("Unexpected field set");
        }

        try {
            Instant.parse(requiredText(event, "timestamp"));
        } catch (DateTimeParseException ex) {
            throw new IllegalArgumentException("Invalid timestamp", ex);
        }

        if (!Set.of("INFO", "WARN", "ERROR").contains(
                requiredText(event, "level"))) {
            throw new IllegalArgumentException("Invalid level");
        }
        if (!EVENT_NAMES.contains(
                requiredText(event, "event.name"))) {
            throw new IllegalArgumentException("Invalid event name");
        }
        requiredText(event, "service.name");

        if (!TRACE_ID.matcher(
                requiredText(event, "trace_id")).matches()) {
            throw new IllegalArgumentException("Invalid trace id");
        }

        Object status = event.get("http.status_code");
        if (!(status instanceof Integer code)
                || code < 100 || code > 599) {
            throw new IllegalArgumentException("Invalid status");
        }

        Object duration = event.get("duration_ms");
        if (!(duration instanceof Long millis) || millis < 0) {
            throw new IllegalArgumentException("Invalid duration");
        }

        if (!(event.get("success") instanceof Boolean)) {
            throw new IllegalArgumentException("Invalid boolean");
        }
        if (requiredText(event, "message").length() > 200) {
            throw new IllegalArgumentException("Message too long");
        }
    }

    // Only for the lesson's String/Integer/Long/Boolean type set.
    private static String jsonValue(Object value) {
        if (value instanceof String text) {
            return quote(text);
        }
        if (value instanceof Integer || value instanceof Long
                || value instanceof Boolean) {
            return value.toString();
        }
        throw new IllegalArgumentException("Unsupported type");
    }

    private static String quote(String value) {
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

    static String toJson(Map<String, Object> event) {
        validate(event);
        StringBuilder out = new StringBuilder("{");
        boolean first = true;

        for (Map.Entry<String, Object> field : event.entrySet()) {
            if (!first) {
                out.append(',');
            }
            first = false;
            out.append(quote(field.getKey()))
                    .append(':')
                    .append(jsonValue(field.getValue()));
        }
        return out.append('}').toString();
    }

    private static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    private static void expectInvalid(Map<String, Object> event) {
        try {
            validate(event);
            throw new AssertionError("Invalid event was accepted");
        } catch (IllegalArgumentException expected) {
            // Validation is responsible for rejecting invalid events.
        }
    }

    public static void main(String[] args) {
        String secret = "SENSITIVE_CANARY_314";
        HttpContext request = new HttpContext(
                "/checkout", 200, 17L,
                "4bf92f3577b34da6a3ce929d0e0e4736",
                "Bearer " + secret,
                "card=" + secret);

        Map<String, Object> good = buildEvent(request);
        validate(good);

        check(good.get("http.status_code") instanceof Integer,
                "status must be integer");
        check(good.get("duration_ms") instanceof Long,
                "duration must be long");
        check(good.get("success") instanceof Boolean,
                "success must be boolean");
        System.out.println("PASS 1: schema and types");

        String json = toJson(good);
        check(json.contains("\"http.status_code\":200"),
                "numeric status lost");
        check(json.contains("\"duration_ms\":17"),
                "numeric duration lost");
        check(json.contains("\"success\":true"),
                "boolean lost");
        check(json.contains("\"message\":\"checkout\\ncompleted\""),
                "newline was not escaped");
        check(json.indexOf('\n') < 0 && json.indexOf('\r') < 0,
                "one event must occupy one physical line");
        System.out.println("PASS 2: JSON values and escaping");

        Map<String, Object> missing = new LinkedHashMap<>(good);
        missing.remove("trace_id");
        expectInvalid(missing);

        Map<String, Object> wrongType = new LinkedHashMap<>(good);
        wrongType.put("http.status_code", "200");
        expectInvalid(wrongType);

        Map<String, Object> extra = new LinkedHashMap<>(good);
        extra.put("authorization", request.authorization());
        expectInvalid(extra);
        System.out.println("PASS 3: missing, wrong-type and extra fields");

        check(!json.contains(secret), "secret leaked");
        check(!json.contains("authorization"), "sensitive key leaked");
        check(!json.contains("\"body\""), "body key leaked");
        System.out.println("PASS 4: sensitive data excluded");

        System.out.println("ALL CHECKS PASSED");
    }
}
```

Commands to run with JDK 17+:

```bash
javac --release 17 StructuredFieldsTestDemo.java
java StructuredFieldsTestDemo
```

**Exact stdout:**

```text
PASS 1: schema and types
PASS 2: JSON values and escaping
PASS 3: missing, wrong-type and extra fields
PASS 4: sensitive data excluded
ALL CHECKS PASSED
```

**Why is this example properly scoped?**

- `Set.of(...)` is used as the required+allowed fields contract for a **specific event type**, not a universal schema for all logs.
- `LinkedHashMap` preserves order in the demo encoder for easy inspection, but **JSON key order carries no semantic meaning**; production tests should not enforce key ordering.
- `http.status_code` is `Integer`, `duration_ms` is `Long`, and `success` is `Boolean`; `toJson` does not quote numbers or booleans.
- `message` has a newline in its Java value. When serialized, it becomes the literal `\n` sequence, without splitting the JSONL record into two lines.
- Missing trace ID, string status, and sensitive fields outside the allowlist are rejected in `expectInvalid`.
- `HttpContext` has Authorization and body containing the canary, but `buildEvent` **never reads those two properties** when emitting the log.
- `Instant.parse` confirms the timestamp is parseable; the timestamp is fixed so stdout is deterministic, not as a production timestamp strategy.

**Limitations:** the `quote(...)` encoder in the example only handles the String/Integer/Long/Boolean subset and escapes common control characters. It **is not a general-purpose JSON serializer**—for example, it does not check invalid Unicode surrogates, nested/array structures, floating-point numbers, or other edge cases. Production code should use a dedicated JSON encoder and **test the parsed JSON with an independent library**, as shown in the next section. The program also does not actually write files, use Logback, or verify a collector.

## 7. Integration testing JSON output with JUnit 5 and Jackson

To test the **actual output of the encoder**, you need to capture the real JSON line from an appender or file and parse it with a type-aware JSON parser. The following example is a **test snippet** requiring JUnit Jupiter and Jackson Databind, along with a `captureActualJsonLine()` helper provided by the system's test fixture. It is **not a standalone program**, as its goal is to show the types of assertions to run on encoded JSON:

```java
// Illustrative imports:
// import com.fasterxml.jackson.databind.JsonNode;
// import com.fasterxml.jackson.databind.ObjectMapper;
// import org.junit.jupiter.api.Test;
// import static org.junit.jupiter.api.Assertions.*;

@Test
void structuredOutputHasContractTypes() throws Exception {
    String line = captureActualJsonLine(); // Fixture from an actual appender/file.
    JsonNode root = new ObjectMapper().readTree(line);

    assertTrue(root.isObject());
    assertEquals("checkout.completed", root.path("event.name").asText());
    assertEquals("checkout-api", root.path("service.name").asText());

    JsonNode status = root.path("http.status_code");
    assertTrue(status.isIntegralNumber());
    assertEquals(200, status.intValue());

    JsonNode duration = root.path("duration_ms");
    assertTrue(duration.isIntegralNumber());
    assertEquals(17L, duration.longValue());

    JsonNode success = root.path("success");
    assertTrue(success.isBoolean());
    assertTrue(success.booleanValue());

    assertFalse(root.has("authorization"));
    assertFalse(root.has("password"));
    assertFalse(root.has("cookie"));
    assertFalse(line.contains("SENSITIVE_CANARY_314"));
}
```

**Important:** `root.path("duration_ms").asLong()` alone is not enough to check the type, because some conversion APIs accept numeric strings. Check `isIntegralNumber()` first; similarly, check `isBoolean()` before `booleanValue()`.

Depending on the backend library, JSON events may use nested objects instead of dotted keys, for example:

```json
{"http":{"status_code":200},"duration_ms":17}
```

In that case, assertions must traverse `root.path("http").path("status_code")`; **do not** flatten nested keys into dotted keys if the contract specifies nesting. Align the shape with the actual pipeline/collector.

### Test the contract, not out-of-contract formatting

Do not compare full JSON strings if field order, spacing, or metadata fields can vary while remaining valid under the contract. Parse into a JSON tree and compare values and types. Only test byte-for-byte output if the workflow requires a canonical format (e.g., signing/HMAC) and serialization is explicitly documented.

Test timestamps with a time parser and an appropriate tolerance, rather than `assertEquals(Instant.now().toString(), timestamp)`, because the clock advances during test execution. You can inject `Clock.fixed(...)` into the event builder to assert deterministic values.

## 8. Logback ListAppender: inspecting events before the encoder

When an application uses SLF4J + Logback-classic, you can attach a `ListAppender<ILoggingEvent>` to a logger in tests to read emitted events. This is a **JUnit snippet** requiring real Logback and SLF4J on the test classpath:

```java
// JUnit 5 snippet; imports are abbreviated:
// ch.qos.logback.classic.Logger;
// ch.qos.logback.classic.spi.ILoggingEvent;
// ch.qos.logback.core.read.ListAppender;
// org.slf4j.LoggerFactory;
// static org.junit.jupiter.api.Assertions.*;

ch.qos.logback.classic.Logger logger =
        (ch.qos.logback.classic.Logger)
        org.slf4j.LoggerFactory.getLogger("test.structured");

var appender = new ch.qos.logback.core.read
        .ListAppender<ch.qos.logback.classic.spi.ILoggingEvent>();

appender.start();
logger.addAppender(appender);
try {
    logger.info("checkout.completed");
    assertEquals(1, appender.list.size());
    assertEquals("checkout.completed",
            appender.list.get(0).getFormattedMessage());
} finally {
    logger.detachAppender(appender);
    appender.stop();
}
```

This snippet verifies that **the event was received by Logback** and checks its formatted message, but **does not verify the output JSON fields**. To test `trace_id` from MDC, you can inspect `getMDCPropertyMap()` while setting and restoring MDC within the proper test scope. If the application uses SLF4J 2.x's fluent API `logger.atInfo().addKeyValue(...)`, verify whether the backend/encoder preserves key-value pairs; merely calling `addKeyValue` does not guarantee they appear as JSON fields.

**To test the real encoder:** configure the production encoder in the test, attach an `OutputStreamAppender` backed by a `ByteArrayOutputStream` or write to a temporary file, emit an event, flush/stop according to backend semantics, and parse each line with Jackson. Only then are the final key names, types, and shapes verified.

### Managing test isolation

- Do not leave test appenders attached to static loggers after a test finishes.
- Save and restore logger level, additivity, and MDC/context if the test modifies them.
- Do not let multiple parallel tests mutate the shared root logger and expect stable assertions.
- For async loggers, which side of the queue `ListAppender` sits on (before or after) determines whether you are measuring events received or events actually encoded/emitted.

## 9. SLF4J 2.x example: structured key-value fields

SLF4J 2.x supports a fluent logging API that can attach key-value pairs:

```java
// Integration snippet requiring SLF4J 2.x + a backend that supports storing fields.
org.slf4j.Logger logger =
        org.slf4j.LoggerFactory.getLogger("checkout");

logger.atInfo()
      .addKeyValue("event.name", "checkout.completed")
      .addKeyValue("http.status_code", 200)
      .addKeyValue("duration_ms", 17L)
      .addKeyValue("success", true)
      .log("Checkout completed");
```

**What must be tested:** the backend may or may not support serializing these pairs into **properly typed JSON keys**. A text pattern might just print `key=value` as a string; another encoder might nest the pairs under `fields` or rename keys. Therefore, **the fact that the API accepts these arguments does not prove the structured output matches the contract**.

The test suite should assert that:

- The event has the exact `event.name`, `http.status_code`, `duration_ms`, and `success` fields.
- There are no duplicate keys or collisions with encoder default fields.
- Integers remain JSON numbers, and booleans remain JSON booleans.
- INFO-level events are emitted when allowed by the logger/config and are not unintentionally blocked by filters/appenders.
- Messages are escaped and carry no raw tokens/PII.
- When DEBUG is disabled, eager expressions with side effects are not used in assertions to infer whether an event was emitted.

## 10. Testing MDC and correlation fields

Request logging typically attaches `trace_id`, `span_id`, `request_id`, and `tenant_id` via MDC or OpenTelemetry. Test these scenarios:

1. **Single request:** events within the same request retain the right trace ID.
2. **Two concurrent requests:** trace/tenant from request A never appears in events from request B.
3. **Thread pool reuse:** a subsequent request does not inherit MDC from a previous request.
4. **Async producer/consumer:** events must snapshot context from the producer at the right time; do not let worker threads read their own thread-local state.
5. **No context:** logs outside HTTP requests (startup/scheduler) follow the optional-field policy without writing garbage trace IDs or ambiguous `null` values.
6. **Untrusted headers:** `traceparent`/`X-Request-ID` from clients must be parsed/validated; do not treat a well-formatted ID as proof of actor identity.
7. **Tenant boundary:** tenant ID must come from the authenticated context, not from raw request query parameters.

A pattern for setting up/cleaning up MDC in tests:

```java
// Snippet requiring SLF4J; not a standalone program.
String previous = org.slf4j.MDC.get("request_id");
org.slf4j.MDC.put("request_id", "req_101");
try {
    runRequestAndCaptureLogs();
} finally {
    if (previous == null) {
        org.slf4j.MDC.remove("request_id");
    } else {
        org.slf4j.MDC.put("request_id", previous);
    }
}
```

This snippet only illustrates **save/restore for a single key**; in production or multi-key tests, use scoped MDC, map snapshots, or appropriate integration mechanisms. Without `finally`, one test can pollute the context of subsequent tests. If the backend uses an asynchronous logger, ensure the event captures a snapshot of values before publishing.

**Testing identity ≠ testing correlation.** A valid trace ID still does not prove the user is authenticated; do not take an actor ID from a spoofable header and confuse it with the authenticated principal.

## 11. Testing security and secrets in structured fields

For sensitive APIs, a log entry with valid JSON is still **unsafe** if it contains tokens. Fields that typically must be excluded:

- `authorization`, `password`, `cookie`, `set_cookie`, `refresh_token`.
- Raw request/response bodies, OTPs, session IDs, API keys, payment PAN/CVV.
- Raw URLs/queries containing tokens or path variables carrying emails/secrets.
- Exceptions/stack traces or `toString()` outputs containing sensitive content.
- MDC baggage containing personal data.

**Canary test:** place a **synthetic** string `SENSITIVE_CANARY_314` in the input of a test endpoint; verify that it **never appears** in the event builder, actual JSON line, file/stdout, collector, backend, dashboard, or export within the allowed test scope. Never use real credentials.

Do not only assert `!root.has("password")`: a secret may end up inside `message`, `exception.stacktrace`, or another key. Scan the **entire JSON string** for the canary, while also checking the field allowlist.

**Log forging:** messages containing CRLF, tabs, quotes, backslashes, Unicode line separators, or control characters must be safely encoded for JSONL as well as downstream viewers/CSV. Jackson escaping handles JSON syntax; dashboards still need HTML escaping, and CSV exports need protection against formula interpretation as appropriate for the application.

Tests can attempt to inject an `authorization` key via the fluent API, custom field providers, or MDC to ensure the encoder/policy does not accidentally emit forbidden data.

## 12. Testing errors, stack traces, and optional fields

When a business operation fails, an event may contain:

```json
{"event.name":"checkout.failed","level":"ERROR","error.code":"PAYMENT_TIMEOUT","http.status_code":504,"success":false}
```

Points that must be defined:

- `error.code` is present on failure events, but absent on success events.
- `error.message` is a controlled string, not a raw exception message from a dependency that might contain secrets.
- `exception.type` may use the class name; `stack_trace` is only included when policy permits and viewers have appropriate access.
- Status 504 does not automatically mean “payment timeout”; the reason must come from the corresponding logic.
- `duration_ms` might be missing on incomplete events; is that a schema violation or a different event type?
- When two exceptions have multi-line stack traces, JSONL must still remain one object per physical line.
- `null` may be written explicitly or the key omitted; tests must enforce a consistent decision rather than letting a default `asText()` mask bugs.

If using nested field structures, test the full path rather than searching for `error` in the JSON string. Some encoders automatically emit `throwable` or `stack_trace`; review data policy and event size limits.

## 13. Testing async logging: do not assert before the consumer finishes writing

With `AsyncAppender`, calling `logger.info(...)` may only **enqueue** the event. Reading `ByteArrayOutputStream` immediately and asserting line counts can produce flaky tests even when the system is working properly.

Designing stable tests:

1. Send `N` events with unique `event.id` values and varied `trace_id` or transaction IDs.
2. Use the backend's **official lifecycle/drain mechanism** or test-specific synchronization to confirm the consumer has processed them. Avoid bare `Thread.sleep(100)`, which depends on CI machine speed.
3. Parse every output JSON line, verify the total count, and confirm each event ID appears per policy; do not require global ordering when multiple producers/consumers are involved.
4. If the system drops/discards events when the queue is full, tests must specify the **expected policy** (drop allowed vs. no-loss required) and check counters; do not conflate test bugs with operational policy.
5. Shut down appenders/consumers cleanly after each test so subsequent tests are not polluted.
6. Test overload/bursts, slow sinks, file rotation, graceful shutdown, and crashes separately in integration/chaos tests.

**Enqueued ≠ written to sink ≠ indexed by backend.** When testing collector parser contracts, wait for the appropriate acknowledgment point rather than just checking that the producer returned.

### Avoid tests that depend on global order

When multiple threads emit events, global ordering can differ from processing order at the appender. Tests should usually assert **the set of IDs, counts, and per-ID content**, or ordering within a single stream where explicitly guaranteed, rather than comparing global order across all requests.

## 14. Collector and search backend contract tests

Even when the JSON encoder emits proper numbers and booleans, the collector can still:

- Convert fields to strings, rename keys, or nest objects incorrectly.
- Overwrite `service.name`, `trace_id`, or `timestamp` with different metadata.
- Reduce timestamp precision, change timezones, or alter duration units.
- Drop fields due to parser errors, size limits, or mapping conflicts.
- Duplicate lines when both a file tailer and a stdout collector read the same event.
- Truncate events or drop them when the queue/ingest is overloaded.

Therefore, an end-to-end contract test should:

1. Generate an **event with a unique ID** and representative field types/units.
2. Wait for the backend to return data using bounded retries and a deadline (no infinite sleep).
3. Query by event ID and service/environment.
4. Compare field mappings, types, values, timestamps, tenant, and nested shapes in the backend.
5. Verify the canary does not appear in forbidden sinks.
6. If ingestion must be exactly-once, test the deduplication policy; do not assume it just because the source is JSONL.
7. Collect failure evidence: raw encoder output, collector parse errors, backend event, and config version.

**Do not use keyword search results in `message` to prove numeric mapping.** Inspect the actual field and its type in the index/query API whenever the system supports it.

## 15. Schema evolution and backward compatibility

Structured fields become a data API for dashboards, alerts, reports, and security systems. Small changes can break consumers:

| Change | Risk | How to verify |
| --- | --- | --- |
| `duration_ms` changed to `duration_ns` | Latency computed in wrong units | Contract tests + explicit versioning/migration |
| `http.status_code` from number to string | Aggregations/histograms stop working | Type assertions |
| `event.name` changed from `checkout.failed` to `checkout.error` | Alerts/filters miss events | Enum/compatibility checks |
| `trace_id` moved to another key | Log/trace correlation breaks | Integration contract |
| `error.code` changed from optional to required | Success events become invalid | Per-event-type schema tests |
| Adding a field containing PII | Data exposure and retention impact | Allowlist + privacy review |
| Flat JSON changed to nested | Legacy queries return nothing | Shape-specific tests |
| Adding encoder default fields | Key collisions/duplicates | Inspect final JSON, parsed tree, and metadata |

You can use `schema.version` and per-`event.name` contracts, keeping older versions readable during transition periods. **Do not assume adding a field is always backward-compatible** if the collector/index enforces `additionalProperties=false`, has field cardinality limits, or if the new field contains sensitive data.

When upgrading the JDK, Logback, Log4j2, JSON encoder, or collector, re-run contract tests to catch discrepancies. Avoid keeping a brittle full-JSON “golden snapshot” if metadata intentionally changes without affecting the contract.

## 16. Common testing mistakes

| Symptom | Bug in test or system | How to fix |
| --- | --- | --- |
| Test PASSES even when status is a string | Using `asText()` or substring checks instead of type assertions | `isIntegralNumber()` then compare number |
| Only testing a mock logger | Does not measure real encoder/appender | Capture actual JSONL and parse |
| Test depends on field order | JSON objects do not guarantee key order | Compare field tree against schema |
| Flaky test on CI | Fixed sleep before async drain | Use synchronization/lifecycle with bounded timeout |
| Missing trace ID yet test still PASSES | `root.path(...).asText()` defaults to empty string | Check `hasNonNull` and format |
| Event has duplicate keys | Multiple field providers write the same key | Review encoder mapping; strict duplicate-key parser if needed |
| Logs missing yet business test stays green | Logger level/filter/appender suppresses event | Backend config integration test |
| Secret not under `password` key but in `message` | Only checking field name list | Scan full payload and pipeline for canary |
| Runtime schema changes when exceptions occur | Encoder adds stack trace fields | Test success, error, and exception cases |
| MDC tenant from request A leaks into B | ThreadLocal not restored | Scoped context, concurrent tests |
| Duplicate events when collector ingests | Both file and stdout tailed; retries without dedup | Canonical source/ID and pipeline tests |
| HTTP 404 has no route | Policy assumes every request has a matched route | Optional/UNKNOWN policy |
| Unstable timestamp tests | Direct comparison against `Instant.now()` | Inject `Clock` or use controlled tolerance |
| Duration measured with nanoTime but labeled ms | Conversion bug | Boundary/threshold tests with fake clock |
| JSON on stdout mixed with plain-text lines | Appender does not use a uniform JSON layout | Separate streams or standardize encoder |
| Overly strict schema tests | Framework adds valid metadata | Clear contract between core fields and extension fields |

## 17. Minimum test matrix for a web service

| Scenario | Level/event | Fields to verify |
| --- | --- | --- |
| HTTP 200 success | `checkout.completed` / INFO | service, status 200 number, duration >= 0, success true |
| HTTP 504 error | `checkout.failed` / ERROR | error code, status number, success false, trace |
| Request rejected before controller | `authorization_denied` | Verified/anonymous actor, UNKNOWN route if missing |
| No tracing context | Startup/scheduler event | Optional trace ID per policy, no fake empty string |
| Two parallel requests | Multiple traces/tenants | No MDC/correlation leakage |
| Body contains canary | Auth/payment event | No canary, token, or raw body leaked |
| Message contains newline/quotes | Text/JSON event | JSONL stays one line, parses to exact string |
| Async queue and shutdown | N events | Count and drops match policy, non-flaky |
| Encoder upgrade | Same fixture | Core contract types/names preserved |
| Collector upgrade | E2E event | Mapping, timestamp, nested shape, and ID correct |

In CI, run unit tests frequently and encoder integration tests on every logging change. Collector E2E tests can be heavier; run them in an appropriate pipeline against an isolated test backend with cleanup.

## 18. Principles for organizing tests and test data

- **One clear goal per test:** types, field presence, secrecy, correlation, async delivery, schema migration.
- **Safe test fixtures:** use synthetic canaries/IDs; never use real tokens, passwords, or user profiles.
- **Test isolation:** isolate logger config, MDC, appenders, temp files, and index namespaces between tests.
- **Track schema/encoder versions:** know which test binary and backend version are actually running.
- **Do not hide errors:** when parsing fails, report the event ID and sanitized details; avoid printing raw secrets to CI logs.
- **Reduce false positives:** assert semantics and types, independent of JSON key order or spacing.
- **Reduce false negatives:** do not test only message text; verify nested fields, exception metadata, MDC, and collector mappings.
- **Optimize runtime:** unit tests cover all fields; integration/E2E tests pick representative scenarios and critical negative cases.
- **Test missing-data behavior:** missing required fields must be rejected; missing optional fields must have consistent semantics.
- **Ensure upgradability:** schema changes are reviewed and have a migration/compatibility plan.

### When structured logs serve audit or security purposes

A log with a clean `actor.id` field does not by itself prove the actor is trustworthy: it must come from the authentication context rather than a self-asserted header; events must record accurate outcomes and have durable storage, tamper/loss detection, and access controls. **Structured field testing is a necessary condition, not a replacement for logging threat modeling or audit trail correctness**.

## 19. Practical checklist

- [ ] Event types, required/optional fields, field names, and types are documented.
- [ ] Timestamps are parseable, have explicit timezones, and are locale-independent.
- [ ] Duration has the right unit; status is a number, and success is a boolean.
- [ ] Missing, wrong-type, null, boundary, and non-allowlisted fields are tested.
- [ ] JSON Lines output is valid, one event per physical line, with proper escaping.
- [ ] Integration tests cover the actual backend/encoder, not just a mock logger.
- [ ] Nested shapes and duplicate/colliding fields are tested against the contract.
- [ ] MDC/trace correlation does not leak across threads, requests, or tenants.
- [ ] Async logging is properly drained/synchronized before assertions; no fixed sleeps.
- [ ] Secret canaries do not appear in messages, exceptions, MDC, JSONL, or the backend.
- [ ] Logger levels, filters, and appenders match event emission requirements.
- [ ] End-to-end tests verify mapping and ingestion after collector changes.
- [ ] Schema evolution is versioned/reviewed and does not silently alter types or units.
- [ ] Test failure output does not accidentally print secrets into CI logs.

**Remember:** testing structured fields does not stop at “the logger was called”. You must verify **exact field names and types in the event builder, the real JSON encoder, runtime context, sensitive data exclusion, and post-collector mapping**. A structured log is only trustworthy when it is semantically accurate, uncontaminated across sources, parseable, and delivered to its destination according to the designed contract.

### References

- [SLF4J 2.x Manual — Fluent Logging API](https://www.slf4j.org/manual.html)
- [Logback Manual — Appenders](https://logback.qos.ch/manual/appenders.html)
- [Logback Manual — MDC](https://logback.qos.ch/manual/mdc.html)
- [Apache Log4j2 — JSON Template Layout](https://logging.apache.org/log4j/2.x/manual/json-template-layout.html)
- [Jackson Databind — JsonNode API](https://github.com/FasterXML/jackson-databind)
- [JUnit 5 User Guide](https://junit.org/junit5/docs/current/user-guide/)
- [OpenTelemetry — Logs Data Model](https://opentelemetry.io/docs/specs/otel/logs/data-model/)
- [OWASP — Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html)
