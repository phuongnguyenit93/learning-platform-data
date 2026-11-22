# Identifying Important Events in a Java Core Logging Strategy

## 1. What Is an Important Event?

An **important log event** is an action, state change, decision, or outcome that the team genuinely needs to **observe, investigate, reconcile, or prove**. Identifying these events is a logging strategy design step: before writing `logger.info()`, you must know **what is worth logging, why it is logged, who uses it, and how long it should be retained**.

Examples in an order service:

- `ORDER_CREATED`: the order has been created and the transaction has been confirmed complete.
- `ORDER_CREATION_REJECTED`: the request was rejected according to business rules or authorization.
- `REPORT_ACCESS_DENIED`: a principal was blocked from accessing a report.
- `DEPENDENCY_RECOVERED`: a dependent service had a transient error, but retry/fallback recovered it.
- `DEPENDENCY_UNAVAILABLE`: the request/job could not complete after trying the permitted options.
- `CONFIG_CHANGED`: a setting with operational or security impact was changed.
- `MESSAGE_DEAD_LETTERED`: a message was moved to quarantine according to the broker contract.

Conversely, `entered method findOrder()`, an internal comparison, or a normal cache miss may only warrant `DEBUG`/`TRACE` logging, aggregation into a metric, or no separate log at all.

**"Important" does not mean log level `ERROR`.** A successfully created order is highly significant but is typically `INFO`. A denied access attempt may be an audit/security event that needs to be retained, yet it is not necessarily a technical error. A failure that exhausts retries and causes HTTP to return 503 is what typically warrants `ERROR` or `SEVERE`.

An event is valuable when it helps answer: **What happened? When? Who/which component was involved? Which target was affected? What was the outcome? Where can it be traced?**

## 2. Categorize Before Deciding to Log

| Category | Examples | Purpose | Notes |
| --- | --- | --- | --- |
| Business | `ORDER_CREATED`, `REFUND_APPROVED` | Reconciliation, customer support, flow investigation | Logs do not replace the transaction ledger or source business data |
| Security/authentication | `LOGIN_DENIED`, `ROLE_GRANTED` | Detecting unauthorized behavior, decision history | May require a separate audit trail and integrity protection |
| Operations/availability | `DEPENDENCY_UNAVAILABLE`, `CIRCUIT_OPENED` | Incident investigation, determining blast radius | Combine with SLOs/metrics/traces |
| Data integrity | `RECONCILIATION_FAILED`, `DATA_CHECK_FAILED` | Detecting data discrepancies or corruption | Distinguish resolved errors from ongoing errors |
| System changes | `CONFIG_CHANGED`, `FEATURE_FLAG_UPDATED` | Tracing changes prior to an incident | Log version/actor; avoid secret values |
| Job/message lifecycle | `JOB_COMPLETED`, `MESSAGE_DEAD_LETTERED` | Tracking batch jobs and consumers | Keep job/message ID and outcome |
| Detailed diagnostics | `cache miss`, `starting method` | Code analysis during debugging | Can use sampling and short retention |

An event type can belong to two categories. `ROLE_GRANTED` is both an administrative operation and requires auditing. However, you should not take an `INFO` entry in application logs and assume it is a reliable audit record: auditing typically has its own requirements for completeness, integrity, access control, retention period, and verifiability.

A **business event** that other systems need to consume (for example, `OrderCreated` via a message broker) is also different from a **log event** for observability. If guaranteed delivery of business events is needed, you must use a transactional/outbox/broker mechanism by design rather than merely calling a logger.

## 3. Ask Impact-Based Questions, Not Method-Count Questions

Before adding an event to the logging catalog, ask:

1. If it occurs, **who will look it up** and in what situation?
2. Does it change money, access permissions, data state, configuration, or availability?
3. Does it help determine the final outcome or a key decision that aggregated metrics alone cannot explain?
4. If omitted, would reconstructing the sequence of actions after an incident be significantly harder?
5. Are there internal requirements or applicable obligations regarding action history?
6. Can a request/job/message/trace ID be attached to locate the exact event?
7. Can it be logged using a **minimal schema** without exposing raw payloads or secrets?
8. Is the event frequency low enough, or is there an appropriate volume/sampling policy?

If there is no clear use case, check whether a **metric** such as `http_requests_total` or a trace span is already sufficient. "Logging everything" often buries important logs under millions of low-value lines.

### Illustrative Priority Matrix

| Event | Risk/Impact Level | Frequency | Suggested Policy |
| --- | --- | --- | --- |
| Administrative role change | Very high | Low | Audit event with actor/target/outcome, reliability protection |
| Confirmed financial transaction | Very high | Medium | Source of truth is the transaction ledger; log minimal correlation IDs |
| Final request returns 503 | High for availability | Spikes during incidents | Structured terminal error, rate metric, impact-based alert |
| Dependency retry that recovers | Medium | Can be high | Retry metric and recovered event when useful |
| Normal cache lookup miss | Low | Very high | Metric/sampling/`DEBUG`, not `INFO` every time |
| Invalid input returning 400 per policy | Usually low | High | Access log or categorized event, avoid `ERROR` by default |
| Mass login denied | Notable security signal | Can be very high | Security telemetry, rate alert, avoid exposing accounts/raw requests |

This is only a **design prioritization approach**, not a fixed scoring scale. Specific company, product, industry, or data requirements may mean the same event needs different retention handling.

## 4. Distinguish Attempt, Decision, Success, and Failure

Before naming an event or choosing its level, determine **what the event is describing**:

- **Attempt:** the system *is trying* to perform an action, not yet guaranteed to succeed.
- **Decision:** authorization/business rules allowed or denied it.
- **Committed success:** the business state change has been completed according to the contract.
- **Terminal failure:** retries/fallbacks are exhausted and the final outcome is still failure.
- **Recovered:** a transient error occurred, but the system recovered.
- **Unknown/ambiguous:** the outcome is undetermined, e.g., a timeout after sending a request with side effects.

A simple flow:

~~~text
Create order request
        |
        v
 Validate + authorize ----- DENIED -> ORDER_CREATION_REJECTED
        |
        v
 DB transaction
        |
      commit
      /    \
   FAILED  SUCCESS
      |        |
      v        v
 ORDER_CREATION_FAILED   ORDER_CREATED
~~~

**Do not log `ORDER_CREATED SUCCESS` before commit** if the DB can still roll back. At the same time, logging an attempt or DENIED when policy requires it is still valuable even without a successful transaction.

If application logs are emitted only **after** commit, there is still a failure window: the DB commit succeeds, but the JVM crashes before the logger/exporter writes the event. When an event truly must be preserved together with the business change, one mechanism to consider is a **transactional outbox** in the same database transaction: persist the business state and an outbox event record in one commit, then have a worker dispatch it.

~~~text
Transaction in database:
   update business row
   insert outbox event (eventId stable)
          |
        COMMIT
          |
     Outbox worker
          |
  send + retry / ACK
          |
     Destination store
~~~

An outbox reduces the risk of losing information if a crash occurs between commit and event emission, but it **does not automatically provide exactly-once** delivery at the final destination. The worker may send successfully and crash before updating the sent status; a stable event ID, receiver-side idempotency/dedup, and reconciliation are needed. An outbox also does not automatically provide an immutable audit store; if auditing is required, integrity, permissions, and retention must be designed separately.

### Retries and Final Outcome

A dependency times out on attempt 1 and recovers on attempt 2. If the lower layer emits `ORDER_CREATION_FAILED` on the first attempt, the system may falsely report an error even though the final outcome succeeded. The retry coordinator can log `DEPENDENCY_RETRY_SCHEDULED`, and finally the boundary logs `ORDER_CREATED` or `DEPENDENCY_RECOVERED` depending on the purpose. **An exception does not equal a terminal failure.**

Conversely, a timeout after a request has been sent to an external system may leave the state **unknown**. Do not guess FAILED; check status, idempotency, or reconciliation.

## 5. Naming and Standardizing the Taxonomy

Event names should reflect **what happened** and remain stable:

~~~text
ORDER_CREATED
ORDER_CREATION_REJECTED
ORDER_CREATION_FAILED
REPORT_ACCESS_DENIED
ROLE_GRANTED
ROLE_REVOKED
DEPENDENCY_RECOVERED
DEPENDENCY_UNAVAILABLE
CONFIG_CHANGED
JOB_COMPLETED
MESSAGE_DEAD_LETTERED
~~~

Avoid multiple variants for the same meaning such as `create_order_success`, `OrderSuccessfullyCreated`, and `order.done` if they serve the same contract. Use an enum or event catalog to stay consistent.

**Do not embed dynamic IDs in event names:** avoid `ORDER_CREATED_42`; instead use `eventCode=ORDER_CREATED` and `targetId=order-42`. When event names are used in metrics/dimensions, arbitrary IDs cause high cardinality; when you need to find a specific event, IDs belong in a controlled log field.

A good event definition should specify: code, meaning, emission condition, owner, level, outcome, schema, sensitive fields, sink, retention, consumers, and testing plan. When renaming an event or changing a field type, treat it as a **contract change** that can break existing dashboards, alerts, and queries.

## 6. Minimal Schema for Important Events

Fields can be specified depending on context:

| Field | Type | Meaning |
| --- | --- | --- |
| `timestamp` | UTC ISO-8601 string | Time of occurrence/logging as defined |
| `schemaVersion` | integer/string | Contract version |
| `eventCode` | stable enum/string | Event type |
| `outcome` | enum | SUCCESS, DENIED, FAILED, RECOVERED, UNKNOWN |
| `level` | string | Operational severity level of the backend |
| `service`, `component` | string | Emission source |
| `requestId`, `traceId` | string | Correlates requests across services |
| `eventId` | unique ID when needed | Dedup, audit, or replay |
| `actorType`, `actorId` | enum/ID | Acting principal |
| `targetType`, `targetId` | enum/ID | Affected target |
| `reasonCode` | enum/string | Standardized reason, not a raw exception |
| `attempt`, `retryPolicyVersion` | integer/string | For retry events if applicable |

**Not every event has a human user.** A job runner may have `actorType=SERVICE`; an event in a scheduled job may use `jobId` instead of an HTTP request ID. Do not fabricate fake actors or request IDs just because the schema has optional fields.

Example JSON log of a decision:

~~~json
{
  "timestamp": "2026-01-15T10:00:00Z",
  "schemaVersion": 1,
  "service": "reports-api",
  "eventCode": "REPORT_ACCESS_DENIED",
  "outcome": "DENIED",
  "level": "INFO",
  "actorType": "USER",
  "actorId": "user-demo-1",
  "targetType": "REPORT",
  "targetId": "report-7",
  "requestId": "req-102",
  "reasonCode": "POLICY_DENIED"
}
~~~

This is only a sample schema. The IDs in this article are dummy data; in practice, actor/target/request IDs **can still be linkable personal data** and require access and retention policies. Do not put authentication tokens or cookies into `requestId`.

Log only fields on an allowlist. Doing `logger.info("request=" + dto.toString())` or printing raw bodies easily leaks passwords, personal data, tokens, and payment details. **JSON escaping is not redaction.**

## 7. Severity Based on Outcome, Not Mere Importance

| Event/Outcome | Typical JUL Level to Consider | Reason |
| --- | --- | --- |
| Successful `ORDER_CREATED` | `INFO` | Worth recording, but no error occurred |
| `REPORT_ACCESS_DENIED` per policy | `INFO` + security/audit policy | A denial does not mean the system is broken |
| `DEPENDENCY_RECOVERED` after fallback | `WARNING` if degradation needs tracking | Recovered, but carries an operational signal |
| Terminal `DEPENDENCY_UNAVAILABLE` | `SEVERE` | Request/job could not recover |
| Routine 400 validation | `FINE`/`INFO` or access log | Do not trigger an incident for every invalid input |
| Debug info for a code branch | `FINE`/`FINER` | Diagnostic value, not a primary outcome |
| Administrative permission change | Separate audit policy | Do not rely solely on an `INFO` appender that may be filtered |

**JUL does not have `Level.ERROR`;** many logging backends like SLF4J/Logback/Log4j 2 have `ERROR`/`WARN`. When learning and implementing, use the right API and level mapping. Do not choose `SEVERE` for every exception that was successfully retried or for expected 403 responses.

On the other hand, **an important event does not automatically trigger an alert**. A single `ORDER_CREATED` usually should not page on-call; an elevated rate of `DEPENDENCY_UNAVAILABLE` can trigger an SLO/burn-rate alert. Special security incidents may require alerting on a single event, but must have a policy and mechanisms to reduce false positives.

## 8. Standalone Java 17 Example: Emitting the Right Event Types

The program uses **JDK 17 and `java.util.logging`**, requiring no Maven or external dependencies. It simulates four already-determined outcomes:

1. Order created successfully.
2. Report read permission denied.
3. Dependency timed out but recovered.
4. Dependency ultimately unavailable.

The code uses **enums** for event/outcome/reason, a record for data, and a custom logger handler for deterministic output. It emits logs **only after being given the simulated outcome**, without actually opening a DB, HTTP server, checking permissions, or performing retries. In production, it must be called from the component that owns the **actual outcome**.

Create **`ImportantEventLoggingDemo.java`**:

~~~java
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.Objects;
import java.util.logging.Formatter;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class ImportantEventLoggingDemo {
    enum EventCode {
        ORDER_CREATED, REPORT_ACCESS_DENIED,
        DEPENDENCY_RECOVERED, DEPENDENCY_UNAVAILABLE
    }

    enum Outcome { SUCCESS, DENIED, RECOVERED, FAILED }
    enum ActorType { USER, SERVICE }
    enum TargetType { ORDER, REPORT, DEPENDENCY }
    enum Reason {
        NONE, POLICY_DENIED, TEMP_TIMEOUT, RETRY_EXHAUSTED
    }

    record Event(
            Instant occurredAt,
            EventCode code,
            Outcome outcome,
            String requestId,
            ActorType actor,
            TargetType targetType,
            String targetId,
            Reason reason) {}

    private static String id(String field, String value) {
        if (value == null ||
                !value.matches("[A-Za-z0-9._-]{1,64}")) {
            throw new IllegalArgumentException(
                    "Invalid identifier: " + field);
        }
        return value;
    }

    private static void emit(
            Logger logger, Level level, Event e) {
        String payload =
                "at=" + Objects.requireNonNull(e.occurredAt())
                + " event=" + Objects.requireNonNull(e.code())
                + " outcome=" + Objects.requireNonNull(e.outcome())
                + " request=" + id("request", e.requestId())
                + " actor=" + Objects.requireNonNull(e.actor())
                + " targetType=" + Objects.requireNonNull(e.targetType())
                + " target=" + id("target", e.targetId())
                + " reason=" + Objects.requireNonNull(e.reason());
        logger.log(level, payload);
    }

    private static Logger createLogger() {
        Logger logger = Logger.getLogger("demo.important.events");
        logger.setUseParentHandlers(false);
        logger.setLevel(Level.ALL);

        Handler handler = new Handler() {
            @Override
            public void publish(LogRecord record) {
                if (isLoggable(record)) {
                    System.out.print(getFormatter().format(record));
                }
            }
            @Override
            public void flush() {
                System.out.flush();
            }
            @Override
            public void close() {
                flush();
            }
        };
        handler.setLevel(Level.ALL);
        handler.setFormatter(new Formatter() {
            @Override
            public String format(LogRecord record) {
                return record.getLevel().getName() + ": "
                        + formatMessage(record)
                        + System.lineSeparator();
            }
        });
        logger.addHandler(handler);
        return logger;
    }

    public static void main(String[] args) {
        Clock clock = Clock.fixed(
                Instant.parse("2026-01-15T10:00:00Z"),
                ZoneOffset.UTC);
        Instant when = Instant.now(clock);
        Logger logger = createLogger();

        try {
            emit(logger, Level.INFO, new Event(
                    when, EventCode.ORDER_CREATED,
                    Outcome.SUCCESS, "req-101",
                    ActorType.USER, TargetType.ORDER,
                    "order-42", Reason.NONE));

            emit(logger, Level.INFO, new Event(
                    when, EventCode.REPORT_ACCESS_DENIED,
                    Outcome.DENIED, "req-102",
                    ActorType.USER, TargetType.REPORT,
                    "report-7", Reason.POLICY_DENIED));

            emit(logger, Level.WARNING, new Event(
                    when, EventCode.DEPENDENCY_RECOVERED,
                    Outcome.RECOVERED, "req-103",
                    ActorType.SERVICE, TargetType.DEPENDENCY,
                    "stock-api", Reason.TEMP_TIMEOUT));

            emit(logger, Level.SEVERE, new Event(
                    when, EventCode.DEPENDENCY_UNAVAILABLE,
                    Outcome.FAILED, "req-104",
                    ActorType.SERVICE, TargetType.DEPENDENCY,
                    "stock-api", Reason.RETRY_EXHAUSTED));
        } finally {
            for (Handler h : logger.getHandlers()) {
                logger.removeHandler(h);
                h.close();
            }
        }
    }
}
~~~

Run with JDK 17 or later:

~~~bash
javac ImportantEventLoggingDemo.java
java ImportantEventLoggingDemo
~~~

**Exact stdout** on a successful run:

~~~text
INFO: at=2026-01-15T10:00:00Z event=ORDER_CREATED outcome=SUCCESS request=req-101 actor=USER targetType=ORDER target=order-42 reason=NONE
INFO: at=2026-01-15T10:00:00Z event=REPORT_ACCESS_DENIED outcome=DENIED request=req-102 actor=USER targetType=REPORT target=report-7 reason=POLICY_DENIED
WARNING: at=2026-01-15T10:00:00Z event=DEPENDENCY_RECOVERED outcome=RECOVERED request=req-103 actor=SERVICE targetType=DEPENDENCY target=stock-api reason=TEMP_TIMEOUT
SEVERE: at=2026-01-15T10:00:00Z event=DEPENDENCY_UNAVAILABLE outcome=FAILED request=req-104 actor=SERVICE targetType=DEPENDENCY target=stock-api reason=RETRY_EXHAUSTED
~~~

**Stderr:** empty on success. The parent logger is disabled to avoid duplicate output; the demo handler prints to `System.out`. JUL's standard `ConsoleHandler` normally prints to stderr, but it is **not used in this example**.

### Why Is the Example Designed This Way?

- `EventCode`, `Outcome`, `ActorType`, `TargetType`, and `Reason` are enums: this reduces the risk of multiple inconsistent terms for the same event.
- `Clock.fixed` is solely for reproducible test output. In production, use a meaningful timestamp per schema with synchronized clocks; client-supplied timestamps are not trustworthy by default.
- `id()` constrains demo IDs and blocks newlines, reducing log injection. It does not prove an ID is non-personal data and is not a multilingual ID parser.
- `emit()` logs only selected metadata, without dumping `Exception.getMessage()` or the request body.
- `ORDER_CREATED` is very important yet `INFO`, whereas `DEPENDENCY_UNAVAILABLE` affects availability so it is `SEVERE`.
- `REPORT_ACCESS_DENIED` only reflects an assumed **decision**, without actually performing authorization checks. If auditing is mandatory, a separate storage path with durability and appropriate policies is required.
- Handlers are removed and closed in `finally`. This example is **diagnostic logging**; it has no collector, persistent queue, outbox, JSON encoder, or durability guarantees.

## 9. Choose the Layer Responsible for Emitting Events

A reliable event should be logged at the layer that **knows the true outcome** and has sufficient context:

| Event | Layer That Typically Owns It | What Must Be Known |
| --- | --- | --- |
| `ORDER_CREATED` | Service after commit/outbox in the same transaction | The change truly succeeded |
| `REPORT_ACCESS_DENIED` | Authorization middleware/boundary | The deny decision and reason code |
| `DEPENDENCY_RECOVERED` | Retry coordinator or fallback service | Number of attempts and final outcome |
| `DEPENDENCY_UNAVAILABLE` | Request/job error boundary | No longer recoverable, request/job impacted |
| `JOB_COMPLETED` | Scheduler/job runner | Job ID, item count, duration, status |
| `MESSAGE_DEAD_LETTERED` | Consumer recovery layer | DLQ handoff confirmed per broker contract |
| `CONFIG_CHANGED` | Configuration/admin service | Actor, config version, action outcome |

A repository may catch `SQLException`, but it does not yet know whether the request will be retried successfully. If you only wrap and rethrow, you should usually **preserve the cause and avoid logging the same stack trace at every layer**. The final boundary logs the terminal event. A service can still log an independent event such as `CIRCUIT_OPENED` or `FALLBACK_ACTIVATED` if it genuinely occurs.

**"Log once" does not mean a request has only one log line.** You can have `ORDER_CREATED`, `CACHE_FALLBACK_ACTIVATED`, and an HTTP completion event because they describe different events; what to avoid is multiple duplicate error lines from the same exception.

## 10. Sampling, Volume, SLOs, and Investigability

Do not retain all logs under a single sampling policy:

| Type | Policy Typically Considered |
| --- | --- |
| Detailed per-branch debug | Enabled temporarily, sampled, or in test environments |
| HTTP 200 at high QPS | Metrics, trace sampling, or structured access logs as needed |
| Terminal failures affecting SLOs | Prioritize events with enough detail to investigate; alert on rate and impact |
| Mandatory security/audit | Do not sample arbitrarily if completeness is required |
| Critical permission/config changes | Retain evidence per security/audit policy |
| Rare but high-consequence events | Typically require full collection and semantic alerting |

**Sampling can drop the exact rare event you need most to investigate.** Choose policies by `eventCode`, source type, impact, and retention. If logs spike during a dependency failure, you can rate-limit repetitive diagnostic logs or aggregate counts while still tracking terminal failures and drop-count metrics.

An event emitted to a logger is not guaranteed to be stored at the collector. An async queue can fill up, transport can fail, or files can be rotated/deleted before the shipper reads them. For events that must be preserved, specify durable storage, ACK, retry, queue/backpressure, retention, and failure handling; **do not rely solely on the `INFO` level**.

### Complementary Metrics, Traces, and Alerts

~~~text
Log:
event=DEPENDENCY_UNAVAILABLE
requestId=req-104 reasonCode=RETRY_EXHAUSTED

Metric:
dependency_failures_total{dependency="stock-api",reason="timeout"} += 1

Trace:
HTTP span -> stock-api span (error, duration, traceId)
~~~

This is an **illustrative example**, not Java program output. Metrics should not use user ID, request ID, or order ID as labels because of very high cardinality. Alert on SLO/error rates and events that genuinely require investigation; **do not page on-call for individual `INFO` logs**.

## 11. Security and Personal Data in Important Events

A log containing actor ID, target ID, IP, trace ID, and timestamp can still be linked to a user. Importance does not mean "log as much as possible."

**Do not log by default:**

- Passwords, access/refresh tokens, OTPs, cookies, secret keys.
- Entire HTTP request/response bodies or DTO `toString()` output.
- Raw SQL/exception messages that may contain parameters, URLs, or PII.
- Account numbers/payment details, identity documents, or unnecessary sensitive data.
- Free-form user input in event names, metric labels, or unescaped text logs.

Keep only fields on an **allowlist**. If actor/target IDs are needed for auditing, define appropriate read permissions, encryption, retention, and deletion policies. Fixed email hashing or ID tokenization does not automatically make data anonymous if it can still be linked or reversed.

For text logs, validate untrusted fields to prevent newline/log injection. For JSON logs, use a standard serializer; it handles escaping and data types, but **does not automatically redact**. Place dummy sentinel data in unit/integration tests to verify secrets do not leak to files, stdout, or collectors.

## 12. Event Catalog — A Shared Contract Across Teams

An event catalog helps teams align on codes, emitters, and usage:

| Event | Trigger | Owner | Outcome | Sink/Consumer |
| --- | --- | --- | --- | --- |
| `ORDER_CREATED` | DB commit confirmed | Order service | SUCCESS | Business/operations log |
| `REPORT_ACCESS_DENIED` | Authorization returns DENY | Security boundary | DENIED | Security/audit policy |
| `DEPENDENCY_RECOVERED` | Retry/fallback completes | Retry coordinator | RECOVERED | Operations + metrics |
| `DEPENDENCY_UNAVAILABLE` | Retries exhausted, request/job fails | Error boundary | FAILED | Error log/rate-based alert |
| `CONFIG_CHANGED` | Config update confirmed | Admin service | Per contract | Audit/change log |
| `JOB_COMPLETED` | Job finishes | Job runner | SUCCESS/FAILED | Operations |
| `MESSAGE_DEAD_LETTERED` | DLQ handoff confirmed | Message consumer | DEAD_LETTERED | Messaging operations |

A definition can include:

1. **Meaning, scope, and emission condition** (attempt vs. committed outcome).
2. **Owner** maintaining the schema and handling alerts.
3. **Required fields**, data types, nullability, sensitive data.
4. **Severity, retention, and routing** to appropriate channels.
5. **Expected volume** and cardinality/sampling controls.
6. **Guarantee**: best-effort or mandatory persistence; behavior on write failure.
7. **Consumers**: dashboards, alerts, support, audit, or investigation.
8. **Schema version, migration, and contract tests**.
9. **Runbook** for anomalies and how to look up requests/jobs/events.

Changing `eventCode` or changing `status` from a number to a string can break dashboards even if the log still parses. Treat the logging schema as a contract with downstream consumers.

## 13. Testing Event Content and Pipelines

### 13.1. Producer Unit Tests

- `ORDER_CREATED` appears only when commit actually succeeds, not after rollback.
- Access denied produces the right `REPORT_ACCESS_DENIED` and reason code without leaking sensitive input.
- A successful retry does not produce a false terminal failure; a true retry failure produces `DEPENDENCY_UNAVAILABLE`.
- Event codes are chosen from the standard catalog, not from arbitrary user input.
- Outcome, actor/target, reason code, request ID, and timestamp match semantics.
- Do not emit duplicate terminal events from multiple `catch` blocks that log and rethrow.

### 13.2. Logger/Backend Integration Tests

- Capture `LogRecord` via a test JUL `Handler` or a real backend appender.
- Verify levels/filters/parent handlers do not drop or duplicate events.
- For JSON logging, parse JSON/NDJSON with a library instead of only matching raw strings.
- For MDC/ThreadContext, ensure context is cleared in `finally` and does not leak across requests.
- For async logging, wait for flush/drain or await with a timeout; do not use arbitrary `Thread.sleep` as a guarantee.
- Check sensitive fields using dummy sentinel data across sinks.

### 13.3. Fault Injection / End-to-End

- Collector down, queue full, spool file error, disk full: the application responds per policy, with drop metrics and alerts.
- Transport retry after ACK timeout: duplicates may occur; verify stable event ID/dedup.
- With an outbox: crash between commit–publish and publish–ACK; verify recoverability.
- Audit: verify permissions, integrity, retention, and queries by actor/event ID if required.
- Schema version upgrade or field change: old/new consumers can read per contract.
- Reconcile events by operation ID; distinguish **attempt** count from terminal outcome count.

**A mock `logger.info()` call only proves the code called the logger.** It does not prove the event arrived or was durably stored at the destination system.

## 14. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Logging every method at `INFO` | Log noise and high cost | Define meaningful events; debug intentionally |
| Every exception at `SEVERE` | Successful retries counted as incidents | Base severity on final outcome |
| Logging success before commit | Wrong log when rolled back | Emit after commit or use outbox as required |
| Ignoring all DENIED events | Blocked actions are invisible | Policy-backed security/audit events |
| Event names containing request/user ID | Uncontrolled cardinality | Fixed event code, IDs as fields |
| Every layer logs the same exception | Duplicate stack traces and alerts | Boundary ownership, preserve cause |
| Dumping DTOs/exceptions/raw payloads | Leaks personal data and secrets | Allowlist, redaction, testing |
| Sampling all types identically | Drops critical security events | Sample by category/contract |
| Logs only, no metrics/traces | Hard to spot trends and blast radius | Combine appropriate signals |
| Assuming logger not throwing means audit saved | Backend may drop or fail to write | ACK, durable queue, integrity, retention |
| Changing fields without versioning | Breaks dashboards and parsers | Event catalog + contract tests |

## 15. Logging Design Checklist

- [ ] Know the purpose and consumer of each event.
- [ ] Select actions/decisions/changes/conditions that affect business, security, or operations.
- [ ] Distinguish attempt, decision, committed success, recovered, failed, and unknown.
- [ ] Lock in a stable event taxonomy and versioned schema.
- [ ] Identify the layer owning the outcome and emit after the appropriate commit/ack.
- [ ] Consider an outbox/separate durability for events that must not be lost.
- [ ] Choose severity by impact, not merely because an exception occurred.
- [ ] Use correlation/event IDs sensibly; avoid high-cardinality metrics.
- [ ] Minimize data; do not log secrets or raw payloads.
- [ ] Configure sampling, retention, routing, and read permissions by category.
- [ ] Combine logs, metrics, traces, and audits according to purpose.
- [ ] Test schema, event counts, outcomes, privacy, and pipelines as needed.

### Self-Check

**Q1.** Why is `ORDER_CREATED` important yet usually `INFO`?  
**A:** Because it is a successful outcome, not an operational error. Importance and severity are two different axes.

**Q2.** A request times out on the first try but succeeds on retry: was there a terminal failure?  
**A:** No. A retry event/metric can be logged, but the terminal outcome is success or recovered per contract.

**Q3.** What is the risk of logging `ORDER_CREATED SUCCESS` before DB commit?  
**A:** A transaction rollback causes the log to state the wrong real-world state. Log at the confirmation point or use an outbox when preservation is required.

**Q4.** Can a security denial be important even when HTTP 403 is expected?  
**A:** Yes. It may require an audit record per policy without turning every 403 into `SEVERE`.

**Q5.** Does calling `logger.info("ROLE_GRANTED")` prove an immutable audit log exists?  
**A:** No. You must ensure outcome source, delivery, integrity, read permissions, and retention.

**Q6.** Why shouldn't order IDs be placed in event names or metric labels?  
**A:** It creates very high cardinality, makes aggregation difficult, and increases data exposure risk; put IDs in controlled log fields instead.

**Q7.** When changing an event code or field type, what needs to be done?  
**A:** Update the schema/version, dashboards, alerts, consumers, and contract tests.

**Remember:** Identifying important events is **designing an observability contract**, not adding logs everywhere. Choose events with clear consumers and purposes, accurately reflect the outcome, emit at the right boundary, use stable names/schemas, and control privacy and retention. Only then will Java logging truly support production investigation and operations.
