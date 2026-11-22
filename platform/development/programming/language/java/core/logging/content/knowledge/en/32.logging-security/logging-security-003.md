# Log Forging in Java Logging

## 1. Concept and Security Goals

**Log forging** (falsifying log records), often considered a form of **log injection**, occurs when untrusted data is written into logs without being neutralized appropriately for the output format. An attacker can insert newline characters, delimiters, control characters, or forged structures to make it appear as though the application emitted additional events, altered data fields, concealed errors, or distorted log collection and analysis.

For example, an application logs a username when a login fails. If the username contains **CR/LF**, a single input string can appear as **two physical log lines**, where the second line mimics the timestamp, level, or content of another event.

This vulnerability is associated with **CWE-117: Improper Output Neutralization for Logs**. The core issue is not that Java has a single dangerous API, but that a **trust boundary** is crossed: externally controlled content is treated as log syntax.

Log forging can:

- **Falsify incident evidence:** create fake INFO or ERROR records to mislead investigations.
- **Conceal activity:** inject an “authentication succeeded”, “access granted”, or distracting message after a real error.
- **Break or mislead parsers:** trick parsers that rely on timestamps, levels, delimiters, or multiline stack traces.
- **Trigger or suppress alerts falsely:** if alerting relies on message regexes or line counts rather than event structure.
- **Distort audits:** undermine accountability when audit logs and diagnostic logs are not separately protected.

**Do not confuse log forging with directly modifying log files.** An attacker does not necessarily need file write permissions; they may only need to control a value that the application logs. That is why log forging is especially relevant in web applications, APIs, message consumers, and background workers.

## 2. Which Input Data Can Become Log Injection?

Any value flowing from a less-trusted zone into a logger must be considered:

| Source | Commonly Logged Examples | Risks |
| --- | --- | --- |
| HTTP request | URL path, query string, User-Agent, Referer | CR/LF, forged timestamp/level strings, control characters |
| Form or JSON body | username, email, search term, message text | Line injection or breaking field structure |
| HTTP headers | X-Request-ID, X-Correlation-ID, forwarded metadata | ID spoofing, overly long values, invalid characters |
| Message broker | message key, header, payload field | Control characters and repeated redeliveries causing noise |
| File names and paths | Uploaded filename, path segment | Newline characters, delimiters, hard-to-see Unicode characters |
| Error messages | Exception message, response from dependency | Externally controlled content embedded into logs |
| Database | User-generated data, display name | Stored log injection: malicious data logged after being read from DB |

A value retrieved from a database **does not automatically become trusted** simply because it has been stored. If a user created the data, it can still carry a confusing or malicious payload when later read and logged.

The same risk applies to **MDC (Mapped Diagnostic Context)**: if an application takes a raw **requestId** from an external header and puts it into MDC, every log emitted during that request may contain the same forging payload when the pattern/encoder outputs that value.

Trace the full path:

~~~text
Untrusted request/message/database value
        |
        v
Java String / exception message / MDC
        |
        v
Logger API
        |
        v
Formatter / encoder / appender
        |
        v
Console / file / collector / SIEM / dashboard
~~~

Each stage may have its own parsing rules. A value that is safe when properly JSON-encoded is not necessarily safe if it is later decoded and interpolated directly into an HTML template or a text-based alert.

## 3. The Simplest Mechanism: CRLF Injection

CR is carriage return (**\r**, U+000D), and LF is line feed (**\n**, U+000A). They are control characters used to terminate or move lines. In a line-oriented text logging environment, if a message contains CRLF and the formatter does not neutralize those characters, a single event can look like multiple lines.

Illustrative input example:

~~~text
guest\r\n2026-11-10T02:42:00Z INFO user=admin action=login_success
~~~

In the snippet above, **\r\n** represents CR and LF; when the actual payload contains those two control characters, the raw log can be split into:

~~~text
2026-11-10T02:41:59Z WARN event=login_rejected user=guest
2026-11-10T02:42:00Z INFO user=admin action=login_success
~~~

The second line is not necessarily emitted by the application; it may simply be **the remainder of a user-supplied value**. If a collector splits events by newline and the search engine interprets the second line as an independent event, investigators can be misled.

Distinguish between a **log event** and a **physical line**:

- One event can legitimately have a multiline message, such as a stack trace.
- One physical line does not always correspond to one business event.
- Attackers exploit confusion between these two concepts and parsers that lack reliable framing.

**Do not rely on the logger “already having a timestamp” for protection.** The timestamp is added by the formatter at the start of the event; a user payload can still inject a fake timestamp string in the middle of the message.

## 4. Beyond CR/LF: Field and Format Injection

A logging system may use text formatted like:

~~~text
level=WARN user=guest status=denied event=login_failed
~~~

If the application directly interpolates `userInput`, an attacker can supply strings such as:

~~~text
guest status=success role=admin
~~~

This string contains no newline, yet it contains **delimiters and key=value pairs**. If the search engine or parser splits on whitespace and takes the last occurrence of a field, the record can be misinterpreted.

Other forms include:

1. **Quotation/delimiter injection:** adding quotes, commas, pipes, tabs, or equals signs to break out of a text or CSV field.
2. **JSON injection:** manually concatenating JSON strings without a serializer, producing malformed JSON or allowing data content to alter object structure.
3. **Terminal control injection:** ESC/ANSI characters can change colors, clear lines, or produce misleading output when a terminal tool interprets control sequences.
4. **Unicode visual spoofing:** bidirectional control characters, invisible characters, or Unicode line/paragraph separators can cause viewers and parsers to interpret text differently.
5. **Multiline framing confusion:** user data or exception messages are incorrectly grouped or split by a collector into multiple log events.
6. **Log viewer injection:** malicious data is rendered in an HTML dashboard without escaping. This is a presentation-layer risk that can lead to XSS; do not conflate it by default with CRLF forging at the storage layer.

**You cannot protect every format with the same string replacement.** Writing key=value text, JSON, CSV, syslog, and HTML requires encoding rules tailored to each target format.

## 5. Why Parameterized Logging Is Not a Complete Solution

In SLF4J, developers often write:

~~~java
logger.warn("Login rejected for user={}", username);
~~~

Instead of:

~~~java
logger.warn("Login rejected for user=" + username);
~~~

Using placeholders has benefits: it avoids string concatenation before checking whether the log level is enabled, keeps the message template stable in certain configurations, and reduces formatting errors. However, **placeholders do not automatically neutralize CR/LF, delimiters, or control characters**. When the formatter writes `username` into text, dangerous characters can still be preserved if the encoder does not handle them.

**Parameterized logging is not the same as SQL prepared statements.** SQL parameter binding defines how values are represented in the query language; SLF4J placeholders are not a syntax-safe binding mechanism for every log sink.

Nor can you rely solely on the **logger API**: whether a value is escaped depends on the **formatter/encoder, schema, collector, and display application**. Apply defenses at the input boundary or at the log-event creation boundary depending on the field type and designed format.

## 6. Standalone Java 17 Example: Raw Log vs. Neutralized Log

The following example intentionally simulates a CRLF payload to demonstrate the difference between **two physical lines** and **an escaped value**. The program uses only Java SE 17, without SLF4J or Logback.

Create the file **LogForgingDemo.java**:

~~~java
import java.util.Locale;

public class LogForgingDemo {
    private static String escapeField(String input) {
        if (input == null) {
            return "<null>";
        }

        StringBuilder output = new StringBuilder();
        for (int i = 0; i < input.length();) {
            int cp = input.codePointAt(i);
            i += Character.charCount(cp);

            switch (cp) {
                case '\\' -> output.append("\\\\");
                case '"'  -> output.append("\\\"");
                case '\r' -> output.append("\\r");
                case '\n' -> output.append("\\n");
                case '\t' -> output.append("\\t");
                default -> {
                    boolean risky =
                            Character.isISOControl(cp)
                            || cp == 0x2028
                            || cp == 0x2029
                            || Character.getType(cp) == Character.FORMAT;
                    if (risky) {
                        output.append("\\u{")
                              .append(Integer.toHexString(cp)
                                      .toUpperCase(Locale.ROOT))
                              .append("}");
                    } else {
                        output.appendCodePoint(cp);
                    }
                }
            }
        }
        return output.toString();
    }

    public static void main(String[] args) {
        String input = "guest\r\n"
                + "2026-11-10T02:42:00Z INFO user=admin action=login_success";

        String raw = "WARN event=login_rejected user=\"" + input + "\"";
        String safe = "WARN event=login_rejected user=\""
                + escapeField(input) + "\"";

        System.out.println("rawPhysicalLines=" + raw.lines().count());
        System.out.println("safePhysicalLines=" + safe.lines().count());
        System.out.println("safeRecord=" + safe);
    }
}
~~~

Compile and run on JDK 17 or later:

~~~bash
javac LogForgingDemo.java
java LogForgingDemo
~~~

Exact stdout of the program:

~~~text
rawPhysicalLines=2
safePhysicalLines=1
safeRecord=WARN event=login_rejected user="guest\r\n2026-11-10T02:42:00Z INFO user=admin action=login_success"
~~~

Explanation:

1. The **input** string in Java actually contains CRLF because the source code uses the **\r\n** escape sequence.
2. **String.lines()** treats CRLF as a line terminator, so the raw record has two physical lines.
3. **escapeField** turns CR/LF into a backslash followed by the letter **r/n**, without creating a new line break. Thus `safeRecord` is a single physical line.
4. The method also escapes double quotes, backslashes, tabs, control characters, Unicode U+2028/U+2029, and characters in the Unicode FORMAT category to mitigate visual spoofing.
5. The method operates by **code point** so it does not split valid Unicode surrogate pairs.
6. **\u{HEX}** is a custom illustrative text representation for uncommon control/format characters; **it is not standard JSON escape syntax**. Do not use this method in place of a JSON serializer.
7. Quoting the `user` field in text logs is only safe if downstream parsers **understand and respect the quote/escape convention**. A naive parser that splits on whitespace can still see `key=value` tokens inside a quoted string.

**Limitations of this example:** this is a neutralization helper for a simulated text log format, not a general-purpose anti-log-forging library for every sink. In production, prefer tested encoders and serializers, use allowlists for identifier fields, and write tests at the collector/parser layer. The “safe” record in this example only proves it is not split by CRLF; it does not prove every parser is immune to confusion.

## 7. Why Format-Appropriate Output Escaping Matters

Defenses should be based on the **output context**:

| Output | Appropriate Approach | Notes |
| --- | --- | --- |
| Line-oriented text logs | Escape CR, LF, delimiters, and control chars per grammar | Verify that the parser understands the escaping |
| JSON logs | Use a compliant JSON encoder/serializer | Do not manually concatenate quotes and keys from input |
| CSV | Use a CSV writer that handles quotes/delimiters/newlines | CSV can be valid even with multiline fields; check the pipeline |
| Syslog or custom protocols | Follow the protocol's framing/escaping rules | Avoid embedding CR/LF outside the record framing contract |
| HTML log viewer | Context-aware HTML escaping and an appropriate CSP | This is the presentation layer, not just the logger layer |
| Alert message/chat webhook | Escape/neutralize for target Markdown/HTML/JSON | Do not let user text become alerting system syntax |

A **JSON encoder** is often a strong choice because each log event is packaged as an object and string fields are escaped by the serializer. However, “using JSON” **does not automatically make the entire pipeline safe** if the application builds JSON via string concatenation, the collector parses it incorrectly, or a dashboard renders content as unescaped HTML.

Example of a valid JSON event:

~~~json
{
  "timestamp": "2026-11-10T02:41:59Z",
  "level": "WARN",
  "event": "login_rejected",
  "userInput": "guest\r\n2026-11-10T02:42:00Z INFO user=admin action=login_success"
}
~~~

In the JSON text above, **\r\n** are escape sequences inside a JSON string value; a compliant JSON serializer will not emit unescaped literal CR/LF into a string. A JSON parser reads back a value containing a logical newline in its data, while the event structure remains a single object; if later exported back to text, it must be escaped for that new sink.

If the collector uses line-based framing, verify that the encoder emits **one JSON object per line** according to the ingestion contract. If stack traces and pretty-printed JSON produce multiple lines, the collector must support appropriate framing or the pipeline risks splitting events incorrectly.

## 8. Input Validation vs. Output Encoding

A secure system usually needs both **contract-based input validation** and **sink-specific output escaping**.

### 8.1. Fixed-Grammar Fields: Validate or Reject

If an application-issued `requestId` must be a string of alphanumeric characters, hyphens, or underscores up to 64 characters long, use an allowlist:

~~~java
private static boolean validRequestId(String value) {
    return value != null
            && value.matches("[A-Za-z0-9_-]{1,64}");
}
~~~

This is an **illustrative snippet** to place inside an application class, not a standalone program. The regex intentionally enforces a sample contract; do not copy it verbatim if your system uses a different ID format, such as a UUID with hyphens (which happens to be accepted by this sample regex).

If the `requestId` header is invalid, you can reject the request per policy or issue a **new server-generated correlationId**. Never let an arbitrary external string become a log field repeated across all events or part of a filename/index name.

### 8.2. Free-Text Fields: Escape on Output

Display names or error responses may legitimately contain Unicode and spaces. Rejecting them is not always appropriate. Instead:

- Do not log unnecessary raw payloads.
- Enforce business-appropriate size limits and allowed character classes.
- Escape accurately for the target sink format when writing.
- If data analysis is needed, use structured fields and a JSON serializer.
- If raw data must be preserved as evidence, store it in a trusted data store with dedicated permissions and policies rather than overusing text logs.

**Validation does not replace encoding**, because business-valid values can still break log structure; **encoding does not replace validation**, because an overly long `requestId` or one with unexpected characters can still cause disruption or increase operational cost even after escaping.

### 8.3. Avoid Out-of-Order Normalization

Systems may URL-decode, unescape JSON, or normalize Unicode before logging. A check that only inspects the pre-decoded string can miss newlines that appear after decoding. Clearly identify **the exact value passed to the logger after all decode/normalization steps** and apply rules at the right boundary.

Do not repeatedly decode attacker-supplied data arbitrarily; that easily breaks contracts and creates opportunities for two-tier parser mismatches. Focus on domain validation and output encoding for the actual sink.

## 9. Safer Use of SLF4J, Logback, and MDC

### 9.1. Use Fixed Event Codes

A good practice is to use **code-defined eventName/errorCode values** rather than using input strings as the event name or log level:

~~~java
logger.warn("event=login_rejected requestId={} reason={}",
        requestId, "invalid_credentials");
~~~

This is integration code assuming **logger** is an SLF4J Logger. Dynamic values still need to be controlled per sink, but having finite domains for `eventName` and `reasonCode` helps prevent syntax confusion.

### 9.2. Scope Context Properly

With MDC:

~~~java
import org.slf4j.MDC;

void withRequestContext(String verifiedRequestId, Runnable work) {
    String previous = MDC.get("requestId");
    try {
        MDC.put("requestId", verifiedRequestId);
        work.run();
    } finally {
        if (previous == null) {
            MDC.remove("requestId");
        } else {
            MDC.put("requestId", previous);
        }
    }
}
~~~

This is an **integration snippet** requiring an SLF4J provider. **verifiedRequestId** must be validated or server-generated before entering the method. Naming a variable “verified” does not make the value trustworthy; code at the boundary must guarantee it.

In thread pools, cleaning up or restoring MDC in a **finally** block prevents context from leaking from one request to the next. With `CompletableFuture`/`ExecutorService`, MDC usually does not propagate automatically to new threads; use a context propagation mechanism supported by your stack/framework.

### 9.3. Configure the Encoder Instead of Manually Patching Messages

Example Logback pattern:

~~~xml
<pattern>%d{ISO8601} %-5level request=%X{requestId} %logger - %msg%n</pattern>
~~~

This pattern **does not automatically protect against forging** if `requestId` or the message contains CR/LF and the encoder prints the content verbatim. Choose an encoder/formatter with explicit escaping rules, or validate IDs and control messages before output.

With a JSON appender, use a real JSON-capable encoder/serializer; ensure each event has clear `level`, `event`, `requestId`, `traceId`, and `errorCode` fields rather than a hand-concatenated `key=value` string.

Do not mix multiple layers of escaping haphazardly: a field already encoded for JSON and then escaped again as text or HTML out of context can corrupt the value or cause double-escaping. Define one concrete contract for each output boundary.

## 10. Exceptions, Stack Traces, and Legitimate Multiline Logs

A Java exception typically has a multiline stack trace. Seeing newlines in logs does not by itself prove an attack. However, you must distinguish **controlled multiline output generated by a formatter** from **newlines originating from untrusted content**.

Example:

~~~text
ERROR event=payment_failed exception=java.io.IOException
    at com.example.PaymentService.pay(PaymentService.java:42)
    at com.example.ApiHandler.handle(ApiHandler.java:18)
~~~

A line-based collector may read lines starting with “at ...” as separate records unless it has a multiline parser or structured exception fields.

Solutions:

1. **Pass the `Throwable` via the logging API** so the provider knows it is an exception, rather than concatenating a stack trace and `userInput` into one long String.
2. **Use structured exception fields** or collector-supported framing where appropriate.
3. **Design strict multiline parser rules** if using traditional text logs.
4. **Do not use ambiguous regexes** like “any line starting with a date is a new event” when an untrusted field can contain a fake timestamp.
5. **Do not strip all stack traces** just to force every event onto one line; preserve investigative evidence through safe formatting.

An exception message can contain data from dependencies, SQL drivers, or requests; it must also be treated as untrusted data when written into text logs or dashboards.

## 11. Unicode Characters and Display Behavior

Beyond CR/LF, several characters can cause readers to misinterpret logs:

| Category | Examples | Issue |
| --- | --- | --- |
| ASCII control | NUL, TAB, CR, LF, ESC | Line breaks, altered display, broken parsers |
| C1 control | U+0085 and other control codes | Some readers interpret them specially |
| Unicode separators | U+2028, U+2029 | May be displayed or processed as line breaks |
| Directionality/format | U+202E, U+200E, isolate marks | Reverse or alter the visual order of strings |
| Delimiters | Quotes, pipe, comma, tab | Alter how parsers split fields |
| Very long strings | Many KB/MB of user values | Exceed event limits, increase ingestion and cost |

Not all invisible Unicode characters are malicious: a zero-width joiner may be necessary in natural text or emoji. For **technical IDs**, a strict grammar is usually appropriate. For **free-form user content**, establish an encoding and display policy that preserves valid information while preventing confusion.

The ESC character can trigger ANSI control sequences on some terminals; if raw data must be kept for investigation, store an escaped representation in normal logs and keep raw evidence in a separate controlled store.

## 12. How Log Forging, Data Exposure, and Denial-of-Service Relate

These issues can occur together, but they are not the same:

- **Log forging:** falsifying the semantics or structure of a record.
- **Sensitive-data exposure:** writing tokens, passwords, or personal data into logs.
- **Log flooding:** generating high log volume to increase cost, bury important events, or cause overload.
- **Log viewer XSS:** rendering data in a UI without HTML/JavaScript context escaping.
- **Unauthorized log modification:** altering or deleting logs after they are written, which requires separate permissions or access vulnerabilities.

An effective defense must combine:

- Validation and output encoding for external data.
- Field length limits, event size limits, event count limits, and appropriate rate limiting.
- Never logging credentials, raw `Authorization` headers, or sensitive payloads.
- Access control for log files, collectors, indices, and dashboards.
- Rotation, retention, audit logging, and configuration-change auditing policies.
- Alerting based on structured fields rather than regexes scanning free-text messages.

**Neutralizing CR/LF does not fix log flooding**, nor does it stop an attacker from sending millions of valid requests. Conversely, rate limiting does not prevent a CRLF payload from slipping through when an event is still logged raw.

## 13. Defense Layers Across Application, Collector, and Log Store

A multi-layered architecture is usually far more reliable than a single regex:

~~~text
[Input boundary]
  validate ID / length limit / classify untrusted data
            |
            v
[Application log event]
  stable event code + structured fields + properly scoped context
            |
            v
[Encoder]
  escape for JSON/text/protocol + appropriate event size
            |
            v
[Collector]
  parse by schema, keep one event with clear ID, alert on parse errors
            |
            v
[Storage / SIEM / dashboard]
  access control, retention, safe rendering, correlation, and alert rules
~~~

If the application outputs single-line JSON, the collector should parse the JSON before routing by **level** or **event**, rather than scanning the message string for a keyword. If parsing fails, route the event to a quarantine/dead-letter queue in the pipeline instead of assuming every loose line is a valid event.

**Do not trust a single layer.** For example, even if users cannot write directly to the log file, they can still control content that the application writes to it. A dashboard with strong HTML escaping reduces UI XSS, but it cannot fix skewed alerts if the collector already split a payload into forged events.

For audits, tamper-resistance, access controls, retention, and chain-of-custody must be designed according to legal/internal requirements. Output encoding is necessary, but it does not by itself guarantee audit trail integrity.

## 14. Testing Against Log Forging

Testing should be performed with controlled input data on **both the logger and the collection pipeline**. Minimum test suite:

| Test Input | Expected Outcome |
| --- | --- |
| Normal name: alice | One event, field has exact value |
| Single LF: alice + U+000A + fake log | Does not create a new event |
| Single CR: alice + U+000D + fake log | Does not break display or record |
| CRLF: alice + U+000D/U+000A + fake log | Event count does not increase |
| Tab, NUL, ESC, or ANSI sequence | Does not control terminal or parser |
| U+2028, U+2029 | Does not create forged records via framing |
| Bidi/format controls | Does not cause misleading display in IDs or UI |
| Quotes, backslash, pipe, equals sign | Field does not break out of expected structure |
| String containing ERROR/INFO and fake timestamp | Does not become an event with attacker-defined level/timestamp |
| Empty/null string | Does not throw an exception or omit required fields |
| Very long value | Bounded or handled per policy; collector is not overloaded |
| Valid Vietnamese/emoji Unicode | Content preserved according to schema |
| Exception message containing CRLF | Stack trace/context is not split incorrectly |
| MDC requestId from header | Validated/regenerated; forging payload does not spread across lines |
| Async/worker threads | Context does not leak and event framing remains intact |

You can write **unit tests** for sanitizers/validators, but **integration tests** must verify how many events the collector actually reads. An escape function might produce one physical line while a downstream parser still misinterprets delimiters; therefore, testing should not stop at counting newlines.

Stronger checks:

- Send a request with a CRLF payload; verify at the backend that it remains **one business log event** containing the encoded value.
- Verify that **level, timestamp, and eventCode** at the backend come from the logger/encoder and are not altered by message content.
- Verify that no **false alerts** are triggered by attacker-injected strings.
- Test both text and JSON logs across stdout/stderr and file sinks if the system uses multiple sinks.
- Test encoding/decoding in the dashboard and report-export tools, not only in the storage index.
- Test parser error handling and event size limits to see how the pipeline handles malformed data.

## 15. Common Mistakes and How to Fix Them

| Mistake | Why It Is Not Safe Enough | Remediation |
| --- | --- | --- |
| Only switching to `logger.warn("{}", value)` | Placeholders do not auto-escape CR/LF across all sinks | Validate fields + use an encoder with proper escaping |
| Only calling `replace("\\n", " ")` | Can miss CR, tab, ESC, U+2028, or delimiters | Handle all relevant control chars and target grammar |
| Manually building JSON with quotes | Quotes/backslashes/control chars can break JSON structure | Use a reliable JSON serializer |
| Writing raw `requestId` to MDC | One payload can infect many events | Validate IDs before placing them in MDC |
| Regex matching `"ERROR"` in message | Forged strings can trigger alerts | Use standardized `level`/`event` fields |
| Relying on one line = one event | Stack traces/pretty JSON/malicious CRLF break framing | Use one-line JSON or explicit framing/multiline policies |
| Stripping all non-ASCII Unicode | Loses valid Vietnamese/multilingual content | Validate technical IDs; encode free text per sink |
| Sanitizing only before file output | Other sinks may exist | Test across the entire output pipeline |
| Logging every request body for debugging | Increases privacy, injection, and flooding risks | Log only minimal fields and error codes |
| Assuming the collector protects itself | Parsers/routers may misbehave on malformed input | Test end-to-end and monitor parse errors |
| Letting users determine level/event | Manipulates alerts or dashboards | Event/level must be determined by application logic |

In illustrative snippets, **\\n** in the table represents a backslash + `n` when written as text. A filter that only searches for the literal string **\n** will fail to detect an **actual LF byte** if the input has already been decoded into a newline character. Always distinguish literal escape sequences from actual control characters at each processing stage.

## 16. Responding to Log Forging in Production

When you notice logs with unusual timestamps/levels or lines that do not match the execution flow:

1. **Verify the original data source:** cross-reference request IDs, trace IDs, ingress logs, message broker metadata, and system events outside the suspect log.
2. **Distinguish real events from split lines:** inspect raw application records if available, collector metadata, framing, and parsing behavior.
3. **Do not use a suspect line as sole authentication evidence:** a line displaying something like “login_success” could originate from an attacker-supplied value.
4. **Isolate the entry point:** query/header/body, exception message, stored data, or MDC.
5. **Apply mitigations:** validate fixed-grammar IDs, use an appropriate encoder, and enforce input/log-volume limits; deploy with tests.
6. **Check affected dashboards/alerts:** determine whether false alerts fired or real incidents were missed because parsers accepted forged events.
7. **Preserve investigative evidence per security policy:** restrict access to raw logs and avoid putting sensitive payloads into public reports.
8. **Add regression tests:** replay CR/LF and delimiter payloads in CI tests to reduce recurrence risk.

Not every unusual log line is an attack. It may be a multiline stack trace, a framework formatter quirk, or a collector bug. Conclude only after verifying data boundaries and how logs are emitted and parsed.

## 17. Secure Deployment Checklist

Before taking a Java service to production, verify:

| Item | Criteria |
| --- | --- |
| Input trust | Know which fields from HTTP, brokers, databases, or dependencies are untrusted |
| Identity fields | `requestId`, `traceId`, and `jobId` are validated or server-generated per contract |
| Event metadata | `level`, event code, and timestamp are never taken from arbitrary messages |
| Text formatting | CR/LF, control chars, quotes/delimiters are neutralized per grammar |
| Structured encoding | A real JSON encoder/serializer is used instead of string concatenation |
| MDC | No raw payloads; scoped properly and cleared/restored when tasks finish |
| Exception | `Throwable` is handled structurally; multiline output has valid framing |
| Collector | Parses and routes by fields; detects malformed events |
| Alert rules | Do not rely solely on regexes over attacker-controlled messages |
| Security | No secrets logged; access controls and retention are enforced |
| Capacity | Limits are set for field/event sizes and log rates |
| Tests | CR, LF, CRLF, Unicode, ANSI, delimiters, very long values, and end-to-end flow are verified |

**Remember:** log forging occurs when **untrusted data is treated as log syntax**. In Java, validate fields with fixed contracts, use encoders/serializers suited to the output, do not treat SLF4J placeholders as sanitizers, keep MDC clean, and test the full path **application → collector → dashboard/alert**. The goal is to preserve logs' investigative value without letting externally controlled content manufacture fake “events”.