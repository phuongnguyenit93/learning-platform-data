# What Is a JSON Log? Structured Logging in Java

## 1. The Concept of a JSON Log

A **JSON log** is a log record (log event) represented in **JSON (JavaScript Object Notation)** format. Instead of a single line of free-form text, each event is represented as an object made up of **named fields**, which can be strings, numbers, booleans, null, objects, or arrays.

Example of a traditional text log:

```text
2026-11-09T08:15:03Z INFO OrderService - Accepted order ORD-7 from channel WEB
```

The same event represented as JSON:

```json
{
  "@timestamp": "2026-11-09T08:15:03Z",
  "level": "INFO",
  "logger": "com.example.orders.OrderService",
  "message": "Order accepted",
  "event": "order_accepted",
  "orderId": "ORD-7",
  "channel": "WEB"
}
```

In the second approach, `orderId` and `channel` are not words that have to be "guessed" from the message; they are separate fields that a collection system can query directly, such as `orderId == "ORD-7"`.

**JSON is only a data format**, not a logging framework, log level, or storage guarantee. To get useful JSON logs, you also need schema design, a way to attach event data to records, an encoder/formatter, an output destination, and a collection system.

Common terms you will encounter:

- **Log event:** an event emitted by the application, such as an order creation or an error.
- **Structured logging:** organizing event data into fields with clear names and types.
- **JSON logging:** outputting log data as JSON; typically one way to implement structured logging.
- **JSON Lines / NDJSON:** multiple independent JSON objects, each on **a single physical line** in a file or stdout stream.
- **Encoder / Formatter / Layout:** the component that converts an in-memory event into its output representation.
- **Collector / shipper:** a tool that receives, transports, parses, stores, and indexes logs.

Not every sentence containing curly braces is structured logging. Real value comes from keeping fields consistent from the moment the application emits the event until it is queried.

## 2. Why Are JSON Logs Useful?

### 2.1. Querying by Field Instead of Only Searching Strings

With text logs:

```text
INFO order accepted ORD-7 channel=WEB
INFO order accepted ORD-8 channel=MOBILE
```

To find only order `ORD-7`, tools may have to rely on regex or substrings and face the risk of pattern changes. With JSON:

```json
{"level":"INFO","event":"order_accepted","orderId":"ORD-7","channel":"WEB"}
{"level":"INFO","event":"order_accepted","orderId":"ORD-8","channel":"MOBILE"}
```

A collector can filter by the `event`, `orderId`, or `channel` fields, provided the pipeline has parsed and indexed them.

### 2.2. Preserving Data Types

A JSON event can contain:

```json
{
  "event": "payment_attempt",
  "attempt": 2,
  "durationMs": 145,
  "success": false,
  "retryable": true,
  "amount": 125000.50,
  "tags": ["checkout", "retry"],
  "context": {
    "region": "ap-southeast",
    "source": "web"
  }
}
```

`attempt` and `durationMs` are **numbers**, `success` is a **boolean**, `tags` is an **array**, and `context` is an **object**. If everything is concatenated into a single message string, these types may be lost or have to be reconstructed by a parser.

Just because JSON supports numbers does not mean every identifier should be a number. `orderId`, `traceId`, postal codes, and strings with leading zeros should be kept as **strings**.

### 2.3. Helping Multiple Services Share a Schema

If every service emits `level`, `service`, `traceId`, `event`, and `message` following the same convention, investigating incidents across services becomes easier. However, **there is no single mandatory set of keys across all JSON logging systems**. Some platforms use `timestamp`, while others use `@timestamp`; OpenTelemetry may use names like `Timestamp` and `SeverityText` in its own data model.

When implementing, follow **your organization's or collector's schema** rather than assuming every backend outputs the exact same fields.

## 3. JSON Lines: Each Log Event Should Be One Line

When writing one independent JSON line per event, the output is commonly called **JSON Lines** or **NDJSON**:

```json
{"timestamp":"2026-11-09T08:15:03Z","level":"INFO","event":"order_accepted","orderId":"ORD-7"}
{"timestamp":"2026-11-09T08:15:04Z","level":"WARN","event":"stock_low","sku":"SKU-2"}
{"timestamp":"2026-11-09T08:15:05Z","level":"ERROR","event":"save_failed","orderId":"ORD-8"}
```

The three lines above **do not form a single JSON document** if concatenated verbatim; each line is **an independent JSON object**. That is what many log agents and collectors expect.

Conversely, a pretty-printed record spanning multiple lines:

```json
{
  "timestamp": "2026-11-09T08:15:03Z",
  "level": "INFO",
  "event": "order_accepted"
}
```

is still valid JSON, but if a collector defaults to treating **each newline as a separate event**, it will misread this as different log lines. Therefore:

1. Write **one complete JSON object on a single line** per event when using a line-based pipeline.
2. Separate events with a newline character after the JSON object.
3. Escape newlines **inside the message** as `\n` within the JSON string so the message does not create physical lines outside the object.
4. Do not print banners, diagnostic text, or raw exception stack traces interleaved into the same JSON stream if downstream requires every line to be parseable.
5. Specify a consistent charset, usually UTF-8.

**JSON Lines does not inherently guarantee global ordering across multiple threads/processes or exactly-once delivery.** It only defines how each event is represented in the stream.

## 4. What Should a Basic JSON Log Schema Include?

Not every application needs every field, but you should clearly define a core set of fields.

| Suggested Field | Type | Example | Meaning |
|---|---|---|---|
| `timestamp` or `@timestamp` | ISO 8601 string | `2026-11-09T08:15:03.125Z` | Time of the event |
| `level` or `severityText` | string | `INFO`, `WARN`, `ERROR` | Severity level |
| `logger` | string | `com.example.OrderService` | Logical source emitting the log |
| `service` or `service.name` | string | `orders-api` | Service producing the event |
| `environment` | string | `prod` | Deployment environment |
| `event` or `event.name` | string | `order_accepted` | Stable event name |
| `message` | string | `Order accepted` | Short human-readable description |
| `traceId` / `spanId` | string | `trace-42` | Correlation with distributed tracing |
| `requestId` | string | `req-42` | Links logs belonging to one request |
| `orderId` / `jobId` | string | `ORD-7` | Business identifier when permitted to log |
| `durationMs` | number | `145` | Duration, with unit clearly stated |
| `error.type` / `exception.type` | string | `java.io.IOException` | Error classification |
| `stackTrace` | string | `...` | Error stack trace, should be size-bounded |
| `schemaVersion` | string/integer | `"1"` | Schema version when compatibility stability is needed |

**Note on timestamps:** JSON has no dedicated datetime type. An ISO 8601 timestamp is actually a string, unless the schema chooses a numeric epoch in milliseconds or nanoseconds. Do not mix `seconds`, `milliseconds`, and `nanoseconds` in the same field without explicit rules.

**Note on measurements:** a field like `durationMs=145` is clearer than `duration=145` because the unit is explicit. When using an official observability standard, follow the names and units defined by that standard.

### 4.1. Use Stable Event Names

Prefer:

```json
{"event":"order_accepted","orderId":"ORD-7","message":"Order accepted"}
```

Instead of constantly changing the message and having to infer the event by parsing:

```text
Accepted #ORD-7!
Order accepted: ORD-7
Completed receiving order ORD-7
```

`event` should have a relatively stable set of values. `message` can be reworded for humans without breaking dashboards that count events by `event`.

### 4.2. Avoid Duplicate-Meaning Field Names

If service A uses `request_id`, B uses `requestId`, and C uses `correlationId` for the same concept, dashboards must support multiple aliases. Standardize upfront. You can use camelCase, snake_case, or dotted keys, but pick one convention and follow the schema contract.

When changing a schema, plan for backward compatibility: adding a new field is easier than changing the meaning of a field already used by alerts, indexes, or queries.

## 5. Distinguishing "Message Is JSON" from "Event Is Structured JSON"

The following two logs are **not equivalent**:

```json
{
  "level": "INFO",
  "message": "{\"orderId\":\"ORD-7\",\"event\":\"order_accepted\"}"
}
```

and:

```json
{
  "level": "INFO",
  "message": "Order accepted",
  "event": "order_accepted",
  "orderId": "ORD-7"
}
```

In the first case, `orderId` only exists inside the **message string**—that is, nested JSON as text. If the collector only parses the outer object, `orderId` **is not an independent field**. Querying it separately may require parsing JSON a second time or configuring an appropriate encoder.

In the second case, `event` and `orderId` are already separate fields. This is much more convenient for indexing and searching, as long as the system receives the right data types and schema.

Similarly, this SLF4J code:

```java
LOG.info("orderId={} event={}", orderId, "order_accepted");
```

is **message parameterization**; it does not automatically mean the backend will output `orderId` and `event` as two JSON fields. The backend may simply create a `message` field with the content `"orderId=ORD-7 event=order_accepted"`. To get structured fields, you must use the appropriate encoder API, structured arguments, MDC, or event model.

## 6. Why Should You Not Build JSON by Concatenating Strings?

A dangerous approach:

```java
// Wrong: illustrative snippet, may produce invalid JSON.
String line = "{\"message\":\"" + userInput + "\"}";
```

If `userInput` contains `"`, `\`, newline characters, or control characters, the result may no longer be valid JSON or may cause log injection. For example, the input might contain a forged line:

```text
Hello
ERROR user=admin action=approved
```

When concatenated manually into a JSON string, an unescaped newline can break the layout and create a fake event if the collector splits by line.

**Use a maintained and tested JSON serializer/encoder**, such as Jackson in Java or your logging backend's JSON encoder. A serializer handles escaping according to JSON rules; the application still needs to control sensitive data, size limits, data types, and schema.

In particular, do not rely on `message.replace("\"", "\\\"")` and assume it is enough: newlines, control characters, surrogate pairs, and many other cases still need to be handled.

JSON escaping **does not mean** masking sensitive data. A serializer can ensure a string is syntactically valid JSON while still writing an access token or password verbatim if the application puts them into the record.

## 7. At Which Layer Are JSON Logs Generated in Java?

For an application using SLF4J + a backend:

```text
Java business code
   |
   | LOG.info("event=...", ...)
   v
SLF4J facade / logging API
   |
   v
Provider/backend: Logback or Log4j 2
   |
   +-- Logger level/filter
   +-- MDC / event attributes
   +-- JSON encoder/layout
   |
   v
Console/File/Async appender
   |
   v
Collector → Parse → Index → Search/Dashboard
```

Simplified diagram: depending on the backend, data snapshotting, layout, encoder, and async scheduling may occur in different specific orders.

**JSON logging does not require changing business code APIs in every case.** If the backend already receives SLF4J events, many applications can switch from a text pattern to a JSON encoder/formatter purely through configuration. However, to add `orderId`/`traceId` as separate fields, the application still needs to emit data using a mechanism the encoder/backend understands.

### 7.1. JUL

The JDK's `java.util.logging` provides `LogRecord`, `Handler`, and `Formatter`. Standard JUL does not have a built-in general-purpose JSON formatter that automatically turns arbitrary custom fields into JSON. You can:

- Write a `Formatter` and use a reliable JSON serializer.
- Use a formatter/handler library that supports JSON.
- Route JUL logs through a bridge to a backend with a JSON encoder, if that fits your topology.

`LogRecord` has level, timestamp, logger name, message, parameters, thrown, and other metadata; it **does not have a built-in standard MDC map like dedicated contextual logging APIs**.

### 7.2. SLF4J + Logback

SLF4J is the facade, and Logback is the backend. The `{}` syntax only formats message parameters; to get true JSON, Logback needs a **compatible JSON encoder/layout** (built-in depending on the version or via an additional library) and a way to receive structured event fields.

Logback can use MDC with an appropriate pattern or encoder, but **MDC does not automatically generate request IDs or trace IDs**. The application or tracing instrumentation must supply the context.

### 7.3. SLF4J + Log4j 2

When using Log4j 2 as the backend, it provides its own layouts/encoders and context/structured data mechanisms depending on the version. The JSON layout must be configured properly; you cannot just rename the output file to `.json` or change the message template to a string with curly braces.

If application code calls SLF4J 2.x, the provider integrating with Log4j 2 must be compatible. Avoid having multiple SLF4J providers at the same time and avoid bidirectional Log4j 2 ↔ SLF4J bridges that create a forwarding loop.

### 7.4. Frameworks and Collectors

Spring Boot may already manage the default logging backend/system. When choosing JSON output, check the Boot/backend versions, dependency tree, and actual configuration. `logback-spring.xml` belongs to Spring Boot's Logback integration and does not apply directly to JUL or Log4j 2.

The collector must be configured to **parse JSON from the right stream/path**; simply emitting JSON strings does not mean every field will automatically be indexed.

## 8. Runnable Java 17 + Maven Example: Generating JSON Logs with a JUL Formatter and Jackson

The following example uses:

- **Java 17** and **Maven**.
- The JDK's `java.util.logging.Logger`, `LogRecord`, `ConsoleHandler`, and `Formatter`.
- The **Jackson** library to convert events into valid JSON instead of manual string concatenation.
- An illustrative `JsonEvent` type containing **structured attributes**, to distinguish real fields from the message string.

The output is **two independent JSON lines on stderr**. Timestamps are fixed in the demo so readers can verify the exact output; in real applications, event timestamps are typically taken from the system clock by the framework/`LogRecord`.

**This is an educational example**, not a recommendation for every production application to rewrite an entire logging backend. In production, prefer an officially supported JSON encoder/layout from your backend, along with schema policies and appropriate testing.

### 8.1. Directory Structure

```text
json-log-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── com/
                └── example/
                    └── logging/
                        └── JsonLogDemo.java
```

### 8.2. The `pom.xml` File

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>json-log-demo</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>com.fasterxml.jackson.core</groupId>
            <artifactId>jackson-databind</artifactId>
            <version>2.17.2</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>com.example.logging.JsonLogDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

The dependency versions here are **fixed values for the example**, not a claim that they are the latest or suitable for every security policy. In real projects, check your dependency management/BOM, supported JDK, security advisories, and update policies.

Jackson's `ObjectMapper` converts an ordered map into a JSON string; the Java code appends a newline to form JSON Lines. Do not treat Gson or Jackson as a "logging backend": they are only **serialization libraries**.

### 8.3. The `src/main/java/com/example/logging/JsonLogDemo.java` File

```java
package com.example.logging;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;

import java.time.Instant;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.logging.ConsoleHandler;
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class JsonLogDemo {
    private static final Logger LOG =
            Logger.getLogger("demo.OrderService");

    public static void main(String[] args) {
        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.ALL);

        ConsoleHandler console = new ConsoleHandler();
        console.setLevel(Level.ALL);
        console.setFormatter(new JsonLineFormatter());
        LOG.addHandler(console);

        try {
            emit(Level.INFO,
                    Instant.parse("2026-11-09T08:15:03Z"),
                    "Order accepted",
                    "order_accepted", "orderId", "ORD-7");

            emit(Level.WARNING,
                    Instant.parse("2026-11-09T08:15:04Z"),
                    "Stock is low",
                    "stock_low", "sku", "SKU-2");
        } finally {
            LOG.removeHandler(console);
            console.flush();
            console.close();
        }
    }

    private static void emit(
            Level level,
            Instant at,
            String message,
            String eventName,
            String idKey,
            String idValue) {

        JsonEvent event = new JsonEvent(
                level, message, eventName, idKey, idValue);
        event.setLoggerName(LOG.getName());
        event.setInstant(at);
        LOG.log(event);
    }

    private static final class JsonEvent extends LogRecord {
        private static final long serialVersionUID = 1L;
        private final Map<String, Object> attributes;

        private JsonEvent(
                Level level,
                String message,
                String eventName,
                String idKey,
                String idValue) {
            super(level, message);

            Map<String, Object> values = new LinkedHashMap<>();
            values.put("event", eventName);
            values.put(idKey, idValue);
            attributes = Collections.unmodifiableMap(values);
        }

        private Map<String, Object> attributes() {
            return attributes;
        }
    }

    private static final class JsonLineFormatter extends Formatter {
        private final ObjectMapper json = new ObjectMapper();

        @Override
        public String format(LogRecord record) {
            Map<String, Object> payload = new LinkedHashMap<>();
            payload.put("@timestamp", record.getInstant().toString());
            payload.put("level", normalizeLevel(record.getLevel()));
            payload.put("logger", record.getLoggerName());
            payload.put("message", formatMessage(record));

            if (record instanceof JsonEvent event) {
                payload.put("attributes", event.attributes());
            }

            try {
                return json.writeValueAsString(payload) + "\n";
            } catch (JsonProcessingException error) {
                throw new IllegalStateException(
                        "Could not encode JSON log", error);
            }
        }

        private static String normalizeLevel(Level level) {
            if (level == Level.SEVERE) return "ERROR";
            if (level == Level.WARNING) return "WARN";
            return level.getName();
        }
    }
}
```

### 8.4. Compiling and Running

Place the files in the proper package/path, open a terminal in the `json-log-demo` directory containing `pom.xml`, and run (requires JDK 17+, Maven, and permission to download dependencies):

```bash
mvn -q compile exec:java
```

The two lines **emitted by `ConsoleHandler` to stderr** will be:

```json
{"@timestamp":"2026-11-09T08:15:03Z","level":"INFO","logger":"demo.OrderService","message":"Order accepted","attributes":{"event":"order_accepted","orderId":"ORD-7"}}
{"@timestamp":"2026-11-09T08:15:04Z","level":"WARN","logger":"demo.OrderService","message":"Stock is low","attributes":{"event":"stock_low","sku":"SKU-2"}}
```

The program itself does not write to stdout. Maven may print its own build/plugin messages in different environments; the two lines above are the **output of the logging handler in the demo**, not every message from the build tool.

### 8.5. Detailed Explanation of Each Part

1. `JsonEvent` is an example class extending `LogRecord` that keeps `attributes` separate from `message`. `LinkedHashMap` preserves field order in the example; `Collections.unmodifiableMap` prevents direct modification of that data after the event is created.
2. `LOG.setUseParentHandlers(false)` prevents JUL from forwarding the same record to parent handlers, which would cause duplicate output.
3. `LOG.setLevel(Level.ALL)` and `console.setLevel(Level.ALL)` allow both INFO and WARNING in the demo.
4. `record.setInstant(...)` sets a fixed timestamp so stdout/stderr output can be verified; real applications should not hardcode event timestamps.
5. `Formatter.format(...)` builds a JSON object containing `@timestamp`, `level`, `logger`, `message`, and the `attributes` object when the record is a `JsonEvent`.
6. `normalizeLevel` maps JUL's `Level.WARNING` to the JSON label `WARN`. This is a **display/schema convention**, not a modification of the record's original level.
7. `ObjectMapper.writeValueAsString(...)` produces valid JSON and escapes characters inside strings; `+ "\n"` separates events into JSON Lines.
8. `ConsoleHandler` defaults to **stderr**. In production, verify whether your collector reads stdout, stderr, or both.
9. Because the code does not call `System.out.println`, the application's stdout is empty. `console.close()` releases handler resources when the demo exits normally.

For simplicity, `JsonEvent` uses `idKey` and `idValue` for business attributes. **That is not a standard structured logging mechanism provided by JUL.** It is a custom adapter in the example to illustrate that getting real fields requires passing data into an event/encoder capable of accepting fields. In large applications, using a well-maintained API/backend/encoder is better than building a complex custom `LogRecord` hierarchy.

### 8.6. What Happens If the Message Contains Special Characters?

Suppose a message or field contains double quotes, backslashes, or newlines. Jackson escapes them inside the JSON string according to JSON rules. A newline is represented by the two visible characters `\n` in the JSON output, and when parsed back, it becomes a newline character in the `message` value.

**Never replace only double quotes while ignoring other control characters.** Using a serializer is the baseline choice to avoid invalid JSON. However, if sensitive data is already in the message, the serializer will still output it; redaction and field allowlisting are separate responsibilities.

### 8.7. What About Adding Exceptions?

In JUL, an event can carry a `Throwable` via `record.getThrown()`. When designing a real JSON formatter, you should add corresponding fields, for example:

```json
{
  "level": "ERROR",
  "event": "order_save_failed",
  "error": {
    "type": "java.io.IOException",
    "message": "Storage unavailable",
    "stackTrace": "java.io.IOException: Storage unavailable\n\tat ..."
  }
}
```

This is **illustrative JSON**, not output from demo 8.3. If using Java to capture a stack trace, you must handle the `Throwable` chain, causes, and suppressed exceptions, and let the serializer escape the result. Do not log only `exception.getMessage()` if you need to investigate the stack or cause. Also, never include passwords, JDBC connection credentials, or sensitive payloads in exception JSON.

With JSON Lines, a stack trace can be a **string containing escaped `\n` characters**, keeping each event on a single physical line. With multiline plain text, the collector needs multiline configuration to merge stack traces if you want them grouped into one event.

## 9. Do You Need Jackson to Do JSON Logging?

**Not necessarily.** Jackson is used here to illustrate serialization. A dedicated logging backend can provide its own JSON encoder/layout or integrate its own serializer library. Depending on Logback, Log4j 2, Spring Boot, and their versions, configuration mechanisms differ.

What matters is not the name of the JSON library, but meeting these requirements:

- Every log event is converted into valid JSON matching the schema.
- The encoder reads the metadata and attributes the application actually provides.
- Values preserve their types, are properly escaped, and no banners corrupt the stream.
- Timestamp, severity, logger name, and exceptions are emitted consistently.
- Sensitive data is protected.
- The collector can parse the stream without unintended duplicates or dropped events.

### Logback JSON Encoder in Production

With Logback, a **text `PatternLayout`**:

```xml
<encoder>
    <pattern>%d{ISO8601} %-5level %logger - %msg%n</pattern>
</encoder>
```

**does not automatically create a JSON object**; the output is still pattern-based text. To get JSON, use a compatible JSON encoder/layout, declare the required dependencies, and configure the right class and field mappings for your version.

Do not rename `<file>orders.log</file>` to `orders.json` and assume that makes it JSON logging: a file extension does not determine the byte format.

### Log4j 2 JSON Layout

Similarly, a Log4j 2 `PatternLayout` emits text unless the pattern is configured to produce valid JSON reliably; **use a proper JSON layout/encoder** instead of manually assembling JSON fields in a simple `PatternLayout`, especially when messages contain dynamic data.

## 10. MDC and Correlation IDs in JSON Logs

For requests processed across multiple layers or services, fields like `requestId`, `traceId`, and `spanId` are very useful.

Example:

```json
{"level":"INFO","traceId":"trace-42","requestId":"req-42","service":"orders-api","event":"order_accepted","orderId":"ORD-7"}
{"level":"INFO","traceId":"trace-42","requestId":"req-42","service":"inventory-api","event":"stock_reserved","orderId":"ORD-7"}
```

In applications using SLF4J, **MDC (Mapped Diagnostic Context)** is one way to attach context to logging events. Example fragment:

```java
import org.slf4j.MDC;

// LOG is an org.slf4j.Logger already declared in a class.
MDC.put("requestId", "req-42");
try {
    LOG.info("event=order_accepted orderId={}", "ORD-7");
} finally {
    MDC.remove("requestId");
}
```

The snippet above is a **fragment**, not a standalone Java program. A JSON encoder can be configured to output MDC fields; **simply calling `MDC.put` does not guarantee that the field will appear in the JSON output**. You must verify the layout/encoder and schema.

**MDC is typically bound to the current thread's context.** When code switches to an `ExecutorService`, `CompletableFuture`, or callback, you must propagate and clean up the context. With thread pools, forgetting `MDC.remove`/`MDC.clear` at the proper lifecycle boundary can cause a subsequent request to inherit the previous request's ID.

JSON logging **does not automatically create distributed tracing**. Trace IDs and span IDs must be supplied by instrumentation or the application according to the chosen tracing system.

## 11. Normalizing Levels Across Backends

Severity names can differ:

| Meaning | JUL | Common SLF4J/Logback/Log4j 2 |
|---|---|---|
| Information | `INFO` | `INFO` |
| Warning | `WARNING` | `WARN` |
| Error | `SEVERE` | `ERROR` |
| Debug | `FINE` | `DEBUG` |
| More detailed | `FINER`/`FINEST` | `TRACE` (roughly equivalent) |

This is a **semantic comparison**, not a mandatory mapping for every adapter. If the collector expects `level="WARN"`, you need a stable mapping from JUL's `WARNING`. Do not map `SEVERE` to `INFO` just to make output look nicer: that distorts semantics and causes false alerts.

If using a standard such as OpenTelemetry Logs, the schema may distinguish `SeverityText` and `SeverityNumber` rather than using a single `level` string. Follow the rules of the standard in use, and do not infer severity by lexicographical string comparison.

**Do not add padding spaces to JSON fields**:

```json
{"level":"WARN"}
```

differs from:

```json
{"level":"WARN "}
```

Whitespace from a text pattern can cause queries like `level == "WARN"` to miss events. Padding and ANSI colors belong only in human-readable text layouts, not in normalized severity data.

## 12. JSON Logs and Exceptions: What to Preserve

An exception that is useful for investigation usually needs:

- `error.type`: exception class, such as `java.sql.SQLException`.
- `error.message`: the message, after checking whether it contains secrets.
- `stackTrace`: stack string including cause chain/suppressed exceptions when appropriate.
- `event`: a stable event code, such as `order_save_failed`.
- `traceId` or `requestId`: links to the execution context.
- `retryable`, `attempt`, or `operation` if meaningful to the business logic.

Do not just write:

```java
// Poor for investigation if you need the stack/cause.
LOG.error("save failed: {}", error.getMessage());
```

This is an illustrative SLF4J snippet assuming `LOG` and `error` already exist. If you want the backend to record the exception, pass the `Throwable` to the appropriate overload (check your API/version and argument count):

```java
// Illustrates how to log an error with a Throwable.
LOG.error("event=order_save_failed", error);
```

The JSON encoder must be configured to serialize exceptions properly. Some encoders keep the stack trace in a single string; others use a different structure or limit length. **There is no single standard exception JSON structure across all backends.**

When a collector parses JSON Lines, a stack trace containing escaped newlines inside a string will not create extra physical events. If the encoder prints the stack trace outside the JSON object, the collector may fail to parse it.

## 13. Querying, Indexing, and High Cardinality

JSON is easy to query by field, but adding every possible attribute is not always good.

Example:

```json
{"event":"http_request","method":"GET","route":"/orders/{id}","status":200,"durationMs":37}
```

The `route` field is a stable route template, allowing aggregation by API without generating too many distinct values. Logging raw URLs containing IDs or query parameters both increases cardinality and risks exposing tokens or PII.

Distinguish between:

- **Fixed fields:** `level`, `service`, `event`, `environment`, `http.method`.
- **Dynamic fields with investigative value:** `requestId`, `orderId`, `traceId` when permitted.
- **Arbitrary payloads:** bodies, headers, and full objects should generally not be logged by default.

Some collectors incur steeply higher costs when every record introduces new keys or too many unique values. Avoid **dynamic field names** (such as generating keys like `user_123456`) and control index mappings. Keep IDs as values of a stable field rather than as field names.

To filter JSON Lines in a local file, the `jq` tool can be helpful if installed separately (not part of the JDK):

```bash
jq -c 'select(.level == "WARN")' application.jsonl
```

This command assumes each line is a valid JSON object with a `level` field. On files containing text banners, multiline JSON, or truncated records, `jq` may report parse errors.

## 14. Is JSON Logging Always Faster Than Text Logging?

**No.** JSON provides benefits in structure and parseability, but serialization, escaping, object allocation, and writing many fields have CPU, memory, and I/O costs. Short text logs can be lighter; conversely, a well-optimized JSON pipeline can reduce downstream parsing work.

Performance depends on:

1. Events per second and the ratio of filtered-out events.
2. Size of messages, MDC/context, arrays/objects, and exceptions.
3. Encoder/serializer and allocation policies.
4. Console/file/network appenders, buffered I/O, and downstream collectors.
5. Whether async appenders/queues, batching, and compression are used.
6. Increased log volume from bloated schemas or large payloads.

### JSON and Async Appenders Are Separate Concepts

- A **JSON encoder** determines how an event is **represented**.
- An **async appender** determines how events are **queued and offloaded to a separate thread** for processing.
- A **rolling policy** determines how **files are split by size or time**.
- A **collector** determines how logs are **gathered, shipped, parsed, and indexed**.

Enabling JSON does not automatically enable async logging, rotation, or retention. Enabling async does not guarantee zero log loss; queues can fill up, and events can be dropped or remain in memory when a process crashes. You must test shutdown/flush behavior and overflow policies.

Do not use JSON logs as the sole transactional record when business requirements demand durability, exactly-once delivery, or tamper-evident auditing. You may need a transactional outbox, event store, or dedicated audit trail.

## 15. Security and Privacy

JSON makes looking up data easier, so the risk of **exposing information through structured fields** is also more significant.

### 15.1. Do Not Log Secrets

Do not log passwords, API keys, access tokens, session cookies, card numbers, connection strings with credentials, or payloads containing unnecessary personal information. Do not assume the `DEBUG` level is safe: real data can end up in files, backups, collectors, or test environments using production data.

Use an **allowlist of permitted fields**, rather than only blocklisting a few sensitive terms. For business IDs, consider masking, hashing, or pseudonymization in line with operational and legal requirements.

### 15.2. Escaping Is Not Redaction

A JSON serializer solves **syntax**: turning quotes, control characters, and newlines into a valid JSON string. It **does not decide** what data should be hidden.

An event containing `"password":"my-secret"` is still valid JSON, but it is a security bug.

### 15.3. Prevent Log Injection and Schema Breakage

Do not let user input determine JSON object keys or insert it directly into an unescaped JSON template. Use a serializer and fixed schema field names. If a message contains newlines, the collector should receive it as a valid JSON string within a single JSON Line.

### 15.4. Access Control and Retention

JSON files and streams may be shipped to multiple systems. You need:
- Role-appropriate log access permissions.
- Encryption in transit and at rest according to policy.
- Managed rotation, retention, deletion, and quotas.
- Schema reviews to avoid retaining unnecessary data.
- Auditing of who has permission to query or export sensitive logs.

JSON does not automatically encrypt data or authenticate the origin of an event.

## 16. Deploying in Containers and Distributed Systems

Many containerized Java applications write logs to **stdout/stderr** for a runtime or agent to collect. JSON Lines is a popular choice because each record can be parsed independently.

However, you must align on:

- **Which stream:** stdout, stderr, or both? Some tools assign severity based on the stream; do not accidentally configure the collector to ignore one stream.
- **Which schema:** services should share field names, timezone conventions, level mappings, and data types.
- **Which metadata:** pod/container/service labels may be added by the collector; avoid duplicating them or letting user input spoof metadata.
- **Size limits:** collectors or platforms may truncate overly long lines, making the JSON invalid.
- **Exceptions:** stack traces should be in a properly escaped JSON string/field.
- **Ordering:** multiple threads/instances have no global order; use event timestamps and correlation IDs.
- **Delivery:** agent restarts, network outages, and retention limits can cause loss or duplicates; JSON formatting does not solve this.
- **Latency:** an event emitted now may reach the collector later due to queuing, batching, or backpressure.

If writing JSON Lines to files, align on file patterns, how the agent tracks rotation/renaming, and retention. Do not have the app write both a JSON file and JSON console logs while the collector ships both unintentionally; this can double dashboard counts.

## 17. Common Mistakes When Using JSON Logging

| Symptom | Possible Cause | How to Verify / Fix |
|---|---|---|
| Collector reports JSON parse error | Interleaved text banners, multiline JSON, unescaped message | Check each line with a JSON parser; use a JSON encoder |
| `orderId` field cannot be searched | It is inside the `message` string | Put it in a separate structured field |
| JSON is cut off mid-line | Collector line-length limit or crash/partial write | Check max event size, batching, and pipeline |
| Timestamp has wrong timezone | Inconsistent server timezones | Standardize on ISO 8601/UTC or schema-defined zone |
| `level` is `WARNING` but dashboard searches `WARN` | JUL and backend use different level names | Map levels intentionally and consistently |
| JSON looks valid but has wrong type | `durationMs` was written as a string | Check serializer, schema, and index mapping |
| Missing `requestId`/`traceId` | Context not attached or not emitted by encoder | Check MDC/tracing and async boundaries |
| Two events on one line | Missing separating newline | Append a newline after each object |
| One exception split into multiple events | Raw stack trace printed outside JSON | Serialize the exception into a field and escape it |
| One event counted twice | Both console and file shipped, multiple appenders/bridges | Check topology and collector sources |
| JSON contains sensitive data | Fields/`Throwable` not filtered, relying only on serializer | Use allowlists, masking, and retention controls |
| Running Logback but file is still text | Using a text `PatternLayout` | Choose the right JSON encoder class/version |
| Only renamed file extension to `.json` | Byte format did not change | Change the formatter/encoder and verify with a parser |
| JSON logs lost under high traffic | Async queue drops, I/O or collector errors | Measure queue depth, loss, shutdown, and pipeline |
| Parse failure due to ANSI colors | Colored pattern writing into JSON stream | Disable colors on machine-readable output |
| Broken alerts after renaming a key | Schema changed without updating old queries | Use versioning and backward compatibility |

### Quick Troubleshooting Workflow

1. Identify the **actual backend/encoder running**; do not rely solely on SLF4J imports.
2. Grab **one raw line** from stdout/file before the collector and verify it is a valid JSON object.
3. Check timestamp, level, logger, message, and business fields.
4. Verify that fields actually have the right types and names per the schema.
5. Check escaping of quotes, backslashes, newlines, and Unicode.
6. Check exceptions and event context on a real request.
7. Compare the raw record against the parsed/indexed data in the collector.
8. If data is present in the raw log but missing in the dashboard, inspect the collector, parser, index, and retention before rushing to change business logic.

## 18. Practice Exercises

### Exercise A — Text to JSON

Given the line:

```text
2026-11-09T08:15:03Z WARN PaymentClient - Retry attempt 3 for order ORD-7
```

Design JSON with the fields `timestamp`, `level`, `logger`, `event`, `attempt`, and `orderId`. Do not write `attempt` as a string if the schema defines it as a number.

A reasonable result:

```json
{"timestamp":"2026-11-09T08:15:03Z","level":"WARN","logger":"PaymentClient","event":"payment_retry","attempt":3,"orderId":"ORD-7"}
```

### Exercise B — Distinguishing Message JSON

Given:

```json
{"level":"INFO","message":"{\"event\":\"order_accepted\",\"orderId\":\"ORD-7\"}"}
```

Is `orderId` a top-level field?

**Answer:** No. It is inside the message string. To query it directly, the encoder must emit it as a structured field, or the collector must explicitly parse the message a second time.

### Exercise C — JSON Lines

A program uses pretty-printing to output each JSON event across five lines. The collector treats each newline as a separate event. What can happen?

**Answer:** The collector may report parse errors, drop invalid fragments, or split a single event into multiple separate lines. The solution is to use compact JSON (one object per line) or configure framing/multiline parsing accurately for the pipeline.

### Exercise D — Security Mistake

A developer adds the full `http.headers` to JSON logs to debug authentication errors. The headers contain an Authorization bearer token.

**Answer:** The JSON is still valid, but it is dangerous. Log only allowlisted safe headers/metadata, mask or omit credentials, and restrict view permissions and retention. Never treat a JSON encoder as a security mechanism.

## 19. Checklist Before Putting JSON Logging into Production

- [ ] Each event is output as **one JSON object per line** if using JSON Lines.
- [ ] Formatter/encoder uses a reliable serializer, not manual JSON string concatenation.
- [ ] Core keys and data types follow the shared schema.
- [ ] Timestamp format, timezone, and precision are consistent.
- [ ] Levels have a clear mapping between JUL and SLF4J/Logback/Log4j 2 if needed.
- [ ] Event names are stable; `message` is for humans and attributes are for machines.
- [ ] `orderId`, `traceId`, and `requestId` are real fields when the pipeline needs to query them.
- [ ] Context is set, propagated across async boundaries, and cleaned up properly.
- [ ] Exceptions are serialized in a controlled way without breaking the single-line rule.
- [ ] No unnecessary secrets or PII are included; field allowlists/redaction are in place.
- [ ] No dynamic field names are generated that cause cardinality or index-mapping explosions.
- [ ] Raw output has been tested with a JSON parser before sending to the collector.
- [ ] stdout/stderr streams, file rotation, duplicates, and queue loss have been checked.
- [ ] Inputs containing quotes, newlines, backslashes, Unicode, and large payloads have been tested.
- [ ] A plan exists for schema versioning, parse-error monitoring, and rollback.
- [ ] Dashboards, queries, and alerts have been verified after switching from text to JSON.

**Conclusion:** A JSON log represents each **logging event** as a JSON object with clearly named and typed fields, typically emitted as **JSON Lines** so centralized systems can parse and query it conveniently. It is different from stuffing a JSON string into `message`. In Java, the application supplies events and context, while the formatter/encoder of JUL, Logback, or Log4j 2 handles serialization. JSON improves observability, but it **does not replace** level policies, sensitive-data controls, async/rotation/retention settings, or resilient collector design.
