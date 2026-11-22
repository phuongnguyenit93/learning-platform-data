# Supporting Auditing with Logging in Java

## 1. How Does Logging Support Auditing?

**Auditing** requires evidence-backed answers to who or which system performed what operation, on which target, when, with what outcome, and whether the related transaction can be traced. **Audit logging** is the proactive creation of event records to support traceability, reconciliation, incident investigation, and proof that control procedures were enforced.

In Java, audit logging is a **logging objective**, typically designed at the business and security layers. It complements application technical logs and is not synonymous with printing every statement or every variable change to the console.

For example, when an administrator changes access permissions, the system needs to know:

- **Who** performed it: the authenticated principal identifier, or the service account identifier.
- **What was done, and to whom/what**: `ROLE_UPDATE` on account `user-81`.
- **When**: a timestamp with an explicit time zone, preferably UTC.
- **Outcome**: succeeded, denied, or failed; the reason at the business-code level.
- **Which request it relates to**: a correlation ID to link processing steps together.
- **Evidence**: records are stored, access-controlled, retained, and integrity-checked according to policy.

Practical benefits include retrieving change history, detecting anomalous behavior, establishing accountability, reconciling approval workflows, and supporting internal or external audits. **Having an audit log does not automatically mean compliance with a regulatory standard**: specific requirements still depend on the domain, data, and audit policy.

## 2. Distinguishing Audit Logs from Technical Logs

| Log Type | Primary Question | Example | Characteristics to Prioritize |
| --- | --- | --- | --- |
| Application/diagnostic log | How is the program running, and where are errors occurring? | `Connection timeout while calling service` | Supports debugging and operational observability; can be very verbose and sampled. |
| Access/request log | What requests are entering the system? | `POST /users/81/roles → 403` | HTTP path, status code, latency; does not by itself clarify business decisions. |
| **Audit log** | Who requested/performed a meaningful action, what was affected, and what was the outcome? | `ROLE_UPDATE / user-81 / DENIED / NO_PERMISSION` | Structured events, bound to a trusted identity, retained and protected according to audit requirements. |

An HTTP 200 does not necessarily prove that data was committed; likewise, an HTTP 500 is not sufficient to determine whether a durable change occurred. An audit event must reflect **the business truth at a defined point in time**, not be inferred solely from HTTP status codes or debug lines.

**Events that should be recorded:** logins and failed logins; role grants/revocations; security configuration changes; approvals/rejections; creation, modification, or deletion of critical data; sensitive data exports; administrative privilege usage; log retention policy changes; and access to data subject to auditing. There is no need to turn every read or every loop into an audit event: choose based on risk and business requirements.

## 3. Designing an Auditable Record

A sample event in JSON Lines format (one standalone JSON object per line):

```json
{
  "schemaVersion": 1,
  "eventId": "evt-001",
  "occurredAt": "2026-11-09T08:00:00Z",
  "actorId": "user-42",
  "action": "ROLE_UPDATE",
  "targetType": "USER",
  "targetId": "user-81",
  "outcome": "SUCCESS",
  "reasonCode": "APPROVED",
  "correlationId": "req-100"
}
```

| Field | Meaning and Notes |
| --- | --- |
| `schemaVersion` | Schema version so older data remains readable when the schema evolves. |
| `eventId` | Unique identifier of the event; used to detect duplicate records during redelivery. |
| `occurredAt` | Event timestamp in ISO 8601/UTC; when needed, `recordedAt` (when the system recorded it) can be added. |
| `actorId` | The genuinely authenticated principal (user, service, scheduled job). |
| `action` | A stable, consistently named action such as `ROLE_UPDATE`, `DATA_EXPORT`. |
| `targetType`, `targetId` | Type and identifier of the affected object. |
| `outcome` | `SUCCESS`, `DENIED`, or `FAILURE` with clearly defined semantics. |
| `reasonCode` | Standardized reason code; avoid logging raw exceptions or sensitive information verbatim. |
| `correlationId` | Links the request with traces/business logs across multiple layers and services. |

In real systems, you can add `tenantId`, `sourceService`, policy/permission codes, or a **selectively chosen** set of changed fields. If before/after values are needed, record only auditable attributes (for example, role codes before/after) and avoid copying the entire entity.

**Data sources must be trustworthy:** obtain `actorId` from the server-established authentication context, not directly from a client-supplied `userId` that could impersonate someone else. Similarly, `outcome` must be derived from the actual processing result. Use `eventId` for deduplication and `correlationId` to find related events. The two fields serve different purposes.

## 4. Standalone Java 17+ Example Without External Libraries

The following example writes two sample events to the file `audit-demo.jsonl` in UTF-8. All sample data is hardcoded for readability and easy verification. The program **only simulates business outcomes**: it does not actually update permissions or authenticate users.

Create the file `AuditLoggingDemo.java`:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.time.Instant;
import java.util.Objects;

public class AuditLoggingDemo {

    record AuditEvent(
            String eventId,
            Instant occurredAt,
            String actorId,
            String action,
            String targetType,
            String targetId,
            String outcome,
            String reasonCode,
            String correlationId) {
    }

    public static void main(String[] args) throws IOException {
        Path file = Path.of("audit-demo.jsonl");

        AuditEvent success = new AuditEvent(
                "evt-001",
                Instant.parse("2026-11-09T08:00:00Z"),
                "user-42",
                "ROLE_UPDATE",
                "USER",
                "user-81",
                "SUCCESS",
                "APPROVED",
                "req-100");

        AuditEvent denied = new AuditEvent(
                "evt-002",
                Instant.parse("2026-11-09T08:01:00Z"),
                "user-99",
                "ROLE_UPDATE",
                "USER",
                "user-81",
                "DENIED",
                "NO_PERMISSION",
                "req-101");

        appendEvent(file, success);
        appendEvent(file, denied);
        System.out.println("Đã ghi 2 sự kiện audit vào " + file);
    }

    private static void appendEvent(Path file, AuditEvent event)
            throws IOException {
        Objects.requireNonNull(event);
        Files.writeString(
                file,
                toJson(event) + "\n",
                StandardCharsets.UTF_8,
                StandardOpenOption.CREATE,
                StandardOpenOption.WRITE,
                StandardOpenOption.APPEND);
    }

    private static String toJson(AuditEvent event) {
        return "{"
                + "\"eventId\":" + quote(event.eventId()) + ","
                + "\"occurredAt\":" + quote(event.occurredAt().toString()) + ","
                + "\"actorId\":" + quote(event.actorId()) + ","
                + "\"action\":" + quote(event.action()) + ","
                + "\"targetType\":" + quote(event.targetType()) + ","
                + "\"targetId\":" + quote(event.targetId()) + ","
                + "\"outcome\":" + quote(event.outcome()) + ","
                + "\"reasonCode\":" + quote(event.reasonCode()) + ","
                + "\"correlationId\":" + quote(event.correlationId())
                + "}";
    }

    private static String quote(String value) {
        Objects.requireNonNull(value);
        StringBuilder result = new StringBuilder();
        result.append('"');

        for (int i = 0; i < value.length(); i++) {
            char c = value.charAt(i);
            switch (c) {
                case '"' -> result.append("\\\"");
                case '\\' -> result.append("\\\\");
                case '\n' -> result.append("\\n");
                case '\r' -> result.append("\\r");
                case '\t' -> result.append("\\t");
                default -> {
                    if (c < 0x20) {
                        result.append('\\').append('u')
                                .append(String.format("%04x", (int) c));
                    } else {
                        result.append(c);
                    }
                }
            }
        }
        return result.append('"').toString();
    }
}
```

Compile and run with JDK 17 or later in the directory containing the source file:

```bash
javac -encoding UTF-8 AuditLoggingDemo.java
java AuditLoggingDemo
```

**Exact** stdout output for each successful run:

```text
Đã ghi 2 sự kiện audit vào audit-demo.jsonl
```

After the first run, `audit-demo.jsonl` contains the following exact two lines (shown as single lines with no added indentation):

```jsonl
{"eventId":"evt-001","occurredAt":"2026-11-09T08:00:00Z","actorId":"user-42","action":"ROLE_UPDATE","targetType":"USER","targetId":"user-81","outcome":"SUCCESS","reasonCode":"APPROVED","correlationId":"req-100"}
{"eventId":"evt-002","occurredAt":"2026-11-09T08:01:00Z","actorId":"user-99","action":"ROLE_UPDATE","targetType":"USER","targetId":"user-81","outcome":"DENIED","reasonCode":"NO_PERMISSION","correlationId":"req-101"}
```

Explanation:

1. `AuditEvent` groups the identifier, operation, outcome, and request-linking fields, helping callers construct a consistent format.
2. `toJson` builds a structured event; `quote` escapes double quotes, backslashes, and control characters so unexpected values cannot break the format or inject forged records via newlines.
3. `appendEvent` uses `CREATE` and `APPEND` to add events to the file without erasing existing content. It lets I/O errors surface via `IOException`, because the application needs to know when writing fails.
4. The timestamps, identifiers, and outcomes here are **illustrative data**, not obtained from real users or a real clock. In an application, generate a distinct `eventId` per event and obtain timestamps from `Instant.now()` or an injected `Clock` for testability.
5. **Running it again will append two more lines with the same IDs**, because the demo hardcodes IDs. A real system must have mechanisms to guarantee unique IDs and deduplicate at the storage layer.

**Important limitation:** `Files.writeString(..., APPEND)` is a learning example, **not a production-grade audit store**. It does not guarantee atomicity across concurrent writer processes, does not guarantee fsync/durability on power loss, does not protect against file modification/deletion, and lacks access control, retention, or integrity verification. Java SE also does not include a general-purpose JSON encoder here; the `quote` method only handles the demo's string fields. In a real deployment, use the project's standard serializer together with a dedicated audit sink.

## 5. Recording at the Right Time So Audit Results Are Accurate

A `SUCCESS` event should mean **the business operation has completed within the defined boundary** (for example, the database transaction has committed). If success is recorded before commit and the transaction rolls back, the log will falsely claim that the change occurred. Conversely, if the process crashes after commit but before sending the audit event, the change may leave no trace.

An appropriate flow for a critical update operation:

```text
Request -> Authentication -> Authorization
                              |-- Denied -> Record DENIED audit
                              |
                              +-- Allowed -> Transaction:
                                               +-- Update data
                                               +-- Write audit_outbox in same transaction
                                              Commit
                                                |
                                       Worker/dispatcher sends event
                                                |
                                       Audit store confirms persistence
```

- **Transactional outbox:** write the business data and the outbox record **in the same transaction on the same database**, then forward the event to the audit store. This reduces the gap between commit and event emission; monitor unsent outbox rows, retries, and recovery capability.
- **At-least-once delivery:** when the dispatcher retries due to a lost ACK, the receiving store must deduplicate by `eventId`. Never assume a single send guarantees exactly one stored record.
- **DENIED/FAILURE:** actions that are denied or fail before commit may not have a successful transaction. If these attempts must be audited, record them through an appropriate audit path independent of the rolled-back business transaction.
- **Mandatory auditing:** decide the policy when an audit record cannot be written. For operations requiring mandatory evidence, you may need to reject the operation or hold it in a recoverable pending state; never silently report success when a critical audit record has been lost. Design consistent behavior for timeouts, network drops, restarts, and duplicate writes.
- **Multiple services:** propagate `correlationId` across steps, synchronize clocks, and distinguish `occurredAt` from `receivedAt`; do not infer absolute ordering solely from timestamps across different machines.

Do not place the only audit message in a `catch` block or a debug log at the end of a controller: this easily misses successful, denied, or rolled-back paths. Identify event emission points according to the business action and test every outcome branch thoroughly.

## 6. Keeping Evidence Trustworthy and Secure

**Integrity:** the audit store needs mechanisms to detect modification, deletion, insertion, or missing records; options include append-only/WORM storage, independent access controls, digital signatures, or key-protected hash chains. Simply adding a checksum field or encrypting the file **is not sufficient proof of tamper-resistance** if someone with edit access can also recompute the checksum or swap the key. Establish periodic verification procedures and record verification results.

**Availability:** centralized storage, backups/replication, monitoring of queue lag and fullness, and alerts for lost events or delivery failures; design so data survives when an application instance fails. Recovery procedures must be rehearsed.

**Access control:** separate writers, readers, and retention policy administrators; audited users should not have permission to modify or delete their own trails. Audit queries or exports of sensitive logs as well when required by policy.

**Security and privacy:** prefer stable IDs over raw identifying data; limit IP/device/location data when not genuinely needed. Do not log passwords, OTPs, access tokens, refresh tokens, private keys, session secrets, full request/response bodies containing sensitive data, or stack traces containing secrets. Apply redaction/allowlisting before emitting events, encrypt data in transit and at rest, and define who is authorized to read.

**Retention and deletion:** define purpose, retention period, legal hold requirements where applicable, timely disposal mechanisms, traceability, and chain-of-custody capability. Do not default to an arbitrary number of days for every product or regulation.

**Querying for audits:** support filtering by `actorId`, `action`, `targetId`, `eventId`, UTC time range, and `correlationId`; preserve schemas/versions to decode historical records; record who exported a result set and the export scope. A record with many fields that cannot be searched or interpreted still fails to serve auditing needs.

## 7. Scenario and How to Reconcile

**Scenario: administrative role change**

1. An auditor searches for `action=ROLE_UPDATE` and `targetId=user-81` within the investigation time window.
2. The system returns `evt-001`: `actorId=user-42`, `SUCCESS`, `08:00:00Z`, `correlationId=req-100`, along with related approval events if the workflow includes approvals.
3. Query `req-100` in operational logs to understand the technical flow. Technical logs serve as supporting documentation; the actual state change must be verified against business/transaction state.
4. There is a record `evt-002`: `DENIED / NO_PERMISSION` at `08:01:00Z`; it proves a denied attempt occurred, **not** that the role was changed by that attempt.
5. Reconcile identifiers, the permission policy in effect at the time, allowed before/after records, and integrity checks to form an evidence-backed conclusion.

This is why simply logging `"update role completed"` or `"403 Forbidden"` is insufficient for audit requirements: it lacks the actor, target, standardized timestamp, business outcome, and links to other evidence.

## 8. Testing and Common Pitfalls

| Test Case | What to Verify |
| --- | --- |
| Valid change commits successfully | Exact `SUCCESS` event bound to the right actor, target, timestamp, and transaction. |
| Permission denied | `DENIED` event recorded (if in audit scope); **no** unauthorized data change occurred. |
| Transaction rollback | No record claiming a successful commit is emitted; failed attempt is recorded per policy. |
| Lost connection to audit store | Retries/recovers or blocks the business operation per contract; alerts are raised and no event is silently dropped. |
| Duplicate event delivery | Only one logical event per `eventId` in the receiving store; retries remain traceable. |
| Input containing newlines, quotes | JSON remains valid; no forged audit lines appear due to control-character injection. |
| Schema and time changes | Older records remain readable; UTC and timestamp semantics remain consistent. |
| Unauthorized access or log tampering | Denied, leaves an appropriate trail, or is detected during integrity verification. |

Common design mistakes:

- Writing free-form log strings without a schema; changing the wording breaks historical queries.
- Trusting `actorId` from the request instead of the authenticated principal.
- Recording `SUCCESS` before commit or forgetting to audit `DENIED` attempts.
- Using `System.out.println`, local files, or debug logs as the sole source of evidence.
- Logging sensitive data to get "enough detail," leading to data exposure and expanded risk.
- Failing to handle duplicates, lost events, clock skew, read permissions, or retention policies.
- Equating "encrypted" with "tamper-proof" and equating "having logs" with "being compliant."

## 9. Checklist for Java Projects

1. **List actions requiring auditing:** identify which events provide evidentiary value, including administrative operations, critical changes, and denied attempts.
2. **Define schema/version:** action name, actor/target, outcome, reason, event ID, request correlation, UTC timestamp, and allowed attributes.
3. **Bind to business boundaries:** use server-side authentication results, clearly decide emission timing and post-commit state; use an outbox if durable event emission with the transaction is needed.
4. **Choose an appropriate sink:** centralized storage, access control over write/read/delete, policy-based retention, failure monitoring, and integrity verification.
5. **Test provability:** from an object ID or a `correlationId`, you can reconstruct the decision chain and distinguish successful changes from failed attempts without leaking secrets.

**Core takeaway:** logging supports auditing when records accurately reflect business behavior, are structured, searchable, linked to other evidence, and protected against loss or unauthorized modification.