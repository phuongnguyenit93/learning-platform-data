# Audit Logging After Business Operations in Spring Application Events

An audit trail is evidence of **who performed what action, on which target, when, and with what outcome**. In a Spring application, a business operation typically runs inside a transaction; the service can publish an event so an audit listener records the action. However, the moment an event is published **is not the same as the moment the transaction commits**. Recording the audit too early may persist an entry for an operation that ultimately rolls back; recording it only after commit via an in-memory callback can lose the audit if the process crashes before the callback finishes running.

This guide covers two different strategies: **mandatory audit written in the same business transaction** and **post-commit audit** using `@TransactionalEventListener(phase = AFTER_COMMIT)`. For the latter, you must understand when to open a new transaction, how to test commit/rollback/audit-write failure, and when to use a transactional outbox or the Spring Modulith Event Publication Registry for retry/recovery capability.

## 1. Define Requirements Before Choosing a Listener

There are at least three audit levels (plus operational logging):

| Type | Example | Guarantee Level |
| --- | --- | --- |
| **Mandatory/compliance audit** | Who approved a transaction, who changed access roles | Business operation must not commit if the corresponding audit is not committed |
| **Post-commit audit** | Supporting history for a completed change | Recorded only if the business TX commits; if callback fails, the possibility of data loss must be clearly understood |
| **Audit sent to another system** | Forwarding change history to a compliance or analytics store | Requires durable send intent, retries, and idempotency |
| **Operational log** | `INFO event received` or stack trace | Not durable audit evidence |

Key design question: **If the audit sink is currently failing, is the main business operation allowed to complete?**

If the answer is **no**, write the audit and the business change in the **same transaction** on the same transactional resource, or at least persist a durable *audit intent* alongside the business change and deliver safely to the sink afterward. If the answer is **yes**, `AFTER_COMMIT` may fit secondary tasks, provided you accept or separately mitigate the event-loss window.

You also need to define `outcome`: recording "user requested approval" differs from "order committed in `APPROVED` state." An after-commit audit normally represents a **committed operation**, not a catch-all log for every attempt or rejected action.

## 2. Why a Plain @EventListener Is Often Insufficient for Post-Commit Audits

A simple event:

~~~java
public record OrderApproved(
    String eventId,
    String orderId,
    String actorId,
    java.time.Instant occurredAt
) { }
~~~

Inside a transactional service:

~~~java
@Transactional
public void approve(String orderId) {
    orderRepository.setApproved(orderId);
    publisher.publishEvent(new OrderApproved(
        newEventId(), orderId, verifiedActorId(), Instant.now()
    ));
}
~~~

The two snippets above are **excerpts**: they require the appropriate repositories/helpers, `@Transactional`, and `ApplicationEventPublisher`.

By default, `ApplicationEventPublisher` dispatches synchronously through `SimpleApplicationEventMulticaster`. If a listener annotated with a plain `@EventListener` writes an audit record to an external system immediately upon receiving the event, it can be invoked **before the business transaction commits**:

~~~text
BEGIN business TX
  UPDATE order -> APPROVED
  publishEvent(OrderApproved)
        |
        +-- @EventListener sends audit to external service
        |      -> "order approved" already saved externally
  a subsequent business step throws an exception
ROLLBACK business TX

Result: external audit says success,
but the order state was never committed.
~~~

If a synchronous listener writes the audit **within the same database transaction** (without starting a separate transaction), both changes can roll back together. That is a valid design for mandatory audits; the risk in the example above is an independent side effect or writing to a resource **outside** the source transaction.

Do not rely on `@Order` to solve this. That annotation only affects listener invocation order, **not transaction boundaries**.

## 3. AFTER_COMMIT: Reacting Only to Successful Business Transactions

Use `@TransactionalEventListener` with an explicit phase:

~~~java
@Component
class AuditEventListener {

    private final AuditWriter auditWriter;

    AuditEventListener(AuditWriter auditWriter) {
        this.auditWriter = auditWriter;
    }

    @TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMMIT
    )
    public void onOrderApproved(OrderApproved event) {
        auditWriter.record(event);
    }
}
~~~

This is an **excerpt** in a Spring application. The annotation requires importing `org.springframework.transaction.event.TransactionalEventListener` and `TransactionPhase`; `AuditWriter` and `OrderApproved` are application-defined.

Timeline:

~~~text
Service thread
    |
    +-- BEGIN TX
    |     UPDATE orders
    |     publish OrderApproved
    |         +-- listener registers AFTER_COMMIT callback
    |
    +-- COMMIT succeeds
    |      |
    |      +-- invoke audit callback
    |             +-- INSERT audit in a SEPARATE transaction
    |
    +-- service finishes

If ROLLBACK: AFTER_COMMIT callback does not handle the event.
~~~

`TransactionPhase` has `BEFORE_COMMIT`, `AFTER_COMMIT` (default), `AFTER_ROLLBACK`, and `AFTER_COMPLETION`. Explicitly specifying `AFTER_COMMIT` makes the code's intent clearer.

**No active transaction:** `@TransactionalEventListener` by default **does not run** because no commit phase can be determined. If `fallbackExecution=true` is configured, it can run without a transaction, but that is a semantic change that must be designed and tested; do not enable it just to make a test pass.

**Cannot undo commit:** an error inside a post-commit callback **cannot roll back** an already-committed business transaction. How exceptions propagate to the caller depends on callback placement and the dispatch mechanism; do not use exception propagation as a substitute for retry/recovery.

**No durable delivery by default:** callbacks are registered via in-process transaction synchronization. If the application dies right after commit before the callback completes, plain Spring Framework **does not automatically persist a publication queue** for redelivery.

## 4. Writing Audit DB Records After Commit Must Use a New Transaction

An important detail in the Spring documentation: after a transaction commits, the old transactional resources may still be bound to the thread during the callback. A DB statement in the listener may continue seeing the old resource yet **never issue another commit** for the new changes.

Therefore, when an audit callback needs to write to the DB, use `PROPAGATION_REQUIRES_NEW`:

~~~java
@Configuration
class AuditTransactionConfig {

    @Bean("auditTx")
    TransactionTemplate auditTx(
            DataSourceTransactionManager manager) {
        TransactionTemplate template =
            new TransactionTemplate(manager);
        template.setPropagationBehavior(
            TransactionDefinition.PROPAGATION_REQUIRES_NEW
        );
        return template;
    }
}
~~~

This is an **excerpt**, requiring imports for Spring configuration, `TransactionTemplate`, `TransactionDefinition`, and the transaction manager. `REQUIRES_NEW` starts a fresh physical transaction suitable for the audit write, with its own commit lifecycle.

Equivalently, place the audit-writing method on a bean invoked **through a Spring transactional proxy**:

~~~java
@Service
class AuditWriter {
    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void record(OrderApproved event) {
        // auditRepository.insert(...);
    }
}
~~~

These two snippets are **alternatives**. With `@Transactional`, if the same bean calls `this.record(...)` internally in standard proxy mode, transactional advice may be bypassed. `TransactionTemplate` often makes transaction boundaries clearer in examples and tests.

Distinguish clearly:
- `@TransactionalEventListener` decides **when the listener is invoked**.
- `@Transactional`/`TransactionTemplate` decides **which transaction wraps the audit write**.
- `@Async` only decides **which executor/thread runs the work**; it does not create transactions, durability, or context propagation by itself.

## 5. Which Fields Should an Audit Event Carry?

A minimal contract:

~~~java
public record AuditFact(
    String eventId,
    String aggregateType,
    String aggregateId,
    String actionCode,
    String actorId,
    String correlationId,
    java.time.Instant occurredAt
) { }
~~~

This is an illustrative record. When a system has many action types, distinguish a business event like `OrderApproved` from a generic `AuditFact` schema. Do not emit a generic `AuditFact` event too early if doing so loses domain semantics.

| Field | Purpose | Notes |
| --- | --- | --- |
| `eventId` | Identifies **one logical event** | Keep stable across retries/redeliveries |
| `aggregateId` and `aggregateType` | Target object affected | May be sensitive; apply hashing/retention |
| `actionCode` | Stable action code | E.g., `order.approved`, not free-form message text |
| `actorId` | Account/identity performing the action | Must come from an authenticated/authorized source |
| `correlationId` | Links request/workflow | Does not replace `eventId` |
| `occurredAt` | Time of the business event | Distinct from when the audit row is recorded |
| `outcome` | `COMMITTED`, `REJECTED`, ... | Does not imply external delivery succeeded |
| `schemaVersion` | Event schema version | Useful as payloads evolve over time |

Avoid passing raw `Authentication`, access tokens, `HttpServletRequest`, managed JPA entities, or lists containing personal data into events. Async/after-commit listeners may execute outside the original request/session scope; a small DTO carrying selected fields is safer and easier to test.

### Trusted actorId Is Captured at the Business Boundary

~~~java
Authentication auth = SecurityContextHolder.getContext()
    .getAuthentication();
if (auth == null || !auth.isAuthenticated()) {
    throw new AccessDeniedException("Authentication required");
}
String actorId = auth.getName();
~~~

This is an excerpt requiring a policy for anonymous authentication: `AnonymousAuthenticationToken` can also be marked authenticated. The application must authorize the action per its policy before assigning the actor to the event. Never treat a client-supplied `actorId` as authenticated proof.

## 6. Complete Java 17+ Integration Example: AFTER_COMMIT Audit + H2

The following example is a Java 17+ integration test using Spring Framework 6.2, Spring JDBC, H2, and JUnit 5, **without Spring Boot**. The service writes an `order_record` inside a transaction; after commit, the listener writes an `audit_entry` using a `TransactionTemplate(REQUIRES_NEW)`. The test demonstrates both the happy path and failure windows.

### 6.1. Gradle Configuration

`settings.gradle`:

~~~groovy
rootProject.name = 'spring-audit-event-demo'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
}
repositories {
    mavenCentral()
}
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
dependencies {
    testImplementation platform('org.springframework:spring-framework-bom:6.2.9')
    testImplementation 'org.springframework:spring-context'
    testImplementation 'org.springframework:spring-jdbc'
    testImplementation 'org.springframework:spring-tx'
    testImplementation 'org.springframework:spring-test'
    testImplementation 'org.junit.jupiter:junit-jupiter:5.11.4'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher:1.11.4'
    testRuntimeOnly 'com.h2database:h2:2.3.232'
}
tasks.named('test') {
    useJUnitPlatform()
}
~~~

With Spring Boot, prefer aligned dependency versions managed by Boot. H2 is an in-memory database for testing: do not use this test result as proof of durability across a JVM crash.

### 6.2. src/test/java/example/audit/AfterCommitAuditTest.java

~~~java
package example.audit;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.sql.Timestamp;
import java.time.Instant;
import java.util.List;
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.concurrent.atomic.AtomicBoolean;
import javax.sql.DataSource;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;
import org.springframework.transaction.support.TransactionTemplate;

@SpringJUnitConfig(AfterCommitAuditTest.Config.class)
class AfterCommitAuditTest {

    @Autowired JdbcTemplate jdbc;
    @Autowired ApprovalService service;
    @Autowired ApplicationEventPublisher publisher;
    @Autowired AuditListener listener;

    @BeforeEach
    void reset() {
        jdbc.execute(
            "CREATE TABLE IF NOT EXISTS order_record (" +
            "id VARCHAR(50) PRIMARY KEY, state VARCHAR(20) NOT NULL)"
        );
        jdbc.execute(
            "CREATE TABLE IF NOT EXISTS audit_entry (" +
            "event_id VARCHAR(50) PRIMARY KEY, " +
            "order_id VARCHAR(50) NOT NULL, " +
            "actor_id VARCHAR(50) NOT NULL, " +
            "action_code VARCHAR(50) NOT NULL, " +
            "occurred_at TIMESTAMP NOT NULL)"
        );
        jdbc.update("DELETE FROM audit_entry");
        jdbc.update("DELETE FROM order_record");
        listener.reset();
    }

    @Test
    void committedOrderGetsAuditRow() {
        service.approve("ORD-1", "evt-1", "alice", false);
        assertEquals(1, orders("ORD-1"));
        assertEquals(1, audits("evt-1"));
        assertEquals("alice", jdbc.queryForObject(
            "SELECT actor_id FROM audit_entry WHERE event_id=?",
            String.class, "evt-1"
        ));
        assertEquals("order.approved", jdbc.queryForObject(
            "SELECT action_code FROM audit_entry WHERE event_id=?",
            String.class, "evt-1"
        ));
    }

    @Test
    void sourceRollbackSkipsAfterCommitAudit() {
        assertThrows(IllegalStateException.class, () ->
            service.approve("ORD-2", "evt-2", "bob", true));
        assertEquals(0, orders("ORD-2"));
        assertEquals(0, audits("evt-2"));
    }

    @Test
    void publicationWithoutTransactionDoesNotInvokeListener() {
        publisher.publishEvent(new OrderApproved(
            "evt-3", "ORD-3", "carol", Instant.now()
        ));
        assertEquals(0, audits("evt-3"));
    }

    @Test
    void auditFailureCannotUndoCommittedOrder() {
        listener.failNextWrite();
        service.approve("ORD-4", "evt-4", "dave", false);
        assertEquals(1, orders("ORD-4"));
        assertEquals(0, audits("evt-4"));
        assertEquals(List.of("evt-4"), listener.failedIds());
    }

    private int orders(String orderId) {
        return jdbc.queryForObject(
            "SELECT COUNT(*) FROM order_record WHERE id=?",
            Integer.class, orderId);
    }

    private int audits(String eventId) {
        return jdbc.queryForObject(
            "SELECT COUNT(*) FROM audit_entry WHERE event_id=?",
            Integer.class, eventId);
    }

    record OrderApproved(
        String eventId, String orderId,
        String actorId, Instant occurredAt) { }

    static class ApprovalService {
        private final JdbcTemplate jdbc;
        private final TransactionTemplate businessTx;
        private final ApplicationEventPublisher publisher;

        ApprovalService(JdbcTemplate jdbc,
                TransactionTemplate businessTx,
                ApplicationEventPublisher publisher) {
            this.jdbc = jdbc;
            this.businessTx = businessTx;
            this.publisher = publisher;
        }

        void approve(String orderId, String eventId,
                String actorId, boolean forceRollback) {
            businessTx.executeWithoutResult(status -> {
                jdbc.update(
                    "INSERT INTO order_record(id,state) VALUES (?,?)",
                    orderId, "APPROVED");
                publisher.publishEvent(new OrderApproved(
                    eventId, orderId, actorId, Instant.now()));
                if (forceRollback) {
                    throw new IllegalStateException("forced rollback");
                }
            });
        }
    }

    static class AuditListener {
        private final JdbcTemplate jdbc;
        private final TransactionTemplate auditTx;
        private final AtomicBoolean failNext = new AtomicBoolean();
        private final ConcurrentLinkedQueue<String> failed =
            new ConcurrentLinkedQueue<>();

        AuditListener(JdbcTemplate jdbc, TransactionTemplate auditTx) {
            this.jdbc = jdbc;
            this.auditTx = auditTx;
        }

        @TransactionalEventListener(
            phase = TransactionPhase.AFTER_COMMIT)
        public void onApproved(OrderApproved event) {
            try {
                auditTx.executeWithoutResult(status -> {
                    if (failNext.getAndSet(false)) {
                        throw new IllegalStateException(
                            "audit store unavailable");
                    }
                    jdbc.update(
                        "INSERT INTO audit_entry(" +
                        "event_id,order_id,actor_id," +
                        "action_code,occurred_at) " +
                        "VALUES (?,?,?,?,?)",
                        event.eventId(), event.orderId(),
                        event.actorId(), "order.approved",
                        Timestamp.from(event.occurredAt())
                    );
                });
            } catch (RuntimeException ex) {
                // Test probe illustrating failure: NOT durable!
                failed.add(event.eventId());
            }
        }

        void failNextWrite() {
            failNext.set(true);
        }

        List<String> failedIds() {
            return List.copyOf(failed);
        }

        void reset() {
            failNext.set(false);
            failed.clear();
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class Config {
        @Bean
        DataSource dataSource() {
            return new DriverManagerDataSource(
                "jdbc:h2:mem:audit_demo;DB_CLOSE_DELAY=-1",
                "sa", "");
        }

        @Bean
        JdbcTemplate jdbcTemplate(DataSource dataSource) {
            return new JdbcTemplate(dataSource);
        }

        @Bean
        DataSourceTransactionManager transactionManager(
                DataSource dataSource) {
            return new DataSourceTransactionManager(dataSource);
        }

        @Bean("businessTx")
        TransactionTemplate businessTx(
                DataSourceTransactionManager manager) {
            return new TransactionTemplate(manager);
        }

        @Bean("auditTx")
        TransactionTemplate auditTx(
                DataSourceTransactionManager manager) {
            TransactionTemplate template =
                new TransactionTemplate(manager);
            template.setPropagationBehavior(
                TransactionDefinition.PROPAGATION_REQUIRES_NEW);
            return template;
        }

        @Bean
        ApprovalService service(
                JdbcTemplate jdbc,
                @Qualifier("businessTx") TransactionTemplate tx,
                ApplicationEventPublisher publisher) {
            return new ApprovalService(jdbc, tx, publisher);
        }

        @Bean
        AuditListener listener(
                JdbcTemplate jdbc,
                @Qualifier("auditTx") TransactionTemplate tx) {
            return new AuditListener(jdbc, tx);
        }
    }
}
~~~

### 6.3. Running and Reading Results

In a project with the Gradle wrapper:

~~~bash
./gradlew test --tests "example.audit.AfterCommitAuditTest"
~~~

On Windows PowerShell:

~~~powershell
./gradlew.bat test --tests "example.audit.AfterCommitAuditTest"
~~~

There is no fixed business stdout: the tests use JUnit assertions directly against the database. Expected results:

| Test | Order | Audit | Conclusion |
| --- | --- | --- | --- |
| `committedOrderGetsAuditRow` | `ORD-1` present | `evt-1` present | Audit written after commit in a new transaction |
| `sourceRollbackSkipsAfterCommitAudit` | `ORD-2` absent | `evt-2` absent | Rollback does not trigger `AFTER_COMMIT` callback |
| `publicationWithoutTransactionDoesNotInvokeListener` | Unchanged | `evt-3` absent | No active transaction; skipped by default |
| `auditFailureCannotUndoCommittedOrder` | `ORD-4` present | `evt-4` absent | Post-commit audit failure does not roll back business TX |

This is a **synchronous listener example in the after-commit callback**, with `@Async` disabled. The callback and new audit transaction finish before `businessTx.executeWithoutResult` returns, so assertions can run immediately. If `@Async` is enabled or audits are sent to a broker, wait for an observable outcome with a timeout (`Awaitility`, `CountDownLatch`, or an application-provided future), never `Thread.sleep`.

The final test **intentionally demonstrates that a failed audit can be lost**: the listener's `ConcurrentLinkedQueue` is merely an in-memory probe, not a durable failure journal. **Do not copy this catch-and-swallow pattern into production** when audits are mandatory.

## 7. Why AFTER_COMMIT Does Not Guarantee Audits Are Never Lost

Consider three failure windows:

~~~text
(A) Business transaction is open
    -> error -> rollback
    -> AFTER_COMMIT does not run
    -> there should be no "approved committed" audit

(B) DB already committed, JVM dies before callback
    -> business record exists
    -> no audit
    -> Spring ApplicationEventPublisher has no durable backlog

(C) Callback already sent audit to external system
    -> process dies before recording completion
    -> retry may send duplicate audit
~~~

`@TransactionalEventListener` handles running only after commit properly, but does not persist events/attempts for recovery. Likewise, `@Async` only switches threads/executors; it does **not** automatically persist tasks durably, provide built-in retries, or prevent executor rejections.

### Transactional Outbox Pattern

A stronger model:

~~~text
BEGIN business transaction
  UPDATE order
  INSERT audit_outbox(
      event_id, action_code, aggregate_id,
      actor_id, payload_ref, status=PENDING)
COMMIT

Background worker:
  claim PENDING via atomic update/lease
  -> send or write audit with idempotency key
  -> mark SENT if sink confirms
  -> error: FAILED, retry with backoff
  -> max attempts exceeded: DEAD, alert/reconciliation
~~~

**Decisive point:** the business change and the outbox row are written **in the same transaction**. If it rolls back, both disappear; if it commits, the audit intent remains in the DB and a worker can recover after a process crash. An `AFTER_COMMIT` callback can be used as a "nudge" to wake the worker and cut latency, but the worker **must still scan the outbox** because a nudge can be lost.

Excerpt for a `@Transactional` service:

~~~java
@Transactional
public void approve(String orderId) {
    String actor = currentVerifiedActorId();
    orderRepository.approve(orderId);
    auditOutboxRepository.insert(
        nextEventId(), "order.approved", orderId, actor);
}
~~~

This is an excerpt, not a standalone class; repositories and helpers are application-defined. To achieve an atomic commit, both repositories must participate in the **same transaction manager/resource**, rather than sending HTTP or writing to a non-transactional DB and assuming atomicity.

### Audit Sink Idempotency

An outbox typically provides **at-least-once delivery**. It can happen that the sink accepts the audit successfully, the process dies before marking `SENT`, and the worker retries. Use a stable `event_id` and a unique key per logical audit action (or `(event_id, handler_id)` across multiple sinks). A standalone `SELECT EXISTS` followed by `INSERT` is not enough to prevent races between two workers; use a proper unique constraint/atomic upsert and classify duplicate errors accurately.

**You cannot claim end-to-end exactly-once** merely because a Spring callback runs once. External APIs, DB transactions, and broker acknowledgements have distinct failure windows; idempotency contracts and reconciliation at the destination are required.

## 8. Spring Modulith Event Publication Registry

If the application uses Spring Modulith, the **Event Publication Registry** can persist publications destined for transactional listeners within the business transaction, track completion, and provide resubmission for incomplete publications. Official documentation: <https://docs.spring.io/spring-modulith/reference/events.html>.

Module listener excerpt:

~~~java
@Component
class AuditModuleListener {

    @ApplicationModuleListener
    void on(OrderApproved event) {
        auditRepository.insertIfAbsent(event);
    }
}
~~~

This snippet only illustrates the Spring Modulith concept, requiring the right imports, starter dependencies, and `auditRepository` bean; it **does not belong to the H2 test project above**. `@ApplicationModuleListener` provides transactional/async semantics suitable for module-event handling according to its version. Even though the registry stores publications, the application still needs an audit schema, security policies, an idempotent sink, retention, and monitoring.

With Spring Modulith 2.x, the publication lifecycle includes statuses such as `PUBLISHED`, `PROCESSING`, `COMPLETED`, `FAILED`, and `RESUBMITTED`; APIs and properties must be verified against **your project's exact version**. Do not blindly apply 2.x examples to a Modulith 1.x app, and do not treat a registry record itself as a complete **audit trail**.

If you do not use Modulith, you can implement an outbox or message broker with separate consumer tracking. For audits spanning multiple services, consider audit sink retention, schema evolution, consumer idempotency, replay permissions, and data protection strategies.

## 9. Recording the Right Audit Type for Rejected Actions

An `AFTER_COMMIT` listener intentionally **does not run when a transaction rolls back**. So audits for "login failed," "access denied," or "approve attempted but rejected" must be recorded elsewhere.

You can separate clearly:

- **Audit of committed actions:** `OrderApproved` published in the transaction, handled by an `AFTER_COMMIT` listener or outbox.
- **Audit of rejected attempts:** events/logs recording a `REJECTED` outcome from the policy/validation path, with their own transaction and reliability guarantees.
- **Audit of system events:** background tasks with no direct human user, recording `actorType=SYSTEM`, `serviceId`, and a meaningful `correlationId`.

Do not enable `fallbackExecution=true` just to "catch all cases": it alters the transactional contract and does not by itself solve failed attempts or durable delivery.

Separate `occurredAt` in the event (when the action happened) from `recordedAt` in the audit table (when the audit was saved). The two timestamps can diverge due to queue delay or retries, so do not treat that difference as evidence of tampering without checking clock sources and latency.

## 10. Security, Privacy, and Audit Integrity

Audits easily contain sensitive data. Even an event with `actorId`, `aggregateId`, or old/new values can constitute PII in certain contexts.

Principles to apply:

1. **Allowlist fields** instead of serializing entire entities or HTTP payloads.
2. **Never store credentials:** passwords, access/refresh tokens, API keys, session cookies, or authorization headers.
3. **Verified identity:** capture the actor from the authentication/authorization context at the business boundary; async listeners do not automatically inherit the caller's `SecurityContext`.
4. **Synchronized timezone:** store `Instant`/UTC or timestamps with an explicit timezone policy; distinguish event time from recorded time.
5. **Read/write authorization:** the audit ledger needs dedicated access controls, edit/delete restrictions, encryption, and appropriate retention.
6. **Tamper evidence when required:** append-only controls, hashing/signatures/immutable storage, and integrity checks; an ordinary SQL table is not inherently tamper-proof.
7. **Before/after data:** record only necessary fields, and evaluate retention and right-to-be-forgotten/deletion rules under applicable regulations.

When the actor may be anonymous or a system process, the audit schema should include actor type or system ID rather than fabricating a default "user." Never log the entire `Authentication` object, as it may contain sensitive credentials.

## 11. Monitoring and Reconciliation

Do not just check whether a listener logged `"audit requested"`. Observe **successfully persisted audits** and pending backlogs:

| Metric | Purpose |
| --- | --- |
| Audit write failures by action/handler | Detect sink/DB failures |
| Oldest `PENDING` age / outbox lag | Detect undelivered events |
| Retry attempts and dead-letter backlog | Detect stuck workers or prolonged failures |
| Audit persisted latency | Time from commit to audit row/sink ACK |
| Missing audit reconciliation count | Detect business changes lacking corresponding audits |
| Duplicate audit events deduped | Track idempotency and retries |
| Audit storage growth and retention | Prevent disk/index exhaustion and policy violations |

A useful structured log includes `event_id`, `action_code`, `actor_id` at the permitted level, `aggregate_id`, `correlation_id`, `handler`, `processing_phase`, `attempt`, and sanitized `error_code`. Do not put `eventId` into metric labels because its cardinality is far too high.

When audits are compliance-critical, reconciliation should compare the business data source against the audit ledger. For example, every `order_record.state=APPROVED` within the audited version/policy scope has a corresponding audit event, except for states accounted for by business rules—do not just compare total row counts.

## 12. Common Mistakes

| Mistake | Consequence | How to Handle |
| --- | --- | --- |
| Sync `@EventListener` writing HTTP audit before commit | Audit says "success" for a rolled-back transaction | Use `AFTER_COMMIT` or write in same TX per policy |
| `AFTER_COMMIT` writing DB without a new transaction | Changes may join old transaction resource and never commit | Use `REQUIRES_NEW` |
| Assuming `AFTER_COMMIT` = durable queue | Crash between commit and callback loses audit | Write outbox/registry transactionally |
| Adding `@Async` for "better durability" | Tasks live only in an in-memory executor | Use durable work + retries |
| Catching audit errors and only logging | No audit row and no recovery path | Durable failure tracking, retries/alerts |
| Using unverified `actorId` from request body | Audit records spoofed identity | Capture trusted actor at the service boundary |
| Event contains JPA entity / HTTP request | Lazy-loading, mutable state, leaked context | Small event DTO with immutable fields |
| Missing `eventId`/unique key | Retries create duplicate audits | Idempotency per logical event |
| `@Transactional` test defaults to rollback while expecting `AFTER_COMMIT` | Listener never runs in test | Test commit explicitly via `TransactionTemplate`/`TestTransaction` |
| Mixing audit log with debug logs | Wrong sampling/retention or insufficient access control | Dedicated audit ledger per requirements |
| Writing `SUCCESS` before commit | Wrong outcome if transaction rolls back | Write committed outcome only after commit/atomic TX |
| Using `@Order` to guarantee atomicity | Only changes invocation ordering | Proper transaction boundaries and persistence |

## 13. Implementation Checklist

- [ ] Defined whether audit is mandatory or best-effort, and acceptable downtime/loss limits.
- [ ] If atomic audit is mandatory, business row and audit row/outbox share the same transaction.
- [ ] Events carry a stable ID, action, aggregate, authenticated actor, `occurredAt`/`correlationId`.
- [ ] `@TransactionalEventListener(AFTER_COMMIT)` is used only when binding to commit is intended.
- [ ] Listener writing DB after commit opens a new transaction (or uses a separate worker transaction).
- [ ] Accounted for `fallbackExecution=false` when no transaction is present.
- [ ] Tested commit, rollback, outside-transaction, and audit failure cases.
- [ ] For async: tests wait for outcomes with a timeout, never asserting right after publish.
- [ ] When audits must not be lost: outbox/registry, retry/backoff, idempotency, and reconciliation.
- [ ] Separate handling for failed/denied attempts, not just committed successes.
- [ ] No unnecessary secrets/PII stored; retention, access control, and integrity requirements defined.
- [ ] Monitoring covers pending age, failure ratio, audit lag, and dead-letter queue.
- [ ] Never equate `publishEvent` returning with commit, delivery, or audit success.

## 14. Self-Check Questions

**Question 1:** Why can a plain `@EventListener` write an inaccurate audit?

Because listeners usually run immediately upon publish, possibly **before the transaction commits**. If it writes to an independent storage and the business transaction rolls back, the audit may reflect a change that was never committed.

**Question 2:** Why does `@TransactionalEventListener(AFTER_COMMIT)` not record an audit when the source rolls back?

Because the callback is registered and executed only on the successful commit phase; rollback does not trigger `AFTER_COMMIT`.

**Question 3:** Why should `REQUIRES_NEW` be used to write audit DB records inside an after-commit callback?

The original transaction has completed, yet old resources may remain bound; no subsequent commit occurs on them. A new transaction gives the audit write an independent write/commit unit.

**Question 4:** Can a post-commit audit failure roll back the business transaction that just committed?

No. The audit is a subsequent task and can fail; to prevent loss, use transactionally recorded intent/outbox or write the audit inside the source transaction.

**Question 5:** Does an outbox guarantee the audit sink processes events exactly once?

Not automatically. A worker can finish sending and crash before marking `SENT`. You need an idempotency key at the sink or reconciliation plus a clear retry contract.

**Question 6:** Is the Spring Modulith Registry itself a business audit ledger?

No. It tracks publication/completion to support delivery/recovery; the application still owns the audit schema, contents, permissions, and retention.

**Question 7:** If you want to audit denied access attempts, is `AFTER_COMMIT` enough?

No. Denied attempts may have no transaction or may roll back; you need a separate recording path for failed attempts matching security policy and durability requirements.

**Key takeaway:** `AFTER_COMMIT` ensures audits **only react after the business transaction has committed**; `REQUIRES_NEW` ensures the audit database write is committed separately. Neither **creates durable recovery by itself**. Mandatory audits must be written atomically with the business operation or backed by durable intent (outbox/registry), idempotency, retries, and reconciliation.

## References

- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
- [Spring Framework — TransactionalEventListener Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/event/TransactionalEventListener.html)
- [Spring Framework — TransactionSynchronization.afterCompletion](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/support/TransactionSynchronization.html)
- [Spring Framework — TransactionTemplate](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/support/TransactionTemplate.html)
- [Spring Framework — Application Events](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html)
- [Spring Modulith — Event Publication Registry](https://docs.spring.io/spring-modulith/reference/events.html)
