# What Is a Formatter? The Role of Formatter and Layout in Java Logging

**Formatter** is the component that converts a **log event** into a human-readable or machine-processable output representation. In **Java Util Logging (JUL)**, a formatter is typically a class extending `java.util.logging.Formatter` that takes a `LogRecord` and returns a `String`. In other backends such as **Logback** and **Log4j 2**, this presentation role is usually called **Layout** and works together with an **Encoder**.

A log record contains many pieces of data: the INFO/WARNING/SEVERE level, message template, parameters, logger name, timestamp, thread information, and optionally a `Throwable`. The formatter chooses **which fields are printed, their order, timestamp format, delimiters, character escaping, and how exceptions are presented**.

Most importantly: **the Formatter determines the appearance of the record; the Logger decides whether to emit the log, and the Handler/Appender decides what to filter at the destination and where to write it.**

## 1. Where Formatter Fits in the Logging Architecture

With JUL, the typical flow is:

~~~text
Application code: logger.log(Level.INFO, template, args)
                          |
                          v
                 java.util.logging.Logger
                     Level / Filter
                          |
                          v
                       LogRecord
         message, parameters, level, instant,
          logger name, thread, thrown...
                          |
                          v
                  Handler / Filter
                          |
                          v
                       Formatter
                  format(LogRecord)
                          |
                          v
                   Formatted string
                          |
                          v
                Console / file / stream
~~~

In Logback and Log4j 2, the diagram is similar in terms of responsibilities, but replaces the JUL types with the corresponding implementation's logging event, appender, layout, and encoder.

| Question | Primary Responsibility |
| --- | --- |
| Which events should be logged, and at what level? | Application code and Logger |
| Does the event pass the level/filter? | Logger and Handler/Appender at each layer |
| Which fields does the log line include, and how are they formatted? | Formatter/Layout/Encoder |
| Is it written to stderr, a file, a stream, or a collection system? | Handler/Appender and configuration |
| Who decides retention and log access permissions? | Logging infrastructure and operational policy |

If the Logger is set to the INFO threshold, a `logger.fine(...)` call can be discarded **before the Formatter is ever involved**. Changing the formatter cannot make an unaccepted `LogRecord` appear.

An application can use **multiple Handlers/Appenders** with different formatters: short text for the console, timestamps and stack traces for files, and JSON for collectors. Business events do not need their content modified every time the presentation changes.

## 2. What Data Does a Formatter Process?

In JUL, the input to a formatter is `java.util.logging.LogRecord`.

| Data | JUL Method | Why It Is Useful |
| --- | --- | --- |
| Level | `record.getLevel()` | Distinguishes INFO, WARNING, SEVERE, etc. |
| Message template | `record.getMessage()` | Original message content, which may contain `{0}` |
| Parameters | `record.getParameters()` | Values inserted into the template |
| Formatted message | `formatMessage(record)` | Combines template, parameters, and resource bundle |
| Logger name | `record.getLoggerName()` | Identifies the component emitting the event |
| Timestamp | `record.getInstant()` | Instant attached to the record |
| Exception | `record.getThrown()` | Cause and stack trace, if present |
| Caller source | `record.getSourceClassName()`, `getSourceMethodName()` | Emission site when source info is available |
| Thread info | Record thread metadata | Helps investigate concurrency issues |

Not every record has an exception or caller source information. A formatter should handle `null` fields gracefully instead of throwing a `NullPointerException` just because an event has no `Throwable`.

### Template vs. Formatted String

In JUL:

~~~java
// Illustrative snippet inside a method that already has a JUL logger.
logger.log(java.util.logging.Level.INFO,
        "event=order_accepted orderId={0} units={1}",
        new Object[]{"ord-7", 3});
~~~

With a formatter that uses `formatMessage(record)`, the message portion is rendered as:

~~~text
event=order_accepted orderId=ord-7 units=3
~~~

If a custom formatter only returns `record.getMessage()`, the reader may see the literal `orderId={0}`, because `getMessage()` returns the original template. `formatMessage(record)` also supports JUL's resource bundle/localization mechanism when configured.

**JUL uses `{0}`, `{1}` placeholders in message templates; SLF4J typically uses `{}`.** The two styles are not syntactically interchangeable.

## 3. Writing a Formatter in JUL

`java.util.logging.Formatter` is an abstract class that requires implementing:

~~~java
public abstract String format(LogRecord record);
~~~

A minimal example:

~~~java
import java.util.logging.Formatter;
import java.util.logging.LogRecord;

final class CompactFormatter extends Formatter {
    @Override
    public String format(LogRecord record) {
        return record.getLevel().getName()
                + " | " + formatMessage(record)
                + System.lineSeparator();
    }
}
~~~

This class compiles when placed in an appropriate Java file, though it does not have a `main` method. To use it, attach it to a `Handler`:

~~~java
// In a configuration snippet where the console variable of type ConsoleHandler already exists:
console.setFormatter(new CompactFormatter());
~~~

**A Formatter does not open files or write to the network itself.** `ConsoleHandler`, `FileHandler`, or another Handler uses the formatter when exporting records.

Related methods:

- `format(LogRecord)`: builds the representation of a single record.
- `formatMessage(LogRecord)`: produces a readable message from the template, parameters, and resource bundle.
- `getHead(Handler)` and `getTail(Handler)`: opening/closing content needed for certain document-style or XML formats.

A text formatter typically appends a newline after each event. Omitting `System.lineSeparator()` can cause consecutive events to merge into a single hard-to-read line.

## 4. Standalone Java 17+ Example

The following program demonstrates a **custom JUL Formatter** with zero dependencies outside the JDK. The output is designed to be deterministic for easy verification: level, logger name, parameterized message, exception class name, and escaping of newlines from input data.

Create **FormatterDemo.java**:

~~~java
import java.util.logging.ConsoleHandler;
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class FormatterDemo {
    private static final Logger LOG =
            Logger.getLogger("demo.checkout");

    public static void main(String[] args) {
        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.INFO);

        ConsoleHandler console = new ConsoleHandler();
        console.setLevel(Level.ALL);
        console.setFormatter(new Formatter() {
            @Override
            public String format(LogRecord record) {
                String message = formatMessage(record)
                        .replace("\\", "\\\\")
                        .replace("\r", "\\r")
                        .replace("\n", "\\n");
                String cause = record.getThrown() == null
                        ? ""
                        : " | cause="
                                + record.getThrown().getClass().getSimpleName();
                return record.getLevel().getName()
                        + " | " + record.getLoggerName()
                        + " | " + message + cause
                        + System.lineSeparator();
            }
        });
        LOG.addHandler(console);

        LOG.log(Level.INFO,
                "event=order_accepted orderId={0} units={1}",
                new Object[]{"ord-7", 3});
        LOG.log(Level.WARNING,
                "event=retry_scheduled reason={0} attempt={1}",
                new Object[]{"timeout", 2});
        LOG.log(Level.SEVERE, "event=payment_failed orderId=ord-8",
                new IllegalStateException("gateway unavailable"));
        LOG.log(Level.INFO, "event=user_input value={0}", "hello\nworld");

        LOG.removeHandler(console);
        console.close();
    }
}
~~~

Compile and run with JDK 17 or later:

~~~bash
javac --release 17 FormatterDemo.java
java FormatterDemo
~~~

**Exact output on stderr** from `ConsoleHandler`:

~~~text
INFO | demo.checkout | event=order_accepted orderId=ord-7 units=3
WARNING | demo.checkout | event=retry_scheduled reason=timeout attempt=2
SEVERE | demo.checkout | event=payment_failed orderId=ord-8 | cause=IllegalStateException
INFO | demo.checkout | event=user_input value=hello\nworld
~~~

Analysis:

1. The formatter calls `formatMessage(record)` to substitute `{0}`, `{1}` in the template.
2. The level and logger name come from `LogRecord`; the application does not need to insert them into every message manually.
3. `getThrown()` indicates whether the record has an exception; the example **prints only the exception class name** to keep the output stable. This is **insufficient for production diagnostics** when stack traces are needed.
4. The last line has input containing an actual newline character. The formatter replaces it with the literal characters `\n`, keeping the event on a single output line.
5. `LOG.setUseParentHandlers(false)` prevents records from also flowing into parent/root logger Handlers, avoiding duplicate output in the example.
6. `ConsoleHandler` writes to **stderr** by default, not stdout. Changing the formatter does not change the target stream.
7. `LOG.removeHandler(console)` and `console.close()` show resource cleanup when managing a Handler directly.

This example was compiled and run with **`javac --release 17`**. With the default formatter, the output would include timestamps and a different exception format. Because timestamps vary with wall-clock time, the example chooses **not to print timestamps** so the output can be matched exactly.

**Security limitation:** the `replace` steps only handle backslashes, carriage returns, and newlines. They do not handle all control characters, JSON escaping, secrets, or length limits. In real applications, use a format-appropriate encoder and proper data policies.

## 5. Built-in Formatters in the JDK

JUL provides two commonly used formatters:

| Formatter | Output Form | Use Case |
| --- | --- | --- |
| `SimpleFormatter` | Human-readable text, typically with timestamp, level, source name, message, and exception | Console, files for operators |
| `XMLFormatter` | XML representation of events | XML-based log processing systems |
| Custom `Formatter` | Application-defined text or custom format | When a system has specific output conventions |

Example of configuring a Handler in code (illustrative snippet):

~~~java
java.util.logging.ConsoleHandler handler =
        new java.util.logging.ConsoleHandler();
handler.setFormatter(new java.util.logging.SimpleFormatter());
~~~

You can use `logging.properties` to configure JUL centrally:

~~~properties
handlers = java.util.logging.ConsoleHandler
.level = INFO
java.util.logging.ConsoleHandler.level = ALL
java.util.logging.ConsoleHandler.formatter = java.util.logging.SimpleFormatter
~~~

Run a compiled program with the configuration file:

~~~bash
java -Djava.util.logging.config.file=logging.properties MyApplication
~~~

`MyApplication` is an illustrative class with `main`; it is not part of the `FormatterDemo` example. If the program later calls `setFormatter` in code, that programmatic setting can override the formatter chosen from properties.

### SimpleFormatter.format Has Its Own Syntax

The JDK also provides the `java.util.logging.SimpleFormatter.format` property to customize the text format of `SimpleFormatter`. For example:

~~~properties
java.util.logging.SimpleFormatter.format = %4$s: %5$s%6$s%n
~~~

The `%4$s`, `%5$s`... specifiers belong to `SimpleFormatter`'s `String.format` mechanism, which is completely different from Logback's `%level` and `%msg`. When using it, check the documentation for your JDK version and test **both normal records and records with a Throwable**; omitting the exception placeholder can drop stack traces.

### XMLFormatter, getHead, and getTail

For a sequence of events forming an XML document, a formatter may need opening/closing content via `getHead(Handler)` and `getTail(Handler)`. Never build XML by concatenating raw input strings directly into tags, because data can contain `<`, `>`, `&`, or quotes. Proper XML escaping is required.

## 6. Formatter and Layout in Logback

Logback is commonly used behind SLF4J as a facade, and **does not use `java.util.logging.Formatter` as its primary formatter**. Instead:

- **`PatternLayout`** turns a logging event into text according to a pattern.
- **`Encoder`** converts an event representation into bytes to write to an `OutputStream`.
- **`PatternLayoutEncoder`** combines a pattern layout and an encoder for `ConsoleAppender`/`FileAppender`.
- **`Appender`** is the component that writes to the console, a file, or another destination.

A `src/main/resources/logback.xml` configuration:

~~~xml
<configuration>
    <appender name="CONSOLE"
              class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%d{ISO8601} %-5level [%thread] %logger{36} - %msg%n%ex</pattern>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
    </root>
</configuration>
~~~

How to read the tokens:

| Token | Meaning |
| --- | --- |
| `%d{ISO8601}` | Timestamp formatted according to Logback rules |
| `%-5level` | Level left-aligned with a minimum width of 5 |
| `%thread` | Thread name |
| `%logger{36}` | Logger name abbreviated according to Logback rules |
| `%msg` | Message content |
| `%n` | Newline |
| `%ex` | Exception/stack trace via Logback's converter |

This is a **standalone Logback configuration** when the application actually uses the Logback backend. Exact output depends on timestamp, thread, logger, and runtime values, so there is no single fixed stdout string to compare across every machine.

**Changing the pattern does not enable DEBUG.** If the root logger is at INFO, application DEBUG logs are still blocked. If Logback is not the active backend, `logback.xml` will not control the output of JUL or Log4j 2 either.

### How Does Layout Differ from Encoder?

**Layout** defines **what the content looks like**, typically producing a string. **Encoder** defines **how to turn an event into bytes** and can add headers/footers or specialized data structures. Appenders need bytes to write to a stream; therefore Logback typically configures an `<encoder>` rather than attaching a JUL `Formatter`.

Do not assume every encoder only uses `PatternLayout`; other encoders exist for structured log output. Check your dependencies, versions, and specific configuration.

## 7. Layout in Log4j 2

Log4j 2 also has **`PatternLayout`**, though its API and configuration syntax are not identical to Logback's. Example `log4j2.xml` for the Log4j 2 backend:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<Configuration>
    <Appenders>
        <Console name="CONSOLE" target="SYSTEM_OUT">
            <PatternLayout pattern="%d{ISO8601} %-5level [%t] %c - %m%n%throwable"/>
        </Console>
    </Appenders>
    <Loggers>
        <Root level="info">
            <AppenderRef ref="CONSOLE"/>
        </Root>
    </Loggers>
</Configuration>
~~~

The `Console` appender writes to `SYSTEM_OUT`, and `PatternLayout` controls the pattern. `%m` is the message, `%c` is the logger, `%t` is the thread name, `%n` is a newline, and `%throwable` formats the exception.

If the application calls the SLF4J API but wants to use Log4j 2 Core, it needs a **compatible SLF4J provider/binding** to forward events to Log4j 2. Having a `log4j2.xml` file does not by itself guarantee that SLF4J has selected Log4j 2 as the backend.

## 8. Are SLF4J Templates a Formatter?

No. Application code might call:

~~~java
// Illustrative snippet inside a method with a logger of type org.slf4j.Logger.
logger.info("event=order_accepted orderId={} units={}", orderId, units);
~~~

SLF4J provides a facade and message parameterization; it **does not standardize a single console/file layout**. Level, timestamp, logger name, thread name, exceptions, and JSON/text output depend on the backend and its configuration.

Three concepts that should not be conflated:

1. **Business information:** the application chooses the appropriate event, outcome, IDs, and message.
2. **Message template format:** JUL uses `{0}`; SLF4J typically uses `{}`.
3. **Final event presentation:** JUL Formatter, Logback Layout/Encoder, or Log4j 2 Layout.

Also do not confuse **Logback's `%msg` pattern** with the **`{}` parameter placeholder**. The `%msg` pattern tells the layout where to insert the message in the final line; it does not write the message on behalf of the application.

## 9. Text Format vs. Structured Logging

A text-formatted log record typically has these parts:

~~~text
2026-11-09T10:15:30Z INFO demo.OrderService - Order ord-7 accepted
~~~

This style is easy to read manually and search as text. When you need exact queries/filters by `requestId`, `orderId`, `durationMs`, and trace ID, structured data is usually much more useful.

Illustrative JSON example (not the default output of JUL or Logback):

~~~json
{
  "timestamp": "2026-11-09T10:15:30Z",
  "level": "INFO",
  "logger": "demo.OrderService",
  "event": "order_accepted",
  "message": "Order accepted",
  "orderId": "ord-7",
  "units": 3
}
~~~

Benefits of structured fields:

- `units` can remain a number rather than just a string.
- Queries can target a stable event name even if the message wording changes.
- Correlation ID / trace ID becomes a dedicated field.
- A compliant JSON encoder systematically handles quotes, newlines, backslashes, and control characters.

**Never assemble JSON with unescaped string concatenation.** A message containing quotes or newlines can make the JSON unparseable; malicious input can break record boundaries. Likewise, wrapping text in `{}` does not turn an event into structured JSON.

Choose a JSON encoder compatible with your backend and version. Typed fields do not appear automatically just by changing a pattern; the application side must provide the fields properly.

## 10. Exceptions, Stack Traces, and Multiline

A `LogRecord` has `record.getThrown()`, but a custom Formatter is **not automatically required to print it**. If it only returns `formatMessage(record)`, readers will not see the error's stack trace.

The main example only outputs `cause=IllegalStateException` for deterministic output; production usually needs more detail. Illustrative snippet inside `format(LogRecord record)`:

~~~java
if (record.getThrown() != null) {
    java.io.StringWriter buffer = new java.io.StringWriter();
    java.io.PrintWriter writer = new java.io.PrintWriter(buffer);
    record.getThrown().printStackTrace(writer);
    writer.flush();
    String stackTrace = buffer.toString();
    // Append stackTrace to the output according to application policy.
}
~~~

This is **not a standalone program**. Stack trace contents vary with call stack, classes, and line numbers, so there is no fixed output.

Options to choose from:

| Output Style | Advantage | Risk to Manage |
| --- | --- | --- |
| Single-line text per event | Easy to grep/ingest line by line | Must escape newlines in data |
| Multiline stack trace | Easy to read when debugging | Collector must reassemble multiline events accurately |
| JSON Lines | Easy to parse into fields | Requires a valid JSON encoder and full escaping |
| XML records | Fits XML processing pipelines | Requires document structure, XML escaping, and head/tail |

Stack traces can contain file paths, URLs, or sensitive data in exception messages. Access control and retention policies are needed; do not assume a formatter only handles public information.

## 11. Timestamps, Timezones, and Caller Location

Production formatters should include timestamps that are easy to compare across systems. With JUL, use **`record.getInstant()`** rather than calling `Instant.now()` when the formatter runs: especially with async logging, those two moments can differ.

An illustrative snippet:

~~~java
// Inside format(LogRecord record):
String timestamp = java.time.format.DateTimeFormatter.ISO_INSTANT
        .format(record.getInstant());
~~~

`ISO_INSTANT` produces a UTC timestamp with an explicit timezone designator. If you need to display a specific timezone, set the offset/zone and keep it consistent with other services. Never mix timezone-less local times with UTC when analyzing event ordering.

**Caller location** such as file/method/line number can be expensive if the backend has to walk the stack; do not leave it enabled when unnecessary. **Thread name** is helpful, but does not replace `requestId`/trace ID, because thread pools reuse the same thread across many requests.

When a log collector aggregates data from multiple machines, clock skew still exists; correlation IDs and distributed tracing correlate events more reliably than timestamps alone.

## 12. Performance and Concurrency

A formatter is invoked frequently in high-throughput applications. Key principles:

- **Do not serialize an entire object graph** when only an ID and a few diagnostic values are needed.
- **Do not perform I/O inside `format()`** to call a database/network or write files outside the handler; the formatter should focus strictly on presentation.
- **Keep formatters free of mutable shared state**, because multiple threads may share the same handler/formatter. Local variables and immutable `DateTimeFormatter` instances are much safer than shared mutable date formatters.
- **Do not call back into the same logging system from a Formatter to report formatting errors** if doing so could cause a loop or recursion.
- **Do not blame all logging cost on the Formatter**: building the message before the logger, capturing stack traces, JSON encoding, file appenders, async queues, and network I/O can have a larger impact.
- **Do not assume placeholders are lazy:** an expensive method call passed as an argument can be evaluated by Java before the logger checks the level; use a supplier or a level check at the call site.

Example of avoiding premature debug dump construction (illustrative SLF4J snippet):

~~~java
if (logger.isDebugEnabled()) {
    logger.debug("event=state_inspected data={}", buildExpensiveDump());
}
~~~

Even with a compact pattern/layout, constructing data before reaching the logger can still consume CPU. Measure performance under realistic workloads rather than just comparing pattern lengths.

## 13. Formatter Does Not Replace Log Data Security

A formatter can escape values for the output format, but **it cannot decide on behalf of the business logic which data is allowed to be logged**.

At the log source, prefer an allowlist: event, reason code, appropriate internal IDs, status, duration. Avoid passwords, tokens, Authorization headers, session cookies, card data, sensitive payloads, or `toString()` output of large objects.

**Log injection** risk arises when external input contains newlines, quotes, or control characters that split a text record improperly or forge text resembling an `ERROR` from another event. The custom formatter example escaped newlines for demonstration; production systems should use a format-appropriate encoder and validate other untrusted fields as well.

**Do not treat JUL `{0}` or SLF4J `{}` as automatic secret masking tools.** They are parameter substitution syntax, not an access-control layer or sensitive-data filter.

## 14. Common Mistakes and Troubleshooting

| Symptom | Possible Cause | Check or Fix |
| --- | --- | --- |
| JUL output still prints `{0}` | Formatter uses `getMessage()` instead of `formatMessage(record)` | Use `formatMessage` when substituted values are needed |
| Missing stack trace | Custom Formatter ignores `getThrown()` | Render the `Throwable` or choose a formatter that supports it |
| Multiple records merged onto one line | No newline appended in `format()` | Add `System.lineSeparator()` / `%n` |
| DEBUG/FINE logs not appearing | Logger/Handler/Appender blocks events before the formatter | Check levels and filters at each layer |
| JUL `{}` not substituted | Using SLF4J syntax in JUL | Use `{0}`, `{1}` as required by JUL |
| Duplicate logs | Multiple Handlers/Appenders or parent forwarding | Check parent handlers and additivity |
| Unparseable JSON | Manual JSON concatenation without escaping | Use a dedicated JSON encoder |
| Stack trace split into multiple events | Collector not configured for multiline | Use structured logging or a multiline parser |
| Timestamps off by several hours | Different formatting timezones | Standardize on UTC/offset |
| Performance degradation | Heavy formatter, caller lookup, stack traces, or serialization | Profile and remove unnecessary data |
| Text appears without logger name/level | Pattern omits those metadata fields | Add the corresponding fields |
| JUL logs go to stderr instead of stdout | `ConsoleHandler` defaults to stderr | Check Handler/output stream, not just Formatter |
| Logback pattern has no effect | Runtime is using a different backend | Verify the active provider and loaded config file |
| Sensitive data appears in logs | Log source writes payloads/secrets | Allowlist/redact at the source and restrict access |

Troubleshooting sequence: confirm the logger call executes → verify level/filter allows the event → identify the backend → inspect handlers/appenders → identify the attached formatter/layout/encoder → test events with parameters, `Throwable`, and newlines → check output on stderr/stdout/file/collector.

Do not change both the level and the formatter at the same time before knowing whether the record was **dropped earlier** or **emitted with wrong formatting**.

## 15. Self-Check Exercise

Given the following JUL Formatter:

~~~java
@Override
public String format(java.util.logging.LogRecord record) {
    return record.getLevel() + " " + record.getMessage();
}
~~~

And a class emitting:

~~~java
logger.log(java.util.logging.Level.WARNING,
        "event=retry attempt={0}", 2);
~~~

These are two illustrative snippets, not a standalone program.

Answer the following:

1. Why might `{0}` still appear in the output?
2. Why might two events be merged onto a single line?
3. Why is there no stack trace even when the record has a `Throwable`?
4. If the Logger is `OFF`, will changing only the Formatter make `INFO` events appear?
5. If JSON is required, why can you not simply concatenate `"{\"message\":\"" + value + "\"}"`?

**Answers:**

1. `getMessage()` returns the template. Use `formatMessage(record)`.
2. `format()` does not append a newline.
3. `record.getThrown()` is never called to handle the exception.
4. No. The Logger drops the event before it reaches the Formatter.
5. Because `value` may contain quotes, backslashes, newlines, and control characters; a valid JSON encoder is required.

An improved text formatter version:

~~~java
@Override
public String format(java.util.logging.LogRecord record) {
    return record.getLevel().getName()
            + " " + formatMessage(record)
            + System.lineSeparator();
}
~~~

This solves template substitution and newlines, but still lacks timestamps, `Throwable` handling, and escaping of untrusted data.

## 16. Formatter and Layout Design Checklist

- Know the exact logging system in use: **JUL, Logback, or Log4j 2**.
- Distinguish **event, handler/appender, and formatting**.
- Display **level, timezone-aware timestamp, logger name, and message** appropriately.
- Use the **correct template syntax for the API** and verify parameter substitution.
- Handle **`Throwable` and stack traces** according to diagnostic needs.
- Define **single-line per event vs. multiline** clearly, compatible with the collector.
- Use format-appropriate escaping; prefer built-in JSON/XML encoders.
- Do not log secrets or raw payloads; control log access permissions.
- Avoid heavy formatting overhead, non-thread-safe stateful handling, and recursive logging.
- Test with INFO/WARNING/SEVERE, parameters, exceptions, and inputs containing newlines.
- Verify that records reach the **intended destination** rather than just looking good in form.

**Conclusion:** A Formatter is **the presentation component of a log event**. JUL uses a `Formatter` attached to a `Handler`; Logback and Log4j 2 use their respective `Layout`/`Encoder` components. A good formatter keeps records consistent, readable, searchable, and format-safe, but **does not replace event selection, level filtering, destination configuration, or protecting data at the source**.
