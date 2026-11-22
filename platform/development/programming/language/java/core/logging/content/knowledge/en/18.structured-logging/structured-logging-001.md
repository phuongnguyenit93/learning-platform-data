# What Is Structured Logging? How to Write Structured Logs in Java

## 1. Concept

**Structured logging** is a way of representing each log event as **fields with clear names, types, and meanings** instead of just writing a free-form text string. A good log typically includes timestamp, level, service, logger, event_code, message, request_id or trace_id, along with useful business data that is permitted to be stored.

Example of a text log:

~~~text
2026-11-09 12:34:56 INFO Checkout created order ORD-42, amount 12500 VND, request req-42
~~~

The same event in structured form:

~~~json
{
  "timestamp": "2026-11-09T12:34:56.789Z",
  "level": "INFO",
  "service": "checkout",
  "logger_name": "com.example.orders.OrderService",
  "event_code": "ORDER_CREATED",
  "message": "Order created",
  "request_id": "req-42",
  "order_id": "ORD-42",
  "amount_minor": 12500,
  "currency": "VND",
  "outcome": "success"
}
~~~

The collection system can search by **event_code = ORDER_CREATED**, filter by currency, or sum amount_minor without needing to parse an English sentence whose word order may vary.

**Structured logging is not just putting JSON curly braces around a message.** Its core value lies in the **schema**, stable field names, meaningful data types, how correlation context is propagated, and the ability to preserve fields throughout the pipeline from the application to the collector.

JSON is a popular format, but structured logs can also use **logfmt/key-value** or another event format. The application should still keep a **short, human-readable message**, while fields and event codes serve machine analysis.

## 2. Why Is Structured Logging Useful?

### Attribute-Based Search

Free-form logs can be written in many ways:

~~~text
Payment retry attempt 2 for ORD-42: gateway timeout
Retry #2 after timeout, order=ORD-43
Gateway error on second request for ORD-44
~~~

With plain text, you need regex or full-text search, and it is easy to miss events. With a unified schema, the events can all look like:

~~~json
{
  "event_code": "PAYMENT_RETRY",
  "operation": "authorize",
  "attempt": 2,
  "reason_code": "GATEWAY_TIMEOUT",
  "outcome": "retrying"
}
~~~

Querying by **event_code** and **attempt** does not depend on the message wording.

### Correlating Across Multiple Services

A request flowing through Gateway → Order Service → Payment Service can emit many logs. If the events share a valid request_id/trace_id, operators can group them together and see which steps occurred.

### Statistics and Alerting

Fields with number/boolean types make grouping and conditional filtering easy. Stable event codes keep dashboards from breaking when messages change. However, **structured logs do not automatically guarantee no lost events**; if there is sampling, queue drops, or collector errors, counting log records is not always the exact request count. Metrics are still necessary.

### Faster Investigation

An error event with **operation, reason_code, error_type, release, instance_id** helps narrow down the scope very quickly. However, adding many unnecessary fields can increase cost and data exposure risk. Choose fields with clear diagnostic value.

## 3. Comparison with Traditional Text Logs

| Criterion | Unstructured log | Structured log |
| --- | --- | --- |
| Data | Free-form message | Named fields |
| Querying | Regex/full-text | Field-based queries |
| Event code | Usually embedded in prose | Dedicated event_code |
| Data types | Mostly String | Number, Boolean, String, null |
| Correlation | IDs embedded in message | Explicit request_id/trace_id |
| Stability | Changing wording easily breaks parsers | Schema can maintain compatibility |
| Volume | May have less metadata | Usually more metadata |
| Risks | Hard to parse, missing context | Cardinality, privacy, schema drift |

A JSON object containing only:

~~~json
{"message":"Order ORD-42 created for 12500 VND"}
~~~

still forces the parser to read the message string to extract order_id and amount. That is an example of **valid JSON without useful field structure**.

## 4. Common Representations

### JSON

JSON supports:
- **String:** event_code, service, request_id.
- **Number:** duration_ms, amount_minor, attempt.
- **Boolean:** cache_hit.
- **null:** Absent value, if the schema allows it.
- **Object/Array:** Limited nested data, when truly needed.

~~~json
{
  "event_code": "CACHE_LOOKUP",
  "cache_hit": true,
  "duration_ms": 12,
  "attempt": 1,
  "tags": ["orders", "cache"]
}
~~~

**duration_ms must be the number 12**, not the string **"12ms"**, if you want machines to compute on it without re-parsing.

### JSON Lines

File logging commonly uses **one JSON object per line**:

~~~json
{"event_code":"ORDER_CREATED","order_id":"ORD-42"}
{"event_code":"PAYMENT_RETRY","attempt":2}
{"event_code":"PAYMENT_FAILED","outcome":"failed"}
~~~

The JSON serializer must escape quotes, backslashes, newlines, and control characters. A newline inside a message must not arbitrarily split a record into two file lines. When a collector reads line by line, one event must be kept as one valid JSON object.

### Key-value / logfmt

~~~text
level=INFO event_code=ORDER_CREATED order_id=ORD-42 amount_minor=12500 currency=VND
~~~

This style is compact and easy to read by eye, but parsers need escaping conventions and typed data rules. Do not assume all logfmt systems interpret numbers and Booleans the same way.

## 5. Schema Design: Commonly Used Fields

| Field | Example | Purpose |
| --- | --- | --- |
| **timestamp** | 2026-11-09T12:34:56.789Z | Event time, usually UTC |
| **level** | INFO, WARN, ERROR | Priority level |
| **service** | checkout | Emission source |
| **environment** | production | Environment |
| **logger_name** | com.example.orders.OrderService | Class/package emitting the event |
| **event_code** | ORDER_CREATED | Stable event code |
| **message** | Order created | Human-readable description |
| **request_id** | req-42 | Request correlation |
| **trace_id / span_id** | ID from tracing | Distributed flow correlation |
| **operation** | createOrder | Operation |
| **outcome** | success, failed, retrying | Outcome |
| **duration_ms** | 35 | Measurement with unit |
| **error_type** | IOException | Exception type |
| **reason_code** | GATEWAY_TIMEOUT | Classifiable reason |
| **release** | 1.8.3 | Application version |
| **instance_id** | checkout-pod-7 | Instance/pod |

Not every event is required to have all fields. **ORDER_CREATED** should have order_id; **PAYMENT_RETRY** needs attempt or reason_code; **SERVICE_STARTED** usually has release. Choose fields based on the event's meaning.

### Naming Conventions

- Use a consistent style such as **snake_case**.
- For measurements, include units in the name, such as **duration_ms**, **size_bytes**, or **amount_minor**.
- Do not let the same field hold the number **200** in one event and the String **"success"** in another.
- Keep **event_code** within a stable set of values; do not generate new names containing request_id.
- Distinguish **status_code** from **outcome**; the two fields do not have the same meaning.
- Avoid copying an entire Java object/domain entity into JSON when only a few fields are needed.
- Do not put secrets, sensitive data, or unapproved payloads into fields.

## 6. Event Code and Message

**Event code** is for machine classification; **message** is for humans.

Example event codes:
- SERVICE_STARTED
- ORDER_CREATED
- ORDER_VALIDATION_FAILED
- PAYMENT_RETRY
- PAYMENT_AUTHORIZATION_FAILED
- PAYMENT_RECOVERED

If a developer changes a message from **Payment failed** to **Payment authorization failed**, queries by event_code do not need to change. This is one of the essential benefits of structured logging.

Do not set event_code to a dynamic value like **PAYMENT_FAILED_ORD-42**. Otherwise every order can produce a unique event code, rendering grouping meaningless.

## 7. Timestamps in Structured Logs

The **UTC ISO 8601** format is easy to exchange:

~~~text
2026-11-09T12:34:56.789Z
~~~

The Z denotes UTC. If storing local time, an explicit UTC offset/ZoneId is required. Never omit the timezone and force readers to guess which region the log-emitting machine belongs to.

Distinguish between:
- **Event time:** When the application records the event.
- **Ingestion time:** When the collector system receives the data.

They differ when there is queuing, network delay, or batching. If both need to be kept, use different field names and avoid overwriting event time with ingestion time.

When measuring duration in Java, use an appropriate source such as **System.nanoTime()** for elapsed time, and do not use that value as a Unix timestamp. A **duration_ms** field should genuinely be in milliseconds.

## 8. Log Levels Still Matter

Structured logging does not eliminate the concepts of INFO, WARN, ERROR, or DEBUG.

| Situation | Usually appropriate level |
| --- | --- |
| Startup and important operational events | INFO |
| Temporary retry that recovers | DEBUG or WARN depending on impact |
| Fallback leading to degradation | WARN |
| Final operation failure | ERROR |
| Detailed internal diagnostics | DEBUG/TRACE |

In JUL, level names are typically **INFO, WARNING, SEVERE, FINE**; in SLF4J they are typically **INFO, WARN, ERROR, DEBUG**. When multiple backends feed into a shared schema, define how severity is represented.

**Do not treat every failed retry attempt as a final failed operation.** A request might retry twice and then succeed; event_code and outcome must accurately reflect the result.

## 9. Java 17: Standalone Example Producing Structured JSON

This example uses **java.util.logging** built into JDK 17. A Handler reads fields according to the example's convention and writes one JSON object per line to **stdout**. Timestamps are fixed to make the output verifiable; numeric data remains a Number. This is an educational demo, not a full production JSON serializer.

Create the file **StructuredLoggingDemo.java**:

~~~java
import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class StructuredLoggingDemo {
    private static final Logger LOG =
            Logger.getLogger("demo.orders.OrderService");

    public static void main(String[] args) {
        Handler output = new Handler() {
            @Override
            public void publish(LogRecord record) {
                if (!isLoggable(record)) {
                    return;
                }
                System.out.println(toJson(record));
            }

            @Override
            public void flush() {
                System.out.flush();
            }

            @Override
            public void close() {
                flush();
            }
        };

        output.setLevel(Level.ALL);
        LOG.setLevel(Level.INFO);
        LOG.setUseParentHandlers(false);
        LOG.addHandler(output);

        try {
            Map<String, Object> order = new LinkedHashMap<>();
            order.put("order_id", "ORD-42");
            order.put("amount_minor", 12500);
            order.put("currency", "VND");

            emit(Level.INFO, "2026-11-09T12:34:56.789Z",
                    "ORDER_CREATED", "Order created", "req-42", order);

            Map<String, Object> retry = new LinkedHashMap<>();
            retry.put("attempt", 2);
            retry.put("reason", "retry after \"timeout\"");

            emit(Level.WARNING, "2026-11-09T12:34:56.790Z",
                    "PAYMENT_RETRY", "Gateway timeout; retrying",
                    "req-42", retry);
        } finally {
            LOG.removeHandler(output);
            output.close();
        }
    }

    private static void emit(
            Level level,
            String timestamp,
            String code,
            String message,
            String requestId,
            Map<String, Object> fields) {

        LogRecord record = new LogRecord(level, message);
        record.setLoggerName(LOG.getName());
        record.setInstant(Instant.parse(timestamp));
        record.setParameters(new Object[] {code, requestId, fields});
        LOG.log(record);
    }

    private static String toJson(LogRecord record) {
        Object[] values = record.getParameters();
        String code = (String) values[0];
        String requestId = (String) values[1];
        Map<?, ?> fields = (Map<?, ?>) values[2];

        return "{"
                + "\"timestamp\":" + quote(record.getInstant().toString())
                + ",\"level\":" + quote(record.getLevel().getName())
                + ",\"logger_name\":" + quote(record.getLoggerName())
                + ",\"service\":\"checkout\""
                + ",\"environment\":\"demo\""
                + ",\"event_code\":" + quote(code)
                + ",\"message\":" + quote(record.getMessage())
                + ",\"request_id\":" + quote(requestId)
                + ",\"fields\":" + fieldsJson(fields)
                + "}";
    }

    private static String fieldsJson(Map<?, ?> fields) {
        StringBuilder out = new StringBuilder("{");
        boolean first = true;

        for (Map.Entry<?, ?> entry : fields.entrySet()) {
            if (!first) {
                out.append(',');
            }
            first = false;
            out.append(quote((String) entry.getKey()))
                    .append(':')
                    .append(valueJson(entry.getValue()));
        }

        return out.append('}').toString();
    }

    private static String valueJson(Object value) {
        if (value == null) {
            return "null";
        }
        if (value instanceof String) {
            return quote((String) value);
        }
        if (value instanceof Integer
                || value instanceof Long
                || value instanceof Boolean) {
            return value.toString();
        }
        throw new IllegalArgumentException(
                "Unsupported demo JSON type: " + value.getClass());
    }

    private static String quote(String text) {
        StringBuilder out = new StringBuilder("\"");

        for (int i = 0; i < text.length(); i++) {
            char c = text.charAt(i);

            switch (c) {
                case '"':
                    out.append("\\\"");
                    break;
                case '\\':
                    out.append("\\\\");
                    break;
                case '\n':
                    out.append("\\n");
                    break;
                case '\r':
                    out.append("\\r");
                    break;
                case '\t':
                    out.append("\\t");
                    break;
                default:
                    if (c < 0x20) {
                        String hex = Integer.toHexString(c);
                        out.append("\\u");
                        for (int j = hex.length(); j < 4; j++) {
                            out.append('0');
                        }
                        out.append(hex);
                    } else {
                        out.append(c);
                    }
            }
        }

        return out.append('"').toString();
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 StructuredLoggingDemo.java
java StructuredLoggingDemo
~~~

**Exact stdout:**

~~~json
{"timestamp":"2026-11-09T12:34:56.789Z","level":"INFO","logger_name":"demo.orders.OrderService","service":"checkout","environment":"demo","event_code":"ORDER_CREATED","message":"Order created","request_id":"req-42","fields":{"order_id":"ORD-42","amount_minor":12500,"currency":"VND"}}
{"timestamp":"2026-11-09T12:34:56.790Z","level":"WARNING","logger_name":"demo.orders.OrderService","service":"checkout","environment":"demo","event_code":"PAYMENT_RETRY","message":"Gateway timeout; retrying","request_id":"req-42","fields":{"attempt":2,"reason":"retry after \"timeout\""}}
~~~

**Line-by-line explanation:**

1. The Logger is at **INFO**, so both INFO and WARNING are accepted.
2. The custom Handler writes to **System.out**, avoiding the behavior of JUL's ConsoleHandler which normally writes to stderr.
3. **LOG.setUseParentHandlers(false)** prevents parent Loggers from emitting duplicate records.
4. **setInstant(...)** uses fixed timestamps so stdout can be verified deterministically.
5. **setParameters(...)** stores the event code, request ID, and Map according to **the example's convention**; JUL does not provide this business JSON schema by default.
6. **LinkedHashMap** preserves the order of business fields in stdout.
7. **amount_minor** and **attempt** are JSON numbers, not strings.
8. The **quote** method escapes double quotes and control characters; therefore a reason containing **"timeout"** is still emitted validly.
9. The demo uses no external JSON libraries and opens no files. In production, choose a well-tested JSON serializer/encoder rather than using this custom quote method for all data types.
10. For invalid Unicode surrogates, nested objects, or external input, you need a standard JSON encoder with validation and size-limit rules.

**Key distinction:** The fact that JUL has **LogRecord.parameters** does not turn JUL into a full structured JSON API. The demo code explicitly interprets parameters into fields. When using a real backend, standardize how fields are passed and formatted.

## 10. SLF4J 2.x and Key-Value Pairs

**SLF4J** is a logging facade; in **SLF4J 2.x**, the fluent API supports adding named fields:

~~~java
log.atInfo()
        .addKeyValue("event_code", "ORDER_CREATED")
        .addKeyValue("order_id", orderId)
        .addKeyValue("amount_minor", amountMinor)
        .addKeyValue("currency", "VND")
        .log("Order created");
~~~

This is an illustrative snippet inside a class that has a Logger **log** and the relevant variables. It requires SLF4J 2.x; it is not a standalone program.

**addKeyValue does not automatically guarantee JSON output.** The provider/backend and encoder/layout must be configured to emit key-value pairs to stdout, files, or a collector.

With an exception:

~~~java
log.atError()
        .addKeyValue("event_code", "ORDER_SAVE_FAILED")
        .addKeyValue("order_id", orderId)
        .addKeyValue("outcome", "failed")
        .setCause(exception)
        .log("Failed to persist order");
~~~

**setCause(exception)** preserves the Throwable so the backend can output the stack trace and cause chain. Avoid passing only **exception.getMessage()** when the technical cause is needed.

SLF4J 1.7 does not have a fluent API like SLF4J 2.x; it typically uses logger overloads with placeholders and a Throwable. Before copying an example, verify your project's SLF4J generation and chosen provider.

## 11. MDC, ThreadContext, and Correlation

SLF4J's **MDC (Mapped Diagnostic Context)** is commonly used to store request context:

~~~java
import org.slf4j.MDC;

MDC.put("requestId", requestId);
try {
    processRequest();
} finally {
    MDC.remove("requestId");
}
~~~

This is an illustrative snippet requiring the corresponding variables/methods. The encoder/layout must be configured to read MDC data; calling MDC.put alone does not guarantee the log has a JSON request_id field.

With Log4j 2, a similar API is **ThreadContext**:

~~~java
import org.apache.logging.log4j.ThreadContext;

try (var scope = ThreadContext.putCloseable("requestId", requestId)) {
    processRequest();
}
~~~

This snippet requires the Log4j 2 API; scope is used to manage the context lifecycle.

### Asynchronous Boundaries

MDC is not propagated by default across **ExecutorService, CompletableFuture, message queues**, or other processes. When the same request_id/trace_id is needed, a proper context propagation mechanism must be in place. For distributed tracing, prefer obtaining trace_id/span_id from the actual tracing context rather than generating unrelated IDs and calling them traces.

Thread pools can reuse threads. **Always clean up MDC according to its lifecycle**, avoiding a request inheriting the ID of a previous request. Do not put tokens or sensitive data in MDC because those values can appear on every log line.

### How Do Request ID and Trace ID Differ?

- **request_id:** The ID of a single request at the application level.
- **trace_id:** A shared ID for a trace across multiple services.
- **span_id:** The ID of a specific span.
- **correlation_id:** An ID defined by a business/integration contract.

They can complement each other, but they are not completely interchangeable. A single request may emit multiple spans or asynchronous messages; the scope of each ID must be defined.

## 12. How Are Logback and Log4j 2 Configured?

### Logback

Logback has Appenders and Encoders. **PatternLayoutEncoder** primarily produces text; for structured JSON, use a supported JSON encoder and test compatibility with the project's Logback version.

The example below illustrates a **text** configuration in logback.xml, **not JSON**:

~~~xml
<configuration>
    <appender name="CONSOLE"
              class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <charset>UTF-8</charset>
            <pattern>%d{yyyy-MM-dd HH:mm:ss.SSS,UTC} %-5level %logger{36} trace=%X{traceId} - %msg%n</pattern>
        </encoder>
    </appender>
    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
    </root>
</configuration>
~~~

The pattern includes MDC traceId, but it does not automatically turn all data into JSON fields. For structured JSON, you must configure an encoder/layout that actually supports JSON, and verify that key-value pairs, MDC, and Throwables are preserved properly.

### Log4j 2

Log4j 2 supports Layouts, including options like **JsonTemplateLayout** when the appropriate module is installed. You can design a template to write timestamp, level, logger, context, and exceptions according to the required schema. The log4j2.xml configuration, dependencies, and layouts differ from Logback.

Do not arbitrarily add multiple SLF4J providers or bidirectional bridges in one application, as events may be misrouted, duplicated, or dropped.

### Real-World Verification

Do not conclude structured logging is working just because the code calls addKeyValue. Read the file/stdout, parse the JSON, and verify that fields are emitted with the right names, types, values, and context. Then send them through a test collector to confirm nothing is dropped or has its type altered.

## 13. Structured Exception Logging

An error event should describe:
- **operation:** The operation that failed.
- **event_code:** A stable error code.
- **reason_code:** A controlled classification.
- **error_type:** The Throwable type.
- **outcome:** Whether it is a final failure or just a retry attempt.
- **request_id/trace_id:** Investigation context.
- **cause/stack trace:** Technical details if needed.

~~~json
{
  "level": "ERROR",
  "event_code": "PAYMENT_AUTHORIZATION_FAILED",
  "reason_code": "GATEWAY_TIMEOUT",
  "error_type": "IOException",
  "operation": "authorize",
  "outcome": "failed",
  "request_id": "req-42",
  "message": "Authorization failed"
}
~~~

This is an example event; the field containing the stack trace depends on the actual encoder. Do not log ERROR for every retry that later recovers. An operation may fail three attempts and ultimately succeed; if a dashboard counts every attempt as a failed operation, the error rate will be wrong.

Avoid logging the same exception at the Repository, Service, and Controller layers without adding useful information. Choose the boundary responsible for the final outcome; log detailed diagnostics at the appropriate level and preserve the Throwable properly.

## 14. Cardinality and Indexing

**Cardinality** is the number of distinct values of a field. Fields like **level**, **outcome**, **event_code**, and **service** usually have a finite set of values. **request_id, trace_id, order_id** can contain a huge number of distinct values.

High cardinality does not mean a field is useless: request_id is very useful for finding a specific request. However, do not put request_id into a **metric label**, as extremely high cardinality causes time-series explosion.

Distinguish between:
- Fields stored in logs.
- Fields indexed for search.
- Metric labels used to group measurements.

Do not index every field unconditionally. Choose based on query needs and actual cost. An event_code should not include dynamic data like **ORDER_CREATED_ORD-42**, because that makes the event code catalog meaningless.

### Volume

Suppose an application emits **1,000 JSON events/second**, with each line averaging **700 bytes** after UTF-8 encoding:

~~~text
1,000 × 700 = 700,000 bytes/second
700,000 × 86,400 = 60.48 GB/day of raw data
~~~

This does not yet include indexing, replication, and retention. Structured logs can carry more metadata than plain text, so balance detail, ingestion cost, searchability, and retention period.

## 15. Data Protection Rules

Structured logging makes data easier to query, so **data protection** is critical:

- Never log passwords, API keys, access tokens, refresh tokens, or private keys.
- Never log raw cookies, Authorization headers, or sensitive payment information.
- Do not copy raw request/response bodies without an approved purpose.
- Keep only necessary and permitted technical IDs.
- Enforce field redaction/allowlists, access control, retention, and access auditing.
- Limit message/field sizes to prevent oversized logs or log injection.

**UTF-8 and JSON are not encryption.** Sensitive data in JSON can still be read by any account with log-viewing permissions. Hashing a field does not automatically make it safe or non-reidentifiable.

### Log Injection

A user-supplied message can contain newlines, quotes, or control characters, breaking JSON lines or forging fake ERROR lines. Use a standard JSON serializer to escape and validate data; never concatenate raw input directly into the output structure.

## 16. Collectors and End-to-End Data Quality

A typical pipeline looks like this:

~~~text
Java application
      |
      v
JSON log on stdout or file
      |
      v
Agent/collector
      |
      v
Parser/schema mapping
      |
      v
Storage and index
      |
      v
Query/dashboard/alert
~~~

Possible failure modes:
- The JSON writer accidentally prints a text prefix before the opening object brace.
- A message contains unescaped newlines.
- The collector converts a number into a string.
- A field is dropped due to size limits or a whitelist.
- The timestamp field is overwritten with the ingestion timestamp.
- Multiple services use the same field name with different types.
- Records are truncated due to rotation or overload.

Therefore, integration tests should verify both **field types and values after ingestion**, not just in-memory application content. For example, **attempt: 2** must still be a Number when queried in the collector.

## 17. Structured Logging, Metrics, and Traces

Structured logs, metrics, and traces complement each other:

| Source | Purpose |
| --- | --- |
| **Log** | Evidence of events with detailed context |
| **Metric** | Counts, rates, latency, SLOs |
| **Trace** | Request flow and spans across services |

If a dependency retries three times and the request eventually succeeds, logs show the reason for each retry, metrics measure retry rate/latency, and traces show the duration of each step.

Do not rely solely on log line counts to infer request counts: logs can be sampled/dropped or duplicate a single error across layers. For mandatory audit events, you need a durable pipeline with an explicitly defined retention policy; structured logging does not inherently guarantee immutable storage.

## 18. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| A JSON object with only message | Cannot query by fields | Separate event_code, outcome, IDs |
| amount as "12500 VND" | Hard to compute on | amount_minor number + currency |
| Inconsistent level/outcome | Broken dashboards | Shared schema |
| event_code contains request ID | Cardinality explosion | Stable codes |
| Calling addKeyValue but layout drops fields | Data loss | Check backend/encoder |
| Not cleaning MDC in thread pools | Wrong correlation | finally block or scope |
| Not propagating context across async boundaries | Broken traces | Proper propagation |
| Not passing Throwable | Missing stack trace | setCause/Throwable overload |
| Logging the same exception across multiple layers | Log noise | Choose the responsible boundary |
| Copying entire payloads | Sensitive data exposure | Field allowlist, redaction |
| Concatenating JSON without escaping | Invalid JSON/injection | Standard serializer |
| Not testing the collector | Lost fields/types | Integration tests |
| Indexing all dynamic values | High cost | Index selectively by need |
| Paging solely on ERROR | Many false alerts | Base alerts on impact and metrics |
| Using JSON logs as durable audit logs | Events can be lost | Dedicated audit pipeline |

## 19. Structured Logging Implementation Checklist

1. Clearly identify the backend: JUL, SLF4J + Logback, Log4j 2, or another stack.
2. Define a baseline schema and stable event_codes.
3. Use Number/Boolean/String with proper types, including units where needed.
4. Use UTC timestamps with explicit timezone information.
5. Propagate request_id/trace_id across boundaries and manage MDC lifecycle.
6. Choose a supported JSON encoder/layout with proper UTF-8 encoding.
7. Attach Throwables to final errors and avoid redundant, low-value logging.
8. Never log secrets, payment data, or sensitive payloads.
9. Establish policies for schema changes, indexing, cardinality, and retention.
10. Test the collector and queries with real data.
11. Combine with metrics/traces to understand error rates and request journeys.
12. Monitor volume, backpressure, dropped events, and parser errors.

## 20. Self-Check Questions

**1. Is structured logging just printing JSON?**  
No. It requires a schema with clear fields, types, and meanings that are preserved in storage.

**2. Why use event_code instead of searching by message?**  
Event codes remain stable when message wording changes, making queries and alerts easier to maintain.

**3. Why should amount_minor be a number?**  
To allow direct comparison and calculation, while currency is stored in a separate field.

**4. Does SLF4J 2.x addKeyValue automatically output JSON?**  
No. The provider and encoder/layout must support it.

**5. Does MDC automatically propagate across ExecutorService?**  
Never assume so. Context propagation and lifecycle cleanup are required.

**6. Why is request_id useful in logs but usually unsuitable as a metric label?**  
Because very high cardinality can cause too many time series.

**7. Does structured JSON protect access tokens?**  
No. You need field selection, redaction, access restrictions, and retention controls.

**8. Why does being able to read JSON in a file not guarantee the collector works properly?**  
The collector may drop fields, change types, or misparse records, so end-to-end testing is required.

**9. Does the JUL example mean every LogRecord has event_code and order_id built in?**  
No. The demo code attaches them to parameters by convention, and the Handler manually converts them to JSON.

**Remember:** Structured logging turns events into **searchable, analyzable data**, not just a JSON string. Success depends on a clear schema, stable event_codes, accurate context, safe data handling, appropriate Throwables, and a pipeline that preserves fields and types. Combined with metrics and traces, structured logs make investigating Java applications much more effective.
