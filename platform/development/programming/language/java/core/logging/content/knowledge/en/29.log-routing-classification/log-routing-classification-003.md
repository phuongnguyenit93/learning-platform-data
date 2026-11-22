# Separating Audit Logs from Application Logs in Java

## 1. What is audit log separation and why do it?

**Audit logs** record actions that matter for accountability, traceability, and verification: **who** performed **what action**, on **which target**, **when**, from **what context**, and with **what outcome**. Examples: granting admin permissions, changing order status, approving a payment, accessing sensitive data, or failed logins.

**Application logs** (application/diagnostic logs) serve operations and debugging: exceptions, latency, processing state, retry attempts, downstream connections, queries, or technical messages. Both types can relate to the same request, yet differ in purpose, criticality, access permissions, retention period, and integrity requirements.

**Separating audit logs** means classifying events right at the source and routing audit events to a **separate channel, appender, file, or storage system**, applying appropriate ingestion and protection policies. Simply adding the word "AUDIT" to a shared logger's message does not create an independent audit pipeline.

| Criterion | Application log | Audit log |
| --- | --- | --- |
| Core question | How is the system running, and where are the errors? | Who did what, to which target, and with what outcome? |
| Examples | Connection timeout, slow request, retry | USER_ROLE_CHANGED, ORDER_APPROVED, ACCESS_DENIED |
| Volume | Can be very large, lots of DEBUG/INFO | Usually selective by business/security action |
| Filtering/sampling | Diagnostic logs may be reduced per policy | Mandatory events must not be sampled or dropped arbitrarily |
| Retention | Based on observability needs and cost | Based on audit policy and applicable obligations |
| Access permissions | Operations/development teams per role | More restricted; protected from unauthorized modification/deletion |
| Durability | Partial loss of non-critical logs may be acceptable | May require durable evidence and integrity verification |

An ERROR event is not automatically an audit event; a **successful** permission-granting action may require auditing even if no ERROR occurred at all. Therefore, you cannot build a reliable audit store simply by copying all WARN/ERROR entries from `application.log`.

## 2. Which events should go into the audit channel?

The scope is determined by business requirements, risk, and applicable regulations. Examples with traceability value:

- **Authentication and authorization:** successful/failed logins per policy, access denials, role/permission changes, issuing or revoking tokens or access keys.
- **Critical data changes:** creating, approving, rejecting, editing, canceling, or deleting orders/transactions; data administration operations.
- **Sensitive resource access:** exporting reports, reading protected records, downloading or sharing critical data.
- **Administrative actions:** changing security configuration, enabling/disabling critical features, changing policies or user permissions.
- **Suspicious actions:** attempts to bypass limits, insufficient-permission access, unusual tasks; specific criteria should be defined to avoid generating excessive noise.

You should not audit every DEBUG line, every getter call, every SQL query, or every healthcheck. Those are usually technical logs that inflate volume and obscure actions that need verification. Conversely, never skip a permission-denial event just because the transaction rolled back: **a denied attempt may also require audit evidence**.

Before writing code, define a list of **event codes** with stable meanings, such as `ORDER_APPROVED`, `USER_ROLE_REVOKED`, `EXPORT_REQUESTED`. Do not use free-form natural-language sentences as the sole identifier of an action, because wording may change or be localized.

## 3. Designing a structured audit schema

An audit record should be data with well-defined fields, rather than a sentence that is hard to query. Illustrative JSON example:

~~~json
{
  "eventId": "evt-000042",
  "occurredAt": "2026-11-10T02:00:00Z",
  "actorType": "USER",
  "actorId": "user-7",
  "action": "ORDER_APPROVE",
  "targetType": "ORDER",
  "targetId": "order-42",
  "outcome": "SUCCESS",
  "correlationId": "req-1",
  "sourceService": "order-service",
  "reasonCode": "APPROVAL_POLICY_MET"
}
~~~

The IDs above are mock data; do not rely on them to infer real identities. A practical schema should consider:

| Field | Meaning | Notes |
| --- | --- | --- |
| eventId | Identifier of **one audit event** | Used to deduplicate records on retry |
| occurredAt | Timestamp when the event occurred, preferably with offset/UTC | Synchronize clocks; distinguish write time from ingest time |
| actorType / actorId | Subject initiating the action | Can be USER, SERVICE, SYSTEM; taken from authenticated context |
| action | Fixed action code | Maintained with a catalog and schema version |
| targetType / targetId | Affected target object | Use necessary identifiers, minimize PII |
| outcome | SUCCESS, DENIED, FAILED, ... | Distinguish an attempt from a committed change |
| correlationId | Link to the business request/trace | **Does not replace eventId** |
| sourceService | Component generating the event | Helps investigate across multiple services |
| reasonCode / allowed metadata | Reason or supporting information | Avoid including raw sensitive data |

A single request can generate **multiple** audit events; therefore, sharing the same `correlationId` is normal. `eventId` must differ for each logical event, whereas when **re-sending the same event** after a network error, the same `eventId` must be preserved so the consumer can deduplicate. If a transaction has multiple attempts, clearly define how `transactionId`, `attemptId`, and `eventId` are linked.

For data changes, before/after values or a selective diff may be needed; never copy an entire record containing passwords, tokens, financial details, or sensitive personal data.

## 4. Routing model: two loggers, two destinations

With SLF4J + Logback or Log4j 2, a straightforward approach is to create a **dedicated named logger for audit** and attach an independent appender:

~~~text
                                  +--> Application logger
Business code --------------------|       |
                                  |       v
                                  |   APPENDER APP
                                  |       |
                                  |   application.log
                                  |
                                  +--> Logger "audit.events"
                                          |
                                          v
                                     APPENDER AUDIT
                                          |
                                       audit.log
                                          |
                                   Audit store/collector
~~~

Here, **routing** is based on the logger name chosen when emitting the event. Do not rely on ERROR/WARN levels to guess whether something is an audit event.

A key detail in Logback and Log4j 2 is **additivity**: by default, logs from a child logger propagate to appenders of parent loggers, including `ROOT`. If you attach `AUDIT_FILE` to the audit logger while leaving `additivity=true`, audit events can also appear in `application.log`, mixing data and increasing the risk of information exposure. To isolate the output path, set **`additivity=false`** on the audit logger and attach the `AUDIT` appender directly.

**Note:** Setting `additivity=false` without configuring a corresponding appender can cause events to go nowhere. You must also check appender filters/thresholds and error handlers. Channel separation at the framework configuration level is only the **routing step**, not a guarantee of durable storage.

## 5. Standalone Java 17+ example: observing two log streams

The following snippet uses `java.util.logging` (JUL) built into the JDK to illustrate two independent loggers attached to two separate `Handler`s. To make the output easy to inspect, both `Handler`s print to stdout with stream labels **APP** and **AUDIT**; in a real application, each `Handler`/appender writes to its own destination.

Create **AuditRoutingDemo.java**:

~~~java
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class AuditRoutingDemo {
    private static Handler sink(String stream) {
        return new Handler() {
            { setLevel(Level.ALL); }

            @Override
            public void publish(LogRecord record) {
                if (isLoggable(record)) {
                    System.out.println(stream + " | "
                            + record.getLevel().getName() + " | "
                            + record.getMessage());
                }
            }

            @Override public void flush() {}
            @Override public void close() {}
        };
    }

    public static void main(String[] args) {
        Logger app = Logger.getLogger("demo.app");
        Logger audit = Logger.getLogger("audit.events");

        Handler appSink = sink("APP");
        Handler auditSink = sink("AUDIT");

        // Prevent JUL from forwarding to parent logger Handlers.
        app.setUseParentHandlers(false);
        audit.setUseParentHandlers(false);
        app.setLevel(Level.INFO);
        audit.setLevel(Level.INFO);

        app.addHandler(appSink);
        audit.addHandler(auditSink);

        try {
            app.info("request-complete id=req-1");
            audit.info("eventId=evt-1 actor=user-7 "
                    + "action=ORDER_APPROVE target=order-42 "
                    + "outcome=SUCCESS");

            app.warning("slow downstream");
            audit.info("eventId=evt-2 actor=user-7 "
                    + "action=ORDER_DELETE target=order-42 "
                    + "outcome=DENIED");
        } finally {
            app.removeHandler(appSink);
            audit.removeHandler(auditSink);
            appSink.close();
            auditSink.close();
        }
    }
}
~~~

Compile and run:

~~~bash
javac AuditRoutingDemo.java
java AuditRoutingDemo
~~~

Stdout:

~~~text
APP | INFO | request-complete id=req-1
AUDIT | INFO | eventId=evt-1 actor=user-7 action=ORDER_APPROVE target=order-42 outcome=SUCCESS
APP | WARNING | slow downstream
AUDIT | INFO | eventId=evt-2 actor=user-7 action=ORDER_DELETE target=order-42 outcome=DENIED
~~~

**Explanation:** The `demo.app` logger only sends to `appSink`; the `audit.events` logger only sends to `auditSink`. Both log at `INFO`, yet their logging purposes differ. Using `INFO` for audit events **does not mean audit events are INFO application logs**: the audit channel is determined by the **dedicated logger and appender**. The demo uses a custom `Handler` that calls `isLoggable(record)` to respect the `Handler`'s level and `Filter`.

This example only demonstrates routing. The console is not a durable audit store; the demo code also lacks schema validation, actor authentication, transactional persistence, retention, and tamper resistance. Those requirements need the architecture covered in later sections.

## 6. Using SLF4J to emit audit events intentionally

In a project using SLF4J, business code can keep a normal class-named logger and create a **dedicated audit logger** with a fixed name:

~~~java
// Illustrative snippet inside a service using SLF4J.
// Requires SLF4J dependency and a logging backend;
// the variables actorId, orderId, eventId, correlationId
// come from authenticated/controlled sources.
private static final org.slf4j.Logger appLog =
        org.slf4j.LoggerFactory.getLogger(OrderService.class);

private static final org.slf4j.Logger auditLog =
        org.slf4j.LoggerFactory.getLogger("audit.events");

public void recordApproval(String eventId, String actorId,
                           String orderId, String correlationId) {
    auditLog.info(
            "eventId={} actor={} action=ORDER_APPROVE "
            + "target={} outcome=SUCCESS correlationId={}",
            eventId, actorId, orderId, correlationId);
}
~~~

**This is a fragment to place inside an appropriate class**, not a standalone program. `OrderService` is an example class name. Audit values must come from a trusted context (authenticated principal, verified business data)—never blindly trust an `actorId` submitted directly by an HTTP client.

Centralize audit logic in an **`AuditService` or `AuditEventPublisher`** to standardize `eventId`, `action`, `outcome`, schema, and error policy. Avoid letting each controller concatenate strings with inconsistent field names. If high transactional reliability is required, `AuditService` must have a durable write path; simply calling `auditLog.info(...)` is not enough.

In systems with structured logging, prefer passing audit fields as structured attributes or safely encoded JSON. The `key=value` string example above helps teach routing, but makes escaping difficult to guarantee if data contains spaces, newlines, or control characters.

## 7. Logback: separating application.log and audit.log

With SLF4J + Logback Classic, you can route audit logs using a logger name and `additivity=false`. Example **logback.xml** (in Spring Boot, **logback-spring.xml** can be used where appropriate):

~~~xml
<configuration>
  <appender name="APP_FILE"
            class="ch.qos.logback.core.rolling.RollingFileAppender">
    <file>logs/application.log</file>
    <rollingPolicy
        class="ch.qos.logback.core.rolling.TimeBasedRollingPolicy">
      <fileNamePattern>logs/application.%d{yyyy-MM-dd}.log</fileNamePattern>
      <maxHistory>14</maxHistory>
    </rollingPolicy>
    <encoder>
      <charset>UTF-8</charset>
      <pattern>%d{ISO8601} %-5level %logger - %msg%n</pattern>
    </encoder>
  </appender>

  <appender name="AUDIT_FILE"
            class="ch.qos.logback.core.rolling.RollingFileAppender">
    <file>logs/audit.log</file>
    <rollingPolicy
        class="ch.qos.logback.core.rolling.TimeBasedRollingPolicy">
      <fileNamePattern>logs/audit.%d{yyyy-MM-dd}.log</fileNamePattern>
      <maxHistory>90</maxHistory>
    </rollingPolicy>
    <encoder>
      <charset>UTF-8</charset>
      <pattern>%d{ISO8601} %logger - %msg%n</pattern>
    </encoder>
  </appender>

  <logger name="audit.events" level="INFO" additivity="false">
    <appender-ref ref="AUDIT_FILE"/>
  </logger>

  <root level="INFO">
    <appender-ref ref="APP_FILE"/>
  </root>
</configuration>
~~~

**Resulting flow when no other configuration overrides it:**

| Logger called | Event | application.log | audit.log |
| --- | --- | --- | --- |
| com.example.OrderService | INFO request processed | Yes | No |
| audit.events | INFO ORDER_APPROVE | No | Yes |
| audit.events | INFO ACCESS_DENIED | No | Yes |
| com.example.OrderService | ERROR timeout | Yes | No |

Because `ROOT` only attaches `APP_FILE`, application loggers go to the general file. The **`audit.events`** logger attaches `AUDIT_FILE` and has `additivity=false`, so its events do not propagate up to `ROOT`. Child loggers under the `audit.events` hierarchy also follow this branch unless overridden individually.

Usage notes:

- **14 and 90 are sample history counts**, not mandatory retention periods. Deleting audit logs must comply with actual policy; if long-term retention is needed, ship them to a dedicated audit store with retention controls.
- Both paths must have appropriate directories and write permissions. With multiple instances/containers, do not let independent processes arbitrarily write to the same shared file path unless the backend safely supports it.
- Do not let framework or environment configuration set the audit logger to `OFF` or higher than `INFO`, which would drop required events. Monitoring the effective configuration may be necessary.
- Do not also attach `AUDIT_FILE` to `ROOT`, unless you truly want every application log to go into `audit.log`.
- **`RollingFileAppender` only rotates files and manages local history**; it does not provide immutable storage, tamper resistance, end-to-end write acknowledgment, or a guarantee against event loss on crash.

If structured JSON auditing is needed, replace the pattern encoder with an encoder compatible with your backend and version; test actual fields, newlines, special characters, and queryability.

## 8. Log4j 2: configuring separate Logger and AppenderRef

If the backend is Log4j 2 Core, the equivalent separation pattern in **log4j2.xml** is:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<Configuration status="WARN">
  <Appenders>
    <File name="APP_FILE" fileName="logs/application.log"
          append="true">
      <PatternLayout
          pattern="%d{ISO8601} %-5p %c - %m%n"/>
    </File>

    <File name="AUDIT_FILE" fileName="logs/audit.log"
          append="true">
      <PatternLayout
          pattern="%d{ISO8601} %c - %m%n"/>
    </File>
  </Appenders>

  <Loggers>
    <Logger name="audit.events" level="info" additivity="false">
      <AppenderRef ref="AUDIT_FILE"/>
    </Logger>

    <Root level="info">
      <AppenderRef ref="APP_FILE"/>
    </Root>
  </Loggers>
</Configuration>
~~~

The **`audit.events`** logger references only `AUDIT_FILE` and stops forwarding events to `ROOT`. Other application loggers inherit from `ROOT` and go to `APP_FILE`. This example uses the `File` appender for readability; in production, add rolling/retention, access permissions, error monitoring, and appropriate long-term storage. Do not copy class names and XML elements between Logback and Log4j 2: they are two different backends.

In Log4j 2, `AppenderRef` can have its own level/filter. If a reference or appender filter rejects an audit event, declaring the logger properly still does not guarantee the log is emitted. Filters, async policies, I/O errors, and additivity must be checked together.

### When to use a marker or context instead of a logger name?

A marker such as `AUDIT` can classify events structurally rather than by logger name. That is useful when you want to keep class-named loggers, but it requires configuring filters/routing properly for **every destination**. Separating via a fixed-name logger is easier to verify for this lesson.

With strict requirements, code that emits events into an `AuditService` is usually better than relying on a marker convention that a developer might forget to attach. Pick one primary mechanism and write tests proving every mandatory audit event actually reaches the dedicated channel.

## 9. Spring Boot: logging.level does not create a separate audit channel

With Spring Boot, properties like:

~~~properties
logging.level.root=INFO
logging.level.audit.events=INFO
~~~

only control **logger levels**. They **do not automatically create `audit.log`**, do not disable additivity, and do not attach appenders. To route by logger name with Logback, place the appropriate configuration in `logback-spring.xml` (or whichever file the system selects), as shown in Section 7.

Depending on Spring Boot and the classpath, the default backend may be Logback; if switching to Log4j 2, you must use the corresponding configuration. Avoid letting two backends/providers conflict.

When deploying, verify which config file is **actually loaded**, which environment overrides levels, and which output paths actually exist. Changing log levels via runtime management endpoints can accidentally disable the audit logger if permissions or guards are not properly designed.

## 10. Separating the output path is not the same as durable audit storage

This is the most important architectural boundary:

~~~text
(A) Routing for observability convenience
Application -> audit logger -> AUDIT_FILE -> file/collector
          Suitable when appender failure risk is acceptable per policy.

(B) Mandatory audit requiring durable evidence
Business transaction + Audit Outbox (same database transaction)
                         |
                         v
                Event-publishing worker
                         |
                         v
               Dedicated audit store
                 (dedup eventId)
                         |
                         v
              Confirmation, monitoring
~~~

In (A), calling `auditLog.info(...)` may return after handing the event to an appender or queue, which does not mean the file was fsynced, the collector received it, or the record was persisted immutably. If the queue is full, the process is killed, the disk fills up, or the network fails, logs can still be lost.

If correctness requires that **every successful business change has an audit record**, one option is the transactional outbox:

1. Within the **same database transaction**, perform the business change and write an outbox record containing `eventId` and the required audit fields.
2. If the transaction rolls back, both the business change and the outbox record roll back; never claim success before committing.
3. After commit, a worker reads the outbox, sends the event to the dedicated audit store, retries on failure, and marks delivery as complete.
4. The receiving store uses `eventId` for **idempotency/deduplication**, because retries can often deliver the same event multiple times.
5. Monitor outbox backlog, retry counts, age of undelivered events, and audit store health.

**Conceptual SQL example** (table/column names and row-count checks depend on the application; not a standalone runnable script):

~~~sql
BEGIN;

-- Only record SUCCESS after checking permissions and valid state change.
UPDATE orders
SET status = 'APPROVED'
WHERE id = 42 AND status = 'PENDING';

-- The application must verify that exactly one row changed state.
-- In the same transaction, store the event for a worker to publish after commit.
INSERT INTO audit_outbox (
    event_id, action, actor_id, target_id, outcome
) VALUES (
    'evt-000042', 'ORDER_APPROVE', 'user-7',
    'order-42', 'SUCCESS'
);

COMMIT;
~~~

Do not run this example as-is without guaranteeing UPDATE row-count checks and business constraints. If the UPDATE fails or permissions are insufficient, the transaction must handle it accordingly and not emit a false `SUCCESS` event.

**Auditing a denied attempt** differs from auditing a committed change: unauthorized access attempts need to be recorded even when no data-modifying transaction occurs. Design an appropriate write path for failed attempts while still avoiding false `SUCCESS` records.

The transactional outbox guarantees atomicity between the business change and **writing to the outbox within the same database transaction**. It does not by itself guarantee the external audit store receives the event immediately; therefore, retries, lag monitoring, idempotency, and recovery mechanisms are still required.

## 11. Protecting the audit channel: permissions, integrity, and sensitive data

Separating files only has practical value when audit control policies are also separated accordingly.

### 11.1. Access permissions

- Only required components may **write** audit records; **read**, export, and query permissions follow roles.
- Application administrators should not by default have permission to delete/modify finalized audit stores, if audit requirements demand separation of duties.
- Secure the connection from the application to the collector/audit store, authenticate the source, and restrict service account privileges.
- Querying, downloading, changing retention, or modifying audit configuration may themselves need to be audited.

### 11.2. Integrity and tamper resistance

Options depending on risk level include **append-only/WORM** storage, separated permissions, per-batch or per-record signing or HMAC, key-managed hash chains with trusted timestamps, periodic integrity checks, and separately protected replicas.

A plain hash chain can detect changes in a finalized dataset, but **is not enough against an attacker with permission to rewrite the entire chain**; you must protect verification anchors/keys and store access. Standard `RollingFileAppender` files do not provide these guarantees.

### 11.3. Do not collect secrets

Never log passwords, access tokens, API keys, session cookies, private keys, full card numbers, sensitive data, or raw request bodies into audit logs. Store only the minimum fields needed to verify accountability; use appropriate IDs/pseudonyms and structured redaction when needed.

Never take `actorId` from an arbitrary client-sent header without authentication. Message data containing newlines or control characters must be encoded/sanitized to prevent **log injection**—forging fake lines that corrupt evidence. For JSON audits, use a reliable serializer instead of manual string concatenation.

Retention must be decided based on audit needs, privacy, and applicable regulations; a longer period is not automatically safer. Define policy-driven deletion, backups, and recovery procedures for appropriate legal/operational scenarios.

## 12. Handling audit channel failures

A clear policy must answer what happens when the audit sink is unavailable:

| Scenario | Possible consequence | Required handling |
| --- | --- | --- |
| Audit file runs out of disk space or lacks write permission | Appender fails or stops saving | Detect error, raise separate alert, follow policy-based recovery |
| Async audit queue is full | Drop, block, or fallback per configuration | Do not use a drop policy for mandatory events unless permitted |
| Collector/audit store loses connection | Events delayed or lost without a durable queue | Bounded retries, durable queue/outbox, backlog monitoring |
| Process is killed between enqueue and flush | Event was created but not persisted durably | Do not treat successful enqueue as long-term storage proof |
| Consumer receives duplicates due to retries | Multiple records for the same event | Deduplicate by `eventId`, retain attempt metadata |
| Clock skew between services | Hard to reconstruct action sequence | UTC, time synchronization, business sequence/version when needed |

Two policy styles are commonly considered:

- **Fail-open with durable buffered writes:** business operations continue if the audit collector is temporarily down, but events must be durably saved in an outbox for later delivery. A "skip when unable to audit" path does not satisfy mandatory audit requirements.
- **Fail-closed:** reject certain sensitive actions if evidence cannot be recorded per policy. This protects audit obligations but impacts availability; decide based on risk and regulation rather than applying it mechanically to every request.

Audit write failures should not be reported solely through **the failing audit logger itself**. Independent metrics/health checks/alerts are needed—for example, `audit_outbox_backlog`, `audit_delivery_failures`, `oldest_pending_event_age`, and evidence checks at the destination store.

## 13. Testing routing and completeness

A good test suite must prove both **presence in the right place** and **absence from disallowed places**.

### 13.1. Log routing matrix

Assuming `APP_FILE` is the root appender and `AUDIT_FILE` belongs to the `audit.events` logger with `additivity=false`:

| Input event | APP_FILE | AUDIT_FILE |
| --- | --- | --- |
| Application logger: INFO request completed | Yes | No |
| Application logger: ERROR downstream failure | Yes | No |
| `audit.events` logger: INFO ORDER_APPROVE | No | Yes |
| `audit.events` logger: INFO ACCESS_DENIED | No | Yes |
| `audit.events` logger: DEBUG diagnostic | No | No if audit level=INFO |

**Note:** If auditing is mandatory, do not let event creation depend on developers remembering to pick the right `DEBUG`/`INFO` level. Use an `AuditService` API with uniform rules, validation, and tests covering event codes.

### 13.2. Key tests

1. **Routing:** emit one business event and one audit event, wait for sinks to flush, and compare each destination.
2. **No duplication:** intentionally enable `additivity=true` in a test environment to observe audit events appearing in root as well; then verify the real configuration produces no unwanted records.
3. **No silent loss:** verify the audit logger is not set to `OFF`/`ERROR` by profile configuration or runtime changes.
4. **Schema:** `eventId`, `action`, `actor`, `target`, `outcome`, `timestamp`, and `correlationId` have valid formats/types; required fields are non-null.
5. **Data provenance:** `actor` is authenticated and cannot be spoofed via headers; newline characters in input fields cannot inject fake records.
6. **Permission separation:** someone authorized only to view `application.log` cannot by default read or modify `audit.log`.
7. **Downstream failure:** simulate disk full or collector timeout in a test environment; verify retries, backlog, alerts, and fail-open/fail-closed policy.
8. **Crash/Restart:** verify events committed to the outbox survive a restart and are delivered with the exact same `eventId`.
9. **Retry/dedup:** send the same `eventId` multiple times; ensure the destination store does not create multiple logical events, while still recording separate retry metadata if needed.
10. **Queryability:** reconstruct a sample action sequence from audit events and cross-check it against the final business state.
11. **Retention and recovery:** test file rotation/archival, backups, deletion permissions, and recovery procedures per policy.

If the backend writes asynchronously or the collector has indexing latency, wait for processing and controlled flushing before concluding an event is missing. Do not use `COUNT(*)` across all application log lines to test audit completeness; count by `eventId` or by the list of required actions.

## 14. Common design mistakes

### Only attaching an AUDIT marker and sharing the same appender

A marker is just metadata; without corresponding filters/routing or a separate sink, logs can still end up in `application.log`. With many developers, someone forgetting the marker can cause mandatory audit events to be lost. Use a dedicated API and enforcing tests.

### Having an audit.log file and assuming audit requirements are met

A file can be edited/deleted, lost when a container is replaced, unflushed on crash, or written concurrently by multiple instances. You need access policies, durable storage, event preservation, and integrity matching your requirements.

### Setting additivity=false but forgetting the appender

The audit logger stops at its own branch. If `AUDIT_FILE` is not attached or the appender is misconfigured, audit events may not appear anywhere. Test each actual event end-to-end to its destination.

### Setting additivity=true and accidentally leaking audit logs to a shared console

Audit events can flow through `APP_FILE` or root stdout, exposing records with sensitive fields into systems with broader access. Check both local logs and centralized collectors, where streams might be merged back into a single index.

### Writing audit events before the transaction commits

If a `SUCCESS` audit event is sent to an external system before the business transaction commits, the transaction may roll back while the evidence still claims success. Write to an outbox in the same transaction, or explicitly design separate `ATTEMPT` and `COMMITTED_OUTCOME` event types.

### Using correlationId as eventId

One request can produce multiple audit actions, so using the same `correlationId` as a unique key will overwrite or drop events. `eventId` identifies each individual event; `correlationId` links events in the same flow.

### Using log level to decide whether auditing is needed

An important action can be `SUCCESS` at `INFO`; a technical `ERROR` stack trace is not an audit record. Classify by `action`/`eventCode` and business requirements, not by message severity.

### Auditing only successful events

Denied access attempts, failed permission changes, unauthorized queries, or disallowed configuration changes can be more important than some successful operations. Clearly define mandatory audit events for `SUCCESS`, `DENIED`, and `FAILED`.

### Logging excessive payloads

Log data can be replicated across backups and multiple search systems. Never log raw requests/responses, tokens, passwords, or sensitive data; keep only minimal classified information.

## 15. Implementation checklist

- [ ] Maintain an audit event code catalog and distinguish audit logs from application logs.
- [ ] Every event includes `eventId`, `timestamp`, trusted `actor`, `action`, `target`, and appropriate `outcome`.
- [ ] The application has an `AuditService` or an easily testable mandatory event-emission convention.
- [ ] The audit logger and appender/destination are declared separately; `additivity` is configured intentionally.
- [ ] Verified that audit events do not leak into `application.log` or get dropped by filters/levels.
- [ ] Audit logs have appropriate read/write/delete permissions, encryption, retention, and tamper-resistance policies.
- [ ] No secrets or unnecessary personal data are logged; log injection is tested.
- [ ] When transactional durability is needed, use an outbox or equivalent mechanism and deduplicate by `eventId`.
- [ ] Independent alerts exist for write failures, backlog, retries, and delayed events.
- [ ] Tested rollback, `DENIED`, retries, crash, disk full, collector outage, and recovery.
- [ ] Can reconstruct the audit action sequence from records stored at the destination.

**Key takeaway:** Proper audit log separation consists of **event classification**, **separate routing**, and **distinct retention/control policies**. Loggers and appenders separate log streams; when audit records are mandatory evidence, you also need durable persistence, integrity verification, and recovery procedures.

## References

- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): distinguishing logging goals, security/audit events, data fields, sensitive information, and log protection.
- [Logback Manual — Architecture](https://logback.qos.ch/manual/architecture.html): logger hierarchy and additivity.
- [Logback Manual — Appenders](https://logback.qos.ch/manual/appenders.html): `FileAppender`, `RollingFileAppender`, and `TimeBasedRollingPolicy`.
- [Apache Log4j 2 — Configuration](https://logging.apache.org/log4j/2.x/manual/configuration.html): `Logger`, `Root`, `AppenderRef`, and additivity.
- [Apache Log4j 2 — Architecture](https://logging.apache.org/log4j/2.x/manual/architecture.html): event flow and appender inheritance rules.
- [Oracle Java SE 17 — java.util.logging](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/package-summary.html): logger and handler used in the standalone example.
