# Searching Logs by Correlation ID in Java: From Log Files to Centralized Systems

When a user reports a failed transaction, a Java system may have emitted thousands of logs from many requests, threads, and services. If you only search for keywords like `ERROR` or `timeout`, the results are usually too broad. **Searching logs by correlation ID** helps trace events belonging to **the same request or operation**, using a stable key attached to each log event.

Example:

```text
2026-11-09T10:00:00Z INFO  correlationId=corr-42 event=request_started
2026-11-09T10:00:02Z WARN  correlationId=corr-42 event=dependency_retry
2026-11-09T10:00:03Z ERROR correlationId=corr-42 event=payment_failed
2026-11-09T10:00:04Z INFO  correlationId=corr-77 event=other_request
```

With `correlationId=corr-42`, an investigator wants to retrieve **the first three events**, not the entire service log or events that happen to contain the string `corr-42` in their message. The data above is illustrative, not the output of a specific backend.

This lesson belongs to the **Correlation ID** group. The focus is on **lookup methods** across text logs, JSONL, PowerShell, centralized logging systems, and Java 17; how to preserve stack traces of matched events; searching in rotated files; checking for missing IDs due to MDC, executors, or service boundaries; and security rules when querying logs.

## 1. Correlation ID, Request ID, and Trace ID

A **Correlation ID** is an identifier used by an organization to link multiple events within the scope of a single operation. Java and SLF4J **do not require** using the field name `correlationId`. An application may use `requestId`, `correlation_id`, or another name according to its logging contract.

An example structured event:

```json
{
  "timestamp": "2026-11-09T10:00:03.000Z",
  "level": "ERROR",
  "service": "payment-service",
  "correlationId": "corr-42",
  "logger": "com.example.PaymentService",
  "event": "payment_failed",
  "errorCode": "UPSTREAM_TIMEOUT",
  "message": "Payment dependency timed out"
}
```

| Field | Common Meaning | Notes |
| --- | --- | --- |
| `correlationId` | Links events in a business/request chain as defined by the project | No universal mandatory format |
| `requestId` | Identifies a single HTTP/API request | May change across hops if not propagated |
| `traceId` | Identifies an entire distributed trace | Not implicitly equal to correlation ID |
| `spanId` | Identifies a single span within a trace | Should not be used alone to represent the entire trace |
| `thread` | The Java thread emitting the event | A single worker may execute multiple requests |
| `errorCode` | Error classification | Different requests can share the same error code |
| `timestamp` | Time the event was recorded | Must know timezone, precision, and the index's time field |

**A correlation ID is not necessarily a trace ID.** In W3C Trace Context, a trace ID is typically represented as 32 valid hex characters and a span ID as 16 valid hex characters. A business ID may follow a different convention, such as `corr-42`. Do not assume from the word "ID" that all ID types are interchangeable.

The field should be logged **separately from the message** so search tools can compare by **field value** instead of substring matching.

## 2. Search Workflow Before Opening Large Files

A structured investigation workflow:

1. **Obtain the exact ID** from an error response, API response header, trace UI, or a trusted initial log. Do not guess the ID solely from a username or timestamp.
2. **Know the actual field name:** `correlationId`, `requestId`, `traceId`, `mdc.correlationId`, or the name mapped by the collector.
3. **Restrict the time range** based on the incident timestamp and timezone to avoid scanning the entire retention window.
4. **Restrict the source** by environment, service, deployment, pod, or tenant that you are authorized to access.
5. **Perform an exact match**, keeping both initial/final events and non-ERROR events.
6. **Expand along the processing flow:** gateway → service → worker/queue → downstream.
7. **Read the full log**, including message, exception/`Throwable`, stack trace, and cause chain.
8. **Cross-reference metrics/tracing** before concluding the root cause.

Keep in mind that **an ID is searched within a scope**. A valid value in service A that does not appear in service B may be due to missing metadata propagation over HTTP or an executor, rather than proving service B never received the work.

### Prefix Matching Risk

```text
INFO requestId=req-42 event=start
INFO requestId=req-420 event=unrelated
WARN requestId=req-42 event=retry
```

Searching for the literal `requestId=req-42` will match **`req-420` as well** because the first string is a prefix of the second. In search systems, you must distinguish between **substring match** and **exact field match**. This is one of the most common sources of false positives during an investigation.

## 3. Searching in Text Files on Linux/macOS

Assume you have identified `logs/application.log` as the file for the service under investigation.

### Quick Literal Search

```bash
grep -n -F 'correlationId=corr-42' logs/application.log
```

`grep -F` treats the pattern as a literal string, and `-n` adds physical line numbers. This is fast but can still match `corr-420` or a message saying "related to corr-42". **Do not treat this as an exact field match.**

### Searching with Field Boundaries

If the text log convention separates fields with whitespace:

```bash
grep -n -E '(^|[[:space:]])correlationId=corr-42([[:space:]]|$)' logs/application.log
```

In the assumed format, the regex requires whitespace or start-of-line before the field and whitespace or end-of-line after the ID. This avoids matching `corr-420`. However, if the message itself contains `correlationId=corr-42`, `grep` can still pull it in; this **is not a structured parser**. Do not arbitrarily concatenate raw user input containing regex or shell characters into commands.

### Viewing Surrounding Lines

```bash
grep -n -C 5 -F 'correlationId=corr-42' logs/application.log
```

With GNU grep, `-C 5` displays five lines before and after each match. This helps reveal part of an exception, but it does not guarantee a complete long stack trace and may pull in events with different IDs.

### Following Actively Written Logs

```bash
tail -n 50 -F logs/application.log
```

On GNU coreutils, `-F` follows the **file name** and is useful when the file is renamed or recreated during rotation. It is not a tool for long-term historical search: previously rotated records may reside in archive files, and events not yet flushed by the appender will not appear on disk yet.

### Rotated or Compressed Files

Example:

```text
logs/application.log
logs/application.log.1
logs/application.2026-11-08.log.gz
```

Searching inside a `.gz` archive when you have access:

```bash
gzip -dc logs/application.2026-11-08.log.gz | grep -n -F 'correlationId=corr-42'
```

`gzip -dc` decompresses to stdout without overwriting the archive file. If you need to preserve evidence or reproduce results, record the **source file name**, query timestamp, and scope read. `grep -n` in this example numbers lines in the decompressed stream, not in the binary compressed file.

Text files with multi-line stack traces will cause `wc -l` or grep match counts to **differ from the number of log events**. You must know the actual formatter to group them properly.

## 4. Exact Search in JSON Lines with jq

With **JSONL/NDJSON**, each physical line must contain a complete JSON object. Example `logs/application.jsonl` file:

```json
{"timestamp":"2026-11-09T10:00:00Z","level":"INFO","correlationId":"corr-42","event":"start"}
{"timestamp":"2026-11-09T10:00:01Z","level":"INFO","correlationId":"corr-420","event":"unrelated"}
{"timestamp":"2026-11-09T10:00:02Z","level":"WARN","correlationId":"corr-42","event":"retry"}
```

If `jq` is installed (not part of the JDK):

```bash
jq -c --arg id 'corr-42' 'select(.correlationId == $id)' logs/application.jsonl
```

`--arg` passes the ID as a string variable in `jq`; `==` compares the **property value**. The `corr-420` event is not selected. If the schema uses `requestId`, adjust the property path to the actual field. Another encoder might store:

```json
{"context":{"correlationId":"corr-42"},"event":"start"}
```

Then the corresponding query is:

```bash
jq -c --arg id 'corr-42' 'select(.context.correlationId == $id)' logs/application.jsonl
```

Filter further by severity:

```bash
jq -c --arg id 'corr-42' 'select(.correlationId == $id and .level == "ERROR")' logs/application.jsonl
```

Count matched events without using `jq -s` (*slurp*) to load the entire file into an array:

```bash
jq -c --arg id 'corr-42' 'select(.correlationId == $id)' logs/application.jsonl | wc -l
```

This count relies on the contract that each matched output is one JSON object per line, and assumes there are no malformed records. For large datasets, querying on an indexed log platform is better than downloading files to a workstation. Do not write custom `String.split(",")` or generic regexes to parse JSON: messages can contain commas, double quotes, nested JSON, or escaped newlines.

## 5. Searching on Windows PowerShell

For text files:

```powershell
Select-String -LiteralPath 'C:\logs\application.log' -SimpleMatch -Pattern 'correlationId=corr-42'
```

Similar to `grep -F`, it performs a substring search and does not parse fields. For whitespace-delimited formats:

```powershell
Select-String -LiteralPath 'C:\logs\application.log' -Pattern '(^|\s)correlationId=corr-42(\s|$)'
```

For JSONL with strictly one object per line, you can parse and compare:

```powershell
Get-Content -LiteralPath 'C:\logs\application.jsonl' | ForEach-Object { $_ | ConvertFrom-Json } | Where-Object { $_.correlationId -ceq 'corr-42' } | ConvertTo-Json -Compress
```

`-ceq` performs a case-sensitive comparison; standard `-eq` is case-insensitive for strings. Use the comparison operator matching your ID contract, especially when IDs contain uppercase letters.

The example assumes all lines are valid JSON. If a line is malformed, `ConvertFrom-Json` may throw an error; do not treat skipped records as proof that "the ID does not exist". For very large files, the PowerShell pipeline can be slow; consider streaming reads, time filtering, or centralized logging.

## 6. Querying Centralized Logging Systems

### Elasticsearch/Kibana

If the index has a `correlationId` field of type `keyword`, a Query DSL might look like:

```json
{
  "query": {
    "bool": {
      "filter": [
        {"term": {"correlationId": "corr-42"}},
        {"range": {"@timestamp": {
          "gte": "2026-11-09T09:55:00Z",
          "lte": "2026-11-09T10:05:00Z"
        }}}
      ]
    }
  }
}
```

`term` searches for the exact indexed term according to the mapping. If the field is analyzed `text`, results may differ from raw string comparison. Some indices have a `correlationId.keyword` subfield which can be used; **do not assume the subfield exists**. Check the mapping first.

A KQL example if the index has that subfield:

```text
correlationId.keyword : "corr-42" and service.name : "payment-service"
```

Do not assume KQL/full-text search performs an exact match by default if the field is not mapped as `keyword`.

### Grafana Loki (LogQL)

Assume the stream has a `service` label and the log body is JSON:

```logql
{service="payment-service"} | json | correlationId="corr-42"
```

The pipeline selects the stream, parses JSON, and filters the field. For unparsed text logs:

```logql
{service="payment-service"} |= "correlationId=corr-42"
```

The `|=` operator performs a substring search and can match `corr-420`. Loki stream labels require cardinality consideration: **correlation IDs have high cardinality and should generally not be used as per-request stream labels**. Narrow streams by service/environment/time and filter the ID in the body or structured metadata.

### Why Might a Dashboard Return No Results?

- The field was **renamed** by the collector to `request.id` or `mdc.correlationId`.
- The index lacks an exact-match type; the query uses the wrong field path.
- `@timestamp` is mapped from ingestion time instead of event time, or the dashboard is in the wrong timezone/time window.
- The backend filtered out DEBUG/INFO before writing; the log was never generated.
- The event is on a different instance/service or in an archive.
- The collector is lagging, dropping, truncating, or failing to parse JSON records.
- The querying user's permissions do not cover all services or tenants.
- Retention has expired.

Therefore, **"not found" does not automatically prove the request never ran**. Check each layer before drawing conclusions.

## 7. Standalone Java 17 Example: Exact requestId Match While Preserving Stack Traces

In text files, `Throwable`/stack traces are typically written across multiple lines. Lines starting with `at ...` or `Caused by: ...` do not contain the ID, so single-line search commands lose exception context. This example uses a small parser for an **explicit sample format**, streams the file, and prints **all matched events**, including continuation lines.

No Maven or external libraries beyond the JDK are needed. The program creates a **temporary directory and file**, writes sample data, reads it, and deletes **only the resources created by the demo itself**. It does not read, write, or delete production logs.

### 7.1. Save as `ReadLogByCorrelationId.java`

```java
import java.io.BufferedReader;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public final class ReadLogByCorrelationId {
    // Match only headers of the sample format: timestamp, level, requestId.
    private static final Pattern HEADER = Pattern.compile(
            "^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}Z "
            + "(?:TRACE|DEBUG|INFO|WARN|ERROR) "
            + "requestId=([A-Za-z0-9_-]+)(?:\\s|$)");

    private ReadLogByCorrelationId() {
    }

    public static void main(String[] args) throws IOException {
        String targetId = "req-42";

        Path dir = Files.createTempDirectory("correlation-demo-");
        Path file = dir.resolve("application.log");

        try {
            String sample = String.join("\n",
                    "2026-11-09T10:00:00Z INFO requestId=req-42 event=request_started",
                    "2026-11-09T10:00:01Z INFO requestId=req-420 event=other_request",
                    "2026-11-09T10:00:02Z WARN requestId=req-42 event=dependency_retry",
                    "2026-11-09T10:00:03Z ERROR requestId=req-42 event=payment_failed",
                    "java.lang.IllegalStateException: timeout",
                    "    at com.example.PaymentGateway.call(PaymentGateway.java:42)",
                    "Caused by: java.net.SocketTimeoutException: read timed out",
                    "2026-11-09T10:00:04Z INFO requestId=req-77 event=unrelated"
            ) + "\n";

            Files.writeString(
                    file, sample, StandardCharsets.UTF_8,
                    StandardOpenOption.CREATE_NEW);

            int matchedEvents = 0;
            int continuationLines = 0;
            boolean matchedCurrentEvent = false;

            System.out.println("query=requestId=" + targetId);

            try (BufferedReader reader =
                    Files.newBufferedReader(file, StandardCharsets.UTF_8)) {
                String line;
                while ((line = reader.readLine()) != null) {
                    Matcher m = HEADER.matcher(line);

                    if (m.find()) {
                        // New header: check exact ID match.
                        matchedCurrentEvent = targetId.equals(m.group(1));
                        if (matchedCurrentEvent) {
                            matchedEvents++;
                            System.out.println(line);
                        }
                    } else if (matchedCurrentEvent) {
                        // Keep continuation Throwable/stack trace lines.
                        continuationLines++;
                        System.out.println(line);
                    }
                }
            }

            System.out.println("matchedEvents=" + matchedEvents);
            System.out.println("continuationLines=" + continuationLines);
        } finally {
            Files.deleteIfExists(file);
            Files.deleteIfExists(dir);
        }
    }
}
```

### 7.2. Run with JDK 17+

```bash
javac -encoding UTF-8 ReadLogByCorrelationId.java
java ReadLogByCorrelationId
```

**Exact stdout on success:**

```text
query=requestId=req-42
2026-11-09T10:00:00Z INFO requestId=req-42 event=request_started
2026-11-09T10:00:02Z WARN requestId=req-42 event=dependency_retry
2026-11-09T10:00:03Z ERROR requestId=req-42 event=payment_failed
java.lang.IllegalStateException: timeout
    at com.example.PaymentGateway.call(PaymentGateway.java:42)
Caused by: java.net.SocketTimeoutException: read timed out
matchedEvents=3
continuationLines=3
```

**Stderr:** the program does not actively write to stderr on success. If permissions to create/delete temporary files are missing or an I/O error occurs, it may terminate with an exception.

### 7.3. Output Analysis

- `req-42` has **3 events**: `request_started`, `dependency_retry`, and `payment_failed`.
- `req-420` is a different ID despite sharing a prefix; comparing with `String.equals` ensures it is **not mistakenly included**.
- `req-77` is excluded.
- The three lines following the ERROR event (exception, stack frame, `Caused by`) are preserved as **3 continuation lines**.
- When encountering a new header, the parser resets `matchedCurrentEvent` so lines from other requests are not pulled in.
- `BufferedReader` avoids loading the entire file into memory; `Files.deleteIfExists` cleans up only the created demo files.

**Intentional limitations:** the regex only matches timestamps in `yyyy-MM-ddTHH:mm:ssZ` format, level, and `requestId` in specific positions. It does not support logs with milliseconds, non-UTC offsets, interleaved logger/thread names, or JSON. If a new header fails to match the regex, the program may treat it as a continuation of the previous event. If a message contains text mimicking a header, the parser may reset prematurely. Do not treat this as a production parser for arbitrary formats.

Additionally, an **extremely long line** can still cause `readLine()` to consume significant memory; live files may change while being read; file rotation or multiple writers can break event boundaries. For production, prefer compact JSONL/structured encoders and log collectors with verified schemas or multiline rules.

## 8. Searching in Containers and Kubernetes

Containerized applications may write only to stdout/stderr. For a specific pod and container:

```bash
kubectl logs pod/payment-service-abc123 -c app --since=30m
```

Pod and container names are illustrative only. If a container restarted and the runtime still retains the previous instance's logs:

```bash
kubectl logs pod/payment-service-abc123 -c app --previous
```

`--previous` is not a long-term storage mechanism. Rotation, retention, and pod replacement can cause old logs to disappear. A single request may traverse multiple instances; do not assume logs from one pod cover the entire operation.

In production, use a centralized logging platform to search across all relevant services by ID, time window, and authorized scope. A deployment log command may not automatically aggregate all replicas as expected.

## 9. Why Are Correlation IDs Lost Across Threads or Services?

To search by ID, logs must first **be tagged with the right ID**.

With SLF4J + an MDC-capable backend:

```java
// Fragment: LOG, correlationId, and handleRequest() already exist.
org.slf4j.MDC.put("correlationId", correlationId);
try {
    LOG.info("event=request_received");
    handleRequest();
} finally {
    org.slf4j.MDC.remove("correlationId");
}
```

The snippet above illustrates a single request scope. If an outer scope already held a key with the same name, `remove` does not restore the previous value; you need proper scope snapshot/restore. SLF4J's `MDC.getCopyOfContextMap()` helps capture a snapshot of the map on the current thread.

In Logback, a pattern might use:

```xml
<!-- Fragment inside Logback <encoder> -->
<pattern>%d{HH:mm:ss.SSS} %-5level correlationId=%X{correlationId} %logger - %msg%n</pattern>
```

However, **the pattern does not generate the ID itself**. If `MDC.put` was not called, the field may be empty. If a JSON encoder nests MDC under `mdc`, queries must use the path `mdc.correlationId`, not assume `correlationId` is at the root.

Boundaries where IDs are commonly lost:

- **HTTP ingress:** validate IDs from headers like `X-Correlation-ID` or generate one server-side when needed. Do not blindly trust client-supplied IDs.
- **HTTP egress:** propagate metadata to downstream services per contract; do not confuse a correlation ID with an authorization token.
- **Executor/CompletableFuture:** MDC is typically thread-bound. Capture at submission time, install on the worker thread, and restore the previous map in `finally`. Thread pools reuse workers, so stale IDs must not leak into subsequent requests.
- **Message broker/background job:** pass appropriate metadata in the message, attach it to the consumer scope, and clean up after processing.
- **Distributed tracing:** use `traceparent`/OpenTelemetry instrumentation to find `traceId` when available; do not assume trace ID and correlation ID are identical.

**MDC data is observability metadata**, not a security context or authorization mechanism. Knowing a correlation ID does not grant a party permission to view or act on any request.

## 10. Building a Timeline and Reading Results

Suppose a query returns:

```text
10:00:00.000 gateway       INFO  corr-42 request_received
10:00:00.031 checkout      INFO  corr-42 price_validated
10:00:00.073 payment       INFO  corr-42 payment_started
10:00:01.204 payment       WARN  corr-42 upstream_retry attempt=1
10:00:02.480 payment       ERROR corr-42 upstream_timeout
10:00:02.510 gateway       ERROR corr-42 response_failed status=503
```

This is an illustrative timeline. It suggests a slow dependency and that the gateway returned an error, but **does not prove causality on its own** without cross-referencing tracing, stack traces, `errorCode`, and metrics.

Investigate in order: find request ingress → find processing start → check WARN/retries → find final exception and cause chain → determine response/outcome → cross-reference services, queues, and traces. Keep in mind:

- **Timestamps may drift between nodes** due to clock skew or timezone differences.
- **Ingestion time** may lag behind event time when backends/collectors are asynchronous.
- Events may be filtered by level or dropped due to queue/retention limits.
- Logs sharing a correlation ID should be analyzed by **service, instance, attempt, and event type**, not merely sorted as plain text.

## 11. Troubleshooting ID-Based Log Searches

| Symptom | Possible Cause | Investigation Step |
| --- | --- | --- |
| Searching `req-42` also returns `req-420` | Substring matching used | Use exact field match, keyword query, or regex with boundaries |
| Querying `correlationId` returns empty | Schema uses `requestId` or `mdc.correlationId` | Inspect source JSON and field mappings |
| ID appears only at gateway | Downstream does not propagate header | Check HTTP ingress/egress propagation |
| Worker is missing ID | MDC not propagated across executor | Capture/install/restore per task |
| Request B carries A's ID | Context not cleared on reused thread | Restore in `finally`, test isolation |
| `traceId` differs from correlation ID | Two ID types have different semantics | Look up the defined mapping |
| Dashboard misses logs present in file | Parser/collector rename or wrong indexing | Verify field path and field type |
| Stack trace is lost | Continuation lines lack the ID | Use multiline parser or structured JSONL |
| Older events missing from current file | Rotation, gzip archiving, retention | Check rotated files and central storage |
| Cannot find logs after pod restart | Runtime did not retain previous log | Check `--previous` if available |
| DEBUG/INFO not appearing | Logger/appender threshold filtering | Check configuration at the source |
| Logs arrive late | Queue/ingest delay, wrong time field queried | Compare event time and observed time |
| IDs collide across requests | Client/server generator lacks uniqueness | Review ID generation and scope |
| JSONL parse error | Truncated record, non-JSONL output | Inspect encoder/serializer |
| Searched wrong service | Request traversed multiple instances | Expand scope in a controlled manner |
| Lacking permission to view logs | Access control policy | Request access through proper channels |

A useful diagnostic checklist flow:

```text
Does the app have an ID when receiving the request?
        |
        v
Does MDC/event contain the ID field?
        |
        v
Does the encoder write the field properly in JSON/text?
        |
        v
Do file/stdout/collector retain the event?
        |
        v
Does the index map the field with the right type?
        |
        v
Are ID, time, service, and access scope queried correctly?
        |
        v
Have all services/instances been searched?
```

If the source file has the ID but the index does not, the issue is in parsing/ingestion. If the worker's raw log lacks the ID, the issue is in propagation. **Do not tweak queries to mask instrumentation bugs.**

## 12. Security When Searching by Correlation ID

- **IDs do not grant authorization:** knowing `corr-42` does not entitle someone to view all related events.
- **Do not embed secrets in IDs:** avoid tokens, passwords, session cookies, card numbers, emails, and sensitive data.
- **Validate client-supplied IDs:** enforce length limits, character sets, CRLF rejection, and guard against spoofing/reuse.
- **Scope queries:** restrict by service, time window, authorized tenant, and record limits.
- **Do not share raw logs out of scope:** apply redaction/allowlisting when sharing excerpts.
- **Never execute commands from log text:** messages and stack traces may contain untrusted input.
- **Prevent log injection:** encoders must escape newlines/control characters; formatters must not concatenate unsanitized input.
- **Preserve evidence per policy:** do not delete or alter source files during security/audit investigations.

In multi-tenant systems, a correlation ID filter **does not replace authorization scoping in the search backend**.

## 13. Checklist for Testing Log Search Functionality

1. Two requests have distinct IDs, including `req-42` and `req-420`.
2. The ID is emitted as a field with a stable type and name in JSON.
3. Downstream HTTP services and message consumers receive the appropriate ID.
4. Executor reuse does not mix context between requests A and B, even when tasks fail.
5. Multiline text exceptions are preserved intact during lookup.
6. Both current files and archives within the retention window are covered.
7. The centralized platform filters accurately by field, time window, and service.
8. Timestamp/offset/ingestion delays do not cause unexplained omissions.
9. Input IDs do not cause log forging or leak secrets.
10. If tracing is present, the relationship between `traceId` and correlation ID is defined.
11. Queries produce no false positives from substring matching.
12. Log volume/indexing and cardinality fit the storage strategy.
13. Sensitive data is redacted when exporting or sharing.
14. Collector/backend drop or parse failures have telemetry for detection.

## 14. Practical Summary

**Searching logs by correlation ID** is more than grepping a string. It requires the **right identifier**, **right field**, **exact match**, **appropriate time/service scope**, and **complete events** including exceptions. On text files, watch out for prefix matches, multiline logs, and rotation; on JSONL, parse fields with `jq`; on logging platforms, verify mappings/indices and access permissions. If data is missing, check propagation, MDC, encoders, collectors, filtering, and retention before concluding an event never occurred.

## Official References

- SLF4J MDC API: https://www.slf4j.org/apidocs/org/slf4j/MDC.html
- Logback MDC: https://logback.qos.ch/manual/mdc.html
- Oracle Java 17 BufferedReader: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/BufferedReader.html
- Oracle Java 17 Files: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html
- W3C Trace Context: https://www.w3.org/TR/trace-context/
- OpenTelemetry Context: https://opentelemetry.io/docs/languages/java/api/
- jq Manual: https://jqlang.github.io/jq/manual/
- Grafana Loki LogQL: https://grafana.com/docs/loki/latest/query/
- Elastic term query: https://www.elastic.co/docs/reference/query-languages/query-dsl/query-dsl-term-query
