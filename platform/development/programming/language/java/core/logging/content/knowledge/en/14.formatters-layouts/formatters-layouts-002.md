# What is a Layout in Java Logging?

A **Layout** is the component that determines **how a log event is represented when written out**. When an application logs `logger.info("Order {} accepted", orderId)`, the logging system typically has an event containing the level, timestamp, logger name, thread, message, exception, and request context. The layout selects which data is displayed, its order, delimiters, and format style: a human-readable line of text, structured JSON, or another representation.

A layout is **not where you decide whether a business operation succeeded**, nor is it where you primarily decide whether an event should be created. Levels and filters participate in selecting events, and appenders/handlers decide the output destination; the layout turns the event into content to send to that destination. In Java, the specific API names differ: **JUL uses `Formatter`**, **Logback has `Layout` combined with `Encoder`**, and **Log4j 2 has `Layout`** configured inside an appender. The three ecosystems serve a similar purpose but do not share the same classes or configuration syntax.

## 1. The Big Picture: From Logger Call to a Log Line

```text
Java application
    |
    | logger.info("event=order.accepted orderId={}", orderId)
    v
Logger / logging API
    |
    +-- effective level, filter? --> May be skipped
    |
    v
Logging event / LogRecord
    |  level, timestamp, logger, thread, message,
    |  Throwable, context (if any)
    v
Appender / Handler
    |  target sink level/filter
    v
Layout / Formatter / Encoder
    |  produce formatted text or bytes
    v
stdout, stderr, file, collector, or other sink
```

This diagram illustrates responsibilities for learning purposes; the internal order of filters, layouts, and encoders depends on the framework and should not be treated as the exact algorithm for every implementation.

Example of an event with the following information:

```text
timestamp = 2026-03-05T08:20:10.123Z
level     = INFO
logger    = com.example.orders.OrderService
thread    = http-worker-2
event     = order.accepted
orderId   = ord-42
requestId = req-17
```

A **text layout** might turn the event into:

```text
2026-03-05T08:20:10.123Z INFO [http-worker-2] OrderService requestId=req-17 - event=order.accepted orderId=ord-42
```

A **JSON layout** might represent the same meaning as:

```json
{"timestamp":"2026-03-05T08:20:10.123Z","level":"INFO","logger":"com.example.orders.OrderService","thread":"http-worker-2","requestId":"req-17","event":"order.accepted","orderId":"ord-42"}
```

This is **static illustrative data**, not the output of a program below. The event content and which fields actually appear depend on the API, logging backend, layout/encoder, and whether the application attaches context/structured attributes properly. Changing the layout does not automatically turn a message string containing `orderId=...` into a JSON field `orderId`.

## 2. Distinguishing Layout, Formatter, Encoder, Appender, and Logger

| Component | Question it answers | Example |
| --- | --- | --- |
| **Logger** | Which component emitted the event, and does it meet the logging threshold? | `com.example.orders.OrderService` |
| **Log event / LogRecord** | What data does the event contain? | `INFO`, message, `Throwable`, timestamp, context |
| **Filter** | Which events are accepted or rejected? | Accept only `WARN` and above at a destination |
| **Layout** | In what structure is the record presented? | `%d %-5level %logger - %msg%n` |
| **Formatter** | Formats a record into a string according to the JUL API. | `java.util.logging.SimpleFormatter` |
| **Encoder** | Converts an event's representation into bytes for the appender to write. | `PatternLayoutEncoder` in Logback |
| **Appender / Handler** | Where is the content sent, and how are I/O and lifecycle managed? | Console, file, rolling file |
| **Collector** | Collects, stores, labels, or forwards data from the application. | Agent receiving stdout/file or a centralized system |

An appender can use a layout to write to the console or a file; **the same event** can be sent to two appenders with **two different layouts**. For example, the console can use a human-readable format while a file uses structured JSON for a search system. When fan-out is not needed, configure only one sink to avoid extra I/O and duplicate data.

**Layout does not equal severity.** If an event is marked `INFO`, changing the pattern does not turn it into an `ERROR` event; the layout only displays the content. **Layout also does not equal retention/rotation.** Writing JSON does not automatically limit file size; retention policies belong to the appender and infrastructure.

## 3. Layout as a Data Transformation with Inputs and Outputs

You can think of it as:

```text
format(loggingEvent, configuration) -> rendered representation
```

Inputs may include:

- **Level**: `TRACE`, `DEBUG`, `INFO`, `WARN`, `ERROR` (depending on the framework), or `FINE`, `INFO`, `WARNING`, `SEVERE` in JUL.
- **Timestamp**: event timestamp; requires consistent timezone and precision.
- **Source**: logger name, class, method if metadata and the corresponding collector are available.
- **Thread**: thread name or ID, useful when diagnosing concurrency.
- **Message**: message template and parameters formatted according to the API.
- **Throwable**: stack trace, cause, and suppressed exceptions when the framework stores them and the layout renders them.
- **Context/attributes**: `requestId`, `traceId`, `spanId`, `tenantId`, `eventName`, etc., when attached properly.
- **Marker/additional metadata**: depending on the library and configuration.

The output can be a line of text, one JSON object per line, XML, or bytes of another format. Which style to choose depends on the log collection target and the reader's needs.

### Text layout

Pros: easy to read in a terminal, with `grep`, and when debugging locally. Cons: delimiters can be ambiguous, messages with newline characters span multiple lines, and querying independent fields is difficult.

### Structured layout

Pros: collectors can parse fields such as `level`, `requestId`, or `durationMs`; easy to build dashboards and alerts based on stable attributes. Cons: requires a schema, an appropriate encoder, handling of dynamic data, and a sensitive-data policy; JSON does not automatically solve every operational problem.

### XML or other representations

Some ecosystems provide XML formatters/output. For example, JUL's `java.util.logging.XMLFormatter` outputs XML by design. XML is not "wrong", but it must match your analysis tools and operational goals, just like JSON or text.

## 4. Pattern Layout: Understanding Placeholders

In Logback and Log4j 2, **PatternLayout** uses conversion patterns to produce a formatted text string. Conceptual example:

```text
%d{yyyy-MM-dd HH:mm:ss.SSS} %-5level [%thread] %logger - %msg%n
```

In common patterns, the meanings are typically:

| Pattern | Meaning | Example content |
| --- | --- | --- |
| `%d{...}` | Timestamp in the configured format. | `2026-03-05 08:20:10.123` |
| `%level` or `%p` | Event level. | `INFO` |
| `%-5level` | Left-aligned level padded to at least five characters. | `INFO ` |
| `%thread` or `%t` | Thread that emitted the event. | `http-worker-2` |
| `%logger` or `%c` | Logger name. | `com.example.orders.OrderService` |
| `%logger{36}` | Logger name shortened according to framework rules when needed. | A shorter name to save display columns |
| `%msg` or `%m` | Message formatted with parameters. | `Order ord-42 accepted` |
| `%n` | Platform-specific line separator. | Ends the record |
| `%ex` / `%exception` | `Throwable` information if present. | Stack trace and cause chain |
| `%X{requestId}` | `requestId` field from MDC/ThreadContext if present. | `req-17` |

**Note:** Pattern details, converter names, and option syntax differ by backend and version. Do not copy a Logback pattern verbatim into JUL or assume every Log4j 2 converter is supported by Logback. For instance, `{0}` in JUL is a **message parameter** placeholder, not a layout pattern converter.

A pattern with multiple fields is usually better than logging only `%msg%n`. However, simply adding `%X{requestId}` does not create a request ID; the application or middleware must attach the context before emitting the event.

## 5. Layout for Stack Traces and Exceptions

When an error occurs, a message like `"Save failed"` does not tell you which layer threw the exception. If the logging API properly receives a `Throwable`, an appropriate layout/formatter can include the stack trace, cause, and suppressed exceptions in the output.

Example using SLF4J in a context where `LOG`, `orderId`, and `ex` already exist:

```java
LOG.error("event=order.save_failed orderId={}", orderId, ex);
```

The code above is an **illustrative snippet**, not a standalone program. `ex` must be passed as a `Throwable` according to the API overload/rules, not merely concatenated into the string via `ex.getMessage()`.

If the layout only outputs the message without including thrown information (or a downstream pipeline strips the exception field), diagnostic data can be lost. Conversely, some backend layouts append exceptions automatically by default even when the pattern does not explicitly specify an exception conversion; therefore, **always verify the actual output for your exact version**.

### Multiline log lines and parsers

Text stack traces usually span multiple lines. This is easy to read in a console, but a "one line per event" collector may split a single exception into multiple bogus records. You can use a structured layout to place the stack trace in a single field or configure a multiline parser on the collector. Do not strip stack traces from important errors just to keep one line; design ingestion appropriately.

### Choosing log level and format independently

An input error rejected by contract may not need `ERROR` or a stack trace; an unrecoverable transaction failure usually needs a higher-level event and enough context to investigate. The layout is not the place to change the business meaning of a level.

## 6. JUL Uses Formatter Instead of Layout

The standard library `java.util.logging` follows this model:

```text
java.util.logging.Logger
    -> LogRecord
    -> Handler (ConsoleHandler / FileHandler / StreamHandler)
    -> Formatter
    -> output
```

Built-in formatters include:

- `SimpleFormatter`: outputs text configured via `java.util.logging.SimpleFormatter.format`; typically includes timestamp, source, level, message, and exception.
- `XMLFormatter`: outputs XML in JUL's format.
- Custom `Formatter`: override `format(LogRecord)` to produce custom text, optionally calling `formatMessage(record)` to handle parameters and resource bundles.

Illustrative JUL example inside a method:

```java
java.util.logging.ConsoleHandler console =
        new java.util.logging.ConsoleHandler();
console.setFormatter(new java.util.logging.SimpleFormatter());

java.util.logging.Logger logger =
        java.util.logging.Logger.getLogger("demo.checkout");
logger.addHandler(console);
```

This is an **illustrative snippet** and omits level management, parent handlers, and lifecycle handling. `ConsoleHandler` in JUL typically writes to stderr; it does not write to stdout by default. `FileHandler` in JUL typically defaults to XML formatting, so a `.log` file is not guaranteed to contain plain text lines.

### Customizing SimpleFormatter via configuration properties

JUL supports defining a `printf` pattern for `SimpleFormatter` via a system property or `logging.properties`. Example:

```properties
java.util.logging.SimpleFormatter.format=%4$s | %5$s%6$s%n
```

In `SimpleFormatter`'s format, `%4$s` is the level, `%5$s` is the message, and `%6$s` is the throwable information included by the formatter when present. **This is JUL's `String.format` syntax**, not Logback's `%level`/`%msg`.

Do not use Logback's `%-5level` syntax to configure `SimpleFormatter.format` because the two mechanisms are different. Moreover, `SimpleFormatter`'s format is read and interpreted by the JVM configuration; if the application uses another logging framework, JUL properties will not automatically affect Logback/Log4j 2.

## 7. Standalone Java 17 Example: Same Event, Two Formatters

The following program uses only JDK 17 (no Maven required). It creates two `StreamHandler` instances for **the same logger**. One handler uses a text formatter, and the other uses an illustrative JSON formatter. Both handlers write to separate `ByteArrayOutputStream` instances to inspect the output without files; the program prints the results after flushing. The same event is represented in two ways.

**Save as `LayoutDemo.java`:**

```java
import java.io.ByteArrayOutputStream;
import java.nio.charset.StandardCharsets;
import java.util.logging.Formatter;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;
import java.util.logging.StreamHandler;

public class LayoutDemo {
    private static String escapeJson(String value) {
        StringBuilder out = new StringBuilder();
        for (int i = 0; i < value.length(); i++) {
            char c = value.charAt(i);
            switch (c) {
                case '"':
                    out.append("\\\"");
                    break;
                case '\\':
                    out.append("\\\\");
                    break;
                case '\n':
                    out.append("\\n");
                    break;
                case '\r':
                    out.append("\\r");
                    break;
                case '\t':
                    out.append("\\t");
                    break;
                default:
                    if (c < 0x20) {
                        out.append(String.format("\\u%04x", (int) c));
                    } else {
                        out.append(c);
                    }
            }
        }
        return out.toString();
    }

    public static void main(String[] args) {
        Logger logger = Logger.getLogger("demo.checkout");
        logger.setUseParentHandlers(false);
        logger.setLevel(Level.INFO);

        ByteArrayOutputStream textBytes = new ByteArrayOutputStream();
        ByteArrayOutputStream jsonBytes = new ByteArrayOutputStream();

        Handler textHandler = new StreamHandler(
                textBytes,
                new Formatter() {
                    @Override
                    public String format(LogRecord record) {
                        return record.getLevel().getName()
                                + " | " + record.getLoggerName()
                                + " | " + formatMessage(record) + "\n";
                    }
                }
        );

        Handler jsonHandler = new StreamHandler(
                jsonBytes,
                new Formatter() {
                    @Override
                    public String format(LogRecord record) {
                        return "{\"level\":\""
                                + escapeJson(record.getLevel().getName())
                                + "\",\"logger\":\""
                                + escapeJson(record.getLoggerName())
                                + "\",\"message\":\""
                                + escapeJson(formatMessage(record))
                                + "\"}\n";
                    }
                }
        );

        textHandler.setLevel(Level.INFO);
        jsonHandler.setLevel(Level.INFO);
        logger.addHandler(textHandler);
        logger.addHandler(jsonHandler);

        try {
            logger.fine("event=debug.filtered");
            logger.log(
                    Level.INFO,
                    "event=checkout.completed orderId={0}",
                    "ord-42"
            );
        } finally {
            logger.removeHandler(textHandler);
            logger.removeHandler(jsonHandler);
            textHandler.close();
            jsonHandler.close();
        }

        System.out.print("TEXT\n");
        System.out.print(textBytes.toString(StandardCharsets.UTF_8));
        System.out.print("JSON\n");
        System.out.print(jsonBytes.toString(StandardCharsets.UTF_8));
    }
}
```

Compile and run:

```bash
javac LayoutDemo.java
java LayoutDemo
```

**Exact standard output** when run successfully:

```text
TEXT
INFO | demo.checkout | event=checkout.completed orderId=ord-42
JSON
{"level":"INFO","logger":"demo.checkout","message":"event=checkout.completed orderId=ord-42"}
```

### Step-by-step explanation

1. `logger.setLevel(Level.INFO)` causes the `FINE` event to be filtered out; no `event=debug.filtered` line is produced.
2. The logger has **two handlers**, each with its own formatter, so **one INFO event** is formatted into two independent outputs.
3. `Formatter.formatMessage(record)` uses JUL's `{0}` placeholder convention to substitute `ord-42`. In SLF4J/Log4j2, code typically uses `{}` instead of `{0}`.
4. Both formatters pick the same three pieces of information: level, logger, and message; text uses ` | `, while JSON uses an object with fixed keys. It is the layout/formatter that changes the representation, not the original level or message.
5. Both `StreamHandler` instances write to `ByteArrayOutputStream` so the program can close the handlers and read the bytes as UTF-8 before printing to stdout. Omitting timestamp/thread keeps the output deterministic.
6. `logger.setUseParentHandlers(false)` prevents the record from propagating to parent logger handlers and causing unexpected output.
7. `escapeJson` is strictly for educational purposes: it handles JSON characters that commonly cause errors such as double quotes, backslashes, newlines, and control characters. In production, use a standard JSON library/structured layout rather than maintaining a custom serializer.
8. The program is not meant to claim that `JUL has a class named Layout`. In JUL, we implement a **Formatter**, which is the equivalent component for representing a record.

In real applications, do not create new handlers per request as in this learning example. Configure handlers/formatters at startup according to the application lifecycle, and manage shutdown and resources properly.

## 8. Logback: How Do Layout and Encoder Work Together?

**Logback Classic** typically receives calls from **SLF4J** and uses appenders together with encoders to write data. In Logback, `PatternLayout` formats an event into a string; `PatternLayoutEncoder` bridges a pattern-style layout to bytes for appenders. That is why common examples configure `<encoder>` rather than attaching `<layout>` directly to a `FileAppender`.

Complete `src/main/resources/logback.xml` example for an application using SLF4J with the Logback provider:

```xml
<configuration>
    <appender name="STDOUT"
              class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%d{HH:mm:ss.SSS} %-5level
                [%thread] %logger - %msg%n</pattern>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="STDOUT"/>
    </root>
</configuration>
```

The XML above is split across lines for readability, but **whitespace and newlines inside `<pattern>` can affect the output depending on how the parser handles them**. In real code, keep the pattern on **one line** to avoid unintended whitespace, for example:

```xml
<pattern>%d{HH:mm:ss.SSS} %-5level [%thread] %logger - %msg%n</pattern>
```

If you want the same event to have different layouts on the console and in a file, declare two appenders, each with its own encoder, and reference both under root/LoggerConfig. **Do not attach the same appender to both a child logger and root at the same time**, to avoid duplicate logs due to additivity.

### Logback is not synonymous with SLF4J

`slf4j-api` is a facade; Logback Classic is a provider/backend. Application code typically calls:

```java
// Illustrative snippet in class OrderService; requires SLF4J dependency.
private static final org.slf4j.Logger LOG =
        org.slf4j.LoggerFactory.getLogger(OrderService.class);

void accept(String orderId) {
    LOG.info("event=order.accepted orderId={}", orderId);
}
```

If the runtime selects a different backend (for example, the Log4j2 provider for SLF4J), `logback.xml` will not control that backend. For a layout to take effect, verify the active provider, version, loaded configuration file, and receiving sink.

### Structured JSON with Logback

A `PatternLayoutEncoder` outputs a text pattern and does not automatically turn data into JSON fields. Reliable JSON for collectors requires a JSON encoder/layout compatible with your chosen Logback version and dependencies, with clear field mapping and valid escaping. Check stack traces, MDC, timestamps, schema, and record size in the actual output.

Do not treat a pattern like `{"message":"%msg"}` as safe JSON: messages containing `"`, `\\`, or newlines can break JSON if not properly escaped.

## 9. Log4j 2: Layout Lives Inside the Appender

Log4j 2 Core provides layouts such as `PatternLayout` and, when the required module is present, `JsonTemplateLayout`. A console configuration with PatternLayout (for an application using Log4j2 API/Core) might look like:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<Configuration status="WARN">
    <Appenders>
        <Console name="STDOUT" target="SYSTEM_OUT">
            <PatternLayout pattern="%d{ISO8601} %-5level [%t] %c - %m%ex%n"/>
        </Console>
    </Appenders>

    <Loggers>
        <Root level="INFO">
            <AppenderRef ref="STDOUT"/>
        </Root>
    </Loggers>
</Configuration>
```

Save this in `src/main/resources/log4j2.xml` so Log4j2 Core finds it on the classpath in a standard setup. `Logger` in code uses `org.apache.logging.log4j.LogManager` and the corresponding `logger.info(...)` methods. If the runtime is using Logback as the backend, `log4j2.xml` will not be applied automatically.

In Log4j2, if you want a file and the console to have different layouts, you can declare both `Console` and `RollingFile` with separate `PatternLayout` configurations and attach them via `AppenderRef`. Levels and filters on the logger/ref/appender determine which events reach which sink; the layout only handles presentation.

### Structured JSON with JsonTemplateLayout

Log4j2 has a JSON template layout module (such as `log4j-layout-template-json` in corresponding versions), which is not necessarily bundled in `log4j-core`. Configuration and the event-template schema should be chosen according to the documentation for your version. The result is JSON records with clear keys, suitable for ingestion when the collector is configured properly.

**A JSON layout does not mean every value is already a separate field.** For example, a text message `"event=order.accepted orderId=42"` may still live inside a single `message` field. To make `orderId` a separate attribute, the application must emit structured data or appropriate context and configure the template/encoder to include that field in JSON.

## 10. Layout and Contextual Data: MDC, ThreadContext, Trace IDs

Information such as `requestId`, `traceId`, and `spanId` helps correlate logs across layers and services. They should not be embedded in logger names or arbitrarily copied into every message string when the framework provides a proper context API.

With **SLF4J**, context can be attached using MDC:

```java
// Illustrative snippet in a method; LOG and requestId are already defined.
org.slf4j.MDC.put("requestId", requestId);
try {
    LOG.info("event=order.accepted orderId={}", "ord-42");
} finally {
    org.slf4j.MDC.remove("requestId");
}
```

In Logback's PatternLayout, you can use `%X{requestId}` to print the value. With **Log4j2**, the corresponding API is typically `ThreadContext.put(...)`, and `%X{requestId}` can read from the context map as configured.

**Do not assume context propagates automatically across all threads.** `ExecutorService`, `CompletableFuture`, reactive pipelines, and virtual threads can change execution context. Use proper propagation and clean up context in `finally`/scopes to avoid leaking one request's logs into another.

For tracing, standardize field names across services—such as `traceId`, `spanId`, `service`, and `environment`. A layout can display these fields, but it **does not generate trace IDs itself**; instrumentation, middleware, or application code must provide the data first.

## 11. Text Layout vs. JSON Layout: How to Choose?

| Criterion | Text/PatternLayout | JSON/structured layout |
| --- | --- | --- |
| Reading directly in terminal | Usually easy and compact. | Longer; sometimes needs a formatter to view. |
| Keyword search | Easy for simple `grep`. | Text search works, but the main value is field queries. |
| Field-level parsing | Depends on pattern/parser; can be ambiguous. | Strong if fields are well-defined and the collector parses cleanly. |
| Escaping | Vulnerable to multiline issues and log injection. | Standard JSON encoders escape properly, though schema still needs control. |
| Exceptions | Text stack traces are readable but multiline. | Can hold stack trace or cause in a field, depending on layout. |
| Missing data | Absent fields can leave blank spots in the pattern. | Can omit the field or emit `null`, depending on schema. |
| Compatibility | Depends on pattern and downstream parsers. | Depends on schema, template version, and downstream consumers. |
| Size/CPU | Usually compact, depending on pattern. | Can be more bytes due to keys and escaping; benchmark it. |

**Choose based on operational goals**, not appearance alone. A CLI may suit text; a distributed application with an observability platform usually benefits from structured logging. You can also use **two different layouts for two appenders** when needed, while weighing I/O, cost, and data duplication.

### One JSON record per line

Many ingestion systems expect NDJSON: each line is **one complete JSON object**. If a serializer leaves unescaped newlines or puts multiple objects on one line, parsing can fail. Verify the real output with a JSON parser rather than just checking the file extension.

## 12. Designing Operationally Valuable Layouts

A good layout should quickly answer these questions:

1. **When?** Timestamp with timezone/offset, appropriate precision, and consistency across services.
2. **Where?** Service, environment, logger name, instance/pod if needed.
3. **How severe?** Level reflects event impact; do not use ERROR for normal operations.
4. **What happened?** `eventName` or stable event code; message clearly states action and outcome.
5. **Which request?** `requestId` or `traceId/spanId` propagated through the processing flow.
6. **Which entity?** Diagnostic IDs without exposing unauthorized information.
7. **What was the result?** `outcome`, `errorCode`, `attempt`, `durationMs` with consistent units.
8. **Why did it fail?** Throwable/stack trace/cause preserved properly on genuine error events.
9. **How is it routed?** Collectors can parse the output without guessing from text strings.

Example of a useful structured event (illustrative data):

```json
{
  "timestamp": "2026-03-05T08:20:10.123Z",
  "level": "INFO",
  "service": "checkout-service",
  "logger": "com.example.checkout.CheckoutService",
  "eventName": "checkout.completed",
  "requestId": "req-17",
  "orderId": "ord-42",
  "outcome": "success",
  "durationMs": 23
}
```

This event has a numeric `durationMs` field and a separate `eventName`; it is not an automatic product of `PatternLayout` when passing only a string message. The application/backend must produce the actual fields and the layout must serialize them according to the schema.

## 13. Common Pitfalls When Working with Layouts

| Symptom | Possible cause | Solution |
| --- | --- | --- |
| Logs do not appear | Logger/handler/appender level or filter drops the record, not the layout. | Check effective level, filters, and sink before editing the pattern. |
| Output missing logger/thread | Pattern omits the corresponding converter. | Add `%logger` / `%thread` or the JSON field per schema. |
| Pattern converter printed literally or errors out | Using another backend's syntax or an unsupported option. | Confirm Logback, Log4j2, or JUL and check version/converters. |
| Message appears but stack trace is missing | Only `ex.getMessage()` was logged or formatter omits throwable. | Pass `Throwable` via the proper API; check layout and collector. |
| Stack trace split into multiple events | Multiline text printed while collector ingests line by line. | Configure a multiline parser or a structured exception field. |
| Unparseable JSON | Manual JSON string concatenation, broken escaping, or multiple records on one line. | Use a standard JSON layout/encoder and test with a parser and schema. |
| `requestId` field always empty | MDC/ThreadContext not set or context lost across threads. | Set the field before logging, propagate it, and clean up in scope. |
| Duplicate logs on the same sink | Appender attached at multiple logger levels with additivity enabled. | Check appender refs/parent handlers; do not tweak layout to mask symptoms. |
| Ambiguous timezone | Local time logged without an offset. | Standardize on UTC or offset timestamps and document the schema version. |
| `.json` file still contains plain text | Only the file extension was changed, not the layout. | Configure a structured layout/encoder and verify each record. |
| Collector cannot find `orderId` field | `orderId` is inside message text rather than a JSON field. | Emit structured attributes and configure schema to output the field. |
| Log volume too noisy after adding layout | Level/frequency issue, not formatting. | Tune levels/metrics, sampling, or rate limiting as appropriate. |
| Garbled Vietnamese/Unicode characters | Writer and reader encodings do not match. | Standardize on UTF-8 in appender/encoder and collector. |

## 14. Security, Performance, and Compatibility

### Sensitive data

A layout can make information easier to search, but it does not automatically classify safe data. **Never log passwords, tokens, session cookies, private keys, full personal payloads, or unnecessary payment details** in messages, MDC, or exceptions. Library stack traces and error messages can also contain URLs with query parameters, file paths, or sensitive connection details.

Prefer designing safe log content at the event source. You can add masking/redaction in the pipeline, but do not use masking as an excuse to allow secrets into raw logs. Restrict access, set retention, and control forwarding logs to third-party systems.

### Log injection and escaping

If a message built from user input contains newlines or control characters, a text layout can make **one event look like multiple separate events**. Standard structured encoders usually escape JSON strings properly, but you still need to bound field sizes, sanitize source data, and watch out for special payloads. Do not rely on manual `String.replace` as a complete solution for production structured logging.

### Performance

Complex patterns, runtime call-site/class/method resolution, JSON serialization, printing long stack traces, and writing to multiple appenders all consume CPU/I/O. Caller location info can be expensive, especially in asynchronous logging; enable it only when truly needed. Do not strip every log down to just a message for optimization if doing so destroys diagnostic capability. Benchmark under realistic load and retention policies.

### Compatibility

- JUL's `SimpleFormatter.format` configuration is not the same as Logback/Log4j 2 patterns.
- Some converters and JSON layouts require specific dependencies or versions.
- Frameworks like Spring Boot may provide their own default configuration files or patterns; verify the active configuration.
- Appenders and encoders may not support every layout type; choose APIs compatible with your backend and sink.
- When changing a JSON schema, remember that dashboards, alerts, pipelines, and saved queries may depend on previous field names.

## 15. Pre-Deployment Checklist

- [ ] Confirmed the actual backend: JUL, Logback, or Log4j2?
- [ ] Are loggers/appenders receiving the expected levels and events?
- [ ] Does the layout include timestamp, level, logger, event, context, and exception as needed?
- [ ] Is the timestamp format consistent in timezone and precision?
- [ ] If outputting JSON: is each record valid, schema clear, and are fields real data rather than just a message string?
- [ ] Are the formatter/encoder versions right and compatible with the appender/sink?
- [ ] Is MDC/ThreadContext set, propagated across threads, and cleaned up on time?
- [ ] Are stack traces/causes preserved without being dropped or split by the collector?
- [ ] Are sensitive data and multiline user inputs controlled?
- [ ] Have UTF-8 encoding, storage volume, and I/O cost been tested?
- [ ] When changing layouts, have dashboards, alerts, parsers, and log consumers been updated?
- [ ] Tested with normal events, error events, Vietnamese/Unicode characters, double quotes, newlines, and missing request IDs?

**Conclusion:** A **Layout is how a log event is represented**, not the component that decides severity or storage destination. In JUL, this role is handled by **Formatter**; in Logback, **Layout/Encoder** works with the Appender; in Log4j2, **Layout** is attached to the Appender. Choose a layout based on reading, querying, and operational needs, and always verify that events and exception/context data actually appear in the output.
