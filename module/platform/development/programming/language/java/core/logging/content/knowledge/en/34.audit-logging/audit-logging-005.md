# Audit Timing in Java Core Logging

## Learning Objectives

This lesson belongs to the **Audit logging** group, focusing on **Audit timing**. An audit log is a trail used to investigate **who did what, to which object, when, with what outcome, and under what permissions/context**. An event emitted at an inappropriate time can create false evidence: recording "money transfer succeeded" before the transaction commits, recording "login failed" too late for investigation, or replacing the original timestamp with the collector's receipt time, distorting the event sequence.

After this lesson, you will be able to:

- Distinguish between **occurrence time**, **action start/completion**, **authentication/authorization decision**, **commit**, **audit recording**, **publishing**, and **ingestion**.
- Decide when to audit **attempt**, **denied**, **failed**, **committed**, and **compensated** without misrecording the outcome.
- Design transaction-consistent auditing: inserting an audit row in the same transaction, using a transactional outbox, or using an independent audit stream for denied events.
- Understand clock skew, timezones, timestamp sources, event ordering, retries, duplicates, and asynchronous delivery.
- Write Java 17 code with an injected `Clock` to test timestamps and outcomes with deterministic stdout.
- Build a test matrix for rollback, unknown commit status, crash, retry, access control, and end-to-end traceability.

**Core principle:** An audit trail must describe **the event and state that actually happened**, not what the application only intended to do. At the same time, a **denied attempt** is still an auditable event even when no business state change is committed.

## 1. "Audit Timing" Has at Least Three Meanings

When someone says "audit at 10:00", you need to ask whether that is when the action started, when the system made a decision, when the database committed, or when the log reached the audit system. These milestones can differ significantly.

Example of a role change operation:

```text
t0                 t1                  t2                 t3             t4             t5
| request received| authorization PASS| UPDATE prepared   | DB COMMIT OK   | audit shipped | index visible
|-------------------- business operation -------------------|
             |-- decision moment --|
                                 |------ durable transition --|
|------------------------- event timeline --------------------------------------->

Specific milestones to consider:
- attempt_at       = when the request/attempt is observed
- decision_at      = when the system accepts or denies
- effective_at     = when the change takes effect in the business domain
- committed_at     = when the transaction is confirmed committed (if the system can know)
- recorded_at      = when the audit record is accepted into the audit store/stream
- ingested_at      = when the collector/backend receives it
- searchable_at    = when the event becomes searchable in the index
```

The diagram is only a **conceptual model**. Not every technology provides an actual commit timestamp; the time the application receives the COMMIT OK response is not necessarily identical to the time the database internally confirms the commit. If a milestone cannot be measured reliably, **do not create a precise-sounding field and populate it with a guessed timestamp**.

Common fields:

| Attribute | Meaning | Preferred Authoritative Source |
| --- | --- | --- |
| `occurred_at` / `event_time` | When the event is determined to have occurred by business definition | Clock at the origin or authoritative timestamp provided by the source system |
| `attempted_at` | When the operation/login started | Request entry point or processing start point, with clear semantics |
| `decision_at` | When the authn/authz policy made the decision | Policy decision enforcer |
| `effective_at` | When the change takes effect in the business domain, sometimes in the future or valid past | Domain model or state store |
| `committed_at` | Confirmed commit milestone / commit timestamp if provided by the DB | Database or confirmation receipt point, with a clear definition |
| `recorded_at` | When the audit subsystem received/stored the record | Audit writer or audit store |
| `published_at` | When the event was sent to the broker/collector | Producer/outbox publisher |
| `ingested_at` | When the collector/ingest pipeline received the event | Collector |
| `searchable_at` | When the backend makes the event queryable | Backend/index |

You do not need to include **every field** in every record. You need a consistent schema where meaningful fields are stored, and timestamps without evidence can be `null`/omitted. For an "access decision denied" audit, `decision_at` and `outcome=DENIED` may matter more than `committed_at`, because no role-changing transaction was committed.

### Event Time vs. Processing Time

**Event time** describes when the original event occurred; **processing/ingest time** describes when a pipeline component processed it. For example:

```text
2026-11-10T09:00:04Z  role.changed committed at source
2026-11-10T09:00:05Z  audit row stored locally
2026-11-10T09:01:15Z  collector ingested after outage
2026-11-10T09:01:18Z  event became searchable
```

If a dashboard treats `ingested_at` as the action time, the role change may appear to have occurred more than a minute later. Both the **original event timestamp** and the backend timestamp should be stored when investigating pipeline latency. Do not overwrite `occurred_at` on each retry/reship.

## 2. Choosing the Audit Timing by Event Type

There are two different questions: **"Did someone try?"** and **"What change actually took effect?"**. They require distinct audit events with clearly recorded timestamps.

| Event Type | Appropriate Audit Timing | Core Data |
| --- | --- | --- |
| Login attempt | When the attempt is received or when the authentication decision is made, depending on event type | `attempted_at`, redacted principal/identifier, source, request ID |
| Login denied | When the system makes the denial decision | `decision_at`, `outcome=DENIED`, safe reason code |
| Login succeeded | When the required session or credential/session state is successfully established | `outcome=SUCCESS`; do not record success after only an initial step |
| Authorization denied | When the policy engine/gateway denies the action | Actor, resource, action, `outcome=DENIED`, policy/version |
| Transactional data change | Success event must be consistent with **commit** | `event=role.changed`, old/new values per policy, transaction/record version |
| Transaction rollback | Do not emit a "changed successfully" event; optionally audit the failed attempt separately | `outcome=ROLLED_BACK` or `FAILED`, reason, correlation |
| External API call | Distinguish **request sent**, **acknowledgement received**, and **side effect took effect** | Remote operation ID, outcome, and corresponding timestamps |
| Asynchronous job | Distinguish **queued**, **started**, **completed**, and **failed** | Job ID, attempt number, event time per state |
| Logout / token revocation | When the session/credential invalidation is confirmed at the authoritative system | Actor, masked target session/credential, outcome |
| Security configuration change | Record attempt, decision, and configuration activation separately if needed | Config version, approver, rollout status, affected scope |
| Data deletion | Record request, approval, commit, or deletion completion as appropriate | Redacted resource ID, retention policy, outcome |

**Do not collapse everything into a single "SUCCESS" event as soon as the controller receives the request.** HTTP `202 Accepted` usually only means the job was accepted into a processing mechanism, not that the final side effect succeeded. For long-running flows, a sequence of state-based audit events is more useful than an early but inaccurate record.

### Attempt, Decision, Outcome, and Effect Categories

A clear structure separates:

- `access.attempted`: an access attempt was observed.
- `access.denied` or `access.allowed`: the policy made a decision.
- `role.change.committed`: the data change was committed.
- `role.change.failed`: the attempt failed, with no requested change applied.
- `role.change.compensated`: a compensating action was executed after a prior change.

These event names are just examples. An organization might use `action=role.change` plus `outcome=DENIED/COMMITTED`, as long as the schema and timing are clear. **Do not confuse `attempted` with `committed`**, and do not use a single `failed` event that fails to distinguish authentication errors, validation errors, rollbacks, or unknown-outcome timeouts.

## 3. Success and Transactions: Write Before or After Commit?

This is the core decision of **audit timing**.

### 3.1. Writing a Success Audit Before Commit, Outside the Transaction

```text
Service:
  audit("role.changed", SUCCESS)  ---> audit sink receives
  UPDATE roles ...
  COMMIT                         ---> may ROLLBACK!
```

If the commit fails, the external audit has declared a change that **does not exist**. This is a **false success** and a correctness bug. Calling `logger.info` must never be treated as proof that data was committed.

### 3.2. Writing Audit to an Independent System After Commit

```text
Service:
  UPDATE roles ...
  COMMIT                         ---> succeeds
  audit("role.changed", SUCCESS) ---> may crash before this step!
```

Now the record does not lie if written, but there is an **audit loss gap**: the database changed, and the process is killed or the audit sink is down before the record is saved. For purely observational auditing, a team might accept this risk based on requirements; for mandatory auditing, it is insufficient.

### 3.3. Writing Business State and Audit Row in the Same Database Transaction

When business data and the audit table reside in the same DB/transaction manager with appropriate semantics, you can do:

```sql
BEGIN;

UPDATE user_roles
SET role = 'editor'
WHERE user_id = 'user-17';

INSERT INTO audit_events (
    event_id, action, outcome, subject_id,
    occurred_at, actor_id
) VALUES (
    'evt-role-0001', 'role.change', 'COMMITTED',
    'user-17', CURRENT_TIMESTAMP, 'admin-3'
);

COMMIT;
```

This is **illustrative SQL**, not a standalone migration or application: it requires proper tables, constraints, permissions, and transaction isolation. Across different database management systems, `CURRENT_TIMESTAMP` may reflect the transaction/statement start time or another value, and **is not automatically the exact commit timestamp**. To audit the actual commit time, you must check DB capabilities and field definitions. The SQL above also does not verify that `UPDATE` modified exactly one row; a real application must check the row count and conditions/version to avoid recording "COMMITTED" when nothing changed.

If both `UPDATE` and `INSERT` **succeed in a COMMITted transaction**, they commit together; if the transaction rolls back, both disappear. Setting `outcome=COMMITTED` on the row happens before commit, but it only becomes visible in committed data when the commit succeeds. This works well for **auditing successful changes** in the same DB.

However, you cannot use this same transaction to persist audits of **denied/rolled-back attempts**, because an audit row inserted into a rolled-back transaction will also be lost. "Attempted but failed" events need an independent, durable audit path according to their own requirements.

### 3.4. Transactional Outbox: Business State and Publish Intent Commit Together

When the centralized audit system lives elsewhere, a transactional outbox avoids the gap between commit and publish:

```text
Application:
  BEGIN
    UPDATE business_state
    INSERT outbox_event(event_id, payload, occurred_at, ...)
  COMMIT
               |
               v
Outbox publisher (later, retryable)
               |
         broker/collector
               |
           audit store
```

**Benefits:** The business change and the outbox row in the same transaction can be committed/rolled back atomically (within the same DB). If the process crashes after commit but before publishing, the publisher can re-read the outbox and continue sending.

**Limitations:**

- It usually provides **at-least-once delivery**, not automatic end-to-end exactly-once. The publisher may send successfully but lose the ACK; a retry causes a duplicate.
- The consumer/audit store must be **idempotent** on `event_id` or have appropriate deduplication.
- The original `occurred_at` timestamp must be preserved across retries; `published_at` and `ingested_at` are updated per hop.
- Persisting an event in the outbox does not mean the external audit system has made it searchable or durable yet; metrics and reconciliation are required.
- Audits of attempt/denied events that do not commit with a business transaction may need an independent outbox or audit writer, depending on the data model.

If ordering of changes per aggregate must be preserved, the publisher/consumer must also maintain a per-aggregate key/sequence/version; an outbox alone does not guarantee every event is delivered and stored in order under multiple workers.

## 4. Auditing Failed, Denied, and Rolled-Back Operations

A **DENIED** decision involves no state change, yet it is a critical security event. You cannot wait for a database transaction to "succeed" to record a rejected action.

Example of a permission change request:

```text
request received
  -> identify principal
  -> check authentication
  -> check authorization
       +-> DENIED
       |     +-> emit audit(access.denied, outcome=DENIED)
       |     +-> return 403
       |
       +-> ALLOWED
             +-> BEGIN business transaction
             +-> UPDATE role, audit row or outbox
             +-> COMMIT
             +-> report outcome COMMITTED
```

This is a decision-flow diagram; in real production systems, authn may fail before the exact principal is known, and audit writing depends on the architecture. Log only **permitted identifiers**—do not stuff passwords or bearer tokens into the audit log for "complete evidence".

### Common Mistakes

- Recording `access.allowed` as soon as a token is valid even though the final policy still denies the action.
- Recording `role.changed` before the transaction commits.
- Creating a denied audit row inside the very transaction that will roll back, causing the row to vanish too.
- Recording `FAILED` on a client timeout when the backend may have committed; the outcome may be **UNKNOWN** and require reconciliation.
- Skipping denial events because "no data changed", losing the trail of attack attempts.
- Recording every failed retry as an independent business change instead of distinguishing **attempt** from **logical operation**.

**Not every attempt must become an unbounded record.** A system may need sampling, rate limiting, or aggregation for massive volumes of denied requests, but the audit/security policy must approve it and still retain sufficient trace per requirements. Do not apply debug-log filters to mandatory audit trails without verification.

### When the Audit System Itself Is Unavailable

Choose **fail-open** (business continues, missing audit is flagged for later handling) or **fail-closed** (reject the operation when auditing cannot be guaranteed) based on risk/compliance level and service design. There is no universal right choice:

- Sensitive administrative privilege changes may require a durable audit before returning success.
- Low-risk read-only operations may prioritize availability and appropriate buffering.
- If rejecting an operation because auditing is down, that rejection itself may need to be reported to an independent operations channel without creating an infinite logging loop.

Do not turn an ordinary logger into a transaction consistency boundary without a clear contract for durability and error propagation.

## 5. Audit Schema: Accurate Timestamps and Context

An audit record can use a conceptual schema:

```json
{
  "event_id": "evt-4e7b",
  "event_type": "role.change",
  "outcome": "COMMITTED",
  "actor_id": "admin-3",
  "subject_id": "user-17",
  "request_id": "req-0e19",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "attempted_at": "2026-11-10T09:00:01Z",
  "occurred_at": "2026-11-10T09:00:04Z",
  "recorded_at": "2026-11-10T09:00:06Z",
  "ingested_at": "2026-11-10T09:00:07Z",
  "previous_role": "viewer",
  "new_role": "editor",
  "aggregate_version": 12
}
```

This is an **illustrative JSON event**, not default Logback/Java output; the IDs and timestamps are for the lesson only. In a real system:

- `event_id` identifies a logical event stably across retries; it needs a uniqueness policy and deduplication support.
- `event_type`/`outcome` must be explicit; do not use a vague message string as the sole source of truth.
- `actor_id` and `subject_id` must comply with personal data/retention policies; do not automatically log full email addresses or secrets.
- `request_id`/`trace_id` help correlate logs, but do not necessarily uniquely identify **each audit event**.
- `aggregate_version` or sequence is an ordering signal per entity, not a replacement for timestamps; version generation must be race-safe in the data model.
- `previous_role` and `new_role` only illustrate before/after values; store only necessary, permitted values, avoiding full objects or secrets.
- `ingested_at` should be set by the collector/audit backend if accurate ingestion latency observation is needed; do not copy `recorded_at` if they are two different systems.

**Do not blindly treat HTTP client-supplied timestamps as authoritative** if the client can tamper with them. A client may submit an offline event that occurred in the past, but you must store both the client-claimed timestamp and the server-received timestamp, mark the source/trust level, and apply appropriate validation/reconciliation.

## 6. Standalone Java 17: Distinguishing occurredAt and recordedAt

This pure Java example uses `java.time.Instant` and `java.time.Clock` to produce **completely deterministic** output. It simulates two audit types:

1. A **DENIED** decision when a login attempt is rejected (no state change).
2. A **COMMITTED** role change after the simulated business state is updated.

The emitter sets `occurredAt` to **the time of the logical event**, while the audit recorder sets `recordedAt` when receiving the event. Both timestamps are injected in the example to demonstrate the difference consistently without relying on a real wall clock. The program uses **in-memory Map/List**, with no database transaction or durable storage. Therefore, it **only teaches timestamps and outcome classification**—it does not prove data-and-audit atomicity on process crash. See section 3 for real transactions.

Create **`AuditTimeDemo.java`**:

```java
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public class AuditTimeDemo {
    record AuditEvent(
            String eventId,
            String type,
            String outcome,
            String subjectId,
            Instant occurredAt,
            Instant recordedAt) {
    }

    static final class AuditRecorder {
        private final Clock clock;
        private final List<AuditEvent> events = new ArrayList<>();

        AuditRecorder(Clock clock) {
            this.clock = clock;
        }

        void record(String id, String type, String outcome,
                    String subject, Instant occurredAt) {
            events.add(new AuditEvent(id, type, outcome, subject,
                    occurredAt, Instant.now(clock)));
        }

        List<AuditEvent> snapshot() {
            return List.copyOf(events);
        }
    }

    public static void main(String[] args) {
        Instant auditReceivedAt =
                Instant.parse("2026-11-10T09:00:06Z");
        Clock auditClock = Clock.fixed(
                auditReceivedAt, ZoneOffset.UTC);
        AuditRecorder recorder = new AuditRecorder(auditClock);

        Map<String, String> roles = new LinkedHashMap<>();
        roles.put("user-17", "viewer");

        // Event 1: login attempt was denied.
        Instant denialDecisionAt =
                Instant.parse("2026-11-10T09:00:01Z");
        recorder.record("evt-1", "login", "DENIED",
                "user-17", denialDecisionAt);

        // Event 2: simulated state change succeeded.
        Instant simulatedCommitAt =
                Instant.parse("2026-11-10T09:00:04Z");
        roles.put("user-17", "editor");
        recorder.record("evt-2", "role.change", "COMMITTED",
                "user-17", simulatedCommitAt);

        List<AuditEvent> events = recorder.snapshot();
        if (events.size() != 2
                || !"editor".equals(roles.get("user-17"))
                || !events.get(0).occurredAt()
                        .isBefore(events.get(1).occurredAt())
                || !events.get(1).recordedAt()
                        .isAfter(events.get(1).occurredAt())) {
            throw new IllegalStateException("Audit timeline invalid");
        }

        for (AuditEvent event : events) {
            System.out.println("id=" + event.eventId()
                    + " type=" + event.type()
                    + " outcome=" + event.outcome()
                    + " occurred_at=" + event.occurredAt()
                    + " recorded_at=" + event.recordedAt());
        }
        System.out.println("effective_role=" + roles.get("user-17"));
        System.out.println("audit_count=" + events.size());
    }
}
```

Compile and run with **JDK 17+**:

```bash
javac AuditTimeDemo.java
java AuditTimeDemo
```

**Exact stdout:**

```text
id=evt-1 type=login outcome=DENIED occurred_at=2026-11-10T09:00:01Z recorded_at=2026-11-10T09:00:06Z
id=evt-2 type=role.change outcome=COMMITTED occurred_at=2026-11-10T09:00:04Z recorded_at=2026-11-10T09:00:06Z
effective_role=editor
audit_count=2
```

**Explanation:**

1. `Clock.fixed(...)` sets the recorder's receipt time to a known value, allowing tests to make exact comparisons. Production typically uses `Clock.systemUTC()` or managed clock infrastructure, while still allowing `Clock` injection into testable code.
2. `Instant` represents a point on the UTC timeline; when `toString()` is called in the example, it renders in ISO-8601 format ending in `Z`. It is independent of the machine's local timezone once the record holds an `Instant`.
3. `evt-1` is a DENIED decision, so its `occurred_at` is the decision time, even though no state change occurred.
4. `evt-2` marks a **simulated** successful change, so `occurred_at` is the simulated commit milestone, **not the request start time**.
5. `recorded_at` for both events is `09:00:06Z` because the recorder received them after the event times; a real collector may receive them even later.
6. `record(...)` appending to an `ArrayList` is neither a transaction nor a durable write. If an error occurs between `roles.put` and `recorder.record`, they can diverge. To avoid this risk for critical changes, use a unified transaction or outbox as shown in section 3.
7. The code above is single-threaded with hardcoded IDs, requiring no synchronization; multi-threaded systems need a store/queue with proper thread safety, ordering, and idempotency.

**Learning experiment:** Change `auditReceivedAt` to `2026-11-10T09:00:08Z`. Both `recorded_at` fields update accordingly, while `occurred_at` **stays the same**, proving that delayed delivery/recording should not alter the event's original timestamp. If you swap `simulatedCommitAt` to be earlier than `denialDecisionAt`, the assertion in the program will fail; that assertion is only for this demo scenario, not a rule that real audit events always arrive in chronological order.

## 7. Clock Rules: UTC, Clock, and Reliable Timestamps

### 7.1. Instant, ZoneId, and Offset Timestamps

In Java 17:

- `Instant` represents a point on the UTC timeline, suitable for event time and cross-service comparison when clocks are synchronized.
- `OffsetDateTime`/`ZonedDateTime` are useful when displaying local time or storing a business-meaningful offset/timezone.
- `LocalDateTime` **has no timezone/offset**, so it is insufficient to represent a global timestamp when multiple environments use different timezones.
- `Clock` allows injecting the time source; use `Clock.fixed(...)` in tests and `Clock.systemUTC()` where appropriate in production.

Java snippet (not a standalone program):

```java
Clock clock = Clock.systemUTC();
Instant observedAt = Instant.now(clock);
String iso8601 = observedAt.toString();
```

In databases, time types and timezone semantics depend on the DBMS: for example, PostgreSQL `TIMESTAMPTZ` stores an absolute instant and displays it in the session timezone; it **does not store the original timezone name**. Check driver/JDBC mapping and precision (milliseconds/microseconds/nanoseconds), and do not assume the DB always preserves nanoseconds.

**Do not store only local time strings** like `10/11/2026 09:00:00` without an offset, especially in multi-region systems or regions with daylight saving time. When displaying time to users, convert from the canonical timestamp to the desired timezone at the presentation layer.

### 7.2. Timestamps Are Limited Evidence

Node clocks can drift due to unstable NTP, VM pauses, manual clock adjustments, container host drift, or network issues. Wall clocks (`Instant.now`) can jump forward or backward; as a result, you may see `ingested_at < occurred_at` across two machines even when the actual order was the opposite.

**Do not use `System.nanoTime()` to record absolute event timestamps.** It measures **elapsed duration within a single JVM** and has no epoch that can be shared across servers. Use `System.nanoTime()` for durations such as time-to-append, handshake duration, or queue wait; never convert it into a UTC timestamp to correlate audits across machines.

When compliance requires high time accuracy, you must manage clock sources, maximum drift, NTP/chrony status, or dedicated time sources—not merely add more fractional digits to the timestamp.

### 7.3. Orders That Must Not Be Conflated

- **Event order:** which event happened first in the domain; may rely on transaction version, sequence number, source offset, or causality.
- **Record order:** which record reached the audit store first.
- **Ingest order:** which record the collector received first.
- **Search order:** how results are indexed and displayed by a given field.

Async queues, retries, batches, network partitions, and multiple consumers cause these orders to diverge. Two events with the same `occurred_at` down to storage precision can still have a distinct order; use a tie-breaker/sequence if ordering is critical.

Example of changes on the same account:

```text
event_id   occurred_at        aggregate_version   ingested_at
evt-101    09:00:01Z         41                  09:00:09Z
evt-102    09:00:02Z         42                  09:00:06Z
```

The collector received `evt-102` before `evt-101`; you cannot conclude that role version 42 occurred before version 41. Sorting by `aggregate_version` can restore order within the aggregate if versions are generated consistently; do not assume a per-aggregate version provides global ordering across the entire system.

## 8. Async Audit: When Is It Successful vs. Merely Enqueued?

A successful `auditLogger.info(...)` call may only mean **publishing to an in-memory queue**. If the worker has not processed it yet, returning from the call does not prove the event is in the audit store. Under high load:

```text
Business thread ---> enqueue audit ---> return
                        |
                        v
                worker / batch / retry
                        |
                        v
                  audit collector
                        |
                        v
                durable audit store
```

What you must define is the **acknowledgement boundary**:

| Milestone | What You Know | What Remains Uncertain |
| --- | --- | --- |
| Event object created | Audit data exists in JVM memory | Whether it will be saved/shipped |
| Enqueue succeeded | Queue accepted the event | Whether the worker processed it; process may crash |
| File appender write returned | Filesystem write API returned | Whether it is fsynced/durable or received by collector |
| Broker ACK | Broker confirmed per its ack config | Whether the consumer/audit store processed it |
| HTTP 2xx from collector | Endpoint returned success per contract | Whether data is indexed, persisted, or immutable across all hops |
| Audit store commit/ACK | Confirmed per the store's semantics | Whether downstream replicas are synced and searchable |

**You cannot infer exactly-once delivery or durability merely from using TLS, HTTP, or AsyncAppender.** Each sink has its own contract. For mandatory auditing, require durable storage, retries, idempotency, disaster recovery, and appropriate monitoring evidence.

### Common Timing Bugs in Async Pipelines

- Setting `occurred_at` in the worker after the event waited 30 seconds in a queue: the event appears to have occurred late.
- Retrying with a **new event ID and new occurred_at**: one action looks like two actions.
- Auditing success based on an async API's `202 Accepted` response: the actual work may fail later.
- Investigators querying only by `ingested_at` while interpreting it as business time.
- Emitting `COMMITTED` before transaction commit, or missing `COMMITTED` after commit due to a process crash.
- Syncing batch/offline data without recording original time and source trust.

**Solution:** Capture event time at the business boundary, keep a stable event ID, persist with an outbox/transaction when needed, ship asynchronously via an idempotent consumer, and attach receiver timestamps downstream. Measure queue lag and reconciliation rather than just counting log calls.

## 9. Idempotency, Retry, UNKNOWN Outcome, and Compensating Audits

### 9.1. A Retry Is Not Necessarily a New Transaction

Suppose a user submits a role change request with `operation_id=op-7`. The gateway times out, and the client retries three times. If the backend enforces idempotency, there may be **one logical role change** but **three request attempts**.

Depending on policy, the audit may record:

- Three `request.attempted` records with different `attempt_id` values, linked to the same `operation_id`.
- One `role.change.committed` record with a unique `event_id` for the business transition.
- Optional `request.retried` records or a `duplicate_request` status if needed for diagnostics.

Do not equate request count with data change count. If a consumer receives the same outbox event multiple times, use the same `event_id` and deduplicate at the audit store; do not blindly record another "SUCCESS" for the same transition.

### 9.2. When Commit Returns an Error and the Outcome Is Unknown

A network error right at COMMIT time can leave the client unsure whether the transaction committed. Recording `outcome=FAILED` immediately may be wrong; "no ACK received" does not mean rollback.

A safer approach is:

```text
transaction.commit.ack_unknown
  operation_id=op-7
  outcome=UNKNOWN
  reason=connection_lost

reconciliation completed later:
  operation_id=op-7
  observed_state=committed
  resolution=COMMITTED
```

This is an **illustrative event pattern**; reconciliation must be designed around transaction ID, idempotency key, data version, or actual authoritative state. If the final outcome still cannot be determined, do not change it to COMMITTED just to close a ticket. Keep both the original record and the resolution record to preserve investigation history.

### 9.3. Compensating Actions Do Not Erase Old Trails

In a saga/microservice architecture, a committed step can be reversed by a compensating action. If a role change occurred and was later revoked, keep both:

1. `role.change.committed` — the initial change.
2. `role.change.compensated` or `role.revoked` — the subsequent compensating action.

Do not delete or overwrite the old event to pretend it "never happened", because the audit must reflect the true sequence. The `compensated_at` timestamp does not replace the original event's `occurred_at`.

## 10. Auditing Across Services: One Event, Multiple Clocks

In distributed systems, the API gateway, service A, service B, database, broker, and collector may generate timestamps on different machines.

Example:

```text
Gateway: request_received_at = 09:00:01.010Z
Service A: authorization_decided_at = 09:00:01.028Z
Service B: business_effect_confirmed_at = 09:00:01.085Z
Audit store: recorded_at = 09:00:01.140Z
Indexer: ingested_at = 09:00:01.870Z
```

The numbers above assume synchronized clocks and are illustrative only. In real systems, **clock skew** can make Service B's timestamp appear earlier than the Gateway's even though actual causality is the reverse.

Therefore:

- Each service must clearly define its timestamps and time sources.
- Use `trace_id`/`span_id` to follow the request flow, but audit `event_id` must still distinguish individual events.
- Use transaction version, broker offset, causal links, or operation IDs when domain ordering must be reconstructed.
- Monitor time sync/offset; alert if ingest latency goes abnormally negative or clock drift exceeds policy.
- Do not correlate content across multiple events solely by nearby timestamps when concurrent requests exist.
- Record `source_system` and version/schema so events remain interpretable when logs are retained for years.

**Do not equate trace span status with audit outcome.** A trace may show HTTP 500 or an exception, but that does not prove the database state rolled back; the audit must take its outcome from the authoritative domain/transaction.

## 11. Designing an Investigable Audit Store

Audit logging differs from ordinary diagnostic logging in its requirements for **accuracy, history preservation, and access control**. Beyond timestamps, consider:

- **Append-only semantics:** restrict direct updates/deletes of records; corrections are expressed as linked supplemental/correction events.
- **Access control:** separate permissions for writers, readers, and retention managers; do not allow business applications to arbitrarily edit/delete history.
- **Integrity/tamper evidence:** use hash chaining, signed batches, or immutable/WORM storage when required; do not claim logs are immutable just because they are written to a file.
- **Retention and data minimization:** retain long enough for obligations; do not store beyond necessity or expose sensitive data.
- **Schema versioning:** events written today must remain readable in future investigations as the product evolves.
- **Recovery and reconciliation:** detect discrepancies between business transitions/outbox and the audit sink, with an accurate backfill process.
- **Monitoring:** queue lag, outbox age, failed publishes, duplicate counts, audit store write errors, clock drift, timestamp anomalies.

If backups and restores are required for audits, verify that restore does not **rewrite event timestamps**, lose event IDs, or introduce undetected duplicates.

### Logging Before and After Change Timestamps

For administrative actions, a record may include `before` and `after` values if policy permits. The `occurred_at` timestamp should correspond to the **transition** the record describes, while `effective_at` may differ if the change takes effect later.

Example of creating a policy effective tomorrow:

```text
policy.change.approved:
  decision_at = 2026-11-10T09:00:00Z
  effective_at = 2026-11-11T00:00:00Z
  outcome = APPROVED

policy.change.activated:
  occurred_at = 2026-11-11T00:00:00Z
  outcome = ACTIVATED
```

These are two **separate events** if the system actually has two state transitions. Do not emit `ACTIVATED` upon approval with a future `effective_at` without verifying that the scheduler actually applied the policy on time.

## 12. Testing Audit Timing

### 12.1. Critical Test Matrix

| ID | Scenario | Expected Audit | Must Not Happen |
| --- | --- | --- | --- |
| T1 | Login denied | `login / DENIED` with clear decision time | Recording `SUCCESS` or token/password |
| T2 | Authorization denied | Denial event independent of state-changing transaction | Dropping the trail just because no state changed |
| T3 | Role change committed | One `role.change/COMMITTED` event tied to the transition | Recording "committed" before commit proof |
| T4 | Role change rolled back | No `COMMITTED` in committed audit store; optional separate failed-attempt audit | Success audit record remaining after rollback |
| T5 | DB commit OK, process crashes before publish | Outbox/audit record still recoverable | Business change exists while mandatory audit is permanently lost |
| T6 | Publisher sends, ACK times out, retries | Same event ID, proper consumer deduplication | Two distinct logical success events for one transition |
| T7 | Certificate/collector down | Buffer/retry and alert per policy without creating a new original timestamp | Overwriting `occurred_at` with late receipt time |
| T8 | Client retries same operation ID | Attempt IDs and business event IDs distinguished | Counting retries as multiple business commits |
| T9 | Commit outcome UNKNOWN | Pending reconciliation; do not assume failed | Generating a false conclusive record |
| T10 | Clock skew between two services | Store source/event time and domain/sequence order | Inferring causality solely from timestamps |
| T11 | Future-effective change | Separate `decision_at` and `effective_at` | Recording activated before it is truly effective |
| T12 | Large outbox/event queue backlog | Event time preserved, ingest lag metrics increase | Altering timestamps or silently dropping events |

### 12.2. End-to-End Verification

An audit test should not merely assert that `logger.info(...)` was called. Verify across the entire chain:

1. **Business state:** before/after the operation, did the authoritative state change or not?
2. **Audit model:** do `event_type`, `outcome`, `actor`, `subject`, and timestamps accurately reflect the result?
3. **Transaction boundary:** does rollback remove both the business change and the corresponding success audit? Does the outbox row exist on commit?
4. **Publisher:** are event ID and `occurredAt` preserved across retries?
5. **Audit store:** is the event persisted per the store's durability semantics? Are there duplicates or missing rows?
6. **Search/backend:** is the event queryable within the SLA, in the right tenant/namespace, without leaking across boundaries?
7. **Security:** no credentials, tokens, policy-violating PII, or sensitive stack traces logged.
8. **Time quality:** are timezone, precision, clock source, and clock offset observed and documented?

To avoid mixing with real data, use a unique `test_run_id`/`event_id` in staging. For async flows, poll with a deadline rather than querying immediately and declaring failure. When testing failures, simulate crashes and network partitions in permitted environments, then reconcile **committed business transitions** against **logical audit events**.

### 12.3. Asserting Outcomes Accurately

A unit test modeling the branches:

```text
given: no current role change
when: authorization denied
then:
  business role unchanged
  audit event outcome = DENIED
  no audit event role.change COMMITTED

given: authorized role change, DB transaction rolled back
then:
  business role unchanged
  no committed role.change audit event
  independent failed-attempt audit may exist

given: authorized role change, DB transaction committed
then:
  new role visible in authoritative store
  committed audit row/outbox persisted in same transaction
  eventual downstream audit event uses same event_id + occurred_at
```

This is **test pseudocode**, not framework output. Pure unit tests can prove timing/field logic; atomicity and crash recovery require integration/failure-injection tests against real databases/brokers.

## 13. Common Mistakes When Choosing Audit Timing

| Symptom | Cause | Fix |
| --- | --- | --- |
| Audit says "SUCCESS" but DB did not change | Emitted before commit, or `UPDATE` row count not checked | Write success with commit/outbox or after guaranteed confirmation |
| DB changed but audit is missing | Emitted only after commit to an independent sink; crash or sink failure | Transactional audit row/outbox, retry/reconciliation |
| Denied request has no trail | Audited only after business transaction | Audit denied decisions in an independent flow |
| Event appears to happen minutes later | Replaced event time with ingest/publish time | Keep original `occurredAt`, store recorded/ingested separately |
| Audit succeeds twice after retry | New event ID per send or consumer lacks deduplication | Stable event ID, idempotent consumer |
| Audit order differs from change order | Parallel consumers, broker partitions, clock skew | Per-aggregate version/sequence/causal link |
| Log timestamp differs from dashboard hour | Timezone/offset misparsed, `LocalDateTime` lost zone | Use `Instant`/ISO-8601 offset, verify parser |
| "FAILED" yet data was committed | Network error after commit with unknown ACK | `UNKNOWN` outcome and reconciliation |
| `attempted` and `activated` not distinguished | One event for non-equivalent milestones | Separate event types/state transitions |
| Incident investigation missing principal | Authn failed before identity known, or filtered/masked out | Store policy-compliant identifier/source and clear outcome |
| High ingest lag while app is fast | Queue/collector backlog | Monitor outbox age, queue lag, and searchable latency |
| Source timestamp is in the future | Clock skew or client-supplied timestamp | Check time sync, source trust, validity bounds |
| Process crash loses final logs | Non-durable in-memory queue | Durable audit store/outbox, graceful shutdown and recovery |
| Audit lands in DEBUG app logs | Normal logger filter/level/sampling applied to audit | Separate audit policy/route, test bypass |
| Timestamp changes during backfill | Used `now()` as `occurred_at` for past events | Preserve original event time, attach separate replay/import time |

## 14. Design and Operations Checklist

Before considering an audit mechanism ready, verify:

- [ ] Is it clearly defined whether the **event** describes an attempt, decision, committed effect, or processing state?
- [ ] Is `occurred_at` captured at the right **domain boundary** and kept immutable across publish/retries?
- [ ] Do `recorded_at` and `ingested_at` have distinct meanings instead of replacing event time?
- [ ] Is auditable success persisted atomically with business state or via an outbox when required?
- [ ] Do denied/rolled-back attempts have an audit path managed independently of transaction rollback?
- [ ] Are unknown COMMIT ACK errors represented as `UNKNOWN` with reconciliation instead of guessing?
- [ ] Is the event ID stable, the consumer idempotent, and are duplicates/retries distinguished from new operations?
- [ ] Are clock sync, timezone, precision, and timestamp sources documented, with clock drift monitored?
- [ ] Do future-effective changes, saga compensations, and approvals have separate milestone events?
- [ ] Is mandatory auditing isolated from DEBUG filters and sampling?
- [ ] Are crashes, rollbacks, retries, collector outages, async lag, and duplicates tested?
- [ ] Does the audit store have appropriate access control, retention, tamper evidence, and recovery mechanisms?
- [ ] Is there periodic reconciliation between business commits/outbox and the audit sink, with discrepancy alerts?
- [ ] Are secrets, raw tokens, passwords, and unauthorized personal data excluded from the audit payload?

**Completion criteria:** You can distinguish action, decision, commit, recording, and ingest timestamps; never emit a success audit before an authoritative outcome; use transactions/outboxes to prevent missing trails; preserve original timestamps across async/retries; and prove via tests that both denied attempts and committed state changes are recorded accurately.

## 15. Self-Check Questions

1. A `role.changed` event is successfully written to the log sink and then the transaction rolls back: is the problem in the timestamp or in the consistency/outcome model?
2. Why can writing an audit outside the transaction **after** commit still lose records?
3. If a login is denied and there is no DB transaction, which timestamp should be audited?
4. Why must a publisher retry never replace `occurred_at` with the current time?
5. What does `Clock.fixed(...)` help verify in a unit test, and what can it not prove?
6. Is `HTTP 202 Accepted` in an asynchronous workflow sufficient to record `COMMITTED`?
7. When connection is lost right at COMMIT, why should `UNKNOWN` and reconciliation be used?
8. If two services have clock skew, can event time be used as a strict global order across all events?
9. A user's role changes and is rolled back by a compensating action minutes later: should the initial event be deleted?
10. How do you distinguish "at-least-once" audit delivery from a business operation executing twice?
11. Why is `System.nanoTime()` not used to record absolute audit timestamps across services?
12. Which counters or reconciliations detect a lingering outbox backlog after a collector outage?

## References

- [Java SE 17 — Instant](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Instant.html) — UTC instants and ISO-8601 representation.
- [Java SE 17 — Clock](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Clock.html) — replaceable time source in unit tests.
- [Java SE 17 — OffsetDateTime](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/OffsetDateTime.html) — instants with a UTC offset for representation/display.
- [Java SE 17 — System.nanoTime](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html#nanoTime()) — measuring duration rather than global event timestamps.
- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html) — events to log, timing, synchronization, and log protection.
- [OpenTelemetry — Semantic Conventions for Logs](https://opentelemetry.io/docs/specs/semconv/general/logs/) — attributes and relationship of log events to telemetry.
- [OpenTelemetry — Logs Data Model](https://opentelemetry.io/docs/specs/otel/logs/data-model/) — `Timestamp` and `ObservedTimestamp` and their semantics.
