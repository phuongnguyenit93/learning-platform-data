# Log Schema — The Data Contract for Structured Logging in Java

## 1. What is a log schema?

A **log schema** is a set of rules describing the **structure, data types, and semantics** of a log event: which fields are required, which fields are optional, the name and type of each field, units of measurement, valid value sets, how timestamps, errors, and context are represented, and how the schema evolves across versions.

A log can serve two groups of readers:

- **Humans:** reading messages, exceptions, and context to understand an incident.
- **Machines:** parsers, collectors, queries, dashboards, alerts, and observability systems need fields with a stable contract.

Example of the same event type with different data:

~~~json
{"schemaVersion":1,"timestamp":"2026-11-09T10:15:00.125Z","level":"INFO","service":"checkout-api","event":"order.created","requestId":"req-001","durationMs":18,"message":"Order accepted"}
{"schemaVersion":1,"timestamp":"2026-11-09T10:15:02.500Z","level":"INFO","service":"checkout-api","event":"order.created","requestId":"req-002","durationMs":32,"message":"Order accepted"}
~~~

The two lines above are **illustrative data**. Values vary per request, but the **field names, data types, units, and event semantics** do not change. That is the property of a stable schema.

**A log schema does not have to be JSON**, even though JSON Lines is a convenient output format. You can have a schema for logfmt/key=value or another protocol; what matters is that the producer and consumer agree on the same contract.

### How does a schema differ from a layout/formatter?

| Concept | Role | Example |
| --- | --- | --- |
| Log event/record | Event data in memory before output | Level, message, logger, timestamp, Throwable |
| Schema | Field names, types, semantics, units, required/optional | durationMs is a number; errorCode is a string |
| Format/serialization | How data is represented as strings or bytes | JSON Lines, text pattern, logfmt |
| Formatter/Layout/Encoder | Software component that produces the output | JUL Formatter; Logback PatternLayoutEncoder |
| Handler/Appender | Writes to a destination | Console, file, remote collector |
| Collector/parser | Receives and interprets records | JSON parser, index mapping, alert queries |

**A line that looks like JSON is not necessarily a good structured log:** if `durationMs` in service A is a number while service B uses the string `"18ms"`, or service C uses a different field name, parsers and aggregations will still fail.

## 2. Why design a schema before logging heavily?

A Java project might start with:

~~~text
Payment failed!
Could not pay for order ORD-42.
Timeout contacting gateway for order ORD-42.
~~~

These messages may be readable, but it is very hard to build reliable alerts based on exact wording. When copy changes across frameworks, languages, or refactors, old filters may stop matching.

A schema lets you use a stable identifier:

~~~json
{"event":"payment.failed","errorCode":"UPSTREAM_TIMEOUT","orderId":"ORD-42","message":"Gateway did not respond"}
~~~

Practical benefits:

1. **Accurate querying:** filter by `event=payment.failed` and `errorCode=UPSTREAM_TIMEOUT` instead of searching message text.
2. **Wording-independent dashboards:** messages can change without metrics disappearing.
3. **Cross-service correlation:** `traceId`, `spanId`, and `requestId` have consistent names and types.
4. **Duration analysis:** `durationMs` is a number, so it can be compared and aggregated.
5. **Managing schema evolution:** two application versions emitting logs simultaneously still have a strategy for reading them.
6. **Data protection:** defines an allowlist and prohibits logging sensitive fields.
7. **Lower parser cost:** fewer ad-hoc formats and fewer unexpected fields.
8. **Incident investigation:** know which event happened, when, in which component, and with what outcome.

A schema is a **data contract between the application emitting logs and the systems consuming them**. It does not by itself guarantee that an event reaches storage; levels, appenders, networks, and collectors can still drop records.

## 3. The path of a structured log

~~~text
Application code
       |
       v
SLF4J / JUL / Log4j 2 API
       |
       v
Log event + context + attributes
       |
       v
Backend: level / filters / appenders
       |
       v
Encoder / Formatter per schema
       |
       v
JSON Lines / text / structured transport
       |
       v
stdout, stderr, file, or agent
       |
       v
Collector -> validation -> mapping
       |
       v
Search / Dashboard / Alert / Investigation
~~~

There are two layers to control:

**Producer:** the application and backend must generate fields with the right types and meanings; the encoder must escape and represent events properly.

**Consumer:** the collector must read event boundaries accurately, map fields to the right types, accept compatible versions, and enforce retention and access controls.

A great schema on paper is worthless if the actual encoder does not emit those fields. Conversely, valid JSON that the collector has not parsed or indexed still cannot be queried by field as expected.

## 4. Event envelope — common fields

A practical schema is usually divided into:

- **Common envelope:** fields shared across all events, such as `schemaVersion`, `timestamp`, `level`, `service`, `event`.
- **Event-specific fields:** `orderId`, `paymentMethod`, `durationMs`, `errorCode`, `retryable`, etc.
- **Correlation context:** `requestId`, `traceId`, `spanId` when available.
- **Diagnostic details:** `message` and `exception` according to policy.

Reference table:

| Field | Recommended Type | Required? | Meaning |
| --- | --- | --- | --- |
| **schemaVersion** | integer | Yes | Log contract version |
| **timestamp** | RFC 3339 string with timezone | Yes | Time the event was recorded |
| **level** | string enum | Yes | TRACE, DEBUG, INFO, WARN, ERROR per normalized convention |
| **service** | string | Yes | Name of the application/service emitting the log |
| **event** | string | Yes | Stable event type code |
| **message** | string | Per contract | Human-readable description |
| **logger** | string | Optional | Logger/class name |
| **environment** | string | Optional | production, staging, development |
| **requestId** | string | Per event type | Correlation ID within a request |
| **traceId** | string | When tracing is enabled | Distributed trace ID |
| **spanId** | string | When tracing is enabled | Span ID of the log event |
| **outcome** | string enum | Per event type | success, failure, retry, cancelled, etc. |
| **errorCode** | string | When an error code exists | Stable error code, not the exception message |
| **durationMs** | number | Events with duration | Duration in milliseconds |
| **retryable** | boolean | Applicable events | Whether the operation can be retried |
| **exception** | object | When needed | Error type, cause, stack trace per policy |

This is a **learning recommendation**, not the only standard. If your organization already uses field names from an observability platform (such as `service.name` or `trace_id`), align with that system. Do not invent a new schema that conflicts with the chosen standard.

### How many fields are enough?

**Do not force every event to include every field.** A startup event may not have a `requestId`, whereas `order.created` should have an `orderId`. A `payment.failed` event may require `errorCode`. Define **required/optional rules per event type**, not just in a single flat table.

A failing event should not generate hundreds of arbitrary fields just because data happens to be in an object. Log only **fields with diagnostic value** that are permitted to be stored.

## 5. Field naming conventions and structure

Choose one consistent naming style:

- **camelCase:** `requestId`, `errorCode`, `durationMs`.
- **snake_case:** `request_id`, `error_code`, `duration_ms`.
- **Dotted names:** `service.name`, `http.request.method`, if required by an existing standard.

JSON can have a key `"service.name"` containing a literal dot, or a nested object `{"service":{"name":"..."}}`; these two structures **must not be assumed to be equivalent**. Collectors may map them differently, so specify which one you use.

Field names should reflect their meaning:

- **durationMs** instead of `time`, if measuring milliseconds.
- **httpStatusCode** instead of generic `status`, if it is actually an HTTP status.
- **errorCode** instead of `error`, if it is a business/domain code.
- **requestId** distinct from `customerId`, `transactionId`, or `traceId`.
- **event** holds the event type code, not a dynamic per-request ID.

**Do not put userId/orderId into field names**, such as key `user_123` or event `order.created.ORD-7`, because that bloats the schema and breaks grouping by event type.

## 6. Data types, units, and null semantics

### 6.1. Keep types consistent

~~~json
{"durationMs":18,"attempt":2,"retryable":true}
~~~

This is completely different in data type from:

~~~json
{"durationMs":"18ms","attempt":"2","retryable":"yes"}
~~~

The second line is valid JSON, but it violates the defined schema. Data types affect comparisons, aggregations, and validation.

| Field | Contract Type | Valid Example | Example to Avoid |
| --- | --- | --- | --- |
| durationMs | number | 18, 18.5 | "18 ms" |
| sizeBytes | integer | 1048576 | "1MB" |
| attempt | integer | 2 | "second" |
| retryable | boolean | true | "true" |
| httpStatusCode | integer | 503 | "HTTP 503" |
| requestId | string | "req-0007" | 7 if leading zeros are lost |
| outcome | string enum | "success" | "ok" if undefined |

For long identifiers, consider representing them as **strings** to avoid precision loss in systems that use finite-precision numbers.

### 6.2. Missing, null, and empty are three distinct states

~~~json
{"event":"order.created"}
{"event":"order.created","requestId":null}
{"event":"order.created","requestId":""}
~~~

You can define them as:

- **Missing field:** not applicable or not present in this event type.
- **null:** the field is defined, but its value is unknown.
- **"" (empty string):** an empty value; usually invalid for an ID.

There is no universal rule for all systems, but **producer and consumer must agree**. Do not write the string `"null"` when you mean a true JSON `null`.

### 6.3. Units belong in the field name

**durationMs** is milliseconds; **sizeBytes** is bytes; **timeoutMs** is milliseconds. Do not change `durationMs` from 18 milliseconds to 18 seconds while keeping the same field name, as that is a severe semantic change.

When microsecond-precision timestamps are needed, document and test the precision explicitly; do not assume every logger/backend supports the same precision.

## 7. Standard timestamps and event ordering

Timestamps are critical but error-prone when multiple JVMs run in different timezones.

Use an instant with an explicit offset; **UTC with a `Z` suffix** is a common choice:

~~~json
{"timestamp":"2026-11-09T10:15:00.125Z"}
~~~

Specify clearly:

1. **Event time or ingestion time?** The time Java emits the log differs from the time the collector receives the record.
2. **Timezone:** UTC/Z or a specific offset; avoid ambiguous local times.
3. **Precision:** seconds, milliseconds, microseconds, or nanoseconds.
4. **Clock:** whether the timestamp is generated by Java, sent by upstream, or attached by the collector.
5. **Ordering:** timestamps from two hosts may not be enough to determine absolute order when clocks drift.

In Java:

~~~java
String timestamp = java.time.Instant.now().toString();
~~~

This is an **illustrative Java snippet**. `Instant.now()` gives an instant on the UTC scale, but the fractional seconds format can vary with precision; if you need exactly three millisecond digits, use a chosen formatter and test it. Do not treat **`LocalDateTime.now()`** without a timezone as sufficient for distributed logs.

## 8. Event codes and taxonomy

Use event codes that describe the action/event type, such as `domain.action`:

~~~text
order.created
order.cancelled
payment.retry
payment.failed
job.started
job.completed
cache.miss
~~~

**An event code is not a unique value per record.** Do not use `payment.failed.req-42`; instead use:

~~~json
{"event":"payment.failed","requestId":"req-42"}
~~~

Document the exact meaning:

- **order.created:** the order has been created per the business contract (distinguish receiving a request from a successful commit).
- **payment.retry:** a retry attempt occurred, not necessarily a final failure.
- **payment.failed:** the operation is considered failed at a defined boundary.
- **job.completed:** the job finished as defined, optionally accompanied by an `outcome`.

Use **message** for human explanation, but build queries and alerts on `event` codes, `errorCode`, and clearly defined fields. If event semantics change, evaluate versioning rather than keeping the old name and misleading consumers.

## 9. ERROR, exceptions, and stack traces

An error event can include a stable **errorCode** and exception data for investigation:

~~~json
{
  "schemaVersion": 1,
  "level": "ERROR",
  "service": "checkout-api",
  "event": "payment.failed",
  "errorCode": "UPSTREAM_TIMEOUT",
  "exception": {
    "type": "java.net.SocketTimeoutException",
    "message": "Gateway did not respond",
    "stackTrace": "java.net.SocketTimeoutException: Gateway did not respond\n    at demo.PaymentClient.call(PaymentClient.java:42)"
  }
}
~~~

This is **illustrative data**. In JSON, newlines inside the `stackTrace` string are escaped as **`\n`**; it is not a new physical text log line.

Several decisions need alignment:

- Should `errorCode` use a business enum or technical codes?
- Is `exception` a nested object or flat keys like `exception.type` and `exception.stacktrace`?
- Is `stackTrace` size-bounded?
- Should the cause chain be stored, and how is sensitive data exposure handled?
- Does the collector parse JSON Lines or multiline text?

**Do not use `exception.message` content as `errorCode`**: messages can vary by library and locale, and may contain file paths or user data. Do not log the same `Throwable` at every layer if it only produces duplicate stack traces without adding investigative information.

## 10. JSON Lines and record boundaries

**JSON Lines** represents **each log event as one JSON object on a single physical line**, helping collectors process streams more reliably than free-form text:

~~~json
{"schemaVersion":1,"event":"order.created","message":"Order accepted"}
{"schemaVersion":1,"event":"payment.failed","message":"Gateway unavailable"}
~~~

If a message contains newlines and quotes:

~~~text
Gateway replied: "retry"
Check gateway
~~~

Then a proper JSON encoder must output:

~~~json
{"schemaVersion":1,"event":"payment.failed","message":"Gateway replied: \"retry\"\nCheck gateway"}
~~~

The **`\n`** inside the JSON is the escape sequence for a newline within the `message` value; the object remains **a single physical line**. User-supplied data can contain quotes, backslashes, control characters, and Unicode, so **never build JSON by string concatenation without escaping**.

Beyond valid JSON, you also need:

- **Event size limits:** collectors/drivers may truncate oversized records.
- **Correct encoding:** typically UTF-8, from encoder to storage.
- **Exception boundaries:** structured exception fields or a multiline policy must be consistent.
- **Typed fields:** JSON numbers, booleans, and nulls must match the contract.
- **Collector parser:** simply printing JSON does not automatically index all fields.
- **No reliance on key order:** JSON objects do not define key order as semantic; consumers read by key name.

A JSON schema helps organize data; it **does not by itself provide durability**. An event logged via a `Logger` can still be dropped by a level/filter, dropped by a queue, or lost when a collector fails.

## 11. Runnable Java 17 Example — SLF4J + Logback + Jackson

We will produce two JSON Lines events containing **schemaVersion, timestamp, level, service, logger, event, requestId, message**, plus event-specific fields. Java code logs via **SLF4J**, Logback writes to stdout, and Jackson handles serialization/escaping.

**Intentional limitation:** This is a demo for learning schemas and deterministic output, using Java to build JSON before calling the logger. In production systems, prefer a **typed structured logging API and a backend-integrated JSON encoder** to capture timestamp, level, `Throwable`, and MDC automatically, rather than requiring every service to assemble JSON manually.

### 11.1. Project structure

~~~text
schema-log-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── demo/
        │       └── SchemaLogDemo.java
        └── resources/
            └── logback.xml
~~~

### 11.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>schema-log-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.slf4j</groupId>
            <artifactId>slf4j-api</artifactId>
            <version>2.0.17</version>
        </dependency>
        <dependency>
            <groupId>ch.qos.logback</groupId>
            <artifactId>logback-classic</artifactId>
            <version>1.5.18</version>
        </dependency>
        <dependency>
            <groupId>com.fasterxml.jackson.core</groupId>
            <artifactId>jackson-databind</artifactId>
            <version>2.18.3</version>
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
                <version>3.5.0</version>
                <configuration>
                    <mainClass>demo.SchemaLogDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

The versions above are just a specific illustrative set, **not a claim that they are the latest**. For real projects, use dependency management and check for security patches.

### 11.3. src/main/resources/logback.xml

~~~xml
<configuration>
    <appender name="STDOUT"
              class="ch.qos.logback.core.ConsoleAppender">
        <target>System.out</target>
        <encoder>
            <charset>UTF-8</charset>
            <pattern>%msg%n</pattern>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="STDOUT"/>
    </root>
</configuration>
~~~

Logback uses **`%msg%n`** to print the message and a newline without adding an external level/timestamp outside the JSON. In the demo, `level` and `timestamp` fields are placed inside the JSON for fixed output. **Do not treat this as a comprehensive production JSON encoder.**

### 11.4. src/main/java/demo/SchemaLogDemo.java

~~~java
package demo;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.LinkedHashMap;
import java.util.Map;

public final class SchemaLogDemo {
    private static final Logger LOG =
            LoggerFactory.getLogger(SchemaLogDemo.class);
    private static final ObjectMapper JSON = new ObjectMapper();

    public static void main(String[] args)
            throws JsonProcessingException {
        Map<String, Object> created = event(
                "2026-11-09T10:15:00.125Z",
                "INFO", "order.created", "req-7",
                "Order accepted");

        created.put("orderId", "ORD-7");
        created.put("durationMs", 18);
        LOG.info("{}", JSON.writeValueAsString(created));

        Map<String, Object> failed = event(
                "2026-11-09T10:15:02.100Z",
                "ERROR", "payment.failed", "req-7",
                "Gateway replied: \"retry\"\nCheck gateway");

        failed.put("errorCode", "PAYMENT_TIMEOUT");
        failed.put("retryable", true);
        LOG.error("{}", JSON.writeValueAsString(failed));
    }

    private static Map<String, Object> event(
            String timestamp, String level, String event,
            String requestId, String message) {

        Map<String, Object> fields = new LinkedHashMap<>();
        fields.put("schemaVersion", 1);
        fields.put("timestamp", timestamp);
        fields.put("level", level);
        fields.put("service", "checkout-api");
        fields.put("logger", LOG.getName());
        fields.put("event", event);
        fields.put("requestId", requestId);
        fields.put("message", message);
        return fields;
    }
}
~~~

`LinkedHashMap` preserves field insertion order, and Jackson with the default configuration above serializes the map in that order. This is only for readability/diffing; **key order is not a semantic part of a JSON schema**.

### 11.5. Compile and run

Requires **JDK 17+**, Maven, and dependencies available locally or downloadable:

~~~bash
mvn -q compile exec:java
~~~

With the exact files above, **stdout emitted by the Java program** (excluding any Maven/runtime-specific output):

~~~json
{"schemaVersion":1,"timestamp":"2026-11-09T10:15:00.125Z","level":"INFO","service":"checkout-api","logger":"demo.SchemaLogDemo","event":"order.created","requestId":"req-7","message":"Order accepted","orderId":"ORD-7","durationMs":18}
{"schemaVersion":1,"timestamp":"2026-11-09T10:15:02.100Z","level":"ERROR","service":"checkout-api","logger":"demo.SchemaLogDemo","event":"payment.failed","requestId":"req-7","message":"Gateway replied: \"retry\"\nCheck gateway","errorCode":"PAYMENT_TIMEOUT","retryable":true}
~~~

There are **exactly two physical lines**: Jackson escaped the quotes and newline in the error message. If Maven or the terminal produces its own output, distinguish it from the two expected business log lines.

### 11.6. Explanation

1. The **`event(...)`** method sets the shared envelope fields.
2. **`orderId`/`durationMs`** belong only to `order.created`; **`errorCode`/`retryable`** belong to `payment.failed`.
3. **`durationMs=18`** is a number and **`retryable=true`** is a real JSON boolean, not strings.
4. **`ObjectMapper`** serializes and escapes special characters properly.
5. **`LOG.info`/`LOG.error`** determine the emitted log level, while the `level` field in the demo code is passed manually; production should let the backend/encoder capture the actual level to avoid inconsistency.
6. **`ConsoleAppender`** writes to stdout, which works with collectors configured to accept JSON Lines.
7. **Fixed timestamps** are used only so the example has reproducible output. Production needs real timestamps with a timezone per the schema.
8. The code provides no audit/durability guarantees. A log call can still be filtered, dropped, or fail on I/O.

### 11.7. Why should production use a structured encoder?

If every service builds JSON manually like the demo, it is easy to miss fields, add fields with the wrong type, enter a level that differs from the backend, omit MDC/`Throwable`, or create duplicate fields. A better approach is a **shared typed event contract + standardized, tested structured logging API/encoder**.

SLF4J 2.x supports fluent key-value logging:

~~~java
// Illustrative snippet inside a class with LOG and an orderId variable.
LOG.atInfo()
        .addKeyValue("event", "order.created")
        .addKeyValue("orderId", orderId)
        .addKeyValue("durationMs", 18)
        .log("Order accepted");
~~~

**This is not a standalone program.** The API provides key-value pairs, but **does not by itself guarantee that every backend/encoder will output JSON or that the collector has indexed the fields**. You still need the right provider, encoder, and output validation.

## 12. JSON Schema to describe the envelope

One way to write a machine-readable contract is **JSON Schema**. The following example uses Draft 2020-12 syntax to describe the common envelope; domain-specific fields need additional schemas.

~~~json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "ApplicationLogV1",
  "type": "object",
  "required": [
    "schemaVersion",
    "timestamp",
    "level",
    "service",
    "event",
    "message"
  ],
  "properties": {
    "schemaVersion": {
      "type": "integer",
      "const": 1
    },
    "timestamp": {
      "type": "string",
      "format": "date-time"
    },
    "level": {
      "type": "string",
      "enum": ["TRACE", "DEBUG", "INFO", "WARN", "ERROR"]
    },
    "service": {
      "type": "string",
      "minLength": 1
    },
    "event": {
      "type": "string",
      "minLength": 1
    },
    "message": {
      "type": "string"
    },
    "requestId": {
      "type": "string",
      "minLength": 1
    },
    "durationMs": {
      "type": "number",
      "minimum": 0
    },
    "retryable": {
      "type": "boolean"
    }
  },
  "additionalProperties": true
}
~~~

A few notes:

- **`additionalProperties=true`** allows event-specific fields. If you want to allow only a fixed set of fields, design event-specific schemas or appropriate composition rules.
- **`format=date-time`** may be treated only as an annotation by some JSON Schema validators; if you need to catch invalid timestamps, enable format assertion or add separate parsing checks.
- **`required`** checks field presence, not whether the event semantics are valid.
- **`level` enum** here follows SLF4J/Logback conventions; JUL has `WARNING`, `SEVERE`, etc., so normalize them or use a separate schema when collecting from JUL.
- This schema does not yet enforce that **`payment.failed` requires `errorCode`**, PII restrictions, field lengths, or propagation. Add per-event rules and tests.
- Keep **`schemaVersion`** aligned with the deployed contract; do not bump the number without migrating consumers.

## 13. Testing JSON Lines and the contract

With the Maven example, redirect stdout:

~~~bash
mvn -q compile exec:java > events.jsonl
~~~

If Maven prints other output to stdout, the file may contain content besides the two JSON lines; check your console/logs and how your environment runs Maven. In production, applications typically emit a dedicated stream per infrastructure configuration.

You can use Python 3 to parse each JSONL line:

~~~bash
python3 -c 'import json; [json.loads(line) for line in open("events.jsonl", encoding="utf-8")]'
~~~

The command prints nothing if every line parses; **that only checks JSON syntax**, not all schema rules.

A script to check types and correlation:

~~~python
import json

with open("events.jsonl", encoding="utf-8") as stream:
    events = [json.loads(line) for line in stream if line.strip()]

assert len(events) == 2
assert all(event["schemaVersion"] == 1 for event in events)
assert all(isinstance(event["event"], str) for event in events)
assert all(event["level"] in {"TRACE", "DEBUG", "INFO", "WARN", "ERROR"}
           for event in events)
assert isinstance(events[0]["durationMs"], int)
assert isinstance(events[1]["retryable"], bool)
assert events[0]["requestId"] == events[1]["requestId"]
print("SCHEMA_CHECK_PASS")
~~~

Save as **`check_schema.py`** and run:

~~~bash
python3 check_schema.py
~~~

When `events.jsonl` contains the exact two demo logs, **stdout** is:

~~~text
SCHEMA_CHECK_PASS
~~~

The Python snippet is only an **auxiliary verification tool**, not a Java dependency. In a Java project, you can write equivalent JUnit/Jackson validation. If you have many events and complex schemas, use a JSON Schema validator with a unified configuration.

### Types of tests you should have

- **Schema and types:** required fields, null/missing, numbers, booleans, enums.
- **Timestamps:** UTC/offset, precision, parsing across locales.
- **Escaping:** quotes, newlines, backslashes, control characters, and Unicode.
- **Exceptions:** stack traces do not break single-line JSONL boundaries.
- **MDC/correlation:** `requestId`/`traceId` are propagated and cleared in the right scope.
- **Routing:** logs are not duplicated by additivity/handlers and not unintentionally filtered out.
- **Real collector:** parser/indexer reads fields properly and alerts do not lose data during deploys.
- **Versioning:** both old and new schemas have a working handling path.
- **Security:** no tokens, passwords, or sensitive raw requests appear in fields.
- **Size:** oversized records are handled according to policy.

**Golden tests** are useful, but dynamic timestamps/thread IDs must be normalized or use a fixed `Clock`; do not remove production timestamps just to make tests easier. For JSON, comparing parsed objects by field is usually more resilient than comparing key order.

## 14. Schema versioning and compatibility

Schemas evolve over time, so classify changes clearly.

### Generally more compatible changes

- Adding an **optional** field with a documented type and meaning.
- Adding a **new event code** without changing the meaning of existing events.
- Adding metadata that old consumers are designed to ignore.
- Changing message wording when queries/alerts do not depend on that literal text.

Even additive changes must be tested against parsers and mappings, because an older collector might reject unknown fields or hit a field conflict.

### Breaking changes

| Change | Potential Consequence |
| --- | --- |
| `durationMs=18` changed to `"18ms"` | Numeric aggregations break |
| `retryable=true` changed to `"yes"` | Boolean queries break |
| `requestId` renamed to `request_id` | Old consumers look up the wrong field |
| `outcome=success` changed to `ok` | Enums/counts are wrong |
| UTC timestamp switched to local without offset | Time-range queries are wrong |
| Single-line JSONL changed to multiline text | Parsers misread event boundaries |
| Removing a required field | Dashboards/validators fail |
| Changing the meaning of `payment.failed` | Alerts count the wrong event type |
| Changing fields while keeping `schemaVersion=1` | Consumers do not know a breaking change occurred |

### Safe migration process

1. **Document the old schema and active consumers**: searches, alerts, dashboards, long-term storage.
2. **Assess the change**: additive or breaking; what changed in name, type, unit, or semantics?
3. **Design a new `schemaVersion` and contract** if needed.
4. **Provide a transition path**: temporarily emit both old/new fields, or have the collector normalize or accept both versions.
5. **Roll out in phases**: prepare consumers first, then retire the old producer when ready.
6. **Monitor quality**: parse errors, missing fields, unknown versions, ingestion drops.
7. **Update tests, documentation, and queries/alerts**.
8. **Decommission the old version in a controlled way**, without breaking historical data.

**`schemaVersion` alone does not transform data.** Consumers must know how to read or convert the corresponding version.

## 15. Correlation, MDC, and tracing

A request spanning multiple services might produce:

~~~json
{"schemaVersion":1,"level":"INFO","service":"gateway","event":"request.accepted","requestId":"req-42"}
{"schemaVersion":1,"level":"INFO","service":"pricing","event":"price.calculated","requestId":"req-42"}
{"schemaVersion":1,"level":"ERROR","service":"payment","event":"payment.failed","requestId":"req-42","errorCode":"UPSTREAM_TIMEOUT"}
~~~

This is illustrative data. Keeping the same **field name and type** for `requestId` makes per-request investigation possible; `traceId` and `spanId` should follow the standard of your active tracing system.

With SLF4J/Logback, you can use MDC:

~~~java
// Code snippet inside a class that already has LOG:
try (org.slf4j.MDC.MDCCloseable ignored =
        org.slf4j.MDC.putCloseable("requestId", "req-42")) {
    LOG.info("event=order.created");
}
~~~

**MDC does not automatically propagate across all thread pools, `CompletableFuture`, or reactive pipelines**. You need context propagation and proper scope cleanup to avoid mixing request IDs between tasks. **MDC also does not guarantee that the encoder outputs the field as JSON**; the backend must be configured accordingly.

Do not use unbounded `requestId`/`traceId` values as metric labels due to cardinality; they belong in logs and traces.

## 16. Schemas must account for size, security, and cost

### 16.1. Event size

A log can be schema-valid yet still too large to transmit or store, especially with `stackTrace`, payloads, and lists. Define:

- Size limits for records/messages and potentially large fields.
- A truncation policy with a signal (e.g., `truncated=true`), avoiding truncating `event`, `errorCode`, or `requestId`.
- How to handle long exceptions or deeply nested objects.
- Concrete limits of your runtime, agent, collector, and log storage.
- Monitoring for rejected, truncated, or dropped events.

There is no single byte limit that fits every organization; limits must match your pipeline and actual load.

### 16.2. Field explosion and cardinality

Do not create dynamic JSON keys like:

~~~json
{"user_123":true,"user_124":false,"user_125":true}
~~~

Instead, if you genuinely need per-subject information:

~~~json
{"event":"feature.checked","subjectId":"user-123","enabled":true}
~~~

Even then, `subjectId` may still be sensitive or high-cardinality. Apply access control, retention, and consider whether it needs to be indexed. **Unbounded field name growth** and **many distinct values for a single field** are two different problems; both can drive up cost.

### 16.3. Security

Do not log **passwords, access tokens, API keys, private keys, session cookies, payment card data, or sensitive personal information** in raw JSON logs. Do not log entire HTTP requests/responses or `object.toString()` by default.

- Build an allowlist of fields permitted for output.
- Apply masking/redaction per policy, tested at the producer and before storage.
- Escape untrusted data to prevent structure breaking / log injection.
- Restrict read permissions, retention periods, and sharing pipelines.
- Review `exception.message` and `stackTrace` because they can contain internal details.

**A JSON serializer only produces valid strings; it does not automatically redact sensitive data.** The `DEBUG` level is not a security boundary either, because it can be enabled unexpectedly during an incident.

### 16.4. Observability is not an audit store

A `LOG.info(...)` call can be filtered by the logger or appender, dropped by a queue, or lost on a storage failure. A schema does not create a durability guarantee. If an event must be **persisted as a condition of a transaction**, choose an audit/storage system with the appropriate durability contract; do not rely solely on a diagnostic logging pipeline.

## 17. Common mistakes

| Mistake | Consequence | How to Avoid |
| --- | --- | --- |
| No event code | Queries depend on message wording | Use a stable `event` field |
| `durationMs` sometimes a number, sometimes a string | Aggregations fail | Keep types and units consistent |
| `requestId` sometimes camelCase, sometimes snake_case | Fragmented queries | Enforce a naming convention |
| Timestamp without offset | Ambiguous across hosts | Use UTC/RFC 3339 |
| Long IDs emitted as numbers | Potential precision loss | Use strings when appropriate |
| Mixing `null`, missing field, and `""` | Consumers misinterpret state | Define missing/null semantics |
| Event name contains dynamic IDs | Cannot group by event type | Separate `event` and `requestId` |
| Building JSON with unescaped strings | Broken JSON or log injection | Use a serializer/encoder |
| Multiline text stack traces in JSONL | Events get split | Structured exception or multiline policy |
| Manually entered `level` differs from logger level | Wrong severity in JSON | Let the backend generate it from the event |
| Continuously adding dynamic fields | Index mapping bloat | Allowlist / typed fields |
| Not clearing MDC | Mixed `requestId` values | Context propagation and cleanup |
| Unversioned schema | Hard to detect breaking changes | Versioning and migration |
| Alerts based on message text | Changing wording breaks alerts | Base alerts on `event`/`errorCode` |
| Logging sensitive tokens/payloads | Data leak in collector | Data minimization and masking |
| Assuming JSONL auto-indexes fields | Field queries do not work | Configure collector/storage |

## 18. Checklist before deploying a new schema

1. Are **event** names and meanings stable?
2. Does the common envelope have **schemaVersion, timestamp, level, service** following conventions?
3. Which fields are required vs. optional per event?
4. Are data types and units clear and locale-independent?
5. Do timestamps include offset/precision and distinguish event time from ingestion time?
6. Are missing/null/empty semantics explained?
7. Does JSONL have one event per line, properly escaping quotes/newlines/Unicode?
8. Do errors/`Throwable`s have a schema, size limit, and masking policy?
9. Do request/trace IDs propagate across async boundaries and get emitted by the encoder?
10. Is dynamic field name generation prevented? Are record sizes bounded?
11. Does the collector parse/map fields properly, and do queries/alerts see sample events?
12. Are there contract tests and checks for old/new schemas?
13. Is there a migration process if names, types, or semantics must change?
14. Have sensitive data and retention been reviewed?
15. Is there monitoring for parse errors/drops and a designated schema owner?

## 19. Self-check questions

**Q1.** How does a log schema differ from a valid JSON string?

**Answer:** JSON is a serialization format; a schema defines field names, types, meanings, and compatibility rules. Valid JSON can still contain fields with wrong types or renamed keys outside the contract.

**Q2.** Are `durationMs=18` and `durationMs="18ms"` equivalent?

**Answer:** No. One is a number and the other is a string; numeric aggregations and queries can fail or misbehave if they are mixed.

**Q3.** Why should alerts search for `event=payment.failed` instead of the exact phrase `"Payment failed"`?

**Answer:** Event codes preserve stable semantics; messages can change wording, language, or technical details.

**Q4.** Are an absent `requestId`, `requestId=null`, and `requestId=""` automatically the same?

**Answer:** No. You must define missing/null/empty semantics; an empty ID is often invalid data.

**Q5.** Can you log a message containing newlines in JSON Lines?

**Answer:** Yes, if the encoder escapes newlines inside the value so that the record remains one JSON object on a single physical line.

**Q6.** Does serializing a `Map` to JSON with Jackson automatically make the collector index the fields?

**Answer:** No. The collector/storage must be configured to parse and map fields; valid JSON is only one step.

**Q7.** What is the risk of manually setting `level="INFO"` in JSON while calling `LOG.error`?

**Answer:** The level in the payload contradicts the actual logging event. Use an encoder that reads the level from the logging event.

**Q8.** Does setting `schemaVersion=2` make all dashboards understand the new version?

**Answer:** No. Consumers must support or transform the version; migration and testing are required.

**Q9.** Does MDC automatically propagate across all `CompletableFuture` instances and thread pools?

**Answer:** No. You need runtime-appropriate propagation/cleanup, and the encoder must emit it.

**Q10.** Should you use JSON keys like `user_123`, `user_124` for individual users?

**Answer:** No. Dynamic keys bloat schemas and indexes; use stable field names, minimize data, and manage privacy.

**Q11.** Is JSON Schema `format=date-time` always enforced by validators?

**Answer:** No. Depending on the implementation, it may be only an annotation; enable format assertions or parse validation when required by the contract.

**Q12.** Why can't console logs be used as durable audit storage just because records have `schemaVersion`?

**Answer:** A schema does not guarantee successful writes, ordering, durable storage, or integrity. Use a dedicated audit/storage mechanism when the business requires it.

## 20. Conclusion

**A log schema is the data contract of structured logging.** To make it valuable long-term:

- Keep **event codes, field names, and semantics stable**.
- Keep **data types, units, timezone-aware timestamps, and null conventions** explicit.
- Choose a **safe encoder/serializer** and single-event boundaries suited to your collector.
- **Test the schema from producer to query**, and manage versioning and breaking changes.
- Protect **sensitive data, cost, and event size**.

Printing JSON is only the first step. A consistently managed and enforced schema makes Java logs easy to query, correlate, alert on, and investigate across many deployments.
