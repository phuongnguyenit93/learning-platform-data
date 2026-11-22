# JSON Escaping in Java Logging: Writing Safe, Syntactically Valid, and Easy-to-Collect JSON Logs

## 1. What is JSON Escaping?

**JSON escaping** is the process of representing characters that have special meaning or are not allowed to appear directly in a **JSON string** using valid escape sequences. When a Java application logs in JSON, dynamic data such as messages, exception messages, URLs, file names, request IDs, or user-provided content may contain double quotes, backslashes, newlines, and control characters. If these values are concatenated directly into JSON, the record can become **syntactically invalid**, split across multiple lines, or lose field boundaries.

For example, a message containing double quotes and a newline:

~~~text
Java value at runtime:
user said "OK"
next line

Valid JSON string representation:
"user said \"OK\"\nnext line"
~~~

In the JSON representation above, `\"` represents a double quote **that belongs to the string content**, while `\n` represents a newline character **inside the value**. When reading the JSON, the parser restores the exact original string. In a JSON Lines log file, the entire record can stay on **a single physical line**, even though the original string contains a newline.

**Important:** JSON escaping **does not** mean stripping characters, encrypting secrets, converting data to URL-encoded form, or turning arbitrary text into a safe JSON object. Escaping is a **syntax rule for JSON string values and string keys**.

Example of a structured JSON log:

~~~json
{"level":"INFO","eventCode":"USER-1001","message":"user said \"OK\"\nnext line","requestId":"req-17"}
~~~

The parser interprets this as **one object** with four fields; the `message` value contains two lines in memory after JSON decoding. A collector designed for NDJSON can process one record per line because the newline character in the message is escaped rather than appearing as a raw newline inside the string.

## 2. Characters Required to Be Escaped in JSON

According to **RFC 8259, Section 7 (Strings)**, JSON strings are enclosed in double quotes. The three groups that **must** be escaped inside string content are:

1. Double quote `"` (U+0022).
2. Backslash `\` (U+005C).
3. Control characters from **U+0000 through U+001F**, including tab, LF, and CR.

Short escape sequences supported by JSON:

| Character in data | Character sequence in JSON text | Meaning |
| --- | --- | --- |
| `"` | `\"` | Double quote |
| `\` | `\\` | Backslash |
| Backspace U+0008 | `\b` | Backspace |
| Form feed U+000C | `\f` | Form feed |
| Line feed U+000A | `\n` | Line feed (LF) |
| Carriage return U+000D | `\r` | Carriage return (CR) |
| Tab U+0009 | `\t` | Tab |
| Forward slash `/` | `\/` if desired | Escaping slash is **optional**, not required |
| Remaining control chars U+0000–U+001F | `\u00XX` | Unicode representation with four hex digits |

For example, the NUL character (U+0000) can be represented as `\u0000`. The JSON string `"a\u0000b"` can still be decoded by a parser back into a string containing NUL; how downstream systems accept or display that character is a separate concern.

**It is not required to escape every Unicode character.** In UTF-8 encoded JSON text, Vietnamese characters such as “đ”, “ế”, “ộ” and emoji characters can appear directly if properly encoded. Representing them with `\uXXXX` or surrogate pairs `\uXXXX\uYYYY` is also valid. The two representations differ in **JSON text bytes**, but decode to the same **string value**.

Some encoders choose to also escape `/`, non-ASCII characters, or U+2028/U+2029 for compatibility with a specific embedded environment. That is an encoder/context policy, **not a mandatory RFC 8259 requirement for all JSON strings**.

## 3. Three Easily Confused Syntax Layers: Java Source, JSON Text, and Parsed String

When writing examples, it is important to separate three perspectives:

1. **Java source literal:** code containing backslashes to construct a string at runtime.
2. **Java String at runtime:** the actual sequence of characters, which may include newlines, tabs, or quotes.
3. **Serialized JSON text:** the sequence of bytes/characters representing the data in JSON syntax, typically containing backslashes for escapes.

Example in Java:

~~~java
String message = "first\nsecond";
~~~

In the source code, `\n` is two characters in the Java literal notation, whereas the runtime value of `message` has **one actual LF character** between `first` and `second`. When a logger outputs the message through a JSON encoder, the message value in JSON text typically appears as:

~~~json
{"message":"first\nsecond"}
~~~

In the JSON file above, the two characters `\` and `n` represent the LF character inside the value; a reader does not see a new physical line inserted between `first` and `second`. When read by a parser, `message` is restored to a string containing the actual LF.

### Backslashes in paths

Java string literal:

~~~java
String path = "C:\\logs\\app.log";
~~~

The runtime value is the Windows path `C:\logs\app.log`. When serialized into a JSON string, the backslashes must be escaped:

~~~json
{"path":"C:\\logs\\app.log"}
~~~

If written raw as `{"path":"C:\logs\app.log"}`, sequences like `\l` and `\a` are not valid JSON escapes; a parser may reject the entire record. Never replace only double quotes and forget backslashes.

### Do not double-escape

A JSON encoder that receives the **original Java string value** will escape it properly during serialization. If application code manually replaces newlines with the literal text `\n` beforehand and then passes it to the encoder, it can produce `\\n` in the JSON text. The parser will then receive two characters—a backslash and “n”—**not the original newline**.

**Right:** pass the raw value through the encoder's typed API.

**Wrong in many situations:** call a custom escape function, then pass the already-escaped result into `ObjectMapper.writeValueAsString(...)` or a JSON layout as if it were still raw data.

## 4. Why Is JSON Escaping Especially Important for Logging?

A log often contains data from **trust boundaries**: HTTP headers, URIs, user agents, file names, exception messages, queue payloads, or responses from dependencies. This data can contain `"`, `\`, or CR/LF.

If JSON is built via string concatenation:

~~~java
// WRONG: illustrative snippet, not a standalone program.
String json = "{\"level\":\"INFO\",\"username\":\""
        + username + "\"}";
~~~

with `username` containing:

~~~text
alice","level":"ERROR","fake":"1
~~~

string concatenation can let user data break out of the **string value** and create unintended JSON fields (or cause duplicate keys, leading parsers and downstream consumers to interpret them differently). That is a form of **JSON injection** in logs. Some parsers may accept an object with duplicate keys or pick the last value; an application should never rely on such behavior when handling untrusted logs.

With proper JSON string escaping, the value becomes a single string:

~~~json
{"level":"INFO","username":"alice\",\"level\":\"ERROR\",\"fake\":\"1"}
~~~

The data contains text that looks like JSON keys, but the parser does not treat them as additional fields.

**Escaping does not mean you can log everything.** Strings such as tokens, passwords, and personal data must still be omitted, masked, or restricted by policy before output. JSON escaping only protects **structural representation**, not **sensitive content**.

## 5. JSON Lines / NDJSON: One Log Event per Physical Line

For operational logs, a common format is **NDJSON/JSON Lines**, where each line ends with a newline and contains **one complete JSON object**:

~~~text
{"level":"INFO","eventCode":"ORD-1001","message":"Checkout started"}
{"level":"WARN","eventCode":"ORD-1501","message":"Retry after timeout\nsecond attempt"}
{"level":"ERROR","eventCode":"ORD-1500","message":"Checkout failed"}
~~~

There are **three physical lines**, corresponding to three events; the `\n` in the second message is a JSON escape and does not create an extra event. This one-event-per-line property is convenient for file/stream reading agents, indexers, and command-line tools.

To configure NDJSON properly:

- The encoder/layout must output **one valid JSON object** per event, without inserting free-form log text between objects.
- Each event ends with the **exact line boundary** expected by the pipeline; newlines **inside strings** must be escaped.
- Do not enable multi-line pretty-printing if the collector assumes one event per line. Pretty-printing may still produce valid JSON, but it breaks the NDJSON assumption.
- Do not write non-JSON banners, debug lines, or status messages to the same stream that the collector strictly parses as NDJSON, unless the pipeline has a way to handle them.
- A JSON object may have a field containing a long stack trace, but the stack trace must be encoded as a valid string or structure.
- When a log exceeds size limits, the encoder/collector may truncate the record; the file may end up with incomplete JSON. Monitor event lengths and configure intentional limits.

**NDJSON does not mean a JSON array.** The three-line content in the example is not a single JSON document wrapped in `[`/`]`, but three independent JSON documents, one per line.

## 6. Java 17: Runnable Example with JUL and JSON Escaping

The following example uses **JDK 17 only**, with no Maven required. The goal is to demonstrate:

1. Quotes, backslashes, LF, tabs, and control characters are escaped inside JSON strings.
2. Events have fixed fields and typed data (e.g., `attempt` is a number).
3. Exception messages containing newlines do not split the record across lines.
4. Non-ASCII Unicode can be represented with `\uXXXX` or **valid surrogate pairs**.
5. Data that looks like JSON syntax remains inside a single string value once escaped.

**Scope note:** we write a small escape helper here to learn the mechanism; this manual serializer is not recommended for production. In real applications, choose a maintained, tested JSON encoder/serializer with policies for untrusted data.

Create **JsonEscapeLoggingDemo.java**:

~~~java
import java.util.logging.Formatter;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;
import java.util.logging.StreamHandler;

public final class JsonEscapeLoggingDemo {
    private static final Logger LOG =
            Logger.getLogger(JsonEscapeLoggingDemo.class.getName());
    private static final char[] HEX =
            "0123456789abcdef".toCharArray();

    private JsonEscapeLoggingDemo() {
    }

    private static void appendUnicodeEscape(StringBuilder out, char value) {
        out.append("\\u");
        for (int shift = 12; shift >= 0; shift -= 4) {
            out.append(HEX[(value >>> shift) & 0x0f]);
        }
    }

    private static String quoteJson(String value) {
        if (value == null) {
            throw new IllegalArgumentException("Expected non-null text");
        }

        StringBuilder out = new StringBuilder("\"");
        for (int i = 0; i < value.length(); i++) {
            char ch = value.charAt(i);
            switch (ch) {
                case '"' -> out.append("\\\"");
                case '\\' -> out.append("\\\\");
                case '\b' -> out.append("\\b");
                case '\f' -> out.append("\\f");
                case '\n' -> out.append("\\n");
                case '\r' -> out.append("\\r");
                case '\t' -> out.append("\\t");
                default -> {
                    if (Character.isHighSurrogate(ch)) {
                        if (i + 1 == value.length()
                                || !Character.isLowSurrogate(
                                        value.charAt(i + 1))) {
                            throw new IllegalArgumentException(
                                    "Unpaired high surrogate");
                        }
                        appendUnicodeEscape(out, ch);
                        appendUnicodeEscape(out, value.charAt(++i));
                    } else if (Character.isLowSurrogate(ch)) {
                        throw new IllegalArgumentException(
                                "Unpaired low surrogate");
                    } else if (ch < 0x20 || ch > 0x7e) {
                        appendUnicodeEscape(out, ch);
                    } else {
                        out.append(ch);
                    }
                }
            }
        }
        return out.append('"').toString();
    }

    private static final class JsonLineFormatter extends Formatter {
        @Override
        public String format(LogRecord record) {
            Object[] p = record.getParameters();
            String eventCode = (String) p[0];
            String requestId = (String) p[1];
            int attempt = (Integer) p[2];

            StringBuilder out = new StringBuilder("{\"level\":");
            out.append(quoteJson(record.getLevel().getName()));
            out.append(",\"eventCode\":").append(quoteJson(eventCode));
            out.append(",\"requestId\":").append(quoteJson(requestId));
            out.append(",\"attempt\":").append(attempt);
            out.append(",\"message\":").append(quoteJson(record.getMessage()));

            Throwable error = record.getThrown();
            if (error != null) {
                out.append(",\"errorType\":")
                   .append(quoteJson(error.getClass().getSimpleName()));
                out.append(",\"errorMessage\":")
                   .append(quoteJson(error.getMessage()));
            }

            return out.append("}\n").toString();
        }
    }

    private static void configureLogger() {
        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.ALL);

        Handler stdout = new StreamHandler(
                System.out, new JsonLineFormatter()) {
            @Override
            public synchronized void publish(LogRecord record) {
                super.publish(record);
                flush();
            }
        };
        stdout.setLevel(Level.ALL);
        LOG.addHandler(stdout);
    }

    private static void emit(
            Level level, String eventCode, String requestId,
            int attempt, String message, Throwable error) {
        LogRecord record = new LogRecord(level, message);
        record.setParameters(new Object[] {
                eventCode, requestId, attempt
        });
        record.setThrown(error);
        LOG.log(record);
    }

    public static void main(String[] args) {
        configureLogger();

        emit(Level.INFO, "AUD-1001", "req-1", 2,
                "user said \"OK\"\nnext line", null);

        emit(Level.SEVERE, "AUD-9001", "req-2", 3,
                "path=C:\\temp\\logs\tfailed",
                new IllegalStateException("bad\nstep"));

        System.out.println("unicode=" + quoteJson("café🚀"));
        System.out.println(
                "payload=" + quoteJson("X\"},\"level\":\"ERROR"));
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 JsonEscapeLoggingDemo.java
java JsonEscapeLoggingDemo
~~~

**Exact expected stdout** (the `\n` and `\t` sequences below are **literal escape characters displayed**, not actual line breaks or tabs):

~~~text
{"level":"INFO","eventCode":"AUD-1001","requestId":"req-1","attempt":2,"message":"user said \"OK\"\nnext line"}
{"level":"SEVERE","eventCode":"AUD-9001","requestId":"req-2","attempt":3,"message":"path=C:\\temp\\logs\tfailed","errorType":"IllegalStateException","errorMessage":"bad\nstep"}
unicode="caf\u00e9\ud83d\ude80"
payload="X\"},\"level\":\"ERROR"
~~~

**Why are there exactly four physical lines?**

- The two `emit(...)` calls create two `LogRecord` instances. The formatter outputs each record as a JSON object and appends one newline **outside the object**.
- Newlines and tabs **inside** `message` or `errorMessage` are converted by `quoteJson(...)` into `\n` and `\t`; they do not insert extra physical lines.
- `attempt` is appended as an unquoted integer, so the JSON field has a number type.
- `errorType` and `errorMessage` are emitted only when `record.getThrown()` is non-null.
- `quoteJson("café🚀")` produces `\u00e9` for “é” and `\ud83d\ude80` for the rocket U+1F680. This is a valid representation using JSON Unicode escapes, with no character loss after parser decoding.
- The fake payload `X"},"level":"ERROR` is escaped as a string; it cannot inject a `level` field into the object created by the formatter.
- The logger uses a `StreamHandler` writing to stdout, disables parent handlers, and flushes after each record. The example omits dynamic timestamps so the expected stdout stays deterministic.

**This is an intentionally minimal demo.** It does not print full stack traces, does not guarantee compatibility with all invalid Unicode inputs, has no external schema management, and enforces no length limits. For `errorMessage`, if the exception message is null, the helper throws an exception; in production, use an explicit null policy and an encoder capable of handling that case. Do not copy this formatter into a live system without adding tests and logging resilience mechanisms.

### 6.1. Why check surrogate pairs?

Java `String` stores data as **UTF-16 code units**. Characters outside the BMP, such as the rocket U+1F680, take **two code units**: a high surrogate `D83D` and a low surrogate `DE80`. JSON can represent it with the escape pair `\ud83d\ude80`.

A lone high surrogate, or a low surrogate without a preceding high surrogate, does not represent a valid Unicode scalar value. RFC 8259 notes that strings containing unpaired surrogates can lead to **inconsistent behavior** across parsers and applications. The demo intentionally throws `IllegalArgumentException` if it encounters an invalid pair, rather than silently producing output that is hard to interoperate with.

**Distinguish** “a character within the BMP” from “each user-perceived character takes one Java char”: Unicode has combining marks and multi-code-point emoji sequences. If you need to limit log length by user-perceived characters, `String.length()` is not equivalent to the number of grapheme clusters.

### 6.2. Is it mandatory to convert every accented letter to \uXXXX?

No. The demo uses an **ASCII-only output** policy to clearly show Unicode escapes and keep expected stdout stable across consoles. Valid UTF-8 JSON can keep “café🚀” directly as appropriate UTF-8 bytes; a proven serializer can be configured to either preserve or escape these characters.

**Do not use `\uXXXX` as a way to hide sensitive data.** Readers can decode it back identically. It is still the original data, just in a different representation.

## 7. Use a JSON Serializer/Encoder Instead of Manual String Concatenation

In real applications, the right choice is to pass **typed values** into a JSON serializer or structured logging encoder. For example, using Jackson's API in a project **with the appropriate dependencies declared**:

~~~java
// Illustrative snippet, NOT standalone with only JDK 17.
// Requires com.fasterxml.jackson.databind.ObjectMapper and Jackson dependencies.
com.fasterxml.jackson.databind.ObjectMapper mapper =
        new com.fasterxml.jackson.databind.ObjectMapper();

java.util.Map<String, Object> event =
        new java.util.LinkedHashMap<>();

event.put("level", "INFO");
event.put("eventCode", "ORD-1001");
event.put("message", "user said \"OK\"\nnext line");
event.put("attempt", 2);
event.put("requestId", "req-17");

String json = mapper.writeValueAsString(event);
// The JSON serializer protects the boundary of each string value.
~~~

In valid cases, the serializer handles escaping for `"`, `\`, control characters, and Unicode according to configuration. It also distinguishes `attempt=2` as a **number** rather than `"2"`, and can serialize `true`, `false`, `null`, arrays, and objects according to schema.

Do not use `Map.toString()`, `Object.toString()`, or `String.format("{...}")` as a substitute for a JSON serializer: they are not designed to guarantee valid JSON for arbitrary data.

### 7.1. Avoid double escaping

~~~java
// Incorrect data handling when the serializer will also escape:
String preEscaped = userMessage.replace("\n", "\\n");
event.put("message", preEscaped);
String json = mapper.writeValueAsString(event);
~~~

If `userMessage` contains a real newline, `preEscaped` contains the two characters `\` and `n`. The serializer then escapes the backslash, causing the parser to receive **a backslash and the letter “n”**, not the original newline.

**Right:** pass `userMessage` directly into the field, letting **one final component** handle serialization for the JSON context.

### 7.2. Do not put “pre-built JSON” into a string field as an object

A value like `"{\"status\":\"ok\"}"` is a **string containing JSON-like text**, not an object. When the serializer writes it into a `details` field, the output looks like:

~~~json
{"details":"{\"status\":\"ok\"}"}
~~~

If you want `details` to be an object with a `status` field, parse and validate the data against a schema and pass the validated object/map to the serializer. **Do not strip quotes with replace** to “turn a string into an object,” as that can open the door to injection or produce invalid JSON.

### 7.3. Non-string values

A valid record:

~~~json
{"attempt":2,"success":false,"durationMs":12.5,"error":null,"tags":["backend","retry"]}
~~~

If every value is wrapped in quotes, `2` becomes `"2"` and `false` becomes `"false"`, corrupting data types and affecting queries. Conversely, never let arbitrary input flow directly into an **unquoted** value position.

JSON does not allow `NaN`, `Infinity`, or `-Infinity` as number literals under RFC 8259. If a Java source has `Double.NaN` or infinities, the encoder needs a policy such as rejecting, converting to `null`, or converting to a string per schema; never emit invalid tokens and treat the result as standard JSON.

## 8. Escaping Stack Traces and Exception Messages

Exceptions can contain Windows paths, quotes, newlines, tabs, SQL text, or dependency responses. If a layout writes JSON Lines with `error.stack_trace` as a string, every newline in the stack trace must be **escaped inside the JSON string** so the collector does not interpret `at ...` lines as new events.

**Illustrative** example:

~~~json
{"level":"ERROR","eventCode":"DB-9001","message":"Database read failed","error":{"type":"java.io.IOException","message":"read failed","stack_trace":"java.io.IOException: read failed\n\tat example.Store.read(Store.java:42)\nCaused by: java.net.SocketException: reset"}}
~~~

In an NDJSON file, this remains **one physical line**. A JSON parser restores `stack_trace` with newlines and tabs in their proper positions inside the string.

There are two separate decisions:

1. **Preserving the Throwable:** in Java, pass the exception to the proper overload so the backend can access the stack trace, cause, and suppressed exceptions.
2. **Serializing the Throwable:** the encoder decides whether to render it as a single string, split it into a structured object/array, or abbreviate it per policy.

With JUL, `LogRecord.getThrown()` retains the Throwable if set via `Logger.log(Level, String, Throwable)` or `LogRecord.setThrown(...)`. In the demo in Section 6, the formatter intentionally outputs only `errorType` and `errorMessage`; it **does not print the full trace**. For production error logging, use a formatter/encoder with full Throwable support or configure a clear schema to preserve causes and suppressed exceptions when needed.

### 8.1. The logging API does not automatically guarantee JSON-safe output

Code like:

~~~java
// Illustrative example in a service with an SLF4J logger and Throwable e.
LOG.error("operation=load path={} failed", path, e);
~~~

is the right way to pass parameterized data and a Throwable. However, **parameterized messages do not automatically escape JSON** if the backend is using a text `PatternLayout`. To get JSON output, you need a **JSON encoder/layout** at the final stage.

**Avoid manually encoding fields before passing them to the log API:** if the appender already has a JSON encoder, you can cause double escaping, corrupting parsed values and hurting searchability.

### 8.2. Stack traces can be very large

A long cause chain or many suppressed exceptions can produce tens of kilobytes or more. Escaping newlines to `\n` also increases output bytes slightly. You should:

- Limit log volume and avoid logging the full stack redundantly at every layer.
- Set maximum lengths for messages/fields per safety policy; mark when truncated.
- When truncating Unicode strings, never cut in the middle of a surrogate pair or cause the encoder to emit an invalid string.
- Check agent/collector limits, which may truncate records even when the encoder produces valid JSON.
- Measure increases in bytes/s, CPU/allocations, and p95/p99 under load.

Never assume every JSON log with a stack trace is stored intact just because the encoder succeeded; the pipeline after the encoder can still truncate or drop it.

## 9. JSON Logging in SLF4J, Logback, and Log4j2

### 9.1. SLF4J is an API; the encoder belongs to the backend

SLF4J provides logger calls, placeholders, and in version 2.x a fluent key/value API:

~~~java
// Illustrative snippet in an application with an SLF4J 2.x Logger LOG.
LOG.atInfo()
   .addKeyValue("eventCode", "ORD-1001")
   .addKeyValue("requestId", requestId)
   .addKeyValue("messageSource", source)
   .log("Order accepted");
~~~

This is an API for emitting events with key/value pairs; it **does not automatically turn output into JSON**. The provider/backend must have a layout/encoder that supports writing these entries as actual fields. Do not take a text line like `eventCode=...` and assume the collector already has an `eventCode` field if it has not been parsed.

### 9.2. Logback: choose an appropriate JSON encoder

With Logback, a common choice is a dedicated JSON encoder, such as from the `logstash-logback-encoder` library when the project declares the dependency and selects a compatible version. **Illustrative configuration snippet, not runnable standalone without dependencies**:

~~~xml
<!-- Snippet from logback.xml; requires the appropriate encoder module. -->
<appender name="JSON_STDOUT"
          class="ch.qos.logback.core.ConsoleAppender">
    <encoder class="net.logstash.logback.encoder.LogstashEncoder"/>
</appender>
~~~

The exact output and how MDC, markers, Throwables, or structured arguments are emitted depend on the encoder, version, and configuration. **Do not replace a text encoder's `<pattern>` with a pseudo-JSON string** containing unescaped `%msg`, because messages with quotes or newlines can break the JSON.

Modern Logback also offers other capabilities and encoders depending on the version. Choose an encoder with documented JSON string escaping, charset, newline separation, Throwable handling, and field names, then test it with tricky inputs like those in Section 6.

### 9.3. Log4j2: JSON Template Layout

Apache Log4j 2 recommends **JSON Template Layout** for structured logging. Plugin configuration depends on the appropriate module, such as `log4j-layout-template-json` along with compatible dependencies. Illustrative XML snippet in `log4j2.xml`:

~~~xml
<!-- Snippet inside <Appenders>; requires the JSON Template Layout module. -->
<Console name="JSON_STDOUT" target="SYSTEM_OUT">
    <JsonTemplateLayout/>
</Console>
~~~

JSON Template Layout uses templates/resolvers to build JSON according to a schema. The encoder handles string quoting/escaping for the message field and other fields per configuration. If you want custom fields, verify the resolver, data type, field presence, and the collector's contract.

**Do not confuse this with:** Log4j2 `PatternLayout`, which uses converters like `%msg` for text. Writing a manual pattern like:

~~~xml
<!-- WARNING: do not use as a production JSON encoder. -->
<PatternLayout pattern='{"message":"%msg"}%n'/>
~~~

does not guarantee valid JSON if the message contains `"`, `\`, or raw newlines. Use a JSON layout/template or an encoder with proper escaping instead of expecting `%msg` to escape for a JSON context.

### 9.4. Custom JUL Formatter

JUL has `java.util.logging.Formatter` and `LogRecord`. It does not include a JSON serializer in the Java SE 17 standard library. You can use a trusted serializer inside a custom `Formatter` or a suitable backend. The demo in Section 6 mainly shows how to quote a string; it **does not replace a JSON library in a real system**.

## 10. JSON Escaping and Log Injection: Common Scenarios

### 10.1. CRLF attack forging a new record

Payload from a request:

~~~text
guest
ERROR eventCode=SEC-9000 accessGranted=true
~~~

If a logger writes the raw message directly to a line-based text file, an attacker can make a normal message produce a line starting with `ERROR` that looks like a separate event. This is a form of **log forging / log injection**.

With a proper JSON encoder in NDJSON, the payload is placed in a string field and the newline is escaped:

~~~json
{"level":"INFO","username":"guest\nERROR eventCode=SEC-9000 accessGranted=true"}
~~~

The parser sees one INFO event; the text after `\n` remains part of the `username` value, not an independent event. However, a UI displaying the decoded value may render the line break; UIs and alerts must treat the data as **data**, never re-parsing decoded text into log records using regex.

### 10.2. Payload containing quotes and braces

Payload:

~~~text
x","admin":true,"role":"root
~~~

In a standard JSON encoder, the internal quotes become `\"`, without creating `admin` or `role` fields on the object. However, if an encoder disables escaping in a “raw JSON mode” or the app concatenates strings manually, the structure can be broken.

**Rule:** an untrusted string is always a **string value**; never treat it as a trusted JSON syntax fragment. If you need to accept JSON data from a client, parse and validate it against a schema before placing allowed parts into logs.

### 10.3. Oversized payload

A megabyte-long request header, even when properly escaped, can still produce an oversized log event, causing high CPU/memory usage, full queues, truncated records, or high ingest costs.

Limit **source length**, field count, event rate, and which fields are allowed to be logged. When truncating values, avoid losing diagnostic clues; you can retain the original length, a validation error code, and a bounded safe sample.

### 10.4. Sensitive data still leaks even when JSON is valid

A log like:

~~~json
{"level":"INFO","accessToken":"secret-value"}
~~~

is syntactically valid JSON, yet still unsafe logging. Escaping does not hide tokens. Never treat wrapping data in a JSON string as redaction; minimize data at the source, enforce access controls, manage retention, and monitor access.

## 11. Unicode, Surrogate Pairs, Charset, and Compatibility

### 11.1. JSON Unicode and UTF-8

RFC 8259 specifies that JSON text exchanged between systems outside a closed ecosystem must use **UTF-8**. Encoders should declare and emit bytes in the appropriate charset, typically UTF-8, so Vietnamese characters and non-ASCII characters do not suffer from mojibake.

Example of UTF-8 JSON text:

~~~json
{"message":"Đơn hàng đã hoàn tất","emoji":"🚀"}
~~~

It can also be emitted by escaping non-ASCII characters:

~~~json
{"message":"\u0110\u01a1n h\u00e0ng \u0111\u00e3 ho\u00e0n t\u1ea5t","emoji":"\ud83d\ude80"}
~~~

Both representations are designed to decode to the same string value. The second takes more bytes in many cases, but can be useful for ASCII-only output or deterministic tests.

### 11.2. Unpaired surrogates

A Java `String` can contain a lone high surrogate or low surrogate `char`. These do not form a valid Unicode scalar value. RFC 8259 warns about **unpaired surrogate** handling across implementations. If you write a serializer yourself, define an explicit policy: **reject**, replace with the replacement character U+FFFD with appropriate error tracking, or rely on a proven encoder.

Do not silently truncate a UTF-16 string at a character limit that might split the two code units of an emoji. If the log pipeline limits bytes or code points, enforce the limit according to policy while keeping the JSON output valid.

### 11.3. Forward slash and characters when embedding JSON in HTML

`/` does not need to be escaped in JSON. However, if you **embed JSON directly into HTML or JavaScript source**, additional HTML/JavaScript context rules apply (e.g., `<`, `&`, script-closing sequences, U+2028/U+2029 in some environments). **Plain JSON escaping is not HTML escaping or JavaScript-source escaping**.

In pure NDJSON log files, there is no need to escape forward slashes just to be “valid JSON.” When rendering to an HTML interface, escape in the **HTML rendering context** or use safe UI DOM APIs rather than reusing raw JSON text as HTML markup.

## 12. Testing JSON Escaping Properly

### 12.1. Tests you should have

| Case | Input data | Expected result |
| --- | --- | --- |
| Quote | `a"b` | `a\"b` inside JSON string |
| Backslash | `C:\logs` | `C:\\logs` in JSON text |
| LF | String with real newline | `\n` in JSON text; no extra physical line |
| CRLF | Real `\r\n` | `\r\n` encoded |
| Tab | Real tab character | `\t` |
| NUL/control | U+0000–U+001F | Short escape or `\u00XX` |
| Unicode BMP | `é` or `ế` | Raw UTF-8 or valid Unicode escape |
| Non-BMP Unicode | `🚀` | Raw UTF-8 or pair `\ud83d\ude80` |
| Unpaired surrogate | Lone high/low surrogate | Tested reject/replace policy |
| Injection quote | `x","admin":true` | Entire text stays inside one string value |
| JSON-like text | `{"admin":true}` | Does not become a nested object |
| Null Java value | `null` | Null field, omitted, or rejected per schema; no accidental NPE |
| Number/boolean | `2`, `false` | Preserves proper type, not quoted arbitrarily |
| Non-finite number | `NaN`, `Infinity` | Does not emit invalid JSON number tokens |
| Exception message | Contains quote/newline/backslash | One valid event, Throwable matches schema |
| Very long input | Many KB/MB | Safe limit, not truncated into invalid JSON |

**Do not rely on visually inspecting output strings alone.** A strong test should:

1. Emit JSON logs through the real backend/encoder.
2. Use an **independent JSON parser** to parse each line.
3. Verify the line/event count, field names, field types, and values **after decoding**.
4. Compare the parsed value against the original Java string (including newlines, tabs, and Unicode).
5. Run cases with attacker-controlled input, error messages, and stack traces.
6. Verify that the collector actually stores one event, without truncation or duplication.

### 12.2. With NDJSON, validate line by line

Suppose `events.jsonl` contains one independent JSON object per event. When `jq` is available:

~~~bash
jq -c . events.jsonl
~~~

This command parses each JSON text in the file in sequence and emits a compact version if the data is valid. For a single JSON array or single JSON document file, handling differs; **NDJSON is not an array**.

If Python 3 is available, you can validate line by line:

~~~python
import json
from pathlib import Path

lines = Path("events.jsonl").read_text(encoding="utf-8").splitlines()
parsed = [json.loads(line) for line in lines]
print("events=", len(parsed))
~~~

This is a snippet illustrating a testing tool, **not a required component of Java 17**. Do not use `python -m json.tool events.jsonl` as a validation check for an entire NDJSON file if the tool expects a single JSON document.

### 12.3. The difference between “valid JSON” and “business-valid log”

A log can parse as valid JSON and still be wrong:

- `level` is turned into an attacker-controlled field.
- `eventCode` is built from request IDs, causing unbounded cardinality.
- `durationMs` is a string instead of a number.
- Stack trace is truncated, losing the root cause.
- Request ID in MDC from a previous request leaks across a thread pool.
- Logs are written but dropped in a queue or collector.

Therefore, verify **syntax, schema, data, event semantics, and the collection path**. JSON escaping only solves the syntax part, even though it is a mandatory part.

## 13. Performance and Operations

A typical JSON encoder must build fields, encode strings, escape special characters, and write bytes to output. At high log volumes, total cost can affect CPU/GC and disk/network I/O.

Key considerations:

- **Parameterized logging:** use templates and arguments instead of arbitrary message concatenation; remember Java still evaluates argument expressions before calling the logger.
- **Structured fields:** keep message text short and use named, typed fields to avoid expensive regex parsing.
- **Size limits:** cap field count, message length, stack trace length, and event bytes per policy; careless truncation after encoding can break JSON.
- **UTF-8:** use consistent charset settings from the JVM/encoder all the way to the collector.
- **NDJSON:** one JSON object per line, with newlines inside strings escaped.
- **Async logging:** can reduce blocking on request threads, but requires monitoring queues, drops, flush/shutdown, and durability.
- **Validation:** the encoder is part of the pipeline; if log data is invalid, handle it explicitly without triggering an error-logging loop inside the formatter itself.
- **Observability:** measure bytes/s, events/s, queue depth, dropped/truncated events, CPU, allocations/GC, p95/p99 latency, and JSON parse errors at the collector.

There is no need to write a custom “optimized” escape function when proven encoders already exist. A single-character bug in a serializer can break ingest across millions of records; safety and maintainability matter far more than a minor `StringBuilder` microbenchmark.

## 14. Common Mistakes and How to Fix Them

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Concatenating user input directly into `{"message":"..."}` | Injection or broken JSON | Use a serializer/structured encoder for string values |
| Escaping only `"` and forgetting `\` | Paths like `C:\logs` break JSON | Escape quotes, backslashes, and control characters |
| Writing raw newlines inside JSON strings | NDJSON splits lines, invalid JSON | Escape newlines to `\n` |
| Replacing `\n` manually before passing to a JSON encoder | Double escaping, wrong parsed value | Serialize once at the final boundary |
| Using `Map.toString()` as JSON | No guarantee of valid JSON | Use a JSON serializer |
| Using `PatternLayout` to hand-craft JSON with `%msg` | Messages can break structure | Use JSON Template Layout or a proper encoder |
| Assuming SLF4J `addKeyValue` produces JSON by itself | Output may still be plain text | Configure a supporting backend/encoder |
| Missing control chars U+0000–U+001F | Parser rejects logs | Enforce full JSON string rules |
| Replacing `'` with `\'` | `\'` is not a valid JSON escape | JSON uses `\"` for double quotes; apostrophes do not need escaping |
| Converting all Unicode to `?` | Loss of Vietnamese text/emojis | Write UTF-8 or valid Unicode escapes |
| Truncating in the middle of a surrogate pair | Corrupted Unicode string, inconsistent parsers | Truncate on valid boundaries or let the encoder handle it |
| Quoting numbers/booleans | Wrong schema types | Serialize typed values |
| Writing raw `NaN` or `Infinity` | Invalid RFC 8259 JSON | Reject/convert per schema |
| Escaping properly but still logging tokens | Secret leakage | Omit or mask sensitive fields |
| Parser allows duplicate keys | Level/metadata may be misinterpreted | Never concatenate raw JSON from input; validate keys via schema |
| Leaving raw multi-line stack traces outside the object | Collector splits events, loses context | Escape inside a field or use structured throwable |
| Custom formatter throws on null | Lost logs and pipeline disruption | Handle null/invalid data intentionally |
| Too many fields/large strings | High CPU, disk, queue, and ingest cost | Enforce limits and measure throughput |
| Assuming valid JSON means logs reached the collector | Records may be dropped/rotated/truncated | Monitor the pipeline end-to-end |

## 15. JSON Logging Implementation Checklist

1. **Define the target format:** a single JSON document or one-event-per-line NDJSON? Configure the collector accordingly.
2. **Use a reliable encoder:** Logback/Log4j2/JUL or a maintained JSON library; do not concatenate JSON strings.
3. **Keep fields typed:** timestamp, level, eventCode, requestId, durationMs, error type; do not quote every value indiscriminately.
4. **Escape strings completely:** quotes, backslashes, control chars U+0000–U+001F; handle Unicode and surrogate pairs properly.
5. **Do not double-escape:** pass original strings to the encoder; encode once at serialization.
6. **Preserve Throwables when needed:** pass exceptions to the logging API and encode stack/cause/suppressed appropriately.
7. **Limit data:** avoid logging secrets/PII, huge payloads, or oversized objects.
8. **Propagate context properly:** requestId/traceId/MDC do not automatically cross every executor; clear context at scope end.
9. **Test with a parser:** parse each line with an independent JSON parser and compare decoded values.
10. **Verify ingest:** confirm collector, index, alerts, retention, and UI display preserve field semantics.
11. **Test performance:** load test with quotes, newlines, Unicode, and long exceptions; measure log bytes/s, CPU, GC, and queues.
12. **Secure logs:** enforce log permissions, prevent log forging, protect archives/backups, and avoid exposing internal stack traces in responses.
13. **Check compatibility:** when upgrading encoder/framework versions, test schema and escaping, especially for Throwable fields.
14. **Monitor failures:** alert on unparseable JSON records, truncated events, encoding errors, and dropped logs.

## 16. Self-Check Exercises

1. **RFC 8259:** list the characters that must be escaped in a JSON string. Is escaping `/` as `\/` mandatory? Must an apostrophe `'` be escaped?
2. **Distinguish syntax layers:** explain the difference between the Java literal `"a\nb"`, its runtime value, and the JSON text representing the same value.
3. **Run Java 17:** create `JsonEscapeLoggingDemo.java`, run the two `javac`/`java` commands, and compare the four stdout lines. Why is the JSON log not split even though the message contains a newline?
4. **JSON injection:** a user submits the username `x","role":"admin`. If code concatenates it into a JSON string manually, what is the risk? With a standard encoder, can that value still create a `role` field?
5. **Backslash:** given the Windows path `C:\temp\logs`, write a valid JSON string containing it. Why does `\t` take on a different meaning if not properly escaped?
6. **Unicode:** distinguish JSON text containing “café🚀” directly from `"caf\u00e9\ud83d\ude80"`. Can both decode to the same Java String?
7. **Surrogates:** if a Java string contains a high surrogate without a low surrogate, why should it be intentionally rejected/replaced instead of silently emitted?
8. **Double escaping:** explain why pre-escaping `\n` before passing a string to Jackson can cause the parser to receive the two characters `\` and `n`.
9. **Schema:** an event has `attempt=2` and `success=false`. When serializing via a Map/object, how do you preserve number and boolean types instead of strings?
10. **Throwable:** if an exception message contains LF and a multi-line stack trace, how can they be stored in a single JSON Lines record?
11. **Structured logging:** is SLF4J 2.x `addKeyValue` alone enough for the collector to see independent JSON fields? What backend condition is still required?
12. **Validation:** build a test suite with quotes, backslashes, tabs, CRLF, NUL, emojis, very long inputs, and sensitive data. State assertions for the parser, line count, schema, and privacy.

## 17. Official References

- RFC 8259 — JSON Data Interchange Format, Sections 7 and 8: https://www.rfc-editor.org/rfc/rfc8259.html
- OWASP — Logging Cheat Sheet, log injection and data to exclude: https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html
- Apache Log4j 2 — Layouts/structured logging: https://logging.apache.org/log4j/2.x/manual/layouts.html
- Apache Log4j 2 — JSON Template Layout: https://logging.apache.org/log4j/2.x/manual/json-template-layout.html
- SLF4J Manual — Fluent logging API: https://slf4j.org/manual.html
- Java SE 17 — `java.util.logging.Formatter`: https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Formatter.html

**Key takeaway:** **JSON escaping is essential for syntactically valid strings in JSON logs**, especially for `"`, `\`, and control characters U+0000–U+001F. In Java logging, use a reliable encoder/serializer instead of string concatenation; keep **one event per line** if your pipeline uses NDJSON; avoid double escaping; handle Unicode, Throwables, and field types according to schema; and remember that **JSON escaping does not replace sensitive-data controls, overload protection, and log collection monitoring**.
