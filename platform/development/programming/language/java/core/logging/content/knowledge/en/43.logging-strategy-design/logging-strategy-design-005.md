# Choosing a Format for Java Logging: Text, Key-Value, JSON Lines, and Structured Telemetry

## 1. What Does “Choosing a Format” Mean in a Logging Strategy?

When designing a logging strategy for a Java application, the **format** is how a **log event** is represented so that humans or other systems can read, store, and analyze it. A format can be a human-readable line of text, key-value pairs, one JSON object per line, a syslog message, or a telemetry structure transmitted over a protocol such as OTLP.

For example, the same business operation of successfully creating an order:

```text
2026-11-10T02:00:00Z INFO orders - Created order ord-42 in 27 ms
```

```text
ts=2026-11-10T02:00:00Z level=INFO event=order.create.result orderId=ord-42 outcome=SUCCEEDED durationMs=27
```

```json
{"timestamp":"2026-11-10T02:00:00Z","level":"INFO","event":"order.create.result","orderId":"ord-42","outcome":"SUCCEEDED","durationMs":27}
```

These three ways of writing **can describe the same event**, but they differ in readability, parseability, schema management, data types, size, and logging pipeline compatibility.

**There is no single “best format” for every system.** A one-off CLI application may prefer simple text. A multi-service Java system shipping logs to a centralized query store usually benefits from **structured JSON Lines** or a standardized structured log record model. If you already use OpenTelemetry, you may choose to export records via OTLP; however, you must distinguish between **record data model, wire protocol, and file output**.

Choosing the right format must be based on **observability goals, searchable fields, consistency, log-receiving tools, security risks, throughput, and operational cost**.

## 2. Distinguishing Event, Message, Field, Formatter, Encoder, and Transport

These concepts are easily mixed up:

| Concept | Meaning |
| --- | --- |
| **Log event / LogRecord** | An occurrence: timestamp, severity, message, Throwable, context, attributes |
| **Message/template** | Descriptive text such as `Order creation finished` or `orderId={}` |
| **Structured fields** | Named, typed fields: `event`, `orderId`, `durationMs`, `outcome` |
| **Formatter / layout / encoder** | Converts a record into formatted text, JSON, or bytes |
| **Appender / handler** | Sends data to a console, file, socket, queue, or sink |
| **Framing** | How boundaries between two events are identified: newline, length prefix, protocol message |
| **Transport** | How data is transmitted: stdout, file tail, HTTP, gRPC, TCP, UDP, etc. |
| **Schema** | Conventions for field names, data types, semantics, versioning, and required fields |
| **Collector** | Receives, parses, enriches, filters, buffers, and forwards logs to storage |

A structured event **does not automatically become structured JSON** when using `log.info("orderId={}", id)`. If the backend only puts everything into a single `message` field, the target system still sees text, not necessarily a standalone `orderId` JSON field.

Conversely, a JSON object might contain **only a single text message field**. It is valid JSON, yet it still lacks the structure needed for analysis if it omits the action, target, outcome, or correlation ID.

**Format and delivery reliability are two separate concerns:** JSON Lines does not make an event more durably written than text. Async queues, rotation, flushing, retries, collectors, and remote acknowledgments govern those other parts of the pipeline.

## 3. Comparison Matrix of Format Options

| Format | Direct Human Readability | Machine Parsing / Querying | Drawbacks and Considerations | When to Use |
| --- | --- | --- | --- | --- |
| **Plain text / pattern** | High | Medium to low if standard fields are missing | Relies on regex, multiline exceptions, hard to query individual fields | CLI, debugging, small services, or local console |
| **Key=value** | Fairly high | Good if escaping and schema are consistent | Spaces, quotes, newlines, and `=` cause ambiguity with ad-hoc parsers | Systems needing compact, grep-friendly logs ingested by a unified parser |
| **JSON Lines / JSONL** | Medium | High with a JSON parser and stable fields | Field-name overhead, serializer/escaping cost, nested schemas, size | Microservices, centralized logging, dashboards |
| **Syslog (e.g., RFC 5424)** | Depends on renderer | Good when the receiver supports the standard | PRI/severity, metadata, encoding, and framing/transport must be exact | Integrating with existing syslog/SIEM systems |
| **CEF/LEEF or specialized SIEM formats** | Structured per vendor/tool | High in compatible target systems | Field mapping, escaping, and semantics depend on the target system | When a SIEM requires this format |
| **OTLP log records** | Not necessarily a text file | Has typed attributes, timestamps, severity/trace | Requires SDK/collector, protocol, and appropriate semantic conventions | Systems standardized on OpenTelemetry |

**OTLP is not simply “JSONL with a different name.”** OpenTelemetry defines a log record model and a wire protocol; payloads can be encoded as protobuf over gRPC/HTTP or other spec-supported encodings. Exporting OTLP and printing JSONL to a file are **two different implementation steps**. Field names in a custom JSON log also do not automatically map cleanly to OpenTelemetry semantic conventions.

With text, “parseable by regex” **does not mean a stable schema**: if the message wording changes, spacing varies, an optional field is missing, or an unescaped newline appears, the parser can break.

## 4. Questions to Answer Before Choosing

Before deciding, answer these questions:

1. **Who reads the logs?** Engineers watching a console, support reading log files, SREs querying a log search UI, or a SIEM/collector parsing them automatically?
2. **What is the volume?** A few hundred events/day or hundreds of thousands of events/second? What are the average event size and tail latency?
3. **What queries are needed?** Filtering by `event`, `status`, `errorCode`, `requestId`, `traceId`, `durationMs`, or just grepping messages?
4. **Are there multiple services?** If so, you need a shared schema and consistent severity/time/trace ID mappings.
5. **What receives the logs?** Console, sidecar, Fluent Bit/Vector/OTel Collector, syslog receiver, log gateway?
6. **Are exceptions complex?** Are there `Caused by` chains, suppressed exceptions, or multiline stack traces that must be preserved intact?
7. **Is the data sensitive?** Are there request/user/message payloads, credentials, IPs, device info, PII, or audit data requiring special controls?
8. **How often does the schema change?** Are multiple versions deployed in parallel requiring forward/backward compatibility?
9. **What is the resource budget?** CPU for encoding, GC allocation, file/network bytes, collector parsing, and storage/indexing?
10. **What delivery guarantees are required?** Best-effort debug logs or audit logs that must be retained and reconciled? Format alone cannot solve durability.

A rule of thumb:

- If logs are primarily **read by humans on a terminal** with few fields, start with a clear text pattern.
- If logs are **queried/aggregated by machines** across multiple services, prefer **structured records + JSONL** or a telemetry structure supported by your collector.
- If the organization already has a **SIEM/syslog contract**, the output format must strictly follow the receiver's protocol and escaping rules.
- If using **OpenTelemetry end-to-end**, evaluate whether exporting OTLP meets logging context, cost, and semantics requirements better than converting text in a collector.
- If you need to serve **two audiences**, you can use different formatters for developer consoles and production pipelines, but you must prevent emitting **duplicate copies of the same event**.

## 5. Text Patterns: Simple, but Consistency Is Essential

A common log pattern:

```text
2026-11-10T02:00:00.000Z INFO  orders-api [traceId=abc123] com.example.OrderService - event=order.create.result orderId=ord-42 outcome=SUCCEEDED
```

Text benefits direct human readers, especially when the system already provides a formatter for level, timestamp, logger, and thread. It works well when the goal is line-by-line diagnosis.

### 5.1. Rules to Keep Text from Becoming an Anti-Pattern

- Include an **explicit-timezone timestamp**, level, component/logger, and event code when needed.
- Use human-language messages only for explanation; important fields should be clearly identifiable.
- If embedding key-value pairs in text, standardize how quotes, spaces, and control characters are escaped.
- Do not use `System.out.println("Done")` as standard logging across services.
- Do not arbitrarily change field positions or the pattern if a collector parses it with regex.
- Do not log arbitrary multiline payloads when the pipeline assumes **one line = one event**.
- Attach `requestId`/`traceId` when available and properly scoped; do not rely on line ordering to infer a request.
- Use **stable event codes and errorCodes**; never use full message sentences as metric labels.

### 5.2. When Is Text Better Than JSON?

In short-lived command-line tools, developer consoles, temporary test logs, or systems without field-level querying, text can be easier to work with. There is no need to force every small Java script into JSON just because “structured” sounds more professional.

However, if you frequently need to ask “How many times did `PAYMENT_TIMEOUT` occur by service and major version?” or correlate by trace ID, text without dedicated fields creates extra work in the collector/parser.

### 5.3. Text with Stack Traces

Exceptions logged via SLF4J or JUL can span multiple lines:

```text
ERROR order.persist.failed requestId=req-101
java.lang.IllegalStateException: cannot save
    at com.example.OrderService.save(...)
Caused by: java.io.IOException: storage unavailable
```

This snippet is illustrative only. If a collector tails line by line, it can split a single `Throwable` into multiple records. You need a multiline parser with bounds/timeouts, or choose a **JSONL encoder that writes the escaped stack trace as a single field inside one record**.

## 6. Key-Value: Easy to Grep, but Not Always Typed Fields

Example:

```text
time=2026-11-10T02:00:00Z level=INFO event=order.create.result requestId=req-101 orderId=ord-42 durationMs=27 outcome=SUCCEEDED
```

Its strengths are brevity, easy grepping, and parseability when conventions are strict. What requires care is the **grammar**:

- Must values containing spaces be quoted?
- How are quotes, backslashes, `=`, CR/LF, and tabs escaped?
- When a field is missing, do you write `null`, `-`, omit the field, or use an empty string?
- Does the parser interpret `27` as an integer or a string?
- Are key names case-sensitive?
- If a value contains Unicode characters or delimiters, does the parser still read it correctly?
- Is field order fixed, or can keys appear in any order?

Never assume that every `key=value` string automatically becomes structured attributes in a centralized log system. Some systems use `logfmt` with specific quoting/escaping rules, while others use regex or custom parsers; you must choose and test **one consistent dialect**.

**Do not write a parser using `line.split(" ")`** and trust it to handle all values. A string like `errorMessage="disk write failed"` will be split incorrectly if the parser does not understand quoting.

## 7. JSON Lines: The Common Choice for Centralized Logs

**JSONL** is a sequence of **independent JSON objects, one event per line**:

```json
{"timestamp":"2026-11-10T02:00:00Z","level":"INFO","event":"order.create.result","orderId":"ord-42","outcome":"SUCCEEDED","durationMs":27}
```

The next event sits on the next line. Nested data or arrays are still valid when genuinely needed, though overly large object graphs should be avoided.

Advantages:

1. **Explicit data types:** number, boolean, string, array, object, null; `durationMs` can be a number.
2. **Named fields:** parsers do not have to guess positions from a prose message.
3. **Strong correlation:** `requestId`, `traceId`, `messageId`, and `jobRunId` become dedicated fields.
4. **Easier search and aggregation:** filter on `event`, `errorCode`, `status`, etc.
5. **Standard escaping:** newlines/quotes inside strings are encoded rather than breaking one event across multiple lines.
6. **Versionable schema:** field names and types can be contract-tested.
7. **Broad collector support:** most collectors include JSON parsers, though the right config must still be enabled.

Drawbacks:

- Added overhead from quotes, delimiters, and repeated field names.
- Console readers see long single-line JSON strings; a pretty-viewer is needed for debugging.
- Deeply nested fields or very long arrays complicate querying/indexing and privacy policies.
- An encoder/serializer may consume more CPU/allocations than a simple text pattern, depending on the library and load.
- JSONL **must** be valid JSON; never concatenate raw messages into JSON strings manually in production.
- A large log event can exceed line limits in agents, file-tail parsers, log gateways, or search backends.
- JSONL does not by itself provide retries/ACKs, disk durability, or guaranteed collector delivery.

**JSONL does not mean the file must be named `.jsonl`.** The filename is just a convention; what matters is that **each line is a JSON value conforming to the defined schema, typically an object**, and the pipeline does not inject raw newlines inside strings.

### 7.1. JSON Must Be One Event per Line

Suppose a message contains a newline:

```text
first line
second line
```

A valid JSON serializer writes a single string with the `\n` escape sequence, for example:

```json
{"event":"debug.message","message":"first line\nsecond line"}
```

In the file, `\n` is **two literal characters**—a backslash and the letter `n`—not an actual line break inside the JSON string. Each line in the file still contains exactly one JSON object.

If the application naively concatenates it into:

```text
{"message":"first line
second line"}
```

then it is **not a valid single-line JSON object**; a JSONL parser may treat it as two broken lines.

## 8. Runnable Java 17 Example: One LogRecord, Two Formats

This Java 17 example uses **JUL `LogRecord` and `Formatter`** built into the JDK. The same event—containing timestamp, level, event code, request ID, order ID, outcome, duration, and detail—is rendered as:

- A **key=value text** line for human readers.
- A **JSONL** line for JSON parsers.

To make stdout completely reproducible, the program sets a fixed `Instant`, invokes both formatters directly, and prints the results. It **does not write to files or send over the network**; in a real application, a formatter/encoder must be attached to a `Handler`/appender with proper backend lifecycle configuration.

The `detail` value contains **quotes and a newline** to demonstrate that both representations can escape them onto **a single line**.

Save the file as **`LogFormatDemo.java`**:

```java
import java.time.Instant;
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;

public class LogFormatDemo {
    record Fields(
            String requestId,
            String orderId,
            String outcome,
            long durationMs,
            String detail) {}

    // Illustrates only partial JSON string escaping in plain JDK.
    // Production should use a proven JSON encoder/serializer.
    private static String quote(String value) {
        if (value == null) {
            return "null";
        }

        StringBuilder out = new StringBuilder();
        out.append((char) 34);

        for (int i = 0; i < value.length(); i++) {
            char c = value.charAt(i);

            if (c == 34 || c == 92) {
                out.append((char) 92).append(c);
            } else if (c == 10) {
                out.append((char) 92).append('n');
            } else if (c == 13) {
                out.append((char) 92).append('r');
            } else if (c == 9) {
                out.append((char) 92).append('t');
            } else if (c < 32) {
                String hex = Integer.toHexString(c);
                out.append((char) 92).append('u');
                out.append("0".repeat(4 - hex.length()));
                out.append(hex);
            } else {
                out.append(c);
            }
        }

        return out.append((char) 34).toString();
    }

    private static Fields fields(LogRecord record) {
        return (Fields) record.getParameters()[0];
    }

    static final class TextFormatter extends Formatter {
        @Override
        public String format(LogRecord record) {
            Fields f = fields(record);
            return record.getInstant() + " "
                    + record.getLevel().getName()
                    + " event=" + record.getMessage()
                    + " requestId=" + f.requestId()
                    + " orderId=" + f.orderId()
                    + " outcome=" + f.outcome()
                    + " durationMs=" + f.durationMs()
                    + " detail=" + quote(f.detail())
                    + System.lineSeparator();
        }
    }

    private static void stringField(
            StringBuilder out, String key, String value) {
        out.append(quote(key)).append(':').append(quote(value));
    }

    static final class JsonFormatter extends Formatter {
        @Override
        public String format(LogRecord record) {
            Fields f = fields(record);
            StringBuilder out = new StringBuilder("{");

            stringField(out, "timestamp",
                    record.getInstant().toString());
            out.append(',');
            stringField(out, "level", record.getLevel().getName());
            out.append(',');
            stringField(out, "event", record.getMessage());
            out.append(',');
            stringField(out, "requestId", f.requestId());
            out.append(',');
            stringField(out, "orderId", f.orderId());
            out.append(',');
            stringField(out, "outcome", f.outcome());
            out.append(',');
            out.append(quote("durationMs"))
                    .append(':').append(f.durationMs());
            out.append(',');
            stringField(out, "detail", f.detail());
            out.append('}').append(System.lineSeparator());
            return out.toString();
        }
    }

    public static void main(String[] args) {
        LogRecord record = new LogRecord(
                Level.INFO, "order.create.result");
        record.setInstant(Instant.parse("2026-11-10T02:00:00Z"));
        String detail = "accepted " + (char) 34 + "item"
                + (char) 34 + (char) 10 + "verified";
        record.setParameters(new Object[]{
                new Fields(
                        "req-101", "ord-42", "SUCCEEDED", 27, detail)
        });

        System.out.println("TEXT");
        System.out.print(new TextFormatter().format(record));
        System.out.println("JSONL");
        System.out.print(new JsonFormatter().format(record));
    }
}
```

Compile and run on **JDK 17+**:

```bash
javac LogFormatDemo.java
java LogFormatDemo
```

**Exact stdout** on a system with standard line endings:

```text
TEXT
2026-11-10T02:00:00Z INFO event=order.create.result requestId=req-101 orderId=ord-42 outcome=SUCCEEDED durationMs=27 detail="accepted \"item\"\nverified"
JSONL
{"timestamp":"2026-11-10T02:00:00Z","level":"INFO","event":"order.create.result","requestId":"req-101","orderId":"ord-42","outcome":"SUCCEEDED","durationMs":27,"detail":"accepted \"item\"\nverified"}
```

### 8.1. Why Does the Output Look Like This?

- `LogRecord` holds the severity and message code; `setInstant` fixes the timestamp so it does not depend on the machine clock.
- `Fields` is a Java 17 record used to pass event data into the demo formatters; **it is not a general JUL API**.
- `TextFormatter` writes a single line of key/value pairs. The `detail` field is quoted so an input newline does not turn into a new log line.
- `JsonFormatter` writes a JSON object. `durationMs` is a **number**, while the remaining fields are strings.
- `quote` handles quotes, backslashes, CR/LF/tabs, and C0 control characters. For example, the input contains a real newline, yet stdout represents it as `\n`.
- `TextFormatter` and `JsonFormatter` are real `java.util.logging.Formatter` subclasses that can be used with a JUL `Handler`; the example calls them directly to verify rendering independently of console handlers, file I/O, and default timestamps.
- `System.lineSeparator()` uses the OS-appropriate line ending; when viewing stdout as lines, the logical content is identical.
- The example contains only **one event**, so it does not demonstrate log rotation, batching, async delivery, or collectors.

### 8.2. Security Limitations of the Example

The `quote` method was written for instructional purposes and **is not a production JSON serializer**. It does not fully handle invalid Unicode data (such as unpaired UTF-16 surrogates), enforce payload size limits, mask PII/secrets, define a schema, or validate semantic correctness of fields. In production, use a tested, framework-maintained encoder/serializer.

The `key=value` text portion is also **not claimed to conform to any specific standard logfmt dialect**. It merely illustrates writing a readable string. The values for `event`, `requestId`, and `orderId` in the example are trusted constants; with real input, you must validate/escape all text fields, not just `detail`.

When running in a data-intensive system, do not manually construct records and invoke formatters in every business method. Use a standard logger/provider so levels/filters, MDC/context, batching, and error handling are managed centrally.

## 9. Wiring Formatters into JUL, SLF4J/Logback, and Log4j 2

### 9.1. JUL: Formatter and Handler

In JUL, `LogRecord` holds log metadata; `Formatter` converts the record into text; `Handler` decides where to send it. When actually using a format in an application, a handler must be configured with the appropriate formatter. **Simply calling `record.setParameters(...)` does not automatically make `ConsoleHandler` produce JSON.**

Integration snippet:

```java
// In the same class containing JsonFormatter and an appropriate logger.
java.util.logging.ConsoleHandler handler =
        new java.util.logging.ConsoleHandler();
handler.setFormatter(new JsonFormatter());
handler.setLevel(java.util.logging.Level.INFO);

java.util.logging.Logger logger =
        java.util.logging.Logger.getLogger("demo.orders");
logger.setUseParentHandlers(false);
logger.addHandler(handler);

// When application lifecycle ends, clean up the handler at the appropriate lifecycle hook.
```

This snippet **illustrates wiring only**; it is not a standalone file. If you use the demo's `JsonFormatter`, it expects `LogRecord.getParameters()[0]` to be `Fields`; normal log records **without** this parameter will fail. In production, a formatter must handle any `LogRecord`, missing fields, message parameters, resource bundles, `Throwable`s, special characters, and error policies. Do not attach the demo formatter to the root logger of a running system.

One common surprise: JUL's `ConsoleHandler` writes to **stderr** by default, not stdout. That is why, to get deterministic stdout in the demo, we called the formatter directly instead of relying on the console handler.

### 9.2. SLF4J Is Not a Target Format

**SLF4J is an API facade**, not a JSON encoder. A call like:

```java
// Integration code; variables have already been validated.
log.info("event=order.create.result orderId={} outcome={}",
        safeOrderId, outcomeCode);
```

may produce text or JSON depending on the provider, backend, and layout. The `{}` placeholder is a message-formatting mechanism; **it does not automatically create standalone JSON properties**.

With **SLF4J 2.x**, you can attach key-value pairs:

```java
// Integration snippet for org.slf4j.Logger version 2.x.
log.atInfo()
        .addKeyValue("event", "order.create.result")
        .addKeyValue("orderId", safeOrderId)
        .addKeyValue("outcome", outcomeCode)
        .addKeyValue("durationMs", durationMs)
        .log("Order creation finished");
```

However, the provider/encoder must still **emit key-value fields** in the desired format. Some patterns only render the message and drop attributes. Always verify the actual record at the sink, not merely the presence of `addKeyValue` calls.

### 9.3. Logback Classic

With Logback, a text pattern can use `PatternLayoutEncoder`:

```xml
<encoder>
    <pattern>%d{yyyy-MM-dd'T'HH:mm:ss.SSS,UTC} %-5level %logger - %msg%n%ex</pattern>
    <charset>UTF-8</charset>
</encoder>
```

This is a **configuration snippet** inside a compatible Logback appender. It includes metadata and exception rendering; it is not JSONL.

For JSONL, you can use an appropriate JSON encoder, such as **logstash-logback-encoder** in a project with compatible dependencies:

```xml
<encoder class="net.logstash.logback.encoder.LogstashEncoder"/>
```

**`LogstashEncoder` is not included in the JDK or Logback Core**: you must add a compatible artifact/version and test formatting, timezone, MDC, `Throwable`, structured arguments, and redaction rules in that specific project.

An application may want a **text pattern in local development** and a **JSON encoder in production**, but do not let the schema change its semantics between environments. If you attach both a console appender and a file/remote appender simultaneously, check whether events are shipped twice over independent paths.

### 9.4. Log4j 2

Log4j 2 provides `PatternLayout` as well as structured JSON outputs such as **JsonTemplateLayout** with the corresponding dependency/configuration. Layout choices and resolver/field-name details depend on the version. Do not use Logback XML classes in Log4j 2 or vice versa.

Regardless of backend, verify:

- Does the encoder format each log event as **one JSON object per line** or multiline text?
- Are MDC/ThreadContext, `Throwable`, and thread/logger metadata emitted?
- Do field names match the desired schema without duplicates or conflicts?
- Are JSON numbers and booleans preserved with the right types?
- Are characters escaped and sensitive fields masked?
- Does the encoder still work with `null` values, deep exceptions, markers, and very long messages?
- Do appenders and collectors agree on timestamp, timezone, and line framing?

## 10. Format and Schema: Which Fields Should Be Standardized?

A recommended structured event:

```json
{
  "timestamp": "2026-11-10T02:00:00Z",
  "level": "ERROR",
  "service.name": "orders-api",
  "deployment.environment": "production",
  "event": "order.persist.failed",
  "operation": "SAVE_ORDER",
  "requestId": "req-101",
  "traceId": "e64c82e718934f48a84e7a5fcf72b9d1",
  "orderId": "ord-42",
  "outcome": "FAILED",
  "errorCode": "DB_CONNECTION_TIMEOUT",
  "durationMs": 103
}
```

This is **an illustrative schema**, not mandatory field names from OpenTelemetry, ECS, or any specific vendor. An organization should pick **one convention** and maintain a mapping table to target systems.

Field groups:

| Group | Examples to Consider |
| --- | --- |
| **Envelope** | timestamp, severity/level, logger name, service, version, environment |
| **Event** | event code, operation, phase, outcome, errorCode |
| **Correlation** | requestId, correlationId, traceId, spanId, messageId, jobRunId |
| **Target / Entity** | resource type, validated resource ID |
| **HTTP** | method, route template, status, duration |
| **Message consumer** | topic/queue, partition/offset or delivery tag, attempt |
| **Exception** | exception type, cause chain/stack trace per policy |
| **System** | instance/pod/container, region, deployment version |
| **Metrics / Measurements** | durationMs, retryCount, itemsProcessed; explicit numeric types |

Not every field is needed in **every** event. A startup log may only need service/version/time, whereas a payment failure needs payment ID, operation, errorCode, and traceId. The schema should **fit the event type**, avoiding “one giant object” carrying dozens of empty fields on every line.

### 10.1. Use Stable Data Types

In JSONL:

- `durationMs: 27` is a number; `"durationMs": "27ms"` is a string, which is hard to aggregate numerically.
- `retryable: true` is a boolean; `"retryable": "true"` is a string.
- `status: 404` can be an integer; storing `"404"` requires justification and mapping.
- `requestId` should be a string, not coerced to a number that strips leading zeros.
- `timestamp` should have an explicit timezone, typically RFC 3339/ISO-8601 UTC.
- `errorCode` should come from a finite enum/catalog, not raw exception messages.

The same field should not flip between number and string across deployments, as queries and indexes can break. If you change its meaning or format, apply versioning or schema migration.

### 10.2. Null, Missing, and Unknown

Three states with distinct meanings:

- **Missing:** the field was not collected or does not apply.
- **Null:** the field is defined in the schema but has no value.
- **Unknown:** cannot be classified or computed, which can be represented by an `UNKNOWN` enum when appropriate.

Do not put `"N/A"` into a numeric field like `durationMs`. In JSON, it is better to omit the field or use `null` per your contract, and ensure the collector/storage interprets it consistently.

## 11. Timestamp, Timezone, and Precision

Timestamp formatting affects how logs from multiple JVMs are merged:

```text
2026-11-10T02:00:00.123Z
2026-11-10T09:00:00.123+07:00
```

These two strings can represent **the exact same instant**, so raw text comparison should not be used to conclude they differ.

Recommendations:

1. Choose UTC or an explicit offset—usually UTC for storage and querying.
2. Write timestamps in a stably parseable format (e.g., RFC 3339).
3. Clarify how **event time** (when it occurred) differs from **observed/ingestion time** (when the collector received it).
4. If the application uses `System.nanoTime()` to measure duration, never serialize that value as a wall-clock timestamp: it is a monotonic clock for elapsed time only.
5. Do not assume clocks across all nodes are perfectly synchronized; distributed logs and traces may appear out of order.
6. Define units and precision: milliseconds, microseconds, or nanoseconds based on actual need.
7. Never use a pattern without a timezone when merging data from multiple regions.

Note that high printed precision does not guarantee equivalent physical clock accuracy. OS clocks, runtimes, and collectors each have their own limits.

## 12. Severity and Level Names

The Java ecosystem has multiple level systems:

- JUL: `SEVERE`, `WARNING`, `INFO`, `CONFIG`, `FINE`, `FINER`, `FINEST`.
- SLF4J/Logback: `ERROR`, `WARN`, `INFO`, `DEBUG`, `TRACE`.
- Log4j 2: `FATAL`, `ERROR`, `WARN`, `INFO`, `DEBUG`, `TRACE`, plus custom configured levels.

If logs from both JUL and Logback enter the same collector, **severity mapping** may be required. Mapping is not always strictly 1-to-1; agree on how to handle `SEVERE` vs `ERROR`, `WARNING` vs `WARN`, and lower levels with matching semantics.

Do not use level as the sole field for identifying outcome. `WARN retrying` does not mean the business operation has finally failed; an `INFO result` might carry `outcome=DENIED`. Define stable `event`, `outcome`, and `errorCode` fields for querying, and use level for observability priority.

## 13. Throwable and Multiline Exceptions: A Key Reason for Format Choice

An exception can contain:

- Class name and message.
- Stack trace of the wrapper and cause chain (`Caused by`).
- Suppressed exceptions (`Suppressed`).
- Request/operation context and error code.
- Sensitive data inside the exception message if a library accidentally includes it.

With **text**, stack traces are usually multiline. The collector must use a multiline parser to recognize a single event and prevent the stack trace from being split into separate records.

With **JSONL**, the encoder can place the stack trace into **a newline-escaped JSON string** or a dedicated structured exception object. However, field names (`stack_trace`, `exception.stacktrace`, etc.) and how causes/suppressed exceptions are rendered depend on the encoder and schema.

An illustrative event:

```json
{
  "event": "order.persist.failed",
  "errorCode": "STORAGE_UNAVAILABLE",
  "exceptionType": "OrderProcessingException",
  "rootCauseType": "IOException",
  "message": "Cannot create order"
}
```

This is a **minimal record**, not a full stack trace. To preserve evidence, the logger must receive the **actual `Throwable`**, not just `e.getMessage()`; and the encoder must be configured to emit exceptions. You can cap stack depth/length for cost and privacy, but be aware that truncating the cause chain makes investigation harder.

SLF4J snippet:

```java
// Integration snippet: log is org.slf4j.Logger.
// failure is a Throwable; safeOrderId has been validated.
log.error("event=order.persist.failed orderId={}",
        safeOrderId, failure);
```

With JUL:

```java
// Integration snippet: logger is java.util.logging.Logger.
logger.log(java.util.logging.Level.SEVERE,
        "Order persistence failed", failure);
```

Calling `log.error("Failed: {}", failure.getMessage())` does not pass the full `Throwable`/cause chain. And a custom formatter that only inspects `record.getMessage()` like the demo will **not automatically include `record.getThrown()` in its output**: production use requires handling this field with a dedicated encoder.

## 14. Correlation, MDC, and Structured Context

An event can carry `requestId`, `traceId`, `spanId`, `messageId`, or `jobRunId`. Any chosen format must **keep IDs properly scoped and prevent mixing** across requests or threads.

With SLF4J:

```java
import org.slf4j.MDC;

// Integration snippet: requestId has been validated.
String old = MDC.get("requestId");
try {
    MDC.put("requestId", validatedRequestId);
    processRequest();
} finally {
    if (old == null) {
        MDC.remove("requestId");
    } else {
        MDC.put("requestId", old);
    }
}
```

This snippet requires `processRequest()` and the surrounding variables to exist. `MDC` neither emits events on its own nor guarantees that an encoder will output `requestId`. A Logback pattern can use `%X{requestId}`; a JSON encoder can export MDC entries as fields if configured to do so.

Be careful:

- Thread pools reuse threads: always clear/restore in `finally`.
- With `CompletableFuture`, executors, or WebFlux/reactive stacks, context does not automatically propagate across threads.
- A trace ID is not a business ID; a request ID does not prove user identity.
- IDs read from client headers can be spoofed or excessively long, so enforce validation and trust policies.
- Never use `requestId`, `traceId`, or `userId` as high-cardinality **metric labels**.

A clean format that lacks correlation fields when distributed analysis is needed is still a weak log design.

## 15. Cross-Service Consistency and Schema Versioning

A common problem in multi-service applications:

```text
Service A: traceId, orderId, durationMs
Service B: trace_id, order_id, elapsed
Service C: TraceID, order_number, time_ms
```

Even though all three emit JSONL, dashboards and queries have to deal with messy mappings. You need a **schema contract**:

1. **Field-name catalog** by domain and shared conventions.
2. **Concrete data types** for each field.
3. **Semantics**: where is duration measured from and to? Is `status` HTTP or business?
4. **Required vs. optional** per event type.
5. **Classification labels**: stable `errorCode`/`outcome`/`event` codes.
6. **Field ownership**: set by the application or by the collector.
7. **Versioning** for breaking changes or staggered service rollouts.
8. **Mapping** to storage/index fields or OpenTelemetry semantic conventions when needed.
9. **Compatibility tests** at both the encoder and collector.

Never change `"durationMs": 27` to `"durationMs": "27 ms"` in the same index without migration; storage may no longer aggregate properly. Never change the meaning of `order.created` from “DB committed” to “message accepted” while keeping the same event name.

Versioning can be `schemaVersion: 1` or a separate contract/release mechanism. Not every log line needs a version field if the receiver already knows the schema from the topic/index, but **semantic changes must be managed**.

## 16. Pretty JSON Is Not JSONL

JSON for debugging is sometimes pretty-printed:

```json
{
  "event": "order.create.result",
  "outcome": "SUCCEEDED"
}
```

This is valid JSON as a document, but it **spans multiple lines**. If a collector tails line by line expecting one event per line, pretty JSON can be split into multiple invalid records.

In files or stdout collected by a sidecar/agent, prefer **compact single-line JSON**; the log viewer can pretty-print after parsing. Unless the collector is explicitly configured for multiline/JSON framing, **do not pretty-print in production log streams**.

Also distinguish JSONL from **a single JSON array spanning the whole file**: an array requires closing delimiters to parse and is not friendly to appending and tail streaming like one-object-per-line formats.

## 17. Security: Format Must Go Hand in Hand with Redaction and Escaping

Choosing JSON does not make logging automatically safe. A JSON object can still contain:

```json
{
  "event": "login.failed",
  "password": "DO_NOT_LOG_THIS",
  "accessToken": "DO_NOT_LOG_THIS"
}
```

This is an example of **fields to avoid**, not a template to follow.

Risks:

1. **PII/secret leaks:** tokens, cookies, passwords, emails, addresses, financial or medical details.
2. **Log injection:** input containing CR/LF/control characters can forge text log entries.
3. **Oversized events:** raw request/response bodies filling queues, disks, or collectors.
4. **Dynamic fields:** user-controlled JSON keys causing schema/index explosion.
5. **Deep nesting / cyclic objects:** serializing arbitrary Java objects can waste resources, trigger recursion errors, or leak data.
6. **Exception messages:** drivers may include SQL, queries, URLs, or internal paths in `getMessage()`.
7. **Source ambiguity:** client-supplied `User-Agent`, correlation IDs, or IP forwarding headers can be spoofed.
8. **Index mapping explosion:** generating dynamic field names from user/resource IDs.
9. **Retained duplicates:** shipping logs to multiple sinks can widen data access exposure.

Practices:

- **Data minimization** in code; log only fields required for a defined purpose.
- Use an encoder/serializer with proper escaping rather than concatenating JSON strings manually.
- Validate and bound inputs (IDs, headers, reasons) before logging.
- For text, escape quotes, newlines, backslashes, and control characters; do not treat SLF4J placeholders as sanitizers.
- Use allowlists for field names and event codes.
- Avoid logging raw payloads; log IDs, entity types, and error codes instead.
- Enforce appropriate read permissions, retention, redaction, and encryption.
- Test with payloads containing quotes, newlines, tabs, control chars, Unicode, and very long lines.

**Format only determines representation; it does not determine what data is allowed to be stored.** Redaction must be applied at the right place in the pipeline and verified on the final data in storage.

## 18. Size, CPU, and Storage Cost

Key trade-offs to consider:

- **Text patterns** can be short and cheap when few fields are present, but querying individual fields may require heavy parsing.
- **JSONL** incurs overhead from repeated key names, quotes, and escaping. In return, parsers can preserve structured data.
- **Key=value** can be compact, though parser and escaping semantics depend on conventions.
- **OTLP / binary/protobuf** can fit modern transport, batching, compression, and typed fields, but requires an exporter/collector and dedicated observability setup.

Do not conclude “JSON is always faster than text” or “protobuf always saves space” without measuring. Performance depends on field count, message length, encoder, batching, compression, JVM allocations, and log rate.

A rough estimate:

```text
bytes_per_second ≈ events_per_second × average_encoded_bytes_per_event
bytes_per_day    ≈ bytes_per_second × 86,400
```

For example: **5,000 events/second × 800 bytes/event = 4 MB/second** (decimal MB), which equals roughly **345.6 GB/day before compression, replication, and index overhead**. If JSONL adds 200 bytes per event compared to text in this scenario, that adds roughly **86.4 GB/day** of raw data. This is an estimate, not a benchmark measurement of a specific application.

Format decisions must go alongside **sampling, log levels, retention, compression, and audit policies**. Never disable mandatory audit events just to cut encoding costs.

## 19. How Does Format Affect the Pipeline and File Rotation?

A log event travels through:

```text
Java code -> Logger -> Formatter/Encoder -> Appender
                                      |
                            file/stdout/network
                                      |
                           Sidecar/Node Collector
                                      |
                              Parse/Enrich/Buffer
                                      |
                           Central logging storage
```

When using line-based files or stdout:

- **One event per line** keeps tailing and parsing reliable.
- File rotation must coordinate with the collector (rename/inode/checkpoint) to avoid missed or duplicate reads.
- Logback, Log4j 2, and JUL have different rolling policies; format and rotation are **two separate decisions**.
- Encoders may flush according to appender rules; calling a logger does not mean the sink has received the event.
- Truncated/cut log events due to runtime or collector limits can produce malformed JSON.
- A JSON object can be split by transport line limits; enforce event size limits.
- When using a remote exporter, understand retries, backpressure, cancellation, and batch acknowledgments.
- If container stdout is collected by a node agent, a sidecar is unnecessary when the infrastructure already meets your requirements.

Structured JSONL written to disk **is not automatically crash-durable**. For guaranteed audit trails, design transactional/outbox mechanisms or proper durable storage paths; pretty text messages or complete JSON are no substitute.

## 20. Testing Formats: Verify Actual Output, Not Just Logger Calls

A test plan should cover:

| Case | Expectation |
| --- | --- |
| Normal INFO event | Contains accurate timestamp, level, event, and outcome |
| Duration | Number in JSON, clear units |
| Error code | Stable finite code, not an exception message |
| Request/trace ID | Properly scoped, validated, may be absent |
| String with quotes | JSON still parses cleanly |
| String with newline/tab | **One event per line** when using JSONL |
| Vietnamese Unicode | Accurate UTF-8 round-trip |
| Null / missing field | Follows schema; does not turn numbers into `"N/A"` |
| Throwable and cause chain | Emitted/bounded per policy |
| Suppressed exceptions | Not dropped outside policy |
| MDC/context in thread pool | Does not leak across requests |
| Async callback | Context propagates correctly |
| Text parser | Quotes/spaces/equals do not shift fields |
| JSON parser | Extracts fields and data types cleanly |
| File tail / collector | Does not split records, no drops/duplicates outside contract |
| Long event | Bounded and reported appropriately, never silently corrupted |
| PII / secrets | Not emitted to sinks outside policy |
| Schema migration | Old/new queries handle supported versions |
| High-cardinality labels | Dynamic IDs not used as metric labels |
| Logging level / filter | Clear which events are dropped and why |
| Full async queue | Drop/block policy and metrics exist; never assumed lossless |

A practical test automation workflow:

1. Write logs to a **test appender/handler** or dedicated temp file.
2. Emit events with stable IDs and timestamps.
3. For JSONL, use a **real JSON parser** to parse each line.
4. Assert field names/types/values, required fields, and optional/null handling.
5. Assert escaping, Unicode, stack traces, and control characters.
6. For text, use the **production parser** to verify round-trip parsing.
7. Pass output through a test collector if the pipeline has multiple stages.
8. After upgrading backend/encoder versions, re-run contract tests.
9. Verify redaction at the **final destination**, not only inside the JVM output.
10. Compare CPU/bytes/event/latency under realistic load to decide if optimization is needed.

### 20.1. Do Not Just Match a String Literal

A test like `assertTrue(output.contains("Order created"))` does not prove that `outcome` or `durationMs` is stored with the right type. For JSONL, parse and assert:

```text
event == "order.create.result"
outcome == "SUCCEEDED"
durationMs == 27  (number)
timestamp has explicit timezone
```

This is an **illustrative assertion**, not Java/JUnit syntax. For dynamically generated times and trace IDs, use test fixtures/injectable clocks or assert types and formats rather than snapshotting real-clock timestamps.

## 21. Roadmap for Migrating from Text to JSONL

If a legacy system uses text logs and needs to move to structured logs, proceed in a controlled manner:

1. **Audit sources:** logger/backend, patterns, appenders, collectors, multiline rules, dashboards, alert rules.
2. **Define the field schema:** timestamp, severity, event, service, request/trace IDs, outcome/errorCode, and required business fields.
3. **Standardize event codes** in the application rather than parsing prose messages.
4. **Select an encoder** compatible with your Logback/Log4j2/JUL version and test dependencies.
5. **Configure UTF-8 and JSONL** for line-oriented files/stdout.
6. **Update collector parsers:** distinguish legacy text from new JSON by source, not by guessing from message content.
7. **Use feature flags / staging rollouts** where the environment allows, measuring parse errors and bytes/event.
8. **Run schemas side by side intentionally:** do not accidentally ship two copies of the same event.
9. **Update queries, dashboards, and alerts** to use typed fields instead of regex.
10. **Review privacy:** structured fields can make certain IDs easier to query, so revisit read permissions and retention.
11. **Test failure modes:** crashes, async queues, rotation, oversized lines, and network outages.
12. **Remove legacy parsers** once data has been reconciled and migration is complete.

A practical option is to keep a **human-readable message** in a JSON `message` field while promoting `event`/`errorCode`/`operation` to standalone fields. It does not have to be “JSON only” or “no message at all.”

### 21.1. Two Different Outputs for Two Purposes

You can use a text console in local development and JSONL in production. You can also emit text and JSON via two appenders serving separate sinks. However, if both reach the same centralized system, define a deduplication policy so the same event is not counted twice.

If JSON is enabled in production while tests use text, escaping, stack trace, or schema bugs may only surface after deployment. Maintain **integration tests running the exact production encoder**, even when developer consoles use another format.

## 22. Common Mistakes When Choosing a Format

### 22.1. “Using JSON Means Good Structured Logging”

False if everything still sits inside `message: "Done"` with no operation, outcome, or IDs. JSON is only a representation container.

### 22.2. “A Simple Text Format Will Never Need a Schema”

If collectors use regex or SREs query by fields, text also needs conventions and a grammar. Otherwise, changing wording will break parsers.

### 22.3. “Key=Value Is Always Easy to Parse”

False when values contain spaces, quotes, `=`, newlines, or special Unicode without clear escaping.

### 22.4. “Pretty JSON Is Better Than JSONL for Collectors”

Multiline pretty JSON can split one event into broken chunks unless the collector supports matching framing/multiline rules.

### 22.5. “A JSON Encoder Automatically Masks Tokens”

A serializer only enforces escaping/encoding rules; **it does not decide which fields are allowed to be stored**. Data minimization and redaction are separate concerns.

### 22.6. “MDC Is Structured Logging”

MDC only provides context. The encoder must export it while ensuring it never leaks across threads or requests.

### 22.7. “More Digits in a Timestamp Means Higher Accuracy”

Printed precision does not guarantee corresponding real-clock accuracy. Timezone and clock skew still matter.

### 22.8. “Using Raw Exception Messages as errorCode Is Convenient”

Driver/JDK messages can change or expose sensitive data. Error codes must be stable, cataloged, and tested.

### 22.9. “OTLP Replaces All Log Schema Decisions”

No. You still have to design event names, attributes, severity, trace context, privacy, and exporter/collector lifecycles.

### 22.10. “JSONL Guarantees Zero Log Loss”

No. Format does not replace flushing, durability, rotation, retries, offsets/checkpoints, and sink acknowledgments.

### 22.11. “A Demo Formatter Is Good Enough for Production”

No. A production formatter must handle all `LogRecord`s, `Throwable`s, invalid Unicode, missing fields, concurrent logging, encoder performance, buffering, and I/O errors.

### 22.12. “More Fields in the Schema Is Always Better”

No. Extra fields increase cost, sensitivity exposure, and semantic ambiguity. Only add fields that answer real operational or business questions.

## 23. Checklist for Choosing a Format in a Java Project

- [ ] Identify the primary readers and the types of queries required.
- [ ] Distinguish format, schema, appender, transport, and delivery guarantees.
- [ ] Compare text patterns, key=value, JSONL, syslog/SIEM, and OTLP against existing infrastructure.
- [ ] If centralized querying is needed, prefer structured fields and reliable parsers.
- [ ] Design event codes, outcome/errorCode, IDs, and durations with explicit types.
- [ ] Standardize UTC/offset timestamps, severity, service, and environment.
- [ ] Ensure one event per line for JSONL; do not pretty-print tailed streams unless supported.
- [ ] Choose a real JSON encoder with escaping, Unicode, and `Throwable` support.
- [ ] Do not treat SLF4J placeholders as JSON fields if the backend does not emit structured attributes.
- [ ] Configure MDC/thread context and async propagation with proper scoping.
- [ ] Protect PII/secrets, validate inputs, prevent log injection, and cap event sizes.
- [ ] Never use raw IDs as metric labels or dynamic JSON field names.
- [ ] Monitor log volume, CPU/GC, bytes/event, compression, and retention.
- [ ] Verify file rotation, collector parsing, and line limits in the target environment.
- [ ] Test JSON parser round-trips, field types, exception chains, schema compatibility, and data at the sink.
- [ ] When changing formats, update parsers/dashboards/alerts and plan a compatible rollout.
- [ ] For mandatory audit logs, design separate durability/integrity/acknowledgment mechanisms rather than relying on JSONL.

**Conclusion:** **Choosing a format** means choosing a **data and operational contract** for Java logging. Text patterns are easy to read; key=value is compact if the grammar is clear; JSON Lines suits centralized logs and field queries; syslog/SIEM and OTLP fit their respective ecosystems. The best choice starts from **investigation goals, schema, typing, parseability, exception handling, security, and cost**, then verifies everything against the real backend and collector. **An event with clear semantics, minimal context, and consistent formatting matters far more than merely changing a file extension to JSON.**
