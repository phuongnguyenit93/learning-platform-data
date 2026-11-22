# Next Learning Steps After Summarizing Java Core Logging

## 1. Goals of the Next Learning Phase

After mastering Java Core Logging, you have the foundation to create logs, choose levels, pass exceptions, understand appenders/handlers, use MDC, and configure output destinations. **The next learning step** is not just learning another logging library; it is upgrading from **logging inside a single class** to **designing observability that helps investigate and operate a real Java application**.

A system can have millions of log lines and still be difficult to troubleshoot during an incident if:

- Logs lack `requestId`, `messageId`, or `errorCode` to correlate steps.
- The same `Throwable` is logged and rethrown across the repository, service, and controller.
- Worker threads lose MDC or mistakenly inherit the previous request's context.
- Logs are free-form text, so the collector cannot parse them into typed fields.
- Files grow unbounded, rotation deletes audit logs too early, or the exporter drops events when the queue is full.
- Logs contain secrets/PII because the raw request body or exception message is printed.
- A text trace ID exists, but there is no actual trace to open from the dashboard.
- Metrics count ERROR logs, causing a request retried three times to be counted as three failed requests.

**Destination:** being able to design a pipeline of **logging → structured context → metrics/traces → collector/backend → alert/runbook**, verify it with tests, and understand the limits of each component. You do not have to learn every tool at once; choose based on your needs and deliverables.

This lesson provides **priority order**, a **standalone Java 17 project**, a **practice roadmap**, **acceptance criteria**, and **official resources**. The schedules below are suggestions only, not mandatory deadlines or certification standards.

## 2. Self-Assessment of Fundamentals Before Moving On

Try explaining and demonstrating the following items with a sample project:

| Competency | Check Question | Practical Evidence |
| --- | --- | --- |
| JUL | What roles do `Logger`, `Handler`, `Formatter`, and `LogRecord` play? | Run a logger with a custom handler |
| SLF4J | How does the façade/API differ from a provider/backend? | Dependency tree has only the intended provider path |
| Level | When should you use INFO, WARN, or ERROR? | Normal validation does not print unnecessary ERROR stack traces |
| Throwable | Why can log-and-rethrow duplicate errors? | A terminal failure has only one clear log owner |
| Structured fields | How does `errorCode` differ from exception class, status, and message? | Output has a consistent schema and types |
| Context | How do `requestId`, `correlationId`, `traceId`, and `messageId` differ? | Events for a specific request/message can be found |
| MDC | Why can a thread pool mix up IDs? | Test A → B → no-context on a single worker |
| Retention | How does rolling differ from audit retention? | Test archive limits without deleting audit logs improperly |
| Reliability | How do you know if logs were dropped or failed to export? | Metrics and alerts at the sink/pipeline |
| Privacy | Why should you not print raw headers/payloads? | Test with a fake secret marker that does not appear in logs |
| Tracing | Does MDC automatically create a span? | Traces link with logs when spans are exported |

If you cannot answer an item yet, do a mini-exercise for that item **before adding more technologies**. Do not substitute memorizing the names OpenTelemetry or Prometheus for understanding how an event flows from code to backend.

### Suggested Competency Progression Scale

- **Level 1 — proper logging:** choosing levels, APIs, and `Throwable` handling without leaking secrets or over-logging.
- **Level 2 — structured logs:** having `event`, `errorCode`, correlation IDs, typed fields, and leak-free MDC.
- **Level 3 — reliable pipeline:** configuring appenders, rotation, collector, retention, and log-loss alerts.
- **Level 4 — integrated observability:** logs, metrics, and traces connected together, with dashboards, SLOs, and runbooks.
- **Level 5 — production readiness:** practicing incident drills, async/microservices debugging, privacy, and cost control.

This is a **learning framework suggested by this lesson**, not an official Java or OpenTelemetry certification level.

## 3. Priority Roadmap and Specialization Tracks

~~~text
Java Core Logging Fundamentals
          |
          v
[1] Standardize Logger/API/Backend + Exception ownership
          |
          v
[2] Structured events + Error code + Schema
          |
          v
[3] MDC + Request context + Async propagation
          |
          +-----------------------+
          |                       |
          v                       v
[4A] Pipeline reliability    [4B] Core metrics
     rolling, collector           rate, errors, latency
     queue, retention             saturation
          |                       |
          +-----------+-----------+
                      |
                      v
[5] OpenTelemetry + Distributed tracing
    trace/span context, OTLP, Resource
                      |
                      v
[6] Dashboards, alerts, SLOs, incident response
                      |
                      v
[7] Capstone or specialization
    Backend / Messaging / Platform / Security
~~~

**Stages 4A and 4B can be learned in parallel.** A single-process application still needs structured logging and proper disk/retention management. A microservice with many downstream calls benefits greatly from tracing. An audit system with strict retention policies should solve durability/retention before enabling sampling to reduce costs.

### Choosing the Next Learning Topic by Real-World Problem

| If you encounter this situation | Topic to prioritize | Measurable outcome |
| --- | --- | --- |
| Every developer logs differently | SLF4J, single provider, level and event conventions | No duplicate providers/appenders |
| Cannot find logs for the same request | Structured logging + MDC | Find logs by requestId without task mix-ups |
| Worker loses requestId | Context propagation across ExecutorService | A/B/no-context test |
| Same stack trace printed three times | Exception ownership and log-and-rethrow | One terminal failure record |
| Logs fill the disk or are lost on restart | Rotation, retention, stdout/container pipeline | Time-to-reserve and drop alert in place |
| Bottlenecks only visible in production | Metrics: rate/errors/latency/saturation | Dashboards and SLOs with clear units |
| Requests cross multiple services | Distributed tracing, W3C context | Logs attached to real spans |
| Kafka/RabbitMQ processes duplicates | Message ID, retry, DLQ, idempotency | Logs distinguish attempts |
| Sensitive log data | Redaction, RBAC, audit | Privacy tests at every sink |

## 4. Stage 1: Standardize the Logging API and Error Destinations

**JUL** belongs to the JDK and provides `Logger`/`Handler`/`Formatter`. **SLF4J** is a façade/API for applications and libraries; **Logback** or an appropriate provider is what actually formats and sends events to a sink. **Log4j 2** has its own API/core and appropriate bridges depending on the environment.

Key practice exercises:

1. Create a small project using JUL, logging one INFO event and one WARNING event with a `Throwable`.
2. Migrate the same logic to SLF4J 2.x with a chosen backend, such as Logback; avoid accidentally adding multiple SLF4J providers.
3. Log `event`/`requestId`/`errorCode` by convention; do not turn raw exception messages into error codes.
4. Configure a console appender; if adding a file appender, verify that each `LogEvent` goes to each intended sink only once.
5. Use a test handler/capturing appender to count events at the sink, rather than only verifying mock logger calls.

Example **SLF4J snippet** (requires appropriate dependencies; not a standalone Java file):

~~~java
private static final org.slf4j.Logger LOG =
        org.slf4j.LoggerFactory.getLogger(OrderService.class);

void report(String safeOrderRef, long durationMs) {
    LOG.info("event=order_processed orderRef={} durationMs={}",
            safeOrderRef, durationMs);
}
~~~

`OrderService` and the variables are application-defined. Parameterized logging lets the backend handle formatting, but it **does not automatically sanitize secrets** and does not automatically turn placeholders into typed JSON fields.

In SLF4J 2.x, there is a fluent API:

~~~java
LOG.atInfo()
   .addKeyValue("event", "order_processed")
   .addKeyValue("orderRef", safeOrderRef)
   .addKeyValue("durationMs", durationMs)
   .log("Order processed");
~~~

The actual encoder/layout must support key–value pairs if you want to export JSON. This fluent API does not exist in SLF4J 1.7. Avoid computing large objects or serializing JSON when DEBUG is disabled; use level checks or lazy computation when needed.

**Stage 1 deliverable:** a logging conventions page documenting standard levels, error boundaries, context fields, the approved provider, appender routes, and `Throwable` handling policy.

## 5. Stage 2: Structured Logging and Event Contracts

In text logs:

~~~text
INFO order done
WARN payment failed
~~~

operators struggle to aggregate by request and error type. A structured event provides individual fields:

~~~json
{
  "timestamp": "2026-11-10T08:00:00Z",
  "level": "ERROR",
  "service": "checkout",
  "event": "payment_failed",
  "errorCode": "PAY_TIMEOUT",
  "requestId": "req-A",
  "attempt": 2,
  "outcome": "failure",
  "durationMs": 47
}
~~~

This JSON only **illustrates an application schema**; it is not the automatic output of SLF4J/Logback or a raw OpenTelemetry `LogRecord`. `durationMs` is a **number**, not the string `"47ms"`. `event` and `errorCode` are bounded sets of values used for grouping and alerting, while `requestId` is a dynamic identifier used for querying individual requests.

Schema design rules:

- **Stable event names:** `request_received`, `operation_succeeded`, `operation_failed`, `retry_scheduled`, `message_dead_lettered`. Do not concatenate `userId`, filenames, or timestamps into event names.
- **Error code taxonomy:** distinguish validation, business conflict, dependency timeout, and unexpected bugs; do not use `exception.getMessage()` or raw class names as public API codes.
- **Separate fields by role:** Resource/service metadata; request/trace/message context; event-specific attributes.
- **Consistent data types:** numeric duration, integer attempt, boolean success if used; changing types or names requires a migration plan.
- **Do not log raw bodies/headers:** they can leak PII, cookies, tokens, SQL, and secrets.
- **Limit inputs:** validate IDs, escape newlines/control characters, and choose an encoder that supports JSON escaping.
- **Realistic testing:** assert the content after the encoder/appender and after the collector, not just objects in code.

**Stage 2 deliverable:** parseable structured output, a catalog of at least five useful events, two error categories, and a schema integration test.

## 6. Stage 3: MDC and Context Propagation

MDC (**Mapped Diagnostic Context**) holds key–value pairs attached to the processing thread, such as `requestId`/`tenantRef`. The logging backend can pull them from MDC and include them across many events. However, `MDC.put(...)` on a web thread **does not automatically transfer values to worker threads**, nor does it propagate across HTTP or message brokers.

An **SLF4J snippet** managing scope:

~~~java
import java.util.Map;
import org.slf4j.MDC;

Map<String, String> previous = MDC.getCopyOfContextMap();
try {
    MDC.put("requestId", verifiedRequestId);
    businessOperation();
} finally {
    if (previous == null) {
        MDC.clear();
    } else {
        MDC.setContextMap(previous);
    }
}
~~~

This is not a standalone program: `verifiedRequestId` and `businessOperation()` are application-defined. IDs must be generated/validated at the boundary; do not trust a user-supplied `X-Tenant-Id` as proof of tenant authorization.

**Mandatory test:** use an `ExecutorService` with a single reusable worker, processing A, then B, then a non-request task:

~~~text
task A -> requestId=req-A
task B -> requestId=req-B
non-request task -> requestId=none
~~~

No log from B may carry A's ID. The wrapper must **capture** MDC on submit, **set/restore** it on the worker, and clean up in `finally`. If the framework already integrates tracing context, do not call `MDC.clear()` in an arbitrary layer and wipe out keys owned by another agent; understand scope ownership.

**Stage 3 deliverable:** a middleware/context wrapper with tests for cleanup on exception, task propagation, and absence of leaked context.

## 7. Stage 4: Exceptions, Retries, and Logging Ownership

An error in the repository passing through the service and then the HTTP handler can still be **a single business failure**. If every `catch` runs `LOG.error(..., ex)` and then `throw ex`, dashboards may count three ERRORs, I/O cost rises, and the stack trace is duplicated multiple times.

Design approach:

1. Domain/repository layers **preserve the `Throwable` cause** and translate to a meaningful exception when needed.
2. The service layer can perform fallback/retry, but should not reprint the same stack trace just because it rethrows.
3. The HTTP/message/job boundary decides the final outcome and logs the failure with `errorCode`/`requestId`/`outcome` in one clear place.
4. Retry attempts and scheduled retries are **real milestones** that can be logged separately with attempt and reason, but should not be treated as three terminal failures.
5. Metrics count **final failed operations**, not simply the number of ERROR logs.
6. With Kafka/RabbitMQ, `messageId` may stay the same across redelivery while delivery metadata/attempt changes; knowing the message ID **does not replace idempotency**.

Example:

~~~text
event=payment_attempt_failed requestId=req-B attempt=1 errorCode=PAY_TIMEOUT
event=retry_scheduled requestId=req-B attempt=1 delayMs=200
event=checkout_failed requestId=req-B attempt=2 outcome=failure errorCode=PAY_TIMEOUT
~~~

There are three events, but only one terminal checkout failure. When wrapping exceptions, do not lose the cause with `new DomainException("failed", null)` and then log text without the root cause; preserve the cause for authorized internal sinks.

## 8. Java 17 Mini-Capstone: Logging Events and Measuring Outcomes in the Right Units

Before integrating external libraries, use a **JDK 17–only** exercise to understand how a `LogRecord` flows, with separate events for retry and terminal failure. The following snippet contains the complete class, with a fixed filename and deterministic output. It **does not perform HTTP calls, measure real latency, export metrics, or create distributed traces**.

Create the file **`LoggingNextStepsDemo.java`**:

~~~java
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class LoggingNextStepsDemo {
    record Event(
            String event, String requestId,
            String outcome, String errorCode, long durationMs) {}

    private static final Logger LOG =
            Logger.getLogger("learning.next.steps");

    private static final class CompactHandler extends Handler {
        @Override
        public void publish(LogRecord record) {
            if (!isLoggable(record)) {
                return;
            }
            Object[] params = record.getParameters();
            if (params == null || params.length != 1
                    || !(params[0] instanceof Event e)) {
                return;
            }
            System.out.println(
                    "level=" + record.getLevel().getName()
                    + " event=" + e.event()
                    + " requestId=" + e.requestId()
                    + " outcome=" + e.outcome()
                    + " errorCode=" +
                        (e.errorCode() == null ? "none" : e.errorCode())
                    + " durationMs=" + e.durationMs()
                    + " hasCause=" + (record.getThrown() != null));
        }

        @Override
        public void flush() {
            // No separate I/O buffer.
        }

        @Override
        public void close() {
            // No external resources.
        }
    }

    private static void emit(
            Level level, Event event, Throwable thrown) {
        LogRecord record = new LogRecord(level, event.event());
        record.setParameters(new Object[] { event });
        record.setLoggerName(LOG.getName());
        record.setThrown(thrown);
        LOG.log(record);
    }

    public static void main(String[] args) {
        Level oldLevel = LOG.getLevel();
        boolean oldParent = LOG.getUseParentHandlers();

        CompactHandler handler = new CompactHandler();
        handler.setLevel(Level.ALL);
        LOG.setLevel(Level.ALL);
        LOG.setUseParentHandlers(false);
        LOG.addHandler(handler);

        int operations = 0;
        int failures = 0;

        try {
            operations++;
            emit(Level.INFO,
                    new Event(
                            "order_processed", "req-A",
                            "success", null, 12),
                    null);

            operations++;
            IllegalStateException cause =
                    new IllegalStateException(
                            "simulated upstream timeout");

            emit(Level.WARNING,
                    new Event(
                            "payment_retry_scheduled", "req-B",
                            "retry", "PAY_TIMEOUT", 40),
                    cause);

            emit(Level.SEVERE,
                    new Event(
                            "checkout_failed", "req-B",
                            "failure", "PAY_TIMEOUT", 45),
                    cause);
            failures++;

            System.out.println(
                    "operations=" + operations
                    + " failures=" + failures);
        } finally {
            LOG.removeHandler(handler);
            LOG.setUseParentHandlers(oldParent);
            LOG.setLevel(oldLevel);
            handler.close();
        }
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 LoggingNextStepsDemo.java
java LoggingNextStepsDemo
~~~

**Exact expected stdout:**

~~~text
level=INFO event=order_processed requestId=req-A outcome=success errorCode=none durationMs=12 hasCause=false
level=WARNING event=payment_retry_scheduled requestId=req-B outcome=retry errorCode=PAY_TIMEOUT durationMs=40 hasCause=true
level=SEVERE event=checkout_failed requestId=req-B outcome=failure errorCode=PAY_TIMEOUT durationMs=45 hasCause=true
operations=2 failures=1
~~~

Equivalent logic was executed with JShell using APIs available since Java 17, producing these exact four lines. This file was not compiled with `javac --release 17` during the verification session, so you should verify it yourself using the commands shown above.

### Code Explanation

- `Event` is a Java record holding properties specific to a single log entry. `LogRecord.setParameters` is read by the custom handler according to **the demo's own contract**; default JUL loggers/OTel exporters **do not automatically** turn this record into JSON Attributes.
- `requestId=req-A` completes successfully with `hasCause=false`. Request B has one retry milestone and one terminal failure; both keep `errorCode=PAY_TIMEOUT` but have different `outcome` values.
- `durationMs` values are **fixed illustrative numbers**, not measured from a clock. In real implementations, use `System.nanoTime()` to compute elapsed duration instead of subtracting wall-clock times.
- `operations=2 failures=1` demonstrates counting operations/outcomes rather than counting `LogRecord`s or stack frames. These local variables are not Prometheus/OpenTelemetry metrics.
- `LogRecord.setThrown(cause)` preserves a cause so authorized internal sinks can record diagnostics. The demo only prints `hasCause` to keep stdout deterministic; that does not mean production should strip stack traces everywhere.
- `LOG.setUseParentHandlers(false)` prevents the parent JUL console handler from printing duplicate events. This manages log routing, **not** log-and-rethrow code.
- The program does not perform real retries, network calls, or side effects. Do not use `errorCode` as an idempotency key.

### Extensions for the Demo

1. Add started/succeeded/failed events using an event schema and typed fields instead of string concatenation.
2. Migrate to SLF4J + Logback with a structured JSON encoder, verifying output via a test appender.
3. Add `requestId` via MDC and run in a thread pool with a capture/restore wrapper.
4. Throw a different `Throwable` and verify that a failure is logged only at the boundary.
5. Replace the counter variables in `main` with a real metrics SDK appropriate for your stack.
6. Add tracing instrumentation, read the trace ID from the active span, and link logs with the exported trace.

## 9. Stage 5: Learning Metrics to Measure Trends

**Logs answer "what happened in a specific execution?"** Metrics answer "how many happened, at what rate, and is anything abnormal?". When learning metrics, focus on **the right units of measurement**:

- Request/operation rate: number of operations per unit of time.
- Terminal error rate: final failed operations / total operations.
- Duration distribution: latency histogram to estimate appropriate percentiles.
- Saturation: thread pool queue, heap/GC, CPU, connection pool, disk.
- Logging pipeline health: drops, write errors, exporter retries, queue backlog.
- Business outcomes: payments succeeded/failed, messages processed/DLQ according to schema.

You can explore **Micrometer** when using Spring or the **OpenTelemetry Metrics SDK** depending on your architecture. You do not need to use both for the same instrument if it causes duplicate telemetry.

Illustrative Prometheus text example (not produced by the code in Section 8):

~~~text
operations_total{operation="checkout",outcome="success"} 1200
operations_total{operation="checkout",outcome="failure"} 12
~~~

Use only bounded labels such as `operation`/`outcome`/`service`/`route template`/`errorCode` catalog values. Do not put `requestId`, `messageId`, `userId`, exception messages, or URLs containing numeric IDs into metric labels; cardinality can grow with every request and blow up memory and cost.

**Practice:** add a counter and duration histogram to your capstone; build an error rate/latency dashboard; simulate an operation that retries twice and then succeeds to verify that the **terminal failure counter does not increment incorrectly**.

## 10. Stage 6: Distributed Tracing and OpenTelemetry

When a request travels across HTTP service A → message broker → service B, per-service logs alone make it hard to see the path and wait times. **Distributed tracing** models execution with traces/spans. **OpenTelemetry** provides APIs/SDKs, instrumentation, semantic conventions, and context propagation to connect telemetry.

| Field | Meaning | Do not confuse with |
| --- | --- | --- |
| `traceId` | Identifier for an entire causally linked trace | An API's `requestId` or idempotency key |
| `spanId` | One execution span within a trace | The entire request/business workflow |
| `requestId` | ID defined by the app's request contract | Span parent or W3C `traceparent` |
| `messageId` | One logical message | Kafka offset or RabbitMQ `deliveryTag` |
| `correlationId` | Links workflow steps | Equal to `traceId` by default |
| `errorCode` | Stable error category | A single error occurrence |

**MDC does not automatically create a trace.** Manually putting a string into `MDC.put("traceId", "...")` does not prove a span was exported. Obtain trace context from the instrumentation's active span; when crossing process boundaries, use a propagator supporting standards such as W3C `traceparent`.

The OpenTelemetry Java documentation recommends that beginners **start with the Java agent** when the framework already has built-in instrumentation, then add manual spans for business operations that need visibility. The actual agent/SDK, modules, and auto-instrumentation capabilities depend on versions and dependencies; do not copy a `-javaagent` command with a nonexistent path and claim tracing is enabled.

### Three Complementary Signals

~~~text
Alert: latency rises and error rate rises
       |
       v
Metrics: which checkout operation is slow?
       |
       v
Trace: which span takes time, which downstream failed?
       |
       v
Logs: what are the event/errorCode/requestId/cause for that span?
       |
       v
Runbook: fix root cause, verify metrics recover
~~~

Trace sampling can leave a log with a `traceId` but **no corresponding span in the backend**; export failures can also cause gaps. Do not claim that every log with a `traceId` can be clicked through to a trace. Audit logs need their own retention/durability and cannot be replaced by sampled traces.

### Two Ways to Send Logs to OpenTelemetry

1. **Logback/Log4j appender bridge → OTel Log SDK → OTLP → Collector → backend**.
2. **Structured stdout/file → shipper/agent → collector parse/map → backend**.

Each approach has trade-offs in queuing, overhead, and durability. Avoid collecting **the same event** through both paths and ingesting it into the same index without provenance/deduplication. In the OpenTelemetry Log Data Model, source metadata belongs in **Resource**, event-specific fields belong in **Attributes**, and `TraceId`/`SpanId` are dedicated fields rather than arbitrary text strings.

**Practice:** an HTTP request creates an active span, calls a downstream stub, opens the trace from the dashboard, and finds the log matching `traceId` when the span is sampled/exported successfully.

## 11. Stage 7: Collector, Rotation, Retention, and Operations

A logging pipeline can have multiple layers:

~~~text
Java logger
  |
  v
Appender / Formatter / Encoder
  |
  +--> file (rotation + retention)
  |         or stdout/stderr
  v
Container runtime / shipper
  |
  v
Collector receiver
  |
  v
Processors: enrich / redact / filter / schema
  |
  v
Exporter queue, retry, transport
  |
  v
Storage, index, archive, dashboards
~~~

In the OpenTelemetry Collector, receivers ingest data, processors transform/filter data, and exporters send it to storage. **Merely declaring a processor in the config does not activate it**; you must include it in `service.pipelines.logs.processors`. Processor order and data sources affect the result, especially when adding/merging resource fields and performing redaction.

Points to learn and self-check:

- **Disk capacity:** free bytes, inodes, log growth rate, time-to-reserve, active vs. archived log files.
- **Rotation:** in Logback, `maxFileSize` does not cap the entire filesystem; `maxHistory`/`totalSizeCap` mainly manage archives by policy and do not replace SRE alerts.
- **Containers:** stdout can still consume host/ephemeral storage; understand Docker logging drivers and Kubernetes eviction.
- **Async appenders:** queues can block/drop when full; crashing before flush can lose buffered events.
- **Collector:** backlog, exporter errors, retries, duplicate ingestion, and missing metrics.
- **Retention:** application DEBUG logs can have short lifetimes; audit/security logs have their own policies and legal holds.
- **Billing:** bytes generated by the app, bytes ingested, and bytes stored/indexed are not necessarily equal.
- **Alerting:** you must know when the exporter is down or metrics are missing; do not treat "no data" as "no errors."

**Practice:** use a separate test environment with a small volume or intentionally pause the collector to observe queuing/drops and recovery. Do not try filling a production disk, deleting Docker-managed logs, or truncating active audit files to "test the limits."

## 12. Security and Privacy Are Not Optional

Effective logging can still introduce risk if the wrong information is stored. When upgrading to structured logging, apply:

- **Data minimization:** do not log passwords, tokens, JWTs, cookies, OTPs, private keys, connection strings, or full `Authorization` headers.
- **Input validation:** limit length/characters of `requestId` and client-influenced fields; prevent newlines/control characters from causing log injection.
- **Public vs. internal errors:** API responses should use error codes and safe messages; detailed stack traces belong only in authorized internal sinks.
- **Tenant isolation:** MDC `tenantRef` is for correlation, **not authorization**; verify the principal and enforce query permissions in the backend.
- **RBAC/retention:** define who can view raw logs, how long they are kept, access auditing, and backups according to policy.
- **Separate audit logs:** actor/action/outcome/time, integrity, retention, and legal hold where required—do not mix them with DEBUG rotation.
- **Testing:** inject fake token/PII markers into test inputs and check every sink, not just the console.

Do not use a simple hash to claim an ID is "anonymized" if it can be brute-forced or correlated over time. Collect only necessary IDs and consider pseudonymization aligned with your threat model.

## 13. Capstone Project: Observable Order API

A right-sized capstone to consolidate the stages above:

**Sample application:** an Order HTTP API, a Payment stub with timeouts, and a notification worker running via `ExecutorService`; using SLF4J/Logback or an equivalent backend, metrics, tracing, and a log pipeline. You do not need to build multiple real microservices.

~~~text
Client -> HTTP Filter / Authentication
                   |
                   +--> requestId, tenantRef, trace extract
                   |
                   v
             OrderService
                   |
                   +--> PaymentAdapter (simulated timeout)
                   |
                   +--> Async Notification Worker
                   |          |
                   |          +--> MDC/trace context propagation
                   v
        Outcome event + errorCode
                   |
             +-----+-----+
             |     |     |
             v     v     v
           Logs  Metrics Traces
             |     |     |
             +-----+-----+
                   |
                   v
              Collector / Backend
                   |
                   v
             Alert + Dashboard + Runbook
~~~

### Capstone Acceptance Criteria

| Item | Demonstrable Result |
| --- | --- |
| Logging backend | One intended provider, no duplicate appenders |
| Event taxonomy | Clear and stable `event`/`errorCode`/`outcome` |
| Context | Same `requestId` appears in controller, service, and worker where appropriate |
| Context cleanup | Request A → B → no-context leaks no MDC |
| Structured logging | Accurate JSON fields and duration/attempt types at the sink |
| Exceptions | A terminal failure is not logged-and-rethrown across multiple layers |
| Retries | Attempts have separate milestones; terminal failure metric counts accurately |
| Real tracing | Trace/span IDs come from instrumentation; spans can be opened when exported |
| Metrics | Rate, terminal error rate, duration, collector drops |
| Reliability | Alerts for queue/exporter/disk and defined behavior when sink fails |
| Security | No fake secret markers leaked to unauthorized sinks |
| Retention | Audit logs are not deleted by DEBUG log rotation config |
| Troubleshooting | From an alert, you can locate logs, traces, root cause, and runbook |
| Documentation | README explaining how to run, test, configure, limits, and cleanup |

Do not try to stand up Kafka, Kubernetes, and Grafana all at once just to make the exercise "have all the tech." Build a small **verifiable** pipeline first, then increase complexity to match the problem you are solving.

## 14. Four-Week Practice Plan (Suggested)

| Week | Content | Hands-on Exercise | Deliverable |
| --- | --- | --- | --- |
| **1** | API/provider, levels, exceptions, structured events | Migrate project to one logger backend; typed fields | Logging conventions and appender test |
| **2** | MDC, async, privacy | A/B/no-context in thread pool; redaction test | Propagation helper + cleanup test |
| **3** | Metrics + distributed tracing | Instrument HTTP/service/worker; error/latency dashboard | Metrics/traces linked with logs |
| **4** | Pipeline + production | Collector, rotation, queue failure, incident drill | End-to-end demo and runbook |

This is a reference schedule only: if the project handles sensitive data, **privacy and retention must be included from week one**, not left until the end. If you have limited time, turn each stage into a 1–2 session exercise; the criterion is that you have **run and tested it**, not merely read the docs.

**Effective learning workflow:** form a hypothesis ("`requestId` is lost on the worker"), write a reproducing test, fix it at the right boundary, verify the output, and record the lesson in the README. Avoid changing the appender, collector, and application code simultaneously before identifying where logs first disappear.

## 15. Choosing Your Next Specialization

After the capstone, choose based on your career and systems:

### Backend Java / Spring

Focus on servlet filters, exception handling (`@ControllerAdvice`), Spring Boot logging config, structured output, metrics, and tracing integration. **Deliverable:** failed requests return safe public errors, and operators can use IDs to trace back to logs and traces.

### Messaging / Distributed Systems

Study Kafka `topic/partition/offset`, RabbitMQ `message_id`/delivery tag, at-least-once delivery, retry/DLQ, transactional outbox, and idempotent consumers. **Deliverable:** redelivery causes no incorrect side effects, and logs distinguish logical messages from delivery attempts.

### SRE / Platform

Focus on Docker logs, Kubernetes ephemeral storage, collectors, Prometheus/Grafana, SLOs/error budgets, capacity, and incident response. **Deliverable:** alerts when logs are dropped or disk is filling up, and pipeline recovery in a test environment.

### Security / Compliance

Focus on audit schemas, tamper detection, immutable storage/WORM if required, RBAC, retention/legal hold, log injection, and privacy. **Deliverable:** audit events remain intact without printing secrets to diagnostic logs.

### Performance / JVM

Explore JFR, GC logs, heap/thread profiling, encoder/async appender benchmarks, queue backpressure, and tail latency. **Deliverable:** measure overhead under the same workload instead of assuming an async logger is always faster.

You do not need to become an expert in every track. Learn enough to recognize boundaries and pick a specialization aligned with your project goals.

## 16. Misconceptions to Avoid

| Misconception | Fact to Remember |
| --- | --- |
| "More logs always make debugging faster" | Right events + right context + reliable pipeline are what matter |
| "SLF4J is a file-writing backend" | SLF4J is an API/façade; it needs a proper provider |
| "MDC automatically follows every thread and message" | Requires capture/restore and context propagation at boundaries |
| "Having a traceId in text means you have tracing" | Requires an active span, propagation, and an exporter |
| "OpenTelemetry replaces SLF4J/Logback" | OTel provides bridges/collectors and usually complements existing logging |
| "JSON cannot leak tokens" | Structured logs only make data easier to parse; minimization is still required |
| "An exception must be logged at every catch" | Log-and-rethrow can produce multiple stack traces for one failure |
| "ERROR log count equals error rate" | Retries and duplicates skew counts; metrics should track terminal outcomes |
| "Logback rotation replaces audit retention" | Audits have separate retention policies and legal obligations |
| "Async loggers guarantee zero log loss" | Queue overflow, shutdown, or network failures can still drop logs |
| "An event in stdout and OTLP is two events" | It may be the same source ingested via two paths |
| "RequestId makes a good Prometheus label" | Dynamic IDs have high cardinality; use them only for querying logs/traces |
| "Unit testing a mock logger is enough" | You must test at the real backend/collector sink |

## 17. End-of-Lesson Self-Assessment Questions

1. Can you describe the path of a JUL `LogRecord` from `Logger` through `Handler` to the console and compare it with SLF4J/Logback?
2. A `Throwable` is logged in both the repository and the controller: how do you distinguish an anti-pattern from a meaningful retry event?
3. Why must `errorCode` not be used as a unique event ID or idempotency key?
4. If a user sends an arbitrary `X-Tenant-Id`, should you put it directly into MDC and use it for log query authorization?
5. When two requests run sequentially on one worker, what test proves MDC does not leak?
6. When enabling SLF4J 2.x `addKeyValue`, what must you verify so the JSON backend actually includes those fields?
7. Which metric counts **final failed operations** more accurately than counting stack traces?
8. A log has a `traceId` but the backend cannot find the trace: what possibilities should you check?
9. When the collector is down, where do you inspect queue depth, drops, and exporter errors?
10. Why do `maxHistory`/`totalSizeCap` not guarantee that every audit event is retained for its required period?
11. When Docker/Kubernetes stores stdout logs, does not using `FileAppender` mean no disk space is consumed?
12. How do you prove a fake token does not leak into the console, files, shipper, and backend?

You can use these answers as an **acceptance checklist** rather than memorizing them. For example, question 6: you must test the real encoder/provider/layout; question 8: sampling, export, propagation, and fake IDs are all possibilities to check; question 7: an operation outcome metric defined at the proper boundary.

## 18. Post-Summary Action Checklist

- [ ] Have a Java 17 project demonstrating log events, `Throwable` handling, and a terminal outcome in the right units.
- [ ] Have a logging conventions document covering API/backend, levels, error codes, and exception ownership.
- [ ] Have structured fields, stable data types, and a schema migration plan.
- [ ] Have MDC request scoping, `finally` cleanup, and an A/B/no-context propagation test.
- [ ] Have no redundant log-and-rethrow or unintended duplicate ingestion.
- [ ] Have metrics for rate, errors, latency, saturation, and logging pipeline health.
- [ ] Have real trace context (not fabricated trace IDs) and verify opening logs linked to spans.
- [ ] Have rotation, collector, disk/queue/drop alerts, and retention tailored to each log type.
- [ ] Have data minimization, redaction, RBAC, and privacy tests.
- [ ] Have a working capstone, instructional README, incident drill, and runbook.
- [ ] Have chosen your next specialization track based on gaps and real work.

**Conclusion:** After summarizing Java Core Logging, **the next learning step** is turning knowledge of loggers, MDC, and exceptions into an **observable, secure system with metrics/traces that is tested under failure conditions**. Progressing stage by stage with evidence from running programs, tests, and dashboards matters far more than adding many libraries at once.

### Official References

- Oracle Java SE 17 — [java.util.logging.Logger](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Logger.html), [LogRecord](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/LogRecord.html), [Handler](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Handler.html).
- SLF4J — [Manual: parameterized logging, fluent API, and MDC](https://www.slf4j.org/manual.html).
- Logback — [Architecture](https://logback.qos.ch/manual/architecture.html), [Mapped Diagnostic Context](https://logback.qos.ch/manual/mdc.html), [Rolling Appenders](https://logback.qos.ch/manual/appenders-rolling.html).
- Log4j 2 — [Manual](https://logging.apache.org/log4j/2.x/manual/index.html), [Thread Context](https://logging.apache.org/log4j/2.x/manual/thread-context.html).
- OpenTelemetry — [Java Instrumentation](https://opentelemetry.io/docs/languages/java/instrumentation/), [Context Propagation](https://opentelemetry.io/docs/concepts/context-propagation/), [Logs Data Model](https://opentelemetry.io/docs/specs/otel/logs/data-model/), [Collector Configuration](https://opentelemetry.io/docs/collector/configuration/).
- Prometheus — [Overview](https://prometheus.io/docs/introduction/overview/), [Instrumentation best practices](https://prometheus.io/docs/practices/instrumentation/).
- Micrometer — [Documentation](https://docs.micrometer.io/micrometer/reference/).
- OWASP — [Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html), [Error Handling Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Error_Handling_Cheat_Sheet.html).
- Docker — [Logging drivers](https://docs.docker.com/engine/logging/configure/); Kubernetes — [Local ephemeral storage](https://kubernetes.io/docs/concepts/storage/ephemeral-storage/).
