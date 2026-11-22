# Log Format Stability — Formatters, Layouts, and Log Data Contracts in Java

## 1. Concept

**Log format stability** means keeping the representation of a log event **consistent with a clear contract**: field names, data types, units, timestamp format, levels, error representation, character escaping, and versioning conventions. The goal is to help readers, collectors, search engines, dashboards, and alerts interpret logs accurately across multiple application versions.

A log message can change its values on every request and still have a stable format. Illustrative example:

~~~text
2026-11-09T10:15:00.125Z INFO service=order-api event=order.created requestId=req-17 outcome=success durationMs=18
2026-11-09T10:15:01.750Z WARN service=order-api event=payment.retry requestId=req-18 reason=timeout attempt=2
~~~

The lines above are **illustrative data**, not the default output of a Java library. What remains stable are the fields **service, event, requestId, outcome, durationMs**, while the values and timestamps are dynamic data.

An unstable log format might change arbitrarily:

~~~text
Payment error!
Payment failed due to timeout
Could not pay. Will retry.
~~~

All three messages may refer to the same kind of issue, yet they are very hard to search or aggregate with a consistent filter. Using a stable **event code** and **error code** reduces dependence on free-form wording:

~~~text
event=payment.failed errorCode=PAYMENT_TIMEOUT outcome=failure
~~~

**Stability does not mean every byte is always identical.** Request data, timestamps, threads, IDs, and actual errors can always change. The contract must be stable in **schema and semantics**, not in every value.

## 2. Why Is a Stable Format an Operational Requirement?

Logs are not only read in an IDE. In production, logs typically pass through multiple components:

~~~text
Java application
      |
      v
Logger + LogRecord / LoggingEvent
      |
      v
Formatter / Layout / Encoder
      |
      v
Console / File / Stream
      |
      v
Collector / Parser / Indexer
      |
      v
Search / Dashboard / Alert / Investigation
~~~

A change at the producer can affect downstream consumers:

1. **Search:** a query for `event=payment.failed` no longer matches when the producer unilaterally renames it to `event=payment.error`.
2. **Dashboards:** the `durationMs` field is renamed to `latency` or changed from a number to a string; charts lose new data.
3. **Alerts:** a filter only understands `ERROR`, but a group of services changes the `level` field or emits a different string.
4. **Correlation:** services do not standardize `requestId`/`traceId`, making it impossible to trace the full request journey.
5. **Historical comparison:** data before and after a deployment has different schemas, requiring multiple parsers.
6. **Security:** arbitrarily printing objects or adding new fields can cause personal/secret data to be collected unexpectedly.
7. **Cost:** abnormally long logs, multiline stack traces, and large payloads increase I/O, storage, and query time.

Therefore, a log format should be treated as a **tested data contract**, especially when dashboards, alerts, or external applications depend on it.

## 3. How Do Message, Log Record, Formatter, Layout, and Encoder Differ?

| Component | Role | Example |
| --- | --- | --- |
| **Log message** | Describes an event for humans | Order accepted |
| **Log record/event** | Event data before output | Level, logger, message, timestamp, Throwable, MDC |
| **Schema/format** | Conventions for fields, types, units, and event codes | schemaVersion, event, durationMs |
| **Formatter** | Converts a LogRecord into a string | JUL's java.util.logging.Formatter |
| **Layout** | Formats an event as text | Logback/Log4j 2 PatternLayout |
| **Encoder** | Turns layout/event data into bytes sent to a destination | PatternLayoutEncoder or JSON encoder |
| **Handler/Appender** | Writes to console, file, or another destination | JUL StreamHandler, Logback ConsoleAppender |
| **Collector/parser** | Reads, splits, and interprets logs | Pipeline ingesting JSON Lines or text |

In **JUL** (java.util.logging), the typical pipeline is Logger → Handler → Formatter. In **SLF4J + Logback**, the typical pipeline is Logger → Appender → Encoder/Layout. They are different APIs; do not copy configurations verbatim between the two systems.

**The formatter determines the presentation form; the schema determines the meaning of the data.** A pattern that looks neat but uses field names that vary by module is still an unstable system.

## 4. Elements to Fix in a Log Schema

### 4.1. Field Names and Meanings

A reference field set:

| Name | Example | Recommended Contract |
| --- | --- | --- |
| schemaVersion | 1 | Schema version, as an integer |
| timestamp | 2026-11-09T10:15:00.125Z | Event timestamp, with timezone |
| level | INFO | Log level following a standardized convention |
| service | order-api | Name of the service emitting the event |
| logger | demo.order.OrderService | Logger name |
| event | order.created | Stable event type code |
| requestId | req-17 | Correlation ID if available |
| traceId | 0123abcd... | Trace ID when supported by the tracing system |
| outcome | success | Documented set of values |
| errorCode | PAYMENT_TIMEOUT | Stable error code |
| durationMs | 18 | Duration number, in milliseconds |
| message | Order accepted | Human-readable description |
| exception | structured object/string | Error type, cause, stack trace details |

This is **not a mandatory schema**. An organization can use different naming conventions such as `service.name` or `trace_id`; what matters is **not mixing multiple conventions without a mapping**.

Some fields may be optional depending on the event type. For example, a startup event does not need `requestId`, whereas a request event usually does. Clearly specify which fields are **required**, which are **optional**, and how missing data is interpreted.

### 4.2. Data Types

- **durationMs** should be a number, not sometimes `18` and sometimes `"18ms"`.
- **attempt** is an integer when counting retry attempts.
- **outcome** is a string belonging to a documented set of values, such as `success`/`failure`.
- **requestId** is a string and may have leading zeros; do not coerce it to a number.
- **statusCode**, if representing an HTTP status, can be a number; do not emit `503` in one place and `"HTTP 503"` in another.

If a value does not exist, clearly distinguish between a **missing field**, **null**, and an **empty string**. Consumers may interpret them differently. Do not change the meaning of the same field across versions.

### 4.3. Units, Numbers, and Locale

Include the unit in the field name: **durationMs**, **sizeBytes**, **timeoutMs**. Changing a field's unit while keeping the same name is a dangerous semantic change.

For decimal numbers, avoid locale-dependent formatting that turns **1.5** into **1,5** in a field where the parser expects a dot. When machines need to process numeric values, use JSON numbers and a clear schema rather than embedding numbers in free-form messages.

### 4.4. Timestamp and Timezone

For logs from multiple machines, standardize on a time profile with an explicit timezone, such as UTC:

~~~text
2026-11-09T10:15:00.125Z
~~~

This is a form belonging to the **ISO-8601/RFC 3339** family. Saying only "ISO-8601" is not enough: you must specify the timezone, precision, and whether the timestamp field represents **when the event was emitted** or **when the collector received it**.

Do not assume a date like **11/09/2026** means September 11 or November 9; that format is locale-dependent. Do not treat the order in which logs are received across hosts as a strict global order, because clock skew, buffering, and network delay can occur.

### 4.5. Stable Event Codes

Examples:

~~~text
event=order.created
event=payment.retry
event=payment.failed
event=job.completed
~~~

Do not embed an individual `orderId`/`requestId` into the **event name**, such as `payment.failed.req-42`. Reserve the event name for the **event type** and place IDs in separate fields.

Changing from **payment.retry** to **payment.failed** is not just a wording tweak: they describe two different event types. If an event's meaning genuinely changes, consider introducing a new code or bumping the schema version.

### 4.6. Consistent Levels

SLF4J/Logback typically uses **TRACE, DEBUG, INFO, WARN, ERROR**; JUL uses **FINEST, FINER, FINE, CONFIG, INFO, WARNING, SEVERE**. If multiple backends send logs into one system, you may need a **level normalization rule** at the producer or collector.

Do not assume JUL's **WARNING** and Logback's **WARN** are completely identical in all semantics. They are close in intent, but the mapping must be specified and tested.


## 5. Choosing a Representation: Text, key=value, and JSON Lines

### 5.1. Pattern-Based Text

~~~text
2026-11-09T10:15:00.125Z INFO demo.OrderService - Order accepted
~~~

Easy to read and suitable for console output, exercises, or small applications. However, parsers typically rely on delimiters, positions, and string patterns; logger names or messages containing unexpected characters can cause the parser to misread fields.

### 5.2. key=value

~~~text
level=INFO service=order-api event=order.created requestId=req-17 durationMs=18 message="Order accepted"
~~~

Searchable and parseable if quoting/escaping rules are consistent. However, if a message contains spaces, equals signs, or newlines, ad-hoc string concatenation makes the record hard to parse.

**A key=value format can be stable**, but it requires specifying pair boundaries, how quotes/backslashes are encoded, data types, and how missing values are represented.

### 5.3. JSON Lines

Each event is written as **one JSON object on one physical line**:

~~~json
{"schemaVersion":1,"level":"INFO","service":"order-api","event":"order.created","requestId":"req-17","durationMs":18,"message":"Order accepted"}
~~~

Benefits of JSON:

- Fields are identified by name rather than splitting a message string.
- Values can be numbers, strings, booleans, null, or objects.
- A proper encoder escapes special characters so logs can be read line by line.
- Easy to validate against a schema and parse in centralized collection systems.

However, **JSON does not automatically guarantee that data is indexed or queryable by field**. The collector must parse, store, and configure mappings properly. **Key order in a JSON object is not part of the semantic contract**; consumers should query by key name.

### 5.4. Newlines, Quotes, and Unicode

Suppose a real message contains two lines and quotes:

~~~text
Timeout: retry "later"
Check gateway
~~~

If a raw newline is inserted into a record intended to be a single line, the collector may misinterpret it as **two events**. JSON Lines must escape the string so it remains a single physical line:

~~~json
{"event":"payment.failed","message":"Timeout: retry \"later\"\nCheck gateway"}
~~~

In this JSON data, **\n** is two escape characters representing a newline inside the `message` value, not a line break separating records.

In addition to quotes, the encoder must properly handle **backslashes, control characters, Unicode, and escaping**. For exceptions/stack traces, you can:

1. Use **multiline text**, while configuring the collector to merge stack trace lines into a single event.
2. Use **single-line structured JSON**, storing the exception in a field with escaped newlines inside.

Choose one clear approach; do not mix single-line JSON and multiline text when the collector uses a single parser.

**Do not concatenate strings manually to build JSON in production.** Use a tested encoder/serializer, especially when data comes from untrusted users or contains nulls or unusual Unicode characters.

## 6. Runnable Java 17+ Example: JUL Formatter Producing Stable JSON Lines

This example uses the JDK's **java.util.logging**, with no external dependencies. It demonstrates how a **Formatter** converts a **LogRecord** into a record with fixed fields.

The demo schema has the fields: **schemaVersion, level, logger, event, requestId, outcome, durationMs, message**. `durationMs` is a number; `event` and `requestId` are separated from `message`. To make the output completely deterministic, the demo **omits the timestamp**; real applications should include a standard timestamp.

Create the file **StableLogFormatDemo.java**:

~~~java
import java.util.Locale;
import java.util.logging.Formatter;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;
import java.util.logging.StreamHandler;

public class StableLogFormatDemo {
    private static final Logger LOGGER =
            Logger.getLogger("demo.order");

    public static void main(String[] args) {
        LOGGER.setUseParentHandlers(false);
        LOGGER.setLevel(Level.INFO);

        Handler stdout = new StreamHandler(
                System.out, new StableJsonFormatter());
        stdout.setLevel(Level.INFO);
        LOGGER.addHandler(stdout);

        logEvent(Level.INFO, "order.created", "req-001",
                "success", 18L, "Order accepted");

        logEvent(Level.WARNING, "payment.failed", "req-002",
                "failure", 2500L,
                "Timeout: retry \"later\"\nCheck gateway");

        stdout.flush();
    }

    private static void logEvent(
            Level level, String event, String requestId,
            String outcome, long durationMs, String message) {

        LogRecord record = new LogRecord(level, message);
        record.setLoggerName(LOGGER.getName());
        record.setParameters(new Object[]{
                event, requestId, outcome, durationMs
        });
        LOGGER.log(record);
    }

    private static final class StableJsonFormatter extends Formatter {
        @Override
        public String format(LogRecord record) {
            Object[] fields = record.getParameters();

            return "{"
                    + "\"schemaVersion\":1"
                    + ",\"level\":" + quote(record.getLevel().getName())
                    + ",\"logger\":" + quote(record.getLoggerName())
                    + ",\"event\":" + quote((String) fields[0])
                    + ",\"requestId\":" + quote((String) fields[1])
                    + ",\"outcome\":" + quote((String) fields[2])
                    + ",\"durationMs\":" + fields[3]
                    + ",\"message\":" + quote(record.getMessage())
                    + "}" + System.lineSeparator();
        }

        private static String quote(String value) {
            StringBuilder result =
                    new StringBuilder(value.length() + 2).append('"');

            for (int i = 0; i < value.length(); i++) {
                char c = value.charAt(i);
                switch (c) {
                    case '"' -> result.append("\\\"");
                    case '\\' -> result.append("\\\\");
                    case '\b' -> result.append("\\b");
                    case '\f' -> result.append("\\f");
                    case '\n' -> result.append("\\n");
                    case '\r' -> result.append("\\r");
                    case '\t' -> result.append("\\t");
                    default -> {
                        if (c < 0x20) {
                            result.append(String.format(
                                    Locale.ROOT, "\\u%04x", (int) c));
                        } else {
                            result.append(c);
                        }
                    }
                }
            }
            return result.append('"').toString();
        }
    }
}
~~~

Compile and run with **JDK 17 or later**:

~~~bash
javac -encoding UTF-8 StableLogFormatDemo.java
java StableLogFormatDemo
~~~

**The program's stdout consists of exactly these two JSON lines** (each line terminated by the OS newline):

~~~json
{"schemaVersion":1,"level":"INFO","logger":"demo.order","event":"order.created","requestId":"req-001","outcome":"success","durationMs":18,"message":"Order accepted"}
{"schemaVersion":1,"level":"WARNING","logger":"demo.order","event":"payment.failed","requestId":"req-002","outcome":"failure","durationMs":2500,"message":"Timeout: retry \"later\"\nCheck gateway"}
~~~

The second message contains a newline **inside the Java String value**, but the formatter escapes it as **\n**, so the JSON remains **one physical line** per event.

### Why Does the Output Look Like This?

1. **LOGGER.setLevel(Level.INFO)** allows `INFO` and `WARNING`; the handler also accepts both levels.
2. **logEvent(...)** creates a `LogRecord`, sets the logger name, and passes business values using a **demo-only** parameter contract.
3. **StableJsonFormatter** reads the fields and builds an object with fixed field names.
4. **quote(...)** escapes quotes, backslashes, newlines, and common control characters.
5. **setUseParentHandlers(false)** prevents parent logger handlers from printing additional records in a different format.
6. **StreamHandler(System.out, ...)** writes to stdout; **JUL's default ConsoleHandler writes to stderr**, so do not confuse the two handlers.
7. **stdout.flush()** flushes buffered data to stdout before `main` exits.

### Scope of the Example

This is an **illustrative formatter**, not a production JSON encoder:

- Reading fields by fixed index from **LogRecord.parameters** only works for records created by the `logEvent` method itself. Do not apply it arbitrarily to `LogRecord` instances created by other libraries.
- The sample values are controlled; this is not a comprehensive test suite for nulls, malformed Unicode surrogates, invalid types, or untrusted input.
- The demo formatter does not handle **Throwable**, timestamps, or advanced context. Production requires additional rules, especially for stack traces.
- Calling `String.format` for control characters is easy to follow for demonstration; high-throughput systems should use a tested JSON encoder/serializer.
- The program uses JUL to demonstrate `Formatter`; **SLF4J/Logback** has different APIs and level names, so you cannot copy this `Formatter` class directly into Logback.

### Validating JSON Lines

On a machine with Python 3, you can run:

~~~bash
java StableLogFormatDemo > events.jsonl
python3 -c 'import json; [json.loads(line) for line in open("events.jsonl", encoding="utf-8")]'
~~~

The Python command prints nothing if every line parses as valid JSON; otherwise, it raises an error. This is only a **JSONL file validation tool**, not a dependency of the Java application.

**Do not assume `python3 -m json.tool events.jsonl` handles multiple separate JSON objects in one file across all Python versions**; for JSON Lines, parse line by line or use a JSONL-aware tool. Beyond JSON syntax, you should also test the `durationMs` type, `event`/`schemaVersion`, and missing-data rules.


## 7. Stabilizing Layouts with Logback PatternLayoutEncoder

In applications using **SLF4J + Logback Classic**, text log formats are typically configured via **logback.xml**:

~~~xml
<configuration>
    <appender name="CONSOLE"
              class="ch.qos.logback.core.ConsoleAppender">
        <target>System.out</target>
        <encoder>
            <charset>UTF-8</charset>
            <pattern>level=%level logger=%logger thread=%thread message=%msg%n</pattern>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
    </root>
</configuration>
~~~

This is an illustrative Logback configuration, **not a configuration for the JUL program in Section 6**.

Common conversion words:

| Pattern | Meaning |
| --- | --- |
| %level | Event level, e.g. INFO/WARN/ERROR |
| %logger | Name of the logger emitting the event |
| %thread | Thread name |
| %msg | Message after parameter formatting |
| %n | Newline character |
| %d{...} | Timestamp formatted by pattern |
| %X{requestId} | The `requestId` field from MDC, if present |
| %ex / %throwable | Exception/stack trace representation depending on the encoder |

Simply printing **message=%msg** does not give you structured logging. If the message contains spaces, equals signs, newlines, or untrusted strings, a naive key=value parser can break. For typed schemas, use a real **JSON encoder** aligned with the collector rather than building JSON-like strings with `PatternLayout`.

### SLF4J 2 and Key-Value Logging

Illustrative snippet with SLF4J 2.x:

~~~java
// Placed inside a class where LOG is declared and an orderId variable exists.
LOG.atInfo()
        .addKeyValue("event", "order.created")
        .addKeyValue("orderId", orderId)
        .addKeyValue("outcome", "success")
        .log("Order accepted");
~~~

The `addKeyValue` method represents structured key-value pairs at the API level, but **it does not automatically guarantee that the backend/encoder outputs them as JSON or that the collector indexes them**. A matching encoder configuration is required. The snippet above is **not a standalone Java program**, because it lacks the declarations for `LOG` and `orderId`.

When changing a layout, preserve the names and semantics of fields that have consumers. Even changing a human-readable display format may not be harmless if a backend previously parsed it by pattern.

## 8. Stabilizing Formatters in JUL

JUL uses a **Formatter** on the Handler side. A built-in option is **java.util.logging.SimpleFormatter**, which supports a formatting property:

~~~properties
java.util.logging.SimpleFormatter.format = %1$tFT%1$tT %4$s %3$s - %5$s%6$s%n
~~~

In `SimpleFormatter`, the format arguments correspond to information such as timestamp, source, logger name, level, message, and the `Throwable` part. This uses **java.util.Formatter syntax in JUL**, which differs from Logback's `%level`/`%logger` syntax.

Keep in mind:

- The property above **does not guarantee UTC**, because the timezone may depend on the environment.
- For reliable Unicode/Vietnamese characters, check the encoding of `ConsoleHandler`/`FileHandler` and the receiving target; configure UTF-8 appropriately.
- If you only print the message without keeping the `Throwable` part, exception/stack trace details can be lost in the output.
- Loggers/handlers have levels and filters; **a formatter cannot recover events that were already filtered out earlier**.
- When writing a custom `Formatter`, explicitly specify handling for nulls, exceptions, newlines, timezone, charset, and schema version.

Both JUL and Logback have formatting mechanisms, but that does not mean a `logging.properties` file will be understood by Logback or that `logback.xml` will configure plain JUL.

## 9. Schema Versioning and Compatibility

A stable format **can still evolve**. What matters is making changes intentionally without breaking running consumers.

### Changes That Are Usually Easier to Keep Compatible

- Adding an **optional field** with a clear name and type that old consumers can ignore.
- Adding a **new event code** with its own distinct meaning.
- Adding metadata without altering the meaning of existing fields.
- Updating human-readable message wording while keeping event/error codes stable and ensuring consumers do not rely on literal messages.

Even adding an optional field requires testing: overly strict parsers may reject unknown fields.

### Contract-Breaking Changes

| Change | Risk |
| --- | --- |
| `durationMs` from `18` to `"18ms"` | Changed from number to string; numeric comparison queries break |
| `outcome=success` to `outcome=ok` | Old enum values no longer match |
| Renaming `event=payment.failed` | Alerts watching the old event stop matching |
| `timestamp` from UTC to local time without offset | Consumers can misinterpret timestamps |
| JSON Lines changed to multiline text | Single-line/single-object parsers fail |
| Dropping `requestId` from request events | Logs can no longer be correlated |
| Moving `errorCode` from its own field into `message` | Exact field-based queries no longer work |

### Schema Upgrade Process

1. **Document the current schema**: field names, types, units, enums, required/optional status, and examples.
2. **Classify the change**: is it compatible with existing consumers?
3. **Attach `schemaVersion`** or an organization-wide versioning mechanism.
4. **Plan the migration**: for example, have the producer emit both old and new fields during a transition period, or have the collector accept two versions.
5. **Verify consumers**: dashboards, alerts, parsers, queries, operational runbooks, and auditing tools.
6. **Deploy with monitoring**: watch for parse errors, dropped logs, and event counts per version.
7. **Retire the old format in a controlled manner** after consumers are ready.
8. **Update tests and documentation** so incompatible changes are not reintroduced.

**`schemaVersion` does not guarantee backward compatibility by itself.** It only indicates which contract is in use; consumers still must know how to read or transform each version.

## 10. Data You Should Not Turn into Contract Keys

Some details are useful for debugging but frequently change across builds or runtimes:

- **Source file/line number**: refactoring shifts line numbers.
- **Method/class names**: change during refactoring or moving modules.
- **Thread name**: thread pools or frameworks may change naming conventions.
- **Log line ordering across multiple hosts**: collectors and networks can transmit/receive asynchronously.
- **Key order in JSON**: consumers should look up fields by name.
- **Natural-language descriptions**: translations or wording can change; use event/error codes for stable queries.
- **Locale-dependent values**: date/number separators can vary by machine.
- **Verbatim stack traces**: change when code is refactored and may contain sensitive information.

Design **event codes**, **errorCode**, **service/component**, **traceId/requestId**, **schemaVersion**, and well-defined fields as the basis for querying.

## 11. Correlation IDs and Multithreaded Context

To link events belonging to the same request across multiple services, use a consistent correlation field:

~~~json
{"schemaVersion":1,"level":"INFO","service":"checkout","event":"checkout.started","requestId":"req-42"}
{"schemaVersion":1,"level":"INFO","service":"pricing","event":"price.calculated","requestId":"req-42"}
{"schemaVersion":1,"level":"ERROR","service":"payment","event":"payment.failed","requestId":"req-42","errorCode":"PAYMENT_TIMEOUT"}
~~~

This is illustrative data. When using SLF4J/Logback, MDC can help attach `requestId` to events:

~~~java
// Illustrative snippet inside a class that already has LOG:
try (org.slf4j.MDC.MDCCloseable ignored =
        org.slf4j.MDC.putCloseable("requestId", "req-42")) {
    LOG.info("event=checkout.started");
}
~~~

**MDC does not automatically propagate across every `CompletableFuture`, thread pool, or reactive task.** You must propagate and clear context properly; otherwise, request IDs can be lost or mixed between requests. The encoder and collector must also actually output and parse that field.

Do not use unique `requestId`/`traceId` values as **unbounded metric labels**, as this causes high cardinality. They belong in logs and traces; metrics should use bounded label sets.


## 12. Security and Sensitive Data

A stable format makes data easier to collect and search, which can also cause sensitive information to be indexed and retained longer. Mandatory principles:

- Never log raw **passwords, access tokens, API keys, private keys, session cookies, or payment card data**.
- Do not log entire HTTP request/response bodies or `object.toString()` by default.
- Choose **safe event codes, `errorCode`s, and correlation IDs** instead of large payloads or direct user data.
- Use an encoder with **escaping** to prevent log injection: input data may contain newlines or control characters that forge fake log lines.
- `Throwable`/stack traces can expose paths, parameters, and internal details; apply redaction/masking policies and proper access controls.
- Configure retention and access permissions for console, files, and centralized storage.
- Monitor record size, events per second, and the cost of new fields when changing schemas.

**Switching from text to JSON does not automatically make logs secure.** Security depends on the data chosen to be logged, the encoder, access controls, and retention policies.

## 13. Testing Formats as Data Contracts

Do not only test that a logger emits a string. Test in layers:

1. **Parseability:** each JSON Lines event produces one valid JSON object.
2. **Escaping:** quotes, backslashes, newlines, control characters, and Unicode data are handled according to the schema.
3. **Required fields:** `schemaVersion`, `timestamp`, `level`, `service`/`event` are present as required by the contract.
4. **Data types:** `durationMs` is a number, `attempt` is an integer, `outcome` belongs to a valid enum.
5. **Timestamp:** timezone/precision follow the rules and are locale-independent.
6. **Exceptions:** cause/stack trace can be stored properly without breaking event boundaries.
7. **Correlation:** `requestId` is emitted accurately, propagated across async boundaries, and cleared after the request.
8. **Level/filter:** `DEBUG` is dropped when level is `INFO`, while `ERROR` is still written to the appropriate appender.
9. **Collector:** queries by typed fields work, no records are dropped, and there is a strategy for reading multiple schema versions during migration.
10. **Security:** no tokens/secrets or forbidden raw payloads are leaked.
11. **Delivery/durability:** recognize that logs can be delayed or dropped; do not use them as a durable transaction store.
12. **Cost limits:** log volume, file rotation, and retention are appropriate.

### Golden Tests and Dynamic Data

**Golden-file tests** can compare sample records to detect formatter changes. However, timestamps, thread IDs, and random request IDs will make snapshots flaky if uncontrolled. You can inject a **fixed `Clock`**, normalize dynamic fields, or parse and compare objects against a schema rather than comparing raw JSON text byte-for-byte.

The Java example in Section 6 intentionally omits timestamps so the output is deterministic. **Production should not omit timestamps just to make testing easier**; schema tests must accept dynamic time fields within contract bounds.

With JSON, **field order carries no semantics**, so comparing parsed objects is usually more resilient than comparing byte strings; for text patterns using a custom parser, test the boundaries between fields.

## 14. Troubleshooting Checklist When Logs Suddenly Become Hard to Search or Fail to Parse

1. Identify the **producer/service and deployment** where logs started looking different.
2. Compare a good event and a broken event: field names, types, missing/null values, or whether the message contains newlines or quotes.
3. Check `schemaVersion` and the change history of the encoder/formatter.
4. Verify which backend is active: JUL `Formatter`, Logback `PatternLayoutEncoder`, or a JSON encoder?
5. Check charset, timezone, and precision.
6. Check additivity/handlers/appenders: is the same event passing through two different formatter pipelines?
7. Check what the collector parser expects: JSON Lines or a specific text pattern?
8. Check for truncation, buffering, sampling, dropped logs, or expired retention.
9. Cross-check dashboards/alerts/queries to see which consumers are affected.
10. Fix according to the schema contract and migration plan; avoid patching queries temporarily while ignoring the producer.

**Not finding a log line is not enough to prove the code did not run**, because the event may have been blocked by a level/filter, an I/O error, or not stored by the collector.

## 15. Common Mistakes

| Mistake | Consequence | How to Avoid |
| --- | --- | --- |
| Using natural-language messages as event keys | Wording changes break alerts | Use stable event/error codes |
| `durationMs` is sometimes a number, sometimes `"18ms"` | Numeric queries fail | Fix units and data types |
| Timestamp without explicit timezone | Cannot determine exact occurrence time | Use UTC or explicit offset |
| Renaming `userId` to `user_id` without migration | Old consumers miss the field | Schema versioning and rollout |
| Printing raw newlines into JSON Lines | One event splits into multiple physical lines | Use escaping / JSON encoder |
| Using only a text pattern while assuming JSON fields exist | Collector fails to parse fields accurately | Use a structured encoder and matching parser |
| Changing formatter and dropping `Throwable` | Stack traces disappear | Test exception representation |
| Comparing field positions in JSON | Breaks when key order changes | Query by field name |
| Using `ThreadLocal`/MDC across async without propagation | Missing or wrong `requestId` | Propagate and clear context |
| Two appenders outputting two different formats | Dashboards struggle to parse, duplicate logs | Manage appender pipelines/additivity |
| Snapshot tests containing current timestamps | Flaky tests | Fix `Clock` / normalize |
| Logging raw tokens or request bodies | Sensitive data gets indexed | Data minimization and masking |
| Enabling `DEBUG` broadly, producing huge logs | Higher I/O and storage costs | Enable selectively, measure performance |

## 16. Exercises and Self-Check Questions

**Q1.** Does format stability require two runs to produce the exact same timestamp and `requestId`?

**Answer:** No. Dynamic data can change; the schema, field names, types, units, encoding, and semantics must remain consistent.

**Q2.** Why is `durationMs=18` easier to process than `duration="18ms"`?

**Answer:** The field name states the unit and the numeric value allows numeric comparisons when the collector parses the type properly; `"18ms"` requires stripping the unit and is prone to format drift.

**Q3.** Can a message containing a newline exist in JSON Lines?

**Answer:** Yes, as long as the newline inside the value is escaped as `\n` so the record remains a single physical line.

**Q4.** Is adding an optional field to JSON always compatible?

**Answer:** Not unconditionally. Flexible consumers can ignore it, but overly strict legacy parsers may reject unknown fields; testing is still required.

**Q5.** Should you build alerts by matching the exact phrase “Payment failed”?

**Answer:** Usually no. Human-facing messages can change; use stable event codes and `errorCode`s instead.

**Q6.** How does a JUL `Formatter` differ from Logback's `PatternLayoutEncoder`?

**Answer:** A JUL `Formatter` converts a `LogRecord` into a string; Logback uses a layout/encoder to format events. The two APIs do not have directly compatible configurations.

**Q7.** What problems can occur if you change `timestamp` from UTC to local time without an offset while keeping the field name `timestamp`?

**Answer:** Consumers may misinterpret the time and compare services inaccurately; it is a semantic change that can break the contract.

**Q8.** Does simply adding `schemaVersion` make every system automatically understand the new format?

**Answer:** No. Consumers must support or transform the version; a migration strategy is still needed.

**Q9.** If two JSON objects have the same keys and values but in a different key order, do they differ semantically?

**Answer:** Normally no. JSON objects do not define key order as semantic; query by field name.

**Q10.** Why should you not use the thread name as an event code?

**Answer:** Thread names depend on runtime details and can change, whereas an event code must represent a stable event type.

**Q11.** Why does the demo example omit the timestamp, while production should not?

**Answer:** The demo aims for exact reproducible stdout; operational logs need timestamps for investigation. Use a fixed `Clock` or schema tests instead of omitting real timestamps.

**Q12.** Should you log the entire HTTP request to “ensure enough information for any future query”?

**Answer:** No. Log only minimal required fields while adhering to security and retention policies; raw payloads can contain tokens or personal data.

## 17. Summary

**Log format stability is about maintaining a data contract between log-producing code and every log-consuming system.** Key takeaways:

- **Stable event codes, field names, and semantics** instead of relying on natural-language wording.
- **Clear data types, units, timezones, and null semantics.**
- **Appropriate Formatter/Layout/Encoder**, proper character escaping, and `Throwable` handling.
- **Versioning, migration, and end-to-end testing from producer to collector.**
- **Security, retention, and performance** when logs are collected, indexed, and queried.

Having a logger emit an event is only the starting point; **a stable format ensures the event retains its diagnostic value** even after Java code, logging backends, or logging infrastructure change.
