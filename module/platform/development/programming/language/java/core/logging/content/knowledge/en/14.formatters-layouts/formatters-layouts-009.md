# Key-Value Formatting in Java Logging: Design, Encoding, and Testing

## 1. What Is Key-Value Formatting?

**Key-value logging** is a way of representing a log event as **field name = field value** pairs, typically written in `key=value` form. Instead of logging only a free-form sentence such as “Payment provider timed out”, an event can be represented as:

```text
timestamp="2026-11-09T10:15:30Z" level="WARN" service="payment-service" event="GATEWAY_TIMEOUT" orderId="O-17" elapsedMs=3000 action="SELECT_FALLBACK"
```

Each pair carries a specific meaning:

- `timestamp`: the time when the event occurred.
- `level`: severity level, e.g. INFO/WARN/ERROR; in JUL, INFO/WARNING/SEVERE are used.
- `service`: the system or component emitting the event.
- `event`: a stable event code, easy to aggregate.
- `orderId`: an order identifier permitted for logging.
- `elapsedMs`: execution duration in milliseconds.
- `action`: the action the application actually chose.

This format has three goals:

1. **Readability:** engineers can immediately see what data accompanies the event without parsing the grammar of a long sentence.
2. **Easy filtering/aggregation:** collectors can extract fields using a consistent convention instead of guessing from word positions.
3. **Reduced ambiguity:** the field name clearly indicates that “3000” is `elapsedMs`, not a retry count or an error code.

**Important condition:** `key=value` is only a representation; it **does not automatically become proper structured logging**. For reliable machine parsing, both the log producer and consumer must agree on rules for **key names, pair delimiters, quoting, escaping, data types, missing values, and schema version**. Without that contract, a message containing spaces, equals signs, or newlines can break the parser.

This lesson belongs to the **Formatters and Layouts** topic: we focus on *how to format a LogEvent/LogRecord into key-value*. Setting log levels, writing to files, or collecting logs are related components, but they do not replace the value-encoding problem covered here.

## 2. How Does a Log Event Flow Through a Formatter/Layout?

```text
Java code
    |
    | logger.info(...), logger.warn(...)
    v
Logger + level/filter
    |
    v
LogRecord / LogEvent
  - timestamp
  - level
  - logger name
  - message
  - exception
  - attributes / MDC / context
    |
    v
Formatter (JUL) or Layout/Encoder (Log4j 2, Logback)
    |
    | into a single key=value, text, or JSON line
    v
Handler / Appender
    |
    v
stdout / file / network / collector / storage
```

Different Java logging systems use their own terminology:

| System | Event | Formatting component | Output destination component |
| --- | --- | --- | --- |
| **java.util.logging (JUL)** | `LogRecord` | `java.util.logging.Formatter` | `Handler` |
| **Log4j 2** | `LogEvent` | `Layout`, e.g. `PatternLayout` or `JsonTemplateLayout` | `Appender` |
| **Logback** | `ILoggingEvent` | `Layout` or `Encoder` | `Appender` |

In JUL, the `Formatter` class has the `String format(LogRecord)` method; `formatMessage(LogRecord)` is a utility for formatting/localizing the message and **does not automatically produce key-value pairs with a custom schema**. To format additional fields in JUL, you must define your own way of carrying and encoding the data.

In Log4j 2, `PatternLayout` can print literals like `level=`, `logger=`, and conversions such as `%p`, `%c`, `%X{traceId}`. However, concatenating literals and variables **is not enough to be parser-safe** when values contain spaces or control characters.

For real data analysis pipelines, the Log4j 2 documentation recommends **JSON Template Layout** over using `PatternLayout` as a structured encoder. Text-based key-value remains useful for human-readable log lines when quoting/escaping rules are in place or when compatibility with collectors supporting logfmt-like formats is needed.

## 3. Designing a Clear `key=value` Convention

There is no single grammar that applies to every system calling itself “key-value”. Before writing code, write down a **formatting contract**. A recommended example for an internal system:

1. **One log event = one line of text.** End with the record’s newline character; do not let newlines in input create fake records.
2. **Pairs are separated by a single ASCII space**; do not use commas as separators unless all parsers support it.
3. **Keys:** accept only `[A-Za-z][A-Za-z0-9_]*`; keys are stable, chosen by developers, and never taken directly from user input.
4. **The `=` sign** separates the field name and its value.
5. **Strings are always double-quoted:** `orderId="O-17"`, `message="Order accepted"`.
6. **Booleans and finite numbers may be unquoted:** `success=true`, `elapsedMs=3000`.
7. **Null is written as unquoted `null`:** distinct from the literal string “null”, which is written `"null"`.
8. **Escaping inside strings:** double quote as `\"`, backslash as `\\`, newline as `\n`, carriage return as `\r`, tab as `\t`, and other control characters as `\uXXXX`.
9. **Stable field ordering** for easy visual comparison and testing; however, parsers should not rely on column positions.
10. **No arbitrary fields from objects/HTTP requests:** use an allowlist and enforce size limits.

Example following this convention:

```text
timestamp="2026-11-09T10:15:30Z" level="INFO" service="order-service" event="ORDER_ACCEPTED" attempts=1 orderId="O-17" success=true
```

Here, a reader can distinguish the string `"1"` from the number `1`, and the string `"false"` from the boolean `false`. However, when ingested by a text parser, **whether data types are preserved or converted depends on the grammar/collector**; not every logfmt parser creates types matching Java’s.

**Do not call this custom convention “the one standard logfmt”.** Logfmt and similar formats have variants for quoting and escaping. If you use a specific parser library, test directly against that parser’s grammar.

### Distinguishing key, value, event code, and message

A free-form message can change across releases:

```text
message="Payment was delayed"
message="Timeout while contacting provider"
```

Therefore, you should also include a **stable event code**:

```text
event="PAYMENT_TIMEOUT" message="Payment provider did not respond"
```

Do not use the message itself as the sole key for computing long-term error rates. A stable event code is convenient for dashboards and alerts, while the message adds context for humans.

## 4. Dangerous Cases with Separators and Escaping

### 4.1. Spaces in values

Unquoted form:

```text
service=order-service message=Order accepted
```

A parser that splits only on spaces may treat `accepted` as a token without a key. Quoting strings solves this:

```text
service="order-service" message="Order accepted"
```

### 4.2. Equals signs in values

Data:

```text
query="status=PAID" detail="a=b c=d"
```

Do not split each token on **all** equals signs and treat every piece as a new pair. The parser must use only the **first `=` outside quotes** as the key/value boundary. Equals signs inside a string are data.

### 4.3. Double quotes and backslashes

Strings containing quotes and file paths must be escaped according to the convention:

```text
message="Invalid field \"amount\"" path="C:\\logs\\orders"
```

Here `\"` represents a quote *inside the value*, not the end of the value; `\\` represents a single backslash. If the parser does not support these escapes, switch to a compatible encoder/parser or use JSON.

### 4.4. Newlines and log injection

Suppose the original message has two lines:

```text
Order accepted
level=ERROR message="Fake incident"
```

If appended directly to text output, a reader might mistake the second line for an independent event. The encoder must convert actual newline characters into **the two visible characters** `\n`:

```text
message="Order accepted\nlevel=ERROR message=\"Fake incident\""
```

This remains **a single event line**. The same principle applies to carriage returns, tabs, and other control characters. For ingestion systems requiring one event per line, test `\r`, `\n`, `\t`, NUL, and Unicode strings.

### 4.5. Missing, null, and empty string

Three distinct states:

```text
# Missing userId key: unknown or not collected.
event="ORDER_CREATED"

# Present key with null value.
event="ORDER_CREATED" userId=null

# Present key with empty string.
event="ORDER_CREATED" userId=""
```

They **should not be arbitrarily conflated** in the pipeline if business logic needs to distinguish them. Depending on privacy policies, many personally identifiable fields should be **omitted completely** rather than logged as null.

## 5. Useful Key-Value Fields in a Java Service

A sample schema:

| Field | Example value | Rationale |
| --- | --- | --- |
| `timestamp` | `"2026-11-09T10:15:30Z"` | Timestamp; prefer UTC or explicit offset. |
| `level` | `"WARN"` | Severity; level names depend on the API. |
| `service` | `"payment-service"` | Distinguishes the service/instance. |
| `environment` | `"production"` | Distinguishes the environment. |
| `logger` | `"com.example.payment.Client"` | Location of the component emitting the event. |
| `event` | `"PAYMENT_TIMEOUT"` | Stable code for searching/alerting. |
| `correlationId` | `"req-1001"` | Tracks processing across the same request. |
| `traceId` | `"4bf92f..."` | Links distributed tracing if available. |
| `orderId` | `"O-17"` | Business ID allowed for logging, instead of the whole entity. |
| `elapsedMs` | `3000` | Explicit time unit. |
| `attempt` | `2` | Attempt count, numeric type. |
| `success` | `false` | Outcome as a boolean. |
| `action` | `"SELECT_FALLBACK"` | Action chosen by the system. |
| `message` | `"Provider timed out"` | Human-readable description. |
| `errorType` | `"java.net.SocketTimeoutException"` | Exception class when investigation is needed. |

**Do not put every attribute into one event.** Select fields that genuinely aid investigation and enforce size limits. `traceId` and `correlationId` are often very useful, but do not turn every unique ID into an ultra-high-cardinality metric label.

### Field naming and normalization

- Pick one naming convention, such as `camelCase` or `snake_case`, and use it consistently across the system.
- Do not replace `elapsedMs` with `duration` without specifying the unit; the number `100` does not tell you whether it is seconds or milliseconds.
- Avoid arbitrary dynamic keys like `featureFlag.<dynamicName>` unless the parser and index are designed for them.
- For major schema changes, add `schemaVersion` so collectors/consumers know how to interpret events.
- Keep `level`, `event`, and `timestamp` as fields with stable semantics.
- When searching by ID is sufficient, do not log raw emails, phone numbers, or other personal data.

## 6. Standalone Java 17 Example: Custom JUL Formatter Producing `key=value`

JDK 17 includes **java.util.logging (JUL)**. This example requires no Maven or third-party libraries; it models a **`LogRecord` carrying an event code and an attribute map**, and a custom `Formatter` formats the record into **a single `key=value` line**. This is a formatting lesson, not a full logging framework.

Formatter rules:

- `timestamp`, `level`, and `event` always precede other fields.
- Dynamic fields are sorted by key using `TreeMap` for deterministic output.
- Strings are **always quoted** with special characters escaped.
- Booleans and finite `Number` values are emitted unquoted.
- Null emits `null`; the literal string “null” emits `"null"`.
- Keys are restricted to a pattern; arbitrary separators or collisions with reserved system fields are rejected.
- `LogRecord.getParameters()` is used as a **demo-only convention** to carry the map, not an official JUL structured logging standard.

### 6.1. File `KvLoggingDemo.java`

```java
import java.time.Instant;
import java.util.Map;
import java.util.TreeMap;
import java.util.Locale;
import java.util.logging.Formatter;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;
import java.util.logging.StreamHandler;

public final class KvLoggingDemo {

    private KvLoggingDemo() {
    }

    public static void main(String[] args) {
        Logger logger = Logger.getLogger("demo.keyvalue");
        logger.setUseParentHandlers(false);

        // Do not use existing handlers on the demo logger.
        for (Handler h : logger.getHandlers()) {
            logger.removeHandler(h);
        }
        logger.setLevel(Level.INFO);

        Handler output = new StreamHandler(System.out, new KvFormatter()) {
            @Override
            public synchronized void publish(LogRecord record) {
                super.publish(record);
                flush();
            }
        };
        output.setLevel(Level.ALL);
        logger.addHandler(output);

        emit(logger, Level.INFO, "ORDER_ACCEPTED",
                Instant.parse("2026-11-09T10:15:30Z"),
                Map.of(
                        "orderId", "O-17",
                        "attempts", 1,
                        "success", true));

        emit(logger, Level.WARNING, "GATEWAY_FALLBACK",
                Instant.parse("2026-11-09T10:15:31Z"),
                Map.of(
                        "orderId", "O-18",
                        "dependency", "primary gateway",
                        "reason", "timeout\nretry"));
    }

    private static void emit(Logger logger, Level level,
                             String event, Instant when,
                             Map<String, ?> attributes) {
        LogRecord record = new LogRecord(level, event);
        record.setInstant(when);
        record.setParameters(new Object[]{attributes});
        logger.log(record);
    }

    private static final class KvFormatter extends Formatter {
        @Override
        public String format(LogRecord record) {
            StringBuilder line = new StringBuilder();

            line.append("timestamp=")
                    .append(quote(record.getInstant().toString()));
            line.append(" level=")
                    .append(quote(record.getLevel().getName()));
            line.append(" event=")
                    .append(quote(record.getMessage()));

            Object[] parameters = record.getParameters();
            if (parameters != null && parameters.length > 0
                    && parameters[0] instanceof Map<?, ?> fields) {

                // TreeMap keeps output deterministic, independent of
                // Map.of() iteration order in the JVM.
                TreeMap<String, Object> sorted = new TreeMap<>();

                for (Map.Entry<?, ?> entry : fields.entrySet()) {
                    if (!(entry.getKey() instanceof String key)
                            || !key.matches("[A-Za-z][A-Za-z0-9_]*")) {
                        throw new IllegalArgumentException(
                                "Invalid log field key");
                    }
                    if (key.equals("timestamp")
                            || key.equals("level")
                            || key.equals("event")) {
                        throw new IllegalArgumentException(
                                "Reserved log field key: " + key);
                    }
                    sorted.put(key, entry.getValue());
                }

                for (Map.Entry<String, Object> entry
                        : sorted.entrySet()) {
                    line.append(' ').append(entry.getKey())
                            .append('=')
                            .append(formatValue(entry.getValue()));
                }
            }
            return line.append('\n').toString();
        }

        private static String formatValue(Object value) {
            if (value == null) {
                return "null";
            }
            // NaN/Infinity are not finite numbers.
            if (value instanceof Double d && !Double.isFinite(d)) {
                return quote(d.toString());
            }
            if (value instanceof Float f && !Float.isFinite(f)) {
                return quote(f.toString());
            }
            if (value instanceof Number || value instanceof Boolean) {
                return value.toString();
            }
            return quote(String.valueOf(value));
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
                            out.append(String.format(
                                    Locale.ROOT, "\\u%04x", (int) c));
                        } else {
                            out.append(c);
                        }
                    }
                }
            }
            return out.append('"').toString();
        }
    }
}
```

### 6.2. Compiling and Running with JDK 17+

Save the file as `KvLoggingDemo.java`, then run from the directory containing the file:

```bash
javac -encoding UTF-8 KvLoggingDemo.java
java KvLoggingDemo
```

**Exact stdout** of the program:

```text
timestamp="2026-11-09T10:15:30Z" level="INFO" event="ORDER_ACCEPTED" attempts=1 orderId="O-17" success=true
timestamp="2026-11-09T10:15:31Z" level="WARNING" event="GATEWAY_FALLBACK" dependency="primary gateway" orderId="O-18" reason="timeout\nretry"
```

The two lines above are **two records**, even though `reason` in Java contains an actual newline. The formatter escaped it into the two characters `\n`, so no fake third log line is created.

### 6.3. Code Breakdown

1. `LogRecord` holds the level, event code, and instant. Timestamps in the example are **fixed** so stdout is deterministically reproducible; in a real application, use the actual event timestamp rather than hardcoding it.
2. `record.setParameters(new Object[]{attributes})` passes the map into the record for the custom formatter to read. This is an **internal contract of the example**, not a standard JUL structured attribute mechanism; if another formatter is used, the map may not be emitted.
3. `TreeMap` guarantees the order `attempts`, `orderId`, `success` in the first record regardless of how `Map.of(...)` iterates.
4. `quote(...)` handles double quotes, backslashes, newlines, tabs, carriage returns, and control characters below `U+0020`. It does not split a log line just because the input contains a newline.
5. `formatValue(...)` keeps `Number`/`Boolean` unquoted, while strings like `"true"` are quoted, preventing type confusion in supporting parsers. For infinite or NaN values, the demo emits a quoted string rather than assuming a valid number.
6. `logger.setUseParentHandlers(false)` prevents extra output from parent/root loggers. `StreamHandler(System.out, ...)` explicitly targets stdout and calls `flush()` after each `publish` so the lesson output is immediately visible; JUL’s default `ConsoleHandler` typically writes to stderr.
7. The program is single-threaded, performs no network/file I/O, and does not depend on the OS timezone because it uses a fixed UTC `Instant`.

**Known limitations:** this formatter is for educational purposes. It does not handle all unusual Unicode surrogates, size-limit policies, sensitive data, stack trace encoding, context propagation, or custom `Number` types. For producing data for large pipelines, prefer a maintained encoder tested with your actual parser; if consumers expect JSON, use a JSON serializer rather than feeding this `key=value` string to a JSON parser.

### 6.4. Further Experiments

- Change `reason` to `"bad=\"yes\"\nnext=ERROR"`: the output must **still be a single line** with `\"` and `\n`.
- Add numeric field `elapsedMs=3000` and boolean `fallback=true`: verify there are no quotes around numbers/booleans.
- Try key `"client id"` or `"x=y"`: the demo formatter rejects them via key validation, preventing fake pairs.
- With a `Map` that allows nulls, add a null value: output `field=null`, not confused with the string `"null"`.
- Enable level filtering on the logger or handler: only accepted records reach stdout; a formatter cannot “recover” filtered-out records.

## 7. With Log4j 2: `PatternLayout` for Human-Readable `key=value`

Log4j 2 lets you use `PatternLayout` with literal text and pattern converters:

```xml
<Console name="Console" target="SYSTEM_OUT">
    <PatternLayout
        pattern="level=%p logger=%c traceId=%X{traceId} message=%m%n"/>
</Console>
```

Here:

- `%p`: event level.
- `%c`: logger name.
- `%X{traceId}`: value of `traceId` in the Thread Context Map/MDC.
- `%m`: formatted message.
- `%n`: platform line separator.

Example of using `ThreadContext` in code:

```java
// Illustrative snippet in a service using Log4j 2, not a standalone file.
import org.apache.logging.log4j.CloseableThreadContext;

try (CloseableThreadContext.Instance scope =
        CloseableThreadContext.put("traceId", "req-1001")) {
    logger.info("Order {} accepted", "O-17");
}
```

Note that **the formatting problem is still not fully solved**: if `%m` or `%X{traceId}` contains spaces or newlines, the `PatternLayout` above **does not automatically quote each value according to the grammar in Section 3**. This is **readable pseudo key-value**, not machine-safe encoding. Use this pattern to learn converters, not as an ingestion contract for untrusted data.

Log4j 2 provides the `%enc{...}{CRLF}` converter to escape newlines and carriage returns in the wrapped portion, e.g. `%enc{%m}{CRLF}`. However, escaping CR/LF alone **does not automatically handle quotes/backslashes or enforce your system’s full key-value grammar**. When data must be parsed reliably, use a structured layout (especially `JsonTemplateLayout`) or a dedicated, tested key-value encoder.

**Do not confuse them:** `%X{traceId}` reads from the context map; PatternLayout’s `%K{key}` has a different meaning, used for certain `MapMessage` forms. Mistyping one for the other will not read the same data source. Always check the `PatternLayout` documentation for your exact backend version.

### Why not just concatenate `key=value` in the message?

```java
// Only builds a single string; the backend is unaware of separate fields.
logger.info("orderId=" + orderId + " elapsedMs=" + elapsedMs);
```

It may be **readable**, but it does not guarantee that the backend stores them as two structured attributes. Furthermore, `+` concatenation runs at the call site before the backend filters the log level, which can be wasteful if operands are expensive or the log level is disabled. Prefer parameterized logging APIs for existing variables, and keep structured attributes in a supported API/encoder when you want to query by field.

## 8. With SLF4J 2: Key-Value as Attributes, Not Just Message Text

SLF4J 2.x provides a **fluent logging API** that lets you attach key-value pairs to an event:

```java
// Illustrative snippet in an application with SLF4J 2.x and a compatible provider/backend.
logger.atInfo()
      .addKeyValue("orderId", "O-17")
      .addKeyValue("elapsedMs", 125)
      .log("Order processed");
```

This API carries key-value pairs as event metadata; it **does not mean every provider will automatically print `orderId="O-17"` or put `elapsedMs` into JSON under the same field name**. How it is rendered depends on the provider, encoder/layout, version, and configuration. For example, `slf4j-simple` has its own formatting; Logback and Log4j 2 have their own layout systems and differing support for preserving key-value pairs.

Writing only placeholders in the message:

```java
logger.info("Order {} processed in {} ms", orderId, elapsedMs);
```

avoids eager string concatenation, but **does not guarantee** the collector sees `orderId` and `elapsedMs` as two separate fields. Distinguish between:
- **Parameterized message:** a template and arguments used to construct the message string.
- **Structured key-value attributes:** field-name/value pairs carried separately on the event and supported by the encoder.

In SLF4J 1.7, the fluent API `atInfo().addKeyValue(...)` does not exist. When upgrading code, verify the runtime API version and provider/backend to avoid `NoSuchMethodError` or silently dropped metadata.

## 9. With Logback: Patterns and Key-Value Configuration

Logback is commonly used as the backend for SLF4J. In Logback, `PatternLayoutEncoder` or other encoders convert events into text/bytes for appenders to write. Example basic layout:

```xml
<configuration>
  <appender name="CONSOLE" class="ch.qos.logback.core.ConsoleAppender">
    <encoder>
      <pattern>level=%level logger=%logger message=%msg%n</pattern>
    </encoder>
  </appender>
  <root level="INFO">
    <appender-ref ref="CONSOLE"/>
  </root>
</configuration>
```

This is an illustrative Logback configuration file, **not a standalone Java program**; it requires compatible SLF4J and Logback versions. As with the Log4j 2 example, `%msg` is not quoted/escaped according to the Section 3 key-value contract, so use it only as a **human-readable pattern**.

Some modern Logback versions support conversion words or encoders specifically for handling key-value pairs from the SLF4J fluent API. **Do not assume every Logback version has the same converter or syntax.** Read the documentation for your exact version and test cases where keys/values contain spaces, quotes, and newlines.

If you need structured ingestion in production, consider a JSON encoder for Logback that matches your version and schema requirements, or use a collector with an officially verified parser. Do not copy a Log4j 2 `log4j2.xml` into `logback.xml`: the two systems use different configuration syntaxes.

## 10. Key-Value Text vs. JSON Lines

The same event can be represented in two ways.

**Key-value text using this lesson’s grammar:**

```text
level="WARN" event="PAYMENT_TIMEOUT" orderId="O-17" elapsedMs=3000 action="SELECT_FALLBACK"
```

**JSON Lines (one JSON object per line):**

```json
{"level":"WARN","event":"PAYMENT_TIMEOUT","orderId":"O-17","elapsedMs":3000,"action":"SELECT_FALLBACK"}
```

| Criterion | Key-value text | JSON Lines |
| --- | --- | --- |
| Manual readability | Compact, minimal syntax punctuation. | Still readable, though more braces/quotes. |
| Standardized grammar | Depends on logfmt-like conventions and specific parser. | JSON has a well-defined syntax standard. |
| Number/Boolean/Null | Depends on rules and parser. | JSON defines explicit literals. |
| Nested data | Requires flattening conventions or custom string encoding. | Natively supports nested objects/arrays. |
| Escaping | Must be agreed upon; error-prone if hand-rolled. | Handled by standard JSON serializers when used properly. |
| Ingest/query | Requires a compatible parser. | Easily integrates with JSON-capable systems. |
| Multi-backend compatibility | Requires consistent templates/encoders. | Usually has JSON encoders or suitable plugins. |

**Practical decision:** use `key=value` when the goal is short, grep-friendly lines and the system already has an agreed-upon grammar and parser. Choose **JSON structured logging** when you need strict schemas, nested fields, multi-system ingestion, and reliable analytics tooling. Never hand-roll JSON via string concatenation, and do not treat a text pattern with `key=` literals as full structured logging.

## 11. Context Propagation, MDC, and Correlation Fields

In a multi-service system, a single request chain can emit hundreds of events. Fields such as `correlationId`, `traceId`, or `spanId` allow filtering related events.

In Log4j 2, `ThreadContext` maintains a map/stack for the current execution context. In SLF4J/Logback, `MDC` is commonly used. However, many implementations rely on `ThreadLocal`; when running across executors, `CompletableFuture`, or reactive pipelines, context **does not necessarily propagate automatically** across threads.

Key principles:

1. Attach a correlation ID at the request boundary; do not generate a new ID at every layer.
2. Propagate context when offloading work to another thread using the mechanism provided by your runtime.
3. Restore/clear context in a `finally` block or managed scope so thread pools do not leak context between requests.
4. Do not automatically dump all HTTP headers, cookies, or request bodies into MDC.
5. When using async logging, pay attention to when data is snapshotted so the event does not mutate after creation.

**`key=value` fields should capture state at log time**, rather than depending on mutable objects modified before the encoder runs on a background thread. If incident investigation requires accuracy, create a compact, immutable, log-safe snapshot.

## 12. Security, PII, and Log Injection

Both structured and key-value logging can leak secrets if events are constructed carelessly.

### Disallowed data

Never log: passwords, OTPs, access tokens, refresh tokens, session cookies, private keys, full sensitive payment details, or personal data beyond what investigation requires. For domain objects, do not assume the default `toString()` performs safe redaction.

**Better:** include only allowlisted IDs and metrics such as `orderId`, `event`, `elapsedMs`, and `outcome`. Configure log store access controls, retention, encryption in transit, and encryption at rest according to policy.

### Escaping must happen before output

If input contains newlines, quotes, or backslashes, encode it according to the shared grammar **before the handler/appender writes it**. Downstream collector filters cannot erase secrets already written to stdout or files before collection.

### Truncation and size limits

An oversized message field can cause collectors to truncate bytes, break quotes, or drop trailing fields; if you truncate, define the limit in **bytes or characters**, preserve valid syntax, and add a `truncated=true` indicator when needed. Avoid cutting in the middle of a multi-byte UTF-8 sequence, Unicode surrogate, or escape sequence. In many systems, reducing event size at the source and offloading detailed payloads to a dedicated store is better than stuffing entire payloads into logs.

### Do not let dynamic fields cause unbounded cardinality

Keys should be a finite, code-reviewed list. Turning customer names, emails, or query URLs into **field names** is a design flaw; it bloats collectors/indexes and risks data exposure. High-cardinality ID values must also be used appropriately (for searching events, not as unbounded metric labels).

## 13. Testing Formatters and Ingestion Systems

A formatter that merely “looks nice” is not enough. For key-value logging, test **round-trip** behavior: encode event → parser ingests → decode back to the exact original fields and values.

| Test case | Expectation |
| --- | --- |
| String without spaces | Quoted per grammar or parsed accurately. |
| String with spaces/tabs | Does not produce extra tokens or fake pairs. |
| Double quotes in value | Escaped and decoded back to the original string. |
| Backslashes in paths | Not swallowed or mis-doubled when parsed. |
| Newline/CR/LF | A single event does not split into multiple lines. |
| Equals sign in value | Does not create additional key-value pairs. |
| Vietnamese Unicode | Diacritics preserved, valid UTF-8 read/write, no mid-byte cuts. |
| Boolean, integer, decimal | Clear data type and unit rules. |
| Missing/null/empty string | Properly distinguished per schema. |
| Invalid/dynamic key | Rejected or normalized according to defined policy. |
| Exception | Error code and stack trace included as supported by encoder/collector. |
| Concurrent/async logging | No mixing of correlation IDs or mutable values across requests. |
| Structured attributes vs. message | Actual provider/layout preserves queryable pairs. |
| Collector/parser | Reads fields and event size limits accurately; reports parse errors rather than failing silently. |

For the JUL demo in Section 6, you can run the program and compare stdout verbatim. A more advanced step is writing a decoder for the defined grammar and testing the round-trip property:

```text
decode(encode("a b=\n\"c")) == "a b=\n\"c"
```

This is a **test assertion**, not standalone Java code. Testing with a table of special characters, randomized strings, and missing-data cases catches escaping bugs far better than a few happy-path examples.

**When the backend fails to emit a field:** check in order whether the code created the attribute → logger level/filter → whether the provider received the key-value → whether the layout/encoder supports it → appender sink → collector parse → index/query. Never assume data was stored just because the source code calls `addKeyValue(...)`.

## 14. Common Mistakes

1. **Concatenating `message=hello world` without quotes:** the parser splits it into multiple tokens.
2. **Putting user input into keys:** mutates the schema, enables injection, or explodes field count.
3. **Escaping only quotes while ignoring newlines/backslashes:** logs can be forged or misparsed.
4. **Calling `logger.info("id={}", id)` and assuming the collector gets an `id` field:** it may only be a formatted message string.
5. **Using `PatternLayout` with `level=%p msg=%m` as a complete structured encoder:** spaces and newlines can still break the grammar.
6. **Failing to distinguish null, empty string, and missing fields:** loses business meaning.
7. **Changing field names/units arbitrarily across modules:** makes dashboards and alerts hard to compare.
8. **Logging too many fields or whole objects:** increases cost, exceeds size limits, and leaks PII.
9. **Not checking the backend version:** key-value converters may be unsupported or behave differently on your runtime version.
10. **Testing only on the console, not with the parser/collector:** a “pretty” log is not guaranteed to be searchable in the log store.
11. **Building the message on another thread after a mutable object changes:** timestamps, context, and values no longer reflect event time.
12. **Treating key-value logs as the sole audit source:** text logs do not inherently guarantee integrity, zero loss/duplication, or transaction commit state.

## 15. Production Readiness Checklist

- [ ] A documented `key=value` formatting contract covering quoting, escaping, separators, null handling, and data types.
- [ ] Stable field names, explicit units, and a `schemaVersion` for breaking changes.
- [ ] Each log event occupies exactly one logical record; newlines in input cannot forge extra records.
- [ ] Framework-appropriate formatter/layout used (JUL `Formatter`, Log4j 2 `Layout`, Logback `Encoder`).
- [ ] Clear distinction between message parameters and backend-supported key-value metadata.
- [ ] UTC/offset timestamp, level, service, event code, and correlation ID included where needed.
- [ ] Never use user input as keys; enforce allowlists, size limits, redaction, and access controls.
- [ ] Encode/decode tests covering tricky inputs: spaces, `=`, `"`, `\\`, Unicode, newlines, and `null`.
- [ ] Provider/encoder/collector tested with final artifacts and production-equivalent configuration.
- [ ] For strict structured ingestion, evaluate a JSON encoder rather than relying solely on text `PatternLayout`.
- [ ] Observability in place for parse errors, drop rates, ingest lag, retention, and sink durability.

## References

- [Java 17 — java.util.logging.Formatter](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Formatter.html)
- [Apache Log4j 2 — Pattern Layout and MDC converters](https://logging.apache.org/log4j/2.x/manual/pattern-layout.html)
- [Apache Log4j 2 — Thread Context](https://logging.apache.org/log4j/2.x/manual/thread-context.html)
- [Apache Log4j 2 — JSON Template Layout](https://logging.apache.org/log4j/2.x/manual/json-template-layout.html)
- [SLF4J 2 — Fluent API and key-value pairs](https://www.slf4j.org/manual.html)
- [Logback — Layouts and PatternLayout](https://logback.qos.ch/manual/layouts.html)

**Takeaway:** key-value formatting makes logs clear and analyzable **only when field names, data types, and encoding rules are consistent**. A formatter can print `orderId="O-17" elapsedMs=3000`, but an event is only truly “structured” to a collector when metadata, escaping, and the parser share the same contract. When high reliability and queryability are required, prefer an officially supported structured encoder and test end-to-end.
