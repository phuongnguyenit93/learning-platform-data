# Defining Logging Objectives in Java: Designing a Logging Strategy from Real-World Needs

## 1. Why Define Objectives Before Writing Logs?

In Java, calling `logger.info(...)` is easy. However, having more logs **does not mean a system is easier to operate**. When an error occurs in production, millions of lines like `"starting..."`, `"processing..."`, or `"something failed"` do not help answer key questions: which users are affected, where the error originated, whether intervention is needed, how many requests are repeating the error, and whether a fix has taken effect.

**Defining logging objectives** is the first step in **designing a logging strategy**: clarifying **why** a type of event needs to be recorded, **who** uses that data, **which decisions or actions** will depend on it, and **what verification signals** prove the data is sufficient, accurate, and safe.

An objective should not be written vaguely like:

> “Log as much information as possible for debugging.”

A better, verifiable objective is:

> “When a payment fails due to an external system, on-call can find `event=payment.failed`, identify the standardized error type, the affected route/service/version, correlate with the trace to investigate, and determine whether a retry is needed; logs must not contain payment card details or access tokens.”

For a Java Core Logging system, the strategy must connect objectives with **events**, **log levels**, **schemas**, **emission points**, **transport channels**, **access permissions**, **retention**, and **testing**. Do not start by picking a Logback appender or enabling system-wide DEBUG and only later asking what the logs are used for.

### 1.1. Expected Outputs of Defining Objectives

After this step, the team should have at least:
- A list of **scenarios to observe** and the questions that must be answered.
- Log consumers and those responsible for **taking action when an event occurs**.
- **Event catalog**: standard event names, emission conditions, and meanings.
- **Field allowlist** along with data classification rules; no logging of secrets.
- Rules for **severity, frequency, sampling**, and event emission locations.
- A clear distinction between **application logs**, **metrics**, **traces**, and **audit records**.
- **QA/acceptance criteria**: where events can be found, within what time window, with the right count, proper structure, no data leaks, and without degrading performance.

Not every project needs a lengthy document; a small service can use a one-page event table. What matters is that decisions are documented **before logs spread across multiple layers** and are updated as business logic or risks evolve.

## 2. Categorizing Objectives: Not All Logs Serve the Same Purpose

| Objective Category | Questions to Answer | Example Events | Target Audience |
| --- | --- | --- | --- |
| **Operations** | Is the service running, which dependency is failing? | `service.started`, `dependency.unavailable` | On-call, SRE |
| **Error Investigation** | Which request failed, at which step, what error type? | `order.create_failed` | Developers, technical support |
| **Security** | Was access denied or was there sensitive behavior? | `auth.denied`, `permission.changed` | Security, SOC |
| **Business Audit** | Who performed a critical change, was the outcome committed? | `payment.refunded`, `role.granted` | Audit, compliance, business |
| **Performance** | Which endpoint/dependency is slow? | `repository.slow_operation` | SRE, performance engineers |
| **Business Flow Tracking** | Which states has an order passed through? | `order.accepted`, `order.cancelled` | Product/operations |
| **Change Management** | Who changed configuration, which release caused impact? | `logging.config_changed`, `release.deployed` | Platform, on-call |
| **Integration Quality** | Did a provider return an invalid schema or time out? | `partner.response_invalid` | Integration team |

Categories may overlap, but they **should not be lumped into a single mechanism**. For example, an application INFO log about `"order created"` does not automatically replace an audit trail that requires durability, chronological ordering, access controls, and integrity guarantees.

The OWASP Logging Cheat Sheet distinguishes between operational, security, audit, and monitoring objectives; the level of detail must be proportionate to the risk and purpose. There is no single fixed checklist that fits every type of system.

### 2.1. Operations: Knowing When to React

A good operational objective is not just “log DB errors”, but rather:

- When a dependency is unavailable, know the `dependency`, `operation`, `error_type`, and `trace_id`.
- Distinguish a widespread outage from an isolated request using **metrics** for error rate, timeouts, and pool saturation.
- Have a runbook specifying who receives the alert and the first action to take.

Example:

```text
ERROR event=dependency.unavailable service=orders
      dependency=inventory-api operation=reserve
      error_type=CONNECT_TIMEOUT request_id=req-104
```

There is no need to print the full URL containing tokens, HTTP Authorization headers, or sensitive response bodies. This event should have a **clear definition**: after how long a timeout occurs, which layer emits the event, and whether it is logged repeatedly for each retry.

### 2.2. Error Investigation: Finding Root Causes Without Log Flooding

An error can propagate from the repository to the service layer and up to the HTTP handler. If all three log a stack trace, a single failure produces three ERROR records without adding context. A useful rule is:
- Lower layers **throw/translate exceptions** and may add specific diagnostics if genuinely valuable.
- The layer owning the final outcome (HTTP boundary, message consumer, scheduler) records **a single summary event** with the error type and correlation ID.
- Traces/spans and metrics assist in root-cause analysis without requiring every method to print INFO logs.

### 2.3. Security: Which Behaviors Must Be Observed?

Events that typically need evaluation:
- Authentication successes/failures according to the threat model; focus on failures and anomalous patterns.
- Authorization denials and privilege changes.
- Credential creation/revocation and security configuration changes.
- Use of administrative or controlled “break-glass” functions.
- Access/export of sensitive data according to policy.
- Input validation failures, business-flow abuse, and rate-limit abuse.

**Do not log passwords, OTPs, access tokens, refresh tokens, session cookies, private keys, or API secrets.** Security events can remain critical even when application log levels are lowered; the strategy must specify channels or event classes that must never be arbitrarily disabled.

### 2.4. Audit: Committed Business Outcome or Merely Intent?

`orderRepository.save(order)` returning **does not guarantee the transaction has committed**. If an audit must prove that a change occurred, an INFO line before commit is insufficient. You may need an audit store or transactional outbox persisted within the same transaction, combined with identity/authorization, retention, and integrity controls.

Therefore, the objective must clearly define:

- Record the **attempt** or the **committed outcome**?
- Is it necessary to trace the actor and permissions at the time of the operation?
- Who is authorized to read/modify/export the data?
- What levels of durability, retention, and legal compliance are required?
- Must the data survive if the JVM crashes and the log exporter is down?

Do not assign a “zero-loss” requirement to an in-memory AsyncAppender that is only meant for best-effort observability.

## 3. Start with Questions and Actions, Not Log Levels

A good objective statement template:

```text
When [SCENARIO] occurs,
[WHO] needs to answer [QUESTION]
to decide [ACTION]
using [EVENT/FIELDS/METRIC/TRACE].
The objective is met when [VERIFICATION CRITERIA]
within approved [SECURITY/COST/TIME] bounds.
```

Example for a payment service:

| Scenario | Question | Action | Signal | Acceptance |
| --- | --- | --- | --- | --- |
| Provider timeout | Is it a widespread impact? | Enable fallback/circuit breaker per runbook | Error-rate metric + `payment.provider_timeout` log + trace | Event, provider alias, timeout category, and trace can be found |
| Payment conflict | Did the customer retry a duplicate transaction? | Enforce idempotency, return appropriate result | `payment.duplicate_request` + audit outcome | No secrets/PII and no duplicate payment created |
| Login denied | Mistyped password or abuse pattern? | Investigate / apply conditional rate limit | `auth.denied` + count by safe grouping | Event includes reason enum, no password logged |
| New deploy | Which version started failing? | Roll back release if needed | `service.started`, release/version metrics | Can correlate version with error spike period |
| Slow query | DB pool wait or slow SQL execution? | Tune pool/query without guessing | Timer histogram + trace + slow log | Distinguishes pool wait from SQL duration |
| Service recovery | Did the fix take effect? | Close the incident | Error rate, p95, recovery log | SLO/metrics return to baseline over the measurement window |

**Every objective should be tied to a consumer and a decision.** If nobody will read a log type, no dashboard/search/runbook depends on it, and there is no retention obligation, reconsider whether the event should be emitted in production at all.

### 3.1. Three Questions to Test Whether an Objective Is Specific Enough

1. **Without this event, what decision-making capability do we lose?**
2. **With this event, what can the recipient do differently than before?**
3. **If this event is wrong or missing, which test or metric will detect it?**

For example, “log every `findById` call” usually fails test #2. “Log `repository.slow_operation` when pool wait exceeds the threshold, attached with a trace ID, to identify pool contention” usually passes.

## 4. Separating the Roles of Logs – Metrics – Traces

An observability objective does not always require a new log. Choose the right signal:

| Need | Preferred Signal | Why |
| --- | --- | --- |
| Request rate/sec, 5xx % | **Metric counter/rate** | Computed over traffic with low-cardinality labels |
| p95/p99 HTTP latency | **Metric histogram/timer** | Provides proper distribution and aggregation |
| At which step a request failed | **Trace** + related log | Shows span hierarchy and error context |
| A business decision just occurred | **Structured log/business event** | Captures event type, outcome, safe references |
| Sensitive action requiring durability | Dedicated **audit trail** | Has transaction/integrity/retention contract |
| Heap/CPU/pool pressure | **Infrastructure/application metrics** | Observes trends without spamming INFO |
| Specific retry/fallback sequence | **Logs + spans** | Shows attempts and semantic outcomes |

For example, p99 request latency **should not** be inferred from a few slow-request logs, because logs may be sampled, filtered, or dropped. Similarly, looking at one slow trace is not enough to claim all traffic is slow. Separate metrics and distributions must be defined for system-level decisions.

### 4.1. Correlation Across Signals

Useful connecting fields:
- `service.name`, environment, version/instance: **resource identity**.
- `trace_id`, `span_id` when inside an active span: **correlation with traces**.
- Controlled, generated `request_id`: **request investigation**.
- Templated `http.route`, status, method: **scope filtering**.
- Event timestamp and duration: **pinpointing timing and impact**.

Do not use `trace_id`, `request_id`, or `user_id` as **metric labels** for each request. They have high cardinality. Logs/traces may retain certain privacy-reviewed identifiers, while metrics should aggregate using labels such as route template, status class, or operation.

## 5. Building an Event Catalog from Critical Journeys

For a Java web application, start from **critical user journeys**: login, checkout, payment, permission updates, job synchronization, and message processing. For each journey, mark:
- Start/completion or outcome events only?
- Critical decision points and failure modes?
- Which dependencies can time out?
- Which events carry security/audit risk?
- Which layer has enough context to log without creating duplicates?
- Does any metric/trace already provide the same information?

An illustrative **event catalog**:

| Event name | Trigger | Suggested Level | Minimum Fields | Owner |
| --- | --- | --- | --- | --- |
| `service.started` | Startup is ready | INFO | service, version, environment | Bootstrap |
| `http.request.completed` | Request completes | INFO/sampled or metrics only | method, route, status, duration, trace | HTTP observation |
| `auth.denied` | Access denied | WARN/INFO per threat policy | auth method, reason enum, route, request ID | Security boundary |
| `order.created` | Order confirmed in valid state | INFO/business or audit | event, outcome, safe order alias | Use-case owner |
| `payment.provider_timeout` | Provider timeout exhausted | ERROR/WARN per retry ownership | provider alias, operation, error type, trace | Integration boundary |
| `storage.slow_operation` | DB access exceeds threshold | Conditional WARN | operation, datasource, duration | Repository instrumentation |
| `message.delivery_failed` | Retries exhausted and moved to DLQ | ERROR | queue, attempt count, error type | Message consumer |
| `permission.changed` | Permission successfully changed | Audit/security | approved actor reference, action, target, outcome | Authorization/audit |
| `logging.config_changed` | Significant level/sink/filter change | Audit/INFO | change ID, config version, actor role | Platform |
| `dependency.recovered` | Transitioned from degraded to healthy | INFO | dependency, recovery window | Health controller |

**Do not tie an event name to free-form message text.** Stable event codes allow querying across versions. For instance, `payment.provider_timeout` remains constant even if the display message differs across languages.

### 5.1. Triggers Must Have Precise Definitions

“Emit `order.created` when creating an order” is ambiguous:
- When the request starts?
- When validation finishes?
- When repository `save()` returns?
- After the transaction commits?
- When the event is published to a message broker?

If the objective is to track **committed business outcomes**, the event must be emitted from a source that reflects the commit by contract (a post-commit callback if best-effort, or a transactional outbox/audit store when durability is required). Use distinct names for attempts vs. results, such as `order.create_attempted` vs. `order.created`.

### 5.2. One Event per Method Is Not Required

A use case may invoke multiple repositories/services. If every method prints an INFO event, log volume grows rapidly while root-cause tracing becomes harder. Instead:
- The boundary records a **request summary** or metric.
- The service records key **business outcomes**.
- The adapter records **diagnostics** on abnormal failures or latency.
- The security module records events with specific security requirements.
- Traces provide spans for steps needing detailed investigation.

## 6. Choosing Log Levels by Meaning, Not Emotion

In SLF4J/Logback/Log4j 2, the familiar levels are TRACE, DEBUG, INFO, WARN, and ERROR. JUL uses different names (FINEST/FINER/FINE, INFO, WARNING, SEVERE).

| Common Level | Interpretation | Recommended Use |
| --- | --- | --- |
| TRACE | Very deep detail, usually disabled | Conditional debugging of specific phases/algorithms |
| DEBUG | Technical context useful during investigation | Cache strategy, decision path, query metadata |
| INFO | Valuable normal lifecycle events | Startup, configuration changes, business milestones |
| WARN | Abnormal condition the system can still handle | Notable retries, fallback, degraded mode |
| ERROR | Failed operation or loss of service requiring attention | Final failure, dependency outage, DLQ exhausted |

An HTTP `404` caused by a user requesting a non-existent record **is not automatically an ERROR**. A successful retry may be WARN or DEBUG depending on policy. Conversely, a successful access-permission change may be a critical audit event even without an exception.

**Severity and alerting are not the same.** Do not page on every ERROR; alert conditions must be based on impact, frequency, SLOs, risk, and runbooks. A single ERROR line might represent one failed request already retried by the client, with no outage.

### 6.1. When to Change Levels and When Never to Disable Them

- Production defaults typically keep selective INFO/WARN/ERROR.
- DEBUG/TRACE should only be enabled per logger/package, for an approved duration and scope.
- Mandatory security/audit events must be protected by a dedicated policy; never let a root-level change accidentally drop all critical events.
- For high log volume, prioritize removing **low-value events** before simply raising the global logger threshold.

Changing levels via a dashboard or runtime API requires authorization, auditing, and a rollback plan. For example, Spring Boot Actuator `/actuator/loggers` can modify levels at runtime, but those changes do not automatically update the source of truth or config files.

## 7. Designing a Schema: Enough to Answer Questions Without Excess Data

An event can follow a **common envelope**:

```json
{
  "timestamp": "2026-11-10T10:15:20.123Z",
  "severity": "ERROR",
  "event": "payment.provider_timeout",
  "service.name": "orders-service",
  "deployment.environment": "production",
  "service.version": "2026.11.1",
  "operation": "authorize_payment",
  "outcome": "FAILED",
  "error_type": "UPSTREAM_TIMEOUT",
  "duration_ms": 1500,
  "http.route": "/api/orders",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "span_id": "00f067aa0ba902b7"
}
```

This is an **illustrative application schema**, not a mandatory raw OTLP JSON format. The OpenTelemetry Logs Data Model distinguishes `Timestamp`, `ObservedTimestamp`, `SeverityText`, `SeverityNumber`, `Body`, `Attributes`, `Resource`, `TraceId`, and `SpanId`. When using an OTel exporter/Collector, map field names and data types according to your actual semantic conventions and version.

Fields to define:

| Field | Purpose | Constraints |
| --- | --- | --- |
| `event` | Stable event class name | Enum/catalog, not unbounded free text |
| `timestamp` | Timeline positioning | UTC/ISO 8601, avoid confusing with ingest time |
| `severity` | Priority classification | Consistent rules across modules |
| `service.name`/version | Identify emission source | Consistent with telemetry resource |
| `operation` | Business/technical action | Controlled set of values |
| `outcome` | SUCCESS/FAILED/DENIED/... | Enum, not exception text |
| `error_type` | Error classification | Must not contain raw messages with secrets |
| `http.route` | Endpoint template | Never raw URI/query/token |
| `duration_ms` | Case-specific latency analysis | Numeric, clear unit |
| `request_id` | Request lookup | Safely generated ID, not a session token |
| `trace_id`/`span_id` | Trace correlation | Only when a valid context exists |
| `actor_ref`/`target_ref` | Audit when needed | Only with valid basis and proper permissions |

**Sufficient fields ≠ whole objects.** Do not serialize an entire `HttpServletRequest`, `User`, JPA entity, or login DTO just “for context”. Those objects may contain passwords, tokens, addresses, health data, or financial details.

### 7.1. Distinguishing Error Codes from Exception Messages

Instead of:

```java
log.error("Payment failed: {}", ex.getMessage());
```

prefer standardized error types:

```java
log.error("event=payment.provider_timeout provider={} error_type={} trace_id={}",
        "provider-a", "UPSTREAM_TIMEOUT", safeTraceId);
```

Both are **SLF4J snippets inside a class that already has a logger**, not standalone runnable Java files. `safeTraceId` should only be a valid ID issued by the tracing/correlation infrastructure. If an exception message or cause contains a URL or token, logging it can leak secrets. Keep Throwables for debugging **only at controlled boundaries**, with appropriate data-filtering policies and access controls.

## 8. Standalone Java 17+ Example: From Objectives to Events

The following program simulates a catalog of three objectives:

1. **Tracking a business outcome:** order created.
2. **Tracking a security denial:** authentication rejected.
3. **Tracking an operational failure:** payment provider unavailable.

It uses only the JDK's `java.util.logging` (JUL) with zero external dependencies. An `Event` record enforces an event name, level, outcome, and a safe `reason`. `CaptureHandler` collects logs in memory to produce **fully deterministic stdout**; the logger is configured at `INFO` to suppress unnecessary `FINE` diagnostic events in production.

Create the file `LoggingObjectivesDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class LoggingObjectivesDemo {
    private record Event(
            String name,
            Level severity,
            String outcome,
            String reason) {
    }

    private static final class CaptureHandler extends Handler {
        private final List<String> lines = new ArrayList<>();

        @Override
        public void publish(LogRecord record) {
            if (!isLoggable(record)) {
                return;
            }
            lines.add(record.getLevel().getName()
                    + " " + record.getMessage());
        }

        @Override public void flush() { }
        @Override public void close() { }

        List<String> lines() {
            return List.copyOf(lines);
        }
    }

    private static void emit(Logger logger, Event event, String requestId) {
        if (!requestId.matches("req-[0-9]{3}")) {
            throw new IllegalArgumentException("INVALID_REQUEST_ID");
        }

        logger.log(event.severity(),
                "event=" + event.name()
                + " outcome=" + event.outcome()
                + " reason=" + event.reason()
                + " request_id=" + requestId);
    }

    public static void main(String[] args) {
        Logger logger = Logger.getLogger("demo.logging.objectives");
        CaptureHandler capture = new CaptureHandler();
        capture.setLevel(Level.ALL);
        logger.setLevel(Level.INFO);
        logger.setUseParentHandlers(false);
        logger.addHandler(capture);

        try {
            emit(logger, new Event(
                    "order.created", Level.INFO,
                    "SUCCESS", "NONE"), "req-100");
            emit(logger, new Event(
                    "auth.denied", Level.WARNING,
                    "DENIED", "INVALID_CREDENTIAL"), "req-101");
            emit(logger, new Event(
                    "payment.provider_timeout", Level.SEVERE,
                    "FAILED", "UPSTREAM_TIMEOUT"), "req-102");
            emit(logger, new Event(
                    "repository.cache_lookup", Level.FINE,
                    "SUCCESS", "NONE"), "req-103");

            for (String line : capture.lines()) {
                System.out.println(line);
            }
        } finally {
            logger.removeHandler(capture);
            capture.close();
        }
    }
}
```

Compile and run on JDK 17 or later:

```bash
javac --release 17 LoggingObjectivesDemo.java
java LoggingObjectivesDemo
```

**Exact stdout:**

```text
INFO event=order.created outcome=SUCCESS reason=NONE request_id=req-100
WARNING event=auth.denied outcome=DENIED reason=INVALID_CREDENTIAL request_id=req-101
SEVERE event=payment.provider_timeout outcome=FAILED reason=UPSTREAM_TIMEOUT request_id=req-102
```

Explanation:
- The logger level is INFO, so the FINE event `repository.cache_lookup` is not emitted; that is a deliberate **logging strategy choice**, not a bug in the demo.
- `Event` has standardized names and outcomes; no passwords, tokens, or exception messages are placed in the event.
- `requestId.matches(...)` is an **input validation rule for the demo**, not a universal request ID format standard. In production, use IDs issued by the system according to contract rather than relying solely on a regex.
- The handler checks `isLoggable(record)` and appends lines to a list without dynamic timestamps, making the output deterministic.
- `setUseParentHandlers(false)` prevents the root handler from printing extra lines and timestamps.
- These events simulate states; **`order.created` in the demo does not reflect a real transaction commit**. For real auditing, source events from an appropriate transactional/durable mechanism.
- This code is **not a complete observability system**: it has no backend, retention, TLS, tracing, or metric exporter. It only illustrates defining objectives and emitting logs with a consistent schema and level.

### 8.1. Why Is a Catalog Better Than Free-Form Messages?

If each service writes:

```text
Login fail
User authentication error
Bad password
Authentication rejected
```

then dashboards and alerts must search for multiple variants. A stable event code `auth.denied` with `reason=INVALID_CREDENTIAL` is far easier to filter and analyze. Humans can still read descriptive messages, but **never use free-text messages as the primary event classification API**.

### 8.2. What QA Does a Small Catalog Change Require?

If you rename an event from `auth.denied` to `authentication.denied`:
- Do existing search queries and dashboards still return results?
- Do SIEM detection rules need updating?
- Are downstream consumers parsing the old schema?
- Do historical reports need an alias during the transition period?
- Have event coverage unit/integration tests been updated?

The key takeaway is that **an event catalog is an operational contract**, not merely a naming convention.

## 9. Using SLF4J/Logback/Log4j 2 According to Defined Policy

In modern Java applications, SLF4J provides the common API, while Logback or Log4j 2 serves as the logging backend. Integration example:

```java
// Code snippet inside a service that already has org.slf4j.Logger log.
log.info("event=order.created outcome={} request_id={}",
        "SUCCESS", safeRequestId);

log.warn("event=auth.denied reason={} request_id={}",
        "PERMISSION_DENIED", safeRequestId);

log.error("event=payment.provider_timeout "
        + "provider={} error_type={} trace_id={}",
        "provider-a", "UPSTREAM_TIMEOUT", safeTraceId);
```

These are snippets that depend on external libraries and application variables `safeRequestId` and `safeTraceId`. The `{}` placeholder **is not data masking**; if you pass a token or a DTO containing PII as a logger argument, the value can still be rendered.

When adding a structured JSON encoder, consider numeric/boolean field types instead of stuffing everything into a single message string. With the SLF4J 2 fluent API, you can attach key-value pairs for compatible backends/encoders:

```java
log.atInfo()
   .addKeyValue("event", "order.created")
   .addKeyValue("outcome", "SUCCESS")
   .addKeyValue("request_id", safeRequestId)
   .log("Order creation finished");
```

**Note:** `addKeyValue` belongs to SLF4J 2; the encoder/layout must actually emit structured key-values for JSON fields to appear in the backend. If you only use a PatternLayout printing `%msg`, do not assume key-value pairs will become queryable columns.

### 9.1. Tying Objectives to Log Level Configuration

Spring Boot `application.properties` example:

```properties
logging.level.root=INFO
logging.level.com.example.orders=INFO
logging.level.com.example.orders.repository=WARN
logging.level.org.springframework=INFO
```

This is an **illustrative** configuration, not a mandatory policy for every project. Setting `com.example.orders.repository` to WARN may fit if routine query DEBUG logs are not needed. Never disable security/audit loggers via root-level settings without reviewing their specific requirements.

With Logback or Log4j 2, verify **root/child additivity, appender references, filters, and async queues**, because having the right level alone does not guarantee an event reaches its destination.

## 10. Determining Emission Locations and Ownership

A payment error might pass through:

```text
PaymentHttpClient → PaymentRepository → PaymentService
                                            |
                                      HTTP Handler
```

If every layer emits `ERROR payment failed`, a single incident generates multiple stack traces. Instead, assign clear ownership:

| Layer | What It Knows Best | Appropriate Logging |
| --- | --- | --- |
| HTTP client adapter | Connection timeout, response code, retry attempt | DEBUG / structured retry diagnostic |
| Repository | Database/transaction behavior | Slow/error classification when needed |
| Service | Business decision, fallback, idempotency | Business outcome or audit event |
| HTTP handler/consumer | Final result, response/retry/DLQ | One failure summary / ERROR |
| Platform/collector | Queue, delivery, export failure | Pipeline metrics and status diagnostics |

**Every event has one owner.** If two layers must emit two events for the same request, their names and semantics should differ (`payment.retry_scheduled` vs. `payment.failed_final`) so they are not miscounted as two independent errors.

### 10.1. Never Swallow Exceptions Just Because You Logged Them

Anti-pattern:

```java
try {
    repository.save(entity);
} catch (RuntimeException ex) {
    log.error("event=order.save_failed", ex);
}
return successResponse;
```

Logging does not fix a transaction or turn a failure into a success. If recovery is not possible, propagate or translate the exception per contract; let the boundary decide the status or retry. Never log and swallow a critical error.

### 10.2. Timing of Business Event Emission

Do not log `order.committed` immediately after `repository.save` and claim the data is committed. JPA `flush` and the transaction commit may still happen later. When an objective requires a durable outcome, use a transaction-bound audit/outbox; if it is only a best-effort notification, document the contract of the post-commit callback clearly.

## 11. Designing Privacy and Security as a Requirement, Not an Afterthought

A logging strategy must explicitly list **prohibited data**. According to OWASP, categories that generally should not be logged directly include access tokens, session identifiers, passwords, database connection strings, encryption keys, sensitive personal data, and information classified higher than the logging system is authorized to hold.

| Do Not Log Raw | Acceptable Safe Alternative (When Valid) |
| --- | --- |
| Password, OTP, PIN | `auth_method`, `reason=INVALID_CREDENTIAL` |
| Bearer/access/refresh token | `credential_present=true`, outcome |
| Cookie, session ID | `session_started`/`session_expired`, safe request ID |
| API key/client secret | Non-privileged integration alias/key version |
| Raw JWT or arbitrary decoded claims | Token type, validation result |
| Raw Authorization/Cookie headers | Allowlisted header names or boolean |
| Raw URI/query containing tokens | `http.route` template |
| Login/refresh body | Event type, validation category, no field values |
| Entity/DTO containing PII | Entity/operation type and standardized outcome |
| SQL bind values | Logical query name, table/entity, error type |
| Unsanitized full exception message | Error class/category and trace ID |
| Private key/DB password | Approved key alias/config version |

**Allowlists are stronger than blocklists** as schemas evolve. If a developer adds a `sessionProof` field to a DTO, serializing the whole object can leak it even if a filter blocks `token` and `password`.

### 11.1. Log Injection and Untrusted Data

Data from HTTP headers, query strings, or forms can contain newlines, control characters, or JSON delimiters to forge log entries. Never concatenate raw user input into messages. When a field must be emitted:
- Validate length and character set as needed.
- Encode properly for JSON/structured formats.
- Standardize reason/status lists using enums.
- Limit bytes per event to prevent log flooding.
- Do not blindly place untrusted input into MDC/ThreadContext.

A “JSON” logging encoder only handles proper escaping when configured correctly; **it does not automatically strip secrets**.

### 11.2. Purpose-Bound Retention and Access Control

If the objective is application debugging, detailed DEBUG logs may not need long retention. If the objective is legally mandated auditing, longer retention and stricter access controls may be required. However, **do not hardcode a fixed number of days** for all organizations: retention depends on needs, contracts, regulations, classification, and cost.

Beyond retention duration, define:
- Who can search, download, export, and share logs?
- Are security/audit logs separated from application debug logs?
- Is there encryption in transit/at rest, access auditing, and backup protection?
- Are there personal data deletion/anonymization requirements, and what process handles them?
- Can alert/ticket/chat channels accidentally copy credentials?

## 12. Log Quality Objectives and Verifiability

Every objective should translate into testable **acceptance criteria**. For example:

| Quality Attribute | Sample Criterion | Verification Method |
| --- | --- | --- |
| **Coverage** | Every provider timeout branch emits the right event | Unit/integration tests |
| **Correctness** | Outcome/level/event code match semantics | State-machine tests |
| **Correlation** | Trace/request ID present when context exists | HTTP → downstream tests |
| **Completeness** | Error type/operation present without raw secrets | Schema validation |
| **Uniqueness** | One final failure does not produce three identical ERRORs | Count by event ID/trace |
| **Timeliness** | Canary log searchable within target ingest window | End-to-end pipeline check |
| **Privacy** | Synthetic canary token does not appear in any sink | Secret leak tests |
| **Availability** | Collector outage does not hang JVM beyond budget | Fault injection |
| **Cost** | Log volume/ingest rate within budget | Load tests, counters |
| **Durability** | Audit event survives crash per contract | Transaction/storage tests |
| **Consistency** | Event name/schema stable across releases | Contract tests |
| **Actionability** | Has owner, dashboard/query, and runbook | Incident drill |

Specific SLO numbers must be agreed upon by the team. Do not claim “100% of logs reach the backend in under 1 second” if the pipeline uses async queues, networks, and storage without measurable guarantees. Distinguish **event ingestion latency** from **request processing duration**.

### 12.1. An Example Acceptance Criterion Written as a Test

Objective: “When a provider times out, emit one final event with enough diagnostics without leaking credentials.”

- Given: the payment provider times out for a request with a synthetic ID.
- When: the service exhausts retries per policy and returns the final error.
- Then: there is **exactly one** final `payment.provider_timeout` log from the boundary.
- Then: `error_type=UPSTREAM_TIMEOUT` and `provider=provider-a`.
- Then: the event includes valid correlation metadata if an active trace exists.
- Then: no Authorization value, API key, password, or raw request body is present.
- Then: failure counter/histogram metrics update regardless of whether DEBUG logs are enabled.

This is a **testing contract**, not Spring-specific code yet. It can be automated using test appenders, mock providers, integration tests, and environment-specific backend queries.

## 13. Log Volume and Cost: Objectives Must Withstand Production Traffic

An overly detailed logging objective may become unviable as traffic grows. Rough estimate:

```text
bytes/second ≈ requests/second
             × events/request
             × average encoded bytes/event

bytes/day ≈ bytes/second × 86,400
```

Hypothetical example:
- 1,000 requests/second.
- 3 log events per request.
- 450 bytes average per encoded event.

Result:

```text
1,000 × 3 × 450 = 1,350,000 bytes/second
1,350,000 × 86,400 = 116,640,000,000 bytes/day
≈ 116.64 GB/day (decimal, excluding replicas/index/retention)
```

This figure is **raw data volume** only in an example scenario. Backend indexing, compression, replicas, storage class, egress, and retention can alter costs significantly. Peak traffic, large exception stack traces, and log bursts rarely match the average.

When reducing volume:
1. Remove events that lack a clear objective.
2. Consolidate repetitive logs into a single outcome summary.
3. Use metrics for counts/rates instead of per-call INFO logs.
4. Keep critical error/security events per policy.
5. Sample frequent events where appropriate, optionally recording `sampling_rate`.
6. Cap field sizes, stack traces, and payloads by use case.
7. Choose retention tiers by value; do not arbitrarily delete audit logs.
8. Monitor drops, queue depth, and backend ingest errors.

**Sampling changes data meaning.** If you keep only 1 in 10 request summaries, do not treat raw log line counts as absolute request counts. Metric counters/throughput or sampling-aware estimation must be used when full-traffic numbers are needed.

### 13.1. Logging Too Little Also Has a Cost

Logging nothing out of “fear of cost” forces on-call engineers to enable TRACE in production during emergencies, which risks leaking data and prolonging incidents. A good strategy selects **a small set of stable, high-signal events** at INFO/WARN/ERROR and keeps controlled DEBUG available for deep investigation.

## 14. Choosing Delivery Routes: Stdout, File, Remote, or Audit Storage?

Logging objectives influence the transport path:

| Objective | Typically Sensible Choice | What to Verify |
| --- | --- | --- |
| App diagnostics in containers | Structured stdout → shipper/Collector | Log parser, pod metadata, retention |
| Correlating logs with traces | Encoder/bridge with trace/span IDs | Active context, OTLP pipeline |
| Legacy on-prem file capture | Rolling file + file shipper | Disk quota, rotation, offsets |
| Low-latency remote ingest | Async exporter/appender | Queue/drop/retry/backpressure |
| Security investigation | Central restricted security log store | ACLs, access audit, tamper detection |
| Durable transaction audit | Transactional audit/outbox/database | Commit, crash recovery, replay/dedup |
| Metrics/SLOs | Micrometer/OpenTelemetry metrics | Registry, histograms, labels, exporter |

**A successful TCP write does not prove the backend durably stored the log.** HTTP/OTLP responses must also be interpreted according to the receiver's contract and the Collector/exporter/queue layers. For critical channels, monitor lost events, retries, and queue capacity.

If the same event is emitted via both a stdout shipper and an OTLP exporter into the **same backend index**, duplicates can occur. This skews error counts and incident searches; the strategy must specify the primary emission source for each event type.

## 15. Defining Ownership, Lifecycle, and Strategy Changes

A logging strategy needs clear owners:

| Item | Responsibility |
| --- | --- |
| Event catalog | Engineering + service owner |
| Security events/data exclusion | Security/privacy owner |
| Audit retention/durability | Compliance/business owner + platform |
| Shared schema/context | Platform/observability |
| Logger/appender configuration | Service/platform owner |
| Alerts, dashboards, runbooks | On-call/SRE and service owner |
| Version/schema migration | API/event contract owners |
| Secret leak response | Security incident process |

When modifying an event:
- Do any dashboards, SIEM rules, or alert queries depend on the event name?
- Will a severity change affect sampling or drop policies?
- Could changing a field type from string to integer break parsers?
- If adding PII, is there a valid legal basis and storage authorization?
- If changing exporters/encoders, is there a risk of duplicate or missing logs?
- If changing the root level, are mandatory security events still preserved?
- Is there a rollback/config-versioning plan and post-deploy QA?

**Logging policy should be a code-reviewed and versioned contract.** Not every update needs heavy ceremony, but changing an event name or retention can impact operations and compliance far more than editing a message string.

## 16. Workflow for Designing Logging Objectives for a New Java Service

### Step 1 — List User Journeys and Failure Modes

Example for an order service:
- Order creation success, duplicate request.
- Payment provider failure, timeout, retry, and fallback.
- Insufficient inventory.
- Database connection pool exhausted.
- Unauthorized order creation attempt.
- Message sent to DLQ.
- Deploy/restart, configuration changes.

### Step 2 — Write Decision Questions

Examples:
- “How many requests returned 5xx after the release?” → metrics.
- “Which error type caused a specific payment to fail?” → structured log.
- “Which dependency call took 1 second?” → trace.
- “Who granted admin privileges and did the change commit?” → audit.

### Step 3 — Assign Ownership for Each Event

Boundary for final failures, service for business outcomes, adapter for specific diagnostics, audit subsystem for privileged actions. Never log the same failure under the same name at every layer.

### Step 4 — Design Schema and Privacy Rules

Finalize event name, severity, required fields, field types, cardinality, max length, and sensitive-data exclusions. Use route templates, reason enums, and valid trace/request IDs.

### Step 5 — Define Levels, Sampling, and Retention

Specify production defaults, loggers allowed to enable DEBUG, rate-limit/sampling rules, alert thresholds, and mandatory data that must never be dropped.

### Step 6 — Choose Sinks and Transport Mechanisms

Distinguish best-effort app diagnostics from audit durability. Define outage resilience, queue full/drop behavior, TLS, ingest lag, and log read permissions.

### Step 7 — Write Acceptance Tests and Runbooks

Simulate 2xx, 4xx, 5xx, timeouts, retries, DB loss, exceptions, async execution, and Collector outages; verify logs have sufficient context without leaking secrets, and that metrics/traces still correlate.

### Step 8 — Canary Rollout and Real-World Measurement

Monitor log volume/cost, events per request, ingest delay, duplicates, query usability, p95 latency, and security canaries. If logs are noisy yet fail to support decisions, update the event catalog—**do not blindly turn up DEBUG**.

## 17. Common Mistakes When Defining Logging Objectives

**Mistake 1 — “Log everything just in case.”** Results in noise, cost, and data exposure risk. Keep only events with a clear use case and owner.

**Mistake 2 — Choosing INFO/WARN/ERROR before knowing what the event means.** Severities become inconsistent, causing alert fatigue.

**Mistake 3 — Using per-request INFO logs to measure request rate/p99.** Metrics/histograms are more suitable; logs can be dropped or sampled.

**Mistake 4 — Logging business success before transaction commit.** The event does not reflect the true outcome; audits require a transactional source.

**Mistake 5 — Logging stack traces at every layer.** A single failure gets counted multiple times and becomes harder to investigate.

**Mistake 6 — Printing entire entities, HTTP bodies, or SQL binds for context.** Leaks passwords, tokens, and PII; use an allowlist.

**Mistake 7 — Using raw URLs or user IDs as metric tags.** Causes cardinality explosion; use route templates and low-cardinality dimensions.

**Mistake 8 — Assuming DEBUG never reaches production.** DEBUG can be enabled during incidents; still avoid secrets at the source.

**Mistake 9 — Not defining who consumes the event.** Logs sit in the backend with no query or runbook referencing them.

**Mistake 10 — Relying on collector ACKs to claim zero-loss auditing.** Networks and backends have queues and crash windows; a separate durability contract is required.

**Mistake 11 — Testing only that code calls the logger.** Does not prove that levels, filters, appenders, and the backend actually receive the event.

**Mistake 12 — Ignoring retention, read permissions, and copies.** Logs may be exported to alerts, tickets, and backups; restrict them according to purpose.

**Mistake 13 — Not versioning schemas.** Renaming an event breaks dashboards, SIEM detections, and integration consumers.

**Mistake 14 — Counting “ERROR lines” as “number of incidents”.** One incident involves multiple requests, retries, and duplicate logging; clear metrics and event semantics are needed.

**Mistake 15 — Trying to use one channel for everything.** Security/audit, request diagnostics, and performance metrics have different privacy, durability, and retention requirements.

## 18. Pre-Release QA Matrix for a Logging Strategy

| Case | What Must Be Proven |
| --- | --- |
| HTTP 200 | Summary/metric follows policy, no INFO spam per method |
| 404 not found | Not treated as an infrastructure ERROR by default |
| Auth denied | Security event has accurate reason, no credential leaked |
| 5xx exception | One final failure log, error type + trace, no 3-layer duplicates |
| DB timeout | Distinguishes timeout from not found; required metrics/traces exist |
| Successful retry | Attempts and final outcome have unambiguous semantics |
| Exhausted retry | Final failure recorded, error not swallowed |
| Transaction rollback | No false “committed success” event |
| Audit privileged change | Actor/action/outcome follow policy and durable contract |
| Async/worker thread | Correlation ID propagated to the right scope |
| Logger level change | Critical events still emitted per policy |
| Structured JSON | Field types, names, escaping, and schema verified |
| Token canary | Never leaks into messages, args, throwables, MDC, spans, or metrics |
| Log injection | Newlines/control characters do not forge fake events |
| Load test | CPU, storage, collector queue, and request latency stay within budget |
| Collector down | App does not hang beyond timeout; loss/drops are observable |
| Dual ingest | One logical event is not duplicated in the same index |
| Event schema migration | Old queries/alerts updated and tested |
| Metrics p95/p99 | Proper histogram and low-cardinality labels exist |
| Retention/privacy | Access, export, delete, and backup policies enforced |
| End-to-end canary | Event reaches the right sink and is searchable by event code/ID |

QAing console output alone does not test the pipeline. For centralized logging, verify source → encoder → shipper/collector → backend, and note that event timestamp differs from ingest timestamp. However, running all failure injections in production can cause disruption; test first in staging or an isolated environment with synthetic data.

## 19. Fillable Logging Objective Template per Event

```yaml
# Illustrative requirement document, not a logback/log4j2 config.
event_name: "payment.provider_timeout"
purpose: "Isolate provider timeouts and support fallback decisions"
consumer: "Orders on-call"
owner: "Payments service team"
trigger: "Retry budget exhausted and payment failed"
severity: "ERROR"
source_boundary: "Payment application service"
required_fields:
  - "service.name"
  - "service.version"
  - "operation"
  - "provider_alias"
  - "error_type"
  - "trace_id"
excluded_fields:
  - "authorization"
  - "access_token"
  - "card_number"
  - "payment_payload"
sampling: "Keep final failures; separate policy for success diagnostics"
delivery: "Central app logs; best-effort per current pipeline"
retention: "Per approved policy"
acceptance:
  - "One final error event per failed request"
  - "Correlation available to locate trace when sampled"
  - "Synthetic token canary does not appear in any sink"
  - "Collector failures are monitored independently"
```

This document can be stored alongside ADRs or the service's event catalog and reviewed together with code and observability dashboards. Values in the example are not a rigid standard for every organization; **retention, zero-loss, and audit** requirements must be decided based on actual needs.

## 20. Pre-Coding Objective Decision Checklist

1. **Purpose:** incident response, debugging, security, audit, business monitoring, or performance?
2. **Consumers:** who searches it, who gets alerted, and who is authorized to act?
3. **Question:** what does this event answer that existing metrics/traces do not?
4. **Trigger:** emitted on attempt, failure, retry, or commit? Are double-logs prevented?
5. **Schema:** event name, timestamp, level, outcome, error type, service, version, trace ID?
6. **Prohibited data:** passwords, tokens, cookies, PII, SQL binds, raw requests/exceptions?
7. **Right signal:** log, metric, trace, or audit storage?
8. **Cost:** events/request, payload size, ingest/day, retention, sampling?
9. **Reliability:** queue/drop/retry/Collector outage, audit durability?
10. **Access:** search/export permissions, TLS, encryption, retention, and backups?
11. **Verification:** tests find the right logs, exact counts, right level/schema, and zero secret leaks?
12. **Operations:** dashboard/query/runbook, alerting, owner, and schema-change plan?

**Conclusion:** A good logging strategy does not start with “how many lines to log”, but with **“what question do we need to answer to make which decision?”**. From there, you choose the events, emission points, log levels, field schemas, corresponding signals, cost bounds, and data protections. Only when objectives are clear enough to be written as acceptance tests do logs become a useful operational asset rather than production noise.

## References

- [OWASP – Logging Cheat Sheet: Purpose, events to log, data to exclude, and testing](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html).
- [OpenTelemetry – Logs Data Model](https://opentelemetry.io/docs/specs/otel/logs/data-model/).
- [OpenTelemetry – Observability Signals](https://opentelemetry.io/docs/concepts/signals/).
- [OpenTelemetry – Semantic Conventions](https://opentelemetry.io/docs/specs/semconv/).
- [OpenTelemetry – Java instrumentation](https://opentelemetry.io/docs/languages/java/).
- [SLF4J – User Manual, fluent logging](https://www.slf4j.org/manual.html).
- [Logback – Logging Architecture](https://logback.qos.ch/manual/architecture.html).
- [Apache Log4j 2 – Log Levels](https://logging.apache.org/log4j/2.x/manual/customloglevels.html).
- [Spring Boot – Logging configuration](https://docs.spring.io/spring-boot/reference/features/logging.html).
- [Oracle Java 17 – java.util.logging.Logger](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Logger.html).
- [Micrometer – Timers and histograms](https://docs.micrometer.io/micrometer/reference/concepts/timers.html).
