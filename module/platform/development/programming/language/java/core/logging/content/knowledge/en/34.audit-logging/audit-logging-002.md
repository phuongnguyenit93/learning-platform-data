# Audit Events in Java Core Logging

## 1. What Is an Audit Event?

An **audit event** is a structured record of **who or what component performed or attempted to perform an action, on which target, when, in what context, and with what outcome**. Audit logging supports accountability, security incident investigation, reconciliation of critical changes, and proof that actions followed required procedures. An audit event may involve authentication, authorization, system configuration, sensitive data access, or business state transitions that must be tracked.

Examples:

- An administrator changes a user account's permissions.
- An account attempts to access a resource but is denied due to insufficient permissions.
- An API key is created, rotated, or revoked.
- Authentication configuration, security policies, or data access permissions are modified.
- A sensitive data export job is requested, approved, completed, or failed.
- The audit mechanism itself has its configuration changed, loses connectivity, or detects an integrity anomaly.

**An audit event differs from an ordinary operational log line.** A line like `logger.debug("Processing request")` helps developers debug; an audit event `permission.role.changed` must contain enough fields to answer who performed the action, which entity was affected, the before/after permissions, the outcome, the authorization basis, and a correlation trail. Auditing should not depend solely on a free-form message string that changes whenever the code is edited.

### Distinguishing Related Data Types

| Type | Primary Question | Example |
| --- | --- | --- |
| Operational log | What is the application doing and are there errors? | Timeout when calling downstream |
| Security event | Are there signs of anomalous access or behavior? | Multiple failed login attempts |
| **Audit event** | What action occurred or was denied, by which principal, and with what impact? | `user-7`'s role changed from `READER` to `EDITOR` |
| Distributed trace | Which services/spans did a request pass through? | Trace ID linking the API gateway to the identity service |
| Business event | Which business state changed? | Order transitioned to `PAID` |

A single event can simultaneously carry audit, security, and business value, but **each purpose has its own retention, access control, and reliability requirements**. Do not assume a sampled trace or an `INFO` log can replace mandatory auditing.

## 2. When to Emit an Audit Event

Auditing is meaningful when emitted at **the boundary of a decision or change that carries accountability**, rather than on every line of code. For a Java service, typically consider:

| Category | Scenario | Minimum Data to Capture |
| --- | --- | --- |
| Authentication | Login success/failure, logout, MFA enrollment/reset | Principal, mechanism, outcome, reason code, request |
| Authorization | Access denied, grant/revoke role, policy change | Actor, target, permission, before/after, outcome |
| Account | Create, lock, unlock, delete account | Actor, subject, old/new state, approval |
| Administration | Change critical settings, sensitive feature flags | Actor, config key, allowed before/after values |
| Credentials | Create/rotate/revoke token or key | Key identifier/fingerprint, operation type; **never store secrets** |
| Sensitive data | Export/download, access permission changes, bulk delete | Resource class/ID, scope, result, volume when valid |
| Critical transactions | Complete/cancel transactions requiring reconciliation | Entity ID, transition, correlation, transaction ID |
| Audit operations | Disable audit, change retention/view permissions, ingest failure | Actor/component, configuration change, impact |

Not every data read must be audited, and not every denied access must be retained forever. Choose the **event catalog based on your threat model, business accountability, and applicable regulatory policies**. For extremely high-frequency operations, distinguish raw access logs from mandatory full auditing; if regulations require recording everything, design the infrastructure to handle that load rather than silently sampling.

### Auditing Failures

Recording only successful operations misses unauthorized access attempts. Conversely, logging only failures leaves you unaware of **who successfully changed permissions**. Define clear event outcomes such as `SUCCESS`, `DENIED`, `FAILED`, `PENDING`, or `CANCELLED`, using only the states that match the actual action lifecycle.

- `DENIED`: the system rejected the request **before execution** due to an authentication/authorization policy.
- `FAILED`: the action was permitted, encountered an error, and **did not complete per its contract**.
- `SUCCESS`: the action completed at a **defined commit/success decision point**.
- `PENDING`: the request was accepted, with insufficient basis yet to confirm completion.

Do not record `SUCCESS` as soon as a request is received if the business operation runs asynchronously. For long-running workflows, emit separate events for `REQUESTED`, `APPROVED`, `COMPLETED`, and `FAILED`, linking them with the same correlation/operation ID.

## 3. Structure of a Good Audit Event

An audit record should have a **versioned schema and fields with stable semantics**. JSON example:

```json
{
  "schema_version": "1",
  "event_id": "evt-100",
  "occurred_at": "2026-01-01T00:00:01Z",
  "event_type": "iam.role.change",
  "actor": {
    "id": "admin-1",
    "kind": "HUMAN",
    "authn_method": "SSO"
  },
  "target": {
    "type": "USER_ACCOUNT",
    "id": "user-7"
  },
  "action": "ROLE_CHANGE",
  "outcome": "SUCCESS",
  "reason_code": "ADMIN_POLICY",
  "changes": {
    "role": {
      "before": "READER",
      "after": "EDITOR"
    }
  },
  "service.name": "identity-api",
  "deployment.environment.name": "prod",
  "request_id": "req-10",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736"
}
```

This is an **illustrative application-defined schema**, not a default format from the JDK, SLF4J, or a SIEM system. To integrate multiple services, you need a unified schema contract, validation, and versioning prior to ingestion.

### Meaning of Each Field Group

| Field / Group | Purpose | Notes |
| --- | --- | --- |
| `schema_version` | Allows parsers to understand structure across upgrades | Never silently change the meaning of an existing field |
| `event_id` | Identifies **one logical event** for deduplication/reconciliation | Should be generated by a trusted component and remain stable across retries |
| `occurred_at` | Timestamp when the event occurred at the source | Use UTC/offset; distinguish from ingestion time |
| `actor` | Who or which service account caused the action | Must come from verified identity; do not blindly trust client-supplied values |
| `target` | The entity acted upon | Standardized ID/type and tenant scope if needed |
| `action` / `event_type` | Action type with stable semantics | Avoid overly arbitrary free text |
| `outcome` / `reason_code` | Success, denial, or failure, with a machine-readable reason | Do not replace with natural-language messages |
| `changes` | Verifiable before/after changes | Include only permitted fields; redact sensitive data |
| `service.name` / environment | Distinguishes the emitting service and environment | Prevent client-spoofed values |
| `request_id` / `trace_id` | Links to operational logs and traces | One request may emit multiple audit events |
| `tenant_id` (when applicable) | Separates multi-tenant data | Enforce tenant access control at view/storage time |
| `approval_id` or `policy_version` | Reconciles authorization decisions | Use only when meaningful and backed by an authoritative source |

**Distinguishing actor and subject/target:** the actor is the principal performing the operation; the target is the entity affected. An administrator locking someone else's account does not make the locked account the actor. In service-to-service calls, the actor may be a workload identity. If acting "on behalf of" a user, clearly represent the **initiating user**, the **executing service**, and any delegation info rather than collapsing both into one.

**`event_id` vs. `request_id`:** a single request changing multiple permissions may emit multiple audit events; using only `request_id` for deduplication will drop valid events. For retries of the same *logical operation*, define an appropriate idempotency key rather than generating a new event ID on each retry if you want to avoid double-counting.

## 4. Authenticity: Who to Trust, and Which Parts to Trust?

An audit event is valuable when the actor, action, and outcome fields **are derived from server-verified state**, not from client-supplied strings. For example, a client can send an `X-User: admin` header, which does not prove the real user is an admin.

Trusted sources typically include:

1. **Authentication context** produced after middleware verifies a signature/session and derives the principal ID; the service must not read an unverified header directly as the actor.
2. **Authorization decision** computed by a policy engine or business logic, along with policy/rule version when useful.
3. **Committed business state** to determine whether the action actually succeeded or failed.
4. **Server-side event generator** creating the event ID, timestamp, and service metadata; prevent clients from overriding these fields.
5. **Trusted deployment metadata** for service name, environment, workload identity, or tenant scope.

Source IP, User-Agent, geolocation, and device are **secondary signals** and do not prove identity on their own. Behind a reverse proxy, you must understand the trusted proxy chain before using `X-Forwarded-For`; never blindly take an address from a client-controlled header. In multi-tenant systems, do not rely solely on a client-controllable `tenant_id` field to determine audit scope or query permissions.

### Log Injection Risks

Fields such as username, object name, URL path, user agent, or error message may contain newlines, quotes, and control characters. When concatenated into text logs, this data can masquerade as multiple separate event lines. **Structured logging through a proven JSON encoder**, validation, and field size limits help preserve event boundaries. However, a good encoder is no substitute for authenticating the actor and outcome fields.

Never log raw secrets, passwords, access tokens, session cookies, private keys, API keys, connection strings containing credentials, sensitive payment details, or unnecessary personal payloads. When emitting a `credential.rotated` event, store only the credential ID or a safe fingerprint—**never the before/after credential values**.

## 5. Event Emission Timing and Ordering

A business operation may consist of these steps:

```text
Request arrived
  -> authenticate
  -> authorize
  -> validate
  -> execute business change
  -> commit
  -> send response
```

Choose when to emit an audit event based on **the meaning of the event**:

- **Denied** operation: emit a `DENIED` event after the denial decision, without waiting for a database change.
- **Successful** operation: emit or durably record a `SUCCESS` event based on the **actual success** of the transaction/operation, avoiding false confirmation before commit.
- **Asynchronous** operation: emit `REQUESTED` when the request is accepted and `COMPLETED` or `FAILED` when the final result is determined.
- **Composite** operation: if multiple objects are modified, clarify whether the event represents the whole operation or each sub-change; do not merge them in a way that breaks reconciliation.

If an API returns success while audit recording fails, a change occurs without evidence. If an audit record is written first and the transaction rolls back, a false `SUCCESS` audit appears. Choose a **consistency contract** suited to the business requirement rather than simply placing `logger.info(...)` before or after `repository.save(...)` and assuming atomicity.

## 6. Standalone Java 17 Example: Auditing Successful and Denied Role Changes

This example uses JDK 17 to demonstrate audit event structure, the distinction between **actor** and **target**, before/after state, outcomes, and auditing both successful and denied operations. The program intentionally uses fixed timestamps and IDs for deterministic stdout.

**Note:** this is an in-memory model. It has **no database transaction, no durable audit storage, no real auth checks, is not thread-safe**, and is not a production authorization system. The minimal JSON encoder only illustrates escaping; production code should use a proven JSON/structured logging library.

Save in `AuditEventDemo.java`:

```java
import java.time.Instant;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;

public final class AuditEventDemo {
    record AuditEvent(
            String eventId, Instant occurredAt, String actorId,
            String action, String targetId, String outcome,
            String beforeRole, String afterRole,
            String reasonCode, String requestId) {}

    private static final Map<String, String> ROLES = new HashMap<>();
    private static final List<AuditEvent> EVENTS = new ArrayList<>();

    private static String quote(String value) {
        StringBuilder out = new StringBuilder("\"");
        for (int i = 0; i < value.length(); i++) {
            char c = value.charAt(i);
            switch (c) {
                case '"' -> out.append("\\\"");
                case '\\' -> out.append("\\\\");
                case '\n' -> out.append("\\n");
                case '\r' -> out.append("\\r");
                case '\t' -> out.append("\\t");
                default -> {
                    if (c < 0x20) {
                        out.append(String.format(
                                Locale.ROOT, "\\u%04x", (int) c));
                    } else {
                        out.append(c);
                    }
                }
            }
        }
        return out.append('"').toString();
    }

    private static String field(String name, String value) {
        return quote(name) + ":" + quote(value);
    }

    private static void emit(AuditEvent event) {
        EVENTS.add(event);
        System.out.println("{"
                + field("event_id", event.eventId()) + ","
                + field("occurred_at", event.occurredAt().toString()) + ","
                + field("actor_id", event.actorId()) + ","
                + field("action", event.action()) + ","
                + field("target_id", event.targetId()) + ","
                + field("outcome", event.outcome()) + ","
                + field("before_role", event.beforeRole()) + ","
                + field("after_role", event.afterRole()) + ","
                + field("reason_code", event.reasonCode()) + ","
                + field("request_id", event.requestId())
                + "}");
    }

    private static void changeRole(
            String actor, String target, String requestedRole,
            String eventId, String requestId, Instant time) {
        String before = ROLES.get(target);
        if (before == null) {
            throw new IllegalArgumentException("Unknown target");
        }

        // Demo rule; not real authentication/authorization.
        boolean allowed = "admin-1".equals(actor);
        if (allowed) {
            ROLES.put(target, requestedRole);
        }
        String after = ROLES.get(target);

        emit(new AuditEvent(
                eventId, time, actor, "ROLE_CHANGE", target,
                allowed ? "SUCCESS" : "DENIED",
                before, after,
                allowed ? "ADMIN_POLICY" : "NOT_AUTHORIZED",
                requestId));
    }

    public static void main(String[] args) {
        ROLES.put("user-7", "READER");

        changeRole(
                "admin-1", "user-7", "EDITOR",
                "evt-100", "req-10",
                Instant.parse("2026-01-01T00:00:01Z"));

        changeRole(
                "user-8", "user-7", "OWNER",
                "evt-101", "req-11",
                Instant.parse("2026-01-01T00:00:02Z"));

        System.out.printf(
                "FINAL role=%s audit_events=%d%n",
                ROLES.get("user-7"), EVENTS.size());
    }
}
```

Compile and run:

```bash
javac AuditEventDemo.java
java AuditEventDemo
```

**Exact stdout**:

```json
{"event_id":"evt-100","occurred_at":"2026-01-01T00:00:01Z","actor_id":"admin-1","action":"ROLE_CHANGE","target_id":"user-7","outcome":"SUCCESS","before_role":"READER","after_role":"EDITOR","reason_code":"ADMIN_POLICY","request_id":"req-10"}
{"event_id":"evt-101","occurred_at":"2026-01-01T00:00:02Z","actor_id":"user-8","action":"ROLE_CHANGE","target_id":"user-7","outcome":"DENIED","before_role":"EDITOR","after_role":"EDITOR","reason_code":"NOT_AUTHORIZED","request_id":"req-11"}
```

Third line on stdout:

```text
FINAL role=EDITOR audit_events=2
```

Explanation:

1. `admin-1` is permitted by the demo rule, so the role transitions `READER → EDITOR`. The first event records `SUCCESS`, different before/after values, and distinct actor and target.
2. `user-8` is not authorized to change roles, so the state remains `EDITOR`. The second event records `DENIED` with identical before/after values instead of mistakenly marking `SUCCESS`.
3. Both events have distinct `event_id` values to identify each action; `request_id` links them to the corresponding request logs.
4. `quote` escapes quotes, backslashes, newlines, and basic control characters; the sample data contains no secrets. Production code needs full Unicode/schema encoding and validation.
5. `ROLES` and `EVENTS` live **in RAM**. If the process crashes after `ROLES.put` but before `emit`, the change occurred without an audit record. Thus, the example only demonstrates audit **content**, not reliability or atomicity.

A common design mistake is treating a RAM/console example as a "complete audit trail". To guarantee that the event exists alongside the data change, you must add a transaction/outbox or appropriate durable audit storage.

## 7. How to Prevent Losing Audit Events on Failure?

Different mechanisms offer very different levels of guarantee:

| Recording Method | Pros | Limitations |
| --- | --- | --- |
| `logger.info(...)` to console | Easy to operate, shares pipeline with regular logs | Logger level/filter/sampling, queues, runtime/agent, and ingestion can drop logs |
| Local file appender | Can work during network outages | File rotation, disk full, crash/flush, permissions, and durability are uncertain |
| Synchronous send to audit service | Clearer ACK feedback | Timeouts/partial failures; a gateway-level ACK may not mean durable storage |
| Durable queue/broker per contract | Supports retries and decouples producer/consumer | Must define ACK level, retention, replication, and recovery |
| **Transactional outbox** | Ties event emission to business change in the same DB transaction | Requires publisher, retry, deduplication, cleanup, and backlog monitoring |
| Dedicated audit storage | Can enforce stronger append-only, retention, and access control policies | Depends on technology and configuration; not automatically immutable |

### Transactional Outbox for Critical Changes

If the business operation uses a transactional database, a common pattern is:

```text
BEGIN TRANSACTION
  UPDATE user_roles
    SET role = 'EDITOR'
    WHERE user_id = 'user-7';

  INSERT INTO audit_outbox (
    event_id, event_type, actor_id, target_id,
    before_role, after_role, outcome, occurred_at
  ) VALUES (...);
COMMIT

Background publisher:
  read unacknowledged outbox rows
  -> export audit event to destination
  -> retry on failure
  -> mark or clean up outbox using a safe mechanism
```

This is a **pseudo-SQL diagram**, not a standalone runnable script. Atomicity applies to the **UPDATE and INSERT within the same transaction in a properly ACID-compliant database**. It does not automatically make external delivery exactly-once.

If the publisher sends an event successfully but the ACK is lost, it may resend and create a duplicate. The consumer/backend should use `event_id` as an **idempotency key** or deduplicate at query/storage time so two deliveries do not become two logical actions. Do not confuse a `retry_attempt` with a new audit event.

### Denials and Transaction Rollbacks

A `DENIED` request does not necessarily have a business database transaction, yet it still requires auditing per policy. If audit records are stored separately from the main transaction, explicitly specify behavior when one side fails. For a `FAILED` and rolled-back action, **never emit a `SUCCESS` event as if the commit succeeded**. You can emit separate `ATTEMPTED` and `FAILED` events to preserve the true execution sequence.

Choose **fail-open or fail-closed** based on operation type:

- For ordinary diagnostic logs, you usually let the service continue even if the logging backend fails, while measuring log loss.
- For mandatory auditing of a sensitive operation, you may need to **reject the operation** if the audit trail or outbox cannot be durably written, depending on business contracts and regulations.
- Do not perform unbounded synchronous network audit writes on the request thread while hoping for both zero data loss and unaffected availability. Design explicit deadlines, retries, backpressure, queues, and recovery.

## 8. Delivery Semantics, Duplicates, and Ordering

A typical pipeline:

```text
Java service
  -> audit event generator
  -> durable commit / outbox / queue
  -> exporter / collector
  -> audit store
  -> index / query / report
```

An event accepted into an in-memory queue is not yet durably stored. A "received" ACK from a Collector does not prove the backend finished persisting it. Therefore, define the **commit point**: source accepted, durably enqueued, committed to DB/broker, or queryable at the final store.

- **At-most-once:** may lose events on failure, but avoids duplicate deliveries.
- **At-least-once:** may produce duplicate attempts on retry; requires IDs and deduplication.
- **Exactly-once effect:** can only be claimed within explicitly designed transaction/idempotency/commit boundaries; standard loggers do not provide this by default.

**Do not assume global ordering.** Multiple threads, instances, queues, and networks can deliver events out of creation order. If you need to establish the sequence of permission changes, use a per-entity `entity_version` or sequence committed in the transaction alongside event time and ingestion time. High-resolution timestamps alone do not guarantee absolute order across machines with clock skew.

A solid investigative system records *event occurred at*, *ingested at*, *event ID*, and *correlation*, handling late events, retries, and duplicates. Intentionally filtered/sampled events must be distinguished from **events lost due to errors**.

## 9. Integrity, Tamper Resistance, and Traceability

An audit trail must be protected from out-of-band modification or deletion. Techniques that can be combined include:

1. **Permission-enforced append-only:** production applications are only allowed to create events, never modify or delete old records. Restrict `DELETE`/`UPDATE` privileges and retention management permissions.
2. **Durability and backups:** replication, durable queue/storage, crash recovery, disk quotas, and scheduled restore testing per contract.
3. **Tamper evidence:** hash chains, HMAC, digital signatures, or platform immutability mechanisms to detect modifications. A **plain hash chain** reliably detects tampering only when the anchor/key or digest is independently protected; anyone able to modify both the chain and all anchors can recompute the hashes.
4. **Timestamping and keys:** timestamps from trusted sources, clock skew checks, signing key management, rotation, and signature verification policies.
5. **Separated query permissions:** writers do not automatically get read access to the entire system's audit trail; investigators have role/tenant-scoped access, and their access itself is audited.
6. **Monitoring the audit pipeline itself:** queue backlog, dropped events, exporter errors, parse failures, heartbeats, dead-letter queues, and retention changes must emit independent alerts.

Do not advertise a system as "tamper-proof" merely because a file is opened in append mode or each line has a SHA-256 hash. Tamper resistance claims must state what an adversary can control and which mechanisms protect anchors/keys, storage, admin privileges, and history.

## 10. Retention, Personal Data, and Access Control

Audit logging generally serves accountability and reconciliation longer than ordinary `DEBUG` logs; however, **there is no single fixed retention period applicable to every country and every business**. Organizations must determine retention from processing purpose, actual legal/contractual requirements, event type, risk, and cost.

Implementation principles:

- **Data minimization:** store IDs, action types, outcomes, and meaningful changes; never store plaintext passwords, tokens, or secrets. When sensitive values change, store only the attribute name or a flag indicating it changed, not plaintext before/after values.
- **Access control:** grant ingest, search, export, delete, and policy-change permissions separately; restrict scope by service/tenant/environment and audit access to the audit trail itself.
- **Transport/storage security:** use TLS across protected network boundaries, encryption at rest, and platform-appropriate key management; authenticate both producers and Collectors.
- **Retention and deletion:** policies may vary by event group. When personal data erasure requests conflict with audit retention obligations, follow an appropriate legal/technical process rather than assuming one always overrides the other.
- **Data classification:** actor IDs, IPs, user agents, correlation IDs, and before/after values can be sensitive depending on context. Do not place them into high-cardinality metric labels or public dashboards.
- **Configuration governance:** audit any changes to retention, access permissions, exporter/collector routing, or enabling/disabling auditing; audit administration must have independent oversight.

Longer retention does not automatically mean better. Data must remain usable, protected, and queryable for the required duration.

## 11. Integrating into the Java Logging Stack

**SLF4J is a facade**, while backends such as Logback or Log4j2 handle filters, appenders, queues, and formatters. JUL has its own `Logger`/`Handler`. When using a general logging framework to emit audit events, verify:

- **Level:** if audit events are logged at `INFO` while the environment sets root to `WARN`, records may be dropped. A dedicated audit path with its own policy should avoid depending on general log levels.
- **Sampling/filtering:** if policy requires keeping every audit event, ensure they bypass sampling filters that could drop them.
- **Structured encoder:** event type, actor, target, outcome, ID, and timestamp must be preserved as queryable fields rather than plain message text.
- **Context propagation:** `request_id`/`trace_id` from MDC may not propagate to tasks on an `ExecutorService` or reactive pipeline; propagate context explicitly and clear/restore it in `finally`.
- **Async and flushing:** logs buffered in an in-memory queue are not naturally crash-durable. Test behavior during shutdown, overload, and network partitions.
- **Provider/bridge:** verify the intended backend is active and there are no duplicate providers or overlapping log routes.

Illustrative snippet for the SLF4J API:

```java
auditLogger.info(
        "audit event_id={} action={} actor_id={} target_id={} outcome={}",
        eventId, action, actorId, targetId, outcome);
```

This is **not a standalone program**; it requires a configured `auditLogger` in the application. Without an additional encoder or structured arguments, it still produces only **parameterized text logs**. Do not treat this call as a durability guarantee. For strict transaction/audit requirements, use an **audit writer or outbox** with its own storage contract, optionally forwarding an accepted copy to the logging backend for observability.

### Do Not Use MDC as the Source of Truth for the Actor

MDC is useful for correlation, but it can be lost across thread boundaries or leaked when thread pools reuse threads. The `actorId` of an audit event must come from the verified authentication context at the action boundary and be passed via a trusted contract. If the actor is unauthenticated, record an appropriate identifier such as `ANONYMOUS` or `UNKNOWN` along with the reason—never guess an identity.

## 12. Querying and Reconciling Audit Events

An audit trail must be able to answer investigative questions:

- Who changed `user-7`'s role during a given time window?
- Did the change succeed? What were the before and after values? Were there corresponding approval and policy versions?
- How many denied access attempts to a sensitive resource were made by a given principal?
- Do events remain in durable storage even if the emitting instance restarts?
- Are there duplicate events from retries or missing events compared to the DB transaction/outbox?

Conceptual query example:

```sql
SELECT occurred_at, event_id, actor_id, action, target_id,
       outcome, before_role, after_role, request_id
FROM audit_events
WHERE target_id = 'user-7'
  AND action = 'ROLE_CHANGE'
ORDER BY occurred_at, event_id;
```

This SQL only illustrates a designed table schema; it is not the query syntax of every cloud log service. For multi-tenant data, query authorization must be enforced by the backend/app—**never rely on the viewer manually adding `WHERE tenant_id=...`**.

If the outbox/broker has at-least-once semantics, group by `event_id` and investigate duplicate attempts separately. Reconciling audit event counts against a durable business source (transactions/change history) is usually more reliable than merely counting logs present in the backend.

## 13. Recommended Tests

| Scenario | What to Verify |
| --- | --- |
| Successful role change | Exact `SUCCESS` event, actor/target, before/after, and IDs |
| Authorization denied | `DENIED` event emitted; state remains unchanged |
| Validation error before commit | Accurate outcome; no false `SUCCESS` |
| Transaction rollback | No false success audit; clear policy for attempt/failure events |
| Crash between change and log emission | Outbox/transaction still allows recovering the mandatory event |
| Retry after lost ACK | No second logical event created; deduplicated by event ID |
| Concurrent requests | Actor, target, and request contexts are never mixed; consistent sequence/version when required |
| Input with newlines/quotes | Valid JSON parsing; no line injection or event spoofing |
| Quota exceeded / queue full / network loss | Fail-open/fail-closed follows policy; errors, backlog, and drops are measurable |
| Process restart/rotation | Durably committed events remain recoverable/queryable |
| Sensitive role change | Approval/policy version and actual actor are verified |
| Sensitive data exposure | No secrets in events, stack traces, or MDC |
| Retention expiration | System deletes/retains per policy; delete/export permissions verified |
| Audit configuration change | Event/alert emitted for retention, permission, or collector route changes |
| Tenant-scoped query | Cannot read another tenant's audit events without authorization |

For Java unit tests, you can compare `AuditEvent` as an immutable record, asserting outcome, request ID, event type, and before/after counts. Integration tests should verify that **events are actually persisted** through the audit writer/DB/Collector to the target store with the right schema. Failure-injection tests with restarts, broker timeouts, and lost ACKs should verify the contract rather than assuming `logger.info` always succeeds.

## 14. SLIs/SLOs and Audit Pipeline Health

If mandatory audit events are lost without anyone noticing, the system loses accountability. Independent observability should be in place:

| Signal | Meaning |
| --- | --- |
| `audit_events_committed_total` | Number of events durably committed at source/outbox |
| `audit_events_exported_total` | Number of events exported from the producer |
| `audit_events_ingested_total` | Number of events accepted by the ingestion layer |
| `audit_events_queryable_total` | Number of unique event IDs queryable at the destination |
| `audit_export_errors_total` | Transport or ACK receipt errors |
| `audit_queue_depth` / `oldest_event_age` | Backlog and risk of missing deadlines |
| `audit_duplicate_attempts_total` | Duplicate deliveries caused by retries |
| `audit_integrity_failures_total` | Hash/signature/schema violations during verification |
| `audit_pipeline_heartbeat` | Detects when the audit pipeline stops running |

These metric names **are only examples**, not built into every JDK logger or Collector. An end-to-end SLI might measure **the ratio of event IDs committed at the source that become queryable in the audit store within a defined deadline**. An SLO must specify the measurement window, event scope, deadline, and exclusions clearly. For zero-loss audit requirements, rely on a durability and reconciliation contract rather than just an "attractive" percentage target.

Alert when the producer continues processing transactions while the outbox backlog grows, when the Collector stops receiving events, when the identity/permission log rate suddenly drops to zero, or when retention is changed out-of-band. Use canaries and independent metrics to detect when **the logging system itself goes silent**.

## 15. Common Pitfalls

| Pitfall | Impact | Fix |
| --- | --- | --- |
| Logging only `"User updated"` | Unknown who, what target, or what outcome | Use an actor/action/target/outcome schema |
| Using IP or header username as verified actor | Event source can be spoofed | Derive from a trusted authentication context |
| Recording `SUCCESS` before commit | Rollback leaves a false audit record | Tie outcome to commit state |
| Logging only successes | Misses denied attempts | Record denial events per policy |
| Using `request_id` as the unique event ID | Multiple actions in one request get collapsed | Generate a distinct ID per logical event |
| Generating a new event ID on each retry | Double-counts actions | Keep the event ID stable across retries |
| Sending audit through a general `INFO` logger and assuming durability | Levels/filters/queues can drop events | Use a dedicated audit writer, outbox, and pipeline when needed |
| Putting tokens/passwords in `changes.before/after` | Leaks sensitive data | Redact and store only non-secret metadata |
| Assuming an append-only file is tamper-proof | Admins can still modify/delete it | Least privilege and protected anchors/hashes/signatures |
| Applying trace sampling to mandatory audits | Required events can be dropped | Separate sampling policies |
| Synchronous network audit writes without timeouts | Logging failures stall business traffic | Define deadlines, failure policies, and contractual buffering |
| Skipping tests for restarts, full queues, and lost ACKs | Silent event loss or duplication | Run failure-injection and reconciliation tests |
| Not auditing changes to audit config | Privileged users can disable trails undetected | Independent monitoring and administrative access controls |

## 16. Checklist for Java Services

- [ ] Is the audit event catalog and set of mandatory actions defined from risk and business requirements?
- [ ] Does each event include `event_id`, timestamp, actor, target, action, outcome, reason, and necessary correlation IDs?
- [ ] Are actor and outcome derived from **verified** identity/decisions rather than arbitrary client headers or messages?
- [ ] Are success, denial, failure, pending, and rollback accurately represented at the commit point?
- [ ] Are schema versioning, validation, escaping, and length limits in place to prevent log injection?
- [ ] Are secrets, plaintext credentials, and unnecessary sensitive fields excluded?
- [ ] Is there a transaction/outbox strategy or sufficiently durable storage when auditing is mandatory?
- [ ] Are retries, idempotency, deduplication, and the exact meaning of ACKs designed and documented?
- [ ] Are retention, view/delete/export permissions, and tamper resistance defined per policy?
- [ ] Are metrics, heartbeats, end-to-end probes, missing/duplicate reconciliation, and pipeline failure alerts in place?
- [ ] Do integration tests cover both `SUCCESS` and `DENIED` events, crashes/restarts, and concurrent requests?

**Conclusion:** a good audit event is **structured evidence of an action**, not just a message line. In Java, design clear actor–action–target–outcome semantics, record meaningful before/after state, separate sensitive data, and apply appropriate storage and reconciliation mechanisms. Accountability is trustworthy only when events have **accurate content, accurate timing, sufficient durability, tamper protection, and remain queryable when needed**.
