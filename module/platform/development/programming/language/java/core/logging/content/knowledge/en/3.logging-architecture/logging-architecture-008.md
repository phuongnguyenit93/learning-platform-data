# Reading and Analyzing Logs in Java Logging Architecture

## Objectives

After this lesson, you will be able to read a log entry in context, understand how data flows through logging components in Java, trace a request across multiple records, isolate incidents using timestamps/levels/identifiers, distinguish symptoms from root causes, and apply techniques for reading single-line text, JSON, and multiline logs. You will also write and run a **Java 17+** example that generates logs with **java.util.logging (JUL)**, reads them back from a file, and aggregates the events.

The focus is on **reading and analyzing logs** within **Logging Architecture**: from the record emitted by the application to the file/console and storage system, and then to searching, filtering, correlating, and interpreting the data. Commands using external tools are optional; the main Java example uses only the JDK.

## 1. Where Are Logs Read From in the Logging Architecture?

When Java executes a logging call, a record does not automatically appear in a single place. A typical simplified path is:

~~~mermaid
flowchart LR
    A["Application / library code"] --> B["Logger creates LogRecord"]
    B --> C["Level threshold, filter"]
    C --> D["Handler / Appender"]
    D --> E["Formatter / Encoder"]
    E --> F["Console, file, or other destination"]
    F --> G["Collector / shipper (if any)"]
    G --> H["Storage and indexing"]
    H --> I["Queries, dashboards, alerts"]
~~~

Depending on the framework, the order in which filters/formatters are applied and the output mechanism may differ; the diagram shows the **conceptual flow**, not a claim that every API executes these steps in the exact same sequence. In JUL, logger, handler, filter, and formatter have specific roles; Logback/Log4j 2 use names and configurations that are not identical to JUL.

- **Application** decides which events are logged, at what level, and what context is included in the message/record.
- **Logger** receives the log request, applies thresholds/some filtering rules, and may forward to parent handlers.
- **Handler/Appender** decides which destination receives the record and may apply additional filtering. JUL provides ConsoleHandler, FileHandler, StreamHandler, and other handlers.
- **Formatter/Encoder** converts the record into bytes or characters: a line of text, XML, JSON, or a custom format.
- **Collector/shipper** (if used) reads logs from stdout, files, or the network, adds metadata, buffers, and ships them to the backend.
- **Storage/index** stores and prepares logs for querying by timestamp, service, level, trace ID, and other fields.
- **Analyst** reads information from the console, files, search tools, or dashboards.

You should distinguish three timestamps: **when the event occurred**, **when the record was created/written**, and **when the backend received/displayed it**. When buffering, batching, retries, queues, or slow networks are involved, these timestamps do not match. A log that appears late does not necessarily mean the event just happened.

**Not seeing a record** is not enough to prove an event did not happen: the code might not have called the logger, a level/filter might have dropped the record, the collector might have failed, retention might have expired, or sampling might have discarded events. **Seeing a record** also does not guarantee that the business event was durably committed; a log may be emitted before a transaction completes.

## 2. Reading Each Field of a Log Entry

Consider an illustrative line:

~~~text
2026-11-09T10:15:30.123Z | WARNING | demo.checkout | event=payment.timeout requestId=req-7 dependency=payments attempt=1
~~~

| Component | Meaning | Questions During Analysis |
| --- | --- | --- |
| Timestamp | Time assigned to the record; in this example, UTC because of Z | What time window does the event fall into? Is the source clock reliable? |
| WARNING | Severity level | What is abnormal? Was it handled or does it still have impact? |
| demo.checkout | Logger/component name emitting the log | Which part of the system did the record come from? |
| event=payment.timeout | Stable event name in the message | Which operation timed out? |
| requestId=req-7 | Correlation identifier | Which other logs belong to the same request? |
| dependency=payments | Related dependency component | Is the error related to an external service? |
| attempt=1 | Attempt number | Which retry attempt is this, and what was the final outcome? |

In JUL, **LogRecord** natively includes metadata such as level, logger name, message, instant, parameters, and Throwable. Pairs like requestId, event, and durationMs in the example are placed in the **message by developer convention**; they do not automatically become separate fields in JUL. When the backend or logging library supports structured logging, they can be stored as independent fields for more accurate querying.

A contextless message like "Timeout" may be a symptom, but it does not tell you the request, operation, or dependency. Reading a record effectively means identifying **who/what, what happened, when, the outcome, and the impact**, while also recognizing what data is missing.

### Timestamps, Timezones, and Ordering

- ISO 8601 with an explicit timezone (for example Z for UTC, or +07:00) helps correlate multiple sources. Do not treat a date-time string without a timezone as UTC.
- Normalize timezones before comparing: 17:15+07:00 corresponds to 10:15Z on the same day; do not merge timelines from local time and UTC without normalizing.
- Timezone and timestamp resolution (seconds, milliseconds, nanoseconds) affect accuracy, especially when multiple events happen close together.
- Logs from **a single process writing sequentially to one file** are usually easy to read in write order. Logs from multiple machines, multiple threads, multiple buffers, or shippers **do not form a reliable total order by timestamp alone**.
- If trace/span IDs and operation sequences are available, use business relationships together with timestamps to reconstruct the execution flow; account for clock skew.

### Level Alone Does Not Answer "How Severe Is the Error?"

In JUL, common levels include SEVERE, WARNING, INFO, CONFIG, FINE, FINER, FINEST (along with ALL and OFF for threshold control). Some other frameworks use ERROR/WARN/DEBUG/TRACE. **Do not equate level names strictly across frameworks** when querying multiple sources.

WARNING may describe a recovered retry; SEVERE may describe an actual failed operation. INFO may contain "status=503" if the system chooses to log an operational summary event at INFO level. Read **level together with event and outcome**, and avoid counting errors solely by the number of ERROR or SEVERE lines.

## 3. Identifying the Log Format Before Parsing

### Single-Line Text

~~~text
2026-11-09T10:15:30Z | INFO | demo.checkout | event=request.finished requestId=req-7 status=200 durationMs=238
~~~

Pros: quick to read by eye and with string-search tools. Cons: if delimiters, spaces, or special characters are not escaped, a custom parser may misidentify field boundaries. When filtering for "503", that string might be an HTTP status code, an order ID, or part of a URL.

### JSON Lines (Each Record Is One JSON Object per Line)

~~~json
{"timestamp":"2026-11-09T10:15:30Z","level":"INFO","service":"checkout","event":"request.finished","requestId":"req-7","status":200,"durationMs":238}
~~~

JSON allows type-accurate queries on numeric fields (durationMs > 100), grouping by service, or extracting exact requestId values. You must know the actual schema and how the collector transforms it (field names are sometimes renamed or normalized). If a Throwable/stack trace contains newlines, the JSON encoder should escape them properly so each record remains a single object; do not assume multiline text is already valid JSON Lines.

### XML or Multiline Text

JUL **FileHandler defaults to XMLFormatter** if no other formatter is configured. Do not read XML logs as if they were key=value text, and do not assume one line equals one record. An exception record can span multiple lines:

~~~text
2026-11-09T10:15:30Z ERROR checkout: payment failed requestId=req-7
java.net.SocketTimeoutException: Read timed out
    at com.example.PaymentClient.call(PaymentClient.java:42)
    at com.example.OrderService.pay(OrderService.java:71)
~~~

This is **one error and an illustrative stack trace**, not three new events. During analysis, identify record boundaries using a timestamp/header pattern, a multiline parser, or a structured format; counting every text line as an event will inflate error counts.

**Rule:** clearly identify the source, encoding (typically UTF-8), formatter, separator, escaping, record structure, and multiline policy **before** writing regexes or statistics. A quick custom parser written for controlled demo data should not be applied directly to heterogeneous production logs.

## 4. Workflow for Investigating an Issue from Logs

An effective approach is to start from a **verifiable symptom**, then narrow down step by step:

1. **Define the symptom and scope.** For example: around 10:15–10:20 UTC, checkout returned many 503s—only in one environment or across all regions? Record the timezone and confirmation source (ticket, metric, trace, user report).
2. **Find logs near the symptom.** Filter by the right service/environment, a wide enough time window, request/trace ID, or endpoint. Do not read millions of lines from the start of a file when you already know the time range.
3. **Distinguish outcome from cause.** "request.finished status=503" describes the outcome of the request; an error in the inventory dependency may be a link in the chain that needs verification.
4. **Use identifiers to trace the path.** Pull all logs for the same requestId; across multiple services, prefer traceId/spanId. Check attempts, retries, timeouts, fallbacks, and the final outcome.
5. **Place milestones on a timeline.** Find the last known success, the first observed anomaly, related changes (deploy/config/load), outage duration, and recovery time.
6. **Read exceptions and context.** Inspect the cause chain, exception type, throw/catch points, and triggering conditions; check whether the same exception is logged repeatedly across multiple layers.
7. **Verify hypotheses with other sources.** Compare logs with metrics (error rate, p95/p99 latency), traces, dependency health, and recent changes; a single stack trace is rarely enough.
8. **Assess actual impact.** How many requests failed, how many users were affected within permitted visibility, and how did latency increase? Count by request/transaction rather than by raw "error" lines.
9. **Document evidence and limitations.** Save the time range, queries, redacted requestId/traceId values, milestones, conclusions with confidence levels, and any open hypotheses.

You can iterate through these steps as new clues emerge. The "first error line" may only be the **first symptom visible in the logs**, not necessarily the root cause: for example, a dependency may have stopped responding because it had been overloaded for several minutes earlier.

### Reading Vertically Along a Request Instead of Isolated Lines

~~~text
10:15:30.010 INFO    event=request.started requestId=req-7
10:15:30.080 WARNING event=payment.timeout requestId=req-7 attempt=1
10:15:30.150 INFO    event=payment.retry_succeeded requestId=req-7 attempt=2
10:15:30.248 INFO    event=request.finished requestId=req-7 status=200 durationMs=238
~~~

The timestamps above are **timeline illustrations**, not the fixed output of the program in the hands-on section. Correct analysis: there was one timeout, one successful retry, and the final outcome was HTTP 200. **Do not conclude req-7 failed just because it has a WARNING.** Conversely, if another request has status=503, trace backward to see whether it was a processing error, a dependency timeout, or a business rule.

## 5. Techniques for Searching, Filtering, Grouping, and Comparing

### Filtering by Time, Source, and Level

Prefer combined conditions: time window + service/environment + requestId/traceId or event. Searching only for the string "ERROR" can miss failed events logged at INFO, while also matching the word "error" in message text that has nothing to do with log level.

For text logs, you can inspect a controlled slice using OS tools.

**PowerShell** (Windows):

~~~powershell
Get-Content -Path .\app.log -Tail 50
Select-String -Path .\app.log -Pattern 'requestId=req-7'
Select-String -Path .\app.log -Pattern '\bWARNING\b|\bSEVERE\b'
Get-Content -Path .\app.log -Tail 20 -Wait
~~~

The last command follows a file as it is being written; press Ctrl+C to stop. A multiline record will appear across multiple lines. These patterns rely on **text formatting**, not JSON schema parsing.

**Bash/GNU tools** (Linux/macOS, where available):

~~~bash
tail -n 50 app.log
grep -n 'requestId=req-7' app.log
grep -E 'WARNING|SEVERE' app.log
tail -n 20 -f app.log
~~~

**If the file is JSON Lines** and `jq` is available:

~~~bash
jq -r 'select(.level == "ERROR") | [.timestamp, .traceId, .message] | @tsv' app.jsonl
jq -r 'select(.event == "request.finished" and (.durationMs > 100)) | [.requestId, .durationMs] | @tsv' app.jsonl
~~~

This syntax targets JSON objects with the corresponding fields. With centralized backends, you should generally query **structured fields** and backend filters instead of running grep over raw messages.

### Grouping by the Right Unit of Analysis

- **By requestId/traceId:** reconstruct the path and outcome of **a single request**.
- **By event:** count occurrences of request.finished, payment.timeout, or retry_succeeded within a time window.
- **By level:** inspect the distribution of WARNING/SEVERE for signals; do not use it as a substitute for failed request counts.
- **By service, host, region, or version:** check whether errors are concentrated in one component or after a deployment.
- **By time:** bucket into 1-minute or 5-minute windows to spot traffic peaks and correlate with latency spikes.
- **By latency/status:** compute 5xx status rates, processing duration, and p95/p99 (when sample size is sufficient and data is reliable).

You must choose the **denominator** before calculating rates. For example, a request failure rate requires failed requests divided by total corresponding requests; do not divide SEVERE line counts by total INFO lines. Retries, duplicate logs, sampling, and dropped logs can all cause record counts to diverge from transaction counts.

### Looking for Relationships Instead of Just Keywords

A common pattern is event A occurring followed by event B. If every timeout follows a deployment, that is a **correlation** worth investigating, not yet proof that the deployment is the cause. Check the version, start time, configuration changes, dependency health, and compare against an unaffected control group to verify.

## 6. Java 17+ Hands-On: Creating Logs, Reading a File, Analyzing Events

This example demonstrates a small pipeline: **Logger → FileHandler → Formatter → UTF-8 file → parser → Stream API queries**. The program writes nine controlled records, closes the handler to flush, reads the file into Entry objects, counts severities, reconstructs request req-7, finds slow requests, and counts HTTP 5xx responses.

To keep the output easy to verify, the program captures the real timestamp of each LogRecord, but prints only **deterministic summary results** to stdout. The temporary log file is created in the system temp directory and deleted after reading; modify the deletion step if you want to keep the file and open it in an editor.

Create the file **LogReadAnalyzeDemo.java**:

~~~java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.logging.FileHandler;
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class LogReadAnalyzeDemo {
    record Entry(Instant timestamp, Level level, String logger,
                 Map<String, String> fields) {}

    static Entry parse(String line) {
        String[] columns = line.split(" \\| ", 4);
        if (columns.length != 4) {
            throw new IllegalArgumentException("Unexpected log format");
        }
        Map<String, String> fields = new LinkedHashMap<>();
        for (String token : columns[3].split(" ")) {
            int equals = token.indexOf('=');
            if (equals > 0) {
                fields.put(token.substring(0, equals),
                        token.substring(equals + 1));
            }
        }
        return new Entry(Instant.parse(columns[0]),
                Level.parse(columns[1]), columns[2], fields);
    }

    public static void main(String[] args) throws Exception {
        Path path = Files.createTempFile("log-read-demo-", ".log");
        Logger logger = Logger.getLogger("demo.checkout");
        logger.setUseParentHandlers(false);
        logger.setLevel(Level.ALL);

        FileHandler handler = new FileHandler(path.toString(), false);
        handler.setEncoding("UTF-8");
        handler.setLevel(Level.ALL);
        handler.setFormatter(new Formatter() {
            @Override
            public String format(LogRecord record) {
                return record.getInstant() + " | "
                        + record.getLevel().getName() + " | "
                        + record.getLoggerName() + " | "
                        + formatMessage(record) + System.lineSeparator();
            }
        });

        logger.addHandler(handler);
        try {
            logger.info("event=request.started requestId=req-7 path=/checkout");
            logger.warning("event=payment.timeout requestId=req-7 attempt=1");
            logger.info("event=payment.retry_succeeded requestId=req-7 attempt=2");
            logger.info("event=request.finished requestId=req-7 status=200 durationMs=238");
            logger.info("event=request.started requestId=req-8 path=/catalog");
            logger.info("event=request.finished requestId=req-8 status=200 durationMs=12");
            logger.info("event=request.started requestId=req-9 path=/checkout");
            logger.severe("event=inventory.unavailable requestId=req-9 dependency=inventory");
            logger.info("event=request.finished requestId=req-9 status=503 durationMs=115");
        } finally {
            logger.removeHandler(handler);
            handler.close();
        }

        List<Entry> entries;
        try (var lines = Files.lines(path, StandardCharsets.UTF_8)) {
            entries = lines.map(LogReadAnalyzeDemo::parse).toList();
        } finally {
            Files.deleteIfExists(path);
        }

        long warningCount = entries.stream()
                .filter(entry -> entry.level().equals(Level.WARNING)).count();
        long severeCount = entries.stream()
                .filter(entry -> entry.level().equals(Level.SEVERE)).count();

        List<String> requestEvents = entries.stream()
                .filter(entry -> "req-7".equals(entry.fields().get("requestId")))
                .map(entry -> entry.fields().get("event")).toList();

        List<String> slowRequests = entries.stream()
                .filter(entry -> "request.finished".equals(entry.fields().get("event")))
                .filter(entry -> Integer.parseInt(
                        entry.fields().getOrDefault("durationMs", "0")) > 100)
                .map(entry -> entry.fields().get("requestId")).toList();

        long serverErrors = entries.stream()
                .filter(entry -> "request.finished".equals(entry.fields().get("event")))
                .filter(entry -> Integer.parseInt(
                        entry.fields().getOrDefault("status", "0")) >= 500)
                .count();

        System.out.println("totalRecords=" + entries.size());
        System.out.println("WARNING=" + warningCount + " SEVERE=" + severeCount);
        System.out.println("req-7=" + String.join(" -> ", requestEvents));
        System.out.println("slow(>100ms)=" + String.join(",", slowRequests));
        System.out.println("http5xx=" + serverErrors);
    }
}
~~~

Run with **JDK 17 or later** in the directory containing the file:

~~~bash
javac LogReadAnalyzeDemo.java
java LogReadAnalyzeDemo
~~~

**Exact stdout** for the sample data generated in the code:

~~~text
totalRecords=9
WARNING=1 SEVERE=1
req-7=request.started -> payment.timeout -> payment.retry_succeeded -> request.finished
slow(>100ms)=req-7,req-9
http5xx=1
~~~

Step-by-step explanation:

1. **FileHandler** creates the log file and manages the associated resource; **setEncoding("UTF-8")** standardizes the encoding. Disabling parent handlers prevents records from also being printed to the console via the root logger in the demo.
2. **Formatter** converts each record into one line with four fields separated by ** | **: ISO-8601 UTC timestamp, level, logger name, and message. Because the example messages contain no newlines or ** | ** delimiters, one record equals exactly one line.
3. **Closing the handler before reading** flushes the written logs and releases the file lock. The temporary file is deleted after analysis so no generated file is left behind.
4. **parse(...)** splits into four parts; the message is then split into key=value tokens. Entry holds Instant, Level, logger, and a field map for attribute-based querying rather than arbitrary substring matching.
5. **Aggregation by level:** there is one payment.timeout at WARNING and one inventory.unavailable at SEVERE. These are **record** counts, not failed request counts.
6. **Correlating req-7:** one request has the sequence started → timeout → retry_succeeded → finished. The final outcome **status=200** is in the request.finished record.
7. **Finding slow requests:** two request.finished records have durationMs exceeding **100** (req-7: 238 ms, req-9: 115 ms).
8. **Counting HTTP 5xx errors:** out of three request.finished records, only req-9 has status=503; the count is **1**. Because the dataset is tiny, do not extrapolate production system quality from it.
9. **Parser scope:** the parser above only works for controlled messages containing key=value tokens **with no spaces, unescaped equals signs, or newline characters**. For real logs, you need a proper schema, encoder, parser, and escaping/multiline handling; do not use a simple split to parse untrusted payloads.

The program uses JUL with no libraries outside the JDK. **Java's record** (Entry) has been a Java feature since Java 16 and is stable in Java 17. **Files.lines** returns a stream backed by the file, so the program uses try-with-resources to close the stream.

### Reading the Demo Results as a Mini Investigation

| Request | Recorded Event Sequence | Final Outcome | Interpretation |
| --- | --- | --- | --- |
| req-7 | start → payment timeout → retry succeeded → finish | 200, 238 ms | Recovered anomaly; the request succeeded but was slow |
| req-8 | start → finish | 200, 12 ms | Successful request in the sample data |
| req-9 | start → inventory unavailable → finish | 503, 115 ms | Request ended with a server error; check the inventory dependency |

Do not treat every WARNING/SEVERE log as an "independent incident". req-7 had a WARNING yet succeeded; req-9 had a SEVERE and status 503. From the table, we have a **hypothesis** that the inventory dependency is involved in req-9, but we still need dependency data, metrics, and traces before confirming the root cause.

## 7. Analyzing Exceptions and Stack Traces

When reading an error with a Throwable, examine the **exception type, cause chain, stack trace, failing action, and subsequent handling**. Start from the business-boundary message ("payment request failed") and work inward to where the exception originated. For multi-layered wrapped errors, **Caused by** often reveals the inner error, but do not assume every "Caused by" is the system root cause: a timeout may stem from slow networking, overload, configuration, a circuit breaker, or other factors.

Illustrative example:

~~~text
2026-11-09T10:15:30Z SEVERE event=payment.failed requestId=req-12
java.lang.IllegalStateException: Payment service unavailable
    at com.example.PaymentService.charge(PaymentService.java:81)
Caused by: java.net.SocketTimeoutException: Read timed out
    at com.example.PaymentClient.call(PaymentClient.java:46)
~~~

How to read it: **PaymentService** failed to complete the operation; **SocketTimeoutException** indicates the downstream call timed out while reading; you need to check host, endpoint, duration, retries, traces, and dependency health. The stack trace lines belong to **the same error record** and should not be counted as multiple independent errors. Appearing in a stack frame does not mean every method in the trace "caused the bug".

Checks to keep in mind:

- An exception may be logged multiple times when code logs and rethrows across layers, inflating statistics.
- Never assume an exception message is safe: it may contain SQL, URLs, headers, tokens, or personal data.
- Truncated stack traces lose part of the evidence; note the limitation before drawing conclusions.
- An exception that is caught and validly handled is not necessarily an operational incident requiring an alert.
- If a stack trace line has no timestamp/header, do not let your parser count it as a new log event.

## 8. Common Analysis Challenges in Multi-Service Systems

### Correlation and Asynchronous Processing

requestId works well for linking logs within a single request inside one service; **traceId/spanId** is better suited for following execution across multiple services. Context must be propagated across thread boundaries, executors, message queues, or async callbacks. In Java, data stored in ThreadLocal does not automatically cross to other threads/tasks, and context leaks if not cleared in thread pools. If correlation IDs are missing, add tracing instrumentation and note that matching logs by nearby timestamps is only speculative.

### Delivery Delays, Lost Logs, and Duplicate Logs

Collectors may read files in batches, fail, and retry; buffering delays arrival at the backend, and retries can duplicate records. Rotation/retention can cause missing file segments; sampling or filters keep only a portion of traffic. Compare **event time** with **ingestion time**, check sources and record counts, and do not conclude an event never happened just because it has not been indexed yet.

### Format and Version Diversity

Services may use JUL, Log4j 2, Logback, HTTP access logs, or JSON encoders with different fields. One record may use **time**, another **timestamp**; level might be ERROR or SEVERE; duration might be in ms, µs, or ns. Before uniting datasets, **normalize field names, timezones, units, and event semantics**, or dashboards will miscalculate.

### Reliability of Log Data

A developer-written message may be poorly timed ("success" before commit), lack context, be truncated, or reflect a retry attempt rather than the final outcome. Use logs to **form and test hypotheses**, alongside business state, metrics, traces, databases, and external results where needed.

## 9. Security and Performance When Reading Logs

**Reading logs also involves handling sensitive data.** Analysts need appropriate environment permissions and should only access data needed for the investigation. Never paste logs containing access tokens, passwords, secrets, session cookies, payment cards, or personal payloads into unauthorized services. When sharing logs in issues or chat, strip or redact sensitive information, including inside stack traces and URL query strings.

When using search or visualization tools:

- User-controlled input can contain newlines and control characters to forge log entries (log injection). Only trust metadata from a properly parsed/escaped pipeline.
- Regexes over massive logs or poorly optimized regex patterns can be expensive; narrow the time window/service, prefer indexed fields, and avoid unbounded scans.
- Do not use verbose-level records to infer overall system quality when traffic is partially sampled. Non-representative samples skew rates.
- Be cautious with logging inside loops and large request payloads: they impact I/O, disk, ingestion costs, and retention. Use metrics for repeated counts and traces for call chains; keep logs focused on event context.
- When running backend queries, watch for indexing lag and UI timezone settings; a "last 15 minutes" query on a backend may filter by ingestion timestamp.

## 10. Common Analysis Mistakes and How to Fix Them

| Mistake / Wrong Assumption | How to Fix It |
| --- | --- |
| "No logs means no errors." | Check logger level/filter, collector, loss, sampling, and retention. |
| "One line in a file is one record." | Identify JSON/XML/multiline stack traces before counting. |
| "One WARNING means a failed request." | Correlate by requestId and check the final status. |
| "Count SEVERE lines to get the error rate." | Count outcomes per request/operation with a well-defined denominator. |
| "Sorting all logs from multiple machines by timestamp gives absolute order." | Normalize timezones, account for clock skew, and use traces/business relationships. |
| "SocketTimeoutException means the network is definitely broken." | Check dependency health, saturation, timeout config, metrics, and wait times. |
| "Log full payloads for faster debugging." | Use approved fields, identifiers, and redaction policies. |
| "Parse every message by splitting on spaces." | Use a parser with proper schema/escaping and multiline support. |
| "The first log line is the root cause." | Reconstruct the timeline, inspect system changes, and verify with other sources. |
| "A success log means the transaction committed." | Check where the log sits relative to commit/ack and verify actual state. |

## 11. Checklist for Reading and Analyzing Logs

1. Confirm the **event/scenario** under investigation, time range, timezone, and environment.
2. Identify the **log source and path**: service/logger → handler/file/stdout → collector → backend.
3. Identify the **format, encoding, fields/schema, timezone, multiline rules, and timestamp semantics**.
4. Filter by **service, version, time window, event, and requestId/traceId** before broadening the scope.
5. Read **level + message + outcome + context** together; distinguish symptoms from final outcomes.
6. Link records into a **timeline**, watching for retries, timeouts, async flows, duplicates, and clock skew.
7. Inspect **Throwable/cause chains**, and cross-check with metrics/traces and dependencies when finding the cause.
8. When aggregating, clearly define the **counting unit, denominator, sampling, and missing data**.
9. Redact sensitive data, limit query scope, and save enough evidence for others to reproduce.
10. Write conclusions tied to actual evidence; clearly state what remains uncertain.

## Self-Check Questions

**1.** There are 20 SEVERE lines in one minute. Can you conclude 20 requests failed?  
**Answer:** No. One request can log multiple SEVERE lines, and logs can be duplicated by retries or collectors; you must count final outcomes per request or transaction.

**2.** One record has timestamp 17:15:00+07:00, and another has 10:15:00Z; are these two different points in time?  
**Answer:** No, they represent the exact same UTC instant if both clocks are accurate.

**3.** Why shouldn't you parse Java stack traces by counting each line?  
**Answer:** A Throwable's stack trace typically spans multiple lines belonging to a single record; counting each line creates false events and distorts statistics.

**4.** In the Java demo, why is req-7 still considered a successful request despite having a WARNING?  
**Answer:** payment.timeout on attempt=1 was retried, and the final request.finished event had status=200. WARNING describes an anomaly at one step, not the request's overall outcome.

**5.** If the backend does not show recent logs yet, what checks are useful?  
**Answer:** Check logger/handler levels and filters, stdout/file writing, collector/shipper status, ingestion delay, retention, sampling, and query permissions. Missing logs alone do not prove an event did not occur.

**Key takeaway:** Reading logs means **turning isolated records into a verifiable picture of a sequence of events**. Understand the data's path and format, correlate using context, keep timestamps and counting units accurate, and cross-check log evidence against metrics, traces, and business state before concluding the root cause.
