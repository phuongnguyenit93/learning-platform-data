# Audit logging: What action occurred?

## 1. The core question of an audit event

In **audit logging**, the question “**What action occurred?**” aims to identify **the specific action an actor requested or the system performed on a target**, along with its outcome and scope. A record that only says “activity occurred” or “request succeeded” is not enough for accountability during an incident investigation.

Suppose we have a user management system:

- `user updated`: too vague — did the user change their name, change their password, or change permissions?
- `ROLE_GRANT`, `target=user:u-42`, `role=REPORT_VIEWER`, `outcome=SUCCEEDED`: indicates the **role-granting action**, the target, the specific role, and that the execution succeeded.
- `CUSTOMER_DATA_EXPORT`, `outcome=DENIED`, `reason=MISSING_PERMISSION`: indicates there was a **data export request**, but the system did not allow it. It must not be phrased as “data was exported”.

A useful audit event typically answers this set of questions:

| Question | Field/explanation |
| --- | --- |
| **What? — Which action?** | `action`, an operation type with clear business semantics |
| **Who? — Who?** | `actorId` from an authenticated identity source, or a service account |
| **On what? — Affected what?** | `targetType`, `targetId`, scope/resource |
| **When? — When?** | `occurredAt` (UTC, in a standard timestamp format) |
| **Where/how? — From where/via which channel?** | service, environment, client/source, API/automation |
| **Outcome? — Result?** | `SUCCEEDED`, `DENIED`, `FAILED`, `PARTIAL`, `PENDING` |
| **Why? — Reason or basis?** | `reasonCode`, ticket/approval, policy ID |
| **Which operation? — Which correlation?** | `eventId`, `requestId`/`correlationId`, `transactionId` |

The focus of this article is **What?**: representing an action precisely enough so that human readers, query engines, and auditors share the same understanding. The remaining fields help determine whether the action **actually took place**, who is accountable, on which data, and with what effect.

**Audit logs** differ from **debug/application logs**: audit records serve accountability for a noteworthy action; debug logs serve technical root-cause analysis. Not every `logger.info(...)` line becomes a trustworthy audit event.

## 2. Separating the “requested action” from the “completed action”

This is the most important principle to avoid a false audit trail.

```text
Receive EXPORT_CUSTOMER_DATA request
       |
       +--> authentication/authorization failed --> DENIED
       |
       +--> validation failed ---------------------> VALIDATION_FAILED
       |
       +--> processing started --------------------> PENDING / STARTED
                 |
                 +--> transaction committed -------> SUCCEEDED
                 +--> processing error ------------> FAILED
                 +--> partially completed ---------> PARTIAL
```

**Action** describes the type of operation, while **outcome** describes the result. For example:

| Action | Outcome | Accurate interpretation |
| --- | --- | --- |
| `GRANT_ROLE` | `SUCCEEDED` | The role was granted and the change was confirmed per the business contract |
| `GRANT_ROLE` | `DENIED` | A role-grant request occurred but was denied; must not claim the role was granted |
| `EXPORT_CUSTOMER_DATA` | `PENDING` | The data export request was accepted/is in progress; export is not yet confirmed |
| `EXPORT_CUSTOMER_DATA` | `SUCCEEDED` | The data export completed at the defined confirmation boundary |
| `DELETE_DOCUMENT` | `FAILED` | The delete operation did not complete as expected |
| `BULK_DISABLE_USERS` | `PARTIAL` | Some targets were changed; must include details or a link to the result list |
| `CHANGE_LOG_LEVEL` | `SUCCEEDED` | The target log level was updated and verified within the committed scope |

An operation may have **multiple lifecycle events** (attempt, started, result) sharing one `operationId`, or a single summary event with `requestedAction` and `outcome` fields. Either approach works if the convention is consistent; **never name an event `DOCUMENT_DELETED` when only checking permissions or receiving the request**.

Especially for asynchronous operations, HTTP `202 Accepted` usually only proves the request was accepted, not that the background job completed. Even an API’s HTTP `200` must be interpreted according to the API contract: it may be returned before data is synchronized across all downstream systems.

## 3. Naming actions in business language

Action names must be **stable, consistent, and queryable**, avoiding dependence on free-form message text.

A common convention uses verb + object:

```text
USER_LOGIN
USER_LOGOUT
PASSWORD_RESET_REQUEST
PASSWORD_RESET_COMPLETE
GRANT_ROLE
REVOKE_ROLE
CREATE_API_KEY
ROTATE_API_KEY
DISABLE_ACCOUNT
APPROVE_PAYMENT
REFUND_PAYMENT
EXPORT_CUSTOMER_DATA
DELETE_DOCUMENT
CHANGE_LOG_LEVEL
UPDATE_LOG_RETENTION
```

You can choose `ROLE_GRANTED` (past tense, indicating an event that happened) instead of `GRANT_ROLE` (command style) **if the schema is standardized and states are clearly documented**. Two design options:

1. **Command-style action:** `action=GRANT_ROLE`, `outcome=DENIED|SUCCEEDED`. Useful for covering all attempts.
2. **Event-style event type:** `eventType=ROLE_GRANTED`, emitted only after success; alongside `ROLE_GRANT_DENIED` or `ROLE_GRANT_ATTEMPTED` for other branches.

Do not mix the semantics of both styles arbitrarily. If `ROLE_GRANTED` is used both when a request arrives and when it commits, the audit data becomes contradictory.

### 3.1. Which names are specific enough?

| Vague name | Better name to consider | Why |
| --- | --- | --- |
| `UPDATE` | `CHANGE_USER_EMAIL` | Explicitly states the meaningful attribute |
| `ACCESS` | `READ_SENSITIVE_RECORD` | Distinguishes reading sensitive data from logging in |
| `LOGIN` | `USER_LOGIN` + outcome | Clarifies whether this was a login attempt or a success |
| `CHANGE_SETTING` | `CHANGE_LOG_LEVEL` | Identifies the exact policy modified |
| `TRANSACTION` | `REFUND_PAYMENT` | Explains the financial impact |
| `ADMIN_ACTION` | `REVOKE_ROLE` | Makes it possible to verify that a role was revoked |
| `DELETE` | `DELETE_API_KEY` | Associates accurately with the target type |

Do not split into countless actions for every unnecessary minor value. For example, `CHANGE_USER_EMAIL` can use `changedFields=["email"]` or `field=email`, but **do not** create a separate action for each email value. Configuration parameters and before/after values should be **attributes**, not embedded into the action name such as `SET_LEVEL_DEBUG_FOR_PAYMENT`.

### 3.2. Action catalog and schema versioning

Maintain an **action catalog** containing:

- Action code and semantic description.
- Condition for marking `SUCCEEDED`/completed.
- Target type and required fields.
- Trusted actor sources.
- Sensitivity level and scope requiring auditing.
- Rules for allowed data, retention, and alerting.
- Schema version if semantics/fields change.

For example:

```text
action: GRANT_ROLE
meaning: grant a role to an account
success_boundary: role-granting transaction committed
targetType: USER
required_context: actorId, targetId, roleCode, requestId, occurredAt, outcome
restricted_fields: password, sessionToken, fullProfile
```

An action name should preserve a single meaning across versions; when semantics change significantly, introduce a new schema version or a new action so historical queries are not misinterpreted.

## 4. Distinguishing action, object, field, and outcome

A sample audit event:

```json
{
  "schemaVersion": 1,
  "eventId": "evt-0001",
  "action": "GRANT_ROLE",
  "outcome": "SUCCEEDED",
  "actorId": "admin-7",
  "targetType": "USER",
  "targetId": "u-42",
  "attributes": {
    "roleCode": "REPORT_VIEWER"
  },
  "requestId": "req-100",
  "occurredAt": "2026-11-10T02:00:00Z",
  "service": "identity-service"
}
```

In this example:

- `action=GRANT_ROLE`: the **role-granting** operation.
- `targetType=USER`, `targetId=u-42`: the **target** receiving the role.
- `attributes.roleCode`: an **attribute** of the operation, not a new action type.
- `outcome=SUCCEEDED`: the operation **completed** according to the business contract.
- `occurredAt`: when the event occurred; the timestamp here is **illustrative**, not from a real system.
- `eventId` and `requestId`: identify the event and correlate it to the request; the two IDs do not need to be the same.

It is not necessary to log the entire user object. Audits usually need a stable ID, allowed fields, and **redacted/filtered** changed values. The sample record does not prove it was persisted durably or immutably; that is a separate pipeline requirement.

## 5. Which actions should be audited?

Do not log every getter call as an audit event. Select based on risk and investigative/compliance requirements, for example:

1. **Authentication:** successful/failed login, logout, MFA changes, password resets, revoked sessions.
2. **Authorization:** granting/revoking roles, policy changes, access permission changes, operations denied due to missing permissions.
3. **Sensitive data:** viewing, exporting, downloading, sharing, deleting, or restoring sensitive data, if required by policy.
4. **Critical changes:** enabling/disabling accounts, security configuration changes, logging/audit configuration, retention changes, API key management.
5. **High-risk financial and business operations:** approvals, refunds, transaction cancellations, payment detail changes, critical order state transitions.
6. **Infrastructure administration:** deployments, rollbacks, privileged access, changes to encryption policies and log destinations.
7. **Blocked attempts:** unauthorized access, insufficient-privilege operations, or policy-denied requests.

For high-volume read access events, clearly define the **scope of data to audit** to balance privacy, performance, and legal requirements. Sampling may be reasonable for telemetry, but **never arbitrarily sample mandatory audit events**.

When an operation combines multiple steps (for example, granting a role and then sending a notification email), only mark `GRANT_ROLE/SUCCEEDED` when the success condition for **granting the role** is met. Sending the email can be a separate `SEND_NOTIFICATION` event; an email failure does not automatically mean the role was not granted.

## 6. Java 17: standalone demo program for action and outcome

The following Java 17 example creates two audit events using `record` and `enum`, with deterministic output for easy verification:

- A completed **grant role** request.
- A **data export** request denied due to insufficient permissions.

The example uses fixed data and **does not claim real authentication/authorization** or database transactions. Its goal is to illustrate how to describe “what action occurred” with a structured action and a separate outcome.

Save the file as **`AuditActionDemo.java`**:

```java
import java.time.Instant;
import java.util.Objects;

public class AuditActionDemo {
    enum Action {
        GRANT_ROLE,
        EXPORT_CUSTOMER_DATA
    }

    enum Outcome {
        SUCCEEDED,
        DENIED,
        FAILED
    }

    record AuditEvent(
            String eventId,
            Instant occurredAt,
            String actorId,
            Action action,
            String targetType,
            String targetId,
            Outcome outcome,
            String reasonCode,
            String requestId) {

        AuditEvent {
            Objects.requireNonNull(eventId);
            Objects.requireNonNull(occurredAt);
            Objects.requireNonNull(actorId);
            Objects.requireNonNull(action);
            Objects.requireNonNull(targetType);
            Objects.requireNonNull(targetId);
            Objects.requireNonNull(outcome);
            Objects.requireNonNull(reasonCode);
            Objects.requireNonNull(requestId);
        }
    }

    static void emit(AuditEvent event) {
        // Fixed text output for learning purposes only: no durable audit sink.
        System.out.println("event=" + event.eventId()
                + " action=" + event.action()
                + " outcome=" + event.outcome()
                + " actor=" + event.actorId()
                + " target=" + event.targetType()
                + ":" + event.targetId()
                + " reason=" + event.reasonCode()
                + " request=" + event.requestId()
                + " time=" + event.occurredAt());
    }

    public static void main(String[] args) {
        emit(new AuditEvent(
                "evt-001",
                Instant.parse("2026-01-01T00:00:00Z"),
                "admin-7",
                Action.GRANT_ROLE,
                "USER",
                "u-42",
                Outcome.SUCCEEDED,
                "APPROVED",
                "req-100"));

        emit(new AuditEvent(
                "evt-002",
                Instant.parse("2026-01-01T00:00:01Z"),
                "analyst-5",
                Action.EXPORT_CUSTOMER_DATA,
                "DATASET",
                "customers",
                Outcome.DENIED,
                "MISSING_PERMISSION",
                "req-101"));
    }
}
```

Compile/run with JDK 17+:

```bash
javac AuditActionDemo.java
java AuditActionDemo
```

Exact **`stdout`** output:

```text
event=evt-001 action=GRANT_ROLE outcome=SUCCEEDED actor=admin-7 target=USER:u-42 reason=APPROVED request=req-100 time=2026-01-01T00:00:00Z
event=evt-002 action=EXPORT_CUSTOMER_DATA outcome=DENIED actor=analyst-5 target=DATASET:customers reason=MISSING_PERMISSION request=req-101 time=2026-01-01T00:00:01Z
```

Explanation:

1. `enum Action` constrains the example's action catalog, helping avoid arbitrary typos such as `"update"`.
2. `enum Outcome` separates **operation type** from **completion status**.
3. `record AuditEvent` creates a shallowly immutable model per record semantics; all fields in the example are immutable types.
4. `Objects.requireNonNull(...)` rejects missing fields but **does not replace business checks** such as whether the actor is authenticated, the action is authorized, or the target exists.
5. `Instant.parse(...)` provides a fixed timestamp. In a real application, timestamps come from a trusted clock with an explicit timezone.
6. The code prints a human-readable string but does not handle input escaping: if an actor or target from an untrusted source contains newlines, it can cause **log injection**. Production systems should use a safe JSON/structured log serializer, enforce length limits, and validate/sanitize control characters.
7. The two events are **simulated** to illustrate structure. `SUCCEEDED` is a mocked conclusion; in real business logic it must only be emitted after verifying the success condition.

This program does not require SLF4J, Logback, or a database. It demonstrates **event content**, not a tamper-resistant audit trail.

### 6.1. Why not just use `logger.info("Updated")`?

Messages without an action code, target, actor, and outcome are difficult to query:

```text
INFO Updated
INFO Done
ERROR Something failed
```

An audit query asking “how many data exports were denied?” would have to rely on a parser guessing from prose. With a schema like `action=EXPORT_CUSTOMER_DATA AND outcome=DENIED`, the system can count and analyze accurately without depending on message wording.

When using a logging framework, structured fields can be supplied through the corresponding API/encoder; do not assume every backend outputs JSON just because `logger.info` was called.

## 7. Emitting audit events at the right success boundary

### 7.1. Data changes within a transaction

Suppose `GRANT_ROLE` updates a database record. Logging `SUCCEEDED` **before commit** risks stating something false:

```text
BEGIN TRANSACTION
   UPDATE user_role
   log "GRANT_ROLE SUCCEEDED"
ROLLBACK (due to deadlock / constraint / exception)
```

The audit claimed the role was granted even though the transaction failed.

A stricter pattern:

```text
BEGIN TRANSACTION
   validate + authorize
   UPDATE role mapping
   INSERT audit/outbox record in the same transaction (if appropriate)
COMMIT
   -> only when commit succeeds do the business operation and corresponding event take effect
   -> publisher forwards the committed event to the audit system
```

The **Transactional outbox** pattern stores business state and the event in the same database transaction, narrowing the gap between updating business data and emitting an audit message. However:

- A publisher sending after commit may redeliver multiple times → consumers need idempotency keyed by `eventId`.
- If the database transaction rolls back, the outbox event also rolls back; if **failed attempts** must be recorded, they must use a separate audit path that does not roll back with the business transaction.
- If the external audit sink is down, committed outbox records need retry, backlog handling, monitoring, retention, and handling for a full outbox.
- Do not assume “inserted into outbox” means the audit system has ultimately received or durably stored the event.

If business logic only mutates in-memory state or calls a downstream API without a shared transaction with another sink, you need an explicit event contract and confirmation boundary—never attach `SUCCEEDED` based on assumptions.

### 7.2. Read operations that do not mutate state

For `VIEW_SENSITIVE_RECORD` or `EXPORT_CUSTOMER_DATA`, “success” must be defined by **the point at which data is accessed or delivered**:

- `ACCESS_REQUESTED`: the API request was recorded; data may not have been read yet.
- `AUTHORIZATION_DENIED`: blocked before reading.
- `RECORD_READ_SUCCEEDED`: data was retrieved according to system criteria, though the client may not have received it yet.
- `EXPORT_READY`: the export file was generated; not necessarily downloaded.
- `EXPORT_DOWNLOADED`: the system recorded a download under the active protocol; it cannot infer the user actually read the contents.

If a streaming transfer is interrupted mid-way, `PARTIAL` or a transfer-failure event may be more accurate than `SUCCEEDED`. Do not infer final status from an HTTP status code alone if the contract is insufficient.

## 8. Complex states: multi-step, asynchronous, and retries

A `REFUND_PAYMENT` operation may go through:

```text
Refund requested -> authorization approved
      |
      -> payment provider accepted
      |
      -> settlement completed / rejected
      |
      -> ledger updated
```

Therefore, define actions corresponding to each **business milestone**:

| Event/action | Meaning |
| --- | --- |
| `REFUND_REQUESTED` | Refund intent has been received |
| `REFUND_SUBMITTED` | Request has been sent to the provider |
| `REFUND_SETTLED` | Settlement proof has been received per contract |
| `REFUND_FAILED` | Workflow did not complete, with a standardized error code |

Do not mark `REFUND_SETTLED` upon merely receiving HTTP `202` from the provider. A provider may acknowledge the request and process it asynchronously; a subsequent webhook or response reveals the actual outcome.

### 8.1. Multiple events for one operation

Use distinct identifiers:

- `eventId`: unique for **each audit event**, used for idempotency.
- `operationId`: shared across **one business operation** spanning multiple steps.
- `requestId`: identifies an incoming service request; one request may trigger multiple operations.
- `traceId`: for correlation with distributed tracing; does not replace `operationId` and is not proof of identity.
- `causationId`: links the current event to the event/command that caused it.

Example:

```json
{
  "eventId": "evt-2202",
  "operationId": "refund-77",
  "action": "REFUND_PAYMENT",
  "phase": "RESULT",
  "outcome": "FAILED",
  "reasonCode": "PROVIDER_REJECTED",
  "requestId": "req-88"
}
```

During retries, multiple attempts may occur for a single operation; you must know whether a retry is a **re-execution of the same command** or a **new business request**. A `SUCCEEDED` event resent due to a network error is still one event and must not be counted as two successful refunds.

### 8.2. Bulk operations and partial success

For a `BULK_REVOKE_ROLE` operation across 100 accounts, an overall `SUCCEEDED` is only valid if the success condition holds for the entire target set. If 98 succeed and 2 fail:

- Emit a summary `PARTIAL` event with `successCount=98`, `failureCount=2`.
- You can emit per-target events for traceability without stuffing an unbounded list of IDs into a single message.
- Link events via `operationId`; do not assume every child event has the same outcome.
- Define counting rules for retries, rollbacks, or a target being processed twice.

There is no single “what action occurred” if a business operation consists of multiple independent actions. Decompose them into events with verifiable boundaries.

## 9. Who and What must be recorded from trusted sources

An `actorId` sent by a client in the request body cannot be trusted by default as an identity. For auditing actions:

- Obtain the actor from an **authenticated principal/token/session**.
- Record `actorType` when there are humans, service accounts, scheduled jobs, or automations.
- Distinguish `initiator` (who created the request), `approver` (who approved it), and `executor` (who executed it) when they differ.
- For `DENIED` due to unauthenticated access, there may be no authenticated actor; use `anonymous` or a policy-defined label rather than treating a self-reported username as a verified identity.
- `targetId` must be the ID of the actual resource, not a mutable display name or a URL containing secrets as the primary identifier.
- For sensitive operations, record appropriate scope such as `tenantId`, `organizationId`, `environment` per permissions and retention policies; do not expose unnecessary data.

**A log line is not the sole proof verifying actor and action.** Link it with authorization decisions, transactions, signed requests, approvals, or another source of truth if the threat model requires it.

## 10. Before and after: describing what changed

A `CHANGE_ACCOUNT_STATUS` action only indicates the operation type. For investigations, you may need the before/after state:

```json
{
  "action": "CHANGE_ACCOUNT_STATUS",
  "outcome": "SUCCEEDED",
  "targetType": "ACCOUNT",
  "targetId": "acct-52",
  "before": {"status": "ACTIVE"},
  "after": {"status": "SUSPENDED"},
  "changedFields": ["status"]
}
```

Only store **allowed fields**. Many configuration changes, passwords, API keys, or medical/financial data **should not** have their full values logged.

- For password reset: `action=RESET_PASSWORD`, `outcome=SUCCEEDED`, but **do not log the new password/hash**.
- For API key rotation: log key ID, version, and allowed metadata; do not log the token/secret.
- For policy change: you may log `policyId`, `fromVersion`, `toVersion`, `approvedSnapshotHash` if appropriate; do not dump the entire configuration.
- For `GRANT_ROLE`: you may log the role code and target; do not log the entire permission list, which could be huge.
- For `DELETE_DOCUMENT`: clarify whether it is soft delete, hard delete, or marked for deletion, as the action semantics differ.

If `before/after` are read before and after an operation at two unsynchronized points in time, concurrent modifications can corrupt the audit data. Attach a version/transaction ID or use a consistent state-and-audit write mechanism.

## 11. Java logging frameworks and carrying actions into events

### 11.1. JUL: suitable for demos, not audit storage by default

`java.util.logging.Logger` allows logging:

```java
// Illustrative snippet: auditLogger and event are variables in the application.
auditLogger.info("action=" + event.action()
        + " outcome=" + event.outcome()
        + " target=" + event.targetId());
```

However, whether a log is accepted by JUL depends on logger level, handler level, filters, `LogManager`, output paths, and sink errors. An `INFO` line **does not guarantee** it was written to a secure audit store.

### 11.2. SLF4J/Logback

In an application using SLF4J, you can have a dedicated audit logger:

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

// Field placed inside a valid class:
private static final Logger AUDIT =
        LoggerFactory.getLogger("com.example.audit.ActionEvents");

// Inside the event-handling method, after variables have been validated:
AUDIT.info("action={} outcome={} actor={} target={}",
        actionCode, outcomeCode, actorId, targetId);
```

This is an **integration snippet**, not a standalone Java file; it requires SLF4J dependencies and an appropriate backend. Using placeholders avoids unnecessary string concatenation, but **does not automatically escape newlines, mask secrets, or produce JSON**. In production, prefer an encoder or event API with structured fields and a dedicated audit pipeline.

Example `logback.xml` for **basic routing** of events to a file:

```xml
<configuration>
    <appender name="AUDIT_FILE"
              class="ch.qos.logback.core.FileAppender">
        <file>logs/audit-actions.log</file>
        <append>true</append>
        <encoder>
            <pattern>%d{yyyy-MM-dd'T'HH:mm:ss.SSS} %-5level %logger - %msg%n</pattern>
        </encoder>
    </appender>

    <logger name="com.example.audit.ActionEvents"
            level="INFO" additivity="false">
        <appender-ref ref="AUDIT_FILE"/>
    </logger>
</configuration>
```

This is an illustrative configuration for Logback Classic with appropriate dependencies. The target directory requires write permissions; you must add rotation, retention, a log shipper, and storage protection if required by the environment. `additivity="false"` prevents propagating audit events up to ancestor logger appenders; it **does not** make records immutable or durable. `append=true` only opens the file in append mode; anyone with permissions can still edit or delete the file.

### 11.3. Log4j 2, Spring Boot, and context

Log4j 2 has its own `org.apache.logging.log4j.Logger` API, filters, and appenders; Spring Boot can use SLF4J with a configured backend. **Do not copy a Logback XML configuration into a Log4j 2 XML file.**

MDC (SLF4J) or `ThreadContext` (Log4j 2) helps attach `requestId`, `operationId`, and service/tenant to each event. However:

- **MDC does not create audit actions automatically**: business code must emit events with an explicit action/outcome.
- Context in thread pools or async pipelines may need to be **propagated** explicitly.
- You must **clear/remove** context in a `finally` block or corresponding scope to prevent cross-request leakage.
- Never use a client-supplied ID as proof of authenticated identity.
- Never let unsanitized MDC values determine file names, topics, or arbitrary routing paths.

An action event may be sent to multiple appenders; if the system counts records without deduplicating by `eventId`, it may mistakenly count one action as two.

## 12. Content security and preventing log injection

Audit logging often handles sensitive data that is valuable to attackers. Data must be designed safely from the source:

1. **Do not log secrets** such as passwords, tokens, API keys, private keys, session cookies, credentials, or recovery codes.
2. **Do not log full payloads** when only the action/target/changed fields are needed; minimize PII per policy.
3. **Escape/serialize safely**: actor strings, resource names, or `reason` values may contain newlines, tabs, quotes, or control characters. Do not concatenate untrusted input to forge fake log lines.
4. **Enforce length and data type limits**: a `reason` containing several MB of text can fill queues or break event structure.
5. **Do not let users choose arbitrary action codes** when actions belong to an enum/catalog; determine the action server-side based on business logic.
6. **Record denied operations** without exposing internal security details in the message returned to the client.
7. **Restrict read access to audit records** separately from regular application logs; audits can reveal permissions, targets, and sensitive activity flows.
8. **Apply retention and deletion policies** rather than keeping all personal information in audit logs indefinitely.

When `before/after` values of sensitive objects must be kept, store **ID/version/field names** and a reference to a protected snapshot; do not assume `hash(secret)` is automatically safe, especially for low-entropy inputs.

**Structured logging** with a fixed schema reduces parsing errors, but does not prevent leaks if the structured fields themselves contain secrets. Filtering responsibility still lies with the event-creation logic and governance policies.

## 13. Reliability: creating an event does not mean it is saved

A typical processing flow is:

```text
operation -> AuditEvent created
               |
               v
          logger/appender
               |
          async queue (optional)
               |
        file/collector/network
               |
       durable storage / retention
```

If an event sits in an in-memory queue and the process crashes, the event may be lost. If the sink is full, the appender may drop events or block requests. If the collector retries, an event may appear **twice**.

For mandatory audits, define:

- **Confirmation level:** accepted into queue, accepted by remote service, persisted, replicated, or retention enforced.
- **Failure policy:** when the audit store fails, reject the operation (fail-closed), write to a durable outbox, or follow an approved exception procedure.
- **Retries and idempotency:** a stable `eventId` helps consumers recognize redelivered events.
- **Evidence protection:** append-only/immutable storage, separation of duties, integrity, retention, and monitoring.
- **Reconciliation:** reconcile state changes/transactions/outbox against the audit trail to detect missing events.
- **Transport security:** TLS, producer authentication, sink authorization.

Do not claim “no audit logs can be lost” if the system only calls `logger.info(...)` or `queue.offer(event)` and moves on. If auditing is mandatory for a transaction, design commit/durability conditions explicitly.

## 14. Searching and answering “What action occurred?” during investigations

Useful analytical queries:

- “Which permissions were **granted to or revoked from** account `u-42` during this time window?”
- “Who requested `EXPORT_CUSTOMER_DATA` and **how many times was it denied**?”
- “Were any `DELETE_DOCUMENT` operations **successful** before the document disappeared?”
- “What phases did a refund request go through, and where did it stop?”
- “Which `CHANGE_LOG_LEVEL` actions enabled DEBUG in production, who approved them, and when were they rolled back?”

With the schema shown earlier, a conceptual query looks like:

```text
action = "GRANT_ROLE"
AND outcome = "SUCCEEDED"
AND targetType = "USER"
AND targetId = "u-42"
```

This is an **illustrative filter**, not SQL or syntax specific to any storage engine. Queries are only trustworthy if events were emitted at the right time, contain complete data, were not dropped, and have integrity protections aligned with audit goals.

Do not just query `message contains "role"`, because it may match both “role check failed” and an actual “role granted” action. A standardized `action` field keeps machines and humans aligned.

### 14.1. Ordering events across multiple services

Nodes can experience clock skew, and networks can retry or deliver events out of order. To reconstruct actions:

- Use UTC timestamps and synchronized clocks, but **do not rely on timestamps alone as the event key**.
- Use `eventId`, `operationId`, and where appropriate `sequenceNo` per operation.
- Keep both `occurredAt` and `ingestedAt` to track latency.
- Distinguish `event order` within a transaction from collector arrival order.
- Combine with trusted state/version/transaction logs to confirm the actual outcome.

If two records share the same `eventId` due to a retry, count them as one logical event; if they share `operationId` but have different `eventId`s, they may represent different phases or attempts.

## 15. Testing how actions and outcomes are recorded

Tests should ask **can an investigator reach the right conclusion?**, not just “was something logged?”.

| Scenario | Expected audit |
| --- | --- |
| Role granted successfully after commit | `GRANT_ROLE/SUCCEEDED`, accurate target and role |
| Role grant denied | `GRANT_ROLE/DENIED`, state unchanged |
| Operation rejected by validation | `VALIDATION_FAILED` and appropriate reason code |
| Transaction rolls back after processing | No false `SUCCEEDED` event |
| Background job only queued | `PENDING` or accepted event, not completed |
| Export finished but download failed | Export and delivery events clearly separated per contract |
| Bulk 98/100 succeeded | `PARTIAL`, with per-target evidence |
| Retry sends the same event twice | Consumer does not count it as two actions |
| Request body spoofs admin actor | Audit actor reflects only the authenticated identity |
| Target contains newlines/control chars | No forged audit lines, does not break JSON/schema |
| A field contains a secret | Secret is not written to file, queue, collector, or search index |
| Async queue full / sink error | Audit policy and business state remain consistent with contract |

Write **unit tests** for the action catalog, outcome mapping, and redaction; **integration tests** for transactions/rollbacks/outbox; and **end-to-end tests** for delivery and querying. Tests should verify both **event count** and **field contents**, preventing duplicate or missing events.

For high-consequence actions, also evaluate what happens when the audit sink is unavailable: does the system reject the operation, write to a durable outbox, or enter an approved emergency procedure? The rules must exist before an incident.

## 16. Common mistakes

### Mistake 1: Action is only `UPDATE` or `DELETE`

Without a target or semantics, it is hard to tell what the user modified. Use a semantic action or include controlled `targetType` and `changedFields`.

### Mistake 2: Logging `SUCCEEDED` as soon as the request arrives

A request may be rejected, rolled back, or fail in a background job. Separate attempt/accepted from result and verify against the true completion boundary.

### Mistake 3: Using `ROLE_GRANTED` even for denied attempts

The event name misleads readers into thinking the role was granted. Use `GRANT_ROLE` + `outcome=DENIED` or a separate event type `ROLE_GRANT_DENIED`.

### Mistake 4: Confusing actor with target

In “admin grants role to user”, admin is the **actor** and user is the **target**; if a user makes a request on behalf of someone else or via automation, there are also initiator/executor/approver roles.

### Mistake 5: Auditing with free-form English sentences

`"Updated user"`, `"User is done"`, `"Change passed"` are hard to parse automatically and may be reworded or translated. Keep `action` codes stable, and use messages only for human readability.

### Mistake 6: Logging only debug logs after an operation

DEBUG logs can be disabled or lost, and lack protection policies. Mandatory audits require a dedicated pipeline and retention.

### Mistake 7: Logging full before/after payloads

This can leak passwords, PII, tokens, secrets, or irrelevant data. Log only allowed attributes and avoid raw payloads.

### Mistake 8: Placing business logic inside a logger guard

```java
// Wrong: role granting may be skipped when the audit logger is disabled.
if (auditLogger.isLoggable(java.util.logging.Level.INFO)) {
    grantRole();
    auditLogger.info("GRANT_ROLE SUCCEEDED");
}
```

This is an **illustrative integration snippet**, not a standalone program. Business logic must not depend on logging levels. A system requiring audits needs a dedicated policy when the audit service fails rather than hiding business logic inside a logging guard.

### Mistake 9: Using the same requestId instead of eventId

One request can trigger multiple actions; if all of them use `requestId` as `eventId`, they become hard to distinguish. Use a unique `eventId` per event and a shared `operationId` for related event sequences.

### Mistake 10: Believing that calling the logger proves the action

Logs can be emitted at the wrong time, filtered/dropped, or fail to reach the sink. Audits are only trustworthy when event semantics, transaction boundaries, and storage paths match the required level of assurance.

## 17. Implementation checklist

- [ ] Every audited operation has a clear, stable action code with documented semantics.
- [ ] Distinguish **requested/attempted** from **performed/succeeded** and `DENIED`, `FAILED`, `PARTIAL` states.
- [ ] Define the exact success boundary: commit, delivery, settlement, or other completion point.
- [ ] Attach target type/ID, allowed changed attributes, scope, and version if needed.
- [ ] Obtain the actor from a trusted authentication source, never from self-reported client data.
- [ ] Attach `eventId`, `operationId`/`requestId`, and UTC timestamp for tracing and deduplication.
- [ ] Never log secrets, unnecessary PII, raw payloads, or unescaped input strings.
- [ ] Place audit events near the business boundary and use transactions/outbox when consistency is required.
- [ ] Define behavior for audit sink failures, full queues, retries, shutdowns, or crashes.
- [ ] Store audits with access control, retention, integrity, and reconciliation appropriate to the risk level.
- [ ] Test success, denial, rollback, async, bulk/partial, sink failure, and duplicate events.
- [ ] Ensure actions can be queried by target/outcome rather than guessing from message text.

**Conclusion:** To accurately answer **“what action occurred?”**, an audit event must record an **action with stable business semantics**, the **target**, the **actual outcome**, and correlation evidence. “Requested” is not “executed”, “job accepted” is not “completed”, and “logger called” is not “evidence saved”. That is the foundation for audit logging to be valuable in investigations, security, and operations.
