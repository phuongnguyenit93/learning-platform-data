# Multiline Messages in Java Logging

A **multiline log message** is a message containing newline characters, which causes **a single logging event** to appear across **multiple lines of text** on the console or in a file. This type of message is useful when you need to present multiple related details for the same operation, but it can also make searching, automated parsing, event correlation, and log security harder.

The most important distinction is between **a log event** and **a physical line** in the output. In Java, a single `logger.info(message)` call typically creates **one record/event**, even when `message` contains multiple newline characters. Depending on the formatter, handler, backend, and collection tool, that single event may span multiple lines in the console/file or be encoded into a single structured record.

## 1. What does a multiline message look like?

Suppose the application emits the message:

```text
orderId=ORD-17 status=FAILED
stage=validate
reason=missing-address
```

The message above has **three lines of content**, yet it can be emitted by **a single** logger call. If the formatter places metadata at the beginning of the event, the text output typically looks like this:

```text
2026-11-09T08:20:10Z WARN OrderService - orderId=ORD-17 status=FAILED
stage=validate
reason=missing-address
```

This is **illustrative** data, not the output of running the Java example below. Only the first line has the timestamp, level, and logger name; the next two lines are continuations of the same message. A human reader can understand it, but a collection tool that treats **each line as a record** may mistake the latter two lines for independent events.

### Distinguishing events, messages, and display lines

| Concept | Meaning |
| --- | --- |
| **Log event / LogRecord** | The event emitted by a logging call, carrying level, logger name, timestamp, message, exception, context, etc. |
| **Log message** | The message content of the event; may have zero, one, or multiple newline characters |
| **Physical line** | A unit of text separated by newline characters in text output |
| **Log entry in a collection system** | The unit that a collector/backend has parsed and stored; may or may not match the original event if the parser is misconfigured |

There is no universal rule that *one logger call equals one log line in a file*. When a formatter appends a newline character at the end of a record, a message containing two internal newlines can produce three or more physical lines.

## 2. Common newline characters

Java uses escape sequences in string literals:

| Representation in Java source | Actual value | Meaning |
| --- | --- | --- |
| `"\n"` | LF character, U+000A | Standard LF line break |
| `"\r"` | CR character, U+000D | Carriage return; may alter cursor position in some environments |
| `"\r\n"` | CR followed by LF | Line-ending pair commonly used in Windows text |
| `System.lineSeparator()` | Line-break string of the current environment | Platform-dependent; may be LF or CRLF |
| `"\\n"` | Two visible characters: backslash and the letter `n` | A way to *display* an escaped newline, not an LF character |

Example:

```java
// This is an illustrative fragment inside a Java method.
String message = "first line\nsecond line";
LOGGER.info(message);
```

If the logging system writes the message as raw text, the content will be displayed across two lines. Conversely:

```java
String message = "first line\\nsecond line";
LOGGER.info(message);
```

The second message contains the characters `\` and `n`, so it will normally be displayed on **one line**, with the literal `\n` sequence in the middle. Both snippets above are fragments and assume a `LOGGER` has already been declared in the class.

**Portability note:** When assembling content for an interchange format that specifies LF, use `"\n"` according to the protocol. When you only want a line break appropriate for the current platform, `System.lineSeparator()` is an option. Do not assume that all files and log collection systems run on the same operating system.

## 3. Creating multiline messages in Java

### Approach 1: String concatenation

```java
String message = "operation=import\n"
        + "fileId=file-42\n"
        + "status=FAILED";
LOGGER.warning(message);
```

This is a straightforward solution when the number of lines is small and fixed. However, if you repeatedly concatenate strings from large inputs or perform expensive computations, consider the log length and whether the log level is currently enabled.

### Approach 2: `String.join`

```java
String message = String.join("\n",
        "operation=import",
        "fileId=file-42",
        "status=FAILED");
LOGGER.warning(message);
```

`String.join` is particularly suitable when joining a set of lines with a uniform structure. The result **does not automatically append a trailing newline**, because the separator is only placed between elements. You can use `System.lineSeparator()` instead of `"\n"` when appropriate.

### Approach 3: Java text block (Java 15+, usable in Java 17)

```java
String message = """
        operation=import
        fileId=file-42
        status=FAILED
        """.stripTrailing();

LOGGER.warning(message);
```

Text blocks `"""` make long multiline content easier to read compared to string concatenation. Java handles common indentation and normalizes line terminators in text blocks; the text block in the example typically has a trailing newline before the closing delimiter, so `.stripTrailing()` removes trailing whitespace, including that newline. If trailing whitespace is meaningful data, **do not use `stripTrailing()` indiscriminately**.

Text block syntax requires a supported Java version (standardized since Java 15). The fragments above assume a `LOGGER` of type `java.util.logging.Logger` is already present and are not three standalone `main` programs.

### Approach 4: Building a string from a list

```java
List<String> issues = List.of(
        "missing address",
        "invalid postal code",
        "unsupported region");
String message = "Validation errors:\n- "
        + String.join("\n- ", issues);
LOGGER.warning(message);
```

This snippet requires `import java.util.List;`. Using a single record for a summary with related lines can help the reader see the full picture. When a list may contain thousands of elements, set limits on the item count and message length to avoid flooding the logs.

## 4. Standalone Java 17 example: one record, multiple lines, and escaping

The program below uses only the JDK. It demonstrates three cases:

1. **Original multiline message:** newlines inside the message are preserved.
2. **Escaped single-line message:** converts CR/LF characters into literal `\r`/`\n` for easier line-by-line collection.
3. **Untrusted data:** prevents input content from forging a fake line that looks like a `SEVERE` message.

Save the file as **`MultilineMessageDemo.java`**:

```java
import java.util.logging.ConsoleHandler;
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class MultilineMessageDemo {
    private static final Logger LOGGER =
            Logger.getLogger(MultilineMessageDemo.class.getName());

    private static String escapeLineBreaks(String text) {
        return text.replace("\\", "\\\\")
                .replace("\r", "\\r")
                .replace("\n", "\\n");
    }

    public static void main(String[] args) {
        LOGGER.setUseParentHandlers(false);
        LOGGER.setLevel(Level.INFO);

        ConsoleHandler console = new ConsoleHandler();
        console.setLevel(Level.INFO);
        console.setFormatter(new Formatter() {
            @Override
            public String format(LogRecord record) {
                return record.getLevel().getName()
                        + " | " + formatMessage(record)
                        + System.lineSeparator();
            }
        });
        LOGGER.addHandler(console);

        try {
            String details = String.join("\n",
                    "requestId=req-7 status=FAILED",
                    "stage=validate",
                    "reason=missing-field");

            LOGGER.info("multi:\n" + details);
            LOGGER.info("single=" + escapeLineBreaks(details));

            String untrusted = "ok\r\nSEVERE | forged";
            LOGGER.info("userInput=" + escapeLineBreaks(untrusted));
        } finally {
            LOGGER.removeHandler(console);
            console.close();
        }
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac -encoding UTF-8 MultilineMessageDemo.java
java MultilineMessageDemo
```

**Exact output on `stderr`:**

```text
INFO | multi:
requestId=req-7 status=FAILED
stage=validate
reason=missing-field
INFO | single=requestId=req-7 status=FAILED\nstage=validate\nreason=missing-field
INFO | userInput=ok\r\nSEVERE | forged
```

The program does not explicitly write to `stdout`. JUL's `ConsoleHandler` writes to **stderr**, and `System.lineSeparator()` uses the OS-specific line break, so the trailing bytes of each record may be LF or CRLF. The displayed text lines above still have the same content.

**Analysis:**

- The program calls `LOGGER.info` **three times**, creating three `LogRecord`s. However, the handler output has **six physical lines**: four lines from the first event and one line for each of the remaining two events.
- `multi:\n` is interpreted by Java as the label `multi:` followed by a newline character. `String.join("\n", ...)` introduces two additional internal newlines.
- `escapeLineBreaks` replaces existing backslashes first, then replaces CR and LF with their visible representations `\r` and `\n`. This ordering avoids ambiguity when the input already contains backslashes.
- The third event has input containing `CRLF` and a fake line that resembles a `SEVERE` log. The escaping helper keeps the entire content on **one line**, so no forged `SEVERE`-level entry is created on the console.
- `LOGGER.setUseParentHandlers(false)` and the custom formatter make the output verifiable without extra lines from the root logger or timestamps. In a real application, use a formatter with complete metadata.

**Limitations of the demo:** The `escapeLineBreaks` function only handles backslashes and CR/LF. In production systems, you also need to consider tabs, control characters, ANSI escape sequences, Unicode line separators, message length, character sets, and the standard encoding method of your collection system. Choose a formatter/encoder that handles input consistently rather than treating this small helper as a complete security filter.

## 5. How is one multiline event different from multiple logger calls?

The following two approaches are not equivalent.

**Approach A – one call, one event containing multiple lines:**

```java
LOGGER.warning("requestId=req-7\n"
        + "stage=validate\n"
        + "reason=missing-field");
```

**Approach B – multiple calls, multiple events:**

```java
LOGGER.warning("requestId=req-7");
LOGGER.warning("stage=validate");
LOGGER.warning("reason=missing-field");
```

Approach A typically creates **one record** with a single level, timestamp, logger name, exception/context, and a multiline message. Approach B creates **three records**, each with its own metadata/timestamp, which can be interleaved with events from other threads. If the system applies level filtering, rate limiting, or sampling, separate events may even be routed to different destinations.

Therefore, **splitting a multiline message into multiple log calls** just to make the console look neat often breaks event-level atomicity and makes it harder to group by context. If the lines represent **genuinely independent business events**, multiple calls make sense; if they are merely details of the same event, keep them in a single event (ideally as structured fields when supported).

In a multithreaded environment, never assume that three consecutive log calls from one thread will always appear adjacent to each other in the aggregated log file. You need a correlation ID and an appropriate collection mechanism.

## 6. Multiline messages and exception stack traces

A **stack trace** is a common case of multiline log data. An exception can propagate through multiple layers; useful diagnostic information resides in the message, stack frames, and `Caused by` chain.

With JUL, at an error-handling boundary you can write:

```java
try {
    process();
} catch (IllegalArgumentException e) {
    LOGGER.log(Level.SEVERE,
            "requestId=req-7 operation=process outcome=failed", e);
}
```

This is a **fragment**: `process()` and `LOGGER` are provided by the application. `LOGGER.log(Level.SEVERE, String, Throwable)` passes the entire exception object into the `LogRecord`; a throwable-aware formatter, such as JUL's default `SimpleFormatter`, can write the stack trace across multiple lines. **The custom formatter in Section 4 only logs the message and ignores the throwable**, so it must not be used as-is if you want to preserve stack traces.

Illustrative example (line numbers vary by source/build):

```text
SEVERE requestId=req-7 operation=process outcome=failed
java.lang.IllegalArgumentException: invalid quantity
    at com.example.OrderService.validate(OrderService.java:42)
    at com.example.OrderService.process(OrderService.java:19)
Caused by: java.lang.NumberFormatException: For input string: "x"
    ...
```

**Do not call `e.printStackTrace()` as your primary logging mechanism in an application:** that call typically writes to `System.err` and bypasses the level, logger name, correlation ID, and configured logging pipeline. Pass the `Throwable` to the appropriate logging API and let the backend/formatter handle it.

With SLF4J in an application that has a provider/backend configured:

```java
// Fragment: log is org.slf4j.Logger; requestId and e are already available.
log.error("requestId={} operation=process failed", requestId, e);
```

The backend will process the throwable according to its configuration. **Do not use `e.getMessage()` as the sole piece of data**, as doing so loses the stack trace, frames, and causes. For a logger to output the full exception, the encoder/formatter must support the throwable field, not just the message field.

The key takeaway: multiline stack traces are **valuable data and should generally not be stripped away**. If your log storage system requires one record per line, place the exception into a structured field and let the encoder escape newlines within the string, or configure the collector to group multiline entries properly.

## 7. When to keep multiple lines vs. when to use a single line

| Scenario | Typically appropriate choice | Reason |
| --- | --- | --- |
| Local debugging, read directly on the console | Clearly structured multiline | Easy to follow step sequences and detailed content |
| Batch job needing to print a step summary | One event with multiple lines or structured data | All details belong to a single execution run |
| Log collection system reading stdout/stderr line by line | **One event per line** or a properly configured multiline parser | Avoids splitting one event into multiple metadata-less records |
| Centralized logs needing filtering by `requestId`, `errorCode`, `stage` | Structured logging, usually single-line JSON | Each field is named, making search/querying easy |
| Exceptions / long stack traces | Preserve throwable, use a structured encoder or multiline parser | Prevents losing error evidence |
| Untrusted input such as headers, query parameters, usernames | Escape or encode when logging | Reduces risk of log line forging and parser disruption |
| Lists with thousands of elements | Summary + count + cap on logged items | Avoids oversized logs, data leaks, and excessive I/O |

Not all multiline logs are wrong. The choice depends on whether the logs are read by **humans** or **automated systems**, querying requirements, length limits, storage format, and trust boundaries.

## 8. Collecting multiline logs in console, files, and centralized systems

With text-based logging, the formatter usually appends a newline at the end of a record. If the message or exception also contains newlines, a single Java event can become multiple output lines.

**Consequences when a collector reads line by line:**

1. The first line has the timestamp, level, logger, and correlation ID.
2. Subsequent lines of the same message may lack those fields.
3. The parser may treat subsequent lines as independent events, report the wrong level, or fail to correlate them with the request.
4. The reported count of "log entries" increases even though the actual number of logger calls has not changed.

There are two common approaches to handle this:

**Approach A – format each event as a single-line structured record.**

Illustrative example:

```json
{"timestamp":"2026-11-09T08:20:10Z","level":"WARN","logger":"OrderService","requestId":"req-7","message":"stage=validate\nreason=missing-field"}
```

This is **a valid single line of JSON**: the newline in the message content is escaped as `\n` inside the string value. A proper JSON serializer escapes control characters inside strings; do not manually concatenate JSON with untrusted input strings. To achieve one event per line, the encoder must **not pretty-print** the object across multiple lines.

With Logback or Log4j 2, the capabilities and configuration syntax for structured encoders/layouts depend on the specific version, dependencies, and backend. Simply adding `%n` to a pattern will not turn every newline in the message into `\n`: the record-ending token usually only appends a newline at the end of the event.

**Approach B – keep multiline text but configure the collector to merge a single event accurately.**

A collector can rely on a timestamp/level at the start of a line, parser state, or start/end rules. When doing so, test at least: messages with internal newlines; stack traces with `Caused by`; interleaved logs from multiple threads; events missing a timestamp on a line; and long records exceeding the collector's size limit. Know whether merging happens at the agent, pipeline, or backend so you do not produce corrupted records.

There is no single universal multiline regex that fits every log format. An overly broad rule can accidentally merge two real events, especially when a message contains text that looks like a timestamp or log level.

## 9. Security: CRLF injection and log forging

A multiline message **intentionally formatted by the application** is different from newlines coming from **external input**. If untrusted input is logged verbatim, an attacker can inject `\r`/`\n` along with words like `ERROR`, `SEVERE`, a logger name, or a timestamp to create a line that **looks like a separate event**.

Hypothetical input example:

```text
guest
2026-11-09T08:20:11Z SEVERE AuthService - access granted
```

If logged directly via `LOGGER.info("username=" + username)`, the text log can appear as two lines, with the second line masquerading as an independent event. This is known as **log forging / log injection**. Not every user-supplied newline is an attack, but the system must separate data from application-generated log structure.

Ways to mitigate the risk:

- Prefer structured fields and a standard encoder with escaping; keep user data inside **field values**, never letting it control record formatting.
- For single-line text logging systems, escape CR/LF and relevant control characters before emitting to the destination.
- Limit the length of logged input and omit/mask sensitive data. **Never log passwords, tokens, session cookies, secret keys, or sensitive personal data.**
- During analysis, avoid assuming that every line starting with `ERROR` or a timestamp is a genuine event if logs have not been properly escaped.
- If a log genuinely needs application-generated multiline content, pass a correlation ID separately and use a format/pipeline capable of preserving event boundaries.

The escaping in the Java example illustrates the principle, but it is **not sufficient to claim safety for all inputs**. For JSON formats, use a serializer. For text logs, apply your system's own escaping and data-length policies.

## 10. Formatting readable multiline logs with context

If the goal is to display multiline output directly for human operators, use a **short header** stating the operation type/correlation ID, followed by an indented list of lines using consistent field names:

```text
INFO requestId=req-7 operation=validate result=FAILED
  errorCount=2
  - missing-address
  - invalid-phone
```

This is still multiple physical lines for one event, but readers can easily distinguish the header from the continuation lines. When passing through a line-by-line collector, configure merging or switch to structured logging.

Another option is to log only a **single summary line** with identifying fields:

```text
WARN requestId=req-7 operation=validate result=FAILED errorCount=2 errorCodes=MISSING_ADDRESS,INVALID_PHONE
```

This approach is usually better for centralized querying when detailed prose is not needed. For systems with strict security requirements, detailed data can be stored in an appropriate location with separate access controls, while the log contains only permitted reference identifiers.

**Note on trailing newlines:** If a message already ends with `\n` and the formatter also appends a newline after the record, the console/file may show **a blank line**. Do not blindly `trim()` the entire message if whitespace is meaningful data; instead, control message output rules in the formatter or construct the string without a trailing newline when appropriate.

## 11. Common mistakes

| Mistake | Consequence | How to fix |
| --- | --- | --- |
| Treating every console line as a log event | Wrong event counts, broken context | Distinguish between a record and a physical line |
| Only the first line has timestamp/level | Continuation lines lose metadata in text files | Use one-line JSON or a multiline parser |
| Splitting one event into multiple log calls for pretty output | Lines interleave with separate timestamps/levels | Keep one event for one logical context |
| Logging CRLF directly from user input | Enables log forging and breaks parsers | Escape and sanitize untrusted data |
| Using only `logger.error(e.getMessage())` | Loses stack trace and causes | Pass `Throwable` to the logging API |
| Calling `printStackTrace()` outside logging | Errors lack correlation ID, level, and pipeline | Log exceptions through the backend |
| Using a formatter that only prints the message | Exception is passed to the record but never appears | Use a throwable-aware formatter/encoder |
| Pretty-printing JSON in a line-based pipeline | A single object is split into multiple entries | Use a compact JSON encoder |
| Logging full payloads or huge lists | High I/O, buffer overflow, truncation, and data leaks | Cap length, filter fields, and log summaries |
| Assuming stdout and stderr logs appear in exact merged order | Incorrect sequence reconstruction | Collect both streams, use timestamps and correlation IDs |
| Using `System.lineSeparator()` in data requiring a fixed format | Different bytes across operating systems | Choose the newline per the interchange contract |
| Escaping `\n` while ignoring `\r` | Control characters remain that can break structure | Handle CR, LF, and relevant control chars |

## 12. Checklist for designing a multiline message

1. **Clarify the purpose.** Is it for direct reading, debugging, stack traces, or a centralized log search system?
2. **Define event boundaries.** Do these lines share the same level, logger, timestamp, and correlation ID? If so, they should belong to a single event.
3. **Decide the format.** Multiline text with parser support, or a single-line structured event with escaped newlines in fields?
4. **Choose the right string construction.** `"\n"`, `String.join`, text block, or a list; avoid unnecessary trailing newlines.
5. **Preserve exception details.** Pass the `Throwable` and ensure the formatter can render or encode the stack trace.
6. **Validate external input.** Escape/serialize properly, cap length, and mask sensitive data.
7. **Test with the actual collector.** Test a multiline record, a stack trace, CRLF from input, concurrent writes from multiple threads, and log size limits.
8. **Verify the final stored data.** One source event should still be stored as a single queryable unit with `requestId`, level, timestamp, logger, and message intact.

**Key takeaway:** A message can contain multiple lines and still belong to **a single log event**. Multiline messages help convey rich details, but they require control over formatting, record boundaries, and untrusted data. For automated collection systems, prefer **a single-line structured event** or a verified multiline parser configuration, while preserving full exceptions and context for investigation.
