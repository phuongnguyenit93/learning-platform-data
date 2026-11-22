# Migrating Text Logs to Structured Logging in Java

## 1. Why Migrate from Text to Structured Logging?

In a Java application, text-based logs typically start out as human-readable sentences:

```text
2026-01-01 10:15:30 INFO OrderService - Created order O-17 amount=120000 VND
2026-01-01 10:15:31 ERROR PaymentService - Payment failed for O-17: gateway timeout
```

These are **mock data examples**, not logs running in a specific system. A human reader can understand the content, but a machine trying to answer the following questions has to parse strings:

- Over a 15-minute window, how many transactions failed due to `GATEWAY_TIMEOUT`?
- Find all events related to `trace_id=tr-42` across multiple services.
- Group `payment.failed` counts by environment, version, or dependency.
- Distinguish `amount=120000` as a **number** rather than a piece of text.
- Query records where `retryable=true` without matching the literal text `retryable=true` appearing inside a descriptive sentence.

**Structured logging** is the practice of representing each log event as a set of **named fields and values**, typically serialized as JSON or another structured data format. For example:

```json
{
  "timestamp": "2026-01-01T10:15:31Z",
  "level": "ERROR",
  "service": "checkout",
  "environment": "production",
  "event_code": "payment.failed",
  "order_id": "O-17",
  "error_code": "GATEWAY_TIMEOUT",
  "retryable": false,
  "trace_id": "tr-42",
  "message": "Không thể hoàn tất thanh toán"
}
```

In this example, `retryable` is a boolean, `event_code` is a value from an event catalog, and `order_id` is a consistently named field. A collector can index, filter, aggregate, and display by field without having to guess sentence structure.

**Migration is not just changing a console pattern into a JSON-looking string.** A proper migration requires designing a schema, changing how data is emitted in Java code, configuring the backend, testing the encoder/collector, maintaining compatibility with legacy queries, and protecting sensitive data.

## 2. Distinguishing Message, Parameter Substitution, and Structured Fields

These layers are often confused:

| Concept | Role | Example |
| --- | --- | --- |
| Message | Human-readable descriptive sentence | `"Cannot complete payment"` |
| Parameter substitution | Filling arguments into a template, commonly `{}` in SLF4J | `log.info("order={}", orderId)` |
| Structured fields | Attributes with stable names, types, and meanings | `"order_id": "O-17"`, `"amount_minor": 120000` |
| Encoder/layout | Converts a logging event into output bytes | Logback JSON encoder |
| Collector/parser | Collects and parses the emitted data | Agent reading container stdout |

A call like:

```java
log.info("order={} amount={}", orderId, amount);
```

usually produces a **formatted message** such as `order=O-17 amount=120000`. It **does not guarantee** that the collector receives two fields named `order` and `amount`. They may still reside solely inside the `message` field as a string.

By contrast, a fluent SLF4J 2.x call:

```java
log.atInfo()
        .addKeyValue("event_code", "order.created")
        .addKeyValue("order_id", orderId)
        .addKeyValue("amount_minor", amountMinor)
        .log("Đã tạo đơn hàng");
```

can pass **key-value pairs** into the logging event. To turn them into actual JSON fields, **the backend/encoder must support them and be configured to emit them**. Calling `addKeyValue` alone does not automatically guarantee JSON output.

In this article, code snippets referencing `log`, `orderId`, or `amountMinor` without declarations are **illustrative in-application snippets**, not standalone Java programs. Complete runnable examples appear in later sections.

## 3. What Limitations Does Text Logging Have?

Look at three message styles that all mean a transaction failed:

```text
Payment failed for order O-17 due to timeout
payment.error order=O-17 code=TIMEOUT
Order O-17 payment rejected by upstream: timeout=3000ms
```

If a query only searches for the string `"Payment failed"`, it misses the other two forms. If a regular expression is used to extract the order ID, the parser can break whenever a developer changes wording, language, delimiters, or adds new data.

Other risks include:

1. **Inconsistent field names:** `orderId`, `order_id`, and `order` appear interchangeably.
2. **Inconsistent types:** the number `1000` today becomes `"1,000"` tomorrow.
3. **Lack of business semantics:** only a sentence like `"Something failed"` with no event code or error code.
4. **Data buried in stack traces:** important fields are hidden inside a multi-line text block.
5. **Hard to filter without fields:** finding a specific request requires searching the entire message, easily matching similar values.
6. **Fragility on wording changes:** dashboards and alerts relying on regexes or fixed phrases can break after a refactor.
7. **Sensitive data exposure:** concatenating full requests or exceptions into text can accidentally log tokens or personal data.
8. **Hard to distinguish event kinds:** the same word `failed` might represent a recovered retry or a final failure.

Structured logging solves many of these issues, but **it does not automatically make logs completely reliable data**. Log loss due to buffers, filters, collectors, or rotation can still happen; sensitive data can still be logged if the application passes it in.

## 4. Designing the Schema Before Rewriting Code

A **schema** is the contract covering fields, names, data types, semantics, and stability across versions. You should not start a migration by finding every `log.info` call and stuffing each sentence into hand-built JSON.

An illustrative schema for a `checkout` service:

| Field | Recommended Type | Meaning |
| --- | --- | --- |
| `timestamp` | Standard timestamp string with timezone, or target timestamp type | When the event occurred |
| `level` | String with a well-defined value set | `INFO`, `WARN`, `ERROR` |
| `service` | String | Logical service name |
| `environment` | String | `dev`, `staging`, `production` |
| `logger` | String | Source logger/class/package name |
| `event_code` | Stable string | Event type, e.g., `order.created` |
| `message` | String | Short human-readable description |
| `trace_id` | Optional string | Correlates distributed activity |
| `request_id` | Optional string | Correlates a single request |
| `order_id` | Optional string | Order identifier; preserves leading zeros if any |
| `amount_minor` | Integer/long | Money in the smallest unit per convention |
| `currency` | String using currency code | `VND`, `USD` |
| `error_code` | Catalogued string | `GATEWAY_TIMEOUT`, `DB_UNAVAILABLE` |
| `retryable` | Boolean | Whether retry is possible as assessed at event time |
| `exception_type` | String on error | Exception class name |
| `stack_trace` | String or structure per encoder | Location and cause chain |

**Not every event needs every field.** An `order.created` event typically does not need `error_code` or a stack trace; a `payment.failed` event needs error context. The schema should separate **common fields** from **event-specific fields**.

### Naming and Typing Rules to Standardize

- Pick one convention, such as `snake_case` for JSON keys: `order_id`, `error_code`, `duration_ms`.
- Keep **the same field name with the same type** across services and versions. Avoid `duration_ms` being a number in one place and `"120 ms"` in another.
- Units must be in the name or schema documentation: `duration_ms`, `bytes_sent`, `amount_minor`.
- Do not coerce IDs into numeric types: `"00017"` must preserve its leading zeros.
- For money, choose a clear rule: integer minor units paired with `currency` or an appropriate decimal contract; avoid binary floating-point numbers for monetary values.
- Do not dump an entire domain object into a giant `payload` field if you only need a few attributes.
- When data is missing, clearly define how an **absent field** differs from `null`, `""`, or a default value.
- Do not rename a field already used by dashboards without a migration plan.
- Do not use human-readable messages as aggregation keys; use `event_code`.

Example avoiding type conflicts:

```json
{"event_code":"checkout.completed","duration_ms":153,"success":true}
```

Do not emit elsewhere:

```json
{"event_code":"checkout.completed","duration_ms":"153ms","success":"yes"}
```

If two events land in the same index/collection with a fixed mapping, some stores may reject or misprocess records with mismatched types.

## 5. Event Codes: The Foundation for Turning Sentences into Groupable Data

**`event_code`** answers: "what kind of event happened?". **`error_code`** answers: "what kind of cause/error state occurred?". The two fields do not replace each other.

Example of a payment processing sequence:

```text
payment.started         INFO
payment.attempt_failed  WARN  attempt=1, error_code=GATEWAY_TIMEOUT
payment.retry_succeeded INFO  attempt=2
```

If a retry succeeds, **you should not emit `payment.failed` with the semantics of a final operation failure**.

When all recovery paths are exhausted:

```text
payment.started         INFO
payment.attempt_failed  WARN  attempt=1, error_code=GATEWAY_TIMEOUT
payment.attempt_failed  WARN  attempt=2, error_code=GATEWAY_TIMEOUT
payment.failed          ERROR attempts=2, error_code=GATEWAY_TIMEOUT
```

A good event code name should:

1. Describe stable semantics rather than a message sentence or method name.
2. Have a catalog and an owner: `payment.failed`, `order.created`, `inventory.reserved`.
3. Contain no dynamic IDs: **do not use** `payment.failed.O-17` as an event code.
4. Distinguish per-attempt events from final state when retries exist.
5. Stay stable even when `message` text is edited or translated into another language.
6. Have a rename/deprecation policy if its meaning changes.

**`trace_id` is different from `event_code`.** `trace_id` links multiple events across a single journey; `event_code` groups events of the same kind. A single trace may contain dozens of event codes.

## 6. Migration Roadmap: Do Not Change Everything at Once

For a running system, migrate in verifiable, rollback-capable steps.

### Step 1 — Inventory Log Sources and Consumers

Identify:

- Which services/packages write to console, file, JUL, Logback, or Log4j 2.
- Current text patterns and levels/filters/appenders.
- Which dashboards, alerts, queries, or scripts depend on old message wording or regexes.
- Which services have high log volume or handle sensitive data.
- Which store receives the logs and what mapping/schema requirements it has.
- Whether any event codes, trace IDs, or request IDs already exist.

Do not inventory only a few obvious lines. Tricky cases often live in exceptions, background jobs, third-party libraries, or messages with hard-to-parse dynamic values.

### Step 2 — Choose the Schema and Naming Rules

Agree on the minimum common fields for every service, plus business fields per event. For example, for `checkout`: `timestamp`, `level`, `service`, `environment`, `event_code`, `message`, `trace_id`; plus `order_id` and `error_code` when applicable.

Document which fields are required, their types, units, whether they contain sensitive data, retention, and who can read them.

### Step 3 — Choose an Appropriate Backend and Encoder

With SLF4J 2.x, the application can keep calling SLF4J; a backend like Logback will output JSON using an encoder that supports structured fields. With Log4j 2, there is an appropriate JSON/template layout. Do not install competing providers at the same time or circular two-way bridges.

Verify the **provider/runtime classpath**, not just `pom.xml`.

### Step 4 — Migrate High-Value Events First

Prioritize operationally valuable events: final payment failures, dependency errors, request outcomes, job completions, exhausted retries. Do not convert every rarely used DEBUG statement before establishing the schema for core events.

### Step 5 — Verify Before and After

For the same scenario, compare:

- Business outcome and logical event count.
- Level, event code, error code, trace ID.
- Typed attributes, such as integers and booleans.
- Throwable/cause/stack trace when present.
- Record count in the collector and queryability.
- Absence of secrets or invalid JSON output.

### Step 6 — Gradually Migrate Dashboards and Alerts

During a transition period, you can keep legacy parsers for historical lookups while building queries on the new fields. Do not turn off old parsers/queries until you confirm all critical consumers use the new fields.

### Step 7 — Retire Unnecessary Compatibility

Once coverage is sufficient and a rollback plan is in place, you can remove unnecessary text parsers or dual output. If emitting **both text and JSON records** for the same event, tag separate pipelines or exclude one from counts to avoid double-counting metrics.

## 7. Before and After: Converting Log Calls in Java

Suppose the original code is:

```java
log.error("Payment failed for order " + orderId
        + ", error=" + errorCode + ", retryable=" + retryable,
        exception);
```

This is an **illustrative snippet** with pre-declared variables. Limitations: string concatenation before the logger call; querying `retryable` requires parsing the message; field names and types are not guaranteed to be stable.

An intermediate improvement:

```java
log.error("event=payment.failed order_id={} error_code={} retryable={}",
        orderId, errorCode, retryable, exception);
```

This uses placeholders to avoid some formatting cost when the level is disabled and produces a clearly labeled message. However, the values **still remain in text** if the encoder does not split them into separate fields.

With the **SLF4J 2.x fluent API**:

```java
log.atError()
        .addKeyValue("event_code", "payment.failed")
        .addKeyValue("order_id", orderId)
        .addKeyValue("error_code", errorCode)
        .addKeyValue("retryable", retryable)
        .setCause(exception)
        .log("Không thể hoàn tất thanh toán");
```

This is a cleaner way to attach separate fields alongside a `Throwable`. The fields will be emitted as JSON when properly supported by the backend/encoder. **`setCause(exception)` differs from passing `exception.getMessage()`**: it preserves the `Throwable` object so the backend can log the exception type and stack trace according to configuration.

For frameworks still on SLF4J 1.7, the fluent `atError()` API is not available. You can use structured argument mechanisms supported by your encoder/backend or upgrade to SLF4J 2.x according to your version roadmap. Do not copy fluent calls into an older project and assume it will compile.

## 8. Standalone Java 17 Example: From Text Logs to Two JSON Events

This example **uses no external logging libraries**. It demonstrates the core idea of structured data: constructing data with **explicit field names, order, and types**, then serializing it to JSON with string escaping.

This is a **minimal JSON writer strictly for practice**. It supports `String`, `Boolean`, `Integer`, `Long`, and `null` in a flat object; it is **not** a general-purpose JSON library and **does not replace** a production logging encoder. For real systems, use a battle-tested encoder/serializer that supports all types, nested data, size limits, and security.

### 8.1. Save the File `StructuredMigrationDemo.java`

```java
import java.io.PrintStream;
import java.nio.charset.StandardCharsets;
import java.util.LinkedHashMap;
import java.util.Locale;
import java.util.Map;

public final class StructuredMigrationDemo {
    private static final PrintStream OUT =
            new PrintStream(System.out, true, StandardCharsets.UTF_8);

    private StructuredMigrationDemo() {
    }

    private static String quote(String source) {
        StringBuilder result = new StringBuilder("\"");

        for (int i = 0; i < source.length(); i++) {
            char ch = source.charAt(i);

            switch (ch) {
                case '"' -> result.append("\\\"");
                case '\\' -> result.append("\\\\");
                case '\n' -> result.append("\\n");
                case '\r' -> result.append("\\r");
                case '\t' -> result.append("\\t");
                default -> {
                    if (ch < 0x20) {
                        result.append(
                                String.format(Locale.ROOT,
                                        "\\u%04x", (int) ch));
                    } else {
                        result.append(ch);
                    }
                }
            }
        }

        return result.append('"').toString();
    }

    private static String jsonValue(Object value) {
        if (value == null) {
            return "null";
        }
        if (value instanceof String text) {
            return quote(text);
        }
        if (value instanceof Boolean
                || value instanceof Integer
                || value instanceof Long) {
            return value.toString();
        }
        throw new IllegalArgumentException(
                "Unsupported JSON value type: "
                + value.getClass().getName());
    }

    private static void writeEvent(Map<String, Object> fields) {
        StringBuilder result = new StringBuilder("{");
        boolean first = true;

        for (Map.Entry<String, Object> field : fields.entrySet()) {
            if (!first) {
                result.append(",");
            }
            first = false;

            result.append(quote(field.getKey()))
                    .append(":")
                    .append(jsonValue(field.getValue()));
        }

        OUT.println(result.append("}"));
    }

    public static void main(String[] args) {
        Map<String, Object> order = new LinkedHashMap<>();
        order.put("timestamp", "2026-01-01T00:00:00Z");
        order.put("level", "INFO");
        order.put("event_code", "order.created");
        order.put("order_id", "O-17");
        order.put("amount_minor", 120000);
        order.put("currency", "VND");
        order.put("message", "Đã tạo đơn");
        writeEvent(order);

        Map<String, Object> failure = new LinkedHashMap<>();
        failure.put("timestamp", "2026-01-01T00:00:01Z");
        failure.put("level", "ERROR");
        failure.put("event_code", "payment.failed");
        failure.put("order_id", "O-17");
        failure.put("error_code", "GATEWAY_TIMEOUT");
        failure.put("retryable", true);
        failure.put("trace_id", "tr-42");
        failure.put("message", "Gateway timeout: \"read\"");
        writeEvent(failure);
    }
}
```

**Note on timestamps:** the two timestamp values are **fixed for testing** and do not represent actual runtime. In production applications, the logging event timestamp should be recorded by the backend using an agreed clock and timezone convention.

### 8.2. Compile and Run

Requires JDK 17 or later:

```bash
javac -encoding UTF-8 StructuredMigrationDemo.java
java StructuredMigrationDemo
```

**Exact two stdout lines printed by the program:**

```json
{"timestamp":"2026-01-01T00:00:00Z","level":"INFO","event_code":"order.created","order_id":"O-17","amount_minor":120000,"currency":"VND","message":"Đã tạo đơn"}
{"timestamp":"2026-01-01T00:00:01Z","level":"ERROR","event_code":"payment.failed","order_id":"O-17","error_code":"GATEWAY_TIMEOUT","retryable":true,"trace_id":"tr-42","message":"Gateway timeout: \"read\""}
```

### 8.3. Reading the Output as Structured Data

In the first line:

- `"order_id":"O-17"` is a string, preserving the hyphen and any ID formatting.
- `"amount_minor":120000` is a **JSON number**, without quotes.
- `"currency":"VND"` is a string indicating the currency unit.
- `"event_code":"order.created"` captures the event meaning, independent of the `message` text.

In the second line:

- `"retryable":true` is a JSON boolean.
- `"trace_id":"tr-42"` enables log correlation.
- `"message":"Gateway timeout: \"read\""` properly escapes quotes inside the string value.
- This line does not include a stack trace; the example intentionally illustrates fields. When a real exception is needed, the logging backend must receive the `Throwable` and serialize it according to the schema.

**Why use `LinkedHashMap`?** It preserves field insertion order, giving predictable stdout ordering for the exercise. **Property order in a JSON object has no business meaning.** Consumers should not depend on `event_code` always appearing before `message`.

**Why is `quote` needed?** If you concatenate `"message":"` + input + `"` directly, a value containing quotes, newlines, or control characters can break JSON syntax or cause log injection. The example helper escapes strings within its supported value scope. For production data, use a standard JSON encoder to handle diverse data types, nested objects, Unicode surrogates, and safety limits.

**Why not call `System.out.println(map.toString())`?** Java's `Map.toString()` produces a format like `{key=value}`, which is **not JSON**. It does not preserve a typed JSON schema or valid escaping. Use a reliable serializer/encoder in real systems.

## 9. Migrating Logback from Text `PatternLayoutEncoder` to JSON

In many applications, the code uses **SLF4J** and the backend is **Logback Classic**. When migrating from text to structured logging, you can keep the facade and swap the appender's encoder while converting business information into fields.

### 9.1. Text Configuration Before Migration

Example `src/main/resources/logback.xml`:

```xml
<configuration>
    <appender name="CONSOLE" class="ch.qos.logback.core.ConsoleAppender">
        <encoder class="ch.qos.logback.classic.encoder.PatternLayoutEncoder">
            <pattern>%d{ISO8601} %-5level [%thread] %logger - %msg%n</pattern>
            <charset>UTF-8</charset>
        </encoder>
    </appender>
    <root level="INFO">
        <appender-ref ref="CONSOLE" />
    </root>
</configuration>
```

The text output depends on date/time, thread, and logger. Business values may only exist inside `%msg`.

### 9.2. Add the JSON Encoder Dependency

One option is **`logstash-logback-encoder`**, which works with Logback. Example of a **standalone** `pom.xml` for JDK 17, using the SLF4J API pulled in by Logback Classic:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>structured-logback-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>ch.qos.logback</groupId>
            <artifactId>logback-classic</artifactId>
            <version>1.5.16</version>
        </dependency>
        <dependency>
            <groupId>net.logstash.logback</groupId>
            <artifactId>logstash-logback-encoder</artifactId>
            <version>8.0</version>
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
            </plugin>
        </plugins>
    </build>
</project>
```

The versions here are a **fixed illustrative set of versions**, not a claim about the latest versions or an instruction to bypass framework dependency management. In practice, choose supported Logback/SLF4J/encoder versions and check security advisories, JDK requirements, and your project's transitive dependencies.

### 9.3. Switch `logback.xml` to the JSON Encoder

```xml
<configuration>
    <appender name="JSON_STDOUT"
              class="ch.qos.logback.core.ConsoleAppender">
        <target>System.out</target>
        <encoder class="net.logstash.logback.encoder.LogstashEncoder">
            <customFields>{"service":"checkout","environment":"demo"}</customFields>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="JSON_STDOUT" />
    </root>
</configuration>
```

Explanation:

- `ConsoleAppender` still writes to stdout: suitable for container-based logging architectures.
- `LogstashEncoder` converts Logback events to JSON according to the encoder's providers/rules.
- `customFields` adds common service/environment fields in the example. In real deployments, the environment typically comes from controlled external configuration; do not hardcode `demo` in a production image.
- `Root level="INFO"` continues to control which logs are recorded.
- Only one JSON appender is attached to root in this example; do not keep an extra text `ConsoleAppender` on the same output without a plan to avoid duplication.

**Do not put `LogstashEncoder` in `logback.xml` if the dependency is missing from the runtime classpath.** The backend may report appender/encoder initialization errors. Verify the full dependency graph and the actual loaded configuration.

### 9.4. Java SLF4J 2.x: Attaching Fields and `Throwable` Explicitly

Create `src/main/java/demo/StructuredLogbackDemo.java`:

```java
package demo;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;

public final class StructuredLogbackDemo {
    private static final Logger LOG =
            LoggerFactory.getLogger(StructuredLogbackDemo.class);

    private StructuredLogbackDemo() {
    }

    public static void main(String[] args) {
        MDC.put("trace_id", "tr-42");
        try {
            LOG.atInfo()
                    .addKeyValue("event_code", "order.created")
                    .addKeyValue("order_id", "O-17")
                    .addKeyValue("amount_minor", 120000)
                    .addKeyValue("currency", "VND")
                    .log("Đã tạo đơn hàng");

            try {
                throw new IllegalStateException("gateway unavailable");
            } catch (IllegalStateException failure) {
                LOG.atError()
                        .addKeyValue("event_code", "payment.failed")
                        .addKeyValue("order_id", "O-17")
                        .addKeyValue("error_code", "GATEWAY_TIMEOUT")
                        .addKeyValue("retryable", true)
                        .setCause(failure)
                        .log("Không thể hoàn tất thanh toán");
            }
        } finally {
            MDC.remove("trace_id");
        }
    }
}
```

Run from the project directory:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.StructuredLogbackDemo
```

This requires JDK 17, Maven, and the XML dependencies above. When the backend actually uses `LogstashEncoder` and the configuration is loaded, stdout consists of JSON objects containing properties such as `message`, `level`, `logger_name`, `trace_id`, `event_code`, `order_id`, and on error, exception/stack trace data according to the encoder's design.

**There is no fixed byte-for-byte stdout for this Logback example.** Timestamp, thread, logger name, and exception formatting can depend on version/configuration; moreover, the encoder's default field structure may include other attributes. To test, **parse the JSON and assert individual fields** rather than comparing the entire line against a fixed string. The plain Java example in Section 8 provided exact stdout for learning how structured data works.

### 9.5. What Should MDC Be Used For?

`MDC` is well suited for context shared across a processing scope: `trace_id`, `request_id`, or `tenant_id` if governed by appropriate security policies. These values can be added by the encoder to every event in that scope.

Usage:

```java
MDC.put("request_id", requestId);
try {
    processRequest();
} finally {
    MDC.remove("request_id");
}
```

This is an **illustrative snippet**, assuming `requestId` and `processRequest()` already exist. With thread pools, `CompletableFuture`, or reactive frameworks, MDC does not automatically propagate across all threads: proper context propagation mechanisms and testing are required.

**Do not put all business data into MDC.** An `order_id` for a specific event can be added directly to that event via key-value pairs. Putting constantly changing data into thread-wide MDC risks leaking values between tasks and polluting unrelated events.

## 10. Log4j 2: Migrating from `PatternLayout` to Structured JSON

If the code uses the **Log4j 2 API** or SLF4J properly bridged to Log4j 2 Core, a common approach is to replace text `PatternLayout` with a JSON layout capable of representing logging event fields.

Example initial text configuration:

```xml
<Configuration>
    <Appenders>
        <Console name="TEXT" target="SYSTEM_OUT">
            <PatternLayout
                pattern="%d{ISO8601} %-5level %c - %m%n" />
        </Console>
    </Appenders>
    <Loggers>
        <Root level="info">
            <AppenderRef ref="TEXT" />
        </Root>
    </Loggers>
</Configuration>
```

When migrating to JSON, you can use **`JsonTemplateLayout`** in a compatible `log4j-layout-template-json` module or a JSON layout supported by your Log4j 2 version, along with the required dependency.

Example **illustrative XML snippet** showing where a JSON template layout goes:

```xml
<Console name="JSON" target="SYSTEM_OUT">
    <JsonTemplateLayout
        eventTemplateUri="classpath:EcsLayout.json"
        stackTraceEnabled="true" />
</Console>
```

**Condition:** the application must have the matching dependency/module and template for its version. This configuration is **not a standalone example**; it requires the surrounding `<Configuration>`, `<Appenders>`, `<Loggers>`, appender reference, and compatible Log4j 2 dependencies. Field names, template paths, and how message/Throwable/ThreadContext are mapped depend on the template, so do not assume it produces the exact same JSON as `LogstashEncoder`.

For Log4j 2 API code, business fields can be passed via `StringMapMessage` or supported message/key-value mechanisms:

```java
import org.apache.logging.log4j.LogManager;
import org.apache.logging.log4j.Logger;
import org.apache.logging.log4j.message.StringMapMessage;

Logger log = LogManager.getLogger("demo.payment");
StringMapMessage event = new StringMapMessage()
        .with("event_code", "payment.failed")
        .with("order_id", "O-17")
        .with("error_code", "GATEWAY_TIMEOUT");
log.error(event);
```

This is **illustrative code within a method scope**, not a standalone Java class; to emit the pairs as JSON fields, you need a layout/template that handles `MapMessage`. If the layout only prints `%m`, the data may be collapsed into a string instead of JSON fields. When attaching a `Throwable`, use the API call/contract that accepts `Throwable` and verify the output.

**Do not replace Logback with Log4j 2 solely to get structured logging** if your existing backend already supports JSON adequately. Switching backends risks provider conflicts, bridge issues, config changes, and behavioral differences. In most cases, you can upgrade the encoder and schema on your current backend.

## 11. When Java Code Cannot Be Changed Yet: Parsing Text Logs at the Collector

In a legacy system, updating thousands of log statements may not happen immediately. A transitional step is **parsing text at ingestion**.

Example legacy text with a fixed format:

```text
INFO order=O-17 amount=120000 currency=VND
```

An illustrative regex:

```regex
^(?<level>INFO|WARN|ERROR) order=(?<order_id>\S+) amount=(?<amount_minor>\d+) currency=(?<currency>[A-Z]{3})$
```

When the parser supports named groups, it can extract `level`, `order_id`, `amount_minor`, and `currency`. Keep in mind:

- The regex-captured `amount_minor` starts as a **string**; the pipeline must convert it to a number.
- If the message changes order or adds extra whitespace, the regex may stop matching.
- If a value contains spaces, `=`, or newlines, a simple parser easily breaks.
- A regex recognizes only **one log shape**; multiline exceptions and library messages have different structures.
- A parser cannot reliably infer `event_code` if logs lack a stable assignment rule.
- Queries/dashboards still depend on the destination's mapping.

**Legacy parsing is a transitional solution**, not a complete replacement for emitting structured fields at the source. You should measure **successful parse rate, missing field rate, and type error rate**, and retain the raw log according to access/retention policies when investigation is needed.

### Risk of Losing History During Cutover

Old logs stored only as text will not retroactively gain new fields after deploying a new Java version. You may need to:

1. Keep old queries running alongside new ones for historical data.
2. Backfill/reindex old data if genuinely required and cost permits.
3. Build dashboards with a cutover date marker.
4. Agree on when old parsers can be retired.

Never assume the new schema applies retroactively to all historical records.

## 12. Maintaining Compatibility, Avoiding Duplication, and Rollback Planning

A rollout strategy might include:

```text
Phase A: Current text + inventory of consumers/fields to preserve
Phase B: Stable schema + testing in development environment
Phase C: JSON canary on one service/instance
Phase D: Migrate dashboards/alerts to new fields
Phase E: Expand JSON + monitor ingest, parse errors, cost
Phase F: Remove unnecessary text/parsers after verification
```

During the canary phase, have a **way to distinguish formats** at the collector, such as by deployment version or separate pipeline/source. Common risks:

- Both text and JSON are sent to the same index, causing mapping conflicts and doubling event counts on dashboards.
- A service configures both text and JSON appenders writing to stdout, causing the collector to count each transaction twice.
- Old regex alerts keep firing while new fields are active, causing duplicate alerts.
- Data from multiple versions uses different field names; the same query returns inconsistent results.
- The new JSON encoder prints very long stack traces or sensitive fields that text previously omitted.
- The collector fails to parse JSON due to line framing or multiline issues.
- On rollback, the service reverts to text while new queries lose data.

To stay safe, pick **one canonical event** for KPI counting, clearly define the trusted source, and use a flag/schema version for breaking changes.

### Should You Keep the Same `message` Field?

Usually yes, keep `message` so operators can read it quickly. Structured logging **does not eliminate human-readable descriptions**; it moves key data out into dedicated fields. What changes is that dashboards no longer parse IDs out of `message`.

If temporary compatibility is needed, `message` can retain some old keywords, but do not turn prose into a long-term source of truth. `event_code`, `error_code`, and typed fields should be the stable query interface.

## 13. Data Types and Mapping in the Log Store

Even after JSON is emitted properly from the application, the collector and destination store can still alter or lose data types.

A test suite should verify:

```json
{
  "event_code": "payment.failed",
  "attempt": 3,
  "retryable": false,
  "duration_ms": 1250,
  "trace_id": "tr-42",
  "error_code": "GATEWAY_TIMEOUT"
}
```

After ingestion:

- Is `attempt` still an integer, or was it converted to a string?
- Is `duration_ms` a number, with sufficient range and consistent units?
- Is `retryable` still a boolean, or did a parser turn it into `"false"`?
- Is `trace_id` preserved intact, without being treated as a number or truncated?
- Can `event_code` be filtered accurately and grouped reliably?
- Are absent fields and `null` handled consistently?
- Are values containing Unicode, quotes, and newlines preserved?

In systems like Elasticsearch, OpenSearch, or tools with strict mappings/schemas, **two different types for the same field** can cause ingest failures or query errors. In other tools, types may be more flexible, but conventions are still needed so dashboards remain accurate.

### Be Careful with Monetary and Time Measurements

Do not log:

```json
{"amount":"1.200.000 VND","duration":"2 seconds"}
```

if the goal is numeric aggregation. Instead:

```json
{"amount_minor":1200000,"currency":"VND","duration_ms":2000}
```

**Monetary values in the example are mock data.** What matters is that the same measurement uses the same unit and type. For different currencies, never sum `amount_minor` across multiple currencies as if they were the same unit.

### Event Schema Version

When an incompatible change is needed, you can add a field like `schema_version` or separate into a new namespace/event. There is no need to bump the version for every wording edit to `message`. Bump it when **a field's meaning or type** changes in a way that breaks old consumers.

Adding an optional field can be compatible, whereas changing `duration_ms` from a number to a string is a breaking contract change. Verify how both the destination store and consumer applications handle it.

## 14. Correlation IDs, MDC, and Distributed Context

Structured logging shines when logs from multiple services can be linked by ID.

Example:

```text
gateway:  trace_id=tr-42 event=request.received
checkout: trace_id=tr-42 event=order.created
payment:  trace_id=tr-42 event=payment.failed
gateway:  trace_id=tr-42 event=request.failed
```

`trace_id` values can be placed into MDC/ThreadContext at request boundaries and emitted by the encoder on every record. However:

1. MDC is typically bound to a **thread/context** and does not automatically propagate across every `ExecutorService` or `CompletableFuture`.
2. A pooled thread serves multiple requests, so **cleanup is mandatory** per lifecycle.
3. Do not generate a new trace ID in every method: that breaks log correlation.
4. Do not use `trace_id`/`order_id` as logger names, creating millions of dynamic loggers.
5. Do not assume every `trace_id` is safe to expose publicly; log access still needs control.

If your system uses platform-standard tracing, obtain the ID from the real tracing context; **do not invent a custom format and treat it as a standard distributed trace**. When changing backends or instrumentation mechanisms, test propagation and mapping to log fields.

### Request ID, Trace ID, Span ID

- `request_id`: ID of a single request within your system.
- `trace_id`: ID for the entire distributed trace, potentially spanning multiple services.
- `span_id`: a unit of work within a trace, when the tracing framework has the concept of spans.
- `event_code`: event type, not a processing session ID.

An event can carry multiple IDs, each with its own role. Only log IDs that are actually generated/recognized by contract; do not mix them up just because they look like strings.

## 15. `Throwable`, Stack Traces, and Business Errors

Text logs typically record exceptions like this:

```text
ERROR Payment failed: java.lang.IllegalStateException: gateway unavailable
    at ...
    at ...
```

With JSON, you can choose fields such as `exception_type`, `error_code`, `stack_trace`, and `message`, but receiving the stack trace depends on **the backend/encoder and passing the `Throwable`**.

The intended call when preserving the cause:

```java
log.atError()
        .addKeyValue("event_code", "payment.failed")
        .addKeyValue("order_id", orderId)
        .addKeyValue("error_code", errorCode)
        .setCause(exception)
        .log("Không thể hoàn tất thanh toán");
```

Not equivalent to:

```java
log.error("payment failed: {}", exception.getMessage());
```

In the second call, the backend only receives a formatted string message; **the original `Throwable` object is not preserved**. If the cause chain matters, pass the `Throwable` using the appropriate API.

### Do Not Emit Two Final Failure Events from One Exception

In many Java architectures, a repository throws an exception, a service wraps the cause, and a controller returns an error. If all three layers log `payment.failed` and rethrow, one transaction can be counted three times. Structured logging **does not automatically deduplicate logical events**.

Choose a final logging boundary or use distinct event codes if each layer genuinely has different semantics. When building KPIs, define counted events clearly and preferably use business/completed-task metrics from a reliable source.

### What About Multiline Stack Traces?

Text stack traces can cause collectors to split one exception into multiple records. A proper JSON encoder typically escapes newlines inside strings or represents exceptions in a supported structure, though **not all JSON encoders produce the same schema**. Test logging real exceptions, parse each record, and compare the required error type/cause.

Do not truncate stack traces too aggressively just to keep a short line: retain enough diagnostic detail within permitted channels, with clear size limits and data policies.

## 16. Security: Switching to JSON Does Not Mean Safer

Structured logging makes data **easier to query**, which also makes sensitive data easier to find if logged improperly.

Common leak sources:

- HTTP `Authorization` headers, cookies, API keys.
- Request/response bodies containing personal information.
- `Throwable.getMessage()` containing URLs with tokens or SQL with parameters.
- `toString()` of a domain object containing private data.
- MDC retaining user IDs/tenant IDs beyond the needed scope.
- Default JSON encoders emitting extra unauthorized fields.
- Collectors recording the raw log after the application tried to mask another field.

Principles:

1. **Data minimization:** only log fields needed for investigation; do not dump entire objects.
2. **Field allowlist:** define allowed fields for each event type.
3. **Mask or strip at the source:** prevent secrets from entering events or `Throwable`s whenever possible.
4. **Check every destination:** stdout, file, collector, central store; two appenders may apply different policies.
5. **Restrict read access and retention:** changing formats does not change compliance or retention rules.
6. **Test for injection:** values with quotes, newlines, tabs, or control characters must be properly escaped by the JSON encoder.
7. **Never use real secrets in tests:** use a dummy string like `SECRET_TEST_TOKEN_123` and assert it **does not appear** in output.

Parameter substitution `{}` or fluent `addKeyValue` **does not mask values automatically**. Preventing secret leaks must be decided at the source, not just by tweaking patterns.

## 17. Performance, Volume, and Cardinality

Structured logging can increase bytes per event due to repeated field names, timestamps, service names, and context. That is **not necessarily bad**: in return, querying and operations become more accurate. Still, measure before rolling out broadly.

Cost sources:

- Encoder JSON serialization, string escaping, exception formatting.
- Adding global fields to every event.
- Large stack traces or deeply nested objects.
- Collectors parsing and storing more fields.
- Log stores indexing too many dynamic fields.
- Extra records from retries or dual text+JSON output.
- High-frequency DEBUG/TRACE logging.

### Distinguish Dynamic-Value Fields from Metric Labels

`trace_id` or `order_id` typically have **high cardinality** because they take countless distinct values. They are useful for **searching a single request**, but should not be used as unbounded aggregated metric labels.

Fields from a stable catalog such as `event_code`, `service`, `environment`, `result`, or `error_code` are generally better suited for dashboard/metric grouping. However, if `error_code` is generated randomly or has an ID appended to it, it too can become high cardinality.

### Structured Logging Does Not Turn Logs into Guaranteed Delivery

A valid JSON event can still be lost when:

- The appender queue fills up or the backend drops events.
- A container restarts before flushing.
- The collector fails or loses connectivity.
- Log rotation deletes old data before it is read.
- The collector drops records via filters or mapping rejections.
- The indexing system slows down or fails.

Audit or business events requiring strict accuracy need dedicated storage/delivery and reconciliation mechanisms; do not rely solely on `log.info`.

## 18. Testing the Migration: From Schema to Collector

A solid test suite has at least four layers.

### 18.1. Testing Semantics at the Source

In unit tests, verify:

- Events have the right `event_code` for each scenario.
- Levels are right (transient retry vs. final failure).
- `order_id`, `error_code`, `attempt`, and `retryable` have accurate meanings.
- A `Throwable` is attached for exceptions requiring investigation.
- A final failure is not accidentally logged multiple times.
- No error event is emitted when an operation recovers.

Assertions like these can use a `ListAppender`/handler or custom abstraction, though they **do not yet prove JSON is encoded properly**.

### 18.2. Testing JSON Output

Emit events through the real encoder, then read bytes from a test appender or console subprocess. **Parse the JSON with a reliable JSON library** instead of searching for raw substrings like:

```text
"retryable":true
```

because whitespace and field order can vary. Check types and values after parsing:

| Field | Meaningful Assertion |
| --- | --- |
| `event_code` | Equals `payment.failed` |
| `retryable` | Boolean `false`/`true` per scenario |
| `attempt` | Integer number with the expected value |
| `order_id` | String preserving ID formatting |
| `trace_id` | Present when context is set |
| `error_code` | Belongs to the valid catalog |
| `stack_trace` | Present when an exception needs diagnosis, per schema |
| `message` | Readable string containing no secrets |

To guarantee JSON Lines, each line must be a parseable JSON object, and newlines inside `message` must be escaped rather than creating "fake log lines".

### 18.3. Testing the Collector and Mapping

In staging or an integration environment, emit a set of events with known `trace_id`/`event_code`/schema version. Then verify:

1. The collector ingests stdout/file correctly.
2. Data parses as JSON without being mixed with build-tool text.
3. Fields have the expected types in the log store.
4. Timestamps are searchable within the right time window.
5. No mapping conflicts or rejected records occur.
6. Filtering and grouping by the new fields work.
7. Error scenarios include the required cause/stack trace.
8. No mock or sensitive data that should be masked is exposed.
9. Destination event count matches emitted count per drop/retry policy.
10. Old and new queries/dashboards are reconciled during the canary phase.

### 18.4. Testing Rollout and Rollback

Run a controlled canary to measure:

- Valid JSON log rate.
- Rate of records missing required fields.
- Number of mapping conflicts/parse failures.
- Log volume by service/level.
- Ingest latency and dropped record count.
- Whether dashboards/alerts continue working accurately.
- Whether rollback restores text logs and corresponding queries.

Do not use "the console prints curly braces" as your sole criterion. A string that looks like JSON can have broken escaping, wrong field types, or never reach the search store.

## 19. Common Pitfalls and How to Fix Them

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| `log.info("order={}", id)` but collector lacks `order_id` | Only formatted message; no structured fields sent | Use key-value/event data and a supporting encoder. |
| JSON output only has `message` | Layout does not emit custom key-values or MDC | Check provider/encoder/schema configuration. |
| Both text and JSON appear on stdout | Two appenders or two routing paths | Plan dual-write carefully; avoid double-counting events. |
| Old dashboard loses data | Regex query relies on legacy text | Migrate queries to fields and keep a compatibility window. |
| A field is sometimes a number, sometimes a string | Unfixed schema | Standardize types/units and verify store mappings. |
| Exception missing in JSON | `Throwable` not passed or encoder omits it | Use `setCause`/appropriate overload and test `Throwable`s. |
| Trace ID missing in async tasks | MDC does not propagate automatically | Use framework-appropriate context propagation. |
| Trace IDs mixed up across requests | Forgot MDC cleanup / thread reuse | Use `finally` and verify lifecycle. |
| Truncated JSON or broken multiline logs | Hand-concatenated text, oversized records, partial collector reads | Use a standard encoder, bound event sizes, test framing. |
| Container logs grow too fast | Too many fields/stack traces or duplicate logging | Measure volume, levels, retries, rotation, and retention. |
| Cannot parse Unicode/newlines | Wrong charset or escaping | Use UTF-8 and a reliable JSON serializer. |
| JSON emitted but collector misses it | Wrong output stream, parser/index/filter issue | Inspect the full ingestion pipeline. |
| `LogstashEncoder` fails to initialize | Missing dependency or incompatible version | Check runtime classpath and status logs. |
| SLF4J reports multiple providers | Multiple backends on classpath | Select exactly one final provider. |
| JSON contains secrets | Token/payload/exception passed into event | Allowlist, mask at source, test with dummy secrets. |
| Multiple `payment.failed` events for one request | Retries/layers all log the same semantics | Set event boundaries and distinguish attempts from final failure. |
| Cannot query history with new fields | Old logs not backfilled/reindexed | Keep legacy queries or plan data migration. |

## 20. Practice Exercises

### Exercise 1 — Schema Design

Legacy log:

```text
Order O-17 completed in 153 ms, total=120000 VND
```

Propose typed fields.

**Suggested Answer:**

```json
{
  "event_code": "order.completed",
  "order_id": "O-17",
  "duration_ms": 153,
  "amount_minor": 120000,
  "currency": "VND",
  "message": "Hoàn tất đơn hàng"
}
```

Confirm the meaning of `amount_minor` against the actual currency system; do not coerce a monetary string to a number without knowing its unit.

### Exercise 2 — SLF4J 2.x Syntax

Inside a method that already has `log`, `orderId`, and `durationMs`, log a success event with three fields: `event_code`, `order_id`, `duration_ms`.

**Hint:**

```java
log.atInfo()
        .addKeyValue("event_code", "order.completed")
        .addKeyValue("order_id", orderId)
        .addKeyValue("duration_ms", durationMs)
        .log("Hoàn tất đơn hàng");
```

Then verify the encoder actually emits all three fields, with `duration_ms` as a number.

### Exercise 3 — Distinguishing Retries from Final Failures

A payment times out on attempt 1, then succeeds on attempt 2. Should you log `payment.failed` at `ERROR` on attempt 1?

**Hint:** If `payment.failed` is defined as a **final transaction failure**, no. You can log `payment.attempt_failed` with `attempt` and `error_code`; the final event is the success outcome. Avoid dashboards counting transient timeouts as failed payments.

### Exercise 4 — Parsing Legacy Text

A regex parser reads `amount=120000` as the string `"120000"`. After switching to JSON, a dashboard wants to sum `amount`. What should be done?

**Hint:** Convert the field to a numeric type, confirm the unit, keep the same mapping across all services, and handle malformed/missing data. Do not sum strings or different currencies directly.

### Exercise 5 — Handling Sensitive Data

An event has `Authorization: Bearer SECRET_TEST_TOKEN_123` inside an exception message. Is it safe enough if the JSON encoder escapes quotes and newlines?

**Hint:** No. JSON escaping only ensures valid syntax; **it does not mask secrets**. Prevent or mask secrets in messages, `Throwable`s, and attached fields; test all output channels.

### Exercise 6 — Dual Logging

A service sends the same event to both a text `ConsoleAppender` and a JSON appender, and both land in the same index. The dashboard's `order.created` count doubles. Can this be fixed by renaming a field?

**Hint:** The issue is **duplicating the event stream**, not just field names. Choose a canonical source, separate pipelines/channels, exclude the unused copy from counts, and plan to retire dual-write.

### Exercise 7 — Tracing in a Thread Pool

A request has `trace_id=tr-42` on thread A, but a task running on an executor lacks the trace ID. Why, and how do you fix it?

**Hint:** Execution-context MDC does not automatically propagate across all threads. Use the context propagation mechanism provided by your framework/tracing library, and clean up when threads are reused. Verify logs from both threads.

### Exercise 8 — End-to-End Migration Testing

Write a pre-rollout checklist for a `payment.failed` event.

**Hint:** Verify event code and level, order ID, error code, attempt count, final state, `Throwable`, schema/types, JSON escaping, data access permissions, collector ingestion, `trace_id` queries working, no mapping conflicts, no duplicates, new alerts/dashboards accurate, and rollback still able to query logs.

## 21. Project Implementation Checklist

- [ ] Know the real backend and runtime provider; no conflicting bridges/providers.
- [ ] Maintain an `event_code` catalog with accountable owners.
- [ ] Have a common schema + per-event schemas with stable names, types, and units.
- [ ] No longer rely on message text to count and group key events.
- [ ] Business data is sent via fields, not only `{}` placeholders.
- [ ] JSON encoder/layout actually emits required key-values and MDC.
- [ ] Timestamps include timezone with proper types; durations and amounts include units.
- [ ] Trace/request IDs are propagated and cleaned up properly across async/thread pools.
- [ ] Exceptions/stack traces retain enough diagnostic detail without exposing secrets.
- [ ] Unicode messages, quotes, backslashes, and newlines are validly escaped.
- [ ] A single final failure is not unintentionally emitted multiple times.
- [ ] Full requests, tokens, and PII are not logged into events.
- [ ] Collector parses JSON cleanly with no mapping conflicts.
- [ ] New dashboards/alerts are field-based; legacy text history has a compatibility plan.
- [ ] Canary measures ingest/drop/volume/cost and has a rollback procedure.
- [ ] Retention, read permissions, and potential log loss are reviewed separately.
- [ ] Logs are not used as the sole source of truth for audit data requiring exactly-once guarantees.

**Conclusion:** Migrating text logs to structured logging is a shift from **"prose for reading"** to **"schema-backed events understood by both machines and humans"**. Start with stable fields and semantics, emit typed values directly from Java code, use a real JSON encoder, verify `Throwable`/MDC and collector behavior, and gradually transition legacy consumers via a rollback-capable canary. Done right, your system troubleshoots faster and more accurately while still keeping messages readable for humans.