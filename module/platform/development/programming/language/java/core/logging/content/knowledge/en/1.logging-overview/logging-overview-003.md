# Log Messages and Events in Java Logging

## Learning Objectives

After this lesson, you will be able to: distinguish between **an event that occurred** and **the log message describing that event**; identify the pieces of information in a log record; choose an appropriate severity level; design messages that are searchable, context-rich, and safe; and create, read, and verify logs in Java using the standard **java.util.logging (JUL)** API.

This lesson is part of the **Java Logging Overview** section. The focus is on the meaning and creation of a *log message* for an *event*, without diving deep into the architecture or specialized configuration of Logback, Log4j 2, or centralized log collection systems.

## 1. Events, Messages, and Log Records

An **event** is something that happened at a point in time in an application or system: a user sends a request, an order is created, a database connection drops, authentication fails, or a background job completes.

A **log message** is the content used to **express an observable event or state**. It can be a fixed text string, a parameterized message template, or the descriptive part of a structured record.

A **log record / log entry** is the unit of data produced by the logging system. Beyond the message, a record typically contains the log level, timestamp, logger name, source information, parameters, exception, and other context fields. How it is stored and displayed depends on the API, handler/appender, and formatter.

For example, when an order is successfully created:

- **Actual event:** order OD-42 was created with two items.
- **Message:** “order.created orderId=OD-42 items=2”.
- **Record:** the message above along with the INFO level, timestamp, the logger of the order-processing class, and context fields.
- **Output destination:** console, file, or a log collection system; where it is stored does not change the meaning of the event.

A single event can produce **zero, one, or many** log records depending on observability policies. Conversely, a message like “Starting scheduler” might only report an operational state, not a business event. An *event* in the context of logging is also not inherently a *domain event* or a message sent to Kafka/RabbitMQ: emitting a log does not mean publishing an event for another system to process.

| Concept | Question Answered | Example |
| --- | --- | --- |
| Event | What actually happened? | Payment request was declined |
| Message | What description should humans read? | “payment.declined orderId=OD-42 reason=insufficient_funds” |
| Level | What degree of attention is required? | WARNING for an issue worth noting, depending on context |
| Context | Which request/entity does the event belong to? | requestId, orderId, service |
| Record | What specific logging data is captured? | Timestamp + level + logger + message + metadata |
| Output | Where is the record sent? | Console, file, centralized system |

Events **do not appear in logs automatically**. Application or library code must create a log record; log level configuration, filters, handlers, the health of the log output system, and sampling policies can all determine whether the record is actually emitted. Therefore, **not finding a log entry does not prove that an event never occurred**.

## 2. What Makes a Useful Log Record?

An easy-to-analyze record typically answers “**when, where, what happened, who/what was affected, and what the outcome was**”:

1. **Timestamp:** the time the record was generated. When aggregating across multiple systems, use a format with an explicit time zone, commonly ISO 8601/UTC.
2. **Severity/level:** the severity or level of detail needed for observation. The level is a signal chosen by the developer based on context, not an objective measurement of impact.
3. **Logger/source:** the name of the class, module, or component emitting the log, such as com.example.order.OrderService.
4. **Message/event name:** the action, state, and outcome, such as order.created or order.validation_failed.
5. **Context:** appropriate identifiers such as requestId, traceId, orderId, operation, processing duration, and failure reason.
6. **Throwable (when present):** error type, error message, and stack trace to pinpoint the root cause location.
7. **Structured fields:** service, environment, statusCode, durationMs, etc., if supported by the logging system.

An illustrative JSON record (not the format JUL outputs automatically):

~~~json
{
  "timestamp": "2026-11-09T10:15:30Z",
  "level": "INFO",
  "logger": "com.example.order.OrderService",
  "event": "order.created",
  "message": "Order created",
  "service": "checkout",
  "requestId": "req-8f2",
  "orderId": "OD-42",
  "itemCount": 2,
  "durationMs": 31
}
~~~

In plain text logs, not every field has its own attribute; some information may need to be embedded into the message. **Structured logging** makes it possible to search, filter, and aggregate by field without parsing free-form sentences. Do not equate a “long message” with “lots of useful information”: without correlation identifiers or an action name, a long log line is still hard to diagnose.

## 3. Which Events Are Worth Logging?

Prioritize points that help trace execution flow, detect anomalies, or explain outcomes:

- **Task lifecycle:** start/completion of an important job, processing outcome, record count, execution time.
- **Meaningful state changes:** order created successfully, request rejected, transaction state transition (do not log redundantly in every setter).
- **Integration boundaries:** external service call failures, timeouts, retries, and retry outcomes; include the dependency name, operation, and attempt count.
- **Operational anomalies:** missing configuration, depleted resources, abnormally malformed data, unexpected disconnections.
- **Error-handling paths:** where an error is handled or where the system decides to return a failure result; preserve the original exception when needed.

Avoid logging every assignment, every loop iteration, or the raw data of every request: too many records create noise, add cost, and risk exposing data. For business operations requiring legal/compliance trails, an **audit trail** has specific requirements for completeness, integrity, access control, and retention; do not assume ordinary diagnostic logs satisfy those requirements.

**Distinguish cause from effect:** an HTTP request returning 500 may be the consequence of a timeout to a dependency. A useful record should tell you which call timed out, rather than repeating “request failed” at every layer without adding information. Establish a single responsible logging point for each error to avoid logging the same stack trace at every layer.

## 4. Choosing a Level Based on Event Meaning

JUL provides standard levels in descending order of severity: **SEVERE, WARNING, INFO, CONFIG, FINE, FINER, FINEST**. **OFF** disables logging; **ALL** enables all levels at the corresponding threshold. Not every logging framework names or maps log levels identically to JUL.

| JUL Level | Typical Use | Example |
| --- | --- | --- |
| SEVERE | Serious error where an operation or component cannot function properly | Essential dependency connection fails, preventing request processing |
| WARNING | Abnormal state requiring attention, though the system can continue or has a fallback | Retry due to timeout, using fallback configuration |
| INFO | Normal operational or business milestone worth tracking | Batch completed, order created |
| CONFIG | Configuration information useful at startup or for diagnostics | Processing mode or feature flag enabled (never log secrets) |
| FINE | Details supporting routine debugging | Cache miss, execution branch chosen |
| FINER/ FINEST | Very deep, typically high-frequency details | Internal algorithm steps, safe intermediate values |

Practical guidelines:

- **Do not infer the level solely from the exception name.** An exception caught and handled properly as an expected business branch may not need WARNING/SEVERE.
- **Do not use SEVERE for valid rejection outcomes**, such as an incorrect password, if that is normal handled behavior.
- **Recoverable warnings** should state the recovery mechanism (retry/fallback), final outcome, and attempt count if appropriate.
- **Loss-of-functionality errors** should describe the failed operation, involved component, and original exception; avoid putting sensitive information in the message.
- A log level is a **filtering threshold**, not a guarantee that a record will appear: a JUL logger and each handler can have their own level/filter.

For example: an API call times out once, then succeeds on the second retry—this might be logged at FINE for the timeout if that situation is normal, or WARNING when latency/anomalies need monitoring. If all attempts ultimately fail, the failure event at the processing boundary might be SEVERE. The final level should match the operational expectations of the application.

## 5. Designing Searchable and Context-Rich Log Messages

A good message typically includes **action name + outcome + identifying fields + just enough diagnostic data**. Examples:

| Less Useful | Better | Why |
| --- | --- | --- |
| “Error!” | “payment.authorization_failed orderId=OD-42 provider=bankA reason=timeout” | Identifies operation, entity, dependency, and cause |
| “Done” | “report.generated reportId=R-7 rows=125 durationMs=84” | Includes measurable results |
| “User data: ...” | “profile.update_rejected requestId=req-8f2 reason=invalid_email” | Does not expose profile data |
| “Retrying” | “inventory.lookup_retry skuRef=SKU-8 attempt=2 maxAttempts=3 reason=timeout” | Includes operation and retry state |

Principles:

1. **Name the action and outcome accurately.** Use consistent terms: created, started, completed, rejected, failed, retrying, etc. You can adopt a stable event naming catalog such as order.created.
2. **Attach useful identifiers** instead of vague descriptive strings. Identifiers must be handled according to security policies; requestId/traceId help correlate logs for a single request.
3. **Specify units clearly:** durationMs, bytes, itemCount; avoid writing “time=40” where readers cannot tell the unit.
4. **Prefer parameterization** over expensive string concatenation or repeated formatting. In JUL, placeholders use **{0}, {1}, ...** syntax when passing parameters; some other libraries use **{}**—do not confuse the APIs.
5. **Keep messages concise yet meaningful.** The message and separate fields should complement each other; avoid dumping entire objects, SQL with real data, tokens, or payloads.
6. **Use a stable structure:** arbitrarily renaming events or fields makes monitoring queries, dashboards, and alerts hard to maintain. Message names are part of the observability contract, not a formal business API on their own.

Messages should describe **what is known at the time of logging**. Do not log “order.completed” before saving the order has actually succeeded. In asynchronous systems, logging “message.published” only proves that the publish step completed according to the corresponding API semantics—it does not prove that the consumer has finished processing it.

## 6. Java 17+ Practice: Logging Events with java.util.logging

JUL is built into the JDK, so the example requires no external libraries. Create a file named **LogEventDemo.java** with the following complete content:

~~~java
import java.util.logging.ConsoleHandler;
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class LogEventDemo {
    private static final Logger LOG =
            Logger.getLogger(LogEventDemo.class.getName());

    public static void main(String[] args) {
        // Avoid receiving additional output from the root logger's default handler.
        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.ALL);

        ConsoleHandler handler = new ConsoleHandler();
        handler.setLevel(Level.ALL);
        handler.setFormatter(new Formatter() {
            @Override
            public String format(LogRecord record) {
                String line = record.getLevel().getName()
                        + " | " + formatMessage(record);
                if (record.getThrown() != null) {
                    line += " | cause="
                            + record.getThrown().getClass().getSimpleName();
                }
                return line + System.lineSeparator();
            }
        });
        LOG.addHandler(handler);

        String orderId = "OD-42";
        LOG.log(Level.INFO, "order.created orderId={0} items={1}",
                new Object[] {orderId, 2});

        try {
            Integer.parseInt("two");
        } catch (NumberFormatException ex) {
            LOG.log(Level.WARNING,
                    "order.invalid_quantity orderId=" + orderId, ex);
        }
    }
}
~~~

Compile and run with JDK 17 or later:

~~~bash
javac LogEventDemo.java
java LogEventDemo
~~~

Output of the illustrative formatter (two lines written by **ConsoleHandler to stderr**):

~~~text
INFO | order.created orderId=OD-42 items=2
WARNING | order.invalid_quantity orderId=OD-42 | cause=NumberFormatException
~~~

Explanation:

- **Logger.getLogger(...)** creates or retrieves a logger named after the class. The logger name helps trace the record's source.
- **LOG.setLevel(Level.ALL)** lets all levels pass the logger threshold in the example; **handler.setLevel(Level.ALL)** lets them pass the handler threshold.
- **setUseParentHandlers(false)** prevents the root logger from also emitting the record, which would cause duplicate console output in this demonstration.
- **LOG.log(Level.INFO, ..., new Object[] {...})** keeps the message template and parameters separate in the LogRecord; **Formatter.formatMessage(record)** applies the parameters to the {0}, {1} placeholders.
- **LOG.log(Level.WARNING, message, ex)** attaches the Throwable to the record rather than only saving ex.getMessage(). This preserves the exception details for the handler/formatter.
- The custom formatter here **intentionally displays only the Throwable type** and omits the timestamp/stack trace so the output is easy to compare. In real applications, retain the timestamp, source, trace context, and appropriate stack trace; the **default SimpleFormatter** can display stack traces and timestamps that vary per run.
- **ConsoleHandler** normally writes to stderr, even though users see it in the same terminal window. This is not System.out.println() behavior.

Key takeaway: **the same event** “order OD-42 was created” was represented as an INFO-level message and record; the invalid number parsing situation created **a different event**, recorded as a WARNING record with a Throwable. In real applications, choose the level for invalid input based on context: if it is a routine input error returned cleanly to the caller, WARNING may not be necessary.

## 7. Parameterization, Exception Handling, and Logging Cost

**Parameterization in JUL**:

~~~java
// Illustrative snippet, assuming LOG and orderId are already declared.
LOG.log(Level.INFO, "order.created orderId={0}", orderId);
~~~

When multiple parameters are needed, pass an Object[] array matching the placeholder order. The **{0}** syntax belongs to JUL with MessageFormat, which differs from the placeholder syntax of many logging facades. Use stable field names in messages or structured fields if the backend supports them, rather than just listing unlabeled values.

**Exceptions:** log a Throwable using the overload that accepts a Throwable when diagnostic detail is genuinely needed; merely concatenating ex.getMessage() into a string often loses the error type, cause chain, and stack trace. Avoid catching and logging repeatedly as the same exception is rethrown across layers; it is better to log where sufficient context exists or where the error is translated into a final outcome.

**Performance:** low-level records may be filtered out before output, but Java expressions used to construct arguments are still evaluated before the method call. For messages requiring expensive computation, JUL supports a Supplier to defer string construction:

~~~java
// Illustrative snippet; expensiveSummary() is an expensive operation.
LOG.log(Level.FINE, () -> "cache.snapshot " + expensiveSummary());
~~~

The Supplier is invoked only when the logger determines the level is loggable; never use a Supplier with business side effects, as it may not be called. You can also use **LOG.isLoggable(Level.FINE)** to guard expensive data preparation. A logger-level check does not replace all handler filters, so never rely on logging to execute core logic.

Under high load, logging on every loop iteration or every request can increase I/O and storage costs. Consider levels, record volume, sampling/rate limiting where appropriate, and use **metrics** for aggregated time-series values instead of logging every counter increment.

## 8. Correlation Context: Following a Request Across Components

Consider the flow: API receives request → OrderService → PaymentClient → database. A “timeout” line from PaymentClient without context is hard to link back to the original request. Lines sharing a common **requestId/traceId**, service name, operation, and relevant entity IDs make the journey much easier to follow:

~~~text
INFO  checkout.request_received requestId=req-8f2 orderId=OD-42
WARNING payment.call_timeout requestId=req-8f2 orderId=OD-42 attempt=1
INFO  payment.call_succeeded requestId=req-8f2 orderId=OD-42 attempt=2
INFO  checkout.completed requestId=req-8f2 orderId=OD-42 durationMs=310
~~~

These lines are a **scenario example**, not the stdout of the program in Section 6. In real code, context can be passed directly as parameters or via a thread/request context mechanism provided by the logging library. For asynchronous processing or thread pools, context must be **propagated across execution boundaries and cleared when the scope ends** according to the mechanism in use; do not assume information in ThreadLocal automatically follows every task.

Remember that **log ordering across multiple machines does not always reflect exact causality** due to clock skew, buffering, network delays, or asynchronous writes. Traces and spans model the relationships between processing steps; logs provide the detail. A good observability design typically combines **logs** (event context), **metrics** (trends/counts/aggregated latency), and **traces** (the path of a single request).

## 9. Security, Quality, and Common Pitfalls

**Never put secrets or sensitive personal data in logs.** For example, avoid passwords, access tokens, session cookies, card numbers, payloads containing personal data, or connection strings with credentials. Only log identifiers permitted by policy; if necessary, mask or hash them in a controlled manner per product requirements. The FINE/DEBUG level **is not a safe zone**: debug logging can be enabled in production.

**Sanitize untrusted data.** Strings coming from requests can contain newlines, control characters, or content masquerading as other log entries. Structured logging or proper escaping helps reduce the risk of **log injection**. Never arbitrarily concatenate raw payloads into a record; filter and cap the length of input data before logging according to application policy.

**Common mistakes and how to fix them:**

1. **Generic messages:** “Something went wrong”. Fix by including the operation, component, identifier, and known cause.
2. **Wrong severity level:** every input error logged as SEVERE. Fix by classifying actual impact and the handling path.
3. **Lost exceptions:** only logging ex.getMessage(). Fix by using the Throwable overload when error analysis is needed.
4. **Duplicate logging across layers:** every catch block logs and rethrows. Choose a responsible logging point and add context instead of duplicating the same stack trace.
5. **Logging success too early:** logging completed before the transaction/IO finishes. Move the log statement after the actual confirmation step.
6. **Missing correlation IDs:** lines cannot be linked to a request. Propagate identifiers across synchronous and asynchronous steps.
7. **Log spam or expensive message construction:** use appropriate levels, Suppliers, guards, metrics, or sampling.
8. **Logging sensitive data:** strip or mask data; also check exception messages and objects that are automatically serialized/printed.
9. **Confusing logs with business guarantees:** a written record does not guarantee an event was sent, processed, durably stored, or occurred only once. Business reliability must be guaranteed by proper transaction, queue/outbox, or audit design.

For exceptions, **a stack trace is useful but does not replace a context-rich message**: the stack trace shows where the error originated, while the message should state which operation failed and which entity/request was affected (when that identifier is permitted to be logged).

## 10. Workflow for Choosing and Writing a Log Message

When adding a log statement to code, ask yourself in order:

1. **What happened?** Clearly identify the event and the point at which it is considered a success or failure.
2. **Who needs to read the record?** Developers debugging, operations, or alerting tools; what information helps them act?
3. **Which level is right?** Prioritize impact and operational expectations; avoid turning every business outcome into a system error.
4. **What is the minimum sufficient context?** Action/result, service/logger, requestId/traceId, relevant entity ID, reason, and duration with units.
5. **Is the exception needed?** If root-cause investigation is needed, pass the Throwable to the right overload and avoid duplicate logging.
6. **Is the log safe and scalable?** No secrets/PII, no multiline injection, no expensive messages, and no high-frequency records.
7. **Can it be verified?** Exercise a success flow and a failure flow; verify the level, context, parameters, exception, and absence of duplicate lines.

Mental-check examples:

- Case A: a user enters quantity “two”, and the application returns a valid validation error. **Event:** order.validation_rejected. **Message:** event name + field=quantity + requestId; usually no need for ERROR/SEVERE and do not log the entire raw input.
- Case B: PaymentClient times out once, then succeeds on retry. **Events:** payment.call_timeout and payment.call_succeeded. **Messages:** include attempt and correlation ID; severity depends on how abnormal this is. Never log a final payment.failed if the transaction succeeded.
- Case C: persisting an order fails after all retries. **Event:** order.persist_failed. **Message:** orderId, operation, safe reason code; preserve the Throwable for analysis; log at the layer responsible for handling the failure.

## Self-Check

**Question 1.** Is a message “job completed” enough evidence of which job ran, how many items were processed, and how long it took?  
**Answer:** No. You need jobId, outcome, itemCount, durationMs, and the corresponding operational context.

**Question 2.** Is calling **LOG.log(Level.INFO, "order={0}", orderId)** in JUL the same as the **"order={}"** syntax in some other libraries?  
**Answer:** No. JUL uses indexed placeholders following MessageFormat when passing parameters.

**Question 3.** If you called logger.log with a Throwable, but the sample formatter only prints the class name, does that mean the Throwable was lost?  
**Answer:** No. The Throwable is still stored in the LogRecord; the example formatter intentionally shortened the display. Another formatter/handler can output the stack trace.

**Question 4.** Does seeing no WARNING lines in the console prove there were no anomalies?  
**Answer:** No. A record might not have been created, might have been filtered by the logger/handler, sampled out, or lost due to a problem in the log output pipeline.

**Key takeaway:** An **event** is what happens; a **message** expresses it; a **record** holds the message along with level/context/metadata; a **handler/appender** delivers the record to its destination. Logging at the right time, with the right level and context, produces valuable diagnostic data without compromising security, performance, or business accuracy.
