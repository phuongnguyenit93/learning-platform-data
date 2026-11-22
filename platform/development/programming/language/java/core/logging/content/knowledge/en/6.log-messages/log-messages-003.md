# Searchable Messages — Designing Easy-to-Query Log Messages in Java

## 1. What is a “Searchable Message”?

A **searchable log message** is a log message written and structured so that operators can **find the exact event they need to investigate, filter by criteria, and correlate related events** in the console, log files, or a centralized logging system. A good message needs to be both easy to understand when read directly and equipped with stable markers that search tools can recognize.

For example, when a customer reports that a payment operation failed, the following log line is very hard to use:

~~~text
An error occurred!
~~~

This message does not state which operation the error belongs to, which service to look in, or how to relate it to a specific request. A message with clearer structure and context looks like this:

~~~text
WARN service=order-api event=payment.retry requestId=req-42 orderId=ORD-7 attempt=2 reason=timeout
~~~

Thanks to fields with consistent names and values, readers can search for **event=payment.retry**, filter by **requestId=req-42**, or aggregate events with **reason=timeout**. The line above is an example of the `key=value` format, not Java's default log output syntax.

**“Searchable” does not mean “the more text, the better.”** A useful message must answer a specific question: *what event occurred, which object/operation does it relate to, where did it happen, and what was the outcome?* The number of fields should be sufficient without containing unnecessary data.

## 2. Why Does Searchability Matter?

A real-world application can emit many logs per second. When an incident occurs, operators usually do not have time to read every line sequentially; instead, they need to perform several actions:

1. **Find events:** look up failed login attempts, retries, timeouts, or the completion of a job.
2. **Filter scope:** keep only logs from a specific service, environment, logger, log level, route, or time range.
3. **Trace a request:** use a request ID or trace ID to correlate events belonging to the same execution flow.
4. **Count and compare:** check whether a type of event is occurring more frequently than normal; formal measurement over time should be paired with metrics.
5. **Identify root causes:** search for error codes, exception types, dependent components, or failed steps.
6. **Verify after a fix:** search for the same event type before and after deployment to see whether the issue still occurs.

If every place in the codebase names an event differently—such as “pay fail”, “Payment failed”, or “Thanh toán bị lỗi”—tools have to search for multiple text patterns and can easily miss records. **Stability of messages and searchable fields is part of maintainability.**

## 3. Components of a Searchable Log Message

A useful event typically includes several of the following fields, depending on the situation:

| Component | Example | Role in Lookup |
| --- | --- | --- |
| Timestamp | 2026-11-09T10:15:00Z | Narrow down the time window; should include an explicit time zone |
| Level | INFO, WARN, ERROR | Categorize the level of attention required |
| Service/component | order-api, payment-client | Identify where the log originated |
| Event name/code | payment.retry, ORDER_PAYMENT_TIMEOUT | Consistently find the same type of event |
| Correlation ID | requestId=req-42, traceId=... | Link multiple records belonging to the same request |
| Business ID | orderId=ORD-7 | Investigate a business entity if logging the ID is permitted |
| Outcome/status | outcome=failure, status=503 | Filter by result or status |
| Error type/code | errorType=TimeoutException | Group technical root causes |
| Duration and unit | durationMs=2500 | Identify slow operations |
| Human-readable message | “Retrying after timeout in payment” | Explain meaning without needing to know the source code |

Not all fields need to be present on every line. An application startup event does not need an `orderId`, whereas a payment error usually needs a `requestId` and an error code for investigation.

### Messages and Metadata Can Live in Different Places

In some libraries, the **message** is the event description; the timestamp, level, logger name, thread, and exception are attached to a **log event** by the logging framework before being written to a file or console. In structured logging, those attributes often become separate JSON fields. Therefore, a “searchable log message” covers both **how you phrase the content** and **how the log data is packaged and emitted**.

A configuration that logs only raw messages while omitting timestamps or levels may be enough for a small exercise, but it lacks critical information in operations. You should design the *entire log record* for effective lookup.

## 4. Writing Messages with Stable Events

Free-form messages are easy to read, but they can vary depending on phrasing. For example:

~~~text
Could not connect to payment on retry 2
Payment timeout, retrying
Payment call error: retry 2
~~~

These three lines may describe the same type of event, but searching for an exact phrase will miss the other variations.

The solution is to choose a **stable event name or event code**, while keeping a natural description when needed:

~~~text
event=payment.retry requestId=req-42 attempt=2 reason=timeout message="Retrying payment dependency"
~~~

In this example, **payment.retry** becomes the primary search key. You can adjust the wording of the human-readable message while keeping the event unchanged as long as the business meaning has not changed.

Suggested naming rules:

- Use names that describe a **specific event**, such as **order.created**, **payment.retry**, **payment.failed**, or **job.completed**.
- Choose a consistent convention for casing and delimiters—for example, lowercase with dots separating domain and action.
- Avoid generating dynamic names like **payment.failed.order-874**. Put the order ID in a **separate field**.
- Do not reuse one event for multiple different meanings. **payment.retry** and **payment.failed** are different: one is a retry attempt, and the other is a failure outcome.
- If an event has an official code, keep the code stable and document its meaning so filtering and dashboards do not depend on natural-language phrasing.

A consistent event name makes searching easier; by itself, it **does not turn a log into a metric** or guarantee that the collection system will index that field.

## 5. Key=Value and JSON Structures

### 5.1. Key=Value Format is Easy to Start With

A simple format:

~~~text
INFO service=order-api event=order.created requestId=req-101 orderId=ORD-100 outcome=success durationMs=18
WARNING service=order-api event=payment.failed requestId=req-102 orderId=ORD-101 outcome=failure errorType=TimeoutException durationMs=2500
~~~

Pros: quick for humans to read, has patterns that are easy to find with string-search tools, and fits demos and small systems.

Cons: if values contain spaces, equals signs, quotes, or newline characters, parsing requires **clear escaping/quoting rules**. Ad-hoc string concatenation produces data that is hard to parse. The examples in this lesson intentionally use simple token values.

### 5.2. JSON Lines for Structured Logging

When the collection tool supports JSON, each record can be a standalone JSON object on **one line**:

~~~json
{"timestamp":"2026-11-09T10:15:00Z","level":"WARN","service":"order-api","event":"payment.failed","requestId":"req-102","orderId":"ORD-101","outcome":"failure","errorType":"TimeoutException","durationMs":2500}
~~~

Pros:

- Fields are typed data: for example, **durationMs** is a number, making filters like **durationMs > 1000** more accurate than string matching.
- Collection tools can parse and query directly by field name.
- Values containing spaces or special characters are represented according to standard JSON syntax.
- Fields can be organized as **error.type**, **http.status_code**, or **service.name** if the project follows a chosen schema.

Key point to remember: **JSON must be produced by a proper encoder/serializer**, not by manual string concatenation that skips escaping. When outputting JSON Lines, one event should correspond to one object per line to keep processing simple. How stack traces are emitted must be consistent with the collector.

**Both key=value and JSON are searchable.** JSON is convenient for querying typed fields once the pipeline is configured to parse and index them; key=value remains useful if your tools have a logfmt parser or rely on string search. Neither format guarantees searchability on its own if the collector does not read, store, or allow querying the data.

## 6. Runnable Java 17+ Example with java.util.logging

The JDK includes **java.util.logging (JUL)**, which is sufficient to demonstrate stable messages without external dependencies. The program below logs three events using the **event, requestId, orderId, outcome** convention along with event-specific fields.

Create the file **SearchableMessageDemo.java**:

~~~java
import java.util.logging.Formatter;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;
import java.util.logging.StreamHandler;

public class SearchableMessageDemo {
    private static final Logger LOGGER =
            Logger.getLogger(SearchableMessageDemo.class.getName());

    public static void main(String[] args) {
        // Isolate the handler so the example does not emit additional logs through the parent logger.
        LOGGER.setUseParentHandlers(false);
        LOGGER.setLevel(Level.INFO);

        // Compact formatter, independent of runtime.
        Handler stdout = new StreamHandler(System.out, new Formatter() {
            @Override
            public String format(LogRecord record) {
                return record.getLevel().getName() + " "
                        + formatMessage(record)
                        + System.lineSeparator();
            }
        });
        stdout.setLevel(Level.INFO);
        LOGGER.addHandler(stdout);

        LOGGER.info("service=order-api event=order.created"
                + " requestId=req-101 orderId=ORD-100"
                + " outcome=success durationMs=18");

        LOGGER.warning("service=order-api event=payment.failed"
                + " requestId=req-102 orderId=ORD-101"
                + " outcome=failure errorType=TimeoutException"
                + " durationMs=2500");

        LOGGER.info("service=order-api event=order.created"
                + " requestId=req-103 orderId=ORD-102"
                + " outcome=success durationMs=21");

        // StreamHandler buffers records; flush to ensure the example prints everything.
        stdout.flush();
    }
}
~~~

Compile and run with **JDK 17 or later** in a UTF-8 terminal:

~~~bash
javac -encoding UTF-8 SearchableMessageDemo.java
java SearchableMessageDemo
~~~

**Exact stdout** when running this program:

~~~text
INFO service=order-api event=order.created requestId=req-101 orderId=ORD-100 outcome=success durationMs=18
WARNING service=order-api event=payment.failed requestId=req-102 orderId=ORD-101 outcome=failure errorType=TimeoutException durationMs=2500
INFO service=order-api event=order.created requestId=req-103 orderId=ORD-102 outcome=success durationMs=21
~~~

How it works:

1. **LOGGER.info(...)** and **LOGGER.warning(...)** emit records at their respective levels. Each message contains consistently named fields.
2. **LOGGER.setLevel(Level.INFO)** and **stdout.setLevel(Level.INFO)** ensure that INFO/WARNING events are accepted.
3. **setUseParentHandlers(false)** prevents the same record from being emitted again through a parent logger's handler, keeping the output deterministic.
4. **StreamHandler(System.out, ...)** writes to stdout; **JUL's default ConsoleHandler typically writes to stderr**, so do not treat the two handlers as identical.
5. The formatter prints only the level and message for easy verification; **production configurations should include a timestamp, logger/service, environment, and appropriate contextual fields**.
6. **stdout.flush()** flushes buffered records before the program exits.

To search inside a log file on Linux/macOS or in an environment with **grep**, you can redirect the program's stdout to a file and search it:

~~~bash
java SearchableMessageDemo > app.log
grep -F 'event=payment.failed' app.log
grep -F 'requestId=req-102' app.log
~~~

Both `grep` commands above select the second WARNING line in the output shown earlier. Depending on your needs, you can search for all **event=order.created** lines or a specific **requestId**. **grep -F** matches a literal substring; it is not a typed field query tool and does not enforce field boundaries. For example, searching for **requestId=req-1** may accidentally match **requestId=req-101**.

On **Windows PowerShell**, a roughly equivalent command for a log file is:

~~~powershell
Select-String -Path app.log -SimpleMatch 'requestId=req-102'
~~~

The command returns lines containing the search string, possibly along with the file name and line number depending on the display environment. This is a text-file search operation, not a logger configuration.

### Limitations of the Example

This program demonstrates string-based searchability. It **does not yet include a centralized collector, indexed JSON fields, retention, or distributed querying**. The output intentionally omits timestamps so it stays identical across runs; real-world logging needs timestamps with an explicit time zone to filter during incidents.

If user-supplied data may contain spaces, quotes, or newline characters, **do not concatenate it directly into key=value as shown above**. Use structured logging and an encoder that guarantees proper escaping, or define an explicit escaping format.

## 7. How Do String Search and Field Search Differ?

There are two common types of queries.

### 7.1. Full-Text or Substring Search

For example, finding all lines containing:

~~~text
payment.failed
~~~

This approach is easy to use, but it can also match text that is not the event field—such as the message “previous event was payment.failed”. Matching behavior can depend on case sensitivity, word splitting, tokenization, or the tool's syntax.

### 7.2. Structured Field Filtering

If the data has been parsed into separate fields, you can express the query logically:

~~~text
service = "order-api"
AND event = "payment.failed"
AND outcome = "failure"
AND durationMs > 1000
~~~

This is a **conceptual filter description**, not a query that can be run verbatim on every backend. In a specific system, the syntax for Elastic, Loki, Cloud Logging, OpenSearch, or another tool may differ. What matters is that the collector recognizes **event** and **durationMs** as distinct data fields.

When you need an exact value such as `requestId`, querying **by a typed or exact-string field** is more reliable than substring search. For instance, `requestId=req-1` and `requestId=req-101` are two different values, even though a substring search might return both.

## 8. Good and Bad Message Patterns

| Hard-to-Search or Unclear Message | Improved Message | Why It Is Better |
| --- | --- | --- |
| “Error occurred” | event=payment.failed errorType=TimeoutException | Includes the event name and root-cause type |
| “Order OK” | event=order.created orderId=ORD-7 outcome=success | Has a clear event, outcome, and ID for correlation |
| “Retry attempt 2” | event=payment.retry requestId=req-42 attempt=2 reason=timeout | Allows filtering retries and their reasons |
| “Query too slow” | event=db.query.slow operation=loadOrders durationMs=1820 | Explicitly records duration and operation name |
| “Bad input: [entire user payload]” | event=validation.failed errorCode=INVALID_FORMAT field=postalCode | Provides error code and field name without exposing sensitive data |

A message can include a **human-readable description** alongside machine-filterable fields. For example:

~~~text
event=job.completed jobType=sync-catalog outcome=success durationMs=381 message="Catalog sync completed"
~~~

Name the **event** field after the actual action, and keep **outcome** separate to distinguish success from failure for the same type of task. Do not invent new field names for every message when only the values differ.

## 9. Correlation IDs Help Trace the Full Story of a Request

An issue often spans multiple steps and may run across multiple threads or services:

~~~text
INFO service=checkout event=checkout.started requestId=req-42
INFO service=pricing event=price.calculated requestId=req-42 total=90
WARNING service=payment event=payment.retry requestId=req-42 attempt=2 reason=timeout
ERROR service=checkout event=checkout.failed requestId=req-42 errorCode=PAYMENT_UNAVAILABLE
~~~

If all records share **requestId=req-42**, an investigator can filter by it to see the sequence of related events. In distributed applications, **traceId/spanId** also help link logs with distributed traces when context propagation is configured.

Keep in mind:

- **Request IDs must be generated/managed systematically and propagated across processing steps**; the logger does not automatically attach the same ID to every message.
- When using thread pools, asynchronous tasks, or reactive flows, context does not necessarily transfer to another thread automatically; you need the framework's proper propagation mechanism.
- Do not assume **ThreadLocal/MDC** follows every asynchronous task. With SLF4J/Logback, MDC is commonly used to attach context; plain JUL does not have a unified MDC API like that.
- In centralized logs collected from multiple instances, the arrival order of lines **is not necessarily the global order** of events; use timestamps, traces, and causal information when analyzing.

IDs used for searching should have appropriate access controls and must not contain sensitive data. Do not put user-identifying information directly into a request ID just to make log searching convenient.

## 10. Java: Placeholders, Exceptions, and Structured Logging

### 10.1. Parameterized Messages

With **java.util.logging**, the standard parameter formatting syntax uses **{0}, {1}**:

~~~java
// Illustrative snippet inside a class that has already declared LOGGER and requestId.
LOGGER.log(java.util.logging.Level.INFO,
        "event=job.completed requestId={0} outcome=success",
        requestId);
~~~

With **SLF4J**, the standard placeholder syntax uses **{}**:

~~~java
// Illustrative snippet: requires SLF4J API, a provider, and the requestId variable.
LOG.info("event=job.completed requestId={} outcome=success",
        requestId);
~~~

Both snippets are **in-context illustrations**, not standalone programs. When logging many events of the same type, keeping the **message template** stable and passing values as arguments is usually easier to maintain than constructing many different message patterns. However, how backends index the raw message or template varies across systems.

**Do not confuse placeholders with structured fields.** A sentence containing **requestId={}** may still be just a plain message string after formatting; to query accurately by field, your pipeline needs a parser or the corresponding structured logging API/encoder.

### 10.2. Logging Exceptions to Find Root Causes

When an operation fails, the message should describe the **event** and **error code**, while preserving the exception object when needed:

~~~java
try {
    callPaymentService();
} catch (java.io.IOException ex) {
    LOGGER.log(java.util.logging.Level.SEVERE,
            "event=payment.failed errorCode=PAYMENT_IO_ERROR",
            ex);
}
~~~

This is an **illustrative snippet**, because `callPaymentService()` would need to be defined in a real program. The **LOGGER.log(Level, String, Throwable)** method stores the throwable in the `LogRecord`. **The formatter/handler must support it** to display the stack trace; the minimal formatter in Section 6 only prints the level and message, so it will not show the stack trace if used as-is.

Do not log only **ex.getMessage()** and lose the cause chain. At the same time, avoid logging the same exception at every layer of processing, which multiplies log lines and makes it harder to locate the original event.

### 10.3. Structured Logging in Projects

In larger applications, consider a logging framework/encoder that supports **structured fields** (such as JSON) instead of concatenating every message manually with Java strings. Libraries such as SLF4J with Logback or Log4j 2 offer stronger configuration capabilities, though the specific API, version, and encoder determine how key-value pairs, context, and throwables are added. **JUL can use a custom formatter**, though the example here focuses on searchable records using the plain JDK.

## 11. Security, Sensitive Data, and Search Limits

The more logs are centralized and indexed, the broader the set of people and systems that can access them. Therefore:

- **Never log passwords, access tokens, API keys, cookies, private keys, payment card numbers, or sensitive request payloads** in raw form.
- **Do not log entire HTTP headers, request/response bodies, or object.toString() by default**; they can accidentally contain secrets and personal data.
- If you need to identify a business entity, log only a **non-sensitive internal ID** or a value masked according to policy. Do not assume every business ID is safe.
- For untrusted input, sanitize or handle **newlines, quotes, and escaping** to prevent log injection (forging log lines or fields).
- Set appropriate access controls, **retention** periods, and deletion policies. A field that is very convenient for searching may still be inappropriate to collect.
- **Do not use unbounded per-item values as metric labels.** A request ID is great for correlating logs and traces, but it can cause extremely high cardinality if used as a label in a metrics system.

A well-designed message also accounts for cost. Large records, many fields, or long stack traces increase the volume of data transmitted and stored. Excessive logging can drown out important events; continuous quantitative measurements such as error counts, throughput, and latency percentiles should use metrics where appropriate.

## 12. Common Mistakes When Designing Messages

| Mistake | Consequence | How to Fix |
| --- | --- | --- |
| Overly generic messages like “An error occurred” | Impossible to search by component or cause | Include event, outcome, and appropriate errorCode/errorType |
| Changing event names across call sites | Missed records when searching for the same event type | Establish a stable naming/code convention |
| Embedding IDs into the event name | Cannot filter a single event type simply | Use a fixed event name and a separate ID field |
| Searching requestId with an ambiguous substring | Easily matches req-1 against req-101 | Query by parsed field or exact field boundaries |
| Putting raw data containing newlines into messages | Log lines can be split or forged | Escape properly or use a structured encoder |
| Logging exceptions using only their message | Missing stack trace and root cause | Pass the Throwable when needed and verify the formatter |
| Omitting timestamp or time zone | Difficult to narrow down incidents by time | Emit standard timestamps with an explicit time zone |
| Using different field names on every line | Queries and aggregations become complex | Use a consistent schema and field names |
| Logging too many fields and large payloads | Wastes storage and risks exposing sensitive data | Log the minimal fields needed for diagnosis |
| Expecting logs when the level is not enabled | Events are dropped at the output destination | Check logger, handler/appender thresholds, and filters |
| Treating missing logs as proof code did not run | Wrong conclusions when logs are filtered, dropped, or delayed | Cross-check metrics, traces, and actual system state |

## 13. How to Verify Whether a Message Is Truly “Searchable”

Before shipping a log pattern into an application, you can run through a quick checklist:

1. **Ask investigation questions:** “How do I find all payment retries?”, “How do I find logs for req-42?”, “How do I find failed requests slower than 2 seconds?”
2. **Identify the fields needed for filtering:** `event`, `service`, `requestId`, `outcome`, `errorCode`, `durationMs`.
3. **Check consistency:** does the same meaning always use the same event name and the same field/data type?
4. **Test with special-character inputs:** are values containing spaces, equals signs, quotes, Unicode, or newlines escaped properly?
5. **Confirm output destination and configuration:** does the event pass the level threshold, filters, handlers/appenders, and collector?
6. **Test searching with real tools:** search for a specific event and a specific request ID; verify nothing is missed and no look-alike values match by mistake.
7. **Review security and cost:** ensure no secrets are exposed, payloads are not oversized, and field counts stay controlled.
8. **Account for incident conditions:** log ingestion systems can lag, sample, or drop data; logs are not absolute proof.

Verifying with real tools is essential because **queryability depends on both the format and the collection pipeline**, not just the logging statement in Java.

## 14. Knowledge Check

**Q1.** Why is `event=payment.failed` easier to search than “Payment error occurred”?

**Answer:** A stable event name acts as a consistent lookup key for the same type of event across multiple call sites, avoiding dependence on language or changing phrasing.

**Q2.** Two requests have IDs `req-1` and `req-101`. Is searching for the substring **requestId=req-1** accurate?

**Answer:** Not guaranteed. That substring also appears inside **requestId=req-101**. You should parse it into a field and query by exact value, or use clear boundary rules when working with plain text.

**Q3.** Is a `key=value` message enough for the system to understand that `durationMs` is a number?

**Answer:** Not automatically. The collector needs an appropriate parser/schema and type conversion. JSON with numeric values transmits a typed representation, though the backend still has to parse it properly.

**Q4.** Should you log the entire request body to make debugging errors easier?

**Answer:** Not by default. The body can be very large or contain sensitive information. Choose the minimal fields with diagnostic value and follow security policies.

**Q5.** A program calls `LOGGER.warning`, yet no log appears in the file. Does that prove execution never reached the call?

**Answer:** No. It also depends on log levels, filters, handlers, output destinations, buffering, collection, retention, and potentially log transport failures.

**Q6.** You need to find all logs for a request that flows through multiple services. Which field is useful?

**Answer:** **requestId or traceId** propagated consistently across services, together with timestamp, service, and event to reconstruct the processing steps.

**Key Takeaway:** A **searchable log message** needs **a meaningful and stable event, consistent fields, correlation context, a parseable format, and safe data**. Writing good messages is the first step; you also need proper logging configuration and collection pipelines for real-world search and analysis to be reliable.
