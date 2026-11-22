# Structured Log Analysis in Java

## 1. What is structured log analysis?

**Structured log analysis** is the practice of filtering, querying, aggregating, and correlating logging events represented by **fields with clear names, data types, and semantics**. Instead of relying solely on a free-form message string, we can ask: which service returns the most HTTP 5xx responses, what is the error rate over time, what is checkout's p95 latency, which events belong to the same trace, and what percentage of records fail schema validation.

Example text log:

~~~text
2026-11-09 08:00:01 ERROR checkout timeout; HTTP 503; 920 ms; trace=t-02
~~~

The same event in structured JSON format:

~~~json
{
  "ts": "2026-11-09T08:00:01Z",
  "service": "checkout",
  "event": "http.request.completed",
  "level": "ERROR",
  "trace_id": "t-02",
  "status_code": 503,
  "duration_ms": 920,
  "error_type": "GatewayTimeout"
}
~~~

From the JSON record, a program can extract **status_code** as a number, **duration_ms** as a duration, and **trace_id** as a correlation key without writing regexes tied to sentence phrasing. When the message wording changes or is translated into another language, the schema can remain unchanged.

After this lesson, you will be able to:
- Distinguish a **structured event** from a plain text line wrapped in JSON.
- Design a schema, define required/optional fields, and manage data types.
- Read and validate **NDJSON** (each line is one JSON object).
- Filter by time, service, event, severity, status, error_type, and trace_id.
- Group and compute counts, HTTP 5xx rate, latency distribution, and p95.
- Identify **double counting** situations when one error is logged across multiple services.
- Handle malformed JSON, missing fields, null values, schema versions, and late-arriving data.
- Run a Java 17+ example using **Jackson** to analyze actual data.
- Understand the limitations of logs for SLI/SLO tracking and how to complement them with metrics/traces.

**Scope:** This lesson belongs to the **Structured logging** section of **Java Core Logging**, focusing on how to analyze already-structured data. The Java example uses Maven/Jackson to read JSON and is not tied to any specific log search tool or commercial backend.

## 2. JSON does not automatically mean good structured logging

A line such as:

~~~json
{"message":"Payment failed, request req-42, after 920 ms"}
~~~

is valid JSON, yet the service, outcome, request ID, and duration are still trapped inside a single string. The backend still has to parse text and easily breaks when the message changes.

A record with higher analytical value:

~~~json
{
  "event": "payment.authorization.failed",
  "service": "payment",
  "request_id": "req-42",
  "duration_ms": 920,
  "error_type": "GatewayTimeout",
  "message": "Payment authorization timed out"
}
~~~

Here, **message** is for human readers, while **event** and the attributes are for querying. A system may store structured data in formats other than JSON; JSON/NDJSON is simply a common interchange format.

Key principles:
1. **Stable event codes**: use `payment.authorization.failed`, not an entire translated sentence as the key.
2. **Consistent data types**: `duration_ms` is a number, `status_code` is an integer.
3. **Explicit units**: the `duration_ms` field is distinct from `duration_seconds`.
4. **Uniform vocabulary**: `service`, `event`, `level`, and `trace_id` share the same meaning across all producers.
5. **Do not use user data as field names**: variable data belongs in values, not keys.
6. **Separate severity from business status**: `level=ERROR` does not automatically imply HTTP 5xx.
7. **Include correlation identifiers when available**: `trace_id`, `span_id`, or `request_id` as appropriate.
8. **Control data sensitivity**: structuring data does not automatically make tokens or passwords safe.

## 3. Recommended schema for an HTTP completion event

| Field | Data type | Required? | Role |
| --- | --- | --- | --- |
| **ts** | ISO 8601 String with offset/Z | Yes | Event timestamp |
| **service** | String | Yes | Source grouping |
| **environment** | String | Per deployment | Distinguish dev/staging/prod |
| **event** | Standardized String | Yes | Event classification |
| **level** | Severity String | Yes | Severity filtering |
| **trace_id** | String | When tracing is enabled | Correlate events across services |
| **span_id** | String | When tracing is enabled | Locate a specific span |
| **request_id** | String | When request context exists | Track request at a boundary |
| **status_code** | Integer | For HTTP completion | Group HTTP status codes |
| **duration_ms** | Non-negative Number | For completion | Compute duration |
| **error_type** | String | Only on error | Categorize error types |
| **route_template** | String | When analyzing HTTP routes | Avoid high-cardinality raw URLs |
| **schema_version** | Integer/string with contract | Recommended for schema management | Support version changes |

A richer example record:

~~~json
{
  "ts": "2026-11-09T08:00:01Z",
  "schema_version": 1,
  "service": "checkout",
  "environment": "development",
  "event": "http.request.completed",
  "level": "ERROR",
  "trace_id": "t-02",
  "request_id": "req-02",
  "http_method": "POST",
  "route_template": "/orders/{id}/checkout",
  "status_code": 503,
  "duration_ms": 920,
  "error_type": "GatewayTimeout"
}
~~~

This is an educational schema, **not a mandatory list of OpenTelemetry fields**. If your system uses OpenTelemetry semantic conventions, adopt the actual naming conventions of that version and map them consistently across producer, collector, and backend.

### 3.1. Four non-equivalent data conditions

- **Missing field**: the event does not have `error_type` at all.
- **Null**: `error_type: null` is present, but has no value.
- **Empty string**: `error_type: ""`; usually not a useful error category.
- **Wrong type**: `error_type: 503` when the contract expects a String.

Do not blindly collapse all of these into **unknown** and lose source quality information. A validator should distinguish a record missing a required field from a record omitting an inapplicable optional field.

### 3.2. Schema evolution

If an older version uses **duration_ms** and a newer version uses **latency_ms**, dashboards can lose data. You need to manage:
- Field names and types per schema version;
- the overlap period when old and new producers run in parallel;
- normalization mappings at the collector/backend;
- tests for queries and alerts;
- the count of events missing required fields;
- a migration plan for historical data and analytics tools.

Changing message wording does not necessarily require changing the event code. However, if the semantics of the event change from "order created" to "order paid", you should review the event code or version.

## 4. NDJSON and ingesting events into an analytics system

**NDJSON (newline-delimited JSON)** places one JSON object on each line. This format is convenient for log streams and many collectors:

~~~json
{"ts":"2026-11-09T08:00:00Z","service":"checkout","event":"http.request.completed","status_code":200,"duration_ms":80}
{"ts":"2026-11-09T08:00:01Z","service":"checkout","event":"http.request.completed","status_code":503,"duration_ms":920}
~~~

These are **two independent JSON documents on two lines**, not a single JSON document. To store a single standard JSON document containing multiple events, you can use an array, though you lose NDJSON's line-by-line streaming convenience.

Typical pipeline:

~~~text
Java application
    |
    | emits event + typed fields
    v
Logging API / backend / JSON encoder
    |
    v
stdout / file / network
    |
    v
Collector: parse -> validate -> enrich -> redact -> route
    |
    v
Storage / search / analytics
    |
    +--> filter / aggregate / percentiles
    +--> dashboard / alert
    +--> trace correlation / investigation
~~~

**Do not test output only at the console.** An event may be valid JSON at the producer, yet have `status_code` coerced into a String by the collector, or be truncated, dropped, sampled, or delivered too late.

### 4.1. Event time vs. ingest time

- **Event time** is when the application emitted the event, for example `08:00:01Z`.
- **Ingest time** is when storage/collector received it, which may be later due to buffering, queues, retries, or network delays.

Application behavior analysis should use normalized event time with explicit timezones. Pipeline health analysis uses ingest time and ingestion lag. An analysis window should use the **[start, end)** rule so boundary events are not double-counted across adjacent windows.

If services log timestamps in different timezones or offsets, parse them into `Instant` before comparing. Do not compare strings arbitrarily when timestamps use different formats.

## 5. Filtering data accurately before aggregation

Before computing metrics, answer:
- What **time range**?
- Which **service/environment**?
- Which **event type** is being counted?
- Does each record represent **one event, one request, or one transaction**?
- Which fields must be present to include a record in the aggregation?

Example filter for checkout HTTP events:

~~~text
ts >= 2026-11-09T08:00:00Z
ts <  2026-11-09T08:01:00Z
service = "checkout"
event = "http.request.completed"
~~~

Only these completion events form the denominator when calculating checkout's HTTP request error rate. A single request can emit many records: `request.started`, `db.query`, `payment.retry`, `request.completed`; **COUNT(all logs)** is not the number of requests.

### 5.1. Severity is not HTTP status

**level=ERROR** is a logging decision at any layer. **status_code=503** is the HTTP response outcome. They can be related, but they are not equivalent:
- A 4xx request may be logged as WARN or INFO.
- A dependency failure may be logged as ERROR even when the request succeeded via fallback.
- A request returning 503 may emit multiple ERROR logs from lower layers.

**To compute the HTTP 5xx rate, filter `status_code >= 500` on completion events.** Do not substitute `level="ERROR"` for that condition.

### 5.2. Full-text search vs. exact field filters

Full-text search on `message` is useful when exploring rare warnings or unfielded messages. However, permanent dashboards should rely on event codes and attributes:

~~~text
event="http.request.completed" AND status_code>=500
~~~

is more reliable than:

~~~text
message contains "request failed"
~~~

because prose can vary by language, template, formatter, and application version.

## 6. COUNT, GROUP BY, and error rate

Using the dataset from the Java example in section 11, after validation there are **8 valid events**:
- checkout: 6;
- inventory: 1;
- payment: 1.

`GROUP BY service` result:

~~~text
services={checkout=6, inventory=1, payment=1}
~~~

This is the **count of valid log records** per service, not necessarily the number of requests or transactions.

### 6.1. HTTP 5xx rate

There are 6 `event=http.request.completed` records for checkout:
- 4 with status 200;
- 1 with status 503;
- 1 with status 500.

Formula:

\[
\text{HTTP 5xx rate} = \frac{\text{completed requests with status >= 500}}{\text{total completed requests}} \times 100\%
\]

Therefore **2/6 × 100% = 33.33%** in the sample dataset.

~~~text
checkout_requests=6 http_5xx=2 error_rate=33.33%
~~~

**Do not extrapolate the rate of 6 test requests to production.** At low traffic, adding one record shifts the percentage dramatically.

### 6.2. Illustrative SQL

Assuming events have been normalized into a `logs` table with properly typed columns:

~~~sql
SELECT service,
       COUNT(*) AS request_count,
       SUM(CASE WHEN status_code >= 500 THEN 1 ELSE 0 END) AS error_5xx,
       100.0 * SUM(CASE WHEN status_code >= 500 THEN 1 ELSE 0 END)
             / NULLIF(COUNT(*), 0) AS error_rate_pct
FROM logs
WHERE event = 'http.request.completed'
  AND ts >= TIMESTAMP '2026-11-09 08:00:00'
  AND ts <  TIMESTAMP '2026-11-09 08:01:00'
GROUP BY service;
~~~

This is **illustrative SQL expressing the logic**, not guaranteed to run verbatim on every engine: session timezones, `TIMESTAMP` syntax, data types, and aggregate functions may differ. If a single request produces multiple completion events due to retries or duplicate logging, deduplicate by **request_id and attempt_id** according to your contract before aggregating.

## 7. Analyzing latency and p95

The checkout data has **duration_ms** values:

~~~text
[80, 110, 120, 200, 450, 920]
~~~

The mean only gives an overall picture and hides tail latency. **p95** is commonly used to inspect the tail, though multiple percentile definitions exist.

### 7.1. Nearest-rank used in the demo

After sorting the data in ascending order:

~~~text
n = 6
rank = ceil(0.95 * 6) = ceil(5.7) = 6
p95 = 6th element, 1-based
p95 = 920 ms
~~~

Thus:

~~~text
checkout_p95_nearest_rank_ms=920
~~~

**Warning:** On small sample sizes, nearest-rank p95 equals the maximum element and is highly sensitive to outliers. Some backends use **PERCENTILE_CONT** with linear interpolation, t-digest, or approximate quantiles, so values may differ. When comparing p95 between the Java demo and a storage backend, verify the **algorithm, time window, sampling, and input dataset**.

### 7.2. Grouping by the right dimensions

Do not mix checkout latency with inventory or payment latency if they represent different operations. In larger systems, slice by:
- service;
- environment;
- route_template;
- endpoint operation;
- release/service_version.

Avoid grouping dashboards by raw URLs containing IDs, `trace_id`, `request_id`, or a user identifier: each unique value creates its own bucket, causing high cardinality.

### 7.3. SQL percentiles do not always share the same definition

Example on an engine supporting ordered-set aggregates:

~~~sql
SELECT service,
       PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY duration_ms) AS p95_ms
FROM logs
WHERE event = 'http.request.completed'
  AND duration_ms IS NOT NULL
GROUP BY service;
~~~

**PERCENTILE_CONT typically uses interpolation**, which differs from nearest-rank. On some engines, you will need different syntax or an approximation function. Do not claim this query will return 920 ms on the 6-number sample dataset.

## 8. Analyzing error_type and avoiding double counting

The sample dataset contains three events with `error_type`:
1. Checkout returned 503: `GatewayTimeout`, trace `t-02`.
2. Payment authorization failed: `GatewayTimeout`, trace `t-02`.
3. Checkout returned 500: `NullPointerException`, trace `t-05`.

If you `GROUP BY error_type` across **all log records**:

~~~text
error_types_across_events={GatewayTimeout=2, NullPointerException=1}
~~~

However, **GatewayTimeout appearing twice does not mean two independent incidents**. The same failure originating in payment can be logged where it occurred and again at checkout when returning HTTP 503.

**Choose your counting unit before calculating:**
- **Event count**: number of log records.
- **Request failure count**: number of failed requests at the chosen boundary.
- **Attempt count**: number of attempts, including retries.
- **Transaction failure count**: requires a business transaction ID.
- **Trace count**: number of trace IDs matching the criteria—not equivalent to request count or incident count.

Using `COUNT(DISTINCT trace_id)` can help group by trace, but one trace can contain multiple errors; conversely, tracing or sampling can leave some events without a `trace_id`. **Do not treat DISTINCT trace_id as a universal standard for every analysis.**

### 8.1. Event code and error type serve different purposes

- **event=payment.authorization.failed**: which operation failed.
- **error_type=GatewayTimeout**: technical error/cause category.
- **reason_code=gateway_unavailable** (if your system has one): standardized business/operational reason code.
- **message**: human-readable explanation.
- **trace_id**: helps pull up related events.

Do not group by the full exception message if it contains IDs, URLs, or dynamic numbers. That easily creates thousands of buckets and obscures how many distinct error types actually exist.

## 9. Finding logs with the same trace and root-cause investigation

When filtering by **trace_id=t-02**, the program finds:

~~~text
trace=t-02 events=[checkout:http.request.completed, payment:payment.authorization.failed]
~~~

Both records share the same trace, but have different services and event codes. This correlation is useful for investigation: payment failed, and checkout returned 503.

**A Trace ID is not full distributed tracing.** Real distributed tracing also includes `span_id`, parent spans, context propagation across network/async boundaries, and a span timeline. Structured logs only correlate via existing IDs.

An investigation workflow:
1. Detect an HTTP 5xx spike from aggregates/dashboards.
2. Pick a failing completion event that has a `trace_id`.
3. Retrieve all events belonging to that `trace_id`.
4. Sort by event time, keeping clock skew in mind.
5. Inspect `error_type`, dependencies, `span_id`, and operation order.
6. Cross-check against the trace timeline, metrics, and service version.
7. Conclude the root cause based on evidence, not merely because two records share a trace ID.

If event times across services are not strictly synchronized, timestamp ordering alone does not prove causality. Collectors can also receive events out of order due to buffering and retries.

## 10. Parse errors and schema validation

Structured logs are only useful when the pipeline knows which records are **valid enough to analyze**.

### 10.1. Malformed JSON

Example:

~~~text
{not valid json}
~~~

This is not valid JSON, and Jackson cannot parse it into an object. The program increments **malformed_json**.

### 10.2. Valid JSON with invalid schema

Example:

~~~json
{"ts":"2026-11-09T08:00:06Z","service":"checkout","level":"INFO","trace_id":"t-07"}
~~~

This is valid JSON, but it is missing the required **event** field. The program increments **schema_rejected**.

### 10.3. Validation rules in the example

In the Java demo:
- **ts**, **service**, **event**, **level** must be non-blank strings.
- **ts** must be parseable by **Instant.parse**.
- For **http.request.completed**, **status_code** and **duration_ms** must be integral numbers.
- **duration_ms >= 0**.
- If JSON fails to parse, count it as `malformed_json`.
- If it parses but violates the schema, count it as `schema_rejected`.

This is basic validation for learning purposes, **not a complete production schema contract**. A real system also needs `status_code` within valid HTTP ranges, record size limits, timestamp bounds, strict field types, `schema_version`, and explicit optional/null policies.

### 10.4. Why track rejected data?

If the parser suddenly rejects 20% of events, an error-rate dashboard built on the remaining events can become severely misleading. You should track:
- Total input count.
- Malformed JSON count/rate.
- Schema-invalid count/rate.
- Ingestion lag.
- Pipeline drop/retry/queue metrics.
- A quarantine mechanism with appropriate access control and retention.

**A drop in ERROR log lines does not prove the application is healthy**: the collector may have stopped receiving logs, or a new schema may no longer match existing queries.

## 11. Java 17 + Maven + Jackson example: analyzing NDJSON

The example below is a **standalone runnable Java program** with the **Jackson Databind 2.20.1** dependency. The data is embedded in a Java text block for easy reproduction without external files. It contains **10 input lines**: 8 valid events, 1 malformed JSON line, and 1 record missing a required field.

The program:
- Parses actual JSON using `ObjectMapper`.
- Validates the schema.
- Groups by `service`.
- Filters checkout completion events.
- Computes the HTTP 5xx rate and nearest-rank p95.
- Groups `error_type` across all valid events.
- Extracts events related to trace `t-02`.

### 11.1. Directory structure

~~~text
structured-log-analysis/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── analysis/
                    └── StructuredLogAnalysisDemo.java
~~~

### 11.2. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>demo.analysis</groupId><artifactId>structured-log-analysis</artifactId><version>1.0</version>
  <properties><maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding></properties>
  <dependencies>
    <dependency><groupId>com.fasterxml.jackson.core</groupId>
      <artifactId>jackson-databind</artifactId><version>2.20.1</version></dependency>
  </dependencies>
  <build><plugins><plugin><groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId><version>3.14.0</version>
    <configuration><release>17</release></configuration>
  </plugin></plugins></build>
</project>
~~~

**Jackson is an external library outside the JDK**, not a standard JSON parser built into Java SE 17. The Maven Compiler Plugin in `pom.xml` is configured with **release=17**, targeting Java 17 compilation.

### 11.3. StructuredLogAnalysisDemo.java

~~~java
package demo.analysis;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.TreeMap;
import java.util.stream.Collectors;

public class StructuredLogAnalysisDemo {
    private static final String NDJSON = """
            {"ts":"2026-11-09T08:00:00Z","service":"checkout","event":"http.request.completed","level":"INFO","trace_id":"t-01","status_code":200,"duration_ms":80}
            {"ts":"2026-11-09T08:00:01Z","service":"checkout","event":"http.request.completed","level":"ERROR","trace_id":"t-02","status_code":503,"duration_ms":920,"error_type":"GatewayTimeout"}
            {"ts":"2026-11-09T08:00:01Z","service":"payment","event":"payment.authorization.failed","level":"ERROR","trace_id":"t-02","error_type":"GatewayTimeout"}
            {"ts":"2026-11-09T08:00:02Z","service":"checkout","event":"http.request.completed","level":"INFO","trace_id":"t-03","status_code":200,"duration_ms":110}
            {"ts":"2026-11-09T08:00:03Z","service":"checkout","event":"http.request.completed","level":"INFO","trace_id":"t-04","status_code":200,"duration_ms":120}
            {"ts":"2026-11-09T08:00:04Z","service":"checkout","event":"http.request.completed","level":"ERROR","trace_id":"t-05","status_code":500,"duration_ms":450,"error_type":"NullPointerException"}
            {"ts":"2026-11-09T08:00:05Z","service":"checkout","event":"http.request.completed","level":"INFO","trace_id":"t-06","status_code":200,"duration_ms":200}
            {"ts":"2026-11-09T08:00:05Z","service":"inventory","event":"inventory.reserved","level":"INFO","trace_id":"t-06"}
            {"ts":"2026-11-09T08:00:06Z","service":"checkout","level":"INFO","trace_id":"t-07"}
            {not valid json}
            """;

    public static void main(String[] args) throws Exception {
        ObjectMapper mapper = new ObjectMapper();
        List<JsonNode> events = new ArrayList<>();
        int inputLines = 0;
        int malformed = 0;
        int rejectedSchema = 0;
        for (String line : NDJSON.split("\\R")) {
            if (line.isBlank()) continue;
            inputLines++;
            try {
                JsonNode node = mapper.readTree(line);
                if (!valid(node)) {
                    rejectedSchema++;
                    continue;
                }
                events.add(node);
            } catch (JsonProcessingException ex) {
                malformed++;
            }
        }

        Map<String, Long> services = events.stream().collect(
                Collectors.groupingBy(n -> n.get("service").asText(), TreeMap::new,
                        Collectors.counting()));
        List<JsonNode> checkout = events.stream()
                .filter(n -> n.get("service").asText().equals("checkout"))
                .filter(n -> n.get("event").asText().equals("http.request.completed"))
                .toList();
        long errors = checkout.stream()
                .filter(n -> n.get("status_code").asInt() >= 500).count();
        List<Long> latencies = new ArrayList<>();
        checkout.forEach(n -> latencies.add(n.get("duration_ms").asLong()));
        Collections.sort(latencies);
        long p95 = latencies.get((int) Math.ceil(0.95 * latencies.size()) - 1);

        Map<String, Long> errorTypes = events.stream()
                .filter(n -> n.hasNonNull("error_type"))
                .collect(Collectors.groupingBy(n -> n.get("error_type").asText(),
                        TreeMap::new, Collectors.counting()));
        List<String> traceEvents = events.stream()
                .filter(n -> n.path("trace_id").asText().equals("t-02"))
                .map(n -> n.get("service").asText() + ":" + n.get("event").asText())
                .toList();

        System.out.printf("input_lines=%d accepted=%d malformed_json=%d schema_rejected=%d%n",
                inputLines, events.size(), malformed, rejectedSchema);
        System.out.println("services=" + services);
        System.out.printf(Locale.ROOT,
                "checkout_requests=%d http_5xx=%d error_rate=%.2f%%%n",
                checkout.size(), errors, 100.0 * errors / checkout.size());
        System.out.println("checkout_latencies_ms=" + latencies);
        System.out.println("checkout_p95_nearest_rank_ms=" + p95);
        System.out.println("error_types_across_events=" + errorTypes);
        System.out.println("trace=t-02 events=" + traceEvents);
    }

    private static boolean valid(JsonNode n) {
        if (n == null || !n.isObject()) return false;
        for (String name : List.of("ts", "service", "event", "level")) {
            if (!n.hasNonNull(name) || !n.get(name).isTextual()
                    || n.get(name).asText().isBlank()) return false;
        }
        try { Instant.parse(n.get("ts").asText()); }
        catch (RuntimeException ex) { return false; }
        if (n.get("event").asText().equals("http.request.completed")) {
            return n.path("status_code").isIntegralNumber()
                    && n.path("duration_ms").isIntegralNumber()
                    && n.get("duration_ms").asLong() >= 0;
        }
        return true;
    }
}
~~~

This is a **complete runnable program** with the provided `pom.xml`. It uses Java text blocks, `Stream.toList`, and `java.time.Instant`, so it requires Java 17+. The sample events contain no real personal data.

### 11.4. Build and run

From the directory containing `pom.xml`:

~~~bash
mvn -q -B package dependency:build-classpath -Dmdep.outputFile=classpath.txt
~~~

After Maven downloads dependencies and compiles, run with a Java 17 or newer JVM.

**Linux/macOS:**

~~~bash
java -cp "target/classes:$(cat classpath.txt)" demo.analysis.StructuredLogAnalysisDemo
~~~

**Windows PowerShell:**

~~~powershell
$deps = (Get-Content .\classpath.txt -Raw).Trim()
java -cp "target\classes;$deps" demo.analysis.StructuredLogAnalysisDemo
~~~

**Classpath separator:** typically **:** on Unix and **;** on Windows. Do not mix PowerShell and Bash shell syntax. To run directly with `javac`, you also need to provide Jackson dependencies on both compile and runtime classpaths; Maven handles this for you.

### 11.5. Verified stdout

The program compiled and ran successfully:

~~~text
input_lines=10 accepted=8 malformed_json=1 schema_rejected=1
services={checkout=6, inventory=1, payment=1}
checkout_requests=6 http_5xx=2 error_rate=33.33%
checkout_latencies_ms=[80, 110, 120, 200, 450, 920]
checkout_p95_nearest_rank_ms=920
error_types_across_events={GatewayTimeout=2, NullPointerException=1}
trace=t-02 events=[checkout:http.request.completed, payment:payment.authorization.failed]
~~~

### 11.6. Explaining the output

**input_lines=10:** the program read 10 non-blank lines.

**accepted=8:** eight lines were JSON objects passing the declared schema rules.

**malformed_json=1:** the line **{not valid json}** had a syntax error and was caught as `JsonProcessingException`.

**schema_rejected=1:** one valid JSON object was missing the **event** field.

**services:** `GROUP BY service` counts valid events, which does not automatically equal request count.

**checkout_requests=6:** filtered to `service=checkout` and `event=http.request.completed`. Two statuses are in the 5xx class, giving an error rate of 33.33%.

**checkout_latencies_ms:** the list of six durations sorted in ascending order.

**checkout_p95_nearest_rank_ms=920:** p95 rank = 6/6 under the nearest-rank algorithm.

**error_types_across_events:** counts occurrences of `error_type` across all events, where `GatewayTimeout` may be logged in two services within the same trace.

**trace=t-02:** outputs the two related events from checkout and payment.

### 11.7. Intentional limitations of the demo

This example is for learning, not a production pipeline:
- NDJSON data is held in memory rather than streamed from large files.
- There are no limits on maximum record size, nesting depth, or field count.
- It does not validate `status_code` within 100–599 or check `schema_version`.
- If there are no checkout completion events, the p95 and error-rate calculations need empty-list handling.
- It does not filter events by a time window in code; the sample data spans a short interval.
- It does not deduplicate by `event_id`/`request_id`.
- It does not handle sampling, late arrivals, clock skew, or distributed storage.
- It does not enforce audit, access-control, or sensitive-data policies.

Use this pattern to understand the fundamentals, then build validation and pipelines tailored to your real application contract.

## 12. Dashboards, alerts, and investigation queries

Commonly needed analyses:

| Purpose | Metric / query | What to watch out for |
| --- | --- | --- |
| Request throughput | COUNT completion events per minute | Log sampling/drops will undercount |
| HTTP 5xx rate | 5xx completions / all completions | Correct denominator and time window |
| Tail latency | p95/p99 duration_ms | Numeric type, unit, percentile algorithm |
| Top error types | COUNT by error_type | One incident may produce multiple records |
| Parser health | malformed/schema_rejected rate | Do not drop invalid records silently |
| Ingestion health | ingest lag, received/dropped | Missing logs do not mean zero errors |
| Trace investigation | filter trace_id | May span multiple services; does not prove causality alone |
| Deployment comparison | compare versions/windows | Must control for traffic mix |

### 12.1. Alerting requires sufficient data

For example, an error-rate 5xx alert exceeding a threshold should only fire when:
- There are enough requests in the time window per policy.
- Ingestion data is reasonably complete.
- No schema migration is breaking the query.
- The time window and sample size are consistent.
- The signal persists long enough to avoid paging on a single request.

For high-accuracy SLIs/SLOs, metric counters and histograms are usually more reliable than logs that may be sampled or rate-limited. Logs help **dig into root causes**, but do not automatically guarantee full coverage of every request.

### 12.2. Comparing before and after a deployment

Select the same `route_template`, `service`, `environment`, and time windows with sufficient samples before and after. Compare throughput, 5xx rate, p95, and `error_type`; then inspect representative traces. If the traffic mix or dependencies changed, do not conclude causality from the deploy timestamp alone.

### 12.3. Monitor the ingestion pipeline in parallel

If error log counts drop to zero because the collector stopped working, a dashboard can create the illusion that the system recovered. Monitor log ingestion volume, rejected counts, data freshness, retries, queues, and collector health.

## 13. Cardinality, cost, and scalability

**Cardinality** is the number of distinct values for a field:
- `service`: typically low;
- `event`: typically moderate when standardized;
- `route_template`: much more stable than `raw_url`;
- `error_type`: use standardized names to avoid many variants;
- `trace_id`, `request_id`: typically very high.

In log storage, keeping `trace_id` lets you look up a specific request. However, **grouping by trace_id** on a dashboard can create millions of buckets, consuming excessive memory and compute. In metrics systems, using a trace ID as a label is a classic high-cardinality anti-pattern.

Example:

~~~text
raw_url = /orders/ORD-42/items/IT-001
route_template = /orders/{orderId}/items/{itemId}
~~~

`route_template` lets you group by functional endpoint without creating a new value for every order. Always take route metadata from the framework rather than parsing raw URLs that may contain sensitive data.

### 13.1. Field indexing

Not every field needs the same indexing strategy. Consider the workload:
- `service`, `event`, `ts`, `status_code`, `environment`, and `error_type` are queried frequently;
- `request_id`/`trace_id` are used for drill-down lookups;
- `message` may need full-text search;
- rare or large fields may need separate retention or index policies.

Some backends use inverted indexes; others use columnar storage or partition scans. **Do not apply a single index design blindly to every backend**; storage and query costs depend on the engine and retention policy.

## 14. Relationship to Java logging frameworks

Downstream structured log analysis **does not depend on** a single logging API.

**JUL:** `java.util.logging.Logger` creates a `LogRecord`. The default `ConsoleHandler`/`SimpleFormatter` outputs text and does not automatically produce a JSON schema with fields like the example. Structured output requires a properly designed `Formatter`/`Handler` or collector transformation.

**SLF4J:** is a facade; parameterized logging such as `logger.info("id={}", id)` may only produce a text message and does not guarantee a separate JSON `id` field. You need a suitable encoder/provider or structured arguments.

**Log4j2:** supports `Message`, `ThreadContext`, `Layout`, and `Appender`. To emit schema-compliant JSON events, choose JSON Template Layout or a compatible structured output option, name fields consistently, preserve exceptions/context, and test against your backend.

**OpenTelemetry:** has its own log record data model including timestamp, observed timestamp, severity, body, attributes, and Resource/Instrumentation Scope, and can attach trace/span IDs. The example schema uses educational names like **ts, status_code, duration_ms**; do not treat them as the full OTel conventions.

Regardless of which API the producer uses, the analytical goal is a **unified schema** at query time. Different services can be normalized at the collector if rules are clear and transformation errors are monitored.

## 15. Data security in structured logs

Structured data is easier to search, which makes it even more critical to control what enters it:
- Do not log passwords, OTPs, session cookies, API keys, private keys, or access/refresh tokens.
- Do not log full payment card details or sensitive payloads.
- Do not let exception messages or raw URL query strings leak secrets.
- Use field allowlists, masking/redaction, retention limits, and policy-based access control.
- The JSON encoder must escape quotes, newlines, backslashes, and control characters to prevent log injection.
- Do not use user input as arbitrary field/key names.
- Test Unicode/Vietnamese text through both the serializer and the collector.

Example **to avoid**:

~~~java
// Illustrates an anti-pattern in a method with a rawInput variable.
String line = "{\"userInput\":\"" + rawInput + "\"}";
~~~

This snippet is not a standalone program. If `rawInput` contains quotes or newlines, it can break JSON or inject forged records. Use a JSON serializer such as Jackson or a dedicated logging encoder, and validate what data is permitted before logging.

### 15.1. Retention and auditing

Structured logs do not automatically guarantee durability, strict ordering, immutability, or mandatory retention. If an event type serves as audit or security evidence, it requires dedicated storage, access controls, integrity guarantees, delivery guarantees, and policies; do not treat a `ConsoleAppender` or a general-purpose collector as tamper-evident evidence.

## 16. Common analysis mistakes

**Mistake 1 — Counting all ERROR lines and calling it the request error rate.** One request can emit multiple ERROR logs. Choose a completion event and proper denominator.

**Mistake 2 — `status_code` is a string in one service and a number in another.** Mappings and aggregations can break. Standardize types and validate.

**Mistake 3 — Mixing duration seconds with milliseconds.** Percentiles can be off by a factor of a thousand. Encode units in field names or contracts and test boundaries.

**Mistake 4 — Dropping malformed records silently.** Track parser/schema rejection counts, quarantine appropriately, and alert on data quality.

**Mistake 5 — Using `COUNT error_type` to infer incident count.** The same failure can be logged in both checkout and payment, as in trace `t-02`.

**Mistake 6 — Comparing p95 across systems with different algorithms.** Nearest-rank, interpolation, and approximations do not always match. Document the method.

**Mistake 7 — Using sampled log counts as exact counters.** Events may be missing; account for sampling rates or use metrics.

**Mistake 8 — Confusing event time and ingest time.** Late arrivals and clock skew distort windowed counts without a clear policy.

**Mistake 9 — Renaming fields without migrating dashboards.** Schema evolution must include query updates and tests.

**Mistake 10 — Grouping by `raw_url` or `trace_id` system-wide.** High cardinality creates excessive buckets and high cost.

**Mistake 11 — Treating two events in the same trace as definite causality.** Correlation aids investigation but does not replace a trace timeline or proof.

**Mistake 12 — Wrapping a message in JSON while still parsing it with regex.** You need real typed fields, not just an object with a `message` field.

**Mistake 13 — Treating `level=ERROR` as HTTP 500.** Severity is a logging policy; HTTP status is a request outcome.

**Mistake 14 — Assuming a drop in error logs means the application has recovered.** Check ingestion health, sampling, parser rejections, and metrics.

## 17. Practice exercises

### Exercise A — Add a successful request

Add a checkout record with status 200 and `duration_ms=90` to the NDJSON. Recompute the 5xx rate and nearest-rank p95. Explain why with small sample sizes, p95 can still equal the maximum.

### Exercise B — Change the service filter

Change the filter from `checkout` to `payment`. `payment` has no `event=http.request.completed` in the dataset. Add a **zero records** handling branch before computing p95/error rate so you do not access an empty list.

### Exercise C — Time windows

Choose `[08:00:00Z, 08:00:03Z)` and `[08:00:03Z, 08:00:06Z)`, and parse `ts` with `Instant` to filter. Verify that boundary events belong to only one window.

### Exercise D — Test parser/schema validation

Add a syntactically invalid JSON string and an event with `duration_ms="450"` (String). Verify that `malformed_json` and `schema_rejected` increment as expected.

### Exercise E — Trace correlation

Add an inventory event with `trace_id=t-02` and a `span_id` field; filter and sort events by `ts`. Compare grouping by `trace_id`, `request_id`, and `service`.

### Exercise F — SQL by status

Write a `GROUP BY service, status_code` query on `event=http.request.completed`. Check 200, 500, and 503, and demonstrate why `COUNT(all ERROR records)` does not equal failed HTTP requests.

### Exercise G — Schema review

Design a **job.completed** event with duration, outcome, retry_count, dependency, request_id, and schema_version. Specify required fields, optional fields, numeric types, and how to handle a service that has not yet adopted the new version.

### Exercise H — Diagnose a dashboard missing data

A deployment renames `duration_ms` to `latency_ms`. Identify why the p95 dashboard drops to null/0, and propose a migration plan and test coverage.

### Exercise I — Redaction and cardinality

A team logs raw URLs containing tokens and groups by `userId`. Propose a `route_template`, an allowlist of fields, retention settings, and a controlled ad-hoc investigation query.

## 18. Self-assessment questions and answers

**1. Is a JSON object with only a `message` field enough to compute duration statistics?**  
No. If duration is embedded in message text, you still need brittle string parsing; a dedicated numeric field is required.

**2. How does NDJSON differ from a JSON array?**  
NDJSON has one JSON object per line, making it convenient for streaming; multiple lines are not a single JSON document.

**3. When calculating the HTTP 5xx rate, why filter only request completion events?**  
So the denominator represents HTTP requests with an outcome, rather than every logging event emitted during a request.

**4. In the example, what is checkout's 5xx rate?**  
**2/6 × 100% = 33.33%.**

**5. What is the nearest-rank p95 of `[80, 110, 120, 200, 450, 920]`?**  
**920 ms**, because `ceil(0.95 × 6) = 6`. Backends using interpolation may return a different value.

**6. Does `GatewayTimeout` appearing twice mean there were 2 incidents?**  
Not necessarily. Both checkout and payment logged errors belonging to trace `t-02`.

**7. What is the difference between `malformed_json` and `schema_rejected`?**  
Malformed means the input cannot be parsed as JSON; schema-rejected means valid JSON that is missing required fields or has invalid field types per the contract.

**8. Does `trace_id` alone create a complete distributed trace?**  
No. It is only a correlation key; tracing requires spans, instrumentation, and context propagation.

**9. Can sampled log counts be used as an exact SLI?**  
Not by default. Sampling or drops leave missing data; you need sampling weights or dedicated metrics.

**10. Why should `status_code` be a number?**  
To support range filters and aggregations properly, and to avoid text parsing and mapping conflicts.

**11. Should you group by `request_id` for an overview dashboard?**  
Usually no, due to high cardinality. Use IDs for drill-downs, and group overview dashboards by `service`, `event`, or `route_template`.

**12. What happens if you change a schema without updating dashboards?**  
Queries miss data or encounter type mismatches, skewing metrics and alerts.

**13. Are `level=ERROR` and HTTP `status >= 500` the same thing?**  
No. One is a logging severity; the other is a protocol-level response outcome.

**14. Why should you monitor malformed records?**  
Because the pipeline may drop invalid events, making error charts look artificially low.

## 19. References

- Java 17 Instant: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Instant.html
- Java 17 Streams: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html
- Jackson Databind: https://github.com/FasterXML/jackson-databind
- JSON Lines: https://jsonlines.org/
- OpenTelemetry Log Data Model: https://opentelemetry.io/docs/specs/otel/logs/data-model/
- OpenTelemetry Semantic Conventions: https://opentelemetry.io/docs/specs/semconv/
- Apache Log4j2 JSON Template Layout: https://logging.apache.org/log4j/2.x/manual/json-template-layout.html

When implementing in practice, select Java/Jackson/backend versions and field conventions that match your actual runtime; the schema in this lesson is a reproducible educational example.

## 20. Key takeaways

**Structured log analysis does not start with a query—it starts with the right event schema.** With a stable schema, typed fields, and correlation IDs, you can filter, group, and measure error rates and p95 without depending on free-form message text. Every result, however, must explicitly account for **the counting unit, denominator, percentile algorithm, time window, and data quality**.

In the Java 17 example, a small pipeline processes **10 input lines → 8 valid events → detects 2 kinds of data errors → GROUP BY service → 5xx rate → nearest-rank p95 → error_type → trace correlation**. In production, combine log analysis with metrics and traces, monitor ingestion health, and manage schema evolution, sampling, cardinality, and data security to reach reliable operational conclusions.
