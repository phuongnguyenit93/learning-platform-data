# Operation Outcomes in Java Audit Logging

## 1. Why Must Audit Logging Record Operation Outcomes?

A valuable audit log must help readers answer: **who performed or requested what action, on which resource, at what time, and what was the actual outcome?** Simply logging `User changed role` can be misleading: the request may have been denied, the input invalid, the database rolled back, only part of the data updated, or a job merely accepted to run later.

Example log records:

```text
actor=admin-1 action=ROLE_CHANGE target=user-7 outcome=SUCCEEDED reason=APPLIED
actor=guest-9 action=ROLE_CHANGE target=user-7 outcome=DENIED reason=NOT_AUTHORIZED
actor=admin-1 action=ROLE_CHANGE target=user-7 outcome=NO_CHANGE reason=ALREADY_SET
```

All three requests target the same type of operation, yet **do not share the same business outcome**. That difference determines how you investigate, aggregate metrics, alert, and prove whether a change actually occurred.

Four concepts must be separated:

- **Request/attempt:** a user or system requested that an action be performed.
- **Decision:** the system authenticates, checks permissions, and evaluates business conditions.
- **Business outcome:** the operation is executed and either achieves or fails to achieve its goal according to the contract.
- **Audit delivery:** how far the outcome record has been sent/stored: created in memory, enqueued, processed by an appender, acknowledged by a collector, or durably persisted.

An event with `outcome=SUCCEEDED` can accurately reflect that the database committed, yet **the event itself is still lost** if the logging pipeline fails. Conversely, a `DENIED` event can be successfully audited even though no business data was updated.

**Principle:** do not equate `logger.info(...)` returning, an API returning HTTP 200, or a Java method not throwing an exception with a verified operation outcome and durable audit persistence.

## 2. Outcome Fields in an Audit Schema

An outcome event typically contains the following information:

| Field | Meaning | Notes |
| --- | --- | --- |
| `eventId` | ID of a single audit event | Used to detect duplicate deliveries; must be unique within its scope |
| `operationId` | ID of a logical business action | Kept the same across retries or async steps |
| `attemptId` / `attemptNo` | ID/number of an operation attempt | Separates individual attempts from the final outcome |
| `actorType`, `actorId` | Who requested or performed the action | Must be derived from an authenticated principal/service identity |
| `action` | Standardized action type name | Use a system-managed enum/list |
| `resourceType`, `resourceId` | The target object acted upon | Limit sensitive data and prevent log injection |
| `outcome` | Outcome in business semantics | Finalize only when sufficient state is known |
| `reasonCode` | Reason as a stable code | Do not copy raw exception messages or tokens |
| `occurredAt` | Time the event occurred at the source | Distinct from when the collector ingests it |
| `requestId` / `traceId` | Links the event to a request or trace | Do not use secrets as correlation IDs |
| `schemaVersion` | Schema version of the event | Supports consumer compatibility |
| `durationMs` | Processing time within a defined boundary | Not proof that the operation committed |

Example JSON event:

```json
{
  "schemaVersion": 1,
  "eventId": "ev-001",
  "occurredAt": "2026-01-01T10:00:00Z",
  "service": "identity-service",
  "operationId": "op-19",
  "requestId": "req-19",
  "actor": { "type": "USER", "id": "admin-1" },
  "action": "ROLE_CHANGE",
  "resource": { "type": "USER_ROLE", "id": "user-7" },
  "outcome": "SUCCEEDED",
  "reasonCode": "APPLIED",
  "durationMs": 37
}
```

The IDs, timestamps, and service name in the JSON are for illustration only. If real identifiers constitute personal data, minimize/pseudonymize them, enforce access control, and set appropriate retention. Never put bearer tokens, session cookies, or credentials into `actor.id`, `resource.id`, or `requestId`.

**Outcome** and **severity** are not the same field: `INFO` does not mean `SUCCEEDED`, `WARN` is not automatically `DENIED`, and `ERROR` does not guarantee a rollback happened. Log level serves diagnostics and operations; outcome describes the business result.

## 3. Common Outcome Values

A taxonomy can start with:

| Outcome | Business Meaning | Example |
| --- | --- | --- |
| `SUCCEEDED` | Goal achieved and confirmed at the defined boundary | New role committed |
| `DENIED` | Authentication/authorization policy does not allow it | Actor lacks export permission |
| `REJECTED` | Input or business precondition invalid before any change | Role does not exist, constraint violation |
| `FAILED` | Execution was attempted and the goal is known not to be met | Transaction rollback confirmed |
| `NO_CHANGE` | Request is valid, but state already matched the desired state | Reassigning the same role |
| `PENDING` | Request accepted, final outcome not yet available | Background job enqueued |
| `PARTIALLY_SUCCEEDED` | Part of the request took effect | 8/10 items in a bulk update succeeded |
| `CANCELED` | Workflow canceled per contract with known canceled state | Queued job canceled |
| `UNKNOWN` | Insufficient evidence to determine the outcome | Timeout after sending command to external party |

This is a **schema suggestion**, not a built-in enum in Java, SLF4J, JUL, Logback, or Log4j2. A simpler system can use fewer states; a multi-step workflow may need `ROLLED_BACK`, `COMPENSATED`, or `EXPIRED`. Define the semantics precisely and version them.

### Key Distinctions

**DENIED vs. REJECTED.** `DENIED` is caused by policy/permission, whereas `REJECTED` is typically due to an invalid request or unsatisfied business conditions. If returning a detailed reason would disclose whether a resource exists, internal audit rules and external responses can differ: internal audit records the authorized code, while the API returns a safe message.

**FAILED vs. UNKNOWN.** A timeout does not prove the remote operation failed. The receiver may have committed and then the response or acknowledgement was lost. When uncertain, use `UNKNOWN` or a reconciliation state—do not mark it `FAILED` and blindly retry afterward.

**NO_CHANGE is not a failure by default.** For an idempotent `PUT` API, performing no mutation because the state is already correct can fully satisfy the request.

**PENDING is not final success.** HTTP `202 Accepted`, a queue accepting a job, or a service starting execution only confirms one step in the lifecycle.

**PARTIALLY_SUCCEEDED needs quantitative details.** Recording only a "partial" label is not enough to reconstruct what changed. You can add success/failure counts and link per-resource events, but do not put lists of sensitive data into broadly collected logs.

## 4. Finalizing the Outcome at the Right Time

A common mistake:

```java
// WRONG: declaring success before the transaction completes.
logger.info("Audit action=ROLE_CHANGE outcome=SUCCEEDED");
repository.updateRole(userId, role);
transaction.commit();
```

If `updateRole` or `commit` fails, the event has already recorded the wrong outcome. This is only an illustrative snippet in code that already has a logger/repository/transaction, not a standalone program.

Semantically correct flow:

```text
Request
   |
   +-- Check actor/permission -- failed -----> DENIED
   |
   +-- Validate business input -- failed ----> REJECTED
   |
   v
Execution
   |
   +-- State already as desired -------------> NO_CHANGE
   |
   +-- Clear error, rollback confirmed ------> FAILED
   |
   +-- Commit result unknown ----------------> UNKNOWN
   |
   +-- Commit succeeded ---------------------> SUCCEEDED
```

A few points to watch:

1. Know your **commit boundary**. `executeUpdate()` returning without throwing an exception before the transaction commits is not enough to conclude a durable outcome.
2. Check affected row counts or verify the change condition. An update returning 0 rows should not automatically become `SUCCEEDED` if the resource does not exist or a version conflict occurred.
3. When an operation has side effects outside the database (network, email, payment, files), a database rollback does not automatically undo those side effects.
4. If an error occurs after a transaction might have committed and the client lost connectivity, reconcile the outcome using a reliable ID/idempotency key.
5. If the system recovers from errors via retries, individual attempts may fail while the final logical operation succeeds; keep those two levels distinct.

Do not log both `SUCCEEDED` and `FAILED` for the same **final outcome** just because two layers of code both have catch/finally blocks. If you want to audit multiple attempts, use separate `attemptId` or `eventType` values so readers understand what each event describes.

## 5. Do Not Infer Outcome Directly from HTTP Status Codes or Exceptions

| Signal | What You Can Know | What You Must Not Infer |
| --- | --- | --- |
| `200 OK` | API processed the request per contract | All background tasks are finished |
| `201 Created` | Resource created per contract | Audit sink has durably persisted the event |
| `202 Accepted` | Command accepted for later processing | Final task `SUCCEEDED` |
| `400 Bad Request` | Request considered invalid | Always an infrastructure `FAILED` |
| `403 Forbidden` | Permission denied | `DENIED` audit event was successfully persisted |
| `409 Conflict` | Condition or version conflict | Cannot be resolved via retry/reconciliation |
| `500 Internal Server Error` | Server encountered an error | No side effects were committed |
| `504 Gateway Timeout` | Gateway timed out waiting | Backend definitely did not process it |

Also distinguish Java exceptions from outcomes:

- Not throwing an exception **does not prove** an async task has completed.
- An exception after commit does not turn a committed change into a failure; it may be an error sending the response or writing the audit log.
- Catching every `Exception` and always emitting `FAILED` can mask `UNKNOWN` or `PARTIALLY_SUCCEEDED` cases.
- Failures when writing to the **audit sink** should not be misattributed as the business operation's outcome, unless the contract specifies fail-closed behavior.

Auditing must rely on an explicitly defined outcome decision in the application, not on parsing stack traces or concatenating exception messages.

## 6. Reason Codes and Event Types

Manage `reasonCode` as a stable code set, which can be grouped by category:

| Category | Example Reason Code | Meaning |
| --- | --- | --- |
| Applied successfully | `APPLIED` | Mutation achieved its goal |
| Idempotent | `ALREADY_SET` | Already in the desired state, no change needed |
| Security | `NOT_AUTHORIZED` | Insufficient permissions |
| Validation | `INVALID_ROLE` | Invalid role name |
| Data | `TARGET_NOT_FOUND` | Target does not exist (if policy permits disclosure) |
| Concurrency | `VERSION_CONFLICT` | Optimistic lock no longer matches |
| Infrastructure | `DEPENDENCY_UNAVAILABLE` | Dependency temporarily unavailable |
| Uncertain | `RESULT_UNCONFIRMED` | Needs reconciliation |
| Bulk | `PARTIAL_APPLY` | Only part of the operation was applied |

**Do not use `exception.getMessage()` as a reason code.** It can change across library versions and may contain URLs, SQL, tokens, or user data. Instead, use predefined codes; if diagnostic details are needed, put safe information in a separate operational log with appropriate access controls.

For multi-step workflows, also separate `eventType`:

- `REQUESTED`: the request arrived.
- `ACCEPTED_FOR_PROCESSING`: the system committed to attempting execution.
- `STARTED`: a worker actually began processing.
- `ATTEMPT_FINISHED`: a single execution attempt finished.
- `OPERATION_FINISHED`: final outcome of the logical operation.

`eventType` states which stage the event belongs to; `outcome` states the result at that stage. You do not have to emit all of these events for every operation, but once emitted, keep their definitions stable so consumers do not miscount.

## 7. Standalone Java 17 Example: Recording Role Change Outcomes

The following example has no external library dependencies. It simulates a `ROLE_CHANGE` operation and stores `AuditEvent` records in a list. The goal is to demonstrate **matching outcomes to business branches**, not to show a durable audit pipeline.

### 7.1. Create `AuditOutcomeDemo.java`

```java
import java.time.Instant;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

public class AuditOutcomeDemo {
    enum Outcome {
        SUCCEEDED, NO_CHANGE, DENIED, REJECTED, FAILED
    }

    record Decision(Outcome outcome, String reasonCode) {}

    record AuditEvent(
            String eventId,
            Instant occurredAt,
            String requestId,
            String actorId,
            String action,
            String resourceId,
            Outcome outcome,
            String reasonCode
    ) {}

    static final class RoleService {
        private final Map<String, String> roles =
                new HashMap<>(Map.of("user-7", "viewer"));

        Decision changeRole(
                String actorId, String targetId, String desiredRole) {

            if (!"admin-1".equals(actorId)) {
                return new Decision(
                        Outcome.DENIED, "NOT_AUTHORIZED");
            }

            if (!"viewer".equals(desiredRole)
                    && !"editor".equals(desiredRole)) {
                return new Decision(
                        Outcome.REJECTED, "INVALID_ROLE");
            }

            // Simulate dependency failure before modifying data.
            if ("user-offline".equals(targetId)) {
                return new Decision(
                        Outcome.FAILED, "DEPENDENCY_UNAVAILABLE");
            }

            if (!roles.containsKey(targetId)) {
                return new Decision(
                        Outcome.REJECTED, "TARGET_NOT_FOUND");
            }

            if (desiredRole.equals(roles.get(targetId))) {
                return new Decision(
                        Outcome.NO_CHANGE, "ALREADY_SET");
            }

            roles.put(targetId, desiredRole);
            return new Decision(Outcome.SUCCEEDED, "APPLIED");
        }

        String currentRole(String targetId) {
            return roles.get(targetId);
        }
    }

    private static void attempt(
            RoleService service, List<AuditEvent> audit,
            String eventId, String actorId, String targetId,
            String desiredRole, String requestId) {

        Decision decision =
                service.changeRole(actorId, targetId, desiredRole);

        // Fixed mock timestamp so the example is reproducible.
        Instant time = Instant.parse("2026-01-01T10:00:00Z")
                .plusSeconds(audit.size());

        AuditEvent event = new AuditEvent(
                eventId, time, requestId, actorId,
                "ROLE_CHANGE", targetId,
                decision.outcome(), decision.reasonCode());

        audit.add(event); // In-memory only; NOT durable.
        System.out.println(
                event.eventId() + " " + event.outcome()
                        + " " + event.reasonCode());
    }

    public static void main(String[] args) {
        RoleService service = new RoleService();
        List<AuditEvent> audit = new ArrayList<>();

        attempt(service, audit, "EV-001",
                "admin-1", "user-7", "editor", "req-1");
        attempt(service, audit, "EV-002",
                "admin-1", "user-7", "editor", "req-2");
        attempt(service, audit, "EV-003",
                "guest-9", "user-7", "viewer", "req-3");
        attempt(service, audit, "EV-004",
                "admin-1", "user-7", "owner", "req-4");
        attempt(service, audit, "EV-005",
                "admin-1", "user-offline", "editor", "req-5");

        System.out.println("finalRole="
                + service.currentRole("user-7"));
        System.out.println("auditEvents=" + audit.size());
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac AuditOutcomeDemo.java
java AuditOutcomeDemo
```

**Exact stdout:**

```text
EV-001 SUCCEEDED APPLIED
EV-002 NO_CHANGE ALREADY_SET
EV-003 DENIED NOT_AUTHORIZED
EV-004 REJECTED INVALID_ROLE
EV-005 FAILED DEPENDENCY_UNAVAILABLE
finalRole=editor
auditEvents=5
```

### 7.2. Interpreting the Results

- **EV-001:** valid admin changes `user-7` from viewer to editor; the map is updated and returns `SUCCEEDED`.
- **EV-002:** assigning editor again requires no mutation; `NO_CHANGE` is a distinct, meaningful outcome.
- **EV-003:** guest lacks permission; `DENIED` is decided before checking role/resource details, reducing information disclosure to unauthorized actors.
- **EV-004:** valid admin, but `owner` is not in the whitelist, so `REJECTED`.
- **EV-005:** the dependency is simulated as unavailable **before mutation**, so `FAILED` is the accurate conclusion in this model. If a failure happens after an unreconciled side effect, use `UNKNOWN`/`PARTIAL` instead of assuming no change occurred.
- `finalRole=editor` proves only the first request mutated state; `auditEvents=5` proves all five decisions produced an event, not that five mutations occurred.

**Limitations:** `ArrayList` and `HashMap` are not durable, not thread-safe, and not atomic with each other. If the program crashes or `audit.add` fails after mutation, audit records can be lost. The clock and IDs are hardcoded solely for reproducible stdout. In a real system, use reliable IDs/timestamps, transactions, and proper persistence/synchronization; do not use this example as a production implementation.

Java `record` keeps event fields immutable at the field level, but if a record holds a mutable object, that object can still be modified. When building structured audit events, prefer simple/immutable values and snapshot context at the moment the outcome is verified.

## 8. Audit Outcomes for Asynchronous Operations

An API receives a report-generation command and processes it via a job queue:

```text
T0: POST /reports -> HTTP 202 Accepted
    eventType=REQUESTED; outcome=PENDING; operationId=op-81

T1: Worker receives and starts running
    eventType=STARTED; operationId=op-81

T2: Worker creates file and commits state
    eventType=OPERATION_FINISHED
    outcome=SUCCEEDED or FAILED; operationId=op-81
```

**T0 is not T2.** If the audit action is `EXPORT_REQUEST_ACCEPTED`, then `SUCCEEDED` at T0 can be accurate for the action of accepting the request. However, if the action is `EXPORT_COMPLETED`, T0 is only `PENDING`. Every system must define actions clearly so both sides interpret them the same way.

With an append-only audit trail, emit a new event when the state transitions:

```json
{"eventId":"ev-201","operationId":"op-81","eventType":"REQUESTED","outcome":"PENDING"}
{"eventId":"ev-202","operationId":"op-81","eventType":"OPERATION_FINISHED","outcome":"SUCCEEDED"}
```

Do not silently overwrite `PENDING` with `SUCCEEDED` in the old audit record if you need state-transition history. You can maintain an additional `current_operation_status` table for fast queries of the final state alongside the append-only audit trail.

### When a Job Fails or Reports No Outcome

- If the worker confirms rollback with no side effects: `FAILED`.
- If the job is canceled with confirmation: `CANCELED`.
- If part of the work took effect: `PARTIALLY_SUCCEEDED` or an outcome per the saga contract.
- If the worker loses connectivity after sending a command to another system: `UNKNOWN` until reconciled.
- If `PENDING` exceeds the SLA: raise a `stale pending` alert; do not automatically flip it to `FAILED` without evidence.
- If the job is retried: link attempts via `operationId` and ensure the final outcome is not recorded multiple times misleadingly.

In distributed systems, machine clocks can skew and events can be ingested out of generation order. Use IDs, scoped sequences where guaranteed, causal relationships, and both source and ingest timestamps to reconstruct the timeline.

## 9. Retries, Idempotency, and Duplicate Events

Example of a logical operation:

```text
operationId=op-7
 attempt=1 -> FAILED (transient dependency error)
 attempt=2 -> FAILED (transient dependency error)
 attempt=3 -> SUCCEEDED
 logical final outcome -> SUCCEEDED
```

**Attempt** metrics show two failures and one success; **operation** metrics show one successful final action. Do not mix the two denominators and misreport customer failure rates.

| Identifier | Scope | Behavior on Retry |
| --- | --- | --- |
| `eventId` | A single audit event | When resending the same event due to lost ack, keep the ID for dedup |
| `operationId` | A single logical action | Remains the same across retries and async steps |
| `attemptId` / `attemptNo` | A single execution attempt | Each attempt gets its own ID or number |
| `requestId` | A specific HTTP/request call | May change when the client sends a new request |
| `traceId` | A distributed trace | May change across retries depending on architecture |

Receiving the same `eventId` twice at the collector due to replay is **duplicate delivery**, not necessarily two operations. If consumers care about uniqueness, use idempotent processing/deduplication. Retries or transactional outboxes typically provide at-least-once delivery; **they do not automatically provide end-to-end exactly-once**.

### `NO_CHANGE` and Idempotent Requests

For `PUT /users/7/role=editor`, a second request may perform no mutation because the system already has `editor`. A `NO_CHANGE` outcome helps distinguish:

- The request was **valid, and the goal is already met**.
- Data was **not modified again**.
- There is no error requiring operational attention.

If the API contract only exposes HTTP 200, the audit log can still record `outcome=NO_CHANGE` for internal analysis; do not force it to `FAILED`.

## 10. Bulk Operations, Partial Success, and Compensation

A single request can affect multiple resources. Suppose an admin assigns roles to 10 users: 8 succeed and 2 fail after part of the changes have committed. The overall audit event might look like:

```json
{
  "operationId": "op-bulk-41",
  "action": "BULK_ROLE_CHANGE",
  "outcome": "PARTIALLY_SUCCEEDED",
  "reasonCode": "PARTIAL_APPLY",
  "requestedCount": 10,
  "succeededCount": 8,
  "failedCount": 2
}
```

The aggregate outcome should link to per-item events or a detail table with appropriate access controls. Do not log full emails/PII to explain the outcome when safely evaluated resource IDs suffice.

**If the entire operation runs in a single transaction and rolls back**, the committed result may be 0; in that case, do not record `PARTIALLY_SUCCEEDED` just because the code ran 8 `UPDATE` statements before rolling back. `PARTIALLY_SUCCEEDED` is only valid when partial side effects **took effect** and were not rolled back as a whole.

### Sagas and Compensation

For example, if an access-granting step committed, a notification step failed, and the system runs compensation to revoke the access:

1. Record the access-granting step event as `SUCCEEDED`.
2. Record the notification step event as `FAILED`.
3. Record the compensation attempt event and its actual outcome.
4. Record the final outcome event of the entire operation per the contract.

Do not delete or rewrite the first event as "never succeeded" just because the final state reverted to the original state. **An audit trail describes what happened**, not only the current snapshot.

## 11. Reliable Audit Persistence: Transactional Outbox

Unsafe approach:

```text
COMMIT role change succeeded
    |
    v
logger.info("ROLE_CHANGE SUCCEEDED")
    |
    X  process crash before log reaches sink
    |
    v
Data changed but audit event is missing
```

When business state and the audit event can reside in the **same database transaction**, the transactional outbox pattern helps close this gap:

```text
Database transaction
+--------------------------------------+
| UPDATE business state                |
| INSERT audit_outbox event            |
+--------------------------------------+
              COMMIT
                 |
                 v
         Outbox dispatcher
         retry + dedup + ack
                 |
                 v
            Audit sink
```

Illustrative pseudocode, not a complete script for every RDBMS:

```sql
BEGIN;

-- Check permissions, conditions, version, and updated row count
-- with the required isolation/locking.
UPDATE user_roles
SET role = 'editor'
WHERE user_id = 'user-7';

-- Only use SUCCEEDED if the update condition is verified.
INSERT INTO audit_outbox (
    event_id, operation_id, action,
    resource_id, outcome, reason_code
) VALUES (
    'ev-501', 'op-501', 'ROLE_CHANGE',
    'user-7', 'SUCCEEDED', 'APPLIED'
);

COMMIT;
```

If the `UPDATE` does not match the resource/version, do not blindly record success; check the row count and conditions. Within the transaction, the mutation and the outbox insert commit or roll back together.

The dispatcher sends committed events to the collector and only marks them delivered once the protocol-defined acknowledgement is reached. If the collector receives an event and the response/ack is lost, the dispatcher may resend it; `eventId` and deduplication are essential.

**Outbox does not guarantee exactly-once by itself.** It solves atomicity between business state and storing the pending event in one transaction. Collector durability, delivery ordering, retention, and reconciliation are separate contracts.

### Auditing Outcomes Without a Business Commit

`DENIED` and `REJECTED` usually produce no mutation. `FAILED` due to a business transaction rollback also leaves no outbox event inserted **inside the rolled-back transaction**. Therefore, these outcomes may require a separate audit transaction or a dedicated secure audit channel. Do not put a `DENIED` audit record inside a transaction that rolls back and then wonder why the record disappeared.

If business rules require **not completing an operation when audit cannot be persisted**, design fail-closed behavior with appropriate ack/commit boundaries. Do not apply this blindly to every log, as a slow collector could make the entire API unresponsive.

## 12. Integrating with SLF4J/Logback: Do Not Confuse Log Messages with Audit Contracts

SLF4J is a facade; a backend like Logback receives messages, markers, and context. It does not provide business outcomes out of the box. The application must define the event and appropriate persistence policy.

Illustrative snippet in an application with a declared logger and variables:

```java
logger.info(
    "audit action={} eventId={} operationId={} actorId={} "
        + "resourceId={} outcome={} reasonCode={}",
    "ROLE_CHANGE",
    eventId,
    operationId,
    actorId,
    resourceId,
    outcome,
    reasonCode
);
```

This writes a **plain-text message**, not automatically a JSON/structured event. If downstream systems need to query individual fields, use a structured logging API/encoder that supports it and verify the output at the collector. Do not just embed fields in a text string and assume parsers will always extract them accurately.

Specifically:

- Logger levels/filters can drop an `INFO` audit event when `root=WARN`.
- An async appender can drop events under its discard/backpressure policy.
- In-memory queues are not durable across JVM/host crashes.
- `logger.info` returning does not prove the collector received the event.
- A logging exception may be reported via the backend's status channel rather than thrown to the business thread.
- MDC helps with correlation, but does not automatically propagate across every `ExecutorService` or async boundary; you must manage context and clear/restore it in `finally`.

For critical auditing, separate the high-reliability/retention event stream from debug logs that may be sampled or dropped. Audit events can still be emitted as logs as well, but the source of truth for outcomes should follow the appropriate contract.

## 13. Testing for Accurate Business Outcomes

Test **both business state and audit events**.

| Case | State After Request | Outcome | Reason |
| --- | --- | --- | --- |
| Valid role change and commit | New role takes effect | `SUCCEEDED` | `APPLIED` |
| Actor lacks permission | Role unchanged | `DENIED` | `NOT_AUTHORIZED` |
| Disallowed role | Role unchanged | `REJECTED` | `INVALID_ROLE` |
| Reassign current role | Role unchanged | `NO_CHANGE` | `ALREADY_SET` |
| DB error, rollback confirmed | No commit | `FAILED` | `STORAGE_ERROR` |
| Connection lost after commit command | State unknown | `UNKNOWN` | `RESULT_UNCONFIRMED` |
| Job enqueued | Not yet completed | `PENDING` | `ACCEPTED_FOR_PROCESSING` |
| Bulk 8/10 succeeded | 8 changes took effect | `PARTIALLY_SUCCEEDED` | `PARTIAL_APPLY` |

Place tests at the right boundaries:

1. **Unit tests** mapping policy/input → `Decision`, without real logging infrastructure when not needed.
2. **Integration tests** using repositories/transactions and a test sink to reconcile state against events.
3. **Fault-injection tests** forcing rollbacks, commit errors, timeouts, and sink outages, verifying no false `SUCCEEDED` is recorded.
4. **End-to-end tests** verifying events reach the required audit store with proper IDs, timestamps, and schema.
5. **Security tests** using dummy tokens to confirm they never appear in fields, messages, exceptions, or MDC.

A JUnit 5 example testing the logic from Section 7 (illustrative test code; requires JUnit Jupiter on the classpath, not a standalone file run with `javac` alone):

```java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class RoleOutcomeTest {
    @Test
    void idempotentRoleChangeIsNotAFailure() {
        AuditOutcomeDemo.RoleService service =
                new AuditOutcomeDemo.RoleService();

        var first = service.changeRole(
                "admin-1", "user-7", "editor");
        var second = service.changeRole(
                "admin-1", "user-7", "editor");

        assertEquals(
                AuditOutcomeDemo.Outcome.SUCCEEDED, first.outcome());
        assertEquals(
                AuditOutcomeDemo.Outcome.NO_CHANGE, second.outcome());
        assertEquals("ALREADY_SET", second.reasonCode());
    }
}
```

This test only verifies **decision logic**. It does not verify that an audit event was durably persisted. To prove audit delivery, use a dedicated sink/repository and assert at the actual persistence point rather than merely mocking `logger.info`.

## 14. Testing Retries, Concurrency, and Reliability

For retries and transactions:

- Simulate a process restart after business commit but before the dispatcher sends; the outbox event must still exist.
- Collector receives the event and loses the ack; retries may produce duplicates, requiring deduplication by `eventId`.
- Workers emit multiple events in parallel; if global ordering is not guaranteed, do not assert cross-producer ordering.
- An operation that times out after calling an external service must be reconciled by operation ID, not immediately flipped to `FAILED`.
- When concurrent updates cause a version conflict, the failing request must record the appropriate outcome, not `SUCCEEDED` just because an earlier step completed.
- If the audit sink fails, observe metrics/backlog or fail-closed policy; do not conflate audit-path errors with business outcomes unless the contract requires it.

When testing async logging, use a `BlockingQueue` or latch at the sink with `poll(timeout)`; avoid `Thread.sleep(500)` and hoping for the best. For events that **must not appear**, use a sentinel/barrier or drain point based on the backend's contract rather than concluding absence after a short wait.

When a service uses thread pools, capture and restore correlation ID/MDC per task; do not let request B carry request A's `operationId`. An immutable event is only safe at its data level; shared databases, queues, and lists still require synchronization.

## 15. Security and Integrity of Audit Results

**Auditing is untrustworthy if any client can choose its own actor and outcome.**

- Derive the actor from a verified authenticated principal or service identity; never trust `actorId` from the request body.
- Have the server determine `outcome` after checking the actual result; never accept a client-reported `"success"` string.
- Validate/canonicalize resource IDs, enforce length limits, and encode safely to prevent log injection.
- Never log passwords, session cookies, access/refresh tokens, private keys, raw request bodies, or stack traces containing secrets.
- Use controlled reason codes; never copy raw exception messages freely.
- Separate read/write/delete/export permissions for audit data; control retention, backups, and policy changes.
- If your threat model requires it, store append-only/immutable records and protect hashes/signatures/chain of custody in a trusted location. A hash stored next to a file that an attacker can also modify does not guarantee integrity on its own.
- When exporting or investigating, use restricted-access channels and do not copy sensitive data into broadly accessible tickets or chats.

Audit schemas also need versioning. If you change `FAILED` to `REJECTED` for the same condition, document the semantic change so dashboards, alerts, and historical reports are not misinterpreted.

## 16. Monitoring Audit Outcome Quality

Useful metrics (names are **examples**, not built-in Logback metrics):

| Metric | Purpose |
| --- | --- |
| `audit_events_total{action,outcome}` | Outcome breakdown per action |
| `audit_outbox_pending` | Committed events not yet delivered |
| `audit_oldest_pending_age_seconds` | Maximum backlog latency |
| `audit_delivery_errors_total` | Sink send/storage errors |
| `audit_duplicate_events_total` | Duplicate events detected |
| `audit_unknown_operations` | Outcomes awaiting reconciliation |
| `audit_stale_pending_operations` | Jobs without a final outcome past SLA |
| `audit_partial_operations_total` | Operations with partial outcomes |

Do not use `eventId`, `actorId`, or `resourceId` as metric labels due to very high cardinality and data exposure risks. Keep detailed information in a controlled audit store.

Signals to alert on: unusual spikes in `DENIED`, increases in `FAILED` after deployments, long-lived unreconciled `UNKNOWN` outcomes, an outbox backlog that stops draining, or committed operations not matching `SUCCEEDED` events under a reliable reconciliation method. Do not attribute every missing event to attacker tampering; filters, queue overflows, collector outages, or bad queries are also common causes.

## 17. Common Mistakes When Recording Operation Outcomes

| Mistake | Impact | Remedy |
| --- | --- | --- |
| Logging success before commit | False audit record on rollback | Finalize outcome after verification boundary |
| Using boolean success/fail for everything | Loses deny/reject/no-change/partial/unknown | Use an appropriate outcome taxonomy |
| Treating HTTP 202 as completion | Misreports background jobs | Use `PENDING` and a final event |
| Treating timeout as definite failure | Retries may cause duplicate side effects | `UNKNOWN` + reconcile |
| Setting reason from exception message | Unstable and can leak secrets | Managed safe codes |
| Conflating attempt and operation | Failure counts get inflated | Operation ID + attempt ID |
| Not logging denied/rejected | Missing evidence of blocked access | Audit on a non-rolling-back path |
| Recording 8/10 as full success | Hides surviving side effects | `PARTIALLY_SUCCEEDED` + counts |
| Treating INFO logger as durable | Logs filtered, dropped, or lost on crash | Outbox/ack/spool when needed |
| Putting client actor/outcome in events | Outcomes can be forged | Derive from trusted server context |
| Tests only verify logger was called | Does not prove business state | Assert state + event + storage |
| Deleting old events after compensation | Loses history of what happened | Append-only event trail |
| Printing raw request/exception for failures | Leaks secrets/PII, log injection | Field allowlist + reason code |

## 18. Implementation Workflow in a Java Project

1. **List actions to audit:** role changes, exports, config changes, sensitive data operations, and mandatory audit actions.
2. **Define outcomes and `reasonCode`s** for each action; determine what qualifies as `PENDING` versus `SUCCEEDED`.
3. **Design the schema** with version, trusted actor, resource, event ID/operation ID, timestamp, and minimum required fields.
4. **Map every business branch:** permission denied, input rejected, idempotent no-change, commit success, failure with rollback, unknown state.
5. **Separate attempts from logical operations** for retry/async workflows; define which level consumers count.
6. **Choose the audit persistence path:** event store/outbox/collector with appropriate ack, retention, and permissions; do not rely solely on a droppable debug logger.
7. **Build a test matrix** covering success, deny, reject, no-change, partial, timeout, conflict, compensation, restart, and collector outage.
8. **Define reconciliation** between business state and audit events to catch missing events or mismatched outcomes.
9. **Set up monitoring and runbooks:** backlog, failures, unknown, stale pending, and audit access controls.
10. **Review the schema on every change:** never silently alter the meaning of `SUCCEEDED`, `FAILED`, or `reasonCode`.

## 19. Knowledge Checklist

- [ ] Every event has a clear action and outcome, without relying on severity to infer the result.
- [ ] Outcomes are finalized at the right business boundary; success is never logged before commit.
- [ ] `DENIED`, `REJECTED`, `NO_CHANGE`, `FAILED`, and `UNKNOWN` are distinguished where meaningful.
- [ ] Async jobs have an initial state and final outcome linked by the same `operationId`.
- [ ] Retries separate event ID, operation ID, and attempt ID, and guard against duplicate delivery.
- [ ] Bulk/saga workflows preserve partial/compensation details without hiding committed changes.
- [ ] Reason codes use a managed list; actors come from the security context; no secrets are logged.
- [ ] The audit store provides durability/acks and access controls appropriate to the action.
- [ ] Tests verify business state, events, transactions, and delivery failures together.
- [ ] Metrics/outbox reconciliation are in place to detect missing events, `UNKNOWN`, or stale `PENDING`.

**Key takeaway:** an "operation outcome" is not a success/failure word in a log message. It must reflect **what actually happened** at a verified boundary—including denial, no change, pending, partial success, and unknown state. A sound audit system must also persist that conclusion with the committed durability, access control, and reconcilability.
