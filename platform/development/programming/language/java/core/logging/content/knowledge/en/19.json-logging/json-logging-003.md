# The message Field in Java JSON Logging

## 1. What Is the `message` Field?

In **JSON logging**, a log event is typically represented as a JSON object. The **`message`** field (usually a string) carries a **human-readable description of the event**: what just happened, which operation succeeded, or what error sign needs attention. It helps readers quickly understand the context even before knowing the entire schema.

Example:

```json
{"timestamp":"2026-11-09T10:15:30Z","level":"INFO","service":"order-service","event":"ORDER_ACCEPTED","orderId":"O-17","message":"Order accepted"}
```

In this event:

- `timestamp` is when the event occurred, using explicit UTC.
- `level` is the log level; for example, INFO, WARN, ERROR in Log4j/Logback, or INFO, WARNING, SEVERE in JUL.
- `service` indicates the service that emitted the event.
- `event` is a **stable event code** for queries, dashboards, and alerts.
- `orderId` is a **separate business attribute** for filtering events.
- `message` is a **descriptive sentence**; it can be reworded for clarity without necessarily changing the event code.

**The `message` field is not the entire log event.** It is distinct from metadata, context, exception, and business attribute fields. Good practice is to let operators immediately read the meaning of the event while keeping data needed for filtering/aggregation in separate fields.

### Why Use JSON Instead of Just a Line of Text?

A text line like:

```text
2026-11-09 WARN Order O-17 failed after 3000ms
```

is readable, but hard to parse reliably by automation if word positions change. JSON has explicit field names:

```json
{"timestamp":"2026-11-09T10:15:30Z","level":"WARN","event":"ORDER_TIMEOUT","orderId":"O-17","elapsedMs":3000,"message":"Order processing timed out"}
```

At this point, a collector can read `elapsedMs` as a number, `event` as a string, and does not need to guess `3000ms` from a sentence. **Logging as JSON only enables structured data; a long message still does not automatically turn all information inside it into separate fields.**

## 2. Role and Recommended Content of `message`

A good message should clearly state **the actual event that occurred** at a level appropriate for the log level, without asserting unverified claims. Some examples:

| Situation | Recommended Message | Why |
| --- | --- | --- |
| Order created successfully | `"Order accepted"` | Clear completion state; no need to stuff the order ID into the sentence. |
| Backend call timed out | `"Payment gateway request timed out"` | Describes the event without assuming the transaction permanently failed. |
| Switched to fallback branch | `"Fallback provider selected"` | Describes the specific action. |
| Optional configuration not found | `"Optional configuration missing; using default"` | States a clear operational consequence. |
| Operation rejected due to validation | `"Request validation failed"` | Does not expose full user data. |
| Connection closed unexpectedly | `"Upstream connection closed unexpectedly"` | Avoids vague wording like "something wrong". |

A message should:

1. **Be short yet informative**; usually one sentence expressing the event, not a dump of an entity/request.
2. **Have a sensible subject or context** if the event code alone is not enough.
3. **Describe what happened**, not promise that a retry succeeded when the retry has only just started.
4. **Avoid secret data**; messages can be sent to many sinks and many viewer groups.
5. **Avoid unnecessary dynamic variations** if the goal is grouping/aggregating logs.
6. **Not replace a stable event code**, especially when building dashboards and alerts by event type.

Good example for an event:

```json
{"level":"WARN","event":"PAYMENT_GATEWAY_TIMEOUT","gateway":"primary","elapsedMs":3000,"retryable":true,"message":"Payment gateway did not respond before deadline"}
```

There is no need to turn `message` into:

```text
Payment gateway primary timed out after 3000ms, retryable=true, requestId=..., orderId=..., ...
```

when those attributes are already in separate fields. Repeating all data into `message` makes logs longer, makes redacting sensitive information harder, and increases storage costs.

## 3. Data Type of the `message` Field

### 3.1. Prefer a Consistent JSON String

For standard schemas, the convention is:

```json
{"message":"Order accepted"}
```

meaning **`message` is a string**. JSON supports objects, arrays, numbers, booleans, and null, but **a field should keep the same data type** across events if the storage system indexes by schema, especially when the backend has fixed mapping/typing.

Avoid randomly emitting both forms:

```json
{"message":"Order accepted"}
```

and:

```json
{"message":{"action":"accept","orderId":"O-17"}}
```

The second line may be valid JSON, but an indexer that has defined `message` as a string type may encounter a **mapping conflict** when receiving an object. This is a schema error, not a JSON parser error.

**Recommendation:** keep `message` as a string for normal events; if object-shaped metadata is needed, move it to a separate branch such as `attributes`, `context`, or a field name matching the agreed schema.

### 3.2. Distinguishing Absent, Null, and Empty String

These three cases are not equivalent:

```json
{"event":"ORDER_ACCEPTED"}
```

```json
{"event":"ORDER_ACCEPTED","message":null}
```

```json
{"event":"ORDER_ACCEPTED","message":""}
```

- **Absent:** there is no `message` field (possibly omitted by the encoder or not provided by the producer).
- **Null:** the field is present, but has no string value.
- **Empty string:** there is a string with length 0.

Some ingestion systems treat these values differently. When an application requires `message` to always be present, design an intentional fallback, such as a safe sentence based on the event code. **Do not automatically assign "null" or "unknown" if it hides a producer bug or distorts the event's meaning.**

### 3.3. Unicode and Languages

JSON supports Unicode. Vietnamese messages are completely valid:

```json
{"level":"WARN","message":"Kết nối đến dịch vụ thanh toán bị gián đoạn"}
```

Prefer **UTF-8** encoding across the application, stdout/files, collector, and storage. If a system uses stable English event codes for analysis, `message` can still be in Vietnamese depending on organizational requirements; dashboards should not use free-form messages as the sole identifier.

## 4. Raw Message, Message Template, and Formatted Message

This is the most confusing part when using Java logging APIs.

### Direct String Message

```java
// Example when logger is an SLF4J or Log4j 2 Logger.
logger.info("Order accepted");
```

The input message is a fixed string. A JSON encoder can output it as:

```json
{"message":"Order accepted"}
```

### Parameterized Template Message

In SLF4J and Log4j 2, you commonly see:

```java
logger.info("Order {} accepted", orderId);
```

Here:

- **Template:** `Order {} accepted`.
- **Argument:** the value of `orderId` at the call site.
- **Formatted message:** for example, `Order O-17 accepted` if `orderId="O-17"`.

Depending on the framework and layout, the JSON `message` field is usually configured to contain the **formatted message**. However, logging with a `{}` template must not be assumed to guarantee that the producer automatically creates a separate `orderId` JSON field. If you need to search by order ID, record `orderId` via a **structured attribute/MDC** supported by the encoder.

With **JUL (`java.util.logging`)**, `Formatter.formatMessage(LogRecord)` can apply `java.text.MessageFormat` to a pattern such as:

```java
// JUL pattern, not SLF4J placeholder syntax.
logger.log(java.util.logging.Level.INFO,
           "Order {0} accepted", "O-17");
```

If a formatter calls `record.getMessage()` without `formatMessage(record)`, it may output `Order {0} accepted` verbatim instead of the parameter-substituted text. **You must know the placeholder convention of the exact logging API**; JUL uses `{0}`, SLF4J uses `{}`, and the two styles must not be mixed up.

### Avoid Concatenating Dynamic Data into `message` Unnecessarily

```java
// Avoid unnecessary string concatenation before the backend filters by level.
logger.debug("Full order=" + order.toString());

// Usually better when only an allowed ID needs to be logged.
logger.debug("Order id={}", orderId);
```

String concatenation in a `+` expression can happen **before** the logger decides not to record DEBUG, and an arbitrary `toString()` may leak data or incur cost. Parameterized logging usually avoids building the final string prematurely, but **Java arguments are evaluated before the call**; if a parameter is computed via `expensive()`, that method still runs unless an appropriate lazy/supplier mechanism or guard is used.

## 5. How `message` Differs from Structured Fields and Event Codes

A useful event typically includes all of these:

```json
{
  "timestamp":"2026-11-09T10:15:30Z",
  "level":"INFO",
  "event":"ORDER_ACCEPTED",
  "service":"order-service",
  "orderId":"O-17",
  "message":"Order accepted"
}
```

This is **a JSON object formatted across multiple lines for readability**, not a JSON Lines example for direct collector consumption. In JSON Lines, it needs to be serialized onto a single physical line.

Why not log only `message`?

- **Alerting:** creating alerts on `ORDER_ACCEPTED`/`PAYMENT_TIMEOUT` codes is less affected by wording changes.
- **Filtering:** searching `orderId="O-17"` accurately, instead of substring matching inside `message`.
- **Aggregation:** counting by `event` or `level`, avoiding a separate message group per order ID.
- **Tracing:** `traceId`, `spanId`, and `correlationId` can correlate events across services.
- **Performance:** typed fields like `elapsedMs` (number) support direct computation.
- **Security:** controlling which attributes are allowed to be logged is easier than putting arbitrary objects into a free-form string.

Do not use `message` as a metric label if it contains per-request varying IDs/URLs/paths: that creates **high cardinality**. Use a stable event code label instead and store `message` only as log data.

## 6. JSON Escaping: Preserving the Meaning of `message`

Because `message` is a string inside JSON, its content must be **encoded according to JSON string rules**. Do not write:

```java
// WRONG: can produce invalid JSON and cause log injection.
String json = "{\"message\":\"" + message + "\"}";
```

Suppose `message` contains double quotes:

```text
Invalid field "name"
```

If concatenated directly, the result is broken:

```text
{"message":"Invalid field "name""}
```

A proper JSON encoder will write:

```json
{"message":"Invalid field \"name\""}
```

### Characters That Need Escaping

| Data in `message` | Escape Sequence in JSON | Why |
| --- | --- | --- |
| Double quote `"` | `\"` | Does not terminate the string prematurely. |
| Backslash `\` | `\\` | Not interpreted as the start of an escape sequence. |
| Newline (LF) | `\n` | Does not create a new physical line inside the record. |
| Carriage return (CR) | `\r` | Does not affect record/display boundaries. |
| Tab | `\t` | Preserves content without creating hard-to-control separators. |
| Backspace/form feed | `\b` / `\f` | Escapes the corresponding control characters. |
| Other control characters U+0000–U+001F | `\u00XX` | JSON strings must not contain raw control characters. |

Forward slash `/` is generally not required to be escaped. Valid Unicode characters can be written directly as UTF-8 or as `\uXXXX` depending on the serializer. In particular, **invalid surrogates** must be handled when a Java string contains a broken UTF-16 pair; well-maintained JSON libraries typically have a policy to handle or reject invalid data.

### Newlines, JSON Lines, and Log Forging

If the original message is:

```text
Payment attempt failed
{"level":"INFO","message":"Everything succeeded"}
```

then a raw newline **cannot** be allowed into a JSON string without escaping. The correct form on a single JSON Lines line is:

```json
{"level":"ERROR","message":"Payment attempt failed\n{\"level\":\"INFO\",\"message\":\"Everything succeeded\"}"}
```

This remains **one ERROR event**, not two independent events. For collectors using NDJSON/JSON Lines, each event is serialized as one **JSON object on a single line**, terminated by a newline *outside* the JSON string.

**Do not expect a plain-text PatternLayout to act as a JSON encoder**. Use `JsonTemplateLayout`, a JSON encoder, or a proper JSON serializer library for your framework. Hand-written escaping should only be used for educational examples with clear tests.

## 7. Standalone Java 17 Example: JUL Formatter Outputting `message` as JSON Lines

The following program uses **pure JDK 17**, without Maven, Log4j 2, or Jackson. It illustrates the flow:

```text
Logger.log(LogRecord)
    -> JUL StreamHandler
    -> JsonLineFormatter.format(record)
    -> encode JSON string
    -> stdout: one JSON object per line for each event
```

Criteria of the example:

1. Each event contains `timestamp`, `level`, `logger`, and `message` in a **fixed field order**.
2. The `message` field comes from **`formatMessage(record)`** to demonstrate JUL `{0}` parameter substitution.
3. Quotes, backslashes, newlines, and control characters are escaped.
4. Timestamps are fixed so stdout is **deterministic**.
5. The logger does not forward events to parent handlers, avoiding duplicate logs on stderr.
6. `StreamHandler` flushes after each event in the demo program. Output is produced from a single thread only.

### 7.1. File `JsonMessageDemo.java`

```java
import java.time.Instant;
import java.util.Locale;
import java.util.logging.Formatter;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;
import java.util.logging.StreamHandler;

public final class JsonMessageDemo {

    private JsonMessageDemo() {
    }

    public static void main(String[] args) throws Exception {
        Logger logger = Logger.getLogger("demo.json.message");
        logger.setUseParentHandlers(false);
        logger.setLevel(Level.ALL);

        for (Handler previous : logger.getHandlers()) {
            logger.removeHandler(previous);
        }

        Handler output = new StreamHandler(System.out,
                                          new JsonLineFormatter()) {
            @Override
            public synchronized void publish(LogRecord record) {
                super.publish(record);
                flush();
            }
        };
        output.setEncoding("UTF-8");
        output.setLevel(Level.ALL);
        logger.addHandler(output);

        emit(logger, Level.INFO,
             "2026-11-09T10:15:30Z",
             "Order {0} accepted", "O-17");

        emit(logger, Level.WARNING,
             "2026-11-09T10:15:31Z",
             "Invalid field \"name\"\nnext=C:\\logs");

        emit(logger, Level.SEVERE,
             "2026-11-09T10:15:32Z",
             "");

        output.flush();
        logger.removeHandler(output);
        // Do not close output: StreamHandler.close() can
        // also close System.out, which is a shared resource.
    }

    private static void emit(Logger logger, Level level,
                             String when, String template,
                             Object... arguments) {
        LogRecord record = new LogRecord(level, template);
        record.setLoggerName(logger.getName());
        record.setInstant(Instant.parse(when));
        record.setParameters(arguments);
        logger.log(record);
    }

    private static final class JsonLineFormatter extends Formatter {
        @Override
        public String format(LogRecord record) {
            return "{"
                 + "\"timestamp\":" + json(record.getInstant().toString())
                 + ",\"level\":" + json(record.getLevel().getName())
                 + ",\"logger\":" + json(record.getLoggerName())
                 + ",\"message\":" + json(formatMessage(record))
                 + "}\n";
        }

        private static String json(String value) {
            if (value == null) {
                return "null";
            }

            StringBuilder out = new StringBuilder("\"");

            for (int i = 0; i < value.length(); i++) {
                char ch = value.charAt(i);

                switch (ch) {
                    case '"'  -> out.append("\\\"");
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
                        } else if (Character.isHighSurrogate(ch)) {
                            if (i + 1 < value.length()
                                    && Character.isLowSurrogate(
                                            value.charAt(i + 1))) {
                                out.append(ch)
                                   .append(value.charAt(++i));
                            } else {
                                out.append("\\uFFFD");
                            }
                        } else if (Character.isLowSurrogate(ch)) {
                            out.append("\\uFFFD");
                        } else {
                            out.append(ch);
                        }
                    }
                }
            }
            return out.append('"').toString();
        }
    }
}
```

### 7.2. Compile and Run

Save the file with the exact name `JsonMessageDemo.java`, then use Java 17 or later:

```bash
javac -encoding UTF-8 JsonMessageDemo.java
java JsonMessageDemo
```

**Exact stdout of the program** (each line below is **one complete JSON object**):

```json
{"timestamp":"2026-11-09T10:15:30Z","level":"INFO","logger":"demo.json.message","message":"Order O-17 accepted"}
{"timestamp":"2026-11-09T10:15:31Z","level":"WARNING","logger":"demo.json.message","message":"Invalid field \"name\"\nnext=C:\\logs"}
{"timestamp":"2026-11-09T10:15:32Z","level":"SEVERE","logger":"demo.json.message","message":""}
```

### 7.3. Why Does the Output Look Like This?

- **Line 1:** `formatMessage(record)` takes the JUL pattern `Order {0} accepted` and argument `O-17`, producing `Order O-17 accepted`.
- **Line 2:** the Java string contains **real quotes, a real newline, and a real backslash**. `json(...)` replaces them with JSON escapes (`\"`, `\n`, `\\`). Therefore, it remains **a single physical line**.
- **Line 3:** an empty message is still validly represented as `"message":""`; it is not confused with `null` or an absent field.
- `Level.WARNING` and `Level.SEVERE` are **JUL** level names. When using Log4j 2 or SLF4J, the names are typically WARN/ERROR; do not automatically replace them with those names in JUL output.
- `logger.setUseParentHandlers(false)` prevents the parent logger from printing extra records through the default handler.
- `StreamHandler` flushes after `publish`, ensuring lines appear before the program exits. The demo code does not close the shared `System.out`.
- The timestamp uses `Instant.parse`, so it does not vary by machine timezone.

**Boundaries of the demo:** this is an educational formatter, not a JSON encoder certified for production deployment. It lacks size limits, redaction policies, fallbacks for abnormal messages, structured stack traces, JSON schema registry integration, metrics, async backpressure, and collector integration. In production, you need a maintained serializer and encoder, compatibility tests across components, and alignment with the logging platform's schema.

### 7.4. Additional Testing Exercises

Try adding a message:

```java
// Illustrating a value in an additional emit call:
"Line 1\r\nLine 2\tpath=C:\\temp"
```

Expect the JSON string to contain the escapes `\r\n`, `\t`, and `\\` respectively instead of raw control characters. For Vietnamese Unicode characters, test reading it back with a UTF-8 compliant JSON parser. For invalid UTF-16 surrogate pairs, the demo chooses to output `\uFFFD` (the Unicode replacement character) rather than keeping an invalid code unit.

A strong test is **round-trip**: create an input message → encode to JSON → parse back with a JSON parser → the decoded message must equal the original valid input. The only exception in the demo: unpaired surrogates are converted to the replacement character according to the stated policy.

## 8. The `message` Field in Log4j 2 JSON Template Layout

When an application uses **Apache Log4j 2**, JSON should be generated by an appropriate **Layout** rather than manual string concatenation. Log4j 2 provides **`JsonTemplateLayout`**, which can use the `message` resolver.

An illustrative event template placed in `src/main/resources/message-event-template.json`:

```json
{
  "timestamp": {
    "$resolver": "timestamp",
    "pattern": {
      "format": "yyyy-MM-dd'T'HH:mm:ss.SSS'Z'",
      "timeZone": "UTC"
    }
  },
  "level": {
    "$resolver": "level",
    "field": "name"
  },
  "logger": {
    "$resolver": "logger",
    "field": "name"
  },
  "message": {
    "$resolver": "message",
    "stringified": true
  }
}
```

Configuration snippet in `log4j2.xml`:

```xml
<Console name="JSON_CONSOLE" target="SYSTEM_OUT">
    <JsonTemplateLayout
        eventTemplateUri="classpath:message-event-template.json"/>
</Console>
```

This is **a snippet inside `<Appenders>`**, not a standalone `log4j2.xml` file; you still need logger/`AppenderRef` declarations and the appropriate Log4j 2 dependencies. Using `JsonTemplateLayout` requires the runtime module:

```text
org.apache.logging.log4j:log4j-layout-template-json
```

version-aligned with the corresponding Log4j 2 modules, preferably via the Log4j BOM or the framework's dependency management.

**Meaning of `"stringified": true`:** the `message` resolver outputs the content as a **JSON string** instead of preserving an object/list when an event uses a `Message` type that supports structured data. This helps keep the type of the `message` field consistent in strictly indexed systems.

If `stringified: true` is omitted, some `ObjectMessage`/`MapMessage` types may be represented as JSON objects instead of strings. That can be useful for an intentional schema, but if `message` is sometimes a string and sometimes an object, storage such as Elasticsearch can hit mapping conflicts. The choice should come from **the receiving system's schema**, not from an assumption that "an object is always better".

**Do not confuse the `message` resolver with the parameters field:** Log4j 2 has a separate mechanism for accessing message parameters, but using that resolver does not mean you already have a meaningful `orderId` field. Use MDC/context map or a structured message with a suitable schema when you need to separate attributes, and keep `message` as a short description.

For applications using **SLF4J → Log4j 2**, you also need to configure the right adapter/provider for your SLF4J generation so logs actually reach the Log4j backend. Simply adding `log4j-layout-template-json` will not automatically switch the pipeline.

## 9. The `message` Field in SLF4J 2 and Logback

SLF4J is an API facade: it forwards logging calls to a provider/backend. In SLF4J 2, a call like:

```java
// Illustration snippet; logger is org.slf4j.Logger version 2.x.
logger.atInfo()
      .addKeyValue("orderId", "O-17")
      .addKeyValue("elapsedMs", 125)
      .log("Order processed");
```

has **two kinds of data**:

- **Message:** `Order processed`.
- **Key-value attributes:** `orderId="O-17"` and `elapsedMs=125`.

A backend/encoder can keep these pairs separate, but **not every provider or layout automatically outputs them as a JSON object with identical field names**. You must check the actual configuration of the running Logback/Log4j 2/provider setup. Adding `addKeyValue(...)` does not automatically guarantee that the fields appear in your search store.

In **Logback**, `PatternLayoutEncoder` produces **text** by default. If the pattern is only `%msg%n`, a collector receives the message sentence rather than a JSON object with a `message` field; you should not try to build JSON by concatenating a literal `{"message":"%msg"}`, because `%msg` may contain quotes or newlines.

If using a Logback JSON encoder/layout, verify that the plugin/version matches the SLF4J API, schema, and metadata/exception storage requirements. Different encoder libraries may name the field `message`, `formattedMessage`, or use another structure. **Do not assume field names and escaping behavior are the same across all encoders.**

## 10. Separating Messages from Exceptions

An error typically needs both a **short message** and **structured exception information**:

```json
{"timestamp":"2026-11-09T10:15:32Z","level":"ERROR","event":"ORDER_SUBMISSION_FAILED","orderId":"O-18","message":"Order submission failed","error":{"type":"java.net.SocketTimeoutException","message":"Read timed out"}}
```

Goals:

- Top-level `message` states the **business event**.
- `error.type` states the exception type; it can be used to group root causes.
- `error.message` describes the technical error; **must be controlled for the risk of containing URLs/tokens/user input**.
- The stack trace can live in another field such as `stackTrace`, `error.stack_trace`, or an array structure depending on the schema.
- `orderId` is stored separately for querying instead of being embedded in every message.

In the logging API:

```java
// Illustration inside an application's catch (Exception ex) block:
logger.error("Order submission failed for id={}", orderId, ex);
```

With APIs supporting this signature, passing `Throwable` as a separate parameter lets the backend capture the stack trace properly. Conversely, writing only:

```java
logger.error("Order submission failed: " + ex);
```

may retain only `ex.toString()`, losing the full stack trace or structured exception. **Depending on the encoder**, the stack trace may be emitted as a text string, an array, or another field; verify the actual output.

**Do not copy the stack trace into `message` when a separate exception field already exists and there is no explicit requirement to do so.** It makes `message` overly long, can introduce newlines, and makes dashboards hard to read. If an ingestion platform requires the stack trace inside `message` (some specialized integrations), that must be an intentional schema rule, not applied blindly to every system.

## 11. Thread Context / MDC and `message`

When an application serves multiple requests, `message` should be combined with **correlation metadata** carried separately.

Example:

```json
{"level":"INFO","traceId":"4bf92f3577b34da6a3ce929d0e0e4736","orderId":"O-17","message":"Order accepted"}
```

Log4j 2 has **ThreadContext**; SLF4J/Logback has **MDC**. They allow attaching metadata to the processing context. However, in many implementations context relies on thread-local storage; when executing across executors, `CompletableFuture`, or reactive schedulers, context **does not automatically propagate in all situations**.

Principles:

1. Attach trace/correlation IDs once at the request boundary according to your tracing design.
2. Propagate context properly when switching threads/async, and never let a thread pool retain a previous request's ID.
3. Clear context when leaving the processing scope, especially when using thread pools.
4. Do not put entire HTTP headers, request bodies, or cookies into MDC.
5. Ensure the encoder outputs context under field names that follow a consistent contract.
6. If an object is mutable, take a compact, safe snapshot at the time the event is created.

Logs with the same `message` across thousands of requests can still be investigated if each event has an appropriate timestamp, trace ID, and business ID. **The solution is not to stuff the entire request into `message`.**

## 12. Security: `message` Is an Easy Place to Leak Data Accidentally

The `message` field is often treated as "just text", which is why many developers accidentally log:

- Full URLs containing query tokens or password reset codes.
- HTTP `Authorization` headers, session cookies, or refresh tokens.
- Passwords, OTPs, private keys, or sensitive payment information.
- Personal data unnecessary for investigation.
- Large raw payloads without size limits containing user data.
- `Throwable` messages embedding secret values generated by third-party libraries.

Example to avoid:

```java
logger.warn("Failed request: {}", request.toString());
```

because `request.toString()` may contain fields that must not be logged. Replace with:

```java
logger.warn("Request validation failed: errorCode={}", safeErrorCode);
```

and add safe fields such as event code, correlation ID, endpoint template, or status if needed.

**JSON escaping is not redaction.** A string can be completely valid JSON syntax while still leaking an access token. Perform allowlisting/redaction at the source, then apply a compliant JSON serializer. Do not treat 30-day log retention deletion as sufficient security.

### Log Injection

An attacker can send a message containing a newline and a spoofed ERROR/INFO log string. A proper JSON Lines serializer escapes control characters and keeps everything inside **one JSON string**, though you must still verify that the collector does not split raw messages before parsing.

### Size Limits

An overly long message increases bandwidth, allocation, storage cost, and ingestion latency, and may be truncated by the collector. If truncation is needed:

- Specify limits in **Unicode characters, UTF-16 code units, or UTF-8 bytes**, not vaguely as "max 1000 chars".
- Truncate **the value before serialization** or use an encoder with a safe strategy; do not slice an already-encoded JSON string in the middle of an escape sequence, surrogate pair, or multibyte UTF-8 character.
- If truncation occurs, consider a field such as `messageTruncated=true` so investigators know the content is incomplete.
- Do not store another full raw copy of the message elsewhere unless appropriate permissions and retention are in place.

Do not take `message` from untrusted data and use it as a metric label. It causes high cardinality and may contain personal content.

## 13. Schema Design: A `message` Field Should Have a Contract

A minimal contract for JSON logging can specify:

| Property | Recommendation |
| --- | --- |
| Field name | `message`, consistently lowercase across the system. |
| Type | Valid UTF-8 string when serialized; handle null/missing per policy. |
| Content | A sentence describing one event, not a dump of an entire object. |
| Default value | Do not silently fabricate "success" when `message` is missing. |
| Escaping | JSON serializer; verify quotes/backslashes/newlines/Unicode. |
| Event code | Separate `event` or `event.code` field per schema. |
| Dynamic attributes | Separate fields such as `orderId`, `elapsedMs`, `traceId`. |
| Exception | Separate error field or structure supported by the encoder. |
| Length limit | Defined policy and indicator when truncated. |
| Security | Allowlist/redaction before serialization; restrict access permissions. |
| Testing | JSON parses successfully and `message` has type string. |

**Schema compatibility:** when changing encoders, frameworks, or adding a structured `Message`, verify that `message` remains a string with the same semantics. Switching from "formatted message" to "raw template" can cause many dashboards to display `Order {} accepted` instead of the actual sentence, even though the JSON is still valid.

Some systems may choose to keep both:

```json
{"message":"Order O-17 accepted","messageTemplate":"Order {} accepted","orderId":"O-17"}
```

if the encoder and security policy support it. However, **do not manually write `messageTemplate` into the output just because it exists in the logging call**; verify that the backend provides it reliably and preserves parameters according to the defined schema.

## 14. How to Verify the `message` Field in Practice

### Producer-Level Checks

- Does the logger call actually execute?
- Does a level/filter drop the event before it reaches the appender/handler?
- Is the template formatted according to JUL or SLF4J/Log4j 2?
- Is the exception passed as a `Throwable` parameter rather than concatenated into a string?
- Does `message` contain tokens, PII, or unnecessary data?
- Can `message` be null/empty, and what policy is needed?

### Encoder-Level Checks

- Does the JSON object have the `message` field with the right name and type?
- Test inputs with `"`, `\`, CR, LF, tab, Unicode, and invalid surrogates.
- Does every record serialize as one object per line if using JSON Lines?
- If using Log4j 2 `JsonTemplateLayout`, does the `message` resolver set `stringified=true` when the schema requires a string?
- If using a Logback JSON encoder, does the provider/version output the right fields without dropping structured attributes?
- Are size limits, JSON escaping, and redaction enforced as required?

### Sink/Collector-Level Checks

- Do stdout/stderr, files, or network sinks actually receive the records?
- Does the collector parser read all JSON objects without splitting or merging them incorrectly?
- Does the system index `message` as a string and map other fields properly?
- Do newlines inside `message` forge a new record?
- Is data dropped due to async queues, oversized payloads, or backend errors?
- After ingestion, can `message` be queried alongside trace/correlation IDs?

**Do not treat "the application runs without exceptions" as proof that the JSON is valid or that logs reached the store.** Test an event with a known ID all the way through the pipeline to storage.

## 15. Test Matrix for the `message` Field

| Test Case | Input Data | What to Verify |
| --- | --- | --- |
| Normal message | `Order accepted` | Output string matches the exact content. |
| JUL template | `Order {0} accepted` + `O-17` | Output is formatted, with no remaining placeholder. |
| SLF4J template | `Order {} accepted` + `O-17` | Backend uses the SLF4J format properly. |
| Double quotes | `Invalid field "name"` | JSON string contains `\"` escape. |
| Backslash | `C:\logs` | JSON string contains `\\` escape. |
| Newline | Text with LF/CR | One event remains one physical line. |
| Tab/control char | Tab or U+0000 | Escaped according to JSON grammar. |
| Vietnamese with diacritics | `Đơn hàng đã được chấp nhận` | Valid UTF-8 parsing, no lost diacritics. |
| Empty message | `""` | Not silently treated as `null`. |
| Null/missing | null / absent field | Handled per schema; distinct from empty string. |
| ObjectMessage | `MapMessage` or custom `Message` | Does not unintentionally change field type. |
| Exception | `Throwable` with stack trace | Business message and technical error are clearly separated. |
| Sensitive data | Token/OTP in object | Redacted / not exposed in `message`. |
| Very long message | Exceeds collector limit | Clear truncation/size policy; JSON remains valid. |
| Async/multithreading | Multiple requests with trace IDs | No mixed contexts; events complete per policy. |
| End-to-end | Fixed event code and ID | Found in log storage with correct mapping. |

An important round-trip test:

```text
originalMessage
    -> JSON serialize
    -> JSON parse
    -> parsed["message"]
    == originalMessage
```

For valid Unicode strings without truncation/redaction, the parsed `message` must match the formatted message prior to serialization, including quotes, backslashes, and logical newlines. If redaction/truncation applies, **redefine the expected value** and include policy metadata.

## 16. Common Mistakes to Avoid

1. **Assuming `message` is the entire record.** A JSON event also has timestamp, level, logger, context, attributes, and exception fields.
2. **Writing a string sometimes and an object other times into `message`.** Storage with a strict schema can suffer mapping conflicts.
3. **Manually building `{"message":"..."}` via string concatenation.** Quotes and newlines break JSON and enable log injection.
4. **Putting every dynamic variable into `message` without separate fields.** Hard to filter, hard to aggregate, and easy to leak data.
5. **Using formatted messages as event codes or metric labels.** Messages vary and create high cardinality.
6. **Mixing up JUL `{0}` and SLF4J `{}` placeholders.** The `message` content is not formatted as expected.
7. **Calling `record.getMessage()` and assuming it is formatted text in every JUL Formatter.** Understand `formatMessage(record)`.
8. **Using a text `PatternLayout` and treating it as a safe JSON encoder.** Patterns do not automatically escape full JSON strings.
9. **Putting long stack traces and secrets into `message`.** Use dedicated error fields and redaction instead.
10. **Testing only JSON parsing without testing field types.** Valid JSON can still fail mapping or schema checks.
11. **Not checking files/stdout/collectors after changing layouts.** Producer execution does not prove ingestion succeeded.
12. **Assuming SLF4J fluent `addKeyValue` automatically appears in JSON regardless of backend.** Verify the encoder.
13. **Truncating encoded JSON output with `substring`.** Can cut in the middle of an escape or UTF-8 sequence, corrupting the JSON.
14. **Logging raw requests or `exception.toString()` unchecked.** Can expose tokens, sensitive URLs, or PII.
15. **Assuming an empty message is a missing message.** `""`, `null`, and absent are different.

## 17. Pre-Production Checklist

- [ ] The `message` field has a consistent string type, with a clear rule for empty/missing/null.
- [ ] Content accurately describes the event without asserting unverified outcomes.
- [ ] A stable `event` code and separate business fields exist when querying is needed.
- [ ] Templates are formatted correctly for the API (JUL/SLF4J/Log4j 2).
- [ ] The encoder produces valid JSON, escapes quotes/backslashes/control chars, and supports UTF-8.
- [ ] If using JSON Lines, each event occupies one physical line.
- [ ] Log4j 2 `JsonTemplateLayout` and Logback encoders conform to the collector's schema.
- [ ] Structured messages do not accidentally turn `message` into an object/array.
- [ ] Stack traces and error types are placed in clear fields and not lost when handling `Throwable`.
- [ ] Allowlisting/redaction is in place to prevent tokens, passwords, OTPs, cookies, and unnecessary PII.
- [ ] Size limits, truncation policies, and truncation markers are configured.
- [ ] Context/`traceId` propagates properly across thread pools or async pipelines.
- [ ] Unit tests cover escaping and round-trip JSON parsing.
- [ ] Integration tests send logs to the sink/collector/index and verify they can be queried back.
- [ ] Metrics monitor parse errors, dropped events, ingest lag, and schema conflicts.
- [ ] Output has been verified from the **actual deployed artifact**, not just when running code from an IDE.

## References

- [Java 17 — Formatter.formatMessage(LogRecord)](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Formatter.html)
- [Java 17 — LogRecord and parameters](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/LogRecord.html)
- [Apache Log4j 2 — JSON Template Layout, message resolver, and stringified](https://logging.apache.org/log4j/2.x/manual/json-template-layout.html)
- [Apache Log4j 2 — Layouts and PatternLayout](https://logging.apache.org/log4j/2.x/manual/layouts.html)
- [SLF4J Manual — Parameterized Logging and Fluent API](https://www.slf4j.org/manual.html)
- [Logback — Layouts](https://logback.qos.ch/manual/layouts.html)

**Takeaway:** In JSON logging, **`message` should be a readable description with a stable data type**, not a dumping ground for all application context or data. Separate event codes and queryable attributes, let a JSON encoder handle escaping, verify the schema against the actual sink, and keep sensitive data out of `message`.
