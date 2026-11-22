# Log Parsing in Java Logging and Observability

## 1. What Is Log Parsing?

**Log parsing** is the process of interpreting a log record in text, JSON, or another data transmission format into **fields with explicit names and types**: timestamp, level, service, logger, thread, requestId, traceId, eventCode, message, and error information. This is a critical stage for turning logs from human-readable text into data that can be searched, filtered, aggregated, and alerted on in an **Observability** platform.

Example of a text line written by a Java application:

~~~text
2026-11-10T03:30:05Z INFO [http-4] com.example.OrderService - requestId=req-42 event=ORDER_CREATED orderId=42
~~~

When parsed according to an agreed-upon format, the system can extract:

~~~json
{
  "timestamp": "2026-11-10T03:30:05Z",
  "severityText": "INFO",
  "thread": "http-4",
  "logger": "com.example.OrderService",
  "requestId": "req-42",
  "eventCode": "ORDER_CREATED",
  "orderId": "42"
}
~~~

The JSON here is an **illustrative expected result**, not something obtained automatically just by reading text. The parser must know where fields start and end. Unstructured data without a contract can match a regex and still be extracted with the **wrong meaning**.

Benefits of proper parsing:

- Find every ERROR for a service within a time range, instead of doing free-text searches.
- Correlate requestId/traceId between logs and distributed traces.
- Count events by eventCode or errorCode without depending on changing messages.
- Query logs by time, environment, service, and outcome.
- Track parse failures to detect schema drift and pipeline issues.
- Reduce the need for investigators to read entire raw logs filled with unnecessary data.

**Remember:** a parser cannot recover an event that was lost, nor can it accurately generate a requestId if the source did not record it.

## 2. Distinguishing the Stages of a Log Pipeline

~~~text
Java application
      |
      | SLF4J / JUL / Logback / Log4j 2
      v
LogEvent (timestamp, level, MDC, message, throwable)
      |
      v
Layout / encoder: text, JSON Lines, ...
      |
      v
Stdout / local file / socket
      |
      v
Shipper / agent (Filebeat, Fluent Bit, ...)
      |
      | framing, multiline, decode
      v
Parser / Collector / transform
      |
      | normalize time, severity, context, redact
      v
Index / storage / search
      |
      v
Query, dashboard, alert, tracing correlation
~~~

| Stage | Role | Common Failures |
| --- | --- | --- |
| Logging API | Create event and context | Missing MDC or accidentally logging personal data |
| Layout/encoder | Serialize the event | Pattern changes break the parser |
| Framing/multiline | Group event boundaries correctly | Stack trace split into multiple events |
| Parsing | Convert data into typed fields | Wrong timestamp conversion or shifted fields |
| Transform | Enrich, mask, and normalize | Dropping fields or assigning the wrong service |
| Indexing | Store by schema for querying | Mapping conflict or ingest lag |
| Dashboard | Query/display | Wrong counts due to parsing, retries, or duplicates |

**Parsing is not synonymous with shipping**: an agent may forward an entire text blob to a collector without parsing it yet. **Parsing is also not synonymous with indexing**: a collector may parse successfully, yet the backend rejects the document due to mapping or quota limits.

When investigating, you need to know whether the log broke at the **source**, **in the parser**, **during schema transformation**, or **at indexing**. Looking only at an empty dashboard will not identify the root cause.

## 3. Two Strategies: Structured JSON and Legacy Text

### 3.1. Structured Logging at the Source

If you have permission to modify the logging configuration, prefer emitting events in a structured schema using JSON Lines: **one complete JSON object per physical line**, with newline characters in messages/exceptions properly escaped.

~~~json
{"timestamp":"2026-11-10T03:30:05Z","level":"INFO","service":"order-service","eventCode":"ORDER_CREATED","requestId":"req-42","durationMs":17}
~~~

A JSON decoder can preserve data types (`durationMs` as a number, not the string `"17ms"`) and handle quotes, backslashes, Unicode, and nested objects. It depends far less on whitespace positions than a regex parser on text. However, valid JSON can still violate the schema, contain PII, miss `requestId`, or have fields with the wrong type; **validation is still required**.

Do not build JSON manually via string concatenation when messages come from user input, because quotes, newlines, and backslashes can corrupt the payload or inject forged fields.

### 3.2. Parsing Legacy Text Logs

Example output from PatternLayout:

~~~text
2026-11-10T03:30:05Z INFO [main] com.example.App - Application started
2026-11-10T03:30:06Z ERROR [worker-2] com.example.DB - Query failed
~~~

This can be parsed with a fixed-delimiter template (Dissect) or regex/Grok. You must know the actual format: whether the timestamp has spaces, whether the level is padded, whether the thread is in square brackets, whether the logger has variable length, and whether the message can contain hyphens or newlines.

A log line such as `"Order accepted user=alice|admin"` is unsafe if the parser splits on `"|"` while the message is allowed to contain `"|"`. With free-form text logs, **the format itself is a technical contract**, not just a presentation detail.

### 3.3. Comparison

| Characteristic | JSON Lines | Text + Parser |
| --- | --- | --- |
| Type preservation | Direct if the schema is correct | Must additionally parse numbers/dates/booleans |
| Handling quotes/newlines | Serializer handles escaping | Must define custom delimiters/escaping |
| Resilience to message changes | Better if the schema stays stable | Easily breaks when the pattern changes |
| Java stack traces | Can reside in an escaped JSON field | Usually requires multiline grouping |
| Legacy systems | May require changing appender/config | Easier to add at the collector |
| Common issues | Schema drift, nested fields, PII | False matches, multiline, regex cost |

You do not necessarily have to change every legacy application immediately. However, when designing new systems, using an explicit schema at the source usually reduces long-term parser maintenance cost.

## 4. Which Fields Should a Log Schema Standardize?

| Field | Suggested Type | Purpose |
| --- | --- | --- |
| timestamp | Standardized UTC/offset instant | When the event was created |
| observedTimestamp | Observation/ingest instant | Measure lag between source and collector |
| severityText | String | Original level such as INFO, WARN, SEVERE |
| severityNumber | Number per convention | Compare severity across frameworks |
| service.name | String | Service emitting the event |
| logger.name | String | Logger/class emitting the log |
| thread.name | String | Executing thread, useful for Java |
| requestId, traceId, spanId | Validated strings | Trace and correlate events |
| eventCode, outcome | Code with a defined value set | Stable queries/alerts |
| body/message | Text or structured | Event description |
| exception.type | String | Group error types |
| exception.stacktrace | Protected text | Root-cause investigation |
| parser.version, parse.status | String | Trace log interpretation |

Individual fields can be **optional** depending on the event type. Startup logs do not necessarily have a `requestId`; a scheduled job may have a `jobId` instead. Do not fabricate dummy IDs just to fill the schema.

The **OpenTelemetry Logs Data Model** defines top-level fields such as Timestamp, ObservedTimestamp, SeverityText, SeverityNumber, Body, TraceId, SpanId, Resource, Attributes, and InstrumentationScope. In this model, `service.name` typically belongs in Resource metadata, while `requestId` can live in Attributes. When mapping to another platform such as Elastic Common Schema, you must define the corresponding fields and types rather than copying names arbitrarily.

Some conventions also specify nanosecond-precision timestamps; that does not mean the timestamp strings of every real-world Java system actually have nanosecond precision. Do not add fake precision.

## 5. Distinguishing Event Timestamp from Ingest Timestamp

Consider these strings:

~~~text
2026-11-10T03:30:05.123Z
2026-11-10T10:30:05.123+07:00
2026-11-10 10:30:05,123
1762745405123
~~~

The first two lines include offset information, so they can be normalized to the same UTC instant when representing the same point in time. The third line **has no timezone**, so the parser must know the source application's timezone rather than guessing based on where the collector runs. The last line may be epoch milliseconds, but a contract is needed to confirm the unit; epoch seconds, milliseconds, and nanoseconds differ dramatically.

In Java:

~~~java
// Fragment; requires importing java.time.Instant and OffsetDateTime.
Instant a = Instant.parse("2026-11-10T03:30:05Z");
Instant b = OffsetDateTime
        .parse("2026-11-10T10:30:05+07:00")
        .toInstant();
System.out.println(a.equals(b)); // true
~~~

If you parse a local datetime using `ZoneId.systemDefault()` on the collector machine, the result can change when deployed to a different container or region. Use the **source timezone declared in the schema**.

A pipeline should preserve both **event timestamp** and **observed timestamp**. The difference between them helps reveal queue lag, network delay, source clock skew, or shipper issues. Never replace the source timestamp with the ingest time and treat every event as having occurred when the collector received it.

## 6. Standalone Java 17+ Example: Parser with Contract and Validation

This exercise simulates legacy logs consisting of exactly **5 fields** separated by `"|"` with the structure:

~~~text
occurredAt|level|service|requestId|eventCode
~~~

Specification:

- `occurredAt`: ISO-8601 UTC parseable with `Instant.parse`.
- `level`: one of `DEBUG`, `INFO`, `WARN`, `ERROR`.
- `service`: lowercase letters/digits/hyphens, underscores, dots; max 64 characters.
- `requestId`: opaque string with allowed characters; max 64 characters.
- `eventCode`: uppercase letters/digits/underscores; max 64 characters.
- No field may contain `"|"` or line breaks; total line length must not exceed 512 Java UTF-16 code units.

This is a **demo format**, not a universal standard for logs. In practice, if you need free-form messages, use JSON or a well-defined escaping protocol.

Create the file **LogParserDemo.java**:

~~~java
import java.time.Instant;
import java.time.format.DateTimeParseException;
import java.util.List;
import java.util.Set;

public class LogParserDemo {
    record Event(Instant occurredAt, String level, String service,
                 String requestId, String eventCode) {}

    static final class ParseProblem extends RuntimeException {
        final String code;

        ParseProblem(String code) {
            this.code = code;
        }
    }

    static Event parse(String line) {
        if (line == null || line.length() > 512
                || line.indexOf('\r') >= 0
                || line.indexOf('\n') >= 0) {
            throw new ParseProblem("INVALID_RECORD_SIZE_OR_LINEBREAK");
        }

        // String.split uses regex; -1 preserves empty trailing fields.
        String[] parts = line.split("\\|", -1);
        if (parts.length != 5) {
            throw new ParseProblem("INVALID_FIELD_COUNT");
        }

        Instant occurredAt;
        try {
            occurredAt = Instant.parse(parts[0]);
        } catch (DateTimeParseException ex) {
            throw new ParseProblem("INVALID_TIMESTAMP");
        }

        if (!Set.of("DEBUG", "INFO", "WARN", "ERROR")
                .contains(parts[1])) {
            throw new ParseProblem("INVALID_LEVEL");
        }

        if (!parts[2].matches("[a-z0-9][a-z0-9._-]{0,63}")
                || !parts[3].matches("[A-Za-z0-9][A-Za-z0-9_-]{0,63}")
                || !parts[4].matches("[A-Z][A-Z0-9_]{0,63}")) {
            throw new ParseProblem("INVALID_IDENTIFIER");
        }

        return new Event(occurredAt, parts[1],
                parts[2], parts[3], parts[4]);
    }

    public static void main(String[] args) {
        List<String> lines = List.of(
            "2026-11-10T03:30:05Z|INFO|order-service|req-42|ORDER_CREATED",
            "2026-11-10T03:30:06Z|ERROR|payment-service|req-42|PAYMENT_TIMEOUT",
            "2026-11-10Tbad|INFO|order-service|req-42|ORDER_CREATED",
            "2026-11-10T03:30:07Z|INFO|order-service|req-42",
            "2026-11-10T03:30:08Z|TRACE|order-service|req-42|ORDER_READ"
        );

        int accepted = 0;
        int rejected = 0;

        for (String line : lines) {
            try {
                Event e = parse(line);
                accepted++;
                System.out.println("parsed level=" + e.level()
                    + " service=" + e.service()
                    + " requestId=" + e.requestId()
                    + " event=" + e.eventCode());
            } catch (ParseProblem ex) {
                rejected++;
                System.out.println("rejected code=" + ex.code);
            }
        }

        System.out.println("accepted=" + accepted
                + " rejected=" + rejected);
    }
}
~~~

Compile and run with JDK 17+:

~~~bash
javac LogParserDemo.java
java LogParserDemo
~~~

**Exact stdout:**

~~~text
parsed level=INFO service=order-service requestId=req-42 event=ORDER_CREATED
parsed level=ERROR service=payment-service requestId=req-42 event=PAYMENT_TIMEOUT
rejected code=INVALID_TIMESTAMP
rejected code=INVALID_FIELD_COUNT
rejected code=INVALID_LEVEL
accepted=2 rejected=3
~~~

Analysis:

1. The first two lines are valid and converted into `Event` instances containing an `Instant` and validated fields.
2. The third line has an invalid timestamp, resulting in `INVALID_TIMESTAMP`.
3. The fourth line has only 4 fields, resulting in `INVALID_FIELD_COUNT`.
4. The fifth line uses `TRACE`, which is not in **this demo's** whitelist, resulting in `INVALID_LEVEL`. `TRACE` is still a valid level in Logback/Log4j 2; a production parser must follow the backend's contract.
5. The `accepted`/`rejected` counters track the validity ratio; do not log the raw input of failed lines because they may contain sensitive data.

**Limitations:** This is a single-line, single-record parser; it does not support multiline stack traces, messages containing delimiters, stream reading, schema registries, retries, or dead-letter queues. `String.length()` checks UTF-16 code units in the JVM; production systems must also limit **UTF-8 bytes** and actual object size. Never use `split` to parse JSON.

## 7. Legacy Parsers: Dissect, Grok, and Regex

Suppose the display pattern is:

~~~text
2026-11-10T03:30:05Z INFO [worker-2] com.example.OrderService - Order created
~~~

An anchored regex with named groups is:

~~~regex
^(?<timestamp>\S+) (?<level>TRACE|DEBUG|INFO|WARN|ERROR) \[(?<thread>[^\]]{1,80})\] (?<logger>[A-Za-z0-9_.$-]{1,160}) - (?<message>.*)$
~~~

This is an **illustrative pattern** and only works when the timestamp has no spaces, delimiters are fixed, the thread is in square brackets, and the message is on a single line. With Java `Pattern.compile(...)`, backslashes in the regex must be escaped again if written as a Java string literal.

Elastic's **Dissect** works well when delimiter positions are very stable; **Grok** is pattern-based and more useful when formats vary. You do not need regex if a contract-backed split or decoder is sufficient. However, splitting on spaces is usually unsafe when messages or timestamps contain spaces.

When designing a regex:

- Anchor the start and end when parsing a full record.
- Bound input length and group lengths.
- Do not use a greedy catch-all group and hope it stops at the right final delimiter.
- Validate required fields, timestamps, levels, and schema after matching.
- Test inputs with quotes, hyphens, Unicode, control characters, and delimiters inside the message.
- Avoid regexes with nested quantifiers that can cause catastrophic backtracking (ReDoS).

A successful regex match **does not guarantee the fields are correct**. You need golden tests with known expected values.

## 8. Multiline Java Stack Traces and Multiline Framing

A Java exception typically spans multiple lines:

~~~text
2026-11-10T03:30:06Z ERROR [worker-2] com.example.DB - Query failed
java.sql.SQLException: Connection refused
    at com.example.DB.execute(DB.java:42)
    at com.example.OrderService.save(OrderService.java:88)
Caused by: java.net.ConnectException: Connection refused
    at java.base/sun.nio.ch.Net.connect0(Native Method)
    ... 3 more
~~~

This is usually **one** logging event with a `Throwable`, even though the text has multiple lines. If a file shipper reads each line as a separate event, the system will produce records containing only `"at..."` or `"Caused by..."` with no timestamp, level, or requestId.

Two ways to handle this:

- **Preferred when you control the source:** encode one event as one JSON object on a single line, escaping newlines in the exception field.
- **For legacy text:** configure multiline handling in the shipper close to the source, based on a rule that detects the **start of a new event**, and only then parse the header fields.

Example for Filebeat with **filestream** (only suitable if every new event starts with a `yyyy-MM-ddTHH:mm:ss` timestamp):

~~~yaml
filebeat.inputs:
  - type: filestream
    id: java-application
    paths:
      - /var/log/my-service/*.log
    parsers:
      - multiline:
          type: pattern
          pattern: '^[0-9]{4}-[0-9]{2}-[0-9]{2}T'
          negate: true
          match: after
          max_lines: 200
          timeout: 5s
~~~

Explanation: lines that **do not start** with a timestamp matching the pattern are appended to the preceding event. `max_lines` and `timeout` cap the line count and wait time so data is not held in the buffer indefinitely. If your timestamp output has a space instead of `T`, the regex above will not match; you must adjust it to the real pattern.

Cases to test:

- `Caused by`, `Suppressed`, and `... more` lines.
- Events whose message itself contains a line that looks like a new timestamp.
- Stack traces longer than `max_lines`.
- File rotation or process restart in the middle of a stack trace.
- Files containing interleaved output from multiple sources/threads where boundaries are hard to determine.
- Timeout flushing when no subsequent line arrives.
- Both collector and shipper having multiline enabled, causing incorrect merging.

Elastic recommends handling multiline in Filebeat before sending to Logstash when appropriate to avoid mixing streams from multiple sources. No single multiline regex is guaranteed to work for every Java logging pattern.

## 9. Parsing JSON: Valid Syntax Is Not Enough for Correct Semantics

A Java appender might emit:

~~~json
{"timestamp":"2026-11-10T03:30:05Z","level":"INFO","logger":"com.example.OrderService","service":"order-service","requestId":"req-42","message":"Order accepted","durationMs":17}
~~~

A JSON parser must preserve **keys, types, escaping, nulls, and nested fields**. After decoding, you must validate:

- `timestamp` has the right type, format, offset, and a reasonable range;
- `level`/severity matches what the backend emits;
- `durationMs` is a number (not sometimes a string, sometimes an object);
- `requestId` and `traceId` have the expected type and length;
- JSON Lines truly has one JSON document per line;
- exception fields may contain escaped newlines;
- unknown, missing, or null fields, or a new `schemaVersion`, are handled intentionally;
- entire nested payloads containing personal data are not pushed into broadly accessible indexes.

**The Java standard library does not provide a built-in general-purpose JSON parser for arbitrary JSON input.** In real applications, you can use Jackson or the collector/backend's parser, with appropriate dependencies/versions and an explicit schema.

Illustrative fragment with Jackson (requires `jackson-databind` and an application-defined DTO):

~~~java
ObjectMapper mapper = new ObjectMapper();
LogDto dto = mapper.readValue(jsonLine, LogDto.class);
validate(dto); // application schema validation
~~~

This is not a standalone program: `LogDto`, `validate(...)`, and `jsonLine` are application components. Do not use `String.split(",")` to parse JSON; commas can appear inside strings and nested arrays/objects. For untrusted sources, limit payload size and JSON depth, and do not enable unrestricted polymorphic deserialization.

## 10. Java Sources: How Logback and Log4j 2 Shape the Parser

**SLF4J is the API**; Logback or Log4j 2 typically performs formatting and output. The parser receives **the output of the encoder/layout**, not the `logger.info(...)` call directly.

### Logback PatternLayout

Example in `logback.xml`:

~~~xml
<configuration>
  <appender name="CONSOLE"
            class="ch.qos.logback.core.ConsoleAppender">
    <encoder>
      <charset>UTF-8</charset>
      <pattern>%d{ISO8601} %-5level [%thread] %logger - %msg%n%ex{full}</pattern>
    </encoder>
  </appender>
  <root level="INFO">
    <appender-ref ref="CONSOLE"/>
  </root>
</configuration>
~~~

A stack trace in text output can span many lines, requiring multiline handling in the shipper. The `%X{requestId}` pattern outputs context from MDC if the application has set `requestId`. Without MDC, the parser cannot reliably invent an ID.

### Log4j 2 PatternLayout

Example fragment:

~~~xml
<PatternLayout pattern="%d{ISO8601} %-5p [%t] %c - %m%n%throwable"/>
~~~

Conversion pattern names look similar, but you should not copy XML or class names between Logback and Log4j 2. If you switch the encoder from text to JSON, **the collector-side parser contract must also be updated and tested**.

### When to Choose a JSON Encoder

If you control the source, using a structured JSON serializer/encoder reduces reliance on regex. Log4j 2 provides JSON layouts/templates depending on version and dependencies; Logback typically needs a compatible JSON encoder if you want an extensible schema. Check the documentation for your exact version and verify exceptions, MDC, Unicode, and nested fields. Do not assume pretty-printed JSON works with a shipper configured for one event per line.

## 11. Normalizing Severity Across Frameworks

Java logging backends do not share the same level names:

~~~text
JUL:     SEVERE / WARNING / INFO / CONFIG / FINE / FINER / FINEST
Logback: ERROR / WARN / INFO / DEBUG / TRACE
Log4j 2:  FATAL / ERROR / WARN / INFO / DEBUG / TRACE
~~~

If an alert rule only looks for `level="ERROR"`, records from JUL with level `SEVERE` may be missed. You must map the original level to a chosen standard severity while keeping the **original `severityText`** for investigation.

Do not convert Java enum ordinals or sequence numbers directly into OpenTelemetry `SeverityNumber`. `SeverityNumber` in OTel has its own rules; for example, WARN and ERROR groups fall into ranges defined by the data model, independent of JUL or Logback internal integers.

Do not assign `ERROR` just because the message contains the word `"error"`. Conversely, an HTTP 500 may be logged across several `INFO` events and one `ERROR` event; do not change the severity of the entire sequence based solely on the final status.

## 12. Parsing requestId/traceId to Correlate Logs and Traces

Context fields for Observability:

~~~text
timestamp=2026-11-10T03:30:05Z
level=ERROR
service=payment-service
requestId=req-42
traceId=4bf92f3577b34da6a3ce929d0e0e4736
eventCode=PAYMENT_TIMEOUT
~~~

After parsing, you can run logical queries:

~~~text
service = "payment-service"
AND requestId = "req-42"
~~~

Exact syntax depends on the backend (Elastic, Loki, Cloud Logging, etc.). A W3C-standard **TraceId** has a different format from a custom ID generated by a gateway. A **SpanId** represents a single span and usually differs at each hop.

If an async worker does not carry MDC or trace context, the parser cannot guess `requestId` from the nearest timestamp without creating false correlations. You must fix **context propagation at the source**. For high-cardinality identifiers, store them as controlled log attributes; do not use `requestId` or `userId` as unbounded metric labels.

## 13. Security: Log Injection, PII, and Untrusted Data

Raw logs may contain:

~~~text
username="alice|admin"
message="OK\nERROR fake event"
path="/api/search?q=email%40example.test"
Authorization="Bearer secret"
~~~

Common issues:

- **Delimiter collision:** separator characters in the input break field order.
- **Log injection:** newlines or control characters forge a new event.
- **PII/secret leakage:** parsing into queryable fields does not make the data safe.
- **Resource exhaustion attacks:** complex regexes, deeply nested JSON, huge messages, very long stack traces.
- **Attribute poisoning:** callers spoofing keys like `service.name`, `tenantId`, or `traceId` in input.

Defenses:

1. Prefer standard serializers and schemas with validation.
2. Enforce size limits in bytes and appropriate element/depth bounds.
3. Do not trust security/tenant/service fields supplied by a client request without authentication/verification.
4. Sanitize control characters when passing text to loggers to prevent forged log lines.
5. Apply data minimization in the application and policy-based masking/redaction in the pipeline.
6. Do not log the entire raw payload when the parser fails; it may contain tokens or emails.
7. Separate access permissions, retention, and encryption for raw/quarantine sinks.
8. Test negative inputs, malformed UTF-8, duplicate keys, and unusual delimiters.

**Redaction at the collector cannot erase copies already written to files or stdout earlier.** Effective protection therefore starts where the event is created.

## 14. Parse Failures Must Have an Explicit Handling Path

A parser should not swallow every invalid input and increment only a success counter. A policy might include:

| Situation | Handling |
| --- | --- |
| Invalid timestamp format | `parse.error_code=INVALID_TIMESTAMP` |
| Missing required field | Reject/quarantine according to policy |
| Unrecognized level | Preserve source value and map to `UNKNOWN`, or reject intentionally |
| Malformed JSON | Increment metric; do not "guess" fields with a fallback regex |
| Index mapping conflict | Report an ingest/schema error; do not treat parse success as storage success |
| Record too large | Enforce limit, handle per policy, and alert |
| Collector unavailable | Retry/backpressure; this is a pipeline failure, not bad content |
| Raw log contains secrets | Block/mask per policy and fix the source |

For mandatory audit or security logs, only drop records if policy permits; you may need **durable quarantine**, retries, and alerts. However, the quarantine store must also have strict access control and retention, rather than "dumping raw failed lines into another, more open log."

A dangerous trap: logging the raw input that failed parsing back into the same stream watched by the parser, creating a loop of **parse error -> log error -> parser receives error again**. Use metrics and minimized error events instead.

## 15. Measuring Parser Quality

Useful metrics:

~~~text
logs_received_total{source,parser_version}
logs_parsed_total{source,parser_version}
logs_rejected_total{source,parser_version,error_code}
logs_quarantined_total{source,parser_version}
logs_indexed_total{source}
parse_duration_seconds{source,parser_version}
pipeline_backlog_events{source}
ingest_lag_seconds{source}
~~~

Labels should only use **bounded-cardinality** values: `source`, `parser_version`, `error_code`. Do not attach `message`, `requestId`, `userId`, or `email` as metric labels.

An illustrative formula:

~~~text
parse_success_ratio =
  delta(logs_parsed_total) / delta(logs_received_total)
~~~

Both counters must share the same source, window, event unit, and consistent retry handling. If a producer or collector restarts, cumulative counters may reset, so use appropriate `rate`/`increase` functions.

**A 100% success rate does not guarantee the parser is correct**, because a regex can match the wrong groups. Combine metrics with golden fixtures, end-to-end queries, anomalous timestamp detection, and sampling of meaningful fields.

Also monitor **multiline split/merge errors**, output bytes/s, queue depth, ingest lag, backend rejects, schema mapping conflicts, CPU/GC, and truncated events. When parser throughput is high but index throughput is low, backlog will still grow.

## 16. Testing Parsing: From Unit to End-to-End

| Test Case | Input | Expectation |
| --- | --- | --- |
| Happy path | Line matching contract | Extracts correct fields and types |
| Missing field | 4 instead of 5 fields | Rejects with the right errorCode |
| Empty field | Consecutive delimiters | Does not silently shift fields |
| Invalid timestamp | Invalid date string | Rejects; does not guess using collector clock |
| Timezone | Equivalent UTC and offset | Normalizes to the same instant |
| Unknown level | `TRACE` when only `INFO`/`WARN`/`ERROR` allowed | Rejects/maps per policy |
| Special characters | Quotes, pipes, slashes, Unicode | Escapes or rejects accurately |
| Java stack trace | `at`/`Caused by`/`Suppressed` | Groups into a single event |
| Nested JSON | Commas/quotes in body | Parses properly without manual splitting |
| Oversized data | Exceeds size limit | Does not cause OOM or CPU storm |
| New schema version | Added/changed fields | Tested migration/backward compatibility |
| Collector restart | Pending queue, in-progress multiline | No data loss beyond accepted semantics |
| Two tenants | Data with same `eventCode` | No cross-routing or wrong tenant assignment |
| End-to-end | Java -> agent -> index -> UI | Queries return exact record, fields, and time |

### Golden Fixtures

Maintain pairs of **input fixtures and expected structured outputs** as synthetic data, versioned alongside the parser. Include both positive and negative tests. Whenever you change Logback `PatternLayout`, Log4j 2 layout, Java version, or shipper rules, rerun the fixtures before deploying.

Do not build a parser that does "try A, if it fails try B, if that fails take everything after the last delimiter" and treat all cases as success. Incompatible formats can accidentally match in ways that are very hard to detect. Use `schemaVersion`, source type, or explicit routing.

### End-to-End Testing

1. Emit a batch of events with synthetic `testRunId` and `requestId`.
2. Inspect the actual raw output of the encoder.
3. Verify framing/multiline at the shipper.
4. Inspect the structured record at the collector before indexing.
5. Check mapping, indexed event count, and any errors.
6. Query by `requestId`/`eventCode`/`testRunId` and compare each field against the source.
7. Test file rotation, async queues, collector timeouts, and retries.
8. Compare the source timestamp with `observedTimestamp` and evaluate ingest lag.

Do not conclude everything succeeded just because an ingest job returned HTTP 200: the backend may still be processing or experiencing index lag. Know the exact acknowledgment point of each system.

## 17. Throughput, Batching, and Parser Limits

At high log volumes, the parser can become a bottleneck:

- Backtracking regexes consume CPU, especially on long inputs.
- Nested JSON and large exception fields increase allocation and GC pressure.
- Multiline buffers increase memory usage and flush latency.
- Lookups for field enrichment can depend on network or caches.
- Regex-based redaction on large raw messages can be very expensive.
- Indexes with too many dynamic fields or nested properties increase cost.
- Rejects/quarantine/retries create backlogs during prolonged incidents.

Measure **records/s and bytes/s** at each stage: logs received, parsed, sent, and indexed; p95 parse latency, queue occupancy, and error rate. Do not consider a parser "faster" because it splits one stack trace into hundreds of lines: throughput increases on paper while **every real event is parsed incorrectly**.

Test with representative payloads: short `INFO` lines, `ERROR` with long stack traces, context-heavy JSON, Unicode, multiple services, and rising load. If the producer rate exceeds parse/index capacity over a sustained period, increasing queue size only delays when it fills up; find the real bottleneck.

## 18. Common Misconceptions

**"A regex match means the log is valid."** Regexes can assign fields incorrectly; you must validate the schema and compare against expected output.

**"JSON is enough; no validation needed."** Valid JSON can still have wrong types, missing fields, PII, or be multi-line pretty JSON.

**"One line equals one log event."** Stack traces span multiple lines and require proper framing.

**"Splitting on spaces parses every PatternLayout."** Timestamps, logger padding, and free-text messages can contain spaces.

**"All timestamps are UTC."** Many applications emit local time without an offset; wrong conversion shifts incident timelines.

**"JUL and Log4j have the same levels."** JUL uses `SEVERE`/`WARNING`/`FINE`; severity mapping is required.

**"If requestId is missing, grab it from the nearest event."** This creates false correlations under concurrent requests; fix MDC/context propagation at the source.

**"When parsing fails, log the raw message for debugging."** This can leak secrets and cause a pipeline error loop. Use protected quarantine and metrics instead.

**"Sent to the collector means successfully indexed."** Schema conflicts, quotas, backlogs, retries, or lag can still occur.

**"Increasing max_lines and queue size indefinitely improves grouping."** It can increase memory and latency without fixing broken framing.

**"More indexed fields are always better."** Dynamic fields and high cardinality increase cost and can create personal data risks.

## 19. Log Parsing Implementation Checklist

- [ ] Know the actual format at the source (JSON Lines or specific PatternLayout).
- [ ] Have a schema for timestamp/timezone, level, service, eventCode, and correlation IDs.
- [ ] Framing/multiline matches Java stack traces and actual text/JSON output.
- [ ] Use a JSON parser for JSON; appropriate regex/Dissect/Grok for legacy text.
- [ ] Inputs have clear size/depth/field limits and escaping rules.
- [ ] Time normalization distinguishes event timestamp from observed timestamp.
- [ ] Severity mapping across JUL/Logback/Log4j 2 follows an explicit convention.
- [ ] Do not fabricate requestId/traceId when no reliable source exists.
- [ ] Have schema validation, `schemaVersion`, and change ownership.
- [ ] Do not ingest unnecessary PII/secrets or raw errors into broadly accessible destinations.
- [ ] Have parse success/reject/quarantine metrics and backlog monitoring.
- [ ] Have golden/negative tests and test log injection, Unicode, and multiline.
- [ ] Verified end-to-end: raw event -> parsed fields -> index -> query.
- [ ] Evaluated CPU, GC, throughput, ingest lag, and lost/duplicate data.
- [ ] Have a parser rollback procedure when changing encoders or backends.

**Conclusion:** Log parsing turns Java application logs into **reliably queryable and correlatable** Observability data. Quality depends on data contracts, event framing, timestamps, severity, schemas, information security, and end-to-end verification. **Prefer structured logging at the source; for legacy text, parse with validation and proper multiline handling** rather than relying solely on regex matches.

## 20. References

- [OpenTelemetry Logs Data Model](https://opentelemetry.io/docs/specs/otel/logs/data-model/): timestamp, observed timestamp, severity, body, resource, attributes, and trace context.
- [OpenTelemetry Logs Concepts](https://opentelemetry.io/docs/concepts/signals/logs/): sources, loggers, log records, and exporters.
- [Elastic Filebeat — Manage multiline messages](https://www.elastic.co/docs/reference/beats/filebeat/multiline-examples): grouping Java stack traces by input stream.
- [Elastic — Grok processor](https://www.elastic.co/docs/reference/enrich-processor/grok-processor): parsing named fields with patterns.
- [Elastic — Dissect processor](https://www.elastic.co/docs/reference/enrich-processor/dissect-processor): parsing data by fixed delimiters.
- [Logback Manual — Layouts](https://logback.qos.ch/manual/layouts.html): configuring PatternLayout.
- [Apache Log4j 2 — Pattern Layout](https://logging.apache.org/log4j/2.x/manual/pattern-layout.html): patterns and exception conversion.
- [Apache Log4j 2 — JSON Template Layout](https://logging.apache.org/log4j/2.x/manual/json-template-layout.html): template-based structured JSON output.
- [Oracle Java SE 17 — java.time.Instant](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Instant.html): handling UTC timestamps.
- [Oracle Java SE 17 — java.util.regex.Pattern](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/regex/Pattern.html): regex in Java, named groups, and escaping.
