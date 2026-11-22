# Recording System Behavior with Java Logging

## 1. What is recording system behavior and what is it for?

In a Java program, *system behavior* refers to meaningful events and decisions that occur while the program is running: the application starting up, receiving a request, validating data, accepting or rejecting an operation, calling a dependent service, changing business state, completing a request, or encountering an error.

**Logging** produces records with a timestamp, severity level, source, and context to answer questions such as:

- Which request did the system receive, at what time, and what was the final outcome?
- Which business rule caused an order to be rejected?
- Did a call to a database or external service fail or run slowly?
- Which execution flow do log records across multiple layers or multiple services belong to?
- When an incident occurs, what sequence of events led to the error and where should investigation start?

The goal is to create **an operational evidence trail sufficient to understand what happened and why**, while keeping cost, noise, and data-exposure risk at acceptable levels. Logging does not replace a debugger, metrics, or distributed tracing; each mechanism answers a different kind of question.

## 2. Choosing events worth logging

You do not need to log every statement or every method call. Prioritize **processing boundaries, business decisions, state transitions, and actionable anomalies**.

| Event category | Example stable event names | Required information | Reference level |
| --- | --- | --- | --- |
| Application lifecycle | app.started, app.stopping | service, version, environment | INFO |
| Request receipt and completion | request.received, request.completed | requestId, route template, status, durationMs | INFO or DEBUG depending on traffic |
| Business decisions | order.accepted, order.rejected | orderId, outcome, reasonCode | INFO |
| Dependency operations | inventory.call.failed, storage.retrying | dependency, attempt, errorCode, durationMs | WARNING or SEVERE depending on impact |
| Notable state transitions | payment.confirmed, job.completed | entity, before/after state, correlation ID | INFO |
| Security events | auth.denied, rate_limit.triggered | action type, reason, minimized identifier | INFO or WARNING depending on policy |
| Anomalies and errors | order.persist.failed, queue.consumer.failed | operation, errorCode, exception, requestId | WARNING or SEVERE |
| Detailed diagnostics | cache.lookup, mapper.input.shape | component name, duration, count | FINE/DEBUG, enabled only when needed |

**Note:** A user entering invalid data is an expected business outcome, typically logged at INFO (or lower), and is not a sufficient reason to treat it as a system error. WARNING is for abnormal conditions that may require attention; SEVERE is for serious errors that impact processing. Do not log at INFO for every loop iteration, every element, or every query when data volume is large.

Each event should indicate: **what happened → where → which entity → what the outcome was → why**, within safe information boundaries. Event names should describe the action that occurred, such as `order.rejected`, rather than a vague message like "Something went wrong".

## 3. Designing searchable and correlatable log records

A useful operational log typically includes:

- **timestamp**: when the event occurred; when stored centrally, use a consistent time representation, preferring UTC in ISO 8601 format.
- **level**: the importance/severity level of the event.
- **service/logger**: the service and class/component that emitted the record.
- **event**: a stable event name, for example `order.rejected`.
- **requestId/correlationId**: an identifier linking records belonging to the same request or workflow.
- **traceId/spanId**: when a distributed tracing system is present; these do not appear automatically just from using Java logging.
- **business identifier**: a non-sensitive order ID or task ID, logged only when genuinely needed.
- **outcome/reasonCode**: `SUCCESS`, `REJECTED`, `FAILED`, and a machine-searchable reason code.
- **durationMs, attempt, dependency**: data needed to analyze latency, retries, or integration failures.
- **exception**: the error type and stack trace at the appropriate location, especially for unexpected errors.

Example of a **JSON record illustrating the format**, not the default output of `java.util.logging`:

~~~json
{
  "timestamp": "2026-11-09T12:00:00Z",
  "level": "INFO",
  "service": "order-service",
  "event": "order.rejected",
  "requestId": "req-b2",
  "orderId": "ord-102",
  "outcome": "REJECTED",
  "reasonCode": "INVALID_QUANTITY"
}
~~~

Keep **key names and event codes stable** across releases so dashboards, queries, and alerts do not break. Use appropriately typed values (`durationMs` as a number in JSON), and keep units consistent. When the system does not yet support a JSON logger, you can log messages in `key=value` format; however, to filter reliably by field at scale, you need a proper formatter/encoder or log-parsing pipeline.

Do not put passwords, tokens, API keys, session cookies, card data, full personal payloads, or unnecessary sensitive information into logs. Minimize, mask, or hash identifiers according to applicable policy. Validate untrusted input to prevent forged newlines (log injection); use controlled event codes and `reasonCode` values instead of directly concatenating arbitrary user-supplied messages.

## 4. Log levels in Java

Java SE provides **java.util.logging (JUL)** with common levels: `SEVERE`, `WARNING`, `INFO`, `CONFIG`, `FINE`, `FINER`, and `FINEST`. In many applications using SLF4J, the level names are `ERROR`, `WARN`, `INFO`, `DEBUG`, `TRACE`; these are two level systems from different APIs and should not be assumed to be strictly equivalent in every configuration.

| Intent | Common JUL level | Usage |
| --- | --- | --- |
| Error causing a critical operation failure | SEVERE | Unhandled error or loss of service capability |
| Anomaly, potential degradation, notable retry | WARNING | Slow dependency, repeated retries, fallback mechanism activated |
| Processing/business milestone useful for operations | INFO | Startup, business acceptance/rejection, task completion |
| Startup configuration | CONFIG | Non-sensitive configuration values when genuinely needed |
| Detailed diagnostics | FINE/FINER/FINEST | Internal steps, typically disabled in production |

**Filtering happens in two places:** In JUL, both the `Logger` and the `Handler` have a level. For example, if the `Logger` allows `FINE` but `ConsoleHandler` remains at `INFO`, `FINE` messages will not be displayed. In production, configure log levels according to environment, investigation needs, and traffic volume; avoid leaving overly verbose logging enabled indefinitely.

## 5. Tracing an end-to-end processing flow

Example order-receiving flow:

~~~text
HTTP POST /orders
   |
   +-- request.received         [requestId=req-a1]
   |
   +-- validate quantity
   |      +-- invalid -> order.rejected [reasonCode=INVALID_QUANTITY]
   |
   +-- inventory.reserve
   |      +-- transient error -> inventory.retrying [attempt=2]
   |
   +-- order.persist
   |      +-- real error -> order.persist.failed [errorCode=STORAGE_ERROR]
   |
   +-- order.accepted           [outcome=SUCCESS]
   |
   +-- request.completed        [status=201, durationMs=...]
~~~

These are **illustrative branches**: a single request does not necessarily emit every event. For a successful request, the sequence might be `received → accepted → completed`. For invalid data, the sequence might be `received → rejected → completed` with HTTP 4xx. For a database error, the logs should show the failing step and the handling outcome at the HTTP boundary.

Logging points are typically placed at the API/controller (entry/exit), service (business decisions), adapter/repository (dependency communication errors), and job/consumer (job start/completion). Avoid having every layer log **the same error with the identical stack trace**, as this skews incident counts and makes timelines harder to read. Choose the layer with sufficient context and handling responsibility to log the primary error; when rethrowing, upper layers should add a log only if they provide new, genuinely needed information.

## 6. Standalone Java 17+ example with java.util.logging

The following example simulates two order-processing requests: one valid request and one request with an invalid quantity. Each log record includes the event name, `requestId`, and `orderId`; no sensitive user data is logged.

Save as **SystemBehaviorLogDemo.java**:

~~~java
import java.util.logging.Formatter;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;
import java.util.logging.StreamHandler;

public class SystemBehaviorLogDemo {
    private static final Logger LOG =
            Logger.getLogger(SystemBehaviorLogDemo.class.getName());

    public static void main(String[] args) {
        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.INFO);

        Handler handler = new StreamHandler(
                System.out,
                new Formatter() {
                    @Override
                    public String format(LogRecord record) {
                        return record.getLevel().getName() + " | "
                                + record.getMessage() + System.lineSeparator();
                    }
                }) {
            @Override
            public synchronized void publish(LogRecord record) {
                super.publish(record);
                flush();
            }
        };
        handler.setLevel(Level.INFO);
        LOG.addHandler(handler);

        processOrder("req-a1", "ord-101", 2);
        processOrder("req-b2", "ord-102", 0);
    }

    private static void processOrder(String requestId,
                                     String orderId,
                                     int quantity) {
        LOG.info(() -> "event=order.received requestId=" + requestId
                + " orderId=" + orderId);

        if (quantity <= 0) {
            LOG.info(() -> "event=order.rejected requestId=" + requestId
                    + " orderId=" + orderId
                    + " outcome=REJECTED reasonCode=INVALID_QUANTITY");
            return;
        }

        LOG.info(() -> "event=order.accepted requestId=" + requestId
                + " orderId=" + orderId + " outcome=SUCCESS");
    }
}
~~~

Compile and run with JDK 17 or later:

~~~bash
javac SystemBehaviorLogDemo.java
java SystemBehaviorLogDemo
~~~

**Standard output (stdout)** of this program, in order:

~~~text
INFO | event=order.received requestId=req-a1 orderId=ord-101
INFO | event=order.accepted requestId=req-a1 orderId=ord-101 outcome=SUCCESS
INFO | event=order.received requestId=req-b2 orderId=ord-102
INFO | event=order.rejected requestId=req-b2 orderId=ord-102 outcome=REJECTED reasonCode=INVALID_QUANTITY
~~~

Explanation of the choices in the example:

1. `Logger` is the source that emits events; `Handler` writes logs to an output destination; `Formatter` determines how records are formatted.
2. **setUseParentHandlers(false)** prevents the parent logger's default handler from emitting duplicate records. `StreamHandler` is configured to write to `stdout` for deterministic output while learning; the default `ConsoleHandler` typically writes to `stderr` and uses a different format.
3. Overriding **publish()** calls **flush()** after each record. A plain `StreamHandler` may buffer output, so you cannot assume every log record appears immediately without flushing.
4. Both **setLevel(Level.INFO)** calls control the threshold on both the `Logger` and the `Handler`.
5. Using **LOG.info(() -> ...)** constructs the message via a `Supplier`. When the `INFO` level is disabled, the string concatenation inside the lambda does not need to be evaluated.
6. A rejection due to an input rule is logged at `INFO` because it is a normal business outcome. `WARNING` can be used for genuine anomalies (such as a degraded dependency), rather than raising the level merely because a branch returns a failure outcome.
7. The `key=value` format is used here for learning purposes. In a real system, you should include a UTC timestamp, service name, thread/trace context, and a centralized log-processing pipeline. If values contain spaces or special characters, an encoder or format with explicit escaping is required.

## 7. Logging errors and stack traces in the right place

When catching an unexpected error, logging only the error message is not enough to diagnose the root cause. JUL supports logging an exception together with its stack trace:

~~~java
// Illustrative snippet placed inside a method that already has the requestId variable
// and the exception; not a standalone program.
LOG.log(
        Level.SEVERE,
        "event=order.persist.failed requestId=" + requestId
                + " errorCode=STORAGE_ERROR",
        exception);
~~~

Key difference: the `Throwable` argument is passed into the logging API, allowing a suitable handler/formatter to render the stack trace. The `Formatter` in the standalone example in section 6 **only displays the level and message**, so to print stack traces you need a formatter that supports `Throwable` or to add exception-handling logic to the `Formatter`. You should also choose the log level based on actual impact, rather than defaulting every exception to `SEVERE`.

**Distinguishing business outcomes from technical errors:** invalid data can produce `order.rejected` with a `reasonCode`; losing connection to the data store can produce `order.persist.failed` with an `exception` and impact the request. Do not turn an expected exception into a severe incident just because it is represented by an `Exception` class.

When retrying, log the **attempt count** and the **terminal outcome**: for example `inventory.retrying attempt=2` and `inventory.reserve.failed` when retries are exhausted. Avoid logging a full stack trace on every retry attempt for the same cause; doing so can generate hundreds of repeated log entries and obscure the primary error.

## 8. Correlating logs in concurrent and multi-service processing

In web applications, thread pools and asynchronous execution interleave logs from many requests. Relying solely on thread names or line order is not enough to identify a single request. Use a shared `requestId`/`correlationId` across related steps.

- At the HTTP boundary, generate or accept a trusted `requestId`; validate the format and length of client-supplied IDs, and avoid treating arbitrary headers as raw, unvalidated log data.
- Pass `requestId` through services and repositories. The example in section 6 passes it explicitly as a parameter, which is easy to understand and does not depend on thread state.
- When calling another service, propagate context via headers according to system conventions and ensure the receiving service links the `requestId` or `traceId`.
- With executors, `CompletableFuture`, virtual threads, or asynchronous flows, propagate context properly. **ThreadLocal/MDC does not automatically propagate across all asynchronous boundaries**; when using thread pools, clear the context after the request completes to prevent leaking it into subsequent requests.
- If using OpenTelemetry or a tracing library, `traceId`/`spanId` help link logs to spans. Plain JUL does not automatically generate `traceId`, `spanId`, or distributed context propagation.

For background tasks not directly tied to HTTP, you can use a controlled `jobId` or `messageId` as the correlation ID. These IDs should remain consistent across start, retry, completion, and failure logs.

## 9. Collecting, querying, and operating logs

Typical pipeline: **Java Logger → Handler/Appender → console/file → agent/collector → storage and search system → dashboards/alerts**. The term `Handler` belongs to JUL, while `Appender` is common in Logback/Log4j; the exact implementation depends on the stack. In containerized environments, writing logs to `stdout`/`stderr` for the platform to collect is a common pattern, though encoding, rotation/retention, and log streams still need proper configuration.

Example investigation queries:

- Filter `event=order.rejected` by `reasonCode=INVALID_QUANTITY` to identify rejection patterns.
- Filter `requestId=req-a1` to inspect the event sequence of a single request.
- Search for `event=inventory.retrying` over the last 15 minutes to assess dependency degradation.
- Aggregate `durationMs` from `request.completed` to find slow execution paths; metrics/histograms are usually better suited than logs for continuous latency measurement and SLOs.

Logs help explain **specific execution details**, metrics help identify **trends and rates**, and tracing helps visualize **paths and timing across components**. Do not place the entire observability burden on logging. For legally mandated or tamper-evident auditing requirements, design a **dedicated audit log** with access control, integrity protection, retention, and access governance; standard application logs do not inherently satisfy audit standards.

In production, define: who is allowed to read logs, how long they are retained, whether sensitive data is filtered before storage, which signals trigger alerts, and how expired data is deleted. Control write volume, label cardinality, ingest cost, latency, and I/O bottleneck risks. Asynchronous logging can reduce blocking on business threads but risks losing records on abrupt shutdown; synchronous logging also has overhead and risks blocking threads if the output destination is slow.

## 10. Common mistakes and how to fix them

| Mistake | Consequence | Appropriate practice |
| --- | --- | --- |
| Logging only "start"/"error"/"done" | Cannot identify the action, entity, or reason | Use clearly named events and `reasonCode` |
| Omitting `requestId` | Cannot connect steps across interleaved execution flows | Propagate a correlation ID across appropriate boundaries |
| Logging too much `INFO` inside loops | Log flooding, high storage cost, slower system | Switch to `FINE`/`DEBUG`, aggregate metrics, or sample intentionally |
| Logging secrets or full requests/responses | Data leakage | Log only necessary fields; mask or filter sensitive data |
| Logging the same stack trace at multiple layers | Inaccurate error counts, noisy search results | Choose the layer with sufficient context to log the error |
| Catching an exception, only logging it, and swallowing the failure | Loss of error semantics and failure state | Handle or propagate the error according to the API contract |
| Logging arbitrary free-form messages without event codes | Hard to aggregate, fragile dashboards | Use stable `event` names and `reasonCode` values |
| Ignoring `Logger`/`Handler` configuration | `FINE` logs do not appear, or logs are duplicated | Configure and test thresholds properly |
| Treating log order as global system order | Incorrect in distributed environments | Use correlation IDs, timestamps, and tracing; understand clock limits |
| No retention, access, or alerting policy | Higher cost and risk, harder incident response | Establish clear operational policies and observability goals |

## 11. Checklist for instrumenting a new behavior

1. Identify the **starting point, decisions, final outcomes**, and notable errors.
2. Choose a small set of events with stable names and express reasons via `reasonCode`; do not turn every step into `INFO`.
3. Define context fields (`requestId`/`jobId`, entity, `outcome`, `durationMs`) and exclude sensitive data.
4. Choose log levels based on actual impact; distinguish valid business rejections from technical errors.
5. Log unexpected errors with a `Throwable` where sufficient context exists, avoiding duplicate error logging across layers.
6. Verify under **success, rejected input, dependency failure, and concurrent requests**: each flow is traceable, output leaks no sensitive data, and logs are neither duplicated nor unexpectedly lost.
7. Test production configuration (`Logger`, `Handler`/`Appender`, collector, read permissions, retention, alerts), because seeing logs on a developer machine does not guarantee the collection pipeline captures them.

**Desired outcome:** From the stored log records, operators can reconstruct the key milestones of a request, explain its outcome, and isolate the failing component. That is the core value of recording system behavior with Java Logging.
