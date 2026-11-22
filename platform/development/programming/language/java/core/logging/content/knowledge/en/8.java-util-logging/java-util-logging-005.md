# JUL Formatter: Turning a LogRecord into Log Output

## 1. What Does Formatter Do in Java Util Logging?

In `java.util.logging` (JUL), **`Formatter`** is the abstract class responsible for turning a **`LogRecord`** into a character string so that a `Handler` can write it to the console, a file, or another stream. A log record contains information such as severity level, message, parameters, timestamp, Logger name, call source, and exception; the Formatter decides which pieces of information appear and how they are presented.

For example, the same `order.created` event can be displayed in different ways:

```text
INFO: event=order.created orderId=O-18
```

```text
2026-01-12T10:15:00Z | INFO | checkout | order.created | orderId=O-18
```

```json
{"timestamp":"2026-01-12T10:15:00Z","level":"INFO","service":"checkout","event":"order.created","orderId":"O-18"}
```

These are three **illustrative representations**, not the default output of a specific JUL program. The point is: **the event stays the same, while the Formatter's encoding changes**.

A Formatter **does not decide whether to log**; the Logger and Handler/Filter perform that conditional check. A Formatter also does not choose where logs are stored: the output destination belongs to the Handler. A good Formatter must output accurate data, preserve important error details, encode safely, and maintain performance appropriate for the log volume.

Objectives of this lesson:

1. Distinguish between `Logger`, `LogRecord`, `Handler`, and `Formatter`.
2. Understand `Formatter.format(LogRecord)`, `formatMessage(LogRecord)`, `getHead()`, and `getTail()`.
3. Know when to use `SimpleFormatter`, `XMLFormatter`, or a custom Formatter.
4. Write and configure a Formatter in Java 17, and verify against stdout.
5. Avoid pitfalls such as losing stack traces, misformatting parameters, log injection, and ineffective configuration.

## 2. Where Does Formatter Sit in the Logging Pipeline?

Conceptual flow of JUL:

```text
Java code: logger.log(Level.INFO, "...")
                 |
                 v
              Logger
       checks level and Logger Filter
                 |
                 v
              LogRecord
                 |
                 v
         Handler / Parent Handler
       checks level and Handler Filter
                 |
                 v
             Formatter
          format(LogRecord)
                 |
                 v
         Handler writes formatted string
                 |
                 v
       stdout/stderr/file/OutputStream
```

An application can attach multiple Handlers, and each Handler has its own Formatter. For example, ConsoleHandler uses concise text for quick reading, while FileHandler uses another format for storage. The same `LogRecord` can produce two different output strings depending on the Handler.

| Component | Role | Question to Answer |
| --- | --- | --- |
| `Logger` | Receives log calls, checks level and filter, forwards the record | Should this event be accepted? |
| `LogRecord` | Holds event data before output | What attributes does the event carry? |
| `Handler` | Checks output conditions and writes to the destination | Where should it be written? |
| `Formatter` | Converts `LogRecord` to text | In what format should it be written? |
| `Filter` | Accepts or rejects records at the Logger/Handler | Should the record proceed? |

**Order matters:** if a Logger filters out `FINE` by level, or a Handler only accepts `WARNING` and above, creating a Formatter that supports `FINE` will still not make the record appear. When a Formatter is not invoked, trace back through level, filter, Handler, and the propagation path to the Handler before modifying the formatter.

In JUL, a Handler often receives records forwarded by child Loggers to a parent Logger's Handler when `useParentHandlers=true`. The Formatter attached to the parent Handler processes those records as well; it does not only receive events emitted by the parent Logger itself.

## 3. Core API of `java.util.logging.Formatter`

`Formatter` is an abstract class. When writing a subclass, the required method is:

```java
@Override
public String format(LogRecord record) {
    return record.getLevel().getName()
            + " " + formatMessage(record)
            + System.lineSeparator();
}
```

This is a **snippet placed inside a `Formatter` subclass**, not a complete program. It converts the level and message into a single line of text.

### 3.1. `format(LogRecord)`: Deciding How the Output Record Looks

The `format` method takes a `LogRecord` and returns a `String`. Here, you can choose the fields, ordering, timestamp, delimiter, error representation, and line ending. For example:

```text
[WARNING] event=payment.retry attempt=2
```

Some useful data-retrieval methods on `LogRecord`:

| Method | Data Retrieved | Notes |
| --- | --- | --- |
| `getLevel()` | Level of the record | Can use `getName()` or localized name |
| `getMessage()` | Raw message or ResourceBundle lookup key | Parameters may not be substituted yet |
| `getParameters()` | Parameter array when present | May be `null` |
| `getLoggerName()` | Name of the Logger that emitted the record | May be `null` for manually created records |
| `getInstant()` | Timestamp of the record as an `Instant` | Available in modern JDKs, including Java 17 |
| `getSourceClassName()`, `getSourceMethodName()` | Call source when known | May be missing or expensive to determine |
| `getThrown()` | Exception attached to the record | Formatter must decide how to represent it |
| `getResourceBundle()` | ResourceBundle for localization | Not every record has one |

Information about **when the record was emitted** should be taken from the record. If a formatter calls `Instant.now()` itself, that timestamp reflects formatting time, which can lag behind the actual event in an asynchronous logging system.

### 3.2. `formatMessage(LogRecord)`: Handling Localization and Parameters

`formatMessage(record)` is a built-in method on `Formatter`. It provides JUL's standard workflow for producing display text from the message:

1. Check the ResourceBundle on the record, if present, to look up the message by key.
2. Process parameters according to JUL/`MessageFormat` conventions.
3. Return the processed message; if there is no applicable resource or parameter, it may keep the content as is.

Example logger call:

```java
logger.log(
        Level.INFO,
        "event=order.created orderId={0} items={1}",
        new Object[] {"ord-17", "3"}
);
```

A Formatter calling `formatMessage(record)` will get:

```text
event=order.created orderId=ord-17 items=3
```

In JUL, parameter templates use `{0}`, `{1}` following `java.text.MessageFormat`; do not confuse them with the `{}` placeholder common in SLF4J. If you call `record.getMessage()` instead of `formatMessage(record)`, parameterized records may still show literal `{0}` and `{1}`.

**Note on locale:** `MessageFormat` can format numbers/dates according to the environment's locale. When you need typed data and a stable machine-readable format, use separate fields and an encoder with a clear schema rather than relying on parsing localized text.

### 3.3. `getHead(Handler)` and `getTail(Handler)`: Wrapping a Stream

`Formatter` also has:

```java
public String getHead(Handler handler)
public String getTail(Handler handler)
```

By default, these two methods return an empty string. A Formatter can write a header/footer for the entire data stream, such as an XML declaration and its corresponding closing tag. Handlers that support stream formatting, such as `StreamHandler`, can use them when opening/closing the stream.

**Head/tail are not called per record.** Do not put timestamps, request details, or per-event processing messages inside `getHead`/`getTail`. Also do not rely on `getTail` to guarantee a closing marker when the process crashes or receives `SIGKILL`: in those cases, the Handler may not be closed cleanly.

## 4. Built-in Formatters in JUL

### 4.1. `SimpleFormatter`: Human-Readable Text

`java.util.logging.SimpleFormatter` converts a record into text containing information such as timestamp, source, level, message, and throwable when present. It is the common default choice for ConsoleHandler. The exact presentation can be influenced by the JDK version and configuration properties, so you should not write a parser that depends on its default format.

You can change the format pattern using the property:

```properties
java.util.logging.SimpleFormatter.format = %4$s: %5$s%6$s%n
```

Meaning of some pattern arguments according to `String.format`:

| Code in Pattern | Meaning |
| --- | --- |
| `%1$` | Date/time of the record (date argument) |
| `%2$s` | Source class/method or logger name |
| `%3$s` | Logger name |
| `%4$s` | Presented level name |
| `%5$s` | Formatted message |
| `%6$s` | Formatted throwable section, if any |
| `%n` | Platform-specific line separator |

In the pattern, the date/time part is typically written as `%1$tF %1$tT`; `%1$` alone is **not a valid pattern for outputting date and time**.

With `SimpleFormatter.format`, placeholders use **`String.format` syntax**, such as `%4$s`, whereas message placeholders inside the record still follow JUL/`MessageFormat` (`{0}`, `{1}`). These are two different formatting layers:

```text
LogRecord message: "orderId={0}" + parameter "ord-17"
    → formatMessage → "orderId=ord-17"
    → SimpleFormatter.format "%4$s: %5$s%n"
    → "INFO: orderId=ord-17"
```

### 4.2. `XMLFormatter`: XML for Machine-Readable Data

`java.util.logging.XMLFormatter` outputs records in an XML structure; it handles head/tail appropriately to produce a valid XML document for a properly closed stream. JUL's `FileHandler` defaults to XMLFormatter when not overridden by other configuration.

XMLFormatter preserves record fields in XML form, which is convenient for tools that understand that format. It **does not automatically turn logs into JSON**, and it does not guarantee a complete XML file if the process dies before the Handler writes the closing section. Do not mix text lines from another Formatter into the same XML file and expect an XML parser to still read it.

### 4.3. When Should You Write a Custom Formatter?

A custom Formatter is appropriate when you need text logs with a fixed schema or integration with an output system that has a clear contract. For example:

- Each line contains `level`, `logger`, `event`, and a few control fields.
- Timestamps in UTC using ISO 8601 format.
- Exceptions/stack traces formatted according to operational conventions.
- Masking sensitive data in certain fields before output.

If the application already uses SLF4J + Logback, Log4j 2, or an official structured logging system, prefer the encoder/layout supported by that backend. There is no need to hand-roll a JSON encoder or a comprehensive Formatter via manual string concatenation.

## 5. Configuring a Handler to Use a Formatter

In JUL, a Formatter is usually attached via `Handler.setFormatter(formatter)`, or via a `logging.properties` file for supported Handlers.

Example concise text configuration for the console:

```properties
handlers = java.util.logging.ConsoleHandler
.level = INFO

java.util.logging.ConsoleHandler.level = INFO
java.util.logging.ConsoleHandler.formatter = java.util.logging.SimpleFormatter
java.util.logging.SimpleFormatter.format = %4$s: %5$s%6$s%n
```

In a suitable JUL application, you can instruct the JVM to load this file early:

```bash
java -Djava.util.logging.config.file=logging.properties YourMainClass
```

`YourMainClass` is **the main class name of the application to run**, not the sample class provided below. ConsoleHandler normally writes to **stderr**, so output may appear on stderr rather than stdout. If the program creates Handlers and Formatters programmatically in code, direct settings can override or prevent some options in the configuration file from taking effect.

A complete configuration also involves Logger levels, Handler levels/filters, parent handlers, and output destinations. Changing the Formatter only changes how a record is converted into a string; it does not enable events already blocked by levels or filters.

## 6. Standalone Java 17 Example: Writing a Custom Formatter

The following example uses only JDK 17+. It creates a `Logger`, attaches a `StreamHandler` to `System.out`, and provides a custom Formatter. We observe three points:

1. A message containing `{0}` has its parameter substituted by `formatMessage(record)`.
2. Level `FINE` is filtered out by the Handler set to `INFO`, even though the Logger has level `ALL`.
3. A record with a `Throwable` has its error type and message presented by the Formatter; the stack trace remains in the record, but this Formatter intentionally omits printing the full stack to keep stdout short and deterministic.

Create the file **`JulFormatterDemo.java`**:

```java
import java.util.logging.Formatter;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;
import java.util.logging.StreamHandler;

public final class JulFormatterDemo {
    public static void main(String[] args) {
        Logger log = Logger.getLogger("demo.jul.formatter");

        Formatter formatter = new Formatter() {
            @Override
            public String format(LogRecord record) {
                StringBuilder line = new StringBuilder()
                        .append(record.getLevel().getName())
                        .append(" logger=")
                        .append(record.getLoggerName())
                        .append(" message=")
                        .append(formatMessage(record));

                if (record.getThrown() != null) {
                    Throwable error = record.getThrown();
                    line.append(" | cause=")
                            .append(error.getClass().getSimpleName())
                            .append(": ")
                            .append(error.getMessage());
                }

                return line.append(System.lineSeparator()).toString();
            }
        };

        Handler output = new StreamHandler(System.out, formatter) {
            @Override
            public synchronized void publish(LogRecord record) {
                super.publish(record);
                flush();
            }
        };

        output.setLevel(Level.INFO);
        log.setLevel(Level.ALL);
        log.setUseParentHandlers(false);
        log.addHandler(output);

        try {
            log.log(Level.INFO,
                    "event=order.created orderId={0}",
                    "ord-17");

            log.fine("event=debug.details");

            log.log(Level.WARNING,
                    "event=payment.retry attempt={0}",
                    "2");

            log.log(Level.SEVERE,
                    "event=payment.failed",
                    new IllegalStateException("gateway unreachable"));
        } finally {
            output.flush();
            log.removeHandler(output);
        }
    }
}
```

Compile and run in the directory containing the file:

```bash
javac JulFormatterDemo.java
java JulFormatterDemo
```

**Exact stdout of the program:**

```text
INFO logger=demo.jul.formatter message=event=order.created orderId=ord-17
WARNING logger=demo.jul.formatter message=event=payment.retry attempt=2
SEVERE logger=demo.jul.formatter message=event=payment.failed | cause=IllegalStateException: gateway unreachable
```

Explanation:

- `log.log(Level.INFO, ...)` creates a record with a message pattern and parameter. `formatMessage(record)` produces `orderId=ord-17`.
- `log.fine(...)` passes the Logger's `ALL` threshold but is blocked by `output.setLevel(INFO)`. Therefore, no `FINE` line is printed.
- `WARNING` has a string parameter `"2"`, which is inserted at `{0}` without depending on locale number formatting.
- `SEVERE` includes `IllegalStateException`; the Formatter writes `cause=IllegalStateException: gateway unreachable` according to the rule we designed.
- `setUseParentHandlers(false)` prevents records from being forwarded to the parent Logger's ConsoleHandler, avoiding duplicate logs.
- `StreamHandler` can buffer data. In the example, `publish()` calls `flush()` after each record; at the end of the program, `flush()` is also called. Do not call `close()` here because the handler is attached to `System.out`: closing the StreamHandler could close the shared stdout stream.
- The stdout order is deterministic because the program runs sequentially and the formatter does not print timestamps or thread IDs. Multithreaded/asynchronous applications should not assume strict emission and output ordering like in this example.

### 6.1. Adding a Timestamp from LogRecord

In a real-world Formatter, you can write **this snippet inside `format(record)`**:

```java
String timestamp = java.time.format.DateTimeFormatter.ISO_INSTANT
        .format(record.getInstant());
```

`record.getInstant()` carries the time the event was created. The `ISO_INSTANT` format gives a UTC timestamp suitable for correlation across multiple hosts; do not use `LocalDateTime.now()` at formatting time as if it were the event time.

If you want to format the date in a specific time zone, use `DateTimeFormatter` with an explicit `ZoneId`. Avoid a shared `SimpleDateFormat`, which has mutable state and is unsafe in concurrent environments; `DateTimeFormatter` is a more convenient immutable alternative.

### 6.2. Including the Stack Trace in a Custom Formatter

If you want to preserve diagnostic details, a snippet **inserted into `format(record)`** could be:

```java
if (record.getThrown() != null) {
    java.io.StringWriter writer = new java.io.StringWriter();
    java.io.PrintWriter printer = new java.io.PrintWriter(writer);
    record.getThrown().printStackTrace(printer);
    printer.flush();
    line.append(System.lineSeparator()).append(writer);
}
```

Here `line` is the Formatter's existing `StringBuilder`. When appending a stack trace, the log output can span multiple lines; you need to configure your log collector to group lines belonging to the same record, or use a structured log format with a dedicated exception field. You should limit volume, mask secrets in exception messages if needed, and avoid logging the same stack trace at every layer.

## 7. Locale and Message Parameters: Two Different Formatting Layers

A common source of bugs is confusing the **message** format pattern with the **SimpleFormatter** pattern.

### 7.1. JUL Message Pattern

```java
logger.log(Level.INFO, "item={0} count={1}", new Object[]{"book", "3"});
```

This is an illustrative snippet, assuming a Logger `logger` is already declared. `formatMessage(record)` may produce:

```text
item=book count=3
```

If the message is a `ResourceBundle` lookup key, `formatMessage` attempts to retrieve the localized string before substituting parameters. When locale affects numbers/dates or phrasing, **human-readable** content can change depending on the environment.

### 7.2. SimpleFormatter Pattern Using Java Formatter

```properties
java.util.logging.SimpleFormatter.format = %1$tF %1$tT %4$s %5$s%6$s%n
```

Here `%1$tF` is the date from the date argument, `%1$tT` is the time; `%4$s` is the level; `%5$s` is the generated message; `%6$s` is the throwable section; `%n` is a newline. The `%1$tF` syntax belongs to `String.format`, not `MessageFormat`.

If an `IllegalFormatException` occurs from an invalid pattern, check the syntax and argument indices of `SimpleFormatter.format`. Do not change `{0}` in the message to `%1$s` unless you design a custom message API and a Formatter that explicitly understands the new syntax.

### 7.3. When a Stable Machine-Readable Schema Is Needed

Localized messages are helpful for humans; however, alerting systems and dashboards should not rely solely on matching message strings that can vary by locale or language. Maintain stable event codes and structured fields (`event`, `errorCode`, `requestId`) for querying; the Formatter is responsible for emitting them in a format understood by the collection system.

## 8. Formatter Quality, Performance, and Safety

### 8.1. Keep Each Event Independent and Well-Structured

For text logs, appending a newline at the end of a record prevents two events from merging together. However, if user-supplied values contain `\\n` or `\\r`, a single log can be forged into multiple lines if not escaped. Example input:

```text
name=visitor
ERROR event=admin.login outcome=success
```

The second line might just be malicious content injected into the `name` field rather than a real event. Use a proper JSON encoder when structured output is needed; for text, escape control characters and quote values consistently. `formatMessage(record)` only performs JUL message processing; **it is not a data security sanitizer**.

Do not hand-assemble JSON with ad-hoc `StringBuilder.append` calls when data may contain quotes, backslashes, Unicode, and control characters; prefer a reliable serializer library if the application architecture requires JSON.

### 8.2. Do Not Lose the Throwable

`record.getMessage()` does not contain the stack trace by rule. `record.getThrown()` stores the exception if the caller passed it using the appropriate overload. A custom Formatter must decide whether to output the error type, message, cause chain, and stack trace. Outputting very little saves space, but losing the call stack makes diagnosing unexpected errors difficult.

Distinguish expected errors that have a business code (where `errorCode` alone may suffice) from system errors that need a stack trace. Only format stack traces when truly meaningful; do not print the same exception at every call boundary.

### 8.3. Do Not Put Business Logic in the Formatter

A Formatter should be a presentation layer. Do not:

- Send HTTP requests or write to a database inside `format()`.
- Mutate payment state or increment business counters when a record is formatted.
- Call `logger.log()` from inside `format()` on the same pipeline, risking recursion.
- Read additional secrets or entire objects just to "enrich information."
- Call the current clock to overwrite the actual timestamp in `LogRecord`.

A Formatter invoked on a synchronous I/O path can slow down requests if serialization, stack trace generation, or lookups are too heavy. With an asynchronous backend, formatting may run on another thread; to avoid races, capture context data as a snapshot when creating the event.

### 8.4. Be Careful with Shared State and Log Ordering

If a Formatter has a line-counter field or mutable formatting objects, you must consider how the Handler uses the Formatter across multiple threads. The safe approach is usually to keep the Formatter **stateless** and use immutable objects (such as `DateTimeFormatter`). JUL supports multithreaded logging, but do not assume all custom Formatters or third-party Handlers synchronize identically.

A Formatter also does not guarantee that logs are durably stored. Handlers can buffer, disks can fill up, collectors can fail, and crashes can lose the last records. When audit guarantees are required, design a dedicated audit/storage mechanism.

### 8.5. Protect Sensitive Information Before Output

A Formatter can apply consistent data masking, but the first line of defense must still be deciding **not to put passwords, tokens, cookies, card numbers, and unnecessary personal data into `LogRecord`**. A Formatter cannot guarantee removal of every secret accidentally embedded in a free-form message or throwable text. Use a safe-field allowlist, length limits, log access controls, and retention policies.

## 9. Diagnosing Formatter-Related Issues

| Symptom | How to Check |
| --- | --- |
| Log shows literal `{0}` | Does the Formatter call `formatMessage(record)`; does the record have parameters |
| Message is formatted but stack trace is missing | Does the Formatter handle `getThrown()`; did the caller pass `Throwable` to the right overload |
| `FINE` level does not appear | Check Logger and Handler levels/filters and parent handler propagation before the Formatter |
| New Formatter has no effect | Check which Handler actually owns the Formatter, and whether runtime config is overridden in code |
| Logs are printed twice | Handlers exist on both child and parent Loggers; check `useParentHandlers` |
| JSON Formatter set but file cannot be parsed | Check escaping, framing, stream head/tail, untrusted data, and multiple Handlers mixing output |
| Log timestamp drifts from trace | Formatter uses `Instant.now()` instead of the record's timestamp, or async delay |
| Vietnamese/non-ASCII characters are garbled | Charset on Handler/stream, collector and terminal encoding; locale/resource bundle |
| XML file missing closing tag | Handler was not closed cleanly, process crashed, or file was truncated |
| Multiline log split into multiple events | Stack trace and text values not escaped; multiline parser configuration in collector |
| Logging slows down requests | Formatter performs heavy serialization or stack trace processing on the synchronous path |
| Sensitive data appears despite masking | Record contains secret in another field, throwable, or another Handler with its own Formatter |

The investigation flow should go from record creation to output destination: **Does the Logger accept the level? → Does the Handler receive the record? → Which Formatter is attached? → Does the Formatter produce the right text? → Does the stream/collector write it properly?** Avoid changing multiple things at once if the goal is only to fix presentation.

## 10. Implementation Checklist

- Verify whether the system uses real JUL or another facade/backend; a JUL Formatter does not configure Logback/Log4j 2 layouts.
- Use `SimpleFormatter` for standard text logs, `XMLFormatter` when the pipeline genuinely needs XML, or a custom Formatter when you have a clear schema.
- In a custom `format(LogRecord)`, use `formatMessage(record)` if you want ResourceBundle and message parameter handling per JUL rules.
- Take the timestamp from the record, output level/source/logger as needed, and clearly include the event and required context.
- Handle `record.getThrown()` intentionally; do not accidentally drop diagnostic information.
- Attach the Formatter to the right Handler, and check levels/filters and parent propagation.
- Ensure each record has a clear structure, escapes untrusted data, and supports Unicode with proper encoding.
- Keep the Formatter concise, thread-safe, and free of side effects or recursive logging.
- Test at least four cases: parameterized log, log with Throwable, log filtered by Handler, and multiple Handlers with different Formatters.
- Verify actual stdout/stderr/file output, buffering/flushing, log collector behavior, data security, and retention policy.

**Conclusion:** In JUL, `Formatter` decides **how a `LogRecord` is represented**, while `Logger` and `Handler` decide whether an event is accepted and which destination it is written to. Using `formatMessage(record)`, handling Throwables, taking timestamps from the record, and configuring the Formatter on the right Handler keeps logs readable, queryable, and less misleading during incident diagnosis.
