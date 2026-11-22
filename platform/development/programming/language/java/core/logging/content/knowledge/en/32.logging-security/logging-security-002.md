# Log Injection in Java: Preventing Forgery and Manipulation of Log Records

## 1. Lesson Objectives

**Log injection** occurs when data from an untrusted source is written into logs without being properly handled for the output format, allowing an attacker to alter how humans or log-reading tools interpret the record. The most common form is **log forging via newline characters**: a username, URL, header, or exception message containing CR/LF is logged verbatim, creating lines that look like legitimate application-generated events.

In Java, this issue is not limited to `System.out.println`. It can appear when using JUL, SLF4J/Logback, Log4j 2, a custom Formatter/Appender, or in a downstream collector/viewer. A thread-safe logging framework and placeholder-based logging **do not automatically protect against log injection**.

After completing this lesson, you will be able to:

1. Explain log injection, log forging, and the vulnerability **CWE-117 – Improper Output Neutralization for Logs**.
2. Identify data crossing the trust boundary: request parameters, usernames, HTTP headers, User-Agent, URLs, queue messages, file contents, exception messages, and MDC fields.
3. Distinguish record-boundary-breaking attacks using CR/LF, terminal/ANSI control sequences, JSON/CSV structure manipulation, visually confusing Unicode characters, and forged metadata.
4. Choose controls appropriate to the sink: validate values, enforce length limits, **encode/escape at write time**, use structured logging with a standard encoder, and prevent user input from controlling the event schema.
5. Write a standalone Java 17 example proving that malicious input remains within **one log event and one displayed line**.
6. Design tests from application code through to the collector/dashboard, covering attack detection, log loss, and alert distortion.

This lesson belongs to the **Logging Security** topic. Its goal is to protect **log integrity, traceability, and interpretability**; do not confuse it with attacks targeting databases or authentication mechanisms.

## 2. Attack Mechanism: How Data Becomes a "New Log Line"

Suppose an application logs a failed login as plain text:

~~~java
// Unsafe example: a client-supplied value is logged verbatim.
logger.warning("LOGIN_FAILED username=" + username);
~~~

With a normal username, the record might be:

~~~text
WARNING LOGIN_FAILED username=alice
~~~

However, the username could contain carriage return (CR, U+000D) and line feed (LF, U+000A) characters followed by forged text:

~~~text
alice\r\nINFO LOGIN_SUCCESS username=admin
~~~

In the block above, `\r` and `\n` represent two actual control characters, not two literal backslash-escaped characters stored as text. If the formatter/sink outputs the raw data into a line-based log, the actual output can be split:

~~~text
WARNING LOGIN_FAILED username=alice
INFO LOGIN_SUCCESS username=admin
~~~

The second line **is not a real LOGIN_SUCCESS event at all**, yet it can be misinterpreted by a dashboard, parser, or investigator. An attacker can forge timestamps, levels, actors, hosts, transaction IDs, or any fields that log readers rely on for classification.

This is **log forging**: falsifying records or altering their semantics. It is a common manifestation of **log injection**. Not every log entry containing a newline results in a successful exploit: the impact depends on the format, encoder, collector, schema, and how downstream systems parse it.

### Why Is This a Security Issue?

A forged log record can:

- Hide a sequence of failed logins by injecting a "login succeeded" message.
- Trigger false alerts, disrupting incident response workflows or risk analysis results.
- Attribute actions to an unrelated user, service, or IP address.
- Cause parsers to skip, mis-merge, or mislabel subsequent lines.
- Skew metrics, fraud detection, audit queries, and automated log-driven decisions.
- Exploit secondary vulnerabilities in a log viewer, terminal, or log-processing system if it fails to handle input safely.

Logs are **data that can contain attacker-controlled input**, even though the file is created on the server. Never treat log messages as unforgeable evidence merely because they were written by a trusted application.

## 3. Trust Boundaries in a Java Logging Pipeline

A log event typically passes through the following layers:

~~~text
HTTP request / message queue / external service / imported file
                 │
                 ▼
    Untrusted external data
                 │
                 ▼
    Java business code / exception / MDC
                 │
                 ▼
    Logger API: JUL, SLF4J, Log4j 2 API
                 │
                 ▼
    Formatter / Layout / Encoder / Appender
                 │
                 ▼
    stdout / stderr / file / syslog / broker
                 │
                 ▼
    container runtime / log collector / parser
                 │
                 ▼
    log database / SIEM / dashboard / alert
~~~

At **each boundary**, data may be represented differently:

- An HTTP request is URL-decoded and converted into a Java `String`.
- A `String` containing CR/LF or escape codes is embedded into a text log by a formatter.
- A JSON encoder converts newlines into escape sequences inside a JSON string.
- A collector may split logs by newline, parse JSON, drop invalid fields, or truncate oversized messages.
- A dashboard may render content as HTML, and a terminal may interpret ANSI escape sequences.

Therefore, protections must match **the actual format of the sink and consumer**. Calling `trim()` or `replace()` once in a controller is not enough to assume every downstream path is safe.

### Commonly Overlooked Data Sources

| Source | Logged Example | Issue |
| --- | --- | --- |
| Username, email, display name | "Login failed for …" | May contain CR/LF, quotes, delimiters, Unicode |
| Request URL and query string | "Request failed: …" | May contain percent-encoded data, secrets, very long strings |
| User-Agent, Referer, X-Forwarded-For | Access log / security log | Can be controlled by untrusted clients or proxies |
| Arbitrary HTTP headers | "header=value" | May have been decoded or normalized differently by proxies/parsers |
| Messages from a broker | "Payload rejected: …" | External producers may intentionally inject formatting characters |
| `Exception.getMessage()` | "Remote error: …" | Exceptions may carry user-supplied or third-party data |
| MDC/ThreadContext | trace_id, request_id, tenant | Not every field is server-generated; context can be forged |
| File names / paths | "Could not open …" | May contain delimiters, control characters, or PII |
| Object `toString()` | "Order: …" | May emit out-of-bounds data, oversized fields, or secrets |

Developer-authored log messages are a more reliable source for **event names**, but values interpolated into logs still need to be evaluated based on their origin.

## 4. Types of Log Injection to Distinguish

### 4.1. CR/LF and Separators: Breaking Record Boundaries

CR (`\r`) and LF (`\n`) are the two most common characters. On Unix systems, LF typically delimits lines; in many Windows environments, CRLF is used. Standalone CR, standalone LF, and Unicode line separators U+2028/U+2029 must all be considered according to the actual parser/renderer.

A malicious string might look like:

~~~text
attacker\n2026-11-10T02:00:00Z INFO AUTHORIZED user=admin
~~~

If the text encoder allows physical newlines, a consumer assuming "one line = one event" may create a new record. A parser that relies on a timestamp prefix can become even more severely confused.

**Mitigation:** Use structured events with an appropriate JSON encoder, or encode separators in untrusted values when producing line-based text logs; never let input determine the prefix, timestamp, level, or event name.

### 4.2. Terminal and ANSI Control Characters

The ESC character (U+001B) typically begins an ANSI control sequence. If logs are viewed in a terminal that interprets escapes, the content can change colors, move the cursor, clear parts of the screen, or mislead an operator. NUL, backspace, tab, and other control characters can also affect parsers or display output.

An example string in its safely represented form:

~~~text
alice\u001B[31m
~~~

Depending on the environment, `\u001B` in the example represents the ESC character; when properly escaped, it must appear as a literal backslash and the letter `u`, with no terminal control effect.

**Mitigation:** Ensure untrusted fields do not contain control sequences that affect terminals; encode or strip them according to policy for console text, and test your log-viewing tools. With JSON, JSON escaping handles control characters inside strings; however, a viewer must still render the data as plain text, not as HTML or trusted control content.

### 4.3. Directional and Invisible Unicode Characters

Certain Unicode characters can make the visual display order differ from the code point order: bidi override/isolate characters such as U+202E or U+2066–U+2069, zero-width space U+200B, and formatting marks U+200E/U+200F. Attackers can abuse them to make usernames, labels, or messages hard to read or compare.

**Mitigation:** Standardize display rules in dashboards and escape potentially risky control/directional characters at output according to field policy. Do not apply an "ASCII-only" filter to all Vietnamese names or multilingual text; valid Unicode must still be supported.

### 4.4. JSON, CSV, Key-Value, and Delimiters

A collector might expect:

~~~json
{"level":"WARN","event":"LOGIN_FAILED","username":"alice"}
~~~

If a developer builds JSON manually by string concatenation:

~~~java
// Wrong: username has not been JSON-escaped.
String line = "{\"level\":\"WARN\",\"username\":\"" + username + "\"}";
~~~

then quotes, backslashes, control characters, or newlines in `username` can make the JSON invalid or cause some parsers to misinterpret it. For CSV, commas, quotes, and newlines have their own escaping rules; for `key=value` formats, spaces and equals signs can inject extra fake "fields" if the parser is overly simple.

**Mitigation:** Use a tested serializer/encoder and supply data through dedicated fields; do not build JSON, CSV, or syslog messages with ad hoc string concatenation. A proper JSON encoder must serialize a `String` so that quotes, backslashes, and control characters cannot break out of the **string value**.

### 4.5. Spoofing Metadata and Altering Destination Configuration

An attacker does not necessarily need to break lines. If an application lets a client send a "log level", "role", "user_id", "trace_id", "severity", or logger name and records it as **server-verified metadata**, downstream systems can be misled even when the JSON is valid.

For example, the `actor` field in an audit event should come from the authenticated principal and server policy, not from a client-supplied username. Event type, level, logger name, index/route, and source service should come from trusted code or configuration; unverified data should only appear in **data fields** clearly marked with their origin.

**Important:** Log injection can cause harm even when the entire event stays on a single line: spoofing trusted-source fields is another way to corrupt observability data.

## 5. Things That Do NOT Automatically Prevent Log Injection

### 5.1. Placeholder Logging Is Not Output Escaping

SLF4J syntax:

~~~java
// Snippet; SLF4J/Logback or another SLF4J provider.
log.warn("LOGIN_FAILED username={}", username);
~~~

keeps the message template fixed and can reduce formatting overhead when the level is disabled. However, **if the appender uses a text pattern that outputs `%msg` verbatim and `username` contains CR/LF, the risk of log forging remains**.

Compare the two concerns:

- Placeholders prevent input from being merged into the **message template** before the logger processes it.
- Encoding/neutralization in the formatter/encoder protects the **emitted record format**.

You need both in their respective places, rather than picking one and ignoring the other.

### 5.2. "We Already Validated Username in the Form" Is Rarely Enough

Logs have many sources: URLs, headers, third-party services, exception messages, imported values, and legacy database records. A form's validation rules may not apply to every path reaching a logger. Moreover, characters can be percent-decoded, HTML-decoded, or Unicode-normalized at different stages.

Validate according to **field semantics** and encode according to **output context**, with a shared logging contract. Avoid double-decoding after validation, as that can reintroduce dangerous characters.

### 5.3. A Log Event Object Does Not Guarantee Valid JSON

A structured logging API may hold data as fields, but if it ultimately passes through an unescaped text layout or a custom appender that concatenates JSON manually, the output can still be vulnerable to injection. Always inspect the **actual bytes at the sink**, not just the data types at the call site.

### 5.4. A Thread-Safe Logger Does Not Solve Untrusted Content

Thread safety protects internal state and concurrent operations; it does not prevent a string containing CR/LF from turning into multiple lines. Do not confuse log forging with race conditions: they are two distinct classes of bugs.

## 6. Defense-in-Depth Principles

| Layer | Control | Why |
| --- | --- | --- |
| At input | Validate against schema/allowlist, length, and data type; reject invalid input where appropriate | Reduces dangerous data before it travels deep into the application |
| When building events | Use server-controlled event names/levels/keys and typed fields | Prevents clients from controlling structure or severity |
| When emitting text logs | Escape CR/LF, control characters, and format delimiters; cap per-field length | Ensures a single input cannot break record boundaries |
| When emitting JSON | Use a standard JSON encoder; write one JSON object/line per event | Preserves valid structure and character escaping |
| On the collector | Parse strictly by format, monitor malformed events, cap size, do not blindly trust display strings | Reduces ingestion errors |
| On the viewer | Escape HTML; never interpret log content as script/HTML; handle ANSI safely | Prevents injection at the presentation layer |
| On storage | Enforce access control, tamper resistance, retention, and access auditing | Protects evidence integrity and confidentiality |
| In testing | Fuzz control characters, JSON delimiters, Unicode, and oversized payloads | Catches formatting bugs and bypasses |

**Prefer "encode" over "strip everything" when security investigation is needed.** Turning CR into visible `\r` and LF into `\n` preserves the original data's meaning while preventing it from controlling line boundaries. If the system needs to retain raw input for deep analysis, store it in a separate, protected repository with appropriate data policies rather than embedding it verbatim in general logs.

### Processing Order

A sensible order for a single-line text event:

~~~text
Input is decoded and typed appropriately
      ↓
Field-level validation and size limits
      ↓
Select trusted metadata from the server
      ↓
Neutralize/escape values for the output log format
      ↓
Formatter/encoder produces a single record
      ↓
Appender → collector → backend
~~~

With a standard JSON encoder, **do not manually JSON-escape twice**. Instead of pre-escaping backslashes and then serializing that as a JSON string, pass the `String` value to the encoder; if you have custom policies for disallowed characters, length, or PII, apply those policies before serialization. The encoder is responsible for proper JSON escaping.

## 7. Complete Java 17 Example: Neutralizing Input Before Writing Text Logs

This example uses **java.util.logging (JUL)** built into the JDK, requiring no external libraries. We deliberately construct input containing CR, LF, ESC, and a bidi override character, then write it through a simple formatter to `System.out` to verify that the value is safely represented.

**File: LogInjectionDemo.java**

~~~java
import java.util.Locale;
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;
import java.util.logging.StreamHandler;

public final class LogInjectionDemo {
    private static final int MAX_CODE_POINTS = 80;

    // Example policy for a text field used in a single-line log.
    private static boolean needsEscaping(int codePoint) {
        return Character.isISOControl(codePoint)
                || codePoint == 0x200B
                || codePoint == 0x200E
                || codePoint == 0x200F
                || codePoint == 0x2028
                || codePoint == 0x2029
                || (codePoint >= 0x202A && codePoint <= 0x202E)
                || (codePoint >= 0x2066 && codePoint <= 0x2069);
    }

    private static String safeLogValue(String input) {
        if (input == null) {
            return "<null>";
        }

        StringBuilder out = new StringBuilder();
        int processed = 0;
        for (int offset = 0; offset < input.length();) {
            if (processed >= MAX_CODE_POINTS) {
                out.append("[truncated]");
                break;
            }

            int codePoint = input.codePointAt(offset);
            offset += Character.charCount(codePoint);
            processed++;

            switch (codePoint) {
                case '\r' -> out.append("\\r");
                case '\n' -> out.append("\\n");
                case '\t' -> out.append("\\t");
                default -> {
                    if (needsEscaping(codePoint)) {
                        out.append(String.format(
                                Locale.ROOT, "\\u%04X", codePoint));
                    } else {
                        out.appendCodePoint(codePoint);
                    }
                }
            }
        }
        return out.toString();
    }

    public static void main(String[] args) {
        Logger log = Logger.getLogger("example.security.LogInjectionDemo");
        log.setUseParentHandlers(false);
        log.setLevel(Level.INFO);

        StreamHandler console = new StreamHandler(
                System.out, new Formatter() {
                    @Override
                    public String format(LogRecord record) {
                        return record.getLevel().getName() + " "
                                + formatMessage(record)
                                + System.lineSeparator();
                    }
                });
        console.setLevel(Level.ALL);
        log.addHandler(console);

        // For demonstration only: input containing CR/LF and control characters.
        String untrustedUsername =
                "alice\r\nINFO LOGIN_SUCCESS actor=admin"
                + (char) 27 + "[31m"
                + Character.toString(0x202E);

        try {
            log.log(Level.WARNING,
                    "LOGIN_FAILED user={0} reason=BAD_PASSWORD",
                    safeLogValue(untrustedUsername));
            log.info("LOGGER_READY");
        } finally {
            console.flush();
            log.removeHandler(console);
            // Do not close the handler here to avoid closing System.out.
        }
    }
}
~~~

**Compile and run with JDK 17 or later:**

~~~bash
javac -encoding UTF-8 LogInjectionDemo.java
java LogInjectionDemo
~~~

**Expected stdout, exactly two lines:**

~~~text
WARNING LOGIN_FAILED user=alice\r\nINFO LOGIN_SUCCESS actor=admin\u001B[31m\u202E reason=BAD_PASSWORD
INFO LOGGER_READY
~~~

In the output, `\r`, `\n`, `\u001B`, and `\u202E` are all **visible escaped character sequences**, not actual control characters. They do not create a new `LOGIN_SUCCESS` line; only two `LogRecord` events are emitted by the program.

### Why Is This Code Safer Than the Initial Example?

1. The username data still preserves information needed for investigation, but CR/LF cannot split a single text event into two lines.
2. ESC and selected directional characters are represented by their code point escapes, limiting side effects when viewed in a terminal.
3. `MAX_CODE_POINTS` caps an oversized field on the logging path; the `[truncated]` marker lets investigators know the data was capped.
4. The logger, level, and message template are server-defined constants. Input cannot select the `INFO` level or fabricate a `LOGIN_SUCCESS` event.
5. `setUseParentHandlers(false)` prevents duplicate delivery to JUL's root handler—unrelated directly to injection, but it keeps the demonstration output deterministic.
6. `Formatter.formatMessage(record)` uses JUL's `{0}` template; the argument is already neutralized into a safe display value before the formatter writes to the sink.
7. `StreamHandler` is flushed in `finally` before inspecting stdout. The demo uses no threads or async loggers, so there is no interleaving to obscure the result.

### Intentional Limitations of This Example

- `safeLogValue` is an **escaper for line-based text logs**, not a JSON encoder, HTML encoder, URL sanitizer, or universal security filter for all formats.
- The limit is 80 **code points**, not 80 UTF-8 bytes or 80 UTF-16 code units. After escaping, the output byte length may be larger. The sink still needs an overall event size limit.
- The demo helper does not detect every Unicode character that can cause visual confusion; use a consistent policy/renderer and test with real languages and data.
- Do not copy this function to hundreds of call sites. In a real application, place neutralization/encoding logic in a shared logging wrapper or standard formatter/encoder so no call site is forgotten.
- For structured JSON, prefer a standard serializer per field to avoid double escaping; apply only data policy checks and field-specific limits beforehand.
- Never use escaping as a substitute for authentication: safely printing the name "admin" does not mean the sender of the input was authenticated as an admin.

## 8. SLF4J and Logback: Placeholders, MDC, and Encoders

### 8.1. Fixed Templates, Untrusted Fields

In an application using SLF4J + Logback:

~~~java
// Snippet; requires slf4j-api and a suitable Logback provider.
log.warn("Login rejected for username={}", username);
~~~

Using placeholders is **recommended**, but it is insufficient if the Logback `ConsoleAppender` uses a `PatternLayout` that outputs `%msg` verbatim. Input containing CR/LF can still appear as multiple physical lines.

If the application must format text lines, encode untrusted values according to policy at a standard point before logging, or use an encoder/layout with tested neutralization. Once a field-level policy is enforced in a wrapper, avoid calling `log.warn` directly with raw headers or usernames on other code paths.

### 8.2. Structured Logging

SLF4J 2.x snippet example:

~~~java
// SLF4J 2.x snippet; output depends on the provider and encoder.
log.atWarn()
        .addKeyValue("event_type", "LOGIN_FAILED")
        .addKeyValue("username", username)
        .addKeyValue("reason_code", "BAD_PASSWORD")
        .log("Login rejected");
~~~

Here `event_type` and `reason_code` are server-defined, while `username` is data. **A key-value logging API does not guarantee safety on its own** if the provider subsequently outputs unescaped text or if key-values are omitted from the formatter configuration. Verify that the actual Logback encoder writes events as valid JSON and properly escapes fields.

If your system uses the structured logging API of a different framework version, use the corresponding API rather than assuming SLF4J 2 syntax is available in SLF4J 1.7.

### 8.3. Do Not Put Arbitrary Data in MDC as Trusted Metadata

MDC/ThreadLocal commonly carries `request_id`, `trace_id`, `tenant`, and other context. However, MDC is just a context storage mechanism; if a client supplies a `request_id` containing CR/LF and the application interpolates it directly into `%X{request_id}`, injection risk still exists.

Better practices:

- Generate or validate IDs against a clear rule (e.g., hex/UUID characters) before putting them into MDC.
- Use a fixed set of context keys; never accept arbitrary MDC keys from clients.
- Set/clear or restore MDC inside `try/finally` so subsequent requests do not inherit stale context from a thread pool.
- Do not store access tokens, cookies, or full headers in MDC.
- Check how the backend layout/encoder serializes MDC into text or JSON.

**Note:** Propagating trace context over HTTP does not turn an ID into proof of identity. Authorization and actor must come from an authenticated auth context.

## 9. Log4j 2: Choosing Layouts and Handling Lookups/Formatting Separately

Log4j 2 also provides parameterized logging APIs and text/JSON layouts. In systems handling untrusted input, you should:

1. Keep the message template, logger name, level, and routing policy under code/configuration control.
2. Use an appropriate structured layout/encoder, such as JSON Template Layout when supported by your dependency version.
3. Never build JSON or dynamic patterns by concatenating client-supplied strings.
4. Test serialized output with CR/LF, quotes, backslashes, ESC, and special Unicode characters.
5. Limit both individual value sizes and total event size; a character-count limit on a string does not necessarily cap the total bytes produced.

**Distinguishing log injection from Log4Shell:** These two topics can both arise in logging, but they are not identical. Log injection/CWE-117 is primarily about **how untrusted data is represented in logs** to forge or corrupt records. Historical lookup/JNDI vulnerabilities involved special evaluation behavior in certain library versions. "Having upgraded Log4j 2" is not a reason to skip escaping or structured logging, and escaping CR/LF is no substitute for dependency and version security management.

Do not introduce vulnerabilities yourself by putting user input into file appender paths, dynamic logger names, route names, or template expressions without an allowlist. If you need multiple event types, use an enum or fixed set of names alongside controlled fields.

## 10. JUL: Handlers, Formatters, and Single-Event Invariants

In `java.util.logging`, `Logger` receives a `LogRecord`, `Formatter.format(LogRecord)` determines the output string, and `Handler` writes it to a sink. JUL supports handler propagation via parent loggers and level filtering, but **it has no built-in sanitizer that guarantees every untrusted `String` becomes a safe text line**.

Key control points:

- User input must be validated or encoded before `Formatter` writes the final format.
- Use a `Formatter` with a clear contract (e.g., single-line text with neutralized values, or a JSON formatter backed by a JSON serializer).
- Do not assemble a single log event via multiple separate writes to a shared stream; that hurts readability and increases line-interleaving risk in multithreaded applications.
- Do not use untrusted values arbitrarily as a `java.util.logging.Level`, logger hierarchy name, or file handler name.
- `ConsoleHandler` writes to `System.err` by default; `StreamHandler(System.out, formatter)` in the Section 7 example intentionally writes to `System.out` for easy stdout inspection.
- Do not confuse JUL's `formatMessage()` placeholder substitution with CR/LF escaping. They are two separate responsibilities.

With an established framework, it is usually better to use a maintained encoder rather than building a complex custom security `Formatter` from scratch. The Java 17 example helps you understand the mechanism, not as a recommendation to write a replacement logging stack.

## 11. JSON Lines and Choosing the Right Encoder

If a collector expects **one JSON object per line**, data inside strings must be JSON-escaped. For example, an actual username containing a quote and a newline:

~~~text
alice"\nadmin
~~~

A valid JSON line will look like:

~~~json
{"event_type":"LOGIN_FAILED","username":"alice\"\nadmin","level":"WARN"}
~~~

In the JSON line above, the quote inside `username` is represented as `\"` and the newline as `\n`; the entire event remains **a single line of valid JSON text**. Only when the JSON parser decodes the `username` field back into a `String` does the newline become a data character—not a new log line.

### Example with a JSON Serializer Library

The following is only a snippet for a project that includes Jackson; it requires the corresponding dependency and **does not** run standalone with JDK 17:

~~~java
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.LinkedHashMap;
import java.util.Map;

ObjectMapper mapper = new ObjectMapper();
Map<String, Object> event = new LinkedHashMap<>();
event.put("event_type", "LOGIN_FAILED");  // trusted constant
event.put("username", username);         // untrusted string as DATA
event.put("level", "WARN");              // trusted constant

String jsonLine = mapper.writeValueAsString(event);
logWriter.write(jsonLine);
logWriter.write("\n");
~~~

Jackson handles escaping within string fields, but this snippet still requires managing `Writer` lifecycle, encoding, concurrency, I/O errors, and appenders. Do not use a standalone write snippet like this as a custom production logger when your logging backend already provides a JSON encoder. If you use a `Map` yourself, ensure client-supplied keys cannot collide with privileged keys such as `actor`, `severity`, `timestamp`, or `event_type`.

**Recommendation:** Use your logging backend's structured JSON encoder and let the framework manage how many bytes/lines an event produces. Inspect the encoder's actual output in tests; a misconfigured JSON layout or broken parser can still cause the collector to drop records.

### Watch Out for Double Escaping

If you manually replace CR with the two characters `\r` and then pass that to a JSON serializer, the JSON output will contain an extra backslash. While syntactically valid, the consumer receives the neutralized value rather than the original `String`. Agree on a single contract: raw values are properly escaped by the JSON encoder; text-line values are neutralized by the text encoder; data policies such as length limits and redaction are applied consistently before serialization.

### Single Events with Multiline Stack Traces

Real exceptions can have multiline stack traces. This is not always an injection. For line-oriented text logging, configure multiline aggregation or use a JSON encoder that places the stack trace into a properly escaped field, rather than banning all exception details. The key is distinguishing **event boundaries created by the logger** from **newline characters originating in untrusted data**.

## 12. Size Limits: Preventing Log Flooding and Resource Exhaustion

Beyond event spoofing, oversized log data can cause:

- Increased CPU usage during encoding, escaping, formatting, or parsing.
- GC and memory pressure, slowing down hot paths.
- Full stdout buffers, queues, disks, or storage backends.
- Log ingestion timeouts, mid-record truncation, or partial record loss.
- Higher costs and harder searches for high-value events.

Design limits per **field** and per **total event**:

| Component | Recommendation |
| --- | --- |
| username / device name | Cap to realistic data lengths; no need to log huge values in full |
| URL / User-Agent | Cap length; strip query secrets or log a path template |
| Remote exception message | Log error code/exception type and a safe summary |
| JSON log event | Cap field count, string sizes, and total bytes after encoding |
| Log rate | Controlled rate limiting/sampling without blinding security events |
| Pipeline | Configure buffers, retention, and alerts for dropped/invalid events |

A limit measured in code points differs from a limit in **UTF-8 bytes**, and escaping can expand output size. If downstream limits are measured in bytes, measure the encoded output.

When truncating data, attach `truncated=true` or a standardized suffix. Never slice in the middle of a UTF-8 sequence, a JSON escape, or a record delimiter, which would render the event unparseable.

Critical security logs may need a dedicated retention policy; do not drop all authentication failures simply due to high volume. Combine metrics, alerts, and deliberate limits on detailed payload fields.

## 13. Ensuring Metadata Integrity

A safe record should have system-determined metadata:

~~~json
{
  "event_type": "AUTHENTICATION_FAILED",
  "severity": "WARN",
  "actor_id": null,
  "attempted_username": "alice",
  "request_id": "req-b39c",
  "source": "auth-service",
  "outcome": "REJECTED"
}
~~~

The JSON above only illustrates schema design. When authentication has not succeeded, **`actor_id` must not be set to a trusted account just because the client supplied a username**. Use `attempted_username` for the client-claimed value. Only set `actor_id` to a server-verified identity once the principal is authenticated.

Fields like `event_type`, `severity`, `actor_id`, `source`, `outcome`, and access-control decisions must originate from trusted logic/configuration. If a client sends values keyed as `"severity"` or `"actor_id"`, place them in a separate allowlisted data field; never blindly merge an untrusted `Map` into the root event.

### Trace ID and Correlation ID

If the system accepts a W3C `traceparent` from a request, the trace ID may be upstream-supplied data and requires standard validation. It helps correlate logs across a trace, **not prove that a user is authenticated**. For security decisions, actor and privileges must come from a verified auth context.

Misconfigured or uncleared MDC in a thread pool can cause another form of log corruption: request B carrying request A's `request_id`. This is a context lifecycle issue that should be tested alongside injection so investigators are not led to the wrong request.

## 14. Rendering and Injection After Logs Are Stored

A JSON event can be written cleanly yet still become dangerous when a viewer uses the data in the wrong context:

- If an HTML UI inserts a message into `innerHTML` without escaping, log content can cause XSS in the viewer. Use `textContent` or proper framework escaping.
- If logs are opened in a terminal that interprets ANSI, control sequences can garble the screen; display escaped/plain text when viewing untrusted data.
- When exporting to CSV, cells starting with formula characters can trigger **CSV/formula injection** in spreadsheet software; apply appropriate mitigations at export time, not just JSON encoding at write time.
- Passing a log message into a shell command, SQL query, template engine, or system prompt for execution crosses a **new trust boundary**. Never treat log content as trusted instructions.
- If a collector treats "a line starting with a timestamp = one record", test multiline messages and multiline aggregation rules.

Never assume a single encode step in Java suffices for every consumer. Every transition into a new context (HTML, CSV, terminal, shell) must be protected for that context.

## 15. Testing Log Injection with Controlled Data

Do not only test that `safeLogValue` returns a clean string. Inspect **actual output from the formatter/appender and collector**.

### 15.1. Test Matrix

| Input / Scenario | Primary Risk | Expected Result |
| --- | --- | --- |
| Normal username: `alice` | Baseline | Exactly one event logged with literal value |
| CRLF: `alice` + CR + LF + fake `INFO` | Log forging | No forged `INFO` event or line |
| LF-only or CR-only | Parser-dependent record split | Does not create a new event boundary |
| Tab, NUL, ESC/ANSI | Terminal/parser control | Rendered escaped or handled safely |
| U+2028, U+2029, U+202E | Line break / display reversal | Safe output; semantics unchanged |
| Quotes and backslashes in JSON | JSON syntax injection | Parses as one valid JSON object; field retains data |
| Commas/quotes/newlines in CSV export | Broken CSV structure | Properly escaped by CSV exporter |
| Very long string | Log flood / resource exhaustion | Truncated per policy; event remains valid |
| Vietnamese Unicode username | Over-sanitization | Valid data is not corrupted |
| Input containing token/PII | Data exposure | Redacted/omitted before storage |
| Forged `actor_id`/`admin` header | Metadata spoofing | `actor_id` comes from auth context, not header |
| Exception containing input | Indirect injection channel | Message/stack trace passes through safe encoder |
| Concurrent requests | Context mix-up or interleaved records | Each event has the right `request_id`, no cross-merging |
| Backend/collector disconnected | Log loss / silent drop | Metrics, retry/buffer policy active; no false success |

### 15.2. Recommended Assertions

1. For every logger call that emits an event, the collector receives the exact designed structure (no extra events spawned from input).
2. For single-line text, physical line count increases strictly by the number of events; values with newlines appear escaped, without creating new lines.
3. For JSON Lines, each line parses into a single JSON object and all fields have the expected types.
4. Event type, level, actor, and source cannot be altered by client-supplied input.
5. Overlong input includes a `truncated` marker/state and does not break the encoder or drop the entire log.
6. No unauthorized secrets or PII appear in main logs, error logs, debug logs, or appender error output.
7. Security-critical logs are still recorded per policy even when input is invalid; **invalid fields** may be dropped or neutralized, but do not silently drop the entire security event.

### 15.3. Fuzzing and Integration Tests

Use control characters, Unicode, and random strings in unit tests for your sanitizer/encoder. Then run integration tests against the actual logger backend, layout, container collector, and dashboard you will deploy. Whenever you upgrade Logback/Log4j 2 or change layout configuration, re-run tests; relying solely on mocked APIs is not enough to prove the final output is safe.

Do not use production logs to test large volumes of payloads. Log storm tests, max-size tests, and slow-collector tests should be run in an authorized, resource-bounded environment.

## 16. Common Mistakes

**Mistake 1 – Replacing CR/LF with a space and stopping there.**  
This may block a simple text log forging variant, but leaves control characters, format delimiters, Unicode, and viewer issues unaddressed. For JSON, use standard JSON escaping rather than just replacing newlines.

**Mistake 2 – Assuming SLF4J placeholders prevent injection automatically.**  
Placeholders do not force a text `PatternLayout` to escape CR/LF. You still need an appropriate formatter/encoder and field policy.

**Mistake 3 – Logging raw requests for "complete evidence".**  
Raw URLs, headers, and bodies can contain secrets, PII, huge payloads, and disruptive characters. Use an allowlist of fields; if raw evidence must be retained, store it in a separate repository with strict access and retention controls.

**Mistake 4 – Building JSON with string concatenation.**  
JSON becomes invalid or manipulable when quotes/newlines are not properly escaped. Use a verified serializer or structured encoder.

**Mistake 5 – Using client data as `event_type`, `severity`, or `actor`.**  
Structured events can still suffer metadata spoofing. Event classification and principal must be determined by the server.

**Mistake 6 – Sanitizing in the controller but forgetting exceptions/MDC.**  
Data can take many indirect paths before reaching a logger. Enforce policy at a shared layer close to the event/encoder, in addition to field-level validation.

**Mistake 7 – Dropping the entire log when input is invalid.**  
An injection attempt itself can be an important security signal. Emit a safe security event, strip/escape the malicious field, and never let input control the log level or auth outcome.

**Mistake 8 – Having the log viewer treat log data as trusted HTML.**  
Even successfully parsed JSON logs still contain user content; the renderer must contextually text-escape it.

**Mistake 9 – Testing only the sanitizer without checking the collector.**  
Collectors may split multilines, reformat, or re-export data. Test end-to-end from the appender to the dashboard and any automated analysis workflows.

**Mistake 10 – Conflating format security with library security.**  
Fixing log forging does not replace dependency updates, log file permission management, retention controls, or addressing independent parser/lookup vulnerabilities.

## 17. Applying This to a Real Java Project

A design can be rolled out in the following steps:

1. **Inventory log fields:** `event_type`, `severity`, `service`, `trace_id`, `actor_id`, `attempted_username`, `result`, `error_code`. Clearly define which fields are server-generated and which are client-supplied.
2. **Design a shared logging API:** A module that emits events with stable names and schemas; business classes should not assemble ad hoc text from HTTP headers.
3. **Choose encoding:** For containerized services, structured JSON on console is usually simplest for collectors; if using text lines, require neutralization on every untrusted field.
4. **Bound inputs:** Measure per-field length and total bytes after encoding; use field allowlists and avoid logging secret payloads.
5. **Enforce policy at the output boundary:** The encoder controls record delimiters and encoding; never let input write directly to a file sink or route.
6. **Verify context:** MDC/ThreadContext is scoped properly and clients cannot overwrite principal or level.
7. **Configure collector and viewer:** Parse JSON against a schema, quarantine invalid events, render as text, and enforce access control and retention.
8. **Test:** CRLF, ANSI, Unicode, JSON/CSV delimiters, overlong values, concurrency, exception messages, downstream failures, and security-event continuity.
9. **Monitor after deployment:** Parse-error event counts, truncated/dropped events, log rate anomalies, policy changes, audit access, and event-to-backend latency.

### Architecture of Responsibilities

~~~text
Controller / Consumer
   ├── Validate input according to business rules
   └── Pass data along; do not format logs ad hoc
             │
             ▼
      SecurityEvent API
   ├── Event names and log levels are approved constants
   ├── Metadata comes from trusted authentication/context
   ├── Policies for length, sensitive data, and schema
   └── Untrusted fields are marked with their source
             │
             ▼
       Logging backend
   ├── Standard JSON encoder or escaping text encoder
   └── Tested Appender/Handler
             │
             ▼
        Collector / SIEM
   ├── Parse, enforce schema and event size
   ├── Quarantine/metrics for malformed data
   └── Access control and safe rendering
~~~

This does not mean building lots of custom framework code. You can leverage existing logging backends and encoder libraries; what matters is **the data contract and testing trust boundaries**.

## 18. Practice Exercises

### Exercise 1 – Reproduce Log Forging in a Test

Starting from `LogInjectionDemo.java`, use normal input and input containing CR/LF. Compare a `Formatter` that logs the raw username against `safeLogValue`, in a **test environment disconnected from real monitoring systems**. Check the physical line count and explain which consumers a forged `LOGIN_SUCCESS` line could deceive.

### Exercise 2 – Extend the Unicode Policy

Add test cases with U+200B, U+202E, U+2028, U+2029, and accented Vietnamese text. Ensure control characters are escaped while valid Vietnamese characters are preserved intact. Distinguish length in code points vs. UTF-8 bytes.

### Exercise 3 – JSON Serializer

In a project with Jackson, create a `LOGIN_FAILED` event with a username containing quotes, backslashes, and newlines. Serialize with `ObjectMapper`, parse it back with `ObjectMapper`, and assert that the original username is restored accurately, **`event_type`** is unchanged, and the output remains a single JSON line.

### Exercise 4 – Protect Metadata

Suppose a client sends headers `actor_id=admin` and `event_type=LOGIN_SUCCESS`. Design a `SecurityEvent` API so authentication status, `actor_id`, and `event_type` are derived server-side; store untrusted headers only in a dedicated field if needed for investigation and permitted by security policy.

### Exercise 5 – End-to-End with a Collector

Use your project's real logging configuration (JUL/Logback/Log4j 2) and collector in a test environment. Send CR/LF, ANSI, oversized payloads, and exceptions containing untrusted input. Verify event counts, schema, retention, and dashboard rendering; record invalid/truncated events without dropping the overall security signal.

## 19. Key Takeaways

**Log injection is not just "a string with a newline".** It is the problem of introducing untrusted data into a log format or metadata field in a way that causes humans, parsers, or pipelines to misinterpret an event. CWE-117 covers improper handling of special characters in logs; log forging is a common consequence.

In Java, follow these principles: **server-determined event names and trusted metadata; untrusted values validated, bounded, and encoded for the output format; standard serializers/encoders for structured JSON; and log viewers/collectors continuing to treat log data as untrusted input**. SLF4J placeholders are useful, but they do not replace escaping. Always test the final bytes and record counts, especially whenever logging backend, collector, or viewer configurations change.

### References

- MITRE CWE-117 – Improper Output Neutralization for Logs: https://cwe.mitre.org/data/definitions/117.html
- OWASP Logging Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html
- OWASP Log Injection: https://owasp.org/www-community/attacks/Log_Injection
- SEI CERT IDS03-J – Do not log unsanitized user input: https://wiki.sei.cmu.edu/confluence/display/java/IDS03-J.+Do+not+log+unsanitized+user+input
- Oracle Java 17 – java.util.logging.Logger: https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Logger.html
- Oracle Java 17 – java.util.logging.Formatter: https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Formatter.html
- Oracle Java 17 – java.util.logging.StreamHandler: https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/StreamHandler.html
- SLF4J User Manual: https://www.slf4j.org/manual.html
- Logback – Configuration: https://logback.qos.ch/manual/configuration.html
- Log4j 2 – Layouts: https://logging.apache.org/log4j/2.x/manual/layouts.html
