# Audit Events and Retention in Spring Framework Application Events

In business systems, an **audit event** (an event for auditing/traceability) records *who or which system performed what action, on which object, at what time, and with what outcome*. **Retention** is the policy defining how long audit records must be kept, for what purpose, who can access them, and whether they must be deleted, anonymized, cold-archived, or placed on hold upon expiration.

For example: an administrator changes an account's permissions, a staff member approves an order, an automated job exports data, or a user fails to log in. Such actions may require a trustworthy audit trail for investigation, reconciliation, and accountability.

For **Spring Framework Application Events**, a crucial point is:

> `ApplicationEventPublisher.publishEvent(...)` only publishes an event in-process. It **does not persist audit records, guarantee commits, provide an immutable audit store, or implement retention**.

Designers must decide **which events require auditing**, **where audit records are stored**, **which transaction they bind to**, and **how retention jobs execute**. A system that audits exhaustively without time limits, or recklessly records sensitive data wholesale, still creates security risks and data-governance violations.

Goals of this lesson:

- Distinguish **domain events**, **audit events**, **application logs**, and **Spring Data auditing metadata**.
- Design an **audit envelope** sufficient for reconciliation while minimizing sensitive data.
- Understand `@EventListener`, `@TransactionalEventListener`, rollbacks, and event-loss risks.
- Choose between writing audits in the same transaction or via a **Transactional Outbox** when durability is required.
- Design a **retention schedule** with clear purpose, duration, legal holds, deletion/anonymization, backup handling, and verifiability.
- Apply these concepts in a Java 17+ program with Spring Framework 6.2, Spring JDBC, and H2, observing commit/rollback behavior and cleanup.

## 1. How Does an Audit Event Differ from a Domain Event or Log Line?

A domain event like `OrderApproved` describes **a business fact that occurred**. It may trigger read-model updates, notifications, or coordination across bounded contexts.

An audit record is optimized to answer **investigative questions**. For example:

```text
actor=staff-17
action=ORDER_APPROVE
resourceType=ORDER
resourceId=order-42
decision=ALLOWED
outcome=SUCCESS
occurredAt=2026-01-10T00:00:00Z
correlationId=req-12
```

These values are **synthetic data**. A business event `OrderApproved(orderId)` does not necessarily carry the actor or authorization decision; the audit record can enrich those details from the **authenticated context established at the application boundary**.

| Data Type | Purpose | Limitations |
| --- | --- | --- |
| **Domain event** | Describes business facts, triggers other logic | Does not inherently carry full audit metadata or retention |
| **Audit event/record** | Tracks who did what, when, on which target, and the result | Must be protected, access-controlled, and lifecycle-managed |
| **Application log** | Diagnoses errors and runtime behavior | Subject to rotation, sampling, dropped lines; not automatically durable evidence |
| **Spring Data auditing** | Stores `createdBy/createdDate/lastModifiedBy/lastModifiedDate` on entities | Typically describes **current metadata state**, not full change history |
| **Outbox event** | Persists message delivery intent alongside data transactions | Has a send/retry lifecycle distinct from audit-trail retention |

**Spring Data JPA** supports `@CreatedBy`, `@CreatedDate`, `@LastModifiedBy`, `@LastModifiedDate`, and `AuditorAware`. It is useful for knowing who last created/modified an entity, yet **does not replace a multi-version audit history table**. A record might change ten times while `lastModifiedBy` holds only the final editor.

Do not "audit" merely by writing `log.info("User changed role")`, since logs generally lack transactional guarantees, integrity policies, access controls, or retention matching audit requirements.

## 2. Classifying Audit Events by Purpose

Before designing a schema, define **which actions must be recorded** and their protection requirements:

| Category | Examples | Question to Answer |
| --- | --- | --- |
| **Security audit** | Failed login, permission changes, account lockouts | Who attempted access, what happened, and which control made the decision? |
| **Business audit** | Order approval, refunds, contract state transitions | Which business decision completed? |
| **Administrative audit** | Config changes, API key creation, data exports | Who altered the system and which resources were affected? |
| **Data access audit** | Reading/viewing/exporting sensitive data | Who accessed which data, under what purpose or permission? |
| **Operational audit** | System job modifying a batch of records | Which automated task mutated the data? |

Not every event in a Spring context should be persisted. Spring also emits **framework/lifecycle events** like `ContextRefreshedEvent`; persisting all of them into an audit table creates noise, inflates storage, and stores data of no audit value.

Define an **allowlist of auditable event types**, specifying actions and outcomes explicitly. A catch-all listener accepting `Object` and serializing every payload is a high-risk design.

### Success and Failure Events Have Different Semantics

For example, `ORDER_APPROVED` should be recorded as **success** only once the change commits under business rules. Meanwhile, a **denied login** is also a critical security event, even though no business transaction commits.

Therefore, do not force a single mechanism ("audit inside the order transaction") for both successful and failed audits. Denied actions or rolled-back transactions may need an **independent audit store/transaction**, while still avoiding falsely recording that a business change succeeded.

## 3. Designing the Audit Event Envelope Structure

A practical audit envelope should be stable and semantically clear:

```json
{
  "auditId": "aud-4d7e",
  "eventType": "ORDER_APPROVAL",
  "schemaVersion": 1,
  "eventId": "evt-65b2",
  "aggregateType": "ORDER",
  "aggregateId": "order-42",
  "actorRef": "staff-17",
  "action": "APPROVE",
  "decision": "ALLOWED",
  "outcome": "SUCCESS",
  "occurredAt": "2026-01-10T00:00:00Z",
  "recordedAt": "2026-01-10T00:00:01Z",
  "correlationId": "req-12",
  "retentionClass": "BUSINESS_AUDIT_V1"
}
```

This is **illustrative JSON**, not a standard auto-generated by Spring Framework. Which fields are required depends on audit goals and organizational policy.

**Field roles:**

- `auditId`: unique key of the **audit record**, aiding queries and reconciliation.
- `eventId`: ID of the **logical source event** for correlation/deduplication when needed; not required to be identical to `auditId`.
- `eventType` and `schemaVersion`: contract identifiers enabling future consumers to interpret historical records.
- `aggregateType`/`aggregateId`: target object type and key; avoid stuffing entire JPA graphs into records.
- `actorRef`: authenticated actor identifier or service/batch job identity; never blindly trust client-submitted actor strings.
- `action`: business verb from a normalized set, such as `APPROVE` or `REVOKE`.
- `decision`: policy/permission evaluation result, such as `ALLOWED`/`DENIED` when applicable.
- `outcome`: `SUCCESS`/`FAILURE`/`REJECTED`; clearly define when the outcome can be confirmed.
- `occurredAt`: time the event was observed at the source, not when it was written to the audit store.
- `recordedAt`: time the audit store accepted the record, helping measure ingestion delay.
- `correlationId`: links to requests/traces or workflows without causing unbounded metric label cardinality.
- `retentionClass`: references a **versioned policy**, rather than forcing every record onto the same duration.

### Separate Event Time from Record Time

With an outbox or message broker, an audit record might be processed **minutes after the event occurred**. Never stamp every timestamp with `Instant.now()` inside the listener and pretend it represents the business action time.

Example:

```text
occurredAt = 10:00:00Z  (when the action was created)
committedAt = 10:00:01Z (transaction commit, if determinable)
recordedAt = 10:03:30Z (written by audit sink after retry)
```

Not every system can obtain an exact `committedAt`; if there is no reliable way to capture commit time, **do not fabricate that field**. Use timestamps with clear provenance, standardize on UTC/`Instant` for storage, and format timezones in the UI.

### Versioning Audit Payloads

Audit records are often retained long-term and read back across many software deployments. Therefore:

1. Never change the meaning of an existing field while keeping its name (e.g., dollars to cents).
2. Add optional fields with **clear business defaults**.
3. For breaking changes, use `schemaVersion`, adapters/upcasters, or new event types.
4. Store minimal data needed to interpret history without depending on Java class/package names.
5. Test replay fixtures for every historical version ever written.

**Successful JSON parsing does not prove accurate audit interpretation.** Audits require semantics that remain defensible across code changes.

## 4. Data Minimization: Do Not Store Whole Events in Audits

An audit trail is valuable because it is **fit for purpose**, not because it hoards as much data as possible. A bad example:

```java
log.info("audit {}", objectMapper.writeValueAsString(request));
```

If `request` contains passwords, access tokens, card numbers, addresses, health records, or arbitrary payloads, this can write secrets into logs and secondary stores. Adding `@EventListener` does not sanitize the data.

**Do:**

- Use an **allowlist of fields** per audit type: object ID, action, outcome, trusted `actorRef`, timestamps, correlation ID.
- Exclude raw passwords, session cookies, access tokens, API keys, JWTs, connection secrets, sensitive payment-card data, or full HTTP headers/bodies unless justified with special controls.
- Pseudonymize actors/subjects when clear identity is unnecessary, while **never assuming pseudonymized data is anonymous**. A stable ID can still link back to an individual.
- Sanitize untrusted inputs to prevent **log injection** via CR/LF or control characters; for SQL, use parameterized statements.
- Never serialize live managed JPA entities, lazy associations, or relationships holding PII.
- Bound the length and domain of `eventType`, `action`, `outcome`, and any caller-supplied strings.
- For actors, take identity from the Spring Security context/server-side principal or a verified boundary source; never accept an arbitrary `actorId` from a request as audit "proof."

**Classification example:**

| Data | Default Stance |
| --- | --- |
| Event type, action enum, policy version | Usually safe to store |
| Order/resource ID, `actorRef` | Store if needed with access controls; may be indirect personal data |
| Trace ID, request ID | May store for correlation; evaluate retention and identifiability |
| Email/phone/address | Restrict or omit if reference IDs suffice |
| Passwords, tokens, session secrets, keys | Never store raw values |
| Full request/response bodies | Avoid by default; usually holds data beyond audit needs |
| Failure reason | Use error codes or secret-scrubbed messages, not arbitrary full stack traces |

The OWASP Logging Cheat Sheet recommends limiting sensitive data, protecting access rights, detecting tampering, and disposing of logs at expiry. That applies to audit trails just as much as traditional log files.

## 5. Transactions: Audits Must Accurately Reflect Outcomes

This is what determines whether an audit trail can be trusted.

### 5.1. Synchronous @EventListener: Can Share the Source Transaction

By default, `SimpleApplicationEventMulticaster` calls `@EventListener` synchronously on the **publisher's thread**. If a service publishes an event **inside a transaction** and the listener uses the same Spring transaction manager/`DataSource`, SQL operations in the listener can join **that exact transaction**:

```text
BEGIN T1
  INSERT orders(id, status)
  publishEvent(OrderApproved)
      -> @EventListener
           INSERT audit_events(...)
COMMIT T1
```

**Benefit:** if both inserts succeed and the transaction commits, an audit record exists alongside the business change. If the transaction rolls back, both the order and the audit record roll back together. This fits **auditing a truly committed change**, yet **does not preserve a separate trail of denied attempts** if you also want to capture failures.

Notes:

- Returning from `publishEvent(...)` **does not prove the transaction has committed**.
- A synchronous listener throwing an unchecked exception can fail the service and roll back the transaction per policy.
- If a listener catches and swallows an audit write error when auditing is mandatory, the transaction may commit **without an audit**, breaking contract.
- If auditing writes to a separate resource outside the same transaction, do not assume atomicity across two databases.
- Never perform slow network I/O inside the same transaction solely for auditing; it holds locks/connections longer and hurts p95/p99 request latency.

### 5.2. @TransactionalEventListener(AFTER_COMMIT): Right Phase, Not Atomic Auditing

```java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void onOrderApproved(OrderApproved event) {
    auditWriter.write(event);
}
```

This is an **illustrative integration snippet**, requiring `OrderApproved`, `auditWriter`, an active transaction, and imports.

The callback runs only after the source transaction **commits successfully**; by default `fallbackExecution = false`, so publishing outside a matching transaction may skip execution.

However:

1. Order data has **already committed** before the listener runs.
2. If writing the audit fails, you **cannot roll back the source transaction** that already committed.
3. If the process crashes between commit and callback, the in-JVM audit event can be **lost**.
4. If an after-commit listener needs to **perform new database writes**, it typically must open an **explicit new transaction**, such as a service method with `@Transactional(propagation = Propagation.REQUIRES_NEW)` invoked via a Spring proxy. In imperative transactions, transaction resources may still be bound to the thread during the callback without triggering a new commit for writes unless a new transaction is started.
5. `AFTER_COMMIT` callbacks are **not async by default**; slow I/O inside the callback still delays the request.

Hence, `@TransactionalEventListener(AFTER_COMMIT)` does not guarantee "every audit record exists exactly once." It controls **reaction timing**, not durable storage, retries, or deduplication.

### 5.3. Failed/Denied Audits Must Be Separated at the Right Boundary

A denied login attempt still needs auditing even when no business transaction exists or it rolls back. You cannot put `INSERT audit` inside **the same transaction that rolls back** and expect the record to survive.

Choose an explicit approach:

- **Independent security logging pipeline** decoupled from business transactions, with governed retention and integrity.
- **Dedicated audit transaction** by design, such as `REQUIRES_NEW` via a Spring proxy for imperative flows, when writing to the same DB and semantics permit it.
- **Durable event ingestion** with write/queue acknowledgments, dead-letter queues, and overload policies if audits must not be dropped on process failures.

Define **fail-open vs fail-closed** per audit category. Best-effort metric recording should not block critical business flows, whereas an operation with mandatory auditing may need to reject requests if the audit store is unavailable. This decision belongs to contracts/risk policy, not Spring's defaults.

## 6. Complete Java 17+ Example: Audit Records in the Same Transaction and Retention Cleanup

This example uses Spring Framework **6.2.9**, Spring JDBC, and H2. No Spring Boot or web server is needed.

We create:

- A `purchase_orders` table storing orders.
- An `audit_events` table storing minimal audit events.
- `AuditRequested` as an immutable event; `AuditListener` handles it via synchronous `@EventListener` and writes `audit_events` using `JdbcTemplate`.
- `TransactionTemplate` wrapping `INSERT purchase_orders` and `publishEvent(...)` so order and audit share **the same transaction**.
- A second execution that intentionally rolls back. After rollback, neither the new order nor its audit exists in the DB.
- Cleanup using `expires_epoch_ms` computed as event time + 30 days **purely for illustration**; it deletes expired audits while **leaving business orders untouched**.

This is a **mechanics exercise**, not a production audit system. Do not treat the 30-day window as a real legal policy; there are no legal holds, auth, partitioning, archiving, backup purges, or integrity signatures in this demo.

### 6.1. Directory Structure

```text
audit-event-retention-demo/
├── pom.xml
└── src/main/java/example/AuditEventRetentionDemo.java
```

### 6.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>example</groupId>
    <artifactId>audit-event-retention-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.9</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>6.2.9</version>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <version>2.3.232</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
                <configuration>
                    <mainClass>example.AuditEventRetentionDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

### 6.3. src/main/java/example/AuditEventRetentionDemo.java

```java
package example;

import java.time.Duration;
import java.time.Instant;

import org.h2.jdbcx.JdbcDataSource;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.event.EventListener;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

public class AuditEventRetentionDemo {

    // Payload contains only fields needed for the example.
    public record AuditRequested(
            String eventId,
            String orderId,
            String actorRef,
            String action,
            Instant occurredAt) {
    }

    public static class AuditListener {
        private final JdbcTemplate jdbc;
        private static final Duration DEMO_RETENTION =
                Duration.ofDays(30);

        public AuditListener(JdbcTemplate jdbc) {
            this.jdbc = jdbc;
        }

        @EventListener
        public void onAuditRequested(AuditRequested event) {
            long occurred = event.occurredAt().toEpochMilli();
            long expires = event.occurredAt()
                    .plus(DEMO_RETENTION).toEpochMilli();

            jdbc.update(
                "INSERT INTO audit_events " +
                "(event_id, order_id, actor_ref, action, " +
                "occurred_epoch_ms, expires_epoch_ms) " +
                "VALUES (?, ?, ?, ?, ?, ?)",
                event.eventId(),
                event.orderId(),
                event.actorRef(),
                event.action(),
                occurred,
                expires
            );

            // "Staged" does not mean the transaction has committed.
            System.out.println("audit: staged " + event.eventId());
        }
    }

    private static long countOrders(JdbcTemplate jdbc) {
        Long value = jdbc.queryForObject(
                "SELECT COUNT(*) FROM purchase_orders", Long.class);
        return value == null ? 0 : value;
    }

    private static long countAudit(JdbcTemplate jdbc) {
        Long value = jdbc.queryForObject(
                "SELECT COUNT(*) FROM audit_events", Long.class);
        return value == null ? 0 : value;
    }

    public static void main(String[] args) {
        JdbcDataSource dataSource = new JdbcDataSource();
        dataSource.setURL(
                "jdbc:h2:mem:audit_retention_demo;DB_CLOSE_DELAY=-1");
        dataSource.setUser("sa");

        JdbcTemplate jdbc = new JdbcTemplate(dataSource);
        jdbc.execute(
                "CREATE TABLE purchase_orders (" +
                "id VARCHAR(40) PRIMARY KEY, status VARCHAR(30) NOT NULL)");
        jdbc.execute(
                "CREATE TABLE audit_events (" +
                "event_id VARCHAR(80) PRIMARY KEY, " +
                "order_id VARCHAR(40) NOT NULL, " +
                "actor_ref VARCHAR(80) NOT NULL, " +
                "action VARCHAR(80) NOT NULL, " +
                "occurred_epoch_ms BIGINT NOT NULL, " +
                "expires_epoch_ms BIGINT NOT NULL)");

        TransactionTemplate tx = new TransactionTemplate(
                new DataSourceTransactionManager(dataSource));

        Instant referenceTime =
                Instant.parse("2026-01-10T00:00:00Z");

        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext()) {

            context.registerBean(
                    AuditListener.class, () -> new AuditListener(jdbc));
            context.refresh();

            // Scenario 1: both business state and audit commit.
            tx.executeWithoutResult(status -> {
                jdbc.update(
                    "INSERT INTO purchase_orders (id, status) " +
                    "VALUES (?, ?)", "order-1", "APPROVED");
                context.publishEvent(
                        new AuditRequested(
                                "evt-ok", "order-1",
                                "staff-ref-7", "ORDER_APPROVE",
                                referenceTime));
            });
            System.out.println("business: committed order-1");

            // Scenario 2: the entire transaction rolls back.
            try {
                tx.executeWithoutResult(status -> {
                    jdbc.update(
                        "INSERT INTO purchase_orders (id, status) " +
                        "VALUES (?, ?)", "order-2", "APPROVED");
                    context.publishEvent(
                            new AuditRequested(
                                    "evt-reverted", "order-2",
                                    "staff-ref-7", "ORDER_APPROVE",
                                    referenceTime));
                    throw new IllegalStateException("rollback demo");
                });
            } catch (IllegalStateException expected) {
                System.out.println("business: rolled back");
            }

            System.out.println(
                "before cleanup: orders=" + countOrders(jdbc) +
                " audits=" + countAudit(jdbc));

            // Simulate retention worker running 31 days later.
            Instant cleanupAt = referenceTime.plus(
                    Duration.ofDays(31));
            int removed = jdbc.update(
                "DELETE FROM audit_events " +
                "WHERE expires_epoch_ms <= ?",
                cleanupAt.toEpochMilli());

            System.out.println("retention: removed=" + removed);
            System.out.println(
                "after cleanup: orders=" + countOrders(jdbc) +
                " audits=" + countAudit(jdbc));
        }
    }
}
```

Run from the directory containing `pom.xml`, requiring **JDK 17+**, Maven, and initial dependency download access:

```bash
mvn -q compile exec:java
```

Lines printed by **the program itself** in order (excluding Maven and Spring logs):

```text
audit: staged evt-ok
business: committed order-1
audit: staged evt-reverted
business: rolled back
before cleanup: orders=1 audits=1
retention: removed=1
after cleanup: orders=1 audits=0
```

### 6.4. Why Does This Output Occur?

1. `AnnotationConfigApplicationContext` is refreshed after registering `AuditListener` as a Spring bean. Spring detects the `@EventListener` method.
2. Event `AuditRequested` is a Java record; Spring handles plain-object payloads via `PayloadApplicationEvent` when needed, and the listener receives the record type directly.
3. `JdbcTemplate` and `DataSourceTransactionManager` share the **same `DataSource`**, so both `INSERT` statements inside the `TransactionTemplate` callback join one database transaction. The listener runs synchronously under the default multicaster.
4. `evt-ok` is published and the listener prints `audit: staged evt-ok`. Then the transaction actually commits and the program prints `business: committed order-1`.
5. `evt-reverted` is also published and the listener prints `staged`; however, the code then throws `IllegalStateException`, rolling back the transaction. Neither `order-2` nor `evt-reverted` remains in the database. A log line from a listener before rollback is not proof the audit persisted durably.
6. Before cleanup, there is only **one order** and **one committed audit record**.
7. The demo sets expiration to `referenceTime + 30 days`. Cleanup after `31 days` removes the expired record without touching the orders table. `removed=1` and `audits=0` show retention cleanup took effect.

**Limitations:** The demo uses a single-database H2 transaction without real security principals. Production must generate `actorRef` server-side, validate actions, classify retention policies, apply legal holds, restrict write/delete permissions, and manage backups/archives. The 30-day period here is a **synthetic learning value**, not a default legal requirement.

## 7. Transactional Outbox: Auditing After Commit While Keeping a Recovery Path

If the goal is to send audits to a **separate audit service** or secure repository without blocking the request with network calls, use a **Transactional Outbox**:

```text
Transaction T1:
    UPDATE order status = APPROVED
    INSERT outbox_events(
        event_id, type, payload_minimized,
        status = PENDING, created_at, ...)
    COMMIT T1
          |
          v
Background dispatcher
    claim PENDING message
    -> send to audit sink
    -> ACK / retry with backoff
    -> mark SENT
          |
          v
Audit sink
    deduplicate by event_id / audit_id
    append audit record under retention policy
```

This design enables recovery if the process dies **after commit but before delivery**. Still:

- The outbox record and business change must be written **atomically** in the same transaction. Calling `publishEvent` and writing to an outbox after commit lacks the same guarantee.
- A worker might send successfully and crash before marking `SENT`, causing **duplicate delivery**. The audit sink needs idempotency/unique keys.
- **Outbox retention** (how long sent messages remain) **differs** from **audit retention** (how long audit evidence is kept). Never delete audits when cleaning up the outbox.
- **Bounded retries** require an exception taxonomy, backoff, jitter, and dead-letter/failure states. Never swallow errors and treat them as success.
- The audit sink may process events asynchronously; its outcome and recording timestamp differ from the source transaction's commit time.
- If zero gap between business commit and audit is required, same-transaction auditing or a stricter transactional/evidence infrastructure may be needed. Outboxes provide recoverability, not a cross-network ACID transaction between two services.

For **denied events** (e.g., insufficient permissions), provide a separate audit path since no successful business transaction exists to write an outbox record the same way. Design security audit pipelines and error paths explicitly.

## 8. Retention Policy: Do Not Pick Durations by Gut Feeling

**Retention** must be grounded in **purpose, data classification, risk, and applicable legal/contractual obligations**. There is no single default duration suitable for all Spring applications.

A policy record should include:

| Attribute | Meaning |
| --- | --- |
| `retentionClass` | Audit group, e.g., `SECURITY_AUDIT` / `BUSINESS_AUDIT` |
| `purpose` | Why retention is needed: investigation, reconciliation, obligation compliance |
| `legalBasisOrPolicyRef` | Reference to a valid basis/approval, not an arbitrary string |
| `startsAt` / retention trigger | Compute duration from event time, commit time, account closure, or another milestone |
| `durationOrEndRule` | Number of days/months/years or rule tied to a business milestone |
| `actionAtExpiry` | Delete, anonymize, archive, or route to a pre-deletion review workflow |
| `legalHoldPolicy` | When approved holds apply and who may release a hold |
| `accessPolicy` | Which roles can view, search, export, delete, or alter policies |
| `policyVersion` | Retention contracts can evolve over time |
| `backupHandling` | How expiry propagates to backups, replicas, cold archives, and search indexes |
| `verification` | How to prove jobs ran and did not delete ineligible data |

**Illustrative classification example, with no legal force:**

```text
SECURITY_AUDIT_V1:
  purpose: investigate access and privilege changes
  duration: determined by approved security/legal schedule
  at_expiry: delete or anonymize unless valid hold

BUSINESS_APPROVAL_V1:
  purpose: reconstruct approval decisions
  duration: determined by applicable recordkeeping obligations
  at_expiry: archive or dispose according to approved policy

DEBUG_TELEMETRY_V1:
  purpose: short-term troubleshooting
  duration: shorter operational window
  at_expiry: rotate/delete with backup propagation
```

Specific year counts are omitted here because **mandatory retention periods depend on industry, jurisdiction, and record type**. An organization subject to GDPR follows the **storage limitation** principle and must keep personal data **no longer than necessary for the purposes** or lawful retention obligations. Regulations applicable in Vietnam or other jurisdictions must be reviewed separately by legal/data-protection teams, never inferred from a technical lesson.

### When Does Retention Start Counting?

- If policy states "delete 90 days after event creation," the trigger may be `occurredAt`.
- If policy states "retain N years after contract termination," expiration **cannot be computed once from `occurredAt`** while the contract remains open.
- If a record arrives late due to retries, computing expiration from `recordedAt` may retain it longer than policy permits if the true trigger is `occurredAt`.
- If policy changes, existing records may need re-evaluation; never silently rewrite expirations without approval.

In production SQL schemas, separate **policy version**, **retention trigger**, and `expires_at` so decisions remain explainable later. For calendar-month or year durations in a timezone, use proper calendar types (`ZonedDateTime`/`LocalDate` + zone/rules) rather than assuming "one month = 30 days." The Java demo uses `Duration.ofDays(30)` solely for a fixed 30×24-hour rule.

## 9. Retention Lifecycle: Capture, Access Control, Expiry, and Disposition

A controlled lifecycle:

```text
AUDIT CAPTURED
       |
       +-- validated + classified
       |
       v
ACTIVE (searchable by authorized roles)
       |
       +-- retention clock / policy version
       |
       +-- legal hold? ---- YES ---> HELD (restricted, reviewable)
       |                          |
       |                          +-- hold released --> evaluate expiry
       |
       +-- NO and expired
       |
       v
DISPOSITION QUEUE
       |
       +-- delete / anonymize / policy-approved archive
       |
       v
VERIFIED DISPOSITION
       |
       +-- record minimal non-sensitive proof:
           batch id, count, timestamp, policy version, outcome
```

**Append-only during the retention window** does not mean "never delete." Audit records may need protection against unauthorized tampering while active, yet the retention scheduler still needs a controlled, approved, authenticated, and verifiable **disposition** path.

### Step 1 — Identify Eligible Records

The worker reads **expired** records, filtering by active policy and legal holds. Never blindly delete every record with an old timestamp without verifying trigger and hold status.

Illustrative **production schema SQL**, not runnable verbatim in section 6's demo:

```sql
SELECT audit_id
FROM audit_events
WHERE expires_at <= :cutoff
  AND legal_hold = FALSE
ORDER BY expires_at
FETCH FIRST 1000 ROWS ONLY;
```

`:cutoff` is an **application-layer named parameter**; pagination/locking syntax depends on the database. Production queries need tenant/policy partitioning and claiming mechanisms so two workers do not accidentally delete the same rows concurrently.

### Step 2 — Delete in Small Batches, Avoiding Long Locks

Never run a single giant `DELETE` across millions of rows when indexed batching or partitioning/pruning is available:

- Create suitable indexes on `expires_at`, `retentionClass`, and hold status per workload.
- Process bounded batches, committing between batches.
- With daily/monthly partitions where the entire partition is eligible, consider dropping/rotating partitions **only after confirming all records are eligible and none are on legal hold**.
- Persist progress checkpoints so jobs restart safely with idempotent cleanup.
- Throttle throughput so audit queries and business transactions keep their SLAs.
- Apply bounded retries for DB errors, raising dead-letter/alerts when completion fails.

### Step 3 — Check All Copies

A record may exist in:

```text
primary audit DB
    +-- read replicas
    +-- full-text search index
    +-- monitoring / logs
    +-- cached exports
    +-- object storage
    +-- cold archive
    +-- backup snapshots
```

Deleting from the primary table **does not mean** every copy is gone. Retention policies should explicitly distinguish **live active data** from backup snapshots that expire on a designed rotation schedule. Establish backup-restore procedures so expired records do not silently reappear, and keep backup access controls at least as strict as the primary system.

When fulfilling personal-data erasure requests, evaluate scope across all copies, search indexes, exports, and lawful exceptions. A hashed ID is not automatically anonymous if it can still be linked back to an individual.

### Step 4 — Record Proof of Retention Actions

A retention job is itself a privileged operation, so **minimal proof** may be needed:

```json
{
  "jobId": "retention-job-88",
  "policyVersion": "SECURITY_AUDIT_V1",
  "startedAt": "2026-02-10T00:00:00Z",
  "completedAt": "2026-02-10T00:01:00Z",
  "selected": 300,
  "deleted": 300,
  "failed": 0,
  "operator": "system-retention-worker"
}
```

This is **illustrative metadata**; do not retain a full list of the deleted audit records. If "proof of deletion" copies the deleted contents, the retention goal is defeated.

Some architectures require **tombstones** to propagate deletions downstream. Tombstones must also obey their own policies and carry only minimal necessary fields.

## 10. Legal Holds and Personal Data Erasure Requests

Two principles are often mistaken as contradictory:

- **Integrity:** records must not be arbitrarily modified or deleted by users or admins to cover tracks while retention is required.
- **Storage limitation/erasure:** data must not be kept indefinitely without a valid purpose/basis; under certain conditions, individuals may request deletion or restricted processing.

Thus, a trustworthy audit store is typically **append-only during normal operations**, paired with a **controlled disposition path** to expire/delete/anonymize or retain under an approved legal hold.

A **legal hold** is not a flag any operator flips arbitrarily to keep data forever. It requires:

1. Valid basis/rationale and scope of covered records.
2. Authorized approver, start time, and review/termination conditions.
3. Restricted access during the hold.
4. Protected audit logs of hold enable/disable events.
5. Automatic re-evaluation of retention once the hold is released.

No universal minimum retention period or erasure exception fits all industries and jurisdictions. Consult your organization's record-retention schedule, applicable legal obligations, and legal/data-protection teams in real deployments.

## 11. Protecting Integrity: Preventing Tampering and Unauthorized Access

Audit data can be targeted by someone trying to **erase their tracks**. Hence, a regular table with broad `UPDATE`/`DELETE` privileges is insufficient for sensitive requirements.

### 11.1. Least Privilege and Separation of Duties

- The application's audit-writing account should have **INSERT and minimal required permissions only**, never broad update/delete rights over all records.
- The retention worker uses a separate role permitted only to delete/anonymize eligible records with policy-governed logging/approval.
- Audit reader roles are separated from writer/deleter roles, enforcing RBAC/ABAC by tenant and purpose.
- Sensitive queries, exports, policy updates, and legal-hold toggles should be governed and audited appropriately.
- Encrypt at rest and in transit; govern key rotation, backups, and access to encryption keys.
- Rate-limit lookups/exports and prevent unauthorized key-based queries, since audit stores can hold highly sensitive events.

### 11.2. Tamper-Evident vs Tamper-Proof

You can add a hash/HMAC chain or signatures across records/batches:

```text
digest_n = HMAC(key, canonical(record_n) || digest_(n-1))
```

This is a **conceptual formula**, not a full standard protocol. With an HMAC or signature whose key is kept outside the reach of anyone modifying the database, altering history becomes hard to hide.

Additional design needs:

- Stable canonical serialization and versioned schemas.
- Protecting keys inside KMS/HSM or an independent boundary.
- Record ordering and concurrency (partitioned/hash chains per stream or batch).
- Anchoring digests to an independent/WORM store when required.
- A way to **prove valid retention deletions** once a link is removed—for example, signing batches/certificates and retaining minimal metadata, or using integrity structures compatible with governed deletion.

**Never call a plain hash "absolute security."** If an attacker has database write access and can rewrite the entire chain/checkpoint, an unanchored hash chain without an independently protected key can be recomputed.

### 11.3. Preventing Log Injection and Forged Inputs

A user-submitted string like `"OK\nadmin=trusted"` can corrupt text logs unless encoded/sanitized. Use structured logging and control CR/LF and delimiters. When writing SQL, use prepared statements/`JdbcTemplate` parameters rather than concatenating user-controlled strings.

Actors and outcomes must come from **server-side** authentication/authorization logic, never from client-supplied event payloads. When auditing denied requests, record the `DENIED` event right at the security boundary.

## 12. Performance, Capacity, and Cost of Keeping Audits

Audits can grow into a massive data stream:

```text
events_per_day × average_record_size × retention_days
```

**Hypothetical** example: 100,000 audit events/day, averaging 800 bytes each, retained for 90 days:

```text
100,000 × 800 × 90 = 7,200,000,000 bytes
≈ 7.2 GB raw payload (decimal)
```

This excludes indexes, metadata, replication, backups, encryption overhead, log shipping, and search copies. Never use it for production sizing without measuring real payloads, indexes, and queries.

Principles:

- Favor **audit-worthy events** instead of broadcasting and storing every Spring event.
- Keep records small with explicit schemas and minimal fields; omit full JPA entities/HTTP bodies.
- Partition by time/tenant if supported by workload and DB; drop/clean partitions safely when eligible.
- Index according to real queries (actor, aggregate, time, type) while balancing write amplification.
- Separate hot storage for recent queries and cold storage if policy allows, managing total retention across both.
- Monitor ingest rate, backlog, write errors, p95 query latency, disk/IO/backup growth, and expired-but-undisposed record counts.
- For **mandatory** audits, define behavior when audit storage is full or down. Never silently drop events just to shave latency.

**Some security event categories may require fail-closed behavior**, while telemetry/debug may be best-effort. Do not apply one failure policy across all categories when risks and obligations differ.

## 13. Dangerous Anti-Patterns

**1. Persisting every Spring event via `@EventListener(Object)` to JSON.**  
May accidentally store bean lifecycle events, tokens, internal data, or huge object graphs. Audit only allowlisted event types.

**2. Using `@TransactionalEventListener(AFTER_COMMIT)` and treating it as same-transaction auditing.**  
The callback runs after commit; a write failure or process crash can leave the business committed without an audit.

**3. Writing audits inside a transaction that rolls back when failed attempts must be recorded.**  
The audit rolls back too. Use an independent pipeline or separate transaction per policy for security failures/denied actions.

**4. Taking `actorId` from a user-supplied field and treating it as verified identity.**  
Can be forged. Derive it from an authenticated principal/server context, including service accounts.

**5. Keeping only `@LastModifiedBy` and claiming an immutable audit history.**  
Last-modifier metadata is not a complete change history; an audit trail is a complementary model.

**6. Logging full request/response bodies or stack traces containing tokens and PII.**  
Can leak secrets via SIEM/backups. Use allowlists, sanitization, and data classification controls.

**7. Setting "retention = forever" to avoid deleting too early.**  
Can violate data minimization/storage limitation while increasing breach exposure and costs. Use approved policies with formal holds when longer retention is needed.

**8. Running `DELETE` by record age without checking legal holds.**  
Can violate preservation duties. Retention must check hold states and disposition eligibility.

**9. Deleting from the DB and claiming all data is gone.**  
Search indexes, exports, backups, replicas, and cold archives may still hold copies. Enforce disposal lifecycles per sink.

**10. Omitting stable `schemaVersion`/`eventType`.**  
Years later, old records may become unreadable due to class renames or format shifts. Use versioned audit schemas/upcasters.

**11. Relying on an "audit staged" log line to conclude a transaction succeeded.**  
A synchronous listener may run before rollback. Verify actual committed state.

**12. Assuming a digest prevents all tampering.**  
A hash chain lacking independent keys/anchors can be rewritten wholesale; retention deletions also need valid proof mechanisms.

**13. Assuming an outbox guarantees exactly-once delivery.**  
Dispatchers can redeliver after crashes; audit consumers must deduplicate using stable IDs.

**14. Running retention jobs with no monitoring or self-auditing.**  
Jobs can stall or delete wrongly unnoticed. Add metrics, alerts, sampling checks, and non-sensitive disposition proofs.

## 14. Audit and Retention Test Plan

Include **business tests, transaction tests, permission tests, and lifecycle tests**.

### 14.1. Transaction Integration Tests

| Scenario | Expected Outcome |
| --- | --- |
| Business change commits | Order and audit row coexist |
| Audit listener fails when audit is mandatory | Source transaction must not commit if designed as synchronous atomic |
| Business transaction rolls back after publish | Audit in the same transaction also rolls back |
| Security action is denied | Denied record exists via the designed independent audit path |
| `@TransactionalEventListener(AFTER_COMMIT)` writes audit | Does not run on rollback; test crash durability separately |
| Outbox dispatcher sends duplicate | Audit sink does not create two logical records |

Never use `@RecordApplicationEvents` alone to conclude an audit persisted. `spring-test`'s recorder confirms **the event was published**, not that it committed, satisfied retention, or reached the audit sink.

### 14.2. Testing Retention with a Fixed Clock

Do not make tests sleep 30 days or depend on the machine clock:

1. Inject a `Clock` or supply a reference timestamp to the retention service.
2. Seed records before, at, and after the expiration threshold.
3. Place a subset on legal hold and verify they are **not disposed**.
4. Verify eligible records are deleted/anonymized while order/business data remains intact.
5. Run cleanup a second time and confirm idempotency (no unexpected extra deletions).
6. Simulate DB failure mid-batch; restarted job resumes cleanly from checkpoints/claim states.
7. Verify backup/index/archive propagation per policy, not just primary row counts.

The section 6 demo uses a fixed `Instant` and an illustrative duration to verify the same principle without sleeping or altering the system clock.

### 14.3. Security/Privacy Tests

- Users lacking audit-reader roles cannot query/export audit records.
- One tenant cannot view or delete another tenant's records.
- App writers cannot update/delete audit history beyond permitted scope.
- Retention workers cannot delete records under legal hold.
- Payloads with synthetic tokens/passwords/PII do not leak into audit serialization/logs.
- CR/LF/delimiters in inputs do not cause log injection.
- IDs are never accepted from unauthenticated clients to impersonate privileged actors.
- Audit store accesses, exports, and policy changes are tracked per policy.
- Backup restores do not improperly resurrect expired records without handling procedures.

### 14.4. Reliability and Operations

- Downstream audit temporarily down: outbox retains events, retries are bounded, backlog alerts fire.
- Process dies after commit before send: worker recovers.
- Send succeeds then crash before ACK: consumer dedup handles safely.
- Schema changes: historical records remain readable by version.
- Disk/storage nearing full: alerts fire before mandatory audits are lost; fail-open/fail-closed behaves as defined.
- Retention worker stalled: oldest-expired-record age and backlog grow, triggering alerts.

## 15. Production Deployment Checklist

Before accepting a Spring-events-based audit workflow, answer:

1. **Audit scope:** which actions/events need auditing, and what is the purpose and basis for recording them?
2. **Trust boundary:** are actor/decision/outcome generated server-side, or could clients spoof them?
3. **Schema:** are event ID, type, version, aggregate ID, timestamps, and correlation stable?
4. **Sensitive data:** are allowlists, masking/redaction, and sensitive-data classification enforced?
5. **Atomicity:** must the audit commit with the business change or can it be eventually consistent?
6. **Rollback/denied events:** is there a separate recording path when transactions fail?
7. **Durability:** does a crash after commit lose audits; are outboxes/retries/dedup in place if required?
8. **Access:** are reader/writer/retention-operator/hold-approver permissions separated?
9. **Integrity:** are tamper resistance and independent verification aligned with risk policy?
10. **Retention:** who approved durations, policy versions, triggers, and disposition actions?
11. **Hold/erasure:** are legal holds and valid deletion/anonymization requests supported?
12. **Copies:** do replicas, search, caches, exports, backups, and archives have matching disposal schedules?
13. **Operations:** are batch jobs, checkpoints, monitoring, alerts, and recovery runbooks in place?
14. **Tests:** have commit/rollback, duplicate events, data leaks, holds, expiration, and restores been tested?

The best design is rarely "one listener does everything," but rather a **clear audit contract** with separate, verified responsibilities across capture, protection, querying, and retention pipelines.

## 16. Self-Assessment Questions

**1. An `@EventListener` printed "audit recorded." Is the audit guaranteed to be durably persisted?**  
No. If the listener joined an uncommitted transaction that later rolls back, the audit row can vanish. Verify the commit/database.

**2. Does `@TransactionalEventListener(AFTER_COMMIT)` guarantee auditing in the same business transaction?**  
No. The callback runs after commit; errors or process crashes can leave the audit missing. Consider same-transaction writes or an outbox as required.

**3. Why not store the entire Java event payload in the audit?**  
It may contain PII/secrets, large object graphs, and unstable schemas. Use an envelope with an allowlist of audit-purpose fields.

**4. Do `@CreatedBy` and `@LastModifiedDate` replace an audit history?**  
No. They provide entity creation/last-modification metadata, not a full log of every action that occurred.

**5. Why can't all audit records simply be deleted on the same 30-day schedule?**  
Different audit types have different purposes, bases, and obligations. The 30-day window in the demo is purely synthetic.

**6. When a transaction rolls back, how can a denied access attempt still be recorded?**  
Use an audit mechanism independent of the business transaction, approved with matching error and retention policies.

**7. Does append-only contradict retention deletion?**  
No. Append-only protects records from arbitrary edits/deletions while retention applies; lawful disposition requires a controlled delete/anonymize path with minimal proof.

**8. Is hashing audit rows enough to prevent all tampering or deletions?**  
No. Keys/anchors must be protected, alongside handling chains/batches, concurrency, and justified retention; hashes can be recomputed if an attacker controls all data.

**9. If an outbox sends the same event twice due to retries, what should the audit sink do?**  
Use stable event IDs and unique keys/idempotency to avoid creating two logical audit records.

**10. Once a retention job deletes from the primary DB, what else must be checked?**  
Backups, replicas, archives, search indexes, cached exports, and personal-data handling requests per policy.

## 17. Official and Security References

- [Spring Framework 6.2 — Application Events and Annotation-Based Listeners](https://docs.spring.io/spring-framework/reference/6.2/core/beans/context-introduction.html)
- [Spring Framework 6.2 — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html)
- [Spring Framework 6.2.9 Javadoc — SimpleApplicationEventMulticaster](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html)
- [Spring Data JPA — Auditing](https://docs.spring.io/spring-data/jpa/reference/data-commons/auditing.html)
- [OWASP Cheat Sheet — Logging](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html)
- [European Commission — Principles of the GDPR, Data Minimisation & Storage Limitation](https://commission.europa.eu/law/law-topic/data-protection/information-business-and-organisations/principles-gdpr_en)
- [European Commission — Dealing with Requests from Individuals](https://commission.europa.eu/law/law-topic/data-protection/information-business-and-organisations/dealing-requests-individuals_en)
- [Java SE 17 — java.time.Instant](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Instant.html)

