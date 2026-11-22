# Log-Producing Applications in Java Logging Architecture

In a logging architecture, **the application is where events originate** (the log producer): the source code observes something that just happened, decides whether to log it, sets the level, message, and context, and then calls the logging API. Downstream components then decide how to filter, format, route, and store the record.

Good design starts with **event semantics in the application**. A powerful backend cannot automatically fix messages that lack context, logs at the wrong level, exposed sensitive data, or the same error logged across five call-stack layers.

## 1. Role and Boundaries of the Log-Producing Application

Typical logical flow:

~~~text
User / scheduler / message / other system
                     |
                     v
      Application processing business logic
                     |
       Observation point for meaningful events
                     |
     Call Logger with level, message, context
                     |
                     v
        Logging API / facade (if any)
                     |
                     v
   Backend -> filter -> handler/appender -> destination
                     |
          stdout / stderr / file / collector
~~~

The application actively chooses **what is worth logging** and **which facts are permitted to be logged**. Downstream layers can automatically add timestamps, logger names, thread names, format as JSON, change output destinations, or drop events based on configuration.

A **logger call** does not equate to **the log having been stored successfully**. A record can still be dropped by a level/filter, fail while writing to a file, or fail to be forwarded by the collection pipeline. Therefore, do not use logging success as a condition to confirm a business transaction.

Three layers of responsibility should be distinguished:

| Component | Primary Responsibility | Example |
| --- | --- | --- |
| Application code | Decides when an event occurs and its content | Log INFO after an order is accepted, WARN when input is rejected |
| Logging API and backend | Receives log events, filters, formats, dispatches | JUL, SLF4J with Logback, Log4j 2 |
| Collection and storage infrastructure | Forwards, indexes, searches, retains records | Container stdout → collector → log search system |

Not every application has all three as separate layers. A small program may write directly to the console via JUL; an application deployed across multiple instances typically sends stdout to a centralized collection system.

## 2. Where to Log in the Business Flow?

Logs are valuable when they answer a specific operational or diagnostic question: **what happened, in which component, for which request, and what was the outcome?**

Commonly useful logging points:

1. **Entry/exit boundaries:** a request is received, a scheduled job starts/finishes, a message is processed. For high traffic, consider DEBUG level, sampling, or summary logs instead of one line per operation.
2. **Significant state transitions:** an order is created successfully, a task enters a waiting state, an action is rejected due to business rules.
3. **External system communication:** calls to a service, database, queue, or storage fail, time out, retry, fall back, and their final outcome.
4. **Anomalies worth investigating:** unexpectedly invalid data, near-exhausted resources, circuit breaker opening, unrecoverable errors.
5. **Lifecycle events:** service ready to serve, relevant configuration loaded, shutdown completed.

There is no need to log every entry/exit of every method at INFO level. Excessive density drowns out important events, increases storage costs, and impacts performance.

### Choosing Where to Log and Avoiding Duplication

Suppose the repository layer encounters a timeout error, the service layer retries twice, and then the HTTP controller returns an error. If the repository, service, and controller all call `logger.error` with the same stack trace, a single failure becomes three noisy ERROR records.

A practical principle is to **log the event at the layer that has enough context to explain the decision**:

- Lower layers can log DEBUG for transient attempts, or simply throw an exception with its cause.
- The layer that owns retries can log WARN for notable failed attempts and fallback outcomes.
- The layer that decides the final outcome logs ERROR **once** if the request actually fails.

This is a design guideline, not a ban on logging across multiple layers. Each layer can still log its own events if they carry **different information**, such as database call duration versus final HTTP status.

An error handled completely along a normal path may not need ERROR. For example, a user entering an invalid quantity is usually a **controlled business rejection**, not an infrastructure incident.

## 3. What Should a Log Event Contain?

A good log event has **stable semantics** and **just enough context**. Sample data fields:

| Field | Meaning |
| --- | --- |
| timestamp | Event time, typically recorded by the logging system in UTC or with an explicit time zone |
| level / severity | Importance level: INFO, WARN, ERROR… |
| logger / component | Class, package, or component emitting the event |
| event | Stable event name, e.g. order_accepted or payment_retry_exhausted |
| message | Short, human-readable sentence describing the event |
| requestId / correlationId | Identifier linking records belonging to the same request or processing flow |
| traceId / spanId | Link to distributed tracing if the system integrates with it |
| orderId / jobId | Identifier of the relevant business entity, if permitted to log |
| durationMs / attempt / outcome | Metrics and outcome aiding investigation |
| exception | Exception type and stack trace when useful for error handling |

**Not every event needs every field.** Choose a meaningful set of fields with consistent names and stable data types. For example, an INFO log recording a successful order typically needs event, orderId, and requestId; an ERROR due to a connection failure might need service, attempt, timeout, and exception.

A structured record can be envisioned as follows; this is a **format illustration**, not the default output of JUL or SLF4J:

~~~json
{
  "timestamp": "2026-11-09T10:15:30Z",
  "level": "INFO",
  "logger": "com.example.OrderService",
  "event": "order_accepted",
  "message": "Order accepted",
  "requestId": "req-101",
  "orderId": "ord-7",
  "units": 3
}
~~~

An event name like **order_accepted** is easier to filter and aggregate than a message that varies per code branch. Order ID, request ID, and metrics should be separate fields when the backend supports structured logging; packing everything into a single string is still readable but harder to query accurately.

### Distinguishing Message, Event, and Context

- **Event**: event category for grouping, e.g. order_rejected.
- **Message**: human-readable explanation, e.g. Order rejected because units are invalid.
- **Context**: facts explaining the specific case, e.g. requestId, orderId, outcome.

Keeping event names and keys stable prevents dashboards, queries, and alerts from breaking when message wording is improved.

## 4. Choosing Log Levels from the Application's Perspective

With SLF4J-style APIs, the five common levels are TRACE, DEBUG, INFO, WARN, and ERROR. Level names and mappings may differ in JUL; for example, JUL uses FINE and WARNING instead of DEBUG and WARN.

| Level | When Should the Application Emit It? | Example |
| --- | --- | --- |
| TRACE | Very detailed tracing, enabled only during deep investigation | Internal steps of a calculation or processing flow |
| DEBUG | Development/diagnostic information, typically disabled in production | Values deciding a branch, sanitized internal retry state |
| INFO | Meaningful normal operational milestones | Service ready, import completed, job finished |
| WARN | Anomaly needing attention, but the application can still handle or recover | Using fallback, continuing retries, input rejected at an unusual rate |
| ERROR | An operation or component has failed and requires attention | Unable to complete transaction due to unavailable dependency, job failed after all retries |

Do not assign ERROR to every exception or WARN to every invalid user input. What matters is **actual impact and recoverability**, not just the exception name.

Remember that the log level requested by the application is not the final log level emitted. If the application calls DEBUG while the backend filters from INFO upward, the event will not appear. When logs are missing, check both the emitting code and the runtime configuration.

## 5. Java 17+ Example: Application Actively Emitting Logs with JUL

To observe the application side accurately, use `java.util.logging` (JUL) built into the JDK. The following example produces two different business outcomes, emits events at decision branches, carries a correlation ID, and avoids logging raw input data.

Create **AppLogDemo.java**:

~~~java
import java.util.logging.ConsoleHandler;
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class AppLogDemo {
    private static final Logger LOG =
            Logger.getLogger(AppLogDemo.class.getName());

    public static void main(String[] args) {
        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.INFO);

        ConsoleHandler console = new ConsoleHandler();
        console.setLevel(Level.ALL);
        console.setFormatter(new Formatter() {
            @Override
            public String format(LogRecord record) {
                return record.getLevel().getName() + " "
                        + formatMessage(record)
                        + System.lineSeparator();
            }
        });
        LOG.addHandler(console);

        acceptOrder("req-101", "ord-7", 3);
        acceptOrder("req-102", "ord-8", 0);
    }

    private static void acceptOrder(String requestId,
                                    String orderId, int units) {
        LOG.fine(() -> "event=validation_started requestId=" + requestId);

        if (units <= 0) {
            LOG.log(Level.WARNING,
                    "event=order_rejected requestId={0} orderId={1} reason=invalid_units",
                    new Object[]{requestId, orderId});
            return;
        }

        LOG.log(Level.INFO,
                "event=order_accepted requestId={0} orderId={1} units={2}",
                new Object[]{requestId, orderId, units});
    }
}
~~~

Compile and run:

~~~bash
javac AppLogDemo.java
java AppLogDemo
~~~

Exact output from **ConsoleHandler to stderr**:

~~~text
INFO event=order_accepted requestId=req-101 orderId=ord-7 units=3
WARNING event=order_rejected requestId=req-102 orderId=ord-8 reason=invalid_units
~~~

Explanation:

1. **acceptOrder** is where the acceptance or rejection outcome is known. Therefore, log events are emitted at the decision branches, not immediately upon entering the method.
2. Each event has a stable name and `requestId` to correlate with the request. Order ID, quantity, and reason are useful facts; the example does not log payment details or the full payload.
3. `LOG.fine` accepts a **Supplier**: if the FINE level is not enabled, that message content does not need to be constructed. Here the Logger is set to INFO, so the FINE record does not appear.
4. `LOG.log` with parameters **{0}, {1}, {2}** uses JUL's message formatting mechanism. This is not SLF4J's **{}** syntax.
5. `ConsoleHandler` is configured with level ALL and a fixed formatter for easy inspection, while parent handlers are disabled to avoid duplicate printing via the root logger. In a real application, this configuration typically lives in the startup/backend layer rather than being repeated in every business class.

The example was verified with javac/java. The **WARNING** level was chosen to illustrate an abnormal situation; in a production API or service, a routine invalid-input request may only need DEBUG or no separate log, depending on frequency and operational policy.

## 6. Logging via SLF4J in Multi-Library Applications

In real-world applications, business code typically uses a facade such as SLF4J. This allows code authors to emit logs without coupling individual classes directly to Logback or Log4j Core.

The following snippet illustrates **part of a class using SLF4J 2.x**; `slf4j-api` and a suitable provider/backend are required to run standalone:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

final class OrderService {
    private static final Logger LOG =
            LoggerFactory.getLogger(OrderService.class);

    void accept(String requestId, String orderId, int units) {
        LOG.atInfo()
                .addKeyValue("event", "order_accepted")
                .addKeyValue("requestId", requestId)
                .addKeyValue("orderId", orderId)
                .addKeyValue("units", units)
                .log("Order accepted");
    }
}
~~~

The fluent method **atInfo().addKeyValue(...).log(...)** creates a message with key/value pairs when supported. **Do not assume JSON output by default**: the backend and layout/encoder must be configured to render key/value pairs. For example, with Logback, the pattern may need a component dedicated to key/value pairs; the actual format depends on configuration.

With standard SLF4J methods, parameterization like:

~~~java
LOG.info("Order {} accepted, units={}", orderId, units);
~~~

avoids string concatenation in the calling code and is convenient for the logging implementation. However, the form above typically embeds values into the formatted message, whereas structured key/value pairs support clearer field-based querying when the backend preserves structure.

When logging an exception, pass the exception to the API in the proper position:

~~~java
try {
    callExternalService();
} catch (RuntimeException ex) {
    LOG.error("event=external_call_failed requestId={}", requestId, ex);
    throw ex;
}
~~~

This is an **illustrative snippet**, assuming variables/methods are declared in an outer context. Only log and rethrow when that layer genuinely needs to record its own context; if an outer layer also logs the same error, agree on which layer owns it to avoid duplicate stack traces.

## 7. Context by Request, Thread, and Asynchronous Tasks

In applications handling many requests, log lines from different users can interleave. A Correlation ID/trace ID lets you reconstruct the sequence of related events without relying on log line order.

For an application to emit genuinely useful logs, establish context at the **entry point** and propagate it to where processing occurs:

- HTTP: receive or generate a `requestId`; use the same ID across processing layers and in the response if policy allows.
- Message queue: attach a correlation ID to the message/consumer to link publish and consume steps.
- Scheduled/background job: use `jobId` or `executionId`, even when no HTTP request exists.
- Distributed tracing: when `traceId`/`spanId` already exist from a tracing system, add them to the log context to link logs with traces; do not assume `requestId` and `traceId` are the same field.

Some facades/backends support **MDC (Mapped Diagnostic Context)**: storing key/value pairs per execution context so the layout automatically attaches them to log events. Example snippet **inside a method that already has `requestId` and `logger` variables**:

~~~java
org.slf4j.MDC.put("requestId", requestId);
try {
    logger.info("Processing request");
} finally {
    org.slf4j.MDC.remove("requestId");
}
~~~

If a thread pool is used, threads can be **reused**. Missing the `finally` block can cause the next request to carry stale context from a previous one. MDC is typically bound to a thread; when offloading work to an `ExecutorService`, `CompletableFuture`, or asynchronous threads, **do not assume MDC will be propagated automatically**. You need a context propagation/restoration mechanism provided by the framework or the application itself, along with cleaning up context when the task finishes.

When using structured logging and MDC together, standardize field names to avoid emitting two `requestId` fields with different values.

## 8. Asynchronous Tasks, Multiple Instances, and the Meaning of Log Order

When multiple threads or multiple instances emit logs concurrently:

- Events from different threads can interleave; do not infer business order solely from line position in a file.
- Producer machine timestamps may suffer from clock skew; the time a collector receives a log may differ from when it was emitted.
- Retries can produce multiple events of the same type; use `requestId`, `attempt`, or `eventId` if individual attempts need to be distinguished.
- The backend may write synchronously or push to an asynchronous queue; queue configuration, backpressure, priority levels, and shutdown behavior affect latency and potential log loss.
- A logger statement called just before a process crashes **does not guarantee** the event reached the centralized storage system.

Therefore, logs are suited for diagnostics and observability, whereas systems requiring **guaranteed non-loss of business events** must use dedicated business mechanisms such as transactional/outbox persistence or an audit trail with explicit rules. Do not turn console log strings into the sole source of truth to confirm payment collection or order recording.

## 9. Performance When the Application Emits Logs

Logging cost comes from multiple operations: constructing messages, serializing data, capturing stack traces, writing to appenders, and shipping to external systems. Applications should avoid creating unnecessary work, especially on hot paths.

### Conditional Message Construction

Example to avoid when DEBUG is disabled:

~~~java
logger.debug("expensive state: " + buildLargeDebugDump());
~~~

The **buildLargeDebugDump()** method is still called before the logger checks the level. With SLF4J, you can use:

~~~java
if (logger.isDebugEnabled()) {
    logger.debug("expensive state: {}", buildLargeDebugDump());
}
~~~

This is an illustrative snippet; `buildLargeDebugDump` is assumed to be defined. If values are already available and cheap to compute, using placeholders is usually sufficient; there is no need to wrap every log call in a level check.

### Traffic Control

- INFO for operational milestones; DEBUG/TRACE for detailed data when needed.
- Log once for an outcome event rather than once per loop iteration.
- For high-frequency events, consider rate limiting, sampling, or count aggregation; do not randomly drop rare, important errors.
- Limit message/payload length and field count; avoid logging objects with expensive `toString()` methods or accidentally pulling an entire object graph into a record.
- Monitor CPU, I/O, storage growth rate, and async queue full conditions. The policy to drop logs or block tasks when full must be a deliberate choice.

## 10. Protecting Data at the Logging Source

**The application is the most convenient place to prevent sensitive data from entering the pipeline.** Once a message has been written to the collector, removing it from all backups and downstream systems can be very difficult.

Do not put directly into logs:

- Passwords, tokens, API keys, session cookies, Authorization headers.
- Payment card details, personal secrets, and payloads containing sensitive data.
- Entire requests/responses or SQL parameters when allowed fields have not been determined.
- Exception contents or user-supplied values if they may contain secrets, sensitive data, or overly long strings.

Prefer an **allowlist of necessary fields** over logging an entire object and trying to mask it afterward. For identifiers, consider using internal IDs or truncated values instead of private content.

Untrusted input values may contain newline or control characters. If concatenated directly into text, an attacker can forge log records or corrupt display formatting. Use structured fields and an appropriate encoder; for text logs, sanitize/escape untrusted data before emitting.

Regardless of the backend used, log viewing access control and retention policies still need to be configured at the infrastructure layer.

## 11. How Do Logs, Metrics, Traces, and Audits Differ?

| Data Type | Primary Question | When to Use? |
| --- | --- | --- |
| **Log** | Which specific event occurred and in what context? | Error investigation, root-cause analysis, tracking task outcomes |
| **Metric** | How many events, at what rate, for how long? | Dashboards, threshold alerting, trend observation |
| **Trace** | Which services/spans did a request traverse and where was time spent? | Distributed flow and latency analysis |
| **Audit record** | Who performed a regulated action, when, and what changed? | Accountability, auditing, action history requiring high reliability |

A log line can carry `durationMs`, but it does not replace distribution-based latency metrics. A `requestId` helps correlate logs, but it does not replace a distributed tracing span tree. An INFO record saying `payment_success` does not inherently provide the durability, integrity, and access control guarantees of a dedicated audit system.

These signals complement one another; log events with consistent `eventId`/`traceId` make cross-referencing between sources easier.

## 12. Common Application-Side Design Mistakes

| Symptom | Cause at Producer | How to Improve |
| --- | --- | --- |
| Thousands of INFO lines for one request | Logging every method entry/exit and every loop iteration | Choose decision milestones; move details to DEBUG/TRACE |
| Cannot tell which request a log belongs to | Missing correlation ID, job ID, or trace context | Attach context at entry point, propagate properly across layers and async boundaries |
| Continuous WARN/ERROR despite normal application behavior | Assigning levels by exception type instead of actual impact | Classify by outcome and required action |
| Multiple identical stack traces for one error | Multiple layers logging and rethrowing the same error | Designate the layer owning the final outcome log and distinct context per layer |
| Logs contain sensitive data | Logging raw payloads, headers, `object.toString()` | Allowlist fields, mask/redact before calling the logger |
| DEBUG slows down the program even when disabled | Building large strings or computing debug dumps before the call | Lazy supplier, placeholders, `isDebugEnabled` when computation is expensive |
| Context from request A appears in request B | Not clearing MDC on thread pools or improper async propagation | `try/finally` context cleanup, controlled propagation |
| Records missing from expected destination | Wrong level, backend, filter, or output destination | Check the runtime path from logger to appender/collector |
| Using logs to decide whether a transaction succeeded | Confusing diagnostic logs with durably persisted events | Rely on transactions/state and appropriate audit/outbox mechanisms |

### Investigation Workflow When Logs Are Missing or Wrong

1. **Verify business conditions:** was the code branch actually executed? Was there an early return or exception before the log statement?
2. **Check emit level:** is the logger enabled for that level at runtime?
3. **Check context/message:** does the case being searched have the right ID, a stable event name, and normalized data?
4. **Check downstream processing:** do the API, provider/backend, filter, appender, and destination match?
5. **Cross-check environment:** is the log going to stderr instead of stdout, another container, or a different system?
6. **For async:** inspect queue, shutdown, sampling, and context propagation.

Steps 1–3 are the producer's responsibility; the remaining steps belong to logging configuration and infrastructure. Separating them prevents changing log levels or scattering extra logs indiscriminately when the real issue lies in the pipeline.

## 13. Applied Exercise

Consider an inventory synchronization job: a worker receives a `jobId`, calls an external API, retries up to three times, and eventually succeeds or fails. Identify:

- **INFO:** a `job_completed` event after the job finishes, including `jobId`, `processedCount`, `durationMs`.
- **WARN:** a `retry_scheduled` event when a notable transient error occurs, including `jobId`, `attempt`, `category`, and wait time, without logging secrets from the request.
- **ERROR:** a `job_failed` event when all retries fail, containing `jobId`, the appropriate exception, and final state.
- **DEBUG:** internal information aiding investigation when verbose level is actively enabled.

Self-check: does each event have a stable name; are recovered errors distinguished from final errors; is the same stack trace logged repeatedly; is `jobId` propagated across worker threads; does the log statement cause large payloads to be serialized on every attempt?

## 14. Key Principles to Remember

An application logs well when it identifies **meaningful events**, assigns **levels matching impact**, records **traceable context**, maintains a **consistent schema**, and **filters sensitive data at the source**. The logger is only the emission point; events still depend on the backend, filters, and collection pipeline before they can be found.

When designing, start from the questions operators need to answer, and only then decide where to call the Logger and which fields to record. A few well-placed, context-rich events are usually far more useful than large volumes of unstructured logs.