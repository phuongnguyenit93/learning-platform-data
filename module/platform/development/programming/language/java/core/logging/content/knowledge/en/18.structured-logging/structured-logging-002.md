# Key-value logs in Java Structured Logging

## 1. What is a key-value log?

A **key-value log** is a way of recording an event as **named fields (keys) and values**, rather than expressing all information in a free-form sentence. Within the **Structured logging** group of Java Core Logging, this is the foundational approach that allows logs to be reliably **filtered, grouped, aggregated, correlated, and searched** by machines.

Example of an order-accepted event:

~~~text
level=INFO event=order.accepted orderId=ORD-17 quantity=2 paid=true
~~~

The key–value pairs are:

| Key | Value | Meaning |
| --- | --- | --- |
| level | INFO | Logging level |
| event | order.accepted | Stable event code |
| orderId | ORD-17 | Order identifier |
| quantity | 2 | Item quantity |
| paid | true | Payment status |

The representation can be **key=value text**, a **JSON object**, or an internal event that keeps fields separate before an encoder writes out bytes. What matters is not merely having an **=** sign, but **whether the logging API, backend, encoder, and collector preserve field boundaries and data types**.

Example JSON representation with the same meaning:

~~~json
{"level":"INFO","event":"order.accepted","orderId":"ORD-17","quantity":2,"paid":true}
~~~

In this JSON, **quantity** is a number and **paid** is a boolean. If you merely write the string **quantity=2 paid=true** into a regular message, the backend/collector may not parse them as a number and a boolean. **True structured key-value logging** requires a consistent event-creation policy and encoder/parser.

## 2. Why are key-value logs better than free-form log strings?

Compare two log styles for the same event:

**Free-form string:**

~~~text
Order ORD-17 was accepted. Quantity was 2 and payment succeeded.
~~~

**Consistent key-value:**

~~~text
event=order.accepted orderId=ORD-17 quantity=2 outcome=SUCCESS
~~~

When a system has millions of records, free-form strings are hard to process if wording varies by developer, product version, or language. With key-value logs, a search system can apply structured conditions:

~~~text
event == "order.accepted"
AND outcome == "SUCCESS"
AND quantity >= 2
~~~

The snippet above is a **pseudo query** illustrating the idea, not the exact syntax of Elasticsearch, Loki, Cloud Logging, or any specific log platform.

**Key benefits:**

1. **Exact condition filtering:** filter by event, level, service, or reasonCode without writing regexes over sentences.
2. **Event correlation:** find all logs carrying a given requestId or jobId.
3. **Grouping and counting:** count retries by dependency or outcome across a log set.
4. **Decoupling data from wording:** the human-readable message can change while the event schema stays stable.
5. **Improved observability:** configure dashboards and alerts against known keys.
6. **Multilingual friendliness:** no need to parse descriptive sentences in Vietnamese or English.
7. **Type safety:** with the right encoder, durationMs is an integer and success is a boolean, not text.

**Key-value logging does not completely replace messages.** An event can still include a short **message** field to help humans understand it, while queryable information should live in dedicated fields.

## 3. Distinguishing text key-value, JSON, and structured events

There are three common levels:

| Approach | Example | Key point |
| --- | --- | --- |
| Manually concatenated message string | logger.info("orderId=" + id) | Looks like key=value, but is usually just a single String |
| Event with separate key-values in the API | addKeyValue("orderId", id) | The backend can receive per-field metadata |
| Schema-backed JSON output | {"orderId":"ORD-17","quantity":2} | The collector can parse into typed fields |

A string such as:

~~~text
event=order.accepted orderId=ORD-17 customer="Nguyễn An" quantity=2
~~~

is not **JSON**. If a text parser is properly configured, it can still be a useful key-value log. However, values containing **spaces, equals signs, quotation marks, newlines, or control characters** require consistent escaping/quoting rules; otherwise, the parser may split fields incorrectly.

JSON makes boundaries explicit:

~~~json
{
  "event": "order.accepted",
  "orderId": "ORD-17",
  "customer": "Nguyễn An",
  "quantity": 2,
  "success": true
}
~~~

**Simply printing curly braces does not make proper structured logging.** The JSON must be valid, each field must have a consistent meaning, and the collector must receive clear boundaries for each event.

## 4. How do event, message, context, and metadata differ?

A well-structured log record typically has three groups of information:

**A. Automatic logging system metadata**

- timestamp, level, loggerName
- threadName
- service, environment, instance, host
- error details or Throwable

**B. Event-specific fields**

- event, orderId, quantity
- outcome, reasonCode, durationMs
- retryAttempt, dependency

**C. Context carried across multiple events in a request/job**

- requestId, traceId, spanId
- tenantId if permitted by data policy
- jobId or workflowId

Example:

~~~json
{
  "timestamp": "2026-11-09T12:00:00Z",
  "level": "INFO",
  "service": "checkout",
  "event": "payment.authorized",
  "requestId": "req-42",
  "traceId": "trace-9a",
  "orderId": "ORD-17",
  "amountMinor": 159900,
  "currency": "VND",
  "outcome": "SUCCESS"
}
~~~

This is an **illustrative record**, not the output of running code. **amountMinor** represents the smallest currency unit chosen by the system; do not assume every currency has two decimal places. Include the unit in the field name or document it in the schema to avoid ambiguity.

**Event** is a stable code like `payment.authorized`. **Message** can be human-readable text like “Payment authorized”. **Context** links logs belonging to the same execution flow. Do not overload a single field with all three responsibilities.

## 5. Designing a good key-value schema

A schema is a shared agreement on **field names, value types, meanings, and presence policies**. You do not necessarily need a separate schema file for a small lesson, but multi-service projects should document their core fields.

A suggested set of field names:

| Key | Data type | Convention |
| --- | --- | --- |
| timestamp | Standardized date-time string | ISO 8601/RFC 3339, preferably UTC |
| level | Enum string | INFO, WARN, ERROR, or matching backend levels |
| service | String | Stable service name |
| environment | Enum string | dev, staging, prod per environment |
| event | Code string | order.accepted, inventory.retry |
| requestId | String | Identifier for a single request |
| traceId/spanId | String | Tracing system identifiers, if used |
| orderId | String | Preserves leading zeros and ID formatting |
| quantity | Integer | Do not convert arbitrarily to string |
| durationMs | Number | Duration in milliseconds |
| attempt | Integer | Attempt number |
| outcome | Enum string | SUCCESS, FAILURE, RETRY |
| reasonCode | Code string | Stable error code, not a stack trace |

### Naming principles

1. **Use one naming convention across services**: camelCase or snake_case, without varying by team.
2. **Make units explicit in field names**: durationMs, bytesSent, retryCount.
3. **Keep IDs as strings**, rather than forcing them into numbers that can drop leading zeros or exceed parser precision limits.
4. **Do not change types across versions**: `attempt` must not be `2` (number) today and `"2"` (string) tomorrow.
5. **Avoid duplicate keys** within the same JSON object; duplicate-handling rules vary across parsers.
6. **Define missing vs. null**: is an absent field different from a field present with a `null` value?
7. **Avoid unbounded dynamic keys**: key names must come from a controlled set. Never turn an email address or orderId into a field name.
8. **Use structured event names**, such as `noun.verb` or `domain.action`, and document when each event is emitted.
9. **Assign one meaning per key**. Do not use `status` for HTTP 200 in one place and order status in another.
10. **Separate human messages from machine data** so formatting or translation changes never break queries.

**Do not cram every field into every event.** Choose a stable core set plus fields specific to each event type. Too many inconsistent fields make the pipeline harder to use.

## 6. Using the right data types in JSON output

JSON supports **string, number, boolean, null, array, and object**. Do not convert everything to String just because a logging API accepts String.

Preferred example:

~~~json
{"event":"inventory.retry","attempt":3,"success":false,"elapsedMs":850}
~~~

Instead of:

~~~json
{"event":"inventory.retry","attempt":"3","success":"false","elapsedMs":"850"}
~~~

The second form is still valid JSON, but it forces parsers to cast types during analysis and easily breaks comparison conditions.

**Type considerations:**

- **BigDecimal/currency:** define a storage type and precision policy for JSON and your collector. You can use an integer minor unit paired with a currency field.
- **Very large numbers:** some collectors/parsers use IEEE 754 and cannot represent all 64-bit `long` values exactly; consider strings for IDs and counts beyond the safe integer range.
- **NaN/Infinity:** not valid JSON number literals; the encoder must handle them deliberately.
- **Enums:** use stable codes; avoid deriving values from exception messages.
- **Timestamps:** use a format with an explicit timezone; avoid mixing epoch seconds and epoch milliseconds.
- **Nested objects:** useful for grouping related data, though some collectors/index mappings limit nesting depth.
- **Arrays:** suitable for certain attributes; avoid overly large arrays in a single event.

A good key-value log requires both a **schema** and an **encoder/parser** that preserve the intended data types.

## 7. “Before and after” exercise: from text to key-value

Suppose you have legacy code:

~~~java
LOG.info("Accepted order " + orderId + " with quantity " + quantity);
~~~

This snippet assumes the variables are already declared. The sentence is easy to read, but filtering by quantity later is brittle if the wording changes.

An intermediate form using placeholders:

~~~java
LOG.info("Accepted orderId={} quantity={}", orderId, quantity);
~~~

This is **SLF4J/Log4j 2** syntax, not JUL's default syntax. It avoids string concatenation in many cases, yet **still does not guarantee that orderId and quantity become two structured fields**, because the backend may only output a formatted message string.

With **SLF4J 2.x fluent logging**:

~~~java
LOG.atInfo()
        .addKeyValue("event", "order.accepted")
        .addKeyValue("orderId", orderId)
        .addKeyValue("quantity", quantity)
        .log("Order accepted");
~~~

This snippet lives in a class with an `org.slf4j.Logger LOG`. The key-values are attached as event metadata. **How they are displayed or stored depends on the backend**; producing true JSON fields requires an encoder/layout that supports them.

**Do not confuse three different things:** naming variables inside a sentence, passing arguments to a message template, and adding distinct key-value metadata via the logging API.

## 8. Standalone Java 17+ example: emitting JSON key-value logs with JUL

To study the data structure **without dependencies outside the JDK**, this example uses:

- **java.util.logging.Logger** to emit LogRecords.
- **ConsoleHandler** to write to **System.err**.
- **LogRecord.setParameters(...)** to pass a Map containing each event's metadata.
- **A custom Formatter** that reads the Map and writes **one JSON object per line**.
- **LinkedHashMap** to preserve field order in the exercise for deterministic expected output.
- Minimal escaping rules for quotation marks, backslashes, and control characters.
- **Level.INFO** on the Handler so FINE records are not emitted.

**Scope note:** this is a **demo-specific convention**: JUL does not automatically turn `Object[]` parameters into a standard schema-backed structured key-value system. In production, you should generally use a battle-tested JSON encoder/library and a centrally managed logging backend; do not use this hand-rolled formatter for arbitrary object graphs.

### File StructuredKvDemo.java

~~~java
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.logging.ConsoleHandler;
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class StructuredKvDemo {
    private static final Logger LOG =
            Logger.getLogger("examples.logging.keyvalue");

    public static void main(String[] args) {
        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.ALL);

        ConsoleHandler console = new ConsoleHandler();
        console.setLevel(Level.INFO);
        console.setFormatter(new JsonLineFormatter());
        LOG.addHandler(console);

        try {
            Map<String, Object> order = new LinkedHashMap<>();
            order.put("orderId", "ORD-17");
            order.put("quantity", 2);
            order.put("paid", true);
            emit(Level.INFO, "order.accepted", order);

            Map<String, Object> retry = new LinkedHashMap<>();
            retry.put("orderId", "ORD-17");
            retry.put("attempt", 2);
            retry.put("reason", "stock \"slow\"");
            emit(Level.WARNING, "inventory.retry", retry);

            Map<String, Object> detail = new LinkedHashMap<>();
            detail.put("key", "ORD-17");
            emit(Level.FINE, "cache.hit", detail);
        } finally {
            LOG.removeHandler(console);
            console.close();
        }
    }

    private static void emit(
            Level level, String event, Map<String, Object> fields) {
        if (fields.containsKey("event")
                || fields.containsKey("level")) {
            throw new IllegalArgumentException(
                    "Reserved field: event or level");
        }

        LogRecord record = new LogRecord(level, event);
        record.setParameters(
                new Object[] { new LinkedHashMap<>(fields) });
        LOG.log(record);
    }

    private static final class JsonLineFormatter extends Formatter {
        @Override
        public String format(LogRecord record) {
            StringBuilder out = new StringBuilder();
            out.append("{\"level\":\"")
                    .append(escape(record.getLevel().getName()))
                    .append("\",\"event\":\"")
                    .append(escape(record.getMessage()))
                    .append('"');

            Object[] parameters = record.getParameters();
            if (parameters != null && parameters.length == 1
                    && parameters[0] instanceof Map<?, ?> fields) {
                for (Map.Entry<?, ?> field : fields.entrySet()) {
                    out.append(",\"")
                            .append(escape(String.valueOf(field.getKey())))
                            .append("\":");
                    appendValue(out, field.getValue());
                }
            }
            return out.append('}')
                    .append(System.lineSeparator())
                    .toString();
        }

        private static void appendValue(
                StringBuilder out, Object value) {
            if (value == null) {
                out.append("null");
            } else if (value instanceof Boolean
                    || value instanceof Byte
                    || value instanceof Short
                    || value instanceof Integer
                    || value instanceof Long) {
                out.append(value);
            } else {
                out.append('"')
                        .append(escape(String.valueOf(value)))
                        .append('"');
            }
        }

        private static String escape(String value) {
            StringBuilder out = new StringBuilder();
            for (int i = 0; i < value.length(); i++) {
                char ch = value.charAt(i);
                switch (ch) {
                    case '"' -> out.append("\\\"");
                    case '\\' -> out.append("\\\\");
                    case '\n' -> out.append("\\n");
                    case '\r' -> out.append("\\r");
                    case '\t' -> out.append("\\t");
                    default -> {
                        if (ch < 0x20) {
                            out.append("\\u00")
                                    .append(Character.forDigit(
                                            (ch >>> 4) & 0xF, 16))
                                    .append(Character.forDigit(
                                            ch & 0xF, 16));
                        } else {
                            out.append(ch);
                        }
                    }
                }
            }
            return out.toString();
        }
    }
}
~~~

### Compile and run

With JDK 17 or newer:

~~~bash
javac StructuredKvDemo.java
java StructuredKvDemo
~~~

**Two stderr lines from ConsoleHandler** (stdout has no output from the program):

~~~json
{"level":"INFO","event":"order.accepted","orderId":"ORD-17","quantity":2,"paid":true}
{"level":"WARNING","event":"inventory.retry","orderId":"ORD-17","attempt":2,"reason":"stock \"slow\""}
~~~

In format, this is **NDJSON/JSON Lines**: each line is an independent JSON object, not a single JSON array wrapping both lines. Physical line endings may vary across operating systems, but the logical content of the two lines is as shown above.

### Why exactly two lines are printed

1. **Logger Level.ALL** lets INFO, WARNING, and FINE LogRecords pass from the source.
2. **ConsoleHandler Level.INFO** drops FINE and keeps INFO and WARNING.
3. **setUseParentHandlers(false)** prevents parent Loggers with their own Handlers from writing duplicate copies.
4. **LinkedHashMap** preserves keys in `put()` insertion order, giving deterministic expected output.
5. **LogRecord.setParameters(...)** holds a Map object in the parameters array; this is a convention defined by the demo.
6. **JsonLineFormatter** outputs level/event first, followed by the Map fields.
7. **quantity=2 and paid=true** are emitted as a JSON number and boolean without quotation marks.
8. **reason** contains literal quotation marks, so `escape()` turns them into **\\"** in the JSON representation.
9. **ConsoleHandler** writes to **System.err** and flushes according to its own mechanism. The program does not use `println` to fake output.
10. **console.close()** flushes and closes the Handler without closing the JVM's `System.err`.
11. **FINE cache.hit** is not printed even though `emit()` was called, because the Handler is set to INFO.

**Careful check:** the explanation in item 8 about escaping describes the JSON display rule; in the output block, the two-character backslash-quote sequence appears as **\"**. When parsed as JSON, the `reason` value is restored to a string containing literal quotation marks.

### Limitations of the custom formatter

- Only **Boolean, Byte, Short, Integer, and Long** are preserved as numeric/boolean literals. Other types are serialized as strings.
- Nested objects, arrays, schema-aware BigDecimals, invalid Unicode surrogates, and Throwables are not handled.
- If you want to include a **timestamp**, you need a consistent timezone and precision format; the example omits it intentionally for easier verification.
- If you want to log an **exception** and its cause chain, you must design how to encode Throwable separately rather than relying on `message` alone.
- Do not put unbounded dynamic keys or PII into an uncontrolled Map.
- Do not treat **LogRecord parameters Map** as a standard JUL interoperability contract; it is only a demo mechanism for carrying metadata.

In production applications, use a **well-tested JSON encoder/layout** instead of manually building JSON with `StringBuilder` when you need to support arbitrary object types.

## 9. SLF4J 2.x: addKeyValue() for per-event metadata

**SLF4J** is the standard logging facade in Java. Since **SLF4J 2.0**, the fluent API supports **LoggingEventBuilder.addKeyValue(key, value)**.

Example:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class CheckoutService {
    private static final Logger LOG =
            LoggerFactory.getLogger(CheckoutService.class);

    public void accept(String orderId, int quantity) {
        LOG.atInfo()
                .addKeyValue("event", "order.accepted")
                .addKeyValue("orderId", orderId)
                .addKeyValue("quantity", quantity)
                .log("Order accepted");
    }
}
~~~

This is a **component class** that compiles when the project has `slf4j-api` 2.x; it has no `main()`, and the application needs **a compatible provider** at runtime to actually emit logs.

**Key points to remember:**

- **atInfo()** starts an INFO event builder; `addKeyValue(...)` attaches individual fields.
- **log(...)** is required to emit the event. If you forget to call **log()**, the builder emits nothing.
- When the log level is disabled, the API is designed to avoid unnecessary work.
- Java still evaluates argument expressions before invoking a method, unless you use a lazy/supplier form explicitly supported by the API.
- **Key-value data is kept separate at the API level**; the provider/backend decides how to represent it.
- **You do not automatically get JSON** just by calling `addKeyValue()`. For JSON output, choose an appropriate encoder/layout and configuration.
- You can use **addArgument(...)** for `{}` placeholders and **addKeyValue(...)** for named fields; they serve different purposes.
- An application on SLF4J 1.7 does not have the `atInfo()`/`addKeyValue()` methods of the 2.x API. Always verify the actual dependency version.

Example combining both a message and key–value pairs:

~~~java
LOG.atWarn()
        .addKeyValue("event", "inventory.retry")
        .addKeyValue("orderId", orderId)
        .addKeyValue("attempt", attempt)
        .log("Dependency retry");
~~~

This snippet assumes the variables are already declared. A text layout may render `key=value` before the message, but only the configured backend/encoder determines the exact output.

## 10. Logback: using %kvp to render key–value pairs

If your application uses **SLF4J 2.x + a compatible Logback version**, Logback's **PatternLayout** provides the **%kvp** conversion word for key–value pairs attached to a logging event.

Example **logback.xml**:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<configuration>
    <appender name="CONSOLE"
              class="ch.qos.logback.core.ConsoleAppender">
        <target>System.out</target>
        <encoder>
            <pattern>%d{yyyy-MM-dd HH:mm:ss.SSS} %-5level %logger %kvp - %msg%n</pattern>
            <charset>UTF-8</charset>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
    </root>
</configuration>
~~~

**Meaning:**

- **%kvp** renders the event's key-value pairs attached via the API.
- **%msg** is the human-readable message.
- **%logger** and **%level** are standard log metadata.
- **%n** is the platform-dependent line separator.
- **ConsoleAppender** writes to `System.out` because `<target>` is configured.
- Requires a Logback/provider version compatible with the SLF4J 2.x API; do not copy this XML into Log4j 2.
- Actual output includes timestamps and logger names, so it will not match the fixed strings from the Java 17 demo in Section 8.

Logback supports quoting options on the conversion word, such as **%kvp{NONE}**, **%kvp{SINGLE}**, and **%kvp{DOUBLE}**. Using **NONE** can make it hard for text parsers to handle values containing spaces or special characters.

Newer Logback versions also provide **%maskedKvp** in supported releases, but **masking at the encoder is no substitute for avoiding creating or logging secrets at the source**. Never rely on a filter/mask in one Appender to assume that other Appenders, queues, tracing, or debug dumps will never see sensitive data.

**Important note:** **%kvp is a text pattern**, not JSON with typed fields. If you want each key ingested as a properly typed JSON property, you must choose an appropriate JSON encoder and verify it with your collector. A numeric Java value may be formatted as text inside a pattern, so do not assume the parser will automatically treat it as a number.

## 11. Log4j 2: MapMessage, ThreadContext, and JSON Template Layout

Log4j 2 provides **Message** implementations and **ThreadContext** to carry structured data.

### MapMessage / StringMapMessage

Example using **StringMapMessage** from the Log4j API:

~~~java
import org.apache.logging.log4j.LogManager;
import org.apache.logging.log4j.Logger;
import org.apache.logging.log4j.message.StringMapMessage;

public class InventoryService {
    private static final Logger LOG =
            LogManager.getLogger(InventoryService.class);

    public void retry(String orderId, int attempt) {
        StringMapMessage event = new StringMapMessage()
                .with("event", "inventory.retry")
                .with("orderId", orderId)
                .with("attempt", String.valueOf(attempt));
        LOG.warn(event);
    }
}
~~~

This is a component class requiring the Log4j API and a backend at runtime. **StringMapMessage** models a Map with String values; the example converts `attempt` to a String. **That does not guarantee `attempt` will be output as a JSON number**; you must design your schema and layout accordingly. Log4j 2 offers other `MapMessage` variants with different formatting capabilities; check the API and backend you are using.

**MapMessage is not ThreadContext.** `MapMessage` describes data **for a single message/event**, whereas the ThreadContext Map typically carries fields for the **current execution context**, such as `requestId`.

### ThreadContext for requestId

~~~java
import org.apache.logging.log4j.CloseableThreadContext;

try (CloseableThreadContext.Instance ignored =
        CloseableThreadContext.put("requestId", requestId)) {
    LOG.info("event=inventory.retry");
}
~~~

This snippet runs inside a method that already has `LOG`/`requestId` and the Log4j API dependency. Context is only useful if the backend/layout includes those fields in the output.

In Log4j 2's **PatternLayout**:

- **%X{requestId}** reads from the Thread Context Map/MDC.
- **%K{orderId}** reads a key from a `MapMessage` when the message is an appropriate map type.
- **%msg** renders the message according to the chosen formatter.

Do not confuse **%X** and **%K**: they read from **two different data sources**.

### JSON Template Layout

Log4j 2 provides **JsonTemplateLayout** to encode LogEvents into JSON using a template. You must add the **log4j-layout-template-json** module compatible with your backend; it is not included automatically just because your app uses `log4j-api`.

Minimal **log4j2.xml** configuration example:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<Configuration>
    <Appenders>
        <Console name="JSON" target="SYSTEM_OUT">
            <JsonTemplateLayout/>
        </Console>
    </Appenders>
    <Loggers>
        <Root level="info">
            <AppenderRef ref="JSON"/>
        </Root>
    </Loggers>
</Configuration>
~~~

When the compatible module and backend are present, `JsonTemplateLayout` uses Log4j's default template (commonly ECS-based per current Log4j 2.x documentation). **The actual JSON shape differs from the output block in Section 8**; to control the schema, configure **eventTemplate/eventTemplateUri** and the necessary resolvers.

**Keep the roles distinct:** `MapMessage` is the **message data source**, `ThreadContext` is the **execution context**, and `JsonTemplateLayout` is the **output encoder**. To get a field end-to-end, verify that your template extracts data from all three places properly.

## 12. Per-event key-values vs. request-scoped MDC

An HTTP request might emit multiple events:

~~~text
requestId=req-42 event=order.validation.started
requestId=req-42 event=inventory.lookup attempt=1
requestId=req-42 event=order.accepted orderId=ORD-17
~~~

**requestId** is shared context. **event, attempt, and orderId** vary per event. In SLF4J, you use **MDC** (Mapped Diagnostic Context):

~~~java
import org.slf4j.MDC;

try (MDC.MDCCloseable ignored =
        MDC.putCloseable("requestId", requestId)) {
    LOG.atInfo()
            .addKeyValue("event", "order.accepted")
            .addKeyValue("orderId", orderId)
            .log("Order accepted");
}
~~~

This snippet requires SLF4J 2.x and pre-declared variables.

**Thread pool caveat:** MDC is typically bound to the current thread's context; **it does not automatically propagate across every Executor, CompletableFuture, virtual thread, or external service**. If request A leaves `requestId` on a thread that is later reused for request B, B's logs can be tagged with the wrong ID.

Rules:

1. Set MDC at the start boundary of a request/job once the context is available.
2. Clear MDC in a `finally` block or via a closeable scope.
3. When switching threads, use an explicit propagation mechanism and ensure cleanup on the target thread.
4. For async logging, ensure context is **snapshotted** onto the event at emission time, rather than reading the writer thread's ThreadLocal and mistaking it for the producer's context.
5. If using `traceId`/`spanId`, integrate proper tracing propagation instead of inventing ad-hoc IDs at each step.
6. Verify that your encoder actually outputs MDC fields; calling `MDC.put` alone is not enough.

## 13. Logging key-values for exceptions

An error log needs **structured event/metadata** while also preserving the **Throwable**.

SLF4J 2.x example:

~~~java
LOG.atError()
        .addKeyValue("event", "order.persist.failed")
        .addKeyValue("orderId", orderId)
        .addKeyValue("reasonCode", "STORAGE_UNAVAILABLE")
        .setCause(exception)
        .log("Order persistence failed");
~~~

This snippet assumes `LOG` is an SLF4J 2.x `Logger`, and `orderId` and `exception` are already declared.

**setCause(exception)** attaches the `Throwable` to the logging event; the backend/encoder must be configured to write the exception type, stack trace, and cause chain according to policy. Merely concatenating **exception.getMessage()** into a value like `reason="..."` usually loses the stack trace and root cause.

A production JSON record might look like:

~~~json
{
  "level": "ERROR",
  "event": "order.persist.failed",
  "orderId": "ORD-17",
  "reasonCode": "STORAGE_UNAVAILABLE",
  "exception": {
    "type": "java.lang.IllegalStateException",
    "message": "Storage unavailable"
  }
}
~~~

This is an **example schema**, not the automatic output of every backend. Stack traces and cause chains may be stored under different fields depending on the encoder.

**Avoid logging the same error at every layer:** logging ERROR in the repository, rethrowing and logging ERROR in the service, and logging ERROR again in the controller produces multiple events for a single failure. Pick a **handling boundary that knows the final outcome** to log the primary error, preserve the cause across lower layers, and only emit additional events when a significant retry or fallback occurs.

**Do not turn exception messages into reasonCode.** Error messages can change and may contain sensitive data. Use a dedicated, stable error code instead.

## 14. Key-value logging is not a metric

You can search and count from logs:

~~~text
event=inventory.retry dependency=stock attempt=2
~~~

However, you should not rely on high-volume detailed logs as the sole way to measure traffic or latency.

**Logs** are suited to answering “what specific events happened for this request/job?”. **Metrics** are suited to measuring distributions, error rates, throughput, or aggregate latency. **Traces** are suited to following execution paths across multiple services.

Common pitfalls:

- Putting **orderId, userId, or requestId** into **metric labels**, causing **high cardinality** and an explosion of time-series.
- Putting every ID into log fields can be useful for search, but you still must manage **index cardinality, ingest cost, and retention**.
- Turning **user values into key names**, such as creating a new field for each `userId`. This causes unbounded schema growth.
- Logging thousands of INFO events inside a loop just to count items, instead of using a metric or batch summary.

**Distinguish key cardinality from value cardinality:** keys should belong to a stable set of fields; values like `requestId` can have many unique values, so you should choose which fields are truly worth indexing or querying according to your log platform's policies.

## 15. Schema evolution: changing keys or types

When an application releases a new version, the logging schema acts as an interface consumed by dashboards, alerts, and queries.

Initial example:

~~~json
{"event":"request.completed","durationMs":120}
~~~

If a new version changes this to:

~~~json
{"event":"request.completed","duration":"120ms"}
~~~

a dashboard comparing **durationMs > 500** may silently stop working. It is far better to keep keys and types stable, or follow a clear migration plan.

Useful rules:

1. **Adding optional fields** is usually much safer for compatibility than renaming a core field.
2. **Never change a field's type** without updating parsers and index mappings.
3. **Never reuse a key name for a different meaning**.
4. **Add a schemaVersion** when an event format undergoes a breaking change.
5. **Document event names and required fields**, not just “what the logger prints”.
6. **Write snapshot/schema tests** for critical events; verify both old and new versions during rollouts.
7. **Watch out for null vs. absent** during transitions: some systems strip `null` fields automatically while others keep them.
8. **Standardize units for time, currency, and size** as well as timestamp formatting.
9. **Never let localization** alter `event` names or `reasonCode`. Localized text belongs in a separate `message` field.
10. When deprecating a field, update dashboards, alerts, ETL pipelines, and documentation together.

A log schema should be managed much like a data API: it needs compatibility guarantees, tests, and clear ownership.

## 16. Security, personal data, and log injection

Structured logging is not secure by default. In fact, key-value fields make data **easier to query**, so accidentally logging a secret can be even more dangerous than in hard-to-parse text logs.

**Data you should avoid logging:**

- Passwords, tokens, API keys, cookies, authorization headers.
- Card numbers, personal financial data, identity documents.
- Full payloads of sensitive requests or responses.
- PII unnecessary for diagnostics.
- SQL parameters or exception messages containing secrets.

**Key principles:**

1. **Data minimization:** log only the fields you need; do not dump entire objects and hope the encoder masks them.
2. **Tested redaction/masking:** if you must mask data, protect every destination (console, file, network), not just a single `PatternLayout`.
3. **Escape untrusted input:** newlines and control characters can forge log entries or break `key=value` formatting. Standard JSON encoders handle escaping, but you still need a schema policy.
4. **Never use user input as a key**: prevent arbitrary field structures or overwriting reserved system keys.
5. **Cap value lengths** for untrusted payloads to prevent log amplification and excessive storage consumption.
6. **Align access controls** across collectors, dashboards, archives, and backups.
7. **Set retention policies** per log type based on compliance and query needs.
8. **Ensure required audit logs** are not accidentally dropped by filters or sampling.
9. In multi-tenant systems, partitioning and access policies must prevent cross-tenant data leaks.
10. Do not assume all UUIDs/IDs are harmless; some IDs can still be linked back to individuals.

**Formatting note:** for text `key=value` logs, you must define explicit quoting and escaping rules. For example, a value like **Nguyễn An** contains a space and must be quoted as the parser expects; values containing **quotation marks** must also be escaped. Do not concatenate strings with spaces and assume the parser will extract them accurately.

## 17. Performance and reliability

Emitting extra metadata adds work for the application, though it can reduce downstream parsing costs. Points to evaluate:

- **Disabled levels:** the SLF4J fluent API minimizes work when a level is disabled, but expensive argument expressions are still evaluated by Java if you compute them eagerly before the call.
- **Allocation:** creating a new `Map` for every frequent event can increase memory/GC pressure. Use your backend's native structured logging support and benchmark hot paths.
- **Serialization:** the JSON encoder handles escaping, formatting, and type inspection; performance depends on the backend and schema.
- **Async logging:** reduces I/O blocking on business threads, but introduces queues, overflow policies, and shutdown/drain considerations.
- **Log volume:** logging every DEBUG step in production can drive up ingest and indexing costs; choose appropriate levels and sampling per event type.
- **Buffering/flushing:** writing JSON to the console does not mean the collector has durably persisted the log.
- **Event ordering:** concurrent producers can interleave logs; rely on `requestId`/`traceId` rather than inferring strict causal order from line position alone.
- **Mutable data:** never pass a mutable `Map` and modify it after enqueuing to an async backend; snapshot values at emission time.
- **Multiple Appenders/Handlers:** the same event can be written twice; verify additivity and routing rules.

**If an event is for auditing or transactions that must not be lost**, evaluate delivery and durability guarantees separately. Standard console/logging backends do not replace a transaction log or an integrity-preserving audit store.

## 18. Testing structured key-value logging

### A. Unit tests for schema

- The **order.accepted** event must contain **event, orderId, quantity, and paid**.
- **quantity** is a number and **paid** is a boolean after JSON parsing.
- **orderId** remains a String and preserves leading zeros.
- Required fields are not `null` if disallowed by the schema.
- There are no **duplicate keys** and no keys derived from user input.
- When values contain quotes, backslashes, newlines, or Unicode, the JSON remains valid and parses back accurately.
- No passwords, tokens, or sensitive payloads appear.
- Event names and `reasonCode` values are unaffected by UI locale settings.

### B. Integration tests through a real backend

- SLF4J 2.x has **a compatible provider** on the runtime classpath.
- Logback `PatternLayout` actually outputs **%kvp** when using text key-value format.
- With a JSON encoder, key-values are mapped into **properly typed JSON fields**, not just concatenated into the message string.
- With Log4j 2, verify that **MapMessage/ThreadContext** are extracted into the `JsonTemplateLayout` template as expected.
- Timestamps, levels, Throwables, and correlation IDs are accurate.
- ERROR logs include stack traces/causes without leaking secrets.
- When a logger level is blocked, the event is suppressed; when re-enabled, the full event is emitted.
- The collector receives one JSON object per event without breaking on embedded newlines.
- No duplicate output from multiple appenders or bridges.

### C. Concurrency and async tests

- Concurrent requests never mix up `requestId` values.
- MDC/ThreadContext is cleared after processing completes.
- Context propagation across `Executor`/`CompletableFuture` boundaries works as designed.
- Under a full queue or slow writer, the overflow policy behaves as expected.
- Graceful shutdown drains all required events.

For the Java 17 example in Section 8, you can redirect **stderr** to a file and parse each line with a standard JSON parser. Do not rely on plain string comparison when **schema and data types** matter: real JSON parsing catches duplicate keys, stringified numbers, and broken JSON escaping.

## 19. Troubleshooting: why aren't key-values becoming fields?

| Symptom | Common cause | Fix |
| --- | --- | --- |
| Log shows **orderId=...** but `orderId` field is not searchable | It is just a message String, or the collector is not parsing it | Use a structured event API and an appropriate JSON encoder/parser |
| SLF4J `addKeyValue` does not appear | Backend/layout drops key-values or provider is incompatible | Check provider version and `PatternLayout`/JSON encoder config |
| Forgot to call `.log()` on builder | The fluent event was never emitted | Always terminate the builder chain with `.log()` |
| Logback only shows `%msg` | Pattern is missing `%kvp` | Add `%kvp` or configure a supporting JSON encoder |
| JSON has `"quantity":"2"` | Value was stringified | Keep numbers typed in the event/encoder and check index mapping |
| A key has multiple unexpected values | Duplicate key names or unstable schema | Enforce clear duplicate-key rules |
| MDC `requestId` is missing | Backend layout does not read MDC or context was not set | Configure `%X`/encoder and verify MDC scope |
| `requestId` from request A appears in B | Thread pool reuse without clearing MDC | Close/clear in `finally` and propagate explicitly |
| Log4j `MapMessage` lacks expected fields | Template/layout does not read `MapMessage` as expected | Check the message resolver and template configuration |
| Invalid JSON output | Manual string concatenation with bad escaping/control chars | Use a standard JSON encoder/serializer |
| Garbled Vietnamese characters | Charset mismatch across writer, collector, or viewer | Enforce UTF-8 end-to-end |
| Dashboards break after deploy | Key name or data type changed | Manage schema evolution and add contract tests |
| Indexing costs spike | Too many fields or high-cardinality values | Control schema, indexing rules, and retention |
| Exception lacks stack trace | Only `exception.getMessage()` was logged or encoder drops `Throwable` | Pass the `Throwable` and test the cause chain |
| Log leaks a token | Raw payload or secret was logged | Minimize data at the source, redact, and restrict access |
| Event appears twice | Multiple `AppenderRef`s, providers, or collector inputs | Check routing and additivity |
| Logs missing on platform | `stdout`/`stderr` not collected or collector error | Verify the pipeline end-to-end |

**Diagnostic order:** identify the emitting API → provider/backend → layout/encoder → stdout/stderr/file → collector/parser → schema/index/search query. Never look at an equals sign in a message and assume you have structured logging.

## 20. Common design mistakes

**Mistake 1 — Concatenating `key=value` manually and assuming the log has separate metadata.** If the backend only sees a String, the collector has to parse text. Use logging event metadata and a proper encoder when you need typed fields.

**Mistake 2 — Using a different key name each time.** `order_id`, `orderId`, and `orderID` make dashboards painful to maintain. Standardize on one schema.

**Mistake 3 — Using dynamic values as keys.** Creating a new field name per `requestId` causes schema and index-mapping explosions. Put `requestId` as the **value** of a fixed key.

**Mistake 4 — Converting numbers to strings.** Conditions like `quantity > 10` become unreliable if the parser treats `quantity` as text. Preserve data types all the way to the final output.

**Mistake 5 — Putting everything into MDC.** MDC is for request-scoped context; event-specific values like `quantity`, `attempt`, and `outcome` belong on the event itself.

**Mistake 6 — Failing to clear MDC in thread pools.** Request context can leak onto unrelated requests.

**Mistake 7 — Using free-form messages instead of event codes.** Messages change with language and releases; event codes should remain stable.

**Mistake 8 — Logging entire objects.** Calling `toString()` can burn CPU, expose sensitive data, and break formatting or types.

**Mistake 9 — Dropping the Throwable.** Logging only the exception message loses the stack trace and cause chain, making debugging much harder.

**Mistake 10 — Assuming all JSON has the same structure.** Valid JSON does not guarantee the right schema or that the template extracts all metadata.

**Mistake 11 — Not verifying the collector.** Even if the backend emits proper key-values, the collector might store the entire line as a single message string.

**Mistake 12 — Neglecting retention and read permissions.** Structured fields are easy to query, which amplifies the impact of leaked secrets or PII.

## 21. Checklist for adopting key-value logging in Java applications

1. **Define the goal:** terminal readability, field search, aggregation, alerting, or correlation?
2. **Define a schema** covering `event`, `timestamp`, `level`, `service`, and key business fields.
3. **Standardize names and types**, including explicit units for `durationMs`, bytes, and currency.
4. **Choose the right logging API:** SLF4J 2.x `addKeyValue`, Log4j `MapMessage`/`ThreadContext`, or a custom/JUL approach when justified.
5. **Select a real backend/provider** and an encoder/layout that preserves the required metadata.
6. **Pick an output format:** `key=value` text with a well-defined parser, or schema-backed JSON/NDJSON.
7. **Separate event fields from request context** such as `requestId`/`traceId`, and manage the MDC lifecycle properly.
8. **Preserve Throwables and cause chains** for errors, and avoid duplicate logging across layers.
9. **Exclude secrets and sensitive data**, escape untrusted input, and bound field sizes.
10. **Control cardinality and log volume**; do not use `userId`/`orderId` as key names or metric labels arbitrarily.
11. **Test parsed data types**, not just text appearance.
12. **Test the entire pipeline** from `Logger` to collector, dashboard, and alerts.
13. **Manage schema evolution** when changing names, types, or semantics.
14. **Evaluate throughput, async behavior, queues, and retention** under production load.
15. **Document the event catalog** so developers and operators share the same conventions.

**Conclusion:** **Key-value logging** transforms a log record from a hard-to-parse sentence into a set of named, typed fields. Its real value lies not in adding an **=** sign, but in **attaching data to logging events properly, maintaining a consistent schema, encoding safely, and verifying that the collector parses them into real fields**.

## 22. Official references

- [SLF4J User Manual — Fluent Logging API](https://www.slf4j.org/manual.html): `atInfo()`, `addKeyValue()`, `addArgument()`, and providers.
- [Logback — Layouts](https://logback.qos.ch/manual/layouts.html): `%kvp`, `%maskedKvp`, and MDC in `PatternLayout`.
- [Apache Log4j 2 — Messages](https://logging.apache.org/log4j/2.x/manual/messages.html): `MapMessage`, `StringMapMessage`, and `StructuredDataMessage`.
- [Apache Log4j 2 — Thread Context](https://logging.apache.org/log4j/2.x/manual/thread-context.html): `ThreadContext` Map, `CloseableThreadContext`, and propagation.
- [Apache Log4j 2 — JSON Template Layout](https://logging.apache.org/log4j/2.x/manual/json-template-layout.html): template-based JSON encoding, resolvers, and additional modules.
- [Oracle Java 17 — Logger](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Logger.html): emitting `LogRecord`s, parameters, and `Throwable`s.
- [Oracle Java 17 — LogRecord](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/LogRecord.html): log event metadata in JUL.
- [Oracle Java 17 — ConsoleHandler](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/ConsoleHandler.html): writing logs to `System.err` and Handler lifecycle.
