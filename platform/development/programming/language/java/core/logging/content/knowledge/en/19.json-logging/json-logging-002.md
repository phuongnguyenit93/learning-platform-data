# JSON Encoder in Java Logging: from LoggingEvent to JSON Lines

## 1. What Is a JSON Encoder?

A **JSON encoder** is the component that converts a **logging event** into **valid JSON** data for output to the console, a file, a socket, or a log collector. In the **SLF4J + Logback** ecosystem, the encoder operates at the output layer of an `Appender`: it transforms an event containing a level, logger, timestamp, message, throwable, and context into structured bytes, rather than simply formatting a line of text with `PatternLayout`.

Example text log record:

```text
2026-01-12 10:15:00 INFO checkout.OrderService - event=order.created orderId=ord-17
```

A semantically equivalent JSON record:

```json
{
  "timestamp": "2026-01-12T10:15:00Z",
  "level": "INFO",
  "logger": "checkout.OrderService",
  "service": "checkout",
  "event": "order.created",
  "orderId": "ord-17",
  "durationMs": 125,
  "success": true
}
```

This is an **illustrative schema example**, not the exact set of default fields produced by any specific encoder. Different encoders use different field names and data types. For example, `timestamp` may be an ISO 8601 string or epoch milliseconds; `logger` may be named `loggerName` or `logger_name`. **Do not assume every encoder configuration emits the exact JSON shown above.**

Benefits of JSON:

- Log collectors can filter by `level`, `event`, `errorCode`, or `traceId` without parsing strings using complex regular expressions.
- Values of type **number**, **boolean**, **null**, **array**, and **object** can preserve their actual types when passed to the encoder via the appropriate API or serializer.
- Quotation marks, backslashes, newline characters, and Unicode can be **escaped according to JSON rules**.
- JSON Lines fits container stdout, file tailing, and centralized log pipelines that ingest one record per event.
- A consistent schema supports dashboards, queries, alerting, and correlating logs with distributed tracing.

**A JSON encoder does not replace a Logger, Filter, or Appender**: a DEBUG call blocked by the Logger will not be "recovered" just because JSON is enabled. Likewise, valid JSON does not automatically mean the data inside it is safe or durably stored.

## 2. Pipeline: Where Is a Log Event Encoded?

```text
Java code:
  logger.atInfo()
        .addKeyValue("durationMs", 125)
        .log("event=order.created")
             |
             v
         SLF4J API
             |
             v
      Logback Logger
      checks level/filter
             |
             v
     ILoggingEvent
      - timestamp/level/logger/thread
      - message, parameters, throwable
      - MDC, markers, key-value pairs
             |
             v
        Appender
        Console / File / RollingFile / ...
             |
             v
        JSON Encoder
        selects fields
        escapes and serializes
        produces bytes + delimiter
             |
             v
    stdout / .jsonl file / collector
```

Core concepts:

| Component | Responsibility |
| --- | --- |
| SLF4J `Logger` | API that emits events and passes message/arguments and throwable |
| Logback `Logger` | Checks level; creates and dispatches the event to an Appender |
| `ILoggingEvent` | Object carrying the properties of the event |
| `Appender` | Output destination and delivery path |
| `Filter` | Allows or blocks an event based on conditions |
| `Layout` | Formats an event into a `String` |
| `Encoder<ILoggingEvent>` | Converts an event into bytes to write to a stream |
| JSON parser/collector | Decodes JSON, maps fields, and stores or queries records |

According to the Logback API, `Encoder<E>` has the following typical methods:

```java
byte[] headerBytes();
byte[] encode(E event);
byte[] footerBytes();
```

These are **illustrative method signatures** inside the generic interface, not a standalone Java file. An Encoder is responsible for producing bytes for output; a Layout only produces text. `LayoutWrappingEncoder` bridges a Layout to the encoder mechanism, whereas a JSON encoder typically serializes data directly from the logging event.

**The filename does not make output JSON:** renaming `application.log` to `application.json` while still using a text `PatternLayoutEncoder` does not turn the output into JSON. Conversely, a JSON encoder can write to stdout or a `.jsonl` file; the actual content is what determines the format.

## 3. JSON Lines: One Event per Line

In production, the commonly used format is **JSON Lines / NDJSON**: each physical line contains **one JSON value**—for logging, typically one object—and ends with a newline.

```text
{"level":"INFO","event":"order.created","orderId":"ord-17"}
{"level":"WARN","event":"inventory.low","sku":"sku-9"}
{"level":"ERROR","event":"payment.failed","errorCode":"TIMEOUT"}
```

This example has three events, one per line. It is **not** a single large JSON array:

```json
[
  {"level":"INFO","event":"order.created"},
  {"level":"WARN","event":"inventory.low"}
]
```

A JSON array can be valid when exporting a complete document, but it is not suitable by default for a continuous stream that appends events one by one. If the appender stops abruptly, a document containing an array whose closing bracket has not been written may fail to parse. With JSON Lines, lines that have already been completely written can still be processed independently.

### 3.1. Data Containing Newline Characters

Suppose a user-supplied value is:

```text
hello
ERROR event=admin.login success=true
```

A compliant JSON encoder represents the newline **inside the JSON string** using an escape sequence, rather than letting the fake `ERROR` line become a separate record:

```json
{"message":"hello\nERROR event=admin.login success=true"}
```

In raw form, the JSON above contains the literal characters `\` and `n`, not a physical line break inside the value. Quotation marks in the data are also escaped as `\"`, and backslashes as `\\`. As a result, JSON Lines can preserve **one record per physical line** even when a message contains logical newlines.

**Caution:** JSON encoding makes data **syntactically valid**, but it does not prove the content is a genuine event, does not strip secrets, and does not sanitize dangerous values for downstream systems. Parsers or UIs that display the content must continue to treat untrusted data as untrusted.

### 3.2. UTF-8 and Delimiters

Use UTF-8 consistently from the application through to the file or collector. If the collector expects NDJSON, each event should end with a newline delimiter. Do not insert a plain-text header line such as `Starting application...` into the same JSON stream if the collector expects to parse every line, and do not mix standalone multi-line plain-text stack traces into that stream.

Framework or JVM startup warnings may be written to stderr without going through the JSON encoder, so the pipeline should distinguish between **application stdout**, **stderr**, launcher logs, and data emitted by the Appender.

## 4. Schema: Syntactically Valid JSON Is Not Automatically Queryable

An operational schema should be designed before choosing an encoder.

| Field | Typically Appropriate Type | Purpose |
| --- | --- | --- |
| `timestamp` | ISO 8601 UTC string or epoch milliseconds | Event timestamp |
| `level` | String | Level such as INFO/WARN/ERROR |
| `logger` or `loggerName` | String | Source by package/class |
| `service` | String | Stable service name |
| `environment` | String | dev/staging/prod per configuration |
| `thread` | String | Thread that emitted the event |
| `event` | String | Event type, e.g., `payment.retry` |
| `requestId`, `traceId`, `spanId` | String | Correlation/tracing |
| `errorCode` | String | Stable error code |
| `durationMs` | Number | Latency measured in milliseconds |
| `attempt` | Number | Retry/attempt count |
| `success` | Boolean | Success/failure outcome |
| `exception` | Object/string depending on encoder | Throwable details for diagnostics |

The field names above are **schema recommendations**, not a table of default fields across all backends. JSON allows both `null` and an **absent field**; agree on what each case represents.

### 4.1. Do Not Accidentally Turn Numbers into Strings

The following two events have different data types:

```json
{"durationMs":"125"}
```

```json
{"durationMs":125}
```

The first is a **string**, and the second is a **number**. If `durationMs` is used to compute percentiles, keep it as a number at serialization time. `MDC.put("durationMs","125")` typically stores a string; an encoder may emit it as a string unless a custom writer or serializer is used. Therefore, **MDC is not a default solution for producing typed numeric or boolean fields**.

Similarly, do not log a message like `"durationMs=125"` and expect the encoder to automatically parse it into a numeric field. The encoder only sees the formatted message (and structured arguments, key-value pairs, or markers if supported by the backend); it cannot infer an exact schema from free-form text.

### 4.2. Event Identification and Logger Names

- `loggerName` identifies the class or module emitting the event.
- `event` identifies the operation type, such as `order.created`.
- `traceId` links a request's path across multiple modules or services.
- `errorCode` describes a stable error category.
- `message` remains useful for humans, but should not be the sole key used to trigger alerts.

Do not embed user IDs or request IDs into **dynamic Logger names**: logger names should remain bounded by package/class; variable IDs belong in context fields with clear retention policies.

## 5. JSON Encoders in the Logback Ecosystem

There are at least two common approaches:

### 5.1. `ch.qos.logback.classic.encoder.JsonEncoder` — Built-in JSON Encoder

Logback provides a **built-in `JsonEncoder`** starting from the 1.3.8/1.4.8 branch onward. This encoder writes each `ILoggingEvent` as **one JSON object per line** with JSON escaping. In Logback 1.5.x, the encoder provides configuration flags to enable or disable individual top-level fields.

Fields present in the built-in format can include `sequenceNumber`, `timestamp` (numeric epoch milliseconds), `nanoseconds`, `level`, `threadName`, `loggerName`, `context`, `mdc`, `kvpList`, `message`, `formattedMessage`, and `throwable`, depending on the event and enabled flags. Do not confuse these field types or paths with the Logstash schema in the next section.

Minimal configuration example:

```xml
<encoder class="ch.qos.logback.classic.encoder.JsonEncoder"/>
```

This is a **fragment inside a FileAppender/ConsoleAppender**, not a standalone Logback configuration file. The built-in encoder is a good fit when Logback's default event schema is sufficient and you want fewer external dependencies.

**Important detail in Logback 1.5.x:** according to the documentation, top-level fields are enabled by default **except `formattedMessage`**. If you want the message with SLF4J placeholders substituted, configure:

```xml
<encoder class="ch.qos.logback.classic.encoder.JsonEncoder">
    <withFormattedMessage>true</withFormattedMessage>
    <withMessage>false</withMessage>
    <withArguments>false</withArguments>
</encoder>
```

With this configuration, the `formattedMessage` field is emitted, while raw `message` and `arguments` are disabled as specified. This is an intentional example: with the template `"orderId={}"` and argument `"ord-17"`, the formatted message is `"orderId=ord-17"`, whereas the raw message remains `"orderId={}"`. Depending on your pipeline, keep both or only one.

**Do not assume the built-in encoder is the Logstash encoder**: field names, how MDC and KVP are represented, timestamps, and exceptions may differ. If your collector requires a specific schema, map the schema or choose an appropriate encoder.

### 5.2. `net.logstash.logback.encoder.LogstashEncoder` — External Encoder with a Flexible Schema

The **logstash-logback-encoder** library provides `LogstashEncoder`, `LoggingEventCompositeJsonEncoder`, and related components. Common capabilities include:

- JSON with Logstash-style default fields, such as `@timestamp`, `message`, `logger_name`, `thread_name`, and `level`.
- Configuring global service fields (for example, `service` and `environment`).
- Filtering or renaming specific MDC keys.
- Emitting SLF4J 2 key-value pairs as structured fields.
- Composite JSON providers to define a custom schema.
- Configuring stack traces, masking/escaping, and event limits according to the library version.

Example **encoder configuration fragment inside an Appender**:

```xml
<encoder class="net.logstash.logback.encoder.LogstashEncoder">
    <timeZone>UTC</timeZone>
    <customFields>{"service":"checkout","environment":"prod"}</customFields>
    <includeMdcKeyName>traceId</includeMdcKeyName>
    <includeMdcKeyName>requestId</includeMdcKeyName>
</encoder>
```

This configuration is for an external library; it **does not run with only the JDK or built-in Logback**. You need a compatible `net.logstash.logback:logstash-logback-encoder` dependency: version **8.1** works with Java 11+, the Logback 1.5.x family, and Jackson 2.x; 9.x switches to Jackson 3 and requires Java 17+. When upgrading major versions, check the compatibility matrix rather than just bumping the version number.

`includeMdcKeyName` acts as an **allowlist of MDC keys to emit** in LogstashEncoder; unlisted keys are excluded from the MDC output. This is a useful control, but it does not replace **keeping secrets out of messages, throwables, and other fields**.

### 5.3. `LoggingEventCompositeJsonEncoder` for Custom Schemas

The composite encoder works with **JSON providers**. You can combine `timestamp`, `logLevel`, `loggerName`, `message`, `mdc`, `arguments`, `keyValuePairs`, `stackTrace`, or custom providers supported by your library version.

Illustrative configuration:

```xml
<encoder class="net.logstash.logback.encoder.LoggingEventCompositeJsonEncoder">
    <providers>
        <timestamp/>
        <logLevel/>
        <loggerName/>
        <threadName/>
        <mdc/>
        <message/>
    </providers>
</encoder>
```

This is a **configuration fragment**, not a complete `logback.xml`. Do not assume the composite encoder automatically adds all default fields; you must explicitly select the providers you need. When using a pattern provider that embeds JSON content, follow the JSON structure supported by the provider and verify the output rather than manually concatenating `%msg` into a raw JSON string.

### 5.4. Selection Table

| Requirement | Option to Consider |
| --- | --- |
| Modern Logback, need valid JSON Lines, and built-in schema is acceptable | Logback `JsonEncoder` |
| Want Logstash-style default fields and rich MDC/KVP options | `LogstashEncoder` from the external library |
| Want to explicitly define every field/provider and schema | `LoggingEventCompositeJsonEncoder` or a dedicated encoder |
| Only need human-readable text | `PatternLayoutEncoder`; JSON may not be needed yet |
| Application uses a framework that manages logging/structured logging | Prefer the framework's version-compatible mechanism |
| Application uses only JUL with no external libraries | Custom `Formatter` with a reliable JSON serializer or an appropriate JUL pipeline |

A system can have **two Appenders with two different encoders**, such as plain text on the console for developers and a JSONL file for the collector. Be sure to prevent **duplicate ingestion** if the collector reads both destinations as independent event sources.

## 6. Complete Example: Java 17 + Logback JsonEncoder + Verification with Jackson

This exercise uses **Java 17**, Gradle, SLF4J 2.0.17, Logback Classic 1.5.18, and Jackson Databind 2.17.2 to **read back and verify** the emitted JSON. The JSON encoder is a **built-in Logback component**; Jackson Databind in the demo project is used on the reading/test side and is not required by the XML configuration to encode logs.

Goals:

1. Use Logback `JsonEncoder` to write each event to `build/events.jsonl`.
2. Enable `formattedMessage`, and disable raw `message` and `arguments`.
3. Emit an INFO event with a numeric key-value pair `durationMs=125` and MDC `requestId=req-42`.
4. Emit a WARN event containing quotation marks and an **actual newline** in the message to test JSON escaping.
5. Emit an ERROR event with a `Throwable` to verify exception structure.
6. Read the three lines back with a JSON parser, assert the fields, and print **deterministic stdout** independent of clock, sequence numbers, or stack traces.

### 6.1. Directory Structure

```text
json-encoder-demo/
  settings.gradle
  build.gradle
  src/
    main/
      java/
        demo/
          JsonEncoderDemo.java
      resources/
        logback.xml
```

### 6.2. `settings.gradle`

```groovy
rootProject.name = 'json-encoder-demo'
```

### 6.3. `build.gradle` (Groovy DSL)

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.slf4j:slf4j-api:2.0.17'
    runtimeOnly 'ch.qos.logback:logback-classic:1.5.18'

    // Used only to parse and validate JSON in the demo program.
    implementation 'com.fasterxml.jackson.core:jackson-databind:2.17.2'
}

application {
    mainClass = 'demo.JsonEncoderDemo'
}
```

These versions are **pinned for the exercise**, not claimed to be the latest releases. In a real project, use version management/BOMs and appropriate security updates. Only **one SLF4J provider** should be present at runtime—here, Logback.

### 6.4. `src/main/resources/logback.xml`

```xml
<configuration>
    <appender name="JSON_FILE" class="ch.qos.logback.core.FileAppender">
        <file>build/events.jsonl</file>
        <append>false</append>
        <immediateFlush>true</immediateFlush>

        <encoder class="ch.qos.logback.classic.encoder.JsonEncoder">
            <withFormattedMessage>true</withFormattedMessage>
            <withMessage>false</withMessage>
            <withArguments>false</withArguments>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="JSON_FILE"/>
    </root>
</configuration>
```

Analysis:

- `FileAppender` writes to `build/events.jsonl`, inside the build directory used by Gradle.
- `append=false` ensures subsequent runs do not accumulate records from previous runs.
- `immediateFlush=true` flushes each event to the stream before the program reads it back for verification. This is **not** an fsync/durability guarantee against power loss.
- `JsonEncoder` writes events as JSON Lines, one record per line.
- `withFormattedMessage`, `withMessage`, and `withArguments` highlight the difference between the message template, arguments, and formatted message.
- Root level `INFO` allows INFO/WARN/ERROR; DEBUG is filtered out.
- The Appender does not print application logs to stdout, so the demo's console output contains only the explicit verification lines.

### 6.5. `src/main/java/demo/JsonEncoderDemo.java`

```java
package demo;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;

public final class JsonEncoderDemo {
    private static final Logger LOG =
            LoggerFactory.getLogger(JsonEncoderDemo.class);

    public static void main(String[] args) throws Exception {
        String previous = MDC.get("requestId");
        try {
            MDC.put("requestId", "req-42");

            LOG.atInfo()
                    .addKeyValue("durationMs", 125)
                    .log("event=order.created orderId={}", "ord-17");

            LOG.warn("event=client.input value={}",
                    "quote=\"A\"\nnext");

            LOG.error("event=payment.failed",
                    new IllegalStateException("upstream unavailable"));
        } finally {
            if (previous == null) {
                MDC.remove("requestId");
            } else {
                MDC.put("requestId", previous);
            }
        }

        Path file = Path.of("build/events.jsonl");
        List<String> lines = Files.readAllLines(
                file, StandardCharsets.UTF_8);

        if (lines.size() != 3) {
            throw new IllegalStateException(
                    "Expected 3 JSON lines, got " + lines.size());
        }

        ObjectMapper mapper = new ObjectMapper();
        JsonNode info = mapper.readTree(lines.get(0));
        JsonNode warning = mapper.readTree(lines.get(1));
        JsonNode failure = mapper.readTree(lines.get(2));

        if (!info.isObject() || !warning.isObject()
                || !failure.isObject()) {
            throw new IllegalStateException(
                    "Every line must contain a JSON object");
        }

        require("INFO".equals(info.path("level").asText()),
                "info.level");
        require("event=order.created orderId=ord-17".equals(
                info.path("formattedMessage").asText()),
                "info.formattedMessage");
        require("req-42".equals(
                info.path("mdc").path("requestId").asText()),
                "info.requestId");

        JsonNode pairs = info.path("kvpList");
        require(pairs.isArray() && pairs.size() == 1
                && pairs.get(0).path("durationMs").asInt() == 125,
                "info.durationMs");

        String expectedMessage =
                "event=client.input value=quote=\"A\"\nnext";
        require(expectedMessage.equals(
                warning.path("formattedMessage").asText()),
                "warning.escapedMessage");

        require("WARN".equals(warning.path("level").asText()),
                "warning.level");
        require("ERROR".equals(failure.path("level").asText()),
                "failure.level");
        require(failure.path("throwable").isObject(),
                "failure.throwable");

        System.out.println("records=3");
        System.out.println("first.level=INFO");
        System.out.println("first.requestId=req-42");
        System.out.println("first.durationMs=125");
        System.out.println("second.escapedMessageRoundTrip=true");
        System.out.println("third.hasThrowable=true");
    }

    private static void require(
            boolean condition,
            String label) {
        if (!condition) {
            throw new IllegalStateException(
                    "JSON validation failed: " + label);
        }
    }
}
```

The code above imports SLF4J only for logging; it uses Jackson to **validate the encoded data**. `LOG.atInfo().addKeyValue(...)` is the SLF4J 2 fluent API. In `JsonEncoder`'s built-in structure, key-value pairs can appear in the `kvpList` field; the program verifies the numeric value carried by the event.

### 6.6. Compiling and Running

In the `json-encoder-demo` directory, using **JDK 17** and a compatible Gradle installation:

```bash
gradle run --quiet
```

If the project includes the Gradle Wrapper, use `./gradlew run --quiet` on Linux/macOS or `gradlew.bat run --quiet` on Windows. The files above do not include a Wrapper, so an installed Gradle/JDK and access to download dependencies from Maven Central are required.

**Expected stdout when XML and dependencies match:**

```text
records=3
first.level=INFO
first.requestId=req-42
first.durationMs=125
second.escapedMessageRoundTrip=true
third.hasThrowable=true
```

Why is stdout deterministic?

- The program **does not print raw JSON** containing timestamps, sequence numbers, stack trace paths, or variable context.
- It checks the number of physical lines, parses each JSON object, compares meaningful fields against expected values, and then prints the results.
- The WARN line contains quotation marks and a newline in a Java String; after encode -> read JSON -> parse, the message **round-trips** accurately.
- The ERROR event carries a `Throwable`, which the encoder represents in the JSON structure; the program checks only for its presence rather than comparing JVM line numbers in the stack trace.
- The output path is `build/events.jsonl`, and `append=false` prevents leftover events from previous runs.

If the configuration is wrong or the JSON output does not meet expectations, the program **throws an exception instead of printing all six lines**. That is the benefit of an assertion-based verification check.

### 6.7. What Does the Actual JSON File Look Like?

In `build/events.jsonl`, each line is a **compact JSON object**. The illustration below **extracts only the key fields**, omitting the remaining fields and dynamic timestamp values:

```json
{
  "level": "INFO",
  "loggerName": "demo.JsonEncoderDemo",
  "mdc": {"requestId": "req-42"},
  "formattedMessage": "event=order.created orderId=ord-17",
  "kvpList": [{"durationMs": 125}]
}
```

**Do not treat this illustration as verbatim output**: the real `JsonEncoder` also includes fields enabled by default such as timestamp, context, and sequence; its output is written compactly on a single line.

For the WARN event with a logical newline, the JSON file contains the escaped sequence `\n` rather than a physical line break in the middle of the JSON object. Jackson parses it back and restores the newline properly; thus `Files.readAllLines` counts **three records**, not four.

### 6.8. Additional Experiments

- **Try removing `withFormattedMessage=true`:** because this field is disabled by default in Logback 1.5.x, assertions relying on `formattedMessage` will no longer pass.
- **Try re-enabling `withMessage=true`:** the JSON will also include the raw message template, showing the difference between `"orderId={}"` and the formatted string.
- **Try changing root level from INFO to ERROR:** the INFO and WARN events are dropped; the record-count check fails. This is **filtering**, not an encoder bug.
- **Try removing MDC:** `requestId` no longer has the expected value; the program flags a context validation failure.
- **Try switching output from FileAppender to ConsoleAppender:** JSON is printed to stdout; the output is no longer just the six verification lines, so the verification strategy must change.
- **Try logging a large object:** evaluate serialization behavior, event size limits, risk of leaking sensitive data, and performance impact.

## 7. Use Key-Value Fields Instead of Stuffing Everything into the Message

The following two approaches have different semantics:

**Free-form message:**

```java
log.info("durationMs={} success={}", 125, true);
```

This is an **illustrative code snippet**, assuming `log` already exists. The backend may only see the formatted message `"durationMs=125 success=true"` and will not automatically create separate numeric or boolean fields.

**SLF4J 2 fluent key-values:**

```java
log.atInfo()
        .addKeyValue("durationMs", 125)
        .addKeyValue("success", true)
        .log("event=request.completed");
```

Key-value pairs are attached to the event at the API level. **How they appear in JSON depends on the encoder**: Logback's built-in `JsonEncoder` may place them in `kvpList`, whereas `LogstashEncoder` can write the pairs directly as fields on the JSON object depending on configuration.

Do not assume from the method name `addKeyValue` alone that a field will be top-level. Inspect the actual JSON and check your collector's schema. If you need fields with `number`, `boolean`, or `object` types, test their types in a parser as shown in Section 6.

### 7.1. Avoiding Field Collisions

A JSON object can accidentally receive two fields with the same name from different sources:

- Standard fields such as `level` or `message` emitted by the encoder.
- Custom fields from `customFields`.
- An MDC entry named `level` or `message` set by application code.
- An SLF4J key-value pair that collides with a standard field name.

JSON parsers handle duplicate keys differently; many pick the last or first value, leading to inconsistent data. **Establish field-naming ownership rules**, such as prefixing context under `labels`/`mdc` or using allowlists and key renaming in `LogstashEncoder`. Test duplicate keys and the actual collector's schema mapping.

### 7.2. Field Cardinality

`requestId` and `traceId` are high-cardinality fields: useful for locating individual logs, but unsuitable as metric labels for unbounded grouping. `event`, `service`, and `environment` should have a relatively stable vocabulary for querying and alerting. Do not turn every dynamic ID into a field name or logger name.

## 8. MDC and Correlation IDs

MDC is commonly used to attach context to the current thread:

```java
String previous = MDC.get("traceId");
try {
    MDC.put("traceId", "trace-abc");
    logger.info("event=payment.started");
} finally {
    if (previous == null) {
        MDC.remove("traceId");
    } else {
        MDC.put("traceId", previous);
    }
}
```

This is a **code snippet**, assuming `logger` is already defined and `org.slf4j.MDC` is imported. With Logback's built-in `JsonEncoder`, MDC entries may appear in an `mdc` object; `LogstashEncoder` may emit entries differently depending on configuration. Do not assume all JSON encoders use the same `mdc.traceId` path.

**Thread pools and async:** MDC does not automatically propagate across every `ExecutorService`, `CompletableFuture`, or reactive pipeline. When a request switches threads, capture, propagate, and restore context using a supported mechanism. Each task must also clean up so subsequent requests do not accidentally inherit a stale trace ID.

**Security:** IDs read from external headers should have length and character restrictions, be validated for origin, and be used strictly as correlation data. Do not put access tokens, session cookies, user profiles, or entire HTTP headers into MDC just because the encoder can serialize them.

## 9. Throwable, Stack Traces, and JSON

An ERROR event with an exception:

```java
try {
    gateway.call();
} catch (RuntimeException ex) {
    logger.error("event=payment.failed errorCode={}",
            "GATEWAY_TIMEOUT", ex);
}
```

This is an illustrative snippet with `gateway` and `logger` already defined. When the overload accepting a `Throwable` is called properly, the backend retains the exception on the logging event; the JSON encoder decides how to represent it:

- An object containing class name, message, and frame list.
- A stack trace string with escaped newlines.
- Depth-limited fields or condensed details according to encoder configuration.

**Do not assume every encoder produces a `stack_trace` or `throwable` field in the same format.** For example, Logback's built-in `JsonEncoder` uses a `throwable` structure, whereas `LogstashEncoder` defaults to a `stack_trace` field when a `Throwable` is present. Before building dashboards or parsers, inspect the actual JSON emitted by the deployed version.

With JSON Lines, even when an exception has many stack frames, the encoder must preserve **one JSON object per physical line** via escaping or nested objects/arrays. Never write raw `printStackTrace` output to stdout on the same JSON Lines stream.

An exception message can contain URLs, usernames, or sensitive payloads; a JSON encoder **does not automatically redact data**. Strip disallowed information when creating the event and verify masking policies in the backend.

## 10. Controlling Fields and Schemas in Production

### 10.1. Keep Versions and Schemas Explicit

If downstream systems rely on JSON fields for alerts, changing encoders or renaming fields can silently break queries while the application keeps running. For example, when migrating:

```text
Logback JsonEncoder: loggerName, timestamp (numeric), mdc {...}
LogstashEncoder:     logger_name, @timestamp (string), MDC per configuration
```

This **illustrates two schema families**, not all available options. When migrating, check all of the following together:

1. Are timestamps and timezones represented the same way?
2. Do level names keep the same values?
3. Does `requestId` move from a nested object to top-level?
4. Is the formatted message field preserved or renamed?
5. Is `Throwable` serialized as an object/array or a string?
6. Do numeric and boolean key-value pairs keep their types?
7. Does the collector map the new schema while still handling older data?

Put schema changes through integration tests and roll them out in a controlled manner. A `schemaVersion` field can be helpful when pipelines evolve over time.

### 10.2. Use Allowlists Instead of Dumping Everything

Do not serialize entire domain entities via `toString()` or object-to-JSON when entities contain many uncontrolled fields. Prefer explicit, purposeful fields such as `event`, `errorCode`, `durationMs`, `attempt`, `requestId`, and system metadata.

A JSON encoder can handle many kinds of objects, but **the ability to serialize does not grant permission to log**. Sensitive data can enter via MDC, throwables, SLF4J key-value pairs, markers, or `customFields`; redacting one source does not cover all sources.

### 10.3. Size and Throughput

JSON repeats field names on every event, so it can consume more bytes than concise plain-text logs. Encoding also incurs CPU and allocation costs. In production, consider:

- Logging only fields needed for querying and diagnostics.
- Avoiding caller class/method/line extraction, which may require walking the stack and is expensive.
- Limiting message, payload, and stack trace sizes.
- Avoiding serialization of mutable or complex objects when unnecessary.
- Measuring throughput with the actual Appender, encoder, and collector.
- Using async appenders with controlled queue sizes, discard policies, blocking behavior, and shutdown handling.
- Reviewing collector indexing and retention costs.

**A JSON encoder does not make logging "asynchronous" automatically.** Sync vs. async behavior depends on the Appender and transport. An event being accepted or encoded does not guarantee it has been fsynced or confirmed as durably stored by the collector.

## 11. JSON Encoders in Container Environments

In Docker/Kubernetes, a common and effective pattern is:

```text
Application (SLF4J + Logback)
    -> ConsoleAppender + JSON encoder
    -> stdout: JSON Lines
    -> container runtime / log agent
    -> collector/parser
    -> search, dashboard, alert
```

The advantage is avoiding `RollingFileAppender` management inside each pod; the platform can attach metadata such as instance, pod, and namespace. However, you still need to:

- Ensure the collector expects the line format (NDJSON/JSONL).
- Separate application stdout from plain-text startup/launcher warnings if the parser is strict.
- Avoid printing banners, `System.out.println` debug lines, or plain-text stack traces onto the same JSON stream.
- Avoid double-ingestion when writing both JSON files and JSON console output.
- Manage rotation and retention in the collector and storage layer rather than expecting the encoder to handle them.
- Monitor for output backpressure, full queues, network errors, or pods terminating before flushing.

If another environment requires files, you can use **the same JSON encoder inside a FileAppender or RollingFileAppender**. Rotation and retention belong to the Appender/RollingPolicy, not the encoder.

## 12. Common Errors and Troubleshooting

| Symptom | Possible Cause | What to Check |
| --- | --- | --- |
| File ends in `.json` but contains only plain text | Appender still uses `PatternLayoutEncoder` | Configure the proper JSON encoder class |
| Collector reports JSON parse errors | Multi-line text mixed into JSON or unescaped manual concatenation | Inspect raw bytes, one object per line, and stdout/stderr sources |
| Message shows literal `{ }` | Viewing raw `message` instead of `formattedMessage` | Enable the appropriate field; check logger overload and arguments |
| `formattedMessage` missing from built-in JSON | Logback 1.5 disables this field by default | Set `withFormattedMessage=true` |
| `durationMs` field is a string | Number put into MDC or message text | Use typed key-value/provider and verify JSON types |
| `requestId` missing | MDC not set, lost across thread switches, or encoder excludes key | Check context propagation and MDC configuration |
| `WARN`/`DEBUG` not emitted | Logger/Appender level or filter drops the event | Inspect the logging pipeline before the encoder |
| Duplicate `level` field | Collision between standard field and custom/MDC/KVP | Rename keys, nest context, or use allowlists |
| `LogstashEncoder` configured but class not found | Missing artifact or incompatible version | Check dependencies/versions and `runtimeClasspath` |
| Jackson error after upgrading to 9.x | Major Jackson change from 2 to 3 | Review compatibility notes and dependency management |
| Stack trace split across multiple records | Plain-text `printStackTrace` printed outside JSON stream | Use JSON throwable fields or valid collector multiline rules |
| Logback config has no effect | Runtime backend is not Logback | Verify the active SLF4J provider and loaded config file |
| JSON timestamp differs from expectations | Encoder uses epoch ms instead of ISO, or wrong timezone | Standardize schema and time units |
| Duplicate logs in collector | Two Appenders/bridges/additivity, or ingesting both file and stdout | Trace event paths and ingestion sources |
| Valid JSON emitted, but logs lost under load | Async appender dropping events or collector bottleneck | Check queue size, discard policy, and shutdown/flush |
| Secrets appear in JSON log file | Over-serializing data/MDC/Throwable | Strip sensitive data at the source, apply masking, and restrict file permissions |

### Step-by-Step Investigation Order

1. Identify whether the runtime uses **JUL, Logback, Log4j 2**, or another backend; do not apply the wrong config.
2. Check Logger levels/filters and which Appender actually receives the event.
3. Verify the configured **encoder class**, not just the file extension.
4. Verify each physical line parses as a single JSON object using a standard JSON parser.
5. Check field names and **data types** on real INFO/WARN/ERROR events.
6. Test messages with quotes, backslashes, Unicode, and newlines; verify round-trip after parsing.
7. Test `Throwable` and MDC/trace IDs; verify context is not lost across async boundaries.
8. Check collector schema/mapping configuration, duplicate ingestion risks, and retention.
9. Test under high load, restarts, and shutdowns to understand buffering, flushing, and durability.

## 13. JSON Encoder Implementation Checklist

- [ ] Decide whether the goal is human-readable text or **machine-parseable JSON Lines**.
- [ ] Choose the right backend/provider and an encoder compatible with your actual versions.
- [ ] Distinguish between built-in Logback `JsonEncoder`, `LogstashEncoder`, and composite JSON encoders.
- [ ] Specify raw/template `message` vs. `formattedMessage`; do not guess from field names.
- [ ] Define a stable schema (names and types) for timestamp, level, logger, event, service, requestId/traceId, and errorCode.
- [ ] Preserve numeric and boolean types; do not put typed data into messages or MDC expecting automatic conversion.
- [ ] Test newlines, quotes, backslashes, and Unicode; every event must remain one JSON object per line.
- [ ] Restore/clean up MDC properly and propagate it across executors/async boundaries.
- [ ] Encode exceptions into parseable fields; never print plain-text stack traces into the JSON stream.
- [ ] Never log passwords, tokens, cookies, or sensitive payloads.
- [ ] Enforce event size limits, sampling policies, retention, masking, and file permissions.
- [ ] Validate with a real JSON parser and test the schema before rollout.
- [ ] Distinguish encoder output issues from Appender buffering, network/backpressure, and durability issues.
- [ ] Avoid double-ingesting the same event from multiple Appenders or file + console.
- [ ] Monitor parser errors, dropped logs, and disk/collector capacity.

### Technical References

- [Logback Manual — Encoders](https://logback.qos.ch/manual/encoders.html): `Encoder<E>`, `JsonEncoder`, JSON Lines, `withFormattedMessage`, and built-in fields.
- [Logback Manual — Appenders](https://logback.qos.ch/manual/appenders.html): ConsoleAppender, FileAppender, and output writing.
- [SLF4J Manual](https://www.slf4j.org/manual.html): logging facade, fluent API, key-value pairs, and parameterized messages.
- [logstash-logback-encoder documentation](https://github.com/logfellow/logstash-logback-encoder): LogstashEncoder, Composite JSON providers, MDC allowlist, and typed key-value fields.
- [Maven Central — logstash-logback-encoder 8.1](https://central.sonatype.com/artifact/net.logstash.logback/logstash-logback-encoder/8.1): example artifact for the Jackson 2 / Logback 1.5 branch.
- [RFC 8259 — The JSON Data Interchange Format](https://www.rfc-editor.org/rfc/rfc8259): JSON syntax, strings, and escaping.
- [JSON Lines](https://jsonlines.org/): one JSON value per line and UTF-8.

**Conclusion:** A **JSON encoder** in Java logging converts events into structured JSON/JSON Lines data for querying and monitoring. With modern Logback, the built-in `JsonEncoder` already supports JSON Lines and configurable fields such as `formattedMessage`; for richer schema needs, consider `LogstashEncoder` or composite providers. Real value comes from **a stable schema, properly typed fields, clear context and exception handling, safe escaping, and parser verification**, not merely from naming a file `.json`.
