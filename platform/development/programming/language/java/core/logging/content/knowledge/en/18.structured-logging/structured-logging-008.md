# Log Collector Compatibility in Java Structured Logging

## 1. What Does "Log Collector Compatibility" Mean?

In a Java application, **structured logging** is the practice of emitting log records with clearly defined fields, such as `timestamp`, `level`, `event`, `service`, `order_id`, and `duration_ms`. However, just because an application produces a string that looks like JSON **does not mean** the log collection system will understand, retain, and allow accurate querying of those fields.

A **log collector** is a component that receives logs from an application or runtime environment, and can then decode, normalize, enrich with metadata, filter, and forward them to a storage/query system. Examples of tool families include Fluent Bit, OpenTelemetry Collector, Elastic Agent/Filebeat, Grafana Alloy, or an internally developed collector. Each tool has various receivers/inputs, processors, and outputs/exporters; there is no single universal configuration that works out of the box for every input.

**Log collector compatibility** means that **the producer and collector agree on an end-to-end contract** regarding:

1. **Collection source**: stdout/stderr, file, socket, HTTP, or OTLP.
2. **Transport and framing**: how bytes are sent, and where each event starts and ends.
3. **Encoding and format**: UTF-8, NDJSON, protobuf, syslog, GELF, etc.
4. **Schema**: field names, data types, required/optional values, and semantics.
5. **Timestamp**: time zone, unit, and whether it represents when the event was created or collected.
6. **Severity and metadata**: log level mapping, service name, trace/correlation ID.
7. **Collector pipeline**: parser, enrichment, filter, buffer, exporter, and storage.
8. **Reliability/security**: parse error events, data loss/duplication, sensitive information, TLS, and access control.

A well-designed logging pipeline enables operators to answer: "What are all the `payment_failed` records from `checkout-service` in the last 15 minutes?", "Which trace does this error belong to?", and "Were any records rejected by the collector due to schema errors?".

**Key takeaway:** "Java called `LOG.info`" only confirms that the code can generate an event. "The collector received bytes" only confirms one hop. "Logs appear on the dashboard with the right fields and timestamps" is a necessary part of integration verification.

## 2. The Full Path: Producer → Collector → Storage

```text
Java application
  |
  +-- Logger.info(...) / Logger.log(...)
  |          |
  |          v
  |    LogEvent / LogRecord
  |          |
  |          v
  |    JSON Encoder / Formatter / Layout
  |          |
  v          v
 stdout       file / network exporter
  |                    |
  +----------+---------+
             |
             v
      Collector input
             |
             v
    Framing & decoding
      (line/JSON/OTLP)
             |
             v
      Field extraction
  timestamp / severity /
   attributes / resource
             |
             v
   Enrichment & filtering
             |
             v
    Queue / exporter / TLS
             |
             v
       Log storage
             |
             v
       Query / alert
```

These steps may reside in different components, or some steps may be skipped when the transport already carries typed data. For example:

- The application prints **JSON Lines to stdout**; the container runtime captures the records; an agent reads container logs, extracts the `log` field, parses the JSON, and forwards it to the log store.
- The application writes an **NDJSON file**; a `filelog`/tail receiver watches the file and converts each line into a LogRecord with attributes.
- The application uses an **OTLP exporter**; the collector receives a telemetry structure over the OTLP protocol, **not** assuming it is an NDJSON string read via `readLine()`.

Before choosing technology or modifying Java code, you must identify the **integration point**. If the platform already collects stdout, adding a SocketAppender that sends directly to another collector can create **two duplicate log paths**. If the collector only reads files, configuring only a stdout ConsoleAppender may prevent records from reaching their destination.

## 3. Input Contract: What Does a Collector Need to Know?

You can start with a **producer–collector contract** table like this:

| Item | Illustrative Contract | Failure if Both Sides Mismatch |
| --- | --- | --- |
| Source | Java service stdout collected by agent | Collector watches the wrong file or only reads stderr |
| Framing | One JSON object on **a single line** | Multi-line pretty JSON gets split into multiple events |
| Encoding | UTF-8 | Vietnamese characters garbled, JSON contains invalid bytes |
| Timestamp | `timestamp`, RFC 3339/ISO 8601 with time zone, UTC | Logs placed in the wrong time window or ingested with receipt time |
| Severity | `severity_text` as string; collector has mapping | JUL's `WARNING` treated as unnormalized text |
| Service | `service_name` as a stable logical name | Logs not grouped under the right service |
| Event | `event` as a stable event code | Dashboards rely on variable message text |
| Duration | `duration_ms` as integer milliseconds | P95 calculations fail if logged as string or wrong unit |
| Trace | `trace_id`/`correlation_id` as optional string | Cannot correlate investigation flows |
| Missing field | Defined rule when not applicable | Parser or query confuses `null`, `""`, and missing keys |
| Exception | Exception field properly encoded | Stack trace breaks across multiple log lines |
| Limits | Bytes/event, rate, retention, sampling | Records silently truncated or dropped |

This is an **example contract for an application**, not a standard schema for Fluent Bit, OpenTelemetry, or Elastic ECS. A collector may require different names and map them to internal fields of the target system.

A "compatible" log needs to satisfy at least three layers:

- **Syntactic compatibility:** the collector can decode it.
- **Semantic compatibility:** fields, types, units, and severity are interpreted correctly.
- **Operational compatibility:** data reaches the right source/destination, is not dropped uncontrollably, and does not break the system under increased load.

## 4. JSON Lines (NDJSON): The Common Choice for stdout and Files

For line-oriented collectors, a simple contract is **each LogEvent corresponds to one valid JSON object on a single UTF-8 line**, terminated by a newline `\n`.

Example:

```json
{"timestamp":"2026-11-09T12:00:00Z","severity_text":"INFO","service_name":"order-service","event":"order_created","order_id":"ORD-101","duration_ms":25}
{"timestamp":"2026-11-09T12:00:01Z","severity_text":"WARNING","service_name":"order-service","event":"payment_retry_scheduled","order_id":"ORD-102","duration_ms":1500}
```

The two lines above are **two separate JSON objects**, not a JSON array. With a JSON Lines parser, each line can be decoded into one event.

Example that is **incompatible** when the collector reads line by line:

```json
{
  "timestamp": "2026-11-09T12:00:00Z",
  "event": "order_created",
  "order_id": "ORD-101"
}
```

This is **one valid JSON object when combined as a block**, but individual lines such as `"{"` or `"order_id": ...` are not complete JSON events. If you want to output multi-line JSON, the collector needs **multiline framing** configured specifically. With Fluent Bit, the documentation clearly distinguishes between JSON Lines and pretty-printed multiline JSON.

### Stack Traces and Newlines

A Java exception can be rendered across multiple lines:

```text
java.io.IOException: timeout
    at example.Gateway.call(Gateway.java:42)
    at example.Checkout.run(Checkout.java:17)
```

If the application outputs stack traces directly between NDJSON lines, the collector may treat each stack frame as a new record. There are two reasonable approaches:

1. **JSON encoder** serializes the stack trace as **a single string value** and escapes newlines using `\n` within the JSON string. The entire object remains on one physical line.
2. If the system must output multi-line text stack traces, configure an appropriate **multiline parser** in the collector to merge lines before parsing.

**Do not concatenate JSON strings manually** and assume quotes, backslashes, control characters, and Unicode are safe. In production, use your backend's JSON encoder or a well-tested serializer library.

## 5. Valid JSON Is Not Enough: Fields Must Have the Right Type and Meaning

Compare:

```json
{"event":"request_completed","duration_ms":150,"success":true}
```

with:

```json
{"event":"request_completed","duration_ms":"150","success":"true"}
```

Both lines are valid JSON. However, in the first line `duration_ms` is a **number** and `success` is a **boolean**; in the second line both are **strings**. A collector or indexing system may apply a different mapping, causing averages and boolean filters to fail.

Several rules should be agreed upon:

- **Units in field names:** `duration_ms` is milliseconds; `bytes_sent` is bytes; do not switch to seconds while keeping the same name.
- **Stable types:** do not log `status_code=200` as a number in service A and `"200"` as a string in service B if they share an index/schema.
- **Null values:** distinguish between **missing field**, `null`, `""`, and `"UNKNOWN"` when their meanings differ.
- **Field names:** standardize on `order_id`, `orderId`, or `order.id` per the contract; avoid arbitrary changes across teams.
- **Nested fields:** the collector must know whether nested objects are supported, whether there is a depth limit, and whether fields are flattened.
- **Duplicate keys:** avoid having `"status"` twice in the same object; parsers may keep the last value or exhibit incompatible behavior.
- **Numeric size:** very large integers can lose precision in some parsers or backends. Large IDs should be stored as identifier strings rather than used for arithmetic.
- **NaN/Infinity:** not valid numeric literals in standard JSON; a separate representation and policy are needed for non-finite numeric values.
- **Arbitrary data:** consider whitelisting observable fields; logging entire business objects can cause schema explosion, data leaks, and increased cost.

### Which Fields Should a Record Have?

An application schema might include:

| Field | Type | Meaning |
| --- | --- | --- |
| `timestamp` | RFC 3339 String | Time the event occurred |
| `severity_text` | String | Original log level from the logger |
| `service_name` | String | Logical service emitting the record |
| `environment` | String | E.g. `production`, `staging` |
| `event` | String | Stable event code |
| `message` | String | Human-readable description |
| `order_id` | String | Per-record business identifier |
| `duration_ms` | Number | Duration in milliseconds |
| `trace_id` | String, optional | Link to distributed trace |
| `schema_version` | Number/String per convention | Contract version of the record |

These fields are **suggestions for a custom contract**, not a claim that ECS and OpenTelemetry use these exact names. If your organization already has a schema, follow it to avoid repeated transformations.

## 6. Timestamp: Event Time or Collector Receipt Time?

A very subtle bug occurs when logs are ingested successfully but **appear in the wrong time window** on dashboards.

Distinguish between:

- **Event timestamp:** when the event occurred in the Java application.
- **Observed/ingest timestamp:** when the agent/collector or storage first saw the record.
- **Indexed timestamp:** when the data was written into the search store.

An event might be emitted at `12:00:00Z`, read by the collector at `12:00:02Z`, and reach storage later. If the collector fails to parse the original timestamp and substitutes the receipt time, event ordering during investigations can be wrong.

With JSON Lines, a readable choice is:

```json
{"timestamp":"2026-11-09T12:00:00.123Z","event":"order_created"}
```

The `Z` indicates UTC. If you use an offset like `+07:00`, preserve the exact offset meaning; do not write Vietnam local time and label it with `Z`.

Cases to verify:

1. **Field name:** does the collector look for `timestamp`, `time`, `@timestamp`, or another name?
2. **Format:** RFC 3339, epoch milliseconds, epoch seconds, nanoseconds, or a custom format?
3. **Timezone:** UTC, explicit offset, or the machine's default time zone?
4. **Precision:** milli/micro/nanoseconds; is anything truncated or converted to the wrong unit?
5. **Clock skew:** host clock drifting relative to the collector and other hosts.
6. **Missing/invalid timestamp:** does the collector drop the record, keep it as a string, or assign receipt time?
7. **Retention by which time:** event time or ingest time?
8. **Late-arriving data:** logs buffered for a long time may fall outside the current search window.

**Specifically with OpenTelemetry:** the log model distinguishes `Timestamp` and `ObservedTimestamp`. In the OTLP protocol, time can be represented as nanoseconds since the Unix epoch, which is **different** from a JSON text contract with an RFC 3339 `timestamp` field. A converter/processor is needed when moving between formats.

## 7. Severity: Preserve Log Levels and Normalize at the Collector

Java has multiple logging APIs:

| Java API | Common Levels | Considerations for Collector Mapping |
| --- | --- | --- |
| JUL (`java.util.logging`) | `SEVERE`, `WARNING`, `INFO`, `CONFIG`, `FINE`, `FINER`, `FINEST` | No `ERROR`/`WARN`/`DEBUG` in JUL level names |
| SLF4J | `ERROR`, `WARN`, `INFO`, `DEBUG`, `TRACE` | API does not dictate which severity number the collector assigns |
| Log4j2 | `FATAL`, `ERROR`, `WARN`, `INFO`, `DEBUG`, `TRACE` | Some levels have backend-specific names/values |
| Collector/OTel | Severity text and/or normalized severity number | Requires intentional mapping, not guessing by string name |

For example, JUL emits `Level.WARNING`. If the JSON encoder writes `"severity_text":"WARNING"` but a dashboard only filters on `"WARN"`, the event may still be collected yet **not appear in query results**. The solution is to standardize:

- Keep the **original severity text** for diagnostics.
- Normalize to groups such as `TRACE`, `DEBUG`, `INFO`, `WARN`, `ERROR`, `FATAL` at the collector if the backend requires it.
- Use an explicit mapping for JUL levels `CONFIG`, `FINE`, `FINER`, `FINEST`.
- If the backend uses a **severity number**, define the mapping and numeric type according to the target standard.
- Also test cases with **missing levels**, invalid values, or custom levels.

**Do not rewrite every Java log call just to satisfy a dashboard filter** when the collector can perform proper mapping and schema governance is in place. However, if the project already uses a unified event standard at the source, maintaining consistency at the producer reduces transform configuration.

## 8. Transport and Framing: Do Not Mix Protocols

A collector may support multiple inputs, but **address and port do not define the entire protocol**.

| Transport Path | Data Shape / Contract | What to Verify |
| --- | --- | --- |
| **Container stdout/stderr** | Logs from standard file descriptors; runtime may wrap with metadata | Does the agent collect the right stream? Is there a wrapper or line splitting? |
| **File tail** | Text, JSON Lines, or other format in files | File path, rotation, encoding, newline, checkpoint/offset |
| **TCP socket** | Byte stream, requires framing | Newline, length prefix, or custom protocol; SSL/TLS as required |
| **UDP** | Datagrams, may be lost or reordered | Packet size, format, is the collector listening on UDP? |
| **Syslog** | Header, priority, timestamp, and framing per standard/implementation | RFC format, TCP/TLS framing, hostname, app-name |
| **GELF** | Graylog event format and specific transport mechanism | GELF JSON/binary, compression, and proper framing |
| **OTLP/gRPC** | Protobuf requests over gRPC | Endpoint, TLS, service/method, OTLP schema, and auth |
| **OTLP/HTTP** | HTTP requests with binary protobuf or JSON-encoded protobuf | Content-Type, endpoint, `/v1/logs` path, auth, schema |

**Sending an NDJSON line to an OTLP/HTTP port does not make it OTLP just because the payload is JSON.** OTLP/HTTP JSON follows a protobuf-defined request structure, typically sent via HTTP POST with specific fields and envelopes. Sending `{"event":"..."}\n` over a TCP socket is likewise not automatically compatible with syslog or GELF.

If using Log4j2 `SocketAppender`, clarify on the collector side: does it expect **TCP text lines**, **TLS**, **GELF**, or **syslog**? If using File/Console Appenders, the collector needs the corresponding parser/receiver rather than "opening a port and figuring it out automatically."

### Docker/Container Wrapper

The application may print JSON Lines to stdout:

```json
{"timestamp":"2026-11-09T12:00:00Z","event":"order_created"}
```

However, in the JSON log file of some runtimes, the record is wrapped with runtime metadata, illustrated as:

```json
{"log":"{\"timestamp\":\"2026-11-09T12:00:00Z\",\"event\":\"order_created\"}\n","stream":"stdout","time":"2026-11-09T12:00:01Z"}
```

Here, the **outer JSON** describes the container log line; the inner `log` field is a **JSON string** from the application. The collector must know whether it is reading the outer wrapper or the raw application line. If it only parses the outer object, `event` will not automatically become a top-level field. You may need to extract `log` and parse JSON a second time, depending on the driver and pipeline.

Similarly, with other container runtimes, records may have their own headers, timestamps, or partial markers. Do not assume every runtime uses the exact format shown above.

## 9. Standalone Java 17+ Example: Writing JSON Lines to stdout

To see the principles with **plain JDK**, this example uses `java.util.logging.Logger` and `StreamHandler(System.out, Formatter)`. It emits two `LogRecord` instances with fixed timestamps, and the `Formatter` writes them as two JSON objects to stdout.

**Main purpose of the demo:** illustrates a **custom JSON Lines contract**, preserving `duration_ms` as a number, keeping JUL's severity text, and escaping characters that break JSON. Fixed timestamps are only used for **deterministic stdout** while learning; real applications must use actual event times.

**Limitations:** the custom formatter in this example is for learning purposes and only supports one event pattern with four positional parameters of known types. In production, use a **maintained JSON encoder / structured logging API**; do not turn this illustration into a general-purpose serializer library or schema for all event types.

Save as **`CollectorCompatibleDemo.java`**:

```java
import java.time.Instant;
import java.util.Locale;
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;
import java.util.logging.StreamHandler;

public final class CollectorCompatibleDemo {
    private static final Logger LOG =
            Logger.getLogger(CollectorCompatibleDemo.class.getName());

    private CollectorCompatibleDemo() {
    }

    // Quote a string into a valid JSON string for the demo.
    private static String quote(String value) {
        StringBuilder result = new StringBuilder("\"");

        for (int i = 0; i < value.length(); i++) {
            char c = value.charAt(i);

            switch (c) {
                case '"' -> result.append("\\\"");
                case '\\' -> result.append("\\\\");
                case '\n' -> result.append("\\n");
                case '\r' -> result.append("\\r");
                case '\t' -> result.append("\\t");
                default -> {
                    if (c < 0x20) {
                        result.append(String.format(
                                Locale.ROOT, "\\u%04x", (int) c));
                    } else if (Character.isHighSurrogate(c)) {
                        if (i + 1 < value.length()
                                && Character.isLowSurrogate(
                                        value.charAt(i + 1))) {
                            result.append(c).append(value.charAt(++i));
                        } else {
                            result.append("\\uFFFD");
                        }
                    } else if (Character.isLowSurrogate(c)) {
                        result.append("\\uFFFD");
                    } else {
                        result.append(c);
                    }
                }
            }
        }
        return result.append('"').toString();
    }

    private static final class JsonLineFormatter
            extends Formatter {
        @Override
        public String format(LogRecord record) {
            Object[] args = record.getParameters();
            String event = (String) args[0];
            String orderId = (String) args[1];
            String outcome = (String) args[2];
            long durationMs = (Long) args[3];

            return "{"
                    + "\"timestamp\":"
                    + quote(record.getInstant().toString()) + ","
                    + "\"severity_text\":"
                    + quote(record.getLevel().getName()) + ","
                    + "\"service_name\":\"order-service\","
                    + "\"event\":" + quote(event) + ","
                    + "\"order_id\":" + quote(orderId) + ","
                    + "\"outcome\":" + quote(outcome) + ","
                    + "\"duration_ms\":" + durationMs + ","
                    + "\"message\":"
                    + quote(record.getMessage())
                    + "}\n";
        }
    }

    private static LogRecord record(
            String timestamp, Level level, String message,
            String event, String orderId, String outcome,
            long durationMs) {
        LogRecord r = new LogRecord(level, message);
        r.setInstant(Instant.parse(timestamp));
        r.setParameters(new Object[] {
                event, orderId, outcome, durationMs
        });
        return r;
    }

    public static void main(String[] args) throws Exception {
        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.INFO);

        StreamHandler stdout =
                new StreamHandler(System.out, new JsonLineFormatter());
        stdout.setEncoding("UTF-8");
        stdout.setLevel(Level.INFO);
        LOG.addHandler(stdout);

        try {
            LOG.log(record(
                    "2026-11-09T12:00:00Z",
                    Level.INFO,
                    "Order created",
                    "order_created", "ORD-101",
                    "SUCCESS", 25L));

            LOG.log(record(
                    "2026-11-09T12:00:01Z",
                    Level.WARNING,
                    "Payment retry scheduled",
                    "payment_retry_scheduled", "ORD-102",
                    "RETRY", 1500L));

            stdout.flush();
        } finally {
            LOG.removeHandler(stdout);
            stdout.flush();
            // Do not close: StreamHandler.close() will close System.out.
        }
    }
}
```

Compile and run with JDK 17+ only:

```bash
javac -encoding UTF-8 CollectorCompatibleDemo.java
java CollectorCompatibleDemo
```

**Exact stdout:**

```json
{"timestamp":"2026-11-09T12:00:00Z","severity_text":"INFO","service_name":"order-service","event":"order_created","order_id":"ORD-101","outcome":"SUCCESS","duration_ms":25,"message":"Order created"}
{"timestamp":"2026-11-09T12:00:01Z","severity_text":"WARNING","service_name":"order-service","event":"payment_retry_scheduled","order_id":"ORD-102","outcome":"RETRY","duration_ms":1500,"message":"Payment retry scheduled"}
```

**Stderr from the application:** no lines during normal execution, excluding JVM messages if the environment fails.

### Why Can This Output Be Used to Test a Collector?

- Each `LogRecord` has an **explicitly set timestamp** via `setInstant` so the example does not depend on the runtime clock.
- `JsonLineFormatter` outputs strictly **one object per line**, with the newline character after `}`.
- `duration_ms` is represented as a **JSON number**, without double quotes.
- `severity_text` preserves JUL's `INFO` and `WARNING`; the collector needs a mapping if dashboards use `WARN`.
- `service_name`, `event`, `order_id`, `outcome`, and `message` are **application-defined** fields.
- The `quote` helper escapes double quotes, backslashes, control characters, and handles unpaired surrogates with a replacement character escape. This pattern helps explain **why a proper serializer must be used**.
- `StreamHandler(System.out, ...)` writes to stdout. JUL's `ConsoleHandler` writes to **stderr** by default, so do not swap the two handlers and expect the same result.
- `LOG.setUseParentHandlers(false)` prevents a JUL record from being printed a second time by a parent logger's handler.
- `stdout.flush()` ensures bytes are visible before exit; it does not prove the collector has durably stored them.

**Technical limitation:** this JSON Formatter depends on the order of four parameters in `LogRecord`. If another event type passes a mismatched count or type of parameters, the code can fail inside `format`. Therefore, it is only suitable for a demo. Real systems should use an API supporting attributes/key-value pairs and a standard JSON encoder, along with schema tests.

## 10. Verify Output and Parsers Before Real Integration

On Linux/macOS, separate stdout and stderr:

```bash
javac -encoding UTF-8 CollectorCompatibleDemo.java
java CollectorCompatibleDemo > events.ndjson 2> errors.txt
```

With this example, `events.ndjson` contains two complete JSON lines, while `errors.txt` is empty when there are no errors.

If Python 3 is available, you can run a standalone JSON parser check:

```bash
python3 -c 'import json,sys; rows=[json.loads(s) for s in sys.stdin if s.strip()]; assert len(rows)==2; assert all(isinstance(r["duration_ms"],int) for r in rows); print("parsed="+str(len(rows)))' < events.ndjson
```

**Stdout of the Python command when the data is valid:**

```text
parsed=2
```

This is a **syntax and partial type check**, not proof that a real collector has ingested the logs successfully. To test the actual collection path, run the correspondingly configured receiver/input.

Steps to verify collector connectivity:

1. Send the two demo records to the **exact source** the collector is reading, not a different file or stream.
2. Confirm the **input event count** seen by the collector is 2—not 0, 1, or more due to retries/duplicates.
3. Check that each event has `event`, `order_id`, and `duration_ms` with the **correct types**.
4. Confirm `timestamp` is parsed as **event time**, not merely stored as a string in the body.
5. Confirm `severity_text` is recognized or normalized properly.
6. Confirm `service_name` is attached from the right source and not overwritten incorrectly by a processor.
7. Query by a field, such as `event=order_created` or `order_id=ORD-101`.
8. Test inputs containing Vietnamese diacritics, double quotes, newlines, and exception messages.
9. Observe parser errors, records dropped, retries, and queue/flush behavior in the collector.
10. Test collector restarts and application restarts to understand log loss/duplication boundaries.

## 11. Using Log4j2 JsonTemplateLayout with a stdout Collector

For Log4j2 applications, you do not need to write a custom `JsonLineFormatter` as in the demo. Apache Log4j 2's **JsonTemplateLayout** can serialize a `LogEvent` using a JSON event template. It requires the separate `log4j-layout-template-json` artifact alongside compatible versions of `log4j-api` and `log4j-core`.

Example Maven dependencies (pinned to **2.26.1** for illustration, not meant as a mandatory latest version):

```xml
<dependencies>
    <dependency>
        <groupId>org.apache.logging.log4j</groupId>
        <artifactId>log4j-api</artifactId>
        <version>2.26.1</version>
    </dependency>
    <dependency>
        <groupId>org.apache.logging.log4j</groupId>
        <artifactId>log4j-core</artifactId>
        <version>2.26.1</version>
        <scope>runtime</scope>
    </dependency>
    <dependency>
        <groupId>org.apache.logging.log4j</groupId>
        <artifactId>log4j-layout-template-json</artifactId>
        <version>2.26.1</version>
        <scope>runtime</scope>
    </dependency>
</dependencies>
```

This is an **illustrative dependencies block**, not a complete POM; it must be placed inside `<project>` with your application's Maven/JDK configuration.

File `src/main/resources/log4j2.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<Configuration status="WARN">
    <Appenders>
        <Console name="JSON_STDOUT" target="SYSTEM_OUT">
            <JsonTemplateLayout
                eventTemplateUri="classpath:EcsLayout.json"/>
        </Console>
    </Appenders>
    <Loggers>
        <Root level="INFO">
            <AppenderRef ref="JSON_STDOUT"/>
        </Root>
    </Loggers>
</Configuration>
```

**Very important:** `EcsLayout.json` is Log4j2's **Elastic Common Schema (ECS)**-oriented template. It **does not emit the exact custom schema** used in `CollectorCompatibleDemo`. Do not switch from the JUL demo to Log4j2 and assume the output still has `severity_text`, `service_name`, or `duration_ms` with the same names.

With ECS, fields such as `@timestamp`, `message`, `log.level`, `service.name`, and `ecs.version` have their own defined semantics. To use an internal schema, you need a **custom JSON template** or a collector transform, while verifying the resolvers and actual output.

Log4j2 Java snippet **within a class that already has the dependencies**, not standalone:

```java
private static final org.apache.logging.log4j.Logger LOG =
        org.apache.logging.log4j.LogManager.getLogger(OrderService.class);

LOG.info("event=order_created order_id={}", orderId);
```

The `LOG.info` call above only emits a **parameterized message**. It does not automatically parse `order_id=ORD-101` into a JSON property named `order_id`. If the collector requires separate fields, you must use structured `LogEvent` data, context, or a configured schema transformation.

## 12. SLF4J and Logback: The Facade Does Not Decide the Schema

Many Java applications use `org.slf4j.Logger`:

```java
LOG.info("event=order_created order_id={}", orderId);
```

This determines the **logging API call**, not whether the final format is text or JSON. The backend/provider decides the encoder, appender, MDC, how `Throwable` is output, and metadata.

With **SLF4J 2.x**, the fluent API can attach key-value pairs:

```java
LOG.atInfo()
        .addKeyValue("event", "order_created")
        .addKeyValue("order_id", orderId)
        .addKeyValue("duration_ms", durationMs)
        .log("Order created");
```

This is a snippet inside a class that already has `LOG` and the relevant variables, **not a standalone runnable program**. Key-value pairs are passed into the logging event. **Whether they are emitted as JSON fields** depends on the backend/encoder and pipeline. Do not assume a plain-text `ConsoleAppender` will automatically turn `addKeyValue` into full JSON.

Logback has its own encoders/layouts and JSON encoder ecosystem. For collector compatibility, choose an encoder compatible with your **Logback/SLF4J version** and verify its actual output. Do not copy `log4j2.xml` XML into `logback.xml`: plugin names and syntax differ.

With JUL, `ConsoleHandler` sends logs to stderr with the default `Formatter`; if the collector only collects stdout or expects JSON, replace the handler/formatter or have the agent parse the agreed format. Two applications calling `Logger.info` with different backends can produce very different output.

## 13. Elastic ECS, OpenTelemetry, and Loki Are Not One Schema

Popular systems have their **own data models**:

| Ecosystem | Common Concepts / Fields | Compatibility Notes |
| --- | --- | --- |
| **Elastic Common Schema (ECS)** | `@timestamp`, `message`, `log.level`, `service.name`, `ecs.version` | Map fields and types per ECS; do not assume `timestamp` equals `@timestamp` in every pipeline |
| **OpenTelemetry log data model** | `Timestamp`, `ObservedTimestamp`, `SeverityText`, `SeverityNumber`, `Body`, `Attributes`, `Resource`, trace/span IDs | Typed model; if receiving JSON Lines from file/stdout, the collector must parse and map to the corresponding `LogRecord` fields |
| **Grafana Loki** | Labels, log line, and optionally structured metadata | Labels create streams; do not put high-cardinality IDs into indexed labels |
| **Fluent Bit** | Input, parser, filter, output | Configure source/format/parser; can parse JSON Lines or merge multilines per configured mode |
| **Custom collector** | Organization-defined schema | Requires contract documentation and producer/collector testing |

### Choosing a Format Based on the Consumer

If the target system uses ECS, you can emit ECS JSON directly from Log4j2 or transform at the collector. If the pipeline normalizes to OpenTelemetry, you can parse `timestamp`/`severity_text`/`service_name` from JSON and map them to `Timestamp`, `SeverityText`, and resource attributes. If you choose an **OTLP exporter**, you must send via the **OTLP protocol**, not arbitrary JSON text.

An application does not necessarily need to emit **three simultaneous formats** for ECS, OTel, and Loki. A more maintainable approach is having a **stable application contract** and placing transformation responsibilities at one or a few well-managed points. Identify the owners of those mappings, because they are critical code/config as well.

### Cardinality in Loki

In Loki, **each combination of labels** can create a stream. Continuously varying values like `request_id`, `trace_id`, `order_id`, or `user_id` should generally **not be indexed labels** because they create too many streams and increase cost. Those values can live in the log line or **structured metadata**, depending on the architecture.

Conversely, fields like `service`, `environment`, `cluster`, or `namespace` usually have lower cardinality and are better suited for stream classification. Exact rules depend on the version/deployment and how queries are organized.

**Parser compatibility does not equal storage model compatibility:** valid JSON using the wrong labels can still be ingested while rapidly degrading performance and increasing cost.

## 14. Example Mapping Between Application Schema and Collector

Suppose the application emits:

```json
{
  "timestamp": "2026-11-09T12:00:00Z",
  "severity_text": "WARNING",
  "service_name": "order-service",
  "event": "payment_retry_scheduled",
  "order_id": "ORD-102",
  "duration_ms": 1500,
  "message": "Payment retry scheduled"
}
```

This is **one JSON object formatted across multiple lines for readability**, not the actual file's NDJSON format.

An agreed mapping table might look like:

| Application Schema | Meaning | Example Target Mapping |
| --- | --- | --- |
| `timestamp` | Time `LogEvent` was created | OTel `Timestamp` or ECS `@timestamp` |
| `severity_text` | Original JUL level string | OTel `SeverityText`; map `WARNING` to WARN group if needed |
| `service_name` | Originating service | OTel `Resource` attribute `service.name` or ECS `service.name` |
| `event` | Event type name | Attribute/event classification per contract |
| `order_id` | Business identifier | Attribute; do not turn into a high-cardinality label |
| `duration_ms` | Numeric milliseconds | Numeric attribute; keep unit or convert explicitly |
| `message` | Human-readable description | OTel `Body` or ECS `message` |

This table is a **transformation plan**, not a guarantee that any given collector performs each mapping automatically. For example, `service_name` is not assumed to be `service.name` in every pipeline. You must configure the appropriate processor/transform or encoder.

**Do not substitute `ingest time` for `event time`** just to have a non-empty field. If a timestamp cannot be parsed, follow an explicit policy: flag invalid data, assign a marked receipt time, or route the record to a dead-letter/error path. Never silently corrupt latency calculations.

## 15. Contract Testing: Verifying Producer and Collector Together

A **contract test** can emit a curated dataset from a test application, have the collector parse it, and then verify the exact record count, fields, types, timestamps, and query results.

The test suite should cover these scenarios:

| Test Case | Data | What to Verify |
| --- | --- | --- |
| Simple event | `order_created` with `order_id` | One event, all fields intact |
| Two consecutive events | Two NDJSON lines | Not merged into one or split into many |
| Vietnamese diacritics | `message="Đã tạo đơn hàng"` | UTF-8 not corrupted |
| Quotes/backslashes | String containing `"` and `\` | JSON still parses cleanly |
| Newline in message | `\n` inside JSON string content | Does not create a third event |
| JUL severity | `WARNING` | Preserved or mapped to WARN where required |
| UTC timestamp | `2026-11-09T12:00:00Z` | Correct event time, not shifted by +7 hours |
| Numeric type | `duration_ms=1500` | Stored as a number, not a string |
| Missing field | No `order_id` on an event without an ID | Follows optional policy, no false errors |
| Exception | `Throwable` with cause | Investigable, does not break multiline framing |
| Oversized data | Message near collector limit | Dropped/truncated with metrics and policy |
| Collector restart | Sending logs during collector outage | Understand loss/duplication limits and queue state |
| Schema change | Old/new producers running in parallel | Collector accepts/maps per transition plan |

**End-to-end event counting** should distinguish:

- How many events the application **attempted to emit**.
- How many events the handler/appender **received** after level/filter checks.
- How many the collector **read**.
- How many the parser **decoded successfully**.
- How many the exporter **sent successfully**.
- How many the backend **ingested/indexed**.
- How many a query actually **returns** for the time range and filter conditions.

These numbers may legitimately differ due to filtering or sampling. However, if there is an unexpected discrepancy, you must know which stage caused it rather than concluding success merely because `LOG.info` threw no exception.

### Verifying No Duplicates

Sometimes an event travels **two paths**: Java prints to stdout and writes to a file; the collector reads both stdout and the file. Dashboards then show duplicate records. Another source of duplicates is exporter retries or downstream systems with at-least-once delivery.

When you need to distinguish an event from delivery attempts, consider a stable `event_id`/idempotency key for critical events. However, **regular logs do not automatically achieve exactly-once** just by adding an event ID; the backend needs an appropriate deduplication strategy.

## 16. Changing the Schema Without Breaking the Collector

Log schemas often become **operational contracts**, even if they started as a small formatter in Java.

Examples of breaking changes:

- `timestamp` changes from an RFC 3339 string to epoch milliseconds without changing the field name.
- `duration_ms` changes from a number to a string, or to `duration_s` without renaming.
- `service_name` is renamed to `service` while the collector still reads the old name.
- `event=payment_failed` is renamed to `event=payment_declined` without semantic distinction.
- `trace_id` is moved into a new nested object while queries still look at the root.
- A field that was previously an object becomes a string, causing a storage mapping conflict.

How to roll out changes safely:

1. **Identify consumers:** dashboards, alerts, saved queries, parsers, pipelines, ETL jobs, downstream apps.
2. **Define the new contract:** names, types, required/optional, enums, units, timestamp, privacy, and migration path.
3. **Add temporary dual-read support** if needed: the collector accepts both old and new schemas or maps both to canonical fields.
4. **Deploy and compare metrics** before removing the old parser.
5. **Use a schema version when needed** for incompatible changes where multiple versions coexist; no need to bump the version for wording tweaks no one depends on.
6. **Set up test fixtures** for critical events so CI pipelines catch accidental renames or type changes.
7. **Specify an end-of-support date** for the old schema if applicable.
8. **Monitor parse errors post-deployment**, because the application can still return HTTP 200 even when the log collector drops critical fields.

There is no rule that "every new field is backward-compatible." Adding fields is usually tolerated by flexible parsers, but some regex-based, positional, or strict-schema parsers may fail. Always test **actual consumers**.

## 17. Safe Logging: Sensitive Data, Escaping, and Source Limits

Technical compatibility is not a license to send all data to the collector. Once logs are centralized, they may be retained long-term, accessed by multiple teams, and traverse various infrastructure layers.

Checklist:

- **Never log** passwords, refresh/access tokens, API keys, OTPs, full card numbers, session cookies, or full sensitive payloads.
- **Limit to necessary fields:** an internal `order_id` may suffice for debugging without customer names or addresses.
- **Escape properly:** the JSON encoder must handle quotes, backslashes, control characters, and Unicode; messages with newlines must not forge fake events.
- **Control size:** collectors, container runtimes, and backends may truncate or reject oversized records.
- **Limit cardinality:** do not create a distinct field name or indexed label per user or request.
- **Access control:** review who can read logs and which fields pass through intermediate systems.
- **Transport security:** if pushing logs directly over the network, use appropriate TLS/authentication and protect credentials.
- **Retention/deletion:** a schema may be valid while retention policies still violate legal or internal compliance requirements.
- **Prevent log injection:** especially in text logs, newlines and control characters can spoof events; in JSON, use a context-appropriate serializer.
- **Do not trust `e.getMessage()` as clean data:** driver/client exceptions can contain file paths, URLs with secrets, or untrusted input.

In some projects, the collector has a **redaction** processor; this is a useful defense-in-depth layer, not a substitute for preventing secrets from leaving the application. Once data hits stdout/file, components upstream of redaction may already have seen it.

## 18. Pipeline Reliability and Error Monitoring

A collector does more than parse. It can buffer, batch, retry, identify sources, enrich metadata, filter, and export. Each stage has failure modes:

| Symptom | What to Check |
| --- | --- |
| No logs in collector | Wrong input/source; level disabled; stdout/stderr mix-up; wrong path/port |
| Bytes arrive but no events | Wrong framing/parsing; invalid JSON; character encoding error |
| Events exist but missing fields | Parser only keeps raw `message`; nested wrapper unparsed; transform dropped fields |
| Events in wrong time window | Timestamp unparsed; wrong timezone/epoch units; clock skew |
| Searching WARN misses JUL WARNING | Severity mapping not normalized |
| Two events split into many lines | Pretty JSON, multiline stack trace, or runtime split/truncate |
| One event appears twice | Two source appenders/agents; retries; logger additivity |
| Events "disappear" under high load | Queue full, sampling, rate limit, backpressure, drops in collector/exporter |
| JSON parses fine but backend rejects | Schema mapping conflict, invalid index, permissions, quota |
| Queries too slow/expensive | High-cardinality index labels, too many unnecessary fields |
| Java requests slow due to logging | Console/socket I/O, heavy formatter, full queue, or network congestion |
| Trace ID does not link | Wrong format, context not propagated across async boundaries, or wrong field mapping |
| Collector restart causes gaps | Non-persistent buffer, file checkpoint, lifecycle, or retry mechanism |
| Security alert from logs | Secrets logged, sensitive info in exceptions/metadata |

Reliability policies depend on requirements: standard diagnostic logs often tolerate some loss during incidents; audit data or financial state requires **dedicated reliable storage mechanisms**. Do not treat a `LOG.info("payment completed")` line as proof that a transaction committed.

**Do not put all logs on a single channel and expect both zero latency and zero data loss under all conditions.** There are trade-offs among latency, throughput, durability, cost, and availability. Design for realistic operational goals without claiming guarantees beyond what the appender/collector can provide.

## 19. An End-to-End Implementation Workflow for "Collector Compatibility"

Suppose a Java service is about to ship structured logs to production. Recommended workflow:

### Step 1 — Lock Down the Receiver and Data Path

Identify the exact collector, which receiver/input it uses, whether it reads stdout, files, OTLP, or a network protocol, how authentication/TLS works, and where data is finally exported. If the Kubernetes platform already collects stdout, start with **one clear path** and avoid sending directly over the network and via the agent simultaneously without a reason.

### Step 2 — Choose the Schema

Choose ECS, the OpenTelemetry model, or a custom application schema with documented mappings. Define field names, types, timestamps, severity, required/optional fields, event codes, and diagnostic fields.

### Step 3 — Choose the Encoder

With Log4j2, you can use `JsonTemplateLayout`; with Logback, choose an appropriate JSON encoder; with JUL, use a matching handler/formatter/adapter. Avoid hand-concatenating JSON in production. Verify the actual config emits **one record per line** if the collector uses line framing.

### Step 4 — Configure Timestamps and Context

Prefer event time with an explicit time zone. Attach `service.name`, environment, and instance if required by the pipeline. Add `trace_id`/`correlation_id` with proper lifecycle management; clear ThreadContext/MDC after requests and propagate context across async boundaries when needed.

### Step 5 — Run Canary Contract Tests

Emit a known set of events: INFO, WARNING/ERROR, Vietnamese messages, Unicode, exceptions, numbers, missing fields, and past timestamps. Read them back at the **final destination** to verify content and data types.

### Step 6 — Test Collection Failure Modes

Test collector shutdown, backend rejection, slow network, full queues, file rotation, and service restarts. Measure event counts, parse failures, dropped records, retries, and latency.

### Step 7 — Define Dashboards and Alerts on Proper Fields

Query by `event`, `severity`, `service`/`resource`, and stable fields. Do not rely solely on free-form message text. With Loki, keep index labels at reasonable cardinality.

### Step 8 — Codify the Contract in CI

Store **sample NDJSON/OTLP payloads** containing no real data; test schemas, field names, types, and serializers on every logging library version bump. Monitor ingestion errors after deployment; do not treat "tests pass" as proof that the production pipeline is always healthy.

## 20. Common Misconceptions

**1. "Printing JSON to the console means the collector parses it automatically."** No. The collector may only keep the raw line. You must enable a parser or use a typed input.

**2. "A multi-line JSON object is still compatible with a line-based parser."** No. You need one JSON object per line or configured multiline framing.

**3. "Strings and numbers in JSON are treated the same by the collector."** No. Types affect aggregations, indexing, and queries.

**4. "Any timestamp field name will work."** No. ECS, OTel, and internal pipelines have their own conventions; mapping is required.

**5. "JUL WARNING automatically becomes WARN on dashboards."** No. Severity mapping is needed if the target system uses different names/numbers.

**6. "Adding `trace_id` to the text message is enough for trace correlation."** Not necessarily. It must be preserved or extracted as a field understood by query/correlation tools.

**7. "Sending JSON Lines to the OTLP port works."** Wrong. OTLP has its own envelope, schema, and HTTP/gRPC protocol.

**8. "Docker logs are always just the application's raw JSON."** Some runtimes wrap records in an outer JSON; the collector must understand the format at the actual collection source.

**9. "Every field should become a Loki label."** No. High-cardinality values like `order_id`/`trace_id` create an excessive number of streams.

**10. "A successful log call means the collector has durably stored it."** No. You must account for queues, transport, collector, and backend; each stage has its own limits.

**11. "Two log records mean the business logic ran twice."** Not necessarily. The collector may be reading two paths, or retries/exports may have duplicated it.

**12. "Only the formatter needs updating when the schema changes."** Parsers, dashboards, alerts, and other consumers also need planned upgrades.

**13. "Using a key-value logger guarantees the JSON encoder outputs all keys."** No. The provider/encoder/template determines which fields are emitted.

**14. "Log fields can contain secrets because the collector will redact them later."** Unsafe: data has already traversed several layers before redaction.

**15. "Logs can be used as the official transaction ledger."** Only when using an audit system or event store designed with corresponding guarantees; regular observability logs can be lost, duplicated, or filtered.

## 21. Self-Check Questions

1. **What layers make up collector compatibility?** Source/transport, framing, encoding/format, schema, timestamp, severity, parser/exporter, and operations.
2. **What is NDJSON?** Multiple independent JSON objects, one object per line; not a single JSON array.
3. **Why can pretty JSON be misread by a collector?** Individual lines are not complete JSON events if the parser uses line framing.
4. **Are `"duration_ms":"1500"` and `"duration_ms":1500` different?** Yes; string and number are two different JSON types.
5. **What time zone does `2026-11-09T12:00:00Z` indicate?** UTC; if using local time, you must express the proper offset.
6. **Why does OTel distinguish Timestamp and ObservedTimestamp?** One is when the event occurred, the other is when it was observed.
7. **Is JUL `WARNING` guaranteed to match a backend filter for `WARN`?** No, mapping per the contract is required.
8. **Does OTLP/HTTP accept an arbitrary JSON line?** No. It requires a payload conforming to the OTLP schema and the appropriate HTTP endpoint/headers.
9. **What is needed to get an `order_id` JSON field from Log4j2?** Choose an appropriate template/encoder/attributes or collector transform; `"order_id=..."` in a message does not automatically become a field.
10. **Should Loki use every `request_id` as a label?** Usually no due to high cardinality; use the log body or structured metadata instead.
11. **Why test with a real collector even if the Java example prints two valid JSON lines?** The destination may still have parser, timestamp, mapping, or backend issues, or drop/duplicate events.
12. **If the collector reports successful ingestion but logs do not appear in the last 15 minutes, what should you check?** Event time, timezone, ingest time, query filters, retention, and ingestion delay.
13. **Should raw multi-line stack traces be put into an NDJSON file?** No if the collector requires one event per line; use JSON escaping/a dedicated field or a multiline parser.
14. **When logs go to both stdout and a file, what can happen?** Two collector inputs may collect the same event twice.
15. **Does a schema version replace testing?** No. It aids migration; you still need to test mappings and consumers.
16. **Does a log collector automatically guarantee exactly-once delivery?** You cannot assume so; inspect the ack/retry/dedup design and durability at each stage.
17. **Why shouldn't you log passwords for the collector to redact later?** The data has already left the application and may be exposed in layers prior to redaction.
18. **Does a log with `"event":"payment_completed"` prove payment was committed?** No. The authoritative business state store is the source of truth.
19. **What should a minimal end-to-end test verify?** Event count, parser pass, fields/types, timestamp, severity, queryability, and drop/duplicate errors.
20. **When switching logging backends, can `LOG.info` calls remain unchanged while compatibility breaks?** Yes. Layouts/encoders, schemas, providers, and context data may differ.

## 22. References

Useful official documentation for checking version-specific configurations:

- OpenTelemetry Logs Data Model: https://opentelemetry.io/docs/specs/otel/logs/data-model/
- OpenTelemetry Protocol (OTLP): https://opentelemetry.io/docs/specs/otlp/
- OpenTelemetry Collector filelog receiver (contrib): https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/main/receiver/filelogreceiver
- Fluent Bit, JSON parser: https://docs.fluentbit.io/manual/data-pipeline/parsers/json
- Fluent Bit, multiline parsing: https://docs.fluentbit.io/manual/data-pipeline/parsers/multiline-parsing
- Elastic Common Schema, base fields and `@timestamp`: https://www.elastic.co/docs/reference/ecs/ecs-base
- Grafana Loki, labels and cardinality: https://grafana.com/docs/loki/latest/get-started/labels/
- Apache Log4j 2, JSON Template Layout: https://logging.apache.org/log4j/2.x/manual/json-template-layout.html
- Oracle Java 17, JUL StreamHandler: https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/StreamHandler.html

**Remember:** structured logging is only truly useful when **the producer, collector, and storage agree on the same contract**. For Java logs, verify from **source → framing → JSON/schema → timestamp/severity → attributes → exporter → query**, not just that the console displays a JSON string. Use a tested structured encoder, keep field names and types stable, manage security/cardinality, and measure dropped, duplicated, or parse-failed events across the pipeline.
