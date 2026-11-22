# Structured Logging Trade-offs in Java: Benefits, Costs, and How to Choose

**Structured logging** is the practice of representing a log event as **named fields with explicit data types**, rather than just constructing a free-form text sentence. JSON Lines is a common format: each log event is an independent JSON object on a single physical line.

For example, the same failed payment event:

~~~text
WARN checkout_failed requestId=req-17 durationMs=42 attempt=2 outcome=RETRYABLE
~~~

~~~json
{"event":"checkout_failed","level":"WARN","requestId":"req-17","durationMs":42,"attempt":2,"outcome":"RETRYABLE"}
~~~

The JSON format lets analysis tools know that `durationMs` and `attempt` are numbers, and filter by `event` or `outcome` without splitting a text sentence using regex. In return, it demands more rigorous **schema design, serialization, sensitive data management, and pipeline operations**.

**Thesis of this article:** structured logging is not "always better than text logging." The greatest benefits appear when data needs to be **queried, correlated, aggregated, and processed automatically**; costs rise when event volume is too high, fields are unstable, values have high cardinality, or the team lacks schema and retention conventions.

## 1. Where Do the Trade-offs Sit in Logging Architecture?

The general flow of a Java application:

~~~text
Business event
     |
     v
Logger / facade (SLF4J, JUL, Log4j 2 API)
     |
     v
Attach context: level, event, traceId, durationMs...
     |
     v
Backend (Logback, Log4j 2, JUL...)
     |
     v
Encoder/Layout/Formatter
     |                  |
     | text pattern     | structured JSON
     v                  v
Console/file/stream/collector
     |
     v
Parse -> index -> store -> query -> alert
~~~

Structured logging can change **multiple links in the chain**, not just the formatter. If an application merely builds a string `"requestId=... durationMs=..."` and a JSON encoder places that entire string into a single `message` field, the system will produce a JSON object, but the components inside the message **do not necessarily become separate typed fields**.

Conversely, to preserve `durationMs` as a number, the application needs to pass a numeric field or corresponding metadata, and the encoder/collector must **preserve the type** along the transport path.

Three questions must be distinguished:

1. **Which events to emit?** Decisions around logger, level, sampling, and business logic.
2. **Which fields describe the event?** Decisions around structured event and context design.
3. **How to store, index, and query?** Decisions around backend, encoder, log collector, and storage.

Adding a JSON encoder only partially addresses the second question; it does not automatically establish security, cost, or query policies.

## 2. Benefits: Field-Based Querying Instead of Free-Form Text Parsing

In unstructured text logging without conventions, the same meaning can appear in many different phrasings:

~~~text
Order ord-7 failed after 42ms
payment failed: order=ord-7, elapsed=42
WARN request ord-7, retry in 42 milliseconds
~~~

To count errors of a specific event type, the system must recognize multiple string patterns and rely on regular expressions. When wording changes, searches and alerts can break.

With structured logging, you can standardize:

~~~json
{
  "event": "checkout_failed",
  "level": "WARN",
  "service": "payment-service",
  "orderId": "ord-7",
  "durationMs": 42,
  "outcome": "RETRYABLE"
}
~~~

A *conceptual query, not specific to any particular tool's syntax*:

~~~text
event == "checkout_failed"
AND outcome == "RETRYABLE"
AND durationMs > 40
~~~

The clearest benefits:

- **More accurate filtering:** `event` and `outcome` have stable values, independent of sentence phrasing.
- **Type-safe numeric queries:** `durationMs > 100` has numeric semantics, not lexicographical string comparison.
- **Easier dashboards and alerts:** aggregate errors by service, action, or reason code without parsing messages.
- **Cross-service correlation:** `traceId`, `spanId`, or `requestId` can help trace a request if every component emits logs consistently.
- **Easier automated processing:** systems can recognize fields, route them into data pipelines, or correlate them with metrics/traces.

**Trade-off:** these benefits only matter when the schema is stable, data is collected properly, and the search tool understands data types. If the backend only stores an unparsed JSON blob, querying fields may still be slow or require post-processing.

## 3. Overview of Benefits and Costs

| Aspect | What Structured Logging Provides | Trade-offs to Accept |
| --- | --- | --- |
| Querying | Filter/aggregate by field, minimal regex | Must standardize field names and types |
| Format | Machine-processable JSON/field map | Serialization, escaping, encoder, and parsing |
| Record length | Useful metadata and context | Repeated field names can make raw payloads larger |
| CPU and allocation | Can reduce downstream regex parsing | Creating maps/objects, JSON serialization, context handling |
| Storage | Queryable data; compression benefits from repeated keys | Indexing, retention, and queries can incur significant cost |
| Cardinality | `requestId`/`traceId` for precise tracing | Many unique values drive up index/aggregation costs if misconfigured |
| Security | Can select/mask individual fields per policy | PII, tokens, and secrets become easier to query/copy |
| Schema | Stable structure for system integration | Requires versioning, compatibility, and type checks |
| Operations | More powerful collectors and alerts | Must monitor encoder errors, queues, ingestion, and mapping |
| Distributed observability | Easy to attach correlation context | Context does not propagate automatically across threads/services |
| Human readability | Explicit, machine-parseable fields | JSON is longer and harder to scan quickly in a terminal |
| Backend portability | Can standardize a shared log contract | Encoders/field naming/MDC differ across stacks |

This table does not mean JSON is always slower or always larger in every system. **End-to-end cost** depends on event size, the previous text format, log emission rate, compression algorithms, indexing tools, and how the data is queried.

## 4. Storage Cost: JSON Can Be Larger Than Text

Suppose the same event is emitted as follows:

~~~text
INFO order_accepted ord-7 42ms
~~~

~~~json
{"timestamp":"2026-11-09T10:15:30Z","level":"INFO","service":"orders","event":"order_accepted","orderId":"ord-7","durationMs":42}
~~~

The JSON version has many **field names repeated on every event**. At high log volumes, that overhead can be significant; however, it also carries more metadata than the text example, so a fair comparison must ensure **the same information is stored**.

### Capacity Model (Hypothetical)

Suppose a system emits **100 events/second**, averaging after encoding:

- A text event is **200 bytes**.
- A structured event is **400 bytes**.

The number of events per day is `100 × 86,400 = 8,640,000`.

| Metric | Text | Structured |
| --- | ---: | ---: |
| Assumed bytes/event | 200 | 400 |
| Events/day | 8,640,000 | 8,640,000 |
| Total bytes/day | 1,728,000,000 | 3,456,000,000 |
| Decimal GB/day | 1.728 GB | 3.456 GB |
| Difference | — | 1.728 GB/day |

**This is an illustrative calculation, not a benchmark.** Actual size must be measured in bytes **after encoding** on a representative set of events. If the backend compresses data, repeated JSON keys often compress well. Conversely, **indexing**, data replication, retention, and query costs can outweigh the raw payload increase.

Do not infer monetary cost solely from event bytes: every logging platform prices and stores data differently. You must account for ingestion, replicated storage, searchable retention, archive, and egress where applicable.

### Reducing Cost While Keeping Structure

1. Only log fields that have **practical lookup or diagnostic value**.
2. Do not attach entire DTOs, request/response bodies, or stack traces to every INFO event.
3. Choose log levels and sampling based on need, reducing unnecessary events before serialization.
4. Use appropriate retention, compression, and indexing policies.
5. Consider indexing only a few key fields for search while storing others without indexing if the platform allows it.
6. Measure **payload + index + query cost**, not just JSON length.

## 5. CPU, Allocation, and Hot Path Overhead

A structured event typically goes through:

~~~text
Identify event / fields
        |
        v
Create Map / object / metadata
        |
        v
Substitute parameters, normalize types
        |
        v
JSON serialization + escaping
        |
        v
Write/queue/batch/network
~~~

These steps can consume CPU and allocate memory. On the other hand, text logging also requires interpolation, pattern formatting, timestamps, stack traces, and I/O; **you cannot conclude that structured logging is always slower than text** without measuring on the same data and backend.

In particular, a statement like:

~~~java
// Illustration inside a method with an SLF4J-style logger.
logger.debug("payload={}", expensiveSerialize(request));
~~~

still calls `expensiveSerialize(request)` **before** the library checks the DEBUG level (due to Java's argument evaluation rules). If the payload is expensive, guard it:

~~~java
if (logger.isDebugEnabled()) {
    logger.debug("payload={}", expensiveSerialize(request));
}
~~~

These are also **two illustrative snippets**, not standalone classes. Structured logging does not change this lazy evaluation principle.

**Watch out for another detail:** if the backend drops DEBUG at the logger, but your code builds a large object or Map before the log statement, that overhead still occurs. On hot paths, prepare minimal fields on the normal path, and only construct heavy diagnostic data when the level/sampling allows it.

### Cost of Stack Traces and Caller Location

Exception stack traces, source files, line numbers, or method names can cost more than a few JSON fields. Do not enable caller location for every event unless needed. With async logging, capturing caller/context may have to happen **before** handing the event off to another thread.

Measure with benchmarks and profiling on a real application, including throughput, allocation rate, tail latency (p95/p99), GC, CPU, and collector load. Do not just run an `ObjectMapper.writeValueAsString` loop and conclude how fast or slow the entire logging stack is.

## 6. Cardinality: Useful Fields That Can Become Expensive

The **cardinality** of a field is the number of distinct values it takes across a dataset.

| Field | Typical Cardinality | Usage |
| --- | --- | --- |
| `level` | Low (INFO, WARN, ERROR...) | Easy to group, filter, aggregate |
| `service` | Low/medium | Per-service dashboards |
| `event` | Low/medium if well-governed | Event type analysis |
| `outcome` | Low | Success/failure rates |
| `region` | Low/medium | Regional health |
| `requestId` | Very high, often near-unique | Find a specific request |
| `traceId` | Very high | Correlate logs with distributed traces |
| `userId` or `orderId` | Can be very high | Targeted investigation when permitted |
| `rawUrl` with query parameters | Can be extremely high | Usually should be normalized to a route template |

**High-cardinality fields are not always bad.** `requestId` and `traceId` can be essential for investigating individual requests. Problems arise when **every value is turned into an expensive dimension/index/aggregation** or promoted to a **metric label** causing an explosion of time series.

Example to avoid in metrics:

~~~text
http_requests_total{requestId="req-17"} 1
http_requests_total{requestId="req-18"} 1
...
~~~

A metric with a different `requestId` every time can generate huge numbers of time series. **Log fields and metric labels are two different tools.** You can keep `requestId` in logs for tracing without turning `requestId` into a metric label; which log fields to index should still be decided based on search needs and actual cost.

### Do Not Create Dynamic Field Names

Avoid:

~~~json
{"request_req-17": true, "request_req-18": true}
~~~

Use instead:

~~~json
{"requestId":"req-17"}
~~~

Dynamic field names mutate the schema, create many distinct mappings, and break queries. A fixed field with varying values may still have high cardinality, but it keeps the schema and processing consistent.

For HTTP endpoints, prefer `route="/orders/{id}"` when grouping by endpoint, rather than using `path="/orders/123456"` as an unbounded aggregation dimension; the route template should also come from a trusted source to avoid losing important context.

## 7. Schema Governance: When Is Adding a Field a Breaking Change?

With text logs, changing "Order accepted" to "Payment processed" may only affect readability (though it can break regexes). With structured logging, changing:

~~~json
{"durationMs":42}
~~~

to:

~~~json
{"durationMs":"42"}
~~~

can break queries and aggregations because **the type of the same field changed from number to string**. Some platforms apply automatic type mapping and may reject or mishandle inconsistent events.

### Minimal Schema Convention

Standardize core fields:

| Field | Recommended Type | Purpose |
| --- | --- | --- |
| `timestamp` | Standard timestamp with timezone (usually UTC) | Event time |
| `level` | Normalized value | INFO/WARN/ERROR... |
| `service` | String from a governed list of names | Event source |
| `event` | Stable string | Event type |
| `message` | String | Human-readable explanation |
| `traceId` / `requestId` | String, optional | Request correlation |
| `durationMs` | Number | Latency / time cost |
| `outcome` | Stable enum/string | SUCCESS/FAILED/RETRYABLE... |
| `errorType` | Stable string on error | Exception type |
| `schemaVersion` | String or integer per contract | Format identification when versioning is needed |

Exact names and types can follow a shared standard chosen by the organization; for example, OpenTelemetry Logs has its own attribute model. **You do not need to invent a new schema for every service**, nor must every system use the exact same field set in every case.

### Changes That Require Planning

- **Renaming a field:** `elapsedMs` → `durationMs` can break existing dashboards.
- **Changing a type:** `durationMs` number → string breaks numeric queries.
- **Changing semantics:** `latencyMs` used to measure HTTP time but now measures DB time only.
- **Changing units:** milliseconds → seconds without renaming the field causes silent bugs.
- **Null vs. absent:** a missing field, a `null` field, and an empty string are not necessarily equivalent.
- **Nested objects:** `user.id` and `userId` may become two different schemas depending on the collector.
- **Field collisions:** the backend emits `level` automatically while the application also writes `level`; clear precedence/namespace rules are required.

A good strategy is to review schema changes like a **data contract**, write tests for critical fields, and deploy changes compatibly with active queries. When a breaking change is needed, you can emit both old and new fields during a transition period or update collectors and dashboards in coordination.

## 8. Event Conventions Matter More Than Producing Huge JSON

A JSON record with 40 fields where `event` and `message` vary arbitrarily can be harder to operate than a well-governed 5-field text log.

Example of **stable event naming**:

~~~json
{"event":"payment_retry","outcome":"SCHEDULED","attempt":2,"reason":"TIMEOUT"}
~~~

Avoid turning the event name into a dynamic sentence:

~~~json
{"event":"payment retry for order ord-7 at 10:15:30 with timeout"}
~~~

The latter embeds IDs, timestamps, and wording inside the event name itself, destroying groupability. Use a stable `event="payment_retry"` and add `orderId`, `attempt`, and `reason` **when permitted to log**.

To optimize queries:

1. **Event names describe a category of behavior**, not a single instance.
2. **Field names are consistent** across services when they share the same meaning.
3. **Keep types and units consistent**, e.g., `durationMs` is a number in milliseconds.
4. **Choose fields based on diagnostic questions**: if nobody uses a field and it adds cost or security risk, consider removing it.
5. **Keep `message` for humans**, but do not make `message` the sole source of data for aggregations.

Good structured logging is **event design**, not just a task of switching a console pattern to JSON.

## 9. Security and Privacy: Easy to Search Means Easy to Expose

Structured logging makes data easy to search and extract by field, so accidentally logging `email`, `accessToken`, `Authorization`, or payment details can increase the risk of **leaking or exploiting sensitive information**.

Do not log:

~~~json
{
  "event": "login_failed",
  "password": "plaintext-password",
  "authorization": "Bearer secret-token"
}
~~~

This is an **example of data NOT TO LOG**, not a guide to putting real credentials into a logging system.

Instead, choose minimal fields:

~~~json
{
  "event": "login_failed",
  "outcome": "DENIED",
  "reason": "INVALID_CREDENTIALS",
  "requestId": "req-17"
}
~~~

Principles:

- **Allowlist fields at the source:** only log what serves a defined operational purpose.
- **Never log secrets**: passwords, tokens, API keys, session cookies, private keys, card data, authentication payloads.
- **Minimize personal identifiers:** if you need to investigate an account, consider an appropriate internal ID or pseudonym along with protection policies.
- **Redaction must happen in the right order:** ideally before serialization/ingestion; avoid relying on a downstream regex to catch every secret.
- **Access control and retention:** structured logs may be copied to collectors, indexes, archives, dashboards, and exports; each location needs proper permissions and data governance.
- **Region/tenant separation:** if data residency or tenant isolation is required, enforce it in both the pipeline and storage.
- **Exceptions also carry data:** messages or stack traces can contain URLs, SQL, parameters, or sensitive payloads.

**JSON escaping is not redaction.** A standard JSON library preserves structure when encountering quotes or newlines, but it does not know which fields are secret. Similarly, SLF4J `{}` parameter substitution does not automatically mask tokens.

Another risk is **log injection**: unescaped newlines in text can forge "fake log lines"; JSON Lines with a proper encoder keeps control characters inside values escaped. That preserves event boundaries, but does not replace input validation at the source.

## 10. Async Logging: Higher Throughput with Reliability Trade-offs

Structured events are often sent through an asynchronous queue/buffer or appender so business threads do not block on serialization/I/O. Async mechanisms can increase throughput and reduce average latency, but they introduce:

- **Queue capacity:** what happens when the queue is full?
- **Backpressure:** do you block application threads to preserve logs?
- **Drop policy:** do you proactively drop debug/info logs under overload?
- **Shutdown/flush:** are queued events flushed before the process exits?
- **Ordering:** is record ordering across threads/processes preserved as readers expect?
- **Metadata capture:** were `requestId`/`traceId`/MDC captured when the event was created?
- **Memory overhead:** events/maps/objects in the queue consume memory and can cause GC pressure.
- **Downstream failures:** if network/file/collector cannot accept data, is there retry, buffering, or alerting?

| Policy When Queue Is Full | Benefit | Risk |
| --- | --- | --- |
| Block producer | Fewer lost logs if backend recovers | Increases latency, propagates backpressure to business logic |
| Drop events by level/sampling | Keeps business threads responsive | Loses diagnostic information right when an incident occurs |
| Buffer/retry externally | Improves short-term resilience | Consumes memory/disk, has limits, requires operations |

There is no universal optimal choice: a financial transaction app has different audit requirements from an image-processing app or game telemetry. **Application logs are not inherently a durable audit system.** If an event must be confirmed written and never lost per business contract, you need a dedicated reliable storage mechanism with appropriate transactions/acknowledgements.

## 11. Structured Logging and Correlation Context in Java

As a request passes through multiple layers, you can attach `traceId`, `spanId`, `requestId`, or controlled tenant information. Depending on the API/backend, this data can be passed via **MDC** or the SLF4J 2.x fluent API.

### Pros and Cons of MDC

MDC (*Mapped Diagnostic Context*) is typically a map of **strings** bound to the execution context. SLF4J example:

~~~java
// Illustration inside a method that already has requestId and logger.
try (org.slf4j.MDC.MDCCloseable ignored =
        org.slf4j.MDC.putCloseable("requestId", requestId)) {
    logger.info("event=order_accepted");
}
~~~

Strength: code within the scope can attach the same `requestId` without manually passing it to every log message. Weakness: MDC usually relies on thread-local context, so **it does not automatically propagate across thread pools, `CompletableFuture`, reactive pipelines, or another service**.

If you forget to clear MDC in a thread pool, a subsequent request can inherit the wrong `requestId` from a previous request; using `try-with-resources` or a framework's context propagation mechanism helps prevent context leaks.

**String-based MDC does not guarantee JSON fields keep number/boolean types.** If you store `durationMs="42"` in MDC, the encoder may emit it as a JSON string; to get typed values, you need an encoder/API that supports typed data.

### SLF4J 2 Fluent Key-Value API

SLF4J 2.x supports adding key-value pairs at the event level:

~~~java
// Illustration inside a method with an SLF4J 2.x logger.
logger.atInfo()
        .addKeyValue("event", "order_accepted")
        .addKeyValue("durationMs", durationMs)
        .addKeyValue("orderId", orderId)
        .log("Order accepted");
~~~

This is **not a standalone program**; `durationMs` and `orderId` are variables in scope. The API allows attaching metadata, **but does not guarantee every backend/encoder will automatically emit them as typed JSON fields**. You must configure and test the actual output. For example, Logback's text pattern has a converter for key-value pairs, yet a text pattern still does not automatically become a typed JSON object.

When using the SLF4J facade, proper structured output also depends on **the provider, backend, encoder, and collector**. If the backend is JUL or NOP, adding key-values will not magically create a JSON pipeline.

## 12. Runnable Java 17+ Example: Plain Text vs. Safe JSON

This example creates the same message containing quotes and a newline character, comparing naive string concatenation with properly serialized JSON using Jackson. It also demonstrates numeric fields and allowlisting: the program **does not put `apiKey` into the event map**.

This is an example of **encoding and log event design**, without setting up an SLF4J/Logback backend or writing to a file. In production, event objects are typically converted to JSON by the backend's encoder. We use a dedicated JSON library rather than concatenating JSON manually so we do not demonstrate an error-prone practice.

### 12.1. Project Structure

~~~text
structured-tradeoff-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── StructuredTradeoffDemo.java
~~~

### 12.2. pom.xml

The example uses Java 17+, Maven, and Jackson `jackson-databind:2.18.4` (a tested illustrative version, **not claimed to be the latest version**).

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
  xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>demo</groupId>
  <artifactId>structured-tradeoff-demo</artifactId>
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

### 12.3. StructuredTradeoffDemo.java

~~~java
package demo;

import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.LinkedHashMap;
import java.util.Map;

public final class StructuredTradeoffDemo {
    public static void main(String[] args) throws Exception {
        String untrustedMessage = "gateway said: \"retry\"\nplease wait";
        String plain = "WARN checkout_failed requestId=req-17 durationMs=42"
                + " message=" + untrustedMessage;

        Map<String, Object> event = new LinkedHashMap<>();
        event.put("event", "checkout_failed");
        event.put("level", "WARN");
        event.put("requestId", "req-17");
        event.put("durationMs", 42);
        event.put("attempt", 2);
        event.put("outcome", "RETRYABLE");
        event.put("message", untrustedMessage);

        String json = new ObjectMapper().writeValueAsString(event);

        System.out.println("plainPhysicalLines=" + plain.split("\\R", -1).length);
        System.out.println("jsonPhysicalLines=" + json.split("\\R", -1).length);
        System.out.println("durationIsNumber=" + (event.get("durationMs") instanceof Number));
        System.out.println("hasSensitiveField=" + event.containsKey("apiKey"));
        System.out.println("json=" + json);
    }
}
~~~

Run from the directory containing `pom.xml`:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.StructuredTradeoffDemo
~~~

**Verified exact stdout:**

~~~text
plainPhysicalLines=2
jsonPhysicalLines=1
durationIsNumber=true
hasSensitiveField=false
json={"event":"checkout_failed","level":"WARN","requestId":"req-17","durationMs":42,"attempt":2,"outcome":"RETRYABLE","message":"gateway said: \"retry\"\nplease wait"}
~~~

Explanation:

1. The string `untrustedMessage` contains **a quote and a literal newline character**. When concatenated directly into plain text, the event spans **two physical lines**, which can cause a collector to misread it as two separate records.
2. Jackson encodes quotes as escaped `\"` and the newline as `\n`; the JSON object remains on **one physical line**.
3. `durationMs` and `attempt` are passed as numbers, so the serializer outputs numeric literals rather than strings `"42"` or `"2"`.
4. `hasSensitiveField=false` only proves the program **did not put the `apiKey` key into the map**. It is not a general-purpose secret filter; the value of `message` in a real application still needs to be controlled.
5. `LinkedHashMap` keeps insertion order in the example output. **Do not build dashboards that depend on JSON property order**: per data interchange principles, field names and types are what matter.
6. The example omits a timestamp so output stays identical across runs. In production, include a timestamp of the **event time** with an explicit timezone.

**Trade-off of the example itself:** Jackson and `ObjectMapper` add a dependency, serialization work, and object/string allocations. In a dedicated logging backend, manage a supported encoder and avoid creating a new `ObjectMapper` or a large event map for every message unnecessarily.

## 13. One Event Per Line Is Not Enough for Good Structured Logging

A valid JSON object can still hold unqueryable data if you dump everything into `message`:

~~~json
{"message":"checkout failed; requestId=req-17; durationMs=42"}
~~~

Readers still have to parse the inner string to extract the duration. Better:

~~~json
{"event":"checkout_failed","requestId":"req-17","durationMs":42}
~~~

However, do not go to the extreme of turning **every word in the message into a field**. Too many fields bloat the schema, increase storage/index costs, and are hard to keep consistent. Only extract values needed for filtering, grouping, tracing, or long-term contract semantics.

### Should You Drop `message` Once You Have `event` and Fields?

Not necessarily. A short, clear `message` helps operators read quickly in a terminal; `event` and fields enable machine querying. Both can coexist as long as they do not introduce sensitive data or pointless duplication.

Example:

~~~json
{
  "level": "WARN",
  "event": "payment_retry",
  "message": "Retry scheduled after gateway timeout",
  "reason": "TIMEOUT",
  "attempt": 2
}
~~~

Here `message` is for humans; `event`, `reason`, and `attempt` serve automation.

## 14. Limitations in Collection and Query Systems

Generating JSON in Java **does not guarantee** the observability backend receives a structured object:

- **Ingestion parser** might fail to parse JSON Lines and store the whole line as a string.
- **Field mapping** might treat `durationMs` as a string because the first event contained `"42"`.
- **Nested fields** may be flattened into different names; for example, `http.status` and `{"http":{"status":200}}` are not always equivalent.
- **Field name conflicts** can occur when two services use the same key with different types.
- **Dropped events** can happen if queues, collectors, or backpressure are overwhelmed.
- **Indexing policies** may or may not index a field depending on configuration.
- **Timestamp parsing** may fall back to ingestion time instead of event time if the field is not mapped properly.
- **Multiline parsing** is still needed for plain-text stack traces; a JSON serializer only guarantees control characters inside *JSON values* are properly escaped.
- **Retention/tiering** determines whether a record remains searchable after several days, independent of Java.

To verify structured logging works, run an **end-to-end test**:

1. Emit an event with a non-sensitive test ID.
2. Inspect the raw output to confirm valid JSON, one object per event.
3. Verify the collector parses it with the right fields and types.
4. Test queries using numeric fields, enums, and `traceId`/`requestId`.
5. Check access controls and how sensitive data is handled.
6. Simulate a full queue or slow backend in a test environment.
7. Verify results in the final storage/display system, not just `System.out.println`.

A clean JSON file that dashboards cannot parse fails the goal of structured logging.

## 15. Structured Logging Does Not Replace Metrics and Tracing

The three observability signals serve different roles:

| Signal | Best Suited For | Limitations |
| --- | --- | --- |
| **Structured logs** | Details of individual events, errors, decisions, context | High volume; querying/indexing can be costly |
| **Metrics** | Rates, ratios, percentiles, trend alerts | Usually do not store individual requests; label cardinality must be controlled |
| **Distributed traces** | Span relationships and request paths across services | Sampling and instrumentation may omit some traces |

Having `traceId` in logs helps correlate them with traces, **but does not create spans automatically**. Putting `durationMs` in every log helps investigate a single request, but alerting on p99 latency per service usually requires metrics/histograms or appropriate aggregation tools.

Do not try to use individual log events to replace every metric: logging every hot-path operation can be expensive. Conversely, an aggregate error metric does not provide a specific `requestId` or stack trace; structured logs support root-cause investigation.

## 16. When to Choose Structured, Text, or Hybrid Logging?

| Context | Appropriate Approach | Reason |
| --- | --- | --- |
| Microservices with collectors, dashboards, tracing | Structured logging with a shared schema | Filter and correlate data across services |
| Applications needing error queries by event/reason/duration | Structured for critical events | Stable fields and types |
| Small CLI scripts read mainly on a console | Concise text may suffice | Avoid unnecessary schema/index operations |
| Small Java service expected to grow | Text console in dev, JSON in ingested environments | Profile-based encoders while keeping a suitable logging API |
| Very high log-volume systems | Selective structured + levels/sampling/retention | Reduce cost at the source before indexing |
| Systems requiring lossless audit trails | Dedicated durable audit mechanism | Standard logging does not guarantee transactional durability |
| Resource-constrained devices/apps | Measure encoder cost and choose lightweight config | CPU, memory, storage, and uplink are constrained |
| Legacy apps with stable text logs | Migrate high-value event groups incrementally | No need to change everything at once |

**Do not decide based solely on "JSON looks more modern."** Answer these questions: which queries must be fast, how many events per second, what storage/search cost is acceptable, what data is allowed to be logged, and who owns the schema.

A practical implementation pattern is **one event-emitting API with two output profiles**: human-readable text in development and JSON Lines for collectors in environments that need analysis. However, verify that **field semantics and levels** stay consistent across profiles.

## 17. Step-by-Step Rollout and Measurement Process

### Step 1 — Define Observability Questions

For example:

- "How many payment retries occurred in the last 15 minutes?"
- "Which service is experiencing timeout errors?"
- "Which routes have requests with `durationMs > 1000`?"
- "Which services did a `traceId` pass through?"

These questions lead directly to fields: `event`, `reason`, `service`, `durationMs`, `route`, `traceId`.

### Step 2 — Establish a Minimal Schema

Choose the required fields, types, units, and meanings. Document explicitly: `durationMs` is a **number in milliseconds**; `event` is a stable enum string; `timestamp` uses UTC or an explicit offset.

### Step 3 — Choose API and Encoder

In Java, evaluate SLF4J 2 fluent key-values, MDC/context propagation, Logback/Log4j 2 encoders, or an appropriate JUL logging pipeline. Check backend dependencies; **having the SLF4J API does not automatically give you a JSON encoder**.

### Step 4 — Protect Data at the Source

Apply field allowlists, redaction, length limits, and exception checks. Do not dump raw HTTP headers, tokens, or request bodies into structured events just because the serializer makes it easy.

### Step 5 — Run a Controlled Parallel Rollout

Test on one service or critical event group, compare text and structured outputs, or shift a portion of traffic. Avoid accidentally **logging the same event twice into two billed pipelines** without measuring cost.

### Step 6 — Benchmark End-to-End

Measure:

- Application CPU, allocation, GC, and p99 latency.
- Actual bytes/event after encoding and compression.
- Ingest throughput and parse/mapping errors.
- Index/storage/retention costs.
- Query latency and alert quality.
- Event drops/backpressure when the collector is slow.
- Rate of events missing required fields.

### Step 7 — Manage the Schema as Code

Store field names, types, sample events, and contract tests in the appropriate configuration or application repository. When changing the schema, review impacts on dashboards, ingestion, and security policies.

### Step 8 — Tune Retention and Indexing

Do not index every field out of habit. Separate short-term search needs from long-term archival, restrict access to sensitive data, and audit which queries actually need to be supported.

## 18. Common Mistakes and How to Fix Them

| Symptom | Cause | Fix |
| --- | --- | --- |
| JSON is emitted, but still need regex on `message` | Dumping all data into `message` | Extract stable fields with queryable meaning |
| `durationMs > 1000` query gives wrong results | Field is a string or mapped with wrong type | Keep numeric type, test ingestion mapping |
| Index/storage grows rapidly | Too many fields, high cardinality, long retention | Measure cost, select indexed fields, limit log volume |
| JSON breaks when input has newlines/quotes | Manual JSON string concatenation | Use a proper JSON serializer/encoder |
| `requestId` appears on another thread with wrong value | MDC not cleared or propagated properly | Clear scopes, try/finally, context propagation |
| Logs missing `traceId` in async jobs | Thread boundary drops context | Capture/propagate context before creating events |
| CPU/GC spikes when enabling structured logs | Serializing large objects, stack traces, caller location | Profile, trim fields, and use lazy data creation |
| Service p99 latency spikes when collector is slow | Async queue fills and blocks producer | Design backpressure/drop policy as needed |
| Records lost on shutdown | Queue not flushed or backend errors | Test shutdown behavior, handle lifecycle, use separate audit if needed |
| `service` or `event` field is inconsistent | Lack of schema governance | Schema contract, enums, and code review |
| `durationMs` changes units | No type/unit convention | Include unit in field name and add tests |
| Secrets appear on dashboards | Logging raw DTOs/headers without allowlist | Block/redact at source, audit indexes/archives |
| JSON encoder enabled, but collector stores strings | Parser/ingestion pipeline not configured | Test raw → collector → index → query |
| Developer console is hard to read | Long JSON with lots of metadata | Add a dev text profile or field-rendering viewer |
| Using `requestId` as a metric label | Extremely high cardinality | Keep in logs; use low-cardinality metric labels |
| Message wording change breaks alerts | Alerts rely on text regex | Alert on stable `event`/`reason` fields |

## 19. Self-Check Exercises

**Exercise 1.** A service emits `{"durationMs":"42"}` and `{"durationMs":100}`. What can happen?

**Answer:** The same field has inconsistent types; the collector may fail to map it, drop the field, or handle the events differently. Standardize `durationMs` as numeric at the source and test ingestion.

**Exercise 2.** Why should you avoid putting `requestId` into a metric counter label even though it is very useful in logs?

**Answer:** `requestId` is usually near-unique, causing time-series cardinality to explode. Log fields are for finding a single request while metric labels are for finite grouping; they have different constraints.

**Exercise 3.** Does JSON automatically prevent log injection?

**Answer:** A proper JSON encoder escapes quotes, newlines, and control characters to protect structure, but it does not guarantee there are no secrets, does not replace validation, and does not prevent misleading content from untrusted sources.

**Exercise 4.** Why might a log event with both `event` and `traceId` still not show up in a dashboard?

**Answer:** The provider/encoder may be misconfigured, the logger level may filter it out, the queue may drop it, the collector may not parse/index it, or the data may be outside retention. Verify end-to-end instead of only inspecting the Java object.

**Exercise 5.** If the JSON payload is twice the size of text, can you conclude total logging cost doubles?

**Answer:** No. Compression, indexing, tiering, query volume, replication, network, and backend pricing affect total cost differently. Measure on the real system.

**Exercise 6.** A team only has CLI scripts and reads logs in a terminal. Must they apply JSON to every debug line?

**Answer:** Not required. If there is no need for field-based querying or an ingest pipeline, concise text may be enough. You can emit structured output only where automation is needed.

## 20. Checklist Before Choosing Structured Logging

- [ ] Identified specific query/alert questions that need fields instead of regex.
- [ ] Separated human-readable `message` text from **event names and typed fields**.
- [ ] Defined a minimal schema for timestamp, level, service, event, reason, IDs, and metrics/measurements.
- [ ] Field names and units are stable; no dynamic field names per request ID.
- [ ] Separated **log fields** from low-cardinality **metric labels**.
- [ ] Only keep valuable fields; do not serialize entire large requests/DTOs out of habit.
- [ ] Use a verified JSON encoder, never ad-hoc string concatenation for JSON.
- [ ] Applied allowlisting/redaction at the source; no tokens, passwords, or sensitive data logged.
- [ ] Verified MDC/context propagation across thread pools and async execution.
- [ ] Tested exceptions, newlines, Unicode, null/missing fields, and types.
- [ ] Measured CPU, allocation, p99 latency, bytes/event, index/storage, and queries.
- [ ] Defined queue-full behavior, drop/backpressure, flush, and shutdown handling.
- [ ] Configured mapping/parsing in the collector, access controls, and retention.
- [ ] Verified a log event end-to-end: **Java → backend → collector → query**.
- [ ] For durable audit requirements, used a dedicated acknowledged storage mechanism.
- [ ] Chose structured, text, or hybrid based on **actual needs and measured data**.

**Conclusion:** Structured logging trades **the flexibility of free-form text** for **field-based querying and automation with typed fields**, while introducing costs in serialization, storage/indexing, schema governance, cardinality, and data protection. Effective adoption means **logging the right events, with the right fields, right types, right context, and right retention**, then measuring results end-to-end. When field-based querying is not yet needed or resources are tightly constrained, good text logging remains a reasonable choice.