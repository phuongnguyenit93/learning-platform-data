# Practical Project: Migrating Java Logging from Text to Structured Logs

## 1. Problem Statement and Target Outcomes

Suppose a Java application is writing text-based logs:

```text
2026-01-01 10:00:00 INFO OrderService - Cancel order O-7 failed: already shipped
2026-01-01 10:00:01 WARN OrderService - Invalid comment from req-18
```

This is useful for human readers, but search engines, dashboards, SIEMs, or alerting tools must **guess** fields using regex. When a developer changes the wording, field order, level formatting, or locale, the parser can break. When a single message contains newlines, log injection, or stack traces, event boundaries become even harder to determine.

**Structured logging** is a way of representing events using **named fields with defined data types**: `timestamp`, `level`, `service`, `eventType`, `action`, `outcome`, `reasonCode`, `requestId`, `operationId`, `durationMs`. JSON Lines/NDJSON (one JSON object per line per event) is a common format, but **structured logging is not strictly synonymous with JSON**: the schema and contract are the core parts.

After this practical exercise, learners will be able to:

1. Inventory existing text logs and identify consumers that depend on message formats.
2. Design a log schema with clear types, semantics, versioning, security requirements, and correlation IDs.
3. Emit structured events using Java 17, understanding escaping rules and null/number data.
4. Configure an application using SLF4J 2.x + Logback + a JSON encoder, distinguishing between the facade and the backend.
5. Migrate call sites incrementally from string concatenation to structured fields without altering control flow.
6. Test fields/types, JSON encoding, exceptions, MDC, log filtering, sensitive data, and duplicate events.
7. Roll out in phases, monitor pipeline quality, and roll back without losing observability.

**Acceptance criteria:** JSON logs are parseable, conform to the minimum schema, include valid correlation info, do not leak secrets, do not alter business outcomes, and are still delivered to the intended sink with the defined reliability level. Changing the format **does not automatically guarantee durability**: appenders, agents, collectors, indexes, and retention remain separate layers.

## 2. Distinguishing Text Logs, Parameterized Logs, and Structured Logs

The following three approaches are **not equivalent**:

### A. Text String Concatenation

```java
// Should not be used as a machine-readable contract.
logger.info("Cancel order " + orderId
        + " rejected because " + reasonCode);
```

This builds a text message and may incur string construction cost even when INFO is disabled. If `reasonCode` or `orderId` comes from untrusted input, there is a risk of log injection or data leakage.

### B. Parameterized Text with SLF4J

```java
logger.info(
    "Cancel order {} rejected because {}",
    safeOrderId, reasonCode);
```

This passes arguments into the logging API via `{}` placeholders and can reduce eager string concatenation. However, **the final output may still be just a single string**; downstream systems will not automatically receive separate `orderId`/`reasonCode` fields if the encoder does not support it.

### C. Structured Event

```java
// SLF4J 2.x fluent API; requires backend/encoder support for output fields.
logger.atInfo()
    .addKeyValue("eventType", "ORDER_CANCEL_RESULT")
    .addKeyValue("action", "ORDER_CANCEL")
    .addKeyValue("orderId", safeOrderId)
    .addKeyValue("outcome", "REJECTED")
    .addKeyValue("reasonCode", reasonCode)
    .log("Cancellation rejected");
```

The call above represents **key–value pairs** on the logging event. Whether they appear in JSON as queryable fields depends on the **running provider/encoder**. Do not conclude "we have structured logging" just from calling `addKeyValue`; you must **inspect the actual record at the sink**.

An expected JSON result:

```json
{
  "schemaVersion": 1,
  "@timestamp": "2026-01-01T10:00:00Z",
  "level": "INFO",
  "service": "order-service",
  "eventType": "ORDER_CANCEL_RESULT",
  "action": "ORDER_CANCEL",
  "orderId": "O-7",
  "outcome": "REJECTED",
  "reasonCode": "ORDER_ALREADY_SHIPPED",
  "message": "Cancellation rejected"
}
```

The name `@timestamp` is just **one schema choice**; the JDK demo in section 7 uses `timestamp`. Choose **one published contract** or a versioned mapping; do not let both names appear simultaneously by accident. This JSON is a formatting example, not an exact promise of every default field from a Logback encoder.

## 3. System Inventory Before Migration

First, find **what currently exists and what depends on it**. An example inventory table:

| Emission Point | Current Log | Users/Consumers | Risk When Changing |
| --- | --- | --- | --- |
| HTTP boundary | Method, path, status, duration text | Latency dashboard, support | Regex parser breaks, URL leaks query secrets |
| Domain service | `Order O-7 rejected` | Business ops | Missing `reasonCode`, hard to group |
| Payment client | Error + stack | On-call alerts | Stack leaks token/URL, alert counts change |
| Message consumer | `Processed msg-1` | Retry debugging | Message ID and attempt are not separated |
| Security boundary | `Access denied` | Audit/SIEM | Missing trusted actor/action/outcome |
| Background job | `Job finished` | Operational SLO | Unknown pending, partial, failed counts |
| Application startup | Config summary | On-call | Config might contain secrets |

For each emission point, record:
- Logger/category name, effective level, and active profile.
- Appender/formatter/encoder, target sink, sampling/filtering/retention.
- Which fields actually need to be queried, alerted on, or correlated.
- Consumers of text patterns: saved queries, alert rules, regexes, parsers, scripts, exported data.
- Which fields are sensitive, who is authorized to view them, and masking/exclusion policies.
- Whether any events are **mandatory audit logs**; whether audit durability needs to differ from operational logs.
- Latency and log volume at peak to estimate ingest/index impact.

**Do not start by changing `logback.xml` in production immediately.** If downstream systems are parsing old patterns, switching everything to JSON at once can leave dashboards blank even while the application is still logging normally.

### Measurable Baseline

Before cutover, record at minimum:
- Events/s by level/service.
- Parse failure rate, missing fields, events with unescaped newlines.
- Volume in bytes/s, queue depth, appender drops, collector errors.
- Active queries/alerts and their current thresholds.
- Trace/request correlation coverage.
- Rate of sensitive data in approved test samples.

Baseline data will be compared post-migration to avoid treating "the JSON looks nice" as sufficient proof of success.

## 4. Designing a Meaningful and Versioned Schema

Proposed schema for the `order-service` example:

| Field | Type | Required? | Meaning |
| --- | --- | --- | --- |
| `schemaVersion` | number/integer | Yes | Log contract version |
| `timestamp` or `@timestamp` | string ISO-8601 UTC | Yes | Event time at source; define timezone/precision |
| `level` | string enum | Yes | Operational level INFO/WARN/ERROR... |
| `service` | string | Yes | Component/service emitting the event |
| `environment` | string | Yes when multi-env | dev/staging/prod... |
| `eventType` | string enum | Yes for business events | Stable event type name, not free-form sentences |
| `message` | string | Optional | Safe human-readable summary sentence |
| `action` | string | For business actions | ORDER_CANCEL, PAYMENT_CAPTURE... |
| `outcome` | string enum | When outcome exists | SUCCEEDED/REJECTED/DENIED/FAILED... |
| `reasonCode` | string or null | When applicable | Stable reason code |
| `requestId` | string or null | When HTTP request exists | Validated tracing ID |
| `traceId`/`spanId` | string or null | When tracing exists | ID from trusted tracing context |
| `operationId` | string or null | When workflow exists | Links retries/async steps of the same action |
| `resourceType`/`resourceId` | string | When needed | Target entity; evaluate privacy impact |
| `durationMs` | number/integer | When timing | Latency of a well-defined scope |
| `error.type` | string | For technical errors | Classified exception type |
| `error.stack` | string, optional | Only when needed | Controlled diagnostic information |

**Consistency:** use the same key/type across all services for the same meaning. `durationMs` should always be a number, not `"12ms"` in one place and `12` in another. `status` is easily confused among HTTP status codes, order status, and business outcome; use specific names like `httpStatus` or `orderStatus`.

**Null or omit field?** Both are acceptable if defined by the contract. For example, an absent `reasonCode` on `SUCCEEDED` can be represented as `null` or an omitted key. However, consumers should not have to guess because service A uses an empty string, service B uses `null`, and service C omits the key.

### Event Codes and Reason Codes

`eventType` answers "what kind of event?", while `outcome` answers "what was the business result?". `reasonCode` explains the result with a stable code.

Example:
- `eventType=ORDER_CANCEL_RESULT`
- `action=ORDER_CANCEL`
- `outcome=REJECTED`
- `reasonCode=ORDER_ALREADY_SHIPPED`

Do not use `logger.error(...)` to encode outcomes: a business rejection can be logged at INFO, whereas an exception after commit might require ERROR even though the preceding business operation succeeded. **Structured logging is only useful if the semantics are right before serialization.**

### Versioning

When adding optional fields, old consumers can continue working if designed to tolerate unknown keys. When **renaming/changing the type/meaning of required fields**, you need a versioned migration, compatibility testing, and a transition period. Never silently change `durationMs` to `durationSeconds` while keeping the same name, or change the meaning of `FAILED` to `REJECTED` without notice.

## 5. Choosing Output Format: JSON Lines, Parallel Text, and Collectors

A common goal is **each event encoded as exactly one JSON object on exactly one line** (NDJSON). Example:

```json
{"schemaVersion":1,"timestamp":"2026-01-01T10:00:00Z","level":"INFO","service":"order-service","eventType":"ORDER_CANCEL_RESULT","outcome":"REJECTED"}
{"schemaVersion":1,"timestamp":"2026-01-01T10:00:01Z","level":"WARN","service":"order-service","eventType":"VALIDATION_RESULT","outcome":"REJECTED"}
```

If the `message` field contains a newline, the JSON encoder must escape it as `\n` characters on the **same JSON line**, rather than printing a raw newline that tricks the collector into thinking there are two events. Double quotes and backslashes must also be escaped.

### Formatting Rules to Lock Down

1. UTF-8 charset throughout the pipeline.
2. One event = one JSON object/line at sinks that normalize by line.
3. Timestamps with an explicit timezone (usually UTC), parseable, with consistent precision.
4. Numbers kept as JSON numbers, booleans as booleans, and null with a defined meaning.
5. Stable keys that do not collide with metadata names auto-generated by the encoder.
6. Exceptions encoded per policy: type field, reviewed message, optional stack.
7. No raw ANSI color escapes from console patterns in production JSON.
8. Include `schemaVersion` or configuration metadata sufficient for consumers to identify the contract.

### Should You Dual-Write Text and JSON?

During a transition phase, you can emit to **two appenders** or two sinks to verify consumers. Keep in mind:
- A single business event may exist in two copies; dashboards must not count it as two operations.
- The two pipelines may have different durability, filtering, and latency characteristics.
- Increases ingest volume and cost, especially when DEBUG/TRACE is high.
- There must be an end date for dual-writing and a mechanism to verify data parity.

Another option is **a single primary JSON sink** with views/queries that project a message column for human readers, avoiding log duplication. Choose based on collector capabilities and compatibility requirements.

## 6. Separation of Responsibilities: SLF4J, Logback, Encoder, and Collector

In Java, the deployment structure typically looks like this:

```text
Application code
   |
   +-- SLF4J 2.x fluent API / Logger
   |
   v
Logback backend (classic)
   |
   v
JSON encoder (e.g., logstash-logback-encoder)
   |
   v
ConsoleAppender / FileAppender / AsyncAppender
   |
   v
Container runtime / log agent
   |
   v
Collector -> storage / index -> query / alert
```

**SLF4J is a facade**; it does not directly determine the final JSON output. Logback is the backend, and the encoder is responsible for turning events into JSON. If the actual backend is Log4j2, the configuration and API differ; do not cast a Log4j2 logger to a Logback `LoggerContext`.

Ways to supply structured fields:
- SLF4J 2.x fluent `atInfo().addKeyValue(...).log(...)`.
- MDC holding scoped correlation context (only small, safe keys, with cleanup).
- Encoders supporting key–value pairs, markers, or structured arguments appropriate for the version in use.
- A custom event/publisher model serialized via a JSON library at the application/transport layer when there is a dedicated data contract.

**Common pitfall:** SLF4J has key–value pairs on the event, but the encoder only prints `message` and drops `keyValuePairs`. Only an integration test with the **exact encoder, dependencies, and production configuration** proves that the fields actually appear in the JSON output. Do not treat compiling code as sufficient.

## 7. Standalone Java 17: Producing Properly Escaped JSON Fields

Before adding frameworks, this program helps illustrate the difference between **event data** and **text formatting**. It creates two `LogEvent` instances with typed fields, then writes one JSON object per line. The second `message` field contains double quotes and a newline to demonstrate escaping.

**Important:** this is a **minimal JSON serializer for learning**, not a recommendation to write your own production JSON encoder. In real projects, use Jackson/Gson or a tested, security-maintained JSON encoder from your logging backend.

### 7.1. File `StructuredLogMigrationDemo.java`

```java
import java.time.Instant;

public class StructuredLogMigrationDemo {
    record LogEvent(
            Instant timestamp,
            String level,
            String service,
            String eventType,
            String action,
            String outcome,
            String reasonCode,
            String requestId,
            String operationId,
            String message,
            long durationMs
    ) {}

    // JSON escaping for String. One record per line.
    private static String quote(String value) {
        if (value == null) {
            return "null";
        }

        StringBuilder output = new StringBuilder();
        output.append('"');

        for (int i = 0; i < value.length(); i++) {
            char c = value.charAt(i);

            switch (c) {
                case '"' -> output.append("\\\"");
                case '\\' -> output.append("\\\\");
                case '\n' -> output.append("\\n");
                case '\r' -> output.append("\\r");
                case '\t' -> output.append("\\t");
                case '\b' -> output.append("\\b");
                case '\f' -> output.append("\\f");
                default -> {
                    if (c < 0x20) {
                        output.append('\\').append('u');
                        String hex = Integer.toHexString(c);
                        for (int n = hex.length(); n < 4; n++) {
                            output.append('0');
                        }
                        output.append(hex);
                    } else {
                        output.append(c);
                    }
                }
            }
        }

        return output.append('"').toString();
    }

    static String toJson(LogEvent e) {
        return "{\"schemaVersion\":1"
                + ",\"timestamp\":" + quote(e.timestamp().toString())
                + ",\"level\":" + quote(e.level())
                + ",\"service\":" + quote(e.service())
                + ",\"eventType\":" + quote(e.eventType())
                + ",\"action\":" + quote(e.action())
                + ",\"outcome\":" + quote(e.outcome())
                + ",\"reasonCode\":" + quote(e.reasonCode())
                + ",\"requestId\":" + quote(e.requestId())
                + ",\"operationId\":" + quote(e.operationId())
                + ",\"message\":" + quote(e.message())
                + ",\"durationMs\":" + e.durationMs()
                + "}";
    }

    public static void main(String[] args) {
        Instant base = Instant.parse("2026-01-01T10:00:00Z");

        LogEvent rejected = new LogEvent(
                base, "INFO", "order-service",
                "ORDER_CANCEL_RESULT", "ORDER_CANCEL",
                "REJECTED", "ORDER_ALREADY_SHIPPED",
                "req-17", "op-7", "Cancel rejected", 12
        );

        LogEvent invalid = new LogEvent(
                base.plusSeconds(1), "WARN", "order-service",
                "VALIDATION_RESULT", "ORDER_CREATE",
                "REJECTED", "INVALID_COMMENT",
                "req-18", "op-8",
                "Input: \"test\"\nnext", 3
        );

        System.out.println(toJson(rejected));
        System.out.println(toJson(invalid));
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac StructuredLogMigrationDemo.java
java StructuredLogMigrationDemo
```

**Exact stdout (two JSON lines, with the newline in the message escaped):**

```json
{"schemaVersion":1,"timestamp":"2026-01-01T10:00:00Z","level":"INFO","service":"order-service","eventType":"ORDER_CANCEL_RESULT","action":"ORDER_CANCEL","outcome":"REJECTED","reasonCode":"ORDER_ALREADY_SHIPPED","requestId":"req-17","operationId":"op-7","message":"Cancel rejected","durationMs":12}
{"schemaVersion":1,"timestamp":"2026-01-01T10:00:01Z","level":"WARN","service":"order-service","eventType":"VALIDATION_RESULT","action":"ORDER_CREATE","outcome":"REJECTED","reasonCode":"INVALID_COMMENT","requestId":"req-18","operationId":"op-8","message":"Input: \"test\"\nnext","durationMs":3}
```

### 7.2. Detailed Explanation

- `LogEvent` is a Java record holding **meaningful data**, rather than a hard-to-parse message sentence.
- `durationMs` is written as a JSON number, not the string `"12ms"`.
- `quote` escapes double quotes, backslashes, newlines, carriage returns, tabs, backspaces, form feeds, and control characters U+0000–U+001F. Thus, the second record remains on **a single stdout line**.
- The `message` field serves human readers. The stable `reasonCode` field enables grouping/alerting without parsing the message.
- Both events have fixed timestamps so the output is reproducible; in production, you need a reliable clock, timestamp format, and trace context per the contract.
- `toJson` does not imply that the log is durable. `System.out.println` only writes to stdout; the agent/collector/index is the next step.
- `record` holds shallowly immutable field references, but does not automatically turn it into an audit event with ACID/retention guarantees.

**Important technical limitations:** this example lacks schema validation, size limits, invalid Unicode normalization, nested structures, special numbers, redaction, streaming/backpressure, or error recovery. Do not use this hand-rolled `quote` method as a production serializer, especially with untrusted input or complex types. Use a mature JSON library and test the output against your requirements.

## 8. Maven Project Using SLF4J 2 and Logback JSON Encoder

A practical setup uses:
- Java 17;
- SLF4J 2.x API;
- Compatible Logback Classic 1.5.x;
- `logstash-logback-encoder` version compatible with the Logback/Java versions in use;
- ConsoleAppender emitting one JSON line per event, with the platform agent collecting stdout.

Below is **a standalone reference project**. The pinned versions provide a deterministic example environment and **are not claimed to be the latest or security-appropriate for all times**. In production, select/verify versions according to dependency management, CVEs, and your actual platform.

### 8.1. Directory Structure

```text
structured-log-lab/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── example/
        │       └── StructuredLoggingApp.java
        └── resources/
            └── logback.xml
```

### 8.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>example</groupId>
    <artifactId>structured-log-lab</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.slf4j</groupId>
            <artifactId>slf4j-api</artifactId>
            <version>2.0.16</version>
        </dependency>

        <dependency>
            <groupId>ch.qos.logback</groupId>
            <artifactId>logback-classic</artifactId>
            <version>1.5.16</version>
        </dependency>

        <dependency>
            <groupId>net.logstash.logback</groupId>
            <artifactId>logstash-logback-encoder</artifactId>
            <version>8.0</version>
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
                <version>3.4.1</version>
            </plugin>
        </plugins>
    </build>
</project>
```

**Note:** do not pull in another SLF4J binding/provider at runtime simultaneously, such as an unnecessary Log4j2 binding. A real Spring Boot application usually already manages Logback versions and configuration; avoid adding duplicate or mismatched dependencies. Check `mvn dependency:tree` in real projects to see which provider/encoder is active.

### 8.3. `src/main/resources/logback.xml`

```xml
<configuration>
    <appender name="JSON_CONSOLE"
              class="ch.qos.logback.core.ConsoleAppender">
        <encoder class="net.logstash.logback.encoder.LogstashEncoder"/>
    </appender>

    <logger name="example" level="INFO"/>

    <root level="WARN">
        <appender-ref ref="JSON_CONSOLE"/>
    </root>
</configuration>
```

This configuration defines a JSON stdout encoder. It **does not automatically add `schemaVersion`, `service`, or `environment` fields** unless you configure encoder providers/customFields or your code emits them. Default names like `@timestamp`, `logger_name`, and `thread_name` depend on the encoder/version; **do not assume field names based on the JDK demo table**. To unify schemas across services, you need a reviewed and tested configuration.

### 8.4. `src/main/java/example/StructuredLoggingApp.java`

```java
package example;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;

public class StructuredLoggingApp {
    private static final Logger LOG =
            LoggerFactory.getLogger(StructuredLoggingApp.class);

    public static void main(String[] args) {
        MDC.put("requestId", "req-17");

        try {
            LOG.atInfo()
                .addKeyValue("schemaVersion", 1)
                .addKeyValue("service", "order-service")
                .addKeyValue("environment", "demo")
                .addKeyValue("eventType", "ORDER_CANCEL_RESULT")
                .addKeyValue("action", "ORDER_CANCEL")
                .addKeyValue("operationId", "op-7")
                .addKeyValue("outcome", "REJECTED")
                .addKeyValue(
                        "reasonCode", "ORDER_ALREADY_SHIPPED")
                .addKeyValue("durationMs", 12)
                .log("Cancellation rejected");
        } finally {
            MDC.clear();
        }
    }
}
```

### 8.5. Running and Verifying

Inside the `structured-log-lab` directory:

```bash
mvn -q compile exec:java -Dexec.mainClass=example.StructuredLoggingApp
```

The application will emit one INFO event through the Logback configuration above. **Do not snapshot verbatim stdout** from the logstash encoder because runtime timestamps, logger names, threads, and providers may vary. Proper acceptance criteria are: each application line is valid JSON; it contains `eventType`, `outcome`, `reasonCode`, `operationId`, and `durationMs` with the appropriate types/values, plus `requestId` when MDC is supported/configured in the encoder.

If any field is missing, **do not silently conclude the migration succeeded**: check the encoder/providers for `keyValuePairs`, `mdc`, and backend version. With a composite encoder configuration, the corresponding providers must be declared; some encoders handle messages or structured arguments in specific ways. Testing against actual output is the source of truth.

### Why Keep `message`?

Structured events do not forbid descriptive sentences. `message` should be short, safe, aimed at human readers, and **must not** be parsed to infer `outcome` or `reasonCode`. If the message changes from "Cancellation rejected" to "Cancel not allowed", business metrics relying on `reasonCode` must remain unaffected.

## 9. From Existing Application to Fluent Structured Logging

Migrate a log call site following these steps:

### Before: Concatenated Text with Multiple Pieces of Information

```java
logger.warn(
    "Cannot cancel " + orderId
        + " because status " + status
        + ", request " + requestId);
```

### After: Business Outcome Separated from Logging

```java
CancelResult result = orderService.cancel(command);

// LOG only reflects the result already obtained.
logger.atInfo()
    .addKeyValue("eventType", "ORDER_CANCEL_RESULT")
    .addKeyValue("action", "ORDER_CANCEL")
    .addKeyValue("resourceId", safeOrderId)
    .addKeyValue("outcome", result.outcome())
    .addKeyValue("reasonCode", result.reasonCode())
    .log("Cancel operation finished");
```

This is a **project-dependent snippet** using `CancelResult`, `orderService`, and `safeOrderId`, not a standalone Java class. If processing involves a transaction, do not emit `SUCCEEDED` before commit; if the commit status is uncertain, use `UNKNOWN`/reconciliation instead of guessing.

### When Do You Not Need to Migrate Every Log?

- Low-importance internal debug logs can remain text messages if there is no requirement to query their fields.
- Technical stack traces remain valuable; they can be recorded in a controlled exception field.
- Legacy applications with pattern-dependent parsers need a compatibility phase.
- For audit events that already have a standardized repository, you do not necessarily need to push every event into the operational logger; keep the audit source of truth separate.

**Do not turn every word in a text sentence into a new field.** Choose fields that are meaningful to query, manageable in volume, safe in sensitivity, and backed by a stable contract.

## 10. Correlation IDs and MDC: Proper Scope, No Cross-Thread Leaks

In distributed systems, `requestId`, `traceId`, `spanId`, and `operationId` help link events across services. SLF4J's MDC is a common mechanism to hold context **bound to the current thread**, though it does not automatically create a complete distributed trace.

Example in a handler:

```java
// Snippet in an SLF4J application.
Map<String, String> before = MDC.getCopyOfContextMap();

try {
    MDC.put("requestId", validatedRequestId);
    MDC.put("operationId", trustedOperationId);
    handleRequest();
} finally {
    if (before == null) {
        MDC.clear();
    } else {
        MDC.setContextMap(before);
    }
}
```

You need to import `java.util.Map` and `org.slf4j.MDC` and have the actual variables/methods in your application. The `finally` block prevents request B from inheriting request A's `requestId` when a thread pool reuses threads.

### Do Not Assume MDC Propagates Across All Async Boundaries

`CompletableFuture`, `ExecutorService`, thread pools, and reactive frameworks have different context mechanisms. If processing continues on another thread, capture/restore context using the framework's supported API or use dedicated instrumentation/tracing. Never assume MDC automatically carries over to child threads.

### Client-Supplied Correlation Fields Must Be Validated

Do not copy a raw `X-Request-ID` with unbounded length or newlines into MDC. Prefer server-generated IDs or validate against format/length rules. Never use bearer tokens, session cookies, or emails as `traceId` just for query convenience. For W3C Trace Context, use instrumentation/libraries that support valid headers/states rather than hand-rolled simple regexes.

### Request ID vs. Operation ID

An async operation may span multiple HTTP requests and retries; `operationId` can persist across attempts while `requestId` changes. `eventId` is the ID of a single event, not automatically equal to `messageId`/`operationId`. Name fields clearly so consumers do not miscount execution attempts.

## 11. Exceptions and Stack Traces in Structured Events

An error log should not just be:

```json
{"level":"ERROR","message":"Something failed"}
```

if operations teams need to know the error type, downstream dependency, and correlation. However, you should also avoid copying raw exception messages containing URLs, SQL, tokens, or payloads without review.

A viable contract:

```json
{
  "eventType": "DEPENDENCY_CALL_RESULT",
  "level": "ERROR",
  "outcome": "FAILED",
  "reasonCode": "DEPENDENCY_TIMEOUT",
  "dependency": "payment-gateway",
  "requestId": "req-91",
  "error": {
    "type": "SocketTimeoutException",
    "message": "Dependency call timed out"
  }
}
```

This is an illustrative schema sample; actual output depends on the encoder. Some Logback encoders place the stack trace in a top-level string field rather than automatically creating a nested `error` object as shown.

### Logging Pattern in SLF4J

```java
// Snippet in an application with an exception and variables.
logger.atError()
    .addKeyValue("eventType", "DEPENDENCY_CALL_RESULT")
    .addKeyValue("outcome", "FAILED")
    .addKeyValue("reasonCode", "DEPENDENCY_TIMEOUT")
    .addKeyValue("dependency", "payment-gateway")
    .setCause(exception)
    .log("Dependency request failed");
```

SLF4J 2.x fluent `setCause(Throwable)` attaches the exception to the event. The encoder must be checked to see how exception fields and stack traces are rendered. Do not serialize `exception.toString()` as a substitute field if you need the cause chain; it may drop important details or leak data.

### Log an Error at the Appropriate Boundary

If the repository, service, and controller all log the same `Throwable`, a single error can appear three times on dashboards and inflate alerts. Choose the responsible boundary; other layers can propagate the exception/cause without duplicate logging. Expected business rejections usually do not need a full stack trace at INFO, though security audits may require a dedicated event.

## 12. Security When Migrating to JSON: Avoid Making Data Leaks Easily Queryable

Structured logging makes searching easier; consequently, if a log leaks a secret, **the secret also becomes easier to find and bulk-export**. Migration must be accompanied by a data policy.

### Allowlist Instead of Dumping Objects

Avoid:

```java
logger.atDebug()
    .addKeyValue("request", requestDto)
    .log("Payment request");
```

`requestDto.toString()` or an encoder serializer may contain full names, addresses, tokens, card numbers, or emails. Prefer an allowlist:

```java
logger.atDebug()
    .addKeyValue("paymentMethodRef", safeMethodRef)
    .addKeyValue("amountMinorUnits", amountMinorUnits)
    .addKeyValue("currency", currencyCode)
    .addKeyValue("requestId", validatedRequestId)
    .log("Payment request received");
```

This code is a snippet, not standalone. For monetary values, distinguish numeric types/units; avoid accidentally serializing money as imprecise floating-point numbers.

### Data Not to Log

- Passwords, OTPs, API keys, access/refresh tokens, session cookies, Authorization headers.
- Private keys, secret configs, credentials in URLs/DB connection strings.
- Raw request/response bodies that may contain PII or payment data.
- Full stack traces/exception messages without reviewing content and access permissions.
- Arbitrary client-supplied data placed into structured fields without size/encoding limits.
- Sensitive IDs in high-cardinality metric labels.

### Log Injection and JSON Escaping

Input containing `\r`/`\n`, quotes, or backslashes must be properly encoded. A JSON encoder escapes strings, but **does not automatically solve** sensitive data, spoofed IDs, duplicate keys, control characters in key names, or unauthorized sink access.

If the `message` field contains an escaped `\n` sequence, downstream systems parse one JSON record instead of multiple lines. **Integration tests on the final output** are needed to ensure the agent/collector does not split records incorrectly.

### Permissions and Retention

JSON events may contain actor/resource identifiers; view/index/export permissions must be managed, with retention policies by data type and environment. For legally mandated audits, structured JSON does not replace integrity, access audit, and durability controls.

## 13. Phased Migration: From Baseline to Cutover

A practical project should be divided into phases with verifiable outcomes.

### Phase A — Inventory and Contract

- List of critical events and consumers of legacy logs.
- Schema version, required/optional fields, field types, and naming conventions.
- Rules for exceptions, MDC, correlation, PII, and retention.
- Choose an encoder and verify dependency compatibility with Java/backend.
- List of alerts/queries/regexes that will need updating.
- Baseline volume, parse rate, and delivery latency.

### Phase B — PoC on One Service or Endpoint

Pick a small service and a clear business `eventType`, such as `ORDER_CANCEL_RESULT`.

- Emit `action`, `outcome`, `reasonCode`, `operationId` with accurate semantics.
- Run unit/integration tests and parse the NDJSON output.
- Verify events reach the collector and can be queried by key/type.
- Compare operation counts from the business source against unique event counts at the sink when an event ID exists.
- Test exceptions, Unicode, newlines, nulls, and fake tokens.

### Phase C — Time-Boxed Parallel/Compatibility Mode

If legacy consumers must be maintained, keep text and JSON during a transition period or have the collector transform JSON into a text view. Count by unique event ID to avoid double-counting on dashboards. Document the sunset date for text parsers, the scope of dual-writing, and the rollback owner.

### Phase D — Incremental Rollout

- Staging with test data → canary on one pod/instance → partial traffic → full service → multiple services.
- Verify logger profiles and appender paths in the target environments.
- Monitor ingest volume, parse errors, latency, queue drops, schema field coverage, and alert health.
- If the collector does not support the intended structure, roll back the encoder or adjust the pipeline within approved boundaries.

### Phase E — Cutover and Dependency Cleanup

- Switch dashboards, saved searches, and alert rules to structured fields.
- Review sampling/filtering so critical events are not dropped.
- Disable dual-write after the verification window.
- Remove legacy text regexes/parsers once all consumers have migrated.
- Document schema, ownership, release version, and runbooks.

**Conditions blocking cutover:** missing required fields, high parse error rates, data leaks, incorrect event counts, missed critical SLOs, or no rollback mechanism.

## 14. Testing: Schema/Fields/Types Instead of Locking Full JSON Lines

A brittle test:

```java
assertEquals(
    "{\"level\":\"INFO\",\"outcome\":\"REJECTED\"}",
    actualLine);
```

Key order, timestamps, and additional fields can change while the event remains valid. For JSON schemas, **parse and assert the structure**.

Example with Jackson + JUnit 5 in a project with the corresponding dependencies:

```java
// Test snippet, requires ObjectMapper, JsonNode,
// outputJson, and JUnit Jupiter to be declared/imported.
JsonNode event = new ObjectMapper().readTree(outputJson);

assertEquals("ORDER_CANCEL_RESULT",
             event.path("eventType").asText());
assertEquals("REJECTED",
             event.path("outcome").asText());
assertEquals("ORDER_ALREADY_SHIPPED",
             event.path("reasonCode").asText());
assertTrue(event.path("durationMs").isIntegralNumber());
assertEquals(12L, event.path("durationMs").asLong());
assertTrue(event.path("timestamp").isTextual());
```

**Do not stop at `path(...).asText()`**, because when a field is missing, Jackson may return a default that causes the test to pass falsely in some cases. Add `hasNonNull`, `isTextual`, schema validation, and enum value checks; the snippet above illustrates the approach rather than a complete schema validator.

### Recommended Test Matrix

| Case | Data | Expectation |
| --- | --- | --- |
| Normal success | `outcome=SUCCEEDED` | Valid JSON, correct fields/types |
| Business rejection | `REJECTED/ORDER_ALREADY_SHIPPED` | Reason not parsed from message text |
| Technical failure | Throwable `SocketTimeoutException` | Exception type/cause preserved per policy |
| Null/optional field | Missing requestId | Correct null/omission contract |
| Number vs string | `durationMs=12` | JSON number, not `"12ms"` |
| Unicode | Vietnamese message | Accurate parse round-trip |
| Quotes/backslash | `"x"` or `\` | Proper JSON escaping |
| CR/LF | Input containing newline | Single JSON object/event, no log injection |
| Fake token | `FAKE_TOKEN_TEST_73` in raw payload | Not leaked to sink if prohibited by policy |
| MDC context | Two requests on a thread pool | Correct request ID, no context leakage |
| Logger level/filter | INFO disabled, ERROR enabled | No impact on business outcome |
| Async appender | Delayed event arrival | Wait for sink with timeout/latch; no flaky sleep |
| Dual-write | Same operation to two sinks | Dashboards do not double-count |
| Downstream parser | JSON field consumer | Queries/alerts still receive correct data |
| Rollback | Revert to old encoder | No change to business processing |

### Testing One Record Per Line

For example, with the output of `StructuredLogMigrationDemo` in section 7, you can use a JSON parser (Jackson in Java or an existing parser tool) to parse each line. Expect exactly **two JSON objects**, with the second `message` containing a newline *after decoding* while the stdout line remains **a single JSON line**.

Do not conclude "valid JSON" via `line.startsWith("{")` and `line.endsWith("}")`: the middle string may have invalid escaping or types.

## 15. Testing Logging with JUL/Logback Without Brittle Tests

In domain unit tests, verify business behavior separately first. In logging tests, capture the **pre-encoder event** when checking level/template/key–value/MDC/Throwable; in encoder tests, parse the JSON output; in delivery tests, verify the actual sink.

With Logback:
- Attach an in-memory `AppenderBase<ILoggingEvent>` and assert `getLevel()`, `getMessage()`, `getMDCPropertyMap()`, `getKeyValuePairs()` if supported by the backend/version.
- Use a dedicated/isolated logger with `additive=false` to avoid noise from the root appender.
- Detach/stop the appender and restore MDC in `finally`.
- If events are processed asynchronously, call `prepareForDeferredProcessing()` at the appropriate boundary to snapshot lazy data like MDC when needed; avoid reading cleared context from another thread.
- Test meaningful message templates/structured fields; do not assert exact timestamps, thread names, and every stack frame.

For `java.util.logging`:
- A `Handler` collects `LogRecord`s; check `Level`, `getMessage()`, `getParameters()`, `getThrown()`.
- `LogRecord`/JUL formatters are not identical to Logback events; do not cast across incompatible APIs.
- A program using a JUL-to-SLF4J bridge may require separate bridge/handler testing.

If a test only does `verify(logger).info(...)`, it does not prove the encoder emits the right fields, the sink receives the log, or data is redacted. **Each layer should have its own test oracle.**

## 16. Performance and Volume: JSON Is Not Automatically "Lighter" Than Text

Migration can make JSON events **longer** due to repeated key names, metadata, MDC, and exceptions. On the other hand, JSON avoids complex regex parsing at the collector and improves query quality. Never assume it is always faster or slower: measure it.

Metrics to monitor:

| Metric | Issue to Detect |
| --- | --- |
| Events/s by service/level | Volume change post-migration |
| Bytes/event, bytes/s | Encoding, network, storage/index cost |
| CPU/allocations/GC | Serializer, caller data, stack trace overhead |
| Request p95/p99 | Blocking from sync appender or full queue |
| Async queue depth/dropped events | Backpressure or event loss |
| Collector 429/5xx/retry | Transport/ingest overload |
| Parse error ratio | Malformed/unsupported events |
| Required-field coverage | Missing keys or unexpected nulls |
| Query latency | Whether field/index design is appropriate |
| Log cost/retention | Storage budget and compliance |

### AsyncAppender Does Not Make Events Durable

Logback's `AsyncAppender` uses an in-memory queue. `queueSize`, `discardingThreshold`, `neverBlock`, and `maxFlushTime` affect dropping, blocking, and shutdown; they **do not guarantee that events are durably persisted at the collector**. When the queue is full, depending on configuration, events may be discarded or application threads may block.

JSON encoders may run on the appender thread; adding too many fields or serializing large objects slows down the worker and backs up the queue. Include only necessary fields, cap value sizes, and avoid serializing entire DTOs or huge stack traces for routine business rejections.

### Logger Levels Can Reduce Work but Not Guarantee All of It

With `logger.debug("payload {}", expensiveOperation())`, Java still evaluates the arguments before calling the logger; if `expensiveOperation()` has side effects or high cost, disabling DEBUG **does not prevent** that computation. Use guards/lazy APIs for pure diagnostics, never for business logic.

## 17. Monitoring Structured Logging Quality Post-Deployment

You can track:

- `log_json_parse_errors_total` — count of unparseable records.
- `log_required_field_missing_total{field}` — missing required fields; `field` label from a bounded set.
- `log_schema_version_total{version}` — distribution of schema versions.
- `log_pipeline_dropped_total{stage}` — events dropped at observable stages.
- `log_collector_ingest_errors_total` — collector errors.
- `log_event_delivery_latency_seconds` — latency from source to defined target milestone.
- `log_canary_delivery_total{result}` — canary success/failure from app to sink.
- `log_structured_event_count{eventType,outcome}` — business distribution, if aligned with source and sampling policy.

These are **illustrative metric names**, not built into SLF4J/Logback. Do not put `requestId`, `orderId`, `userId`, or message text into metric labels due to high cardinality and data exposure risks.

A dashboard should distinguish:
1. **Source event count** (if a trusted source exists, e.g., an audit outbox).
2. **Delivered/ingested unique event count**.
3. **Parseable/queryable event count**.
4. **Missing/late/duplicate** after reconciliation by event ID/cohort.

Merely dividing "JSONs parsed OK / JSONs reaching collector" cannot detect events dropped before the collector. For critical events, use source IDs, reconcilers, or end-to-end canaries; never claim a log pipeline is 100% reliable just because parse errors are zero.

### Example Alerting Thresholds

- Parse failure rate increases after rollout.
- `reasonCode`/`outcome` disappears from queries even though console logs continue.
- Ingest rate/volume exceeds budget.
- Canary deliveries to sink drop or are delayed.
- Excessive exception events due to duplicate logging across layers.
- Sensitive data appears in the sink in approved synthetic leak tests.
- MDC leaks `requestId` between two tasks.

Specific thresholds should match traffic, SLOs, and the priority of each log category, rather than an arbitrary universal number.

## 18. Troubleshooting When JSON Does Not Appear as Expected

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Still plain text on console | `logback.xml` not loaded, different backend, wrong appender | Verify provider, active config, root appender |
| JSON parse error | Formatter adds text/ANSI or raw newlines | Inspect line by line, JSON encoder, and upstream driver |
| `addKeyValue` produces no fields | Encoder/provider does not emit key–value pairs | Use proper provider, test version/config |
| `requestId` missing | MDC not set, cleared early, or not propagated | Check context on the emitting thread |
| `durationMs` field is a string | Code/encoder serializes differently from schema | Keep numeric field, add schema tests |
| Duplicate or overwritten keys | MDC/customFields collide with reserved keys | Rename, enforce namespace policy, test conflicts |
| Valid JSON but empty dashboard | Old parser/index mapping/query uses regex | Update mappings/queries, check each pipeline stage |
| Sharp log volume spike | Added fields, duplicate appender, or TRACE enabled | Check additivity/filters, keep only needed fields |
| Exception missing stack trace | Encoder/proxy/filter excludes throwable | Test `Throwable` on events and output per policy |
| Stack trace contains secret | Raw exception payload/header copied | Redaction/allowlist, trigger data-leak incident response |
| Random log loss | Async queue drops, agent rate-limiting, collector errors | Drop/backpressure metrics, delivery design |
| Events appear twice | Dual-write, additivity, transport retries | Distinguish copies and event IDs |
| Event ordering changes | Async/multi-threading/batching | Use IDs and causal boundaries, not display order |
| Logback config applied to one pod | Config drift, pod restart, or partial deployment | Verify service/version/instance |
| Parser rollback fails to recover | Text consumers turned off too early | Maintain a tested compatibility plan |

### Do Not Fix Issues by Turning On Root TRACE Immediately

If JSON is missing a field, the problem is likely in the **encoder/provider**, not the logger level. Enabling TRACE only inflates volume and risks leaking data. Use small test events, schemas, and boundary-by-boundary pipeline checks instead.

## 19. Safe Rollback and Preserving Observability

A migration may need to be rolled back when:
- JSON breaks critical parsers/alerts.
- Required event counts/fields are missing or have wrong types.
- The encoder causes latency/CPU spikes or queue drops.
- Events contain sensitive information due to new code/config.
- Part of the cluster emits JSON while another emits text that the collector cannot classify.

Rollback plan includes:

1. Keep old encoder configurations versioned with controlled deploy/flag mechanisms.
2. Prepare parsers/ingest to support both formats during the transition when necessary.
3. Do not delete old mappings/indexes before verifying consumers.
4. Roll back the encoder or route within a bounded scope; do not alter business logic just to fix logs.
5. Verify critical alerts, source-to-sink events, and secret policies after rollback.
6. Document which events emit text and which emit JSON during the transition window.
7. Disable dual-write once metrics and behavior stabilize to avoid prolonged costs.

**Rolling back the format does not necessarily roll back the business schema.** If consumers already rely on the new event version, maintain an appropriate adapter; never silently change the meaning of `outcome` or `reasonCode`.

### Should You Roll Back Immediately on One Bad JSON Line?

Evaluate the impact, error severity, and defined stop conditions. A single escaping bug in a low-priority flow differs from all audit logs being dropped. If there is a risk of secret leakage, the safe response usually prioritizes stopping the emission of sensitive data and initiating incident response, rather than waiting for a volume threshold.

## 20. Ensuring Structured Logs Do Not Alter Control Flow

A successful migration must never accidentally turn logging into a decision-making mechanism. Anti-patterns to avoid:

```java
// WRONG: logging the result instead of returning/enforcing it.
if (!authorized) {
    logger.atWarn()
        .addKeyValue("outcome", "DENIED")
        .log("Access denied");
}
return secretData;
```

Even schema-compliant structured JSON **does not replace authorization enforcement**. You must `return`/`throw` or block at the policy layer.

Similarly:
- `outcome=SUCCEEDED` before transaction commit is unreliable.
- Logging `PROCESSING_COMPLETED` does not replace broker ACK/offset commit.
- Logging `RETRY_SCHEDULED` does not actually schedule a retry job.
- Logging `AUDIT_EVENT` on best-effort async does not guarantee durable evidence.
- Disabling DEBUG must not change the effect of a command.

**The business source of truth** must be maintained via transactions, results, state stores, domain events, and delivery contracts. Logging only observes.

## 21. Advanced Exercises and Acceptance Criteria

### Exercise A — Field Semantics

Pick three existing text events (success, rejection, technical failure). Convert them to JSON with `eventType`, `outcome`, `reasonCode`, and IDs. Explain why a business `REJECTED` does not necessarily have to be ERROR.

**Pass:** dashboard groups by `reasonCode` without regexes on `message`.

### Exercise B — Unicode, Newlines, and Log Injection

Provide messages containing:
- Vietnamese characters with diacritics;
- double quotes and backslashes;
- newline characters;
- IDs with control characters that are rejected or escaped.

**Pass:** each event is a single parseable JSON record, creating no forged records and leaving the schema intact.

### Exercise C — MDC and Concurrency

Run two requests on a thread pool, each with a different ID. Collect events from the sink.

**Pass:** event A does not carry requestId B, and event B does not carry requestId A; context is restored/cleared after each task, even when an exception occurs.

### Exercise D — Exceptions and Redaction

Create a fake exception whose message contains `FAKE_TOKEN_TEST_73` and a clear error type. Configure a policy that prevents sending raw secrets to the sink.

**Pass:** logs still include useful `reasonCode`/`error.type` fields without leaking the fake token to any protected sink.

### Exercise E — Delivery and Rollback

Stop the collector in a test environment and emit a critical event with an ID. Restore the collector and inspect the retry/backpressure/spool policy. Test rolling back the encoder to text in a canary.

**Pass:** accurate counts of lost/late/duplicate events, without claiming higher guarantees than verified; rollback does not corrupt business state.

### Exercise F — Query Compatibility Check

Migrate a saved search/alert from `message contains "already shipped"` to `eventType=ORDER_CANCEL_RESULT` + `reasonCode=ORDER_ALREADY_SHIPPED`.

**Pass:** changing the `message` wording keeps the alert/query working. Also include schema/version tests to prevent silent field renames.

## 22. Summary of Common Mistakes and How to Avoid Them

| Mistake | Impact | Prevention |
| --- | --- | --- |
| Assuming `logger.info("x={}", x)` creates a structured field | Downstream only sees text | Use key–value events + supporting encoder, verify at sink |
| Changing formatter without reviewing parsers | Dashboards/alerts suddenly go blank | Inventory consumers and run canary rollouts |
| Using `message` as primary query source | Wording refactors break searches | Contracted `eventType`/`reasonCode` |
| Inconsistent field types | Index mapping conflicts | Schema tests, versioning |
| Serializing whole DTOs/exceptions | Token/PII leaks, volume spikes | Field allowlists and redaction |
| Failing to escape newlines/control chars | Broken event splitting, log injection | JSON encoder, Unicode/CRLF tests |
| Not cleaning up MDC | `requestId` leaks across threads | `finally` cleanup / context propagation tests |
| Counting dual-write as two operations | Inflated dashboard metrics | Unique event IDs / deduplication |
| Keeping both text and JSON indefinitely | Higher cost and operational complexity | Cutover date and deprecation plan |
| Treating JSON output as durable | Audits lost on appender/collector failure | Outbox/ack/retention per contract |
| Enabling DEBUG/TRACE to test fields | Higher load and data exposure risk | Synthetic events and encoder integration tests |
| Snapshotting raw JSON strings only | Breaks on key order or timestamp changes | Parse and assert fields/types/schema |
| Not testing collector outages | Silent drops go undetected | Fault injection and source-to-sink checks |
| No rollback plan | Prolonged incidents on encoder failures | Versioned config, staged rollout |
| Unbounded cardinality/value sizes | Index/cost explosion | Schema allowlists, size limits, metric label policies |

## 23. Pre-Merge and Deployment Checklist

- [ ] Inventoried loggers, appenders, collectors, parsers, and alerts depending on text logs.
- [ ] Versioned schema with consistent field names and types.
- [ ] Clear definitions for `eventType`, `action`, `outcome`, `reasonCode`, and correlation IDs.
- [ ] No parsing of `message` text to infer business outcomes post-migration.
- [ ] Runtime has only one appropriate SLF4J backend/provider.
- [ ] Actual encoder emits `keyValuePairs` and MDC as required, not just `message`.
- [ ] One event / one JSON line at the sink; accurate Unicode/CRLF/quote escaping.
- [ ] Numeric/boolean/null types preserved, not mixed with strings.
- [ ] Tests cover JSON parsing, required schema fields, exceptions, and field types.
- [ ] Tests verify no fake secrets leak to any protected sink.
- [ ] MDC is validated, properly propagated across async contexts, and cleaned up.
- [ ] Business outcomes/transactions/ACKs do not depend on logging.
- [ ] Evaluated volume/latency, queue drops, ingest quotas, and retention.
- [ ] Canaries, parse error metrics, field coverage, and source-to-sink checks in place.
- [ ] Phased rollout, dual-write end date, and rollback plan documented.
- [ ] New dashboard/search/alert consumers tested before cutover.
- [ ] Critical audits have separate reliability/retention/access controls.
- [ ] Schema/encoder/config reviewed with long-term ownership assigned.

**Conclusion:** migrating from text logs to structured logs is **a data and operational contract change**, not just swapping a console pattern for JSON. Start with event semantics, field types, and consumers; use SLF4J/backends/encoders within their actual capabilities, test JSON at the sink, protect sensitive data, roll out in phases, and preserve rollback capability. Your new logs will then be both human-readable and machine-queryable without altering control flow or equating "logged" with "durably stored."
