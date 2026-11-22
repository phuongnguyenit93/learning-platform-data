# Anti-pattern: Logging Everything at INFO in Java Core Logging

## 1. What is the “Log Everything at INFO” Anti-pattern?

**Logging everything at INFO** is a logging design where almost every internal event in a Java program is recorded at the `INFO` level, regardless of whether it is a normal operational state, a debugging detail, a repeated operation inside a loop, a warning requiring attention, or an actual error. For example, a single HTTP request might produce dozens of `INFO` lines for minor steps such as “entering method”, “reading variable”, “calling repository”, “received result”, and “exiting method”.

`INFO` **is not the wrong level**. It plays a very important role in describing meaningful and relatively stable operational milestones. The anti-pattern occurs when a program uses `INFO` as the **default level for everything it wants to report**, drowning important logs in noise, increasing costs, and making querying and investigation harder.

Contrasting example:

```text
Avoid:
INFO Enter OrderController.create()
INFO Request received
INFO Calling OrderService
INFO Validating order
INFO Validation completed
INFO Calling OrderRepository
INFO Repository returned
INFO Response created
INFO Exiting OrderController.create()

Recommended, depending on operational requirements:
INFO event=order.accepted order_id=42 status=ACCEPTED request_id=req-101
DEBUG event=order.validation.completed rule_set=v3 request_id=req-101
WARN event=payment.retry dependency=payment attempt=1 reason=TIMEOUT
ERROR event=order.processing.failed error_code=PAYMENT_UNAVAILABLE request_id=req-102
```

The lines above are text examples, not fixed output from a specific framework. In practice, you should use **structured logging** so that `event.name`, `error.code`, `request_id`, `service.name`, and `outcome` are structured fields rather than just key/value strings stuffed into `message`.

Lesson objectives: understand the semantics of log levels, the technical/cost/security consequences of overusing INFO, how to choose meaningful events, how to configure and optimize logging in Java, how to design testable observability, and how to implement a deterministic Java 17 example demonstrating level filtering and lazy parameter evaluation.

## 2. Why Do Developers Easily Fall Into This Anti-pattern?

Some common causes:

1. **Wanting to “make sure logs are visible” in production:** DEBUG or TRACE is usually disabled, so developers switch everything to INFO instead of establishing a controlled debugging path.
2. **Using logs instead of a debugger or tracing:** logging “enter/exit”, variable values, and every function result to follow the execution flow.
3. **Lack of an event taxonomy:** no convention to distinguish business milestones, warnings, final failures, diagnostic details, and audit events.
4. **Fear of missing information during an incident:** logging as much as possible instead of designing correlation fields, error codes, traces, and the right moments to capture state.
5. **Copy/paste code:** logging at the controller, service, and DAO all at INFO for the same request; one operation produces multiple lines with duplicate content.
6. **Overly coarse level configuration:** only knowing the root INFO level, without knowing how to temporarily enable DEBUG per package/class or by correlation in a safe environment.
7. **Confusing INFO with “safe/low impact”:** the level itself does not limit event rate, payload size, sensitive data, or ingestion cost.

The fix is not mechanically changing every `INFO` to `DEBUG`. You need to answer **who will use this log line, to make what decision, and how long it needs to be kept**. An important business event may still deserve INFO or a dedicated audit route; many DEBUG lines can be removed altogether if appropriate metrics or traces already exist.

## 3. Log Levels in Java: Choosing by Semantics

| Purpose | Common SLF4J / Logback / Log4j2 | Approximate JUL (`java.util.logging`) equivalent | Example |
| --- | --- | --- | --- |
| Very deep detail, many internal steps | TRACE | `FINER` or `FINEST` depending on detail level | Parsing individual tokens, state per loop iteration |
| Detail for developer investigation | DEBUG | `FINE` | Branch selection result, sanitized parameters |
| Observable normal operational milestone | INFO | `INFO` | Service started, deployment applied, operation accepted |
| Recoverable anomaly or degradation | WARN | `WARNING` | Retry due to timeout, circuit breaker state transition |
| Real failure requiring attention | ERROR | `SEVERE` | Request/operation did not complete, dependency unavailable |
| Mandatory business audit/security | Do not rely on a single level alone | Channel/sink with a dedicated contract | Role granted/revoked, admin policy changed |

This table provides an **approximate equivalence**, not a strict one-to-one API mapping. JUL has `CONFIG`, `FINE`, `FINER`, `FINEST`, `INFO`, `WARNING`, `SEVERE`; SLF4J typically has `TRACE`, `DEBUG`, `INFO`, `WARN`, `ERROR`. Log4j2 also has `FATAL`/its own capabilities, whereas the standard SLF4J API does not have a `fatal()` method.

### When Is INFO Appropriate?

INFO is generally appropriate for **operationally meaningful milestones** with an anticipated frequency:

- Application start/stop, loading important non-secret configuration, health transitions.
- A significant business state change or background job completion, when policy requires observation.
- One **request completion** event per request if the organization intentionally maintains access logging with appropriate volume, retention, and query permissions.
- The outcome of a meaningful batch/job, total items processed, or checkpoints, rather than every small item.
- Changes to operational mode, deployment version, or critical feature gates, with a clear owner and emission conditions.

**There is no rule saying “INFO must never be logged per request.”** Access logs may intentionally record one completion event per request for incident and traffic analytics. The problem is duplicating INFO messages that **add no value** at every step and have no capacity budget.

### WARN and ERROR Should Distinguish Final Outcome

- **WARN:** transient error that recovered, retry, fallback, or unusual request where the system still responded.
- **ERROR:** an operation has **finally failed**, the service could not fulfill an important request, or a situation requires attention at an appropriate severity.
- An `IOException` on the first attempt does not automatically mean the entire HTTP request failed; a retry may succeed.
- A 400 validation error or 403 permission denial is not necessarily a server ERROR. Depending on the threat model, it may require dedicated security events, metrics, and audits.
- A `NullPointerException` that is caught and safely handled may still warrant a code quality investigation, but log severity should reflect the consequence and policy, not merely the exception type.

Organizations should define severity conventions, error codes, and event owners for each type of operation. The essence of severity is **prioritizing interpretation**, not a rigid rule of “whenever something throws, log ERROR”.

## 4. First Consequence: INFO Noise Hides Real Errors

When 99% of log lines are repetitive INFO messages, engineers responding to an incident must sift through huge volumes of low-value messages to find the few ERROR/WARN entries that matter. Consequences:

- Searches return too many results, forcing complex regexes and exclusion filters.
- Request timelines are hard to read because every method emits multiple INFO lines, while the actual failure event lacks `error.code` or `outcome`.
- Dashboards based on log counts reflect the number of call sites rather than application behavior.
- Operators may ignore alerts due to being conditioned by high volumes of unremarkable messages (**alert fatigue**).
- Whenever log statements change, the “INFO volume” graph shifts sharply even when traffic and business activity remain unchanged.

For example, if a request calls a repository 12 times and logs “query started/query finished” at INFO each time: 24 log lines still might not tell you whether the final request **succeeded, was slow, or failed**. Instead, a completion event carrying `duration_ms`, `route`, `http.status_code`, `request_id`, and latency metrics per route explains the impact far better.

A useful rule of thumb: **every INFO event must answer a specific operational question**. If the question “when will I need to search for this event?” has no clear answer, the log line likely belongs in DEBUG/TRACE, metrics/traces, or should not be emitted at all.

## 5. Second Consequence: Cost of Creating Logs in the JVM

Even when logs are “just text”, creating events consumes CPU, heap, I/O, and request time.

Potential costs include:

1. **Argument evaluation:** building messages, accessing fields, serializing objects, string concatenation, formatting numbers/dates.
2. **Object allocation:** `StringBuilder`, byte arrays, maps, stack traces, and exception details creating GC pressure.
3. **Encoder/layout:** formatting timestamps, severity, thread, MDC, JSON escaping, Unicode encoding.
4. **Appender/handler:** writing to console/file/network, lock contention, flush or `fsync` depending on configuration.
5. **Async queue:** enqueueing, allocating buffers, backpressure, or discarding when full.
6. **Agent/shipper and backend:** CPU for parsing/indexing, disk storage, network egress, retention, querying.
7. **Cascading impact:** if logs are produced faster than the backend can ingest them, full queues/disks reduce application throughput, increase latency, or cause log loss.

Not every INFO call has the same cost: a tiny constant message can be cheap, while dumping a large object or stack trace on every request can be extremely expensive. Benchmark under realistic workloads and stacks rather than making absolute assumptions based solely on level.

### Eager Parameter Evaluation

Common mistake:

```java
logger.fine("state=" + expensiveSnapshot());
```

In Java, `expensiveSnapshot()` is invoked **before** the `fine` method decides whether to log. Even when `FINE` is disabled, the cost of building the snapshot still occurs.

JUL provides overloads taking `Supplier<String>` so the message is built only when the level is enabled:

```java
logger.log(Level.FINE, () -> "state=" + expensiveSnapshot());
```

When `FINE` is disabled, this supplier **is not invoked to format the message**. With SLF4J, placeholder parameterization avoids string concatenation before checking the level, but **does not defer expensive expressions** passed as arguments:

```java
logger.debug("state={}", expensiveSnapshot()); // expensiveSnapshot() still runs
```

If you need to avoid the computation, consider:

```java
if (logger.isDebugEnabled()) {
    logger.debug("state={}", expensiveSnapshot());
}
```

The SLF4J snippets above are **not standalone programs**; they require a logger and dependencies. With SLF4J 2.x, the fluent API can support suppliers via the appropriate overload, though you must verify the exact version/provider and semantics:

```java
logger.atDebug()
      .addArgument(() -> expensiveSnapshot())
      .log("state={}");
```

Do not assume every logging API is lazy just because a message uses placeholders. Furthermore, logging an object via `toString()` may trigger I/O or read sensitive data; do not pass whole objects to default INFO logs.

## 6. Third Consequence: Transport, Storage, and Query Costs

Suppose a Java API serves **2,000 requests/second**, each request emits an average of **6 INFO lines**, and each serialized line is about **400 bytes**.

```text
events_per_second = 2,000 × 6 = 12,000 events/s
bytes_per_second  = 12,000 × 400 = 4,800,000 B/s
                  ≈ 4.8 MB/s (decimal)
bytes_per_day     = 4,800,000 × 86,400
                  = 414,720,000,000 B
                  ≈ 414.72 GB/day (decimal)
```

If redesigned to **one completion event/request** with the same average size of 400 bytes:

```text
events_per_second = 2,000
bytes_per_day     = 2,000 × 400 × 86,400
                  = 69,120,000,000 B
                  ≈ 69.12 GB/day
reduction         ≈ 345.60 GB/day
```

This is a **raw byte estimate** and does not include indexes, metadata, replication, compression, retention tiers, network overhead, retries, or logs from other components. This reduction ratio is not a guarantee; changing schemas or formats can alter event sizes.

Higher cost is not limited to “ingest fees”: large log volumes increase file rotation, Collector parsing time, queue depth, risk of backend throttling, query costs, and long-term storage. Worse, critical logs may be **dropped by overload-protection mechanisms** right when an incident occurs.

The takeaway is not to eliminate all INFO logs to save money. Prioritize **removing purposeless events and redundant payloads**, keeping useful milestones, optimizing the observability pipeline, and evaluating total cost.

## 7. Fourth Consequence: Sensitive Data Exposure and Security Risks

INFO is typically enabled in production long-term and shipped to a centralized system accessible by many people or services. Using INFO to dump everything makes it easy to record:

- Passwords, tokens, API keys, cookies, authorization headers, or connection strings containing credentials.
- Request/response bodies containing PII, payment details, or personal records.
- Raw URLs/query strings containing signed links, emails, or temporary codes.
- Full SQL queries with sensitive parameter values.
- Entire Java objects whose `toString()` includes secret fields.
- Tenant/resource details unnecessary for investigation.

**Changing INFO to DEBUG is not a security control.** DEBUG can be enabled during an incident, and data still flows through console/file/Collector. You must design **data minimization at the call site**, structured allowlists, redaction, and access controls across all levels. For audits, never log plaintext secrets in before/after states.

Untrusted input may contain newlines/CRs or control characters that cause **log injection** if concatenated directly into text lines. A verified JSON encoder escapes record boundaries, but it does not validate client-supplied actor/outcome fields. Separate trusted system metadata from user-supplied fields.

## 8. Fifth Consequence: Distorting Metric and Alert Semantics

If a system sets an alert `count(severity=INFO) > N`, every release that adds a log statement can push the alert higher unrelated to any incident. Similarly:

- **INFO line count ≠ request count.** One request emits multiple logs, while another emits none due to filtering/sampling.
- **ERROR line count ≠ failed request count.** A single request may have multiple retries or an exception logged at multiple layers.
- **Logs resent by an exporter** can create duplicates, inflating line counts even when application activity has not increased.
- **Decreased log volume** could mean lower traffic, disabled logging, or pipeline drops — you cannot conclude the system is healthy from a log-count graph alone.

SLI metrics such as request success/error rate, latency, and throughput should be instrumented at boundaries with clear definitions, rather than inferred by counting ad-hoc messages. If using log-derived metrics, you must design event names, unique event IDs, level/sampling policies, deduplication, and error handling transparently.

### Do Not Turn INFO Into the Source of Truth for Audits

Audit events may need to be preserved even if the INFO root level is changed, an agent fails, or the pipeline samples logs. For operations like permission grants or administrative actions, you need an audit event schema and durable storage per contract, possibly using an outbox or a dedicated audit store. A `logger.info("role changed")` call typically **does not provide atomicity between a DB commit and an audit record**.

## 9. Choosing the Right Observability Signal: Log, Metric, or Trace?

| Information Needed | Appropriate Source | Example |
| --- | --- | --- |
| Request success/failure, latency, count | HTTP metrics and policy-based completion logs | `http.server.request.duration`, status 503 |
| An important business operation changed state | INFO business event or audit route if mandatory | `order.accepted`, `role.revoked` |
| A dependency retried but eventually recovered | WARN event + retry/fallback metric | `dependency.retry` |
| Variable values in a branch during debugging | Controlled DEBUG/TRACE, without secrets | `validation.rule.chosen` |
| Flow across multiple services/spans and duration | Distributed trace + correlation | `trace_id`, span name/duration |
| Error frequency by service/route/error code | Counter/histogram with bounded tags | `requests_failed_total` |
| Mandatory business evidence | Audit event + durable store/outbox | `access.policy.changed` |
| Log pipeline health | Self-metrics and canaries | Queue depth, dropped events, ingest lag |

**An event does not always belong to only one signal.** You can use completion logs and request duration metrics side by side, provided you understand they describe **the same request in two different units of observation**. Metrics use bounded dimensions; request IDs/trace IDs belong in logs/traces, not as metric labels, to avoid high cardinality.

## 10. Designing an Intentional INFO Policy

Replace “put everything at INFO so it’s easy to see” with an **event catalog**.

| Event | Log at INFO? | Recommended Fields | Rationale |
| --- | --- | --- | --- |
| `service.started` | Usually yes | service, version, environment, safe config profile | Rare operational milestone |
| `http.request.completed` | Yes if access log policy requires it | method, matched route, status, duration, request ID | Budgeted one event/request |
| `batch.completed` | Yes | job ID, processed count, failed count, elapsed | Summarizes a batch instead of each item |
| `order.accepted` | Depends on business | event ID, valid internal order ID, outcome | Business milestone requiring reconciliation |
| `repository.query.started` | Usually no | DEBUG/TRACE or DB metric | High frequency and little direct meaning |
| `loop.item.processed` | Usually no | Selective DEBUG or aggregation | Avoids millions of events |
| `dependency.retry` | WARN on anomaly | dependency, attempt, reason, request ID | Indicates degradation |
| `request.failed` | ERROR on real failure | error code, route, request ID, exception type | Aids investigation of final failure |
| `authz.access.denied` | Security/audit per policy | verified actor, resource, reason | Do not rely solely on INFO level |
| `credential.rotated` | Dedicated audit route | key identifier, actor, outcome | No secrets and no default sampling |

**This list is not a rigid law.** A system requiring full access logging may log INFO on every HTTP request; batch processing may need to audit every item; security policy may require retaining every denied event. Define requirements, volume, retention, data consumers, and trust boundaries before deciding.

### A Contract for INFO Events

An important INFO log should answer:

- **What happened?** Stable `event.name`, outcome.
- **Where?** `service.name`, environment, instance/version when useful.
- **When?** Timestamp with timezone/UTC, distinct from ingest time.
- **Which entity?** Internal IDs only when necessary and per security policy.
- **Which request?** `request_id`/`trace_id`/`span_id` when present.
- **What impact?** Status/error code/duration/count if it is a completion event.
- **Is it searchable?** JSON schema, encoder/parser, retention, and search permissions.

Avoid uncataloged INFO messages like `"Step 7 done"`: after refactoring, step 7’s meaning changes and dashboards/saved searches can break. Event names must be stable; human-readable messages can evolve.

## 11. Standalone Java 17 Example: Meaningful INFO, Controlled FINE, Lazy Supplier

This example uses **JDK 17** only, with no Maven, SLF4J, or Spring Boot required. It demonstrates three things:

1. `INFO`, `WARNING`, and `SEVERE` have distinct semantics and are still printed when the logger is at the INFO threshold.
2. Expensive parameter concatenation **is evaluated even when `FINE` is disabled**, whereas JUL’s `Supplier<String>` message is deferred.
3. When FINE is temporarily enabled, only the selected diagnostic events appear; there is no need to promote every detailed narrative to INFO.

Create the file **`LoggingInfoAntipatternDemo.java`**:

```java
import java.util.concurrent.atomic.AtomicInteger;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class LoggingInfoAntipatternDemo {
    private static final Logger LOG =
            Logger.getLogger("example.logging.levels");

    private static String buildDiagnostic(AtomicInteger calls) {
        calls.incrementAndGet();
        // In a real application, this can be very expensive in CPU or allocations.
        return "details=redacted-summary";
    }

    public static void main(String[] args) {
        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.INFO);

        Handler sink = new Handler() {
            @Override
            public void publish(LogRecord record) {
                if (isLoggable(record)) {
                    System.out.println(
                            record.getLevel().getName()
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
            // Not printed because FINE is disabled, but buildDiagnostic still runs!
            LOG.fine("event=payment.detail "
                    + buildDiagnostic(eager));

            // Not printed and does not call buildDiagnostic when FINE is disabled.
            LOG.log(Level.FINE, () ->
                    "event=payment.detail " + buildDiagnostic(lazy));

            // Operationally meaningful milestones are still logged at explicit levels.
            LOG.info("event=order.accepted order_id=42");
            LOG.warning(
                    "event=payment.retry attempt=1 reason=TIMEOUT");
            LOG.severe(
                    "event=payment.failed reason=TIMEOUT");

            // Enable FINE in a controlled manner to capture one diagnostic event.
            LOG.setLevel(Level.FINE);
            LOG.log(Level.FINE, () ->
                    "event=payment.detail " + buildDiagnostic(lazy));

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
javac LoggingInfoAntipatternDemo.java
java LoggingInfoAntipatternDemo
```

**Exact stdout:**

```text
INFO event=order.accepted order_id=42
WARNING event=payment.retry attempt=1 reason=TIMEOUT
SEVERE event=payment.failed reason=TIMEOUT
FINE event=payment.detail details=redacted-summary
COUNTS eager_calls=1 lazy_calls=1
```

Explanation:

- Initially `LOG.setLevel(Level.INFO)` disables `FINE` records. The line `LOG.fine("..." + buildDiagnostic(eager))` is not published, yet **the method is still called once**, resulting in `eager_calls=1`.
- `LOG.log(Level.FINE, () -> ...)` evaluates the supplier only when the record is loggable. The first call at INFO is skipped, so `lazy` is not incremented.
- `INFO` records the tracked success milestone, `WARNING` records the retry/degradation, and `SEVERE` records the failure. The example includes both WARN and ERROR to illustrate the taxonomy; in a real operation, you might not log a final error if a retry succeeded.
- `LOG.setLevel(Level.FINE)` temporarily enables diagnostics; the second supplier is invoked exactly once and prints one FINE line.
- The custom `Handler` strips default timestamps/layouts to keep output deterministic. `LOG.setUseParentHandlers(false)` prevents parent handlers from printing duplicate lines to stderr.
- The counters in this example only check *argument evaluation* cost, not real CPU/GC/I/O. To benchmark latency or throughput, use JMH/profiling on a representative production stack.

**Limitations:** this is a single-threaded JUL example with plain text log messages. It does not include an HTTP server, JSON encoder, async queue, MDC, audit storage, or distributed tracing. In a multithreaded application, changing a logger level globally affects all threads sharing that logger; production systems should enforce policies, configuration, TTLs, and permissions for enabling DEBUG/FINE rather than toggling it arbitrarily per request.

## 12. JUL, SLF4J, Logback, Log4j2, and Spring Boot: Level Configuration

### JUL

A simple Java setup:

```java
Logger logger = Logger.getLogger("com.example.orders");
logger.setLevel(Level.INFO);  // Allows INFO, WARNING, SEVERE.
logger.fine("Low-level detail");
logger.info("Order accepted");
```

This snippet is **not standalone** without imports and context; where logs are written also depends on the `Handler`, the handler’s level, and `LogManager` configuration. In JUL, an event reaches output only when it passes **both logger and handler filtering**. Changing the logger level is not enough if the handler still filters out `FINE`. You can use a JUL configuration file per application, though exact option names should be verified against your runtime.

### SLF4J

SLF4J is a **facade**, not the log sink. A compatible provider/backend such as Logback or Log4j2 performs filtering, encoding, and appending. With SLF4J:

```java
logger.debug("event=order.validation rule={}", ruleName);
logger.info("event=order.accepted orderId={}", orderId);
logger.warn("event=payment.retry attempt={}", attempt);
logger.error("event=order.failed code={}", errorCode, throwable);
```

This is an **illustrative snippet** and is not standalone since it requires a logger, context variables, and SLF4J dependencies. INFO does not need full exception stack traces for every retry; `ERROR` with a `Throwable` should be used for meaningful failures observed at an appropriate boundary.

### Logback

Illustrative level configuration (assuming the application **already has an appender**):

```xml
<configuration>
    <!-- Only the package under investigation temporarily uses DEBUG. -->
    <logger name="com.example.payment" level="DEBUG"/>

    <!-- Root for the remaining packages stays at INFO. -->
    <root level="INFO"/>
</configuration>
```

This is only a **configuration fragment expressing levels**, not a complete Logback file guaranteed to emit logs: you still need appenders/encoders and the proper `appender-ref` wiring. If an appender also has a `ThresholdFilter` or root/child additivity causes duplicate logs, verify the actual pipeline.

Log4j2 has its own configuration/logger/appender structure; do not copy Logback XML expecting Log4j2 to interpret it the same way.

### Spring Boot

Spring Boot typically allows declaring log levels per package (when supported by the stack):

```properties
logging.level.root=INFO
logging.level.com.example.payment=DEBUG
```

This is **a fragment of `application.properties`**, not a complete Spring Boot application. Changing levels at runtime via Actuator or an admin UI depends on dependencies, endpoint exposure, version, and authentication; never leave level-changing endpoints publicly exposed. If enabling DEBUG in production, enforce **an owner, package scope, TTL/time limit, volume monitoring, and a turn-off procedure**.

### Prefer Scoped Log Level Changes

Prefer enabling DEBUG for the `com.example.payment` namespace rather than switching the entire system to `root=DEBUG`. Adding request/trace correlation, metrics, and tracing often provides investigative data without every package emitting routine lines at INFO.

Never hardcode secrets in configuration files or log-level change events. Log-level changes should also have appropriate auditing or change tracking if they affect cost and privacy.

## 13. Fewer Logs, Richer Information

An informative event does not mean a long event. Access completion example:

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
  "request_id": "req-101",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736"
}
```

This is an **illustrative schema**, not a payload automatically generated by every SDK/Collector. Attribute names in OpenTelemetry HTTP semantic conventions and backend mappings can vary by version; configurations must be verified against your runtime.

Compared to ten “enter/exit” INFO lines, this completion event is easy to filter by route, status, duration, and request ID. For failed requests, you can add `error.code` and `exception.type`, while messages/stack traces are emitted separately per policy.

A structured event should have:

- A stable **event name** and schema version if multiple systems consume it.
- Explicit UTC/offset timestamp, service, environment, version, and instance when needed.
- Outcome, status/error code, and duration/count with well-defined units.
- Request/trace ID for correlation, not as metric labels.
- Fields from trusted sources containing no secrets.
- Bounded size to avoid overloading parsers/ingesters or storage.

**Do not use raw exception messages, raw URLs, user IDs, or request IDs as metric labels.** Metric cardinality will explode; correlation belongs in logs/traces with appropriate access controls.

## 14. When to Aggregate Instead of Logging INFO per Event?

Many codebases log INFO inside a loop:

```java
for (Order order : orders) {
    logger.info("Processed order {}", order.id());
}
```

This is an **illustrative SLF4J snippet**, not standalone; it requires `orders`/`Order`/`logger`. If there are one million items, emitting one million INFO lines is rarely useful. Alternatives:

- Count total processed/failed/skipped items and elapsed time, then emit **one summary event** when the batch completes.
- Use metric counters/timers to measure progress, throughput, and failure rate.
- If per-item auditing is required, emit an **audit/business event** with a durable storage contract, not plain INFO.
- When needing to trace a specific ID for debugging, enable controlled diagnostics by job/request ID or query business data, rather than bulk-logging PII.
- For long-running jobs, emit **periodic checkpoints** at defined time or volume intervals rather than per item.
- If a small percentage is needed for debugging, sample according to policy and record the sampling rate, avoiding the use of sampled data to prove exact totals.

Do not over-aggregate to the point of losing mandatory information. For example, a funds transfer operation required by policy to record every transaction cannot be replaced by a single line saying “processed 1,000 transactions”.

## 15. Sampling, Rate Limiting, and Policies for Excessive Logging

Replacing detailed INFO with DEBUG does not eliminate all risk: DEBUG can still be enabled and produce massive bursts. You can apply:

| Technique | Effect | Risk to Manage |
| --- | --- | --- |
| **Level filtering** | Enable only appropriate levels, disable details by default | Missing context if errors lack a primary event |
| **Scoped dynamic levels** | Enable DEBUG for a package/service in a short window | Volume/PII spikes if scoped too broadly or left on |
| **Diagnostic log sampling** | Retain a small fraction of similar events | Do not use for mandatory audits; avoid bias |
| **Rate limiting** | Cap log spam from loops/repeated errors | Loss of counts if suppressed count is omitted |
| **Aggregation** | Summarize N events into counters/summaries | Loss of per-event detail |
| **Dedup/suppression** | Avoid printing the same error repeatedly in bursts | Must preserve first/last, count, and scope |
| **Bounded async queue** | Decouple request rate from output rate | Full queue causes blocking/dropping per policy |
| **Payload limit/redaction** | Reduce event size and data exposure risk | May truncate useful stack/context |

When sampling, define the **sampling unit**: per-request, per-event, per-error-code, or per-trace. Independent per-line sampling can leave a request’s timeline missing arbitrary steps; consistent trace/request-based sampling is usually better for reconstructing an execution flow, though it carries its own trade-offs.

Crucially: **do not turn sampling into a way to hide incidents**. Request/error metrics should be measured at boundaries with their own semantics; `logs_dropped_total`, queue depth, oldest event age, and exporter retries must be observed independently.

### Should You Rate-Limit WARN/ERROR?

Sometimes a configuration error can emit millions of ERRORs per second and overwhelm the log backend. You can rate-limit repeated messages with a **suppressed count** and alert on metrics, provided you know which rules require keeping every event (such as audits). Losing all visibility during an incident is worse than reducing logs under an intentional policy.

Instead of disabling all ERRORs, design a summary event:

```text
ERROR event=dependency.failed code=DB_UNAVAILABLE first_seen=... 
WARN event=dependency.failures_suppressed count=12000 interval=60s
```

This is illustrative data; suppressed statistics must come from an accurate counter, not by recounting retained log lines.

## 16. Avoiding Duplicate Logs Across Multiple Layers

A failing request may pass through DAO → Service → Controller. An anti-pattern that often accompanies “INFO at every step” is **logging and then rethrowing the same exception**:

```java
try {
    repository.save(order);
} catch (RuntimeException ex) {
    logger.error("Repository failed", ex);
    throw ex;
}
```

This is an illustrative fragment and is not standalone since it requires `repository`/`order`/`logger`. If the service and controller also log ERROR stack traces before rethrowing, the backend receives three error logs for **one failed request**.

How to improve:

1. Choose one **boundary** responsible for logging the final error with complete service/route/request ID/outcome details.
2. Lower layers can emit a different diagnostic event or wrap/attach context to the exception without necessarily printing the full stack.
3. If an attempt fails but a retry succeeds, record a WARN/retry metric and a clear final success.
4. Use separate metrics for downstream attempt errors and HTTP failed requests; do not add both together as “failed requests”.
5. If multiple real events must be logged, give them distinct `event.name` values and record a logical `event_id` for querying and deduplicating transport retries.

**A request ID is not an event ID.** One request can legitimately produce multiple events. Deduplicating the same transport event requires its own key; do not collapse all lines sharing a request ID into one.

## 17. Logging in Servlet, Spring MVC, and Async Java

Web apps often have multiple places where logs can be written:

```text
Gateway -> Servlet Filter -> Security Filter
        -> Controller -> Service -> Repository
        -> Exception Handler -> Response
```

If every layer logs `INFO "request arrived"` and `INFO "request completed"`, a single HTTP call can produce multiple completion-like records. Standardize on:

- Pick one place to emit the **HTTP completion event**, using the actual status and duration when the request finishes.
- **404, 401, 403, and pre-controller exceptions** also need observability per access/security policy; logging only in the controller can miss them.
- With async Servlet/WebFlux, controller return does not always mean response completion; use the proper framework lifecycle hook to avoid premature or duplicate logs.
- Use `http.route` from the framework’s matched route rather than raw URLs containing tokens/IDs as metric labels.
- Context propagation (MDC/ThreadContext) must follow the request across `ExecutorService`, `CompletableFuture`, or reactive pipelines; restore/clear context when threads are reused.

SLF4J MDC can help attach `request_id`/`trace_id` to records, but **MDC does not automatically guarantee propagation across all tasks**. Do not log raw headers, request bodies, or query strings just to “have enough INFO data”.

### Async Logging and Full-Queue Risks

An async appender reduces blocking in many scenarios, but still incurs encoding, allocation, queueing, context copying, and disk/network costs. When the queue fills up, some configurations block requests, while others drop lower-priority levels or fall back to synchronous writes, depending on the framework and version. Therefore, enabling async **does not fix the root cause** of logging too much at INFO.

Monitor `logs_dropped_total`, queue usage, exporter errors, and latency impact on business requests. Never claim “async is definitely faster” without benchmarking under realistic workloads and failure modes.

## 18. During an Incident: Temporarily Enable DEBUG Instead of Flooding INFO

A controlled investigation workflow:

1. **Check SLIs/metrics first:** which service is failing, which route, which version, and when.
2. **Inspect structured INFO/ERROR logs:** request completion, error codes, correlation, outcomes, retries.
3. **Scope DEBUG:** target only the package/class/service under investigation, optionally specific instances and a short time window.
4. **Enforce authorization:** only authorized operators can change log levels; never leave admin endpoints unauthenticated.
5. **Assess data risk:** will the newly enabled DEBUG logs expose tokens, PII, or internal payloads? If so, fix the call site first.
6. **Cap volume:** watch queues, disk, and backend ingest, with a rollback threshold.
7. **Reconstruct the timeline:** follow `request_id`/`trace_id`, combining trace spans and metrics.
8. **Turn off verbose levels and document:** return to the safe baseline, save queries/incident notes, and evaluate updating the event catalog if evidence was missing.

If you frequently have to enable DEBUG to answer a recurring question, you may be missing **a meaningful INFO/ERROR event** or a metric/trace; do not leave DEBUG enabled permanently.

## 19. Testing and Evaluating INFO Logging Quality

### Unit Tests and Code Review

| Scenario | What to Verify |
| --- | --- |
| INFO at service startup | Single event with version/environment, no secrets |
| Successful request | Completion event per policy, no duplicate INFO across layers |
| Failed request | ERROR at final boundary, accurate error code and request/trace ID |
| Failed attempt then successful retry | WARN/retry metric, final request not marked FAILED |
| INFO level with FINE/DEBUG disabled | No diagnostic events emitted; supplier/guard skips expensive payload |
| DEBUG enabled for one package | Only selected details emitted, root not opened unintentionally |
| Message contains newlines/quotes | JSON Lines remain valid, no log injection |
| Data contains tokens/PII | Never appears in INFO, DEBUG, stack traces, MDC, or sinks |
| Async requests/thread pools | Correlation does not leak across requests, cleanup works |
| Misconfigured logger/appender | Health signals detect missing logs |
| Backend 429/503 or full queue | Backpressure/dropping follows policy, app stays stable within limits |
| Mandatory audit event | Not lost due to INFO level filtering/sampling |
| Deployment changes log levels | Dashboards and saved searches do not rely on fragile text |

For the Java 17 demo above, content tests must observe exactly **3 severity lines**, **1 FINE line after enabling**, and counters `eager_calls=1, lazy_calls=1`. When moving to SLF4J/Logback in a real application, write unit/integration tests for the backend and encoder rather than assuming JUL handler behavior is identical.

### Performance Measurement

Use representative JMH benchmarks when comparing eager vs. lazy logging; observe allocations/op, throughput, p95/p99 request latency, GC pauses, log bytes/s, and queue backlog. Test both enabled and disabled log levels, small/large payloads, multiple threads, and failure scenarios.

**Do not benchmark with a single `System.nanoTime()` call and draw conclusions** about framework cost. Warmup, JIT, constant folding, GC, and sink I/O make manual timing error-prone. In real log pipelines, the bottleneck may be the JSON encoder, disk `fsync`, Collector, or cloud ingest rather than calling `logger.info`.

## 20. Related Anti-patterns

| Mistake | Impact | Fix |
| --- | --- | --- |
| Logging INFO enter/exit on every method | Noise, wasted storage | Controlled TRACE/DEBUG, tracing |
| Logging INFO on every loop/item | Cost scales with item count | Aggregate + metrics/batch summary |
| Dumping entire objects at INFO | CPU/GC overhead, sensitive data exposure | Field allowlist and lazy formatting |
| Concatenating strings before level check | Wasted work when level is disabled | Supplier/guard, appropriate parameterized API |
| Treating every exception as ERROR | Recovered attempts look like “final failures” | Severity by outcome; attempt vs. request |
| Logging the same stack trace at every layer | Duplicate records, noisy alerts | Log at the responsible boundary |
| Only INFO, no error code or event name | Hard to search, text-fragile dashboards | Structured events, taxonomy |
| Permanent root DEBUG for “enough data” | Volume spikes and PII risk | Per-package enablement, scope/TTL, monitoring |
| Sampling all INFO including audits | Loss of mandatory events | Dedicated audit channel, retention/durability |
| Cutting INFO by removing needed completion events | Blind spots during incidents | Keep key milestones and metrics/traces |
| Using user ID/request ID as metric labels | Unbounded cardinality | Keep them in logs/traces |
| No pipeline monitoring after level changes | Mistaking silence for health | Self-metrics, heartbeat, canary |
| INFO with raw URLs and query strings | Exposes tokens/PII and creates high variance | Matched route and data minimization |
| Using console INFO counts as business KPIs | Skewed by duplicates/filters/sampling | Instrument counters at business boundaries |

## 21. Checklist for Moving From “Log Everything at INFO” to Purposeful Logging

- [ ] Listed the events operators actually need to find in production?
- [ ] Reserved INFO for meaningful milestones/completions/summaries with budgeted frequency?
- [ ] Reserved DEBUG/TRACE for internal details with scoped package enablement and time limits?
- [ ] Aligned WARN/ERROR with recoverable vs. final failure rather than just `Throwable` type?
- [ ] Assigned a single owner for request completion and exception logging to avoid meaningless duplicates?
- [ ] Included `event.name`, outcome, error code, service, route, duration, and correlation fields where needed?
- [ ] Ensured no secrets/PII/raw tokens or full object dumps appear at any level?
- [ ] Protected expensive computations in disabled logs with suppliers/guards matching your API version?
- [ ] Aggregated high-frequency loop/batch logs or converted them into metrics where appropriate?
- [ ] Defined clear sampling/rate-limit policies that do not violate mandatory audit requirements?
- [ ] Kept SLI metrics as independent semantic signals rather than counting INFO/ERROR lines?
- [ ] Used a structured JSON encoder and verified search/indexing in the log backend?
- [ ] Measured log bytes/s, allocations/GC, queue/drops, and backend ingest/cost before and after changes?
- [ ] Added unit/integration tests for level filtering, duplicates, retry/recovery, async context, and privacy?
- [ ] Set up canaries/self-metrics to detect a silent logging pipeline or dropped logs during incidents?

**Conclusion:** `INFO` is not a “catch-all bucket for everything you want to write”, but **the level for normal operational events that need to be retained and found**. Use DEBUG/TRACE for details, WARN for recoverable degradation, ERROR for final failures per contract, and a dedicated audit route when durable storage is required. Choosing the right events, using structured fields/correlation, avoiding expensive message construction when a level is disabled, and monitoring cost and sensitive data make Java logging **less noisy and far more useful during incidents**.
