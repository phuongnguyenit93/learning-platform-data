# Validating JSON in Java Logging

**JSON validation** is the process of verifying that a log record is properly represented in JSON format, has clear event boundaries, preserves accurate data types, and satisfies the information contract required by the observability system. In **JSON logging**, validity does not stop at having matching braces and quotation marks.

Example of a log event:

~~~json
{"timestamp":"2026-11-09T10:15:30Z","level":"WARN","event":"payment_retry","durationMs":42,"message":"Gateway timeout"}
~~~

This line can be validated at four levels: **JSON syntax**, **one event per JSONL line**, **the schema and semantics of each field**, and finally **the ability to be ingested and queried correctly by the collector**. A record may pass the first level and still fail at subsequent levels.

## 1. Four Levels of Validity to Distinguish

| Validation level | Question | Failure cases |
| --- | --- | --- |
| JSON syntax | Can the data be parsed by a standard-compliant JSON parser? | Missing braces, single quotes, trailing commas |
| JSON Lines / NDJSON | Does each physical line contain exactly one JSON event? | Pretty-printing an object across multiple lines |
| Schema / semantic | Are the root, required fields, types, timestamp, and values correct? | durationMs is a string instead of a number |
| End-to-end logging | Do the backend, collector, and storage preserve the event/fields accurately? | Valid JSON, but the collector fails to parse or mis-maps fields |

**Syntactically valid JSON does not equal a valid log event.** JSON allows the root to be an object, array, string, number, boolean, or null. However, a JSON logging contract typically requires a **root object** containing specific fields and may reject values that a plain JSON parser would still accept.

For example:

~~~json
[{"event":"ready"}]
~~~

This is syntactically valid JSON, but it is **invalid** if the application specifies that each line must be a single object rather than an array.

Similarly:

~~~json
{"durationMs":"42"}
~~~

is syntactically valid JSON, but if the schema requires `durationMs` to be an **integer**, the record is considered **invalid according to the schema**.

## 2. Essential JSON Syntax Rules

JSON has the following types: **object**, **array**, **string**, **number**, **boolean**, and **null**. An object is a collection of name–value pairs; an array is an ordered list of values.

~~~json
{
  "event": "order_completed",
  "durationMs": 37,
  "success": true,
  "tags": ["checkout", "payment"],
  "error": null,
  "details": {"attempt": 2}
}
~~~

A few important rules:

1. **Field names** in an object must be strings enclosed in **double quotes**.
2. A colon separates a field name from its value, and commas separate elements.
3. Standard JSON does not support `//` or `/* ... */` comments.
4. Trailing commas after the last element of an object or array are not allowed.
5. Booleans are lowercase `true` and `false`; the empty value is `null`.
6. Do not use `undefined` as a literal.
7. Numbers use a dot for the decimal point; `NaN` and `Infinity` are not valid standard JSON numbers.
8. Strings must properly escape double quotes, backslashes, and control characters.

Illustrative errors:

| Invalid input | Reason |
| --- | --- |
| {event:"ready"} | Missing double quotes around the key name |
| {'event':'ready'} | Using JavaScript-style single quotes instead of JSON |
| {"event":"ready",} | Trailing comma |
| {"event":"ready" "level":"INFO"} | Missing comma |
| {"attempt":undefined} | undefined is not a JSON value |
| {"durationMs":NaN} | NaN is not a JSON number |
| {"success":TRUE} | TRUE must be true |
| {"event":"ready"} other | Extra significant data after the JSON document |

Some parsers support **non-standard extensions**, such as comments or trailing commas. If you test with a parser that has those options enabled, it may accept data that the production collector rejects. For logs exchanged across multiple systems, use standard JSON syntax and strict parser configuration.

## 3. What Is JSON Lines (JSONL/NDJSON)?

JSON Lines, typically using the `.jsonl` extension, stores **one JSON value per physical line**. In JSON logging, the practical contract usually requires **each line to be a single JSON object**.

~~~text
{"level":"INFO","event":"order_started","orderId":"ord-7"}
{"level":"WARN","event":"payment_retry","orderId":"ord-7","attempt":2}
{"level":"INFO","event":"order_completed","orderId":"ord-7"}
~~~

The benefit is that events can be appended one by one and read incrementally via streaming without holding an entire massive document in memory.

Distinguish between the two representations:

**A valid pretty-printed JSON document:**

~~~json
{
  "event": "order_started",
  "level": "INFO"
}
~~~

**A valid JSONL record:**

~~~text
{"event":"order_started","level":"INFO"}
~~~

Both are valid JSON when evaluated as a **whole block**, but if the collector splits **each line** into a separate record, the pretty-printed object will be split incorrectly. Therefore:

- A JSONL event must fit on **one physical line**.
- Actual newlines inside a message value must be **escaped inside the JSON string**.
- Do not print a multi-line stack trace separately after the closing brace of the JSON object.
- An empty line is not a valid JSON value, even though some collectors may intentionally skip it.
- The stream should be encoded in UTF-8 without a BOM.
- The last line may have a trailing newline to make appending convenient; there is no need to add an empty object.

**Note on tooling:** a parser that accepts multiple consecutive JSON documents does not necessarily verify that each object occupies exactly one line. Conversely, a parser for a single document may reject a JSONL file containing multiple objects. You must use the **right framing check**, rather than merely asking whether the parser accepts the entire stream.

## 4. Escaping Control Characters and Protecting Event Boundaries

Suppose the actual message contains:

~~~text
gateway said: "retry"
please wait
~~~

If the application concatenates JSON strings manually:

~~~java
// INCORRECT example if message contains double quotes or newlines.
String json = "{\"message\":\"" + message + "\"}";
~~~

The result can produce invalid JSON and split into multiple physical lines. That is a form of **log injection** when untrusted values break record boundaries or forge another log line.

A standard JSON serializer converts that message into an escaped value:

~~~json
{"message":"gateway said: \"retry\"\nplease wait"}
~~~

The JSON line above still has **one physical newline at the end of the record**, with no physical newline inside the value. The backslash–n and backslash–quote sequences are escape sequences in the file, which the parser restores to the original characters when reading.

Common escapes:

| Original character | Representation in a JSON string |
| --- | --- |
| Double quote | \" |
| Backslash | \\ |
| Line feed (LF) | \n |
| Carriage return | \r |
| Tab | \t |
| Other control characters | \u00XX |

Do not write your own full escaping logic with a few `replace` calls, because strings can contain many different Unicode and control characters. **Use ObjectMapper or a dedicated JSON encoder** so the serializer handles syntax encoding.

Especially with Windows paths, a string containing an unescaped backslash can be interpreted as a tab, newline, or invalid escape. Parseable JSON does not guarantee that the parsed path value matches the original path if the string was concatenated incorrectly by hand.

**Escaping is not redaction.** A JSON object containing a password or token can still be completely valid syntactically. Do not log sensitive information simply because it is properly JSON-escaped.

## 5. Schema: Which Fields Are Required and What Types?

An illustrative JSON logging contract for a Java service:

| Field | Expected type | Required in example | Rules |
| --- | --- | --- | --- |
| timestamp | String | Yes | ISO-8601 with timezone/offset |
| level | String | Yes | TRACE, DEBUG, INFO, WARN, ERROR |
| event | String | Yes | Stable, non-empty event name |
| message | String | Yes | Non-empty message |
| durationMs | Integer | Yes | Non-negative, within long range |
| service | String | Optional | Organization-managed service name |
| requestId | String | Optional | Correlation ID when applicable |
| traceId | String | Optional | Following tracing conventions |
| errorType | String | Optional | Exception type name when an error occurs |

This is a **schema for learning**, not mandatory for every backend. An application using JUL may emit WARNING/SEVERE, while SLF4J uses WARN/ERROR. To standardize, configure level mapping in the logging pipeline.

### Checking Types Before Converting

If the input is:

~~~json
{"durationMs":"42","success":"false"}
~~~

then both values are **strings**, not a number and a boolean. Some Java APIs may coerce strings into numbers and hide the evidence of mistyped data. To diagnose schema issues, check the node's JSON type directly first, such as `isIntegralNumber()` or `isBoolean()`, rather than simply calling `asLong()` or `asBoolean()` and assuming everything is valid.

### Distinguishing Missing, Null, and Empty

The objects below represent different states:

~~~json
{"requestId":null}
~~~

~~~json
{}
~~~

~~~json
{"requestId":""}
~~~

A missing field, a `null` field, and an empty-string field do not mean the same thing in every contract. The validator must establish clear rules: an optional field may be omitted, but if present, what type must it have? For required fields, are `null` or empty values allowed?

### Wrong Value Despite Correct Type

~~~json
{"durationMs":-10}
~~~

This value may be a valid number, but it is wrong if duration must be non-negative. Similarly, an event name using a dynamic UUID may be a valid string but makes aggregation difficult; a level `"INFORMATION"` may violate the enum even though it does not violate JSON syntax.

**Schema validation should check field names, types, value ranges, and units.** Complex conditions can use JSON Schema or a contract validator, but you still need to test at the ingestion point.

## 6. Valid Timestamps and Timezones

JSON does not have a dedicated datetime type; timestamps are typically stored as strings according to the logging system's contract.

~~~json
{"timestamp":"2026-11-09T10:15:30Z"}
~~~

~~~json
{"timestamp":"2026-11-09T17:15:30+07:00"}
~~~

Both values above have an explicit offset. In Java, they can be parsed with `java.time.OffsetDateTime` and converted to `Instant`. Conversely, strings such as `"yesterday"` or `"2026-11-09 10:15:30"` are still valid as **JSON strings**, but lack the timestamp/offset format accepted by the example schema.

~~~java
// Illustrative snippet inside a method with a String variable named timestamp.
java.time.OffsetDateTime parsed =
        java.time.OffsetDateTime.parse(timestamp);
java.time.Instant utcInstant = parsed.toInstant();
~~~

Key points to understand:

1. **Being parseable** does not prove the server clock is accurate.
2. **Event timestamp** differs from **ingestion timestamp**; queues/networks can introduce latency.
3. If using UTC, write `Z` or the actual matching offset—do not arbitrarily append `Z` to local time.
4. Standardize precision and timezone across services.
5. A wrong timestamp places the event outside the dashboard's time range, even when JSON syntax is completely valid.

## 7. Duplicate Keys and Trailing Tokens

An easily overlooked issue:

~~~json
{"event":"ready","level":"INFO","level":"ERROR"}
~~~

Some JSON parsers may accept duplicate keys and take the last value; others may take the first value or throw an error. According to RFC 8259, member names **should be unique**; operationally, to prevent the collector and application from interpreting the same event in two different ways, you should **reject duplicate keys**.

Jackson provides **StreamReadFeature.STRICT_DUPLICATE_DETECTION** to detect this case.

Another case:

~~~text
{"event":"ready"} true
~~~

That line is not a single JSON value. If the code only reads the first object and ignores the remaining tokens, the validator may falsely report a pass. Jackson supports **DeserializationFeature.FAIL_ON_TRAILING_TOKENS** to reject leftover significant data after a value.

Do not confuse this with **having multiple JSONL lines**: each line is still allowed to be its own valid object, but **within a single line**, multiple documents must not be concatenated.

### Why Enable Checks Explicitly?

Libraries have different default configurations that can change across versions. If strict parsing is required, explicitly declare the critical features, write tests for duplicates/trailing tokens, and re-run tests after upgrading versions.

The cost of detecting duplicate keys can consume extra parser resources; if the validator runs on a high-volume ingest path, measure it against realistic workloads rather than guessing.

## 8. Complete Java 17+ Example: Validating a JSONL File with Jackson

This example uses Maven, **Jackson 2.18.4**, and JDK 17+. The program creates a valid event using a serializer, writes it along with error cases into a **temporary file**, reads each line, and returns one of three labels:

- **VALID:** JSON parses successfully, and the root object and fields match the sample schema.
- **INVALID_JSON:** syntax error, duplicate keys, trailing tokens, or blank line.
- **INVALID_SCHEMA:** valid JSON syntax, but invalid root, type, required field, or value.

There is no Logback or Log4j 2 dependency here because the goal is **validating already-emitted JSON records**. In production, you can combine the validator with reading actual files or streams written by the backend.

### 8.1. Project Structure

~~~text
json-log-validation/
├── pom.xml
└── src/main/java/demo/JsonLogValidationDemo.java
~~~

### 8.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
  xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://www.w3.org/2001/XMLSchema-instance">
  <modelVersion>4.0.0</modelVersion>
  <groupId>demo</groupId>
  <artifactId>json-log-validation</artifactId>
  <version>1.0.0</version>
  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>
  <dependencies>
    <dependency>
      <groupId>com.fasterxml.jackson.core</groupId>
      <artifactId>jackson-databind</artifactId>
      <version>2.18.4</version>
    </dependency>
  </dependencies>
  <build>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-compiler-plugin</artifactId>
        <version>3.13.0</version>
      </plugin>
      <plugin>
        <groupId>org.codehaus.mojo</groupId>
        <artifactId>exec-maven-plugin</artifactId>
        <version>3.5.1</version>
      </plugin>
    </plugins>
  </build>
</project>
~~~

### 8.3. JsonLogValidationDemo.java

~~~java
package demo;

import com.fasterxml.jackson.core.JsonFactory;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.core.StreamReadFeature;
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.BufferedReader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.OffsetDateTime;
import java.time.format.DateTimeParseException;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

public final class JsonLogValidationDemo {
    private static final ObjectMapper MAPPER =
            new ObjectMapper(JsonFactory.builder()
                    .enable(StreamReadFeature.STRICT_DUPLICATE_DETECTION)
                    .build())
                    .enable(DeserializationFeature.FAIL_ON_TRAILING_TOKENS);
    private static final Set<String> LEVELS =
            Set.of("TRACE", "DEBUG", "INFO", "WARN", "ERROR");

    public static void main(String[] args) throws Exception {
        Map<String, Object> event = new LinkedHashMap<>();
        event.put("timestamp", "2026-11-09T10:15:30Z");
        event.put("level", "WARN");
        event.put("event", "payment_retry");
        event.put("durationMs", 42);
        event.put("message", "gateway said: \"retry\"\nnext");
        String valid = MAPPER.writeValueAsString(event);

        List<String> input = List.of(
                valid,
                "{\"event\":\"unfinished\",",
                "{\"timestamp\":\"2026-11-09T10:15:30Z\","
                    + "\"level\":\"INFO\",\"event\":\"ok\","
                    + "\"durationMs\":\"42\",\"message\":\"done\"}",
                "{\"timestamp\":\"2026-11-09T10:15:30Z\","
                    + "\"level\":\"WARN\",\"event\":\"a\","
                    + "\"event\":\"b\",\"durationMs\":1,\"message\":\"x\"}",
                "{\"timestamp\":\"2026-11-09T10:15:30Z\","
                    + "\"level\":\"INFO\",\"event\":\"ok\","
                    + "\"durationMs\":1,\"message\":\"done\"} true",
                "{\"level\":\"INFO\",\"event\":\"ok\","
                    + "\"durationMs\":1,\"message\":\"done\"}",
                "[]");

        Path file = Files.createTempFile("json-log-validation-", ".jsonl");
        try {
            Files.write(file, input, StandardCharsets.UTF_8);
            try (BufferedReader reader =
                    Files.newBufferedReader(file, StandardCharsets.UTF_8)) {
                String line;
                int number = 0;
                while ((line = reader.readLine()) != null) {
                    System.out.println("line" + (++number) + "=" + validate(line));
                }
            }
            System.out.println("validJsonIsOneLine="
                    + !valid.contains("\n"));
        } finally {
            Files.deleteIfExists(file);
        }
    }

    private static String validate(String line) {
        if (line.isBlank()) {
            return "INVALID_JSON";
        }

        final JsonNode record;
        try {
            record = MAPPER.readTree(line);
        } catch (JsonProcessingException e) {
            return "INVALID_JSON";
        }

        if (record == null || !record.isObject()
                || !textPresent(record, "timestamp")
                || !textPresent(record, "event")
                || !textPresent(record, "message")
                || !textPresent(record, "level")
                || !LEVELS.contains(record.get("level").asText())
                || !record.path("durationMs").isIntegralNumber()
                || !record.path("durationMs").canConvertToLong()
                || record.path("durationMs").longValue() < 0) {
            return "INVALID_SCHEMA";
        }

        try {
            OffsetDateTime.parse(record.get("timestamp").asText());
        } catch (DateTimeParseException e) {
            return "INVALID_SCHEMA";
        }
        return "VALID";
    }

    private static boolean textPresent(JsonNode record, String field) {
        JsonNode value = record.path(field);
        return value.isTextual() && !value.asText().isBlank();
    }
}
~~~

### 8.4. Run Command

In the directory containing `pom.xml`, using Maven and JDK 17+:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.JsonLogValidationDemo
~~~

**Stdout verified with a real Java program:**

~~~text
line1=VALID
line2=INVALID_JSON
line3=INVALID_SCHEMA
line4=INVALID_JSON
line5=INVALID_JSON
line6=INVALID_SCHEMA
line7=INVALID_SCHEMA
validJsonIsOneLine=true
~~~

Interpreting each result:

| Line | Sample data | Why? |
| --- | --- | --- |
| 1 | Jackson serializes an object with quotes and a newline in message | Properly escaped, valid fields, and on one line |
| 2 | Unclosed object and missing value | INVALID_JSON due to syntax |
| 3 | durationMs passed as a string | INVALID_SCHEMA due to wrong type |
| 4 | Field event appears twice | INVALID_JSON due to strict duplicate detection |
| 5 | An object plus a trailing token true | INVALID_JSON due to trailing token |
| 6 | Missing timestamp | INVALID_SCHEMA |
| 7 | Root is an empty array | Parseable JSON, but INVALID_SCHEMA |

The output `validJsonIsOneLine=true` proves the serializer does not leave a **physical newline** inside the JSON text when the message contains a newline. The newline is encoded as an escape sequence.

The program uses `LinkedHashMap` to create predictable events for debugging; **schemas and queries should not depend on JSON field order**. It does not print raw JSON containing real data to the diagnostic stream.

### 8.5. Why Use BufferedReader?

Reading line by line with `Files.newBufferedReader` and `StandardCharsets.UTF_8` allows validating a JSONL file without loading the entire file into memory at once. However, `readLine()` still creates **one String for the entire line**. For untrusted input with lines hundreds of megabytes long, you need **byte/line limits or parser stream constraints** to avoid running out of memory.

The temporary file in this article is deleted in `finally`. When inspecting production logs, **do not delete or overwrite real log files**; read an accessible snapshot or stream while adhering to security policies.

### 8.6. Why Configure Jackson Before Using It?

`ObjectMapper` is created with `StreamReadFeature.STRICT_DUPLICATE_DETECTION` in `JsonFactory` and `DeserializationFeature.FAIL_ON_TRAILING_TOKENS` enabled. These two options are active validation requirements; **do not rely on parser defaults**.

Once configured, an `ObjectMapper` can be reused, avoiding creating a new mapper for every log event. Do not continuously mutate the configuration of the same mapper while multiple threads are sharing it.

### 8.7. Limitations of the Sample Validator

The validator above only enforces a **basic schema**. It does not yet check:

- Whether additional fields are prohibited.
- Event/message length limits or nested object depth.
- Specific formats for `traceId`, `service`, or `errorType`.
- Cross-event validity, such as `order_complete` only appearing after `order_started`.
- Complex JSON Schema validity or schema versioning.
- Whether the original byte stream was decoded incorrectly.
- Security issues in message/exception content.
- Whether data reached the collector and was indexed correctly.

If you need to validate multiple event types or conditional contracts, use JSON Schema or a dedicated validator and add tests for schema changes. Parsing into `JsonNode` **does not replace business-logic checks**.

## 9. Jackson and Strict Validation Options

Three points to note:

**First: `ObjectMapper.readTree` alone is not enough for schema validation.** `readTree` verifies that the data can be parsed into a JSON tree; it does not know which fields are required by the logging system.

**Second: duplicate keys can be handled differently across systems.** If the application and collector interpret the same field name in two different ways, logs can produce wrong results or cause confusion during incident investigation. Configuring strict duplicate detection helps eliminate this class of bugs.

**Third: trailing tokens must be detected when the contract requires one event per line.** Enable `FAIL_ON_TRAILING_TOKENS` so the parser does not read the first object and silently ignore the remaining data.

For oversized payloads or deeply nested data, you can apply the parser constraints of your Jackson version. Balance strictness, CPU cost, and protecting the pipeline against untrusted input.

## 10. JSON Numbers, NaN, Infinity, and Computed Data

Java has `Double.NaN`, `Double.POSITIVE_INFINITY`, and `Double.NEGATIVE_INFINITY`. They **do not have valid standard JSON number literals**.

If structured logs contain results of divisions or statistics that can produce non-finite values, the schema must define what to do:

- Reject the event or field.
- Omit the field and log a reason code.
- Use JSON `null` if the contract allows it.
- Use a clearly specified string, if the analytics system actually supports it.

Do not enable non-standard JSON numbers just because the serializer has an option for it if downstream collectors only support standard JSON.

Another failure mode is oversized numbers or precision loss: a JSON parser may read very large numbers as `BigInteger`/`BigDecimal`, whereas the application schema may require a signed 64-bit integer. That is why the example validator checks both `isIntegralNumber` and `canConvertToLong` before accepting `durationMs`.

## 11. UTF-8 and Unicode

JSON Lines is standardized on **UTF-8**. Strings containing Vietnamese characters, emojis, and Unicode characters must be properly encoded in the byte stream.

Issues to watch out for:

- Producer and consumer must agree on the charset.
- A byte stream truncated in the middle of a UTF-8 character can cause the decoder/parser to fail.
- Some decoders replace invalid bytes with a replacement character, making the data appear "valid" even though it has been altered.
- A BOM at the start of the stream can cause some parsers to fail; for JSON Lines, do not emit a BOM.
- Unicode escapes may be valid, but rendering or character normalization can differ across systems.
- Explicitly use UTF-8 when writing and reading files instead of relying on the machine's default charset.

When you need to verify at the byte level, use a decoder that reports malformed/unmappable input or test through the target pipeline. **Seeing Vietnamese diacritics display properly in the console does not prove the stored byte stream is completely valid.**

## 12. Connecting the Validator to a Real Logging Backend

In Java, final JSON generation is usually handled by the **backend encoder/layout**, not the SLF4J API alone:

| Logging stack | Where JSON events are created | What to check |
| --- | --- | --- |
| JUL | Custom Formatter or adapter | One event/object, escaping, UTF-8 |
| SLF4J + Logback | Compatible JSON encoder/layout | Correct provider, pattern does not inject non-JSON text |
| SLF4J + Log4j 2 | JSON layout/encoder and Appender | Schema/fields preserved, no duplicate output |
| Console JSON in container | Encoder → stdout/stderr → collector | One physical line/event, proper ingestion |
| JSONL file | Encoder → FileAppender/FileHandler → file | Rotation, newline, collector tailing |

A file whose content looks almost like JSON, except each line has a text prefix added:

~~~text
2026-11-09 10:15:30 INFO {"event":"order_started"}
~~~

is **no longer a single-line JSON object**. Pattern configuration, a console wrapper, or a log agent can accidentally add prefixes or suffixes. Inspect the **raw bytes/lines at the destination the collector actually reads**, not just the object created in Java.

### Exceptions and Stack Traces

If the backend prints a multi-line stack trace **outside the JSON string**, a line-by-line collector will treat the stack trace lines as separate events. For JSONL output, the stack trace must be a properly JSON-encoded field or a structure understood by both the encoder and collector.

For example:

~~~json
{"level":"ERROR","event":"payment_failed","errorType":"IllegalStateException","stackTrace":"demo.Service.handle(Service.java:42)\n..."}
~~~

This is an illustrative example, not the default output of every backend. Exception data may contain URLs, user information, SQL, or sensitive content; control both **content** and **format**.

## 13. End-to-End Testing to Collector and Dashboard

A passing `ObjectMapper` unit test **does not prove** JSON logging works in production. You need to test the entire path:

~~~text
Java code
   |
   v
SLF4J/JUL/Log4j 2 Logger
   |
   v
Backend, filter, encoder
   |
   v
stdout/stderr/file
   |
   v
Collector/agent parses JSONL
   |
   v
Index/storage mapping
   |
   v
Query/dashboard/alert
~~~

Workflow:

1. Emit an event with a non-sensitive test ID.
2. Verify the raw output is **one JSON object on one line**.
3. Parse it with a strict JSON validator and check the schema.
4. Verify the collector reads from the right stdout/file source.
5. Query the `event`/`level`/`durationMs` fields by their **actual data types**.
6. Verify timestamp and timezone are mapped correctly.
7. Check retention, log access permissions, and data sanitization policies.
8. Watch for queue drops, backpressure, or event sizes exceeding limits.

If an event cannot be found on the dashboard, the cause could be logger level filtering, an unattached backend appender, the collector reading the wrong path, wrong field mapping, a timestamp outside the time window, or the event being dropped. **Passing JSON syntax does not rule out these failures.**

## 14. How to Handle an Invalid Log Line

For a log collection pipeline, you should not silently turn every invalid input into data that merely "looks right."

| Policy | Benefit | Watch out for |
| --- | --- | --- |
| Reject and increment error counter | Keeps the ingestion contract clean | Loses content needed for diagnosis |
| Send to a protected quarantine/dead-letter area | Enables later investigation of errors | Consumes storage and may hold sensitive data |
| Skip with a warning | Keeps the pipeline processing | May lose events during an incident |
| Pause ingestion | Prevents bad data from spreading | Backpressure on sources and backlog risk |
| Auto-fix certain deterministic errors | Reduces failures from known format bugs | Easily masks root causes or alters event meaning |

**Do not automatically truncate data after the last brace or append a closing brace when an object is truncated.** Doing so can create a falsely valid record with missing or corrupted information.

Diagnostic errors should include **line number, error type, field name, schema version, source**, and other permitted metadata. Avoid logging **the entire malformed JSON line**, as it may contain tokens, personal data, or large payloads.

You can track metrics such as invalid JSON rate, schema failure rate, parse failures, ingestion drops, event size, and field mapping conflicts. Configure alerts based on rates/time windows rather than paging on every isolated minor error.

## 15. Structured JSON Containing Sensitive Data

The following example may be valid JSON, but it **should never be written to logs**:

~~~json
{"event":"login_failed","password":"plaintext-password","authorization":"Bearer secret-token"}
~~~

Standard syntax/schema checks may not notice that sensitive values have been leaked. A dedicated **data policy** is required:

- Allowlist fields permitted to be logged.
- Never log passwords, tokens, API keys, session cookies, private keys, or raw authentication headers.
- Consider pseudonyms or internal IDs for personal data that must be correlated.
- Limit the length of messages, request bodies, and stack traces.
- Apply redaction **before serialization** whenever possible.
- Protect read permissions and retention of files, collectors, dashboards, and archives.
- Do not paste production logs containing sensitive information into an online JSON validator.

**JSON escaping preserves structure; it does not remove secrets.** If a message contains a secret, the serializer can still encode and write that secret in a completely valid way.

## 16. Supporting Tools and Their Limitations

### Python json.tool

~~~bash
python -m json.tool sample.json
~~~

Suitable for validating **a single JSON document** and pretty-printing it, but not by default a tool for validating a JSONL file with **multiple JSON objects**. If the input is JSONL, validate each line individually.

### jq

~~~bash
jq -c . sample.json
~~~

Helpful for parsing and compactly printing JSON if `jq` is installed. However, `jq` can accept **multiple JSON values from the same stream**; therefore, a successful run **does not prove that each physical line has exactly one object** or that the schema is valid. Combine it with per-line checks and schema validation when strict JSONL is required.

### Online JSON Validators

Use only with dummy or sanitized data approved by your organization. Do not upload raw production logs to external services without verifying permissions and data policies.

### JSON Schema

JSON Schema is useful for required fields, types, enums, ranges, nested objects, and cross-field conditions. It does not replace byte-stream checks, JSONL framing, time synchronization, log access permissions, or end-to-end ingestion testing.

## 17. Quick Troubleshooting Table

| Symptom | Likely cause | How to fix |
| --- | --- | --- |
| Line looks like JSON but parser fails | Wrong quotes, braces, commas, or escaping | Use a standard JSON serializer and parser |
| Collector reads one event as multiple lines | Pretty-printing or unescaped newlines | One object per physical line |
| Valid JSON, but durationMs queries fail | String type instead of number | Check schema and storage mapping |
| Two level values in one event | Duplicate keys | Enable strict duplicate detection |
| Parser only accepts the first object | Trailing tokens ignored | Enable FAIL_ON_TRAILING_TOKENS |
| Root [] is treated as valid | Valid JSON, but schema requires an object | Validate the root type |
| Missing timestamp | Required field omitted | Schema validation |
| Timestamp falls outside query results | Wrong timezone/mapping | Parse offset and normalize event time |
| UTF-8 displays corrupted characters | Encoding/decoder issue or truncated stream | Inspect raw bytes and charset |
| NaN/Infinity breaks the parser | Non-finite JSON number | Choose a standard contract representation |
| Valid JSON, but event is too large | Ingestion/queue/collector limit | Limit event/message size |
| JSON exists, but dashboard lacks fields | Collector not parsing or mapping conflict | Inspect raw output and ingest pipeline |
| Stack trace becomes separate events | Multiline text outside the JSON object | Use an exception JSON encoder |
| Secrets still appear in logs | Missing allowlist/redaction | Strip at the source and control retention |
| Java test passes, but container fails | Different config/encoder/charset or log source | Inspect runtime and the real collector |
| JSON Lines contains blank lines | File/encoder added blank lines | Define an explicit reject or skip policy |

## 18. Self-Check Exercises

**Exercise 1.** Consider the data:

~~~json
{"event":"ready","durationMs":"42"}
~~~

Question: Is it valid JSON syntax? Does it satisfy a schema requiring `durationMs` to be an integer?

**Answer:** The syntax is valid, but the schema fails because `durationMs` is a string, not a number.

**Exercise 2.** Given:

~~~json
[{"event":"ready"}]
~~~

Question: Why does the logging validator return `INVALID_SCHEMA` even though the JSON parses?

**Answer:** The example contract requires each line to be a root object representing one event; an array is a different root type.

**Exercise 3.** Given an object where the `event` key appears twice.

Question: Which value might a parser choose, and why should strict duplicate detection be enabled?

**Answer:** Implementations can differ, leading to discrepancies between the application and the collector. Rejecting duplicate keys establishes a consistent rule.

**Exercise 4.** A real message contains double quotes and newlines. What is the safe way to output JSONL?

**Answer:** Use a serializer; quotes and newlines inside the string are escaped, keeping the entire object on one physical line.

**Exercise 5.** A JSON object is pretty-printed across four lines, and the collector splits by line.

**Answer:** The object may be a valid JSON document, but it has **invalid JSON Lines framing** for that collector.

**Exercise 6.** JSON syntax passes, but the timestamp lacks a timezone and `durationMs` is in seconds instead of milliseconds.

**Answer:** There are schema/semantic issues; you need a timestamp with an offset and consistent unit rules.

**Exercise 7.** A JSON record is verified as valid by a unit test, yet it does not appear on the dashboard.

**Answer:** Check the backend encoder/output, collector, event timestamp, ingestion drops, mapping, and query—do not stop at the JSON parser.

**Exercise 8.** A valid JSON event contains a 10 MB stack trace, while the collector limit is 1 MB.

**Answer:** It may be rejected or truncated at ingestion; you need length limits and a dedicated exception policy.

## 19. JSON Logging Validation Checklist

- [ ] Clearly define whether the contract is **JSON document** or **JSONL/NDJSON**.
- [ ] If JSONL, each physical line contains one root object/event.
- [ ] Use UTF-8 consistently and avoid unexpected BOMs.
- [ ] The serializer/encoder properly escapes quotes, backslashes, newlines, and control characters.
- [ ] The parser does not accept disallowed non-standard syntax.
- [ ] Reject duplicate keys when the schema requires unique field names.
- [ ] Reject trailing tokens after an event.
- [ ] Verify the root object and required fields.
- [ ] Numbers remain numbers and booleans remain booleans, without silent type coercion.
- [ ] Timestamps are parseable and have an explicit timezone/offset.
- [ ] Handle null/missing/empty fields according to the contract.
- [ ] Validate enums, ranges, and units.
- [ ] Stack traces/errors are encoded inside JSON values without breaking framing.
- [ ] Event size and nesting depth are appropriately bounded.
- [ ] Do not output secrets, tokens, or unauthorized personal data.
- [ ] Test with malformed JSON, duplicates, trailing tokens, wrong types, missing fields, array roots, and inputs with Unicode/newlines.
- [ ] Inspect the raw output written by the **real backend**, not just Java objects.
- [ ] Successfully query a test event in the **final collector/storage**.
- [ ] Monitor invalid line counts, parse failures, schema conflicts, and dropped logs.

## 20. References

- [RFC 8259 — The JavaScript Object Notation (JSON) Data Interchange Format](https://www.rfc-editor.org/rfc/rfc8259): JSON syntax, data types, and Unicode.
- [JSON Lines](https://jsonlines.org/): one JSON value per UTF-8 line.
- [Jackson Databind](https://github.com/FasterXML/jackson-databind): ObjectMapper, JsonNode, and data binding.
- [Jackson Core](https://github.com/FasterXML/jackson-core): parser, generator, and strict parsing.

**Conclusion:** In JSON logging, a truly reliable event requires **valid JSON syntax, proper one-event-per-line boundaries, valid schema/data types, and a working collection pipeline**. Checking duplicate keys, trailing tokens, timestamps, Unicode, size limits, and security right at the source helps prevent logs that parse cleanly yet cannot be queried—or worse, cause confusion during incident investigations.