# Idempotency of Post-Commit Listeners in Spring Framework Application Events

## 1. The problem: already committed, why still guard against duplicate processing?

A payment system updates an order to `PAID` inside a transaction, publishes `PaymentCaptured`, and has a listener request invoice issuance or notify the customer. The listener is annotated with `@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)` so it processes only when the source transaction has committed successfully.

Yet the condition **"run after commit" is not synonymous with "each event runs exactly once"**. Real-world situations:

- The same event may have `publishEvent(...)` called twice due to a logic bug or a business flow being invoked repeatedly.
- A worker re-reads an outbox record not yet marked complete after a process restart.
- An external system already processed a request yet the client timed out, leaving the application unsure of the outcome and forcing a retry.
- Multiple application instances or workers process the same event identifier concurrently.
- A user resubmits the same payment request, causing different components to create or receive duplicate information.

**Idempotent** means executing the same operation multiple times with the **same valid business identifier** still produces **observable effects equivalent to once**. In a post-commit listener, the goal is usually avoiding duplicate invoices, outbox records, entitlements, or notification requests for the **same event/business intent**.

Distinguish:

- **At-most-once**: tasks may be lost, but are never retried.
- **At-least-once**: permits retries to reduce task loss, so duplicates can be received.
- **Idempotent effect**: duplicates may arrive, yet side effects are guarded so duplicate outcomes are not produced.
- **Exactly-once end-to-end**: a much stronger requirement, especially hard across HTTP/email and disparate systems; merely adding `@TransactionalEventListener` does not provide this guarantee.

## 2. What does `AFTER_COMMIT` actually guarantee?

`@TransactionalEventListener` is a listener bound to a **phase of the event-publishing transaction**:

```java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void onPaymentCaptured(PaymentCaptured event) {
    // Handle once the transaction has committed successfully.
}
```

The phases:

| Phase | When is the callback executed? | Suitable for triggering post-commit side effects? |
| --- | --- | --- |
| `BEFORE_COMMIT` | Before commit, with the possibility the transaction later does not commit | Not post-commit |
| `AFTER_COMMIT` | After the transaction commits successfully; this is the default phase | Suitable for starting post-commit handling |
| `AFTER_ROLLBACK` | After rollback | Suitable for reacting to failure |
| `AFTER_COMPLETION` | After the transaction finishes regardless of outcome | For general observation/cleanup work |

By default, when an event is published **with no active transaction**, `@TransactionalEventListener` **does not execute**, because `fallbackExecution` defaults to `false`. If `fallbackExecution = true` is enabled, events published outside a transaction can also be processed; this alters the expected semantics of an "after-commit only" listener, so it must be an intentional decision.

`AFTER_COMMIT` protects **timing**: it does not process events for rolled-back transactions. It **does not** automatically deduplicate, retry, persist events, synchronize across multiple instances, or control external service reliability.

### Pitfall when writing to the database from a post-commit listener

After commit, some old transaction resources may still remain bound to the thread while the callback runs. Per the `TransactionSynchronization` documentation, data access at this point may still join the old context **without a subsequent commit**. Hence, if the listener needs to write to `processed_events` or `outbox`, it must actively create a **new transaction** (usually using `PROPAGATION_REQUIRES_NEW`).

Do not drop an arbitrary `repository.save(...)` into the callback and assume the newly written data will commit. Also do not put `@Transactional(REQUIRES_NEW)` on a method called via `this.method()` in the same bean expecting the Spring proxy to intervene; self-invocation can bypass transaction advice.

## 3. Designing a properly scoped idempotency key

An event should have a stable identifier assigned when the business operation creates the event. For example:

```java
public record PaymentCaptured(
        String eventId,
        String paymentId,
        String orderId,
        long amountInCents
) {}
```

- `eventId` identifies **the same business occurrence** and stays **unchanged** across retries/replays. Do not generate a new UUID on each reprocessing of the same event.
- `paymentId` links to the specific payment transaction.
- `orderId` helps link to the business entity.
- `amountInCents` is an important data snapshot; use integers to avoid currency rounding errors from `double`.

If an event is consumed by multiple components, a single `eventId` key may be too broad. For instance, both `invoice-service` and `email-service` are allowed to process an event. The idempotency key is typically:

```text
(consumer_name, event_id)
```

Or, when the business invariant is truly "at most one invoice per order", `(invoice_type, order_id)` can protect that invariant. The **event key** and the **business invariant key** solve related but distinct problems; critical systems often need both.

Example table design:

```sql
CREATE TABLE processed_events (
    consumer_name VARCHAR(80) NOT NULL,
    event_id      VARCHAR(80) NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);
```

A database unique constraint/primary key is the line of defense **under concurrent processing**. An in-RAM `HashSet` or `ConcurrentHashMap` can be useful for experiments, yet **cannot guarantee deduplication** across restarts, across multiple instances, or when a race occurs between check and write.

### Why is "check then insert" not enough?

```text
Worker A                         Worker B
--------                         --------
SELECT: event not present        SELECT: event not present
send notification                send notification
INSERT marker                    INSERT marker
```

Both A and B can see "not present" before either writes. Running `SELECT` first does not make the operation atomic. You must let the database enforce uniqueness via a **unique constraint**, and place writing the marker together with **transactional** side effects inside one transaction.

## 4. Safe pattern: write marker and outbox in the same new transaction

For database-involved work, a common solution:

1. The business transaction updates state and commits.
2. The `AFTER_COMMIT` listener receives the event.
3. The listener opens a **new** transaction.
4. Attempts to `INSERT` the `(consumer_name, event_id)` key into `processed_events`.
5. If the insert succeeds, in the **same new transaction** write a `notification_outbox` record or another database effect.
6. Commit the new transaction. If the key already exists, treat it as a duplicate delivery and skip per defined policy.
7. A separate worker delivers the outbox to external systems with appropriate retries and idempotency.

The crucial condition is **the marker and outbox commit together or roll back together**. If you write the marker first and then call external email, the application can crash after the marker but before the email: a retry will be blocked and the email lost. If you send the email before the marker, the application can crash after the email but before the marker: a retry sends a duplicate. With email/HTTP outside the database transaction, an internal marker alone **does not guarantee end-to-end exactly-once**.

```text
Business transaction                 New transaction after commit
--------------------                 ----------------------------
Update Order = PAID
publishEvent(PaymentCaptured)
COMMIT ------------------------------> INSERT processed_events
                                       INSERT notification_outbox
                                       COMMIT
                                             |
                                             v
                                       Worker sends externally
                                       (retry + idempotency)
```

## 5. Complete example: Java 17, Spring Framework, JDBC, H2

The example below **runs in a plain `ApplicationContext`**, using Spring Framework 6.2.0, Maven, and in-memory H2. We intentionally publish **two events with the same `eventId`** in **one committed transaction**, then publish another event in a transaction **that rolls back**.

The post-commit listener runs twice for the duplicate event, yet writes only **one marker** and **one outbox row** thanks to the primary key and the new transaction. The event from the rolled-back transaction has no post-commit effect.

**Structure:**

```text
idempotent-after-commit/
├── pom.xml
└── src/main/java/example/IdempotentAfterCommitDemo.java
```

**`pom.xml`:**

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>idempotent-after-commit</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.0</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>6.2.0</version>
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
                <version>3.5.0</version>
                <configuration>
                    <mainClass>example.IdempotentAfterCommitDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

**`src/main/java/example/IdempotentAfterCommitDemo.java`:**

```java
package example;

import java.util.concurrent.atomic.AtomicInteger;
import javax.sql.DataSource;

import org.h2.jdbcx.JdbcDataSource;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;
import org.springframework.transaction.support.TransactionTemplate;

public class IdempotentAfterCommitDemo {

    public record PaymentCaptured(String eventId, String orderId) {}

    public static class ReceiptListener {
        private final JdbcTemplate jdbc;
        private final TransactionTemplate isolatedTx;
        private final AtomicInteger callbacks = new AtomicInteger();
        private final AtomicInteger created = new AtomicInteger();
        private final AtomicInteger duplicates = new AtomicInteger();

        public ReceiptListener(JdbcTemplate jdbc,
                               PlatformTransactionManager manager) {
            this.jdbc = jdbc;
            this.isolatedTx = new TransactionTemplate(manager);
            this.isolatedTx.setPropagationBehavior(
                    TransactionDefinition.PROPAGATION_REQUIRES_NEW);
        }

        @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
        public void onCaptured(PaymentCaptured event) {
            callbacks.incrementAndGet();

            try {
                isolatedTx.executeWithoutResult(status -> {
                    // Atomic claim: unique by consumer + event.
                    jdbc.update(
                        "INSERT INTO processed_events " +
                        "(consumer_name, event_id) VALUES (?, ?)",
                        "receipt", event.eventId());

                    // Same transaction: persist durable send request.
                    jdbc.update(
                        "INSERT INTO notification_outbox " +
                        "(consumer_name, event_id, order_id) " +
                        "VALUES (?, ?, ?)",
                        "receipt", event.eventId(), event.orderId());
                });
                created.incrementAndGet();
            } catch (DuplicateKeyException duplicate) {
                // In this example, duplicate means idempotency key collision.
                // In practice, inspect the exact violated constraint.
                duplicates.incrementAndGet();
            }
        }

        public int callbacks() { return callbacks.get(); }
        public int created() { return created.get(); }
        public int duplicates() { return duplicates.get(); }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {
        @Bean
        public DataSource dataSource() {
            JdbcDataSource ds = new JdbcDataSource();
            ds.setURL("jdbc:h2:mem:idem_demo;DB_CLOSE_DELAY=-1");
            ds.setUser("sa");
            ds.setPassword("");
            return ds;
        }

        @Bean
        public JdbcTemplate jdbcTemplate(DataSource dataSource) {
            return new JdbcTemplate(dataSource);
        }

        @Bean
        public PlatformTransactionManager transactionManager(
                DataSource dataSource) {
            return new DataSourceTransactionManager(dataSource);
        }

        @Bean
        public TransactionTemplate transactionTemplate(
                PlatformTransactionManager manager) {
            return new TransactionTemplate(manager);
        }

        @Bean
        public ReceiptListener receiptListener(
                JdbcTemplate jdbc, PlatformTransactionManager manager) {
            return new ReceiptListener(jdbc, manager);
        }
    }

    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(Config.class)) {
            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);
            TransactionTemplate tx =
                    context.getBean(TransactionTemplate.class);
            ReceiptListener listener =
                    context.getBean(ReceiptListener.class);

            jdbc.execute(
                "CREATE TABLE business_orders (" +
                "order_id VARCHAR(80) PRIMARY KEY, " +
                "status VARCHAR(30) NOT NULL)");
            jdbc.execute(
                "CREATE TABLE processed_events (" +
                "consumer_name VARCHAR(80) NOT NULL, " +
                "event_id VARCHAR(80) NOT NULL, " +
                "PRIMARY KEY (consumer_name, event_id))");
            jdbc.execute(
                "CREATE TABLE notification_outbox (" +
                "consumer_name VARCHAR(80) NOT NULL, " +
                "event_id VARCHAR(80) NOT NULL, " +
                "order_id VARCHAR(80) NOT NULL, " +
                "PRIMARY KEY (consumer_name, event_id))");

            // Transaction 1: commit, yet publish the same event twice.
            tx.executeWithoutResult(status -> {
                jdbc.update(
                    "INSERT INTO business_orders " +
                    "(order_id, status) VALUES (?, ?)",
                    "ORD-1", "PAID");
                context.publishEvent(
                    new PaymentCaptured("evt-001", "ORD-1"));
                context.publishEvent(
                    new PaymentCaptured("evt-001", "ORD-1"));
            });

            // Transaction 2: rollback; AFTER_COMMIT does not run.
            tx.executeWithoutResult(status -> {
                jdbc.update(
                    "INSERT INTO business_orders " +
                    "(order_id, status) VALUES (?, ?)",
                    "ORD-2", "PAID");
                context.publishEvent(
                    new PaymentCaptured("evt-002", "ORD-2"));
                status.setRollbackOnly();
            });

            Integer one = jdbc.queryForObject(
                "SELECT COUNT(*) FROM notification_outbox " +
                "WHERE event_id = ?", Integer.class, "evt-001");
            Integer rolledBack = jdbc.queryForObject(
                "SELECT COUNT(*) FROM notification_outbox " +
                "WHERE event_id = ?", Integer.class, "evt-002");

            System.out.println(
                "AFTER_COMMIT callbacks: " + listener.callbacks());
            System.out.println(
                "Outbox tasks created: " + listener.created());
            System.out.println(
                "Duplicate events skipped: " + listener.duplicates());
            System.out.println(
                "Outbox for evt-001: " + one);
            System.out.println(
                "Outbox for evt-002: " + rolledBack);
        }
    }
}
```

**Run** from the directory containing `pom.xml` using JDK 17+ and Maven:

```bash
mvn -q compile exec:java
```

**Five lines printed by the application** (excluding Maven/Spring logs if any):

```text
AFTER_COMMIT callbacks: 2
Outbox tasks created: 1
Duplicate events skipped: 1
Outbox for evt-001: 1
Outbox for evt-002: 0
```

**Result explanation:**

- Both `publishEvent` calls with `evt-001` register a post-commit callback. When transaction 1 commits, the listener is invoked **twice**.
- On the first call, `INSERT processed_events` succeeds and `INSERT notification_outbox` records one processing request. Both rows commit in the `REQUIRES_NEW` transaction.
- On the second call, the `(consumer_name, event_id)` primary key blocks the duplicate marker record. This new transaction rolls back without adding a second outbox row; `DuplicateKeyException` is caught outside `TransactionTemplate`.
- Event `evt-002` was published inside transaction 2, yet the transaction rolled back, so the `AFTER_COMMIT` callback does not run; there is no outbox row for `evt-002`.
- The example runs synchronously in the post-commit callback so no `sleep` is needed. It proves **idempotency of writing the outbox in the database**, does not send a real email, and **does not** prove exactly-once when an external service is involved.

**Note on error handling:** In the illustrative code, both tables only have the corresponding unique keys so `DuplicateKeyException` represents a key collision. With a production schema, you must identify the **exact constraint** violated. If a duplicate error stems from another invariant or conflicting data, never silently treat it as "already processed".

Dependency versions are pinned so the example is reproducible. In real adoption, use actively maintained Spring/H2 patch releases along with your project's BOM/version management strategy.

## 6. Why does `REQUIRES_NEW` matter?

Consider an easy-to-write snippet lacking guarantees:

```java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void onPaid(PaymentCaptured event) {
    repository.save(new ProcessedEvent(event.eventId()));
}
```

This is only an illustrative integration snippet (missing repository/entity). Because the callback runs after commit, old transaction resources may still be bound to the thread, and there is no subsequent commit for changes participating in that context. **Do not expect `save` in the callback to mean the data was successfully persisted.**

The common approach is delegating to **another service bean**:

```java
@Service
public class IdempotencyService {
    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void reserveAndCreateOutbox(PaymentCaptured event) {
        // INSERT marker with unique key;
        // INSERT outbox in the SAME new transaction.
    }
}

@Component
public class PaidListener {
    private final IdempotencyService service;

    public PaidListener(IdempotencyService service) {
        this.service = service;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void handle(PaymentCaptured event) {
        service.reserveAndCreateOutbox(event);
    }
}
```

This snippet is an integration pattern, not a standalone program: it requires entity/repository definitions and annotation imports. Calling through **another bean** allows `@Transactional(REQUIRES_NEW)` to apply via the Spring proxy; calling `this.reserveAndCreateOutbox(...)` on the same bean in proxy mode usually fails to trigger the expected advice.

In section 5's runnable example, `TransactionTemplate` creates `REQUIRES_NEW` **directly**, avoiding proxy reliance for the new transaction.

## 7. Idempotency and atomicity at the external API boundary

The database can guarantee a single unique marker/outbox record, yet it cannot roll back an email that already left the server or an HTTP request a partner already processed. Analyze the failure points:

| Operation order | Crash point | Consequence if using only a marker |
| --- | --- | --- |
| Write `processed_events` then send email | After marker, before email | Retry is skipped, **email lost** |
| Send email then write `processed_events` | After email, before marker | Retry may **send duplicate email** |
| Write marker and outbox in the same DB transaction | Inside transaction before commit | Both roll back; creating the outbox can be safely retried |
| Worker reads outbox then sends HTTP/email | After provider received it yet before marking sent | Worker may resend; needs receiver-side idempotency or acceptable duplicate policy |

The outbox pattern typically has statuses like `PENDING`, `IN_PROGRESS`, `SENT`, `FAILED`, and timestamps/leases to reclaim stuck work. Workers should **claim atomically** (e.g., conditional update or database-appropriate row locking), send with a partner-supported idempotency key, and mark complete once an explicit result arrives.

If the provider supports an idempotency header/key, pass the same stable key on every retry. If the provider does not support it, you must accept the possibility of repeated side effects or add a partner-status-check mechanism. Never claim "exactly once" simply because a single outbox row was created.

## 8. Processing states and retry strategies

Some systems need more than a simple marker record because the listener performs long-running work:

| Status | Meaning | Action when receiving the same event again |
| --- | --- | --- |
| `NEW` / no marker yet | Work not yet claimed | Claim atomically |
| `PROCESSING` | A worker currently holds a lease | Do not run concurrently, or reclaim if lease expired |
| `DONE` | Idempotent effect completed | Return prior result/skip |
| `FAILED_RETRYABLE` | Transient error | Retry with limit/backoff |
| `FAILED_PERMANENT` | Unrecoverable error | Record for operational handling |

**Do not mark `DONE` too early.** Marking complete before critical side effects are durably saved can cause the system to lose work. Conversely, if an external system's side effect finishes before `DONE` is committed, assume retries can happen and protect the receiver side.

Errors must be classified:

- **Duplicate expected:** unique violation on the exact idempotency key; can skip or return processed status.
- **Transient:** connection drop, deadlock, queue full; retry with bounded attempts and backoff.
- **Business conflict:** same `eventId` yet different critical content; must not be treated as a valid duplicate—detect and raise an error.
- **Permanent:** incompatible schema, invalid data; stop blind retries and route to an error-handling flow.

For events carrying monetary amounts, currencies, or versions, a payload fingerprint can be stored alongside the marker to detect **same key with different data**. Payload hashing must follow a deterministic canonicalization rule; never rely on arbitrary serialization ordering.

## 9. Special notes when using `@Async` with post-commit listeners

A listener may declare:

```java
@Async("billingExecutor")
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void afterCommit(PaymentCaptured event) {
    // Work is handed off to the executor after the phase condition is met.
}
```

This is an illustrative snippet requiring `@EnableAsync`, an executor bean, and active transaction management. Running on a worker has several consequences:

- The original transaction context does not automatically follow `ThreadLocal` to the worker.
- Callback order, completion timing, and exceptions differ from the synchronous version.
- If the pool rejects tasks, the source transaction having committed does not imply subsequent processing succeeded.
- A task waiting in an in-memory executor can be lost if the process crashes.
- **DB idempotency keys and a new transaction are still required**, because async does not naturally make an event execute only once.

Do not rely on `@Order` to guarantee the **completion** order of async tasks. If B needs A's result, express the dependency in a workflow or a durably tracked job.

## 10. Testing idempotency properly

A test must distinguish **callback count** from **side-effect count**. Matrix:

| Scenario | Post-commit callbacks | Expected effect |
| --- | --- | --- |
| Publish one event and commit | 1 | 1 marker, 1 outbox row |
| Publish same `eventId` twice then commit | 2 | Still 1 marker and 1 outbox row |
| Publish then roll back | 0 | No marker/outbox |
| Two workers process same key concurrently | Possibly > 1 attempt | Unique constraint allows only one claim to succeed |
| Send event with different `eventId`, same consumer | Additional callback | Additional effect if business rules permit |
| Same event for `receipt` and `analytics` consumers | Two independent handlers | Each consumer has its own marker |
| Replay after restart | New processing attempt | Does not increase completed effect count |
| Crash after business commit yet before callback | Callback may be lost | Outbox written in business transaction is needed if events cannot be lost |

Practical checks should include:

1. **Real commit/rollback:** test with `PlatformTransactionManager` or appropriate integration tests; do not just invoke the listener method directly.
2. **Count effects in database:** assert row counts or business state, not just log/callback counts.
3. **Concurrency:** have two connections/workers attempt to insert the unique key simultaneously, verifying only one transaction succeeds.
4. **Retries and crash windows:** simulate failures after outbox creation, external send errors, and failures before marking complete.
5. **Key stability:** retries reuse the original `eventId`; same key with different payload is detected.
6. **Isolated rollback of post-commit transaction:** if writing the outbox fails after inserting the marker, the entire new transaction must roll back so a retry can process it next time.

### Avoid pitfalls with default-rollback `@Transactional` tests

A test that opens its own transaction and rolls back at the end may **never run `AFTER_COMMIT` callbacks**. Therefore, actively commit inside the test or manage transactions properly. Calling the annotated method directly only tests the Java body and does not prove Spring bound it to the commit phase.

## 11. Common mistakes

1. **Believing `AFTER_COMMIT` already prevents duplicates.** It only binds callbacks to transaction outcome; each valid publication can still create a separate callback.
2. **Using local memory as the sole deduplication source.** Insufficient across multiple instances, restarts, or races.
3. **Generating a new `eventId` on retry.** The system treats every retry as a new event, defeating idempotency.
4. **Choosing an improperly scoped key.** Using only `orderId` may accidentally block another valid payment event on the same order; using only `eventId` across all consumers may block other subscribers.
5. **`SELECT` first then `INSERT` without a unique constraint.** Both workers can pass the check.
6. **Marking processed before sending external email outside the transaction.** Leaves an email-loss window on crash.
7. **Sending email first then marking processed.** Leaves a duplicate-send window on timeout/crash.
8. **Writing to the database in `AFTER_COMMIT` without opening a new transaction.** Risks joining old transaction resources without committing new changes.
9. **Catching every `DuplicateKeyException` and ignoring it.** Can mask corrupted data or unique violations unrelated to the intended idempotency key.
10. **Confusing a single outbox row with successful exactly-once delivery.** External partners can still receive duplicate requests from retries.
11. **Forgetting that default Spring events live in the same process.** Crashing after commit before the callback can lose the event unless an outbox is written inside the business transaction itself.
12. **Overlooking `fallbackExecution`.** Enabling it casually can run callbacks when no transaction exists to prove commit occurred.

## 12. Production readiness checklist

- Events carry an identifier stable across all replays/retries.
- Idempotency key matches the consumer scope and business invariants.
- Markers have a database unique constraint; never rely solely on "existence checks".
- Markers and related database changes are written **in the same new transaction** inside post-commit callbacks.
- Expected duplicates are distinguished from conflicting-data errors.
- For external APIs/email, an outbox/worker and receiver-side retry/idempotency strategy exist.
- If events must not be lost between business commit and callback, the outbox is created **inside the business transaction** rather than waiting for post-commit callbacks.
- Tests cover commit, rollback, duplicates, concurrency, crashes, and retries.
- Logs/metrics include `eventId`, `consumerName`, duplicate counts, and final status.
- "Exactly once end-to-end" is not claimed if uncontrolled windows remain in external systems.

**Remember:** `@TransactionalEventListener(AFTER_COMMIT)` ensures a listener runs only after a successful commit. **Idempotency**, however, demands stable keys, unique constraints, atomic data updates in a new transaction, and durable persistence/retries when external systems are involved. The two mechanisms complement each other.

## References

- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
- [Javadoc — TransactionalEventListener](https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/transaction/event/TransactionalEventListener.html)
- [Javadoc — TransactionSynchronization](https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/transaction/support/TransactionSynchronization.html)
- [Spring Framework — Programmatic Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html)
