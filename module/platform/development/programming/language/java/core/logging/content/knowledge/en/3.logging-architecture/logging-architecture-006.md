# The Formatter and Layout Layer in Java Logging Architecture

## 1. What problem does a formatter/layout solve?

An application calls a logger to **emit an event**: "order ORD-7 submitted", "database connection failed". However, to make that event readable on a terminal, in a file, or in a log search system, you need to decide **how each record will be represented**.

The same event can appear in different presentation formats:

```text
INFO | OrderService | order ORD-7 submitted
```

```text
2026-11-09T08:15:03.125Z INFO  [worker-1] OrderService - order ORD-7 submitted
```

```json
{"timestamp":"2026-11-09T08:15:03.125Z","level":"INFO","logger":"OrderService","thread":"worker-1","event":"order_submitted","orderId":"ORD-7"}
```

The three lines above are **formatting examples**, not three runs of the same code snippet. The business event can be identical; the output changes depending on the formatter, available data fields, and configuration.

A **formatter** or **layout** is the component that takes a log event object and converts it into an appropriate output representation, typically a string or data that can be encoded into bytes. It determines field order, delimiters, timestamp formatting, messages, exceptions, and line endings. This layer separates two concerns:

- **What does the application say happened?** Creating a log record/event with level, message, exception, and context.
- **How will readers or tools see it?** Consistent text, pattern, or JSON formatting.

A good formatter makes logs easy to read, query, and correlate across components. However, a formatter **does not create information that is not already in the event**; for instance, it cannot know a `requestId` on its own if the application code or logging system has not provided it.

## 2. Position in the logging pipeline

Conceptual model:

```text
Application code
    |
    v
Logger / logging API
    | Creates events, evaluates levels and filtering rules
    v
Handler / Appender
    | Selects destination and controls writing
    v
Formatter / Layout (+ Encoder if present)
    | Formats into strings / bytes
    v
Console / File / Collector / Log ingestion system
```

This diagram is a logical view. In real implementations, **the handler/appender often actively invokes the formatter, layout, or encoder during writing**; not every library has a single separate intermediate class or an exact physical sequence matching the diagram. With asynchronous appenders, formatting may happen on a queue-processing thread after the event is created.

In common Java Logging architectures:

| Ecosystem | Event object | Destination writer component | Formatting component |
|---|---|---|---|
| `java.util.logging` (JUL, JDK) | `LogRecord` | `Handler` such as `ConsoleHandler`, `FileHandler` | `java.util.logging.Formatter` |
| SLF4J + Logback | Logback event, e.g., `ILoggingEvent` | `Appender` | `Layout` and usually `Encoder`, e.g., `PatternLayoutEncoder` |
| Log4j 2 | `LogEvent` | `Appender` | `Layout`, e.g., `PatternLayout` |
| SLF4J API itself | Logging call interface | Handled by the provider/backend | Does not define a single shared formatter/layout |

**Distinguishing the three responsibilities:**

- **Logger:** interface for emitting events; can decide which levels are enabled.
- **Handler/appender:** delivers events to the destination and may apply additional filters or delivery policies.
- **Formatter/layout/encoder:** transforms an event into its final representation. `Layout` describes how it is presented; in Logback, `Encoder` also converts data into bytes for the appender to write to a stream.

For example, switching a formatter from text to JSON **does not mean** changing log levels, changing the output destination, enabling long-term storage, or guaranteeing zero lost records.

## 3. Input data for the formatting layer

A log event typically already contains or provides access to the following fields:

| Field | Illustrative value | Meaning when formatting |
|---|---|---|
| Timestamp | `2026-11-09T08:15:03.125Z` | Identifies when the event occurred; determines timezone and precision |
| Level | `INFO`, `WARNING`, `SEVERE` | Filters and highlights severity |
| Logger name | `com.example.OrderService` | Identifies where the event originated |
| Message/parameters | `"order {0} submitted"`, `["ORD-7"]` | Produces the interpolated message when needed |
| Throwable | `IllegalStateException` | Displays error type, message, and stack trace |
| Thread/context | `worker-1`, `requestId=req-42` | Supports tracing by thread or request |
| Additional attributes | `traceId`, `orderId`, marker | Creates structured fields for search systems |

Actual fields depend on the API/backend. For example, JUL `LogRecord` has level, logger name, message, parameters, timestamp, and throwable; whereas MDC (Mapped Diagnostic Context) is commonly used with SLF4J/Logback/Log4j 2 and **is not a built-in property of `LogRecord` in JUL**.

A formatter must define how missing fields are handled: leave empty, omit the key, use a default value, or display a placeholder marker. Do not assume every event has a stack trace or correlation ID.

## 4. JUL: `java.util.logging.Formatter` and `LogRecord`

With built-in JDK logging, the abstract class `Formatter` provides the extension point for converting a `LogRecord` into text. Key APIs:

- `String format(LogRecord record)`: required method when creating a concrete formatter; returns the entire text written for the record.
- `String formatMessage(LogRecord record)`: helps handle resource bundles and message parameters according to JUL rules. If you call `record.getMessage()` directly, you may only get the template such as `order {0} submitted`.
- `getHead(Handler handler)` and `getTail(Handler handler)`: can provide headers/footers when a handler outputs a sequence of records as a structured document, such as XML. For typical single-line logs, overriding these is usually unnecessary.

Some commonly used data from `LogRecord`:

```java
record.getLevel();
record.getLoggerName();
record.getInstant();      // Instant since JDK 9+
record.getMessage();
record.getParameters();
record.getThrown();
```

The lines above **only illustrate the API**, not a standalone program. For timestamps, prefer explicitly including the timezone (usually UTC) and a format recognizable by parsers; do not output local time without declaring the time zone.

### 4.1. Standalone Java 17+ example

The following example creates a single-line formatter per event and appends a cause line when an exception is present. The code intentionally omits timestamps so that the output is deterministic and easy to compare; real systems should include timestamps, correlation IDs, and a stack trace policy.

Save as `FormatterLayoutDemo.java`:

```java
import java.util.logging.ConsoleHandler;
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class FormatterLayoutDemo {
    private static final Logger LOG =
            Logger.getLogger(FormatterLayoutDemo.class.getName());

    public static void main(String[] args) {
        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.ALL);

        ConsoleHandler console = new ConsoleHandler();
        console.setLevel(Level.ALL);
        console.setFormatter(new ReadableFormatter());
        LOG.addHandler(console);

        LOG.log(Level.INFO,
                "order {0} submitted", new Object[]{"ORD-7"});

        try {
            throw new IllegalStateException("inventory offline");
        } catch (IllegalStateException error) {
            LOG.log(Level.SEVERE, "order ORD-7 failed", error);
        }

        console.flush();
    }

    private static final class ReadableFormatter extends Formatter {
        @Override
        public String format(LogRecord record) {
            String message = oneLine(formatMessage(record));

            String text = record.getLevel().getName()
                    + " | " + record.getLoggerName()
                    + " | " + message + System.lineSeparator();

            Throwable error = record.getThrown();
            if (error != null) {
                text += "cause=" + error.getClass().getSimpleName()
                        + ": " + oneLine(error.getMessage())
                        + System.lineSeparator();
            }
            return text;
        }

        private String oneLine(String value) {
            if (value == null) {
                return "";
            }
            return value.replace("\r", "\\r")
                    .replace("\n", "\\n");
        }
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac FormatterLayoutDemo.java
java FormatterLayoutDemo
```

The output consists of these exact lines; JUL's `ConsoleHandler` writes to **`System.err`** by default, so this is console output on the `stderr` stream, not `stdout`:

```text
INFO | FormatterLayoutDemo | order ORD-7 submitted
SEVERE | FormatterLayoutDemo | order ORD-7 failed
cause=IllegalStateException: inventory offline
```

**Why does it produce this output?**

1. `LOG.log(Level.INFO, "order {0} submitted", new Object[]{"ORD-7"})` creates a `LogRecord` carrying the template and parameter. `formatMessage(record)` produces the text `order ORD-7 submitted`.
2. `getLevel().getName()` provides `INFO` or `SEVERE`, and `getLoggerName()` provides `FormatterLayoutDemo`.
3. `System.lineSeparator()` terminates a record on the current operating system. The difference between LF and CRLF does not change the displayed content of each line.
4. For the error event, `record.getThrown()` holds the exception. The example formatter prints only the class name and message to keep the output predictable; **this is not how to preserve full stack traces in production**.
5. `LOG.setUseParentHandlers(false)` prevents the same event from also passing through parent logger handlers in the demo program. This is a JUL-specific setting, not a universal fix for duplicate logs in other backends.

The logging mechanism continues to work if `ReadableFormatter` is replaced with another formatter. The event-emitting code does not need to know whether the output uses `|` delimiters, timestamps, or JSON.

### 4.2. Preserving exception details in a real formatter

A custom formatter can easily **lose the stack trace** if it only uses `record.getThrown().getMessage()`. To preserve the full exception trace, you can convert the `Throwable` to text using `StringWriter` and `PrintWriter`, then append it to the record. The following snippet is **an illustration inside `format(LogRecord)`**, not a standalone program:

```java
if (record.getThrown() != null) {
    java.io.StringWriter buffer = new java.io.StringWriter();
    java.io.PrintWriter writer = new java.io.PrintWriter(buffer);
    record.getThrown().printStackTrace(writer);
    writer.flush();
    text += buffer.toString();
}
```

With multi-line formats, ensure your log collector understands that the stack trace belongs to the same event; otherwise, each line of the stack trace may be split into a separate record. Dedicated formatters or JSON encoders with a dedicated exception field usually solve this better than manual string concatenation.

### 4.3. Built-in formatters in JUL

JUL provides common built-in implementations:

- `SimpleFormatter`: human-readable text output, typically including level, message, and source information; the format can be customized via the `java.util.logging.SimpleFormatter.format` configuration property.
- `XMLFormatter`: produces an XML representation for records, useful when structured XML output is needed. Handlers supporting headers/footers participate in forming a valid document.
- `ConsoleHandler` and `FileHandler`: **handlers**, not formatters; they choose the output destination and delegate to a formatter. Changing the handler or changing the formatter are two separate decisions.

Even when using built-in formatters, you still need to verify encoding, output destination, write permissions, log rotation, and how the ingestion system receives logs. Those concerns lie outside the responsibility of converting a record into text.

## 5. Logback: How do Layout and Encoder work together?

When an application calls SLF4J and uses Logback as the backend, the typical model is:

```text
SLF4J call
   -> Logback event
   -> Appender
   -> Encoder (may use a Layout)
   -> Byte stream / log destination
```

A **layout** produces a readable representation from an event; an **encoder** is responsible for encoding that representation into bytes for the appender to write. With Logback, `PatternLayoutEncoder` is the standard choice for text because it combines pattern layout with encoder functionality. Do not confuse `java.util.logging.Formatter` with Logback's interfaces/classes; they belong to different ecosystems.

### 5.1. Pattern layout

A pattern determines which fields appear and in what order. Some common conversion words in Logback:

| Pattern | Meaning |
|---|---|
| `%d{yyyy-MM-dd HH:mm:ss.SSS}` | Timestamp matching the pattern |
| `%-5level` | Left-aligned level, minimum width of 5 characters |
| `%thread` or `%t` | Thread name |
| `%logger{36}` | Logger name, abbreviated to a target length if needed |
| `%msg` or `%m` | Formatted message |
| `%X{traceId}` | MDC value for the key `traceId`, if set |
| `%ex` | Throwable/stack trace information |
| `%n` | Platform-appropriate newline character |

These are **Logback** specifiers; do not copy this pattern directly into a `java.util.logging.Formatter`.

### 5.2. Sample Logback configuration

When the application **already has Logback on the classpath**, you can place `src/main/resources/logback.xml`:

```xml
<configuration>
    <appender name="CONSOLE"
              class="ch.qos.logback.core.ConsoleAppender">
        <encoder class="ch.qos.logback.classic.encoder.PatternLayoutEncoder">
            <charset>UTF-8</charset>
            <pattern>%d{yyyy-MM-dd HH:mm:ss.SSS} %-5level [%thread] %logger{36} traceId=%X{traceId} - %msg%n%ex</pattern>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
    </root>
</configuration>
```

This file is a **framework configuration**, not a standalone Java program, and cannot be run with `javac` alone. It controls text formatting for the console appender:

- `%d` outputs the timestamp; specify a timezone when comparing across multiple servers, otherwise it depends on the environment/backend time configuration.
- `%-5level` makes the level column easy to scan visually.
- `%X{traceId}` reads from MDC and **does not generate a trace ID automatically**. If MDC has not been set or propagated to asynchronous threads, this value may be empty.
- `%msg%n` outputs the message and ends the line.
- `%ex` prints the throwable when present; stack traces can span multiple lines and require multiline aggregation in the collector.

To use MDC responsibly, the application must populate values within the appropriate execution scope and clear the context once finished. A request on a thread pool must never accidentally "inherit" the identifier of a previous request.

### 5.3. Log4j 2 also has Layout, with its own configuration

In Log4j 2, appenders typically use `PatternLayout` or structured data layouts. Although some placeholders look similar to Logback (`%d`, `%p`, `%m`, `%n`, `%X`), **do not assume all specifiers, options, or configuration files are one-to-one compatible**. Log4j 2 has its own layout definitions and registration mechanisms. Always consult the documentation for the exact backend version before copying configurations between Logback and Log4j 2.

SLF4J acts only as an API/facade on the application side; switching the provider/backend can completely change the supported appender and formatter/layout types.

## 6. Text, pattern, and structured logging formats

### 6.1. Text or pattern: for human readers

A consistent text layout can produce:

```text
2026-11-09 15:15:03.125 INFO  [http-17] OrderService traceId=trace-7 - Order accepted
```

Pros: easy to read directly during development or with `tail`. Cons: parsers may have to rely on spaces, `|` delimiters, regex, or escaping rules; messages containing newlines or special characters can easily break the structure.

### 6.2. JSON: for machine parsing

A JSON encoder/layout can output one object per event:

```json
{"timestamp":"2026-11-09T08:15:03.125Z","level":"INFO","logger":"OrderService","thread":"http-17","traceId":"trace-7","event":"order_accepted","orderId":"ORD-7","message":"Order accepted"}
```

This is **illustrative output**, not the automatic format of JUL or every Logback/Log4j 2 setup.

JSON has the advantage of clearly named fields that are easy to filter, group, and aggregate. However, JSON is truly useful only when:

- You maintain a **consistent schema** (e.g., `timestamp`, `level`, `logger`, `traceId`) with uniform data types and timestamp formats.
- You properly escape double quotes, backslashes, control characters, and newlines; use a reliable encoder/serializer rather than manually concatenating JSON strings.
- You define how `Throwable`, stack traces, exception types, messages, and nested cause stacks are represented.
- You manage custom fields to avoid key collisions, oversized payloads, or dumping unnecessary objects into logs.
- You choose clear timestamp and Unicode policies, typically ISO 8601 in UTC and UTF-8.

**Structured formatting does not equal reliable storage.** Collectors can still drop events, write slowly, enforce size limits, or apply data retention policies.

### 6.3. Distinguishing message templates from rendered strings

Before formatting, a log call may contain a **message template + parameters**, such as `"order {0} submitted"` and `"ORD-7"` in JUL, or `{}` placeholders in some other APIs. During rendering, the formatter produces the concrete text. Structured logging can preserve the template, parameters, and named fields if the backend supports it.

Do not assume SLF4J's `{}` works in `java.util.logging.Formatter.formatMessage`: JUL typically uses `MessageFormat`-compatible parameter syntax such as `{0}`. Parameter syntax belongs to the API, not to a universal specification across all logging libraries.

## 7. Designing safe and useful formatters/layouts

### 7.1. Keep the schema stable with sufficient context

Choose fields based on real investigation needs: timestamp, level, logger, message, exception, request/trace ID, and a few essential business keys. Do not attempt to dump the entire program state into every record.

If multiple services send logs to the same collector, standardize key names and timezones. For example, if service A uses `requestId` while service B uses `request_id` without a normalization rule, querying becomes much harder.

### 7.2. Protect data and prevent log injection

Messages, parameters, or exceptions may contain external input. When written into text logs, newline characters or control characters can make one line of input look like multiple separate events. Escape or normalize them when necessary, and use a properly escaping JSON encoder when outputting JSON.

However, changing the format alone **does not guarantee secrets are hidden**. Never log access tokens, passwords, card data, access keys, or unnecessary personal information at the source. If masking/redaction is used, verify it across messages, parameters, MDC, and exceptions.

### 7.3. Preserve exceptions and traceability

An exception may include a class, message, stack trace, cause chain, and suppressed exceptions. A layout that only prints `error.getMessage()` discards crucial evidence. Decide when to log full stack traces, when to log only summaries, and avoid logging the same error repeatedly at every layer.

In asynchronous systems, ensure context data such as MDC is properly captured/propagated before the original thread finishes or clears its context. A formatter only reads what the event currently holds; it cannot recover fields lost during thread handoffs.

### 7.4. Control performance

Formatting timestamps, stack traces, JSON serialization, and large objects all consume CPU and memory. Only fully process events that are actually selected for writing; use message template APIs or lazy evaluation where appropriate.

Do not put network calls, database queries, or heavy computations inside `Formatter.format`. The formatting component may be invoked very frequently, including under high application load. With asynchronous logging, queue organization and when data is snapshotted also affect consistency.

### 7.5. Newlines and timestamps

- **Newline:** omitting `%n` or `System.lineSeparator()` can cause events to merge together. Multi-line exceptions require collector multiline support or emission as a single structured event.
- **Timestamp:** determine whether the timestamp is captured at event creation time or when the backend actually writes it. If a queue backs up, these two times will differ.
- **Timezone:** prefer UTC or include an explicit offset; do not compare local date-times without timezones across machines.
- **Precision:** do not fabricate microsecond or nanosecond precision if the data source and backend only provide lower precision.

## 8. Common errors when configuring the formatting layer

| Symptom | Possible cause | How to check |
|---|---|---|
| Logs appear in default format | Config file not loaded, or appender/handler not attached to the expected layout | Check the active backend, loaded config file, and which handler receives the events |
| Unsubstituted `{0}` in JUL | Formatter calls `getMessage()` or the event has no parameters | Use `formatMessage(record)` and inspect the logger call |
| Empty `traceId` | MDC not set/propagated or key name mismatch | Check the context on the same thread and at event creation time |
| Missing stack trace | Formatter ignores `getThrown()`, layout omits throwable, or exception was not passed | Verify the logger call and the throwable converter configuration |
| Log lines run together | Missing line-ending character | Use `%n` or `System.lineSeparator()` as appropriate |
| Unintended duplicate logs | Event passes through multiple handlers/appenders or propagates to parent loggers | Check handler/appender configuration and inheritance/additivity settings |
| Unparseable JSON lines | Manual string concatenation with bad escaping or non-JSON text mixed in | Use a standard serializer/encoder and validate output with a JSON parser |
| Skewed timestamps | Inconsistent timezone/timestamp configuration or clock drift | Log explicit UTC/offset and check clock synchronization |

Do not try to fix "missing logs" by immediately changing the formatter: first check whether the logger emits the event, whether levels/filters drop it, and whether the appender/handler writes to the expected destination. If **the event never reaches the formatting layer**, no layout—however well designed—can output it.

## 9. Self-check checklist after changing a formatter/layout

1. **All expected events:** logs at enabled levels appear without duplicates and without altering business behavior.
2. **Accurate content:** message templates render as expected; exception data and key context are not dropped.
3. **Valid structure:** each event is clearly delimited; JSON parses cleanly; parsers/collectors receive the right fields and data types.
4. **Consistent time:** timezone, offset, and precision are consistent across services.
5. **Secure output:** no secrets are exposed, and input cannot break structure or spoof records.
6. **Acceptable performance:** formatting handles expected load without generating excessive data or wasteful processing.
7. **Operational readiness:** destination, rotation, retention, permissions, and collection mechanisms are verified at the **output layer**, rather than assuming the layout handles them.

A formatter/layout is the **presentation layer of a log event**. A logger can emit the same kind of event across many environments; by separating the formatting layer, an application can choose human-readable text during development and a stable structure for centralized collection in production while keeping the event-emitting code consistent.
