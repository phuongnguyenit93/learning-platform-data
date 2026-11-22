# What Is an Audit Log? — Java Core Logging

## 1. Concept and Purpose

An **audit log** (audit trail or action tracking log) is a collection of structured records that indicate **who or what component performed or attempted to perform which action, on which target, when, in what context, and with what outcome**. Audit logs provide accountability for actions that are significant to security, authorization, business operations, and system governance.

Examples that should be recorded include an administrator granting access permissions, a user failing to log in, a service changing configuration that affects customers, or an important record being deleted. This is not merely about “whether the application is running well,” but about maintaining an **action history that can be verified and reconciled later**.

A simple audit event:

~~~text
time=2026-01-15T10:00:00Z
actor=operator-1
action=VIEW_REPORT
target=report-42
outcome=ALLOWED
request=req-001
~~~

The identifiers here are dummy examples. `actor` and `target` can still be linked to real individuals or sensitive assets, so access control and retention periods must be enforced.

Audit logging typically supports:

- **Accountability:** explaining who performed an action, including failed or denied attempts.
- **Security investigation:** reconstructing the sequence of actions when privilege abuse, anomalous logins, or unexpected configuration changes are suspected.
- **Change history:** identifying which changes occurred prior to an incident.
- **Operational review:** supporting reconciliation of critical actions across systems.
- **Compliance and governance:** providing evidence under applicable policies and obligations. An audit log is only **one part** of a compliance process and does not automatically prove that a system complies with all regulations.

**An audit log is not a copy of all business data.** Its job is to record enough information to identify and verify an action—not to store raw passwords, tokens, HTTP bodies, or every before/after value of an object.

## 2. Distinguishing Audit Logs, Application Logs, Access Logs, Traces, and Business Events

| Data Type | Primary Question | Examples |
| --- | --- | --- |
| **Audit log** | Who did/attempted what, affecting which target, and with what outcome? | `ROLE_GRANTED`, `LOGIN_DENIED`, `CONFIG_CHANGED` |
| **Application/diagnostic log** | How did the program execute, and where did an error occur? | `Database timeout after 2 retries` |
| **Access log** | How did an HTTP request pass through a server or proxy? | Method, path, response status, latency |
| **Distributed trace** | Which services/spans did a request traverse, and how long did each take? | Trace ID, span, duration |
| **Business event** | What happened in the business domain for other systems to process? | `OrderPlaced` on a message broker |
| **Metric** | What is the aggregated count, rate, or latency? | `login_failures_total` |

A single action can produce **multiple types of signals**, but they do not replace one another.

For example, when an administrator grants a role:

- The application log might record “role service completed in 23 ms”.
- The audit log records “actor A granted role R to target B, outcome SUCCESS, under request X”.
- A business event may notify other systems to update permissions or send an alert.
- A trace shows the call path from the API to the database.

Merely seeing HTTP `200` in an access log does not guarantee that the permission change completed; merely seeing an `INFO` message does not prove that the audit record was durably stored.

**Distinguishing an audit log from a transaction ledger:** in financial domains, a ledger is business data governed by its own balancing and transaction rules. An audit log can prove who approved a transaction or who modified a setting, but it does not replace transaction records, ledgers, or financial auditing mechanisms.

## 3. Which Actions Should Have Audit Events?

Design the event catalog based on risk and business requirements rather than a habit of “logging everything.” Typical categories include:

1. **Authentication and login:** successes, failures, account recovery requests, and changes to authentication factors.
2. **Authorization:** granting/revoking roles, changing access permissions, and modifying authentication policies.
3. **Critical data operations:** creating/modifying/deleting records with legal or operational impact; bulk data exports.
4. **System administration:** modifying security configuration, locking accounts, and creating/revoking technical access credentials.
5. **Sensitive resource access:** opening private reports, accessing restricted data, and actions denied by policy.
6. **Audit operations:** changing audit collection configuration, detecting audit write failures, and modifying retention or log read permissions.

Not every event requires the same level of detail. Clicking a routine UI button may not belong in a long-term audit trail; accessing a particularly sensitive record may require stronger evidence. **You must specify which event types must record both successes and failures.**

For example, a denied login attempt still has audit value. If you only log successful operations, investigating privilege probing or unauthorized access will lack crucial evidence.

## 4. Which Fields Should an Audit Event Contain?

A practical schema typically includes the following groups of fields:

| Group | Suggested Fields | Purpose |
| --- | --- | --- |
| **Time** | `occurredAt` (UTC), ingestion/write timestamp when needed | Identify when the action occurred |
| **Actor** | `actorId`, actor type (user/service), tenant if applicable | Who performed or attempted the action |
| **Action** | `action` encoded as an enum or standard vocabulary | What action was performed |
| **Target** | `resourceType`, `targetId` | What was affected |
| **Outcome** | `outcome`, controlled `reasonCode` | Whether it succeeded, failed, or was denied |
| **Correlation** | `requestId`, `traceId` when appropriate | Link events belonging to the same request |
| **Source** | `service`, `component`, `environment`, `schemaVersion` | Who emitted it and in what format |
| **Additional context** | Delegation level, normalized change scope | Explain the decision when needed |

These fields are **not a mandatory checklist for every system**. An action executed by a batch job might not have a user ID; in that case, `actorType=SERVICE` and an appropriate service identifier are far more valuable than fabricating a “user”. You must also identify which fields constitute personal data and who is permitted to view them.

A stable event naming convention:

~~~text
LOGIN_SUCCEEDED
LOGIN_DENIED
ROLE_GRANTED
ROLE_REVOKED
REPORT_VIEWED
CONFIG_CHANGED
EXPORT_REQUESTED
AUDIT_DELIVERY_FAILED
~~~

Event names should describe an event that occurred, using consistent tense and semantics. Keep `action` and `outcome` separate if you want to aggregate both allowed and denied actions without proliferating near-duplicate event names.

**For actions that produce changes:** `oldValue/newValue` or the set of changed fields may be needed, but you should not dump the entire object. To reduce privacy risk, many systems record only `changedFields` (a list of field names), a change ID, or a version ID, and store full details in a separately access-controlled business store.

## 5. Key Properties of Reliable Audit Logging

A single line of text in `app.log` is not enough to form a reliable audit trail. Consider the following properties:

### 5.1. Completeness — not missing critical events

If audit events are lost during configuration reloads, full queues, unwritable files, or collector disconnections, the history becomes incomplete. The design should clearly define:

- Which events must be durably recorded before allowing the business operation to proceed?
- Is losing audit events acceptable for low-risk operations?
- If the audit store is unavailable, does the application **reject the operation (fail closed)**, durably persist to a queue/outbox, or allow continuation with an alert?
- Are the count, age, and latency of pending events measured alongside delivery failure counts?

There is no single choice that fits every case. For highly sensitive operations, succeeding while silently ignoring an audit write failure can violate design requirements.

### 5.2. Integrity — detecting unauthorized modification or deletion

An audit trail often needs protection against tampering, deletion, or unauthorized edits. Measures may include:

- Granting **append-only permissions** to the writer component; application users must not be able to modify records.
- Separating application administrators from audit store administrators.
- Shipping to a centralized service or immutable/WORM storage when required.
- Using hash chains, digital signatures, or appropriate attestation mechanisms to **detect** tampering; protecting and anchoring reference digests elsewhere.
- Running periodic integrity checks and alerting on anomalies.

**Note:** writing to a file with `APPEND` does not automatically make the file immutable. Anyone with sufficient OS privileges can still edit or delete it. A hash stored in the same file as the data can also be modified simultaneously if there is no trusted external verification mechanism.

### 5.3. Availability, retention, and searchability

Records must remain queryable for as long as needed; however, **retaining them too long** increases data exposure risk, cost, and operational liability. Establish a retention policy based on purpose, industry requirements, and applicable regulations—covering backups, replicas, search indexes, and logs exported to other systems.

### 5.4. Time and event ordering

Store timestamps in an easily comparable standard format, such as UTC `Instant` in ISO-8601, but **timestamps alone are not sufficient to prove absolute ordering in distributed systems**. Clocks across machines can drift; two events can share the same timestamp or arrive out of order.

When necessary, include a sequence number, event ID, position in an event stream, collector ingestion timestamp, or transaction identifier. Synchronizing server clocks helps reduce drift; never rely on arbitrary client-supplied timestamps as the sole source of truth.

### 5.5. Do not assume “exactly once”

Networks, retries, and queues can cause an audit event to be **delivered multiple times** or appear duplicated. If the collector/consumer uses at-least-once delivery, design a unique `eventId` and handle deduplication appropriately. “Exactly-once recording” across multiple systems is a separate problem and does not emerge automatically from calling a logger API once.

## 6. Standalone Java 17 Example: Writing Audit Events with a Fixed Schema

This example uses **plain JDK 17** with no Maven/Gradle or external libraries. We create a small writer dedicated to appending audit events to a separate file, keeping them distinct from diagnostic logs. Each event carries only predetermined fields rather than calling `toString()` on the entire request.

**Limitations of this example:** the writer uses `Files.writeString` to demonstrate event construction and appending; it is **not** a production implementation that satisfies tamper resistance, transactionality, deduplication, multi-JVM concurrent writing, or crash/power-loss durability. Later sections explain how to extend it.

Create **`AuditLogDemo.java`**:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.Objects;

public class AuditLogDemo {

    enum Action { VIEW_REPORT }
    enum Outcome { ALLOWED, DENIED }

    record AuditEvent(
            Instant occurredAt,
            String actorId,
            Action action,
            String targetId,
            Outcome outcome,
            String requestId) {}

    static final class AuditWriter {
        private final Path file;

        AuditWriter(Path file) {
            this.file = Objects.requireNonNull(file);
        }

        private static String validatedId(String field, String value) {
            if (value == null
                    || !value.matches("[A-Za-z0-9._-]{1,64}")) {
                throw new IllegalArgumentException("Invalid " + field);
            }
            return value;
        }

        synchronized void append(AuditEvent event) throws IOException {
            Objects.requireNonNull(event, "event");

            String entry =
                    "time=" + Objects.requireNonNull(event.occurredAt())
                    + " actor=" + validatedId("actorId", event.actorId())
                    + " action=" + Objects.requireNonNull(event.action())
                    + " target=" + validatedId("targetId", event.targetId())
                    + " outcome=" + Objects.requireNonNull(event.outcome())
                    + " request=" + validatedId("requestId", event.requestId());

            Files.writeString(
                    file,
                    entry + System.lineSeparator(),
                    StandardCharsets.UTF_8,
                    StandardOpenOption.CREATE,
                    StandardOpenOption.WRITE,
                    StandardOpenOption.APPEND);
        }
    }

    public static void main(String[] args) throws IOException {
        Path directory = Path.of("logs");
        Files.createDirectories(directory);

        // Create a new demo file on each run without deleting old audit files.
        Path file = Files.createTempFile(
                directory, "audit-demo-", ".log");

        // Fixed clock only to keep the demonstration output unchanged.
        Clock clock = Clock.fixed(
                Instant.parse("2026-01-15T10:00:00Z"),
                ZoneOffset.UTC);

        AuditWriter writer = new AuditWriter(file);
        writer.append(new AuditEvent(
                Instant.now(clock),
                "operator-1",
                Action.VIEW_REPORT,
                "report-42",
                Outcome.ALLOWED,
                "req-001"));

        writer.append(new AuditEvent(
                Instant.now(clock),
                "operator-2",
                Action.VIEW_REPORT,
                "report-99",
                Outcome.DENIED,
                "req-002"));

        System.out.println("eventsWritten=2");
        Files.readAllLines(file, StandardCharsets.UTF_8)
                .forEach(System.out::println);
    }
}
~~~

Compile and run in a directory where you have permission to create directories and files:

~~~bash
javac AuditLogDemo.java
java AuditLogDemo
~~~

**Exact stdout** (with JDK 17+ and no I/O errors):

~~~text
eventsWritten=2
time=2026-01-15T10:00:00Z actor=operator-1 action=VIEW_REPORT target=report-42 outcome=ALLOWED request=req-001
time=2026-01-15T10:00:00Z actor=operator-2 action=VIEW_REPORT target=report-99 outcome=DENIED request=req-002
~~~

**Stderr:** empty on success. The actual file is created in the `logs` directory with a name starting with `audit-demo-` and ending in `.log`; the middle portion is generated automatically and is not fixed. The program reads the file back and prints both audit events to stdout for inspection. In a real application, you should not automatically print the entire audit trail to the console like this; it is shown here purely for lesson verification.

### Code Explanation and Safety Boundaries

- `AuditEvent` is a **structured record**. `Action` and `Outcome` use enums to prevent arbitrary free-text descriptions that are hard to aggregate.
- `Instant` represents a point in time in UTC; `Clock.fixed` is used solely for deterministic demo output. In real runtime code, obtain time from a managed and clock-synchronized system clock.
- `validatedId` restricts the length and character set of identifiers. This reduces the risk of log injection via newlines and avoids logging untrusted input verbatim; **it does not anonymize the actor ID**.
- `Files.writeString(... CREATE, WRITE, APPEND)` appends a line to the target file. `synchronized` only serializes calls on the **same `AuditWriter` instance** and does not lock across other writers or OS processes.
- On an I/O error, the method throws `IOException` so the caller knows the audit operation failed; it **does not silently drop the event**. A real service must define how business logic handles that failure.
- The program does not record full names, emails, passwords, tokens, or HTTP bodies in the audit event; it uses dummy identifiers for illustration only.
- `Files.createTempFile` creates a new file per run so previous test runs are not overwritten. A temporary file with such permissions, storage layout, and lifecycle should not be used as a production audit store.

**Important:** this program simulates two access decisions and **does not actually perform resource authorization checks**. It illustrates the schema, not proof that a business operation succeeded or committed. In a real system, `outcome` must come from the verified result of the authorization or business mechanism.

## 7. How to Ensure Audit Logs Accurately Reflect Business Outcomes

Suppose an API changes a user's permissions. If the application logs “ROLE_GRANTED” **before** the database commits, and the transaction subsequently rolls back, the audit event will be false. If it only logs **after** the commit, and the process crashes before sending the audit event, the change took effect while the audit record is missing.

~~~text
Option A:
write audit -> business commit
                  |
           commit fails -> false "success" log

Option B:
business commit -> write audit
                         |
               app crash -> missing audit

Option C (when transactional consistency is required):
business transaction + write outbox record
                  |
                commit
                  |
          worker reads outbox
                  |
         audit store / collector
~~~

The **transactional outbox** pattern is an option when business data and the outbox share the same transactional database. Upon commit, the business change and a record stating “an audit event must be emitted” are persisted atomically within that database boundary. A worker then forwards the record to the audit store with retries and deduplication. This approach increases reliability around **recording the intent to emit an event**, though you still must handle disconnections, backlogs, duplicate deliveries, outbox cleanup, and destination acknowledgments.

Do not conclude that “using an outbox guarantees exactly-once auditing.” If the worker delivers successfully and crashes before marking the record as sent, the same event can be re-sent. Therefore, use a stable event ID to deduplicate at the receiver according to a clear policy.

Some operations (such as **denied access**) do not create a successful business transaction yet still require auditing. In those cases, you need an independent mechanism to record `DENIED` events rather than placing all auditing exclusively after a successful commit branch.

## 8. Audit Logs and Java Logging Backends

### 8.1. Java Util Logging (JUL)

`java.util.logging.Logger` and `Handler` can route events to a file or a dedicated destination. Integration snippet:

~~~java
// Integration snippet; AUDIT_LOGGER is already configured with a dedicated handler.
AUDIT_LOGGER.info("action=VIEW_REPORT outcome=DENIED request=req-002");
~~~

This is only an integration snippet, not a standalone runnable application. If you use JUL as an audit channel, ensure that:

- The logger has an appropriate level and filter so events are not accidentally dropped by global level changes.
- The audit handler/destination is configured separately if its policy differs from diagnostic logs.
- Handler write failures are observable: some logging APIs report errors differently rather than throwing exceptions back to the caller.
- Rotation, retention, and shutdown do not lose required history.

**Never assume that `Logger.info` returning normally means the audit event was durably persisted.** When strict success/failure semantics are required, use an API/writer or audit infrastructure with an explicit acknowledgment contract.

### 8.2. SLF4J with Logback or Log4j 2

SLF4J is a facade. Logback and Log4j 2 typically provide appenders, encoders, filters, async queues, routing, and log separation mechanisms. An audit configuration can route by logger name or marker, for example:

~~~java
// Illustrative snippet requiring SLF4J and a configured backend.
// Has no special audit behavior unless the backend routes it separately.
org.slf4j.Logger auditLogger =
        org.slf4j.LoggerFactory.getLogger("audit.events");
auditLogger.info("action={} target={} outcome={}",
        "VIEW_REPORT", "report-42", "ALLOWED");
~~~

**Naming a logger `audit.events` does not automatically create a reliable audit trail.** You must configure the backend, guarantee transport, write permissions, event completeness, error reporting, and retention.

An appender that writes the same event to both the console and a remote collector can produce duplicates if the collector also scrapes console output. Each delivery path must have a clear purpose; critical audits typically require a dedicated store with stricter permissions and policies than diagnostic logs.

## 9. Security and Privacy of the Audit Trail

Because audit events have high investigative value, they often contain actor IDs, target IDs, timestamps, and context. These data points can **link back to real individuals**, even when names and emails are omitted.

### Fields to Avoid

- Passwords, access tokens, refresh tokens, cookies, secrets, and encryption keys.
- Raw request/response bodies, entire DTOs, or authentication headers.
- Identifying, financial, or health fields not required for auditing purposes.
- Unreviewed exception messages, which sometimes contain file paths, query parameters, or user data.
- Full “before/after” snapshots of sensitive documents when recording only the changed field names or a version ID suffices.

### Protecting the Storage System

1. **Minimize at the source:** only record fields approved by the schema.
2. **Access control:** separate audit writers, readers, and store administrators.
3. **Protect in transit and at rest:** use encryption and key management mechanisms appropriate to the system.
4. **Tamper resistance:** append-only permissions, immutable storage, and integrity verification when required.
5. **Retention and deletion:** define storage locations, replicas, backups, purpose, retention limits, and applicable obligations.
6. **Protect correlation:** request/trace IDs can link data across sources; never use authentication tokens as correlation IDs.

Masking or hashing a field does not automatically make it “non-personal data.” If a token or pseudonym can still be linked to an identity through another system, it must still be managed according to applicable risks and rules.

## 10. Deployment Architectures: Files, Queues, and Centralized Stores

Three common models:

| Model | Strengths | Limitations to Address |
| --- | --- | --- |
| **Dedicated local audit file** | Easy to deploy, easy to inspect locally | Edit/delete permissions, rotation, disk full, multi-process writes, backups |
| **Queue or outbox + worker** | Decouples business latency from exporter, supports retries | Queue/backlog growth, deduplication, acknowledgments, and shutdown |
| **Centralized audit service/store** | Search, access control, retention, and cross-service aggregation | Network dependency, availability, cost, access policies |

In systems with multiple replicas or microservices, writing to local files per container makes distributed tracing harder without a collector and durable storage. Conversely, **pushing logs to stdout for a collector to scrape** does not by default provide delivery or integrity guarantees suitable for sensitive audits.

An observable audit pipeline:

~~~text
Producer (Java service)
        |
        v
Validate schema / generate event ID
        |
        v
Durable handoff (when required)
        |
        v
Transport / worker / retry
        |
        v
Audit store with access + integrity controls
        |
        v
Search / investigation / retention / verification
~~~

Where queues or workers exist, measure `pending_count`, oldest event age, failed delivery count, retry count, discard rate, and any discrepancy between expected business operations and recorded audit events.

## 11. Failure Modes and Application Responses

| Scenario | Consequence | Mitigation to Consider |
| --- | --- | --- |
| Disk full or permission denied | Audit append fails | Never swallow errors; enforce explicit fail-closed/outbox policy |
| Collector down or timeout | Events do not reach destination | Controlled retries, temporary durable storage, and backlog alerts |
| Async queue full | Events may be dropped or callers blocked | Define an explicit policy for critical audit events |
| Process `SIGKILL` / power loss | In-memory buffers/queues may be lost | Persist durably before returning success when strictly required |
| Event resent after timeout | May create duplicate records | Stable event ID and idempotent consumer |
| Machine clock drift | Event ordering is hard to reconcile | Clock synchronization, ingestion timestamps, sequence/correlation IDs |
| Privileged user edits file | Audit trail is no longer trustworthy | Separation of duties, immutable store / integrity verification |
| Retention too short | Missing evidence during investigations | Policy aligned with operational needs and obligations |
| Retention too long | Increased privacy risk and storage cost | Retention limits, classification, and replica management |
| Audit only logs `SUCCESS` | Denied attempts are invisible | Log `DENIED`/`FAILED` within the designed scope |
| Logs contain sensitive data | Leakage via files, dashboards, backups | Field allowlist, no secrets logged, test export paths |

**Note on shutdown hooks:** a hook can help drain queues, flush buffers, and close resources during an orderly JVM shutdown, but it cannot save logs when the process is forcibly killed or the host crashes. For mandatory audit events, durability must be designed into **runtime execution**, not only at shutdown.

## 12. Purpose-Driven Testing for Audit Logging

Beyond unit tests checking whether a logger was called, verify **queryability and consistency with actual outcomes**:

1. A successful action generates the expected event type, actor, target, outcome, and request ID.
2. A `DENIED`/`FAILED` action also emits an event when policy requires it.
3. A rolled-back business transaction does not emit a false `SUCCESS` event; if attempts are logged, the outcome accurately reflects reality.
4. File/queue/collector write failure: the application reacts according to policy and emits metrics/alerts.
5. Worker resends the same event ID: does the receiver detect and handle duplicates as designed?
6. Under thousands of concurrent requests: do ordering, idempotency, and the writer remain correct?
7. Test downtime, reconnects, restarts, and shutdowns; compare expected event counts against confirmed stored events.
8. Identifiers or messages with newlines or unusual input: does the schema validator/encoder prevent log injection?
9. No secrets or non-allowlisted PII appear in any destination, including exception paths and tested backups.
10. Test read/write/edit/delete permissions per role; verify tamper-detection mechanisms if implemented.
11. Verify retention policies and investigative queries by actor, action, target, and event ID.
12. When the schema version is bumped, can older consumers still read or safely migrate events?

**A useful verification test** is reconciling the number of auditable operations against the number of audit records by event ID—distinguishing unsent, rejected, duplicated, and confirmed-stored events. Line counts in a single text file are insufficient to prove completeness when multiple appenders or collectors are involved.

## 13. Common Misconceptions

**“If the application has INFO logs, it has an audit log.”** False. Diagnostic logs may lack actor/target/outcome, be suppressed by log-level changes, or live only in ephemeral files.

**“Appending to a file makes it impossible to edit or delete.”** False. An API's append mode does not equate to immutability at the access-control or storage-system level.

**“The more data we log, the better the audit.”** False. Over-logging increases privacy risk, adds search noise, and creates unnecessary copies.

**“Denied attempts don't need to be logged.”** False whenever policies require investigating unauthorized access attempts. `DENIED` events can be critical evidence.

**“UTC timestamps always reflect exact system-wide ordering.”** False. You must account for clock drift, retries, network delays, and asynchronous processing.

**“Calling `auditLogger.info()` guarantees the event was saved.”** False. You must examine delivery semantics, failover, queues, write acknowledgments, and backend error visibility.

**“An audit log alone satisfies all compliance requirements.”** False. Compliance also involves access controls, personal data handling, investigation workflows, retention, and jurisdiction-specific requirements.

## 14. Audit Log Design Checklist for Java Projects

- [ ] Clearly define the purpose and catalog of auditable actions, including `FAILED`/`DENIED` when needed.
- [ ] Create a versioned schema with appropriate actor, action, target, `occurredAt`, outcome, and correlation fields.
- [ ] Never log full objects, request payloads, or secrets; classify PII and minimize at the source.
- [ ] Separate audit events from diagnostic logs, access logs, and business events.
- [ ] Define when events are recorded relative to business state changes, commits, and rollbacks.
- [ ] Specify how audit pipeline failures are handled: surface errors, halt the operation, outbox/retry, or another approved strategy.
- [ ] Design deduplication using event IDs and idempotency rules for retries.
- [ ] Define append-only requirements, integrity verification, and access controls for the audit store.
- [ ] Synchronize clocks and include timestamps/sequences suited for distributed systems.
- [ ] Ensure retention, backups, and searchability align with applicable policies.
- [ ] Monitor backlogs, drops, timeouts, and recorded event counts.
- [ ] Test failure modes, access controls, sensitive data exposure, and outcome accuracy.

### Self-Check Questions

**1. What questions does an audit log answer?**  
Who/what performed or attempted what action, on which resource, when, with what outcome, and in relation to which request.

**2. Why not just use `logger.info("Role changed")`?**  
Because it lacks actor, target, outcome, correlation, and the persistence/storage guarantees an audit trail may require.

**3. If the database rolls back after logging “ROLE_GRANTED SUCCESS”, what went wrong?**  
The audit event reports a completed change even though the business transaction never committed; you need proper write timing or an outbox pattern.

**4. Does `APPEND` mode in Java make a file immutable?**  
No. It only controls how the file is opened/written for that operation; it does not prevent privileged users from modifying or deleting it.

**5. Why should some denied access attempts be logged?**  
Because `DENIED` events help detect and trace unauthorized privilege probing.

**6. Should an access token be logged in an audit event to identify the actor?**  
No. Use an appropriate actor identifier or correlation ID; tokens are secrets and must be kept out of logs.

**Key takeaway:** An audit log is a **verifiable trail of actions**, not just diagnostic messages. A valuable audit trail requires a clear schema, accurate business outcomes, access controls, minimal data exposure, protection against loss and tampering, deduplication, and appropriate retention. In Java, calling a logger is only the signal-emission step; ultimate reliability comes from the entire pipeline that records and manages audit events.