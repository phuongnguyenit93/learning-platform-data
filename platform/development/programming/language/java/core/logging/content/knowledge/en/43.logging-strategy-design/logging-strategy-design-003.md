# Choosing Log Levels in Java Core Logging: Designing a Meaningful Logging Strategy

## 1. Why Does Choosing the Right Log Level Matter?

A **log level** is an attribute used to classify the **operational significance and required attention** of an event, while allowing the logger/backend to filter relevant records before writing them to the console, files, network, or a centralized observability system. Choosing levels well helps development and operations teams find the right information during incident investigation, reduces log noise, controls costs, and avoids turning every normal event into an alert.

For example, a Java service handling a request might emit the following events:

```text
INFO  event=order.accepted order_id=42
DEBUG event=payment.request.prepared dependency=payment
WARN  event=payment.retry attempt=1 reason=TIMEOUT
INFO  event=order.completed outcome=SUCCESS duration_ms=112
```

A single timeout on the first attempt **does not mean** the request ultimately failed. If a retry succeeds, logging `WARN` for the degradation signal and `INFO` for the completion result is often more appropriate than logging `ERROR` as soon as an exception occurs and letting a dashboard report a "failed request." Conversely, once retries are exhausted and the operation fails, the terminal event can be logged at `ERROR`.

**The core question is not "which line of code is this?" but "what does this event say about the actual state, and who needs to act?"**

Choosing a level requires considering:

- **Actual severity:** normal, diagnostic, recoverable anomaly, or final failure.
- **Audience:** developers debugging, on-call engineers, infrastructure operations, security, audit, or business owners.
- **Actionability:** whether the event signals something requiring investigation/intervention or is just a technical step.
- **Frequency and cost:** an event per deployment is different from an event per message in a queue.
- **Retention requirements:** whether the event must be fully audited, or can be filtered/sampled.
- **Sensitivity:** whether data in the message/exception/context is permitted to be written to logs.

A level alone does not tell you which request was affected, what the root cause was, or what the business outcome was. Therefore, level selection must go hand in hand with an appropriate **event name, error code, outcome, correlation ID, and schema**.

## 2. Levels in SLF4J/Logback/Log4j2 and JUL

### A. Common conventions in Java logging backends

| Common Level | Practical Meaning | Examples to Consider |
| --- | --- | --- |
| **TRACE** | Very fine-grained detail, usually for investigating a specific execution path | Internal state transitions, parser branches, controlled loop operations |
| **DEBUG** | Diagnostic information helping developers understand code decisions | Processing branch selection, rule matching, sanitized cache hit/miss reasons |
| **INFO** | Normal operational milestones worth keeping in a running environment | Service ready, job completed, business milestones, HTTP completion per policy |
| **WARN** | Signs of anomaly, degradation, or risk that **may not lead to a final failure** | Retry after timeout, approaching quota limit, fallback activated |
| **ERROR** | A critical operation/request has failed, or the service cannot perform a required function | Transaction failed to commit, request ended in 5xx due to server error |
| **FATAL** (if supported by backend) | Particularly severe error, often preventing the component from continuing to operate | Unrecoverable startup failure; this level is not part of the standard SLF4J API |

These are **recommended design conventions**, not absolute rules: a system might use `WARN` for suspicious 4xx validation failures or `ERROR` for severe security errors depending on its threat model. What matters is that **the same event type has consistent semantics across services**.

### B. `java.util.logging` (JUL) does not have the exact same names

The JDK provides `java.util.logging.Level` with the following standard levels:

```text
SEVERE   (1000)
WARNING   (900)
INFO      (800)
CONFIG    (700)
FINE      (500)
FINER     (400)
FINEST    (300)
```

In addition, there is `Level.OFF` to disable logging and `Level.ALL` to allow all levels at the corresponding filtering step. The numeric values listed above belong to **standard JUL levels**; applications can define custom `Level` instances, so do not treat them as a complete security taxonomy.

Approximate mapping when switching stacks:

| Meaning | SLF4J | Approximate JUL Equivalent |
| --- | --- | --- |
| Deep detail | TRACE | `FINER` / `FINEST` |
| Diagnostics | DEBUG | `FINE` |
| Operational info | INFO | `INFO` |
| Warning | WARN | `WARNING` |
| Error | ERROR | `SEVERE` |
| Configuration info | No dedicated equivalent level | `CONFIG` |

**There is no guaranteed one-to-one default mapping** across every bridge/provider. For example, JUL's `CONFIG` is a dedicated level for configuration and cannot be assumed to equal `DEBUG` by default. When using a JUL-to-SLF4J bridge or another provider, check the mapping applied by the active implementation.

### C. A level is a filtering threshold, not a business priority order

Typically, when the threshold is set to `INFO`, the system retains logs with severity **INFO and more severe**, dropping `DEBUG`/`TRACE` (or lower JUL levels). Setting the threshold to `WARN` drops `INFO`. However, whether a log is actually emitted still depends on the **logger, handler/appender, filter, sampling, and output pipeline**.

Do not treat a level as an "automatic email/pager flag." Alerting should be based on symptoms, error rates, SLOs, and well-designed conditions, rather than paging an on-call engineer the instant a single `ERROR` line appears.

## 3. Rules for Deciding Levels by Event Semantics

A simple decision tree:

```text
Does the event need to be recorded?
 |
 +-- Only used to trace internal steps / debug values?
 |      -> DEBUG or TRACE, bounded and without secrets
 |
 +-- Normal operation, an important milestone / summary?
 |      -> INFO
 |
 +-- Signs of deviation, retry / fallback / degradation,
 |   but the business operation can still complete?
 |      -> WARN, with clear reason code and scope
 |
 +-- Action has finally failed or the system cannot
 |   fulfill a contractual requirement?
 |      -> ERROR / JUL SEVERE
 |
 +-- Mandatory security / audit event requiring durable storage?
        -> Design a dedicated audit channel and choose severity by
           meaning, rather than relying only on INFO/ERROR.
```

This is an **analytical guide**, not a mechanical algorithm. For instance, a sustained wave of retries can severely degrade the system even if it eventually returns 200; conversely, an HTTP 404 caused by a user mistyping a path can be completely normal and not require `WARN` on every request.

When in doubt, answer in order:

1. If this record is disabled in production, would we lose an operational milestone that on-call engineers must know?
2. Is this the **final outcome**, or just a transient failure on a single attempt?
3. Does someone need to act immediately, analyze trends, or only read it when diagnostics are enabled?
4. How many times per second does the event occur; can we afford to keep all of them?
5. Could a metric/trace or summary event achieve the same goal?
6. Does the event carry security, compliance, or legal accountability meaning that must be separated from level-filtered logs?

## 4. Level Selection Table by Event Type

| Scenario | Typically Appropriate Level | Explanation |
| --- | --- | --- |
| Service start, ready, graceful shutdown | INFO | Important milestone, low frequency |
| Loading valid configuration | INFO or `CONFIG` (JUL) | Do not log secrets; log only truly needed details |
| Which service a controller calls | DEBUG/TRACE or trace span | Internal detail, usually very high volume |
| Validation condition succeeds | DEBUG if needed | Usually no need to log every branch |
| Normal HTTP 200 | INFO access completion per policy or metric | One standardized event is better than multiple entry/exit logs |
| HTTP 400 due to invalid input | INFO; occasionally WARN if risk is clear | Do not treat client errors as server exceptions by default |
| HTTP 401/403 | INFO/WARN or dedicated security audit | Depends on threat model; do not log tokens |
| HTTP 404 due to non-existent route | INFO access log or metric | Avoid WARN/ERROR for every meaningless scanner request |
| HTTP 429 rate-limit | INFO/WARN + metric | May be normal policy enforcement or a sign of abuse |
| Downstream timeout followed by successful retry | WARN for the abnormal attempt, INFO for final completion if needed | Do not mark the final request as ERROR |
| Retries exhausted, request ends in 503 | ERROR at final boundary | Has user impact; count final failures separately |
| Fallback works but with degraded quality | WARN/INFO based on impact | Add a degradation/fallback metric |
| Cannot connect to DB during startup | ERROR/SEVERE; FATAL if backend supports it and policy fits | Consequence may be inability to serve traffic |
| Batch job finishes processing | INFO summary | Use counts/duration instead of INFO per item |
| Long-running job and internal checkpoints | DEBUG or bounded periodic INFO | Choose a clear cadence, not every record |
| Business invariant violated and rolled back | ERROR if operation truly did not complete | Include error code and sanitized actor/resource |
| Exception caught and handled normally | DEBUG/WARN depending on impact | A `Throwable` does not dictate the level by itself |
| Reading secrets, rotating credentials, changing permissions | Audit/security route per policy | May have an INFO/WARN mirror, but never replaces audit |
| Periodic worker heartbeat | Metric/healthcheck, sparse INFO if purposeful | Do not spam every second if unhelpful |
| Log shipper loses connection | WARN/ERROR based on impact + self-metrics | Need visibility into logging pipeline blind spots |

A public API with extremely high traffic **may need an access log per request** by policy; this is not necessarily an anti-pattern if volume and retention are designed for it. Conversely, "one `INFO` for every item in a loop" is usually a confusion between debug details and operational events.

## 5. Exception Levels: Look at the Final Outcome, Not Just the `Throwable` Type

### A. Same exception, different severity

Consider a `SocketTimeoutException` when calling a payment service:

```text
Attempt 1 times out, retries still available:
  WARN event=payment.attempt.failed outcome=RETRY attempt=1

Attempt 2 succeeds:
  INFO event=payment.completed outcome=SUCCESS retries=1

Final attempt still times out, payment request fails:
  ERROR event=payment.completed outcome=FAILED
        error_code=DOWNSTREAM_TIMEOUT
```

On the first attempt, `WARN` indicates something worth monitoring, but the user is not necessarily affected yet. `ERROR` is used at the **final outcome boundary** when the operation truly fails. If every layer logs `ERROR` with a stack trace and rethrows, on-call engineers will see multiple "errors" for a single request, distorting impact estimates.

### B. Exception caught and recovered

```java
try {
    return remoteClient.fetch();
} catch (TimeoutException ex) {
    // Illustrative code only; requires remoteClient, fallbackValue, and imports.
    logger.warn("event=remote.fallback code=TIMEOUT", ex);
    return fallbackValue;
}
```

This fragment **cannot run standalone**; with SLF4J it requires a logger and dependencies. If the fallback fully satisfies business requirements, the final outcome may be `SUCCESS`, though you should still emit a fallback metric to see that the dependency is degraded. If the fallback returns stale data that affects quality, `WARN` + a degradation indicator is useful.

### C. Errors converted into HTTP responses

In Spring MVC, an exception handler may convert `IllegalArgumentException` into HTTP 400. The presence of a `Throwable` does not mean the server returned 500. You should distinguish:

- `http.status_code`: final status recorded by the framework;
- `business.outcome`: business-level success/failure;
- `exception.type`: technical error type;
- `error.code`: stable reason code for searching logs and measuring metrics.

Do not use `exception.getMessage()` as a metric label because it has high cardinality and may expose sensitive data.

### D. Errors occurring in an async worker

If HTTP returns `202 Accepted` and a background job fails later, the `ERROR` event belongs to the **job**, not the already-completed HTTP request. Do not retroactively alter the HTTP outcome or conflate the two units of measurement. Log the job ID/correlation and emit a job failure metric at the worker boundary.

### E. Do not log stack traces at every layer

A good pattern is to **log where sufficient context exists, after the handling decision is clear**. The DAO layer can wrap an exception with its cause and propagate; the service layer can retry/fallback; the controller or job worker logs the final failure. If events are needed at multiple layers, use distinct event names and separate `attempt` from `operation`.

## 6. What Is `INFO` When Implementing a Logging Strategy?

`INFO` is appropriate for events that are:

- Infrequent or have predictable frequency, such as service boot, deployment, or job summaries.
- Useful for investigation without enabling `DEBUG`, such as request completion with route, status, duration, and correlation.
- Describing **meaningful outcomes** rather than technical steps.
- Easy to query by event name, outcome, and error code; minimally dependent on message wording.
- Free of unnecessary secrets/PII, without logging entire raw payloads.

Compare:

```text
Multiple fragmented INFO logs:
INFO Enter OrderController.create()
INFO Validating...
INFO Calling repository...
INFO Repository returned...
INFO Exiting OrderController.create()

One structured event:
INFO event=order.created order_id=42 outcome=SUCCESS request_id=req-7 duration_ms=34
```

For high-frequency operations, use metrics for counts, duration histograms for latency, and traces to describe flow. **Do not force `INFO` to replace `DEBUG`/traces**, but do not disable important events just to cut costs either.

When choosing `INFO` for request access logs, you must define who emits the completion event, when the request is truly complete (including async, exceptions, 404/401), and how to avoid duplicates if both gateway and application log the event. Do not assume HTTP 200 means business success if the API uses error codes in the response body.

## 7. `WARN`: Anomaly or Degradation, Not Necessarily Failure

`WARN` / JUL `WARNING` generally says: "something unexpected is happening that may have an impact or is worth watching, but the action can still complete."

Reasonable examples:

- Retry due to network timeout, with attempt number and dependency.
- Circuit breaker transitioning to `OPEN` or connection pool nearing exhaustion.
- Fallback activated, data is no longer fresh.
- Record parse errors on a small subset of data that can be skipped by policy, accompanied by a count/ratio.
- Cache hit ratio dropping or queue backlog rising **when crossing a meaningful threshold**.

Be cautious about logging `WARN` on every request for normal, expected situations: a client entering an invalid email, HTTP 404 from web-scanning bots, normal cache misses, or scheduled retries in an eventually consistent system. These events may warrant metrics/`INFO`/debug or a separate security signal rather than `WARN` spam.

A `WARN` should carry context for triage: `event.name`, `reason_code`, `dependency`, `attempt`/`retryable`, and `request_id` when appropriate. If thousands of consecutive `WARN`s could be emitted, consider aggregation, suppression, and metric counts rather than simply downgrading them to `INFO` to avoid alerts.

## 8. `ERROR`: Meaningful Failure with an Owner

`ERROR` / JUL `SEVERE` is typically appropriate for:

- A critical request or operation **failing to complete** per contract.
- Service startup failure, readiness failure, or a core component unable to function.
- Business data rolled back due to an unexpected error condition.
- A mandatory task failing finally after retries and requiring investigation/intervention.

However, **`ERROR` does not mean a paged incident** and **does not mean every `Throwable`**. A valid HTTP 400 request may not need `ERROR`; a batch queue encountering a poison record can be isolated and handled per policy (`WARN` if SLA is unaffected); an authorization denial may require a security event even though it is not a server error.

If `ERROR` is needed at both the dependency source and the final boundary, make the distinction clear:

- The dependency event is `dependency.attempt.failed` or `dependency.call.failed`, counted per attempt/call.
- The request event is `http.request.completed` with the final outcome, counted per request.
- Avoid using the same event name and the same metric semantics across multiple layers.
- Log the stack trace once where the investigative context resides; you can preserve the cause chain without duplicating the entire message everywhere.

For rapid recurring failures, an `ERROR` flood can overload the logging pipeline itself. You need error-rate metrics, suppressed counts, and policy-based rate limiting/sampling; **never drop mandatory audit records**.

## 9. `TRACE` and `DEBUG`: Purposeful Diagnostics

`DEBUG` and `TRACE` help explain how code makes decisions, but are usually disabled or enabled only narrowly in production. Examples:

- `DEBUG`: processing rule selection, coded validation results, selected cache strategy.
- `TRACE`: parser state transitions, protocol frame details (with secrets stripped), ultra-fine algorithm steps.
- Metrics are better suited for: cache hit/miss counts, latency, retries, queue depth.
- Traces/spans are better suited for: a request traversing multiple dependencies and the timing of each step.

**`DEBUG` is not a "data-exposure-free" zone**: during an incident, it may be enabled and collected through the exact same pipeline. Do not dump request bodies, auth headers, tokens, or entire entities just because the level is low.

If `DEBUG` must be enabled in production, target the specific package/service/instance having issues, require approval, set a time limit, and monitor log volume. Avoid setting `root=DEBUG` permanently when the service includes many chatty libraries.

## 10. Filtering Mechanics: Logger Level, Handler/Appender Level, and Filters

### A. With JUL, there are at least two filtering layers

Example logger configuration:

```java
Logger log = Logger.getLogger("com.example.payment");
log.setLevel(Level.INFO);
```

Here, a `FINE` record is typically dropped right at the logger. However, **to actually be emitted**, a record must also pass through a `Handler` with a matching level/filter. If the logger allows `INFO` but the handler is set to `WARNING`, `INFO` can still be dropped at the handler.

Several important details:

- `Logger.getLevel()` can return `null`, meaning it **inherits the level** from its parent; the effective level is not simply `getLevel()` on the current logger.
- `Handler.setLevel(Level.ALL)` only allows the handler to accept more levels; it **does not force a logger to create a record already blocked by the logger level**.
- A logger can forward records to parent handlers when `useParentHandlers=true`, causing duplicate output paths or different filtering per handler.
- A `Filter` on a logger or handler can apply additional rules beyond level.
- `Level.OFF` disables at that level; `Level.ALL` opens it up, but cannot bypass a filter, handler, or inactive output path.
- Behavior depends on the `LogManager` configuration, active handlers, formatters, and runtime.

Use levels to filter intentional events; for mandatory audits, do not pick a generic `INFO` logger and assume every environment will always preserve it.

### B. SLF4J and backends

SLF4J is a **facade API**; it does not decide persistence, JSON formatting, async behavior, or retention. In common setups, Logback or Log4j2 acts as the provider/backend, where logger levels, appenders, thresholds, additivity, and layouts are configured.

Illustrative SLF4J snippet:

```java
logger.trace("event=parser.transition state={}", state);
logger.debug("event=policy.evaluated rule={}", rule);
logger.info("event=payment.completed status={}", status);
logger.warn("event=payment.retry attempt={}", attempt);
logger.error("event=payment.failed error_code={}", code, exception);
```

This snippet **is not a standalone Java file**; it requires a logger, variables, and dependencies. Calling `logger.error` does not throw an exception; passing a `Throwable` lets the backend print the stack/cause if the layout allows it. Check method overloads so the exception is not accidentally treated as a text argument.

### C. Logback XML: per-package level configuration

```xml
<configuration>
  <appender name="STDOUT"
            class="ch.qos.logback.core.ConsoleAppender">
    <encoder>
      <pattern>%d{ISO8601} %-5level %logger - %msg%n</pattern>
    </encoder>
  </appender>

  <logger name="com.example.payment" level="DEBUG"/>

  <root level="INFO">
    <appender-ref ref="STDOUT"/>
  </root>
</configuration>
```

This is an **illustrative Logback configuration**, not plain Java; it requires the right dependencies, config path, and compatible backend version. The `com.example.payment` logger has a `DEBUG` threshold, while other loggers inherit root `INFO` per Logback rules. Appenders/Filters can still drop records; additivity can cause records to be emitted through multiple appenders if configured overlappingly.

Do not confuse Logback with Log4j2: each backend has different XML/YAML schemas, class names, and defaults. For Log4j2, thresholds, logger configuration, additivity, and appender refs must be configured according to the documentation of the running version.

### D. Spring Boot properties

If Spring Boot uses a compatible backend:

```properties
logging.level.root=INFO
logging.level.com.example.payment=DEBUG
logging.level.org.springframework.web=WARN
```

This is an **`application.properties` fragment**, not a full Boot application. It expresses intent: `INFO` for the application overall, temporary `DEBUG` for a specific package, and `WARN` for certain framework logs. Avoid suppressing useful `WARN`/`ERROR` logs from dependencies just to reduce noise; tune based on observed behavior.

If an organization allows changing levels at runtime via actuator/admin endpoints, it must enforce authentication/authorization, restrict exposure, log configuration change audits, and provide a way to revert to a safe configuration. Do not assume every Boot version supports the same endpoint or allows level changes without configuration.

## 11. Standalone Java 17 Example: Level Selection and Two-Layer JUL Filtering

The following example **uses only JDK 17**. It demonstrates:

1. `INFO`, `WARNING`, and `SEVERE` are emitted when the logger is set to `INFO`.
2. Diagnostic `FINE` messages are suppressed, and how arguments are passed determines computation cost when the level is disabled.
3. Enabling `FINE` on the logger allows the supplier-based diagnostic message to appear.
4. A handler can **filter out `INFO`** even when the logger allows it.
5. The program prints deterministic stdout for step-by-step verification.

Save as **`LogLevelSelectionDemo.java`**:

```java
import java.util.concurrent.atomic.AtomicInteger;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class LogLevelSelectionDemo {
    private static final Logger LOG =
            Logger.getLogger("example.level.selection");

    private static String makeDetails(AtomicInteger calls) {
        int n = calls.incrementAndGet();
        return "detail-" + n;
    }

    public static void main(String[] args) {
        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.INFO);

        Handler sink = new Handler() {
            @Override
            public void publish(LogRecord record) {
                if (isLoggable(record)) {
                    System.out.println(record.getLevel().getName()
                            + " " + record.getMessage());
                }
            }

            @Override
            public void flush() {}

            @Override
            public void close() {}
        };
        sink.setLevel(Level.ALL);
        LOG.addHandler(sink);

        AtomicInteger eager = new AtomicInteger();
        AtomicInteger lazy = new AtomicInteger();

        try {
            // FINE is disabled. String concatenation still calls makeDetails.
            LOG.fine("event=diagnostic " + makeDetails(eager));

            // FINE is disabled. The Supplier does not need to build the message.
            LOG.log(Level.FINE, () ->
                    "event=diagnostic " + makeDetails(lazy));

            LOG.info("event=service.started outcome=SUCCESS");
            LOG.warning("event=payment.retry attempt=1 reason=TIMEOUT");
            LOG.severe("event=payment.failed outcome=FAILED");

            // Enable the DEBUG equivalent for the logger under consideration.
            LOG.setLevel(Level.FINE);
            LOG.log(Level.FINE, () ->
                    "event=diagnostic " + makeDetails(lazy));

            // The Logger allows INFO, but the Handler blocks INFO.
            sink.setLevel(Level.WARNING);
            LOG.info("event=hidden.by.handler");
            LOG.warning("event=handler.warning.only");

            System.out.printf(
                    "COUNTS eager_calls=%d lazy_calls=%d%n",
                    eager.get(), lazy.get());
        } finally {
            LOG.removeHandler(sink);
            sink.close();
        }
    }
}
```

Compile and run:

```bash
javac LogLevelSelectionDemo.java
java LogLevelSelectionDemo
```

**Exact stdout:**

```text
INFO event=service.started outcome=SUCCESS
WARNING event=payment.retry attempt=1 reason=TIMEOUT
SEVERE event=payment.failed outcome=FAILED
FINE event=diagnostic detail-1
WARNING event=handler.warning.only
COUNTS eager_calls=1 lazy_calls=1
```

Explanation:

- When the logger is at `INFO`, the first two `FINE` logs are not published. However, in the string-concatenation call, Java still evaluates `makeDetails(eager)` **before** the logger checks the level: `eager_calls=1`.
- JUL `log(Level, Supplier<String>)` defers message construction when the logger level is disabled, so `lazy` remains 0 on the first call.
- `INFO` is a normal milestone, `WARNING` is for retry, and `SEVERE` is for final failure. The example assumes retry and failure are meaningful within the illustrative operation; a real application must ensure it does not log `ERROR` if a retry succeeded.
- After `LOG.setLevel(Level.FINE)`, the supplier is invoked once to produce `detail-1`, and the record is accepted by the `ALL` handler.
- After `sink.setLevel(Level.WARNING)`, the logger still allows `INFO` but the handler blocks it. Thus `event=hidden.by.handler` is **not** emitted; `WARNING` still is.
- `setUseParentHandlers(false)` prevents parent handlers from printing a duplicate copy (usually to stderr), and the custom `Handler` adds no timestamp/formatter so output is deterministic.
- `AtomicInteger` only demonstrates argument evaluation counts; it is not a benchmark for CPU, heap, or log bytes.

**Limitations:** the example has one logger, one handler, and runs sequentially; it has no Logback, SLF4J, MDC, structured JSON, HTTP server, async logging, log shipping, or audit guarantees. Changing levels dynamically in a multi-threaded process can affect all in-flight requests; in production, use proper governance processes instead of toggling levels arbitrarily.

## 12. Argument Evaluation and Cost When Choosing Levels

A lower level reduces log volume when filtered, but **does not always avoid argument computation costs**.

### A. String concatenation before the logger call

```java
logger.fine("userState=" + expensiveSnapshot());
```

Even when `FINE` is disabled, Java evaluates `expensiveSnapshot()` before calling the method. If the snapshot serializes a large object, exposes secrets, or performs I/O, moving the message to `DEBUG` does not solve the cost.

### B. JUL's `Supplier`

```java
logger.log(Level.FINE, () -> "userState=" + expensiveSnapshot());
```

When `FINE` is filtered out by the logger, the supplier is not evaluated to build the message. Once enabled, however, building the snapshot still consumes resources. Even **instantiating the supplier/lambda** can have varying overhead depending on captures and JIT; do not claim zero cost.

### C. SLF4J parameterized logging

```java
logger.debug("result={}", expensiveResult());
```

Parameterized logging avoids string pattern concatenation at the call site, but **`expensiveResult()` still runs** before `debug` is called. For expensive expressions, a guard may be necessary:

```java
if (logger.isDebugEnabled()) {
    logger.debug("result={}", expensiveResult());
}
```

These SLF4J snippets require dependencies and a logger; they are not standalone programs. In SLF4J 2.x, the fluent API also provides supplier-based methods (depending on the overload) to defer argument evaluation:

```java
logger.atDebug()
      .addArgument(() -> expensiveResult())
      .log("result={}");
```

Verify your SLF4J version and provider, and do not confuse it with other APIs. Do not use a supplier as an excuse to dump sensitive data: once `DEBUG` is enabled, that data can still be emitted and stored.

### D. How to optimize?

- Avoid building large strings and calling `toString()` on sensitive entities unnecessarily.
- Do not serialize entire request/response objects at default `INFO`.
- Choose small, schema-driven events with controlled error codes and IDs.
- Measure allocations/op, CPU, p95/p99 latency, and throughput with logging enabled/disabled using representative benchmarks (e.g., JMH).
- Check encoder, disk/network I/O, async queue, and Collector costs, not just message-creation time.

A "disabled" logger does not mean all arguments are cheap; an async appender does not mean it will never block or drop under overload.

## 13. Pairing Levels with Structured Events, Not Just Plain Text

A structured completion event:

```json
{
  "timestamp": "2026-01-01T00:00:01Z",
  "severity": "INFO",
  "event.name": "http.request.completed",
  "service.name": "orders-api",
  "deployment.environment.name": "prod",
  "http.method": "POST",
  "http.route": "/api/orders",
  "http.status_code": 201,
  "duration_ms": 34.5,
  "outcome": "SUCCESS",
  "request_id": "req-101",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736"
}
```

This is an **illustrative application-designed schema**, not output automatically generated by every Java logger or OpenTelemetry SDK. Actual structures may have different log record attributes, resource attributes, and schemas depending on the backend/version.

For consistent level selection and querying, include:

- **`event.name`**: stable, meaningful event identifier.
- **`severity`**: interpretive priority level; kept separate from HTTP status.
- **`outcome`**: `SUCCESS`, `FAILED`, `RETRY`, `DENIED`, `DEGRADED`, etc., per contract.
- **`error.code`/`exception.type`**: filterable reason/error type, independent of exact message text.
- **`service.name`**, environment, version: identifies where and which version emitted it.
- **`request_id`/`trace_id`**: links logs and traces of the same request/operation.
- **`duration_ms`/`attempt`**: measurements with clear units and scope.
- **Sensitive fields excluded**: do not log tokens/passwords, excessive PII, or raw URLs/queries containing secrets.

For metrics, tags/labels must have bounded cardinality: service, route template, outcome, error code. Never put request ID, trace ID, order ID, or exception message into metric labels.

### Correlation cannot fix poor level selection

Having a `trace_id` helps open the right request, but it does not make an `INFO` line inside every loop iteration useful. Conversely, a `WARN`/`ERROR` without a reason code, operation, and scope is hard to investigate. You must **choose the right event and severity first**, then add correlation.

## 14. Environment-Based Level Selection Strategy

| Environment / Goal | Commonly Considered | What Not to Assume |
| --- | --- | --- |
| Local development | DEBUG/TRACE for code under development | DEBUG across all libraries is always safe/fast |
| Automated tests | INFO/WARN default; DEBUG on test failure | Log level determines test pass/fail |
| Staging | INFO + temporary DEBUG in select components | Low traffic reflects production cost |
| Normal production | INFO milestones, meaningful WARN/ERROR, DEBUG/TRACE filtered | Every INFO is worth keeping or every WARN must page |
| Production incident | Scoped/TTL/owned DEBUG enabled | Permanently setting root DEBUG is the only way |
| Mandatory audit/security | Dedicated channel/sink per durability contract | INFO logger is always complete or never sampled |

A typical policy:

```text
Root logging: INFO
Noisy dependency/framework packages: WARN when justified
Application:
  - INFO: readiness, business/HTTP completion per policy
  - WARN: recoverable degradation, retry/suppression summary
  - ERROR: final failure at operation boundary
  - DEBUG/TRACE: disabled by default, enabled narrowly when needed

Audit:
  - independent of root INFO sampling/filters
  - durability, retention, and access control per dedicated requirements
```

There is no single optimal configuration for every application. A service handling millions of requests/second and a batch job running once a day have different volume profiles. Base your policy on SLOs, investigative value, traffic, backend quotas, legal requirements, and budget.

### Safe dynamic level changes

You should have:

1. Approval permissions or access controls for changing levels.
2. Precise scope (package, class, instance, pod, or trace scope if supported by the stack).
3. TTL/rollback so `DEBUG` does not stay on indefinitely.
4. Limits on log volume, queues, disk, and ingest rate.
5. Redaction and field allowlists **enforced at every level**.
6. Configuration change tracking to audit who enabled verbose logging.
7. Before/after metrics observation: bytes/s, events/s, dropped count, latency impact.

Increasing verbosity in production can affect performance and privacy; do not experiment cluster-wide without a risk assessment.

## 15. Log Levels Do Not Replace Log Sampling and Retention Policies

Severity and sampling solve two different problems:

- **Level filtering:** drops events below a threshold at the logger/handler/backend.
- **Sampling:** retains a percentage of events per policy, e.g., by request, event type, or trace.
- **Rate limiting/suppression:** caps similar logs within a time window, recording a suppressed count.
- **Aggregation:** replaces many detailed events with summaries/counters.
- **Retention:** determines how long ingested records are kept.
- **Audit durability:** determines how critical records are durably stored, not just kept at a certain level.

For example, 50,000 retry warnings/minute from a failing dependency can cause overload. If your organization permits, you can keep a sample of events, aggregate them into a summary, and use a `retry_attempts_total` counter to still measure scale accurately. However, **do not arbitrarily sample mandatory audit events** or use sampled logs to infer exact rates without a proper statistical method.

When reducing verbosity, ensure critical signals remain: HTTP failures, queue drops, dependency health, outages, audits, log pipeline errors, and request metrics. Seeing "fewer ERROR logs" is not enough to conclude a service is healthy; the logger may be disabled or the agent may be failing to ship.

## 16. Choosing Levels in Web Systems and Microservices

A request flows through gateway → auth filter → controller → service → repository → downstream client. Each layer can log, but every layer should not emit an indistinguishable `INFO request started` and `INFO request completed`.

A clean design might include:

1. **Gateway:** edge access event with method/route/status/duration/trace context.
2. **Application HTTP boundary:** completion event per policy, final outcome, and correlation.
3. **Business service:** key state-transition events, such as `payment.authorized` or `order.cancelled`.
4. **Dependency call wrapper:** `WARN` for abnormal retries/fallbacks; metrics for dependency attempts/errors.
5. **Exception handler:** `ERROR` for final failed requests/operations when appropriate; avoid logging the same exception at every layer.
6. **Audit/security path:** authentication/authorization-change events with verified actor, not reliant on generic levels.

**A single request can legitimately produce multiple logs.** The goal is to avoid useless duplicates and clearly distinguish event names and units of measurement. Use route templates instead of raw URIs containing dynamic IDs; keep request ID/trace ID in logs/traces, not in metric labels.

In Servlet/Spring MVC, 404 errors or auth rejections may occur before reaching a controller; logging only inside controllers will miss them. In async/WebFlux requests, completion may occur after the handler returns control; choose the appropriate hook to avoid logging the wrong outcome/latency or emitting duplicates across dispatches.

## 17. Production Cost and Impact of Log Levels

An application serving 2,000 requests/second, with each request emitting 5 `INFO` events at ~400 bytes each:

```text
events/s = 2,000 × 5 = 10,000
bytes/s  = 10,000 × 400 = 4,000,000
bytes/day = 4,000,000 × 86,400
          = 345,600,000,000 bytes
          ≈ 345.6 GB/day (decimal units)
```

If reduced to one completion event per request at the same assumed size:

```text
events/s = 2,000
bytes/day = 2,000 × 400 × 86,400
          = 69,120,000,000 bytes
          ≈ 69.12 GB/day
```

This is a **raw byte estimate**, excluding metadata, indexing, replication, compression, network retries, and retention. Do not treat this example as a cost-savings guarantee. Actual costs must be measured from your sink and backend.

More importantly, a log flood can fill queues or disks right when an incident occurs, causing **`WARN`/`ERROR` logs to be delayed or dropped**. Thus, `INFO` volume is not just a cost issue—it is also about preserving capacity for critical signals.

To evaluate impact, monitor:

- `log_events_total` by event name/severity/service.
- `log_bytes_total` or encode/ingest throughput.
- `logs_dropped_total`, queue depth, exporter errors, oldest event age.
- CPU, allocations, GC pauses, throughput, and p95/p99 latency when changing levels.
- Ingest/index/storage costs and retention periods.
- Percentage of `ERROR`/`WARN` logs searchable by error code and linked to a request/trace.
- Incident usefulness: how many queries/triages actually need that line?

These metric names are suggestions and are not built into every logging stack.

## 18. Security and Audit When Choosing Levels

**Do not treat `DEBUG`/`TRACE` as safe for logging secrets.** A log line containing a password or token is a risk at any level. It can be enabled during an incident and persisted in local files, queues, Collectors, cloud backends, or backups.

Do not include the following data in logs without a specific purpose and handling policy:

- Plaintext passwords, API keys, access tokens, refresh tokens, session cookies, private keys.
- Request bodies containing personal/payment information or sensitive data.
- Raw URLs/query strings with signed tokens/emails; raw paths with secrets in segments.
- Exception messages/stacks that might contain SQL, payloads, or credentials.
- Overly detailed user/tenant information when the event only needs an error code/route.

Use a structured encoder with escaping to prevent log injection; validate client-supplied fields so they cannot spoof level, actor, or outcome. Apply least-privilege permissions for read/search/export access and appropriate retention per log class.

**Audit** serves a different purpose than operational logging: it tracks accountability—who did what to which object and with what result. It may need to record both successful and denied operations with special durability/retention. Calling `logger.info("role changed")` does not guarantee the event survives if root `INFO` is disabled, an async queue drops it, or the service crashes. When mandatory, use an audit writer/outbox or storage with appropriate durability/atomicity guarantees.

## 19. Testing Level Selection in Unit/Integration Tests

| Scenario | Expectation |
| --- | --- |
| `INFO` logger receives `INFO`/`WARNING`/`SEVERE` | Configured output events are emitted |
| `FINE`/`DEBUG` under `INFO` threshold | Diagnostic records are not emitted |
| Lazy `Supplier` when `FINE` is disabled | Expensive payload is not built |
| Eager concatenation when `FINE` is disabled | Pre-call expression still executes |
| Handler set to `WARNING` while logger allows `INFO` | `INFO` is filtered out by the handler |
| Retry succeeds | `WARN`/retry metric emitted, no false final request `ERROR` |
| Retries exhausted and final failure | `ERROR` emitted once at boundary, with error code/context |
| Normal HTTP 400 validation | Server `ERROR` is not logged by default |
| HTTP 500 due to exception | `ERROR` includes request ID/trace ID and exception context when needed |
| 404 or 401/403 before controller | Log/security event emitted per policy |
| Background job fails after HTTP 202 | Job failure logged separately without altering HTTP outcome |
| Backend async queue full | Drop/block/backpressure has metrics and alerts |
| Logger parent/additivity | No unintended duplicate records |
| Dynamic level enables only target package | Root `DEBUG` is not unexpectedly enabled |
| Log contains newline/secret | Proper encoding/validation, no token leaked at any level |
| Audit event through filters/sampling | Durable mechanism exists and is verified per separate contract |
| Multi-instance and thread pool | Correlation does not leak across requests, logger settings behave consistently |

You can verify with an in-memory/test appender or custom JUL `Handler` to assert levels and event counts; integration tests should confirm the encoder, Collector, and backend receive the expected fields. For async loggers, use a wait/flush condition with an appropriate timeout rather than just `Thread.sleep(1000)` and assuming ingestion finished.

### Evaluating a new event in code review

When reviewing a new `logger.info/warn/error` call, ask:

1. Is this event a **final outcome** or an intermediate step?
2. Does the level match the impact and system conventions?
3. If logged per request/item, what is the expected volume?
4. Does the message have a stable code and correlation for lookup?
5. Is it duplicated in another layer, or do metrics/traces already cover it?
6. When the level is disabled, does the code still build expensive payloads or secrets?
7. Is it a security/audit event that must be written independently of the root logger?
8. When level configuration changes, is there a risk of losing necessary events?

## 20. Common Mistakes When Choosing Log Levels

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Logging everything at `INFO` | Noise, storage cost, buried signals | Reserve `INFO` for meaningful milestones/completions/summaries |
| Using `ERROR` for every caught exception | Retries/fallbacks become false errors | Choose level by final outcome |
| Using `WARN` for every 404 or cache miss | Alert fatigue, skewed metrics | Use access logs/metrics; `WARN` only when truly abnormal |
| Printing full stack traces at every layer | Duplicate logs and high cost | Log stack trace once at the boundary with context |
| `DEBUG` with string concatenation calling `expensiveCall()` | Wastes CPU even when level is off | Use `Supplier`/guard per API |
| Assuming handler `ALL` prints `FINE` | Logger may still filter `FINE` | Check both logger and handler |
| Reading only `getLevel()` as effective level | May be `null`/inherited | Check parent config and handler chain |
| Enabling root `DEBUG` across production | Volume/PII explosion | Narrow scope, TTL, permissions, and rollback |
| Using severity as the sole SLO | Log volume is not request error rate | Measure metrics at measurement boundaries |
| Using request/trace IDs as metric labels | High-cardinality time series | Keep IDs in logs/traces; keep labels bounded |
| Treating `WARN`/`ERROR` as direct pager triggers | Non-actionable alerts | Alert on rates, impact, SLOs, and dedup |
| Using `INFO` as audit storage | Lost logs on filter/drop/crash | Use a dedicated durable audit path |
| Logging secrets at `DEBUG` because "it's normally off" | Exposed when enabled or in other sinks | Enforce redaction/data minimization at all levels |
| Forgetting appender additivity/filters | Missing or duplicate events | Test the actual pipeline |
| Dropping necessary `INFO` access completions | Loss of request investigation capability | Keep purposeful events, accounting for throughput |
| Not testing when the collector loses network | Logs go silent while service keeps running | Use self-metrics and end-to-end canaries |

## 21. Checklist for Applying to a Java Logging Strategy

- [ ] Has the team clearly defined `TRACE`/`DEBUG`/`INFO`/`WARN`/`ERROR` and business exceptions?
- [ ] Is `INFO` reserved for valuable milestones/summaries/completions rather than individual code steps?
- [ ] Does `WARN` represent anomalies/retries/degradation while `ERROR` represents actual final failures?
- [ ] Are attempt-level, operation-level, HTTP request, and async job failures clearly distinguished?
- [ ] Does each event type have an owner, event name, error code, and sufficient data for triage?
- [ ] Do we avoid log-and-rethrow across multiple layers causing duplicate stack traces?
- [ ] Are levels chosen based on actual request outcome/status rather than `Throwable` alone?
- [ ] Do we know the JUL `FINE/INFO/WARNING/SEVERE` mapping for our active logging stack and bridge?
- [ ] Have we verified logger, handler/appender, filter, additivity, and inheritance so levels actually take effect?
- [ ] Do expensive arguments when a level is disabled use a `Supplier`/guard rather than `String` concatenation?
- [ ] Are `DEBUG`/`TRACE` restricted by default with a mechanism for temporary per-package enabling with TTL/rollback?
- [ ] Have we estimated bytes/s, log volume, queue/backpressure, retention, and ingest costs?
- [ ] Are passwords/tokens/excessive PII excluded at every level?
- [ ] Do we have structured logging with service/environment, outcome, route, and request/trace IDs for searchability?
- [ ] Do metric labels avoid dynamic IDs, and are request/error SLIs measured separately from log line counts?
- [ ] Do mandatory security/audit records have a retention path independent of general sampling/levels?
- [ ] Have we tested `INFO`/`DEBUG`/`WARN`/`ERROR`, exception retries, async, handler filtering, and logging pipeline failures?
- [ ] Do we have canaries/self-metrics to detect dropped or unsearchable logs?

**Conclusion:** choosing a log level is not merely picking `info()`, `warn()`, or `error()`. It is part of an **observability strategy**: determining **what an event means, who needs to pay attention, and when**, then selecting the appropriate severity, schema, frequency, sampling, and retention. In Java, remember that both the logger and handler/appender can filter; exceptions must be classified by **final outcome**; `DEBUG`/`TRACE` must never contain secrets; `INFO` should only keep observable milestones; and `WARN`/`ERROR` must aid investigation rather than create noise. When conventions are consistent, logs become searchable, trustworthy, and effective alongside metrics and traces.
