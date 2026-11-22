# Hands-on Practice: Adding JSON Output for Java Core Logging

## 1. Objectives and Final Deliverable

In a Java project, default text-based logs are usually easy for humans to read, but they are hard to filter accurately by `service`, `event.name`, `request_id`, `trace_id`, or `error.code` when a system runs across multiple instances. This hands-on exercise converts **log output to JSON Lines** (each log event is a JSON object on **one physical line**), while preserving the exact meaning of severity, context, and exceptions.

After completing this lesson, you will be able to:

1. Distinguish between a **structured log event**, **JSON encoding**, and **a text line that merely looks like JSON**.
2. Produce JSON output containing timestamp, severity, logger, service, event name, request ID, trace ID, message, error code, and exception type.
3. Run a Java 17 program using only the JDK to observe **deterministic, exact-matchable** JSON output.
4. Ensure that quotes, backslashes, newlines, and control characters in messages do not break the JSON Lines structure.
5. Know how to integrate a JSON encoder into Logback/SLF4J, along with considerations for Log4j2 and Spring Boot based on actual dependencies/versions.
6. Verify output with a JSON parser and compare schemas across the application, file/stdout, shipper/Collector, and log backend.
7. Avoid common pitfalls: manual string concatenation without escaping, leaking secrets into logs, splitting stack traces into multiple events, duplicating output, or assuming a JSON file guarantees log ingestion.

**Expected result:** running `javac JsonOutputDemo.java` and `java JsonOutputDemo` will produce **three valid JSON objects on three lines**, queryable by `event.name`, `request_id`, and `error.code`. No Maven, Gradle, database, or external logging service is required for the pure Java exercise.

The lesson also includes a Logback configuration section using a JSON encoder library for SLF4J applications, along with a checklist for safely migrating an existing service to structured logging.

## 2. Before and After: What Changes?

A typical text log:

```text
Jan 01, 2026 10:00:01 AM com.example.PaymentService authorize
WARNING: payment provider timed out, req-101
```

With text, a human reader can understand the content, but search systems must parse prose to find a request ID, error code, or service. Default formatters can also vary by locale/runtime, and multi-line exception stack traces are easily misinterpreted by shippers as multiple separate events.

After converting to JSON Lines:

```json
{"timestamp":"2026-01-01T10:00:01Z","severity":"WARNING","logger":"demo.orders","service.name":"orders-api","event.name":"payment.retry","request_id":"req-101","trace_id":"4bf92f3577b34da6a3ce929d0e0e4736","message":"Retry scheduled","error.code":"DOWNSTREAM_TIMEOUT"}
```

Each field is a **separate JSON key/value pair**, rather than free-form tokens inside a message. The backend can filter accurately by `event.name=payment.retry` or `error.code=DOWNSTREAM_TIMEOUT` once the appropriate parser/mapping is configured.

However, **JSON output does not automatically mean "proper structured logging."** If Java only writes:

```text
{"message":"severity=ERROR request_id=req-101 error_code=TIMEOUT"}
```

then severity, request ID, and error code are still **a single message string**. Users may still need regex to search them. Important attributes must be promoted to keys with clear types and semantics.

### Distinguishing the Three Layers

| Layer | Purpose | Examples |
| --- | --- | --- |
| Log event in JVM | Holds severity, message, timestamp, exception, and context | JUL `LogRecord`, Logback ILoggingEvent |
| Encoder/Formatter | Converts the event into bytes/text as JSON Lines | JSON formatter/encoder, UTF-8 |
| Shipper/Collector/backend | Collects, parses, enriches, indexes, and searches | Container agent, file shipper, OTLP Collector, log store |

Replacing a text layout with a JSON encoder changes the **formatting** layer, not necessarily the **transport**. Logs can still be written to stdout or files and collected by an agent as before. Nor should JSON Lines be confused with a JSON array: multiple lines of individual objects are **not** a single JSON document wrapped in `[ ... ]`.

## 3. Designing the JSON Schema Before Writing Code

A minimal schema with a clear purpose:

| Field | Type | Meaning | Source of Truth |
| --- | --- | --- | --- |
| `timestamp` | String ISO-8601 UTC/offset | Time when the event occurred | Logging framework/JVM |
| `severity` | String | INFO, WARNING, SEVERE… | Logging event |
| `logger` | String | Name of the logger emitting the record | Framework |
| `service.name` | String | Service generating the event | Deployment/application config |
| `event.name` | String | Stable, machine-readable event name | Code/event catalog |
| `request_id` | String, event-dependent | Correlates logs belonging to one request | Verified ingress/correlation context |
| `trace_id` | String, event-dependent | Correlates distributed traces | Trusted trace context |
| `message` | String | Human-readable summary, subject to change | Code, stripped of sensitive data |
| `error.code` | String, event-dependent | Stable error code, e.g. `DOWNSTREAM_TIMEOUT` | Business/exception boundary |
| `exception.type` | String, event-dependent | Exception class name for classification | `Throwable.getClass()` |

This is an **application-defined illustrative schema**; it does not mean every system automatically recognizes these keys as standard OpenTelemetry fields. In a real backend, some fields may be resource attributes, log record attributes, or organization-standardized names. You must align on versioning, serialization, and mapping.

### Conventions to Lock Down

- **Timestamp:** use `Instant`/ISO-8601 with `Z` or an offset. Separate event time from ingest time when reconciling logs.
- **Severity:** maintain a clear convention; JUL uses `INFO`/`WARNING`/`SEVERE`—do not assume they are identical to SLF4J's `INFO`/`WARN`/`ERROR` tokens without mapping.
- **Event name:** use a stable catalog such as `order.accepted`, `payment.retry`, `payment.failed`; never use `exception.getMessage()` verbatim as an event name.
- **Identifiers:** include a dedicated `event_id` if needed. One request can emit multiple events, so `request_id` is not always a deduplication key.
- **Optional fields:** you may **omit the key** when no value exists or use JSON `null` per your contract, but **never use the string `"null"`** to represent an absent value.
- **Field types:** status/duration/count should be JSON integers or floating-point numbers, not forced into strings. For example, `"http.status_code":503` and `"duration_ms":12.5`.
- **Payload size:** cap message length, exception details, and user-supplied fields to avoid overloading the encoder/Collector/backend.
- **Data minimization:** tokens, session cookies, API keys, passwords, and unnecessary personal data **must never enter the event**, regardless of whether the formatter can escape them.

Different JSON backends handle dots in keys differently—for instance, `service.name` may be preserved verbatim or mapped into a nested object depending on configuration. Always verify the actual output and stored schema rather than guessing based on dot notation.

## 4. Practice Architecture

The JDK 17 portion uses:

```text
JsonOutputDemo.main()
   |
   +-- create Context(event, service, request, trace, errorCode)
   |
   +-- create java.util.logging.LogRecord
   |     level + timestamp + message + Throwable + context
   |
   +-- java.util.logging.Logger
   |     level threshold + handler chain
   |
   +-- JsonFormatter
   |     JSON escaping + field assembly
   |
   +-- custom Handler -> System.out
         |
         +-- 1 LogRecord = 1 JSON object + '\n'
```

**Why use JUL in the main example?** JUL is built into JDK 17, making the exercise runnable immediately with deterministic output and clearly demonstrating the separation between `LogRecord`, `Formatter`, and `Handler`. Once understood, the same schema can be implemented with SLF4J + Logback/Log4j2 or an OpenTelemetry SDK/exporter.

The hand-written JSON formatter here is **only for explaining the underlying principles**. For production, prefer a battle-tested JSON encoder/serializer that supports Unicode, escaping, exception serialization, performance, configurable fields, and schema versioning. Do not copy a minimal formatter into a system handling untrusted input and assume it meets all security/standardization requirements.

## 5. Creating the Complete Java 17 Program

Create a file named `JsonOutputDemo.java` with the code below. The program creates no external files, requires no network access, reads no environment variables, and uses fixed timestamps so stdout can be tested directly.

```java
import java.time.Instant;
import java.util.Locale;
import java.util.logging.Formatter;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class JsonOutputDemo {
    private static final Logger LOG =
            Logger.getLogger("demo.orders");

    record Context(
            String eventName,
            String serviceName,
            String requestId,
            String traceId,
            String errorCode) {}

    private static String quote(String text) {
        StringBuilder out = new StringBuilder("\"");
        for (int i = 0; i < text.length(); i++) {
            char ch = text.charAt(i);
            switch (ch) {
                case '"' -> out.append("\\\"");
                case '\\' -> out.append("\\\\");
                case '\b' -> out.append("\\b");
                case '\f' -> out.append("\\f");
                case '\n' -> out.append("\\n");
                case '\r' -> out.append("\\r");
                case '\t' -> out.append("\\t");
                default -> {
                    if (ch < 0x20) {
                        out.append(String.format(
                                Locale.ROOT, "\\u%04x", (int) ch));
                    } else {
                        out.append(ch);
                    }
                }
            }
        }
        return out.append('"').toString();
    }

    private static void addField(
            StringBuilder out, String name, String value) {
        if (out.length() > 1) {
            out.append(',');
        }
        out.append(quote(name)).append(':').append(quote(value));
    }

    private static final class JsonFormatter extends Formatter {
        @Override
        public String format(LogRecord record) {
            StringBuilder json = new StringBuilder("{");

            addField(json, "timestamp", record.getInstant().toString());
            addField(json, "severity", record.getLevel().getName());
            addField(json, "logger", record.getLoggerName());

            Object[] params = record.getParameters();
            if (params != null
                    && params.length == 1
                    && params[0] instanceof Context context) {
                addField(json, "service.name", context.serviceName());
                addField(json, "event.name", context.eventName());
                if (context.requestId() != null) {
                    addField(json, "request_id", context.requestId());
                }
                if (context.traceId() != null) {
                    addField(json, "trace_id", context.traceId());
                }
                addField(json, "message", record.getMessage());
                if (context.errorCode() != null) {
                    addField(json, "error.code", context.errorCode());
                }
            } else {
                addField(json, "message", record.getMessage());
            }

            if (record.getThrown() != null) {
                addField(json, "exception.type",
                        record.getThrown().getClass().getName());
            }

            return json.append("}\n").toString();
        }
    }

    private static void publish(
            Level level,
            Instant timestamp,
            Context context,
            String message,
            Throwable error) {
        LogRecord record = new LogRecord(level, message);
        record.setInstant(timestamp);
        record.setLoggerName(LOG.getName());
        record.setParameters(new Object[] {context});
        record.setThrown(error);
        LOG.log(record);
    }

    public static void main(String[] args) {
        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.INFO);

        Handler console = new Handler() {
            @Override
            public void publish(LogRecord record) {
                if (isLoggable(record)) {
                    System.out.print(getFormatter().format(record));
                }
            }

            @Override
            public void flush() {
                System.out.flush();
            }

            @Override
            public void close() {
                flush();
            }
        };
        console.setLevel(Level.ALL);
        console.setFormatter(new JsonFormatter());
        LOG.addHandler(console);

        String trace = "4bf92f3577b34da6a3ce929d0e0e4736";

        try {
            publish(
                    Level.INFO,
                    Instant.parse("2026-01-01T10:00:00Z"),
                    new Context(
                            "order.accepted", "orders-api",
                            "req-101", trace, null),
                    "Order \"A-42\" accepted\nnext step",
                    null);

            publish(
                    Level.WARNING,
                    Instant.parse("2026-01-01T10:00:01Z"),
                    new Context(
                            "payment.retry", "orders-api",
                            "req-101", trace, "DOWNSTREAM_TIMEOUT"),
                    "Retry scheduled",
                    null);

            publish(
                    Level.SEVERE,
                    Instant.parse("2026-01-01T10:00:02Z"),
                    new Context(
                            "payment.failed", "orders-api",
                            "req-102", trace, "PAYMENT_UNAVAILABLE"),
                    "Provider failed",
                    new IllegalStateException("provider unavailable"));
        } finally {
            LOG.removeHandler(console);
            console.close();
        }
    }
}
```

Compile and run in the directory containing the file:

```bash
javac JsonOutputDemo.java
java JsonOutputDemo
```

**Exact stdout (three physical lines):**

```json
{"timestamp":"2026-01-01T10:00:00Z","severity":"INFO","logger":"demo.orders","service.name":"orders-api","event.name":"order.accepted","request_id":"req-101","trace_id":"4bf92f3577b34da6a3ce929d0e0e4736","message":"Order \"A-42\" accepted\nnext step"}
{"timestamp":"2026-01-01T10:00:01Z","severity":"WARNING","logger":"demo.orders","service.name":"orders-api","event.name":"payment.retry","request_id":"req-101","trace_id":"4bf92f3577b34da6a3ce929d0e0e4736","message":"Retry scheduled","error.code":"DOWNSTREAM_TIMEOUT"}
{"timestamp":"2026-01-01T10:00:02Z","severity":"SEVERE","logger":"demo.orders","service.name":"orders-api","event.name":"payment.failed","request_id":"req-102","trace_id":"4bf92f3577b34da6a3ce929d0e0e4736","message":"Provider failed","error.code":"PAYMENT_UNAVAILABLE","exception.type":"java.lang.IllegalStateException"}
```

### Part-by-Part Explanation

**`Context`:** a record holding the fields belonging to a meaningful log event. In this example, `eventName`, `requestId`, `traceId`, and `errorCode` are placed in `LogRecord.parameters` as a simple way to pass context. This is **not JUL's standard MDC mechanism** and not a universal convention for all JUL formatters. In a real application, use a proper event API/schema and context propagation rather than arbitrarily stuffing objects into `LogRecord.parameters` if another formatter or bridge might interpret them differently.

**`LogRecord`:** carries `Level`, timestamp, logger, message, parameters, and Throwable. `setInstant` is available in Java 17; setting a fixed timestamp makes output verification easy. Real events should use actual time with an explicit UTC/offset.

**`JsonFormatter`:** builds a JSON object/record, escapes keys/values with `quote`, and adds `error.code` and `exception.type` only when present. `addField` inserts commas between fields to avoid invalid JSON caused by a trailing comma before `}`.

**`quote`:** turns `"` into `\\"`, newline into `\\n`, and backslash into `\\\\` in the JSON output. Because the first message contains quotes and a newline, yet the formatter keeps them escaped, **JSON Lines still remains strictly three physical lines**.

**`Handler`:** prints one line from the formatter for each permitted record. `LOG.setUseParentHandlers(false)` prevents extra output from parent handlers; `LOG.setLevel(Level.INFO)` allows INFO/WARNING/SEVERE, while the `ALL` handler does not block those three levels. The default `ConsoleHandler` is not used because it typically writes to stderr and has a different default formatter and behavior.

**`Throwable`:** the example records only `exception.type`, omitting the stack trace to keep output compact and stable. Production systems typically need stack traces serialized by an encoder inside a single field (or structured fields) with sanitization and size limits. **Never turn a single stack trace into multiple independent log events.**

### Technical Limitations of the Illustrative Formatter

- `quote` handles common control characters and characters below U+0020, but **does not perform full Unicode string validation**, such as handling unpaired surrogates or oversized strings. Production should use a proven JSON library and data policy.
- `format` assumes `record.getInstant()`, logger name, and message are valid per the demo data. For log records from external sources, handle nulls and unexpected values according to your schema contract.
- Exception messages and full stack traces are omitted from output. If your system needs forensic details, use an encoder that supports `Throwable` and restricts sensitive information.
- Printing via `System.out.print` in the handler is a learning model; in practice, pay attention to UTF-8 charset, batching, flush/shutdown, queuing, and I/O errors.
- There is no retry/ACK, file checkpoint, or Collector. **Successfully printing to stdout does not prove that logs were durably ingested by the backend.**
- `LogRecord.parameters` is used as a lesson-specific context container. Do not assume every JUL handler will understand those parameters.
- A trace ID should correspond only to an actual request/trace. The demo uses a fixed string across two requests for readability; **in production, never reuse a single trace ID for all requests**. Different requests normally have distinct trace contexts unless a defined trace relationship exists.
- Sample data uses ASCII so stdout stays consistent across terminals. For Vietnamese or other non-ASCII text, ensure the source, encoder, and file/console all use UTF-8.

## 6. Verifying JSON Output Instead of Just Eyeballing It

### Checking the Physical Line Count

You should see **three lines**, even though the first message contains a **logical** newline. The `\\n` sequence inside JSON consists of two printable characters `\` and `n`; it is not an LF byte terminating a record. If a single log event breaks across two physical lines, line-oriented shippers may parse it incorrectly.

On a POSIX shell, you can save the output and count lines:

```bash
java JsonOutputDemo > logs.jsonl
wc -l logs.jsonl
```

The expected result from `wc -l` is 3 lines (filename display and spacing vary by shell). On PowerShell, you can use:

```powershell
java JsonOutputDemo | Set-Content -Encoding utf8 logs.jsonl
(Get-Content logs.jsonl).Count
```

The expected count is `3`. PowerShell stdout encoding and redirection behavior can vary across PowerShell/console versions, so verify UTF-8 when logs actually contain Vietnamese text.

### Parsing Each JSON Line

If Python 3 is installed, you can test with the standard parser; this command is only a **verification** step for the example output, not a dependency of the Java program:

```python
import json

with open("logs.jsonl", encoding="utf-8-sig") as f:
    events = [json.loads(line) for line in f if line.strip()]

assert len(events) == 3
assert events[0]["event.name"] == "order.accepted"
assert events[0]["message"] == 'Order "A-42" accepted\nnext step'
assert events[1]["error.code"] == "DOWNSTREAM_TIMEOUT"
assert events[2]["severity"] == "SEVERE"
assert events[2]["exception.type"] == "java.lang.IllegalStateException"
print("JSONL_VALID events=3")
```

**Expected stdout** if all assertions pass:

```text
JSONL_VALID events=3
```

Make sure to use `json.loads(line)` for **each line**, not `json.load(file)` on the entire JSON Lines file as if it were a single JSON object or array. If the parser reports `Extra data` on the first line when loading the whole file, the JSON Lines file is not necessarily invalid—you may simply be parsing it the wrong way.

### Testing with Intent

Beyond the parser, verify these functional characteristics:

1. Every log event includes all required fields.
2. Timestamp has an offset and matches when the record was created.
3. `severity` preserves the JUL/backend mapping.
4. `event.name` belongs to a managed catalog and does not change unpredictably with the message.
5. `error.code` is present on corresponding error events and never set to `"null"`.
6. `request_id` and `trace_id` do not leak or mix across concurrent requests.
7. Messages with quotes, backslashes, newlines, and Unicode parse cleanly.
8. Stack traces and exception causes do not break JSON Lines.
9. No passwords, tokens, or out-of-policy PII appear.
10. The Collector/backend parses events into **queryable fields**, rather than leaving a raw JSON string inside `message`.

## 7. Adding JSON Output to an SLF4J + Logback Application

For real applications using SLF4J and Logback, use a **dedicated JSON encoder** instead of writing a custom `Formatter` attached to JUL. The exact choice depends on your logging backend, dependencies, and project versions.

A common example is **Logstash Logback Encoder** via the `net.logstash.logback:logstash-logback-encoder` dependency. You must pick a version **compatible** with your Logback/SLF4J/Jackson/Java versions; do not copy an arbitrary version number without checking the dependency tree and minimum Java requirements.

Assuming the compatible dependency is added, `logback.xml` or `logback-spring.xml` can be configured as:

```xml
<configuration>
    <appender name="JSON_STDOUT"
              class="ch.qos.logback.core.ConsoleAppender">
        <encoder class="net.logstash.logback.encoder.LogstashEncoder"/>
    </appender>

    <root level="INFO">
        <appender-ref ref="JSON_STDOUT"/>
    </root>
</configuration>
```

This is an **illustrative configuration requiring an external library**, not a Java 17 JDK-only example. Verify the encoder class, classpath, Logback/provider API, which config file is loaded, and the actual field names emitted by your chosen version.

### Dependency Checklist

- Are the SLF4J API and **one matching provider/backend** on the classpath?
- Are `logback-classic` and `logback-core` on compatible matching versions?
- Does the JSON encoder support the exact Logback version in use?
- Are there two competing SLF4J providers or a bridge creating a loop?
- If the application uses Spring Boot, is the config file named and located where Boot loads it?
- Is the encoder dependency present **at runtime**, not just in test scope?
- Do startup logs report any appender/encoder initialization errors or silently fall back to the old console pattern?

Add dependencies via Maven/Gradle using versions managed by your project; if the backend lacks the encoder, the XML may still exist while runtime fails to produce the expected JSON output. **Always run the application and parse real log events.**

### How to Add Extra Fields?

In Logback, you can use **MDC** and/or structured arguments/key-value logging depending on the encoder and SLF4J version. SLF4J example:

```java
logger.info("event=order.accepted orderId={}", orderId);
```

This is a **fragment**, not standalone: it requires `logger`/`orderId` and dependencies. If the formatter only serializes the message into a JSON string, `orderId` may stay inside `message` instead of becoming its own JSON key. To achieve a proper schema, use the encoder's structured fields capability or an event wrapper that holds dedicated fields.

Example with MDC when the framework uses SLF4J:

```java
try (var ignored = org.slf4j.MDC.putCloseable("request_id", requestId)) {
    logger.info("order accepted");
}
```

This fragment requires SLF4J dependencies and the `requestId` variable; output will contain the `request_id` field **only if the encoder is configured to emit MDC**. With `putCloseable`, the key is removed when the resource closes; in production, check **whether the previous context needs to be restored**, especially in nested scopes, and manage propagation properly across async tasks. Never treat MDC as proof of an authenticated actor.

### Should Each Level Have Its Own Schema?

Usually it is best to use a **consistent schema across INFO/WARN/ERROR**, adding conditional fields as needed. For example, `error.code` and `exception.type` appear when an error actually occurs, while `event.name`/`service.name`/timestamp are always present.

Do not turn each severity into a completely different JSON format that forces collectors to maintain multiple parsers. At the same time, there is no need to inject `"exception":""` into non-error INFO logs just to populate every key. Define required and optional fields clearly in your schema contract.

## 8. Log4j2 and Other Java Stacks

If your project uses Log4j2, do not use the Logback XML file shown above. Log4j2 supports JSON layout options; one approach is **JsonTemplateLayout** with the corresponding `log4j-layout-template-json` module.

Illustrative Log4j2 configuration snippet:

```xml
<Configuration status="WARN">
  <Appenders>
    <Console name="JSON" target="SYSTEM_OUT">
      <JsonTemplateLayout eventTemplateUri="classpath:EcsLayout.json"/>
    </Console>
  </Appenders>
  <Loggers>
    <Root level="info">
      <AppenderRef ref="JSON"/>
    </Root>
  </Loggers>
</Configuration>
```

This configuration **must be verified against your actual version and dependencies**. The `EcsLayout.json` template is a sample template commonly bundled via the related module in supported versions; do not assume every Log4j2 version or packaging includes this template on the classpath. You can use a different template matching your organization's schema.

A system using JUL can keep its own Handler/Formatter or use an appropriate bridge/provider to route JUL logs into a shared backend. **Do not enable two parallel pipelines without checking for duplicate events or bridge loops.**

A Spring Boot application may support structured logging depending on its version and stack, though property names and formats evolve across releases. Prefer framework-supported capabilities when compatible, or use a JSON encoder standardized by your operations team. After making changes, verify the schema and field names **against actual output**.

## 9. Timestamp, Severity, and Standard Field Names

### Timestamp

`Instant.now()` captures the actual instant in the JVM; the formatter should output UTC/offset formats understood by the backend parser. Event time differs from ingest time:

```text
event happened:    2026-01-01T10:00:00Z
collector received:2026-01-01T10:00:03Z
searchable:        2026-01-01T10:00:07Z
```

If a dashboard uses event time, the record belongs to minute 10:00; if searching by ingest time, it falls in a different window. When debugging "missing logs," always check the timezone and whether the time window accounts for ingest lag.

### Severity

JUL uses `WARNING`/`SEVERE`; SLF4J uses `WARN`/`ERROR`. An organization can map them to common severity values per backend/OTel standards, but **never rename them arbitrarily** in ways that break log searches or alerts. If a JSON encoder emits `level` while the backend expects `severity`, define an explicit mapping step or schema adapter.

### Field Types and Optional Values

In valid JSON:

```json
{"http.status_code":503,"duration_ms":12.5,"retryable":false}
```

These values are true numbers and booleans, suitable for range queries and aggregations. Conversely:

```json
{"http.status_code":"503","duration_ms":"12.5","retryable":"false"}
```

All values here are strings: some backends can coerce them, while others trigger schema errors or incorrect sorting/querying. In the JDK-only demo, all present fields are strings because the goal is escaping and JSON Lines; **when expanding to a real schema, support typed JSON values** and avoid forcing every metric field into a string.

### Keys Containing Dots

`service.name`, `event.name`, and `exception.type` are intuitive keys, but different backends may require mapping. If a system uses OpenTelemetry log records, resource attributes and record attributes also have distinct places. Do not assume a flat JSON object automatically becomes an OTel log model simply by using dotted key names.

## 10. Exceptions and Stack Traces When Moving to JSON

A Java exception typically carries:

- Class/type: `java.net.SocketTimeoutException`, `IllegalStateException`…
- Message, which may contain user content or infrastructure details.
- Cause chain and suppressed exceptions.
- Stack trace consisting of multiple frames and newline characters.

If formatted as text and shipped line by line on LF, a single exception can split into **multiple fragmented events**, distorting log counts and breaking correlation. A JSON encoder should keep the exception inside **one log event** using appropriate fields; newlines are escaped as `\n` inside the JSON string. Some encoders support root-cause fields, stack-trace arrays, or nested structures; no single schema applies universally to every backend.

### Choosing Log Levels Based on Final Outcome

- Single-attempt timeout that will be retried: log as WARN or a diagnostic event; **do not treat the final request as ERROR** if a retry succeeds.
- Retries exhausted and request/job fails: log ERROR at the final boundary with the error code and necessary `Throwable`.
- User 400 validation error: not necessarily a server ERROR even if an exception is thrown.
- Async job fails after returning HTTP 202: log/record metric outcome in the job worker; do not retroactively alter the HTTP status already returned.

If an exception is logged in full at the DAO, service, and controller layers, JSON output will still produce **three separate events**. Switching to JSON does not automatically solve duplicate semantic logging; choose an owner at the boundary and use distinct event names if you need to record both individual attempts and the final outcome.

### Do Not Dump an Entire Throwable Into an Uncontrolled Field

`Throwable.toString()` or a stack trace can expose file paths, SQL, or payloads. Enforce size limits, redaction, and retention; very large errors can exceed the agent/Collector's max record size. Never put an entire stack trace into a metric label.

## 11. Correlation Fields and MDC/ThreadContext

Useful JSON logs typically include `request_id`, `trace_id`, and `span_id` as a request flows through multiple components. However, IDs must be **generated or validated at a trusted ingress point**; never trust unverified client-supplied headers to determine tenant, actor, or access permissions.

In Logback via SLF4J, `MDC` helps attach context:

```java
org.slf4j.MDC.put("request_id", requestId);
try {
    logger.info("event=order.accepted");
} finally {
    org.slf4j.MDC.remove("request_id");
}
```

This code is a **fragment**, not standalone, and does not restore a previous value if nested MDC scopes exist. Whether the encoder outputs MDC depends on configuration. **MDC is typically thread-bound**: when crossing `ExecutorService`, `CompletableFuture`, or reactive chains, context does not propagate automatically across all tasks. Use appropriate framework/context propagation and clean up properly when thread pools reuse threads.

One request can emit many JSON events, and one trace consists of many spans. **Never use trace IDs or request IDs as metric labels** because cardinality grows with every request; keep IDs in logs/traces for searching.

### When There Is No Request Context

Startup events or background schedulers may lack a request ID. Allow optional fields to **be absent** or use a meaningful context value per your contract, rather than fabricating `"request_id":"null"` as a real identifier. Do not conflate a job ID with a request ID if their semantics differ.

## 12. Writing JSON to Stdout or a File?

### Stdout/Stderr

In containers/Kubernetes, Java apps typically write to stdout/stderr, and the container runtime or node agent collects and ships logs centrally. Advantage: no need to manage rolling files inside the container, and the collection pipeline can attach pod/service metadata. However, check log line limits, charset, runtime rotation, event size, shutdown/flush behavior, and collector processing.

Do not automatically emit the same event to **both** stdout and a file with two agents collecting them, unless you have distinct sinks or deduplication policies. Both may ingest the same JSON event, creating duplicate data.

### File

If an application requires file output, you can use JUL `FileHandler` or Logback `RollingFileAppender` with a JSON formatter/encoder. Keep in mind:

- UTF-8 encoding in the handler/encoder to prevent corrupted Vietnamese characters.
- JSON Lines with one event per line and a trailing newline on each record.
- Rolling file policy (rename/create or copytruncate) and how the shipper tracks file identity.
- Byte-level **checkpoints/offsets**, partial lines, multiline handling, and max record size.
- Flush/close on shutdown and failure policy when the disk is full.
- Read/write permissions, local retention, and redaction at the source.

JSON output **does not solve** file shippers dropping logs during rotation or backpressure. That is a delivery problem, not a formatting problem.

### OTLP Logs

Some applications send `LogRecord` directly to a Collector via an OpenTelemetry-compatible SDK/appender/exporter without writing JSON Lines files. In that case, JSON output is **not strictly required**; signals can be transmitted via OTLP and converted to the backend's format downstream. If your exercise goal is "add JSON output," identify where JSON is needed: stdout, file, Collector output, or storage backend. There is no need to serialize JSON and then wrap it inside OTLP when the pipeline already supports structured attributes.

## 13. Integrating with Shippers and Collectors

A typical pipeline:

```text
Java JSON stdout
    |
container runtime / local file
    |
file shipper / node agent / Collector filelog receiver
    |
JSON parser
    |
resource enrichment + privacy filter + routing
    |
backend ingest + index
    |
search by service.name/event.name/request_id
```

At the shipper/Collector layer, verify:

1. **Reader framing:** each LF delimits one record; embedded newlines inside messages must be escaped.
2. **JSON parsing:** parse into structured fields rather than leaving the entire JSON inside a single `body` string if the backend needs field-level queries.
3. **Timestamp mapping:** use the event timestamp when trustworthy, keeping ingest time separate.
4. **Severity mapping:** JUL `SEVERE` can be mapped to the backend's ERROR level; exact mapping depends on processor/schema.
5. **Resource metadata:** service, environment, host, pod, container, and version from trusted sources.
6. **Redaction/filtering:** keep tokens/PII out of the backend; strip sensitive data as close to the source as possible.
7. **Transport/ACK:** reaching the Collector does not by itself prove the event is indexed and queryable in storage.
8. **Cardinality:** never use `request_id` or `trace_id` as stream/metric labels that create unbounded series.
9. **Parse failures:** oversized lines, malformed JSON, or type mismatches need counters, alerts, and handling policies.
10. **Retention/permissions:** ingest permissions differ from search/export permissions; enforce access control by tenant/environment.

**There is no single universal YAML that works for all Filebeat, Fluent Bit, Vector, or OpenTelemetry Collector setups.** Choose the parser/input/output matching your exact version and distribution, then test with a canary event carrying a unique ID and query it back in the backend within a measured deadline.

## 14. Step-by-Step Migration in an Existing Service

A safe rollout approach:

### Step 1 — Audit the Current State

Document the logger facade/backend, output sinks, log formats, records/sec, bytes/sec, exception handling, MDC fields, file rotation, Collector parsers, and active dashboard searches. Identify who depends on the legacy text pattern.

### Step 2 — Finalize Schema and Data Policy

Create an event catalog: `event.name`, severity, service, timestamp, request/trace IDs, outcome/error code, exception type, and optional fields. Define field names/types/sources, versioning, size limits, and redaction/retention rules.

### Step 3 — Choose a Compatible Encoder

- **JDK-only/prototype:** try a formatter like the program in Section 5.
- **SLF4J + Logback:** use a proven JSON encoder with compatible dependencies.
- **Log4j2:** use a JSON layout/template matching your version and schema.
- **Spring Boot:** check structured logging support and providers for your exact version.
- **OTel instrumentation:** if you already have an OTLP log pipeline, consider keeping structured attributes instead of forcing JSON text.

### Step 4 — Test Locally and in Staging

Ensure each event is one parseable JSON line; verify optional values, exceptions, Unicode, newlines, and quotes. Test context propagation across thread pools, 404/401/403 responses, async jobs, and source redaction.

### Step 5 — Synchronize Parsers and Saved Queries

If the backend previously used regex parsers for text, switch to the corresponding JSON parser/mapping **before or alongside** the rollout. During transition, both JSON and text from different versions may coexist; use a `schema_version` field or a source/version/format discriminator if the backend needs it.

### Step 6 — Canary Deployment

Enable JSON output on a single instance or small group. Compare log event counts, parse errors, ingest lag, dropped records, bytes/s, CPU/GC, latency, and searchability by request/trace ID. Verify ERROR events are not lost due to misconfigured loggers/appenders.

### Step 7 — Expand and Roll Back

Gradually expand across instances while keeping a rollback path to the old configuration that does not break dashboards or alerts. Once all clients/collectors have migrated, retire the old parser on schedule; do not delete historical data before retention expires. Document the schema and operational runbooks for other services.

**Do not migrate production by replacing a file pattern with a hand-assembled JSON string and deploying immediately.** Format changes can affect alerts, pipelines, costs, and query permissions even when business logic is unchanged.

## 15. Detecting Broken JSON and Log Injection

Common failure cases:

| Input | If Handled Improperly | Proper Solution |
| --- | --- | --- |
| Double quote `"` | JSON string terminates early | Escape as `\"` |
| Backslash `\` | Invalid escape sequence | Escape as `\\` |
| Newline/CR | Single event splits into multiple lines | Encode `\n`/`\r` inside string |
| Tab/control characters | JSON parser rejects the record | Escape control chars per JSON spec |
| Multi-byte UTF-8 | Characters corrupted on mismatched encode/decode | Use consistent UTF-8 and decoder policy |
| Oversized string | Collector truncates/drops or hits ingest quota | Size limits + parse/drop counters |
| Unexpected field type | Mapping conflict, broken queries | Schema validation/typed serializer |
| Nested object/array | Text formatting breaks | Structure-aware JSON serializer |
| Multi-frame Throwable | One exception becomes multiple log lines | Encode stack in one field/event |
| Fake timestamp/level input | Enables log injection when concatenating text | Server-side metadata and JSON encoding |

**Escaping does not replace sanitization.** A properly JSON-encoded token is still a leaked token. Never log raw `Authorization` headers, cookies, passwords, signed URLs, private keys, sensitive SQL parameters, or full request bodies unnecessarily.

If a user-supplied message contains something resembling `"severity":"ERROR"`, JSON escaping ensures it remains **part of the message field content** and cannot break out into a top-level key. However, if the application lets clients directly overwrite context fields like `severity`/`service.name`/`tenant_id`, the encoder cannot fix that trust boundary issue.

## 16. Log Levels and JSON Output Do Not Replace Each Other

When JSON output is enabled, logger levels still govern filtering:

- JUL `INFO` allows INFO, WARNING, and SEVERE; `FINE` may be blocked.
- SLF4J `INFO` allows INFO/WARN/ERROR, subject to backend filters.
- Encoders/handlers can have their own levels/filters and may drop records even when the logger allows them.
- JSON formatting does not automatically enable DEBUG, nor does it guarantee ERROR logs reach the backend.
- Call sites using eager argument evaluation still perform expensive work even when the level is disabled.

Example of eager logging:

```java
logger.fine("state=" + expensiveSnapshot());
```

If `FINE` is disabled, `expensiveSnapshot()` is still evaluated before calling the logger. JUL supports suppliers:

```java
logger.log(Level.FINE, () -> "state=" + expensiveSnapshot());
```

This snippet is illustrative (requiring a logger and function), and a supplier avoids constructing the message when the level is disabled. In SLF4J, parameterized logging defers formatting inside the backend, but expressions passed as arguments still execute before the method call unless guarded or wrapped in a supplier.

JSON encoding can consume more CPU and allocations than a simple pattern depending on the library, field count, and workload. Benchmark on your real stack rather than concluding JSON is always faster or slower than text from a tiny micro-test.

## 17. Cost, Latency, and Durability

An encoder change can increase record size due to key names and structured metadata, or decrease it by eliminating redundant messages and unnecessary stack traces. Measure:

- Log events/s and average/percentile bytes per event.
- Formatter/encoder CPU, allocations/op, GC, and throughput.
- Counts of request logs and exceptions; log levels do not constitute business SLIs.
- Async queue depth, drops, backpressure, and export retries.
- Collector parse errors, mapping rejects, and ingest lag.
- Storage/index cost and query latency.
- Impact on p95/p99 request latency when the sink is slow.
- Encoding/decoding of Vietnamese text and special fields.

A large JSON event printed to stdout may still be chunked by the container runtime if it exceeds the logging driver's or Collector's limit. **A single `System.out.print` call is not an end-to-end atomic log delivery contract** across all environments. Therefore, cap record sizes, verify framing/aggregation, and choose shippers and sinks sized for your load.

### Delivery Semantics

Possible failure scenarios include:

- App prints the log, then crashes before the agent reads it.
- Agent reads the log, but destination ACK is lost; a subsequent retry creates a duplicate.
- Collector receives the log, but the backend has not indexed it yet; an immediate search returns empty.
- Log sampling/filtering prevents an event from being emitted or retained.
- File rotates or is deleted before the shipper finishes reading the tail.

JSON output solves **format/schema**, not **at-least-once**, exactly-once, or atomicity with business transactions. For mandatory audit trails, use a dedicated audit store/outbox and durability contract, not just a JSON INFO event.

## 18. Common Diagnostic Scenarios

| Symptom | Likely Cause | How to Check |
| --- | --- | --- |
| Console still shows text | Encoder not loaded, wrong config path, wrong backend | Check dependencies, provider, startup config diagnostics |
| No logs at all | Logger/appender level filtering, appender not attached to root | Check logger + handler/appender + additivity |
| Invalid JSON fails parsing | Raw string concatenation, unescaped quotes/newlines, truncated record | Parse line by line, inspect encoder and max size |
| Stack trace splits into multiple records | Using text formatter or line-based shipper input | Use JSON exception converter or multiline policy |
| Backend only has `message` containing JSON text | Collector not parsing/mapping | Check parser/transform and indexed fields |
| `request_id` set in code but missing in output | Encoder not emitting MDC/context | Check context + encoder + raw output bytes |
| Request IDs mixed across threads | MDC leak or missing async propagation | Check context scopes, cleanup, and tests |
| INFO appears but ERROR is missing | Misconfigured filter, sampling, or output routing | Check logger/appender, Collector, and backend rules |
| Duplicate identical JSON events | Root + named logger appenders, stdout + file, or shipper retry | Check additivity, source ownership, and event IDs |
| JSON parser fails on type | Schema drift or index mapping conflict | Check field types, version, and migrations |
| Valid JSON missing in search | Ingest lag, wrong project/tenant/time, retention/permissions | Compare event vs ingest time, agent/backend metrics |
| Logs contain tokens/PII | Call site dumps request, encoder emits all MDC fields | Data minimization, redaction, field allowlist |
| Corrupted Vietnamese characters | Charset mismatch across JDK/terminal/file/agent | Enforce UTF-8 end to end |
| Backend costs spike sharply | JSON keys, wide fields, large exceptions, duplicates | Measure bytes/event, event rate, and sampling policy |
| JSON output fine locally, split in container | Event too long / runtime logging limit | Size cap and integration test on real runtime |

During an incident, trace from **application → encoder → stdout/file → shipper/Collector → backend**. Find the first stage where the event ID disappears—do not tweak dashboard queries before confirming data was ingested under the expected schema.

## 19. Practical Verification Scenarios

### A. Value and Escaping Checks

- [ ] Exactly 3 physical JSON lines appear after running the demo.
- [ ] Each line parses as a single JSON object.
- [ ] `timestamp` is ISO-8601 with `Z`.
- [ ] Severity values are `INFO`, `WARNING`, `SEVERE` in order.
- [ ] `event.name` values are `order.accepted`, `payment.retry`, `payment.failed` in order.
- [ ] The first event's message contains quotes and a **logical** newline while remaining one physical line.
- [ ] The second event has `error.code=DOWNSTREAM_TIMEOUT`.
- [ ] The third event has `exception.type=java.lang.IllegalStateException`.
- [ ] No `"null"` strings or trailing commas appear in the JSON.
- [ ] No output from parent JUL handlers emits extra text.

### B. Framework Checks

- [ ] Logback/Log4j2 config loads properly and the encoder dependency is present at runtime.
- [ ] JSON fields are parsed by the backend according to the agreed schema.
- [ ] Logger severity, exception formatting, and MDC are encoded properly.
- [ ] Parent/additivity and stdout/file ownership do not cause duplicates.
- [ ] Switching between text and JSON supports rollout/rollback without breaking alerts or search queries.
- [ ] Log sources consistently use UTF-8 and line framing.
- [ ] Secret/PII redaction has been tested at both source and Collector.
- [ ] Source metadata (service/environment/version) is trusted and cannot be overridden by clients.

### C. Failure and End-to-End Observability Checks

- [ ] Send a canary event with a unique event ID and retrieve it in the backend by ID.
- [ ] Collector JSON parse errors increment metrics/alerts rather than failing silently.
- [ ] Network loss, backend 429/503, full queues, and restarts do not lead to false delivery assumptions.
- [ ] Log retention and search/export permissions are properly scoped.
- [ ] Thread pools and async requests do not mix request/trace IDs.
- [ ] Event size limits and large `Throwable` stacks follow policy.
- [ ] Request metrics (count/error/latency) are tracked independently of log line counts.
- [ ] Mandatory audit/security events use a durable path independent of INFO filtering/sampling.

## 20. Extensions: Making JSON Output More Realistic

Once the basic demo runs cleanly, proceed step by step with these extensions and verify each with parsers/tests:

1. **Add `schema_version`:** helps the backend handle migrations when adding, removing, or renaming fields.
2. **Add numeric fields:** `http.status_code` as a number and `duration_ms` as numeric, rather than forcing them into strings.
3. **Add Throwable stack traces:** encode inside a redacted, size-capped JSON string field.
4. **Add context propagation:** unique request ID/trace ID per request, using proper scoping and cleanup across async tasks.
5. **Add a UTF-8 formatter/file sink:** write JSONL and test shipper reading across byte offsets and rotation.
6. **Add schema contract tests:** fail the build if a critical event is missing fields or has wrong types.
7. **Add Collector integration tests:** verify events reach the backend and are queryable by `event.name`/`request_id` within a timeout, with self-metrics.
8. **Add a production JSON encoder:** replace the custom formatter with a proven library and compare output, field count, and performance.
9. **Add security tests:** ensure tokens, raw URLs, and secrets inside exceptions do not leak through the formatter/collector.
10. **Add dashboards/queries:** query `payment.failed` by service and time window, group by error code, and link traces when available.

Do not declare success simply because stdout starts with `{`. The definition of done is **every event parses cleanly, the schema is stable, context is trustworthy, no sensitive data leaks, and events are genuinely queryable at the destination**.

## 21. Common Mistakes When "Adding JSON Output"

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Concatenating strings `"{\"message\":\"" + message + "\"}"` | Quotes/newlines break JSON, log injection | Use a standard JSON encoder/serializer |
| Only wrapping text message in JSON | No structured fields for searching | Put event name, code, service, correlation in separate keys |
| Using `json.load` on an entire JSONL file | Parser reports extra data | Parse line by line with `json.loads` |
| Writing stack traces across multiple physical lines | One error becomes many events | Escape stack inside a field or use multiline handling |
| Writing `"status":"503"` when schema expects a number | Range/aggregations may fail | Serialize using proper JSON types |
| Setting all optional fields to `"null"` | Queries mistake missing values for literals | Omit or use JSON null per schema |
| Forgetting to attach the encoder to the root appender | Text logs still appear | Verify backend/runtime config |
| Putting Logback XML into Log4j2 | Layout/plugin unrecognized | Use configuration matching your backend |
| Assuming SLF4J placeholders become JSON fields | Message remains a plain string | Use structured arguments/MDC with a supporting encoder |
| Dumping all of MDC into output unfiltered | Can leak tokens/tenant data | Use an MDC allowlist, trusted fields, and cleanup |
| Reusing a fixed trace ID for all requests | Broken correlation | Propagate real trace context |
| Logging raw request bodies/headers at DEBUG | Leaks secrets when diagnostics are enabled | Enforce data minimization at all levels |
| Not updating the Collector parser | JSON stays trapped inside `message`; fields unindexed | Configure JSON parsing/enrichment/mapping |
| Collecting the same event from both file and stdout | Duplicate records, higher cost | Use a single collection path or deduplication |
| Assuming JSON guarantees audit durability | Logs still lost on crash/filter/drop | Use a dedicated outbox/audit storage |
| Ignoring ingest lag/retention | Assuming missing logs mean no event occurred | Use event ID canaries and pipeline metrics |

## 22. Exercise Completion Checklist

- [ ] Compiled and ran `JsonOutputDemo.java` successfully on Java 17+?
- [ ] Output consists of **3 JSON Lines**, one physical line per log record?
- [ ] Messages containing quotes/newlines are escaped and parse without error?
- [ ] Includes timestamp, severity, logger, service, event name, and correlation fields?
- [ ] Error code and exception type appear only when meaningful?
- [ ] Distinguished typed keys from message text; avoided "fake structured logging" via regex?
- [ ] Confirmed the output schema aligns with indexing/Collector/backend?
- [ ] Decided appropriately between stdout/file/OTLP and avoided duplicate collection?
- [ ] If using Logback/Log4j2, verified JSON encoder/layout and dependency versions?
- [ ] Verified logger/handler/appender levels and actual output, not just XML?
- [ ] Enforced field size limits, escaped control chars, UTF-8 handling, and `Throwable` handling?
- [ ] Confirmed no tokens, passwords, cookies, or unnecessary PII appear in logs?
- [ ] Verified correlation IDs come from trusted context and do not leak across thread pools?
- [ ] Added parser/tests proving every JSON line is valid and matches the schema?
- [ ] Verified via end-to-end canary that logs are ingested and queryable in the backend?
- [ ] Measured parse failures, drops, queues, throughput, and log cost after rollout?
- [ ] Protected mandatory audit logs with a separate retention/durability path if needed?

**Conclusion:** adding JSON output is the transition from **hard-to-parse text lines** to **structured log events**. In Java, what matters is not merely a formatter emitting `{` and `}`, but **one valid JSON line per event**, a schema with meaningful fields, proper escaping, stripping sensitive data at the source, and a parser/backend that understands those fields. Start with the standalone JUL example, validate JSON Lines with a parser, and then adopt the right JSON encoder for Logback/Log4j2 or your telemetry stack in production. That is the foundation for reliable searching, correlation, alerting, and incident investigation.
