# Message Content in Java Logging

A **log message** is the content supplied by an application when emitting a log event. A useful message helps answer: **what happened, what was the outcome, where did it happen, which request/entity does it relate to, and what should an operator pay attention to?**

In Java, a log event can include a **message template**, parameters, level, logger name, timestamp, thread, exception, and context fields. **The message is only one part of a log event**: other components may be added by the logging framework or backend. Message quality is determined by the author of the business code; the backend cannot automatically add business information that the application never recorded.

## 1. What Should Good Message Content Answer?

The important information depends on the event, but it usually falls into five categories:

1. **Event/action:** request received, order accepted, sync job started, external service call failed.
2. **Outcome:** completed, accepted, rejected, retrying, failed. Do not describe a step as "completed" when the work has only just started.
3. **Related identifiers:** requestId, orderId, jobId, messageId, or traceId if permitted to log.
4. **Actual reason:** invalid_quantity, upstream_timeout, configuration_missing, or a meaningful reason code. Do not speculate about causes without evidence.
5. **Useful metrics:** attempt, processedCount, durationMs, retryDelayMs; use clear units.

Not every message needs all five categories. A service startup might only need `event=service_ready` and the component name; a retry error needs the dependency, attempt, reason, and outcome as well.

| Uninformative Message | Clearer Message | Benefit |
| --- | --- | --- |
| `"Done"` | `"event=inventory_sync_completed jobId=job-42 processedCount=180 durationMs=560"` | Identifies the task, count, and duration |
| `"Error calling service"` | `"event=pricing_call_failed dependency=pricing-api requestId=req-14 reason=upstream_timeout"` | Shows which system, which request, and why |
| `"Invalid data"` | `"event=order_rejected orderId=ord-7 reason=invalid_quantity"` | Shows which rule was violated without logging the raw payload |
| `"Retry"` | `"event=inventory_sync_retry_scheduled jobId=job-42 attempt=2 delayMs=500 reason=timeout"` | Distinguishes a retry from a final failure |
| `"Started"` | `"event=batch_import_started jobId=job-42 sourceType=csv"` | Shows which job started |

The entries in the second column are text examples following a `key=value` convention. To query by field reliably, emit values as **structured fields** when supported by the API/backend, rather than only concatenating them into a string.

### Log Messages Differ from User-Facing Messages

A UI message might say `"Payment unsuccessful. Please try again."` because its goal is to guide the user. Logs for operations should contain controlled technical details, such as `payment_authorization_failed`, `requestId`, `dependency`, `attempt`, `reason`, and the related exception.

Nor should log text be relied upon as the sole proof that a transaction succeeded; business state must be recorded using an appropriate data storage mechanism with dedicated reliability guarantees.

## 2. Distinguishing Message, Metadata, and Context

Consider an illustrative log record:

~~~text
2026-11-09T10:15:30Z INFO com.example.OrderService
event=order_accepted outcome=accepted requestId=req-101 orderId=ord-7 quantity=3
~~~

- **Timestamp**, **level**, **logger name**, and sometimes **thread** are typically added by the logger/backend at the formatting layer. There is no need to insert them manually into every message.
- **Message** states the event and outcome, for example `order_accepted`.
- **Context** is data that helps locate related records, such as requestId, orderId, traceId. It can live in the text, parameters, MDC, or structured fields.
- **Throwable** carries the error context and stack trace when passed to the logging API. Do not treat the exception name or `ex.getMessage()` as a substitute for the full exception.

A message should not repeat the timestamp, level, and class name if the backend already outputs them consistently. If the application manually logs the time using `LocalDateTime.now()` while the backend records the timestamp in a different time zone, the two values can mislead investigators.

### Message Templates and Dynamic Values

To make grouping events easier, keep a single meaningful template and pass dynamic values as parameters:

~~~text
Template: event=order_accepted orderId={0} quantity={1}
Values:   ord-7, 3
Rendered: event=order_accepted orderId=ord-7 quantity=3
~~~

Here `order_accepted` is the **stable event name**, while `ord-7` and `3` are the values for this execution. Parameterization generally makes code more readable and avoids string concatenation at the call site; however, formatting behavior, deferred parameter evaluation, and structure preservation depend on the specific API/backend.

## 3. Conventions for Message Content

An easily recognizable text convention is:

~~~text
event=<stable_name> outcome=<state> requestId=<id> entityId=<id> reason=<code>
~~~

This is a **suggested template**, not a requirement that every record contain every key. When establishing conventions for a project:

- **Stable event names:** use a consistent style such as `snake_case`: `order_accepted`, `payment_failed`, `inventory_sync_completed`. Do not rename an event just because you reworded the human-readable phrasing.
- **Outcome is the state known at log time:** `retrying` differs from `failed`; `rejected` differs from an infrastructure error.
- **Consistent reason codes:** `invalid_quantity` differs from `upstream_unavailable`. Do not turn dynamic exception messages into an unbounded list of reason codes.
- **Uniform key names:** avoid calling the same request ID `req` in one place, `correlation_id` in another, and `requestId` in a third.
- **Metrics with units:** `durationMs=250`, `delayMs=500`; do not log `duration=250` when readers cannot tell the unit.
- **Enough context, low noise:** a log event usually only needs a few useful values, not the entire request body or an object's `toString()`.
- **Consistent language:** event names, field keys, and reason codes should remain stable across deployments. Human-readable messages can use the team's shared language, but do not translate key names inconsistently.

In plain-text logs, the `key=value` format does not automatically guarantee that parsers will handle values containing spaces, newlines, or equals signs correctly. For arbitrary data, structured fields and properly escaping encoders are more reliable.

## 4. Message Templates in Java: JUL and SLF4J

Java logging systems do not share a single placeholder syntax. You must know which API the codebase uses.

### java.util.logging (JUL)

JUL can format message templates with indexed placeholders `{0}`, `{1}`, ... via `Formatter.formatMessage(LogRecord)`:

~~~java
import java.util.logging.Level;
import java.util.logging.Logger;

// Illustrative snippet inside a method.
Logger logger = Logger.getLogger("com.example.orders");
String orderId = "ord-7";
int quantity = 3;

logger.log(Level.INFO,
        "event=order_accepted orderId={0} quantity={1}",
        new Object[]{orderId, quantity});
~~~

This snippet is not a standalone program. The final output is determined by JUL's formatter/handler. The `{0}` pattern is a parameter index, **not** SLF4J's `{}` syntax.

One benefit of passing a parameter array is that the application does not concatenate strings before calling `logger.log`; when parameters get formatted depends on the formatter mechanism. However, expressions used to construct the elements of `new Object[]{...}` are still evaluated eagerly in Java. Do not assume all computation becomes lazy.

### SLF4J

With `org.slf4j.Logger` and a compatible backend/provider, message templates typically use `{}`:

~~~java
// Inside a method where logger, orderId, and quantity are available.
logger.info("event=order_accepted orderId={} quantity={}", orderId, quantity);
~~~

The two APIs have different `Logger` types. Calling `logger.info("orderId={}", orderId)` on a JUL `Logger` will not behave like SLF4J, because JUL does not use `{}` placeholders and has different overloads.

Java method arguments are still **evaluated before** the call; when you need to build expensive debug data, you can guard with a level check:

~~~java
if (logger.isDebugEnabled()) {
    logger.debug("event=cache_inspection details={}", buildExpensiveSummary());
}
~~~

This is an SLF4J illustration: `buildExpensiveSummary()` is a hypothetical application method. If values are already available and cheap to access, placeholders are usually sufficient; you do not need to wrap every log statement in an `if`. SLF4J 2.x also provides a fluent/lazy API, though you must use the overloads that actually support deferred evaluation.

An unsuitable pattern on hot paths:

~~~java
logger.debug("Debug dump: " + buildExpensiveSummary());
~~~

Computing the summary and concatenating the string happen even when DEBUG is disabled. Parameterization or a level check is more appropriate depending on the case.

## 5. Complete Java 17+ Example: Content for Three Outcome Types

The example below uses only `java.util.logging` built into the JDK, with no Gradle or Maven required. The program emits three events: an accepted order, a rejected order, and a failed payment step. The message content includes the **event name, outcome, correlation IDs, and reason code when needed**, and demonstrates how to attach an exception.

Create the file **MessageContentDemo.java**:

~~~java
import java.util.logging.ConsoleHandler;
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class MessageContentDemo {
    private static final Logger LOG =
            Logger.getLogger(MessageContentDemo.class.getName());

    public static void main(String[] args) {
        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.INFO);

        ConsoleHandler handler = new ConsoleHandler();
        handler.setLevel(Level.ALL);
        handler.setFormatter(new Formatter() {
            @Override
            public String format(LogRecord record) {
                String exception = record.getThrown() == null
                        ? ""
                        : " | exception="
                        + record.getThrown().getClass().getSimpleName();
                return record.getLevel().getName()
                        + " | " + formatMessage(record)
                        + exception + System.lineSeparator();
            }
        });
        LOG.addHandler(handler);

        LOG.log(Level.INFO,
                "event=order_accepted outcome=accepted requestId={0} orderId={1} quantity={2}",
                new Object[]{"req-101", "ord-7", 3});

        LOG.log(Level.WARNING,
                "event=order_rejected outcome=rejected requestId={0} orderId={1} reason=invalid_quantity",
                new Object[]{"req-102", "ord-8"});

        LogRecord failure = new LogRecord(Level.SEVERE,
                "event=payment_failed outcome=failed requestId={0} orderId={1} reason=upstream_unavailable");
        failure.setParameters(new Object[]{"req-103", "ord-9"});
        failure.setThrown(new IllegalStateException("gateway unavailable"));
        LOG.log(failure);
    }
}
~~~

Compile and run with JDK 17 or later:

~~~bash
javac MessageContentDemo.java
java MessageContentDemo
~~~

**Exact three output lines** written by `ConsoleHandler` to **stderr**:

~~~text
INFO | event=order_accepted outcome=accepted requestId=req-101 orderId=ord-7 quantity=3
WARNING | event=order_rejected outcome=rejected requestId=req-102 orderId=ord-8 reason=invalid_quantity
SEVERE | event=payment_failed outcome=failed requestId=req-103 orderId=ord-9 reason=upstream_unavailable | exception=IllegalStateException
~~~

Analysis:

1. The `LOG.log(Level, String, Object[])` calls pass a **message template and parameters**; `Formatter.formatMessage(record)` substitutes the values into `{0}`, `{1}`, `{2}`.
2. The three event names describe three distinct events; `outcome` and `reason` distinguish success, valid rejection, and system failure.
3. The final `LogRecord` holds both `parameters` and a `Throwable`, allowing the code to separate the message text from the exception cause.
4. The sample formatter **only prints the exception class name** to keep the output short and deterministic. In production, formatters for severe errors typically need to log a **controlled stack trace**; this example is not meant to hide stack traces in real applications.
5. The handler has level ALL and the logger has level INFO. `setUseParentHandlers(false)` prevents duplicate records from parent logger handlers. `ConsoleHandler` writes to stderr by default, not stdout.
6. Using WARNING for invalid input is an illustrative choice. For frequent invalid inputs that are handled properly, a real environment might use a lower level or omit a separate log; choose levels based on operational impact.

Note: the handler is configured inside `main` to keep the example self-contained. In larger applications, formatters, handlers/appenders, and levels are typically configured centrally rather than initialized in every business class.

## 6. Content for Errors and Exceptions

When an exception occurs, the message should describe the **affected operation**, not merely echo the exception name. A good error event can include:

- **Operation**: calling the payment gateway, querying data, importing a file, processing a message.
- **Outcome**: retrying or finally failed.
- **Dependency and scope**: which external service, which requestId/jobId.
- **Reason code**: the identified error category, such as `upstream_timeout`.
- **Throwable**: passed to the logging API when a stack trace is needed to trace the failure path.

SLF4J example inside a method that has `logger`, `requestId`, `orderId`, and `exception`:

~~~java
logger.error(
        "event=payment_authorization_failed requestId={} orderId={} reason=upstream_timeout",
        requestId, orderId, exception);
~~~

In the appropriate SLF4J overloads, a trailing `Throwable` argument is interpreted as the cause so the backend can log the stack trace. This is only an illustrative snippet, not a complete Java class.

Avoid doing this:

~~~java
logger.error("Error: " + exception.getMessage());
~~~

This approach can lose the stack trace and business context. In addition, `exception.getMessage()` may contain URLs, SQL parameters, or sensitive data. Review what data actually enters the logs as well as log access-control policies.

If a lower layer catches an exception, logs it, and rethrows it, and a higher layer also logs the same stack trace, the result can be multiple identical ERROR entries for a single failure. Agree on **which layer owns logging the final outcome**; other layers should only log separate events when they genuinely add information (retries, fallbacks, timing).

Not every exception is an ERROR. A controlled rejection of a business request is different from a job failing after all retries.

## 7. Structured Logging: Message and Fields as Separate Components

An event can be represented in JSON as follows (illustrative; **not JUL's default output**):

~~~json
{
  "timestamp": "2026-11-09T10:15:30Z",
  "level": "INFO",
  "logger": "com.example.orders.OrderService",
  "message": "Order accepted",
  "event": "order_accepted",
  "outcome": "accepted",
  "requestId": "req-101",
  "orderId": "ord-7",
  "quantity": 3
}
~~~

Here `message` is a human-readable sentence; `event`, `orderId`, and `quantity` are separate fields that can be queried, grouped, or counted. If the wording of `message` changes while the event code stays the same, queries by event continue to work reliably.

In **SLF4J 2.x**, the fluent API supports attaching key/value pairs alongside the message:

~~~java
// Illustrative snippet inside a method with a logger of type org.slf4j.Logger.
logger.atInfo()
        .addKeyValue("event", "order_accepted")
        .addKeyValue("outcome", "accepted")
        .addKeyValue("requestId", requestId)
        .addKeyValue("orderId", orderId)
        .addKeyValue("quantity", quantity)
        .log("Order accepted");
~~~

Whether fields appear as JSON or in the console depends on the backend/provider, encoder, and layout. **Calling `addKeyValue` does not automatically turn every backend into a JSON logger.**

When using plain-text logs only, writing `event=...` directly in the message is still useful but has limitations: parsers cannot automatically distinguish numbers from strings, and spaces or newlines in values can break structure. When field-level analysis is needed, use a consistent structured-data pipeline.

## 8. Context: Content That Enables Tracing Across Layers and Services

A single request flowing through a controller, service, and HTTP client can emit logs from different logger names. A message like `"Failed"` does not show that they belong to the same request. Certain identifiers should be attached to the **log event**:

- `requestId` or `correlationId` for a processing chain.
- `traceId`/`spanId` if tracing is integrated; do not automatically equate `requestId` with `traceId`.
- `jobId` or `messageId` for batch/background tasks.
- `orderId`, `batchId`, or business entity IDs when permitted to log.
- `attempt`, `outcome`, and `dependency` for retry steps or external system calls.

These values can be passed via method arguments, structured fields, or context mechanisms like MDC. With MDC, you must propagate, restore, and clear context properly—especially when thread pools or asynchronous tasks reuse threads. If context is not cleared, messages from a subsequent request can carry the `requestId` of a previous one.

**Do not create dynamic logger names per request ID.** Logger names should follow packages/classes; `requestId` is data belonging to each event.

## 9. Protecting Data Directly in Message Content

Messages can travel to the console, files, collectors, search systems, backups, and monitoring tools. Once secrets enter the pipeline, removing them from every storage location can be very difficult. **The application should strip sensitive data right at the point where logs are emitted.**

Do not put directly into messages:

- Passwords, access tokens, API keys, session cookies, Authorization headers, or verification codes.
- Payment card details, private keys, personal data, or unnecessary account details.
- Entire HTTP request/response bodies, SQL parameters, or message payloads unless vetted.
- Object `toString()` outputs that may include private fields or change across versions.
- Exception messages containing user data, sensitive URLs, or unvetted content from external systems.

Prefer an **allowlist of fields**: pick only the values you genuinely need, such as `event`, `reason`, internal `requestId`, `attempt`, and `durationMs`. If a sensitive identifier must be logged, apply masking, truncation, or access controls according to project policy.

### Preventing Log Injection

Untrusted input can contain `\\n`, literal newline characters, control characters, or strings that mimic a log record prefix. If concatenated directly into plain text, a viewer may see a forged event or lose the boundary between records.

- Select which fields to log, enforce length limits, and avoid unnecessary raw input.
- With structured logging, use an encoder that escapes properly; with plain text, normalize/escape control characters according to application conventions.
- Do not treat JUL `{0}` or SLF4J `{}` placeholders as automatic secret-masking or full protection against log injection.
- Review exceptions and stack traces as well before deciding log access permissions.

Proper formatting does not replace storage, retention, or access-control policies.

## 10. Stable Messages Aid Investigation and Alerting

If an application generates a different sentence every time it logs—such as `"Could not call API"`, `"External service failed"`, `"Remote server unavailable"`—monitoring tools struggle to tell whether the three sentences represent the same kind of event.

Separate them into:

- **Event code**: `external_call_failed` — stable event classification.
- **Reason code**: `upstream_timeout`, `upstream_5xx`, `invalid_response` — cause classification.
- **Message**: a clear sentence for operators, such as `"Pricing request failed"`.
- **Fields**: requestId, dependency, attempt, durationMs — varying facts.

Do not build critical alerts by matching an entire free-form message sentence if the system already provides `event`, `reason`, and `level` fields. For text logs without structured fields, you can use a stable conventional event prefix, while making sure you know how the parser handles escaping and quoting.

Event names, keys, and reason codes can be treated as an **observability contract** between the application and dashboards. If you rename them, update queries and check downstream log consumers.

## 11. Message Length, Frequency, and Cost

Message content affects CPU, memory, I/O, network bandwidth, and log storage costs. A few rules of thumb:

1. Log **meaningful events**; avoid INFO on every method call and inside loops.
2. Pass only the required fields; do not serialize an entire object graph "just in case."
3. Use parameterization or lazy computation when possible; check the level before computing an expensive debug dump.
4. Consider sampling, rate limiting, or aggregation for high-volume events; do not suppress rare, critical error events.
5. Cap text fields that could grow too large; prevent values from external systems from producing multi-megabyte log entries.
6. Choose `durationMs`, `processedCount`, or other genuinely useful metrics rather than long, unmeasurable descriptions.

A short message is not automatically a good message: `"Error"` is very short, yet useless for investigation. Aim for just enough detail so a standalone record can be correlated with the event and key facts.

## 12. Common Mistakes When Writing Log Content

| Practice | Consequence | How to Improve |
| --- | --- | --- |
| `"Error"`, `"Done"`, `"Start"` | Unclear operation, outcome, and entity | Use a stable event name and accurate outcome |
| `"Request: " + requestObject` | Verbose, hard to search, risks leaking data | Use an appropriate field allowlist |
| Logging only `ex.getMessage()` | Loses stack trace and context | Pass the Throwable via the proper API |
| Logging `retry_exhausted` on the first retry | Misreports the state | Distinguish retry_scheduled from final failed |
| Message contains full user input | Data leak, log injection | Validate source, escape/encode, and limit length |
| Message wording constantly changes | Text-based queries/dashboards break easily | Keep event and reason codes stable |
| String concatenation with heavy calls at DEBUG | Wastes work even when DEBUG is off | Use isDebugEnabled or lazy API |
| Every layer logs and rethrows the same exception | Multiple duplicate stack traces | Log final error at the layer with sufficient context |
| Manually inserting timestamp and level in message | Redundant, may differ from backend | Let the framework emit metadata |
| Logger name contains dynamic requestId | Hard to configure and manage loggers | Put the ID in context/structured fields |
| Unquoted/unescaped text values | Parser splits fields or lines incorrectly | Use a valid structured encoder |

## 13. Practical Scenario: Inventory Sync Job

Suppose a worker processes an inventory sync job and has up to three attempts to call an API. Structure the message content across the steps as follows:

~~~text
event=inventory_sync_started outcome=running jobId=job-42 source=warehouse
event=inventory_sync_retry_scheduled outcome=retrying jobId=job-42 attempt=2 delayMs=500 reason=upstream_timeout
event=inventory_sync_completed outcome=completed jobId=job-42 processedCount=180 durationMs=560
~~~

If all attempts fail, **replace the completed line** with a different outcome:

~~~text
event=inventory_sync_failed outcome=failed jobId=job-42 attempts=3 reason=upstream_unavailable
~~~

The `completed` and `failed` lines are **two mutually exclusive outcomes**, not two final states of the same job. The application can choose the appropriate level, fields, timestamp, and Throwable on the log event; the snippet above only illustrates the content.

Self-check: for each event, can a reader identify the job, state, reason, and attempt? Did you avoid logging API credentials and the full response body? Are event names and fields consistent for querying?

## 14. Checklist for Reviewing a Message

Before adding or modifying a log statement:

1. Does this event need to be logged at the chosen point and level?
2. Does the message accurately state **what happened** and the **actual outcome**?
3. Is there a stable event name and a meaningful reason code?
4. Are `requestId`/`jobId`/`traceId` or other required identifiers present to find related logs?
5. Are field names, types, and units consistent across the system?
6. Is the parameter syntax correct for JUL or SLF4J?
7. When an exception is present, is the `Throwable` passed so the backend can record a stack trace when needed?
8. Have secrets, unnecessary personal data, large payloads, and dangerous inputs been excluded?
9. Is the cost of constructing the message acceptable when the level is disabled?
10. If a single record is copied on its own, can an operator understand it and find the next related record?

**Remember:** Good log message content expresses **an accurate event, a clear outcome, sufficient context, stable structure, and safe data**. The logging API/backend decides formatting and destination; the application is responsible for the meaning of the message at the point it is emitted.